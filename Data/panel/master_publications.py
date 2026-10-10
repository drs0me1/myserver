#!/usr/bin/env python3
"""Caddy publication catalogue from package declarations (DD-191, DD-195, DD-199, DD-252).

Settings owns transactions; the share publisher applies the projection under its
locks. The built-in WebDAV row and the Konsol (panel) row are fixed; package rows
come from a manifest with PAKET_YAYIN=1: a name, a local name, a loopback upstream
and an optional security module inside the package folder. DD-252 adds addresses the
operator enters in Settings → Caddy: a name, a local name and a port on this server's
loopback, guarded by the application's own login. No other upstreams or tunnels.
Application preferences are inspected, never rewritten.
"""
import argparse
import http.client
import ipaddress
import os
from pathlib import Path
import re
import socket
import sys

import master_https as tls
from master_settings import SettingsError, atomic, load_package_module, package_env, read_manifests, read_regular, require

BUILTIN_ID = "paylasim"
PANEL_ID = "panel"
UPSTREAM_RE = re.compile(r"^127\.0\.0\.1:[1-9][0-9]{0,4}$")
LOCAL_RE = re.compile(r"^[a-z][a-z0-9-]{0,30}$")
NAME_RE = re.compile(r"^[^\x00-\x1f]{1,40}$")
CHECK_RE = re.compile(r"^[a-z][a-z0-9_]{0,30}\.py$")
# DD-252: operator-entered addresses. The id carries the local name, which never changes;
# its files are CADDY_MODULES_DIR/elle-<local>.caddy (tailnet) and elle-<local>-wan.caddy (internet),
# and every tailnet name is one line of DNSMASQ_CONF_DIR/modul-elle.conf.
MANUAL_PREFIX = "elle-"
MANUAL_LIMIT = 16
MANUAL_DNS = "modul-elle.conf"
MANUAL_FIELDS = ("name", "local", "upstream")
# Konsol's own loopback backends have no login of their own (Files) or are already
# published with their checks (WebDAV); a manual address never puts one on a name.
RESERVED_PORT_KEYS = ("FILES_PANEL_PORT", "SHARE_PORT")


def packages(env):
    """Publishable packages from manifests: {id: {name, local, upstream, check, order}}, in catalogue order.
    A manifest that declares publication without a loopback upstream is left out: no guessing."""
    result = {}
    for mid, manifest in read_manifests(env).items():
        if manifest.get("PAKET_YAYIN") != "1" or manifest.get("PAKET_YERLESIK") == "1" or mid in (BUILTIN_ID, PANEL_ID):
            continue
        name = manifest.get("PAKET_YAYIN_AD", "")
        local = manifest.get("PAKET_YAYIN_YEREL", "")
        upstream = manifest.get("PAKET_YAYIN_UPSTREAM", "")
        port_key = manifest.get("PAKET_YAYIN_PORT_ANAHTARI", "")
        if port_key:
            if not UPSTREAM_RE.fullmatch(upstream) or not re.fullmatch(r"[A-Z][A-Z0-9_]*", port_key):
                continue
            port = package_env(env, mid).get(port_key, "")
            if not str(port).isdigit() or not 0 < int(port) < 65536:
                continue
            upstream = "127.0.0.1:%s" % int(port)
        check = manifest.get("PAKET_YAYIN_DENETIM", "")
        order = manifest.get("PAKET_SIRA", "50")
        if not (NAME_RE.match(name) and LOCAL_RE.match(local) and UPSTREAM_RE.match(upstream)
                and (not check or CHECK_RE.match(check)) and order.isdigit()):
            continue
        result[mid] = {"name": name, "local": local, "upstream": upstream, "check": check, "order": int(order)}
    return dict(sorted(result.items(), key=lambda item: (item[1]["order"], item[0])))


