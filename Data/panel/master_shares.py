#!/usr/bin/env python3
"""Klasör paylaşımlarının root yöneticisi. Parolalar yalnız stdin; diskte scrypt özeti.

WebDAV işlemleri indirme hesabında, master_webdav.py içinde yürür. Yönetici sabit
eylemler dışında komut çalıştırmaz; JSON kayıt 0600 ve servis LoadCredential kullanır.
"""
import argparse
import contextlib
import ctypes
import errno
import fcntl
import hashlib
import hmac
import http.client
import ipaddress
import json
import math
import os
import re
import secrets
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import time

UNIT = "master-paylasim.service"
ID_RE = re.compile(r"[0-9a-f]{24}\Z")
USER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{2,31}\Z")
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
# DD-180: auth_* (per client IP) and share_* (per share, all IPs) apply to both listeners.
# DD-181: 64 tailnet slots, so Caddy's pool of idle upstream connections cannot fill them.
DEFAULT_LIMITS = {"wan_connections": 8, "wan_connections_per_ip": 4,
                  "tail_connections": 64, "wan_auth_parallel": 4, "tail_auth_parallel": 2,
                  "auth_failures": 5, "auth_window_seconds": 60,
                  "auth_block_seconds": 300, "auth_entries": 4096,
                  "share_failures": 100, "share_window_seconds": 3600,
                  "share_block_seconds": 3600,
                  "wan_timeout_seconds": 30}
# Edge sockets include unauthenticated/idle connections, before proxy admission.
WAN_SOCKET_PER_IP = 16
WAN_SOCKET_TOTAL = 64
SCOPES = ("tailscale", "wan")


class ShareError(Exception):
    pass


def env_read(path):
    with open(path, encoding="utf-8") as stream:
        return {k: v.strip('"') for line in stream if not line.startswith("#") and "=" in line
                for k, v in [line.rstrip("\n").split("=", 1)]}


def parts(raw, empty=False):
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > 4096:
        raise ShareError("Geçersiz klasör yolu.")
    out = raw.strip("/").split("/") if raw.strip("/") else []
    if (not out and not empty) or len(out) > 64 or any(
            not p or p.startswith(".") or "\\" in p or len(p.encode("utf-8")) > 255
            or any(ord(c) < 32 or ord(c) == 127 for c in p) for p in out):
        raise ShareError("Kök, gizli/iç klasörler ve geçersiz yollar paylaşılamaz.")
    return out


