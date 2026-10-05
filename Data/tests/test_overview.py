"""Overview layout and network card (DD-206): the root backend's layout store and endpoints, the
WAN rate sampler, /api/konsol/ag with package traffic modules, and both packages' trafik.py.
Temporary directories only; no host changes."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "panel"))
import master_auth as auth
import test_resources

panel = test_resources.panel


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Fixture(unittest.TestCase):
    """A Panel on a temporary state: account folder, package folder and registry, WAN interface."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="konsol-overview-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        (self.root / "konsol").mkdir(mode=0o700)
        (self.root / "moduller").mkdir()
        self.registry = self.root / "registry"
        self.registry.write_text("")
        self.state = self.root / "state.env"
        self.state.write_text("SERVER_ROOT=%s\nLOCAL_DOMAIN=test\nV2_VERSION=test\nMODULES_FILE=%s\nMODULES_DIR=%s\n"
                              "KONSOL_AUTH_DIR=%s\nWAN_INTERFACE=eth0\n"
                              % (self.root, self.registry, self.root / "moduller", self.root / "konsol"))
        self.p = panel.Panel(types.SimpleNamespace(state=str(self.state), allow_host=[]))

    def package(self, mid, module_source=None, manifest_extra='PAKET_TRAFIK="trafik.py"\n', state="calisiyor"):
        folder = self.root / "moduller" / mid
        folder.mkdir()
        (folder / "paket.env").write_text('PAKET_AD="Deneme %s"\n%s' % (mid, manifest_extra))
        if module_source is not None:
            (folder / "trafik.py").write_text(module_source)
        if state:
            with self.registry.open("a") as fh:
                fh.write("%s\t%s\n" % (mid, state))
        return folder


class LayoutTests(unittest.TestCase):
    def test_clean_layout_accepts_the_shape_and_refuses_anything_else(self):
        good = {"kareler": ["dosyalar", "ayarlar"], "widgetlar": [{"id": "saat", "genislik": 1, "gizli": False}]}
        self.assertEqual(panel.clean_layout(good), dict(good, schema=1))
        self.assertEqual(panel.clean_layout({}), {"schema": 1, "kareler": [], "widgetlar": []})
        bad = [None, [], {"x": 1}, {"schema": 2}, {"kareler": "dosyalar"}, {"kareler": ["Dosyalar"]}, {"kareler": ["a"]},
               {"kareler": ["dosyalar", "dosyalar"]}, {"kareler": ["k%02d" % i for i in range(panel.LAYOUT_MAX_TILES + 1)]},
               {"kareler": [1]}, {"widgetlar": {}}, {"widgetlar": [{"id": "saat", "genislik": 5, "gizli": False}]},
               {"widgetlar": [{"id": "saat", "genislik": 0, "gizli": False}]}, {"widgetlar": [{"id": "saat", "genislik": True, "gizli": False}]},
               {"widgetlar": [{"id": "saat", "genislik": 2, "gizli": 0}]}, {"widgetlar": [{"id": "saat", "genislik": 2}]},
               {"widgetlar": [{"id": "saat", "genislik": 2, "gizli": False, "yukseklik": 2}]},
               {"widgetlar": [{"id": "saat", "genislik": 2, "gizli": False}, {"id": "saat", "genislik": 1, "gizli": False}]},
               {"widgetlar": [{"id": "../x", "genislik": 2, "gizli": False}]}]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                panel.clean_layout(value)


