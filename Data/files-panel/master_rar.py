"""Resource-limited RAR helper; metadata or one member on stdout, never extraction paths.

Called only by master_archives with a private, descriptor-validated volume snapshot.
No shell, password prompt, destination writes or inherited credentials.
"""
import json
import os
import resource
import stat
import sys

UNRAR = "/usr/bin/unrar"
MAX_MEMORY = 192 * 1024 ** 2


def main():
    resource.setrlimit(resource.RLIMIT_AS, (MAX_MEMORY, MAX_MEMORY))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    mode, archive = sys.argv[1:3]
    if mode == "stream":
        resource.setrlimit(resource.RLIMIT_CPU, (900, 900))
        # -@ disables @listfile expansion; -- ends options; no extractor writes.
        os.execv(UNRAR, [UNRAR, "p", "-inul", "-p-", "-cfg-", "-@", "--", archive, sys.argv[3]])
    if mode != "list":
        raise ValueError("mode")
    resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
    import rarfile
    rarfile.UNRAR_TOOL = UNRAR
    # Some RAR3 archive comments also require decompression. Do not choose a
    # different backend with weaker solid/volume support if unrar is absent.
    rarfile.CURRENT_SETUP = rarfile.ToolSetup(rarfile.UNRAR_CONFIG)
    count, metadata_bytes = 0, 0
    limit, budget = int(sys.argv[3]), int(sys.argv[4])

    def bounded(info):
        nonlocal count, metadata_bytes
        count += 1
        metadata_bytes += len((getattr(info, "filename", None) or "").encode("utf-8")) + 256
        if count > limit + 2048 or metadata_bytes > 8 * 1024 ** 2:
            raise ValueError("metadata limit")

    try:
        with rarfile.RarFile(archive, errors="strict", info_callback=bounded) as source:
            if source.needs_password():
                raise ValueError("encrypted")
            entries, total = [], 0
            for info in source.infolist():
                # Windows attributes can overlap Unix device bits (e.g. 0x2020).
                # rarfile normalizes both RAR generations' Unix host ID to 3.
                file_mode = stat.S_IFMT(info.mode) if info.host_os == rarfile.RAR_OS_UNIX else 0
                if (info.is_symlink() or getattr(info, "file_redir", None)
                        or not (info.is_file() or info.is_dir())
                        or file_mode not in (0, stat.S_IFREG, stat.S_IFDIR)):
                    raise ValueError("unsafe member")
                total += info.file_size
                if len(entries) >= limit or total > budget or info.file_size < 0:
                    raise ValueError("size or entry limit")
                entries.append({"name": info.filename, "size": info.file_size,
                                "directory": info.is_dir(), "crc": info.CRC})
            print(json.dumps({"entries": entries, "volumes": [os.path.basename(v) for v in source.volumelist()]}))
    except (rarfile.Error, ValueError, OSError, MemoryError):
        # No untrusted archive comments/paths or subprocess output in logs/API.
        print(json.dumps({"error": "RAR okunamadı: eksik parça, bozuk/şifreli arşiv, bağlantı veya kaynak sınırı."}))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
