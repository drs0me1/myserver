"""Real Caddy/qBittorrent HTTPS in an isolated netns, with a test-only CA.

Run: unshare --net --fork python3 Data/tests/publications-proxy-linux.py
No host units, real profiles, public DNS/ACME or trust-store changes.
"""
import argparse
import http.client
import json
import os
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.parse

DATA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DATA / "panel"))
import master_publications as pubs
import master_settings as settings
import master_https as tls


def load_ayar():
    """DD-202: the qBittorrent package's settings worker (its password hash), straight from the repository."""
    import importlib.machinery
    import importlib.util
    loader = importlib.machinery.SourceFileLoader("torrent_ayar", str(DATA / "magaza/torrent/ayar.py"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


ayar = load_ayar()


def cmd(*args):
    return subprocess.run(args, check=True, capture_output=True, timeout=20)


def main():
    import shutil
    if not shutil.which("qbittorrent-nox"):
        # A host without the App Store module cannot start the isolated qBittorrent.
        print("SKIP: qbittorrent-nox is not installed on this host; nothing was changed.", file=sys.stderr)
        sys.exit(3)
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, choices=(443, 18443), default=18443)
    args = parser.parse_args()
    assert os.geteuid() == 0
    assert os.readlink("/proc/self/ns/net") != os.readlink("/proc/1/ns/net"), "Separate namespace required"
    cmd("ip", "link", "set", "lo", "up")
    cmd("ip", "addr", "add", "9.9.9.9/32", "dev", "lo")
    processes = []
    with tempfile.TemporaryDirectory(prefix="publication-proxy-") as directory:
        root = Path(directory); root.chmod(0o755)
        e = settings.env_read(DATA / "config/defaults.env")
        e.update(WAN_IPV4="9.9.9.9", TORRENT_UI_PORT="18555", SHARE_HTTPS_PORT=str(args.port),
                 TORRENT_PROFILE_DIR=str(root / "profile"), SETTINGS_FILE=str(root / "settings.json"),
                 SETTINGS_PENDING_FILE=str(root / "pending.json"), MODULES_FILE=str(root / "modules"),
                 MODULES_DIR=str(root / "templates"), LOCAL_DOMAIN="ayc")
        for folder in ("profile", "profile/qBittorrent", "downloads", "templates/torrent"):
            target = root / folder; target.mkdir(parents=True, exist_ok=True); os.chown(target, 1000, 1000)
        (root / "modules").write_text("torrent\tcalisiyor\n")
        name, password = "torrent.example.net", "Fixture-only-Password-8"
        settings.save_json(e["SETTINGS_FILE"], {"https":{"domain":""}, "web":{"torrent":{"tail":True,"enabled":True,"domain":name}}})
        (root / "templates/torrent/torrent.caddy").write_text("http://torrent.ayc {\n respond 403\n}\n")
        # DD-199: the row, its upstream and its checks come from the package's manifest and module.
        (root / "templates/torrent/paket.env").write_text(
            (DATA / "magaza/torrent/paket.env").read_text().replace("__TORRENT_UI_PORT__", e["TORRENT_UI_PORT"]))
        shutil.copy(DATA / "magaza/torrent/yayin.py", root / "templates/torrent/yayin.py")
        # DD-203: the check module reads the interface port and profile from the package's own env file.
        (root / "templates/torrent/torrent.env").write_text(
            "TORRENT_UI_PORT=%s\nTORRENT_PROFILE_DIR=%s\n" % (e["TORRENT_UI_PORT"], e["TORRENT_PROFILE_DIR"]))
        text = (DATA / "magaza/torrent/qBittorrent.conf").read_text()
        for key, value in dict(e, DOWNLOADS_PATH=str(root / "downloads")).items():
            text = text.replace("__" + key + "__", value)
        text += "WebUI\\Username=fixture\nWebUI\\Password_PBKDF2=" + ayar.password_hash(password) + "\n"
        settings.atomic(root / "profile/qBittorrent/qBittorrent.conf", text, 0o640, (1000,1000))
        cert, key = root / "cert.pem", root / "key.pem"
        cmd("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
            "-subj", "/CN=" + name, "-addext", "subjectAltName=DNS:" + name,
            "-keyout", str(key), "-out", str(cert))
        site = pubs.extra_sites(e)["torrent-wan.caddy"].replace(tls.tls_block(), "\ttls %s %s\n" % (cert, key))
        assert site, "qBittorrent site was not generated"
        config = root / "Caddyfile"
        config.write_text("{\n admin off\n auto_https disable_redirects\n servers {\n protocols h1 h2\n strict_sni_host on\n }\n}\n" + site)
        check = subprocess.run(["caddy","validate","--config",str(config),"--adapter","caddyfile"],capture_output=True,text=True)
        assert check.returncode == 0, check.stderr
        env = dict(os.environ, HOME=e["TORRENT_PROFILE_DIR"], XDG_CONFIG_HOME=e["TORRENT_PROFILE_DIR"],
                   XDG_DATA_HOME=e["TORRENT_PROFILE_DIR"], XDG_CACHE_HOME=e["TORRENT_PROFILE_DIR"]+"/cache")
        context = ssl.create_default_context(cafile=str(cert))
        class Connection(http.client.HTTPSConnection):
            def connect(self):
                self.sock = context.wrap_socket(socket.create_connection((e["WAN_IPV4"], int(e["SHARE_HTTPS_PORT"])), timeout=3), server_hostname=name)
        authority = name + (":" + str(args.port) if args.port != 443 else "")
        def request(path, body=None, cookie=None, origin=None, host=None, extra=None):
            conn = Connection(name, int(e["SHARE_HTTPS_PORT"]), timeout=3)
            headers = {"Host":host or authority, "Origin":origin or "https://"+authority}
            headers.update(extra or {})
            if cookie: headers["Cookie"] = cookie
            if body is not None: headers["Content-Type"] = "application/x-www-form-urlencoded"
            try:
                conn.request("POST" if body is not None else "GET", path, urllib.parse.urlencode(body) if body is not None else None, headers)
                response = conn.getresponse()
                return response.status, response.read(), response.getheader("Set-Cookie")
            finally:
                conn.close()
        try:
            processes.append(subprocess.Popen(["setpriv","--reuid=1000","--regid=1000","--clear-groups","qbittorrent-nox"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
            processes.append(subprocess.Popen(["caddy","run","--config",str(config),"--adapter","caddyfile"], env=dict(os.environ,XDG_DATA_HOME=str(root / "caddy-data"),XDG_CONFIG_HOME=str(root / "caddy-config")), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
            until = time.monotonic()+15
            last = None
            while True:
                try:
                    last = request("/")[:2]
                    if last[0] == 200: break
                except OSError as err:
                    last = str(err)
                assert time.monotonic()<until, ("Isolated apps did not become ready",last,[p.poll() for p in processes])
                time.sleep(.1)
            pubs.security_check(e, "torrent", name, probe=True)
            assert request("/api/v2/app/version")[0] == 403
            assert request("/api/v2/auth/login",dict(username="fixture",password="bad"))[1] == b"Fails."
            code, body, cookie = request("/api/v2/auth/login",dict(username="fixture",password=password))
            assert code == 200 and body == b"Ok." and cookie, (code,body)
            cookie = cookie.split(";",1)[0]
            code, body, _ = request("/api/v2/app/version",cookie=cookie)
            assert code == 200 and body.startswith(b"v"), (code,body)
            assert request("/api/v2/app/version",cookie=cookie,extra={"X-Forwarded-Host":"evil.example.net"})[0] == 200
            assert request("/api/v2/app/preferences",cookie=cookie,origin="https://evil.example.net")[0] == 401
            assert request("/api/v2/app/version",cookie=cookie,host="panel.ayc")[0] == 421
            assert request("/api/konsol/ayarlar",cookie=cookie)[0] == 404
            print("PASS real generated Caddy HTTPS/qBittorrent login, cookie/API, bad-password, CSRF, SNI/Host and Panel isolation (test-only certificate, port %s)" % args.port,flush=True)
        finally:
            for process in reversed(processes):
                if process.poll() is None:
                    process.terminate(); process.wait(timeout=15)


if __name__ == "__main__":
    main()
