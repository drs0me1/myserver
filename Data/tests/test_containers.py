"""Legacy read-only mapper (DD-208), reused by the main container manager (DD-211).

Podman is base infrastructure; panel/master_containers.py maps read-only podman output for the
root backend. No real podman: every command answers from canned output, so the tests cover the
mapping, the masking and the gates; a route test runs the real backend handler on a Unix socket."""
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "panel"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import master_containers as containers  # noqa: E402
import tempfile  # noqa: E402
import types  # noqa: E402
from test_resources import panel, start_unix, unix_get  # noqa: E402

PS = [{"Id": "2073a1b2c3d4e5f6", "Names": ["deneme-qbit"], "Image": "lscr.io/linuxserver/qbittorrent:latest", "State": "running",
       "Status": "Up 9 minutes", "Created": 1790972658, "StartedAt": 1790972659, "ExitCode": 0, "Restarts": 2,
       "Labels": {"PODMAN_SYSTEMD_UNIT": "deneme-qbit.service"}, "Namespaces": {"Net": "host"}, "Networks": [], "Ports": None,
       "Mounts": ["/config", "/downloads"]},
      {"Id": "ffff000011112222", "Names": ["web"], "Image": "docker.io/library/nginx:1.27", "State": "exited", "Status": "Exited (3) 2 hours ago",
       "Created": 1790900000, "StartedAt": 1790900001, "ExitCode": 3, "Restarts": 0, "Labels": {}, "Networks": ["podman"],
       "Ports": [{"host_ip": "", "host_port": 8081, "container_port": 80, "protocol": "tcp", "range": 1}], "Mounts": []}]
IMAGES = [{"Names": ["lscr.io/linuxserver/qbittorrent:latest"], "Size": 228000000, "Created": 1790667122}, {"Names": None, "Size": 5, "Created": 1}]
DF = [{"Type": "Images", "RawSize": 228000000}, {"Type": "Containers", "RawSize": 1000}, {"Type": "Local Volumes", "RawSize": 0}]
INSPECT = [{"Id": "2073a1b2c3d4e5f6", "Name": "deneme-qbit", "ImageName": "lscr.io/linuxserver/qbittorrent:latest", "ImageDigest": "sha256:abcdef0123456789",
            "Created": "2026-10-02T22:24:18.9+02:00", "RestartCount": 1,
            "State": {"Status": "running", "StartedAt": "2026-10-02T22:24:19.081055326+02:00", "FinishedAt": "0001-01-01T00:00:00Z", "ExitCode": 0,
                      "Health": {"Status": "healthy"}},
            "Mounts": [{"Type": "bind", "Source": "/srv/downloads/deneme-podman", "Destination": "/downloads", "RW": True, "Name": None},
                       {"Type": "bind", "Source": "/var/lib/master-stack/deneme-qbit/config", "Destination": "/config", "RW": False, "Name": None}],
            "HostConfig": {"NetworkMode": "host", "PortBindings": {}}, "NetworkSettings": {"Ports": {}},
            "Config": {"Cmd": ["/init"], "Env": ["WEBUI_PASSWORD=verysecret", "PUID=1000"],
                       "Labels": {"PODMAN_SYSTEMD_UNIT": "deneme-qbit.service", "org.opencontainers.image.version": "5.2.4", "org.opencontainers.image.source": "https://github.com/x/y", "org.opencontainers.image.title": "Qbittorrent"}}}]
INSPECT_BRIDGE = [dict(INSPECT[0], Name="web", HostConfig={"NetworkMode": "bridge", "PortBindings": {"80/tcp": [{"HostIp": "", "HostPort": "8081"}], "53/udp": [{"HostIp": "127.0.0.1", "HostPort": "5353"}]}},
                       NetworkSettings={"Ports": {}}, Mounts=[], Config={"Cmd": ["nginx", "-g", "daemon off;"], "Labels": {}})]
