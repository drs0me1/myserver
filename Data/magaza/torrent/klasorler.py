"""qBittorrent package: folders the application writes into (DD-203).

The base's share manager loads this file from the rendered package folder (like yayin.py) and
asks yazilan(env) for the absolute folders qBittorrent currently writes half-finished files
into, beyond the manifest's PAKET_KLASORLER default: the temporary folder the user may have
chosen in qBittorrent itself. It never writes the profile. An unreadable profile raises and
the base refuses the share change (fail closed); a missing profile means nothing extra.
"""
import os
from pathlib import Path

from master_settings import env_read, read_regular

PACKAGE_DIR = Path(__file__).resolve().parent


def package_env(env):
    merged = dict(env)
    merged.update(env_read(PACKAGE_DIR / "torrent.env"))
    return merged


def yazilan(env):
    conf = Path(package_env(env)["TORRENT_PROFILE_DIR"]) / "qBittorrent/qBittorrent.conf"
    try:
        raw, _ = read_regular(conf)
    except FileNotFoundError:
        return []
    out = []
    for line in raw.decode("utf-8").splitlines():
        if line.startswith(("Session\\TempPath=", "Downloads\\TempPath=")):
            value = line.rstrip().split("=", 1)[1].strip().strip('"')
            if value:
                out.append(os.path.normpath(value))
    return out
