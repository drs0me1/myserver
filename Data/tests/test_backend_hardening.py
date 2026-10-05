"""Burst admission and untrusted filesystem regressions; disposable local fixtures only."""
import contextlib
import http.server
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest

DATA = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(DATA / "panel"), str(DATA / "files-panel")]
import master_shares as shares
import test_share_manager_networks as fixture
import master_webdav as dav


def load_script(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


panel = load_script("hardened_panel", DATA / "panel/master-panel")
files = load_script("hardened_files", DATA / "files-panel/master-files-panel")
# DD-202: the qBittorrent profile's root reader is the package worker's; the share path check is the base's.
ayar = load_script("torrent_ayar", DATA / "magaza/torrent/ayar.py")


class ConfigReadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        (self.root / "profile/qBittorrent").mkdir(parents=True)
        (self.root / "srv/media").mkdir(parents=True)
        self.conf = self.root / "profile/qBittorrent/qBittorrent.conf"
        # DD-203: the share path check asks the torrent package's folder module (klasorler.py).
        fixture.torrent_package(self.root / "mods", self.root / "srv/downloads", self.root / "profile")
        self.manager = object.__new__(shares.Manager)
        self.manager.env = {"MODULES_DIR": str(self.root / "mods"), "SERVER_ROOT": str(self.root / "srv")}
        self.data = {"root": str(self.root / "srv"), "blocked": [], "items": []}

    def assert_rejected(self):
        self.assertIsNone(ayar.read_conf(self.conf))
        with self.assertRaisesRegex(shares.ShareError, "güvenli okunamadı"):
            self.manager.validate_path(self.data, "media")

    def test_normal_and_missing_config_keep_user_paths_and_hide_other_keys(self):
        self.assertIsNone(ayar.read_conf(self.conf))
        self.assertEqual(self.manager.validate_path(self.data, "media")[0], "media")
        self.conf.write_text("[BitTorrent]\nSession\\TempPath=" + str(self.root / "srv/media")
                             + "\nWebUI\\Password_PBKDF2=fixture-secret\n")
        # The package worker's view carries paths only, never the hash the file also holds.
        view = ayar.durum({"TORRENT_PROFILE_DIR": str(self.root / "profile"), "DOWNLOADS_PATH": str(self.root / "srv")})
        self.assertEqual((view["temp"], view["temp_inside"]), (str(self.root / "srv/media"), True))
        self.assertNotIn("fixture-secret", json.dumps(view))
        with self.assertRaisesRegex(shares.ShareError, "çakışıyor"):
            self.manager.validate_path(self.data, "media")

    def test_final_symlink_and_symlinked_parent_are_rejected(self):
        target = self.root / "outside.conf"
        target.write_text("Session\\TempPath=/private\n")
        self.conf.symlink_to(target)
        self.assert_rejected()
        self.conf.unlink()
        folder = self.conf.parent
        folder.rmdir()
        outside = self.root / "outside"
        outside.mkdir()
        (outside / self.conf.name).write_text(target.read_text())
        folder.symlink_to(outside, target_is_directory=True)
        self.assert_rejected()

    def test_directory_and_oversized_config_are_rejected(self):
        self.conf.mkdir()
        self.assert_rejected()
        self.conf.rmdir()
        with self.conf.open("wb") as stream:
            stream.truncate(1024 * 1024 + 1)
        self.assert_rejected()

    def test_fifo_is_rejected_without_waiting_for_a_writer(self):
        os.mkfifo(self.conf)
        # A regression must fail with a deadline, never hang the test runner.
        code = """
import importlib.machinery, importlib.util, json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import master_shares as shares
loader = importlib.machinery.SourceFileLoader('fifo_ayar', sys.argv[4])
spec = importlib.util.spec_from_loader(loader.name, loader)
p = importlib.util.module_from_spec(spec); loader.exec_module(p)
assert p.read_conf(sys.argv[2]) is None
m = object.__new__(shares.Manager)
m.env = json.loads(sys.argv[5])
try:
    m.validate_path(json.loads(sys.argv[3]), 'media')
except shares.ShareError:
    pass
else:
    raise AssertionError('FIFO accepted')
"""
        result = subprocess.run([sys.executable, "-c", code, str(DATA / "panel"),
                                 str(self.conf), json.dumps(self.data), str(DATA / "magaza/torrent/ayar.py"),
                                 json.dumps(self.manager.env)],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)


class ReservedNamesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in (".cop", ".pay", ".arsiv", "dest"):
            (self.root / name).mkdir()
            (self.root / name / "marker").write_text(name)
        (self.root / "ordinary").write_text("keep")
        self.files = files.Files(str(self.root), ".cop", ".pay", ".arsiv")

    def test_reserved_sources_reject_rename_move_and_trash_before_any_mutation(self):
        for name in (".cop", ".pay", ".arsiv"):
            actions = [lambda: self.files.rename([], name, "renamed"),
                       lambda: self.files.move([], ["ordinary", name], ["dest"]),
                       lambda: self.files.to_trash([], ["ordinary", name])]
            for action in actions:
                with self.subTest(name=name, action=action), self.assertRaises(files.PanelError) as err:
                    action()
                self.assertEqual(err.exception.code, 403)
                self.assertEqual((self.root / name / "marker").read_text(), name)
                self.assertEqual((self.root / "ordinary").read_text(), "keep")
                self.assertFalse((self.root / "dest/ordinary").exists())
                self.assertEqual(sorted(p.name for p in (self.root / ".cop").iterdir()), ["marker"])

    def test_moving_nested_reserved_name_cannot_create_a_root_system_area(self):
        for name in (".cop", ".pay", ".arsiv"):
            source = self.root / "dest" / name
            source.mkdir()
            with self.subTest(name=name), self.assertRaises(files.PanelError) as error:
                self.files.move(["dest"], [name], [])
            self.assertIn("kök klasöre", str(error.exception))
            self.assertTrue(source.is_dir())

    def test_ordinary_rename_move_trash_and_restore_still_work(self):
        self.files.rename([], "ordinary", "renamed")
        self.files.move([], ["renamed"], ["dest"])
        tokens = self.files.to_trash(["dest"], ["renamed"])
        self.files.restore(tokens)
        self.assertEqual((self.root / "dest/renamed").read_text(), "keep")

    def test_restore_never_publishes_a_reserved_root_name(self):
        for name in (".pay", ".arsiv"):
            # A historical/manually edited trash entry must choose a harmless new name.
            token = "1700000000000-" + ("a" if name == ".pay" else "b") * 8
            target = self.root / ".cop" / token
            target.mkdir()
            (target / name).write_text("saved")
            (self.root / ".cop" / (token + ".json")).write_text(json.dumps({"from": ""}))
            result = self.files.restore([token])[0]
            self.assertNotEqual(result["name"], name)
            self.assertEqual((self.root / result["name"]).read_text(), "saved")
            self.assertEqual((self.root / name / "marker").read_text(), name)


class ListenQueueTests(unittest.TestCase):
    def test_all_backends_accept_a_burst_before_the_accept_loop_runs(self):
        # No requests/threads are processed: this isolates the actual kernel listen queue.
        with tempfile.TemporaryDirectory(prefix="queue-", dir="/tmp") as root:
            constructors = [lambda: panel.Server(root + "/api.sock"),
                            lambda: files.Server(("127.0.0.1", 0), http.server.BaseHTTPRequestHandler),
                            lambda: dav.Server(("127.0.0.1", 0), {"items": []})]
            for construct in constructors:
                with contextlib.ExitStack() as cleanup:
                    server = construct()
                    cleanup.callback(server.server_close)
                    for _ in range(24):
                        client = socket.socket(server.address_family, socket.SOCK_STREAM)
                        cleanup.callback(client.close)
                        client.settimeout(.5)
                        client.connect(server.server_address)


if __name__ == "__main__":
    unittest.main()
