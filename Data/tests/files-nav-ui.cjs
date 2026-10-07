/* DD-236: Files navigates like a file manager, on the real console assets under the production CSP with
   fixtured APIs: a fixed window whose frame is never rebuilt, the old listing kept (dimmed, inert) while the
   next one loads, back/forward with each folder's scroll, the short cache, a failed open staying put, stale
   answers dropped, polling that repaints nothing, the keyboard, and the phone's page scroll. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs"), os = require("node:os"), path = require("node:path");
const shots = fs.mkdtempSync(path.join(os.tmpdir(), "konsol-files-nav-"));
const base = process.env.KONSOL_URL || "http://127.0.0.1:8766";
const csp = fs.readFileSync(path.join(__dirname, "../templates/Caddyfile"), "utf8").match(/Content-Security-Policy "([^"]+)"/)[1];
const now = Date.now() / 1000;
const dir = (name, count = 3) => ({ name, type: "dir", count, size: 4096, mtime: now });
const file = (name) => ({ name, type: "file", size: 2048, mtime: now });
// Root: 60 folders (the contents must scroll), a "broken" folder that cannot be listed, a slow one.
const tree = {
  "": [...Array.from({ length: 60 }, (_, i) => dir("klasor-" + String(i + 1).padStart(2, "0"))), dir("bozuk"), dir("yavas"), file("not.txt")],
  "klasor-60": [dir("alt"), file("a.txt"), file("b.txt")],
  "klasor-60/alt": [file("derin.txt")],
  "klasor-01": [file("bir.txt")],
  "yavas": [file("gec.txt")],
};
const errors = [], reads = [];
let hold = {};   // path -> Promise to wait for before answering
(async () => {
  const browser = await chromium.launch({ headless: true, ...(process.env.PLAYWRIGHT_CHROMIUM ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM } : {}) });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    await context.route("**/*", async (route) => {
      const req = route.request(), url = new URL(req.url()), p = url.pathname;
      if (req.resourceType() === "document") {
        const response = await route.fetch();
        return route.fulfill({ response, headers: { ...response.headers(), "content-security-policy": csp } });
      }
      if (!p.startsWith("/api/")) return route.continue();
      let result;
      if (p === "/api/list") {
        const at = url.searchParams.get("path") || "", dirs = url.searchParams.get("dirs") === "1";
        reads.push(at + (dirs ? "?dirs" : ""));
        if (hold[at]) await hold[at];
        if (at === "bozuk") return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: "bulunamadı (taşınmış ya da silinmiş olabilir)" }) });
        const entries = (tree[at] || []).filter((e) => !dirs || e.type === "dir");
        result = { path: at, entries };
      } else if (p === "/api/state") result = { root: "/srv", downloads: "downloads", protected: [], trash: { count: 0, size: 0 }, disk: { total: 1000, free: 500 } };
      else if (p === "/api/sistem/state") return route.fulfill({ status: 404, contentType: "application/json", body: '{"error":"yok"}' });
      else if (p === "/api/konsol/paylasim") result = { enabled: true, running: true, max: 32, host: "http://100.64.0.2:61010", items: [] };
      else if (p === "/api/konsol/moduller" || p === "/api/konsol/islemler" || p === "/api/trash" || p === "/api/archives") result = { items: [] };
      else if (p === "/api/konsol/kaynaklar") result = { host: "nrm", version: "x", domain: "ev", os: "Debian 13", kernel: "t", uptime: 1, cores: 2, cpu: [1],
        mem: { total: 1000, used: 200 }, disk: { total: 1000, free: 500 }, root: "/srv", net: { tailscale: "100.64.0.2", wan: "192.0.2.1" }, read_at: now, sampled_at: now };
      else if (p === "/api/konsol/oturum") result = { durum: "acik", kullanici: "fixture", kanal: "tailscale" };
      else if (p === "/api/konsol/guncelleme") result = { kurulu: "x", son: "x", commit: null, yeni: false, denetlendi: 1, hata: "", baslatilabilir: true, is: { durum: "yok" } };
      else if (p === "/api/konsol/duzen") result = { duzen: null };
      else { errors.push("Unexpected endpoint: " + p); return route.fulfill({ status: 404, body: "unexpected" }); }
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(result) });
    });
    const page = await context.newPage();
    await page.clock.install();
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("console", (m) => { if (/Content Security Policy|Refused to/.test(m.text())) errors.push(m.text()); });
    const tile = (name) => page.locator(`#fs-table [data-item="${name}"]`);
    const crumb = () => page.locator("#fs-bar .crumb.cur").innerText();
    const rows = page.locator("#fs-rows");
    const loading = () => page.locator("#fs-panel").evaluate((p) => p.classList.contains("fx-loading"));
    const open = async (name) => { await tile(name).click(); await tile(name).click(); };
    const frame = () => page.evaluate(() => {
      const r = (s) => { const b = document.querySelector(s).getBoundingClientRect(); return [Math.round(b.left), Math.round(b.top), Math.round(b.width), Math.round(b.height)]; };
      return { side: r(".side"), title: r("#title"), panel: r("#fs-panel"), rail: r("#fs-rail"), page: [scrollY, document.documentElement.scrollHeight <= innerHeight + 1] };
    });
    const sameNodes = () => page.evaluate(() => window.__nodes.every((el) => el.isConnected));

    await page.goto(base + "/#/dosyalar");
    await tile("klasor-60").waitFor();
    await page.evaluate(() => { window.__nodes = ["#fs-bar .pathfield", "#fs-q", "#fs-rail", "#fs-rows", "#fs-detail", ".side", "#title"].map((s) => document.querySelector(s)); });

    // A window of the viewport's height: the page does not scroll, the contents do.
    const first = await frame();
    assert.deepEqual(first.page, [0, true], "the page itself must not scroll on a desktop-width screen");
    assert(await rows.evaluate((b) => b.scrollHeight > b.clientHeight + 100), "60 folders must scroll inside the contents");
    assert(await page.evaluate(() => document.documentElement.classList.contains("fx-fixed")));
    await page.screenshot({ path: path.join(shots, "window-1440.png") });

    // Scroll down, open a folder: the contents start at the top, nothing else moves or is rebuilt.
    await rows.evaluate((b) => { b.scrollTop = b.scrollHeight; });
    const deep = await rows.evaluate((b) => b.scrollTop);
    assert(deep > 200);
    await page.evaluate(() => { window.__shift = 0; new PerformanceObserver((l) => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__shift += e.value; }).observe({ type: "layout-shift", buffered: false }); });
    await open("klasor-60");
    await tile("alt").waitFor();
    assert.equal(await crumb(), "klasor-60");
    assert.equal(await rows.evaluate((b) => b.scrollTop), 0, "an opened folder starts at its top");
    assert(await sameNodes(), "opening a folder rebuilt the frame");
    const opened = await frame();
    for (const k of ["side", "title", "panel", "page"]) assert.deepEqual(opened[k], first[k], `${k} moved when the folder opened`);
    // The places column stays put; it may grow by the opened folder's entry when that is past the first eight (DD-237).
    assert.deepEqual(opened.rail.slice(0, 3), first.rail.slice(0, 3), "the places column moved when the folder opened");
    // DD-237: the folder is in the address (a history entry, no reload).
    assert.equal(new URL(page.url()).hash, "#/dosyalar/klasor/klasor-60");
    assert(await page.evaluate(() => window.__shift) < 0.01, "layout shift while opening a folder");
    assert.equal(await page.locator("#fs-back").isDisabled(), false);
    assert(await page.locator("#fs-fwd").isDisabled());

    // DD-237: the details sit in a fixed panel under the contents; selecting never changes its height.
    const panelBox = () => page.evaluate(() => { const d = document.querySelector("#fs-detail").getBoundingClientRect(), r = document.querySelector("#fs-rows").getBoundingClientRect(); return { top: Math.round(d.top), h: Math.round(d.height), rowsBottom: Math.round(r.bottom), left: Math.round(d.left), right: Math.round(r.right) }; });
    const emptyPanel = await panelBox();
    await tile("a.txt").click();
    const filePanel = await panelBox();
    assert.deepEqual(filePanel, emptyPanel, "selecting resized the detail panel or the contents");
    assert(filePanel.top >= filePanel.rowsBottom - 1, "the detail panel is under the contents");
    assert(await page.evaluate(() => !document.querySelector(".fx-side #fs-detail")), "the right column no longer holds the details");
    // DD-243: three independent panels with a small gap; the details are one fixed 82 px line.
    const split = await page.evaluate(() => { const r = (s) => document.querySelector(s).getBoundingClientRect();
      const body = r("#fs-body"), detail = r("#fs-detail"), side = r(".fx-side");
      return { gapBelow: Math.round(detail.top - body.bottom), gapSide: Math.round(side.left - Math.max(body.right, detail.right)), h: Math.round(detail.height),
        frame: getComputedStyle(document.querySelector("#fs-panel")).borderTopWidth, card: getComputedStyle(document.querySelector("#fs-body")).borderTopWidth };
    });
    assert(split.gapBelow >= 8 && split.gapBelow <= 14 && split.gapSide >= 8 && split.gapSide <= 16 && split.h === 82 && split.frame === "0px" && split.card === "1px",
      `separate panels: ${JSON.stringify(split)}`);
    await page.keyboard.press("Escape");
    // Back: at once from the cache, at the scroll position it was left at; read again behind the scenes.
    let release; hold[""] = new Promise((r) => { release = r; });
    await page.locator("#fs-back").click();
    await tile("klasor-60").waitFor();
    assert.equal(await crumb(), "/srv");
    assert.equal(await rows.evaluate((b) => b.scrollTop), deep, "back restores the folder's scroll");
    assert.equal(await loading(), false, "a cached folder shows without the loading state");
    delete hold[""]; release();
    await page.waitForFunction(() => true);
    assert(await page.locator("#fs-fwd").isEnabled());
    await page.locator("#fs-fwd").click();
    await tile("alt").waitFor();
    assert.equal(await crumb(), "klasor-60");

    // While a slow folder loads, the old listing stays dimmed and inert, and the path shows at once.
    await page.locator("#fs-up").click();
    await tile("yavas").waitFor();
    hold["yavas"] = new Promise((r) => { release = r; });
    await open("yavas");
    await page.waitForFunction(() => document.querySelector("#fs-panel").classList.contains("fx-loading"));
    assert.equal(await tile("klasor-01").count(), 1, "the old listing disappeared while loading");
    assert(await rows.evaluate((b) => b.inert));
    assert.equal(await crumb(), "yavas");
    await page.waitForFunction(() => getComputedStyle(document.querySelector("#fs-rows")).opacity === "0.55");
    await page.screenshot({ path: path.join(shots, "loading-1440.png") });
    // A newer click wins: the slow answer arriving later is dropped.
    await page.locator("#fs-home").click();
    await page.waitForFunction(() => !document.querySelector("#fs-panel").classList.contains("fx-loading"));
    delete hold["yavas"]; release();
    await page.waitForTimeout(200);
    assert.equal(await crumb(), "/srv", "a stale answer replaced the newer folder");
    assert.equal(await tile("gec.txt").count(), 0);

    // DD-237: Favoriler shows eight folders and a switch; the switch shows them all and back.
    const favs = () => page.locator("#fs-rail .rl").count();
    const fewer = await favs();
    await page.locator("#fs-rail .rl-more").click();
    assert.equal(await page.locator("#fs-rail .rl-more").innerText(), "Daha az göster");
    assert(await favs() > fewer + 50, "show all lists every top folder");
    await page.locator("#fs-rail .rl-more").click();
    assert.equal(await favs(), fewer);
    assert.match(await page.locator("#fs-rail .rl-more").innerText(), /^Tümünü göster \(62\)$/);
    // A folder that cannot be opened leaves you where you were.
    await rows.evaluate((b) => { b.scrollTop = 0; });
    await open("bozuk");
    await page.locator("#toast").getByText("bulunamadı (taşınmış ya da silinmiş olabilir)", { exact: true }).waitFor();
    assert.equal(await crumb(), "/srv", "a failed open must stay in the current folder");
    assert.equal(await tile("klasor-01").count(), 1);
    assert.equal(await loading(), false);
    assert.equal(await rows.evaluate((b) => b.inert), false);

    // Polling repaints nothing: the same tile node survives the ten-second state refresh.
    await page.evaluate(() => { window.__tile = document.querySelector('#fs-table [data-item="klasor-02"]'); });
    await page.clock.fastForward(11000);
    await page.waitForTimeout(100);
    assert(await page.evaluate(() => window.__tile.isConnected), "a poll rebuilt the listing");
    assert(await sameNodes());

    // Keyboard: arrows move, Enter opens, Backspace goes up, Alt+← / Alt+→ walk history, Ctrl+A selects all.
    await rows.focus();
    // Folders first, by name: bozuk, klasor-01 … klasor-60, yavas, then not.txt.
    await page.keyboard.press("ArrowRight");
    assert.equal(await page.locator("#fs-detail-title").innerText(), "bozuk");
    await page.keyboard.press("ArrowRight");
    assert.equal(await page.locator("#fs-detail-title").innerText(), "klasor-01");
    const cols = await page.locator("#fs-table").evaluate((t) => getComputedStyle(t).gridTemplateColumns.split(" ").length);
    await page.keyboard.press("ArrowDown");
    assert.equal(await page.locator("#fs-detail-title").innerText(), "klasor-" + String(1 + cols).padStart(2, "0"));
    await page.keyboard.press("ArrowUp");
    assert.equal(await page.locator("#fs-detail-title").innerText(), "klasor-01");
    await page.keyboard.press("Enter");
    await tile("bir.txt").waitFor();
    assert.equal(await crumb(), "klasor-01");
    await page.keyboard.press("Backspace");
    await tile("klasor-01").waitFor();
    assert.equal(await crumb(), "/srv");
    await page.keyboard.press("Alt+ArrowLeft");
    await tile("bir.txt").waitFor();
    await page.keyboard.press("Alt+ArrowRight");
    await tile("klasor-01").waitFor();
    await rows.focus();
    await page.keyboard.press("Control+a");
    assert.equal(await page.locator("#fs-detail-title").innerText(), "63 öge seçili");
    await page.keyboard.press("Escape");

    // The search box keeps its node and focus while typing; opening a folder clears it.
    await page.locator("#fs-q").fill("klasor-6");
    assert.equal(await page.locator("#fs-table [data-item]").count(), 1);
    await open("klasor-60");
    await tile("alt").waitFor();
    assert.equal(await page.locator("#fs-q").inputValue(), "");
    assert(await sameNodes());

    // DD-237: the address opens the folder after a reload; the browser's back/forward walk folders; a bad
    // address falls back to the root; bare #/dosyalar keeps the folder you are in.
    await page.reload();
    await tile("alt").waitFor();
    assert.equal(await crumb(), "klasor-60");
    await open("alt");
    await tile("derin.txt").waitFor();
    assert.equal(new URL(page.url()).hash, "#/dosyalar/klasor/klasor-60/alt");
    await page.goBack();
    await tile("a.txt").waitFor();
    assert.equal(await crumb(), "klasor-60");
    await page.goForward();
    await tile("derin.txt").waitFor();
    await page.evaluate(() => { location.hash = "#/dosyalar"; });
    await page.waitForFunction(() => location.hash === "#/dosyalar/klasor/klasor-60/alt");
    assert.equal(await crumb(), "alt");
    await page.evaluate(() => { location.hash = "#/dosyalar/klasor/%E0%A4%A"; });
    await tile("klasor-01").waitFor();
    assert.equal(await crumb(), "/srv", "an undecodable address opens the root");
    await page.evaluate(() => { location.hash = "#/dosyalar/klasor/klasor-60/alt"; });
    await tile("derin.txt").waitFor();
    await page.locator("#fs-up").click();
    await tile("alt").waitFor();
    // Leaving Files gives the page its scroll back; phones keep the page scroll.
    await page.evaluate(() => { location.hash = "#/moduller"; });
    await page.waitForFunction(() => !document.documentElement.classList.contains("fx-fixed"));
    await page.evaluate(() => { location.hash = "#/dosyalar"; });
    await page.waitForFunction(() => document.documentElement.classList.contains("fx-fixed"));
    for (const [width, theme] of [[1024, "light"], [390, "dark"]]) {
      await page.emulateMedia({ colorScheme: theme });
      await page.setViewportSize({ width, height: 800 });
      await page.waitForFunction(() => !document.documentElement.classList.contains("fx-fixed"));
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `overflow ${width}`);
      await page.locator("#fs-up").click();
      await tile("klasor-60").waitFor();
      assert(await page.evaluate(() => document.documentElement.scrollHeight > innerHeight), `the page scrolls at ${width}`);
      await page.screenshot({ path: path.join(shots, `page-${theme}-${width}.png`) });
      await open("klasor-60");
      await tile("alt").waitFor();
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.waitForFunction(() => document.documentElement.classList.contains("fx-fixed"));
    assert.deepEqual((await frame()).page, [0, true]);
    assert(reads.filter((r) => r === "klasor-60").length >= 2, "cached folders are read again");
    assert.deepEqual(errors, []);
    console.log("PASS: fixed window, frame never rebuilt, no layout shift, scroll reset/restore, back/forward, cache with revalidation, dimmed inert loading, stale answer dropped, failed open stays, quiet polling, keyboard, search, phone page scroll. Screenshots: " + shots);
  } finally { await browser.close(); }
})().catch((e) => { console.error(e); process.exit(1); });
