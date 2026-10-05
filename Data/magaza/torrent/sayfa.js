/* qBittorrent paketinin Konsol sayfası (DD-202). Konsol bu dosyayı paket kuruluyken
   /uygulama/torrent/sayfa.js olarak yükler; sayfa window.Konsol.sayfa ile kaydolur. Servis
   başlat/durdur ve ilk giriş hesabı Konsol'un modül API'sinden, hesap/dizin ayarları ve durum
   paketin kendi API'sinden (/api/uygulama/torrent/*) gelir. Sayfa CSP altında çalışır. */
(() => {
  "use strict";
  window.Konsol.sayfa("torrent", (k) => {
  const { h, svg, $, api, post, enc, toast, fail, ask, credRow, copyButton, copyText, modPill, modAct } = k;
  const ROUTE = "torrent", ID = "torrent", BASE = "/api/uygulama/torrent";
  let DURUM = null, busy = false, message = "", readAt = 0, failed = false;
  const publicPanel = () => location.protocol === "https:";
  // DD-195: on the public (HTTPS) Konsol address the app opens by its own public name,
  // which Settings → Caddy must have turned on; on the tailnet address by its tailnet name.
  const appUrl = () => { const urls = (k.module(ID) || {}).urls || {}; return publicPanel() ? urls.internet || "" : urls.tailscale || ""; };
  const hhmm = (at) => new Date(at * 1000).toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });

  /* ---------- küçük yapı taşları (ayarlar.css'teki biçemlerle) ---------- */
  const note = (text, warn = false) => h("p", { class: "as-note" + (warn ? " warn" : "") }, text);
  const card = (title, subtitle, ...body) => h("article", { class: "card as-card" }, h("div", { class: "card-head" }, h("div", null, h("h2", null, title), h("small", null, subtitle))), ...body);
  function field(label, control, hint) {
    control.setAttribute("aria-label", label);
    return h("label", { class: "as-field" }, h("span", null, label), control, hint ? h("small", null, hint) : null);
  }
  const btn = (text, action, primary = false) => h("button", { type: "button", class: "btn btn-sm" + (primary ? " btn-primary" : ""), disabled: busy, onclick: action }, text);

  /* ---------- durum (paket API'si) ---------- */
  function loadDurum() {
    return api(BASE + "/durum").then((d) => { DURUM = d; failed = false; readAt = Date.now() / 1000; paint(); })
      .catch((e) => { failed = true; DURUM = null; paint(); fail(e); });
  }

  /* ---------- servis çubuğu ---------- */
  function renderToolbar() {
    const box = $("torrent-status");
    if (!box) return;
    const m = k.module(ID);
    if (!m || !m.installed) { box.replaceChildren(h("p", { class: "hint-s" }, "Kurulum durumu okunuyor…")); return; }
    const running = m.state === "calisiyor", url = appUrl();
    // replaceChildren yazar: boş (null) öğe metne dönüşüp "null" görünürdü; yalnız var olanlar konur.
    box.replaceChildren(...[modPill(m),
      h("button", { type: "button", class: "btn btn-quiet", disabled: !!m.busy, onclick: () => {
        if (!running) { modAct(ID, "baslat"); return; }
        ask({ title: "qBittorrent durdurulsun mu?", calm: true, go: "Durdur", items: [["pause", "Süren indirmeler duraklar. Başlatana kadar servis kapalı kalır."]],
          onOk: () => modAct(ID, "durdur") });
      } }, svg(running ? "pause" : "play"), running ? "Durdur" : "Başlat"),
      running && url ? h("a", { class: "btn btn-primary", id: "torrent-open", href: url, target: "_blank", rel: "noopener" }, "Web arayüzünü aç ↗") : null,
      running && !url && publicPanel() ? h("p", { class: "hint-s", id: "torrent-open-note" }, "İnternetten açmak için qBittorrent'in internet yayınını açın: ",
        h("a", { href: "#/ayarlar/web" }, "Ayarlar → Caddy")) : null,
      // DD-211: uygulamanın konteyneri ana menüdeki yönetim sayfasında açılır.
      h("a", { class: "linkbtn", id: "torrent-container", href: "#/konteynerler" + (DURUM && DURUM.container ? "/" + enc(DURUM.container) : "") }, "Konteyner"),
      h("a", { class: "linkbtn", href: "#/moduller" }, "App Store’da yönet")].filter(Boolean));
  }

  /* ---------- ilk giriş hesabı: parola yalnız göz ya da kopyala ile, açıkça istenince gelir,
     30 sn sonra (sekme gizlenince hemen) ekrandan kalkar, hiç yoklanmaz (DD-151). ---------- */
  let ACCT = null, REVEAL = null, acctLoading = false, acctFailed = false;
  const REVEAL_SECONDS = 30;
  const acctUrl = (withPass) => `/api/konsol/moduller/${ID}/hesap${withPass ? "?parola=1" : ""}`;
  function loadAccount() {
    if (acctLoading) return Promise.resolve(ACCT);
    acctLoading = true;
    return api(acctUrl(false)).then((a) => { ACCT = a; acctFailed = false; paintAccount(); return a; })
      .catch(() => { ACCT = null; acctFailed = true; paintAccount(); }).finally(() => { acctLoading = false; });
  }
  function revealPass() {
    return api(acctUrl(true)).then((a) => {
      ACCT = Object.assign({}, a);
      delete ACCT.pass;
      hidePass();
      const r = REVEAL = { pass: a.pass, left: REVEAL_SECONDS };
      r.timer = setInterval(() => {
        r.left -= 1;
        if (r.left <= 0) { hidePass(); return; }
        document.querySelectorAll("[data-acct-left]").forEach((el) => { el.textContent = `${r.left} sn sonra gizlenir`; });
      }, 1000);
      paintAccount();
    }).catch(fail);
  }
  function hidePass() {
    if (!REVEAL) return;
    clearInterval(REVEAL.timer);
    REVEAL = null;
    paintAccount();
  }
  const onHidden = () => { if (document.hidden) hidePass(); };
  function copyPassButton() {
    const b = h("button", { type: "button", class: "ib", title: "Parola kopyala", "aria-label": "Parola kopyala", onclick: async () => {
      let pass = REVEAL && REVEAL.pass;
      if (!pass) {
        try { pass = (await api(acctUrl(true))).pass; } catch (e) { fail(e); return; }
      }
      const ok = await copyText(pass);
      pass = "";
      if (!ok) { toast("Pano kullanılamadı; parolayı gösterip seçerek kopyalayın."); return; }
      b.replaceChildren(svg("check"));
      setTimeout(() => b.replaceChildren(svg("copy")), 1200);
    } }, svg("copy"));
    return b;
  }
  function accountBlock() {
    const a = ACCT, r = REVEAL;
    const cred = h("div", { class: "cred" });
    if (!a && acctFailed) {
      cred.append(h("p", { class: "hint-s" }, "Hesap okunamadı. Servisin çalıştığını kontrol edip sayfayı yenileyin."));
    } else if (!a) {
      cred.append(h("p", { class: "hint-s" }, "Hesap okunuyor…"));
      loadAccount();
    } else {
      const url = appUrl();
      const address = url ? url.replace(/^[a-z]+:\/\//, "") : a.host;
      cred.append(...[
        address ? credRow("Adres", address, [copyButton(address, "Adres")]) : null,
        credRow("Kullanıcı", a.user, [copyButton(a.user, "Kullanıcı")]),
        a.temp ? credRow("Geçici", r ? r.pass : "•".repeat(9), [
          h("button", { type: "button", class: "ib", title: r ? "Gizle" : "Günlükten göster", "aria-label": r ? "Geçici parolayı gizle" : "Geçici parolayı göster",
            onclick: () => (REVEAL ? hidePass() : revealPass()) }, svg("eye")),
          copyPassButton()], false, r ? "" : "masked-row") : null,
        h("div", { class: "acct-wg" }, svg("info"), h("span", null, a.temp
          ? "qBittorrent ilk açılışta geçici parolayı günlüğüne yazar; Konsol onu oradan okur ve her yeniden başlatmada değişir. Girişten sonra aşağıdan kalıcı bir parola belirleyin."
          : "Parola kayıtlı; Konsol mevcut parolayı göstermez. Aşağıdan yeni kullanıcı adı veya parola belirleyebilirsiniz."))].filter(Boolean));
    }
    return h("div", { class: "acct-inner", "data-acct": ID }, cred,
      h("div", { class: "acct-meta" }, h("span", null), r ? h("span", { "data-acct-left": ID }, `${r.left} sn sonra gizlenir`) : null));
  }
  function paintAccount() {
    document.querySelectorAll(`[data-acct="${ID}"]`).forEach((el) => el.replaceWith(accountBlock()));
  }

  /* ---------- hesap ve indirme dizini (paket API'si; DD-165: doğrudan kaydedilir) ---------- */
  async function saveAccount(account) {
    if (busy) return;
    busy = true; message = "qBittorrent hesabı kaydediliyor…"; renderSettings();
    try {
      const result = await post(BASE + "/hesap", account);
      delete account.password;
      if (DURUM && result.username) DURUM.username = result.username;
      message = "qBittorrent hesabı kaydedildi. Web arayüzüne yeni bilgilerle giriş yapabilirsiniz.";
      toast(message);
      hidePass(); ACCT = null;
      await loadDurum();
    } catch (e) {
      message = `Hesap kaydı doğrulanamadı. ${e.message} Sonucu Yenile ile kontrol edin; yeniden denemek için parolayı tekrar girin.`;
      fail(e);
    } finally { delete account.password; busy = false; renderSettings(); }
  }
  async function saveFolder(path) {
    if (busy) return;
    busy = true; message = "İndirme dizini kaydediliyor…"; renderSettings();
    try {
      const result = await post(BASE + "/dizin", { save: path });
      message = `İndirme dizini kaydedildi: ${result.save}. Mevcut dosyalar taşınmaz.`;
      toast("İndirme dizini kaydedildi.");
      await loadDurum();
    } catch (e) {
      message = `İndirme dizini kaydedilemedi. ${e.message}`;
      fail(e);
    } finally { busy = false; renderSettings(); }
  }
  function chooseFolder() {
    const box = h("div", { class: "as-stack" });
    k.dialog.show("İndirme klasörü seç", "Yalnız indirmeler veya kütüphane altındaki gerçek klasörler", "folder", box);
    async function show(path) {
      box.replaceChildren(note("Klasörler okunuyor…"));
      try {
        const r = await api("/api/konsol/ayarlar/klasorler" + (path ? "?path=" + encodeURIComponent(path) : ""));
        box.replaceChildren(btn("Başlangıç dizinleri", () => show()), ...(path ? [note(path)] : []),
          ...r.items.map((x) => h("div", { class: "as-folder" }, h("div", null, h("strong", null, x.path), h("small", null, `${(x.free / 1073741824).toFixed(1)} GB boş`)),
            btn("İçine gir", () => show(x.path)), btn("Seç", () => { k.dialog.close(); saveFolder(x.path); }))),
          h("div", { class: "dlg-foot" }, h("button", { type: "button", class: "btn btn-quiet", onclick: k.dialog.close }, "Vazgeç")));
      } catch (e) { box.replaceChildren(note(e.message, true)); }
    }
    show();
  }
  function settingsCards() {
    if (failed) return [note("qBittorrent durumu okunamadı; Yenile ile tekrar deneyin.", true)];
    if (!DURUM) return [note("Okunuyor…")];
    if (DURUM.error) return [note(DURUM.error, true), note(`Profil: ${DURUM.profile}`)];
    const username = h("input", { name: "username", required: true, value: DURUM.username || "", maxlength: 64, pattern: "[A-Za-z0-9._@\\-]{1,64}", autocomplete: "username", disabled: busy });
    const password = h("input", { name: "password", type: "password", minlength: 8, maxlength: 256, autocomplete: "new-password", disabled: busy });
    const repeat = h("input", { name: "repeat", type: "password", autocomplete: "new-password", disabled: busy });
    const form = h("form", { class: "as-body", onsubmit: (e) => {
      e.preventDefault();
      if (busy) return;
      if (password.value !== repeat.value) { repeat.setCustomValidity("Parolalar aynı olmalı."); repeat.reportValidity(); return; }
      const account = {};
      if (username.value !== DURUM.username) account.username = username.value;
      if (password.value) account.password = password.value;
      if (!Object.keys(account).length) { toast("Hesap bilgilerinde değişiklik yok."); return; }
      password.value = repeat.value = ""; username.value = username.defaultValue;  // taslak sunucuya gitti; form artık sunucuyu izler
      saveAccount(account);
    } }, h("div", { class: "as-formgrid" }, field("Kullanıcı adı", username), h("div"), field("Yeni parola", password, "Boş bırakılırsa kayıtlı parola korunur; en az 8 karakter."), field("Yeni parola (tekrar)", repeat)),
    h("div", { class: "as-inline" }, h("button", { type: "submit", class: "btn btn-primary", disabled: busy }, "Hesabı kaydet")),
    note("Doğrudan kaydedilir; ek onay gerekmez. Çalışıyorsa qBittorrent kısa süre yeniden başlar."),
    note("Henüz kalıcı parola belirlenmediyse geçici ilk giriş parolası yeniden başlatmada değişebilir. Kalıcı giriş için yeni parola belirleyin."));
    repeat.addEventListener("input", () => repeat.setCustomValidity(""));
    password.addEventListener("input", () => repeat.setCustomValidity(""));
    return [card("Web arayüzü hesabı", "Mevcut parola gösterilmez", form),
      card("İndirme dizini", "Yalnız yeni torrentlerin varsayılanı", h("div", { class: "as-body" }, h("code", null, DURUM.save || "—"),
        h("div", null, btn("Klasör seç", chooseFolder)),
        note("Seçilen dizin mevcut ve servis kullanıcısına yazılabilir olmalı; doğrudan kaydedilir, çalışıyorsa qBittorrent kısa süre yeniden başlar. İndirme klasörü dışındaki bir dizin konteynere aynı yolla bağlanır. Mevcut torrentler ve yarım indirmelerin yerleri taşınmaz."),
        DURUM.save && !DURUM.save_inside ? note("Dizin indirme klasörünün dışında; konteynere ayrıca bağlanmıştır.") : null),
      note(`Profil: ${DURUM.profile}. Çöp, paylaşım iç dizinleri, gizli klasörler ve sembolik bağlantılar seçilemez.`))];
  }
  /* Hesap formundaki taslak (yazılmış ama kaydedilmemiş alanlar ve imleç) 10 sn'lik yoklama yeniden
     çizerken korunur; aksi hâlde tekrar parolası yazılırken ilk parola silinirdi. */
  function draftOf(box) {
    const form = box.querySelector("form.as-body");
    if (!form) return null;
    const draft = { values: {}, focus: null };
    for (const el of form.querySelectorAll("input")) {
      if (el.value !== el.defaultValue) draft.values[el.name] = el.value;
      if (el === document.activeElement) draft.focus = { name: el.name, start: el.selectionStart, end: el.selectionEnd };
    }
    return draft;
  }
  function restoreDraft(box, draft) {
    const form = draft && box.querySelector("form.as-body");
    if (!form) return;
    for (const el of form.querySelectorAll("input")) if (el.name in draft.values) el.value = draft.values[el.name];
    const el = draft.focus && form.querySelector(`input[name="${draft.focus.name}"]`);
    if (el && !el.disabled) { el.focus(); try { el.setSelectionRange(draft.focus.start, draft.focus.end); } catch (_) { /* tür izin vermiyorsa imleç sona gider */ } }
  }
  function renderSettings() {
    const box = $("torrent-settings");
    if (!box) return;
    const draft = draftOf(box);
    box.replaceChildren(...[message ? h("p", { class: "as-message", role: "status" }, message) : null, ...settingsCards()].filter(Boolean));
    restoreDraft(box, draft);
    const stamp = $("torrent-stamp");
    if (stamp) stamp.textContent = readAt ? "Son okuma " + hhmm(readAt) : "Okunuyor…";
  }
  function paint() { if (k.route() === ROUTE) { renderToolbar(); renderSettings(); } }

  return {
    mount(section) {
      section.append(
        h("div", { id: "torrent-status", class: "app-toolbar" }),
        h("details", { class: "card app-account" }, h("summary", null, "İlk giriş bilgileri"), h("div", { id: "torrent-account" })),
        h("div", { id: "torrent-settings" }));
      section.querySelector("details").addEventListener("toggle", (e) => {
        if (e.currentTarget.open) { $("torrent-account").replaceChildren(accountBlock()); loadAccount(); }
        else { hidePass(); $("torrent-account").replaceChildren(); }
      });
      document.addEventListener("visibilitychange", onHidden);
    },
    unmount() {
      hidePass();
      document.removeEventListener("visibilitychange", onHidden);
      DURUM = null; ACCT = null; message = "";
    },
    title: "qBittorrent",
    eyebrow: "Hesap, indirme dizini ve servis",
    actions: () => [h("span", { class: "hm", id: "torrent-stamp" }, readAt ? "Son okuma " + hhmm(readAt) : "Okunuyor…"),
      h("button", { type: "button", class: "btn btn-quiet", onclick: () => { loadDurum(); k.reloadModules(); } }, svg("refresh"), "Yenile")],
    render() { hidePass(); message = ""; renderToolbar(); renderSettings(); loadDurum(); },
    poll() { loadDurum(); k.reloadModules(); },
    modules() { renderToolbar(); },
  };
  });
})();
