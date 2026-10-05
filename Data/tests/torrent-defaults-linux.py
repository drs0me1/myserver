#!/usr/bin/env python3
"""DD-178/DD-219: compare the seed with qBittorrent's own defaults in the package's container image.

Run as root on a Linux host with Podman and the package image present:
  unshare --net --fork python3 Data/tests/torrent-defaults-linux.py
TORRENT_TEST_IMAGE overrides the image (default: the package's TORRENT_IMAGE). The containers join
the private network namespace (--network host there), never the server's; profiles are disposable.
No installed service, account, image or firewall is changed and nothing is downloaded.
"""
import http.cookiejar
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

DATA = Path(__file__).resolve().parents[1]
# DD-178/DD-219: the seed carries integration keys only; every user preference stays qBittorrent's own
# (DD-218's chosen defaults were reverted in v2-197).
NATIVE = ("upnp", "lsd", "dht", "pex", "encryption", "anonymous_mode", "max_active_downloads", "max_active_uploads",
          "max_active_torrents", "temp_path_enabled", "preallocate_all", "dl_limit", "up_limit", "max_ratio_enabled",
          "max_seeding_time_enabled", "queueing_enabled", "max_connec", "max_connec_per_torrent", "locale",
          "incomplete_files_ext", "web_ui_csrf_protection_enabled", "web_ui_host_header_validation_enabled",
          "web_ui_max_auth_fail_count", "web_ui_ban_duration")


def image():
    value = os.environ.get("TORRENT_TEST_IMAGE") or next(
        (line.split("=", 1)[1].strip() for line in (DATA / "magaza/torrent/torrent.env").read_text().splitlines()
         if line.startswith("TORRENT_IMAGE=")), "")
    assert re.fullmatch(r"[a-z0-9.-]+(/[a-z0-9._-]+)+@sha256:[0-9a-f]{64}", value), "Pinned image required: " + value
    assert subprocess.run(["podman", "image", "exists", value], timeout=30).returncode == 0, \
        "Image not present (set TORRENT_TEST_IMAGE to the one this host runs): " + value
    return value


class Client:
    def __init__(self, root, port, seed, downloads):
        self.root, self.port, self.downloads = root, port, downloads
        self.base = "http://127.0.0.1:%d" % port
        self.name = "konsol-qb-varsayilan-%d" % port
        self.proc = None
        self.log = None
        self.conf = root / "profile/qBittorrent/qBittorrent.conf"
        self.conf.parent.mkdir(parents=True)
        downloads.mkdir(parents=True, exist_ok=True)
        self.conf.write_text(seed)
        for path in [root, *root.rglob("*"), downloads, *downloads.rglob("*")]:
            os.chown(path, 1000, 1000)
        self.conf.chmod(0o600)

    def request(self, endpoint, fields=None):
        payload = None if fields is None else urllib.parse.urlencode(fields).encode()
        request = urllib.request.Request(self.base + "/api/v2/" + endpoint, payload,
                                         {"Origin": self.base, "Referer": self.base + "/"})
        with self.http.open(request, timeout=3) as response:
            return response.read().decode()

    def preferences(self):
        return json.loads(self.request("app/preferences"))

    def start(self, image_ref):
        self.http = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        # The private log may contain a fixture password; never print it on failure.
        self.log = tempfile.TemporaryFile()
        self.proc = subprocess.Popen(
            ["podman", "run", "--rm", "--name", self.name, "--network", "host", "--pull=never",
             "-e", "PUID=1000", "-e", "PGID=1000", "-e", "WEBUI_PORT=%d" % self.port,
             "-v", "%s:/config" % (self.root / "profile"), "-v", "%s:%s" % (self.downloads, self.downloads), image_ref],
            stdin=subprocess.DEVNULL, stdout=self.log, stderr=self.log)
        deadline = time.monotonic() + 60
        password = None
        while time.monotonic() < deadline:
            assert self.proc.poll() is None, "Fixture qBittorrent exited"
            self.log.seek(0)
            match = re.search(r"temporary password is provided for this session:\s*(\S+)",
                              self.log.read().decode(errors="replace"))
            if match:
                password = match[1]
                try:
                    self.request("app/version")
                except urllib.error.HTTPError as error:
                    assert error.code == 403, "Anonymous API must require login"
                    break
                except (OSError, urllib.error.URLError):
                    pass
                else:
                    raise AssertionError("Anonymous API unexpectedly accessible")
            time.sleep(.2)
        else:
            raise AssertionError("Private fixture did not become ready")
        assert password, "No temporary password in the fixture log"
        # qBittorrent 5.2 answers a good login with an empty 204 (older versions said "Ok.").
        assert self.request("auth/login", {"username": "admin", "password": password}) in ("", "Ok.")
        assert re.fullmatch(r"v\d+\.\d+\.\d+.*", self.request("app/version")), "Login did not open a session"
        top = subprocess.run(["podman", "top", self.name, "huid", "comm"], capture_output=True, text=True, timeout=30).stdout
        assert re.search(r"^\s*1000\s+qbittorrent-nox\s*$", top, re.M), "qBittorrent is not uid 1000: " + top
        prefs = self.preferences()
        assert prefs["web_ui_address"] == "*" and prefs["web_ui_port"] == self.port
        assert not prefs["bypass_local_auth"], "Local login protection was lost"

    def stop(self):
        try:
            if self.proc is not None:
                subprocess.run(["podman", "stop", "-t", "20", self.name], capture_output=True, timeout=60)
                try:
                    self.proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                    self.proc.wait(timeout=10)
                    raise AssertionError("Fixture did not stop cleanly")
        finally:
            self.proc = None
            if self.log is not None:
                self.log.close()
                self.log = None


