"""DD-239: master-onar (check and repair) with fake systemctl/tailscale/ip/dig/curl/master-firewall on PATH:
check-only changes nothing, repair restarts exactly the broken units, a stopped package and a disabled network
are left alone, the address step hands over to refresh-tailnet-config, the report file follows every step,
--duvar touches only the firewall, and the panel's start/route rules. Temporary directories only."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "panel"))
import master_onar as mo
import master_update as mu
import test_resources

panel = test_resources.panel

FAKES = {
    # state/<unit> holds the ActiveState (default active); fail/<unit> makes a restart fail; enabled/<unit>=disabled.
    "systemctl": r'''
F="$FAKE"; echo "systemctl $*" >> "$F/calls"
case "$1" in
  show) shift; for a in "$@"; do case "$a" in --*) ;; *)
        st=active; [ -f "$F/state/$a" ] && st=$(cat "$F/state/$a")
        en=enabled; [ -f "$F/enabled/$a" ] && en=$(cat "$F/enabled/$a")
        ld=loaded; [ -f "$F/missing/$a" ] && ld=not-found
        printf 'Id=%s\nLoadState=%s\nActiveState=%s\nUnitFileState=%s\n\n' "$a" "$ld" "$st" "$en";; esac; done ;;
  restart) [ -f "$F/fail/$2" ] && exit 1; echo active > "$F/state/$2"
        [ "$2" = master-firewall.service ] && echo 0 > "$F/fw_rc"
        [ "$2" = dnsmasq.service ] && echo ok > "$F/dns"
        [ "$2" = master-panel.service ] && echo 200 > "$F/http"; exit 0 ;;
  reset-failed) exit 0 ;;
  list-units) for f in "$F"/state/*; do [ -f "$f" ] && [ "$(cat "$f")" = failed ] && echo "$(basename "$f") loaded failed failed x"; done; exit 0 ;;
esac''',
    "master-firewall": r'''echo "master-firewall $*" >> "$FAKE/calls"; exit "$(cat "$FAKE/fw_rc" 2>/dev/null || echo 0)"''',
    "tailscale": r'''echo "tailscale $*" >> "$FAKE/calls"
[ "$1" = status ] && cat "$FAKE/ts.json"; exit 0''',
    "ip": r'''echo "3: tailscale0    inet $(cat "$FAKE/ip")/32 scope global tailscale0"''',
    "dig": r'''[ "$(cat "$FAKE/dns" 2>/dev/null)" = ok ] && echo 100.64.0.2; exit 0''',
    "curl": r'''printf '%s' "$(cat "$FAKE/http" 2>/dev/null || echo 403)"''',
    "master-modul": r'''echo "master-modul $*" >> "$FAKE/calls"; cat "$FAKE/saglik" 2>/dev/null; exit 0''',
    "refresh-tailnet-config": r'''echo "refresh $*" >> "$FAKE/calls"; sed -i "s/^TAILSCALE_IPV4=.*/TAILSCALE_IPV4=$(cat "$FAKE/ip")/" "$STATE_FILE"''',
}


class Fixture(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="onar-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.bin, self.fake = self.root / "bin", self.root / "fake"
        for d in (self.bin, self.fake / "state", self.fake / "fail", self.fake / "enabled", self.fake / "missing"):
            d.mkdir(parents=True)
        for name, body in FAKES.items():
            p = self.bin / name
            p.write_text("#!/bin/bash\n" + body + "\n")
            p.chmod(0o755)
        (self.fake / "ts.json").write_text(json.dumps({"BackendState": "Running", "Self": {"Online": True}}))
        (self.fake / "ip").write_text("100.64.0.2")
        (self.fake / "dns").write_text("ok")
        (self.fake / "http").write_text("403")
        (self.fake / "missing" / "master-sistem-dosya.service").write_text("")
        self.modules = self.root / "moduller"
        self.modules.write_text("torrent\tcalisiyor\nwireguard\tdurduruldu\n")
        (self.fake / "saglik").write_text("torrent\tqbittorrent.service\tgerekli\nwireguard\twg-quick@wg0.service\tag\n")
        self.state = self.root / "state.env"
        self.report = self.root / "onarim.json"
        self.state.write_text("TAILSCALE_IPV4=100.64.0.2\nTAILSCALE_IF=tailscale0\nLOCAL_DOMAIN=ev\nSBIN_DIR=%s\nMODULES_FILE=%s\n"
                              "RUNTIME_DIR=%s\nONARIM_DURUM_FILE=%s\n" % (self.bin, self.modules, self.root / "run", self.report))
        env = {"PATH": "%s:%s" % (self.bin, os.environ["PATH"]), "FAKE": str(self.fake), "STATE_FILE": str(self.state)}
        patcher = patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        patch.object(mo, "STATE_FILE", str(self.state)).start()
        patch.object(mo.time, "sleep", lambda s: None).start()
        self.addCleanup(patch.stopall)

    def calls(self):
        path = self.fake / "calls"
        return path.read_text().splitlines() if path.exists() else []

    def restarts(self):
        return [c.split()[-1] for c in self.calls() if c.startswith("systemctl restart")]

    def run_repair(self, fix=True):
        r = mo.Repair(mo.read_env(str(self.state)), fix, str(self.report))
        code = r.all()
        return code, {s["id"]: s for s in json.loads(self.report.read_text())["adimlar"]}, json.loads(self.report.read_text())


class RepairTests(Fixture):
    def test_healthy_host_is_left_alone(self):
        code, steps, report = self.run_repair()
        self.assertEqual(code, 0)
        self.assertEqual(report["durum"], "tamam")
        self.assertEqual({s: v["durum"] for s, v in steps.items()},
                         {"duvar": "ok", "tailscale": "ok", "adres": "ok", "servisler": "ok", "dns": "ok", "konsol": "ok", "diger": "ok"})
        self.assertEqual(self.restarts(), [])
        self.assertIsInstance(report["bitis"], int)

    def test_check_only_reports_and_changes_nothing(self):
        (self.fake / "fw_rc").write_text("1")
        (self.fake / "state" / "caddy.service").write_text("failed")
        (self.fake / "ip").write_text("100.64.0.9")
        code, steps, report = self.run_repair(fix=False)
        self.assertEqual(code, 1)
        self.assertEqual(report["kip"], "denetle")
        self.assertEqual(steps["duvar"]["durum"], "sorun")
        self.assertEqual(steps["servisler"]["durum"], "sorun")
        self.assertIn("caddy.service", steps["servisler"]["detay"])
        self.assertIn("Kayıtlı 100.64.0.2, şimdiki 100.64.0.9", steps["adres"]["detay"])
        self.assertEqual(self.restarts(), [])
        self.assertFalse(any(c.startswith("refresh") for c in self.calls()))

    def test_repair_restarts_exactly_the_broken_units(self):
        (self.fake / "fw_rc").write_text("1")
        for unit in ("caddy.service", "qbittorrent.service"):
            (self.fake / "state" / unit).write_text("failed")
        # A stopped package's network and a missing unit are not touched.
        (self.fake / "state" / "wg-quick@wg0.service").write_text("inactive")
        code, steps, _ = self.run_repair()
        self.assertEqual(code, 0)
        self.assertEqual(steps["duvar"]["durum"], "onarildi")
        self.assertEqual(steps["servisler"]["durum"], "onarildi")
        self.assertEqual(sorted(self.restarts()), ["caddy.service", "master-firewall.service", "qbittorrent.service"])
        self.assertNotIn("wg-quick@wg0.service", self.restarts())
        self.assertNotIn("master-sistem-dosya.service", self.restarts())

    def test_a_disabled_network_of_a_running_package_is_left_alone(self):
        self.modules.write_text("wireguard\tcalisiyor\n")
        (self.fake / "state" / "wg-quick@wg0.service").write_text("inactive")
        (self.fake / "enabled" / "wg-quick@wg0.service").write_text("disabled")
        _, steps, _ = self.run_repair()
        self.assertEqual(steps["servisler"]["durum"], "ok")
        (self.fake / "enabled" / "wg-quick@wg0.service").write_text("enabled")
        _, steps, _ = self.run_repair()
        self.assertEqual(steps["servisler"]["durum"], "onarildi")
        self.assertIn("wg-quick@wg0.service", self.restarts())

    def test_a_unit_that_will_not_start_is_an_error(self):
        (self.fake / "state" / "master-paylasim.service").write_text("failed")
        (self.fake / "fail" / "master-paylasim.service").write_text("")
        code, steps, report = self.run_repair()
        self.assertEqual(code, 1)
        self.assertEqual(report["durum"], "hata")
        self.assertEqual(steps["servisler"]["durum"], "hata")
        self.assertIn("master-paylasim.service", steps["servisler"]["detay"])

    def test_address_change_hands_over_to_refresh_tailnet_config(self):
        (self.fake / "ip").write_text("100.64.0.9")
        _, steps, _ = self.run_repair()
        self.assertEqual(steps["adres"]["durum"], "onarildi")
        self.assertIn("100.64.0.2 → 100.64.0.9", steps["adres"]["detay"])
        self.assertIn("TAILSCALE_IPV4=100.64.0.9", self.state.read_text())

    def test_dns_and_konsol_are_restarted_only_when_silent(self):
        (self.fake / "dns").write_text("no")
        (self.fake / "http").write_text("000")
        _, steps, _ = self.run_repair()
        self.assertEqual(steps["dns"]["durum"], "onarildi")
        self.assertEqual(steps["konsol"]["durum"], "onarildi")
        self.assertEqual(self.restarts(), ["dnsmasq.service", "master-panel.service", "caddy.service"])

    def test_logged_out_tailscale_is_reported_not_forced(self):
        (self.fake / "ts.json").write_text(json.dumps({"BackendState": "NeedsLogin", "Self": {"Online": False}}))
        _, steps, _ = self.run_repair()
        self.assertEqual(steps["tailscale"]["durum"], "sorun")
        self.assertIn("sudo tailscale up", steps["tailscale"]["detay"])
        self.assertNotIn("tailscaled.service", self.restarts())

    def test_other_failed_units_are_listed_not_touched(self):
        (self.fake / "state" / "foo.service").write_text("failed")
        _, steps, _ = self.run_repair()
        self.assertEqual(steps["diger"]["durum"], "sorun")
        self.assertIn("foo.service", steps["diger"]["detay"])
        self.assertNotIn("foo.service", self.restarts())

    def test_a_broken_step_does_not_hide_the_others(self):
        with patch.object(mo.Repair, "dns", side_effect=RuntimeError("x")):
            _, steps, _ = self.run_repair()
        self.assertEqual(steps["dns"]["durum"], "hata")
        self.assertEqual(steps["konsol"]["durum"], "ok")


class CommandTests(Fixture):
    def cli(self, *args):
        if os.geteuid() != 0:
            self.skipTest("the command refuses non-root")
        return subprocess.run([sys.executable, str(ROOT / "panel" / "master_onar.py"), *args], capture_output=True, text=True,
                              env=dict(os.environ), timeout=60)

    def test_firewall_only_mode_keeps_the_last_report(self):
        self.report.write_text('{"durum":"tamam","adimlar":[]}')
        (self.fake / "fw_rc").write_text("1")
        proc = self.cli("--duvar")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Güvenlik duvarı", proc.stdout)
        self.assertEqual(self.restarts(), ["master-firewall.service"])
        self.assertEqual(self.report.read_text(), '{"durum":"tamam","adimlar":[]}')

    def test_terminal_output_has_one_line_per_step(self):
        proc = self.cli("--denetle")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = [l for l in proc.stdout.splitlines() if l[:1] in "✓↻!✗–"]
        self.assertEqual(len(lines), 7)
        self.assertTrue(proc.stdout.startswith("master-onar: yalnız denetim"))


class PanelTests(unittest.TestCase):
    """repair_start → systemd-run master-onar [--denetle] as its own unit; one at a time; not beside an update."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.bin = self.root / "sbin"
        self.bin.mkdir()
        self.active = self.bin / "active"
        self.active.write_text("")
        for name, body in {
            "systemd-run": 'printf "%s\\n" "$*" >> "$(dirname "$0")/calls"',
            "systemctl": 'for u in $(cat "$(dirname "$0")/active"); do case "$u" in $(eval echo \\${$#})) echo "$u loaded active running x";; esac; done',
            "master-modul": "exit 0"}.items():
            path = self.bin / name
            path.write_text("#!/bin/sh\n" + body + "\n")
            path.chmod(0o755)
        self.report = self.root / "onarim.json"
        self.state = self.root / "state.env"
        self.state.write_text("ONARIM_UNIT=master-onar.service\nONARIM_DURUM_FILE=%s\nGUNCELLEME_UNIT=master-guncelle.service\n" % self.report)
        self.p = panel.Panel(types.SimpleNamespace(state=str(self.state), allow_host=["panel.test"], state_env=True,
                                                   master_modul=str(self.bin / "master-modul")))

    def calls(self):
        path = self.bin / "calls"
        return path.read_text().splitlines() if path.exists() else []

    def test_starts_its_own_unit(self):
        self.assertEqual(self.p.repair_start("denetle"), "denetle")
        self.assertEqual(self.p.repair_start("onar"), "onar")
        tool = self.bin / "master-onar"
        self.assertEqual(self.calls(), [
            "--unit=master-onar.service --collect --quiet --description=Konsol: denetle --setenv=STATE_FILE=%s %s --denetle" % (self.state, tool),
            "--unit=master-onar.service --collect --quiet --description=Konsol: denetle ve onar --setenv=STATE_FILE=%s %s" % (self.state, tool)])

    def test_refusals(self):
        with self.assertRaises(mu.UpdateError) as err:
            self.p.repair_start("sil")
        self.assertEqual(err.exception.status, 400)
        for unit, word in (("master-onar.service", "zaten"), ("master-guncelle.service", "Güncelleme")):
            self.active.write_text(unit)
            with self.assertRaises(mu.UpdateError) as err:
                self.p.repair_start("onar")
            self.assertEqual(err.exception.status, 409)
            self.assertIn(word, str(err.exception))
        self.assertEqual(self.calls(), [])

    def test_info_reads_the_report_and_a_vanished_run(self):
        self.assertEqual(self.p.repair_info(), {"calisiyor": False, "rapor": None, "kurulu": True})
        self.report.write_text(json.dumps({"durum": "calisiyor", "kip": "onar", "baslangic": 1, "bitis": None, "adimlar": []}))
        self.active.write_text("master-onar.service")
        self.assertTrue(self.p.repair_info()["calisiyor"])
        self.active.write_text("")
        info = self.p.repair_info()
        self.assertEqual(info["rapor"]["durum"], "hata")
        self.assertTrue(info["rapor"]["yarida"])
        self.report.write_text("{bozuk")
        self.assertIsNone(self.p.repair_info()["rapor"])


