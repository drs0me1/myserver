/* DD-233: Ana Menü's update button beside the clock, on the real console assets under the production
   CSP: up to date / check now / new version / confirmation and its payload / running stage / failure /
   finished run reloading the page / internet channel locked / phone width. Every API call is fixtured. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs"), os = require("node:os"), path = require("node:path");
const shots = fs.mkdtempSync(path.join(os.tmpdir(), "konsol-update-ui-"));
const base = process.env.KONSOL_URL || "http://127.0.0.1:8766";
const csp = fs.readFileSync(path.join(__dirname, "../templates/Caddyfile"), "utf8").match(/Content-Security-Policy "([^"]+)"/)[1];
const OLD = "2026.08.06-v2-211", NEW = "2026.08.06-v2-212", SHA = "0123456789abcdef0123456789abcdef01234567";
const errors = [], starts = [], checks = [];
let upd = { kurulu: OLD, son: OLD, commit: SHA, yeni: false, denetlendi: 1, hata: "", baslatilabilir: true,
  is: { durum: "yok", hedef: "", mesaj: "", bitis: null, asama: "" } };
let afterCheck = null, startFails = "", documents = 0;
(async () => {
  const browser = await chromium.launch({ headless: true, ...(process.env.PLAYWRIGHT_CHROMIUM ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM } : {}) });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    await context.route("**/*", async (route) => {
      const req = route.request(), url = new URL(req.url()), p = url.pathname;
      if (req.resourceType() === "document") {
        documents++;
        const response = await route.fetch();
        return route.fulfill({ response, headers: { ...response.headers(), "content-security-policy": csp } });
      }
      if (!p.startsWith("/api/")) return route.continue();
      let result;
      if (p === "/api/konsol/guncelleme" && req.method() === "POST") {
        starts.push(req.postDataJSON());
        if (startFails) {
          const error = startFails; startFails = "";
          return route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ error }) });
        }
        upd.is = { durum: "calisiyor", hedef: NEW, mesaj: "", bitis: null, asama: "İndiriliyor" };
        result = { surum: NEW };
      } else if (p === "/api/konsol/guncelleme") {
        checks.push(url.search);
        if (url.searchParams.get("yenile") === "1" && afterCheck) { upd = afterCheck(upd); afterCheck = null; }
        result = upd;
      } else if (p === "/api/konsol/moduller") result = { items: [] };
      else if (p === "/api/konsol/kaynaklar") result = { host: "nrm", version: OLD, domain: "ev", os: "Debian 13", kernel: "test", uptime: 120, cores: 2, cpu: [1],
        mem: { total: 1000, used: 200 }, disk: { total: 1000, free: 500 }, root: "/srv", net: { tailscale: "100.64.0.2", wan: "192.0.2.1" }, read_at: Date.now() / 1000, sampled_at: Date.now() / 1000 };
      else if (p === "/api/konsol/oturum") result = { durum: "acik", kullanici: "fixture", kanal: "tailscale" };
      else if (p === "/api/konsol/ag") { const now = Math.floor(Date.now() / 1000); result = { read_at: now, iface: "eth0", window: 120, sampled_at: now, rx: 1, tx: 1, points: [], apps: [] }; }
      else if (p === "/api/konsol/duzen") result = { duzen: null };
      else if (p === "/api/state") result = { root: "/srv", downloads: "downloads", protected: [], trash: { count: 0, size: 0 }, disk: { total: 1000, free: 500 } };
      else if (p === "/api/konsol/islemler") result = { items: [] };
      else { errors.push("Unexpected endpoint: " + p); return route.fulfill({ status: 404, body: "unexpected" }); }
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(result) });
    });
    const page = await context.newPage();
    await page.clock.install();
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("console", (m) => { if (/Content Security Policy|Refused to/.test(m.text())) errors.push(m.text()); });
    const button = page.locator("#title #home-update .upd");
    const tick = async (ms = 5000) => { await page.clock.fastForward(ms); await page.waitForTimeout(60); };

    await page.goto(base + "/");
    await button.waitFor();
    assert.equal(await button.innerText(), "Güncel");
    // The button sits on the clock's line, after the date.
    const line = await page.evaluate(() => ["home-clock", "home-date", "home-update"].map((id) => document.getElementById(id).getBoundingClientRect()));
    assert(line[2].left > line[1].right && Math.abs((line[2].top + line[2].bottom) / 2 - (line[0].top + line[0].bottom) / 2) < 14, "button beside the clock and date");

    // "Güncel" asks GitHub again; the newer version turns it into the update button.
    afterCheck = (u) => ({ ...u, son: NEW, yeni: true });
    await button.click();
    await page.locator("#toast").getByText("Yeni sürüm var: v2-212", { exact: true }).waitFor();
    assert(checks.includes("?yenile=1"));
    assert.equal(await button.innerText(), "Güncelle\nv2-212");
    assert(await button.evaluate((b) => b.classList.contains("new")));
    await page.screenshot({ path: path.join(shots, "new-1440.png") });

    // Cancel sends nothing; the confirmation names both versions and the pinned commit.
    await button.click();
    assert.equal(await page.locator("#cf-title").textContent(), "Sunucu v2-212 sürümüne güncellensin mi?");
    assert.equal(await page.locator("#cf-sub").textContent(), `Kurulu: ${OLD} → ${NEW}`);
    assert.match(await page.locator("#cf-list").innerText(), /commit 0123456/);
    await page.screenshot({ path: path.join(shots, "confirm-1440.png") });
    await page.locator("#cf-cancel").click();
    assert.equal(starts.length, 0);

    // A refused start shows the reason and keeps the offer.
    const refusal = "Bir uygulama işlemi sürüyor; bitince yeniden deneyin.";
    startFails = refusal;
    await button.click(); await page.locator("#cf-go").click();
    await page.locator("#toast").getByText(refusal, { exact: true }).waitFor();
    assert.equal(await button.innerText(), "Güncelle\nv2-212");

    // Start: exactly the shown version and commit; the stage follows the unit every tick.
    await button.click(); await page.locator("#cf-go").click();
    await page.locator("#toast").getByText("Güncelleme başladı; bu sayfa açık kalabilir.", { exact: true }).waitFor();
    assert.deepEqual(starts.at(-1), { surum: NEW, commit: SHA });
    assert(await button.isDisabled());
    upd.is.asama = "Aşama 3/7 — servisler";
    await tick();
    assert.equal(await button.innerText(), "Güncelleniyor\nAşama 3/7");
    assert.equal(await button.getAttribute("title"), "Aşama 3/7 — servisler");
    await page.screenshot({ path: path.join(shots, "running-1440.png") });

    // A restarting Konsol (API down) keeps the running state instead of an error.
    const failing = (route) => route.fulfill({ status: 502, contentType: "application/json", body: '{"error":"bad gateway"}' });
    await page.route("**/api/konsol/guncelleme", failing);
    await tick();
    assert.equal(await button.innerText(), "Güncelleniyor\nAşama 3/7");
    await page.unroute("**/api/konsol/guncelleme", failing);

    // A failed run says why and offers the update again, with the reason in the confirmation.
    upd.is = { durum: "hata", hedef: NEW, mesaj: "Tailscale oturumu açık değil", bitis: 2, asama: "" };
    await tick();
    await page.locator("#toast").getByText("Güncelleme başarısız: Tailscale oturumu açık değil", { exact: true }).waitFor();
    assert.equal(await button.innerText(), "Güncelle\nv2-212");
    await button.click();
    assert.match(await page.locator("#cf-list").innerText(), /Son deneme başarısız: Tailscale oturumu açık değil/);
    await page.locator("#cf-go").click();
    assert.equal(starts.length, 3);

    // A finished run reloads the page once so the new Konsol files load.
    const before = documents;
    upd = { ...upd, kurulu: NEW, yeni: false, is: { durum: "tamam", hedef: NEW, mesaj: "", bitis: 3, asama: "" } };
    await tick();
    await page.locator("#toast").getByText("Güncelleme tamamlandı: v2-212. Sayfa yenileniyor…", { exact: true }).waitFor();
    await tick(3000);
    for (let n = 0; n < 50 && documents === before; n++) await page.waitForTimeout(50);
    assert.equal(documents, before + 1, "page reloaded");
    await button.waitFor();
    assert.equal(await button.innerText(), "Güncel");

    // Unreachable GitHub: a quiet "Denetlenemedi" with the reason as its title.
    upd = { ...upd, hata: "GitHub'a ulaşılamadı ya da sürüm okunamadı; daha sonra yeniden denenir." };
    await tick(61000);
    assert.equal(await button.innerText(), "Denetlenemedi");
    assert.equal(await button.getAttribute("title"), upd.hata);

    // The internet channel sees the offer but cannot start it.
    upd = { ...upd, hata: "", son: "2026.08.06-v2-213", yeni: true, baslatilabilir: false };
    await tick(61000);
    assert(await button.isDisabled());
    assert.equal(await button.getAttribute("title"), "Güncelleme yalnız Tailscale adresinden başlatılır");

    // Phone and dark: the line wraps without page overflow; the button stays whole.
    upd.baslatilabilir = true;
    for (const [width, theme] of [[390, "dark"], [320, "light"]]) {
      await page.emulateMedia({ colorScheme: theme });
      await page.setViewportSize({ width, height: 800 });
      await tick(61000);
      const g = await button.evaluate((b) => { const r = b.getBoundingClientRect(); return { left: r.left, right: r.right, fits: b.scrollWidth <= b.clientWidth + 1 }; });
      assert(g.left >= 0 && g.right <= width && g.fits, `button fits ${width}`);
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `no overflow ${width}`);
      await page.screenshot({ path: path.join(shots, `phone-${theme}-${width}.png`) });
    }
    assert.deepEqual(errors, []);
    console.log("PASS: update button beside the clock — up to date, check now, new version, confirmation/cancel/refusal, pinned payload, running stage across restarts, failure and retry, reload after success, unreachable GitHub, internet locked, phone/dark. Screenshots: " + shots);
  } finally { await browser.close(); }
})().catch((e) => { console.error(e); process.exit(1); });
