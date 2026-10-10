#!/usr/bin/env python3
"""Konsol settings transactions (DD-156), Python stdlib only.

The HTTP process only reads here. Mutations run in an independent systemd unit,
with JSON on stdin, and share the install/module locks. A permanent systemd
timer recovers incomplete transactions, including after a reboot. No shell input.
"""
import argparse
import base64
import contextlib
import copy
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import importlib.util
import secrets
import shlex
import stat
import subprocess
import sys
import time
import urllib.parse

LIMIT = 65536
# DD-181: the rollback timer runs only while a change is pending (apply starts it, an idle
# guard stops it under the locks); at boot it runs once to catch a pending change.
GUARD_TIMER = "master-settings-guard.timer"
# DD-182: a failing automatic rollback is retried after 15, 30, 60 and 120 s; after the
# fifth failure it is "stuck" and waits for the operator (retry or discard in Konsol).
ROLLBACK_ATTEMPTS = 5
ROLLBACK_BACKOFF = 15
CONFIRM_WORD = "onayla"
OFF = "# konsol-off: "
DEFAULT = {"firewall": [], "dns": {"disabled": [], "records": [], "forward": False, "servers": []}}
DOMAIN_RE = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"


class SettingsError(Exception):
    pass


class SettingsBusy(SettingsError):
    pass


def require(ok, message):
    if not ok:
        raise SettingsError(message)


def env_read(path):
    result = {}
    for line in Path(path).read_text().splitlines():
        key, sep, value = line.partition("=")
        if sep and re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            result[key] = value.strip('"')
    return result


def read_json(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return copy.deepcopy(default)
    except (ValueError, OSError, RecursionError) as err:
        raise SettingsError("Ayar kaydı okunamadı; üzerine yazılmadı.") from err


@contextlib.contextmanager
def parent_fd(path, create=False):
    # Servis kullanıcısının sahip olduğu profil dizinleri değişebilir; tüm yolu
    # O_NOFOLLOW ile açıp yazma boyunca dizin tanıtıcısını sabit tutuyoruz.
    path = Path(path)
    require(path.is_absolute() and ".." not in path.parts, "Ayar dosyasının yolu geçersiz.")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            if create:
                try:
                    os.mkdir(part, 0o755, dir_fd=fd)
                except FileExistsError:
                    pass
            new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = new
        yield fd, path.name
    finally:
        os.close(fd)


def read_regular(path, limit=1024 * 1024):
    with parent_fd(path) as (directory, name):
        with os.fdopen(os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory), "rb") as fh:
            info = os.fstat(fh.fileno())
            require(stat.S_ISREG(info.st_mode) and info.st_size <= limit, "Ayar dosyası geçersiz veya çok büyük.")
            data = fh.read(limit + 1)
            require(len(data) <= limit, "Ayar dosyası çok büyük.")
            return data, info


# DD-197/198: a package manifest (MODULES_DIR/<id>/paket.env) is parsed line by line with the
# engine's pattern and never executed. Malformed manifests are left out: no guessing.
MANIFEST_LINE_RE = re.compile(r'^(PAKET_[A-Z_]+)=(?:"([^"]*)"|([A-Za-z0-9_./@*: -]*))$')
MANIFEST_ID_RE = re.compile(r"^[a-z]{2,16}$")


def package_env(env, mid):
    """Package defaults plus supported durable choices outside the regenerated package directory."""
    base = env.get("MODULES_DIR", "")
    if not base or not MANIFEST_ID_RE.fullmatch(mid):
        return {}
    try:
        values = env_read(Path(base) / mid / (mid + ".env"))
    except (OSError, UnicodeError):
        return {}
    values.update(package_overrides(env, mid))
    return values


def package_override_path(env, mid):
    require(bool(MANIFEST_ID_RE.fullmatch(mid)), "Paket adı geçersiz.")
    directory = env.get("PACKAGE_OVERRIDES_DIR")
    if not directory:
        directory = str(Path(env["STATE_DIR"]) / "package-overrides") if env.get("STATE_DIR") else None
    return Path(directory) / (mid + ".env") if directory else None


def package_overrides(env, mid):
    """Private, data-only overrides. A package explicitly declares every writable key.

    Values never reach `source`/eval; the bounded KEY=value CLI is also safe to consume
    with `IFS='=' read` and printf -v. Unknown keys fail closed, including old overrides
    after a package changes its supported settings.
    """
    path = package_override_path(env, mid)
    if path is None:
        return {}
    try:
        raw, info = read_regular(path, 16384)
    except FileNotFoundError:
        return {}
    require(info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) & 0o077 == 0,
            "Paket ayar dosyası yalnız root tarafından okunabilir olmalı.")
    allowed = set(read_manifests(env).get(mid, {}).get("PAKET_AYAR_ANAHTARLAR", "").split())
    require(bool(allowed) and all(re.fullmatch(r"[A-Z][A-Z0-9_]*", key) for key in allowed),
            "Paket kalıcı ayarları desteklemiyor.")
    values = {}
    for line in raw.decode("ascii").splitlines():
        key, sep, value = line.partition("=")
        require(bool(sep) and key in allowed and key not in values and
                re.fullmatch(r"[A-Za-z0-9_./:@+-]{1,1024}", value) is not None,
                "Paket ayar dosyasında desteklenmeyen alan/değer var.")
        # A declared service listener remains valid even if its file was edited by hand.
        if key.endswith("_PORT"):
            require(value.isdecimal() and 1 <= int(value) <= 65535, "Paket portu geçersiz.")
        values[key] = value
    return values


_package_modules = {}


