"""DD-235: Files' "Sistem (/)" view: the same backend in --sistem mode, root over the whole server.
Temporary directories and a temporary Unix socket only; nothing touches real system paths."""
import http.client
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

import test_resources as resources

SOURCE = Path(__file__).resolve().parents[1] / "files-panel" / "master-files-panel"
loader = importlib.machinery.SourceFileLoader("files_panel_system", str(SOURCE))
spec = importlib.util.spec_from_loader(loader.name, loader)
fp = importlib.util.module_from_spec(spec)
loader.exec_module(fp)

REMOTE = "100.100.1.2"  # a tailnet address this host does not own


class SystemFilesTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="sistem-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        for name in ("etc", "proc", "sys", "dev", "run", "mnt/disk/data"):
            (self.root / name).mkdir(parents=True)
        (self.root / "etc/hosts").write_text("127.0.0.1 localhost\n")
        self.files = fp.Files(str(self.root), "", system=True)

    def test_pseudo_filesystem_folders_are_managed_like_any_other(self):
        # DD-238: no read-only roots (the administrator's request); on a real host the kernel's own
        # answers (EPERM, EROFS) still apply. Nothing overwrites an existing item, as everywhere.
        self.assertFalse(hasattr(fp, "SYSTEM_READONLY"))
        for top in ("proc", "sys", "dev", "run"):
            with self.subTest(top=top):
                self.files.mkdir([top], "x")
                self.files.upload_check([top], "y", 1)
                self.files.rename([top], "x", "x2")
                self.files.move([top], ["x2"], ["etc"])
                self.assertTrue((self.root / "etc/x2").is_dir())
                self.files.move(["etc"], ["x2"], [top])
                self.assertEqual(self.files.delete([top], ["x2"], mounts=[]), ["x2"])
                self.assertFalse((self.root / top / "x2").exists())
        self.files.rename([], "run", "run2")
        self.files.rename([], "run2", "run")
        self.assertEqual(self.files.listing(["proc"], False)["entries"], [])

    def test_new_items_are_root_style(self):
        self.files.mkdir(["etc"], "yeni")
        self.assertEqual((self.root / "etc/yeni").stat().st_mode & 0o777, 0o755)
        with patch.object(fp, "disk_room"):
            self.files.upload(["etc"], "a.conf", io.BytesIO(b"x=1\n"), 4)
        self.assertEqual((self.root / "etc/a.conf").stat().st_mode & 0o777, 0o644)

    def test_dir_sizes_are_walked_only_on_local_file_systems(self):
        # DD-248: a folder on a local disk type gets its walked size; one on any other device (/proc,
        # overlay, a network share) keeps only its count. A folder listing asks mountinfo once.
        (self.root / "etc/sub").mkdir()
        (self.root / "etc/sub/big").write_bytes(b"x" * 1000)
        dev = os.stat(self.root).st_dev
        with patch.object(fp, "local_devices", return_value={dev}) as local:
            etc = {e["name"]: e for e in self.files.listing([], False)["entries"]}["etc"]
        local.assert_called_once_with()
        self.assertEqual(etc["size"], len("127.0.0.1 localhost\n") + 1000)
        with patch.object(fp, "local_devices", return_value=set()):
            etc = {e["name"]: e for e in self.files.listing([], False)["entries"]}["etc"]
        self.assertIsNone(etc["size"])
        self.assertEqual(etc["count"], 2)
        with patch.object(fp, "local_devices") as local:
            self.files.listing([], True)
        local.assert_not_called()

    def test_size_walk_stays_on_one_device(self):
        # DD-248: like du -x; an entry on another device is neither counted nor entered.
        (self.root / "etc/sub").mkdir()
        (self.root / "etc/sub/big").write_bytes(b"x" * 1000)
        dev = os.stat(self.root).st_dev
        with fp.DirFd(os.open(self.root, fp.O_DIR)) as fd:
            self.assertEqual(fp.dir_size(fd, "etc", [100], dev), 1020)
            self.assertEqual(fp.dir_size(fd, "etc", [100], dev + 1), 0)
            self.assertEqual(fp.dir_size(fd, "etc", [100]), 1020)

    def test_local_devices_reads_the_type_after_the_separator(self):
        info = self.root / "mountinfo"
        info.write_text("22 1 254:3 / / rw,relatime shared:1 - ext4 /dev/vda3 rw\n"
                        "23 22 0:23 / /proc rw shared:12 - proc proc rw\n"
                        "24 22 0:25 / /run rw shared:5 - tmpfs tmpfs rw\n"
                        "25 22 0:54 / /var/lib/containers/storage/overlay/x/merged rw - overlay overlay rw\n"
                        "26 22 0:60 / /mnt/nas rw - nfs4 nas:/data rw\n"
                        "27 22 8:17 / /mnt/usb rw - vfat /dev/sdb1 rw\n"
                        "broken line\n")
        self.assertEqual(fp.local_devices(str(info)), {os.makedev(254, 3), os.makedev(0, 25), os.makedev(8, 17)})
        self.assertEqual(fp.local_devices(str(self.root / "yok")), set())

    def test_no_reserved_names_and_no_trash(self):
        # /srv's reserved workspace names mean nothing here.
        self.files.mkdir([], ".cop")
        self.assertIn(".cop", [e["name"] for e in self.files.listing([], False)["entries"]])

    def test_delete_is_permanent_and_stops_at_mount_points(self):
        mount = str(self.root / "mnt/disk")
        for target in (["mnt"], ["mnt", "disk"]):
            with self.subTest(target=target):
                with self.assertRaises(fp.PanelError) as err:
                    self.files.delete(target[:-1], [target[-1]], mounts=["/", mount])
                self.assertEqual(err.exception.code, 409)
        self.assertTrue((self.root / "mnt/disk/data").is_dir())
        # A mount whose name only starts the same way does not protect its sibling.
        (self.root / "mnt/disk2").mkdir()
        self.assertEqual(self.files.delete(["mnt"], ["disk2"], mounts=["/", mount]), ["disk2"])
        self.assertEqual(self.files.delete([], ["etc"], mounts=["/", mount]), ["etc"])
        self.assertFalse((self.root / "etc").exists())

    def test_recursive_delete_refuses_another_device(self):
        (self.root / "etc/sub").mkdir()
        real = os.stat

        def fake(path, *args, **kwargs):
            st = real(path, *args, **kwargs)
            if path == "sub":
                return types.SimpleNamespace(st_dev=st.st_dev + 1, st_mode=st.st_mode)
            return st
        with patch.object(fp.os, "stat", side_effect=fake):
            with self.assertRaises(OSError):
                self.files.delete([], ["etc"], mounts=[])
        self.assertTrue((self.root / "etc/sub").is_dir())

    def test_mountinfo_paths_are_unescaped(self):
        info = self.root / "mountinfo"
        info.write_text("22 1 8:1 / / rw - ext4 /dev/sda1 rw\n"
                        "40 22 8:2 / /mnt/my\\040disk rw - ext4 /dev/sdb1 rw\n")
        self.assertEqual(fp.mount_points(str(info)), ["/", "/mnt/my disk"])


