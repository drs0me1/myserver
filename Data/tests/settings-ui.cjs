/* Real production UI with deterministic API fixtures; no server mutations. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const screenshots = fs.mkdtempSync(path.join(os.tmpdir(), "konsol-v136-ui-"));
const copy = (x) => JSON.parse(JSON.stringify(x));
// DD-200: the qBittorrent sidebar link and store texts come from the package's konsol.json.
const torrentMeta = JSON.parse(fs.readFileSync(path.join(__dirname, "../magaza/torrent/konsol.json"), "utf8").replace(/__[A-Z_]+__/g, "x"));
const config = { firewall: [{id:"fixture-ci",name:"CI",family:4,scope:"wan",proto:"tcp",port:9443,source:"192.0.2.0/24",allow:false}], dns: { disabled: [], records: [], forward: false, servers: [] } };
const data = {
  read_at: 1780000000, version: "2026.08.06-v2-134", domain: "ayc", tailscale: "100.64.0.2", ts_if: "tailscale0", wan: { iface: "eth0", ipv4: "192.0.2.1" },
  firewall: { ok: true, check: "ok", vpn_installed:false, vpn_name:"", networks:[], ports: [{ name: "SSH", family: 4, scope: "wan", port: 22, proto: "tcp", baseline: true },
      { name: "Caddy", family: 4, scope: "tail", port: 80, proto: "tcp", baseline: true }, { name: "Caddy", family: 4, scope: "wan", port: 80, proto: "tcp", baseline: false },
      { name: "Konsol · dosya arka ucu", family: 4, scope: "lo", port: 61009, proto: "tcp", baseline: true },
      { name: "SSH", family: 6, scope: "wan", port: 22, proto: "tcp", baseline: true }],
    listeners: [{ port: 22, proto: "tcp", family: 4, address: "0.0.0.0", scope:"any" },
      {port:80,proto:"tcp",family:4,address:"100.64.0.2",scope:"tail"},
      {port:61009,proto:"tcp",family:4,address:"127.0.0.1",scope:"lo"}],
    rules: { errors: [], rows: [{ family: 4, table: "filter", chain: "ts-input", position: 1, packets: 12, bytes: 1024, spec: "-i tailscale0 -j ACCEPT", owner: "Tailscale" }] } },
  web: { entries: [{ address: "panel.ayc", source: "base", access: "tailscale", routes: [{ kind: "proxy", path: "/api/*", to: "127.0.0.1:61008" }] }], raw: [] },
  dns: { listen: ["lo", "tailscale0"] },
  manage: { revision: "r1", config: copy(config), pending: null, names: [{ name: "panel.ayc", target: "tailscale", source: "base" }, { name: "torrent.ayc", target: "tailscale", source: "torrent" }] },
};
let lastApply = null, writes = 0, failApply = false, discarded = false;
// DD-194/DD-205: Konsol account fixture. The backend names the channel: on the internet address the
// card shows the signed-in user, the password dialog asks the current password and the sidebar
// signs out; on the tailnet there is no sign-in — accountOverride switches the fixture there.
let sessionState = "acik", passwordFail = "", loggedOut = false, accountOverride = null;
const passwordWrites = [], createWrites = [];
// DD-182: Settings → Sistem health card fixture; one warning, one problem.
const health = { status: "bad", read_at: 1790750000, checks: [
  { id: "units", name: "Servisler", status: "ok", detail: "Başarısız servis yok" },
  { id: "reboot", name: "Yeniden başlatma", status: "warn", detail: "Güncellemeler yeniden başlatma bekliyor (linux-image-test)" },
  { id: "settings", name: "Ayar işlemi", status: "bad", detail: "Geri alma takıldı; Ayarlar'da yeniden deneyin ya da bırakın" }] };
// DD-239: "Denetle ve onar" fixture: the unit runs while repair.calisiyor, its report is repair.rapor.
let repair = { calisiyor: false, kurulu: true, baslatilabilir: true, rapor: null };
const repairStarts = [], logReads = [];
const step = (id, ad, durum, detay) => ({ id, ad, durum, detay });
(async () => {
  const browser = await chromium.launch({ headless: true, ...(process.env.PLAYWRIGHT_CHROMIUM ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM } : {}) });
  try {
    const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("console", m => {if (/violates.*Content Security Policy|Refused to|not a valid regular expression/.test(m.text())) errors.push(m.text());});
    const csp = fs.readFileSync(path.join(__dirname,"../templates/Caddyfile"),"utf8").match(/Content-Security-Policy "([^"]+)"/)[1];
    await page.route("**/*", async route => {
      if (route.request().resourceType() !== "document") return route.continue();
      const response = await route.fetch();
      await route.fulfill({response, headers:{...response.headers(),"content-security-policy":csp}});
    });
    await page.route("**/api/**", async (route) => {
      if (route.request().method() === "POST") writes++;
      const url = new URL(route.request().url()), endpoint = url.pathname;
      let result = {};
      if (endpoint === "/api/konsol/moduller") result = { items: [{ id: "torrent", installed: true, state: "calisiyor", runtime: "konteyner", live: "running", durdurulabilir: true, konsol: torrentMeta }] };
      else if (endpoint === "/api/konsol/kaynaklar") result = { host: "test", version: data.version, domain: "ayc", os: "Debian 13", kernel: "test", uptime: 120, cores: 2, cpu: [1], mem: { total: 1000, used: 200, graph: [20] }, net: { wan: "192.0.2.1", tailscale: data.tailscale }, root: "/srv", disk: { total: 1000, free: 800 }, ports: [{ port: 22, proto: "tcp", scope: "internet", name: "SSH" }] };
      else if (endpoint === "/api/konsol/islemler") result = { items: [] };
      else if (endpoint === "/api/state") result = {root:"/srv", protected:[{path:"downloads/incomplete",owner:"Deneme Uygulaması"}], disk:{total:10000,free:8000}, trash:{count:0,size:0}};
      else if (endpoint === "/api/list") result = {path:"",entries:[]};
      else if (endpoint === "/api/archives") result = {items:[], limits:{bytes:2147483648,entries:10000,layers:5,seconds:900}};
      else if (endpoint === "/api/konsol/ayarlar") result = data;
      else if (endpoint === "/api/konsol/ayarlar/durum") result = data.manage;
      else if (endpoint === "/api/konsol/ayarlar/klasorler") result = { items: [{ path: "/srv/downloads", free: 10000000000 }, { path: "/srv/media", free: 10000000000 }] };
      else if (endpoint === "/api/konsol/ayarlar/uygula") {
        lastApply = route.request().postDataJSON();
        assert.equal(lastApply.revision, data.manage.revision, "Draft revision follows our own account commit");
        if (failApply) {
          failApply = false;
          return route.fulfill({status:400, contentType:"application/json", body:JSON.stringify({error:"DNS sınama hatası; önceki ayarlar korundu."})});
        }
        if (lastApply.firewall) data.manage.config.firewall = copy(lastApply.firewall);
        if (lastApply.dns) data.manage.config.dns = copy(lastApply.dns);
        data.manage.pending = { id: "transaction", seconds: 60, phase: "awaiting" };
        if (lastApply.domain) {
          data.manage.pending.domain = { old: "ayc", new: lastApply.domain };
          data.manage.pending.seconds = 300;
        }
        result = { pending: data.manage.pending };
        if (Object.keys(lastApply).sort().join(",") === "dns,revision") {
          data.manage.pending = null; data.manage.revision += "-dns";
          result = {pending:null, committed:true};
        }
      } else if (endpoint === "/api/konsol/saglik") result = health;
      else if (endpoint === "/api/konsol/onarim" && route.request().method() === "POST") {
        const body = route.request().postDataJSON();
        repairStarts.push(body);
        repair = { ...repair, calisiyor: true, rapor: { durum: "calisiyor", kip: body.kip, baslangic: 1790750100, bitis: null,
          adimlar: [step("duvar", "Güvenlik duvarı", "ok", "Kurallar beklenen biçimde"), step("tailscale", "Tailscale", "calisiyor", "")] } };
        result = { kip: body.kip };
      }
      else if (endpoint === "/api/konsol/onarim") result = repair;
      else if (endpoint === "/api/konsol/onarim/gunluk") {
        logReads.push(url.searchParams.get("sure"));
        return route.fulfill({ status: 200, contentType: "text/plain; charset=utf-8",
          body: url.searchParams.get("sure") === "7g" ? "2026-10-01T03:20:00+0000 nrm refresh-tailnet-config[9]: refresh-tailnet: değişiklik yok (100.64.0.2)\n<b>x</b>\n"
            : "2026-10-07T06:35:00+0000 nrm master-onar[1]: denetim ve onarım başladı (konsol)\n2026-10-07T06:36:00+0000 nrm master-onar[1]: ↻ Güvenlik duvarı: kurallar yeniden kuruldu\n" });
      }
      else if (endpoint === "/api/konsol/oturum") result = accountOverride || (sessionState === "acik" ? {durum:"acik",kullanici:"fixture",oturum_gun:7,kanal:"internet"} : {durum:"giris",kanal:"internet"});
      else if (endpoint === "/api/konsol/oturum/kur") { createWrites.push(route.request().postDataJSON()); result = {durum:"kuruldu"}; }
      else if (endpoint === "/api/konsol/hesap/parola") {
        passwordWrites.push(route.request().postDataJSON());
        if (passwordFail) {
          const error = passwordFail; passwordFail = "";
          return route.fulfill({status:401, contentType:"application/json", body:JSON.stringify({error})});
        }
        result = {durum:"acik"};
      }
      else if (endpoint === "/api/konsol/oturum/cikis") { loggedOut = true; result = {durum:"cikis"}; }
      else if (endpoint.endsWith("/birak")) {
        const body = route.request().postDataJSON();
        assert.deepEqual(body, { id: "stuck", confirm: "onayla" }, "Discard sends the typed word and the stuck id");
        discarded = true; data.manage.pending = null; result = { ok: true };
      }
      else if (endpoint.endsWith("/onayla")) { data.manage.pending = null; data.manage.revision = "r2"; result = { ok: true }; }
      else if (endpoint.endsWith("/geri-al")) { data.manage.pending = null; data.manage.config = copy(config); result = { ok: true }; }
      else throw new Error("Unexpected endpoint " + endpoint);
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(result) });
    });
    await page.goto((process.env.KONSOL_URL || "http://127.0.0.1:8766") + "/#/ayarlar");
    // DD-182: the Sistem tab opens with the read-only health card.
    const healthCard = page.locator("article.card", { has: page.getByRole("heading", { name: "Sağlık", exact: true }) });
    await healthCard.getByText("Güncellemeler yeniden başlatma bekliyor (linux-image-test)", { exact: true }).waitFor();
    assert.equal(await healthCard.locator(".card-head .hm.bad").innerText(), "Sorun var");
    assert.equal(await healthCard.locator(".health-facts .hm.warn").count(), 1);
    assert.equal(await healthCard.locator(".health-facts > div").count(), 3);
    await page.screenshot({ path: path.join(screenshots, "health-card.png"), fullPage: true });
    // DD-245: three cards: Panel ve sunucu (with the account), Sağlık in one row, Denetle ve onar; no "Yerleşik altyapı".
    assert.deepEqual(await page.locator(".as-stack > article").evaluateAll((a) => a.map((c) => c.className)), ["card server-card", "card health-strip", "card repair-card"]);
    assert.equal(await page.getByText("Yerleşik altyapı").count(), 0);
    assert.equal(await page.locator(".server-card #konsol-account").count(), 1, "the account is the server card's last line");
    const strip = await healthCard.evaluate((c) => { const r = c.getBoundingClientRect(), facts = [...c.querySelectorAll(".health-facts > div")].map((d) => Math.round(d.getBoundingClientRect().top)); return { h: r.height, rows: new Set(facts).size }; });
    assert(strip.rows === 1 && strip.h < 120, `Sağlık is one row: ${JSON.stringify(strip)}`);
    // DD-239: no background loop; the card starts master-onar. "Denetle" needs no confirmation, "Onar" does.
    const box = page.locator(".repair-card .repair");
    await box.getByText("Henüz denetim yapılmadı", { exact: true }).waitFor();
    assert.match(await box.innerText(), /sudo master-onar/);
    await box.getByRole("button", { name: "Denetle", exact: true }).click();
    await box.locator('[data-step="tailscale"].rs-calisiyor').waitFor();
    assert.deepEqual(repairStarts, [{ kip: "denetle" }]);
    assert.equal(await box.locator(".repair-head small").innerText(), "Denetim sürüyor…");
    assert(await box.getByRole("button", { name: "Onar", exact: true }).isDisabled(), "a running check locks both buttons");
    await page.screenshot({ path: path.join(screenshots, "repair-running.png"), fullPage: true });
    repair = { ...repair, calisiyor: false, rapor: { durum: "hata", kip: "onar", baslangic: 1790750100, bitis: 1790750160, adimlar: [
      step("duvar", "Güvenlik duvarı", "onarildi", "Kurallar beklenenden farklı; kurallar yeniden kuruldu"),
      step("tailscale", "Tailscale", "ok", "Çalışıyor, çevrimiçi"),
      step("servisler", "Servisler", "hata", "Başlatılamadı: master-paylasim.service"),
      step("dns", "DNS", "atlandi", "dig kurulu değil")] } };
    await box.locator('[data-step="servisler"].rs-hata').waitFor({ timeout: 8000 });
    assert.match(await box.locator(".repair-head small").innerText(), /^Son onarım: \d{1,2} [^ ]+ \d\d:\d\d · sorun var$/);
    assert.deepEqual(await box.locator(".rs-mark").allInnerTexts(), ["↻", "✓", "✗", "–"]);
    await page.screenshot({ path: path.join(screenshots, "repair-report.png"), fullPage: true });
    // DD-241: Günlük shows the last 72 hours, or the last week; text only, newest at the bottom.
    await box.getByRole("button", { name: "Günlük", exact: true }).click();
    await page.locator("#repair-log").getByText(/Güvenlik duvarı: kurallar yeniden kuruldu/).waitFor();
    assert.equal(await page.locator("#sh h3").innerText(), "Denetim ve onarım günlüğü");
    assert.equal(await page.locator('.repair-log-tools [aria-pressed="true"]').innerText(), "72 saat");
    await page.screenshot({ path: path.join(screenshots, "repair-log.png"), fullPage: false });
    await page.locator(".repair-log-tools").getByRole("button", { name: "1 hafta", exact: true }).click();
    await page.locator("#repair-log").getByText(/değişiklik yok/).waitFor();
    assert.match(await page.locator("#repair-log").innerText(), /<b>x<\/b>/, "log text is shown as text");
    assert.equal(await page.locator("#repair-log b").count(), 0);
    assert.deepEqual(logReads, ["72s", "7g"]);
    await page.locator("#sh").getByRole("button", { name: "Kapat" }).click();
    await box.getByRole("button", { name: "Onar", exact: true }).click();
    assert.equal(await page.locator("#cf-title").innerText(), "Denetim ve onarım başlasın mı?");
    await page.locator("#cf-cancel").click();
    assert.equal(repairStarts.length, 1, "cancel starts nothing");
    await box.getByRole("button", { name: "Onar", exact: true }).click();
    await page.locator("#cf-go").click();
    await box.locator('[data-step="tailscale"].rs-calisiyor').waitFor();
    assert.deepEqual(repairStarts.at(-1), { kip: "onar" });
    repair = { ...repair, calisiyor: false, baslatilabilir: false, rapor: { ...repair.rapor, durum: "tamam", bitis: 1790750200,
      adimlar: repair.rapor.adimlar.map((s) => ({ ...s, durum: "ok" })) } };
    await box.locator(".repair-head small").getByText(/· tamam$/).waitFor({ timeout: 8000 });
    assert(await box.getByRole("button", { name: "Onar", exact: true }).isDisabled(), "the internet address cannot start a repair");
    assert.equal(await box.getByRole("button", { name: "Onar", exact: true }).getAttribute("title"), "Onarım yalnız Tailscale adresinden başlatılır");
    repair.baslatilabilir = true;
    // DD-194: the Konsol account card; the password change runs in the shared dialog, which
    // the 10-second Settings refresh cannot redraw while typing.
    const account = page.locator("#konsol-account");
    await account.getByText("Giriş yapan: fixture. Oturum 7 gün açık kalır.", { exact: true }).waitFor();
    await account.getByRole("button", { name: "Parolayı değiştir", exact: true }).click();
    const passwordForm = page.locator("#konsol-password");
    const changePassword = passwordForm.getByRole("button", { name: "Parolayı değiştir", exact: true });
    await page.locator("#acc-old").fill("old-password-1");
    await page.locator("#acc-new").fill("new-password-12");
    await page.locator("#acc-again").fill("new-password-13");
    await changePassword.click();
    assert.equal(passwordWrites.length, 0, "Different new passwords stay in the browser");
    await page.locator("#acc-again").fill("new-password-12");
    passwordFail = "Mevcut parola hatalı.";
    await changePassword.click();
    await passwordForm.getByText("Mevcut parola hatalı.", { exact: true }).waitFor();
    assert.equal(await page.locator("#acc-old").inputValue(), "", "A rejected current password is cleared");
    assert.equal(page.url().includes("giris.html"), false, "A wrong current password is not a sign-out");
    await page.locator("#acc-old").fill("old-password-1");
    await changePassword.click();
    await page.getByText("Konsol parolası değişti; diğer oturumlar kapatıldı.", { exact: true }).first().waitFor();
    assert.equal(await page.locator("#sh").evaluate((d) => d.open), false);
    assert.deepEqual(passwordWrites, [{ eski: "old-password-1", yeni: "new-password-12" }, { eski: "old-password-1", yeni: "new-password-12" }]);
    assert(await page.locator("#logout").isVisible(), "the sidebar signs out on the internet address");
    // DD-205: on the tailnet address there is no sign-in — the card shows the internet account, the
    // password dialog asks no current password, and the sidebar has no sign-out.
    accountOverride = { durum: "giris", kullanici: "fixture", kanal: "tailscale" };
    await page.reload();
    await account.getByText("İnternet hesabı: fixture. Tailscale'den giriş parolasızdır; internet adresi bu hesapla açılır.", { exact: true }).waitFor();
    assert.equal(await account.getByRole("button", { name: "Çıkış yap", exact: true }).count(), 0);
    assert(await page.locator("#logout").isHidden(), "no sidebar sign-out on the tailnet");
    await account.getByRole("button", { name: "Parolayı değiştir", exact: true }).click();
    await passwordForm.waitFor();
    assert.equal(await page.locator("#acc-old").count(), 0, "no current password on the tailnet");
    await page.locator("#acc-new").fill("new-password-77");
    await page.locator("#acc-again").fill("new-password-78");
    await changePassword.click();
    assert.equal(passwordWrites.length, 2, "different new passwords stay in the browser");
    await page.locator("#acc-again").fill("new-password-77");
    await changePassword.click();
    await page.getByText("Konsol parolası değişti; internet oturumları kapatıldı.", { exact: true }).first().waitFor();
    assert.deepEqual(passwordWrites.at(-1), { yeni: "new-password-77" });
    // No account yet: the card creates the internet account (user name + password, no code).
    accountOverride = { durum: "kurulum", kanal: "tailscale" };
    await page.reload();
    await account.getByText(/hesap olmadan internet yayını açılmaz/).waitFor();
    await account.getByRole("button", { name: "İnternet hesabı oluştur", exact: true }).click();
    const createForm = page.locator("#konsol-create"), createButton = createForm.getByRole("button", { name: "Hesabı oluştur", exact: true });
    await createForm.waitFor();
    assert.equal(await page.evaluate(() => document.activeElement.id), "acc-user");
    await page.locator("#acc-user").fill("-kotu");
    await page.locator("#acc-new").fill("fixture-password-1");
    await page.locator("#acc-again").fill("fixture-password-1");
    await createButton.click();
    assert.equal(createWrites.length, 0, "an invalid user name never leaves the browser");
    await page.locator("#acc-user").fill("yonetici");
    await page.locator("#acc-again").fill("fixture-password-2");
    await createButton.click();
    assert.equal(createWrites.length, 0, "different passwords never leave the browser");
    await page.locator("#acc-again").fill("fixture-password-1");
    await createButton.click();
    await page.getByText("Konsol hesabı oluşturuldu; internet adresi bu hesapla açılır.", { exact: true }).first().waitFor();
    assert.deepEqual(createWrites, [{ kullanici: "yonetici", parola: "fixture-password-1" }]);
    assert.equal(await page.locator("#sh").evaluate((d) => d.open), false);
    accountOverride = null;
    await page.reload();
    await account.getByText("Giriş yapan: fixture. Oturum 7 gün açık kalır.", { exact: true }).waitFor();
    // DD-182: a stuck rollback offers retry and a typed discard, never an automatic give-up.
    data.manage.pending = { id: "stuck", phase: "stuck", seconds: 0, attempts: 5, error: "Komut tamamlanamadı: master-firewall" };
    await page.reload();
    await page.getByRole("tab", { name: "Güvenlik Duvarı" }).click();
    const stuck = page.locator(".as-rollback.stuck");
    await stuck.getByText("Geri alma tamamlanamadı (5 deneme)", { exact: true }).waitFor();
    assert.match(await stuck.innerText(), /Son hata: Komut tamamlanamadı: master-firewall/);
    await stuck.getByRole("button", { name: "Bırak…", exact: true }).click();
    const dialog = page.locator("dialog.as-dialog");
    await dialog.getByLabel("Onaylamak için onayla yazın").fill("evet");
    await dialog.getByRole("button", { name: "Devam et", exact: true }).click();
    assert(await dialog.isVisible() && !discarded, "A wrong word neither closes the dialog nor calls the server");
    await dialog.getByLabel("Onaylamak için onayla yazın").fill("ONAYLA");
    await dialog.getByRole("button", { name: "Devam et", exact: true }).click();
    await page.getByText("Takılan işlem bırakıldı; kaydedilmiş ayarlar için kurulumu yeniden çalıştırın.", { exact: true }).first().waitFor();
    assert(discarded);
    assert.equal(await page.locator(".as-rollback").count(), 0);
    writes = 0;  // the discard was this block's only write
    // Continue from a settled page, as the original flow starts (the discard reloads settings).
    await page.reload();
    await page.getByRole("tab", { name: "Güvenlik Duvarı" }).click();
    const category = name => page.getByRole("tablist",{name:"Trafik kategorileri",exact:true}).getByRole("tab",{name,exact:true});
    assert.equal(await category("Tailscale").getAttribute("aria-selected"),"true");
    assert.equal(await category("WireGuard").count(),0);
    assert.match(await page.locator(".as-ports").innerText(), /Bu ağda dinliyor/);
    assert.equal(await page.locator(".as-ports details").count(),0);
    assert.equal(await page.locator(".as-ports thead th").count(),7);
    assert.equal(await page.locator(".as-ports th[scope=row]").count(),1);
    await category("Tailscale").focus(); await page.keyboard.press("ArrowRight");
    assert.equal(await category("İnternet").getAttribute("aria-selected"),"true");
    assert.equal(await page.evaluate(() => document.activeElement.id),"as-fw-tab-wan");
    assert.match(await page.locator(".as-ports").innerText(), /Tüm IPv4 arayüzlerinde dinler/);
    assert.match(await page.locator(".as-ports").innerText(),/Sunucuya uzaktan terminal bağlantısı/);
    assert.match(await page.locator(".as-ports").innerText(),/192\.0\.2\.0\/24/);
    assert.match(await page.locator(".as-ports").innerText(),/Başka adreste dinliyor/);
    await page.keyboard.press("End");
    assert.equal(await category("Sunucu içi").getAttribute("aria-selected"),"true");
    assert(await page.getByRole("switch",{name:"Konsol · dosya arka ucu Sunucu içi tcp 61009",exact:true}).isDisabled());
    assert.match(await page.locator(".as-ports").innerText(),/Sunucu içinde dinliyor/);
    assert.equal(await page.getByRole("button",{name:"+ Port kuralı",exact:true}).count(),0);
    await page.keyboard.press("Home");
    assert.equal(await page.locator(".as-ports tbody tr").count(),1);
    await category("İnternet").click();
    await page.getByRole("combobox",{name:"Adres ailesi",exact:true}).selectOption("6");
    assert.equal(await page.locator(".as-ports th[scope=row]").count(),1);
    assert.match(await page.locator(".as-ports").innerText(),/Dinleyici yok/);
    await category("Tailscale").click();
    assert.match(await page.locator(".as-ports").innerText(),/Bu seçimde kayıt yok/);
    await page.getByRole("combobox",{name:"Adres ailesi",exact:true}).selectOption("4");
    await category("İnternet").click();
    const ci = page.locator(".as-ports tbody tr").filter({has:page.getByRole("rowheader",{name:/^CI /})});
    await ci.getByRole("button",{name:"Düzenle",exact:true}).click();
    await page.getByRole("textbox",{name:"Kaynak IP/CIDR",exact:true}).fill("192.0.2.5/32");
    await page.getByRole("button",{name:"Devam et",exact:true}).click();
    assert.match(await ci.innerText(),/192\.0\.2\.5\/32/);
    assert.match(await ci.innerText(),/Taslak · henüz uygulanmadı/);
    await ci.getByRole("button",{name:"Kuralı kaldır",exact:true}).click();
    assert.equal(await ci.count(),0);
    assert.equal(writes,0, "Table edits only stage drafts");
    await page.getByRole("button",{name:"Vazgeç",exact:true}).click();
    await page.getByRole("switch", { name: "SSH İnternet tcp 22", exact: true }).click();
    assert.match(await page.locator(".as-footer").innerText(), /1 değişiklik/);
    await category("Tailscale").click();
    assert.match(await page.locator(".as-footer").innerText(), /1 değişiklik/);
    await category("İnternet").click();
    assert.equal(await page.getByRole("switch", { name: "SSH İnternet tcp 22", exact: true }).getAttribute("aria-checked"), "false");
    await page.getByRole("button", { name: "Vazgeç", exact: true }).click();
    assert.equal(await page.getByRole("switch", { name: "SSH İnternet tcp 22", exact: true }).getAttribute("aria-checked"), "true");
    await page.getByRole("button", { name: "Teknik kurallar", exact: true }).click();
    assert.match(await page.locator(".as-rules").innerText(), /ts-input/);
    assert.match(await page.locator(".as-rules").innerText(), /Eşleşen pakete bu zincirde izin verir/);
    assert.match(await page.locator(".as-rules").innerText(), /Salt okunur · bu panelden değiştirilmez/);
    assert.equal(await page.locator(".as-rules").getByRole("switch").count(),0);
    await page.getByRole("tab", { name: "Caddy", exact: true }).click();
    await page.locator(".as-web-details > summary").click();
    assert.match(await page.locator("#cfg-web").innerText(), /panel.ayc/);
    await page.getByRole("tab", { name: "Dnsmasq", exact: true }).click();
    assert(await page.getByRole("switch", {name:"panel.ayc", exact:true}).isDisabled());
    const dnsWrites = writes;
    await page.getByRole("switch", {name:"torrent.ayc", exact:true}).click();
    await page.getByRole("button", {name:"Uygula", exact:true}).click();
    await page.waitForFunction(() => document.querySelector(".as-message")?.textContent.includes("Dnsmasq ayarları uygulandı ve kaydedildi"));
    await page.waitForFunction(() => document.querySelector(".as-footer")?.textContent.includes("Kaydedilmemiş değişiklik yok"));
    assert.equal(writes, dnsWrites + 1, "DNS uses a single Apply request, no confirmation POST");
    assert.deepEqual(Object.keys(lastApply).sort(), ["dns", "revision"]);
    assert.deepEqual(data.manage.config.dns.disabled, ["torrent.ayc"]);
    assert.equal(await page.locator("dialog[open], .as-rollback").count(), 0);
    await page.reload();
    await page.getByRole("switch", {name:"torrent.ayc", exact:true}).waitFor();
    assert.equal(await page.getByRole("switch", {name:"torrent.ayc", exact:true}).getAttribute("aria-checked"), "false");
    await page.getByRole("switch", {name:"torrent.ayc", exact:true}).click();
    failApply = true;
    await page.getByRole("button", {name:"Uygula", exact:true}).click();
    await page.waitForFunction(() => document.querySelector(".as-message")?.textContent.includes("DNS sınama hatası"));
    assert.deepEqual(data.manage.config.dns.disabled, ["torrent.ayc"]);
    assert.equal(await page.locator(".as-rollback").count(), 0);
    assert.match(await page.locator(".as-footer").innerText(), /1 değişiklik taslakta/);
    await page.getByRole("button", {name:"Uygula", exact:true}).click();
    await page.waitForFunction(() => document.querySelector(".as-footer")?.textContent.includes("Kaydedilmemiş değişiklik yok"));
    assert.deepEqual(data.manage.config.dns.disabled, []);
    await page.getByRole("switch", { name: "torrent.ayc", exact: true }).click();
    await page.getByRole("button", { name: "+ Alan adı", exact: true }).click();
    await page.getByRole("textbox", { name: "Tam alan adı" }).fill("nas.ayc");
    await page.getByRole("button", { name: "Devam et" }).click();
    await page.getByRole("switch", { name: "Üst DNS'e yönlendirme", exact: true }).click();
    await page.getByLabel("Sağlayıcı", { exact: true }).selectOption("google");
    // DD-202: the base transaction carries no application section; the DNS draft applies directly.
    await page.getByRole("button", { name: "Uygula", exact: true }).click();
    await page.waitForFunction(() => document.querySelector(".as-message")?.textContent.includes("Dnsmasq ayarları uygulandı"));
    assert.deepEqual(lastApply.dns.servers, ["8.8.8.8", "8.8.4.4"]);
    assert.deepEqual(Object.keys(lastApply).sort(), ["dns", "revision"], "No application section in a settings request");
    assert.equal(data.manage.config.dns.records.length, 1);
    await page.emulateMedia({colorScheme:"light"});
    await page.setViewportSize({width:1400, height:1000});
    await page.locator('.nav [data-route="ayarlar"]').click();
    await page.getByRole("tab", { name: "Güvenlik Duvarı" }).click();
    await category("İnternet").click();
    await page.getByRole("button", { name: "+ Port kuralı", exact: true }).click();
    await page.getByRole("textbox", { name: "Ad", exact: true }).fill("Test port");
    await page.getByRole("spinbutton", { name: "Port", exact: true }).fill("12345");
    await page.getByRole("button", { name: "Devam et" }).click();
    await page.getByRole("switch",{name:"Test port İnternet tcp 12345",exact:true}).click();
    assert.equal(await page.getByRole("switch",{name:"Test port İnternet tcp 12345",exact:true}).getAttribute("aria-checked"),"false");
    await page.getByRole("button", { name: "İncele ve uygula" }).click();
    await page.getByRole("button", { name: "Sunucuda uygula", exact: true }).click();
    await page.locator(".as-rollback").waitFor();
    assert.equal(lastApply.firewall.find(r => r.name === "Test port").allow,false);
    assert(await page.getByRole("switch",{name:"Test port İnternet tcp 12345",exact:true}).isDisabled());
    await page.getByRole("button", { name: "Geri al", exact: true }).click();
    await page.waitForFunction(() => !document.querySelector(".as-rollback"));
    assert.equal(await page.locator(".as-ports").getByText("Test port", { exact: true }).count(), 0);
    await page.screenshot({ path: path.join(screenshots, "desktop.png"), fullPage: true });
    await page.getByRole("tab", { name: "Caddy", exact: true }).click();
    await page.getByRole("textbox", { name: "Yerel alan adı", exact: true }).fill("bad.example");
    assert.equal(await page.getByRole("textbox", { name: "Yerel alan adı", exact: true }).evaluate((el) => el.checkValidity()), false);
    await page.getByRole("textbox", { name: "Yerel alan adı", exact: true }).fill("ev");
    await page.getByRole("button", { name: "Güncelle", exact: true }).click();
    assert.match(await page.locator(".as-dialog").innerText(), /Restrict to domain/);
    assert.match(await page.locator(".as-dialog").innerText(), /http:\/\/panel.ev/);
    await page.getByRole("button", { name: "Alan adını güncelle", exact: true }).click();
    await page.locator(".as-rollback").waitFor();
    assert.equal(lastApply.domain, "ev");
    assert.deepEqual(Object.keys(lastApply).sort(), ["domain", "revision"]);
    assert(await page.getByRole("button", { name: "Bağlantı çalışıyor · onayla" }).isDisabled());
    assert.equal(await page.getByRole("link", { name: "Yeni Konsol'u aç: panel.ev" }).getAttribute("href"), "http://panel.ev/#/ayarlar");
    await page.screenshot({ path: path.join(screenshots, "domain-change.png"), fullPage: true });
    await page.getByRole("button", { name: "Geri al", exact: true }).click();
    await page.waitForFunction(() => !document.querySelector(".as-rollback"));
    for (const width of [1400, 1024, 736, 390, 320]) {
      await page.setViewportSize({ width, height: 900 });
      for (const name of ["Sistem", "Güvenlik Duvarı", "Caddy", "Dnsmasq", "Günlük"]) {
        await page.getByRole("tab", { name, exact: true }).click();
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `overflow at ${width} / ${name}`);
        if (name === "Güvenlik Duvarı") {
          for (const label of ["Teknik kurallar","Portlara dön"]) {
            await page.getByRole("button",{name:label,exact:true}).click();
            const region = page.locator(".as-fw-scroll");
            assert.equal(await region.locator("thead").evaluate(el => getComputedStyle(el).display),"table-header-group");
            assert.equal(await region.locator("tbody tr").first().evaluate(el => getComputedStyle(el).display),"table-row");
            if (width <= 736) {
              assert(await region.evaluate(el => el.scrollWidth > el.clientWidth));
              await region.focus(); await page.keyboard.press("ArrowRight");
              await page.waitForFunction(() => document.querySelector(".as-fw-scroll")?.scrollLeft > 0);
            }
            const bounds = await page.evaluate(() => ({window:innerWidth, page:document.documentElement.scrollWidth,
              boxes:[...document.querySelectorAll('.main,.content,#settings-page,#as-view,.as-card,.as-fw-scroll')].map(el => [el.className || el.id,el.clientWidth,el.scrollWidth])}));
            assert(bounds.page <= bounds.window + 1,`${width}/${label}: ${JSON.stringify(bounds)}`);
          }
          // The toggle remains reachable in the actual horizontally scrolled table.
          const ssh = page.getByRole("switch",{name:"SSH İnternet tcp 22",exact:true});
          await ssh.click(); assert.equal(await ssh.getAttribute("aria-checked"),"false");
          await page.getByRole("button",{name:"Vazgeç",exact:true}).click();
        }
      }
    }
    await page.emulateMedia({ colorScheme: "dark" });
    await page.getByRole("tab",{name:"Güvenlik Duvarı",exact:true}).click();
    await page.screenshot({path:path.join(screenshots,"firewall-mobile-dark.png"),fullPage:true});
    await page.setViewportSize({width:1440,height:1000});
    await page.screenshot({path:path.join(screenshots,"firewall-desktop-dark.png"),fullPage:true});
    await page.getByRole("tab", { name: "Dnsmasq", exact: true }).click();
    await page.screenshot({ path: path.join(screenshots, "mobile-dark.png"), fullPage: true });
    // Installation state controls the VPN category, independently of network count.
    await page.getByRole("tab", { name: "Güvenlik Duvarı", exact: true }).click();
    // DD-200: the category takes the installed package's name from the backend (vpn_name).
    data.firewall.vpn_installed = true; data.firewall.vpn_name = "WireGuard";
    await page.getByRole("button", {name:"Yenile",exact:true}).click();
    await category("WireGuard").click();
    assert.match(await page.locator("#as-fw-content").innerText(),/Henüz yönetilebilir bir WireGuard ağı yok/);
    assert.equal(await page.getByRole("button",{name:"+ Port kuralı",exact:true}).count(),0);
    data.firewall.networks = [{iface:"wg0",label:"Ev",active:true}, {iface:"wg1",label:"Telefon",active:false}];
    data.firewall.ports.push({name:"WireGuard wg0",family:4,scope:"wan",port:51820,proto:"udp",baseline:true});
    await page.getByRole("button",{name:"Yenile",exact:true}).click();
    await page.getByRole("combobox",{name:"WireGuard ağı",exact:true}).waitFor();
    assert.equal(await page.locator(".as-ports th[scope=row]").count(),0);
    assert.match(await page.locator("#as-fw-content").innerText(),/yalnız internete/);
    assert.equal(await page.getByRole("button",{name:"+ Port kuralı",exact:true}).count(),0);
    await page.getByRole("combobox",{name:"WireGuard ağı",exact:true}).selectOption("wg1");
    assert.equal(await page.locator(".as-ports").getByRole("switch").count(),0);
    await category("İnternet").click();
    assert(await page.getByRole("switch",{name:"WireGuard wg0 İnternet udp 51820",exact:true}).count());
    await page.getByRole("button",{name:"+ Port kuralı",exact:true}).click();
    assert.deepEqual(await page.getByRole("combobox",{name:"Kapsam",exact:true}).locator("option").evaluateAll(xs=>xs.map(x=>x.value)),["wan","tail"]);
    await page.locator(".as-dialog").getByRole("button",{name:"Vazgeç",exact:true}).click();
    await category("WireGuard").click();
    await page.screenshot({path:path.join(screenshots,"wireguard-networks.png"),fullPage:true});
    // DD-173/174: removing automatic rows never hides explicit rules on WAN and Tailscale.
    const beforeRules = copy(data.manage.config.firewall), beforeRuleWrites = writes;
    for (const [ruleScope, tab] of [["tail","Tailscale"], ["wan","İnternet"]]) {
      await category(tab).click();
      if (ruleScope === "wg1") await page.getByRole("combobox",{name:"WireGuard ağı",exact:true}).selectOption("wg1");
      const label = `Özel kural ${ruleScope === "wg1" ? "wg1" : tab} tcp 61009`;
      for (const allow of [false, true]) {
        data.manage.config.firewall = [...copy(beforeRules),
          {id:"explicit-rule",name:"Özel kural",family:4,scope:ruleScope,proto:"tcp",port:61009,source:"",allow}];
        await page.getByRole("button",{name:"Yenile",exact:true}).click();
        const custom = page.getByRole("switch",{name:label,exact:true});
        await page.waitForFunction(({label,allow}) => [...document.querySelectorAll('[role="switch"]')]
          .find(el => el.getAttribute("aria-label") === label)?.getAttribute("aria-checked") === String(allow), {label,allow});
        assert.equal(await custom.getAttribute("aria-checked"),String(allow));
        await custom.click();
        assert.equal(await custom.getAttribute("aria-checked"),String(!allow));
        await page.getByRole("button",{name:"Vazgeç",exact:true}).click();
        const row = page.locator(".as-ports tbody tr").filter({has:custom});
        await row.getByRole("button",{name:"Kuralı kaldır",exact:true}).click();
        assert.equal(await custom.count(),0,"Removing an explicit rule does not invent a listener-derived baseline");
        await page.getByRole("button",{name:"Vazgeç",exact:true}).click();
        assert.equal(await custom.getAttribute("aria-checked"),String(allow));
      }
      data.manage.config.firewall = copy(beforeRules);
      await page.getByRole("button",{name:"Yenile",exact:true}).click();
      await page.getByRole("switch",{name:label,exact:true}).waitFor({state:"detached"});
    }
    assert.equal(writes,beforeRuleWrites,"Custom rule checks only stage drafts");
    data.manage.config.firewall = beforeRules.filter(r => r.id !== "fixture-wg1");
    await category("WireGuard").click();
    data.firewall.vpn_installed = false; data.firewall.vpn_name = "";
    data.firewall.networks = [];
    data.firewall.ports = data.firewall.ports.filter(r => !r.scope.startsWith("wg") && r.port !== 51820);
    await page.getByRole("button",{name:"Yenile",exact:true}).click();
    await category("WireGuard").waitFor({state:"detached"});
    assert.equal(await category("Tailscale").getAttribute("aria-selected"),"true");
    // An allowed policy must never disguise a loopback-only or unreadable socket.
    data.firewall.listeners = [{port:80,proto:"tcp",family:4,address:"127.0.0.1",scope:"lo"}];
    await page.getByRole("button",{name:"Yenile",exact:true}).click();
    await page.getByText("Yalnız sunucu içinde",{exact:true}).waitFor();
    assert.equal(await page.getByRole("switch",{name:"Caddy Tailscale tcp 80",exact:true}).getAttribute("aria-checked"),"true");
    data.firewall.listeners = [{port:80,proto:"tcp",family:4,address:"10.10.0.1",scope:"unknown"}];
    await page.getByRole("button",{name:"Yenile",exact:true}).click();
    await page.getByText("Ağ eşleşmesi bilinmiyor",{exact:true}).waitFor();
    data.firewall.listeners = null;
    await page.getByRole("button",{name:"Yenile",exact:true}).click();
    await page.getByText("Dinleyici durumu bilinmiyor.",{exact:true}).waitFor();
    // DD-194: sidebar sign-out ends the session and lands on the sign-in page.
    await page.setViewportSize({ width: 1400, height: 900 });
    sessionState = "giris";
    await page.locator("#logout").click();
    await page.waitForURL((url) => url.pathname === "/giris.html");
    await page.locator("#form-login").waitFor();
    assert(loggedOut);
    assert.deepEqual(errors, []);
    assert.deepEqual(await page.evaluate(() => Object.keys(localStorage)), []);
    console.log("PASS: Konsol account card (internet: signed-in user, current password, sign-out; tailnet: internet account, new password only, account creation, no sign-out), network categories/WG lifecycle and multi-network selection/listener versus permission/keyboard tabs/draft retention, full firewall tables/toggles/rollback, DNS immediate single Apply/persistence/failure/retry/protected panel/mixed confirmation, no application section (the qBittorrent form is torrent-ui.cjs) in 5 widths/both themes, domain transaction, keyboard scroll, production CSP. Screenshots: " + screenshots);
  } finally { await browser.close(); }
})().catch((err) => { console.error(err); process.exit(1); });
