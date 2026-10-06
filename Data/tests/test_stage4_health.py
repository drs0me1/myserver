"""Stage 4: actual health decisions with local fixtures and bounded mocked probes."""
import contextlib
import json
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch

import test_resources as resources

panel = resources.panel


class HealthTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="stage4-health-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.modules = self.root / "modules"
        self.modules.write_text("")
        self.networks = self.root / "networks"
        self.env = {"MODULES_FILE": str(self.modules), "WG_NETWORKS_FILE": str(self.networks),
                    "DOWNLOADS_UID": "1000", "SERVER_ROOT": str(self.root)}
        self.state = self.root / "state.env"
        self.state.write_text("".join(k + "=" + v + "\n" for k, v in self.env.items()))
        self.p = panel.Panel(types.SimpleNamespace(state=str(self.state), state_env=False, master_modul="/fixture/master-modul"))
        self.props = {}
        # DD-198: the engine's saglik output is derived from the fixture registry files, like the real hooks.
        self.saglik_rc = 0
        self.failed = (0, "")
        self.show = None
        self.calls = []
        self.outputs = {"tailscale": (0, json.dumps({"BackendState": "Running", "Self": {"Online": True}})),
                        "master-firewall": (0, ""), "timedatectl": (0, "yes\n")}

    def saglik(self):
        if self.saglik_rc:
            return self.saglik_rc, ""
        lines = []
        registry = self.modules.read_text() if self.modules.exists() else ""
        if "torrent\tcalisiyor" in registry.splitlines():
            lines.append("torrent\tqbittorrent-nox@downloads.service\tgerekli")
        if "wireguard\tcalisiyor" in registry.splitlines() and self.networks.exists():
            for line in self.networks.read_text().splitlines():
                f = line.split("\t")
                if len(f) != 9 or f[2] != "inet":
                    return 1, "wireguard\thata\tbozuk\n"
                lines.append("wireguard\twg-quick@%s.service\tag" % f[0])
        return 0, "".join(l + "\n" for l in lines)

    def cmd(self, argv, timeout=10):
        self.calls.append((argv, timeout))
        if argv == ["/fixture/master-modul", "saglik"]:
            return self.saglik()
        if argv[:2] == ["systemctl", "list-units"]:
            return self.failed
        if argv[:2] == ["systemctl", "show"]:
            if self.show is not None:
                return self.show
            blocks = []
            for unit in argv[4:]:
                props = dict(Id=unit, LoadState="loaded", ActiveState="active", UnitFileState="enabled")
                props.update(self.props.get(unit, {}))
                blocks.append("\n".join(k + "=" + v for k, v in props.items()))
            return 0, "\n\n".join(blocks)
        return self.outputs[argv[0]]

    def units(self):
        with patch.object(self.p, "health_cmd", side_effect=self.cmd), \
                patch.object(panel.pwd, "getpwuid", return_value=types.SimpleNamespace(pw_name="downloads")):
            return self.p.health_units(self.env)

    def test_core_units_are_required_even_with_no_failed_units(self):
        expected = {"tailscaled.service", "dnsmasq.service", "caddy.service", "master-firewall.service",
                    "master-panel.service", "master-files-panel.service", "master-sistem-dosya.service", "master-paylasim.service",
                    "refresh-tailnet-config.timer", "master-share-network.timer"}
        self.assertEqual(self.units()[0], "ok")
        shown = set(self.calls[-1][0][4:])
        self.assertEqual(shown, expected)
        self.assertNotIn("master-settings-guard.timer", shown)
        for unit in expected:
            with self.subTest(unit=unit):
                self.props = {unit: {"ActiveState": "inactive"}}
                status, detail = self.units()
                self.assertEqual(status, "bad")
                self.assertIn(unit, detail)

    def test_missing_masked_or_transitioning_required_unit_is_not_healthy(self):
        for changes in ({"LoadState": "not-found"}, {"LoadState": "masked"},
                        {"ActiveState": "activating"}, {"ActiveState": "deactivating"}, {"ActiveState": "failed"}):
            with self.subTest(changes=changes):
                self.props = {"caddy.service": changes}
                self.assertEqual(self.units()[0], "bad")

    def test_failed_units_still_report_unrelated_failures(self):
        self.failed = (0, "example.service loaded failed failed example\n")
        status, detail = self.units()
        self.assertEqual(status, "bad")
        self.assertIn("example.service", detail)

    def test_nonzero_missing_malformed_and_timeout_probes_never_pass(self):
        for response in ((1, ""), (None, ""), (0, ""), (0, "Id=caddy.service\nActiveState=active\n")):
            with self.subTest(response=response):
                self.show = response
                self.assertEqual(self.units()[0], "warn")
        self.show = None
        for response in ((1, ""), (None, "")):
            self.failed = response
            self.assertEqual(self.units()[0], "warn")

    def test_optional_qbit_is_required_only_when_registered_running(self):
        unit = "qbittorrent-nox@downloads.service"
        self.props[unit] = {"ActiveState": "inactive"}
        for registry, expected in (("", "ok"), ("torrent\tdurduruldu\n", "ok"), ("torrent\tcalisiyor\n", "bad")):
            with self.subTest(registry=registry):
                self.modules.write_text(registry)
                self.assertEqual(self.units()[0], expected)
                self.assertEqual(unit in self.calls[-1][0], expected == "bad")
        self.props[unit]["ActiveState"] = "active"
        self.assertEqual(self.units()[0], "ok")
        # The engine failing to list package units is "unknown", never healthy.
        self.saglik_rc = 1
        self.assertEqual(self.units()[0], "warn")
        self.saglik_rc = 0

    def test_wg_enabled_networks_required_disabled_networks_stay_stopped(self):
        self.modules.write_text("wireguard\tcalisiyor\n")
        self.networks.write_text("wg0\t61001\tinet\t10.8.0.1\t10.8.0.0/24\tfd00::1\tfd00::/112\t1.1.1.1\tTest\n")
        unit = "wg-quick@wg0.service"
        for enabled, active, expected in (("enabled", "active", "ok"), ("enabled", "inactive", "bad"),
                                          ("enabled-runtime", "failed", "bad"), ("disabled", "inactive", "ok"),
                                          ("", "inactive", "warn"), ("masked", "inactive", "warn")):
            with self.subTest(enabled=enabled, active=active):
                self.props[unit] = dict(UnitFileState=enabled, ActiveState=active)
                self.assertEqual(self.units()[0], expected)
        self.props[unit] = dict(UnitFileState="disabled", ActiveState="failed")
        self.failed = (0, unit + " loaded failed failed WireGuard\n")
        self.assertEqual(self.units()[0], "bad")
        self.failed = (0, "")
        self.modules.write_text("")  # Removing the module leaves its network registry.
        self.assertEqual(self.units()[0], "ok")
        self.assertNotIn(unit, self.calls[-1][0])

    def test_empty_network_registry_is_valid_but_corruption_is_unknown(self):
        self.modules.write_text("wireguard\tcalisiyor\n")
        self.assertEqual(self.units()[0], "ok")  # No networks created yet.
        self.networks.write_text("")
        self.assertEqual(self.units()[0], "ok")
        self.networks.write_text("wg0\tbroken\n")
        self.assertEqual(self.units()[0], "warn")
        for content in ("torrent\tunknown\n", "torrent\tcalisiyor\ntorrent\tdurduruldu\n", "broken\n"):
            self.modules.write_text(content)
            self.assertEqual(self.units()[0], "warn")
        self.modules.unlink()
        self.assertEqual(self.units()[0], "warn")

    def compute(self, settings_error=None, shares_error=None, disk_error=False):
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(self.p, "health_cmd", side_effect=self.cmd))
            stack.enter_context(patch.object(self.p, "health_reboot", return_value=("ok", "same kernel")))
            manager = stack.enter_context(patch.object(panel.master_settings, "Manager"))
            manager.return_value.status.return_value = {"pending": None}
            manager.return_value.status.side_effect = settings_error
            shares = stack.enter_context(patch.object(panel.master_shares, "Manager"))
            shares.return_value.wan_info.return_value = {"available": True}
            shares.return_value.read.return_value = {"items": []}
            shares.return_value.read.side_effect = shares_error
            if disk_error:
                stack.enter_context(patch.object(panel.os, "statvfs", side_effect=OSError("unreadable")))
            data = self.p.health_compute()
            return data, {c["id"]: c for c in data["checks"]}

    def test_aggregate_unknowns_are_visible_and_firewall_failclosed_stays_red(self):
        self.assertEqual(self.compute()[0]["status"], "ok")
        for key, kwargs in (("settings", dict(settings_error=panel.master_settings.SettingsError("bad registry"))),
                            ("wan", dict(shares_error=panel.master_shares.ShareError("bad registry"))),
                            ("disk:/", dict(disk_error=True))):
            data, checks = self.compute(**kwargs)
            self.assertNotEqual(data["status"], "ok")
            self.assertEqual(checks[key]["status"], "warn")
            if key == "wan":
                self.assertIn("bad registry", checks[key]["detail"])
        self.outputs["master-firewall"] = (1, "degraded policy; invalid registry")
        data, checks = self.compute()
        self.assertEqual((data["status"], checks["firewall"]["status"]), ("bad", "bad"))
        self.assertIn((["master-firewall", "--check"], 30), self.calls)

    def test_corrupt_registry_cannot_hide_a_failed_core_firewall(self):
        self.modules.write_text("wireguard\tcorrupt\n")
        self.props["master-firewall.service"] = {"ActiveState": "failed"}
        self.outputs["master-firewall"] = (1, "degraded; invalid registry")
        data, checks = self.compute()
        self.assertEqual((data["status"], checks["units"]["status"], checks["firewall"]["status"]),
                         ("bad", "bad", "bad"))
        self.assertIn("master-firewall.service", checks["units"]["detail"])

    def test_missing_inode_and_clock_measurements_never_report_healthy(self):
        disk = types.SimpleNamespace(f_blocks=100000, f_frsize=4096, f_bavail=50000, f_files=0, f_favail=0)
        with patch.object(panel.os, "statvfs", return_value=disk):
            self.assertEqual(self.compute()[1]["disk:/"]["status"], "warn")
            disk.f_files = 10000
            self.assertEqual(self.compute()[1]["disk:/"]["status"], "bad")
        for response in ((None, ""), (1, "yes"), (0, ""), (0, "unexpected")):
            self.outputs["timedatectl"] = response
            self.assertEqual(self.compute()[1]["clock"]["status"], "warn")

    def test_bad_tailscale_shapes_and_expiry_are_never_healthy(self):
        for value in ([], {}, {"Self": []}, {"BackendState": "Running", "Self": {"Online": "true"}},
                      {"BackendState": "Running", "Self": {"Online": True, "KeyExpiry": "bad"}},
                      {"BackendState": "Running", "Self": {"Online": True, "KeyExpiry": 42}},
                      {"BackendState": "Running", "Self": {"Online": True, "KeyExpiry": False}},
                      {"BackendState": "Running", "Self": {"Online": True, "KeyExpiry": "2030-01-01"}}):
            with self.subTest(value=value):
                self.outputs["tailscale"] = (0, json.dumps(value))
                self.assertNotEqual(self.compute()[1]["tailscale"]["status"], "ok")
        self.outputs["tailscale"] = (0, "[" * 2000 + "0" + "]" * 2000)
        self.assertEqual(self.compute()[1]["tailscale"]["status"], "bad")

    def test_health_commands_keep_timeout_and_no_stdin(self):
        for error in (OSError("missing"), subprocess.TimeoutExpired("systemctl", 10)):
            with patch.object(panel.subprocess, "run", side_effect=error) as run:
                self.assertEqual(self.p.health_cmd(["systemctl", "show"]), (None, ""))
                self.assertEqual(run.call_args.kwargs["timeout"], 10)
                self.assertEqual(run.call_args.kwargs["stdin"], subprocess.DEVNULL)


class RebootTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="stage4-boot-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        (self.root / "boot").mkdir()
        (self.root / "run").mkdir()
        self.p = panel.Panel(types.SimpleNamespace())

    def image(self, release, complete=True):
        image = self.root / "boot" / ("vmlinuz-" + release)
        image.write_bytes(b"kernel fixture")
        if complete:
            (image.parent / ("initrd.img-" + release)).write_bytes(b"initramfs fixture")
            (self.root / "lib/modules" / release).mkdir(parents=True, exist_ok=True)
        return image

    def probe(self, running):
        with patch.object(panel.platform, "release", return_value=running):
            return self.p.health_reboot(self.root)

    def test_debian_root_link_not_package_or_lexical_order_decides(self):
        running = "6.12.9+deb13-amd64"
        self.image(running)
        self.image("6.12.100+deb13-cloud-amd64")
        self.image("6.12.999+deb13-amd64", complete=False)
        link = self.root / "vmlinuz"
        link.symlink_to("boot/vmlinuz-" + running)
        self.assertEqual(self.probe(running)[0], "ok")
        for selected in ("6.12.10+deb13-amd64", "6.12.8+deb13-amd64"):
            self.image(selected)
            link.unlink()
            link.symlink_to("boot/vmlinuz-" + selected)
            status, detail = self.probe(running)
            self.assertEqual(status, "warn")
            self.assertIn(selected, detail)
            self.assertIn("bekliyor", detail)

    def test_supported_ubuntu_boot_link_fallback(self):
        for release in ("6.8.0-101-generic", "7.0.0-12-generic"):
            with self.subTest(release=release):
                image = self.image(release)
                link = self.root / "boot/vmlinuz"
                link.unlink(missing_ok=True)
                link.symlink_to(image.name)
                self.assertEqual(self.probe(release)[0], "ok")
                self.assertIn(release, self.probe("6.8.0-99-generic")[1])

    def test_root_link_takes_precedence_and_broken_link_cannot_fall_back(self):
        running = "6.8.0-9-generic"
        (self.root / "boot/vmlinuz").symlink_to(self.image(running).name)
        root_link = self.root / "vmlinuz"
        root_link.symlink_to("boot/vmlinuz-6.8.0-10-generic")
        self.assertIn("bilinmiyor", self.probe(running)[1])
        self.image("6.8.0-10-generic")
        self.assertIn("bekliyor", self.probe(running)[1])

    def test_missing_broken_wrong_flavor_and_unbootable_targets_are_unknown(self):
        running = "6.12.9+deb13-amd64"
        self.assertEqual(self.probe(running)[0], "warn")
        link = self.root / "vmlinuz"
        for release, complete in (("6.12.10+deb13-amd64", False), ("6.12.10+deb13-cloud-amd64", True)):
            image = self.image(release, complete)
            link.unlink(missing_ok=True)
            link.symlink_to(image)
            self.assertIn("bilinmiyor", self.probe(running)[1])
        image = self.image("6.12.11+deb13-amd64")
        link.unlink()
        link.symlink_to(image)
        (image.parent / "initrd.img-6.12.11+deb13-amd64").write_bytes(b"")
        self.assertIn("bilinmiyor", self.probe(running)[1])

    def test_production_sandbox_hidden_modules_do_not_hide_kernel_change(self):
        running = "6.12.107+deb13-amd64"
        selected = "6.12.111+deb13-amd64"
        image = self.image(selected)
        (self.root / "vmlinuz").symlink_to("boot/" + image.name)
        modules = self.root / "lib/modules"
        self.assertTrue((modules / selected).is_dir())  # Present on the host.
        real_stat = Path.stat

        def sandbox_stat(path, *args, **kwargs):
            if path == modules or modules in path.parents:
                # ProtectKernelModules masks /usr/lib/modules on merged-/usr
                # Debian: stat through /lib/modules raises ENOENT in the unit.
                raise FileNotFoundError(str(path))
            return real_stat(path, *args, **kwargs)

        with patch.object(Path, "stat", new=sandbox_stat), \
                patch.object(panel.subprocess, "run", side_effect=AssertionError("no privileged probe")):
            with self.assertRaises(FileNotFoundError):
                (modules / selected).stat()
            status, detail = self.probe(running)
            self.assertEqual(status, "warn")
            self.assertIn(running, detail)
            self.assertIn(selected, detail)
            self.assertIn("bekliyor", detail)
            self.assertNotIn("bilinmiyor", detail)
            # The same sandbox must also work after the manual reboot.
            self.assertEqual(self.probe(selected)[0], "ok")

    def test_empty_image_and_unreadable_probe_are_unknown(self):
        running = "6.8.0-10-generic"
        image = self.image(running)
        (self.root / "vmlinuz").symlink_to(image)
        image.write_bytes(b"")
        self.assertIn("bilinmiyor", self.probe(running)[1])
        with patch.object(panel.Path, "stat", side_effect=PermissionError("boot")):
            self.assertEqual(self.probe(running)[0], "warn")

    def test_marker_has_priority_even_without_kernel_evidence(self):
        (self.root / "run/reboot-required").touch()
        (self.root / "run/reboot-required.pkgs").write_text("linux-image-fixture\nlibc6\n")
        status, detail = self.probe("unknown")
        self.assertEqual(status, "warn")
        self.assertIn("Güncellemeler", detail)
        self.assertIn("libc6", detail)


if __name__ == "__main__":
    unittest.main()
