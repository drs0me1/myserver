"""Read-only firewall categories and socket bindings; never invoke host networking."""
import importlib.machinery
import importlib.util
from pathlib import Path
import types
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "panel" / "master-panel"
loader = importlib.machinery.SourceFileLoader("firewall_view_panel", str(SOURCE))
spec = importlib.util.spec_from_loader(loader.name, loader)
panel = importlib.util.module_from_spec(spec)
loader.exec_module(panel)


class FirewallViewTests(unittest.TestCase):
    def setUp(self):
        self.tailnet = patch.object(panel.master_settings, "tailnet_ports", return_value=[]).start()
        self.addCleanup(patch.stopall)
        self.p = panel.Panel(types.SimpleNamespace(state="/unused", state_env=False))
        self.env = {"TAILSCALE_IF": "tailscale0", "TAILSCALE_IPV4": "100.64.0.2",
                    "TAILSCALE_IPV6": "fd7a:115c:a1e0::2", "WAN_INTERFACE": "eth0",
                    "WAN_IPV4": "192.0.2.1", "WAN_IPV6": "2001:db8::1", "TORRENT_UI_PORT": "61004", "FILES_PANEL_PORT": "61009"}
        self.nets = [{"iface": "wg0", "server4": "10.8.0.1", "server6": "fd00::1",
                      "label": "Home", "active": True, "scope": "ui", "port": 51820},
                     {"iface": "wg1", "server4": "10.9.0.1", "server6": "fd01::1",
                      "label": "Mobile", "active": False, "scope": "inet", "port": 51821}]

    def test_bindings_use_addresses_and_interfaces_not_private_prefix_guesses(self):
        cases = {"0.0.0.0": "any", "::": "any", "*": "any", "127.0.0.2": "lo", "::1": "lo",
                 "100.64.0.2": "tail", "fd7a:115c:a1e0:0:0:0:0:2": "tail",
                 "fe80::123%tailscale0": "tail", "fe80::123%eth0": "wan",
                 "192.0.2.1": "wan", "2001:db8:0:0:0:0:0:1": "wan",
                 "10.8.0.1": "wg0", "fd01::1": "wg1", "fe80::123%wg1": "wg1",
                 "100.64.0.99": "unknown", "fd7a:115c:a1e0::99": "unknown",
                 "fe80::123%other0": "unknown", "10.10.0.1": "unknown", "not-ip": "unknown"}
        for address, expected in cases.items():
            with self.subTest(address=address):
                self.assertEqual(self.p.binding_scope(address, self.env, self.nets), expected)

    def test_ss_ipv6_zone_outside_brackets_and_normal_brackets(self):
        outputs = [b"tcp LISTEN 0 10 0.0.0.0:22 0.0.0.0:*\nignored\n",
                   b"udp UNCONN 0 0 [fe80::123]%tailscale0:53 [::]:*\n"
                   b"tcp LISTEN 0 10 [::1]:61008 [::]:*\n"
                   b"tcp LISTEN 0 10 [fd01::1]:61004 [::]:*\n"]
        with patch.object(panel.subprocess, "run", side_effect=[types.SimpleNamespace(returncode=0, stdout=o) for o in outputs]) as run:
            rows = self.p.listeners(self.env, self.nets)
        self.assertEqual([(r["address"], r["scope"]) for r in rows],
                         [("0.0.0.0", "any"), ("fe80::123%tailscale0", "tail"), ("::1", "lo"), ("fd01::1", "wg1")])
        self.assertEqual([c.args[0] for c in run.call_args_list],
                         [["ss", "-H", "-lntu", "-4"], ["ss", "-H", "-lntu", "-6"]])

    def test_failed_socket_read_is_not_an_empty_listener_list(self):
        for result in (types.SimpleNamespace(returncode=1), OSError("missing"),
                       panel.subprocess.TimeoutExpired("ss", 10)):
            with self.subTest(result=result), patch.object(panel.subprocess, "run") as run:
                if isinstance(result, Exception):
                    run.side_effect = result
                else:
                    run.return_value = result
                self.assertIsNone(self.p.listeners(self.env, []))

    def test_bridge_package_peer_port_is_a_fixed_ipv4_publication(self):
        # DD-217/219: the peer port is published into the package bridge on IPv4 only and let through by
        # the container guard; Settings shows it without an INPUT toggle and without an IPv6 row.
        import shutil
        import tempfile
        mods = Path(tempfile.mkdtemp(prefix="fw-view-mods-")).resolve()
        self.addCleanup(shutil.rmtree, mods, True)
        (mods / "torrent").mkdir()
        manifest = (Path(__file__).resolve().parents[1] / "magaza/torrent/paket.env").read_text()
        (mods / "torrent/paket.env").write_text(manifest.replace("__TORRENT_NETWORK__", "torrent"))
        (mods / "torrent/torrent.env").write_text("TORRENT_PEER_PORT=63851\n")
        with patch.object(self.p, "module_state", return_value="calisiyor"), \
                patch.dict(self.env, {"MODULES_DIR": str(mods)}):
            rows = self.p.settings_ports(self.env, [], [])
        peer = [r for r in rows if r["port"] == 63851]
        self.assertEqual(sorted((r["family"], r["proto"], r["scope"]) for r in peer), [(4, "tcp", "wan"), (4, "udp", "wan")])
        self.assertTrue(all(r.get("fixed") for r in peer))
        self.assertFalse(any(r.get("fixed") for r in rows if r["port"] != 63851))

    def test_known_service_names_are_retained_across_scopes(self):
        # DD-198: the Files backend's loopback row is declared by the built-in dosya manifest.
        import shutil
        import tempfile
        mods = Path(tempfile.mkdtemp(prefix="fw-view-mods-")).resolve()
        self.addCleanup(shutil.rmtree, mods, True)
        (mods / "dosya").mkdir()
        shutil.copy(Path(__file__).resolve().parents[1] / "magaza/dosya/paket.env", mods / "dosya/paket.env")
        with patch.object(self.p, "module_state", return_value="calisiyor"), \
                patch.dict(self.env, {"MODULES_DIR": str(mods)}):
            rows = self.p.settings_ports(self.env, [], [{"family": 4, "proto": "tcp", "port": 61009},
                                                       {"family": 4, "proto": "tcp", "port": 54321}])
        keys = [(r["family"], r["proto"], r["port"], r["scope"]) for r in rows]
        self.assertEqual(len(keys), len(set(keys)))
        by_scope = {r["scope"]: r for r in rows if r["port"] == 61009 and r["family"] == 4}
        self.assertNotIn("tail", by_scope)
        self.assertIn("Konsol", by_scope["lo"]["name"])
        self.assertNotIn("wan", by_scope)
        self.assertTrue(by_scope["lo"]["baseline"])
        self.assertEqual(next(r["name"] for r in rows if r["port"] == 54321), "Diğer dinleyici")

    def test_settings_network_metadata_is_public_only_and_includes_stopped_install(self):
        nets = [{**n, "private_key": "must-not-leak"} for n in self.nets]
        with patch.object(panel, "read_env", return_value=self.env), \
             patch.object(self.p, "package_networks", return_value=nets), \
             patch.object(self.p, "vpn_apps", return_value=["WireGuard"]), \
             patch.object(self.p, "firewall_view", return_value={}), \
             patch.object(self.p, "web_view", return_value={}), \
             patch.object(self.p, "dns_view", return_value={}):
            fw = self.p.settings(fresh=True)["firewall"]
        self.assertTrue(fw["vpn_installed"])
        self.assertEqual(fw["vpn_name"], "WireGuard")
        self.assertEqual(len(fw["networks"]), 2)
        self.assertEqual(set(fw["networks"][0]), {"app", "iface", "label", "active", "server4", "server6"})
        self.assertFalse(fw["networks"][1]["active"])

    def test_wireguard_endpoints_have_no_tunnel_host_service(self):
        with patch.object(self.p, "module_state", return_value="calisiyor"):
            rows = self.p.settings_ports(self.env, self.nets)
        endpoints = [r for r in rows if r["port"] in (51820, 51821)]
        self.assertTrue(endpoints)
        self.assertTrue(all(r["scope"] in ("wan", "tail") and r["proto"] == "udp" for r in endpoints))
        # Registered networks remain in the tailnet catalogue even with no sockets/peers.
        self.assertEqual({(r["family"], r["port"]) for r in endpoints if r["scope"] == "tail"},
                         {(f, p) for f in (4, 6) for p in (51820, 51821)})
        self.assertTrue(all(r["baseline"] for r in endpoints if r["scope"] == "tail"))
        self.assertFalse(any(r["scope"].startswith("wg") for r in rows))

    def test_tailnet_catalogue_excludes_unconfigured_listeners_in_both_families(self):
        self.tailnet.return_value = [dict(family=f, proto="tcp", port=80, name="Caddy") for f in (4, 6)]
        self.tailnet.return_value.append(dict(family=4, proto="tcp", port=54321, name="Tailscale PeerAPI"))
        sockets = [dict(family=f, proto=p, port=n) for f in (4, 6) for p in ("tcp", "udp")
                   for n in (20902, 61006, 61008, 61009, 2019, 54321, 49876)]
        with patch.object(self.p, "module_state", return_value="calisiyor"):
            rows = self.p.settings_ports(self.env, self.nets, sockets)
        tail = {(r["family"], r["proto"], r["port"]): r for r in rows if r["scope"] == "tail"}
        self.assertEqual(set(tail), {(4, "tcp", 80), (6, "tcp", 80), (4, "tcp", 54321)} |
                         {(f, "udp", p) for f in (4, 6) for p in (51820, 51821)})
        self.assertTrue(all(r["baseline"] for r in tail.values()))
        self.assertEqual(tail[(4, "tcp", 54321)]["name"], "Tailscale PeerAPI")
        for port in (20902, 61006, 61008, 61009, 2019, 49876):
            for family in (4, 6):
                self.assertFalse(any(r["scope"] == "wan" and r["family"] == family and r["port"] == port for r in rows))
                self.assertTrue(any(r["scope"] == "lo" and r["baseline"] and
                                    r["family"] == family and r["port"] == port for r in rows))
        self.assertEqual(len(rows), len({(r["family"], r["proto"], r["port"], r["scope"]) for r in rows}))
        # The endpoint permission is preserved on WAN regardless of peer count.
        self.assertTrue(next(r["baseline"] for r in rows if r["scope"] == "wan" and r["family"] == 4 and r["port"] == 51821))

    def test_tailnet_uses_configured_ports_and_families_without_socket_discovery(self):
        env = {**self.env, "CADDY_HTTP_PORT": "8081", "SHARE_PORT": "61011", "DNS_PORT": "5353"}
        self.tailnet.return_value = [dict(family=4, proto="tcp", port=p, name=n)
                                    for p, n in ((8081, "Caddy"), (61011, "Paylaşım WebDAV"))]
        self.tailnet.return_value += [dict(family=f, proto=p, port=5353, name="dnsmasq")
                                     for f in (4, 6) for p in ("tcp", "udp")]
        for sockets in (None, [], [dict(family=6, proto="tcp", port=8081)]):
            with self.subTest(sockets=sockets), patch.object(self.p, "module_state", return_value="calisiyor"):
                rows = self.p.settings_ports(env, [], sockets)
            tail = {(r["family"], r["proto"], r["port"]) for r in rows if r["scope"] == "tail"}
            self.assertEqual(tail, {(r["family"], r["proto"], r["port"]) for r in self.tailnet.return_value})

    def test_wan_catalogue_has_only_configured_per_family_ingress(self):
        env = {**self.env, "SSH_PUBLIC_PORT": "2222", "TAILSCALE_UDP_PORT": "41642"}
        sockets = [dict(family=f, proto=p, port=n) for f in (4, 6) for p in ("tcp", "udp")
                   for n in (53, 80, 61004, 61008, 61009, 61010, 2019, 20902, 55221)]
        self.tailnet.return_value = [dict(family=4, proto="tcp", port=55221, name="Tailscale PeerAPI")]
        for discovered in (None, [], sockets):
            with self.subTest(discovered=bool(discovered)), patch.object(self.p, "module_state", return_value="calisiyor"):
                rows = self.p.settings_ports(env, self.nets, discovered)
            wan = [r for r in rows if r["scope"] == "wan"]
            self.assertEqual({(r["family"], r["proto"], r["port"]) for r in wan},
                             {(f, p, n) for f in (4, 6) for p, n in (("tcp", 2222), ("udp", 41642))} |
                             {(4, "udp", 51820), (4, "udp", 51821)})
            self.assertTrue(all(r["baseline"] for r in wan))

    def test_tunnel_catalogue_has_no_host_services_even_with_legacy_scope(self):
        for active in (True, False):
            nets = [{**n, "active": active, "count": 0} for n in self.nets]
            with self.subTest(active=active), patch.object(self.p, "module_state", return_value="calisiyor"):
                rows = self.p.settings_ports(self.env, nets, [])
            tunnel = [r for r in rows if r["scope"].startswith("wg")]
            self.assertEqual(tunnel, [])
            self.assertTrue(any(r["scope"] == "wan" and r["port"] == 51821 for r in rows))
        with patch.object(self.p, "module_state", return_value="calisiyor"):
            rows = self.p.settings_ports(self.env, [{**n, "scope": "inet"} for n in self.nets])
        self.assertFalse(any(r["scope"].startswith("wg") for r in rows))

    def test_no_networks_means_no_wireguard_placeholder_ports(self):
        with patch.object(self.p, "module_state", return_value=""):
            rows = self.p.settings_ports(self.env, [])
        self.assertFalse(any(r["scope"].startswith("wg") or r["name"].startswith("WireGuard ") for r in rows))

    def test_a_wireguard_to_host_accept_is_shown_as_unknown(self):
        # DD-177: the firewall never emits these; one added by hand must stand out, not look known.
        for spec in ("-d 10.8.0.1/32 -i wg0 -p tcp -m tcp --dport 61004 -j ACCEPT",
                     "-d 10.8.0.1/32 -i wg0 -p icmp -m icmp --icmp-type 8 -j ACCEPT"):
            rows = panel.classify_rules("input", [{"spec": spec, "pkts": 3}], self.env, self.nets)
            self.assertEqual((rows[0]["group"], rows[0]["kind"]), ("other", "unknown"))

    def test_absent_wg_chains_are_expected_only_without_networks(self):
        env = {**self.env, "CHAIN_INPUT": "MASTER-INPUT", "CHAIN_FORWARD": "MASTER-FORWARD", "CHAIN_NAT": "MASTER-NAT"}
        def read(binary, chain, table):
            return ([], "-N MASTER-INPUT") if chain == "MASTER-INPUT" else (None, "")
        with patch.object(self.p, "iptables_chain", side_effect=read), \
             patch.object(panel.subprocess, "run", return_value=types.SimpleNamespace(returncode=0, stdout=b"ok", stderr=b"")):
            self.assertTrue(self.p.firewall_view(env, [])["v4"]["readable"])
            self.assertFalse(self.p.firewall_view(env, self.nets)["v4"]["readable"])
        # Missing INPUT or a failed --check must never appear as healthy.
        with patch.object(self.p, "iptables_chain", return_value=(None, "")), \
             patch.object(panel.subprocess, "run", return_value=types.SimpleNamespace(returncode=1, stdout=b"", stderr=b"failed")):
            view = self.p.firewall_view(env, [])
            self.assertFalse(view["v4"]["readable"])
            self.assertFalse(view["ok"])


if __name__ == "__main__":
    unittest.main()
