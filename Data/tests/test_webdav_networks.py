"""Portable ingress/budget tests; only temporary files and unprivileged loopback."""
import base64
from concurrent.futures import ThreadPoolExecutor
import contextlib
import copy
import errno
import http.client
import io
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "panel"))
import master_shares as shares
import master_webdav as dav

PASSWORD = "network-fixture-password"


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class LimiterTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.limiter = dav.Limiter(dict(shares.DEFAULT_LIMITS), self.clock)

    def bad(self, ip="198.51.100.1"):
        with self.assertRaises(dav.DavError) as caught:
            with self.limiter.credentials(ip):
                raise dav.DavError(401)
        return caught.exception

    def test_defaults_match_runtime_contract(self):
        self.assertEqual(shares.DEFAULT_LIMITS, {
            "wan_connections": 8, "wan_connections_per_ip": 4,
            "tail_connections": 64, "wan_auth_parallel": 4, "tail_auth_parallel": 2,
            "auth_failures": 5, "auth_window_seconds": 60,
            "auth_block_seconds": 300, "auth_entries": 4096,
            "share_failures": 100, "share_window_seconds": 3600,
            "share_block_seconds": 3600,
            "wan_timeout_seconds": 30,
        })

    def test_fifth_failure_blocks_for_fixed_ttl_and_does_not_slide(self):
        for _ in range(4):
            self.assertEqual(self.bad().code, 401)
        blocked = self.bad()
        self.assertEqual((blocked.code, blocked.retry_after), (429, 300))
        self.clock.advance(0.1)
        self.assertEqual(self.bad().retry_after, 300)
        self.clock.advance(298.9)
        self.assertEqual(self.bad().retry_after, 1)
        self.clock.advance(1)
        self.assertEqual(self.bad().code, 401)
        self.assertEqual(len(self.limiter.entries["198.51.100.1"]["failures"]), 1)

    def test_window_is_sliding_and_exact_boundary_expires(self):
        self.bad()
        self.clock.advance(59)
        for _ in range(3):
            self.bad()
        self.clock.advance(1)
        self.assertEqual(self.bad().code, 401)
        self.assertEqual(self.bad().code, 429)

    def test_success_does_not_erase_bad_attempts_or_create_account_lock(self):
        for _ in range(4):
            self.bad()
        with self.limiter.credentials("198.51.100.1"):
            pass
        self.assertEqual(self.bad().code, 429)
        with self.limiter.credentials("198.51.100.2"):
            pass
        self.assertNotIn("198.51.100.2", self.limiter.entries)

    def test_bounded_table_rejects_new_ips_without_evicting_blocks(self):
        self.limiter.limits["auth_entries"] = 2
        for ip in ("198.51.100.1", "198.51.100.2"):
            for _ in range(5):
                self.bad(ip)
        original = copy.deepcopy(self.limiter.entries)
        self.assertEqual(self.bad("198.51.100.3").code, 503)
        self.assertEqual(self.limiter.entries, original)
        self.clock.advance(300)
        self.assertEqual(self.bad("198.51.100.3").code, 401)
        self.assertEqual(list(self.limiter.entries), ["198.51.100.3"])

    def test_expired_failures_are_pruned_but_pending_attempts_reserve_space(self):
        self.limiter.limits["auth_entries"] = 1
        with self.limiter.credentials("198.51.100.1"):
            self.clock.advance(61)
            self.assertEqual(self.bad("198.51.100.2").code, 503)
        self.assertFalse(self.limiter.entries)
        self.bad()
        self.clock.advance(60)
        self.assertEqual(self.bad("198.51.100.2").code, 401)
        self.assertNotIn("198.51.100.1", self.limiter.entries)

    def test_attempt_already_running_cannot_extend_a_block(self):
        with self.assertRaises(dav.DavError) as caught:
            with self.limiter.credentials("198.51.100.1"):
                for _ in range(5):
                    self.bad()
                self.clock.advance(100)
                raise dav.DavError(401)
        self.assertEqual(caught.exception.retry_after, 200)
        self.assertEqual(self.limiter.entries["198.51.100.1"]["pending"], 0)

    def test_request_and_hash_slots_release_after_exceptions(self):
        with self.assertRaises(RuntimeError):
            with self.limiter.request("198.51.100.1"):
                raise RuntimeError("fixture")
        self.assertFalse(self.limiter.active)
        with self.assertRaises(ValueError):
            with self.limiter.hashing() as admitted:
                self.assertTrue(admitted)
                raise ValueError("fixture")
        with contextlib.ExitStack() as stack:
            for _ in range(self.limiter.limits["wan_auth_parallel"]):
                self.assertTrue(self.limiter.auth_slots.acquire(False))
                stack.callback(self.limiter.auth_slots.release)
            self.assertFalse(self.limiter.auth_slots.acquire(False))

    def test_concurrent_failures_are_atomic_and_do_not_overflow_the_table(self):
        self.limiter.limits["auth_entries"] = 1
        self.bad()
        barrier = threading.Barrier(4)

        def attempt():
            try:
                with self.limiter.credentials("198.51.100.1"):
                    barrier.wait(timeout=3)
                    raise dav.DavError(401)
            except dav.DavError as err:
                return err.code

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(attempt) for _ in range(4)]
            self.assertEqual(sorted(f.result() for f in futures), [401, 401, 401, 429])
        self.assertEqual(len(self.limiter.entries), 1)
        self.assertEqual(self.limiter.entries["198.51.100.1"]["pending"], 0)
        self.assertEqual(self.bad("198.51.100.2").code, 503)


class NetworkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.salt, cls.digest = shares.password_hash(PASSWORD)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="webdav-networks-")
        self.addCleanup(self.tmp.cleanup)
        fqdn = patch.object(socket, "getfqdn", return_value="localhost")
        fqdn.start()
        self.addCleanup(fqdn.stop)
        self.root = Path(self.tmp.name)
        self.config = {"schema": 4, "root": str(self.root), "items": [],
                       "limits": dict(shares.DEFAULT_LIMITS),
                       # DD-203: root-relative folders packages write into; hidden and unreachable in shares.
                       "protected": ["1/incomplete", "2/incomplete", "3/incomplete"]}
        for index, networks in enumerate((["tailscale"], ["wan"], ["tailscale", "wan"]), 1):
            folder = self.root / str(index)
            folder.mkdir()
            (folder / "file.txt").write_bytes(b"fixture-content")
            fd = shares.open_dir(str(folder), [])
            try:
                folder_identity = shares.identity(fd)
            finally:
                os.close(fd)
            self.config["items"].append({
                "id": "%024x" % index, "path": str(index), "name": str(index),
                "username": "fixture-user", "salt": self.salt, "hash": self.digest,
                "identity": folder_identity, "created": int(time.time()), "changed": int(time.time()),
                "connections": {scope: {"enabled": scope in networks, "permission": "rw", "expires": None}
                                for scope in ("tailscale", "wan")},
            })
        self.tail_item, self.wan_item, self.both_item = self.config["items"]
        self.mutation_lock = threading.Lock()
        self.tail = self.start_server()
        # macOS does not route 127.0.0.2 without an admin-created lo0 alias.
        # Exercise the identical trusted scope using a second 127.0.0.1 port.
        self.wan = self.start_server("wan")

    def start_server(self, scope="tailscale", config=None, host="127.0.0.1", port=0):
        server = dav.Server((host, port), config or self.config, scope=scope,
                            mutation_lock=self.mutation_lock)
        thread = threading.Thread(target=server.serve_forever,
                                  kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        self.addCleanup(self.stop_server, server, thread)
        return server

    def stop_server(self, server, thread):
        server.shutdown()
        server.server_close()
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.wait_for(lambda: not server.connections)
        self.assertFalse(server.limiter.active)
        self.assertFalse(any(e["pending"] for e in server.limiter.entries.values()))

    def wait_for(self, predicate):
        deadline = time.monotonic() + 3
        while not predicate() and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertTrue(predicate(), "background request did not reach/release its budget")

    def request(self, server=None, item=None, method="GET", leaf="file.txt", ip="198.51.100.1",
                auth=True, headers=(), body=None, path=None):
        server = server or self.wan
        item = item or self.wan_item
        fields = []
        if auth is True:
            auth = "Basic " + base64.b64encode((item["username"] + ":" + PASSWORD).encode()).decode()
        if auth is not None:
            fields.append(("Authorization", auth))
        if ip is not None:
            fields.append(("X-Share-Client-IP", ip))
        fields.extend(headers)
        conn = http.client.HTTPConnection(*server.server_address, timeout=4)
        try:
            conn.putrequest(method, path or "/s/" + item["id"] + "/" + leaf)
            for key, value in fields:
                conn.putheader(key, value)
            if body is not None:
                conn.putheader("Content-Length", str(len(body)))
            conn.endheaders(body)
            resp = conn.getresponse()
            return resp.status, resp.read(), dict(resp.getheaders())
        finally:
            conn.close()

    def test_scopes_allow_selected_networks_and_default_is_tailscale(self):
        for server, item in ((self.tail, self.tail_item), (self.wan, self.wan_item),
                             (self.tail, self.both_item), (self.wan, self.both_item)):
            self.assertEqual(self.request(server, item)[:2], (200, b"fixture-content"))
        with dav.Server(("127.0.0.1", 0), self.config) as server:
            self.assertEqual(server.scope, "tailscale")
            self.assertEqual(server.limiter.scope, "tailscale")

    def test_same_port_on_two_loopback_addresses(self):
        try:
            wan = self.start_server("wan", host="127.0.0.2", port=self.tail.server_address[1])
        except OSError as err:
            if err.errno == errno.EADDRNOTAVAIL:
                self.skipTest("host has no 127.0.0.2 loopback alias; run on supported Linux")
            raise
        self.assertEqual(wan.server_address[1], self.tail.server_address[1])
        self.assertEqual(self.request(wan)[0], 200)
        self.assertEqual(self.request(wan, self.tail_item)[0], 403)
        self.assertEqual(self.request(self.tail, self.wan_item)[0], 403)
        self.assertEqual(self.request(self.tail, self.tail_item)[0], 200)

    def test_cross_network_all_methods_denied_before_hash_and_filesystem(self):
        methods = dav.READ_METHODS + dav.WRITE_METHODS + ("LOCK", "PROPPATCH", "TRACE", "UNKNOWN")
        with patch.object(dav, "password_ok") as verify, patch.object(dav, "open_dir") as open_dir:
            for server, item in ((self.tail, self.wan_item), (self.wan, self.tail_item)):
                for method in methods:
                    with self.subTest(scope=server.scope, method=method):
                        result = self.request(server, item, method=method,
                                              headers=(("Expect", "100-continue"),))
                        self.assertEqual(result[0], 403)
            verify.assert_not_called()
            open_dir.assert_not_called()

    def test_invalid_or_absent_connections_fail_closed(self):
        missing = object()
        invalid = (missing, None, [], "wan", ["wan"], {"wan": True}, {},
                   {"tailscale": {}, "wan": {}},
                   {scope: {"enabled": 1, "permission": "rw", "expires": None} for scope in ("tailscale", "wan")})
        for connections in invalid:
            config = copy.deepcopy(self.config)
            if connections is missing:
                config["items"][2].pop("connections")
            else:
                config["items"][2]["connections"] = connections
            with self.subTest(connections=connections), self.assertRaises(shares.ShareError):
                shares.normalize_registry(config)
        # The request boundary also denies an absent policy before authentication or IO.
        with patch.object(dav, "password_ok") as verify, patch.object(dav, "open_dir") as open_dir:
            for connections in (missing, {}):
                if connections is missing:
                    self.both_item.pop("connections")
                else:
                    self.both_item["connections"] = connections
                for server in (self.tail, self.wan):
                    with self.subTest(connections=connections, scope=server.scope):
                        self.assertEqual(self.request(server, self.both_item, method="OPTIONS")[0], 403)
            verify.assert_not_called()
            open_dir.assert_not_called()

    def test_forged_scope_headers_and_forwarded_addresses_do_not_switch_listener(self):
        headers = (("X-Share-Scope", "tailscale"), ("X-Share-Network", "tailscale"),
                   ("X-Forwarded-For", "100.64.0.2"), ("Forwarded", "for=100.64.0.2"),
                   ("Host", "paylas.tailnet"))
        self.assertEqual(self.request(item=self.tail_item, headers=headers)[0], 403)
        self.assertEqual(self.request(self.tail, self.wan_item, headers=(("X-Share-Scope", "wan"),))[0], 403)

    def test_wan_rejects_missing_duplicate_list_or_malformed_client_ip(self):
        bad_ips = (None, "", "not-an-ip", "198.51.100.1, 198.51.100.2", "198.51.100.1:80",
                   "[2001:db8::1]", "fe80::1%lo0", "198.51.100.1 ", "010.0.0.1")
        with patch.object(dav, "password_ok") as verify:
            for ip in bad_ips:
                with self.subTest(ip=ip):
                    self.assertEqual(self.request(ip=ip)[0], 400)
            self.assertEqual(self.request(headers=(("X-Share-Client-IP", "198.51.100.2"),))[0], 400)
            self.assertEqual(self.request(ip=None, headers=(("X-Forwarded-For", "198.51.100.2"),))[0], 400)
            verify.assert_not_called()
        self.assertEqual(self.request(self.tail, self.tail_item, ip=None)[0], 200)
        self.assertEqual(self.request(ip="2001:db8::1")[0], 200)

    def test_missing_auth_is_challenge_without_failure_but_supplied_bad_auth_blocks(self):
        for _ in range(7):
            status, _, headers = self.request(auth=None)
            self.assertEqual(status, 401)
            self.assertIn("WWW-Authenticate", headers)
        self.assertFalse(self.wan.limiter.entries)
        for value in ("", "Bearer token", "Basic !!!!", "Basic dXNlcg=="):
            self.assertEqual(self.request(auth=value)[0], 401)
        status, _, headers = self.request(auth="Basic !!!!")
        self.assertEqual((status, headers["Retry-After"]), (429, "300"))
        self.assertEqual(self.request()[0], 429)
        self.assertEqual(self.request(auth=None)[0], 429)
        self.assertEqual(self.request(ip="198.51.100.2")[0], 200)
        self.assertEqual(self.request(self.tail, self.tail_item)[0], 200)

    def test_unknown_share_and_bad_password_share_the_ip_failure_budget(self):
        auth = "Basic " + base64.b64encode(b"fixture-user:wrong").decode()
        for index in range(4):
            path = "/s/" + "f" * 24 + "/" if index % 2 else None
            self.assertEqual(self.request(auth=auth, path=path)[0], 401)
        self.assertEqual(self.request(auth=auth, path="/not-a-share")[0], 429)
        self.assertEqual(self.request(item=self.both_item)[0], 429)

    def test_equivalent_ip_forms_and_spoofed_forwarded_headers_cannot_reset_failures(self):
        clock = Clock()
        self.wan.limiter.clock = clock
        for index in range(5):
            ip = "2001:db8::1" if index % 2 else "2001:0db8:0:0:0:0:0:1"
            self.assertEqual(self.request(auth="bad", ip=ip,
                                         headers=(("X-Forwarded-For", "198.51.100.%d" % index),))[0],
                             429 if index == 4 else 401)
        clock.advance(300)
        self.assertEqual(self.request(ip="2001:db8::1")[0], 200)
        for _ in range(4):
            self.request(auth="bad", ip="198.51.100.1")
        self.assertEqual(self.request(auth="bad", ip="::ffff:198.51.100.1")[0], 429)

    def test_full_failure_table_denies_credentials_before_hash_and_recovers(self):
        limiter = self.wan.limiter
        limiter.limits["auth_entries"] = 1
        clock = Clock()
        limiter.clock = clock
        for _ in range(5):
            self.request(auth="bad")
        with patch.object(dav, "password_ok") as verify:
            self.assertEqual(self.request(ip="198.51.100.2")[0], 503)
            verify.assert_not_called()
        self.assertEqual(self.request(ip="198.51.100.2", auth=None)[0], 401)
        clock.advance(300)
        self.assertEqual(self.request(ip="198.51.100.2")[0], 200)
        self.assertFalse(limiter.entries)

    def test_expiry_readonly_and_descriptor_bounds_still_apply_to_wan(self):
        policy = self.wan_item["connections"]["wan"]
        policy["expires"] = time.time() - 1
        self.assertEqual(self.request()[0], 403)
        policy["expires"] = None
        policy["permission"] = "ro"
        for method in dav.WRITE_METHODS:
            self.assertEqual(self.request(method=method, body=b"denied")[0], 403)
        for leaf in ("../1/file.txt", "%2e%2e/1/file.txt", "a%2fb", ".secret", "incomplete/x"):
            self.assertIn(self.request(leaf=leaf)[0], (400, 403))
        os.symlink(self.root / "1/file.txt", self.root / "2/link")
        os.link(self.root / "1/file.txt", self.root / "2/hard")
        for leaf in ("link", "hard"):
            self.assertEqual(self.request(leaf=leaf)[0], 403)
        self.assertEqual((self.root / "2/file.txt").read_bytes(), b"fixture-content")

    def test_success_error_and_propfind_responses_close_wan_connection(self):
        for kwargs in ({}, {"method": "OPTIONS"}, {"auth": None}, {"ip": None},
                       {"method": "PROPFIND", "leaf": "", "headers": (("Depth", "1"),)}):
            with self.subTest(kwargs=kwargs):
                self.assertEqual(self.request(**kwargs)[2]["Connection"], "close")
        conn = http.client.HTTPConnection(*self.wan.server_address, timeout=3)
        try:
            conn.request("GET", "/", headers={"X-Share-Client-IP": "198.51.100.1"})
            resp = conn.getresponse()
            resp.read()
            self.assertTrue(resp.will_close)
            self.assertIsNone(conn.sock)
        finally:
            conn.close()

    def test_pipelined_request_cannot_reuse_wan_connection_or_another_ip_budget(self):
        with socket.create_connection(self.wan.server_address, timeout=3) as sock:
            first = b"GET / HTTP/1.1\r\nHost: localhost\r\nX-Share-Client-IP: 198.51.100.1\r\n\r\n"
            second = first.replace(b"198.51.100.1", b"198.51.100.2")
            sock.sendall(first + second)
            data = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
        self.assertEqual(data.count(b"HTTP/1.1"), 1)
        self.assertTrue(data.startswith(b"HTTP/1.1 401"))

    def test_expect_continue_is_sent_only_after_network_and_authentication(self):
        auth = base64.b64encode((self.wan_item["username"] + ":" + PASSWORD).encode()).decode()
        for item, authorization, expected in ((self.tail_item, auth, 403),
                                               (self.wan_item, "invalid", 401),
                                               (self.wan_item, auth, 100)):
            with socket.create_connection(self.wan.server_address, timeout=3) as sock:
                raw = ("PUT /s/%s/expect.txt HTTP/1.1\r\nHost: localhost\r\n"
                       "Authorization: Basic %s\r\nX-Share-Client-IP: 198.51.100.1\r\n"
                       "Content-Length: 2\r\nExpect: 100-continue\r\n\r\n") % (item["id"], authorization)
                sock.sendall(raw.encode())
                with sock.makefile("rb") as stream:
                    line = stream.readline()
                    self.assertTrue(line.startswith(("HTTP/1.1 %d " % expected).encode()), line)
                    if expected == 100:
                        self.assertEqual(stream.readline(), b"\r\n")
                        sock.sendall(b"ok")
                        self.assertTrue(stream.readline().startswith(b"HTTP/1.1 201 "))
        self.wait_for(lambda: not self.wan.connections)
        self.assertEqual((self.root / "2/expect.txt").read_bytes(), b"ok")

    def test_wan_hash_parallel_cap_preserves_tail_and_releases_slots(self):
        reached = threading.Event()
        release = threading.Event()
        count_lock = threading.Lock()
        active = 0
        peak = 0
        original = dav.password_ok

        def verify(item, password):
            nonlocal active, peak
            if item is not self.wan_item:
                return original(item, password)
            with count_lock:
                active += 1
                peak = max(peak, active)
                if active == 4:
                    reached.set()
            try:
                if not release.wait(4):
                    raise ValueError("fixture verification did not release")
                return original(item, password)
            finally:
                with count_lock:
                    active -= 1

        # Distinct spellings of the valid credentials are separate single-flight keys
        # (DD-193), so each request needs its own hash slot.
        token = base64.b64encode((self.wan_item["username"] + ":" + PASSWORD).encode()).decode()
        spellings = ["Basic", "basic", "BASIC", "bAsic", "baSic"]
        with ThreadPoolExecutor(max_workers=4) as pool, patch.object(dav, "password_ok", side_effect=verify):
            futures = [pool.submit(self.request, ip="198.51.100.%d" % i, auth=spellings[i - 1] + " " + token)
                       for i in range(1, 5)]
            try:
                self.assertTrue(reached.wait(3))
                self.assertEqual(self.request(ip="198.51.100.5", auth=spellings[4] + " " + token)[0], 503)
                self.assertEqual(self.request(self.tail, self.tail_item)[0], 200)
                self.assertEqual(peak, 4)
            finally:
                release.set()
            self.assertEqual([f.result()[0] for f in futures], [200] * 4)
        self.assertEqual(self.request()[0], 200)
        self.assertFalse(self.wan.limiter.entries)

    def test_per_ip_budget_covers_request_lifetime_after_hash_finishes(self):
        reached = threading.Event()
        release = threading.Event()
        count_lock = threading.Lock()
        active = 0
        original = dav.Handler.get

        def get(handler, pp):
            nonlocal active
            if handler.server is self.wan and handler.client_ip == "198.51.100.1":
                with count_lock:
                    active += 1
                    if active == 4:
                        reached.set()
                if not release.wait(4):
                    raise ValueError("fixture request did not release")
            return original(handler, pp)

        with ThreadPoolExecutor(max_workers=4) as pool, patch.object(dav.Handler, "get", get):
            futures = [pool.submit(self.request) for _ in range(4)]
            try:
                self.assertTrue(reached.wait(3))
                self.assertEqual(self.request()[0], 503)
                self.assertEqual(self.request(ip="198.51.100.2")[0], 200)
                self.assertEqual(self.request(self.tail, self.tail_item)[0], 200)
            finally:
                release.set()
            self.assertEqual([f.result()[0] for f in futures], [200] * 4)
        self.wait_for(lambda: not self.wan.limiter.active)
        self.assertEqual(self.request()[0], 200)

    def test_global_connection_caps_are_independent_and_close_idle_readers(self):
        with contextlib.ExitStack() as stack:
            for _ in range(8):
                sock = stack.enter_context(socket.create_connection(self.wan.server_address, timeout=2))
                sock.sendall(b"GET ")
            self.wait_for(lambda: len(self.wan.connections) == 8)
            with socket.create_connection(self.wan.server_address, timeout=2) as overflow:
                response = http.client.HTTPResponse(overflow)
                response.begin()
                self.assertEqual(response.status, 503)
                self.assertEqual(response.getheader("Retry-After"), "1")
                response.read()
            self.assertEqual(self.request(self.tail, self.tail_item)[0], 200)
            self.wait_for(lambda: not self.tail.connections)
            tail_slots = self.tail.limits["tail_connections"]
            for _ in range(tail_slots):
                sock = stack.enter_context(socket.create_connection(self.tail.server_address, timeout=2))
                sock.sendall(b"GET ")
            self.wait_for(lambda: len(self.tail.connections) == tail_slots)
            with socket.create_connection(self.tail.server_address, timeout=2) as overflow:
                response = http.client.HTTPResponse(overflow)
                response.begin()
                self.assertEqual(response.status, 503)
                self.assertEqual(response.getheader("Retry-After"), "1")
                response.read()
            self.wan.server_close()
            self.tail.server_close()
            self.wait_for(lambda: not self.wan.connections and not self.tail.connections)

    def test_wan_timeout_releases_idle_connection(self):
        config = copy.deepcopy(self.config)
        config["limits"]["wan_timeout_seconds"] = 1
        server = self.start_server("wan", config)
        with socket.create_connection(server.server_address, timeout=3) as sock:
            sock.sendall(b"GET ")
            self.wait_for(lambda: bool(server.connections))
            self.assertEqual(sock.recv(1024), b"")
        self.wait_for(lambda: not server.connections)
        self.assertEqual(self.request(server)[0], 200)

    def test_interrupted_wan_upload_releases_ip_budget_and_removes_temporary_file(self):
        auth = base64.b64encode((self.wan_item["username"] + ":" + PASSWORD).encode()).decode()
        with socket.create_connection(self.wan.server_address, timeout=3) as sock:
            request = ("PUT /s/%s/file.txt HTTP/1.1\r\nHost: localhost\r\n"
                       "Authorization: Basic %s\r\nX-Share-Client-IP: 198.51.100.1\r\n"
                       "Content-Length: 100\r\n\r\nshort") % (self.wan_item["id"], auth)
            sock.sendall(request.encode())
            sock.shutdown(socket.SHUT_WR)
            while sock.recv(4096):
                pass
        self.wait_for(lambda: not self.wan.connections)
        self.assertFalse(self.wan.limiter.active)
        self.assertFalse(list((self.root / "2").glob(".webdav-*")))
        self.assertEqual((self.root / "2/file.txt").read_bytes(), b"fixture-content")

    def test_non_loopback_listeners_invalid_scope_and_bad_limits_rejected(self):
        for host in ("0.0.0.0", "198.51.100.1", "::", "localhost", ""):
            with self.subTest(host=host), self.assertRaises(ValueError):
                dav.Server((host, 0), self.config)
        with self.assertRaises(ValueError):
            dav.Server(("127.0.0.1", 0), self.config, scope="header")
        for bad in (0, -1, True, 1.5, "8", None):
            config = copy.deepcopy(self.config)
            config["limits"]["wan_connections"] = bad
            with self.subTest(limit=bad), self.assertRaises(ValueError):
                dav.Server(("127.0.0.1", 0), config, scope="wan")
        config = copy.deepcopy(self.config)
        del config["limits"]
        with dav.Server(("127.0.0.1", 0), config) as server:
            self.assertEqual(server.limits, shares.DEFAULT_LIMITS)

    def test_main_binds_two_loopbacks_same_port_and_shares_mutation_lock(self):
        tail, wan = MagicMock(), MagicMock()
        tail.__enter__.return_value = tail
        wan.__enter__.return_value = wan
        with patch.object(dav, "Server", side_effect=[tail, wan]) as factory, \
                patch.object(dav, "load", return_value=self.config), \
                patch.object(dav.os, "geteuid", return_value=1000), \
                patch.object(sys, "argv", ["master_webdav.py", "--registry", "fixture", "--port", "61010",
                                           "--wan-listen", "127.0.0.2"]):
            dav.main()
        self.assertEqual([c.args[0] for c in factory.call_args_list],
                         [("127.0.0.1", 61010), ("127.0.0.2", 61010)])
        self.assertEqual(factory.call_args_list[1].kwargs["scope"], "wan")
        self.assertIs(factory.call_args_list[0].kwargs["mutation_lock"],
                      factory.call_args_list[1].kwargs["mutation_lock"])
        tail.shutdown.assert_called_once()
        tail.__exit__.assert_called_once()
        wan.__exit__.assert_called_once()

    def test_main_closes_tail_listener_if_wan_bind_fails(self):
        tail = MagicMock()
        tail.__enter__.return_value = tail
        with patch.object(dav, "Server", side_effect=[tail, OSError("fixture bind failure")]), \
                patch.object(dav, "load", return_value=self.config), \
                patch.object(dav.os, "geteuid", return_value=1000), \
                patch.object(sys, "argv", ["master_webdav.py", "--registry", "fixture", "--port", "61010",
                                           "--wan-listen", "127.0.0.2"]), \
                self.assertRaises(OSError):
            dav.main()
        tail.__exit__.assert_called_once()
        tail.serve_forever.assert_not_called()

    def test_cli_rejects_external_or_overlapping_wan_address(self):
        for address in ("0.0.0.0", "198.51.100.1", "127.0.0.1", "::1", "localhost"):
            with patch.object(sys, "argv", ["master_webdav.py", "--registry", "fixture", "--port", "61010",
                                           "--wan-listen", address]), \
                    patch.object(dav.os, "geteuid", return_value=1000), \
                    contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit), \
                    patch.object(dav, "Server") as factory:
                dav.main()
            factory.assert_not_called()

    def test_cli_requires_wan_address_and_uses_supplied_loopback(self):
        with patch.object(sys, "argv", ["master_webdav.py", "--registry", "fixture", "--port", "61010"]), \
                contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit), \
                patch.object(dav, "Server") as factory:
            dav.main()
        factory.assert_not_called()
        server = MagicMock()
        with patch.object(dav, "Server", return_value=server) as factory, \
                patch.object(dav, "load", return_value=self.config), \
                patch.object(dav.os, "geteuid", return_value=1000), \
                patch.object(sys, "argv", ["master_webdav.py", "--registry", "fixture", "--port", "61010",
                                           "--wan-listen", "127.0.0.3"]):
            dav.main()
        self.assertEqual(factory.call_args_list[1].args[0], ("127.0.0.3", 61010))

    def test_bad_credentials_and_request_targets_never_reach_logs(self):
        output = io.StringIO()
        with contextlib.redirect_stderr(output), contextlib.redirect_stdout(output):
            self.assertEqual(self.request(auth="Basic credential-fixture", path="/private-log-fixture")[0], 401)
        self.assertEqual(output.getvalue(), "")

    def test_tailnet_listener_blocks_repeated_bad_passwords_per_client(self):
        auth = "Basic " + base64.b64encode(b"fixture-user:wrong").decode()
        for _ in range(4):
            self.assertEqual(self.request(self.tail, self.tail_item, auth=auth, ip="100.64.0.8")[0], 401)
        status, _, headers = self.request(self.tail, self.tail_item, auth=auth, ip="100.64.0.8")
        self.assertEqual((status, headers.get("Retry-After")), (429, "300"))
        self.assertEqual(self.request(self.tail, self.tail_item, ip="100.64.0.8")[0], 429)
        self.assertEqual(self.request(self.tail, self.tail_item, ip="100.64.0.9")[0], 200)
        # Local readiness probes carry no client header and share one budget.
        for _ in range(5):
            self.request(self.tail, self.tail_item, auth=auth, ip=None)
        self.assertEqual(self.request(self.tail, self.tail_item, ip=None)[0], 429)
        self.assertEqual(self.request(self.tail, self.tail_item, ip="100.64.0.9")[0], 200)
        self.assertEqual(self.request(self.tail, self.tail_item, ip="not-an-ip")[0], 400)
        # A request without credentials is only the challenge: readiness probes keep seeing 401.
        self.assertEqual(self.request(self.tail, self.tail_item, auth=None, ip=None)[0], 401)

    def test_share_budget_closes_the_share_to_new_addresses_only(self):
        limiter = self.wan.limiter
        limiter.limits = dict(limiter.limits, share_failures=3)
        self.assertEqual(self.request(ip="198.51.100.50")[0], 200)
        auth = "Basic " + base64.b64encode(b"fixture-user:wrong").decode()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            for index in range(3):
                self.assertEqual(self.request(auth=auth, ip="198.51.100.%d" % (index + 1))[0], 401)
        self.assertIn(self.wan_item["id"] + " (wan)", output.getvalue())
        self.assertNotIn("198.51.100", output.getvalue())
        self.assertNotIn("wrong", output.getvalue())
        status, _, headers = self.request(ip="198.51.100.60")
        self.assertEqual((status, headers["Retry-After"]), (429, "3600"))
        # The recipient who already logged in keeps working; other shares and listeners too.
        self.assertEqual(self.request(ip="198.51.100.50")[0], 200)
        self.assertEqual(self.request(item=self.both_item, ip="198.51.100.60")[0], 200)
        self.assertEqual(self.request(self.tail, self.tail_item, ip="198.51.100.60")[0], 200)
        with patch.object(limiter, "clock", return_value=limiter.clock() + 3600):
            self.assertEqual(self.request(ip="198.51.100.60")[0], 200)

    def test_known_addresses_are_bounded_per_share(self):
        limiter = dav.Limiter(dict(shares.DEFAULT_LIMITS), Clock())
        for index in range(dav.Limiter.KNOWN_PER_SHARE + 5):
            with limiter.credentials("198.51.100.%d" % index, "a" * 24):
                pass
        known = limiter.shares["a" * 24]["known"]
        self.assertEqual(len(known), dav.Limiter.KNOWN_PER_SHARE)
        self.assertNotIn("198.51.100.0", known)
        self.assertIn("198.51.100.%d" % (dav.Limiter.KNOWN_PER_SHARE + 4), known)

    def test_wrong_user_and_unknown_share_cost_one_hash_disabled_scope_costs_none(self):
        calls = []

        def verify(item, password):
            calls.append(item)
            return shares.password_ok(item, password)
        wrong_user = "Basic " + base64.b64encode(("other-user:" + PASSWORD).encode()).decode()
        with patch.object(dav, "password_ok", side_effect=verify):
            self.assertEqual(self.request(self.tail, self.tail_item, auth=wrong_user)[0], 401)
            self.assertEqual(self.request(self.tail, self.tail_item, path="/s/" + "f" * 24 + "/")[0], 401)
            self.tail_item["connections"]["tailscale"]["enabled"] = False
            self.assertEqual(self.request(self.tail, self.tail_item)[0], 403)
            self.assertEqual(calls, [self.tail.decoy] * 2)
            self.tail_item["connections"]["tailscale"]["enabled"] = True
            self.assertEqual(self.request(self.wan, self.wan_item, auth=wrong_user)[0], 401)
            self.assertEqual(self.request(self.tail, self.tail_item)[0], 200)
        self.assertEqual(calls, [self.tail.decoy] * 2 + [self.wan.decoy, self.tail_item])
        self.assertFalse(shares.password_ok(self.tail.decoy, PASSWORD))

    def test_writes_stop_before_the_disk_reserve(self):
        body = b"x" * 1024
        copy_to = (("Destination", "/s/%s/copy.txt" % self.tail_item["id"]),)
        with patch.object(dav, "disk_room", return_value=False):
            self.assertEqual(self.request(self.tail, self.tail_item, method="PUT", leaf="new.bin", body=body)[0], 507)
            self.assertEqual(self.request(self.tail, self.tail_item, method="COPY", headers=copy_to)[0], 507)
        # Streaming re-checks: space that runs out mid-upload removes the partial file.
        answers = iter([True, False])
        with patch.object(dav, "DISK_CHECK_EVERY", 512), \
                patch.object(dav, "disk_room", side_effect=lambda *_: next(answers)):
            self.assertEqual(self.request(self.tail, self.tail_item, method="PUT", leaf="late.bin", body=body)[0], 507)
        for name in ("new.bin", "copy.txt", "late.bin"):
            self.assertFalse((self.root / "1" / name).exists())
        self.assertFalse(list((self.root / "1").glob(".webdav-*")))
        self.assertEqual(self.request(self.tail, self.tail_item, method="PUT", leaf="ok.bin", body=body)[0], 201)

    def test_disk_reserve_is_five_gib_or_a_tenth_of_a_small_disk(self):
        gib = 1024 ** 3

        def vfs(total, free):
            return types.SimpleNamespace(f_frsize=1, f_blocks=total, f_bavail=free)
        with patch.object(dav.os, "fstatvfs", return_value=vfs(1000 * gib, 6 * gib)):
            self.assertTrue(dav.disk_room(0, gib))
            self.assertFalse(dav.disk_room(0, 2 * gib))
        with patch.object(dav.os, "fstatvfs", return_value=vfs(20 * gib, 3 * gib)):
            self.assertTrue(dav.disk_room(0, gib))
            self.assertFalse(dav.disk_room(0, gib + 1))

    def test_successful_login_is_remembered_without_weakening_checks(self):
        calls = []

        def verify(item, password):
            calls.append(item["id"] if item is not self.tail.decoy else "decoy")
            return shares.password_ok(item, password)
        wrong = "Basic " + base64.b64encode(b"fixture-user:wrong").decode()
        with patch.object(dav, "password_ok", side_effect=verify):
            for _ in range(3):
                self.assertEqual(self.request(self.tail, self.tail_item)[0], 200)
            self.assertEqual(calls, [self.tail_item["id"]])
            # A different password is still hashed; a disabled connection bypasses the cache and hash.
            self.assertEqual(self.request(self.tail, self.tail_item, auth=wrong)[0], 401)
            self.tail_item["connections"]["tailscale"]["enabled"] = False
            self.assertEqual(self.request(self.tail, self.tail_item)[0], 403)
            self.tail_item["connections"]["tailscale"]["enabled"] = True
            self.assertEqual(calls, [self.tail_item["id"], self.tail_item["id"]])
            # Entries expire, and each listener keeps its own memory.
            with patch.object(dav.time, "monotonic", return_value=time.monotonic() + dav.AUTH_CACHE_SECONDS + 1):
                self.assertEqual(self.request(self.tail, self.tail_item)[0], 200)
            self.assertEqual(self.request(self.wan, self.both_item)[0], 200)
        self.assertEqual(len(calls), 4)
        self.assertLessEqual(len(self.tail.auth_cache), dav.AUTH_CACHE_SIZE)

    def test_tailnet_errors_announce_the_close(self):
        status, _, headers = self.request(self.tail, self.tail_item, auth="Basic !!!!")
        self.assertEqual((status, headers.get("Connection")), (401, "close"))
        status, _, headers = self.request(self.tail, self.tail_item)
        self.assertEqual(status, 200)
        self.assertNotEqual(headers.get("Connection"), "close")

    def test_accepted_connections_send_without_nagle_delay(self):
        seen = []
        original = dav.Handler.setup

        def setup(handler):
            original(handler)
            seen.append(handler.connection.getsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY))
        with patch.object(dav.Handler, "setup", setup):
            self.assertEqual(self.request(self.tail, self.tail_item)[0], 200)
        self.assertTrue(seen and all(seen))


if __name__ == "__main__":
    unittest.main()
