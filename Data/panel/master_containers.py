#!/usr/bin/env python3
"""Read-only Podman mapper (DD-208), reused by the DD-211 container manager.

Podman is part of the base (the App Store's container runtime). The root backend calls this module
for GET /api/konsol/konteynerler/{liste,ayrinti,gunluk}; everything comes from `podman` itself
(ps, inspect, images, system df, logs) run inside the backend's sandbox, which is enough for
reading, and, for a container on the host network, from /proc (the sockets it listens on, DD-215).
Nothing here starts, stops or removes a container: that belongs to the application that owns it. Environment variables are never returned (they may hold passwords), and log lines mask
values that follow words like password or token before they leave the server.
"""
import ipaddress
import json
import os
import re
import sys
import time

NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
TAILS = (100, 200, 500, 1000)
# "A temporary password is provided for this session: X", "token=..." , "API key: ..." → the value is masked.
SECRET_RE = re.compile(r"((?i:password|passwd|parola|secret|token|api[_ -]?key|private[_ -]?key)[^\n:=]{0,60}[:=]\s*)(\S+)")
MASK = "••••"
LABEL_KEYS = {"version": "org.opencontainers.image.version", "source": "org.opencontainers.image.source", "title": "org.opencontainers.image.title"}


def mask(line):
    return SECRET_RE.sub(lambda m: m.group(1) + MASK, line)


def epoch(value):
    """podman gives epoch seconds in ps and RFC 3339 text in inspect; the zero time means none."""
    if isinstance(value, (int, float)):
        return int(value) if value > 0 else None
    if isinstance(value, str) and value and not value.startswith("0001-"):
        from datetime import datetime
        text = re.sub(r"(\.\d{1,6})\d*", r"\1", value).replace("Z", "+00:00")
        try:
            return int(datetime.fromisoformat(text).timestamp())
        except ValueError:
            return None
    return None


def ports_of(bindings):
    """{'8080/tcp': [{'HostIp': '', 'HostPort': '61016'}]} → rows; an empty list for host networking."""
    rows = []
    for key, binds in sorted((bindings or {}).items()):
        port, _, proto = str(key).partition("/")
        for b in binds or []:
            host_port = str((b or {}).get("HostPort", "")).strip()
            if port.isdigit() and host_port.isdigit():
                rows.append({"host_ip": (b or {}).get("HostIp") or "0.0.0.0", "host_port": int(host_port),
                             "container_port": int(port), "protocol": proto or "tcp"})
    return rows


def ps_ports(items):
    """podman ps gives Ports as a list of {host_ip, host_port, container_port, protocol, range}."""
    rows = []
    for p in items or []:
        if isinstance(p, dict) and str(p.get("host_port", "")).isdigit() and str(p.get("container_port", "")).isdigit():
            rows.append({"host_ip": p.get("host_ip") or "0.0.0.0", "host_port": int(p["host_port"]),
                         "container_port": int(p["container_port"]), "protocol": p.get("protocol") or "tcp"})
    return rows


DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")


def image_repo(ref):
    """Repository of an image reference: without its @digest and without a :tag after the last '/'."""
    repo = str(ref or "").split("@", 1)[0]
    head, sep, last = repo.rpartition("/")
    if sep and ":" in last:
        repo = head + "/" + last.split(":", 1)[0]
    return repo


