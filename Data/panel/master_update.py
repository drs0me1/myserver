"""DD-233: Konsol's "Güncelle" button. Reads the newest installer version on GitHub (the commit at the
tip of GUNCELLEME_DAL and the V2_VERSION in that commit's Data/install.sh), compares it with the
installed one, and starts master-guncelle as its own systemd unit, so the run survives the Konsol
restarts the installer makes. The unit's result file and output are under LOG_DIR; this module only
reads them. Nothing here runs installer code itself."""
import os
import re
import threading
import time
import urllib.error
import urllib.request

VERSION_RE = re.compile(r"^[0-9]{4}\.[0-9]{2}\.[0-9]{2}-v2-([0-9]{1,6})$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REPO_RE = re.compile(r"^[A-Za-z0-9-]{1,39}/[A-Za-z0-9._-]{1,100}$")
BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]{1,100}$")
INSTALL_LINE_RE = re.compile(r'^V2_VERSION="([^"\n]{1,64})"$', re.M)
STAGE_RE = re.compile(r"Aşama ([0-9])/([0-9]) — ([^\n]{1,80})")
CHECK_SECONDS = 6 * 3600       # a fresh answer is reused for six hours
FAIL_SECONDS = 15 * 60         # an unreachable GitHub is asked again after a quarter hour
FORCE_GAP_SECONDS = 60         # "Denetle" asks GitHub at most once a minute
FETCH_TIMEOUT = 10
FETCH_LIMIT = 256 * 1024
LOG_TAIL = 16384
API_URL = "https://api.github.com/repos/%s/commits/%s"
RAW_URL = "https://raw.githubusercontent.com/%s/%s/Data/install.sh"


class UpdateError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def number(version):
    """The build number of an installer version (v2-<n>); None for anything else."""
    m = VERSION_RE.match(version or "")
    return int(m.group(1)) if m else None


def fetch(url, accept):
    req = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": "master-stack-konsol"})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:  # noqa: S310 (fixed https URLs)
        return resp.read(FETCH_LIMIT + 1)[:FETCH_LIMIT].decode("utf-8", "replace")


def read_kv(path):
    """The unit's result file (key=value lines). Missing or unreadable → {}."""
    out = {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh.read(8192).splitlines():
                key, sep, value = line.partition("=")
                if sep and re.fullmatch(r"[a-z]{2,12}", key):
                    out[key] = value[:300]
    except OSError:
        pass
    return out


def tail(path, size=LOG_TAIL):
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - size))
            return fh.read().decode("utf-8", "replace")
    except OSError:
        return ""


class Updates:
    def __init__(self, fetcher=fetch, clock=time.time):
        self.fetcher = fetcher
        self.clock = clock
        self.lock = threading.Lock()
        self.cache = None      # {"at", "ok", "son", "commit", "hata"}
        self.forced_at = -FORCE_GAP_SECONDS

    # -- GitHub
    def latest(self, env, force=False):
        repo, branch = env.get("GUNCELLEME_REPO", ""), env.get("GUNCELLEME_DAL", "")
        if not REPO_RE.match(repo) or not BRANCH_RE.match(branch) or ".." in branch:
            return {"at": 0, "ok": False, "son": None, "commit": None, "hata": "Güncelleme deposu tanımlı değil; kurulumu terminalden yeniden çalıştırın."}
        with self.lock:
            now = self.clock()
            cached = self.cache
            if force and now - self.forced_at >= FORCE_GAP_SECONDS:
                self.forced_at = now
                cached = None
            if cached and cached.get("kaynak") == (repo, branch) and now - cached["at"] < (CHECK_SECONDS if cached["ok"] else FAIL_SECONDS):
                return cached
            result = {"at": now, "kaynak": (repo, branch), "ok": False, "son": None, "commit": None, "hata": ""}
            try:
                sha = self.fetcher(API_URL % (repo, branch), "application/vnd.github.sha").strip()
                if not SHA_RE.match(sha):
                    raise ValueError("commit")
                found = INSTALL_LINE_RE.search(self.fetcher(RAW_URL % (repo, sha), "text/plain"))
                if not found or number(found.group(1)) is None:
                    raise ValueError("sürüm")
                result.update(ok=True, son=found.group(1), commit=sha)
            except (OSError, urllib.error.URLError, ValueError, UnicodeError):
                result["hata"] = "GitHub'a ulaşılamadı ya da sürüm okunamadı; daha sonra yeniden denenir."
            self.cache = result
            return result

    # -- the unit
    @staticmethod
    def job(env, running):
        state = read_kv(env.get("GUNCELLEME_DURUM_FILE", ""))
        status = state.get("durum", "")
        if status not in ("calisiyor", "tamam", "hata"):
            status = ""
        if status == "calisiyor" and not running:
            # The unit is gone without a result (a reboot or a killed run).
            status, state["mesaj"] = "hata", state.get("mesaj") or "Güncelleme yarıda kaldı; sonucu yazılmadı."
        if running:
            status = "calisiyor"
        job = {"durum": status or "yok", "hedef": state.get("hedef", ""), "mesaj": state.get("mesaj", "") if status == "hata" else "",
               "bitis": int(state["bitis"]) if state.get("bitis", "").isdigit() else None, "asama": ""}
        if status == "calisiyor":
            stages = STAGE_RE.findall(tail(env.get("GUNCELLEME_LOG_FILE", "")))
            job["asama"] = "Aşama %s/%s — %s" % stages[-1] if stages else "İndiriliyor"
        return job

    def status(self, env, running, force=False):
        info = self.latest(env, force)
        installed = env.get("V2_VERSION", "")
        mine, theirs = number(installed), number(info["son"])
        return {"kurulu": installed, "son": info["son"], "commit": info["commit"],
                "yeni": bool(info["ok"] and mine is not None and theirs is not None and theirs > mine),
                "denetlendi": int(info["at"]) or None, "hata": info["hata"], "is": self.job(env, running)}

    def check_start(self, env, data, running, blocked):
        """Validates a start request against the shown offer; returns (commit, version)."""
        if running:
            raise UpdateError(409, "Güncelleme zaten sürüyor.")
        if blocked:
            raise UpdateError(409, blocked)
        info = self.status(env, running)
        if not info["yeni"]:
            raise UpdateError(409, "Kurulu sürüm güncel; yeni bir sürüm yok.")
        if data.get("surum") != info["son"] or data.get("commit") != info["commit"]:
            raise UpdateError(409, "GitHub'daki sürüm değişti; sayfayı yenileyip yeniden deneyin.")
        return info["commit"], info["son"]
