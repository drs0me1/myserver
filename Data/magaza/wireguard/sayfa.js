/* WireGuard paketinin Konsol sayfası (DD-200). Konsol bu dosyayı paket kuruluyken
   /uygulama/wireguard/ altından yükler; sayfa window.Konsol.sayfa ile kaydolur ve yalnız
   /api/uygulama/wireguard/* yollarını çağırır. Bütün değişiklikleri sunucuda paketin aracı
   master-wg yapar. Sayfa CSP altında çalışır: satır içi biçem ve betik yok. */
(() => {
  "use strict";
  window.Konsol.sayfa("wireguard", (k) => {
  const { h, svg, $, api, post, enc, toast, fail, ask, bytes, since } = k;
  const shClose = k.dialog.close;
  const ROUTE = "wireguard";
  const BASE = "/api/uygulama/wireguard";
  const netPath = (iface, tail) => `${BASE}/nets/${enc(iface)}${tail || ""}`;
  const peerPath = (iface, name, tail) => `${netPath(iface)}/peers/${enc(name)}${tail || ""}`;

  /* ---------- biçimleme ---------- */
  function normDns(v) {
    const parts = v.split(",").map((t) => t.replace(/\s+/g, "")).filter(Boolean);
    if (!parts.length) return null;
    for (const t of parts) {
      if (!/^\d{1,3}(\.\d{1,3}){3}$/.test(t) && !/^[0-9a-f]*:[0-9a-f:]*$/i.test(t)) return null;
    }
    return parts.join(", ");
  }
  const NAME_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$/;
  const kaText = (ka) => (ka ? `${ka} sn` : "kapalı");
  const dative = (name) => name + ({ 0: "'a", 1: "'e", 2: "'ye", 3: "'e", 4: "'e", 5: "'e", 6: "'ya", 7: "'ye", 8: "'e", 9: "'a" }[name.slice(-1)] || "'e");

  /* ---------- durum ---------- */
  let WG = null;
  const RATES = new Map();
  const nets = () => (WG ? WG.networks : []);
  const netOf = (iface) => nets().find((n) => n.iface === iface);
  const DNS_PRESETS = [
    { name: "Cloudflare", tag: "Hızlı; kurulumun varsayılanı", ips: "1.1.1.1, 1.0.0.1, 2606:4700:4700::1001" },
    { name: "Cloudflare Aile", tag: "Zararlı ve yetişkin içerik engelli", ips: "1.1.1.3, 1.0.0.3, 2606:4700:4700::1113" },
    { name: "Quad9", tag: "Zararlı site engelli", ips: "9.9.9.9, 149.112.112.112, 2620:fe::fe" },
    { name: "AdGuard", tag: "Reklam ve izleyici engelli", ips: "94.140.14.14, 94.140.15.15, 2a10:50c0::ad1:ff" },
    { name: "Google", tag: "", ips: "8.8.8.8, 8.8.4.4, 2001:4860:4860::8888" },
  ];
  const providerOf = (ips, fallback) => (DNS_PRESETS.find((d) => d.ips === ips) || { name: fallback || "Özel" }).name;
  const STLABEL = { ok: "Bağlı", idle: "Boşta", never: "Görülmedi", off: "Kapalı", netoff: "Ağ kapalı" };
  function effState(p) {
    if (!p.net.active) return "netoff";
    if (!p.enabled) return "off";
    if (p.online) return "ok";
    if (p.handshake && k.clock.now() - p.handshake < 86400) return "idle";
    return "never";
  }
  const stClass = (st) => (st === "off" || st === "netoff" ? "off" : st);
  const labelOf = (n) => n.label || (n.iface === "wg0" ? "Ana ağ" : "Etiketsiz");

  /* aktarım hızı: iki örnek arasındaki fark */
  function trackRates(state) {
    const at = state.now;
    state.networks.forEach((n) => n.peers.forEach((p) => {
      const key = `${n.iface}/${p.name}`, prev = RATES.get(key);
      let down = 0, up = 0;
      if (prev && at > prev.at && p.rx >= prev.rx) {
        down = (p.rx - prev.rx) / (at - prev.at);
        up = (p.tx - prev.tx) / (at - prev.at);
      }
      RATES.set(key, { at, rx: p.rx, tx: p.tx, down, up });
      p.down = down;
      p.up = up;
    }));
  }

  /* ---------- yükleme ---------- */
  function loadWg() {
    return api(`${BASE}/state`).then((s) => {
      k.clock.sync(s.now);
      trackRates(s);
      WG = s;
      paintWg();
    }).catch(fail);
  }
  const paintWg = () => {
    if (k.route() !== ROUTE) return;
    k.header();
    if (!$("wg-ekle").hidden) {
      if (NA.i === null) renderAddNet();
    } else renderWg();
  };

  /* ---------- ağlar ve cihazlar ---------- */
  let wgNet = "wg0";
  try { wgNet = localStorage.getItem("konsol-net") || "wg0"; } catch (e) { /* özel pencere */ }
  function selectNet(iface) {
    wgNet = iface;
    try { localStorage.setItem("konsol-net", iface); } catch (e) { /* özel pencere */ }
    renderWg();
  }
  function renderWg() {
    if (!WG) return;
    if (!nets().length) { renderWgEmpty(); return; }
    $("wg-wrap").hidden = false;
    $("wg-empty").hidden = true;
    if (!netOf(wgNet)) wgNet = nets()[0].iface;
    const tabs = $("wg-tabs");
    tabs.textContent = "";
    nets().forEach((n) => {
      const online = n.peers.filter((p) => effState(Object.assign({ net: n }, p)) === "ok").length;
      const sel = wgNet === n.iface;
      tabs.append(h("div", { class: "nettab" + (sel ? " sel" : "") + (n.active ? "" : " off") },
        h("button", { type: "button", class: "nt-main", role: "tab", "aria-selected": sel, onclick: () => selectNet(n.iface) },
          h("span", { class: "nt-top" }, h("span", { class: "nt-if" }, n.iface), h("span", { class: "nt-lab" }, labelOf(n))),
          h("small", null, "UDP ", h("span", { class: "mono" }, n.port), ` · ${n.subnet4} · Yalnız internet`),
          h("span", { class: "nt-cnt" + (n.active && online ? " on" : "") }, h("span", { class: "dotmark" }),
            n.active ? `${online}/${n.peers.length} bağlı` : "Kapalı")),
        h("span", { class: "nt-actions" },
          h("button", { type: "button", class: "nt-act", title: `${n.iface} ayarları: DNS ve yeniden üret`, "aria-label": `${n.iface} arayüz ayarları`, onclick: () => openNetSettings(n) }, svg("sliders")),
          // DD-143: her ağ eşittir; wg0 da kaldırılabilir (son ağ kalkınca sayfa Yapılandır'a döner).
          h("button", { type: "button", class: "nt-act del", title: `${n.iface} arayüzünü kaldır`, "aria-label": `${n.iface} arayüzünü kaldır`, onclick: () => askDeleteNet(n) }, svg("trash")),
          h("button", { type: "button", class: "vsw", role: "switch", "aria-checked": n.active, title: n.active ? "Arayüzü kapat" : "Arayüzü aç",
            "aria-label": `${n.iface} arayüzü`, onclick: () => toggleNet(n) }))));
    });
    const next = nextNetId();
    tabs.append(h("button", { type: "button", class: "nettab add", "data-go": next ? "#/wireguard/ekle" : null, disabled: !next },
      h("span", { class: "nt-top" }, svg("plus"), h("span", { class: "nt-lab" }, "Arayüz ekle")),
      h("small", null, next ? `wg${next} · ayrı anahtar, port ve alt ağ` : "En çok 9 ek ağ oluşturulabilir")));

    const n = netOf(wgNet);
    if (!n) return;
    const list = n.peers.map((p) => Object.assign({ net: n }, p));
    const online = list.filter((p) => effState(p) === "ok").length, offCount = list.filter((p) => !p.enabled).length;
    const panel = $("wg-panel");
    panel.classList.toggle("first", nets().length > 0 && wgNet === nets()[0].iface);
    panel.classList.toggle("off", !n.active);
    const bar = $("wg-offbar");
    bar.hidden = n.active;
    bar.replaceChildren(h("div", null, h("strong", null, `${n.iface} kapalı. `),
      h("span", null, `Cihazlar bağlanamaz. Anahtarlar, cihazlar ve profiller duruyor; açınca kendiliğinden bağlanırlar.`)),
      h("button", { type: "button", class: "btn btn-primary btn-sm", onclick: () => toggleNet(n) }, "Arayüzü aç"));
    $("wg-summary").replaceChildren(
      h("div", null, h("dt", null, "Bağlı"), h("dd", null, n.active ? `${online} ` : "Kapalı ",
        h("small", null, n.active ? `/ ${list.length} cihaz${offCount ? ` · ${offCount} kapalı` : ""}` : `${list.length} cihaz bekliyor`))),
      h("div", null, h("dt", null, "Port"), h("dd", null, `${n.port} `, h("small", null, n.active ? "UDP açık" : "UDP dinlenmiyor"))),
      h("div", null, h("dt", null, "Erişim"), h("dd", null, h("small", { class: "plain" }, "Yalnız internet"))),
      h("div", null, h("dt", null, "Adres"), h("dd", null, h("small", { class: "plain mono" }, `${n.server4}/24`))));
    $("wg-table").replaceChildren(
      h("div", { class: "tr head" }, h("span", { class: "c-sw" }, "Açık"), h("span", null, "Durum"), h("span", null, "Cihaz"),
        h("span", { class: "c-addr" }, "Adres"), h("span", { class: "c-hs" }, "Son görülme"), h("span", { class: "c-traffic" }, "Trafik"), h("span", { class: "c-dns" }, "")),
      ...list.map((p) => {
        const st = effState(p), cut = st === "off" || st === "netoff";
        return h("div", { class: "tr" + (cut ? " p-off" : "") },
          h("span", { class: "c-sw" }, h("button", { type: "button", class: "sw", role: "switch", "aria-checked": p.enabled, disabled: !n.active,
            title: !n.active ? "Önce arayüzü açın" : p.enabled ? "Bağlantıyı kapat" : "Bağlantıyı aç",
            "aria-label": `${p.name} bağlantısı`, onclick: () => togglePeer(n, p) })),
          h("span", { class: `status ${stClass(st)}` }, h("span", { class: "dotmark" }), STLABEL[st]),
          h("span", { class: "who2" }, h("strong", null, p.name),
            h("small", null, `DNS ${providerOf(p.dns, p.provider)} · keepalive ${kaText(p.keepalive)}`)),
          h("span", { class: "addr c-addr" }, h("span", { class: "mono" }, p.ipv4), h("span", { class: "mono v6" }, p.ipv6)),
          h("span", { class: "c-hs" }, cut ? "—" : since(p.handshake)),
          h("span", { class: "traffic c-traffic" }, h("span", null, h("i", null, "↓ "), bytes(p.rx)), h("span", null, h("i", null, "↑ "), bytes(p.tx))),
          h("span", { class: "acts c-dns" },
            h("button", { type: "button", class: "ib", title: "QR ve profil", "aria-label": `${p.name} QR ve profil`, disabled: !p.profile, onclick: () => openQr(n, p) }, svg("qr")),
            h("button", { type: "button", class: "ib del", title: "Sil", "aria-label": `${p.name} sil`, onclick: () => askPeerDelete(n, p) }, svg("trash")),
            h("button", { type: "button", class: "ib more-btn", title: "Diğer", "aria-label": `${p.name} için diğer işlemler`, "aria-haspopup": "menu", "aria-expanded": false,
              onclick: (e) => openRowMenu(e.currentTarget, n, p) }, svg("more"))));
      }));
    if (!list.length) {
      $("wg-table").append(h("div", { class: "empty-row" }, h("strong", null, "Bu ağda henüz cihaz yok"),
        h("span", null, "Aşağıdaki Peer ekle ile ilk cihazı ekleyin; QR hemen hazır olur.")));
    }
    const add = $("wg-add");
    add.onclick = () => openPeerAdd(n);
    add.replaceChildren(h("span", { class: "plus" }, svg("plus")),
      h("span", null, h("strong", null, "Peer ekle"),
        h("small", null, `${n.iface} · ${labelOf(n)} ağına yeni cihaz; anahtarlar sunucuda üretilir, QR hemen hazır olur`)));
  }

  // DD-143: kurulum WireGuard ağı yaratmaz; ilk ağı buradan kurulur.
  function renderWgEmpty() {
    $("wg-wrap").hidden = true;
    $("wg-empty").hidden = false;
    $("wg-empty").replaceChildren(
      h("div", { class: "empty-card" },
        h("span", { class: "empty-ico" }, svg("shield")),
        h("h2", null, "WireGuard yapılandırılmadı"),
        h("p", null, "Sunucu kurulumu WireGuard ağı oluşturmaz. İlk ağı burada kurarsınız: anahtar sunucuda üretilir, UDP portu açılır ve cihaz eklemeye hazır olur."),
        h("ul", { class: "conseq calm" },
          h("li", null, svg("shield"), h("span", null, "wg0 · 10.8.0.0/24 · sunucu 10.8.0.1")),
          h("li", null, svg("lock"), h("span", null, "Cihazlar yalnız internete çıkar; sunucu servislerine ve diğer ağlara erişemez.")),
          h("li", null, svg("plus"), h("span", null, "Kurduktan sonra bu sayfadan cihaz (peer) eklersiniz; QR hemen hazır olur."))),
        h("button", { type: "button", class: "btn btn-primary", onclick: () => { location.hash = "#/wireguard/ekle"; } },
          svg("plus"), "Yapılandır")));
  }

  function togglePeer(n, p) {
    post(peerPath(n.iface, p.name, "/durum"), { on: !p.enabled })
      .then(() => loadWg())
      .then(() => toast(p.enabled
        ? `${p.name} kapatıldı: bağlantısı kesildi, profili ve adresi duruyor.`
        : `${p.name} açıldı: cihaz birkaç saniye içinde kendiliğinden bağlanır.`))
      .catch(fail);
  }

  function toggleNet(n) {
    const list = n.peers, online = list.filter((p) => effState(Object.assign({ net: n }, p)) === "ok").length;
    if (!n.active) {
      post(netPath(n.iface, "/durum"), { on: true })
        .then(() => loadWg()).then(() => toast(`${n.iface} açıldı: UDP ${n.port} dinleniyor, cihazlar birkaç saniye içinde bağlanır.`))
        .catch(fail);
      return;
    }
    ask({
      title: `${n.iface} · ${labelOf(n)} kapatılsın mı?`, sub: `UDP ${n.port} · ${n.subnet4} · Yalnız internet`, calm: true,
      items: [
        ["shield", online ? `${online} bağlı cihazın bağlantısı hemen kesilir; ${list.length} cihazın hiçbiri bağlanamaz.` : `Bu ağdaki ${list.length} cihaz bağlanamaz.`],
        ["lock", "Arayüz durdurulur; açınca aynı anahtar ve adreslerle geri gelir."],
        ["refresh", n.iface === "wg0"
          ? "Anahtar, cihazlar ve profiller silinmez. Sunucu yeniden başlasa da kapalı kalır; kurulum yeniden çalışınca wg0 yeniden açılır."
          : "Anahtar, cihazlar ve profiller silinmez. Sunucu yeniden başlasa da kapalı kalır."],
      ],
      go: "Arayüzü kapat",
      onOk: () => post(netPath(n.iface, "/durum"), { on: false })
        .then(() => loadWg()).then(() => toast(`${n.iface} kapatıldı: ${list.length} cihazın bağlantısı kesildi.`)).catch(fail),
    });
  }

  function openNetSettings(n) {
    let busy = false, picker;
    const error = h("p", {class:"err-s", role:"alert", hidden:true});
    const dnsBox = h("div", {class:"sugg", role:"radiogroup", "aria-label":"Varsayılan DNS"});
    const save = h("button", {type:"submit", class:"btn btn-primary", id:"wn-save"}, "Ayarları kaydet");
    const fields = h("fieldset", {class:"wg-net-fields"},
      h("div", {class:"field"}, h("span", {class:"lbl"}, "Varsayılan DNS"), dnsBox,
        h("small", {class:"hint-s"}, "Yalnız yeni eklenecek cihazlara önerilir. Mevcut cihazların DNS ayarı ve QR/profili değişmez; cihazın Düzenle menüsünden ayrıca değiştirilebilir. Kaydet anahtarları, cihazları, portu ve adresleri değiştirmez; kapalı bir ağı başlatmaz.")), error,
      h("div", {class:"dlg-foot"}, h("button", {type:"button", class:"btn btn-quiet", onclick:shClose}, "Vazgeç"), save),
      h("div", {class:"wg-net-danger"}, h("p", null, "Yeniden üret tüm cihaz profillerini siler ve sunucu anahtarını değiştirir. Kaydedilmemiş DNS seçimi bu işlemde uygulanmaz."),
        h("button", {type:"button", class:"btn btn-sm btn-danger", onclick:()=>{shClose(); askRegen(netOf(n.iface) || n);}}, svg("refresh"), "Anahtarı yeniden üret")));
    function update() {
      const dns = picker.value();
      save.disabled = busy || !picker.check() || !dns || dns === n.dns;
    }
    const form = h("form", {class:"wg-net-settings", onsubmit:async event=>{
      event.preventDefault();
      if (save.disabled) return;
      busy=true; fields.disabled=true; error.hidden=true; update();
      try {
        await post(netPath(n.iface,"/ayarlar"), {dns:picker.value(),revision:n.revision});
        shClose(); await loadWg();
        toast(`${n.iface} ayarları kaydedildi. Mevcut anahtarlar ve cihaz profilleri korundu.`);
      } catch (err) { error.textContent=err.message; error.hidden=false; }
      finally {busy=false; fields.disabled=false; update();}
    }}, fields);
    k.dialog.show(`${n.iface} · Arayüz ayarları`, `${labelOf(n)} · UDP ${n.port} · ${n.subnet4}`, "sliders", form);
    picker = makeDnsPicker(dnsBox,"wn-dns",{badge:ips=>ips===n.dns?"kayıtlı":"",onChange:update});
    picker.set(n.dns); update(); dnsBox.querySelector("button")?.focus();
  }

  function askRegen(n) {
    const names = n.peers.map((p) => p.name);
    ask({
      title: `${n.iface} · ${labelOf(n)} yeniden üretilsin mi?`, sub: `UDP ${n.port} · ${n.subnet4} · Yalnız internet`, word: true, danger: true,
      items: [
        ["refresh", "Yeni sunucu anahtarı üretilir; port, adresler ve erişim aynı kalır."],
        ["shield", names.length ? `${names.length} cihazın profili ve QR kodu silinir (${names.join(", ")}); eski profillerle bağlanılamaz.` : "Bu ağda cihaz yok."],
        ["plus", "Cihazları Peer ekle ile yeniden eklemek gerekir. Geri alınamaz."],
      ],
      go: "Yeniden üret",
      onOk: () => post(netPath(n.iface, "/reset"), { confirm: "onayla" })
        .then((r) => loadWg().then(() => toast(`${n.iface} yeniden üretildi: ${r.peers} cihaz silindi, yeni sunucu anahtarı etkin.`))).catch(fail),
    });
  }

  function askDeleteNet(n) {
    const names = n.peers.map((p) => p.name);
    const last = nets().length === 1;
    ask({
      title: `${n.iface} · ${labelOf(n)} kaldırılsın mı?`, sub: `UDP ${n.port} · ${n.subnet4} · Yalnız internet`, word: true, danger: true,
      items: [
        ["shield", names.length ? `${names.length} cihazın bağlantısı kesilir; profilleri ve QR kodları silinir (${names.join(", ")}).` : "Bu ağda cihaz yok."],
        ["lock", `UDP ${n.port} kapanır; bu ağın güvenlik duvarı kuralları kaldırılır.`],
        ["trash", "Sunucu anahtarı silinir. Geri alınamaz; aynı ağ yeniden eklenirse cihazlara yeni profil gerekir."],
        last ? ["plus", "Bu son ağ: kaldırınca WireGuard yapılandırılmamış duruma döner, yeni ağı Yapılandır ile kurarsınız."] : null,
      ].filter(Boolean),
      go: "Arayüzü kaldır",
      onOk: () => post(netPath(n.iface, "/remove"), { confirm: "onayla" }).then((r) => {
        if (wgNet === n.iface) wgNet = "";
        return loadWg().then(() => toast(`${n.iface} kaldırıldı: ${r.peers} cihaz silindi, UDP ${n.port} kapandı.`));
      }).catch(fail),
    });
  }

  function askPeerDelete(n, p) {
    ask({
      title: `“${p.name}” silinsin mi?`, sub: `${n.iface} · ${p.ipv4} · ${p.ipv6}`, danger: true,
      items: [
        ["shield", "Bağlantısı hemen kesilir."],
        ["qr", "Profili ve QR kodu silinir; bu cihazı yeniden bağlamak için yeniden eklemek gerekir."],
        ["refresh", `${p.ipv4} adresi boşa çıkar ve yeni cihazlara verilebilir.`],
      ],
      go: "Peer'ı sil",
      onOk: () => post(peerPath(n.iface, p.name, "/remove")).then(() => loadWg()).then(() => toast(`“${p.name}” silindi.`)).catch(fail),
    });
  }

  /* satır menüsü (…) */
  const rowMenu = h("div", { class: "popmenu", id: "rowmenu", role: "menu", hidden: true });
  let menuBtn = null;
  function closeRowMenu() {
    if (rowMenu.hidden) return;
    rowMenu.hidden = true;
    if (menuBtn) menuBtn.setAttribute("aria-expanded", "false");
    menuBtn = null;
  }
  function openRowMenu(btn, n, p) {
    if (menuBtn === btn) { closeRowMenu(); return; }
    closeRowMenu();
    menuBtn = btn;
    btn.setAttribute("aria-expanded", "true");
    rowMenu.replaceChildren(
      h("button", { type: "button", role: "menuitem", onclick: () => { closeRowMenu(); openEdit(n, p); } },
        svg("pencil"), h("span", null, "Düzenle"), h("small", null, "DNS ve keepalive")),
      h("button", { type: "button", role: "menuitem", disabled: !p.profile, onclick: () => { closeRowMenu(); downloadProfile(n, p); } },
        svg("download"), h("span", null, "Profili indir"), h("small", null, "gizli anahtar içerir")));
    rowMenu.hidden = false;
    const r = btn.getBoundingClientRect();
    rowMenu.style.left = `${Math.max(8, Math.min(window.innerWidth - 218, r.right - 210))}px`;
    rowMenu.style.top = `${Math.min(window.innerHeight - 90, r.bottom + 6)}px`;
    rowMenu.querySelector("button").focus();
  }
  const onDocClick = (e) => { if (!e.target.closest("#rowmenu") && !e.target.closest(".more-btn")) closeRowMenu(); };
  const onDocKey = (e) => { if (e.key === "Escape") closeRowMenu(); };

  /* ---------- DNS seçici ---------- */
  function makeDnsPicker(box, idp, opts) {
    const st = { choice: DNS_PRESETS[0].ips, custom: "" };
    const value = () => (st.choice === "custom" ? normDns(st.custom) : st.choice);
    function check() {
      const bad = st.choice === "custom" && st.custom.trim() !== "" && !value();
      const err = $(`${idp}-err`), inp = $(`${idp}-custom`);
      if (err) err.hidden = !bad;
      if (inp) inp.setAttribute("aria-invalid", String(bad));
      return !bad;
    }
    function render() {
      box.replaceChildren(...DNS_PRESETS.map((d) => {
        const sel = st.choice === d.ips;
        return h("button", { type: "button", class: "sug" + (sel ? " on" : ""), role: "radio", "aria-checked": sel,
          onclick: () => { st.choice = d.ips; render(); opts.onChange(); } },
          h("strong", null, d.name), h("span", { class: "badge" }, opts.badge(d.ips)),
          h("span", { class: "meta" }, d.tag ? h("span", { class: "tagline" }, d.tag + " · ") : null, h("span", { class: "ips" }, d.ips)));
      }));
      const isCustom = st.choice === "custom";
      const custom = h("div", { class: "sug custom" + (isCustom ? " on" : "") },
        h("button", { type: "button", class: "sug-head", role: "radio", "aria-checked": isCustom,
          onclick: () => { if (!isCustom) { st.choice = "custom"; render(); opts.onChange(); } $(`${idp}-custom`).focus(); } },
          h("strong", null, "Custom"), h("span", { class: "badge" }, opts.badge(null)),
          h("span", { class: "tagline" }, "Kendi DNS adreslerinizi yazın; birden çoksa virgülle ayırın")));
      if (isCustom) {
        custom.append(h("div", { class: "cwrap" },
          h("input", { type: "text", id: `${idp}-custom`, value: st.custom, placeholder: "ör. 192.168.1.10, fd00::53", autocomplete: "off", spellcheck: "false",
            "aria-label": "Custom DNS adresleri", oninput: (e) => { st.custom = e.target.value; opts.onChange(); } }),
          h("small", { class: "err-s", id: `${idp}-err`, hidden: true }, "Geçerli IPv4 ya da IPv6 adreslerini virgülle ayırarak yazın.")));
      }
      box.append(custom);
    }
    function set(ips) {
      const preset = DNS_PRESETS.find((d) => d.ips === ips);
      st.choice = preset ? preset.ips : "custom";
      st.custom = preset ? "" : ips || "";
      render();
    }
    return { set, value, check, render };
  }

  /* ---------- düzenle penceresi (DNS ve keepalive) ---------- */
  function openEdit(n, p) {
    let picker = null;
    const ka = h("input", { type: "number", id: "pe-ka", min: "0", max: "65535", autocomplete: "off", value: String(p.keepalive) });
    const chips = h("div", { class: "chips-s", id: "pe-ka-chips" });
    const save = h("button", { type: "submit", class: "btn btn-primary", id: "pe-save", disabled: true }, "Kaydet");
    const dnsBox = h("div", { class: "sugg", id: "pe-sugg", role: "radiogroup", "aria-labelledby": "pe-dns-lbl" });
    function renderKaChips() {
      const v = ka.value.trim();
      chips.replaceChildren(...[["0", "Kapalı"], ["21", "21 sn · önerilen"], ["25", "25 sn"]].map(([val, label]) =>
        h("button", { type: "button", "aria-pressed": v === val, onclick: () => { ka.value = val; validate(); } }, label)));
    }
    function validate() {
      if (!picker) return;
      const dnsOk = picker.check(), dns = picker.value();
      const kaRaw = ka.value.trim(), kaNum = /^\d+$/.test(kaRaw) ? Number(kaRaw) : NaN, kaOk = kaNum >= 0 && kaNum <= 65535;
      ka.setAttribute("aria-invalid", String(!kaOk));
      save.disabled = !dnsOk || !dns || !kaOk || (dns === p.dns && kaNum === p.keepalive);
      renderKaChips();
    }
    const form = h("form", { class: "pe-form", novalidate: true, onsubmit: (e) => {
      e.preventDefault();
      if (save.disabled) return;
      const dns = picker.value(), kaNum = Number(ka.value.trim());
      const jobs = [];
      if (dns !== p.dns) jobs.push(() => post(peerPath(n.iface, p.name, "/dns"), { dns }));
      if (kaNum !== p.keepalive) jobs.push(() => post(peerPath(n.iface, p.name, "/keepalive"), { keepalive: kaNum }));
      shClose();
      jobs.reduce((chain, job) => chain.then(job), Promise.resolve())
        .then(() => loadWg())
        .then(() => toast(`${p.name} güncellendi: DNS ${providerOf(dns)}, keepalive ${kaText(kaNum)}. Cihazda yeni QR'ı okutun.`,
          { label: "QR'ı göster", fn: () => openQr(netOf(n.iface), (netOf(n.iface).peers.find((x) => x.name === p.name) || p)) }))
        .catch(fail);
    } },
      h("div", { class: "field" }, h("span", { class: "lbl", id: "pe-dns-lbl" }, "DNS sunucuları"), dnsBox),
      h("div", { class: "field" }, h("label", { for: "pe-ka" }, "PersistentKeepalive (saniye)"),
        h("div", { class: "ka-row" }, ka, chips),
        h("small", { class: "hint-s" }, "Cihaz boştayken bağlantıyı açık tutmak için kaç saniyede bir paket yollasın. 0 = kapalı; mobil ağlarda 21 önerilir.")),
      h("div", { class: "infoline-s" }, svg("info"), h("span", null, "Anahtar ve adres değişmez. Kaydedince cihazda yeni QR'ı okutun: eski tüneli silip yenisini ekleyin.")),
      h("div", { class: "dlg-foot" }, h("button", { type: "button", class: "btn btn-quiet", onclick: shClose }, "Vazgeç"), save));
    k.dialog.show(`${p.name} · düzenle`, `${n.iface} · ${p.ipv4} · şu an DNS ${providerOf(p.dns, p.provider)}, keepalive ${kaText(p.keepalive)}`, "pencil", form);
    picker = makeDnsPicker(dnsBox, "pe-dns", {
      badge: (ips) => {
        const isPreset = DNS_PRESETS.some((d) => d.ips === p.dns);
        if (ips === null) return isPreset ? "" : "şu an";
        return ips === p.dns ? "şu an" : ips === n.dns ? "ağın varsayılanı" : "";
      },
      onChange: validate,
    });
    picker.set(p.dns);
    ka.addEventListener("input", validate);
    validate();
    const on = dnsBox.querySelector('[aria-checked="true"]');
    if (on) on.focus();
  }

  /* ---------- peer ekle ve QR ---------- */
  let PA = null;
  function openPeerAdd(n) {
    PA = { n, name: "", dns: n.dns || (WG.defaults && WG.defaults.dns) || DNS_PRESETS[0].ips, ka: (WG.defaults && WG.defaults.keepalive) || 21 };
    renderPeerAdd();
    const inp = $("pa-name");
    if (inp) inp.focus();
  }
  function renderPeerAdd() {
    const n = PA.n;
    const nameErr = PA.name && !NAME_RE.test(PA.name) ? "Harf, rakam, nokta, alt çizgi ve tire; en çok 32 karakter." : "";
    const taken = n.peers.some((p) => p.name === PA.name) ? "Bu ağda aynı adlı bir cihaz zaten var." : "";
    const err = nameErr || taken;
    k.dialog.show(`${dative(n.iface)} peer ekle`, `${labelOf(n)} · ${n.subnet4} · anahtarlar sunucuda üretilir`, "shield",
      h("div", { class: "field" },
        h("label", { for: "pa-name" }, "Cihaz adı"),
        h("input", { type: "text", id: "pa-name", value: PA.name, maxlength: "32", autocomplete: "off", spellcheck: "false",
          placeholder: "ör. iphone, macbook, tv-salon", "aria-invalid": String(!!err),
          oninput: (e) => { PA.name = e.target.value.trim(); updatePeerAdd(); } }),
        h("small", { class: "err-s", id: "pa-err", hidden: !err }, err),
        h("small", { class: "hint-s" }, "Profil dosyasının adı da bu olur.")),
      h("div", { class: "field" },
        h("span", { class: "lbl" }, "DNS sunucuları"),
        h("div", { class: "sugg", id: "pa-sugg", role: "radiogroup", "aria-label": "DNS sunucuları" })),
      h("div", { class: "field" },
        h("label", { for: "pa-ka" }, "PersistentKeepalive (saniye)"),
        h("div", { class: "ka-row" }, h("input", { type: "number", id: "pa-ka", min: "0", max: "65535", value: String(PA.ka), autocomplete: "off",
          oninput: (e) => { PA.ka = e.target.value.trim(); updatePeerAdd(); } }),
          h("div", { class: "chips-s" }, ...[["0", "Kapalı"], ["21", "21 sn · önerilen"], ["25", "25 sn"]].map(([val, label]) =>
            h("button", { type: "button", "aria-pressed": String(PA.ka) === val, onclick: () => { PA.ka = val; renderPeerAdd(); } }, label)))),
        h("small", { class: "hint-s" }, "0 = kapalı; mobil ağlarda 21 önerilir.")),
      h("div", { class: "dlg-foot" },
        h("button", { type: "button", class: "btn btn-quiet", onclick: shClose }, "Vazgeç"),
        h("button", { type: "button", class: "btn btn-primary", id: "pa-go", onclick: createPeer }, svg("plus"), "Peer ekle")));
    PA.picker = makeDnsPicker($("pa-sugg"), "pa-dns", {
      badge: (ips) => (ips === n.dns ? "ağın varsayılanı" : ips === DNS_PRESETS[0].ips ? "önerilen" : ""),
      onChange: () => updatePeerAdd(),
    });
    PA.picker.set(PA.dns);
    updatePeerAdd();
  }
  function updatePeerAdd() {
    const n = PA.n;
    const nameOk = NAME_RE.test(PA.name) && !n.peers.some((p) => p.name === PA.name);
    const ka = /^\d+$/.test(String(PA.ka)) ? Number(PA.ka) : NaN;
    const dns = PA.picker.value(), dnsOk = PA.picker.check();
    const err = $("pa-err");
    if (err) {
      const text = PA.name && !NAME_RE.test(PA.name) ? "Harf, rakam, nokta, alt çizgi ve tire; en çok 32 karakter."
        : n.peers.some((p) => p.name === PA.name) ? "Bu ağda aynı adlı bir cihaz zaten var." : "";
      err.textContent = text;
      err.hidden = !text;
    }
    const go = $("pa-go");
    if (go) go.disabled = !nameOk || !dns || !dnsOk || !(ka >= 0 && ka <= 65535);
  }
  function createPeer() {
    const n = PA.n, name = PA.name, dns = PA.picker.value(), ka = Number(PA.ka);
    const mtu = (WG.defaults && WG.defaults.mtu) || 1420;
    $("pa-go").disabled = true;
    post(netPath(n.iface, "/peers"), { name, dns, keepalive: ka, mtu })
      .then(() => loadWg())
      .then(() => {
        const fresh = netOf(n.iface), peer = fresh && fresh.peers.find((p) => p.name === name);
        if (fresh && peer) openQr(fresh, peer, true);
        toast(`“${name}” eklendi.`);
      })
      .catch((e) => { fail(e); updatePeerAdd(); });
  }

  function openQr(n, p, fresh) {
    k.dialog.show(`${p.name} · QR`, `${n.iface} · ${p.ipv4} · ${providerOf(p.dns, p.provider)} DNS`, "qr",
      h("div", { class: "qrbox", id: "qr-box" }, h("p", { class: "hint-s" }, "QR hazırlanıyor…")),
      h("div", { class: "infoline-s" }, svg("lock"),
        h("span", null, "QR ve profil cihazın gizli anahtarını taşır. Yalnız cihazın kendisine okutun; ekran görüntüsü almayın.")),
      h("div", { class: "dlg-foot" },
        h("button", { type: "button", class: "btn btn-quiet", onclick: () => downloadProfile(n, p) }, svg("download"), "Profili indir"),
        h("button", { type: "button", class: "btn btn-primary", onclick: shClose }, fresh ? "Bitti" : "Kapat")));
    api(peerPath(n.iface, p.name, "/qr.png"), { blob: true }).then((blob) => {
      const url = URL.createObjectURL(blob);
      const img = h("img", { src: url, alt: `${p.name} için WireGuard QR kodu` });
      img.addEventListener("load", () => URL.revokeObjectURL(url));
      const box = $("qr-box");
      if (box) box.replaceChildren(img);
    }).catch((e) => {
      const box = $("qr-box");
      if (box) box.replaceChildren(h("p", { class: "err-s" }, e.message));
    });
  }
  function downloadProfile(n, p) {
    api(peerPath(n.iface, p.name, "/profile"), { blob: true }).then((blob) => {
      const url = URL.createObjectURL(blob);
      const a = h("a", { href: url, download: `${p.name}.conf` });
      document.body.append(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
    }).catch(fail);
  }

  /* ---------- arayüz ekle ---------- */
  function nextNetId() {
    const max = (WG && WG.max ? WG.max : 10) - 1;
    for (let i = 0; i <= max; i++) if (!netOf(`wg${i}`)) return i;
    return null;
  }
  const PORT_START = 61020;
  function firstPort() {
    const def = WG && WG.defaults ? WG.defaults.port : 0;
    return def && !portOwner(def) ? def : suggestPort();
  }
  function portOwner(port) {
    const n = nets().find((x) => x.port === port);
    if (n) return n.iface;
    return (WG && WG.reserved || []).includes(port) ? "sunucu" : null;
  }
  function suggestPort() {
    let port = PORT_START;
    while (portOwner(port)) port++;
    return port;
  }
  const NA = { i: null };
  let naDns = null;
  function renderAddNet() {
    if (!WG) return;
    const i = nextNetId();
    if (i == null) { location.hash = "#/wireguard"; toast("En çok 9 ek ağ oluşturulabilir."); return; }
    NA.i = i;
    $("na-label").value = "";
    $("na-port").value = String(nets().length ? suggestPort() : firstPort());
    $("na-ident").replaceChildren(h("span", { class: "big" }, `wg${i}`),
      h("span", { class: "mono" }, `10.8.${i}.0/24`), h("span", { class: "mono" }, `sunucu 10.8.${i}.1`), h("span", { class: "hint-s" }, "Yalnız internet"));
    naDns.set(DNS_PRESETS[0].ips);
    updateAddNet();
    $("na-label").focus();
  }
  function addNetDraft() {
    const i = NA.i, label = $("na-label").value.trim();
    const raw = $("na-port").value.trim(), port = /^\d+$/.test(raw) ? Number(raw) : NaN;
    let portErr = "";
    if (!(port >= 1024 && port <= 65535)) portErr = "1024 ile 65535 arasında bir port yazın.";
    else if (portOwner(port)) portErr = `UDP ${port} kullanımda (${portOwner(port)}); bu port reddedildi, başka bir port yazın.`;
    return { i, id: `wg${i}`, label, port, portErr,
      subnet: `10.8.${i}.0/24`, dns: naDns.value(), dnsOk: naDns.check() };
  }
  function updateAddNet() {
    if (NA.i == null) return;
    const d = addNetDraft();
    $("na-port-err").textContent = d.portErr;
    $("na-port-err").hidden = !d.portErr;
    $("na-port").setAttribute("aria-invalid", String(!!d.portErr));
    const will = [
      "Yeni sunucu anahtarı üretilir.",
      `UDP ${Number.isNaN(d.port) ? "…" : d.port} internete açılır; güvenlik duvarı kuralları kurulur.`,
      `Yeni cihazlara ${d.dns ? providerOf(d.dns) : "seçilen"} DNS önerilir.`,
    ];
    $("na-will").replaceChildren(...will.map((text) => h("li", null, svg("check"), h("span", null, text))));
    $("na-create").disabled = !!d.portErr || !d.dns || !d.dnsOk;
  }
  function createNet() {
    const d = addNetDraft();
    if (d.portErr || !d.dns || !d.dnsOk) return;
    $("na-create").disabled = true;
    post(`${BASE}/nets`, { port: String(d.port), dns: d.dns, label: d.label })
      .then((r) => {
        wgNet = r.iface;
        return loadWg().then(() => {
          location.hash = "#/wireguard";
          toast(`${r.iface} oluşturuldu: UDP ${r.port} açık. Şimdi Peer ekle ile cihaz ekleyin.`);
        });
      })
      .catch((e) => { fail(e); updateAddNet(); });
  }

  /* ---------- sayfa: bölüm, başlık, rota ---------- */
  function buildSection(section) {
    section.append(
      h("div", { class: "wg-empty", id: "wg-empty", hidden: true }),
      h("div", { class: "netwrap", id: "wg-wrap" },
        h("nav", { class: "nettabs", id: "wg-tabs", role: "tablist", "aria-label": "WireGuard ağları" }),
        h("div", { class: "netpanel first", id: "wg-panel", role: "tabpanel" },
          h("div", { class: "offbar", id: "wg-offbar", hidden: true }),
          h("dl", { class: "summary", id: "wg-summary" }),
          h("div", { class: "table wg-t", id: "wg-table" }),
          h("button", { type: "button", class: "addrow", id: "wg-add" }))),
      // Arayüz ekle (#/wireguard/ekle): tek kart, pencerelerle aynı genişlikte. Sıradaki boş ağ
      // kendiliğinden seçilir; etiket ve port yan yana, DNS seçicisi pencerelerdekiyle aynı.
      h("div", { class: "addpage", id: "wg-ekle", hidden: true },
        h("article", { class: "card addcard", "aria-labelledby": "na-title" },
          h("div", { class: "card-head" }, h("h2", { id: "na-title" }, svg("shield"), "Yeni ağ"), h("span", { class: "hint-s" }, "Sıradaki boş ağ seçildi")),
          h("div", { class: "ident-row", id: "na-ident" }),
          h("div", { class: "add-fields" },
            h("div", { class: "field" },
              h("label", { for: "na-label" }, "Etiket"),
              h("input", { type: "text", id: "na-label", maxlength: "24", autocomplete: "off", spellcheck: "false", placeholder: "ör. Misafir, İş" }),
              h("small", { class: "hint-s" }, "Yalnız Konsol'da görünür; boş bırakılabilir.")),
            h("div", { class: "field" },
              h("label", { for: "na-port" }, "UDP portu"),
              h("input", { type: "number", id: "na-port", min: "1024", max: "65535", autocomplete: "off" }),
              h("small", { class: "err-s", id: "na-port-err", hidden: true }),
              h("small", { class: "hint-s", id: "na-port-hint" }, "1024–65535; kullanılmayan port."))),
          h("div", { class: "field" },
            h("span", { class: "lbl", id: "na-dns-lbl" }, "Varsayılan DNS"),
            h("div", { class: "sugg", id: "na-sugg", role: "radiogroup", "aria-labelledby": "na-dns-lbl" }),
            h("small", { class: "hint-s" }, "Bu ağa eklenen cihazlara önerilir.")),
          h("ul", { class: "will", id: "na-will" }),
          h("div", { class: "infoline-s" }, svg("info"), h("span", null, "Cihazlar yalnız internete çıkar; sunucu servisleri, özel ağlar ve diğer cihazlar erişime kapalıdır.")),
          h("div", { class: "dlg-foot" },
            h("button", { class: "btn btn-quiet", type: "button", "data-go": "#/wireguard" }, "Vazgeç"),
            h("button", { class: "btn btn-primary", type: "button", id: "na-create", disabled: true }, "Arayüzü oluştur")))));
    naDns = makeDnsPicker($("na-sugg"), "na-dns", { badge: (ips) => (ips === DNS_PRESETS[0].ips ? "önerilen" : ""), onChange: () => updateAddNet() });
    $("na-label").addEventListener("input", updateAddNet);
    $("na-port").addEventListener("input", updateAddNet);
    $("na-create").addEventListener("click", createNet);
  }
  function show(sub) {
    const adding = sub === "ekle";
    $("wg-ekle").hidden = !adding;
    if (adding) {
      $("wg-wrap").hidden = true;
      $("wg-empty").hidden = true;
      if (WG) renderAddNet(); else NA.i = null;
    } else {
      NA.i = null;
      renderWg();
    }
  }
  return {
    mount(section) {
      buildSection(section);
      document.body.append(rowMenu);
      document.addEventListener("click", onDocClick, true);
      document.addEventListener("keydown", onDocKey);
      window.addEventListener("resize", closeRowMenu);
      window.addEventListener("scroll", closeRowMenu, true);
    },
    unmount() {
      closeRowMenu();
      rowMenu.remove();
      document.removeEventListener("click", onDocClick, true);
      document.removeEventListener("keydown", onDocKey);
      window.removeEventListener("resize", closeRowMenu);
      window.removeEventListener("scroll", closeRowMenu, true);
      WG = null;
      RATES.clear();
    },
    // İlk ağ kurulurken başlık "WireGuard'ı yapılandır" olur; veri gelince Konsol başlığı yeniler.
    title: (sub) => (sub === "ekle" ? (WG && !nets().length ? "WireGuard'ı yapılandır" : "Arayüz ekle") : "WireGuard"),
    eyebrow: (sub) => (sub === "ekle" ? "WireGuard · yeni ağ" : "Cihazlar ve ağlar"),
    actions: (sub) => (sub === "ekle"
      ? [h("button", { type: "button", class: "btn btn-quiet", "data-go": "#/wireguard" }, svg("back"), "WireGuard")] : []),
    render(sub) { show(sub); loadWg(); },
    poll() { loadWg(); },
  };
  });
})();
