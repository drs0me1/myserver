"""DD-239/DD-241: master-onar (check and repair) with fake systemctl/tailscale/ip/sysctl/curl/dpkg/… on PATH:
check-only changes nothing, repair touches exactly what is broken and only with the installer's own settings,
report-only steps never repair, a stopped package and a disabled network are left alone, the report file
follows every step, --duvar touches only the firewall, and the panel's start, report and log routes.
Temporary directories only."""
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
GiB = 1024 ** 3

FAKES = {
    # state/<unit> holds the ActiveState (default active); fail/<unit> makes a restart fail;
    # enabled/<unit> holds the UnitFileState (default enabled); missing/<unit> makes it not-found.
    "systemctl": r'''
F="$FAKE"; echo "systemctl $*" >> "$F/calls"
case "$1" in
  show) shift; for a in "$@"; do case "$a" in --*) ;; *)
        st=active; [ -f "$F/state/$a" ] && st=$(cat "$F/state/$a")
        en=enabled; [ -f "$F/enabled/$a" ] && en=$(cat "$F/enabled/$a")
        ld=loaded; [ -f "$F/missing/$a" ] && ld=not-found
        printf 'Id=%s\nLoadState=%s\nActiveState=%s\nUnitFileState=%s\n\n' "$a" "$ld" "$st" "$en";; esac; done ;;
  restart) [ -f "$F/fail/$2" ] && exit 1; echo active > "$F/state/$2"
        case "$2" in
          master-firewall.service) echo 0 > "$F/fw_rc" ;;
          dnsmasq.service) echo ok > "$F/dns" ;;
          master-panel.service) echo 200 > "$F/backend" ;;
          caddy.service) echo 403 > "$F/http" ;;
          master-files-panel.service) echo 200 > "$F/files" ;;
          systemd-timesyncd.service) echo yes > "$F/ntp" ;;
        esac; exit 0 ;;
  enable) shift; [ "$1" = --now ] && shift; [ -f "$F/fail/$1" ] && exit 1
        echo active > "$F/state/$1"; echo enabled > "$F/enabled/$1"; exit 0 ;;
  reset-failed) exit 0 ;;
  list-units) for f in "$F"/state/*; do [ -f "$f" ] && [ "$(cat "$f")" = failed ] && echo "$(basename "$f") loaded failed failed x"; done; exit 0 ;;
esac''',
    "master-firewall": r'''echo "master-firewall $*" >> "$FAKE/calls"; exit "$(cat "$FAKE/fw_rc" 2>/dev/null || echo 0)"''',
    "tailscale": r'''echo "tailscale $*" >> "$FAKE/calls"
case "$1" in
  status) cat "$FAKE/ts.json" ;;
  debug) cat "$FAKE/prefs.json" ;;
  set) echo '{"AdvertiseRoutes":["0.0.0.0/0","::/0"],"RunSSH":true}' > "$FAKE/prefs.json" ;;
esac; exit 0''',
    "ip": r'''case "$*" in *tailscale0*) a=$(cat "$FAKE/ip");; *) a=$(cat "$FAKE/wanip");; esac
echo "3: dev    inet $a/32 scope global dev"''',
    "sysctl": r'''echo "sysctl $*" >> "$FAKE/calls"
case "$*" in
  "-n net.ipv4.ip_forward") cat "$FAKE/fwd" ;;
  "-n net.core.rmem_max") echo 33554432 ;;
  -p*) [ -f "$FAKE/sysctl_stuck" ] || echo 1 > "$FAKE/fwd" ;;
esac''',
    "timedatectl": r'''cat "$FAKE/ntp"''',
    "dig": r'''[ "$(cat "$FAKE/dns" 2>/dev/null)" = ok ] && echo 100.64.0.2; exit 0''',
    "curl": r'''case "$*" in
  *--unix-socket*) printf '%s' "$(cat "$FAKE/backend")" ;;
  */api/state*) printf '%s' "$(cat "$FAKE/files")" ;;
  *) printf '%s' "$(cat "$FAKE/http")" ;;
esac''',
    "dpkg": r'''echo "dpkg $*" >> "$FAKE/calls"
case "$1" in
  --audit) cat "$FAKE/audit" 2>/dev/null ;;
  --configure) if [ -f "$FAKE/dpkg_locked" ]; then echo "dpkg: error: dpkg frontend lock is locked" >&2; exit 2; fi; : > "$FAKE/audit" ;;
esac''',
    "apt-get": r'''echo "apt-get $*" >> "$FAKE/calls"; touch "$FAKE/cleaned"''',
    "journalctl": r'''echo "journalctl $*" >> "$FAKE/calls"; case "$*" in *-k*) cat "$FAKE/oom" 2>/dev/null ;; esac; exit 0''',
    "caddy": r'''[ -f "$FAKE/caddy_bad" ] && { echo "Error: adapting config: unrecognized directive: bozuk" >&2; exit 1; }; exit 0''',
    "podman": r'''echo 5.4.2''',
    "nft": r'''[ -f "$FAKE/nft_missing" ] && exit 1; exit 0''',
    "wg": r'''printf 'wg0\tpeerA=\t1790000000\nwg0\tpeerB=\t0\n' ''',
    "master-modul": r'''echo "master-modul $*" >> "$FAKE/calls"; cat "$FAKE/saglik" 2>/dev/null; exit 0''',
    "refresh-tailnet-config": r'''echo "refresh $*" >> "$FAKE/calls"; sed -i "s/^TAILSCALE_IPV4=.*/TAILSCALE_IPV4=$(cat "$FAKE/ip")/" "$STATE_FILE"''',
}
DEFAULTS = {"ts.json": json.dumps({"BackendState": "Running", "Self": {"Online": True}}),
            "prefs.json": json.dumps({"AdvertiseRoutes": ["0.0.0.0/0", "::/0"], "RunSSH": True}),
            "ip": "100.64.0.2", "wanip": "192.0.2.1", "dns": "ok", "http": "403", "backend": "200", "files": "200",
            "fwd": "1", "ntp": "yes"}
