#!/usr/bin/env python3
"""qBittorrent package: settings worker (DD-202).

The Konsol root backend never edits the profile itself: its API module (api.py) runs this
file through ctx.worker() as a separate transient unit (outside the backend's sandbox, like
the base settings worker), JSON on stdin, JSON on stdout, exit 1 with {"error"} on refusal.

    ayar.py --state STATE hesap    {"username"?: str, "password"?: str}
    ayar.py --state STATE dizin    {"save": "/abs/dir"}
    ayar.py --state STATE ayar     {"username"?, "password"?, "save"?}  one stop/start for all
    ayar.py --state STATE kur-hazirla --tohum SEED   {"username", "password", "save"}
    ayar.py --state STATE kur-uygula --tohum SEED    (the engine, before the first start)
    ayar.py --state STATE kur-geri --tohum SEED      (the engine, when that install fails)

Every change is direct (DD-165): validate, stop the service if it runs, snapshot the files,
write, start again, verify; a failure restores the snapshot and starts the service again.
No pending/confirmation window: a wrong account or folder cannot lock the operator out.

DD-209: qBittorrent runs in a Podman container whose unit Podman's systemd generator writes from
the package's quadlet file. The profile is the container's /config (same files, same paths on the
host); a download folder outside the downloads tree is bind-mounted at the same path through the
quadlet drop-in <container>.container.d/90-konsol.conf, so the paths qBittorrent stores are host paths.

DD-210: the App Store install form. The base runs kur-hazirla before it starts the engine: the choices
are validated here and only the password's hash goes into a private seed file (0600, the base's runtime
folder); the engine's hook runs kur-uygula into the fresh or kept profile before the container's first
start and kur-geri when that install fails. The engine removes the seed at the end either way.
"""
import argparse
import base64
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import stat
import sys
import time


def _lib_dir():
    """The base's Python library (master_settings.py) sits next to master-modul (SBIN_DIR): the
    backend passes it as --lib; a hand run finds master-modul on PATH."""
    argv = sys.argv
    if "--lib" in argv[:-1]:
        return argv[argv.index("--lib") + 1]
    return os.path.dirname(shutil.which("master-modul") or "/usr/local/sbin/master-modul")


if "master_settings" not in sys.modules:  # standalone worker run; inside the backend it is loaded already
    sys.path.insert(0, _lib_dir())
import master_settings as settings  # noqa: E402

LIMIT = 65536
USERNAME_RE = re.compile(r"[A-Za-z0-9._@-]{1,64}")
PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))


def package_env(env):
    """The package's own settings (torrent.env next to this file, DD-203) on top of the base's state."""
    merged = dict(env)
    merged.update(settings.env_read(os.path.join(PACKAGE_DIR, "torrent.env")))
    merged.update(settings.package_overrides(env, "torrent"))
    return merged
CONF = "qBittorrent/qBittorrent.conf"
DROP_IN = "90-konsol.conf"
PORT_DROP_IN = "85-konteyner.conf"
CONTAINER_RE = re.compile(r"[a-z][a-z0-9-]{1,30}")
# A bind mount is "SRC:DST" in the quadlet; systemd expands % and splits on whitespace elsewhere.
MOUNTABLE_RE = re.compile(r"/[^\s:%\\\"']+")
STOP_TIMEOUT = 75   # the quadlet's StopTimeout (45 s) plus the container teardown
HASH_RE = re.compile(r"@ByteArray\([A-Za-z0-9+/]+={0,2}:[A-Za-z0-9+/]+={0,2}\)")
SEED_RE = re.compile(r"modul-[a-z]{2,16}\.kur")


class ContainerEditError(settings.SettingsError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def ini_values(text):
    section, out = "", {}
    for line in text.splitlines():
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
        elif "=" in line and not line.startswith(("#", ";")):
            k, _, v = line.partition("=")
            out[(section, k)] = v.strip('"').replace("\\\\", "\\")
    return out


def ini_patch(text, updates):
    """Change only selected keys, preserving unrelated qBittorrent settings."""
    remaining, section, out = dict(updates), "", []

    def finish():
        for (sec, key), value in list(remaining.items()):
            if sec == section:
                out.append(key + "=" + value)
                del remaining[(sec, key)]
    seen = set()
    for line in text.splitlines():
        if line.startswith("[") and line.endswith("]"):
            finish()
            section = line[1:-1]
        key = (section, line.partition("=")[0])
        if "=" in line and key in updates:
            if key not in seen:
                out.append(key[1] + "=" + updates[key])
                seen.add(key)
                remaining.pop(key, None)
        else:
            out.append(line)
    finish()
    for sec in dict.fromkeys(k[0] for k in remaining):
        out.extend(["", "[" + sec + "]"])
        out.extend(k + "=" + v for (s, k), v in remaining.items() if s == sec)
    return "\n".join(out) + "\n"


def password_hash(password):
    # qBittorrent Utils::Password::PBKDF2 (4.6/5.x): SHA512, 100000, salt16/key64.
    salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac("sha512", password.encode("utf-8"), salt, 100000, 64)
    return "@ByteArray(%s:%s)" % (base64.b64encode(salt).decode(), base64.b64encode(key).decode())


def conf_path(env):
    return Path(env["TORRENT_PROFILE_DIR"]) / CONF


def container_name(env):
    name = env.get("TORRENT_CONTAINER", "")
    settings.require(bool(CONTAINER_RE.fullmatch(name)), "Konteyner adı geçersiz.")
    return name


def drop_in_path(env):
    return Path(env["KONTEYNER_BIRIM_DIR"]) / (container_name(env) + ".container.d") / DROP_IN


def unit_name(env):
    return container_name(env) + ".service"


def wait_ui(env, seconds=40):
    """The container's unit is active before qBittorrent listens (its s6 init starts first); a change
    counts only once the interface answers on loopback, otherwise the previous settings return."""
    port = int(env.get("TORRENT_UI_PORT", "0") or 0)
    deadline = time.monotonic() + seconds
    while True:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=2):
                return
        except OSError:
            if time.monotonic() >= deadline:
                raise settings.SettingsError("qBittorrent arayüzü yeniden başlatmadan sonra açılmadı.")
            time.sleep(1)


