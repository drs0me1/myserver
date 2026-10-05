"""Disposable-host ZIP acceptance through real Caddy. Only owned fixtures change."""
import argparse
import hashlib
from http.client import HTTPConnection
import io
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import sys
import tempfile
import time
import urllib.parse
import zipfile

sys.path.insert(0, "/usr/local/sbin")
from master_shares import env_read, atomic
env = env_read("/etc/master-stack/state.env")


def request(method, path, data=None, extra=None):
    headers = {"Host": "panel." + env["LOCAL_DOMAIN"], "X-Konsol": "1"}
    if data is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(data)
    headers.update(extra or {})
    # DD-194: through Caddy every Konsol path needs a session and host-local callers are
    # refused (DD-180); this host-side test talks to the Files backend on loopback.
    conn = HTTPConnection("127.0.0.1", int(env["FILES_PANEL_PORT"]), timeout=20)
    try:
        conn.request(method, path, data, headers)
        response = conn.getresponse()
        return response.status, response.read()
    finally:
        conn.close()


def api(method, path, data=None, expected=200):
    code, body = request(method, path, data)
    assert code == expected, (path, code, body[:300])
    return json.loads(body)


def zip_bytes(entries):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries:
            archive.writestr(name, content)
    return out.getvalue()


def wait(job_id):
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        job = next(j for j in api("GET", "/api/archives")["items"] if j["id"] == job_id)
        if job["status"] not in ("queued", "running"):
            return job
        time.sleep(.1)
    raise AssertionError("Archive job timed out")


def prepare():
    manifest_dir = Path(tempfile.mkdtemp(prefix="master-archive-test-", dir="/var/tmp"))
    manifest = manifest_dir / "manifest.json"
    root = Path(env["SERVER_ROOT"]) / ("archive-test-" + secrets.token_hex(5))
    root.mkdir()
    state = {"root": str(root), "jobs": []}
    atomic(str(manifest), state)
    print("Manifest:", manifest, flush=True)
    (root / "source").mkdir()
    (root / "source" / "Türkçe.txt").write_text("Merhaba İstanbul\n")
    inner = zip_bytes([("hello.txt", b"nested payload")])
    (root / "nested.zip").write_bytes(zip_bytes([("inner.zip", inner)]))
    (root / "escape.zip").write_bytes(zip_bytes([("../outside.txt", b"denied")]))
    (root / "broken.zip").write_bytes(zip_bytes([("ok", b"valid"), ("bad.zip", b"invalid")]))
    # Enough real compression work for cancellation; still bounded scratch data.
    with (root / "cancel.bin").open("wb") as output:
        chunk = secrets.token_bytes(1024 * 1024)
        for _ in range(64):
            output.write(chunk)
    for item in [root, *root.rglob("*")]:
        os.chown(item, int(env["DOWNLOADS_UID"]), int(env["DOWNLOADS_GID"]))
        os.chmod(item, 0o775 if item.is_dir() else 0o664)
    def submit(operation="unzip", **kw):
        data = dict(operation=operation, path=root.name, target=root.name, names=["nested.zip"],
                    name="expanded", nested=True, layers=3, conflict="rename")
        data.update(kw)
        job = api("POST", "/api/archives", data, 202)["job"]
        state["jobs"].append(job["id"])
        atomic(str(manifest), state)
        return job
    def run(operation="unzip", **kw):
        return wait(submit(operation, **kw)["id"])
    assert run()["status"] == "done"
    assert (root / "expanded/inner/hello.txt").read_bytes() == b"nested payload"
    assert (root / "expanded/inner.zip").is_file()
    assert run(name="flat", nested=False)["status"] == "done"
    assert not (root / "flat/inner").exists()
    assert run(name="layer-one", layers=1)["limited"] == 1
    assert run(conflict="skip")["status"] == "skipped"
    assert run(conflict="stop")["status"] == "failed"
    assert run()["result"] == root.name + "/expanded (2)"
    assert run("zip", names=["source"], name="roundtrip.zip")["status"] == "done"
    assert run(names=["roundtrip.zip"], name="roundtrip")["status"] == "done"
    assert (root / "source/Türkçe.txt").read_bytes() == (root / "roundtrip/source/Türkçe.txt").read_bytes()
    for source in ("escape.zip", "broken.zip"):
        assert run(names=[source], name="must-not-exist")["status"] == "failed"
        assert not (root / "must-not-exist").exists()
    job = submit("zip", names=["cancel.bin"], name="cancelled.zip")
    api("POST", "/api/archives/cancel", {"id": job["id"]}, 202)
    assert wait(job["id"])["status"] == "cancelled"
    assert not (root / "cancelled.zip").exists()
    assert request("GET", "/api/archives", extra={"X-Konsol": ""})[0] == 403
    assert request("POST", "/api/archives", {}, {"Sec-Fetch-Site": "cross-site"})[0] == 403
    assert request("GET", "/api/list?path=" + urllib.parse.quote(env["FILES_ARCHIVE_DIR"]))[0] == 403
    entries = api("GET", "/api/list?path=")["entries"]
    assert env["FILES_ARCHIVE_DIR"] not in [entry["name"] for entry in entries]
    state["digest"] = hashlib.sha256((root / "expanded/inner/hello.txt").read_bytes()).hexdigest()
    atomic(str(manifest), state)
    verify(manifest)
    print("PASS: ZIP roundtrip, nested/depth/off, rename/skip/stop, traversal/corrupt rollback, cancellation, API gates.")


def verify(manifest):
    state = json.loads(Path(manifest).read_text())
    root = Path(state["root"])
    assert hashlib.sha256((root / "expanded/inner/hello.txt").read_bytes()).hexdigest() == state["digest"]
    current = {j["id"]: j for j in api("GET", "/api/archives")["items"]}
    assert all(jid in current and current[jid]["status"] not in ("queued", "running") for jid in state["jobs"])
    workspace = Path(env["SERVER_ROOT"]) / env["FILES_ARCHIVE_DIR"]
    assert stat.S_IMODE(workspace.stat().st_mode) == 0o700
    assert stat.S_IMODE((workspace / "jobs.json").stat().st_mode) == 0o600
    assert sorted(p.name for p in workspace.iterdir()) == ["jobs.json"]
    print("PASS: completed job history, output content and private workspace preserved.")


def cleanup(manifest):
    state = json.loads(Path(manifest).read_text())
    root = Path(state["root"])
    assert root.parent == Path(env["SERVER_ROOT"]) and root.name.startswith("archive-test-") and not root.is_symlink()
    shutil.rmtree(root)
    Path(manifest).unlink()
    Path(manifest).parent.rmdir()
    print("Removed only the archive-test scratch tree and its private manifest; job history retained.")


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
