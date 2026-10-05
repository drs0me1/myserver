"""Read-only HTTPS WAN presentation; no host services or external TLS probes."""
import contextlib
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

import test_resources as resources
import master_https

panel = resources.panel


class HttpsPanelTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="https-panel-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.modules = self.root / "caddy-modules"
        self.modules.mkdir()
        self.env = {"LOCAL_DOMAIN": "test", "TAILSCALE_IPV4": "100.64.0.2",
                    "WAN_IPV4": "192.0.2.1", "SHARE_PORT": "61010", "SHARE_HTTPS_PORT": "443",
                    "SHARE_WAN_BACKEND": "127.0.0.2",
                    "CADDYFILE": str(self.root / "Caddyfile"), "CADDY_MODULES_DIR": str(self.modules),
                    "SERVER_ROOT": str(self.root), "SETTINGS_FILE": str(self.root / "settings.json")}
        self.state = self.root / "state.env"
        self.state.write_text("".join(k + "=" + v + "\n" for k, v in self.env.items()))
        self.p = panel.Panel(types.SimpleNamespace(state=str(self.state), allow_host=[], state_env=False))
        self.now = 1800000000
        self.https = {"domain": "files.example.com", "mode": "https", "status": "ready",
                      "message": "Sertifika yerelde doğrulandı", "expires": self.now + 90 * 86400,
                      "port": 443, "wan_ip": self.env["WAN_IPV4"]}
        self.wan = {"available": True, "address": self.env["WAN_IPV4"], "reason": "",
                    "domain": self.https["domain"], "mode": "https", "scheme": "https", "port": 443}
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        self.manager = stack.enter_context(patch.object(panel.master_settings, "Manager")).return_value
        self.manager.status.return_value = {"pending": None, "https": self.https}
        self.shares = stack.enter_context(patch.object(panel.master_shares, "Manager")).return_value
        self.shares.wan_info.return_value = self.wan
        self.shares.wan_active.return_value = True
        self.shares.read.return_value = {"items": []}
        stack.enter_context(patch.object(panel.subprocess, "run", side_effect=AssertionError("unexpected host command")))
        stack.enter_context(patch.object(panel.socket, "create_connection", side_effect=AssertionError("unexpected network probe")))

    def health(self, firewall_ok=True):
        outputs = {"tailscale": (0, json.dumps({"BackendState": "Running", "Self": {"Online": True}})),
                   "master-firewall": (0 if firewall_ok else 1, ""), "timedatectl": (0, "yes")}
        disk = types.SimpleNamespace(f_blocks=100000, f_frsize=4096, f_bavail=50000,
                                     f_files=10000, f_favail=9000)
        with patch.object(self.p, "health_units", return_value=("ok", "Services ready")), \
                patch.object(self.p, "health_reboot", return_value=("ok", "Same kernel")), \
                patch.object(self.p, "health_cmd", side_effect=lambda argv, **kw: outputs[argv[0]]), \
                patch.object(panel.os, "statvfs", return_value=disk), \
                patch.object(panel.time, "time", return_value=self.now):
            result = self.p.health_compute()
        return result, {c["id"]: c for c in result["checks"]}

    def test_ready_is_local_certificate_evidence_without_active_shares(self):
        result, checks = self.health()
        self.assertEqual((result["status"], checks["https"]["status"]), ("ok", "ok"))
        self.assertIn(self.https["domain"], checks["https"]["detail"])
        self.assertIn("90 gün", checks["https"]["detail"])
        self.assertIn("internetten erişim sınanmadı", checks["https"]["detail"])
        self.manager.status.assert_called_once_with()
        self.shares.read.assert_called_once_with()
        self.shares.wan_active.assert_not_called()

    def test_pending_error_and_unknown_status_warn_even_without_active_shares(self):
        for status in ("pending", "error", "unknown", None):
            with self.subTest(status=status):
                self.https.update(status=status, expires=None, message="Sertifika henüz doğrulanamadı")
                result, checks = self.health()
                self.assertEqual((result["status"], checks["https"]["status"]), ("warn", "warn"))
                self.assertIn(self.https["message"], checks["https"]["detail"])

    def test_expiry_boundary_includes_exactly_fourteen_days(self):
        for remaining, expected in ((90 * 86400, "ok"), (14 * 86400 + 1, "ok"),
                                    (14 * 86400, "warn"), (86400, "warn"), (0, "warn"), (-86400, "warn")):
            with self.subTest(remaining=remaining):
                self.https["expires"] = self.now + remaining
                result, checks = self.health()
                self.assertEqual((result["status"], checks["https"]["status"]), (expected, expected))
                if remaining <= 0:
                    self.assertIn("süresi dolmuş", checks["https"]["detail"])

    def test_invalid_or_missing_expiry_is_unknown_never_green(self):
        for expiry in (None, "bad", str(self.now), True, [], {}, float("nan"), float("inf"), 10 ** 100):
            with self.subTest(expiry=expiry):
                self.https["expires"] = expiry
                result, checks = self.health()
                self.assertEqual((result["status"], checks["https"]["status"]), ("warn", "warn"))
                self.assertIn("okunamadı", checks["https"]["detail"])
        self.https.pop("expires")
        self.assertEqual(self.health()[1]["https"]["status"], "warn")

    def test_http_and_disabled_modes_do_not_require_certificates(self):
        for mode, status in (("http", "http"), ("off", "disabled")):
            with self.subTest(mode=mode):
                self.https.update(mode=mode, status=status, domain="", expires=None)
                self.wan["mode"] = mode
                result, checks = self.health()
                self.assertEqual(result["status"], "ok")
                self.assertNotIn("https", checks)

    def test_missing_or_malformed_https_status_warns_when_configured(self):
        for info in (None, {}, [], "bad", {"mode": "unknown"}, {**self.https, "domain": ""}):
            with self.subTest(info=info):
                self.manager.status.return_value = {"pending": None, "https": info}
                result, checks = self.health()
                self.assertEqual((result["status"], checks["https"]["status"]), ("warn", "warn"))
        self.manager.status.return_value = {"pending": None}
        self.assertEqual(self.health()[1]["https"]["status"], "warn")

    def test_settings_failure_and_stuck_rollback_keep_existing_health_severity(self):
        self.manager.status.side_effect = panel.master_settings.SettingsError("bad registry")
        result, checks = self.health()
        self.assertEqual((result["status"], checks["settings"]["status"], checks["https"]["status"]),
                         ("warn", "warn", "warn"))
        self.manager.status.side_effect = None
        self.manager.status.return_value["pending"] = {"phase": "stuck"}
        result, checks = self.health()
        self.assertEqual((result["status"], checks["settings"]["status"], checks["https"]["status"]),
                         ("bad", "bad", "ok"))

    def test_configured_https_still_reports_damaged_share_registry_and_failed_firewall(self):
        self.shares.read.side_effect = panel.master_shares.ShareError("bad registry")
        result, checks = self.health(firewall_ok=False)
        self.assertEqual((result["status"], checks["firewall"]["status"], checks["wan"]["status"]),
                         ("bad", "bad", "warn"))

    def test_missing_wan_address_warns_even_with_ready_cert_and_no_active_share(self):
        self.wan.update(available=False, reason="WAN IPv4 artık bu sunucuda değil")
        result, checks = self.health()
        self.assertEqual((result["status"], checks["wan"]["status"]), ("warn", "warn"))
        self.assertEqual(checks["wan"]["detail"], self.wan["reason"])

    def test_firewall_row_uses_effective_public_port_and_scheme(self):
        tailnet = [dict(family=4, proto="tcp", port=61010, name="Paylaşım WebDAV")]
        for scheme, port in (("https", 443), ("http", 61010), ("http", 62010)):
            with self.subTest(scheme=scheme, port=port):
                self.wan.update(mode=scheme, scheme=scheme, port=port)
                with patch.object(panel.master_settings, "tailnet_ports", return_value=tailnet), \
                        patch.object(self.p, "module_state", return_value="calisiyor"):
                    rows = self.p.settings_ports(self.env, [], listeners=[])
                wan_rows = [r for r in rows if r["scope"] == "wan"]
                self.assertEqual(wan_rows, [{"name": "Paylaşım WebDAV %s · WAN" % scheme.upper(),
                                            "family": 4, "proto": "tcp", "port": port,
                                            "scope": "wan", "baseline": True}])
                self.assertEqual([r["port"] for r in rows if r["scope"] == "tail"], [61010])
        self.shares.read.assert_not_called()  # wan_active owns renewal/admission policy.

    def test_disabled_listener_has_no_wan_permission_even_if_socket_exists(self):
        self.shares.wan_active.return_value = False
        self.wan.update(mode="off", scheme="", port=0)
        with patch.object(panel.master_settings, "tailnet_ports", return_value=[]), \
                patch.object(self.p, "module_state", return_value=""):
            rows = self.p.settings_ports(self.env, [], listeners=[dict(family=4, proto="tcp", port=443)])
        self.assertFalse(any(r["scope"] == "wan" for r in rows))
        self.assertTrue(any(r["scope"] == "lo" and r["port"] == 443 for r in rows))
        self.shares.wan_info.assert_not_called()

    def test_caddy_https_keeps_scheme_wan_source_and_routes(self):
        Path(self.env["CADDYFILE"]).write_text("{\n servers {\n protocols h1 h2\n }\n}\n"
                                               "http://panel.test {\n file_server\n}\n")
        (self.modules / "paylasim.caddy").write_text("http://paylas.test, http://{$TAILSCALE_IPV4}:61010 {\n"
                                                     " reverse_proxy 127.0.0.1:61010\n}\n")
        (self.modules / "paylasim-wan.caddy").write_text(master_https.site(self.env, self.wan))
        rows = {r["address"]: r for r in self.p.web_view(self.env, [])["entries"]}
        wan = rows["files.example.com:443"]
        self.assertEqual((wan["source"], wan["access"], wan["scheme"]), ("paylasim-wan", "wan", "https"))
        self.assertIn(dict(path="/s/*", kind="proxy", to="127.0.0.2:61010"), wan["routes"])
        self.assertIn(dict(path="", kind="respond", to=""), wan["routes"])
        for address in ("panel.test", "paylas.test", "100.64.0.2:61010"):
            self.assertEqual((rows[address]["access"], rows[address]["scheme"]), ("tailscale", "http"))

    def test_caddy_legacy_http_and_https_source_do_not_imply_public_access(self):
        (self.modules / "paylasim-wan.caddy").write_text("http://:61010 {\n reverse_proxy 127.0.0.2:61010\n}\n")
        (self.modules / "other.caddy").write_text("https://private.example.com {\n respond 404\n}\n")
        rows = {r["source"]: r for r in self.p.web_view(self.env, [])["entries"]}
        self.assertEqual((rows["paylasim-wan"]["address"], rows["paylasim-wan"]["scheme"], rows["paylasim-wan"]["access"]),
                         ("192.0.2.1:61010", "http", "wan"))
        self.assertEqual((rows["other"]["scheme"], rows["other"]["access"]), ("https", "tailscale"))

    def test_settings_returns_manager_https_metadata_unchanged(self):
        with patch.object(self.p, "package_networks", return_value=[]), \
                patch.object(self.p, "module_state", return_value=""), \
                patch.object(self.p, "firewall_view", return_value={}), \
                patch.object(self.p, "web_view", return_value={}), \
                patch.object(self.p, "dns_view", return_value={}), \
                patch.object(self.p, "all_firewall_rules", return_value={}), \
                patch.object(self.p, "listeners", return_value=[]), \
                patch.object(panel.master_settings, "tailnet_ports", return_value=[]):
            data = self.p.settings(fresh=True)
        self.assertEqual(data["manage"]["https"], self.https)
        self.assertEqual(data["firewall"]["ports"][0]["port"], 443)

    def test_https_uses_existing_gated_settings_routes_only(self):
        class Handler(panel.Handler):
            pass
        Handler.panel = self.p
        _server, sock = resources.start_unix(self, Handler)
        headers = {"X-Konsol": "1", "Content-Type": "application/json"}
        payload = {"revision": "test-revision", "https": {"domain": self.https["domain"]}}
        with patch.object(self.p, "settings_run", return_value=(200, {"committed": True})) as worker:
            for extra in ({"X-Konsol": ""}, {"Host": "evil.test"}, {"Sec-Fetch-Site": "cross-site"},
                          {"X-Forwarded-For": "192.0.2.50"}):
                with self.subTest(extra=extra):
                    code, _, _ = resources.unix_get(sock, "/api/konsol/ayarlar/uygula", {**headers, **extra}, "POST", "{}")
                    self.assertEqual(code, 403)
            worker.assert_not_called()
            for path in ("/api/konsol/https", "/api/konsol/https/uygula", "/api/konsol/ayarlar/https"):
                code, _, _ = resources.unix_get(sock, path, headers, "POST", "{}")
                self.assertEqual(code, 404)
            worker.assert_not_called()
            code, _, _ = resources.unix_get(sock, "/api/konsol/ayarlar/uygula", headers, "POST", json.dumps(payload))
            self.assertEqual(code, 200)
            worker.assert_called_once_with("apply", payload)
        code, response_headers, body = resources.unix_get(sock, "/api/konsol/ayarlar/durum", headers)
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)["https"], self.https)
        self.assertEqual(response_headers["Cache-Control"], "no-store")
        code, _, _ = resources.unix_get(sock, "/api/konsol/ayarlar/durum", {})
        self.assertEqual(code, 403)


if __name__ == "__main__":
    unittest.main()
