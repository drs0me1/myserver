"""Stage 3 concurrency and publication races, temporary data/loopback only."""
import base64
from concurrent.futures import ThreadPoolExecutor
import contextlib
import copy
import errno
import http.client
import os
import socket
import threading
import time
import unittest
from unittest.mock import Mock, patch

import test_webdav_networks as fixture

dav, shares = fixture.dav, fixture.shares


class Stage3WebDAVTests(unittest.TestCase):
    # Reuse the portable two-listener fixture without inheriting its test cases.
    setUp = fixture.NetworkTests.setUp
    start_server = fixture.NetworkTests.start_server
    stop_server = fixture.NetworkTests.stop_server
    wait_for = fixture.NetworkTests.wait_for
    request = fixture.NetworkTests.request

    @classmethod
    def setUpClass(cls):
        cls.salt, cls.digest = shares.password_hash(fixture.PASSWORD)

    def test_auth_storms_bound_both_pools_and_leave_the_other_scope_available(self):
        for server, item, other, other_item, cap in (
                (self.wan, self.wan_item, self.tail, self.tail_item, 4),
                (self.tail, self.tail_item, self.wan, self.wan_item, 2)):
            with self.subTest(scope=server.scope):
                server.auth_cache.clear()
                entered, release = threading.Event(), threading.Event()
                lock = threading.Lock()
                active = peak = 0
                original = dav.password_ok

                def verify(record, password):
                    nonlocal active, peak
                    if record is not item:
                        return original(record, password)
                    with lock:
                        active += 1
                        peak = max(peak, active)
                        if active == cap:
                            entered.set()
                    try:
                        self.assertTrue(release.wait(4))
                        return original(record, password)
                    finally:
                        with lock:
                            active -= 1

                # Distinct spellings of the same valid credentials are separate keys, so
                # single flight (DD-193) cannot merge them: each needs its own hash slot.
                token = base64.b64encode((item["username"] + ":" + fixture.PASSWORD).encode()).decode()
                spellings = ["Basic", "basic", "BASIC", "bAsic", "baSic", "basIc"]
                with ThreadPoolExecutor(max_workers=cap) as pool, patch.object(dav, "password_ok", verify):
                    futures = [pool.submit(self.request, server, item, ip="198.51.100.%d" % n,
                                           auth=spellings[n - 10] + " " + token)
                               for n in range(10, 10 + cap)]
                    try:
                        self.assertTrue(entered.wait(2))
                        start = time.monotonic()
                        code, _, headers = self.request(server, item, ip="198.51.100.200",
                                                        auth=spellings[-1] + " " + token)
                        self.assertEqual((code, headers.get("Retry-After")), (503, "1"))
                        self.assertLess(time.monotonic() - start, 1)
                        self.assertEqual(self.request(other, other_item)[0], 200)
                        self.assertEqual(peak, cap)
                        self.assertNotIn("198.51.100.200", server.limiter.entries)
                    finally:
                        release.set()
                    self.assertEqual([f.result()[0] for f in futures], [200] * cap)

    def test_waiter_rechecks_success_cache_before_hash_and_after_timeout(self):
        for server, item in ((self.wan, self.wan_item), (self.tail, self.tail_item)):
            for free_slot in (True, False):
                with self.subTest(scope=server.scope, free_slot=free_slot):
                    server.auth_cache.clear()
                    slots = server.limiter.auth_slots
                    cap = server.limits["wan_auth_parallel" if server.scope == "wan" else "tail_auth_parallel"]
                    for _ in range(cap):
                        self.assertTrue(slots.acquire(False))
                    held = cap
                    key_seen, waiting = [], threading.Event()
                    original = server.remembered
                    original_acquire = slots.acquire

                    def remembered(key):
                        key_seen.append(key)
                        return original(key)

                    def acquire(*args, **kwargs):
                        waiting.set()
                        return original_acquire(*args, **kwargs)

                    try:
                        with ThreadPoolExecutor(max_workers=1) as pool, \
                                patch.object(server, "remembered", remembered), \
                                patch.object(slots, "acquire", acquire), \
                                patch.object(dav, "password_ok") as verify:
                            future = pool.submit(self.request, server, item)
                            self.assertTrue(waiting.wait(2))
                            server.remember(key_seen[0])
                            if free_slot:
                                slots.release()
                                held -= 1
                            self.assertEqual(future.result(timeout=2)[0], 200)
                            verify.assert_not_called()
                            self.assertGreaterEqual(len(key_seen), 2)
                    finally:
                        for _ in range(held):
                            slots.release()

    def test_concurrent_identical_logins_share_one_real_hash(self):
        # DD-193 single flight: the follower waits on the leader, not on a hash slot.
        self.tail.limiter.auth_slots = threading.BoundedSemaphore(1)
        entered, release, joined = threading.Event(), threading.Event(), threading.Event()
        original_verify = dav.password_ok
        original_join = self.tail.join_flight
        calls = []

        def verify(item, password):
            calls.append(item)
            entered.set()
            self.assertTrue(release.wait(2))
            return original_verify(item, password)

        def join(key):
            leader, event = original_join(key)
            if not leader:
                joined.set()
            return leader, event

        with ThreadPoolExecutor(max_workers=2) as pool, patch.object(dav, "password_ok", verify), \
                patch.object(self.tail, "join_flight", join):
            first = pool.submit(self.request, self.tail, self.tail_item)
            try:
                self.assertTrue(entered.wait(2))
                second = pool.submit(self.request, self.tail, self.tail_item)
                self.assertTrue(joined.wait(2))
            finally:
                release.set()
            self.assertEqual(first.result(timeout=2)[0], 200)
            self.assertEqual(second.result(timeout=2)[0], 200)
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.tail.auth_flights, {})

    def test_identical_login_burst_hashes_once_and_never_answers_503(self):
        # An Infuse-like burst with one cold login: one slot, a slow hash, eight requests.
        for server, item in ((self.wan, self.wan_item), (self.tail, self.tail_item)):
            with self.subTest(scope=server.scope):
                server.auth_cache.clear()
                server.limiter.auth_slots = threading.BoundedSemaphore(1)
                release, calls = threading.Event(), []
                original = dav.password_ok

                def verify(record, password):
                    calls.append(record)
                    self.assertTrue(release.wait(3))
                    return original(record, password)

                with ThreadPoolExecutor(max_workers=8) as pool, patch.object(dav, "password_ok", verify):
                    # WAN admits four requests per address; spread the burst over two.
                    futures = [pool.submit(self.request, server, item, ip="198.51.100.%d" % (20 + n % 2))
                               for n in range(8)]
                    time.sleep(.5)
                    release.set()
                    codes = [f.result(timeout=4)[0] for f in futures]
                self.assertEqual(codes, [200] * 8)
                self.assertEqual(len(calls), 1)
                self.assertEqual(server.auth_flights, {})

    def test_follower_checks_itself_after_a_failed_or_slow_leader(self):
        self.tail.limiter.auth_slots = threading.BoundedSemaphore(1)
        wrong = "Basic " + base64.b64encode((self.tail_item["username"] + ":wrong-password").encode()).decode()
        for slow in (False, True):
            with self.subTest(slow=slow):
                entered, release, calls = threading.Event(), threading.Event(), []
                original = dav.password_ok

                def verify(record, password):
                    calls.append(record)
                    entered.set()
                    self.assertTrue(release.wait(3))
                    return original(record, password)

                auth = wrong if not slow else True
                with ThreadPoolExecutor(max_workers=2) as pool, patch.object(dav, "password_ok", verify), \
                        patch.object(dav, "AUTH_FLIGHT_SECONDS", .1 if slow else 2):
                    first = pool.submit(self.request, self.tail, self.tail_item, ip="198.51.100.31", auth=auth)
                    self.assertTrue(entered.wait(2))
                    second = pool.submit(self.request, self.tail, self.tail_item, ip="198.51.100.32", auth=auth)
                    if slow:
                        # The leader still holds the only slot: the follower gives up waiting
                        # on it and gets the normal bounded-capacity answer.
                        code, _, headers = second.result(timeout=2)
                        self.assertEqual((code, headers.get("Retry-After")), (503, "1"))
                        release.set()
                        self.assertEqual(first.result(timeout=2)[0], 200)
                    else:
                        time.sleep(.2)
                        release.set()
                        self.assertEqual([first.result(timeout=3)[0], second.result(timeout=3)[0]], [401, 401])
                        self.assertEqual(len(calls), 2)
                self.assertEqual(self.tail.auth_flights, {})
                self.tail.auth_cache.clear()
                self.tail.limiter.entries.clear()

    def test_hash_error_releases_slots_without_creating_bad_credential_history(self):
        for server, item in ((self.wan, self.wan_item), (self.tail, self.tail_item)):
            with patch.object(dav, "password_ok", side_effect=ValueError("fixture")):
                self.assertEqual(self.request(server, item)[0], 403)
            self.assertFalse(server.limiter.entries)
            self.assertEqual(self.request(server, item)[0], 200)

    def test_capacity_rejection_never_waits_for_a_blocked_reader_or_spawns_workers(self):
        for server in (self.wan, self.tail):
            with contextlib.ExitStack() as stack:
                while server.slots.acquire(False):
                    stack.callback(server.slots.release)
                peer = Mock()

                def blocked_send(data):
                    peer.setblocking.assert_called_with(False)
                    self.assertIn(b"503 Service Unavailable", data)
                    raise BlockingIOError()

                peer.send.side_effect = blocked_send
                with patch.object(dav.http.server.ThreadingHTTPServer, "process_request") as spawn:
                    for _ in range(100):
                        server.process_request(peer, ("127.0.0.1", 1))
                    spawn.assert_not_called()
                self.assertEqual(peer.send.call_count, 100)
                self.assertEqual(peer.close.call_count, 100)
                peer.sendall.assert_not_called()
                self.assertFalse(server.connections)
            item = self.wan_item if server.scope == "wan" else self.tail_item
            self.assertEqual(self.request(server, item)[0], 200)

    def test_tail_idle_sockets_release_admission_and_new_requests_work(self):
        config = copy.deepcopy(self.config)
        config["limits"]["tail_connections"] = 1
        with patch.object(dav, "TAIL_TIMEOUT_SECONDS", .15):
            server = self.start_server(config=config)
            with socket.create_connection(server.server_address, timeout=2) as idle:
                idle.sendall(b"GET ")
                self.wait_for(lambda: len(server.connections) == 1)
                code, _, headers = self.request(server, self.tail_item)
                self.assertEqual((code, headers.get("Retry-After")), (503, "1"))
                self.assertEqual(idle.recv(1024), b"")
            self.wait_for(lambda: not server.connections)
            self.assertEqual(self.request(server, self.tail_item)[0], 200)

    def test_slow_wan_put_does_not_block_an_independent_tail_writer(self):
        auth = base64.b64encode((self.wan_item["username"] + ":" + fixture.PASSWORD).encode()).decode()
        with socket.create_connection(self.wan.server_address, timeout=3) as slow:
            slow.sendall(("PUT /s/%s/slow.bin HTTP/1.1\r\nHost: localhost\r\n"
                          "Authorization: Basic %s\r\nX-Share-Client-IP: 198.51.100.1\r\n"
                          "Content-Length: 8\r\n\r\npart" % (self.wan_item["id"], auth)).encode())
            self.wait_for(lambda: list((self.root / "2").glob(".webdav-*")))
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(self.request, self.tail, self.tail_item,
                                     method="PUT", leaf="other.bin", body=b"independent")
                try:
                    self.assertEqual(future.result(timeout=1)[0], 201)
                finally:
                    slow.sendall(b"done")
            response = http.client.HTTPResponse(slow)
            response.begin()
            self.assertEqual(response.status, 201)
            response.read()
        self.assertEqual((self.root / "2/slow.bin").read_bytes(), b"partdone")
        self.assertEqual((self.root / "1/other.bin").read_bytes(), b"independent")

    def test_slow_copy_io_does_not_hold_the_mutation_lock(self):
        entered, release = threading.Event(), threading.Event()
        original = dav.Handler.staged_file

        @contextlib.contextmanager
        def staging(handler, parent, chunks, size=0):
            def slow_chunks():
                for chunk in chunks:
                    entered.set()
                    if not release.wait(3):
                        raise RuntimeError("copy did not release")
                    yield chunk
            with original(handler, parent, slow_chunks() if handler.command == "COPY" else chunks, size) as temp:
                yield temp

        dest = "/s/%s/copied.txt" % self.both_item["id"]
        with ThreadPoolExecutor(max_workers=2) as pool, patch.object(dav.Handler, "staged_file", staging):
            copying = pool.submit(self.request, self.wan, self.both_item, method="COPY",
                                  headers=(("Destination", dest),))
            try:
                self.assertTrue(entered.wait(2))
                writing = pool.submit(self.request, self.tail, self.both_item, method="PUT",
                                      leaf="independent.bin", body=b"independent")
                self.assertEqual(writing.result(timeout=1)[0], 201)
            finally:
                release.set()
            self.assertEqual(copying.result(timeout=2)[0], 201)
        self.assertEqual((self.root / "3/copied.txt").read_bytes(), b"fixture-content")

    def race(self, method, intervene, leaf="file.txt", headers=(), body=b"staged"):
        """Hold a completed stage while a real request or filesystem change wins."""
        entered, release = threading.Event(), threading.Event()
        original = dav.Handler.staged_file

        @contextlib.contextmanager
        def staging(handler, parent, chunks, size=0):
            with original(handler, parent, chunks, size) as temp:
                if handler.server is self.wan:
                    entered.set()
                    if not release.wait(4):
                        raise RuntimeError("staged writer did not release")
                yield temp

        with ThreadPoolExecutor(max_workers=1) as pool, patch.object(dav.Handler, "staged_file", staging):
            future = pool.submit(self.request, self.wan, self.both_item, method=method,
                                 leaf=leaf, headers=headers, body=body if method == "PUT" else None)
            try:
                self.assertTrue(entered.wait(2))
                intervene()
            finally:
                release.set()
            result = future.result(timeout=3)
        self.assertFalse(list(self.root.rglob(".webdav-*")))
        return result[0]

    def tail_write(self, leaf="file.txt", body=b"winner"):
        self.assertIn(self.request(self.tail, self.both_item, method="PUT", leaf=leaf, body=body)[0], (201, 204))

    def test_put_rechecks_if_match_and_unconditional_target_identity(self):
        tag = self.request(self.tail, self.both_item)[2]["ETag"]
        self.assertEqual(self.race("PUT", self.tail_write, headers=(("If-Match", tag),)), 412)
        self.assertEqual((self.root / "3/file.txt").read_bytes(), b"winner")
        self.assertEqual(self.race("PUT", lambda: self.tail_write(body=b"newer")), 409)
        self.assertEqual((self.root / "3/file.txt").read_bytes(), b"newer")

    def test_put_rechecks_if_none_match_after_another_writer_creates_target(self):
        self.assertEqual(self.race("PUT", lambda: self.tail_write("new.bin"), leaf="new.bin",
                                   headers=(("If-None-Match", "*"),)), 412)
        self.assertEqual((self.root / "3/new.bin").read_bytes(), b"winner")

    def test_copy_rechecks_overwrite_and_source_preconditions(self):
        dest = "/s/%s/copied.txt" % self.both_item["id"]
        self.assertEqual(self.race("COPY", lambda: self.tail_write("copied.txt"),
                                   headers=(("Destination", dest), ("Overwrite", "F"))), 412)
        self.assertEqual((self.root / "3/copied.txt").read_bytes(), b"winner")
        tag = self.request(self.tail, self.both_item)[2]["ETag"]
        self.assertEqual(self.race("COPY", self.tail_write,
                                   headers=(("Destination", dest), ("If-Match", tag))), 412)
        self.assertEqual((self.root / "3/copied.txt").read_bytes(), b"winner")

    def test_copy_rechecks_destination_identity_even_with_overwrite_true(self):
        dest = "/s/%s/copied.txt" % self.both_item["id"]
        self.assertEqual(self.race("COPY", lambda: self.tail_write("copied.txt"),
                                   headers=(("Destination", dest),)), 409)
        self.assertEqual((self.root / "3/copied.txt").read_bytes(), b"winner")

    def test_copy_rejects_replaced_or_in_place_modified_source(self):
        dest = "/s/%s/copied.txt" % self.both_item["id"]
        source = self.root / "3/file.txt"
        self.assertEqual(self.race("COPY", self.tail_write, headers=(("Destination", dest),)), 409)

        def edit_in_place():
            old = source.stat()
            source.write_bytes(b"edited")
            os.utime(source, ns=(old.st_atime_ns, old.st_mtime_ns))

        self.assertEqual(self.race("COPY", edit_in_place, headers=(("Destination", dest),)), 409)
        self.assertFalse((self.root / "3/copied.txt").exists())

    def test_copy_rejects_source_replaced_between_initial_stat_and_open(self):
        source, replacement = self.root / "3/file.txt", self.root / "3/replacement.txt"
        replacement.write_bytes(b"replacement")
        original = os.open
        swapped = False

        def opening(path, flags, *args, **kwargs):
            nonlocal swapped
            if path == "file.txt" and flags == shares.FILE_FLAGS and not swapped:
                swapped = True
                os.replace(replacement, source)
            return original(path, flags, *args, **kwargs)

        dest = "/s/%s/copied.txt" % self.both_item["id"]
        with patch.object(dav.os, "open", opening):
            self.assertEqual(self.request(self.wan, self.both_item, method="COPY",
                                           headers=(("Destination", dest),))[0], 409)
        self.assertTrue(swapped)
        self.assertEqual(source.read_bytes(), b"replacement")
        self.assertFalse(list(self.root.rglob("copied.txt")))
        self.assertFalse(list(self.root.rglob(".webdav-*")))

    def test_copy_rechecks_if_none_match_on_the_source_at_publish(self):
        replacement = self.root / "3/replacement.txt"
        replacement.write_bytes(b"new source")
        tag = dav.etag(replacement.stat())
        dest = "/s/%s/copied.txt" % self.both_item["id"]
        self.assertEqual(self.race("COPY", lambda: replacement.replace(self.root / "3/file.txt"),
                                   headers=(("Destination", dest), ("If-None-Match", tag))), 412)
        self.assertFalse((self.root / "3/copied.txt").exists())

    def test_put_rejects_moved_replaced_and_detached_parent_and_cleans_stage(self):
        parent = self.root / "3/sub"
        for action in ("move", "replace", "delete"):
            with self.subTest(action=action):
                parent.mkdir()

                def change_parent():
                    if action == "delete":
                        self.assertEqual(self.request(self.tail, self.both_item, method="DELETE", leaf="sub")[0], 204)
                    else:
                        target = "/s/%s/moved-%s" % (self.both_item["id"], action)
                        self.assertEqual(self.request(self.tail, self.both_item, method="MOVE", leaf="sub",
                                                       headers=(("Destination", target),))[0], 201)
                        if action == "replace":
                            parent.mkdir()

                self.assertEqual(self.race("PUT", change_parent, leaf="sub/new.bin"), 409)
                self.assertFalse(list(self.root.rglob("new.bin")))
                if parent.exists():
                    parent.rmdir()

    def test_copy_rejects_source_or_destination_parent_moved_during_staging(self):
        for moved in ("src", "dst"):
            with self.subTest(parent=moved):
                base = self.root / "3" / moved
                base.mkdir()
                (base / "file.txt").write_bytes(b"original")
                leaf = moved + "/file.txt" if moved == "src" else "file.txt"
                dest = "copied.txt" if moved == "src" else "dst/copied.txt"
                self.assertEqual(self.race("COPY", lambda: base.rename(base.with_name(moved + "-moved")),
                                           leaf=leaf, headers=(("Destination", "/s/%s/%s" %
                                                               (self.both_item["id"], dest)),)), 409)
                self.assertFalse(list(self.root.rglob("copied.txt")))

    def test_publication_rechecks_root_scope_expiry_pause_permission_and_account(self):
        item = self.both_item
        for change in ({"enabled": False}, {"expires": time.time() - 1},
                       {"both_disabled": True}, {"permission": "ro"}, {"hash": "f" * 64}):
            before = copy.deepcopy(item)
            with self.subTest(change=change):
                def change_policy():
                    if "hash" in change:
                        item.update(change)
                    elif "both_disabled" in change:
                        for policy in item["connections"].values():
                            policy["enabled"] = False
                    else:
                        item["connections"]["wan"].update(change)
                try:
                    self.assertEqual(self.race("PUT", change_policy, leaf="new.bin"), 403)
                    self.assertFalse((self.root / "3/new.bin").exists())
                finally:
                    item.update(before)

        def replace_root():
            (self.root / "3").rename(self.root / "old-root")
            (self.root / "3").mkdir()

        self.assertEqual(self.race("PUT", replace_root, leaf="new.bin"), 410)
        self.assertFalse(list(self.root.rglob("new.bin")))

    def test_disk_reserve_is_rechecked_after_small_stage_before_publish(self):
        with patch.object(dav, "disk_room", side_effect=[True, False]):
            self.assertEqual(self.request(self.tail, self.tail_item, method="PUT", body=b"small")[0], 507)
        self.assertEqual((self.root / "1/file.txt").read_bytes(), b"fixture-content")
        self.assertFalse(list(self.root.rglob(".webdav-*")))

    def test_stage_fsync_failure_preserves_target_and_cleans_temporary_file(self):
        with patch.object(dav.os, "fsync", side_effect=OSError(errno.EIO, "fixture")):
            self.assertEqual(self.request(self.tail, self.tail_item, method="PUT", body=b"new")[0], 403)
        self.assertEqual((self.root / "1/file.txt").read_bytes(), b"fixture-content")
        self.assertFalse(list(self.root.rglob(".webdav-*")))
        self.assertEqual(self.request(self.tail, self.tail_item, method="PUT", body=b"new")[0], 204)


if __name__ == "__main__":
    unittest.main()
