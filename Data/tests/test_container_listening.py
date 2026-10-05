"""DD-215: a container on the host network has no port mappings, so Konsol lists the sockets its own
processes listen on (TCP LISTEN, unconnected bound UDP) from /proc. Unknown stays unknown (None),
never an empty list; the whole host is never attributed to a container."""
import ipaddress
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

PANEL = Path(__file__).resolve().parents[1] / "panel"
sys.path.insert(0, str(PANEL))
import master_containers as containers  # noqa: E402
import master_container_manager as manager  # noqa: E402

PAYLOAD = "/system.slice/app.service/libpod-payload-" + "ab" * 32
HEADER = {"tcp": "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode",
          "udp": "   sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode ref pointer drops"}


def enc(ip, port):
    """An address as /proc/net prints it: each 32-bit word in host byte order, then the port."""
    raw = ipaddress.ip_address(ip).packed
    if sys.byteorder == "little":
        raw = b"".join(raw[i:i + 4][::-1] for i in range(0, len(raw), 4))
    return raw.hex().upper() + ":%04X" % port


class ProcTree:
    """A minimal /proc and cgroup v2 tree: processes, their fds and the namespace's socket tables."""

    def __init__(self, root):
        self.proc, self.cgroups = root / "proc", root / "cgroup"
        self.tables = {"tcp": [], "tcp6": [], "udp": [], "udp6": []}

    def process(self, pid, cgroup=PAYLOAD, sockets=(), fds=True):
        d = self.proc / str(pid)
        d.mkdir(parents=True, exist_ok=True)
        (d / "cgroup").write_text("0::%s\n" % cgroup)
        if fds:
            (d / "fd").mkdir(exist_ok=True)
            os.symlink("/dev/null", d / "fd" / "0")
            for n, inode in enumerate(sockets, start=3):
                os.symlink("socket:[%s]" % inode, d / "fd" / str(n))
        return d

    def group(self, path, *pids):
        d = self.cgroups / path.lstrip("/")
        d.mkdir(parents=True, exist_ok=True)
        (d / "cgroup.procs").write_text("".join("%d\n" % p for p in pids))

    def sock(self, table, local, inode, state, remote=None):
        v6 = table.endswith("6")
        remote = remote or ("::" if v6 else "0.0.0.0", 0)
        self.tables[table].append("   %d: %s %s %s 00000000:00000000 00:00000000 00000000  1000        0 %s 1 0000000000000000 100 0 0 10 0"
                                  % (len(self.tables[table]), enc(*local), enc(*remote), state, inode))

    def write_tables(self, pid):
        net = self.proc / str(pid) / "net"
        net.mkdir(parents=True, exist_ok=True)
        for name, lines in self.tables.items():
            (net / name).write_text("\n".join([HEADER[name.rstrip("6")]] + lines) + "\n")

    def read(self, pid, **kw):
        return containers.listening(pid, proc=str(self.proc), cgroups=str(self.cgroups), **kw)


class ListeningTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.t = ProcTree(Path(tmp.name))

    def test_own_listeners_only_with_address_kinds(self):
        t = self.t
        t.process(4242, sockets=[11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24])
        t.process(4243, sockets=[12])  # a second process holding the same socket counts once
        t.group(PAYLOAD, 4242, 4243)
        t.sock("tcp", ("127.0.0.1", 61006), 11, "0A")
        t.sock("tcp", ("192.0.2.1", 51413), 12, "0A")
        t.sock("tcp", ("100.64.0.2", 51413), 13, "0A")
        t.sock("tcp6", ("fd7a:115c:a1e0::5", 51413), 14, "0A")
        t.sock("tcp6", ("::ffff:192.0.2.1", 8080), 15, "0A")           # IPv4-mapped → IPv4
        t.sock("tcp", ("192.0.2.1", 51413), 16, "01", ("198.51.100.7", 6881))  # a peer connection
        t.sock("udp", ("0.0.0.0", 6771), 17, "07")
        t.sock("udp6", ("::", 6771), 18, "07")
        t.sock("udp6", ("2001:db8::1", 40000), 19, "07")
        t.sock("udp", ("10.89.0.1", 51413), 20, "07")
        t.sock("udp6", ("fe80::1", 51413), 21, "07")                   # link-local: left out
        t.sock("udp", ("192.0.2.1", 53000), 22, "01", ("192.0.2.53", 53))   # connected UDP: not a listener
        t.sock("udp", ("0.0.0.0", 0), 23, "07")                        # unbound: no port
        t.sock("tcp", ("0.0.0.0", 9999), 24, "07")                     # closed TCP
        t.sock("tcp", ("0.0.0.0", 22), 99, "0A")                       # the host's own sshd
        t.write_tables(4242)
        rows = t.read(4242, wan={"192.0.2.1", "2001:db8::1"}, tailscale={"100.64.0.2"})
        self.assertEqual(rows, [
            {"address": "0.0.0.0", "port": 6771, "protocol": "udp", "scope": "all"},
            {"address": "::", "port": 6771, "protocol": "udp", "scope": "all"},
            {"address": "192.0.2.1", "port": 8080, "protocol": "tcp", "scope": "wan"},
            {"address": "2001:db8::1", "port": 40000, "protocol": "udp", "scope": "wan"},
            {"address": "192.0.2.1", "port": 51413, "protocol": "tcp", "scope": "wan"},
            {"address": "100.64.0.2", "port": 51413, "protocol": "tcp", "scope": "tailscale"},
            {"address": "fd7a:115c:a1e0::5", "port": 51413, "protocol": "tcp", "scope": "tailscale"},
            {"address": "10.89.0.1", "port": 51413, "protocol": "udp", "scope": "other"},
            {"address": "127.0.0.1", "port": 61006, "protocol": "tcp", "scope": "local"}])

    def test_child_cgroups_count_and_the_root_cgroup_never_widens(self):
        t = self.t
        t.process(4242, sockets=[])
        t.process(5000, cgroup=PAYLOAD + "/worker", sockets=[31])
        t.group(PAYLOAD, 4242)
        t.group(PAYLOAD + "/worker", 5000)
        t.sock("tcp", ("127.0.0.1", 7000), 31, "0A")
        t.write_tables(4242)
        self.assertEqual([r["port"] for r in t.read(4242)], [7000])
        # A container left in the root cgroup is read by its own process only, never the host's.
        t.process(6000, cgroup="/", sockets=[])
        t.group("/", 6000, 5000)
        t.write_tables(6000)
        self.assertEqual(t.read(6000), [])

    def test_unknown_is_none_not_an_empty_list(self):
        t = self.t
        for bad in (None, 0, -1, True, "4242", 4.2):
            self.assertIsNone(t.read(bad))
        t.process(4242, fds=False)
        t.group(PAYLOAD, 4242)
        t.write_tables(4242)
        self.assertIsNone(t.read(4242), "unreadable fds are unknown")
        t.process(4300, sockets=[1])
        t.group(PAYLOAD, 4300)
        self.assertIsNone(t.read(4300), "no socket table is unknown")
        t.write_tables(4300)
        self.assertEqual(t.read(4300), [], "readable and nothing listening")

    def test_scope_prefers_the_hosts_own_addresses(self):
        scope = lambda ip, **kw: containers.socket_scope(ipaddress.ip_address(ip), **kw)
        # Carrier-grade NAT shares 100.64.0.0/10: the server's own WAN address wins over the range.
        self.assertEqual(scope("100.70.1.2", wan={"100.70.1.2"}), "wan")
        self.assertEqual(scope("100.70.1.2"), "tailscale")
        self.assertEqual(scope("::1"), "local")
        self.assertEqual(scope("169.254.1.1"), "link")
        self.assertEqual(scope("203.0.113.9"), "other")


