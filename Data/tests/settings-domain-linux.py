#!/usr/bin/env python3
"""DD-157: real Caddy + dnsmasq + both API Host gates, isolated from host services.

Root: unshare --net --fork python3 Data/tests/settings-domain-linux.py
Only systemctl is adapted to disposable processes. No real host units touched.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

DATA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DATA / "panel"))
import master_settings as settings
real_run = settings.run


def cmd(*args, **kwargs):
    return real_run(list(args), **kwargs).stdout.strip()


def wait_for(test):
    for _ in range(60):
        if test():
            return
        time.sleep(.1)
    raise AssertionError("Disposable service did not become ready")


def main():
    assert os.geteuid() == 0
    assert os.readlink("/proc/self/ns/net") != os.readlink("/proc/1/ns/net"), "Separate network namespace required"
    cmd("ip", "link", "set", "lo", "up")
    cmd("ip", "link", "add", "tailscale0", "type", "dummy")
    cmd("ip", "addr", "add", "100.64.0.2/32", "dev", "tailscale0")
    cmd("ip", "link", "set", "tailscale0", "up")
    with tempfile.TemporaryDirectory(prefix="konsol-domain-") as temp:
        root = Path(temp)
        root.chmod(0o755)
        e = settings.env_read(DATA / "config/defaults.env")
        # DD-203: the torrent site's upstream port is the package's own setting, not a base default.
        e["TORRENT_UI_PORT"] = settings.env_read(DATA / "magaza/torrent/torrent.env")["TORRENT_UI_PORT"]
        paths = {"SETTINGS_FILE": "etc/settings.json", "SETTINGS_PENDING_FILE": "etc/pending.json",
                 "SETTINGS_DNS_FILE": "dns/konsol.conf", "DNSMASQ_CONF_FILE": "dns/base.conf", "DNSMASQ_CONF_DIR": "dns",
                 "TORRENT_PROFILE_DIR": "profile", "UNIT_DIR": "units", "MODULES_FILE": "etc/modules",
                 "MODULES_DIR": "templates", "RUNTIME_DIR": "run", "SERVER_ROOT": "srv", "DOWNLOADS_PATH": "srv/downloads",
                 "CADDYFILE": "Caddyfile", "CADDY_MODULES_DIR": "caddy-modules",
                 "KONSOL_AUTH_DIR": "etc/konsol"}
        e.update({k: str(root / v) for k, v in paths.items()})
        # DD-180: both private sockets live in the disposable tree, never in the host's /run.
        e.update(PANEL_SOCKET=str(root / "run/api.sock"), CADDY_ADMIN_SOCKET=str(root / "run/caddy-admin.sock"))
        e.update(LOCAL_DOMAIN="ayc", WAN_IPV4="192.0.2.1", TAILSCALE_IPV4="100.64.0.2", CONSOLE_WEB_DIR=str(DATA / "console"),
                 DOWNLOADS_UID="1000", DOWNLOADS_GID="1000", V2_VERSION="test", FILES_PANEL_USER="test", FILES_PANEL_GROUP="test")
        for folder in ("etc", "dns", "profile", "units", "templates/dosya", "templates/torrent", "caddy-modules", "run", "srv/downloads", "srv/media"):
            (root / folder).mkdir(parents=True, exist_ok=True)
        for p in [root / "srv", *(root / "srv").rglob("*")]:
            os.chown(p, 1000, 1000)
        (root / "etc/konsol").mkdir(mode=0o700)  # DD-194: never the host's account folder
        (root / "etc/modules").write_text("dosya\tcalisiyor\ntorrent\tcalisiyor\n")
        (root / "etc/networks").write_text("")
        state = root / "state.env"
        state.write_text("".join(k + '="' + v + '"\n' for k, v in e.items()))
        def render(source):
            text = (DATA / source).read_text()
            for k, v in e.items():
                text = text.replace("__" + k + "__", v)
            return text
        for target, source in {
            "Caddyfile": "templates/Caddyfile", "dns/base.conf": "templates/dnsmasq.conf",
            "dns/modul-torrent.conf": "magaza/torrent/dnsmasq.conf",
            "templates/torrent/dnsmasq.conf": "magaza/torrent/dnsmasq.conf",
            "caddy-modules/torrent.caddy": "magaza/torrent/torrent.caddy",
            "templates/torrent/torrent.caddy": "magaza/torrent/torrent.caddy",
            "templates/dosya/master-files-panel.service": "systemd/master-files-panel.service",
            "units/master-files-panel.service": "systemd/master-files-panel.service",
        }.items():
            (root / target).write_text(render(source))
        m = settings.Manager(state)
        processes = {}
        child_env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", TAILSCALE_IPV4=e["TAILSCALE_IPV4"], XDG_CONFIG_HOME=str(root / "caddy-config"), XDG_DATA_HOME=str(root / "caddy-data"))
        def stop(name):
            p = processes.pop(name, None)
            if p and p.poll() is None:
                p.terminate()
                p.wait(timeout=10)
        def http(host, path="/", port=None, header=True):
            # port: a loopback TCP port, or a Unix socket path for the root backend (DD-180).
            args = ["curl", "--noproxy", "*", "-s", "--max-time", "2", "-o", "/dev/null", "-w", "%{http_code}",
                    "-H", "Host: " + host]
            if port and str(port).startswith("/"):
                args += ["--unix-socket", str(port)]
                address = "localhost"
            else:
                address = ("127.0.0.1:" + str(port)) if port else e["TAILSCALE_IPV4"]
            if header:
                args += ["-H", "X-Konsol: 1"]
            return cmd(*args, "http://" + address + path, check=False)
        def dig(name):
            return cmd("dig", "@127.0.0.1", "+short", "+time=1", "+tries=1", name)
        def start(name):
            stop(name)
            domain = settings.env_read(state)["LOCAL_DOMAIN"]
            if name == "dns":
                args = ["dnsmasq", "--keep-in-foreground", "--conf-file=/dev/null", "--conf-dir=" + e["DNSMASQ_CONF_DIR"]]
                ready = lambda: dig("panel." + domain) == e["TAILSCALE_IPV4"]
            elif name == "caddy":
                args = ["caddy", "run", "--config", e["CADDYFILE"], "--adapter", "caddyfile"]
                ready = lambda: http("panel." + domain, "/giris.html") == "200"
            elif name == "files":
                args = ["setpriv", "--reuid=1000", "--regid=1000", "--clear-groups", "python3", str(DATA / "files-panel/master-files-panel"),
                        "serve", "--listen", "127.0.0.1:" + e["FILES_PANEL_PORT"], "--root", e["SERVER_ROOT"], "--domain=" + domain]
                ready = lambda: http("panel." + domain, "/api/state", e["FILES_PANEL_PORT"]) == "200"
            else:
                args = ["python3", str(DATA / "panel/master-panel"), "serve", "--listen", "unix:" + e["PANEL_SOCKET"],
                        "--state", str(state), "--master-modul", "/bin/false"]
                ready = lambda: http("panel." + domain, "/api/konsol/ayarlar/durum", e["PANEL_SOCKET"]) == "200"
            processes[name] = subprocess.Popen(args, env=child_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            wait_for(ready)
        def adapter(argv, **kwargs):
            if argv[0] != "systemctl":
                return real_run(argv, **kwargs)
            action, unit = argv[1], argv[-1]
            if action == "reload":
                assert unit == "caddy.service"
                cmd("caddy", "reload", "--config", e["CADDYFILE"], "--adapter", "caddyfile", env={"TAILSCALE_IPV4": e["TAILSCALE_IPV4"]})
            elif action == "restart":
                assert unit in ("master-files-panel.service", "dnsmasq")
                start("files" if unit == "master-files-panel.service" else "dns")
            elif action == "is-active":
                assert unit in ("master-settings-guard.timer", "master-files-panel.service")
            elif action == "start":
                assert unit == "master-settings-guard.timer"  # DD-181: apply starts the timer
            else:
                assert action == "daemon-reload"
            return subprocess.CompletedProcess(argv, 0, "", "")
        def dns_test():
            cmd("dnsmasq", "--test", "--conf-file=/dev/null", "--conf-dir=" + e["DNSMASQ_CONF_DIR"])
        def proof(domain, old):
            assert dig("panel." + domain) == e["TAILSCALE_IPV4"]
            assert dig("panel." + old) != e["TAILSCALE_IPV4"]
            assert dig("health." + domain) == ""
            # DD-194: the sign-in page is open; Konsol itself asks the root backend through
            # forward_auth, which refuses this host-local caller (DD-180) under the new name.
            assert http("panel." + domain, "/giris.html") == "200"
            assert http("panel." + domain) == "403"
            # DD-195: the refusal is the address rule, so the snippet's rewritten backend
            # Host (panel.<new>) passed the backend's Host check first.
            assert "Tailscale cihazından" in cmd("curl", "--noproxy", "*", "-s", "--max-time", "2", "-H", "Host: panel." + domain,
                                                 "http://" + e["TAILSCALE_IPV4"] + "/", check=False)
            # Caddy may return an empty 200 for an unmatched Host; there is no
            # site or health payload. Do not mistake status alone for a route.
            assert cmd("curl", "--noproxy", "*", "-s", "--max-time", "2", "-H", "Host: health." + domain,
                       "http://" + e["TAILSCALE_IPV4"] + "/") == ""
            for path, port in (("/api/konsol/ayarlar/durum", e["PANEL_SOCKET"]), ("/api/state", e["FILES_PANEL_PORT"])):
                root_api = port == e["PANEL_SOCKET"]
                # DD-180/194: Caddy's session check refuses what it relays from this host (100.64.0.2
                # is local here); the reply still proves the new name reaches the root backend.
                # Direct calls (root socket, loopback Files port) answer the new name.
                assert http("panel." + domain, path) == "403"
                assert http("panel." + domain, path, port) == "200"
                assert http("panel." + old, path, port) == "403"
                assert http("panel." + domain, path, header=False) == "403"
        try:
            start("root")
            start("files")
            start("dns")
            start("caddy")
            with patch.object(settings, "run", side_effect=adapter), patch.object(m, "dns_test", side_effect=dns_test):
                for confirm in (False, True):
                    with m.locked():
                        m.apply(dict(revision=m.revision(), domain="ev"))
                    proof("ev", "ayc")
                    with m.locked():
                        if confirm:
                            m.confirm({"id": m.pending()["id"], "client": "100.64.0.9", "host": "panel.ev", "kanal": "tailscale"})
                        else:
                            m.rollback()
                            proof("ayc", "ev")
                assert settings.saved_domain(m.config_path) == "ev"
                assert "--domain=ev " in (root / "templates/dosya/master-files-panel.service").read_text()
                assert not m.pending()
            print("PASS real Caddy reload, dnsmasq names, both API Host/header gates, disabled health, domain rollback/confirm, saved-domain")
        finally:
            for name in list(processes):
                stop(name)


if __name__ == "__main__":
    main()
