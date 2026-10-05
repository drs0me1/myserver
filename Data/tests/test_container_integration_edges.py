"""Independent inventory/broker/worker edge reproductions; no server or real Podman calls."""
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "panel"))
import master_container_config as config
import master_container_manager as manager
import master_container_worker as worker


class IntegrationEdges(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="container-edges-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.env = {"KONTEYNER_STATE_DIR": str(self.root / "state"), "MODULES_FILE": str(self.root / "modules"),
                    "MODULES_DIR": str(self.root / "packages"), "RUNTIME_DIR": str(self.root / "run"),
                    "KONTEYNER_LOCK": str(self.root / "run/containers.lock"), "KONTEYNER_NETWORK": "konsol",
                    "TAILSCALE_IPV4": "100.64.0.2"}
        (self.root / "modules").write_text("")
        self.state = self.root / "state.env"
        self.state.write_text("".join(k + "=" + v + "\n" for k, v in self.env.items()))
        self.raw, self.networks, self.calls = {}, [], []
        panel = types.SimpleNamespace(args=types.SimpleNamespace(state=str(self.state)), run_tool=self.fake_run,
                                      env=lambda: {}, module_busy=lambda _: False)
        self.service = manager.Service(panel)

    def fake_run(self, argv, timeout=30, **kwargs):
        self.calls.append(list(argv))
        if argv[:2] == ["podman", "version"]:
            return 0, "5.4.2", ""
        if argv[:2] == ["podman", "ps"]:
            rows = [{"Id": r["Id"], "Names": [name], "Image": r["ImageName"], "State": r["State"]["Status"],
                     "Labels": r["Config"].get("Labels", {}), "Status": "Up 2 minutes (unhealthy)"}
                    for name, r in self.raw.items()]
            return 0, json.dumps(rows), ""
        if argv[:2] == ["podman", "inspect"]:
            return (0, json.dumps([self.raw[argv[-1]]]), "") if argv[-1] in self.raw else (1, "", "no such container")
        if argv[:3] == ["podman", "container", "exists"]:
            return (0 if argv[-1] in self.raw else 1), "", ""
        if argv[:2] == ["podman", "stop"]:
            self.raw[argv[-1]]["State"].update(Running=False, Status="exited")
            return 0, "", ""
        if argv[:3] == ["podman", "network", "ls"]:
            return 0, json.dumps(self.networks), ""
        if argv[:2] in (["podman", "images"], ["podman", "system"], ["podman", "stats"], ["podman", "volume"]):
            return 0, "[]", ""
        raise AssertionError(argv)

    def container(self, name="outside", status="running", labels=None):
        self.raw[name] = {"Id": "c" * 64, "Name": name, "ImageName": "docker.io/library/nginx:alpine",
                          "State": {"Status": status, "Running": status in ("running", "paused"),
                                    "Paused": status == "paused", "Health": {"Status": "unhealthy"}},
                          "HostConfig": {"NetworkMode": "bridge"}, "NetworkSettings": {}, "Mounts": [],
                          "Config": {"Labels": labels or {}, "Env": ["TOKEN=native-secret-value"], "Cmd": ["serve"]}}

    def definition(self, name="owned"):
        definition = {"schema": 1, "name": name, "revision": "a" * 32,
                      "image": "docker.io/library/nginx@sha256:" + "b" * 64, "image_ref": "docker.io/library/nginx:alpine",
                      "network": "bridge", "ports": [], "mounts": [], "command": [],
                      "environment": [{"name": "TOKEN", "value": "saved-secret-value", "secret": True}],
                      "autostart": True, "manual_stop": True, "restart": "on-failure", "cpus": "", "memory": ""}
        config.Store(self.env).save(definition)
        return definition

    def test_paused_container_does_not_offer_start_as_if_it_were_stopped(self):
        self.container(status="paused")
        detail = self.service.view().ayrinti("outside")
        self.assertEqual(detail["state"], "paused")
        self.assertNotIn("start", detail["actions"], "Start cannot resume a paused container; advertise a supported action or restriction")

    def test_saved_name_collision_with_foreign_owner_is_read_only(self):
        self.definition()
        self.container("owned", labels={"PODMAN_SYSTEMD_UNIT": "foreign-owner.service"})
        row = self.service.view().ayrinti("owned")
        self.assertEqual(row["actions"], [], "Saved names alone must not grant actions over a foreign runtime owner")
        self.assertTrue(row["restricted_reason"])

    def test_list_health_uses_already_collected_native_inspection(self):
        self.container()
        row = self.service.view().liste()["containers"][0]
        self.assertEqual(row["health"], "unhealthy", "The summary must not report zero unhealthy containers when native inspect says unhealthy")

    def test_real_network_subnet_objects_normalized_for_console_string_rows(self):
        self.networks = [{"name": "konsol", "driver": "bridge", "id": "d" * 64,
                          "subnets": [{"subnet": "10.89.0.0/24", "gateway": "10.89.0.1"}],
                          "labels": {"io.master-stack.managed": "konsol"}}]
        row = self.service.view().liste()["networks"][0]
        self.assertEqual(row["subnets"], ["10.89.0.0/24"], "Console joins these rows as strings; objects display as [object Object]")

    def test_external_name_advertised_by_broker_can_reach_the_actual_worker(self):
        self.container("outside.web")
        self.assertIn("stop", self.service.view().ayrinti("outside.web")["actions"])
        payload = {"action": "stop", "name": "outside.web", "revision": None}
        with patch.object(self.service, "_launch"):
            self.assertEqual(self.service.submit(payload)["state"], "running")
        actual = worker.Manager(str(self.state), run=self.fake_run)
        try:
            result = actual.execute("stop", {k: v for k, v in payload.items() if k != "action"}, uuid.uuid4().hex)
        except config.ContainerConfigError as error:
            self.fail("Broker-advertised standalone stop rejected by worker: " + str(error))
        self.assertFalse(result["running"])

    def test_missing_saved_definition_stays_visible_and_secret_values_stay_private(self):
        self.definition()
        row = self.service.view().ayrinti("owned")
        self.assertEqual((row["state"], row["live"]), ("stopped", False))
        self.assertIn("start", row["actions"])
        self.assertNotIn("saved-secret-value", json.dumps(row))
        self.assertEqual(row["config"]["environment"], [{"name": "TOKEN", "secret": True, "present": True}])

    def test_runtime_environment_values_are_not_returned_from_inspect(self):
        self.container()
        self.assertNotIn("native-secret-value", json.dumps(self.service.view().ayrinti("outside")))


if __name__ == "__main__":
    unittest.main()