LOGS = ("2026-10-02T22:24:19+02:00 The WebUI administrator username is: admin\n"
        "2026-10-02T22:24:19+02:00 A temporary password is provided for this session: Zq3pL9ab2\n"
        "2026-10-02T22:24:20+02:00 token=abc.def.ghi api_key: XYZ Private key = 12345\n"
        "2026-10-02T22:24:20+02:00 [ls.io-init] done.\n\n")


class Ctx:
    def __init__(self):
        self.calls, self.fail, self.version = [], {}, "5.4.2"

    def run(self, argv, timeout=120, binary=False):
        self.calls.append((list(argv), timeout))
        key = argv[1]
        if key in self.fail:
            return 125, "", self.fail[key]
        if key == "version":
            return 0, self.version + "\n", ""
        if key == "ps":
            return 0, json.dumps(PS), ""
        if key == "images":
            return 0, json.dumps(IMAGES), ""
        if key == "system":
            return 0, json.dumps(DF), ""
        if key == "inspect":
            name = argv[-1]
            if name == "deneme-qbit":
                return 0, json.dumps(INSPECT), ""
            if name == "web":
                return 0, json.dumps(INSPECT_BRIDGE), ""
            return 125, "", 'Error: no such object: "%s"' % name
        if key == "logs":
            return (0, LOGS, "") if argv[-1] == "deneme-qbit" else (125, "", "Error: no container with name or ID \"%s\" found: no such container" % argv[-1])
        raise AssertionError(argv)


