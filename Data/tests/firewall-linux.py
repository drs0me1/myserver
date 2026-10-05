#!/usr/bin/env python3
"""Real packet tests in nested disposable namespaces, never the host firewall.

Run as root: unshare --net --fork python3 Data/tests/firewall-linux.py
"""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import shlex
import socket
import subprocess
import tempfile
import threading
import time

DATA = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("settings", DATA / "panel/master_settings.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def cmd(*args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, text=True, **kwargs).stdout.strip()


def main():
    assert os.geteuid() == 0
    assert os.readlink("/proc/self/ns/net") != os.readlink("/proc/1/ns/net"), "Separate network namespace required"
    peers, sockets, echoes = [], [], []
    cmd("ip", "link", "set", "lo", "up")
    try:
        addresses = [("eth0", "192.0.2", "2001:db8:1"), ("tailscale0", "100.64.0", "fd00:2"),
                     ("wg0", "10.8.0", "fd00:3"), ("eth1", "198.51.100", "2001:db8:4")]
        for index, (iface, v4, v6) in enumerate(addresses):
            proc = subprocess.Popen(["unshare", "--net", "sleep", "600"])
            peers.append(proc)
            until = time.monotonic() + 5
            while os.readlink(f"/proc/{proc.pid}/ns/net") == os.readlink("/proc/self/ns/net"):
                assert time.monotonic() < until
                time.sleep(.01)
            peer = "peer" + str(index)
            cmd("ip", "link", "add", iface, "type", "veth", "peer", "name", peer)
            cmd("ip", "link", "set", peer, "netns", str(proc.pid))
            for prefix, device, suffix in (([], iface, 1), (["nsenter", "-t", str(proc.pid), "-n"], peer, 2)):
                cmd(*prefix, "ip", "link", "set", "lo", "up")
                cmd(*prefix, "ip", "addr", "add", f"{v4}.{suffix}/24", "dev", device)
                cmd(*prefix, "ip", "-6", "addr", "add", f"{v6}::{suffix}/64", "dev", device, "nodad")
                cmd(*prefix, "ip", "link", "set", device, "up")
        # veth stands in for point-to-point WireGuard (which has no NDP).
        # Pin only fixture neighbors: allowing WG INPUT ICMPv6 would weaken the policy.
        peer_mac=json.loads(cmd("nsenter","-t",str(peers[2].pid),"-n","ip","-j","link","show","peer2"))[0]["address"]
        host_mac=json.loads(cmd("ip","-j","link","show","wg0"))[0]["address"]
        cmd("ip","-6","neigh","replace","fd00:3::2","lladdr",peer_mac,"nud","permanent","dev","wg0")
        cmd("nsenter","-t",str(peers[2].pid),"-n","ip","-6","neigh","replace","fd00:3::1","lladdr",host_mac,"nud","permanent","dev","peer2")
        cmd("ip", "route", "add", "default", "via", "192.0.2.2", "dev", "eth0")
        # An upstream blanket tailnet ACCEPT must not bypass our baseline.
        for binary in ("iptables", "ip6tables"):
            cmd(binary, "-N", "ts-input")
            cmd(binary, "-A", "ts-input", "-i", "tailscale0", "-j", "ACCEPT")
            cmd(binary, "-A", "ts-input", "-p", "udp", "--dport", "41641", "-j", "ACCEPT")
            cmd(binary, "-A", "INPUT", "-j", "ts-input")
            for table, parent, chain in (("filter", "FORWARD", "ts-forward"), ("nat", "POSTROUTING", "ts-postrouting")):
                cmd(binary, "-t", table, "-N", chain)
                cmd(binary, "-t", table, "-A", chain, "-j", "RETURN")
                cmd(binary, "-t", table, "-A", parent, "-j", chain)
            for table, parent in (("filter", "INPUT"), ("filter", "FORWARD"), ("nat", "POSTROUTING")):
                if parent != "FORWARD":
                    cmd(binary, "-t", table, "-N", "third-party")
                    if table == "filter":
                        # Keep conntrack hooks registered after project chains
                        # are removed for a cold boot. Without any state match,
                        # nftables does not track the pre-guard UDP fixtures.
                        cmd(binary, "-t", table, "-A", "third-party", "-m", "conntrack",
                            "--ctstate", "ESTABLISHED,RELATED", "-j", "RETURN")
                    cmd(binary, "-t", table, "-A", "third-party", "-j", "RETURN")
                cmd(binary, "-t", table, "-A", parent, "-j", "third-party")
            # Final project DROP must win even if an unknown NIC falls through
            # to a permissive built-in policy and a later third-party ACCEPT.
            cmd(binary, "-A", "INPUT", "-i", "eth1", "-j", "ACCEPT")
        def tailscale_chains():
            return [cmd(b, "-t", t, "-S", c) for b in ("iptables", "ip6tables")
                    for t, c in (("filter", "ts-input"), ("filter", "ts-forward"), ("nat", "ts-postrouting"))]
        ts_before = tailscale_chains()
        def outsiders():
            return [cmd(b, "-t", t, "-S", "third-party") for b in ("iptables", "ip6tables") for t in ("filter", "nat")]
        outsiders_before = outsiders()
        with tempfile.TemporaryDirectory(prefix="firewall-test-") as temp:
            root = Path(temp)
            e = m.env_read(DATA / "config/defaults.env")
            # DD-203: the interface port is the torrent package's own setting, not a base default.
            e["TORRENT_UI_PORT"] = m.env_read(DATA / "magaza/torrent/torrent.env")["TORRENT_UI_PORT"]
            for key in ("SETTINGS_FILE", "SETTINGS_PENDING_FILE", "SETTINGS_DNS_FILE", "DNSMASQ_CONF_FILE",
                        "DNSMASQ_CONF_DIR", "MODULES_FILE", "MODULES_DIR", "WG_NETWORKS_FILE", "RUNTIME_DIR",
                        "UNIT_DIR", "TORRENT_PROFILE_DIR", "SBIN_DIR", "SHARE_STATE_FILE", "SERVER_ROOT"):
                e[key] = str(root / key.lower())
            e.update(LOCAL_DOMAIN="test", WAN_INTERFACE="eth0", TAILSCALE_IPV4="100.64.0.1",
                     WAN_IPV4="93.184.216.34", DOWNLOADS_PATH=str(Path(e["SERVER_ROOT"]) / "downloads"))
            # DD-182: wan_active reads the registry only with an assigned global
            # address and a running built-in share module. This alias exists
            # solely in the disposable namespace; no external packets are sent.
            cmd("ip", "addr", "add", e["WAN_IPV4"] + "/32", "dev", "lo")
            for key in ("SBIN_DIR", "RUNTIME_DIR", "DNSMASQ_CONF_DIR"):
                Path(e[key]).mkdir()
            # DD-198: the firewall asks the installed WireGuard package for its "vpn" declarations.
            (Path(e["MODULES_DIR"]) / "wireguard").mkdir(parents=True)
            for name in ("paket.env", "kanca"):
                shutil.copy(DATA / "magaza/wireguard" / name, Path(e["MODULES_DIR"]) / "wireguard" / name)
            # DD-201: the hook reads its registry path and defaults from the package's own env file.
            wg = m.env_read(DATA / "magaza/wireguard/wireguard.env")
            e["WG_PORT_DEFAULT"] = wg["WG_PORT_DEFAULT"]
            (Path(e["MODULES_DIR"]) / "wireguard/wireguard.env").write_text(
                "WG_NETWORKS_FILE=%s\nWG_PORT_DEFAULT=%s\n" % (shlex.quote(e["WG_NETWORKS_FILE"]), wg["WG_PORT_DEFAULT"]))
            # DD-199: qBittorrent's publication row exists only through its package manifest and check module.
            (Path(e["MODULES_DIR"]) / "torrent").mkdir()
            (Path(e["MODULES_DIR"]) / "torrent/paket.env").write_text(
                (DATA / "magaza/torrent/paket.env").read_text().replace("__TORRENT_UI_PORT__", e["TORRENT_UI_PORT"]))
            shutil.copy(DATA / "magaza/torrent/yayin.py", Path(e["MODULES_DIR"]) / "torrent/yayin.py")
            (Path(e["MODULES_DIR"]) / "torrent/torrent.env").write_text(
                "TORRENT_UI_PORT=%s\nTORRENT_PROFILE_DIR=%s\n" % (e["TORRENT_UI_PORT"], e["TORRENT_PROFILE_DIR"]))
            modules = Path(e["MODULES_FILE"])
            networks = Path(e["WG_NETWORKS_FILE"])
            module_record = "wireguard\tcalisiyor\ntorrent\tcalisiyor\npaylasim\tcalisiyor\n"
            network_record = f"wg0\t{e['WG_PORT_DEFAULT']}\tinet\t10.8.0.1\t10.8.0.0/24\tfd00:3::1\tfd00:3::/112\t1.1.1.1\tTest\n"
            state = root / "state.env"
            e["STATE_FILE"] = str(state)
            state.write_text("".join(k + "=" + shlex.quote(v) + "\n" for k, v in e.items()))
            shutil.copy(DATA / "panel/master_settings.py", Path(e["SBIN_DIR"]) / "master_settings.py")
            # DD-179: firewall.sh asks master_shares.py whether a WAN share is active.
            shutil.copy(DATA / "panel/master_shares.py", Path(e["SBIN_DIR"]) / "master_shares.py")
            shutil.copy(DATA / "panel/master_https.py", Path(e["SBIN_DIR"]) / "master_https.py")
            shutil.copy(DATA / "panel/master_publications.py", Path(e["SBIN_DIR"]) / "master_publications.py")
            worker = ["bash", str(DATA / "scripts/firewall.sh")]
            env = dict(os.environ, STATE_FILE=str(state))
            def apply():
                cmd(*worker, env=env)
                cmd(*worker, "--check", env=env)
            def snapshot():
                return [cmd(b, "-t", t, "-S") for b in ("iptables", "ip6tables") for t in ("filter", "nat")]
            def assert_outsiders():
                assert ts_before == tailscale_chains(), "Tailscale-owned rules changed"
                assert outsiders_before == outsiders(), "Third-party chain changed"
                for binary in ("iptables", "ip6tables"):
                    for table, parent, chain in (("filter", "INPUT", "ts-input"),
                                                  ("filter", "FORWARD", "ts-forward"),
                                                  ("nat", "POSTROUTING", "ts-postrouting")):
                        cmd(binary, "-t", table, "-C", parent, "-j", chain)
                        cmd(binary, "-t", table, "-C", parent, "-j", "third-party")
                    cmd(binary, "-C", "INPUT", "-i", "eth1", "-j", "ACCEPT")
            def remove_owned_policy():
                # Only disposable fixture chains in the already-isolated netns.
                # No flush of built-in, ts-* or third-party chains is permitted.
                for binary in ("iptables", "ip6tables"):
                    for table in ("filter", "nat"):
                        lines = [shlex.split(line) for line in cmd(binary, "-t", table, "-S").splitlines()]
                        names = {e[k] for k in ("CHAIN_INPUT", "CHAIN_SETTINGS", "CHAIN_FORWARD", "CHAIN_NAT")}
                        owned = {row[1] for row in lines if row[0] == "-N" and
                                 (row[1] in names or row[1].startswith(e["CHAIN_STAGING_PREFIX"]))}
                        for row in lines:
                            if row[0] == "-A" and "-j" in row and row[row.index("-j") + 1] in owned:
                                cmd(binary, "-t", table, "-D", *row[1:])
                        for chain in sorted(owned):
                            cmd(binary, "-t", table, "-F", chain)
                        for chain in sorted(owned):
                            cmd(binary, "-t", table, "-X", chain)
                assert_outsiders()
            def no_wg():
                for listing in snapshot():
                    assert e["CHAIN_FORWARD"] not in listing and e["CHAIN_NAT"] not in listing, listing
                    assert "wg0" not in listing and "--dport " + e["WG_PORT_DEFAULT"] not in listing, listing
            def repeat():
                before = snapshot()
                apply()
                assert before == snapshot(), "Repeated application changed the rules"
            # A genuinely empty firewall configuration; no module/network files.
            apply()
            no_wg()
            repeat()
            # Merely retaining a network file must never reactivate a module.
            networks.write_text(network_record)
            for record in (None, "", "dosya\tcalisiyor\npaylasim\tcalisiyor\n", "wireguard\tdurduruldu\n"):
                if record is not None:
                    modules.write_text(record)
                apply()
                no_wg()
                repeat()
            modules.write_text(module_record)
            share_status = json.loads(cmd("python3", str(Path(e["SBIN_DIR"]) / "master_shares.py"),
                                          "--state", str(state), "status"))
            assert share_status["running"] and share_status["wan"]["available"], share_status
            apply()
            hold_https = threading.Event()
            def serve(sock, proto):
                while True:
                    try:
                        if proto == "tcp":
                            conn, _ = sock.accept()
                            conn.sendall(b"ok")
                            if hold_https.is_set() and sock.getsockname()[1] == int(e["SHARE_HTTPS_PORT"]):
                                sockets.append(conn)
                            else:
                                conn.close()
                        else:
                            data, addr = sock.recvfrom(128)
                            sock.sendto(data, addr)
                    except OSError:
                        return
            allowed_tcp = {int(e[k]) for k in ("SSH_PUBLIC_PORT", "CADDY_HTTP_PORT", "SHARE_PORT", "DNS_PORT")}
            denied_tcp = {2019, 20902, 59000, 61002, 61003, 61007, 61008, int(e["FILES_PANEL_PORT"]),
                          int(e["TORRENT_UI_PORT"]), int(e["SHARE_HTTPS_PORT"])}
            udp_ports = {int(e[k]) for k in ("DNS_PORT", "TAILSCALE_UDP_PORT", "WG_PORT_DEFAULT")} | {20902, 59000}
            for family in (socket.AF_INET, socket.AF_INET6):
                for proto, ports in (("tcp", allowed_tcp | denied_tcp), ("udp", udp_ports)):
                    for port in ports:
                        sock = socket.socket(family, socket.SOCK_STREAM if proto == "tcp" else socket.SOCK_DGRAM)
                        sockets.append(sock)
                        if family == socket.AF_INET6:
                            sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
                        sock.bind(("0.0.0.0" if family == socket.AF_INET else "::", port))
                        if proto == "tcp":
                            sock.listen()
                        threading.Thread(target=serve, args=(sock, proto), daemon=True).start()
            probe = """import socket,sys
s=socket.socket(socket.AF_INET6 if ':' in sys.argv[1] else socket.AF_INET,socket.SOCK_STREAM if sys.argv[3]=='tcp' else socket.SOCK_DGRAM)
s.settimeout(.25)
if len(sys.argv)>5: s.bind(("::" if ":" in sys.argv[1] else "0.0.0.0",int(sys.argv[5])))
try:
 s.connect((sys.argv[1],int(sys.argv[2])))
 if sys.argv[3]=='udp': s.send(b'ok')
 result=s.recv(2)==b'ok'
except OSError: result=False
assert result==(sys.argv[4]=='1'),sys.argv[1:]
"""
            def check(index, family, proto, port, allowed):
                addr = addresses[index][1] + ".1" if family == 4 else addresses[index][2] + "::1"
                cmd("nsenter", "-t", str(peers[index].pid), "-n", "python3", "-c", probe,
                    addr, str(port), proto, "1" if allowed else "0")
            for family in (4, 6):
                tail_tcp = allowed_tcp if family == 4 else {int(e["SSH_PUBLIC_PORT"]), int(e["DNS_PORT"])}
                for port in allowed_tcp | denied_tcp:
                    check(1, family, "tcp", port, port in tail_tcp)
                    check(0, family, "tcp", port, port == int(e["SSH_PUBLIC_PORT"]))
                for port in udp_ports:
                    check(1, family, "udp", port, port in {int(e["DNS_PORT"]), int(e["WG_PORT_DEFAULT"])})
                    check(0, family, "udp", port, port == int(e["TAILSCALE_UDP_PORT"]) or
                          (family == 4 and port == int(e["WG_PORT_DEFAULT"])))
                for port in allowed_tcp | denied_tcp:
                    check(2, family, "tcp", port, False)
                for port in udp_ports:
                    check(2, family, "udp", port, False)
                for port in allowed_tcp | denied_tcp:
                    check(3, family, "tcp", port, False)
                for port in (int(e["DNS_PORT"]), int(e["WG_PORT_DEFAULT"]), 59000):
                    check(3, family, "udp", port, False)
                address = addresses[2][1]+".1" if family == 4 else addresses[2][2]+"::1"
                ping = subprocess.run(["nsenter","-t",str(peers[2].pid),"-n","ping","-"+str(family),"-c","1","-W","1",address], capture_output=True)
                assert ping.returncode != 0, "WG host ping unexpectedly allowed"
            print("PASS real IPv4/IPv6 tailnet allowlist, unknown/peer/backend deny, second-NIC default deny, WAN and WG preservation", flush=True)
            # The real helper keeps TLS-ALPN renewal reachable with no folders.
            # This is only a local TCP echo; no DNS, ACME or host services are used.
            https_port, share_port = int(e["SHARE_HTTPS_PORT"]), int(e["SHARE_PORT"])
            https_settings = dict(m.DEFAULT, https={"domain": "dav.example.com"})
            m.save_json(e["SETTINGS_FILE"], https_settings)
            apply()
            repeat()
            status = cmd("python3", str(Path(e["SBIN_DIR"]) / "master_shares.py"),
                         "--state", str(state), "wan-firewall")
            assert status.split() == ["1", "16", "64", str(https_port)], status
            check(0, 4, "tcp", https_port, True)
            check(0, 4, "tcp", share_port, False)
            check(1, 4, "tcp", share_port, True)
            for family in (4, 6):
                check(2, family, "tcp", https_port, False)
                check(3, family, "tcp", https_port, False)
            check(0, 6, "tcp", https_port, False)
            check(0, 4, "udp", int(e["WG_PORT_DEFAULT"]), True)

            # Hold real WAN TCP sockets to exercise both limits, even when an
            # operator ACCEPT is present. Fresh source aliases avoid old probes.
            allow_https = dict(id="https", name="HTTPS fixture", family=4, scope="wan", proto="tcp",
                               port=https_port, source="", allow=True)
            m.save_json(e["SETTINGS_FILE"], dict(https_settings, firewall=[allow_https]))
            apply()
            admission = """import socket,struct,sys
opened=[]
try:
 for address in sys.argv[4:]:
  for _ in range(int(sys.argv[2])):
   s=socket.socket(); s.settimeout(.5)
   s.setsockopt(socket.SOL_SOCKET,socket.SO_LINGER,struct.pack('ii',1,0))
   s.bind((address,0))
   try:
    s.connect(('192.0.2.1',int(sys.argv[1])))
    assert s.recv(2)==b'ok'
   except OSError:
    s.close()
   else: opened.append(s)
 assert len(opened)==int(sys.argv[3]),(len(opened),sys.argv[3])
finally:
 for s in opened: s.close()
"""
            hold_https.set()
            try:
                for sources, attempts, expected in ((["192.0.2.10"], 17, 16),
                                                    ([f"192.0.2.{n}" for n in range(20, 25)], 16, 64)):
                    for address in sources:
                        cmd("nsenter", "-t", str(peers[0].pid), "-n", "ip", "addr", "add",
                            address + "/32", "dev", "peer0")
                    apply()
                    cmd("nsenter", "-t", str(peers[0].pid), "-n", "python3", "-c", admission,
                        str(https_port), str(attempts), str(expected), *sources)
                    check(1, 4, "tcp", share_port, True)
            finally:
                hold_https.clear()
            deny_https = dict(allow_https, allow=False)
            m.save_json(e["SETTINGS_FILE"], dict(https_settings, firewall=[deny_https]))
            apply()
            check(0, 4, "tcp", https_port, False)
            rules = cmd("iptables", "-S", e["CHAIN_SETTINGS"])
            assert rules.index("konsol-base:share-total") < rules.index("konsol-base:share-ip") < rules.index("konsol:https")
            m.save_json(e["SETTINGS_FILE"], https_settings)
            apply()
            # Both obsolete HTTP allows and misplaced connlimit rules fail check.
            stale = ["-i", "eth0", "-p", "tcp", "--dport", str(share_port), "-j", "ACCEPT"]
            cmd("iptables", "-I", e["CHAIN_INPUT"], "1", *stale)
            assert subprocess.run([*worker, "--check"], env=env, capture_output=True).returncode != 0
            apply()
            for line in cmd("iptables", "-S", e["CHAIN_SETTINGS"]).splitlines():
                if "konsol-base:share-total" in line:
                    args = shlex.split(line)[2:]
                    cmd("iptables", "-D", e["CHAIN_SETTINGS"], *args)
                    cmd("iptables", "-A", e["CHAIN_SETTINGS"], *args)
                    break
            assert subprocess.run([*worker, "--check"], env=env, capture_output=True).returncode != 0
            apply()
            # Explicit HTTPS removal must not revive legacy WAN HTTP.
            m.save_json(e["SETTINGS_FILE"], dict(m.DEFAULT, https={"domain": ""}))
            apply()
            repeat()
            check(0, 4, "tcp", https_port, False)
            check(0, 4, "tcp", share_port, False)
            check(1, 4, "tcp", share_port, True)
            assert "connlimit" not in cmd("iptables", "-S", e["CHAIN_SETTINGS"])
            m.save_json(e["SETTINGS_FILE"], m.DEFAULT)
            apply()
            assert_outsiders()
            print("PASS HTTPS renewal without folders, 16/IP and 64 total limits, manual deny, HTTP closure and tailnet preservation", flush=True)
            # DD-191: the same permission supports qBittorrent without DAV;
            # two enabled hostnames still generate a single TCP-port permit.
            qconf = Path(e["TORRENT_PROFILE_DIR"]) / "qBittorrent/qBittorrent.conf"
            qconf.parent.mkdir(parents=True)
            qconf.write_text("[Preferences]\nWebUI\\Password_PBKDF2=fixture\nWebUI\\LocalHostAuth=true\n")
            qweb = {"torrent": dict(tail=True, enabled=True, domain="torrent.example.com")}
            for domain in ("", "dav.example.com"):
                m.save_json(e["SETTINGS_FILE"], dict(m.DEFAULT, https={"domain": domain}, web=qweb))
                apply()
                repeat()
                check(0, 4, "tcp", https_port, True)
                check(0, 4, "tcp", share_port, False)
                rules = cmd("iptables", "-S", e["CHAIN_INPUT"])
                assert sum("--dport " + str(https_port) + " -j ACCEPT" in line for line in rules.splitlines()) == 1
            m.save_json(e["SETTINGS_FILE"], dict(m.DEFAULT, https={"domain": ""}, web=qweb))
            modules.write_text(module_record.replace("torrent\tcalisiyor", "torrent\tdurduruldu"))
            apply()
            check(0, 4, "tcp", https_port, False)
            modules.write_text(module_record)
            qconf.write_text("[Preferences]\nWebUI\\Password_PBKDF2=fixture\nWebUI\\LocalHostAuth=false\n")
            apply()
            check(0, 4, "tcp", https_port, False)
            m.save_json(e["SETTINGS_FILE"], m.DEFAULT)
            apply()
            print("PASS qBittorrent-only/shared HTTPS permission, stopped-module and unsafe-auth closure", flush=True)
            # Real routed traffic: the WAN peer has no route back to the WG
            # subnet, so an echo reply also proves NAT (both address families).
            cmd("sysctl", "-qw", "net.ipv4.ip_forward=1", "net.ipv6.conf.all.forwarding=1")
            cmd("nsenter", "-t", str(peers[2].pid), "-n", "ip", "route", "add", "default", "via", "10.8.0.1")
            cmd("nsenter", "-t", str(peers[2].pid), "-n", "ip", "-6", "route", "add", "default", "via", "fd00:3::1")
            echo = """import socket,threading,time
def serve(s):
 while True:
  data,addr=s.recvfrom(128); s.sendto(data,addr)
for family,addr in ((socket.AF_INET,'0.0.0.0'),(socket.AF_INET6,'::')):
 s=socket.socket(family,socket.SOCK_DGRAM)
 if family==socket.AF_INET6: s.setsockopt(socket.IPPROTO_IPV6,socket.IPV6_V6ONLY,1)
 s.bind((addr,59001)); threading.Thread(target=serve,args=(s,),daemon=True).start()
print('ready',flush=True)
time.sleep(600)
"""
            for index in (0, 1):
                process = subprocess.Popen(["nsenter", "-t", str(peers[index].pid), "-n", "python3", "-c", echo],
                                           stdout=subprocess.PIPE, text=True)
                echoes.append(process)
                assert process.stdout.readline().strip() == "ready"
                for family in (4, 6):
                    addr = addresses[index][1] + ".2" if family == 4 else addresses[index][2] + "::2"
                    cmd("python3", "-c", probe, addr, "59001", "udp", "1")
                    cmd("nsenter", "-t", str(peers[2].pid), "-n", "python3", "-c", probe,
                        addr, "59001", "udp", "1" if index == 0 else "0")
            # Private/CGNAT/link-local destinations routed through the WAN are still denied.
            for addr in ("10.23.1.2", "172.20.0.2", "192.168.40.2", "100.90.0.2", "169.254.20.2", "fd00:5::2"):
                version = "-6" if ":" in addr else "-4"
                prefix = "/128" if version == "-6" else "/32"
                gateway = "2001:db8:1::2" if version == "-6" else "192.0.2.2"
                cmd("nsenter","-t",str(peers[0].pid),"-n","ip",version,"addr","add",addr+prefix,"dev","lo")
                cmd("ip",version,"route","add",addr+prefix,"via",gateway)
                # Bind the echo to this exact alias, so replies use the same source.
                fixture = echo.replace("((socket.AF_INET,'0.0.0.0'),(socket.AF_INET6,'::'))",
                                       f"((socket.AF_INET6 if ':' in '{addr}' else socket.AF_INET,'{addr}'),)").replace("59001","59002")
                process=subprocess.Popen(["nsenter","-t",str(peers[0].pid),"-n","python3","-c",fixture],
                                         stdout=subprocess.PIPE,text=True)
                echoes.append(process)
                assert process.stdout.readline().strip()=="ready"
                cmd("python3","-c",probe,addr,"59002","udp","1")
                cmd("nsenter","-t",str(peers[2].pid),"-n","python3","-c",probe,addr,"59002","udp","0")
            # A previous allowed UDP flow must not bypass the new WG host guard.
            for binary, addr in (("iptables","10.8.0.1"),("ip6tables","fd00:3::1")):
                cmd(binary,"-I",e["CHAIN_SETTINGS"],"1","-i","wg0","-p","udp","--dport","59000","-j","ACCEPT")
                call = ["nsenter","-t",str(peers[2].pid),"-n","python3","-c",probe,addr,"59000","udp"]
                cmd(*call,"1","59005")
                apply()
                cmd(*call,"0","59005")
            # Old disk rules cannot punch a hole in the mandatory WG policy.
            old_rule = dict(id="retired",name="Legacy",family=4,scope="wg0",proto="tcp",port=61006,source="",allow=True)
            m.save_json(e["SETTINGS_FILE"],dict(m.DEFAULT,firewall=[old_rule]))
            apply()
            check(2,4,"tcp",61006,False)
            print("PASS WG host isolation including established flows; IPv4/IPv6 WAN forwarding/NAT; private WAN and tailnet deny", flush=True)
            # Explicit operator allows/denies stay above the baseline, in order.
            rule = dict(id="fixture", name="Test", family=4, scope="tail", proto="tcp", port=59000, source="", allow=True)
            m.save_json(e["SETTINGS_FILE"], dict(m.DEFAULT, firewall=[rule]))
            apply()
            check(1, 4, "tcp", 59000, True)
            rule.update(port=int(e["CADDY_HTTP_PORT"]), allow=False)
            m.save_json(e["SETTINGS_FILE"], dict(m.DEFAULT, firewall=[rule]))
            apply()
            check(1, 4, "tcp", rule["port"], False)
            m.save_json(e["SETTINGS_FILE"], m.DEFAULT)
            apply()
            repeat()
            for binary in ("iptables", "ip6tables"):
                cmd(binary, "-I", e["CHAIN_SETTINGS"], "3", "-i", "tailscale0", "-j", "RETURN")
                result = subprocess.run([*worker, "--check"], env=env, capture_output=True)
                assert result.returncode != 0, "Extra tailnet bypass was not detected"
                apply()
                # Real stale INPUT/FORWARD/NAT rules, not just UI rows.
                for table, chain, rule in (
                    ("filter", e["CHAIN_INPUT"], ["-i", "wg0", "-p", "tcp", "--dport", "61003", "-j", "ACCEPT"]),
                    ("filter", e["CHAIN_FORWARD"], ["-j", "RETURN"]),
                    ("nat", e["CHAIN_NAT"], ["-o", "eth0", "-j", "MASQUERADE"]),
                ):
                    cmd(binary, "-t", table, "-A", chain, *rule)
                    result = subprocess.run([*worker, "--check"], env=env, capture_output=True)
                    assert result.returncode != 0, f"Stale {binary}/{chain} rule was not detected"
                    apply()
                    assert subprocess.run([binary, "-t", table, "-C", chain, *rule], capture_output=True).returncode != 0
            # No terminal-only RETURN remains in any of our chains.
            for listing in snapshot():
                assert not any(line.startswith("-A MASTER-") and line.split()[2:] == ["-j", "RETURN"]
                               for line in listing.splitlines())
            # Uninstall while retaining networks -> no WG chains/ports, including
            # on the next install/reload. The module record is the sole authority.
            modules.unlink()
            apply()
            no_wg()
            repeat()
            for family in (4, 6):
                check(0, family, "udp", int(e["WG_PORT_DEFAULT"]), False)
                check(1, family, "udp", int(e["WG_PORT_DEFAULT"]), False)
            assert networks.read_text() == network_record
            modules.write_text(module_record)
            apply()
            repeat()
            check(0, 4, "udp", int(e["WG_PORT_DEFAULT"]), True)
            check(1, 4, "udp", int(e["WG_PORT_DEFAULT"]), True)
            assert_outsiders()
            print("PASS clean/repeat installs, missing/stopped module, retained profiles, stale INPUT/FORWARD/NAT repair, untouched third-party chains", flush=True)

            # Both families require a final unconditional DROP. A missing or
            # moved final rule must fail --check, even with the WAN DROP intact.
            for binary in ("iptables", "ip6tables"):
                cmd(binary, "-D", e["CHAIN_INPUT"], "-j", "DROP")
                result = subprocess.run([*worker, "--check"], env=env, capture_output=True, text=True, timeout=20)
                assert result.returncode != 0, "Missing final DROP passed --check"
                check(3, 4 if binary == "iptables" else 6, "tcp", 59000, True)
                apply()
                cmd(binary, "-D", e["CHAIN_INPUT"], "-j", "DROP")
                cmd(binary, "-I", e["CHAIN_INPUT"], "1", "-j", "DROP")
                result = subprocess.run([*worker, "--check"], env=env, capture_output=True, text=True, timeout=20)
                assert result.returncode != 0, "Misordered final DROP passed --check"
                apply()

            # Corrupt each real input independently. Existing policy must stay
            # byte-for-byte intact, including an explicit operator SSH deny.
            settings_path = Path(e["SETTINGS_FILE"])
            share_path = Path(e["SHARE_STATE_FILE"])
            deny_rules = [dict(id="deny" + str(f), name="Keep SSH deny", family=f, scope="tail",
                               proto="tcp", port=int(e["SSH_PUBLIC_PORT"]), source="", allow=False)
                          for f in (4, 6)]
            corruptions = (("settings", settings_path, "{broken settings"),
                           ("share", share_path, "{broken shares"),
                           ("WireGuard", networks, "wg0\tinvalid\n"),
                           ("share port", Path(e["SBIN_DIR"]) / "master_shares.py", "print('1 16 64 65536')\n"),
                           ("old helper", Path(e["SBIN_DIR"]) / "master_shares.py", "print('1 16 64')\n"))

            def expect_load_failure(label):
                result = subprocess.run(worker, env=env, capture_output=True, text=True, timeout=20)
                assert result.returncode != 0, (label, result.stdout, result.stderr)
                assert {"settings": "WebDAV WAN kaydı okunamadı",
                        "share": "WebDAV WAN kaydı okunamadı",
                        "WireGuard": "güvenlik duvarı bildirimi bozuk",
                        "share port": "WebDAV WAN portu geçersiz",
                        "old helper": "WebDAV WAN sınırları veya portu geçersiz"}[label] in result.stderr, result.stderr
                before_check = snapshot()
                result = subprocess.run([*worker, "--check"], env=env, capture_output=True, text=True, timeout=20)
                assert result.returncode != 0, label + " invalid configuration passed --check"
                assert before_check == snapshot(), "--check mutated the firewall"
                assert_outsiders()

            for label, path, broken in corruptions:
                m.save_json(settings_path, dict(m.DEFAULT, firewall=deny_rules))
                apply()
                before = snapshot()
                saved = path.read_bytes() if path.exists() else None
                path.write_text(broken)
                expect_load_failure(label)
                assert before == snapshot(), label + " load failure replaced an existing manual deny"
                for family in (4, 6):
                    check(1, family, "tcp", int(e["SSH_PUBLIC_PORT"]), False)
                    check(0, family, "tcp", int(e["SSH_PUBLIC_PORT"]), True)
                    check(2, family, "tcp", 59000, False)
                    check(3, family, "tcp", 59000, False)
                if saved is None:
                    path.unlink()
                else:
                    path.write_bytes(saved)
                apply()
                assert before == snapshot(), label + " repaired load did not preserve operator rules"
            print("PASS invalid settings/share/WG preserve existing manual denies and --check stays read-only", flush=True)

            # Explicit return routes make a successful pre-guard forwarding
            # probe independent of NAT. A later denial therefore proves filtering.
            for family, subnet, gateway in (("-4", "10.8.0.0/24", "192.0.2.1"),
                                             ("-6", "fd00:3::/64", "2001:db8:1::1")):
                cmd("nsenter", "-t", str(peers[0].pid), "-n", "ip", family,
                    "route", "replace", subnet, "via", gateway)
            process = subprocess.Popen(["nsenter", "-t", str(peers[2].pid), "-n", "python3", "-c", echo],
                                       stdout=subprocess.PIPE, text=True)
            echoes.append(process)
            assert process.stdout.readline().strip() == "ready"

            for label, path, broken in corruptions:
                m.save_json(settings_path, m.DEFAULT)
                saved = path.read_bytes() if path.exists() else None
                remove_owned_policy()
                if label == "WireGuard":
                    # Registry validation cannot identify this unregistered interface.
                    cmd("ip", "link", "set", "wg0", "name", "wg9")
                for binary in ("iptables", "ip6tables"):
                    assert "-P INPUT ACCEPT" in cmd(binary, "-S", "INPUT")
                    assert "-P FORWARD ACCEPT" in cmd(binary, "-S", "FORWARD")
                flows = []
                for family in (4, 6):
                    # Prove listeners and routes work before installing recovery.
                    for index in (0, 1, 2, 3):
                        check(index, family, "tcp", 59000, True)
                    for index, source_port in ((1, 59006), (2, 59007)):
                        addr = addresses[index][1] + ".1" if family == 4 else addresses[index][2] + "::1"
                        call = ["nsenter", "-t", str(peers[index].pid), "-n", "python3", "-c", probe,
                                addr, "59000", "udp"]
                        cmd(*call, "1", str(source_port))
                        flows.append((call, index, source_port))
                    addr = addresses[0][1] + ".2" if family == 4 else addresses[0][2] + "::2"
                    cmd("nsenter", "-t", str(peers[2].pid), "-n", "python3", "-c", probe,
                        addr, "59001", "udp", "1", "59008")
                    wg_addr = addresses[2][1] + ".2" if family == 4 else addresses[2][2] + "::2"
                    cmd("nsenter", "-t", str(peers[0].pid), "-n", "python3", "-c", probe,
                        wg_addr, "59001", "udp", "1", "59009")
                path.write_text(broken)
                expect_load_failure(label)
                # Probe the seeded flows before the lengthy deny matrix can
                # outlive Linux's UDP conntrack idle timeout (normally 30s).
                for call, index, source_port in flows:
                    cmd(*call, "1" if index == 1 else "0", str(source_port))
                failed_policy = snapshot()
                # A repeated failure cannot duplicate guards or open anything.
                expect_load_failure(label)
                assert failed_policy == snapshot(), "Repeated cold failure changed recovery policy"
                # Model an interrupted recovery after INPUT was attached but
                # before FORWARD. Retry must rebuild FORWARD independently.
                for binary in ("iptables", "ip6tables"):
                    guard = e["CHAIN_STAGING_PREFIX"] + "SAFE-FW"
                    cmd(binary, "-D", "FORWARD", "-j", guard)
                    cmd(binary, "-F", guard)
                    cmd(binary, "-X", guard)
                expect_load_failure(label)
                assert failed_policy == snapshot(), "Recovery retry left WG forwarding unguarded"
                for binary in ("iptables", "ip6tables"):
                    guard = e["CHAIN_STAGING_PREFIX"] + "SAFE"
                    rules = cmd(binary, "-S", "INPUT").splitlines()
                    assert rules[1] == "-A INPUT -j " + guard, rules
                    assert cmd(binary, "-S", guard).splitlines()[-1] == "-A " + guard + " -j DROP"
                for family in (4, 6):
                    for index in (0, 1, 3):
                        check(index, family, "tcp", int(e["SSH_PUBLIC_PORT"]), True)
                        check(index, family, "udp", int(e["TAILSCALE_UDP_PORT"]), True)
                        for port in (int(e["CADDY_HTTP_PORT"]), int(e["SHARE_PORT"]), int(e["SHARE_HTTPS_PORT"]),
                                     int(e["DNS_PORT"]), 59000):
                            check(index, family, "tcp", port, False)
                        check(index, family, "udp", int(e["WG_PORT_DEFAULT"]), False)
                        check(index, family, "udp", int(e["DNS_PORT"]), False)
                    for proto, port in (("tcp", int(e["SSH_PUBLIC_PORT"])),
                                        ("udp", int(e["TAILSCALE_UDP_PORT"])), ("tcp", 59000)):
                        check(2, family, proto, port, False)
                    loopback = "127.0.0.1" if family == 4 else "::1"
                    cmd("python3", "-c", probe, loopback, "59000", "tcp", "1")
                    addr = addresses[0][1] + ".2" if family == 4 else addresses[0][2] + "::2"
                    cmd("nsenter", "-t", str(peers[2].pid), "-n", "python3", "-c", probe,
                        addr, "59001", "udp", "0", "59008")
                    wg_addr = addresses[2][1] + ".2" if family == 4 else addresses[2][2] + "::2"
                    cmd("nsenter", "-t", str(peers[0].pid), "-n", "python3", "-c", probe,
                        wg_addr, "59001", "udp", "0", "59009")
                    host_addr = addresses[2][1] + ".1" if family == 4 else addresses[2][2] + "::1"
                    ping = subprocess.run(["nsenter", "-t", str(peers[2].pid), "-n", "ping",
                                           "-" + str(family), "-c", "1", "-W", "1", host_addr], capture_output=True, timeout=5)
                    assert ping.returncode != 0, "Cold recovery allowed WG host ICMP"
                for index in (0, 1, 3):
                    cmd("nsenter", "-t", str(peers[index].pid), "-n", "ping", "-6", "-c", "1", "-W", "1",
                        addresses[index][2] + "::1")
                if saved is None:
                    path.unlink()
                else:
                    path.write_bytes(saved)
                if label == "WireGuard":
                    cmd("ip", "link", "set", "wg9", "name", "wg0")
                apply()
                repeat()
                for listing in snapshot():
                    assert e["CHAIN_STAGING_PREFIX"] not in listing, "Recovery staging survived successful apply"
                for family in (4, 6):
                    check(1, family, "tcp", int(e["SSH_PUBLIC_PORT"]), True)
                    check(1, family, "tcp", int(e["CADDY_HTTP_PORT"]), family == 4)
                    check(3, family, "tcp", int(e["SSH_PUBLIC_PORT"]), False)
                    addr = addresses[0][1] + ".2" if family == 4 else addresses[0][2] + "::2"
                    cmd("nsenter", "-t", str(peers[2].pid), "-n", "python3", "-c", probe,
                        addr, "59001", "udp", "1")
                assert_outsiders()
                print("PASS cold invalid " + label + ": recovery access, WG host/forward deny, full recovery and staging cleanup", flush=True)

            # Family-specific preservation: IPv4 still has its manual deny;
            # IPv6 has a baseline but a missing/misordered pre-ts settings jump.
            for placement in ("missing", "after-ts-input"):
                m.save_json(settings_path, dict(m.DEFAULT, firewall=deny_rules))
                apply()
                v4_before = snapshot()[:2]
                cmd("ip6tables", "-D", "INPUT", "-j", e["CHAIN_SETTINGS"])
                if placement == "after-ts-input":
                    cmd("ip6tables", "-A", "INPUT", "-j", e["CHAIN_SETTINGS"])
                settings_path.write_text("{broken settings")
                expect_load_failure("settings")
                assert v4_before == snapshot()[:2], "Healthy IPv4 manual deny changed during IPv6 recovery"
                guard = e["CHAIN_STAGING_PREFIX"] + "SAFE"
                assert cmd("ip6tables", "-S", "INPUT").splitlines()[1] == "-A INPUT -j " + guard
                check(1, 4, "tcp", int(e["SSH_PUBLIC_PORT"]), False)
                check(1, 6, "tcp", int(e["SSH_PUBLIC_PORT"]), True)
                check(1, 6, "tcp", 59000, False)
                m.save_json(settings_path, dict(m.DEFAULT, firewall=deny_rules))
                apply()
                repeat()
                check(1, 6, "tcp", int(e["SSH_PUBLIC_PORT"]), False)
                assert_outsiders()
            print("PASS missing/misordered settings guard recovers only the unsafe family", flush=True)
    finally:
        for process in echoes:
            process.terminate()
            process.wait(timeout=5)
            process.stdout.close()
        for sock in sockets:
            sock.close()
        for proc in peers:
            proc.terminate()
            proc.wait(timeout=5)


if __name__ == "__main__":
    main()
