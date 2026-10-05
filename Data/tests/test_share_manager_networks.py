"""Network opt-in, migration and root publication rollback, without host changes."""
import copy
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "panel"))
import master_shares as s
loader=importlib.machinery.SourceFileLoader("share_panel",str(Path(__file__).resolve().parents[1]/"panel/master-panel"))
if Path(loader.path).exists():
    spec=importlib.util.spec_from_loader(loader.name,loader)
    panel=importlib.util.module_from_spec(spec); loader.exec_module(panel)
else:
    loader=importlib.machinery.SourceFileLoader("share_panel","/usr/local/sbin/master-panel")
    spec=importlib.util.spec_from_loader(loader.name,loader)
    panel=importlib.util.module_from_spec(spec); loader.exec_module(panel)



def torrent_package(mods_dir, downloads_path, profile_dir, ui_port="61006"):
    """DD-203: a rendered torrent package folder: manifest (folders it writes into), its folder module
    and its own settings file, as the installer leaves them under MODULES_DIR."""
    repo = Path(__file__).resolve().parents[1] / "magaza" / "torrent"
    folder = Path(mods_dir) / "torrent"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "paket.env").write_text((repo / "paket.env").read_text().replace("__TORRENT_UI_PORT__", ui_port)
                                      .replace("__DOWNLOADS_PATH__", str(downloads_path)))
    (folder / "klasorler.py").write_bytes((repo / "klasorler.py").read_bytes())
    (folder / "torrent.env").write_text("TORRENT_UI_PORT=%s\nTORRENT_PROFILE_DIR=%s\n" % (ui_port, profile_dir))
    return folder


class NetworkManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="share-networks-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        for name in ("srv/alpha", "run", "sites", "profile"):
            (self.root / name).mkdir(parents=True)
        # DD-203: the folders a package writes into come from its manifest and module, not the base.
        torrent_package(self.root/"mods", self.root/"srv/downloads", self.root/"profile")
        self.env = dict(SHARE_STATE_FILE=str(self.root/"registry"), MODULES_FILE=str(self.root/"modules"),
                        MODULES_DIR=str(self.root/"mods"),
                        RUNTIME_DIR=str(self.root/"run"), SERVER_ROOT=str(self.root/"srv"),
                        DOWNLOADS_PATH=str(self.root/"srv/downloads"), FILES_PANEL_TRASH=".cop", SHARE_DIR=".pay",
                        SETTINGS_PENDING_FILE=str(self.root/"settings-pending"),
                        SHARE_PORT="61010", TAILSCALE_IPV4="100.64.0.2", WAN_IPV4="8.8.8.8",
                        SHARE_WAN_BACKEND="127.0.0.2", CADDY_MODULES_DIR=str(self.root/"sites"),
                        CADDYFILE=str(self.root/"Caddyfile"), SBIN_DIR=str(self.root))
        self.state = self.root/"state.env"
        self.state.write_text("".join(k+"="+v+"\n" for k,v in self.env.items()))
        # The fixture WAN address is not on this machine; DD-182's live check is tested separately.
        self.addCleanup(patch.stopall)
        self.assigned_patch = patch.object(s, "assigned", return_value=True)
        self.assigned = self.assigned_patch.start()
        (self.root/"modules").write_text("paylasim\tdurduruldu\n")
        self.m = s.Manager(self.state)
        self.m.change("save", dict(path="alpha",username="reader",password="Test12345"))
        self.item = self.m.read()["items"][0]

    def save(self, **fields):
        return self.m.change("save", dict(id=self.item["id"], **fields))

    def running(self):
        (self.root/"modules").write_text("paylasim\tcalisiyor\n")

    def test_optin_required_and_selections_strict(self):
        before = Path(self.m.path).read_bytes()
        for connections in ({}, None, "wan", [], {"other": {"enabled": True}},
                            {"wan": {}}, {"wan": {"enabled": 1}}, {"wan": {"enabled": "true"}}):
            with self.subTest(connections=connections), self.assertRaises(s.ShareError):
                self.save(connections=connections)
        for ack in (None, False, 1, "true"):
            with self.assertRaises(s.ShareError):
                self.save(connections={"wan": {"enabled": True}},ack_wan_http=ack)
        self.assertEqual(before,Path(self.m.path).read_bytes())

    def test_network_edit_preserves_identity_credentials_and_absolute_expiry(self):
        self.save(connections={"wan": {"enabled": True}},ack_wan_http=True)
        self.running()
        row = self.m.public()["items"][0]
        after = self.m.read()["items"][0]
        for key in ("id","salt","hash","identity"):
            self.assertEqual(self.item[key],after[key])
        for scope in ("tailscale", "wan"):
            for key in ("expires", "permission"):
                self.assertEqual(self.item["connections"][scope][key], after["connections"][scope][key])
        self.assertEqual(set(row["urls"]),{"tailscale","wan"})
        self.assertTrue(row["urls"]["wan"].startswith("http://8.8.8.8:61010/s/"))
        (self.root/"modules").write_text("paylasim\tdurduruldu\n")
        stopped = self.save(connections={"tailscale": {"enabled": False}})["items"][0]
        self.assertEqual(stopped["urls"], {})
        self.assertFalse(stopped["connections"]["wan"]["active"])
        self.running()
        row = self.m.public()["items"][0]
        self.assertEqual(set(row["urls"]),{"wan"})
        self.assertEqual(row["url"],row["urls"]["wan"])
        (self.root/"modules").write_text("paylasim\tdurduruldu\n")
        self.save(connections={"tailscale": {"enabled": True}, "wan": {"enabled": False}})
        with self.assertRaises(s.ShareError): self.save(connections={"wan": {"enabled": True}})

    def test_schema4_is_stable_schema3_migrates_and_schema2_is_rejected(self):
        before=Path(self.m.path).read_bytes()
        self.m.prepare()
        self.assertEqual(before,Path(self.m.path).read_bytes())
        data = self.m.read()
        self.assertEqual(data["schema"], 4)
        old = copy.deepcopy(data); old["schema"] = 2
        s.atomic(self.m.path,old)
        with self.assertRaises(s.ShareError): self.m.read()
        legacy = copy.deepcopy(data); legacy["schema"] = 3
        policy = legacy["items"][0].pop("connections")["tailscale"]
        legacy["items"][0].update(networks=["tailscale"], paused=False,
                                  permission=policy["permission"], expires=policy["expires"])
        s.atomic(self.m.path, legacy)
        self.assertEqual(self.m.read(), data)
        legacy["items"][0].pop("networks")
        s.atomic(self.m.path, legacy)
        with self.assertRaises(s.ShareError): self.m.read()
        data["items"][0].pop("connections")
        s.atomic(self.m.path,data)
        with self.assertRaises(s.ShareError): self.m.read()

    def test_private_nat_and_ipv6_only_addresses_are_not_offered(self):
        for ip in ("", "192.168.1.2", "100.64.0.3", "127.0.0.1", "224.0.0.1", "::1", "192.0.2.1"):
            self.m.env["WAN_IPV4"] = ip
            self.assertFalse(self.m.wan_info()["available"])
            with self.assertRaises(s.ShareError): self.save(connections={"wan": {"enabled": True}},ack_wan_http=True)

    def test_last_active_share_closes_publication(self):
        self.save(connections={"tailscale": {"enabled": False}, "wan": {"enabled": True}},ack_wan_http=True)
        self.running()
        self.assertTrue(self.m.wan_active())
        with patch.object(s.subprocess,"run",return_value=subprocess.CompletedProcess([],0)) as run:
            self.m.publish()
            target=self.root/"sites/paylasim-wan.caddy"
            text=target.read_text()
            self.assertIn("bind 8.8.8.8",text)
            self.assertIn("http://:61010 {",text)  # catch all Host values on only this explicit bind
            self.assertIn("127.0.0.2:61010",text)
            self.assertIn("X-Share-Client-IP {http.request.remote.host}",text)
            self.assertNotIn("panel.",text)
            self.assertNotIn("0.0.0.0",text)
            self.assertIn("respond 404",text)
            calls=run.call_count
            self.m.publish()
            self.assertEqual(run.call_count,calls)
            data=self.m.read(); data["items"][0]["connections"]["wan"]["expires"]=time.time()-1; s.atomic(self.m.path,data)
            self.assertFalse(self.m.wan_active())
            self.m.guard()
            self.assertFalse(target.exists())
            self.assertGreater(run.call_count,calls)

    def test_rollback_restores_registry_and_publication_on_caddy_failure(self):
        self.running()
        old=Path(self.m.path).read_bytes()
        with patch.object(self.m,"restart"), patch.object(s.subprocess,"run",side_effect=[subprocess.CalledProcessError(1,"caddy"),subprocess.CompletedProcess([],0),subprocess.CompletedProcess([],0),subprocess.CompletedProcess([],0)]):
            with self.assertRaises(s.ShareError): self.save(connections={"wan": {"enabled": True}},ack_wan_http=True)
        self.assertEqual(Path(self.m.path).read_bytes(),old)
        self.assertFalse(os.path.exists(self.m.pending))
        self.assertFalse((self.root/"sites/paylasim-wan.caddy").exists())

    def test_vanished_wan_address_closes_publication_with_a_reason(self):
        self.save(connections={"wan": {"enabled": True}},ack_wan_http=True)
        self.running()
        with patch.object(s.subprocess,"run",return_value=subprocess.CompletedProcess([],0)):
            self.m.publish()
            target=self.root/"sites/paylasim-wan.caddy"
            self.assertTrue(target.exists())
            self.assigned.return_value=False
            info=self.m.wan_info()
            self.assertFalse(info["available"])
            self.assertIn("8.8.8.8 artık bu sunucuda değil",info["reason"])
            self.assertFalse(self.m.wan_active())
            self.m.guard()
            self.assertFalse(target.exists())

    def test_address_probe_only_reports_missing_for_eaddrnotavail(self):
        self.assigned_patch.stop()
        for code,present in ((s.errno.EADDRNOTAVAIL,False),(s.errno.EADDRINUSE,True),(s.errno.EMFILE,True)):
            with self.subTest(code=code), patch.object(s.socket.socket,"bind",side_effect=OSError(code,"fixture")):
                self.assertEqual(s.assigned("198.51.100.7"),present)
        self.assertTrue(s.assigned("127.0.0.1"))
        self.assertFalse(s.assigned("192.0.2.77"))

    def test_reload_failure_starts_a_stopped_caddy_but_rolls_back_a_running_one(self):
        self.save(connections={"wan": {"enabled": True}},ack_wan_http=True)
        self.running()
        target=self.root/"sites/paylasim-wan.caddy"
        marker=self.root/"run/share-network-applied.json"
        calls=[]
        def run(argv,**kw):
            calls.append(argv)
            if argv[:2]==["systemctl","reload"]:
                raise subprocess.CalledProcessError(1,argv)
            if argv[:2]==["systemctl","is-active"]:
                return subprocess.CompletedProcess(argv,self.caddy)
            return subprocess.CompletedProcess(argv,0)
        self.caddy=3  # stopped, e.g. it could not bind an address the provider took away
        with patch.object(s.subprocess,"run",side_effect=run):
            self.m.publish()
        self.assertTrue(target.exists())
        self.assertFalse(marker.exists())
        self.assertIn(["systemctl","reset-failed","caddy"],calls)
        self.assertIn(["systemctl","start","--no-block","caddy"],calls)
        target.unlink(); calls.clear()
        self.caddy=0  # running: a failed reload is a real error and the old projection returns
        with patch.object(s.subprocess,"run",side_effect=run), self.assertRaises(s.ShareError):
            self.m.publish()
        self.assertFalse(target.exists())
        self.assertNotIn(["systemctl","start","--no-block","caddy"],calls)

    def test_interrupted_operation_is_recovered_with_credentials_first(self):
        old=self.m.read()
        self.save(connections={"wan": {"enabled": True}},ack_wan_http=True)
        self.running()
        s.atomic(self.m.pending,old)
        with patch.object(self.m,"restart") as restart, patch.object(self.m,"publish") as publish:
            self.m.guard()
            restart.assert_called_once(); publish.assert_called_once()
        self.assertEqual(self.m.read(),old)
        self.assertFalse(os.path.exists(self.m.pending))

    def test_pause_and_missing_root_do_not_leave_active_wan(self):
        self.save(connections={"tailscale": {"enabled": False}, "wan": {"enabled": True}},ack_wan_http=True)
        self.running()
        data=self.m.read(); data["items"][0]["connections"]["wan"]["enabled"]=False; s.atomic(self.m.path,data)
        self.assertFalse(self.m.wan_active())
        data["items"][0]["connections"]["wan"]["enabled"]=True; s.atomic(self.m.path,data)
        (self.root/"srv/alpha").rename(self.root/"srv/old")
        (self.root/"srv/alpha").mkdir()
        self.assertFalse(self.m.wan_active())

    def test_installer_recovery_reloads_credentials_before_clearing_pending(self):
        old=self.m.read()
        self.save(connections={"wan": {"enabled": True}},ack_wan_http=True)
        self.running()
        s.atomic(self.m.pending,old)
        with patch.object(self.m,"restart",side_effect=s.ShareError("injected")):
            with self.assertRaises(s.ShareError): self.m.prepare()
        self.assertTrue(os.path.exists(self.m.pending))
        with patch.object(self.m,"restart") as restart:
            self.m.prepare()
            restart.assert_called_once()
        self.assertFalse(os.path.exists(self.m.pending))
        self.assertEqual(self.m.read(),old)

    def test_panel_caddy_projection_names_wan_and_preserves_proxy_routes(self):
        self.save(connections={"wan": {"enabled": True}},ack_wan_http=True)
        self.running()
        with patch.object(s.subprocess,"run",return_value=subprocess.CompletedProcess([],0)):
            self.m.publish()
        Path(self.env["CADDYFILE"]).write_text("{\n servers 8.8.8.8:61010 {\n timeouts {\n read_header 10s\n }\n }\n}\n")
        p=object.__new__(panel.Panel)
        entries=p.web_view(self.env,[])["entries"]
        self.assertEqual(len(entries),1)
        self.assertEqual(entries[0]["address"],"8.8.8.8:61010")
        self.assertEqual(entries[0]["access"],"wan")
        self.assertIn(dict(path="/s/*",kind="proxy",to="127.0.0.2:61010"),entries[0]["routes"])


if __name__ == "__main__": unittest.main()