class ContainerViewTests(unittest.TestCase):
    def setUp(self):
        self.ctx = Ctx()
        self.view = containers.Containers(self.ctx.run)

    def call(self, sub, method="GET", **query):
        """The backend route's logic: GET only, three read paths, a ContainerError becomes its status."""
        if method != "GET" or sub not in ("liste", "ayrinti", "gunluk"):
            raise RuntimeError("404 bulunamadı")
        try:
            if sub == "liste":
                return 200, self.view.liste()
            name = containers.name_of(query.get("ad", ""))
            return 200, self.view.ayrinti(name) if sub == "ayrinti" else self.view.gunluk(name, query.get("satir", "200"))
        except containers.ContainerError as err:
            raise RuntimeError("%d %s" % (err.status, err))

    def test_list_maps_containers_images_and_storage(self):
        code, answer = self.call("liste")
        self.assertEqual(code, 200)
        self.assertEqual(answer["runtime"], {"version": "5.4.2", "ok": True, "error": ""})
        qbit, web = answer["containers"]
        self.assertEqual((qbit["id"], qbit["name"], qbit["state"], qbit["unit"], qbit["network"], qbit["ports"], qbit["mounts"], qbit["restarts"]),
                         ("2073a1b2c3d4", "deneme-qbit", "running", "deneme-qbit.service", "host", [], 2, 2))
        self.assertEqual((qbit["created"], qbit["started"], qbit["exit_code"]), (1790972658, 1790972659, 0))
        self.assertEqual((web["state"], web["exit_code"], web["network"], web["unit"]), ("exited", 3, "podman", ""))
        self.assertEqual(web["ports"], [{"host_ip": "0.0.0.0", "host_port": 8081, "container_port": 80, "protocol": "tcp"}])
        self.assertEqual(answer["images"], [{"name": "lscr.io/linuxserver/qbittorrent:latest", "size": 228000000, "created": 1790667122},
                                            {"name": "<adsız>", "size": 5, "created": 1}])
        self.assertEqual(answer["storage"], {"images": 2, "containers": 2, "size": 228001000})
        self.assertNotIn("Env", json.dumps(answer))
        self.assertEqual([c[0][:2] for c in self.ctx.calls], [["podman", "version"], ["podman", "ps"], ["podman", "images"], ["podman", "system"]])

    def test_list_without_podman_is_a_calm_answer(self):
        self.ctx.fail["version"] = "podman çalıştırılamadı (FileNotFoundError)"
        code, answer = self.call("liste")
        self.assertEqual((code, answer["runtime"]["ok"], answer["containers"], answer["images"]), (200, False, [], []))
        self.assertIn("Podman kullanılamıyor", answer["runtime"]["error"])
        self.ctx.fail = {"ps": "Error: database is locked"}
        code, answer = self.call("liste")
        self.assertEqual((answer["runtime"]["ok"], answer["runtime"]["version"]), (False, "5.4.2"))
        self.assertIn("Konteynerler okunamadı", answer["runtime"]["error"])
        self.ctx.fail = {}
        self.ctx.version = "weird; rm -rf"
        self.assertFalse(self.call("liste")[1]["runtime"]["ok"])

    def test_inspect_maps_mounts_ports_labels_and_never_the_environment(self):
        code, c = self.call("ayrinti", ad="deneme-qbit")
        self.assertEqual(code, 200)
        self.assertEqual((c["name"], c["id"], c["image_digest"], c["state"], c["health"], c["restarts"], c["unit"], c["network"], c["command"]),
                         ("deneme-qbit", "2073a1b2c3d4", "abcdef012345", "running", "healthy", 1, "deneme-qbit.service", "host", "/init"))
        self.assertEqual((c["created"], c["started"], c["finished"]), (1790972658, 1790972659, None))
        self.assertEqual([m["destination"] for m in c["mounts"]], ["/config", "/downloads"], "sorted by container path")
        self.assertEqual(c["mounts"][0], {"type": "bind", "source": "/var/lib/master-stack/deneme-qbit/config", "destination": "/config", "rw": False, "name": ""})
        self.assertEqual(c["labels"], {"version": "5.2.4", "source": "https://github.com/x/y", "title": "Qbittorrent"})
        self.assertEqual(c["ports"], [])
        self.assertNotIn("verysecret", json.dumps(c))
        self.assertNotIn("PUID", json.dumps(c))
        code, w = self.call("ayrinti", ad="web")
        self.assertEqual(w["ports"], [{"host_ip": "127.0.0.1", "host_port": 5353, "container_port": 53, "protocol": "udp"},
                                      {"host_ip": "0.0.0.0", "host_port": 8081, "container_port": 80, "protocol": "tcp"}])
        self.assertEqual((w["network"], w["labels"], w["command"]), ("bridge", {"version": "", "source": "", "title": ""}, "nginx -g daemon off;"))

    def test_logs_are_returned_as_written_and_the_tail_is_bounded(self):
        # DD-251: no masking or other filter; only blank lines go.
        code, log = self.call("gunluk", ad="deneme-qbit")
        self.assertEqual((code, log["name"], log["truncated"]), (200, "deneme-qbit", False))
        self.assertNotIn("masked", log)
        self.assertEqual(log["lines"], [l for l in LOGS.splitlines() if l], "every line as the runtime wrote it")
        self.assertEqual(self.ctx.calls[-1][0], ["podman", "logs", "--timestamps", "--tail", "200", "deneme-qbit"])
        self.call("gunluk", ad="deneme-qbit", satir="500")
        self.assertEqual(self.ctx.calls[-1][0][4], "500")
        self.call("gunluk", ad="deneme-qbit", satir="7")
        self.assertEqual(self.ctx.calls[-1][0][4], "200", "an unknown tail falls back to 200")
        with self.assertRaises(RuntimeError) as err:
            self.call("gunluk", ad="yok")
        self.assertIn("404", str(err.exception))

    def test_gates_names_methods_and_paths(self):
        for bad in ("", "-x", "a b", "x" * 65, "../etc", "a;b"):
            with self.subTest(bad=bad), self.assertRaises(RuntimeError) as err:
                self.call("ayrinti", ad=bad)
            self.assertIn("400", str(err.exception))
        with self.assertRaises(RuntimeError) as err:
            self.call("ayrinti", ad="yok")
        self.assertIn("404", str(err.exception))
        with self.assertRaises(RuntimeError) as err:
            self.call("liste", method="POST")
        self.assertIn("404", str(err.exception), "the backend has no write route for containers")
        with self.assertRaises(RuntimeError) as err:
            self.call("baslat")
        self.assertIn("404", str(err.exception))
        self.assertEqual([c[0] for c in self.ctx.calls if c[0][1] in ("rm", "stop", "start", "kill", "exec")], [])

    def test_time_parsing(self):
        self.assertEqual(containers.epoch("2026-10-02T22:24:19.081055326+02:00"), 1790972659)
        self.assertEqual(containers.epoch("2026-10-02T20:24:19Z"), 1790972659)
        self.assertIsNone(containers.epoch("0001-01-01T00:00:00Z"))
        self.assertIsNone(containers.epoch(-62135596800))
        self.assertIsNone(containers.epoch("garbage"))
        self.assertEqual(containers.epoch(1790972659.7), 1790972659)


