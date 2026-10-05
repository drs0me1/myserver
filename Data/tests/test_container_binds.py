"""DD-226: a Konsol container's bind sources are pinned at start; mount calls are fakes."""
import hashlib
import importlib.util
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest

DATA = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("container_binds", DATA / "panel/master_container_binds.py")
binds = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(binds)


class FakeMounts:
    """Records mount(2)/umount2(2); a bind 'mounts' the directory behind the source descriptor."""

    def __init__(self):
        self.table = {}
        self.calls = []
        self.before_bind = None
        self.silent = False

    def mount(self, source, target, flags):
        self.calls.append(("mount", source, str(target), flags))
        if flags & binds.MS_BIND:
            if self.before_bind:
                self.before_bind()
            fd = int(source.rsplit("/", 1)[1])
            st = os.fstat(fd)
            if not self.silent:
                self.table[str(target)] = (st.st_dev, st.st_ino)

    def umount(self, target, flags):
        self.calls.append(("umount", str(target), flags))
        if str(target) not in self.table:
            raise OSError(22, "Invalid argument", str(target))
        del self.table[str(target)]

    def identity(self, path):
        return self.table.get(str(path))


class BindTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="container-binds-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        for name in ("srv/data", "srv/media/films", "srv/.cop", "run", "elsewhere/secret"):
            (self.root / name).mkdir(parents=True)
        os.chmod(self.root / "run", 0o755)
        self.env = {"SERVER_ROOT": str(self.root / "srv"), "RUNTIME_DIR": str(self.root / "run"),
                    "KONTEYNER_BAGLAMA_DIR": str(self.root / "run/konteyner-baglama")}
        self.fake = FakeMounts()
        for attr, value in (("ROOT_UID", os.getuid()), ("_mount", self.fake.mount), ("_umount", self.fake.umount),
                            ("_mounted_identity", self.fake.identity)):
            original = getattr(binds, attr)
            setattr(binds, attr, value)
            self.addCleanup(setattr, binds, attr, original)

    def anchor(self, name, index, source):
        return Path(self.env["KONTEYNER_BAGLAMA_DIR"]) / name / hashlib.sha256(("%d:%s" % (index, source)).encode()).hexdigest()[:16]

    def test_bagla_pins_the_walked_directory_and_verifies_it(self):
        data, films = str(self.root / "srv/data"), str(self.root / "srv/media/films")
        anchors = binds.bagla(self.env, "demo", [data, films])
        self.assertEqual(anchors, [self.anchor("demo", 0, data), self.anchor("demo", 1, films)])
        self.assertEqual(anchors, [binds.anchor_path(self.env, "demo", i, s) for i, s in enumerate((data, films))])
        for anchor, source in zip(anchors, (data, films)):
            st = os.stat(source)
            self.assertEqual(self.fake.table[str(anchor)], (st.st_dev, st.st_ino))
        bind, private = [c for c in self.fake.calls if c[0] == "mount"][:2]
        self.assertTrue(bind[1].startswith("/proc/self/fd/"))
        self.assertEqual(bind[3], binds.MS_BIND | binds.MS_REC)
        self.assertEqual((private[1], private[3]), (None, binds.MS_REC | binds.MS_PRIVATE))
        base = Path(self.env["KONTEYNER_BAGLAMA_DIR"])
        self.assertEqual(stat.S_IMODE(base.stat().st_mode), 0o700)

    def test_a_swap_after_the_walk_does_not_redirect_the_mount(self):
        data = self.root / "srv/data"
        original = os.stat(data)

        def swap():  # uid 1000 replaces the folder with a link to a directory it must not reach
            data.rename(self.root / "srv/data.orig")
            data.symlink_to(self.root / "elsewhere/secret", target_is_directory=True)
        self.fake.before_bind = swap
        [anchor] = binds.bagla(self.env, "demo", [str(data)])
        self.assertEqual(self.fake.table[str(anchor)], (original.st_dev, original.st_ino))

    def test_refusals_mount_nothing_and_release_partial_anchors(self):
        (self.root / "srv/link").symlink_to(self.root / "elsewhere/secret", target_is_directory=True)
        (self.root / "srv/media/inner").symlink_to(self.root / "elsewhere", target_is_directory=True)
        (self.root / "srv/file").write_text("x")
        good = str(self.root / "srv/data")
        for source in ("srv/link", "srv/media/inner/secret", "srv/.cop", "elsewhere/secret", "srv", "srv/file",
                       "srv/missing", "srv/data/../media", "srv/da$ta"):
            with self.subTest(source=source):
                self.fake.calls.clear()
                with self.assertRaises(binds.BindError):
                    binds.bagla(self.env, "demo", [good, str(self.root / source)])
                self.assertEqual(self.fake.table, {}, "the first, valid source was released again")
                self.assertFalse((Path(self.env["KONTEYNER_BAGLAMA_DIR"]) / "demo").exists())
        for name in ("../x", "", "a/b", ".hidden", "x" * 65):
            with self.subTest(name=name), self.assertRaises(binds.BindError):
                binds.bagla(self.env, name, [good])

    def test_an_unmounted_or_foreign_anchor_is_never_accepted(self):
        self.fake.silent = True
        with self.assertRaises(binds.BindError):
            binds.bagla(self.env, "demo", [str(self.root / "srv/data")])
        self.assertFalse((Path(self.env["KONTEYNER_BAGLAMA_DIR"]) / "demo").exists())

    def test_unsafe_anchor_directories_are_refused(self):
        os.chmod(self.root / "run", 0o777)
        with self.assertRaises(binds.BindError):
            binds.bagla(self.env, "demo", [str(self.root / "srv/data")])
        os.chmod(self.root / "run", 0o755)
        binds.ROOT_UID = os.getuid() + 1
        with self.assertRaises(binds.BindError):
            binds.bagla(self.env, "demo", [str(self.root / "srv/data")])
        self.assertEqual(self.fake.table, {})

    def test_birak_detaches_every_anchor_and_removes_only_empty_folders(self):
        data = str(self.root / "srv/data")
        [anchor] = binds.bagla(self.env, "demo", [data])
        binds.birak(self.env, "demo")
        self.assertIn(("umount", str(anchor), binds.MNT_DETACH | binds.UMOUNT_NOFOLLOW), self.fake.calls)
        self.assertFalse(anchor.parent.exists())
        self.assertTrue(Path(data).is_dir(), "the source itself is never touched")
        binds.birak(self.env, "demo")  # nothing left: a no-op

    def test_a_stale_anchor_is_released_before_new_pins(self):
        data = str(self.root / "srv/data")
        [anchor] = binds.bagla(self.env, "demo", [data])
        [again] = binds.bagla(self.env, "demo", [data])  # e.g. after kill -9 without ExecStopPost
        self.assertEqual(anchor, again)
        self.assertIn(("umount", str(anchor), binds.MNT_DETACH | binds.UMOUNT_NOFOLLOW), self.fake.calls)
        self.assertEqual(list(self.fake.table), [str(anchor)])

    def test_the_helper_runs_no_package_code_and_takes_no_lock(self):
        source = (DATA / "panel/master_container_binds.py").read_text(encoding="utf-8")
        for word in ("master_settings", "master_container_config", "klasorler", "flock", "PAKET_", "torrent"):
            self.assertNotIn(word, source)


if __name__ == "__main__":
    unittest.main()
