/* Konsol (DD-140, DD-200, DD-202, DD-204): root ve dosya arka uçlarının tek arayüzü; hiçbir
   uygulamayı tanımaz. App Store metinleri ve uygulama sayfaları paketlerden gelir
   (konsol.json, /uygulama/<id>/sayfa.js); bu dosya yalnız API'yi çağırır ve sayfalara küçük
   bir arayüz (window.Konsol) verir. Sayfa CSP altında çalışır: satır içi biçem ve betik yok. */
(() => {
  "use strict";
  const ICON = {
    gauge: '<path d="M2.8 12.6a6.4 6.4 0 1 1 12.4 0"/><path d="M9 11.2l3-3.6"/><circle cx="9" cy="11.6" r="1.1"/>',
    shield: '<path d="M9 2.2l5.6 2v4.4c0 3.4-2.4 5.9-5.6 7.2-3.2-1.3-5.6-3.8-5.6-7.2V4.2z"/>',
    folder: '<path d="M2.2 5.2c0-.9.7-1.6 1.6-1.6h3.1l1.7 1.9h5.6c.9 0 1.6.7 1.6 1.6v6.1c0 .9-.7 1.6-1.6 1.6H3.8c-.9 0-1.6-.7-1.6-1.6z"/>',
    stack: '<rect x="2.6" y="2.8" width="12.8" height="4.4" rx="1.2"/><rect x="2.6" y="10.8" width="12.8" height="4.4" rx="1.2"/><path d="M5.2 5h.1M5.2 13h.1"/>',
    grid: '<rect x="2.8" y="2.8" width="5.2" height="5.2" rx="1.2"/><rect x="10" y="2.8" width="5.2" height="5.2" rx="1.2"/><rect x="2.8" y="10" width="5.2" height="5.2" rx="1.2"/><rect x="10" y="10" width="5.2" height="5.2" rx="1.2"/>',
    list: '<path d="M6.6 4.6h8.4M6.6 9h8.4M6.6 13.4h8.4"/><circle cx="3.3" cy="4.6" r=".95" fill="currentColor" stroke="none"/><circle cx="3.3" cy="9" r=".95" fill="currentColor" stroke="none"/><circle cx="3.3" cy="13.4" r=".95" fill="currentColor" stroke="none"/>',
    download: '<path d="M9 2.8v8.4M5.6 7.9L9 11.3l3.4-3.4M3.2 14.6h11.6"/>',
    disk: '<ellipse cx="9" cy="4.6" rx="6" ry="2.2"/><path d="M3 4.6v8.8c0 1.2 2.7 2.2 6 2.2s6-1 6-2.2V4.6M3 9c0 1.2 2.7 2.2 6 2.2S15 10.2 15 9"/>',
    server: '<rect x="2.6" y="2.6" width="12.8" height="12.8" rx="2"/><path d="M5.6 6.2h6.8M5.6 9h6.8M5.6 11.8h3.6"/>',
    plus: '<path d="M9 3.5v11M3.5 9h11"/>',
    trash: '<path d="M3.2 5h11.6M7.2 5V3.4h3.6V5M4.6 5l.8 9.6h7.2l.8-9.6"/><path d="M7.6 8v4M10.4 8v4"/>',
    info: '<circle cx="9" cy="9" r="6.8"/><path d="M9 8.2v4.2M9 5.6v.1"/>',
    video: '<rect x="2.2" y="3.6" width="13.6" height="10.8" rx="1.8"/><path d="M7.4 6.7v4.6l3.9-2.3z"/>',
    text: '<path d="M4.6 2.4h5.8l3 3v10.2H4.6z"/><path d="M10.2 2.4v3.2h3.2M6.8 9h4.4M6.8 11.6h4.4"/>',
    file: '<path d="M4.6 2.4h5.8l3 3v10.2H4.6z"/><path d="M10.2 2.4v3.2h3.2"/>',
    qr: '<rect x="2.6" y="2.6" width="5" height="5" rx=".8"/><rect x="10.4" y="2.6" width="5" height="5" rx=".8"/><rect x="2.6" y="10.4" width="5" height="5" rx=".8"/><path d="M10.4 10.4h2v2M15.4 10.4v5h-5"/>',
    more: '<circle cx="4.2" cy="9" r="1" fill="currentColor" stroke="none"/><circle cx="9" cy="9" r="1" fill="currentColor" stroke="none"/><circle cx="13.8" cy="9" r="1" fill="currentColor" stroke="none"/>',
    lock: '<rect x="3.6" y="8" width="10.8" height="7.4" rx="1.6"/><path d="M6 8V5.8a3 3 0 0 1 6 0V8"/>',
    move: '<path d="M2.2 5.2c0-.9.7-1.6 1.6-1.6h3.1l1.7 1.9h5.6c.9 0 1.6.7 1.6 1.6v6.1c0 .9-.7 1.6-1.6 1.6H3.8c-.9 0-1.6-.7-1.6-1.6z"/><path d="M6.4 10.1h4.8M9.4 8.2l1.9 1.9-1.9 1.9"/>',
    refresh: '<path d="M14.4 9a5.4 5.4 0 1 1-1.6-3.9"/><path d="M14.6 2.6v3.2h-3.2"/>',
    back: '<path d="M11 4.5L6.5 9l4.5 4.5"/>',
    copy: '<rect x="6.2" y="6.2" width="8.8" height="8.8" rx="1.6"/><path d="M11.8 6.2V4.6c0-.9-.7-1.6-1.6-1.6H4.6C3.7 3 3 3.7 3 4.6v5.6c0 .9.7 1.6 1.6 1.6h1.6"/>',
    check: '<path d="M3.8 9.4l3.2 3.2 7.2-7.4"/>',
    globe: '<circle cx="9" cy="9" r="6.6"/><path d="M2.4 9h13.2M9 2.4c1.8 1.9 2.7 4.1 2.7 6.6S10.8 13.7 9 15.6C7.2 13.7 6.3 11.5 6.3 9S7.2 4.3 9 2.4z"/>',
    pencil: '<path d="M11.8 3.2l3 3-8.4 8.4H3.4v-3z"/><path d="M10.2 4.8l3 3"/>',
    up: '<path d="M9 14.4V3.8M4.8 8L9 3.8 13.2 8"/>',
    home: '<path d="M2.8 8.6L9 3.2l6.2 5.4"/><path d="M4.6 7.2v7.4h8.8V7.2"/>',
    clock: '<circle cx="9" cy="9" r="6.6"/><path d="M9 5.4V9l2.4 1.6"/>',
    restore: '<path d="M3.6 8.8a5.4 5.4 0 1 0 1.6-3.9"/><path d="M3.4 2.6v3.2h3.2"/>',
    share: '<circle cx="4.8" cy="9" r="2"/><circle cx="13.2" cy="4.6" r="2"/><circle cx="13.2" cy="13.4" r="2"/><path d="M6.6 8.1l4.8-2.6M6.6 9.9l4.8 2.6"/>',
    eye: '<path d="M1.8 9S4.4 4.2 9 4.2 16.2 9 16.2 9 13.6 13.8 9 13.8 1.8 9 1.8 9z"/><circle cx="9" cy="9" r="2.2"/>',
    upload: '<path d="M9 11.6V3.2M5.6 6.6L9 3.2l3.4 3.4M3.2 14.6h11.6"/>',
    box: '<path d="M2.8 5.4L9 2.4l6.2 3v7.2L9 15.6l-6.2-3z"/><path d="M2.8 5.4L9 8.4l6.2-3M9 8.4v7.2"/>',
    boxOpen: '<path d="M9 6L3 3 1 6l6 3 2-3 6-3 2 3-6 3-2-3M3 7v6l6 3 6-3V7M9 10v6"/>',
    play: '<path d="M5.6 3.6v10.8L14.2 9z"/>',
    pause: '<path d="M6 3.8v10.4M12 3.8v10.4"/>',
    stop: '<rect x="4.6" y="4.6" width="8.8" height="8.8" rx="1.6"/>',
    search: '<circle cx="8" cy="8" r="4.8"/><path d="M11.6 11.6L15.4 15.4"/>',
    close: '<path d="M4.8 4.8l8.4 8.4M13.2 4.8l-8.4 8.4"/>',
    key: '<circle cx="5.8" cy="12" r="3.2"/><path d="M8.1 9.7l6.5-6.5M12.4 5.4l1.9 1.9M10.6 7.2l1.5 1.5"/>',
    gear: '<path d="M14.56 7.76 L16.34 8.04 L16.34 9.96 L14.56 10.24 L13.81 12.05 L14.87 13.51 L13.51 14.87 L12.05 13.81 L10.24 14.56 L9.96 16.34 L8.04 16.34 L7.76 14.56 L5.95 13.81 L4.49 14.87 L3.13 13.51 L4.19 12.05 L3.44 10.24 L1.66 9.96 L1.66 8.04 L3.44 7.76 L4.19 5.95 L3.13 4.49 L4.49 3.13 L5.95 4.19 L7.76 3.44 L8.04 1.66 L9.96 1.66 L10.24 3.44 L12.05 4.19 L13.51 3.13 L14.87 4.49 L13.81 5.95Z"/><circle cx="9" cy="9" r="2.3"/>',
    terminal: '<rect x="1.8" y="3" width="14.4" height="12" rx="2"/><path d="M5 7.2l2.4 1.8L5 10.8M9.4 11.4h3.6"/>',
    sliders: '<path d="M3 5h7M13.5 5H15M3 13h2.5M9 13h6"/><circle cx="11.8" cy="5" r="1.8"/><circle cx="7.2" cy="13" r="1.8"/>',
    chev: '<path d="M7 4.5L11.5 9 7 13.5"/>',
    chevl: '<path d="M11 4.5L6.5 9 11 13.5"/>',
    arrow: '<path d="M3.4 9h11.2M10.6 5l4 4-4 4"/>',
  };
  // Tek şablon noktası: simgeler ve Genel bakış'ın çizgi grafiği buradan üretilir; içine
  // yalnız bu dosyanın kendi işaretlemesi ve sayılar girer.
  const svgFrom = (markup) => { const t = document.createElement("template"); t.innerHTML = markup; return t.content.firstChild; };
  const svg = (name) => svgFrom('<svg viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + (ICON[name] || ICON.file) + "</svg>");
  const $ = (id) => document.getElementById(id);
  function h(tag, attrs, ...kids) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === "style") { Object.assign(e.style, v); continue; }  // CSP: biçem özniteliği değil, CSSOM
      if (k.startsWith("aria-")) { e.setAttribute(k, String(v)); continue; }
      if (v == null || v === false) continue;
      if (k === "class") e.className = v;
      else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v === true ? "" : v);
    }
    for (const c of kids.flat()) {
      if (c == null || c === false) continue;
      e.append(c.nodeType ? c : document.createTextNode(String(c)));
    }
    return e;
  }
  document.querySelectorAll("[data-icon]").forEach((el) => el.prepend(svg(el.dataset.icon)));

  let toastTimer;
  function toast(msg, action) {
    const t = $("toast");
    t.textContent = "";
    t.append(document.createTextNode(msg));
    if (action) t.append(h("button", { type: "button", class: "toast-act", onclick: () => { t.hidden = true; action.fn(); } }, action.label));
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.hidden = true; }, action ? 6500 : 4200);
  }
  const fail = (err) => toast(err && err.message ? err.message : String(err));

  /* ---------- API ---------- */
  // DD-194/DD-205: on the internet address an expired or missing session sends the browser to the
  // sign-in page, which returns to the same Konsol page afterwards. The tailnet address never asks.
  const toLogin = () => location.replace("/giris.html" + (location.hash.startsWith("#/") ? location.hash : ""));
  function api(path, opts) {
    opts = opts || {};
    const headers = { "X-Konsol": "1" };
    const init = { method: opts.method || "GET", headers, credentials: "same-origin", cache: "no-store", signal: opts.signal };
    if (opts.body !== undefined) {
      headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(opts.body);
    }
    return fetch(path, init).then((res) => {
      if (res.status === 401) return res.json().catch(() => ({})).then((j) => {
        if (j.giris) toLogin();
        throw new Error(j.error || "Oturum gerekli; yeniden giriş yapın.");
      });
      if (opts.blob) {
        if (!res.ok) return res.json().catch(() => ({})).then((j) => { throw new Error(j.error || `HTTP ${res.status}`); });
        return res.blob();
      }
      if (opts.text) {
        if (!res.ok) return res.json().catch(() => ({})).then((j) => { throw new Error(j.error || `HTTP ${res.status}`); });
        return res.text();
      }
      return res.json().catch(() => ({})).then((j) => {
        if (!res.ok) throw new Error(j.error || `HTTP ${res.status}`);
        return j;
      });
    });
  }
  const post = (path, body) => api(path, { method: "POST", body: body || {} });
  const enc = encodeURIComponent;

  /* ---------- biçimleme ---------- */
  const GiB = 1073741824, MiB = 1048576, KiB = 1024;
  const dec = (v, d) => v.toFixed(d).replace(".", ",");
  function bytes(b) {
    if (b == null) return "—";
    if (!b) return "0 B";
    if (b >= 1099511627776) return dec(b / 1099511627776, 2) + " TB";
    if (b >= GiB) return dec(b / GiB, 1) + " GB";
    if (b >= MiB) return Math.round(b / MiB) + " MB";
    return Math.max(1, Math.round(b / KiB)) + " KB";
  }
  function since(seconds) {
    if (!seconds) return "hiç";
    const a = Math.max(0, Math.floor(now() - seconds));
    if (a < 90) return "şimdi";
    if (a < 7200) return `${Math.floor(a / 60)} dk önce`;
    if (a < 172800) return `${Math.floor(a / 3600)} sa önce`;
    return `${Math.floor(a / 86400)} gün önce`;
  }
  function duration(seconds) {
    const d = Math.floor(seconds / 86400), hh = Math.floor((seconds % 86400) / 3600), mm = Math.floor((seconds % 3600) / 60);
    if (d) return `${d} gün ${hh} sa açık`;
    if (hh) return `${hh} sa ${mm} dk açık`;
    return `${mm} dk açık`;
  }
  const clock = (at) => new Date(at * 1000).toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
  function stamp(at) {
    const d = new Date(at * 1000), today = new Date();
    if (d.toDateString() === today.toDateString()) return clock(at);
    today.setDate(today.getDate() - 1);
    if (d.toDateString() === today.toDateString()) return "Dün";
    return d.toLocaleDateString("tr-TR", { day: "numeric", month: "short" });
  }

  /* ---------- durum ---------- */
  const S = { sys: null, health: null, repair: null, fs: null, sysfs: null, actions: [], share: null, offset: 0 };
  const now = () => Date.now() / 1000 + S.offset;
  /* ---------- yükleme ---------- */
  let resourceBusy = false, resourceReceived = 0, resourceFailed = false;
  async function loadSystem() {
    if (resourceBusy) return;
    resourceBusy = true;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 12000);
    try {
      S.sys = await api("/api/konsol/kaynaklar", { signal: controller.signal });
      if (Number.isFinite(S.sys.read_at)) S.offset = S.sys.read_at - Date.now() / 1000;
      resourceReceived = performance.now(); resourceFailed = false;
      paintSystem();
    } catch (_err) {
      resourceFailed = true; paintResources();
    } finally { clearTimeout(timeout); resourceBusy = false; }
  }
  // DD-182: read-only health checks for Settings → Sistem; the server caches them for 30 s.
  let healthFailed = false;
  // DD-239: the health card also carries the last "Denetle ve onar" report; while a run is going it is
  // re-read every two seconds (the run may restart Caddy or Konsol: a failed read just waits).
  let repairTimer = 0;
  function loadHealth() {
    const repair = api("/api/konsol/onarim").then((r) => { S.repair = r; }).catch(() => {});
    return Promise.all([api("/api/konsol/saglik").then((s) => { S.health = s; healthFailed = false; })
      .catch(() => { healthFailed = true; }), repair])
      .finally(() => {
        if (current === "ayarlar" && settingsTab === "system") renderSettings();
        clearTimeout(repairTimer);
        if (S.repair && S.repair.calisiyor && current === "ayarlar" && settingsTab === "system") repairTimer = setTimeout(loadHealth, 2000);
      });
  }
  function startRepair(kip) {
    const go = () => post("/api/konsol/onarim", { kip }).then(() => {
      S.repair = Object.assign({}, S.repair, { calisiyor: true, rapor: null });
      toast(kip === "onar" ? "Denetim ve onarım başladı." : "Denetim başladı.");
      renderSettings();
      repairTimer = setTimeout(loadHealth, 1500);
    }).catch(fail);
    if (kip === "denetle") { go(); return; }
    ask({ title: "Denetim ve onarım başlasın mı?", calm: true, go: "Onar",
      items: [["shield", "Güvenlik duvarı, Tailscale ve adresi, servisler, DNS ve Konsol denetlenir."],
        ["refresh", "Bozuk olanlar yeniden başlatılır ya da yeniden kurulur; yapılandırma dosyaları değişmez."],
        ["info", "Caddy ya da Konsol yeniden başlarsa sayfa birkaç saniye yanıt vermeyebilir."]],
      onOk: go });
  }
  function loadActions() {
    return api("/api/konsol/islemler").then((s) => { S.actions = s.items || []; paintActions(); }).catch(fail);
  }
  function loadFsState() {
    return api("/api/state").then((s) => { S.fs = s; paintFsState(); }).catch(fail);
  }
  // DD-235: the system view answers only on the tailnet site; elsewhere it is absent (404/403). Files only.
  function loadSysState() {
    return api("/api/sistem/state").then((s) => { S.sysfs = s; paintFsState(); }).catch(() => { S.sysfs = null; paintFsState(); });
  }
  // Folder sharing is a built-in Files capability.
  function loadShares() {
    if (sharesPage.interacting()) return Promise.resolve();
    const previous = S.share;
    return api("/api/konsol/paylasim").then((s) => {
      if (S.share !== previous || sharesPage.interacting()) return;
      // DD-236: an unchanged answer repaints nothing (the Files window keeps its focus and hover).
      if (previous && JSON.stringify(previous) === JSON.stringify(s)) return;
      S.share = s; if (current === "dosyalar") renderFs();
    })
      .catch((e) => { if (S.share === previous && !sharesPage.interacting()) { S.share = null; fail(e); } });
  }
  const paintActions = () => { if (current === "ayarlar" && settingsTab === "log") renderLog(); };
  const paintFsState = () => { if (current === "dosyalar") renderRail(); };

  /* ---------- Independent host resources (DD-160) ---------- */
  function resourceValues() {
    const s = S.sys, age = s ? (performance.now() - resourceReceived) / 1000 : Infinity;
    const fresh = !!s && !resourceFailed && age <= 30;
    const cpuFresh = fresh && Number.isFinite(s.sampled_at) && s.read_at - s.sampled_at + age <= 30;
    const cpu = cpuFresh && s.cpu.length ? s.cpu[s.cpu.length - 1] : null;
    const mem = fresh && s.mem.total > 0 ? 100 * s.mem.used / s.mem.total : null;
    const disk = fresh && s.disk?.total > 0 ? 100 * (s.disk.total - s.disk.free) / s.disk.total : null;
    return { s, fresh, cpuFresh, cpu, mem, disk };
  }
  function paintResources() {
    const { s, fresh, cpuFresh, cpu, mem, disk } = resourceValues();
    for (const [id, value] of [["cpu", cpu], ["mem", mem], ["disk", disk]]) {
      const known = Number.isFinite(value);
      $("resource-" + id).textContent = known ? "%" + Math.round(value) : "—";
      $("bar-" + id).hidden = !known;
      if (known) $("bar-" + id).value = Math.max(0, Math.min(100, value));
    }
    $("detail-cpu").textContent = Number.isFinite(cpu) ? s.cores + " çekirdek" : fresh ? "Örnek bekleniyor" : "Güncel ölçüm yok";
    $("detail-mem").textContent = Number.isFinite(mem) ? bytes(s.mem.used) + " / " + bytes(s.mem.total) : "Güncel ölçüm yok";
    $("detail-disk").textContent = Number.isFinite(disk) ? bytes(s.disk.total - s.disk.free) + " / " + bytes(s.disk.total) + " · " + bytes(s.disk.free) + " boş · " + s.root : "Güncel ölçüm yok";
    const status = !s && !resourceFailed ? "Kaynaklar okunuyor…" : !fresh ? "Bağlantı yok · ölçümler eski" : !cpuFresh ? "İşlemci örneği bekleniyor" : "Sunucu kaynakları · canlı";
    if ($("resource-status").textContent !== status) $("resource-status").textContent = status;
    paintFacts();
    paintHomeClock();
  }
  // DD-230: the address facts are Ana Menü's "Sunucu" widget; they are painted wherever it is shown.
  function serverFacts() {
    const { s, fresh } = resourceValues();
    // DD-231: a 1×1 card: short labels; the version shows its last part ("v2-209"), the full string as title.
    const version = s && s.version || "—", shortVersion = version.replace(/^.*-(v\d+-\d+)$/, "$1");
    return [
      ["foot-ts", "TS", s && s.net.tailscale || "—", true],
      ["foot-wan", "WAN", s && s.net.wan || "—", true],
      ["foot-uptime", "Açık", fresh && Number.isFinite(s.uptime) ? uptimeText(s.uptime + (performance.now() - resourceReceived) / 1000) : "—", false],
      ["foot-version", "Sürüm", shortVersion, true, version],
      // DD-195: the tailnet address is HTTP; only the public Konsol address is HTTPS.
      ["foot-access", "Erişim", location.protocol === "https:" ? "İnternet · HTTPS ile bağlı" : "Tailscale ile bağlı", false],
    ];
  }
  function paintFacts() {
    for (const [id, , value] of serverFacts()) { const el = $(id); if (el && el.textContent !== value) el.textContent = value; }
  }
  function paintHomeClock() {
    const clock = $("home-clock"), date = $("home-date");
    if (!clock || !date) return;
    const d = new Date(now() * 1000);
    clock.textContent = d.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
    clock.dateTime = d.toISOString();
    date.textContent = d.toLocaleDateString("tr-TR", { day: "numeric", month: "long", year: "numeric" });
  }
  /* ---------- DD-233: "Güncelle" beside the clock ---------- */
  // The backend compares the installed version with the newest one on GitHub (cached for hours) and
  // runs the update as its own systemd unit; the page only asks, confirms and follows its stage.
  let UPD = null, updAsked = 0, updSeen = "";
  const shortV = (v) => (v || "—").replace(/^.*-(v\d+-\d+)$/, "$1");
  function loadUpdate(force) {
    updAsked = Date.now();
    return api("/api/konsol/guncelleme" + (force ? "?yenile=1" : "")).then((r) => {
      const was = UPD && UPD.is.durum;
      UPD = r;
      // The installer replaced Konsol's own files: a finished run reloads the page once.
      if (was === "calisiyor" && r.is.durum === "tamam") { toast(`Güncelleme tamamlandı: ${shortV(r.kurulu)}. Sayfa yenileniyor…`); setTimeout(() => location.reload(), 2500); }
      if (was === "calisiyor" && r.is.durum === "hata") toast(`Güncelleme başarısız: ${r.is.mesaj || "ayrıntı Ayarlar → Günlük'te"}`);
      paintUpdate();
      return r;
    }).catch(() => { paintUpdate(); return null; });
  }
  function paintUpdate() {
    const box = $("home-update");
    if (!box) return;
    if (!UPD) { box.replaceChildren(); return; }
    // DD-245: one round update icon; words only while an update runs (its stage). Every state keeps its
    // sentence as the accessible name; there is no tooltip.
    const job = UPD.is, running = job.durum === "calisiyor";
    let btn;
    if (running) {
      btn = h("button", { type: "button", class: "upd busy", disabled: true, "aria-label": "Güncelleniyor: " + (job.asama || ""), title: job.asama || "Güncelleniyor" },
        svg("refresh"), h("span", null, "Güncelleniyor"), h("small", null, (job.asama || "").replace(/ — .*$/, "")));
    } else if (UPD.yeni) {
      const locked = !UPD.baslatilabilir;
      btn = h("button", { type: "button", class: "upd icon new", disabled: locked,
        "aria-label": locked ? `Yeni sürüm ${shortV(UPD.son)}; güncelleme yalnız Tailscale adresinden başlatılır` : `Yeni sürüm ${shortV(UPD.son)}: güncelle`
          + (job.durum === "hata" && job.mesaj ? ` · son deneme başarısız: ${job.mesaj}` : ""),
        onclick: askUpdate }, svg("refresh"));
    } else {
      btn = h("button", { type: "button", class: "upd icon" + (UPD.hata ? " err" : ""),
        "aria-label": UPD.hata ? `Sürüm denetlenemedi: ${UPD.hata}` : `Sürüm güncel (${shortV(UPD.kurulu)}); yeniden denetle`,
        onclick: () => loadUpdate(true).then((r) => { if (r) toast(r.yeni ? `Yeni sürüm var: ${shortV(r.son)}` : r.hata || `Sürüm güncel: ${shortV(r.kurulu)}`); }) },
        svg("refresh"));
    }
    const key = btn.className + btn.textContent + btn.getAttribute("aria-label") + btn.disabled;
    if (key === updSeen && box.firstChild) return;
    updSeen = key;
    box.replaceChildren(btn);
  }
  function askUpdate() {
    if (!UPD || !UPD.yeni) return;
    const offer = { surum: UPD.son, commit: UPD.commit };
    ask({ title: `Sunucu ${shortV(UPD.son)} sürümüne güncellensin mi?`, sub: `Kurulu: ${UPD.kurulu} → ${UPD.son}`, calm: true,
      items: [["download", `Kod GitHub'dan indirilir (commit ${UPD.commit.slice(0, 7)}).`],
        ["stack", "Sistem paketleri de güncellenir; birkaç dakika sürebilir."],
        ["refresh", "Konsol ve servisler yeniden başlar; bitince sayfa kendini yeniler."]].concat(
        UPD.is.durum === "hata" && UPD.is.mesaj ? [["info", `Son deneme başarısız: ${UPD.is.mesaj}`]] : []),
      go: "Güncelle",
      onOk: () => post("/api/konsol/guncelleme", offer).then(() => {
        UPD.is = { durum: "calisiyor", asama: "İndiriliyor", hedef: offer.surum, mesaj: "" };
        toast("Güncelleme başladı; bu sayfa açık kalabilir.");
        paintUpdate();
      }).catch((e) => { fail(e); loadUpdate(); }) });
  }
  function paintSystem() {
    const s = S.sys;
    if (!s) return;
    $("brand-host").textContent = s.host;
    $("brand-host-m").textContent = s.host;
    $("brand-sub").textContent = s.domain ? "panel." + s.domain : "Konsol";
    document.title = s.host + " · Konsol";
    paintResources();
    if (current === "ayarlar" && settingsTab === "system") renderSettings();
    if (current === "genel") renderOverview();
  }

  /* ---------- Audit log, shown only in Settings ---------- */
  // Paket API'lerinin satırları "<id>:<eylem>" diye gelir ve metni paketin konsol.json şablonundan alır.
  const ACTION_TEXT = {
    klasor: (e) => `Yeni klasör: ${e.detail}`, ad: (e) => `Yeniden adlandırıldı: ${e.detail}`,
    tasi: (e) => `Taşındı: ${e.detail}`, cope: (e) => `Çöpe taşındı: ${e.detail}`,
    "geri-yukle": (e) => `Çöpten geri yüklendi: ${e.detail}`, "kalici-sil": (e) => `Kalıcı silindi: ${e.detail}`,
    "cop-bosalt": (e) => `Çöp boşaltıldı (${e.detail} öge)`, indir: (e) => `İndirildi: ${e.detail}`,
    "modul-kur": (e) => `${modName(e.detail)} kurulumu başlatıldı`, "modul-baslat": (e) => `${modName(e.detail)} başlatıldı`,
    "modul-durdur": (e) => `${modName(e.detail)} durduruldu`,
    "modul-kaldir": (e) => `${modName(e.detail)} kaldırıldı${e.detail.endsWith("+veri") ? " · verisiyle" : ""}`,
    "modul-hesap": (e) => `${modName(e.detail)} parolası görüntülendi`,
    // DD-183: archive jobs; the result line is written by the server when the job ends.
    "arsiv-olustur": (e) => `ZIP oluşturma başladı: ${e.detail}`, "arsiv-ac": (e) => `Arşiv açma başladı: ${e.detail}`,
    "arsiv-iptal": (e) => `Arşiv işlemi için iptal istendi: ${e.detail}`, "arsiv-sonuc": (e) => `Arşiv işlemi bitti: ${e.detail}`,
    // DD-194/196: Konsol account, settings and share events have their own words and source.
    "hesap-kur": () => "Konsol hesabı oluşturuldu", giris: () => "Konsol girişi", cikis: () => "Konsol çıkışı",
    "parola-degis": () => "Konsol parolası değiştirildi",
    duzen: (e) => e.detail === "sifirla" ? "Ana Menü varsayılan düzene döndü" : "Ana Menü düzeni kaydedildi",
    "ayar-apply": () => "Ayarlar uygulandı", "ayar-confirm": () => "Ayar değişikliği onaylandı",
    "ayar-rollback": () => "Ayarlar geri alındı", "ayar-discard": () => "Takılan ayar işlemi bırakıldı",
    "paylasim-save": () => "Klasör paylaşımı kaydedildi", "paylasim-pause": () => "Klasör paylaşımının durumu değişti",
    "paylasim-remove": () => "Klasör paylaşımı kaldırıldı",
    guncelleme: (e) => `Sunucu güncellemesi başlatıldı: ${e.detail}`,
  };
  // DD-196/200: the root backend carries the Konsol account, Settings, Shares and App Store
  // events; a package API's events are "<id>:<verb>" and take their words from the package.
  const evKind = (e) => e.action.startsWith("modul-") ? "mod" : e.source !== "panel" ? "fs"
    : e.action.includes(":") ? e.action.split(":")[0] : e.action.startsWith("ayar-") ? "ayar" : e.action.startsWith("paylasim-") ? "paylasim" : "konsol";
  const EVICON = { konsol: "key", ayar: "sliders", paylasim: "share", fs: "folder", mod: "stack" };
  const EVLABEL = { konsol: "Konsol", ayar: "Ayarlar", paylasim: "Paylaşımlar", fs: "Dosyalar", mod: "Uygulamalar" };
  const evIcon = (k) => EVICON[k] || metaOf(k).icon;
  const evLabel = (k) => EVLABEL[k] || metaOf(k).name;
  function evText(e) {
    const fn = ACTION_TEXT[e.action];
    let text;
    if (fn) text = fn(e);
    else if (e.action.includes(":")) {
      const [id, verb] = e.action.split(":"), tpl = metaOf(id).gunluk[verb], words = e.detail.split(" ");
      text = typeof tpl === "string" ? tpl.replace(/\{(detail|\d)\}/g, (_, key) => (key === "detail" ? e.detail : words[Number(key)] || ""))
        : `${metaOf(id).name}: ${verb} ${e.detail}`;
    } else text = `${e.action} ${e.detail}`;
    return e.ok ? text : `${text} — başarısız`;
  }
  function evRow(e, full) {
    const k = evKind(e);
    return h("div", { class: "ev" + (e.ok ? "" : " bad") }, h("time", null, stamp(e.at)),
      h("span", { class: `ico ${EVICON[k] ? k : "app"}` }, svg(evIcon(k))),
      h("p", null, evText(e), h("small", null, full ? evLabel(k) : `${evLabel(k)} · ${e.user}`)),
      full ? h("span", { class: "who" }, `${e.user} · ${e.client}`) : null);
  }
  /* ---------- ortak pencere (#sh): uygulama sayfaları, paylaşım ve arşiv formları, dosya görüntüleyici ---------- */
  const xIcon = (btn) => { btn.append(svg("plus")); btn.firstChild.style.transform = "rotate(45deg)"; };
  const shClose = () => $("sh").close();
  function shHead(title, sub, icon) {
    const x = h("button", { type: "button", class: "dlg-x", "aria-label": "Kapat", onclick: shClose });
    xIcon(x);
    return h("div", { class: "dlg-head" },
      h("div", { class: "okhead" }, h("span", { class: "okico plain" }, svg(icon)),
        h("div", null, h("h3", { id: "sh-title" }, title), h("p", null, sub))), x);
  }
  function shShow(title, sub, icon, ...content) {
    $("sh-body").replaceChildren(shHead(title, sub, icon), ...content);
    if (!$("sh").open) $("sh").showModal();
  }
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && current === "dosyalar" && (fsSel.size || fsPicking) && !document.querySelector("dialog[open]")) clearSel();
  });

  /* ---------- onay penceresi ---------- */
  let askOk = null;
  function ask(o) {
    askOk = o.onOk;
    $("cf").classList.toggle("compact", !!o.compact);
    $("cf-title").textContent = o.title;
    $("cf-sub").textContent = o.sub || "";
    $("cf-sub").title = o.compact ? o.sub || "" : "";
    $("cf-sub").hidden = !o.sub;
    $("cf-list").replaceChildren(...(o.items || []).map(([ic, text]) => h("li", null, svg(ic), h("span", null, text))));
    $("cf-list").hidden = !o.items?.length;
    $("cf-list").classList.toggle("calm", !!o.calm);
    $("cf-extra").replaceChildren(...(o.extra ? [o.extra] : []));
    $("cf-extra").hidden = !o.extra;
    $("cf-word-row").hidden = !o.word;
    // DD-235: the word may be the item's own name (system view delete); otherwise "onayla".
    askWord = typeof o.word === "string" ? o.word : "onayla";
    $("cf-word-label").textContent = askWord;
    $("cf-word").value = "";
    const go = $("cf-go");
    go.textContent = o.go;
    go.className = "btn " + (o.danger ? "btn-danger" : "btn-primary");
    go.disabled = !!o.word;
    $("cf").showModal();
    (o.word ? $("cf-word") : $("cf-cancel")).focus();
  }
  xIcon($("cf-x"));
  let askWord = "onayla";
  $("cf-word").addEventListener("input", (e) => {
    $("cf-go").disabled = askWord === "onayla" ? e.target.value.trim().toLocaleLowerCase("tr") !== "onayla" : e.target.value !== askWord;
  });
  const closeAsk = () => { $("cf").close(); askOk = null; };
  $("cf-x").addEventListener("click", closeAsk);
  $("cf-cancel").addEventListener("click", closeAsk);
  $("cf-form").addEventListener("submit", (e) => {
    e.preventDefault();
    if ($("cf-go").disabled) return;
    const fn = askOk;
    closeAsk();
    if (fn) fn();
  });

  /* ---------- Dosyalar ---------- */
  let fsPath = [], fsView = "files", fsList = null, fsTrash = null, fsAdding = false, fsRename = null;
  // DD-232: Finder-style Files: an icon grid (or the list) and, on the right, places, the selection's details and actions.
  let fsLayout = "grid";
  try { fsLayout = localStorage.getItem("konsol-files-view") === "list" ? "list" : "grid"; } catch (e) { /* özel pencere */ }
  /* DD-145: kısayol sütunu, arama, çoklu seçim ve listenin içine bırakarak yükleme. */
  // fsPicking (DD-244): "Seç" is on; a click adds or removes an item and never opens it.
  let fsPicking = false;
  let fsRootDirs = null, fsQuery = "", fsSel = new Set(), fsLast = "", fsOpened = false, fsUps = [], upSeq = 0, upBusy = false, dragDepth = 0;
  /* DD-235: "Sistem (/)": the same page over the root backend's system view (/api/sistem/*). No trash,
     archives or shares there; delete is permanent and asks for the item's name. */
  let fsSys = false;
  /* DD-236: a real file manager's navigation. The window's frame (bar, places, detail) is built once; opening a
     folder swaps only its contents. The listing on screen stays (dimmed, inert) until the next one arrives, a
     failed open stays where it was, back/forward keep each folder's scroll, and recent folders show at once
     from a short cache while they are read again. */
  let fsRouteGo = null, fsNav = 0, fsBusy = false, fsShownPath = null, fsBack = [], fsFwd = [];
  const fsScrolls = new Map(), fsCache = new Map(), FS_CACHE_MS = 60000, FS_CACHE_MAX = 20;
  const fsKey = (sys, parts) => (sys ? "s:" : "f:") + parts.join("/");
  const FX_WIDE = window.matchMedia("(min-width: 1101px)");
  const fsApi = (p) => (fsSys ? "/api/sistem" + p.slice(4) : p);
  const fsState = () => (fsSys ? S.sysfs : S.fs);
  /* DD-144: kök kullanıcı alanı (/srv); adı arka uçtan gelir, hiçbir yerde sabit yazılmaz. */
  const fsRoot = () => (fsSys ? "/" : (S.fs && S.fs.root) || "/srv");
  const fsHere = () => (fsSys ? "/" + fsPath.join("/") : [fsRoot(), ...fsPath].join("/") || "/");
  const pathText = (parts) => parts.join("/");
  /* DD-203: paketlerin yazdığı klasörler köke göre, sahibinin adıyla gelir ({path, owner}); Konsol
     onları seçtirmez, paylaştırmaz ve kimin yazdığını söyler. Hiçbir ad burada sabit değildir. */
  const protectedList = () => (!fsSys && S.fs && Array.isArray(S.fs.protected) ? S.fs.protected : []);
  const protectedOwner = (rel) => { const hit = protectedList().find((p) => rel === p.path || rel.startsWith(p.path + "/")); return hit ? hit.owner : ""; };
  const inTemp = (rel) => !!protectedOwner(rel);
  const kindOf = (item) => (item.type === "dir" ? "dir" : /\.(txt|log|nfo|srt|sub|md|json|conf|ini|csv|yml|yaml)$/i.test(item.name) ? "text"
    : /\.(mkv|mp4|avi|mov|m4v|ts|webm)$/i.test(item.name) ? "video" : "file");
  const isText = (item) => kindOf(item) === "text";
  // Büyük simgeler: klasör ve uzantı etiketli belge; etiketin rengi dosya türünden gelir.
  const extOf = (name) => { const m = /\.([A-Za-z0-9]{1,5})$/.exec(name); return m ? m[1].toUpperCase().slice(0, 4) : ""; };
  const extTone = (name) => /\.(zip|rar|7z|tar|gz|tgz|bz2|xz|r\d\d|part\d+\.rar)$/i.test(name) ? "x-arc"
    : /\.(mkv|mp4|avi|mov|m4v|ts|webm|mp3|flac|wav|m4a)$/i.test(name) ? "x-media"
    : /\.(jpe?g|png|gif|webp|heic|svg)$/i.test(name) ? "x-img"
    : /\.(pdf)$/i.test(name) ? "x-pdf" : /\.(iso|img|dmg)$/i.test(name) ? "x-disk" : "x-doc";
  const folderArt = () => svgFrom('<svg class="fx-art fx-folder" viewBox="0 0 64 52" aria-hidden="true"><path class="back" d="M4 8a4 4 0 0 1 4-4h16l6 6h26a4 4 0 0 1 4 4v4H4z"/><rect class="front" x="4" y="14" width="56" height="34" rx="5"/><rect class="shine" x="4" y="14" width="56" height="6"/></svg>');
  const docArt = (name) => {
    const ext = extOf(name).replace(/[^A-Z0-9]/g, "");
    return svgFrom(`<svg class="fx-art fx-doc ${extTone(name)}" viewBox="0 0 52 64" aria-hidden="true"><path class="page" d="M8 2h26l14 14v42a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4V6a4 4 0 0 1 4-4z"/><path class="fold" d="M34 2v10a4 4 0 0 0 4 4h10"/>${ext ? `<rect class="tag" x="7" y="40" width="38" height="14" rx="3"/><text x="26" y="50.5" text-anchor="middle">${ext}</text>` : ""}</svg>`);
  };
  const stackArt = (count) => svgFrom(`<svg class="fx-art fx-stack" viewBox="0 0 72 76" aria-hidden="true"><path class="page2" d="M22 4h24l12 12v44a4 4 0 0 1-4 4H22a4 4 0 0 1-4-4V8a4 4 0 0 1 4-4z"/><path class="page" d="M12 14h24l12 12v42a4 4 0 0 1-4 4H12a4 4 0 0 1-4-4V18a4 4 0 0 1 4-4z"/><path class="fold" d="M36 14v8a4 4 0 0 0 4 4h8"/><circle class="badge" cx="50" cy="62" r="11"/><text x="50" y="66.5" text-anchor="middle">${Math.min(count, 99)}</text></svg>`);
  const itemArt = (item) => (item.type === "dir" ? folderArt() : docArt(item.name));

  function applyList(r, scroll) {
    fsList = r;
    fsShownPath = fsPath.slice();
    fsSel.forEach((n) => { if (!r.entries.some((e) => e.name === n)) fsSel.delete(n); });
    if (!fsPath.length) fsRootDirs = r.entries.filter((e) => e.type === "dir").map((e) => ({ name: e.name, count: e.count }));
    setFsLoading(false);
    renderFs();
    const box = $("fs-rows");
    if (box && scroll != null) box.scrollTop = scroll;
    // The opened tile is gone; keep the keyboard in the contents instead of the page.
    if (box && current === "dosyalar" && (document.activeElement === document.body || !document.activeElement)) box.focus({ preventScroll: true });
    if (fsRootDirs == null) loadRootDirs();
  }
  // nav: undefined refreshes the folder on screen in place (after a change; the cache is dropped);
  // {restore, push} opens fsPath: from the cache at once when recent, otherwise over the dimmed old listing.
  function loadFs(nav) {
    const sys = fsSys, parts = fsPath.slice(), at = pathText(parts), key = fsKey(sys, parts), token = ++fsNav;
    if (!nav) fsCache.clear();
    const hit = nav && fsCache.get(key), cached = hit && Date.now() - hit.at < FS_CACHE_MS ? hit.list : null;
    const scroll = nav ? (nav.restore ? fsScrolls.get(key) || 0 : 0) : null;
    if (cached) applyList(cached, scroll); else if (nav) setFsLoading(true);
    fsBusy = true;
    return api(fsApi(`/api/list?path=${enc(at)}`)).then((r) => {
      if (token !== fsNav || sys !== fsSys || at !== pathText(fsPath)) return;
      fsCache.delete(key);
      fsCache.set(key, { list: r, at: Date.now() });
      while (fsCache.size > FS_CACHE_MAX) fsCache.delete(fsCache.keys().next().value);
      if (cached && JSON.stringify(cached) === JSON.stringify(r)) return;
      applyList(r, cached ? null : scroll);
    }).catch((e) => {
      if (token !== fsNav) return;
      setFsLoading(false);
      fail(e);
      // A folder that cannot be opened leaves you where you were, like any file manager.
      if (nav && fsList && fsShownPath && pathText(fsShownPath) !== pathText(fsPath)) {
        fsPath = fsShownPath.slice();
        if (nav.push) fsBack.pop();
        syncHash(false);
        renderFs();
        return;
      }
      if (fsPath.length) { fsPath = []; loadFs({}); } else if (fsSys) fsOpen([], false);
    }).finally(() => { if (token === fsNav) fsBusy = false; });
  }
  function setFsLoading(on) {
    const panel = $("fs-panel");
    if (!panel) return;
    panel.classList.toggle("fx-loading", on);
    for (const id of ["fs-rows", "fs-detail"]) { const el = $(id); if (el) el.inert = on; }
    if (on) paintBar();
  }
  /* Alt klasörden açılan sayfada da kısayol sütunu dolsun. */
  function loadRootDirs() {
    const sys = fsSys;
    return api(fsApi("/api/list?path=&dirs=1")).then((r) => {
      if (sys !== fsSys) return;
      fsRootDirs = r.entries.map((e) => ({ name: e.name, count: e.count }));
      renderRail();
    }).catch(() => { fsRootDirs = []; });
  }
  function loadTrash() {
    return api("/api/trash").then((r) => { fsTrash = r.items || []; renderFs(); }).catch(fail);
  }
  // how: "push" (a new place: history grows), "back"/"fwd" (history moves, the folder's scroll comes back),
  // "hash" (the browser's own back/forward or an address: the folder's scroll comes back, the address is already right).
  function fsGo(parts, how = "push") {
    const same = pathText(parts) === pathText(fsPath), box = $("fs-rows");
    if (box && fsShownPath) fsScrolls.set(fsKey(fsSys, fsShownPath), box.scrollTop);
    const push = how === "push" && !same && !!fsShownPath;
    if (push) { fsBack.push(fsPath.slice()); if (fsBack.length > 50) fsBack.shift(); fsFwd = []; }
    fsPath = parts;
    fsAdding = false;
    fsRename = null;
    fsSel.clear();
    fsPicking = false;
    fsQuery = "";
    // Phones scroll the page; the desktop window scrolls only its contents (DD-236).
    if (current === "dosyalar" && !FX_WIDE.matches) window.scrollTo({ top: 0 });
    if (how !== "hash") syncHash(!same);
    paintBar();
    renderRail();
    return loadFs({ restore: how !== "push", push });
  }
  function fsHistory(dir) {
    const from = dir < 0 ? fsBack : fsFwd, to = dir < 0 ? fsFwd : fsBack;
    if (!from.length || !fsShownPath) return;
    to.push(fsPath.slice());
    fsGo(from.pop(), dir < 0 ? "back" : "fwd");
  }
  /* DD-237: the open folder is in the address: #/dosyalar/klasor/<a>/<b> (/srv) or #/dosyalar/sistem/<a>/<b>
     (the system view), each part URI-encoded. Opening a folder pushes a browser history entry without a
     reload; a reload or a bookmark opens that folder; bare #/dosyalar keeps the folder you were in. */
  const fsPathHash = (sys, parts) => (sys ? "#/dosyalar/sistem" : "#/dosyalar/klasor") + parts.map((p) => "/" + encodeURIComponent(p)).join("");
  const fsHash = (v) => (v === "trash" ? "#/dosyalar/cop" : v === "shares" ? "#/dosyalar/paylasim" : fsPathHash(fsSys, fsPath));
  function syncHash(push) {
    if (current !== "dosyalar" || fsView !== "files") return;
    const want = fsHash("files");
    if (location.hash !== want) history[push ? "pushState" : "replaceState"](null, "", want);
  }
  // Path parts from the address; null when it names no folder (bare #/dosyalar) or cannot be decoded.
  function hashParts(raw) {
    if (raw[1] !== "klasor" && raw[1] !== "sistem") return null;
    try {
      const parts = raw.slice(2).filter(Boolean).map(decodeURIComponent);
      return parts.some((p) => p === "." || p === ".." || p.includes("/") || p.includes("\0")) ? [] : parts;
    } catch (e) { return []; }
  }
  function fsSetView(v) {
    fsView = v;
    location.hash = fsHash(v);
    renderFs();
    if (v === "trash") loadTrash();
    else if (v === "shares") loadShares();
    else if (v === "files" && !fsList && !fsBusy) loadFs();
  }

  /* ---- sağ menü (DD-232): Favoriler (kök ve kök klasörleri), Konumlar (Paylaşımlar, Çöp), disk ---- */
  function railBtn(o) {
    return h("button", { type: "button", class: "rl" + (o.cur ? " cur" : ""), "aria-current": o.cur ? "true" : "false", title: o.title, onclick: o.onclick },
      h("span", { class: `rl-ico ${o.tone}` }, svg(o.icon)),
      h("span", { class: "rl-nm" }, o.title),
      o.count != null && o.count !== "" ? h("span", { class: "rl-c" }, String(o.count)) : null);
  }
  /* DD-237: Favoriler lists the first FAV_MAX top folders (plus the one you are in) and a "show all" switch,
     so a long root does not push Konumlar and the disk out of the column. */
  const FAV_MAX = 8;
  let fsFavAll = false;
  function favDirs(files) {
    const dirs = fsRootDirs || [], long = dirs.length > FAV_MAX;
    const shown = !long || fsFavAll ? dirs : dirs.filter((d, i) => i < FAV_MAX || d.name === fsPath[0]);
    return [...shown.map((d) => railBtn({ cur: files && fsPath[0] === d.name, icon: "folder", tone: "t-dir", title: d.name, onclick: () => fsOpen([d.name]) })),
      long ? h("button", { type: "button", class: "rl-more", "aria-expanded": fsFavAll ? "true" : "false",
        onclick: () => { fsFavAll = !fsFavAll; renderRail(); } }, fsFavAll ? "Daha az göster" : `Tümünü göster (${dirs.length})`) : null];
  }
  function renderRail() {
    const rail = $("fs-rail");
    if (!rail) return;
    const files = fsView === "files", trash = S.fs && S.fs.trash ? S.fs.trash.count : null;
    const shares = S.share && Array.isArray(S.share.items) ? S.share.items.length : null;
    const specs = [
      h("p", { class: "fx-group" }, "Favoriler"),
      railBtn({ cur: files && !fsSys && !fsPath.length, icon: "server", tone: "t-dir", title: "Sunucu", count: (S.fs && S.fs.root) || "/srv", onclick: () => fsOpen([], false) }),
      ...(!fsSys ? favDirs(files) : []),
      S.sysfs ? railBtn({ cur: files && fsSys && !fsPath.length, icon: "lock", tone: "t-sys", title: "Sistem (/)", count: "root", onclick: () => fsOpen([], true) }) : null,
      ...(fsSys ? favDirs(files) : []),
      h("p", { class: "fx-group" }, "Konumlar"),
      railBtn({ cur: fsView === "shares", icon: "share", tone: "t-dir", title: "Paylaşımlar", count: shares || null, onclick: () => fsSetView("shares") }),
      railBtn({ cur: fsView === "trash", icon: "trash", tone: "t-dir", title: "Çöp", count: trash || null, onclick: () => fsSetView("trash") })].filter(Boolean);
    // DD-236: the places column is rebuilt only when its entries change; otherwise only the mark moves.
    const sig = specs.map((e) => e.textContent + "|" + (e.querySelector(".rl-ico") || {}).className).join("\n");
    if (rail.dataset.sig !== sig || rail.children.length !== specs.length) { rail.dataset.sig = sig; rail.replaceChildren(...specs); }
    else specs.forEach((e, i) => {
      const b = rail.children[i], cur = e.classList.contains("cur");
      if (b.classList.contains("cur") !== cur) { b.classList.toggle("cur", cur); b.setAttribute("aria-current", cur ? "true" : "false"); }
    });
    const disk = $("fs-disk"), d = fsState() && fsState().disk;
    if (disk) {
      const known = d && d.total > 0, pct = known ? Math.round(100 * (d.total - d.free) / d.total) : 0;
      disk.replaceChildren(h("small", null, `Disk · ${fsRoot()}`),
        h("progress", { max: "100", value: String(pct), "aria-label": "Disk doluluğu", hidden: !known }),
        h("small", null, known ? `${bytes(d.total - d.free)} / ${bytes(d.total)} · ${bytes(d.free)} boş` : "Disk bilgisi yok"));
    }
  }
  function fsOpen(parts, sys = fsSys) {
    // Another tree (Sunucu ↔ Sistem): nothing of the old one stays on screen or in history.
    if (sys !== fsSys) { fsSys = sys; fsRootDirs = null; fsList = null; fsShownPath = null; fsBack = []; fsFwd = []; }
    if (fsView !== "files") { fsView = "files"; renderFs(); }
    fsGo(parts);
  }

  /* ---- liste: arama + sıralama ---- */
  function fsShown() {
    const q = fsQuery.trim().toLocaleLowerCase("tr");
    const all = fsList.entries.slice().sort((a, b) => (a.type === b.type ? a.name.localeCompare(b.name, "tr") : a.type === "dir" ? -1 : 1));
    return q ? all.filter((e) => e.name.toLocaleLowerCase("tr").includes(q)) : all;
  }
  const selItems = () => fsShown().filter((e) => fsSel.has(e.name));
  // Seçimi bırakmak "Seç" kipini de kapatır (Esc, boş alana tık, "Seçimi bırak").
  function clearSel() { if (!fsSel.size && !fsPicking) return; fsSel.clear(); fsPicking = false; renderRows(); renderDetail(); paintBar(); }
  function togglePick() {
    if (fsPicking) { clearSel(); return; }
    fsPicking = true; renderRows(); renderDetail(); paintBar();
  }
  function selectAll() {
    fsSel = new Set(fsShown().map((e) => e.name).filter((n) => !inTemp(pathText(fsPath.concat(n)))));
    renderRows(); renderDetail();
  }
  // Izgarada tık: tek seçim; seçili tek ögeye yeniden tık onu açar. Çift tık da iki tıktır: ögeyi bir kez açar, açan tıktan
  // sonraki tık (e.detail > 1) yok sayılır; yoksa klasör iki kez açılıyordu (klasör/klasör → "bulunamadı") ya da dosya iki kez
  // iniyordu. Ctrl/Cmd ekler, Shift aralık seçer.
  function openItem(item) {
    if (item.type === "dir") fsGo(fsPath.concat(item.name)); else if (isText(item)) openText(item); else download(item);
  }
  function pickItem(item, e) {
    if (fsPicking || (e && (e.shiftKey || e.ctrlKey || e.metaKey))) { toggleSel(item.name, !!(e && e.shiftKey)); return; }
    if (e && e.detail > 1 && fsOpened) return;
    fsOpened = fsSel.size === 1 && fsSel.has(item.name);
    if (fsOpened) { openItem(item); return; }
    fsSel = new Set([item.name]); fsLast = item.name;
    renderRows(); renderDetail();
    document.querySelector(`[data-item="${CSS.escape(item.name)}"]`)?.focus();
  }
  function toggleSel(name, range) {
    const names = fsShown().map((e) => e.name);
    if (range && fsSel.size) {
      const last = names.indexOf(fsLast), now = names.indexOf(name);
      if (last >= 0 && now >= 0) {
        for (let i = Math.min(last, now); i <= Math.max(last, now); i++) fsSel.add(names[i]);
        fsLast = name; renderRows(); renderDetail(); return;
      }
    }
    if (fsSel.has(name)) fsSel.delete(name); else fsSel.add(name);
    fsSel.forEach((n) => { if (inTemp(pathText(fsPath.concat(n)))) fsSel.delete(n); });
    fsLast = name;
    renderRows();
    renderDetail();
  }

  function renderFs() {
    renderRail();
    const panel = $("fs-panel"), body = $("fs-body");
    panel.dataset.fs = fsView;
    if (fsView !== "files") {
      body.dataset.mode = fsView;
      body.textContent = "";
      if (fsView === "trash") { body.append(h("h2", { class: "fx-title" }, "Çöp")); renderTrashList(body); }
      else { body.append(h("h2", { class: "fx-title" }, "Paylaşımlar")); renderShareList(body); }
      renderDetail();
      return;
    }
    // DD-236: the bar, the archive strip and the contents box are built once per tree; later calls repaint them.
    const mode = fsSys ? "sys" : "files";
    if (body.dataset.mode !== mode || !$("fs-rows")) {
      body.dataset.mode = mode;
      // DD-183: a running archive job shows here (progress, cancel); results go to Günlük.
      const archiveBar = h("div", { id: "archive-bar", class: "archive-bars", hidden: true });
      body.replaceChildren(h("div", { id: "fs-bar" }), archiveBar,
        h("div", { id: "fs-rows", class: "fx-rows " + fsLayout, tabindex: "-1", "aria-label": "Klasör içeriği", onkeydown: fsKeys }));
      if (!fsSys) archiveTools.mount(archiveBar);
      initDrop();
      buildBar();
    }
    paintBar();
    if (!fsList) { $("fs-rows").replaceChildren(h("p", { class: "hint-s fx-wait" }, "Yükleniyor…")); renderDetail(); return; }
    renderRows();
    renderDetail();
  }

  function buildBar() {
    const picker = h("input", { type: "file", id: "fs-file", multiple: true, class: "vis-hidden",
      onchange: (e) => { uploadFiles(e.target.files); e.target.value = ""; } });
    const nav = (id, label, icon, fn) => h("button", { type: "button", class: "pf-btn", id, title: label, "aria-label": label, onclick: fn }, svg(icon));
    $("fs-bar").replaceChildren(h("div", { class: "pathfield" },
      nav("fs-back", "Geri", "chevl", () => fsHistory(-1)),
      nav("fs-fwd", "İleri", "chev", () => fsHistory(1)),
      nav("fs-up", "Üst klasör", "up", () => fsGo(fsPath.slice(0, -1))),
      nav("fs-home", "Sunucu kökü", "home", () => fsGo([])),
      h("span", { class: "pf-sep" }),
      h("nav", { class: "pf-crumbs", id: "fs-crumbs", "aria-label": "Konum" }),
      h("span", { class: "fs-search" }, svg("search"),
        h("input", { type: "search", id: "fs-q", placeholder: "Bu klasörde ara", "aria-label": "Bu klasörde ara",
          autocomplete: "off", spellcheck: "false",
          oninput: (e) => { fsQuery = e.target.value; renderRows(); renderDetail(); },
          onkeydown: (e) => { if (e.key === "Escape") { fsQuery = ""; e.target.value = ""; renderRows(); renderDetail(); } } })),
      h("span", { class: "fx-views", role: "group", "aria-label": "Görünüm" }, ...[["grid", "Simgeler", "grid"], ["list", "Liste", "list"]].map(([id, label, icon]) =>
        h("button", { type: "button", class: "pf-btn", "data-layout": id, "aria-pressed": "false", "aria-label": label, title: label, onclick: () => {
          fsLayout = id; try { localStorage.setItem("konsol-files-view", id); } catch (e) { /* özel pencere */ }
          $("fs-rows").className = "fx-rows " + fsLayout; paintBar(); renderRows();
        } }, svg(icon)))),
      picker,
      h("button", { type: "button", class: "btn btn-sm", onclick: () => $("fs-file").click() }, svg("upload"), "Yükle"),
      // DD-244: "Seç" turns clicks into adding/removing items ("Tümünü seç" is in the detail panel, so the bar
      // never changes width).
      h("button", { type: "button", class: "btn btn-sm fx-pick", id: "fs-pick", "aria-pressed": "false", onclick: togglePick }, svg("check"), "Seç"),
      h("button", { type: "button", class: "pf-btn", title: "Yeni klasör", "aria-label": "Yeni klasör", onclick: startNewFolder }, svg("plus")),
      h("span", { class: "fx-progress", "aria-hidden": "true" })));
  }
  // Repaints the bar in place: history and up buttons, the path, the search text, the view switch. DD-243: no
  // count or size here; it changed the bar's width at every folder (the detail panel names them).
  function paintBar() {
    if (!$("fs-crumbs")) return;
    $("fs-back").disabled = !fsBack.length;
    $("fs-fwd").disabled = !fsFwd.length;
    $("fs-up").disabled = $("fs-home").disabled = !fsPath.length;
    $("fs-crumbs").replaceChildren(h("ol", { class: "crumbs" },
      h("li", null, h("button", { type: "button", class: "crumb root" + (fsPath.length ? "" : " cur"), onclick: () => fsGo([]) }, fsRoot())),
      ...fsPath.map((part, i) => h("li", null, h("button", { type: "button", class: "crumb" + (i === fsPath.length - 1 ? " cur" : ""),
        onclick: () => fsGo(fsPath.slice(0, i + 1)) }, part)))));
    const ol = $("fs-crumbs").firstChild;
    ol.scrollLeft = ol.scrollWidth;
    const q = $("fs-q");
    if (q.value !== fsQuery) q.value = fsQuery;
    document.querySelectorAll("#fs-bar [data-layout]").forEach((b) => b.setAttribute("aria-pressed", b.dataset.layout === fsLayout ? "true" : "false"));
    $("fs-pick").setAttribute("aria-pressed", fsPicking ? "true" : "false");
  }
  function startNewFolder() { fsAdding = true; renderRows(); const i = $("nf-name"); if (i) i.focus(); }

  /* DD-236: keyboard like a file manager, while the contents have the focus: arrows move the selection
     (Shift extends it), Enter or Ctrl/⌘+↓ opens, Backspace or Ctrl/⌘+↑ goes up, Alt+←/→ back and forward,
     Ctrl/⌘+A selects everything that may be selected. */
  function fsKeys(e) {
    if (e.target.closest("input, textarea, select") || !fsList || $("fs-panel").classList.contains("fx-loading")) return;
    const mod = e.ctrlKey || e.metaKey;
    if (e.altKey && (e.key === "ArrowLeft" || e.key === "ArrowRight")) { e.preventDefault(); fsHistory(e.key === "ArrowLeft" ? -1 : 1); return; }
    if (e.key === "Backspace" || (mod && e.key === "ArrowUp")) { if (fsPath.length) { e.preventDefault(); fsGo(fsPath.slice(0, -1)); } return; }
    if (mod && e.key.toLowerCase() === "a") {
      e.preventDefault();
      fsSel = new Set(fsShown().map((x) => x.name).filter((n) => !inTemp(pathText(fsPath.concat(n)))));
      renderRows(); renderDetail();
      return;
    }
    if (e.key === "Enter" || (mod && e.key === "ArrowDown")) {
      const one = selItems();
      if (one.length === 1) { e.preventDefault(); openItem(one[0]); }
      return;
    }
    const grid = fsLayout === "grid", table = $("fs-table");
    const cols = grid && table ? getComputedStyle(table).gridTemplateColumns.split(" ").length : 1;
    const step = { ArrowLeft: grid ? -1 : 0, ArrowRight: grid ? 1 : 0, ArrowUp: -cols, ArrowDown: cols }[e.key];
    if (!step) return;
    e.preventDefault();
    const names = fsShown().map((x) => x.name);
    if (!names.length) return;
    const at = fsSel.has(fsLast) ? names.indexOf(fsLast) : -1;
    const next = names[at < 0 ? 0 : Math.max(0, Math.min(names.length - 1, at + step))];
    if (e.shiftKey && at >= 0) fsSel.add(next); else fsSel = new Set([next]);
    fsLast = next;
    renderRows(); renderDetail();
    const el = document.querySelector(`#fs-rows [data-item="${CSS.escape(next)}"]`);
    if (el) { (el.matches("button") ? el : el.querySelector("button.fname") || el).focus({ preventScroll: true }); el.scrollIntoView({ block: "nearest" }); }
  }

  function renderRows() {
    const box = $("fs-rows");
    if (!box) return;
    box.classList.toggle("picking", fsPicking);
    const shown = fsShown();
    const kids = [];
    if (inTemp(pathText(fsPath))) {
      kids.push(h("div", { class: "offbar" }, h("div", null, h("strong", null, `${protectedOwner(pathText(fsPath))} bu klasöre yazıyor. `),
        h("span", null, "Buradaki dosyaları taşımak ya da silmek süren indirmeyi bozar."))));
    }
    if (fsLayout === "grid") {
      const grid = h("div", { class: "fx-grid" + (dragDepth ? " dragging" : ""), id: "fs-table", role: "group", "aria-label": `${fsHere()} içeriği`,
        onclick: (e) => { if (e.target === e.currentTarget) clearSel(); } },
        dragDepth ? h("div", { class: "droptip" }, svg("upload"), h("span", null, "Bırakın — "), h("b", null, fsHere()), h("span", null, " içine yüklenir")) : null,
        ...fsUps.filter((u) => u.path === pathText(fsPath) && u.sys === fsSys).map(upTile),
        ...shown.map(fsTile));
      if (fsAdding) grid.append(newFolderTile());
      if (!shown.length && !fsAdding && !fsUps.length) grid.append(h("div", { class: "empty-row" },
        h("strong", null, fsQuery.trim() ? "Eşleşen öge yok" : "Bu klasör boş"),
        h("span", null, fsQuery.trim() ? "Aramayı değiştirin ya da Esc ile temizleyin." : "Dosyaları buraya sürükleyin ya da Yükle ile seçin.")));
      kids.push(grid);
      if (fsList.skipped) kids.push(h("p", { class: "hint-s" }, `${fsList.skipped} öge gösterilmedi (adı geçersiz).`));
      box.replaceChildren(...kids);
      return;
    }
    const table = h("div", { class: "table fs-t" + (dragDepth ? " dragging" : ""), id: "fs-table" },
      dragDepth ? h("div", { class: "droptip" }, svg("upload"), h("span", null, "Bırakın — "), h("b", null, fsHere()), h("span", null, " içine yüklenir")) : null,
      h("div", { class: "tr head" }, h("span", null, ""), h("span", null, "Ad"), h("span", { class: "c-size" }, "Boyut"),
        h("span", { class: "c-date" }, "Değiştirilme"), h("span", null, "")),
      ...fsUps.filter((u) => u.path === pathText(fsPath) && u.sys === fsSys).map(upRow),
      ...shown.map(fsRow));
    if (fsAdding) table.append(newFolderRow());
    if (!shown.length && !fsAdding && !fsUps.length) {
      table.append(h("div", { class: "empty-row" },
        h("strong", null, fsQuery.trim() ? "Eşleşen öge yok" : "Bu klasör boş"),
        h("span", null, fsQuery.trim() ? "Aramayı değiştirin ya da Esc ile temizleyin." : "Dosyaları buraya sürükleyin ya da Yükle ile seçin.")));
    }
    kids.push(table);
    if (fsList.skipped) kids.push(h("p", { class: "hint-s" }, `${fsList.skipped} öge gösterilmedi (adı geçersiz).`));
    box.replaceChildren(...kids);
  }

  /* ---- yükleme: hedef listenin kendisi, ilerleme satırın içinde (DD-145) ---- */
  function upRow(u) {
    const pct = u.size ? Math.min(100, Math.round((100 * u.sent) / u.size)) : 0;
    return h("div", { class: "tr up" + (u.state === "wait" ? " wait" : "") + (u.state === "err" ? " err" : ""), id: `up-${u.id}` },
      h("span", { class: "c-sel" }),
      h("span", { class: "fname" }, h("span", { class: "ticon t-file" }, svg("upload")),
        h("span", null, h("strong", null, u.name),
          h("span", { class: "uprog" }, h("i", { id: `upb-${u.id}`, style: { width: `${pct}%` } })))),
      h("span", { class: "c-size" }, bytes(u.size)),
      h("span", { class: "c-date", id: `upm-${u.id}` }, upText(u, pct)),
      h("span", { class: "acts" }, h("button", { type: "button", class: "ib del", title: "İptal", "aria-label": "Yüklemeyi iptal et",
        onclick: () => cancelUp(u) }, svg("close"))));
  }
  function upTile(u) {
    const pct = u.size ? Math.min(100, Math.round((100 * u.sent) / u.size)) : 0;
    return h("div", { class: "fx-item up" + (u.state === "err" ? " err" : ""), id: `up-${u.id}` }, docArt(u.name),
      h("span", { class: "fx-name" }, u.name),
      h("span", { class: "uprog" }, h("i", { id: `upb-${u.id}`, style: { width: `${pct}%` } })),
      h("span", { class: "fx-sub", id: `upm-${u.id}` }, upText(u, pct)),
      h("button", { type: "button", class: "ib del fx-cancel", title: "İptal", "aria-label": "Yüklemeyi iptal et", onclick: () => cancelUp(u) }, svg("close")));
  }
  const upText = (u, pct) => (u.state === "err" ? u.error || "yüklenemedi" : u.state === "wait" ? "sırada" : `%${pct}`);
  function upTick(u) {
    const bar = $(`upb-${u.id}`), meta = $(`upm-${u.id}`);
    const pct = u.size ? Math.min(100, Math.round((100 * u.sent) / u.size)) : 0;
    if (bar) bar.style.width = `${pct}%`;
    if (meta) meta.textContent = upText(u, pct);
  }
  function uploadFiles(list) {
    const here = pathText(fsPath);
    const files = Array.from(list || []);
    if (!files.length) return;
    // Aynı adlı öge zaten varsa dosya hiç gönderilmez: sunucu üzerine yazmaz, boşuna aktarım olmaz.
    const taken = new Set((fsList && fsList.path === here ? fsList.entries : []).map((e) => e.name));
    fsUps.filter((u) => u.path === here && u.sys === fsSys && u.state !== "err").forEach((u) => taken.add(u.name));
    for (const f of files) {
      const clash = taken.has(f.name);
      taken.add(f.name);
      fsUps.push({ id: ++upSeq, name: f.name, size: f.size, sent: 0, file: f, path: here, sys: fsSys, api: fsSys ? (q) => "/api/sistem" + q.slice(4) : (q) => q,
        state: clash ? "err" : "wait", error: clash ? "zaten var; üzerine yazılmaz" : "" });
    }
    renderRows();
    pumpUp();
  }
  function pumpUp() {
    if (upBusy) return;
    const u = fsUps.find((x) => x.state === "wait");
    if (!u) return;
    upBusy = true;
    u.state = "up";
    upTick(u);
    const xhr = new XMLHttpRequest();
    u.xhr = xhr;
    xhr.open("POST", u.api(`/api/upload?path=${enc(u.path)}&name=${enc(u.name)}`));
    xhr.setRequestHeader("X-Konsol", "1");
    xhr.upload.addEventListener("progress", (e) => { u.sent = e.loaded; upTick(u); });
    xhr.addEventListener("load", () => {
      upBusy = false;
      if (xhr.status >= 200 && xhr.status < 300) {
        fsUps = fsUps.filter((x) => x !== u);
        if (u.path === pathText(fsPath) && u.sys === fsSys) loadFs().then(() => toast(`“${u.name}” yüklendi.`));
        else toast(`“${u.name}” yüklendi.`);
      } else {
        let message = `sunucu ${xhr.status}`;
        try { message = JSON.parse(xhr.responseText).error || message; } catch (err) { /* düz metin */ }
        u.state = "err";
        u.error = message;
        upTick(u);
      }
      pumpUp();
    });
    xhr.addEventListener("error", () => { upBusy = false; u.state = "err"; u.error = "bağlantı koptu"; upTick(u); pumpUp(); });
    xhr.addEventListener("abort", () => { upBusy = false; pumpUp(); });
    xhr.send(u.file);
  }
  function cancelUp(u) {
    if (u.xhr && u.state === "up") u.xhr.abort();
    fsUps = fsUps.filter((x) => x !== u);
    renderRows();
  }
  let dropReady = false;
  function initDrop() {
    if (dropReady) return;
    dropReady = true;
    const panel = $("fs-panel");
    const hasFiles = (e) => Array.from((e.dataTransfer && e.dataTransfer.types) || []).includes("Files");
    panel.addEventListener("dragenter", (e) => {
      if (fsView !== "files" || !hasFiles(e)) return;
      e.preventDefault(); dragDepth++; if (dragDepth === 1) renderRows();
    });
    panel.addEventListener("dragover", (e) => {
      if (fsView !== "files" || !hasFiles(e)) return;
      e.preventDefault(); e.dataTransfer.dropEffect = "copy";
    });
    panel.addEventListener("dragleave", (e) => {
      if (fsView !== "files" || !hasFiles(e)) return;
      dragDepth = Math.max(0, dragDepth - 1); if (!dragDepth) renderRows();
    });
    panel.addEventListener("drop", (e) => {
      if (fsView !== "files" || !hasFiles(e)) return;
      e.preventDefault(); dragDepth = 0; renderRows(); uploadFiles(e.dataTransfer.files);
    });
    for (const type of ["dragover", "drop"]) {
      document.addEventListener(type, (e) => { if (hasFiles(e)) e.preventDefault(); });
    }
  }

  const shareOf = (path) => (fsSys ? undefined : (S.share && S.share.items || []).find((x) => x.path === path));
  function shareBtn(item, path) {
    const sh = shareOf(path);
    return h("button", { type: "button", class: "ib" + (sh ? " shared" : ""),
      title: sh ? "Paylaşım bilgileri" : "WebDAV ile paylaş",
      "aria-label": sh ? `${item.name} paylaşım bilgileri` : `${item.name} ögesini paylaş`,
      onclick: () => (sh ? openShareInfo(sh, false) : openShareCreate(item, path)) }, svg("share"));
  }
  function shareChip(path) {
    const sh = shareOf(path);
    return sh ? h("span", { class: "shchip", title: sh.url }, svg("share"), sharesPage.stateText(sh)) : null;
  }

  function fsTile(item) {
    const dir = item.type === "dir", here = pathText(fsPath.concat(item.name)), on = fsSel.has(item.name), sh = shareOf(here);
    const sub = dir ? `${item.count == null ? "?" : item.count} öge` : bytes(item.size);
    if (fsRename === item.name) {
      return h("div", { class: "fx-item on" }, itemArt(item),
        h("input", { type: "text", id: "rn-name", class: "inline-input fx-rename", value: item.name, maxlength: "255", autocomplete: "off", spellcheck: "false",
          "aria-label": "Yeni ad",
          onkeydown: (e) => {
            if (e.key === "Escape") { fsRename = null; renderFs(); }
            if (e.key === "Enter") { e.preventDefault(); doRename(item, e.target.value.trim()); }
          },
          onblur: (e) => doRename(item, e.target.value.trim()) }));
    }
    return h("button", { type: "button", class: "fx-item" + (on ? " on" : ""), "data-item": item.name, "aria-pressed": on ? "true" : "false",
      "aria-label": `${item.name}, ${dir ? "klasör" : "dosya"}, ${sub}`, title: item.name,
      onclick: (e) => pickItem(item, e),
      onkeydown: (e) => { if (e.key === "Escape") clearSel(); } },
      itemArt(item), sh ? h("span", { class: "fx-badge", title: "Paylaşılıyor" }, svg("share")) : null,
      h("span", { class: "fx-name" }, item.name), h("span", { class: "fx-sub" }, sub));
  }
  function newFolderTile() {
    return h("div", { class: "fx-item on" }, folderArt(),
      h("input", { type: "text", id: "nf-name", class: "inline-input fx-rename", maxlength: "255", autocomplete: "off", spellcheck: "false",
        placeholder: "klasör adı", "aria-label": "Yeni klasör adı",
        onkeydown: (e) => {
          if (e.key === "Escape") { fsAdding = false; renderFs(); }
          if (e.key === "Enter") { e.preventDefault(); createFolder(e.target.value.trim()); }
        } }));
  }
  function fsRow(item) {
    const kind = kindOf(item), dir = item.type === "dir";
    const name = fsRename === item.name
      ? h("span", { class: "fname" }, h("span", { class: `ticon t-${kind}` }, svg(dir ? "folder" : kind)),
        h("input", { type: "text", id: "rn-name", class: "inline-input", value: item.name, maxlength: "255", autocomplete: "off", spellcheck: "false",
          "aria-label": "Yeni ad",
          onkeydown: (e) => {
            if (e.key === "Escape") { fsRename = null; renderFs(); }
            if (e.key === "Enter") { e.preventDefault(); doRename(item, e.target.value.trim()); }
          },
          onblur: (e) => doRename(item, e.target.value.trim()) }))
      : h("button", { type: "button", class: "fname", onclick: (e) => (fsPicking ? toggleSel(item.name, e.shiftKey) : dir ? fsGo(fsPath.concat(item.name)) : isText(item) ? openText(item) : download(item)) },
        h("span", { class: `ticon t-${kind}` }, svg(dir ? "folder" : kind)),
        h("span", null, h("strong", null, item.name, shareChip(pathText(fsPath.concat(item.name)))),
          h("small", null, dir ? `${item.count == null ? "?" : item.count} öge` : isText(item) ? "metin dosyası" : "")));
    const here = pathText(fsPath.concat(item.name));
    const on = fsSel.has(item.name);
    // Bir paketin yazdığı klasör seçilmez, paylaşılmaz: süren indirme bozulmasın.
    const locked = inTemp(here) || inTemp(pathText(fsPath));
    return h("div", { class: "tr" + (on ? " on" : "") + (on && fsSel.size === 1 ? " focused" : ""), "data-item": item.name },
      h("span", { class: "c-sel" },
        locked ? null : h("button", { type: "button", class: "chk" + (on ? " on" : ""), role: "checkbox", "aria-checked": on ? "true" : "false",
          "aria-label": `${item.name} seç`, onclick: (e) => toggleSel(item.name, e.shiftKey) }, on ? svg("check") : null)),
      name,
      h("span", { class: "c-size" }, bytes(item.size)),
      h("span", { class: "c-date" }, since(item.mtime)),
      h("span", { class: "acts" },
        h("button", { type: "button", class: "btn btn-sm btn-quiet fx-info", "aria-label": `${item.name} ayrıntıları`,
          onclick: () => { fsSel = new Set([item.name]); fsLast = item.name; renderRows(); renderDetail(); } }, "Ayrıntılar"),
        fsSys || inTemp(here) || inTemp(pathText(fsPath)) ? null : shareBtn(item, here),
        dir ? null : h("button", { type: "button", class: "ib", "aria-label": "İndir", title: "İndir", onclick: () => download(item) }, svg("download")),
        h("button", { type: "button", class: "ib", "aria-label": "Yeniden adlandır", title: "Yeniden adlandır", onclick: () => { fsRename = item.name; renderFs(); const i = $("rn-name"); if (i) { i.focus(); i.select(); } } }, svg("pencil")),
        h("button", { type: "button", class: "ib", "aria-label": "Taşı", title: "Taşı", onclick: () => openMove(item) }, svg("move")),
        h("button", { type: "button", class: "ib del", "aria-label": fsSys ? "Kalıcı sil" : "Çöpe taşı", title: fsSys ? "Kalıcı sil" : "Çöpe taşı",
          onclick: () => askRemove(item) }, svg("trash"))));
  }

  function newFolderRow() {
    const input = h("input", { type: "text", id: "nf-name", class: "inline-input", maxlength: "255", autocomplete: "off", spellcheck: "false",
      placeholder: "klasör adı", "aria-label": "Yeni klasör adı",
      onkeydown: (e) => {
        if (e.key === "Escape") { fsAdding = false; renderFs(); }
        if (e.key === "Enter") { e.preventDefault(); createFolder(e.target.value.trim()); }
      } });
    return h("div", { class: "tr" },
      h("span", { class: "c-sel" }),
      h("span", { class: "fname" }, h("span", { class: "ticon t-dir" }, svg("folder")), input),
      h("span", { class: "c-size" }, "—"), h("span", { class: "c-date" }, "—"),
      h("span", { class: "acts" }, h("button", { type: "button", class: "btn btn-quiet btn-sm", onclick: () => { fsAdding = false; renderFs(); } }, "Vazgeç")));
  }
  function createFolder(name) {
    if (!name) { fsAdding = false; renderFs(); return; }
    post(fsApi("/api/mkdir"), { path: pathText(fsPath), name })
      .then(() => { fsAdding = false; return loadFs(); })
      .then(() => toast(`“${name}” klasörü oluşturuldu.`))
      .catch(fail);
  }
  function doRename(item, to) {
    if (fsRename !== item.name) return;
    fsRename = null;
    if (!to || to === item.name) { renderFs(); return; }
    post(fsApi("/api/rename"), { path: pathText(fsPath), name: item.name, to })
      .then(() => loadFs()).then(() => toast(`“${item.name}” → “${to}”`)).catch((e) => { fail(e); renderFs(); });
  }
  function download(item) {
    const a = h("a", { href: fsApi(`/api/download?path=${enc(pathText(fsPath.concat(item.name)))}`), download: item.name });
    document.body.append(a);
    a.click();
    a.remove();
  }
  /* Tek satırdan da seçim çubuğundan da çağrılır (DD-145). */
  const asList = (x) => (Array.isArray(x) ? x : [x]);
  const listLabel = (items) => (items.length === 1 ? `“${items[0].name}”` : `${items.length} öge`);
  const askRemove = (what) => (fsSys ? askDelete(what) : askTrash(what));
  // DD-235: the system view has no trash. One item is confirmed by typing its name, several by "onayla".
  function askDelete(what) {
    const items = asList(what), word = items.length === 1 ? items[0].name : "onayla";
    ask({
      title: items.length === 1 ? "Kalıcı silinsin mi?" : `${items.length} öge kalıcı silinsin mi?`,
      sub: `${fsHere()}${items.length === 1 ? (fsPath.length ? "/" : "") + items[0].name : ""}`, word, danger: true,
      items: [["lock", "Geri alınamaz; Sistem görünümünde çöp yoktur."], ["server", "Root olarak silinir; sistem dosyaları da silinebilir."]],
      go: "Kalıcı sil",
      onOk: () => post("/api/sistem/delete", { path: pathText(fsPath), names: items.map((i) => i.name), confirm: word })
        .then(() => { fsSel.clear(); return Promise.all([loadFs(), loadSysState()]); })
        .then(() => toast(`${listLabel(items)} kalıcı silindi.`)).catch((e) => { fail(e); loadFs(); }),
    });
  }
  function askTrash(what) {
    const items = asList(what);
    ask({
      title: items.length === 1 ? "Çöpe taşınsın mı?" : `${items.length} öge çöpe taşınsın mı?`,
      sub: items.length === 1 ? items[0].name : "", compact: true,
      go: "Çöpe taşı",
      onOk: () => post("/api/trash", { path: pathText(fsPath), names: items.map((i) => i.name) })
        .then(() => { fsSel.clear(); return Promise.all([loadFs(), loadFsState()]); })
        .then(() => toast(`${listLabel(items)} çöpe taşındı.`)).catch(fail),
    });
  }

  /* taşıma penceresi: hedef klasör ağacı */
  let MV = null;
  function openMove(what) {
    MV = { items: asList(what), dest: [], dirs: null };
    renderMove();
    $("sh").showModal();
    loadMoveDirs([]);
  }
  function loadMoveDirs(parts) {
    return api(fsApi(`/api/list?path=${enc(pathText(parts))}&dirs=1`)).then((r) => {
      MV.dirs = r.entries.map((e) => e.name).sort((a, b) => a.localeCompare(b, "tr"));
      renderMove();
    }).catch(fail);
  }
  function renderMove() {
    const items = MV.items, same = pathText(MV.dest) === pathText(fsPath);
    const size = items.reduce((tot, i) => tot + (i.size || 0), 0);
    const crumbs = h("ol", { class: "crumbs" },
      h("li", null, h("button", { type: "button", class: "crumb root" + (MV.dest.length ? "" : " cur"), onclick: () => { MV.dest = []; MV.dirs = null; renderMove(); loadMoveDirs([]); } }, fsRoot())),
      ...MV.dest.map((part, i) => h("li", null, h("button", { type: "button", class: "crumb" + (i === MV.dest.length - 1 ? " cur" : ""),
        onclick: () => { MV.dest = MV.dest.slice(0, i + 1); MV.dirs = null; renderMove(); loadMoveDirs(MV.dest); } }, part))));
    $("sh-body").replaceChildren(
      shHead(`${listLabel(items)} taşı`, `${fsHere()} · ${bytes(size)}`, "move"),
      h("div", { class: "pathfield" },
        h("button", { type: "button", class: "pf-btn", title: "Üst klasör", "aria-label": "Üst klasör", disabled: !MV.dest.length,
          onclick: () => { MV.dest = MV.dest.slice(0, -1); MV.dirs = null; renderMove(); loadMoveDirs(MV.dest); } }, svg("up")),
        h("span", { class: "pf-sep" }), h("nav", { class: "pf-crumbs", "aria-label": "Hedef" }, crumbs)),
      h("div", { class: "table fs-t movelist" },
        ...(MV.dirs == null ? [h("div", { class: "empty-row" }, h("span", null, "Yükleniyor…"))]
          : MV.dirs.length ? MV.dirs.map((name) => h("div", { class: "tr" },
            h("button", { type: "button", class: "fname", onclick: () => { MV.dest = MV.dest.concat(name); MV.dirs = null; renderMove(); loadMoveDirs(MV.dest); } },
              h("span", { class: "ticon t-dir" }, svg("folder")), h("span", null, h("strong", null, name)))))
            : [h("div", { class: "empty-row" }, h("span", null, "Bu klasörde alt klasör yok; buraya taşıyabilirsiniz."))])),
      h("div", { class: "infoline-s" }, svg("info"), h("span", null, "Aynı diskte taşıma anında biter; dosya kopyalanmaz. Aynı adlı bir öge varsa taşıma yapılmaz.")),
      h("div", { class: "dlg-foot" },
        h("button", { type: "button", class: "btn btn-quiet", onclick: shClose }, "Vazgeç"),
        h("button", { type: "button", class: "btn btn-primary", disabled: same, onclick: doMove },
          `Buraya taşı: ${fsSys ? "/" + MV.dest.join("/") : [fsRoot(), ...MV.dest].join("/")}`)));
  }
  function doMove() {
    const items = MV.items, dest = MV.dest;
    post(fsApi("/api/move"), { path: pathText(fsPath), names: items.map((i) => i.name), to: pathText(dest) })
      .then(() => { shClose(); fsSel.clear(); return loadFs(); })
      .then(() => toast(`${listLabel(items)} taşındı → ${fsSys ? "/" + dest.join("/") : [fsRoot(), ...dest].join("/")}`))
      .catch(fail);
  }

  /* metin görüntüleyici */
  function openText(item, encName) {
    api(fsApi(`/api/text?path=${enc(pathText(fsPath.concat(item.name)))}&enc=${enc(encName || "auto")}`)).then((r) => {
      const pre = h("pre", { class: "textview", tabindex: "0" }, r.text);
      $("sh-body").replaceChildren(
        shHead(item.name, `${fsHere()} · ${bytes(item.size)} · ${r.encoding}`, "text"),
        r.truncated ? h("div", { class: "infoline-s" }, svg("info"), h("span", null, "Dosya büyük: yalnız ilk bölümü gösteriliyor.")) : null,
        h("div", { class: "field" },
          h("label", { for: "tv-enc" }, "Kodlama"),
          h("select", { id: "tv-enc", onchange: (e) => openText(item, e.target.value) },
            ...[["auto", "Otomatik"], ["utf-8", "UTF-8"], ["cp1254", "Türkçe (Windows-1254)"], ["cp437", "DOS (CP437)"]].map(([v, label]) =>
              h("option", { value: v, selected: (encName || "auto") === v }, label)))),
        pre,
        h("div", { class: "dlg-foot" },
          h("button", { type: "button", class: "btn btn-quiet", onclick: () => download(item) }, svg("download"), "İndir"),
          h("button", { type: "button", class: "btn btn-primary", onclick: shClose }, "Kapat")));
      if (!$("sh").open) $("sh").showModal();
    }).catch(fail);
  }

  /* hesap satırları ve kopyalama (paket sayfalarının hesap kartları, klasör paylaşım adresleri) */
  const credRow = (k, v, acts, plain, cls) => h("div", { class: "cred-row" + (cls ? ` ${cls}` : "") }, h("span", { class: "k" }, k),
    h("span", { class: "v" + (plain ? " plain" : "") }, v), h("span", { class: "cred-acts" }, acts));
  // Konsol düz HTTP'den açılır: navigator.clipboard orada çalışmaz, eski yöntemle kopyalanır.
  async function copyText(text) {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
        return true;
      }
    } catch (e) { /* aşağıdaki eski yöntem denenir */ }
    const ta = h("textarea", { readonly: true, "aria-hidden": "true" });
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.append(ta);
    ta.select();
    let ok = false;
    try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
    ta.remove();
    return ok;
  }
  function copyButton(text, label) {
    const b = h("button", { type: "button", class: "ib", title: `${label} kopyala`, "aria-label": `${label} kopyala`, onclick: async () => {
      if (!(await copyText(text))) { toast("Pano kullanılamadı; değeri seçip kopyalayın."); return; }
      b.replaceChildren(svg("check"));
      setTimeout(() => b.replaceChildren(svg("copy")), 1200);
    } }, svg("copy"));
    return b;
  }
  const sharesPage = window.createSharesPage({
    h, svg, post, toast, fail, copyButton, root: fsRoot, getShares: () => S.share,
    setShares: (data) => { S.share = data; renderFs(); },
    showDialog: (title, content) => { $("sh-body").replaceChildren(shHead(title, "Ortak klasör ve hesap · bağımsız Tailscale / WAN bağlantıları", "share"), content); if (!$("sh").open) $("sh").showModal(); },
    closeDialog: shClose, ask,
  });
  $("sh").addEventListener("close", () => { const pw = $("dav-password"); if (pw) pw.value = ""; });
  const archiveTools = window.createArchiveTools({h, api, post, toast, fail, root:fsRoot, downloads:() => S.fs?.downloads,
    refresh:() => { loadFsState(); if (current === "dosyalar" && fsView === "files") loadFs(); },
    showDialog:(title, content) => { $("sh-body").replaceChildren(shHead(title, "", "box"), content); if (!$("sh").open) $("sh").showModal(); },
    closeDialog:shClose});
  const renderShareList = (body) => sharesPage.list(body);
  const openShareCreate = (item, path) => sharesPage.create(item, path);
  const openShareInfo = (sh) => sharesPage.edit(sh);
  // DD-232: the right column's detail: the open folder (nothing selected), one item, or the selection;
  // every file action lives here (the floating selection dock and the per-row detail pane are gone).
  function renderDetail() {
    const box = $("fs-detail");
    if (!box) return;
    box.hidden = fsView !== "files" || !fsList;
    if (box.hidden) { box.replaceChildren(); return; }
    const sel = selItems();
    // DD-244: the actions are words (the icon is dropped on a desktop-width screen); the name is also the
    // accessible name and tooltip.
    const action = (label, icon, fn, attrs = {}) => h("button", { type: "button", class: "btn btn-sm btn-quiet" + (attrs.danger ? " fx-danger" : ""),
      disabled: !!attrs.disabled, "aria-label": label, title: attrs.title || label, "data-act": attrs.act || null, onclick: fn },
      svg(icon), h("span", { class: "fx-act-label" }, label));
    // DD-244: under the name, one line: what it is, its size, where it is and when it changed (and a shared
    // folder's open connections); the whole line is the tooltip when it is cut.
    const head = (art, title, parts) => {
      const line = parts.filter(Boolean);
      return h("div", { class: "fx-head" }, h("span", { class: "fx-preview" }, art), h("h2", { id: "fs-detail-title" }, title),
        h("small", { class: "fx-line", title: line.map((p) => (typeof p === "string" ? p : p.textContent)).join(" · ") },
          ...line.flatMap((p, i) => (i ? [" · ", p] : [p]))));
    };
    const all = fsPicking ? action("Tümünü seç", "check", selectAll, { act: "tumu" }) : null;
    if (!sel.length) {
      const shown = fsShown(), name = fsPath.length ? fsPath[fsPath.length - 1] : fsSys ? "Sistem" : "Sunucu";
      box.replaceChildren(head(folderArt(), name, [fsHere(), `${shown.length} öge`, bytes(shown.reduce((t, e) => t + (e.size || 0), 0))]),
        h("div", { class: "fx-acts" }, all,
          action("Yeni klasör", "plus", startNewFolder, { act: "yeni" }),
          action("Yükle", "upload", () => $("fs-file")?.click(), { act: "yukle" })));
      return;
    }
    if (sel.length > 1) {
      const dirs = sel.filter((i) => i.type === "dir").length, files = sel.length - dirs;
      const kinds = [dirs ? `${dirs} klasör` : "", files ? `${files} dosya` : ""].filter(Boolean).join(", ");
      box.replaceChildren(head(stackArt(sel.length), `${sel.length} öge seçili`, [kinds, bytes(sel.reduce((t, e) => t + (e.size || 0), 0)), fsHere()]),
        h("div", { class: "fx-acts" }, all,
          action("İndir", "download", () => sel.forEach((i) => i.type !== "dir" && download(i)), { disabled: !files, act: "indir" }),
          action("Taşı", "move", () => openMove(sel), { act: "tasi" }),
          fsSys ? null : action("Arşiv oluştur", "box", () => archiveTools.open("zip", pathText(fsPath), sel), { act: "arsiv" }),
          fsSys ? null : action("Arşivi aç", "boxOpen", () => {}, { disabled: true, title: "Tek bir arşiv seçin", act: "ac-arsiv" }),
          fsSys ? null : action("Paylaş", "share", () => {}, { disabled: true, title: "Paylaşım tek tek verilir", act: "paylas" }),
          fsSys ? action("Kalıcı sil", "trash", () => askDelete(sel), { danger: true, act: "sil" })
            : action("Çöpe at", "trash", () => askTrash(sel), { danger: true, act: "cop" }),
          action("Seçimi bırak", "close", clearSel, { act: "birak" })));
      return;
    }
    const item = sel[0], path = pathText(fsPath.concat(item.name)), sh = shareOf(path), directory = item.type === "dir";
    const eligible = !fsSys && directory && !inTemp(path) && !protectedList().some((p) => p.path.startsWith(path + "/")) && !path.split("/").some((p) => p.startsWith("."));
    const canExtract = !directory && archiveTools.canExtract(item.name), locked = inTemp(path);
    const type = directory ? "Klasör" : isText(item) ? "Metin dosyası" : extOf(item.name) ? `${extOf(item.name)} dosyası` : "Dosya";
    const share = sh ? sharesPage.brief(sh) : null;
    box.replaceChildren(
      head(itemArt(item), item.name, [type, directory ? (item.count ?? "?") + " öge" : bytes(item.size), fsHere(), since(item.mtime),
        locked ? `Yazan: ${protectedOwner(path)}` : "",
        // DD-237: the full share cards and the access note live on Paylaşımlar.
        share ? h("span", { class: "fx-shared" + (share.on ? " on" : "") }, share.text)
          : directory && !eligible && !fsSys ? h("span", { title: "Geçici/iç alan içeren klasör paylaşılmaz. Bir alt klasör seçin." }, "Paylaşılamaz") : ""]),
      h("div", { class: "fx-acts" }, all,
        directory ? action("Klasörü aç", "folder", () => fsGo(fsPath.concat(item.name)), { act: "ac" })
          : action("İndir", "download", () => download(item), { act: "indir" }),
        action("Yeniden adlandır", "pencil", () => { fsRename = item.name; renderRows(); const inp = $("rn-name"); if (inp) { inp.focus(); inp.select(); } }, { act: "adlandir" }),
        action("Taşı", "move", () => openMove(item), { act: "tasi" }),
        locked || fsSys ? null : action("Arşiv oluştur", "box", () => archiveTools.open("zip", pathText(fsPath), [item]), { act: "arsiv" }),
        canExtract && !locked && !fsSys ? action("Arşivi aç", "boxOpen", () => archiveTools.open("unzip", pathText(fsPath), [item]), { act: "ac-arsiv" }) : null,
        eligible && !sh ? action("Paylaş", "share", () => openShareCreate(item, path), { act: "paylas" }) : null,
        sh ? action("Paylaşımı yönet", "sliders", () => openShareInfo(sh), { act: "paylasim-yonet" }) : null,
        sh ? action("Paylaşımı kaldır", "trash", () => sharesPage.remove(sh), { act: "paylasim-kaldir" }) : null,
        fsSys ? action("Kalıcı sil", "trash", () => askDelete(item), { danger: true, act: "sil" })
          : action("Çöpe at", "trash", () => askTrash(item), { danger: true, act: "cop" })));
  }

  /* çöp */
  function renderTrashList(body) {
    if (fsTrash == null) { body.append(h("p", { class: "hint-s" }, "Yükleniyor…")); return; }
    if (!fsTrash.length) {
      body.append(h("div", { class: "table" }, h("div", { class: "empty-row" }, h("strong", null, "Çöp boş"),
        h("span", null, "Silinen dosyalar burada görünür ve geri yüklenebilir."))));
      return;
    }
    body.append(h("div", { class: "table fs-t trash-t" },
      h("div", { class: "tr head" }, h("span", null, "Ad"), h("span", { class: "c-size" }, "Boyut"), h("span", { class: "c-date" }, "Silinme"), h("span", null, "")),
      ...fsTrash.map((t) => {
        const kind = t.type === "dir" ? "dir" : kindOf(t);
        return h("div", { class: "tr" },
          h("span", { class: "fname plain" }, h("span", { class: `ticon t-${kind}` }, svg(kind === "dir" ? "folder" : kind)),
            h("span", null, h("strong", null, t.name), h("small", null, `Nereden: ${fsRoot()}${t.from ? "/" + t.from : ""}`))),
          h("span", { class: "c-size" }, bytes(t.size)),
          h("span", { class: "c-date" }, since(t.deleted || t.mtime)),
          h("span", { class: "acts" },
            h("button", { type: "button", class: "btn btn-quiet btn-sm", onclick: () => restore(t) }, svg("restore"), "Geri yükle"),
            h("button", { type: "button", class: "ib", title: "Kalıcı sil", "aria-label": "Kalıcı sil", onclick: () => askPurge(t) }, svg("trash"))));
      })));
    const total = fsTrash.reduce((sum, t) => sum + (t.size || 0), 0);
    body.append(h("button", { type: "button", class: "addrow danger", onclick: askEmptyTrash },
      h("span", { class: "plus" }, svg("trash")),
      h("span", null, h("strong", null, "Çöpü boşalt"), h("small", null, `${fsTrash.length} öge · ${bytes(total)} kalıcı silinir; geri alınamaz`))));
  }
  function restore(t) {
    post("/api/trash/restore", { ids: [t.id] })
      .then(() => Promise.all([loadTrash(), loadFsState(), fsView === "files" ? loadFs() : null]))
      .then(() => toast(`Geri yüklendi: ${t.name}`)).catch(fail);
  }
  function askPurge(t) {
    ask({
      title: `“${t.name}” kalıcı silinsin mi?`, sub: `${bytes(t.size)}`, danger: true,
      items: [["disk", `${bytes(t.size)} disk alanı boşalır.`], ["lock", "Geri alınamaz."]],
      go: "Kalıcı sil",
      onOk: () => post("/api/trash/purge", { ids: [t.id] })
        .then(() => Promise.all([loadTrash(), loadFsState()]))
        .then(() => toast(`“${t.name}” kalıcı silindi.`)).catch(fail),
    });
  }
  function askEmptyTrash() {
    const total = fsTrash.reduce((sum, t) => sum + (t.size || 0), 0);
    ask({
      title: "Çöp boşaltılsın mı?", sub: `${fsTrash.length} öge · ${bytes(total)}`, word: true, danger: true,
      items: [
        ["trash", `${fsTrash.length} öge kalıcı silinir.`],
        ["disk", `${bytes(total)} disk alanı boşalır.`],
        ["lock", "Geri alınamaz."],
      ],
      go: "Çöpü boşalt",
      onOk: () => post("/api/trash/empty", { confirm: "onayla" })
        .then((r) => Promise.all([loadTrash(), loadFsState()]).then(() => toast(`${r.purged} öge kalıcı silindi.`))).catch(fail),
    });
  }

  /* ---------- Günlük ---------- */
  let logFilter = "all";
  function renderLog() {
    // Filter chips for the kinds present; a kind no event carries (an absent package) is not offered.
    const present = new Set(S.actions.map(evKind));
    const labels = Object.assign({}, EVLABEL);
    present.forEach((k) => { if (!labels[k]) labels[k] = evLabel(k); });
    const chips = [["all", "Tümü"], ...Object.entries(labels).filter(([k]) => present.has(k) || k === logFilter)];
    $("log-filter").replaceChildren(...chips.map(([k, label]) =>
      h("button", { type: "button", class: "fchip", "aria-pressed": logFilter === k, onclick: () => { logFilter = k; renderLog(); } }, label)));
    const list = S.actions.filter((e) => logFilter === "all" || evKind(e) === logFilter);
    $("log-table").replaceChildren(...(list.length ? list.map((e) => evRow(e, true))
      : [h("div", { class: "empty-row" }, h("strong", null, "Kayıt yok"), h("span", null, "Konsol'dan yapılan değişiklikler burada görünür."))]));
  }

  /* ---------- Modüller (DD-148, DD-200) ---------- */
  // Katalog ve her paketin App Store metinleri sunucudan gelir (master-modul liste + paketin
  // konsol.json'u); burada hiçbir uygulama adı yazılı değildir. Metinler yalnız metin düğümü olur.
  const ROUTE_RE = /^[a-z]{2,16}$/;
  const SHELL_ROUTES = new Set(["genel", "dosyalar", "moduller", "konteynerler", "ayarlar"]);
  const META_FALLBACK = { alt: "", simge: "box", ton: "t-text", aciklama: "", neler: [], notlar: [], kaldir: {}, durdur_notu: "", gunluk_kaynak: "", sayfa: {}, gunluk: {} };
  const pairs = (v) => (Array.isArray(v) ? v.filter((x) => Array.isArray(x) && x.length === 2 && typeof x[1] === "string").map(([ic, t]) => [ICON[ic] ? ic : "info", t]) : []);
  function metaOf(id) {
    const m = (MODS || []).find((x) => x.id === id);
    const k = Object.assign({}, META_FALLBACK, m && m.konsol && typeof m.konsol === "object" ? m.konsol : {});
    const text = (v) => (typeof v === "string" ? v : "");
    const rm = k.kaldir && typeof k.kaldir === "object" ? k.kaldir : {};
    const page = k.sayfa && typeof k.sayfa === "object" ? k.sayfa : {};
    return {
      name: text(k.ad) || id, sub: text(k.alt), icon: ICON[k.simge] ? k.simge : "box", tone: /^t-[a-z]+$/.test(k.ton) ? k.ton : "t-text",
      desc: text(k.aciklama), will: pairs(k.neler), facts: Array.isArray(k.notlar) ? k.notlar.filter((t) => typeof t === "string") : [],
      removeWhat: pairs(rm.neler), removeLabel: text(rm.veri_etiket), removeKeep: text(rm.veri_kalir), removeDrop: text(rm.veri_silinir),
      stopNote: text(k.durdur_notu), logSrc: text(k.gunluk_kaynak),
      rota: ROUTE_RE.test(text(page.rota)) && !SHELL_ROUTES.has(page.rota) ? page.rota : "", baslik: text(page.baslik), ustbilgi: text(page.ustbilgi), detay: text(page.detay),
      gunluk: k.gunluk && typeof k.gunluk === "object" ? k.gunluk : {},
    };
  }
  const modName = (detail) => metaOf(String(detail || "").split(" ")[0]).name;
  // DD-209: "konteyner" = tabandaki Podman'da çalışan uygulama; durumu host gibi birimin canlılığıdır.
  const RUNTIME = { host: ["host", "server", "Host"], konsol: ["konsol", "gauge", "Konsol"], konteyner: ["konteyner", "box", "Konteyner"] };
  const unitRuntime = (m) => m.runtime === "host" || m.runtime === "konteyner";
  let MODS = null, modTimer = null, modMisses = 0;
  /* DD-210: a package may declare a form (konsol.json "form"): the App Store's Kur asks for it before the
     install and the overview's settings action edits the same fields through the package's own API.
     Field types are generic (text, password, folder); the shell names no application. */
  const FORM_TYPES = new Set(["metin", "parola", "klasor"]);
  function formOf(id) {
    const m = (MODS || []).find((x) => x.id === id), f = m && m.konsol && m.konsol.form;
    if (!f || typeof f !== "object" || !Array.isArray(f.alanlar)) return null;
    const text = (v) => (typeof v === "string" ? v : "");
    const num = (v) => (Number.isInteger(v) && v > 0 && v <= 4096 ? v : null);
    const route = (v) => (typeof v === "string" && /^\/[a-z]{1,16}$/.test(v) ? v : "");
    const fields = f.alanlar.filter((a) => a && typeof a === "object" && /^[a-z_]{1,32}$/.test(a.ad) && FORM_TYPES.has(a.tur))
      .map((a) => ({ ad: a.ad, tur: a.tur, etiket: text(a.etiket) || a.ad, varsayilan: text(a.varsayilan), desen: text(a.desen),
        enAz: num(a.en_az), enCok: num(a.en_cok), ipucu: text(a.ipucu), ayarIpucu: text(a.ayar_ipucu) }));
    if (!fields.length) return null;
    return { fields, kurBaslik: text(f.kur_baslik), kurAlt: text(f.kur_alt), kurNot: text(f.kur_not),
      ayarBaslik: text(f.ayar_baslik), ayarAlt: text(f.ayar_alt), ayarNot: text(f.ayar_not), oku: route(f.oku), yaz: route(f.yaz) };
  }
  /* DD-210: an app with a native web interface (its publication's names, DD-195/199) opens there in a new
     tab while it runs: the public name on the public HTTPS address, the tailnet name on the tailnet. No
     name is ever made up here, and the public address never falls back to a private one. */
  const publicAddress = () => location.protocol === "https:";
  function launchUrl(m) {
    if (!m || !m.installed || m.busy || m.state !== "calisiyor" || (unitRuntime(m) && m.live !== "running") || !m.urls) return "";
    const url = publicAddress() ? m.urls.internet : m.urls.tailscale;
    return typeof url === "string" && /^https?:\/\/[^\s"'<>]+$/.test(url) ? url : "";
  }
  const newTab = (url) => (url ? { target: "_blank", rel: "noopener noreferrer" } : {});
  const modOn = (id) => !!((MODS || []).find((m) => m.id === id) || {}).installed;
  // Files is built in; application pages follow the server registry and each package's declaration.
  function appRoutes() {
    const out = {};
    (MODS || []).forEach((m) => {
      const meta = metaOf(m.id);
      if (meta.rota && !out[meta.rota]) out[meta.rota] = { id: m.id, installed: !!m.installed, baslik: meta.baslik || meta.name, ustbilgi: meta.ustbilgi, icon: meta.icon };
    });
    return out;
  }
  const modLogs = {};
  const modLogLoading = new Set();
  let modSelected = null, modRenderKey = "";
  // İstek kabul edilince birim başlar ama ilerleme dosyasında bir an önceki işlemin satırı durur;
  // o arada istenen işlem gösterilir.
  const modPending = {};
  // Sayfanın başlattığı işlem bitince sonucu söyler; parolalar yalnız istenince okunur.
  function modDone(m, want) {
    const meta = metaOf(m.id), p = m.progress || {};
    if (p.step === "hata") { toast(`${meta.name}: ${p.text || "işlem başarısız"}`); return; }
    if (p.step !== "bitti") return;
    if (want === "kur") toast(`${meta.name} kuruldu.`);
    else if (want === "kaldir") toast(`${meta.name} kaldırıldı.`);
    if (want === "kur") CFG = null;
  }
  function loadModules() {
    return api("/api/konsol/moduller").then((r) => {
      MODS = r.items || [];
      modsSettled = true;
      modMisses = 0;
      MODS.forEach((m) => {
        if (!m.installed) delete modLogs[m.id];
        const want = modPending[m.id];
        if (!want) return;
        if (!m.busy) { delete modPending[m.id]; modDone(m, want); return; }
        const p = m.progress;
        if (!p || p.action !== want || p.step === "bitti" || p.step === "hata") m.progress = { action: want, step: "0", total: 0, text: "" };
      });
      ensurePages();
      const owner = appRoutes()[current];
      if (owner && !owner.installed) location.hash = "#/moduller";
      else if (pendingRoute) route();
      if (current === "moduller") renderModules();
      if (current === "genel") renderOverview();
      if (current === "konteynerler") containers.modules();
      if (PAGES[current] && PAGES[current].page.modules) PAGES[current].page.modules(MODS);
      clearTimeout(modTimer);
      if (MODS.some((m) => m.busy)) modTimer = setTimeout(loadModules, 1500);
    }).catch((err) => {
      // The overview waits for the first answer; a failed catalogue has an explicit empty/error state.
      if (!modsSettled) { modsSettled = true; renderOverview(); }
      // DD-207: while an App Store operation runs the backend may restart once (a package's write path);
      // keep following the progress quietly for a few tries instead of dropping it after one miss.
      if (MODS && MODS.some((m) => m.busy) && ++modMisses <= 8) {
        clearTimeout(modTimer);
        modTimer = setTimeout(loadModules, 1500);
        return;
      }
      fail(err);
    });
  }
  function modAct(m, action, veri, body) {
    return modStart(m, action, body || { veri: !!veri }).catch(fail);
  }
  // The request itself; a form that must show the server's refusal (DD-210) catches it on its own.
  function modStart(m, action, body) {
    return post(`/api/konsol/moduller/${enc(m.id)}/${action}`, body)
      .then(() => {
        modPending[m.id] = action;
        // An unchanged poll may retain DOM handlers while replacing the catalogue objects.
        const live = (MODS || []).find(x => x.id === m.id) || m;
        live.busy = true; live.progress = { action, step: "0", total: 0, text: "" };
        renderModules(); return loadModules();
      });
  }
  function modPill(m) {
    if (m.busy) {
      const label = { kur: "Kuruluyor", baslat: "Başlatılıyor", durdur: "Durduruluyor", kaldir: "Kaldırılıyor" }[m.progress && m.progress.action] || "İşleniyor";
      return h("span", { class: "hm warn" }, h("span", { class: "spin", "aria-hidden": "true" }), label);
    }
    if (!m.installed) return h("span", { class: "hm" }, "Kurulu değil");
    if (m.state === "durduruldu") return h("span", { class: "hm idle" }, "Durduruldu");
    if (m.runtime === "konsol") return m.live === "exited" ? h("span", { class: "hm warn" }, "Çalışmıyor")
      : h("span", { class: "hm ok" }, h("span", { class: "dotmark live", "aria-hidden": "true" }), "Kurulu");
    if (unitRuntime(m) && m.live !== "running") return h("span", { class: "hm warn" }, "Çalışmıyor");
    return h("span", { class: "hm ok" }, h("span", { class: "dotmark live", "aria-hidden": "true" }), "Çalışıyor");
  }
  function modRow(m) {
    const meta = metaOf(m.id), p = m.progress || {};
    const disabled = !!m.busy;
    return h("article", { class:"store-row", id:`modc-${m.id}`, "aria-labelledby":`mod-name-${m.id}` },
      h("span", {class:`svc-ico ${meta.tone}`}, svg(meta.icon)),
      h("div", {class:"store-who"}, h("h2", {id:`mod-name-${m.id}`}, meta.name)),
      h("div", {class:"store-state", role:"status"}, modPill(m)),
      h("div", {class:"store-actions"},
        h("button", {type:"button", class:"btn btn-sm btn-quiet", id:`mod-details-${m.id}`,
          "aria-expanded":String(modSelected === m.id), "aria-controls":"mod-detail", onclick:() => {
            modSelected = modSelected === m.id ? null : m.id; renderModules();
          }}, "Ayrıntı"),
        m.installed && launchUrl(m)
          ? h("a", {class:"btn btn-sm btn-primary", id:`mod-open-${m.id}`, href:launchUrl(m), ...newTab(launchUrl(m)),
              "aria-label":`${meta.name} arayüzünü yeni sekmede aç`}, "Aç ↗")
          : m.installed
          ? h("button", {type:"button", class:"btn btn-sm btn-primary", id:`mod-open-${m.id}`, disabled,
              "data-go":meta.rota ? "#/" + meta.rota : "#/moduller"}, "Aç")
          : h("button", {type:"button", class:"btn btn-sm btn-primary", id:`mod-install-${m.id}`, disabled,
              onclick:() => (formOf(m.id) ? appForm(m.id, "kur") : modAct(m, "kur"))}, "Kur")),
      m.busy ? h("p", {class:"store-progress", role:"status"}, p.text || "İşlem sunucuda sürüyor…")
        : p.step === "hata" ? h("p", {class:"store-progress store-error", role:"alert"}, "Son işlem başarısız: " + (p.text || "İşlem tamamlanamadı.")) : null);
  }
  // The stop confirmation with the package's own explanation (App Store details and the overview tile).
  function askStop(m, onOk) {
    const meta = metaOf(m.id);
    ask({title:`${meta.name} durdurulsun mu?`, sub:"Kurulu kalır; istediğinizde başlatırsınız", calm:true, go:"Durdur",
      items:[["pause",meta.stopNote],["info","Açılışta da kapalı kalır; başlatılana kadar çalışmaz."]], onOk});
  }
  function modDetail(m) {
    const meta = metaOf(m.id), p = m.progress || {};
    const [rtCls, rtIcon, rtLabel] = RUNTIME[m.runtime] || RUNTIME.host;
    const kids = [h("div", {class:"store-detail-head"}, h("h2", {id:"mod-detail-title"}, meta.name),
      h("button", {type:"button", class:"btn btn-sm btn-quiet", id:"mod-detail-close", onclick:() => {
        modSelected = null; renderModules(); $("mod-details-" + m.id)?.focus();
      }}, "Kapat")),
      h("p", {class:"mod-desc"}, meta.desc),
      h("div", {class:"mod-facts"}, h("span", {class:`rt-chip ${rtCls}`}, svg(rtIcon), rtLabel), meta.facts.map(t => h("span", null, t))),
      h("ul", {class:"will"}, meta.will.map(([ic,t]) => h("li", null, svg(ic), h("span", null, t))))];
    if (m.busy) {
      // Progress comes from the server; no timer-driven or invented step completion.
      kids.push(h("p", {class:"hint-s"}, p.text || "İşlem sunucuda sürüyor…"),
        h("p", {class:"hint-s"}, "Sayfadan çıkabilirsiniz; işlem sunucuda sürer."));
    }
    if (m.installed) {
      if (meta.detay && meta.rota) kids.push(h("a", {href:"#/" + meta.rota, class:"linkbtn"}, meta.detay));
      const running = m.state === "calisiyor";
      kids.push(h("div", {class:"store-detail-actions"},
        !m.durdurulabilir ? null : h("button", {type:"button", class:"btn btn-sm btn-quiet", id:`mod-service-${m.id}`, disabled:!!m.busy, onclick:() => {
          if (!running) { modAct(m, "baslat"); return; }
          askStop(m, () => modAct(m,"durdur"));
        }}, svg(running ? "pause" : "play"), running ? "Durdur" : "Başlat"),
        h("button", {type:"button", class:"btn btn-sm btn-quiet", id:`mod-log-${m.id}`, disabled:!!m.busy || modLogLoading.has(m.id),
          "aria-expanded":String(modLogs[m.id] != null), "aria-controls":"mod-log-output", onclick:() => {
            if (modLogs[m.id] != null) { delete modLogs[m.id]; renderModules(); return; }
            modLogLoading.add(m.id); renderModules();
            fetch(`/api/konsol/moduller/${enc(m.id)}/gunluk`, {headers:{"X-Konsol":"1"}, cache:"no-store"})
              .then(r => { if (!r.ok) throw new Error(`Günlük okunamadı (HTTP ${r.status}).`); return r.text(); })
              .then(txt => { if (modOn(m.id)) modLogs[m.id] = txt; }).catch(fail)
              .finally(() => { modLogLoading.delete(m.id); renderModules(); });
          }}, svg("list"), modLogLoading.has(m.id) ? "Okunuyor…" : modLogs[m.id] != null ? "Günlüğü gizle" : "Günlük"),
        h("button", {type:"button", class:"btn btn-sm btn-quiet danger-text", id:`mod-remove-${m.id}`,
          disabled:!!m.busy, onclick:() => {
            const box = h("input", {type:"checkbox", id:"mod-veri"});
            ask({title:`${meta.name} kaldırılsın mı?`,
              sub:"Uygulama ve açtığı erişimler kaldırılır",
              go:"Kaldır", danger:true,
              items:[...meta.removeWhat, ["folder","Kullanıcı alanındaki dosyalarınıza dokunulmaz."]],
              extra:h("label", {class:"opt", for:"mod-veri"}, box, h("span", null, meta.removeLabel || "Uygulamanın verisini de sil",
                h("small", null, `${meta.removeDrop} İşaretlemezseniz: ${meta.removeKeep}`))),
              onOk:() => modAct(m, "kaldir", box.checked)});
          }}, svg("trash"), "Kaldır")));
    }
    kids.push(h("div", {id:"mod-log-output", class:"logbox", hidden:modLogs[m.id] == null},
      h("div", {class:"acct-head"}, h("span", null, "Günlük"), h("span", {class:"src"}, meta.logSrc || m.id)),
      h("pre", {id:`mod-log-text-${m.id}`, tabindex:"0"}, modLogs[m.id] || "(boş)")));
    return kids;
  }
  function renderModules() {
    if (!MODS) { $("mod-grid").replaceChildren(h("p", { class: "hint-s" }, "Yükleniyor…")); return; }
    const n = MODS.filter((m) => m.installed).length;
    if ($("mod-sum")) $("mod-sum").textContent = `${n} kurulu · ${MODS.length - n} kurulabilir`;
    const selected = MODS.find(m => m.id === modSelected);
    if (!selected) modSelected = null;
    const key = JSON.stringify([MODS, modSelected, modLogs, [...modLogLoading]]);
    if (key === modRenderKey) return;
    modRenderKey = key;
    const focused = document.activeElement;
    const focusId = focused?.closest("#mod-grid, #mod-detail") ? focused.id : null;
    const focusApp = focused?.closest(".store-row")?.id.replace("modc-", "") || modSelected;
    const pre = $("mod-detail").querySelector("pre");
    const scroll = pre ? [pre.id, pre.scrollTop, pre.scrollLeft] : null;
    $("mod-grid").replaceChildren(...MODS.map(modRow));
    $("mod-detail").hidden = !selected;
    $("mod-detail").replaceChildren(...(selected ? modDetail(selected) : []));
    if (focusId) {
      const target = $(focusId);
      (target && !target.disabled ? target : $("mod-details-" + focusApp))?.focus({preventScroll:true});
    }
    if (scroll && $(scroll[0])) { $(scroll[0]).scrollTop = scroll[1]; $(scroll[0]).scrollLeft = scroll[2]; }
  }

  /* ---------- Uygulama formu (DD-210) ---------- */
  // "kur": the App Store's install form; nothing is sent until a valid submission, and the engine starts
  // only after the package's worker accepted the values. "ayar": the same fields, current values from
  // the package API (never a password), only changed fields sent; a blank password keeps the stored one.
  // The form lives in the shared dialog, outside views the polls redraw, so drafts survive polls/errors.
  // Each call owns the dialog only while its own root node is the dialog's content and the dialog has not
  // closed since: a late answer of an older call (a held install, a slow read) never closes, clears or
  // replaces a newer dialog; it reports through a toast instead.
  function appForm(id, mode) {
    const form = formOf(id), meta = metaOf(id), install = mode === "kur";
    if (!form || (!install && !(form.oku && form.yaz))) return;
    const opener = document.activeElement;
    const root = h("div", { class: "app-form-root" });
    let closed = false;
    const mine = () => !closed && $("sh").open && $("sh-body").contains(root);
    const restoreFocus = () => {
      const back = opener && opener.isConnected ? opener : document.querySelector(install ? `#mod-install-${id}` : `[data-tile="${id}"] [data-act="ayar"]`);
      if (back && !back.disabled) back.focus();
    };
    const title = (install ? form.kurBaslik : form.ayarBaslik) || meta.name;
    const sub = (install ? form.kurAlt : form.ayarAlt) || "";
    root.replaceChildren(shHead(title, sub, install ? meta.icon : "sliders"), h("p", { class: "hint-s" }, "Okunuyor…"));
    $("sh-body").replaceChildren(root);
    if (!$("sh").open) $("sh").showModal();
    $("sh").addEventListener("close", () => {
      const own = $("sh-body").contains(root);
      closed = true;
      root.querySelectorAll("input[type=password]").forEach((i) => { i.value = ""; });
      if (own) restoreFocus();
    }, { once: true });
    if (install) { drawForm({}); return; }
    api(`/api/uygulama/${enc(id)}${form.oku}`).then((now) => {
      if (mine()) drawForm(now && typeof now === "object" ? now : {});
    }).catch((err) => { if (mine()) root.replaceChildren(shHead(title, sub, "sliders"), h("p", { class: "err-s", role: "alert" }, err.message)); });

    function drawForm(now) {
      const initial = {}, inputs = {};
      let busy = false;
      const error = h("p", { class: "err-s", role: "alert", hidden: true });
      const note = h("p", { class: "hint-s", role: "status", hidden: true });
      const submit = h("button", { type: "submit", class: "btn btn-primary" }, install ? "Kur ve başlat" : "Kaydet");
      const rows = form.fields.map((f) => {
        const fid = `app-${f.ad}`;
        if (f.tur === "parola") {
          const attrs = { type: "password", autocomplete: "new-password", required: install, minlength: f.enAz, maxlength: f.enCok };
          const first = h("input", { ...attrs, id: fid, name: f.ad }), second = h("input", { ...attrs, id: fid + "-tekrar", name: f.ad + "-tekrar" });
          inputs[f.ad] = first;
          first.addEventListener("input", () => second.setCustomValidity(""));
          second.addEventListener("input", () => second.setCustomValidity(""));
          const hint = install ? f.ipucu : f.ayarIpucu || f.ipucu;
          if (hint) first.setAttribute("aria-describedby", fid + "-ipucu");
          return [h("div", { class: "app-field" }, h("label", { for: fid }, f.etiket, first), hint ? h("small", { class: "hint-s", id: fid + "-ipucu" }, hint) : null),
            h("label", { for: fid + "-tekrar" }, `${f.etiket} (tekrar)`, second)];
        }
        const value = install ? f.varsayilan : typeof now[f.ad] === "string" ? now[f.ad] : "";
        initial[f.ad] = value;
        if (f.tur === "metin") {
          const input = h("input", { type: "text", id: fid, name: f.ad, value, required: true, maxlength: f.enCok, minlength: f.enAz,
            pattern: f.desen || null, autocomplete: f.ad === "username" ? "username" : "off", autocapitalize: "none", spellcheck: false });
          inputs[f.ad] = input;
          if (f.ipucu) input.setAttribute("aria-describedby", fid + "-ipucu");
          return h("div", { class: "app-field" }, h("label", { for: fid }, f.etiket, input), f.ipucu ? h("small", { class: "hint-s", id: fid + "-ipucu" }, f.ipucu) : null);
        }
        // klasor: chosen from the base's safe folder list (downloads/library, no hidden/share/trash dirs).
        const input = h("input", { type: "text", id: fid, name: f.ad, value, required: true, readonly: true });
        inputs[f.ad] = input;
        const list = h("div", { class: "app-picker", hidden: true });
        const toggle = h("button", { type: "button", class: "btn btn-sm btn-quiet", "aria-expanded": "false", onclick: () => {
          const open = list.hidden;
          list.hidden = !open; toggle.setAttribute("aria-expanded", String(open));
          if (open) browse();
        } }, svg("folder"), "Klasör seç");
        async function browse(at) {
          list.replaceChildren(h("p", { class: "hint-s" }, "Klasörler okunuyor…"));
          try {
            const r = await api("/api/konsol/ayarlar/klasorler" + (at ? "?path=" + enc(at) : ""));
            const items = Array.isArray(r.items) ? r.items : [];
            list.replaceChildren(...[at ? h("div", { class: "app-picker-here" },
              h("button", { type: "button", class: "btn btn-sm btn-quiet", onclick: () => browse() }, svg("back"), "Başlangıç dizinleri"),
              h("code", null, at)) : null,
              ...items.map((x) => h("div", { class: "app-picker-row" },
                h("span", null, h("strong", null, x.path), h("small", null, `${dec((x.free || 0) / GiB, 1)} GB boş`)),
                h("button", { type: "button", class: "btn btn-sm btn-quiet", "aria-label": `${x.path} içine gir`, onclick: () => browse(x.path) }, "İçine gir"),
                h("button", { type: "button", class: "btn btn-sm btn-primary", "aria-label": `${x.path} seç`, onclick: () => {
                  input.value = x.path; list.hidden = true; toggle.setAttribute("aria-expanded", "false"); toggle.focus();
                } }, "Seç"))),
              items.length ? null : h("p", { class: "hint-s" }, "Bu klasörün altında seçilebilir klasör yok.")].filter(Boolean));
          } catch (err) { list.replaceChildren(h("p", { class: "err-s" }, err.message)); }
        }
        if (f.ipucu) input.setAttribute("aria-describedby", fid + "-ipucu");
        return h("div", { class: "app-folder app-field" }, h("label", { for: fid }, f.etiket), h("span", { class: "app-folder-pick" }, input, toggle),
          f.ipucu ? h("small", { class: "hint-s", id: fid + "-ipucu" }, f.ipucu) : null, list);
      }).flat();
      const formEl = h("form", { class: "dav-form app-form", id: `app-form-${id}`, novalidate: false, onsubmit: async (e) => {
        e.preventDefault();
        if (busy) return;
        error.hidden = true; note.hidden = true;
        for (const f of form.fields) {
          if (f.tur !== "parola") continue;
          const a = inputs[f.ad], b = formEl.querySelector(`#app-${f.ad}-tekrar`);
          b.setCustomValidity(a.value === b.value ? "" : "Parolalar aynı değil.");
        }
        if (!formEl.reportValidity()) return;
        const values = {};
        for (const f of form.fields) {
          const v = f.tur === "metin" ? inputs[f.ad].value.trim() : inputs[f.ad].value;
          if (install) values[f.ad] = v;
          else if (f.tur === "parola" ? v !== "" : v !== initial[f.ad]) values[f.ad] = v;
        }
        if (!install && !Object.keys(values).length) { note.textContent = "Değişiklik yok."; note.hidden = false; return; }
        busy = true; submit.disabled = true;
        submit.textContent = install ? "Kuruluyor…" : "Kaydediliyor…";
        try {
          if (install) {
            const m = (MODS || []).find((x) => x.id === id);
            if (!m) throw new Error("Uygulama listesi okunamadı; sayfayı yenileyin.");
            await modStart(m, "kur", { form: values });
            if (mine()) shClose();
            toast(`${meta.name} kuruluyor; ilerleme App Store'da görünür.`);
          } else {
            await post(`/api/uygulama/${enc(id)}${form.yaz}`, values);
            if (mine()) shClose();
            toast(`${meta.name} ayarları kaydedildi.`);
            loadModules();
            const page = PAGES[metaOf(id).rota];
            if (page && page.page.poll && current === metaOf(id).rota) page.page.poll();
          }
        } catch (err) {
          if (mine()) { error.textContent = err.message; error.hidden = false; }
          else toast(`${meta.name}: ${err.message}`);
        } finally {
          Object.keys(values).forEach((k) => { values[k] = ""; });
          busy = false; submit.disabled = false; submit.textContent = install ? "Kur ve başlat" : "Kaydet";
        }
      } },
      ...rows,
      (install ? form.kurNot : form.ayarNot) ? h("p", { class: "hint-s" }, install ? form.kurNot : form.ayarNot) : null,
      error, note,
      h("div", { class: "dav-actions" }, submit, h("button", { type: "button", class: "btn btn-quiet", onclick: shClose }, "Vazgeç")));
      root.replaceChildren(shHead(title, sub, install ? meta.icon : "sliders"), formEl);
      const first = formEl.querySelector("input:not([readonly])");
      if (first && mine()) first.focus();
    }
  }

  /* ---------- Ayarlar (DD-156) ---------- */
  let CFG = null, cfgBusy = null, cfgAgain = false;
  const hhmm = (sec) => new Date(sec * 1000).toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
  // replaceChildren boş öğeyi "null" metni olarak basar: yalnız gerçek öğeler konur.
  const fill = (id, ...kids) => $(id).replaceChildren(...kids.flat(Infinity).filter(Boolean));
  function loadSettings(fresh) {
    // A forced refresh asked for during a load (e.g. right after a save) runs once
    // that load ends; callers awaiting it never draw a reply read before their change.
    if (cfgBusy) { if (fresh === true) cfgAgain = true; return cfgBusy; }
    cfgBusy = api(fresh === true ? "/api/konsol/ayarlar?yenile=1" : "/api/konsol/ayarlar").then((d) => { CFG = d; renderSettings(); }).catch(fail).finally(() => {
      cfgBusy = null;
      if (cfgAgain) { cfgAgain = false; return loadSettings(true); }
    });
    return cfgBusy;
  }
  const srcTag = (source) => source === "base" ? h("span", { class: "tag base first" }, "Temel")
    : h("span", { class: "tag mod first" }, metaOf(source).name);
  function rawBox(title, src, text) {
    return h("details", { class: "raw" },
      h("summary", null, svg("chev"), title, h("span", { class: "src" }, src)),
      h("div", { class: "logbox" },
        h("div", { class: "rawhead" }, h("button", { type: "button", class: "btn btn-sm btn-quiet",
          onclick: async () => toast((await copyText(text)) ? "Kopyalandı." : "Pano kullanılamadı; metni seçip kopyalayın.") },
        svg("copy"), "Kopyala")),
        h("pre", { tabindex: "0" }, text || "(boş)")));
  }

  const isIpPort = (a) => /^\d+\.\d+\.\d+\.\d+:\d+$/.test(a);
  function webDesc(e) {
    // DD-202: a package's public site is "<id>-wan"; its name comes from the package.
    if (e.access === "wan") return (e.source === "panel-wan" ? "Sunucu yönetim paneli · internet girişi"
      : e.source === "paylasim-wan" ? "İnternet üzerinden seçili klasör paylaşımları"
      : metaOf(e.source.replace(/-wan$/, "")).name + " · kendi girişiyle") + " · " + (e.scheme === "https" ? "HTTPS" : "HTTP şifrelemez");
    const extra = isIpPort(e.address) ? " · ad çözmeyen cihazlar için (ör. Infuse)" : "";
    if (e.source === "base") return (e.address.startsWith("panel.") ? "Sunucu yönetim paneli" : "Temel servis") + extra;
    return metaOf(e.source).name + extra;
  }
  function webHop(r, many) {
    const arrow = svg("arrow");
    const path = r.path ? h("code", null, r.path) : many ? h("span", { class: "muted" }, "diğer") : null;
    const what = r.kind === "proxy" ? h("code", null, r.to) : r.kind === "files" ? "sayfa dosyaları"
      : r.kind === "respond" ? `sabit yanıt “${r.to}”` : h("span", null, "→ ", h("code", null, r.to));
    return h("span", { class: "hop" }, path ? [path, arrow] : null, what);
  }
  function paintWeb() {
    const w = CFG.web, names = w.entries.filter((e) => !isIpPort(e.address)).length;
    const rows = w.entries.map((e) => h("div", { class: "tr" },
      h("span", { class: "a" }, e.address, h("small", null, webDesc(e))),
      h("span", { class: "to" }, e.routes.map((r) => webHop(r, e.routes.length > 1))),
      h("span", { class: "who" }, srcTag(e.source === "panel-wan" ? "base" : e.source.replace(/-wan$/, "")), h("span", { class: "tag" }, e.access === "wan" ? "WAN · " + (e.scheme === "https" ? "HTTPS" : "HTTP") : "Tailscale"))));
    fill("cfg-web", 
      h("div", { class: "card-head" }, h("h2", null, svg("globe"), "Web adresleri"),
        h("div", { class: "head-right" }, h("span", { class: "hm" }, `Caddy · ${names} ad, ${w.entries.length - names} IP adresi`))),
      h("div", { class: "table addr-t" }, h("div", { class: "tr head" }, h("span", null, "Adres"), h("span", null, "Nereye gider"), h("span", null, "Kaynak · erişim")), rows),
      rawBox("Ham yapılandırma", "Caddyfile · moduller/*.caddy", w.raw.map((f) => `# ${f.file}\n${f.text.trim()}`).join("\n\n")),
      h("div", { class: "card-foot" }, h("span", null, "Panel'in Tailscale adresi her zaman açıktır. WAN etiketi Ayarlar → Caddy ile açılan internet yayınını gösterir."
        + (w.entries.some(e => e.access === "wan" && e.scheme !== "https") ? " İnternet üzerinden HTTP parola ve dosyaları şifrelemez." : ""))));
  }
  const HEALTH = { ok: ["ok", "Sağlıklı"], warn: ["warn", "Dikkat"], bad: ["bad", "Sorun var"] };
  // DD-245: Sağlık is one row: the overall state and the last check on the left, each check as a dot, its
  // name and its detail beside it (rows wrap on narrow screens).
  function healthCard() {
    const hs = S.health;
    const pill = (status) => h("span", {class:"hm " + HEALTH[status][0]}, HEALTH[status][1]);
    return h("article", {class:"card health-strip"},
      h("div", {class:"card-head"}, h("div", null, h("div", {class:"hs-title"}, h("h2", null, "Sağlık"), hs ? pill(hs.status) : null),
        h("small", {class:"hint-s"}, hs ? `Son denetim ${hhmm(hs.read_at)}` : healthFailed ? "Okunamadı" : "Denetleniyor…"))),
      // DD-246: two rows: the checks split over ceil(n/2) columns; each detail wraps under its name.
      hs ? h("dl", {class:"health-facts", "data-cols": String(Math.min(6, Math.max(2, Math.ceil(hs.checks.length / 2))))}, ...hs.checks.map((c) =>
        h("div", {class:"hc-" + c.status, title: c.detail}, h("dt", null, pill(c.status), c.name), h("dd", null, c.detail))))
        : h("p", {class:"hint-s"}, healthFailed ? "Sağlık bilgisi okunamadı; bağlantıyı kontrol edin." : "Sağlık denetleniyor…"));
  }
  /* DD-241: the repair log: master-onar's lines (Konsol, SSH, the hourly firewall check's findings) and the
     address refresh's (boot, nightly 03–04, Caddy failures) for the last 72 hours or the last week. */
  function openRepairLog(span) {
    const out = h("pre", { class: "repair-log", id: "repair-log", tabindex: "0" }, "Okunuyor…");
    const pick = (id, label) => h("button", { type: "button", class: "fchip", "aria-pressed": span === id ? "true" : "false", onclick: () => openRepairLog(id) }, label);
    shShow("Denetim ve onarım günlüğü", span === "7g" ? "Son 1 hafta" : "Son 72 saat", "text",
      h("div", { class: "repair-log-tools", role: "group", "aria-label": "Süre" }, pick("72s", "72 saat"), pick("7g", "1 hafta")), out);
    api("/api/konsol/onarim/gunluk?sure=" + span, { text: true }).then((text) => {
      if (!out.isConnected) return;
      out.textContent = text.trim() || "Bu sürede kayıt yok.";
      out.scrollTop = out.scrollHeight;
    }).catch((e) => { if (out.isConnected) out.textContent = e.message || String(e); });
  }
  /* DD-239: "Denetle ve onar" runs master-onar as its own unit; there is no 5-minute background loop.
     Over SSH the same run is: sudo master-onar (only checking: --denetle). */
  const REPAIR_MARK = { ok: ["ok", "✓"], onarildi: ["warn", "↻"], sorun: ["warn", "!"], hata: ["bad", "✗"], atlandi: ["", "–"], calisiyor: ["", "…"] };
  function repairBox() {
    const rp = S.repair, rep = rp && rp.rapor, running = !!(rp && rp.calisiyor);
    const locked = rp && rp.baslatilabilir === false, off = !rp || !rp.kurulu || running || locked;
    const title = locked ? "Onarım yalnız Tailscale adresinden başlatılır" : rp && !rp.kurulu ? "Kurulumu bir kez yeniden çalıştırın" : null;
    const when = (sec) => new Date(sec * 1000).toLocaleString("tr-TR", { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" });
    const via = rep && rep.kaynak === "terminal" ? " · SSH" : "";
    const head = running ? "Denetim sürüyor…" : rep ? `Son ${rep.kip === "denetle" ? "denetim" : "onarım"}: ${when(rep.bitis || rep.baslangic)}${via} · ${rep.durum === "tamam" ? "tamam" : rep.yarida ? "yarıda kaldı" : "sorun var"}` : "Henüz denetim yapılmadı";
    return h("section", { class: "repair", "aria-live": "polite", "aria-busy": running ? "true" : "false" },
      h("div", { class: "repair-head" }, h("div", null, h("h3", null, "Denetle ve onar"), h("small", null, head)),
        h("div", { class: "repair-acts" },
          h("button", { type: "button", class: "btn btn-sm btn-quiet", onclick: () => openRepairLog("72s") }, svg("text"), "Günlük"),
          h("button", { type: "button", class: "btn btn-sm btn-quiet", disabled: off, title, onclick: () => startRepair("denetle") }, svg("search"), "Denetle"),
          h("button", { type: "button", class: "btn btn-sm btn-primary", disabled: off, title, onclick: () => startRepair("onar") }, svg("refresh"), "Onar"))),
      rep && rep.adimlar.length ? h("ol", { class: "repair-steps" }, ...rep.adimlar.map((st) => {
        const [tone, mark] = REPAIR_MARK[st.durum] || ["", "?"];
        return h("li", { class: "rs-" + st.durum, "data-step": st.id }, h("span", { class: "rs-mark " + tone, "aria-hidden": "true" }, mark),
          h("strong", null, st.ad), h("span", null, st.detay || (st.durum === "calisiyor" ? "denetleniyor…" : "")));
      })) : null,
      h("p", { class: "hint-s" }, "Arka planda sürekli çalışan bir denetim yok: adres denetimi açılışta ve her gece 03–04 arası, onarım bir servis çökünce ve burada istenince çalışır; güvenlik duvarı saatte bir ayrıca denetlenir. Konsol'a ulaşılamazsa SSH ile: sudo master-onar"));
  }
  // DD-194/DD-205: the Konsol account, read once per page. Settings → Sistem shows it; the sidebar's
  // sign-out exists only on the internet address — the tailnet address has no sign-in, the device is
  // the credential. The backend names the channel (kanal); the page never guesses it.
  let konsolAccount = null, konsolAccountBusy = false;
  const publicChannel = () => konsolAccount?.kanal === "internet";
  function loadKonsolAccount() {
    if (konsolAccountBusy) return;
    konsolAccountBusy = true;
    api("/api/konsol/oturum").then((s) => { konsolAccount = s; }).catch(() => { konsolAccount = { durum: "bilinmiyor" }; })
      .finally(() => {
        konsolAccountBusy = false;
        $("logout").hidden = !publicChannel();
        if (current === "ayarlar" && settingsTab === "system") renderSettings();
      });
  }
  async function logout() {
    try { await post("/api/konsol/oturum/cikis", {}); } catch (_err) { /* oturum zaten bitmiş olabilir */ }
    location.replace("/giris.html");
  }
  // One dialog for the account: "kur" creates the internet account (tailnet only), "degistir" sets a
  // new password — the current one is asked only on the internet address (DD-205). It runs in the
  // shared dialog, outside the Settings view that re-renders every 10 s.
  function accountDialog(kind) {
    const create = kind === "kur", needOld = !create && publicChannel();
    const field = (id, label, auto, min) => h("label", { for: id }, label,
      h("input", { type: "password", id, autocomplete: auto, required: true, minlength: min, maxlength: 256 }));
    const error = h("p", { class: "err-s", role: "alert", hidden: true });
    const submit = h("button", { type: "submit", class: "btn btn-primary" }, svg("key"), create ? "Hesabı oluştur" : "Parolayı değiştir");
    const form = h("form", { class: "dav-form", id: create ? "konsol-create" : "konsol-password", onsubmit: async (e) => {
      e.preventDefault();
      const next = $("acc-new"), again = $("acc-again");
      again.setCustomValidity(next.value === again.value ? "" : (create ? "Parolalar aynı değil." : "Yeni parolalar aynı değil."));
      if (submit.disabled || !form.reportValidity()) return;
      submit.disabled = true; error.hidden = true;
      try {
        if (create) {
          await post("/api/konsol/oturum/kur", { kullanici: $("acc-user").value.trim(), parola: next.value });
          shClose(); toast("Konsol hesabı oluşturuldu; internet adresi bu hesapla açılır.");
        } else {
          await post("/api/konsol/hesap/parola", needOld ? { eski: $("acc-old").value, yeni: next.value } : { yeni: next.value });
          shClose(); toast(needOld ? "Konsol parolası değişti; diğer oturumlar kapatıldı." : "Konsol parolası değişti; internet oturumları kapatıldı.");
        }
        konsolAccount = null; loadKonsolAccount();
      } catch (err) { if (needOld) $("acc-old").value = ""; error.textContent = err.message; error.hidden = false; }
      finally { submit.disabled = false; }
    } },
    create ? h("label", { for: "acc-user" }, "Kullanıcı adı", h("input", { type: "text", id: "acc-user", autocomplete: "username", autocapitalize: "none",
      spellcheck: false, required: true, minlength: 3, maxlength: 32, pattern: "[A-Za-z0-9][A-Za-z0-9._\\-]{2,31}" })) : null,
    needOld ? field("acc-old", "Mevcut parola", "current-password", null) : null,
    field("acc-new", create ? "Parola (en az 10 karakter)" : "Yeni parola (en az 10 karakter)", "new-password", 10),
    field("acc-again", create ? "Parola (tekrar)" : "Yeni parola (tekrar)", "new-password", 10),
    h("p", { class: "hint-s" }, create ? "Kayıt sunucuda yalnız özet olarak tutulur. Tailscale'den giriş parolasızdır; bu hesap yalnız internet adresinde sorulur."
      : needOld ? "Bu tarayıcı açık kalır; diğer tüm oturumlar kapanır." : "Tailscale cihazından mevcut parola sorulmaz; internet adresindeki tüm oturumlar kapanır."),
    error, h("div", { class: "dav-actions" }, submit, h("button", { type: "button", class: "btn btn-quiet", onclick: shClose }, "Vazgeç")));
    form.addEventListener("input", (e) => { if (e.target.id === "acc-again") e.target.setCustomValidity(""); });
    $("sh").addEventListener("close", () => form.querySelectorAll("input").forEach((i) => { i.value = ""; }), { once: true });
    $("sh-body").replaceChildren(shHead(create ? "İnternet hesabı" : "Konsol parolası", "Konsol girişi · yalnız internet adresinde sorulur", "key"), form);
    if (!$("sh").open) $("sh").showModal();
    (create ? $("acc-user") : needOld ? $("acc-old") : $("acc-new")).focus();
  }
  function accountCard() {
    if (!konsolAccount) loadKonsolAccount();
    const a = konsolAccount, user = a?.kullanici;
    const action = (label, onclick, primary) => h("button", { type: "button", class: primary ? "btn btn-primary" : "btn btn-quiet", onclick }, svg("key"), label);
    let note, actions = [];
    if (!a) note = "Hesap bilgisi okunuyor…";
    else if (a.durum === "bilinmiyor" || (a.durum !== "kurulum" && !user)) note = "Hesap bilgisi okunamadı.";
    else if (publicChannel()) {
      note = `Giriş yapan: ${user}. Oturum ${a.oturum_gun || 7} gün açık kalır.`;
      actions = [action("Parolayı değiştir", () => accountDialog("degistir")), h("button", { type: "button", class: "btn btn-quiet", onclick: logout }, "Çıkış yap")];
    } else if (a.durum === "kurulum") {
      note = "Tailscale'den giriş parolasızdır. İnternet adresi (Ayarlar → Caddy → Panel) için bir kullanıcı adı ve parola belirleyin; hesap olmadan internet yayını açılmaz.";
      actions = [action("İnternet hesabı oluştur", () => accountDialog("kur"), true)];
    } else {
      note = `İnternet hesabı: ${user}. Tailscale'den giriş parolasızdır; internet adresi bu hesapla açılır.`;
      actions = [action("Parolayı değiştir", () => accountDialog("degistir"))];
    }
    // DD-245: the account is the last line of the "Panel ve sunucu" card.
    return h("div", { class: "srv-account", id: "konsol-account" }, h("strong", null, "Konsol hesabı"),
      h("p", { class: "page-note" }, note), h("div", { class: "top-actions" }, ...actions));
  }
  // DD-246: reboot the server after a typed confirmation; the backend refuses it beside an update, a repair or a
  // package operation and reboots a few seconds after answering.
  function askReboot() {
    ask({ title: "Sunucu yeniden başlatılsın mı?", sub: S.sys ? S.sys.host : "", danger: true, word: true, go: "Yeniden başlat",
      items: [["refresh", "Tüm servisler ve uygulamalar durur; sunucu birkaç dakika içinde geri gelir."],
        ["info", "Süren aktarımlar ve WebDAV bağlantıları kesilir."]],
      onOk: () => post("/api/konsol/yeniden-baslat", {}).then((r) => {
        toast(`Sunucu ${r && r.sure ? r.sure + " saniye içinde" : "birazdan"} yeniden başlıyor; Konsol birkaç dakika ulaşılamaz.`);
      }).catch(fail) });
  }
  // DD-245: three cards: Panel ve sunucu (with the Konsol account), Sağlık in one row, Denetle ve onar.
  function systemContent() {
    const s = S.sys;
    const row = (label, value) => h("div", null, h("dt", null, label), h("dd", null, value || "—"));
    return h("div", {class:"as-stack"},
      h("article", {class:"card server-card"}, h("div", {class:"card-head"}, h("h2", null, "Panel ve sunucu"),
        h("button", {type:"button", class:"btn btn-sm btn-quiet", id:"reboot", disabled: publicChannel(),
          title: publicChannel() ? "Yeniden başlatma yalnız Tailscale adresinden istenir" : null, onclick: askReboot}, svg("refresh"), "Yeniden başlat")),
        s ? h("dl", {class:"system-facts"},
          row("Sunucu", s.host), row("Sistem", s.os), row("Çekirdek", s.kernel), row("Panel sürümü", s.version),
          row("Çalışma süresi", duration(s.uptime)), row("Tailscale", s.net.tailscale),
          row("Panel adresi", "panel." + s.domain), row("Kullanıcı alanı", s.root)) : h("p", {class:"hint-s"}, "Sunucu bilgisi bekleniyor…"),
        accountCard()),
      healthCard(),
      h("article", {class:"card repair-card"}, repairBox()));
  }
  const logContent = () => h("div", {class:"logwrap"},
    h("p", {class:"page-note"}, "Konsol’dan yapılan son işlemler. Servis günlükleri App Store → Ayrıntı bölümünde bulunur."),
    h("div", {class:"chipset", id:"log-filter", role:"group", "aria-label":"Süzgeç"}),
    h("div", {class:"table log-t", id:"log-table"}));
  let settingsTab = "system";
  // Podman: kenar çubuğunda kendi sayfası (konteynerler.js, #/konteynerler). Yönetici kendi okumasını ve işlemlerini yapar;
  // bir işlem bitince App Store ve Genel bakış ortak modül listesinden yenilenir (refreshShared).
  const containers = window.createContainerManager({ h, svg, api, post, enc, toast, fail, ask, bytes, since,
    clock: { sync: (serverNow) => { if (Number.isFinite(serverNow)) S.offset = serverNow - Date.now() / 1000; } },
    stamp: (text) => { const s = $("ct-stamp"); if (s && current === "konteynerler") s.textContent = text; },
    // Before the catalogue answers an App Store row keeps its container name, never the internal package id.
    appMeta: (id) => ((MODS || []).some((m) => m.id === id) ? metaOf(id) : null), refreshShared: () => loadModules(), go: (hash) => { location.hash = hash; }, active: () => current === "konteynerler" });
  const settingsPage = window.createSettingsPage({ h, svg, api, post, toast, fail, paintWeb, loadSettings, systemContent, logContent, paintLog:renderLog });
  function renderSettings() {
    const stamp = $("cfg-stamp");
    if (stamp) stamp.textContent = CFG ? "Son okuma " + hhmm(CFG.read_at) : "Okunuyor…";
    settingsPage.render(CFG, settingsTab);
  }
  /* ---------- One workspace, hash routes ---------- */
  function setMenu(open) {
    $("menu-toggle").setAttribute("aria-expanded", String(open));
    $("panel-sidebar").classList.toggle("menu-open", open);
  }
  $("menu-toggle").addEventListener("click", () => setMenu($("menu-toggle").getAttribute("aria-expanded") !== "true"));
  document.querySelector(".skip-link").addEventListener("click", (e) => { e.preventDefault(); $("main-content").focus(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && $("menu-toggle").getAttribute("aria-expanded") === "true") { setMenu(false); $("menu-toggle").focus(); } });
  const settingsActions = () => [h("span", {class:"hm", id:"cfg-stamp"}, "Okunuyor…"),
    h("button", {type:"button", class:"btn btn-quiet", onclick:() => {
      if (current === "ayarlar" && settingsTab === "log") loadActions();
      else if (current === "ayarlar" && settingsTab === "system") { loadSystem(); loadHealth(); }
      else loadSettings(true);
    }}, svg("refresh"), "Yenile")];
  /* ---------- Ana Menü (DD-213): yalnız kurulu uygulamalar ve kompakt ağ kartı ---------- */
  // Kaynaklar yan menüde; ağ /api/konsol/ag'den, kareler modül listesinden; görünürken 5 sn'de bir.
  // Kare ve widget sırası ile widget'ların görünürlüğü aynı sunucu düzen kaydında durur.
  const uptimeText = (sec) => { const d = Math.floor(sec / 86400), hh = Math.floor((sec % 86400) / 3600), mm = Math.floor((sec % 3600) / 60);
    return d ? `${d} g ${hh} sa` : hh ? `${hh} sa ${mm} dk` : `${mm} dk`; };
  // Eski saat/sistem ayarları yok sayılır; widget'lar kare sütunlarının ilk ikisini kullanır.
  const WIDGETS = [
    // DD-242: the 1×1 widgets share the first row; the 2×1 application traffic card is the row below.
    { id: "sunucu", ad: "Sunucu", label: "Sunucu adresleri", genislik: 1, boy: "1x1" },
    { id: "hiz", ad: "Hız", label: "Anlık ağ hızı", genislik: 1, boy: "1x1" },
    { id: "ag", ad: "Ağ", label: "Uygulama trafiği", genislik: 2, boy: "2x1" },
  ];
  // layout: sunucudaki kayıt (null: varsayılan); editing: Düzenle açıkken taslak, değilse null.
  // modsSettled: the module list answered once (or failed), so the tiles do not jump in after the page.
  let layout = null, layoutLoaded = false, modsSettled = false, editing = null, drag = null;
  const defaultLayout = () => ({ kareler: [], widgetlar: WIDGETS.map((w) => ({ id: w.id, genislik: w.genislik, gizli: false })) });
  const activeLayout = () => editing || layout || defaultLayout();
  function widgetSetting(id) {
    const own = (activeLayout().widgetlar || []).find((w) => w.id === id), base = WIDGETS.find((w) => w.id === id);
    return { genislik: base.genislik, gizli: own ? own.gizli : false };
  }
  // DD-242: widgets fill a two-column block in order, row by row: a 1×1 card takes a cell, a 2×1 card a
  // whole row. The order is kept as the block shows it (rows top to bottom, cells left to right), so an
  // order and what is on screen always agree.
  function packWidgets(ids) {
    const rows = [], at = new Map();
    for (const id of ids) {
      const wide = WIDGETS.find((w) => w.id === id).genislik > 1;
      for (let r = 0; !at.has(id); r++) {
        const row = rows[r] || (rows[r] = [false, false]);
        const c = wide ? (row[0] || row[1] ? -1 : 0) : row.indexOf(false);
        if (c < 0) continue;
        row[c] = true;
        if (wide) row[1] = true;
        at.set(id, r * 2 + c);
      }
    }
    return [...ids].sort((a, b) => at.get(a) - at.get(b));
  }
  // A saved order counts only when it names every widget; records from before DD-242 list some or none.
  function widgetOrder() {
    const ids = WIDGETS.map((w) => w.id);
    const saved = (activeLayout().widgetlar || []).map((w) => w.id).filter((id) => ids.includes(id));
    return packWidgets(saved.length === ids.length && new Set(saved).size === ids.length ? saved : ids);
  }
  // One place earlier or later. A step the block would show unchanged (a 2×1 card cannot sit beside a
  // 1×1 card) goes on until the arrangement changes; null when nothing changes in that direction.
  function widgetStep(order, id, step) {
    const next = [...order];
    for (let i = next.indexOf(id); i + step >= 0 && i + step < next.length; i += step) {
      [next[i], next[i + step]] = [next[i + step], next[i]];
      const shown = packWidgets(next);
      if (shown.join() !== order.join()) return shown;
    }
    return null;
  }
  function loadLayout() {
    return api("/api/konsol/duzen").then((r) => { if (!editing) layout = r && r.duzen ? r.duzen : null; })
      .catch(() => { /* düzen okunamazsa varsayılan düzen gösterilir */ })
      .finally(() => { layoutLoaded = true; renderOverview(); });
  }

  /* -- ağ kartı (DD-206) -- */
  let NET = null, netFailed = false, netBusy = false, netReceived = 0;
  const netReplyFresh = () => !!NET && !netFailed && (performance.now() - netReceived) / 1000 <= 15;
  const netFresh = () => netReplyFresh() && Number.isFinite(NET.sampled_at)
    && NET.read_at - NET.sampled_at + (performance.now() - netReceived) / 1000 <= 15;
  function speed(b) {
    if (!Number.isFinite(b)) return "—";
    if (b < KiB) return Math.round(b) + " B/s";
    if (b < MiB) return Math.round(b / KiB) + " KB/s";
    if (b < GiB) return dec(b / MiB, b < 10 * MiB ? 1 : 0) + " MB/s";
    return dec(b / GiB, 1) + " GB/s";
  }
  function netApps() {
    const apps = NET && Array.isArray(NET.apps) ? NET.apps : [];
    if (!apps.length) return [h("tr", null, h("td", { colspan: 3, class: "net-empty" }, netFailed ? "Uygulama trafiği okunamadı." : NET ? "Trafiğini bildiren kurulu uygulama yok." : "Uygulama trafiği okunuyor…"))];
    return apps.map((a) => {
      const meta = metaOf(a.id), fresh = netReplyFresh() && a.state === "calisiyor";
      const name = meta.name === a.id ? (typeof a.name === "string" && a.name ? a.name : a.id) : meta.name;
      // DD-242: the column headings are for assistive technology; on screen the glyphs of "Hız" name them.
      const total = (key, cls) => h("td", { class: "v " + cls,
        title: !fresh || !Number.isFinite(a[key]) ? (a.state === "durduruldu" ? "Uygulama durduruldu" : "Aktarım miktarı okunamadı") : "" },
        svg(cls === "down" ? "download" : "upload"), fresh && Number.isFinite(a[key]) ? bytes(a[key]) : "—");
      return h("tr", { class: "net-app", "data-app": a.id },
        h("th", { scope: "row" }, h("span", { class: "net-app-name", title: name }, h("span", { class: "ico " + meta.tone }, svg(meta.icon)), h("strong", null, name))),
        total("down", "down"), total("up", "up"));
    });
  }
  const netSub = () => NET ? (NET.iface ? `${NET.iface} · anlık` : "WAN arayüzü bilinmiyor")
    : netFailed ? "Ağ bilgisi okunamadı" : "Ölçülüyor…";
  // DD-231: the server's live rates are the "Hız" widget; "Ağ" lists the applications' totals.
  function rateBody() {
    const fresh = netFresh();
    return [
      // DD-231: download/upload glyphs instead of words; the row keeps its name for assistive technology.
      h("div", { class: "net-rate down", role: "group", "aria-label": "İndirme", title: "İndirme" }, svg("download"), h("b", { id: "ag-rx" }, fresh ? speed(NET.rx) : "—")),
      h("div", { class: "net-rate up", role: "group", "aria-label": "Yükleme", title: "Yükleme" }, svg("upload"), h("b", { id: "ag-tx" }, fresh ? speed(NET.tx) : "—")),
    ];
  }
  function appsTable() {
    return h("table", { class: "net-table", "aria-label": "Uygulama aktarım toplamları" },
      h("thead", null, h("tr", null, ...["Uygulama", "İndirme", "Yükleme"].map(t => h("th", { scope: "col" }, t)))),
      h("tbody", null, ...netApps()));
  }
  function paintNetwork() {
    const rates = $("hiz-body"), apps = $("ag-apps"), sub = $("ag-sub"), live = $("ag-live");
    if (rates) rates.replaceChildren(...rateBody());
    // Preserve the scroll/focus of a long application list while replacing its measured values.
    if (apps) {
      const scroll = apps.scrollTop, focused = document.activeElement === apps;
      apps.replaceChildren(appsTable());
      apps.scrollTop = scroll;
      if (focused) apps.focus({ preventScroll: true });
    }
    if (sub) sub.textContent = netSub();
    if (live) { live.textContent = netFresh() ? "Canlı" : "Bekleniyor"; live.className = "hm" + (netFresh() ? " ok" : ""); }
  }
  async function loadNetwork() {
    if (netBusy) return;
    netBusy = true;
    const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 12000);
    try { NET = await api("/api/konsol/ag", { signal: controller.signal }); netReceived = performance.now(); netFailed = false; }
    catch (_err) { netFailed = true; }
    finally { clearTimeout(timeout); netBusy = false; }
    if (current === "genel") paintNetwork();
  }

  /* -- widget'lar -- */
  function widgetContent(id) {
    if (id === "sunucu") {
      const facts = serverFacts(), access = facts.find((f) => f[0] === "foot-access");
      return [
        h("div", { class: "card-head" }, h("div", null, h("h2", null, "Sunucu"),
          h("small", { class: "hint-s", id: "foot-access" }, access[2]))),
        h("dl", { class: "server-facts" }, ...facts.filter((f) => f[0] !== "foot-access").map(([key, label, value, mono, full]) =>
          h("div", null, h("dt", null, label), h("dd", { id: key, class: mono ? "mono" : null, title: full || null }, value)))),
      ];
    }
    if (id === "hiz") return [
      h("div", { class: "card-head" }, h("div", null, h("h2", null, "Hız"), h("small", { class: "hint-s", id: "ag-sub" }, netSub())),
        h("span", { class: "hm" + (netFresh() ? " ok" : ""), id: "ag-live" }, netFresh() ? "Canlı" : "Bekleniyor")),
      h("div", { class: "net-rates", id: "hiz-body" }, ...rateBody()),
    ];
    return [
      h("div", { class: "card-head" }, h("div", null, h("h2", null, "Ağ"), h("small", { class: "hint-s" }, "Uygulamalar · toplam aktarım"))),
      h("div", { class: "net-apps", id: "ag-apps", tabindex: "0", role: "region", "aria-label": "Uygulama trafiği" }, appsTable()),
    ];
  }
  // DD-242: ◀ ▶ move a widget one place earlier or later in the order, like the tiles' arrows.
  function widgetTools(def, set, order) {
    const change = (patch, tool) => {
      Object.assign(editing.widgetlar.find((w) => w.id === def.id), patch);
      renderOverview(true, `[data-widget="${def.id}"] [data-tool="${tool}"]`);
    };
    const arrow = (step, icon, word) => h("button", { type: "button", "data-move": String(step), "aria-label": `${def.ad}: ${word}`,
      disabled: !widgetStep(order, def.id, step), onclick: () => moveWidget(def.id, step) }, svg(icon));
    return h("div", { class: "widget-tools", role: "group", "aria-label": def.ad + " düzeni" },
      h("span", { class: "tile-move" }, arrow(-1, "chevl", "öne taşı"), arrow(1, "chev", "geriye taşı")),
      // A narrow 1×1 card keeps only the eye; the word stays as the tooltip.
      h("button", { type: "button", class: "btn btn-sm btn-quiet", "data-tool": "gizle", "aria-label": `${def.ad}: ${set.gizli ? "göster" : "gizle"}`,
        title: set.gizli ? "Göster" : "Gizle", onclick: () => change({ gizli: !set.gizli }, "gizle") },
        svg("eye"), h("span", { class: "wt-label" }, set.gizli ? "Göster" : "Gizle")));
  }
  function moveWidget(id, step) {
    const order = editing && widgetStep(widgetOrder(), id, step);
    if (!order) return;
    editing.widgetlar = order.map((key) => editing.widgetlar.find((w) => w.id === key));
    renderOverview(true, `[data-widget="${id}"] [data-move="${step}"]`);
  }
  function overviewWidgets() {
    const order = widgetOrder();
    return order.filter((id) => editing || !widgetSetting(id).gizli).map((id) => {
      const def = WIDGETS.find((w) => w.id === id), set = widgetSetting(id);
      const el = h("article", { class: "card widget" + (set.gizli ? " is-hidden" : ""), "aria-label": def.label, "data-widget": def.id,
        "data-span": String(set.genislik), "data-boy": def.boy }, ...widgetContent(def.id));
      if (editing) el.append(widgetTools(def, set, order));
      return el;
    });
  }

  /* -- uygulama kareleri -- */
  function tileDefs() {
    return (MODS || []).filter((m) => m.installed).map((m) => {
      const meta = metaOf(m.id);
      const state = m.busy ? "işleniyor" : m.state === "durduruldu" ? "durduruldu" : (unitRuntime(m) && m.live !== "running") || m.live === "exited" ? "çalışmıyor" : "çalışıyor";
      const dot = m.busy ? "warn" : state === "çalışıyor" ? "on" : state === "durduruldu" ? "off" : "warn";
      const form = formOf(m.id);
      return { key: m.id, href: meta.rota ? "#/" + meta.rota : "#/moduller", icon: meta.icon, tone: meta.tone, name: meta.name, sub: state, dot,
        launch: launchUrl(m), settings: form && form.oku && form.yaz ? "form" : meta.rota ? "#/" + meta.rota : "", service: !!m.durdurulabilir };
    });
  }
  // Kayıtlı sıradakiler önce, kayıtta olmayanlar (sonradan kurulan uygulama) varsayılan sırayla sonra.
  function orderedTiles() {
    const defs = tileDefs(), order = activeLayout().kareler || [];
    const rank = (d, i) => { const at = order.indexOf(d.key); return at < 0 ? order.length + i : at; };
    return defs.map((d, i) => [rank(d, i), d]).sort((a, b) => a[0] - b[0]).map((p) => p[1]);
  }
  function tileEl(def, index, total) {
    const inner = [def.dot ? h("span", { class: "dot " + def.dot, "aria-hidden": "true" }) : null,
      h("span", { class: "ico " + def.tone }, svg(def.icon)), h("strong", null, def.name), h("small", null, def.sub)];
    // DD-213: three fixed action slots beneath the icon (Durdur/Başlat, Ayarlar, Günlükler).
    // The row sits next to the (stretched) launch link, never
    // inside it; the link opens the app's web UI. Edit mode draws the plain tiles below.
    const actions = !editing ? appActions(def) : null;
    if (actions) return h("div", { class: "tile card has-actions", "data-tile": def.key },
      h("a", { class: "tile-link", href: def.launch || def.href, ...newTab(def.launch),
        "aria-label": def.launch ? `${def.name}: arayüzü yeni sekmede aç` : def.name }, ...inner), actions);
    if (!editing) return h("a", { class: "tile card", href: def.launch || def.href, "data-tile": def.key, ...newTab(def.launch) }, ...inner);
    return h("div", { class: "tile card", "data-tile": def.key, role: "group", "aria-label": def.name, onpointerdown: (e) => dragStart(e, def.key) }, ...inner,
      h("span", { class: "tile-move" },
        h("button", { type: "button", "data-move": "-1", "aria-label": `${def.name}: sola taşı`, disabled: index === 0, onclick: () => moveTile(def.key, -1) }, svg("chevl")),
        h("button", { type: "button", "data-move": "1", "aria-label": `${def.name}: sağa taşı`, disabled: index === total - 1, onclick: () => moveTile(def.key, 1) }, svg("chev"))));
  }
  // Ayarlar: the package's declared form (dialog), else its page. Durdur/Başlat follows the server's state and
  // progress: busy (or a request on its way) marks it aria-disabled — still focusable, so keyboard focus
  // survives the poll redraws — and clicks are ignored until the operation ends. DD-229/230: the service action
  // is a short word (Dur/Başla), settings a gear and logs a terminal icon; the full name is the label and tooltip.
  const tilePending = new Map();   // id → the action whose request is on its way
  function appActions(def) {
    const m = (MODS || []).find((x) => x.id === def.key);
    if (!m) return null;
    const kids = [];
    const blank = (action) => h("span", { class: "tile-act tile-act-empty", "data-act": action, "aria-hidden": "true" });
    const named = (name) => ({ "aria-label": name, title: name });
    if (def.service) {
      const running = m.state === "calisiyor", busy = !!m.busy || tilePending.has(m.id);
      const doing = m.busy ? m.progress && m.progress.action : tilePending.get(m.id);
      const word = !busy ? (running ? "Durdur" : "Başlat") : doing === "durdur" ? "Durduruluyor…" : doing === "baslat" ? "Başlatılıyor…"
        : running ? "Durdur" : "Başlat";
      kids.push(h("button", { type: "button", class: "tile-act", "data-act": "servis", "aria-disabled": busy ? "true" : "false",
        ...named(`${def.name}: ${word}`), onclick: () => tileService(m.id) }, running ? "Dur" : "Başla"));
    } else kids.push(blank("servis"));
    if (def.settings === "form") kids.push(h("button", { type: "button", class: "tile-act", "data-act": "ayar", ...named(`${def.name} ayarları`),
      onclick: () => appForm(m.id, "ayar") }, svg("gear")));
    else if (def.settings) kids.push(h("a", { class: "tile-act", "data-act": "ayar", href: def.settings, ...named(`${def.name} ayarları`) }, svg("gear")));
    else kids.push(blank("ayar"));
    kids.push(h("button", { type: "button", class: "tile-act", "data-act": "gunluk", ...named(`${def.name} günlükleri`),
      onclick: () => appLog(m.id) }, svg("terminal")));
    return h("div", { class: "tile-actions", role: "group", "aria-label": `${def.name} işlemleri` }, ...kids);
  }
  function appLog(id) {
    const meta = metaOf(id), opener = document.activeElement;
    const root = h("div", { class: "app-log-root" });
    const output = h("pre", { tabindex: "0", "aria-label": `${meta.name} günlük çıktısı` }, "Okunuyor…");
    const error = h("p", { class: "err-s", role: "alert", hidden: true });
    let controller = null, closed = false;
    const mine = () => !closed && $("sh").open && $("sh-body").contains(root);
    const refresh = h("button", { type: "button", class: "btn btn-quiet btn-sm", onclick: read }, svg("refresh"), "Yenile");
    root.append(shHead(`${meta.name} günlükleri`, meta.logSrc, "list"), h("div", { class: "logbox" }, output), error,
      h("div", { class: "dlg-foot" }, refresh, h("button", { type: "button", class: "btn btn-primary", onclick: shClose }, "Kapat")));
    $("sh-body").replaceChildren(root);
    if (!$("sh").open) $("sh").showModal();
    $("sh").addEventListener("close", () => {
      const own = $("sh-body").contains(root);
      closed = true; controller?.abort();
      if (own) (opener?.isConnected ? opener : document.querySelector(`[data-tile="${id}"] [data-act="gunluk"]`))?.focus();
    }, { once: true });
    read();
    async function read() {
      if (refresh.disabled) return;
      refresh.disabled = true; error.hidden = true;
      const request = new AbortController();
      controller = request;
      const timeout = setTimeout(() => request.abort(), 12000);
      try {
        const response = await fetch(`/api/konsol/moduller/${enc(id)}/gunluk`, {
          headers: { "X-Konsol": "1" }, cache: "no-store", credentials: "same-origin", signal: request.signal });
        if (response.status === 401) { const body = await response.json().catch(() => ({})); if (body.giris) toLogin(); }
        if (!response.ok) throw new Error(`Günlük okunamadı (HTTP ${response.status}).`);
        const value = await response.text();
        if (mine()) output.textContent = value || "(boş)";
      } catch (err) {
        if (mine()) { output.textContent = ""; error.textContent = err.name === "AbortError" ? "Günlük okunamadı; istek zaman aşımına uğradı." : err.message; error.hidden = false; }
      } finally { clearTimeout(timeout); refresh.disabled = false; }
    }
  }
  function tileService(id) {
    const m = (MODS || []).find((x) => x.id === id);
    if (!m || !m.installed || m.busy || tilePending.has(id)) return;
    const focusSel = `[data-tile="${id}"] [data-act="servis"]`;
    const go = (action) => {
      tilePending.set(id, action);
      renderOverview(false, focusSel);
      // The finishing redraw keeps whatever has focus by then (the operator may have moved on).
      modStart(m, action, { veri: false }).catch(fail).finally(() => { tilePending.delete(id); renderOverview(); });
    };
    if (m.state === "calisiyor") askStop(m, () => go("durdur")); else go("baslat");
  }
  function moveTile(key, step) {
    const order = orderedTiles().map((d) => d.key), i = order.indexOf(key), j = i + step;
    if (!editing || i < 0 || j < 0 || j >= order.length) return;
    [order[i], order[j]] = [order[j], order[i]];
    editing.kareler = order;
    renderOverview(true, `[data-tile="${key}"] [data-move="${step}"]`);
  }
  // Sürükle-bırak: fare ve dokunma için aynı işaretçi olayları; kare sürüklenirken yerinde taşınır.
  // Taşınan öğe belgeden bir an ayrıldığı için tarayıcı işaretçi yakalamasını bırakır; olaylar bu
  // yüzden belge düzeyinde dinlenir.
  function dragStart(e, key) {
    if (!editing || drag || e.button > 0 || e.target.closest("button")) return;
    const el = e.currentTarget;
    drag = { key, el, id: e.pointerId, moved: false };
    el.classList.add("dragging");
    document.addEventListener("pointermove", dragMove);
    document.addEventListener("pointerup", dragEnd);
    document.addEventListener("pointercancel", dragEnd);
    e.preventDefault();
  }
  function dragMove(e) {
    if (!drag || e.pointerId !== drag.id) return;
    const target = document.elementFromPoint(e.clientX, e.clientY);
    const over = target && target.closest("#genel-tiles .tile");
    if (!over || over === drag.el) return;
    const r = over.getBoundingClientRect();
    if (e.clientX > r.left + r.width / 2) over.after(drag.el); else over.before(drag.el);
    drag.moved = true;
  }
  function dragEnd(e) {
    if (!drag || e.pointerId !== drag.id) return;
    const { el, moved } = drag;
    drag = null;
    el.classList.remove("dragging");
    ["pointermove", "pointerup", "pointercancel"].forEach((t) => document.removeEventListener(t, t === "pointermove" ? dragMove : dragEnd));
    if (moved && e.type === "pointerup" && editing) editing.kareler = [...$("genel-tiles").querySelectorAll(".tile")].map((t) => t.dataset.tile);
    renderOverview(true);
  }

  /* -- düzenleme modu -- */
  function sameAsDefault(draft) {
    const keys = tileDefs().map((d) => d.key), order = orderedTiles().map((d) => d.key);
    return order.join() === keys.join() && draft.widgetlar.map((w) => w.id).join() === WIDGETS.map((w) => w.id).join() && WIDGETS.every((w) => {
      const own = draft.widgetlar.find((x) => x.id === w.id);
      return own && own.genislik === w.genislik && !own.gizli;
    });
  }
  function startEdit() {
    const draft = { kareler: orderedTiles().map((d) => d.key), widgetlar: widgetOrder().map((id) => ({ id, ...widgetSetting(id) })) };
    editing = draft;
    renderOverview(true, "#genel-bitti");
  }
  function cancelEdit() {
    editing = null;
    renderOverview(true, "#genel-duzenle");
  }
  function resetDraft() {
    editing = { kareler: [], widgetlar: defaultLayout().widgetlar };
    renderOverview(true, "#genel-varsayilan");
  }
  async function finishEdit() {
    const button = $("genel-bitti");
    if (!editing || !button || button.disabled) return;
    const draft = { kareler: orderedTiles().map((d) => d.key), widgetlar: editing.widgetlar.map((w) => ({ id: w.id, genislik: w.genislik, gizli: w.gizli })) };
    const reset = sameAsDefault(draft);
    button.disabled = true;
    try {
      const answer = await post("/api/konsol/duzen", reset ? { sifirla: true } : { duzen: draft });
      layout = answer && answer.duzen ? answer.duzen : null;
      editing = null;
      renderOverview(true, "#genel-duzenle");
      toast(reset ? "Ana Menü varsayılan düzene döndü." : "Düzen kaydedildi.");
    } catch (err) { button.disabled = false; fail(err); }
  }
  function paintEditBar() {
    const bar = $("genel-edit");
    if (!bar) return;
    bar.classList.toggle("editing", !!editing);
    bar.replaceChildren(...(editing ? [
      h("span", { class: "edit-hint" }, "Kareleri sürükleyin; kareleri ve widget'ları oklarla taşıyın"),
      h("button", { type: "button", class: "btn btn-sm btn-quiet", id: "genel-varsayilan", onclick: resetDraft }, "Varsayılan"),
      h("button", { type: "button", class: "btn btn-sm btn-quiet", id: "genel-vazgec", onclick: cancelEdit }, "Vazgeç"),
      h("button", { type: "button", class: "btn btn-sm btn-primary", id: "genel-bitti", onclick: finishEdit }, "Bitti"),
    ] : [h("button", { type: "button", class: "btn btn-sm btn-quiet", id: "genel-duzenle", disabled: !layoutLoaded || !modsSettled, onclick: startEdit }, svg("pencil"), "Düzenle")]));
  }
  // force: düzenleme adımları; veriler yenilenince Düzenle açıksa sayfa yeniden çizilmez (sürükleme ve
  // odak bozulmasın), sayılar kendi yerlerinde güncellenir.
  function renderOverview(force, focus) {
    if (current !== "genel" || (editing && !force) || drag) return;
    const widgets = $("genel-widgets"), tiles = $("genel-tiles");
    if (!layoutLoaded) { widgets.replaceChildren(); tiles.replaceChildren(); paintEditBar(); return; }
    const oldApps = $("ag-apps"), appScroll = oldApps?.scrollTop || 0;
    const appFocused = !focus && oldApps && document.activeElement === oldApps;
    // DD-242: the cards sit in one block over the first two tile columns.
    const cards = overviewWidgets();
    widgets.replaceChildren(...(cards.length ? [h("div", { class: "widget-block" }, ...cards)] : []));
    const newApps = $("ag-apps");
    if (newApps) {
      newApps.scrollTop = appScroll;
      if (appFocused) newApps.focus({ preventScroll: true });
    }
    widgets.classList.toggle("editing", !!editing);
    const defs = modsSettled ? orderedTiles() : [];
    // A poll redraws the tiles; keyboard focus on a tile's link or settings action stays on its new copy.
    const had = document.activeElement, hadTile = !focus && had && had.closest ? had.closest("#genel-tiles [data-tile]") : null;
    const hadPart = hadTile && had !== hadTile ? (had.dataset.act ? ` [data-act="${had.dataset.act}"]` : " .tile-link") : "";
    tiles.replaceChildren(...defs.map((d, i) => tileEl(d, i, defs.length)));
    if (modsSettled && !defs.length) tiles.append(h("div", { class: "home-empty" },
      h("p", { class: "hint-s" }, MODS ? "Henüz kurulu uygulama yok." : "Uygulama listesi okunamadı."),
      h("a", { href: "#/moduller", class: "btn btn-sm btn-quiet" }, svg("stack"), "App Store’u aç")));
    if (hadTile) tiles.querySelector(`[data-tile="${hadTile.dataset.tile}"]${hadPart}`)?.focus({ preventScroll: true });
    tiles.classList.toggle("editing", !!editing);
    const installed = (MODS || []).filter((m) => m.installed).length;
    $("genel-sum").textContent = editing ? "Düzenleniyor · değişiklikler Bitti ile kaydedilir"
      : MODS && installed ? `${installed} kurulu uygulama` : "";
    paintEditBar();
    if (focus) {
      const target = document.querySelector(focus);
      const fallback = target && target.disabled ? target.parentElement.querySelector("button:not([disabled])") : null;
      (fallback || target)?.focus();
    }
  }
  // Konsol'un kendi sayfaları; uygulama sayfaları paketlerden gelir (DD-200/202).
  const ROUTES = {
    genel: { title: "Ana Menü", eyebrow: "", actions: () => [],
      render: () => { renderOverview(); loadLayout(); loadNetwork(); if (!(MODS || []).some((m) => m.busy)) loadModules(); } },
    dosyalar: { title: "Dosyalar", eyebrow: "Sunucu alanı", actions: () => [],
      render: () => {
        renderFs(); loadSysState();
        if (fsView === "trash") loadTrash();
        else if (fsView === "shares") loadShares();
        else if (fsView === "files") {
          loadShares();
          const go = fsRouteGo; fsRouteGo = null;
          if (go) fsGo(go, "hash"); else if (!fsList && !fsBusy) loadFs();
          syncHash(false);  // bare #/dosyalar names the folder on screen
        }
      } },
    moduller: { title: "App Store", eyebrow: "", actions: () => [h("span", {class:"hm", id:"mod-sum"}, "Okunuyor…")], render: () => { renderModules(); loadModules(); } },
    // #/konteynerler[/AD]: liste ya da bir konteynerin ayrıntısı (ad URL'de kodlu).
    konteynerler: { title: (sub) => containers.title(sub), eyebrow: (sub) => containers.eyebrow(sub), actions: (sub) => containers.actions(sub),
      render: (sub) => containers.show(sub) },
    ayarlar: { title: "Ayarlar", eyebrow: "Panel ve sunucu yapılandırması", actions:settingsActions,
      render: () => { renderSettings(); if (settingsTab === "log") loadActions(); if (settingsTab === "system") loadHealth(); loadSettings(); } },
  };
  // DD-204: açılış sayfası Genel bakış (DD-160'ta Dosyalar'dı).
  let current = "genel";
  const view = () => current;

  /* ---------- Paket sayfaları (DD-200) ---------- */
  // Kurulu bir paketin sayfası paketle gelir: dosyaları /uygulama/<id>/ altından yüklenir ve
  // betik window.Konsol.sayfa(id, fabrika) ile kaydolur. Konsol rotayı, başlığı ve bölümü sağlar;
  // sayfanın verisi ve API yolları (/api/uygulama/<id>/*) paketin kendisindedir.
  const PAGES = {};            // rota → { id, page }
  const FACTORIES = {};        // id → fabrika (kaldırılıp yeniden kurulunca betik yeniden yüklenmez)
  const PAGE_FILES = new Set();
  const PAGE_FILE_RE = /^[a-z][a-z0-9_.-]{0,40}\.(js|css)$/;
  let pendingRoute = false;
  const PAGE_API = Object.freeze({
    h, svg, $, api, post, enc, toast, fail, ask, bytes, since, credRow, copyButton, copyText,
    clock: { sync: (serverNow) => { if (Number.isFinite(serverNow)) S.offset = serverNow - Date.now() / 1000; }, now },
    dialog: { show: shShow, close: shClose },
    // Modül listesi ve işlemleri Konsol'undur; sayfa yalnız okur ve ister (DD-202).
    module: (id) => (MODS || []).find((x) => x.id === id) || null,
    modPill, modAct: (id, action) => { const m = (MODS || []).find((x) => x.id === id); return m ? modAct(m, action) : Promise.resolve(); },
    reloadModules: () => loadModules(),
    route: () => current, header: () => paintHeader(), go: (hash) => { location.hash = hash; },
  });
  function sectionFor(rota) {
    let section = document.querySelector(`.content > section[data-view="${rota}"]`);
    if (!section) {
      section = h("section", { "data-view": rota, hidden: true }, h("p", { class: "hint-s" }, "Sayfa yükleniyor…"));
      document.querySelector(".content").append(section);
    }
    return section;
  }
  function mountPage(id) {
    const m = (MODS || []).find((x) => x.id === id), meta = metaOf(id);
    if (!m || !m.installed || !meta.rota || PAGES[meta.rota] || !FACTORIES[id]) return;
    const section = sectionFor(meta.rota);
    let page;
    try {
      page = FACTORIES[id](PAGE_API);
      section.replaceChildren();
      if (page && page.mount) page.mount(section);
    } catch (e) {
      section.replaceChildren(h("p", { class: "err-s" }, `${meta.name} sayfası yüklenemedi.`));
      return;
    }
    PAGES[meta.rota] = { id, page: page || {} };
    if (current === meta.rota) route();
  }
  function unmountPage(rota) {
    const entry = PAGES[rota];
    if (!entry) return;
    try { if (entry.page.unmount) entry.page.unmount(); } catch (e) { /* kapanan sayfanın hatası Konsol'u durdurmaz */ }
    delete PAGES[rota];
    document.querySelector(`.content > section[data-view="${rota}"]`)?.remove();
  }
  function registerPage(id, factory) {
    if (!ROUTE_RE.test(String(id)) || typeof factory !== "function") return;
    FACTORIES[id] = factory;
    mountPage(id);
  }
  function ensurePages() {
    (MODS || []).forEach((m) => {
      const meta = metaOf(m.id);
      if (!meta.rota) return;
      if (!m.installed) { if (PAGES[meta.rota] && PAGES[meta.rota].id === m.id) unmountPage(meta.rota); return; }
      (Array.isArray(m.sayfa) ? m.sayfa : []).forEach((f) => {
        if (typeof f !== "string" || !PAGE_FILE_RE.test(f)) return;
        const url = `/uygulama/${enc(m.id)}/${f}`;
        if (PAGE_FILES.has(url)) return;
        PAGE_FILES.add(url);
        document.head.append(f.endsWith(".css") ? h("link", { rel: "stylesheet", href: url }) : h("script", { src: url, defer: true }));
      });
      if (FACTORIES[m.id] && !PAGES[meta.rota]) mountPage(m.id);
    });
  }
  window.Konsol = Object.freeze({ sayfa: registerPage });

  const text = (v, sub) => (typeof v === "function" ? v(sub) : v);
  function headerFor(key, sub) {
    const r = ROUTES[key] || (PAGES[key] && PAGES[key].page), app = appRoutes()[key];
    return { title: r && r.title != null ? text(r.title, sub) : app ? app.baslik : "",
      eyebrow: (r && r.eyebrow != null ? text(r.eyebrow, sub) : app ? app.ustbilgi : "") || "",
      actions: r && r.actions ? r.actions(sub) || [] : [] };
  }
  function paintHeader() {
    const raw = location.hash.replace(/^#\/?/, "").split("/");
    const hd = headerFor(current, raw[0] === current ? raw[1] : undefined);
    $("title").classList.toggle("home-title", current === "genel");
    if (current === "genel") {
      $("title").replaceChildren(h("time", { id: "home-clock" }), h("span", { id: "home-date" }), h("span", { id: "home-update", class: "home-update" }));
      paintHomeClock();
      updSeen = "";
      if (UPD) paintUpdate(); else loadUpdate();
    } else $("title").textContent = hd.title;
    $("eyebrow").textContent = hd.eyebrow;
    $("eyebrow").hidden = !hd.eyebrow;
    $("top-actions").replaceChildren(...hd.actions);
  }
  /* DD-236: on a desktop-width screen Files is a window of the viewport's height: the page itself does not
     scroll, only the contents, the places/detail column and the trash or share lists inside it. Phones keep
     the page scroll. Below ~460 px of room the window keeps that height and the page scrolls again. */
  function fitFs() {
    const panel = $("fs-panel"), on = current === "dosyalar" && FX_WIDE.matches;
    document.documentElement.classList.toggle("fx-fixed", on);
    if (!panel || !on) { panel?.style.removeProperty("--fx-h"); return; }
    const top = panel.getBoundingClientRect().top + window.scrollY;
    const pad = parseFloat(getComputedStyle($("main-content")).paddingBottom) || 0;
    panel.style.setProperty("--fx-h", `${Math.max(460, Math.floor(window.innerHeight - top - pad))}px`);
  }
  let fitQueued = false;
  const queueFit = () => { if (fitQueued) return; fitQueued = true; requestAnimationFrame(() => { fitQueued = false; fitFs(); }); };
  window.addEventListener("resize", queueFit);
  FX_WIDE.addEventListener("change", queueFit);
  function route() {
    let raw = location.hash.replace(/^#\/?/, "").split("/");
    // Eski Ayarlar → Konteynerler bağlantıları (#/ayarlar/konteynerler[/AD]) yeni sayfaya yönlenir.
    if (raw[0] === "ayarlar" && raw[1] === "konteynerler") {
      history.replaceState(null, "", "#/konteynerler" + (raw[2] ? "/" + raw[2] : ""));
      raw = ["konteynerler"].concat(raw[2] ? [raw[2]] : []);
    }
    const apps = appRoutes();
    // Before the module list arrives an application bookmark is kept and shown once the list is known.
    pendingRoute = !MODS && !SHELL_ROUTES.has(raw[0]) && !ROUTES[raw[0]] && ROUTE_RE.test(raw[0]);
    let key = ROUTES[raw[0]] || apps[raw[0]] || pendingRoute ? raw[0] : "genel";
    setMenu(false);
    // An absent application sends a saved bookmark to App Store.
    if (MODS && apps[key] && !apps[key].installed) {
      history.replaceState(null, "", "#/moduller");
      key = "moduller";
    }
    if (key === "dosyalar") {
      fsView = raw[1] === "cop" ? "trash" : raw[1] === "paylasim" ? "shares" : "files";
      // DD-235: #/dosyalar/sistem is the system view; switching views starts at its root.
      const parts = hashParts(raw);
      if (fsView === "files" && (raw[1] === "sistem") !== fsSys) {
        fsSys = raw[1] === "sistem"; fsPath = parts || []; fsList = null; fsShownPath = null; fsBack = []; fsFwd = []; fsRootDirs = null; fsSel.clear(); fsQuery = "";
      } else if (fsView === "files" && parts && pathText(parts) !== pathText(fsPath)) {
        // The browser's back/forward or a typed address inside the same tree: open it in place.
        if (fsList || fsBusy) fsRouteGo = parts; else fsPath = parts;
      }
    }
    if (key === "ayarlar") settingsTab = ["fw","web","dns","log"].includes(raw[1]) ? raw[1] : "system";
    // DD-206: leaving the overview drops an unsaved layout draft.
    if (key !== "genel" && editing) { editing = null; drag = null; }
    // Likewise leaving the Podman page closes its open sheet (an accepted operation keeps running on the server).
    if (key !== "konteynerler") containers.leave();
    current = key;
    if (!ROUTES[key]) sectionFor(key);
    document.querySelectorAll("[data-view]").forEach((s) => { s.hidden = s.dataset.view !== key; });
    // DD-216: applications have no sidebar entry; their pages open from Ana Menü's tiles, which stays marked.
    const navKey = apps[key] ? "genel" : key;
    document.querySelectorAll("[data-route]").forEach((a) => {
      if (a.dataset.route === navKey) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
    paintHeader();
    const r = ROUTES[key] || (PAGES[key] && PAGES[key].page);
    if (r && r.render) r.render(raw[1]);
    window.scrollTo({ top: 0 });
    fitFs();
  }
  window.addEventListener("hashchange", route);
  document.addEventListener("click", (e) => {
    const go = e.target.closest("[data-go]");
    if (go && go.dataset.go) location.hash = go.dataset.go;
  });

  /* Keep the shell independent; poll expensive application data only on its page. */
  loadSystem();
  route();
  loadModules();
  setInterval(() => {
    if (document.hidden || current === "genel") return;
    loadSystem();
    if (PAGES[current] && PAGES[current].page.poll) PAGES[current].page.poll();
    if (current === "ayarlar" && settingsTab === "log") loadActions();
    if (current === "ayarlar" && settingsTab === "system") loadHealth();
    if (current === "konteynerler") containers.poll();
    if (current === "dosyalar") { loadFsState(); loadSysState(); if (fsView === "shares") loadShares(); }
    if (current === "moduller" && !(MODS || []).some((m) => m.busy)) loadModules();
  }, 10000);
  setInterval(() => { if (!document.hidden) { paintResources(); if (current === "genel" && NET && !netReplyFresh()) paintNetwork(); } }, 1000);
  // DD-213: one five-second home tick; no page reload, no duplicate ten-second home poll.
  setInterval(() => {
    if (document.hidden || current !== "genel") return;
    loadSystem();
    if (!(MODS || []).some((m) => m.busy)) loadModules();
    if (editing || !widgetSetting("ag").gizli || !widgetSetting("hiz").gizli) loadNetwork();
    // DD-233: the update offer every minute; its stage every tick while the unit runs.
    if ((UPD && UPD.is.durum === "calisiyor") || Date.now() - updAsked > 60000) loadUpdate();
  }, 5000);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && editing && current === "genel" && !$("sh").open) cancelEdit(); });
  $("logout").addEventListener("click", logout);
  loadKonsolAccount();  // DD-205: shows the sign-out only on the internet address
  document.addEventListener("visibilitychange", () => { if (!document.hidden) { paintResources(); loadSystem(); loadModules(); } });
  loadFsState();
})();
