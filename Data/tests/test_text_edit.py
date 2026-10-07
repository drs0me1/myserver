"""DD-249: Files' text editor backend: what the text view offers for editing and how a save replaces a
file (version check, encoding and line endings kept, owner/mode/xattrs copied, atomic, cleaned up).
Temporary directories only."""
import codecs
import hashlib
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "files-panel" / "master-files-panel"
loader = importlib.machinery.SourceFileLoader("files_panel_edit", str(SOURCE))
spec = importlib.util.spec_from_loader(loader.name, loader)
fp = importlib.util.module_from_spec(spec)
loader.exec_module(fp)


def sha(data):
    return hashlib.sha256(data).hexdigest()


class TextEditTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="duzenle-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        (self.root / "etc").mkdir()
        self.files = fp.Files(str(self.root), ".cop")
        self.system = fp.Files(str(self.root), "", system=True)

    def write(self, name, data, mode=0o644):
        path = self.root / "etc" / name
        path.write_bytes(data)
        os.chmod(path, mode)
        return path

    def save(self, name, text, enc="utf-8", files=None, version=None):
        data = (self.root / "etc" / name).read_bytes()
        return (files or self.files).save_text(["etc", name], text, enc, version or sha(data))

    def leftovers(self):
        return [p.name for p in (self.root / "etc").iterdir() if p.name.startswith(".konsol-kayit-")]

    def test_text_view_offers_a_version_for_an_editable_file(self):
        self.write("a.yml", b"ad: nrm\r\nport: 22\r\n")
        r = self.files.text(["etc", "a.yml"], "auto")
        self.assertEqual((r["editable"], r["reason"], r["eol"], r["bom"]), (True, "", "crlf", False))
        self.assertEqual(r["version"], sha(b"ad: nrm\r\nport: 22\r\n"))

    def test_text_view_names_why_a_file_is_not_editable(self):
        self.write("big.log", b"x" * (fp.TEXT_LIMIT + 1))
        self.write("türk.txt", b"\x81\x8d")  # not UTF-8; undefined in Windows-1254
        cases = {"big.log": "1 MiB", "türk.txt": "kayıpsız"}
        for name, words in cases.items():
            with self.subTest(name=name):
                r = self.files.text(["etc", name], "auto")
                self.assertFalse(r["editable"])
                self.assertIsNone(r["version"])
                self.assertIn(words, r["reason"])
        self.write("small.txt", b"x")
        os.link(self.root / "etc/small.txt", self.root / "etc/small2.txt")
        self.assertIn("sabit bağlantı", self.files.text(["etc", "small.txt"], "auto")["reason"])

    def test_save_replaces_the_file_atomically_and_keeps_its_metadata(self):
        path = self.write("a.yml", b"ad: nrm\n", 0o640)
        before = path.stat().st_ino
        r = self.save("a.yml", "ad: nrm\nport: 22\n")
        self.assertEqual(path.read_bytes(), b"ad: nrm\nport: 22\n")
        self.assertEqual((r["version"], r["size"]), (sha(b"ad: nrm\nport: 22\n"), 17))
        st = path.stat()
        self.assertEqual(stat.S_IMODE(st.st_mode), 0o640)
        self.assertNotEqual(st.st_ino, before, "a new file took the old one's place")
        self.assertEqual(self.leftovers(), [])

    def test_line_endings_and_utf8_bom_are_kept(self):
        self.write("crlf.txt", b"bir\r\niki\r\n")
        self.save("crlf.txt", "bir\niki\nüç\n")
        self.assertEqual((self.root / "etc/crlf.txt").read_bytes(), "bir\r\niki\r\nüç\r\n".encode())
        self.write("bom.txt", codecs.BOM_UTF8 + b"a\n")
        self.save("bom.txt", "a\r\nb\n")
        self.assertEqual((self.root / "etc/bom.txt").read_bytes(), codecs.BOM_UTF8 + b"a\nb\n")

    def test_legacy_encodings_are_written_back_and_unencodable_text_is_refused(self):
        self.write("tr.txt", "şeker\n".encode("cp1254"))
        self.save("tr.txt", "şeker ığdır\n", "cp1254")
        self.assertEqual((self.root / "etc/tr.txt").read_bytes(), "şeker ığdır\n".encode("cp1254"))
        with self.assertRaises(fp.PanelError) as err:
            self.save("tr.txt", "emoji \U0001F600\n", "cp1254")
        self.assertEqual(err.exception.code, 400)
        self.assertEqual((self.root / "etc/tr.txt").read_bytes(), "şeker ığdır\n".encode("cp1254"))
        self.assertEqual(self.leftovers(), [])

    def test_a_changed_file_is_never_overwritten(self):
        self.write("a.txt", b"one\n")
        old = sha(b"one\n")
        (self.root / "etc/a.txt").write_bytes(b"two\n")
        with self.assertRaises(fp.PanelError) as err:
            self.files.save_text(["etc", "a.txt"], "mine\n", "utf-8", old)
        self.assertEqual(err.exception.code, 409)
        self.assertEqual((self.root / "etc/a.txt").read_bytes(), b"two\n")

    def test_a_swap_between_the_check_and_the_rename_is_refused(self):
        self.write("a.txt", b"one\n")
        stat_real = os.stat

        def late_stat(path, *a, **kw):
            # The re-check right before the rename sees the swapped file.
            if path == "a.txt" and kw.get("follow_symlinks") is False and not self.swapped:
                self.swapped = True
                (self.root / "etc/a.txt").unlink()
                (self.root / "etc/a.txt").write_bytes(b"someone else\n")
            return stat_real(path, *a, **kw)
        self.swapped = False
        with patch.object(fp.os, "stat", side_effect=late_stat):
            with self.assertRaises(fp.PanelError) as err:
                self.save("a.txt", "mine\n")
        self.assertEqual(err.exception.code, 409)
        self.assertEqual((self.root / "etc/a.txt").read_bytes(), b"someone else\n")
        self.assertEqual(self.leftovers(), [])

    def test_refusals_leave_nothing_behind(self):
        self.write("a.txt", b"x\n")
        bad = [("a.txt", "x", "latin-1", None, 400), ("a.txt", 5, "utf-8", None, 400), ("a.txt", "x", "utf-8", "z" * 64, 400),
               ("a.txt", "y" * (fp.TEXT_LIMIT + 1), "utf-8", None, 413)]
        for name, text, enc, version, code in bad:
            with self.subTest(text=str(text)[:10], enc=enc):
                with self.assertRaises(fp.PanelError) as err:
                    self.files.save_text(["etc", name], text, enc, version or sha(b"x\n"))
                self.assertEqual(err.exception.code, code)
        (self.root / "etc/link").symlink_to("a.txt")
        with self.assertRaises(OSError):
            self.files.save_text(["etc", "link"], "y", "utf-8", sha(b"x\n"))
        (self.root / "etc/dir").mkdir()
        with self.assertRaises(fp.PanelError):
            self.files.save_text(["etc", "dir"], "y", "utf-8", sha(b""))
        self.assertEqual((self.root / "etc/a.txt").read_bytes(), b"x\n")
        self.assertEqual(self.leftovers(), [])

    def test_a_failed_write_removes_the_temporary_file(self):
        self.write("a.txt", b"x\n")
        with patch.object(fp.os, "fsync", side_effect=OSError(28, "No space left on device")):
            with self.assertRaises(OSError):
                self.save("a.txt", "y\n")
        self.assertEqual((self.root / "etc/a.txt").read_bytes(), b"x\n")
        self.assertEqual(self.leftovers(), [])

    def test_setuid_and_foreign_owner_files_are_not_edited(self):
        self.write("s.sh", b"#!/bin/sh\n", 0o4755)
        with self.assertRaises(fp.PanelError) as err:
            self.save("s.sh", "#!/bin/sh\necho\n")
        self.assertEqual(err.exception.code, 403)
        self.assertIn("setuid", self.files.text(["etc", "s.sh"], "auto")["reason"])
        self.write("o.txt", b"x\n")
        with patch.object(fp.os, "geteuid", return_value=os.geteuid() + 1):
            self.assertIn("sahibi", self.files.text(["etc", "o.txt"], "auto")["reason"])
            with self.assertRaises(fp.PanelError):
                self.save("o.txt", "y\n")
            # The root view (DD-235) writes as root: another owner is no obstacle there.
            self.assertTrue(self.system.text(["etc", "o.txt"], "auto")["editable"])

    @unittest.skipUnless(os.geteuid() == 0, "root keeps another account's ownership")
    def test_root_view_edits_read_only_files_and_keeps_their_owner(self):
        path = self.write("sudoers", b"root ALL=(ALL) ALL\n", 0o440)
        os.chown(path, 1234, 4321)
        self.save("sudoers", "root ALL=(ALL) ALL\n# not\n", files=self.system)
        st = path.stat()
        self.assertEqual((stat.S_IMODE(st.st_mode), st.st_uid, st.st_gid), (0o440, 1234, 4321))
        self.assertEqual(path.read_bytes(), b"root ALL=(ALL) ALL\n# not\n")

    def test_extended_attributes_are_copied(self):
        path = self.write("x.txt", b"x\n")
        try:
            os.setxattr(path, "user.konsol", b"1")
        except OSError:
            self.skipTest("no user xattrs on this file system")
        self.save("x.txt", "y\n")
        self.assertEqual(os.getxattr(path, "user.konsol"), b"1")


if __name__ == "__main__":
    unittest.main()
