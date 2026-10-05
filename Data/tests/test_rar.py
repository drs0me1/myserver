"""RAR boundaries and real extractor tests; only private temporary fixtures."""
import contextlib
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import threading
import time
import unittest
from unittest.mock import patch
import zlib

import test_archives as zip_tests

ar, zip_bytes = zip_tests.ar, zip_tests.zip_bytes


def block(kind, flags, payload=b""):
    body = struct.pack("<BHH", kind, flags, 7 + len(payload)) + payload
    return struct.pack("<H", zlib.crc32(body) & 65535) + body


def stored_rar(entries, host_os=3, mode=0o100644):
    """Generate uncompressed RAR3 fixtures locally, including nested archives."""
    data = b"Rar!\x1a\x07\x00" + block(0x73, 0, b"\0" * 6)
    for name, content in entries:
        name = name.encode("ascii")
        header = struct.pack("<LLBLLBBHL", len(content), len(content), host_os,
                             zlib.crc32(content), 0x50210000, 20, 0x30, len(name), mode)
        data += block(0x74, 0x8000, header + name) + content
    return data + block(0x7b, 0)


class RarTests(unittest.TestCase):
    setUp, tearDown = zip_tests.ArchiveTests.setUp, zip_tests.ArchiveTests.tearDown
    def request(self, operation="zip", **overrides):
        data = zip_tests.ArchiveTests.request(self, operation, **overrides)
        for key in ("nested", "layers"):
            if key not in overrides:
                data.pop(key)
        return data
    run_job = zip_tests.ArchiveTests.run_job
    assert_failed_clean = zip_tests.ArchiveTests.assert_failed_clean

    def fake_rar(self, name="input.rar", entries=None, volumes=None):
        entries = entries or [("hello.txt", b"content")]
        volumes = volumes or [name]
        for volume in volumes:
            (self.root / volume).write_bytes(b"fake volume")
        def output(args, *unused):
            if args[0] == "list":
                yield json.dumps({"volumes": volumes, "entries": [
                    {"name":n, "size":len(c), "directory":False, "crc":zlib.crc32(c)} for n,c in entries]}).encode()
            else:
                yield dict(entries)[args[2]]
        return patch.object(self.manager, "helper_output", side_effect=output)

    def test_old_new_and_later_volume_selection(self):
        for volumes in [["x.rar","x.r00","x.r01"], ["x.part01.rar","x.part02.rar"]]:
            with self.subTest(volumes=volumes), self.fake_rar(volumes[0], volumes=volumes):
                result = self.run_job("unzip", names=[volumes[-1]], name=volumes[0]+"-out")
                self.assertEqual(result["status"],"done",result)
                self.assertEqual((self.root/result["result"]/"hello.txt").read_bytes(),b"content")
                self.assertEqual(result["archives"],1)
                for name in volumes:
                    self.assertEqual((self.root/name).read_bytes(),b"fake volume")

    def test_missing_or_ambiguous_volume_refused_before_helper(self):
        for names in [["a.rar","a.r01"],["a.part02.rar"],["a.part1.rar","a.part01.rar"]]:
            for n in names:
                (self.root/n).write_bytes(b"part")
            with patch.object(self.manager,"helper_output",side_effect=AssertionError("must not run")):
                self.assert_failed_clean(self.run_job("unzip",names=[names[-1]]))
            for n in names:
                (self.root/n).unlink()

    def test_unsafe_duplicate_or_wildcard_members_fail_closed(self):
        for names in [["../escape"],["/escape"],["a\\b"],[".arsiv/jobs.json"],["a\x00bad"],["*.txt"],["same","same"]]:
            with self.subTest(names=names), self.fake_rar(entries=[(name,b"bad") for name in names]):
                self.assert_failed_clean(self.run_job("unzip",names=["input.rar"]))

    def test_source_volume_symlinks_and_hardlinks_rejected(self):
        (self.root/"input.rar").symlink_to(self.root/"source/hello.txt")
        with self.assertRaises((OSError,ar.ArchiveError)):
            self.manager.submit(self.request("unzip",names=["input.rar"]))
        (self.root/"input.rar").unlink()
        os.link(self.root/"source/hello.txt",self.root/"input.rar")
        self.assert_failed_clean(self.run_job("unzip",names=["input.rar"]))

    def test_nested_zip_in_rar_and_preserved_inputs(self):
        with self.fake_rar(entries=[("inside.zip",zip_bytes([("hello.txt",b"nested")]))]):
            result = self.run_job("unzip",names=["input.rar"])
        self.assertEqual(result["status"],"done",result)
        self.assertEqual(result["archives"],2)
        self.assertEqual((self.root/"output/inside/hello.txt").read_bytes(),b"nested")
        self.assertTrue((self.root/"output/inside.zip").exists())

    def test_corrupt_stream_and_changed_source_never_publish(self):
        for bad in ("crc","changed"):
            with self.fake_rar() as helper:
                original = helper.side_effect
                def output(args,*rest):
                    if args[0] == "stream":
                        if bad == "changed":
                            (self.root/"input.rar").write_bytes(b"changed")
                        yield b"content" if bad == "changed" else b"corrupt"
                    else:
                        yield from original(args,*rest)
                helper.side_effect = output
                self.assert_failed_clean(self.run_job("unzip",names=["input.rar"]))

    def test_global_byte_and_entry_limits(self):
        with self.fake_rar(entries=[("one",b"x"*100),("two",b"x"*100)]):
            with patch.object(ar,"MAX_BYTES",150):
                self.assert_failed_clean(self.run_job("unzip",names=["input.rar"]))
            with patch.object(ar,"MAX_ENTRIES",1):
                self.assert_failed_clean(self.run_job("unzip",names=["input.rar"]))

    def test_helper_cancel_timeout_and_output_cap(self):
        # A real subprocess that never writes must still be cancellable/reaped.
        helper = self.root/"wait-helper.py"
        helper.write_text("import os,time\nprint(os.getpid(),flush=True)\ntime.sleep(30)\n")
        job={"bytes":0,"entries":0}
        with patch.object(ar,"RAR_HELPER",str(helper)):
            event=threading.Event()
            with contextlib.closing(self.manager.helper_output([],job,event,time.monotonic()+5,1024)) as chunks:
                pid=int(next(chunks))
                event.set()
                with self.assertRaises(ar.Cancelled): next(chunks)
            with self.assertRaises(ProcessLookupError): os.kill(pid,0)
            with self.assertRaises(ar.ArchiveError):
                list(self.manager.helper_output([],job,threading.Event(),time.monotonic()+.15,1024))
            with self.assertRaises(ar.ArchiveError):
                list(self.manager.helper_output([],job,threading.Event(),time.monotonic()+5,1))

    @unittest.skipUnless(sys.platform == "linux" and os.path.isfile("/usr/bin/unrar"), "real Linux unrar required")
    def test_real_nested_rar_zip_rar(self):
        deepest=stored_rar([("hello.txt",b"native nested RAR")])
        middle=zip_bytes([("inner.rar",deepest)])
        # DOS attributes overlap S_IFCHR, but this is a regular Windows file.
        (self.root/"input.rar").write_bytes(stored_rar([("middle.zip",middle)], host_os=2, mode=0x2020))
        result=self.run_job("unzip",names=["input.rar"])
        self.assertEqual(result["status"],"done",result)
        self.assertEqual(result["archives"],3)
        self.assertEqual((self.root/"output/middle/inner/hello.txt").read_bytes(),b"native nested RAR")
        self.assertTrue((self.root/"input.rar").exists())
        self.assertTrue((self.root/"output/middle.zip").exists())
        self.assertTrue((self.root/"output/middle/inner.rar").exists())

    @unittest.skipUnless(os.environ.get("RAR_FIXTURES"), "optional upstream RAR fixtures not supplied")
    def test_real_rar3_rar5_solid_volumes_and_unsafe_entries(self):
        fixtures=Path(os.environ["RAR_FIXTURES"])
        for source in fixtures.glob("*.rar"):
            shutil.copyfile(source,self.root/source.name)
        for suffix in ("r00","r01"):
            for source in fixtures.glob("*."+suffix):
                shutil.copyfile(source,self.root/source.name)
        for name in ["rar3-solid.rar","rar5-solid.rar","rar3-old.rar","rar3-vols.part2.rar","rar5-vols.part1.rar","rar5-blake.rar","unicode.rar"]:
            with self.subTest(name=name):
                result=self.run_job("unzip",names=[name],name=name+"-out")
                self.assertEqual(result["status"],"done",result)
                self.assertGreater(result["entries"],0)
        for name in ["rar5-hpsw.rar","rar5-psw.rar","rar3-symlink-unix.rar","rar5-hlink.rar","rar5-dups.rar"]:
            with self.subTest(name=name):
                self.assert_failed_clean(self.run_job("unzip",names=[name]))

        # A real compressed multipart set inside RAR, reverse header order:
        # process all three parts once, retaining every part beside the result.
        names=["rar3-vols.part3.rar","rar3-vols.part2.rar","rar3-vols.part1.rar"]
        (self.root/"nested.rar").write_bytes(stored_rar([(n,(fixtures/n).read_bytes()) for n in names]))
        result=self.run_job("unzip",names=["nested.rar"],name="nested-out")
        self.assertEqual(result["status"],"done",result)
        self.assertEqual(result["archives"],2)
        self.assertTrue((self.root/"nested-out/rar3-vols/vols/bigfile.txt").is_file())
        self.assertTrue(all((self.root/"nested-out"/n).is_file() for n in names))

        # Missing final part: sequential filenames alone cannot detect it.
        (self.root/"rar5-vols.part3.rar").unlink()
        self.assert_failed_clean(self.run_job("unzip",names=["rar5-vols.part1.rar"]))


if __name__ == "__main__":
    unittest.main()
