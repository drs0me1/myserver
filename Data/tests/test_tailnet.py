"""DD-172: deterministic host allowlist and bounded Self-only PeerAPI discovery."""
import importlib.util
import json
from pathlib import Path
import types
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("tailnet_settings", Path(__file__).resolve().parents[1] / "panel/master_settings.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class TailnetTests(unittest.TestCase):
    env = {"SSH_PUBLIC_PORT": "2222", "CADDY_HTTP_PORT": "8080", "DNS_PORT": "5353", "SHARE_PORT": "18080"}

    def rows(self, status):
        with patch.object(m, "run", return_value=types.SimpleNamespace(stdout=json.dumps(status))) as run:
            result = m.tailnet_ports(self.env)
        run.assert_called_once_with(["tailscale", "status", "--json", "--peers=false"], timeout=3)
        return result

    def test_fixed_ports_come_from_environment_with_explicit_families_and_protocols(self):
        rows = self.rows({})
        self.assertEqual({(r["family"], r["proto"], r["port"]) for r in rows},
                         {(f, p, n) for f in (4, 6) for p, n in
                          (("tcp", 2222), ("tcp", 5353), ("udp", 5353))}
                         | {(4, "tcp", 8080), (4, "tcp", 18080)})

    def test_only_self_peerapi_and_correct_address_family_not_peers_or_ranges(self):
        rows = self.rows({"Self": {"TailscaleIPs": ["100.64.0.2", "fd7a:115c:a1e0::2"],
                                  "PeerAPIURL": ["http://100.64.0.2:50001", "http://[fd7a:115c:a1e0::2]:50002/",
                                                 "http://100.64.0.2:50001", "http://100.64.0.9:50003"]},
                          "Peer": {"other": {"PeerAPIURL": ["http://100.64.0.9:50004"]}}})
        self.assertEqual([(r["family"], r["port"]) for r in rows if r["name"] == "Tailscale PeerAPI"], [(4, 50001), (6, 50002)])

    def test_malformed_and_nonself_urls_never_open_arbitrary_ports(self):
        for url in ("http://example.com:50001", "https://100.64.0.2:50001", "http://u:p@100.64.0.2:50001",
                    "http://100.64.0.2:50001/evil", "http://100.64.0.2:50001?q=x", "http://100.64.0.2:50001#x",
                    "http://127.0.0.1:50001", "http://100.64.0.2:0", "http://100.64.0.2:999999"):
            with self.subTest(url=url):
                self.assertEqual(len(self.rows({"Self": {"TailscaleIPs": ["100.64.0.2"], "PeerAPIURL": [url]}})), 8)

    def test_daemon_startup_and_failed_reads_do_not_remove_base_protection(self):
        for error in (m.SettingsError("not ready"), ValueError("broken json")):
            with patch.object(m, "run", side_effect=error):
                self.assertEqual(len(m.tailnet_ports(self.env)), 8)
        for status in ({"Self": None}, {"Self": {}}, {"Self": {"PeerAPIURL": None}}):
            self.assertEqual(len(self.rows(status)), 8)


if __name__ == "__main__":
    unittest.main()