def inside(path, root):
    if not path or not root:
        return False
    real, base = os.path.realpath(path), os.path.realpath(root)
    return real == base or real.startswith(base.rstrip("/") + "/")


def read_conf(path, limit=LIMIT):
    """The profile, read like the base reads any root file: regular, no-follow, bounded; None when unsafe."""
    try:
        raw, _ = settings.read_regular(path, limit)
        return raw.decode("utf-8", "replace")
    except (OSError, settings.SettingsError):
        return None


def durum(env):
    """Read-only view for the page: paths, interface, account name; never the password hash."""
    profile = env.get("TORRENT_PROFILE_DIR", "")
    text = read_conf(conf_path(env)) if profile else None
    if text is None:
        return {"error": "qBittorrent'in ayar dosyası okunamadı", "profile": profile}
    q = ini_values(text)
    downloads = env.get("DOWNLOADS_PATH", "")
    save = q.get(("BitTorrent", "Session\\DefaultSavePath")) or q.get(("Preferences", "Downloads\\SavePath"), "")
    temp = q.get(("BitTorrent", "Session\\TempPath")) or q.get(("Preferences", "Downloads\\TempPath"), "")
    port = q.get(("BitTorrent", "Session\\Port"), "")
    return {"profile": profile, "downloads": downloads, "save": save, "save_inside": inside(save, downloads),
            "temp": temp, "temp_on": q.get(("BitTorrent", "Session\\TempPathEnabled"), "").lower() == "true",
            "temp_inside": inside(temp, downloads),
            # DD-217: inside its bridge the interface listens on the container's address; the server
            # publishes it on loopback only, which is where it is reached.
            "ui": "127.0.0.1:%s" % q.get(("Preferences", "WebUI\\Port"), ""),
            "peer_port": int(port) if port.isdigit() else 0,
            "username": q.get(("Preferences", "WebUI\\Username"), "admin")}


def snapshot(path):
    settings.require(not path.is_symlink(), "Sembolik ayar dosyası reddedildi.")
    if not path.exists():
        return None
    data, info = settings.read_regular(path)
    return {"data": data, "mode": stat.S_IMODE(info.st_mode), "uid": info.st_uid, "gid": info.st_gid}


def restore(path, snap):
    if snap is None:
        if path.exists() and not path.is_symlink():
            path.unlink()
        return
    settings.atomic(path, snap["data"], snap["mode"], (snap["uid"], snap["gid"]))


def change(env, updates, drop_in=None):
    """Stop/snapshot/write/start; a failure restores the files and starts the service again.
    drop_in: None keeps the quadlet drop-in, "" removes it, text replaces it."""
    unit = unit_name(env)
    conf = conf_path(env)
    settings.require(conf.is_file() and not conf.is_symlink(), "qBittorrent kurulu değil.")
    active = settings.run(["systemctl", "is-active", "--quiet", unit], check=False).returncode == 0
    saved = {conf: None, drop_in_path(env): None}
    try:
        # Stop first: qBittorrent writes its settings back on shutdown.
        settings.run(["systemctl", "stop", unit], timeout=STOP_TIMEOUT)
        saved[conf] = snapshot(conf)
        if drop_in is not None:
            saved[drop_in_path(env)] = snapshot(drop_in_path(env))
            if drop_in:
                settings.atomic(drop_in_path(env), drop_in, 0o644)
            else:
                restore(drop_in_path(env), None)
            settings.run(["systemctl", "daemon-reload"])
        text = settings.read_regular(conf)[0].decode()
        settings.atomic(conf, ini_patch(text, updates), 0o640, (int(env["DOWNLOADS_UID"]), int(env["DOWNLOADS_GID"])))
        if active:
            settings.run(["systemctl", "start", unit], timeout=60)
            settings.run(["systemctl", "is-active", "--quiet", unit])
            wait_ui(env)
    except Exception:
        for path, snap in saved.items():
            if snap is not None or path.exists():
                restore(path, snap)
        if drop_in is not None:
            settings.run(["systemctl", "daemon-reload"], check=False)
        if active:
            settings.run(["systemctl", "start", unit], timeout=60, check=False)
        raise


def check_username(value):
    settings.require(isinstance(value, str) and USERNAME_RE.fullmatch(value), "Kullanıcı adı geçersiz (1–64 harf/rakam/._@-).")
    return value