class RouteTests(unittest.TestCase):
    def setUp(self):
        started = self.started = []

        class FakePanel:
            def repair_info(self):
                return {"calisiyor": False, "rapor": None, "kurulu": True}

            def repair_start(self, kip):
                started.append(kip)
                return kip

        class Handler(panel.Handler):
            def gate(self):
                return panel.ACTOR

            def channel(self):
                return self.headers.get("X-Test-Kanal", "tailscale")

        Handler.panel = FakePanel()
        _server, self.sock = test_resources.start_unix(self, Handler)

    def request(self, method, kanal, body=None):
        headers = {"X-Konsol": "1", "X-Test-Kanal": kanal}
        if body is not None:
            headers["Content-Type"] = "application/json"
        status, _h, raw = test_resources.unix_get(self.sock, "/api/konsol/onarim", headers, method, json.dumps(body) if body is not None else None)
        return status, json.loads(raw)

    def test_only_the_tailnet_starts_a_repair(self):
        self.assertTrue(self.request("GET", "tailscale")[1]["baslatilabilir"])
        self.assertFalse(self.request("GET", "internet")[1]["baslatilabilir"])
        status, body = self.request("POST", "internet", {"kip": "onar"})
        self.assertEqual(status, 403)
        self.assertEqual(self.started, [])
        self.assertEqual(self.request("POST", "tailscale", {"kip": "denetle"}), (202, {"kip": "denetle"}))
        self.assertEqual(self.started, ["denetle"])


if __name__ == "__main__":
    unittest.main()
