"""qBittorrent package: traffic totals for Konsol's network card (DD-206).

qBittorrent keeps its own all-time download/upload totals and writes them to its profile
(qBittorrent-data.conf, [Stats] AllStats, a Qt QVariantHash with AlltimeDL/AlltimeUL) every few
minutes while it runs and when it stops. This module reads that file only — no login, no
command — and reports the figures with the file's time as "at". systemd's IP accounting was
tried first and rejected: a daemon-reload drops the counters of units loaded from disk on
Debian 13 (systemd 257) until the service restarts. The base loads this file from the rendered
package folder (like yayin.py) and calls trafik(env) with state.env's values.
"""
import os
from pathlib import Path
import re
import string
import struct

from master_settings import env_read, read_regular

PACKAGE_DIR = Path(__file__).resolve().parent
NAMED = {"a": 7, "b": 8, "f": 12, "n": 10, "r": 13, "t": 9, "v": 11}
TYPE_LONGLONG, TYPE_ULONGLONG, TYPE_HASH, TYPE_MAP = 4, 5, 28, 8


def package_env(env):
    merged = dict(env)
    merged.update(env_read(PACKAGE_DIR / "torrent.env"))
    return merged


def unescape(text):
    """Qt's INI escapes back to bytes: \\xHH… and octal runs (a writer escapes any digit that
    follows an escape, so greedy reading is exact), the named C escapes and quoted characters."""
    out, i = bytearray(), 0
    while i < len(text):
        ch = text[i]
        if ch != "\\":
            out.append(ord(ch))
            i += 1
            continue
        i += 1
        if i >= len(text):
            raise ValueError("eksik kaçış")
        ch = text[i]
        if ch == "x":
            j = i + 1
            while j < len(text) and text[j] in string.hexdigits:
                j += 1
            if j == i + 1:
                raise ValueError("boş onaltılık kaçış")
            out.append(int(text[i + 1:j], 16))
            i = j
        elif ch in "01234567":
            j = i
            while j < len(text) and text[j] in "01234567":
                j += 1
            out.append(int(text[i:j], 8))
            i = j
        else:
            out.append(NAMED.get(ch, ord(ch)))
            i += 1
    return bytes(out)


def variant(data, pos=0):
    """One QVariant as QSettings streams it (QDataStream version Qt_4_0: a type id, no null flag,
    then the value); 64-bit integers and hashes/maps of named values only."""
    kind, = struct.unpack_from(">I", data, pos)
    pos += 4
    if kind in (TYPE_LONGLONG, TYPE_ULONGLONG):
        return struct.unpack_from(">q" if kind == TYPE_LONGLONG else ">Q", data, pos)[0], pos + 8
    if kind in (TYPE_HASH, TYPE_MAP):
        count, = struct.unpack_from(">I", data, pos)
        pos += 4
        values = {}
        for _ in range(count):
            size, = struct.unpack_from(">I", data, pos)
            pos += 4
            key = data[pos:pos + size].decode("utf-16-be")
            pos += size
            values[key], pos = variant(data, pos)
        return values, pos
    raise ValueError("beklenmeyen QVariant türü %d" % kind)


def trafik(env):
    path = Path(package_env(env)["TORRENT_PROFILE_DIR"]) / "qBittorrent" / "qBittorrent-data.conf"
    try:
        raw, _ = read_regular(path)
        at = int(os.stat(path, follow_symlinks=False).st_mtime)
    except FileNotFoundError:
        return {"down": 0, "up": 0, "since": None, "at": None}  # nothing transferred and saved yet
    section, value = "", None
    for line in raw.decode("utf-8").splitlines():
        if line.startswith("["):
            section = line.strip()
        elif section == "[Stats]" and line.startswith("AllStats="):
            value = line.split("=", 1)[1].strip()
    if value is None:
        return {"down": 0, "up": 0, "since": None, "at": at}
    match = re.fullmatch(r'"?@Variant\((.*)\)"?', value)
    if not match:
        raise ValueError("AllStats okunamadı")
    stats, _ = variant(unescape(match.group(1)))
    down, up = stats.get("AlltimeDL"), stats.get("AlltimeUL")
    if not (isinstance(down, int) and isinstance(up, int)) or down < 0 or up < 0:
        raise ValueError("AllStats beklenen biçimde değil")
    return {"down": down, "up": up, "since": None, "at": at}