def check_password(value):
    settings.require(isinstance(value, str) and 8 <= len(value) <= 256 and all(ord(x) >= 32 for x in value),
                     "Parola 8–256 karakter olmalı.")
    return value


def save_choice(env, value, state):
    """A download folder: the base's user-area policy (DD-202), then what a same-path bind mount can carry.
    Returns (path with a trailing slash, profile updates, drop-in text or "" for none)."""
    # The base owns the user-area policy (downloads/library only, no hidden/share/trash dirs,
    # writable by the service user); the package only asks it.
    path = str(settings.Manager(state).safe_dir(value, writable=True)).rstrip("/") + "/"
    return (path, *save_updates(env, path))


def save_updates(env, path):
    updates = {("BitTorrent", "Session\\DefaultSavePath"): '"' + path + '"',
               ("Preferences", "Downloads\\SavePath"): '"' + path + '"'}
    # The container sees the downloads tree; a folder outside it (the library) is one narrow extra
    # bind mount at the same path, so the stored path means the same inside and outside.
    folder = path.rstrip("/")
    if inside(folder, env.get("DOWNLOADS_PATH", "")):
        return updates, ""
    settings.require(bool(MOUNTABLE_RE.fullmatch(folder)),
                     "Bu klasör adı konteynere bağlanamaz (boşluk, ':' ya da '%' içeriyor); adını değiştirin ya da indirme klasöründen seçin.")
    return updates, "# Konsol: qBittorrent indirme dizini (DD-209)\n[Container]\nVolume=" + folder + ":" + folder + "\n"


def hesap(env, data):
    settings.require(isinstance(data, dict) and set(data) <= {"username", "password"} and bool(data), "Hesap alanı geçersiz.")
    updates = {}
    if "username" in data:
        updates[("Preferences", "WebUI\\Username")] = check_username(data["username"])
    if "password" in data:
        updates[("Preferences", "WebUI\\Password_PBKDF2")] = password_hash(check_password(data["password"]))
    change(env, updates)
    return {"ok": True, "username": durum(env).get("username", "")}


def dizin(env, data, state):
    settings.require(isinstance(data, dict) and set(data) == {"save"}, "Dizin alanı geçersiz.")
    path, updates, drop_in = save_choice(env, data["save"], state)
    change(env, updates, drop_in)
    return {"ok": True, "save": path}


def ayar(env, data, state):
    """DD-210: the overview's settings dialog. Every field is checked first, then one stop/write/start;
    an omitted (blank) password keeps the stored hash."""
    settings.require(isinstance(data, dict) and bool(data) and set(data) <= {"username", "password", "save"}, "Ayar alanı geçersiz.")
    updates, drop_in, path = {}, None, None
    if "username" in data:
        updates[("Preferences", "WebUI\\Username")] = check_username(data["username"])
    if "password" in data:
        updates[("Preferences", "WebUI\\Password_PBKDF2")] = password_hash(check_password(data["password"]))
    if "save" in data:
        path, more, drop_in = save_choice(env, data["save"], state)
        updates.update(more)
    change(env, updates, drop_in)
    view = durum(env)
    return {"ok": True, "username": view.get("username", ""), "save": view.get("save", "")}


def container_config(env):
    """Declared App Store adapter: safe effective settings and an opaque stale-edit revision.

    Account credentials and the profile contents never leave this interface. Their bytes
    participate in the revision so another application-settings edit invalidates the draft.
    """
    env = package_env(env)
    view = durum(env)
    settings.require("error" not in view, "qBittorrent ayarları okunamadı.")
    port = int(env["TORRENT_UI_PORT"])
    # DD-221: the peer port is the package's WAN publication; qBittorrent follows it at every start.
    config = {"listener_port": port, "peer_port": int(env["TORRENT_PEER_PORT"]), "save": view["save"]}
    digest = hashlib.sha256(json.dumps(config, sort_keys=True).encode())
    paths = [conf_path(env), drop_in_path(env), drop_in_path(env).with_name(PORT_DROP_IN)]
    override = settings.package_override_path(env, "torrent")
    if override is not None:
        paths.append(override)
    for path in paths:
        digest.update(str(path).encode() + b"\0")
        try:
            digest.update(settings.read_regular(path)[0])
        except FileNotFoundError:
            digest.update(b"missing")
    state = ""
    if env.get("MODULES_FILE"):
        try:
            state = next((line for line in settings.read_regular(env["MODULES_FILE"])[0].decode().splitlines()
                          if line.split("\t", 1)[0] == "torrent"), "")
        except FileNotFoundError:
            pass
    digest.update(state.encode())
    return {"config": config, "revision": digest.hexdigest(), "editable": ["listener_port", "peer_port", "save"],
            "protected_mounts": [{"source": env["TORRENT_PROFILE_DIR"], "target": "/config",
                                  "destination": "/config", "reason": "Uygulama profili; taşıma ayrı bir işlemdir."},
                                 {"source": env["DOWNLOADS_PATH"], "target": env["DOWNLOADS_PATH"],
                                  "destination": env["DOWNLOADS_PATH"], "reason": "Uygulamanın indirme kökü."}],
            "effective_autostart": state == "torrent\tcalisiyor"}