def manual(env, value=None):
    """Operator-entered addresses (DD-252): {id: {name, local, upstream}}, in local-name order."""
    value = tls.settings(env) if value is None else value
    items = value.get("elle", {})
    require(isinstance(items, dict) and len(items) <= MANUAL_LIMIT, "Elle adres kaydı geçersiz.")
    result = {}
    for mid, item in items.items():
        require(isinstance(item, dict) and set(item) == set(MANUAL_FIELDS)
                and all(isinstance(item[k], str) for k in MANUAL_FIELDS)
                and NAME_RE.fullmatch(item["name"]) and LOCAL_RE.fullmatch(item["local"])
                and mid == MANUAL_PREFIX + item["local"] and UPSTREAM_RE.fullmatch(item["upstream"])
                and int(item["upstream"].rpartition(":")[2]) < 65536, "Elle adres kaydı geçersiz.")
        result[mid] = dict(item)
    return dict(sorted(result.items()))


def manual_ids(rows):
    return [mid for mid in rows if mid.startswith(MANUAL_PREFIX)]


def module_ids(env):
    """Rows that own a private Caddy site file: the packages, then the built-in WebDAV."""
    return (*packages(env), BUILTIN_ID)


def ids(env):
    return module_ids(env) + (PANEL_ID,)


def config(env, value=None):
    value = tls.settings(env) if value is None else value
    web = value.get("web", {})
    require(isinstance(web, dict), "Caddy yayın kaydı geçersiz.")
    dav = tls.config(env, value)
    rows = {mid: {"tail": True, "enabled": False, "domain": ""} for mid in packages(env)}
    rows[BUILTIN_ID] = {"tail": True, "enabled": dav["mode"] != "off", "domain": dav["domain"]}
    rows[PANEL_ID] = {"tail": True, "enabled": False, "domain": ""}
    for mid in manual(env, value):
        rows[mid] = {"tail": True, "enabled": False, "domain": ""}
    for key, item in web.items():
        if key not in rows:
            continue  # a row saved for a package that no longer ships stays in the file, unused
        require(isinstance(item, dict) and set(item) == {"tail", "enabled", "domain"}
                and type(item["tail"]) is bool and type(item["enabled"]) is bool,
                "Caddy ağ seçimi geçersiz.")
        name = tls.domain(item["domain"])
        require(not item["enabled"] or bool(name), "İnternet yayını için HTTPS alan adı gerekli.")
        # The tailnet address is the management path that always remains.
        require(key != PANEL_ID or item["tail"], "Panel'in Tailscale erişimi kapatılamaz.")
        rows[key] = dict(item, domain=name)
    names = [r["domain"] for r in rows.values() if r["enabled"] and r["domain"]]
    require(len(names) == len(set(names)), "İki uygulama aynı HTTPS alan adını kullanamaz.")
    return rows


def https_apps_enabled(env, rows=None):
    """A saved application or Panel internet row: Caddy's one WAN port is then TCP 443 (v2-169)."""
    rows = config(env) if rows is None else rows
    return (any(rows[mid]["enabled"] for mid in packages(env)) or rows[PANEL_ID]["enabled"]
            or any(rows[mid]["enabled"] for mid in manual_ids(rows)))


def legacy_http_active(env):
    """Folders shared over the internet with plaintext HTTP right now (no HTTPS name saved)."""
    from master_shares import Manager, ShareError
    if tls.config(env)["mode"] != "http":
        return False
    try:
        return Manager.from_env(env).wan_active()
    except (ShareError, OSError, ValueError, KeyError):
        return False


LEGACY_HTTP_BUSY = ("WebDAV internet paylaşımı şu an eski HTTP ile açık. Önce WebDAV için HTTPS alan adı "
                    "kaydedin ya da o klasörlerin internet bağlantısını kapatın.")


def module_states(env):
    try:
        text = read_regular(env["MODULES_FILE"], 65536)[0].decode()
    except FileNotFoundError:
        return {}
    return {parts[0]: parts[1] for line in text.splitlines()
            if len(parts := line.split("\t")) == 2}


def security_module(env, mid, info):
    """The package's own check module (DD-199), through the base's package-module loader (DD-203)."""
    if not info["check"]:
        return None
    return load_package_module(env, mid, info["check"], "security", info["name"] + " yayın denetimi")


def security_check(env, mid, name, probe=False):
    """The package's native-login checks; raises SettingsError when the app would be exposed."""
    info = packages(env)[mid]
    module = security_module(env, mid, info)
    if module is not None:
        module.security(env, name, probe)


