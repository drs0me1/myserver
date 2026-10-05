#!/usr/bin/env python3
"""Public WebDAV TLS: bounded DNS checks and a pinned, verified certificate probe.

The settings worker owns transactions; Caddy owns ACME keys and renewal. No
Cloudflare token, new daemon, DNS write or user-supplied connection target.
"""
import ipaddress
import json
import re
import socket
import ssl
import sys
import time

from master_settings import SettingsError, boot_id, read_json, require, run


def domain(value):
    require(isinstance(value, str), "HTTPS alan adı metin olmalı.")
    value = value.strip().lower().rstrip(".")
    if not value:
        return ""
    labels = value.split(".")
    require(len(value) <= 253 and len(labels) >= 2 and
            all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels)
            and re.fullmatch(r"[a-z]{2,63}|xn--[a-z0-9-]+", labels[-1]) and
            labels[-1] not in ("localhost", "local", "internal", "invalid", "test", "example", "onion"),
            "Tam internet alan adını yazın; https://, port, yol veya joker karakter eklemeyin.")
    return value


def settings(env, value=None):
    if value is None:
        value = read_json(env["SETTINGS_FILE"], {}) if env.get("SETTINGS_FILE") else {}
        pending = read_json(env["SETTINGS_PENDING_FILE"], None) if env.get("SETTINGS_PENDING_FILE") else None
        require(pending is None or isinstance(pending, dict), "Bekleyen HTTPS ayarı geçersiz.")
        if pending:
            require(isinstance(pending.get("changes"), dict) and
                    isinstance(pending.get("until"), (int, float)) and
                    isinstance(pending.get("candidate"), dict), "Bekleyen HTTPS ayarı geçersiz.")
        if (pending and (pending.get("changes", {}).get("https") or pending.get("changes", {}).get("web")) and pending.get("phase") in ("applying", "awaiting") and
                pending.get("boot") == boot_id() and pending.get("until", 0) > time.monotonic()):
            value = pending["candidate"]
    require(isinstance(value, dict), "HTTPS ayar kaydı okunamadı.")
    return value


def config(env, value=None):
    value = settings(env, value)
    web = value.get("web", {})
    require(isinstance(web, dict), "Caddy yayın kaydı geçersiz.")
    if "paylasim" in web:
        row = web["paylasim"]
        require(isinstance(row, dict) and set(row) == {"tail", "enabled", "domain"}
                and type(row["enabled"]) is bool and type(row["tail"]) is bool,
                "WebDAV yayın kaydı geçersiz.")
        name = domain(row["domain"])
        require(not row["enabled"] or bool(name), "HTTPS alan adı gerekli.")
        value = dict(value, https={"domain": name if row["enabled"] else ""})
    # Existing explicit HTTP opt-ins survive the upgrade. Once HTTPS has been
    # configured, clearing its domain closes WAN instead of exposing plaintext.
    if "https" not in value:
        return {"domain": "", "mode": "http", "scheme": "http", "port": int(env.get("SHARE_PORT", 0))}
    item = value["https"]
    require(isinstance(item, dict) and set(item) == {"domain"}, "HTTPS ayar kaydı geçersiz.")
    name = domain(item["domain"])
    port = int(env["SHARE_HTTPS_PORT"])
    require(1 <= port <= 65535 and port != int(env["SHARE_PORT"]), "HTTPS portu geçersiz.")
    return {"domain": name, "mode": "https" if name else "off", "scheme": "https" if name else "", "port": port}


def check_dns(env, name):
    # libc resolution can block without a deadline; isolate it in a short-lived
    # child and return addresses only. The validated hostname is argv, not code.
    ip = ipaddress.IPv4Address(env["WAN_IPV4"])
    require(ip.is_global and not ip.is_multicast, "HTTPS için sunucuya atanmış genel IPv4 gerekli.")
    probe = ("import json,socket,sys; print(json.dumps(sorted({r[4][0] for r in "
             "socket.getaddrinfo(sys.argv[1],None,socket.AF_UNSPEC,socket.SOCK_STREAM)})))")
    try:
        result = run([sys.executable, "-c", probe, name], timeout=8)
        addresses = {ipaddress.ip_address(v) for v in json.loads(result.stdout)}
    except (SettingsError, ValueError, TypeError) as err:
        raise SettingsError("Alan adı DNS üzerinden çözülemedi. A kaydını ve DNS yayılımını kontrol edin.") from err
    require(addresses == {ip}, "DNS yalnız %s adresine yönlenmeli. A kaydını DNS only yapın; bu adın AAAA kaydını kaldırın." % ip)