def project_ports(env, own, protocols):
    """Ports another project service holds: the base's and this package's other *_PORT values, other
    packages' declared ports and the saved Konsol container definitions (`protocols` of them)."""
    reserved = {int(v) for k, v in env.items() if k.endswith("_PORT") and k != own and str(v).isdigit()}
    for mid, manifest in settings.read_manifests(env).items():
        if mid == "torrent":
            continue
        package = settings.package_env(env, mid)
        for entry in manifest.get("PAKET_PORTLAR", "").split(";"):
            key = entry.split(":", 1)[0]
            val = package.get(key, env.get(key, ""))
            if str(val).isdigit():
                reserved.add(int(val))
    if env.get("KONTEYNER_STATE_DIR"):
        try:
            import master_container_config
            planned = master_container_config.Store(env).list()
            for definition in planned:
                reserved.update(row["host_port"] for row in definition.get("ports", [])
                                if row.get("protocol") in protocols)
        except Exception as err:
            raise ContainerEditError("Kaydedilmiş konteyner portları doğrulanamadı; değişiklik uygulanmadı.", 503) from err
    return reserved


def check_listener_port(env, value):
    settings.require(type(value) is int and 1024 <= value <= 65535, "Arayüz portu 1024–65535 arasında olmalı.")
    current = int(env["TORRENT_UI_PORT"])
    if value == current:
        return
    settings.require(value not in project_ports(env, "TORRENT_UI_PORT", ("tcp",)), "Bu port başka bir proje servisine ayrılmış.")
    # A host listener must be free on loopback, including a wildcard/dual-stack listener.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", value))
    except OSError as err:
        raise settings.SettingsError("Seçilen port kullanımda veya bağlanamıyor.") from err


def wan_address(env):
    value = env.get("WAN_IPV4", "")
    try:
        address = ipaddress.IPv4Address(value)
    except ValueError:
        address = None
    settings.require(address is not None and not (address.is_loopback or address.is_unspecified),
                     "Sunucunun WAN IPv4 adresi bilinmiyor; kurulumu yeniden çalıştırın.")
    return str(address)


def peer_probe(address, port):
    """The peer port is published for TCP and UDP on the WAN address; both must be bindable there."""
    for kind in (socket.SOCK_STREAM, socket.SOCK_DGRAM):
        try:
            with socket.socket(socket.AF_INET, kind) as probe:
                probe.bind((address, port))
        except OSError as err:
            raise settings.SettingsError("Seçilen eş portu sunucunun WAN adresinde kullanımda veya bağlanamıyor.") from err


def check_peer_port(env, value, listener):
    """DD-221: a new peer port is a WAN publication (TCP+UDP) like the old one; no other service may hold it."""
    settings.require(type(value) is int and 1024 <= value <= 65535, "Eş portu 1024–65535 arasında olmalı.")
    settings.require(value != listener, "Eş portu arayüz portundan farklı olmalı.")
    if value == int(env["TORRENT_PEER_PORT"]):
        return
    settings.require(value not in project_ports(env, "TORRENT_PEER_PORT", ("tcp", "udp")),
                     "Bu port başka bir proje servisine ayrılmış.")
    peer_probe(wan_address(env), value)


def container_publish(env, state):
    """Reproject WAN policy through its existing publisher; no new publication authority."""
    worker = Path(env["SBIN_DIR"]) / "master_shares.py"
    if worker.is_file():
        settings.run(["python3", str(worker), "--state", str(state), "publish"], timeout=90)


def container_guard(env, state):
    """DD-217/221: the base's forwarding guard lets through exactly what the placed Quadlet publishes."""
    worker = Path(env["SBIN_DIR"]) / "master_container_network.py"
    if worker.is_file():
        settings.run(["python3", str(worker), "--state", str(state), "apply"], timeout=60)


