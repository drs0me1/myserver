"""WireGuard package API through the root backend's package dispatcher (DD-200): gates,
validation and the master-wg argument lines; no real WireGuard or systemd changes."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import types
import unittest
from unittest.mock import patch

import test_resources as resources

panel = resources.panel
REPO = Path(__file__).resolve().parents[1]
API = "/api/uygulama/wireguard"


class NetworkSettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name).resolve()
        # The rendered package folder: manifest and API module straight from the repository.
        (root / "mods" / "wireguard").mkdir(parents=True)
        for name in ("paket.env", "api.py"):
            shutil.copy(REPO / "magaza" / "wireguard" / name, root / "mods" / "wireguard" / name)
        (root / "bin").mkdir()
        (root / "bin" / "master-modul").write_text("#!/bin/sh\nexit 1\n")
        os.chmod(root / "bin" / "master-modul", 0o755)
        self.registry = root / "moduller"
        self.installed(True)
        state = root / "state.env"
        state.write_text("LOCAL_DOMAIN=test\nMODULES_FILE=%s\nMODULES_DIR=%s\n" % (self.registry, root / "mods"))
        self.tool = str(root / "bin" / "master-wg")
        self.p = panel.Panel(types.SimpleNamespace(state=str(state), allow_host=[], state_env=False,
                                                   master_modul=str(root / "bin" / "master-modul")))
        self.addCleanup(lambda: [self.p.api_stop(mid, api) for mid, (_key, api) in list(self.p.apis.items())])
        class Handler(panel.Handler):
            def log_message(self, *_args):
                pass
        Handler.panel = self.p
        self.server, self.sock = resources.start_unix(self, Handler)
        self.data = dict(dns="9.9.9.9, 2620:fe::fe", revision="a" * 64)

    def installed(self, flag):
        self.registry.write_text("wireguard\tcalisiyor\n" if flag else "")

    def request(self, data=None, headers=None, path=API + "/nets/wg0/ayarlar"):
        headers = headers if headers is not None else {"X-Konsol":"1"}
        headers = {"Content-Type":"application/json", **headers}
        body = json.dumps(self.data if data is None else data).encode()
        status, _headers, raw = resources.unix_get(self.sock, path, headers, "POST", body)
        return status, json.loads(raw)

    @staticmethod
    def tool_calls(run, verb):
        return [c.args[0] for c in run.call_args_list if verb in c.args[0]]

    def test_valid_request_delegates_once_without_reset_and_invalidates_settings_cache(self):
        self.p.settings_cache = (1, {"old":True})
        with patch.object(self.p, "run_tool", return_value=(0,"","")) as run:
            code, data = self.request()
            self.assertEqual(code,200,data)
            self.assertEqual(self.tool_calls(run, "net-settings"),
                             [[self.tool, "--if", "wg0", "net-settings", self.data["dns"], self.data["revision"]]])
            self.assertFalse(self.tool_calls(run, "reset"))
            self.assertEqual(data["dns"],self.data["dns"])
        self.assertEqual(self.p.settings_cache,(0,None))

    def test_gates_and_module_absence_never_invoke_helper(self):
        with patch.object(self.p, "run_tool", side_effect=AssertionError("must not mutate")):
            for path in (API + "/nets", API + "/nets/wg0/ayarlar"):
                for headers in ({}, {"X-Konsol":"1","Host":"evil.test"},
                                {"X-Konsol":"1","Sec-Fetch-Site":"cross-site"}):
                    self.assertEqual(self.request(headers=headers,path=path)[0],403)
                self.installed(False)
                code, data = self.request(path=path)
                self.assertEqual(code, 409)
                self.assertIn("WireGuard kurulu değil", data["error"])
                self.installed(True)
        # The API module is loaded only for the registered package; nothing else answers.
        self.assertEqual(self.request(path="/api/uygulama/torrent/nets")[0], 409)

    def test_network_creation_has_no_access_option(self):
        data = dict(port="61020", dns="1.1.1.1", label="New network")
        with patch.object(self.p, "run_tool", return_value=(0,"wg1\t61020\n","")) as run:
            code, result = self.request(data,path=API + "/nets")
            self.assertEqual(code,201,result)
            self.assertEqual(result,{"iface":"wg1","port":61020})
            self.assertEqual(self.tool_calls(run, "net-add"), [[self.tool, "net-add", "61020", "1.1.1.1", "New network"]])

    def test_retired_scope_is_rejected_on_both_routes(self):
        with patch.object(self.p, "run_tool", side_effect=AssertionError("invalid mutation")):
            for scope in (None, "", "all", False, "ui", "inet"):
                for path, data in ((API + "/nets",dict(port="61020",dns="1.1.1.1")),
                                   (API + "/nets/wg0/ayarlar",self.data)):
                    with self.subTest(scope=scope,path=path):
                        self.assertEqual(self.request({**data,"scope":scope},path=path)[0],400)

    def test_bad_inputs_never_reach_helper(self):
        with patch.object(self.p, "run_tool", side_effect=AssertionError("invalid mutation")):
            for override in [{"scope":"all"},{"dns":None},{"dns":"dns.example"},{"dns":"999.1.1.1"},
                             {"dns":"1.1.1.1\n9.9.9.9"},{"dns":"1.1.1.1,,"},{"dns":":::"},
                             {"dns":"fe80::1%eth0"},{"dns":", ".join(["1.1.1.1"]*9)},
                             {"revision":None},{"revision":"bad"}]:
                with self.subTest(override=override):
                    self.assertEqual(self.request({**self.data,**override})[0],400)
            self.assertEqual(self.request(path=API + "/nets/notwg/ayarlar")[0],400)

    def test_conflict_or_apply_failure_is_not_reported_as_saved(self):
        with patch.object(self.p, "run_tool", return_value=(1,"","Ağ ayarları değişmiş")):
            code,data=self.request()
            self.assertEqual(code,409)
            self.assertIn("Ağ ayarları değişmiş",data["error"])

    def test_revision_matches_exact_registry_line_not_runtime_activity(self):
        line="wg0\t61001\tinet\t10.8.0.1\t10.8.0.0/24\tfd00::1\tfd00::/112\t1.1.1.1\tTürkçe ağ"
        with patch.object(self.p, "run_tool") as run:
            run.return_value=(0,"","")
            api = self.p.package_api("wireguard")
            self.assertIsNotNone(api)
            for runtime in ("\t1\t2","\t0\t3"):
                run.return_value=(0,line+runtime+"\n","")
                self.assertNotIn("scope",api.net_rows()[0])
                self.assertEqual(api.net_rows()[0]["revision"],hashlib.sha256(line.encode()).hexdigest())
            # Settings consumers get the public network fields only (no DNS, no revision, no keys).
            nets = self.p.package_networks()
            self.assertEqual([n["iface"] for n in nets], ["wg0"])
            self.assertEqual(set(nets[0]), {"app", "iface", "port", "label", "active", "server4", "subnet4", "server6", "subnet6"})
            self.assertEqual(self.p.vpn_apps(), ["WireGuard"])

    def test_audit_lines_carry_the_package_id(self):
        with patch.object(self.p, "run_tool", return_value=(0,"phone\t10.8.0.3\n","")), \
                patch("builtins.print") as out:
            code, _ = self.request(dict(name="phone", dns="1.1.1.1", keepalive="21", mtu="1420"), path=API + "/nets/wg0/peers")
        self.assertEqual(code, 201)
        lines = [c.args[0] for c in out.call_args_list if c.args and "wireguard:ekle" in str(c.args[0])]
        self.assertEqual(len(lines), 1, out.call_args_list)
        self.assertIn(" wireguard:ekle wg0/phone -> ok", lines[0])


if __name__ == "__main__":
    unittest.main()
