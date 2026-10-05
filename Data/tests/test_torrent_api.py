"""qBittorrent package (DD-202): the settings worker ayar.py and the API module api.py behind
the root backend's package dispatcher. No real qBittorrent, Podman or systemd: service control is
faked, the profile and the quadlet drop-in (DD-209) are scratch files."""
import base64
import contextlib
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import test_resources as resources

panel = resources.panel
REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "magaza" / "torrent"
sys.path.insert(0, str(REPO / "panel"))
import master_settings as settings  # noqa: E402


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


ayar = load("torrent_ayar_test", PACKAGE / "ayar.py")
SEED = ("[Preferences]\nWebUI\\Username=admin\nWebUI\\Password_PBKDF2=oldhash\nWebUI\\Address=127.0.0.1\n"
        "WebUI\\Port=61006\nUnrelated=keep\n[BitTorrent]\nSession\\DefaultSavePath=%s/\nSession\\Port=45410\n")


QUADLET = ("[Container]\nImage=lscr.io/linuxserver/qbittorrent@sha256:" + "b5" * 32 + "\nContainerName=qbittorrent\n"
           "Network=torrent\nPublishPort=127.0.0.1:%d:%d/tcp\nPublishPort=203.0.113.1:61008:61008/tcp\n"
           "PublishPort=203.0.113.1:61008:61008/udp\nEnvironment=PUID=1000 TZ=UTC TORRENTING_PORT=61008\n")