class ContainerRouteTests(unittest.TestCase):
    """The real handler: shared Konsol gates, GET answers, no write route (POST → 404), no podman write verb."""
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name).resolve()
        (root / "modules").write_text("")
        (root / "state.env").write_text(f"SERVER_ROOT={root}\nLOCAL_DOMAIN=test\nV2_VERSION=test\nMODULES_FILE={root / 'modules'}\n")
        self.p = panel.Panel(types.SimpleNamespace(state=str(root / "state.env"), allow_host=[], master_modul="/fixture/master-modul"))

    def test_routes_keep_the_gates_and_never_write(self):
        fake = Ctx()

        class Handler(panel.Handler):
            def log_message(self, *_args):
                pass
        Handler.panel = self.p
        with patch.object(self.p, "run_tool", side_effect=lambda argv, binary=False, timeout=120: fake.run(argv, timeout)):
            _server, sock = start_unix(self, Handler)
            self.assertEqual(unix_get(sock, "/api/konsol/konteynerler/liste", {})[0], 403)
            self.assertEqual(unix_get(sock, "/api/konsol/konteynerler/liste", {"X-Konsol": "1", "Host": "evil.test"})[0], 403)
            status, _h, body = unix_get(sock, "/api/konsol/konteynerler/liste", {"X-Konsol": "1"})
            self.assertEqual((status, [c["name"] for c in json.loads(body)["containers"]]), (200, ["deneme-qbit", "web"]))
            status, _h, body = unix_get(sock, "/api/konsol/konteynerler/ayrinti?ad=deneme-qbit", {"X-Konsol": "1"})
            self.assertEqual((status, json.loads(body)["unit"]), (200, "deneme-qbit.service"))
            self.assertEqual(unix_get(sock, "/api/konsol/konteynerler/ayrinti?ad=a%3Bb", {"X-Konsol": "1"})[0], 400)
            self.assertEqual(unix_get(sock, "/api/konsol/konteynerler/ayrinti?ad=yok", {"X-Konsol": "1"})[0], 404)
            status, _h, body = unix_get(sock, "/api/konsol/konteynerler/gunluk?ad=deneme-qbit&satir=100", {"X-Konsol": "1"})
            self.assertEqual(status, 200)
            self.assertIn("Zq3pL9ab2", body.decode(), "DD-251: the log is not filtered")
            self.assertEqual(unix_get(sock, "/api/konsol/konteynerler/baslat", {"X-Konsol": "1"})[0], 404)
            for path in ("/api/konsol/konteynerler/liste", "/api/konsol/konteynerler/durdur"):
                self.assertEqual(unix_get(sock, path, {"X-Konsol": "1", "Content-Type": "application/json"}, "POST", b"{}")[0], 404)
        self.assertEqual([c[0] for c in fake.calls if c[0][1] in ("rm", "stop", "start", "kill", "exec", "pull", "run")], [])


if __name__ == "__main__":
    unittest.main()
