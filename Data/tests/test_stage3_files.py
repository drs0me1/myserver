"""Stage 3 Files JSON and idle cleanup; no system service or host mutations."""
import http.client
import os
from pathlib import Path
import socket
import tempfile
import threading
import time
import types
import unittest

import test_files_upload as fixture

fp = fixture.fp


class Stage3FilesTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="stage3-files-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        args = types.SimpleNamespace(root=str(self.root), trash=".cop", share=".pay",
                                     archive_dir="", domain="", version="test", temp_dir="",
                                     allow_host=[])
        self.handler = type("FixtureHandler", (fp.Handler,), {"panel": fp.Panel(args), "timeout": .2})
        self.server = fp.Server(("127.0.0.1", 0), self.handler)
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={"poll_interval": .01}, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def request(self, method="GET", path="/api/list", body=None):
        conn = http.client.HTTPConnection(*self.server.server_address, timeout=2)
        try:
            conn.request(method, path, body=body,
                         headers={"X-Konsol": "1", "Content-Type": "application/json"})
            response = conn.getresponse()
            return response.status, response.read(), response.will_close
        finally:
            conn.close()

    def test_deep_json_returns_400_and_closes_then_next_request_succeeds(self):
        body = b'{"path":' + b"[" * 20000 + b"0" + b"]" * 20000 + b"}"
        code, data, _ = self.request("POST", "/api/mkdir", body)
        self.assertEqual(code, 400)
        self.assertIn(b"JSON", data)
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertEqual(self.request()[0], 200)

    def test_recursive_trash_metadata_is_ignored(self):
        target = self.root / "meta.json"
        target.write_bytes(b'{"from":' + b"[" * 20000 + b"0" + b"]" * 20000 + b"}")
        with fp.DirFd(os.open(self.root, fp.O_DIR)) as fd:
            self.assertIsNone(fp.read_json_at(fd, target.name))
            target.write_text('{"from":"downloads"}')
            self.assertEqual(fp.read_json_at(fd, target.name), {"from": "downloads"})

    def test_idle_and_incomplete_headers_close_without_blocking_healthy_request(self):
        for partial in (b"", b"GET /api/list HTTP/1.1\r\n"):
            with socket.create_connection(self.server.server_address, timeout=2) as idle:
                if partial:
                    idle.sendall(partial)
                self.assertEqual(self.request()[0], 200)
                self.assertEqual(idle.recv(1024), b"")

    def test_stalled_upload_removes_stage_and_active_upload_can_outlive_idle_timeout(self):
        def headers(name):
            return ("POST /api/upload?name=%s HTTP/1.1\r\nHost: 127.0.0.1:%s\r\n"
                    "X-Konsol: 1\r\nContent-Length: 4\r\n\r\n" %
                    (name, self.server.server_address[1])).encode()

        with socket.create_connection(self.server.server_address, timeout=2) as idle:
            idle.sendall(headers("stalled.bin") + b"x")
            response = http.client.HTTPResponse(idle)
            response.begin()
            self.assertEqual(response.status, 400)
            response.read()
        self.assertFalse((self.root / "stalled.bin").exists())
        self.assertFalse(list(self.root.glob(".yukleniyor-*")))
        with socket.create_connection(self.server.server_address, timeout=2) as active:
            active.sendall(headers("active.bin"))
            for byte in (b"a", b"b", b"c", b"d"):
                time.sleep(.08)
                active.sendall(byte)
            response = http.client.HTTPResponse(active)
            response.begin()
            self.assertEqual(response.status, 201)
            response.read()
        self.assertEqual((self.root / "active.bin").read_bytes(), b"abcd")


if __name__ == "__main__":
    unittest.main()
