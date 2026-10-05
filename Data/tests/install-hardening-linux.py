#!/usr/bin/env python3
"""Real flock and ownership tests; only private temporary files are changed.

Run as root on Linux: python3 Data/tests/install-hardening-linux.py
No services, accounts, installed state or host firewall are changed. Missing
Linux/root/util-linux prerequisites are errors, never skipped passing tests.
"""
import fcntl
import os
from pathlib import Path
import re
import select
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest

from test_install_hardening import DATA, PermissionRepairTests, metadata, permissions


class OwnershipTests(unittest.TestCase):
    setUp = PermissionRepairTests.setUp
    file = PermissionRepairTests.file

    def test_uid_gid_and_mode_changes_count_each_entry_once(self):
        uid, gid = 65534, 65534
        self.root.chmod(0o775)
        os.chown(self.root, uid, gid)
        owner_only = self.file(self.root / "owner-only", 0o664)
        mode_only = self.file(self.root / "mode-only", 0o600)
        os.chown(mode_only, uid, gid)
        both = self.file(self.root / "both", 0o600)
        folder = self.root / "folder"
        folder.mkdir(mode=0o700)
        good = self.file(self.root / "good", 0o664)
        os.chown(good, uid, gid)
        before = metadata(good)
        self.assertEqual(permissions.repair(self.root, uid, gid, ()), 4)
        for path in (owner_only, mode_only, both, folder, good):
            st = path.stat()
            self.assertEqual((st.st_uid, st.st_gid), (uid, gid))
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o775 if path.is_dir() else 0o664)
        self.assertEqual(metadata(good), before)
        self.assertEqual(permissions.repair(self.root, uid, gid, ()), 0)

    def test_root_never_chowns_links_devices_or_private_workspaces(self):
        os.link(self.target, self.root / "hardlink")
        (self.root / "symlink").symlink_to(self.target)
        os.mkfifo(self.root / "fifo", 0o600)
        # A real device entry must be neither opened nor repaired.
        os.mknod(self.root / "device", stat.S_IFCHR | 0o600, os.makedev(1, 3))
        for name in (".arsiv", ".pay"):
            (self.root / name).mkdir(mode=0o700)
            self.file(self.root / name / "private")
        watched = list(self.root.iterdir()) + [self.target, self.root / ".arsiv/private", self.root / ".pay/private"]
        before = [metadata(p) for p in watched]
        self.assertEqual(permissions.repair(self.root, 65534, 65534, (".arsiv", ".pay")), 1)
        self.assertEqual([metadata(p) for p in watched], before)

    def test_private_directory_repairs_only_its_own_owner_and_mode(self):
        private = self.root / ".arsiv"
        private.mkdir(mode=0o755)
        child = self.file(private / "jobs.json")
        before = metadata(child)
        permissions.prepare_directory(private, 65534, 65534, 0o700)
        st = private.stat()
        self.assertEqual((st.st_uid, st.st_gid, stat.S_IMODE(st.st_mode)), (65534, 65534, 0o700))
        self.assertEqual(metadata(child), before)


class LockTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="installer-locks-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.runtime = self.root / "run"
        self.runtime.mkdir()
        self.install = self.runtime / "install.lock"
        self.module = self.runtime / "modul.lock"
        self.state = self.root / "state.env"
        values = dict(RUNTIME_DIR=self.runtime, MODULES_FILE=self.root / "registry",
                      MODULES_DIR=self.root / "modules", DOWNLOADS_PATH=self.root / "downloads",
                      SETTINGS_PENDING_FILE=self.root / "pending.json")
        self.state.write_text("".join(k + "=" + shlex.quote(str(v)) + "\n" for k, v in values.items()))
        # DD-197: the catalogue is the set of rendered package folders; the engine validates the
        # id before it takes the locks, so the fixture needs the real torrent manifest and hooks.
        (self.root / "modules" / "torrent").mkdir(parents=True)
        for name in ("paket.env", "kanca"):
            shutil.copy(DATA / "magaza" / "torrent" / name, self.root / "modules" / "torrent" / name)
        self.env = dict(os.environ, STATE_FILE=str(self.state))
        self.env.pop("V2_LOCK_FD", None)
        self.module_cmd = ["bash", str(DATA / "scripts/master-modul"), "uygula", "torrent"]
        source = (DATA / "scripts/master-modul").read_text()
        take_lock = re.search(r"^take_lock\(\) \{\n.*?^\}", source, re.M | re.S)
        self.assertIsNotNone(take_lock)
        self.lock_script = ('set -Eeuo pipefail\nsource "$STATE_FILE"\n'
                            'die() { printf "%s\\n" "$*" >&2; exit 1; }\n'
                            + take_lock[0] + '\ntake_lock\nprintf "ready\\n"\nread -r release\n')

    def run_cmd(self, args=None, **kwargs):
        return subprocess.run(args or self.module_cmd, env=kwargs.pop("env", self.env),
                              capture_output=True, text=True, timeout=12, **kwargs)

    def hold(self, path):
        stream = path.open("a+")
        self.addCleanup(stream.close)
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return stream

    def locked(self, path):
        with path.open("a+") as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            return False

    def spawn(self, script, *args):
        process = subprocess.Popen(["bash", "-c", script, "lock-fixture", *map(str, args)], env=self.env,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, start_new_session=True)

        def cleanup():
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
            for stream in (process.stdin, process.stdout, process.stderr):
                stream.close()
        self.addCleanup(cleanup)
        return process

    def ready(self, process):
        self.assertTrue(select.select([process.stdout], [], [], 8)[0], "lock holder did not become ready")
        line = process.stdout.readline().strip()
        self.assertEqual(line, "ready", process.stderr.read() if process.poll() is not None else line)

    def release(self, process):
        stdout, stderr = process.communicate("release\n", timeout=8)
        self.assertEqual(process.returncode, 0, stdout + stderr)

    def test_competing_installer_blocks_real_module_and_releases_cleanly(self):
        holder = self.hold(self.install)
        result = self.run_cmd()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("başka bir kurulum/ayar işlemi", result.stderr)
        self.assertFalse(self.module.exists(), "module lock opened before acquiring install.lock")
        fcntl.flock(holder, fcntl.LOCK_UN)
        result = self.run_cmd()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "torrent\tyok\n")
        self.assertFalse(self.locked(self.install))
        self.assertFalse(self.locked(self.module))

    def test_module_waits_for_module_lock_and_blocks_competing_installer(self):
        holder = self.hold(self.module)
        process = self.spawn(self.lock_script)
        deadline = time.monotonic() + 3
        while not self.locked(self.install):
            self.assertLess(time.monotonic(), deadline, "module never acquired install.lock")
            self.assertIsNone(process.poll())
            time.sleep(.01)
        result = self.run_cmd(["bash", "-c", 'set -Eeuo pipefail; source "$1"; acquire_lock "$2" 0',
                               "installer", str(DATA / "common.sh"), str(self.install)])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("kilit alınamadı", result.stderr)
        fcntl.flock(holder, fcntl.LOCK_UN)
        self.ready(process)
        self.assertTrue(self.locked(self.install))
        self.assertTrue(self.locked(self.module))
        result = self.run_cmd()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("başka bir kurulum/ayar işlemi", result.stderr)
        self.release(process)
        self.assertFalse(self.locked(self.install))
        self.assertFalse(self.locked(self.module))

    def test_module_lock_timeout_releases_the_install_lock(self):
        self.hold(self.module)
        result = self.run_cmd()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("başka bir modül işlemi", result.stderr)
        self.assertFalse(self.locked(self.install))

    def test_inherited_common_lock_survives_nested_modules_without_deadlock(self):
        script = '''set -Eeuo pipefail
source "$1"
acquire_lock "$2" 1
# The real child requires common.sh to export V2_LOCK_FD; both invocations
# reuse the open description without releasing the parent's lock.
bash "$3" uygula torrent >/dev/null
bash "$3" uygula torrent >/dev/null
printf 'ready\n'
read -r release
'''
        process = self.spawn(script, DATA / "common.sh", self.install, DATA / "scripts/master-modul")
        self.ready(process)
        self.assertTrue(self.locked(self.install), "nested module unlocked the installer")
        self.assertFalse(self.locked(self.module), "child leaked its module lock")
        result = self.run_cmd()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("başka bir kurulum/ayar işlemi", result.stderr)
        self.release(process)
        self.assertFalse(self.locked(self.install))

    def test_forged_or_wrong_inode_descriptor_never_bypasses_install_lock(self):
        self.hold(self.install)
        wrong = self.hold(self.root / "unrelated.lock")
        for value, fds in ((str(wrong.fileno()), (wrong.fileno(),)), ("12345", ()), ("not-a-fd", ())):
            with self.subTest(fd=value):
                result = self.run_cmd(env=dict(self.env, V2_LOCK_FD=value), pass_fds=fds)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("başka bir kurulum/ayar işlemi", result.stderr)
                self.assertFalse(self.module.exists())

    def test_matching_inode_with_independent_open_description_must_lock(self):
        self.hold(self.install)
        with self.install.open("a+") as independent:
            result = self.run_cmd(env=dict(self.env, V2_LOCK_FD=str(independent.fileno())),
                                  pass_fds=(independent.fileno(),))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("üst kurulum kilidi doğrulanamadı", result.stderr)
            self.assertFalse(self.module.exists())

    def test_pending_settings_are_rejected_and_both_locks_are_released(self):
        (self.root / "pending.json").write_text("{}")
        result = self.run_cmd()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("onay bekleyen ayar", result.stderr)
        self.assertFalse(self.locked(self.install))
        self.assertFalse(self.locked(self.module))


if __name__ == "__main__":
    if sys.platform != "linux" or os.geteuid() != 0 or shutil.which("flock") is None:
        raise SystemExit("Requires Linux, root and util-linux flock; no tests were run")
    subprocess.run(["bash", "-c", "(( BASH_VERSINFO[0] >= 4 ))"], check=True)
    unittest.main(verbosity=2)
