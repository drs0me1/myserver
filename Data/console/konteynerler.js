/* Podman sayfası: tabandaki Podman'ın yöneticisi (kenar çubuğunda, App Store'dan sonra; rota #/konteynerler). Sözleşme:
   docs/design/container-manager-api.md. Okuma: GET /api/konsol/konteynerler/{liste,ayrinti,gunluk,islem};
   yazma: yalnız POST /islem → 202 {id}, sonra GET /islem?id=… ile işlem bitene kadar izlenir. Tarayıcı izin
   tahmin etmez: her konteynerin yapabileceği işlemler sunucunun "actions" listesindedir, kısıt nedeni
   "restricted_reason". Düzenleme bir taslaktır: yoklamalar taslağa ve odağa dokunmaz; geç gelen bir yanıt
   kendinden sonra açılan pencereye dokunmaz. Gizli ortam değerleri tarayıcıya gelmez, boş bırakılan korunur.
   CSP altında: satır içi biçem/betik yok, işaretleme metinden üretilmez; sınıflar pd- önekli. */
"use strict";
window.createContainerManager = ({ h, svg, api, post, enc, toast, fail, ask, bytes, since, clock, stamp, appMeta, refreshShared, go, active }) => {
  const BASE = "/api/konsol/konteynerler";
  const NAME_RE = /^[a-z][a-z0-9-]{1,30}$/;
  const RES_NAME_RE = /^[a-z0-9][a-z0-9_.-]{0,62}$/;
  // Tam ad: kayıt adresi (nokta, port ya da localhost), depo ve etiket ya da özet.
  const IMAGE_RE = /^(localhost|[a-z0-9-]+(\.[a-z0-9-]+)+)(:[0-9]{1,5})?\/[a-z0-9]+([._-][a-z0-9]+)*(\/[a-z0-9]+([._-][a-z0-9]+)*)*(:[A-Za-z0-9_][A-Za-z0-9._-]{0,127}|@sha256:[0-9a-f]{64})$/;
  const ENV_RE = /^[A-Za-z_][A-Za-z0-9_]{0,127}$/;
  const CIDR_RE = /^(\d{1,3}\.){3}\d{1,3}\/\d{1,2}$/;
  const TAILS = [100, 200, 500, 1000];
  const root = h("div", { class: "pd-root", id: "pd-root" });
  const sheet = h("dialog", { id: "pd-sheet", class: "pd-sheet", "aria-labelledby": "pd-sheet-title" });
  document.body.append(sheet);

  /* ---------------- durum ---------------- */
  let LIST = null, listError = "", readAt = 0, listSeq = 0;
  let tab = "konteynerler", filter = "tum", query = "";
  let detailName = "", DETAIL = null, detailError = "", detailSeq = 0, section = "genel";
  let LOG = null, logError = "", logTail = 200, logQuery = "", logSeq = 0, logLoading = false;
  // DD-214: imaj güncelleme durumu; sunucu kayıt defterine yalnız manifest sorar ve yanıtı önbellekte tutar.
  let UPD = null, updLoading = false, updError = "";
  const pending = new Map();    // hedef → istenen eylem (istek gitti, işlem bitmedi)
  const OPS = new Map();        // işlem kimliği → { id, action, target, state, step, error, result, ctx }
  const lastError = new Map();  // konteyner adı → son başarısız işlemin metni
  let opTimer = 0;
  let SH = null, sheetSeq = 0;  // açık pencere ve onun kimliği (her açılış/kapanış artırır)

  /* ---------------- etiketler ---------------- */
  const DOING = { start: "Başlatılıyor…", stop: "Durduruluyor…", restart: "Yeniden başlatılıyor…", remove: "Kaldırılıyor…", save: "Kaydediliyor…",
    create: "Oluşturuluyor…", adopt: "Sahipleniliyor…", "image-pull": "İmaj çekiliyor…", "image-remove": "İmaj siliniyor…", "image-update": "İmaj güncelleniyor…",
    "volume-create": "Birim oluşturuluyor…", "volume-remove": "Birim siliniyor…", "network-create": "Ağ oluşturuluyor…", "network-remove": "Ağ siliniyor…" };
  const DONE = { start: "başlatıldı", stop: "durduruldu", restart: "yeniden başlatıldı", remove: "kaldırıldı", save: "değişiklikler uygulandı", create: "oluşturuldu",
    adopt: "sahiplenildi", "image-pull": "imaj çekildi", "image-remove": "imaj silindi", "image-update": "imaj güncellendi", "volume-create": "birim oluşturuldu",
    "volume-remove": "birim silindi", "network-create": "ağ oluşturuldu", "network-remove": "ağ silindi" };
  const FAILED = { start: "Başlatılamadı", stop: "Durdurulamadı", restart: "Yeniden başlatılamadı", remove: "Kaldırılamadı", save: "Kaydedilemedi", create: "Oluşturulamadı",
    adopt: "Sahiplenilemedi", "image-pull": "İmaj çekilemedi", "image-remove": "İmaj silinemedi", "image-update": "İmaj güncellenemedi", "volume-create": "Birim oluşturulamadı",
    "volume-remove": "Birim silinemedi", "network-create": "Ağ oluşturulamadı", "network-remove": "Ağ silinemedi" };
  const SCOPE = { local: "Yalnız bu sunucu", tailscale: "Tailscale", public: "İnternet (açık)", other: "Belirli adres" };
  const STATE = { running: ["ok", "Çalışıyor"], stopped: ["idle", "Durduruldu"], exited: ["idle", "Durdu"], created: ["idle", "Oluşturuldu"], paused: ["warn", "Duraklatıldı"], unknown: ["warn", "Bilinmiyor"] };
  const HEALTH = { healthy: ["ok", "Sağlıklı"], unhealthy: ["bad", "Sağlıksız"], starting: ["warn", "Sağlık denetimi başlıyor"] };
  const SOURCE = { appstore: ["App Store", "store", "App Store uygulaması: yaşam döngüsü App Store ile ortaktır"],
    konsol: ["Konsol", "konsol", "Konsol'da tanımlı: ayarları burada düzenlenir"], external: ["Dışarıda", "dis", "Konsol dışında oluşturuldu"] };
  const RESTART = { no: "Hayır", "on-failure": "Hata olursa", always: "Her zaman" };
  // DD-227: the account a Konsol container runs as; writable server folders need the Files account.
  const USERS = { downloads: "Dosyalar hesabı (yetkisiz)", image: "İmajın kendi hesabı (çoğunlukla root)" };
  const ACCOUNT_RULE = "Sunucu klasörüne yalnız Dosyalar hesabıyla yazılabilir: hesabı değiştirin ya da klasörü salt okunur yapın.";
  const writesFolder = (d) => d.mounts.some((m) => m.type === "bind" && !m.read_only);
  const hhmm = (at) => new Date(at * 1000).toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
  const when = (at) => (at ? new Date(at * 1000).toLocaleString("tr-TR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "—");
  const decode = (v) => { try { return decodeURIComponent(v || ""); } catch (_) { return ""; } };
  const can = (c, action) => !!(c && Array.isArray(c.actions) && c.actions.includes(action));
  const running = (c) => !!c && c.state === "running";
  const mono = (t) => h("span", { class: "mono" }, t);
  const lower = (s) => String(s || "").toLocaleLowerCase("tr");
  function scopeOfIp(ip) {
    if (!ip || ip === "0.0.0.0" || ip === "::") return "public";
    if (/^127\./.test(ip) || ip === "::1") return "local";
    if (/^100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\./.test(ip) || /^fd7a:115c:a1e0:/i.test(ip)) return "tailscale";
    return "other";
  }
  // DD-215: sunucu ağındaki (host) konteynerin port eşlemesi yoktur; sunucu, konteynerin kendi süreçlerinin
  // dinlediği soketleri bildirir. Etiket, adresin türüdür; dışarıdan erişimi güvenlik duvarı belirler.
  const LISTEN = { all: "Tüm adresler", wan: "WAN", tailscale: "Tailscale", other: "Belirli adres", local: "Yalnız bu sunucu" };
  const LISTEN_ORDER = ["all", "wan", "tailscale", "other", "local"];
  const hostPort = (address, port) => `${String(address).includes(":") ? `[${address}]` : address}:${port}`;
  const listenLabel = (scopes) => (scopes.length === 1 ? LISTEN[scopes[0]] || scopes[0] : scopes.map((k) => (k === "local" ? "yerel" : LISTEN[k] || k)).join(" · "));
  // Aynı port birden çok adreste (ve TCP ile UDP'de) açılabilir: satırda port başına bir satır, en geniş
  // adresiyle (IPv4 önce); ayrıntıda her adres ayrı satırdır.
  function listenGroups(c) {
    const by = new Map();
    (Array.isArray(c.listening) ? c.listening : []).forEach((s) => {
      if (!s || !Number.isInteger(s.port)) return;
      const g = by.get(s.port) || { port: s.port, protos: new Set(), scopes: new Set(), socks: [] };
      g.protos.add(s.protocol); g.scopes.add(s.scope); g.socks.push(s);
      by.set(s.port, g);
    });
    const rank = (s) => LISTEN_ORDER.indexOf(s.scope) * 2 + (String(s.address).includes(":") ? 1 : 0);
    return [...by.values()].map((g) => ({ port: g.port, protos: ["tcp", "udp"].filter((x) => g.protos.has(x)),
      lead: g.socks.slice().sort((a, b) => rank(a) - rank(b))[0], scopes: LISTEN_ORDER.filter((k) => g.scopes.has(k)) }))
      .sort((a, b) => (a.protos.includes("tcp") ? 0 : 1) - (b.protos.includes("tcp") ? 0 : 1) || a.port - b.port);
  }
  const pct = (v) => (Number.isFinite(v) ? v.toFixed(1).replace(".", ",") + " %" : "—");
  const mem = (v) => (Number.isFinite(v) ? bytes(v) : "—");
  const appName = (c) => { const m = c && c.module_id && appMeta ? appMeta(c.module_id) : null; return m && m.name ? m.name : (c && c.name) || ""; };
  const containersOf = () => (LIST && Array.isArray(LIST.containers) ? LIST.containers : []);
  const rowOf = (name) => containersOf().find((c) => c.name === name) || null;
  // Bir koleksiyonun okunamaması boş liste değildir: sunucunun metni (resource_errors) gösterilir.
  const collectionError = (key) => {
    if (!LIST) return "";
    const errs = LIST.resource_errors || LIST.errors || {};
    if (errs[key]) return String(errs[key]);
    const label = { containers: "Konteynerler", images: "İmajlar", volumes: "Birimler", networks: "Ağlar" }[key];
    return label && !Array.isArray(LIST[key]) ? `${label} okunamadı.` : "";
  };
  // Özetle sabitlenmiş imaj adı kısaltılır (özetin ilk 12 karakteri); tam adı ipucunda kalır.
  const shortImage = (ref) => String(ref || "").replace(/@sha256:([0-9a-f]{12})[0-9a-f]+$/, "@$1…");
  // Seçilebilir ağlar: mantıksal varsayılan "bridge" (sunucu yapılandırılmış Konsol ağını ilk kullanımda kurar; boş
  // sunucuda da sunulur) ve Konsol'un yönettiği köprü ağları. Podman'ın kendi "podman" ağı ve dış ağlar seçilemez.
  const DEFAULT_NET = "bridge";
  const netLabel = (v) => (v === DEFAULT_NET ? "Varsayılan Konsol ağı" : v === "none" ? "Ağ yok" : v || "—");
  function netChoices(keep) {
    const out = [[DEFAULT_NET, netLabel(DEFAULT_NET)]];
    (LIST && Array.isArray(LIST.networks) ? LIST.networks : []).forEach((n) => {
      if (n && n.driver === "bridge" && n.managed === true && n.name !== DEFAULT_NET) out.push([n.name, n.name + (n.internal ? " (iç ağ)" : "")]);
    });
    // Kayıtlı tanımın ağı listede yoksa ilgisiz bir düzenleme onu sessizce değiştirmesin.
    if (keep && !out.some(([v]) => v === keep)) out.push([keep, netLabel(keep) + " (şu anki)"]);
    return out;
  }
  // Podman alt ağ satırları {subnet, gateway} nesneleridir; düz metin de okunur.
  const subnetText = (list) => (Array.isArray(list) ? list : []).map((x) => (typeof x === "string" ? x
    : x && typeof x.subnet === "string" ? x.subnet + (x.gateway ? ` (ağ geçidi ${x.gateway})` : "") : "")).filter(Boolean).join(", ");

  /* ---------------- okuma ---------------- */
  function loadList() {
    const seq = ++listSeq;
    return api(`${BASE}/liste`).then((d) => {
      if (seq !== listSeq) return;
      LIST = d; listError = ""; readAt = Date.now() / 1000;
      if (Number.isFinite(d.read_at) && clock) clock.sync(d.read_at);
      containersOf().forEach((c) => { if (c.busy && /^[0-9a-f]{32}$/.test(c.busy) && !OPS.has(c.busy)) track({ id: c.busy, action: "", target: c.name }, {}); });
      paint();
    }).catch((e) => { if (seq !== listSeq) return; listError = e.message || "Konteyner listesi okunamadı."; paint(); });
  }
  function loadDetail() {
    const name = detailName, seq = ++detailSeq;
    if (!name) return Promise.resolve();
    return api(`${BASE}/ayrinti?ad=${enc(name)}`).then((d) => {
      if (name !== detailName || seq !== detailSeq) return;
      DETAIL = d; detailError = ""; paint();
    }).catch((e) => { if (name !== detailName || seq !== detailSeq) return; DETAIL = null; detailError = e.message; paint(); });
  }
  function loadLog() {
    const name = detailName, seq = ++logSeq, tail = logTail;
    if (!name) return Promise.resolve();
    logLoading = true; paint();
    return api(`${BASE}/gunluk?ad=${enc(name)}&satir=${tail}`).then((r) => {
      if (name !== detailName || seq !== logSeq) return;
      LOG = r; logError = ""; logLoading = false; paint();
    }).catch((e) => { if (name !== detailName || seq !== logSeq) return; logError = e.message; logLoading = false; paint(); });
  }
  function refresh() { loadList(); if (detailName) { loadDetail(); if (section === "gunluk") loadLog(); } }
  // Sayfa açılınca sunucunun önbelleği istenir (eskiyse sunucu yeniden denetler); düğme zorla denetletir.
  function loadUpdates(force) {
    if (updLoading) return Promise.resolve();
    updLoading = true; paint();
    return api(`${BASE}/guncellemeler${force ? "?yenile=1" : ""}`).then((d) => { UPD = d; updError = ""; })
      .catch((e) => { updError = e.message || "Güncellemeler denetlenemedi."; })
      .finally(() => { updLoading = false; paint(); });
  }
  const updOf = (c) => (c && UPD && UPD.items && UPD.items[c.name]) || (c && c.update) || null;

  /* ---------------- işlemler: POST → 202 → izleme ---------------- */
  // Hedef anahtarı: konteyner adı ya da "image:…", "volume:…", "network:…". Aynı hedefe ikinci istek gitmez.
  function submit(payload, target, ctx = {}) {
    if (pending.has(target)) return Promise.reject(new Error("Bu hedefte bir işlem sürüyor."));
    pending.set(target, payload.action);
    lastError.delete(target);
    paint();
    return post(`${BASE}/islem`, payload).then((r) => {
      if (!r || !/^[0-9a-f]{32}$/.test(String(r.id || ""))) throw new Error("İşlem başlatılamadı: sunucu kimlik döndürmedi.");
      track({ id: r.id, action: payload.action, target }, ctx);
      return r;
    }).catch((e) => { pending.delete(target); paint(); throw e; });
  }
  function track(op, ctx) {
    OPS.set(op.id, Object.assign({ state: "running", step: "", error: "", misses: 0 }, op, { ctx }));
    schedule(800);
  }
  function schedule(ms) { clearTimeout(opTimer); if (OPS.size) opTimer = setTimeout(pollOps, document.hidden ? 4000 : ms || 1000); }
  async function pollOps() {
    for (const o of [...OPS.values()]) {
      try {
        const r = await api(`${BASE}/islem?id=${enc(o.id)}`);
        Object.assign(o, { state: r.state || o.state, step: r.step || o.step, error: r.error || "", result: r.result, status: r.status, misses: 0 });
        if (!o.action && r.action) o.action = r.action;
      } catch (e) {
        if (++o.misses > 8) Object.assign(o, { state: "failed", error: `İşlem durumu okunamadı: ${e.message}` });
      }
      if (o.state === "done" || o.state === "failed") { OPS.delete(o.id); finish(o); }
    }
    paint();
    if (SH && SH.opId && OPS.has(SH.opId)) drawSheet();
    schedule(1000);
  }
  function finish(o) {
    pending.delete(o.target);
    const name = String(o.target).replace(/^(image|volume|network):/, "");
    if (o.state === "failed") {
      const text = `${FAILED[o.action] || "İşlem başarısız"}: ${o.error || "nedeni bildirilmedi"}${o.step ? ` (adım: ${o.step})` : ""}`;
      if (!/^(image|volume|network):/.test(o.target)) lastError.set(o.target, text);
      if (!(o.ctx.onFail && o.ctx.onFail(o, text))) toast(`${name}: ${text}`);
    } else {
      if (!(o.ctx.onDone && o.ctx.onDone(o))) { if (o.action && DONE[o.action]) toast(`${name}: ${DONE[o.action]}.`); }
      if (o.action === "remove" && detailName === o.target) go("#/konteynerler");
    }
    loadList();
    if (detailName) loadDetail();
    if (refreshShared) refreshShared();
  }
  const busyOf = (c) => pending.get(c.name) || (c.busy ? ((OPS.get(c.busy) || {}).action || "işlem") : "");
  const busyText = (action) => DOING[action] || "İşleniyor…";

  /* ---------------- yaşam döngüsü ---------------- */
  function lifecycle(c, action) {
    if (!c || busyOf(c) || !can(c, action)) return;
    const run = () => submit({ action, name: c.name, revision: c.revision }, c.name).catch((e) => { lastError.set(c.name, e.message); paint(); toast(`${c.name}: ${e.message}`); });
    if (action !== "stop") { run(); return; }
    const m = c.source === "appstore" && c.module_id && appMeta ? appMeta(c.module_id) : null;
    const items = [["pause", (m && m.stopNote) || "Konteyner durur ve siz başlatana kadar kapalı kalır; sunucu yeniden başlasa da açılmaz."]];
    if (c.source === "appstore") items.push(["stack", "App Store ve Genel bakış aynı durumu gösterir."]);
    if (c.source === "external") items.push(["info", "Bu konteyneri Konsol oluşturmadı; onu yöneten başka bir araç yeniden başlatabilir."]);
    ask({ title: `${c.source === "appstore" ? appName(c) : c.name} durdurulsun mu?`, sub: "Kurulu kalır; istediğinizde başlatırsınız", calm: true, go: "Durdur", items, onOk: run });
  }
  function removeContainer(c) {
    if (!c || busyOf(c) || !can(c, "remove")) return;
    const send = (extra) => submit(Object.assign({ action: "remove", name: c.name, revision: c.revision }, extra || {}), c.name)
      .catch((e) => { lastError.set(c.name, e.message); paint(); toast(`${c.name}: ${e.message}`); });
    if (c.source === "appstore") {
      const m = (c.module_id && appMeta && appMeta(c.module_id)) || {};
      const box = h("input", { type: "checkbox", id: "mod-veri" });
      ask({ title: `${appName(c)} kaldırılsın mı?`, sub: "Bu bir App Store uygulaması", go: "Uygulamayı kaldır", danger: true,
        items: [["stack", "Uygulama App Store'dan da kaldırılır: Genel bakış karesi, kenar menüsündeki sayfası ve adresleri gider."], ...(m.removeWhat || []),
          ["folder", "Kullanıcı alanındaki dosyalarınıza dokunulmaz."]],
        extra: h("label", { class: "opt", for: "mod-veri" }, box, h("span", null, m.removeLabel || "Uygulamanın verisini de sil",
          h("small", null, `${m.removeDrop || ""} İşaretlemezseniz: ${m.removeKeep || "veri korunur."}`))),
        onOk: () => send({ with_data: box.checked }) });
      return;
    }
    if (c.source === "external") {
      ask({ title: `${c.name} kaldırılsın mı?`, sub: "Konsol bu konteyneri oluşturmadı", go: "Kaldır", danger: true, word: true,
        items: [["info", "Onu oluşturan araç (betik, başka bir panel) bozulabilir ya da konteyneri yeniden oluşturabilir."], ["disk", "Yalnız konteyner silinir; imaj ve birimler kalır."]],
        onOk: () => send() });
      return;
    }
    ask({ title: `${c.name} kaldırılsın mı?`, sub: running(c) ? "Önce durdurulur" : "Durmuş konteyner", go: "Kaldır", danger: true,
      items: [["box", "Konteyner ve hizmet tanımı kaldırılır."], ["disk", "Adlı birimler kalır; silmek için Birimler sekmesini kullanın."], ["folder", "Sunucu klasörlerine dokunulmaz."]],
      onOk: () => send() });
  }
  function updateImage(c) {
    if (!c || busyOf(c) || !can(c, "image-update")) return;
    const u = updOf(c), app = c.source === "appstore";
    const items = app
      ? [["download", "Kanalın şu an gösterdiği imaj indirilir; birkaç dakika sürebilir."],
        ["refresh", running(c) ? "Uygulama yeni imajla yeniden başlar; süren indirmeler kısa süre durur." : "Uygulama durmuş; başlattığınızda yeni imajla açılır."],
        ["restore", "Açılmazsa önceki imaja dönülür. Profil, ayarlar ve indirilenler korunur."]]
      : [["download", "İmajın etiketi yeniden çekilir ve yeni özetle karşılaştırılır."], ["refresh", "Özet değiştiyse konteyner yeni imajla yeniden oluşturulur; kısa bir kesinti olabilir."],
        ["disk", "Kalıcı veriler bağlamalarda kalır; konteynerin yazılabilir katmanı silinir."]];
    ask({ title: `${appName(c)} güncellensin mi?`, sub: u && u.state === "var" ? `Yeni sürüm yayınlanmış · ${u.channel}` : "Açık istek: kendiliğinden güncelleme yoktur",
      go: "Güncelle", calm: true, items,
      onOk: () => submit({ action: "image-update", name: c.name, revision: c.revision }, c.name, {
        onDone: (o) => {
          const r = o.result || {};
          toast(`${appName(c)}: ${r.changed === false ? "imaj zaten güncel" : "imaj güncellendi" + (r.version ? ` (${r.version})` : "")}.`);
          loadUpdates(false);
          return true;
        } }).catch((e) => toast(`${c.name}: ${e.message}`)) });
  }

  /* ---------------- çizim: ortak parçalar ---------------- */
  function statePill(c) {
    const [tone, label] = STATE[c.state] || ["warn", c.state || "Bilinmiyor"];
    const text = c.state === "exited" ? `Durdu (çıkış ${Number.isFinite(c.exit_code) ? c.exit_code : "?"})` : label;
    return h("span", { class: `hm ${tone}` }, c.state === "running" ? h("span", { class: "dotmark live", "aria-hidden": "true" }) : null, text);
  }
  const healthPill = (hs) => (HEALTH[hs] ? h("span", { class: `hm ${HEALTH[hs][0]}` }, HEALTH[hs][1]) : null);
  const srcBadge = (c) => { const [label, cls, tip] = SOURCE[c.source] || SOURCE.external; return h("span", { class: `pd-src pd-src-${cls}`, title: tip }, label); };
  function icon(c) {
    const m = c.source === "appstore" && c.module_id && appMeta ? appMeta(c.module_id) : null;
    return h("span", { class: `pd-ico ${m && /^t-[a-z]+$/.test(m.tone) ? m.tone : c.source === "konsol" ? "pd-ico-konsol" : ""}`, "aria-hidden": "true" }, svg(m && m.icon ? m.icon : "box"));
  }
  function accessLines(c) {
    if (c.network === "host") {
      const groups = listenGroups(c), shown = groups.slice(0, 3);
      if (!groups.length) return [h("span", null, "Sunucu ağı (host)"),
        Array.isArray(c.listening) && running(c) ? h("span", { class: "pd-muted" }, "Açık port yok") : null].filter(Boolean);
      return shown.map((g) => h("span", { "data-port": String(g.port) }, mono(`${hostPort(g.lead.address, g.port)}/${g.protos.join("+")}`), " ",
        h("span", { class: "pd-muted" }, listenLabel(g.scopes))))
        .concat(groups.length > shown.length ? [h("span", { class: "pd-muted" }, `+${groups.length - shown.length} port daha`)] : []);
    }
    const ports = Array.isArray(c.ports) ? c.ports : [];
    if (!ports.length) return [h("span", { class: "pd-muted" }, "Port yayımlanmıyor")];
    return ports.map((p) => { const sc = p.scope || scopeOfIp(p.host_ip);
      return h("span", null, mono(`${p.host_ip || "0.0.0.0"}:${p.host_port} → ${p.container_port}/${p.protocol || "tcp"}`), " ",
        h("span", { class: sc === "public" ? "hm bad" : "pd-muted" }, SCOPE[sc])); });
  }
  const stampText = () => (readAt ? "Son okuma " + hhmm(readAt) : "Okunuyor…");

  /* ---------------- liste ---------------- */
  function summary() {
    const rt = (LIST && LIST.runtime) || {}, cs = containersOf();
    const run = cs.filter((c) => c.state === "running").length, bad = cs.filter((c) => c.health === "unhealthy").length;
    const st = (LIST && LIST.storage) || {};
    return h("section", { class: "card pd-summary", id: "pd-summary", "aria-label": "Özet" },
      h("div", { class: "pd-rt" }, svg("box"),
        !LIST ? h("span", { class: "hm" }, listError ? "Konteyner listesi okunamadı" : "Okunuyor…")
          : rt.ok ? h("div", null, h("strong", null, `Podman ${rt.version || ""}`), h("small", null, "bu sunucu · rootful · systemd ile yönetilir"))
            : h("span", { class: "hm warn pd-wrap" }, rt.error || "Podman yanıt vermedi")),
      LIST && rt.ok ? h("dl", { class: "pd-counts" },
        h("div", null, h("dt", null, "Çalışıyor"), h("dd", null, String(run))),
        h("div", null, h("dt", null, "Duran"), h("dd", null, String(cs.length - run))),
        h("div", null, h("dt", null, "Sağlıksız"), h("dd", null, String(bad))),
        h("div", null, h("dt", null, "Güncelleme"), h("dd", { id: "pd-upd-count" }, String(cs.filter((c) => (updOf(c) || {}).state === "var").length))),
        h("div", null, h("dt", null, "Depolama"), h("dd", null, Number.isFinite(st.size) ? bytes(st.size) : "—"))) : null,
      listError && LIST ? h("p", { class: "err-s", role: "alert" }, `Son okuma başarısız: ${listError}`) : null,
      LIST && rt.ok && collectionError("stats") ? h("p", { class: "hint-s pd-wide2" }, collectionError("stats")) : null,
      LIST && rt.ok && cs.some((c) => !("source" in c)) ? h("p", { class: "hint-s pd-wide2", role: "status" },
        "Yönetim kayıtları henüz hazır değil: konteynerler salt okunur gösteriliyor. Kurulumu yeniden çalıştırınca işlemler açılır.") : null);
  }
  const TABS = [["konteynerler", "Konteynerler", "box", "containers"], ["imajlar", "İmajlar", "stack", "images"], ["birimler", "Birimler", "disk", "volumes"], ["aglar", "Ağlar", "globe", "networks"]];
  function tabsEl() {
    const count = (key) => (collectionError(key) ? "!" : LIST && Array.isArray(LIST[key]) ? String(LIST[key].length) : "…");
    const choose = (id) => { tab = id; paint("tab:" + id); };
    return h("div", { class: "pd-tabs", role: "tablist", "aria-label": "Konteyner kaynakları",
      onkeydown: (e) => {
        // Oklar odaktaki sekmeden yürür (seçili olandan değil).
        const ids = TABS.map((t) => t[0]), at = String((document.activeElement && document.activeElement.dataset.k) || "").replace(/^tab:/, "");
        let i = ids.indexOf(ids.includes(at) ? at : tab);
        if (e.key === "ArrowRight") i = (i + 1) % ids.length; else if (e.key === "ArrowLeft") i = (i - 1 + ids.length) % ids.length;
        else if (e.key === "Home") i = 0; else if (e.key === "End") i = ids.length - 1; else return;
        e.preventDefault(); choose(ids[i]);
      } },
    TABS.map(([id, label, ic, key]) => h("button", { type: "button", role: "tab", id: "pd-tab-" + id, "data-k": "tab:" + id, "aria-selected": String(tab === id),
      "aria-controls": "pd-tabpanel", tabindex: tab === id ? "0" : "-1", onclick: () => choose(id) }, svg(ic), label, h("span", { class: "pd-count" }, count(key)))));
  }
  function filtered() {
    const q = lower(query.trim());
    return containersOf().filter((c) => {
      if (filter === "calisan" && c.state !== "running") return false;
      if (filter === "duran" && c.state === "running") return false;
      if (filter === "sorunlu" && c.health !== "unhealthy") return false;
      return !q || lower(`${c.name} ${c.image}`).includes(q);
    });
  }
  function containersPanel() {
    const chip = (id, label) => h("button", { type: "button", class: "pd-chip", "data-k": "chip:" + id, "aria-pressed": String(filter === id), onclick: () => { filter = id; paint("chip:" + id); } }, label);
    const tools = h("div", { class: "pd-toolbar" },
      h("label", { class: "pd-search" }, svg("search"), h("span", { class: "vis-hidden" }, "Konteyner ara"),
        h("input", { type: "search", id: "pd-q", placeholder: "Ad ya da imaj ara", value: query, autocomplete: "off", oninput: (e) => { query = e.target.value; paint("id:pd-q"); } })),
      h("div", { class: "pd-chips", role: "group", "aria-label": "Duruma göre süz" }, chip("tum", "Tümü"), chip("calisan", "Çalışan"), chip("duran", "Duran"), chip("sorunlu", "Sağlıksız")),
      h("div", { class: "pd-updtools" },
        h("span", { class: updError ? "err-s" : "hint-s", id: "pd-upd-stamp", role: "status" },
          updLoading ? "Güncellemeler denetleniyor…" : updError ? updError : UPD && UPD.checked_at ? `Güncellemeler ${hhmm(UPD.checked_at)}'de denetlendi` : ""),
        h("button", { type: "button", class: "btn btn-quiet btn-sm", "data-k": "updcheck", id: "pd-upd-check", "aria-disabled": updLoading ? "true" : "false",
          onclick: () => { if (!updLoading) loadUpdates(true); } }, svg("refresh"), "Güncellemeleri denetle")));
    if (!LIST) return [tools, h("section", { class: "card pd-empty" }, h("p", { class: listError ? "err-s" : "hint-s", role: listError ? "alert" : null }, listError || "Okunuyor…"))];
    const rt = LIST.runtime || {};
    const err = !rt.ok ? rt.error || "Podman yanıt vermedi." : collectionError("containers");
    if (err) return [tools, h("section", { class: "card pd-empty", role: "alert" }, h("strong", null, "Konteynerler okunamadı"), h("span", null, err))];
    const rows = filtered();
    if (!containersOf().length) return [tools, h("section", { class: "card pd-empty" }, svg("box"), h("strong", null, "Bu sunucuda konteyner yok"),
      h("span", null, "App Store'dan bir uygulama kurun ya da Yeni konteyner ile bir imajdan oluşturun."))];
    return [tools, h("section", { class: "card pd-table", "aria-label": "Konteynerler" },
      h("div", { class: "pd-row pd-head", "aria-hidden": "true" }, h("span", null, "Ad"), h("span", null, "Durum"), h("span", null, "Kaynak"), h("span", null, "Erişim"), h("span", null, "")),
      rows.length ? rows.map(rowEl) : h("p", { class: "pd-none hint-s" }, "Eşleşen konteyner yok; süzgeci ya da aramayı değiştirin.")),
      h("p", { class: "card pd-note" }, svg("info"), h("span", null, "Yönetim: ", h("b", null, "App Store"), " uygulamaları App Store ile aynı yaşam döngüsünü paylaşır; ",
        h("b", null, "Konsol"), " tanımları burada düzenlenir; ", h("b", null, "Dışarıda"), " oluşturulanlar için Konsol yalnız sunucunun izin verdiği işlemleri gösterir."))];
  }
  function rowEl(c) {
    const busy = busyOf(c), err = lastError.get(c.name);
    return h("div", { class: "pd-row", "data-name": c.name },
      h("div", { class: "pd-c-who" }, rowLead(c), icon(c), h("div", { class: "pd-nm" },
        h("button", { type: "button", class: "pd-open", "data-k": "open:" + c.name, onclick: () => go("#/konteynerler/" + enc(c.name)) }, appName(c)),
        updChip(c))),
      h("div", { class: "pd-c-state" }, busy ? h("span", { class: "hm warn" }, h("span", { class: "spin", "aria-hidden": "true" }), busyText(busy)) : statePill(c), running(c) ? healthPill(c.health) : null,
        c.live === false ? h("span", { class: "hm", title: "Hizmet durunca Podman konteyneri siler; tanım Konsol'da kalır" }, "tanım kayıtlı") : null),
      h("div", { class: "pd-c-res" }, h("span", null, "İşlemci ", pct(c.cpu_percent)), h("span", null, "Bellek ", mem(c.memory_bytes))),
      h("div", { class: "pd-c-access" }, accessLines(c)),
      h("div", { class: "pd-acts pd-acts-end" }, control(c, "remove")),
      c.restricted_reason ? h("p", { class: "pd-reason" }, svg("lock"), h("span", null, c.restricted_reason)) : null,
      err ? errorLine(c.name, err) : null);
  }
  // Son başarısız işlemin satırı: operatör kapatana ya da yeni bir işlem başlayana kadar kalır.
  const errorLine = (name, text) => h("p", { class: "pd-error", role: "alert" }, h("span", null, text),
    h("button", { type: "button", class: "pd-ib pd-dismiss", "data-k": "dismiss:" + name, "aria-label": "Hata bildirimini kapat", title: "Kapat",
      onclick: () => { lastError.delete(name); paint(); } }, svg("close")));
  // Sabit yerler: başlat/durdur ve düzenle adın önünde, kaldır sonda (DD-214). Simgeler ana menünün uygulama
  // kartlarıyla aynıdır: oynat/duraklat, ayarlar (kaydırıcılar), çöp. Yetki yalnız sunucudan gelir.
  function control(c, slot) {
    const busy = busyOf(c), svcAction = running(c) ? "stop" : "start";
    const [action, label, ic, fn] = {
      svc: [svcAction, svcAction === "stop" ? "Durdur" : "Başlat", svcAction === "stop" ? "pause" : "play", () => lifecycle(c, svcAction)],
      edit: ["save", "Düzenle", "sliders", () => openEditor(c.name)],
      remove: ["remove", "Kaldır", "trash", () => removeContainer(c)],
    }[slot];
    const reason = busy ? busyText(busy) : !can(c, action) ? c.restricted_reason || "Sunucu bu işleme izin vermiyor." : "";
    const tip = reason ? `${label}: ${reason}` : label;
    return h("button", { type: "button", class: `pd-ib pd-act-${slot === "svc" ? svcAction : slot}`, "data-act": slot, "data-k": slot + ":" + c.name,
      "aria-label": `${appName(c)}: ${busy && slot === "svc" ? busyText(busy) : tip}`, title: tip, "aria-disabled": reason ? "true" : "false",
      onclick: () => { if (!busyOf(c) && can(c, action)) fn(); } }, svg(busy && slot === "svc" ? "clock" : ic));
  }
  const rowLead = (c) => h("div", { class: "pd-acts pd-acts-lead", role: "group", "aria-label": `${appName(c)} işlemleri` }, control(c, "svc"), control(c, "edit"));
  // DD-214: kanalda yeni imaj varsa adın altında; tıklayınca açık onaylı güncelleme penceresi açılır.
  function updChip(c) {
    const u = updOf(c);
    if (!u || u.state !== "var") return null;
    const ok = can(c, "image-update") && !busyOf(c);
    return h("button", { type: "button", class: "pd-upd", "data-k": "upd:" + c.name, "aria-disabled": ok ? "false" : "true",
      title: ok ? `Yeni imaj yayınlanmış (${u.channel}); güncellemek için tıklayın` : busyOf(c) ? busyText(busyOf(c)) : "Bu konteyner Konsol'dan güncellenemez",
      onclick: () => { if (ok) updateImage(c); } }, svg("up"), "Güncelleme var");
  }

  /* ---------------- ayrıntı ---------------- */
  const SECTIONS = [["genel", "Genel"], ["ag", "Ağ ve portlar"], ["baglama", "Bağlamalar"], ["ortam", "Ortam"], ["sinir", "Başlatma ve sınırlar"], ["gunluk", "Günlük"]];
  // Satır (liste) ve ayrıntı birleşir: ayrıntının bildirdiği alanlar önce gelir, eksikleri satırdan.
  function current() {
    const r = rowOf(detailName), d = DETAIL && DETAIL.name === detailName ? DETAIL : null;
    if (!r && !d) return null;
    const out = Object.assign({}, r || {});
    if (d) for (const [k, v] of Object.entries(d)) if (v !== undefined) out[k] = v;
    return out;
  }
  const UPD_STATE = { var: ["warn", "Yeni sürüm var"], guncel: ["ok", "Güncel"], sabit: ["", "Sabit özet"], denetlenemedi: ["bad", "Denetlenemedi"] };
  function updFact(c) {
    const u = updOf(c);
    if (c.source === "external") return null;
    const [tone, label] = u ? UPD_STATE[u.state] || ["warn", u.state] : ["", updLoading ? "Denetleniyor…" : "Henüz denetlenmedi"];
    const when2 = u && (u.checked_at || (UPD && UPD.checked_at)) ? `${hhmm(u.checked_at || UPD.checked_at)}'de denetlendi` : "";
    const note = !u ? "" : u.state === "sabit" ? "Bir etiket izlemiyor; imaj yalnız elle değişir."
      : [u.channel ? `kanal: ${u.channel}` : "", u.error || "", when2].filter(Boolean).join(" · ");
    return fact("Güncelleme", h("span", { class: `hm ${tone}`, id: "pd-upd-state" }, label), note);
  }
  // DD-215: konteynerin şu an dinlediği her adres; eşleme yok, dışarıdan erişimi güvenlik duvarı belirler.
  function listenTable(c) {
    const socks = Array.isArray(c.listening) ? c.listening : null;
    if (!running(c)) return h("p", { class: "pd-muted", id: "pd-listen" }, "Konteyner çalışmıyor; açık port yok.");
    if (!socks) return h("p", { class: "pd-muted", id: "pd-listen" }, "Dinlenen portlar okunamadı.");
    if (!socks.length) return h("p", { class: "pd-muted", id: "pd-listen" }, "Konteyner şu an hiçbir portu dinlemiyor.");
    return h("div", { class: "pd-stack", id: "pd-listen" },
      h("div", { class: "pd-mini", role: "table", "aria-label": "Dinlenen portlar" },
        h("div", { class: "pd-mrow pd-mhead", role: "row" }, ["Adres türü", "Adres", "Port", "Protokol"].map((t) => h("span", { role: "columnheader" }, t))),
        socks.map((s) => h("div", { class: "pd-mrow", role: "row" }, h("span", { role: "cell" }, LISTEN[s.scope] || s.scope),
          h("span", { role: "cell" }, mono(String(s.address))), h("span", { role: "cell" }, mono(String(s.port))), h("span", { role: "cell" }, String(s.protocol).toUpperCase())))),
      h("p", { class: "pd-muted" }, "Konteynerin şu an dinlediği adresler. Sunucu ağında port eşlemesi yoktur; dışarıdan erişimi sunucunun güvenlik duvarı belirler."));
  }
  function detailView() {
    const c = current();
    const back = h("button", { type: "button", class: "pd-back", "data-k": "back", onclick: () => go("#/konteynerler") }, svg("back"), "Podman");
    if (!c) return [back, h("section", { class: "card pd-empty" }, h("p", { class: detailError ? "err-s" : "hint-s", role: detailError ? "alert" : null }, detailError || "Okunuyor…"))];
    const busy = busyOf(c), run = running(c), err = lastError.get(c.name);
    const btn = (label, ic, act, fn, primary, danger) => h("button", { type: "button", class: `btn ${primary ? "btn-primary" : "btn-quiet"}${danger ? " pd-danger" : ""}`, "data-k": "d:" + act,
      "aria-disabled": busy ? "true" : "false", title: busy ? busyText(busy) : null, onclick: () => { if (!busyOf(c)) fn(); } }, svg(ic), label);
    const bar = [];
    if (busy) bar.push(h("button", { type: "button", class: "btn btn-quiet", "data-k": "d:svc", "aria-disabled": "true" }, h("span", { class: "spin", "aria-hidden": "true" }), busyText(busy)));
    else if (run && can(c, "stop")) bar.push(btn("Durdur", "pause", "svc", () => lifecycle(c, "stop")));
    else if (!run && can(c, "start")) bar.push(btn("Başlat", "play", "svc", () => lifecycle(c, "start"), true));
    if (can(c, "restart") && run) bar.push(btn("Yeniden başlat", "refresh", "restart", () => lifecycle(c, "restart")));
    if (can(c, "save")) bar.push(btn("Düzenle", "sliders", "edit", () => openEditor(c.name)));
    if (can(c, "image-update")) bar.push(btn((updOf(c) || {}).state === "var" ? "Güncelle" : "İmajı güncelle", "up", "update", () => updateImage(c), (updOf(c) || {}).state === "var"));
    if (can(c, "adopt")) bar.push(btn("Sahiplen", "key", "adopt", () => openAdopt(c)));
    if (can(c, "remove")) bar.push(btn(c.source === "appstore" ? "Uygulamayı kaldır" : "Kaldır", "trash", "remove", () => removeContainer(c), false, true));
    const op = c.busy ? OPS.get(c.busy) : null;
    const head = h("section", { class: "card pd-detail-head" },
      h("div", { class: "pd-dtitle" }, icon(c), h("div", null,
        h("h2", { id: "pd-detail-title" }, c.name),
        h("div", { class: "pd-meta" }, busy ? h("span", { class: "hm warn" }, h("span", { class: "spin", "aria-hidden": "true" }), busyText(busy)) : statePill(c), run ? healthPill(c.health) : null, srcBadge(c),
          c.source === "appstore" ? h("span", { class: "pd-muted" }, appName(c)) : null, h("span", { class: "mono pd-muted", title: c.image || null }, shortImage(c.image))))),
      bar.length ? h("div", { class: "pd-bar" }, bar) : null,
      op && op.step ? h("p", { class: "hint-s", role: "status" }, `Adım: ${op.step}`) : null,
      c.restricted_reason ? h("p", { class: "pd-reason" }, svg("lock"), h("span", null, c.restricted_reason)) : null,
      err ? errorLine(c.name, err) : null,
      detailError && DETAIL ? h("p", { class: "err-s" }, `Ayrıntı yenilenemedi: ${detailError}`) : null);
    const choose = (id) => { section = id; if (id === "gunluk") loadLog(); paint("sec:" + id); };
    const secs = h("div", { class: "pd-tabs pd-sec", role: "tablist", "aria-label": "Konteyner bölümleri",
      onkeydown: (e) => {
        const ids = SECTIONS.map((s) => s[0]), at = String((document.activeElement && document.activeElement.dataset.k) || "").replace(/^sec:/, "");
        let i = ids.indexOf(ids.includes(at) ? at : section);
        if (e.key === "ArrowRight") i = (i + 1) % ids.length; else if (e.key === "ArrowLeft") i = (i - 1 + ids.length) % ids.length; else return;
        e.preventDefault(); choose(ids[i]);
      } },
    SECTIONS.map(([id, label]) => h("button", { type: "button", role: "tab", id: "pd-sec-" + id, "data-k": "sec:" + id, "aria-selected": String(section === id),
      "aria-controls": "pd-secpanel", tabindex: section === id ? "0" : "-1", onclick: () => choose(id) }, label)));
    return [back, head, secs, h("div", { class: "pd-panel", id: "pd-secpanel", role: "tabpanel", "aria-labelledby": "pd-sec-" + section }, sectionBody(c))];
  }
  const fact = (dt, dd, small) => h("div", null, h("dt", null, dt), h("dd", null, dd, small ? h("small", null, small) : null));
  const lockNote = (text) => h("span", { class: "pd-lock" }, svg("lock"), text);
  // Etkin açılış durumu: sunucunun effective_autostart değeri (boolean ya da {enabled, reason}); elle durdurma
  // açılış tercihinden önce gelir ve öyle yazılır.
  function autostartText(c) {
    const ea = c.effective_autostart, cfg = c.config || {};
    const reason = ea && typeof ea === "object" ? ea.reason : "";
    const enabled = ea && typeof ea === "object" ? !!ea.enabled : typeof ea === "boolean" ? ea : cfg.autostart !== false && !cfg.manual_stop;
    if (reason === "manual_stop" || cfg.manual_stop) return ["Kapalı · siz durdurdunuz", "Başlat bu durumu kaldırır; açılış tercihi yeniden geçerli olur."];
    if (reason === "external" || c.source === "external") return ["Konsol söz veremez", "Bu konteyneri başka bir araç yönetir; açılışta ne olacağını o belirler."];
    if (reason === "package" || c.source === "appstore") return [enabled ? "Açılışta başlar" : "Kapalı · uygulama durduruldu", "App Store uygulamasının durumu izlenir: durdurulursa açılışta da kapalı kalır."];
    return [enabled ? "Açılışta başlar" : "Açılışta başlamaz", cfg.autostart === false ? "Açılış tercihi kapalı." : ""];
  }
  function sectionBody(c) {
    const cfg = c.config || null, adapter = cfg && "listener_port" in cfg;
    const protectedWhy = new Map((c.protected_mounts || []).map((m) => (typeof m === "string" ? [m, ""] : [m && m.destination, (m && m.reason) || ""])).filter((x) => x[0]));
    const protectedSet = new Set(protectedWhy.keys());
    if (section === "genel") {
      return [c.live === false ? h("p", { class: "card pd-note" }, svg("info"), h("span", null, "Hizmet durduğu için Podman konteyneri şu an yok. Gösterilenler kayıtlı tanımdır; Başlat aynı tanımla yeniden oluşturur.")) : null,
        c.health === "unhealthy" ? h("p", { class: "card pd-note pd-bad" }, svg("info"), h("span", null, "Sağlık denetimi başarısız; nedeni için Günlük bölümüne bakın.")) : null,
        h("section", { class: "card" }, h("h2", null, svg("info"), "Özet"),
          h("dl", { class: "pd-facts" },
            fact("Durum", statePill(c), c.state === "running" && c.started ? `başladı ${since(c.started)}` : c.created ? `oluşturuldu ${when(c.created)}` : ""),
            fact("Sağlık", (running(c) && healthPill(c.health)) || "—", running(c) && c.health ? "salt okunur; denetim imajdan gelir" : ""),
            fact("Yönetim", srcBadge(c), c.source === "appstore" ? appName(c) : c.source === "konsol" ? "Konsol tanımı" : "Konsol dışında"),
            fact("Hizmet", c.unit ? mono(c.unit) : "—"),
            fact("Kimlik", c.id ? mono(c.id) : "—", c.live === false ? "çalışan konteyner yok" : ""),
            fact("İmaj", h("span", { class: "mono", title: c.image || null }, shortImage(c.image) || "—"), cfg && cfg.image_ref && cfg.image_ref !== c.image ? `etiket: ${cfg.image_ref}` : ""),
            updFact(c),
            fact("Yeniden başlatma", String(c.restarts || 0)),
            "user" in c ? fact("Hesap", c.user ? mono(c.user) : "imajın varsayılanı", cfg && cfg.user ? USERS[cfg.user] : "") : null,
            fact("İşlemci", pct(c.cpu_percent), cfg && cfg.cpus ? `sınır ${cfg.cpus} çekirdek` : ""),
            fact("Bellek", mem(c.memory_bytes), cfg && cfg.memory ? `sınır ${cfg.memory}` : ""),
            c.command ? fact("Komut", mono(c.command)) : null))];
    }
    if (section === "ag") {
      const listener = adapter ? fact("Uygulama dinleyicisi", mono(`127.0.0.1:${cfg.listener_port}`), "uygulama ayarı; hizmet, Caddy ve denetimler aynı değeri kullanır") : null;
      if (c.network === "host") return [h("section", { class: "card" }, h("h2", null, svg("globe"), "Ağ ve portlar"),
        adapter ? h("p", { class: "pd-muted" }, "Sunucu ağını (host) kullanır; port eşlemesi yoktur. Uygulama kendi arayüzünde, yalnız sunucunun içinde dinler; dışarıdan Caddy üzerinden açılır.") : null,
        h("dl", { class: "pd-facts" }, fact("Ağ", "Sunucu ağı (host)"), listener), listenTable(c))];
      const ports = cfg && Array.isArray(cfg.ports) ? cfg.ports.map((p) => ({ scope: p.scope, host: p.host_port, ctr: p.container_port, proto: p.protocol }))
        : (c.ports || []).map((p) => ({ scope: p.scope || scopeOfIp(p.host_ip), host: p.host_port, ctr: p.container_port, proto: p.protocol, ip: p.host_ip }));
      // DD-217: an App Store app on its own bridge publishes only what its Quadlet names, per address.
      return [h("section", { class: "card" }, h("h2", null, svg("globe"), "Ağ ve portlar"),
        adapter ? h("p", { class: "pd-muted", id: "pd-app-net" }, "Uygulama kendi köprü ağında çalışır; yalnız aşağıdaki portlar yayımlanır. Arayüz yalnız bu sunucuda açılır, dışarıdan Caddy üzerinden erişilir.") : null,
        h("dl", { class: "pd-facts" }, fact("Ağ", adapter ? mono(c.network || "—") : netFact(cfg && cfg.network, c.network)), listener),
        ports.length ? h("div", { class: "pd-mini", role: "table", "aria-label": "Portlar" },
          h("div", { class: "pd-mrow pd-mhead", role: "row" }, ["Erişim", "Sunucu", "Konteyner", "Protokol"].map((t) => h("span", { role: "columnheader" }, t))),
          ports.map((p) => h("div", { class: "pd-mrow", role: "row" },
            h("span", { role: "cell" }, p.scope === "public" ? h("span", { class: "hm bad" }, SCOPE.public) : SCOPE[p.scope] || p.scope),
            h("span", { role: "cell" }, mono(`${p.ip || ""}${p.ip ? ":" : ""}${p.host}`)), h("span", { role: "cell" }, mono(String(p.ctr))), h("span", { role: "cell" }, String(p.proto || "tcp").toUpperCase()))))
          : h("p", { class: "pd-muted" }, adapter && !running(c) ? "Uygulama çalışmadığı için şu an port yayımlanmıyor." : "Port yayımlanmıyor; konteynere yalnız aynı ağdaki konteynerler ulaşır."),
        ports.some((p) => p.scope === "public") ? h("p", { class: "pd-error" }, "İnternete açık port Konsol oturumunu ve Caddy TLS'yi atlar; uygulamanın kendi kimlik doğrulamasına güvenir.") : null)];
    }
    if (section === "baglama") {
      const observed = Array.isArray(c.mounts) ? c.mounts : [];
      const rows = cfg && Array.isArray(cfg.mounts)
        ? cfg.mounts.map((m) => ({ type: m.type, src: m.source, dst: m.destination, ro: !!m.read_only }))
        : observed.map((m) => ({ type: m.type, src: m.name || m.source, dst: m.destination, ro: m.rw === false }));
      return [h("section", { class: "card" }, h("h2", null, svg("disk"), "Bağlamalar"),
        rows.length ? h("div", { class: "pd-mini", role: "table", "aria-label": "Bağlamalar" },
          h("div", { class: "pd-mrow pd-mhead", role: "row" }, ["Kaynak", "Konteynerde", "Erişim", ""].map((t) => h("span", { role: "columnheader" }, t))),
          rows.map((m) => h("div", { class: "pd-mrow", role: "row" },
            h("span", { role: "cell" }, h("span", { class: "pd-kind" }, m.type === "volume" ? "birim" : m.type === "bind" ? "klasör" : m.type || "?"), " ", mono(m.src || "—")),
            h("span", { role: "cell" }, mono(m.dst || "—")), h("span", { role: "cell" }, m.ro ? "Salt okunur" : "Okuma-yazma"),
            h("span", { role: "cell" }, protectedSet.has(m.dst) ? lockNote(protectedWhy.get(m.dst) ? `korunur · ${protectedWhy.get(m.dst)}` : "uygulama verisi · korunur")
              : adapter && cfg.save && m.dst === cfg.save ? lockNote("kayıt klasörü · uygulama ayarı") : null))))
          : h("p", { class: "pd-muted" }, "Bağlama yok: konteyner yeniden oluşturulursa içindeki veriler silinir."),
        h("p", { class: "pd-muted" }, "Bağlama yolunu değiştirmek dosyaları taşımaz. Konteyneri kaldırmak adlı birimleri silmez."))];
    }
    if (section === "ortam") {
      const env = cfg && Array.isArray(cfg.environment) ? cfg.environment : null;
      return [h("section", { class: "card" }, h("h2", null, svg("key"), "Ortam değişkenleri"),
        env ? (env.length ? h("div", { class: "pd-mini", role: "table", "aria-label": "Ortam değişkenleri" },
          h("div", { class: "pd-mrow pd-mhead pd-m2", role: "row" }, ["Ad", "Değer"].map((t) => h("span", { role: "columnheader" }, t))),
          env.map((e) => h("div", { class: "pd-mrow pd-m2", role: "row" }, h("span", { role: "cell" }, mono(e.name)),
            h("span", { role: "cell" }, e.secret ? lockNote("gizli · gösterilmez") : mono(e.value || ""))))) : h("p", { class: "pd-muted" }, "Ortam değişkeni yok."))
          : h("p", { class: "pd-muted" }, adapter ? "Uygulamanın ortamını paket yönetir; burada gösterilmez." : "Bu konteynerin ortamı Konsol'da tanımlı değil; değerleri gösterilmez."),
        h("p", { class: "pd-muted" }, "Gizli değerler sunucudan tarayıcıya hiç gönderilmez."))];
    }
    if (section === "sinir") {
      const [text, note] = autostartText(c);
      return [h("section", { class: "card" }, h("h2", null, svg("clock"), "Başlatma ve sınırlar"),
        h("dl", { class: "pd-facts" },
          fact("Açılışta", text, note),
          cfg && "autostart" in cfg ? fact("Açılış tercihi", cfg.autostart ? "Açık" : "Kapalı") : null,
          cfg && cfg.restart ? fact("Yeniden başlatma", RESTART[cfg.restart] || cfg.restart) : null,
          cfg && "cpus" in cfg ? fact("İşlemci sınırı", cfg.cpus ? `${cfg.cpus} çekirdek` : "Yok") : null,
          cfg && "memory" in cfg ? fact("Bellek sınırı", cfg.memory || "Yok") : null),
        cfg && !adapter ? h("p", { class: "pd-muted" }, "İşlemci ve bellek sınırı canlı uygulanabilir; port, bağlama, ağ ve imaj değişiklikleri konteyneri yeniden oluşturur.") : null)];
    }
    // günlük
    const q = lower(logQuery.trim());
    const lines = LOG && Array.isArray(LOG.lines) ? LOG.lines.map(String) : [];
    const shown = q ? lines.filter((l) => lower(l).includes(q)) : lines;
    const mark = (line) => { if (!q) return line; const i = lower(line).indexOf(q); if (i < 0) return line; return [line.slice(0, i), h("mark", null, line.slice(i, i + q.length)), line.slice(i + q.length)]; };
    return [h("section", { class: "card" }, h("div", { class: "pd-head2" }, h("h2", null, svg("list"), "Günlük"), h("small", { class: "hint-s" }, `son ${logTail} satır · en yenisi altta`)),
      h("div", { class: "pd-logtools" },
        h("label", { class: "pd-search" }, svg("search"), h("span", { class: "vis-hidden" }, "Günlükte ara"),
          h("input", { type: "search", id: "pd-logq", placeholder: "Günlükte ara", value: logQuery, autocomplete: "off", oninput: (e) => { logQuery = e.target.value; paint("id:pd-logq"); } })),
        h("div", { class: "pd-tail", role: "group", "aria-label": "Satır sayısı" }, TAILS.map((n) => h("button", { type: "button", class: "btn btn-sm btn-quiet", "data-k": "tail:" + n,
          "aria-pressed": String(n === logTail), onclick: () => { logTail = n; loadLog(); } }, String(n)))),
        h("button", { type: "button", class: "btn btn-sm btn-quiet", "data-k": "logrefresh", onclick: () => loadLog() }, svg("refresh"), "Günlüğü yenile")),
      logError ? h("p", { class: "err-s", role: "alert" }, logError) : null,
      h("div", { class: "pd-log", tabindex: "0", role: "log", "aria-label": `${c.name} günlüğü` },
        logLoading && !LOG ? h("span", { class: "pd-muted" }, "Okunuyor…") : shown.length ? shown.map((l) => h("div", { class: "pd-line" }, mark(l))) : h("span", { class: "pd-muted" }, q ? "Eşleşen satır yok." : "Günlük kaydı yok.")),
      // DD-251: the log as written, no filter: a Konsol or App Store container's lines come from its unit's journal.
      h("p", { class: "pd-muted" }, "Günlük olduğu gibi, filtresiz gösterilir; uygulamanın yazdığı parola ve belirteçler de görünür. Konsol ve App Store konteynerlerinde yeniden başlatmalardan önceki satırlar da vardır."))];
  }

  /* ---------------- kaynak sekmeleri ---------------- */
  function resourceTable(key, cols, rows, empty) {
    const err = collectionError(key);
    if (err) return h("section", { class: "card pd-empty", role: "alert" }, h("strong", null, "Okunamadı"), h("span", null, err));
    if (!LIST) return h("section", { class: "card pd-empty" }, h("p", { class: "hint-s" }, "Okunuyor…"));
    if (!rows.length) return h("section", { class: "card pd-empty" }, h("span", null, empty));
    return h("section", { class: "card pd-table pd-rtable", "aria-label": cols.label },
      h("div", { class: `pd-res pd-head pd-res-${key}`, "aria-hidden": "true" }, cols.head.map((t) => h("span", null, t))), rows);
  }
  function removeButton(label, reason, target, onOk) {
    const busy = pending.has(target);
    return h("button", { type: "button", class: "pd-ib", "data-act": "remove", "data-k": "rm:" + target, "aria-label": `${label} sil`,
      title: busy ? "İşlem sürüyor" : reason || "Sil", "aria-disabled": reason || busy ? "true" : "false",
      onclick: () => { if (reason) { toast(reason); return; } if (!busy) onOk(); } }, busy ? svg("clock") : svg("trash"));
  }
  const usedText = (list) => (Array.isArray(list) && list.length ? list.join(", ") : null);
  function imagesPanel() {
    const imgs = LIST && Array.isArray(LIST.images) ? LIST.images : [];
    const rows = imgs.map((i) => {
      const used = usedText(i.used_by), target = "image:" + i.id;
      const reason = i.pinned ? "Paket imajı: App Store paketi sabitler; güncellemesi kurulumla gelir." : used ? `Kullanımda: ${used}. Önce konteyneri kaldırın.` : "";
      return h("div", { class: "pd-res pd-res-images", "data-name": i.name },
        h("span", { class: "pd-rname" }, mono(i.name), i.pinned ? h("span", { class: "pd-src pd-src-store" }, "paket") : null, !i.managed ? h("span", { class: "pd-src pd-src-dis" }, "dışarıda") : null),
        h("span", { "data-l": "Kimlik" }, mono(String(i.id || "").replace(/^sha256:/, "").slice(0, 12))),
        h("span", { "data-l": "Boyut" }, Number.isFinite(i.size) ? bytes(i.size) : "—"),
        h("span", { "data-l": "Kullanan" }, used || h("span", { class: "hm" }, "kullanılmıyor")),
        h("span", { class: "pd-racts" }, pending.has(target) ? h("span", { class: "hm warn" }, busyText(pending.get(target))) : null,
          removeButton(i.name, reason, target, () => ask({ title: `${i.name} silinsin mi?`, sub: "Kullanılmayan imaj", go: "Sil", danger: true,
            items: [["stack", "İmaj sunucudan silinir; gerekirse yeniden çekilir."]],
            onOk: () => submit({ action: "image-remove", image: i.id }, target).catch((e) => toast(`${i.name}: ${e.message}`)) }))));
    });
    return [h("div", { class: "pd-toolbar" }, h("button", { type: "button", class: "btn btn-primary btn-sm", "data-k": "pull", onclick: () => openSmall("pull") }, svg("download"), "İmaj çek")),
      resourceTable("images", { label: "İmajlar", head: ["İmaj", "Kimlik", "Boyut", "Kullanan", ""] }, rows, "İmaj yok."),
      h("p", { class: "card pd-note" }, svg("info"), h("span", null, "Paket imajları App Store paketinin özetiyle sabittir; güncellemeleri kurulumla gelir. Konsol konteynerlerinde imajı güncellemek açık bir istektir ve konteyneri yeniden oluşturabilir."))];
  }
  function volumesPanel() {
    const vols = LIST && Array.isArray(LIST.volumes) ? LIST.volumes : [];
    const rows = vols.map((v) => {
      const used = usedText(v.used_by), target = "volume:" + v.name;
      return h("div", { class: "pd-res pd-res-volumes", "data-name": v.name },
        h("span", { class: "pd-rname" }, mono(v.name), !v.managed ? h("span", { class: "pd-src pd-src-dis" }, "dışarıda") : null),
        h("span", { "data-l": "Sürücü" }, v.driver || "—"),
        h("span", { "data-l": "Boyut" }, Number.isFinite(v.size) ? bytes(v.size) : "—"),
        h("span", { "data-l": "Kullanan" }, used || h("span", { class: "hm warn" }, "kullanılmıyor")),
        h("span", { class: "pd-racts" }, pending.has(target) ? h("span", { class: "hm warn" }, busyText(pending.get(target))) : null,
          removeButton(v.name, used ? `Kullanımda: ${used}. Önce konteyneri kaldırın.` : "", target, () => ask({ title: `${v.name} silinsin mi?`, sub: "Kullanılmayan birim", go: "Birimi sil", danger: true,
            items: [["disk", "Birimdeki bütün veri kalıcı olarak silinir; geri alınamaz."]],
            onOk: () => submit({ action: "volume-remove", name: v.name }, target).catch((e) => toast(`${v.name}: ${e.message}`)) }))));
    });
    return [h("div", { class: "pd-toolbar" }, h("button", { type: "button", class: "btn btn-primary btn-sm", "data-k": "newvol", onclick: () => openSmall("volume") }, svg("plus"), "Yeni birim")),
      resourceTable("volumes", { label: "Birimler", head: ["Birim", "Sürücü", "Boyut", "Kullanan", ""] }, rows, "Birim yok."),
      h("p", { class: "card pd-note" }, svg("info"), h("span", null, "Birim (volume), Podman'ın konteynerden bağımsız sakladığı adlı veri alanıdır: konteyner kaldırılınca kalır, yalnız burada açıkça silinir. Sunucu klasörleri burada değil, Dosyalar'dadır."))];
  }
  function netFact(saved, live) {
    const v = saved || live;
    if (v !== DEFAULT_NET) return mono(v || "—");
    return live && live !== DEFAULT_NET ? h("span", null, netLabel(v) + " · ", mono(live)) : netLabel(v);
  }
  function networksPanel() {
    const nets = LIST && Array.isArray(LIST.networks) ? LIST.networks : [];
    const rows = nets.map((n) => {
      const used = usedText(n.used_by), target = "network:" + n.name;
      const reason = !n.managed ? "Konsol yönetmiyor; silinemez." : used ? `Kullanımda: ${used}.` : "";
      return h("div", { class: "pd-res pd-res-networks", "data-name": n.name },
        h("span", { class: "pd-rname" }, mono(n.name), n.internal ? h("span", { class: "hm" }, "iç ağ") : null, !n.managed ? h("span", { class: "pd-src pd-src-dis" }, "sistem") : null),
        h("span", { "data-l": "Sürücü" }, n.driver || "—"),
        h("span", { "data-l": "Alt ağ" }, mono(subnetText(n.subnets) || "—")),
        h("span", { "data-l": "Kullanan" }, used || "—"),
        h("span", { class: "pd-racts" }, pending.has(target) ? h("span", { class: "hm warn" }, busyText(pending.get(target))) : null,
          removeButton(n.name, reason, target, () => ask({ title: `${n.name} ağı silinsin mi?`, sub: "Kullanılmayan köprü ağı", go: "Ağı sil", danger: true,
            items: [["globe", "Ağ ve onun güvenlik duvarı kuralları kaldırılır."]],
            onOk: () => submit({ action: "network-remove", name: n.name }, target).catch((e) => toast(`${n.name}: ${e.message}`)) }))));
    });
    return [h("div", { class: "pd-toolbar" }, h("button", { type: "button", class: "btn btn-primary btn-sm", "data-k": "newnet", onclick: () => openSmall("network") }, svg("plus"), "Yeni ağ")),
      resourceTable("networks", { label: "Ağlar", head: ["Ağ", "Sürücü", "Alt ağ", "Kullanan", ""] }, rows, "Ağ yok."),
      h("p", { class: "card pd-note" }, svg("info"), h("span", null, "Köprü ağlarındaki portlar seçilen erişime göre açılır; sunucu ağını (host) kullanan uygulamalar port eşlemesi kullanmaz. Yalnız köprü ağı oluşturulur."))];
  }

  /* ---------------- pencere (düzenle, oluştur, sahiplen, küçük formlar) ---------------- */
  sheet.addEventListener("close", () => {
    const s = SH; SH = null; sheetSeq++;
    sheet.querySelectorAll("input[type=password]").forEach((i) => { i.value = ""; });
    if (s && s.opener && s.opener.isConnected) s.opener.focus();
  });
  const mine = (seq) => SH && SH.seq === seq && sheet.open;
  // Açık pencere kapatılıp yeniden açılmaz: kapanış olayı sonradan gelip yeni durumu silerdi. İçerik ve kimlik
  // değişir, odak dönüşü ilk açanda kalır.
  function openSheet(init) {
    const opener = sheet.open && SH ? SH.opener : document.activeElement;
    SH = Object.assign({ seq: ++sheetSeq, step: "form", error: "", opener, opId: "", start: false }, init);
    sheet.classList.toggle("pd-small", !!SH.small);
    drawSheet();
    if (!sheet.open) sheet.showModal();
    const first = sheet.querySelector(".pd-body input:not([readonly]):not([type=checkbox]), .pd-body select, .pd-body textarea");
    if (first) first.focus(); else sheet.querySelector(".pd-x")?.focus();
  }
  function openEditor(name) {
    const c = rowOf(name) || current();
    const seq = sheetSeq + 1;
    openSheet({ mode: "loading", name, title: `${name} · düzenle` });
    api(`${BASE}/ayrinti?ad=${enc(name)}`).then((d) => {
      if (!mine(seq)) return;
      const cfg = d.config;
      if (!cfg || typeof cfg !== "object") { SH.mode = "message"; SH.error = "Bu konteynerin düzenlenebilir bir tanımı yok."; drawSheet(); return; }
      const adapter = "listener_port" in cfg;
      Object.assign(SH, { mode: adapter ? "adapter" : "edit", revision: d.revision || (c && c.revision), editable: d.editable || [], protectedMounts: d.protected_mounts || [],
        mounts: d.mounts || [], running: d.state === "running", network: d.network || "", orig: JSON.parse(JSON.stringify(cfg)), draft: adapter ? adapterDraft(cfg) : draftFrom(cfg) });
      drawSheet(true);
    }).catch((e) => { if (!mine(seq)) return; SH.mode = "message"; SH.error = e.message; drawSheet(); });
  }
  function openCreate() {
    if (!LIST || !(LIST.runtime || {}).ok) return;
    openSheet({ mode: "create", name: "", title: "Yeni konteyner", start: true, editable: ["image", "network", "ports", "mounts", "environment", "command", "autostart", "restart", "cpus", "memory", "user"],
      orig: null, draft: draftFrom({ network: DEFAULT_NET, autostart: true, restart: "on-failure", user: "downloads" }) });
  }
  function openAdopt(c) {
    if (!c || busyOf(c) || !can(c, "adopt")) return;
    const seq = sheetSeq + 1;
    openSheet({ mode: "adopt-wait", name: c.name, title: `${c.name} · sahiplen`, start: running(c) });
    submit({ action: "adopt", name: c.name, preview: true }, c.name, {
      onDone: (o) => {
        if (!mine(seq)) { toast(`${c.name}: sahiplenme önizlemesi hazır; Sahiplen ile yeniden açın.`); return true; }
        const pv = o.result && o.result.preview;
        if (!pv || !pv.config) { SH.mode = "message"; SH.error = "Sunucu önizleme döndürmedi."; drawSheet(); return true; }
        const draft = draftFrom(pv.config);
        draft.ports.forEach((p) => { p.current = p.scope; p.scope = ""; p.public_ack = false; p.was_public = false; });
        if (!netChoices().some(([v]) => v === draft.network)) draft.network = DEFAULT_NET;
        Object.assign(SH, { mode: "adopt", preview: pv, draft, orig: null, fingerprint: pv.fingerprint, unsupported: Array.isArray(pv.unsupported) ? pv.unsupported : [] });
        drawSheet(true); return true;
      },
      onFail: (o, text) => { if (!mine(seq)) return false; SH.mode = "message"; SH.error = text; drawSheet(); return true; },
    }).catch((e) => { if (!mine(seq)) { toast(`${c.name}: ${e.message}`); return; } SH.mode = "message"; SH.error = e.message; drawSheet(); });
  }
  function openSmall(kind) {
    const title = { pull: "İmaj çek", volume: "Yeni birim", network: "Yeni ağ" }[kind];
    openSheet({ mode: kind, small: true, title, draft: { image: "", name: "", subnet: "", internal: false }, tried: false });
  }
  function draftFrom(cfg) {
    return {
      name: cfg.name || "", image: cfg.image || "", image_ref: cfg.image_ref || cfg.image || "", network: cfg.network || "",
      ports: (cfg.ports || []).map((p) => ({ scope: p.scope || "local", host_port: p.host_port != null ? String(p.host_port) : "", container_port: p.container_port != null ? String(p.container_port) : "",
        protocol: p.protocol || "tcp", public_ack: !!p.public_ack, was_public: p.scope === "public" })),
      mounts: (cfg.mounts || []).map((m) => ({ type: m.type === "bind" ? "bind" : "volume", source: m.source || "", destination: m.destination || "", read_only: !!m.read_only })),
      environment: (cfg.environment || []).map((e) => (e.secret ? { name: e.name || "", value: "", secret: true, stored: !!e.present } : { name: e.name || "", value: e.value != null ? String(e.value) : "", secret: false })),
      command: Array.isArray(cfg.command) ? cfg.command.join("\n") : "", autostart: cfg.autostart !== false, restart: cfg.restart || "on-failure", cpus: cfg.cpus || "", memory: cfg.memory || "",
      user: cfg.user === "downloads" ? "downloads" : "image",
    };
  }
  const editable = (f) => SH && (SH.mode === "create" || (SH.editable || []).includes(f));
  // Taslağı sunucunun yapılandırma biçimine çevirir. Değişmemiş gizli değer değersiz gider (sunucu korur).
  function configOut(d) {
    const imageChanged = !SH.orig || d.image_ref !== (SH.orig.image_ref || SH.orig.image || "");
    return { name: d.name.trim(), image: imageChanged ? d.image_ref.trim() : d.image, image_ref: d.image_ref.trim(), network: d.network,
      ports: d.ports.map((p) => ({ scope: p.scope, host_port: Number(p.host_port), container_port: Number(p.container_port), protocol: p.protocol, public_ack: p.scope === "public" && !!(p.public_ack || p.was_public) })),
      mounts: d.mounts.map((m) => ({ type: m.type, source: m.source.trim(), destination: m.destination.trim(), read_only: !!m.read_only })),
      environment: d.environment.map((e) => (e.secret ? (e.value !== "" ? { name: e.name.trim(), value: e.value, secret: true } : { name: e.name.trim(), secret: true }) : { name: e.name.trim(), value: e.value, secret: false })),
      command: d.command.split("\n").map((s) => s.trim()).filter(Boolean), autostart: !!d.autostart, restart: d.restart, cpus: d.cpus.trim(), memory: d.memory.trim(), user: d.user };
  }
  function problems(d) {
    const out = {};
    const add = (k, m) => { (out[k] = out[k] || []).push(m); };
    if (SH.mode === "create") {
      if (!NAME_RE.test(d.name.trim())) add("name", "Ad küçük harfle başlar; küçük harf, rakam ve - içerir (2–31 karakter).");
      else if (rowOf(d.name.trim())) add("name", "Bu ad kullanılıyor.");
    }
    if ((SH.mode === "create" || editable("image")) && !IMAGE_RE.test(d.image_ref.trim())) add("image", "İmajın tam adını yazın: kayıt adresi, depo ve etiket (ör. docker.io/library/nginx:1.27-alpine).");
    if (editable("network") && !netChoices(SH.orig && SH.orig.network).some(([v]) => v === d.network)) add("network", "Bir ağ seçin.");
    if (d.user !== "downloads" && writesFolder(d)) add("user", ACCOUNT_RULE);
    const seen = new Set();
    d.ports.forEach((p, i) => {
      const k = "p" + i, hp = Number(p.host_port), cp = Number(p.container_port);
      if (!p.scope) add(k, "Erişimi seçin.");
      if (!(Number.isInteger(hp) && hp >= 1 && hp <= 65535) || !(Number.isInteger(cp) && cp >= 1 && cp <= 65535)) add(k, "Portlar 1–65535 arasında bir sayı olmalı.");
      const key = `${p.scope}:${hp}/${p.protocol}`;
      if (p.scope && seen.has(key)) add(k, "Aynı erişimde bu port iki kez var."); seen.add(key);
      if (p.scope === "public" && !p.public_ack && !p.was_public) add(k, "İnternete açık port için onay kutusunu işaretleyin.");
    });
    d.mounts.forEach((m, i) => {
      const k = "m" + i;
      if (m.type === "volume" && !RES_NAME_RE.test(m.source.trim())) add(k, "Birim adı küçük harf, rakam ve - _ . içerir.");
      if (m.type === "bind" && !/^\/[^\0]*$/.test(m.source.trim())) add(k, "Sunucu klasörü mutlak bir yol olmalı (/srv/… gibi).");
      if (!/^\/[^\0]*$/.test(m.destination.trim())) add(k, "Konteynerdeki yol / ile başlamalı.");
    });
    const names = new Set();
    d.environment.forEach((e, i) => {
      const k = "e" + i, n = e.name.trim();
      if (!ENV_RE.test(n)) add(k, "Değişken adı harf ya da _ ile başlar; harf, rakam ve _ içerir.");
      else if (names.has(n)) add(k, "Bu ad iki kez var."); names.add(n);
    });
    if (d.cpus.trim() && !/^\d+(\.\d+)?$/.test(d.cpus.trim())) add("cpus", "İşlemci sınırı bir sayı olmalı (ör. 1.5).");
    if (d.memory.trim() && !/^\d+(\.\d+)?[kmg]?b?$/i.test(d.memory.trim())) add("memory", "Bellek sınırı sayı ve birim olmalı (ör. 512m, 2g).");
    return out;
  }
  // Uygulama bağdaştırıcısının bildirdiği alanlar; eş portu yalnız onu bildiren uygulamada vardır (DD-221).
  const adapterDraft = (cfg) => Object.assign({ listener_port: String(cfg.listener_port), save: cfg.save || "" }, "peer_port" in cfg ? { peer_port: String(cfg.peer_port) } : {});
  function adapterProblems(d) {
    const out = {}, port = Number(d.listener_port);
    if (!(Number.isInteger(port) && port >= 1024 && port <= 65535)) out.listener = ["Arayüz portu 1024–65535 arasında bir sayı olmalı."];
    if ("peer_port" in d) {
      const peer = Number(String(d.peer_port).trim());
      if (!(/^\d+$/.test(String(d.peer_port).trim()) && peer >= 1024 && peer <= 65535)) out.peer = ["Eş portu 1024–65535 arasında bir sayı olmalı."];
      else if (peer === port) out.peer = ["Eş portu arayüz portundan farklı olmalı."];
    }
    if (!/^\/[^\0]*$/.test(d.save.trim())) out.save = ["Kayıt klasörü mutlak bir yol olmalı."];
    return out;
  }
  // Doğrulama için çizer; odak, olaydan sonra operatörün bulunduğu öğede kalır (Tab ile ilerleyen geri çekilmez).
  function redraw(focusId) {
    const seq = SH && SH.seq;
    setTimeout(() => {
      if (!mine(seq)) return;
      const body = sheet.querySelector(".pd-body"), top = body ? body.scrollTop : 0;
      const a = document.activeElement, id = focusId || (a && sheet.contains(a) ? a.id : "");
      const sel = a && a.id === id && typeof a.selectionStart === "number" ? [a.selectionStart, a.selectionEnd] : null;
      drawSheet();
      const nb = sheet.querySelector(".pd-body"); if (nb) nb.scrollTop = top;
      const el = id && document.getElementById(id);
      if (el) { el.focus({ preventScroll: true }); if (sel && typeof el.setSelectionRange === "function") try { el.setSelectionRange(sel[0], sel[1]); } catch (_) { /* tür izin vermez */ } }
    }, 0);
  }
  function drawSheet(focusFirst) {
    if (!SH) return;
    const s = SH;
    const head = h("div", { class: "pd-shead" }, h("div", null, h("h2", { id: "pd-sheet-title" }, s.title), h("p", null, subtitle(s))),
      h("button", { type: "button", class: "pd-ib pd-x", id: "pd-x", "aria-label": "Kapat", onclick: () => sheet.close() }, svg("close")));
    const steps = ["edit", "adapter", "create"].includes(s.mode) ? h("ol", { class: "pd-steps", "aria-label": "Adımlar" },
      ["Düzenle", "Gözden geçir", "Uygula"].map((t, i) => h("li", { "aria-current": ["form", "review", "apply"][i] === s.step ? "step" : null }, `${i + 1}. ${t}`))) : null;
    let body, foot;
    if (s.mode === "loading" || s.mode === "adopt-wait") {
      body = h("div", { class: "pd-body" }, h("p", { class: "hint-s", role: "status" }, h("span", { class: "spin", "aria-hidden": "true" }), s.mode === "loading" ? " Tanım okunuyor…" : " Sunucu sahiplenme önizlemesini hazırlıyor…"));
      foot = h("div", { class: "pd-foot" }, h("span"), h("button", { type: "button", class: "btn btn-quiet", id: "pd-close", onclick: () => sheet.close() }, "Kapat"));
    } else if (s.mode === "message") {
      body = h("div", { class: "pd-body" }, h("p", { class: "err-s", role: "alert" }, s.error));
      foot = h("div", { class: "pd-foot" }, h("span"), h("button", { type: "button", class: "btn btn-quiet", id: "pd-close", onclick: () => sheet.close() }, "Kapat"));
    } else if (["pull", "volume", "network"].includes(s.mode)) ({ body, foot } = smallForm(s));
    else if (s.mode === "adopt") ({ body, foot } = adoptForm(s));
    else if (s.step === "form") ({ body, foot } = s.mode === "adapter" ? adapterForm(s) : editForm(s));
    else if (s.step === "review") ({ body, foot } = reviewStep(s));
    else ({ body, foot } = applyStep(s));
    const a = document.activeElement, keep = a && sheet.contains(a) ? a.id : "";
    sheet.replaceChildren(h("div", { class: "pd-sheetin" }, head, steps, body, foot));
    if (focusFirst) { const f = sheet.querySelector(".pd-body input:not([readonly]):not([type=checkbox]), .pd-body select"); if (f) f.focus(); }
    else if (keep && document.getElementById(keep)) document.getElementById(keep).focus({ preventScroll: true });
    else if (keep) (sheet.querySelector("#pd-apply, #pd-review, #pd-close") || sheet.querySelector(".pd-x")).focus({ preventScroll: true });
  }
  function subtitle(s) {
    if (s.mode === "create") return "Konsol tanımı saklar ve systemd ile çalıştırır";
    if (s.mode === "adapter") return "App Store uygulaması: yalnız paketin izin verdiği alanlar";
    if (s.mode === "edit") return "Taslak; kaydetmeden önce değişiklikleri görürsünüz";
    if (s.mode === "adopt" || s.mode === "adopt-wait") return "Sunucu önizlemesi; erişimi siz seçersiniz";
    if (s.mode === "pull") return "Tam ad ve etiket; çekilince özete sabitlenir";
    if (s.mode === "volume") return "Konteynerden bağımsız adlı veri alanı";
    if (s.mode === "network") return "Yalnız köprü ağı";
    return "";
  }
  const errs = (list) => (list && list.length ? h("p", { class: "pd-ferr", role: "alert" }, list.join(" ")) : null);
  const input = (id, value, set, attrs = {}) => h("input", Object.assign({ class: "pd-inp", id, value, autocomplete: "off", spellcheck: "false",
    oninput: (e) => set(e.target.value), onchange: () => redraw() }, attrs));
  const field = (label, control, hint, problem) => h("label", { class: "pd-field" }, h("span", null, label), control, hint ? h("small", null, hint) : null, errs(problem));
  function editForm(s) {
    const d = s.draft, pr = problems(d);
    const ro = (f) => !editable(f);
    const sections = [];
    if (s.mode === "create") {
      sections.push(h("fieldset", { class: "pd-fs" }, h("legend", null, svg("stack"), "İmaj ve ad"),
        field("İmaj", input("pd-f-image", d.image_ref, (v) => { d.image_ref = v; }, { placeholder: "docker.io/library/nginx:1.27-alpine", class: "pd-inp mono", "aria-invalid": pr.image && d.image_ref ? "true" : null }),
          "Çekildiğinde özete (sha256) sabitlenir; güncelleme yalnız sizin isteğinizle olur.", d.image_ref ? pr.image : null),
        field("Ad", input("pd-f-name", d.name, (v) => { d.name = v; }, { placeholder: "ornek-uygulama", class: "pd-inp mono", "aria-invalid": pr.name && d.name ? "true" : null }),
          "Ad sonradan değişmez.", d.name ? pr.name : null)));
    } else {
      sections.push(h("fieldset", { class: "pd-fs" }, h("legend", null, svg("stack"), "İmaj"),
        field("İmaj (etiket)", input("pd-f-image", d.image_ref, (v) => { d.image_ref = v; }, { class: "pd-inp mono", readonly: ro("image") }),
          ro("image") ? "Bu kaynakta imaj değiştirilemez." : "Etiketi değiştirmek konteyneri yeni imajla yeniden oluşturur.", pr.image)));
    }
    sections.push(h("fieldset", { class: "pd-fs" }, h("legend", null, svg("globe"), "Ağ ve portlar"),
      field("Ağ", h("select", { class: "pd-inp", id: "pd-f-network", disabled: ro("network"), onchange: (e) => { d.network = e.target.value; redraw(); } },
        netChoices(s.orig && s.orig.network).map(([v, label]) => h("option", { value: v, selected: v === d.network }, label))),
        d.network === DEFAULT_NET ? "Sunucu bu ağı ilk kullanımda kendisi kurar." : null, pr.network),
      h("p", { class: "pd-muted" }, svg("lock"), " Yeni port ", h("b", null, "Yalnız bu sunucu"), " ile başlar. Tailscale ve İnternet açıkça seçilir."),
      d.ports.map((p, i) => portRow(d, p, i, pr["p" + i], ro("ports"))),
      ro("ports") ? null : h("div", null, h("button", { type: "button", class: "btn btn-quiet btn-sm", id: "pd-add-port", onclick: () => { d.ports.push({ scope: "local", host_port: "", container_port: "", protocol: "tcp", public_ack: false, was_public: false }); redraw(`pd-p${d.ports.length - 1}-host`); } }, svg("plus"), "Port ekle"))));
    sections.push(h("fieldset", { class: "pd-fs" }, h("legend", null, svg("disk"), "Bağlamalar"),
      h("p", { class: "pd-muted" }, "Bir bağlamanın yolunu değiştirmek dosyaları taşımaz; yalnız eşlemeyi değiştirir. Konteyneri yeniden oluşturmak, bağlanmamış yollardaki veriyi siler."),
      d.mounts.map((m, i) => mountRow(d, m, i, pr["m" + i], ro("mounts"))),
      ro("mounts") ? null : h("div", null, h("button", { type: "button", class: "btn btn-quiet btn-sm", id: "pd-add-mount", onclick: () => { d.mounts.push({ type: "volume", source: "", destination: "", read_only: false }); redraw(`pd-m${d.mounts.length - 1}-src`); } }, svg("plus"), "Bağlama ekle"))));
    sections.push(h("fieldset", { class: "pd-fs" }, h("legend", null, svg("key"), "Ortam"),
      d.environment.map((e, i) => envRow(d, e, i, pr["e" + i], ro("environment"))),
      ro("environment") ? null : h("div", null, h("button", { type: "button", class: "btn btn-quiet btn-sm", id: "pd-add-env", onclick: () => { d.environment.push({ name: "", value: "", secret: false }); redraw(`pd-e${d.environment.length - 1}-name`); } }, svg("plus"), "Değişken ekle")),
      h("p", { class: "pd-muted" }, "Kayıtlı gizli değerler tarayıcıya gönderilmez; boş bırakırsanız korunur, satırı silerseniz değişken kalkar.")));
    sections.push(h("fieldset", { class: "pd-fs" }, h("legend", null, svg("clock"), "Komut, başlatma ve sınırlar"),
      field("Çalıştıran hesap", h("select", { class: "pd-inp", id: "pd-f-user", disabled: ro("user"), onchange: (e) => { d.user = e.target.value; redraw(); } },
        Object.entries(USERS).map(([k, v]) => h("option", { value: k, selected: d.user === k }, v))),
        "Dosyalar hesabıyla sunucu klasörlerindeki dosyalar Dosyalar'la aynı sahipte olur ve yetki yoktur. İmajın kendi hesabı sunucu klasörünü yalnız salt okunur bağlayabilir.", pr.user),
      field("Komut (her satır bir argüman)", h("textarea", { class: "pd-inp mono", id: "pd-f-command", rows: "2", readonly: ro("command"), oninput: (e) => { d.command = e.target.value; }, onchange: () => redraw() }, d.command), "Boşsa imajın kendi komutu çalışır."),
      h("label", { class: "pd-check" }, h("input", { type: "checkbox", id: "pd-f-autostart", checked: d.autostart, disabled: ro("autostart"), onchange: (e) => { d.autostart = e.target.checked; redraw(); } }),
        h("span", null, "Açılışta başlat", h("small", null, "Siz durdurursanız bu tercih ne olursa olsun kapalı kalır; Başlat bu durumu kaldırır."))),
      field("Yeniden başlatma", h("select", { class: "pd-inp", id: "pd-f-restart", disabled: ro("restart"), onchange: (e) => { d.restart = e.target.value; redraw(); } },
        Object.entries(RESTART).map(([k, v]) => h("option", { value: k, selected: d.restart === k }, v)))),
      h("div", { class: "pd-two" },
        field("İşlemci sınırı (çekirdek)", input("pd-f-cpus", d.cpus, (v) => { d.cpus = v; }, { placeholder: "sınırsız", readonly: ro("cpus") }), null, pr.cpus),
        field("Bellek sınırı", input("pd-f-memory", d.memory, (v) => { d.memory = v; }, { placeholder: "sınırsız (ör. 512m)", readonly: ro("memory") }), null, pr.memory))));
    s.check = () => {
      const nothing = s.mode === "edit" && !changes(s).length, blocked = Object.keys(problems(d)).length > 0;
      return { blocked: blocked || nothing, why: nothing ? "Değişiklik yok." : blocked ? "Önce işaretli alanları düzeltin." : "Henüz hiçbir şey uygulanmadı." };
    };
    return { body: h("div", { class: "pd-body" }, sections), foot: footer(s, "Değişiklikleri gözden geçir", () => { s.step = "review"; s.error = ""; drawSheet(); sheet.querySelector("#pd-review-title")?.focus(); }) };
  }
  function portRow(d, p, i, pr, ro) {
    return h("div", { class: "pd-erow pd-erow-port" },
      field("Erişim", h("select", { class: "pd-inp", id: `pd-p${i}-scope`, disabled: ro, onchange: (e) => { p.scope = e.target.value; if (p.scope !== "public") p.public_ack = false; redraw(); } },
        [["local", SCOPE.local], ["tailscale", SCOPE.tailscale], ["public", SCOPE.public]].map(([k, v]) => h("option", { value: k, selected: p.scope === k }, v)))),
      field("Sunucu portu", input(`pd-p${i}-host`, p.host_port, (v) => { p.host_port = v; }, { inputmode: "numeric", readonly: ro })),
      field("Konteyner portu", input(`pd-p${i}-ctr`, p.container_port, (v) => { p.container_port = v; }, { inputmode: "numeric", readonly: ro })),
      field("Protokol", h("select", { class: "pd-inp", id: `pd-p${i}-proto`, disabled: ro, onchange: (e) => { p.protocol = e.target.value; redraw(); } }, ["tcp", "udp"].map((x) => h("option", { value: x, selected: p.protocol === x }, x.toUpperCase())))),
      ro ? h("span") : h("button", { type: "button", class: "pd-ib pd-rm", id: `pd-p${i}-rm`, "aria-label": `${i + 1}. portu kaldır`, title: "Kaldır", onclick: () => { d.ports.splice(i, 1); redraw("pd-add-port"); } }, svg("trash")),
      p.scope === "public" && !p.was_public ? h("label", { class: "pd-check pd-wide pd-warnbox" }, h("input", { type: "checkbox", id: `pd-p${i}-ack`, checked: !!p.public_ack, onchange: (e) => { p.public_ack = e.target.checked; redraw(); } }),
        h("span", null, "Bu portun internetten herkese açık olacağını anlıyorum", h("small", null, "Konsol oturumunu ve Caddy TLS'yi atlar; erişimi yalnız uygulamanın kendi protokolü ve kimlik doğrulaması korur. Web uygulamaları için Ayarlar → Caddy yayını daha güvenlidir."))) : null,
      pr ? h("div", { class: "pd-wide" }, errs(pr)) : null);
  }
  function mountRow(d, m, i, pr, ro) {
    return h("div", { class: "pd-erow pd-erow-mount" },
      field("Tür", h("select", { class: "pd-inp", id: `pd-m${i}-type`, disabled: ro, onchange: (e) => { m.type = e.target.value; redraw(); } },
        h("option", { value: "volume", selected: m.type === "volume" }, "Birim"), h("option", { value: "bind", selected: m.type === "bind" }, "Klasör"))),
      field(m.type === "volume" ? "Birim adı" : "Sunucu klasörü", input(`pd-m${i}-src`, m.source, (v) => { m.source = v; }, { class: "pd-inp mono", readonly: ro, list: m.type === "volume" ? "pd-volumes" : null })),
      field("Konteynerde", input(`pd-m${i}-dst`, m.destination, (v) => { m.destination = v; }, { class: "pd-inp mono", readonly: ro })),
      h("label", { class: "pd-check" }, h("input", { type: "checkbox", id: `pd-m${i}-ro`, checked: m.read_only, disabled: ro, onchange: (e) => { m.read_only = e.target.checked; redraw(); } }), "Salt okunur"),
      ro ? h("span") : h("button", { type: "button", class: "pd-ib pd-rm", id: `pd-m${i}-rm`, "aria-label": `${i + 1}. bağlamayı kaldır`, title: "Kaldır", onclick: () => { d.mounts.splice(i, 1); redraw("pd-add-mount"); } }, svg("trash")),
      pr ? h("div", { class: "pd-wide" }, errs(pr)) : null,
      i === 0 ? h("datalist", { id: "pd-volumes" }, (LIST && Array.isArray(LIST.volumes) ? LIST.volumes : []).map((v) => h("option", { value: v.name }))) : null);
  }
  function envRow(d, e, i, pr, ro) {
    return h("div", { class: "pd-erow pd-erow-env" },
      field("Ad", input(`pd-e${i}-name`, e.name, (v) => { e.name = v; }, { class: "pd-inp mono", readonly: ro || (e.secret && e.stored), "data-env-name": e.name })),
      field("Değer", input(`pd-e${i}-value`, e.value, (v) => { e.value = v; }, { class: "pd-inp mono", type: e.secret ? "password" : "text", readonly: ro, "data-env": e.name,
        placeholder: e.secret && e.stored ? "kayıtlı · boş bırakılırsa korunur" : "", autocomplete: e.secret ? "new-password" : "off" })),
      h("label", { class: "pd-check" }, h("input", { type: "checkbox", id: `pd-e${i}-secret`, checked: e.secret, disabled: ro || e.stored, onchange: (ev) => { e.secret = ev.target.checked; redraw(); } }), "Gizli"),
      ro ? h("span") : h("button", { type: "button", class: "pd-ib pd-rm", id: `pd-e${i}-rm`, "aria-label": `${e.name || i + 1} değişkenini kaldır`, title: "Kaldır", onclick: () => { d.environment.splice(i, 1); redraw("pd-add-env"); } }, svg("trash")),
      pr ? h("div", { class: "pd-wide" }, errs(pr)) : null);
  }
  function adapterForm(s) {
    const d = s.draft, pr = adapterProblems(d), ed = (f) => (s.editable || []).includes(f);
    const prot = new Map((s.protectedMounts || []).map((m) => (typeof m === "string" ? [m, ""] : [m && m.destination, (m && m.reason) || ""])).filter((x) => x[0]));
    const fixed = (s.mounts || []).filter((m) => prot.has(m.destination));
    const body = h("div", { class: "pd-body" },
      h("fieldset", { class: "pd-fs" }, h("legend", null, svg("globe"), "Uygulama dinleyicisi"),
        h("p", { class: "pd-muted" }, s.network === "host" ? "Sunucu ağını (host) kullanır; port eşlemesi yoktur. Bu port uygulamanın kendi ayarına, hizmetine, Caddy yönlendirmesine ve denetimlerine birlikte uygulanır."
          : "Arayüz yalnız 127.0.0.1'de yayımlanır. Bu port uygulamanın kendi ayarına, yayın satırına, Caddy yönlendirmesine ve denetimlerine birlikte uygulanır."),
        field("Arayüz portu (yalnız 127.0.0.1)", input("pd-f-listener", d.listener_port, (v) => { d.listener_port = v; }, { inputmode: "numeric", readonly: !ed("listener_port") }), null, pr.listener),
        "peer_port" in d ? field("Eş portu (WAN IPv4, TCP+UDP)", input("pd-f-peer", d.peer_port, (v) => { d.peer_port = v; }, { inputmode: "numeric", readonly: !ed("peer_port") }),
          "Eşler bu porttan bağlanır. 61000–65535 arası önerilir: sunucunun giden bağlantılar için kullandığı 32768–60999 aralığının dışındadır.", pr.peer) : null),
      h("fieldset", { class: "pd-fs" }, h("legend", null, svg("disk"), "Bağlamalar"),
        field("Kayıt klasörü (uygulama ayarı)", h("span", { class: "pd-pick" }, input("pd-f-save", d.save, (v) => { d.save = v; }, { class: "pd-inp mono", readonly: true }),
          ed("save") ? h("button", { type: "button", class: "btn btn-quiet btn-sm", id: "pd-pick-save", "aria-expanded": String(!!s.picker), onclick: () => { s.picker = !s.picker; if (s.picker) browse(s); else redraw("pd-pick-save"); } }, svg("folder"), "Klasör seç") : null),
          "Konteynerde aynı yolla görünür; var olan dosyalar taşınmaz.", pr.save),
        s.picker ? pickerEl(s) : null,
        fixed.map((m) => h("p", { class: "pd-fixed" }, lockNote("korunur"), " ", mono(`${m.source} → ${m.destination}`), h("span", { class: "pd-muted" }, ` · ${prot.get(m.destination) || "uygulama verisi"}; burada değiştirilemez`)))));
    s.check = () => {
      const nothing = !changes(s).length, blocked = Object.keys(adapterProblems(d)).length > 0;
      return { blocked: blocked || nothing, why: nothing ? "Değişiklik yok." : blocked ? "Önce işaretli alanları düzeltin." : "Hesap ayarları uygulamanın kendi ayar penceresindedir." };
    };
    return { body, foot: footer(s, "Değişiklikleri gözden geçir", () => { s.step = "review"; s.error = ""; drawSheet(); sheet.querySelector("#pd-review-title")?.focus(); }) };
  }
  function pickerEl(s) {
    const box = h("div", { class: "pd-picker", id: "pd-picker" }, h("p", { class: "hint-s" }, s.pickItems ? "" : "Klasörler okunuyor…"));
    if (s.pickError) box.replaceChildren(h("p", { class: "err-s" }, s.pickError));
    else if (s.pickItems) box.replaceChildren(...[s.pickAt ? h("button", { type: "button", class: "btn btn-quiet btn-sm", onclick: () => browse(s) }, svg("back"), "Başlangıç dizinleri") : null,
      ...s.pickItems.map((x) => h("div", { class: "pd-pickrow" }, mono(x.path),
        h("button", { type: "button", class: "btn btn-quiet btn-sm", "aria-label": `${x.path} içine gir`, onclick: () => browse(s, x.path) }, "İçine gir"),
        h("button", { type: "button", class: "btn btn-primary btn-sm", "aria-label": `${x.path} seç`, onclick: () => { s.draft.save = x.path; s.picker = false; redraw("pd-pick-save"); } }, "Seç")))].filter(Boolean));
    return box;
  }
  function browse(s, at) {
    const seq = s.seq;
    s.pickItems = null; s.pickError = ""; s.pickAt = at || "";
    drawSheet();
    api("/api/konsol/ayarlar/klasorler" + (at ? "?path=" + enc(at) : "")).then((r) => { if (!mine(seq)) return; s.pickItems = Array.isArray(r.items) ? r.items : []; drawSheet(); })
      .catch((e) => { if (!mine(seq)) return; s.pickError = e.message; drawSheet(); });
  }
  // Düğmenin durumu yazarken de güncel kalır (aşağıdaki input dinleyicisi); tıklamada yeniden denetlenir.
  function footer(s, label, next) {
    const st = s.check();
    return h("div", { class: "pd-foot" }, h("span", { class: "pd-muted", role: "status", id: "pd-foot-status" }, st.why),
      h("div", { class: "pd-foot-btns" }, h("button", { type: "button", class: "btn btn-quiet", id: "pd-cancel", onclick: () => sheet.close() }, "Vazgeç"),
        h("button", { type: "button", class: "btn btn-primary", id: "pd-review", "aria-disabled": st.blocked ? "true" : "false",
          onclick: () => { if (s.check().blocked) { redraw("pd-review"); return; } next(); } }, label)));
  }
  sheet.addEventListener("input", () => {
    if (!SH || !SH.check || SH.step !== "form") return;
    const st = SH.check(), b = document.getElementById("pd-review"), t = document.getElementById("pd-foot-status");
    if (b) b.setAttribute("aria-disabled", st.blocked ? "true" : "false");
    if (t) t.textContent = st.why;
  });
  // Değişiklik listesi: [tür (add|del|chg), alan, metin]; incelemede ve "değişiklik yok" kararında kullanılır.
  function changes(s) {
    const out = [];
    if (s.mode === "adapter") {
      const o = s.orig, d = s.draft;
      if (String(o.listener_port) !== String(d.listener_port).trim()) out.push(["chg", "Arayüz portu", `${o.listener_port} → ${String(d.listener_port).trim()}`]);
      if ("peer_port" in d && String(o.peer_port) !== String(d.peer_port).trim()) out.push(["chg", "Eş portu", `${o.peer_port} → ${String(d.peer_port).trim()}`]);
      if ((o.save || "") !== d.save) out.push(["chg", "Kayıt klasörü", `${o.save || "—"} → ${d.save}`]);
      return out;
    }
    const d = configOut(s.draft), o = s.orig;
    const pk = (p) => `${SCOPE[p.scope] || p.scope} ${p.host_port} → ${p.container_port}/${p.protocol}`;
    const mk = (m) => `${m.type === "volume" ? "birim" : "klasör"} ${m.source} → ${m.destination}${m.read_only ? " (salt okunur)" : ""}`;
    const ek = (e) => (e.secret ? `${e.name} (gizli${"value" in e ? ", yeni değer" : ""})` : `${e.name}=${e.value}`);
    if (!o) {
      out.push(["add", "Ad", d.name], ["add", "İmaj", d.image_ref], ["add", "Ağ", netLabel(d.network)]);
      d.ports.forEach((p) => out.push(["add", "Port", pk(p)])); d.mounts.forEach((m) => out.push(["add", "Bağlama", mk(m)]));
      d.environment.forEach((e) => out.push(["add", "Ortam", ek(e)]));
      if (d.command.length) out.push(["add", "Komut", d.command.join(" ")]);
      out.push(["add", "Başlatma", `${d.autostart ? "açılışta başlar" : "açılışta başlamaz"} · ${RESTART[d.restart] || d.restart}`]);
      if (d.cpus) out.push(["add", "İşlemci", d.cpus]); if (d.memory) out.push(["add", "Bellek", d.memory]);
      out.push(["add", "Hesap", USERS[d.user]]);
      return out;
    }
    const list = (a, b, key, label) => { const A = new Set(a.map(key)), B = new Set(b.map(key));
      a.map(key).filter((x) => !B.has(x)).forEach((x) => out.push(["del", label, x])); b.map(key).filter((x) => !A.has(x)).forEach((x) => out.push(["add", label, x])); };
    if ((o.image_ref || o.image) !== d.image_ref) out.push(["chg", "İmaj", `${o.image_ref || o.image} → ${d.image_ref}`]);
    if ((o.network || "") !== d.network) out.push(["chg", "Ağ", `${netLabel(o.network)} → ${netLabel(d.network)}`]);
    list(o.ports || [], d.ports, pk, "Port");
    list(o.mounts || [], d.mounts, mk, "Bağlama");
    const oe = (o.environment || []).map((e) => (e.secret ? { name: e.name, secret: true } : { name: e.name, value: e.value, secret: false }));
    list(oe, d.environment, ek, "Ortam");
    if ((o.command || []).join("\n") !== d.command.join("\n")) out.push(["chg", "Komut", d.command.join(" ") || "imajın komutu"]);
    if ((o.autostart !== false) !== d.autostart) out.push(["chg", "Açılışta", d.autostart ? "başlar" : "başlamaz"]);
    if ((o.restart || "on-failure") !== d.restart) out.push(["chg", "Yeniden başlatma", RESTART[d.restart] || d.restart]);
    if ((o.cpus || "") !== d.cpus) out.push(["chg", "İşlemci", `${o.cpus || "sınırsız"} → ${d.cpus || "sınırsız"}`]);
    if ((o.memory || "") !== d.memory) out.push(["chg", "Bellek", `${o.memory || "sınırsız"} → ${d.memory || "sınırsız"}`]);
    if ((o.user || "image") !== d.user) out.push(["chg", "Hesap", `${USERS[o.user || "image"]} → ${USERS[d.user]}`]);
    return out;
  }
  function reviewStep(s) {
    const list = changes(s), create = s.mode === "create", adapter = s.mode === "adapter";
    const stopped = !create && !s.running;
    // Sunucu her kayıtta çalışan konteyneri durdurur, yeniden oluşturur ve başlatır (sınır ve başlatma ayarları dahil);
    // durmuş olan durmuş kalır. Uygulama bağdaştırıcısı durmuş durumu kendisi korur, "başlat" seçeneği sunulmaz.
    const items = [];
    if (create) items.push(["info", "İmaj çekilir ve özete sabitlenir; tanım Konsol'a kaydedilir, systemd hizmeti yazılır."]);
    else if (adapter && stopped) items.push(["ok", "Uygulama durmuş olduğu için kesinti olmaz: ayarlar kaydedilir ve uygulama durmuş kalır."]);
    else if (adapter) items.push(["warn", "Uygulama durdurulup yeni ayarlarla yeniden başlatılır; bu sırada kısa süre erişilemez."]);
    else if (stopped) items.push(["warn", "Konteyner durmuş olduğu için kesinti olmaz: tanım kaydedilir, başlattığınızda yeni ayarlarla yeniden oluşturulur. Siz başlatana kadar durmuş kalır."]);
    else items.push(["warn", "Her kayıtta çalışan konteyner durdurulup yeni ayarlarla yeniden oluşturulur; bu sırada hizmet kısa süre kesilir."]);
    if (!create && !adapter && !stopped) items.push(["bad", "Konteynerin yazılabilir katmanı silinir; kalıcı veriler yalnız bağlamalarda durur."]);
    if (list.some(([, k]) => k === "Bağlama" || k === "Kayıt klasörü")) items.push(["warn", "Bağlama değişikliği dosya taşımaz; eski klasör ya da birim olduğu gibi kalır."]);
    if (list.some(([kind, k, v]) => kind === "add" && k === "Port" && v.startsWith(SCOPE.public))) items.push(["bad", "İnternete açık port Konsol oturumunu ve Caddy TLS'yi atlar; uygulamanın kendi kimlik doğrulamasına güvenir."]);
    if (s.draft && s.draft.user === "downloads" && list.some(([, k]) => k === "Hesap"))
      items.push(["warn", "Önceden kullanılmış ya da imajdaki bir klasörün üzerine bağlanan birim sahibini korur; Dosyalar hesabı ona yazamayabilir. Root gerektiren ya da 1024 altında port açan imajlar başlamayabilir."]);
    if (list.some(([, k]) => k === "Eş portu")) items.push(["warn", "Eski eş portu internete kapanır, yenisi WAN IPv4 adresinde TCP ve UDP olarak açılır; eşler yeni portu bir sonraki duyuruda öğrenir."]);
    if (s.mode === "adapter") items.push(["info", "Uygulama ayarı, hizmet, Caddy yönlendirmesi ve denetimler aynı değerle birlikte güncellenir."]);
    const icon = { info: "info", ok: "check", warn: "info", bad: "info" };
    const body = h("div", { class: "pd-body" },
      h("h3", { id: "pd-review-title", tabindex: "-1" }, s.mode === "create" ? "Oluşturulacak" : `${list.length} değişiklik`),
      h("div", { class: "pd-diff" }, list.map(([kind, k, v]) => h("div", { class: "pd-d-" + kind }, h("b", null, { add: "+ ", del: "− ", chg: "~ " }[kind] + k), h("span", null, kind === "del" ? h("del", null, v) : v)))),
      h("ul", { class: "pd-conseq" }, items.map(([tone, t]) => h("li", { class: "pd-c-" + tone }, svg(icon[tone]), h("span", null, t)))),
      create || (stopped && !adapter) ? h("label", { class: "pd-check" }, h("input", { type: "checkbox", id: "pd-f-start", checked: !!s.start, onchange: (e) => { s.start = e.target.checked; } }),
        h("span", null, s.mode === "create" ? "Oluşturunca başlat" : "Kaydettikten sonra başlat", h("small", null, s.mode === "create" ? "İşaretlemezseniz oluşturulur ama başlatılmaz." : "İşaretlemezseniz durmuş kalır."))) : null,
      s.error ? h("div", { class: "pd-failbox", role: "alert" }, h("strong", null, "Uygulanamadı"), h("span", null, s.error),
        s.stale ? h("button", { type: "button", class: "btn btn-quiet btn-sm", onclick: () => openEditor(s.name) }, svg("refresh"), "Güncel tanımı yükle") : null) : null);
    const label = create ? (s.start ? "Oluştur ve başlat" : "Oluştur") : stopped ? "Kaydet" : adapter ? "Uygula ve yeniden başlat" : "Uygula ve yeniden oluştur";
    const foot = h("div", { class: "pd-foot" }, h("button", { type: "button", class: "btn btn-quiet", id: "pd-back", onclick: () => { s.step = "form"; s.error = ""; drawSheet(); } }, svg("back"), "Geri"),
      h("div", { class: "pd-foot-btns" }, h("button", { type: "button", class: "btn btn-quiet", id: "pd-cancel", onclick: () => sheet.close() }, "Vazgeç"),
        h("button", { type: "button", class: "btn btn-primary", id: "pd-apply", "aria-disabled": s.sending ? "true" : "false", onclick: () => apply(s) }, label)));
    return { body, foot };
  }
  function apply(s) {
    if (s.sending || !mine(s.seq)) return;
    let payload, target;
    if (s.mode === "create") { const cfg = configOut(s.draft); payload = { action: "create", config: cfg, start: !!s.start }; target = cfg.name; }
    else if (s.mode === "adapter") {
      const config = { listener_port: Number(String(s.draft.listener_port).trim()), save: s.draft.save };
      if ("peer_port" in s.draft) config.peer_port = Number(String(s.draft.peer_port).trim());
      payload = { action: "save", name: s.name, revision: s.revision, config, start: false }; target = s.name;
    }
    else { payload = { action: "save", name: s.name, revision: s.revision, config: configOut(s.draft), start: !s.running && !!s.start }; target = s.name; }
    s.sending = true; s.error = ""; s.stale = false; drawSheet();
    const seq = s.seq;
    submit(payload, target, {
      onDone: (o) => { if (mine(seq)) sheet.close(); toast(`${target}: ${DONE[payload.action]}.`); return true; },
      onFail: (o, text) => { if (!mine(seq)) return false; s.step = "apply"; s.failed = text; s.sending = false; drawSheet(); return true; },
    }).then((r) => { if (!mine(seq)) return; s.opId = r.id; s.step = "apply"; s.sending = false; drawSheet(); })
      .catch((e) => { if (!mine(seq)) { toast(`${target}: ${e.message}`); return; } s.sending = false; s.error = e.message; s.stale = /değişti|güncel|revision/i.test(e.message); drawSheet(); });
  }
  function applyStep(s) {
    const o = s.opId ? OPS.get(s.opId) : null;
    const body = h("div", { class: "pd-body" },
      s.failed ? h("div", { class: "pd-failbox", role: "alert" }, h("strong", null, "Uygulanamadı"), h("span", null, s.failed), h("span", { class: "pd-muted" }, "Konteynerin gerçek durumu listede yenilendi."))
        : h("p", { class: "pd-progress", role: "status" }, h("span", { class: "spin", "aria-hidden": "true" }), h("span", null, o && o.step ? o.step : "İşlem sunucuda başladı…")),
      s.failed ? null : h("p", { class: "pd-muted" }, "Pencereyi kapatsanız da işlem sunucuda sürer; sonucu bildirim olarak görürsünüz."));
    const foot = h("div", { class: "pd-foot" }, s.failed ? h("button", { type: "button", class: "btn btn-quiet", id: "pd-back", onclick: () => { s.step = "form"; s.failed = ""; s.opId = ""; drawSheet(); } }, svg("back"), "Düzenlemeye dön") : h("span"),
      h("button", { type: "button", class: "btn btn-quiet", id: "pd-close", onclick: () => sheet.close() }, "Kapat"));
    return { body, foot };
  }
  function adoptForm(s) {
    const d = s.draft, unsupported = s.unsupported || [];
    const missing = d.ports.some((p) => !p.scope || (p.scope === "public" && !p.public_ack));
    const account = d.user !== "downloads" && writesFolder(d);
    const blocked = unsupported.length > 0 || missing || account || s.sending;
    const body = h("div", { class: "pd-body" },
      h("p", { class: "pd-muted" }, "Sunucu bu konteynerin ayarlarını okudu. Sahiplenince Konsol tanımına dönüştürülür ve bir kez Konsol hizmetiyle yeniden oluşturulur (kısa kesinti; yazılabilir katman silinir)."),
      unsupported.length ? h("div", { class: "pd-failbox", role: "alert" }, h("strong", null, "Sahiplenilemez: desteklenmeyen seçenekler"), h("ul", null, unsupported.map((u) => h("li", null, String(u))))) : null,
      h("fieldset", { class: "pd-fs" }, h("legend", null, svg("stack"), "Okunan ayarlar"),
        h("dl", { class: "pd-facts" }, fact("İmaj", mono(d.image_ref || "—")), fact("Ağ", mono((rowOf(s.name) || {}).network || "—")),
          fact("Bağlamalar", d.mounts.length ? d.mounts.map((m) => `${m.source} → ${m.destination}`).join(", ") : "yok"),
          fact("Ortam", d.environment.length ? d.environment.map((e) => e.name + (e.secret ? " (gizli)" : "")).join(", ") : "yok"),
          fact("Yeniden başlatma", RESTART[d.restart] || d.restart))),
      h("fieldset", { class: "pd-fs" }, h("legend", null, svg("globe"), "Ağ ve portların erişimi"),
        field("Ağ", h("select", { class: "pd-inp", id: "pd-f-network", onchange: (e) => { d.network = e.target.value; redraw(); } },
          netChoices().map(([v, label]) => h("option", { value: v, selected: v === d.network }, label))), `Şu an: ${(rowOf(s.name) || {}).network || "bilinmiyor"}`),
        d.ports.length ? null : h("p", { class: "pd-muted" }, "Yayımlanan port yok."),
        d.ports.map((p, i) => h("div", { class: "pd-erow pd-erow-adopt" },
          field(`${p.host_port} → ${p.container_port}/${p.protocol}`, h("select", { class: "pd-inp", id: `pd-p${i}-scope`, onchange: (e) => { p.scope = e.target.value; if (p.scope !== "public") p.public_ack = false; redraw(); } },
            h("option", { value: "", selected: !p.scope }, "Erişimi seçin…"), [["local", SCOPE.local], ["tailscale", SCOPE.tailscale], ["public", SCOPE.public]].map(([k, v]) => h("option", { value: k, selected: p.scope === k }, v))),
            `Şu an: ${SCOPE[p.current] || p.current || "bilinmiyor"}`),
          p.scope === "public" ? h("label", { class: "pd-check pd-warnbox" }, h("input", { type: "checkbox", id: `pd-p${i}-ack`, checked: !!p.public_ack, onchange: (e) => { p.public_ack = e.target.checked; redraw(); } }),
            h("span", null, "Bu portun internetten herkese açık kalacağını anlıyorum", h("small", null, "Konsol oturumunu ve Caddy TLS'yi atlar."))) : null))),
      h("fieldset", { class: "pd-fs" }, h("legend", null, svg("key"), "Çalıştıran hesap"),
        field("Hesap", h("select", { class: "pd-inp", id: "pd-f-user", onchange: (e) => { d.user = e.target.value; redraw(); } },
          Object.entries(USERS).map(([k, v]) => h("option", { value: k, selected: d.user === k }, v))), `Şu an: ${USERS[(s.preview.config || {}).user] || "bilinmiyor"}`,
          account ? [ACCOUNT_RULE] : null)),
      h("label", { class: "pd-check" }, h("input", { type: "checkbox", id: "pd-f-start", checked: !!s.start, onchange: (e) => { s.start = e.target.checked; } }), h("span", null, "Sahiplendikten sonra başlat")),
      s.error ? h("p", { class: "err-s", role: "alert" }, s.error) : null);
    const foot = h("div", { class: "pd-foot" }, h("span", { class: "pd-muted", role: "status" }, unsupported.length ? "Desteklenmeyen seçenek varken sahiplenilmez." : missing ? "Her portun erişimini seçin." : account ? "Hesabı ya da klasörü düzeltin." : "Henüz hiçbir şey değişmedi."),
      h("div", { class: "pd-foot-btns" }, h("button", { type: "button", class: "btn btn-quiet", id: "pd-cancel", onclick: () => sheet.close() }, "Vazgeç"),
        h("button", { type: "button", class: "btn btn-primary", id: "pd-apply", "aria-disabled": blocked ? "true" : "false", onclick: () => {
          if (blocked) return;
          const seq = s.seq;
          const cfg = Object.assign({}, s.preview.config, { network: d.network, user: d.user, ports: d.ports.map((p) => ({ scope: p.scope, host_port: Number(p.host_port), container_port: Number(p.container_port), protocol: p.protocol, public_ack: p.scope === "public" && !!p.public_ack })) });
          s.sending = true; drawSheet();
          submit({ action: "adopt", name: s.name, preview_fingerprint: s.fingerprint, config: cfg, start: !!s.start, confirm: true }, s.name, {
            onDone: () => { if (mine(seq)) sheet.close(); toast(`${s.name}: ${DONE.adopt}.`); return true; },
            onFail: (o, text) => { if (!mine(seq)) return false; s.sending = false; s.error = text; drawSheet(); return true; },
          }).catch((e) => { if (!mine(seq)) { toast(`${s.name}: ${e.message}`); return; } s.sending = false; s.error = e.message; drawSheet(); });
        } }, s.sending ? "Sahipleniliyor…" : "Sahiplen")));
    return { body, foot };
  }
  function smallForm(s) {
    const d = s.draft, rows = [];
    let error = "";
    if (s.mode === "pull") {
      rows.push(field("İmaj", input("pd-f-pull", d.image, (v) => { d.image = v; }, { class: "pd-inp mono", placeholder: "docker.io/library/redis:7.4-alpine" }), "İndirme sunucuda sürer; pencereyi kapatabilirsiniz."));
      if (s.tried && !IMAGE_RE.test(d.image.trim())) error = "İmajın tam adını yazın: kayıt adresi, depo ve etiket (ör. docker.io/library/redis:7.4-alpine).";
    } else if (s.mode === "volume") {
      rows.push(field("Birim adı", input("pd-f-volume", d.name, (v) => { d.name = v; }, { class: "pd-inp mono", placeholder: "ornek-veri" })));
      if (s.tried && !RES_NAME_RE.test(d.name.trim())) error = "Birim adı küçük harf ya da rakamla başlar; küçük harf, rakam ve - _ . içerir.";
    } else {
      rows.push(field("Ağ adı", input("pd-f-netname", d.name, (v) => { d.name = v; }, { class: "pd-inp mono", placeholder: "ornek-ag" })),
        field("Alt ağ (isteğe bağlı)", input("pd-f-subnet", d.subnet, (v) => { d.subnet = v; }, { class: "pd-inp mono", placeholder: "10.89.5.0/24" }), "Boşsa Podman boş bir aralık seçer."),
        h("label", { class: "pd-check" }, h("input", { type: "checkbox", id: "pd-f-internal", checked: d.internal, onchange: (e) => { d.internal = e.target.checked; } }),
          h("span", null, "İç ağ", h("small", null, "Konteynerler birbirine ulaşır, dışarıya çıkamaz."))));
      if (s.tried && !RES_NAME_RE.test(d.name.trim())) error = "Ağ adı küçük harf ya da rakamla başlar; küçük harf, rakam ve - _ . içerir.";
      else if (s.tried && d.subnet.trim() && !CIDR_RE.test(d.subnet.trim())) error = "Alt ağı CIDR olarak yazın (ör. 10.89.5.0/24).";
    }
    const o = s.opId ? OPS.get(s.opId) : null;
    const body = h("div", { class: "pd-body" }, rows, error ? h("p", { class: "pd-ferr", role: "alert" }, error) : null,
      s.error ? h("p", { class: "err-s", role: "alert" }, s.error) : null,
      s.opId ? h("p", { class: "pd-progress", role: "status" }, h("span", { class: "spin", "aria-hidden": "true" }), h("span", null, (o && o.step) || busyText({ pull: "image-pull", volume: "volume-create", network: "network-create" }[s.mode]))) : null);
    const action = { pull: "image-pull", volume: "volume-create", network: "network-create" }[s.mode];
    const foot = h("div", { class: "pd-foot" }, h("span"), h("div", { class: "pd-foot-btns" },
      h("button", { type: "button", class: "btn btn-quiet", id: "pd-cancel", onclick: () => sheet.close() }, s.opId ? "Kapat" : "Vazgeç"),
      h("button", { type: "button", class: "btn btn-primary", id: "pd-apply", "aria-disabled": s.opId || s.sending ? "true" : "false", onclick: () => {
        if (s.opId || s.sending) return;
        s.tried = true;
        const valid = s.mode === "pull" ? IMAGE_RE.test(d.image.trim()) : RES_NAME_RE.test(d.name.trim()) && (s.mode !== "network" || !d.subnet.trim() || CIDR_RE.test(d.subnet.trim()));
        if (!valid) { drawSheet(); return; }
        const payload = s.mode === "pull" ? { action, image: d.image.trim() } : s.mode === "volume" ? { action, name: d.name.trim() } : { action, name: d.name.trim(), subnet: d.subnet.trim(), internal: !!d.internal };
        const target = (s.mode === "pull" ? "image:" : s.mode === "volume" ? "volume:" : "network:") + (payload.image || payload.name);
        const seq = s.seq;
        s.sending = true; s.error = ""; drawSheet();
        submit(payload, target, {
          onDone: () => { if (mine(seq)) sheet.close(); toast(`${payload.image || payload.name}: ${DONE[action]}.`); return true; },
          onFail: (op, text) => { if (!mine(seq)) return false; s.opId = ""; s.sending = false; s.error = text; drawSheet(); return true; },
        }).then((r) => { if (!mine(seq)) return; s.opId = r.id; s.sending = false; drawSheet(); })
          .catch((e) => { if (!mine(seq)) { toast(e.message); return; } s.sending = false; s.error = e.message; drawSheet(); });
      } }, { pull: "Çek", volume: "Oluştur", network: "Oluştur" }[s.mode])));
    return { body, foot };
  }

  /* ---------------- sayfa ---------------- */
  // Her çizim kökü yeniden kurar; odak (data-k ya da id), arama imleci ve günlük kaydırması korunur.
  function paint(focusKey) {
    const a = document.activeElement;
    const key = focusKey || (a && root.contains(a) ? (a.dataset.k ? "k:" + a.dataset.k : a.id ? "id:" + a.id : "") : "");
    const caret = a && root.contains(a) && typeof a.selectionStart === "number" && a.type === "search" ? [a.selectionStart, a.selectionEnd] : null;
    const log = root.querySelector(".pd-log"), follow = log ? log.scrollHeight - log.scrollTop - log.clientHeight < 6 : true, logTop = log ? log.scrollTop : 0;
    const bars = {};
    root.querySelectorAll(".pd-tabs").forEach((b) => { bars[b.getAttribute("aria-label")] = b.scrollLeft; });
    const kids = detailName ? detailView() : [summary(), tabsEl(), h("div", { class: "pd-stack", id: "pd-tabpanel", role: "tabpanel", "aria-labelledby": "pd-tab-" + tab },
      tab === "konteynerler" ? containersPanel() : tab === "imajlar" ? imagesPanel() : tab === "birimler" ? volumesPanel() : networksPanel())];
    root.replaceChildren(...kids.flat().filter(Boolean));
    const nl = root.querySelector(".pd-log"); if (nl) nl.scrollTop = follow ? nl.scrollHeight : logTop;
    // Dar ekranda sekme şeridi yatay kayar: konumunu koru ve seçili sekmeyi görünür tut (sayfayı kaydırmadan).
    root.querySelectorAll(".pd-tabs").forEach((b) => {
      b.scrollLeft = bars[b.getAttribute("aria-label")] || 0;
      const on = b.querySelector('[aria-selected="true"]');
      if (!on) return;
      const br = b.getBoundingClientRect(), tr = on.getBoundingClientRect();
      if (tr.left < br.left) b.scrollLeft -= br.left - tr.left + 4;
      else if (tr.right > br.right) b.scrollLeft += tr.right - br.right + 4;
    });
    if (key) {
      const sel = key.startsWith("k:") ? `[data-k="${CSS.escape(key.slice(2))}"]` : key.startsWith("id:") ? "#" + CSS.escape(key.slice(3)) : `[data-k="${CSS.escape(key)}"]`;
      const el = root.querySelector(sel);
      if (el && (focusKey || root.contains(document.activeElement) || document.activeElement === document.body)) {
        el.focus({ preventScroll: true });
        if (caret && typeof el.setSelectionRange === "function") try { el.setSelectionRange(caret[0], caret[1]); } catch (_) { /* yok */ }
      }
    }
    if (stamp) stamp(stampText());
    const nb = document.getElementById("ct-new");
    if (nb) nb.setAttribute("aria-disabled", LIST && (LIST.runtime || {}).ok ? "false" : "true");
  }
  function mount() {
    const host = document.getElementById("konteyner-page");
    if (host && root.parentNode !== host) host.replaceChildren(root);
  }
  return {
    title: (sub) => (sub ? decode(sub) || "Konteyner" : "Podman"),
    eyebrow: (sub) => (sub ? "Podman" : "Konteynerler · bu sunucu"),
    actions: (sub) => [h("span", { class: "hm", id: "ct-stamp" }, stampText()),
      h("button", { type: "button", class: "btn btn-quiet", onclick: () => refresh() }, svg("refresh"), "Yenile"),
      sub ? null : h("button", { type: "button", class: "btn btn-primary", id: "ct-new", "aria-disabled": LIST && (LIST.runtime || {}).ok ? "false" : "true",
        onclick: (e) => { if (e.currentTarget.getAttribute("aria-disabled") !== "true") openCreate(); } }, svg("plus"), "Yeni konteyner")].filter(Boolean),
    show(sub) {
      mount();
      const name = sub ? decode(sub) : "";
      if (name !== detailName) {
        detailName = name; DETAIL = null; detailError = ""; LOG = null; logError = ""; logQuery = "";
        if (!name) section = "genel"; else if (section !== "gunluk") section = "genel";
        detailSeq++; logSeq++;
      }
      paint();
      loadList();
      if (detailName) { loadDetail(); if (section === "gunluk") loadLog(); }
      if (!updLoading && (!UPD || Date.now() / 1000 - (UPD.checked_at || 0) > 3600)) loadUpdates(false);
    },
    poll() { if (active && active()) refresh(); },
    // App Store satırının adı ve simgesi modül listesinden gelir; liste ondan önce geldiyse yeniden çizilir.
    modules() { if (LIST) paint(); },
    // Sayfadan çıkınca (geri tuşu, yazılan bağlantı) açık pencere kapanır, taslak düşer; Genel bakış'ın
    // düzen taslağı gibi (DD-206). Gönderilmiş bir işlem sunucuda sürer, sonucu satırda ve bildirimde görünür.
    leave() { if (sheet.open) sheet.close(); },
    refresh,
  };
};
