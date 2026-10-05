#!/usr/bin/env python3
"""Rootful bridge publication validation and the project's independent forwarding guard.

Netavark owns DNAT/SNAT. We own only one nft inet table with a forward and an input
chain at priority -10; an ACCEPT in Netavark/Tailscale's filter chains cannot bypass
its DROP. The input chain closes the host itself to containers (DD-229). No foreign
table is flushed. The locked writers (master-firewall, the container worker and the
package engine) install it; container units only check it before they start, including
at boot, and retry until it is in place (DD-223).

Worker API (caller holds installer/module/container locks):
  validate_ports(env, ports, name, run=runner) -> normalized schema rows
  bindings(env, ports, run=runner) -> Quadlet PublishPort values
  apply(env, run=runner); check(env, run=runner)
runner(argv, timeout=20) returns CompletedProcess or (rc, stdout, stderr).
Initial publications explicitly use IPv4; IPv6 remote/direct ingress to managed
bridges is denied. The host may reach local publications through OUTPUT DNAT.
DD-217: an App Store package may run on its own bridge (manifest PAKET_KONTEYNER_AG);
its placed Quadlet's IPv4 PublishPort lines on the WAN/Tailscale address are let through.

References: docs.podman.io/en/v5.4.2/markdown/podman-run.1.html (--publish);
www.netfilter.org/projects/nftables/manpage.html (hook priorities and ct tuples);
manpages.debian.org/trixie/libnftables1/libnftables-json.5.en.html.
"""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile


class NetworkError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _run(argv, timeout=20):
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)


def _result(run, argv, timeout=20):
    try:
        result = (run or _run)(argv, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as err:
        raise NetworkError("Ağ komutu çalıştırılamadı: " + argv[0], 503) from err
    if isinstance(result, tuple):
        return result
    return result.returncode, result.stdout or "", result.stderr or ""


def _json(run, argv):
    rc, out, _ = _result(run, argv)
    if rc:
        raise NetworkError("Ağ durumu okunamadı: " + argv[0], 503)
    try:
        return json.loads(out)
    except (ValueError, TypeError) as err:
        raise NetworkError("Ağ durumu geçersiz: " + argv[0], 503) from err


def _iface(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,14}", value):
        raise NetworkError("Ağ arayüzü adı geçersiz.")
    return value


def _config(env):
    table = env.get("KONTEYNER_NFT_TABLE", "")
    prefix = env.get("KONTEYNER_BRIDGE_PREFIX", "")
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,31}", table) or not re.fullmatch(r"[a-z][a-z0-9]{1,4}", prefix):
        raise NetworkError("Konteyner ağ koruması yapılandırılmamış.", 503)
    return table, prefix


def bridge_name(env, network="bridge"):
    _, prefix = _config(env)
    name = env.get("KONTEYNER_NETWORK", "") if network == "bridge" else network
    if not isinstance(name, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}", name) or name in ("none", "host", "podman"):
        raise NetworkError("Konsol tarafından yönetilen bir köprü ağı seçin.")
    return prefix + hashlib.sha256(name.encode()).hexdigest()[:10]


def _addresses(env, iface, run):
    rows = _json(run, ["ip", "-j", "address", "show", "dev", _iface(iface)])
    if not isinstance(rows, list):
        raise NetworkError("Arayüz adresleri okunamadı.", 503)
    addresses = []
    for row in rows:
        for address in row.get("addr_info", []):
            if address.get("family") != "inet" or address.get("scope") != "global":
                continue
            if any(flag in address.get("flags", []) for flag in ("tentative", "dadfailed")):
                continue
            try:
                parsed = ipaddress.IPv4Address(address["local"])
            except (KeyError, ValueError) as err:
                raise NetworkError("Arayüzde geçersiz IPv4 adresi.", 503) from err
            if parsed.is_unspecified or parsed.is_loopback or parsed.is_multicast or parsed.is_link_local:
                raise NetworkError("Arayüzde kullanılamayan IPv4 adresi.", 503)
            addresses.append(str(parsed))
    return sorted(set(addresses))


