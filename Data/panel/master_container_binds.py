#!/usr/bin/env python3
"""DD-226: pin a Konsol container's bind sources at every start.

Podman resolves a Volume= source by path whenever the container starts. Under SERVER_ROOT,
which the downloads account can write, a path component swapped for a symbolic link would
let a root container mount another host directory. Each generated unit therefore runs

  ExecStartPre: master_container_binds.py --state STATE bagla NAME SOURCE...
  ExecStopPost: master_container_binds.py --state STATE birak NAME

`bagla` walks every source from / without following links, binds the directory behind that
descriptor onto a root-owned anchor (KONTEYNER_BAGLAMA_DIR/NAME/<hash>) and verifies the
anchor's identity; the Quadlet mounts the anchor, never the path. Only base invariants are
checked here (absolute, no '..', a non-hidden subfolder of SERVER_ROOT). Package-declared
folders stay a save-time check: no store, package code or lock is involved at start.
"""
import argparse
import ctypes
import ctypes.util
import errno
import hashlib
import os
from pathlib import Path
import re
import stat
import sys

MS_BIND = 0x1000
MS_REC = 0x4000
MS_PRIVATE = 1 << 18
MNT_DETACH = 2
UMOUNT_NOFOLLOW = 8
ROOT_UID = 0
NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
SOURCE_RE = re.compile(r"/[A-Za-z0-9_./ -]+")
ANCHOR_RE = re.compile(r"[0-9a-f]{16}")


class BindError(Exception):
    pass


def env_read(path):
    out = {}
    with open(path, encoding="utf-8") as stream:
        for line in stream.read().splitlines():
            key, sep, value = line.partition("=")
            if sep and re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
                out[key] = value.strip().strip('"')
    return out


def _libc():
    return ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)


def _mount(source, target, flags):
    src = None if source is None else os.fsencode(source)
    if _libc().mount(src, os.fsencode(str(target)), None, ctypes.c_ulong(flags), None) != 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), str(target))


def _umount(target, flags):
    if _libc().umount2(os.fsencode(str(target)), ctypes.c_int(flags)) != 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), str(target))


def _unescape(value):
    return re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), value)


def _mounted_identity(path):
    """(st_dev, st_ino) of the directory mounted at path, or None when nothing is mounted there."""
    with open("/proc/self/mountinfo", encoding="utf-8") as stream:
        points = {_unescape(line.split()[4]) for line in stream if len(line.split()) > 4}
    if str(path) not in points:
        return None
    st = os.stat(path)
    return st.st_dev, st.st_ino


def checked_name(name):
    if not isinstance(name, str) or not NAME_RE.fullmatch(name):
        raise BindError("Konteyner adı geçersiz.")
    return name


def checked_source(env, source):
    root = Path(env["SERVER_ROOT"])
    path = Path(source)
    if (not isinstance(source, str) or not SOURCE_RE.fullmatch(source) or not path.is_absolute()
            or ".." in path.parts or root not in path.parents
            or any(part.startswith(".") for part in path.relative_to(root).parts)):
        raise BindError("Bağlanan klasör kullanıcı alanının gizli olmayan bir alt klasörü olmalı: " + str(source))
    return str(path)


def walk(source):
    """An O_PATH-free descriptor of source, opened component by component without following links."""
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in Path(source).parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            os.close(fd)
            fd = child
        if not stat.S_ISDIR(os.fstat(fd).st_mode):
            raise BindError("Bağlanan klasör eksik veya sembolik bağlantı; konteyner başlatılmadı: " + source)
        return fd
    except OSError as err:
        os.close(fd)
        raise BindError("Bağlanan klasör eksik veya sembolik bağlantı; konteyner başlatılmadı: " + source) from err
    except BindError:
        os.close(fd)
        raise


def trusted_dir(path, create=False):
    """A real directory owned by root and writable by no one else; created 0700 when asked."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        if not create:
            raise BindError("Konteyner bağlama klasörü yok: " + str(path)) from None
        os.mkdir(path, 0o700)
        st = os.lstat(path)
    if (stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode) or st.st_uid != ROOT_UID
            or st.st_mode & (stat.S_IWGRP | stat.S_IWOTH)):
        raise BindError("Konteyner bağlama klasörü güvenli değil: " + str(path))


def base_dir(env, name, create):
    runtime = Path(env["RUNTIME_DIR"])
    anchors = Path(env["KONTEYNER_BAGLAMA_DIR"])
    if anchors.parent != runtime:
        raise BindError("Konteyner bağlama klasörü çalışma klasörünün içinde olmalı.")
    trusted_dir(runtime.parent)
    trusted_dir(runtime, create)
    trusted_dir(anchors, create)
    return anchors / checked_name(name)


def anchor_path(env, name, index, source):
    digest = hashlib.sha256(("%d:%s" % (index, source)).encode()).hexdigest()[:16]
    return Path(env["KONTEYNER_BAGLAMA_DIR"]) / checked_name(name) / digest


def birak(env, name):
    """Detach and remove every anchor of name; only empty folders are ever removed."""
    try:
        base = base_dir(env, name, create=False)
    except BindError:
        if not Path(env["KONTEYNER_BAGLAMA_DIR"]).exists():
            return
        raise
    if not os.path.lexists(base):
        return
    trusted_dir(base)
    for entry in sorted(os.listdir(base)):
        anchor = base / entry
        if not ANCHOR_RE.fullmatch(entry):
            raise BindError("Konteyner bağlama klasöründe beklenmeyen öge: " + str(anchor))
        for _ in range(8):  # stacked mounts left by an interrupted earlier start
            try:
                _umount(anchor, MNT_DETACH | UMOUNT_NOFOLLOW)
            except OSError as err:
                if err.errno in (errno.EINVAL, errno.ENOENT):
                    break
                raise
        os.rmdir(anchor)
    os.rmdir(base)


def bagla(env, name, sources):
    name = checked_name(name)
    if not sources:
        raise BindError("Bağlanacak klasör yok.")
    birak(env, name)
    base = base_dir(env, name, create=True)
    trusted_dir(base, create=True)
    anchors = []
    try:
        for index, source in enumerate(sources):
            source = checked_source(env, source)
            fd = walk(source)
            try:
                walked = os.fstat(fd)
                anchor = anchor_path(env, name, index, source)
                os.mkdir(anchor, 0o700)
                anchors.append(anchor)
                _mount("/proc/self/fd/%d" % fd, anchor, MS_BIND | MS_REC)
                _mount(None, anchor, MS_REC | MS_PRIVATE)
                if _mounted_identity(anchor) != (walked.st_dev, walked.st_ino):
                    raise BindError("Konteyner bağlaması doğrulanamadı; konteyner başlatılmadı: " + source)
            finally:
                os.close(fd)
    except (BindError, OSError) as err:
        try:
            birak(env, name)
        except (BindError, OSError):
            pass
        if isinstance(err, BindError):
            raise
        raise BindError("Konteyner bağlaması kurulamadı; konteyner başlatılmadı: " + str(err)) from err
    return anchors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True)
    parser.add_argument("action", choices=("bagla", "birak"))
    parser.add_argument("name")
    parser.add_argument("sources", nargs="*")
    args = parser.parse_args()
    try:
        env = env_read(args.state)
        if args.action == "bagla":
            bagla(env, args.name, args.sources)
        else:
            if args.sources:
                raise BindError("birak yalnız konteyner adını alır.")
            birak(env, args.name)
    except (BindError, OSError, KeyError) as err:
        print("HATA: %s" % err, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