def open_dir(root, path):
    fd = os.open(root, DIR_FLAGS) if isinstance(root, str) else os.dup(root)
    try:
        for name in path:
            nxt = os.open(name, DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = nxt
        return fd
    except BaseException:
        os.close(fd)
        raise


def identity(fd):
    """Birth time prevents inode reuse from exposing a replacement directory."""
    st = os.fstat(fd)
    if sys.platform == "linux":
        buf = ctypes.create_string_buffer(256)
        libc = ctypes.CDLL(None, use_errno=True)
        # statx(fd, "", AT_EMPTY_PATH|AT_SYMLINK_NOFOLLOW, STATX_BTIME, buf)
        if libc.statx(fd, b"", 0x1000 | 0x100, 0x800, ctypes.byref(buf)) != 0:
            raise ShareError("Dosya sistemi klasör kimliğini doğrulayamıyor (statx).")
        mask = struct.unpack_from("=I", buf.raw, 0)[0]
        sec, ns = struct.unpack_from("=qI", buf.raw, 80)
        if not mask & 0x800:
            raise ShareError("Bu dosya sistemi güvenli paylaşım için oluşturulma zamanını sağlamıyor.")
        birth = [sec, ns]
    else:
        birth = [getattr(st, "st_birthtime", 0)]
    return [st.st_dev, st.st_ino, birth]


def assigned(address):
    """DD-182: is this IPv4 address still on this host? Only a local address can be bound;
    no port is reserved. Errors other than "not local" keep the current behaviour."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            with contextlib.suppress(OSError):
                probe.setsockopt(socket.IPPROTO_IP, getattr(socket, "IP_BIND_ADDRESS_NO_PORT", 24), 1)
            probe.bind((address, 0))
    except OSError as err:
        return err.errno != errno.EADDRNOTAVAIL
    return True


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt),
                            n=16384, r=8, p=1, dklen=32).hex()
    return salt, digest


def password_ok(item, password):
    return hmac.compare_digest(password_hash(password, item["salt"])[1], item["hash"])


def load(path):
    fd = os.open(path, FILE_FLAGS)
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ShareError("Paylaşım kaydı düz dosya olmalı.")
        raw = stream.read(262145)
    if len(raw) > 262144:
        raise ShareError("Paylaşım kaydı çok büyük.")
    data = json.loads(raw)
    return normalize_registry(data)


def validate_connection(value):
    if (not isinstance(value, dict) or set(value) != {"enabled", "permission", "expires"}
            or type(value["enabled"]) is not bool or value["permission"] not in ("ro", "rw")):
        raise ShareError("Bağlantı ayarı geçersiz.")
    expires = value["expires"]
    if expires is not None and (type(expires) not in (int, float) or expires <= 0
                                or (isinstance(expires, float) and not math.isfinite(expires))):
        raise ShareError("Bağlantının bitiş zamanı geçersiz.")
    return value


def normalize_registry(data):
    """DD-192: one policy per trusted listener; schema-3 access is never widened."""
    if (not isinstance(data, dict) or type(data.get("schema")) is not int
            or data["schema"] not in (3, 4) or not isinstance(data.get("items"), list)):
        raise ShareError("Paylaşım kaydı desteklenmiyor.")
    for item in data["items"]:
        if not isinstance(item, dict):
            raise ShareError("Paylaşım kaydı desteklenmiyor.")
        if data["schema"] == 3:
            networks = validate_networks(item.get("networks"))
            if "connections" in item or "expires" not in item or type(item.get("paused")) is not bool:
                raise ShareError("Paylaşım kaydı desteklenmiyor.")
            item["connections"] = {scope: validate_connection({
                "enabled": scope in networks and not item["paused"],
                "permission": item.get("permission"), "expires": item.get("expires")})
                for scope in SCOPES}
            for key in ("networks", "paused", "permission", "expires"):
                item.pop(key, None)
        elif any(k in item for k in ("networks", "paused", "permission", "expires")):
            raise ShareError("Paylaşım kaydı çelişkili bağlantı ayarları içeriyor.")
        connections = item.get("connections")
        if not isinstance(connections, dict) or set(connections) != set(SCOPES):
            raise ShareError("Paylaşımın iki bağlantı kaydı da gerekli.")
        for policy in connections.values():
            validate_connection(policy)
    data.update(schema=4, limits=dict(DEFAULT_LIMITS))
    return data


def validate_networks(value):
    if (not isinstance(value, list) or not value or len(value) > 2
            or any(n not in ("tailscale", "wan") for n in value)
            or len(set(value)) != len(value)):
        raise ShareError("En az bir erişim ağı seçin: Tailscale veya WAN.")
    return [n for n in ("tailscale", "wan") if n in value]


def atomic(path, data):
    directory = os.path.dirname(path)
    fd, temp = tempfile.mkstemp(prefix=".webdav-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        dfd = os.open(directory, DIR_FLAGS)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


class Manager:
    def __init__(self, state):
        self.state = str(state)
        self.env = env_read(state)
        self.path = self.env["SHARE_STATE_FILE"]
        self.pending = self.path + ".pending"

    @classmethod
    def from_env(cls, env):
        """Read-only views for callers that hold the parsed state (master_publications)."""
        manager = cls.__new__(cls)
        manager.state, manager.env = "", dict(env)
        manager.path = env["SHARE_STATE_FILE"]
        manager.pending = manager.path + ".pending"
        return manager

    def initial(self):
        e = self.env
        return {"schema": 4, "limits": dict(DEFAULT_LIMITS), "root": e["SERVER_ROOT"], "items": [],
                "blocked": [e["FILES_PANEL_TRASH"], e["SHARE_DIR"]], "protected": self.protected_folders()}

    def read(self):
        try:
            data = load(self.path)
        except FileNotFoundError:
            return self.initial()
        # DD-203: the folders packages write into follow the catalogue and the packages' own reports,
        # not the saved file; the WebDAV server hides and refuses them inside shares. A report that
        # cannot be read leaves the list at the declarations here (path validation fails closed itself).
        data["protected"] = self.protected_folders()
        try:
            data["protected"] += [p for p in self.written_folders() if p not in data["protected"]]
        except ShareError:
            pass
        return data

    def relative_folders(self, paths):
        root = self.env["SERVER_ROOT"].rstrip("/")
        out = []
        for value in paths:
            value = os.path.normpath(value)
            if value.startswith(root + "/") and value != root:
                rel = os.path.relpath(value, root)
                if rel not in out:
                    out.append(rel)
        return out

    def protected_folders(self):
        """DD-203: every catalogued package's declared folders (PAKET_KLASORLER, absolute), root-relative."""
        from master_settings import read_manifests
        paths = []
        for manifest in read_manifests(self.env).values():
            paths.extend(manifest.get("PAKET_KLASORLER", "").split())
        return self.relative_folders(paths)

    def written_folders(self):
        """DD-203: what the packages' own modules (PAKET_KLASOR_MODUL) report they write into right now,
        e.g. a temporary folder the user chose in the application; fail closed on an unreadable report."""
        from master_settings import SettingsError, load_package_module, read_manifests
        paths = []
        for mid, manifest in read_manifests(self.env).items():
            name = manifest.get("PAKET_KLASOR_MODUL", "")
            if not name:
                continue
            label = (manifest.get("PAKET_AD") or mid) + " klasör bildirimi"
            try:
                module = load_package_module(self.env, mid, name, "yazilan", label)
                reported = module.yazilan(dict(self.env))
                require_list = isinstance(reported, list) and all(isinstance(x, str) for x in reported)
                if not require_list:
                    raise ShareError("%s geçersiz; paylaşım değiştirilmedi." % label)
                paths.extend(reported)
            except ShareError:
                raise
            except (OSError, SettingsError, UnicodeError, ValueError, TypeError, KeyError, RecursionError) as err:
                raise ShareError("%s güvenli okunamadı; paylaşım değiştirilmedi." % label) from err
        return self.relative_folders(paths)

    def module_state(self):
        try:
            with open(self.env["MODULES_FILE"], encoding="utf-8") as stream:
                return next((line.rstrip().split("\t")[1] for line in stream
                             if line.startswith("paylasim\t")), "")
        except FileNotFoundError:
            return ""

    def tail_available(self):
        """DD-191 global gate: Settings → Caddy can close WebDAV on Tailscale."""
        from master_publications import config as publication_config
        from master_settings import SettingsError
        try:
            return bool(publication_config(self.env)["paylasim"]["tail"])
        except (SettingsError, ValueError, KeyError, TypeError) as err:
            raise ShareError("Caddy yayın kaydı okunamadı.") from err

    def public(self):
        data = self.read()
        result = []
        base = "http://%s:%s" % (self.env["TAILSCALE_IPV4"], self.env["SHARE_PORT"])
        wan = self.wan_info()
        state = self.module_state()
        tail_enabled = self.tail_available()
        for item in data["items"]:
            row = {k: item[k] for k in ("id", "path", "name", "username", "created", "changed")}
            row.update(type="dir", available=False, connections={}, urls={})
            try:
                fd = open_dir(data["root"], parts(item["path"]))
                try:
                    row["available"] = identity(fd) == item["identity"]
                finally:
                    os.close(fd)
            except (OSError, ShareError):
                pass
            for scope, saved in item["connections"].items():
                transport = tail_enabled if scope == "tailscale" else wan["available"]
                expired = bool(saved["expires"] and time.time() >= saved["expires"])
                if not row["available"]:
                    reason = "Klasör bulunamadı veya değiştirildi."
                elif state != "calisiyor":
                    reason = "WebDAV hizmeti çalışmıyor."
                elif not transport:
                    reason = "Ayarlar → Caddy bölümünde Tailscale erişimi kapalı." if scope == "tailscale" else wan["reason"]
                elif expired:
                    reason = "Süresi doldu; yeniden süre seçin."
                else:
                    reason = "Bağlantı kapalı." if not saved["enabled"] else ""
                url = ""
                if transport:
                    origin = base if scope == "tailscale" else (
                        "https://" + wan["domain"] + (":" + str(wan["port"]) if wan["port"] != 443 else "") if wan["mode"] == "https" else
                        "http://%s:%s" % (wan["address"], wan["port"]))
                    url = origin + "/s/" + item["id"] + "/"
                active = not reason
                row["connections"][scope] = dict(saved, expired=expired, available=bool(transport),
                                                  active=active, reason=reason, url=url)
                if active:
                    row["urls"][scope] = url
            row["url"] = next(iter(row["urls"].values()), "")
            result.append(row)
        return {"enabled": bool(state), "running": state == "calisiyor", "host": base,
                "items": result, "max": 32, "wan": wan, "tail_enabled": tail_enabled, "limits": dict(DEFAULT_LIMITS)}

    def wan_info(self):
        from master_https import config
        from master_settings import SettingsError
        try:
            cfg = config(self.env)
        except (SettingsError, ValueError, KeyError, TypeError) as err:
            raise ShareError("HTTPS yapılandırması okunamadı; WAN erişimi uygulanmadı.") from err
        address = self.env.get("WAN_IPV4", "")
        try:
            ip = ipaddress.IPv4Address(address)
            available = ip.is_global and not ip.is_multicast and not ip.is_reserved
        except ValueError:
            available = False
        available = available and bool(self.env.get("SHARE_WAN_BACKEND"))
        reason = "" if available else "WAN paylaşımı için sunucuya atanmış genel IPv4 ve güncel kurulum gerekli."
        # DD-182: the provider can take the address away; Caddy could then not bind it.
        if available and not assigned(address):
            available = False
            reason = "Sunucunun internet IPv4 adresi değişti (%s artık bu sunucuda değil); kurulumu yeniden çalıştırın." % address
        if cfg["mode"] == "off":
            available, reason = False, "İnternet paylaşımı kapalı. Ayarlar → Caddy bölümünde HTTPS alan adı kaydedin."
        elif available and cfg["mode"] == "http":
            # One WAN port for Caddy publications (contract §3.1): while a package or Konsol is
            # published over HTTPS (TCP 443), legacy plaintext WebDAV on SHARE_PORT stays closed.
            from master_publications import https_apps_enabled
            try:
                conflict = https_apps_enabled(self.env)
            except (SettingsError, ValueError, KeyError, TypeError) as err:
                raise ShareError("HTTPS yapılandırması okunamadı; WAN erişimi uygulanmadı.") from err
            if conflict:
                available = False
                reason = ("Bir uygulamanın veya Panel'in internet yayını açıkken WebDAV internet erişimi için HTTPS alan adı gerekir; "
                          "Ayarlar → Caddy bölümünde kaydedin.")
        return {"available": available, "address": address if available else "",
                **cfg, "reason": reason}

    def wan_active(self):
        wan = self.wan_info()
        if not wan["available"] or self.module_state() != "calisiyor":
            return False
        data = self.read()
        # TLS-ALPN issuance/renewal needs the HTTPS listener even with no active
        # folder. The WAN backend still authenticates and checks each folder.
        if wan["mode"] == "https":
            return True
        for item in data["items"]:
            policy = item["connections"]["wan"]
            if not policy["enabled"] or (policy["expires"] and time.time() >= policy["expires"]):
                continue
            try:
                fd = open_dir(data["root"], parts(item["path"]))
                try:
                    if identity(fd) == item["identity"]:
                        return True
                finally:
                    os.close(fd)
            except (OSError, ShareError):
                pass
        return False

    def validate_path(self, data, path, exclude=""):
        pp = parts(path)
        path = "/".join(pp)
        # DD-203: the base's own reserved names, every package's declared folders and what the
        # packages report they write into right now (a folder the user chose in the application).
        blocked = list(data["blocked"]) + list(data.get("protected", [])) + self.written_folders()
        for p in blocked:
            if path == p or path.startswith(p + "/") or p.startswith(path + "/"):
                raise ShareError("Bu klasör iç/geçici alan “%s” ile çakışıyor. Bu alanı içermeyen bir klasör seçin." % p)
        for item in data["items"]:
            p = item["path"]
            if item["id"] != exclude and (path == p or path.startswith(p + "/") or p.startswith(path + "/")):
                raise ShareError("Bu klasör mevcut paylaşım “%s” ile çakışıyor. Paylaşımların yolları iç içe olamaz." % p)
        fd = open_dir(data["root"], pp)
        try:
            return path, identity(fd)
        finally:
            os.close(fd)

    def change(self, action, request):
        if not isinstance(request, dict):
            raise ShareError("Geçersiz paylaşım işlemi.")
        if any(k in request for k in ("permission", "days", "expires", "networks", "paused", "ack_write")) or action == "pause":
            raise ShareError("Paylaşım ayarları bağlantı bazında değişti; sayfayı yenileyin.")
        allowed = {"id", "path", "username", "password", "connections", "ack_wan_http"} if action == "save" else {"id"}
        if set(request) - allowed:
            raise ShareError("Geçersiz paylaşım alanı.")
        with contextlib.ExitStack() as stack:
            # Same ordering as settings; no module lifecycle/installer race.
            for name in ("install.lock", "modul.lock", "paylasim.lock"):
                stream = stack.enter_context(open(os.path.join(self.env["RUNTIME_DIR"], name), "a"))
                try:
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise ShareError("Başka bir kurulum/ayar işlemi sürüyor; yeniden deneyin.")
            if os.path.exists(self.env["SETTINGS_PENDING_FILE"]):
                raise ShareError("Önce bekleyen ayar değişikliğini onaylayın veya geri alın.")
            if not self.module_state():
                raise ShareError("Yerleşik WebDAV kurulumu tamamlanmamış; kurulumu yeniden çalıştırın.")
            if os.path.exists(self.pending):
                raise ShareError("Önceki paylaşım işlemi kurtarılıyor; biraz sonra yeniden deneyin.")
            old = self.read()
            data = json.loads(json.dumps(old))
            items = data["items"]
            sid = request.get("id", "")
            item = next((i for i in items if i["id"] == sid), None)
            if sid and (not isinstance(sid, str) or not ID_RE.fullmatch(sid) or item is None):
                raise ShareError("Paylaşım bulunamadı.")
            if action == "save":
                if item is None and len(items) >= 32:
                    raise ShareError("En çok 32 bağımsız paylaşım oluşturulabilir.")
                user = request.get("username", item["username"] if item else "")
                if not isinstance(user, str) or not USER_RE.fullmatch(user):
                    raise ShareError("Kullanıcı adı 3–32 harf/rakam veya . _ - içermeli.")
                if any(i["username"].lower() == user.lower() and i["id"] != sid for i in items):
                    raise ShareError("Bu kullanıcı adı başka bir paylaşımda kullanılıyor.")
                password = request.get("password", "")
                if not isinstance(password, str) or len(password) > 256 or ":" in password or any(ord(c) < 32 for c in password):
                    raise ShareError("Parola geçersiz (en çok 256 karakter; kontrol karakteri ve : yok).")
                if (password or item is None) and len(password) < 8:
                    raise ShareError("Yeni parola en az 8 karakter olmalı.")
                now = int(time.time())
                # DD-193: a new folder starts on Tailscale only while that transport is published.
                connections = item["connections"] if item else {
                    scope: {"enabled": scope == "tailscale" and self.tail_available(), "permission": "ro",
                            "expires": now + 7 * 86400}
                    for scope in SCOPES}
                patches = request.get("connections", {})
                if (not isinstance(patches, dict) or set(patches) - set(SCOPES)
                        or ("connections" in request and not patches)):
                    raise ShareError("Geçersiz bağlantı seçimi.")
                for scope, patch in patches.items():
                    if (not isinstance(patch, dict) or not patch
                            or set(patch) - {"enabled", "permission", "days", "ack_write"}):
                        raise ShareError("Geçersiz bağlantı ayarı.")
                    policy = connections[scope]
                    enabled = patch.get("enabled", policy["enabled"])
                    permission = patch.get("permission", policy["permission"])
                    if type(enabled) is not bool or permission not in ("ro", "rw"):
                        raise ShareError("Geçersiz bağlantı izni.")
                    if permission == "rw" and "permission" in patch and patch.get("ack_write") is not True:
                        raise ShareError("Yazma izninin silmeyi de kapsadığını bu bağlantı için onaylayın.")
                    expires = policy["expires"]
                    if "days" in patch:
                        days = patch["days"]
                        if type(days) is not int or days not in (0, 1, 7, 30):
                            raise ShareError("Süre 1, 7, 30 gün veya süresiz olabilir.")
                        expires = now + days * 86400 if days else None
                    if scope == "tailscale" and enabled and not policy["enabled"] and not self.tail_available():
                        raise ShareError("Ayarlar → Caddy bölümünde WebDAV için Tailscale erişimi kapalı; önce orada açın.")
                    if scope == "wan" and enabled and not policy["enabled"]:
                        info = self.wan_info()
                        if not info["available"]:
                            raise ShareError(info["reason"])
                        if info["mode"] == "http" and request.get("ack_wan_http") is not True:
                            raise ShareError("WAN üzerinden HTTP'nin parola ve dosyaları şifrelemediğini onaylayın.")
                    connections[scope] = {"enabled": enabled, "permission": permission, "expires": expires}
                # List controls change only access/expiry; never rebind a replaced folder
                # or overwrite credentials from stale browser metadata.
                if item is None or "path" in request:
                    path, ident = self.validate_path(data, request.get("path"), sid)
                else:
                    path, ident = item["path"], item["identity"]
                if item is None:
                    item = {"id": secrets.token_hex(12), "created": now}
                    items.append(item)
                item.update(path=path, identity=ident, name=path.rsplit("/", 1)[-1], username=user,
                            connections=connections, changed=now)
                if password:
                    item["salt"], item["hash"] = password_hash(password)
            elif action == "remove" and item is not None:
                items.remove(item)
            else:
                raise ShareError("Geçersiz paylaşım işlemi.")
            atomic(self.pending, old)
            atomic(self.path, data)
            if self.module_state() == "calisiyor":
                try:
                    self.restart()
                    self.publish()
                except (subprocess.SubprocessError, OSError, ShareError):
                    atomic(self.path, old)
                    try:
                        self.restart()
                        self.publish()
                    except (subprocess.SubprocessError, OSError, ShareError):
                        raise ShareError("Önceki kayıt geri yüklendi ancak WebDAV başlamadı. Sunucuda master-paylasim günlüğünü kontrol edin.")
                    os.unlink(self.pending)
                    raise ShareError("Paylaşım/ağ ayarı uygulanamadı; önceki kayıt geri yüklendi.")
            os.unlink(self.pending)
            return self.public()

    def publish(self):
        """DAV, package and Konsol projections (DD-199). Caller owns install/module/share locks."""
        if not self.env.get("SHARE_WAN_BACKEND"):
            return  # Legacy fixture/installation without the new listener capability.
        e = self.env
        active = self.wan_active()
        target = os.path.join(e["CADDY_MODULES_DIR"], "paylasim-wan.caddy")
        marker = os.path.join(e["RUNTIME_DIR"], "share-network-applied.json")
        text = ""
        if active:
            from master_https import site
            text = site(e, self.wan_info())
        from master_publications import extra_sites, https_apps_active
        from master_settings import SettingsError, atomic as atomic_text, read_regular
        try:
            extras = extra_sites(e)
            apps_wan = https_apps_active(e)
            previous_extras = {}
            for name in extras:
                try:
                    previous_extras[name] = read_regular(os.path.join(e["CADDY_MODULES_DIR"], name))[0].decode()
                except FileNotFoundError:
                    previous_extras[name] = ""
        except (SettingsError, OSError, ValueError, KeyError) as err:
            raise ShareError("Caddy yayın kaydı uygulanamadı.") from err
        try:
            with open(target, encoding="utf-8") as stream:
                previous = stream.read()
        except FileNotFoundError:
            previous = ""
        signature = {"config": text, "wan": active, "extra": extras, "apps_wan": apps_wan}
        try:
            with open(marker, encoding="utf-8") as stream:
                applied = json.load(stream)
        except (OSError, ValueError):
            applied = None
        if previous == text and previous_extras == extras and applied == signature:
            return
        # Always remove the success marker first: interrupted reloads retry, even
        # when the disk projection already matches. Credential rollback is separate.
        with contextlib.suppress(FileNotFoundError):
            os.unlink(marker)
        def write_config(content):
            if not content:
                with contextlib.suppress(FileNotFoundError):
                    os.unlink(target)
                return
            fd, temp = tempfile.mkstemp(prefix=".share-wan-", dir=e["CADDY_MODULES_DIR"])
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                    os.fchmod(stream.fileno(), 0o644)
                os.replace(temp, target)
            finally:
                with contextlib.suppress(FileNotFoundError):
                    os.unlink(temp)
        env = dict(os.environ, TAILSCALE_IPV4=e["TAILSCALE_IPV4"], STATE_FILE=self.state)
        def write_extras(values):
            for name, content in values.items():
                path = os.path.join(e["CADDY_MODULES_DIR"], name)
                if content:
                    atomic_text(path, content, 0o644)
                else:
                    with contextlib.suppress(FileNotFoundError):
                        os.unlink(path)
        try:
            write_config(text)
            write_extras(extras)
            subprocess.run(["caddy", "validate", "--config", e["CADDYFILE"], "--adapter", "caddyfile"],
                           check=True, timeout=15, capture_output=True, env=env)
            # Apply restrictions before opening a listener; existing manual denials
            # stay ahead of the base permission. Caddy reload never opens panel ports.
            subprocess.run([os.path.join(e["SBIN_DIR"], "master-firewall")], check=True, timeout=30, capture_output=True, env=env)
            try:
                subprocess.run(["systemctl", "reload", "caddy"], check=True, timeout=30, capture_output=True)
            except subprocess.CalledProcessError:
                if subprocess.run(["systemctl", "is-active", "--quiet", "caddy"], timeout=10).returncode == 0:
                    raise
                # DD-182: Caddy is down, e.g. it could not bind a WAN address the provider
                # took away. Start it with this projection; the next guard run confirms it.
                subprocess.run(["systemctl", "reset-failed", "caddy"], timeout=10, capture_output=True)
                subprocess.run(["systemctl", "start", "--no-block", "caddy"], timeout=10, capture_output=True)
                return
            atomic(marker, signature)
        except (OSError, SettingsError, subprocess.SubprocessError):
            write_config(previous)
            write_extras(previous_extras)
            raise ShareError("WAN dinleyicisi/güvenlik duvarı uygulanamadı.")

    def guard(self):
        with contextlib.ExitStack() as stack:
            for name in ("install.lock", "modul.lock", "paylasim.lock"):
                stream = stack.enter_context(open(os.path.join(self.env["RUNTIME_DIR"], name), "a"))
                try:
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    return
            if os.path.exists(self.env["SETTINGS_PENDING_FILE"]):
                return
            if os.path.exists(self.pending):
                atomic(self.path, load(self.pending))
                if self.module_state() == "calisiyor":
                    self.restart()
                self.publish()
                os.unlink(self.pending)
            else:
                self.publish()

    def restart(self):
        # Explicit user changes must not exhaust the automatic crash restart limit.
        subprocess.run(["systemctl", "reset-failed", UNIT], check=True, timeout=10, capture_output=True)
        subprocess.run(["systemctl", "restart", UNIT], check=True, timeout=30, capture_output=True)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            conn = http.client.HTTPConnection("127.0.0.1", int(self.env["SHARE_PORT"]), timeout=1)
            try:
                conn.request("GET", "/")
                response = conn.getresponse()
                response.read()
                if response.status == 401:
                    return
            except (OSError, http.client.HTTPException):
                pass
            finally:
                conn.close()
            time.sleep(.1)
        raise ShareError("WebDAV yeniden başlatıldı ancak giriş kapısı yanıt vermiyor.")

    def prepare(self):
        if os.path.exists(self.pending):
            atomic(self.path, load(self.pending))
            if self.module_state() == "calisiyor":
                self.restart()
            os.unlink(self.pending)
        if not os.path.exists(self.path):
            atomic(self.path, self.initial())
        else:
            data = self.read()
            with open(self.path, encoding="utf-8") as stream:
                if json.load(stream) != data:
                    atomic(self.path, data)


def main():
    from master_settings import SettingsError
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", default=os.environ.get("STATE_FILE", "/etc/master-stack/state.env"))
    parser.add_argument("action", choices=("prepare", "status", "save", "pause", "remove", "publish", "guard", "wan-firewall"))
    args = parser.parse_args()
    try:
        manager = Manager(args.state)
        if args.action == "wan-firewall":
            # Published packages and Konsol (DD-195/199) share the HTTPS port with WebDAV and its budgets.
            https_apps = False
            if manager.env.get("SHARE_WAN_BACKEND"):
                from master_publications import https_apps_active
                https_apps = bool(https_apps_active(manager.env))
            print(int(manager.wan_active() or https_apps), WAN_SOCKET_PER_IP, WAN_SOCKET_TOTAL,
                  int(manager.env["SHARE_HTTPS_PORT"]) if https_apps else manager.wan_info()["port"])
            return
        if args.action in ("publish", "guard"):
            getattr(manager, args.action)()
            return
        if args.action == "prepare":
            manager.prepare()
            return
        result = manager.public() if args.action == "status" else manager.change(args.action, json.loads(sys.stdin.read(65537)))
        print(json.dumps(result, ensure_ascii=False))
    except (ShareError, SettingsError, OSError, ValueError, KeyError, TypeError, RecursionError) as err:
        print(json.dumps({"error": str(err) if isinstance(err, ShareError) else "Paylaşım kaydı işlenemedi; kurulumu kontrol edin."}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