class ManagerListeningTests(unittest.TestCase):
    """The inventory reads sockets only for a running host-network container, with the host's addresses."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        env = {"MODULES_FILE": str(root / "modules"), "MODULES_DIR": str(root / "packages"), "RUNTIME_DIR": str(root / "run"),
               "WAN_IPV4": "192.0.2.1", "WAN_IPV6": "2001:db8::1", "TAILSCALE_IPV4": "100.64.0.2", "TAILSCALE_IPV6": ""}
        (root / "modules").write_text("")
        (root / "state").write_text("".join("%s=%s\n" % kv for kv in env.items()))
        self.containers = {}
        p = types.SimpleNamespace(args=types.SimpleNamespace(state=str(root / "state"), master_modul="/fixture/master-modul"),
                                  run_tool=self.fake_run, env=lambda: {}, module_busy=lambda _: False)
        self.service = manager.Service(p)

    def add(self, name, state, network, pid):
        self.containers[name] = (state, network, pid)

    def fake_run(self, argv, timeout=30, binary=False):
        if argv[:2] == ["podman", "version"]:
            return 0, "5.4.2", ""
        if argv[:2] == ["podman", "ps"]:
            return 0, json.dumps([{"Id": "%012d" % i, "Names": [n], "Image": "example.org/app@sha256:" + "c" * 64, "State": s,
                                   "Networks": [] if net == "host" else [net], "Namespaces": {"Net": net if net == "host" else ""}}
                                  for i, (n, (s, net, _)) in enumerate(self.containers.items(), start=1)]), ""
        if argv[:2] == ["podman", "inspect"]:
            s, net, pid = self.containers[argv[-1]]
            return 0, json.dumps([{"Id": "f" * 64, "Name": argv[-1], "State": {"Status": s, "Pid": pid}, "HostConfig": {"NetworkMode": net},
                                   "Config": {"Labels": {"PODMAN_SYSTEMD_UNIT": argv[-1] + ".service"}}}]), ""
        if argv[:2] in (["podman", "images"], ["podman", "system"], ["podman", "stats"], ["podman", "volume"], ["podman", "network"]):
            return 0, "[]", ""
        raise AssertionError(argv)

    def test_only_running_host_network_rows_are_read(self):
        self.add("hostapp", "running", "host", 4242)
        self.add("bridged", "running", "konsol", 4343)
        self.add("parked", "exited", "host", 0)
        calls = []
        fake = lambda pid, wan=(), tailscale=(): calls.append((pid, set(wan), set(tailscale))) or [{"address": "127.0.0.1", "port": 61006, "protocol": "tcp", "scope": "local"}]
        apps = {n: {"name": n, "image": "example.org/app@sha256:" + "c" * 64, "unit": n + ".service", "module_id": n,
                    "module_state": "calisiyor", "adapter": ""} for n in ("hostapp", "bridged", "parked")}
        with patch.object(manager, "listening", fake), patch.object(manager, "app_specs", return_value=apps), \
             patch.object(manager, "app_config", return_value={"revision": "d" * 64, "config": {}, "editable": [], "protected_mounts": []}):
            rows = {r["name"]: r for r in self.service.view().liste()["containers"]}
            detail = self.service.view().ayrinti("hostapp")
        self.assertEqual(calls[0], (4242, {"192.0.2.1", "2001:db8::1"}, {"100.64.0.2"}))
        self.assertEqual(len(calls), 2, "the list row and the detail; never the bridged or stopped container")
        self.assertEqual(rows["hostapp"]["listening"][0]["port"], 61006)
        self.assertEqual(detail["listening"][0]["port"], 61006)
        self.assertIsNone(rows["bridged"]["listening"])
        self.assertIsNone(rows["parked"]["listening"])


class PublishedScopeTests(unittest.TestCase):
    """DD-217: a publication on the server's WAN address reads as internet access, not "another address"."""

    def test_published_addresses_are_labelled_by_access(self):
        env = {"WAN_IPV4": "192.0.2.1", "WAN_IPV6": "", "TAILSCALE_IPV4": "100.64.0.2", "TAILSCALE_IPV6": ""}
        cases = {"127.0.0.1": "local", "::1": "local", "100.64.0.2": "tailscale", "192.0.2.1": "public",
                 "0.0.0.0": "public", "::": "public", "": "public", "10.89.0.1": "other", "100.64.0.9": "other"}
        for ip, scope in cases.items():
            with self.subTest(ip=ip):
                self.assertEqual(manager.port_scope(ip, env), scope)

    def test_detail_names_the_bridge_networks(self):
        inspect = [{"Id": "f" * 64, "Name": "app", "State": {"Status": "running"}, "Config": {"Labels": {}},
                    "HostConfig": {"NetworkMode": "bridge", "PortBindings": {}},
                    "NetworkSettings": {"Ports": {}, "Networks": {"torrent": {}}}}]
        reader = containers.Containers(lambda argv, timeout: (0, json.dumps(inspect), ""))
        self.assertEqual(reader.ayrinti("app")["network"], "torrent")


if __name__ == "__main__":
    unittest.main()
