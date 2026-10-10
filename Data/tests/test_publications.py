"""Publication transactions, rollback and private/public isolation (DD-191)."""
from pathlib import Path
import json
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_https_settings as fixtures
import master_https as tls
import master_settings as settings
import master_publications as pubs
REAL_RUN = subprocess.run


class PublicationTests(unittest.TestCase):
    command = fixtures.HttpsSettingsTests.command

    def setUp(self):
        fixtures.HttpsSettingsTests.setUp(self)
        self.env["TORRENT_UI_PORT"] = "61006"
        self.env["FILES_PANEL_PORT"] = "61009"
        self.env["KONSOL_AUTH_DIR"] = str(self.root / "konsol")
        (self.root / "konsol").mkdir(mode=0o700)
        self.state.write_text("".join(k + "=" + v + "\n" for k, v in self.env.items()))
        self.m = settings.Manager(self.state)
        self.s.env.update(self.env)
        (self.root / "modules").write_text("paylasim\tcalisiyor\ntorrent\tcalisiyor\n")
        for service, addresses in (("paylasim", "http://paylas.ayc, http://{$TAILSCALE_IPV4}:61010"),
                                   ("torrent", "http://torrent.ayc")):
            directory = self.root / "templates" / service
            directory.mkdir()
            source = "# fixture\n%s {\n\trespond 401\n}\n" % addresses
            (directory / (service + ".caddy")).write_text(source)
            (self.root / "sites" / (service + ".caddy")).write_text(source)
        # DD-199: the qBittorrent row comes from the package's rendered manifest and check module.
        repo = Path(__file__).resolve().parents[1] / "magaza/torrent"
        (self.root / "templates/torrent/paket.env").write_text(
            (repo / "paket.env").read_text().replace("__TORRENT_UI_PORT__", self.env["TORRENT_UI_PORT"]))
        (self.root / "templates/torrent/yayin.py").write_bytes((repo / "yayin.py").read_bytes())
        # DD-203: the check module reads the interface port and profile from the package's own env file.
        (self.root / "templates/torrent/torrent.env").write_text(
            "TORRENT_UI_PORT=%s\nTORRENT_PROFILE_DIR=%s\n" % (self.env["TORRENT_UI_PORT"], self.root / "profile"))
        self.qconf = self.root / "profile/qBittorrent/qBittorrent.conf"
        self.qconf.parent.mkdir()
        self.qconf.write_text("[Preferences]\nWebUI\\Password_PBKDF2=@ByteArray(fixture)\nWebUI\\LocalHostAuth=true\n")
        self.m.apply({"revision": self.m.revision(), "https": {"domain": "dav.example.net"}})

    def payload(self, service="paylasim", tail=True, enabled=True, domain="dav.example.net", **extra):
        return {"revision": self.m.revision(), "web": dict(service=service, tail=tail, enabled=enabled, domain=domain, **extra)}

    def panel(self, **changes):
        # Enabling the console publicly also carries the typed word (DD-195).
        item = dict(enabled=True, domain="konsol.example.net", confirm="onayla")
        item.update(changes)
        return self.payload(service="panel", **item)

    def test_unknown_upstreams_rejected(self):
        for service in ("wireguard", "localhost:2019", "dosya", [], None):
            with self.subTest(service=service), self.assertRaises(settings.SettingsError):
                self.m.validate(self.payload(service=service))
        payload = self.payload(); payload["web"]["upstream"] = "localhost:2019"
        with self.assertRaises(settings.SettingsError):
            self.m.validate(payload)

    def test_real_worker_reports_imported_validation_errors_as_json(self):
        for payload in (self.payload(service="wireguard"), self.payload(domain="https://bad.example.net")):
            p = REAL_RUN([sys.executable, settings.__file__, "--state", str(self.state), "apply"],
                         input=json.dumps(payload), text=True, capture_output=True, timeout=10)
            self.assertEqual(p.returncode, 1)
            self.assertIn("error", json.loads(p.stdout))
            self.assertEqual(p.stderr, "")

    def test_shared_https_port_is_reported_once_and_without_dav(self):
        import test_resources
        panel = test_resources.panel
        import types
        instance = panel.Panel(types.SimpleNamespace(state=str(self.state), allow_host=[], state_env=False))
        with patch.object(pubs, "https_apps_active", return_value=["qBittorrent"]), \
                patch.object(panel.master_settings, "tailnet_ports", return_value=[]), \
                patch.object(instance, "ports", return_value=[]):
            rows = instance.settings_ports(self.env, [])
            self.assertEqual(len(rows), 1)
            self.assertIn("qBittorrent + WebDAV", rows[0]["name"])
            self.assertEqual(rows[0]["port"], 443)
            with patch.object(panel.master_shares.Manager, "wan_active", return_value=False):
                rows = instance.settings_ports(self.env, [])
            self.assertEqual(len(rows), 1)
            self.assertIn("qBittorrent", rows[0]["name"])
            self.assertNotIn("WebDAV", rows[0]["name"])
        # DD-195/199: Konsol joins the same single row; the names come from the package manifests.
        with patch.object(pubs, "https_apps_active", return_value=["qBittorrent", "Konsol"]), \
                patch.object(panel.master_settings, "tailnet_ports", return_value=[]), \
                patch.object(instance, "ports", return_value=[]):
            rows = instance.settings_ports(self.env, [])
        self.assertEqual([r["name"] for r in rows], ["Caddy HTTPS · qBittorrent + Konsol + WebDAV · WAN"])
        self.assertEqual(pubs.https_apps_active(self.env), [])
        with patch.object(pubs, "package_active", return_value=True), patch.object(pubs, "panel_active", return_value=True):
            self.assertEqual(pubs.https_apps_active(self.env), ["qBittorrent", "Konsol"])

    def make_account(self):
        import master_auth
        store = master_auth.Store(self.env["KONSOL_AUTH_DIR"])
        store.create("yonetici", "fixture-password-10")  # DD-205: no code; the tailnet device is the credential
        return store

    def wan_firewall(self):
        import contextlib
        import io
        out = io.StringIO()
        with patch.object(sys, "argv", ["master_shares.py", "--state", str(self.state), "wan-firewall"]), \
                contextlib.redirect_stdout(out):
            fixtures.shares.main()
        return out.getvalue().split()

    def test_panel_publication_needs_an_account_and_keeps_its_tailnet_address(self):
        # DD-195: the tailnet address is the management path that always remains.
        with self.assertRaises(settings.SettingsError) as err:
            self.m.validate(self.payload(service="panel", tail=False, enabled=False, domain=""))
        self.assertIn("Tailscale", str(err.exception))
        with self.assertRaises(settings.SettingsError) as err:
            self.m.apply(self.panel())
        self.assertIn("Konsol hesabı bölümünde", str(err.exception))
        self.assertFalse((self.root / "sites/panel-wan.caddy").exists())
        with self.assertRaises(settings.SettingsError):
            self.m.validate(self.panel(domain="dav.example.net"))
        # The typed word is checked on the server, only for the panel row.
        with self.assertRaises(settings.SettingsError) as err:
            self.m.validate(self.payload(service="panel", domain="konsol.example.net"))
        self.assertIn("onayla", str(err.exception))
        with self.assertRaises(settings.SettingsError):
            self.m.validate(self.panel(confirm="evet"))
        with self.assertRaises(settings.SettingsError):
            self.m.validate(self.payload(confirm="onayla"))
        # Saved rows alone never conflict (v2-169): the live listener decides, see the fresh-install test.
        pubs.config(self.env, {"web": {"panel": {"tail": True, "enabled": True, "domain": "konsol.example.net"}}})
        store = self.make_account()
        self.assertEqual(self.wan_firewall()[0], "1")  # WebDAV over HTTPS already listens
        self.assertTrue(self.m.apply(self.panel())["committed"])
        # Keeping it on with the same name needs no new word; a new name does.
        self.m.validate(self.payload(service="panel", domain="konsol.example.net"))
        with self.assertRaises(settings.SettingsError):
            self.m.validate(self.payload(service="panel", domain="konsol2.example.net"))
        site = (self.root / "sites/panel-wan.caddy").read_text()
        self.assertIn("https://konsol.example.net:443 {\n\tbind 8.8.8.8\n", site)
        self.assertIn("disable_http_challenge", site)
        self.assertIn('\theader Strict-Transport-Security "max-age=31536000"\n', site)
        self.assertTrue(site.endswith("\timport konsol internet\n}\n"))
        self.assertNotIn("reverse_proxy", site, "only the shared signed-in routes, no other upstream")
        self.assertTrue(pubs.panel_active(self.env))
        with patch.object(tls, "certificate", return_value=1_900_000_000):
            row = pubs.status(self.env)[0]
        self.assertEqual((row["service"], row["status"], row["expires"], row["tail"], row["account"]),
                         ("panel", "ready", 1_900_000_000, True, True))
        # WebDAV's public address closes; the Konsol site alone keeps TCP 443 and its budgets.
        self.assertTrue(self.m.apply(self.payload(enabled=False))["committed"])
        self.assertFalse((self.root / "sites/paylasim-wan.caddy").exists())
        self.assertEqual(self.wan_firewall(), ["1", "16", "64", "443"])
        # A reset account closes the public door at the next publish (the 30-second guard).
        store.reset()
        self.assertFalse(pubs.panel_active(self.env))
        self.s.publish()
        self.assertFalse((self.root / "sites/panel-wan.caddy").exists())
        self.assertEqual(self.wan_firewall()[0], "0")
        row = pubs.status(self.env)[0]
        self.assertEqual(row["status"], "error")
        self.assertIn("Konsol hesabı bölümünde oluşturun", row["message"])

    def legacy_http(self):
        # A fresh install: no HTTPS setting and no WebDAV row, so WebDAV is in legacy consent-gated HTTP mode.
        cfg = self.m.config()
        cfg.pop("https", None)
        cfg.pop("web", None)
        settings.save_json(self.m.config_path, cfg)
        self.assertEqual(tls.config(self.env)["mode"], "http")

    def test_fresh_install_publishes_panel_without_a_webdav_name(self):
        # v2-169: WebDAV's mode alone does not block; folders live on plaintext HTTP do.
        self.legacy_http()
        self.make_account()
        self.s.publish()
        self.assertTrue(self.s.wan_active(), "setUp shares media/alpha over legacy HTTP")
        self.assertTrue(pubs.legacy_http_active(self.env))
        with self.assertRaises(settings.SettingsError) as err:
            self.m.validate(self.panel())
        self.assertIn("eski HTTP ile açık", str(err.exception))
        with patch.object(pubs, "security_check"), self.assertRaises(settings.SettingsError) as err:
            self.m.validate(self.payload(service="torrent", domain="torrent.example.net"))
        self.assertIn("eski HTTP ile açık", str(err.exception))
        row = {r["service"]: r for r in pubs.status(self.env)}["paylasim"]
        self.assertEqual((row["mode"], row["wan_active"]), ("http", True))
        # Closing that folder's internet connection frees the port; no WebDAV name is needed.
        item = self.s.read()["items"][0]
        self.s.change("save", {"id": item["id"], "connections": {"wan": {"enabled": False}}})
        self.assertFalse(pubs.legacy_http_active(self.env))
        self.assertTrue(self.m.apply(self.panel())["committed"])
        self.assertTrue((self.root / "sites/panel-wan.caddy").exists())
        self.assertFalse((self.root / "sites/paylasim-wan.caddy").exists())
        self.assertEqual(self.wan_firewall(), ["1", "16", "64", "443"])
        # While the HTTPS row is on, legacy HTTP stays closed and the cards say why; nothing is rewritten.
        info = self.s.wan_info()
        self.assertFalse(info["available"])
        self.assertIn("HTTPS alan adı gerekir", info["reason"])
        with self.assertRaises(fixtures.shares.ShareError):
            self.s.change("save", {"id": item["id"], "connections": {"wan": {"enabled": True}}, "ack_wan_http": True})
        self.assertFalse(self.s.wan_active())
        row = {r["service"]: r for r in pubs.status(self.env)}["paylasim"]
        self.assertEqual((row["status"], row["wan_active"]), ("http", False))
        self.assertIn("HTTPS alan adı gerekir", row["message"])
        # Turning the Panel row off reopens legacy HTTP for the folders (a plain re-enable).
        self.m.apply(self.payload(service="panel", enabled=False, domain="konsol.example.net"))
        self.assertTrue(self.s.wan_info()["available"])
        self.s.change("save", {"id": item["id"], "connections": {"wan": {"enabled": True}}, "ack_wan_http": True})
        self.assertTrue(self.s.wan_active())
        self.assertEqual(self.wan_firewall(), ["1", "16", "64", "61010"])

    def test_panel_certificate_failure_rolls_back_the_public_site(self):
        self.make_account()
        with patch.object(tls, "wait_certificate", side_effect=settings.SettingsError("cert failed")):
            with self.assertRaises(settings.SettingsError):
                self.m.apply(self.panel())
        self.assertFalse((self.root / "sites/panel-wan.caddy").exists())
        self.assertNotIn("panel", self.m.config().get("web", {}))
        self.assertFalse(self.m.pending_path.exists())
        # Turning it off again removes the site and keeps the remembered name.
        self.m.apply(self.panel())
        self.assertTrue((self.root / "sites/panel-wan.caddy").exists())
        self.m.apply(self.payload(service="panel", enabled=False, domain="konsol.example.net"))
        self.assertFalse((self.root / "sites/panel-wan.caddy").exists())
        self.assertEqual(pubs.config(self.env)["panel"], {"tail": True, "enabled": False, "domain": "konsol.example.net"})

    def test_tail_disabled_preserves_wan_and_folder_accounts(self):
        accounts = self.s.path and Path(self.s.path).read_bytes()
        self.assertTrue(self.m.apply(self.payload(tail=False))["committed"])
        self.assertIn("respond 403", (self.root / "sites/paylasim.caddy").read_text())
        self.assertIn("http://{$TAILSCALE_IPV4}:61010", (self.root / "sites/paylasim.caddy").read_text())
        self.assertIn("https://dav.example.net:443", (self.root / "sites/paylasim-wan.caddy").read_text())
        self.assertEqual(set(self.s.public()["items"][0]["urls"]), {"wan"})
        self.assertEqual(Path(self.s.path).read_bytes(), accounts)
        self.assertFalse(self.s.public()["tail_enabled"])
        self.m.apply(self.payload())
        self.assertIn("respond 401", (self.root / "sites/paylasim.caddy").read_text())

    def test_wan_off_remembers_domain_without_plaintext_fallback(self):
        self.m.apply(self.payload(enabled=False))
        self.assertEqual(pubs.config(self.env)["paylasim"]["domain"], "dav.example.net")
        self.assertEqual(tls.config(self.env)["mode"], "off")
        self.assertFalse((self.root / "sites/paylasim-wan.caddy").exists())
        self.assertEqual(set(self.s.public()["items"][0]["urls"]), {"tailscale"})
        self.s.publish()
        self.assertFalse((self.root / "sites/paylasim-wan.caddy").exists())

    def test_first_row_certificate_failure_restores_private_file(self):
        private = self.root / "sites/paylasim.caddy"
        old = private.read_bytes()
        with patch.object(tls, "wait_certificate", side_effect=settings.SettingsError("cert failed")):
            with self.assertRaises(settings.SettingsError):
                self.m.apply(self.payload(tail=False))
        self.assertEqual(private.read_bytes(), old)
        self.assertNotIn("web", self.m.config())
        self.assertFalse(self.m.pending_path.exists())

    def test_process_crash_restores_private_file_after_reboot(self):
        old = (self.root / "sites/paylasim.caddy").read_bytes()
        with patch.object(tls, "wait_certificate", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.m.apply(self.payload(tail=False))
        with patch.object(settings, "boot_id", return_value="new"), patch.object(tls, "boot_id", return_value="new"):
            self.m.guard()
        self.assertEqual((self.root / "sites/paylasim.caddy").read_bytes(), old)
        self.assertFalse(self.m.pending_path.exists())

    def test_duplicate_domains_and_mixed_writes_rejected(self):
        with self.assertRaises(settings.SettingsError):
            self.m.validate(self.payload(service="torrent"))
        payload = self.payload(); payload["dns"] = self.m.config()["dns"]
        with self.assertRaises(settings.SettingsError):
            self.m.validate(payload)

    def test_dns_error_is_read_only(self):
        before = self.m.config()
        with patch.object(tls, "check_dns", side_effect=settings.SettingsError("DNS mismatch")):
            with self.assertRaises(settings.SettingsError):
                self.m.apply(self.payload(domain="bad.example.net"))
        self.assertEqual(self.m.config(), before)
        self.assertFalse(self.m.pending_path.exists())

    def test_torrent_https_stops_with_module_and_keeps_own_auth(self):
        before = self.qconf.read_bytes()
        # Only the real network probe is mocked; static qBittorrent auth gates run below.
        with patch.object(pubs, "security_check"):
            self.m.apply(self.payload(service="torrent", domain="torrent.example.net"))
        site = self.root / "sites/torrent-wan.caddy"
        self.assertIn("https://torrent.example.net:443", site.read_text())
        self.assertIn("reverse_proxy 127.0.0.1:61006", site.read_text())
        self.assertNotIn("panel", site.read_text())
        self.assertEqual(self.qconf.read_bytes(), before)
        with patch.dict(self.env, SHARE_HTTPS_PORT="18443"):
            custom = pubs.extra_sites(self.env)["torrent-wan.caddy"]
        self.assertIn("header_up Host torrent.example.net\n", custom)
        self.assertIn("header_up X-Forwarded-Host torrent.example.net:18443\n", custom)
        (self.root / "modules").write_text("paylasim\tcalisiyor\ntorrent\tdurduruldu\n")
        self.s.publish()
        self.assertFalse(site.exists())
        self.assertTrue(pubs.config(self.env)["torrent"]["enabled"])

    def test_unsafe_native_auth_fails_closed(self):
        original = self.qconf.read_text()
        pubs.security_check(self.env, "torrent", "torrent.example.net")
        for key, value in (("LocalHostAuth", "false"), ("AuthSubnetWhitelistEnabled", "true"),
                           ("CSRFProtection", "false"), ("HostHeaderValidation", "false"),
                           ("MaxAuthenticationFailCount", "0"), ("BanDuration", "0"), ("ServerDomains", "another.example.net")):
            with self.subTest(key=key):
                self.qconf.write_text(original + "WebUI\\%s=%s\n" % (key, value))
                with self.assertRaises(settings.SettingsError):
                    pubs.security_check(self.env, "torrent", "torrent.example.net")
        self.qconf.write_text("[Preferences]\n")
        with self.assertRaises(settings.SettingsError):
            pubs.security_check(self.env, "torrent", "torrent.example.net")
        # The check module is the package's; a missing or broken one closes the row instead of exposing the app.
        self.qconf.write_text(original)
        module_path = self.root / "templates/torrent/yayin.py"
        module_original = module_path.read_bytes()
        module_path.write_text("def security(env, name, probe=False):\n    raise RuntimeError('x')\n")
        with self.assertRaises(RuntimeError):
            pubs.security_check(self.env, "torrent", "torrent.example.net")
        self.assertFalse(pubs.package_active(self.env, "torrent"))
        module_path.write_text("this is not python\n")
        with self.assertRaises(settings.SettingsError):
            pubs.security_check(self.env, "torrent", "torrent.example.net")
        module_path.unlink()
        with self.assertRaises(settings.SettingsError) as err:
            pubs.security_check(self.env, "torrent", "torrent.example.net")
        self.assertIn("yayın denetimi yok", str(err.exception))
        module_path.write_bytes(module_original)
        pubs.security_check(self.env, "torrent", "torrent.example.net")
        # A manifest without a loopback upstream never produces a row.
        manifest = self.root / "templates/torrent/paket.env"
        kept = manifest.read_text()
        manifest.write_text(kept.replace('PAKET_YAYIN_UPSTREAM="127.0.0.1:61006"', 'PAKET_YAYIN_UPSTREAM="10.0.0.5:61006"'))
        self.assertNotIn("torrent", pubs.packages(self.env))
        self.assertNotIn("torrent", pubs.config(self.env))
        manifest.write_text(kept)
        self.assertEqual(pubs.packages(self.env)["torrent"]["upstream"], "127.0.0.1:61006")

    def test_private_403_stub_uses_exactly_the_module_template_addresses(self):
        # DD-193: no hard-coded host names; the real templates are the single source.
        self.m.apply(self.payload(service="torrent", tail=False, enabled=False, domain=""))
        self.m.apply(self.payload(tail=False))
        values = {"__LOCAL_DOMAIN__": "ev", "__SHARE_PORT__": "61010", "__TORRENT_UI_PORT__": "61006"}
        for service in ("paylasim", "torrent"):
            with self.subTest(service=service):
                source = (settings.Path(__file__).resolve().parents[1] / "magaza" / service / (service + ".caddy")).read_text()
                for key, value in values.items():
                    source = source.replace(key, value)
                first = next(line for line in source.splitlines() if line.startswith("http"))
                stub = pubs.private_site(self.env, service, source)
                self.assertEqual(stub.splitlines()[1], first)
                self.assertIn("\trespond 403\n", stub)
                self.assertNotIn("reverse_proxy", stub)
        extra = "# x\nhttp://torrent.ev, http://torrent-alt.ev {\n\treverse_proxy 127.0.0.1:1\n}\n"
        self.assertIn("http://torrent.ev, http://torrent-alt.ev {", pubs.private_site(self.env, "torrent", extra))
        with self.assertRaises(settings.SettingsError):
            pubs.private_site(self.env, "torrent", "# no site block\n")

    def test_stopped_or_unsafe_torrent_row_reports_the_actual_cause(self):
        with patch.object(pubs, "security_check"):
            self.m.apply(self.payload(service="torrent", domain="torrent.example.net"))
        (self.root / "modules").write_text("paylasim\tcalisiyor\ntorrent\tdurduruldu\n")
        row = next(r for r in pubs.status(self.env) if r["service"] == "torrent")
        self.assertEqual(row["status"], "error")
        self.assertIn("durdurulmuş", row["message"])
        (self.root / "modules").write_text("paylasim\tcalisiyor\n")
        row = next(r for r in pubs.status(self.env) if r["service"] == "torrent")
        self.assertIn("kurulu değil", row["message"])
        (self.root / "modules").write_text("paylasim\tcalisiyor\ntorrent\tcalisiyor\n")
        self.qconf.write_text(self.qconf.read_text() + "WebUI\\AuthSubnetWhitelistEnabled=true\n")
        row = next(r for r in pubs.status(self.env) if r["service"] == "torrent")
        self.assertIn("giriş atlama", row["message"])

    def test_unavailable_listener_fails_fast_without_certificate_wait(self):
        # DD-193: no minute-long certificate wait when no public listener could open.
        import master_shares
        cases = (("paylasim", "dav.example.net", "WAN HTTPS dinleyicisi açılamadı",
                  patch.object(master_shares.Manager, "wan_active", return_value=False)),
                 ("torrent", "torrent.example.net", "qBittorrent internet yayını açılamadı",
                  patch.object(pubs, "package_active", return_value=False)))
        for service, domain, message, blocked in cases:
            with self.subTest(service=service):
                before = self.m.config()
                tls.wait_certificate.reset_mock()
                with blocked, patch.object(pubs, "security_check"), \
                        self.assertRaises(settings.SettingsError) as error:
                    self.m.apply(self.payload(service=service, domain=domain, tail=False))
                self.assertIn(message, str(error.exception))
                tls.wait_certificate.assert_not_called()
                self.assertEqual(self.m.config(), before)
                self.assertFalse(self.m.pending_path.exists())

    def test_reapply_projects_saved_private_choice_and_uninstall_removes_site(self):
        self.m.apply(self.payload(service="torrent", tail=False, enabled=False, domain=""))
        original = (self.root / "templates/torrent/torrent.caddy").read_text()
        self.assertIn("respond 403", pubs.private_site(self.env, "torrent", original))
        (self.root / "sites/torrent.caddy").write_text(original)
        self.s.publish()
        self.assertIn("respond 403", (self.root / "sites/torrent.caddy").read_text())
        (self.root / "modules").write_text("paylasim\tcalisiyor\n")
        self.s.publish()
        self.assertFalse((self.root / "sites/torrent.caddy").exists())

    # --- DD-252: addresses the operator enters ----------------------------------

    def manual(self, local="gezgin", port=8090, tail=True, enabled=True, domain="gezgin.example.net", name="Gezgin"):
        return self.payload(service="elle-" + local, tail=tail, enabled=enabled, domain=domain,
                            elle={"name": name, "local": local, "upstream": "127.0.0.1:%d" % port})

    def test_manual_address_opens_its_tailnet_and_public_names(self):
        result = self.m.apply(self.manual())
        self.assertEqual(result, {"pending": None, "committed": True})
        saved = self.m.config()
        self.assertEqual(saved["elle"], {"elle-gezgin": {"name": "Gezgin", "local": "gezgin", "upstream": "127.0.0.1:8090"}})
        self.assertEqual(saved["web"]["elle-gezgin"], {"tail": True, "enabled": True, "domain": "gezgin.example.net"})
        private = (self.root / "sites/elle-gezgin.caddy").read_text()
        self.assertIn("http://gezgin.ayc {\n\treverse_proxy 127.0.0.1:8090\n}", private)
        public = (self.root / "sites/elle-gezgin-wan.caddy").read_text()
        self.assertIn("https://gezgin.example.net:443 {\n\tbind 8.8.8.8\n", public)
        self.assertIn("reverse_proxy 127.0.0.1:8090 {", public)
        self.assertIn("disable_http_challenge", public)
        # The application's own login is the guard: no Konsol routes or session check.
        self.assertNotIn("konsol", public.replace("# ", ""))
        self.assertNotIn("forward_auth", public)
        self.assertEqual((self.root / "dns/modul-elle.conf").read_text().splitlines()[1:],
                         ["interface-name=gezgin.ayc,tailscale0/4"])
        self.assertIn(["systemctl", "restart", "dnsmasq"], self.calls)
        self.assertIn("Gezgin", pubs.https_apps_active(self.env))
        tls.wait_certificate.assert_called_with(self.m.e, "gezgin.example.net")
        row = next(r for r in pubs.status(self.env) if r["service"] == "elle-gezgin")
        self.assertEqual((row["manual"], row["local"], row["upstream"]), (True, "gezgin.ayc", "127.0.0.1:8090"))
        self.assertIn("yanıt vermiyor", row["message"])  # nothing listens on the fixture port

    def test_manual_address_refuses_konsol_and_package_ports_and_foreign_upstreams(self):
        bad = {"upstream": ("10.0.0.5:80", "localhost:8090", "127.0.0.1:0", "127.0.0.1:70000",
                            "127.0.0.1:61009", "127.0.0.1:61010", "127.0.0.1:61006", "127.0.0.1:8090/x"),
               "local": ("panel", "paylas", "torrent", "Gezgin", "1gezgin", "gez gin", "gezgin.ev"),
               "name": ("", "x" * 41, "a\nb")}
        for key, values in bad.items():
            for value in values:
                payload = self.manual()
                payload["web"]["elle"][key] = value
                if key == "local":
                    payload["web"]["service"] = "elle-" + value
                with self.subTest(key=key, value=value), self.assertRaises(settings.SettingsError):
                    self.m.validate(payload)
        renamed = self.manual()
        renamed["web"]["service"] = "elle-baska"
        with self.assertRaises(settings.SettingsError):
            self.m.validate(renamed)
        with self.assertRaises(settings.SettingsError):  # the gates alone need an existing address
            self.m.validate(self.payload(service="elle-gezgin", enabled=False, domain=""))
        self.assertNotIn("elle", self.m.config())

    def test_manual_name_already_answered_by_dns_is_refused(self):
        (self.root / "dns/modul-baska.conf").write_text("interface-name=gezgin.ayc,tailscale0/4\n")
        with self.assertRaisesRegex(settings.SettingsError, "zaten kullanılıyor"):
            self.m.validate(self.manual())

    def test_manual_limit(self):
        saved = {"elle": {"elle-a%d" % i: {"name": "A", "local": "a%d" % i, "upstream": "127.0.0.1:%d" % (9000 + i)}
                          for i in range(pubs.MANUAL_LIMIT)}}
        request = self.manual(enabled=False, domain="")["web"]
        with self.assertRaisesRegex(settings.SettingsError, "En çok"):
            pubs.validate(self.env, saved, request)

    def test_manual_tailnet_off_then_removal_leaves_nothing(self):
        self.m.apply(self.manual(enabled=False, domain=""))
        self.assertTrue((self.root / "sites/elle-gezgin.caddy").exists())
        self.assertFalse((self.root / "sites/elle-gezgin-wan.caddy").exists())
        self.assertNotIn("Gezgin", pubs.https_apps_active(self.env))
        self.m.apply(self.payload(service="elle-gezgin", tail=False, enabled=False, domain=""))
        self.assertFalse((self.root / "sites/elle-gezgin.caddy").exists())
        self.assertFalse((self.root / "dns/modul-elle.conf").exists())
        self.m.apply({"revision": self.m.revision(), "web": {"service": "elle-gezgin", "sil": True}})
        saved = self.m.config()
        self.assertEqual((saved["elle"], "elle-gezgin" in saved["web"]), ({}, False))
        self.assertEqual(sorted(p.name for p in (self.root / "sites").glob("elle-*")), [])
        with self.assertRaisesRegex(settings.SettingsError, "bulunamadı"):
            self.m.validate({"revision": self.m.revision(), "web": {"service": "elle-gezgin", "sil": True}})

    def test_manual_dns_failure_rolls_back_sites_name_and_settings(self):
        before = self.m.config()
        self.fail_once = "restart dnsmasq"
        with self.assertRaises(subprocess.CalledProcessError):
            self.m.apply(self.manual())
        self.assertEqual(self.m.config(), before)
        self.assertFalse(self.m.pending_path.exists())
        self.assertFalse((self.root / "dns/modul-elle.conf").exists())
        self.assertEqual(sorted(p.name for p in (self.root / "sites").glob("elle-*")), [])
        self.assertNotIn("Gezgin", pubs.https_apps_active(self.env))

    def test_manual_names_follow_a_local_domain_change(self):
        self.m.apply(self.manual(enabled=False, domain=""))
        # The rename itself is under test, not the transaction's reload.
        with patch.object(self.m, "domain_reload"), patch.object(self.m, "pending", return_value={"files_active": False}):
            self.m.domain_apply(dict(self.m.config(), domain="ev"))
        self.assertIn("http://gezgin.ev {", (self.root / "sites/elle-gezgin.caddy").read_text())
        self.assertIn("interface-name=gezgin.ev,tailscale0/4", (self.root / "dns/modul-elle.conf").read_text())
        self.assertEqual(pubs.manual_private_site(self.m.e, pubs.manual(self.m.e)["elle-gezgin"]).split("\n")[1],
                         "http://gezgin.ev {")

    def test_stale_manual_sites_are_removed_but_names_ending_in_wan_kept(self):
        self.m.apply(self.manual(local="ev-wan", enabled=False, domain=""))
        (self.root / "sites/elle-eski.caddy").write_text("http://eski.ayc {\n\trespond 200\n}\n")
        (self.root / "sites/elle-eski-wan.caddy").write_text("# stale\n")
        extras = pubs.extra_sites(self.env)
        self.assertEqual((extras["elle-eski.caddy"], extras["elle-eski-wan.caddy"]), ("", ""))
        self.assertIn("http://ev-wan.ayc {", extras["elle-ev-wan.caddy"])


if __name__ == "__main__":
    unittest.main()
