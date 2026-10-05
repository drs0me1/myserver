#!/usr/bin/env python3
"""DD-156: real transient worker and timer, scratch state only, no service edits."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

DATA = Path(__file__).resolve().parents[1]
HELPER = DATA / "panel/master_settings.py"
spec = importlib.util.spec_from_file_location("settings", HELPER)
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


def main():
    assert os.geteuid() == 0
    with tempfile.TemporaryDirectory(prefix="konsol-timer-test-") as temp:
        root = Path(temp)
        e = s.env_read(DATA / "config/defaults.env")
        e.update(LOCAL_DOMAIN="ayc", SETTINGS_FILE=str(root / "settings.json"), SETTINGS_PENDING_FILE=str(root / "pending.json"),
                 SETTINGS_DNS_FILE=str(root / "dns/custom.conf"), RUNTIME_DIR=str(root / "run"))
        state = root / "state.env"
        state.write_text("".join(k + '="' + v + '"\n' for k, v in e.items()))
        m = s.Manager(state)
        s.save_json(m.pending_path, dict(id="timer-test", phase="awaiting", boot=s.boot_id(), until=time.monotonic() + 1,
                    candidate=s.DEFAULT, files={}, q_active=False, changes=dict(firewall=False, dns=False, torrent=False)))
        unit = "konsol-test-" + root.name
        try:
            subprocess.run(["systemd-run", "--quiet", "--collect", "--unit=" + unit, "--on-active=2s",
                            "--timer-property=AccuracySec=1s", "--setenv=PYTHONDONTWRITEBYTECODE=1", "/usr/bin/python3", str(HELPER),
                            "--state", str(state), "guard"], check=True)
            until = time.monotonic() + 15
            while m.pending_path.exists() and time.monotonic() < until:
                time.sleep(.2)
            assert not m.pending_path.exists(), "systemd geri alma zamanlayıcısı çalışmadı"
            assert not m.config_path.exists(), "Onaysız işlem kalıcılaştırıldı"
            # Panelin kullandığı stdin/pipe biçimi gerçek systemd-run ile JSON verir.
            worker = subprocess.run(["systemd-run", "--quiet", "--wait", "--pipe", "--collect", "--property=UMask=0077",
                                     "--property=RuntimeMaxSec=150", "--setenv=PYTHONDONTWRITEBYTECODE=1", "/usr/bin/python3", str(HELPER),
                                     "--state", str(state), "rollback"], input='{"id":"none"}', capture_output=True, text=True, timeout=20)
            assert worker.returncode == 0 and json.loads(worker.stdout) == {"ok": True}, worker.stderr
            text = (DATA / "systemd/master-settings-guard.service").read_text().replace("__SBIN_DIR__", str(HELPER.parent)).replace("__STATE_FILE__", str(state))
            rendered = root / "master-settings-guard.service"
            rendered.write_text(text)
            subprocess.run(["systemd-analyze", "verify", str(rendered)], check=True, capture_output=True)
            print("PASS real systemd timer recovery, isolated worker stdin/JSON, rendered service validation")
        finally:
            subprocess.run(["systemctl", "stop", unit + ".timer", unit + ".service"], capture_output=True)
            subprocess.run(["systemctl", "reset-failed", unit + ".timer", unit + ".service"], capture_output=True)


if __name__ == "__main__":
    main()