def konteyner_ayar(env, data, state):
    """Apply the declared listener, peer port and save directory under the caller's standard settings locks.

    Snapshots cover only files changed here. Failure restores configuration and previous
    service state, never claims to restore application data or a server installation.
    An omitted peer_port keeps the current one (DD-221).
    """
    settings.require(isinstance(data, dict) and set(data) == {"revision", "config"} and
                     isinstance(data["config"], dict) and
                     set(data["config"]) in ({"listener_port", "save"}, {"listener_port", "peer_port", "save"}),
                     "Konteyner ayar alanları geçersiz.")
    current = container_config(env)
    if not isinstance(data["revision"], str) or data["revision"] != current["revision"]:
        raise ContainerEditError("Ayarlar değişti; sayfayı yenileyip değişiklikleri yeniden gözden geçirin.", 409)
    config = data["config"]
    check_listener_port(env, config["listener_port"])
    peer_value = config.get("peer_port", int(env["TORRENT_PEER_PORT"]))
    check_peer_port(env, peer_value, config["listener_port"])
    path, updates, drop_in = save_choice(env, config["save"], state)
    port, peer = str(config["listener_port"]), str(peer_value)
    changed_port = port != str(env["TORRENT_UI_PORT"])
    changed_peer = peer != str(env["TORRENT_PEER_PORT"])
    if not changed_port and not changed_peer and path == current["config"]["save"]:
        return dict(current, ok=True)
    override = settings.package_override_path(env, "torrent")
    conf, drop = conf_path(env), drop_in_path(env)
    port_drop = drop.with_name(PORT_DROP_IN)
    caddy = Path(env["CADDY_MODULES_DIR"]) / "torrent.caddy"
    targets = [conf, drop]
    # DD-219/221: only a changed port becomes the operator's durable choice; a folder-only edit keeps
    # following the package's default (and leaves an earlier choice as it is).
    if changed_port or changed_peer:
        settings.require(override is not None, "Kalıcı paket ayar dizini yok; kurulumu yeniden çalıştırın.")
        chosen_overrides = dict(settings.package_overrides(env, "torrent"))
        if changed_port:
            chosen_overrides["TORRENT_UI_PORT"] = port
            targets.append(port_drop)
        if changed_peer:
            chosen_overrides["TORRENT_PEER_PORT"] = peer
        targets.append(override)
    caddy_text = None
    if changed_port and caddy.exists():
        text = settings.read_regular(caddy)[0].decode()
        caddy_text, count = re.subn(r"(\breverse_proxy[ \t]+127\.0\.0\.1:)\d+", lambda m: m[1] + port, text)
        settings.require(count == 1, "Uygulamanın Caddy upstream tanımı doğrulanamadı.")
        targets.append(caddy)
    # DD-217: the rendered and, while placed, the active Quadlet publish the interface on loopback and
    # the peer port on the WAN address; both are patched to what the next installer run renders.
    quadlet, _, placed = image_files(env)
    published = [quadlet] + ([placed] if placed.exists() else []) if changed_port or changed_peer else []
    targets.extend(published)
    # Readability/symlink failures are discovered before the running service is stopped.
    before = {target: snapshot(target) for target in targets}
    settings.require(before[conf] is not None, "qBittorrent kurulu değil.")
    settings.require(all(before[target] is not None for target in published), "Uygulamanın Quadlet dosyası okunamadı.")
    publish_text = {}
    for target in published:
        text = before[target]["data"].decode()
        if changed_port:
            text = patch_ui_publish(text, env["TORRENT_UI_PORT"], port)
        if changed_peer:
            text = patch_peer_publish(text, wan_address(env), env["TORRENT_PEER_PORT"], peer)
        publish_text[target] = text
    unit = unit_name(env)
    active = settings.run(["systemctl", "is-active", "--quiet", unit], check=False).returncode == 0
    touched, stop_attempted, started = [], False, False
    new_env = dict(env, TORRENT_UI_PORT=port, TORRENT_PEER_PORT=peer)
    caddy_env = {"TAILSCALE_IPV4": env.get("TAILSCALE_IPV4", "")}

    def write(target, content, mode=0o644, owner=None):
        touched.append(target)
        if content is None:
            restore(target, None)
        else:
            settings.atomic(target, content, mode, owner)

    try:
        if active:
            stop_attempted = True
            settings.run(["systemctl", "stop", unit], timeout=STOP_TIMEOUT)
            # qB persists native preferences during stop; preserve that most recent version.
            before[conf] = snapshot(conf)
        updates[("Preferences", "WebUI\\Port")] = port
        if changed_peer:
            updates[("BitTorrent", "Session\\Port")] = peer
        write(conf, ini_patch(before[conf]["data"].decode(), updates), 0o640,
              (int(env["DOWNLOADS_UID"]), int(env["DOWNLOADS_GID"])))
        write(drop, drop_in or None)
        if changed_port:
            write(port_drop, "# Konteynerler: uygulamanın etkin arayüz portu\n[Container]\nEnvironment=WEBUI_PORT=" + port + "\n")
        if changed_port or changed_peer:
            write(override, "".join(k + "=" + v + "\n" for k, v in sorted(chosen_overrides.items())), 0o600)
        for target, text in publish_text.items():
            write(target, text)
        if caddy_text is not None:
            write(caddy, caddy_text)
            settings.run(["caddy", "validate", "--config", env["CADDYFILE"], "--adapter", "caddyfile"], env=caddy_env)
        settings.run(["systemctl", "daemon-reload"])
        if changed_peer:
            # Before the start: the guard lets the new WAN publication through, the old one no longer.
            container_guard(new_env, state)
        if active:
            started = True
            settings.run(["systemctl", "start", unit], timeout=60)
            settings.run(["systemctl", "is-active", "--quiet", unit])
            wait_ui(new_env)
        if changed_port:
            container_publish(new_env, state)
            if caddy_text is not None:
                settings.run(["systemctl", "reload", "caddy"])
    except Exception as error:
        rollback_failed = False
        # A partially successful start can write the new profile on shutdown: stop first.
        if started:
            try:
                settings.run(["systemctl", "stop", unit], timeout=STOP_TIMEOUT)
            except settings.SettingsError:
                rollback_failed = True
        for target in reversed(touched):
            try:
                restore(target, before[target])
            except (OSError, settings.SettingsError):
                rollback_failed = True
        if touched:
            try:
                settings.run(["systemctl", "daemon-reload"])
            except settings.SettingsError:
                rollback_failed = True
        if changed_peer and touched:
            # As on the way in: the restored publication is let through before the app starts again.
            try:
                container_guard(env, state)
            except settings.SettingsError:
                rollback_failed = True
        if active and stop_attempted:
            try:
                settings.run(["systemctl", "start", unit], timeout=60)
                settings.run(["systemctl", "is-active", "--quiet", unit])
                wait_ui(env)
            except settings.SettingsError:
                rollback_failed = True
        if changed_port and touched:
            try:
                container_publish(env, state)
                if caddy_text is not None:
                    settings.run(["systemctl", "reload", "caddy"])
            except settings.SettingsError:
                rollback_failed = True
        if rollback_failed:
            raise ContainerEditError("Konteyner ayarı uygulanamadı; önceki yapılandırma/servis bütünüyle geri yüklenemedi. Servis durumunu denetleyin.", 503) from error
        raise ContainerEditError("Konteyner ayarı uygulanamadı; önceki yapılandırma ve servis durumu korundu.", 502) from error
    return dict(container_config(new_env), ok=True)


