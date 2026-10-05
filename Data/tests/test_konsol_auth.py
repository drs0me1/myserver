"""Konsol sign-in (DD-194, DD-205): account, sessions, limits and the root backend endpoints
that Caddy's forward_auth calls — the tailnet passes without a session, the internet signs in.
Temporary directories only; no host changes."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "panel"))
import master_auth as auth
import test_resources

panel = test_resources.panel
PASSWORD = "fixture-password-10"


class Clock:
    def __init__(self, now=2_000_000_000):
        self.now = now

    def __call__(self):
        return self.now


class StoreTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="konsol-auth-")
        self.addCleanup(temp.cleanup)
        self.dir = Path(temp.name) / "konsol"
        self.dir.mkdir(mode=0o700)
        self.clock = Clock()
        self.store = auth.Store(self.dir, clock=self.clock)
        auth.decoy()  # made once, outside the timing comparison below

    def setup_account(self, user="yonetici", password=PASSWORD):
        """DD-205: creating the account opens no session; tests that need one sign in."""
        self.store.create(user, password)
        return self.store.login(user, password)

    def test_account_is_created_once_without_a_code_and_stored_only_as_a_hash(self):
        self.assertEqual(self.store.status(None), {"durum": "kurulum"})
        self.assertIsNone(self.store.create("yonetici", PASSWORD))
        stored = (self.dir / auth.ACCOUNT_FILE).read_text()
        self.assertNotIn(PASSWORD, stored)
        self.assertEqual(oct((self.dir / auth.ACCOUNT_FILE).stat().st_mode & 0o777), "0o600")
        self.assertEqual(self.store.sessions(), {}, "no session is opened: the tailnet needs none")
        self.assertFalse((self.dir / "kurulum-kodu.json").exists(), "there is no setup code any more")
        # The name goes only to a trusted caller (the tailnet) while no session is open.
        self.assertEqual(self.store.status(None), {"durum": "giris"})
        self.assertEqual(self.store.status(None, reveal=True), {"durum": "giris", "kullanici": "yonetici"})
        with self.assertRaises(auth.AuthError) as err:
            self.store.create("ikinci", PASSWORD)
        self.assertEqual(err.exception.status, 409)
        self.assertEqual(self.store.account()["kullanici"], "yonetici")

    def test_user_and_password_rules_are_checked_before_anything_is_written(self):
        for user, password in (("ab", PASSWORD), ("-bad", PASSWORD), ("ok-user", "ninechars"),
                               ("ok-user", "x" * 257), ("ok-user", "tab\tpassword-10"), (None, PASSWORD)):
            with self.subTest(user=user, password=len(str(password))), self.assertRaises(auth.AuthError) as err:
                self.store.create(user, password)
            self.assertEqual(err.exception.status, 400)
        self.assertIsNone(self.store.account())
        self.assertEqual(self.store.status(None), {"durum": "kurulum"})

    def test_login_logout_and_status(self):
        first = self.setup_account()
        self.assertEqual(self.store.status(first)["durum"], "acik")
        self.assertEqual(self.store.status(None), {"durum": "giris"})
        token = self.store.login("yonetici", PASSWORD)
        self.assertNotEqual(token, first)
        for user, password in (("yonetici", PASSWORD + "x"), ("baskasi", PASSWORD), ("Yonetici", PASSWORD),
                               (None, PASSWORD), ("yonetici", None), ("yonetici", "x" * 300)):
            with self.subTest(user=user), self.assertRaises(auth.AuthError) as err:
                self.store.login(user, password)
            self.assertEqual((err.exception.status, str(err.exception)), (401, auth.BAD_LOGIN))
        self.store.logout(token)
        self.assertIsNone(self.store.user_for(token))
        self.assertEqual(self.store.user_for(first), "yonetici")

    def test_wrong_user_costs_the_same_hash_as_a_wrong_password(self):
        self.setup_account()
        calls = []
        original = auth.digest

        def counted(secret, salt):
            calls.append(salt)
            return original(secret, salt)

        with patch.object(auth, "digest", counted):
            for user in ("yonetici", "baskasi"):
                calls.clear()
                with self.assertRaises(auth.AuthError):
                    self.store.login(user, "wrong-password-1")
                self.assertEqual(len(calls), 1, user)

    def test_sessions_expire_are_bounded_and_ignore_malformed_tokens(self):
        token = self.setup_account()
        self.clock.now += auth.SESSION_SECONDS - 1
        self.assertEqual(self.store.user_for(token), "yonetici")
        self.clock.now += 1
        self.assertIsNone(self.store.user_for(token))
        for bad in (None, "", "x" * 43 + "!", "a" * 44, 5, "../" * 15):
            self.assertIsNone(self.store.user_for(bad))
        tokens = []
        for _ in range(auth.MAX_SESSIONS + 4):
            self.clock.now += 1
            tokens.append(self.store.login("yonetici", PASSWORD))
        self.assertEqual(len(self.store.sessions()), auth.MAX_SESSIONS)
        self.assertIsNone(self.store.user_for(tokens[0]))
        self.assertEqual(self.store.user_for(tokens[-1]), "yonetici")
        stored = (self.dir / auth.SESSIONS_FILE).read_text()
        self.assertFalse(any(t in stored for t in tokens))

    def test_password_change_keeps_this_browser_and_closes_the_others(self):
        mine = self.setup_account()
        other = self.store.login("yonetici", PASSWORD)
        for old, new, status in (("wrong-old-password", "new-password-123", 401),
                                 (PASSWORD, PASSWORD, 400), (PASSWORD, "short", 400)):
            with self.subTest(new=new), self.assertRaises(auth.AuthError) as err:
                self.store.change_password(mine, old, new)
            self.assertEqual(err.exception.status, status)
        with self.assertRaises(auth.AuthError) as err:
            self.store.change_password("x" * 43, PASSWORD, "new-password-123")
        self.assertEqual(err.exception.status, 401)
        self.store.change_password(mine, PASSWORD, "new-password-123")
        self.assertEqual(self.store.user_for(mine), "yonetici")
        self.assertIsNone(self.store.user_for(other))
        with self.assertRaises(auth.AuthError):
            self.store.login("yonetici", PASSWORD)
        self.assertTrue(self.store.login("yonetici", "new-password-123"))

    def test_set_password_asks_no_current_password_and_ends_every_session(self):
        # DD-205: from the tailnet the device is the credential; internet browsers sign in again.
        mine = self.setup_account()
        other = self.store.login("yonetici", PASSWORD)
        for bad in ("short", "x" * 257, None):
            with self.subTest(new=bad), self.assertRaises(auth.AuthError) as err:
                self.store.set_password(bad)
            self.assertEqual(err.exception.status, 400)
        self.assertEqual(self.store.user_for(mine), "yonetici")
        self.store.set_password("new-password-123")
        self.assertIsNone(self.store.user_for(mine))
        self.assertIsNone(self.store.user_for(other))
        with self.assertRaises(auth.AuthError):
            self.store.login("yonetici", PASSWORD)
        self.assertTrue(self.store.login("yonetici", "new-password-123"))
        self.store.reset()
        with self.assertRaises(auth.AuthError) as err:
            self.store.set_password("new-password-123")
        self.assertEqual((err.exception.status, str(err.exception)), (409, auth.NO_ACCOUNT))

    def test_reset_removes_account_and_sessions(self):
        token = self.setup_account()
        self.assertIsNone(self.store.reset())
        self.assertIsNone(self.store.account())
        self.assertIsNone(self.store.user_for(token))
        self.assertEqual(self.store.status(None), {"durum": "kurulum"})
        with self.assertRaises(auth.AuthError) as err:
            self.store.login("yonetici", PASSWORD)
        self.assertEqual((err.exception.status, str(err.exception)), (409, auth.NO_ACCOUNT))
        self.store.create("yeni-yonetici", PASSWORD)
        self.assertEqual(self.store.user_for(self.store.login("yeni-yonetici", PASSWORD)), "yeni-yonetici")

    def test_automation_session_is_short_and_works_before_the_first_sign_in(self):
        for seconds in (59, auth.AUTOMATION_MAX_SECONDS + 1, "600"):
            with self.assertRaises(auth.AuthError):
                self.store.automation_session(seconds)
        token = self.store.automation_session(600)
        self.assertEqual(self.store.user_for(token), "otomasyon")
        self.assertEqual(self.store.status(token)["durum"], "kurulum")
        self.clock.now += 600
        self.assertIsNone(self.store.user_for(token))

    def test_unsafe_directory_or_records_fail_closed_without_blocking(self):
        self.setup_account()
        account = self.dir / auth.ACCOUNT_FILE
        saved = account.read_bytes()
        cases = [("symlink", lambda: (account.unlink(), account.symlink_to(self.dir / auth.SESSIONS_FILE))),
                 ("fifo", lambda: (account.unlink(), os.mkfifo(account))),
                 ("oversized", lambda: account.write_bytes(b" " * (auth.FILE_LIMIT + 1))),
                 ("corrupt", lambda: account.write_text("{")),
                 ("shape", lambda: account.write_text(json.dumps({"schema": 1, "kullanici": "x"})))]
        for name, damage in cases:
            with self.subTest(name=name):
                damage()
                with self.assertRaises(auth.AuthError) as err:
                    self.store.account()
                self.assertEqual(err.exception.status, 503)
                account.unlink()
                account.write_bytes(saved)
        self.dir.chmod(0o755)
        with self.assertRaises(auth.AuthError) as err:
            self.store.account()
        self.assertEqual(err.exception.status, 503)
        self.dir.chmod(0o700)
        missing = auth.Store(self.dir / "yok")
        with self.assertRaises(auth.AuthError) as err:
            missing.status(None)
        self.assertEqual(err.exception.status, 503)


class AttemptTests(unittest.TestCase):
    def test_five_failures_close_an_address_for_five_minutes_only(self):
        clock = Clock(1000)
        attempts = auth.Attempts(clock=clock)
        for _ in range(auth.FAILURES - 1):
            attempts.check("100.64.0.9")
            attempts.failed("100.64.0.9")
        attempts.check("100.64.0.9")
        attempts.failed("100.64.0.9")
        with self.assertRaises(auth.AuthError) as err:
            attempts.check("100.64.0.9")
        self.assertEqual((err.exception.status, err.exception.retry_after), (429, auth.BLOCK_SECONDS))
        attempts.check("100.64.0.10")
        clock.now += auth.BLOCK_SECONDS
        attempts.check("100.64.0.9")

    def test_failures_outside_the_window_are_forgotten_and_the_table_is_bounded(self):
        clock = Clock(1000)
        attempts = auth.Attempts(clock=clock)
        for _ in range(auth.FAILURES - 1):
            attempts.failed("a")
        clock.now += auth.WINDOW_SECONDS
        attempts.failed("a")
        attempts.check("a")
        with patch.object(auth, "MAX_ENTRIES", 2):
            attempts.failed("b")
            with self.assertRaises(auth.AuthError) as err:
                attempts.check("c")
            self.assertEqual(err.exception.status, 429)


    def test_public_failures_share_one_budget_that_never_closes_tailscale(self):
        # DD-195: many addresses cannot multiply the per-address limit on the public site.
        clock = Clock(1000)
        attempts = auth.Attempts(clock=clock)
        for i in range(auth.PUBLIC_FAILURES - 1):
            attempts.failed("203.0.113.%d" % i, public=True)
        clock.now += auth.PUBLIC_WINDOW_SECONDS
        attempts.failed("198.51.100.1", public=True)
        attempts.check("198.51.100.2", public=True)  # the old failures left the window
        for i in range(auth.PUBLIC_FAILURES - 1):
            attempts.failed("192.0.2.%d" % i, public=True)
        with self.assertRaises(auth.AuthError) as err:
            attempts.check("198.51.100.3", public=True)
        self.assertEqual((err.exception.status, err.exception.retry_after), (429, auth.PUBLIC_BLOCK_SECONDS))
        self.assertIn("Tailscale üzerinden giriş açık", str(err.exception))
        attempts.check("100.64.0.9")  # tailnet sign-in is never counted or closed
        attempts.failed("100.64.0.9")
        clock.now += auth.PUBLIC_BLOCK_SECONDS
        attempts.check("198.51.100.3", public=True)

    def test_one_check_per_address_and_two_password_checks_at_once(self):
        attempts = auth.Attempts()
        with attempts.attempt("a"):
            with self.assertRaises(auth.AuthError) as err:
                with attempts.attempt("a"):
                    pass
            self.assertEqual(err.exception.status, 429)
            with attempts.attempt("b"), patch.object(auth, "HASH_WAIT_SECONDS", 0.01):
                with self.assertRaises(auth.AuthError) as err:
                    with attempts.attempt("c"):
                        pass
                self.assertIn("meşgul", str(err.exception))
        with attempts.attempt("a"), attempts.attempt("c"):
            pass
        self.assertEqual(attempts.inflight, set())


class CliTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="konsol-cli-")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / "konsol").mkdir(mode=0o700)
        self.state = root / "state.env"
        self.state.write_text("KONSOL_AUTH_DIR=%s\nLOCAL_DOMAIN=ev\n" % (root / "konsol"))
        self.store = auth.Store(root / "konsol")

    def run_cli(self, *argv, stdin="", root=True):
        out, err = io.StringIO(), io.StringIO()
        code = 0
        with patch.object(sys, "argv", ["master-konsol", "--state", str(self.state), *argv]), \
                patch.object(auth.os, "geteuid", return_value=0 if root else 1000), \
                patch.object(sys, "stdin", io.StringIO(stdin)), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                auth.main()
            except SystemExit as exc:
                code = exc.code or 0
        return code, out.getvalue(), err.getvalue()

    def test_root_commands(self):
        self.assertEqual(self.run_cli("durum", root=False)[0], 1)
        with patch.object(auth.Store, "check_dir", return_value=None):
            code, out, _ = self.run_cli("durum")
            self.assertEqual((code, out.strip()), (0, auth.NO_ACCOUNT))
            self.assertEqual(self.run_cli("kod")[0], 2, "the setup-code verb is gone (DD-205)")
            self.store.create("yonetici", PASSWORD)
            self.assertIn("Konsol hesabı: yonetici", self.run_cli("durum")[1])
            code, token, _ = self.run_cli("oturum-ac", "--sure", "300")
            self.assertEqual(self.store.user_for(token.strip()), "yonetici")
            self.assertEqual(self.run_cli("oturum-kapat", stdin=token)[0], 0)
            self.assertIsNone(self.store.user_for(token.strip()))
            self.assertEqual(self.run_cli("oturum-ac", "--sure", "7200")[0], 1)
            code, out, _ = self.run_cli("sifirla")
            self.assertEqual(code, 0)
            self.assertIn("http://panel.ev", out)
            self.assertIn("Ayarlar → Sistem", out)
            self.assertNotRegex(out, r"[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}")
            self.assertIsNone(self.store.account())
            self.assertEqual(self.run_cli("durum")[1].strip(), auth.NO_ACCOUNT)


class PanelEndpointTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="konsol-panel-")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name).resolve()
        (root / "konsol").mkdir(mode=0o700)
        (root / "modules").write_text("")
        state = root / "state.env"
        state.write_text("SERVER_ROOT=%s\nLOCAL_DOMAIN=test\nV2_VERSION=test\nMODULES_FILE=%s\nKONSOL_AUTH_DIR=%s\n"
                         % (root, root / "modules", root / "konsol"))
        self.p = panel.Panel(types.SimpleNamespace(state=str(state), allow_host=[]))
        self.store = auth.Store(root / "konsol")

        class Handler(panel.Handler):
            def log_message(self, *_args):
                pass
        Handler.panel = self.p
        _server, self.sock = test_resources.start_unix(self, Handler)

    def call(self, path, headers=None, method="GET", body=None):
        headers = dict(headers or {})
        if body is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(body).encode()
        return test_resources.unix_get(self.sock, path, headers, method=method, body=body)

    def post(self, path, body, cookie=None, client="100.64.0.9"):
        headers = {"X-Konsol": "1", "X-Forwarded-For": client}
        if cookie:
            headers["Cookie"] = cookie
        return self.call(path, headers, "POST", body)

    @staticmethod
    def cookie(headers):
        return headers["Set-Cookie"].split(";", 1)[0]

    def gate(self, uri, cookie=None):
        """forward_auth as the tailnet site sends it: Caddy's X-Forwarded-For names another device."""
        headers = {"X-Forwarded-For": "100.64.0.9", "X-Forwarded-Uri": uri}
        if cookie:
            headers["Cookie"] = "theme=dark; " + cookie
        return self.call("/oturum-denetle", headers)

    def local(self, uri, cookie=None):
        """forward_auth without Caddy's forwarding headers (a direct socket caller): a session is required."""
        headers = {"X-Forwarded-Uri": uri}
        if cookie:
            headers["Cookie"] = "theme=dark; " + cookie
        return self.call("/oturum-denetle", headers)

    def test_forward_auth_passes_the_tailnet_without_a_session_and_needs_one_elsewhere(self):
        # DD-205: another Tailscale device needs no sign-in; its sign-in page goes back to Konsol.
        self.assertEqual(self.gate("/#/ayarlar")[0], 204)
        self.assertEqual(self.gate("/api/konsol/kaynaklar?yenile=1")[0], 204)
        status, headers, _ = self.gate("/giris.html")
        self.assertEqual((status, headers["Location"]), (302, "/"))
        self.assertEqual(self.gate("/giris.html?x=1")[0], 302)
        # Without Caddy's forwarding headers a session is required, except for the sign-in page itself.
        status, headers, _ = self.local("/#/ayarlar")
        self.assertEqual((status, headers["Location"]), (302, "/giris.html"))
        status, _, body = self.local("/api/konsol/kaynaklar?yenile=1")
        self.assertEqual((status, json.loads(body)["giris"]), (401, True))
        self.assertEqual(self.local("/giris.html")[0], 204)
        # Host-local callers through Caddy stay refused (DD-180) before any session check.
        status, _, body = self.call("/oturum-denetle", {"X-Forwarded-For": "127.0.0.1", "X-Forwarded-Uri": "/"})
        self.assertEqual(status, 403)
        self.assertEqual(self.call("/oturum-denetle", {"Host": "evil.test", "X-Forwarded-Uri": "/"})[0], 403)
        # The account is created from the tailnet: no code, no session cookie.
        status, headers, body = self.post("/api/konsol/oturum/kur", {"kullanici": "yonetici", "parola": PASSWORD})
        self.assertEqual((status, json.loads(body)), (200, {"durum": "kuruldu"}))
        self.assertNotIn("Set-Cookie", headers)
        self.assertEqual(self.post("/api/konsol/oturum/kur", {"kullanici": "ikinci", "parola": PASSWORD})[0], 409)
        # The tailnet sees the account name without a session; a sign-in still works and sets the cookie.
        status, _, body = self.call("/api/konsol/oturum", {"X-Konsol": "1", "X-Forwarded-For": "100.64.0.9"})
        self.assertEqual(json.loads(body), {"durum": "giris", "kullanici": "yonetici", "kanal": "tailscale"})
        status, headers, _ = self.post("/api/konsol/oturum/giris", {"kullanici": "yonetici", "parola": PASSWORD})
        self.assertEqual(status, 200)
        attributes = [part.strip() for part in headers["Set-Cookie"].split(";")]
        self.assertEqual(attributes[1:], ["Path=/", "HttpOnly", "SameSite=Strict", "Max-Age=%d" % auth.SESSION_SECONDS])
        self.assertEqual(self.local("/api/konsol/kaynaklar", self.cookie(headers))[0], 204)
        self.assertEqual(self.local("/", self.cookie(headers))[0], 204)
        status, _, body = self.call("/api/konsol/oturum", {"X-Konsol": "1", "Cookie": self.cookie(headers)})
        self.assertEqual(json.loads(body)["kullanici"], "yonetici")
        self.assertEqual(self.call("/api/konsol/oturum", {})[0], 403, "the status API keeps the X-Konsol gate")

    def test_sign_in_failures_are_limited_and_never_logged_with_secrets(self):
        self.store.create("yonetici", PASSWORD)
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            for _ in range(auth.FAILURES):
                self.assertEqual(self.post("/api/konsol/oturum/giris",
                                           {"kullanici": "yonetici", "parola": "wrong-password-x"})[0], 401)
            status, headers, body = self.post("/api/konsol/oturum/giris", {"kullanici": "yonetici", "parola": PASSWORD})
            self.assertEqual((status, headers["Retry-After"]), (429, str(auth.BLOCK_SECONDS)))
            self.assertIn("saniye sonra", json.loads(body)["error"])
            status, headers, _ = self.post("/api/konsol/oturum/giris", {"kullanici": "yonetici", "parola": PASSWORD},
                                           client="100.64.0.10")
            self.assertEqual(status, 200)
        log = printed.getvalue()
        self.assertIn("giris - -> hata", log)
        self.assertNotIn("wrong-password-x", log)
        self.assertNotIn(PASSWORD, log)
        self.assertNotIn("yonetici", log)

    def test_logout_and_password_change_endpoints(self):
        self.store.create("yonetici", PASSWORD)
        _, first, _ = self.post("/api/konsol/oturum/giris", {"kullanici": "yonetici", "parola": PASSWORD})
        _, second, _ = self.post("/api/konsol/oturum/giris", {"kullanici": "yonetici", "parola": PASSWORD})
        mine, other = self.cookie(first), self.cookie(second)
        # DD-205, tailnet: no current password and no session; every session ends.
        self.assertEqual(self.post("/api/konsol/hesap/parola", {"yeni": "short"})[0], 400)
        status, headers, body = self.post("/api/konsol/hesap/parola", {"yeni": "new-password-123"})
        self.assertEqual((status, json.loads(body)), (200, {"durum": "degisti"}))
        self.assertNotIn("Set-Cookie", headers)
        self.assertEqual(self.local("/", mine)[0], 302)
        self.assertEqual(self.local("/", other)[0], 302)
        self.assertEqual(self.post("/api/konsol/oturum/giris", {"kullanici": "yonetici", "parola": PASSWORD})[0], 401)
        _, third, _ = self.post("/api/konsol/oturum/giris", {"kullanici": "yonetici", "parola": "new-password-123"})
        mine = self.cookie(third)
        # Internet: the current password and this browser's session are required; the other sessions end.
        with patch.object(self.p, "public_open", return_value=True):
            _, fourth, _ = self.public("/api/konsol/oturum/giris", body={"kullanici": "yonetici", "parola": "new-password-123"})
            other = self.cookie(fourth)
            self.assertEqual(self.public("/api/konsol/hesap/parola", other, body={"yeni": "new-password-456"})[0], 401)
            self.assertEqual(self.public("/api/konsol/hesap/parola", other,
                                         body={"eski": "wrong-old-password", "yeni": "new-password-456"})[0], 401)
            self.assertEqual(self.public("/api/konsol/hesap/parola",
                                         body={"eski": "new-password-123", "yeni": "new-password-456"})[0], 401)
            status, headers, body = self.public("/api/konsol/hesap/parola", other,
                                                body={"eski": "new-password-123", "yeni": "new-password-456"})
            self.assertEqual((status, json.loads(body)), (200, {"durum": "degisti"}))
            self.assertNotIn("Set-Cookie", headers)
            self.assertEqual(self.public("/oturum-denetle", other, uri="/")[0], 204)
            self.assertEqual(self.local("/", mine)[0], 302)
            status, headers, _ = self.public("/api/konsol/oturum/cikis", other, body={})
            self.assertEqual(status, 200)
            self.assertTrue(headers["Set-Cookie"].startswith("konsol_oturum=; "))
            self.assertIn("Max-Age=0", headers["Set-Cookie"])
            self.assertEqual(self.public("/oturum-denetle", other, uri="/api/x")[0], 401)

    def public(self, path, cookie=None, client="203.0.113.7", body=None, uri=None):
        # Headers exactly as the public Caddy site writes them (DD-195).
        headers = {"X-Forwarded-For": client, "X-Konsol-Kanal": "internet", "X-Forwarded-Proto": "https", "X-Konsol": "1"}
        if uri is not None:
            headers["X-Forwarded-Uri"] = uri
        if cookie:
            headers["Cookie"] = cookie
        return self.call(path, headers, "POST" if body is not None else "GET", body)

    def test_public_channel_needs_the_publication_and_signs_in_with_a_secure_cookie(self):
        # Closed publication: every public request is refused before any session check.
        status, _, body = self.public("/oturum-denetle", uri="/")
        self.assertEqual((status, json.loads(body)["error"]), (403, "Konsol'un internet yayını kapalı"))
        with patch.object(self.p, "public_open", return_value=True):
            # The account is never created from the internet (DD-195/DD-205).
            status, _, body = self.public("/api/konsol/oturum/kur", body={"kullanici": "yonetici", "parola": PASSWORD})
            self.assertEqual(status, 403)
            self.assertIn("Tailscale", json.loads(body)["error"])
            self.assertIsNone(self.store.account())
            status, _, body = self.public("/api/konsol/oturum")
            self.assertEqual(json.loads(body), {"durum": "kurulum", "kanal": "internet"})
            self.assertEqual(self.post("/api/konsol/oturum/kur", {"kullanici": "yonetici", "parola": PASSWORD})[0], 200)
            self.assertEqual(self.public("/oturum-denetle", uri="/")[0], 302)
            self.assertEqual(self.public("/oturum-denetle", uri="/giris.html")[0], 204, "the sign-in page is open on the internet site")
            self.assertEqual(self.public("/oturum-denetle", uri="/api/konsol/kaynaklar")[0], 401)
            # An anonymous internet visitor never learns the account name (DD-205).
            status, _, body = self.public("/api/konsol/oturum")
            self.assertEqual(json.loads(body), {"durum": "giris", "kanal": "internet"})
            status, headers, _ = self.public("/api/konsol/oturum/giris", body={"kullanici": "yonetici", "parola": PASSWORD})
            self.assertEqual(status, 200)
            self.assertEqual([part.strip() for part in headers["Set-Cookie"].split(";")][1:],
                             ["Path=/", "HttpOnly", "SameSite=Strict", "Max-Age=%d" % auth.SESSION_SECONDS, "Secure"])
            cookie = self.cookie(headers)
            self.assertEqual(self.public("/oturum-denetle", cookie, uri="/api/konsol/kaynaklar")[0], 204)
            status, _, body = self.public("/api/konsol/oturum", cookie)
            self.assertEqual((json.loads(body)["kanal"], json.loads(body)["durum"]), ("internet", "acik"))
            # A program on this server cannot use the public door either (DD-180).
            self.assertEqual(self.public("/oturum-denetle", cookie, client="127.0.0.1", uri="/")[0], 403)
            # Without Caddy's internet mark, a non-tailnet client is still refused.
            self.assertEqual(self.call("/oturum-denetle", {"X-Forwarded-For": "203.0.113.7", "X-Forwarded-Uri": "/",
                                                           "Cookie": cookie})[0], 403)
            self.assertEqual(self.call("/oturum-denetle", {"X-Forwarded-For": "203.0.113.7", "X-Forwarded-Uri": "/",
                                                           "X-Konsol-Kanal": "tailscale", "Cookie": cookie})[0], 403)
            status, _, body = self.call("/api/konsol/oturum", {"X-Konsol": "1", "X-Forwarded-For": "100.64.0.9",
                                                               "X-Konsol-Kanal": "tailscale"})
            self.assertEqual(json.loads(body), {"durum": "giris", "kullanici": "yonetici", "kanal": "tailscale"})
        # Closing the publication closes even a signed-in public browser.
        self.assertEqual(self.public("/oturum-denetle", cookie, uri="/")[0], 403)
        # Tailnet sign-ins carry no Secure flag (plain HTTP inside Tailscale).
        status, headers, _ = self.post("/api/konsol/oturum/giris", {"kullanici": "yonetici", "parola": PASSWORD})
        self.assertNotIn("Secure", headers["Set-Cookie"])

    def test_public_failures_count_in_the_shared_budget(self):
        self.store.create("yonetici", PASSWORD)
        printed = io.StringIO()
        with patch.object(self.p, "public_open", return_value=True), patch.object(auth, "PUBLIC_FAILURES", 3), \
                contextlib.redirect_stdout(printed):
            for i in range(3):
                self.assertEqual(self.public("/api/konsol/oturum/giris", client="203.0.113.%d" % i,
                                             body={"kullanici": "yonetici", "parola": "wrong-password-x"})[0], 401)
            status, headers, body = self.public("/api/konsol/oturum/giris", client="198.51.100.9",
                                                body={"kullanici": "yonetici", "parola": PASSWORD})
            self.assertEqual((status, headers["Retry-After"]), (429, str(auth.PUBLIC_BLOCK_SECONDS)))
            self.assertEqual(self.post("/api/konsol/oturum/giris", {"kullanici": "yonetici", "parola": PASSWORD})[0], 200)

    def test_publication_state_is_cached_for_a_few_seconds(self):
        with patch.object(panel.master_publications, "panel_active", return_value=True) as active, \
                patch.object(panel.time, "monotonic", side_effect=[100.0, 101.0, 100.0 + panel.PUBLIC_CACHE_SECONDS]):
            self.assertTrue(self.p.public_open())
            self.assertTrue(self.p.public_open())
            active.return_value = False
            self.assertFalse(self.p.public_open())
        self.assertEqual(active.call_count, 2)

    def test_missing_account_directory_setting_is_a_controlled_error(self):
        with patch.object(panel, "read_env", return_value={"LOCAL_DOMAIN": "test"}):
            status, _, body = self.local("/")
        self.assertEqual(status, 503)
        self.assertIn("kurulumu yeniden", json.loads(body)["error"])


if __name__ == "__main__":
    unittest.main()
