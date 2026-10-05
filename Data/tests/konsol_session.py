"""Live tests only: a short root-issued Konsol session for API calls through Caddy (DD-194).

`master-konsol oturum-ac` prints a token over SSH; it stays in memory, is sent only as the
konsol_oturum cookie and is closed afterwards. Never print or log it.
"""
import subprocess

COMMAND = "/usr/local/sbin/master-konsol"


def open_session(ssh, seconds=1800):
    result = subprocess.run(ssh + ["sudo -n %s oturum-ac --sure %d" % (COMMAND, seconds)],
                            capture_output=True, text=True, timeout=60)
    token = result.stdout.strip()
    if result.returncode or not token:
        raise RuntimeError("Konsol test session could not be opened (output withheld)")
    return "konsol_oturum=" + token


def close_session(ssh, cookie):
    if cookie:
        subprocess.run(ssh + ["sudo -n %s oturum-kapat" % COMMAND], input=cookie.split("=", 1)[1],
                       capture_output=True, text=True, timeout=60)