OK = {"duvar": "ok", "yonlendirme": "ok", "tailscale": "ok", "adres": "ok", "wan": "ok", "zamanlayicilar": "ok",
      "servisler": "ok", "ssh": "ok", "saat": "ok", "dns": "ok", "konsol": "ok", "dosyalar": "ok", "izinler": "ok",
      "disk": "ok", "paketler": "ok", "caddy": "ok", "podman": "ok", "wireguard": "atlandi", "sistem": "ok",
      "yarim": "ok", "diger": "ok"}


def big_disk(path):
    return os.statvfs_result((4096, 4096, 10 ** 8, 10 ** 7, 10 ** 7, 10 ** 6, 10 ** 5, 10 ** 5, 0, 255))


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
        for name, value in DEFAULTS.items():
            (self.fake / name).write_text(value)
        for unit in ("master-sistem-dosya.service", "chrony.service"):
            (self.fake / "missing" / unit).write_text("")
        self.modules = self.root / "moduller"
        self.modules.write_text("torrent\tcalisiyor\nwireguard\tdurduruldu\n")
        (self.fake / "saglik").write_text("torrent\tqbittorrent.service\tgerekli\nwireguard\twg-quick@wg0.service\tag\n")
        self.state, self.report, self.caddyfile = self.root / "state.env", self.root / "onarim.json", self.root / "Caddyfile"
        self.caddyfile.write_text("{\n}\n")
        self.auth = self.root / "konsol"
        self.auth.mkdir(mode=0o700)
        self.state.write_text(
            "TAILSCALE_IPV4=100.64.0.2\nTAILSCALE_IF=tailscale0\nLOCAL_DOMAIN=ev\nSBIN_DIR=%s\nMODULES_FILE=%s\nRUNTIME_DIR=%s\n"
            "ONARIM_DURUM_FILE=%s\nWAN_INTERFACE=eth0\nWAN_IPV4=192.0.2.1\nPANEL_SOCKET=/run/x.sock\nFILES_PANEL_PORT=61009\n"
            "CADDYFILE=%s\nKONTEYNER_NFT_TABLE=master_containers\nKONSOL_AUTH_DIR=%s\nNET_BUF_FLOOR_BYTES=16777216\n"
            "SYSCTL_FORWARD_FILE=%s\nSERVER_ROOT=%s\n" % (self.bin, self.modules, self.root / "run", self.report, self.caddyfile,
                                                         self.auth, self.caddyfile, self.root))
        self.state.chmod(0o600)
        env = {"PATH": "%s:%s" % (self.bin, os.environ["PATH"]), "FAKE": str(self.fake), "STATE_FILE": str(self.state)}
        for p in (patch.dict(os.environ, env), patch.object(mo, "STATE_FILE", str(self.state)),
                  patch.object(mo.time, "sleep", lambda s: None), patch.object(mo, "journal", self.journaled),
                  patch.object(mo.os, "statvfs", big_disk), patch.object(mo.os.path, "exists", self.exists)):
            p.start()
        self.addCleanup(patch.stopall)
        self.lines = []

    def journaled(self, line):
        self.lines.append(line)

    real_exists = staticmethod(os.path.exists)

    def exists(self, path):
        return False if path == "/run/reboot-required" else Fixture.real_exists(path)

    def calls(self):
        path = self.fake / "calls"
        return path.read_text().splitlines() if path.exists() else []

    def restarts(self):
        return [c.split()[-1] for c in self.calls() if c.startswith("systemctl restart")]

    def changes(self):
        """Every call that changes the host in the fakes."""
        verbs = ("systemctl restart", "systemctl enable", "sysctl -p", "tailscale set", "apt-get", "dpkg --configure",
                 "journalctl --vacuum", "refresh")
        return [c for c in self.calls() if c.startswith(verbs)]

    def run_repair(self, fix=True):
        r = mo.Repair(mo.read_env(str(self.state)), fix, str(self.report))
        code = r.all()
        report = json.loads(self.report.read_text())
        return code, {s["id"]: s for s in report["adimlar"]}, report