def _runner(argv, timeout):
    """master_containers' runner contract over the shared command helper: (rc, stdout, last stderr line)."""
    try:
        p = settings.run(argv, check=False, timeout=timeout)
    except settings.SettingsError:
        return 1, "", argv[0] + " çalıştırılamadı"
    lines = [line for line in p.stderr.splitlines() if line.strip()]
    return p.returncode, p.stdout, lines[-1] if lines else ""


def image_files(env):
    """DD-214: the files that name the pinned image. A Quadlet drop-in cannot replace Image= (the
    generator keeps the main file's value), so the rendered Quadlet, the rendered manifest and, while
    the app is placed, the active Quadlet are patched to exactly what the installer will render from
    the durable override on its next run."""
    name = container_name(env) + ".container"
    placed = Path(env["KONTEYNER_BIRIM_DIR"]) / name
    return Path(PACKAGE_DIR) / name, Path(PACKAGE_DIR) / "paket.env", placed


def patch_ui_publish(text, old, new):
    """DD-217: the interface is published on loopback only. Quadlet merges PublishPort lists from
    drop-ins instead of replacing them, so the single loopback line is patched like the image line."""
    pattern = r"^PublishPort=127\.0\.0\.1:%s:%s/tcp$" % (re.escape(str(old)), re.escape(str(old)))
    line = "PublishPort=127.0.0.1:%s:%s/tcp" % (new, new)
    result, count = re.subn(pattern, line, text, flags=re.M)
    settings.require(count == 1, "Arayüzün port satırı doğrulanamadı; kurulumu yeniden çalıştırın.")
    return result


def patch_peer_publish(text, wan, old, new):
    """DD-221: the peer port is published on the WAN address for TCP and UDP and handed to the image as
    TORRENTING_PORT; exactly those three places move together, as the installer would render them."""
    result = text
    for proto in ("tcp", "udp"):
        pattern = r"^PublishPort=%s:%s:%s/%s$" % (re.escape(wan), re.escape(str(old)), re.escape(str(old)), proto)
        result, count = re.subn(pattern, "PublishPort=%s:%s:%s/%s" % (wan, new, new, proto), result, flags=re.M)
        settings.require(count == 1, "Eş portunun yayın satırları doğrulanamadı; kurulumu yeniden çalıştırın.")
    pattern = r"^(Environment=(?:\S+ )*TORRENTING_PORT=)%s(?= |$)" % re.escape(str(old))
    result, count = re.subn(pattern, lambda m: m[1] + str(new), result, flags=re.M)
    settings.require(count == 1, "Eş portunun ortam değeri doğrulanamadı; kurulumu yeniden çalıştırın.")
    return result


def patch_image(text, old, new, manifest=False):
    pattern = r'^(PAKET_IMAJ=)"?' + re.escape(old) + r'"?$' if manifest else r"^(Image=)" + re.escape(old) + r"$"
    result, count = re.subn(pattern, lambda m: m[1] + ('"%s"' % new if manifest else new), text, flags=re.M)
    settings.require(count == 1, "İmaj satırı doğrulanamadı; kurulumu yeniden çalıştırın.")
    return result


