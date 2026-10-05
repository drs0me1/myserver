"""Installer permission regressions using private, physical temporary paths.

Run: python3 -m unittest discover -s Data/tests -p test_install_hardening.py -v
Real Linux ownership and flock coverage lives in install-hardening-linux.py.
"""
import errno
import importlib.util
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

DATA = Path(__file__).resolve().parents[1]
HELPER = DATA / "panel/master_permissions.py"
spec = importlib.util.spec_from_file_location("installer_permissions", HELPER)
permissions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(permissions)


def metadata(path):
    st = path.lstat()
    return (st.st_dev, st.st_ino, st.st_mode, st.st_uid, st.st_gid,
            st.st_size, st.st_mtime_ns, st.st_ctime_ns)


class PermissionRepairTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="installer-permissions-")
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()
        self.root = self.base / "data"
        self.root.mkdir(mode=0o775)
        self.root.chmod(0o775)
        self.outside = self.base / "outside"
        self.outside.mkdir(mode=0o700)
        self.target = self.file(self.outside / "private", 0o600)
        self.uid, self.gid = os.getuid(), os.getgid()

    def file(self, path, mode=0o600):
        path.write_bytes(b"private fixture\n")
        path.chmod(mode)
        return path

    def repair(self, **kwargs):
        return permissions.repair(self.root, self.uid, self.gid,
                                  kwargs.get("excluded", (".arsiv", ".pay")))

    def test_regular_files_directories_and_counts_are_selective(self):
        folder = self.root / "folder"
        folder.mkdir(mode=0o700)
        bad = self.file(folder / "bad")
        good = self.file(folder / "good", 0o664)
        before = metadata(good)
        with mock.patch.object(permissions.os, "fchmod", wraps=os.fchmod) as chmod, \
                mock.patch.object(permissions.os, "fchown", wraps=os.fchown) as chown:
            self.assertEqual(self.repair(), 2)
            self.assertEqual(chmod.call_count, 2)
            chown.assert_not_called()
        self.assertEqual(stat.S_IMODE(folder.stat().st_mode), 0o775)
        self.assertEqual(stat.S_IMODE(bad.stat().st_mode), 0o664)
        self.assertEqual(metadata(good), before)
        entries = (self.root, folder, bad, good)
        before = [metadata(p) for p in entries]
        with mock.patch.object(permissions.os, "fchmod", wraps=os.fchmod) as chmod, \
                mock.patch.object(permissions.os, "fchown", wraps=os.fchown) as chown:
            self.assertEqual(self.repair(), 0)
            chmod.assert_not_called()
            chown.assert_not_called()
        self.assertEqual([metadata(p) for p in entries], before)

    def test_count_includes_root_and_each_newline_name_once(self):
        self.root.chmod(0o700)
        self.file(self.root / "line\nbreak")
        self.file(self.root / "space name")
        self.assertEqual(self.repair(), 3)
        self.assertEqual(self.repair(), 0)

    def test_symlinks_and_hardlinks_keep_targets_and_metadata(self):
        (self.root / "file-link").symlink_to(self.target)
        (self.root / "parent-link").symlink_to(self.outside, target_is_directory=True)
        (self.root / "dangling").symlink_to(self.base / "missing")
        os.link(self.target, self.root / "hardlink")
        # Even two names entirely inside the data area share an inode and are excluded.
        inside = self.file(self.root / "linked-a")
        os.link(inside, self.root / "linked-b")
        watched = list(self.root.iterdir()) + [self.target, self.outside]
        before = [metadata(p) for p in watched]
        self.assertEqual(self.repair(), 0)
        self.assertEqual([metadata(p) for p in watched], before)
        self.assertEqual(self.target.read_bytes(), b"private fixture\n")

    def test_fifo_and_unix_socket_are_untouched_without_blocking(self):
        fifo = self.root / "fifo"
        os.mkfifo(fifo, 0o600)
        # AF_UNIX paths must also fit macOS's short pathname limit.
        with tempfile.TemporaryDirectory(prefix="iperm-", dir="/tmp") as short:
            sockpath = Path(short).resolve() / "sock"
            sock = socket.socket(socket.AF_UNIX)
            try:
                sock.bind(str(sockpath))
                destination = self.root / "socket"
                sockpath.rename(destination)
                watched = (fifo, destination)
                before = [metadata(p) for p in watched]
                result = subprocess.run([sys.executable, str(HELPER), str(self.root),
                                         str(self.uid), str(self.gid)],
                                        capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "0\n")
                self.assertEqual([metadata(p) for p in watched], before)
            finally:
                sock.close()

    def test_top_level_workspaces_are_excluded_but_similar_and_nested_names_are_data(self):
        protected = []
        for name in (".arsiv", ".pay"):
            folder = self.root / name
            (folder / "work").mkdir(parents=True, mode=0o700)
            folder.chmod(0o700)
            protected.extend((folder, folder / "work", self.file(folder / "work/private")))
        for name in (".arsiv-copy", ".pay-copy", ".cop", "media"):
            (self.root / name).mkdir(mode=0o700)
        nested = self.root / "media/.arsiv"
        nested.mkdir(mode=0o700)
        self.file(nested / "ordinary")
        before = [metadata(p) for p in protected]
        self.assertEqual(self.repair(), 6)
        self.assertEqual([metadata(p) for p in protected], before)
        self.assertEqual(stat.S_IMODE(nested.stat().st_mode), 0o775)
        self.assertEqual(self.repair(), 0)

    def test_configured_workspace_names_are_honored(self):
        for name in ("private-archives", "retired-shares", ".arsiv", ".pay"):
            (self.root / name).mkdir(mode=0o700)
        self.assertEqual(self.repair(excluded=("private-archives", "retired-shares")), 2)
        for name in ("private-archives", "retired-shares"):
            self.assertEqual(stat.S_IMODE((self.root / name).stat().st_mode), 0o700)

    def test_root_and_parent_symlinks_fail_before_any_repair(self):
        direct = self.base / "root-link"
        direct.symlink_to(self.root, target_is_directory=True)
        parent = self.base / "parent-link"
        parent.symlink_to(self.base, target_is_directory=True)
        before = metadata(self.target), metadata(self.root)
        for path in (direct, parent / "data", self.root / "../outside", Path("relative")):
            with self.subTest(path=path), self.assertRaises((OSError, ValueError)):
                permissions.repair(path, self.uid, self.gid, ())
        self.assertEqual((metadata(self.target), metadata(self.root)), before)

    def test_cli_reports_unsafe_root_without_success_count(self):
        link = self.base / "link"
        link.symlink_to(self.outside, target_is_directory=True)
        before = metadata(self.target)
        result = subprocess.run([sys.executable, str(HELPER), str(link),
                                 str(self.uid), str(self.gid)],
                                capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("güvenli onarılamadı", result.stderr)
        self.assertEqual(metadata(self.target), before)

    def test_entry_replaced_before_open_cannot_redirect_repairs(self):
        real_open = os.open
        # Deterministically change the entry after its lstat and before openat.
        # Inode changes, no-follow failures and nonblocking special-file opens
        # must all preserve the replacement, with no counted repair.
        for kind in ("symlink", "parent-symlink", "regular", "directory", "fifo", "hardlink", "missing"):
            with self.subTest(kind=kind):
                victim = self.root / "victim"
                if kind == "parent-symlink":
                    victim.mkdir(mode=0o700)
                else:
                    self.file(victim)
                parked = self.base / ("parked-" + kind)
                fired, replacement = [], []
                before = metadata(self.target)

                def swap(path, flags, *args, **kwargs):
                    if path == "victim" and kwargs.get("dir_fd") is not None and not fired:
                        fired.append(flags)
                        victim.rename(parked)
                        if kind in ("symlink", "parent-symlink"):
                            victim.symlink_to(self.outside if kind == "parent-symlink" else self.target)
                        elif kind == "regular":
                            self.file(victim)
                        elif kind == "directory":
                            victim.mkdir(mode=0o700)
                        elif kind == "fifo":
                            os.mkfifo(victim, 0o600)
                            self.assertTrue(flags & os.O_NONBLOCK)
                        elif kind == "hardlink":
                            os.link(self.target, victim)
                        if kind != "missing":
                            replacement.append(metadata(victim))
                    return real_open(path, flags, *args, **kwargs)

                with mock.patch.object(permissions.os, "open", side_effect=swap):
                    self.assertEqual(self.repair(), 0)
                self.assertEqual(len(fired), 1)
                self.assertTrue(fired[0] & os.O_NOFOLLOW)
                if replacement:
                    self.assertEqual(metadata(victim), replacement[0])
                # Creating a hardlink itself changes the target's ctime.
                if kind != "hardlink":
                    self.assertEqual(metadata(self.target), before)
                else:
                    self.assertEqual(metadata(self.target)[2:5], before[2:5])
                if victim.is_dir() and not victim.is_symlink():
                    victim.rmdir()
                elif victim.is_symlink() or victim.exists():
                    victim.unlink()

    def test_new_hardlink_between_stat_and_open_is_not_repaired(self):
        victim = self.file(self.root / "victim")
        real_open = os.open
        fired = []

        def link(path, flags, *args, **kwargs):
            if path == "victim" and not fired:
                os.link(victim, self.outside / "new-link")
                fired.append(metadata(victim))
            return real_open(path, flags, *args, **kwargs)

        with mock.patch.object(permissions.os, "open", side_effect=link):
            self.assertEqual(self.repair(), 0)
        self.assertEqual(metadata(victim), fired[0])

    def test_path_replaced_after_open_keeps_repairs_on_the_original_descriptor(self):
        victim = self.file(self.root / "victim")
        parked = self.base / "parked"
        real_open = os.open
        before = metadata(self.target)
        fired = []

        def swap(path, flags, *args, **kwargs):
            fd = real_open(path, flags, *args, **kwargs)
            if path == "victim" and not fired:
                victim.rename(parked)
                victim.symlink_to(self.target)
                fired.append(True)
            return fd

        with mock.patch.object(permissions.os, "open", side_effect=swap):
            self.assertEqual(self.repair(), 1)
        self.assertEqual(fired, [True])
        self.assertTrue(victim.is_symlink())
        self.assertEqual(metadata(self.target), before)
        self.assertEqual(stat.S_IMODE(parked.stat().st_mode), 0o664)

    def test_non_race_io_failures_are_not_silently_ignored(self):
        self.file(self.root / "victim")
        real_open = os.open

        def fail(path, flags, *args, **kwargs):
            if path == "victim":
                raise OSError(errno.EIO, "injected read failure")
            return real_open(path, flags, *args, **kwargs)

        with mock.patch.object(permissions.os, "open", side_effect=fail), \
                self.assertRaises(OSError) as raised:
            self.repair()
        self.assertEqual(raised.exception.errno, errno.EIO)

    def test_mkdir_creates_nested_tree_without_rewriting_existing_metadata(self):
        existing = self.root / "existing"
        existing.mkdir(mode=0o700)
        before = metadata(existing)
        permissions.prepare_directory(existing, self.uid, self.gid)
        self.assertEqual(metadata(existing), before)
        destination = existing / "new/media/movies"
        permissions.prepare_directory(destination, self.uid, self.gid)
        self.assertTrue(destination.is_dir())
        self.assertEqual(stat.S_IMODE(existing.stat().st_mode), 0o700)
        before = metadata(destination)
        permissions.prepare_directory(destination, self.uid, self.gid)
        self.assertEqual(metadata(destination), before)

    def test_mkdir_rejects_symlink_parent_without_creating_outside_children(self):
        parent = self.root / "media"
        parent.symlink_to(self.outside, target_is_directory=True)
        before = metadata(self.outside), metadata(self.target)
        for mode in (None, 0o700):
            with self.subTest(mode=mode), self.assertRaises(OSError):
                permissions.prepare_directory(parent / "movies/new", self.uid, self.gid, mode)
        self.assertFalse((self.outside / "movies").exists())
        self.assertEqual((metadata(self.outside), metadata(self.target)), before)

    def test_mkdir_parent_swapped_after_mkdir_before_open_cannot_escape(self):
        real_mkdir = os.mkdir
        fired = []
        before = metadata(self.outside)

        def swap(path, *args, **kwargs):
            result = real_mkdir(path, *args, **kwargs)
            if path == "new-parent" and not fired:
                parent = self.root / "new-parent"
                parent.rename(self.root / "parked-parent")
                parent.symlink_to(self.outside, target_is_directory=True)
                fired.append(True)
            return result

        with mock.patch.object(permissions.os, "mkdir", side_effect=swap), self.assertRaises(OSError):
            permissions.prepare_directory(self.root / "new-parent/child", self.uid, self.gid)
        self.assertEqual(fired, [True])
        self.assertFalse((self.outside / "child").exists())
        self.assertEqual(metadata(self.outside), before)

    def test_private_directory_is_selective_and_never_walks_its_contents(self):
        private = self.root / ".arsiv"
        private.mkdir(mode=0o755)
        payload = self.file(private / "jobs.json", 0o600)
        before = metadata(payload)
        permissions.prepare_directory(private, self.uid, self.gid, 0o700)
        self.assertEqual(stat.S_IMODE(private.stat().st_mode), 0o700)
        self.assertEqual(metadata(payload), before)
        before = metadata(private)
        with mock.patch.object(permissions.os, "fchmod", wraps=os.fchmod) as chmod, \
                mock.patch.object(permissions.os, "fchown", wraps=os.fchown) as chown:
            permissions.prepare_directory(private, self.uid, self.gid, 0o700)
            chmod.assert_not_called()
            chown.assert_not_called()
        self.assertEqual(metadata(private), before)

    def test_private_directory_symlink_and_fifo_are_refused(self):
        link = self.root / "archive-link"
        link.symlink_to(self.outside, target_is_directory=True)
        fifo = self.root / "archive-fifo"
        os.mkfifo(fifo, 0o600)
        before = metadata(self.outside), metadata(self.target), metadata(fifo)
        for path in (link, fifo):
            with self.subTest(path=path):
                result = subprocess.run([sys.executable, str(HELPER), "--directory-mode", "0700",
                                         str(path), str(self.uid), str(self.gid)],
                                        capture_output=True, text=True, timeout=5)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("güvenli onarılamadı", result.stderr)
        self.assertEqual((metadata(self.outside), metadata(self.target), metadata(fifo)), before)

    def test_private_directory_swapped_after_open_does_not_chmod_link_target(self):
        private = self.root / ".arsiv"
        private.mkdir(mode=0o755)
        parked = self.root / "parked-archive"
        real_open = os.open
        before = metadata(self.outside), metadata(self.target)
        fired = []

        def swap(path, flags, *args, **kwargs):
            fd = real_open(path, flags, *args, **kwargs)
            if path == ".arsiv" and not fired:
                private.rename(parked)
                private.symlink_to(self.outside, target_is_directory=True)
                fired.append(True)
            return fd

        with mock.patch.object(permissions.os, "open", side_effect=swap):
            permissions.prepare_directory(private, self.uid, self.gid, 0o700)
        self.assertEqual(fired, [True])
        self.assertTrue(private.is_symlink())
        self.assertEqual(stat.S_IMODE(parked.stat().st_mode), 0o700)
        self.assertEqual((metadata(self.outside), metadata(self.target)), before)


if __name__ == "__main__":
    unittest.main()