def load_package_module(env, mid, name, attr, label):
    """DD-199/203: a package's own Python module (yayin.py, klasorler.py), loaded from its rendered
    folder as data: regular file, no symlink, cached by mtime, no bytecode written next to it.
    It must expose the callable `attr`; any failure is a SettingsError under `label`."""
    require(bool(re.fullmatch(r"[a-z][a-z0-9_]{0,40}\.py", name or "")), "%s adı geçersiz." % label)
    path = Path(env["MODULES_DIR"]) / mid / name
    try:
        st = os.stat(path, follow_symlinks=False)
    except OSError as err:
        raise SettingsError("%s yok; kurulumu yeniden çalıştırın." % label) from err
    require(not os.path.islink(path) and stat.S_ISREG(st.st_mode), "%s okunamadı." % label)
    key = (str(path), st.st_mtime_ns, st.st_size)
    module = _package_modules.get(key)
    if module is None:
        spec = importlib.util.spec_from_file_location("magaza_%s_%s" % (mid, name[:-3]), path)
        module = importlib.util.module_from_spec(spec)
        before = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        try:
            spec.loader.exec_module(module)
        except Exception as err:  # the package's file is data for us
            raise SettingsError("%s yüklenemedi." % label) from err
        finally:
            sys.dont_write_bytecode = before
        require(callable(getattr(module, attr, None)), "%s eksik (%s)." % (label, attr))
        for old in [k for k in _package_modules if k[0] == str(path)]:
            del _package_modules[old]
        _package_modules[key] = module
    return module


def read_manifests(env, limit=65536):
    """{id: {PAKET_KEY: value}} for every rendered package folder with a readable manifest."""
    result = {}
    base = env.get("MODULES_DIR", "")
    if not base or not os.path.isdir(base):
        return result
    for name in sorted(os.listdir(base)):
        if not MANIFEST_ID_RE.fullmatch(name):
            continue
        try:
            raw, _ = read_regular(os.path.join(base, name, "paket.env"), limit)
        except (OSError, ValueError, SettingsError):
            continue
        values = {}
        for line in raw.decode("utf-8", "replace").splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            m = MANIFEST_LINE_RE.match(line)
            if not m:
                values = None
                break
            values[m.group(1)] = m.group(2) if m.group(2) is not None else (m.group(3) or "")
        if values is not None:
            result[name] = values
    return result


def atomic(path, content, mode=0o600, owner=None):
    path = Path(path)
    require(not path.is_symlink(), "Sembolik bağlantı hedefi reddedildi.")
    data = content.encode() if isinstance(content, str) else content
    try:
        if read_regular(path, max(16 * 1024 * 1024, len(data)))[0] == data:
            return
    except FileNotFoundError:
        pass
    with parent_fd(path, create=True) as (directory, name):
        tmp = ".konsol-" + secrets.token_hex(16)
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode, dir_fd=directory)
            with os.fdopen(fd, "wb") as fh:
                os.fchmod(fh.fileno(), mode)
                if owner is not None:
                    os.fchown(fh.fileno(), *owner)
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, name, src_dir_fd=directory, dst_dir_fd=directory)
            os.fsync(directory)
        finally:
            try:
                os.unlink(tmp, dir_fd=directory)
            except FileNotFoundError:
                pass