def konteyner_guncelle(env, data, state):
    """DD-214: move the pinned image to what the update channel points to now, on explicit request.

    Pulls the exact new digest before touching the running service; restarts only a running app
    and verifies the interface and the container's image; any failure restores every file and the
    previous service state. The previous image is removed only after success.
    """
    import master_containers
    settings.require(isinstance(data, dict) and set(data) == {"revision"} and isinstance(data["revision"], str),
                     "Güncelleme alanları geçersiz.")
    current = container_config(env)
    if data["revision"] != current["revision"]:
        raise ContainerEditError("Ayarlar değişti; sayfayı yenileyip yeniden deneyin.", 409)
    channel = env.get("TORRENT_IMAGE_KANAL", "")
    settings.require(bool(channel) and "@" not in channel, "Bu uygulama için güncelleme kanalı tanımlı değil.")
    quadlet, manifest, placed = image_files(env)
    # The deployed Quadlet is the truth about the running image (the override only records it).
    lines = re.findall(r"^Image=(\S+)$", (snapshot(quadlet) or {"data": b""})["data"].decode(), re.M)
    settings.require(len(lines) == 1, "qBittorrent paketi bulunamadı; kurulumu yeniden çalıştırın.")
    old = lines[0]
    rc, arch, _ = _runner(["podman", "info", "--format", "{{.Host.Arch}}"], 20)
    settings.require(rc == 0 and bool(arch.strip()), "Podman yanıt vermedi.")
    status = master_containers.update_status(_runner, old, channel, arch.strip())
    if status["state"] == "guncel":
        return dict(current, ok=True, changed=False, image=old)
    if status["state"] != "var" or not status["candidate"]:
        raise ContainerEditError(status["error"] or "Güncelleme denetlenemedi.", 502)
    new = status["candidate"]
    override = settings.package_override_path(env, "torrent")
    settings.require(override is not None, "Kalıcı paket ayar dizini yok; kurulumu yeniden çalıştırın.")
    chosen = dict(settings.package_overrides(env, "torrent"), TORRENT_IMAGE=new)
    targets = [override, quadlet, manifest] + ([placed] if placed.exists() else [])
    before = {target: snapshot(target) for target in targets}
    settings.require(before[quadlet] is not None and before[manifest] is not None, "qBittorrent paketi bulunamadı; kurulumu yeniden çalıştırın.")
    texts = {override: "".join(k + "=" + v + "\n" for k, v in sorted(chosen.items())),
             quadlet: patch_image(before[quadlet]["data"].decode(), old, new),
             manifest: patch_image(before[manifest]["data"].decode(), old, new, manifest=True)}
    if placed in before:
        texts[placed] = patch_image(before[placed]["data"].decode(), old, new)
    # Every file was validated above; only now the exact digest is downloaded, before any service change.
    settings.run(["podman", "pull", "-q", new], timeout=600)
    unit = unit_name(env)
    active = settings.run(["systemctl", "is-active", "--quiet", unit], check=False).returncode == 0
    restarted = False
    try:
        for target in targets:
            settings.atomic(target, texts[target], 0o600 if target == override else before[target]["mode"] if before[target] else 0o644)
        settings.run(["systemctl", "daemon-reload"])
        if active:
            restarted = True
            settings.run(["systemctl", "restart", unit], timeout=STOP_TIMEOUT + 60)
            settings.run(["systemctl", "is-active", "--quiet", unit])
            wait_ui(env)
            image = settings.run(["podman", "inspect", "--format", "{{.ImageName}}", container_name(env)], timeout=20).stdout.strip()
            settings.require(image == new, "Konteyner yeni imajla açılmadı.")
    except Exception as error:
        rollback_failed = False
        for target in targets:
            try:
                restore(target, before[target])
            except (OSError, settings.SettingsError):
                rollback_failed = True
        try:
            settings.run(["systemctl", "daemon-reload"])
            if restarted:
                settings.run(["systemctl", "restart", unit], timeout=STOP_TIMEOUT + 60)
                settings.run(["systemctl", "is-active", "--quiet", unit])
                wait_ui(env)
        except settings.SettingsError:
            rollback_failed = True
        if rollback_failed:
            raise ContainerEditError("Güncelleme başarısız ve önceki imaj tam geri yüklenemedi; servis durumunu denetleyin.", 503) from error
        raise ContainerEditError("Güncelleme başarısız; önceki imaja dönüldü.", 502) from error
    # The old image goes only now and only if nothing else uses it (no force).
    rc, ident, _ = _runner(["podman", "image", "inspect", "--format", "{{.Id}}", old], 20)
    rc_new, ident_new, _ = _runner(["podman", "image", "inspect", "--format", "{{.Id}}", new], 20)
    if rc == 0 and re.fullmatch(r"[0-9a-f]{64}", ident.strip()) and ident.strip() != ident_new.strip():
        _runner(["podman", "rmi", ident.strip()], 60)
    _, version, _ = _runner(["podman", "image", "inspect", "--format", '{{index .Labels "org.opencontainers.image.version"}}', new], 20)
    return dict(container_config(dict(env, TORRENT_IMAGE=new)), ok=True, changed=True, image=new, previous=old,
                version=version.strip()[:80])


def seed_path(env, value):
    """The seed sits directly in the base's runtime folder under the engine's name for it."""
    path = Path(value)
    settings.require(SEED_RE.fullmatch(path.name) is not None and str(path.parent) == str(Path(env.get("RUNTIME_DIR", "/nonexistent"))),
                     "Kurulum bilgisi dosyası geçersiz.")
    return path


def kur_hazirla(env, data, state, seed):
    """DD-210: validate the install form and keep only the hash, before the engine starts."""
    path = seed_path(env, seed)
    settings.require(isinstance(data, dict) and set(data) == {"username", "password", "save"}, "Kurulum bilgileri eksik ya da geçersiz.")
    username = check_username(data["username"])
    check_password(data["password"])
    save, _, _ = save_choice(env, data["save"], state)
    seed_doc = {"username": username, "hash": password_hash(data["password"]), "save": save}
    settings.atomic(path, json.dumps(seed_doc) + "\n", 0o600)
    return {"ok": True, "username": username, "save": save}