def update_status(run, image, channel, arch, timeout=30):
    """DD-214: is there a newer build on the image's channel? Reads manifests only, downloads no layer.

    `image` is the installed, digest-pinned reference; `channel` the tag it follows (empty or a
    digest: pinned, nothing to follow). A multi-arch index is compared by this host's platform
    manifest digest, a single manifest by its config digest (the local image id).
    run(argv, timeout) -> (returncode, stdout, last stderr line). Never raises.
    """
    result = {"state": "sabit", "channel": channel or "", "candidate": "", "error": ""}
    if not channel or "@" in channel:
        return result
    rc, out, _ = run(["podman", "image", "inspect", image], 20)
    try:
        info = json.loads(out)[0] if rc == 0 else None
    except (ValueError, IndexError, TypeError):
        info = None
    if not isinstance(info, dict):
        return dict(result, state="denetlenemedi", error="Kurulu imaj okunamadı.")
    local = {str(d).split("@", 1)[1] for d in info.get("RepoDigests") or [] if "@" in str(d)}
    if isinstance(info.get("Digest"), str):
        local.add(info["Digest"])
    rc, out, message = run(["podman", "manifest", "inspect", channel], timeout)
    try:
        remote = json.loads(out) if rc == 0 else None
    except ValueError:
        remote = None
    if not isinstance(remote, dict):
        return dict(result, state="denetlenemedi", error="Kayıt defterine ulaşılamadı" + (": " + message if message else "."))
    if isinstance(remote.get("manifests"), list):
        entries = [m for m in remote["manifests"] if isinstance(m, dict) and isinstance(m.get("platform"), dict)
                   and m["platform"].get("architecture") == arch and m["platform"].get("os", "linux") == "linux"
                   and DIGEST_RE.fullmatch(str(m.get("digest", "")))]
        if not entries:
            return dict(result, state="denetlenemedi", error="Kanalda bu sunucunun mimarisi (%s) için imaj yok." % arch)
        digest = entries[0]["digest"]
        return dict(result, state="guncel" if digest in local else "var", candidate=image_repo(channel) + "@" + digest)
    config = str((remote.get("config") or {}).get("digest", ""))
    if DIGEST_RE.fullmatch(config):
        current = "sha256:" + str(info.get("Id", "")).replace("sha256:", "")
        return dict(result, state="guncel" if config == current else "var")
    return dict(result, state="denetlenemedi", error="Kanalın imaj tanımı okunamadı.")


# DD-215: a container on the host network has no port mappings, so Konsol shows the sockets its own
# processes listen on: TCP in LISTEN and unconnected bound UDP, read from /proc like ss does.
TCP_LISTEN, UDP_UNBOUND = "0A", "07"
TAILNET_NETS = (ipaddress.ip_network("100.64.0.0/10"), ipaddress.ip_network("fd7a:115c:a1e0::/48"))
SOCKET_SCOPES = ("all", "wan", "tailscale", "other", "local")


def proc_address(text):
    """/proc/net/{tcp,udp}{,6} "0100007F:EE6E" → (address, port); each 32-bit word is in host order."""
    host, _, port = text.partition(":")
    raw = bytes.fromhex(host)
    if len(raw) not in (4, 16):
        raise ValueError("address length")
    if sys.byteorder == "little":
        raw = b"".join(raw[i:i + 4][::-1] for i in range(0, len(raw), 4))
    ip = ipaddress.ip_address(raw)
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip, int(port, 16)


def socket_scope(ip, wan=(), tailscale=()):
    """The kind of address a socket is bound to, not whether it is reachable (the firewall decides)."""
    if ip.is_unspecified:
        return "all"
    if ip.is_loopback:
        return "local"
    if ip.is_link_local:
        return "link"
    if str(ip) in tailscale:
        return "tailscale"
    if str(ip) in wan:
        return "wan"
    if any(ip.version == net.version and ip in net for net in TAILNET_NETS):
        return "tailscale"
    return "other"


def container_pids(pid, proc="/proc", cgroups="/sys/fs/cgroup", limit=512):
    """The container's init process and every process of its own cgroup (v2) subtree."""
    pids = {pid}
    try:
        with open("%s/%d/cgroup" % (proc, pid)) as f:
            path = next((line.strip()[3:] for line in f if line.startswith("0::")), "")
    except OSError:
        return pids
    if not path.startswith("/") or path == "/":
        return pids
    for root, _, _ in os.walk(os.path.join(cgroups, path.lstrip("/"))):
        try:
            with open(os.path.join(root, "cgroup.procs")) as f:
                pids.update(int(x) for x in f.read().split() if x.isdigit())
        except OSError:
            continue
        if len(pids) >= limit:
            break
    return pids


