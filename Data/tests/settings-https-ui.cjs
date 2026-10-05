/* Production Settings/Shares UI with intercepted APIs; no live mutations.
   DD-193: public WebDAV HTTPS is edited only in the Settings → Caddy address table. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs"), path = require("node:path"), os = require("node:os");
const shots = fs.mkdtempSync(path.join(os.tmpdir(), "konsol-https-ui-"));
const data = {
  read_at: 1790790000, version: "fixture", domain: "ayc", tailscale: "100.64.0.2", ts_if: "tailscale0",
  wan: { iface: "eth0", ipv4: "192.0.2.1" },
  firewall: { ok: true, ports: [], listeners: [], rules: { rows: [], errors: [] } },
  web: { entries: [{ address: "panel.ayc", source: "base", access: "tailscale", routes: [] },
    { address: "192.0.2.1:61010", source: "paylasim-wan", access: "wan", routes: [] }], raw: [] },
  dns: { listen: ["lo", "tailscale0"] }, torrent: { installed: false },
  manage: { revision: "r1", pending: null, config: { firewall: [], dns: { disabled: [], records: [], forward: false, servers: [] } },
    names: [{ name: "panel.ayc", target: "tailscale", source: "base" }, { name: "paylas.ayc", target: "tailscale", source: "paylasim" }],
    // Unconfigured host: legacy consented HTTP on SHARE_PORT, the HTTPS port is still 443.
    https: { domain: "", mode: "http", scheme: "http", port: 61010, https_port: 443, status: "http",
      message: "HTTPS alan adı tanımlanmadı. Mevcut WAN paylaşımları HTTP kullanıyor.", expires: null, wan_ip: "192.0.2.1" },
    publications: [
      { service: "panel", name: "Panel", local: "panel.ayc", tail: true, enabled: false, domain: "", installed: true, running: true, account: true, status: "disabled", message: "İnternet yayını kapalı. Tailscale adresi her zaman açık kalır." },
      { service: "torrent", name: "qBittorrent", local: "torrent.ayc", tail: true, enabled: false, domain: "", installed: false, running: false, status: "disabled", message: "İnternet yayını kapalı." },
      { service: "paylasim", name: "WebDAV", local: "paylas.ayc", tail: true, enabled: true, domain: "", installed: true, running: true, status: "http", mode: "http",
        wan_active: false, message: "HTTPS alan adı tanımlanmadı. Mevcut WAN paylaşımları HTTP kullanıyor.", expires: null }] },
};
const dav = () => data.manage.publications.find(r => r.service === "paylasim");
const share = {id:"a".repeat(24),name:"media",path:"media",username:"fixture-user",available:true,
  connections:{tailscale:{enabled:true,permission:"ro",expires:null},wan:{enabled:false,permission:"ro",expires:null}}};
const shares = {enabled:true,running:true,tail_enabled:true,max:32,host:"http://100.64.0.2:61010",items:[share],
  wan:{available:true,address:"192.0.2.1",port:61010,reason:""}};
function projectShares() {
  share.urls = {};
  for (const scope of ["tailscale","wan"]) {
    const c = share.connections[scope];
    c.expired = false;
    c.available = scope === "tailscale" ? shares.tail_enabled : shares.wan.available;
    c.active = c.enabled && c.available && share.available;
    c.reason = c.available ? "" : scope === "wan" ? shares.wan.reason : "Tailscale yayını kapalı.";
    c.url = c.available ? (scope === "tailscale" ? shares.host : shares.wan.mode === "https" ? "https://"+shares.wan.domain : "http://"+shares.wan.address+":"+shares.wan.port)+"/s/"+share.id+"/" : "";
    if (c.active) share.urls[scope] = c.url;
  }
  share.url = share.urls.tailscale || share.urls.wan || "";
  return shares;
}
const applies = [], shareWrites = [], endpoints = [], errors = [];
let holdApply = false, releaseApply, failApply = "", incompleteApply = false;
// Mirrors master_publications.status(): enabled=false keeps the name, mode becomes off.
function setHttps(domain, status = "ready", enabled = !!domain) {
  const on = enabled && !!domain;
  data.manage.https = { domain: on ? domain : "", mode: on ? "https" : "off", scheme: on ? "https" : "", port: 443, https_port: 443,
    status: on ? status : "disabled", message: on ? "Sertifika doğrulandı." : "İnternet paylaşımı kapalı.", expires: on ? 1798000000 : null, wan_ip: "192.0.2.2" };
  Object.assign(dav(), { enabled, domain, status: data.manage.https.status, mode: data.manage.https.mode,
    message: data.manage.https.message, expires: data.manage.https.expires });
  shares.wan = { available: on && status === "ready", scheme: on ? "https" : "", mode: on ? "https" : "off", domain: on ? domain : "", port: 443,
    reason: on ? "" : "İnternet paylaşımı kapalı. Ayarlar → Caddy bölümünde HTTPS alan adı kaydedin." };
  projectShares();
  data.web.entries = data.web.entries.filter(e => e.access !== "wan");
  if (on) data.web.entries.push({ address: domain + ":443", source: "paylasim-wan", access: "wan", scheme: "https", routes: [] });
}
(async () => {
  const browser = await chromium.launch({ headless: true, ...(process.env.PLAYWRIGHT_CHROMIUM ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM } : {}) });
  try {
    const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
    page.on("pageerror", e => errors.push(e.message));
    page.on("console", m => { if (/Content Security Policy|Refused to|not a valid regular expression/.test(m.text())) errors.push(m.text()); });
    const csp = fs.readFileSync(path.join(__dirname, "../templates/Caddyfile"), "utf8").match(/Content-Security-Policy "([^"]+)"/)[1];
    await page.route("**/*", async route => {
      if (route.request().resourceType() !== "document") return route.continue();
      const response = await route.fetch();
      await route.fulfill({ response, headers: { ...response.headers(), "content-security-policy": csp } });
    });
    await page.route("**/api/**", async route => {
      const endpoint = new URL(route.request().url()).pathname;
      endpoints.push(endpoint);
      let result = {};
      if (endpoint === "/api/konsol/ayarlar") result = data;
      else if (endpoint === "/api/konsol/ayarlar/durum") result = data.manage;
      else if (endpoint === "/api/konsol/ayarlar/uygula") {
        const body = route.request().postDataJSON(); applies.push(body);
        assert.equal(body.revision, data.manage.revision);
        if (holdApply) await new Promise(resolve => { releaseApply = resolve; });
        if (failApply) {
          const error = failApply; failApply = "";
          return route.fulfill({ status: 400, contentType: "application/json", body: JSON.stringify({ error }) });
        }
        if (incompleteApply) { incompleteApply = false; result = { pending: null }; }
        else if (body.web) {
          assert.deepEqual(Object.keys(body).sort(), ["revision", "web"]);
          assert.equal(body.web.service, "paylasim");
          assert.deepEqual(Object.keys(body.web).sort(), ["domain", "enabled", "service", "tail"]);
          setHttps(body.web.domain, "ready", body.web.enabled); data.manage.revision += "-web";
          result = { committed: true, pending: null };
        } else if (body.domain) {
          assert.deepEqual(Object.keys(body).sort(), ["domain", "revision"]);
          data.manage.pending = { id: "domain-change", phase: "awaiting", seconds: 300, domain: { old: "ayc", new: body.domain } };
          result = { pending: data.manage.pending };
        } else throw new Error("Unexpected settings payload");
      } else if (endpoint === "/api/konsol/ayarlar/geri-al") { data.manage.pending = null; result = { ok: true }; }
      else if (endpoint === "/api/konsol/paylasim") result = projectShares();
      else if (endpoint === "/api/konsol/paylasim/kaydet") {
        const body = route.request().postDataJSON(); shareWrites.push(body);
        for (const key of ["networks","permission","expires","paused","days","ack_write"]) assert.equal(body[key],undefined);
        if ("username" in body) share.username = body.username;
        for (const [scope,patch] of Object.entries(body.connections || {})) Object.assign(share.connections[scope],patch);
        result = projectShares();
      } else if (endpoint === "/api/konsol/moduller" || endpoint === "/api/konsol/islemler" || endpoint === "/api/archives") result = { items: [] };
      else if (endpoint === "/api/konsol/oturum") result = { durum: "giris", kullanici: "fixture", kanal: "tailscale" };  // DD-205
      else if (endpoint === "/api/konsol/kaynaklar") result = { host: "fixture", version: "fixture", domain: "ayc", os: "Debian 13", kernel: "fixture", uptime: 100,
        cores: 2, cpu: [1], mem: { total: 1000, used: 200, graph: [20] }, net: { wan: data.wan.ipv4, tailscale: data.tailscale }, root: "/srv", disk: { total: 1000, free: 800 }, ports: [] };
      else if (endpoint === "/api/state") result = { root: "/srv", downloads: "downloads", disk: { total: 1000, free: 800 }, trash: { count: 0, size: 0 } };
      else if (endpoint === "/api/list") result = { path: "", entries: [] };
      else throw new Error("Unexpected endpoint " + endpoint);
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(result) });
    });
    const url = process.env.KONSOL_URL || "http://127.0.0.1:8766";
    await page.goto(url + "/#/ayarlar/web");
    const table = page.locator("#as-publications"), row = table.locator('[data-publication="paylasim"]');
    const input = row.getByRole("textbox", { name: "WebDAV HTTPS alan adı", exact: true });
    const wanSwitch = row.getByRole("switch", { name: "WebDAV internet erişimi", exact: true });
    const save = row.getByRole("button", { name: "Kaydet", exact: true });
    const local = page.getByRole("textbox", { name: "Yerel alan adı", exact: true });
    const settled = () => page.waitForFunction(() => document.querySelector("#as-publications")?.getAttribute("aria-busy") === "false");
    const refresh = async () => {
      const response = page.waitForResponse(r => r.url().includes("/api/konsol/ayarlar?yenile=1"));
      await page.getByRole("button", { name: "Yenile", exact: true }).click();
      await response; await settled();
    };
    assert.equal(await page.locator("#as-https-card").count(), 0, "The table is the only public-HTTPS editor");
    await row.getByText("Eski HTTP erişimi", { exact: true }).waitFor();
    assert.equal(await local.inputValue(), "ayc");
    assert.equal(await input.inputValue(), "");
    assert.equal(await wanSwitch.getAttribute("aria-checked"), "true");
    assert.match(await table.innerText(), /192\.0\.2\.1/);
    assert.match(await table.innerText(), /DNS only/);
    assert.match(await table.innerText(), /HTTPS TCP 443\b/, "Legacy HTTP shows the configured HTTPS port, not SHARE_PORT");
    // v2-180: a ready Panel (or application) name is shown on the HTTPS port even while WebDAV is still on legacy HTTP,
    // whose own port (manage.https.port = SHARE_PORT) once leaked into the link as https://panel.example.net:61010.
    const panelRow = data.manage.publications.find(r => r.service === "panel"), panelSaved = { ...panelRow };
    Object.assign(panelRow, { enabled: true, domain: "panel.example.net", status: "ready", message: "Sertifika doğrulandı.", expires: 1798000000 });
    await refresh();
    assert.equal(await table.locator('[data-publication="panel"] a[href^="https://"]').getAttribute("href"), "https://panel.example.net", "Panel link carries no WebDAV port");
    assert.doesNotMatch(await table.innerText(), /:61010/, "SHARE_PORT never appears in a public HTTPS address");
    Object.assign(panelRow, panelSaved);
    await refresh();
    // v2-169: nothing is shared over plaintext HTTP yet, so only the plain note shows and nothing blocks HTTPS rows.
    assert.match(await table.innerText(), /internet paylaşımı açılırsa eski HTTP kullanılır/);
    assert.doesNotMatch(await table.innerText(), /Eski WebDAV WAN erişimi HTTP kullanıyor/);
    dav().wan_active = true; await refresh();
    assert.match(await table.innerText(), /Eski WebDAV WAN erişimi HTTP kullanıyor/);
    assert.equal(await row.locator(".good").count(), 0);
    await page.locator(".as-web-details > summary").click();
    assert.match(await page.locator("#cfg-web").innerText(), /WAN · HTTP/);
    assert.match(await page.locator("#cfg-web").innerText(), /HTTP parola ve dosyaları şifrelemez/);
    // An unchanged empty name cannot be saved; every malformed name stays in the browser.
    assert(await save.isDisabled());
    for (const invalid of ["https://dav.example.com", "dav.example.com/path", "dav.example.com:443", "user@dav.example.com", "*.example.com", "127.0.0.1", "ayc", "-dav.example.com", "a".repeat(64) + ".example.com"]) {
      await input.fill(invalid); await save.click();
      assert.equal(applies.length, 0, invalid);
      assert.equal(await input.evaluate(el => el.checkValidity()), false, invalid);
    }
    // DNS drafts and the independent publication draft survive navigation; writes remain separate.
    await input.fill("dav.example.com");
    await page.getByRole("tab", { name: "Dnsmasq", exact: true }).click();
    await page.getByRole("switch", { name: "paylas.ayc", exact: true }).click();
    await page.getByRole("tab", { name: "Caddy", exact: true }).click();
    assert.equal(await input.inputValue(), "dav.example.com"); assert(await save.isDisabled());
    assert(await page.getByRole("button", { name: "Güncelle", exact: true }).isDisabled());
    await page.locator(".as-footer").getByRole("button", { name: "Vazgeç", exact: true }).click();
    await input.fill(" DAV.Example.COM ");
    // Hold the request and advance browser time past the certificate provisioning interval.
    await page.clock.install(); holdApply = true;
    await save.click();
    await row.getByText("Uygulanıyor…", { exact: true }).waitFor();
    await page.waitForFunction(() => document.querySelector("#as-publications")?.getAttribute("aria-busy") === "true");
    assert(await input.isDisabled()); assert(await local.isDisabled()); assert(await save.isDisabled());
    await save.click({ force: true });
    await page.clock.fastForward(75000);
    assert.equal(applies.length, 1, "One POST despite a repeated click and 75 seconds of provisioning");
    assert.deepEqual(applies[0], { revision: "r1", web: { service: "paylasim", tail: true, enabled: true, domain: "dav.example.com" } });
    assert.equal(await page.locator("dialog[open], .as-rollback, .as-domain-links").count(), 0);
    assert.equal(typeof releaseApply, "function"); holdApply = false; releaseApply(); await settled();
    await row.getByText("Sertifika hazır", { exact: true }).waitFor();
    assert.equal(await row.locator(".good").count(), 1);
    assert.equal(await row.locator("time").getAttribute("datetime"), new Date(1798000000 * 1000).toISOString());
    assert.match(await row.innerText(), /https:\/\/dav\.example\.com\/s\/…\//);
    assert.match(await table.innerText(), /internetten erişimin test edildiği anlamına gelmez/);
    assert.doesNotMatch(await table.innerText(), /Eski WebDAV WAN erişimi HTTP/);
    await page.locator(".as-web-details > summary").click();
    assert.match(await page.locator("#cfg-web").innerText(), /WAN · HTTPS/);
    assert(!/HTTP şifrelemez|HTTP parola/.test(await page.locator("#cfg-web").innerText()));
    assert.equal(await local.inputValue(), "ayc");
    assert(await save.isDisabled(), "An unchanged ready certificate is not reprovisioned");
    // Request failures retain the edited domain and show the actual certificate state on refresh.
    await input.fill("next.example.com"); failApply = "DNS A kaydı beklenen WAN adresiyle eşleşmiyor.";
    await save.click(); await settled();
    assert.match(await page.locator(".as-message").innerText(), /DNS A kaydı/);
    assert.equal(await input.inputValue(), "next.example.com");
    assert.equal(dav().domain, "dav.example.com");
    assert.equal(await page.locator(".as-rollback, .as-domain-links").count(), 0);
    incompleteApply = true; await save.click(); await settled();
    assert.match(await page.locator(".as-message").innerText(), /kalıcı kaydı doğrulamadı/);
    await save.click(); await settled();
    assert.equal(dav().domain, "next.example.com");
    // A pending certificate from a fresh response is not a local-domain rollback transaction.
    setHttps("next.example.com", "pending"); dav().expires = null; dav().message = "Sertifika bekleniyor.";
    data.manage.pending = { id: "web-change", phase: "applying", seconds: 150, web: true };
    await page.getByRole("button", { name: "Yenile", exact: true }).click();
    await row.getByText("Sertifika bekleniyor.", { exact: true }).waitFor();
    await row.getByText("Sertifika hazırlanıyor…", { exact: true }).waitFor();
    assert(await input.isDisabled()); assert.equal(await row.locator(".good, time").count(), 0);
    assert.equal(await page.locator(".as-rollback").count(), 0);
    await page.reload(); await row.getByText("Sertifika bekleniyor.", { exact: true }).waitFor();
    assert.equal(await page.locator(".as-rollback, .as-domain-links").count(), 0);
    assert(await input.isDisabled());
    data.manage.pending = null;
    setHttps("next.example.com", "error"); dav().expires = null;
    dav().message = "Sertifika alınamadı: <img src=x onerror=alert(1)>";
    await refresh();
    await row.getByText(dav().message, { exact: true }).waitFor();
    assert.equal(await row.locator("img, .good").count(), 0); assert(!(await save.isDisabled()), "An error row can be retried");
    setHttps("next.example.com"); await refresh();
    await page.clock.fastForward(5000);
    for (const colorScheme of ["light", "dark"]) {
      await page.emulateMedia({ colorScheme });
      for (const width of [1400, 736, 390, 320]) {
        await page.setViewportSize({ width, height: 1000 });
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `${colorScheme}/${width}`);
        await page.screenshot({ path: path.join(shots, `https-${colorScheme}-${width}.png`), fullPage: true });
      }
    }
    await page.setViewportSize({ width: 1400, height: 1000 });
    // Turning the internet switch off is a draft; Save closes WAN and remembers the name.
    await wanSwitch.click(); const beforeRemoval = applies.length;
    assert.equal(applies.length, beforeRemoval);
    await row.getByRole("button", { name: "Vazgeç", exact: true }).click();
    assert.equal(await wanSwitch.getAttribute("aria-checked"), "true");
    await wanSwitch.click(); failApply = "WAN kapatma sınama hatası.";
    await save.click(); await settled();
    assert.equal(data.manage.https.mode, "https"); assert.match(await page.locator(".as-message").innerText(), /WAN kapatma sınama hatası/);
    await save.click(); await settled();
    assert.deepEqual(applies.at(-1).web, { service: "paylasim", tail: true, enabled: false, domain: "next.example.com" });
    await row.getByText("İnternet kapalı", { exact: true }).waitFor();
    assert.equal(await input.inputValue(), "next.example.com", "The disabled public name is remembered");
    assert.equal(await row.locator(".good, time").count(), 0);
    await page.reload(); await row.getByText("İnternet kapalı", { exact: true }).waitFor();
    assert(!/Eski HTTP erişimi/.test(await table.innerText()));
    // Original local-domain validation, confirmation and new-host-only approval remain intact.
    await local.fill("bad.example"); assert.equal(await local.evaluate(el => el.checkValidity()), false);
    await local.fill("ev"); await page.getByRole("button", { name: "Güncelle", exact: true }).click();
    const dialog = page.locator("dialog.as-dialog");
    assert.match(await dialog.innerText(), /Restrict to domain/);
    assert.match(await dialog.innerText(), /5 dakika/);
    await dialog.getByRole("button", { name: "Alan adını güncelle", exact: true }).click();
    await page.locator(".as-rollback").waitFor();
    assert.deepEqual(Object.keys(applies.at(-1)).sort(), ["domain", "revision"]);
    assert(await page.getByRole("button", { name: "Bağlantı çalışıyor · onayla", exact: true }).isDisabled());
    assert.equal(await page.getByRole("link", { name: "Yeni Konsol'u aç: panel.ev", exact: true }).getAttribute("href"), "http://panel.ev/#/ayarlar");
    assert(await row.getByRole("switch", { name: "WebDAV internet erişimi", exact: true }).isDisabled());
    await page.getByRole("button", { name: "Geri al", exact: true }).click();
    await page.waitForFunction(() => !document.querySelector(".as-rollback"));
    // Shared-account management has no network fields; switches send independent patches.
    setHttps("dav.example.com");
    await page.goto(url + "/#/dosyalar/paylasim");
    await page.getByRole("button",{name:"Yönet",exact:true}).click();
    const username = page.locator("#dav-user");
    await username.fill("invalid user"); assert.equal(await username.evaluate(el=>el.checkValidity()),false);
    await username.fill("fixture-user"); assert(await username.evaluate(el=>el.checkValidity()));
    assert.equal(await page.locator("#sh select, #sh [role=switch], #sh input[type=checkbox]").count(),0);
    await page.getByRole("button",{name:"Güncelle",exact:true}).click();
    await page.waitForFunction(()=>!document.querySelector("#sh").open);
    assert.equal(shareWrites.length,0);
    const tail = page.locator('.dav-connection[data-network="tailscale"]');
    const pair = page.locator('.dav-connection[data-network="wan"]');
    const settledShare = () => page.waitForFunction(()=>document.querySelector(".dav-shares")?.getAttribute("aria-busy")==="false");
    assert.equal(await tail.getByRole("switch").getAttribute("aria-checked"),"true");
    assert.equal(await pair.getByRole("switch").getAttribute("aria-checked"),"false");
    assert.equal(await pair.locator(".dav-address code").textContent(),"https://dav.example.com/s/"+share.id+"/","Disabled candidate URL is available");
    await pair.getByRole("switch").click(); await settledShare();
    assert.deepEqual(shareWrites.at(-1),{id:share.id,connections:{wan:{enabled:true}}});
    assert.equal(await page.locator("#cf[open]").count(),0,"HTTPS needs no plaintext consent");
    await pair.getByText("HTTPS",{exact:true}).waitFor();
    assert.deepEqual(await pair.locator(".dav-infuse dd").allTextContents(),["dav.example.com","443","/s/"+share.id+"/"]);
    await page.locator(".dav-boundary summary").click();
    assert(!/WAN üzerinden HTTP,/.test(await page.locator(".dav-boundary").innerText()));
    await page.screenshot({path:path.join(shots,"shares-https-mobile.png"),fullPage:true});
    setHttps(""); await page.reload(); await pair.waitFor();
    assert.match(await pair.innerText(),/İnternet paylaşımı kapalı/);
    assert.equal((await pair.locator("h3").textContent()).trim(),"WAN","A closed WAN card is neither HTTP nor HTTPS");
    assert.equal(await pair.locator(".dav-address").count(),0);
    assert.equal(await pair.getByRole("switch").getAttribute("aria-checked"),"true");
    assert(!(await pair.getByRole("switch").isDisabled()));
    await pair.getByRole("switch").click(); await settledShare();
    assert(await pair.getByRole("switch").isDisabled());
    // Explicit and implicit legacy HTTP both require activation consent.
    for (const explicit of [true,false]) {
      shares.wan = {available:true,address:"192.0.2.1",port:61010,reason:"",...(explicit?{scheme:"http",mode:"http",domain:""}:{})};
      await page.reload(); await pair.waitFor();
      await pair.getByText("HTTP (WAN)",{exact:true}).waitFor();
      const before = shareWrites.length;
      await pair.getByRole("switch").click();
      assert.match(await page.locator("#cf").innerText(),/parola ve verileri şifrelemeden/);
      assert.equal(shareWrites.length,before);
      await page.locator("#cf-cancel").click();
      assert.equal(shareWrites.length,before);
      await pair.getByRole("switch").click(); await page.locator("#cf-go").click(); await settledShare();
      assert.deepEqual(shareWrites.at(-1),{id:share.id,connections:{wan:{enabled:true}},ack_wan_http:true});
      await pair.getByRole("switch").click(); await settledShare();
      assert.deepEqual(shareWrites.at(-1),{id:share.id,connections:{wan:{enabled:false}}});
    }
    assert.deepEqual(errors, []);
    assert.equal(endpoints.filter(p => p.endsWith("/onayla")).length, 0);
    assert.equal(applies.filter(a => "https" in a).length, 0, "The browser never writes the legacy https key");
    assert.deepEqual(await page.evaluate(() => Object.keys(localStorage)), []);
    console.log("PASS: table-only public HTTPS editor, validation, isolated revision payload, 75-second busy/repeat guard, ready/pending/error/expiry, error retry, draft switch/discard/failure/off with remembered name, legacy-HTTP port note, local-domain regression, HTTPS/HTTP/off share cards and acknowledgements, production CSP, 4 widths/both themes. Screenshots: " + shots);
  } finally { await browser.close(); }
})().catch(err => { console.error(err); process.exit(1); });
