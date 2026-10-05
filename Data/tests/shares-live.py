"""Explicit disposable-host acceptance: prepare, verify after rerun/reboot, cleanup.

Uses production APIs through Caddy and real systemd workers. Creates only its own
random /srv/dav-test-* tree and two accounts. Prints no credentials. Run as root.
"""
import argparse
import base64
import hashlib
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse

sys.path.insert(0, "/usr/local/sbin")
import master_shares

env = master_shares.env_read("/etc/master-stack/state.env")


class UnixConnection(HTTPConnection):
    """DD-180: the root backend refuses Konsol requests that Caddy relays from this host."""
    def __init__(self, path, timeout):
        super().__init__("localhost", timeout=timeout)
        self.socket_path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.socket_path)


def http(method, path, data=None, item=None, password=None, extra=None):
    headers = {"Host": "panel." + env["LOCAL_DOMAIN"], "X-Konsol": "1"}
    # DD-194: Caddy's Konsol paths need a session and refuse host-local callers (DD-180);
    # this host-side test uses the Files backend on loopback and the root socket.
    address, port = "127.0.0.1", int(env["FILES_PANEL_PORT"])
    if item:
        address, port = env["TAILSCALE_IPV4"], int(env["SHARE_PORT"])
        headers = {"Host": address + ":" + str(port), "Authorization": "Basic " + base64.b64encode(
            (item["username"] + ":" + password).encode()).decode()}
        path = "/s/" + item["id"] + "/" + path
    elif isinstance(data, dict):
        headers["Content-Type"] = "application/json"
        data = json.dumps(data)
    headers.update(extra or {})
    root_api = not item and path.startswith(("/api/konsol/", "/api/uygulama/"))
    conn = UnixConnection(env["PANEL_SOCKET"], 45) if root_api else HTTPConnection(address, port, timeout=45)
    try:
        conn.request(method, path, data, headers)
        result = conn.getresponse()
        return result.status, result.read()
    finally:
        conn.close()


def api(action="", data=None):
    code, raw = http("POST" if action else "GET", "/api/konsol/paylasim" + ("/" + action if action else ""), data)
    assert code == 200, (code, raw.decode()[:200])
    assert b'"hash"' not in raw and b'"salt"' not in raw
    return json.loads(raw)


def dav(item, password, method, path="", body=None, extra=None, expected=200):
    code, raw = http(method, path, body, item, password, extra)
    assert code == expected, (method, path, code, expected)
    return raw


