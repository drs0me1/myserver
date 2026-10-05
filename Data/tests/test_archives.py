"""Real ZIP/filesystem tests; only TemporaryDirectory fixtures are modified."""
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import stat
import struct
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

SOURCE = Path(os.environ.get("KONSOL_FILES_BACKEND", str(Path(__file__).resolve().parents[1] / "files-panel" / "master-files-panel")))
loader = importlib.machinery.SourceFileLoader("files_archive_test", str(SOURCE))
spec = importlib.util.spec_from_loader(loader.name, loader)
files_module = importlib.util.module_from_spec(spec)
loader.exec_module(files_module)
import master_archives as ar


def zip_bytes(entries):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries:
            archive.writestr(name, content)
    return out.getvalue()


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="konsol-archive-test-")
        self.root = Path(self.tmp.name)
        self.files = files_module.Files(str(self.root), ".cop", ".pay", ".arsiv")
        self.manager = ar.Archives(self.files, ".arsiv", files_module.rename_noreplace, files_module.rmtree_at)
        (self.root / "source").mkdir()
        (self.root / "source" / "hello.txt").write_text("Merhaba İstanbul\n" * 50)

    def tearDown(self):
        if self.manager.thread:
            self.manager.thread.join(5)
        self.tmp.cleanup()

    def request(self, operation="zip", **overrides):
        values = dict(operation=operation, path="", names=["source"] if operation == "zip" else ["input.zip"],
                      target="", name="output.zip" if operation == "zip" else "output", nested=True, layers=3, conflict="rename")
        values.update(overrides)
        return values

    def run_job(self, operation="zip", **overrides):
        job = self.manager.submit(self.request(operation, **overrides))
        self.manager.thread.join(5)
        self.assertFalse(self.manager.thread.is_alive())
        return next(j for j in self.manager.status()["items"] if j["id"] == job["id"])

    def input(self, entries):
        (self.root / "input.zip").write_bytes(zip_bytes(entries))

    def assert_failed_clean(self, result):
        self.assertEqual(result["status"], "failed", result)
        self.assertFalse((self.root / "output").exists())
        self.assertEqual(sorted(p.name for p in (self.root / ".arsiv").iterdir()), ["jobs.json"])

    def test_each_finished_or_interrupted_job_is_reported_once_for_the_log(self):
        reported = []
        self.manager = ar.Archives(self.files, ".arsiv", files_module.rename_noreplace, files_module.rmtree_at,
                                   report=lambda job: reported.append((job["name"], job["status"])))
        result = self.run_job()
        self.assertEqual(result["status"], "done", result)
        self.assertEqual(reported, [("output.zip", "done")])
        # A job the service did not finish is reported when the service starts again.
        history = json.loads((self.root / ".arsiv" / "jobs.json").read_text())
        history[0]["status"] = "running"
        (self.root / ".arsiv" / "jobs.json").write_text(json.dumps(history))
        reported.clear()
        ar.Archives(self.files, ".arsiv", files_module.rename_noreplace, files_module.rmtree_at,
                    report=lambda job: reported.append((job["name"], job["status"])))
        self.assertEqual(reported, [("output.zip", "interrupted")])

    def test_log_line_matches_the_console_audit_format(self):
        job = {"names": ["a.rar", "b", "c", "d"], "name": "cikti", "status": "failed", "message": "Bozuk arşiv."}
        with contextlib.redirect_stdout(io.StringIO()) as out:
            files_module.report_archive(job)
            files_module.report_archive(dict(job, status="done", message="Tamamlandı; kaynaklar korundu."))
        lines = out.getvalue().splitlines()
        self.assertEqual(lines[0], 'dosya: konsol - arsiv-sonuc "a.rar, b, c (+1) → cikti: Bozuk arşiv." -> hata')
        self.assertTrue(lines[1].endswith("-> ok"))
        pattern = r"^(panel|dosya): (\S+) (\S+) (\S+) (.*) -> (ok|hata)$"  # ACTION_RE in master-panel
        self.assertTrue(all(re.match(pattern, line) for line in lines))

    def test_next_job_waits_for_the_previous_cleanup_instead_of_refusing(self):
        release = threading.Event()
        original = self.manager.remove_tree
        def slow_cleanup(*args):
            release.wait(3)
            return original(*args)
        with patch.object(self.manager, "remove_tree", side_effect=slow_cleanup):
            first = self.manager.submit(self.request())
            deadline = time.monotonic() + 5
            while next(j for j in self.manager.status()["items"] if j["id"] == first["id"])["status"] in ("queued", "running"):
                self.assertLess(time.monotonic(), deadline)
                time.sleep(0.01)
            self.assertTrue(self.manager.thread.is_alive())  # "done", still cleaning its staging area
            threading.Timer(0.2, release.set).start()
            second = self.manager.submit(self.request(name="second.zip"))
        self.manager.thread.join(5)
        self.assertEqual(next(j for j in self.manager.status()["items"] if j["id"] == second["id"])["status"], "done")

    def test_damaged_history_is_set_aside_and_service_starts(self):
        self.manager.thread = None
        (self.root / ".arsiv" / "jobs.json").write_text("{not json")
        with contextlib.redirect_stderr(io.StringIO()) as err:
            manager = ar.Archives(self.files, ".arsiv", files_module.rename_noreplace, files_module.rmtree_at)
        self.assertEqual(manager.status()["items"], [])
        kept = [p.name for p in (self.root / ".arsiv").iterdir() if p.name.startswith("jobs.json.bozuk-")]
        self.assertEqual(len(kept), 1)
        self.assertEqual((self.root / ".arsiv" / kept[0]).read_text(), "{not json")
        self.assertIn(kept[0], err.getvalue())
        self.assertEqual(json.loads((self.root / ".arsiv" / "jobs.json").read_text()), [])

    def test_compressed_media_is_stored_and_text_is_deflated(self):
        (self.root / "source" / "Film.MKV").write_bytes(b"\0" * 4096)
        (self.root / "source" / "kapak.jpg").write_bytes(b"\0" * 4096)
        result = self.run_job()
        self.assertEqual(result["status"], "done", result)
        with zipfile.ZipFile(self.root / "output.zip") as archive:
            kinds = {info.filename: info.compress_type for info in archive.infolist() if not info.is_dir()}
        self.assertEqual(kinds, {"source/hello.txt": zipfile.ZIP_DEFLATED, "source/Film.MKV": zipfile.ZIP_STORED,
                                 "source/kapak.jpg": zipfile.ZIP_STORED})

    def test_round_trip_unicode_and_source_preserved(self):
        (self.root / "source" / "Boş klasör").mkdir()
        result = self.run_job()
        self.assertEqual(result["status"], "done", result)
        original = (self.root / "source" / "hello.txt").read_bytes()
        result = self.run_job("unzip", names=["output.zip"])
        self.assertEqual(result["status"], "done", result)
        self.assertEqual((self.root / "output" / "source" / "hello.txt").read_bytes(), original)
        self.assertTrue((self.root / "output" / "source" / "Boş klasör").is_dir())
        self.assertTrue((self.root / "source" / "hello.txt").exists())

    def test_nested_off_depth_two_and_three(self):
        inner = zip_bytes([("photo.jpg", b"picture")])
        middle = zip_bytes([("year.zip", inner)])
        self.input([("pictures.zip", middle)])
        for nested, layers, name in [(False, 3, "flat"), (True, 2, "two"), (True, 3, "three")]:
            result = self.run_job("unzip", nested=nested, layers=layers, name=name)
            self.assertEqual(result["status"], "done", result)
        self.assertFalse((self.root / "flat" / "pictures").exists())
        self.assertTrue((self.root / "two" / "pictures" / "year.zip").is_file())
        self.assertFalse((self.root / "two" / "pictures" / "year").exists())
        self.assertEqual((self.root / "three" / "pictures" / "year" / "photo.jpg").read_bytes(), b"picture")
        self.assertTrue((self.root / "input.zip").is_file())

    def test_automatic_nested_default_and_depth_ceiling_are_atomic(self):
        def request():
            data = self.request("unzip")
            del data["nested"], data["layers"]
            self.manager.submit(data)
            self.manager.thread.join(5)
            self.assertFalse(self.manager.thread.is_alive())
            return self.manager.status()["items"][0]
        inner = zip_bytes([("hello.txt", b"automatic")])
        for _ in range(ar.MAX_LAYERS - 2):
            inner = zip_bytes([("inside.zip", inner)])
        self.input([("inside.zip", inner)])
        result = request()
        self.assertEqual(result["status"], "done", result)
        self.assertTrue(result["automatic"])
        self.assertEqual(result["archives"], ar.MAX_LAYERS)
        self.assertEqual((self.root / "output" / ("inside/" * (ar.MAX_LAYERS - 1)) / "hello.txt").read_bytes(), b"automatic")
        # One deeper archive must fail, not publish a misleading partial success.
        self.input([("inside.zip", zip_bytes([("inside.zip", inner)]))])
        result = request()
        self.assertEqual(result["status"], "failed", result)
        self.assertIn("güvenlik sınırı", result["message"])
        self.assertFalse((self.root / "output (2)").exists())
        self.assertEqual(sorted(p.name for p in (self.root / ".arsiv").iterdir()), ["jobs.json"])

    def test_state_uses_installer_downloads_not_source_or_torrent_temp(self):
        panel = files_module.Panel(SimpleNamespace(root=str(self.root),trash=".cop",share="",version="test",domain="test",protected=[{"path":"different/tmp","owner":"Deneme"}],downloads_dir="custom-downloads"))
        self.assertEqual(panel.state()["downloads"], "custom-downloads")

    def test_conflicts_never_overwrite(self):
        self.input([("hello", b"new")])
        (self.root / "output").mkdir()
        (self.root / "output" / "keep").write_text("original")
        self.assertEqual(self.run_job("unzip", conflict="stop")["status"], "failed")
        self.assertEqual(self.run_job("unzip", conflict="skip")["status"], "skipped")
        self.assertEqual(self.run_job("unzip")["result"], "output (2)")
        self.assertEqual((self.root / "output" / "keep").read_text(), "original")

    def test_traversal_absolute_drive_backslash_internal_and_duplicate(self):
        for name in ["../escape", "/escape", "C:/escape", "a\\b", ".arsiv/jobs.json", ".cop/trash", ".pay/accounts"]:
            with self.subTest(name=name):
                self.input([(name, b"bad")])
                self.assert_failed_clean(self.run_job("unzip"))
        self.input([("a", b"one"), ("a", b"two")])
        self.assert_failed_clean(self.run_job("unzip"))

    def test_zip_symlink_rejected(self):
        info = zipfile.ZipInfo("link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        self.input([(info, b"/etc/passwd")])
        self.assert_failed_clean(self.run_job("unzip"))

    def test_source_symlink_hardlink_and_target_symlink_rejected(self):
        (self.root / "source" / "link").symlink_to("/etc/passwd")
        self.assertEqual(self.run_job()["status"], "failed")
        self.assertFalse((self.root / "output.zip").exists())
        (self.root / "source" / "link").unlink()
        os.link(self.root / "source" / "hello.txt", self.root / "source" / "hardlink")
        self.assertEqual(self.run_job()["status"], "failed")
        (self.root / "target").symlink_to(self.root / "source")
        with self.assertRaises(OSError):
            self.manager.submit(self.request(target="target"))

    def test_global_bytes_entries_and_deadline(self):
        self.input([("first", b"x" * 100), ("second", b"x" * 100)])
        with patch.object(ar, "MAX_BYTES", 150):
            self.assert_failed_clean(self.run_job("unzip"))
        with patch.object(ar, "MAX_ENTRIES", 1):
            self.assert_failed_clean(self.run_job("unzip"))
        with patch.object(ar, "MAX_SECONDS", -1):
            self.assert_failed_clean(self.run_job("unzip"))

    def test_corrupt_nested_rolls_back_whole_result(self):
        self.input([("valid.txt", b"valid"), ("broken.zip", b"not a zip")])
        self.assert_failed_clean(self.run_job("unzip"))
        self.assertTrue((self.root / "input.zip").is_file())

    def test_nested_layers_share_one_uncompressed_budget(self):
        inner = zip_bytes([("expanded", b"a" * 5000)])
        self.input([("one.zip", inner), ("two.zip", inner)])
        with patch.object(ar, "MAX_BYTES", 7000):
            result = self.run_job("unzip")
        self.assert_failed_clean(result)
        self.assertGreaterEqual(result["archives"], 2)

    def test_created_zip_rejects_nonportable_source_names(self):
        (self.root / "source" / "drive:name").write_text("not portable")
        self.assertEqual(self.run_job()["status"], "failed")
        self.assertFalse((self.root / "output.zip").exists())

    def test_crc_failure_rolls_back(self):
        data = bytearray(zip_bytes([("data", b"distinct data for corruption")]))
        data[35] ^= 0xff
        (self.root / "input.zip").write_bytes(data)
        self.assert_failed_clean(self.run_job("unzip"))

    def test_central_directory_rejected_before_zipfile(self):
        (self.root / "input.zip").write_bytes(struct.pack("<4s4H2LH", b"PK\x05\x06", 0, 0, 12000, 12000, 0, 0, 0))
        with patch.object(ar.zipfile, "ZipFile", side_effect=AssertionError("must reject before allocation")):
            result = self.run_job("unzip")
        self.assertIn("öge sayısı", result["message"])
        self.assert_failed_clean(result)

    def test_cancel_and_single_worker(self):
        entered, release = threading.Event(), threading.Event()
        original = self.manager.pack
        def block(*args, **kwargs):
            entered.set()
            release.wait(3)
            return original(*args, **kwargs)
        with patch.object(self.manager, "pack", block):
            job = self.manager.submit(self.request())
            self.assertTrue(entered.wait(2))
            with self.assertRaises(ar.ArchiveError) as err:
                self.manager.submit(self.request())
            self.assertEqual(err.exception.code, 409)
            self.manager.cancel(job["id"])
            release.set()
            self.manager.thread.join(5)
        self.assertEqual(self.manager.status()["items"][0]["status"], "cancelled")
        self.assertFalse((self.root / "output.zip").exists())
        self.assertTrue((self.root / "source" / "hello.txt").exists())

    def test_invalid_options_and_internal_api_paths(self):
        for values in [dict(operation="tar"), dict(layers=True), dict(layers=6), dict(nested="yes"), dict(conflict="overwrite"), dict(name="../bad.zip"), dict(target=".arsiv"), dict(path=".arsiv"), dict(names=[".arsiv"]), dict(target="source")]:
            with self.subTest(values=values), self.assertRaises((ar.ArchiveError, files_module.PanelError)):
                self.manager.submit(self.request(**values))
        self.assertNotIn(".arsiv", [e["name"] for e in self.files.listing([], False)["entries"]])

    def test_restart_marks_interrupted_cleans_only_owned_job(self):
        job_id = "a" * 24
        (self.root / ".arsiv" / job_id).mkdir()
        (self.root / ".arsiv" / job_id / "partial").write_text("partial")
        (self.root / ".arsiv" / "unrelated").write_text("keep")
        self.manager.jobs = [{"id": job_id, "status": "running"}]
        self.manager.persist()
        recovered = ar.Archives(self.files, ".arsiv", files_module.rename_noreplace, files_module.rmtree_at)
        self.assertEqual(recovered.status()["items"][0]["status"], "interrupted")
        self.assertFalse((self.root / ".arsiv" / job_id).exists())
        self.assertEqual((self.root / ".arsiv" / "unrelated").read_text(), "keep")
        self.assertEqual(stat.S_IMODE((self.root / ".arsiv").stat().st_mode), 0o700)


if __name__ == "__main__":
    unittest.main()
