/* App Store install form, direct app launch and the overview settings action (DD-210) on the real
   console assets under the production CSP. Package pages come from magaza/ through Playwright routes;
   every API call is fixtured and no server is modified. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs"), os = require("node:os"), path = require("node:path");
const shots = fs.mkdtempSync(path.join(os.tmpdir(), "konsol-app-install-"));
const base = process.env.KONSOL_URL || "http://127.0.0.1:8766";
const csp = fs.readFileSync(path.join(__dirname, "../templates/Caddyfile"), "utf8").match(/Content-Security-Policy "([^"]+)"/)[1];
const magaza = path.join(__dirname, "../magaza");
const meta = (id) => JSON.parse(fs.readFileSync(path.join(magaza, id, "konsol.json"), "utf8")
  .replace(/__DOWNLOADS_PATH__/g, "/srv/downloads").replace(/__[A-Z_]+__/g, "x"));
const modules = [
  { id: "wireguard", installed: false, state: "", runtime: "konsol", live: "-", busy: false, progress: null, durdurulabilir: true, konsol: meta("wireguard") },
  { id: "torrent", installed: false, state: "", runtime: "konteyner", live: "-", busy: false, progress: null, durdurulabilir: true, konsol: meta("torrent") },
];
const durum = { installed: true, running: true, unit: "qbittorrent.service", container: "qbittorrent", profile: "/var/lib/qbittorrent",
  downloads: "/srv/downloads", save: "/srv/downloads/", save_inside: true, temp: "", temp_on: false, temp_inside: false,
  ui: "127.0.0.1:61006", peer_port: 0, username: "admin" };
const installs = [], edits = [], urls = [], errors = [], lifecycle = [], logReads = [];
const LOG = '<img src=x onerror="window.logInjected=true">\n<script>window.logInjected=true</script>\nfixture service log & < >';
let hold = false, release = null, failNext = "", modReads = 0, holdRead = false, releaseRead = null, failLifecycle = "";
let holdLifecycle = false, releaseLifecycle = null;
let holdLog = false, releaseLog = null;
const PASS = "fixture-install-phrase", EDIT_PASS = "fixture-edit-phrase";
(async () => {
  const browser = await chromium.launch({ headless: true, ...(process.env.PLAYWRIGHT_CHROMIUM ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM } : {}) });
  try {
    const context = await browser.newContext({ viewport: { width: 1400, height: 1000 } });
    const shell = async (route) => {
      const url = new URL(route.request().url());
      if (url.pathname.startsWith("/uygulama/")) {
        const file = path.join(magaza, url.pathname.slice("/uygulama/".length));
        return route.fulfill({ status: 200, contentType: url.pathname.endsWith(".css") ? "text/css" : "application/javascript", body: fs.readFileSync(file, "utf8") });
      }
      if (url.pathname.startsWith("/api/")) return api(route);
      // The public-address page (https://konsol.example) loads the same console files from the preview.
      if (route.request().resourceType() !== "document") {
        if (url.origin === new URL(base).origin) return route.continue();
        return route.fulfill({ response: await route.fetch({ url: base + url.pathname + url.search }) });
      }
      const response = await route.fetch({ url: base + url.pathname + url.search });
      await route.fulfill({ response, headers: { ...response.headers(), "content-security-policy": csp } });
    };
    const api = async (route) => {
      const req = route.request(), url = new URL(req.url()), p = url.pathname;
      urls.push(req.url());
      let result = {};
      if (p === "/api/konsol/moduller") { modReads++; result = { items: modules }; }
      else if (/^\/api\/konsol\/moduller\/(torrent|wireguard)\/gunluk$/.test(p)) {
        logReads.push({path:p,method:req.method()});
        if (holdLog) { holdLog=false; await new Promise(resolve => { releaseLog=resolve; }); }
        return route.fulfill({status:200,contentType:"text/plain",body:LOG});
      }
      else if (/^\/api\/konsol\/moduller\/(torrent|wireguard)\/kur$/.test(p)) {
        const body = req.postDataJSON(), m = modules.find((x) => p.includes("/" + x.id + "/"));
        installs.push({ id: m.id, body });
        if (hold) await new Promise((resolve) => { release = resolve; });
        if (failNext) {
          const error = failNext; failNext = "";
          return route.fulfill({ status: 400, contentType: "application/json", body: JSON.stringify({ error }) });
        }
        if (m.id === "torrent" && !(body.form && typeof body.form === "object")) {
          errors.push("qBittorrent install without its form: " + JSON.stringify(body));
          return route.fulfill({ status: 400, contentType: "application/json", body: JSON.stringify({ error: "Kurulum bilgileri gerekli" }) });
        }
        Object.assign(m, { installed: true, state: "calisiyor", live: m.runtime === "konsol" ? "-" : "running", progress: { action: "kur", step: "bitti", total: 0, text: "kuruldu" } });
        if (m.id === "torrent") {
          Object.assign(m, { sayfa: ["sayfa.js", "sayfa.css"], urls: { tailscale: "http://torrent.ayc", internet: null } });
          durum.username = body.form.username; durum.save = body.form.save.replace(/\/?$/, "/");
        }
        return route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify({ id: m.id, action: "kur" }) });
      }
      else if (/^\/api\/konsol\/moduller\/torrent\/(durdur|baslat)$/.test(p)) {
        // Like the backend: the request starts the engine's unit (202) and the module is busy until the
        // test finishes the operation; a refusal is an error answer and changes nothing.
        const action = p.split("/").pop(), m = modules[1];
        lifecycle.push({ action, body: req.postDataJSON() });
        if (holdLifecycle) { holdLifecycle = false; await new Promise((resolve) => { releaseLifecycle = resolve; }); }
        if (failLifecycle) {
          const error = failLifecycle; failLifecycle = "";
          return route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ error }) });
        }
        Object.assign(m, { busy: true, progress: { action, step: "1", total: 1, text: action === "durdur" ? "Durduruluyor" : "Başlatılıyor" } });
        return route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify({ id: "torrent", action }) });
      }
      else if (p === "/api/uygulama/torrent/durum") {
        // One delayed read on request (DD-210 regression: a late answer must not touch a newer dialog).
        if (holdRead) { holdRead = false; await new Promise((resolve) => { releaseRead = resolve; }); }
        result = { ...durum, running: modules[1].state === "calisiyor" };
      }
      else if (p === "/api/uygulama/torrent/ayar") {
        const body = req.postDataJSON();
        edits.push(body);
        if (failNext) {
          const error = failNext; failNext = "";
          return route.fulfill({ status: 400, contentType: "application/json", body: JSON.stringify({ error }) });
        }
        if (body.username) durum.username = body.username;
        if (body.save) durum.save = body.save.replace(/\/?$/, "/");
        result = { ok: true, username: durum.username, save: durum.save };
      }
      else if (p === "/api/konsol/moduller/torrent/hesap") result = { user: durum.username, temp: false };
      else if (p === "/api/konsol/ayarlar/klasorler") {
        const at = url.searchParams.get("path");
        result = { items: at === "/srv/media" ? [{ path: "/srv/media/filmler", free: 5 * 1024 ** 3 }]
          : [{ path: "/srv/downloads", free: 10 * 1024 ** 3 }, { path: "/srv/media", free: 10 * 1024 ** 3 }] };
      }
      else if (p === "/api/uygulama/wireguard/state") result = { now: Date.now() / 1000, networks: [], reserved: [], max: 10, defaults: { dns: "1.1.1.1", keepalive: 21, mtu: 1420, port: 61001 } };
      else if (p === "/api/konsol/kaynaklar") result = { host: "test", version: "test", domain: "ayc", os: "Debian 13", kernel: "test", uptime: 120, cores: 2, cpu: [1],
        mem: { total: 1000, used: 200 }, disk: { total: 1000, free: 500 }, root: "/srv", net: { tailscale: "100.64.0.2", wan: "192.0.2.1" }, read_at: Date.now() / 1000, sampled_at: Date.now() / 1000 };
      else if (p === "/api/konsol/saglik") result = { status: "ok", read_at: 1, checks: [] };
      else if (p === "/api/konsol/oturum") result = { durum: "acik", kullanici: "fixture", oturum_gun: 7, kanal: url.protocol === "https:" ? "internet" : "tailscale" };
      else if (p === "/api/konsol/ag") { const now = Math.floor(Date.now() / 1000); result = { read_at: now, iface: "eth0", window: 120, sampled_at: now, rx: 1, tx: 1, points: [], apps: [] }; }
      else if (p === "/api/konsol/guncelleme") result = {kurulu:"2026.08.06-v2-131",son:"2026.08.06-v2-131",commit:"a".repeat(40),yeni:false,denetlendi:1,hata:"",baslatilabilir:true,is:{durum:"yok",hedef:"",mesaj:"",bitis:null,asama:""}};  // DD-233: up to date
      else if (p === "/api/konsol/duzen") result = { duzen: null };
      else if (p === "/api/state") result = { root: "/srv", downloads: "downloads", protected: [], trash: { count: 0, size: 0 }, disk: { total: 1000, free: 500 } };
      else if (p === "/api/list") result = { path: "", entries: [] };
      else if (p === "/api/konsol/paylasim") result = { enabled: true, running: true, max: 32, host: "http://100.64.0.2:61010", items: [] };
      else if (p === "/api/trash" || p === "/api/konsol/islemler" || p === "/api/archives") result = { items: [] };
      else { errors.push("Unexpected endpoint: " + p); return route.fulfill({ status: 404, body: "unexpected" }); }
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(result) });
    };
    await context.route("**/*", shell);
    // The application's own web UI: a stub page so the new tab has somewhere to land.
    await context.route(/^https?:\/\/(torrent\.ayc|qbit\.example\.net)\//, (route) => route.fulfill({ status: 200, contentType: "text/html", body: "<title>qBittorrent</title>" }));
    const watch = (pg) => {
      pg.on("pageerror", (e) => errors.push(e.message));
      pg.on("console", (m) => { if (/violates.*Content Security Policy|Refused to/.test(m.text())) errors.push(m.text()); });
    };
    const page = await context.newPage();
    await page.clock.install();
    watch(page);
    const dialog = page.locator("#sh");
    // dialog.open becomes false before its queued close handlers run; await the event before reopening.
    const closeDialog = async () => {
      await dialog.evaluate(el => {
        el.dataset.testCloseObserved = "false";
        el.addEventListener("close",() => { el.dataset.testCloseObserved = "true"; },{once:true});
      });
      await page.keyboard.press("Escape");
      await page.waitForFunction(() => document.querySelector("#sh")?.dataset.testCloseObserved === "true",null,{timeout:3000});
      await dialog.waitFor({state:"hidden"});
    };
    const poll = async () => { const n = modReads; await page.evaluate(() => document.dispatchEvent(new Event("visibilitychange"))); for (let i = 0; i < 200 && modReads === n; i++) await page.waitForTimeout(10); };
    const navigate = async (hash) => { await page.evaluate((h) => { location.hash = h; }, hash); await page.waitForTimeout(80); };
    const noOverflow = async (pg = page) => assert(await pg.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), "no horizontal page scroll");

    /* ---- App Store: Kur opens the form; nothing is sent until a valid submission ---- */
    await page.goto(base + "/#/moduller");
    const card = page.locator("#modc-torrent");
    await card.getByRole("button", { name: "Kur", exact: true }).click();
    await dialog.getByRole("heading", { name: "qBittorrent'i kur", exact: true }).waitFor();
    const user = dialog.getByRole("textbox", { name: "Kullanıcı adı", exact: true });
    const pass = dialog.getByLabel("Parola", { exact: true }), again = dialog.getByLabel("Parola (tekrar)", { exact: true });
    const folder = dialog.getByRole("textbox", { name: "İndirme klasörü", exact: true });
    assert.equal(await user.inputValue(), "admin", "a sensible username is offered");
    assert.equal(await folder.inputValue(), "/srv/downloads", "the configured downloads folder is the default");
    assert.equal(await pass.inputValue(), "");
    assert.equal(await page.evaluate(() => document.activeElement && document.activeElement.id), await user.getAttribute("id"), "focus starts in the form");
    await page.screenshot({ path: path.join(shots, "install-dialog.png") });
    await page.keyboard.press("Escape");
    await dialog.waitFor({ state: "hidden" });
    await card.getByRole("button", { name: "Kur", exact: true }).click();
    await user.waitFor();
    await dialog.getByRole("button", { name: "Vazgeç", exact: true }).click();
    await dialog.waitFor({ state: "hidden" });
    assert.equal(installs.length, 0, "opening and cancelling the form sends nothing");
    // A password is required for a new setup and both entries must match.
    await card.getByRole("button", { name: "Kur", exact: true }).click();
    const submit = dialog.getByRole("button", { name: "Kur ve başlat", exact: true });
    await submit.click();
    assert.equal(installs.length, 0, "no password: no install");
    await pass.fill(PASS); await again.fill(PASS + "x");
    await submit.click();
    assert.equal(installs.length, 0, "different entries: no install");
    // WireGuard has no install form: its Kur still starts at once (no regression for other apps).
    await page.keyboard.press("Escape");
    await page.locator("#modc-wireguard").getByRole("button", { name: "Kur", exact: true }).click();
    while (!installs.length) await page.waitForTimeout(10);
    assert.deepEqual(installs[0], { id: "wireguard", body: { veri: false } });
    assert.equal(await dialog.isVisible(), false);
    // The form keeps its drafts through a server refusal and the 10 s poll; one click, one request.
    await card.getByRole("button", { name: "Kur", exact: true }).click();
    await user.fill("operator"); await pass.fill(PASS); await again.fill(PASS);
    await dialog.getByRole("button", { name: "Klasör seç", exact: true }).click();
    await dialog.getByRole("button", { name: "/srv/media içine gir", exact: true }).click();
    await dialog.getByText("/srv/media/filmler", { exact: true }).waitFor();
    await dialog.getByRole("button", { name: "Başlangıç dizinleri", exact: true }).click();
    await dialog.getByRole("button", { name: "/srv/media seç", exact: true }).click();
    assert.equal(await folder.inputValue(), "/srv/media");
    failNext = "Bu klasöre servis kullanıcısı yazamıyor.";
    await submit.click();
    await dialog.getByRole("alert").filter({ hasText: "Bu klasöre servis kullanıcısı yazamıyor." }).waitFor();
    await poll();
    assert.deepEqual([await user.inputValue(), await pass.inputValue(), await again.inputValue(), await folder.inputValue()],
      ["operator", PASS, PASS, "/srv/media"], "drafts survive an error and a poll");
    hold = true;
    await submit.click();
    while (installs.length < 3) await page.waitForTimeout(10);
    const busySubmit = dialog.locator("button[type=submit]");
    assert.equal(await busySubmit.innerText(), "Kuruluyor…");
    assert.equal(await busySubmit.isDisabled(), true, "the submit is locked while the request runs");
    await busySubmit.click({ force: true, timeout: 1000 }).catch(() => {});
    await page.waitForTimeout(100);
    assert.equal(installs.length, 3, "no duplicate submission");
    // The operator leaves the running request and opens a new form; the old request's answer must not
    // close or clear that new form (it reports in the background instead).
    await page.keyboard.press("Escape");
    await dialog.waitFor({ state: "hidden" });
    await card.getByRole("button", { name: "Kur", exact: true }).click();
    await user.waitFor();
    await user.fill("second-draft"); await pass.fill("second-draft-phrase"); await again.fill("second-draft-phrase");
    hold = false; release();
    await card.getByRole("link", { name: "qBittorrent arayüzünü yeni sekmede aç", exact: true }).waitFor();
    await page.getByText("qBittorrent kuruluyor; ilerleme App Store'da görünür.", { exact: true }).waitFor();
    assert.equal(await dialog.isVisible(), true, "A completed older request must not close a newly opened form");
    assert.deepEqual([await user.inputValue(), await pass.inputValue()], ["second-draft", "second-draft-phrase"], "nor clear its draft");
    await page.screenshot({ path: path.join(shots, "older-request-keeps-new-form.png") });
    assert.deepEqual(installs[2], { id: "torrent", body: { form: { username: "operator", password: PASS, save: "/srv/media" } } });
    await page.keyboard.press("Escape");
    await dialog.waitFor({ state: "hidden" });
    assert.equal(installs.length, 3, "the second draft was never sent");
    assert(!urls.some((u) => u.includes(PASS)), "the password never travels in a URL");
    assert(!JSON.stringify(await page.evaluate(() => [localStorage, sessionStorage])).includes(PASS));
    await page.waitForFunction(() => [...document.querySelectorAll("#sh input[type=password]")].every(el => !el.value));
    assert.equal(await page.locator("#sh input[type=password]").evaluateAll((els) => els.filter((e) => e.value).length), 0, "the closed form forgets the password");

    /* ---- App Store and overview open the native web UI in a new tab; no sidebar entry (DD-216) ---- */
    assert.equal(await page.locator(".nav a[data-app], #installed-label").count(), 0);
    const open = card.getByRole("link", { name: "qBittorrent arayüzünü yeni sekmede aç", exact: true });
    assert.equal(await open.getAttribute("href"), "http://torrent.ayc");
    assert.equal(await open.getAttribute("target"), "_blank");
    assert.equal(await page.locator("#modc-wireguard").getByRole("button", { name: "Aç", exact: true }).count(), 1, "WireGuard keeps its page");
    await navigate("#/genel");
    const tile = page.locator('#genel-tiles .tile[data-tile="torrent"]');
    await tile.waitFor();
    const launch = tile.locator("a.tile-link");
    assert.equal(await launch.getAttribute("href"), "http://torrent.ayc");
    assert.equal(await launch.getAttribute("target"), "_blank");
    assert.match(await launch.getAttribute("rel"), /noopener/);
    const settingsBtn = tile.getByRole("button", { name: "qBittorrent ayarları", exact: true });
    // Every footer reserves exactly three slots; unsupported actions keep their position as blank spans.
    const row = (sel) => page.locator(`#genel-tiles .tile[data-tile="${sel}"] .tile-actions > .tile-act`)
      .evaluateAll((els) => els.map((e) => [e.dataset.act,e.tagName, e.innerText.trim(), e.getAttribute("aria-label"), e.getAttribute("title"),
        e.querySelectorAll("svg").length, e.closest("a.tile-link") === null]));
    const iconOnly = async () => {
      // DD-229/230: the service action is a short word (Dur/Başla); settings (gear) and logs (terminal) are icons.
      assert.deepEqual(await row("torrent"), [["servis","BUTTON", "Dur", "qBittorrent: Durdur", "qBittorrent: Durdur", 0, true],
        ["ayar","BUTTON", "", "qBittorrent ayarları", "qBittorrent ayarları", 1, true],
        ["gunluk","BUTTON", "", "qBittorrent günlükleri", "qBittorrent günlükleri", 1, true]], "service, settings, logs in order; controls outside the launch link");
      // WireGuard stops as a whole now; its settings are its page.
      assert.deepEqual(await row("wireguard"), [["servis","BUTTON","Dur","WireGuard: Durdur","WireGuard: Durdur",0,true],
        ["ayar","A", "", "WireGuard ayarları", "WireGuard ayarları", 1, true],
        ["gunluk","BUTTON","","WireGuard günlükleri","WireGuard günlükleri",1,true]]);
      for (const id of ["torrent","wireguard"])
        assert.equal(await page.locator(`#genel-tiles [data-tile="${id}"] .tile-actions > *`).count(),3,"no extra footer slots");
      const icon = (sel) => page.locator(sel + " svg").evaluate((el) => el.innerHTML);
      assert.match(await icon('#genel-tiles [data-tile="torrent"] [data-act="ayar"]'), /<circle cx="9" cy="9" r="2.3"/, "settings is the gear");
      assert.match(await icon('#genel-tiles [data-tile="torrent"] [data-act="gunluk"]'), /<rect x="1.8" y="3"/, "logs is the terminal");
      await page.locator('#genel-tiles [data-tile="wireguard"] [data-act="servis"]').focus();
      await page.keyboard.press("Tab");
      assert(await page.locator('#genel-tiles [data-tile="wireguard"] [data-act="ayar"]').evaluate(el => document.activeElement === el),"Tab follows the visible row");
    };
    // Computed look of an action now (rest, hover, pressed): transparent, borderless, no shadow, no text.
    const bare = (sel) => page.locator(sel).evaluate((el) => { const c = getComputedStyle(el);
      return [c.backgroundColor, c.borderTopStyle === "none" || c.borderTopWidth === "0px", c.boxShadow, el.innerText.trim()]; });
    const BARE = ["rgba(0, 0, 0, 0)", true, "none", ""];
    const bareFor = (sel) => sel.includes('"servis"') ? [...BARE.slice(0, 3), "Dur"] : BARE;
    const looks = async () => {
      for (const sel of ['#genel-tiles [data-tile="torrent"] [data-act="ayar"]', '#genel-tiles [data-tile="torrent"] [data-act="servis"]',
        '#genel-tiles [data-tile="torrent"] [data-act="gunluk"]', '#genel-tiles [data-tile="wireguard"] [data-act="ayar"]',
        '#genel-tiles [data-tile="wireguard"] [data-act="gunluk"]']) {
        assert.deepEqual(await bare(sel), bareFor(sel), `${sel} at rest`);
        await page.locator(sel).hover();
        assert.deepEqual(await bare(sel), bareFor(sel), `${sel} on hover`);
        await page.mouse.down();
        assert.deepEqual(await bare(sel), bareFor(sel), `${sel} while pressed`);
        await page.mouse.move(1, 1); await page.mouse.up();
      }
    };
    await iconOnly();
    const compactTile = await tile.boundingBox();
    // v191 at this viewport: ~169px wide, 193px tall. Keep its height and usable 44px action targets.
    assert(compactTile.width>=139 && compactTile.width<=144,`15–18% narrower at 1400px: ${JSON.stringify(compactTile)}`);
    assert(Math.abs(compactTile.height-193)<=2,`same card height: ${JSON.stringify(compactTile)}`);
    await looks();
    assert.equal(await page.locator('#genel-tiles .tile[data-tile="wireguard"] .tile-actions a').getAttribute("href"), "#/wireguard");
    assert.equal(await page.locator('#genel-tiles .tile[data-tile="wireguard"] a.tile-link').getAttribute("href"), "#/wireguard");
    for (const builtIn of ["dosyalar", "paylasim", "moduller", "ayarlar"])
      assert.equal(await page.locator(`#genel-tiles .tile[data-tile="${builtIn}"]`).count(), 0, `${builtIn} has no home tile`);
    assert.deepEqual(await page.locator("#genel-tiles .tile").evaluateAll(els => els.map(el => el.dataset.tile)),["wireguard","torrent"]);
    await page.screenshot({ path: path.join(shots, "overview-desktop.png") });
    await page.locator("#genel-tiles").screenshot({ path: path.join(shots, "tiles-desktop.png") });
    const serviceBtn = tile.locator('[data-act="servis"]');
    const actBox = await settingsBtn.boundingBox(), svcBox = await serviceBtn.boundingBox(), icoBox = await tile.locator(".ico").boundingBox();
    assert(actBox.y > icoBox.y + icoBox.height && svcBox.y > icoBox.y + icoBox.height, "the actions sit beneath the application icon");
    assert(Math.abs(actBox.y - svcBox.y) < 2, "one row");
    assert(actBox.height <= 44 && actBox.width <= 70, `compact: ${JSON.stringify(actBox)}`);
    for (const b of [settingsBtn, serviceBtn,tile.locator('[data-act="gunluk"]')]) {
      // DD-229: the service action is a word (no glyph); settings and logs keep their 18 px icon.
      const hit = await b.evaluate((el) => { const r=el.getBoundingClientRect(),g=el.querySelector("svg"),s=g&&g.getBoundingClientRect();
        return r.width>=44 && r.height>=44 && (s ? s.width===18 && s.height===18 : el.innerText.trim().length>0) &&
          [[r.left+r.width/2,r.top+1],[r.right-1,r.top+r.height/2],[r.left+1,r.top+r.height/2],[r.left+r.width/2,r.bottom-1]].every(([x,y]) => {
            const target=document.elementFromPoint(x,y); return target===el || el.contains(target);
          }); });
      assert(hit, "actual 44 px touch bounds receive edge hits around the visible 18 px glyph");
    }
    const [popup] = await Promise.all([context.waitForEvent("page"), launch.click()]);
    await popup.waitForLoadState();
    assert.equal(popup.url(), "http://torrent.ayc/");
    assert.equal(await popup.evaluate(() => window.opener), null, "noopener");
    await popup.close();
    assert.equal(await page.evaluate(() => location.hash), "#/genel", "Konsol stays where it was");

    /* ---- Logs use the existing read-only endpoint and render untrusted bytes as text in #sh ---- */
    for (const [id,name] of [["torrent","qBittorrent"],["wireguard","WireGuard"]]) {
      const logButton = page.locator(`#genel-tiles [data-tile="${id}"] [data-act="gunluk"]`);
      const reads = logReads.length;
      await logButton.focus();
      await page.keyboard.press("Enter");
      await dialog.getByRole("heading",{name:`${name} günlükleri`,exact:true}).waitFor();
      await dialog.locator("pre").filter({hasText:"fixture service log"}).waitFor();
      assert.equal(await dialog.locator("pre").textContent(),LOG,"log markup remains literal text");
      assert.equal(await dialog.locator("img,script").count(),0);
      assert.equal(await page.evaluate(() => window.logInjected),undefined);
      assert.deepEqual(logReads.slice(reads),[{path:`/api/konsol/moduller/${id}/gunluk`,method:"GET"}]);
      assert.equal(await page.evaluate(() => location.hash),"#/genel");
      await closeDialog();
    }
    assert.equal(lifecycle.length,0,"opening logs never starts or stops an app");

    /* ---- Timeout is recoverable with Yenile; late reads cannot overwrite a new dialog or reopen it ---- */
    const logButton = tile.locator('[data-act="gunluk"]');
    const waitHeldLog = async () => {
      for (let i=0;i<200 && !releaseLog;i++) await page.waitForTimeout(10);
      assert(releaseLog,"the held log request reached the API fixture");
    };
    holdLog=true;
    await logButton.click();
    await waitHeldLog();
    await page.clock.fastForward(13000);
    await dialog.getByRole("alert").filter({hasText:/zaman aşımı/}).waitFor();
    releaseLog(); releaseLog=null;
    const retry = dialog.getByRole("button",{name:"Yenile",exact:true});
    assert(await retry.isEnabled(),"a timed-out log read leaves Yenile available");
    const beforeRetry=logReads.length;
    await retry.click();
    await dialog.locator("pre").filter({hasText:"fixture service log"}).waitFor({timeout:3000});
    assert.equal(logReads.length,beforeRetry+1,"Yenile sends a new GET after timeout");
    assert.equal(await dialog.getByRole("alert").isVisible(),false);
    await closeDialog();
    for (const replace of [false,true]) {
      holdLog=true;
      await logButton.click();
      await waitHeldLog();
      await closeDialog();
      if (replace) {
        await settingsBtn.click();
        await user.waitFor();
        await user.fill("new-dialog-draft");
      }
      releaseLog(); releaseLog=null;
      await page.waitForTimeout(150);
      if (replace) {
        assert.equal(await dialog.getByRole("heading",{name:"qBittorrent ayarları",exact:true}).count(),1,"a late log answer leaves the newer dialog intact");
        assert.equal(await user.inputValue(),"new-dialog-draft");
        assert.equal(await dialog.locator("pre").count(),0);
        await closeDialog();
      } else assert.equal(await dialog.isVisible(),false,"a late log answer cannot reopen a closed dialog");
    }
    await page.clock.setSystemTime(new Date());

    /* ---- The gear opens a compact edit dialog; a blank password keeps the stored one ---- */
    await settingsBtn.focus();
    await page.keyboard.press("Enter");
    await dialog.getByRole("heading", { name: "qBittorrent ayarları", exact: true }).waitFor();
    await page.waitForFunction(() => document.querySelector("#sh input[name=username]")?.value === "operator");
    assert.equal(await folder.inputValue(), "/srv/media/");
    assert.equal(await pass.inputValue(), "", "the stored password is never shown or read");
    assert.equal(await pass.getAttribute("required"), null, "a blank password is allowed when editing");
    await page.screenshot({ path: path.join(shots, "settings-dialog.png") });
    const saveEdit = dialog.getByRole("button", { name: "Kaydet", exact: true });
    await saveEdit.click();
    await dialog.getByText("Değişiklik yok.", { exact: true }).waitFor();
    assert.equal(edits.length, 0);
    await user.fill("editor");
    failNext = "Kullanıcı adı geçersiz.";
    await saveEdit.click();
    await dialog.getByRole("alert").filter({ hasText: "Kullanıcı adı geçersiz." }).waitFor();
    await poll();
    assert.equal(await user.inputValue(), "editor", "the edit draft survives an error and a poll");
    await saveEdit.click();
    await dialog.waitFor({ state: "hidden" });
    assert.deepEqual(edits, [{ username: "editor" }, { username: "editor" }], "only the changed field, no password");
    // The dialog's close event (which returns focus) is queued after it hides.
    await page.waitForFunction(() => document.activeElement && document.activeElement.getAttribute("aria-label") === "qBittorrent ayarları", null, { timeout: 3000 })
      .catch(() => assert.fail("focus returns to the settings action"));
    await settingsBtn.click();
    await page.waitForFunction(() => document.querySelector("#sh input[name=username]")?.value === "editor");
    await pass.fill(EDIT_PASS); await again.fill(EDIT_PASS);
    await dialog.getByRole("button", { name: "Klasör seç", exact: true }).click();
    await dialog.getByRole("button", { name: "/srv/downloads seç", exact: true }).click();
    await saveEdit.click();
    await dialog.waitFor({ state: "hidden" });
    assert.deepEqual(edits[2], { password: EDIT_PASS, save: "/srv/downloads" });
    await settingsBtn.click();
    await user.waitFor();
    await page.keyboard.press("Escape");
    await dialog.waitFor({ state: "hidden" });
    assert.equal(edits.length, 3, "Escape changes nothing");

    /* ---- A late settings read must not replace a dialog opened after it ---- */
    holdRead = true;
    await settingsBtn.click();
    await dialog.getByText("Okunuyor…", { exact: true }).waitFor();
    while (!releaseRead) await page.waitForTimeout(10);
    await page.keyboard.press("Escape");
    await dialog.waitFor({ state: "hidden" });
    await navigate("#/torrent");
    await page.locator("#torrent-settings").getByRole("button", { name: "Klasör seç", exact: true }).click();
    await dialog.getByRole("heading", { name: "İndirme klasörü seç", exact: true }).waitFor();
    releaseRead(); releaseRead = null;
    await page.waitForTimeout(300);
    assert.equal(await dialog.getByRole("heading", { name: "İndirme klasörü seç", exact: true }).count(), 1, "the late read leaves the newer dialog alone");
    assert.equal(await dialog.locator("form.app-form").count(), 0);
    await page.keyboard.press("Escape");
    await dialog.waitFor({ state: "hidden" });
    await navigate("#/genel");

    /* ---- Durdur from the tile: the existing confirmation, server progress, no duplicates, focus kept ---- */
    // [tooltip, accessible name, aria-disabled, focused, visible text]
    const svc = () => page.evaluate(() => { const b = document.querySelector('#genel-tiles [data-tile="torrent"] [data-act="servis"]');
      return b && [b.getAttribute("title"), b.getAttribute("aria-label"), b.getAttribute("aria-disabled"), document.activeElement === b, b.innerText.trim()]; });
    await serviceBtn.focus();
    await page.keyboard.press("Enter");
    await page.locator("#cf-title").filter({ hasText: "qBittorrent durdurulsun mu?" }).waitFor();
    assert.match(await page.locator("#cf-list").innerText(), /Süren indirmeler duraklar/, "the package's own stop explanation");
    await page.locator("#cf-cancel").click();
    assert.equal(lifecycle.length, 0, "cancelling the confirmation stops nothing");
    await serviceBtn.click();
    await page.locator("#cf-go").click();
    while (lifecycle.length < 1) await page.waitForTimeout(10);
    await page.waitForFunction(() => document.querySelector('#genel-tiles [data-tile="torrent"] [data-act="servis"]')?.getAttribute("aria-disabled") === "true");
    assert.deepEqual(await svc(), ["qBittorrent: Durduruluyor…", "qBittorrent: Durduruluyor…", "true", true, "Dur"], "busy: the word stays, dimmed; focus back on the action after the confirmation");
    // Measured in one step: the 1.5 s progress poll redraws the row and would detach a held element.
    assert(await page.evaluate(() => { const t = document.querySelector('#genel-tiles .tile[data-tile="torrent"]'), b = t.querySelector('[data-act="servis"]');
      const tr = t.getBoundingClientRect(), br = b.getBoundingClientRect(); return br.left >= tr.left && br.right <= tr.right; }), "the busy action stays inside the tile");
    // The busy row is redrawn by the 1.5 s progress poll; click the current copy directly, then by keyboard.
    await page.evaluate(() => document.querySelector('#genel-tiles [data-tile="torrent"] [data-act="servis"]').click());
    await serviceBtn.focus();
    await page.keyboard.press("Enter");
    await page.waitForTimeout(150);
    assert.equal(await page.locator("#cf").evaluate((d) => d.open), false, "a busy app asks nothing");
    assert.equal(lifecycle.length, 1, "no duplicate stop while the operation runs");
    await serviceBtn.focus();
    await poll();
    assert.equal((await svc())[3], true, "keyboard focus stays on the action across a poll redraw");
    await page.screenshot({ path: path.join(shots, "tile-stopping.png") });
    Object.assign(modules[1], { busy: false, state: "durduruldu", live: "exited", progress: { action: "durdur", step: "bitti", total: 0, text: "durduruldu" } });
    await poll();
    await page.waitForFunction(() => document.querySelector('#genel-tiles [data-tile="torrent"] [data-act="servis"]')?.getAttribute("aria-label") === "qBittorrent: Başlat");
    assert.deepEqual(await svc(), ["qBittorrent: Başlat", "qBittorrent: Başlat", "false", true, "Başla"], "the name follows the finished operation; focus kept");
    assert.deepEqual(lifecycle[0], { action: "durdur", body: { veri: false } });

    /* ---- A stopped app opens its page, not a dead link; its settings still open and save ---- */
    await page.waitForFunction(() => document.querySelector('#genel-tiles .tile[data-tile="torrent"] a.tile-link')?.getAttribute("href") === "#/torrent");
    assert.equal(await launch.getAttribute("target"), null);
    assert.equal(await settingsBtn.count(), 1);
    await settingsBtn.click();
    await page.waitForFunction(() => document.querySelector("#sh input[name=username]")?.value === "editor");
    await user.fill("stopped-edit");
    await saveEdit.click();
    await dialog.waitFor({ state: "hidden" });
    assert.deepEqual(edits[edits.length - 1], { username: "stopped-edit" }, "a stopped app's settings save");
    assert.equal(modules[1].state, "durduruldu", "saving settings does not start the app");
    await navigate("#/moduller");
    assert.equal(await card.getByRole("button", { name: "Aç", exact: true }).count(), 1, "the App Store opens the page while stopped");
    await navigate("#/genel");
    await poll();

    /* ---- Başlat: no confirmation; a refusal is shown and the action stays usable ---- */
    failLifecycle = "bu modülde bir işlem sürüyor";
    await serviceBtn.click();
    await page.getByText("bu modülde bir işlem sürüyor", { exact: true }).waitFor();
    await page.waitForFunction(() => document.querySelector('#genel-tiles [data-tile="torrent"] [data-act="servis"]')?.getAttribute("aria-disabled") === "false");
    assert.deepEqual((await svc()).slice(0, 3), ["qBittorrent: Başlat", "qBittorrent: Başlat", "false"]);
    assert.equal(modules[1].state, "durduruldu");
    // The request's own redraws must not pull focus back to the tile once the operator has moved on.
    holdLifecycle = true;
    await serviceBtn.click();
    while (!releaseLifecycle) await page.waitForTimeout(10);
    const elsewhere = page.locator('.nav a[href="#/dosyalar"]');
    await elsewhere.focus();
    releaseLifecycle(); releaseLifecycle = null;
    while (lifecycle.length < 3) await page.waitForTimeout(10);
    await page.waitForFunction(() => document.querySelector('#genel-tiles [data-tile="torrent"] [data-act="servis"]')?.getAttribute("aria-label") === "qBittorrent: Başlatılıyor…");
    await page.waitForTimeout(200);
    assert.equal(await elsewhere.evaluate((el) => document.activeElement === el), true, "a finishing request leaves focus where the operator put it");
    await page.waitForFunction(() => document.querySelector('#genel-tiles [data-tile="torrent"] [data-act="servis"]')?.getAttribute("aria-label") === "qBittorrent: Başlatılıyor…");
    assert.deepEqual([(await svc())[0], (await svc())[4]], ["qBittorrent: Başlatılıyor…", "Başla"]);
    Object.assign(modules[1], { busy: false, state: "calisiyor", live: "running", progress: { action: "baslat", step: "bitti", total: 0, text: "başlatıldı" } });
    await poll();
    await page.waitForFunction(() => document.querySelector('#genel-tiles [data-tile="torrent"] [data-act="servis"]')?.getAttribute("aria-label") === "qBittorrent: Durdur");
    assert.deepEqual(lifecycle.map((x) => x.action), ["durdur", "baslat", "baslat"]);
    await page.waitForFunction(() => document.querySelector('#genel-tiles .tile[data-tile="torrent"] a.tile-link')?.getAttribute("href") === "http://torrent.ayc");

    /* ---- Edit mode keeps reordering: no settings action, tiles are not links ---- */
    await page.emulateMedia({ reducedMotion: "reduce" });  // the wiggle would keep the arrows "unstable" for clicks
    await page.locator("#genel-duzenle").click();
    assert.equal(await page.locator("#genel-tiles .tile-actions").count(), 0, "no app actions while editing");
    assert.equal(await page.locator("#genel-tiles a").count(), 0);
    const order = () => page.locator("#genel-tiles .tile").evaluateAll((els) => els.map((e) => e.dataset.tile));
    const before = await order();
    await page.locator('#genel-tiles .tile[data-tile="torrent"] [data-move="-1"]').click();
    const after = await order();
    assert.equal(after.indexOf("torrent"), before.indexOf("torrent") - 1, "arrow moves still work");
    await page.locator("#genel-vazgec").click();
    assert.deepEqual(await order(), before);
    assert.equal(await page.locator("#genel-tiles .tile-actions").count(), 2, "the actions return after editing");
    // The lifecycle refusal toast is transient; measure the resting layout after it dismisses.
    await page.locator("#toast").waitFor({state:"hidden",timeout:7000});

    /* ---- Desktop and 320/390 px phones, in both themes: visible, distinct icon hit targets ---- */
    const actionGlyphs = await page.locator("#genel-tiles .tile-act:not(.tile-act-empty) svg").evaluateAll(els => els.map(el => el.innerHTML));
    for (const colorScheme of ["light","dark"]) {
      await page.emulateMedia({colorScheme});
      for (const width of [1400,390,320]) {
        await page.setViewportSize({width,height:950});
        await noOverflow();
        await iconOnly();
        assert.deepEqual(await page.locator("#genel-tiles .tile-act:not(.tile-act-empty) svg").evaluateAll(els => els.map(el => el.innerHTML)),actionGlyphs,
          `glyphs remain intact at ${width}/${colorScheme}`);
        for (const id of ["torrent","wireguard"]) {
          const actions = page.locator(`#genel-tiles [data-tile="${id}"] .tile-actions`);
          const rowBox = await actions.boundingBox(), tileBox = await page.locator(`#genel-tiles [data-tile="${id}"]`).boundingBox();
          assert(rowBox.x>=tileBox.x && rowBox.x+rowBox.width<=tileBox.x+tileBox.width+1,`three slots fit ${id} at ${width}/${colorScheme}`);
          const slots = await actions.locator(".tile-act").evaluateAll(els => els.map(el => {
            const r=el.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height};
          }));
          assert(slots.every(s => s.width>0 && s.height>0 && Math.abs(s.y-slots[0].y)<2),"all three slots reserve space on one row");
          assert(slots[0].x+slots[0].width<=slots[1].x && slots[1].x+slots[1].width<=slots[2].x,"slots remain ordered without overlap");
          // Each control is found again by its slot, and the check repeats once if the five-second poll
          // redraws the tile in the middle of it (a detached element measures 0×0).
          for (const act of await actions.locator("button,a").evaluateAll(els => els.map(el => el.dataset.act))) {
            const button = actions.locator(`[data-act="${act}"]`);
            let hitTest;
            for (let attempt = 0; attempt < 3; attempt++) {
              try {
                await button.scrollIntoViewIfNeeded();
                assert(await button.isVisible());
                hitTest = await button.evaluate(el => {
                  const r=el.getBoundingClientRect(),svg=el.querySelector("svg")||el,s=svg.getBoundingClientRect();
                  const point={x:r.x+r.width/2,y:r.y+r.height/2},hit=document.elementFromPoint(point.x,point.y);
                  const describe = node => node && ({tag:node.tagName,id:node.id,class:node.getAttribute("class"),label:node.getAttribute("aria-label")});
                  return {ok:el.isConnected && (hit===el || el.contains(hit)) && s.width>0 && s.height>0 && getComputedStyle(svg).visibility!=="hidden",
                    attached:el.isConnected,
                    control:describe(el),rect:{x:r.x,y:r.y,width:r.width,height:r.height},point,scroll:{x:scrollX,y:scrollY},
                    viewport:{width:innerWidth,height:innerHeight},glyph:{width:s.width,height:s.height,visibility:getComputedStyle(svg).visibility},
                    hit:describe(hit),stack:document.elementsFromPoint(point.x,point.y).slice(0,6).map(describe)};
                });
              } catch (err) {
                if (!/not attached|detached/i.test(String(err)) || attempt === 2) throw err;
                continue;
              }
              if (hitTest.ok || hitTest.attached && hitTest.rect.width > 0) break;
            }
            const hitShot=path.join(shots,`hit-target-${id}-${act}-${width}-${colorScheme}.png`);
            if (!hitTest.ok) await page.screenshot({path:hitShot});
            assert(hitTest.ok,`visible control receives its center hit at ${width}/${colorScheme}: ${JSON.stringify(hitTest)}; screenshot: ${hitShot}`);
            await button.click({trial:true});
          }
        }
        // Exercise the visible log control on every viewport/theme; no forced clicks or DOM dispatch.
        await tile.locator('[data-act="gunluk"]').click();
        await dialog.getByRole("heading",{name:"qBittorrent günlükleri",exact:true}).waitFor();
        await dialog.locator("pre").filter({hasText:"fixture service log"}).waitFor();
        const logBox = await dialog.boundingBox();
        assert(logBox.x>=0 && logBox.x+logBox.width<=width+1,`logs fit ${width}/${colorScheme}`);
        await noOverflow();
        await closeDialog();
        await page.screenshot({path:path.join(shots,`overview-${width}-${colorScheme}.png`),fullPage:true});
      }
    }

    /* ---- The existing phone settings/install journeys ---- */
    await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ colorScheme: "dark" });
    await page.waitForTimeout(100);
    await noOverflow();
    await page.screenshot({ path: path.join(shots, "overview-390-dark.png"), fullPage: true });
    // DD-229: the bar is fixed bottom-right; scrolled to the end, the last row stays clear of it.
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
    const phoneEditLayout = await page.evaluate(() => {
      const bar=document.querySelector("#genel-edit").getBoundingClientRect();
      const rect=r => ({x:r.x,y:r.y,width:r.width,height:r.height});
      const overlaps=[...document.querySelectorAll("#genel-tiles .tile")].flatMap(el => {
        const tile=el.getBoundingClientRect();
        return bar.left<tile.right && bar.right>tile.left && bar.top<tile.bottom && bar.bottom>tile.top
          ? [{id:el.dataset.tile,rect:rect(tile)}] : [];
      });
      return {editing:document.querySelector("#genel-tiles").classList.contains("editing"),bar:rect(bar),overlaps};
    });
    assert.equal(phoneEditLayout.editing,false,"check the normal phone layout outside edit mode");
    assert.deepEqual(phoneEditLayout.overlaps,[],`Düzenle must not overlap application tiles at 390x844: ${JSON.stringify(phoneEditLayout)}`);
    await page.locator("#genel-tiles").screenshot({ path: path.join(shots, "tiles-390-dark.png") });
    const phoneRow = await tile.locator(".tile-actions").boundingBox(), phoneTile = await tile.boundingBox();
    assert(phoneRow.x >= phoneTile.x && phoneRow.x + phoneRow.width <= phoneTile.x + phoneTile.width + 1, "the action row fits the phone tile");
    await iconOnly();
    for (const sel of ['#genel-tiles [data-tile="torrent"] [data-act="ayar"]', '#genel-tiles [data-tile="torrent"] [data-act="servis"]'])
      assert.deepEqual(await bare(sel), bareFor(sel), `${sel} at 390 px dark`);
    // Keyboard order matches the visible row: service → settings → logs.
    await page.locator('#genel-tiles [data-tile="torrent"] [data-act="servis"]').focus();
    await page.keyboard.press("Tab");
    assert.equal(await page.locator('#genel-tiles [data-tile="torrent"] [data-act="ayar"]').evaluate((el) => document.activeElement === el), true);
    await page.locator("#genel-tiles").screenshot({ path: path.join(shots, "tiles-390-dark-focus.png") });
    assert.notEqual(await page.locator('#genel-tiles [data-tile="torrent"] [data-act="ayar"]').evaluate((el) => getComputedStyle(el).outlineStyle), "none",
      "keyboard focus stays visible");
    await page.locator('#genel-tiles [data-tile="torrent"] [data-act="ayar"]').blur();
    await settingsBtn.click();
    await user.waitFor();
    await dialog.getByRole("button", { name: "Klasör seç", exact: true }).click();
    await dialog.getByRole("button", { name: "/srv/media seç", exact: true }).waitFor();
    const dlgBox = await dialog.boundingBox();
    assert(dlgBox.x >= 0 && dlgBox.x + dlgBox.width <= 390, `the dialog fits the phone: ${JSON.stringify(dlgBox)}`);
    await noOverflow();
    await page.screenshot({ path: path.join(shots, "settings-dialog-390-dark.png") });
    await page.keyboard.press("Escape");
    await navigate("#/moduller");
    modules[1].installed = false; modules[1].state = ""; delete modules[1].urls;
    await poll();
    await card.getByRole("button", { name: "Kur", exact: true }).click();
    await user.waitFor();
    await page.screenshot({ path: path.join(shots, "install-dialog-390-dark.png") });
    await page.keyboard.press("Escape");
    Object.assign(modules[1], { installed: true, state: "calisiyor", live: "running", urls: { tailscale: "http://torrent.ayc", internet: "https://qbit.example.net" } });

    /* ---- Public HTTPS address: the public name, or the page while that publication is off ---- */
    const secure = await context.newPage();
    watch(secure);
    await secure.goto("https://konsol.example/#/genel");
    const sTile = secure.locator('#genel-tiles .tile[data-tile="torrent"] a.tile-link');
    await sTile.waitFor();
    assert.equal(await sTile.getAttribute("href"), "https://qbit.example.net");
    modules[1].urls.internet = null;
    await secure.reload();
    await sTile.waitFor();
    assert.equal(await sTile.getAttribute("href"), "#/torrent", "never the private tailnet name on the public address");
    await secure.close();

    assert.deepEqual(errors, []);
    console.log("PASS: install form and settings regressions; native app launch/noopener/public channel; installed-only home; three ordered action slots (word, gear, terminal), WireGuard stop/start; safe GET logs in dialog; stop/start confirmation, progress, refusal and focus; edit reorder; desktop/320/390 light/dark overflow, glyphs and visible hit targets. Screenshots: " + shots);
  } catch (err) { if (errors.length) console.error("Browser errors:",errors); throw err;
  } finally { await browser.close(); }
})().catch((err) => { console.error(err); process.exit(1); });
