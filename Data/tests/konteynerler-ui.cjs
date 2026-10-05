/* Konteynerler (container manager) on the real console assets under the production CSP. Every API call
   is a fixture that follows Data/docs/design/container-manager-api.md: read routes, POST /islem with 202
   operations and GET /islem polling. No server is modified. Covers navigation and the old Settings link,
   name-only list/fixed action slots, lifecycle with confirmation/busy/failure, detail sections and logs, the shared
   create/edit/review/apply sheet (secrets, public ports, stopped saves, late answers), the App Store
   host-network adapter, removal, adoption preview, images/volumes/networks and their refusals, failed
   resource reads, keyboard use and the 390 px dark/light layout. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs"), os = require("node:os"), path = require("node:path");
const shots = fs.mkdtempSync(path.join(os.tmpdir(), "konsol-konteynerler-"));
const base = process.env.KONSOL_URL || "http://127.0.0.1:8766";
const csp = fs.readFileSync(path.join(__dirname, "../templates/Caddyfile"), "utf8").match(/Content-Security-Policy "([^"]+)"/)[1];
const magaza = path.join(__dirname, "../magaza");
const meta = (id) => JSON.parse(fs.readFileSync(path.join(magaza, id, "konsol.json"), "utf8").replace(/__DOWNLOADS_PATH__/g, "/srv/downloads").replace(/__[A-Z_]+__/g, "x"));
const T = Math.floor(Date.now() / 1000);
const hex = (n) => n.toString(16).padStart(32, "0");
const sha = (s) => "sha256:" + s.padEnd(64, "0");
const MB = 1024 * 1024;

/* ---------------- fixture state ---------------- */
const row = (o) => Object.assign({ id: "abc123def456", image: "", state: "running", status: "", unit: "", network: "konsol", ports: [], mounts: 0,
  created: T - 86400, started: T - 3600, exit_code: 0, restarts: 0, module_id: null, revision: "r1", live: true, actions: [], restricted_reason: "",
  health: null, cpu_percent: null, memory_bytes: null, busy: null }, o);
const S = {
  runtime: { version: "5.4.2", ok: true, error: "" },
  containers: [
    row({ name: "qbittorrent", management_id: "appstore:torrent", source: "appstore", module_id: "torrent", image: "lscr.io/linuxserver/qbittorrent@" + sha("b522f9f4"),
      unit: "qbittorrent.service", network: "torrent", mounts: 2, revision: "q1", actions: ["stop", "restart", "save", "remove", "image-update"], cpu_percent: 1.4, memory_bytes: 212 * MB,
      // DD-217: its own bridge; the backend labels each published address (the WAN one as internet access).
      ports: [{ host_ip: "127.0.0.1", host_port: 61006, container_port: 61006, protocol: "tcp", scope: "local" },
        { host_ip: "192.0.2.1", host_port: 61008, container_port: 61008, protocol: "tcp", scope: "public" },
        { host_ip: "192.0.2.1", host_port: 61008, container_port: 61008, protocol: "udp", scope: "public" }] }),
    row({ name: "jellyfin", management_id: "konsol:jellyfin", source: "konsol", image: "docker.io/jellyfin/jellyfin@" + sha("3c1a77e0"), unit: "jellyfin.service",
      ports: [{ host_ip: "100.64.0.2", host_port: 8096, container_port: 8096, protocol: "tcp" }, { host_ip: "127.0.0.1", host_port: 8920, container_port: 8920, protocol: "tcp" }],
      mounts: 2, revision: "j1", health: "healthy", actions: ["stop", "restart", "save", "remove", "image-update"], cpu_percent: 6.8, memory_bytes: 684 * MB }),
    row({ name: "uptime-kuma", management_id: "konsol:uptime-kuma", source: "konsol", id: "", image: "docker.io/louislam/uptime-kuma@" + sha("9a0e5d14"), unit: "uptime-kuma.service",
      state: "stopped", live: false, started: 0, ports: [{ host_ip: "100.64.0.2", host_port: 3001, container_port: 3001, protocol: "tcp" }], mounts: 1, revision: "u1",
      actions: ["start", "save", "remove"] }),
    row({ name: "deneme-nginx", management_id: "external:deneme-nginx", source: "external", image: "docker.io/library/nginx:1.27-alpine", network: "podman",
      state: "exited", exit_code: 0, ports: [{ host_ip: "0.0.0.0", host_port: 8088, container_port: 80, protocol: "tcp" }], revision: "n1",
      actions: ["start", "remove", "adopt"], restricted_reason: "Konsol dışında oluşturuldu; düzenlemek için önce sahiplenin." }),
    row({ name: "pod-uygulama", management_id: "external:pod-uygulama", source: "external", image: "docker.io/library/redis:7.4", network: "host", revision: "p1",
      actions: [], restricted_reason: "Bir pod'a bağlı; denetleyicisi bilinmediği için Konsol yalnız gösterir.", cpu_percent: 0.2, memory_bytes: 9 * MB,
      // DD-215: a host-network container has no mappings; the backend reports the sockets it listens on.
      listening: [{ address: "0.0.0.0", port: 6771, protocol: "udp", scope: "all" }, { address: "192.0.2.1", port: 51413, protocol: "tcp", scope: "wan" },
        { address: "2001:db8::1", port: 51413, protocol: "tcp", scope: "wan" }, { address: "100.64.0.2", port: 51413, protocol: "tcp", scope: "tailscale" },
        { address: "127.0.0.1", port: 51413, protocol: "tcp", scope: "local" }, { address: "192.0.2.1", port: 51413, protocol: "udp", scope: "wan" },
        { address: "2001:db8::1", port: 40000, protocol: "udp", scope: "wan" }, { address: "127.0.0.1", port: 61006, protocol: "tcp", scope: "local" }] }),
  ],
  images: [
    { name: "lscr.io/linuxserver/qbittorrent:5.2.4", id: sha("b522f9f4"), size: 228e6, created: T - 9e5, used_by: ["qbittorrent"], managed: false, pinned: true },
    { name: "docker.io/jellyfin/jellyfin:10.10.7", id: sha("3c1a77e0"), size: 1.2e9, created: T - 8e5, used_by: ["jellyfin"], managed: true, pinned: false },
    { name: "docker.io/louislam/uptime-kuma:1.23.16", id: sha("9a0e5d14"), size: 4.1e8, created: T - 7e5, used_by: ["uptime-kuma"], managed: true, pinned: false },
    { name: "docker.io/library/nginx:1.27-alpine", id: sha("c1d4a2f9"), size: 4.8e7, created: T - 6e5, used_by: ["deneme-nginx"], managed: false, pinned: false },
    { name: "docker.io/library/nginx:1.25-alpine", id: sha("77b0e1aa"), size: 4.3e7, created: T - 5e6, used_by: [], managed: true, pinned: false },
  ],
  volumes: [
    { name: "jellyfin-config", driver: "local", size: 312 * MB, used_by: ["jellyfin"], managed: true },
    { name: "uptime-kuma-data", driver: "local", size: 38 * MB, used_by: ["uptime-kuma"], managed: true },
    { name: "eski-deneme", driver: "local", size: 12 * MB, used_by: [], managed: true },
  ],
  // Podman's own default network comes first; a fresh host has only this one. The backend normalises subnets
  // to strings; the one raw {subnet, gateway} row checks that the page tolerates Podman's own shape.
  networks: [
    { name: "podman", id: "n2", driver: "bridge", subnets: ["10.88.0.0/16"], used_by: ["deneme-nginx"], managed: false, internal: false },
    { name: "konsol", id: "n1", driver: "bridge", subnets: [{ subnet: "10.89.0.0/24", gateway: "10.89.0.1" }], used_by: ["jellyfin", "uptime-kuma"], managed: true, internal: false },
    { name: "medya", id: "n3", driver: "bridge", subnets: ["10.89.1.0/24"], used_by: [], managed: true, internal: true },
  ],
  resource_errors: {},
};
const detailBase = (name) => {
  const r = S.containers.find((c) => c.name === name);
  return Object.assign({}, r, { image_digest: (r.image.split("sha256:")[1] || "").slice(0, 12), finished: 0, labels: {}, command: "", health: r.health || "" });
};
const D = {
  qbittorrent: { config: { listener_port: 61006, peer_port: 61008, save: "/srv/downloads" }, editable: ["listener_port", "peer_port", "save"],
    protected_mounts: [{ source: "/var/lib/qbittorrent", target: "/config", destination: "/config", reason: "Uygulama profili; taşıma ayrı bir işlemdir." }],
    effective_autostart: true,
    mounts: [{ type: "bind", source: "/var/lib/qbittorrent", destination: "/config", rw: true, name: "" }, { type: "bind", source: "/srv/downloads", destination: "/srv/downloads", rw: true, name: "" }] },
  jellyfin: { config: { name: "jellyfin", image: "docker.io/jellyfin/jellyfin@" + sha("3c1a77e0"), image_ref: "docker.io/jellyfin/jellyfin:10.10.7", network: "bridge",
      ports: [{ scope: "tailscale", host_port: 8096, container_port: 8096, protocol: "tcp", public_ack: false }, { scope: "local", host_port: 8920, container_port: 8920, protocol: "tcp", public_ack: false }],
      mounts: [{ type: "volume", source: "jellyfin-config", destination: "/config", read_only: false }, { type: "bind", source: "/srv/media", destination: "/media", read_only: true }],
      environment: [{ name: "TZ", value: "Europe/Istanbul", secret: false }, { name: "API_TOKEN", secret: true, present: true }],
      command: [], autostart: true, manual_stop: false, restart: "always", cpus: "2", memory: "2g" },
    editable: ["image", "network", "ports", "mounts", "environment", "command", "autostart", "restart", "cpus", "memory", "user"], protected_mounts: [],
    effective_autostart: true, user: "",
    mounts: [{ type: "volume", source: "/var/lib/containers/storage/volumes/jellyfin-config/_data", destination: "/config", rw: true, name: "jellyfin-config" }, { type: "bind", source: "/srv/media", destination: "/media", rw: false, name: "" }] },
  "uptime-kuma": { config: { name: "uptime-kuma", image: "docker.io/louislam/uptime-kuma@" + sha("9a0e5d14"), image_ref: "docker.io/louislam/uptime-kuma:1.23.16", network: "bridge",
      ports: [{ scope: "tailscale", host_port: 3001, container_port: 3001, protocol: "tcp", public_ack: false }],
      mounts: [{ type: "volume", source: "uptime-kuma-data", destination: "/app/data", read_only: false }], environment: [], command: [],
      autostart: true, manual_stop: true, restart: "on-failure", cpus: "", memory: "512m" },
    editable: ["image", "network", "ports", "mounts", "environment", "command", "autostart", "restart", "cpus", "memory"], protected_mounts: [],
    effective_autostart: false, mounts: [] },
  "deneme-nginx": { config: null, editable: [], protected_mounts: [], mounts: [] },
  "pod-uygulama": { config: null, editable: [], protected_mounts: [], mounts: [] },
};
const ops = {}, posts = [], errors = [], reads = [];
// DD-214: what the backend's cached registry check answers; the page never forces it on open.
const UPD = { qbittorrent: { state: "guncel", channel: "lscr.io/linuxserver/qbittorrent:latest", error: "" },
  jellyfin: { state: "guncel", channel: "docker.io/jellyfin/jellyfin:latest", error: "" },
  "uptime-kuma": { state: "guncel", channel: "docker.io/louislam/uptime-kuma:1.23.16", error: "" } };
