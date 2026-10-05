/* Klasör başına WebDAV yönetimi. Parola tarayıcı deposuna yazılmaz. */
window.createSharesPage = function ({ h, svg, post, toast, fail, copyButton, getShares, setShares, root, showDialog, closeDialog, ask }) {
  let busy = false;
  const scopes = ["tailscale", "wan"];
  const durations = [["1", "1 gün"], ["7", "7 gün"], ["30", "30 gün"], ["0", "Süresiz"]];
  const permissions = [["ro", "Salt okunur"], ["rw", "Okuma ve yazma"]];
  const wanScheme = () => getShares()?.wan?.scheme ?? (getShares()?.wan?.mode === "off" ? "" : getShares()?.wan?.mode || "http");
  // A closed WAN (scheme "") is neither HTTP nor HTTPS; say only which network it is.
  const label = (scope) => scope === "tailscale" ? "Tailscale" : { http: "HTTP (WAN)", https: "HTTPS" }[wanScheme()] || "WAN";
  const expiry = (c) => c.expires == null ? "Süresiz" : new Date(c.expires * 1000).toLocaleString("tr-TR", { dateStyle: "medium", timeStyle: "short" });
  const stateText = (s) => {
    const connections = scopes.map(scope => s.connections?.[scope]).filter(Boolean);
    if (!connections.length) return "Bağlantı bilgisi yok";
    if (connections.every(c => !c.enabled)) return "Duraklatıldı";
    if (!s.available) return "Klasör bulunamadı";
    if (connections.some(c => c.active)) return "Açık";
    return connections.some(c => c.enabled && c.expired) ? "Süresi doldu" : "Erişim kullanılamıyor";
  };
  const button = (text, icon, fn) => h("button", { type: "button", class: "btn btn-sm btn-quiet", disabled: busy, onclick: fn }, svg(icon), text);
  function warning() {
    return h("details", { class: "dav-boundary" }, h("summary", null, svg("shield"), "Paylaşmadan önce erişim sınırını kontrol edin"),
      h("p", null, "Alıcıya yalnız WebDAV portunu açın; Konsol ve SSH yalnız yöneticide kalmalı. Konsol hesabıyla giren kişi tüm dosyaları yönetebilir; Konsol parolasını paylaşmayın. Tailscale ACL/grants kuralları burada değiştirilmez."),
      h("p", null, "Tailscale bağlantısı şifreli tünelde taşınır. " + (wanScheme() === "http" ? "WAN üzerinden HTTP, parola ve verileri şifrelemeden gönderir. " : "") + "Dosya kilidi isteyen istemciler bu adresle uyumlu olmayabilir; Infuse/Finder uyumu istemcide ayrıca sınanmalıdır."));
  }
  function update(action, body) {
    if (busy) return Promise.reject(new Error("Paylaşım kaydediliyor; lütfen bekleyin."));
    busy = true; setShares(getShares());
    return post("/api/konsol/paylasim/" + action, body).then((data) => { setShares(data); return data; })
      .finally(() => { busy = false; setShares(getShares()); });
  }
  function options(s, scope) {
    const c = s.connections[scope], name = s.name + " " + label(scope);
    const permission = h("select", { "aria-label": name + " erişim izni", disabled: busy, onchange: (event) => {
      const value = event.target.value;
      event.target.value = c.permission;
      if (value === c.permission) return;
      const patch = { permission: value };
      if (value === "rw") patch.ack_write = true;
      const save = () => update("kaydet", { id: s.id, connections: { [scope]: patch } })
        .then(() => toast(label(scope) + " erişim izni kaydedildi.")).catch(fail);
      if (value === "rw") ask({ title: "Yazma izni açılsın mı?", sub: name, go: "Yazma izni ver",
        items: [["info", "Yükleme, üzerine yazma ve kalıcı silme izni verir. WebDAV ile silinenler Çöp'e gitmez."]], onOk: save });
      else save();
    } }, ...permissions.map(([value, text]) => h("option", { value, selected: value === c.permission }, text)));
    const days = h("select", { "aria-label": name + " paylaşım süresi", title: expiry(c), disabled: busy, onchange: (event) => {
      const value = event.target.value === "keep" ? null : Number(event.target.value);
      event.target.value = c.expires == null ? "0" : "keep";
      if (value === null || (value === 0 && c.expires == null)) return;
      update("kaydet", { id: s.id, connections: { [scope]: { days: value } } })
        .then(() => toast(label(scope) + " süresi kaydedildi.")).catch(fail);
    } }, c.expires != null ? h("option", { value: "keep", selected: true }, "Bitiş " + expiry(c)) : null,
      ...durations.map(([value, text]) => h("option", { value, selected: c.expires == null && value === "0" }, text)));
    return h("div", { class: "dav-controls" },
      h("label", { class: "dav-cell" }, h("span", null, "Erişim"), permission),
      h("label", { class: "dav-cell" }, h("span", null, "Süre"), days));
  }
  function toggle(s, scope) {
    const c = s.connections[scope], enabled = !c.enabled;
    const body = { id: s.id, connections: { [scope]: { enabled } } };
    const save = () => update("kaydet", body).then(() => toast(enabled
      ? c.expired ? "Seçim kaydedildi. Bağlantının süresi dolmuş; açmak için yeni bir süre seçin." : label(scope) + " seçimi açıldı."
      : label(scope) + " bağlantısı kapatıldı; hesap ve dosyalar korundu.")).catch(fail);
    if (scope === "wan" && enabled && wanScheme() === "http") {
      ask({ title: "HTTP üzerinden WAN erişimi açılsın mı?", sub: s.name, go: "Onayla ve aç",
        items: [["info", "WAN üzerinden HTTP, parola ve verileri şifrelemeden gönderir."]],
        onOk: () => { body.ack_wan_http = true; return save(); } });
    } else save();
  }
  function connection(s, scope) {
    const c = s.connections?.[scope], name = label(scope);
    if (!c) return h("section", { class: "dav-connection", "data-network": scope }, h("p", { class: "dav-warning" }, name + " bağlantı bilgisi okunamadı."));
    const status = c.active ? "Erişim açık" : c.expired ? "Süresi doldu" : !c.enabled ? "Kapalı" : "Erişim kullanılamıyor";
    let endpoint;
    try { if (c.url) endpoint = new URL(c.url); } catch (_) { /* Bozuk adresi bağlantı bilgisi olarak göstermeyin. */ }
    if (endpoint && !["http:", "https:"].includes(endpoint.protocol)) endpoint = null;
    return h("section", { class: "dav-connection", "data-network": scope, "aria-label": s.name + " " + name },
      h("div", { class: "dav-connection-head" }, h("h3", null, svg(scope === "tailscale" ? "shield" : wanScheme() === "https" ? "lock" : "globe"), name),
        h("button", { type: "button", class: "sw", role: "switch", "aria-checked": c.enabled, disabled: busy || (!c.enabled && !c.available),
          "aria-label": s.name + " " + name + " bağlantısı", title: c.enabled ? "Bağlantıyı kapat" : "Bağlantıyı aç", onclick: () => toggle(s, scope) })),
      h("div", { class: "dav-connection-body" },
        h("p", { class: "dav-connection-state" + (c.active ? " active" : "") }, status),
        c.reason ? h("p", { class: "hint-s dav-reason" }, c.reason) : null,
        options(s, scope),
        h("p", { class: "hint-s dav-expiry" }, c.expires == null ? "Süresiz" : [c.expired ? "Süre doldu · " : "Bitiş · ", h("time", { datetime: new Date(c.expires * 1000).toISOString() }, expiry(c))]),
        endpoint ? h("div", { class: "dav-address" }, h("code", null, c.url), copyButton(c.url, s.name + " " + name + " adresi")) : null,
        endpoint ? h("div", { class: "dav-infuse" }, h("small", null, "Infuse · " + (endpoint.protocol === "https:" ? "WebDAV (HTTPS)" : "WebDAV (HTTP)")),
          h("dl", null, ...[["Adres", endpoint.hostname], ["Port", endpoint.port || (endpoint.protocol === "https:" ? "443" : "80")], ["Yol", endpoint.pathname]].map(([key, value]) =>
            h("div", null, h("dt", null, key), h("dd", null, value))))) : h("p", { class: "hint-s" }, "Bağlantı adresi kullanılamıyor.")));
  }
  function remove(s) {
    closeDialog();
    ask({ title: "“" + s.name + "” paylaşımı kaldırılsın mı?", sub: root() + "/" + s.path, danger: true, go: "Paylaşımı kaldır",
      items: [["key", "Bu klasörün iki bağlantısı ve ortak hesabı iptal edilir."], ["folder", "Klasör ve içindeki dosyalar silinmez."],
        ["info", "WebDAV servisi yenilenir; diğer paylaşımların sürmekte olan aktarımları da kesilir, yeniden bağlanabilirler."]],
      onOk: () => update("kaldir", { id: s.id }).then(() => toast("Paylaşım kaldırıldı; dosyalar korundu.")).catch(fail) });
  }
  function info(s) {
    return h("article", { class: "dav-share-row", "data-share-id": s.id },
      h("header", { class: "dav-share-top" },
        h("div", { class: "dav-share-name" }, h("span", { class: "ticon t-dir" }, svg("folder")),
          h("div", null, h("strong", null, s.name), h("small", null, root() + "/" + s.path))),
        h("div", { class: "dav-actions" }, h("span", { class: "shchip dav-share-state" }, stateText(s)),
          button("Yönet", "sliders", () => edit(s)), button("Kaldır", "trash", () => remove(s))),
        h("div", { class: "dav-account" }, h("span", null, "Kullanıcı · ", s.username, copyButton(s.username, s.name + " kullanıcı adı")),
          h("small", null, "İki bağlantı aynı hesabı kullanır. Parola Yönet’ten yenilenir."))),
      h("div", { class: "dav-card-grid" }, ...scopes.map(scope => connection(s, scope))));
  }
  function form(path, existing, onDone) {
    const username = h("input", { id: "dav-user", autocomplete: "off", required: true, minlength: 3, maxlength: 32,
      pattern: "[A-Za-z0-9][A-Za-z0-9._\\-]{2,31}", value: existing ? existing.username : "", placeholder: "ör. aile-medya" });
    const password = h("input", { type: "password", id: "dav-password", autocomplete: "new-password", required: !existing,
      minlength: 8, maxlength: 256, placeholder: existing ? "Boş bırak: mevcut parola korunsun" : "En az 8 karakter" });
    const target = h("input", { id: "dav-path", required: true, value: path, autocomplete: "off", spellcheck: "false" });
    const draft = {};
    const cards = !existing ? h("div", { class: "dav-card-grid" }, ...scopes.map(scope => {
      const name = label(scope), available = scope === "tailscale" ? getShares()?.tail_enabled !== false : getShares()?.wan?.available === true;
      // Start Tailscale on only while Settings → Caddy publishes it; the server refuses otherwise.
      const enabled = h("button", { type: "button", class: "sw", role: "switch", id: "dav-" + scope, "aria-label": name + " bağlantısı", "aria-checked": scope === "tailscale" && available });
      const permission = h("select", { id: "dav-" + scope + "-permission", "aria-label": name + " erişim izni" },
        ...permissions.map(([value, text]) => h("option", { value }, text)));
      const days = h("select", { id: "dav-" + scope + "-days", "aria-label": name + " paylaşım süresi" },
        ...durations.map(([value, text]) => h("option", { value, selected: value === "7" }, text)));
      const ack = h("input", { type: "checkbox", id: "dav-" + scope + "-ack" });
      const acknowledgement = h("label", { class: "dav-warning dav-check", hidden: true }, ack,
        h("span", null, name + ": yazma; yükleme, üzerine yazma, taşıma ve kalıcı silmeyi kapsar. WebDAV ile silinenler Çöp'e gitmez. Onaylıyorum."));
      const ackWan = scope === "wan" ? h("input", { type: "checkbox", id: "dav-ack-wan" }) : null;
      const wanAcknowledgement = ackWan ? h("label", { class: "dav-warning dav-check", hidden: true }, ackWan,
        h("span", null, "WAN üzerinden HTTP, parola ve verileri şifrelemeden gönderir. Onaylıyorum.")) : null;
      const sync = () => {
        const on = enabled.getAttribute("aria-checked") === "true";
        enabled.disabled = !on && !available;
        ack.required = permission.value === "rw"; acknowledgement.hidden = !ack.required;
        if (!ack.required) ack.checked = false;
        if (ackWan) {
          ackWan.required = on && wanScheme() === "http"; wanAcknowledgement.hidden = !ackWan.required;
          if (!ackWan.required) ackWan.checked = false;
        }
      };
      enabled.addEventListener("click", () => { enabled.setAttribute("aria-checked", enabled.getAttribute("aria-checked") !== "true"); sync(); });
      permission.addEventListener("change", sync); sync();
      draft[scope] = { enabled, permission, days, ack, ackWan };
      return h("section", { class: "dav-connection", "data-network": scope },
        h("div", { class: "dav-connection-head" }, h("h3", null, name), enabled),
        h("div", { class: "dav-connection-body" },
          !available ? h("p", { class: "hint-s" }, scope === "wan" ? getShares()?.wan?.reason || "WAN kullanılamıyor." : "Tailscale yayını kapalı.") : null,
          h("label", { class: "dav-cell" }, "Erişim", permission), h("label", { class: "dav-cell" }, "Süre", days), acknowledgement, wanAcknowledgement));
    })) : null;
    const error = h("p", { class: "err-s", role: "alert", hidden: true });
    const save = h("button", { type: "submit", class: "btn btn-primary" }, svg("share"), existing ? "Güncelle" : "Paylaşımı oluştur");
    const frm = h("form", { class: "dav-form" },
      h("label", { for: "dav-path" }, "Klasör · " + root() + "/", target),
      h("label", { for: "dav-user" }, "Kullanıcı adı", username),
      h("label", { for: "dav-password" }, existing ? "Yeni parola (isteğe bağlı)" : "Parola", password),
      h("div", { class: "dav-actions" }, button("Parola üret", "key", () => {
        const values = new Uint8Array(20); crypto.getRandomValues(values);
        password.value = Array.from(values, (v) => v.toString(16).padStart(2, "0")).join(""); password.type = "text";
      }), button("Göster / gizle", "eye", () => { password.type = password.type === "password" ? "text" : "password"; })),
      h("small", { class: "hint-s" }, "Parolayı kaydetmeden önce not edin; daha sonra gösterilmez. Tarayıcı deposuna kaydedilmez."), cards,
      !existing ? h("small", { class: "hint-s" }, "İki bağlantı da kapalıysa hesap duraklatılmış olarak saklanır. WAN sınırları: 60 saniyede 5 hatalı giriş → 5 dakika engel; IP başına 4, toplam 8 eşzamanlı istek.") : null,
      h("p", { class: "hint-s" }, "Kaydetme WebDAV servisini yeniler ve devam eden aktarımları keser. Kapalı veya süresi dolmuş bağlantılar kendiliğinden açılmaz."),
      error, h("div", { class: "dav-actions" }, save, button("Vazgeç", "close", onDone)));
    frm.addEventListener("submit", (event) => {
      event.preventDefault();
      if (busy || save.disabled || !frm.reportValidity()) return;
      const data = existing ? { id: existing.id } : { path: target.value.trim(), username: username.value.trim(), password: password.value, connections: {} };
      if (existing) {
        if (target.value.trim() !== existing.path) data.path = target.value.trim();
        if (username.value.trim() !== existing.username) data.username = username.value.trim();
        if (password.value) data.password = password.value;
        if (Object.keys(data).length === 1) { onDone(); return; }
      } else scopes.forEach(scope => {
        const d = draft[scope];
        data.connections[scope] = { enabled: d.enabled.getAttribute("aria-checked") === "true", permission: d.permission.value, days: Number(d.days.value) };
        if (d.permission.value === "rw") data.connections[scope].ack_write = d.ack.checked;
        if (d.ackWan?.required) data.ack_wan_http = d.ackWan.checked;
      });
      const controls = [...frm.querySelectorAll("input, select, button")].map(el => [el, el.disabled]);
      controls.forEach(([el]) => { el.disabled = true; }); error.hidden = true;
      update("kaydet", data).then(() => { password.value = ""; onDone(); toast(existing ? "Paylaşım güncellendi." : "Klasör paylaşımı hazır."); })
        .catch((err) => { error.textContent = err.message; error.hidden = false; })
        .finally(() => { if ("password" in data) data.password = ""; controls.forEach(([el, disabled]) => { el.disabled = disabled; }); });
    });
    return frm;
  }
  function edit(s) { showDialog(s.name + " · paylaşımı düzenle", form(s.path, s, closeDialog)); }
  function create(item, path) {
    if (item.type !== "dir") { toast("WebDAV için bir klasör seçin."); return; }
    const found = (getShares()?.items || []).find((s) => s.path === path);
    if (found) { edit(found); return; }
    showDialog(item.name + " · WebDAV ile paylaş", form(path, null, closeDialog));
  }
  function list(body) {
    const data = getShares();
    body.append(warning());
    if (!data) { body.append(h("p", { class: "hint-s" }, "Paylaşımlar okunuyor…")); return; }
    if (!data.running) body.append(h("p", { class: "dav-warning" }, "WebDAV hizmeti çalışmıyor. Hesaplar korunuyor; sunucuda master-paylasim hizmetini kontrol edin."));
    body.append(h("div", { class: "dav-list-head" }, h("h2", null, "WebDAV paylaşımları"),
      h("p", { class: "hint-s" }, data.items.length + "/" + data.max + " klasör · Seçimler anında kaydedilir. Yeni süre seçilirse bugünden başlar; anahtar süreyi yenilemez. Değişiklikler WebDAV aktarımlarını kesebilir.")));
    if (!data.items.length) {
      body.append(h("div", { class: "dav-empty" }, svg("share"), h("h3", null, "Henüz paylaşım yok"),
        h("p", null, "Dosyalar sekmesinde bir klasörün Ayrıntılar düğmesini seçin, ardından WebDAV ile paylaşın.")));
      return;
    }
    body.append(h("div", { class: "dav-shares", "aria-busy": busy }, ...data.items.map(info)));
  }
  return { list, create, edit, info, warning, stateText,
    interacting: () => busy || !!document.querySelector("#sh[open] .dav-form, #cf[open]") || !!document.activeElement?.closest(".dav-connection select") };
};
