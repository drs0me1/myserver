#!/usr/bin/env python3
"""DD-239: master-onar — the operator's check-and-repair run (root).

Started from Konsol (Ayarlar → Sistem → Sağlık, as its own unit) or over SSH (`sudo master-onar`).
It replaces the 5-minute refresh-tailnet-config timer: nothing here runs on a schedule except the
hourly firewall-only check (`--duvar`). Fixed, bounded steps over the project's own units; it never
rewrites configuration (that is the installer's job), so it is not a reconcile engine.

  master-onar              check and repair, report every step
  master-onar --denetle    check only, change nothing
  master-onar --duvar      firewall only (the hourly timer); keeps the last full report

Every step reports ok | onarildi | sorun | hata | atlandi. A full run writes ONARIM_DURUM_FILE
(JSON, atomically, after each step) for Konsol and prints one line per step for a terminal.
"""
import argparse
import fcntl
import json
import os
import re
import subprocess
import sys
import time

STATE_FILE = os.environ.get("STATE_FILE", "/etc/master-stack/state.env")
BASE_UNITS = ("caddy.service", "dnsmasq.service", "master-panel.service", "master-files-panel.service",
              "master-sistem-dosya.service", "master-paylasim.service")
FIREWALL_UNIT = "master-firewall.service"
UNIT_RE = re.compile(r"^[A-Za-z0-9@._-]+\.service$")
MARK = {"ok": "✓", "onarildi": "↻", "sorun": "!", "hata": "✗", "atlandi": "–", "calisiyor": "…"}


def read_env(path):
    env = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                key, sep, value = line.rstrip("\n").partition("=")
                if sep and re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
                    env[key] = value.strip().strip('"')
    except OSError:
        pass
    return env


