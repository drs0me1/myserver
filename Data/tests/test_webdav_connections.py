"""Per-connection DAV authorization over real, unprivileged loopback sockets.

The canonical schema-4 fixture intentionally has no global permission, pause,
expiry or networks fields. No existing test fixture or external service is used.
"""
import base64
from concurrent.futures import ThreadPoolExecutor
import contextlib
import copy
import http.client
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "panel"))
import master_shares as shares
import master_webdav as dav


NOW = 2_000_000_000
PASSWORD = "dav-connection-fixture-password"
CONTENT = b"connection-fixture-content"
SCOPES = ("tailscale", "wan")
READ_METHODS = ("OPTIONS", "GET", "HEAD", "PROPFIND")
WRITE_METHODS = ("PUT", "MKCOL", "DELETE", "MOVE", "COPY")
UNSUPPORTED_METHODS = ("LOCK", "UNLOCK", "PROPPATCH", "POST", "TRACE")


def connection(enabled=True, permission="rw", expires=NOW + 600):
    return {"enabled": enabled, "permission": permission, "expires": expires}


class WebDAVConnectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.salt, cls.digest = shares.password_hash(PASSWORD)

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="dav-connections-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.folder = self.root / "alpha"
        self.folder.mkdir()
        (self.folder / "file.txt").write_bytes(CONTENT)
        fd = shares.open_dir(str(self.root), ["alpha"])
        try:
            folder_identity = shares.identity(fd)
        finally:
            os.close(fd)
        self.item = {
            "id": "b" * 24, "path": "alpha", "name": "alpha",
            "username": "fixture-user", "salt": self.salt, "hash": self.digest,
            "identity": folder_identity, "created": NOW - 100, "changed": NOW - 10,
            "connections": {"tailscale": connection(permission="ro"), "wan": connection()},
        }
        self.config = {"schema": 4, "root": str(self.root), "items": [self.item],
                       "limits": dict(shares.DEFAULT_LIMITS),
                       "blocked": [".cop", ".pay"], "protected": ["alpha/incomplete"]}
        self.enterContext(patch.object(socket, "getfqdn", return_value="localhost"))
        self.clock = self.enterContext(patch.object(dav.time, "time", return_value=NOW))
        self.mutation_lock = threading.Lock()
        # Separate ports preserve trusted listener scopes without requiring a
        # privileged 127.0.0.2 alias on macOS.
        self.servers = {scope: self.start_server(scope) for scope in SCOPES}

    def start_server(self, scope):
        server = dav.Server(("127.0.0.1", 0), self.config, scope=scope,
                            mutation_lock=self.mutation_lock)
        thread = threading.Thread(target=server.serve_forever,
                                  kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        self.addCleanup(self.stop_server, server, thread)
        return server

    def stop_server(self, server, thread):
        server.shutdown()
        server.server_close()
        thread.join(3)
        self.assertFalse(thread.is_alive())
        deadline = time.monotonic() + 3
        while server.connections and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertFalse(server.connections, "request did not release its connection slot")
        self.assertFalse(server.limiter.active)
        self.assertFalse(any(entry["pending"] for entry in server.limiter.entries.values()))

    def url(self, leaf="file.txt"):
        return f"/s/{self.item['id']}/{leaf}"

    def request(self, scope, method="GET", leaf="file.txt", auth=True, headers=(), body=None):
        fields = {"X-Share-Client-IP": "198.51.100.11", "Connection": "close"}
        if auth is True:
            auth = "Basic " + base64.b64encode(
                f"{self.item['username']}:{PASSWORD}".encode()).decode()
        if auth is not None:
            fields["Authorization"] = auth
        fields.update(headers)
        conn = http.client.HTTPConnection(*self.servers[scope].server_address, timeout=4)
        try:
            conn.request(method, self.url(leaf), body=body, headers=fields)
            response = conn.getresponse()
            return response.status, response.read(), dict(response.getheaders())
        finally:
            conn.close()

    def method_request(self, scope, method, **kwargs):
        headers = {"Depth": "0", "Destination": self.url("destination.txt")}
        headers.update(kwargs.pop("headers", {}))
        return self.request(scope, method, headers=headers,
                            body=b"updated" if method == "PUT" else None, **kwargs)

    def assert_no_stage(self):
        self.assertFalse(list(self.root.rglob(".webdav-*")), "staged content leaked")

    def test_canonical_fixture_and_server_budgets_remain_unchanged(self):
        self.assertFalse({"permission", "paused", "networks", "expires"}.intersection(self.item))
        self.assertEqual(shares.DEFAULT_LIMITS, {
            "wan_connections": 8, "wan_connections_per_ip": 4,
            "tail_connections": 64, "wan_auth_parallel": 4, "tail_auth_parallel": 2,
            "auth_failures": 5, "auth_window_seconds": 60, "auth_block_seconds": 300,
            "auth_entries": 4096, "share_failures": 100, "share_window_seconds": 3600,
            "share_block_seconds": 3600, "wan_timeout_seconds": 30,
        })
        for scope, server in self.servers.items():
            self.assertEqual(server.scope, scope)
            self.assertEqual(server.limiter.scope, scope)
            self.assertEqual(server.limits, shares.DEFAULT_LIMITS)
        self.assertEqual((dav.MAX_UPLOAD, dav.CHUNK, dav.DISK_RESERVE, dav.DISK_RESERVE_DIVISOR),
                         (64 * 1024 ** 3, 1024 ** 2, 5 * 1024 ** 3, 10))
        self.assertEqual((dav.AUTH_CACHE_SECONDS, dav.AUTH_CACHE_SIZE, dav.TAIL_TIMEOUT_SECONDS),
                         (600, 256, 60))

    def test_each_scope_reads_and_options_advertises_only_its_own_permission(self):
        for rw_scope in SCOPES:
            self.item["connections"] = {
                scope: connection(permission="rw" if scope == rw_scope else "ro") for scope in SCOPES
            }
            for scope in SCOPES:
                for method in READ_METHODS:
                    with self.subTest(rw_scope=rw_scope, scope=scope, method=method):
                        code, body, headers = self.method_request(scope, method)
                        self.assertEqual(code, 207 if method == "PROPFIND" else 200)
                        if method == "GET":
                            self.assertEqual(body, CONTENT)
                        elif method == "HEAD":
                            self.assertEqual(body, b"")
                        elif method == "OPTIONS":
                            allowed = {value.strip() for value in headers["Allow"].split(",")}
                            self.assertEqual(allowed, set(READ_METHODS +
                                                         (WRITE_METHODS if scope == rw_scope else ())))

    def test_ro_blocks_every_write_method_while_other_scope_remains_rw(self):
        for scope in SCOPES:
            self.item["connections"] = {name: connection(permission="ro" if name == scope else "rw")
                                        for name in SCOPES}
            for method in WRITE_METHODS:
                with self.subTest(scope=scope, method=method):
                    self.assertEqual(self.method_request(scope, method)[0], 403)
                    self.assertEqual((self.folder / "file.txt").read_bytes(), CONTENT)
                    self.assertFalse((self.folder / "destination.txt").exists())
                    self.assert_no_stage()

    def test_rw_allows_each_supported_write_on_either_listener(self):
        for scope in SCOPES:
            self.item["connections"] = {name: connection(permission="rw" if name == scope else "ro")
                                        for name in SCOPES}
            with self.subTest(scope=scope):
                self.assertEqual(self.request(scope, "PUT", "new.txt", body=b"created")[0], 201)
                self.assertEqual(self.request(scope, "PUT", "new.txt", body=b"replaced")[0], 204)
                self.assertEqual((self.folder / "new.txt").read_bytes(), b"replaced")
                self.assertEqual(self.request(scope, "COPY", "new.txt",
                                              headers={"Destination": self.url("copy.txt")})[0], 201)
                self.assertEqual((self.folder / "copy.txt").read_bytes(), b"replaced")
                self.assertEqual(self.request(scope, "MOVE", "copy.txt",
                                              headers={"Destination": self.url("moved.txt")})[0], 201)
                self.assertFalse((self.folder / "copy.txt").exists())
                self.assertEqual((self.folder / "moved.txt").read_bytes(), b"replaced")
                self.assertEqual(self.request(scope, "MKCOL", "new-folder")[0], 201)
                for leaf in ("new.txt", "moved.txt", "new-folder"):
                    self.assertEqual(self.request(scope, "DELETE", leaf)[0], 204)
                    self.assertFalse((self.folder / leaf).exists())
                self.assert_no_stage()

    def test_unsupported_methods_remain_405_after_auth_for_ro_and_rw_connections(self):
        for scope in SCOPES:
            for permission in ("ro", "rw"):
                self.item["connections"][scope] = connection(permission=permission)
                for method in UNSUPPORTED_METHODS:
                    with self.subTest(scope=scope, permission=permission, method=method):
                        self.assertEqual(self.method_request(scope, method)[0], 405)

    def test_disabled_scope_denies_all_methods_before_auth_even_with_cached_login(self):
        for scope in SCOPES:
            self.item["connections"] = {name: connection() for name in SCOPES}
            self.assertEqual(self.request(scope)[0], 200)
            self.item["connections"][scope]["enabled"] = False
            for method in READ_METHODS + WRITE_METHODS + UNSUPPORTED_METHODS:
                for auth in (True, None):
                    with self.subTest(scope=scope, method=method, auth=auth):
                        code, _, headers = self.method_request(scope, method, auth=auth)
                        self.assertEqual(code, 403)
                        self.assertNotIn("WWW-Authenticate", headers)
            other = next(name for name in SCOPES if name != scope)
            self.assertEqual(self.request(other)[:2], (200, CONTENT))
            self.assertEqual((self.folder / "file.txt").read_bytes(), CONTENT)

    def test_expiry_is_per_scope_exact_at_boundary_and_checked_after_authentication(self):
        for scope in SCOPES:
            self.item["connections"] = {name: connection() for name in SCOPES}
            self.item["connections"][scope]["expires"] = NOW
            with self.subTest(scope=scope):
                code, _, headers = self.request(scope, auth=None)
                self.assertEqual(code, 401)
                self.assertIn("WWW-Authenticate", headers)
                wrong = "Basic " + base64.b64encode(b"fixture-user:wrong-password").decode()
                self.assertEqual(self.request(scope, auth=wrong)[0], 401)
                for method in READ_METHODS + WRITE_METHODS + UNSUPPORTED_METHODS:
                    with self.subTest(method=method):
                        self.assertEqual(self.method_request(scope, method)[0], 403)
                other = next(name for name in SCOPES if name != scope)
                self.assertEqual(self.request(other)[:2], (200, CONTENT))
                self.item["connections"][scope]["expires"] = NOW + 1
                self.assertEqual(self.request(scope)[0], 200)
                self.item["connections"][scope]["expires"] = None
                self.clock.return_value = NOW + 10_000
                self.assertEqual(self.request(scope)[0], 200)
                self.clock.return_value = NOW

    def test_cached_authentication_never_caches_connection_permission_pause_or_expiry(self):
        self.item["connections"] = {scope: connection() for scope in SCOPES}
        with patch.object(dav, "password_ok", wraps=dav.password_ok) as verify:
            for scope in SCOPES:
                self.assertEqual(self.request(scope)[0], 200)
            self.assertEqual(verify.call_count, 2)
            for scope in SCOPES:
                policy = self.item["connections"][scope]
                with self.subTest(scope=scope):
                    policy["permission"] = "ro"
                    self.assertEqual(self.request(scope, "PUT", body=b"forbidden")[0], 403)
                    self.assertEqual(self.request(scope)[0], 200)
                    policy["enabled"] = False
                    self.assertEqual(self.request(scope)[0], 403)
                    policy["enabled"] = True
                    policy["expires"] = NOW
                    self.assertEqual(self.request(scope)[0], 403)
                    policy["expires"] = None
                    self.assertEqual(self.request(scope)[0], 200)
            self.assertEqual(verify.call_count, 2)

    def test_scope_headers_cannot_borrow_other_connection_access_or_write_permission(self):
        for scope in SCOPES:
            other = next(name for name in SCOPES if name != scope)
            forged = {"X-Share-Scope": other, "X-Share-Network": other,
                      "X-Forwarded-For": "100.64.0.9", "X-Forwarded-Host": "paylas.local",
                      "X-Forwarded-Proto": "https", "Forwarded": "for=100.64.0.9;proto=https"}
            self.item["connections"] = {name: connection() for name in SCOPES}
            self.item["connections"][scope]["enabled"] = False
            with self.subTest(scope=scope):
                self.assertEqual(self.request(scope, headers=forged)[0], 403)
                self.item["connections"][scope].update(enabled=True, permission="ro")
                self.assertEqual(self.request(scope, "PUT", headers=forged, body=b"forbidden")[0], 403)
                self.assertEqual(self.request(scope, headers=forged)[0], 200)
                self.assertEqual((self.folder / "file.txt").read_bytes(), CONTENT)

    def test_both_disabled_retains_credentials_and_resuming_one_scope_restores_only_it(self):
        credentials = {key: self.item[key] for key in ("id", "username", "salt", "hash", "identity")}
        for scope in SCOPES:
            self.item["connections"][scope]["enabled"] = False
            self.assertEqual(self.request(scope)[0], 403)
        self.item["connections"]["wan"]["enabled"] = True
        self.assertEqual(self.request("wan")[:2], (200, CONTENT))
        self.assertEqual(self.request("tailscale")[0], 403)
        self.assertEqual(credentials, {key: self.item[key] for key in credentials})

    def test_live_get_chunks_stop_on_selected_scope_expiry_or_disable(self):
        original = dav.Handler.live
        for scope in SCOPES:
            for change in ({"expires": NOW}, {"enabled": False}):
                self.item["connections"] = {name: connection() for name in SCOPES}
                calls = []

                def live(handler):
                    if handler.server is self.servers[scope] and handler.command == "GET" and handler.response_started:
                        calls.append(True)
                        if len(calls) == 2:
                            self.item["connections"][scope].update(change)
                    return original(handler)

                with self.subTest(scope=scope, change=change), \
                        patch.object(dav, "CHUNK", 4), patch.object(dav.Handler, "live", live):
                    with self.assertRaises(http.client.IncompleteRead) as error:
                        self.request(scope)
                    self.assertEqual(error.exception.partial, CONTENT[:4])
                    self.assertEqual(len(calls), 2)

    def test_other_scope_expiring_during_get_does_not_cut_current_transfer(self):
        original = dav.Handler.live
        for scope in SCOPES:
            self.item["connections"] = {name: connection() for name in SCOPES}
            other = next(name for name in SCOPES if name != scope)
            calls = []

            def live(handler):
                if handler.server is self.servers[scope] and handler.response_started:
                    calls.append(True)
                    self.item["connections"][other]["expires"] = NOW
                return original(handler)

            with self.subTest(scope=scope), patch.object(dav, "CHUNK", 4), \
                    patch.object(dav.Handler, "live", live):
                self.assertEqual(self.request(scope)[:2], (200, CONTENT))
                self.assertGreater(len(calls), 1)

    def test_live_upload_and_copy_chunks_recheck_selected_policy_and_remove_stage(self):
        original = dav.Handler.staged_file
        for scope in SCOPES:
            for method in ("PUT", "COPY"):
                for change in ({"expires": NOW}, {"enabled": False}, {"permission": "ro"}):
                    self.item["connections"] = {name: connection() for name in SCOPES}
                    seen = []

                    @contextlib.contextmanager
                    def staging(handler, parent, chunks, size=0):
                        def changing_chunks():
                            for chunk in chunks:
                                seen.append(True)
                                if len(seen) == 2:
                                    self.item["connections"][scope].update(change)
                                yield chunk
                        with original(handler, parent, changing_chunks(), size) as temp:
                            yield temp

                    with self.subTest(scope=scope, method=method, change=change), \
                            patch.object(dav, "CHUNK", 4), patch.object(dav.Handler, "staged_file", staging):
                        self.assertEqual(self.method_request(scope, method)[0], 403)
                        self.assertEqual(len(seen), 2)
                        self.assertEqual((self.folder / "file.txt").read_bytes(), CONTENT)
                        self.assertFalse((self.folder / "destination.txt").exists())
                        self.assert_no_stage()

    def staged_race(self, scope, method, intervene, overwrite=False):
        """Pause after fsync but before publish; the request still uses real HTTP."""
        entered, release = threading.Event(), threading.Event()
        original = dav.Handler.staged_file
        leaf = "file.txt" if method == "COPY" or overwrite else "new.txt"
        destination = "existing.txt" if overwrite else "new.txt"
        if method == "COPY" and overwrite:
            (self.folder / destination).write_bytes(b"previous-target")

        @contextlib.contextmanager
        def staging(handler, parent, chunks, size=0):
            with original(handler, parent, chunks, size) as temp:
                if handler.server is self.servers[scope]:
                    entered.set()
                    if not release.wait(3):
                        raise RuntimeError("staged request was not released")
                yield temp

        with patch.object(dav.Handler, "staged_file", staging), ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.request, scope, method, leaf,
                                 headers={"Destination": self.url(destination)},
                                 body=b"staged-content" if method == "PUT" else None)
            try:
                self.assertTrue(entered.wait(3), "request did not finish staging")
                self.assertTrue(list(self.folder.glob(".webdav-*")))
                intervene()
            finally:
                release.set()
            result = future.result(timeout=4)
        self.assert_no_stage()
        self.assertEqual((self.folder / "file.txt").read_bytes(), CONTENT)
        if method == "COPY" and overwrite:
            self.assertEqual((self.folder / destination).read_bytes(), b"previous-target")
        else:
            self.assertFalse((self.folder / "new.txt").exists())
        return result[0]

    def test_staged_put_and_copy_expiry_at_commit_preserves_absent_and_existing_targets(self):
        for scope in SCOPES:
            for method in ("PUT", "COPY"):
                for overwrite in (False, True):
                    self.clock.return_value = NOW
                    self.item["connections"] = {name: connection(expires=NOW + 100) for name in SCOPES}
                    self.item["connections"][scope]["expires"] = NOW + 10
                    before = copy.deepcopy(self.item)

                    def expire():
                        # No registry mutation: a snapshot comparison alone must
                        # not mask a missing final wall-clock expiry check.
                        self.clock.return_value = NOW + 10

                    with self.subTest(scope=scope, method=method, overwrite=overwrite):
                        self.assertEqual(self.staged_race(scope, method, expire, overwrite), 403)
                        self.assertEqual(self.item, before)
                        other = next(name for name in SCOPES if name != scope)
                        self.assertEqual(self.request(other)[:2], (200, CONTENT))

    def test_staged_put_and_copy_revalidate_disable_and_permission_before_publish(self):
        for scope in SCOPES:
            for method in ("PUT", "COPY"):
                for change in ({"enabled": False}, {"permission": "ro"}):
                    self.item["connections"] = {name: connection() for name in SCOPES}
                    with self.subTest(scope=scope, method=method, change=change):
                        self.assertEqual(self.staged_race(
                            scope, method, lambda: self.item["connections"][scope].update(change)), 403)


if __name__ == "__main__":
    unittest.main()
