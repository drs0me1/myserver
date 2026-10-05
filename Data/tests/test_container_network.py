"""Container publication validation and owned nft policy; no host mutations."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "panel"))
SPEC = importlib.util.spec_from_file_location("container_network", Path(__file__).resolve().parents[1] / "panel/master_container_network.py")
network = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(network)
DATA = Path(__file__).resolve().parents[1]


def port(scope="local", host=18080, container=8080, protocol="tcp", **extra):
    return dict(scope=scope, host_port=host, container_port=container, protocol=protocol, **extra)


class NetworkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = {"KONTEYNER_STATE_DIR": self.tmp.name, "RUNTIME_DIR": self.tmp.name,
                    "KONTEYNER_NETWORK": "konsol", "KONTEYNER_BRIDGE_PREFIX": "ksl",
                    "KONTEYNER_NFT_TABLE": "master_containers", "TAILSCALE_IF": "tailscale0",
                    "SSH_PUBLIC_PORT": "22", "DNS_PORT": "53",
                    "VPN_BLOCK_DEST4": network.env_read(DATA / "config/defaults.env")["VPN_BLOCK_DEST4"]}
        self.calls = []
        self.ss = ""
        self.podman = []
        self.inspected = None
        self.tail = "100.64.0.1"

    def runner(self, argv, timeout=20):
        self.calls.append(argv)
        if argv[:4] == ["ip", "-j", "address", "show"]:
            dev = argv[-1]
            rows = [] if dev == "tailscale0" and not self.tail else [{"ifname": dev, "addr_info": [
                {"family": "inet", "local": self.tail if dev == "tailscale0" else "192.0.2.1", "scope": "global"}]}]
            return subprocess.CompletedProcess(argv, 0, json.dumps(rows), "")
        if argv[:4] == ["ip", "-j", "route", "show"]:
            return 0, '[{"dev":"eth0","metric":100}]', ""
        if argv[0] == "ss":
            return 0, self.ss, ""
        if argv[:3] == ["podman", "ps", "-a"]:
            return 0, json.dumps(self.podman), ""
        if argv[:3] == ["podman", "inspect", "--type"]:
            return 0, json.dumps([self.inspected]), ""
        self.fail("Unexpected command: " + repr(argv))

    def validate(self, ports, **kw):
        return network.validate_ports(self.env, ports, "example", run=self.runner, **kw)

    def definitions(self, *rows):
        root = Path(self.tmp.name) / "definitions"
        root.mkdir(exist_ok=True)
        for row in rows:
            (root / (row["name"] + ".json")).write_text(json.dumps(row))

    def test_explicit_bindings_and_no_mutations(self):
        rows = self.validate([port(), port("tailscale", 18081), port("public", 18082, public_ack=True)])
        self.assertEqual(network.bindings(self.env, rows, run=self.runner), [
            "127.0.0.1:18080:8080/tcp", "100.64.0.1:18081:8080/tcp", "0.0.0.0:18082:8080/tcp"])
        self.assertFalse(any(c[0] in ("nft", "iptables", "ip6tables") for c in self.calls))

    def test_public_requires_boolean_explicit_ack(self):
        for value in (None, False, "true", 1):
            with self.subTest(value=value), self.assertRaises(network.NetworkError):
                self.validate([port("public", public_ack=value)])

    def test_types_ranges_protocols_and_unknown_keys(self):
        bad = [port(host=True), port(host=0), port(host=65536), port(host="8080"), port(host=3.5),
               port(container=0), port(protocol="sctp"), port(protocol="TCP"), port(scope="all"),
               port(host_ip="0.0.0.0")]
        for row in bad:
            with self.subTest(row=row), self.assertRaises(network.NetworkError):
                self.validate([row])

    def test_reserved_even_if_not_listening(self):
        for host in (22, 53):
            with self.subTest(host=host), self.assertRaises(network.NetworkError):
                self.validate([port(host=host)])

    def test_package_ports_reserved(self):
        base = Path(self.tmp.name) / "packages" / "example"
        base.mkdir(parents=True)
        (base / "example.env").write_text("EXAMPLE_UI_PORT=19999\n")
        self.env["MODULES_DIR"] = str(base.parent)
        with self.assertRaises(network.NetworkError):
            self.validate([port(host=19999)])

    def test_stopped_package_effective_port_is_reserved(self):
        base = Path(self.tmp.name) / "packages" / "torrent"
        base.mkdir(parents=True)
        (base / "torrent.env").write_text("TORRENT_UI_PORT=61015\n")
        (base / "paket.env").write_text('PAKET_AD="torrent"\nPAKET_AYAR_ANAHTARLAR="TORRENT_UI_PORT"\n')
        self.env["MODULES_DIR"] = str(base.parent)
        overrides = Path(self.tmp.name) / "package-overrides"
        overrides.mkdir()
        override = overrides / "torrent.env"
        override.write_text("TORRENT_UI_PORT=61016\n")
        override.chmod(0o600)
        self.env["PACKAGE_OVERRIDES_DIR"] = str(overrides)
        # No running container or listener exists: the durable choice alone reserves it.
        for host in (61015, 61016):
            with self.subTest(host=host), self.assertRaises(network.NetworkError):
                self.validate([port(host=host)])

    def test_invalid_package_override_fails_closed(self):
        base = Path(self.tmp.name) / "packages" / "torrent"
        base.mkdir(parents=True)
        (base / "torrent.env").write_text("TORRENT_UI_PORT=61015\n")
        (base / "paket.env").write_text('PAKET_AD="torrent"\nPAKET_AYAR_ANAHTARLAR="TORRENT_UI_PORT"\n')
        self.env["MODULES_DIR"] = str(base.parent)
        overrides = Path(self.tmp.name) / "package-overrides"
        overrides.mkdir()
        override = overrides / "torrent.env"
        override.write_text("TORRENT_UI_PORT=not-a-port\n")
        override.chmod(0o600)
        self.env["PACKAGE_OVERRIDES_DIR"] = str(overrides)
        with self.assertRaises(network.NetworkError):
            self.validate([port(host=19998)])

    def test_duplicate_overlap_and_independent_protocols(self):
        for rows in ([port(), port()], [port(), port("public", public_ack=True)]):
            with self.subTest(rows=rows), self.assertRaises(network.NetworkError):
                self.validate(rows)
        self.assertEqual(len(self.validate([port(), port(protocol="udp")])), 2)
        self.assertEqual(len(self.validate([port(), port("tailscale")])), 2)

    def test_saved_stopped_definition_reserves_binding_except_self(self):
        self.definitions({"name": "other", "network": "bridge", "ports": [port()], "manual_stop": True})
        with self.assertRaises(network.NetworkError):
            self.validate([port()])
        self.assertEqual(len(network.validate_ports(self.env, [port()], "other", run=self.runner)), 1)

    def test_socket_conflicts_including_ipv6_wildcard(self):
        for addr in ("0.0.0.0:18080", "[::]:18080", "*:18080", "127.0.0.1:18080"):
            self.ss = "tcp LISTEN 0 128 %s *:*\n" % addr
            with self.subTest(addr=addr), self.assertRaises(network.NetworkError):
                self.validate([port()])
        self.ss = "udp UNCONN 0 0 127.0.0.1:18080 0.0.0.0:*\n"
        self.assertEqual(len(self.validate([port()])), 1)

    def test_external_podman_mapping_conflicts_even_without_socket(self):
        self.podman = [{"Names": ["foreign"], "Ports": [{"host_ip": "", "host_port": 18080,
                          "container_port": 80, "protocol": "tcp", "range": 1}]}]
        with self.assertRaises(network.NetworkError):
            self.validate([port()])

    def own_runtime(self):
        self.podman = [{"Id": "a" * 64, "Names": ["example"], "Ports": [
            {"host_ip": "127.0.0.1", "host_port": 18080, "container_port": 8080, "protocol": "tcp", "range": 1}]}]
        self.inspected = {"Id": "a" * 64, "Name": "example", "State": {"Running": True, "ConmonPid": 43210},
                          "Config": {"Labels": {"io.master-stack.managed": "konsol", "PODMAN_SYSTEMD_UNIT": "konsol-example.service"}},
                          "HostConfig": {"PortBindings": {"8080/tcp": [
                              {"HostIp": "127.0.0.1", "HostPort": "18080"},
                              {"HostIp": "100.64.0.1", "HostPort": "18081"},
                              {"HostIp": "0.0.0.0", "HostPort": "18082"}]}}}
        self.ss = 'tcp LISTEN 0 4096 127.0.0.1:18080 0.0.0.0:* users:(("conmon",pid=43210,fd=5))\n'

    def test_running_target_conmon_bindings_allow_save_and_restart_for_all_scopes(self):
        self.own_runtime()
        self.ss += 'tcp LISTEN 0 4096 100.64.0.1:18081 0.0.0.0:* users:(("conmon",pid=43210,fd=6))\n'
        self.ss += 'tcp LISTEN 0 4096 0.0.0.0:18082 0.0.0.0:* users:(("conmon",pid=43210,fd=7))\n'
        rows = [port(container=9090), port('tailscale', 18081), port('public', 18082, public_ack=True)]
        self.assertEqual(len(self.validate(rows)), 3)
        self.assertIn(['ss', '-H', '-lntup'], self.calls)

    def test_owned_udp_mapping_is_distinct_from_tcp_and_requires_complete_socket_owners(self):
        self.own_runtime()
        self.inspected['HostConfig']['PortBindings']['8080/udp'] = [{'HostIp': '127.0.0.1', 'HostPort': '18080'}]
        self.ss += 'udp UNCONN 0 0 127.0.0.1:18080 0.0.0.0:* users:(("conmon",pid=43210,fd=8))\n'
        self.assertEqual(len(self.validate([port(), port(protocol='udp')])), 2)
        self.ss = self.ss.replace('fd=8))', 'fd=8),unknown-owner)')
        with self.assertRaises(network.NetworkError):
            self.validate([port(protocol='udp')])

    def test_conmon_exception_requires_exact_live_owner_and_runtime_mapping(self):
        for defect in ('foreign-pid', 'foreign-process', 'mixed-owners', 'missing-owner', 'missing-mapping',
                       'different-address', 'different-protocol', 'stopped', 'missing-conmon', 'foreign-controller',
                       'name-mismatch', 'id-mismatch', 'missing-inventory', 'definition-only'):
            self.own_runtime()
            if defect == 'foreign-pid': self.ss = self.ss.replace('43210', '43211')
            elif defect == 'foreign-process': self.ss = self.ss.replace('conmon', 'nginx')
            elif defect == 'mixed-owners': self.ss = self.ss.replace('fd=5))', 'fd=5),("nginx",pid=43211,fd=6))')
            elif defect == 'missing-owner': self.ss = self.ss.split(' users:')[0] + '\n'
            elif defect == 'missing-mapping': self.inspected['HostConfig']['PortBindings'] = {}
            elif defect == 'different-address': self.inspected['HostConfig']['PortBindings']['8080/tcp'][0]['HostIp'] = '127.0.0.2'
            elif defect == 'different-protocol': self.inspected['HostConfig']['PortBindings'] = {'8080/udp': [{'HostIp': '127.0.0.1', 'HostPort': '18080'}]}
            elif defect == 'stopped': self.inspected['State']['Running'] = False
            elif defect == 'missing-conmon': self.inspected['State'].pop('ConmonPid')
            elif defect == 'foreign-controller': self.inspected['Config']['Labels']['PODMAN_SYSTEMD_UNIT'] = 'foreign.service'
            elif defect == 'name-mismatch': self.inspected['Name'] = 'foreign'
            elif defect == 'id-mismatch': self.inspected['Id'] = 'b' * 64
            elif defect in ('missing-inventory', 'definition-only'):
                self.podman = []
                if defect == 'definition-only': self.definitions({'name': 'example', 'network': 'bridge', 'ports': [port()]})
            with self.subTest(defect=defect), self.assertRaises(network.NetworkError):
                self.validate([port()])

    def test_proven_standalone_adoption_owns_conmon_but_another_listener_still_conflicts(self):
        self.own_runtime()
        self.inspected['Config']['Labels'] = {}
        self.assertEqual(len(self.validate([port()])), 1)
        self.ss += 'tcp LISTEN 0 128 127.0.0.2:18080 0.0.0.0:* users:(("other",pid=12345,fd=4))\n'
        with self.assertRaises(network.NetworkError):
            self.validate([port('public', public_ack=True)])

    def test_tailscale_resolution_never_uses_stale_env_or_wildcard(self):
        self.env["TAILSCALE_IPV4"] = "100.64.0.9"
        for value in (None, "0.0.0.0", "127.0.0.1", "192.0.2.1", "::1", "100.64.0.1;drop"):
            self.tail = value
            with self.subTest(value=value), self.assertRaises(network.NetworkError):
                network.bindings(self.env, [port("tailscale")], run=self.runner)

    def test_fail_closed_on_unreadable_runtime_inventory(self):
        with self.assertRaises(network.NetworkError):
            network.validate_ports(self.env, [port()], "example", run=lambda *a, **k: (1, "", "failed"))

    def test_policy_no_blanket_established_and_scoped_dnat(self):
        rows = [{"name": "example", "network": "bridge", "ports": [port(), port("tailscale", 18081),
                 port("public", 18082, public_ack=True)]}]
        policy = network.policy(self.env, rows, run=self.runner)
        chain = next(x["chain"] for x in policy if "chain" in x)
        self.assertEqual((chain["family"], chain["hook"], chain["prio"], chain["policy"]), ("inet", "forward", -10, "accept"))
        text = json.dumps(policy)
        self.assertIn('"direction"', text)
        self.assertIn('"reply"', text)
        self.assertIn('"dnat"', text)
        self.assertIn('"tailscale0"', text)
        self.assertIn('"192.0.2.1"', text)
        self.assertIn('"100.64.0.1"', text)
        self.assertNotIn('"ip6"', text, "IPv6 ingress is denied, not implicitly opened")
        self.assertNotIn('18080', text, "local publications get no forward permit")
        self.assertEqual(policy[-1]["rule"]["expr"][-1], {"drop": None})

    def package(self, quadlet, state="calisiyor", network_name="torrent"):
        """DD-217: a registered package on its own bridge with a placed Quadlet (None: stopped, no unit)."""
        root = Path(self.tmp.name)
        (root / "mods/torrent").mkdir(parents=True, exist_ok=True)
        (root / "units").mkdir(exist_ok=True)
        (root / "modules").write_text("torrent\t%s\n" % state)
        (root / "mods/torrent/paket.env").write_text('PAKET_KONTEYNER="qbittorrent.container"\nPAKET_KONTEYNER_AG="%s"\n' % network_name)
        if quadlet is not None:
            (root / "units/qbittorrent.container").write_text(quadlet)
        self.env.update(MODULES_FILE=str(root / "modules"), MODULES_DIR=str(root / "mods"), KONTEYNER_BIRIM_DIR=str(root / "units"))

    def rules_for(self, policy, bridge):
        return [x["rule"]["expr"] for x in policy if "rule" in x and {"match": {"op": "==", "left": {"meta": {"key": "oifname"}}, "right": bridge}} in x["rule"]["expr"]]

    def test_package_bridge_lets_through_only_its_wan_publication(self):
        self.package("[Container]\nNetwork=torrent\nPublishPort=127.0.0.1:61006:61006/tcp\n"
                     "PublishPort=192.0.2.1:61008:61008/tcp\nPublishPort=192.0.2.1:61008:61008/udp\n"
                     "PublishPort=198.51.100.9:7000:7000/tcp\nPublishPort=8080\n")
        policy = network.policy(self.env, [], run=self.runner)
        bridge = network.bridge_name(self.env, "torrent")
        rules = self.rules_for(policy, bridge)
        text = json.dumps(rules)
        # Intra-bridge, then exactly the two WAN publications (TCP and UDP) from eth0 to 192.0.2.1:61008.
        self.assertEqual(len(rules), 3)
        self.assertEqual(text.count('"eth0"'), 2)
        self.assertIn('"udp"', text)
        self.assertNotIn("61006", text, "the loopback interface needs no forward path")
        self.assertNotIn("198.51.100.9", text, "an address that is not the server's WAN or Tailscale one is not let through")
        self.assertNotIn("tailscale0", text)
        self.assertEqual(policy[-1]["rule"]["expr"][-1], {"drop": None})

    def test_stopped_unregistered_or_mismatched_package_publishes_nothing(self):
        self.package(None)
        bridge = network.bridge_name(self.env, "torrent")
        self.assertEqual(self.rules_for(network.policy(self.env, [], run=self.runner), bridge), [])
        self.package("[Container]\nNetwork=torrent\nPublishPort=192.0.2.1:61008:61008/tcp\n", state="calisiyor")
        Path(self.env["MODULES_FILE"]).write_text("")
        self.assertEqual(self.rules_for(network.policy(self.env, [], run=self.runner), bridge), [])
        # An installer run renders the new manifest before it places the new Quadlet: the old one on
        # another network is let through nothing, and the firewall still applies (found live on nrm).
        self.package("[Container]\nNetwork=host\nPublishPort=192.0.2.1:61008:61008/tcp\n")
        policy = network.policy(self.env, [], run=self.runner)
        self.assertEqual(self.rules_for(policy, bridge), [])
        self.assertEqual(policy[-1]["rule"]["expr"][-1], {"drop": None})

    def test_policy_identity_and_corrupt_definitions_fail_closed(self):
        with self.assertRaises(network.NetworkError):
            network.policy(dict(self.env, KONTEYNER_BRIDGE_PREFIX="*"), [], run=self.runner)
        self.definitions({"name": "broken", "network": "bridge", "ports": [port("public")]})
        with self.assertRaises(network.NetworkError):
            network.policy(self.env, network.read_definitions(self.env), run=self.runner)

    def egress_rules(self, objects):
        return [o["rule"]["expr"] for o in objects if "rule" in o]

    def test_container_egress_rules_come_after_the_hot_path_and_replies(self):
        # DD-224: exit-node/WireGuard traffic leaves after one rule; replies to publications pass
        # before any egress drop; then IPv6, tailscale0 and every block-list prefix, in list order.
        rules = self.egress_rules(network.policy(self.env, [], run=self.runner))
        m = lambda key, right, op="==": {"match": {"op": op, "left": {"meta": {"key": key}}, "right": right}}
        self.assertEqual(rules[0], [m("iifname", "ksl*", "!="), m("oifname", "ksl*", "!="), {"return": None}])
        self.assertEqual([r[-1] for r in rules[1:3]], [{"return": None}] * 2)
        self.assertTrue(all(r[0]["match"]["left"] == {"ct": {"key": "direction"}} for r in rules[1:3]))
        egress = [m("iifname", "ksl*"), m("oifname", "ksl*", "!=")]
        self.assertEqual(rules[3], egress + [m("nfproto", "ipv6"), {"drop": None}])
        self.assertEqual(rules[4], [m("iifname", "ksl*"), m("oifname", "tailscale0"), {"drop": None}])
        blocks = self.env["VPN_BLOCK_DEST4"].split()
        dests = []
        for r in rules[5:5 + len(blocks)]:
            self.assertEqual(r[:2], egress)
            self.assertEqual(r[2]["match"]["left"], {"payload": {"protocol": "ip", "field": "daddr"}})
            self.assertEqual(r[-1], {"drop": None})
            right = r[2]["match"]["right"]
            dests.append(right if isinstance(right, str) else "%s/%d" % (right["prefix"]["addr"], right["prefix"]["len"]))
        self.assertEqual(dests, blocks)
        self.assertEqual(rules[5 + len(blocks)], [m("oifname", "ksl*", "!="), {"return": None}])
        # One rule per prefix, no literal list in the code: the block list has one owner (defaults.env).
        source = (DATA / "panel/master_container_network.py").read_text(encoding="utf-8")
        for literal in ("169.254", "172.16", "192.168"):
            self.assertNotIn(literal, source)
        single = self.egress_rules(network.policy(dict(self.env, VPN_BLOCK_DEST4="203.0.113.9/32 10.0.0.0/8"), [], run=self.runner))
        self.assertEqual([r[2]["match"]["right"] for r in single[5:7]],
                         ["203.0.113.9", {"prefix": {"addr": "10.0.0.0", "len": 8}}])

    def test_container_egress_block_list_fails_closed(self):
        for value in (None, "", "fd00::/8", "10.0.0.1/8", "10.0.0.0/33", "not-a-network"):
            env = dict(self.env)
            if value is None:
                env.pop("VPN_BLOCK_DEST4")
            else:
                env["VPN_BLOCK_DEST4"] = value
            with self.subTest(value=value), self.assertRaises(network.NetworkError) as err:
                network.policy(env, [], run=self.runner)
            self.assertEqual(err.exception.status, 503)

    def test_health_detects_a_missing_or_reordered_egress_rule(self):
        expected = network.policy(self.env, [], run=self.runner)
        rules = [i for i, o in enumerate(expected) if "rule" in o]
        missing = [o for i, o in enumerate(expected) if i != rules[6]]
        self.assertFalse(network.same_policy(expected, {"nftables": copy.deepcopy(missing)}))
        swapped = copy.deepcopy(expected)
        swapped[rules[5]], swapped[rules[6]] = swapped[rules[6]], swapped[rules[5]]
        self.assertFalse(network.same_policy(expected, {"nftables": swapped}))
        self.assertTrue(network.same_policy(expected, {"nftables": copy.deepcopy(expected)}))

    def test_a_loopback_port_change_leaves_the_guard_unchanged(self):
        # DD-223: the package worker restarts qBittorrent after an interface-port change without
        # applying the guard; the start check passes because loopback rows are not in the policy.
        root = Path(self.tmp.name)
        (root / "mods/torrent").mkdir(parents=True)
        (root / "units").mkdir()
        (root / "mods/torrent/paket.env").write_text('PAKET_KONTEYNER="qbittorrent.container"\nPAKET_KONTEYNER_AG="torrent"\n')
        (root / "kayit").write_text("torrent\tcalisiyor\n")
        env = dict(self.env, MODULES_FILE=str(root / "kayit"), MODULES_DIR=str(root / "mods"),
                   KONTEYNER_BIRIM_DIR=str(root / "units"))
        quadlet = "[Container]\nNetwork=torrent\nPublishPort=127.0.0.1:{0}:{0}/tcp\nPublishPort=192.0.2.1:{1}:{1}/tcp\n"
        placed = root / "units/qbittorrent.container"
        placed.write_text(quadlet.format(62947, 63851))
        before = network.policy(env, [], run=self.runner)
        self.assertTrue(any("63851" in json.dumps(o) for o in before), "the WAN publication is let through")
        placed.write_text(quadlet.format(61997, 63851))
        self.assertEqual(network.policy(env, [], run=self.runner), before)
        # A peer-port change does change it; the worker applies the guard before that start.
        placed.write_text(quadlet.format(61997, 63999))
        self.assertNotEqual(network.policy(env, [], run=self.runner), before)

    def test_check_names_a_missing_guard_table(self):
        # DD-223: a container unit's start precondition says why the container waits.
        def missing(argv, timeout=20):
            if argv[:3] == ["nft", "-j", "list"]:
                return 1, "", "Error: No such file or directory\nlist table inet master_containers"
            return self.runner(argv, timeout)
        with self.assertRaises(network.NetworkError) as err:
            network.check(self.env, run=missing)
        self.assertEqual(str(err.exception), "Konteyner yönlendirme koruması eksik veya güncel değil.")

        def broken(argv, timeout=20):
            if argv[:3] == ["nft", "-j", "list"]:
                return 1, "", "Error: Operation not permitted"
            return self.runner(argv, timeout)
        with self.assertRaises(network.NetworkError) as err:
            network.check(self.env, run=broken)
        self.assertEqual(str(err.exception), "Ağ durumu okunamadı: nft")

    def test_health_comparison_checks_rules_not_only_existence(self):
        expected = network.policy(self.env, [], run=self.runner)
        actual = {"nftables": [{"metainfo": {"version": "test"}}] + copy.deepcopy(expected)}
        for row in actual["nftables"][1:]:
            next(iter(row.values()))["handle"] = 3
        self.assertTrue(network.same_policy(expected, actual))
        actual["nftables"][-1]["rule"]["expr"][-1] = {"accept": None}
        self.assertFalse(network.same_policy(expected, actual))

    def test_health_accepts_nft_inferred_protocols_but_not_changed_tuple(self):
        expected = network.policy(self.env, [{"name": "example", "network": "bridge",
            "ports": [port("tailscale", 18081)]}], run=self.runner)
        canonical = copy.deepcopy(expected)
        for obj in canonical:
            if "rule" not in obj:
                continue
            expr = obj["rule"]["expr"]
            implied = any(e.get("match", {}).get("left", {}).get("ct", {}).get("key") == "daddr" for e in expr)
            obj["rule"]["expr"] = [e for e in expr if not (
                e.get("match", {}).get("left", {}).get("meta", {}).get("key") == "l4proto"
                or implied and e.get("match", {}).get("left", {}).get("meta", {}).get("key") == "nfproto")]
            for e in expr:
                ct = e.get("match", {}).get("left", {}).get("ct", {})
                ct.pop("family", None)
        self.assertTrue(network.same_policy(expected, {"nftables": canonical}))
        changed = copy.deepcopy(canonical)
        for obj in changed:
            for e in obj.get("rule", {}).get("expr", []):
                if e.get("match", {}).get("left", {}).get("ct", {}).get("key") == "daddr":
                    e["match"]["right"] = "100.64.0.2"
        self.assertFalse(network.same_policy(expected, {"nftables": changed}))
        changed = copy.deepcopy(canonical)
        changed[-2]["rule"]["expr"] = [e for e in changed[-2]["rule"]["expr"] if "payload" not in e.get("match", {}).get("left", {})]
        self.assertFalse(network.same_policy(expected, {"nftables": changed}))


if __name__ == "__main__":
    unittest.main()
