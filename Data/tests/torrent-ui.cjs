/* qBittorrent package page (DD-202) on the real console assets under the production CSP: the page
   files are served from magaza/torrent through Playwright routes, every API call is fixtured; no
   server is modified. Covers the account form, the download folder, the service bar and layout. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs"), os = require("node:os"), path = require("node:path");
const shots = fs.mkdtempSync(path.join(os.tmpdir(), "konsol-torrent-ui-"));
const base = process.env.KONSOL_URL || "http://127.0.0.1:8766";
const csp = fs.readFileSync(path.join(__dirname, "../templates/Caddyfile"), "utf8").match(/Content-Security-Policy "([^"]+)"/)[1];
const magaza = path.join(__dirname, "../magaza");
const meta = (id) => JSON.parse(fs.readFileSync(path.join(magaza, id, "konsol.json"), "utf8").replace(/__[A-Z_]+__/g, "x"));
const modules = [
  { id: "wireguard", installed: false, state: "yok", runtime: "konsol", live: "-", durdurulabilir: false, konsol: meta("wireguard") },
  { id: "torrent", installed: true, state: "calisiyor", runtime: "konteyner", live: "running", durdurulabilir: true, konsol: meta("torrent"),
    sayfa: ["sayfa.js", "sayfa.css"], urls: { tailscale: "http://torrent.ayc", internet: null } },
];
const durum = { installed: true, running: true, unit: "qbittorrent.service", container: "qbittorrent", profile: "/var/lib/qbittorrent",
  downloads: "/srv/downloads", save: "/srv/downloads/", save_inside: true, temp: "", temp_on: false, temp_inside: false,
  ui: "127.0.0.1:61006", peer_port: 0, username: "admin" };
const writes = [], errors = [];
let hold = false, release = null, failNext = "", durumReads = 0;
(async () => {
  const browser = await chromium.launch({ headless: true, ...(process.env.PLAYWRIGHT_CHROMIUM ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM } : {}) });
  try {
    const context = await browser.newContext({ viewport: { width: 1400, height: 1000 } });
    await context.route("**/*", async (route) => {
      const p = new URL(route.request().url()).pathname;
      if (p.startsWith("/uygulama/")) {
        const file = path.join(magaza, p.slice("/uygulama/".length));
        return route.fulfill({ status: 200, contentType: p.endsWith(".css") ? "text/css" : "application/javascript", body: fs.readFileSync(file, "utf8") });
      }
      if (route.request().resourceType() !== "document") return route.continue();
      const response = await route.fetch();
      await route.fulfill({ response, headers: { ...response.headers(), "content-security-policy": csp } });
    });
    const page = await context.newPage();
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("console", (m) => { if (/violates.*Content Security Policy|Refused to/.test(m.text())) errors.push(m.text()); });
    await page.route("**/api/**", async (route) => {
      const req = route.request(), url = new URL(req.url()), p = url.pathname;
      let result = {};
      if (p === "/api/konsol/moduller") result = { items: modules };
      else if (p === "/api/uygulama/torrent/durum") { durumReads++; result = durum; }
      else if (p === "/api/uygulama/torrent/hesap" || p === "/api/uygulama/torrent/dizin") {
        const body = req.postDataJSON();
        writes.push({ path: p, body });
        if (hold) await new Promise((resolve) => { release = resolve; });
        if (failNext) {
          const error = failNext; failNext = "";
          return route.fulfill({ status: 400, contentType: "application/json", body: JSON.stringify({ error }) });
        }
        if (p.endsWith("/hesap")) { if (body.username) durum.username = body.username; result = { ok: true, username: durum.username }; }
        else { durum.save = body.save.replace(/\/?$/, "/"); durum.save_inside = durum.save.startsWith("/srv/downloads/"); result = { ok: true, save: durum.save }; }
      }
      else if (/\/moduller\/torrent\/(durdur|baslat)$/.test(p)) {
        const m = modules[1];
        m.state = p.endsWith("durdur") ? "durduruldu" : "calisiyor"; m.live = m.state === "calisiyor" ? "running" : "inactive";
        durum.running = m.state === "calisiyor"; result = { ok: true };
      }
      else if (p === "/api/konsol/moduller/torrent/hesap") result = { user: durum.username, temp: false };
      else if (p === "/api/konsol/ayarlar/klasorler") result = { items: [{ path: "/srv/downloads", free: 10 * 1024 ** 3 }, { path: "/srv/media", free: 10 * 1024 ** 3 }] };
      else if (p === "/api/konsol/kaynaklar") result = { host: "test", version: "test", domain: "ayc", os: "Debian 13", kernel: "test", uptime: 120, cores: 2, cpu: [1],
        mem: { total: 1000, used: 200 }, disk: { total: 1000, free: 500 }, root: "/srv", net: { tailscale: "100.64.0.2", wan: "192.0.2.1" }, read_at: Date.now() / 1000, sampled_at: Date.now() / 1000 };
      else if (p === "/api/konsol/saglik") result = { status: "ok", read_at: 1, checks: [] };
      else if (p === "/api/konsol/oturum") result = { durum: "acik", kullanici: "fixture", oturum_gun: 7 };
      else if (p === "/api/state") result = { root: "/srv", downloads: "downloads", protected: [{ path: "downloads/incomplete", owner: "Deneme Uygulaması" }], trash: { count: 0, size: 0 }, disk: { total: 1000, free: 500 } };
      else if (p === "/api/list") result = { path: "", entries: [] };
      else if (p === "/api/konsol/paylasim") result = { enabled: true, running: true, max: 32, host: "http://100.64.0.2:61010", items: [] };
      else if (p === "/api/trash" || p === "/api/konsol/islemler" || p === "/api/archives") result = { items: [] };
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(result) });
    });
    const box = page.locator("#torrent-settings");
    const username = () => box.getByRole("textbox", { name: "Kullanıcı adı", exact: true });
    const password = () => box.getByLabel("Yeni parola", { exact: true });
    const repeat = () => box.getByLabel("Yeni parola (tekrar)", { exact: true });
    const save = () => box.getByRole("button", { name: "Hesabı kaydet", exact: true });
    const settled = async (count) => {
      while (writes.length < count) await page.waitForTimeout(10);
      await page.waitForFunction(() => { const el = document.querySelector("#torrent-settings input[name=username]"); return el && !el.disabled; });
    };
    await page.goto(base + "/#/torrent");
    await username().waitFor();
    assert.equal(await page.locator("#title").innerText(), "qBittorrent");
    assert.equal(await page.getByRole("tab").count(), 0, "No settings tabs on the application page");
    assert.equal(await page.locator("#torrent-open").getAttribute("href"), "http://torrent.ayc");
    // DD-211: the application links directly to the main-sidebar container manager.
    await page.waitForFunction(() => document.querySelector("#torrent-container")?.getAttribute("href") === "#/konteynerler/qbittorrent");
    // Found live: an absent bar item must not become the text "null".
    assert(!(await page.locator("#torrent-status").innerText()).includes("null"), "no null text in the service bar");
    assert.equal(await username().inputValue(), "admin");
    assert.equal(await box.locator("div.as-body > code").innerText(), "/srv/downloads/");
    // Validation stays in the browser: no request leaves for an invalid username or password.
    await username().fill("bad user");
    assert.equal(await username().evaluate((el) => el.checkValidity()), false);
    await save().click(); assert.equal(writes.length, 0);
    await username().fill("new-user");
    assert.equal(await password().evaluate((el) => el.minLength), 8);
    await password().fill("1234567"); await repeat().fill("1234567");
    await save().click(); assert.equal(writes.length, 0);
    await password().fill("sample-ui-only-password"); await repeat().fill("mismatched-password");
    await save().click(); assert.equal(writes.length, 0);
    await repeat().fill("sample-ui-only-password");
    hold = true;
    await save().click();
    await page.waitForFunction(() => document.querySelector("#torrent-settings .as-message")?.textContent.includes("hesabı kaydediliyor"));
    assert(await save().isDisabled());
    assert(await password().isDisabled());
    while (!release) await page.waitForTimeout(10);
    hold = false; release(); release = null;
    await page.waitForFunction(() => document.querySelector("#torrent-settings .as-message")?.textContent.includes("hesabı kaydedildi."));
    await settled(1);
    assert.equal(writes.length, 1, "One click = one direct request to the package API, no confirmation");
    assert.deepEqual(writes[0], { path: "/api/uygulama/torrent/hesap", body: { username: "new-user", password: "sample-ui-only-password" } });
    assert.equal(await username().inputValue(), "new-user");
    assert.equal(await password().inputValue(), "");
    assert(!(await page.locator("body").innerText()).includes("sample-ui-only-password"));
    assert.equal(await page.locator(".as-footer, .as-rollback, dialog[open]").count(), 0, "No draft footer, rollback bar or confirmation window");
    // Username-only keeps the password; password-only keeps the username; unchanged sends nothing.
    await username().fill("another-user"); await save().click(); await settled(2);
    assert.deepEqual(writes[1].body, { username: "another-user" });
    assert.equal(await username().inputValue(), "another-user");
    await password().fill("Pass8!xy"); await repeat().fill("Pass8!xy"); await save().click(); await settled(3);
    assert.deepEqual(writes[2].body, { password: "Pass8!xy" });
    await save().click();
    await page.getByText("Hesap bilgilerinde değişiklik yok.").waitFor();
    assert.equal(writes.length, 3, "Unchanged account does not restart the service");
    failNext = "Hesap sınama hatası; önceki ayar korundu.";
    await username().fill("failed-user");
    await password().fill("failed-test-password"); await repeat().fill("failed-test-password");
    await save().click();
    await page.waitForFunction(() => document.querySelector("#torrent-settings .as-message")?.textContent.includes("Hesap kaydı doğrulanamadı"));
    await settled(4);
    assert.equal(durum.username, "another-user");
    assert.equal(await username().inputValue(), "another-user", "The form shows the server's account after a failure");
    assert.equal(await password().inputValue(), "");
    assert.equal(await repeat().inputValue(), "");
    assert.equal(await page.locator(".as-rollback").count(), 0);
    // Download folder: the picker lists the base's folders; the choice goes straight to the package API.
    await box.getByRole("button", { name: "Klasör seç", exact: true }).click();
    await page.locator(".as-folder").filter({ hasText: "/srv/media" }).getByRole("button", { name: "Seç", exact: true }).click();
    await settled(5);
    assert.deepEqual(writes[4], { path: "/api/uygulama/torrent/dizin", body: { save: "/srv/media" } });
    await page.waitForFunction(() => document.querySelector("#torrent-settings .as-message")?.textContent.includes("İndirme dizini kaydedildi: /srv/media/"));
    assert.equal(await box.locator("div.as-body > code").innerText(), "/srv/media/");
    // DD-209: a folder outside downloads is bind-mounted into the container; the page says so, calmly.
    assert.equal(await box.locator(".as-note.warn").count(), 0);
    assert.equal(await box.getByText("Dizin indirme klasörünün dışında; konteynere ayrıca bağlanmıştır.", { exact: true }).count(), 1, "A folder outside downloads is named");
    assert.equal(await page.locator("dialog[open]").count(), 0);
    // Service bar: stop asks, start does not; the link follows the running state.
    await page.locator("#torrent-status").getByRole("button", { name: "Durdur", exact: true }).click();
    await page.locator("#cf-go").click();
    await page.locator("#torrent-status").getByRole("button", { name: "Başlat", exact: true }).waitFor();
    assert.equal(await page.locator("#torrent-open").count(), 0);
    await page.locator("#torrent-status").getByRole("button", { name: "Başlat", exact: true }).click();
    await page.locator("#torrent-status").getByRole("button", { name: "Durdur", exact: true }).waitFor();
    assert.equal(await page.locator("#torrent-open").getAttribute("href"), "http://torrent.ayc");
    assert.equal(await page.locator("#torrent-status a[href='#/moduller']").count(), 1);
    // Layout: equal controls, aligned edges, the path and its action on one row, five widths, both themes.
    for (const colorScheme of ["light", "dark"]) {
      await page.emulateMedia({ colorScheme });
      for (const width of [1400, 1024, 736, 390, 320]) {
        await page.setViewportSize({ width, height: 1000 });
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `no horizontal scroll at ${width}`);
        const boxes = await box.evaluate((root) => {
          const rect = (el) => { const r = el.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; };
          return { fields: [...root.querySelectorAll("input")].map(rect),
            headers: [...root.querySelectorAll(".card-head")].map(rect),
            buttons: [...root.querySelectorAll(".as-body button")].map(rect),
            path: rect(root.querySelector("div.as-body > code")) };
        });
        const [user, pass, again] = boxes.fields;
        const near = (a, b) => Math.abs(a - b) < 1;
        assert(near(user.height, pass.height) && near(pass.height, again.height), `equal controls at ${width}`);
        assert(user.height >= 44, "Readable input height");
        assert(near(user.x, boxes.headers[0].x) && near(user.x, boxes.buttons[0].x), "Heading/field/Save left edge");
        assert(near(boxes.path.x, boxes.headers[1].x), "Download path aligned with heading");
        if (width > 700) {
          assert(near(pass.y, again.y) && near(pass.width, again.width), `password row at ${width}`);
          assert(near(boxes.path.y + boxes.path.height / 2, boxes.buttons[1].y + boxes.buttons[1].height / 2), "Path and folder action share a row");
        } else {
          assert(near(user.x, again.x) && near(user.width, again.width) && again.y > pass.y + pass.height);
          assert(near(boxes.path.x, boxes.buttons[1].x), "Mobile folder action left edge");
        }
        await page.screenshot({ path: path.join(shots, `torrent-${colorScheme}-${width}.png`), fullPage: true });
      }
    }
    const originalSave = durum.save;
    durum.save = "/srv/downloads/" + "long-folder-name-".repeat(24);
    await page.getByRole("button", { name: "Yenile", exact: true }).click();
    await page.getByText(durum.save, { exact: true }).waitFor();
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), "Long folder path wraps on mobile");
    durum.save = originalSave;
    await page.getByRole("button", { name: "Yenile", exact: true }).click();
    await page.getByText(originalSave, { exact: true }).waitFor();
    // A refresh or the shell's 10 s poll re-reads the status while the operator types: the typed
    // password, the half-typed repeat, the focus and the caret survive the re-render (v2-185).
    await page.setViewportSize({ width: 1400, height: 1000 });
    await password().fill("draft-password-1"); await repeat().click(); await repeat().pressSequentially("draft-pa");
    const rebuilt = async (action) => {   // wait until the status read has rebuilt the form
      const before = await box.locator("form").elementHandle();
      await action();
      await page.waitForFunction((old) => { const f = document.querySelector("#torrent-settings form"); return f && f !== old; }, before);
    };
    await rebuilt(() => page.getByRole("button", { name: "Yenile", exact: true }).click());
    assert.equal(await password().inputValue(), "draft-password-1", "Typed password survives a refresh");
    assert.equal(await repeat().inputValue(), "draft-pa", "Half-typed repeat survives a refresh");
    await page.clock.install();
    await repeat().click(); await repeat().pressSequentially("ss");
    const reads = durumReads;
    await rebuilt(() => page.clock.runFor(10500));
    assert.equal(durumReads, reads + 1, "The poll read the status once");
    assert.deepEqual(await page.evaluate(() => { const a = document.activeElement; return [a && a.name, a && a.selectionStart, a && a.selectionEnd]; }),
      ["repeat", 10, 10], "Focus and caret stay in the repeat field across the poll");
    assert.equal(await repeat().inputValue(), "draft-pass");
    assert.equal(await password().inputValue(), "draft-password-1");
    assert.equal(await username().inputValue(), "another-user", "An untouched username still follows the server");
    assert.deepEqual(errors, []);
    assert.deepEqual(await page.evaluate(() => Object.keys(localStorage)), []);
    console.log("PASS: qBittorrent package page — direct account save (validation, hold, failure, username-only, password-only, unchanged), draft kept across refresh/poll, folder picker to the package API, service bar with link, five widths/dark; screenshots in " + shots);
  } finally { await browser.close(); }
})().catch((err) => { console.error(err); process.exit(1); });