def tailscale_address(env, run=None):
    addresses = _addresses(env, env.get("TAILSCALE_IF", ""), run)
    if len(addresses) != 1 or ipaddress.ip_address(addresses[0]) not in ipaddress.ip_network("100.64.0.0/10"):
        raise NetworkError("Tailscale IPv4 adresi hazır değil; port açılmadı.", 409)
    return addresses[0]


def wan_addresses(env, run=None):
    rows = _json(run, ["ip", "-j", "route", "show", "default"])
    if not isinstance(rows, list):
        raise NetworkError("İnternet arayüzü bulunamadı.", 503)
    rows = sorted((r for r in rows if isinstance(r, dict) and r.get("dev")), key=lambda r: r.get("metric", 0))
    if not rows or (len(rows) > 1 and rows[0].get("metric", 0) == rows[1].get("metric", 0) and rows[0]["dev"] != rows[1]["dev"]):
        raise NetworkError("İnternet arayüzü belirsiz; port açılmadı.", 409)
    iface = _iface(rows[0]["dev"])
    _, prefix = _config(env)
    if iface == env.get("TAILSCALE_IF") or iface.startswith((prefix, "wg")):
        raise NetworkError("İnternet portu VPN veya konteyner arayüzüne açılamaz.", 409)
    addresses = _addresses(env, iface, run)
    if not addresses:
        raise NetworkError("İnternet IPv4 adresi hazır değil; port açılmadı.", 409)
    return iface, addresses


