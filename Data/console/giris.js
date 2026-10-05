/* Konsol internet girişi (DD-194, DD-205). Tailscale adresinde oturum yoktur: arka uç bu sayfayı
   Konsol'a yönlendirir; burada yalnız kullanıcı adı ve parola sorulur. Parola yalnız istek
   gövdesinde gider; tarayıcı deposuna yazılmaz. Girişten sonra gelinen Konsol sayfasına dönülür. */
"use strict";
(() => {
  const $ = (id) => document.getElementById(id);
  const back = () => location.replace("/" + (location.hash.startsWith("#/") ? location.hash : ""));
  async function call(path, body) {
    const init = { method: body ? "POST" : "GET", headers: { "X-Konsol": "1" }, credentials: "same-origin", cache: "no-store" };
    if (body) { init.headers["Content-Type"] = "application/json"; init.body = JSON.stringify(body); }
    const res = await fetch(path, init);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `Sunucu yanıtı: HTTP ${res.status}`);
    return data;
  }
  function show(state, note) {
    $("form-login").hidden = state !== "giris";
    $("login-note").textContent = note;
    if (state === "giris") $("login-user").focus();
  }
  const form = $("form-login"), button = $("login-submit"), error = $("login-error");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (button.disabled || !form.reportValidity()) return;
    button.disabled = true; error.hidden = true;
    try {
      await call("/api/konsol/oturum/giris", { kullanici: $("login-user").value.trim(), parola: $("login-pass").value });
      back();
    } catch (err) {
      error.textContent = err.message; error.hidden = false;
      button.disabled = false;
      $("login-pass").value = "";
    }
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) $("login-pass").value = "";
  });
  call("/api/konsol/oturum").then((state) => {
    // DD-205: the tailnet address never asks for a sign-in (the backend already sends this page back
    // to Konsol); a browser with an open session goes back too. Only the internet address signs in.
    if (state.durum === "acik" || (state.kanal && state.kanal !== "internet")) { back(); return; }
    $("login-access").textContent = "Sunucu yönetimi · internet (HTTPS)";
    if (state.durum === "kurulum") {
      show("", "Konsol hesabı yok. Tailscale adresinden Ayarlar → Sistem → Konsol hesabı bölümünde oluşturun; internet adresi o hesapla açılır.");
      return;
    }
    show("giris", "Kullanıcı adınız ve parolanızla giriş yapın.");
  }).catch((err) => show("", "Oturum durumu okunamadı: " + err.message + " Sayfayı yenileyin."));
})();
