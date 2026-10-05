"""Real HTTP and descriptor isolation tests; portable, no privileged host changes."""
import base64
import fcntl
import copy
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest

import test_share_manager_networks as fixture
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "panel"))
import master_shares as shares
import master_webdav as dav

PASSWORD = "test-only-password-4938"


class SharesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="webdav-test-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        for folder in ("srv/alpha", "srv/beta", "srv/downloads/incomplete", "srv/.pay", "srv/.cop", "run", "profile"):
            (self.base / folder).mkdir(parents=True, exist_ok=True)
        self.root = self.base / "srv"
        (self.root / "alpha/movie.txt").write_bytes(b"abcdefghij")
        (self.root / "beta/private.txt").write_bytes(b"beta-only")
        # DD-203: downloads/incomplete is reserved because the torrent package declares it.
        fixture.torrent_package(self.base / "mods", self.root / "downloads", self.base / "profile")
        self.env = {"SHARE_STATE_FILE": str(self.base / "webdav.json"), "MODULES_FILE": str(self.base / "modules"),
                    "MODULES_DIR": str(self.base / "mods"),
                    "RUNTIME_DIR": str(self.base / "run"), "SERVER_ROOT": str(self.root), "SHARE_DIR": ".pay",
                    "FILES_PANEL_TRASH": ".cop", "DOWNLOADS_PATH": str(self.root / "downloads"),
                    "SETTINGS_PENDING_FILE": str(self.base / "pending"),
                    "TAILSCALE_IPV4": "100.64.0.2", "SHARE_PORT": "61010"}
        self.state = self.base / "state.env"
        self.state.write_text("".join(k + "=" + v + "\n" for k, v in self.env.items()))
        (self.base / "modules").write_text("paylasim\tdurduruldu\n")
        self.manager = shares.Manager(self.state)
        self.mock = patch.object(shares.subprocess, "run", return_value=subprocess.CompletedProcess([], 1))
        self.mock.start()
        self.addCleanup(self.mock.stop)
        self.save("alpha", "reader", "ro")
        self.save("beta", "writer", "rw")
        self.config = self.manager.read()
        self.a, self.b = self.config["items"]
        self.server = dav.Server(("127.0.0.1", 0), self.config)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def save(self, path, user, permission, **kw):
        return self.manager.change("save", dict(path=path, username=user, password=PASSWORD,
                                  connections={"tailscale": {"permission": permission, "ack_write": True, "days": 0}}, **kw))

    def request(self, method, item=None, leaf="", body=None, headers=None, username=None, password=PASSWORD):
        item = item or self.a
        url = "/s/" + item["id"] + "/" + leaf
        head = {"Authorization": "Basic " + base64.b64encode(((username or item["username"]) + ":" + password).encode()).decode()}
        head.update(headers or {})
        conn = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        try:
            conn.request(method, url, body, head)
            resp = conn.getresponse()
            return resp.status, resp.read(), dict(resp.getheaders())
        finally:
            conn.close()

    def test_accounts_isolated_and_no_anonymous_access(self):
        self.assertEqual(self.request("GET", leaf="movie.txt")[1], b"abcdefghij")
        self.assertEqual(self.request("GET", self.b, "private.txt", username="reader")[0], 401)
        self.assertEqual(self.request("GET", leaf="movie.txt", password="wrong")[0], 401)
        self.assertEqual(self.request("GET", leaf="movie.txt", headers={"Authorization": ""})[0], 401)
        self.assertEqual(self.request("GET", leaf="private.txt")[0], 404)

    def test_readonly_all_write_methods_denied(self):
        for method in dav.WRITE_METHODS:
            with self.subTest(method=method):
                self.assertEqual(self.request(method, leaf="movie.txt", body=b"changed")[0], 403)
        self.assertEqual((self.root / "alpha/movie.txt").read_bytes(), b"abcdefghij")

    def test_write_create_overwrite_copy_move_delete(self):
        self.assertEqual(self.request("MKCOL", self.b, "folder")[0], 201)
        self.assertEqual(self.request("PUT", self.b, "folder/new.txt", b"new")[0], 201)
        self.assertEqual(self.request("PUT", self.b, "folder/new.txt", b"updated")[0], 204)
        dest = "/s/" + self.b["id"] + "/folder/copied.txt"
        self.assertEqual(self.request("COPY", self.b, "folder/new.txt", headers={"Destination": dest})[0], 201)
        dest = "/s/" + self.b["id"] + "/renamed.txt"
        self.assertEqual(self.request("MOVE", self.b, "folder/new.txt", headers={"Destination": dest})[0], 201)
        self.assertEqual(self.request("GET", self.b, "renamed.txt")[1], b"updated")
        self.assertEqual(self.request("DELETE", self.b, "folder")[0], 204)

    def test_destination_and_traversal_rejected(self):
        for method in ("COPY", "MOVE"):
            for destination in ("/s/" + self.a["id"] + "/oops", "http://evil.example/s/" + self.b["id"] + "/oops"):
                self.assertEqual(self.request(method, self.b, "private.txt", headers={"Destination": destination})[0], 403)
        for path in ("../beta/private.txt", "%2e%2e/beta/private.txt", "..%2fbeta/private.txt", "x%00", "a//b", ".hidden"):
            self.assertIn(self.request("GET", leaf=path)[0], (400, 403))
        # DD-203: a folder a package reports it writes into (root-relative) is refused and hidden
        # inside the share that contains it; a same-named folder elsewhere is ordinary.
        (self.root / "alpha/incomplete").mkdir()
        (self.root / "alpha/incomplete/x").write_bytes(b"half")
        self.assertEqual(self.request("GET", leaf="incomplete/x")[0], 200)
        self.config["protected"].append("alpha/incomplete")
        self.assertEqual(self.request("GET", leaf="incomplete/x")[0], 403)
        self.assertNotIn(b"incomplete", self.request("PROPFIND", leaf="", headers={"Depth": "1"})[1])

    def test_symlink_hardlink_and_hidden_entries_not_served(self):
        os.symlink(self.root / "beta", self.root / "alpha/link")
        os.link(self.root / "beta/private.txt", self.root / "alpha/hard")
        (self.root / "alpha/.hidden").write_text("private")
        for path in ("link/private.txt", "hard", ".hidden"):
            self.assertEqual(self.request("GET", leaf=path)[0], 403)
        code, data, _ = self.request("PROPFIND", headers={"Depth": "1"})
        self.assertEqual(code, 207)
        self.assertNotIn(b"hard", data)
        self.assertNotIn(b".hidden", data)
        self.assertNotIn(b"link", data)

    def test_range_unicode_zero_byte_and_etag(self):
        code, body, headers = self.request("GET", leaf="movie.txt", headers={"Range": "bytes=2-4"})
        self.assertEqual((code, body), (206, b"cde"))
        self.assertEqual(headers["Content-Range"], "bytes 2-4/10")
        self.assertEqual(self.request("GET", leaf="movie.txt", headers={"Range": "bytes=-3"})[:2], (206, b"hij"))
        self.assertEqual(self.request("GET", leaf="movie.txt", headers={"If-None-Match": headers["ETag"]})[0], 304)
        self.assertEqual(self.request("PUT", self.b, "%C3%A7%C4%B1.txt", b"")[0], 201)
        self.assertEqual(self.request("HEAD", self.b, "%C3%A7%C4%B1.txt")[0], 200)
        self.assertEqual(self.request("PUT", self.b, "private.txt", b"new", {"If-Match": '"wrong"'})[0], 412)

    def test_pause_expiry_password_rotation_without_listing(self):
        policy = self.a["connections"]["tailscale"]
        policy["enabled"] = False
        self.assertEqual(self.request("GET", leaf="movie.txt")[0], 403)
        policy["enabled"] = True
        policy["expires"] = time.time() - 1
        self.assertEqual(self.request("GET", leaf="movie.txt")[0], 403)
        policy["expires"] = None
        self.a["salt"], self.a["hash"] = shares.password_hash("new-test-password")
        self.assertEqual(self.request("GET", leaf="movie.txt")[0], 401)

    def test_replaced_or_renamed_root_fails_closed(self):
        (self.root / "alpha").rename(self.root / "old-alpha")
        (self.root / "alpha").mkdir()
        (self.root / "alpha/movie.txt").write_text("wrong target")
        self.assertEqual(self.request("GET", leaf="movie.txt")[0], 410)
        status = self.manager.public()
        self.assertFalse(status["items"][0]["available"])
        self.manager.change("save", dict(id=self.a["id"], path="old-alpha", username="reader", password=""))
        self.assertEqual(self.manager.read()["items"][0]["id"], self.a["id"])

    def test_interrupted_put_preserves_existing_target(self):
        addr = self.server.server_address
        auth = base64.b64encode(("writer:" + PASSWORD).encode()).decode()
        sock = socket.create_connection(addr)
        sock.sendall(("PUT /s/%s/private.txt HTTP/1.1\r\nHost: localhost\r\nAuthorization: Basic %s\r\nContent-Length: 100\r\n\r\nshort" % (self.b["id"], auth)).encode())
        sock.shutdown(socket.SHUT_WR)
        while sock.recv(4096):
            pass
        sock.close()
        self.assertEqual((self.root / "beta/private.txt").read_bytes(), b"beta-only")
        self.assertFalse(list((self.root / "beta").glob(".webdav-*")))

    def test_registry_no_plaintext_and_safe_public_projection(self):
        raw = Path(self.env["SHARE_STATE_FILE"]).read_text()
        self.assertNotIn(PASSWORD, raw)
        self.assertEqual(Path(self.env["SHARE_STATE_FILE"]).stat().st_mode & 0o777, 0o600)
        public = json.dumps(self.manager.public())
        self.assertNotIn('"hash"', public)
        self.assertNotIn('"salt"', public)
        before = self.manager.read()["items"][0]["hash"]
        self.manager.change("save", dict(id=self.a["id"], path="alpha", username="reader", password=""))
        self.assertEqual(self.manager.read()["items"][0]["hash"], before)

    def test_overlap_reserved_user_and_input_validation(self):
        (self.root / "alpha/sub").mkdir()
        for path in ("", ".cop", ".pay", "downloads", "downloads/incomplete", "alpha/sub", "../elsewhere"):
            with self.subTest(path=path), self.assertRaises((shares.ShareError, OSError)):
                self.save(path, "third", "ro")
        for change in ({"username": "writer"}, {"connections": {"tailscale": {"permission": "rw", "ack_write": False}}},
                       {"password": "short"}, {"connections": {"tailscale": {"days": -1}}}):
            request = dict(id=self.a["id"], path="alpha", username="reader", password="")
            request.update(change)
            with self.assertRaises(shares.ShareError):
                self.manager.change("save", request)

    def test_remove_never_deletes_data_and_stopped_service_stays_stopped(self):
        with patch.object(shares.subprocess, "run", return_value=subprocess.CompletedProcess([], 1)) as run:
            self.manager.change("remove", {"id": self.a["id"]})
        self.assertTrue((self.root / "alpha/movie.txt").exists())
        self.assertEqual(len(self.manager.read()["items"]), 1)
        self.assertFalse(any("restart" in call.args[0] for call in run.call_args_list))

    def test_password_length_boundaries_create_edit_and_blank_preservation(self):
        (self.root / "gamma").mkdir()
        request = dict(path="gamma", username="third", connections={"tailscale": {"permission": "ro", "days": 0}})
        before = Path(self.env["SHARE_STATE_FILE"]).read_bytes()
        for phrase in ("", "x" * 7, "x" * 257, "1234567\n", "1234:678", None):
            with self.subTest(phrase=phrase), self.assertRaises(shares.ShareError):
                self.manager.change("save", dict(request, password=phrase))
        self.assertEqual(before, Path(self.env["SHARE_STATE_FILE"]).read_bytes())
        for phrase in ("Pass8!xy", "ü" * 8, "x" * 11, "x" * 12, "x" * 256):
            self.manager.change("save", dict(request, password=phrase))
            item = self.manager.read()["items"][-1]
            request["id"] = item["id"]
            self.assertTrue(shares.password_ok(item, phrase))
            self.assertNotIn(phrase, Path(self.env["SHARE_STATE_FILE"]).read_text())
        self.manager.change("save", dict(request, password=""))
        self.assertEqual(self.manager.read()["items"][-1]["hash"], item["hash"])

    def test_eight_character_password_authenticates_and_retains_readonly_boundary(self):
        self.manager.change("save", dict(id=self.a["id"], path="alpha", username="reader",
                                        password="Pass8!xy"))
        self.a.update(self.manager.read()["items"][0])
        self.assertEqual(self.request("GET", leaf="movie.txt", password="Pass8!xy")[:2], (200, b"abcdefghij"))
        self.assertEqual(self.request("PROPFIND", password="Pass8!xy", headers={"Depth":"1"})[0], 207)
        self.assertEqual(self.request("GET", leaf="movie.txt")[0], 401)
        self.assertEqual(self.request("PUT", leaf="movie.txt", body=b"deny", password="Pass8!xy")[0], 403)

    def test_pending_settings_and_operation_locks_block_mutations(self):
        before = Path(self.env["SHARE_STATE_FILE"]).read_bytes()
        Path(self.env["SETTINGS_PENDING_FILE"]).touch()
        with self.assertRaises(shares.ShareError):
            self.manager.change("remove", {"id": self.a["id"]})
        Path(self.env["SETTINGS_PENDING_FILE"]).unlink()
        with open(self.base / "run/install.lock", "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            with self.assertRaisesRegex(shares.ShareError, "Başka bir kurulum/ayar işlemi"):
                self.manager.change("save", {"id": self.a["id"], "connections": {"tailscale": {"enabled": False}}})
        self.assertEqual(Path(self.env["SHARE_STATE_FILE"]).read_bytes(), before)

    def test_inline_access_and_duration_preserve_other_fields(self):
        sid = self.a["id"]
        self.manager.change("save", {"id": sid, "connections": {"tailscale": {"enabled": False}}})
        before = self.manager.read()["items"][0]
        for fields in ({"permission": "rw", "ack_write": True}, {"days": 7}, {"days": 0}, {"permission": "ro"}):
            with self.subTest(fields=fields):
                self.manager.change("save", dict(id=sid, connections={"tailscale": fields}))
                item = self.manager.read()["items"][0]
                for key in ("id", "path", "name", "username", "identity", "salt", "hash", "created"):
                    self.assertEqual(item[key], before[key], key)
                self.assertEqual(item["connections"]["wan"], before["connections"]["wan"])
                policy, previous = item["connections"]["tailscale"], before["connections"]["tailscale"]
                self.assertFalse(policy["enabled"])
                if "permission" in fields:
                    self.assertEqual(policy["permission"], fields["permission"])
                    self.assertEqual(policy["expires"], previous["expires"])
                else:
                    self.assertEqual(policy["permission"], previous["permission"])
                    self.assertEqual(policy["expires"], item["changed"] + 7 * 86400 if fields["days"] else None)
                before = item
        self.assertEqual(self.manager.read()["items"][1], self.b)

    def test_inline_validation_and_restart_failure_do_not_change_registry(self):
        before = Path(self.env["SHARE_STATE_FILE"]).read_bytes()
        for fields in ({"permission":"rw"}, {"permission":"rw","ack_write":1}, {"permission":"bad"},
                       {"days":True}, {"days":-1}, {"days":"7"}, {"days":2}):
            with self.subTest(fields=fields), self.assertRaises(shares.ShareError):
                self.manager.change("save", dict(id=self.a["id"], connections={"tailscale": fields}))
        self.assertEqual(Path(self.env["SHARE_STATE_FILE"]).read_bytes(), before)
        (self.base / "modules").write_text("paylasim\tcalisiyor\n")
        with patch.object(self.manager, "restart", side_effect=[shares.ShareError("injected"), None]), self.assertRaises(shares.ShareError):
            self.manager.change("save", {"id": self.a["id"], "connections": {"tailscale": {"days": 1}}})
        self.assertEqual(Path(self.env["SHARE_STATE_FILE"]).read_bytes(), before)

    def test_inline_options_never_rebind_replaced_or_missing_directory(self):
        (self.root / "alpha").rename(self.root / "old-alpha")
        self.manager.change("save", {"id": self.a["id"], "connections": {"tailscale": {"days": 7}}})
        self.assertFalse(self.manager.public()["items"][0]["available"])
        (self.root / "alpha").mkdir()
        (self.root / "alpha/movie.txt").write_text("wrong target")
        self.manager.change("save", {"id": self.a["id"], "connections": {"tailscale": {"permission": "rw", "ack_write": True}}})
        self.a.update(self.manager.read()["items"][0])
        self.assertFalse(self.manager.public()["items"][0]["available"])
        self.assertEqual(self.request("GET", leaf="movie.txt")[0], 410)

    def test_account_edit_preserves_latest_access_expiry_and_paused_state(self):
        sid = self.b["id"]
        self.manager.change("save", {"id": sid, "connections": {"tailscale": {"days": 30}}})
        self.manager.change("save", {"id": sid, "connections": {"tailscale": {"enabled": False}}})
        before = self.manager.read()["items"][1]
        self.manager.change("save", {"id":sid, "path":"beta", "username":"renamed-writer", "password":""})
        after = self.manager.read()["items"][1]
        for key in ("connections", "identity", "salt", "hash"):
            self.assertEqual(after[key], before[key], key)
        self.assertEqual(after["username"], "renamed-writer")

    def test_failed_service_restart_rolls_back_registry(self):
        before = Path(self.env["SHARE_STATE_FILE"]).read_bytes()
        (self.base / "modules").write_text("paylasim\tcalisiyor\n")
        results = [subprocess.CalledProcessError(1, "systemctl"), None]
        with patch.object(self.manager, "restart", side_effect=results), self.assertRaises(shares.ShareError):
            self.manager.change("save", {"id": self.a["id"], "connections": {"tailscale": {"enabled": False}}})
        self.assertEqual(Path(self.env["SHARE_STATE_FILE"]).read_bytes(), before)

    def test_explicit_restarts_reset_the_crash_counter_and_wait_for_http(self):
        self.manager.env["SHARE_PORT"] = str(self.server.server_address[1])
        with patch.object(shares.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run:
            self.manager.restart()
        self.assertEqual([c.args[0][1] for c in run.call_args_list], ["reset-failed", "restart"])

    def test_chunked_upload_and_unsupported_operations_are_explicit(self):
        conn = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        auth = base64.b64encode((self.b["username"] + ":" + PASSWORD).encode()).decode()
        try:
            conn.request("PUT", "/s/" + self.b["id"] + "/chunked.txt", iter([b"one", b"two"]),
                         {"Authorization": "Basic " + auth}, encode_chunked=True)
            response = conn.getresponse()
            self.assertEqual(response.status, 201)
            response.read()
        finally:
            conn.close()
        self.assertEqual(self.request("GET", self.b, "chunked.txt")[1], b"onetwo")
        for method in ("LOCK", "UNLOCK", "PROPPATCH"):
            self.assertEqual(self.request(method, self.b, "chunked.txt")[0], 405)


if __name__ == "__main__":
    unittest.main()