class Scratch(unittest.TestCase):
    """A profile, unit folder and user area like the installer's, plus a recording service control."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="torrent-pkg-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        for rel in ("profile/qBittorrent", "units", "quadlet", "run", "etc", "dns", "srv/downloads", "srv/media/movies", "srv/.pay",
                    "srv/media/a b"):
            (self.root / rel).mkdir(parents=True)
        self.env = {
            "SETTINGS_FILE": str(self.root / "etc/settings.json"), "SETTINGS_PENDING_FILE": str(self.root / "etc/pending.json"),
            "SETTINGS_DNS_FILE": str(self.root / "dns/konsol.conf"), "DNSMASQ_CONF_FILE": str(self.root / "dns/base.conf"),
            "DNSMASQ_CONF_DIR": str(self.root / "dns"), "TORRENT_PROFILE_DIR": str(self.root / "profile"),
            "UNIT_DIR": str(self.root / "units"), "MODULES_FILE": str(self.root / "modules"),
            "KONTEYNER_BIRIM_DIR": str(self.root / "quadlet"), "TORRENT_CONTAINER": "qbittorrent", "TORRENT_UI_PORT": "61006",
            "MODULES_DIR": str(self.root / "mods"), "RUNTIME_DIR": str(self.root / "run"),
            "SERVER_ROOT": str(self.root / "srv"), "DOWNLOADS_PATH": str(self.root / "srv/downloads"), "MEDIA_SUBDIR": "media",
            "LOCAL_DOMAIN": "test", "TAILSCALE_IF": "tailscale0", "WAN_INTERFACE": "eth0", "WAN_IPV4": "203.0.113.1",
            "TAILSCALE_IPV4": "100.64.0.2", "DOWNLOADS_UID": str(os.getuid()), "DOWNLOADS_GID": str(os.getgid()),
            "SBIN_DIR": str(self.root / "bin"), "DNS_PORT": "53", "CADDY_HTTP_PORT": "80",
            "CADDYFILE": str(self.root / "Caddyfile"), "CADDY_MODULES_DIR": str(self.root / "caddy-modules"),
        }
        (self.root / "modules").write_text("torrent\tcalisiyor\n")
        (self.root / "dns/base.conf").write_text("interface=lo\n")
        self.state = self.root / "state.env"
        self.state.write_text("".join(k + "=" + v + "\n" for k, v in self.env.items()))
        self.conf = ayar.conf_path(self.env)
        self.drop = ayar.drop_in_path(self.env)
        self.conf.write_text(SEED % self.env["DOWNLOADS_PATH"])
        self.conf.chmod(0o640)
        # DD-203: the rendered package folder with its own settings file; the worker reads it next to itself.
        self.pkg = self.root / "mods" / "torrent"
        self.pkg.mkdir(parents=True)
        for name in ("api.py", "ayar.py", "klasorler.py"):
            shutil.copy(PACKAGE / name, self.pkg / name)
        (self.pkg / "paket.env").write_text((PACKAGE / "paket.env").read_text().replace("__TORRENT_UI_PORT__", "61006")
                                            .replace("__DOWNLOADS_PATH__", self.env["DOWNLOADS_PATH"]))
        (self.pkg / "torrent.env").write_text("TORRENT_UI_PORT=61006\nTORRENT_PEER_PORT=61008\nTORRENT_PROFILE_DIR=%s\nTORRENT_CONTAINER=qbittorrent\n" % self.env["TORRENT_PROFILE_DIR"])
        # DD-217: the rendered Quadlet publishes the interface on loopback and the peer port on the WAN address.
        (self.pkg / "qbittorrent.container").write_text(QUADLET % (61006, 61006))
        self.calls, self.fail_cmd, self.active = [], None, True
        self.addCleanup(patch.stopall)
        patch.object(settings, "run", side_effect=self.fake_run).start()
        patch.object(ayar, "PACKAGE_DIR", str(self.pkg)).start()
        # DD-209: the worker waits for the interface after a restart; here it answers at once.
        self.ui_waits = []
        patch.object(ayar, "wait_ui", side_effect=lambda env, seconds=40: self.ui_waits.append(env["TORRENT_UI_PORT"])).start()

    def fake_run(self, argv, **kwargs):
        self.calls.append(list(argv))
        if self.fail_cmd and self.fail_cmd in " ".join(argv):
            self.fail_cmd = None
            raise settings.SettingsError("injected failure")
        code = 0
        if argv[:3] == ["systemctl", "is-active", "--quiet"]:
            code = 0 if self.active else 3
            settings.require(not kwargs.get("check", True) or code == 0, "Test servisi durmuş")
        return subprocess.CompletedProcess(argv, code, "", "")

    def systemctl(self):
        return [c[1] for c in self.calls if c[0] == "systemctl"]


class WorkerTests(Scratch):
    def test_password_hash_format_and_ini_preservation(self):
        hashed = ayar.password_hash("sample-test-phrase")
        salt, key = hashed[len("@ByteArray("):-1].split(":")
        self.assertEqual(len(base64.b64decode(salt)), 16)
        self.assertEqual(base64.b64decode(key), hashlib.pbkdf2_hmac("sha512", b"sample-test-phrase", base64.b64decode(salt), 100000, 64))
        result = ayar.ini_patch("[Preferences]\nOther=value\nWebUI\\Username=old\n[BitTorrent]\nX=2\n", {("Preferences", "WebUI\\Username"): "new"})
        self.assertIn("Other=value\n", result)
        self.assertIn("[BitTorrent]\nX=2\n", result)
        self.assertIn("WebUI\\Username=new", result)
        # A key whose section does not exist yet gets its section appended.
        result = ayar.ini_patch("[Preferences]\nA=1\n", {("BitTorrent", "Session\\DefaultSavePath"): '"/x/"'})
        self.assertIn("[Preferences]\nA=1\n", result)
        self.assertIn('[BitTorrent]\nSession\\DefaultSavePath="/x/"', result)

    def test_durum_reports_paths_and_account_name_without_the_hash(self):
        d = ayar.durum(self.env)
        self.assertEqual((d["profile"], d["downloads"]), (self.env["TORRENT_PROFILE_DIR"], self.env["DOWNLOADS_PATH"]))
        self.assertEqual((d["save"], d["save_inside"]), (self.env["DOWNLOADS_PATH"] + "/", True))
        self.assertEqual((d["temp"], d["temp_on"], d["temp_inside"]), ("", False, False))
        self.assertEqual((d["ui"], d["peer_port"], d["username"]), ("127.0.0.1:61006", 45410, "admin"))
        self.assertNotIn("oldhash", json.dumps(d))
        self.assertNotIn("Password", json.dumps(d))
        with self.conf.open("a") as fh:
            fh.write("Session\\TempPath=%s/incomplete/\nSession\\TempPathEnabled=true\n" % self.env["DOWNLOADS_PATH"])
        d = ayar.durum(self.env)
        self.assertEqual((d["temp"], d["temp_on"], d["temp_inside"]), (self.env["DOWNLOADS_PATH"] + "/incomplete/", True, True))
        self.conf.write_text(SEED % "/root/indirilenler")
        self.assertFalse(ayar.durum(self.env)["save_inside"])
        self.conf.unlink()
        self.assertEqual(ayar.durum(self.env), {"error": "qBittorrent'in ayar dosyası okunamadı", "profile": self.env["TORRENT_PROFILE_DIR"]})
        self.conf.symlink_to(self.root / "dns/base.conf")
        self.assertIn("error", ayar.durum(self.env))
        self.assertEqual(self.calls, [], "the view runs no command")

    def test_hesap_validation_runs_before_any_service_change(self):
        before = self.conf.read_bytes()
        for data in ({}, {"x": 1}, {"username": "bad user"}, {"username": ""}, {"username": "a" * 65}, {"password": "short"},
                     {"password": "x" * 257}, {"password": "1234567\n9"}, {"password": None}, {"username": 5}, "text", None,
                     {"username": "ok", "password": ""}):
            with self.subTest(data=data), self.assertRaises(settings.SettingsError):
                ayar.hesap(self.env, data)
        self.assertEqual(self.conf.read_bytes(), before)
        self.assertEqual(self.calls, [])
        for phrase in ("Pass8!xy", "ü" * 8, "x" * 256):
            with self.subTest(phrase=phrase):
                ayar.hesap(self.env, {"password": phrase})

    def test_hesap_stops_writes_and_starts_again_without_plaintext(self):
        phrase = "sample-only-test-password"
        self.assertEqual(ayar.hesap(self.env, {"username": "newuser", "password": phrase}), {"ok": True, "username": "newuser"})
        text = self.conf.read_text()
        self.assertIn("WebUI\\Username=newuser\n", text)
        for keep in ("Unrelated=keep\n", "[BitTorrent]\n", "Session\\Port=45410\n", "WebUI\\Address=127.0.0.1\n"):
            self.assertIn(keep, text)
        self.assertNotIn(phrase, text)
        self.assertNotIn("oldhash", text)
        salt, key = text.split("WebUI\\Password_PBKDF2=@ByteArray(", 1)[1].split(")", 1)[0].split(":")
        self.assertEqual(base64.b64decode(key), hashlib.pbkdf2_hmac("sha512", phrase.encode(), base64.b64decode(salt), 100000, 64))
        self.assertEqual(self.conf.stat().st_mode & 0o777, 0o640)
        self.assertEqual(self.systemctl(), ["is-active", "stop", "start", "is-active"])
        self.assertEqual(self.ui_waits, ["61006"], "the change counts once the interface answers")
        self.assertFalse(self.drop.exists(), "an account change adds no drop-in")

    def test_username_only_keeps_hash_and_password_only_keeps_username(self):
        ayar.hesap(self.env, {"username": "other"})
        self.assertIn("WebUI\\Password_PBKDF2=oldhash\n", self.conf.read_text())
        ayar.hesap(self.env, {"password": "password-only-test"})
        text = self.conf.read_text()
        self.assertIn("WebUI\\Username=other\n", text)
        self.assertNotIn("oldhash", text)

    def test_failed_start_restores_the_profile_and_starts_the_service_again(self):
        before = self.conf.read_bytes()
        self.fail_cmd = "start qbittorrent.service"
        with self.assertRaises(settings.SettingsError):
            ayar.hesap(self.env, {"username": "failed-user"})
        self.assertEqual(self.conf.read_bytes(), before)
        self.assertEqual(self.conf.stat().st_mode & 0o777, 0o640)
        self.assertEqual(self.systemctl(), ["is-active", "stop", "start", "start"], "the second start is the recovery")

    def test_stopped_service_stays_stopped(self):
        self.active = False
        self.assertEqual(ayar.hesap(self.env, {"username": "stopped-user"}), {"ok": True, "username": "stopped-user"})
        self.assertEqual(self.systemctl(), ["is-active", "stop"])
        self.assertEqual(self.ui_waits, [], "a stopped service is not waited for")
        self.assertIn("WebUI\\Username=stopped-user\n", self.conf.read_text())

    def test_an_interface_that_never_opens_restores_the_profile(self):
        before = self.conf.read_bytes()
        with patch.object(ayar, "wait_ui", side_effect=settings.SettingsError("qBittorrent arayüzü yeniden başlatmadan sonra açılmadı.")):
            with self.assertRaises(settings.SettingsError):
                ayar.hesap(self.env, {"username": "slow-user"})
        self.assertEqual(self.conf.read_bytes(), before)
        self.assertEqual(self.systemctl(), ["is-active", "stop", "start", "is-active", "start"], "restored, then started again")

    def test_dizin_writes_one_narrow_drop_in_and_restores_both_files_on_failure(self):
        before = self.conf.read_bytes()
        for data in ({}, {"save": 1}, {"save": "/etc"}, {"save": str(self.root / "srv")}, {"save": str(self.root / "srv/.pay")},
                     {"save": str(self.root / "srv/downloads/../media")}, {"other": "x"}, {"save": str(self.root / "srv/media"), "x": 1}):
            with self.subTest(data=data), self.assertRaises(settings.SettingsError):
                ayar.dizin(self.env, data, str(self.state))
        self.assertEqual(self.conf.read_bytes(), before)
        self.assertEqual(self.calls, [], "validation runs no command")
        media = str(self.root / "srv/media")
        # First failure, no drop-in yet: the profile is restored and the drop-in does not appear.
        self.fail_cmd = "start qbittorrent.service"
        with self.assertRaises(settings.SettingsError):
            ayar.dizin(self.env, {"save": media}, str(self.state))
        self.assertEqual(self.conf.read_bytes(), before)
        self.assertFalse(self.drop.exists())
        self.assertEqual(self.systemctl().count("daemon-reload"), 2)
        self.calls.clear()
        self.assertEqual(ayar.dizin(self.env, {"save": media}, str(self.state)), {"ok": True, "save": media + "/"})
        text = self.conf.read_text()
        self.assertIn('Session\\DefaultSavePath="%s/"\n' % media, text)
        self.assertIn('Downloads\\SavePath="%s/"\n' % media, text)
        self.assertIn("Unrelated=keep\n", text)
        # DD-209: a folder outside the downloads tree is one bind mount at the same path in the quadlet drop-in.
        self.assertEqual(self.drop, self.root / "quadlet/qbittorrent.container.d/90-konsol.conf")
        self.assertEqual(self.drop.read_text(), "# Konsol: qBittorrent indirme dizini (DD-209)\n[Container]\nVolume=%s:%s\n" % (media, media))
        self.assertEqual(self.drop.stat().st_mode & 0o777, 0o644)
        probe = [c for c in self.calls if c[0] == "setpriv"]
        self.assertEqual(len(probe), 1, "writability is probed as the service user")
        self.assertIn("--reuid=" + self.env["DOWNLOADS_UID"], probe[0])
        self.assertEqual(self.systemctl(), ["is-active", "stop", "daemon-reload", "start", "is-active"])
        self.assertEqual(ayar.durum(self.env)["save"], media + "/")
        # Second failure, with a drop-in: both files return to the previous choice.
        saved_conf, saved_drop = self.conf.read_bytes(), self.drop.read_bytes()
        self.fail_cmd = "start qbittorrent.service"
        with self.assertRaises(settings.SettingsError):
            ayar.dizin(self.env, {"save": self.env["DOWNLOADS_PATH"]}, str(self.state))
        self.assertEqual((self.conf.read_bytes(), self.drop.read_bytes()), (saved_conf, saved_drop))
        # Back inside the downloads tree: the extra mount goes (the container already sees that folder).
        self.calls.clear()
        inner = self.env["DOWNLOADS_PATH"] + "/filmler"
        os.mkdir(inner)
        self.assertEqual(ayar.dizin(self.env, {"save": inner}, str(self.state)), {"ok": True, "save": inner + "/"})
        self.assertFalse(self.drop.exists())
        self.assertEqual(self.systemctl(), ["is-active", "stop", "daemon-reload", "start", "is-active"])
        # A folder name a bind mount cannot carry (space, ':' or '%') is refused before any service change.
        self.calls.clear()
        with self.assertRaises(settings.SettingsError) as err:
            ayar.dizin(self.env, {"save": str(self.root / "srv/media/a b")}, str(self.state))
        self.assertIn("konteynere bağlanamaz", str(err.exception))
        self.assertEqual(self.systemctl(), [])

    def test_standalone_run_finds_the_base_library_through_lib(self):
        # Found live: run as its own process from the package folder, the worker has no base module
        # on sys.path; the backend hands it the engine's folder as --lib.
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH",)}
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        argv = [sys.executable, str(self.pkg / "ayar.py"), "--state", str(self.state), "durum"]
        with_lib = argv[:2] + ["--lib", str(REPO / "panel")] + argv[2:]
        p = subprocess.run(with_lib, capture_output=True, text=True, env=env, cwd=str(self.root), timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)["username"], "admin")
        if shutil.which("master-modul") is None and not os.path.exists("/usr/local/sbin/master_settings.py"):
            p = subprocess.run(argv, capture_output=True, text=True, env=env, cwd=str(self.root), timeout=60)
            self.assertNotEqual(p.returncode, 0)
            self.assertIn("master_settings", p.stderr)

    def test_package_env_overrides_the_state_and_the_folder_module_reports_the_chosen_temp(self):
        # The state carries no TORRENT_* key any more; the package's own file does (DD-203).
        state_only = {k: v for k, v in self.env.items() if not k.startswith("TORRENT_")}
        merged = ayar.package_env(state_only)
        self.assertEqual(merged["TORRENT_PROFILE_DIR"], self.env["TORRENT_PROFILE_DIR"])
        self.assertEqual(merged["TORRENT_UI_PORT"], "61006")
        klasorler = load("torrent_klasorler_test", self.pkg / "klasorler.py")
        self.assertEqual(klasorler.yazilan(state_only), [])
        with self.conf.open("a") as fh:
            fh.write('Session\\TempPath="%s/incomplete/"\n' % self.env["DOWNLOADS_PATH"])
        self.assertEqual(klasorler.yazilan(state_only), [self.env["DOWNLOADS_PATH"] + "/incomplete"])
        self.conf.unlink()
        self.assertEqual(klasorler.yazilan(state_only), [], "a missing profile reports nothing")
        self.conf.symlink_to(self.root / "dns/base.conf")
        with self.assertRaises((settings.SettingsError, OSError)):
            klasorler.yazilan(state_only)  # an unsafe profile is an error, never a guess
        self.assertEqual(self.calls, [])

    def test_cli_reads_json_on_stdin_and_answers_json(self):
        def main(action, stdin=""):
            out = io.StringIO()
            with patch("sys.argv", ["ayar.py", "--lib", str(REPO / "panel"), "--state", str(self.state), action]), patch("sys.stdin", io.StringIO(stdin)), \
                    contextlib.redirect_stdout(out):
                try:
                    ayar.main()
                except SystemExit as stop:
                    return stop.code, json.loads(out.getvalue())
            return 0, json.loads(out.getvalue())
        code, view = main("durum")
        self.assertEqual((code, view["save"], view["username"]), (0, self.env["DOWNLOADS_PATH"] + "/", "admin"))
        self.assertEqual(main("hesap", json.dumps({"username": "cliuser"})), (0, {"ok": True, "username": "cliuser"}))
        self.assertIn("WebUI\\Username=cliuser\n", self.conf.read_text())
        code, err = main("hesap", json.dumps({"password": "short"}))
        self.assertEqual((code, err), (1, {"error": "Parola 8–256 karakter olmalı."}))
        code, err = main("hesap", "not json")
        self.assertEqual(code, 1)
        self.assertEqual(err["error"], "qBittorrent ayarı uygulanamadı; önceki ayar geri yüklendi.")
        code, err = main("hesap", json.dumps({"username": "a" * (ayar.LIMIT + 1)}))
        self.assertEqual((code, err), (1, {"error": "İstek çok büyük."}))
        code, err = main("dizin", json.dumps({"save": str(self.root / "srv")}))
        self.assertEqual(code, 1)
        self.assertIn("Yalnız indirmeler", err["error"])
        # The base's settings lock is honoured: a held lock refuses the worker.
        with settings.Manager(str(self.state)).locked():
            code, err = main("hesap", json.dumps({"username": "locked"}))
        self.assertEqual(code, 1)
        self.assertIn("WebUI\\Username=cliuser\n", self.conf.read_text())



class InstallWorkerTests(Scratch):
    """DD-210: the App Store install form. kur-hazirla validates the choices and stores only a hash in a
    private seed; kur-uygula writes them into the profile before the first start; kur-geri restores."""
    def setUp(self):
        super().setUp()
        self.seed = self.root / "run" / "modul-torrent.kur"
        self.form = {"username": "operator", "password": "first-install-phrase", "save": self.env["DOWNLOADS_PATH"]}

    def test_kur_hazirla_validates_everything_before_writing_and_keeps_only_a_hash(self):
        media = str(self.root / "srv/media")
        bad = [None, "text", {}, {"username": "operator", "save": media}, dict(self.form, password=""),
               dict(self.form, password="short"), dict(self.form, password="x" * 257), dict(self.form, password="tab\there"),
               dict(self.form, username="bad user"), dict(self.form, username=""), dict(self.form, save="/etc"),
               dict(self.form, save=str(self.root / "srv/.pay")), dict(self.form, save=str(self.root / "srv/media/a b")),
               dict(self.form, extra=1)]
        for data in bad:
            with self.subTest(data=data), self.assertRaises(settings.SettingsError):
                ayar.kur_hazirla(self.env, data, str(self.state), str(self.seed))
        self.assertFalse(self.seed.exists(), "a refused form leaves no seed")
        with self.assertRaises(settings.SettingsError):
            ayar.kur_hazirla(self.env, self.form, str(self.state), str(self.root / "elsewhere.kur"))
        self.assertFalse((self.root / "elsewhere.kur").exists(), "the seed lives only in the runtime folder")
        self.assertEqual(self.systemctl(), [], "preparing an install touches no service")
        self.calls.clear()
        result = ayar.kur_hazirla(self.env, dict(self.form, save=media), str(self.state), str(self.seed))
        self.assertEqual(result, {"ok": True, "username": "operator", "save": media + "/"})
        self.assertEqual(self.seed.stat().st_mode & 0o777, 0o600)
        raw = self.seed.read_text()
        self.assertNotIn("first-install-phrase", raw)
        data = json.loads(raw)
        self.assertEqual((data["username"], data["save"]), ("operator", media + "/"))
        salt, key = data["hash"][len("@ByteArray("):-1].split(":")
        self.assertEqual(base64.b64decode(key), hashlib.pbkdf2_hmac("sha512", b"first-install-phrase", base64.b64decode(salt), 100000, 64))
        self.assertEqual(len([c for c in self.calls if c[0] == "setpriv"]), 1, "writability is probed as the service user")
        self.assertEqual(self.conf.read_text(), SEED % self.env["DOWNLOADS_PATH"], "the profile is not touched yet")

    def test_kur_uygula_writes_the_choices_before_the_first_start_and_kur_geri_restores_them(self):
        media = str(self.root / "srv/media")
        operator = (SEED % "/elsewhere") + "[Network]\nPortForwardingEnabled=true\n"
        self.conf.write_text(operator)
        self.conf.chmod(0o640)
        before = self.conf.read_bytes()
        ayar.kur_hazirla(self.env, dict(self.form, save=media), str(self.state), str(self.seed))
        self.calls.clear()
        self.assertEqual(ayar.kur_uygula(self.env, str(self.seed)), {"ok": True})
        text = self.conf.read_text()
        self.assertIn("WebUI\\Username=operator\n", text)
        self.assertIn('Session\\DefaultSavePath="%s/"\n' % media, text)
        self.assertIn('Downloads\\SavePath="%s/"\n' % media, text)
        self.assertNotIn("oldhash", text)
        self.assertNotIn("first-install-phrase", text)
        for keep in ("Unrelated=keep\n", "Session\\Port=45410\n", "PortForwardingEnabled=true\n"):
            self.assertIn(keep, text, "a kept profile keeps every other preference")
        # DD-217: on its own bridge the interface listens on the container's address (published on loopback only).
        self.assertIn("WebUI\\Address=*\n", text)
        self.assertNotIn("WebUI\\Address=127.0.0.1", text)
        self.assertEqual(self.conf.stat().st_mode & 0o777, 0o640)
        self.assertEqual(self.drop.read_text(), "# Konsol: qBittorrent indirme dizini (DD-209)\n[Container]\nVolume=%s:%s\n" % (media, media))
        self.assertEqual(self.calls, [], "no service command: the container has not started yet")
        ayar.kur_geri(self.env, str(self.seed))
        self.assertEqual(self.conf.read_bytes(), before, "a failed install returns the previous account and folder")
        self.assertFalse(self.drop.exists())
        # Inside the downloads tree an earlier drop-in goes, and comes back on rollback.
        self.drop.parent.mkdir(parents=True, exist_ok=True)
        self.drop.write_text("[Container]\nVolume=/old:/old\n")
        ayar.kur_hazirla(self.env, self.form, str(self.state), str(self.seed))
        self.calls.clear()
        ayar.kur_uygula(self.env, str(self.seed))
        self.assertFalse(self.drop.exists())
        ayar.kur_geri(self.env, str(self.seed))
        self.assertEqual(self.drop.read_text(), "[Container]\nVolume=/old:/old\n")
        self.assertEqual(self.calls, [])

    def test_kur_uygula_refuses_a_seed_that_is_not_private(self):
        ayar.kur_hazirla(self.env, self.form, str(self.state), str(self.seed))
        before = self.conf.read_bytes()
        self.seed.chmod(0o644)
        with self.assertRaises(settings.SettingsError):
            ayar.kur_uygula(self.env, str(self.seed))
        self.seed.chmod(0o600)
        link = self.root / "run" / "modul-link.kur"
        link.symlink_to(self.seed)
        with self.assertRaises((settings.SettingsError, OSError)):
            ayar.kur_uygula(self.env, str(link))
        data = json.loads(self.seed.read_text())
        for broken in (dict(data, username="bad user"), dict(data, hash="plain"), dict(data, save="relative/")):
            with self.subTest(broken=broken), self.assertRaises(settings.SettingsError):
                self.seed.write_text(json.dumps(broken))
                ayar.kur_uygula(self.env, str(self.seed))
        self.assertEqual(self.conf.read_bytes(), before)
        self.seed.unlink()
        with self.assertRaises((settings.SettingsError, OSError)):
            ayar.kur_uygula(self.env, str(self.seed))
        ayar.kur_geri(self.env, str(self.seed))  # nothing applied: nothing to restore
        self.assertEqual(self.conf.read_bytes(), before)

    def test_ayar_changes_every_field_with_one_restart_and_a_blank_password_keeps_the_hash(self):
        media = str(self.root / "srv/media")
        before = self.conf.read_bytes()
        for data in ({}, {"password": ""}, {"username": "bad user"}, {"save": "/etc"}, {"x": 1}, None,
                     {"username": "ok", "save": str(self.root / "srv/media/a b")}):
            with self.subTest(data=data), self.assertRaises(settings.SettingsError):
                ayar.ayar(self.env, data, str(self.state))
        self.assertEqual(self.conf.read_bytes(), before)
        self.assertEqual(self.systemctl(), [], "validation runs before any service change")
        self.calls.clear()
        result = ayar.ayar(self.env, {"username": "edited", "save": media}, str(self.state))
        self.assertEqual(result, {"ok": True, "username": "edited", "save": media + "/"})
        text = self.conf.read_text()
        self.assertIn("WebUI\\Username=edited\n", text)
        self.assertIn("WebUI\\Password_PBKDF2=oldhash\n", text, "no password given: the stored one stays")
        self.assertIn('Session\\DefaultSavePath="%s/"\n' % media, text)
        self.assertTrue(self.drop.exists())
        self.assertEqual(self.systemctl(), ["is-active", "stop", "daemon-reload", "start", "is-active"], "one stop and one start")
        # A failed restart restores the account, the folder and the drop-in together.
        saved = (self.conf.read_bytes(), self.drop.read_bytes())
        self.fail_cmd = "start qbittorrent.service"
        with self.assertRaises(settings.SettingsError):
            ayar.ayar(self.env, {"username": "lost", "password": "never-applied-phrase", "save": self.env["DOWNLOADS_PATH"]}, str(self.state))
        self.assertEqual((self.conf.read_bytes(), self.drop.read_bytes()), saved)
        # A stopped app stays stopped; the account alone adds no daemon-reload.
        self.calls.clear()
        self.active = False
        ayar.ayar(self.env, {"password": "stopped-phrase-1"}, str(self.state))
        self.assertEqual(self.systemctl(), ["is-active", "stop"])
        self.assertNotIn("oldhash", self.conf.read_text())

    def test_cli_install_actions_read_stdin_and_never_print_the_password(self):
        def main(argv, stdin=""):
            out = io.StringIO()
            with patch("sys.argv", ["ayar.py", "--lib", str(REPO / "panel"), "--state", str(self.state), *argv]), \
                    patch("sys.stdin", io.StringIO(stdin)), contextlib.redirect_stdout(out):
                try:
                    ayar.main()
                except SystemExit as stop:
                    return stop.code, json.loads(out.getvalue())
            return 0, json.loads(out.getvalue())
        code, body = main(["kur-hazirla", "--tohum", str(self.seed)], json.dumps(self.form))
        self.assertEqual((code, body["username"]), (0, "operator"))
        self.assertNotIn("first-install-phrase", json.dumps(body))
        self.assertEqual(main(["kur-uygula", "--tohum", str(self.seed)]), (0, {"ok": True}))
        self.assertEqual(main(["kur-geri", "--tohum", str(self.seed)]), (0, {"ok": True}))
        code, body = main(["kur-hazirla", "--tohum", str(self.seed)], json.dumps(dict(self.form, password="short")))
        self.assertEqual((code, body), (1, {"error": "Parola 8–256 karakter olmalı."}))
        code, body = main(["ayar"], json.dumps({"username": "cli-edit"}))
        self.assertEqual((code, body["username"]), (0, "cli-edit"))
        with patch("sys.argv", ["ayar.py", "--state", str(self.state), "kur-uygula"]), patch("sys.stderr", io.StringIO()), \
                self.assertRaises(SystemExit) as stop:
            ayar.main()  # the seed path is required
        self.assertEqual(stop.exception.code, 2)

class FakeContext:
    """What api.py may use of the backend (PackageContext), recording the worker calls."""
    def __init__(self, env, state, active=True):
        self._env, self._state, self.active = env, state, active
        self.worker_calls, self.runs = [], []
        self.worker_result = (200, {"ok": True, "username": "worker-user"})

    def env(self):
        return {k: v for k, v in self._env.items() if not k.startswith("TORRENT_")}  # the state has none (DD-203)

    read_env = staticmethod(panel.read_env)

    def state_path(self):
        return self._state

    @staticmethod
    def tool(name):
        return "/fixture/sbin/" + name

    def run(self, argv, binary=False, timeout=120):
        self.runs.append(list(argv))
        return (0 if self.active else 3), "", ""

    def worker(self, argv, data):
        self.worker_calls.append((list(argv), json.loads(json.dumps(data))))
        return self.worker_result

    @staticmethod
    def error(code, message):
        return panel.ApiError(code, message)


class FakeRequest:
    def __init__(self, method, path, data=None):
        self.method, self.path, self.query, self.data = method, path, {}, data
        self.user, self.client, self.audits = "konsol", "yerel", []

    def audit(self, verb, detail, ok):
        self.audits.append((verb, detail, ok))


class ApiModuleTests(Scratch):
    def setUp(self):
        super().setUp()
        self.api_module = load("torrent_api_test", self.pkg / "api.py")
        self.ctx = FakeContext(self.env, str(self.state))
        self.api = self.api_module.create(self.ctx)

    def test_status_is_the_workers_view_plus_the_service_state(self):
        code, body = self.api.handle(FakeRequest("GET", "/durum"))
        self.assertEqual(code, 200)
        self.assertEqual((body["installed"], body["running"], body["save"], body["username"]), (True, True, self.env["DOWNLOADS_PATH"] + "/", "admin"))
        self.assertEqual(body["unit"], ayar.unit_name(self.env))
        self.assertEqual(self.ctx.runs, [["systemctl", "is-active", "--quiet", body["unit"]]])
        self.assertNotIn("oldhash", json.dumps(body))
        self.ctx.active = False
        self.assertFalse(self.api.handle(FakeRequest("GET", "/durum"))[1]["running"])
        self.assertEqual(self.ctx.worker_calls, [], "reads never start the worker")

    def test_bad_shapes_are_refused_before_the_worker(self):
        for path, data in (("/hesap", {}), ("/hesap", None), ("/hesap", {"x": 1}), ("/hesap", {"username": "bad user"}),
                           ("/hesap", {"username": 5}), ("/hesap", {"password": "short"}), ("/hesap", {"password": "x" * 257}),
                           ("/hesap", {"password": "tab\there"}), ("/dizin", {}), ("/dizin", {"save": 1}), ("/dizin", {"save": "x" * 1025}),
                           ("/dizin", {"save": "/x", "y": 1}), ("/dizin", None)):
            with self.subTest(path=path, data=data), self.assertRaises(panel.ApiError) as caught:
                self.api.handle(FakeRequest("POST", path, data))
            self.assertEqual(caught.exception.code, 400)
        self.assertEqual(self.ctx.worker_calls, [])
        with self.assertRaises(panel.ApiError) as caught:
            self.api.handle(FakeRequest("GET", "/yok"))
        self.assertEqual(caught.exception.code, 404)
        with self.assertRaises(panel.ApiError) as caught:
            self.api.handle(FakeRequest("PUT", "/hesap", {"username": "x"}))
        self.assertEqual(caught.exception.code, 405)

    def test_changes_run_the_packages_worker_with_the_state_and_audit_without_secrets(self):
        req = FakeRequest("POST", "/hesap", {"username": "new-user", "password": "dummy-api-password"})
        self.assertEqual(self.api.handle(req), (200, {"ok": True, "username": "worker-user"}))
        argv, data = self.ctx.worker_calls[0]
        self.assertEqual(argv, ["/usr/bin/python3", str(self.pkg / "ayar.py"), "--lib", "/fixture/sbin", "--state", str(self.state), "hesap"])
        self.assertEqual(data, {"username": "new-user", "password": "dummy-api-password"})
        self.assertEqual(req.audits, [("hesap", "kullanıcı adı ve parola", True)])
        req = FakeRequest("POST", "/hesap", {"password": "dummy-api-password"})
        self.api.handle(req)
        self.assertEqual(req.audits, [("hesap", "parola", True)])
        self.ctx.worker_result = (200, {"ok": True, "save": "/srv/media/"})
        req = FakeRequest("POST", "/dizin", {"save": "/srv/media"})
        self.assertEqual(self.api.handle(req), (200, {"ok": True, "save": "/srv/media/"}))
        self.assertEqual(self.ctx.worker_calls[-1][0][-1], "dizin")
        self.assertEqual(req.audits, [("dizin", "/srv/media", True)])
        self.assertEqual(self.calls, [], "the API module itself touches no file and runs no service command")

    def test_worker_refusals_become_the_requests_error(self):
        self.ctx.worker_result = (400, {"error": "Kullanıcı adı geçersiz."})
        req = FakeRequest("POST", "/hesap", {"username": "x"})
        with self.assertRaises(panel.ApiError) as caught:
            self.api.handle(req)
        self.assertEqual((caught.exception.code, caught.exception.message), (400, "Kullanıcı adı geçersiz."))
        self.assertEqual(req.audits, [("hesap", "kullanıcı adı", False)])
        self.ctx.worker_result = (502, "garbage")
        with self.assertRaises(panel.ApiError) as caught:
            self.api.handle(FakeRequest("POST", "/dizin", {"save": "/x"}))
        self.assertEqual((caught.exception.code, caught.exception.message), (502, "qBittorrent ayarı uygulanamadı"))


    def test_ayar_route_checks_the_shape_and_runs_the_worker_once(self):
        for data in ({}, None, {"x": 1}, {"username": "bad user"}, {"password": "short"}, {"password": ""},
                     {"save": 1}, {"save": "x" * 1025}):
            with self.subTest(data=data), self.assertRaises(panel.ApiError) as caught:
                self.api.handle(FakeRequest("POST", "/ayar", data))
            self.assertEqual(caught.exception.code, 400)
        self.assertEqual(self.ctx.worker_calls, [])
        self.ctx.worker_result = (200, {"ok": True, "username": "edited", "save": "/srv/media/"})
        req = FakeRequest("POST", "/ayar", {"username": "edited", "password": "dummy-edit-password", "save": "/srv/media"})
        self.assertEqual(self.api.handle(req), (200, {"ok": True, "username": "edited", "save": "/srv/media/"}))
        argv, data = self.ctx.worker_calls[0]
        self.assertEqual(argv[-1], "ayar")
        self.assertEqual(data["password"], "dummy-edit-password")
        self.assertEqual(req.audits, [("ayar", "kullanıcı adı, parola ve dizin /srv/media", True)])
        self.assertNotIn("dummy-edit-password", json.dumps(req.audits))

class DispatcherTests(Scratch):
    """The real backend over its Unix socket: gates, the package folder rule and the private worker run."""
    def setUp(self):
        super().setUp()
        # The state file carries no TORRENT_* key (DD-203); the package folder from Scratch does.
        self.state.write_text("".join(k + "=" + v + "\n" for k, v in self.env.items() if not k.startswith("TORRENT_")))
        (self.root / "bin").mkdir()
        (self.root / "bin" / "master-modul").write_text("#!/bin/sh\nexit 1\n")
        os.chmod(self.root / "bin" / "master-modul", 0o755)
        self.p = panel.Panel(types.SimpleNamespace(state=str(self.state), allow_host=[], state_env=False,
                                                   master_modul=str(self.root / "bin" / "master-modul")))
        self.addCleanup(lambda: [self.p.api_stop(mid, api) for mid, (_key, api) in list(self.p.apis.items())])

        class Handler(panel.Handler):
            def log_message(self, *_args):
                pass
        Handler.panel = self.p
        self.server, self.sock = resources.start_unix(self, Handler)
        self.runs = []

        def fake_subprocess(argv, **kwargs):
            self.runs.append((list(argv), kwargs.get("input")))
            if argv[0] == "systemd-run":
                return subprocess.CompletedProcess(argv, 0, '{"ok": true, "username": "u"}', "")
            return subprocess.CompletedProcess(argv, 3, b"", b"")
        patch.object(panel.subprocess, "run", side_effect=fake_subprocess).start()

    def request(self, method, path, data=None, headers=None):
        headers = {"X-Konsol": "1"} if headers is None else headers
        body = None if data is None else json.dumps(data).encode()
        if body is not None:
            headers = {"Content-Type": "application/json", **headers}
        status, _headers, raw = resources.unix_get(self.sock, path, headers, method, body)
        return status, json.loads(raw)

    def test_status_and_private_worker_run_through_the_dispatcher(self):
        self.assertEqual(self.request("GET", "/api/uygulama/torrent/durum", headers={})[0], 403)
        status, body = self.request("GET", "/api/uygulama/torrent/durum")
        self.assertEqual((status, body["installed"], body["running"], body["save"]), (200, True, False, self.env["DOWNLOADS_PATH"] + "/"))
        self.assertNotIn("oldhash", json.dumps(body))
        self.assertEqual(self.request("POST", "/api/uygulama/torrent/hesap", {"password": "short"})[0], 400)
        self.assertFalse([r for r in self.runs if r[0][0] == "systemd-run"], "a refused shape starts no worker")
        with patch("builtins.print") as out:
            status, body = self.request("POST", "/api/uygulama/torrent/hesap", {"password": "dummy-api-password"})
        self.assertEqual((status, body), (200, {"ok": True, "username": "u"}))
        argv, stdin = [r for r in self.runs if r[0][0] == "systemd-run"][0]
        self.assertEqual(argv[:5], ["systemd-run", "--quiet", "--wait", "--pipe", "--collect"])
        self.assertEqual(argv[-7:], ["/usr/bin/python3", str(self.root / "mods/torrent/ayar.py"), "--lib", str(self.root / "bin"), "--state", str(self.state), "hesap"])
        self.assertEqual(json.loads(stdin), {"password": "dummy-api-password"})
        self.assertNotIn("dummy-api-password", " ".join(argv))
        lines = [str(c.args[0]) for c in out.call_args_list if c.args]
        self.assertEqual([l for l in lines if "torrent:hesap" in l], ["panel: konsol yerel torrent:hesap parola -> ok"])
        self.assertFalse([l for l in lines if "dummy-api-password" in l])
        self.assertEqual(self.conf.read_text(), SEED % self.env["DOWNLOADS_PATH"], "the backend itself never writes the profile")
        (self.root / "modules").write_text("")
        self.assertEqual(self.request("GET", "/api/uygulama/torrent/durum")[0], 404)
        self.assertEqual(self.request("POST", "/api/uygulama/torrent/hesap", {"username": "x"})[0], 409)

    def test_worker_scripts_must_live_in_the_package_folder(self):
        ctx = panel.PackageContext(self.p, "torrent")
        outside = self.root / "elsewhere.py"
        outside.write_text("")
        code, body = ctx.worker(["/usr/bin/python3", str(outside), "--state", str(self.state), "hesap"], {})
        self.assertEqual(code, 400)
        self.assertIn("paket klasöründe değil", body["error"])
        link = self.root / "mods" / "torrent" / "link.py"
        link.symlink_to(outside)
        self.assertEqual(ctx.worker(["/usr/bin/python3", str(link), "x"], {})[0], 400)
        self.assertFalse([r for r in self.runs if r[0][0] == "systemd-run"])
        code, body = ctx.worker(["/usr/bin/python3", str(self.root / "mods/torrent/ayar.py"), "--state", str(self.state), "durum"], {"a": 1})
        self.assertEqual((code, body), (200, {"ok": True, "username": "u"}))


    def test_settings_of_a_stopped_app_read_and_save_without_starting_it(self):
        # DD-210: an installed but stopped qBittorrent (registry durduruldu) keeps its settings route: the
        # overview dialog reads /durum and saves /ayar through the worker; the backend starts nothing.
        (self.root / "modules").write_text("torrent\tdurduruldu\n")
        status, body = self.request("GET", "/api/uygulama/torrent/durum")
        self.assertEqual((status, body["installed"], body["running"], body["username"]), (200, True, False, "admin"))
        self.assertNotIn("oldhash", json.dumps(body))
        status, body = self.request("POST", "/api/uygulama/torrent/ayar", {"username": "stopped-edit", "password": "dummy-stopped-pass"})
        self.assertEqual(status, 200)
        workers = [r for r in self.runs if r[0][0] == "systemd-run"]
        self.assertEqual(len(workers), 1)
        self.assertEqual(workers[0][0][-1], "ayar")
        self.assertEqual(json.loads(workers[0][1]), {"username": "stopped-edit", "password": "dummy-stopped-pass"})
        self.assertNotIn("dummy-stopped-pass", " ".join(workers[0][0]))
        self.assertFalse([r for r in self.runs if r[0][:2] in (["systemctl", "start"], ["systemctl", "restart"])],
                         "the backend never starts a stopped app to change its settings")
        self.assertEqual((self.root / "modules").read_text(), "torrent\tdurduruldu\n")
        self.assertEqual([mid for mid, _api in self.p.package_apis()], [], "a stopped app is not given to background callers")
        (self.root / "modules").write_text("")
        self.assertEqual(self.request("GET", "/api/uygulama/torrent/durum")[0], 404)
        self.assertEqual(self.request("POST", "/api/uygulama/torrent/ayar", {"username": "x"})[0], 409)

class InstallRouteTests(Scratch):
    """DD-210: POST /api/konsol/moduller/<id>/kur with the form of a package that declares PAKET_KUR_AYAR.
    The base runs the package's worker first (stdin only); the engine starts only after it accepted."""
    def setUp(self):
        super().setUp()
        self.state.write_text("".join(k + "=" + v + "\n" for k, v in self.env.items() if not k.startswith("TORRENT_")))
        (self.root / "modules").write_text("")
        (self.root / "bin").mkdir()
        (self.root / "bin" / "master-modul").write_text("#!/bin/sh\nexit 1\n")
        os.chmod(self.root / "bin" / "master-modul", 0o755)
        (self.root / "mods" / "wireguard").mkdir()
        shutil.copy(REPO / "magaza" / "wireguard" / "paket.env", self.root / "mods" / "wireguard" / "paket.env")
        self.p = panel.Panel(types.SimpleNamespace(state=str(self.state), allow_host=[], state_env=False,
                                                   master_modul=str(self.root / "bin" / "master-modul")))
        self.items = [{"id": "wireguard", "installed": False}, {"id": "torrent", "installed": False}]
        patch.object(panel.Panel, "modules", side_effect=lambda: self.items).start()

        class Handler(panel.Handler):
            def log_message(self, *_args):
                pass
        Handler.panel = self.p
        self.server, self.sock = resources.start_unix(self, Handler)
        self.runs, self.worker_answer, self.spawn_code = [], (0, '{"ok": true, "username": "operator", "save": "/srv/downloads/"}'), 0

        def fake_subprocess(argv, **kwargs):
            self.runs.append((list(argv), kwargs.get("input")))
            if argv[0] == "systemd-run" and "--wait" in argv:
                return subprocess.CompletedProcess(argv, self.worker_answer[0], self.worker_answer[1], "")
            if argv[0] == "systemd-run":
                return subprocess.CompletedProcess(argv, self.spawn_code, b"", b"Unit already exists" if self.spawn_code else b"")
            return subprocess.CompletedProcess(argv, 0, b"", b"")
        patch.object(panel.subprocess, "run", side_effect=fake_subprocess).start()
        self.seed = self.root / "run" / "modul-torrent.kur"
        self.form = {"username": "operator", "password": "dummy-install-password", "save": self.env["DOWNLOADS_PATH"]}

    def request(self, path, data):
        body = json.dumps(data).encode()
        status, _headers, raw = resources.unix_get(self.sock, path, {"X-Konsol": "1", "Content-Type": "application/json"}, "POST", body)
        return status, json.loads(raw)

    def worker_runs(self):
        return [r for r in self.runs if r[0][0] == "systemd-run" and "--wait" in r[0]]

    def spawns(self):
        return [r for r in self.runs if r[0][0] == "systemd-run" and "--wait" not in r[0]]

    def test_the_form_is_required_validated_by_the_package_and_only_then_installed(self):
        status, body = self.request("/api/konsol/moduller/torrent/kur", {"veri": False})
        self.assertEqual(status, 400)
        self.assertIn("Kurulum bilgileri", body["error"])
        self.assertEqual(self.request("/api/konsol/moduller/torrent/kur", {"form": "x"})[0], 400)
        self.assertEqual((self.worker_runs(), self.spawns()), ([], []), "no form: no worker and no install")
        self.worker_answer = (1, '{"error": "Parola 8–256 karakter olmalı."}')
        status, body = self.request("/api/konsol/moduller/torrent/kur", {"form": dict(self.form, password="short")})
        self.assertEqual((status, body["error"]), (400, "Parola 8–256 karakter olmalı."))
        self.assertEqual(self.spawns(), [], "a refused form starts no install")
        self.worker_answer = (0, '{"ok": true, "username": "operator", "save": "/srv/downloads/"}')
        self.runs.clear()
        with patch("builtins.print") as out:
            status, body = self.request("/api/konsol/moduller/torrent/kur", {"form": self.form})
        self.assertEqual((status, body), (202, {"id": "torrent", "action": "kur"}))
        argv, stdin = self.worker_runs()[0]
        self.assertEqual(argv[-9:], ["/usr/bin/python3", str(self.pkg / "ayar.py"), "--lib", str(self.root / "bin"), "--state",
                                     str(self.state), "kur-hazirla", "--tohum", str(self.seed)])
        self.assertEqual(json.loads(stdin), self.form)
        spawn = self.spawns()[0][0]
        self.assertIn("--unit=master-modul-torrent.service", spawn)
        self.assertEqual(spawn[-2:], ["kur", "torrent"])
        self.assertLess(self.runs.index(self.worker_runs()[0]), self.runs.index(self.spawns()[0]), "validated before the engine starts")
        flat = json.dumps([r[0] for r in self.runs]) + json.dumps([str(c.args) for c in out.call_args_list])
        self.assertNotIn("dummy-install-password", flat, "the password travels on stdin only, never argv or audit")
        self.assertIn("modul-kur torrent -> ok", " ".join(str(c.args[0]) for c in out.call_args_list if c.args))

    def test_a_failed_start_removes_the_seed_and_an_installed_or_busy_package_is_refused_first(self):
        self.seed.write_text("{}")
        self.spawn_code = 1
        status, _body = self.request("/api/konsol/moduller/torrent/kur", {"form": self.form})
        self.assertEqual(status, 502)
        self.assertFalse(self.seed.exists(), "a seed whose install never started is removed")
        self.runs.clear()
        self.items[1]["installed"] = True
        status, body = self.request("/api/konsol/moduller/torrent/kur", {"form": self.form})
        self.assertEqual(status, 409)
        self.assertEqual(self.worker_runs(), [], "an installed package is refused before the worker")

    def test_a_package_without_an_install_form_refuses_one(self):
        status, _body = self.request("/api/konsol/moduller/wireguard/kur", {"form": self.form})
        self.assertEqual(status, 400)
        self.assertEqual(self.worker_runs(), [])
        status, _body = self.request("/api/konsol/moduller/wireguard/kur", {"veri": False})
        self.assertEqual(status, 202)
        self.assertEqual(self.worker_runs(), [])