def prepare():
    manifest_dir = Path(tempfile.mkdtemp(prefix="master-dav-test-", dir="/var/tmp"))
    root = Path(env["SERVER_ROOT"]) / ("dav-test-" + secrets.token_hex(5))
    state = {"root": str(root), "items": [], "password": secrets.token_hex(20), "writer_password": secrets.token_hex(20)}
    manifest = manifest_dir / "manifest.json"
    def save():
        master_shares.atomic(str(manifest), state)
    save()
    print("Manifest:", manifest, flush=True)
    for name in ("reader", "writer"):
        folder = root / name
        folder.mkdir(parents=True)
        (folder / "hello.txt").write_bytes(b"abcdefghij")
        os.chown(folder / "hello.txt", int(env["DOWNLOADS_UID"]), int(env["DOWNLOADS_GID"]))
        os.chown(folder, int(env["DOWNLOADS_UID"]), int(env["DOWNLOADS_GID"]))
        os.chmod(folder, 0o775)
        data = dict(path=str(folder.relative_to(env["SERVER_ROOT"])), username=root.name + "-" + name,
                    password=state["password"] if name == "reader" else state["writer_password"],
                    connections={"tailscale": {"permission": "ro" if name == "reader" else "rw",
                                                "days": 7, "ack_write": True}})
        result = api("kaydet", data)
        item = next(i for i in result["items"] if i["path"] == data["path"])
        state["items"].append(item)
        save()
    a, b = state["items"]
    p = state["password"]
    q = state["writer_password"]
    for _ in range(30):
        try:
            if http("GET", "hello.txt", item=a, password=p)[0] == 200:
                break
        except OSError:
            pass
        time.sleep(.2)
    assert dav(a, p, "GET", "hello.txt") == b"abcdefghij"
    dav(a, p, "PROPFIND", extra={"Depth": "1"}, expected=207)
    dav(a, p, "GET", "hello.txt", extra={"Authorization": ""}, expected=401)
    dav(dict(b, username=a["username"]), p, "GET", "hello.txt", expected=401)
    for method in ("PUT", "DELETE", "MKCOL", "MOVE", "COPY"):
        dav(a, p, method, "hello.txt", b"denied", expected=403)
    assert dav(a, p, "GET", "hello.txt", extra={"Range": "bytes=2-4"}, expected=206) == b"cde"
    dav(b, q, "MKCOL", "new", expected=201)
    target = "new/" + urllib.parse.quote("Türkçe.txt")
    dav(b, q, "PUT", target, b"new", expected=201)
    dav(b, q, "PUT", target, b"updated", expected=204)
    assert dav(b, q, "GET", target) == b"updated"
    dest = "/s/" + b["id"] + "/copy.txt"
    dav(b, q, "COPY", target, extra={"Destination": dest}, expected=201)
    dav(b, q, "MOVE", "copy.txt", extra={"Destination": "/s/" + a["id"] + "/copy.txt"}, expected=403)
    dav(b, q, "MOVE", "copy.txt", extra={"Destination": dest.replace("copy.txt", "moved.txt")}, expected=201)
    dav(b, q, "DELETE", "moved.txt", expected=204)
    os.symlink(root / "writer", root / "reader" / "escape")
    dav(a, p, "GET", "escape/hello.txt", expected=403)
    dav(a, p, "GET", "%2e%2e/writer/hello.txt", expected=403)
    assert http("GET", "/api/konsol/paylasim", extra={"X-Konsol": ""})[0] == 403
    state["password"] = secrets.token_hex(20)
    api("kaydet", dict(id=a["id"], path=a["path"], username=a["username"],
                       password=state["password"]))
    save()
    time.sleep(.3)
    dav(a, p, "GET", "hello.txt", expected=401)
    dav(a, state["password"], "GET", "hello.txt")
    result = api("kaydet", dict(id=b["id"], connections={
        "tailscale": {"enabled": False}, "wan": {"enabled": False}}))
    paused = next(i for i in result["items"] if i["id"] == b["id"])
    assert not paused["urls"] and not any(c["active"] for c in paused["connections"].values())
    time.sleep(.3)
    dav(b, q, "GET", "hello.txt", expected=403)
    state["registry_digest"] = hashlib.sha256(Path(env["SHARE_STATE_FILE"]).read_bytes()).hexdigest()
    save()
    verify(manifest)
    print("PASS: real Caddy + worker accounts, isolation, RO/RW, Unicode, range, pause, gates; secrets not printed.")


def verify(manifest):
    state = json.loads(Path(manifest).read_text())
    a, b = state["items"]
    current = api()
    assert current["running"]
    assert hashlib.sha256(Path(env["SHARE_STATE_FILE"]).read_bytes()).hexdigest() == state["registry_digest"]
    assert Path(env["SHARE_STATE_FILE"]).stat().st_mode & 0o777 == 0o600
    assert dav(a, state["password"], "GET", "hello.txt") == b"abcdefghij"
    dav(b, state.get("writer_password", state["password"]), "GET", "hello.txt", expected=403)
    pid = subprocess.check_output(["systemctl", "show", "-p", "MainPID", "--value", "master-paylasim"], text=True).strip()
    inspected = b"\n".join(Path("/proc", pid, name).read_bytes() for name in ("cmdline", "environ"))
    inspected += Path(env["SHARE_STATE_FILE"]).read_bytes()
    inspected += Path("/etc/master-stack/state.env").read_bytes()
    inspected += subprocess.check_output(["journalctl", "--since", "-20 minutes", "-u", "master-paylasim",
                                         "-u", "master-panel", "--no-pager", "-o", "cat"])
    for secret in (state["password"], state.get("writer_password", state["password"])):
        assert secret.encode() not in inspected, "Plaintext test credential exposed"
    print("PASS: IDs/hashes/per-connection policies preserved; active reader and disabled writer verified.")


def cleanup(manifest):
    state = json.loads(Path(manifest).read_text())
    for item in state["items"]:
        if any(i["id"] == item["id"] for i in api()["items"]):
            api("kaldir", dict(id=item["id"]))
    root = Path(state["root"])
    assert root.parent == Path(env["SERVER_ROOT"]) and root.name.startswith("dav-test-") and not root.is_symlink()
    assert root.is_dir(), "Test folder disappeared; refuse cleanup of an unexpected target"
    shutil.rmtree(root)
    Path(manifest).unlink()
    Path(manifest).parent.rmdir()
    print("Removed only test accounts, their scratch folder and the private test manifest.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "verify", "cleanup"))
    parser.add_argument("manifest", nargs="?")
    args = parser.parse_args()
    if args.action == "prepare":
        prepare()
    else:
        assert args.manifest
        globals()[args.action](args.manifest)
