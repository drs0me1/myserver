#!/usr/bin/env python3
"""Konsol hesabı ve oturumları (DD-194, DD-205). Yalnız root; hiçbir şey sunucu dışına çıkmaz.

Tailscale adresinde oturum sorulmaz: cihazı Tailscale doğrular, kök backend Caddy'nin oturum
sorusuna orada hep "geç" der. Hesap (kullanıcı adı + parola) internet adresinin anahtarıdır;
operatör onu Tailscale'den Ayarlar → Sistem → Konsol hesabı bölümünde oluşturur. Parola yalnız
scrypt özeti, oturum belirteci yalnız SHA-256 özeti olarak saklanır. Kök backend (master-panel)
bu modülü içe aktarır; `master-konsol` (root CLI) aynı dosyaları aynı kilitle değiştirir:
durum, sıfırlama ve kısa ömürlü otomasyon oturumu.
"""
import argparse
import fcntl
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import stat
import sys
import threading
import time
from collections import deque
from contextlib import contextmanager

ACCOUNT_FILE = "hesap.json"
SESSIONS_FILE = "oturumlar.json"
LOCK_FILE = ".kilit"
COOKIE = "konsol_oturum"
# User decision (2026-10-01): a sign-in lasts seven days; it is not renewed by use.
SESSION_SECONDS = 7 * 86400
AUTOMATION_MAX_SECONDS = 3600
MAX_SESSIONS = 16
FILE_LIMIT = 64 * 1024
USER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{2,31}\Z")
TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{43}\Z")
HEX_RE = re.compile(r"[0-9a-f]+\Z")
PASSWORD_MIN = 10
PASSWORD_MAX = 256
# Same budget as WebDAV logins (DD-180): five failures per address within 60 s
# close that address for five minutes. The table is bounded and fails closed.
FAILURES = 5
WINDOW_SECONDS = 60
BLOCK_SECONDS = 300
MAX_ENTRIES = 4096
# DD-195: failures through the public (internet) address also share one budget, so
# many addresses cannot multiply the per-address limit. Tailscale is never counted
# here and stays open while the public sign-in waits.
PUBLIC_FAILURES = 20
PUBLIC_WINDOW_SECONDS = 600
PUBLIC_BLOCK_SECONDS = 900
# One password check at a time per address and two at once in total: each scrypt
# check needs 16 MiB, and one HTTP/2 connection can carry many requests.
HASH_SLOTS = 2
HASH_WAIT_SECONDS = 10
NO_ACCOUNT = "Konsol hesabı yok; Tailscale adresinden Ayarlar → Sistem → Konsol hesabı bölümünde oluşturun."
BAD_LOGIN = "Kullanıcı adı veya parola hatalı."


class AuthError(Exception):
    def __init__(self, message, status=400, retry_after=None):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


def env_read(path):
    with open(path, encoding="utf-8") as stream:
        return {k: v.strip('"') for line in stream if not line.startswith("#") and "=" in line
                for k, v in [line.rstrip("\n").split("=", 1)]}


def digest(secret, salt):
    return hashlib.scrypt(secret.encode("utf-8"), salt=bytes.fromhex(salt),
                          n=16384, r=8, p=1, dklen=32).hex()


def make_record(secret):
    salt = secrets.token_hex(16)
    return {"salt": salt, "hash": digest(secret, salt)}


def matches(record, secret):
    return hmac.compare_digest(digest(secret, record["salt"]), record["hash"])


_decoy = None
_decoy_lock = threading.Lock()


def decoy():
    """A never-matching record, made on first use (no scrypt work at service start)."""
    global _decoy
    with _decoy_lock:
        if _decoy is None:
            _decoy = make_record(secrets.token_hex(16))
        return _decoy


def hashed_record(value):
    return (isinstance(value, dict) and isinstance(value.get("salt"), str) and len(value["salt"]) == 32
            and HEX_RE.fullmatch(value["salt"]) is not None and isinstance(value.get("hash"), str)
            and len(value["hash"]) == 64 and HEX_RE.fullmatch(value["hash"]) is not None)


def token_key(token):
    if not isinstance(token, str) or not TOKEN_RE.fullmatch(token):
        return None
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def valid_user(user):
    if not isinstance(user, str) or not USER_RE.fullmatch(user):
        raise AuthError("Kullanıcı adı 3–32 karakter olmalı: harf, rakam veya . _ - (ilk karakter harf ya da rakam).")
    return user