if __name__ == "__main__":
    unittest.main()


class ImageUpdateTests(Scratch):
    """DD-214: the package moves its pinned image on explicit request; rollback restores every file."""
    REPO = "lscr.io/linuxserver/qbittorrent"
    OLD = REPO + "@sha256:" + "b5" * 32
    NEW = REPO + "@sha256:" + "11" * 32
    CHANNEL = REPO + ":latest"

    def setUp(self):
        super().setUp()
        self.env.update(PACKAGE_OVERRIDES_DIR=str(self.root / "overrides"), TORRENT_IMAGE_KANAL=self.CHANNEL, TORRENT_IMAGE=self.OLD)
        (self.root / "overrides").mkdir(mode=0o700)
        self.override = self.root / "overrides" / "torrent.env"
        self.override.write_text("TORRENT_UI_PORT=61016\n")
        self.override.chmod(0o600)
        quadlet = QUADLET % (61016, 61016)
        self.assertIn("Image=%s\n" % self.OLD, quadlet)
        self.rendered = self.pkg / "qbittorrent.container"
        self.rendered.write_text(quadlet)
        manifest = (PACKAGE / "paket.env").read_text().replace("__TORRENT_IMAGE__", self.OLD)
        (self.pkg / "paket.env").write_text(manifest)
        self.placed = self.root / "quadlet" / "qbittorrent.container"
        self.placed.write_text(quadlet)
        self.remote_digest = "sha256:" + "11" * 32
        self.local_digest = "sha256:" + "22" * 32
        self.files = [self.override, self.rendered, self.pkg / "paket.env", self.placed]

    def fake_run(self, argv, **kwargs):
        argv = list(argv)
        if argv[:1] != ["podman"]:
            return super().fake_run(argv, **kwargs)
        self.calls.append(argv)
        if self.fail_cmd and self.fail_cmd in " ".join(argv):
            self.fail_cmd = None
            raise settings.SettingsError("injected failure")
        out = ""
        if argv[:2] == ["podman", "info"]:
            out = "amd64\n"
        elif argv[:3] == ["podman", "image", "inspect"] and "--format" not in argv:
            out = json.dumps([{"Id": "a" * 64, "Digest": "sha256:" + "b5" * 32, "RepoDigests": [self.REPO + "@" + self.local_digest, self.OLD]}])
        elif argv[:3] == ["podman", "manifest", "inspect"]:
            out = json.dumps({"manifests": [{"digest": self.remote_digest, "platform": {"architecture": "amd64", "os": "linux"}}]})
        elif argv[:2] == ["podman", "inspect"]:
            out = self.NEW + "\n"
        elif argv[:3] == ["podman", "image", "inspect"]:
            fmt = argv[argv.index("--format") + 1]
            out = ("5.2.5_v2.0.15-ls480\n" if "version" in fmt else ("a" * 64 if argv[-1] == self.OLD else "c" * 64) + "\n")
        return subprocess.CompletedProcess(argv, 0, out, "")

    def podman(self):
        return [c[:3] for c in self.calls if c[0] == "podman"]

    def run_update(self):
        revision = ayar.container_config(self.env)["revision"]
        return ayar.konteyner_guncelle(self.env, {"revision": revision}, str(self.state))

    def test_an_up_to_date_channel_changes_nothing(self):
        self.local_digest = self.remote_digest
        before = [p.read_bytes() for p in self.files]
        result = self.run_update()
        self.assertEqual((result["ok"], result["changed"], result["image"]), (True, False, self.OLD))
        self.assertEqual([p.read_bytes() for p in self.files], before)
        self.assertNotIn(["podman", "pull", "-q"], self.podman())
        self.assertEqual(self.systemctl(), [])

    def test_update_pins_the_new_digest_everywhere_restarts_verifies_and_drops_the_old_image(self):
        result = self.run_update()
        self.assertEqual((result["changed"], result["image"], result["previous"], result["version"]), (True, self.NEW, self.OLD, "5.2.5_v2.0.15-ls480"))
        self.assertEqual(self.override.read_text(), "TORRENT_IMAGE=%s\nTORRENT_UI_PORT=61016\n" % self.NEW, "the port choice is kept")
        self.assertEqual(self.override.stat().st_mode & 0o777, 0o600)
        for path in (self.rendered, self.placed):
            self.assertIn("Image=%s\n" % self.NEW, path.read_text())
            self.assertNotIn(self.OLD, path.read_text())
        self.assertIn('PAKET_IMAJ="%s"\n' % self.NEW, (self.pkg / "paket.env").read_text())
        self.assertIn('PAKET_IMAJ_KANAL="__TORRENT_IMAGE_KANAL__"', (self.pkg / "paket.env").read_text(), "only the image line changes")
        pulls = [c for c in self.calls if c[:2] == ["podman", "pull"]]
        self.assertEqual(pulls, [["podman", "pull", "-q", self.NEW]], "the exact digest seen by the check is pulled")
        self.assertEqual(self.systemctl(), ["is-active", "daemon-reload", "restart", "is-active"])
        self.assertEqual(self.ui_waits, ["61006"])
        self.assertIn(["podman", "rmi", "a" * 64], self.calls, "the previous image is removed only after success")
        # Order: pull before any file is written or the service touched.
        first_write = min(i for i, c in enumerate(self.calls) if c[:1] == ["systemctl"])
        self.assertLess(self.calls.index(["podman", "pull", "-q", self.NEW]), first_write)

    def test_a_failed_restart_restores_every_file_and_the_previous_service(self):
        before = [p.read_bytes() for p in self.files]
        self.fail_cmd = "restart qbittorrent.service"
        with self.assertRaises(settings.SettingsError) as err:
            self.run_update()
        self.assertEqual(err.exception.status, 502)
        self.assertIn("önceki imaja dönüldü", str(err.exception))
        self.assertEqual([p.read_bytes() for p in self.files], before)
        self.assertEqual(self.systemctl(), ["is-active", "daemon-reload", "restart", "daemon-reload", "restart", "is-active"])
        self.assertNotIn(["podman", "rmi", "a" * 64], self.calls)

    def test_a_container_that_comes_up_with_another_image_is_rolled_back(self):
        before = [p.read_bytes() for p in self.files]
        original = self.fake_run

        def wrong(argv, **kwargs):
            if list(argv)[:2] == ["podman", "inspect"]:
                self.calls.append(list(argv))
                return subprocess.CompletedProcess(argv, 0, self.OLD + "\n", "")
            return original(argv, **kwargs)
        with patch.object(settings, "run", side_effect=wrong):
            with self.assertRaises(settings.SettingsError) as err:
                self.run_update()
        self.assertEqual(err.exception.status, 502)
        self.assertEqual([p.read_bytes() for p in self.files], before)

    def test_a_stopped_app_only_changes_the_files_its_next_start_uses(self):
        self.active = False
        self.placed.unlink()
        result = self.run_update()
        self.assertTrue(result["changed"])
        self.assertFalse(self.placed.exists(), "a stopped app's unit stays removed")
        self.assertIn("Image=%s\n" % self.NEW, self.rendered.read_text())
        self.assertEqual(self.systemctl(), ["is-active", "daemon-reload"])
        self.assertEqual(self.ui_waits, [])

    def test_stale_revision_missing_channel_and_unknown_image_line_change_nothing(self):
        before = [p.read_bytes() for p in self.files]
        with self.assertRaises(settings.SettingsError) as err:
            ayar.konteyner_guncelle(self.env, {"revision": "0" * 64}, str(self.state))
        self.assertEqual(err.exception.status, 409)
        revision = ayar.container_config(self.env)["revision"]
        with self.assertRaises(settings.SettingsError):
            ayar.konteyner_guncelle(dict(self.env, TORRENT_IMAGE_KANAL=""), {"revision": revision}, str(self.state))
        self.rendered.write_text("[Container]\nImage=elsewhere\n")
        with self.assertRaises(settings.SettingsError):
            ayar.konteyner_guncelle(self.env, {"revision": ayar.container_config(self.env)["revision"]}, str(self.state))
        self.rendered.write_bytes(before[1])
        self.assertEqual([p.read_bytes() for p in self.files], before)
        self.assertFalse([c for c in self.calls if c[:2] == ["podman", "pull"]])
