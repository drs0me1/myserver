#!/usr/bin/env python3
"""Actual forwarding/NAT acceptance in disposable nested network namespaces.

Run as root: unshare --net --fork python3 Data/tests/containers-network-linux.py
Requires iproute2, nftables and Python; never changes the host network namespace.
This exercises our actual nft guard with Netavark-shaped DNAT/SNAT and permissive
foreign filter chains, including what a container may open itself (DD-224): the
internet yes; tailnet, WireGuard, private, link-local and IPv6 destinations no.
Real Podman/Quadlet lifecycle is a separate live check.
"""
import importlib.util
import json
import os
from pathlib import Path
import select
import socket
import subprocess
import tempfile
import time

DATA = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("container_network", DATA / "panel/master_container_network.py")
net = importlib.util.module_from_spec(spec)
spec.loader.exec_module(net)


def cmd(*args, **kw):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=15, **kw).stdout.strip()


def line(process, timeout=5):
    if not select.select([process.stdout], [], [], timeout)[0]:
        raise AssertionError("fixture session output timed out")
    return process.stdout.readline().strip()


SERVER = r'''
import socket, threading, time
def client(c):
    with c:
        while True:
            data=c.recv(1024)
            if not data: return
            c.sendall(data)
def serve(kind):
    s=socket.socket(socket.AF_INET6,kind)
    s.setsockopt(socket.IPPROTO_IPV6,socket.IPV6_V6ONLY,0)
    s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    s.bind(('::',8080))
    if kind == socket.SOCK_STREAM:
        s.listen()
        while True:
            c,_=s.accept();threading.Thread(target=client,args=(c,),daemon=True).start()
    else:
        while True:
            d,a=s.recvfrom(1024);s.sendto(d,a)
for k in (socket.SOCK_STREAM,socket.SOCK_DGRAM): threading.Thread(target=serve,args=(k,),daemon=True).start()
time.sleep(300)
'''
PROBE = r'''
import socket,sys
ip,port,proto=sys.argv[1:]
s=socket.socket(socket.AF_INET6 if ':' in ip else socket.AF_INET,socket.SOCK_DGRAM if proto=='udp' else socket.SOCK_STREAM)
s.settimeout(.45)
try:
    s.connect((ip,int(port)));s.send(b'container-policy-probe');ok=s.recv(128)==b'container-policy-probe'
except OSError: ok=False
finally: s.close()
sys.exit(0 if ok else 1)
'''


