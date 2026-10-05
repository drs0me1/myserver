#!/usr/bin/env python3
"""Klasör sınırları tanıtıcılarla korunan, bağımsız hesaplı sınırlı WebDAV.

Root olarak çalışmaz. Sembolik/çoklu sabit bağlantılar, gizli dosyalar ve bağlanan
alt dosya sistemleri sunulmaz. PUT/COPY tamamlanmadan hedef değiştirilmez. LOCK
ve PROPPATCH desteklenmez; desteklenmeyen işlemler başarılı gibi gösterilmez.
"""
import argparse
import base64
from collections import OrderedDict, deque
import contextlib
import copy
import email.utils
import hmac
import http.server
import ipaddress
import math
import mimetypes
import os
import re
import secrets
import socket
import stat
import threading
import time
import urllib.parse
import xml.etree.ElementTree as ET

from master_shares import DEFAULT_LIMITS, DIR_FLAGS, FILE_FLAGS, ShareError, identity, load, open_dir, parts, password_ok

MAX_UPLOAD = 64 * 1024 ** 3
CHUNK = 1024 * 1024
# DD-180: writes stop before the filesystem falls under min(5 GiB, 10%) free, so the
# journal, apt and state files keep room. Same numbers in master-files-panel.
DISK_RESERVE = 5 * 1024 ** 3
DISK_RESERVE_DIVISOR = 10
DISK_CHECK_EVERY = 64 * 1024 ** 2
# DD-181: a successful login is remembered in memory so each Infuse/Finder request does
# not pay one scrypt check (~20-60 ms). Registry edits restart the service and clear it.
AUTH_CACHE_SECONDS = 600
AUTH_CACHE_SIZE = 256
AUTH_WAIT_SECONDS = 0.2
# DD-193: concurrent requests carrying the same credentials share one verification
# (Infuse opens several connections at once) instead of competing for hash slots.
AUTH_FLIGHT_SECONDS = 2
TAIL_TIMEOUT_SECONDS = 60
DAV = "{DAV:}"
ET.register_namespace("d", "DAV:")
READ_METHODS = ("OPTIONS", "GET", "HEAD", "PROPFIND")
WRITE_METHODS = ("PUT", "MKCOL", "DELETE", "MOVE", "COPY")


class DavError(Exception):
    def __init__(self, code, message="İstek reddedildi.", retry_after=None):
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after