class RepairTests(Fixture):
    def test_healthy_host_is_left_alone(self):
        code, steps, report = self.run_repair()
        self.assertEqual({s: v["durum"] for s, v in steps.items()}, OK)
        self.assertEqual(code, 0)
        self.assertEqual(report["durum"], "tamam")
        self.assertEqual(self.changes(), [])
        self.assertEqual(self.lines[0], "denetim ve onarım başladı (terminal)")
        self.assertTrue(self.lines[-1].startswith("bitti: tamam"))
        self.assertEqual(len(self.lines), len(OK) + 2)

    def test_check_only_reports_and_changes_nothing(self):
        (self.fake / "fw_rc").write_text("1")
        (self.fake / "fwd").write_text("0")
        (self.fake / "prefs.json").write_text(json.dumps({"AdvertiseRoutes": [], "RunSSH": False}))
        (self.fake / "ip").write_text("100.64.0.9")
        (self.fake / "ntp").write_text("no")
        (self.fake / "backend").write_text("000")
        (self.fake / "files").write_text("000")
        (self.fake / "audit").write_text("The following packages are only half configured")
        for unit in ("caddy.service", "ssh.service", "ssh.socket"):
            (self.fake / "state" / unit).write_text("failed")
        (self.fake / "enabled" / "master-share-network.timer").write_text("disabled")
        self.state.chmod(0o644)
        with patch.object(mo.os, "statvfs", lambda p: os.statvfs_result((4096, 4096, 10 ** 6, 100, 100, 10 ** 6, 10 ** 5, 10 ** 5, 0, 255))):
            code, steps, report = self.run_repair(fix=False)
        self.assertEqual(code, 1)
        self.assertEqual(report["kip"], "denetle")
        for sid in ("duvar", "yonlendirme", "tailscale", "adres", "zamanlayicilar", "servisler", "ssh", "saat", "konsol",
                    "dosyalar", "izinler", "disk", "paketler"):
            self.assertEqual(steps[sid]["durum"], "sorun", sid)
        self.assertEqual(self.changes(), [])
        self.assertEqual(oct(self.state.stat().st_mode & 0o777), "0o644")

    def test_repair_restarts_exactly_the_broken_units(self):
        (self.fake / "fw_rc").write_text("1")
        for unit in ("caddy.service", "qbittorrent.service", "tailscale-udp-gro.service"):
            (self.fake / "state" / unit).write_text("failed")
        (self.fake / "state" / "wg-quick@wg0.service").write_text("inactive")  # a stopped package
        code, steps, _ = self.run_repair()
        self.assertEqual(code, 0)
        self.assertEqual(steps["duvar"]["durum"], "onarildi")
        self.assertEqual(steps["servisler"]["durum"], "onarildi")
        self.assertEqual(sorted(self.restarts()), ["caddy.service", "master-firewall.service", "qbittorrent.service", "tailscale-udp-gro.service"])

    def test_a_disabled_network_of_a_running_package_is_left_alone(self):
        self.modules.write_text("wireguard\tcalisiyor\n")
        (self.fake / "state" / "wg-quick@wg0.service").write_text("inactive")
        (self.fake / "enabled" / "wg-quick@wg0.service").write_text("disabled")
        _, steps, _ = self.run_repair()
        self.assertEqual(steps["servisler"]["durum"], "ok")
        self.assertEqual(steps["wireguard"]["detay"], "2 eş, 1 tanesi hiç bağlanmadı")

    def test_a_unit_that_will_not_start_is_an_error(self):
        (self.fake / "state" / "master-paylasim.service").write_text("failed")
        (self.fake / "fail" / "master-paylasim.service").write_text("")
        code, steps, report = self.run_repair()
        self.assertEqual(code, 1)
        self.assertEqual(report["durum"], "hata")
        self.assertIn("master-paylasim.service", steps["servisler"]["detay"])

    def test_forwarding_reapplies_the_installers_sysctl_files(self):
        (self.fake / "fwd").write_text("0")
        _, steps, _ = self.run_repair()
        self.assertEqual(steps["yonlendirme"]["durum"], "onarildi")
        self.assertIn("sysctl -p %s" % self.caddyfile, self.calls())
        (self.fake / "fwd").write_text("0")
        (self.fake / "sysctl_stuck").write_text("")
        _, steps, _ = self.run_repair()
        self.assertEqual(steps["yonlendirme"]["durum"], "hata")

    def test_tailscale_flags_come_back(self):
        (self.fake / "prefs.json").write_text(json.dumps({"AdvertiseRoutes": [], "RunSSH": True}))
        _, steps, _ = self.run_repair()
        self.assertEqual(steps["tailscale"]["durum"], "onarildi")
        self.assertIn("tailscale set --advertise-exit-node --ssh=true", self.calls())

    def test_logged_out_tailscale_is_reported_not_forced(self):
        (self.fake / "ts.json").write_text(json.dumps({"BackendState": "NeedsLogin", "Self": {"Online": False}}))
        _, steps, _ = self.run_repair()
        self.assertEqual(steps["tailscale"]["durum"], "sorun")
        self.assertIn("sudo tailscale up", steps["tailscale"]["detay"])
        self.assertFalse(any(c.startswith(("tailscale set", "tailscale up")) for c in self.calls()))

    def test_address_change_hands_over_to_refresh_tailnet_config(self):
        (self.fake / "ip").write_text("100.64.0.9")
        _, steps, _ = self.run_repair()
        self.assertEqual(steps["adres"]["durum"], "onarildi")
        self.assertIn("TAILSCALE_IPV4=100.64.0.9", self.state.read_text())

    def test_wan_change_is_reported_only(self):
        (self.fake / "wanip").write_text("198.51.100.7")
        _, steps, _ = self.run_repair()
        self.assertEqual(steps["wan"]["durum"], "sorun")
        self.assertIn("Kayıtlı 192.0.2.1, şimdiki 198.51.100.7", steps["wan"]["detay"])

    def test_timers_ssh_and_clock(self):
        (self.fake / "enabled" / "master-share-network.timer").write_text("disabled")
        (self.fake / "state" / "ssh.service").write_text("inactive")
        (self.fake / "state" / "ssh.socket").write_text("inactive")
        (self.fake / "enabled" / "ssh.socket").write_text("disabled")
        (self.fake / "ntp").write_text("no")
        _, steps, _ = self.run_repair()
        self.assertEqual(steps["zamanlayicilar"]["durum"], "onarildi")
        self.assertIn("systemctl enable --now master-share-network.timer", self.calls())
        self.assertEqual(steps["ssh"]["durum"], "onarildi")
        self.assertIn("ssh.service", self.restarts())
        self.assertEqual(steps["saat"]["durum"], "onarildi")
        self.assertIn("systemd-timesyncd.service", self.restarts())

    def test_idle_settings_guard_timer_is_not_a_fault(self):
        # DD-246: the rollback timer is stopped while no settings change is pending (DD-181).
        (self.fake / "state" / "master-settings-guard.timer").write_text("inactive")
        _, steps, _ = self.run_repair(fix=False)
        self.assertEqual(steps["zamanlayicilar"]["durum"], "ok")
        (self.fake / "enabled" / "master-settings-guard.timer").write_text("disabled")
        _, steps, _ = self.run_repair()
        self.assertEqual(steps["zamanlayicilar"]["durum"], "onarildi")
        self.assertIn("systemctl enable master-settings-guard.timer", self.calls())
        self.assertNotIn("systemctl enable --now master-settings-guard.timer", self.calls())

    def test_konsol_restarts_only_the_broken_side(self):
        (self.fake / "http").write_text("000")  # Caddy path down, backend fine
        _, steps, _ = self.run_repair()
        self.assertEqual(steps["konsol"]["durum"], "onarildi")
        self.assertEqual(self.restarts(), ["caddy.service"])

    def test_files_backend_and_dns(self):
        (self.fake / "files").write_text("000")
        (self.fake / "dns").write_text("no")
        _, steps, _ = self.run_repair()
        self.assertEqual(steps["dosyalar"]["durum"], "onarildi")
        self.assertEqual(steps["dns"]["durum"], "onarildi")
        self.assertEqual(sorted(self.restarts()), ["dnsmasq.service", "master-files-panel.service"])

    def test_wide_record_modes_are_narrowed(self):
        self.state.chmod(0o644)
        self.auth.chmod(0o755)
        _, steps, _ = self.run_repair()
        self.assertEqual(steps["izinler"]["durum"], "onarildi")
        self.assertEqual(oct(self.state.stat().st_mode & 0o777), "0o600")
        self.assertEqual(oct(self.auth.stat().st_mode & 0o777), "0o700")

    def test_low_disk_cleans_apt_and_the_journal_only(self):
        def disk(path):
            free = 100 * 10 ** 6 if (self.fake / "cleaned").exists() else 10 ** 3
            return os.statvfs_result((4096, 4096, 10 ** 6, free, free, 10 ** 6, 10 ** 5, 10 ** 5, 0, 255))
        with patch.object(mo.os, "statvfs", disk):
            _, steps, _ = self.run_repair()
        self.assertEqual(steps["disk"]["durum"], "onarildi")
        self.assertIn("apt-get clean", self.calls())
        self.assertIn("journalctl --vacuum-size=200M", self.calls())
        with patch.object(mo.os, "statvfs", lambda p: os.statvfs_result((4096, 4096, 10 ** 6, 10, 10, 10 ** 6, 10 ** 5, 10 ** 5, 0, 255))):
            _, steps, _ = self.run_repair()
        self.assertEqual(steps["disk"]["durum"], "sorun", "still low after cleaning is reported, nothing else is deleted")

    def test_half_configured_packages(self):
        (self.fake / "audit").write_text("The following packages are only half configured")
        _, steps, _ = self.run_repair()
        self.assertEqual(steps["paketler"]["durum"], "onarildi")
        self.assertIn("dpkg --configure -a", self.calls())
        (self.fake / "audit").write_text("half configured")
        (self.fake / "dpkg_locked").write_text("")
        _, steps, _ = self.run_repair()
        self.assertEqual(steps["paketler"]["durum"], "sorun")
        self.assertIn("meşgul", steps["paketler"]["detay"])

    def test_report_only_steps(self):
        (self.fake / "caddy_bad").write_text("")
        (self.fake / "nft_missing").write_text("")
        (self.fake / "oom").write_text("Out of memory: Killed process 42\n")
        update = self.root / "guncelleme.durum"
        update.write_text("durum=calisiyor\nhedef=2026.08.06-v2-300\n")
        with self.state.open("a") as fh:
            fh.write("GUNCELLEME_DURUM_FILE=%s\nGUNCELLEME_UNIT=master-guncelle.service\n" % update)
        (self.fake / "state" / "master-guncelle.service").write_text("inactive")
        code, steps, _ = self.run_repair()
        self.assertEqual(steps["caddy"]["durum"], "sorun")
        self.assertIn("unrecognized directive", steps["caddy"]["detay"])
        self.assertEqual(steps["podman"]["durum"], "sorun")
        self.assertEqual(steps["sistem"]["durum"], "sorun")
        self.assertIn("OOM", steps["sistem"]["detay"])
        self.assertEqual(steps["yarim"]["durum"], "sorun")
        self.assertIn("v2-300", steps["yarim"]["detay"])
        self.assertEqual(code, 0, "report-only findings are not repair errors")
        self.assertEqual(self.changes(), [])

    def test_other_failed_units_are_listed_not_touched(self):
        (self.fake / "state" / "foo.service").write_text("failed")
        _, steps, _ = self.run_repair()
        self.assertEqual(steps["diger"]["durum"], "sorun")
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
                              env=dict(os.environ), timeout=120)

    def test_firewall_only_mode_keeps_the_last_report(self):
        self.report.write_text('{"durum":"tamam","adimlar":[]}')
        (self.fake / "fw_rc").write_text("1")
        proc = self.cli("--duvar")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.restarts(), ["master-firewall.service"])
        self.assertEqual(self.report.read_text(), '{"durum":"tamam","adimlar":[]}')

    def test_terminal_output_has_one_line_per_step(self):
        proc = self.cli("--denetle")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        lines = [l for l in proc.stdout.splitlines() if l[:1] in "✓↻!✗–"]
        self.assertEqual(len(lines), len(OK))
        self.assertTrue(proc.stdout.startswith("master-onar: yalnız denetim"))
        self.assertEqual(json.loads(self.report.read_text())["kaynak"], "terminal")

    def test_konsol_runs_print_nothing(self):
        proc = self.cli("--denetle", "--kaynak", "konsol")
        self.assertEqual([l for l in proc.stdout.splitlines() if l[:1] in "✓↻!✗–"], [])
        self.assertEqual(json.loads(self.report.read_text())["kaynak"], "konsol")


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
            "journalctl": 'printf "%s\\n" "$*" >> "$(dirname "$0")/calls"; echo "2026-10-07T03:12:00+0000 nrm master-onar[1]: ✓ Güvenlik duvarı: Kurallar beklenen biçimde"',
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
            "--unit=master-onar.service --collect --quiet --description=Konsol: denetle --setenv=STATE_FILE=%s %s --kaynak konsol --denetle" % (self.state, tool),
            "--unit=master-onar.service --collect --quiet --description=Konsol: denetle ve onar --setenv=STATE_FILE=%s %s --kaynak konsol" % (self.state, tool)])

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

    def test_reboot_is_a_delayed_transient_unit(self):
        # DD-246: the answer reaches the page first; systemctl reboot runs a few seconds later.
        self.assertEqual(self.p.reboot_start(), panel.REBOOT_DELAY_SECONDS)
        self.assertEqual(self.calls(), ["--unit=master-yeniden-baslat --collect --quiet --on-active=%d --description=Konsol: yeniden başlat systemctl reboot"
                                        % panel.REBOOT_DELAY_SECONDS])

    def test_reboot_refused_beside_an_update_a_repair_or_a_package_operation(self):
        for unit, word in (("master-guncelle.service", "Güncelleme"), ("master-onar.service", "Onarım"), ("master-modul-torrent.service", "uygulama")):
            self.active.write_text(unit)
            with self.assertRaises(mu.UpdateError) as err:
                self.p.reboot_start()
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

    def test_log_reads_both_tags_for_the_chosen_span(self):
        self.assertIn("Güvenlik duvarı", self.p.repair_log("72s"))
        self.p.repair_log("7g")
        self.assertEqual(self.calls(), [
            "--since -72h -t master-onar -t refresh-tailnet-config -o short-iso --no-pager -q -n 3000",
            "--since -7d -t master-onar -t refresh-tailnet-config -o short-iso --no-pager -q -n 3000"])
        with self.assertRaises(mu.UpdateError) as err:
            self.p.repair_log("1y; rm -rf /")
        self.assertEqual(err.exception.status, 400)


