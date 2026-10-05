/* Model A disposable-host browser acceptance. ZIP writes only inside ARCHIVE_FIXTURE.
   Optional app lifecycle is explicitly enabled with TEST_APP_LIFECYCLE=1.
   DD-194: pass a session as KONSOL_COOKIE (sudo master-konsol oturum-ac); it is never printed. */
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs"), path = require("node:path"), os = require("node:os");
const screenshots = fs.mkdtempSync(path.join(os.tmpdir(), "konsol-v130-live-"));
const fixture = process.env.ARCHIVE_FIXTURE;
assert(/^archive-test-[a-f0-9]+$/.test(fixture || ""), "Pass the owned live archive fixture name");
(async () => {
  const browser = await chromium.launch({headless:true, ...(process.env.PLAYWRIGHT_CHROMIUM ? {executablePath:process.env.PLAYWRIGHT_CHROMIUM} : {})});
  try {
    const base = process.env.KONSOL_URL || "http://panel.ayc/";
    const context = await browser.newContext({viewport:{width:1440,height:1000}});
    if (process.env.KONSOL_COOKIE) await context.addCookies([{name:"konsol_oturum", value:process.env.KONSOL_COOKIE, url:base}]);
    const page = await context.newPage();
    const errors = [];
    const go = async name => {
      if (await page.locator("#menu-toggle").isVisible() && await page.locator("#menu-toggle").getAttribute("aria-expanded") !== "true") await page.locator("#menu-toggle").click();
      const link = page.locator(".nav").getByRole("link",{name,exact:true}), hash = await link.getAttribute("href");
      await link.click();
      await page.waitForURL(url => url.hash === hash || url.hash.startsWith(hash + "/"));
      await page.waitForFunction(() => document.querySelector('#menu-toggle').getAttribute('aria-expanded') === 'false');
    };
    page.on("pageerror", e => errors.push(e.message));
    await page.goto(base);
    await page.getByRole("heading", {name:"Dosyalar", exact:true}).waitFor();
    await page.getByRole("button", {name:fixture + " ayrıntıları", exact:true}).click();
    await page.getByRole("button", {name:"Klasörü aç", exact:true}).click();
    const selectFixture = async () => {
      await page.getByRole("button",{name:"Hedef klasör seç",exact:true}).click();
      await page.locator("#archive-picker").getByRole("button",{name:"Sunucu",exact:true}).click();
      await page.locator("#archive-picker").getByRole("button",{name:fixture,exact:true}).click();
      await page.getByRole("button",{name:"Bu klasörü seç",exact:true}).click();
      assert.equal(await page.locator("#archive-target").textContent(),"/srv/"+fixture);
    };
    await page.getByRole("checkbox", {name:"source seç", exact:true}).click();
    await page.screenshot({path:path.join(screenshots,"dock-desktop.png"),fullPage:true});
    await page.locator("#fs-dock").getByRole("button", {name:"Arşiv oluştur", exact:true}).click();
    assert.equal(await page.locator("#archive-target").textContent(),"/srv/downloads");
    await selectFixture();
    await page.locator("#archive-name").fill("../outside");
    await page.locator("#sh").getByRole("button", {name:"Oluştur", exact:true}).click();
    await page.locator("#sh [role=alert]").waitFor();
    await page.locator("#archive-name").fill("browser");
    await page.locator("#sh").getByRole("button", {name:"Oluştur", exact:true}).click();
    await page.waitForFunction(() => !document.querySelector("#sh").open);
    // DD-183: no jobs page; the running-job bar goes away and the list (the destination) refreshes.
    await page.locator("#archive-bar").getByText("browser.zip",{exact:true}).waitFor();
    await page.locator("#archive-bar").waitFor({state:"hidden", timeout:60000});
    await page.getByRole("button", {name:"browser.zip ayrıntıları", exact:true}).click();
    await page.locator("#fs-detail").getByRole("button", {name:"Arşiv açıcı", exact:true}).click();
    assert.equal(await page.locator("#archive-nested,#archive-layers").count(), 0);
    assert.equal(await page.locator("#archive-target").textContent(),"/srv/downloads");
    await selectFixture();
    await page.locator("#archive-name").fill("browser-expanded");
    await page.screenshot({path:path.join(screenshots,"archive-dialog.png"),fullPage:true});
    await page.locator("#sh").getByRole("button", {name:"Arşivi aç", exact:true}).click();
    await page.locator("#archive-bar").waitFor({state:"hidden", timeout:60000});
    await page.getByRole("button", {name:"browser-expanded ayrıntıları", exact:true}).waitFor();
    await page.waitForURL("**/#/dosyalar");
    await page.screenshot({path:path.join(screenshots,"files-desktop.png"),fullPage:true});
    await page.locator("#fs-tabs").getByRole("button", {name:"Paylaşımlar", exact:true}).click();
    await page.locator(".dav-shares").waitFor();
    assert.equal(await page.locator('.desktop-dock,#window-min,[data-view="genel"],[data-view="uygulamalar"]').count(),0);
    await page.waitForFunction(() => document.querySelector("#resource-cpu").textContent.startsWith("%"));
    assert(await page.locator("#resource-mem").isVisible());
    assert(await page.locator("#resource-disk").isVisible());
    await go("App Store");
    await page.locator("#modc-torrent").waitFor();
    assert.equal(await page.locator("#modc-paylasim,#modc-dosya").count(),0);
    assert.equal(await page.locator("#mod-grid > article").count(),2);
    if (process.env.TEST_APP_LIFECYCLE === "1") {
      const card = page.locator("#modc-torrent");
      await card.getByRole("button", {name:"Kur",exact:true}).click();
      await card.getByRole("button", {name:"Ayrıntı",exact:true}).click();
      const detail = page.locator("#mod-detail");
      await detail.getByRole("button", {name:"Kaldır",exact:true}).waitFor({timeout:180000});
      await detail.getByRole("button", {name:"Durdur",exact:true}).click();
      await page.locator("#cf-go").click();
      await detail.getByRole("button", {name:"Başlat",exact:true}).waitFor({timeout:60000});
      await detail.getByRole("button", {name:"Başlat",exact:true}).click();
      await detail.getByRole("button", {name:"Durdur",exact:true}).waitFor({timeout:60000});
      await page.screenshot({path:path.join(screenshots,"store-installed.png"),fullPage:true});
      await detail.getByRole("button", {name:"Kaldır",exact:true}).click();
      assert.equal(await page.locator("#mod-veri").isChecked(),false);
      await page.locator("#cf-go").click();
      await card.getByRole("button", {name:"Kur",exact:true}).waitFor({timeout:60000});
      console.log("PASS: real App Store qBittorrent install/stop/start/remove; profile retained.");
    }
    for (const width of [1440,1024,736,390,320]) {
      await page.setViewportSize({width,height:950});
      for (const app of ["Dosyalar","App Store","Ayarlar"]) {
        await go(app);
        if (app === "Ayarlar") {
          for (const name of ["Sistem","Güvenlik Duvarı","Caddy","Dnsmasq","Günlük"]) {
            await page.getByRole("tab", {name,exact:true}).click();
            assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `${width}/${app}/${name}`);
          }
        } else assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `${width}/${app}`);
      }
    }
    await page.emulateMedia({colorScheme:"dark"});
    await go("Dosyalar");
    await page.screenshot({path:path.join(screenshots,"files-mobile-dark.png"),fullPage:true});
    assert.deepEqual(errors,[]);
    console.log("PASS: real Model A sidebar/resources, ZIP create/unzip/error recovery, shares, protected builtins, settings, 5 widths. Screenshots: " + screenshots);
  } finally { await browser.close(); }
})().catch(err => {console.error(err); process.exit(1);});