class Limiter:
    """Sliding bad-credential history by client IP and by share, on both listeners (DD-180).

    Both listeners bound parallel hash work independently; WAN also bounds requests
    per IP. A share that
    collects share_failures in share_window_seconds is closed for share_block_seconds
    to addresses that have not logged in to it since the service started.
    """
    KNOWN_PER_SHARE = 32

    def __init__(self, limits, clock=time.monotonic, scope="wan"):
        self.limits = limits
        self.clock = clock
        self.scope = scope
        self.lock = threading.Lock()
        self.active = {}
        self.entries = {}
        self.shares = {}
        self.auth_slots = threading.BoundedSemaphore(
            limits["wan_auth_parallel" if scope == "wan" else "tail_auth_parallel"])

    def prune(self, now):
        # Called under lock. Never evict an active block or an unfinished attempt.
        for ip, entry in list(self.entries.items()):
            failures = entry["failures"]
            while failures and failures[0] <= now - self.limits["auth_window_seconds"]:
                failures.popleft()
            if not failures and entry["blocked_until"] <= now and not entry["pending"]:
                del self.entries[ip]

    def blocked(self, ip, now):
        entry = self.entries.get(ip)
        if entry and entry["blocked_until"] > now:
            raise DavError(429, retry_after=math.ceil(entry["blocked_until"] - now))

    def share_blocked(self, share, ip, now):
        record = self.shares.get(share)
        if record and record["blocked_until"] > now and ip not in record["known"]:
            raise DavError(429, retry_after=math.ceil(record["blocked_until"] - now))

    def share_result(self, share, ip, now, failed):
        # Called under lock; share ids come from the registry, so the table is bounded.
        record = self.shares.setdefault(share, {"failures": deque(), "blocked_until": 0,
                                                "known": OrderedDict()})
        if not failed:
            record["known"][ip] = now
            record["known"].move_to_end(ip)
            while len(record["known"]) > self.KNOWN_PER_SHARE:
                record["known"].popitem(last=False)
            return
        failures = record["failures"]
        while failures and failures[0] <= now - self.limits["share_window_seconds"]:
            failures.popleft()
        failures.append(now)
        if len(failures) >= self.limits["share_failures"] and record["blocked_until"] <= now:
            failures.clear()
            record["blocked_until"] = now + self.limits["share_block_seconds"]
            # Registry id and fixed numbers only; never the address, user or password.
            print("paylasim: %s (%s) %d dk içinde %d hatalı giriş; yeni adresler %d dk bekletiliyor"
                  % (share, self.scope, self.limits["share_window_seconds"] // 60,
                     self.limits["share_failures"], self.limits["share_block_seconds"] // 60), flush=True)

    @contextlib.contextmanager
    def request(self, ip):
        with self.lock:
            now = self.clock()
            self.prune(now)
            self.blocked(ip, now)
            if self.active.get(ip, 0) >= self.limits["wan_connections_per_ip"]:
                raise DavError(503, retry_after=1)
            self.active[ip] = self.active.get(ip, 0) + 1
        try:
            yield
        finally:
            with self.lock:
                self.active[ip] -= 1
                if not self.active[ip]:
                    del self.active[ip]

    @contextlib.contextmanager
    def credentials(self, ip, share=None):
        with self.lock:
            now = self.clock()
            self.prune(now)
            self.blocked(ip, now)
            if share is not None:
                self.share_blocked(share, ip, now)
            if ip not in self.entries:
                if len(self.entries) >= self.limits["auth_entries"]:
                    raise DavError(503, retry_after=1)
                self.entries[ip] = {"failures": deque(), "blocked_until": 0, "pending": 0}
            entry = self.entries[ip]
            entry["pending"] += 1
        failed = succeeded = False
        try:
            yield
            succeeded = True
        except DavError as err:
            failed = err.code == 401
            raise
        finally:
            with self.lock:
                now = self.clock()
                entry["pending"] -= 1
                self.prune(now)
                if share is not None and (failed or succeeded):
                    self.share_result(share, ip, now, failed)
                # A request admitted before a block cannot lengthen its TTL.
                if failed and entry["blocked_until"] <= now:
                    entry["failures"].append(now)
                    self.entries[ip] = entry
                    if len(entry["failures"]) >= self.limits["auth_failures"]:
                        entry["failures"].clear()
                        entry["blocked_until"] = now + self.limits["auth_block_seconds"]
                self.blocked(ip, now)

    @contextlib.contextmanager
    def hashing(self):
        # Wait only briefly, within the listener's bounded connection pool. The
        # caller checks the successful-login cache again even after a timeout.
        admitted = self.auth_slots.acquire(timeout=AUTH_WAIT_SECONDS)
        try:
            yield admitted
        finally:
            if admitted:
                self.auth_slots.release()


def disk_room(fd, incoming=0):
    st = os.fstatvfs(fd)
    reserve = min(DISK_RESERVE, st.f_blocks * st.f_frsize // DISK_RESERVE_DIVISOR)
    return st.f_bavail * st.f_frsize - incoming >= reserve


def check_stat(st, device):
    if st.st_dev != device or not (stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode)):
        raise DavError(403, "Bağlantı veya alt dosya sistemi sunulmaz.")
    if stat.S_ISREG(st.st_mode) and st.st_nlink != 1:
        raise DavError(403, "Çoklu sabit bağlantı sunulmaz.")


def etag(st):
    return '"%x-%x-%x"' % (st.st_ino, st.st_size, st.st_mtime_ns)


def file_version(st):
    # Include ctime: a replacement/in-place edit may keep the size and mtime.
    return ((st.st_dev, st.st_ino, st.st_mode, st.st_nlink, st.st_size,
             st.st_mtime_ns, st.st_ctime_ns) if st is not None else None)


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "Konsol-WebDAV"
    sys_version = ""
    protocol_version = "HTTP/1.1"
    # DD-181: headers and body are separate writes. On Caddy's kept-alive upstream
    # connection Nagle held the body for the peer's delayed ACK: ~44 ms per request.
    disable_nagle_algorithm = True

    def setup(self):
        super().setup()
        self.connection.settimeout(self.server.limits["wan_timeout_seconds"]
                                   if self.server.scope == "wan" else TAIL_TIMEOUT_SECONDS)

    def handle(self):
        try:
            super().handle()
        except OSError:
            # Disconnects during header parsing or shutdown are ordinary cleanup.
            self.close_connection = True

    def parse_request(self):
        if not super().parse_request():
            return False
        if self.server.scope == "wan":
            self.close_connection = True
        # Unsupported methods still pass through the same ingress/auth gates.
        if not hasattr(self, "do_" + self.command):
            setattr(self, "do_" + self.command, self.dispatch)
        return True

    def handle_expect_100(self):
        # Delay upload permission until network and credential checks have passed.
        return True

    def end_headers(self):
        if self.server.scope == "wan":
            self.close_connection = True
        # DD-181: say so whenever this server closes, or Caddy may reuse the closed connection.
        if self.close_connection and not any(line.lower().startswith(b"connection:")
                                             for line in getattr(self, "_headers_buffer", [])):
            self.send_header("Connection", "close")
        self.response_started = True
        super().end_headers()

    def log_message(self, *args):
        pass  # Never log Authorization, credentials or attacker-controlled request lines.

    def send(self, code, body=b"", headers=None):
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def live(self):
        policy = self.item["connections"][self.server.scope]
        if not policy["enabled"]:
            raise DavError(403, "Bu bağlantı kapalı.")
        if policy["expires"] and time.time() >= policy["expires"]:
            raise DavError(403, "Bu bağlantının süresi doldu.")
        if self.command in WRITE_METHODS and policy["permission"] != "rw":
            raise DavError(403, "Bu bağlantı salt okunur.")

    def authenticate(self):
        match = re.match(r"^/s/([0-9a-f]{24})(?:/|$)", self.path)
        self.item = next((i for i in self.server.config["items"]
                          if match and i["id"] == match.group(1)), None)
        item = self.item
        if item:
            policy = item.get("connections", {}).get(self.server.scope)
            if not policy or not policy.get("enabled"):
                raise DavError(403)
        supplied = self.headers.get_all("Authorization", [])
        if not supplied:
            raise DavError(401)
        with self.server.limiter.credentials(self.client_ip, item["id"] if item else None):
            self.check_credentials(supplied)
        self.authorized = copy.deepcopy(item)
        self.live()
        if self.headers.get("Origin") or self.headers.get("Sec-Fetch-Site") == "cross-site":
            raise DavError(403)
        self.prefix = "/s/" + item["id"] + "/"
        if self.command not in READ_METHODS + WRITE_METHODS:
            raise DavError(405)
        # Chosen root is re-opened O_NOFOLLOW for every request, then identity checked.
        self.rootfd = open_dir(self.server.config["root"], parts(item["path"]))
        if identity(self.rootfd) != item["identity"]:
            raise DavError(410, "Klasör taşındı veya değiştirildi; yönetici paylaşımı güncellemeli.")
        self.device = os.fstat(self.rootfd).st_dev

    def check_credentials(self, supplied):
        if len(supplied) != 1 or len(supplied[0]) > 2048:
            raise DavError(401)
        try:
            kind, value = supplied[0].split(" ", 1)
            user, password = base64.b64decode(value, validate=True).decode("utf-8").split(":", 1)
        except (ValueError, UnicodeError):
            raise DavError(401)
        item = self.item
        # DD-180: an unknown share, a wrong user or scheme costs one hash
        # too, so response time does not reveal which part was wrong.
        valid = (kind.lower() == "basic" and item is not None
                 and len(password) <= 256
                 and hmac.compare_digest(user.encode("utf-8"), item["username"].encode("utf-8")))
        key = None
        leader = False
        if valid:
            key = (item["id"], item["hash"],
                   hmac.new(self.server.auth_key, supplied[0].encode("utf-8"), "sha256").digest())
            if self.server.remembered(key):
                return
            leader, flight = self.server.join_flight(key)
            if not leader:
                # Same exact credentials are being verified now: reuse that success.
                # A failure or timeout falls through to this request's own check.
                flight.wait(AUTH_FLIGHT_SECONDS)
                if self.server.remembered(key):
                    return
        try:
            with self.server.limiter.hashing() as admitted:
                if valid and self.server.remembered(key):
                    return
                if not admitted:
                    raise DavError(503, retry_after=1)
                if not password_ok(item if valid else self.server.decoy, password[:256]) or not valid:
                    raise DavError(401)
                # Publish success before releasing the slot: waiting requests can use it.
                self.server.remember(key)
        finally:
            if leader:
                self.server.land_flight(key)

    def client_address_ip(self):
        values = self.headers.get_all("X-Share-Client-IP", [])
        if len(values) != 1 or len(values[0]) > 45 or "%" in values[0]:
            raise DavError(400)
        try:
            address = ipaddress.ip_address(values[0])
        except ValueError:
            raise DavError(400)
        # Canonicalize IPv6 spellings and IPv4-mapped addresses to one budget.
        return str(getattr(address, "ipv4_mapped", None) or address)

    def path_parts(self, raw, destination=False):
        parsed = urllib.parse.urlsplit(raw)
        if destination:
            if parsed.netloc and (parsed.netloc.lower() != self.headers.get("Host", "").lower()
                                  or parsed.scheme not in ("http", "https")):
                raise DavError(403, "Başka bir adrese taşınamaz.")
        elif parsed.netloc or parsed.scheme:
            raise DavError(400)
        if parsed.query or parsed.fragment or re.search(r"%(?:2f|5c|00)", parsed.path, re.I):
            raise DavError(400)
        if parsed.path == self.prefix[:-1]:
            return []
        if not parsed.path.startswith(self.prefix):
            raise DavError(403, "Başka bir paylaşıma erişilemez.")
        try:
            pp = parts(urllib.parse.unquote(parsed.path[len(self.prefix):], errors="strict"), empty=True)
            if self.protected(pp):
                raise DavError(403)
            return pp
        except (ShareError, UnicodeError):
            raise DavError(403)

    def protected(self, pp):
        """DD-203: a folder a package writes into (root-relative list from the registry) is neither
        listed nor reachable through any share that contains it."""
        rel = "/".join(parts(self.authorized["path"]) + list(pp))
        return any(rel == p or rel.startswith(p + "/") for p in self.server.config.get("protected", []))

    def folder(self, pp):
        fd = open_dir(self.rootfd, pp)
        try:
            check_stat(os.fstat(fd), self.device)
        except BaseException:
            os.close(fd)
            raise
        return fd

    def stat_path(self, pp):
        if not pp:
            return os.fstat(self.rootfd)
        with contextlib.ExitStack() as stack:
            fd = self.folder(pp[:-1])
            stack.callback(os.close, fd)
            st = os.stat(pp[-1], dir_fd=fd, follow_symlinks=False)
            check_stat(st, self.device)
            return st

    def body(self, limit):
        chunks, total = [], 0
        for chunk in self.body_chunks(limit):
            chunks.append(chunk)
            total += len(chunk)
        return b"".join(chunks)

    def body_chunks(self, limit):
        transfer = self.headers.get("Transfer-Encoding", "").lower()
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) > 1 or (transfer and lengths) or transfer not in ("", "chunked"):
            raise DavError(400)
        if not transfer:
            try:
                left = int(lengths[0]) if lengths else 0
            except ValueError:
                raise DavError(400)
            if left < 0 or left > limit:
                raise DavError(413)
            while left:
                self.live()
                data = self.rfile.read(min(CHUNK, left))
                if not data:
                    raise DavError(400, "Yükleme yarıda kesildi.")
                left -= len(data)
                yield data
            return
        total = 0
        while True:
            line = self.rfile.readline(128)
            if not re.fullmatch(rb"[0-9a-fA-F]{1,16}\r\n", line):
                raise DavError(400)
            size = int(line.strip(), 16)
            if total + size > limit:
                raise DavError(413)
            if not size:
                if self.rfile.read(2) != b"\r\n":
                    raise DavError(400)
                return
            total += size
            left = size
            while left:
                self.live()
                data = self.rfile.read(min(CHUNK, left))
                if not data:
                    raise DavError(400)
                left -= len(data)
                yield data
            if self.rfile.read(2) != b"\r\n":
                raise DavError(400)

    def preconditions(self, st):
        tag = etag(st) if st else ""
        if self.headers.get("If-Match") and self.headers["If-Match"] not in (tag, "*" if st else ""):
            raise DavError(412)
        if self.headers.get("If-None-Match") in (tag, "*") and st:
            raise DavError(412)
        # No DAV locks: do not silently ignore a client's lock condition.
        if self.headers.get("If"):
            raise DavError(412)

    def target_stat(self, fd, name):
        try:
            st = os.stat(name, dir_fd=fd, follow_symlinks=False)
            check_stat(st, self.device)
            return st
        except FileNotFoundError:
            return None

    def get(self, pp):
        st = self.stat_path(pp)
        if stat.S_ISDIR(st.st_mode):
            self.send(200, "Klasör paylaşımı. WebDAV istemcisiyle bağlanın.\n".encode())
            return
        parent = self.folder(pp[:-1])
        try:
            fd = os.open(pp[-1], FILE_FLAGS, dir_fd=parent)
        finally:
            os.close(parent)
        with os.fdopen(fd, "rb") as stream:
            st = os.fstat(stream.fileno())
            check_stat(st, self.device)
            tag = etag(st)
            if self.headers.get("If-None-Match") == tag:
                self.send(304, headers={"ETag": tag})
                return
            self.preconditions(st)
            start, end, code = 0, st.st_size - 1, 200
            raw_range = self.headers.get("Range", "")
            if raw_range and self.headers.get("If-Range", tag) == tag:
                match = re.fullmatch(r"bytes=(\d*)-(\d*)", raw_range)
                if not match or not any(match.groups()) or not st.st_size:
                    raise DavError(416)
                a, b = match.groups()
                start = int(a) if a else max(0, st.st_size - int(b))
                end = min(st.st_size - 1, int(b)) if a and b else st.st_size - 1
                if start > end:
                    raise DavError(416)
                code = 206
            length = max(0, end - start + 1)
            self.send_response(code)
            self.send_header("Content-Length", str(length))
            self.send_header("Content-Type", mimetypes.guess_type(pp[-1])[0] or "application/octet-stream")
            self.send_header("ETag", tag)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Last-Modified", email.utils.formatdate(st.st_mtime, usegmt=True))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "sandbox; default-src 'none'")
            if code == 206:
                self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, st.st_size))
            self.end_headers()
            if self.command == "HEAD":
                return
            stream.seek(start)
            while length:
                self.live()
                data = stream.read(min(CHUNK, length))
                if not data:
                    self.close_connection = True
                    break
                self.wfile.write(data)
                length -= len(data)

    def propfind(self, pp):
        depth = self.headers.get("Depth", "infinity")
        if depth not in ("0", "1"):
            raise DavError(403, "Depth 0 veya 1 kullanın.")
        raw = self.body(65536)
        requested = None
        if raw:
            if b"<!" in raw:
                raise DavError(400)
            try:
                doc = ET.fromstring(raw)
            except ET.ParseError:
                raise DavError(400)
            prop = doc.find(DAV + "prop")
            if prop is not None:
                requested = [p.tag for p in prop]
        st = self.stat_path(pp)
        entries = [(pp, st)]
        if depth == "1" and stat.S_ISDIR(st.st_mode):
            fd = self.folder(pp)
            try:
                names = os.listdir(fd)
                if len(names) > 10000:
                    raise DavError(507, "Bu klasörde çok fazla öge var.")
                for name in sorted(names):
                    try:
                        if self.protected(pp + [name]):
                            continue
                        parts(name)
                        child = self.target_stat(fd, name)
                        if child:
                            entries.append((pp + [name], child))
                    except (OSError, ShareError, DavError):
                        continue
            finally:
                os.close(fd)
        root = ET.Element(DAV + "multistatus")
        for path, info in entries:
            response = ET.SubElement(root, DAV + "response")
            href = self.prefix + "/".join(urllib.parse.quote(p, safe="") for p in path)
            directory = stat.S_ISDIR(info.st_mode)
            if directory and not href.endswith("/"):
                href += "/"
            ET.SubElement(response, DAV + "href").text = href
            props = {DAV + "displayname": path[-1] if path else self.item["name"],
                     DAV + "resourcetype": None, DAV + "getcontentlength": str(info.st_size if not directory else 0),
                     DAV + "getlastmodified": email.utils.formatdate(info.st_mtime, usegmt=True),
                     DAV + "getetag": etag(info),
                     DAV + "getcontenttype": "httpd/unix-directory" if directory else (mimetypes.guess_type(path[-1])[0] or "application/octet-stream")}
            for status, keys in (("200 OK", [k for k in (requested or props) if k in props]),
                                 ("404 Not Found", [k for k in (requested or []) if k not in props])):
                if not keys:
                    continue
                pstat = ET.SubElement(response, DAV + "propstat")
                pnode = ET.SubElement(pstat, DAV + "prop")
                for key in keys:
                    elem = ET.SubElement(pnode, key)
                    if status.startswith("200"):
                        elem.text = props[key]
                        if key == DAV + "resourcetype" and directory:
                            ET.SubElement(elem, DAV + "collection")
                ET.SubElement(pstat, DAV + "status").text = "HTTP/1.1 " + status
        body = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        self.send_response(207)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Type", "application/xml; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def remove_tree(self, fd, name, budget):
        budget[0] -= 1
        self.live()
        if budget[0] < 0:
            raise DavError(507)
        st = self.target_stat(fd, name)
        if st is None:
            raise DavError(404)
        if stat.S_ISDIR(st.st_mode):
            child = os.open(name, DIR_FLAGS, dir_fd=fd)
            try:
                for leaf in os.listdir(child):
                    # Hidden files may be removed along with their parent, never followed.
                    self.remove_tree(child, leaf, budget)
            finally:
                os.close(child)
            os.rmdir(name, dir_fd=fd)
        else:
            os.unlink(name, dir_fd=fd)

    def write(self, pp):
        if not pp:
            raise DavError(403, "Paylaşım kökü değiştirilemez.")
        if self.command in ("PUT", "COPY"):
            self.staged_write(pp)
            return
        with self.server.mutation_lock, contextlib.ExitStack() as stack:
            self.recheck_share()
            parent = self.folder(pp[:-1])
            stack.callback(os.close, parent)
            st = self.target_stat(parent, pp[-1])
            self.preconditions(st)
            if self.command == "MKCOL":
                if self.body(65536):
                    raise DavError(415)
                self.recheck_share()
                os.mkdir(pp[-1], 0o775, dir_fd=parent)
                self.send(201)
            elif self.command == "DELETE":
                self.remove_tree(parent, pp[-1], [100000])
                self.send(204)
            elif self.command == "MOVE":
                if st is None:
                    raise DavError(404)
                dest = self.path_parts(self.headers.get("Destination", ""), destination=True)
                if not dest or dest == pp or dest[:len(pp)] == pp:
                    raise DavError(403)
                dfd = self.folder(dest[:-1])
                stack.callback(os.close, dfd)
                existing = self.target_stat(dfd, dest[-1])
                if self.headers.get("Overwrite", "T") not in ("T", "F"):
                    raise DavError(400)
                if existing and self.headers.get("Overwrite") == "F":
                    raise DavError(412)
                self.live()
                os.rename(pp[-1], dest[-1], src_dir_fd=parent, dst_dir_fd=dfd)
                self.send(204 if existing else 201)

    def recheck_share(self):
        self.live()
        current = next((i for i in self.server.config["items"]
                        if i["id"] == self.authorized["id"]), None)
        if (current != self.authorized or not current["connections"][self.server.scope]["enabled"]
                or current["connections"][self.server.scope]["permission"] != "rw"):
            raise DavError(403, "Paylaşım izni değişti; yeniden deneyin.")
        try:
            fd = open_dir(self.server.config["root"], parts(current["path"]))
        except OSError as err:
            raise DavError(410, "Paylaşım klasörü taşındı veya değiştirildi.") from err
        try:
            if identity(fd) != self.authorized["identity"] or identity(self.rootfd) != identity(fd):
                raise DavError(410, "Paylaşım klasörü taşındı veya değiştirildi.")
        finally:
            os.close(fd)

    def recheck_parent(self, pp, held):
        # A descriptor alone is insufficient: MOVE/DELETE may have detached its
        # directory while the body was arriving. Walk from the verified live root.
        try:
            fresh = self.folder(pp)
        except OSError as err:
            raise DavError(409, "Hedef veya kaynak klasörü taşındı; yeniden deneyin.") from err
        try:
            if identity(fresh) != identity(held):
                raise DavError(409, "Hedef veya kaynak klasörü değişti; yeniden deneyin.")
        finally:
            os.close(fresh)

    def staged_write(self, pp):
        with contextlib.ExitStack() as stack:
            with self.server.mutation_lock:
                self.recheck_share()
                parent = self.folder(pp[:-1])
                stack.callback(os.close, parent)
                st = self.target_stat(parent, pp[-1])
                self.preconditions(st)
                if self.command == "COPY":
                    if st is None:
                        raise DavError(404)
                    if stat.S_ISDIR(st.st_mode):
                        raise DavError(501, "Klasör COPY desteklenmiyor; dosya kopyalanabilir.")
                    dest = self.path_parts(self.headers.get("Destination", ""), destination=True)
                    if not dest or dest == pp or dest[:len(pp)] == pp:
                        raise DavError(403)
                    if self.headers.get("Overwrite", "T") not in ("T", "F"):
                        raise DavError(400)
                    dfd = self.folder(dest[:-1])
                    stack.callback(os.close, dfd)
                    existing = self.target_stat(dfd, dest[-1])
                    if existing and self.headers.get("Overwrite") == "F":
                        raise DavError(412)
                    src = os.open(pp[-1], FILE_FLAGS, dir_fd=parent)
                    stream = stack.enter_context(os.fdopen(src, "rb"))
                    source = os.fstat(src)
                    check_stat(source, self.device)
                    if file_version(source) != file_version(st):
                        raise DavError(409, "Kaynak dosya değişti; yeniden deneyin.")
                    chunks, size = iter(lambda: stream.read(CHUNK), b""), source.st_size
                else:
                    if st and stat.S_ISDIR(st.st_mode):
                        raise DavError(405)
                    if not self.headers.get("Content-Length") and not self.headers.get("Transfer-Encoding"):
                        raise DavError(411)
                    lengths = self.headers.get_all("Content-Length", [])
                    size = int(lengths[0]) if len(lengths) == 1 and lengths[0].isdigit() else 0
                    size = size if size <= MAX_UPLOAD else 0
                    dest, dfd, existing = pp, parent, st
                    chunks = self.body_chunks(MAX_UPLOAD)
            # No global mutation lock while receiving/copying or fsyncing the data.
            with self.staged_file(dfd, chunks, size) as temp:
                with self.server.mutation_lock:
                    self.recheck_share()
                    self.recheck_parent(pp[:-1], parent)
                    self.recheck_parent(dest[:-1], dfd)
                    current = self.target_stat(parent, pp[-1])
                    self.preconditions(current)
                    if file_version(current) != file_version(st):
                        raise DavError(409, "Dosya işlem sırasında değişti; yeniden deneyin.")
                    if self.command == "COPY":
                        # Check both the path and the still-open source descriptor.
                        if file_version(os.fstat(src)) != file_version(source):
                            raise DavError(409, "Kaynak dosya işlem sırasında değişti.")
                        target = self.target_stat(dfd, dest[-1])
                        if target and self.headers.get("Overwrite") == "F":
                            raise DavError(412)
                        if file_version(target) != file_version(existing):
                            raise DavError(409, "Hedef dosya işlem sırasında değişti.")
                    if not disk_room(dfd):
                        raise DavError(507, "Sunucuda yeterli boş alan yok.")
                    os.rename(temp, dest[-1], src_dir_fd=dfd, dst_dir_fd=dfd)
                os.fsync(dfd)
        self.send(204 if existing else 201)

    @contextlib.contextmanager
    def staged_file(self, parent, chunks, size=0):
        full = DavError(507, "Sunucuda yeterli boş alan yok.")
        if not disk_room(parent, size):
            raise full
        temp = ".webdav-" + secrets.token_hex(12)
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o664, dir_fd=parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                since = 0
                for chunk in chunks:
                    self.live()
                    stream.write(chunk)
                    since += len(chunk)
                    # Chunked bodies declare no size; other writers share the disk too.
                    if since >= DISK_CHECK_EVERY:
                        since = 0
                        if not disk_room(parent):
                            raise full
                stream.flush()
                os.fsync(stream.fileno())
            yield temp
        finally:
            try:
                os.unlink(temp, dir_fd=parent)
            except FileNotFoundError:
                pass

    def dispatch(self):
        self.rootfd = None
        self.response_started = False
        budget = contextlib.ExitStack()
        try:
            if self.server.scope == "wan":
                self.client_ip = self.client_address_ip()
                budget.enter_context(self.server.limiter.request(self.client_ip))
            else:
                # DD-180: Caddy always sets it; local readiness probes connect without it.
                self.client_ip = (self.client_address_ip()
                                  if self.headers.get_all("X-Share-Client-IP") else "yerel")
            self.authenticate()
            pp = self.path_parts(self.path)
            if self.headers.get("Expect", "").lower() == "100-continue":
                self.wfile.write(b"HTTP/1.1 100 Continue\r\n\r\n")
            if self.command == "OPTIONS":
                self.send(200, headers={"DAV": "1", "Allow": ", ".join(READ_METHODS + (WRITE_METHODS if self.item["connections"][self.server.scope]["permission"] == "rw" else ()))})
            elif self.command in ("GET", "HEAD"):
                self.get(pp)
            elif self.command == "PROPFIND":
                self.propfind(pp)
            else:
                self.write(pp)
        except (OSError, ShareError, DavError, ValueError) as err:
            self.close_connection = True
            code = err.code if isinstance(err, DavError) else 404 if isinstance(err, FileNotFoundError) else 403
            extra = {"WWW-Authenticate": 'Basic realm="Klasor-%s", charset="UTF-8"' % (self.item["id"] if getattr(self, "item", None) else "WebDAV")} if code == 401 else {}
            if isinstance(err, DavError) and err.retry_after is not None:
                extra["Retry-After"] = str(err.retry_after)
            if not self.response_started:
                try:
                    self.send(code, (str(err) if isinstance(err, DavError) else "İstek gerçekleştirilemedi.").encode(), extra)
                except OSError:
                    pass
        finally:
            if self.rootfd is not None:
                os.close(self.rootfd)
            budget.close()

    do_GET = do_HEAD = do_OPTIONS = do_PROPFIND = dispatch
    do_PUT = do_MKCOL = do_DELETE = do_MOVE = do_COPY = dispatch
    do_LOCK = do_UNLOCK = do_PROPPATCH = do_POST = dispatch


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 128
    def __init__(self, address, config, scope="tailscale", mutation_lock=None):
        if scope not in ("tailscale", "wan"):
            raise ValueError("Geçersiz paylaşım ağı.")
        if not ipaddress.IPv4Address(address[0]).is_loopback:
            raise ValueError("WebDAV yalnız loopback adresinde dinleyebilir.")
        self.config = config
        self.scope = scope
        supplied = config.get("limits", {})
        if not isinstance(supplied, dict):
            raise ValueError("Geçersiz paylaşım sınırları.")
        self.limits = dict(DEFAULT_LIMITS, **supplied)
        if any(type(self.limits[key]) is not int or self.limits[key] <= 0 for key in DEFAULT_LIMITS):
            raise ValueError("Geçersiz paylaşım sınırları.")
        self.mutation_lock = mutation_lock if mutation_lock is not None else threading.Lock()
        self.limiter = Limiter(self.limits, scope=scope)
        # Never matches: hashed instead of the real record when the request cannot succeed.
        self.decoy = {"salt": secrets.token_hex(16), "hash": secrets.token_hex(32)}
        # Keyed by share, stored hash and an HMAC of the exact Authorization value.
        self.auth_key = secrets.token_bytes(32)
        self.auth_cache = OrderedDict()
        self.auth_flights = {}
        self.auth_lock = threading.Lock()
        self.slots = threading.BoundedSemaphore(self.limits["wan_connections" if scope == "wan" else "tail_connections"])
        self.connections = set()
        self.connection_lock = threading.Lock()
        super().__init__(address, Handler)

    def remembered(self, key):
        with self.auth_lock:
            until = self.auth_cache.get(key)
            if until is not None and until > time.monotonic():
                self.auth_cache.move_to_end(key)
                return True
            self.auth_cache.pop(key, None)
            return False

    def remember(self, key):
        with self.auth_lock:
            self.auth_cache[key] = time.monotonic() + AUTH_CACHE_SECONDS
            self.auth_cache.move_to_end(key)
            while len(self.auth_cache) > AUTH_CACHE_SIZE:
                self.auth_cache.popitem(last=False)

    def join_flight(self, key):
        """(leader, event): the first request for a key verifies; others wait on it.
        Entries live only while a verification runs, so the table is bounded by
        this listener's connection slots."""
        with self.auth_lock:
            event = self.auth_flights.get(key)
            if event is None:
                event = self.auth_flights[key] = threading.Event()
                return True, event
            return False, event

    def land_flight(self, key):
        with self.auth_lock:
            event = self.auth_flights.pop(key, None)
        if event is not None:
            event.set()

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            # Best-effort overload response, with no parsing, waiting or new thread.
            # One small nonblocking send bounds work even when the peer never reads.
            try:
                request.setblocking(False)
                request.send(b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\n"
                             b"Retry-After: 1\r\nConnection: close\r\n\r\n")
            except OSError:
                pass
            finally:
                self.shutdown_request(request)
            return
        with self.connection_lock:
            self.connections.add(request)
        try:
            super().process_request(request, address)
        except BaseException:
            with self.connection_lock:
                self.connections.discard(request)
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            with self.connection_lock:
                self.connections.discard(request)
            self.slots.release()

    def server_close(self):
        # Wake idle/header/body readers so shutdown releases their request budgets.
        with self.connection_lock:
            for request in self.connections:
                with contextlib.suppress(OSError):
                    request.shutdown(socket.SHUT_RDWR)
        super().server_close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--wan-listen", required=True)
    args = parser.parse_args()
    if os.geteuid() == 0:
        parser.error("WebDAV root olarak çalıştırılamaz.")
    try:
        wan_address = ipaddress.IPv4Address(args.wan_listen)
    except ValueError:
        parser.error("WAN arka ucu geçerli bir IPv4 loopback adresi olmalı.")
    if not wan_address.is_loopback or str(wan_address) == "127.0.0.1":
        parser.error("WAN arka ucu Tailscale'den ayrı bir loopback adresi olmalı.")
    config = load(args.registry)
    mutation_lock = threading.Lock()
    with Server(("127.0.0.1", args.port), config, mutation_lock=mutation_lock) as tail:
        with Server((args.wan_listen, args.port), config, scope="wan", mutation_lock=mutation_lock) as wan:
            thread = threading.Thread(target=tail.serve_forever, daemon=True)
            thread.start()
            try:
                wan.serve_forever()
            finally:
                tail.shutdown()
                thread.join()


if __name__ == "__main__":
    main()