let updChecked = T;
let opSeq = 0, holdOps = false, failNext = "", postError = null, listFail = false, holdModules = null;
const LOG_LINES = ["[08:12:04] Başlatma tamamlandı", "[08:14:31] Yavaş istek: /api/items 1840 ms", "[08:16:40] Yapılandırma okundu: API_TOKEN=****", "[08:18:09] Sağlık denetimi başarılı"];

function effect(op, body) {
  const c = S.containers.find((x) => x.name === body.name);
  const d = D[body.name];
  switch (body.action) {
    case "start": Object.assign(c, { state: "running", live: true, id: c.id || "fed654cba321", started: T, cpu_percent: 0.4, memory_bytes: 40 * MB, actions: c.source === "external" ? ["stop", "restart", "remove", "adopt"] : ["stop", "restart", "save", "remove"].concat(["jellyfin", "qbittorrent"].includes(c.name) ? ["image-update"] : []) });
      if (d && d.config && "manual_stop" in d.config) { d.config.manual_stop = false; d.effective_autostart = !!d.config.autostart; }
      break;
    case "stop": Object.assign(c, { state: c.source === "konsol" ? "stopped" : "exited", live: c.source !== "konsol", id: c.source === "konsol" ? "" : c.id, cpu_percent: null, memory_bytes: null,
      actions: c.source === "external" ? ["start", "remove", "adopt"] : ["start", "save", "remove"].concat(["jellyfin", "qbittorrent"].includes(c.name) ? ["image-update"] : []) });
      if (d && d.config && "manual_stop" in d.config) { d.config.manual_stop = true; d.effective_autostart = false; }
      break;
    case "restart": c.restarts += 1; break;
    case "remove": S.containers = S.containers.filter((x) => x !== c); delete D[body.name]; break;
    case "save": {
      if ("listener_port" in body.config) Object.assign(d.config, body.config);
      else {
        const keep = d.config.environment;
        d.config = JSON.parse(JSON.stringify(body.config));
        d.config.environment = body.config.environment.map((e) => e.secret ? { name: e.name, secret: true, present: !!(e.value || keep.find((k) => k.name === e.name)) } : e);
        d.config.manual_stop = c.state !== "running" && !body.start;
      }
      c.revision = c.revision + "+";
      if (body.start) Object.assign(c, { state: "running", live: true });
      break;
    }
    case "create": {
      const cfg = body.config;
      S.containers.push(row({ name: cfg.name, management_id: "konsol:" + cfg.name, source: "konsol", image: cfg.image_ref || cfg.image, unit: cfg.name + ".service",
        state: body.start ? "running" : "stopped", live: !!body.start, revision: "c1", actions: body.start ? ["stop", "restart", "save", "remove"] : ["start", "save", "remove"],
        ports: cfg.ports.map((p) => ({ host_ip: p.scope === "local" ? "127.0.0.1" : p.scope === "tailscale" ? "100.64.0.2" : "0.0.0.0", host_port: p.host_port, container_port: p.container_port, protocol: p.protocol })) }));
      D[cfg.name] = { config: Object.assign({ manual_stop: false }, cfg), editable: D.jellyfin ? D.jellyfin.editable : [], protected_mounts: [], effective_autostart: !!cfg.autostart, mounts: [],
        user: cfg.user === "downloads" ? "1000:1000" : "" };
      break;
    }
    case "adopt":
      if (body.preview) op.result = { preview: { config: { name: body.name, image: "docker.io/library/nginx@" + sha("c1d4a2f9"), image_ref: "docker.io/library/nginx:1.27-alpine", network: "bridge",
        ports: [{ scope: "public", host_port: 8088, container_port: 80, protocol: "tcp", public_ack: false }], mounts: [], environment: [{ name: "NGINX_HOST", value: "ornek", secret: false }],
        command: [], autostart: false, manual_stop: false, restart: "no", cpus: "", memory: "" }, unsupported: adoptUnsupported, fingerprint: "fp-1", requires_scope_review: true } };
      else Object.assign(c, { source: "konsol", management_id: "konsol:" + c.name, restricted_reason: "", actions: c.state === "running" ? ["stop", "restart", "save", "remove"] : ["start", "save", "remove"] });
      break;
    case "image-pull": S.images.push({ name: body.image, id: sha("ddee0011"), size: 3.3e7, created: T, used_by: [], managed: true, pinned: false }); break;
    case "image-remove": S.images = S.images.filter((i) => i.id !== body.image); break;
    case "image-update":
      c.revision += "u";
      if (UPD[body.name]) UPD[body.name].state = "guncel";
      op.result = { ok: true, changed: true, version: body.name === "qbittorrent" ? "5.2.5_v2.0.15-ls480" : "" };
      break;
    case "volume-create": S.volumes.push({ name: body.name, driver: "local", size: 0, used_by: [], managed: true }); break;
    case "volume-remove": S.volumes = S.volumes.filter((v) => v.name !== body.name); break;
    case "network-create": S.networks.push({ name: body.name, id: "n9", driver: "bridge", subnets: body.subnet ? [body.subnet] : ["10.89.9.0/24"], used_by: [], managed: true, internal: !!body.internal }); break;
    case "network-remove": S.networks = S.networks.filter((n) => n.name !== body.name); break;
  }
}
let adoptUnsupported = [];
function listBody() {
  const b = { read_at: Math.floor(Date.now() / 1000), runtime: S.runtime, containers: S.containers.map((c) => Object.assign({}, c)), images: S.images, volumes: S.volumes,
    networks: S.networks, storage: { images: S.images.length, containers: S.containers.length, size: 4.6e9 }, resource_errors: Object.assign({}, S.resource_errors) };
  for (const k of Object.keys(S.resource_errors)) b[k] = [];   // like the backend: the list stays empty, the error says why
  return b;
}
const holds = [];
function settle(op) {
  if (op.state !== "running") return;
  if (failNext) { op.state = "failed"; op.error = failNext; op.status = 1; op.step = "Başlatılıyor"; failNext = ""; }
  else { effect(op, op.body); op.state = "done"; op.step = "Tamamlandı"; }
  const c = S.containers.find((x) => x.name === op.body.name); if (c && c.busy === op.id) c.busy = null;
  op.updated_at = Math.floor(Date.now() / 1000);
}