def wan_ready(env):
    from master_shares import assigned
    ip = ipaddress.IPv4Address(env["WAN_IPV4"])
    return ip.is_global and not ip.is_multicast and assigned(str(ip))


def package_active(env, mid, rows=None):
    """A package's public site exists only with its row on, the app running, an assigned WAN IPv4
    and its security checks passing."""
    try:
        rows = config(env) if rows is None else rows
        if mid not in rows or not rows[mid]["enabled"] or module_states(env).get(mid) != "calisiyor":
            return False
        if not wan_ready(env):
            return False
        security_check(env, mid, rows[mid]["domain"])
        return True
    except (SettingsError, OSError, ValueError, KeyError):
        return False


def konsol_account(env):
    """True only when the operator's Konsol account exists (DD-194)."""
    import master_auth
    try:
        return master_auth.Store(env["KONSOL_AUTH_DIR"]).account() is not None
    except (master_auth.AuthError, OSError, KeyError):
        return False


def panel_active(env, rows=None):
    """Public Konsol only with a saved name, an assigned WAN IPv4 and an existing account."""
    try:
        rows = config(env) if rows is None else rows
        return rows[PANEL_ID]["enabled"] and wan_ready(env) and konsol_account(env)
    except (SettingsError, OSError, ValueError, KeyError):
        return False


def manual_active(env, mid, rows=None):
    """A manual address's public site exists with its row on, a saved name and an assigned
    WAN IPv4. The application behind it keeps its own login (DD-252); nothing is probed."""
    try:
        rows = config(env) if rows is None else rows
        return (mid in rows and mid.startswith(MANUAL_PREFIX) and rows[mid]["enabled"]
                and bool(rows[mid]["domain"]) and wan_ready(env))
    except (SettingsError, OSError, ValueError, KeyError):
        return False


def https_apps_active(env, rows=None):
    """Names of the HTTPS publications active right now (packages, Konsol, then manual
    addresses); [] when none."""
    try:
        rows = config(env) if rows is None else rows
        items = manual(env)
    except (SettingsError, OSError, ValueError, KeyError):
        return []
    names = [info["name"] for mid, info in packages(env).items() if package_active(env, mid, rows)]
    if panel_active(env, rows):
        names.append("Konsol")
    names += [info["name"] for mid, info in items.items() if manual_active(env, mid, rows)]
    return names


def reserved_ports(env):
    """Loopback ports a manual address may not name: Konsol's own backends and every
    package publication's upstream (those keep their row and checks)."""
    ports = {int(env[key]) for key in RESERVED_PORT_KEYS if str(env.get(key, "")).isdigit()}
    ports |= {int(info["upstream"].rpartition(":")[2]) for info in packages(env).values()}
    return ports


def taken_names(env, saved):
    """Names other owners already answer in the local domain: the base and package DNS
    files, the operator's own DNS records and the fixed Caddy names."""
    domain = env["LOCAL_DOMAIN"]
    names = {"panel." + domain, "paylas." + domain}
    names |= {info["local"] + "." + domain for info in packages(env).values()}
    paths = [Path(env["DNSMASQ_CONF_FILE"])] if env.get("DNSMASQ_CONF_FILE") else []
    if env.get("DNSMASQ_CONF_DIR"):
        paths += [p for p in sorted(Path(env["DNSMASQ_CONF_DIR"]).glob("modul-*.conf")) if p.name != MANUAL_DNS]
    for path in paths:
        try:
            text = read_regular(path, 1 << 20)[0].decode()
        except FileNotFoundError:
            continue
        for line in text.splitlines():
            line = line.removeprefix("# konsol-off: ")
            if line.startswith("interface-name="):
                names.add(line.partition("=")[2].partition(",")[0])
    dns = saved.get("dns", {}) if isinstance(saved.get("dns", {}), dict) else {}
    names |= {r.get("name") for r in dns.get("records", []) if isinstance(r, dict)}
    return names