class SystemGateTests(unittest.TestCase):
    """The real handler on a temporary Unix socket, as master-sistem-dosya runs it."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="sistem-gate-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve() / "kok"
        (self.root / "etc").mkdir(parents=True)
        (self.root / "etc/hosts").write_text("127.0.0.1 localhost\n")
        self.sock = str(Path(tmp.name).resolve() / "s.sock")
        args = types.SimpleNamespace(root=str(self.root), sistem=True, domain="ornek.lan", version="t",
                                     allow_host=[], trash="", share="", archive_dir="", downloads_dir="",
                                     protected=[])
        handler = type("H", (fp.SystemHandler,), {"panel": fp.Panel(args)})
        self.server = fp.UnixServer(self.sock, handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def call(self, method, path, body=None, channel="tailscale", client=REMOTE, host="panel.ornek.lan"):
        conn = http.client.HTTPConnection("localhost")
        conn.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.sock.connect(self.sock)
        headers = {"Host": host, "X-Konsol": "1"}
        if channel:
            headers["X-Konsol-Kanal"] = channel
        if client:
            headers["X-Forwarded-For"] = client
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        conn.request(method, path, body=data, headers=headers)
        resp = conn.getresponse()
        raw = resp.read()
        conn.close()
        return resp.status, json.loads(raw) if raw.startswith(b"{") else raw

    def test_only_another_tailscale_device_on_the_tailnet_site(self):
        code, state = self.call("GET", "/api/sistem/state")
        self.assertEqual(code, 200)
        self.assertTrue(state["sistem"])
        self.assertNotIn("readonly", state)
        for kwargs in ({"channel": "internet"}, {"channel": None}, {"client": None},
                       {"client": "127.0.0.1"}, {"client": "203.0.113.9"}, {"host": "baska.ornek"}):
            with self.subTest(**kwargs):
                self.assertEqual(self.call("GET", "/api/sistem/state", **kwargs)[0], 403)

    def test_only_system_routes_exist(self):
        self.assertEqual(self.call("GET", "/api/list?path=")[0], 404)
        self.assertEqual(self.call("GET", "/api/sistem/trash")[0], 404)
        self.assertEqual(self.call("GET", "/api/sistem/archives")[0], 404)
        self.assertEqual(self.call("POST", "/api/sistem/trash", {"path": "", "names": ["etc"]})[0], 404)
        code, listing = self.call("GET", "/api/sistem/list?path=etc")
        self.assertEqual((code, [e["name"] for e in listing["entries"]]), (200, ["hosts"]))

    def test_delete_needs_the_name_or_onayla(self):
        (self.root / "etc/b").write_text("")
        code, err = self.call("POST", "/api/sistem/delete", {"path": "etc", "names": ["hosts"], "confirm": "onayla"})
        self.assertEqual(code, 400)
        code, err = self.call("POST", "/api/sistem/delete", {"path": "etc", "names": ["hosts", "b"], "confirm": "hosts"})
        self.assertEqual(code, 400)
        self.assertTrue((self.root / "etc/hosts").exists())
        code, done = self.call("POST", "/api/sistem/delete", {"path": "etc", "names": ["hosts"], "confirm": "hosts"})
        self.assertEqual((code, done["deleted"]), (200, ["hosts"]))
        code, done = self.call("POST", "/api/sistem/delete", {"path": "", "names": ["etc"], "confirm": "etc"})
        self.assertEqual(code, 200)
        self.assertFalse((self.root / "etc").exists())


class SystemCaddyViewTests(unittest.TestCase):
    """Settings → Web: the system route belongs to the tailnet site only."""

    def test_internet_site_has_no_system_route(self):
        template = (Path(__file__).resolve().parents[1] / "templates" / "Caddyfile").read_text()
        _lines, snippets = resources.panel.split_snippets(template)
        site = "http://panel.ornek.lan, https://genel.ornek.net {\n\timport konsol internet\n}\n"
        routes = resources.panel.parse_caddy(site, "100.64.0.7", "panel", snippets)[0]["routes"]
        self.assertNotIn("/api/sistem/*", [r["path"] for r in routes])
        self.assertIn("/api/*", [r["path"] for r in routes])
        site = "http://panel.ornek.lan {\n\timport konsol tailscale\n}\n"
        routes = resources.panel.parse_caddy(site, "100.64.0.7", "panel", snippets)[0]["routes"]
        self.assertIn(("/api/sistem/*", "unix/__SYSTEM_FILES_SOCKET__"), [(r["path"], r["to"]) for r in routes])


if __name__ == "__main__":
    unittest.main()
