/* Approved v08 interaction model, live implementation (DD-156, DD-202: no application tab;
   package pages carry their own settings). Drafts stay in memory only. No localStorage, no inline HTML. */
"use strict";
window.createSettingsPage = ({ h, svg, api, post, toast, fail, paintWeb, loadSettings, systemContent, logContent, paintLog }) => {
  let root = document.getElementById("settings-page");
  const clone = (x) => JSON.parse(JSON.stringify(x));
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  // Konteynerler artık ana menüde kendi sayfasıdır (konteynerler.js); eski sekmenin bağlantıları oraya yönlenir.
  const tabs = [["system", "Sistem"], ["fw", "Güvenlik Duvarı"], ["web", "Caddy"], ["dns", "Dnsmasq"], ["log", "Günlük"]];
  // DD-200: the VPN category is named after the installed package that declares networks.
  const vpnName = () => (live && live.firewall && live.firewall.vpn_name) || "VPN";
  const scopeName = (s) => ({ wan: "İnternet", tail: "Tailscale", wg: vpnName(), lo: "Sunucu içi" }[s] || s);
  let live = null, draft = null, tab = "system", family = 4, scope = "tail", mode = "ports", wgNetwork = "all";
  let pending = null, busy = false, poll = null, message = "", baseRevision = "";
  let domainInput = "", migration = null;
  const webDrafts = {};
  let webBusy = "";
  const dirty = () => live?.manage?.config && draft && (!same(draft.firewall, live.manage.config.firewall) || !same(draft.dns, live.manage.config.dns));
  const locked = () => busy || !!pending;
  const httpsApplying = () => pending?.phase === "applying" && (!!webBusy || pending.web || live?.manage?.https?.status === "pending");
  const btn = (text, action, primary = false, available = false) => h("button", { type: "button", class: "btn btn-sm" + (primary ? " btn-primary" : ""), disabled: !available && locked(), onclick: action }, text);
  const note = (text, warn = false) => h("p", { class: "as-note" + (warn ? " warn" : "") }, text);
  const badge = (text, good = false) => h("span", { class: "as-badge" + (good ? " good" : "") }, text);
  const card = (title, subtitle, ...body) => h("article", { class: "card as-card" }, h("div", { class: "card-head" }, h("div", null, h("h2", null, title), h("small", null, subtitle))), ...body);
  function field(label, control, hint) {
    control.setAttribute("aria-label", label);
    return h("label", { class: "as-field" }, h("span", null, label), control, hint ? h("small", null, hint) : null);
  }
  function select(items, value, change) {
    return h("select", { onchange: (e) => change(e.target.value) }, ...items.map(([v, label]) => h("option", { value: v, selected: String(v) === String(value) }, label)));
  }
  function toggle(label, value, action, id, disabled = false) {
    return h("button", { type: "button", id, class: "as-switch", role: "switch", "aria-label": label, "aria-checked": !!value,
      disabled: disabled || locked(), onclick: () => { action(!value); draw(); document.getElementById(id)?.focus(); } }, value ? "Açık" : "Kapalı");
  }
  function table(headers, rows, className = "", caption = "") {
    return h("div", { class: "as-tablewrap" + (caption ? " as-fw-scroll" : ""),
      ...(caption ? {role:"region", "aria-label":caption, tabindex:"0"} : {}) },
      h("table", { class: className }, caption ? h("caption", null, caption) : null,
        h("thead", null, h("tr", null, ...headers.map((x) => h("th", { scope: "col" }, x)))),
        h("tbody", null, ...(rows.length ? rows : [h("tr", null, h("td", {colspan:headers.length}, "Bu seçimde kayıt yok."))]))));
  }
  const td = (...kids) => h("td", null, ...kids);
  function modal(title, content, submit) {
    const dialog = h("dialog", { class: "as-dialog", "aria-labelledby": "as-dialog-title" });
    const close = () => { dialog.close(); dialog.remove(); };
    dialog.addEventListener("cancel", () => dialog.remove());
    const form = h("form", { class: "dlg", onsubmit: (e) => { e.preventDefault(); if (submit) submit(form, close); } },
      h("h3", { id: "as-dialog-title" }, title), content,
      h("div", { class: "dlg-foot" }, btn("Vazgeç", close, false, true), submit ? h("button", { type: "submit", class: "btn btn-primary" }, "Devam et") : null));
    dialog.append(form); document.body.append(dialog); dialog.showModal();
    return dialog;
  }
  function error(e) { message = e.message || String(e); fail(e); draw(); }
  function changes() {
    if (!live?.manage?.config || !draft) return [];
    const out = [], old = live.manage.config;
    for (const r of draft.firewall) {
      if (!same(r, old.firewall.find((x) => x.id === r.id))) out.push(`${r.name}: IPv${r.family} · ${scopeName(r.scope)} · ${r.proto.toUpperCase()} ${r.port} · ${r.source || "tüm kaynaklar"} → ${r.allow ? "izin ver" : "engelle"}`);
    }
    for (const r of old.firewall) if (!draft.firewall.some((x) => x.id === r.id)) out.push(`${r.name}: kullanıcı kuralı kaldırılacak; temel politika geçerli olacak.`);
    if (!same(draft.dns, old.dns)) {
      for (const n of live.manage.names) {
        if (draft.dns.disabled.includes(n.name) !== old.dns.disabled.includes(n.name)) out.push(`${n.name} → ${draft.dns.disabled.includes(n.name) ? "kapalı" : "açık"}`);
      }
      for (const r of draft.dns.records) if (!same(r, old.dns.records.find((x) => x.name === r.name))) out.push(`${r.name} → ${r.target} · ${r.enabled ? "açık" : "kapalı"}`);
      for (const r of old.dns.records) if (!draft.dns.records.some((x) => x.name === r.name)) out.push(`${r.name}: silinecek`);
      if (draft.dns.forward !== old.dns.forward || !same(draft.dns.servers, old.dns.servers)) out.push(`Üst DNS → ${draft.dns.forward ? draft.dns.servers.join(", ") : "kapalı"}`);
    }
    return out;
  }
  function reset() {
    draft = clone(live.manage.config); baseRevision = live.manage.revision; message = ""; draw();
  }
  async function submitChanges(close) {
    if (locked() || !dirty()) return;
    const payload = { revision: baseRevision };
    if (!same(draft.firewall, live.manage.config.firewall)) payload.firewall = draft.firewall;
    if (!same(draft.dns, live.manage.config.dns)) payload.dns = draft.dns;
    close(); busy = true; message = "Sunucuda doğrulanıyor ve uygulanıyor…"; draw();
    try {
      const result = await post("/api/konsol/ayarlar/uygula", payload);
      pending = result.pending;
      if (result.committed) {
        draft = null; clearTimeout(poll);
        message = "Dnsmasq ayarları uygulandı ve kaydedildi.";
        toast(message);
      } else {
        message = "Değişiklikler geçici olarak uygulandı. Bağlantınızı onaylayın.";
        startPoll();
      }
      await loadSettings(true);
    } catch (e) { error(e); startPoll(); }
    finally { busy = false; draw(); }
  }
  function review() {
    const list = changes();
    if (!list.length) return;
    let dialog;
    dialog = modal("Değişiklikleri incele", h("div", null,
      h("ul", { class: "as-changes" }, ...list.map((t) => h("li", null, t))),
      note("Uygulama sonrası 60 saniye içinde onay gerekir. Sekme/bağlantı kapanırsa sunucu eski ayarları geri yükler.", true),
      note("İnternete izin vermek servisin dinlediği adresi değiştirmez. İlk eşleşen kullanıcı kuralı geçerlidir; açık bağlantılar korunur.")),
    (_form, close) => submitChanges(close));
    dialog.querySelector('[type="submit"]').textContent = "Sunucuda uygula";
  }
  // DD-182: a rollback that failed five times waits for the operator. Discarding keeps the
  // files as they are now; re-running the installer re-applies the saved settings.
  function discard() {
    if (busy || pending?.phase !== "stuck") return;
    const word = h("input", { type: "text", autocomplete: "off", spellcheck: "false", required: true });
    modal("Takılan geri alma bırakılsın mı?", h("div", null,
      note("Sunucu önceki ayarları beş denemede geri yükleyemedi. Bırakırsanız dosyalar şu anki hâlinde kalır ve bekleyen işlem silinir; kurulum ve uygulama işlemleri yeniden açılır.", true),
      note("Kaydedilmiş (onaylanmış) ayarları yeniden uygulamak için ardından kurulumu çalıştırın."),
      field("Onaylamak için onayla yazın", word)),
    async (_form, close) => {
      if (word.value.trim().toLocaleLowerCase("tr") !== "onayla") { word.focus(); return; }
      close(); busy = true; draw();
      try {
        await post("/api/konsol/ayarlar/birak", { id: pending.id, confirm: "onayla" });
        pending = null; draft = null; message = "Takılan işlem bırakıldı; kaydedilmiş ayarlar için kurulumu yeniden çalıştırın.";
        toast(message); loadSettings(true);
      } catch (e) { error(e); }
      finally { busy = false; draw(); }
    });
  }
  function rollbackState() {
    if (pending.phase === "stuck") return [h("strong", null, `Geri alma tamamlanamadı (${pending.attempts} deneme)`),
      h("p", null, `Son hata: ${pending.error || "bilinmiyor"}. Sunucu kendiliğinden yeniden denemez; kurulum ve uygulama işlemleri beklemede.`),
      h("div", { class: "as-inline" }, h("button", { type: "button", class: "btn btn-primary", disabled: busy, onclick: () => finish("geri-al") }, "Yeniden dene"),
        h("button", { type: "button", class: "btn", disabled: busy, onclick: discard }, "Bırak…"))];
    const retry = pending.phase === "rollback" && pending.attempts
      ? `Geri alma denendi, tamamlanamadı: ${pending.error || "bilinmiyor"}. ${pending.retry_in ?? 0} sn sonra yeniden denenecek (${pending.attempts}/5).` : "";
    return [h("strong", null, pending.phase === "awaiting" ? `${pending.seconds} sn içinde bağlantıyı onaylayın` : "Sunucuda işlem sürüyor…"),
      h("p", null, retry || "Onay verilmezse önceki ayarlar sunucuda geri yüklenir. Sayfayı kapatmak bunu durdurmaz."),
      h("div", { class: "as-inline" }, h("button", { type: "button", class: "btn btn-primary", disabled: busy || pending.phase !== "awaiting" || pending.seconds <= 0 || (!!pending.domain && location.hostname !== "panel." + pending.domain.new), onclick: () => finish("onayla") }, "Bağlantı çalışıyor · onayla"),
        h("button", { type: "button", class: "btn", disabled: busy || pending.phase === "applying", onclick: () => finish("geri-al") }, "Geri al"))];
  }
  async function finish(action) {
    if (busy || !pending) return;
    busy = true; draw();
    try {
      await post("/api/konsol/ayarlar/" + action, { id: pending.id });
      pending = null; draft = null; message = action === "onayla" ? "Ayarlar kalıcı olarak kaydedildi." : "Önceki ayarlar geri yüklendi.";
      toast(message); loadSettings(true);
    } catch (e) { error(e); }
    finally { busy = false; draw(); }
  }
  function startPoll() {
    clearTimeout(poll);
    poll = setTimeout(async () => {
      try {
        const s = await api("/api/konsol/ayarlar/durum");
        const was = pending; pending = s.pending;
        if (s.https && live?.manage) live.manage.https = s.https;
        if (s.publications && live?.manage) live.manage.publications = s.publications;
        if (was && !pending) { draft = null; message = "İşlem tamamlandı; sunucudaki ayarlar yeniden okunuyor."; loadSettings(true); }
        draw();
      } catch (_e) { message = pending && !httpsApplying() ? "Sunucuya erişilemiyor. Onay verilmezse sunucu değişiklikleri geri alır." : "Sunucuya erişilemiyor. İşlemin sonucunu ayarları yenileyerek kontrol edin."; draw(); }
      if (pending) startPoll();
    }, 2000);
  }
  function ruleForm(existing = null) {
    const selectedScope = ["wan", "tail"].includes(scope) ? scope : "tail";
    const r = existing || { name: "", family, scope: selectedScope && selectedScope !== "lo" ? selectedScope : "tail", proto: "tcp", port: "", source: "", allow: true };
    const input = (name, value, attrs = {}) => h("input", { name, value, ...attrs });
    const opts = (name, choices, value) => { const s = select(choices, value, () => {}); s.name = name; return s; };
    modal(existing ? "Kuralı düzenle" : "Port kuralı ekle", h("div", { class: "as-formgrid" },
      field("Ad", input("name", r.name, { required: true, maxlength: 64 })),
      field("Kapsam", opts("scope", [["wan", "İnternet"], ["tail", "Tailscale"]], r.scope)),
      field("Adres ailesi", opts("family", [[4, "IPv4"], [6, "IPv6"]], r.family)),
      field("Protokol", opts("proto", [["tcp", "TCP"], ["udp", "UDP"]], r.proto)),
      field("Port", input("port", r.port, { type: "number", required: true, min: 1, max: 65535 })),
      field("Kaynak IP/CIDR", input("source", r.source, { placeholder: "boş = tüm kaynaklar", maxlength: 64 })),
      field("Eylem", opts("allow", [["true", "İzin ver"], ["false", "Engelle"]], String(r.allow)))), (form, close) => {
      const f = new FormData(form);
      const item = { id: existing ? existing.id : "u_" + Date.now().toString(36) + Math.random().toString(36).slice(2, 8),
        name: f.get("name").trim(), family: Number(f.get("family")), scope: f.get("scope"), proto: f.get("proto"), port: Number(f.get("port")), source: f.get("source").trim(), allow: f.get("allow") === "true" };
      const clash = draft.firewall.find((x) => x.id !== item.id && x.family === item.family && x.scope === item.scope && x.proto === item.proto && x.port === item.port && x.source === item.source);
      if (clash) { toast("Bu port/kaynak için zaten bir kural var; mevcut satırı düzenleyin."); return; }
      if (existing) draft.firewall[draft.firewall.indexOf(existing)] = item;
      else draft.firewall.push(item);
      close(); draw();
    });
  }
  const wgScopes = () => (live.firewall.networks || []).map((n) => n.iface);
  function addressNote(address) {
    const ip = address.split("%")[0].replace(/^\[|\]$/g, "");
    if (ip === "0.0.0.0") return "Tüm IPv4 arayüzlerinde dinler.";
    if (ip === "::") return "Tüm IPv6 arayüzlerinde dinler.";
    if (ip === "*") return "Tüm yerel arayüzlerde dinler.";
    if (ip.startsWith("127.") || ip === "::1") return "Yalnız sunucu içinden erişilir.";
    if (ip === live.tailscale || ip === live.tailscale6) return "Sunucunun Tailscale adresi.";
    if (ip === live.wan?.ipv4 || ip === live.wan?.ipv6) return "Sunucunun internet arayüzü.";
    return "Yalnız bu yerel IP üzerinde dinler.";
  }
  function fwRows() {
    if (scope === "wg") return []; // Fixed internet-only policy; no host overrides.
    const rows = clone(live.firewall.ports || []);
    for (const r of draft.firewall) {
      const found = rows.find((x) => x.family === r.family && x.scope === r.scope && x.proto === r.proto && x.port === r.port && !x.rule);
      if (found && !r.source) { found.rule = r; continue; }
      rows.push({ ...r, rule: r, baseline: false });
    }
    return rows.filter((r) => r.family === family && r.scope === scope);
  }
  function bindingStatus(binds, row) {
    if (live.firewall.listeners == null) return "Okunamadı";
    if (!binds.length) return "Dinleyici yok";
    if (binds.some((b) => b.scope === "any" || b.scope === row.scope))
      return row.scope === "lo" ? "Sunucu içinde dinliyor" : "Bu ağda dinliyor";
    if (binds.every((b) => b.scope === "lo")) return "Yalnız sunucu içinde";
    if (binds.some((b) => !b.scope || b.scope === "unknown")) return "Ağ eşleşmesi bilinmiyor";
    return "Başka adreste dinliyor";
  }
  function serviceNote(row) {
    const known = [
      ["SSH", "Sunucuya uzaktan terminal bağlantısı."],
      ["Tailscale PeerAPI", "Tailscale'in cihazlar arası hizmet ucu; portu otomatik izlenir."],
      ["Tailscale", "Tailscale tünelinin bağlantı trafiği."],
      ["Caddy", "Panel ve servislerin web adreslerini sunar."],
      ["dnsmasq", "Yerel alan adlarını DNS ile çözer."],
      ["Paylaşım WebDAV", "Dosyalar uygulamasındaki klasör paylaşımları."],
      ["Konsol · dosya", "Panelin dosya ve ZIP işlemleri arka ucu."],
    ];
    // DD-202: packages' ports come from their manifests; the base knows no application text.
    return known.find(([prefix]) => row.name.startsWith(prefix))?.[1]
      || (row.rule ? "Kullanıcının tanımladığı port izni." : row.module ? "Kurulu bir uygulamanın bildirdiği port." : "Servis adı eşleştirilemedi; dinlenen adresi kontrol edin.");
  }
  function ruleNote(row) {
    if (row.spec.startsWith("Politika: ")) return "Bu zincirde eşleşmeyen paketler için varsayılan karar.";
    if (row.spec === "Özel zincir") return "Başka bir kuralın yönlendirmesiyle çalıştırılan zincir.";
    // Explain only an unambiguous terminal target; keep the complete rule visible.
    const target = row.spec.match(/(?:^|\s)-j ([A-Za-z0-9_-]+)$/)?.[1];
    const notes = {ACCEPT:"Eşleşen pakete bu zincirde izin verir.", DROP:"Eşleşen paketi yanıt vermeden düşürür.",
      REJECT:"Eşleşen paketi ret yanıtıyla engeller.", RETURN:"Çağıran zincire döner; ana zincirde varsayılan karar uygulanır.",
      MASQUERADE:"Kaynak adresini çıkış arayüzünün adresine dönüştürür."};
    if (notes[target]) return notes[target];
    return "Ham kuraldaki eşleşme ve hedef seçenekleri geçerlidir.";
  }
  function firewall() {
    const groups = ["tail", "wan", ...(live.firewall.vpn_installed ? ["wg"] : []), "lo"];
    if (!groups.includes(scope)) scope = "tail";
    if (wgNetwork !== "all" && !wgScopes().includes(wgNetwork)) wgNetwork = "all";
    const chooseScope = (key) => { scope = key; mode = "ports"; draw(); document.getElementById("as-fw-tab-" + key)?.focus(); };
    const categories = h("nav", {class:"as-fw-tabs", role:"tablist", "aria-label":"Trafik kategorileri"}, ...groups.map((key) => h("button", {
      type:"button", role:"tab", id:"as-fw-tab-" + key, "aria-controls":"as-fw-content", "aria-selected":scope === key, tabindex:scope === key ? "0" : "-1",
      onclick:() => chooseScope(key), onkeydown:(e) => {
        const delta = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
        if (!delta && !["Home", "End"].includes(e.key)) return;
        e.preventDefault(); chooseScope(groups[e.key === "Home" ? 0 : e.key === "End" ? groups.length - 1 : (groups.indexOf(key) + delta + groups.length) % groups.length]);
      }
    }, scopeName(key))));
    const descriptions = {
      tail:"Tailscale ağından sunucuya gelen bağlantılar. Gerekli servisler ve tanımlı VPN portları izinlidir; diğer portlar açık bir kullanıcı kuralı olmadıkça engellenir.",
      wan:"İnternet arayüzünden gelen bağlantılar. SSH ve VPN bağlantı portları burada yer alır; listede olmayan portlar varsayılan olarak engellenir.",
      wg:`${vpnName()} cihazları yalnız internete çıkar. Sunucu servisleri, özel ağlar ve diğer cihazlar engellenir; bu politika değiştirilemez. VPN’in UDP bağlantı portu İnternet sekmesindedir. Yönlendirme ve NAT kuralları Teknik kurallar görünümündedir.`,
      lo:"Sunucunun kendi iç bağlantıları (loopback). Servislerin arka uçları burada çalışır; bu izinler korunur ve değiştirilemez."
    };
    const toolbar = h("div", { class: "as-toolbar as-fw-controls" },
      field("Adres ailesi", select([[4, "IPv4"], [6, "IPv6"]], family, (v) => { family = Number(v); draw(); })),
      mode === "ports" && scope === "wg" && wgScopes().length ? field(`${vpnName()} ağı`, select([["all", `Tüm ${vpnName()} ağları`], ...wgScopes().map((s) => {
        const net = (live.firewall.networks || []).find(n => n.iface === s);
        return [s, `${s}${net?.label ? " · " + net.label : ""}${net && !net.active ? " · durduruldu" : ""}`];
      })], wgNetwork, (v) => { wgNetwork = v; draw(); })) : null,
      mode === "ports" && ["wan", "tail"].includes(scope) ? btn("+ Port kuralı", () => ruleForm()) : null,
      btn(mode === "rules" ? "Portlara dön" : "Teknik kurallar", () => { mode = mode === "rules" ? "ports" : "rules"; draw(); }, false, true));
    let content;
    if (mode === "rules") {
      const rules = live.firewall.rules || { rows: [], errors: ["Kurallar okunamadı"] };
      const rows = rules.rows.filter(r => r.family === family);
      content = h("div", {class:"as-fw-rules"}, ...rules.errors.map((e) => note(e, true)),
        table(["Tablo / zincir", "Sıra", "Ham kural", "Kısa açıklama", "Sayaç", "Sahibi / yönetim"], rows.map((r) => h("tr", null,
          h("th", {scope:"row"}, h("strong", null, r.chain), h("small", null, `${r.table} · IPv${r.family}`)), td(r.position), td(h("code", null, r.spec)),
          td(ruleNote(r)), td(`${r.packets.toLocaleString("tr-TR")} paket`, h("small", null, `${r.bytes.toLocaleString("tr-TR")} bayt`)),
          td(r.owner, h("small", null, r.owner === "Konsol" ? "Salt okunur · izinler trafik sekmelerinde yönetilir." : "Salt okunur · bu panelden değiştirilmez.")))),
        "as-rules as-fw-table", `Canlı kurallar · IPv${family} · ${rows.length} satır`),
        note("Tüm ağlar · INPUT, FORWARD ve NAT dahil tüm tablolar. Kurallar zincir içindeki sırayla değerlendirilir; sayaçlar son okumanın değeridir. Bu görünüm salt okunurdur."));
    } else {
      const rows = fwRows();
      content = table(["Servis / açıklama", "Port / protokol", "Kaynak IP / CIDR", "Dinleme / adres", "Firewall izni", "Aç / kapa", "İşlemler"], rows.map((r, i) => {
        const rule = r.rule, allow = rule ? rule.allow : r.baseline;
        const saved = live.manage.config.firewall.find(x => rule ? x.id === rule.id
          : x.family === r.family && x.scope === r.scope && x.proto === r.proto && x.port === r.port && !x.source);
        const changed = rule ? !same(rule, saved) : !!saved;
        const sockets = live.firewall.listeners;
        const binds = (sockets || []).filter((s) => s.port === r.port && s.proto === r.proto && s.family === family);
        const iface = r.scope === "wan" ? live.wan?.iface : r.scope === "tail" ? live.ts_if : r.scope;
        return h("tr", { class: changed ? "changed" : "" },
          h("th", {scope:"row"}, h("strong", null, r.name.split(" — ")[0]), h("small", null, serviceNote(r)), h("small", null, `IPv${r.family} · ${iface || "arayüz okunamadı"}`)),
          td(h("code", null, String(r.port)), h("small", null, r.proto.toUpperCase())),
          td(h("code", null, rule?.source || "Tüm kaynaklar"), h("small", null, rule?.source ? "Yalnız bu IP / ağ eşleşir." : "Seçilen gelen ağdaki tüm kaynaklar.")),
          td(h("strong", {class:"as-binding"}, bindingStatus(binds, r)), ...[...new Set(binds.map(b => b.address))].map((address) =>
            h("div", { class: "as-address" }, h("code", null, address), h("small", null, addressNote(address)))),
            sockets == null ? h("small", null, "Dinleyici durumu bilinmiyor.") : !binds.length ? h("small", null, "Bu adres ailesi ve protokolde servis görülmedi.") : null),
          td(badge(allow ? "İzinli" : "Engelli", allow), h("small", null, changed ? "Taslak · henüz uygulanmadı" : rule ? "Kullanıcı kuralı" : "Temel politika"),
            changed ? h("small", null, saved ? `Kayıtlı: ${saved.allow ? "izinli" : "engelli"}` : "Yeni kullanıcı kuralı") : null),
          td(toggle(`${r.name} ${scopeName(r.scope)} ${r.proto} ${r.port}`, allow, (on) => {
            if (rule) rule.allow = on;
            else draft.firewall.push({ id: `p_${r.family}_${r.scope}_${r.proto}_${r.port}`, name: r.name.slice(0, 64), family: r.family, scope: r.scope, proto: r.proto, port: r.port, source: "", allow: on });
          }, "as-port-" + i, r.scope === "lo" || r.fixed), r.scope === "lo" ? h("small", null, "Sunucu içi · korunur")
            : r.fixed ? h("small", null, "Konteyner yayını · uygulamayla açılır, kapanır") : null),
          td(rule ? h("div", { class:"as-fw-actions" }, btn("Düzenle", () => ruleForm(rule)), btn("Kuralı kaldır", () => {
            draft.firewall = draft.firewall.filter(x => x.id !== rule.id); draw();
          })) : h("small", null, r.scope === "lo" || r.fixed ? "Değiştirilemez" : "Anahtarla kullanıcı kuralı eklenir.")));
      }), "as-ports as-fw-table", `${scopeName(scope)}${scope === "wg" && wgNetwork !== "all" ? " · " + wgNetwork : ""} · IPv${family} · ${rows.length} satır`);
    }
    return card("Güvenlik Duvarı", "Gelen ağa göre port izinleri · IPv4 / IPv6", mode === "ports" ? categories : null, toolbar,
      !live.firewall.ok ? note(live.firewall.check || "Güvenlik duvarı denetimi uyardı.", true) : null,
      h("div", {id:"as-fw-content", ...(mode === "ports" ? {role:"tabpanel", "aria-labelledby":"as-fw-tab-" + scope} : {})},
        mode === "ports" ? note(descriptions[scope]) : null,
        mode === "ports" && scope === "wg" && !wgScopes().length ? note(`Henüz yönetilebilir bir ${vpnName()} ağı yok. ${vpnName()} uygulamasından ağ oluşturun veya durdurulmuş modülü başlatın.`) : content),
      scope !== "wg" || mode !== "ports" ? note("Dinleme ve izin ayrıdır; bu ağda dinlemesi erişim garantisi değildir. Tailscale ACL, kaynak kısıtları ve diğer kurallar da etkilidir. Yenile, güncel durumu yeniden okur.") : null,
      ["wan", "tail"].includes(scope) && mode === "ports" ? note("Aç/kapa yalnız yeni bağlantıların iznini değiştirir; servisi başlatmaz. Mevcut bağlantılar korunur. Dar ekranda tabloyu yatay kaydırabilirsiniz.") : null);
  }
  const domainUrl = (domain) => `http://panel.${domain}/#/ayarlar`;
  function domainLinks(change) {
    return h("div", { class: "as-domain-links" },
      h("a", { href: domainUrl(change.new), target: "_blank", rel: "noopener" }, `Yeni Konsol'u aç: panel.${change.new}`),
      h("small", null, "Yeni sayfada bağlantıyı onaylayın. Açılmazsa 5 dakika içinde eski ayarlar geri gelir."),
      h("a", { href: domainUrl(change.old), target: "_blank", rel: "noopener" }, `Geri dönüş adresi: panel.${change.old}`));
  }
  async function submitDomain(domain, close) {
    const change = { old: live.domain, new: domain };
    close(); migration = change; busy = true; message = "Alan adı güncelleniyor; yeni adres bağlantısını aşağıda bulabilirsiniz."; draw();
    try {
      const result = await post("/api/konsol/ayarlar/uygula", { revision: baseRevision, domain });
      pending = result.pending; domainInput = "";
      message = "Yeni Konsol adresini açıp 5 dakika içinde onaylayın. Bu sayfanın eski adresi artık yanıt vermeyebilir.";
      startPoll();
    } catch (e) { message = `${e.message} Yeni adresi kontrol edin; onaylanmayan işlem otomatik geri alınır.`; }
    finally { busy = false; draw(); }
  }
  function caddy() {
    const input = h("input", { name: "domain", value: domainInput || live.domain, required: true, maxlength: 63,
      pattern: "[a-z0-9]([a-z0-9\\-]{0,61}[a-z0-9])?", disabled: locked(), autocapitalize: "none", spellcheck: false,
      oninput: (e) => { domainInput = e.target.value; } });
    const form = h("form", { class: "as-body", onsubmit: (e) => {
      e.preventDefault();
      if (locked()) return;
      if (dirty()) { toast("Önce diğer sekmelerdeki taslakları uygulayın veya vazgeçin."); return; }
      const domain = input.value;
      if (domain === live.domain) { toast("Alan adı zaten bu değerde."); return; }
      const dialog = modal("Yerel alan adını değiştir", h("div", { class: "as-stack" },
        note(`${live.domain} → ${domain}. Panel, paylaşım, uygulama ve özel DNS adlarının son eki birlikte değişir.`),
        note(`Önce Tailscale Admin → DNS'te ${live.tailscale} sunucusuna, “Restrict to domain” ile ${domain} alanını ekleyin. Onay bitene kadar eski ${live.domain} eşleştirmesini de koruyun.`, true),
        note("Uygulamadan sonra aşağıdaki yeni adresi açıp 5 dakika içinde onaylayın. Aksi halde sunucu eski ada döner. Dosya yöneticisi açıksa kısa süre yeniden başlar; devam eden dosya aktarımlarını önce bitirin."),
        h("code", null, domainUrl(domain))), (_form, close) => submitDomain(domain, close));
      dialog.querySelector('[type="submit"]').textContent = "Alan adını güncelle";
    } }, h("div", { class: "as-domain-row" }, field("Yerel alan adı", input),
      h("button", { type: "submit", class: "btn btn-primary", disabled: locked() || !!dirty() }, "Güncelle")),
    h("small", null, "Örn. ayc veya ev · küçük harf, rakam ve tire. HTTPS alan adları değişmez."));
    const local = card("Yerel alan adı", `Geçerli adres: panel.${live.domain}`, form,
      h("section", { class: "as-tailnet-guide", "aria-labelledby": "as-tailnet-guide-title" },
        h("h3", { id: "as-tailnet-guide-title" }, "Tailscale Admin · DNS tanımı"),
        h("ol", null,
          h("li", null, h("a", { href: "https://login.tailscale.com/admin/dns", target: "_blank", rel: "noopener noreferrer" }, "Tailscale Admin → DNS"),
            " sayfasında Nameservers → Add nameserver → Custom seçin."),
          h("li", null, "Nameserver IP: ", h("code", null, live.tailscale || "Tailscale IP okunamadı")),
          h("li", null, "Restrict to search domain (Split DNS) seçeneğini açın. Alan adı: ", h("code", null, live.domain)),
          h("li", null, "Save ile kaydedin. Bağlanan cihazda Tailscale ve Tailscale DNS ayarlarını kullanma seçeneği açık olsun.")),
        h("small", null, "Bu adımlar Admin panelinde elle yapılır; yalnız kayıtlı yerel alan içindir.")),
      dirty() ? note("Alan adını değiştirmeden önce diğer ayar taslaklarını tamamlayın.", true) : null);
    local.classList.add("as-local-domain");
    return h("div", { class: "as-stack" }, local,
      live.manage.publications ? publications() : note("Caddy yayın tablosu okunamadı; sayfayı yenileyin.", true),
      h("details", { class: "as-web-details" }, h("summary", null, "Etkin Caddy yapılandırması"), h("article", { class: "card", id: "cfg-web" })));
  }
  async function savePublication(row, item) {
    if (locked() || dirty()) return;
    busy = true; webBusy = row.service; message = "Yayın ve sertifika doğrulanıyor…"; draw();
    try {
      const result = await post("/api/konsol/ayarlar/uygula", { revision: baseRevision, web: { service: row.service, ...item } });
      if (!result.committed || result.pending) throw new Error("Sunucu kalıcı kaydı doğrulamadı.");
      delete webDrafts[row.service];
      message = `${row.name} erişim ayarları kaydedildi.`; toast(message);
    } catch (e) { error(new Error(`${e.message} Sonucu Yenile ile kontrol edin.`)); }
    finally { await loadSettings(true); webBusy = ""; busy = false; draw(); }
  }
  // DD-195: publishing Konsol itself needs an explicit, typed decision.
  function confirmPanel(row, item) {
    const word = h("input", { type: "text", autocomplete: "off", spellcheck: "false", required: true });
    modal("Panel internete açılsın mı?", h("div", null,
      note(`https://${item.domain} adresinde Konsol giriş sayfası internete açılır. Konsol hesabıyla giren herkes sunucuyu yönetebilir: güvenlik duvarı, dosyalar, paylaşımlar ve uygulamalar.`, true),
      row.enabled && location.protocol === "https:" ? note("Bu sayfayı eski internet adresinden açtınız; kaydettiğinizde bu bağlantı kesilir. Konsol Tailscale adresinden ve yeni addan açık kalır.", true) : null,
      h("ul", { class: "as-changes" },
        h("li", null, "Uzun ve başka yerde kullanmadığınız bir Konsol parolası kullanın; gerekirse önce Sistem → Konsol hesabı bölümünden değiştirin."),
        h("li", null, "İnternetten çok sayıda hatalı giriş olursa internet girişi 15 dakika kapanır; Tailscale girişi etkilenmez."),
        h("li", null, "Hesap yalnız Tailscale adresinden oluşturulur; parolası orada mevcut parola sorulmadan değiştirilir. Güvenlik duvarı ve alan adı değişiklikleri de yalnız Tailscale’den onaylanır."),
        h("li", null, `DNS: ${item.domain} → ${live.wan?.ipv4 || "WAN IPv4"} · A kaydı, proxy kapalı (DNS only), AAAA kaydı yok.`)),
      field("Onaylamak için onayla yazın", word)),
    (_form, close) => {
      if (word.value.trim().toLocaleLowerCase("tr") !== "onayla") { word.focus(); return; }
      close(); savePublication(row, { ...item, confirm: "onayla" });
    });
  }
  function publications() {
    const rows = live.manage.publications;
    const labels = { ready: "Sertifika hazır", pending: "Sertifika hazırlanıyor…", error: "Yayın doğrulanamadı", disabled: "İnternet kapalı", http: "Eski HTTP erişimi" };
    const cell = (name, ...children) => h("td", { "data-label": name }, ...children);
    const content = table(["Uygulama", "Tailscale", "İnternet", "HTTPS alan adı", "Durum / işlem"], rows.map(row => {
      const saved = { tail: row.tail, enabled: row.enabled, domain: row.domain };
      const current = webDrafts[row.service] || saved;
      const changed = !same(current, saved), panel = row.service === "panel";
      const disabled = !row.installed || locked() || !!dirty();
      let saveButton, discardButton, draftNote;
      const edit = (key, value) => {
        const next = { ...(webDrafts[row.service] || current), [key]: value };
        if (same(next, saved)) delete webDrafts[row.service]; else webDrafts[row.service] = next;
      };
      const name = row.name;
      const domain = h("input", { type:"text", value:current.domain, maxlength:253, disabled,
        placeholder: row.service === "paylasim" ? "dav.example.com" : panel ? "panel.example.com" : `${row.local.split(".")[0]}.example.com`,
        "aria-label":name + " HTTPS alan adı", autocapitalize:"none", autocomplete:"off", spellcheck:false,
        oninput:e => {
          edit("domain", e.target.value); e.target.setCustomValidity("");
          const changed = !same(webDrafts[row.service] || saved, saved);
          if (saveButton) saveButton.disabled = disabled || (!changed && row.status !== "error");
          if (discardButton) discardButton.hidden = !changed;
          if (draftNote) draftNote.textContent = changed ? "Taslak · henüz uygulanmadı" : "";
        } });
      const save = () => {
        if (disabled) return;
        const item = { ...(webDrafts[row.service] || current), domain: domain.value.trim().toLowerCase().replace(/\.$/, "") };
        const valid = (!item.domain && !item.enabled) || /^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:[a-z]{2,63}|xn--[a-z0-9-]+)$/.test(item.domain);
        domain.setCustomValidity(valid ? "" : "Tam alan adını girin; URL, IP, port veya yol eklemeyin.");
        if (!domain.reportValidity()) return;
        if (item.enabled && rows.some(other => other.service !== row.service && other.enabled && other.domain === item.domain)) {
          domain.setCustomValidity("Bu HTTPS alan adı başka bir uygulamada kullanılıyor."); domain.reportValidity(); return;
        }
        if (item.enabled && row.service !== "paylasim" && rows.some(other => other.mode === "http" && other.wan_active)) {
          // One WAN port (v2-169): folders shared over plaintext HTTP right now block HTTPS publications; WebDAV's mode alone does not.
          domain.setCustomValidity("WebDAV internet paylaşımı şu an eski HTTP ile açık. Önce WebDAV için HTTPS alan adı kaydedin ya da o klasörlerin internet bağlantısını kapatın."); domain.reportValidity(); return;
        }
        if (panel && item.enabled && (!row.enabled || item.domain !== row.domain)) { confirmPanel(row, item); return; }
        if (panel && row.enabled && location.protocol === "https:" && (!item.enabled || item.domain !== row.domain)) {
          // This page itself came through the public address; it closes with the save.
          modal("İnternet adresi kapansın mı?", note("Bu sayfayı internet adresinden açtınız. Kaydettiğinizde bu bağlantı kesilir; Konsol Tailscale adresinden açık kalır.", true),
            (_form, close) => { close(); savePublication(row, item); });
          return;
        }
        savePublication(row, item);
      };
      // Every public name listens on SHARE_HTTPS_PORT (manage.https.https_port); manage.https.port is
      // WebDAV's own WAN port, which is SHARE_PORT while WebDAV still uses legacy HTTP (v2-180 fix).
      const address = row.enabled && row.domain && row.status === "ready" ? "https://" + row.domain
        + (live.manage.https?.https_port && live.manage.https.https_port !== 443 ? ":" + live.manage.https.https_port : "") : "";
      draftNote = h("small", null, changed ? "Taslak · henüz uygulanmadı" : "");
      saveButton = row.installed ? h("button", {type:"button", class:"btn btn-sm", disabled:disabled || (!changed && row.status !== "error"), onclick:save}, "Kaydet") : null;
      discardButton = row.installed ? h("button", {type:"button", class:"btn btn-sm btn-quiet", hidden:!changed, disabled:locked(), onclick:() => { delete webDrafts[row.service]; draw(); }}, "Vazgeç") : null;
      return h("tr", { class:changed ? "changed" : "", "data-publication":row.service },
        cell("Uygulama", h("strong", null, name), h("code", null, row.local), h("small", null,
          panel ? "Konsol hesabı · Tailscale her zaman açık" : !row.installed ? "Kurulu değil" : row.service === "paylasim" ? "Klasör hesabı + ağ izni" : "Uygulamanın kendi girişi")),
        cell("Tailscale", toggle(name + " Tailscale erişimi", current.tail, on => edit("tail", on), "as-web-tail-" + row.service, disabled || panel)),
        cell("İnternet", toggle(name + " internet erişimi", current.enabled, on => edit("enabled", on), "as-web-wan-" + row.service, disabled)),
        cell("HTTPS alan adı", domain, address ? (row.service === "paylasim" ? h("small", null, address + "/s/…/ · tam adres Paylaşımlar’da")
          : h("a", { href:address, target:"_blank", rel:"noopener" }, address)) : h("small", null, "Doğrudan HTTPS · DNS only")),
        cell("Durum / işlem", badge(webBusy === row.service ? "Uygulanıyor…" : labels[row.status] || "Durum bilinmiyor", !webBusy && row.status === "ready"),
          draftNote, saveButton, discardButton,
          row.expires ? h("small", null, "Sertifika: ", h("time", {datetime:new Date(row.expires * 1000).toISOString()}, new Date(row.expires * 1000).toLocaleDateString("tr-TR"))) : null,
          row.message ? h("small", null, row.message) : null));
    }), "as-publications");
    const box = card("Adresler ve erişim", "Tailscale ve internet yayını birbirinden bağımsızdır", content,
      note(`DNS A kaydı: ${live.wan?.ipv4 || "WAN IPv4 okunamadı"} · proxy kapalı (DNS only) · HTTPS TCP ${live.manage.https?.https_port || 443}.`),
      note("WebDAV’ın ana ağ seçimi klasör izinlerini genişletmez. Kapalı ağdaki yeni istekler reddedilir; devam eden aktarımlar tamamlanabilir. Sertifika hazır olması internetten erişimin test edildiği anlamına gelmez."),
      rows.some(row => row.mode === "http" && row.wan_active) ? note("Eski WebDAV WAN erişimi HTTP kullanıyor. HTTPS alan adı kaydedin; kapatınca HTTP’ye otomatik dönülmez.", true)
        : rows.some(row => row.mode === "http") ? note("WebDAV için HTTPS alan adı kaydedilmedi; internet paylaşımı açılırsa eski HTTP kullanılır. Panelin veya bir uygulamanın internet yayını açıkken WebDAV internet erişimi HTTPS alan adı ister.") : null);
    box.id = "as-publications"; box.setAttribute("aria-busy", !!webBusy || !!pending?.web);
    return box;
  }
  function addDns() {
    let targetType = "tailscale";
    const name = h("input", { name: "name", required: true, maxlength: 253, placeholder: "yeni." + live.domain });
    const ip = h("input", { name: "ip", placeholder: "IPv4 veya IPv6", disabled: true });
    modal("Yerel alan adı ekle", h("div", { class: "as-formgrid" }, field("Tam alan adı", name, `Yalnız .${live.domain} alanı`),
      field("Hedef", select([["tailscale", "Dinamik Tailscale adresi"], ["fixed", "Sabit IP"]], targetType, (v) => { targetType = v; ip.disabled = v === "tailscale"; ip.required = v !== "tailscale"; })), field("Sabit IP", ip)), (form, close) => {
      const value = form.elements.name.value.trim().toLowerCase();
      if ([...live.manage.names, ...draft.dns.records].some((x) => x.name === value)) { toast("Bu ad zaten var."); return; }
      if (!value.endsWith("." + live.domain)) { toast(`Ad .${live.domain} ile bitmeli.`); return; }
      draft.dns.records.push({ name: value, target: targetType === "tailscale" ? "tailscale" : ip.value.trim(), enabled: true }); close(); draw();
    });
  }
  function dns() {
    const d = draft.dns;
    const names = [...live.manage.names.map((r) => ({ ...r, enabled: !d.disabled.includes(r.name) })), ...d.records.map((r) => ({ ...r, source: "Özel" }))];
    const rows = names.map((r, i) => h("tr", null, td(h("strong", null, r.name)), td(r.target === "tailscale" ? live.tailscale : r.target), td(r.source === "base" ? "Temel" : r.source),
      td(toggle(r.name, r.enabled, (on) => {
        if (r.source === "Özel") d.records.find((x) => x.name === r.name).enabled = on;
        else d.disabled = on ? d.disabled.filter((n) => n !== r.name) : [...d.disabled, r.name];
      }, "as-dns-" + i, r.name === "panel." + live.domain)), td(r.source === "Özel" ? btn("Sil", () => { d.records = d.records.filter((x) => x.name !== r.name); draw(); }) : null)));
    const providers = [["cloudflare", "Cloudflare", ["1.1.1.1", "1.0.0.1"]], ["google", "Google", ["8.8.8.8", "8.8.4.4"]], ["quad9", "Quad9", ["9.9.9.9", "149.112.112.112"]]];
    const provider = providers.find((x) => same(x[2], d.servers))?.[0] || "custom";
    const providerSelect = select([...providers.map((x) => [x[0], x[1]]), ["custom", "Özel IP adresleri"]], provider, (v) => { if (v !== "custom") d.servers = providers.find((x) => x[0] === v)[2].slice(); else d.servers = []; draw(); });
    providerSelect.disabled = !d.forward || locked();
    const upstream = h("input", { value: d.servers.join(", "), disabled: !d.forward || locked(), placeholder: "1.1.1.1, 1.0.0.1", "aria-label": "Üst DNS adresleri",
      onchange: (e) => { d.servers = e.target.value.split(",").map((x) => x.trim()).filter(Boolean); draw(); } });
    return h("div", { class: "as-stack" }, card("Yerel adlar", `${live.domain} · adları kapatmak servisleri durdurmaz`, h("div", { class: "as-toolbar" }, note(`Dinleme: ${live.dns.listen.join(", ")}`), btn("+ Alan adı", addDns)),
      table(["Ad", "Yanıt", "Sahibi", "Durum", ""], rows, "as-dns"), note("DNS önbellekleri hemen silinmez. Yeni ad eklemek Caddy sitesi oluşturmaz. Panel erişimi için Konsol'un kendi DNS adı korunur.")),
    card("Üst DNS'e yönlendirme", "Yerel alan dışındaki sorgular için", h("div", { class: "as-body" },
      h("div", { class: "as-inline" }, toggle("Üst DNS'e yönlendirme", d.forward, (on) => { d.forward = on; if (on && !d.servers.length) d.servers = providers[0][2].slice(); }, "as-forward"), h("span", null, "Genel adları çöz")),
      field("Sağlayıcı", providerSelect),
      field("DNS IP adresleri", upstream, "En çok dört genel DNS adresi; virgülle ayırın. Sunucuların hangi sırada kullanılacağı garanti edilmez.")),
    note(`.${live.domain} içindeki adlar, kapalı veya bulunamayanlar dahil, dış DNS'e gönderilmez. İnternete DNS erişimi açılmaz. Üst DNS bağlantısı DoH/DoT ile şifrelenmez; Tailscale Admin DNS ayarları değişmez.`)));
  }
  function draw() {
    const previousTable = root.querySelector(".as-fw-scroll");
    const tableScroll = previousTable ? {name:previousTable.getAttribute("aria-label"), top:previousTable.scrollTop, left:previousTable.scrollLeft} : null;
    const choose = (key) => { location.hash = "#/ayarlar/" + key; };
    const nav = h("nav", { class: "as-tabs", role: "tablist", "aria-label": "Ayar sekmeleri" }, ...tabs.map(([key, name]) => h("button", {
      type: "button", role: "tab", id: "as-tab-" + key, "aria-selected": key === tab, "aria-controls": "as-view", tabindex: key === tab ? "0" : "-1", onclick: () => choose(key),
      onkeydown: (e) => { const delta = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0; if (!delta && !["Home", "End"].includes(e.key)) return; e.preventDefault(); choose(tabs[e.key === "Home" ? 0 : e.key === "End" ? tabs.length - 1 : (tabs.findIndex(([k]) => k === key) + delta + tabs.length) % tabs.length][0]); }
    }, name)));
    const ready = !!(live?.manage && !live.manage.error && draft);
    const content = tab === "system" ? systemContent() : tab === "log" ? logContent() : !ready
      ? note(live?.manage?.error || "Ayarlar okunuyor…", !!live?.manage?.error)
      : tab === "fw" ? firewall() : tab === "dns" ? dns() : caddy();
    const view = h("div", { id: "as-view", role: "tabpanel", "aria-labelledby": "as-tab-" + tab }, content);
    const list = changes();
    const directDns = ready && (tab === "dns" || !same(draft.dns, live.manage.config.dns))
      && same(draft.firewall, live.manage.config.firewall);
    const restoreFocus = document.activeElement?.getAttribute("role") === "tab" ? document.activeElement.id : "";
    root.replaceChildren(...[nav,
      pending && !httpsApplying() ? h("div", { class: "as-rollback" + (pending.phase === "stuck" ? " stuck" : ""), role: "status" }, ...rollbackState()) : null,
      pending?.domain || migration ? domainLinks(pending?.domain || migration) : null,
      message ? h("p", { class: "as-message", role: "status" }, message) : null, view,
      ready && (list.length || !["system", "log", "web"].includes(tab)) ? h("footer", { class: "as-footer" }, h("div", null, h("strong", null, list.length ? `${list.length} değişiklik taslakta` : "Kaydedilmemiş değişiklik yok"),
        h("small", null, directDns ? "Uygula ile DNS ayarları doğrudan kaydedilir; süreli onay gerekmez." : "İnceleyip uygulayana kadar sunucu değişmez.")), h("div", { class: "as-inline" },
        h("button", { type: "button", class: "btn btn-quiet", disabled: locked() || !list.length, onclick: reset }, "Vazgeç"),
        h("button", { type: "button", class: "btn btn-primary", disabled: locked() || !list.length, onclick: directDns ? () => submitChanges(() => {}) : review }, directDns ? "Uygula" : "İncele ve uygula"))) : null].filter(Boolean));
    if (tab === "web" && ready) paintWeb();
    if (tab === "log") paintLog();
    const nextTable = root.querySelector(".as-fw-scroll");
    if (tableScroll && nextTable?.getAttribute("aria-label") === tableScroll.name) {
      nextTable.scrollTop = tableScroll.top; nextTable.scrollLeft = tableScroll.left;
    }
    if (restoreFocus) document.getElementById(restoreFocus.startsWith("as-fw-tab-") ? "as-fw-tab-" + scope : "as-tab-" + tab)?.focus();
  }
  window.addEventListener("beforeunload", (e) => { if ((dirty() || (domainInput && domainInput !== live?.domain)
    || webBusy || Object.keys(webDrafts).length) && !pending && !migration) { e.preventDefault(); e.returnValue = ""; } });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      root.querySelectorAll('input[type="password"]').forEach((x) => { x.value = ""; });
    }
  });
  return { render(data, section = "system") {
    tab = section;
    if (!root) root = document.getElementById("settings-page");
    if (!data) { draw(); return; }
    const keepDraft = dirty();
    live = data;
    if (live.manage && !live.manage.error) {
      pending = live.manage.pending;
      if (!draft || !keepDraft || pending) { draft = clone(live.manage.config); baseRevision = live.manage.revision; }
      if (pending) startPoll();
    }
    draw();
  } };
};