def save_json(path, value):
    atomic(path, json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")


def saved_domain(path):
    value = read_json(path, {}).get("domain", "")
    require(isinstance(value, str) and (not value or re.fullmatch(DOMAIN_RE, value)), "Kayıtlı yerel alan adı geçersiz.")
    return value


def run(argv, *, input=None, check=True, timeout=30, env=None):
    try:
        p = subprocess.run(argv, input=input, capture_output=True, text=True, timeout=timeout,
                           env=dict({"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C.UTF-8"}, **(env or {})))
    except (OSError, subprocess.TimeoutExpired) as err:
        raise SettingsError("Komut tamamlanamadı: " + Path(argv[0]).name) from err
    # Never copy command output into errors: a service may print credentials.
    require(not check or p.returncode == 0, "Doğrulama/uygulama başarısız: " + Path(argv[0]).name)
    return p


def boot_id():
    return Path("/proc/sys/kernel/random/boot_id").read_text().strip()


def tailnet_ports(env):
    """DD-172: host ingress allowlist; not a list of arbitrary open sockets.

    Keep Tailscale's own PeerAPI endpoints, discovered from Self, never peers.
    A daemon not yet ready must not prevent the WAN firewall from landing.
    The existing firewall watchdog notices changed endpoints via --check.
    """
    rows = []
    for key, proto, name in (("SSH_PUBLIC_PORT", "tcp", "SSH"),
                             ("CADDY_HTTP_PORT", "tcp", "Caddy"),
                             ("DNS_PORT", "tcp", "dnsmasq"),
                             ("DNS_PORT", "udp", "dnsmasq"),
                             ("SHARE_PORT", "tcp", "Paylaşım WebDAV")):
        port = int(env.get(key, 0))
        if 1 <= port <= 65535:
            # Caddy templates bind only TAILSCALE_IPV4, including folder WebDAV.
            families = (4,) if key in ("CADDY_HTTP_PORT", "SHARE_PORT") else (4, 6)
            rows.extend(dict(family=f, proto=proto, port=port, name=name) for f in families)
    try:
        status = json.loads(run(["tailscale", "status", "--json", "--peers=false"], timeout=3).stdout)
        own = status.get("Self") or {}
        addresses = {ipaddress.ip_address(x) for x in own.get("TailscaleIPs", [])}
        for value in own.get("PeerAPIURL", []) or []:
            url = urllib.parse.urlsplit(value)
            ip = ipaddress.ip_address(url.hostname)
            if (url.scheme == "http" and ip in addresses and url.port and
                    not url.username and not url.password and url.path in ("", "/") and
                    not url.query and not url.fragment):
                row = dict(family=ip.version, proto="tcp", port=url.port, name="Tailscale PeerAPI")
                if not any(all(r[k] == row[k] for k in ("family", "proto", "port")) for r in rows):
                    rows.append(row)
    except (SettingsError, ValueError, TypeError, AttributeError, RecursionError):
        # PeerAPI normally also has a userspace netstack path; never grant an
        # ephemeral port range or abort host protection on a failed status read.
        pass
    return rows


def dns_interface(value):
    """The managed interface-name grammar, shared with the read-only DNS view."""
    match = re.fullmatch(r"([^,\s]+),([^,/\s]+)(?:/([46]))?", value)
    if match is None:
        return None
    name, iface, family = match.groups()
    return {"name": name, "iface": iface, "family": int(family) if family else None}


class Manager:
    def __init__(self, state):
        self.state = str(state)
        self.e = env_read(state)
        self.config_path = Path(self.e["SETTINGS_FILE"])
        self.pending_path = Path(self.e["SETTINGS_PENDING_FILE"])
        self.dns_file = Path(self.e["SETTINGS_DNS_FILE"])

    def config(self):
        return read_json(self.config_path, DEFAULT)

    def pending(self):
        return read_json(self.pending_path, None)

    def current(self):
        p = self.pending()
        if p and p["boot"] == boot_id() and time.monotonic() < p["until"] and p["phase"] != "rollback":
            return p["candidate"]
        return self.config()

    def revision(self):
        h = hashlib.sha256(json.dumps(self.config(), sort_keys=True).encode())
        # Detect installer and module lifecycle changes too (DD-201/202: no package file is named
        # here; a package's own settings go through its API module and worker).
        for path in [Path(self.state), Path(self.e["MODULES_FILE"]), self.dns_file, *self.dns_paths(), *self.domain_paths()]:
            try:
                s = path.stat()
                h.update((str(path) + str(s.st_mtime_ns) + str(s.st_size)).encode())
            except FileNotFoundError:
                pass
        return h.hexdigest()

    @contextlib.contextmanager
    def locked(self):
        with contextlib.ExitStack() as stack:
            for name in ("install.lock", "modul.lock", "settings.lock", "state.lock"):
                path = Path(self.e["RUNTIME_DIR"]) / name
                path.parent.mkdir(parents=True, exist_ok=True)
                f = stack.enter_context(open(path, "a"))
                try:
                    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as err:
                    raise SettingsBusy("Kurulum/modül/ayar işlemi sürüyor; biraz sonra yeniden deneyin.") from err
            yield

    def dns_paths(self):
        directory = Path(self.e["DNSMASQ_CONF_DIR"])
        return [Path(self.e["DNSMASQ_CONF_FILE"]), *sorted(directory.glob("modul-*.conf"))]

    def dns_names(self):
        names = []
        for path in self.dns_paths():
            if not path.exists():
                continue
            source = path.stem.removeprefix("modul-") if path.name.startswith("modul-") else "base"
            for line in path.read_text().splitlines():
                line = line.removeprefix(OFF)
                if line.startswith("interface-name="):
                    record = dns_interface(line.partition("=")[2])
                    if record:
                        target = "tailscale" if record["family"] != 6 else self.e.get("TAILSCALE_IPV6", "")
                        names.append({**record, "target": target, "source": source})
        return names

    def validate(self, data):
        require(isinstance(data, dict) and set(data) <= {"revision", "firewall", "dns", "domain", "https", "web"}, "Bilinmeyen ayar alanı.")
        require(data.get("revision") == self.revision(), "Ayarlar değişmiş. Yenileyip yeniden inceleyin.")
        c = self.config()
        if "web" in data:
            import master_publications
            require(set(data) == {"revision", "web"}, "Caddy yayınını diğer ayarlardan ayrı kaydedin.")
            require(not Path(self.e["SHARE_STATE_FILE"] + ".pending").exists(), "Önceki paylaşım işlemi kurtarılıyor.")
            c = master_publications.validate(self.e, c, data["web"])
        if "https" in data:
            import master_https
            require(set(data) == {"revision", "https"}, "HTTPS alan adını diğer ayarlardan ayrı kaydedin.")
            item = data["https"]
            require(isinstance(item, dict) and set(item) == {"domain"}, "HTTPS ayarı geçersiz.")
            c["https"] = {"domain": master_https.domain(item["domain"])}
            if "paylasim" in c.get("web", {}):
                c["web"]["paylasim"].update(domain=c["https"]["domain"], enabled=bool(c["https"]["domain"]))
            import master_publications
            master_publications.config(self.e, c)
            master_https.config(self.e, c)
            require(Path(self.e["CADDYFILE"]).is_file(), "Caddy yapılandırması bulunamadı.")
            require(not Path(self.e["SHARE_STATE_FILE"] + ".pending").exists(), "Önceki paylaşım işlemi kurtarılıyor.")
            if c["https"]["domain"]:
                master_https.check_dns(self.e, c["https"]["domain"])
        if "domain" in data:
            require(set(data) == {"revision", "domain"}, "Alan adını diğer ayarlardan ayrı güncelleyin.")
            domain = data["domain"]
            require(isinstance(domain, str) and re.fullmatch(DOMAIN_RE, domain),
                    "Yerel ad 1–63 küçük harf/rakam veya tire olmalı; nokta, boşluk ve adres öneki kullanmayın.")
            old = self.e["LOCAL_DOMAIN"]
            require(domain != old, "Yeni alan adı mevcut adla aynı.")
            c["domain"] = domain
            def rename(name):
                return name[:-len(old)] + domain if name.endswith("." + old) else name
            c["dns"]["disabled"] = [rename(n) for n in c["dns"]["disabled"]]
            for record in c["dns"]["records"]:
                record["name"] = rename(record["name"])
        if "firewall" in data:
            rules = data["firewall"]
            require(isinstance(rules, list) and len(rules) <= 100, "En çok 100 kullanıcı kuralı olabilir.")
            seen, selectors = set(), set()
            for r in rules:
                require(isinstance(r, dict) and set(r) == {"id", "name", "family", "scope", "proto", "port", "source", "allow"}, "Kural biçimi geçersiz.")
                require(isinstance(r["id"], str) and re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", r["id"]), "Kural kimliği geçersiz.")
                require(r["id"] not in seen, "Tekrar eden kural kimliği.")
                seen.add(r["id"])
                require(isinstance(r["name"], str) and 1 <= len(r["name"]) <= 64 and r["name"].isprintable(), "Kural adı geçersiz.")
                require(type(r["family"]) is int and r["family"] in (4, 6), "IPv4 veya IPv6 seçin.")
                require(r["scope"] in ("wan", "tail"), "Port kuralları yalnız İnternet ve Tailscale için düzenlenebilir.")
                require(r["proto"] in ("tcp", "udp") and type(r["port"]) is int and 1 <= r["port"] <= 65535, "Port/protokol geçersiz.")
                require(type(r["allow"]) is bool and isinstance(r["source"], str), "Kural eylemi/kaynağı geçersiz.")
                if r["source"]:
                    try:
                        src = ipaddress.ip_network(r["source"], strict=False)
                    except ValueError as err:
                        raise SettingsError("Kaynak IP/CIDR geçersiz.") from err
                    require(src.version == r["family"], "Kaynak adresinin IP ailesi uyuşmuyor.")
                    r["source"] = str(src)
                selector = (r["family"], r["scope"], r["proto"], r["port"], r["source"])
                require(selector not in selectors, "Aynı port/kaynak için iki kural olamaz.")
                selectors.add(selector)
            c["firewall"] = rules
        if "dns" in data:
            d = data["dns"]
            require(isinstance(d, dict) and set(d) == {"disabled", "records", "forward", "servers"}, "DNS biçimi geçersiz.")
            require(type(d["forward"]) is bool and isinstance(d["disabled"], list) and isinstance(d["records"], list)
                    and isinstance(d["servers"], list), "DNS alanları geçersiz.")
            require(len(d["records"]) <= 100 and len(d["disabled"]) <= 200 and len(d["servers"]) <= 4, "Çok fazla DNS kaydı.")
            known = {n["name"] for n in self.dns_names()}
            reserved = set(known)
            for path in Path(self.e["MODULES_DIR"]).glob("*/dnsmasq.conf"):
                for line in path.read_text().splitlines():
                    if line.startswith("interface-name="):
                        reserved.add(line.partition("=")[2].partition(",")[0])
            managed_names = set(reserved)
            for r in d["records"]:
                require(isinstance(r, dict) and set(r) == {"name", "target", "enabled"}, "DNS kaydı biçimi geçersiz.")
                name = r["name"]
                require(isinstance(name, str) and len(name) <= 253 and name.endswith("." + self.e["LOCAL_DOMAIN"])
                        and all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", x) for x in name.split(".")),
                        "Kayıt yerel alan içinde, geçerli küçük harfli bir ad olmalı.")
                require(name not in reserved, "Bu DNS adı zaten tanımlı ya da bir modüle ayrılmış.")
                reserved.add(name)
                require(type(r["enabled"]) is bool and isinstance(r["target"], str), "DNS hedefi geçersiz.")
                if r["target"] != "tailscale":
                    try:
                        addr = ipaddress.ip_address(r["target"])
                    except ValueError as err:
                        raise SettingsError("DNS hedefi IPv4/IPv6 olmalı.") from err
                    require(not (addr.is_unspecified or addr.is_multicast), "DNS hedefi geçersiz.")
                    r["target"] = str(addr)
            require(all(isinstance(n, str) and n in managed_names for n in d["disabled"]), "Bilinmeyen DNS adı kapatılamaz.")
            for server in d["servers"]:
                try:
                    addr = ipaddress.ip_address(server)
                except (ValueError, TypeError) as err:
                    raise SettingsError("Üst DNS, public IPv4/IPv6 adresi olmalı.") from err
                require(addr.is_global and not addr.is_multicast and str(addr) not in
                        {self.e.get(k, "") for k in ("WAN_IPV4", "WAN_IPV6", "TAILSCALE_IPV4", "TAILSCALE_IPV6")},
                        "Yerel/kendisine dönen DNS sunucusu kullanılamaz.")
            require(not d["forward"] or bool(d["servers"]), "Yönlendirme için DNS sunucusu seçin.")
            c["dns"] = d
        return c

    def safe_dir(self, value, writable=False):
        require(isinstance(value, str) and len(value) <= 1024 and bool(re.fullmatch(r"/[A-Za-z0-9_./ -]+", value)),
                "Dizin yolu geçersiz (harf/rakam, boşluk, . _ - / kullanılabilir).")
        path = Path(value)
        root = Path(self.e["SERVER_ROOT"])
        require(path.is_absolute() and ".." not in path.parts and path.is_dir() and str(path.resolve()) == str(path), "Dizin mevcut ve gerçek bir klasör olmalı; sembolik bağlantı kullanılamaz.")
        allowed = [Path(self.e["DOWNLOADS_PATH"]), root / self.e["MEDIA_SUBDIR"]]
        require(any(path == a or a in path.parents for a in allowed), "Yalnız indirmeler veya kütüphane altı seçilebilir.")
        require(not any(part.startswith(".") for part in path.relative_to(root).parts), "Gizli/paylaşım/çöp dizinleri kullanılamaz.")
        if writable:
            # Probe as the service user, never chown a user-selected tree as root.
            probe = "import os,sys,tempfile; f,p=tempfile.mkstemp(prefix='.konsol-test-',dir=sys.argv[1]); os.close(f); os.unlink(p)"
            run(["setpriv", "--reuid=" + self.e["DOWNLOADS_UID"], "--regid=" + self.e["DOWNLOADS_GID"],
                 "--clear-groups", "python3", "-c", probe, str(path)])
            s = os.statvfs(path)
            require(s.f_bavail * s.f_frsize > 0, "Seçilen diskte boş alan yok.")
        return path

    def folders(self, path=None):
        if path:
            root = self.safe_dir(path)
            dirs = [p for p in root.iterdir() if not p.is_symlink() and p.is_dir() and not p.name.startswith(".")]
        else:
            dirs = [Path(self.e["DOWNLOADS_PATH"]), Path(self.e["SERVER_ROOT"]) / self.e["MEDIA_SUBDIR"]]
        result = []
        for p in sorted(dirs)[:200]:
            try:
                self.safe_dir(str(p))
                s = os.statvfs(p)
                result.append({"path": str(p), "free": s.f_bavail * s.f_frsize})
            except (SettingsError, OSError):
                continue
        return result

    def filter_dns(self, text, config=None):
        disabled = (config or self.current())["dns"]["disabled"]
        lines = []
        for raw in text.splitlines():
            line = raw.removeprefix(OFF)
            name = line.partition("=")[2].partition(",")[0]
            lines.append(OFF + line if line.startswith("interface-name=") and name in disabled else line)
        return "\n".join(lines) + "\n"

    def project_dns(self, config=None):
        d = (config or self.current())["dns"]
        for path in self.dns_paths():
            if not path.exists():
                continue
            atomic(path, self.filter_dns(path.read_text(), config), 0o644)
        lines = ["# Konsol (DD-156); kalıcı kaynak SETTINGS_FILE."]
        for r in d["records"]:
            if r["enabled"]:
                lines.append("interface-name=" + r["name"] + "," + self.e["TAILSCALE_IF"] + "/4" if r["target"] == "tailscale"
                             else "host-record=" + r["name"] + "," + r["target"])
        if d["forward"]:
            lines += ["server=" + ip for ip in d["servers"]]
        # Base local=/DOMAIN/ + no-resolv remain authoritative, even for disabled names.
        atomic(self.dns_file, "\n".join(lines) + "\n", 0o644)

    def rules(self, family, wan=None):
        out = []
        for r in self.current()["firewall"]:
            if r["family"] != family or r["scope"] not in ("wan", "tail"):
                continue
            iface = (wan or self.e["WAN_INTERFACE"]) if r["scope"] == "wan" else self.e["TAILSCALE_IF"]
            require(bool(re.fullmatch(r"[A-Za-z0-9_.:-]{1,15}", iface)), "Arayüz adı geçersiz.")
            args = ["-i", iface, "-p", r["proto"], "--dport", str(r["port"])]
            if r["source"]:
                args += ["-s", r["source"]]
            # The core continues protecting loopback, established flows and IPv6 ICMP.
            args += ["-m", "comment", "--comment", "konsol:" + r["id"], "-j", "ACCEPT" if r["allow"] else "DROP"]
            out.append(args)
        return out

    def status(self):
        import master_https
        import master_publications
        p = self.pending()
        pending = None
        if p:
            pending = {"id": p["id"], "phase": p["phase"], "seconds": max(0, int(p["until"] - time.monotonic())) if p["boot"] == boot_id() else 0}
            if p.get("attempts"):
                pending.update(attempts=p["attempts"], error=p.get("error", ""))
                if p["phase"] == "rollback" and p.get("retry_boot") == boot_id():
                    pending["retry_in"] = max(0, int(p.get("retry_at", 0) - time.monotonic()))
            if p["changes"].get("domain"):
                pending["domain"] = {"old": p["old_domain"], "new": p["candidate"]["domain"]}
            if p["changes"].get("web"):
                pending["web"] = True
        return {"revision": self.revision(), "config": self.current(), "pending": pending,
                "names": self.dns_names(), "folders": self.folders(), "https": master_https.status(self.e),
                "publications": master_publications.status(self.e)}

    def snapshot(self, path):
        require(not path.is_symlink(), "Sembolik ayar dosyası reddedildi.")
        if not path.exists():
            return None
        data, info = read_regular(path)
        return {"data": base64.b64encode(data).decode(), "mode": stat.S_IMODE(info.st_mode), "uid": info.st_uid, "gid": info.st_gid}

    def restore(self, files):
        for name, record in files.items():
            path = Path(name)
            if record is None:
                path.unlink(missing_ok=True)
            else:
                atomic(path, base64.b64decode(record["data"]), record["mode"], (record["uid"], record["gid"]))

    def firewall_apply(self):
        run([self.e["SBIN_DIR"] + "/master-firewall"], timeout=40, env={"STATE_FILE": self.state})
        run([self.e["SBIN_DIR"] + "/master-firewall", "--check"], timeout=40, env={"STATE_FILE": self.state})

    def dns_test(self):
        helper = Path("/usr/share/dnsmasq/systemd-helper")
        run([str(helper), "checkconfig"] if helper.exists() else ["dnsmasq", "--test", "--conf-dir=" + self.e["DNSMASQ_CONF_DIR"]])

    def domain_paths(self):
        # Only installer-owned renderings; never touch credentials or download data.
        modules = Path(self.e["MODULES_DIR"])
        paths = [*modules.glob("*/dnsmasq.conf"), *modules.glob("*/*.caddy"),
                 modules / "dosya/master-files-panel.service",
                 Path(self.e["UNIT_DIR"]) / "master-files-panel.service",
                 Path(self.e["UNIT_DIR"]) / "master-sistem-dosya.service"]
        if self.e.get("CADDYFILE"):
            paths.append(Path(self.e["CADDYFILE"]))
        if self.e.get("CADDY_MODULES_DIR"):
            paths.extend(Path(self.e["CADDY_MODULES_DIR"]).glob("*.caddy"))
        return sorted({p for p in paths if p.exists()})

    def set_domain_state(self, domain):
        # refresh-tailnet shares state.lock. Restore ONLY the suffix, never old IPs.
        text, info = read_regular(self.state)
        text, count = re.subn(r"(?m)^LOCAL_DOMAIN=.*$", "LOCAL_DOMAIN=" + domain, text.decode())
        require(count == 1, "state.env alan adı kaydı geçersiz.")
        atomic(self.state, text, stat.S_IMODE(info.st_mode), (info.st_uid, info.st_gid))
        self.e = env_read(self.state)

    def caddy_test(self):
        run(["caddy", "validate", "--config", self.e["CADDYFILE"], "--adapter", "caddyfile"],
            env={"TAILSCALE_IPV4": self.e["TAILSCALE_IPV4"]})

    def domain_reload(self, files_active):
        self.dns_test()
        self.caddy_test()
        run(["systemctl", "daemon-reload"])
        if files_active:
            run(["systemctl", "restart", "master-files-panel.service"], timeout=20)
            run(["systemctl", "is-active", "--quiet", "master-files-panel.service"])
        # DD-235: the system view checks the Host name it was started with.
        if Path(self.e["UNIT_DIR"], "master-sistem-dosya.service").exists():
            run(["systemctl", "restart", "master-sistem-dosya.service"], timeout=20)
        run(["systemctl", "restart", "dnsmasq"], timeout=20)
        # Caddy's graceful reload keeps the in-flight apply response alive.
        run(["systemctl", "reload", "caddy.service"], timeout=20)

    def domain_apply(self, candidate):
        old, new = re.escape(self.e["LOCAL_DOMAIN"]), candidate["domain"]
        for path in [*self.dns_paths(), *self.domain_paths()]:
            if not path.exists():
                continue
            raw, info = read_regular(path)
            text = raw.decode()
            # Structured tokens only: no blanket replacement in paths/comments.
            patterns = [r"(?m)^((?:# konsol-off: )?interface-name=[^,\n]+\.)" + old + r"(?=,)",
                        r"(?m)^(local=/)" + old + r"(?=/$)",
                        r"(?m)^(http://[a-z0-9.-]+\.)" + old + r"(?=[:\s,{]|$)",
                        # DD-195: the shared Konsol routes name the backends' Host.
                        r"(?m)^(\t+header_up Host panel\.)" + old + r"$",
                        r"(--domain=)" + old + r"(?=\s|$)"]
            for pattern in patterns:
                text = re.sub(pattern, lambda m: m[1] + new, text)
            atomic(path, text, stat.S_IMODE(info.st_mode), (info.st_uid, info.st_gid))
        self.set_domain_state(new)
        self.project_dns(candidate)
        self.domain_reload(self.pending()["files_active"])

    def apply(self, data):
        require(not self.pending(), "Önce bekleyen işlemi onaylayın veya geri alın.")
        candidate = self.validate(data)
        change = {k: k in data for k in ("firewall", "dns", "domain", "https", "web")}
        require(any(change.values()), "Değişiklik yok.")
        dns_only = change["dns"] and not any(change[k] for k in ("firewall", "domain"))
        if change["dns"]:
            require("panel." + self.e["LOCAL_DOMAIN"] not in candidate["dns"]["disabled"],
                    "Panel erişimini korumak için Konsol'un kendi DNS adı kapatılamaz.")
        run(["systemctl", "start", GUARD_TIMER])
        run(["systemctl", "is-active", "--quiet", GUARD_TIMER])
        paths = [*self.dns_paths(), self.dns_file] if change["dns"] else []
        files_active = False
        manual_dns = False
        if change["web"]:
            import master_publications
            # Snapshot private projections too: a first-time row has no saved
            # web key for the publisher to reconstruct after a failed apply.
            paths += [Path(self.e["CADDY_MODULES_DIR"]) / (name + ".caddy")
                      for name in master_publications.module_ids(self.e)]
            # DD-252: a manual address also owns a tailnet DNS line; it is restored with the rest.
            manual_dns = data["web"]["service"].startswith(master_publications.MANUAL_PREFIX)
            if manual_dns:
                paths.append(Path(self.e["DNSMASQ_CONF_DIR"]) / master_publications.MANUAL_DNS)
        if change["domain"]:
            require(Path(self.e["CADDYFILE"]).is_file(), "Caddy yapılandırması bulunamadı.")
            paths += [*self.dns_paths(), self.dns_file, *self.domain_paths()]
            files_active = run(["systemctl", "is-active", "--quiet", "master-files-panel.service"], check=False).returncode == 0
        # Pending is durable BEFORE the first mutation, and the timer already runs.
        p = {"id": secrets.token_hex(16), "boot": boot_id(), "until": time.monotonic() + 180,
             "phase": "applying", "candidate": candidate, "changes": change,
             "files": {str(path): self.snapshot(path) for path in paths},
             "old_domain": self.e["LOCAL_DOMAIN"], "files_active": files_active, "manual_dns": manual_dns}
        save_json(self.pending_path, p)
        try:
            if change["web"]:
                row = data["web"]
                # A removed manual address has no row and nothing to certify.
                self.https_apply(candidate["web"][row["service"]]["domain"] if row.get("enabled") else None,
                                 row["service"])
                if manual_dns:
                    self.manual_dns_apply(candidate)
            if change["https"]:
                self.https_apply(candidate["https"]["domain"])
            if change["domain"]:
                self.domain_apply(candidate)
            if change["dns"]:
                self.project_dns(candidate)
                self.dns_test()
                run(["systemctl", "restart", "dnsmasq"], timeout=20)
            if change["firewall"]:
                self.firewall_apply()
            p = self.pending()
            require(p["until"] > time.monotonic(), "Uygulama zaman aşımına uğradı.")
            if dns_only or change["https"] or change["web"]:
                self.commit(p)
                return {"pending": None, "committed": True}
            p.update(phase="awaiting", until=time.monotonic() + (300 if change["domain"] else 60))
            save_json(self.pending_path, p)
        except Exception:
            self.rollback()
            raise
        return {"pending": self.status()["pending"]}

    def https_apply(self, name=None, service="paylasim"):
        import master_https
        import master_shares
        try:
            shares = master_shares.Manager(self.state)
            shares.publish()
            if name:
                # Without the listener the certificate wait can only time out after a
                # minute with a DNS/CAA hint; report the actual cause instead (DD-193).
                import master_publications
                packages = master_publications.packages(self.e)
                if service in packages:
                    require(master_publications.package_active(self.e, service),
                            "%s internet yayını açılamadı; uygulamanın çalıştığını, giriş ayarlarını ve WAN adresini kontrol edin."
                            % packages[service]["name"])
                elif service == "panel":
                    require(master_publications.panel_active(self.e),
                            "Panel internet yayını açılamadı; Konsol hesabını ve sunucunun WAN IPv4 adresini kontrol edin.")
                elif service.startswith(master_publications.MANUAL_PREFIX):
                    require(master_publications.manual_active(self.e, service),
                            "İnternet yayını açılamadı; sunucunun WAN IPv4 adresini kontrol edin.")
                elif not shares.wan_active():
                    raise SettingsError(shares.wan_info()["reason"] or
                                        "WAN HTTPS dinleyicisi açılamadı; paylaşım servisini ve WAN adresini kontrol edin.")
                master_https.wait_certificate(self.e, name)
        except master_shares.ShareError as err:
            raise SettingsError(str(err)) from err

    def manual_dns_apply(self, candidate):
        """DD-252: the tailnet names of manual addresses, under the DNS tab's off switches."""
        import master_publications
        path = Path(self.e["DNSMASQ_CONF_DIR"]) / master_publications.MANUAL_DNS
        text = master_publications.manual_dns(self.e, candidate)
        text = self.filter_dns(text, candidate) if text else ""
        before = path.read_text() if path.exists() else ""
        if text == before:
            return
        if text:
            atomic(path, text, 0o644)
        else:
            path.unlink(missing_ok=True)
        self.dns_test()
        run(["systemctl", "restart", "dnsmasq"], timeout=20)

    def confirm(self, data):
        p = self.pending()
        require(p and p["id"] == data.get("id") and p["phase"] == "awaiting" and p["boot"] == boot_id()
                and p["until"] > time.monotonic(), "Onay süresi dolmuş veya işlem artık geçerli değil.")
        # A fresh API request is necessary, but an established browser TCP connection
        # can survive a new-connection deny. Do not mistake that for connectivity.
        try:
            client = ipaddress.ip_address(data.get("client", ""))
        except ValueError as err:
            raise SettingsError("Yönetim istemcisinin adresi doğrulanamadı.") from err
        # DD-195: 100.64.0.0/10 is also carrier NAT space, so the Caddy site matters too:
        # a confirmation through the public Konsol address is refused.
        require((client in ipaddress.ip_network("100.64.0.0/10") or client in ipaddress.ip_network("fd7a:115c:a1e0::/48"))
                and data.get("kanal") == "tailscale", "Onay Tailscale üzerinden Konsol'dan gelmeli.")
        if p["changes"].get("domain"):
            require(data.get("host") == "panel." + p["candidate"]["domain"], "Alan adı değişikliğini yeni Konsol adresinden onaylayın.")
            self.dns_test()
            self.caddy_test()
        for proto, port in (("tcp", self.e["CADDY_HTTP_PORT"]), ("udp", self.e["DNS_PORT"]), ("tcp", self.e["DNS_PORT"])):
            for r in p["candidate"]["firewall"]:
                if (r["scope"] == "tail" and r["family"] == client.version and r["proto"] == proto and r["port"] == int(port)
                        and (not r["source"] or client in ipaddress.ip_network(r["source"]))):
                    require(r["allow"], "Bu kural yeni Konsol/DNS bağlantınızı engelliyor; geri alın veya sürenin dolmasını bekleyin.")
                    break
        require("panel." + self.e["LOCAL_DOMAIN"] not in p["candidate"]["dns"]["disabled"],
                "Konsol'un kendi DNS adı kapalıyken değişiklik kalıcılaştırılamaz.")
        # Recheck validators before committing.
        if p["changes"]["dns"]:
            self.dns_test()
        require(p["until"] > time.monotonic(), "Onay süresi doldu.")
        self.commit(p)
        return {"ok": True}

    def commit(self, p):
        committed = dict(p["candidate"], _transaction=p["id"])
        save_json(self.config_path, committed)
        # A crash after the commit is recognized by guard, rather than rolling back a committed change.
        p["phase"] = "committed"
        save_json(self.pending_path, p)
        self.pending_path.unlink()

    def rollback(self, manual=False):
        p = self.pending()
        if not p:
            return {"ok": True}
        if p["phase"] == "committed" or self.config().get("_transaction") == p["id"]:
            self.pending_path.unlink()
            return {"ok": True}
        if p["phase"] == "stuck" and not manual:
            return {"ok": True}  # DD-182: waits for the operator
        p["phase"] = "rollback"
        p["attempts"] = p.get("attempts", 0) + 1
        save_json(self.pending_path, p)
        try:
            self.rollback_steps(p)
        except (SettingsError, OSError, ValueError, KeyError, TypeError) as err:
            p["error"] = str(err) if isinstance(err, SettingsError) else "Geri alma adımı tamamlanamadı."
            if p["attempts"] >= ROLLBACK_ATTEMPTS:
                p["phase"] = "stuck"
            else:
                p.update(retry_at=time.monotonic() + ROLLBACK_BACKOFF * 2 ** (p["attempts"] - 1), retry_boot=boot_id())
            save_json(self.pending_path, p)
            raise
        self.pending_path.unlink()
        return {"ok": True}

    def rollback_steps(self, p):
        if p["changes"].get("web"):
            self.restore(p["files"])
        if p["changes"].get("https") or p["changes"].get("web"):
            self.https_apply()
        self.restore(p["files"])
        if p.get("manual_dns"):
            self.dns_test()
            run(["systemctl", "restart", "dnsmasq"], timeout=20)
        if p["changes"].get("domain"):
            self.set_domain_state(p["old_domain"])
            self.domain_reload(p["files_active"])
        if p["changes"]["dns"]:
            self.project_dns(self.config())
            self.dns_test()
            run(["systemctl", "restart", "dnsmasq"], timeout=20)
        if p["changes"]["firewall"]:
            self.firewall_apply()

    def discard(self, data):
        """DD-182: stop a stuck rollback. Files stay as they are now; the installer re-applies
        the saved (confirmed) settings. Only for "stuck", only with the typed word."""
        p = self.pending()
        require(p and p["id"] == data.get("id") and p["phase"] == "stuck", "Bırakılacak takılmış bir işlem yok.")
        require(str(data.get("confirm", "")).strip().lower() == CONFIRM_WORD, "Bırakmak için onayla yazın.")
        self.pending_path.unlink()
        return {"ok": True}

    def guard(self):
        p = self.pending()
        if not p or p["phase"] == "stuck":
            return {"ok": True}
        if p["phase"] == "rollback" and p.get("retry_boot") == boot_id() and p.get("retry_at", 0) > time.monotonic():
            return {"ok": True}  # DD-182: backoff between automatic attempts
        if p["phase"] in ("rollback", "committed") or p["boot"] != boot_id() or p["until"] <= time.monotonic():
            return self.rollback()
        return {"ok": True}


def guard_idle(p):
    """Nothing for the timer to do: no pending change, or a stuck rollback (DD-182)."""
    return not p or p["phase"] == "stuck"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", default=os.environ.get("STATE_FILE", "/etc/master-stack/state.env"))
    parser.add_argument("action", choices=("apply", "confirm", "rollback", "discard", "guard", "rules", "tailnet-ports", "project-dns", "filter-dns", "dns-enabled", "dns-forward", "pending", "status", "saved-domain", "package-overrides", "container-revision"))
    parser.add_argument("value", nargs="?")
    parser.add_argument("wan", nargs="?")
    args = parser.parse_args()
    try:
        if args.action == "saved-domain":
            print(saved_domain(args.value))
            return
        if args.action == "package-overrides":
            for key, value in sorted(package_overrides(env_read(args.state), args.value).items()):
                print(key + "=" + value)
            return
        if args.action == "container-revision":
            env = env_read(args.state)
            mid = args.value
            require(isinstance(mid, str) and bool(MANIFEST_ID_RE.fullmatch(mid)), "Paket adı geçersiz.")
            manifest = read_manifests(env).get(mid, {})
            adapter = load_package_module(env, mid, manifest.get("PAKET_KONTEYNER_YONETIM", ""),
                                          "container_config", "Konteyner paket ayarı")
            effective = dict(env, **package_env(env, mid))
            current = adapter.container_config(effective)
            require(isinstance(current, dict) and isinstance(current.get("revision"), str) and
                    isinstance(args.wan, str) and bool(args.wan) and current["revision"] == args.wan,
                    "Konteyner ayarları değişti; yenileyip yeniden deneyin.")
            return
        m = Manager(args.state)
        if args.action == "tailnet-ports":
            for row in tailnet_ports(m.e):
                print(row["family"], row["proto"], row["port"])
            return
        if args.action == "guard" and guard_idle(m.pending()):
            # Re-check under the locks: an apply holds them from starting the timer
            # until its pending file exists, so a timer stopped here is never needed.
            with m.locked():
                if guard_idle(m.pending()):
                    run(["systemctl", "stop", "--no-block", GUARD_TIMER], check=False)
                    return
        if args.action == "rules":
            for rule in m.rules(int(args.value), args.wan):
                print(shlex.join(rule))
            return
        if args.action == "project-dns":
            m.project_dns()
            return
        if args.action == "filter-dns":
            path = Path(args.value)
            atomic(path, m.filter_dns(path.read_text()), 0o644)
            return
        if args.action == "dns-enabled":
            sys.exit(0 if args.value not in m.current()["dns"]["disabled"] else 1)
        if args.action == "dns-forward":
            sys.exit(0 if m.current()["dns"]["forward"] else 1)
        if args.action == "pending":
            sys.exit(0 if m.pending() else 1)
        if args.action == "status":
            print(json.dumps(m.status(), ensure_ascii=False))
            return
        with m.locked():
            if args.action in ("apply", "confirm", "rollback", "discard"):
                raw = sys.stdin.read(LIMIT + 1)
                require(len(raw) <= LIMIT, "İstek çok büyük.")
                data = json.loads(raw)
                require(isinstance(data, dict), "İstek gövdesi JSON nesnesi olmalı.")
                if args.action == "rollback":
                    require(not m.pending() or m.pending()["id"] == data.get("id"), "Geri alınacak işlem artık geçerli değil.")
                    result = m.rollback(manual=True)
                else:
                    result = getattr(m, args.action)(data)
            else:
                result = getattr(m, args.action)()
        print(json.dumps(result, ensure_ascii=False))
    except (SettingsError, ValueError, KeyError, TypeError, OSError, RecursionError) as err:
        if args.action == "guard" and isinstance(err, SettingsBusy):
            return
        message = str(err) if isinstance(err, SettingsError) else "Ayar işlemi tamamlanamadı; sunucu yapılandırmasını denetleyin."
        print(json.dumps({"error": message}, ensure_ascii=False))
        if args.action == "guard":
            print(message, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    # Imported helpers must share this worker's exception classes. Loading a
    # second copy as master_settings made validation errors escape as tracebacks.
    sys.modules["master_settings"] = sys.modules[__name__]
    main()
