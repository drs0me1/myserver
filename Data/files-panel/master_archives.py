"""Bounded ZIP/RAR jobs for the unprivileged Files backend (DD-159/DD-166).

No shell, automatic folder watcher or root worker. Sources
are never removed. A private staging tree is published with NOREPLACE only
after every member and nested archive has passed the same global limits.
"""
import copy
import contextlib
import errno
import json
import os
import re
import secrets
import selectors
import signal
import stat
import struct
import subprocess
import sys
import threading
import time
import zipfile
import zlib

MAX_BYTES = 2 * 1024 ** 3
MAX_ENTRIES = 10000
MAX_LAYERS = 5
MAX_SECONDS = 900
MAX_CENTRAL = 16 * 1024 ** 2
CHUNK = 1024 * 1024
HISTORY = 20
JOB_RE = re.compile(r"^[a-f0-9]{24}$")
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
RAR_HELPER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "master_rar.py")
RAR_SUFFIX = re.compile(r"\.(?:rar|[r-z][0-9]{2})$", re.I)
# DD-181: already-compressed media is stored, not deflated again: same size, far less CPU.
STORED_SUFFIX = re.compile(r"\.(?:mkv|mp4|m4v|avi|mov|webm|ts|m2ts|mp3|m4a|aac|flac|ogg|opus|jpe?g|png|gif|webp|heic|"
                           r"zip|rar|7z|gz|tgz|bz2|xz|zst|iso|pdf|epub)$", re.I)
MAX_VOLUMES = 1000


class ArchiveError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


class Cancelled(Exception):
    pass


def job_source(job):
    """Günlük satırı için işin kaynağı: seçilen adlar, uzunsa kısaltılmış."""
    names = job.get("names") or []
    return ", ".join(names[:3]) + (" (+%d)" % (len(names) - 3) if len(names) > 3 else "")