def main():
    assert os.geteuid() == 0, "Root required for the disposable uid-1000 fixture"
    assert os.readlink("/proc/self/ns/net") != os.readlink("/proc/1/ns/net"), "Refusing host network namespace"
    subprocess.run(["ip", "link", "set", "lo", "up"], check=True, timeout=10)
    image_ref = image()
    template = (DATA / "magaza/torrent/qBittorrent.conf").read_text()
    with tempfile.TemporaryDirectory(prefix="konsol-torrent-defaults-") as tmp:
        root = Path(tmp)
        root.chmod(0o755)
        baseline = "[LegalNotice]\nAccepted=true\n[Preferences]\nWebUI\\Address=*\nWebUI\\LocalHostAuth=true\nWebUI\\Port=18555\n"
        downloads = root / "seed/downloads"
        seed = template.replace("__DOWNLOADS_PATH__", str(downloads)).replace("__TORRENT_UI_PORT__", "18556")
        assert "__" not in seed, "Unrendered seed placeholder"
        vanilla = Client(root / "vanilla", 18555, baseline, root / "vanilla-downloads")
        panel = Client(root / "seed", 18556, seed, downloads)
        try:
            vanilla.start(image_ref)
            defaults = vanilla.preferences()
            vanilla.stop()
            panel.start(image_ref)
            current = panel.preferences()
            assert current["save_path"].rstrip("/") == str(downloads)
            for key in NATIVE:
                assert current[key] == defaults[key], "Forced preference: " + key
            print("PASS: native defaults preserved; nonroot start, local login and downloads integration")
            changed = {"upnp": not current["upnp"], "lsd": not current["lsd"], "temp_path_enabled": True,
                       "max_active_downloads": 4}
            panel.request("app/setPreferences", {"json": json.dumps(changed)})
            panel.stop()
            panel.start(image_ref)
            saved = panel.preferences()
            for key, value in changed.items():
                assert saved[key] == value, "User choice lost on restart: " + key
            print("PASS: the seed is a starting point; the user's own choices survive a restart")
        finally:
            panel.stop()
            vanilla.stop()


if __name__ == "__main__":
    main()
