"""DD-250: Files' favourite folders in the root backend: KONSOL_AUTH_DIR/favoriler.json through
/api/konsol/favoriler, add/remove, the limit, path checks, a damaged record and the internet channel.
Temporary directories only."""
import contextlib
import io
import json

import test_resources
from test_overview import Fixture

panel = test_resources.panel


class FavoritesEndpointTests(Fixture):
    def setUp(self):
        super().setUp()

        class Handler(panel.Handler):
            def log_message(self, *_args):
                pass
        Handler.panel = self.p
        _server, self.sock = test_resources.start_unix(self, Handler)
        self.stored = self.root / "konsol" / panel.FAVORITES_FILE

    def call(self, body=None):
        headers = {"X-Konsol": "1"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        status, _, answer = test_resources.unix_get(self.sock, "/api/konsol/favoriler", headers,
                                                    method="POST" if body is not None else "GET",
                                                    body=json.dumps(body).encode() if body is not None else None)
        return status, json.loads(answer)

    def test_add_list_and_remove_in_order(self):
        self.assertEqual(self.call(), (200, {"favoriler": []}))
        media, nginx = {"yol": "media/Filmler 2026", "sistem": False}, {"yol": "etc/nginx", "sistem": True}
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            self.assertEqual(self.call({"ekle": media}), (200, {"favoriler": [media]}))
            self.assertEqual(self.call({"ekle": nginx}), (200, {"favoriler": [media, nginx]}))
            self.assertEqual(self.call({"ekle": media}), (200, {"favoriler": [nginx, media]}), "adding again moves it last, once")
        self.assertIn("favori + media/Filmler 2026 -> ok", printed.getvalue())
        self.assertIn("favori + /etc/nginx -> ok", printed.getvalue())
        self.assertEqual(oct(self.stored.stat().st_mode & 0o777), "0o600")
        self.assertEqual(json.loads(self.stored.read_text()), {"favoriler": [nginx, media]})
        self.assertEqual(self.call({"cikar": nginx}), (200, {"favoriler": [media]}))
        self.assertEqual(self.call({"cikar": nginx}), (200, {"favoriler": [media]}), "removing twice is fine")
        self.assertEqual(self.call({"cikar": media}), (200, {"favoriler": []}))
        self.assertFalse(self.stored.exists(), "an empty list leaves no file")

    def test_the_internet_channel_never_sees_or_changes_system_favourites(self):
        # The handler admits the internet channel only with a public name and a session (DD-195); the
        # channel rule itself lives in the Panel methods the handler calls with self.channel().
        media, nginx = {"yol": "media", "sistem": False}, {"yol": "etc/nginx", "sistem": True}
        self.call({"ekle": nginx})
        self.assertEqual(self.p.save_favorite({"ekle": media}, "internet"), ("+ media", [media]))
        self.assertEqual(self.p.favorites("internet"), [media])
        with self.assertRaises(PermissionError):
            self.p.save_favorite({"cikar": nginx}, "internet")
        self.assertEqual(self.call(), (200, {"favoriler": [nginx, media]}), "the system favourite is kept")

    def test_bad_requests_the_limit_and_a_damaged_record(self):
        bad = [{}, {"ekle": {"yol": "a"}}, {"ekle": {"yol": "a", "sistem": "evet"}}, {"ekle": {"yol": "", "sistem": False}},
               {"ekle": {"yol": "/etc", "sistem": True}}, {"ekle": {"yol": "a/../b", "sistem": False}},
               {"ekle": {"yol": "a//b", "sistem": False}}, {"ekle": {"yol": "a\nb", "sistem": False}},
               {"ekle": {"yol": "x" * 256, "sistem": False}}, {"ekle": {"yol": "/".join(["x" * 200] * 6), "sistem": False}},
               {"ekle": {"yol": "a", "sistem": False}, "cikar": {"yol": "a", "sistem": False}}, {"sil": {"yol": "a", "sistem": False}}]
        for body in bad:
            with self.subTest(body=str(body)[:60]):
                status, answer = self.call(body)
                self.assertEqual(status, 400)
                self.assertTrue(answer["error"])
        self.assertFalse(self.stored.exists())
        for i in range(panel.FAVORITES_MAX):
            self.assertEqual(self.call({"ekle": {"yol": "k%d" % i, "sistem": False}})[0], 200)
        status, answer = self.call({"ekle": {"yol": "fazla", "sistem": False}})
        self.assertEqual(status, 400)
        self.assertIn(str(panel.FAVORITES_MAX), answer["error"])
        self.stored.write_text("{")
        self.assertEqual(self.call(), (200, {"favoriler": []}), "a damaged record reads as no favourites")
        self.stored.write_text(json.dumps({"favoriler": [{"yol": "../x", "sistem": False}, {"yol": "ok", "sistem": False}, 5]}))
        self.assertEqual(self.call(), (200, {"favoriler": [{"yol": "ok", "sistem": False}]}), "only valid entries are listed")
        self.assertEqual(self.call({"ekle": {"yol": "yeni", "sistem": False}})[0], 200, "a save rewrites it cleanly")
        self.assertEqual(json.loads(self.stored.read_text()), {"favoriler": [{"yol": "ok", "sistem": False}, {"yol": "yeni", "sistem": False}]})

    def test_the_gates_stay_in_front(self):
        status, _, _ = test_resources.unix_get(self.sock, "/api/konsol/favoriler", {})
        self.assertEqual(status, 403, "X-Konsol is required")
        status, _, _ = test_resources.unix_get(self.sock, "/api/konsol/favoriler", {"X-Konsol": "1", "Host": "evil.test"})
        self.assertEqual(status, 403)