(async () => {
  const browser = await chromium.launch({ headless: true, ...(process.env.PLAYWRIGHT_CHROMIUM ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM } : {}) });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    await context.route("**/*", async (route) => {
      const url = new URL(route.request().url());
      if (url.pathname.startsWith("/uygulama/")) {
        const file = path.join(magaza, url.pathname.slice("/uygulama/".length));
        return route.fulfill({ status: 200, contentType: url.pathname.endsWith(".css") ? "text/css" : "application/javascript", body: fs.readFileSync(file, "utf8") });
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
      const json = (status, body) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
      if (p.startsWith("/api/konsol/konteynerler/")) {
        reads.push(req.method() + " " + p + url.search);
        if (p.endsWith("/liste")) return listFail ? json(503, { error: "Podman envanteri okunamadı" }) : json(200, listBody());
        if (p.endsWith("/ayrinti")) {
          const name = url.searchParams.get("ad");
          if (!D[name]) return json(404, { error: "konteyner bulunamadı" });
          return json(200, Object.assign(detailBase(name), JSON.parse(JSON.stringify(D[name]))));
        }
        if (p.endsWith("/gunluk")) return json(200, { name: url.searchParams.get("ad"), lines: LOG_LINES, truncated: false, masked: true });
        if (p.endsWith("/guncellemeler")) {
          if (url.searchParams.has("yenile")) updChecked = Math.floor(Date.now() / 1000);
          return json(200, { checked_at: updChecked, items: JSON.parse(JSON.stringify(UPD)), cached: !url.searchParams.has("yenile") });
        }
        if (p.endsWith("/islem") && req.method() === "POST") {
          const body = req.postDataJSON();
          posts.push(body);
          if (postError) { const e = postError; postError = null; return json(e.status, { error: e.error }); }
          const id = hex(++opSeq);
          ops[id] = { id, action: body.action, name: body.name || body.image || "", state: "running", step: "Doğrulanıyor", body, polls: 0 };
          const c = S.containers.find((x) => x.name === body.name); if (c && body.action !== "create") c.busy = id;
          if (holdOps) holds.push(ops[id]);
          return json(202, { id, action: body.action, name: body.name || "", state: "running" });
        }
        if (p.endsWith("/islem")) {
          const op = ops[url.searchParams.get("id")];
          if (!op) return json(404, { error: "işlem yok" });
          op.polls++;
          if (!holds.includes(op)) settle(op);
          const { body, polls, ...out } = op;
          return json(200, out);
        }
        return json(404, { error: "yok" });
      }
      let result = {};
      if (p === "/api/konsol/moduller" && holdModules) await holdModules;
      if (p === "/api/konsol/moduller") result = { items: [{ id: "torrent", installed: true, state: S.containers.some((c) => c.name === "qbittorrent" && c.state === "running") ? "calisiyor" : "durduruldu",
        runtime: "konteyner", live: "running", busy: false, progress: null, durdurulabilir: true, konsol: meta("torrent"), sayfa: ["sayfa.js", "sayfa.css"], urls: { tailscale: "http://torrent.ayc", internet: null } }] };
      else if (p === "/api/uygulama/torrent/durum") result = { installed: true, running: true, unit: "qbittorrent.service", container: "qbittorrent", profile: "/var/lib/qbittorrent", downloads: "/srv/downloads", save: "/srv/downloads/", save_inside: true, temp: "", temp_on: false, temp_inside: false, ui: "127.0.0.1:61006", peer_port: 0, username: "admin" };
      else if (p === "/api/konsol/moduller/torrent/hesap") result = { user: "admin", temp: false };
      else if (p === "/api/konsol/kaynaklar") result = { host: "test", version: "test", domain: "ayc", os: "Debian 13", kernel: "test", uptime: 120, cores: 2, cpu: [1], mem: { total: 1000, used: 200 }, disk: { total: 1000, free: 500 }, root: "/srv", net: { tailscale: "100.64.0.2", wan: "192.0.2.1" }, read_at: Date.now() / 1000, sampled_at: Date.now() / 1000 };
      else if (p === "/api/konsol/saglik") result = { status: "ok", read_at: 1, checks: [] };
      else if (p === "/api/konsol/oturum") result = { durum: "acik", kullanici: "fixture", oturum_gun: 7, kanal: "tailscale" };
      else if (p === "/api/konsol/ag") { const now = Math.floor(Date.now() / 1000); result = { read_at: now, iface: "eth0", window: 120, sampled_at: now, rx: 1, tx: 1, points: [], apps: [] }; }
      else if (p === "/api/konsol/guncelleme") result = {kurulu:"2026.08.06-v2-131",son:"2026.08.06-v2-131",commit:"a".repeat(40),yeni:false,denetlendi:1,hata:"",baslatilabilir:true,is:{durum:"yok",hedef:"",mesaj:"",bitis:null,asama:""}};  // DD-233: up to date
      else if (p === "/api/konsol/duzen") result = { duzen: null };
      else if (p === "/api/konsol/ayarlar") result = { read_at: Date.now() / 1000, domain: "ayc", manage: { error: "fixture: ayarlar okunmuyor" } };
      else if (p === "/api/konsol/ayarlar/klasorler") result = { items: [{ path: "/srv/downloads", free: 10 * 1024 ** 3 }, { path: "/srv/media", free: 10 * 1024 ** 3 }] };
      else if (p === "/api/state") result = { root: "/srv", downloads: "downloads", protected: [], trash: { count: 0, size: 0 }, disk: { total: 1000, free: 500 } };
      else if (p === "/api/list") result = { path: "", entries: [] };
      else if (p === "/api/konsol/paylasim") result = { enabled: true, running: true, max: 32, host: "http://100.64.0.2:61010", items: [] };
      else if (p === "/api/trash" || p === "/api/konsol/islemler" || p === "/api/archives") result = { items: [] };
      else { errors.push("Unexpected endpoint: " + p); return route.fulfill({ status: 404, body: "unexpected" }); }
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(result) });
    });

    const cf = page.locator("#cf"), sheet = page.locator("#pd-sheet");
    const rowOf = (n) => page.locator(`.pd-row[data-name="${n}"]`);
    // Waits until every operation that is not deliberately held has finished and the page has redrawn.
    const settled = async () => { while (Object.values(ops).some((o) => o.state === "running" && !holds.includes(o))) await page.waitForTimeout(25); await page.waitForTimeout(250); };
    const noOverflow = async () => {
      const r = await page.evaluate(() => {
        const w = innerWidth, clipped = (e) => { for (let x = e.parentElement; x; x = x.parentElement) if (getComputedStyle(x).overflowX !== "visible") return true; return false; };
        const bad = [...document.querySelectorAll("body *")].filter((e) => e.getBoundingClientRect().right > w + 1 && !clipped(e))
          .slice(0, 5).map((e) => `${e.tagName}.${typeof e.className === "string" ? e.className : ""} ${Math.round(e.getBoundingClientRect().right)}`);
        return { ok: document.documentElement.scrollWidth <= w + 1, bad };
      });
      assert(r.ok, "no horizontal page scroll " + JSON.stringify(r.bad));
    };
    const focused = () => page.evaluate(() => { const a = document.activeElement; return a ? a.dataset.k || a.id || a.getAttribute("aria-label") || a.textContent.trim() : ""; });
    const listLayout = async () => {
      // Operation toasts temporarily cover the page; measure the settled list after they expire.
      await page.locator("#toast").waitFor({ state: "hidden", timeout: 8000 });
      await page.evaluate(() => window.scrollTo(0, 0));
      await noOverflow();
      const issues = await page.locator(".pd-row[data-name]").evaluateAll((rows) => rows.flatMap((r) => {
        const problems = [], bounds = r.getBoundingClientRect();
        for (const selector of [".pd-c-who", ".pd-c-state", ".pd-c-res", ".pd-c-access"]) {
          const cell = r.querySelector(selector), b = cell?.getBoundingClientRect();
          if (!b || !b.width || !b.height) problems.push(r.dataset.name + ": hidden " + selector);
        }
        // DD-214: the lead controls share the first cell; the name keeps readable room and neither it nor the
        // update chip runs into the status cell (the sidebar's narrow table becomes cards instead).
        const who = r.querySelector(".pd-c-who").getBoundingClientRect(), state = r.querySelector(".pd-c-state").getBoundingClientRect();
        const room = who.right - r.querySelector(".pd-nm").getBoundingClientRect().left;
        if (room < 100) problems.push(r.dataset.name + ": name squeezed to " + Math.round(room) + "px");
        for (const e of r.querySelectorAll(".pd-nm > *")) {
          const b = e.getBoundingClientRect();
          if (b.right > who.right + 1 || (b.right > state.left + 1 && b.left < state.right - 1 && b.bottom > state.top + 1 && b.top < state.bottom - 1))
            problems.push(r.dataset.name + ": " + e.className + " leaves the name cell");
        }
        const buttons = [...r.querySelectorAll(".pd-acts button")];
        buttons.forEach((b, i) => {
          const box = b.getBoundingClientRect(), previous = buttons[i - 1]?.getBoundingClientRect();
          if (box.width < 44 || box.height < 44 || box.left < bounds.left || box.right > bounds.right || (previous && previous.right > box.left))
            problems.push(r.dataset.name + ": clipped, overlapping or undersized " + b.dataset.act);
          const hit = document.elementFromPoint(box.left + 2, box.top + box.height / 2);
          if (box.top >= 0 && box.bottom < innerHeight && hit?.closest("button") !== b)
            problems.push(r.dataset.name + ": touch target intercepted " + b.dataset.act + " by " + hit?.tagName + "." + hit?.className + " at " + innerWidth);
        });
        return problems;
      }));
      if (issues.length) await page.screenshot({ path: path.join(shots, "layout-failure-" + page.viewportSize().width + ".png"), fullPage: true });
      assert.deepEqual(issues, [], "visible status/resources/access and distinct 44px controls; evidence: " + shots);
    };

    /* ---- navigation: Podman sidebar entry after App Store, apps only on Ana Menü (DD-216); old links redirect ---- */
    await page.goto(base + "/#/genel");
    await page.locator('#genel-tiles .tile[data-tile="torrent"]').waitFor();
    assert.deepEqual(await page.locator(".nav a:visible").allTextContents(), ["Ana Menü", "Dosyalar", "App Store", "Podman", "Ayarlar"]);
    assert.equal(await page.locator(".nav a[data-app], #installed-label").count(), 0, "an installed application has no sidebar entry");
    await page.locator('.nav a[data-route="ayarlar"]').click();
    await page.getByRole("tab", { name: "Sistem", exact: true }).waitFor();
    assert.deepEqual(await page.locator("#settings-page [role=tab]").allTextContents(), ["Sistem", "Güvenlik Duvarı", "Caddy", "Dnsmasq", "Günlük"], "Settings has no container tab any more");
    await page.evaluate(() => { location.hash = "#/ayarlar/konteynerler/jellyfin"; });
    await page.waitForFunction(() => location.hash === "#/konteynerler/jellyfin");
    await page.locator("#pd-detail-title").filter({ hasText: "jellyfin" }).waitFor();
    assert.equal(await page.locator('.nav a[data-route="konteynerler"]').getAttribute("aria-current"), "page");
    await page.locator('.nav a[data-route="konteynerler"]').click();
    await page.waitForFunction(() => location.hash === "#/konteynerler");
    // The hashchange handler repaints the header after the hash itself has changed.
    await page.waitForFunction(() => document.getElementById("title").textContent === "Podman");
    assert.equal(await page.locator("#eyebrow").innerText(), "Konteynerler · bu sunucu");

    /* ---- a cold load whose list answers before the application catalogue still names the App Store row ---- */
    let releaseModules;
    holdModules = new Promise((resolve) => { releaseModules = resolve; });
    await page.reload();  // a full load: the same URL with a hash alone would not reload the shell
    await rowOf("qbittorrent").waitFor();
    assert.equal(await rowOf("qbittorrent").locator(".pd-open").innerText(), "qbittorrent", "the container name until the catalogue arrives");
    const coldReads = reads.filter((r) => r.includes("/liste")).length;
    holdModules = null; releaseModules();
    await page.waitForFunction(() => document.querySelector('.pd-row[data-name="qbittorrent"] .pd-open')?.textContent === "qBittorrent");
    assert.equal(reads.filter((r) => r.includes("/liste")).length, coldReads, "repainted from the catalogue without another list read");

    /* ---- list: names only, retained columns, three accessible capability-aware action slots ---- */
    await rowOf("jellyfin").waitFor();
    assert.equal(await page.locator(".pd-row[data-name]").count(), 5);
    assert.match(await page.locator("#pd-summary").innerText(), /Podman 5\.4\.2/);
    assert.doesNotMatch(await page.locator("#pd-summary").innerText(), /undefined/);
    // Collect independent presentation failures so the test-first run records each missing requirement.
    const listFailures = [];
    const checkList = (fn) => { try { fn(); } catch (e) { listFailures.push(e.message); } };
    const headings = await page.locator(".pd-row.pd-head > span").allTextContents();
    checkList(() => assert.deepEqual(headings, ["Ad", "Durum", "Kaynak", "Erişim", ""], "name-only heading; no owner column"));
    for (const c of S.containers) {
      const r = rowOf(c.name), displayName = c.module_id ? meta(c.module_id).ad : c.name;
      const nameText = await r.locator(".pd-c-who").innerText();
      checkList(() => assert.equal(nameText, displayName, c.name + ": application/container name only"));
      const owners = await r.locator(".pd-c-src, .pd-src").count();
      checkList(() => assert.equal(owners, 0, c.name + ": no owner badge in the list"));
      const controls = await r.locator(".pd-acts button").evaluateAll((buttons) => buttons.map((b) => ({
        action: b.dataset.act, label: b.getAttribute("aria-label"), title: b.title,
        disabled: b.getAttribute("aria-disabled"), text: b.textContent.trim(), icons: b.querySelectorAll("svg[aria-hidden=true]").length,
        width: b.getBoundingClientRect().width, height: b.getBoundingClientRect().height,
      })));
      checkList(() => assert.deepEqual(controls.map((b) => b.action), ["svc", "edit", "remove"], c.name + ": lifecycle/edit/remove order"));
      const actions = [c.state === "running" ? "stop" : "start", "save", "remove"];
      const labels = [c.state === "running" ? "Durdur" : "Başlat", "Düzenle", "Kaldır"];
      controls.forEach((b, i) => checkList(() => {
        assert(b.label.startsWith(displayName + ": " + labels[i]), c.name + ": accessible action name");
        assert(b.title.includes(labels[i]), c.name + ": action tooltip");
        assert.equal(b.text, "", c.name + ": icon-only action");
        assert.equal(b.icons, 1, c.name + ": decorative icon");
        assert(b.width >= 44 && b.height >= 44, c.name + ": non-overlapping 44px touch target");
        assert.equal(b.disabled, c.actions.includes(actions[i]) ? "false" : "true", c.name + ": backend capability enforced");
        if (!c.actions.includes(actions[i])) {
          assert(b.title.includes(c.restricted_reason), c.name + ": disabled reason in tooltip");
          assert(b.label.includes(c.restricted_reason), c.name + ": disabled reason accessible");
        }
      }));
    }
    await page.screenshot({ path: path.join(shots, "list-desktop.png"), fullPage: true });
    assert.deepEqual(listFailures, [], "bounded list refinement; screenshot: " + path.join(shots, "list-desktop.png"));
    // DD-214: start/stop and edit right before the name, remove last; the home tiles' icons, bare like them.
    const order = await rowOf("jellyfin").evaluate((r) => {
      const box = (sel) => r.querySelector(sel).getBoundingClientRect();
      return { kids: [...r.querySelector(".pd-c-who").children].map((k) => k.classList[0]),
        svc: box('[data-act="svc"]').left, edit: box('[data-act="edit"]').left, name: box(".pd-open").left, remove: box('[data-act="remove"]').left, access: box(".pd-c-access").right };
    });
    assert.deepEqual(order.kids, ["pd-acts", "pd-ico", "pd-nm"], "lead controls, icon, name");
    assert(order.svc < order.edit && order.edit < order.name && order.remove > order.access, "start/stop → edit → name … remove: " + JSON.stringify(order));
    const shellJs = fs.readFileSync(path.join(__dirname, "../console/konsol.js"), "utf8");
    const iconD = (n) => shellJs.match(new RegExp("\\b" + n + ": '<path d=\"([^\"]+)\""))[1];
    const glyph = (n, act) => rowOf(n).locator(`[data-act="${act}"] svg path`).first().getAttribute("d");
    assert.equal(await glyph("jellyfin", "svc"), iconD("pause"), "running: pause, as on the home tiles");
    assert.equal(await glyph("uptime-kuma", "svc"), iconD("play"), "stopped: play");
    assert.equal(await glyph("jellyfin", "edit"), iconD("sliders"), "edit: the settings sliders");
    assert.equal(await glyph("jellyfin", "remove"), iconD("trash"));
    assert.deepEqual(await rowOf("jellyfin").locator('[data-act="edit"]').evaluate((b) => { const st = getComputedStyle(b); return [st.borderTopWidth, st.backgroundColor]; }),
      ["0px", "rgba(0, 0, 0, 0)"], "bare icon like the home tile actions");
    assert.equal(await page.locator(".pd-upd").count(), 0, "nothing to update yet");
    // DD-215: a host-network row shows the sockets its container listens on, one line per port (widest address).
    assert.deepEqual(await rowOf("pod-uygulama").locator(".pd-c-access > span").allInnerTexts(), ["192.0.2.1:51413/tcp+udp WAN · Tailscale · yerel",
      "127.0.0.1:61006/tcp Yalnız bu sunucu", "0.0.0.0:6771/udp Tüm adresler", "+1 port daha"]);
    // DD-217: the App Store app on its own bridge shows its three publications; the WAN one reads as internet access.
    assert.deepEqual(await rowOf("qbittorrent").locator(".pd-c-access > span").allInnerTexts(), ["127.0.0.1:61006 → 61006/tcp Yalnız bu sunucu",
      "192.0.2.1:61008 → 61008/tcp İnternet (açık)", "192.0.2.1:61008 → 61008/udp İnternet (açık)"]);
    assert(reads.some((r) => r.endsWith("/guncellemeler")), "the page asks for the cached update status on open");
    assert(!reads.some((r) => r.includes("/guncellemeler?yenile")), "opening the page never forces a registry check");
    await listLayout();
    assert.match(await rowOf("uptime-kuma").innerText(), /tanım kayıtlı/, "a stopped definition without a live container stays visible");
    assert.match(await rowOf("pod-uygulama").innerText(), /denetleyicisi bilinmediği için/, "the read-only reason is shown beside the controls");
    assert.equal(await rowOf("pod-uygulama").locator('button[data-act][aria-disabled="false"]').count(), 0, "no enabled controls without backend permission");
    // Programmatic clicks also cannot bypass disabled slots or silently adopt an external container.
    const beforeDisabled = reads.length;
    await page.locator('.pd-acts button[aria-disabled="true"]').evaluateAll((buttons) => buttons.forEach((b) => b.click()));
    assert.equal(posts.length, 0);
    assert.equal(reads.length, beforeDisabled);
    assert.equal(await sheet.evaluate((d) => d.open), false);
    assert.equal(await cf.evaluate((d) => d.open), false);
    assert.match(await rowOf("deneme-nginx").innerText(), /İnternet \(açık\)/);
    await rowOf("jellyfin").locator('[data-act="svc"]').focus();
    await page.keyboard.press("Tab");
    assert.equal(await focused(), "edit:jellyfin", "keyboard order follows the visual action order");
    await page.keyboard.press("Enter");
    await page.locator("#pd-f-image").waitFor();
    assert.equal(await page.locator("#pd-f-image").inputValue(), D.jellyfin.config.image_ref);
    await page.keyboard.press("Escape");
    await sheet.waitFor({ state: "hidden" });
    assert.equal(await focused(), "edit:jellyfin", "closing the editor returns focus to its row action");
    await page.keyboard.press("Tab");
    assert.equal(await focused(), "open:jellyfin", "the name follows the lead controls");
    await page.keyboard.press("Tab");
    assert.equal(await focused(), "remove:jellyfin");
    // Row controls preserve package-specific stop/remove disclosures and default data retention.
    await rowOf("qbittorrent").locator('[data-act="svc"]').click();
    await cf.getByText("qBittorrent durdurulsun mu?").waitFor();
    assert((await page.locator("#cf-list").innerText()).includes(meta("torrent").durdur_notu));
    await page.locator("#cf-cancel").click();
    for (const name of ["qbittorrent", "jellyfin", "deneme-nginx"]) {
      await rowOf(name).locator('[data-act="remove"]').click();
      await cf.waitFor({ state: "visible" });
      const disclosure = await page.locator("#cf-list").innerText();
      if (name === "qbittorrent") {
        assert.match(disclosure, /App Store/);
        assert.match(disclosure, /dosyalarınıza dokunulmaz/);
        assert.equal(await page.locator("#mod-veri").isChecked(), false);
      } else if (name === "jellyfin") {
        assert.match(disclosure, /birimler kalır/);
        assert.match(disclosure, /Sunucu klasörlerine dokunulmaz/);
      } else {
        assert.match(disclosure, /imaj ve birimler kalır/);
        assert.equal(await page.locator("#cf-go").isDisabled(), true);
      }
      await page.locator("#cf-cancel").click();
    }
    assert.equal(posts.length, 0, "row edit/cancel and removal cancellation never mutate state");
    await page.locator("#pd-q").fill("kuma");
    assert.equal(await page.locator(".pd-row[data-name]").count(), 1);
    assert.equal(await page.evaluate(() => document.activeElement.id), "pd-q", "typing keeps the search focused");
    await page.locator("#pd-q").fill("");
    await page.getByRole("button", { name: "Duran", exact: true }).click();
    assert.deepEqual(await page.locator(".pd-row[data-name]").evaluateAll((els) => els.map((e) => e.dataset.name)), ["uptime-kuma", "deneme-nginx"]);
    await page.getByRole("button", { name: "Tümü", exact: true }).click();

    /* ---- lifecycle: confirmation, busy without duplicates, completion refreshes App Store/overview ---- */
    const jStop = rowOf("jellyfin").locator('[data-act="svc"]');
    assert.equal(await jStop.getAttribute("aria-label"), "jellyfin: Durdur");
    await jStop.click();
    await cf.getByText("jellyfin durdurulsun mu?").waitFor();
    await page.locator("#cf-cancel").click();
    assert.equal(posts.length, 0, "cancel sends nothing");
    holdOps = true;
    await jStop.click();
    await page.locator("#cf-go").click();
    while (posts.length < 1) await page.waitForTimeout(20);
    assert.deepEqual(posts[0], { action: "stop", name: "jellyfin", revision: "j1" });
    await page.waitForFunction(() => document.querySelector('.pd-row[data-name="jellyfin"] [data-act="svc"]')?.getAttribute("aria-disabled") === "true");
    assert.equal(await rowOf("jellyfin").locator('[data-act="svc"]').getAttribute("aria-label"), "jellyfin: Durduruluyor…");
    assert.equal(await rowOf("jellyfin").locator('.pd-acts [aria-disabled="true"]').count(), 3, "busy disables every row action");
    await rowOf("jellyfin").locator(".pd-acts button").evaluateAll((buttons) => buttons.forEach((b) => b.click()));
    await page.waitForTimeout(150);
    assert.equal(posts.length, 1, "no duplicate request while busy");
    assert.equal(await cf.evaluate((d) => d.open), false);
    assert.equal(await sheet.evaluate((d) => d.open), false);
    const modReadsBefore = reads.length;
    holdOps = false; holds.splice(0);
    await page.waitForFunction(() => document.querySelector('.pd-row[data-name="jellyfin"] [data-act="svc"]')?.getAttribute("aria-label") === "jellyfin: Başlat", null, { timeout: 8000 });
    assert.match(await rowOf("jellyfin").innerText(), /tanım kayıtlı/);
    assert(reads.length > modReadsBefore, "the list is read again after the operation");
    // A worker failure arrives as a failed operation: shown, state unchanged.
    failNext = "İmaj bulunamadı: docker.io/louislam/uptime-kuma";
    await rowOf("uptime-kuma").locator('[data-act="svc"]').click();
    await page.getByText("İmaj bulunamadı: docker.io/louislam/uptime-kuma", { exact: false }).first().waitFor({ timeout: 8000 });
    assert.match(await rowOf("uptime-kuma").locator(".pd-error").innerText(), /Başlatılamadı/);
    assert.equal(await rowOf("uptime-kuma").locator('[data-act="svc"]').getAttribute("aria-label"), "uptime-kuma: Başlat");
    // An immediate refusal (409) is shown and the control stays usable.
    postError = { status: 409, error: "Bu konteynerde bir işlem sürüyor" };
    await rowOf("uptime-kuma").locator('[data-act="svc"]').click();
    await page.getByText("Bu konteynerde bir işlem sürüyor", { exact: false }).first().waitFor();
    assert.equal(await rowOf("uptime-kuma").locator('[data-act="svc"]').getAttribute("aria-disabled"), "false");
    // Additional operations remain on the detail page, including restart for a running package.
    await rowOf("qbittorrent").locator('[data-k="open:qbittorrent"]').click();
    await page.getByRole("button", { name: "Yeniden başlat", exact: true }).click();
    while (posts.at(-1).action !== "restart") await page.waitForTimeout(20);
    assert.deepEqual(posts.at(-1), { action: "restart", name: "qbittorrent", revision: "q1" });
    await settled();
    assert.equal(await page.locator(".pd-detail-head .pd-src").innerText(), "App Store");
    const packageImage = S.containers.find((c) => c.name === "qbittorrent").image;
    assert.equal(await page.locator(".pd-meta .mono").getAttribute("title"), packageImage, "full image information remains in details");
    assert.match(await page.locator(".pd-panel").textContent(), /lscr\.io\/linuxserver\/qbittorrent/);
    await page.evaluate(() => { location.hash = "#/konteynerler"; });

    /* ---- detail: sections, effective startup, logs ---- */
    await rowOf("uptime-kuma").locator('[data-k="open:uptime-kuma"]').click();
    await page.waitForFunction(() => location.hash === "#/konteynerler/uptime-kuma");
    await page.locator("#pd-detail-title").filter({ hasText: "uptime-kuma" }).waitFor();
    assert.match(await page.locator(".pd-panel").innerText(), /kayıtlı tanım/);
    await page.getByRole("tab", { name: "Başlatma ve sınırlar" }).click();
    assert.match(await page.locator(".pd-panel").innerText(), /Kapalı · siz durdurdunuz/, "manual stop overrides the autostart preference");
    await page.getByRole("tab", { name: "Günlük" }).click();
    await page.locator(".pd-log .pd-line").first().waitFor();
    await page.locator("#pd-logq").fill("sağlık");
    assert.equal(await page.locator(".pd-log .pd-line").count(), 1);
    assert.equal(await page.locator(".pd-log mark").innerText(), "Sağlık");
    await page.getByRole("tab", { name: "Genel" }).focus();
    await page.keyboard.press("ArrowRight");
    assert.equal(await page.evaluate(() => document.activeElement.textContent.trim()), "Ağ ve portlar");
    assert.match(await page.locator(".pd-panel").innerText(), /Varsayılan Konsol ağı · konsol/);
    await page.screenshot({ path: path.join(shots, "detail-desktop.png"), fullPage: true });

    /* ---- stopped save: edit uptime-kuma, review says it stays stopped, start stays false ---- */
    await page.getByRole("button", { name: "Düzenle", exact: true }).click();
    await page.locator("#pd-sheet-title").filter({ hasText: "uptime-kuma · düzenle" }).waitFor();
    await page.locator("#pd-f-memory").fill("768m");
    await page.locator("#pd-review").click();
    assert.match(await sheet.locator(".pd-diff").innerText(), /768m/);
    assert.match(await sheet.locator(".pd-conseq").innerText(), /durmuş kalır/);
    assert.equal(await page.locator("#pd-f-start").isChecked(), false);
    await page.locator("#pd-apply").click();
    await sheet.waitFor({ state: "hidden", timeout: 8000 });
    assert.equal(posts.at(-1).action, "save");
    assert.equal(posts.at(-1).start, false, "a stopped save stays stopped");
    assert.equal(posts.at(-1).revision, "u1");
    assert.equal(posts.at(-1).config.memory, "768m");
    assert.equal("manual_stop" in posts.at(-1).config, false, "manual_stop is server-controlled");

    /* ---- edit jellyfin: secret preserved, public port needs consent, draft survives a poll ---- */
    await page.evaluate(() => { location.hash = "#/konteynerler/jellyfin"; });
    await page.locator("#pd-detail-title").filter({ hasText: "jellyfin" }).waitFor();
    await page.getByRole("button", { name: "Düzenle", exact: true }).click();
    await page.locator("#pd-sheet-title").filter({ hasText: "jellyfin · düzenle" }).waitFor();
    const secret = page.locator('#pd-sheet input[data-env="API_TOKEN"]');
    assert.equal(await secret.inputValue(), "", "a stored secret is never echoed");
    assert.equal(await secret.getAttribute("type"), "password");
    await page.locator("#pd-add-port").click();
    await page.waitForFunction(() => document.activeElement && document.activeElement.id === "pd-p2-host");
    assert.equal(await page.locator("#pd-p2-scope").inputValue(), "local", "new ports start private");
    await page.keyboard.type("8097");
    await page.keyboard.press("Tab");
    await page.waitForTimeout(80);
    assert.equal(await focused(), "pd-p2-ctr", "Tab moves on after an edit");
    await page.keyboard.type("8096");
    await page.locator("#pd-p2-scope").selectOption("public");
    await page.waitForTimeout(80);
    assert.match(await sheet.innerText(), /Konsol oturumunu ve Caddy/);
    assert.equal(await page.locator("#pd-review").getAttribute("aria-disabled"), "true", "a public port needs explicit consent");
    await page.locator("#pd-p2-ack").check();
    await page.locator('#pd-sheet input[data-env-name="TZ"]').waitFor();
    await page.locator('#pd-sheet input[data-env="TZ"]').fill("UTC");
    await page.waitForTimeout(10500);   // one 10 s shell poll while the draft is open
    assert.equal(await page.locator('#pd-sheet input[data-env="TZ"]').inputValue(), "UTC", "the draft survives the poll");
    assert.equal(await page.locator("#pd-p2-host").inputValue(), "8097");
    await page.locator("#pd-review").click();
    const diff = await sheet.locator(".pd-diff").innerText();
    assert.match(diff, /8097/); assert.match(diff, /TZ/);
    assert.match(await sheet.locator(".pd-conseq").innerText(), /yeniden oluşturulur/);
    await page.screenshot({ path: path.join(shots, "edit-review.png") });
    holdOps = true;
    await page.locator("#pd-apply").click();
    while (posts.at(-1).action !== "save" || posts.at(-1).name !== "jellyfin") await page.waitForTimeout(20);
    const saved = posts.at(-1);
    assert.deepEqual(saved.config.environment, [{ name: "TZ", value: "UTC", secret: false }, { name: "API_TOKEN", secret: true }], "an unchanged secret is sent without a value");
    assert.deepEqual(saved.config.ports[2], { scope: "public", host_port: 8097, container_port: 8096, protocol: "tcp", public_ack: true });
    assert.equal(saved.start, false);
    await sheet.getByText("Doğrulanıyor", { exact: false }).waitFor();
    // Leave the running save and open another sheet; the late answer must not touch it.
    await page.keyboard.press("Escape");
    await sheet.waitFor({ state: "hidden" });
    const allNetworks = S.networks;
    S.networks = S.networks.filter((n) => n.name === "podman");   // a fresh host: only Podman's own network
    await page.evaluate(() => { location.hash = "#/konteynerler"; });
    await page.locator("#ct-new").click();
    await page.locator("#pd-sheet-title").filter({ hasText: "Yeni konteyner" }).waitFor();
    assert.deepEqual(await page.locator("#pd-f-network option").evaluateAll((o) => o.map((x) => [x.value, x.textContent])), [["bridge", "Varsayılan Konsol ağı"]],
      "the logical default is offered on a fresh host; Podman's own network is not");
    assert.equal(await page.locator("#pd-f-network").inputValue(), "bridge");
    await page.locator("#pd-f-image").fill("docker.io/library/nginx:1.27-alpine");
    holdOps = false; holds.splice(0);
    await page.getByText("jellyfin: değişiklikler uygulandı", { exact: false }).waitFor({ timeout: 8000 });
    assert.equal(await sheet.evaluate((d) => d.open), true, "a late answer does not close a newer sheet");
    assert.equal(await page.locator("#pd-f-image").inputValue(), "docker.io/library/nginx:1.27-alpine");

    /* ---- create: validation, review, start ---- */
    await page.locator("#pd-f-image").fill("nginx");
    await page.locator("#pd-f-image").press("Tab");
    await page.waitForTimeout(80);
    assert.match(await sheet.innerText(), /tam adını/);
    await page.locator("#pd-f-image").fill("docker.io/library/nginx:1.27-alpine");
    await page.locator("#pd-f-name").fill("web-deneme");
    await page.locator("#pd-add-port").click();
    await page.waitForFunction(() => document.activeElement && document.activeElement.id === "pd-p0-host");
    await page.keyboard.type("8099"); await page.keyboard.press("Tab"); await page.keyboard.type("80");
    await page.locator("#pd-add-env").click();
    await page.waitForFunction(() => document.activeElement && document.activeElement.id === "pd-e0-name");
    await page.keyboard.type("API_KEY"); await page.keyboard.press("Tab"); await page.keyboard.type("gizli-deger-123");
    await page.locator("#pd-e0-secret").check();
    assert.equal(await page.locator("#pd-f-user").inputValue(), "downloads", "DD-227: a new container runs as the Files account");
    await page.locator("#pd-review").click();
    assert.match(await sheet.locator(".pd-diff").innerText(), /web-deneme/);
    assert.match(await sheet.locator(".pd-diff").innerText(), /hesap\s*dosyalar hesabı/i);
    await page.locator("#pd-apply").click();
    await sheet.waitFor({ state: "hidden", timeout: 8000 });
    const created = posts.at(-1);
    assert.equal(created.config.user, "downloads");
    assert.equal(created.action, "create");
    assert.equal(created.start, true);
    assert.equal(created.config.name, "web-deneme");
    assert.equal(created.config.image_ref, "docker.io/library/nginx:1.27-alpine");
    assert.deepEqual(created.config.environment, [{ name: "API_KEY", value: "gizli-deger-123", secret: true }]);
    assert.equal(created.config.network, "bridge", "the worker creates the managed network on first use");
    S.networks = allNetworks;
    await rowOf("web-deneme").waitFor();
    // Leaving the page (browser back, a typed link) closes the sheet and drops its draft, like the overview's layout draft.
    await page.locator("#ct-new").click();
    await page.locator("#pd-f-image").fill("docker.io/library/redis:7.4");
    await page.evaluate(() => { location.hash = "#/genel"; });
    await sheet.waitFor({ state: "hidden", timeout: 4000 });
    await page.locator("#title #home-clock").waitFor();
    await page.evaluate(() => { location.hash = "#/konteynerler"; });
    await rowOf("web-deneme").waitFor();
    // Every generic save of a running container stops, recreates and starts it, limits and startup included.
    await rowOf("web-deneme").locator('[data-k="open:web-deneme"]').click();
    await page.getByText("1000:1000", { exact: true }).waitFor();  // DD-227: the account the process runs as
    await page.getByRole("button", { name: "Düzenle", exact: true }).click();
    await page.locator("#pd-f-cpus").waitFor();
    assert.deepEqual(await page.locator("#pd-f-network option").evaluateAll((o) => o.map((x) => x.value)), ["bridge", "konsol", "medya"],
      "the logical default plus managed bridges only");
    await page.locator("#pd-f-cpus").fill("1.5");
    await page.locator("#pd-review").click();
    const runningNote = await sheet.locator(".pd-conseq").innerText();
    assert.match(runningNote, /durdurulup yeni ayarlarla yeniden oluşturulur/);
    assert.match(runningNote, /kısa süre kesilir/);
    assert.doesNotMatch(runningNote, /canlı|etkilenmez/);
    assert.equal(await page.locator("#pd-f-start").count(), 0, "a running container needs no start box");
    assert.equal((await page.locator("#pd-apply").innerText()).trim(), "Uygula ve yeniden oluştur");
    await page.locator("#pd-cancel").click();
    await sheet.waitFor({ state: "hidden" });
    await page.evaluate(() => { location.hash = "#/konteynerler"; });

    /* ---- DD-227: writable server folders only with the Files account ---- */
    await rowOf("jellyfin").locator('[data-k="open:jellyfin"]').click();
    await page.getByRole("button", { name: "Düzenle", exact: true }).click();
    await page.locator("#pd-f-user").waitFor();
    assert.equal(await page.locator("#pd-f-user").inputValue(), "image", "a definition from before DD-227 keeps the image's account");
    await page.locator("#pd-m1-ro").uncheck();
    await page.waitForTimeout(80);
    assert.match(await sheet.innerText(), /yalnız Dosyalar hesabıyla yazılabilir/);
    assert.equal(await page.locator("#pd-review").getAttribute("aria-disabled"), "true", "the operator must switch the account explicitly");
    await page.locator("#pd-f-user").selectOption("downloads");
    await page.waitForTimeout(80);
    assert.doesNotMatch(await sheet.innerText(), /yalnız Dosyalar hesabıyla yazılabilir/);
    await page.locator("#pd-review").click();
    assert.match(await sheet.locator(".pd-diff").innerText(), /hesap\s*İmajın kendi hesabı.*→ Dosyalar hesabı/i);
    assert.match(await sheet.locator(".pd-conseq").innerText(), /bağlanan birim sahibini korur; Dosyalar hesabı ona yazamayabilir/);
    await page.locator("#pd-cancel").click();
    await sheet.waitFor({ state: "hidden" });
    await page.evaluate(() => { location.hash = "#/konteynerler"; });

    /* ---- DD-215: a host-network container's detail lists every listening address ---- */
    await rowOf("pod-uygulama").locator('[data-k="open:pod-uygulama"]').click();
    await page.getByRole("tab", { name: "Ağ ve portlar" }).click();
    // Every listening address, IPv6 too, with the note that the firewall decides outside access.
    const listen = page.locator('#pd-listen [role="row"]:not(.pd-mhead)');
    assert.equal(await listen.count(), 8);
    assert.deepEqual(await listen.nth(2).locator('[role="cell"]').allInnerTexts(), ["WAN", "2001:db8::1", "51413", "TCP"]);
    assert.match(await page.locator("#pd-listen").innerText(), /güvenlik duvarı belirler/);
    await page.evaluate(() => { location.hash = "#/konteynerler"; });

    /* ---- App Store adapter on its own bridge (DD-217): listener and save only, protected mount read-only ---- */
    await rowOf("qbittorrent").locator('[data-k="open:qbittorrent"]').click();
    await page.getByRole("tab", { name: "Ağ ve portlar" }).click();
    // textContent: the label is upper-cased by CSS (innerText would return "DİNLEYİCİSİ").
    assert.match(await page.locator(".pd-panel").textContent(), /Uygulama dinleyicisi/);
    assert.match(await page.locator(".pd-panel").textContent(), /127\.0\.0\.1:61006/);
    assert.match(await page.locator("#pd-app-net").innerText(), /kendi köprü ağında/);
    assert.match(await page.locator(".pd-panel").textContent(), /torrent/);
    const published = page.locator('.pd-panel .pd-mini[aria-label="Portlar"] [role="row"]:not(.pd-mhead)');
    assert.equal(await published.count(), 3);
    assert.deepEqual(await published.nth(1).locator('[role="cell"]').allInnerTexts(), ["İnternet (açık)", "192.0.2.1:61008", "61008", "TCP"]);
    assert.equal(await page.locator("#pd-listen").count(), 0, "a bridge app shows its publications, not host sockets");
    await page.getByRole("tab", { name: "Bağlamalar" }).click();
    assert.match(await page.locator(".pd-panel").innerText(), /korunur/);
    await page.getByRole("button", { name: "Düzenle", exact: true }).click();
    await page.locator("#pd-f-listener").waitFor();
    assert.equal(await page.locator("#pd-add-port").count(), 0, "no invented port mapping for a host-network app");
    assert.equal(await page.locator("#pd-f-save").inputValue(), "/srv/downloads");
    await page.locator("#pd-f-listener").fill("61016");
    await page.locator("#pd-review").click();
    assert.match(await sheet.locator(".pd-diff").innerText(), /61006 → 61016/);
    assert.match(await sheet.locator(".pd-conseq").innerText(), /durdurulup yeni ayarlarla yeniden başlatılır/);
    assert.equal(await page.locator("#pd-f-start").count(), 0, "an App Store adapter never offers start-after-save");
    assert.equal((await page.locator("#pd-apply").innerText()).trim(), "Uygula ve yeniden başlat");
    await page.locator("#pd-apply").click();
    await sheet.waitFor({ state: "hidden", timeout: 8000 });
    assert.deepEqual(posts.at(-1), { action: "save", name: "qbittorrent", revision: "q1", config: { listener_port: 61016, peer_port: 61008, save: "/srv/downloads" }, start: false });
    await settled();
    // DD-221: the adapter's declared peer port is edited here too: checked in the form, explained in the review.
    await page.getByRole("button", { name: "Düzenle", exact: true }).click();
    await page.locator("#pd-f-peer").waitFor();
    assert.equal(await page.locator("#pd-f-peer").inputValue(), "61008");
    assert.match(await sheet.locator(".pd-body").innerText(), /32768–60999 aralığının dışındadır/);
    for (const [value, why] of [["61016", /arayüz portundan farklı/], ["1000", /1024–65535/], ["6x", /1024–65535/]]) {
      await page.locator("#pd-f-peer").fill(value);
      await page.locator("#pd-f-peer").press("Tab");
      await page.waitForFunction((src) => new RegExp(src).test(document.querySelector("#pd-sheet .pd-ferr")?.innerText || ""), why.source);
      assert.equal(await page.locator("#pd-review").getAttribute("aria-disabled"), "true");
    }
    await page.locator("#pd-f-peer").fill("63900");
    await page.locator("#pd-f-peer").press("Tab");
    await page.waitForFunction(() => !document.querySelector("#pd-sheet .pd-ferr"));
    await page.locator("#pd-review").click();
    assert.match(await sheet.locator(".pd-diff").textContent(), /Eş portu[\s\S]*61008 → 63900/);
    assert.doesNotMatch(await sheet.locator(".pd-diff").innerText(), /Arayüz portu/);
    assert.match(await sheet.locator(".pd-conseq").innerText(), /Eski eş portu internete kapanır, yenisi WAN IPv4 adresinde TCP ve UDP/);
    await page.locator("#pd-apply").click();
    await sheet.waitFor({ state: "hidden", timeout: 8000 });
    assert.deepEqual(posts.at(-1), { action: "save", name: "qbittorrent", revision: "q1+", config: { listener_port: 61016, peer_port: 63900, save: "/srv/downloads" }, start: false });
    await settled();
    // An adapter that does not declare a peer port gets no such field and sends none.
    const declared = D.qbittorrent;
    D.qbittorrent = Object.assign({}, declared, { config: { listener_port: 61016, save: "/srv/downloads" }, editable: ["listener_port", "save"] });
    await page.getByRole("button", { name: "Düzenle", exact: true }).click();
    await page.locator("#pd-f-listener").waitFor();
    assert.equal(await page.locator("#pd-f-peer").count(), 0);
    await page.locator("#pd-f-listener").fill("61017");
    await page.locator("#pd-review").click();
    await page.locator("#pd-apply").click();
    await sheet.waitFor({ state: "hidden", timeout: 8000 });
    assert.deepEqual(posts.at(-1).config, { listener_port: 61017, save: "/srv/downloads" });
    await settled();
    D.qbittorrent = declared;
    // A stopped App Store app: the package keeps it stopped, so the review offers no start box either.
    const qb = S.containers.find((c) => c.name === "qbittorrent"), qbRunning = Object.assign({}, qb);
    Object.assign(qb, { state: "exited", cpu_percent: null, memory_bytes: null, actions: ["start", "save", "remove"] });
    await page.getByRole("button", { name: "Yenile", exact: true }).click();
    await page.getByRole("button", { name: "Başlat", exact: true }).waitFor();
    await page.getByRole("button", { name: "Düzenle", exact: true }).click();
    await page.locator("#pd-f-listener").waitFor();
    await page.locator("#pd-f-listener").fill("61026");
    await page.locator("#pd-review").click();
    assert.match(await sheet.locator(".pd-conseq").innerText(), /kesinti olmaz: ayarlar kaydedilir ve uygulama durmuş kalır/);
    assert.equal(await page.locator("#pd-f-start").count(), 0, "a stopped App Store app is not offered a start box");
    assert.equal((await page.locator("#pd-apply").innerText()).trim(), "Kaydet");
    await page.locator("#pd-cancel").click();
    await sheet.waitFor({ state: "hidden" });
    Object.assign(qb, qbRunning);
    await page.getByRole("button", { name: "Yenile", exact: true }).click();
    await page.getByRole("button", { name: "Durdur", exact: true }).waitFor();

    /* ---- DD-214: update check, row chip, package update and detail status ---- */
    await page.evaluate(() => { location.hash = "#/konteynerler"; });
    await rowOf("qbittorrent").waitFor();
    assert.match(await page.locator("#pd-upd-stamp").innerText(), /denetlendi/);
    UPD.qbittorrent.state = "var"; UPD.jellyfin.state = "var";
    await page.locator("#pd-upd-check").click();
    await rowOf("qbittorrent").locator(".pd-upd").waitFor();
    assert(reads.some((r) => r.endsWith("/guncellemeler?yenile=1")), "the button forces a check");
    assert.equal(await page.locator(".pd-upd").count(), 2);
    assert.equal(await page.locator("#pd-upd-count").innerText(), "2");
    assert.equal(await rowOf("uptime-kuma").locator(".pd-upd").count(), 0);
    await rowOf("qbittorrent").locator('[data-k="open:qbittorrent"]').focus();
    await page.keyboard.press("Tab");
    assert.equal(await focused(), "upd:qbittorrent", "the update chip follows the name");
    const qbRevision = S.containers.find((c) => c.name === "qbittorrent").revision;
    await page.keyboard.press("Enter");
    await cf.getByText("qBittorrent güncellensin mi?").waitFor();
    assert.match(await cf.innerText(), /lscr\.io\/linuxserver\/qbittorrent:latest/);
    assert.match(await page.locator("#cf-list").innerText(), /önceki imaja dönülür/);
    assert.match(await page.locator("#cf-list").innerText(), /indirilenler korunur/);
    await page.locator("#cf-go").click();
    while (posts.at(-1).action !== "image-update") await page.waitForTimeout(20);
    assert.deepEqual(posts.at(-1), { action: "image-update", name: "qbittorrent", revision: qbRevision });
    await settled();
    await page.waitForFunction(() => (document.querySelector("#toast")?.textContent || "").includes("qBittorrent: imaj güncellendi (5.2.5_v2.0.15-ls480)."));
    await page.waitForFunction(() => !document.querySelector('.pd-row[data-name="qbittorrent"] .pd-upd'));
    assert.equal(await page.locator("#pd-upd-count").innerText(), "1");
    await page.evaluate(() => { location.hash = "#/konteynerler/jellyfin"; });
    await page.locator("#pd-detail-title").filter({ hasText: "jellyfin" }).waitFor();
    assert.equal(await page.locator("#pd-upd-state").innerText(), "Yeni sürüm var");
    assert.match(await page.locator(".pd-panel").innerText(), /kanal: docker\.io\/jellyfin\/jellyfin:latest/);
    assert.equal(await page.getByRole("button", { name: "Güncelle", exact: true }).count(), 1, "the detail bar says Güncelle when a newer build exists");
    UPD.jellyfin.state = "guncel";
    await page.evaluate(() => { location.hash = "#/konteynerler"; });
    await page.locator("#pd-upd-check").click();
    await page.waitForFunction(() => document.querySelectorAll(".pd-upd").length === 0);

    /* ---- image update and removal flows ---- */
    await page.evaluate(() => { location.hash = "#/konteynerler/jellyfin"; });
    await page.locator("#pd-detail-title").filter({ hasText: "jellyfin" }).waitFor();
    await page.getByRole("button", { name: "İmajı güncelle", exact: true }).click();
    await cf.getByText("jellyfin güncellensin mi?").waitFor();
    assert.match(await page.locator("#cf-list").innerText(), /yeniden oluşturulur/);
    await page.locator("#cf-go").click();
    while (posts.at(-1).action !== "image-update") await page.waitForTimeout(20);
    assert.deepEqual(posts.at(-1), { action: "image-update", name: "jellyfin", revision: "j1+" });
    await settled();
    await page.getByRole("button", { name: "Kaldır", exact: true }).click();
    await cf.getByText("jellyfin kaldırılsın mı?").waitFor();
    assert.match(await page.locator("#cf-list").innerText(), /birimler.*kalır/i);
    await page.locator("#cf-cancel").click();
    await page.evaluate(() => { location.hash = "#/konteynerler/qbittorrent"; });
    await page.locator("#pd-detail-title").filter({ hasText: "qbittorrent" }).waitFor();
    await page.getByRole("button", { name: "Uygulamayı kaldır", exact: true }).click();
    await cf.getByText("qBittorrent kaldırılsın mı?").waitFor();
    assert.match(await page.locator("#cf-list").innerText(), /App Store/);
    assert.equal(await page.locator("#mod-veri").isChecked(), false);
    await page.locator("#cf-cancel").click();
    await page.evaluate(() => { location.hash = "#/konteynerler/deneme-nginx"; });
    await page.locator("#pd-detail-title").filter({ hasText: "deneme-nginx" }).waitFor();
    assert.equal(await page.getByRole("button", { name: "Düzenle", exact: true }).count(), 0, "no edit without save permission");
    await page.getByRole("button", { name: "Kaldır", exact: true }).click();
    assert.equal(await page.locator("#cf-go").isDisabled(), true, "an external container needs the typed confirmation");
    await page.locator("#cf-cancel").click();

    /* ---- adoption: server preview, explicit scope per port, unsupported options block ---- */
    await page.getByRole("button", { name: "Sahiplen", exact: true }).click();
    while (posts.at(-1).action !== "adopt") await page.waitForTimeout(20);
    assert.deepEqual(posts.at(-1), { action: "adopt", name: "deneme-nginx", preview: true });
    await page.locator("#pd-sheet-title").filter({ hasText: "deneme-nginx · sahiplen" }).waitFor({ timeout: 8000 });
    await page.locator("#pd-p0-scope").waitFor();
    assert.equal(await page.locator("#pd-p0-scope").inputValue(), "", "the operator chooses each port's scope");
    assert.match(await sheet.innerText(), /Şu an: İnternet \(açık\)/);
    assert.equal(await page.locator("#pd-f-network").inputValue(), "bridge");
    assert.match(await sheet.innerText(), /Şu an: podman/);
    assert.equal(await page.locator("#pd-apply").getAttribute("aria-disabled"), "true");
    await page.locator("#pd-p0-scope").selectOption("local");
    await page.waitForTimeout(80);
    await page.locator("#pd-apply").click();
    while (posts.at(-1).confirm !== true) await page.waitForTimeout(20);
    const adopt = posts.at(-1);
    assert.equal(adopt.preview_fingerprint, "fp-1");
    assert.equal(adopt.config.ports[0].scope, "local");
    assert.equal(adopt.config.network, "bridge");
    assert.equal(adopt.config.user, "image", "the adopt payload carries the account choice");
    await sheet.waitFor({ state: "hidden", timeout: 8000 });
    await page.waitForFunction(() => document.querySelector(".pd-detail-head .pd-src")?.textContent === "Konsol", null, { timeout: 8000 });

    /* ---- images: pull, in-use and package refusals, removal ---- */
    await page.evaluate(() => { location.hash = "#/konteynerler"; });
    await page.getByRole("tab", { name: /^İmajlar/ }).click();
    const imgRow = (n) => page.locator(`.pd-res[data-name="${n}"]`);
    await imgRow("docker.io/library/nginx:1.25-alpine").waitFor();
    assert.equal(await imgRow("lscr.io/linuxserver/qbittorrent:5.2.4").locator("[data-act=remove]").getAttribute("aria-disabled"), "true");
    assert.match(await imgRow("lscr.io/linuxserver/qbittorrent:5.2.4").locator("[data-act=remove]").getAttribute("title"), /paket/i);
    assert.equal(await imgRow("docker.io/jellyfin/jellyfin:10.10.7").locator("[data-act=remove]").getAttribute("aria-disabled"), "true");
    await imgRow("docker.io/library/nginx:1.25-alpine").locator("[data-act=remove]").click();
    await page.locator("#cf-go").click();
    while (posts.at(-1).action !== "image-remove") await page.waitForTimeout(20);
    assert.deepEqual(posts.at(-1), { action: "image-remove", image: sha("77b0e1aa") });
    await page.waitForFunction(() => !document.querySelector('.pd-res[data-name="docker.io/library/nginx:1.25-alpine"]'), null, { timeout: 8000 });
    await page.getByRole("button", { name: "İmaj çek", exact: true }).click();
    await page.locator("#pd-f-pull").fill("redis");
    await page.locator("#pd-apply").click();
    assert.match(await sheet.innerText(), /tam adını/);
    await page.locator("#pd-f-pull").fill("docker.io/library/redis:7.4-alpine");
    await page.locator("#pd-apply").click();
    await sheet.waitFor({ state: "hidden", timeout: 8000 });
    assert.deepEqual(posts.at(-1), { action: "image-pull", image: "docker.io/library/redis:7.4-alpine" });
    await imgRow("docker.io/library/redis:7.4-alpine").waitFor({ timeout: 8000 });

    /* ---- volumes and networks ---- */
    await page.getByRole("tab", { name: /^Birimler/ }).click();
    await page.locator('.pd-res[data-name="eski-deneme"]').waitFor();
    assert.equal(await page.locator('.pd-res[data-name="jellyfin-config"] [data-act=remove]').getAttribute("aria-disabled"), "true");
    await page.getByRole("button", { name: "Yeni birim", exact: true }).click();
    await page.locator("#pd-f-volume").fill("Kötü Ad");
    await page.locator("#pd-apply").click();
    assert.match(await sheet.innerText(), /küçük harf/i);
    await page.locator("#pd-f-volume").fill("yedek-veri");
    await page.locator("#pd-apply").click();
    await sheet.waitFor({ state: "hidden", timeout: 8000 });
    assert.deepEqual(posts.at(-1), { action: "volume-create", name: "yedek-veri" });
    await page.locator('.pd-res[data-name="eski-deneme"] [data-act=remove]').click();
    await page.locator("#cf-go").click();
    while (posts.at(-1).action !== "volume-remove") await page.waitForTimeout(20);
    assert.deepEqual(posts.at(-1), { action: "volume-remove", name: "eski-deneme" });
    await page.getByRole("tab", { name: /^Ağlar/ }).click();
    await page.locator('.pd-res[data-name="medya"]').waitFor();
    assert.match(await page.locator('.pd-res[data-name="konsol"]').innerText(), /10\.89\.0\.0\/24 \(ağ geçidi 10\.89\.0\.1\)/);
    assert.match(await page.locator('.pd-res[data-name="podman"]').innerText(), /10\.88\.0\.0\/16/);
    assert.doesNotMatch(await page.locator("#pd-tabpanel").innerText(), /object Object/);
    assert.equal(await page.locator('.pd-res[data-name="podman"] [data-act=remove]').getAttribute("aria-disabled"), "true");
    await page.getByRole("button", { name: "Yeni ağ", exact: true }).click();
    await page.locator("#pd-f-netname").fill("arka-ag");
    await page.locator("#pd-f-subnet").fill("10.89.7.0/24");
    await page.locator("#pd-f-internal").check();
    await page.locator("#pd-apply").click();
    await sheet.waitFor({ state: "hidden", timeout: 8000 });
    assert.deepEqual(posts.at(-1), { action: "network-create", name: "arka-ag", subnet: "10.89.7.0/24", internal: true });
    await page.locator('.pd-res[data-name="medya"] [data-act=remove]').click();
    await page.locator("#cf-go").click();
    while (posts.at(-1).action !== "network-remove") await page.waitForTimeout(20);
    assert.deepEqual(posts.at(-1), { action: "network-remove", name: "medya" });
    await settled();

    /* ---- a failed resource read is an error, not an empty collection ---- */
    S.resource_errors.volumes = "Birimler okunamadı: podman volume ls zaman aşımı";
    await page.getByRole("button", { name: "Yenile", exact: true }).click();
    await page.getByRole("tab", { name: /^Birimler/ }).click();
    await page.getByText("Birimler okunamadı: podman volume ls zaman aşımı", { exact: false }).waitFor();
    assert.equal(await page.locator(".pd-res").count(), 0);
    delete S.resource_errors.volumes;

    /* ---- desktop/tablet/phone: keep resource values and distinct touch targets in both themes ---- */
    await page.getByRole("tab", { name: /^Konteynerler/ }).click();
    for (const width of [1180, 1024, 768, 320]) {
      await page.setViewportSize({ width, height: 1000 });
      await listLayout();
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ colorScheme: "dark" });
    await page.waitForTimeout(150);
    await listLayout();
    await page.screenshot({ path: path.join(shots, "list-390-dark.png"), fullPage: true });
    await rowOf("jellyfin").locator('[data-k="open:jellyfin"]').click();
    await page.locator("#pd-detail-title").filter({ hasText: "jellyfin" }).waitFor();
    await noOverflow();
    await page.screenshot({ path: path.join(shots, "detail-390-dark.png"), fullPage: true });
    // A section tab beyond the phone's visible strip stays in view after it is chosen and repainted.
    await page.locator("#pd-sec-gunluk").click();
    await page.locator(".pd-log .pd-line").first().waitFor();
    const strip = await page.evaluate(() => {
      const b = document.querySelector(".pd-sec").getBoundingClientRect(), t = document.getElementById("pd-sec-gunluk").getBoundingClientRect();
      return { inside: t.left >= b.left - 1 && t.right <= b.right + 1, scrolled: document.querySelector(".pd-sec").scrollLeft > 0 };
    });
    assert(strip.inside && strip.scrolled, "the chosen Günlük tab stays visible in the scrolled strip: " + JSON.stringify(strip));
    await page.locator("#pd-sec-genel").click();
    await page.getByRole("button", { name: "Düzenle", exact: true }).click();
    await page.locator("#pd-f-image").waitFor();
    const box = await sheet.boundingBox();
    assert(box.x >= 0 && box.x + box.width <= 391, "the sheet fits the phone");
    await page.screenshot({ path: path.join(shots, "edit-390-dark.png") });
    await page.keyboard.press("Escape");
    await page.emulateMedia({ colorScheme: "light" });
    await page.evaluate(() => { location.hash = "#/konteynerler"; });
    await page.waitForTimeout(150);
    await listLayout();
    await page.screenshot({ path: path.join(shots, "list-390-light.png"), fullPage: true });

    /* ---- direct remove sends existing payloads: generic data kept, package cleanup opt-in only ---- */
    await rowOf("web-deneme").locator('[data-act="remove"]').click();
    await page.locator("#cf-go").click();
    await rowOf("web-deneme").waitFor({ state: "hidden", timeout: 8000 });
    assert.deepEqual(posts.at(-1), { action: "remove", name: "web-deneme", revision: "c1" });
    for (const withData of [false, true]) {
      const original = { ...S.containers.find((c) => c.name === "qbittorrent") }, originalDetail = D.qbittorrent;
      await rowOf("qbittorrent").locator('[data-act="remove"]').click();
      assert.equal(await page.locator("#mod-veri").isChecked(), false, "each package removal defaults to keeping data");
      if (withData) await page.locator("#mod-veri").check();
      await page.locator("#cf-go").click();
      await rowOf("qbittorrent").waitFor({ state: "hidden", timeout: 8000 });
      assert.deepEqual(posts.at(-1), { action: "remove", name: "qbittorrent", revision: original.revision, with_data: withData });
      S.containers.unshift(original); D.qbittorrent = originalDetail;
      await page.getByRole("button", { name: "Yenile", exact: true }).click();
      await rowOf("qbittorrent").waitFor();
    }

    assert.deepEqual(errors, []);
    console.log("PASS: sidebar Podman (title, eyebrow, no app entries) + cold-load app name + host-network listening ports (row and detail) + App Store app on its own bridge with per-address publications + old link redirect + Settings without the tab; name-only list with status/resources/access, no owner column, three capability-aware icon actions with accessible names/titles and 44px targets; disabled/busy actions send nothing; keyboard edit and focus return; stop confirm/busy/no duplicate/refresh, failed op, 409; restart and image metadata in details; detail sections/effective startup/logs; stopped save start:false; running save discloses recreation; edit with secret kept, public consent, draft across poll, late answer vs newer sheet; create on a fresh host with the logical default network; leaving the page closes the sheet; adapter listener/save and the declared peer port (form checks, review, payload; none when undeclared) without a start box (running/stopped); image update; direct removal with retained generic data and package data deletion opt-in; adoption preview with explicit scope; images/volumes/networks with refusals and subnet text; failed read; 1440/1024/768/390/320 layout, 390 dark/light and section tab kept in view. Screenshots: " + shots);
  } finally { await browser.close(); }
})().catch((err) => { console.error(err); process.exit(1); });
