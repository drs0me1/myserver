#!/usr/bin/env python3
"""DD-239/DD-241: master-onar — the operator's check-and-repair run (root).

Started from Konsol (Ayarlar → Sistem → Sağlık, as its own unit) or over SSH (`sudo master-onar`).
Nothing here runs on a schedule except the hourly firewall-only check (`--duvar`). Fixed, bounded steps
over what the installer itself set up; it puts the installer's own settings back (its sysctl files,
the Tailscale flags it sets, its units and timers, its file modes) and never writes new configuration,
so it is not a reconcile engine. Some steps only report: their fix is a re-run or the operator's call.

  master-onar              check and repair, report every step
  master-onar --denetle    check only, change nothing
  master-onar --duvar      firewall only (the hourly timer); keeps the last full report

Every step reports ok | onarildi | sorun | hata | atlandi. A full run writes ONARIM_DURUM_FILE (JSON,
atomically, after each step) for Konsol, prints one line per step for a terminal and sends the same
lines to the journal as "master-onar" (Konsol's Günlük reads them with refresh-tailnet-config's).
"""
import argparse
import fcntl
import json
import os
import re
import stat
import subprocess
import sys
import syslog
import time

STATE_FILE = os.environ.get("STATE_FILE", "/etc/master-stack/state.env")
BASE_UNITS = ("caddy.service", "dnsmasq.service", "master-panel.service", "master-files-panel.service",
              "master-sistem-dosya.service", "master-paylasim.service", "tailscale-udp-gro.service")
# DD-241: the installer's timers; each must be enabled and waiting.
TIMERS = ("refresh-tailnet-config.timer", "master-duvar-denetim.timer", "master-settings-guard.timer",
          "master-share-network.timer", "apt-daily.timer", "apt-daily-upgrade.timer")
FIREWALL_UNIT = "master-firewall.service"
UNIT_RE = re.compile(r"^[A-Za-z0-9@._-]+\.service$")
MARK = {"ok": "✓", "onarildi": "↻", "sorun": "!", "hata": "✗", "atlandi": "–", "calisiyor": "…"}
JOURNAL_TAG = "master-onar"
GiB = 1024 ** 3


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


def run(argv, timeout=30, env=None):
    try:
        proc = subprocess.run(argv, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL, env=env)
    except (OSError, subprocess.TimeoutExpired) as err:
        return 127, "", err.__class__.__name__
    return proc.returncode, proc.stdout.decode("utf-8", "replace"), proc.stderr.decode("utf-8", "replace")


def last_line(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return lines[-1][:160] if lines else ""


def journal(line):
    try:
        syslog.openlog(JOURNAL_TAG, 0, syslog.LOG_DAEMON)
        syslog.syslog(syslog.LOG_INFO, line)
    except OSError:
        pass


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
    return rc == 0, last_line(err)


def http_code(argv):
    rc, out, _ = run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "5", *argv], timeout=15)
    code = out.strip()
    return code if code.isdigit() else "000"


def answered(code):
    # Any HTTP answer proves the service is up (the backends refuse the server's own address with 403).
    return code.isdigit() and 200 <= int(code) < 500


def upper_first(text):
    return text[:1].upper() + text[1:]


