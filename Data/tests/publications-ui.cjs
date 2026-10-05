/* Production console, mocked APIs: table interactions/CSP/responsiveness. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs"), path = require("node:path"), os = require("node:os"), http = require("node:http");
const root = path.resolve(__dirname, "../console"), shots = fs.mkdtempSync(path.join(os.tmpdir(), "caddy-publications-ui-"));
const csp = fs.readFileSync(path.join(root, "../templates/Caddyfile"), "utf8").match(/Content-Security-Policy "([^"]+)"/)[1];
const data = { read_at:1790790000, version:"fixture", domain:"ayc", tailscale:"100.64.0.2", ts_if:"tailscale0",
  wan:{iface:"eth0",ipv4:"192.0.2.1"}, firewall:{ok:true,ports:[],listeners:[],rules:{rows:[],errors:[]}},
  web:{entries:[],raw:[]}, dns:{listen:["lo","tailscale0"]}, torrent:{installed:true},
  manage:{revision:"r1",pending:null, config:{firewall:[],dns:{disabled:[],records:[],forward:false,servers:[]}},names:[],
    https:{mode:"https",domain:"dav.example.net",port:443,status:"ready"}, publications:[
      {service:"panel",name:"Panel",local:"panel.ayc",tail:true,enabled:false,domain:"",installed:true,running:true,account:true,status:"disabled",message:"İnternet yayını kapalı. Tailscale adresi her zaman açık kalır."},
      {service:"torrent",name:"qBittorrent",local:"torrent.ayc",tail:true,enabled:false,domain:"",installed:true,running:true,status:"disabled"},
      {service:"paylasim",name:"WebDAV",local:"paylas.ayc",tail:true,enabled:true,domain:"dav.example.net",installed:true,running:true,status:"ready",expires:1800000000}
    ]}};
const writes=[], errors=[]; let failure="", hold=false, release;
const server = http.createServer((req,res) => {
  const name = new URL(req.url,"http://localhost").pathname;
  const file = path.join(root, name === "/" ? "index.html" : name);
  if (!file.startsWith(root + "/")) { res.writeHead(403); return res.end(); }
  fs.readFile(file,(err,body)=>{ res.writeHead(err?404:200,{"Content-Type":file.endsWith(".js")?"text/javascript":file.endsWith(".css")?"text/css":"text/html", "Content-Security-Policy":csp}); res.end(err?"Not found":body); });
});
(async()=>{
  await new Promise(resolve=>server.listen(0,"127.0.0.1",resolve));
  const browser=await chromium.launch({headless:true});
  try {
    const page=await browser.newPage({viewport:{width:1440,height:1100}});
    page.on("pageerror",e=>errors.push(e.message));
    page.on("console",m=>{if(/Content Security Policy|Refused to/.test(m.text())) errors.push(m.text());});
    page.on("dialog",d=>d.accept());
    await page.route("**/api/**",async route=>{
      const url=new URL(route.request().url()); let result={};
      if(url.pathname==="/api/konsol/ayarlar") result=data;
      else if(url.pathname==="/api/konsol/ayarlar/durum") result=data.manage;
      else if(url.pathname==="/api/konsol/ayarlar/uygula") {
        const body=route.request().postDataJSON(); writes.push(body);
        assert.deepEqual(Object.keys(body).sort(),["revision","web"]); assert.equal(body.revision,data.manage.revision);
        if(body.web.service==="panel") assert.equal(body.web.tail,true,"Konsol's tailnet address never closes");
        if(hold) await new Promise(resolve=>{release=resolve;});
        if(failure) { const error=failure;failure="";return route.fulfill({status:400,contentType:"application/json",body:JSON.stringify({error})}); }
        const row=data.manage.publications.find(r=>r.service===body.web.service);
        Object.assign(row,body.web,{status:body.web.enabled?"ready":"disabled"});
        data.manage.revision="r"+(writes.length+1); result={committed:true,pending:null};
      } else if(url.pathname==="/api/konsol/moduller") result={items:[]};
      else if(url.pathname==="/api/konsol/islemler") result={items:[]};
      else if(url.pathname==="/api/state") result={roots:[],path:"",capabilities:{}};
      else if(url.pathname==="/api/list") result={path:"",entries:[]};
      else if(url.pathname==="/api/konsol/oturum") result={durum:"giris",kullanici:"fixture",kanal:"tailscale"};  // DD-205
      else if(url.pathname==="/api/konsol/kaynaklar") result={mem:{},net:{},cpu:[],torrent:{}};
      else throw new Error("Unexpected endpoint: "+url.pathname);
      await route.fulfill({status:200,contentType:"application/json",body:JSON.stringify(result)});
    });
    await page.goto(`http://127.0.0.1:${server.address().port}/#/ayarlar/web`);
    const table=page.locator("#as-publications"), row=id=>table.locator(`[data-publication="${id}"]`);
    const save=id=>row(id).getByRole("button",{name:"Kaydet",exact:true});
    const settled=()=>page.waitForFunction(()=>document.querySelector("#as-publications")?.getAttribute("aria-busy")==="false");
    await table.waitFor();
    const local=page.locator(".as-local-domain"), guide=local.locator(".as-tailnet-guide");
    const localInput=local.getByRole("textbox",{name:"Yerel alan adı",exact:true});
    const guideValues=()=>guide.locator("code").allTextContents();
    assert.deepEqual(await guideValues(),["100.64.0.2","ayc"]);
    assert.equal(await guide.locator("li").count(),4);
    assert.match(await guide.innerText(),/Restrict to search domain/);
    const admin=guide.getByRole("link",{name:"Tailscale Admin → DNS",exact:true});
    assert.equal(await admin.getAttribute("href"),"https://login.tailscale.com/admin/dns");
    assert.equal(await admin.getAttribute("target"),"_blank");
    assert.match(await admin.getAttribute("rel"),/noopener/);
    await localInput.fill("yeni");
    assert.deepEqual(await guideValues(),["100.64.0.2","ayc"],"Guide describes saved DNS, not an unapplied draft");
    await local.getByRole("button",{name:"Güncelle",exact:true}).click();
    const dialog=page.locator("dialog.as-dialog");
    assert.match(await dialog.innerText(),/100\.64\.0\.2.*yeni/);
    await dialog.getByRole("button",{name:"Vazgeç",exact:true}).click();
    assert.equal(writes.length,0); await localInput.fill("ayc");
    data.domain="ev"; data.tailscale="100.64.0.22";
    await page.reload(); await table.waitFor();
    assert.deepEqual(await guideValues(),["100.64.0.22","ev"],"Guide follows current server state");
    data.domain="ayc"; data.tailscale="100.64.0.2";
    await page.reload(); await table.waitFor();
    assert.equal(await table.locator("tbody tr").count(),3);
    // DD-195: only Panel's tailnet switch is fixed; its internet address is editable.
    const panelTail=row("panel").getByRole("switch",{name:"Panel Tailscale erişimi"});
    assert(await panelTail.isDisabled()); assert.equal(await panelTail.getAttribute("aria-checked"),"true");
    assert(!(await row("panel").getByRole("switch",{name:"Panel internet erişimi"}).isDisabled()));
    assert(!(await row("panel").getByRole("textbox").isDisabled()));
    assert.equal(await row("panel").getByRole("textbox").getAttribute("placeholder"),"panel.example.com");
    // Single click saves a typed domain: blur must not redraw away the clicked button.
    await row("torrent").getByRole("textbox").fill("torrent.example.net");
    await save("torrent").click(); await settled();
    assert.equal(writes.length,1); assert.equal(writes[0].web.domain,"torrent.example.net");
    assert.equal(writes[0].web.enabled,false);
    await row("torrent").getByRole("switch",{name:"qBittorrent internet erişimi"}).click();
    assert.equal(writes.length,1,"Switch only edits a draft");
    hold=true; await save("torrent").click();
    await row("torrent").getByText("Uygulanıyor…",{exact:true}).waitFor();
    assert(await row("paylasim").getByRole("textbox").isDisabled());
    assert(await row("torrent").getByRole("switch").first().isDisabled());
    assert.equal(writes.length,2); hold=false; release(); await settled();
    assert.equal(await row("torrent").getByRole("link").getAttribute("href"),"https://torrent.example.net");
    // Native validation and shared-host conflicts never reach the API.
    for(const bad of ["https://bad.example.net","dav.example.net","127.0.0.1","x.example.net/path"]) {
      await row("torrent").getByRole("textbox").fill(bad); await save("torrent").click();
      assert.equal(writes.length,2); assert.equal(await row("torrent").getByRole("textbox").evaluate(e=>e.checkValidity()),false);
    }
    await row("torrent").getByRole("button",{name:"Vazgeç"}).click();
    await row("paylasim").getByRole("switch",{name:"WebDAV Tailscale erişimi"}).click();
    failure="DNS veya sertifika doğrulanamadı."; await save("paylasim").click(); await settled();
    assert.equal(data.manage.publications[2].tail,true);
    assert.equal(await row("paylasim").getByRole("switch",{name:"WebDAV Tailscale erişimi"}).getAttribute("aria-checked"),"false");
    await save("paylasim").click();await settled();
    assert.equal(data.manage.publications[2].tail,false);
    await row("paylasim").getByRole("switch",{name:"WebDAV internet erişimi"}).click();await save("paylasim").click();await settled();
    assert.deepEqual(writes.at(-1).web,{service:"paylasim",tail:false,enabled:false,domain:"dav.example.net"});
    await page.reload(); await table.waitFor();
    assert.equal(await row("paylasim").getByRole("textbox").inputValue(),"dav.example.net");
    // Publishing Konsol needs the typed word; the dialog names the address and the DNS target.
    const before=writes.length, confirm=page.locator("dialog.as-dialog");
    await row("panel").getByRole("textbox").fill("konsol.example.net");
    await row("panel").getByRole("switch",{name:"Panel internet erişimi"}).click();
    await save("panel").click();
    assert.match(await confirm.innerText(),/https:\/\/konsol\.example\.net/);
    assert.match(await confirm.innerText(),/konsol\.example\.net → 192\.0\.2\.1/);
    assert.match(await confirm.innerText(),/Tailscale girişi etkilenmez/);
    await confirm.getByRole("textbox").fill("evet");
    await confirm.getByRole("button",{name:"Devam et",exact:true}).click();
    assert.equal(writes.length,before,"Only the typed word publishes Konsol");
    await confirm.getByRole("button",{name:"Vazgeç",exact:true}).click();
    assert.equal(writes.length,before); assert.equal(await confirm.count(),0);
    await save("panel").click();
    await confirm.getByRole("textbox").fill(" ONAYLA ");
    await confirm.getByRole("button",{name:"Devam et",exact:true}).click(); await settled();
    assert.deepEqual(writes.at(-1).web,{service:"panel",tail:true,enabled:true,domain:"konsol.example.net",confirm:"onayla"});
    assert.equal(await row("panel").getByRole("link").getAttribute("href"),"https://konsol.example.net");
    // Closing it from the tailnet address is a plain save.
    await row("panel").getByRole("switch",{name:"Panel internet erişimi"}).click();
    await save("panel").click(); await settled();
    assert.equal(await confirm.count(),0);
    assert.deepEqual(writes.at(-1).web,{service:"panel",tail:true,enabled:false,domain:"konsol.example.net"});
    for(const colorScheme of ["light","dark"]) {
      await page.emulateMedia({colorScheme});
      for(const width of [1440,1024,736,390,320]) {
        await page.setViewportSize({width,height:1100});
        assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`${colorScheme}/${width}`);
        const localBox=await local.boundingBox(), tableBox=await table.boundingBox(), guideBox=await guide.boundingBox();
        assert(localBox.width<=620 && localBox.width<=tableBox.width+1,"Local card is compact and responsive");
        if(width===1440) assert(localBox.width<tableBox.width*.65,"Address table retains full width");
        const inputBox=await localInput.boundingBox(), buttonBox=await local.getByRole("button",{name:"Güncelle",exact:true}).boundingBox();
        assert(buttonBox.x>=inputBox.x+inputBox.width && Math.abs(buttonBox.y+buttonBox.height-inputBox.y-inputBox.height)<2,"Input and Update share a row");
        assert(guideBox.y>inputBox.y+inputBox.height,"DNS instructions sit below the controls");
        for(const id of ["panel","torrent","paylasim"]) assert(await row(id).getByRole("textbox").isVisible());
        await page.screenshot({path:path.join(shots,`${colorScheme}-${width}.png`),fullPage:true});
      }
    }
    assert.deepEqual(errors,[]); console.log(JSON.stringify({ok:true,writes:writes.length,widths:5,themes:2,screenshots:shots}));
  } finally { await browser.close(); server.close(); }
})().catch(err=>{console.error(err);server.close();process.exitCode=1;});
