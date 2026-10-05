"""qBittorrent internet publication checks (DD-191, DD-199).

master_publications loads this file from the package folder when the operator turns the
qBittorrent row on, and again while the row is on. It reads qBittorrent.conf and never
writes it: the application's own permanent login, CSRF/Host checks and login-attempt ban
must be in place before Caddy forwards the public name to its loopback interface.
"""
import fnmatch
import http.client
from pathlib import Path

from master_settings import SettingsError, env_read, package_overrides, read_regular, require

PACKAGE_DIR = Path(__file__).resolve().parent


def package_env(env):
    """The package's own settings (torrent.env, DD-203) on top of the base's state."""
    merged = dict(env)
    merged.update(env_read(PACKAGE_DIR / "torrent.env"))
    merged.update(package_overrides(env, "torrent"))
    return merged


def ini_values(text):
    """qBittorrent's INI, section-qualified (DD-202: the base no longer carries this reader)."""
    section, out = "", {}
    for line in text.splitlines():
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
        elif "=" in line and not line.startswith(("#", ";")):
            k, _, v = line.partition("=")
            out[(section, k)] = v.strip('"').replace("\\\\", "\\")
    return out


def security(env, name, probe=False):
    """Fail closed if the native app permits bypass or has no permanent password."""
    env = package_env(env)
    path = Path(env["TORRENT_PROFILE_DIR"]) / "qBittorrent/qBittorrent.conf"
    q = ini_values(read_regular(path)[0].decode())

    def flag(key, default):
        return q.get(("Preferences", "WebUI\\" + key), default).lower()
    require(flag("LocalHostAuth", "true") == "true" and
            flag("AuthSubnetWhitelistEnabled", "false") == "false",
            "qBittorrent internet erişimi için giriş atlama seçenekleri kapalı olmalı.")
    require(bool(q.get(("Preferences", "WebUI\\Password_PBKDF2"))),
            "Önce qBittorrent için kalıcı kullanıcı parolası belirleyin.")
    require(flag("CSRFProtection", "true") == "true" and flag("HostHeaderValidation", "true") == "true",
            "qBittorrent CSRF ve Host koruması açık olmalı.")
    try:
        require(1 <= int(flag("MaxAuthenticationFailCount", "5")) <= 20 and
                int(flag("BanDuration", "3600")) >= 60, "qBittorrent parola denemesi sınırı etkin olmalı.")
    except ValueError as err:
        raise SettingsError("qBittorrent parola denemesi sınırı okunamadı.") from err
    domains = flag("ServerDomains", "*").replace(";", ",").split(",")
    require(any(fnmatch.fnmatchcase(name, part.strip()) for part in domains),
            "qBittorrent izinli sunucu adlarına bu alan adını ekleyin.")
    if probe:
        conn = http.client.HTTPConnection("127.0.0.1", int(env["TORRENT_UI_PORT"]), timeout=3)
        try:
            conn.request("GET", "/api/v2/app/version", headers={"Host": name, "X-Forwarded-Host": name})
            response = conn.getresponse()
            body = response.read(4096)
            require(response.status == 403 and b"banned" not in body.lower(),
                    "qBittorrent giriş kapısı doğrulanamadı; internet yayını açılmadı.")
        finally:
            conn.close()
