"""Stage 3 actionable share conflicts retain fail-closed configuration reads."""
from pathlib import Path
import unittest

import test_share_manager_networks as fixture

s = fixture.s


class Stage3SharePathTests(unittest.TestCase):
    setUp = fixture.NetworkManagerTests.setUp

    def test_internal_conflict_names_the_reserved_path_and_leaves_registry_untouched(self):
        before = Path(self.m.path).read_bytes()
        with self.assertRaisesRegex(s.ShareError, "iç/geçici alan “downloads/incomplete”"):
            self.m.validate_path(self.m.read(), "downloads")
        self.assertEqual(Path(self.m.path).read_bytes(), before)

    def test_existing_share_conflict_names_its_path_and_exclusion_still_works(self):
        before = Path(self.m.path).read_bytes()
        with self.assertRaisesRegex(s.ShareError, "mevcut paylaşım “alpha”"):
            self.m.validate_path(self.m.read(), "alpha/child")
        path, identity = self.m.validate_path(self.m.read(), "alpha", self.item["id"])
        self.assertEqual((path, identity), ("alpha", self.item["identity"]))
        self.assertEqual(Path(self.m.path).read_bytes(), before)

    def test_custom_temp_conflict_is_distinct_and_unsafe_config_never_falls_back(self):
        profile = self.root / "profile/qBittorrent"
        profile.mkdir()
        config = profile / "qBittorrent.conf"
        config.write_text("Session\\TempPath=%s\n" % (self.root / "srv/media/pending"))
        with self.assertRaisesRegex(s.ShareError, "iç/geçici alan “media/pending”"):
            self.m.validate_path(self.m.read(), "media")
        config.unlink()
        config.symlink_to(self.root / "missing-config")
        with self.assertRaisesRegex(s.ShareError, "güvenli okunamadı"):
            self.m.validate_path(self.m.read(), "alpha", self.item["id"])


if __name__ == "__main__":
    unittest.main()