class RouteTests(unittest.TestCase):
    def setUp(self):
        started = self.started = []

        class FakePanel:
            def repair_info(self):
                return {"calisiyor": False, "rapor": None, "kurulu": True}

            def repair_start(self, kip):
                started.append(kip)
                return kip

            def repair_log(self, span):
                if span not in ("72s", "7g"):
                    raise mu.UpdateError(400, "süre 72s ya da 7g olmalı")
                return "satır " + span

        class Handler(panel.Handler):
            def gate(self):
                return panel.ACTOR

            def channel(self):
                return self.headers.get("X-Test-Kanal", "tailscale")

        Handler.panel = FakePanel()
        _server, self.sock = test_resources.start_unix(self, Handler)

    def request(self, method, kanal, body=None, path="/api/konsol/onarim"):
        headers = {"X-Konsol": "1", "X-Test-Kanal": kanal}
        if body is not None:
            headers["Content-Type"] = "application/json"
        status, hdrs, raw = test_resources.unix_get(self.sock, path, headers, method, json.dumps(body) if body is not None else None)
        return status, (json.loads(raw) if hdrs.get("Content-Type", "").startswith("application/json") else raw.decode())

    def test_only_the_tailnet_starts_a_repair(self):
        self.assertTrue(self.request("GET", "tailscale")[1]["baslatilabilir"])
        self.assertFalse(self.request("GET", "internet")[1]["baslatilabilir"])
        status, body = self.request("POST", "internet", {"kip": "onar"})
        self.assertEqual(status, 403)
        self.assertEqual(self.started, [])
        self.assertEqual(self.request("POST", "tailscale", {"kip": "denetle"}), (202, {"kip": "denetle"}))
        self.assertEqual(self.started, ["denetle"])

    def test_log_route(self):
        self.assertEqual(self.request("GET", "tailscale", path="/api/konsol/onarim/gunluk?sure=7g"), (200, "satır 7g"))
        self.assertEqual(self.request("GET", "tailscale", path="/api/konsol/onarim/gunluk?sure=bozuk")[0], 400)


if __name__ == "__main__":
    unittest.main()
