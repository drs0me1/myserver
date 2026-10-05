"""Address-change event dispatch without a new reconciler or timer."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/'scripts/refresh-tailnet-config'

class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.bin=self.root/'bin';self.bin.mkdir();(self.root/'run').mkdir()
        self.state=self.root/'state';self.log=self.root/'calls';self.pending=self.root/'run/containers-tailnet.pending'
        bodies={'id':'echo 0', 'flock':'exit 0', 'jq':'echo ok',
                'ip':'case "$*" in *-4*) echo "2: tailscale0 inet 100.64.0.3/32 scope global tailscale0";; esac',
                'tailscale':'exit 0', 'systemctl':'case "$1" in is-failed) exit 1;; show) echo active;; esac',
                'systemd-run':'printf "%s\\n" "$*" >> "$CALL_LOG"', 'firewall':'exit 0'}
        for name,body in bodies.items():
            p=self.bin/name;p.write_text('#!/bin/sh\n'+body+'\n');p.chmod(0o755)
        (self.bin/'master_container_worker.py').write_text('# fixture worker\n')
        self.write_state('100.64.0.2')

    def write_state(self,ip):
        self.state.write_text(f'TAILSCALE_IPV4={ip}\nTAILSCALE_IPV6=\nTAILSCALE_IF=tailscale0\nRUNTIME_DIR={self.root}/run\nSBIN_DIR={self.bin}\nKONTEYNER_STATE_DIR={self.root}/containers\n')

    def execute(self):
        return subprocess.run(['bash',str(SCRIPT)],capture_output=True,text=True,timeout=10,
            env=dict(os.environ,STATE_FILE=str(self.state),FIREWALL_BIN=str(self.bin/'firewall'),
                     PATH=str(self.bin)+':'+os.environ['PATH'],CALL_LOG=str(self.log)))

    def test_address_change_records_event_and_dispatches_bounded_worker(self):
        result=self.execute();self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(self.pending.is_file())
        self.assertIn('100.64.0.3',self.pending.read_text())
        self.assertIn('--refresh-tailnet',self.log.read_text())
        self.assertIn('RuntimeMaxSec=900',self.log.read_text())

    def test_pending_event_retries_without_new_address_but_idle_refresh_does_not(self):
        self.write_state('100.64.0.3');self.pending.write_text('100.64.0.3\n')
        result=self.execute();self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(self.log.exists())
        self.log.unlink();self.pending.unlink()
        result=self.execute();self.assertEqual(result.returncode,0,result.stderr)
        self.assertFalse(self.log.exists())

if __name__=='__main__':unittest.main()