def read_seed(path):
    raw, info = settings.read_regular(path, LIMIT)
    settings.require(info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) & 0o077 == 0, "Kurulum bilgisi dosyası korunmuyor.")
    doc = json.loads(raw.decode("utf-8"))
    settings.require(isinstance(doc, dict) and set(doc) == {"username", "hash", "save"}, "Kurulum bilgisi dosyası geçersiz.")
    check_username(doc["username"])
    settings.require(isinstance(doc["hash"], str) and HASH_RE.fullmatch(doc["hash"]) is not None
                     and isinstance(doc["save"], str) and doc["save"].startswith("/") and doc["save"].endswith("/")
                     and ".." not in doc["save"].split("/") and os.path.isdir(doc["save"]) and not os.path.islink(doc["save"].rstrip("/")),
                     "Kurulum bilgisi dosyası geçersiz.")
    return doc


def kur_uygula(env, seed):
    """DD-210: write the form's choices into the profile before the container first starts. The files as
    they were go next to the seed (private, removed with it) so kur-geri can put them back."""
    path = seed_path(env, seed)
    doc = read_seed(path)
    conf, drop = conf_path(env), drop_in_path(env)
    settings.require(conf.is_file() and not conf.is_symlink(), "qBittorrent profili hazır değil.")
    updates, drop_in = save_updates(env, doc["save"])
    # DD-217: on its own bridge the interface listens on the container's address; the host publishes
    # it on loopback only (a kept profile gets the same value).
    updates[("Preferences", "WebUI\\Address")] = "*"
    updates[("Preferences", "WebUI\\Username")] = doc["username"]
    updates[("Preferences", "WebUI\\Password_PBKDF2")] = doc["hash"]
    before = {"conf": snapshot(conf), "drop": snapshot(drop)}
    keep = {k: None if v is None else dict(v, data=base64.b64encode(v["data"]).decode()) for k, v in before.items()}
    settings.atomic(str(path) + ".onceki", json.dumps(keep) + "\n", 0o600)
    snap = before["conf"]
    settings.atomic(conf, ini_patch(snap["data"].decode(), updates), snap["mode"], (snap["uid"], snap["gid"]))
    if drop_in:
        settings.atomic(drop, drop_in, 0o644)
    else:
        restore(drop, None)
    return {"ok": True}


def kur_geri(env, seed):
    """DD-210: a failed install returns the profile and the drop-in to what they were before kur-uygula."""
    path = Path(str(seed_path(env, seed)) + ".onceki")
    try:
        raw, info = settings.read_regular(path, 4 * 1024 * 1024)
    except FileNotFoundError:
        return {"ok": True}
    settings.require(info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) & 0o077 == 0, "Kurulum yedeği korunmuyor.")
    keep = json.loads(raw.decode("utf-8"))
    for key, target in (("conf", conf_path(env)), ("drop", drop_in_path(env))):
        snap = keep.get(key)
        restore(target, None if snap is None else dict(snap, data=base64.b64decode(snap["data"])))
    return {"ok": True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", default=os.environ.get("STATE_FILE", "/etc/master-stack/state.env"))
    parser.add_argument("--lib", default=None, help=argparse.SUPPRESS)  # consumed above, before the import
    parser.add_argument("--tohum", default=None, help="DD-210: the engine's seed file for the install form")
    parser.add_argument("action", choices=("hesap", "dizin", "ayar", "durum", "konteyner-ayar", "konteyner-guncelle",
                                           "kur-hazirla", "kur-uygula", "kur-geri"))
    args = parser.parse_args()
    if args.action.startswith("kur-") and not args.tohum:
        parser.error("--tohum gerekli")
    try:
        env = package_env(settings.env_read(args.state))
        if args.action == "durum":
            print(json.dumps(durum(env), ensure_ascii=False))
            return
        # The engine runs these inside its own install, holding the locks already.
        if args.action in ("kur-uygula", "kur-geri"):
            result = (kur_uygula if args.action == "kur-uygula" else kur_geri)(env, args.tohum)
            print(json.dumps(result, ensure_ascii=False))
            return
        raw = sys.stdin.read(LIMIT + 1)
        settings.require(len(raw) <= LIMIT, "İstek çok büyük.")
        data = json.loads(raw)
        manager = settings.Manager(args.state)
        with manager.locked():
            if args.action in ("konteyner-ayar", "konteyner-guncelle") and manager.pending():
                raise ContainerEditError("Konsol'da onay bekleyen ayar var; önce onaylayın veya geri alın.", 409)
            if args.action == "kur-hazirla":
                result = kur_hazirla(env, data, args.state, args.tohum)
            elif args.action == "ayar":
                result = ayar(env, data, args.state)
            elif args.action == "konteyner-ayar":
                result = konteyner_ayar(env, data, args.state)
            elif args.action == "konteyner-guncelle":
                result = konteyner_guncelle(env, data, args.state)
            else:
                result = hesap(env, data) if args.action == "hesap" else dizin(env, data, args.state)
        print(json.dumps(result, ensure_ascii=False))
    except (settings.SettingsError, ValueError, KeyError, TypeError, OSError, RecursionError) as err:
        message = str(err) if isinstance(err, settings.SettingsError) else "qBittorrent ayarı uygulanamadı; önceki ayar geri yüklendi."
        result = {"error": message}
        if args.action in ("konteyner-ayar", "konteyner-guncelle"):
            result["status"] = getattr(err, "status", 409 if isinstance(err, settings.SettingsBusy) else
                                       400 if isinstance(err, (settings.SettingsError, ValueError, TypeError)) else 503)
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
