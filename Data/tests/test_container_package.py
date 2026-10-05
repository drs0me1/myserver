"""Package adapter transactions and one locked App Store restart; no real services."""
import json
import contextlib
import io
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from test_torrent_api import Scratch, ayar, settings, REPO


class PackageConfigTests(Scratch):
    def setUp(self):
        super().setUp()
        self.env["PACKAGE_OVERRIDES_DIR"] = str(self.root / "overrides")
        self.state.write_text("".join(k + "=" + v + "\n" for k, v in self.env.items()))
        with (self.pkg / "paket.env").open("a") as stream:
            stream.write('\nPAKET_AYAR_ANAHTARLAR="TORRENT_UI_PORT TORRENT_PEER_PORT"\n')
        self.override = self.root / "overrides/torrent.env"
        self.caddy = self.root / "caddy-modules/torrent.caddy"
        self.caddy.parent.mkdir()
        self.caddy.write_text("http://torrent.test {\n reverse_proxy 127.0.0.1:61006\n}\n")

    def view(self):
        self.assertTrue(callable(getattr(ayar, "container_config", None)), "package adapter is missing")
        return ayar.container_config(self.env)

    def apply(self, port=61997, save=None, revision=None):
        request = {"revision": revision or self.view()["revision"],
                   "config": {"listener_port": port, "save": save or self.env["DOWNLOADS_PATH"]}}
        return ayar.konteyner_ayar(ayar.package_env(self.env), request, str(self.state))

    def test_effective_override_survives_regenerated_package_defaults(self):
        self.override.parent.mkdir()
        self.override.write_text("TORRENT_UI_PORT=61997\n")
        self.override.chmod(0o600)
        self.assertEqual(settings.package_env(self.env, "torrent")["TORRENT_UI_PORT"], "61997")
        (self.pkg / "torrent.env").write_text((self.pkg / "torrent.env").read_text().replace("61006", "61007"))
        self.assertEqual(settings.package_env(self.env, "torrent")["TORRENT_UI_PORT"], "61997")

    def test_unallowlisted_or_public_override_is_refused(self):
        self.override.parent.mkdir()
        for content, mode in (("TORRENT_PROFILE_DIR=/tmp/wrong\n", 0o600),
                              ("TORRENT_UI_PORT=61997\n", 0o644),
                              ("TORRENT_UI_PORT=$(id)\n", 0o600)):
            self.override.write_text(content)
            self.override.chmod(mode)
            with self.subTest(content=content, mode=mode), self.assertRaises(settings.SettingsError):
                settings.package_env(self.env, "torrent")

    def test_config_is_safe_and_revision_changes_with_native_save(self):
        first = self.view()
        self.assertEqual(first["config"], {"listener_port": 61006, "peer_port": 61008, "save": self.env["DOWNLOADS_PATH"] + "/"})
        self.assertEqual(set(first["editable"]), {"listener_port", "peer_port", "save"})
        self.assertEqual(first["protected_mounts"][0]["target"], "/config")
        self.assertNotIn("oldhash", json.dumps(first))
        self.assertNotIn("password", json.dumps(first).lower())
        self.conf.write_text(self.conf.read_text().replace("Unrelated=keep", "Unrelated=changed"))
        self.assertNotEqual(first["revision"], self.view()["revision"])

    def test_stale_request_is_refused_before_stop_or_config_writes(self):
        revision = self.view()["revision"]
        self.conf.write_text(self.conf.read_text() + "New=changed\n")
        before = self.conf.read_bytes()
        with self.assertRaisesRegex(settings.SettingsError, "değiş") as raised:
            self.apply(revision=revision)
        self.assertEqual(raised.exception.status, 409)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.conf.read_bytes(), before)
        self.assertFalse(self.override.exists())

    def test_stopped_edit_changes_every_port_consumer_without_start(self):
        self.active = False
        media = str(self.root / "srv/media/movies")
        result = self.apply(save=media)
        self.assertTrue(result["ok"])
        self.assertNotIn("start", self.systemctl())
        self.assertIn("WebUI\\Port=61997", self.conf.read_text())
        self.assertIn('Session\\DefaultSavePath="' + media + '/"', self.conf.read_text())
        self.assertIn("oldhash", self.conf.read_text())
        self.assertEqual(settings.package_env(self.env, "torrent")["TORRENT_UI_PORT"], "61997")
        self.assertEqual(self.override.stat().st_mode & 0o777, 0o600)
        self.assertIn("Environment=WEBUI_PORT=61997", (self.drop.parent / "85-konteyner.conf").read_text())
        self.assertIn("Volume=" + media + ":" + media, self.drop.read_text())
        self.assertIn("reverse_proxy 127.0.0.1:61997", self.caddy.read_text())
        self.assertEqual(self.view()["config"]["listener_port"], 61997)
        # DD-217: the loopback publication moves with the port; the peer publications stay; a stopped app
        # has no placed Quadlet and none is created.
        rendered = (self.pkg / "qbittorrent.container").read_text()
        self.assertIn("PublishPort=127.0.0.1:61997:61997/tcp\n", rendered)
        self.assertNotIn("61006", rendered)
        self.assertEqual(rendered.count("PublishPort=203.0.113.1:61008:61008/"), 2)
        self.assertFalse((self.root / "quadlet/qbittorrent.container").exists())

    def test_folder_only_edit_does_not_pin_the_interface_port(self):
        # DD-219: only a changed port becomes a durable choice; otherwise a later default port still applies.
        self.active = False
        media = str(self.root / "srv/media/movies")
        self.apply(port=61006, save=media)
        self.assertFalse(self.override.exists(), "no override for an unchanged port")
        self.assertFalse((self.drop.parent / "85-konteyner.conf").exists())
        self.assertIn("Volume=" + media + ":" + media, self.drop.read_text())
        # An earlier explicit choice stays exactly as it was.
        self.apply(port=61997)
        before = self.override.read_bytes(), (self.drop.parent / "85-konteyner.conf").read_bytes()
        self.apply(port=61997, save=media)
        self.assertIn("Volume=" + media + ":" + media, self.drop.read_text(), "the folder edit itself applied")
        self.assertEqual((self.override.read_bytes(), (self.drop.parent / "85-konteyner.conf").read_bytes()), before)

    def test_placed_quadlet_publication_moves_and_failure_restores_it(self):
        from test_torrent_api import QUADLET
        placed = self.root / "quadlet/qbittorrent.container"
        placed.write_text(QUADLET % (61006, 61006))
        self.apply()
        self.assertIn("PublishPort=127.0.0.1:61997:61997/tcp\n", placed.read_text())
        placed.write_text(QUADLET % (61006, 61006))
        (self.pkg / "qbittorrent.container").write_text(QUADLET % (61006, 61006))
        self.override.unlink()
        before = placed.read_bytes()
        self.fail_cmd = "systemctl start"
        with self.assertRaises(settings.SettingsError):
            self.apply()
        self.assertEqual(placed.read_bytes(), before)
        self.assertEqual((self.pkg / "qbittorrent.container").read_bytes(), before)

    def test_quadlet_without_its_loopback_publication_is_refused_before_stop(self):
        (self.pkg / "qbittorrent.container").write_text("[Container]\nImage=x\nNetwork=host\n")
        with self.assertRaisesRegex(settings.SettingsError, "port satırı"):
            self.apply()
        self.assertEqual(self.systemctl(), [], "nothing stopped or written for a Quadlet it cannot patch")
        self.assertFalse(self.override.exists())

    def test_active_edit_waits_on_effective_new_listener(self):
        self.apply()
        self.assertEqual(self.systemctl().count("stop"), 1)
        self.assertEqual(self.systemctl().count("start"), 1)
        self.assertEqual(self.ui_waits, ["61997"])

    def test_invalid_or_reserved_or_occupied_port_refused_before_stop(self):
        for port in (True, "61997", 0, 65536, 80):
            with self.subTest(port=port), self.assertRaises(settings.SettingsError):
                self.apply(port=port)
            self.assertEqual(self.calls, [])
        with socket.socket() as server:
            server.bind(("127.0.0.1", 0))
            with self.assertRaisesRegex(settings.SettingsError, "port|Port"):
                self.apply(port=server.getsockname()[1])
        self.assertEqual(self.calls, [])

    def apply_peer(self, peer, port=61006, save=None):
        request = {"revision": self.view()["revision"],
                   "config": {"listener_port": port, "peer_port": peer, "save": save or self.env["DOWNLOADS_PATH"]}}
        return ayar.konteyner_ayar(ayar.package_env(self.env), request, str(self.state))

    def guard_script(self):
        (self.root / "bin").mkdir(exist_ok=True)
        (self.root / "bin/master_container_network.py").write_text("# fixture\n")

    def test_stopped_peer_edit_moves_both_publications_environment_profile_and_override(self):
        # DD-221: the WAN publications (TCP+UDP), TORRENTING_PORT and Session\Port move together; only the
        # changed key is recorded, the interface port keeps following the package default.
        self.active = False
        probes = []
        patch.object(ayar, "peer_probe", side_effect=lambda address, port: probes.append((address, port))).start()
        result = self.apply_peer(63999)
        self.assertTrue(result["ok"])
        self.assertEqual(probes, [("203.0.113.1", 63999)])
        self.assertNotIn("start", self.systemctl())
        rendered = (self.pkg / "qbittorrent.container").read_text()
        for proto in ("tcp", "udp"):
            self.assertIn("PublishPort=203.0.113.1:63999:63999/%s\n" % proto, rendered)
        self.assertIn("Environment=PUID=1000 TZ=UTC TORRENTING_PORT=63999\n", rendered)
        self.assertNotIn("61008", rendered)
        self.assertIn("PublishPort=127.0.0.1:61006:61006/tcp\n", rendered, "the interface publication stays")
        self.assertIn("Session\\Port=63999", self.conf.read_text())
        self.assertEqual(self.override.read_text(), "TORRENT_PEER_PORT=63999\n")
        self.assertEqual(self.override.stat().st_mode & 0o777, 0o600)
        self.assertFalse((self.drop.parent / "85-konteyner.conf").exists())
        self.assertIn("reverse_proxy 127.0.0.1:61006", self.caddy.read_text())
        self.assertEqual(self.view()["config"]["peer_port"], 63999)
        self.assertEqual(settings.package_env(self.env, "torrent")["TORRENT_PEER_PORT"], "63999")
        self.assertFalse((self.root / "quadlet/qbittorrent.container").exists())

    def test_active_peer_edit_updates_the_guard_before_the_start(self):
        from test_torrent_api import QUADLET
        patch.object(ayar, "peer_probe").start()
        self.guard_script()
        placed = self.root / "quadlet/qbittorrent.container"
        placed.write_text(QUADLET % (61006, 61006))
        self.apply_peer(63999, port=61997)
        self.assertIn("PublishPort=203.0.113.1:63999:63999/udp\n", placed.read_text())
        self.assertIn("PublishPort=127.0.0.1:61997:61997/tcp\n", placed.read_text())
        self.assertEqual(self.override.read_text(), "TORRENT_PEER_PORT=63999\nTORRENT_UI_PORT=61997\n")
        flat = [" ".join(c) for c in self.calls]
        guard = [i for i, c in enumerate(flat) if "master_container_network.py" in c and c.endswith(" apply")]
        start = [i for i, c in enumerate(flat) if c.startswith("systemctl start")]
        self.assertEqual(len(guard), 1)
        self.assertLess(guard[0], start[0], "the new WAN publication is let through before the app starts")

    def test_failed_peer_edit_restores_publications_profile_and_guard(self):
        from test_torrent_api import QUADLET
        patch.object(ayar, "peer_probe").start()
        self.guard_script()
        placed = self.root / "quadlet/qbittorrent.container"
        placed.write_text(QUADLET % (61006, 61006))
        before = placed.read_bytes(), (self.pkg / "qbittorrent.container").read_bytes(), self.conf.read_bytes()
        self.fail_cmd = "systemctl start"
        with self.assertRaises(settings.SettingsError):
            self.apply_peer(63999)
        self.assertEqual((placed.read_bytes(), (self.pkg / "qbittorrent.container").read_bytes(), self.conf.read_bytes()), before)
        self.assertFalse(self.override.exists())
        flat = [" ".join(c) for c in self.calls]
        guards = [i for i, c in enumerate(flat) if "master_container_network.py" in c]
        starts = [i for i, c in enumerate(flat) if c.startswith("systemctl start")]
        self.assertEqual(len(guards), 2, "the guard is reapplied from the restored Quadlet")
        self.assertEqual(len(starts), 2)
        self.assertLess(guards[1], starts[1], "the restored publication is let through before the app restarts")

    def test_invalid_reserved_or_occupied_peer_port_refused_before_stop(self):
        patch.object(ayar, "peer_probe").start()
        self.env["SHARE_PORT"] = "61010"
        for peer in (True, "63999", 0, 1023, 65536, 61006, 61010):
            with self.subTest(peer=peer), self.assertRaises(settings.SettingsError):
                self.apply_peer(peer)
            self.assertEqual(self.calls, [])
        directory = self.root / "containers/definitions"
        directory.mkdir(parents=True)
        definition = directory / "sample.json"
        definition.write_text(json.dumps({"schema": 1, "name": "sample", "revision": "a" * 32, "manual_stop": True,
            "ports": [{"scope": "public", "host_port": 63999, "container_port": 9, "protocol": "udp"}]}))
        definition.chmod(0o600)
        self.env["KONTEYNER_STATE_DIR"] = str(directory.parent)
        with self.assertRaisesRegex(settings.SettingsError, "ayrılmış"):
            self.apply_peer(63999)
        self.assertEqual(self.calls, [])
        del self.env["KONTEYNER_STATE_DIR"]
        patch.object(ayar, "peer_probe", side_effect=settings.SettingsError("kullanımda")).start()
        with self.assertRaisesRegex(settings.SettingsError, "kullanımda"):
            self.apply_peer(63998)
        self.assertEqual(self.calls, [])
        self.assertFalse(self.override.exists())

    def test_peer_probe_refuses_a_held_udp_or_tcp_port(self):
        for kind in (socket.SOCK_DGRAM, socket.SOCK_STREAM):
            with self.subTest(kind=kind), socket.socket(socket.AF_INET, kind) as held:
                held.bind(("127.0.0.1", 0))
                with self.assertRaisesRegex(settings.SettingsError, "eş portu"):
                    ayar.peer_probe("127.0.0.1", held.getsockname()[1])

    def test_quadlet_without_its_peer_publication_is_refused_before_stop(self):
        patch.object(ayar, "peer_probe").start()
        quadlet = self.pkg / "qbittorrent.container"
        for text in (quadlet.read_text().replace("61008:61008/udp", "61009:61009/udp"),
                     quadlet.read_text().replace("TORRENTING_PORT=61008", "TORRENTING_PORT=61009"),
                     quadlet.read_text().replace("203.0.113.1", "198.51.100.7")):
            quadlet.write_text(text)
            with self.subTest(text=text), self.assertRaisesRegex(settings.SettingsError, "Eş portunun"):
                self.apply_peer(63999)
            self.assertEqual(self.systemctl(), [])
            quadlet.write_text(text.replace("61009", "61008").replace("198.51.100.7", "203.0.113.1"))
        self.assertFalse(self.override.exists())

    def test_unknown_config_key_is_refused(self):
        request = {"revision": self.view()["revision"],
                   "config": {"listener_port": 61006, "peer_port": 61008, "save": self.env["DOWNLOADS_PATH"], "x": 1}}
        with self.assertRaisesRegex(settings.SettingsError, "alanları"):
            ayar.konteyner_ayar(ayar.package_env(self.env), request, str(self.state))
        self.assertEqual(self.calls, [])

    def test_bad_folder_is_refused_before_any_service_action(self):
        with self.assertRaises(settings.SettingsError):
            self.apply(save=str(self.root))
        self.assertEqual(self.calls, [])

    def test_saved_stopped_container_reserves_its_planned_tcp_port(self):
        directory = self.root / "containers/definitions"
        directory.mkdir(parents=True)
        definition = directory / "sample.json"
        definition.write_text(json.dumps({"schema": 1, "name": "sample", "revision": "a" * 32,
            "manual_stop": True, "ports": [{"scope": "local", "host_port": 61997, "container_port": 80, "protocol": "tcp"}]}))
        definition.chmod(0o600)
        self.env["KONTEYNER_STATE_DIR"] = str(directory.parent)
        with self.assertRaisesRegex(settings.SettingsError, "port"):
            self.apply()
        self.assertEqual(self.calls, [])

    def test_failure_restores_only_touched_configuration_and_original_service(self):
        old = self.conf.read_bytes(), self.caddy.read_bytes()
        self.fail_cmd = "systemctl start"
        with self.assertRaises(settings.SettingsError):
            self.apply(save=str(self.root / "srv/media/movies"))
        self.assertEqual((self.conf.read_bytes(), self.caddy.read_bytes()), old)
        self.assertFalse(self.override.exists())
        self.assertFalse(self.drop.exists())
        self.assertFalse((self.drop.parent / "85-konteyner.conf").exists())
        self.assertEqual(self.systemctl().count("start"), 2)

    def test_stop_failure_does_not_remove_original_configuration(self):
        old = self.conf.read_bytes(), self.caddy.read_bytes()
        self.fail_cmd = "systemctl stop"
        with self.assertRaises(settings.SettingsError):
            self.apply()
        self.assertEqual((self.conf.read_bytes(), self.caddy.read_bytes()), old)
        self.assertFalse(self.override.exists())
        self.assertIn("start", self.systemctl(), "a failed stop can still have stopped the unit; restore the initial running state")

    def test_existing_settings_form_keeps_container_port_override(self):
        self.apply()
        port_drop = self.drop.parent / "85-konteyner.conf"
        before = port_drop.read_bytes()
        ayar.ayar(ayar.package_env(self.env), {"username": "updated", "save": self.env["DOWNLOADS_PATH"]}, str(self.state))
        self.assertEqual(port_drop.read_bytes(), before)
        self.assertIn("WebUI\\Port=61997", self.conf.read_text())

    def test_cli_dispatch_and_private_override_cli(self):
        self.active = False
        request = {"revision": self.view()["revision"], "config": {"listener_port": 61997, "save": self.env["DOWNLOADS_PATH"]}}
        output = io.StringIO()
        with patch("sys.argv", ["ayar.py", "--state", str(self.state), "konteyner-ayar"]), \
                patch("sys.stdin", io.StringIO(json.dumps(request))), contextlib.redirect_stdout(output):
            ayar.main()
        self.assertTrue(json.loads(output.getvalue())["ok"])
        command = subprocess.run(["python3", str(REPO / "panel/master_settings.py"), "--state", str(self.state),
                                  "package-overrides", "torrent"], capture_output=True, text=True,
                                 env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        self.assertEqual(command.returncode, 0, command.stderr)
        self.assertEqual(command.stdout, "TORRENT_UI_PORT=61997\n")
        for expected, code in ((self.view()["revision"], 0), ("stale", 1)):
            checked = subprocess.run(["python3", str(REPO / "panel/master_settings.py"), "--state", str(self.state),
                                      "container-revision", "torrent", expected], capture_output=True, text=True,
                                     env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
            self.assertEqual(checked.returncode, code, checked.stdout)

    def test_pending_base_change_refused_by_cli_before_mutation(self):
        Path(self.env["SETTINGS_PENDING_FILE"]).write_text('{"id":"pending"}')
        request = {"revision": self.view()["revision"], "config": {"listener_port": 61997, "save": self.env["DOWNLOADS_PATH"]}}
        output = io.StringIO()
        with patch("sys.argv", ["ayar.py", "--state", str(self.state), "konteyner-ayar"]), \
                patch("sys.stdin", io.StringIO(json.dumps(request))), contextlib.redirect_stdout(output), \
                self.assertRaises(SystemExit):
            ayar.main()
        self.assertEqual(json.loads(output.getvalue())["status"], 409)
        self.assertEqual(self.calls, [])
        self.assertFalse(self.override.exists())


class EngineRestartTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="container-engine-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        for rel in ("bin", "mods/sample", "run", "downloads"):
            (self.root / rel).mkdir(parents=True)
        for name in ("flock", "logger"):
            p = self.root / "bin" / name
            p.write_text("#!/bin/sh\n" + ("printf 'lock\\n' >> " + str(self.root / "locks") +
                '\nif [ "$3" = 8 ] && [ -n "$TEST_REVISION_AFTER_LOCK" ]; then printf "%s" "$TEST_REVISION_AFTER_LOCK" > ' +
                str(self.root / "mods/sample/revision") + "; fi\n" if name == "flock" else "") + "exit 0\n")
            p.chmod(0o755)
        pkg = self.root / "mods/sample"
        (pkg / "paket.env").write_text("PAKET_AD=Sample\nPAKET_CALISMA=konteyner\nPAKET_DURDURULABILIR=1\n")
        with (pkg / "paket.env").open("a") as stream:
            stream.write('PAKET_KONTEYNER_YONETIM="adapter.py"\n')
        (pkg / "adapter.py").write_text('from pathlib import Path\ndef container_config(env):\n    return {"revision": (Path(env["MODULES_DIR"]) / "sample/revision").read_text()}\n')
        (pkg / "revision").write_text("before")
        shutil.copy(REPO / "panel/master_settings.py", self.root / "bin/master_settings.py")
        (pkg / "kanca").write_text('paket_yeniden_baslat() { printf "restart\\n" >> "$RUNTIME_DIR/calls"; }\n')
        self.registry = self.root / "registry"
        self.registry.write_text("sample\tcalisiyor\n")
        self.state = self.root / "state.env"
        self.state.write_text("\n".join(k + "=" + str(v) for k, v in {
            "MODULES_FILE": self.registry, "MODULES_DIR": self.root / "mods", "RUNTIME_DIR": self.root / "run",
            "DOWNLOADS_PATH": self.root / "downloads", "SBIN_DIR": self.root / "bin"}.items()) + "\n")

    def run_engine(self, **extra):
        return subprocess.run(["bash", str(REPO / "scripts/master-modul"), "yeniden-baslat", "sample"],
             env=dict(os.environ, STATE_FILE=str(self.state), PATH=str(self.root / "bin") + ":" + os.environ["PATH"], **extra),
             capture_output=True, text=True)

    def test_restart_is_one_engine_operation_with_hook_and_registry(self):
        result = self.run_engine()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / "run/calls").read_text(), "restart\n")
        self.assertEqual((self.root / "locks").read_text(), "lock\nlock\n", "one install/module lock pair for the entire restart")
        self.assertEqual(self.registry.read_text(), "sample\tcalisiyor\n")
        self.assertIn("yeniden-baslat\tbitti", (self.root / "run/modul-sample.ilerleme").read_text())

    def test_restart_refuses_stopped_package_without_running_hook(self):
        self.registry.write_text("sample\tdurduruldu\n")
        result = self.run_engine()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("başlat", result.stderr.lower())
        self.assertFalse((self.root / "run/calls").exists())
        self.assertEqual(self.registry.read_text(), "sample\tdurduruldu\n")

    def test_lifecycle_revision_is_rechecked_after_lock_acquisition(self):
        result = self.run_engine(KONSOL_KONTEYNER_REVISION="before", TEST_REVISION_AFTER_LOCK="after")
        self.assertEqual(result.returncode, 75, result.stderr)
        self.assertEqual((self.root / "locks").read_text(), "lock\nlock\n")
        self.assertEqual((self.root / "mods/sample/revision").read_text(), "after")
        self.assertFalse((self.root / "run/calls").exists())
        self.assertEqual(self.registry.read_text(), "sample\tcalisiyor\n")
        self.assertIn("yeniden-baslat\thata", (self.root / "run/modul-sample.ilerleme").read_text())

    def test_matching_lifecycle_revision_allows_the_single_restart(self):
        result = self.run_engine(KONSOL_KONTEYNER_REVISION="before")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / "run/calls").read_text(), "restart\n")


if __name__ == "__main__":
    unittest.main()
