"""WireGuard package: Konsol API module (DD-200).

The root backend loads this file only while the package is registered and hands every
/api/uygulama/wireguard/* request to Api.handle(). Nothing here opens a port or touches
the host directly: every change goes through the package's tool master-wg (same
validation, same lock, same live apply), run through the backend's ctx.run().

Contract with the backend (ctx):
  ctx.env()                     state.env as a dict
  ctx.read_env(path)            another KEY=value file as a dict (the package's wireguard.env)
  ctx.tool(name)                path of a package tool beside master-modul
  ctx.run(argv, binary, timeout)  (rc, out, message) with the backend's environment
  ctx.ports(env)                port catalogue rows (reserved UDP ports for new networks)
  ctx.error(code, message)      exception to raise for an HTTP error answer
  ctx.settings_changed()        drop the Settings cache after a change
  ctx.log(message)              one journal line
  req.method/path/query/data/user, req.audit(verb, detail, ok)
Replies are (code, dict) for JSON or (code, bytes, content_type, headers) for a download.
"""
import hashlib
import ipaddress
import os
import re
import threading
import time
import urllib.parse

IFACE_RE = re.compile(r"^wg[0-9]$")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")
# DD-137: "Bağlı" = son ACTIVE_WINDOW saniyede cihazdan veri geldi (istemci 21 sn'de bir
# canlı tutma paketi yollar). Sayaçlar SAMPLE_SECONDS'ta bir, sayfa açık olmasa da okunur.
ACTIVE_WINDOW = float(os.environ.get("PANEL_ACTIVE_WINDOW", "45"))
SAMPLE_SECONDS = float(os.environ.get("PANEL_SAMPLE_SECONDS", "10"))
HANDSHAKE_FRESH = 180
MASK = "•" * 44
APP_NAME = "WireGuard"


def num_or(value, default):
    return int(value) if value is not None and str(value).strip().isdigit() else default


def dns_provider(dns):
    tokens = [t.strip() for t in dns.split(",") if t.strip()]
    known = (
        # Aile sürümü Cloudflare'in önekiyle de eşleşir; önce o denenir.
        ("Cloudflare Aile", ("1.1.1.3", "1.0.0.3", "2606:4700:4700::1113", "2606:4700:4700::1003")),
        ("Cloudflare", ("1.1.1.", "1.0.0.", "2606:4700:4700::")),
        ("AdGuard", ("94.140.14.", "94.140.15.", "2a10:50c0::ad")),
        ("Google", ("8.8.8.", "8.8.4.", "2001:4860:4860::")),
        ("Quad9", ("9.9.9.", "149.112.112.", "2620:fe::")),
        ("NextDNS", ("45.90.28.", "45.90.30.", "2a07:a8c0:", "2a07:a8c1:")),
    )
    for name, prefixes in known:
        if tokens and all(t.startswith(prefixes) for t in tokens):
            return name
    return "Özel"


def mask_profile(text):
    out = []
    for line in text.splitlines():
        key, sep, _ = line.partition(" = ")
        out.append("%s = %s" % (key, MASK) if sep and key in ("PrivateKey", "PresharedKey") else line)
    return "\n".join(out) + "\n"


def create(ctx):
    return Api(ctx)