def valid_password(password):
    if (not isinstance(password, str) or not PASSWORD_MIN <= len(password) <= PASSWORD_MAX
            or any(ord(c) < 32 or ord(c) == 127 for c in password)):
        raise AuthError("Parola %d–%d karakter olmalı ve kontrol karakteri içermemeli." % (PASSWORD_MIN, PASSWORD_MAX))
    return password


class Store:
    """Account and sessions in one root-only 0700 directory."""

    def __init__(self, directory, clock=time.time):
        self.dir = str(directory)
        self.clock = clock

    def path(self, name):
        return os.path.join(self.dir, name)

    def check_dir(self):
        try:
            st = os.lstat(self.dir)
        except FileNotFoundError as err:
            raise AuthError("Konsol hesap klasörü yok; kurulumu yeniden çalıştırın.", 503) from err
        if (not stat.S_ISDIR(st.st_mode) or st.st_uid != os.geteuid()
                or stat.S_IMODE(st.st_mode) & 0o077):
            raise AuthError("Konsol hesap klasörü güvenli değil; kurulumu yeniden çalıştırın.", 503)

    @contextmanager
    def locked(self):
        self.check_dir()
        fd = os.open(self.path(LOCK_FILE), os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def read(self, name):
        """Bounded no-follow read of a regular file; None when it does not exist."""
        self.check_dir()
        try:
            fd = os.open(self.path(name), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        except FileNotFoundError:
            return None
        except OSError as err:
            raise AuthError("Konsol hesap kaydı okunamadı.", 503) from err
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_size > FILE_LIMIT:
                raise AuthError("Konsol hesap kaydı okunamadı.", 503)
            data = os.read(fd, FILE_LIMIT + 1)
        finally:
            os.close(fd)
        try:
            value = json.loads(data.decode("utf-8"))
        except (ValueError, UnicodeDecodeError, RecursionError) as err:
            raise AuthError("Konsol hesap kaydı bozuk; `sudo master-konsol sifirla` ile sıfırlayın.", 503) from err
        if not isinstance(value, dict):
            raise AuthError("Konsol hesap kaydı bozuk; `sudo master-konsol sifirla` ile sıfırlayın.", 503)
        return value

    def write(self, name, value):
        data = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
        temp = self.path(".%s.%s" % (name, secrets.token_hex(6)))
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        try:
            view = memoryview(data)
            while view:
                view = view[os.write(fd, view):]
            os.fsync(fd)
        except BaseException:
            os.close(fd)
            os.unlink(temp)
            raise
        os.close(fd)
        try:
            os.replace(temp, self.path(name))
        except BaseException:
            os.unlink(temp)
            raise
        dfd = os.open(self.dir, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)

    def remove(self, name):
        try:
            os.unlink(self.path(name))
        except FileNotFoundError:
            pass

    # -- records
    def account(self):
        value = self.read(ACCOUNT_FILE)
        if value is None:
            return None
        if (value.get("schema") != 1 or not isinstance(value.get("kullanici"), str)
                or not USER_RE.fullmatch(value["kullanici"]) or not hashed_record(value)):
            raise AuthError("Konsol hesap kaydı bozuk; `sudo master-konsol sifirla` ile sıfırlayın.", 503)
        return value

    def sessions(self):
        """Unexpired, well-formed sessions only; anything else simply does not authorize."""
        value = self.read(SESSIONS_FILE) or {}
        now = self.clock()
        return {key: item for key, item in value.items()
                if isinstance(key, str) and len(key) == 64 and HEX_RE.fullmatch(key)
                and isinstance(item, dict) and type(item.get("olusturma")) is int
                and type(item.get("bitis")) is int and item["bitis"] > now}

    def save_sessions(self, sessions):
        newest = sorted(sessions.items(), key=lambda pair: pair[1]["olusturma"])[-MAX_SESSIONS:]
        self.write(SESSIONS_FILE, dict(newest))

    def new_session(self, sessions, seconds=SESSION_SECONDS, kind="giris"):
        token = secrets.token_urlsafe(32)
        now = int(self.clock())
        sessions[token_key(token)] = {"olusturma": now, "bitis": now + seconds, "tur": kind}
        self.save_sessions(sessions)
        return token

    # -- checks (every Konsol request; never writes)
    def user_for(self, token):
        key = token_key(token)
        if key is None or key not in self.sessions():
            return None
        account = self.account()
        # A root-issued automation session may exist before the operator's first sign-in.
        return account["kullanici"] if account else "otomasyon"

    def status(self, token, reveal=False):
        """State for the sign-in page and the account card. The user name goes out with an open
        session or to a trusted caller (DD-205: the tailnet address), never to an anonymous
        internet visitor."""
        account = self.account()
        if account is None:
            return {"durum": "kurulum"}
        key = token_key(token)
        if key is not None and key in self.sessions():
            return {"durum": "acik", "kullanici": account["kullanici"],
                    "oturum_gun": SESSION_SECONDS // 86400}
        return {"durum": "giris", "kullanici": account["kullanici"]} if reveal else {"durum": "giris"}

    # -- changes
    def reset(self):
        """Deletes the account and every session; the internet address closes with it (DD-195)."""
        with self.locked():
            for name in (ACCOUNT_FILE, SESSIONS_FILE):
                self.remove(name)

    def create(self, user, password):
        """DD-205: no code. The request reached the backend from another Tailscale device, which is
        the credential; the backend refuses this over the internet. No session is opened: the
        tailnet needs none and the internet address signs in with the new password."""
        valid_user(user)
        valid_password(password)
        with self.locked():
            if self.account() is not None:
                raise AuthError("Konsol hesabı zaten var; parolayı değiştirin ya da `sudo master-konsol sifirla` ile sıfırlayın.", 409)
            record = make_record(password)
            self.write(ACCOUNT_FILE, {"schema": 1, "kullanici": user, "salt": record["salt"],
                                      "hash": record["hash"], "degisim": int(self.clock())})

    def login(self, user, password):
        account = self.account()
        if account is None:
            raise AuthError(NO_ACCOUNT, 409)
        if not isinstance(user, str) or not isinstance(password, str) or len(password) > PASSWORD_MAX:
            raise AuthError(BAD_LOGIN, 401)
        same = hmac.compare_digest(user.encode("utf-8"), account["kullanici"].encode("utf-8"))
        # A wrong user name costs the same scrypt check, so timing does not reveal it.
        if not matches(account if same else decoy(), password) or not same:
            raise AuthError(BAD_LOGIN, 401)
        with self.locked():
            return self.new_session(self.sessions())

    def logout(self, token):
        key = token_key(token)
        if key is None:
            return
        with self.locked():
            sessions = self.sessions()
            if sessions.pop(key, None) is not None:
                self.save_sessions(sessions)

    def change_password(self, token, old, new):
        valid_password(new)
        key = token_key(token)
        with self.locked():
            account = self.account()
            sessions = self.sessions()
            if account is None or key is None or key not in sessions:
                raise AuthError("Oturum gerekli; yeniden giriş yapın.", 401)
            if not isinstance(old, str) or len(old) > PASSWORD_MAX or not matches(account, old):
                raise AuthError("Mevcut parola hatalı.", 401)
            if matches(account, new):
                raise AuthError("Yeni parola mevcut paroladan farklı olmalı.")
            record = make_record(new)
            account.update(salt=record["salt"], hash=record["hash"], degisim=int(self.clock()))
            self.write(ACCOUNT_FILE, account)
            # Every other sign-in ends; the browser that changed the password stays.
            self.save_sessions({key: sessions[key]})

    def set_password(self, new):
        """DD-205: from the tailnet the current password is not asked (the device is the
        credential) and no session is needed; every session ends, so internet browsers sign in again."""
        valid_password(new)
        with self.locked():
            account = self.account()
            if account is None:
                raise AuthError(NO_ACCOUNT, 409)
            record = make_record(new)
            account.update(salt=record["salt"], hash=record["hash"], degisim=int(self.clock()))
            self.write(ACCOUNT_FILE, account)
            self.save_sessions({})

    def automation_session(self, seconds):
        if type(seconds) is not int or not 60 <= seconds <= AUTOMATION_MAX_SECONDS:
            raise AuthError("Süre 60–%d saniye olmalı." % AUTOMATION_MAX_SECONDS)
        with self.locked():
            return self.new_session(self.sessions(), seconds, kind="otomasyon")


class Attempts:
    """Per-address failure window for sign-in and current-password checks, plus one
    shared window for the public address (DD-195) and a bound on parallel checks."""

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.entries = {}
        self.public = {"fails": deque(), "until": 0}
        self.inflight = set()
        self.slots = threading.BoundedSemaphore(HASH_SLOTS)

    def _prune(self, now):
        for key, entry in list(self.entries.items()):
            while entry["fails"] and entry["fails"][0] <= now - WINDOW_SECONDS:
                entry["fails"].popleft()
            if not entry["fails"] and entry["until"] <= now:
                del self.entries[key]

    def _check(self, key, public, now):
        self._prune(now)
        while self.public["fails"] and self.public["fails"][0] <= now - PUBLIC_WINDOW_SECONDS:
            self.public["fails"].popleft()
        if public and self.public["until"] > now:
            wait = math.ceil(self.public["until"] - now)
            raise AuthError("İnternetten çok fazla hatalı giriş denendi; internet girişi %d saniye kapalı. "
                            "Tailscale üzerinden giriş açık." % wait, 429, wait)
        entry = self.entries.get(key)
        if entry is not None and entry["until"] > now:
            wait = math.ceil(entry["until"] - now)
            raise AuthError("Çok fazla hatalı deneme; %d saniye sonra yeniden deneyin." % wait, 429, wait)
        if entry is None and len(self.entries) >= MAX_ENTRIES:
            raise AuthError("Çok fazla deneme; biraz sonra yeniden deneyin.", 429, WINDOW_SECONDS)

    def check(self, key, public=False):
        with self.lock:
            self._check(key, public, self.clock())

    @contextmanager
    def attempt(self, key, public=False):
        """Check the windows, then run one bounded password check for this address."""
        with self.lock:
            self._check(key, public, self.clock())
            if key in self.inflight:
                raise AuthError("Önceki deneme sürüyor; birkaç saniye sonra yeniden deneyin.", 429, 2)
            self.inflight.add(key)
        try:
            if not self.slots.acquire(timeout=HASH_WAIT_SECONDS):
                raise AuthError("Sunucu meşgul; biraz sonra yeniden deneyin.", 429, 5)
            try:
                # Attempts queued behind the slots must not outlive a block that
                # started meanwhile; the budgets are checked again before the work.
                with self.lock:
                    self._check(key, public, self.clock())
                yield
            finally:
                self.slots.release()
        finally:
            with self.lock:
                self.inflight.discard(key)

    def failed(self, key, public=False):
        with self.lock:
            now = self.clock()
            self._prune(now)
            entry = self.entries.setdefault(key, {"fails": deque(), "until": 0})
            entry["fails"].append(now)
            if len(entry["fails"]) >= FAILURES:
                entry["fails"].clear()
                entry["until"] = now + BLOCK_SECONDS
            if public:
                fails = self.public["fails"]
                while fails and fails[0] <= now - PUBLIC_WINDOW_SECONDS:
                    fails.popleft()
                fails.append(now)
                if len(fails) >= PUBLIC_FAILURES:
                    fails.clear()
                    self.public["until"] = now + PUBLIC_BLOCK_SECONDS


def main():
    parser = argparse.ArgumentParser(prog="master-konsol", description="Konsol hesabı (root, DD-194/DD-205)")
    parser.add_argument("--state", default=os.environ.get("STATE_FILE", "/etc/master-stack/state.env"))
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("durum", help="hesap ve açık oturum sayısı")
    sub.add_parser("sifirla", help="hesabı ve oturumları siler; internet adresi kapanır")
    opener = sub.add_parser("oturum-ac", help="kısa ömürlü otomasyon/test oturumu; belirteci yazar")
    opener.add_argument("--sure", type=int, default=600)
    sub.add_parser("oturum-kapat", help="stdin'den okunan otomasyon oturumunu kapatır")
    args = parser.parse_args()
    if os.geteuid() != 0:
        print("HATA: master-konsol root ister (sudo master-konsol ...)", file=sys.stderr)
        sys.exit(1)
    try:
        env = env_read(args.state)
        store = Store(env["KONSOL_AUTH_DIR"])
        if args.action == "durum":
            account = store.account()
            if account is not None:
                print("Konsol hesabı: %s · açık oturum: %d" % (account["kullanici"], len(store.sessions())))
            else:
                print(NO_ACCOUNT)
        elif args.action == "sifirla":
            store.reset()
            print("Konsol hesabı ve tüm oturumlar silindi; internet adresi kapandı.")
            print("Yeni hesap: Tailscale'den http://panel.%s → Ayarlar → Sistem → Konsol hesabı."
                  % env.get("LOCAL_DOMAIN", ""))
        elif args.action == "oturum-ac":
            print(store.automation_session(args.sure))
        else:
            store.logout(sys.stdin.read(128).strip())
    except AuthError as err:
        print("HATA: " + str(err), file=sys.stderr)
        sys.exit(1)
    except (OSError, KeyError) as err:
        print("HATA: Konsol hesap kaydı okunamadı (%s)." % type(err).__name__, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