def run(argv, timeout=30):
    try:
        proc = subprocess.run(argv, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as err:
        return 127, "", err.__class__.__name__
    return proc.returncode, proc.stdout.decode("utf-8", "replace"), proc.stderr.decode("utf-8", "replace")


def unit_props(units):
    rc, out, _ = run(["systemctl", "show", "--no-pager", "--property=Id,LoadState,ActiveState,UnitFileState", *units])
    found = {}
    if rc == 0:
        for block in out.strip().split("\n\n"):
            props = dict(line.split("=", 1) for line in block.splitlines() if "=" in line)
            if props.get("Id"):
                found[props["Id"]] = props
    return found


def restart(unit, timeout=90):
    run(["systemctl", "reset-failed", unit], timeout=15)
    rc, _, err = run(["systemctl", "restart", unit], timeout=timeout)
    return rc == 0, err.strip().splitlines()[-1] if err.strip() else ""


class Repair:
    def __init__(self, env, fix, report):
        self.env, self.fix, self.report = env, fix, report
        self.steps, self.started = [], int(time.time())
        self.sbin = env.get("SBIN_DIR", "/usr/local/sbin")

    # -- report
    def save(self, state):
        if not self.report:
            return
        body = {"durum": state, "kip": "onar" if self.fix else "denetle", "baslangic": self.started,
                "bitis": int(time.time()) if state != "calisiyor" else None, "adimlar": self.steps}
        tmp = "%s.%d" % (self.report, os.getpid())
        try:
            os.makedirs(os.path.dirname(self.report), exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(body, fh, ensure_ascii=False)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.report)
        except OSError as err:
            print("master-onar: rapor yazılamadı (%s)" % err.__class__.__name__, file=sys.stderr)

    def step(self, sid, name, fn):
        entry = {"id": sid, "ad": name, "durum": "calisiyor", "detay": ""}
        self.steps.append(entry)
        self.save("calisiyor")
        try:
            entry["durum"], entry["detay"] = fn()
        except Exception as err:  # one broken step never hides the others
            entry["durum"], entry["detay"] = "hata", "Adım çalışmadı (%s)" % err.__class__.__name__
        print("%s %s: %s" % (MARK.get(entry["durum"], "?"), name, entry["detay"]), flush=True)
        self.save("calisiyor")

    # -- steps
    def firewall(self):
        tool = os.path.join(self.sbin, "master-firewall")
        if not os.access(tool, os.X_OK):
            return "atlandi", "master-firewall kurulu değil"
        for _ in range(15):  # an apply in progress fails --check for a moment
            if unit_props([FIREWALL_UNIT]).get(FIREWALL_UNIT, {}).get("ActiveState") not in ("activating", "deactivating"):
                break
            time.sleep(2)
        failed = unit_props([FIREWALL_UNIT]).get(FIREWALL_UNIT, {}).get("ActiveState") == "failed"
        if not failed and run([tool, "--check"], timeout=60)[0] == 0:
            return "ok", "Kurallar beklenen biçimde"
        why = "birim başarısız" if failed else "kurallar beklenenden farklı"
        if not self.fix:
            return "sorun", why.capitalize() + "; Onar yeniden kurar"
        ok, err = restart(FIREWALL_UNIT, timeout=120)
        if ok and run([tool, "--check"], timeout=60)[0] == 0:
            return "onarildi", why.capitalize() + "; kurallar yeniden kuruldu"
        return "hata", "Kurallar yeniden kurulamadı" + (" (%s)" % err if err else "")

    def tailscale(self):
        if unit_props(["tailscaled.service"]).get("tailscaled.service", {}).get("ActiveState") != "active":
            if not self.fix:
                return "sorun", "tailscaled çalışmıyor"
            ok, err = restart("tailscaled.service")
            if not ok:
                return "hata", "tailscaled başlatılamadı" + (" (%s)" % err if err else "")
            run(["tailscale", "wait", "--timeout=60s"], timeout=75)
            fixed = True
        else:
            fixed = False
        rc, out, _ = run(["tailscale", "status", "--json"], timeout=15)
        try:
            ts = json.loads(out) if rc == 0 else {}
        except ValueError:
            ts = {}
        if ts.get("BackendState") == "Running" and (ts.get("Self") or {}).get("Online") is True:
            return ("onarildi", "tailscaled yeniden başlatıldı; çevrimiçi") if fixed else ("ok", "Çalışıyor, çevrimiçi")
        state = ts.get("BackendState") or "okunamadı"
        return "sorun", "Durum: %s; giriş gerekiyorsa sunucuda: sudo tailscale up" % state

    def address(self):
        iface = self.env.get("TAILSCALE_IF", "tailscale0")
        rc, out, _ = run(["ip", "-4", "-o", "addr", "show", "dev", iface, "scope", "global"], timeout=10)
        now = next((f.split("/")[0] for line in out.splitlines() for i, f in enumerate(line.split()) if i == 3), "") if rc == 0 else ""
        saved = self.env.get("TAILSCALE_IPV4", "")
        if not now:
            return "sorun", "%s üzerinde Tailscale adresi yok" % iface
        if now == saved:
            return "ok", "Kayıtlı adres güncel (%s)" % now
        if not self.fix:
            return "sorun", "Kayıtlı %s, şimdiki %s; Onar Caddy'yi yeni adrese taşır" % (saved or "yok", now)
        rc, _, err = run([os.path.join(self.sbin, "refresh-tailnet-config")], timeout=180)
        self.env = read_env(STATE_FILE) or self.env
        if rc == 0 and self.env.get("TAILSCALE_IPV4") == now:
            return "onarildi", "Adres %s → %s; Caddy yeniden başlatıldı" % (saved or "yok", now)
        return "hata", "Adres güncellenemedi" + (" (%s)" % err.strip().splitlines()[-1] if err.strip() else "")

    def package_units(self):
        """Required units of the installed, running packages (master-modul saglik); a stopped package is left alone."""
        stopped = set()
        try:
            with open(self.env.get("MODULES_FILE", "/etc/master-stack/moduller"), encoding="utf-8") as fh:
                stopped = {f[0] for f in (line.rstrip("\n").split("\t") for line in fh) if len(f) == 2 and f[1] == "durduruldu"}
        except OSError:
            pass
        rc, out, _ = run([os.path.join(self.sbin, "master-modul"), "saglik"], timeout=30)
        units, networks = [], []
        for line in out.splitlines() if rc == 0 else []:
            f = line.split("\t")
            if len(f) == 3 and f[0] not in stopped and UNIT_RE.match(f[1]):
                (networks if f[2] == "ag" else units).append(f[1])
        return units, networks

    def services(self):
        units, networks = self.package_units()
        wanted = list(dict.fromkeys(list(BASE_UNITS) + units + networks))
        props = unit_props(wanted)
        down = []
        for unit in wanted:
            p = props.get(unit, {})
            if p.get("LoadState") != "loaded":
                continue  # not installed here (e.g. no system view)
            if unit in networks and p.get("UnitFileState") not in ("enabled", "enabled-runtime"):
                continue  # Konsol's network switch disabled it on purpose
            if p.get("ActiveState") != "active":
                down.append(unit)
        if not down:
            return "ok", "Gerekli servisler çalışıyor"
        if not self.fix:
            return "sorun", "Çalışmıyor: " + ", ".join(down)
        fixed, broken = [], []
        for unit in down:
            ok, _ = restart(unit)
            (fixed if ok else broken).append(unit)
        if broken:
            return "hata", "Başlatılamadı: %s%s" % (", ".join(broken), (" · yeniden başlatıldı: " + ", ".join(fixed)) if fixed else "")
        return "onarildi", "Yeniden başlatıldı: " + ", ".join(fixed)

    def dns(self):
        domain, ip = self.env.get("LOCAL_DOMAIN", ""), self.env.get("TAILSCALE_IPV4", "")
        if not domain or not ip:
            return "atlandi", "Alan adı ya da Tailscale adresi kayıtlı değil"
        ask = lambda: run(["dig", "+short", "+time=2", "+tries=1", "panel." + domain, "@" + ip], timeout=10)
        rc, out, _ = ask()
        if rc == 127:
            return "atlandi", "dig kurulu değil"
        if rc == 0 and out.strip():
            return "ok", "panel.%s yanıtlanıyor" % domain
        if not self.fix:
            return "sorun", "panel.%s yanıtlanmıyor" % domain
        restart("dnsmasq.service")
        rc, out, _ = ask()
        return ("onarildi", "dnsmasq yeniden başlatıldı; panel.%s yanıtlanıyor" % domain) if rc == 0 and out.strip() \
            else ("hata", "panel.%s yine yanıtlanmıyor" % domain)

    def konsol(self):
        domain, ip = self.env.get("LOCAL_DOMAIN", ""), self.env.get("TAILSCALE_IPV4", "")
        if not domain or not ip:
            return "atlandi", "Alan adı ya da Tailscale adresi kayıtlı değil"
        ask = lambda: run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "5",
                           "-H", "Host: panel." + domain, "http://%s/" % ip], timeout=15)[1].strip()
        code = ask()
        # Any answer from Konsol counts (the backend refuses the server's own address with 403).
        alive = lambda c: c.isdigit() and 200 <= int(c) < 500
        if alive(code):
            return "ok", "Konsol yanıt veriyor (HTTP %s)" % code
        if not self.fix:
            return "sorun", "Konsol yanıt vermiyor (%s)" % (code or "bağlantı yok")
        for unit in ("master-panel.service", "caddy.service"):
            restart(unit)
        for _ in range(10):
            time.sleep(1)
            code = ask()
            if alive(code):
                return "onarildi", "master-panel ve Caddy yeniden başlatıldı; Konsol yanıt veriyor"
        return "hata", "Konsol yine yanıt vermiyor (%s)" % (code or "bağlantı yok")

    def others(self):
        rc, out, _ = run(["systemctl", "list-units", "--failed", "--plain", "--no-legend", "--no-pager"], timeout=15)
        if rc != 0:
            return "atlandi", "Başarısız birimler okunamadı"
        failed = [line.split()[0] for line in out.splitlines() if line.split()]
        if not failed:
            return "ok", "Başarısız birim yok"
        return "sorun", "Onarılmadı (proje dışı ya da kendi döngüsü var): " + ", ".join(failed[:12])

    def all(self):
        self.step("duvar", "Güvenlik duvarı", self.firewall)
        self.step("tailscale", "Tailscale", self.tailscale)
        self.step("adres", "Tailscale adresi", self.address)
        self.step("servisler", "Servisler", self.services)
        self.step("dns", "DNS", self.dns)
        self.step("konsol", "Konsol", self.konsol)
        self.step("diger", "Diğer birimler", self.others)
        bad = any(s["durum"] == "hata" for s in self.steps) or (not self.fix and any(s["durum"] == "sorun" for s in self.steps))
        self.save("hata" if bad else "tamam")
        return 1 if bad else 0