def certificate(env, name, timeout=2):
    # Never resolve/connect to the supplied hostname: connect only to the host's
    # assigned WAN IPv4, with name used for SNI and certificate verification.
    from master_shares import assigned
    address = str(ipaddress.IPv4Address(env["WAN_IPV4"]))
    require(ipaddress.ip_address(address).is_global and assigned(address), "WAN adresi bu sunucuda değil.")
    port = int(env["SHARE_HTTPS_PORT"])
    context = ssl.create_default_context()
    with socket.create_connection((address, port), timeout=timeout) as raw:
        with context.wrap_socket(raw, server_hostname=name) as secure:
            cert = secure.getpeercert()
    return int(ssl.cert_time_to_seconds(cert["notAfter"]))


def wait_certificate(env, name, seconds=60):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            return certificate(env, name, timeout=min(2, max(.1, deadline - time.monotonic())))
        except (OSError, ValueError, KeyError, SettingsError):
            time.sleep(min(1, max(0, deadline - time.monotonic())))
    raise SettingsError("HTTPS sertifikası doğrulanamadı. DNS, CAA ve internetten TCP 443 erişimini kontrol edin; önceki ayar geri alınıyor.")


def status(env):
    cfg = config(env)
    # In legacy HTTP mode "port" is SHARE_PORT; the UI still names the HTTPS port to open.
    result = dict(cfg, wan_ip=env.get("WAN_IPV4", ""), expires=None,
                  https_port=int(env.get("SHARE_HTTPS_PORT", 443)))
    if cfg["mode"] == "http":
        return dict(result, status="http", message="HTTPS alan adı tanımlanmadı. Mevcut WAN paylaşımları HTTP kullanıyor.")
    if cfg["mode"] == "off":
        return dict(result, status="disabled", message="İnternet paylaşımı kapalı.")
    try:
        expires = certificate(env, cfg["domain"])
        return dict(result, status="ready", message="Sertifika doğrulandı.", expires=expires)
    except (OSError, ValueError, KeyError, SettingsError):
        pending = read_json(env["SETTINGS_PENDING_FILE"], None) if env.get("SETTINGS_PENDING_FILE") else None
        if pending and pending.get("phase") == "applying" and (pending.get("changes", {}).get("https") or pending.get("changes", {}).get("web")):
            return dict(result, status="pending", message="Sertifika hazırlanıyor…")
        return dict(result, status="error", message="HTTPS sertifikası doğrulanamadı; Caddy ve DNS ayarlarını kontrol edin.")


def tls_block():
    return ("\ttls {\n\t\tissuer acme {\n"
           "\t\t\tdir https://acme-v02.api.letsencrypt.org/directory\n"
           "\t\t\tdisable_http_challenge\n\t\t}\n\t}\n")


def site(env, cfg):
    tls = tls_block() if cfg["mode"] == "https" else ""
    address = ("https://%s:%s" % (cfg["domain"], cfg["port"]) if tls else "http://:%s" % cfg["port"])
    return ("# Generated folder WAN endpoint; no console routes.\n%s {\n\tbind %s\n%s"
            "\t@share path /s/*\n\thandle @share {\n"
            "\t\treverse_proxy %s:%s {\n"
            "\t\t\theader_up X-Share-Client-IP {http.request.remote.host}\n"
            "\t\t\ttransport http {\n\t\t\t\tkeepalive off\n\t\t\t}\n"
            "\t\t}\n\t}\n\thandle {\n\t\trespond 404\n\t}\n}\n"
            % (address, env["WAN_IPV4"], tls, env["SHARE_WAN_BACKEND"], env["SHARE_PORT"]))
