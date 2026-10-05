"""HTTPS changes are atomic settings transactions, never plaintext fallbacks."""
import copy
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "panel"))
import master_https as tls
import master_settings as settings
import master_shares as shares


class HttpsSettingsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="https-settings-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        for name in ("run", "dns", "sites", "templates", "profile", "units", "srv/downloads", "srv/media/alpha"):
            (self.root / name).mkdir(parents=True)
        self.env = {"SETTINGS_FILE": "settings.json", "SETTINGS_PENDING_FILE": "pending.json",
                    "SETTINGS_DNS_FILE": "dns/settings.conf", "DNSMASQ_CONF_FILE": "dns/base.conf",
                    "DNSMASQ_CONF_DIR": "dns", "TORRENT_PROFILE_DIR": "profile", "UNIT_DIR": "units",
                    "MODULES_DIR": "templates", "MODULES_FILE": "modules", "RUNTIME_DIR": "run",
                    "SERVER_ROOT": "srv", "DOWNLOADS_PATH": "srv/downloads", "CADDYFILE": "Caddyfile",
                    "CADDY_MODULES_DIR": "sites", "SBIN_DIR": "bin",
                    "SHARE_STATE_FILE": "shares.json"}
        self.env = {key: str(self.root / value) for key, value in self.env.items()}
        self.env.update(LOCAL_DOMAIN="ayc", TAILSCALE_IF="tailscale0", WAN_INTERFACE="eth0", WAN_IPV4="8.8.8.8",
                        TAILSCALE_IPV4="100.64.0.2", DOWNLOADS_UID=str(os.getuid()), DOWNLOADS_GID=str(os.getgid()),
                        MEDIA_SUBDIR="media", SHARE_PORT="61010", SHARE_HTTPS_PORT="443", SHARE_WAN_BACKEND="127.0.0.2",
                        TORRENT_TEMP_DIR="incomplete", FILES_PANEL_TRASH=".cop", SHARE_DIR=".pay", DNS_PORT="53", CADDY_HTTP_PORT="80")
        (self.root / "modules").write_text("paylasim\tcalisiyor\n")
        (self.root / "Caddyfile").write_text("{\n auto_https disable_redirects\n}\n")
        self.state = self.root / "state.env"
        self.state.write_text("".join(k + "=" + v + "\n" for k, v in self.env.items()))
        self.m = settings.Manager(self.state)
        self.s = shares.Manager(self.state)
        self.calls = []
        self.fail_once = None
        self.mocks = []
        for owner, key, kwargs in (
            (settings, "run", {"side_effect": self.command}),
            (shares.subprocess, "run", {"side_effect": self.command}),
            (shares, "assigned", {"return_value": True}),
            (settings, "boot_id", {"return_value": "boot-test"}),
            (tls, "boot_id", {"return_value": "boot-test"}),
            (tls, "check_dns", {"return_value": None}),
            (tls, "wait_certificate", {"return_value": int(time.time()) + 86400}),
            (shares.Manager, "restart", {"return_value": None}),
        ):
            ctx = patch.object(owner, key, **kwargs)
            self.mocks.append(ctx.start())
            self.addCleanup(ctx.stop)
        self.s.prepare()
        self.s.change("save", {"path": "media/alpha", "username": "fixture", "password": "fixture-password",
                               "connections": {"wan": {"enabled": True}}, "ack_wan_http": True})

    def command(self, argv, **kwargs):
        self.calls.append(argv)
        if self.fail_once and self.fail_once in " ".join(argv):
            self.fail_once = None
            raise subprocess.CalledProcessError(1, argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    def payload(self, name="dav.example.net"):
        return {"revision": self.m.revision(), "https": {"domain": name}}

    def test_save_commits_verified_https_and_preserves_accounts_local_domain(self):
        original = Path(self.env["SHARE_STATE_FILE"]).read_bytes()
        result = self.m.apply(self.payload())
        self.assertEqual(result, {"pending": None, "committed": True})
        self.assertFalse(self.m.pending_path.exists())
        self.assertEqual(self.m.config()["https"], {"domain": "dav.example.net"})
        site = (self.root / "sites/paylasim-wan.caddy").read_text()
        self.assertIn("https://dav.example.net:443", site)
        self.assertIn("reverse_proxy 127.0.0.2:61010", site)
        self.assertIn("disable_http_challenge", site)
        self.assertNotIn("http://:61010", site)
        self.assertEqual(Path(self.env["SHARE_STATE_FILE"]).read_bytes(), original)
        self.assertEqual(settings.env_read(self.state)["LOCAL_DOMAIN"], "ayc")
        public = self.s.public()
        self.assertEqual(public["wan"]["port"], 443)
        self.assertTrue(public["items"][0]["urls"]["wan"].startswith("https://dav.example.net/s/"))
        self.assertTrue(public["items"][0]["urls"]["tailscale"].startswith("http://100.64.0.2:61010/"))

    def test_certificate_failure_restores_previous_https_domain(self):
        self.m.apply(self.payload())
        old = (self.root / "sites/paylasim-wan.caddy").read_bytes()
        with patch.object(tls, "wait_certificate", side_effect=settings.SettingsError("certificate failure")):
            with self.assertRaises(settings.SettingsError):
                self.m.apply(self.payload("new.example.net"))
        self.assertEqual(self.m.config()["https"]["domain"], "dav.example.net")
        self.assertEqual((self.root / "sites/paylasim-wan.caddy").read_bytes(), old)
        self.assertFalse(self.m.pending_path.exists())

    def test_dns_rejection_does_not_write_or_start_timer(self):
        before = len(self.calls)
        with patch.object(tls, "check_dns", side_effect=settings.SettingsError("DNS mismatch")):
            with self.assertRaises(settings.SettingsError):
                self.m.apply(self.payload())
        self.assertEqual(len(self.calls), before)
        self.assertFalse(self.m.pending_path.exists())
        self.assertNotIn("https", self.m.config())

    def test_publication_failure_rolls_back_and_can_retry(self):
        self.fail_once = "caddy validate"
        with self.assertRaises(settings.SettingsError):
            self.m.apply(self.payload())
        self.assertNotIn("https", self.m.config())
        self.assertFalse(self.m.pending_path.exists())
        self.assertTrue(self.m.apply(self.payload())["committed"])

    def test_remove_closes_wan_without_http_fallback_or_deleting_accounts(self):
        self.m.apply(self.payload())
        self.m.apply(self.payload(""))
        self.assertFalse((self.root / "sites/paylasim-wan.caddy").exists())
        self.assertFalse(self.s.wan_active())
        public = self.s.public()
        self.assertEqual(public["wan"]["mode"], "off")
        self.assertNotIn("wan", public["items"][0]["urls"])
        self.assertIn("tailscale", public["items"][0]["urls"])
        self.s.publish()
        self.assertFalse((self.root / "sites/paylasim-wan.caddy").exists())

    def test_certificate_renewal_listener_survives_last_share_pause(self):
        self.m.apply(self.payload())
        item = self.s.read()["items"][0]
        public = self.s.change("save", {"id": item["id"], "connections": {
            "tailscale": {"enabled": False}, "wan": {"enabled": False}}})
        self.assertEqual(public["items"][0]["urls"], {})
        self.assertTrue(self.s.wan_active())
        self.assertIn("https://dav.example.net", (self.root / "sites/paylasim-wan.caddy").read_text())

    def test_https_share_does_not_need_plaintext_consent(self):
        self.m.apply(self.payload())
        (self.root / "srv/media/beta").mkdir()
        public = self.s.change("save", {"path": "media/beta", "username": "second", "password": "fixture-password",
                                        "connections": {"tailscale": {"enabled": False}, "wan": {"enabled": True}}})
        self.assertEqual(len(public["items"]), 2)

    def test_corrupt_pending_is_controlled_and_never_http_fallback(self):
        self.m.apply(self.payload())
        for change in ({"changes": []}, {"until": "bad"}, {"candidate": []}):
            pending = dict(changes={"https": True}, phase="applying", until=time.monotonic()+60,
                           candidate=self.m.config(), boot="boot-test")
            pending.update(change)
            settings.save_json(self.m.pending_path, pending)
            with self.assertRaises(shares.ShareError):
                self.s.wan_info()

    def test_https_address_preserves_nondefault_port(self):
        self.m.apply(self.payload())
        self.s.env["SHARE_HTTPS_PORT"] = "8443"
        self.assertIn(":8443/s/", self.s.public()["items"][0]["urls"]["wan"])

    def test_status_names_the_https_port_even_in_legacy_http_mode(self):
        # DD-193: legacy HTTP reports SHARE_PORT as "port"; the table needs the HTTPS port.
        env = dict(self.env, SHARE_HTTPS_PORT="8443")
        self.assertEqual((tls.status(env)["port"], tls.status(env)["https_port"]), (61010, 8443))
        self.m.apply(self.payload())
        with patch.object(tls, "certificate", return_value=1900000000):
            self.assertEqual((tls.status(env)["port"], tls.status(env)["https_port"]), (8443, 8443))

    def test_crash_recovery_restores_only_uncommitted_https(self):
        def crash(*_):
            raise KeyboardInterrupt()
        with patch.object(tls, "wait_certificate", side_effect=crash):
            with self.assertRaises(KeyboardInterrupt):
                self.m.apply(self.payload())
        self.assertTrue(self.m.pending_path.exists())
        with patch.object(settings, "boot_id", return_value="new-boot"), patch.object(tls, "boot_id", return_value="new-boot"):
            self.m.guard()
        self.assertFalse(self.m.pending_path.exists())
        self.assertNotIn("https", self.m.config())
        self.assertIn("http://:61010", (self.root / "sites/paylasim-wan.caddy").read_text())

    def test_read_status_never_claims_success_without_verified_certificate(self):
        self.m.apply(self.payload())
        with patch.object(tls, "certificate", side_effect=ssl.SSLError("bad certificate")):
            self.assertEqual(self.m.status()["https"]["status"], "error")
        with patch.object(tls, "certificate", return_value=1900000000):
            self.assertEqual(self.m.status()["https"]["expires"], 1900000000)

    def test_mixed_stale_and_shared_pending_changes_are_rejected(self):
        for change in ({"domain": "ev"}, {"firewall": []}, {"revision": "stale"}, {"https": {"domain": "dav.example.net", "extra": True}}):
            with self.subTest(change=change), self.assertRaises(settings.SettingsError):
                self.m.validate(dict(self.payload(), **change))
        Path(self.env["SHARE_STATE_FILE"] + ".pending").write_text("{}")
        with self.assertRaises(settings.SettingsError):
            self.m.validate(self.payload())


class HttpsValidationTests(unittest.TestCase):
    def test_public_listener_requires_matching_tls_name_without_quic_or_redirects(self):
        template = (Path(__file__).resolve().parents[1] / "templates/Caddyfile").read_text()
        listener = template.split("servers __WAN_IPV4__:__SHARE_HTTPS_PORT__ {", 1)[1].split("\n\t}", 1)[0]
        self.assertIn("protocols h1 h2\n", listener)
        self.assertIn("strict_sni_host on", listener)
        self.assertIn("auto_https disable_redirects", template)

    def test_domain_canonicalization_and_injection_rejection(self):
        self.assertEqual(tls.domain(" DAV.Example.NET. "), "dav.example.net")
        for value in (None, [], 123, "https://dav.example.net", "dav.example.net:443", "dav.example.net/s/x", "*.example.net", "127.0.0.1", "localhost", "x.local", "x.invalid", "x;id.net", "x\n.net", "-x.example.net", "x..net"):
            with self.subTest(value=value), self.assertRaises(settings.SettingsError):
                tls.domain(value)

    def test_dns_rejects_proxy_ipv6_multiple_addresses_and_timeout(self):
        env = {"WAN_IPV4": "8.8.8.8"}
        with patch.object(tls, "run", return_value=subprocess.CompletedProcess([], 0, '["8.8.8.8"]')) as run:
            tls.check_dns(env, "dav.example.net")
            self.assertEqual(run.call_args.kwargs["timeout"], 8)
        for addresses in ([], ["1.1.1.1"], ["8.8.8.8", "1.1.1.1"], ["8.8.8.8", "2606:4700::1111"]):
            with patch.object(tls, "run", return_value=subprocess.CompletedProcess([], 0, json.dumps(addresses))):
                with self.assertRaises(settings.SettingsError):
                    tls.check_dns(env, "dav.example.net")
        with patch.object(tls, "run", side_effect=settings.SettingsError("timeout")):
            with self.assertRaises(settings.SettingsError):
                tls.check_dns(env, "dav.example.net")

    def test_certificate_probe_pins_wan_ip_and_verifies_hostname(self):
        context = MagicMock()
        context.wrap_socket.return_value.__enter__.return_value.getpeercert.return_value = {"notAfter": "Oct 20 12:00:00 2027 GMT"}
        with patch.object(shares, "assigned", return_value=True), patch.object(ssl, "create_default_context", return_value=context), patch.object(socket, "create_connection") as connect:
            tls.certificate({"WAN_IPV4": "8.8.8.8", "SHARE_HTTPS_PORT": "443"}, "dav.example.net")
            self.assertEqual(connect.call_args.args[0], ("8.8.8.8", 443))
            self.assertEqual(context.wrap_socket.call_args.kwargs["server_hostname"], "dav.example.net")


if __name__ == "__main__":
    unittest.main()
