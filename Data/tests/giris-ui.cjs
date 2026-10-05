/* Konsol sign-in page (DD-194, DD-205) with intercepted APIs and the real CSP. Only the internet
   address signs in; the tailnet address sends the page straight back to Konsol. Uses the shared
   console preview on port 8766; never contacts a server. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs"), path = require("node:path"), os = require("node:os");
const shots = fs.mkdtempSync(path.join(os.tmpdir(), "konsol-giris-ui-"));
const base = process.env.KONSOL_URL || "http://127.0.0.1:8766";
const csp = fs.readFileSync(path.join(__dirname, "../templates/Caddyfile"), "utf8").match(/Content-Security-Policy "([^"]+)"/)[1];
let state = { durum: "giris", kanal: "internet" }, reply = null, konsolUnauthorized = false;
const posts = [], errors = [];
(async () => {
  const browser = await chromium.launch({ headless: true, ...(process.env.PLAYWRIGHT_CHROMIUM ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM } : {}) });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("console", (m) => { if (/Content Security Policy|Refused to|not a valid regular expression/.test(m.text())) errors.push(m.text()); });
    await page.route("**/*", async (route) => {
      const request = route.request(), url = new URL(request.url());
      if (request.resourceType() === "document" && url.pathname === "/" && !konsolUnauthorized) {
        // Successful sign-in leaves this page; Konsol itself is covered by the other suites.
        return route.fulfill({ status: 200, contentType: "text/html", headers: { "content-security-policy": csp }, body: "<!doctype html><title>Konsol</title>" });
      }
      if (url.pathname.startsWith("/api/")) {
        assert.equal(request.headers()["x-konsol"], "1", "every sign-in API call carries the CSRF header");
        if (url.pathname === "/api/konsol/oturum") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(state) });
        if (url.pathname.startsWith("/api/konsol/oturum/")) {
          posts.push({ path: url.pathname, body: request.postDataJSON() });
          const answer = reply || { status: 200, body: { durum: "acik" } };
          reply = null;
          return route.fulfill({ status: answer.status, contentType: "application/json", headers: answer.headers || {}, body: JSON.stringify(answer.body) });
        }
        // Konsol pages reached without a session get forward_auth's API answer.
        return route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ error: "Oturum gerekli; yeniden giriş yapın.", giris: true }) });
      }
      if (request.resourceType() !== "document") return route.continue();
      const response = await route.fetch();
      return route.fulfill({ response, headers: { ...response.headers(), "content-security-policy": csp } });
    });
    const note = page.locator("#login-note");
    // A fresh load each time: a fragment-only change would not rerun the page script.
    const open = async (url) => { await page.goto("about:blank"); await page.goto(base + url); };
    // Internet address: sign-in only. A wrong password is cleared; the attempt limit's message is shown as sent.
    await open("/giris.html#/dosyalar");
    await page.locator("#form-login").waitFor();
    assert.equal(await page.locator("#form-setup, #setup-code").count(), 0, "no first-account form: the account is made in Settings over Tailscale (DD-205)");
    assert.equal(await page.locator("#login-title").innerText(), "Giriş");
    assert.equal(await page.evaluate(() => document.activeElement.id), "login-user");
    assert.equal(await page.locator("#login-access").innerText(), "Sunucu yönetimi · internet (HTTPS)");
    assert.match(await page.locator(".login-foot").innerText(), /Tailscale adresinde parola sorulmaz/);
    await page.locator("#login-user").fill(" yonetici ");
    await page.locator("#login-pass").fill("wrong-password");
    reply = { status: 401, body: { error: "Kullanıcı adı veya parola hatalı." } };
    await page.locator("#login-submit").click();
    await page.getByText("Kullanıcı adı veya parola hatalı.", { exact: true }).waitFor();
    assert.equal(await page.locator("#login-pass").inputValue(), "");
    await page.locator("#login-pass").fill("wrong-password");
    reply = { status: 429, headers: { "Retry-After": "300" }, body: { error: "Çok fazla hatalı deneme; 300 saniye sonra yeniden deneyin." } };
    await page.locator("#login-submit").click();
    await page.getByText("Çok fazla hatalı deneme; 300 saniye sonra yeniden deneyin.", { exact: true }).waitFor();
    for (const colorScheme of ["light", "dark"]) {
      await page.emulateMedia({ colorScheme });
      for (const width of [1280, 768, 390, 320]) {
        await page.setViewportSize({ width, height: 900 });
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `login ${colorScheme}/${width}`);
        await page.screenshot({ path: path.join(shots, `login-${colorScheme}-${width}.png`), fullPage: true });
      }
    }
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.locator("#login-pass").fill("fixture-password");
    await page.locator("#login-submit").click();
    await page.waitForURL((url) => url.pathname === "/" && url.hash === "#/dosyalar");
    assert.deepEqual(posts, [
      { path: "/api/konsol/oturum/giris", body: { kullanici: "yonetici", parola: "wrong-password" } },
      { path: "/api/konsol/oturum/giris", body: { kullanici: "yonetici", parola: "wrong-password" } },
      { path: "/api/konsol/oturum/giris", body: { kullanici: "yonetici", parola: "fixture-password" } }]);
    // No account yet (the public site is closed then; only a stale page can see this): no form, a pointer to Settings.
    state = { durum: "kurulum", kanal: "internet" };
    await open("/giris.html");
    await note.filter({ hasText: "Konsol hesabı yok" }).waitFor();
    assert.match(await note.innerText(), /Ayarlar → Sistem → Konsol hesabı/);
    assert(await page.locator("#form-login").isHidden());
    // DD-205: the tailnet never signs in — a direct load of this page goes straight back to Konsol.
    state = { durum: "giris", kullanici: "yonetici", kanal: "tailscale" };
    await open("/giris.html#/ayarlar");
    await page.waitForURL((url) => url.pathname === "/" && url.hash === "#/ayarlar");
    // An already signed-in browser goes straight back too.
    state = { durum: "acik", kullanici: "yonetici", oturum_gun: 7, kanal: "internet" };
    await open("/giris.html#/moduller");
    await page.waitForURL((url) => url.pathname === "/" && url.hash === "#/moduller");
    // Real Konsol whose internet session ended: its first API answer sends the browser to sign in.
    state = { durum: "giris", kanal: "internet" }; konsolUnauthorized = true;
    await open("/#/ayarlar");
    await page.waitForURL((url) => url.pathname === "/giris.html" && url.hash === "#/ayarlar");
    await page.locator("#form-login").waitFor();
    assert.equal(posts.length, 3, "status reads and redirects never post");
    assert.deepEqual(await page.evaluate(() => [Object.keys(localStorage), Object.keys(sessionStorage)]), [[], []]);
    assert.deepEqual(errors, []);
    console.log("PASS: internet sign-in (wrong/limit/success, trimmed user name), return to the original page, no-account notice without a form, tailnet shortcut back to Konsol, signed-in shortcut, Konsol 401 redirect, production CSP, no browser storage, widths/both themes. Screenshots: " + shots);
  } finally { await browser.close(); }
})().catch((err) => { console.error(err); process.exit(1); });