def validate_manual(env, saved, request):
    """Add, change or remove an operator-entered address (DD-252)."""
    service = request.get("service")
    require(isinstance(service, str) and service.startswith(MANUAL_PREFIX), "Bilinmeyen Caddy yayını.")
    items = manual(env, saved)
    if "sil" in request:
        require(set(request) == {"service", "sil"} and request["sil"] is True, "Caddy yayın alanları geçersiz.")
        require(service in items, "Elle adres bulunamadı.")
        saved["elle"] = {k: v for k, v in items.items() if k != service}
        saved.setdefault("web", {}).pop(service, None)
        return saved
    fields = {"service", "tail", "enabled", "domain"}
    require(fields <= set(request) <= fields | {"elle"}, "Caddy yayın alanları geçersiz.")
    if "elle" in request:
        item = request["elle"]
        require(isinstance(item, dict) and set(item) == set(MANUAL_FIELDS)
                and all(isinstance(item[k], str) for k in MANUAL_FIELDS), "Elle adres alanları geçersiz.")
        name, local, upstream = item["name"].strip(), item["local"].strip().lower(), item["upstream"].strip()
        require(bool(NAME_RE.fullmatch(name)), "Ad 1–40 karakter olmalı.")
        require(bool(LOCAL_RE.fullmatch(local)),
                "Tailscale adı küçük harfle başlamalı; yalnız küçük harf, rakam ve tire (en çok 31).")
        require(service == MANUAL_PREFIX + local, "Elle adresin Tailscale adı değiştirilemez; silip yeniden ekleyin.")
        require(bool(UPSTREAM_RE.fullmatch(upstream)) and int(upstream.rpartition(":")[2]) < 65536,
                "Hedef bu sunucuda bir port olmalı: 127.0.0.1:port.")
        require(int(upstream.rpartition(":")[2]) not in reserved_ports(env),
                "Bu port Konsol'un ya da bir uygulama yayınının kendi portu; elle adres olarak açılamaz.")
        if service not in items:
            require(len(items) < MANUAL_LIMIT, "En çok %d elle adres eklenebilir." % MANUAL_LIMIT)
            require(local + "." + env["LOCAL_DOMAIN"] not in taken_names(env, saved),
                    "%s.%s adı zaten kullanılıyor." % (local, env["LOCAL_DOMAIN"]))
        items[service] = {"name": name, "local": local, "upstream": upstream}
        saved["elle"] = items
    else:
        require(service in items, "Elle adres bulunamadı.")
    require(type(request["tail"]) is bool and type(request["enabled"]) is bool,
            "Ağ seçimleri açık veya kapalı olmalı.")
    gate = {"tail": request["tail"], "enabled": request["enabled"], "domain": tls.domain(request["domain"])}
    saved.setdefault("web", {})[service] = gate
    config(env, saved)  # one HTTPS name per enabled row, a name for an enabled row
    if gate["enabled"]:
        require(not legacy_http_active(env), LEGACY_HTTP_BUSY)
        tls.check_dns(env, gate["domain"])
    return saved


def validate(env, saved, request):
    if isinstance(request, dict) and isinstance(request.get("service"), str) and request["service"].startswith(MANUAL_PREFIX):
        return validate_manual(env, saved, request)
    fields = {"service", "tail", "enabled", "domain"}
    require(isinstance(request, dict) and fields <= set(request) <= fields | {"confirm"},
            "Caddy yayın alanları geçersiz.")
    service = request["service"]
    pkgs = packages(env)
    require(isinstance(service, str) and service in ids(env), "Bilinmeyen Caddy yayını.")
    require("confirm" not in request or service == PANEL_ID, "Caddy yayın alanları geçersiz.")
    before = config(env, saved)[service]
    require(type(request["tail"]) is bool and type(request["enabled"]) is bool,
            "Ağ seçimleri açık veya kapalı olmalı.")
    item = {k: request[k] for k in ("tail", "enabled", "domain")}
    item["domain"] = tls.domain(item["domain"])
    saved.setdefault("web", {})[service] = item
    # The old WebDAV-only endpoint remains a compatible writer; one row owns
    # the effective setting after migration, including its remembered off name.
    if service == BUILTIN_ID:
        saved.pop("https", None)
    rows = config(env, saved)
    if service == PANEL_ID:
        if item["enabled"]:
            # Publishing the console is the operator's typed decision, checked here too.
            if not before["enabled"] or before["domain"] != item["domain"]:
                require(request.get("confirm") == "onayla", "Panel'i internete açmak için onayla yazın.")
            # The first account is created only over Tailscale with the one-time code.
            require(konsol_account(env), "Önce Tailscale adresinden Ayarlar → Sistem → Konsol hesabı bölümünde internet hesabını oluşturun.")
            require(not legacy_http_active(env), LEGACY_HTTP_BUSY)
            tls.check_dns(env, item["domain"])
        return saved
    states = module_states(env)
    require(service in states, "Önce uygulamayı kurun.")
    if item["enabled"]:
        require(states.get(service) == "calisiyor", "Önce uygulamayı başlatın.")
        if service in pkgs:
            # Not WebDAV's mode: only folders actually shared over plaintext HTTP block the port.
            require(not legacy_http_active(env), LEGACY_HTTP_BUSY)
            try:
                security_check(env, service, rows[service]["domain"], probe=True)
            except (OSError, http.client.HTTPException) as err:
                raise SettingsError("%s giriş kapısı yanıt vermiyor." % pkgs[service]["name"]) from err
        tls.check_dns(env, item["domain"])
    return saved


