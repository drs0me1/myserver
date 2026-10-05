"""Schema-4 connection policy regressions; temporary files, no host changes.

Run with Python 3.13 unittest. Fixtures deliberately contain no legacy policy
fields and do not depend on the schema-3 network test fixture.
"""
import copy
import itertools
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "panel"))
import master_shares as shares


NOW = 2_000_000_000
PASSWORD = "connection-fixture-password"
SCOPES = ("tailscale", "wan")
LEGACY_FIELDS = {"networks", "permission", "paused", "expires"}
SHARED_FIELDS = ("id", "path", "identity", "name", "username", "salt", "hash", "created")


def connection(enabled=True, permission="ro", expires=NOW + 604800):
    return {"enabled": enabled, "permission": permission, "expires": expires}


class ShareConnectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.salt, cls.digest = shares.password_hash(PASSWORD)

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="share-connections-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        for folder in ("srv/alpha", "srv/beta", "run", "profile"):
            (self.root / folder).mkdir(parents=True)
        self.env = {
            "SHARE_STATE_FILE": str(self.root / "registry.json"),
            "MODULES_FILE": str(self.root / "modules"),
            "RUNTIME_DIR": str(self.root / "run"),
            "SERVER_ROOT": str(self.root / "srv"),
            "DOWNLOADS_PATH": str(self.root / "srv/downloads"),
            "FILES_PANEL_TRASH": ".cop",
            "SHARE_DIR": ".pay", "SETTINGS_FILE": str(self.root / "settings.json"),
            "SETTINGS_PENDING_FILE": str(self.root / "settings-pending"),
            "SHARE_PORT": "61010", "SHARE_HTTPS_PORT": "443",
            "TAILSCALE_IPV4": "100.64.0.2", "WAN_IPV4": "8.8.8.8",
            "SHARE_WAN_BACKEND": "127.0.0.2",
        }
        state = self.root / "state.env"
        state.write_text("".join(f"{key}={value}\n" for key, value in self.env.items()))
        Path(self.env["MODULES_FILE"]).write_text("paylasim\tcalisiyor\n")
        self.manager = shares.Manager(state)
        self.clock = self.enterContext(patch.object(shares.time, "time", return_value=NOW))
        self.assigned = self.enterContext(patch.object(shares, "assigned", return_value=True))
        self.restart = self.enterContext(patch.object(self.manager, "restart"))
        self.publish = self.enterContext(patch.object(self.manager, "publish"))
        # An accidental lifecycle call must never execute a host command.
        self.enterContext(patch.object(shares.subprocess, "run",
                                       side_effect=AssertionError("unexpected host command")))
        fd = shares.open_dir(self.env["SERVER_ROOT"], ["alpha"])
        try:
            folder_identity = shares.identity(fd)
        finally:
            os.close(fd)
        self.item = {
            "id": "a" * 24, "path": "alpha", "identity": folder_identity,
            "name": "alpha", "username": "fixture-user", "salt": self.salt,
            "hash": self.digest, "created": NOW - 200, "changed": NOW - 100,
            "connections": {"tailscale": connection(), "wan": connection(False)},
        }
        self.data = {
            "schema": 4, "root": self.env["SERVER_ROOT"],
            "limits": dict(shares.DEFAULT_LIMITS), "items": [self.item],
            "blocked": [".cop", ".pay"], "protected": [],
        }
        self.write(self.data)

    def write(self, data, path=None):
        shares.atomic(path or self.manager.path, data)

    def disk(self):
        return json.loads(Path(self.manager.path).read_text())

    def save(self, **fields):
        return self.manager.change("save", {"id": self.item["id"], **fields})

    def legacy(self, networks=("tailscale",), paused=False, permission="ro", expires=None):
        data = copy.deepcopy(self.data)
        data["schema"] = 3
        item = data["items"][0]
        item.pop("connections")
        item.update(networks=list(networks), paused=paused, permission=permission, expires=expires)
        return data

    def assert_canonical(self, data):
        self.assertEqual(data["schema"], 4)
        for item in data["items"]:
            self.assertFalse(LEGACY_FIELDS.intersection(item))
            self.assertEqual(set(item["connections"]), set(SCOPES))
            for policy in item["connections"].values():
                self.assertEqual(set(policy), {"enabled", "permission", "expires"})
                self.assertIs(type(policy["enabled"]), bool)
                self.assertIn(policy["permission"], ("ro", "rw"))

    def assert_rejected(self, fields, action="save", reload=False):
        before = Path(self.manager.path).read_bytes()
        with self.assertRaises(shares.ShareError) as error:
            self.manager.change(action, {"id": self.item["id"], **fields})
        if reload:
            self.assertRegex(str(error.exception).lower(), r"yenile|reload|refresh")
        self.assertEqual(Path(self.manager.path).read_bytes(), before)
        self.assertFalse(Path(self.manager.pending).exists())
        self.restart.assert_not_called()
        self.publish.assert_not_called()

    def test_schema3_load_migrates_every_network_pause_permission_and_expiry_in_memory(self):
        cases = itertools.product((("tailscale",), ("wan",), SCOPES),
                                  (False, True), ("ro", "rw"), (None, NOW - 1, NOW + 1234))
        for networks, paused, permission, expires in cases:
            with self.subTest(networks=networks, paused=paused, permission=permission, expires=expires):
                legacy = self.legacy(networks, paused, permission, expires)
                self.write(legacy)
                before = Path(self.manager.path).read_bytes()
                loaded = shares.load(self.manager.path)
                self.assert_canonical(loaded)
                item = loaded["items"][0]
                for key in (*SHARED_FIELDS, "changed"):
                    self.assertEqual(item[key], legacy["items"][0][key])
                for scope in SCOPES:
                    self.assertEqual(item["connections"][scope],
                                     connection(scope in networks and not paused, permission, expires))
                self.assertIsNot(item["connections"]["tailscale"], item["connections"]["wan"])
                self.assertEqual(Path(self.manager.path).read_bytes(), before)

    def test_prepare_persists_upgrade_once_without_rotating_account(self):
        self.write(self.legacy(("wan",), permission="rw", expires=NOW + 90))
        expected = shares.load(self.manager.path)
        self.manager.prepare()
        self.assert_canonical(self.disk())
        self.assertEqual(self.disk(), expected)
        self.assertEqual(Path(self.manager.path).stat().st_mode & 0o777, 0o600)
        self.assertTrue(shares.password_ok(self.disk()["items"][0], PASSWORD))
        before = Path(self.manager.path).stat().st_mtime_ns
        with patch.object(shares, "atomic", wraps=shares.atomic) as atomic:
            self.manager.prepare()
            atomic.assert_not_called()
        self.assertEqual(Path(self.manager.path).stat().st_mtime_ns, before)

    def test_prepare_creates_empty_schema4_registry(self):
        Path(self.manager.path).unlink()
        self.manager.prepare()
        self.assert_canonical(self.disk())
        self.assertEqual(self.disk()["items"], [])

    def test_invalid_schema_or_connection_shape_fails_closed_without_rewriting(self):
        variants = []
        for schema in (None, 2, 5, "4", True):
            variants.append(dict(copy.deepcopy(self.data), schema=schema))
        for policies in (None, [], {}, {"tailscale": connection()},
                         {**self.item["connections"], "vpn": connection()}):
            data = copy.deepcopy(self.data)
            data["items"][0]["connections"] = policies
            variants.append(data)
        for field, value in (("enabled", 1), ("enabled", "true"), ("permission", "write"),
                             ("permission", None), ("expires", True), ("expires", "tomorrow"),
                             ("expires", float("nan")), ("expires", float("inf"))):
            data = copy.deepcopy(self.data)
            data["items"][0]["connections"]["wan"][field] = value
            variants.append(data)
        for field in ("enabled", "permission", "expires"):
            data = copy.deepcopy(self.data)
            del data["items"][0]["connections"]["tailscale"][field]
            variants.append(data)
        for field, value in (("permission", "ro"), ("paused", False),
                             ("networks", ["tailscale"]), ("expires", None)):
            data = copy.deepcopy(self.data)
            data["items"][0][field] = value
            variants.append(data)
        mixed_legacy = self.legacy()
        mixed_legacy["items"][0]["connections"] = copy.deepcopy(self.item["connections"])
        variants.append(mixed_legacy)
        for items in (None, {}, [None]):
            variants.append(dict(copy.deepcopy(self.data), items=items))
        variants.append(self.legacy(networks=()))
        missing_expiry = self.legacy()
        del missing_expiry["items"][0]["expires"]
        variants.append(missing_expiry)
        for index, data in enumerate(variants):
            with self.subTest(case=index):
                self.write(data)
                before = Path(self.manager.path).read_bytes()
                for operation in (self.manager.read, self.manager.prepare, self.manager.public,
                                  lambda: self.save(connections={"tailscale": {"enabled": False}})):
                    with self.assertRaises(shares.ShareError):
                        operation()
                self.assertEqual(Path(self.manager.path).read_bytes(), before)
                self.assertFalse(Path(self.manager.pending).exists())

    def test_legacy_and_mixed_api_writes_require_reload(self):
        for field, value in (("networks", ["wan"]), ("permission", "rw"), ("paused", True),
                             ("expires", None), ("days", 7), ("ack_write", True)):
            for mixed in (False, True):
                with self.subTest(field=field, mixed=mixed):
                    request = {field: value}
                    if mixed:
                        request["connections"] = {"tailscale": {"enabled": False}}
                    self.assert_rejected(request, reload=True)
        self.assert_rejected({"paused": True}, action="pause", reload=True)

    def test_new_account_defaults_to_tail_ro_seven_days_and_disabled_wan(self):
        self.manager.change("save", {"path": "beta", "username": "new-reader", "password": PASSWORD})
        created = next(i for i in self.disk()["items"] if i["path"] == "beta")
        self.assert_canonical(self.disk())
        self.assertEqual(created["connections"], {
            "tailscale": connection(), "wan": connection(False),
        })
        self.assertEqual((created["created"], created["changed"]), (NOW, NOW))
        self.assertTrue(shares.password_ok(created, PASSWORD))

    def test_closed_tailscale_publication_blocks_new_and_reenabled_tail_connections(self):
        # DD-193: the folder switch cannot be turned on while Settings → Caddy keeps
        # WebDAV off on Tailscale; an existing policy stays as saved and can be closed.
        web = {"paylasim": {"tail": False, "enabled": False, "domain": ""}}
        Path(self.env["SETTINGS_FILE"]).write_text(json.dumps({"web": web}))
        self.manager.change("save", {"path": "beta", "username": "new-reader", "password": PASSWORD})
        created = next(i for i in self.disk()["items"] if i["path"] == "beta")
        self.assertEqual(created["connections"]["tailscale"], connection(False))
        self.assertTrue(self.disk()["items"][0]["connections"]["tailscale"]["enabled"])
        self.restart.reset_mock()
        self.publish.reset_mock()
        with self.assertRaises(shares.ShareError) as error:
            self.manager.change("save", {"id": created["id"], "connections": {"tailscale": {"enabled": True}}})
        self.assertIn("Ayarlar → Caddy", str(error.exception))
        self.restart.assert_not_called()
        self.save(connections={"tailscale": {"enabled": False}})
        self.restart.reset_mock()
        self.publish.reset_mock()
        self.assert_rejected({"connections": {"tailscale": {"enabled": True}}})
        web["paylasim"]["tail"] = True
        Path(self.env["SETTINGS_FILE"]).write_text(json.dumps({"web": web}))
        self.save(connections={"tailscale": {"enabled": True}})
        self.assertTrue(self.disk()["items"][0]["connections"]["tailscale"]["enabled"])

    def test_partial_patch_preserves_other_scope_credentials_and_absolute_expiry(self):
        self.item["connections"] = {"tailscale": connection(True, "rw", NOW + 111),
                                    "wan": connection(True, "ro", NOW + 222)}
        self.write(self.data)
        original = copy.deepcopy(self.item)
        for scope in SCOPES:
            with self.subTest(scope=scope):
                self.write(self.data)
                self.clock.return_value = NOW + 40
                self.save(connections={scope: {"enabled": False}})
                actual = self.disk()["items"][0]
                expected = copy.deepcopy(original)
                expected["connections"][scope]["enabled"] = False
                expected["changed"] = NOW + 40
                self.assertEqual(actual, expected)
                self.save(connections={scope: {"enabled": True}}, ack_wan_http=True)
                actual = self.disk()["items"][0]
                self.assertEqual(actual["connections"], original["connections"])
                for key in SHARED_FIELDS:
                    self.assertEqual(actual[key], original[key])

    def test_days_patch_changes_only_selected_expiry(self):
        for scope, days in itertools.product(SCOPES, (0, 1, 7, 30)):
            with self.subTest(scope=scope, days=days):
                self.write(self.data)
                self.save(connections={scope: {"days": days}})
                expected = copy.deepcopy(self.item["connections"])
                expected[scope]["expires"] = NOW + days * 86400 if days else None
                self.assertEqual(self.disk()["items"][0]["connections"], expected)

    def test_toggle_does_not_renew_expired_connection_or_rebind_replaced_folder(self):
        self.item["connections"]["wan"] = connection(False, "rw", NOW - 1)
        self.write(self.data)
        (self.root / "srv/alpha").rename(self.root / "srv/original")
        (self.root / "srv/alpha").mkdir()
        self.save(connections={"wan": {"enabled": True}}, ack_wan_http=True)
        actual = self.disk()["items"][0]
        self.assertEqual(actual["identity"], self.item["identity"])
        self.assertEqual(actual["connections"]["wan"], connection(True, "rw", NOW - 1))
        self.assertFalse(self.manager.wan_active())

    def test_both_off_retains_account_and_can_resume_without_new_password(self):
        self.save(connections={scope: {"enabled": False} for scope in SCOPES})
        self.assertEqual(len(self.disk()["items"]), 1)
        actual = self.disk()["items"][0]
        for key in SHARED_FIELDS:
            self.assertEqual(actual[key], self.item[key])
        self.assertTrue(shares.password_ok(actual, PASSWORD))
        row = self.manager.public()["items"][0]
        self.assertEqual(row["urls"], {})
        self.assertEqual(row["url"], "")
        self.save(connections={"tailscale": {"enabled": True}})
        self.assertEqual(self.disk()["items"][0]["connections"], self.item["connections"])

    def test_connections_patch_types_and_selected_fields_are_strict(self):
        invalid = [None, [], "wan", {"vpn": {}}, {"tailscale": None}, {"wan": []}]
        for field, values in {
            "enabled": (None, 0, 1, "true"),
            "permission": (None, "RW", "write", False),
            "days": (None, True, "7", 7.0, -1, 2),
            "expires": (None,), "paused": (False,), "networks": (["wan"],),
            "ack_wan_http": (True,), "unknown": (True,),
        }.items():
            invalid.extend({"tailscale": {field: value}} for value in values)
        for policy in invalid:
            with self.subTest(policy=policy):
                self.assert_rejected({"connections": policy})

    def test_explicit_rw_requires_true_ack_in_the_same_scope_patch(self):
        for scope, ack in itertools.product(SCOPES, (None, False, 1, "true")):
            with self.subTest(scope=scope, ack=ack):
                self.assert_rejected({"connections": {scope: {"permission": "rw", "ack_write": ack}}})
        self.assert_rejected({"connections": {
            "tailscale": {"ack_write": True}, "wan": {"permission": "rw"},
        }})
        self.save(connections={"tailscale": {"permission": "rw", "ack_write": True}})
        self.assertEqual(self.disk()["items"][0]["connections"]["tailscale"]["permission"], "rw")
        self.restart.reset_mock()
        self.publish.reset_mock()
        self.assert_rejected({"connections": {"tailscale": {"permission": "rw"}}})

    def test_http_wan_enable_and_reenable_require_explicit_true_consent(self):
        for ack in (None, False, 1, "true"):
            with self.subTest(ack=ack):
                self.assert_rejected({"connections": {"wan": {"enabled": True}}, "ack_wan_http": ack})
        self.save(connections={"wan": {"enabled": True}}, ack_wan_http=True)
        self.save(connections={"wan": {"enabled": False}})
        self.restart.reset_mock()
        self.publish.reset_mock()
        self.assert_rejected({"connections": {"wan": {"enabled": True}}})

    def test_https_wan_enable_needs_no_http_consent_but_unavailable_wan_is_rejected(self):
        Path(self.env["SETTINGS_FILE"]).write_text(json.dumps({"https": {"domain": "dav.example.org"}}))
        self.save(connections={"wan": {"enabled": True}})
        self.assertTrue(self.disk()["items"][0]["connections"]["wan"]["enabled"])
        self.write(self.data)
        self.assigned.return_value = False
        self.restart.reset_mock()
        self.publish.reset_mock()
        self.assert_rejected({"connections": {"wan": {"enabled": True}}, "ack_wan_http": True})

    def test_public_policy_projects_each_scope_and_only_active_urls_without_secrets(self):
        self.item["connections"] = {"tailscale": connection(True, "rw", NOW),
                                    "wan": connection(True, "ro", None)}
        self.write(self.data)
        before = Path(self.manager.path).read_bytes()
        row = self.manager.public()["items"][0]
        for scope in SCOPES:
            policy = row["connections"][scope]
            for key, value in self.item["connections"][scope].items():
                self.assertEqual(policy[key], value)
            self.assertTrue({"expired", "available", "active", "reason", "url"} <= policy.keys())
            for key in ("expired", "available", "active"):
                self.assertIs(type(policy[key]), bool)
        tail, wan = (row["connections"][scope] for scope in SCOPES)
        self.assertTrue(tail["expired"])
        self.assertFalse(tail["active"])
        self.assertTrue(tail["reason"])
        self.assertEqual(tail["url"], f"http://100.64.0.2:61010/s/{self.item['id']}/")
        self.assertTrue(wan["active"])
        self.assertFalse(wan["expired"])
        self.assertEqual(wan["reason"], "")
        self.assertEqual(row["urls"], {"wan": wan["url"]})
        self.assertEqual(row["url"], wan["url"])
        self.assertEqual(wan["url"], f"http://8.8.8.8:61010/s/{self.item['id']}/")
        self.assertFalse({"salt", "hash", "password"}.intersection(row))
        self.assertNotIn(self.digest, json.dumps(row))
        self.assertEqual(Path(self.manager.path).read_bytes(), before)

    def test_public_missing_folder_and_unavailable_wan_have_no_active_urls(self):
        self.item["connections"]["wan"]["enabled"] = True
        self.write(self.data)
        self.assigned.return_value = False
        row = self.manager.public()["items"][0]
        self.assertEqual(set(row["urls"]), {"tailscale"})
        self.assertFalse(row["connections"]["wan"]["available"])
        self.assertTrue(row["connections"]["wan"]["reason"])
        (self.root / "srv/alpha").rename(self.root / "srv/moved")
        row = self.manager.public()["items"][0]
        self.assertFalse(row["available"])
        self.assertEqual(row["urls"], {})
        for policy in row["connections"].values():
            self.assertFalse(policy["active"])
            self.assertTrue(policy["reason"])
            self.assertEqual(policy["url"],
                             f"http://100.64.0.2:61010/s/{self.item['id']}/" if policy["available"] else "")

    def test_legacy_http_wan_activity_uses_only_wan_enable_and_expiry(self):
        for tail_expiry, wan_enabled, wan_expiry, expected in (
            (NOW - 1, True, NOW + 1, True), (None, True, NOW, False),
            (None, False, None, False), (NOW - 1, True, None, True),
        ):
            with self.subTest(tail_expiry=tail_expiry, wan_enabled=wan_enabled, wan_expiry=wan_expiry):
                self.item["connections"] = {"tailscale": connection(True, "rw", tail_expiry),
                                            "wan": connection(wan_enabled, "ro", wan_expiry)}
                self.write(self.data)
                self.assertEqual(self.manager.wan_active(), expected)
        Path(self.env["MODULES_FILE"]).write_text("paylasim\tdurduruldu\n")
        self.assertFalse(self.manager.wan_active())

    def test_pending_schema3_recovery_persists4_before_restart_and_keeps_pending_on_failure(self):
        legacy = self.legacy(("wan",), paused=True, permission="rw", expires=NOW - 10)
        for operation in (self.manager.prepare, self.manager.guard):
            with self.subTest(operation=operation.__name__):
                self.write(self.data)
                self.write(legacy, self.manager.pending)
                self.restart.reset_mock()
                self.publish.reset_mock()

                def restarting():
                    self.assert_canonical(self.disk())
                    self.assertTrue(Path(self.manager.pending).exists())
                    raise shares.ShareError("fixture restart failure")

                self.restart.side_effect = restarting
                with self.assertRaises(shares.ShareError):
                    operation()
                self.assertTrue(Path(self.manager.pending).exists())
                self.publish.assert_not_called()
                self.restart.side_effect = None
                operation()
                self.assertFalse(Path(self.manager.pending).exists())
                self.assertEqual(self.disk(), shares.load(self.manager.path))
                restored = self.disk()["items"][0]
                for key in SHARED_FIELDS:
                    self.assertEqual(restored[key], self.item[key])
                self.assertEqual(restored["connections"], {
                    scope: connection(False, "rw", NOW - 10) for scope in SCOPES
                })

    def test_invalid_pending_schema_never_overwrites_valid_registry_or_clears_recovery(self):
        pending = copy.deepcopy(self.data)
        pending["schema"] = 2
        self.write(pending, self.manager.pending)
        before = Path(self.manager.path).read_bytes()
        pending_before = Path(self.manager.pending).read_bytes()
        for operation in (self.manager.prepare, self.manager.guard):
            with self.subTest(operation=operation.__name__), self.assertRaises(shares.ShareError):
                operation()
            self.assertEqual(Path(self.manager.path).read_bytes(), before)
            self.assertEqual(Path(self.manager.pending).read_bytes(), pending_before)
        self.restart.assert_not_called()
        self.publish.assert_not_called()

    def test_schema_migration_does_not_import_custom_runtime_limits(self):
        for data in (copy.deepcopy(self.data), self.legacy()):
            with self.subTest(schema=data["schema"]):
                data["limits"] = {"wan_connections": 10000, "tail_auth_parallel": 10000}
                self.write(data)
                self.assertEqual(shares.load(self.manager.path)["limits"], shares.DEFAULT_LIMITS)

    def test_failed_publication_rolls_back_both_policies_and_credentials(self):
        before = Path(self.manager.path).read_bytes()
        self.publish.side_effect = [shares.ShareError("fixture publication failure"), None]
        with self.assertRaises(shares.ShareError):
            self.save(connections={"tailscale": {"enabled": False},
                                   "wan": {"enabled": True, "permission": "rw", "ack_write": True}},
                      ack_wan_http=True)
        self.assertEqual(Path(self.manager.path).read_bytes(), before)
        self.assertEqual(self.restart.call_count, 2)
        self.assertEqual(self.publish.call_count, 2)
        self.assertFalse(Path(self.manager.pending).exists())


if __name__ == "__main__":
    unittest.main()