def main():
    parser = argparse.ArgumentParser(prog="master-onar", description="Konsol: denetle ve onar (DD-239)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--denetle", action="store_true", help="yalnız denetle, hiçbir şeyi değiştirme")
    mode.add_argument("--duvar", action="store_true", help="yalnız güvenlik duvarı (saatlik zamanlayıcı)")
    args = parser.parse_args()
    if os.geteuid() != 0:
        print("HATA: root gerekli (sudo master-onar)", file=sys.stderr)
        return 2
    env = read_env(STATE_FILE)
    if not env:
        print("HATA: state.env okunamadı: %s" % STATE_FILE, file=sys.stderr)
        return 2
    lock_dir = env.get("RUNTIME_DIR", "/run/master-stack")
    os.makedirs(lock_dir, exist_ok=True)
    lock = open(os.path.join(lock_dir, "onarim.lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("HATA: başka bir onarım sürüyor", file=sys.stderr)
        return 3
    if args.duvar:
        repair = Repair(env, True, None)
        repair.step("duvar", "Güvenlik duvarı", repair.firewall)
        return 1 if repair.steps[0]["durum"] == "hata" else 0
    print("master-onar: %s" % ("yalnız denetim" if args.denetle else "denetim ve onarım"), flush=True)
    return Repair(env, not args.denetle, env.get("ONARIM_DURUM_FILE")).all()


if __name__ == "__main__":
    sys.exit(main())