def listening(pid, wan=(), tailscale=(), proc="/proc", cgroups="/sys/fs/cgroup"):
    """Sockets a running host-network container listens on: [{address, port, protocol, scope}].

    Only sockets owned by the container's processes count (their fds matched against the socket
    table of the container's network namespace). IPv6 link-local binds are left out. None when the
    processes or the socket table cannot be read: unknown, never an empty "no ports".
    """
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return None
    inodes, seen_fds = set(), False
    for p in container_pids(pid, proc, cgroups):
        fd_dir = "%s/%d/fd" % (proc, p)
        try:
            names = os.listdir(fd_dir)
        except OSError:
            continue
        seen_fds = True
        for n in names:
            try:
                target = os.readlink(os.path.join(fd_dir, n))
            except OSError:
                continue
            if target.startswith("socket:[") and target.endswith("]"):
                inodes.add(target[8:-1])
    if not seen_fds:
        return None
    rows, seen, tables = [], set(), 0
    for protocol, files in (("tcp", ("tcp", "tcp6")), ("udp", ("udp", "udp6"))):
        for name in files:
            try:
                with open("%s/%d/net/%s" % (proc, pid, name)) as f:
                    lines = f.read().splitlines()[1:]
            except OSError:
                continue
            tables += 1
            for line in lines:
                parts = line.split()
                if len(parts) < 10 or parts[9] not in inodes:
                    continue
                if parts[3] != (TCP_LISTEN if protocol == "tcp" else UDP_UNBOUND) or not parts[2].endswith(":0000"):
                    continue
                try:
                    ip, port = proc_address(parts[1])
                except ValueError:
                    continue
                scope = socket_scope(ip, wan, tailscale)
                if port == 0 or scope == "link" or (protocol, str(ip), port) in seen:
                    continue
                seen.add((protocol, str(ip), port))
                rows.append({"address": str(ip), "port": port, "protocol": protocol, "scope": scope})
    if not tables:
        return None
    rows.sort(key=lambda r: (r["port"], r["protocol"], SOCKET_SCOPES.index(r["scope"]), r["address"]))
    return rows


class ContainerError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def name_of(value):
    if not isinstance(value, str) or not NAME_RE.fullmatch(value):
        raise ContainerError(400, "Konteyner adı geçersiz.")
    return value


