"""Selective installer-only data permissions repair, through pinned descriptors."""
import argparse
import errno
import os
from pathlib import PurePath
import stat
import sys

DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
RACES = (errno.ENOENT, errno.ENOTDIR, errno.ELOOP, errno.ESTALE)


def open_root(path, create=False):
    path = PurePath(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('mutlak ve geçerli kök yolu gerekli')
    fd = os.open('/', DIR)
    try:
        for part in path.parts[1:]:
            if create:
                try:
                    os.mkdir(part, 0o775, dir_fd=fd)
                except FileExistsError:
                    pass
            new = os.open(part, DIR, dir_fd=fd)
            os.close(fd)
            fd = new
        return fd
    except BaseException:
        os.close(fd)
        raise


def repair(root, uid, gid, excluded):
    changed = 0

    def fix(fd):
        nonlocal changed
        st = os.fstat(fd)
        directory = stat.S_ISDIR(st.st_mode)
        # Never mutate devices/FIFOs, symlinks or multiply-linked files.
        if not directory and (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1):
            return False
        mode = 0o775 if directory else 0o664
        owner_diff = (st.st_uid, st.st_gid) != (uid, gid)
        mode_diff = stat.S_IMODE(st.st_mode) != mode
        if owner_diff:
            os.fchown(fd, uid, gid)
        if mode_diff:
            os.fchmod(fd, mode)
        changed += bool(owner_diff or mode_diff)
        return directory

    def walk(fd, top=False):
        if not fix(fd):
            return
        with os.scandir(fd) as entries:
            for entry in entries:
                if top and entry.name in excluded:
                    continue
                child = None
                try:
                    st = entry.stat(follow_symlinks=False)
                    if not (stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode)):
                        continue
                    flags = DIR if stat.S_ISDIR(st.st_mode) else os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW
                    child = os.open(entry.name, flags, dir_fd=fd)
                    current = os.fstat(child)
                    if (current.st_dev, current.st_ino) != (st.st_dev, st.st_ino):
                        continue
                    walk(child)
                except OSError as error:
                    if error.errno not in RACES:
                        raise
                finally:
                    if child is not None:
                        os.close(child)

    fd = open_root(root)
    try:
        walk(fd, top=True)
    finally:
        os.close(fd)
    return changed


def prepare_directory(path, uid, gid, mode=None):
    fd = open_root(path, create=True)
    try:
        if mode is not None:
            st = os.fstat(fd)
            if (st.st_uid, st.st_gid) != (uid, gid):
                os.fchown(fd, uid, gid)
            if stat.S_IMODE(st.st_mode) != mode:
                os.fchmod(fd, mode)
    finally:
        os.close(fd)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--mkdir', action='store_true')
    parser.add_argument('--directory-mode', type=lambda value: int(value, 8))
    parser.add_argument('root')
    parser.add_argument('uid', type=int)
    parser.add_argument('gid', type=int)
    parser.add_argument('excluded', nargs='*')
    args = parser.parse_args()
    try:
        if args.mkdir or args.directory_mode is not None:
            prepare_directory(args.root, args.uid, args.gid, args.directory_mode)
        else:
            print(repair(args.root, args.uid, args.gid, args.excluded))
    except (OSError, ValueError, RecursionError):
        print('HATA: kullanıcı alanı izinleri güvenli onarılamadı.', file=sys.stderr)
        sys.exit(1)