class LayoutEndpointTests(Fixture):
    def setUp(self):
        super().setUp()

        class Handler(panel.Handler):
            def log_message(self, *_args):
                pass
        Handler.panel = self.p
        _server, self.sock = test_resources.start_unix(self, Handler)

    def call(self, path, body=None):
        headers = {"X-Konsol": "1"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        return test_resources.unix_get(self.sock, path, headers, method="POST" if body is not None else "GET",
                                       body=json.dumps(body).encode() if body is not None else None)

    def test_layout_is_saved_read_back_and_reset_by_the_root_backend(self):
        self.assertEqual(json.loads(self.call("/api/konsol/duzen")[2]), {"duzen": None})
        layout = {"kareler": ["ayarlar", "dosyalar"], "widgetlar": [{"id": "ag", "genislik": 4, "gizli": True}]}
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            status, _, body = self.call("/api/konsol/duzen", {"duzen": layout})
        self.assertEqual((status, json.loads(body)), (200, {"duzen": dict(layout, schema=1)}))
        stored = self.root / "konsol" / panel.LAYOUT_FILE
        self.assertEqual(oct(stored.stat().st_mode & 0o777), "0o600")
        self.assertEqual(json.loads(stored.read_text()), dict(layout, schema=1))
        self.assertEqual(json.loads(self.call("/api/konsol/duzen")[2]), {"duzen": dict(layout, schema=1)})
        self.assertIn("duzen kaydet -> ok", printed.getvalue())
        # The account records are untouched by a layout save.
        self.assertEqual(sorted(p.name for p in (self.root / "konsol").iterdir() if not p.name.startswith(".")), [panel.LAYOUT_FILE])
        with contextlib.redirect_stdout(printed):
            status, _, body = self.call("/api/konsol/duzen", {"sifirla": True})
        self.assertEqual((status, json.loads(body)), (200, {"duzen": None}))
        self.assertFalse(stored.exists())
        self.assertIn("duzen sifirla -> ok", printed.getvalue())
        self.assertEqual(self.call("/api/konsol/duzen", {"sifirla": True})[0], 200, "resetting twice is fine")

    def test_bad_requests_and_a_damaged_record(self):
        for body in ({}, {"duzen": {"kareler": ["X"]}}, {"duzen": {}, "sifirla": True}, {"sifirla": False}, {"duzen": []}):
            with self.subTest(body=body):
                status, _, answer = self.call("/api/konsol/duzen", body)
                self.assertEqual(status, 400)
                self.assertTrue(json.loads(answer)["error"])
        self.assertFalse((self.root / "konsol" / panel.LAYOUT_FILE).exists())
        (self.root / "konsol" / panel.LAYOUT_FILE).write_text("{")
        self.assertEqual(json.loads(self.call("/api/konsol/duzen")[2]), {"duzen": None}, "a damaged layout falls back to the defaults")
        (self.root / "konsol" / panel.LAYOUT_FILE).write_text(json.dumps({"kareler": ["X"]}))
        self.assertEqual(json.loads(self.call("/api/konsol/duzen")[2]), {"duzen": None})
        self.assertEqual(self.call("/api/konsol/duzen", {"duzen": {"kareler": ["dosyalar"]}})[0], 200, "a new save replaces it")

    def test_the_gates_stay_in_front(self):
        status, _, _ = test_resources.unix_get(self.sock, "/api/konsol/duzen", {})
        self.assertEqual(status, 403, "X-Konsol is required")
        status, _, _ = test_resources.unix_get(self.sock, "/api/konsol/duzen", {"X-Konsol": "1", "Host": "evil.test"})
        self.assertEqual(status, 403)


class Clock:
    def __init__(self):
        self.mono, self.wall = 1000.0, 2_000_000_000.0

    def step(self, seconds):
        self.mono += seconds
        self.wall += seconds


class NetworkSamplerTests(Fixture):
    def sample(self, clock, rx, tx, env=None):
        with patch.object(panel.Panel, "net_counters", staticmethod(lambda iface: [rx, tx])), \
                patch.object(panel.time, "monotonic", lambda: clock.mono), patch.object(panel.time, "time", lambda: clock.wall):
            return self.p.net_sample(env or {"WAN_INTERFACE": "eth0"})

    def test_rates_come_from_counter_deltas_with_a_minimum_step(self):
        clock = Clock()
        self.assertEqual(self.sample(clock, 1000, 500), "eth0")
        self.assertEqual(self.p.net_points, [], "the first reading is only a baseline")
        clock.step(2)
        self.sample(clock, 1000 + 4 * 1024 * 1024, 500 + 2048)
        self.assertEqual(self.p.net_points[-1], {"t": int(clock.wall), "rx": 2 * 1024 * 1024, "tx": 1024})
        clock.step(0.5)
        self.sample(clock, 10 ** 9, 10 ** 9)
        self.assertEqual(len(self.p.net_points), 1, "readings closer than NET_STEP_SECONDS add no point")
        clock.step(2)
        self.sample(clock, 0, 0)
        self.assertEqual(self.p.net_points[-1]["rx"], 0, "a counter reset is not a negative rate")
        clock.step(10 * panel.SAMPLE_SECONDS)
        self.sample(clock, 100, 100)
        self.assertEqual(len(self.p.net_points), 2, "a stale baseline gives no point")
        for _ in range(panel.NET_POINTS + 5):
            clock.step(2)
            self.sample(clock, 0, 0)
        self.assertEqual(len(self.p.net_points), panel.NET_POINTS)

    def test_interface_names_are_checked_and_a_new_interface_starts_a_new_history(self):
        clock = Clock()
        for bad in ("", "../x", ".", "..", "a" * 16, "eth 0", "eth/0"):
            with self.subTest(iface=bad):
                self.assertEqual(self.sample(clock, 1, 1, {"WAN_INTERFACE": bad}), "")
        self.sample(clock, 0, 0)
        clock.step(2)
        self.sample(clock, 2048, 2048)
        self.assertEqual(len(self.p.net_points), 1)
        clock.step(2)
        self.assertEqual(self.sample(clock, 0, 0, {"WAN_INTERFACE": "ens3"}), "ens3")
        self.assertEqual(self.p.net_points, [])

    def test_unreadable_counters_leave_the_history_alone(self):
        def broken(_iface):
            raise OSError("no such device")
        with patch.object(panel.Panel, "net_counters", staticmethod(broken)):
            self.assertEqual(self.p.net_sample({"WAN_INTERFACE": "eth0"}), "eth0")
        self.assertIsNone(self.p.net_prev)


class TrafficEndpointTests(Fixture):
    def network(self):
        with patch.object(panel.Panel, "net_counters", staticmethod(lambda iface: [0, 0])):
            return self.p.network()

    def test_packages_report_through_their_own_modules(self):
        self.package("deneme", "def trafik(env):\n    assert env['LOCAL_DOMAIN'] == 'test'\n    return {'down': 5, 'up': 7, 'since': 1700000000}\n")
        self.package("durmus", "def trafik(env):\n    raise AssertionError('a stopped package is not asked')\n", state="durduruldu")
        self.package("yok", "def trafik(env):\n    return {'down': 1, 'up': 1}\n", state=None)
        self.package("sessiz", None, manifest_extra="")
        self.package("ozel", "def trafik(env):\n    return {'down': 1, 'up': 1}\n", manifest_extra='PAKET_TRAFIK="trafik.py"\nPAKET_YERLESIK=1\n')
        answer = self.network()
        self.assertEqual(answer["iface"], "eth0")
        self.assertEqual(answer["window"], panel.NET_WINDOW_SECONDS)
        self.assertEqual(answer["apps"], [
            {"id": "deneme", "name": "Deneme deneme", "state": "calisiyor", "down": 5, "up": 7, "since": 1700000000, "at": None},
            {"id": "durmus", "name": "Deneme durmus", "state": "durduruldu", "down": None, "up": None, "since": None, "at": None}])

    def test_a_broken_module_empties_only_its_own_row_and_is_reported_once(self):
        self.package("bozuk", "def trafik(env):\n    raise RuntimeError('x')\n")
        self.package("tuhaf", "def trafik(env):\n    return {'down': -1, 'up': 'many', 'since': 1.5}\n")
        self.package("liste", "def trafik(env):\n    return [1, 2]\n")
        self.package("iyi", "def trafik(env):\n    return {'down': 0, 'up': 3, 'at': 1700000000}\n")
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            first = self.network()["apps"]
            self.p.traffic_cache = (-panel.TRAFFIC_CACHE_SECONDS, None)
            self.network()
        rows = {a["id"]: (a["down"], a["up"], a["since"], a["at"]) for a in first}
        self.assertEqual(rows, {"bozuk": (None, None, None, None), "tuhaf": (None, None, None, None), "liste": (None, None, None, None),
                                "iyi": (0, 3, None, 1700000000)})
        self.assertEqual(printed.getvalue().count("Deneme bozuk trafik ölçümü okunamadı (RuntimeError)"), 1)
        self.assertEqual(printed.getvalue().count("Deneme liste trafik ölçümü okunamadı (TypeError)"), 1)

    def test_totals_are_cached_briefly(self):
        folder = self.package("deneme", "CALLS = []\ndef trafik(env):\n    CALLS.append(1)\n    return {'down': len(CALLS), 'up': 0}\n")
        self.assertEqual(self.network()["apps"][0]["down"], 1)
        self.assertEqual(self.network()["apps"][0]["down"], 1, "a second viewer within the cache window shares the reading")
        self.p.traffic_cache = (-panel.TRAFFIC_CACHE_SECONDS, self.p.traffic_cache[1])
        self.assertEqual(self.network()["apps"][0]["down"], 2)
        self.assertTrue((folder / "trafik.py").exists())
        self.assertEqual([p.name for p in folder.iterdir() if p.name == "__pycache__"], [], "no bytecode next to the package")

    def test_points_outside_the_window_are_not_returned(self):
        now = 2_000_000_000
        self.p.net_points = [{"t": now - panel.NET_WINDOW_SECONDS - 1, "rx": 1, "tx": 1}, {"t": now - 10, "rx": 2, "tx": 3}]
        with patch.object(panel.time, "time", lambda: now), patch.object(panel.Panel, "net_counters", staticmethod(lambda iface: [0, 0])):
            answer = self.p.network()
        self.assertEqual(answer["points"], [[now - 10, 2, 3]])
        self.assertEqual((answer["rx"], answer["tx"], answer["sampled_at"], answer["read_at"]), (2, 3, now - 10, now))


# The AllStats line qBittorrent 5.1 wrote on nrm (2026-10-02): a QVariantHash in QSettings' Qt 4.0
# stream format with AlltimeUL = 18968 and AlltimeDL = 12576.
REAL_ALLSTATS = (r"@Variant(\0\0\0\x1c\0\0\0\x2\0\0\0\x12\0\x41\0l\0l\0t\0i\0m\0\x65\0U\0L\0\0\0\x4\0\0\0\0\0\0J\x18"
                 r"\0\0\0\x12\0\x41\0l\0l\0t\0i\0m\0\x65\0\x44\0L\0\0\0\x4\0\0\0\0\0\0\x31 )")


def qt_escape(data):
    r"""QSettings' INI writer for a byte string, as far as AllStats needs it: NUL as \0, other
    control and non-ASCII bytes as \x.., and a hex digit right after an escape escaped too."""
    out, after_escape = [], False
    for byte in data:
        ch = chr(byte)
        if byte == 0:
            out.append("\\0"); after_escape = True
        elif byte < 0x20 or byte >= 0x7f or (after_escape and ch in "0123456789abcdefABCDEF"):
            out.append("\\x%x" % byte); after_escape = True
        elif ch in '\\"':
            out.append("\\" + ch); after_escape = False
        else:
            out.append(ch); after_escape = False
    return "".join(out)


def allstats(down, up):
    import struct
    def key(name):
        raw = name.encode("utf-16-be")
        return struct.pack(">I", len(raw)) + raw
    body = struct.pack(">II", 28, 2) + key("AlltimeUL") + struct.pack(">Iq", 4, up) + key("AlltimeDL") + struct.pack(">Iq", 4, down)
    return "@Variant(%s)" % qt_escape(body)


class TorrentTrafficTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="torrent-trafik-")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name).resolve()  # read_regular follows no link (macOS /var is one)
        (root / "pkg").mkdir()
        (root / "pkg/torrent.env").write_text("TORRENT_PROFILE_DIR=%s\n" % (root / "profile"))
        (root / "profile/qBittorrent").mkdir(parents=True)
        self.data = root / "profile/qBittorrent/qBittorrent-data.conf"
        self.mod = load(ROOT / "magaza/torrent/trafik.py", "torrent_trafik_test")
        self.mod.PACKAGE_DIR = root / "pkg"

    def test_the_real_file_from_qbittorrent_5_1(self):
        self.data.write_text("[Stats]\nAllStats=%s\n" % REAL_ALLSTATS)
        os.utime(self.data, (1790962380, 1790962380))
        self.assertEqual(self.mod.trafik({}), {"down": 12576, "up": 18968, "since": None, "at": 1790962380})

    def test_large_totals_survive_the_escaping(self):
        for down, up in ((0, 0), (5 * 1024 ** 4 + 0x1c0d0a, 0x7F00A1B2C3D4), (0xA0A0A0A0A0, 0x3031323334), (1, 2 ** 62)):
            with self.subTest(down=down, up=up):
                self.data.write_text("[Other]\nAllStats=x\n[Stats]\nAllStats=%s\n" % allstats(down, up))
                value = self.mod.trafik({})
                self.assertEqual((value["down"], value["up"]), (down, up))

    def test_nothing_saved_yet_and_damaged_records(self):
        self.assertEqual(self.mod.trafik({}), {"down": 0, "up": 0, "since": None, "at": None}, "no file before the first save")
        self.data.write_text("[Stats]\n")
        self.assertEqual(self.mod.trafik({})["down"], 0)
        for bad in ("AllStats=12", "AllStats=@Variant(\\0\\0\\0\\x9\\0\\0\\0\\0)", "AllStats=@Variant(\\0\\0\\0\\x1c\\0\\0\\0\\x5)",
                    "AllStats=@Variant(\\x)", "AllStats=@Variant(%s)" % qt_escape(b"\0\0\0\x1c\0\0\0\0")):
            with self.subTest(bad=bad), self.assertRaises((ValueError, Exception)):
                self.data.write_text("[Stats]\n%s\n" % bad)
                self.mod.trafik({})

    def test_it_reads_the_profile_only(self):
        source = (ROOT / "magaza/torrent/trafik.py").read_text()
        self.assertNotIn("subprocess", source)
        self.assertNotIn("systemctl", source.split('"""', 2)[2])


class WireguardTrafficTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="wg-trafik-")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name).resolve()  # read_regular follows no link (macOS /var is one)
        self.mod = load(ROOT / "magaza/wireguard/trafik.py", "wireguard_trafik_test")
        (root / "pkg").mkdir()
        (root / "pkg/wireguard.env").write_text('WG_NETWORKS_FILE="%s"\n' % (root / "networks"))
        self.networks = root / "networks"
        self.sys = root / "sys"
        for iface, rx, tx in (("wg0", 100, 1000), ("wg1", 20, 300), ("eth0", 7, 7)):
            (self.sys / iface / "statistics").mkdir(parents=True)
            (self.sys / iface / "statistics/rx_bytes").write_text("%d\n" % rx)
            (self.sys / iface / "statistics/tx_bytes").write_text("%d\n" % tx)
        self.mod.PACKAGE_DIR = root / "pkg"
        self.mod.SYS_NET = self.sys

    def run_trafik(self, stdout="ActiveEnterTimestampMonotonic=4000000000\nActiveEnterTimestampMonotonic=4500000000\n"):
        calls = []

        def fake(cmd, **kwargs):
            calls.append(cmd)
            return types.SimpleNamespace(returncode=0, stdout=stdout)
        with patch.object(self.mod.subprocess, "run", fake), patch.object(self.mod.time, "time", lambda: 2_000_000_000.0), \
                patch.object(self.mod.time, "monotonic", lambda: 5000.0):
            return self.mod.trafik({}), calls

    def test_down_is_what_the_peers_received_and_up_what_they_sent(self):
        self.networks.write_text("wg0\t61001\tx\nwg1\t61002\tx\nwg2\t61003\tx\n# yorum\neth0\t1\n")
        value, calls = self.run_trafik()
        self.assertEqual(value, {"down": 1300, "up": 120, "since": 2_000_000_000 - 1000})
        self.assertEqual(calls[0][-2:], ["wg-quick@wg0.service", "wg-quick@wg1.service"], "wg2 is down and eth0 is not a network")

    def test_no_registry_or_no_network_up(self):
        value, calls = self.run_trafik()
        self.assertEqual((value, calls), ({"down": 0, "up": 0, "since": None}, []))
        self.networks.write_text("wg5\t61005\tx\n")
        self.assertEqual(self.run_trafik()[0], {"down": 0, "up": 0, "since": None})


if __name__ == "__main__":
    unittest.main()