class Containers:
    """run(argv, timeout) → (returncode, stdout text, last stderr line); the backend's run_tool."""

    def __init__(self, run):
        self.run = run

    # -- podman
    def podman(self, *args, timeout=20):
        """Runs podman read-only; returns (ok, parsed JSON or text, error text)."""
        rc, out, message = self.run(["podman", *args], timeout)
        if rc != 0:
            return False, None, message or "podman komutu başarısız"
        if "--format" in args and "json" in args:
            try:
                return True, json.loads(out or "null"), ""
            except ValueError:
                return False, None, "podman çıktısı okunamadı"
        return True, out, ""

    def runtime(self):
        ok, version, message = self.podman("version", "--format", "{{.Client.Version}}")
        version = (version or "").strip() if ok else ""
        if ok and not re.fullmatch(r"[0-9][0-9A-Za-z.+~-]{0,30}", version):
            ok, message = False, "podman sürümü okunamadı"
        return {"version": version if ok else "", "ok": ok, "error": "" if ok else "Podman kullanılamıyor: %s" % message}

    def liste(self):
        runtime = self.runtime()
        answer = {"read_at": int(time.time()), "runtime": runtime, "containers": [], "images": [], "storage": {"images": 0, "containers": 0, "size": None}}
        if not runtime["ok"]:
            return answer
        ok, rows, message = self.podman("ps", "-a", "--format", "json")
        if not ok:
            answer["runtime"] = {"version": runtime["version"], "ok": False, "error": "Konteynerler okunamadı: %s" % message}
            return answer
        for c in rows or []:
            if not isinstance(c, dict):
                continue
            names = c.get("Names") or []
            name = names[0] if isinstance(names, list) and names else str(c.get("Id", ""))[:12]
            labels = c.get("Labels") or {}
            networks = c.get("Networks") or []
            answer["containers"].append({
                "id": str(c.get("Id", ""))[:12], "name": name, "image": c.get("Image", ""), "state": c.get("State") or "unknown",
                "status": c.get("Status", ""), "created": epoch(c.get("Created")), "started": epoch(c.get("StartedAt")),
                "exit_code": c.get("ExitCode", 0) if isinstance(c.get("ExitCode"), int) else 0,
                "restarts": c.get("Restarts", 0) if isinstance(c.get("Restarts"), int) else 0,
                "unit": labels.get("PODMAN_SYSTEMD_UNIT", "") if isinstance(labels, dict) else "",
                "network": ", ".join(networks) if networks else "host" if (c.get("Namespaces") or {}).get("Net", "") == "host" or not networks else "",
                "ports": ps_ports(c.get("Ports")), "mounts": len(c.get("Mounts") or []),
            })
        answer["storage"]["containers"] = len(answer["containers"])
        ok, images, _ = self.podman("images", "--format", "json")
        if ok:
            for i in images or []:
                if isinstance(i, dict):
                    for n in (i.get("Names") or ["<adsız>"]):
                        answer["images"].append({"name": n, "size": i.get("Size") if isinstance(i.get("Size"), int) else None, "created": epoch(i.get("Created"))})
            answer["storage"]["images"] = len(answer["images"])
        ok, df, _ = self.podman("system", "df", "--format", "json")
        if ok and isinstance(df, list):
            total = 0
            for row in df:
                size = row.get("RawSize") if isinstance(row, dict) else None
                if isinstance(size, int):
                    total += size
            answer["storage"]["size"] = total
        return answer

    def ayrinti(self, name):
        ok, data, message = self.podman("inspect", "--type", "container", name)
        if not ok:
            raise ContainerError(404 if "no such" in message.lower() or "not found" in message.lower() else 502, "Konteyner bulunamadı" if "no such" in message.lower() else "Konteyner okunamadı: %s" % message)
        try:
            c = json.loads(data)[0]
        except (ValueError, IndexError, TypeError):
            raise ContainerError(502, "podman inspect çıktısı okunamadı")
        state, host, config, net = c.get("State") or {}, c.get("HostConfig") or {}, c.get("Config") or {}, c.get("NetworkSettings") or {}
        mode = host.get("NetworkMode", "") or ""
        networks = sorted(k for k in (net.get("Networks") or {}) if isinstance(k, str))
        labels = config.get("Labels") or {}
        health = state.get("Health") or {}
        mounts = []
        for m in c.get("Mounts") or []:
            if isinstance(m, dict):
                mounts.append({"type": m.get("Type", ""), "source": m.get("Source", ""), "destination": m.get("Destination", ""),
                               "rw": bool(m.get("RW", True)), "name": m.get("Name") or ""})
        mounts.sort(key=lambda m: m["destination"])
        return {
            "name": (c.get("Name") or name).lstrip("/"), "id": str(c.get("Id", ""))[:12], "image": c.get("ImageName", ""),
            "image_digest": str(c.get("ImageDigest", "")).replace("sha256:", "")[:12], "state": state.get("Status") or "unknown",
            "status": "", "created": epoch(c.get("Created")), "started": epoch(state.get("StartedAt")), "finished": epoch(state.get("FinishedAt")),
            "exit_code": state.get("ExitCode", 0) if isinstance(state.get("ExitCode"), int) else 0,
            "restarts": c.get("RestartCount", 0) if isinstance(c.get("RestartCount"), int) else 0,
            "unit": labels.get("PODMAN_SYSTEMD_UNIT", "") if isinstance(labels, dict) else "",
            "network": ", ".join(networks) if mode == "bridge" and networks else mode,
            "health": (health.get("Status") or "") if isinstance(health, dict) else "",
            # DD-227: the account the process runs as ("" = the image's default, often root).
            "user": str(config.get("User") or ""),
            "ports": ports_of(net.get("Ports") or host.get("PortBindings")), "mounts": mounts,
            "labels": {k: str(labels.get(v, "")) if isinstance(labels, dict) else "" for k, v in LABEL_KEYS.items()},
            "command": " ".join(str(x) for x in (config.get("Cmd") or [])),
        }

    def gunluk(self, name, tail):
        tail = int(tail) if str(tail).isdigit() and int(tail) in TAILS else 200
        ok, text, message = self.podman("logs", "--timestamps", "--tail", str(tail), name, timeout=30)
        if not ok:
            raise ContainerError(404 if "no such" in message.lower() else 502, "Konteyner bulunamadı" if "no such" in message.lower() else "Günlük okunamadı: %s" % message)
        lines = [mask(l) for l in (text or "").splitlines() if l.strip()]
        return {"name": name, "lines": lines[-tail:], "truncated": len(lines) >= tail, "masked": True}
