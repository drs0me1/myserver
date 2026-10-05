"""WireGuard package: traffic totals for Konsol's network card (DD-206).

The kernel counts each network's interface (wgN in the package's registry, read from
/sys/class/net); the counters start when the network comes up (wg-quick@wgN). Totals are given
as the VPN's users see them: down = bytes the server sent to the peers (what the devices
downloaded through the VPN), up = bytes received from them. The base loads this file from the
rendered package folder and calls trafik(env); networks that are down add nothing.
"""
import re
import subprocess
import time
from pathlib import Path

from master_settings import env_read, read_regular

PACKAGE_DIR = Path(__file__).resolve().parent
SYS_NET = Path("/sys/class/net")
IFACE_RE = re.compile(r"^wg[0-9]$")
SYSTEMCTL_ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"}


def networks():
    """Interface names from the registry (WG_NETWORKS_FILE, first tab-separated field)."""
    path = env_read(PACKAGE_DIR / "wireguard.env")["WG_NETWORKS_FILE"]
    try:
        raw, _ = read_regular(path)
    except FileNotFoundError:
        return []
    names = [line.split("\t", 1)[0] for line in raw.decode("utf-8").splitlines()]
    return [name for name in names if IFACE_RE.fullmatch(name)]


def counters(iface):
    base = SYS_NET / iface / "statistics"
    return (int((base / "rx_bytes").read_text(encoding="ascii").strip()),
            int((base / "tx_bytes").read_text(encoding="ascii").strip()))


def started(units):
    """The earliest start of the running networks' units, as epoch seconds (None when unknown)."""
    proc = subprocess.run(["systemctl", "show", "-p", "ActiveEnterTimestampMonotonic", "--", *units],
                          capture_output=True, text=True, timeout=5, stdin=subprocess.DEVNULL, env=SYSTEMCTL_ENV)
    values = [int(v) for v in re.findall(r"^ActiveEnterTimestampMonotonic=(\d+)$", proc.stdout, re.M) if int(v) > 0]
    return int(time.time() - (time.monotonic() - min(values) / 1e6)) if values else None


def trafik(env):
    down = up = 0
    units = []
    for iface in networks():
        try:
            rx, tx = counters(iface)
        except (OSError, ValueError):
            continue
        down, up = down + tx, up + rx
        units.append("wg-quick@%s.service" % iface)
    return {"down": down, "up": up, "since": started(units) if units else None}
