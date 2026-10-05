"""Stage 4 DNS family projections and controlled JSON failures at real HTTP/CLI boundaries."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import test_resources as resources
import test_settings as settings_tests

panel = resources.panel
settings = settings_tests.settings
DATA = Path(__file__).resolve().parents[1]
DEEP = '{"secret":' + '[' * 30000 + '"private-test-value"' + ']' * 30000 + '}'


class DnsTests(unittest.TestCase):
    def setUp(self):
        self.fixture = settings_tests.SettingsTests()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.m = self.fixture.m
        self.root = self.fixture.root
        self.env = {**self.fixture.env, "TAILSCALE_IPV6": "fd7a:115c:a1e0::2"}
        self.m.e.update(self.env)
        self.p = panel.Panel(types.SimpleNamespace())

    def test_published_templates_limit_answers_without_changing_dns_listeners(self):
        for relative, name in (("templates/dnsmasq.conf", "panel"), ("magaza/paylasim/dnsmasq.conf", "paylas"),
                               ("magaza/torrent/dnsmasq.conf", "torrent")):
            text = (DATA / relative).read_text().replace("__LOCAL_DOMAIN__", "ayc").replace("__TAILSCALE_IF__", "tailscale0")
            record = panel.parse_dnsmasq(text, "base")["names"]
            self.assertEqual(record, [dict(name=name + ".ayc", iface="tailscale0", family=4, source="base")])
            if name == "panel":
                parsed = panel.parse_dnsmasq(text, "base")
                self.assertEqual(parsed["listen"], ["lo", "tailscale0"])
                self.assertEqual(parsed["domains"], ["ayc"])
                self.assertFalse(parsed["dhcp"])
                self.assertIn("no-resolv\n", text)
                self.assertIn("bind-dynamic\n", text)

    def test_parser_and_view_separate_interface_from_family_and_keep_fixed_ipv6(self):
        base = Path(self.env["DNSMASQ_CONF_FILE"])
        base.write_text("interface-name=v4.ayc,tailscale0/4\n"
                        "interface-name=v6.ayc,tailscale0/6\n"
                        "interface-name=dual.ayc,tailscale0\n"
                        "interface-name=other.ayc,eth0/4\n"
                        "host-record=fixed.ayc,2001:db8::9\n"
                        "# konsol-off: interface-name=off.ayc,tailscale0/4\n")
        parsed = {n["name"]: n for n in self.p.dns_view(self.env)["names"]}
        for name, family, address in (("v4", 4, self.env["TAILSCALE_IPV4"]),
                                      ("v6", 6, self.env["TAILSCALE_IPV6"]),
                                      ("dual", None, self.env["TAILSCALE_IPV4"] + ", " + self.env["TAILSCALE_IPV6"]),
                                      ("other", 4, ""), ("fixed", 6, "2001:db8::9")):
            with self.subTest(name=name):
                row = parsed[name + ".ayc"]
                self.assertEqual((row["family"], row["address"]), (family, address))
                self.assertNotIn("/", row["iface"])
        self.assertNotIn("off.ayc", parsed)
        names = {n["name"]: n for n in self.m.dns_names()}
        self.assertEqual((names["v4.ayc"]["iface"], names["v4.ayc"]["target"]), ("tailscale0", "tailscale"))
        self.assertEqual(names["v6.ayc"]["target"], self.env["TAILSCALE_IPV6"])
        self.assertEqual(names["off.ayc"]["family"], 4)

    def test_explicit_ipv6_choices_survive_projection_and_disabled_names(self):
        base = Path(self.env["DNSMASQ_CONF_FILE"])
        base.write_text("interface=lo\ninterface=tailscale0\nlocal=/ayc/\nno-resolv\ninterface-name=panel.ayc,tailscale0/4\n")
        module = base.parent / "modul-torrent.conf"
        module.write_text("interface-name=torrent.ayc,tailscale0/4\n")
        records = [dict(name="auto.ayc", target="tailscale", enabled=True),
                   dict(name="v6.ayc", target="2001:db8::9", enabled=True),
                   dict(name="v4.ayc", target="192.0.2.9", enabled=True),
                   dict(name="off.ayc", target="tailscale", enabled=False)]
        dns = self.fixture.dns(records=records, disabled=["torrent.ayc"], forward=True, servers=["2606:4700:4700::1111"])
        result = self.m.apply(self.fixture.payload(dns=dns))
        self.assertTrue(result["committed"])
        expected = self.m.dns_file.read_text()
        for line in ("interface-name=auto.ayc,tailscale0/4", "host-record=v6.ayc,2001:db8::9",
                     "host-record=v4.ayc,192.0.2.9", "server=2606:4700:4700::1111"):
            self.assertIn(line + "\n", expected)
        self.assertNotIn("off.ayc", expected)
        self.assertEqual(module.read_text(), settings.OFF + "interface-name=torrent.ayc,tailscale0/4\n")
        self.m.project_dns()
        self.assertEqual(self.m.dns_file.read_text(), expected)
        self.assertEqual(self.m.filter_dns(module.read_text(), settings.DEFAULT), "interface-name=torrent.ayc,tailscale0/4\n")
        shown = {n["name"]: n for n in self.p.dns_view(self.env)["names"]}
        self.assertEqual(shown["auto.ayc"]["address"], self.env["TAILSCALE_IPV4"])
        self.assertEqual(shown["v6.ayc"]["address"], "2001:db8::9")
        self.assertNotIn("torrent.ayc", shown)
        self.assertEqual(self.m.current()["dns"]["records"], records)

    def test_domain_apply_and_rollback_keep_family_and_custom_ipv6(self):
        self.fixture.domain_fixture()
        base = Path(self.env["DNSMASQ_CONF_FILE"])
        base.write_text("interface-name=panel.ayc,tailscale0/4\nlocal=/ayc/\nno-resolv\n")
        stage = self.root / "templates/torrent/dnsmasq.conf"
        stage.write_text("interface-name=torrent.ayc,tailscale0/4\n")
        config = self.m.config()
        config["dns"]["records"] = [dict(name="ipv6.ayc", target="2001:db8::9", enabled=True)]
        settings.save_json(self.m.config_path, config)
        self.m.project_dns()
        before = {p: p.read_bytes() for p in (base, stage, self.m.dns_file)}
        self.m.apply(self.fixture.payload(domain="ev"))
        self.assertIn("interface-name=panel.ev,tailscale0/4", base.read_text())
        self.assertIn("interface-name=torrent.ev,tailscale0/4", stage.read_text())
        self.assertIn("host-record=ipv6.ev,2001:db8::9", self.m.dns_file.read_text())
        self.m.rollback()
        for path, content in before.items():
            self.assertEqual(path.read_bytes(), content)


class JsonTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="stage4-json-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        state = self.root / "state.env"
        state.write_text("LOCAL_DOMAIN=test\n")
        self.p = panel.Panel(types.SimpleNamespace(state=str(state), allow_host=[], state_env=False,
                                                  master_modul="/mock/master-modul"))

    def test_deep_http_json_returns_400_keeps_gates_and_does_not_run_worker(self):
        class Handler(panel.Handler):
            pass
        Handler.panel = self.p
        _server, sock = resources.start_unix(self, Handler)
        headers = {"X-Konsol": "1", "Content-Type": "application/json"}
        self.assertLess(len(DEEP), panel.MAX_BODY)
        with patch.object(self.p, "settings_run", side_effect=AssertionError("must not run")):
            for endpoint in ("/api/konsol/ayarlar/uygula", "/api/konsol/paylasim/kaydet", "/api/uygulama/wireguard/nets"):
                status, response_headers, body = resources.unix_get(sock, endpoint, headers, "POST", DEEP)
                self.assertEqual(status, 400)
                self.assertEqual(response_headers["Connection"], "close")
                self.assertEqual(response_headers["Cache-Control"], "no-store")
                self.assertIn("error", json.loads(body))
                self.assertNotIn("private-test-value", body.decode())
            # The gate rejects before consuming a body; a large send could race its close.
            status, _, _ = resources.unix_get(sock, endpoint, {**headers, "Host": "evil.test"}, "POST", "{}")
            self.assertEqual(status, 403)
            status, _, _ = resources.unix_get(sock, "/api/konsol/kaynaklar", {"X-Konsol": "1"})
            self.assertEqual(status, 200)

    def test_worker_response_json_is_controlled_without_echoing_output(self):
        for stdout in (DEEP, "[]", "null", '"private-test-value"', "not-json"):
            for shares in (False, True):
                with self.subTest(stdout=stdout[:20], shares=shares), \
                        patch.object(panel.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, stdout, "private-test-value")) as run:
                    status, data = self.p.settings_run("apply", {}, shares=shares)
                    self.assertEqual(status, 502)
                    self.assertNotIn("private-test-value", json.dumps(data))
                    self.assertEqual(run.call_args.kwargs["timeout"], 155)
        for returncode, expected in ((0, 200), (1, 400)):
            with patch.object(panel.subprocess, "run", return_value=subprocess.CompletedProcess([], returncode, '{"error":"test"}', "")):
                self.assertEqual(self.p.settings_run("apply", {})[0], expected)

    def test_settings_cli_deep_and_nonobject_input_returns_only_safe_json(self):
        env = {"SETTINGS_FILE": str(self.root / "settings.json"), "SETTINGS_PENDING_FILE": str(self.root / "pending.json"),
               "SETTINGS_DNS_FILE": str(self.root / "dns.conf"), "TORRENT_PROFILE_DIR": str(self.root / "profile"),
               "UNIT_DIR": str(self.root / "units"), "RUNTIME_DIR": str(self.root / "run")}
        state = self.root / "worker.env"
        state.write_text("".join(k + "=" + v + "\n" for k, v in env.items()))
        for action in ("apply", "confirm", "rollback", "discard"):
            for raw in (DEEP, "[]", "null", '"private-test-value"'):
                with self.subTest(action=action, raw=raw[:20]):
                    proc = subprocess.run([sys.executable, str(DATA / "panel/master_settings.py"), "--state", str(state), action],
                                          input=raw, capture_output=True, text=True, timeout=10,
                                          env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
                    self.assertEqual(proc.returncode, 1, proc.stderr)
                    self.assertEqual(set(json.loads(proc.stdout)), {"error"})
                    self.assertNotIn("private-test-value", proc.stdout + proc.stderr)
                    self.assertNotIn("Traceback", proc.stderr)
        self.assertFalse(Path(env["SETTINGS_FILE"]).exists())
        self.assertFalse(Path(env["SETTINGS_PENDING_FILE"]).exists())

    def test_deep_persisted_json_does_not_get_replaced(self):
        path = self.root / "settings.json"
        path.write_text(DEEP)
        with self.assertRaises(settings.SettingsError):
            settings.read_json(path, {})
        self.assertEqual(path.read_text(), DEEP)


class FirewallTests(unittest.TestCase):
    def test_only_unconditional_input_drop_is_classified_as_default(self):
        rules = [{"spec": "-i eth0 -j DROP", "pkts": 4}, {"spec": "-j DROP", "pkts": 9},
                 {"spec": "-s 192.0.2.0/24 -j DROP", "pkts": 2}]
        rows = panel.classify_rules("input", rules, {"WAN_INTERFACE": "eth0"}, [])
        self.assertEqual([(r["group"], r["kind"]) for r in rows],
                         [("wan", "drop"), ("self", "default-drop"), ("other", "unknown")])
        self.assertEqual(rows[1]["pkts"], 9)
        self.assertEqual(rows[1]["spec"], "-j DROP")


if __name__ == "__main__":
    unittest.main()