def human(n):
    return "%.1f GB" % (n / GiB) if n >= GiB else "%d MB" % (n // (1024 * 1024))


class Repair:
    def __init__(self, env, fix, report, source="terminal"):
        self.env, self.fix, self.report, self.source = env, fix, report, source
        self.steps, self.started = [], int(time.time())
        self.sbin = env.get("SBIN_DIR", "/usr/local/sbin")

    # -- report
    def save(self, state):
        if not self.report:
            return
        body = {"durum": state, "kip": "onar" if self.fix else "denetle", "kaynak": self.source, "baslangic": self.started,
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

    def step(self, sid, name, fn, quiet_ok=False):
        entry = {"id": sid, "ad": name, "durum": "calisiyor", "detay": ""}
        self.steps.append(entry)
        self.save("calisiyor")
        try:
            entry["durum"], entry["detay"] = fn()
        except Exception as err:  # one broken step never hides the others
            entry["durum"], entry["detay"] = "hata", "Adım çalışmadı (%s)" % err.__class__.__name__
        line = "%s %s: %s" % (MARK.get(entry["durum"], "?"), name, entry["detay"])
        # A unit's stdout already goes to the journal under the same name: print only for a person.
        if self.source == "terminal" or sys.stdout.isatty():
            print(line, flush=True)
        if not (quiet_ok and entry["durum"] == "ok"):
            journal(line)
        self.save("calisiyor")

    def need(self, what):
        """Check-only runs report instead of fixing; every fix goes through here."""
        return ("sorun", what) if not self.fix else None

    # -- network edge
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
        if self.need(why.capitalize() + "; Onar yeniden kurar"):
            return self.need(why.capitalize() + "; Onar yeniden kurar")
        ok, err = restart(FIREWALL_UNIT, timeout=120)
        if ok and run([tool, "--check"], timeout=60)[0] == 0:
            return "onarildi", why.capitalize() + "; kurallar yeniden kuruldu"
        return "hata", "Kurallar yeniden kurulamadı" + (" (%s)" % err if err else "")

    def forwarding(self):
        """A1: exit-node forwarding and the network buffers come from the installer's sysctl files."""
        def read():
            values = {}
            for key in ("net.ipv4.ip_forward", "net.core.rmem_max"):
                rc, out, _ = run(["sysctl", "-n", key], timeout=10)
                values[key] = out.strip() if rc == 0 else ""
            return values
        floor = int(self.env.get("NET_BUF_FLOOR_BYTES", "0") or 0)
        bad = lambda v: [k for k, ok in (("ip_forward", v["net.ipv4.ip_forward"] == "1"),
                                         ("rmem_max", not floor or (v["net.core.rmem_max"].isdigit() and int(v["net.core.rmem_max"]) >= floor))) if not ok]
        wrong = bad(read())
        if not wrong:
            return "ok", "ip_forward=1, ağ tamponları yerinde"
        if self.need("Ezilmiş: " + ", ".join(wrong) + " (başka bir /etc/sysctl.d dosyası)"):
            return self.need("Ezilmiş: " + ", ".join(wrong) + " (başka bir /etc/sysctl.d dosyası)")
        files = [self.env.get(k, "") for k in ("SYSCTL_FORWARD_FILE", "SYSCTL_NETBUF_FILE", "SYSCTL_TCP_FILE")]
        for path in [f for f in files if f and os.path.isfile(f)]:
            run(["sysctl", "-p", path], timeout=15)
        still = bad(read())
        if not still:
            return "onarildi", "Projenin sysctl dosyaları yeniden uygulandı (%s)" % ", ".join(wrong)
        return "hata", "Hâlâ ezilmiş: %s; başka bir /etc/sysctl.d dosyası sonradan uygulanıyor olabilir" % ", ".join(still)

    def tailscale(self):
        if unit_props(["tailscaled.service"]).get("tailscaled.service", {}).get("ActiveState") != "active":
            if self.need("tailscaled çalışmıyor"):
                return self.need("tailscaled çalışmıyor")
            ok, err = restart("tailscaled.service")
            if not ok:
                return "hata", "tailscaled başlatılamadı" + (" (%s)" % err if err else "")
            run(["tailscale", "wait", "--timeout=60s"], timeout=75)
            fixed = ["tailscaled yeniden başlatıldı"]
        else:
            fixed = []
        rc, out, _ = run(["tailscale", "status", "--json"], timeout=15)
        try:
            ts = json.loads(out) if rc == 0 else {}
        except ValueError:
            ts = {}
        if ts.get("BackendState") != "Running" or (ts.get("Self") or {}).get("Online") is not True:
            return "sorun", "Durum: %s; giriş gerekiyorsa sunucuda: sudo tailscale up" % (ts.get("BackendState") or "okunamadı")
        # A2: the installer's flags: exit node offered, Tailscale SSH on.
        rc, out, _ = run(["tailscale", "debug", "prefs"], timeout=15)
        try:
            prefs = json.loads(out) if rc == 0 else {}
        except ValueError:
            prefs = {}
        notes = []
        if prefs:
            routes = prefs.get("AdvertiseRoutes") or []
            missing = [n for n, ok in (("exit node", "0.0.0.0/0" in routes), ("Tailscale SSH", prefs.get("RunSSH") is True)) if not ok]
            if missing:
                if not self.fix:
                    return "sorun", "Kapalı: " + ", ".join(missing)
                rc, _, err = run(["tailscale", "set", "--advertise-exit-node", "--ssh=true"], timeout=30)
                if rc != 0:
                    return "hata", "Tailscale ayarları geri getirilemedi" + (" (%s)" % last_line(err) if err.strip() else "")
                fixed.append("yeniden açıldı: " + ", ".join(missing))
        else:
            notes.append("ayarlar okunamadı")
        # B: the node key's expiry.
        expiry = (ts.get("Self") or {}).get("KeyExpiry")
        if expiry:
            try:
                left = (time.mktime(time.strptime(expiry[:19], "%Y-%m-%dT%H:%M:%S")) - time.time()) / 86400
                if left < 14:
                    notes.append("anahtar %d gün sonra doluyor" % max(0, int(left)))
            except ValueError:
                pass
        detail = "Çevrimiçi, exit node ve SSH açık" + ("; " + "; ".join(fixed) if fixed else "") + ("; " + "; ".join(notes) if notes else "")
        if fixed:
            return "onarildi", detail
        return ("sorun" if any("doluyor" in n for n in notes) else "ok"), detail

    def address(self):
        iface = self.env.get("TAILSCALE_IF", "tailscale0")
        now = self.iface_ipv4(iface)
        saved = self.env.get("TAILSCALE_IPV4", "")
        if not now:
            return "sorun", "%s üzerinde Tailscale adresi yok" % iface
        if now == saved:
            return "ok", "Kayıtlı adres güncel (%s)" % now
        if self.need("Kayıtlı %s, şimdiki %s; Onar Caddy'yi yeni adrese taşır" % (saved or "yok", now)):
            return self.need("Kayıtlı %s, şimdiki %s; Onar Caddy'yi yeni adrese taşır" % (saved or "yok", now))
        rc, _, err = run([os.path.join(self.sbin, "refresh-tailnet-config")], timeout=180)
        self.env = read_env(STATE_FILE) or self.env
        if rc == 0 and self.env.get("TAILSCALE_IPV4") == now:
            return "onarildi", "Adres %s → %s; Caddy yeniden başlatıldı" % (saved or "yok", now)
        return "hata", "Adres güncellenemedi" + (" (%s)" % last_line(err) if err.strip() else "")

    @staticmethod
    def iface_ipv4(iface):
        rc, out, _ = run(["ip", "-4", "-o", "addr", "show", "dev", iface, "scope", "global"], timeout=10)
        if rc != 0:
            return ""
        for line in out.splitlines():
            fields = line.split()
            if len(fields) > 3:
                return fields[3].split("/")[0]
        return ""

    def wan(self):
        """B: the WAN IPv4 the firewall, shares and WireGuard endpoints were built for."""
        iface, saved = self.env.get("WAN_INTERFACE", ""), self.env.get("WAN_IPV4", "")
        if not iface or not saved:
            return "atlandi", "WAN arayüzü kayıtlı değil"
        now = self.iface_ipv4(iface)
        if now == saved:
            return "ok", "WAN adresi değişmemiş (%s)" % saved
        return "sorun", "Kayıtlı %s, şimdiki %s; kurulumu yeniden çalıştırın (Ana Menü → Güncelle ya da curl satırı)" % (saved, now or "yok")

    # -- units
    def timers(self):
        """A4: the installer's timers are enabled and waiting."""
        props = unit_props(TIMERS)
        off = [t for t in TIMERS if props.get(t, {}).get("LoadState") == "loaded"
               and (props[t].get("UnitFileState") not in ("enabled", "enabled-runtime", "static") or props[t].get("ActiveState") != "active")]
        if not off:
            return "ok", "Zamanlayıcılar etkin"
        if self.need("Kapalı: " + ", ".join(off)):
            return self.need("Kapalı: " + ", ".join(off))
        broken = [t for t in off if run(["systemctl", "enable", "--now", t], timeout=30)[0] != 0]
        if broken:
            return "hata", "Açılamadı: " + ", ".join(broken)
        return "onarildi", "Yeniden açıldı: " + ", ".join(off)

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
        if self.need("Çalışmıyor: " + ", ".join(down)):
            return self.need("Çalışmıyor: " + ", ".join(down))
        fixed, broken = [], []
        for unit in down:
            ok, _ = restart(unit)
            (fixed if ok else broken).append(unit)
        if broken:
            return "hata", "Başlatılamadı: %s%s" % (", ".join(broken), (" · yeniden başlatıldı: " + ", ".join(fixed)) if fixed else "")
        return "onarildi", "Yeniden başlatıldı: " + ", ".join(fixed)

    def ssh(self):
        """A5: SSH is the way in when Konsol is down. Ubuntu may start it through ssh.socket."""
        props = unit_props(["ssh.service", "ssh.socket"])
        svc, sock = props.get("ssh.service", {}), props.get("ssh.socket", {})
        if svc.get("LoadState") != "loaded":
            return "atlandi", "ssh.service kurulu değil"
        if svc.get("ActiveState") == "active" or (sock.get("LoadState") == "loaded" and sock.get("ActiveState") == "active"):
            return "ok", "SSH dinliyor"
        unit = "ssh.socket" if sock.get("LoadState") == "loaded" and sock.get("UnitFileState") in ("enabled", "enabled-runtime") else "ssh.service"
        if self.need("SSH çalışmıyor (%s)" % unit):
            return self.need("SSH çalışmıyor (%s)" % unit)
        ok, err = restart(unit)
        return ("onarildi", "%s yeniden başlatıldı" % unit) if ok else ("hata", "%s başlatılamadı%s" % (unit, " (%s)" % err if err else ""))

    def clock(self):
        """A6: NTP; share expiry and updates depend on the time."""
        ask = lambda: run(["timedatectl", "show", "-p", "NTPSynchronized", "--value"], timeout=10)
        rc, out, _ = ask()
        if rc != 0:
            return "atlandi", "Saat durumu okunamadı"
        if out.strip() == "yes":
            return "ok", "Eşitlenmiş"
        unit = next((u for u, p in unit_props(["systemd-timesyncd.service", "chrony.service"]).items() if p.get("LoadState") == "loaded"), "")
        if not unit:
            return "sorun", "Eşitlenmemiş; saat eşitleme servisi yok"
        if self.need("Eşitlenmemiş (%s)" % unit):
            return self.need("Eşitlenmemiş (%s)" % unit)
        restart(unit)
        time.sleep(3)
        return ("onarildi", "%s yeniden başlatıldı; eşitlendi" % unit) if ask()[1].strip() == "yes" \
            else ("sorun", "%s yeniden başlatıldı; eşitleme sürüyor" % unit)

    # -- names and backends
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
        if self.need("panel.%s yanıtlanmıyor" % domain):
            return self.need("panel.%s yanıtlanmıyor" % domain)
        restart("dnsmasq.service")
        rc, out, _ = ask()
        return ("onarildi", "dnsmasq yeniden başlatıldı; panel.%s yanıtlanıyor" % domain) if rc == 0 and out.strip() \
            else ("hata", "panel.%s yine yanıtlanmıyor" % domain)

    def konsol(self):
        """A7: the backend's own socket first, then the path through Caddy; restart only the broken one."""
        domain, ip, sock = self.env.get("LOCAL_DOMAIN", ""), self.env.get("TAILSCALE_IPV4", ""), self.env.get("PANEL_SOCKET", "")
        if not domain or not ip:
            return "atlandi", "Alan adı ya da Tailscale adresi kayıtlı değil"
        backend = lambda: http_code(["--unix-socket", sock, "-H", "Host: panel." + domain, "http://konsol/api/konsol/oturum"]) if sock else "200"
        caddy = lambda: http_code(["-H", "Host: panel." + domain, "http://%s/" % ip])
        if answered(backend()) and answered(caddy()):
            return "ok", "Konsol ve Caddy yanıt veriyor"
        if self.need("Konsol %s, Caddy %s" % ("yanıt veriyor" if answered(backend()) else "yanıt vermiyor",
                                              "yanıt veriyor" if answered(caddy()) else "yanıt vermiyor")):
            return self.need("Konsol %s, Caddy %s" % ("yanıt veriyor" if answered(backend()) else "yanıt vermiyor",
                                                      "yanıt veriyor" if answered(caddy()) else "yanıt vermiyor"))
        done = []
        for unit, probe in (("master-panel.service", backend), ("caddy.service", caddy)):
            if not answered(probe()):
                restart(unit)
                done.append(unit.split(".")[0])
                for _ in range(10):
                    time.sleep(1)
                    if answered(probe()):
                        break
        if answered(backend()) and answered(caddy()):
            return "onarildi", "Yeniden başlatıldı: %s; Konsol yanıt veriyor" % ", ".join(done)
        return "hata", "Konsol yine yanıt vermiyor (yeniden başlatıldı: %s)" % ", ".join(done)

    def files(self):
        """A8: the Files backend on its loopback port (the unit may run while the port is stuck)."""
        port = self.env.get("FILES_PANEL_PORT", "")
        if not port.isdigit():
            return "atlandi", "Dosyalar portu kayıtlı değil"
        probe = lambda: http_code(["http://127.0.0.1:%s/api/state" % port])
        if answered(probe()):
            return "ok", "Dosyalar arka ucu yanıt veriyor"
        if self.need("Dosyalar arka ucu yanıt vermiyor"):
            return self.need("Dosyalar arka ucu yanıt vermiyor")
        restart("master-files-panel.service")
        for _ in range(10):
            time.sleep(1)
            if answered(probe()):
                return "onarildi", "master-files-panel yeniden başlatıldı; yanıt veriyor"
        return "hata", "Dosyalar arka ucu yine yanıt vermiyor"

    # -- files and disks
    def modes(self):
        """A9: the private records keep their modes (root, no group or world access)."""
        want = [(self.env.get("CONFIG_FILE", ""), 0o600), (STATE_FILE, 0o600), (self.env.get("KONSOL_AUTH_DIR", ""), 0o700),
                (self.env.get("ONARIM_DURUM_FILE", ""), 0o600), (self.env.get("GUNCELLEME_LOG_FILE", ""), 0o600)]
        wrong = []
        for path, mode in want:
            try:
                st = os.lstat(path) if path else None
            except OSError:
                continue
            if st is None or stat.S_ISLNK(st.st_mode):
                continue
            if stat.S_IMODE(st.st_mode) & ~mode or st.st_uid != os.geteuid():
                wrong.append((path, mode))
        if not wrong:
            return "ok", "Kayıt izinleri doğru"
        names = ", ".join(os.path.basename(p) for p, _ in wrong)
        if self.need("İzni geniş: " + names):
            return self.need("İzni geniş: " + names)
        try:
            for path, mode in wrong:
                os.chown(path, os.geteuid(), os.getegid())
                os.chmod(path, mode)
        except OSError as err:
            return "hata", "İzin düzeltilemedi (%s)" % err.__class__.__name__
        return "onarildi", "İzin düzeltildi: " + names

    def disk(self):
        """A10: below the upload reserve, apt's package cache goes and the journal shrinks to 200 MB.
        Konsol's trash and users' files are never touched."""
        def low():
            out, seen = [], set()
            for label, path in (("sistem diski", "/"), ("kullanıcı alanı", self.env.get("SERVER_ROOT", ""))):
                try:
                    st, dev = os.statvfs(path), os.stat(path).st_dev
                except (OSError, TypeError, ValueError):
                    continue
                if dev in seen:
                    continue
                seen.add(dev)
                total, free = st.f_blocks * st.f_frsize, st.f_bavail * st.f_frsize
                if total and free < min(5 * GiB, total // 10):
                    out.append((label, path, free))
                if st.f_files and st.f_favail == 0:
                    out.append((label + " (inode)", path, 0))
            return out
        short = low()
        if not short:
            return "ok", "Yeterli boş alan var"
        text = ", ".join("%s %s boş" % (label, human(free)) for label, _, free in short)
        if self.need("Az: " + text):
            return self.need("Az: " + text)
        before = {path: os.statvfs(path).f_bavail * os.statvfs(path).f_frsize for _, path, _ in short}
        run(["apt-get", "clean"], timeout=120)
        run(["journalctl", "--vacuum-size=200M"], timeout=120)
        gained = sum(max(0, os.statvfs(p).f_bavail * os.statvfs(p).f_frsize - b) for p, b in before.items())
        still = low()
        if not still:
            return "onarildi", "apt önbelleği ve eski günlükler silindi (%s açıldı)" % human(gained)
        return "sorun", "Temizlendi (%s açıldı) ama hâlâ az: %s; dosyaları gözden geçirin" % (
            human(gained), ", ".join("%s %s boş" % (label, human(free)) for label, _, free in still))

    def packages(self):
        """A11: a half-finished package install (dpkg --audit). Fixed with dpkg --configure -a when apt is idle."""
        rc, out, _ = run(["dpkg", "--audit"], timeout=60)
        if rc == 127:
            return "atlandi", "dpkg yok"
        if not out.strip():
            return "ok", "Yarım kalmış paket kurulumu yok"
        if self.need("Yarım kalmış paket kurulumu var"):
            return self.need("Yarım kalmış paket kurulumu var")
        rc, _, err = run(["dpkg", "--configure", "-a"], timeout=900, env=dict(os.environ, DEBIAN_FRONTEND="noninteractive"))
        if rc != 0 and "lock" in err.lower():
            return "sorun", "apt şu anda meşgul (otomatik güncelleme?); biraz sonra yeniden deneyin"
        if rc == 0 and not run(["dpkg", "--audit"], timeout=60)[1].strip():
            return "onarildi", "dpkg --configure -a tamamlandı"
        return "hata", "dpkg --configure -a başarısız" + (" (%s)" % last_line(err) if err.strip() else "")

    # -- report only (B)
    def caddy_config(self):
        path = self.env.get("CADDYFILE", "")
        if not path or not os.path.isfile(path):
            return "atlandi", "Caddyfile yok"
        # Caddy reads its addresses from state.env (EnvironmentFile); validate with the same values.
        rc, out, err = run(["caddy", "validate", "--config", path, "--adapter", "caddyfile"], timeout=60,
                           env=dict(os.environ, **{k: v for k, v in self.env.items() if k.isupper()}))
        if rc == 127:
            return "atlandi", "caddy komutu yok"
        if rc == 0:
            return "ok", "Yapılandırma geçerli"
        return "sorun", "Yapılandırma geçersiz: %s; kurulumu yeniden çalıştırın" % (last_line(err) or last_line(out) or "ayrıntı yok")

    def containers(self):
        rc, _, err = run(["podman", "info", "--format", "{{.Version.Version}}"], timeout=60)
        if rc == 127:
            return "atlandi", "podman kurulu değil"
        if rc != 0:
            return "sorun", "podman çalışmıyor (%s)" % last_line(err)
        table = self.env.get("KONTEYNER_NFT_TABLE", "")
        if table and run(["nft", "list", "table", "inet", table], timeout=15)[0] != 0:
            return "sorun", "Konteyner koruma tablosu (inet %s) yok; Podman sayfasından ya da kurulumla yeniden kurulur" % table
        return "ok", "Podman çalışıyor" + (", konteyner koruması yerinde" if table else "")

    def wireguard(self):
        try:
            with open(self.env.get("MODULES_FILE", "/etc/master-stack/moduller"), encoding="utf-8") as fh:
                running = any(line.rstrip("\n").split("\t") == ["wireguard", "calisiyor"] for line in fh)
        except OSError:
            running = False
        if not running:
            return "atlandi", "WireGuard kurulu değil ya da durdurulmuş"
        rc, out, _ = run(["wg", "show", "all", "latest-handshakes"], timeout=15)
        if rc != 0:
            return "sorun", "wg okunamadı"
        rows = [l.split() for l in out.splitlines() if len(l.split()) == 3]
        never = [r for r in rows if r[2] == "0"]
        return "ok", "%d eş, %d tanesi hiç bağlanmadı" % (len(rows), len(never)) if rows else "Eş yok"

    def system(self):
        notes = []
        try:
            with open("/proc/mounts", encoding="utf-8") as fh:
                for line in fh:
                    f = line.split()
                    if len(f) > 3 and f[1] in ("/", self.env.get("SERVER_ROOT", "")) and "ro" in f[3].split(","):
                        notes.append("%s salt okunur bağlanmış (disk hatası?)" % f[1])
        except OSError:
            pass
        rc, out, _ = run(["journalctl", "-k", "--since", "-24h", "-q", "--no-pager", "-g", "Out of memory|oom-kill"], timeout=30)
        if rc == 0 and out.strip():
            notes.append("son 24 saatte %d bellek yetmezliği (OOM) olayı" % len(out.strip().splitlines()))
        if os.path.exists("/run/reboot-required"):
            notes.append("yeniden başlatma bekleniyor")
        return ("sorun", upper_first("; ".join(notes))) if notes else ("ok", "Dosya sistemi yazılabilir, OOM yok, yeniden başlatma gerekmiyor")

    def halfway(self):
        notes = []
        state = {}
        try:
            with open(self.env.get("GUNCELLEME_DURUM_FILE", ""), encoding="utf-8") as fh:
                state = dict(l.rstrip("\n").split("=", 1) for l in fh if "=" in l)
        except OSError:
            pass
        if state.get("durum") == "calisiyor" and unit_props([self.env.get("GUNCELLEME_UNIT", "master-guncelle.service")]).get(
                self.env.get("GUNCELLEME_UNIT", "master-guncelle.service"), {}).get("ActiveState") != "active":
            notes.append("güncelleme yarıda kalmış (%s); Ana Menü → Güncelle ile yeniden deneyin" % state.get("hedef", "?"))
        pending = self.env.get("SETTINGS_PENDING_FILE", "")
        if pending and os.path.exists(pending):
            notes.append("Ayarlar'da onay ya da geri alma bekleyen bir işlem var")
        return ("sorun", upper_first("; ".join(notes))) if notes else ("ok", "Yarıda kalan işlem yok")

    def others(self):
        rc, out, _ = run(["systemctl", "list-units", "--failed", "--plain", "--no-legend", "--no-pager"], timeout=15)
        if rc != 0:
            return "atlandi", "Başarısız birimler okunamadı"
        failed = [line.split()[0] for line in out.splitlines() if line.split()]
        if not failed:
            return "ok", "Başarısız birim yok"
        return "sorun", "Onarılmadı (proje dışı ya da kendi döngüsü var): " + ", ".join(failed[:12])

    STEPS = (("duvar", "Güvenlik duvarı", "firewall"), ("yonlendirme", "Yönlendirme (exit node)", "forwarding"),
             ("tailscale", "Tailscale", "tailscale"), ("adres", "Tailscale adresi", "address"), ("wan", "WAN adresi", "wan"),
             ("zamanlayicilar", "Zamanlayıcılar", "timers"), ("servisler", "Servisler", "services"), ("ssh", "SSH", "ssh"),
             ("saat", "Saat", "clock"), ("dns", "DNS", "dns"), ("konsol", "Konsol", "konsol"), ("dosyalar", "Dosyalar", "files"),
             ("izinler", "Kayıt izinleri", "modes"), ("disk", "Disk", "disk"), ("paketler", "Paket kurulumu", "packages"),
             ("caddy", "Caddy yapılandırması", "caddy_config"), ("podman", "Podman", "containers"),
             ("wireguard", "WireGuard", "wireguard"), ("sistem", "Sistem", "system"), ("yarim", "Yarıda kalanlar", "halfway"),
             ("diger", "Diğer birimler", "others"))

    def all(self):
        journal("%s başladı (%s)" % ("denetim ve onarım" if self.fix else "denetim", self.source))
        for sid, name, method in self.STEPS:
            self.step(sid, name, getattr(self, method))
        bad = any(s["durum"] == "hata" for s in self.steps) or (not self.fix and any(s["durum"] == "sorun" for s in self.steps))
        counts = {k: sum(1 for s in self.steps if s["durum"] == k) for k in ("onarildi", "sorun", "hata")}
        journal("bitti: %s (onarıldı %d, sorun %d, hata %d)" % ("sorun var" if bad else "tamam", counts["onarildi"], counts["sorun"], counts["hata"]))
        self.save("hata" if bad else "tamam")
        return 1 if bad else 0


def main():
    parser = argparse.ArgumentParser(prog="master-onar", description="Konsol: denetle ve onar (DD-239, DD-241)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--denetle", action="store_true", help="yalnız denetle, hiçbir şeyi değiştirme")
    mode.add_argument("--duvar", action="store_true", help="yalnız güvenlik duvarı (saatlik zamanlayıcı)")
    parser.add_argument("--kaynak", choices=("konsol", "terminal"), default="terminal", help=argparse.SUPPRESS)
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
        # The hourly check writes to the journal only when it finds something.
        repair = Repair(env, True, None, "saatlik")
        repair.step("duvar", "Güvenlik duvarı", repair.firewall, quiet_ok=True)
        return 1 if repair.steps[0]["durum"] == "hata" else 0
    print("master-onar: %s" % ("yalnız denetim" if args.denetle else "denetim ve onarım"), flush=True)
    return Repair(env, not args.denetle, env.get("ONARIM_DURUM_FILE"), args.kaynak).all()


if __name__ == "__main__":
    sys.exit(main())