def _read(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "r", encoding="utf-8") as fh:
            info = os.fstat(fh.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 1048576:
                raise NetworkError("Konteyner ağ kaydı geçersiz.", 503)
            return fh.read(1048577)
    except (OSError, UnicodeError) as err:
        raise NetworkError("Konteyner ağ kaydı okunamadı.", 503) from err


def env_read(path):
    out = {}
    for line in _read(path).splitlines():
        key, sep, value = line.partition("=")
        if sep and re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            out[key] = value.strip().strip('"')
    return out


def read_definitions(env):
    base = Path(env["KONTEYNER_STATE_DIR"]) / "definitions"
    if base.is_symlink():
        raise NetworkError("Konteyner tanım dizini bağlantı olamaz.", 503)
    if not base.exists():
        return []
    out = []
    for path in sorted(base.glob("*.json")):
        try:
            row = json.loads(_read(path))
        except ValueError as err:
            raise NetworkError("Konteyner tanımı okunamadı; ağ kuralları korunuyor.", 503) from err
        if not isinstance(row, dict) or row.get("name") != path.stem:
            raise NetworkError("Konteyner tanımı adı geçersiz.", 503)
        out.append(row)
    return out


PUBLISH_RE = re.compile(r"(\d{1,3}(?:\.\d{1,3}){3}):([1-9]\d{0,4}):([1-9]\d{0,4})/(tcp|udp)")


def package_publications(env):
    """DD-217: registered packages on their own bridge publish what their placed Quadlet says.

    A stopped package's Quadlet is removed, so it publishes nothing. Only explicit IPv4
    "address:host:container/protocol" values count; anything else is simply not let through.
    A placed Quadlet on another network (an installer run renders the manifest before it places
    the new Quadlet) publishes nothing either: never a reason to stop the firewall.
    """
    registry, base, units = env.get("MODULES_FILE"), env.get("MODULES_DIR"), env.get("KONTEYNER_BIRIM_DIR")
    if not (registry and base and units) or not Path(registry).exists():
        return []
    out = []
    for line in _read(registry).splitlines():
        mid = line.split("\t", 1)[0]
        manifest = Path(base) / mid / "paket.env"
        if not re.fullmatch(r"[a-z]{2,16}", mid) or not manifest.exists():
            continue
        declared = env_read(manifest)
        name, network = declared.get("PAKET_KONTEYNER", ""), declared.get("PAKET_KONTEYNER_AG", "")
        if not network or not re.fullmatch(r"[a-z][a-z0-9-]{1,30}\.container", name):
            continue
        quadlet = Path(units) / name
        if not quadlet.exists():
            continue
        lines = [row.strip() for row in _read(quadlet).splitlines()]
        if "Network=" + network not in lines:
            continue
        ports = []
        for row in lines:
            match = PUBLISH_RE.fullmatch(row[len("PublishPort="):]) if row.startswith("PublishPort=") else None
            if not match or max(int(match[2]), int(match[3])) > 65535:
                continue
            try:
                address = str(ipaddress.IPv4Address(match[1]))
            except ValueError:
                continue
            ports.append({"address": address, "host_port": int(match[2]), "container_port": int(match[3]),
                          "protocol": match[4]})
        out.append({"id": mid, "network": network, "ports": ports})
    return out


def normalize_ports(ports):
    if not isinstance(ports, list) or len(ports) > 64:
        raise NetworkError("En fazla 64 port eşlemesi girilebilir.")
    out = []
    allowed = {"scope", "host_port", "container_port", "protocol", "public_ack"}
    for row in ports:
        if not isinstance(row, dict) or set(row) - allowed:
            raise NetworkError("Port eşlemesi geçersiz.")
        if row.get("scope") not in ("local", "tailscale", "public") or row.get("protocol") not in ("tcp", "udp"):
            raise NetworkError("Port erişimi veya protokolü geçersiz.")
        for key in ("host_port", "container_port"):
            if type(row.get(key)) is not int or not 1 <= row[key] <= 65535:
                raise NetworkError("Port 1–65535 arasında tam sayı olmalı.")
        ack = row.get("public_ack", False)
        if type(ack) is not bool or (row["scope"] == "public" and not ack):
            raise NetworkError("İnternet portu için açık onay gerekli.")
        item = {key: row[key] for key in ("scope", "host_port", "container_port", "protocol")}
        item["public_ack"] = ack if row["scope"] == "public" else False
        if any(overlap(item, previous) for previous in out):
            raise NetworkError("Aynı adres ve port birden fazla eşlenemez.")
        out.append(item)
    return out


def overlap(a, b):
    return (a["host_port"] == b["host_port"] and a["protocol"] == b["protocol"]
            and (a["scope"] == b["scope"] or "public" in (a["scope"], b["scope"])))


def bindings(env, ports, run=None):
    rows = normalize_ports(ports)
    tail = tailscale_address(env, run) if any(p["scope"] == "tailscale" for p in rows) else ""
    addresses = {"local": "127.0.0.1", "tailscale": tail, "public": "0.0.0.0"}
    return ["%s:%s:%s/%s" % (addresses[p["scope"]], p["host_port"], p["container_port"], p["protocol"]) for p in rows]


def reserved_ports(env):
    sources = [env]
    base = env.get("MODULES_DIR")
    if base and Path(base).exists():
        # Reuse the package engine's validated private overrides. Keep both the
        # default and effective port reserved, including while a package is stopped.
        import master_settings as settings
        for entry in Path(base).iterdir():
            if not re.fullmatch(r"[a-z]{2,16}", entry.name) or entry.is_symlink():
                continue
            path = entry / (entry.name + ".env")
            if path.exists():
                sources.append(env_read(path))
                try:
                    sources.append(settings.package_env(env, entry.name))
                except (OSError, UnicodeError, ValueError, settings.SettingsError) as err:
                    raise NetworkError("Paketin kalıcı port ayarları okunamadı; port açılmadı.", 503) from err
    reserved = {int(v) for source in sources for key, v in source.items()
                if key.endswith("_PORT") and str(v).isdigit() and 1 <= int(v) <= 65535}
    return reserved


def _socket_rows(text):
    for line in text.splitlines():
        values = line.split(None, 6)
        if len(values) < 6 or values[0] not in ("tcp", "udp"):
            if line.strip():
                raise NetworkError("Dinleyen portlar çözümlenemedi.", 503)
            continue
        ip, colon, port = values[4].rpartition(":")
        if not colon or not port.isdigit():
            raise NetworkError("Dinleyen port kaydı geçersiz.", 503)
        ip = ip.strip("[]").split("%")[0]
        owners = []
        processes = re.fullmatch(r'users:\((.*)\)', values[6].strip()) if len(values) == 7 else None
        if processes:
            pattern = r'\("([^"\\]+)",pid=([1-9][0-9]*),fd=[0-9]+\)'
            # Require the complete owner list, not a matching PID buried beside an unknown owner.
            remainder = re.sub(pattern, '', processes[1])
            if not remainder.strip(','):
                owners = [(process, int(pid)) for process, pid in re.findall(pattern, processes[1])]
        yield values[0], ip, int(port), owners


def _target_conmon_bindings(env, inventory, name, run):
    """Kernel socket owners may be exempt only with matching live Podman identity and mapping."""
    def names(row):
        value = row.get('Names') or []
        return [value] if isinstance(value, str) else value
    targets = [row for row in inventory if name in names(row)]
    if len(targets) != 1:
        return None
    expected_id = targets[0].get('Id') or targets[0].get('ID') or targets[0].get('id')
    if not isinstance(expected_id, str) or not re.fullmatch(r'[0-9a-f]{64}', expected_id):
        return None
    inspected = _json(run, ['podman', 'inspect', '--type', 'container', name])
    if not isinstance(inspected, list) or len(inspected) != 1 or not isinstance(inspected[0], dict):
        raise NetworkError('Konteyner portunun sahibi okunamadı.', 503)
    info = inspected[0]
    state = info.get('State') or {}
    pid = state.get('ConmonPid')
    if (info.get('Id') != expected_id or str(info.get('Name', '')).lstrip('/') != name or
            state.get('Running') is not True or type(pid) is not int or pid <= 0):
        return None
    import master_container_config as config
    # Standalone ownership is needed by adoption preflight; foreign units/pods/apps stay blocked.
    if config.ownership(info, env) not in ('konsol', 'standalone'):
        return None
    bindings = set()
    try:
        for target, rows in (info.get('HostConfig') or {}).get('PortBindings', {}).items():
            container_port, protocol = target.split('/')
            if not container_port.isdecimal() or not 1 <= int(container_port) <= 65535 or protocol not in ('tcp', 'udp'):
                return None
            for row in rows or []:
                host = int(row['HostPort'])
                ip = str(ipaddress.ip_address(row.get('HostIp') or '0.0.0.0'))
                if not 1 <= host <= 65535:
                    return None
                bindings.add((protocol, ip, host))
    except (AttributeError, KeyError, TypeError, ValueError):
        return None
    return pid, bindings


def validate_ports(env, ports, name, run=None):
    rows = normalize_ports(ports)
    if not rows:
        return rows
    reserved = reserved_ports(env)
    if any(p["host_port"] in reserved for p in rows):
        raise NetworkError("Bu port sistem veya App Store uygulaması için ayrılmış.", 409)
    addresses = {"local": "127.0.0.1", "public": "0.0.0.0"}
    if any(p["scope"] == "tailscale" for p in rows):
        addresses["tailscale"] = tailscale_address(env, run)
    for definition in read_definitions(env):
        if definition["name"] == name:
            continue
        previous = normalize_ports(definition.get("ports", []))
        if any(overlap(a, b) for a in rows for b in previous):
            raise NetworkError("Port başka bir kayıtlı konteynere ayrılmış: " + definition["name"], 409)
    inventory = _json(run, ["podman", "ps", "-a", "--format", "json"])
    if not isinstance(inventory, list) or not all(isinstance(row, dict) for row in inventory):
        raise NetworkError("Podman portları okunamadı.", 503)
    rc, text, _ = _result(run, ["ss", "-H", "-lntup"])
    if rc:
        raise NetworkError("Dinleyen portlar okunamadı.", 503)
    own, inspected_own = None, False
    for proto, ip, port, owners in _socket_rows(text):
        for row in rows:
            if proto == row["protocol"] and port == row["host_port"] and (ip in ("*", "::", "0.0.0.0") or row["scope"] == "public" or ip == addresses[row["scope"]]):
                if owners and not inspected_own:
                    own = _target_conmon_bindings(env, inventory, name, run)
                    inspected_own = True
                if (own and owners and all(owner == ('conmon', own[0]) for owner in owners) and
                        (proto, ip, port) in own[1]):
                    continue
                raise NetworkError("Port sunucuda başka bir işlem tarafından kullanılıyor.", 409)
    for container in inventory:
        names = container.get("Names") or []
        if isinstance(names, str):
            names = [names]
        if name in names:
            continue
        for binding in container.get("Ports") or []:
            try:
                host, count = int(binding["host_port"]), int(binding.get("range", 1))
                addr = binding.get("host_ip") or "0.0.0.0"
                proto = binding.get("protocol", "tcp")
            except (KeyError, ValueError, TypeError) as err:
                raise NetworkError("Podman port kaydı geçersiz.", 503) from err
            if not 1 <= host <= 65535 or not 1 <= count <= 65535 or host + count - 1 > 65535:
                raise NetworkError("Podman port aralığı geçersiz.", 503)
            for row in rows:
                if proto == row["protocol"] and host <= row["host_port"] < host + count and (addr in ("0.0.0.0", "::") or row["scope"] == "public" or addr == addresses[row["scope"]]):
                    raise NetworkError("Port başka bir Podman konteyneri tarafından kullanılıyor.", 409)
    return rows


def _match(left, right, op="=="):
    return {"match": {"op": op, "left": left, "right": right}}


def egress_blocks(env):
    """DD-224: destinations a container may not open a connection to: the VPN block list (IPv4,
    defaults.env's single owner). Missing or invalid fails closed: no guard is written."""
    blocks = []
    for item in env.get("VPN_BLOCK_DEST4", "").split():
        try:
            blocks.append(ipaddress.IPv4Network(item, strict=True))
        except ValueError as err:
            raise NetworkError("Konteyner çıkış engeli listesi geçersiz; kurulumu yeniden çalıştırın.", 503) from err
    if not blocks:
        raise NetworkError("Konteyner çıkış engeli listesi yok; kurulumu yeniden çalıştırın.", 503)
    return blocks


def policy(env, definitions, run=None):
    """Return nft's JSON table/chain/rule objects, suitable for exact health comparison."""
    table, prefix = _config(env)
    owner = {"family": "inet", "table": table}
    objects = [{"table": {"family": "inet", "name": table}},
               {"chain": dict(owner, name="forward", type="filter", hook="forward", prio=-10, policy="accept")},
               {"chain": dict(owner, name="input", type="filter", hook="input", prio=-10, policy="accept")}]
    inputs = []
    def rule(*expr):
        objects.append({"rule": dict(owner, chain="forward", expr=list(expr))})
    meta = lambda key: {"meta": {"key": key}}
    ct = lambda key, **kw: {"ct": dict(key=key, **kw)}
    # DD-229: a container opens nothing on the host itself (any host address: bridge gateway, WAN,
    # Tailscale, WireGuard, loopback through route_localnet). Only replies to connections the host
    # opened and DNS to its own bridge gateway (aardvark-dns) are let in. This is the project's own
    # input guard; it holds even if the host INPUT chain is missing or another chain accepts first.
    def input_rule(*expr):
        inputs.append({"rule": dict(owner, chain="input", expr=list(expr))})
    input_rule(_match(meta("iifname"), prefix + "*", "!="), {"return": None})
    for state in ("established", "related"):
        input_rule(_match(ct("direction"), "reply"), _match(ct("state"), state, "in"), {"return": None})
    for protocol in ("udp", "tcp"):
        input_rule(_match(meta("nfproto"), "ipv4"), _match(meta("l4proto"), protocol),
                   _match({"payload": {"protocol": protocol, "field": "dport"}}, 53),
                   _match({"fib": {"result": "type", "flags": ["daddr", "iif"]}}, "local"), {"return": None})
    input_rule({"drop": None})
    # DD-181/DD-224: traffic that neither leaves nor enters a bridge (exit node, WireGuard) passes after one rule.
    rule(_match(meta("iifname"), prefix + "*", "!="), _match(meta("oifname"), prefix + "*", "!="), {"return": None})
    # Only replies to container-originated traffic bypass publication checks. Original-direction
    # established connections still lose access immediately when their publication is revoked.
    # They come before the egress drops: replies to a Tailscale or WAN publication leave the bridge.
    for state in ("established", "related"):
        rule(_match(ct("direction"), "reply"), _match(ct("state"), state, "in"), {"return": None})
    # DD-224: a container may open connections to the internet, but not to the tailnet (it would leave
    # as this exit node), private, CGNAT or link-local ranges, nor over IPv6 (the bridges are IPv4-only).
    egress = lambda: [_match(meta("iifname"), prefix + "*"), _match(meta("oifname"), prefix + "*", "!=")]
    rule(*egress(), _match(meta("nfproto"), "ipv6"), {"drop": None})
    rule(_match(meta("iifname"), prefix + "*"), _match(meta("oifname"), _iface(env["TAILSCALE_IF"])), {"drop": None})
    for block in egress_blocks(env):
        address = str(block.network_address)
        rule(*egress(), _match({"payload": {"protocol": "ip", "field": "daddr"}},
                               address if block.prefixlen == 32 else {"prefix": {"addr": address, "len": block.prefixlen}}),
             {"drop": None})
    rule(_match(meta("oifname"), prefix + "*", "!="), {"return": None})
    packages = package_publications(env)
    # Bridge-local peers are governed by Netavark's network isolation; no blanket interbridge permit.
    bridges = {bridge_name(env, d.get("network", "bridge")) for d in definitions if d.get("network") != "none"}
    bridges.update(bridge_name(env, p["network"]) for p in packages)
    for bridge in sorted(bridges):
        rule(_match(meta("iifname"), bridge), _match(meta("oifname"), bridge), {"return": None})
    tail = None
    wan = None
    seen = []

    def publish(bridge, ingress, address, row):
        rule(_match(meta("oifname"), bridge), _match(meta("iifname"), ingress),
             _match(meta("nfproto"), "ipv4"), _match(meta("l4proto"), row["protocol"]),
             _match(ct("direction"), "original"), _match(ct("status"), "dnat", "in"),
             _match(ct("daddr", family="ip", dir="original"), address),
             _match(ct("proto-dst", dir="original"), row["host_port"]),
             _match({"payload": {"protocol": row["protocol"], "field": "dport"}}, row["container_port"]),
             {"return": None})
    for definition in sorted(definitions, key=lambda d: d["name"]):
        rows = normalize_ports(definition.get("ports", []))
        if definition.get("network") == "none":
            if rows:
                raise NetworkError("Ağsız konteyner port yayımlayamaz.")
            continue
        bridge = bridge_name(env, definition.get("network", "bridge"))
        for row in rows:
            if any(overlap(row, other) for other in seen):
                raise NetworkError("Kayıtlı konteyner portları çakışıyor.", 409)
            seen.append(row)
            if row["scope"] == "local":
                continue
            if row["scope"] == "tailscale":
                if tail is None:
                    tail = tailscale_address(env, run)
                ingress, originals = _iface(env["TAILSCALE_IF"]), [tail]
            else:
                if wan is None:
                    wan = wan_addresses(env, run)
                ingress, originals = wan
            for address in originals:
                publish(bridge, ingress, address, row)
    # DD-217: a package's loopback publication needs no forward path; its WAN or Tailscale one does.
    for package in packages:
        bridge = bridge_name(env, package["network"])
        for row in package["ports"]:
            if ipaddress.IPv4Address(row["address"]).is_loopback:
                continue
            if wan is None:
                wan = wan_addresses(env, run)
            if row["address"] == "0.0.0.0" or row["address"] in wan[1]:
                for address in (wan[1] if row["address"] == "0.0.0.0" else [row["address"]]):
                    publish(bridge, wan[0], address, row)
                continue
            if ipaddress.IPv4Address(row["address"]) in ipaddress.ip_network("100.64.0.0/10"):
                if tail is None:
                    tail = tailscale_address(env, run)
                if row["address"] == tail:
                    publish(bridge, _iface(env["TAILSCALE_IF"]), tail, row)
    rule({"drop": None})
    # nft lists chains before rules, and rules chain by chain; the health check compares in that order.
    return objects + inputs


def same_policy(expected, actual):
    def canonical_expr(expr):
        # nft list elides protocol selectors implied by a typed address/payload,
        # and the ct-address family. Normalize only these provable redundancies;
        # the address, port, direction and verdict must still match exactly.
        protocols = set()
        families = set()
        for e in expr:
            match = e.get("match", {})
            left = match.get("left", {})
            if match.get("op") != "==":
                continue
            payload = left.get("payload", {})
            if payload.get("protocol") in ("tcp", "udp"):
                protocols.add(payload["protocol"])
            ct = left.get("ct", {})
            if ct.get("key") == "daddr":
                try:
                    address = ipaddress.ip_address(match.get("right"))
                except ValueError:
                    continue
                family = "ip" if address.version == 4 else "ip6"
                if ct.get("family", family) == family:
                    families.add("ipv4" if address.version == 4 else "ipv6")
                    ct.pop("family", None)
        return [e for e in expr if not (
            e.get("match", {}).get("op") == "==" and (
                e["match"].get("left") == {"meta": {"key": "nfproto"}} and e["match"].get("right") in families
                or e["match"].get("left") == {"meta": {"key": "l4proto"}} and e["match"].get("right") in protocols))]
    def clean(value):
        if isinstance(value, list):
            return [clean(x) for x in value]
        if isinstance(value, dict):
            result = {k: clean(v) for k, v in value.items() if k not in ("handle", "index", "position")}
            if "expr" in result:
                result["expr"] = canonical_expr(result["expr"])
            return result
        return value
    if not isinstance(actual, dict) or not isinstance(actual.get("nftables"), list):
        return False
    rows = [x for x in actual["nftables"] if "metainfo" not in x]
    return clean(expected) == clean(rows)


def check(env, run=None):
    table, _ = _config(env)
    expected = policy(env, read_definitions(env), run=run)
    rc, out, err = _result(run, ["nft", "-j", "list", "table", "inet", table])
    if rc and re.search(r"No such file|does not exist", err, re.I):
        raise NetworkError("Konteyner yönlendirme koruması eksik veya güncel değil.", 503)
    if rc:
        raise NetworkError("Ağ durumu okunamadı: nft", 503)
    try:
        actual = json.loads(out)
    except (ValueError, TypeError) as error:
        raise NetworkError("Ağ durumu geçersiz: nft", 503) from error
    if not same_policy(expected, actual):
        raise NetworkError("Konteyner yönlendirme koruması eksik veya güncel değil.", 503)
    return True


def apply(env, run=None):
    table, _ = _config(env)
    objects = policy(env, read_definitions(env), run=run)
    rc, _, err = _result(run, ["nft", "-j", "list", "table", "inet", table])
    if rc and not re.search(r"No such file|does not exist", err, re.I):
        raise NetworkError("Konteyner güvenlik duvarı okunamadı.", 503)
    commands = [] if rc else [{"delete": {"table": {"family": "inet", "name": table}}}]
    commands.extend({"add": item} for item in objects)
    # Delete + rebuild is ONE netlink transaction; a failed parse/commit retains the previous table.
    with tempfile.NamedTemporaryFile(mode="w", prefix="container-net-", suffix=".json", dir=env["RUNTIME_DIR"], encoding="utf-8") as fh:
        json.dump({"nftables": commands}, fh)
        fh.flush()
        for argv in (["nft", "-j", "-c", "-f", fh.name], ["nft", "-j", "-f", fh.name]):
            rc, _, _ = _result(run, argv)
            if rc:
                raise NetworkError("Konteyner yönlendirme koruması uygulanamadı; önceki kurallar korunuyor.", 503)
    check(env, run=run)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True)
    parser.add_argument("operation", choices=("apply", "check", "--check"), nargs="?", default="apply")
    parser.add_argument("--check", action="store_true", dest="check_only")
    args = parser.parse_args()
    try:
        env = env_read(args.state)
        (check if args.check_only or args.operation in ("check", "--check") else apply)(env)
    except (NetworkError, KeyError) as err:
        parser.exit(1, "HATA: %s\n" % err)


if __name__ == "__main__":
    main()