def site_addresses(source):
    """Address line of a module's single site block (DD-193: the template is the source)."""
    for line in source.splitlines():
        if line.startswith(("http://", "https://")) and line.rstrip().endswith("{"):
            return line.rstrip()[:-1].strip()
    raise SettingsError("Uygulamanın Caddy site adresi okunamadı.")


def private_site(env, service, source):
    if config(env)[service]["tail"]:
        info = packages(env).get(service)
        declared = read_manifests(env).get(service, {}).get("PAKET_YAYIN_UPSTREAM", "")
        if info and UPSTREAM_RE.fullmatch(declared):
            source = re.sub(r"(\breverse_proxy[ \t]+)" + re.escape(declared) + r"(?=\s|$)",
                            lambda m: m.group(1) + info["upstream"], source)
        return source
    # A disabled route refuses requests on exactly the template's addresses,
    # including WebDAV by Tailscale IP:port for clients without DNS.
    return ("# Caddy Tailscale publication disabled; application remains running.\n%s {\n\trespond 403\n}\n"
            % site_addresses(source))


def package_site(env, mid, info, rows):
    """The package's public site: one name, TLS-ALPN, its loopback upstream, nothing else."""
    port = env["SHARE_HTTPS_PORT"]
    domain = rows[mid]["domain"]
    authority = domain + (":" + port if int(port) != 443 else "")
    # Native Host validation compares an explicit port with its loopback
    # listener. CSRF instead needs the external authority (including port).
    return ("# Managed public %s only; native authentication remains mandatory.\n"
            "https://%s:%s {\n\tbind %s\n%s"
            "\treverse_proxy %s {\n"
            "\t\theader_up Host %s\n"
            "\t\theader_up X-Forwarded-Host %s\n"
            "\t\theader_up X-Forwarded-For {http.request.remote.host}\n"
            "\t}\n}\n" % (info["name"], domain, port, env["WAN_IPV4"], tls.tls_block(), info["upstream"], domain, authority))


def manual_private_site(env, info):
    """The tailnet name of a manual address (default_bind is the Tailscale IPv4)."""
    return ("# Elle adres (DD-252): Tailscale; upstream on this server's loopback.\n"
            "http://%s.%s {\n\treverse_proxy %s\n}\n" % (info["local"], env["LOCAL_DOMAIN"], info["upstream"]))


def manual_public_site(env, info, domain):
    """The public name of a manual address: one name, TLS-ALPN, its loopback upstream.
    The application's own login is the guard (DD-252); the client address is Caddy's."""
    return ("# Elle adres (DD-252): internet; the application's own login remains the guard.\n"
            "https://%s:%s {\n\tbind %s\n%s"
            "\treverse_proxy %s {\n"
            "\t\theader_up X-Forwarded-For {http.request.remote.host}\n"
            "\t}\n}\n" % (domain, env["SHARE_HTTPS_PORT"], env["WAN_IPV4"], tls.tls_block(), info["upstream"]))


