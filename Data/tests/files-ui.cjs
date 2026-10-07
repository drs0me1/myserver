/* Production Files UI: independent account forms, navigation, list view, trash. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs"), path = require("node:path"), os = require("node:os");
const shots = fs.mkdtempSync(path.join(os.tmpdir(), "konsol-files-networks-"));
const csp = fs.readFileSync(path.join(__dirname, "../templates/Caddyfile"), "utf8").match(/Content-Security-Policy "([^"]+)"/)[1];
const wanStatus = {available:true,address:"192.0.2.1",port:61010,reason:""};
const shares = { enabled: true, running: true, tail_enabled: true, max: 32, host: "http://100.64.0.2:61010", wan:{...wanStatus}, items: [] };
function projectShares() {
  for (const s of shares.items) {
    s.urls = {};
    for (const scope of ["tailscale", "wan"]) {
      const c = s.connections[scope];
      c.expired = c.expires != null && c.expires <= Date.now()/1000;
      c.available = scope === "tailscale" ? shares.tail_enabled : shares.wan.available;
      c.active = c.enabled && !c.expired && s.available && c.available;
      c.reason = !c.available ? scope === "wan" ? shares.wan.reason : "Tailscale yayını kapalı."
        : !s.available ? "Klasör bulunamadı." : c.expired ? "Bağlantının süresi doldu." : "";
      c.url = c.available ? (scope === "tailscale" ? shares.host : shares.wan.scheme === "https"
        ? "https://" + shares.wan.domain + (shares.wan.port === 443 ? "" : ":" + shares.wan.port)
        : "http://" + shares.wan.address + ":" + shares.wan.port) + "/s/" + s.id + "/" : "";
      if (c.active) s.urls[scope] = c.url;
    }
    s.url = s.urls.tailscale || s.urls.wan || "";
  }
  return shares;
}
const trashFixtures = [
  {id:"trash-short",name:"notlar.txt",type:"file",from:"",size:1024,deleted:Date.now()/1000-300},
  {id:"trash-long",name:"Uzun.dosya.adı.".repeat(12)+"1080p.2026.zip",type:"file",from:"downloads/"+"çok-uzun-klasör/".repeat(12),size:7*1024**3,deleted:Date.now()/1000-3600},
  {id:"trash-unbroken",name:"x".repeat(251)+".zip",type:"file",from:"media/"+"y".repeat(255),size:2*1024**4,deleted:Date.now()/1000-86400},
  {id:"trash-folder",name:"Belgeler ve Türkçe klasör adı",type:"dir",from:"media/Belgeler",size:4096,deleted:Date.now()/1000-172800},
];
let trash = [], trashWrites = [];
// DD-235: the system view's fixture (root over /); every write is recorded, nothing is sent anywhere.
const sysWrites = [], sysReads = [];
let holdSys = null;  // a pending promise holds the system view's next folder listing
const sysEntries = { "": [["etc","dir"],["proc","dir"],["srv","dir"],["vmlinuz","file"]], etc: [["hosts","file"],["ssh","dir"]], "etc/ssh": [] };
let submitted, failShare = false, holdShare = false, releaseShare;
// DD-249: the editor's fixtures; every save is recorded and answered with the next version.
const textStart = "ad: nrm\nport: 22\n", textSaves = [], sysSaves = [];
let textNow = textStart, textVersion = "a".repeat(64), sysText = "127.0.0.1 localhost\n";
// DD-250: the root backend's favourites, kept in order like favoriler.json.
let favorites = [];
const favWrites = [];
const shareWrites = [], deleted = [], longFile = "x".repeat(251) + ".iso";
(async () => {
  const browser = await chromium.launch({ headless: true, ...(process.env.PLAYWRIGHT_CHROMIUM ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM } : {}) });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    await page.addInitScript(() => {
      window.copiedShareTexts = [];
      window.requestedDownloads = [];
      const click = HTMLAnchorElement.prototype.click;
      HTMLAnchorElement.prototype.click = function () {
        if (this.hasAttribute("download")) { window.requestedDownloads.push(this.href); return; }
        return click.call(this);
      };
      if (navigator.clipboard) navigator.clipboard.writeText = async text => { window.copiedShareTexts.push(text); };
      const original = document.execCommand.bind(document);
      document.execCommand = (command, ...args) => {
        if (command !== "copy") return original(command, ...args);
        window.copiedShareTexts.push(document.querySelector("textarea[aria-hidden=true]").value);
        return true;
      };
    });
    const checkShareAddress = async (locator, expected, rerenderDuringMeasurement = false) => {
      assert.equal(await locator.locator("code").textContent(), expected);
      assert(!/[^\x21-\x7e]/.test(expected), "share URL contains whitespace or non-ASCII characters");
      // Hash routing and the share response both rebuild the list. The element
      // resolved by evaluate can detach AFTER waitFor(visible), yielding all-zero
      // rectangles. Re-resolve only stale/hidden snapshots, never a real bad gap.
      let geometry;
      for (let attempt = 0; attempt < 5; attempt++) {
        await locator.waitFor({state:"visible"});
        geometry = await locator.evaluate((el, rerender) => {
          // Deterministically exercise replacement between resolution and reading.
          if (rerender) document.querySelector('#fs-rail [aria-current="true"]').click();
          const rect = node => { const r=node.getBoundingClientRect(); return {left:r.left,right:r.right,top:r.top,bottom:r.bottom}; };
          return {group:rect(el),text:rect(el.querySelector("code")),button:rect(el.querySelector("button")),
            rendered:el.isConnected && el.checkVisibility(), gap:getComputedStyle(el).columnGap};
        }, rerenderDuringMeasurement && attempt === 0);
        if (rerenderDuringMeasurement && attempt === 0) assert.equal(geometry.rendered,false,"Regression must replace the resolved address");
        if (geometry.rendered) break;
      }
      assert(geometry.rendered, "address must remain rendered for measurement: " + JSON.stringify(geometry));
      assert(Math.abs(geometry.button.left-geometry.text.right-6)<1, "copy button must directly follow address: " + JSON.stringify(geometry));
      assert(geometry.button.right<=geometry.group.right+1, "copy button outside address group");
      assert(geometry.text.left>=geometry.group.left-1, "address outside group");
      await locator.getByRole("button").click();
      assert.equal(await page.evaluate(() => window.copiedShareTexts.at(-1)),expected);
    };
    const checkShareAddresses = async (locator, share = shares.items[0]) => {
      await locator.waitFor({state:"visible"});
      assert.deepEqual(await locator.locator(".dav-connection").evaluateAll(nodes=>nodes.map(n=>n.dataset.network)),["tailscale","wan"]);
      for (const scope of ["tailscale","wan"]) {
        const card = locator.locator('.dav-connection[data-network="' + scope + '"]');
        const c = share.connections[scope];
        assert.equal(await card.locator("h3").textContent(),scope === "tailscale" ? "Tailscale" : shares.wan.scheme === "https" ? "HTTPS" : "HTTP (WAN)");
        if (!c.url) { assert.equal(await card.locator(".dav-address").count(),0); continue; }
        await checkShareAddress(card.locator(".dav-address"),c.url);
        const url = new URL(c.url);
        assert.deepEqual(await card.locator(".dav-infuse dd").allTextContents(),[url.hostname,url.port || (url.protocol === "https:" ? "443" : "80"),url.pathname]);
      }
    };
    // DD-244: the detail line names a shared folder's open connections (else its state); "Paylaşımı yönet" and
    // "Paylaşımı kaldır" are detail actions. Addresses, the account and copy buttons stay on Paylaşımlar.
    const checkShareSummary = async (locator, share = shares.items[0]) => {
      await locator.locator(".fx-shared").waitFor();
      const line = await locator.locator(".fx-line").innerText(), open = ["tailscale","wan"].filter(scope => share.connections[scope].active);
      if (open.length) {
        assert.match(line, /Paylaşılıyor: /);
        if (share.connections.tailscale.active) assert.match(line, /Tailscale \((\d+ gün|süresiz)\)/);
        assert.equal(await locator.locator(".fx-shared.on").count(), 1);
      } else assert.match(line, /Paylaşım: /);
      assert.equal(await locator.locator(".dav-address, .dav-connection, .fx-chip").count(), 0, "addresses stay on Paylaşımlar");
      assert(!line.includes(share.username), "the account stays on Paylaşımlar");
      for (const name of ["Paylaşımı yönet","Paylaşımı kaldır"]) assert.equal(await locator.getByRole("button",{name,exact:true}).count(), 1);
    };
    // DD-232: grid tiles select on click (a second click opens); the right column holds the actions.
    const tile = name => page.locator(`#fs-table [data-item="${name}"]`);
    const select = async name => { if (await tile(name).getAttribute("aria-pressed") !== "true") await tile(name).click(); };
    const act = key => page.locator(`#fs-detail [data-act="${key}"]`);
    const rail = title => page.locator("#fs-rail").getByTitle(title,{exact:true});
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("console", (m) => { if (/Content Security Policy|Refused to/.test(m.text())) errors.push(m.text()); });
    await page.route("**/*", async (route) => {
      if (route.request().resourceType() !== "document") return route.continue();
      const response = await route.fetch();
      await route.fulfill({response, headers:{...response.headers(), "content-security-policy":csp}});
    });
    await page.route("**/api/**", async (route) => {
      const req = route.request(), url = new URL(req.url()), p = url.pathname;
      let result;
      if (p === "/api/konsol/moduller") result = { items: ["wireguard", "torrent"].map((id) => ({ id, installed: false, state: "yok", runtime: id === "wireguard" ? "konsol" : "host", live: "-" })) };
      else if (p === "/api/archives") result = {items:[], limits:{bytes:2147483648,entries:10000,layers:5,seconds:900}};
      else if (p === "/api/konsol/oturum") result = { durum: "giris", kullanici: "fixture", kanal: "tailscale" };  // DD-205: tailnet, no sign-out
      else if (p === "/api/konsol/kaynaklar") result = { host: "nrm", version: "v128", domain: "ayc", os: "Debian 13", kernel: "test", uptime: 300, cores: 2, cpu: [1], mem: { total: 10000, used: 200, graph: [20] }, net: { wan: "192.0.2.1", tailscale: "100.64.0.2" }, root: "/srv", disk: { total: 100000, free: 80000 }, ports: [{ port: 22, proto: "tcp", scope: "internet", name: "SSH" }] };
      else if (p === "/api/konsol/islemler") result = { items: [] };
      else if (p === "/api/konsol/favoriler") {
        if (req.method() === "POST") {
          const data = req.postDataJSON(), [op, entry] = Object.entries(data)[0];
          favWrites.push(data);
          favorites = favorites.filter((f) => !(f.yol === entry.yol && f.sistem === entry.sistem));
          if (op === "ekle") favorites.push(entry);
        }
        result = { favoriler: favorites };
      }
      else if (p === "/api/state") result = { root: "/srv", downloads:"downloads", protected: [{ path: "downloads/incomplete", owner: "Deneme Uygulaması" }], disk: { total: 100000, free: 80000 }, trash: { count: 0, size: 0 } };
      else if (p === "/api/list") result = { path: url.searchParams.get("path") || "", entries: [
        // DD-247: "movies" was not walked (size null), "series" is empty.
        ...(url.searchParams.get("path") ? [["movies", 2, null], ["series", 0, 0]] : [["media", 2, 1024], ["downloads", 2, 1024], ["Belgeler ve uzun klasör adı", 2, 1024]])
          .map(([name, count, size]) => ({ name, type: "dir", count, size, mtime: Date.now() / 1000 })),
        ...(!url.searchParams.get("path") && !url.searchParams.get("dirs") ? [longFile,"sample.part02.rar"].map(name=>({name,type:"file",size:840*1024**2,mtime:Date.now()/1000})) : []),
        ...(url.searchParams.get("path") === "media" && !url.searchParams.get("dirs") ? [["ayar.yml", 17], ["buyuk.log", 3 * 1024 ** 2]].map(([name, size]) => ({ name, type: "file", size, mtime: Date.now() / 1000 })) : [])] };
      else if (p === "/api/text") {
        const at = url.searchParams.get("path"), big = at.endsWith("buyuk.log");
        result = { path: at, size: big ? 3 * 1024 ** 2 : textNow.length, mtime: Date.now() / 1000, truncated: big, detected: "utf-8", encoding: "utf-8",
          bom: false, eol: "lf", editable: !big, reason: big ? "dosya 1 MiB'tan büyük; yalnız ilk bölümü okunur" : "",
          version: big ? null : textVersion, text: big ? "satır\n".repeat(40) : textNow };
      } else if (p === "/api/text/save") {
        const data = req.postDataJSON(); textSaves.push(data);
        textNow = data.text; textVersion = "abcdef"[textSaves.length].repeat(64);
        result = { path: data.path, version: textVersion, size: data.text.length, mtime: Date.now() / 1000 };
      }
      else if (p.startsWith("/api/sistem/")) {
        sysReads.push(p + url.search);
        if (p === "/api/sistem/state") result = { root: "/", sistem: true, writable: true,
          disk: { total: 200000, free: 50000, used: null, mount: true }, textLimit: 1048576 };
        else if (p === "/api/sistem/list") {
          const at = url.searchParams.get("path") || "";
          if (at && holdSys) await holdSys;
          if (!sysEntries[at]) return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: "bulunamadı (taşınmış ya da silinmiş olabilir)" }) });
          result = { path: at, skipped: 0, entries: (sysEntries[at] || []).filter(([, type]) => !url.searchParams.get("dirs") || type === "dir")
            // DD-248: "etc" is on a local disk and was walked; "proc" is not, so it has no size.
            .map(([name, type]) => ({ name, type, count: type === "dir" ? 1 : undefined, size: type === "dir" ? (name === "etc" ? 3072 : null) : 512, mtime: Date.now() / 1000 })) };
        } else if (p === "/api/sistem/text") {
          result = { path: url.searchParams.get("path"), size: sysText.length, mtime: Date.now() / 1000, truncated: false, detected: "utf-8",
            encoding: "utf-8", bom: false, eol: "lf", editable: true, reason: "", version: "c".repeat(64), text: sysText };
        } else if (p === "/api/sistem/text/save") {
          const data = req.postDataJSON(); sysSaves.push(data); sysText = data.text;
          result = { path: data.path, version: "d".repeat(64), size: data.text.length, mtime: Date.now() / 1000 };
        } else if (p === "/api/sistem/delete") {
          const data = req.postDataJSON(); sysWrites.push(data);
          sysEntries[data.path] = sysEntries[data.path].filter(([name]) => !data.names.includes(name));
          result = { deleted: data.names };
        } else throw new Error("Unexpected system endpoint: " + p);
      }
      else if (p === "/api/konsol/paylasim") result = projectShares();
      else if (p === "/api/konsol/paylasim/kaydet") {
        submitted = req.postDataJSON();
        shareWrites.push(submitted);
        if (holdShare) await new Promise(resolve => { releaseShare = resolve; });
        if (failShare) { failShare = false; return route.fulfill({status:503,contentType:"application/json",body:JSON.stringify({error:"Test: önceki paylaşım korundu."})}); }
        const id = submitted.id || (shares.items.length ? "b" : "a").repeat(24);
        let s = shares.items.find((i) => i.id === id);
        for (const key of ["networks","permission","expires","paused","days","ack_write"]) assert.equal(submitted[key],undefined,"Legacy field: " + key);
        if (!s) {
          assert.deepEqual(Object.keys(submitted.connections).sort(),["tailscale","wan"]);
          s = { id, available:true, created:Date.now()/1000, changed:Date.now()/1000, connections:{} };
          for (const scope of ["tailscale","wan"]) s.connections[scope] = {enabled:false,permission:"ro",expires:null};
          shares.items.push(s);
        }
        if (submitted.path !== undefined) Object.assign(s, {name:submitted.path.split("/").pop(),path:submitted.path});
        if (submitted.username !== undefined) s.username = submitted.username;
        for (const [scope, patch] of Object.entries(submitted.connections || {})) {
          assert(["tailscale","wan"].includes(scope));
          assert(Object.keys(patch).every(k=>["enabled","permission","days","ack_write"].includes(k)));
          if (patch.permission === "rw") assert.equal(patch.ack_write,true);
          if (scope === "wan" && patch.enabled === true && !s.connections.wan.enabled && shares.wan.scheme !== "https") {
            assert.equal(submitted.ack_wan_http,true);
          }
          const conn = s.connections[scope];
          for (const key of ["enabled","permission"]) if (key in patch) conn[key] = patch[key];
          if ("days" in patch) conn.expires = patch.days ? Math.floor(Date.now()/1000)+patch.days*86400 : null;
        }
        result = projectShares();
      } else if (p === "/api/konsol/paylasim/kaldir") {
        const data = req.postDataJSON(); shareWrites.push({remove:data.id});
        shares.items = shares.items.filter(s=>s.id!==data.id); result = projectShares();
      }
      else if (p === "/api/trash") {
        if (req.method() === "POST") { deleted.push(req.postDataJSON()); result = {ok:true}; }
        else result = { items: trash };
      }
      else if (["/api/trash/restore", "/api/trash/purge", "/api/trash/empty"].includes(p)) {
        assert.equal(req.method(), "POST");
        const data = req.postDataJSON();
        trashWrites.push({path:p, data});
        trash = p.endsWith("/empty") ? [] : trash.filter(t => !data.ids.includes(t.id));
        result = {ok:true, purged:trashFixtures.length};
      }
      else throw new Error("Unexpected endpoint: " + p);
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(result) });
    });
    await page.goto((process.env.KONSOL_URL || "http://127.0.0.1:8766") + "/#/dosyalar");
    // DD-247: a folder tile and its info line give the item count and the walked total size, each part unbroken.
    assert.equal(await tile("media").locator(".fx-sub").innerText(), "2 öge · 1 KB");
    assert.equal(await tile("media").locator(".fx-sub > span").count(), 2);
    assert.match(await tile("media").getAttribute("aria-label"), /^media, klasör, 2 öge · 1 KB$/);
    await select("media");
    assert.match(await page.locator("#fs-detail").innerText(), /media/);
    // DD-250: the star after the selected folder's name adds it to Favoriler, above the tree's own rows; a
    // favourite opens its folder; the filled star or the row's × takes it out.
    const star = () => page.locator('#fs-detail-title [data-act="favori"]');
    assert.deepEqual([await star().getAttribute("aria-pressed"), await star().getAttribute("aria-label")], ["false", "Favorilere ekle"]);
    assert(await page.locator("#fs-detail-title").evaluate((t) => t.lastElementChild.dataset.act === "favori"
      && t.firstElementChild.textContent === "media" && t.textContent === "media"), "the star follows the name and adds no text");
    await star().click();
    await page.locator('#fs-rail [data-fav="/srv/media"]').waitFor();
    assert.deepEqual(favWrites.at(-1), { ekle: { yol: "media", sistem: false } });
    assert.deepEqual([await star().getAttribute("aria-pressed"), await star().getAttribute("aria-label")], ["true", "Favorilerden çıkar"]);
    assert(await page.locator("#fs-rail").evaluate((r) => {
      const kids = [...r.children], fav = kids.findIndex((c) => c.querySelector("[data-fav]")), root = kids.findIndex((c) => c.title === "Sunucu");
      return fav > 0 && fav < root;
    }), "the favourite comes first, before Sunucu");
    assert.equal(await page.locator('#fs-rail [data-fav="/srv/media"] .rl-c').innerText(), "/srv");
    await page.locator('#fs-rail [data-fav="/srv/media"]').click();
    await tile("movies").waitFor();
    assert.deepEqual(await page.locator("#fs-bar .crumb").allInnerTexts(), ["/srv","media"]);
    assert.equal(await star().getAttribute("aria-pressed"), "true", "the open folder's own star is filled");
    await page.locator("#fs-rail .rl-fav").hover();
    await page.locator("#fs-rail .rl-fav .rl-x").click();
    await page.waitForFunction(() => !document.querySelector("#fs-rail .rl-fav"));
    assert.deepEqual(favWrites.at(-1), { cikar: { yol: "media", sistem: false } });
    assert.equal(await page.locator("#fs-rail .rl-sep").count(), 0);
    await rail("Sunucu").click();
    await tile("media").waitFor();
    await select("media");
    assert.match(await page.locator("#fs-detail .fx-line").getAttribute("title"), /^Klasör · 2 öge · 1 KB · /);
    await page.screenshot({ path: path.join(shots, "desktop-list.png"), fullPage: true });
    await act("paylas").click();
    const tailscale = page.locator("#dav-tailscale"), wan = page.locator("#dav-wan"), ackWan = page.locator("#dav-ack-wan");
    const createButton = page.getByRole("button",{name:"Paylaşımı oluştur",exact:true});
    const closed = () => page.waitForFunction(()=>!document.querySelector("#sh").open);
    const ready = () => page.waitForFunction(()=>document.querySelector(".dav-shares")?.getAttribute("aria-busy")==="false");
    const refreshShares = async () => { await page.reload(); await page.locator(".dav-share-row").first().waitFor(); };
    assert.equal(await tailscale.getAttribute("aria-checked"),"true");
    assert.equal(await wan.getAttribute("aria-checked"),"false");
    for (const scope of ["tailscale","wan"]) {
      assert.equal(await page.locator("#dav-"+scope+"-permission").inputValue(),"ro");
      assert.equal(await page.locator("#dav-"+scope+"-days").inputValue(),"7");
    }
    assert(await ackWan.isHidden());
    await page.getByLabel("Kullanıcı adı",{exact:true}).fill("family-media");
    const sharePassword = page.getByLabel("Parola",{exact:true});
    await sharePassword.fill("1234567"); await createButton.click();
    assert.equal(submitted,undefined); assert.equal(await sharePassword.evaluate(i=>i.checkValidity()),false);
    await sharePassword.fill("Pass8!xy");
    await wan.click();
    assert(await ackWan.evaluate(i=>i.required)); await createButton.click(); assert.equal(submitted,undefined);
    await ackWan.check(); await wan.click(); await wan.click();
    assert(!(await ackWan.isChecked()),"HTTP consent resets when switching off");
    await wan.click();
    await page.locator("#dav-tailscale-permission").selectOption("rw");
    await createButton.click(); assert.equal(submitted,undefined,"RW requires scope-specific acknowledgement");
    await page.locator("#dav-tailscale-ack").check();
    await page.screenshot({path:path.join(shots,"editor.png"),fullPage:true});
    await createButton.click(); await closed();
    assert.deepEqual(submitted,{path:"media",username:"family-media",password:"Pass8!xy",connections:{
      tailscale:{enabled:true,permission:"rw",days:7,ack_write:true},wan:{enabled:false,permission:"ro",days:7}}});
    assert(!JSON.stringify(await page.evaluate(()=>({...localStorage,...sessionStorage}))).includes("Pass8!xy"));
    await select("media");
    await checkShareSummary(page.locator("#fs-detail"));
    await page.reload();
    await select("media");
    await checkShareSummary(page.locator("#fs-detail"));
    await rail("Paylaşımlar").click();
    const row = page.locator(".dav-share-row").first();
    const card = scope => row.locator('.dav-connection[data-network="'+scope+'"]');
    const permission = scope => card(scope).getByRole("combobox").nth(0);
    const days = scope => card(scope).getByRole("combobox").nth(1);
    const toggle = scope => card(scope).getByRole("switch");
    await checkShareAddresses(row);
    await checkShareAddress(card("tailscale").locator(".dav-address"),shares.items[0].connections.tailscale.url,true);
    await page.getByRole("button",{name:"Yönet",exact:true}).click();
    assert.equal(await page.locator("#sh select, #sh [role=switch], #sh input[type=checkbox]").count(),0,"Manage only contains shared fields");
    assert.equal(await page.locator("#dav-password").inputValue(),"");
    const beforeNoop = shareWrites.length;
    await page.getByRole("button",{name:"Güncelle",exact:true}).click(); await closed();
    assert.equal(shareWrites.length,beforeNoop,"Unchanged account does not restart the service");
    await page.getByRole("button",{name:"Yönet",exact:true}).click();
    await page.locator("#dav-user").fill("changed-user");
    failShare = true;
    await page.getByRole("button",{name:"Güncelle",exact:true}).click();
    await page.locator("#sh [role=alert]").waitFor({state:"visible"});
    assert.equal(await page.locator("#dav-user").inputValue(),"changed-user");
    assert.equal(shares.items[0].username,"family-media");
    await page.getByRole("button",{name:"Güncelle",exact:true}).click(); await closed(); await ready();
    assert.deepEqual(submitted,{id:"a".repeat(24),username:"changed-user"});
    const savedConnections = structuredClone(shares.items[0].connections);
    for (const change of [{password:"ChangedPass8!"},{path:"media-renamed"},{path:"media"}]) {
      await page.getByRole("button",{name:"Yönet",exact:true}).click();
      const [field,value] = Object.entries(change)[0];
      await page.locator("#dav-"+field).fill(value);
      await page.getByRole("button",{name:"Güncelle",exact:true}).click(); await closed(); await ready();
      assert.deepEqual(submitted,{id:"a".repeat(24),...change});
      assert.equal(await page.locator("#dav-password").inputValue(),"");
      assert.deepEqual(shares.items[0].connections,savedConnections);
    }
    const originalWan = structuredClone(shares.items[0].connections.wan);
    await permission("tailscale").selectOption("ro"); await ready();
    assert.deepEqual(submitted,{id:"a".repeat(24),connections:{tailscale:{permission:"ro"}}});
    const beforeAck = shareWrites.length;
    for (const cancel of ["button","escape"]) {
      await permission("tailscale").selectOption("rw");
      assert.equal(await permission("tailscale").inputValue(),"ro");
      if (cancel === "button") await page.locator("#cf-cancel").click(); else await page.keyboard.press("Escape");
      assert.equal(shareWrites.length,beforeAck);
    }
    await permission("tailscale").selectOption("rw"); await page.locator("#cf-go").click(); await ready();
    assert.deepEqual(submitted,{id:"a".repeat(24),connections:{tailscale:{permission:"rw",ack_write:true}}});
    for (const value of ["1","7","30","0"]) {
      await days("tailscale").selectOption(value); await ready();
      assert.deepEqual(submitted,{id:"a".repeat(24),connections:{tailscale:{days:Number(value)}}});
      assert.equal(await days("tailscale").inputValue(),value==="0"?"0":"keep");
      assert.deepEqual(shares.items[0].connections.wan,originalWan,"Other scope untouched");
    }
    const beforeUnlimited = shareWrites.length;
    await days("tailscale").selectOption("0"); assert.equal(shareWrites.length,beforeUnlimited);
    failShare = true;
    await permission("tailscale").selectOption("ro"); await ready();
    assert.equal(await permission("tailscale").inputValue(),"rw");
    await page.locator("#toast").getByText("Test: önceki paylaşım korundu.",{exact:true}).waitFor();
    holdShare = true; releaseShare = null;
    await days("tailscale").selectOption("7");
    while (!releaseShare) await page.waitForTimeout(10);
    assert(await row.locator("select, [role=switch], .dav-actions button").evaluateAll(nodes=>nodes.every(n=>n.disabled)));
    // A duplicate DOM event and a poll cannot overwrite the in-flight request.
    const beforeBusy = shareWrites.length;
    await toggle("tailscale").evaluate(el=>el.dispatchEvent(new Event("click")));
    await page.clock.install(); await page.clock.fastForward(11000);
    assert.equal(shareWrites.length,beforeBusy);
    holdShare = false; releaseShare(); await ready();
    await toggle("tailscale").click(); await ready();
    assert.deepEqual(submitted,{id:"a".repeat(24),connections:{tailscale:{enabled:false}}});
    assert.equal(await row.locator(".dav-share-state").textContent(),"Duraklatıldı");
    assert.equal(shares.items.length,1);
    await days("tailscale").selectOption("0"); await ready();
    assert.equal(shares.items[0].connections.tailscale.enabled,false);
    await toggle("tailscale").click(); await ready();
    assert.deepEqual(submitted,{id:"a".repeat(24),connections:{tailscale:{enabled:true}}},"Saved RW resumes without re-sending permission/ack");
    const beforeHttp = shareWrites.length;
    await toggle("wan").click(); await page.locator("#cf-cancel").click();
    assert.equal(shareWrites.length,beforeHttp); assert.equal(await toggle("wan").getAttribute("aria-checked"),"false");
    await toggle("wan").click(); await page.locator("#cf-go").click(); await ready();
    assert.deepEqual(submitted,{id:"a".repeat(24),connections:{wan:{enabled:true}},ack_wan_http:true});
    await permission("wan").selectOption("rw"); await page.locator("#cf-go").click(); await ready();
    assert.deepEqual(submitted,{id:"a".repeat(24),connections:{wan:{permission:"rw",ack_write:true}}});
    for (const value of ["1","7","30","0"]) {
      await days("wan").selectOption(value); await ready();
      assert.deepEqual(submitted,{id:"a".repeat(24),connections:{wan:{days:Number(value)}}});
    }
    // Expired candidate addresses survive; enabling does not renew either scope.
    for (const scope of ["tailscale","wan"]) {
      shares.items[0].connections[scope].expires = Math.floor(Date.now()/1000)-120;
      shares.items[0].connections[scope].enabled = false;
    }
    await refreshShares(); await checkShareAddresses(row);
    for (const scope of ["tailscale","wan"]) {
      const expires = shares.items[0].connections[scope].expires;
      assert.equal(await card(scope).locator(".dav-connection-state").textContent(),"Süresi doldu");
      assert.equal(await card(scope).locator("time").getAttribute("datetime"),new Date(expires*1000).toISOString());
      await toggle(scope).click();
      if (scope==="wan") await page.locator("#cf-go").click();
      await ready();
      assert.equal(shares.items[0].connections[scope].expires,expires);
      assert.equal(shares.items[0].connections[scope].active,false);
      assert.deepEqual(submitted.connections,{[scope]:{enabled:true}});
    }
    assert.equal(shares.items[0].url,""); assert.deepEqual(shares.items[0].urls,{});
    // Global gates may remove candidate URLs, but an enabled choice remains switchable off.
    shares.tail_enabled = false;
    shares.wan = {...wanStatus,available:false,reason:"WAN adresi şu anda kullanılamıyor."};
    await refreshShares();
    for (const scope of ["tailscale","wan"]) {
      assert.equal(await card(scope).locator(".dav-address").count(),0);
      assert(!(await toggle(scope).isDisabled()));
      await toggle(scope).click(); await ready();
      assert(await toggle(scope).isDisabled());
    }
    assert.match(await card("wan").innerText(),/WAN adresi şu anda kullanılamıyor/);
    assert.equal(await row.locator(".dav-share-state").textContent(),"Duraklatıldı");
    shares.tail_enabled = true; shares.wan = {...wanStatus,scheme:"https",mode:"https",domain:"dav.example.test",port:443};
    await refreshShares();
    for (const scope of ["tailscale","wan"]) {
      await days(scope).selectOption("7"); await ready();
      assert.equal(shares.items[0].connections[scope].enabled,false);
      await toggle(scope).click(); await ready();
      assert.equal(submitted.ack_wan_http,undefined);
    }
    assert.equal(await card("wan").locator("h3").textContent(),"HTTPS");
    await checkShareAddresses(row);
    shares.items[0].available = false; await refreshShares();
    assert.equal(await row.locator(".dav-share-state").textContent(),"Klasör bulunamadı");
    assert.equal(await row.locator(".dav-connection-state.active").count(),0);
    shares.items[0].available = true; await refreshShares();
    // Polling must not replace a focused selector or a pending confirmation.
    await permission("tailscale").focus();
    await page.clock.fastForward(11000);
    assert.equal(await page.locator(":focus").getAttribute("aria-label"),"media Tailscale erişim izni");
    await permission("tailscale").selectOption("ro"); await ready();
    await permission("tailscale").selectOption("rw"); await page.clock.fastForward(11000);
    assert(await page.locator("#cf").isVisible()); await page.locator("#cf-cancel").click();
    // DD-193: with Tailscale publication closed the create form starts that switch off and locked.
    shares.tail_enabled = false; await refreshShares();
    await rail("Sunucu").click();
    await select("Belgeler ve uzun klasör adı");
    await act("paylas").click();
    assert.equal(await tailscale.getAttribute("aria-checked"),"false");
    assert(await tailscale.isDisabled());
    assert.match(await page.locator('#sh .dav-connection[data-network="tailscale"]').innerText(),/Tailscale yayını kapalı/);
    await page.locator("#sh").getByRole("button",{name:"Vazgeç",exact:true}).click(); await closed();
    shares.tail_enabled = true;
    await rail("Paylaşımlar").click();
    // Creation supports paused, WAN-only and dual accounts, independent permissions/expiry.
    for (const selected of [[],["wan"],["tailscale","wan"]]) {
      shares.wan = {...wanStatus};
      await refreshShares();
      await rail("Sunucu").click();
      await select("Belgeler ve uzun klasör adı");
      await act("paylas").click();
      await page.getByLabel("Kullanıcı adı",{exact:true}).fill("wan-documents");
      await sharePassword.fill("WanPass8!");
      if (!selected.includes("tailscale")) await tailscale.click();
      if (selected.includes("wan")) { await wan.click(); await ackWan.check(); }
      await page.locator("#dav-wan-days").selectOption("30");
      await page.locator("#dav-wan-permission").selectOption("rw");
      const beforeCreate = shareWrites.length;
      await createButton.click(); assert.equal(shareWrites.length,beforeCreate);
      await page.locator("#dav-wan-ack").check();
      await page.setViewportSize({width:320,height:800});
      assert(await page.locator("#sh").evaluate(d=>d.scrollWidth<=d.clientWidth+1));
      failShare = true; await createButton.click();
      await page.locator("#sh [role=alert]").waitFor({state:"visible"});
      assert.equal(shares.items.length,1); assert.equal(await sharePassword.inputValue(),"WanPass8!");
      await createButton.click(); await closed();
      assert.deepEqual(submitted.connections,{
        tailscale:{enabled:selected.includes("tailscale"),permission:"ro",days:7},
        wan:{enabled:selected.includes("wan"),permission:"rw",days:30,ack_write:true}});
      assert.equal(submitted.ack_wan_http,selected.includes("wan")?true:undefined);
      await checkShareSummary(page.locator("#fs-detail"),shares.items[1]);
      await page.locator("#fs-detail").getByRole("button",{name:"Paylaşımı kaldır",exact:true}).click();
      const beforeRemove = shareWrites.length;
      await page.locator("#cf-cancel").click(); assert.equal(shareWrites.length,beforeRemove);
      await page.locator("#fs-detail").getByRole("button",{name:"Paylaşımı kaldır",exact:true}).click();
      await page.locator("#cf-go").click();
      await act("paylas").waitFor();
      assert.equal(shares.items.length,1);
      await rail("Paylaşımlar").click();
    }
    shares.wan = {...wanStatus,scheme:"https",mode:"https",domain:"dav.example.test",port:443};
    await refreshShares();
    for (const theme of ["light","dark"]) {
      await page.emulateMedia({colorScheme:theme});
      for (const width of [2560,1440,1024,761,760,736,600,480,390,320]) {
        await page.setViewportSize({width,height:950});
        await checkShareAddresses(row);
        assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),"share overflow "+theme+"/"+width);
        assert.equal(await row.locator("select").count(),4);
        const geometry = await row.locator(".dav-connection").evaluateAll(cards=>cards.map(card=>{
          const r=card.getBoundingClientRect();
          return {top:r.top,inside:[...card.querySelectorAll("select,button,code,dd,.dav-expiry")].every(el=>{
            const b=el.getBoundingClientRect();return b.left>=r.left && b.right<=r.right+1 && el.scrollWidth<=el.clientWidth+1;
          })};
        }));
        assert(geometry.every(c=>c.inside),"card control overflow "+theme+"/"+width);
        assert.equal(geometry[0].top===geometry[1].top,width>600,"Twin cards stack on mobile");
        await page.clock.fastForward(5000);
        await page.evaluate(()=>{ document.activeElement?.blur(); window.scrollTo(0,0); });
        await page.screenshot({path:path.join(shots,"shares-"+theme+"-"+width+".png"),fullPage:true});
        if ([1440,736,390,320].includes(width)) {
          await page.getByRole("button",{name:"Yönet",exact:true}).click();
          assert.equal(await page.locator("#sh select, #sh [role=switch]").count(),0);
          assert(await page.locator("#sh").evaluate(d=>d.scrollWidth<=d.clientWidth+1));
          await page.getByRole("button",{name:"Vazgeç",exact:true}).click();
        }
        await rail("Sunucu").click();
        await select("media");
        await checkShareSummary(page.locator("#fs-detail"));
        // Finder grid by default; the icon/list switch sits in the bar.
        assert(await page.locator(".fx-rows.grid #fs-table.fx-grid").count()===1);
        assert.equal(await page.locator('.fx-views [aria-pressed="true"]').getAttribute("aria-label"),"Simgeler");
        assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),"list overflow "+width);
        await rail("Paylaşımlar").click();
      }
    }
    await rail("Sunucu").click();
    // Move-to-trash is a short confirmation, with full names and no explanatory rows.
    for (const theme of ["light", "dark"]) {
      await page.emulateMedia({colorScheme:theme});
      for (const width of [1440,1024,736,390,320]) {
        await page.setViewportSize({width,height:950});
        await select(longFile);
        await act("cop").click();
        assert.equal(await page.locator('#cf-title').textContent(), 'Çöpe taşınsın mı?');
        assert.equal(await page.locator('#cf-sub').textContent(), longFile);
        assert.equal(await page.locator('#cf-sub').getAttribute('title'), longFile);
        assert(await page.locator('#cf-list').isHidden());
        assert(await page.locator('#cf-word-row').isHidden());
        assert.equal(await page.locator('#cf button:visible').count(),2);
        const fits = await page.locator('#cf').evaluate(d=>{
          const r=d.getBoundingClientRect();
          return r.height<240 && r.left>=0 && r.right<=innerWidth && d.scrollWidth<=d.clientWidth+1 &&
            [...d.querySelectorAll('#cf-title,.dlg-foot button')].every(e=>{const b=e.getBoundingClientRect();return b.left>=r.left && b.right<=r.right && b.bottom<=r.bottom;});
        });
        assert(fits, `trash confirmation overflow ${theme}/${width}`);
        await page.screenshot({path:path.join(shots,`confirm-${theme}-${width}.png`),fullPage:true});
        await page.locator('#cf-cancel').click();
      }
    }
    assert.deepEqual(deleted,[]);
    // DD-232: the detail column lists only the actions that apply; a multi-selection keeps six stable slots.
    const acts = () => page.locator("#fs-detail .fx-acts button").evaluateAll(bs=>bs.map(b=>[b.dataset.act,b.disabled]));
    const title = () => page.locator("#fs-detail-title").textContent();
    await select(longFile);
    assert.deepEqual(await acts(),[["indir",false],["adlandir",false],["tasi",false],["arsiv",false],["cop",false]]);
    await act("tasi").click();
    await page.locator("#sh .movelist .fname").first().waitFor();
    await page.locator("#sh").getByRole("button",{name:"Vazgeç",exact:true}).click();
    await act("arsiv").click();
    assert.equal(await page.locator("#archive-target").textContent(),"/srv/downloads");
    assert.equal(await page.locator("#sh h3").textContent(),"Arşiv oluştur");
    await page.locator("#sh").getByRole("button",{name:"Vazgeç",exact:true}).click();
    await tile(longFile).press("Escape");
    assert.equal(await title(),"Sunucu","Escape returns the detail to the open folder");
    await select("sample.part02.rar");
    assert.deepEqual((await acts()).map(a=>a[0]),["indir","adlandir","tasi","arsiv","ac-arsiv","cop"]);
    await act("ac-arsiv").click();
    assert.equal(await page.locator("#sh h3").textContent(),"Arşiv açıcı");
    assert.equal(await page.locator("#archive-name").inputValue(),"sample");
    assert.equal(await page.locator("#archive-target").textContent(),"/srv/downloads");
    await page.locator("#sh").getByRole("button",{name:"Vazgeç",exact:true}).click();
    await page.locator("#fs-table").click({position:{x:4,y:4}});
    assert.equal(await title(),"Sunucu","Clicking empty grid space clears the selection");
    await select("media");
    assert.deepEqual((await acts()).map(a=>a[0]),["ac","adlandir","tasi","arsiv","paylasim-yonet","paylasim-kaldir","cop"],"A shared folder offers its share instead of Paylaş");
    // DD-244: the actions are words; the icons are dropped on a desktop-width screen (narrower ones keep both).
    const wordsOnly = page.viewportSize().width >= 1101 ? "none" : "block";
    assert.deepEqual(await page.locator("#fs-detail .fx-acts .btn").evaluateAll(bs=>bs.map(b=>[b.innerText.trim(),getComputedStyle(b.querySelector("svg")).display])).then(r=>r.slice(0,2)),
      [["Klasörü aç",wordsOnly],["Yeniden adlandır",wordsOnly]]);
    await select("Belgeler ve uzun klasör adı");
    assert.deepEqual((await acts()).map(a=>a[0]),["ac","adlandir","tasi","arsiv","paylas","cop"]);
    await act("paylas").click();
    await page.getByLabel("Kullanıcı adı",{exact:true}).waitFor();
    await page.locator("#sh").getByRole("button",{name:"Vazgeç",exact:true}).click();
    await select(longFile);
    await tile("media").click({modifiers:["Control"]});
    assert.equal(await title(),"2 öge seçili");
    assert.equal(await page.locator("#fs-detail .fx-stack text").textContent(),"2","One two-document icon with a count");
    assert.deepEqual(await acts(),[["indir",false],["tasi",false],["arsiv",false],["ac-arsiv",true],["paylas",true],["cop",false],["birak",false]],"DD-243: Seçimi bırak is the last action");
    await act("indir").click();
    assert.deepEqual(await page.evaluate(()=>window.requestedDownloads.map(url=>{
      const u=new URL(url); return {path:u.pathname,file:u.searchParams.get("path")};
    })),[{path:"/api/download",file:longFile}],"Download links exclude selected folders");
    for (const theme of ["light", "dark"]) {
      await page.emulateMedia({colorScheme:theme,reducedMotion:"reduce"});
      for (const width of [2560,1440,1024,761,760,600,390,320]) {
        await page.setViewportSize({width,height:800});
        assert(await page.getByRole("navigation",{name:"Konum",exact:true}).isVisible(), "Selection preserves the address bar");
        const geometry = await page.locator("#fs-detail").evaluate(d=>{
          const r=d.getBoundingClientRect();
          return {inside:r.left>=0 && r.right<=innerWidth+1,scroll:document.documentElement.scrollWidth,
            controls:[...d.querySelectorAll('button')].every(b=>{const x=b.getBoundingClientRect(); return x.left>=r.left-1 && x.right<=r.right+1 && b.scrollWidth<=b.clientWidth+1;})};
        });
        assert(geometry.inside && geometry.controls && geometry.scroll<=width+1,`detail overflow ${theme}/${width}: ${JSON.stringify(geometry)}`);
        const tiles = await page.locator("#fs-table .fx-item").evaluateAll(items=>items.map(i=>{const r=i.getBoundingClientRect();return {left:r.left,right:r.right,w:r.width};}));
        assert(tiles.every(t=>t.left>=0 && t.right<=width+1 && t.w>=80),`tile overflow ${theme}/${width}`);
        assert.equal(await page.locator(".fs-dock, #fs-dock").count(),0,"No bottom dock");
        await page.screenshot({path:path.join(shots,`detail-${theme}-${width}.png`),fullPage:true});
      }
    }
    await page.setViewportSize({width:1440,height:1000});
    await page.getByRole("searchbox",{name:"Bu klasörde ara"}).fill("no-match");
    assert.equal(await title(),"Sunucu");
    await page.getByRole("searchbox",{name:"Bu klasörde ara"}).fill("");
    assert.equal(await title(),"2 öge seçili");
    await rail("Paylaşımlar").click();
    assert(await page.locator("#fs-detail").isHidden());
    await rail("Sunucu").click();
    await tile(longFile).waitFor();
    await select(longFile); await tile("media").click({modifiers:["Control"]});
    await act("cop").click();
    assert.equal(await page.locator('#cf-title').textContent(),'2 öge çöpe taşınsın mı?');
    await page.keyboard.press('Escape'); assert.deepEqual(deleted,[]);
    await act("cop").click();
    await page.locator('#cf-go').click();
    await page.waitForFunction(()=>!document.querySelector('#cf').open && document.querySelector('#fs-detail-title')?.textContent!=="2 öge seçili");
    assert.equal(deleted.length,1);
    assert.equal(deleted[0].path,'');
    assert.deepEqual(deleted[0].names.slice().sort(), ['media',longFile].sort());
    // List view stays available and remembered per browser.
    await page.locator(".fx-views").getByRole("button",{name:"Liste",exact:true}).click();
    await page.locator("#fs-table.fs-t").waitFor();
    assert.equal(await page.evaluate(()=>localStorage.getItem("konsol-files-view")),"list");
    await page.locator(".fx-views").getByRole("button",{name:"Simgeler",exact:true}).click();
    await page.locator("#fs-table.fx-grid").waitFor();
    // A real double-click opens the folder once: the second click already opens the selected tile.
    await tile("media").dblclick();
    await tile("movies").waitFor();
    assert.deepEqual(await page.locator("#fs-bar .crumb").allInnerTexts(), ["/srv","media"]);
    assert.equal(await tile("movies").locator(".fx-sub").innerText(), "2 öge", "an unwalked folder shows only its count");
    assert.equal(await tile("series").locator(".fx-sub").innerText(), "0 öge", "an empty folder shows no 0 B");
    // DD-249: a text file opens in the editor (CodeMirror under the production CSP). A save sends the version the
    // server gave (Ctrl+S too); unsaved changes ask before Kapat or Esc closes the window.
    await tile("ayar.yml").dblclick();
    await page.locator("#sh .ed-box .cm-content").waitFor();
    assert(await page.locator("#sh").evaluate((d) => d.open && d.classList.contains("ed-wide")));
    assert(!(await page.locator("#sh-body").evaluate((b) => [...b.childNodes].some((n) => n.nodeType === 3))), "the window shows a stray text node (null)");
    assert.equal(await page.locator("#sh .ed-lang").innerText(), "YAML");
    assert.equal(await page.locator("#sh .ed-warn").count(), 0, "the /srv view has no root warning");
    assert.match(await page.locator("#sh .okhead p").innerText(), /^\/srv\/media · 1 KB · UTF-8 · LF$/);
    const saveBtn = page.locator('#sh [data-act="kaydet"]');
    assert(await saveBtn.isDisabled());
    assert(await page.locator("#sh .ed-dirty").isHidden());
    await page.locator("#sh .cm-content").click();
    await page.keyboard.press("Control+End");
    await page.keyboard.type("debug: true");
    assert(await saveBtn.isEnabled());
    assert(await page.locator("#sh .ed-dirty").isVisible());
    assert.equal(await page.locator("#sh .ed-pos").innerText(), "Satır 3, Sütun 12");
    await page.keyboard.press("Control+s");
    await page.waitForFunction(() => document.querySelector('#sh [data-act="kaydet"]').disabled && document.querySelector("#sh .ed-dirty").hidden);
    assert.deepEqual(textSaves.at(-1), { path: "media/ayar.yml", text: textStart + "debug: true", encoding: "utf-8", version: "a".repeat(64) });
    await page.keyboard.type("\n# iki");
    await saveBtn.click();
    await page.waitForFunction(() => document.querySelector("#sh .ed-dirty").hidden);
    assert.equal(textSaves.at(-1).version, "b".repeat(64), "the next save sends the version the last one returned");
    assert(await page.locator("#sh .cm-content").evaluate((c) => c.contains(document.activeElement) || c === document.activeElement),
      "after Kaydet the caret is back in the text");
    await page.keyboard.type("x");
    await page.locator("#sh .ed-foot").getByRole("button", { name: "Kapat", exact: true }).click();
    await page.locator("#cf[open]").waitFor();
    assert.equal(await page.locator("#cf-title").innerText(), "Kaydedilmemiş değişiklikler atılsın mı?");
    assert(await page.locator("#sh").evaluate((d) => d.open), "the editor stays open behind the question");
    await page.locator("#cf-cancel").click();
    await page.locator("#sh .dlg-x").focus();
    await page.keyboard.press("Escape");
    await page.locator("#cf[open]").waitFor();
    assert(await page.locator("#sh").evaluate((d) => d.open), "Esc asks too");
    await page.locator("#cf-go").click();
    await page.waitForFunction(() => !document.querySelector("#sh").open && !document.querySelector("#sh").classList.contains("ed-wide"));
    assert.equal(textSaves.length, 2, "discarding saves nothing");
    // A file the server will not have edited opens read-only, with the reason.
    await tile("buyuk.log").dblclick();
    await page.locator("#sh pre.textview").waitFor();
    assert.match(await page.locator("#sh .infoline-s").innerText(), /Dosya büyük/);
    assert.equal(await page.locator("#sh .ed-box").count(), 0);
    await page.locator("#sh .dlg-foot").getByRole("button", { name: "Kapat", exact: true }).click();
    await page.waitForFunction(() => !document.querySelector("#sh").open);
    await page.getByRole("searchbox", { name: "Bu klasörde ara" }).fill("series");
    assert.equal(await tile("movies").count(), 0);
    assert.equal(await tile("series").count(), 1);
    const trashTab = rail("Çöp");
    await trashTab.click();
    await page.getByText("Çöp boş", {exact:true}).waitFor();
    trash = [...trashFixtures];
    await rail("Sunucu").click();
    await trashTab.click();
    await page.locator(".trash-t > .tr:not(.head)").nth(3).waitFor();
    for (const theme of ["light", "dark"]) {
      await page.emulateMedia({colorScheme:theme});
      for (const width of [1440, 1101, 1100, 1024, 736, 390, 320]) {
        await page.setViewportSize({width,height:1000});
        await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
        const geometry = await page.locator(".trash-t").evaluate(table => {
          const rect = el => {const r=el.getBoundingClientRect();return {x:r.x,y:r.y,right:r.right,bottom:r.bottom,w:r.width,h:r.height};};
          return {table:rect(table), head:[...table.querySelector(".head").children].map(rect), rows:[...table.querySelectorAll(".tr:not(.head)")].map(row => ({
            cells:[...row.children].map(rect), text:rect(row.querySelector(".fname > span:last-child")),
            parts:[...row.querySelectorAll(".fname strong,.fname small")].map(el=>({scroll:el.scrollWidth,client:el.clientWidth})),
            buttons:[...row.querySelectorAll("button")].map(rect),
          }))};
        });
        for (const row of geometry.rows) {
          const [name,size,date,actions]=row.cells;
          assert(name.w>180, `trash name squeezed: ${theme}/${width}: ${name.w}`);
          assert(row.text.w>130, `trash text squeezed ${width}`);
          assert(row.parts.every(p=>p.scroll<=p.client+1), `trash text clipped ${width}`);
          assert(row.cells.every(c=>c.x>=geometry.table.x && c.right<=geometry.table.right), `trash cell escaped ${width}`);
          assert(row.buttons.every(b=>b.x>=actions.x && b.right<=actions.right+1 && b.h>=30), `trash actions escaped ${width}`);
          if (geometry.head[0].w>0) {  // wide table: the trash follows the Finder window's own width
            row.cells.forEach((c,i)=>assert(Math.abs(c.x-geometry.head[i].x)<1, `trash header alignment ${width}`));
            assert(name.right<=size.x && size.right<=date.x && date.right<=actions.x, `trash cell overlap ${width}`);
          } else {
            assert(size.y>=name.bottom && date.y>=name.bottom, `trash metadata overlaps name ${width}`);
            assert(actions.y>=Math.max(size.bottom,date.bottom), `trash actions overlap metadata ${width}`);
            assert.equal(name.x,actions.x);
          }
        }
        assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1), `trash page overflow ${theme}/${width}`);
        await page.screenshot({path:path.join(shots,`trash-${theme}-${width}.png`),fullPage:true});
      }
    }
    assert.deepEqual(trashWrites, []);
    // All mutations are fixtures: never restore/purge real operator trash in UI tests.
    await page.getByRole("button",{name:"Geri yükle",exact:true}).first().click();
    await page.waitForFunction(()=>document.querySelectorAll(".trash-t > .tr:not(.head)").length===3);
    assert.deepEqual(trashWrites.at(-1),{path:"/api/trash/restore",data:{ids:["trash-short"]}});
    await page.getByRole("button",{name:"Kalıcı sil",exact:true}).last().click();
    await page.locator("#cf").getByRole("button",{name:"Vazgeç",exact:true}).click();
    assert.equal(trashWrites.length,1);
    await page.getByRole("button",{name:"Kalıcı sil",exact:true}).last().click();
    await page.locator("#cf-go").click();
    await page.waitForFunction(()=>document.querySelectorAll(".trash-t > .tr:not(.head)").length===2);
    assert.deepEqual(trashWrites.at(-1),{path:"/api/trash/purge",data:{ids:["trash-folder"]}});
    await page.getByRole("button",{name:/Çöpü boşalt/}).click();
    assert(await page.locator("#cf-go").isDisabled());
    await page.locator("#cf-word").fill("onayla");
    await page.locator("#cf-go").click();
    await page.getByText("Çöp boş",{exact:true}).waitFor();
    assert.deepEqual(trashWrites.at(-1),{path:"/api/trash/empty",data:{confirm:"onayla"}});
    // DD-235: "Sistem (/)" in the sidebar: root view (DD-238: no warning strip), no trash/archive/share actions,
    // permanent delete confirmed by typing the item's name, every call under /api/sistem/.
    await page.emulateMedia({colorScheme:"light"});
    await page.setViewportSize({width:1440,height:1000});
    await rail("Sistem (/)").click();
    await page.locator("#fs-bar .crumb.root").getByText("/", {exact:true}).waitFor();
    assert.equal(new URL(page.url()).hash, "#/dosyalar/sistem");
    assert.equal(await page.locator(".offbar.sysbar").count(), 0, "DD-238: no 'Root olarak çalışıyorsunuz' strip");
    assert(!/Root olarak çalışıyorsunuz|salt okunur/.test(await page.locator("#fs-panel").innerText()));
    assert.equal(await page.locator("#fs-bar .crumb.root").innerText(), "/");
    assert.equal(await tile("etc").locator(".fx-sub").innerText(), "1 öge · 3 KB", "DD-248: a walked system folder shows its size");
    assert.equal(await tile("proc").locator(".fx-sub").innerText(), "1 öge", "DD-248: a pseudo file system shows only its count");
    await select("vmlinuz");
    assert.equal(await act("sil").count(), 1);
    for (const key of ["cop","paylas","arsiv","ac-arsiv"]) assert.equal(await act(key).count(), 0, "system view offers " + key);
    await act("indir").click();
    assert.match(await page.evaluate(()=>window.requestedDownloads.at(-1)), /\/api\/sistem\/download\?path=vmlinuz$/);
    const downloads = await page.evaluate(()=>window.requestedDownloads.length);
    await tile("vmlinuz").dblclick();
    assert.equal(await page.evaluate(()=>window.requestedDownloads.length), downloads + 1, "a double-click downloads once");
    // DD-236: while a folder loads, the listing on screen stays (dimmed, inert) and the window's frame is the
    // same DOM: nothing shrinks, nothing is rebuilt. A double-click on the selected folder opens it once.
    await select("etc");
    // DD-250: a system-view favourite carries its tree: listed as "root · /", removed with the filled star.
    await page.locator('#fs-detail [data-act="favori"]').click();
    await page.locator('#fs-rail [data-fav="/etc"]').waitFor();
    assert.deepEqual(favWrites.at(-1), { ekle: { yol: "etc", sistem: true } });
    assert.equal(await page.locator('#fs-rail [data-fav="/etc"] .rl-c').innerText(), "root · /");
    await page.locator('#fs-detail [data-act="favori"][aria-pressed="true"]').click();
    await page.waitForFunction(() => !document.querySelector('#fs-rail [data-fav="/etc"]'));
    assert.deepEqual(favWrites.at(-1), { cikar: { yol: "etc", sistem: true } });
    const panelHeight = () => page.locator("#fs-panel").evaluate((p) => p.getBoundingClientRect().height);
    const tall = await panelHeight();
    await page.evaluate(() => { window.__frame = [document.querySelector("#fs-bar .pathfield"), document.querySelector("#fs-q"), document.querySelector("#fs-rail")]; });
    await select("vmlinuz");  // the double-click below selects etc and then opens it, as a person's does
    let releaseSys; holdSys = new Promise((resolve) => { releaseSys = resolve; });
    await tile("etc").dblclick();
    await page.waitForFunction(() => document.querySelector("#fs-panel").classList.contains("fx-loading"));
    assert.equal(await tile("vmlinuz").count(), 1, "the old listing stays on screen while the folder loads");
    assert(await page.locator("#fs-rows").evaluate((b) => b.inert), "the old listing is inert while loading");
    assert.equal(await page.locator("#fs-bar .crumb.cur").innerText(), "etc", "the path changes at once");
    assert.equal(await page.locator("#fs-meta, .pf-meta").count(), 0, "DD-243: no count or size in the path bar");
    assert.equal(await panelHeight(), tall, "the window changed height while the folder loaded");
    holdSys = null; releaseSys();
    await page.waitForFunction(()=>document.querySelector('#fs-table [data-item="hosts"]') || /bulunamadı/.test(document.querySelector("#toast").textContent));
    assert(!sysReads.some(r=>/path=etc(%2F|\/)etc/.test(r)), "a double-click opened the folder twice");
    await tile("hosts").waitFor();
    assert(await page.evaluate(() => window.__frame.every((el, i) => el === [document.querySelector("#fs-bar .pathfield"), document.querySelector("#fs-q"), document.querySelector("#fs-rail")][i])),
      "opening a folder rebuilt the toolbar, the search box or the places column");
    assert(!(await page.locator("#fs-panel").evaluate((p) => p.classList.contains("fx-loading"))));
    // The scroll bar's room is always kept, so selecting or opening never moves the page sideways (v2-217).
    assert.equal(await page.evaluate(() => getComputedStyle(document.documentElement).scrollbarGutter), "stable");
    await select("hosts");
    assert(!/null/.test(await page.locator("#fs-detail").innerText()), "detail column prints null");
    // DD-249: the root view's editor says it saves as root and posts under /api/sistem/.
    await act("duzenle").click();
    await page.locator("#sh .ed-box .cm-content").waitFor();
    assert.match(await page.locator("#sh .ed-warn").innerText(), /Root olarak kaydedilir/);
    assert.equal(await page.locator("#sh .ed-lang").innerText(), "Yapılandırma");
    await page.locator("#sh .cm-content").click();
    await page.keyboard.press("Control+End");
    await page.keyboard.type("10.0.0.1 nas");
    await page.keyboard.press("Control+s");
    await page.waitForFunction(() => document.querySelector("#sh .ed-dirty").hidden);
    assert.deepEqual(sysSaves, [{ path: "etc/hosts", text: "127.0.0.1 localhost\n10.0.0.1 nas", encoding: "utf-8", version: "c".repeat(64) }]);
    await page.screenshot({ path: path.join(shots, "system-editor.png") });
    await page.locator("#sh .dlg-x").click();
    await page.waitForFunction(() => !document.querySelector("#sh").open);
    await page.screenshot({path:path.join(shots,"system-view.png"),fullPage:true});
    await act("sil").click();
    assert(await page.locator("#cf-go").isDisabled());
    assert.equal(await page.locator("#cf-word-label").innerText(), "hosts");
    await page.locator("#cf-word").fill("onayla");
    assert(await page.locator("#cf-go").isDisabled(), "a single item needs its own name, not onayla");
    await page.locator("#cf-word").fill("hosts");
    await page.locator("#cf-go").click();
    await page.waitForFunction(()=>!document.querySelector('#fs-table [data-item="hosts"]'));
    assert.deepEqual(sysWrites, [{path:"etc", names:["hosts"], confirm:"hosts"}]);
    assert(sysReads.every(r=>r.startsWith("/api/sistem/")) && sysReads.some(r=>r.startsWith("/api/sistem/list?path=etc")));
    // DD-236: on a desktop-width screen the page itself does not scroll; opening a folder never moves it.
    await select("ssh");
    holdSys = new Promise((resolve) => { releaseSys = resolve; });
    await page.evaluate(() => document.querySelector('#fs-table [data-item="ssh"]').click());
    await page.waitForFunction(() => document.querySelector("#fs-panel").classList.contains("fx-loading"));
    assert.equal(await page.evaluate(() => scrollY), 0, "the page moved while the folder loaded");
    holdSys = null; releaseSys();
    await page.locator("#fs-bar .crumb.cur").getByText("ssh", {exact:true}).waitFor();
    assert.equal(await page.evaluate(() => scrollY), 0);
    await page.setViewportSize({width:1440,height:1000});
    await rail("Sunucu").click();
    await page.locator("#fs-bar .crumb.root").getByText("/srv", {exact:true}).waitFor();
    assert.equal(new URL(page.url()).hash, "#/dosyalar/klasor");
    assert.equal(await page.locator("#fs-bar .crumb.root").innerText(), "/srv");
    assert.deepEqual(errors, []);
    console.log("PASS: schema4 twin cards, independent partial writes/RO/RW/expiry, paused creation, HTTP consent, HTTPS, global gates, expired candidates, shared account edits, failed saves/retry/busy/poll guards, Infuse/copy, responsive light/dark/CSP; Finder grid/detail column/multi-selection, trash, the root system view (DD-235) and Files regressions. Screenshots: " + shots);
  } finally { await browser.close(); }
})().catch((e) => { console.error(e); process.exit(1); });