def main():
    if os.geteuid() != 0 or os.readlink("/proc/self/ns/net") == os.readlink("/proc/1/ns/net"):
        raise SystemExit("Run as root in a separate network namespace (unshare --net --fork).")
    children = []
    cmd("ip", "link", "set", "lo", "up")
    # The simulated NAT needs Netavark's loopback-routing prerequisite too. This
    # changes only the fixture namespace, never the host's sysctl configuration.
    cmd("sysctl", "-q", "-w", "net.ipv4.ip_forward=1", "net.ipv6.conf.all.forwarding=1",
        "net.ipv4.conf.all.route_localnet=1")
    def peer(iface, v4, v6, bridge=None):
        process = subprocess.Popen(["unshare", "--net", "sleep", "300"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        children.append(process)
        until = time.monotonic() + 5
        while os.readlink(f"/proc/{process.pid}/ns/net") == os.readlink("/proc/self/ns/net"):
            if time.monotonic() > until:
                raise AssertionError("child network namespace did not start")
            time.sleep(.01)
        remote = "p" + str(len(children))
        cmd("ip", "link", "add", iface, "type", "veth", "peer", "name", remote)
        cmd("ip", "link", "set", remote, "netns", str(process.pid))
        if bridge:
            cmd("ip", "link", "set", iface, "master", bridge)
        cmd("ip", "link", "set", iface, "up")
        hostdev = bridge or iface
        cmd("ip", "addr", "add", v4 + ".1/24", "dev", hostdev)
        cmd("ip", "-6", "addr", "add", v6 + "::1/64", "dev", hostdev, "nodad")
        prefix = ["nsenter", "-t", str(process.pid), "-n"]
        cmd(*prefix, "ip", "link", "set", "lo", "up")
        cmd(*prefix, "ip", "addr", "add", v4 + ".2/24", "dev", remote)
        cmd(*prefix, "ip", "-6", "addr", "add", v6 + "::2/64", "dev", remote, "nodad")
        cmd(*prefix, "ip", "link", "set", remote, "up")
        cmd(*prefix, "ip", "route", "add", "default", "via", v4 + ".1")
        cmd(*prefix, "ip", "-6", "route", "add", "default", "via", v6 + "::1")
        return prefix
    probes = 0
    def probe(prefix, address, port, protocol, allowed):
        nonlocal probes
        got = subprocess.run([*prefix, "python3", "-c", PROBE, address, str(port), protocol], capture_output=True, text=True, timeout=3)
        if (got.returncode == 0) != allowed:
            raise AssertionError(f"{prefix or 'host'} -> {address}:{port}/{protocol}: wanted {'allow' if allowed else 'deny'}, rc={got.returncode}, {got.stderr}")
        probes += 1
    try:
        with tempfile.TemporaryDirectory(prefix="container-network-") as root:
            env = dict(KONTEYNER_STATE_DIR=root, RUNTIME_DIR=root, KONTEYNER_NETWORK="konsol",
                       KONTEYNER_BRIDGE_PREFIX="ksl", KONTEYNER_NFT_TABLE="master_containers", TAILSCALE_IF="tailscale0",
                       VPN_BLOCK_DEST4=net.env_read(DATA / "config/defaults.env")["VPN_BLOCK_DEST4"])
            wan = peer("eth0", "192.0.2", "2001:db8:1")
            tail = peer("tailscale0", "100.64.0", "fd7a:115c:a1e0:1")
            wg = peer("wg0", "10.8.0", "fd00:3")
            other = peer("eth1", "198.51.100", "2001:db8:4")
            lan = peer("eth2", "192.168.77", "2001:db8:77")
            meta = peer("eth3", "169.254.169", "2001:db8:169")
            bridge = net.bridge_name(env)
            cmd("ip", "link", "add", bridge, "type", "bridge")
            cmd("ip", "link", "set", bridge, "up")
            ctr = peer("ceth", "10.250.0", "fd00:250", bridge)
            cmd("ip", "route", "add", "default", "via", "192.0.2.2", "dev", "eth0")
            server = subprocess.Popen([*ctr, "python3", "-c", SERVER], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            children.append(server)
            deadline = time.monotonic() + 5
            while True:
                try:
                    with socket.create_connection(("10.250.0.2", 8080), timeout=.1):
                        break
                except OSError:
                    if time.monotonic() > deadline:
                        raise AssertionError("fixture echo server not ready")
                    time.sleep(.05)
            rows = []
            for scope, port in (("local", 18080), ("tailscale", 18081), ("public", 18082)):
                for protocol in ("tcp", "udp"):
                    rows.append(dict(scope=scope, host_port=port, container_port=8080, protocol=protocol, public_ack=scope == "public"))
            definition = dict(name="probe", network="bridge", ports=rows)
            directory = Path(root) / "definitions"
            directory.mkdir()
            path = directory / "probe.json"
            path.write_text(json.dumps(definition))
            # Prefix guards must win over both earlier and later foreign ACCEPT chains.
            nat = ["table inet fixture {",
                   "chain early { type filter hook forward priority -20; policy accept; accept; }",
                   "chain late { type filter hook forward priority 0; policy accept; accept; }",
                   "chain pre { type nat hook prerouting priority -100; policy accept;"]
            for protocol in ("tcp", "udp"):
                for address, port in (("127.0.0.1", 18080), ("100.64.0.1", 18081), ("192.0.2.1", 18082), ("203.0.113.88", 18082)):
                    nat.append(f"ip daddr {address} {protocol} dport {port} dnat ip to 10.250.0.2:8080;")
                nat.append(f"ip6 daddr 2001:db8:1::1 {protocol} dport 18082 dnat ip6 to [fd00:250::2]:8080;")
            nat += ["}", "chain out { type nat hook output priority -100; policy accept;"]
            for protocol in ("tcp", "udp"):
                nat.append(f"ip daddr 127.0.0.1 {protocol} dport 18080 dnat ip to 10.250.0.2:8080;")
            nat += ["}", "chain post { type nat hook postrouting priority 100; policy accept; ip saddr 127.0.0.0/8 ip daddr 10.250.0.2 masquerade; }", "}"]
            cmd("nft", "-f", "-", input="\n".join(nat))
            outsiders = cmd("nft", "-j", "list", "table", "inet", "fixture")
            net.apply(env)
            assert net.check(env)
            # DD-224: echo servers next to the host; the container may reach only the internet ones.
            for prefix in (wan, tail, wg, other, lan, meta):
                children.append(subprocess.Popen([*prefix, "python3", "-c", SERVER], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE))
            for address in ("192.0.2.2", "100.64.0.2", "10.8.0.2", "198.51.100.2", "192.168.77.2", "169.254.169.2"):
                deadline = time.monotonic() + 5
                while True:
                    try:
                        with socket.create_connection((address, 8080), timeout=.1):
                            break
                    except OSError:
                        if time.monotonic() > deadline:
                            raise AssertionError("peer echo server not ready: " + address)
                        time.sleep(.05)
            for protocol in ("tcp", "udp"):
                probe(ctr, "192.0.2.2", 8080, protocol, True)
                probe(ctr, "198.51.100.2", 8080, protocol, True)
                for address in ("100.64.0.2", "10.8.0.2", "192.168.77.2", "169.254.169.2", "2001:db8:1::2", "2001:db8:4::2"):
                    probe(ctr, address, 8080, protocol, False)
            for protocol in ("tcp", "udp"):
                probe([], "127.0.0.1", 18080, protocol, True)
                probe(tail, "100.64.0.1", 18081, protocol, True)
                probe(wan, "192.0.2.1", 18082, protocol, True)
                for prefix in (wan, tail, wg, other):
                    probe(prefix, "10.250.0.2", 8080, protocol, False)
                    probe(prefix, "fd00:250::2", 8080, protocol, False)
                    probe(prefix, "127.0.0.1", 18080, protocol, False)
                    if prefix != tail:
                        probe(prefix, "100.64.0.1", 18081, protocol, False)
                    if prefix != wan:
                        probe(prefix, "192.0.2.1", 18082, protocol, False)
                probe(wan, "2001:db8:1::1", 18082, protocol, False)
                # Exit-node/transit packets with the same port never count as a local publication.
                probe(tail, "203.0.113.88", 18082, protocol, False)
                probe(wg, "203.0.113.88", 18082, protocol, False)
            # Existing inbound TCP connections must stop after changing public -> local.
            session = subprocess.Popen([*wan, "python3", "-u", "-c",
                "import socket,sys;s=socket.create_connection(('192.0.2.1',18082));s.settimeout(.7);s.sendall(b'before');print(s.recv(32).decode(),flush=True);sys.stdin.readline();s.sendall(b'after');\ntry: print(s.recv(32).decode(),flush=True)\nexcept OSError: print('blocked',flush=True)"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            children.append(session)
            assert line(session) == "before"
            definition["ports"] = [p for p in rows if p["scope"] != "public"]
            path.write_text(json.dumps(definition))
            net.apply(env)
            session.stdin.write("continue\n"); session.stdin.flush()
            assert line(session) == "blocked", "revoked established inbound session still allowed"
            session.wait(timeout=3)
            assert outsiders == cmd("nft", "-j", "list", "table", "inet", "fixture"), "foreign table changed"
            # Tampering that keeps the table present must fail health verification.
            cmd("nft", "add", "rule", "inet", env["KONTEYNER_NFT_TABLE"], "forward", "accept")
            try:
                net.check(env)
            except net.NetworkError:
                pass
            else:
                raise AssertionError("health accepted changed owned rules")
            print(f"PASS: {probes} TCP/UDP IPv4/IPv6 packet probes (publications and container egress), scope revocation, foreign chains preserved, rule-integrity check")
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                child.kill(); child.wait()


if __name__ == "__main__":
    main()