class Archives:
    def __init__(self, files, workspace, rename, remove_tree, report=None):
        self.files, self.workspace = files, workspace
        self.rename, self.remove_tree = rename, remove_tree
        # DD-183: a finished job is reported once (the Files backend writes it to the audit
        # log, which Konsol → Ayarlar → Günlük shows). Tests pass their own callable.
        self.report = report or (lambda job: None)
        self.lock = threading.RLock()
        self.jobs, self.cancel_event, self.thread = [], None, None
        with self.root_fd() as root:
            try:
                os.mkdir(workspace, 0o700, dir_fd=root)
            except FileExistsError:
                pass
            fd = os.open(workspace, DIR_FLAGS, dir_fd=root)
            os.fchmod(fd, 0o700)
        with self.fd(fd):
            try:
                handle = os.open("jobs.json", FILE_FLAGS, dir_fd=fd)
                with os.fdopen(handle, "rb") as stream:
                    data = json.loads(stream.read(1024 * 1024))
                if not isinstance(data, list) or len(data) > HISTORY:
                    raise ValueError("invalid history")
                self.jobs = [j for j in data if isinstance(j, dict) and JOB_RE.fullmatch(str(j.get("id", "")))]
            except FileNotFoundError:
                pass
            except ValueError:
                # DD-182: a damaged history must not keep the Files service from starting.
                # It is kept beside the new one (private workspace) and history starts empty.
                aside = "jobs.json.bozuk-%d" % time.time()
                os.rename("jobs.json", aside, src_dir_fd=fd, dst_dir_fd=fd)
                print("dosya: arşiv işlem kaydı okunamadı; %s olarak saklandı, geçmiş boş başlıyor" % aside,
                      file=sys.stderr, flush=True)
                self.jobs = []
            except OSError as err:
                raise ArchiveError(500, "Arşiv işlem kaydı okunamadı; kayıt korunuyor.") from err
            interrupted = []
            for job in self.jobs:
                if job.get("status") in ("running", "queued"):
                    job.update(status="interrupted", message="Servis yeniden başladı; kaynaklar korundu. Sonucu hedef klasörde kontrol edin.", finished=int(time.time()))
                    interrupted.append(job)
                # Only this worker's validated job directories may be cleaned.
                self.remove_tree(fd, job["id"])
        self.persist()
        for job in interrupted:
            self.report(job)

    class fd:
        def __init__(self, value):
            self.value = value
        def __enter__(self):
            return self.value
        def __exit__(self, *args):
            os.close(self.value)

    def root_fd(self):
        return self.fd(self.files.open_dir([]))

    def work_fd(self):
        with self.root_fd() as root:
            return self.fd(os.open(self.workspace, DIR_FLAGS, dir_fd=root))

    def persist(self):
        with self.work_fd() as work:
            name = ".history-" + secrets.token_hex(6)
            handle = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=work)
            try:
                with os.fdopen(handle, "w", encoding="utf-8") as stream:
                    json.dump(self.jobs, stream, ensure_ascii=False)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.rename(name, "jobs.json", src_dir_fd=work, dst_dir_fd=work)
                os.fsync(work)
            finally:
                try:
                    os.unlink(name, dir_fd=work)
                except FileNotFoundError:
                    pass

    def status(self):
        with self.lock:
            return {"items": copy.deepcopy(self.jobs), "limits": {
                "bytes": MAX_BYTES, "entries": MAX_ENTRIES, "layers": MAX_LAYERS,
                "seconds": MAX_SECONDS, "formats": ["zip", "rar"], "concurrent": 1}}

    def submit(self, data):
        operation = data.get("operation")
        if operation not in ("zip", "unzip"):
            raise ArchiveError(400, "İşlem arşiv oluşturma veya arşiv açma olmalı.")
        source = self.files.split(data.get("path"))
        target = self.files.split(data.get("target"))
        if len("/".join(source).encode()) > 2048 or len("/".join(target).encode()) > 2048:
            raise ArchiveError(400, "Kaynak veya hedef yolu çok uzun.")
        names, name = data.get("names"), data.get("name")
        if not isinstance(names, list) or not 1 <= len(names) <= 100 or any(not isinstance(n, str) for n in names) or len(set(names)) != len(names):
            raise ArchiveError(400, "1–100 öge seçin.")
        for n in names:
            self.files.check_new_name(source, n)
            self.files.split("/".join(source + [n]))
        if sum(len(n.encode()) for n in names) > 8192:
            raise ArchiveError(400, "Seçilen adların toplamı çok uzun.")
        self.files.check_new_name(target, name)
        if name.startswith(".") or len(name.encode()) > 220:
            raise ArchiveError(400, "Sonuç adı noktayla başlayamaz; en çok 220 bayt olabilir.")
        if operation == "zip" and not name.lower().endswith(".zip"):
            raise ArchiveError(400, "Dosya adı .zip ile bitmeli.")
        if operation == "unzip" and (len(names) != 1 or not self.is_archive(names[0])):
            raise ArchiveError(400, "Açmak için tek bir ZIP veya RAR parçası seçin.")
        # The compact UI omits legacy depth controls: recurse automatically and
        # fail atomically at the safety ceiling, never report a partial open as done.
        automatic = operation == "unzip" and "nested" not in data and "layers" not in data
        nested, layers, conflict = data.get("nested", operation == "unzip"), data.get("layers", MAX_LAYERS), data.get("conflict", "rename")
        if not isinstance(nested, bool) or type(layers) is not int or not 1 <= layers <= MAX_LAYERS or conflict not in ("rename", "skip", "stop"):
            raise ArchiveError(400, "Arşiv seçenekleri geçersiz.")
        with self.fd(self.files.open_dir(source)) as src, self.fd(self.files.open_dir(target)) as dst, self.work_fd() as work:
            device = os.fstat(work).st_dev
            if os.fstat(dst).st_dev != device:
                raise ArchiveError(400, "Atomik işlem için hedef kullanıcı alanıyla aynı diskte olmalı.")
            for n in names:
                info = os.stat(n, dir_fd=src, follow_symlinks=False)
                if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
                    raise ArchiveError(400, "Bağlantı veya özel dosya arşivlenemez.")
                if operation == "unzip" and not stat.S_ISREG(info.st_mode):
                    raise ArchiveError(400, "Seçim ZIP veya RAR dosyası olmalı.")
                if stat.S_ISDIR(info.st_mode) and target[:len(source) + 1] == source + [n]:
                    raise ArchiveError(400, "ZIP hedefi seçilen klasörün içinde olamaz.")
            identity = (os.fstat(dst).st_dev, os.fstat(dst).st_ino)
        # DD-182: a job shows "done" before its worker has removed its staging area. If
        # nothing is queued or running, wait briefly for that cleanup instead of refusing.
        with self.lock:
            finishing = self.thread if (self.thread and self.thread.is_alive() and not any(
                j.get("status") in ("queued", "running") for j in self.jobs)) else None
        if finishing:
            finishing.join(10)
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise ArchiveError(409, "Bir arşiv işlemi sürüyor; bitmesini bekleyin veya iptal edin.")
            job = {"id": secrets.token_hex(12), "operation": operation, "path": "/".join(source), "names": names,
                   "target": "/".join(target), "name": name, "nested": nested, "layers": layers, "automatic": automatic, "conflict": conflict,
                   "status": "queued", "message": "Sıraya alındı", "created": int(time.time()), "bytes": 0, "entries": 0, "archives": 0}
            self.jobs = [job] + self.jobs[:HISTORY - 1]
            self.persist()
            self.cancel_event = threading.Event()
            self.thread = threading.Thread(target=self.run, args=(job, identity, self.cancel_event), daemon=True)
            self.thread.start()
            return copy.deepcopy(job)

    def cancel(self, job_id):
        with self.lock:
            job = next((j for j in self.jobs if j["id"] == job_id), None)
            if not job:
                raise ArchiveError(404, "Arşiv işlemi bulunamadı.")
            if job["status"] not in ("running", "queued"):
                raise ArchiveError(409, "Bu işlem artık çalışmıyor; sonucu kontrol edin.")
            self.cancel_event.set()
            job["message"] = "İptal ediliyor; geçici dosyalar temizleniyor"
            return copy.deepcopy(job)

    def check(self, job, event, deadline, added=0, entry=False):
        if event.is_set():
            raise Cancelled()
        if time.monotonic() > deadline:
            raise ArchiveError(400, "Arşiv işlemi süre sınırını aştı.")
        with self.lock:
            job["bytes"] += added
            job["entries"] += int(entry)
            if job["bytes"] > MAX_BYTES or job["entries"] > MAX_ENTRIES:
                raise ArchiveError(400, "Toplam açılmış veri veya dosya sayısı sınırı aşıldı; sonuç yayımlanmadı.")

    def zip_guard(self, stream, job):
        # Reject oversized central directories BEFORE ZipFile allocates them.
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        if size > MAX_BYTES:
            raise ArchiveError(400, "ZIP dosyası boyut sınırını aşıyor.")
        stream.seek(max(0, size - 65557))
        tail = stream.read(65557)
        position = tail.rfind(b"PK\x05\x06")
        if position < 0 or len(tail) - position < 22:
            raise ArchiveError(400, "Geçerli ZIP son kaydı bulunamadı.")
        _, disk, central_disk, on_disk, count, length, offset, comment = struct.unpack_from("<4s4H2LH", tail, position)
        if disk or central_disk or on_disk != count or count == 65535 or length == 0xffffffff or offset == 0xffffffff:
            raise ArchiveError(400, "Çok parçalı ZIP ve ZIP64 bu sürümde desteklenmiyor.")
        if len(tail) - position != 22 + comment or offset + length > size - 22 - comment:
            raise ArchiveError(400, "ZIP dizin kaydı geçersiz.")
        if length > MAX_CENTRAL or count + job["entries"] > MAX_ENTRIES:
            raise ArchiveError(400, "ZIP dizini veya toplam öge sayısı sınırı aşıldı.")
        stream.seek(0)

    def member_parts(self, info):
        name = info.filename
        # orig_filename reveals embedded NULs that ZipInfo otherwise truncates.
        if name != info.orig_filename or name.startswith("/") or "\\" in name or ":" in name:
            raise ArchiveError(400, "Arşivde güvensiz yol bulundu.")
        parts = name.rstrip("/").split("/")
        if len(parts) > 64 or any(p in ("", ".", "..") or re.search(r"[\x00-\x1f\x7f]", p) or len(p.encode()) > 255 for p in parts):
            raise ArchiveError(400, "Arşivde geçersiz yol bulundu.")
        if any(p in (self.files.trash, self.files.share, self.workspace) for p in parts):
            raise ArchiveError(400, "Arşiv iç sistem klasörü içeriyor.")
        mode = stat.S_IFMT(info.external_attr >> 16)
        if mode not in (0, stat.S_IFREG, stat.S_IFDIR) or (mode == stat.S_IFDIR and not info.is_dir()):
            raise ArchiveError(400, "Arşivde bağlantı veya özel dosya var.")
        if info.flag_bits & 1 or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            raise ArchiveError(400, "Şifreli ZIP veya bu sıkıştırma yöntemi desteklenmiyor (Store/Deflate gerekir).")
        return parts

    def make_dirs(self, base, parts, job, event, deadline):
        fd = os.dup(base)
        try:
            for part in parts:
                try:
                    os.mkdir(part, 0o775, dir_fd=fd)
                    self.check(job, event, deadline, entry=True)
                except FileExistsError:
                    pass
                nxt = os.open(part, DIR_FLAGS, dir_fd=fd)
                os.close(fd)
                fd = nxt
            return fd
        except BaseException:
            os.close(fd)
            raise

    def extract(self, stream, base, job, event, deadline, layer=1):
        self.check(job, event, deadline)
        self.zip_guard(stream, job)
        with zipfile.ZipFile(stream) as archive:
            with self.lock:
                job["archives"] += 1
            seen, nested = set(), []
            for info in archive.infolist():
                self.check(job, event, deadline)
                parts = self.member_parts(info)
                key = "/".join(parts)
                if key in seen:
                    raise ArchiveError(400, "Arşivde aynı adlı birden fazla öge var.")
                seen.add(key)
                if info.file_size + job["bytes"] > MAX_BYTES:
                    raise ArchiveError(400, "Toplam açılmış veri sınırı aşılacak; işlem durduruldu.")
                with self.fd(self.make_dirs(base, parts if info.is_dir() else parts[:-1], job, event, deadline)) as parent:
                    if info.is_dir():
                        continue
                    self.check(job, event, deadline, entry=True)
                    handle = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o664, dir_fd=parent)
                    with os.fdopen(handle, "wb") as output, archive.open(info) as member:
                        while True:
                            self.check(job, event, deadline)
                            chunk = member.read(CHUNK)
                            if not chunk:
                                break
                            self.check(job, event, deadline, added=len(chunk))
                            output.write(chunk)
                        output.flush()
                        os.fsync(output.fileno())
                    if self.is_archive(parts[-1]):
                        nested.append(parts)
            self.extract_nested(base, nested, job, event, deadline, layer)

    @staticmethod
    def is_archive(name):
        return name.lower().endswith(".zip") or bool(RAR_SUFFIX.search(name))

    def rar_volumes(self, parent, selected):
        names = os.listdir(parent)
        if len(names) > MAX_ENTRIES:
            raise ArchiveError(400, "RAR klasöründe çok fazla öge var.")
        part = re.fullmatch(r"(.+)\.part([0-9]+)\.rar", selected, re.I)
        if part:
            prefix = part[1]
            pattern = re.compile(re.escape(prefix) + r"\.part([0-9]+)\.rar\Z", re.I)
            number = lambda m: int(m[1])
        else:
            prefix = RAR_SUFFIX.sub("", selected)
            pattern = re.compile(re.escape(prefix) + r"\.(rar|[r-z][0-9]{2})\Z", re.I)
            number = lambda m: 1 if m[1].lower() == "rar" else (ord(m[1][0].lower()) - ord("r")) * 100 + int(m[1][1:]) + 2
        found = [(number(match), name) for name in names if (match := pattern.fullmatch(name))]
        found.sort()
        if not found or len(found) > MAX_VOLUMES or [n for n, _ in found] != list(range(1, len(found) + 1)):
            raise ArchiveError(400, "RAR parçaları eksik veya sırası belirsiz; ilk .rar/part01.rar ve tüm parçalar aynı klasörde olmalı.")
        return [name for _, name in found]

    def helper_output(self, args, job, event, deadline, limit):
        """Bound output and wall time even while unrar produces no data; reap its group."""
        env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"}
        process = subprocess.Popen([sys.executable, RAR_HELPER] + args, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0,
                                   start_new_session=True, env=env)
        total = 0
        try:
            with selectors.DefaultSelector() as poll:
                poll.register(process.stdout, selectors.EVENT_READ)
                while True:
                    self.check(job, event, deadline)
                    if not poll.select(0.1):
                        continue
                    chunk = os.read(process.stdout.fileno(), CHUNK)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > limit:
                        raise ArchiveError(400, "RAR çıktısı boyut sınırını aştı; sonuç yayımlanmadı.")
                    yield chunk
                while process.poll() is None:
                    self.check(job, event, deadline)
                    event.wait(0.05)
                if process.returncode:
                    raise ArchiveError(400, "RAR açılamadı: eksik/bozuk/şifreli parça, CRC hatası veya bellek sınırı. Sonuç yayımlanmadı.")
        finally:
            # The helper's comment decoder may have descendants even after it exits.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.stdout.close()
            process.wait()

    def extract_rar(self, parent, selected, base, job, event, deadline, layer):
        volumes = self.rar_volumes(parent, selected)
        with self.work_fd() as work, self.fd(os.open(job["id"], DIR_FLAGS, dir_fd=work)) as stage:
            snapshot = "rar-" + secrets.token_hex(8)
            os.mkdir(snapshot, 0o700, dir_fd=stage)
            source_info, compressed = [], 0
            try:
                with self.fd(os.open(snapshot, DIR_FLAGS, dir_fd=stage)) as snap:
                    for name in volumes:
                        self.check(job, event, deadline)
                        with self.fd(os.open(name, FILE_FLAGS, dir_fd=parent)) as src:
                            info = os.fstat(src)
                            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_dev != os.fstat(stage).st_dev:
                                raise ArchiveError(400, "RAR parçası tek bağlı normal dosya ve aynı diskte olmalı.")
                            compressed += info.st_size
                            if compressed > MAX_BYTES:
                                raise ArchiveError(400, "RAR parçalarının toplam boyutu sınırı aşıyor.")
                            handle = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=snap)
                            copied = 0
                            with os.fdopen(handle, "wb") as output:
                                while True:
                                    self.check(job, event, deadline)
                                    chunk = os.read(src, CHUNK)
                                    if not chunk:
                                        break
                                    copied += len(chunk)
                                    if copied > info.st_size:
                                        raise ArchiveError(409, "RAR parçası işlem sırasında değişti.")
                                    output.write(chunk)
                            after = os.fstat(src)
                            if copied != info.st_size or self.fingerprint(info) != self.fingerprint(after):
                                raise ArchiveError(409, "RAR parçası işlem sırasında değişti.")
                            source_info.append((name, self.fingerprint(info)))
                archive_path = os.path.join(self.files.root, self.workspace, job["id"], snapshot, volumes[0])
                data = b"".join(self.helper_output(["list", archive_path, str(MAX_ENTRIES - job["entries"]), str(MAX_BYTES - job["bytes"])],
                                                  job, event, min(deadline, time.monotonic() + 30), MAX_CENTRAL))
                metadata = json.loads(data)
                if metadata.get("volumes") != volumes:
                    raise ArchiveError(400, "RAR parça dizisi arşiv başlıklarıyla uyuşmuyor.")
                seen, nested = set(), []
                with self.lock:
                    job["archives"] += 1
                for item in metadata["entries"]:
                    self.check(job, event, deadline)
                    name, size = item["name"], item["size"]
                    if any(c in name for c in "*?[]"):
                        raise ArchiveError(400, "RAR dosya adında belirsiz seçim karakteri var.")
                    parts = self.member_parts(zipfile.ZipInfo(name))
                    key = "/".join(parts)
                    if key in seen:
                        raise ArchiveError(400, "Arşivde aynı adlı birden fazla öge var.")
                    seen.add(key)
                    if size + job["bytes"] > MAX_BYTES:
                        raise ArchiveError(400, "Toplam açılmış veri sınırı aşılacak; işlem durduruldu.")
                    with self.fd(self.make_dirs(base, parts if item["directory"] else parts[:-1], job, event, deadline)) as dest:
                        if item["directory"]:
                            continue
                        self.check(job, event, deadline, entry=True)
                        handle = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o664, dir_fd=dest)
                        total, checksum = 0, 0
                        with os.fdopen(handle, "wb") as output, contextlib.closing(self.helper_output(["stream", archive_path, name], job, event, deadline, size)) as chunks:
                            for chunk in chunks:
                                self.check(job, event, deadline, added=len(chunk))
                                total += len(chunk)
                                checksum = zlib.crc32(chunk, checksum)
                                output.write(chunk)
                            output.flush()
                            os.fsync(output.fileno())
                        if total != size or (item["crc"] is not None and checksum != item["crc"]):
                            raise ArchiveError(400, "RAR içerik uzunluğu veya CRC doğrulaması başarısız.")
                    if self.is_archive(parts[-1]):
                        nested.append(parts)
                for name, fingerprint in source_info:
                    if self.fingerprint(os.stat(name, dir_fd=parent, follow_symlinks=False)) != fingerprint:
                        raise ArchiveError(409, "Kaynak RAR parçası değişti; sonuç yayımlanmadı.")
            finally:
                self.remove_tree(stage, snapshot)
        self.extract_nested(base, nested, job, event, deadline, layer)

    @staticmethod
    def fingerprint(info):
        return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)

    def extract_nested(self, base, nested, job, event, deadline, layer):
        if not job["nested"]:
            return
        done = set()
        for parts in nested:
            if layer >= job["layers"]:
                if job.get("automatic"):
                    raise ArchiveError(400, "Arşiv iç içe açma güvenlik sınırını aşıyor; sonuç yayımlanmadı.")
                stem = re.sub(r"(?:\.part[0-9]+)?\.(?:rar|[r-z][0-9]{2})$", ".rar", parts[-1], flags=re.I)
                key = tuple(parts[:-1] + [stem])
                if key not in done:
                    done.add(key)
                    with self.lock:
                        job["limited"] = job.get("limited", 0) + 1
                continue
            with self.fd(self.make_dirs(base, parts[:-1], job, event, deadline)) as parent:
                first = self.rar_volumes(parent, parts[-1])[0] if RAR_SUFFIX.search(parts[-1]) else parts[-1]
                key = tuple(parts[:-1] + [first])
                if key in done:
                    continue
                done.add(key)
                dest = re.sub(r"(?:\.part[0-9]+)?\.(?:zip|rar)$", "", first, flags=re.I) or "arsiv"
                for index in range(1, 102):
                    candidate = dest if index == 1 else "%s (%d)" % (dest, index)
                    try:
                        os.mkdir(candidate, 0o775, dir_fd=parent)
                        break
                    except FileExistsError:
                        continue
                else:
                    raise ArchiveError(409, "İç arşiv için boş klasör adı bulunamadı.")
                self.check(job, event, deadline, entry=True)
                with self.fd(os.open(candidate, DIR_FLAGS, dir_fd=parent)) as child:
                    if RAR_SUFFIX.search(first):
                        self.extract_rar(parent, first, child, job, event, deadline, layer + 1)
                    else:
                        with os.fdopen(os.open(first, FILE_FLAGS, dir_fd=parent), "rb") as inner:
                            self.extract(inner, child, job, event, deadline, layer + 1)

    def pack(self, archive, parent, name, relative, device, job, event, deadline, depth=0):
        self.check(job, event, deadline, entry=True)
        self.member_parts(zipfile.ZipInfo(relative))
        if depth > 64 or name in (self.files.trash, self.files.share, self.workspace):
            raise ArchiveError(400, "İç sistem klasörü veya çok derin klasör arşivlenemez.")
        info = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if info.st_dev != device or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
            raise ArchiveError(400, "Bağlantı, özel dosya veya farklı disk arşivlenemez.")
        flags = DIR_FLAGS if stat.S_ISDIR(info.st_mode) else FILE_FLAGS
        with self.fd(os.open(name, flags, dir_fd=parent)) as source:
            actual = os.fstat(source)
            if (actual.st_dev, actual.st_ino, actual.st_mode) != (info.st_dev, info.st_ino, info.st_mode):
                raise ArchiveError(409, "Kaynak işlem sırasında değişti.")
            if stat.S_ISDIR(info.st_mode):
                entry = zipfile.ZipInfo(relative + "/")
                entry.external_attr = (stat.S_IFDIR | 0o775) << 16
                archive.writestr(entry, b"")
                with os.scandir(source) as listing:
                    for child in listing:
                        self.files.check_new_name([], child.name)
                        self.pack(archive, source, child.name, relative + "/" + child.name, device, job, event, deadline, depth + 1)
            else:
                if info.st_nlink != 1 or info.st_size + job["bytes"] > MAX_BYTES:
                    raise ArchiveError(400, "Çok bağlı dosya veya toplam veri sınırını aşan kaynak.")
                entry = zipfile.ZipInfo(relative)
                entry.compress_type = zipfile.ZIP_STORED if STORED_SUFFIX.search(relative) else zipfile.ZIP_DEFLATED
                entry.external_attr = (stat.S_IFREG | 0o664) << 16
                with archive.open(entry, "w") as output:
                    while True:
                        self.check(job, event, deadline)
                        chunk = os.read(source, CHUNK)
                        if not chunk:
                            break
                        self.check(job, event, deadline, added=len(chunk))
                        output.write(chunk)
                after = os.fstat(source)
                if (after.st_size, after.st_mtime_ns, after.st_ctime_ns) != (info.st_size, info.st_mtime_ns, info.st_ctime_ns):
                    raise ArchiveError(409, "Kaynak dosya işlem sırasında değişti; sonuç yayımlanmadı.")

    def publish(self, stage, identity, job, event, deadline):
        with self.fd(self.files.open_dir(self.files.split(job["target"]))) as dest:
            info = os.fstat(dest)
            if (info.st_dev, info.st_ino) != identity:
                raise ArchiveError(409, "Hedef klasör değişti; işlem durduruldu.")
            # Cancellation and publication are serialized: cancel never claims
            # success after the result has already become visible.
            with self.lock, self.files.lock:
                self.check(job, event, deadline)
                name = job["name"]
                for index in range(1, 102):
                    try:
                        self.rename(stage, "result", dest, name)
                        job.update(status="done", result="/".join(filter(None, [job["target"], name])), message="Tamamlandı; kaynaklar korundu.")
                        try:
                            os.fsync(dest)
                        except OSError:
                            job["message"] += " Hedef dizin kalıcılığı doğrulanamadı."
                        if job.get("limited"):
                            job["message"] += " %d iç arşiv katman sınırı nedeniyle kapalı bırakıldı." % job["limited"]
                        return
                    except FileExistsError:
                        if job["conflict"] == "skip":
                            job.update(status="skipped", message="Hedefte aynı ad var; sonuç atlandı, mevcut dosyalar korundu.")
                            return
                        if job["conflict"] == "stop":
                            raise ArchiveError(409, "Hedefte aynı ad var; üzerine yazılmadı.")
                        stem = job["name"][:-4] if job["operation"] == "zip" else job["name"]
                        name = "%s (%d)%s" % (stem, index + 1, ".zip" if job["operation"] == "zip" else "")
                raise ArchiveError(409, "Sonuç için boş ad bulunamadı.")

    def run(self, job, identity, event):
        deadline = time.monotonic() + MAX_SECONDS
        # DD-181: the job thread (and the unrar it starts) yields CPU to the Files UI and
        # other services. Linux sets niceness per thread id; elsewhere it is skipped.
        if sys.platform == "linux":
            try:
                os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), 10)
            except OSError:
                pass
        try:
            with self.lock:
                job.update(status="running", message="Arşiv oluşturuluyor" if job["operation"] == "zip" else "Arşiv açılıyor")
                self.persist()
            with self.work_fd() as work:
                os.mkdir(job["id"], 0o700, dir_fd=work)
                with self.fd(os.open(job["id"], DIR_FLAGS, dir_fd=work)) as stage:
                    if job["operation"] == "zip":
                        handle = os.open("result", os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o664, dir_fd=stage)
                        with os.fdopen(handle, "w+b") as output:
                            with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=False) as archive:
                                with self.fd(self.files.open_dir(self.files.split(job["path"]))) as source:
                                    for name in job["names"]:
                                        self.pack(archive, source, name, name, os.fstat(work).st_dev, job, event, deadline)
                            output.flush()
                            os.fsync(output.fileno())
                    else:
                        os.mkdir("result", 0o775, dir_fd=stage)
                        if RAR_SUFFIX.search(job["names"][0]):
                            with self.fd(self.files.open_dir(self.files.split(job["path"]))) as parent, self.fd(os.open("result", DIR_FLAGS, dir_fd=stage)) as target:
                                self.extract_rar(parent, job["names"][0], target, job, event, deadline, 1)
                            self.publish(stage, identity, job, event, deadline)
                            return
                        handle, info = self.files.open_file(self.files.split(job["path"]) + job["names"])
                        with os.fdopen(handle, "rb") as source, self.fd(os.open("result", DIR_FLAGS, dir_fd=stage)) as target:
                            if info.st_nlink != 1 or info.st_dev != os.fstat(work).st_dev:
                                raise ArchiveError(400, "ZIP tek bağlı dosya ve aynı diskte olmalı.")
                            self.extract(source, target, job, event, deadline)
                            after = os.fstat(source.fileno())
                            if (info.st_size, info.st_mtime_ns, info.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                                raise ArchiveError(409, "Kaynak ZIP değişti; sonuç yayımlanmadı.")
                    self.publish(stage, identity, job, event, deadline)
        except Cancelled:
            with self.lock:
                job.update(status="cancelled", message="İptal edildi; kaynaklar korundu, sonuç yayımlanmadı.")
        except Exception as err:
            message = str(err) if isinstance(err, ArchiveError) else "Arşiv işlenemedi; bozuk/uyumsuz arşiv, değişen kaynak veya disk/izin hatası."
            with self.lock:
                job.update(status="failed", message=message)
        finally:
            try:
                with self.work_fd() as work:
                    self.remove_tree(work, job["id"])
            except OSError:
                with self.lock:
                    job["message"] += " Geçici alan temizlenemedi; normal dosya listesine açılmadı."
            with self.lock:
                job["finished"] = int(time.time())
                try:
                    self.persist()
                except OSError:
                    job["message"] += " İşlem geçmişi diske yazılamadı; hedefi kontrol edin."
            self.report(job)
