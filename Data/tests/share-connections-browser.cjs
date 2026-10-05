/* Read-only installed DD-192 UI acceptance; refuses every API mutation.
   DD-194: pass a session as KONSOL_COOKIE (sudo master-konsol oturum-ac); it is never printed. */
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs"), os = require("node:os"), path = require("node:path");
const shots = fs.mkdtempSync(path.join(os.tmpdir(), "share-connections-live-"));
(async () => {
  const browser = await chromium.launch({headless:true});
  try {
    const base = process.env.KONSOL_URL || "http://panel.ayc";
    const context = await browser.newContext({viewport:{width:1440,height:1050}});
    if (process.env.KONSOL_COOKIE) await context.addCookies([{name:"konsol_oturum", value:process.env.KONSOL_COOKIE, url:base}]);
    const page = await context.newPage();
    const errors = [], writes = [];
    page.on("pageerror", err => errors.push(err.message));
    await page.route("**/api/**", route => {
      if (!["GET", "HEAD"].includes(route.request().method())) {
        writes.push(route.request().method() + " " + route.request().url());
        return route.abort();
      }
      return route.continue();
    });
    await page.goto(base + "/#/dosyalar/paylasim");
    await page.locator(".dav-share-row").first().waitFor();
    assert(await page.locator(".dav-share-row").count() > 0, "Requires an existing share; creates none");
    for (const row of await page.locator(".dav-share-row").all()) {
      assert.equal(await row.locator(".dav-connection").count(), 2);
      assert.equal(await row.getByRole("switch").count(), 2);
      assert.equal(await row.getByRole("combobox").count(), 4);
      for (const scope of ["tailscale", "wan"]) {
        const card = row.locator('[data-network="' + scope + '"]');
        assert(await card.isVisible());
        const code = card.locator(".dav-address code");
        if (await code.count()) {
          const url = new URL(await code.textContent());
          const values = await card.locator(".dav-infuse dd").allTextContents();
          assert.deepEqual(values, [url.hostname, url.port || (url.protocol === "https:" ? "443" : "80"), url.pathname]);
          assert.equal(await card.locator(".dav-address button").count(), 1);
        }
      }
    }
    for (const theme of ["light", "dark"]) {
      await page.emulateMedia({colorScheme:theme, reducedMotion:"reduce"});
      for (const width of [1440, 900, 390]) {
        await page.setViewportSize({width,height:1050});
        const geometry = await page.evaluate(() => {
          const outside = [...document.querySelectorAll(".dav-share-row, .dav-connection, .dav-connection select")]
            .filter(el => {const b = el.getBoundingClientRect(); return b.left < -1 || b.right > innerWidth + 1 || el.scrollWidth > el.clientWidth + 2;})
            .map(el => el.tagName + "." + el.className);
          return {overflow:document.documentElement.scrollWidth > innerWidth + 1, outside};
        });
        assert.deepEqual(geometry,{overflow:false,outside:[]}, theme + " " + width);
        await page.screenshot({path:path.join(shots, theme + "-" + width + ".png"),fullPage:true});
      }
    }
    assert.deepEqual(errors,[]);
    assert.deepEqual(writes,[]);
    console.log(JSON.stringify({ok:true,widths:3,themes:2,writes:0,screenshots:shots}));
  } finally { await browser.close(); }
})().catch(err=>{console.error(err);process.exitCode=1;});