def manual_dns(env, value=None):
    """modul-elle.conf: one interface-name line per manual address open on the tailnet;
    "" when there is none (the file is then removed)."""
    rows, items = config(env, value), manual(env, value)
    lines = ["interface-name=%s.%s,%s/4" % (info["local"], env["LOCAL_DOMAIN"], env["TAILSCALE_IF"])
             for mid, info in items.items() if rows[mid]["tail"]]
    if not lines:
        return ""
    return "# Elle adresler (DD-252); kaynak Ayarlar → Caddy.\n" + "\n".join(lines) + "\n"


def panel_site(env, rows):
    # The snippet keeps backend Host checks and writes the channel the backend
    # trusts; no other route, upstream or module is reachable through this name.
    return ("# Managed public Konsol (DD-195): same sign-in and routes as the tailnet site.\n"
            "https://%s:%s {\n\tbind %s\n%s"
            "\theader Strict-Transport-Security \"max-age=31536000\"\n"
            "\timport konsol internet\n}\n"
            % (rows[PANEL_ID]["domain"], env["SHARE_HTTPS_PORT"], env["WAN_IPV4"], tls.tls_block()))


def extra_sites(env):
    rows, states, pkgs = config(env), module_states(env), packages(env)
    saved = tls.settings(env).get("web", {})
    result = {}
    for service in module_ids(env):
        # Unconfigured installations retain the original module projection.
        if service not in saved:
            continue
        if service not in states:
            result[service + ".caddy"] = ""
            continue
        source = Path(env["MODULES_DIR"]) / service / (service + ".caddy")
        result[service + ".caddy"] = private_site(env, service, read_regular(source)[0].decode())
    for mid, info in pkgs.items():
        result[mid + "-wan.caddy"] = package_site(env, mid, info, rows) if package_active(env, mid, rows) else ""
    result["panel-wan.caddy"] = panel_site(env, rows) if panel_active(env, rows) else ""
    items = manual(env)
    for mid, info in items.items():
        result[mid + ".caddy"] = manual_private_site(env, info) if rows[mid]["tail"] else ""
        result[mid + "-wan.caddy"] = manual_public_site(env, info, rows[mid]["domain"]) if manual_active(env, mid, rows) else ""
    # A public site left by a package that no longer ships, or the sites of a removed
    # manual address, are removed, never kept by accident.
    try:
        for name in os.listdir(env["CADDY_MODULES_DIR"]):
            stem = name[:-len("-wan.caddy")] if name.endswith("-wan.caddy") else ""
            if stem and stem not in pkgs and stem not in (BUILTIN_ID, PANEL_ID) and re.fullmatch(r"[a-z]{2,16}", stem):
                result.setdefault(name, "")
            base = name[:-len(".caddy")] if name.startswith(MANUAL_PREFIX) and name.endswith(".caddy") else ""
            if (base and base not in items and base.removesuffix("-wan") not in items
                    and re.fullmatch(re.escape(MANUAL_PREFIX) + r"[a-z][a-z0-9-]{0,34}", base)):
                result.setdefault(name, "")
    except (OSError, KeyError):
        pass
    return result


def status(env):
    rows, states, pkgs = config(env), module_states(env), packages(env)
    out = [panel_status(env, rows)]
    for mid, info in pkgs.items():
        row = dict(rows[mid], service=mid, name=info["name"], local=info["local"] + "." + env["LOCAL_DOMAIN"],
                   installed=mid in states, running=states.get(mid) == "calisiyor", expires=None,
                   status="disabled", message="İnternet yayını kapalı.")
        if row["enabled"]:
            row.update(status="error", message="%s yayını veya sertifikası doğrulanamadı." % info["name"])
            if not row["running"]:
                # Name the actual cause; a stopped app is not a certificate problem.
                row["message"] = ("%s kurulu değil; internet yayını kapalı." % info["name"] if not row["installed"] else
                                  "%s durdurulmuş; başlatıldığında internet yayını yeniden açılır." % info["name"])
            elif package_active(env, mid, rows):
                try:
                    row.update(expires=tls.certificate(env, row["domain"]), status="ready", message="Sertifika doğrulandı.")
                except (OSError, ValueError, KeyError, SettingsError):
                    pass
            else:
                try:
                    security_check(env, mid, row["domain"])
                except SettingsError as err:
                    row["message"] = str(err)
                except (OSError, ValueError, KeyError):
                    pass
        out.append(row)
    out += manual_status(env, rows)
    row = dict(rows[BUILTIN_ID], service=BUILTIN_ID, name="WebDAV", local="paylas." + env["LOCAL_DOMAIN"],
               installed=BUILTIN_ID in states, running=states.get(BUILTIN_ID) == "calisiyor", expires=None,
               status="disabled", message="İnternet yayını kapalı.")
    info = tls.status(env)
    row.update({k: info[k] for k in ("status", "message", "expires", "mode")})
    row["wan_active"] = legacy_http_active(env) if info["mode"] == "http" else None
    if info["mode"] == "http" and https_apps_enabled(env, rows):
        row["message"] = ("HTTPS alan adı tanımlanmadı. Bir uygulamanın veya Panel'in internet yayını açıkken "
                          "WebDAV internet erişimi için HTTPS alan adı gerekir.")
    out.append(row)
    return out