class Api:
    APP_NAME = APP_NAME  # Ayarlar'ın VPN sekmesi bu adı taşır (DD-200)

    def __init__(self, ctx):
        self.ctx = ctx
        self.activity = {}
        self.activity_lock = threading.Lock()
        self.stopped = threading.Event()

    # -- lifecycle: the backend calls start() once after loading and stop() when the
    #    package is removed (or its file changed); the sampler watches peer counters.
    def start(self):
        threading.Thread(target=self.sample_forever, name="wireguard-sampler", daemon=True).start()

    def stop(self):
        self.stopped.set()

    def sample_forever(self):
        while not self.stopped.is_set():
            try:
                self.state()
            except Exception as err:  # örnekleme durursa sayfa yine el sıkışmaya düşer
                self.ctx.log("sayaç okunamadı (%s)" % err)
            self.stopped.wait(SAMPLE_SECONDS)

    # -- master-wg
    def run(self, *argv, binary=False, net=None):
        cmd = [self.ctx.tool("master-wg")] + (["--if", net] if net else []) + list(argv)
        return self.ctx.run(cmd, binary=binary, timeout=120)

    def net_rows(self):
        """master-wg nets satırları (peer listesi olmadan); state ve Ayarlar aynı kaynağı okur."""
        rc, out, message = self.run("nets")
        if rc != 0:
            raise RuntimeError(message or "ağ listesi okunamadı")
        rows = []
        for line in out.splitlines():
            f = line.split("\t")
            if len(f) != 11 or not IFACE_RE.match(f[0]):
                continue
            rows.append({
                "iface": f[0], "port": num_or(f[1], 0),
                "server4": f[3], "subnet4": f[4], "server6": f[5], "subnet6": f[6],
                "dns": f[7], "label": f[8], "active": f[9] == "1", "count": num_or(f[10], 0),
                "revision": hashlib.sha256("\t".join(f[:9]).encode("utf-8")).hexdigest(),
            })
        return rows

    def networks(self):
        """DD-200: Ayarlar'ın güvenlik duvarı ve port görünümleri için ağlar (anahtar yok)."""
        try:
            rows = self.net_rows()
        except RuntimeError:
            return []
        return [{"app": APP_NAME, "iface": n["iface"], "port": n["port"], "label": n["label"], "active": n["active"],
                 "server4": n["server4"], "subnet4": n["subnet4"], "server6": n["server6"], "subnet6": n["subnet6"]}
                for n in rows]

    def peers(self, net, seen=None):
        rc, out, message = self.run("info", net=net)
        if rc != 0:
            raise RuntimeError(message or "%s peer listesi okunamadı" % net)
        peers = []
        now = time.time()
        for line in out.splitlines():
            f = line.split("\t")
            if len(f) != 11:
                continue
            peer = {
                "name": f[0], "ipv4": f[1], "ipv6": f[2], "handshake": num_or(f[3], 0),
                "rx": num_or(f[4], 0), "tx": num_or(f[5], 0), "profile": f[6] == "var",
                "dns": f[7], "provider": dns_provider(f[7]) if f[7] else "",
                "keepalive": num_or(f[8], 0), "mtu": num_or(f[9], 0), "enabled": f[10] != "0",
            }
            peer["online"], peer["active_at"] = self.observe(net, peer, now, seen)
            peer["online"] = peer["online"] and peer["enabled"]
            peers.append(peer)
        return peers

    def observe(self, net, peer, now, seen):
        """DD-137: cihazdan gelen bayt (rx) son ACTIVE_WINDOW saniyede arttıysa bağlı.

        WireGuard'da "bağlantı" yoktur; el sıkışma yalnız 2 dakikada bir yenilenir, bu
        yüzden kapanan cihaz yalnız ona bakılınca 3 dakika bağlı görünürdü. Yeterince
        izlenmemiş (servis yeni başlamış) bir peer için taze el sıkışmaya bakılır.
        """
        key = (net, peer["name"], peer["ipv4"])
        if seen is not None:
            seen.add(key)
        fresh = peer["handshake"] > 0 and now - peer["handshake"] < HANDSHAKE_FRESH
        with self.activity_lock:
            rec = self.activity.get(key)
            if rec is None or peer["rx"] < rec[0]:
                rec = [peer["rx"], None, now]
                self.activity[key] = rec
            elif peer["rx"] > rec[0]:
                rec[0], rec[1] = peer["rx"], now
            if rec[1] is not None:
                online = now - rec[1] <= ACTIVE_WINDOW
            elif now - rec[2] >= ACTIVE_WINDOW:
                online = False
            else:
                online = fresh
            return online and fresh, (int(rec[1]) if rec[1] is not None else None)

    def package_env(self, env):
        """DD-201: the package's own settings (wireguard.env in its rendered folder); the base state
        carries none of them."""
        base = env.get("MODULES_DIR", "")
        return self.ctx.read_env(os.path.join(base, "wireguard", "wireguard.env")) if base else {}

    def state(self):
        """DD-136: bütün ağlar (wg0 + panelde eklenenler), her biri kendi peer'larıyla."""
        env = self.ctx.env()
        wg = self.package_env(env)
        networks = self.net_rows()
        seen = set()
        for net in networks:
            net["peers"] = self.peers(net["iface"], seen)
        with self.activity_lock:
            for key in [k for k in self.activity if k not in seen]:
                del self.activity[key]
        # Yeni ağa önerilmeyecek portlar: temelin ve kayıtlı paketlerin port kataloğu.
        reserved = {p["port"] for p in self.ctx.ports(env) if p.get("port")}
        return {
            "endpoint": env.get("WAN_IPV4", ""),
            "max": num_or(wg.get("WG_NETWORKS_MAX"), 9) + 1,
            "reserved": sorted(reserved | {num_or(env.get("DNS_PORT"), 53), num_or(env.get("CADDY_HTTP_PORT"), 80)}),
            "defaults": {
                "dns": wg.get("WG_CLIENT_DNS_DEFAULT", ""),
                "keepalive": num_or(wg.get("WG_CLIENT_KEEPALIVE_DEFAULT"), 21),
                "mtu": num_or(wg.get("WG_MTU"), 1420),
                # DD-143: ilk ağa önerilen UDP portu; sonrakiler 61020'den sıralanır.
                "port": num_or(wg.get("WG_PORT_DEFAULT"), 61001),
            },
            "now": int(time.time()),
            "active_window": int(ACTIVE_WINDOW),
            "networks": networks,
        }

    # -- HTTP
    def net_and_name(self, raw_net, raw_name=None):
        net = urllib.parse.unquote(raw_net)
        if not IFACE_RE.match(net):
            raise self.ctx.error(400, "geçersiz arayüz")
        if raw_name is None:
            return net, None
        name = urllib.parse.unquote(raw_name)
        if not NAME_RE.match(name):
            raise self.ctx.error(400, "geçersiz peer adı")
        return net, name

    def confirmed(self, data):
        if str(data.get("confirm", "")).strip().lower() != self.ctx.confirm_word:
            raise self.ctx.error(400, "onay için %s yazın" % self.ctx.confirm_word)

    def handle(self, req):
        if req.method == "GET":
            return self.get(req)
        if req.method == "POST":
            return self.post(req)
        raise self.ctx.error(405, "yöntem desteklenmiyor")

    def get(self, req):
        if req.path == "/state":
            try:
                return 200, self.state()
            except RuntimeError as err:
                raise self.ctx.error(502, str(err))
        m = re.match(r"^/nets/([^/]+)/peers/([^/]+)/(profile|qr\.png)$", req.path)
        if m:
            net, name = self.net_and_name(m.group(1), m.group(2))
            if m.group(3) == "qr.png":
                rc, out, message = self.run("png", name, binary=True, net=net)
                req.audit("qr", "%s/%s" % (net, name), rc == 0)
                if rc != 0 or not out.startswith(b"\x89PNG"):
                    raise self.ctx.error(404, message or "QR üretilemedi")
                return 200, out, "image/png", {"Content-Disposition": 'attachment; filename="%s.png"' % name}
            rc, out, message = self.run("profile", name, net=net)
            if rc != 0:
                raise self.ctx.error(404, message or "profil yok")
            if req.query.get("masked") == ["1"]:
                return 200, mask_profile(out).encode("utf-8"), "text/plain; charset=utf-8", {}
            req.audit("profil", "%s/%s" % (net, name), True)
            return (200, out.encode("utf-8"), "text/plain; charset=utf-8",
                    {"Content-Disposition": 'attachment; filename="%s.conf"' % name})
        raise self.ctx.error(404, "bulunamadı")

    def post(self, req):
        data = req.data
        if req.path == "/nets":
            port = str(data.get("port", "")).strip()
            dns = str(data.get("dns", "")).strip()
            label = str(data.get("label", "")).strip()
            if "scope" in data or not port.isdigit() or not dns:
                raise self.ctx.error(400, "Port ve DNS gerekli; erişim seçeneği desteklenmiyor. Sayfayı yenileyin.")
            rc, out, message = self.run("net-add", port, dns, label)
            parts = out.strip().split("\t")
            req.audit("ag-ekle", parts[0] if rc == 0 else port, rc == 0)
            if rc != 0:
                raise self.ctx.error(400, message or "ağ eklenemedi")
            return 201, {"iface": parts[0], "port": num_or(parts[-1], 0)}
        m = re.match(r"^/nets/([^/]+)/(remove|reset|peers|durum|ayarlar)$", req.path)
        if m:
            net, _ = self.net_and_name(m.group(1))
            if m.group(2) == "ayarlar":
                return self.net_settings(req, net, data)
            if m.group(2) == "remove":
                self.confirmed(data)
                rc, out, message = self.run("net-remove", net, "--onay")
                req.audit("ag-kaldir", net, rc == 0)
                if rc != 0:
                    raise self.ctx.error(400, message or "ağ kaldırılamadı")
                self.ctx.settings_changed()
                return 200, {"iface": net, "peers": num_or(out.strip().split("\t")[-1], 0)}
            if m.group(2) == "durum":
                want = "ac" if data.get("on") else "kapat"
                rc, out, message = self.run("net", want, net=net)
                # Günlük satırı Konsol'da şablonla okunur: ayrıntı doğrudan cümleye girer.
                req.audit("ag-durum", "%s %s" % (net, "açıldı" if want == "ac" else "kapatıldı"), rc == 0)
                if rc != 0:
                    raise self.ctx.error(400, message or "ağ durumu değiştirilemedi")
                self.ctx.settings_changed()
                return 200, {"iface": net, "active": out.strip().split("\t")[-1] == "1"}
            if m.group(2) == "reset":
                self.confirmed(data)
                rc, out, message = self.run("reset", "--onay", net=net)
                req.audit("yeniden-uret", net, rc == 0)
                if rc != 0:
                    raise self.ctx.error(400, message or "%s yeniden üretilemedi" % net)
                parts = out.strip().split("\t")
                return 200, {"peers": num_or(parts[0], 0), "profiles": num_or(parts[-1], 0)}
            name = str(data.get("name", ""))
            if not NAME_RE.match(name):
                raise self.ctx.error(400, "geçersiz peer adı (harf, rakam, . _ -; en çok 32)")
            dns = str(data.get("dns", "")).strip()
            keepalive = str(data.get("keepalive", "")).strip()
            mtu = str(data.get("mtu", "")).strip()
            if not dns or not keepalive.isdigit() or not mtu.isdigit():
                raise self.ctx.error(400, "DNS, keepalive ve MTU gerekli")
            rc, out, message = self.run("add", name, dns, keepalive, mtu, net=net)
            req.audit("ekle", "%s/%s" % (net, name), rc == 0)
            if rc != 0:
                raise self.ctx.error(400, message or "peer eklenemedi")
            return 201, {"name": name, "ipv4": out.strip().split("\t")[-1]}
        m = re.match(r"^/nets/([^/]+)/peers/([^/]+)/(remove|dns|keepalive|durum)$", req.path)
        if m:
            net, name = self.net_and_name(m.group(1), m.group(2))
            if m.group(3) == "remove":
                rc, _, message = self.run("remove", name, net=net)
                req.audit("cikar", "%s/%s" % (net, name), rc == 0)
            elif m.group(3) == "durum":
                want = "ac" if data.get("on") else "kapat"
                rc, _, message = self.run("peer", name, want, net=net)
                req.audit("peer-durum", "%s/%s %s" % (net, name, "açıldı" if want == "ac" else "kapatıldı"), rc == 0)
            elif m.group(3) == "keepalive":
                keepalive = str(data.get("keepalive", "")).strip()
                if not keepalive.isdigit():
                    raise self.ctx.error(400, "keepalive saniye olarak gerekli (0 = kapalı)")
                rc, _, message = self.run("keepalive", name, keepalive, net=net)
                req.audit("keepalive", "%s/%s %s" % (net, name, keepalive), rc == 0)
            else:
                dns = str(data.get("dns", "")).strip()
                if not dns:
                    raise self.ctx.error(400, "DNS gerekli")
                rc, _, message = self.run("dns", name, dns, net=net)
                req.audit("dns", "%s/%s" % (net, name), rc == 0)
            if rc != 0:
                raise self.ctx.error(400, message or "işlem yapılamadı")
            return 200, {"ok": True}
        raise self.ctx.error(404, "bulunamadı")

    def net_settings(self, req, net, data):
        dns, revision = (data.get(k) for k in ("dns", "revision"))
        if ("scope" in data or not isinstance(dns, str) or not dns.strip()
                or len(dns) > 512 or any(ord(c) < 32 for c in dns)
                or not isinstance(revision, str) or not re.fullmatch(r"[a-f0-9]{64}", revision)):
            raise self.ctx.error(400, "Geçerli DNS ve ağ revizyonu gerekli; erişim seçeneği desteklenmiyor.")
        try:
            addresses = [s.strip() for s in dns.split(",")]
            if not 1 <= len(addresses) <= 8 or any("%" in s for s in addresses):
                raise ValueError("DNS")
            for address in addresses:
                ipaddress.ip_address(address)
        except ValueError:
            raise self.ctx.error(400, "DNS için en fazla 8 geçerli IPv4/IPv6 adresi yazın")
        rc, _, message = self.run("net-settings", dns, revision, net=net)
        self.ctx.settings_changed()
        req.audit("ag-ayarlar", net, rc == 0)
        if rc != 0:
            raise self.ctx.error(409, message or "Ağ ayarları kaydedilemedi")
        return 200, {"iface": net, "dns": ", ".join(addresses)}
