"""Settings worker tests: no root, services or networking required."""
import base64
import contextlib
import copy
import fcntl
import hashlib
import io
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("master_settings", Path(__file__).resolve().parents[1] / "panel/master_settings.py")
settings = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(settings)


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="settings-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.env = {
            "SETTINGS_FILE": str(self.root / "settings.json"), "SETTINGS_PENDING_FILE": str(self.root / "pending.json"),
            "SETTINGS_DNS_FILE": str(self.root / "dns/konsol.conf"), "DNSMASQ_CONF_FILE": str(self.root / "dns/base.conf"),
            "DNSMASQ_CONF_DIR": str(self.root / "dns"), "TORRENT_PROFILE_DIR": str(self.root / "profile"),
            "UNIT_DIR": str(self.root / "units"), "MODULES_FILE": str(self.root / "modules"),
            "MODULES_DIR": str(self.root / "templates"), "RUNTIME_DIR": str(self.root / "run"),
            "SERVER_ROOT": str(self.root / "srv"), "DOWNLOADS_PATH": str(self.root / "srv/downloads"), "MEDIA_SUBDIR": "media",
            "LOCAL_DOMAIN": "ayc", "TAILSCALE_IF": "tailscale0", "WAN_INTERFACE": "eth0", "WAN_IPV4": "203.0.113.1",
            "TAILSCALE_IPV4": "100.64.0.2", "DOWNLOADS_UID": str(os.getuid()), "DOWNLOADS_GID": str(os.getgid()),
            "SBIN_DIR": str(self.root / "bin"), "DNS_PORT": "53", "CADDY_HTTP_PORT": "80",
            "CADDYFILE": str(self.root / "Caddyfile"), "CADDY_MODULES_DIR": str(self.root / "caddy-modules"),
        }
        for rel in ("dns", "templates/torrent", "srv/downloads", "srv/media/movies", "srv/.pay", "units", "run"):
            (self.root / rel).mkdir(parents=True, exist_ok=True)
        (self.root / "modules").write_text("torrent\tcalisiyor\n")
        (self.root / "networks").write_text("wg0\t61001\tui\n")
        (self.root / "templates/torrent/dnsmasq.conf").write_text("interface-name=torrent.ayc,tailscale0\n")
        (self.root / "dns/base.conf").write_text("interface=lo\ninterface=tailscale0\nno-resolv\nlocal=/ayc/\ninterface-name=panel.ayc,tailscale0\ninterface-name=health.ayc,tailscale0\n")
        self.state = self.root / "state.env"
        self.state.write_text("".join(k + "=" + v + "\n" for k, v in self.env.items()))
        self.m = settings.Manager(self.state)
        self.now = 1000
        self.calls = []
        self.fail_cmd = None
        self.addCleanup(patch.stopall)
        patch.object(settings, "boot_id", return_value="boot-a").start()
        patch.object(settings.time, "monotonic", side_effect=lambda: self.now).start()
        patch.object(settings, "run", side_effect=self.fake_run).start()

    def fake_run(self, argv, **kwargs):
        self.calls.append(argv)
        if self.fail_cmd and self.fail_cmd in " ".join(argv):
            self.fail_cmd = None
            raise settings.SettingsError("injected failure")
        return subprocess.CompletedProcess(argv, 0, "", "")

    def payload(self, **kwargs):
        return dict(revision=self.m.revision(), **kwargs)

    def rule(self, **kwargs):
        return dict(dict(id="one", name="Test port", family=4, scope="wan", proto="tcp", port=12345, source="", allow=True), **kwargs)

    def dns(self, **kwargs):
        return dict(copy.deepcopy(settings.DEFAULT["dns"]), **kwargs)

    def confirm(self):
        return self.m.confirm({"id": self.m.pending()["id"], "client": "100.64.0.9", "kanal": "tailscale"})

    def test_defaults_and_no_secrets_in_status(self):
        s = self.m.status()
        self.assertEqual(s["config"], settings.DEFAULT)
        # DD-202: the base's status knows no application account or folder.
        self.assertFalse({"username", "save"} & set(s), sorted(s))

    def test_stale_revision_and_external_dns_change(self):
        data = self.payload(firewall=[])
        base = Path(self.env["DNSMASQ_CONF_FILE"])
        base.write_text(base.read_text() + "# changed outside the transaction\n")
        with self.assertRaises(settings.SettingsError):
            self.m.validate(data)
        self.assertFalse(self.m.pending_path.exists())

    def test_firewall_validation(self):
        invalid = [dict(port=0), dict(port=True), dict(port=65536), dict(proto="tcp;id"), dict(scope="lo"),
                   dict(source="1.2.3.4;id"), dict(source="::1/128"), dict(family="4"), dict(id="x y"), dict(allow="yes"), dict(scope="wg9")]
        for change in invalid:
            with self.subTest(change=change), self.assertRaises(settings.SettingsError):
                self.m.validate(self.payload(firewall=[self.rule(**change)]))
        with self.assertRaises(settings.SettingsError):
            self.m.validate(self.payload(firewall=[self.rule(), self.rule(id="two")]))

    def test_rules_normalize_source_and_live_wan(self):
        self.m.apply(self.payload(firewall=[self.rule(source="192.0.2.18/24"), self.rule(id="ipv6", family=6, scope="tail", source="2001:db8::/32", allow=False)]))
        args = self.m.rules(4, "ens3")[0]
        self.assertIn("ens3", args)
        self.assertIn("192.0.2.0/24", args)
        self.assertEqual(self.m.rules(6)[0][-1], "DROP")
        self.assertEqual(self.m.rules(6)[0][1], "tailscale0")

    def test_apply_confirm_is_persistent(self):
        self.m.apply(self.payload(firewall=[self.rule()]))
        self.assertEqual(self.m.config()["firewall"], [])
        self.assertEqual(self.m.pending()["phase"], "awaiting")
        self.assertEqual(self.m.pending_path.stat().st_mode & 0o777, 0o600)
        self.confirm()
        self.assertIsNone(self.m.pending())
        self.assertEqual(self.m.config()["firewall"], [self.rule()])
        self.assertEqual(self.m.config_path.stat().st_mode & 0o777, 0o600)

    def test_deadline_and_reboot_rollback(self):
        for reboot in (False, True):
            self.m.apply(self.payload(firewall=[self.rule()]))
            if reboot:
                with patch.object(settings, "boot_id", return_value="boot-b"):
                    self.assertEqual(self.m.current()["firewall"], [])
                    self.m.guard()
            else:
                self.now += 61
                with self.assertRaises(settings.SettingsError):
                    self.confirm()
                self.m.guard()
            self.assertIsNone(self.m.pending())
            self.assertEqual(self.m.current()["firewall"], [])

    def test_pending_blocks_second_apply(self):
        self.m.apply(self.payload(firewall=[self.rule()]))
        with self.assertRaises(settings.SettingsError):
            self.m.apply(self.payload(firewall=[]))

    def test_forged_id_or_local_confirm_rejected(self):
        self.m.apply(self.payload(firewall=[]))
        for data in ({"id": "wrong", "client": "100.64.0.9"}, {"id": self.m.pending()["id"], "client": "127.0.0.1"}):
            with self.assertRaises(settings.SettingsError):
                self.m.confirm(data)

    def test_existing_tcp_connection_is_not_connectivity_proof(self):
        self.m.apply(self.payload(firewall=[self.rule(scope="tail", port=80, allow=False)]))
        with self.assertRaises(settings.SettingsError):
            self.confirm()
        self.m.rollback()
        self.m.apply(self.payload(firewall=[self.rule(scope="tail", port=80, source="100.64.0.20/32", allow=False)]))
        self.confirm()

    def test_disable_panel_is_rejected_before_mutation(self):
        before = Path(self.env["DNSMASQ_CONF_FILE"]).read_bytes()
        for extra in ({}, {"firewall": []}):
            with self.subTest(extra=extra), self.assertRaises(settings.SettingsError):
                self.m.apply(self.payload(dns=self.dns(disabled=["panel.ayc"]), **extra))
        self.assertEqual(before, Path(self.env["DNSMASQ_CONF_FILE"]).read_bytes())
        self.assertIsNone(self.m.pending())
        self.assertFalse(self.m.config_path.exists())
        self.assertEqual(self.calls, [])

    def test_dns_only_commits_immediately_and_survives_deadline_and_reboot(self):
        dns = self.dns(disabled=["health.ayc"])
        result = self.m.apply(self.payload(dns=dns))
        self.assertEqual(result, {"pending": None, "committed": True})
        self.assertIsNone(self.m.pending())
        self.assertEqual(self.m.config_path.stat().st_mode & 0o777, 0o600)
        self.now += 181
        with patch.object(settings, "boot_id", return_value="boot-b"):
            recovered = settings.Manager(self.state)
            recovered.guard()
            self.assertEqual(recovered.current()["dns"], dns)
        self.assertEqual(self.m.config()["firewall"], [])
        self.assertIn(["systemctl", "restart", "dnsmasq"], self.calls)

    def test_mixed_dns_keeps_confirmation_even_with_unchanged_firewall(self):
        for extra in ({"firewall": []},):
            with self.subTest(extra=extra):
                self.m.apply(self.payload(dns=self.dns(disabled=["health.ayc"]), **extra))
                self.assertEqual(self.m.status()["pending"]["seconds"], 60)
                self.assertEqual(self.m.config()["dns"], settings.DEFAULT["dns"])
                self.now += 61
                self.m.guard()
                self.assertEqual(self.m.current()["dns"], settings.DEFAULT["dns"])

    def test_dns_restart_or_commit_failure_restores_previous_config(self):
        self.m.apply(self.payload(dns=self.dns(records=[dict(name="nas.ayc", target="tailscale", enabled=True)])))
        before = self.m.config()
        for failure in ("restart", "commit"):
            with self.subTest(failure=failure):
                if failure == "restart":
                    self.fail_cmd = "restart dnsmasq"
                    with self.assertRaises(settings.SettingsError):
                        self.m.apply(self.payload(dns=self.dns(disabled=["health.ayc"])))
                else:
                    with patch.object(self.m, "commit", side_effect=OSError("disk failure")), self.assertRaises(OSError):
                        self.m.apply(self.payload(dns=self.dns(disabled=["health.ayc"])))
                self.assertIsNone(self.m.pending())
                self.assertEqual(self.m.config(), before)
                self.assertIn("interface-name=nas.ayc", self.m.dns_file.read_text())

    def test_dns_crash_recovery_before_and_after_durable_commit(self):
        for committed in (False, True):
            with self.subTest(committed=committed):
                dns = self.dns(disabled=["health.ayc"])
                def crash(p):
                    if committed:
                        settings.save_json(self.m.config_path, dict(p["candidate"], _transaction=p["id"]))
                    raise SystemExit("simulated process death")
                with patch.object(self.m, "commit", side_effect=crash), self.assertRaises(SystemExit):
                    self.m.apply(self.payload(dns=dns))
                self.assertEqual(self.m.pending()["phase"], "applying")
                self.now += 181
                self.m.guard()
                self.assertIsNone(self.m.pending())
                self.assertEqual(self.m.config()["dns"], dns if committed else settings.DEFAULT["dns"])

    def test_dns_rejects_client_confirmation_bypass_flag(self):
        with self.assertRaises(settings.SettingsError):
            self.m.apply(self.payload(dns=self.dns(), firewall=[], committed=True))
        self.assertIsNone(self.m.pending())

    def test_dns_projection_survives_rerender_and_private_zone_stays_local(self):
        self.m.apply(self.payload(dns=self.dns(disabled=["health.ayc"], forward=True, servers=["1.1.1.1"],
                         records=[{"name": "nas.ayc", "target": "192.0.2.10", "enabled": True}])))
        base = Path(self.env["DNSMASQ_CONF_FILE"])
        self.assertIn(settings.OFF + "interface-name=health.ayc", base.read_text())
        base.write_text(base.read_text().replace(settings.OFF, ""))
        self.m.project_dns()
        self.assertIn(settings.OFF, base.read_text())
        self.assertIn("local=/ayc/", base.read_text())
        self.assertIn("no-resolv", base.read_text())
        self.assertIn("host-record=nas.ayc,192.0.2.10", self.m.dns_file.read_text())
        self.assertIn("server=1.1.1.1", self.m.dns_file.read_text())
        self.assertEqual(len(self.m.dns_names()), 2)

    def test_dns_invalid_collisions_and_upstream_loops(self):
        for ip in ["127.0.0.1", "100.100.100.100", "192.168.1.1", "::1", "224.0.0.1", "not-an-ip", "1.1.1.1\nserver=evil"]:
            with self.subTest(ip=ip), self.assertRaises(settings.SettingsError):
                self.m.validate(self.payload(dns=self.dns(forward=True, servers=[ip])))
        for name in ["panel.ayc", "torrent.ayc", "evil.example", "bad..ayc", "-bad.ayc", "*.ayc"]:
            with self.subTest(name=name), self.assertRaises(settings.SettingsError):
                self.m.validate(self.payload(dns=self.dns(records=[{"name": name, "target": "tailscale", "enabled": True}])))

    def test_apply_failure_restores_dns_and_preserves_pending_on_recovery_failure(self):
        before = Path(self.env["DNSMASQ_CONF_FILE"]).read_bytes()
        self.fail_cmd = "checkconfig"
        # Works on Linux and macOS (the fallback validator is dnsmasq --test).
        with patch.object(self.m, "dns_test", side_effect=[settings.SettingsError("test"), None]):
            with self.assertRaises(settings.SettingsError):
                self.m.apply(self.payload(dns=self.dns(disabled=["health.ayc"])))
        self.assertEqual(before, Path(self.env["DNSMASQ_CONF_FILE"]).read_bytes())
        self.assertIsNone(self.m.pending())

    def test_directory_scope_and_symlinks(self):
        for value in (str(self.root / "srv"), str(self.root / "srv/.pay"), "/etc", str(self.root / "srv/downloads/../media")):
            with self.subTest(value=value), self.assertRaises(settings.SettingsError):
                self.m.safe_dir(value)
        link = self.root / "srv/downloads/link"
        link.symlink_to(self.root / "srv/media", target_is_directory=True)
        with self.assertRaises(settings.SettingsError):
            self.m.safe_dir(str(link))
        self.assertEqual(self.m.safe_dir(str(self.root / "srv/media")), self.root / "srv/media")
        self.assertNotIn(str(link), [x["path"] for x in self.m.folders(str(link.parent))])

    def test_lock_blocks_mutation(self):
        with self.m.locked():
            with self.assertRaises(settings.SettingsError):
                with self.m.locked():
                    pass

    def test_commit_crash_window_does_not_undo_confirmed_transaction(self):
        self.m.apply(self.payload(firewall=[self.rule()]))
        p = self.m.pending()
        settings.save_json(self.m.config_path, dict(p["candidate"], _transaction=p["id"]))
        self.now += 61
        self.m.guard()
        self.assertEqual(self.m.config()["firewall"], [self.rule()])
        self.assertIsNone(self.m.pending())

    def test_recovery_failure_keeps_pending_for_timer_retry(self):
        with patch.object(self.m, "dns_test", side_effect=settings.SettingsError("retry")), self.assertRaises(settings.SettingsError):
            self.m.apply(self.payload(dns=self.dns(disabled=["health.ayc"])))
        self.assertEqual(self.m.pending()["phase"], "rollback")
        self.assertEqual((self.m.pending()["attempts"], self.m.pending()["error"]), (1, "retry"))
        # DD-182: the next automatic attempt waits for the backoff.
        self.m.guard()
        self.assertIsNotNone(self.m.pending())
        self.assertEqual(self.m.status()["pending"]["retry_in"], 15)
        self.now += 15
        self.m.guard()
        self.assertIsNone(self.m.pending())

    def test_rollback_that_keeps_failing_becomes_stuck_and_waits_for_the_operator(self):
        self.m.apply(self.payload(firewall=[self.rule()]))
        self.now += 61
        with patch.object(self.m, "firewall_apply", side_effect=settings.SettingsError("iptables busy")):
            waits = []
            for attempt in range(1, 6):
                with self.assertRaises(settings.SettingsError):
                    self.m.guard()
                p = self.m.pending()
                self.assertEqual(p["attempts"], attempt)
                if attempt < 5:
                    waits.append(p["retry_at"] - self.now)
                    self.now = p["retry_at"]
            self.assertEqual(waits, [15, 30, 60, 120])
            self.assertEqual(self.m.pending()["phase"], "stuck")
            self.assertEqual(self.m.status()["pending"]["error"], "iptables busy")
            calls = len(self.calls)
            self.m.guard()  # no more automatic attempts
            self.assertEqual(len(self.calls), calls)
            with self.assertRaises(settings.SettingsError):
                self.m.rollback(manual=True)  # the operator's retry still runs
            self.assertEqual((self.m.pending()["phase"], self.m.pending()["attempts"]), ("stuck", 6))
        self.m.rollback(manual=True)
        self.assertIsNone(self.m.pending())

    def test_discard_needs_a_stuck_rollback_its_id_and_the_typed_word(self):
        self.m.apply(self.payload(firewall=[self.rule()]))
        p = self.m.pending()
        with self.assertRaises(settings.SettingsError):
            self.m.discard({"id": p["id"], "confirm": "onayla"})  # awaiting, not stuck
        p.update(phase="stuck", attempts=5, error="x")
        settings.save_json(self.m.pending_path, p)
        for data in ({"id": p["id"]}, {"id": p["id"], "confirm": "evet"}, {"id": "other", "confirm": "onayla"}):
            with self.assertRaises(settings.SettingsError):
                self.m.discard(data)
            self.assertIsNotNone(self.m.pending())
        self.assertEqual(self.m.discard({"id": p["id"], "confirm": " ONAYLA "}), {"ok": True})
        self.assertIsNone(self.m.pending())
        self.assertEqual(self.m.config()["firewall"], [])  # nothing was committed

    def test_timer_must_be_active_before_any_mutation(self):
        self.fail_cmd = "master-settings-guard.timer"
        with self.assertRaises(settings.SettingsError):
            self.m.apply(self.payload(firewall=[self.rule()]))
        self.assertEqual(self.m.config()["firewall"], [])
        self.assertEqual([c for c in self.calls if "master-settings-guard.timer" not in c], [])
        self.assertIsNone(self.m.pending())

    def test_apply_starts_the_guard_timer_before_the_pending_file(self):
        start = ["systemctl", "start", "master-settings-guard.timer"]
        written = []
        original = settings.save_json
        with patch.object(settings, "save_json", side_effect=lambda *a, **k: (written.append(len(self.calls)), original(*a, **k))):
            self.m.apply(self.payload(firewall=[self.rule()]))
        self.assertIn(start, self.calls)
        self.assertLess(self.calls.index(start), written[0])

    def run_guard(self):
        with patch("sys.argv", ["master_settings.py", "--state", str(self.state), "guard"]), \
                contextlib.redirect_stdout(io.StringIO()):
            settings.main()

    def test_idle_guard_stops_its_timer_only_when_it_holds_the_locks(self):
        stop = ["systemctl", "stop", "--no-block", "master-settings-guard.timer"]
        with open(self.root / "run/settings.lock", "a") as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.run_guard()
        self.assertNotIn(stop, self.calls)
        self.run_guard()
        self.assertIn(stop, self.calls)
        # Something pending: the timer keeps running.
        self.calls.clear()
        self.m.apply(self.payload(firewall=[self.rule()]))
        self.assertIsNotNone(self.m.pending())
        self.run_guard()
        self.assertNotIn(stop, self.calls)
        # DD-182: a stuck rollback waits for the operator, so the timer sleeps too.
        p = self.m.pending()
        p.update(phase="stuck", attempts=5)
        settings.save_json(self.m.pending_path, p)
        self.run_guard()
        self.assertIn(stop, self.calls)

    def test_symlinked_parent_cannot_redirect_root_file_access(self):
        link = self.root / "redirect"
        link.symlink_to(self.root / "dns", target_is_directory=True)
        conf = self.root / "dns" / "base.conf"
        before = conf.read_bytes()
        target = link / conf.name
        with self.assertRaises(OSError):
            settings.atomic(target, "injected")
        with self.assertRaises(OSError):
            self.m.snapshot(target)
        self.assertEqual(before, conf.read_bytes())

    def domain_fixture(self):
        (self.root / "Caddyfile").write_text('(konsol) {\n\treverse_proxy x {\n\t\theader_up Host panel.ayc\n\t}\n}\n'
                                             'http://panel.ayc {\n respond "test"\n}\n# leave /some.ayc unchanged\n')
        for rel in ("caddy-modules", "templates/dosya"):
            (self.root / rel).mkdir(exist_ok=True)
        unit = "[Service]\nExecStart=/bin/backend --domain=ayc --version=test\n"
        for rel in ("units/master-files-panel.service", "templates/dosya/master-files-panel.service"):
            (self.root / rel).write_text(unit)
        site = 'http://paylas.ayc, http://{$TAILSCALE_IPV4}:61010 {\n respond "test"\n}\n'
        (self.root / "caddy-modules/paylasim.caddy").write_text(site)
        settings.save_json(self.m.config_path, dict(copy.deepcopy(settings.DEFAULT), dns=self.dns(
            disabled=["torrent.ayc"], records=[dict(name="nas.ayc", target="192.0.2.8", enabled=False)],
            forward=True, servers=["1.1.1.1"])))

    def test_domain_migration_templates_names_and_new_host_confirmation(self):
        self.domain_fixture()
        self.m.apply(self.payload(domain="ev"))
        self.assertEqual(self.m.status()["pending"]["domain"], {"old": "ayc", "new": "ev"})
        self.assertEqual(self.m.status()["pending"]["seconds"], 300)
        self.assertEqual(settings.env_read(self.state)["LOCAL_DOMAIN"], "ev")
        self.assertIn("http://panel.ev", (self.root / "Caddyfile").read_text())
        self.assertIn("\t\theader_up Host panel.ev\n", (self.root / "Caddyfile").read_text())
        self.assertIn("/some.ayc", (self.root / "Caddyfile").read_text())
        self.assertIn("http://paylas.ev, http://{$TAILSCALE_IPV4}:61010", (self.root / "caddy-modules/paylasim.caddy").read_text())
        self.assertIn("torrent.ev", (self.root / "templates/torrent/dnsmasq.conf").read_text())
        self.assertIn("--domain=ev ", (self.root / "templates/dosya/master-files-panel.service").read_text())
        self.assertIn("local=/ev/", Path(self.env["DNSMASQ_CONF_FILE"]).read_text())
        self.assertEqual(self.m.current()["dns"]["disabled"], ["torrent.ev"])
        self.assertEqual(self.m.current()["dns"]["records"], [dict(name="nas.ev", target="192.0.2.8", enabled=False)])
        self.assertEqual(self.m.current()["dns"]["servers"], ["1.1.1.1"])
        for host in ("panel.ayc", "127.0.0.1", "panel.ev.evil", ""):
            with self.subTest(host=host), self.assertRaises(settings.SettingsError):
                self.m.confirm({"id": self.m.pending()["id"], "client": "100.64.0.9", "host": host, "kanal": "tailscale"})
        # DD-195: the public Konsol site may not confirm, even from a 100.64/10 (CGNAT) address.
        with self.assertRaises(settings.SettingsError):
            self.m.confirm({"id": self.m.pending()["id"], "client": "100.64.0.9", "host": "panel.ev", "kanal": "internet"})
        self.m.confirm({"id": self.m.pending()["id"], "client": "100.64.0.9", "host": "panel.ev", "kanal": "tailscale"})
        self.assertEqual(settings.saved_domain(self.m.config_path), "ev")
        self.assertIn(["systemctl", "reload", "caddy.service"], self.calls)
        self.assertNotIn(["systemctl", "restart", "master-panel.service"], self.calls)

    def test_domain_timeout_restores_files_but_not_new_tailscale_ip(self):
        self.domain_fixture()
        before = {p: p.read_bytes() for p in [*self.m.domain_paths(), *self.m.dns_paths()]}
        self.m.apply(self.payload(domain="ev"))
        self.state.write_text(self.state.read_text().replace("TAILSCALE_IPV4=100.64.0.2", "TAILSCALE_IPV4=100.64.0.3"))
        self.now += 301
        recovered = settings.Manager(self.state)
        recovered.guard()
        self.assertIsNone(recovered.pending())
        self.assertEqual(settings.env_read(self.state)["LOCAL_DOMAIN"], "ayc")
        self.assertEqual(settings.env_read(self.state)["TAILSCALE_IPV4"], "100.64.0.3")
        for path, content in before.items():
            self.assertEqual(path.read_bytes(), content)
        self.assertEqual(settings.saved_domain(self.m.config_path), "")

    def test_domain_failure_reboot_and_committed_crash_recovery(self):
        for reason in ("validator", "reboot", "commit-crash"):
            with self.subTest(reason=reason):
                self.domain_fixture()
                if reason == "validator":
                    self.fail_cmd = "caddy validate"
                    with self.assertRaises(settings.SettingsError):
                        self.m.apply(self.payload(domain="ev"))
                    self.assertEqual(self.m.e["LOCAL_DOMAIN"], "ayc")
                    self.assertIsNone(self.m.pending())
                    continue
                self.m.apply(self.payload(domain="ev"))
                if reason == "commit-crash":
                    p = self.m.pending()
                    settings.save_json(self.m.config_path, dict(p["candidate"], _transaction=p["id"]))
                with patch.object(settings, "boot_id", return_value="new-boot"):
                    settings.Manager(self.state).guard()
                self.assertEqual(settings.env_read(self.state)["LOCAL_DOMAIN"], "ev" if reason == "commit-crash" else "ayc")
                self.m = settings.Manager(self.state)

    def test_domain_validation_revision_and_stopped_file_backend(self):
        self.domain_fixture()
        for value in ("", "AyC", "new.example", "bad;id", "a\nb", "-bad", "bad-", "x" * 64, "ayc", None):
            with self.subTest(value=value), self.assertRaises(settings.SettingsError):
                self.m.validate(self.payload(domain=value))
        with self.assertRaises(settings.SettingsError):
            self.m.validate(self.payload(domain="ev", firewall=[]))
        stale = self.payload(domain="ev")
        (self.root / "Caddyfile").write_text((self.root / "Caddyfile").read_text() + "# external edit\n")
        with self.assertRaises(settings.SettingsError):
            self.m.validate(stale)
        original = self.fake_run
        def inactive(argv, **kwargs):
            if argv == ["systemctl", "is-active", "--quiet", "master-files-panel.service"]:
                return subprocess.CompletedProcess(argv, 3, "", "")
            return original(argv, **kwargs)
        with patch.object(settings, "run", side_effect=inactive):
            self.m.apply(self.payload(domain="ev"))
            self.m.rollback()
        self.assertNotIn(["systemctl", "restart", "master-files-panel.service"], self.calls)

    def test_saved_domain_only_reads_confirmed_value_and_rejects_corruption(self):
        self.assertEqual(settings.saved_domain(self.m.config_path), "")
        settings.save_json(self.m.config_path, dict(copy.deepcopy(settings.DEFAULT), domain="ev"))
        self.assertEqual(settings.saved_domain(self.m.config_path), "ev")
        settings.save_json(self.m.config_path, {"domain": "ev;id"})
        with self.assertRaises(settings.SettingsError):
            settings.saved_domain(self.m.config_path)


if __name__ == "__main__":
    unittest.main()