def upstream_answers(upstream, timeout=0.3):
    """Whether something listens on the manual address's loopback port (status only)."""
    host, _, port = upstream.rpartition(":")
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def manual_status(env, rows):
    out = []
    for mid, info in manual(env).items():
        row = dict(rows[mid], service=mid, name=info["name"], local=info["local"] + "." + env["LOCAL_DOMAIN"],
                   manual=True, upstream=info["upstream"], installed=True, running=True, expires=None,
                   status="disabled", message="İnternet yayını kapalı.")
        if row["enabled"]:
            row.update(status="error", message="%s yayını veya sertifikası doğrulanamadı." % info["name"])
            if manual_active(env, mid, rows):
                try:
                    row.update(expires=tls.certificate(env, row["domain"]), status="ready", message="Sertifika doğrulandı.")
                except (OSError, ValueError, KeyError, SettingsError):
                    pass
            else:
                row["message"] = "Sunucunun internet IPv4 adresi kullanılamıyor; internet yayını kapalı."
        if not upstream_answers(info["upstream"]):
            row["message"] = "Hedef %s yanıt vermiyor; uygulamanın çalıştığını ve portunu kontrol edin. %s" % (
                info["upstream"], row["message"])
        out.append(row)
    return out


def panel_status(env, rows):
    row = dict(rows[PANEL_ID], service=PANEL_ID, name="Panel", local="panel." + env["LOCAL_DOMAIN"],
               installed=True, running=True, expires=None, account=konsol_account(env),
               status="disabled", message="İnternet yayını kapalı. Tailscale adresi her zaman açık kalır.")
    if not row["enabled"]:
        return row
    row.update(status="error", message="Panel yayını veya sertifikası doğrulanamadı.")
    if not row["account"]:
        row["message"] = "Konsol hesabı yok; internet yayını kapalı. Hesabı Tailscale adresinden Ayarlar → Sistem → Konsol hesabı bölümünde oluşturun."
    elif panel_active(env, rows):
        try:
            row.update(expires=tls.certificate(env, row["domain"]), status="ready", message="Sertifika doğrulandı.")
        except (OSError, ValueError, KeyError, SettingsError):
            pass
    else:
        row["message"] = "Sunucunun internet IPv4 adresi kullanılamıyor; internet yayını kapalı."
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", default="/etc/master-stack/state.env")
    parser.add_argument("action", choices=("filter-caddy", "tail-enabled"))
    parser.add_argument("service")
    parser.add_argument("path", nargs="?")
    args = parser.parse_args()
    from master_settings import env_read
    try:
        env = env_read(args.state)
        require(args.service in module_ids(env), "Bilinmeyen Caddy yayını.")
        if args.action == "tail-enabled":
            sys.exit(0 if config(env)[args.service]["tail"] else 1)
        require(bool(args.path), "Caddy geçici dosyası gerekli.")
        atomic(args.path, private_site(env, args.service, read_regular(args.path)[0].decode()), 0o644)
    except (SettingsError, OSError, ValueError, KeyError) as err:
        print(str(err) if isinstance(err, SettingsError) else "Caddy yayın ayarı okunamadı.", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
