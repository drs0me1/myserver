# Architecture

**Status:** current architecture for the installer tree under `Data/`.
Read [`contract.md`](contract.md) first — that document says *what* the installer
does; this one says *where each part of it lives* and *how data moves*.
Operator entry point: [`README.md`](../../README.md).

**Konsol (DD-160, DD-204, DD-206):** [Model A](model-a-clean-install.md) is a single-workspace
admin panel: sidebar with resource meters, an overview landing page (clock, status and
network widgets and application tiles, arranged in an edit mode and saved on the server),
App Store as tiles, installed app pages and tabbed Settings.
`panel.css` carries the CasaOS-inspired skin — palette, glass tokens, wallpaper
colours, tiles — over `konsol.css`'s base rules; the wallpaper itself is inline SVG in
`index.html`. Host CPU
sampling runs independently of WireGuard; the resources API
(`/api/konsol/kaynaklar`) does not enumerate networks or ports or invoke external
commands. Settings renders the base's tabs only; an application's settings belong to its
package page (`magaza/torrent/sayfa.js`, **DD-202**) and go to its API, which runs
the package worker directly (no draft, no confirmation). Folder/network edits of
the base retain their confirmation flow.

**Built-ins (DD-159/166/170):** Files, folder WebDAV and archive tools are built in.
Creation produces ZIP; extraction automatically detects multipart RAR and nested
ZIP/RAR, with internal safety limits. The App Store
catalogue contains WireGuard/qBittorrent only. `dosya`/`paylasim` are internal
paths and registry IDs, not public lifecycle operations.
The [archive architecture](desktop-and-archives.md) supplements this
document with the archive API and its security boundaries.

The ownership rule: one owner per fact and one owner per decision. A port,
path or chain name of the base is declared once (`config/defaults.env`); a
package's own defaults are declared once in its `magaza/<id>/<id>.env`, and a
durable Konsol override may replace only the keys the package allows
(`PAKET_AYAR_ANAHTARLAR`, `PACKAGE_OVERRIDES_DIR`; **DD-203**, **DD-214**,
**DD-220**). Each question (is this healthy? has the address changed?) has
exactly one answerer (§6).

---

## 1. Data flow

```
                     operator input
                   (SSH host, local domain)
                            │
                            ▼
              ┌──────────────────────────────┐
              │  /etc/master-stack/config.env│   persistent choices
              │  (rendered from              │   survives re-runs
              │   config/defaults.env)       │
              └──────────────┬───────────────┘
                             │
                             ▼
                    address detection
                    (install.sh + refresh-tailnet-config)
              WAN if + WAN IPv4, tailscale0
                    IPv4 + IPv6
                             │
                             ▼
              ┌──────────────────────────────┐
              │  /etc/master-stack/state.env │   detected runtime facts
              │  (regenerated every run and  │   never hand-edited
              │   by refresh-tailnet-config) │
              └──────────────┬───────────────┘
                             │
        ┌────────────┬───────┴────────┬──────────────┐
        ▼            ▼                ▼              ▼
    magaza/<id>   dnsmasq conf     Caddyfile     firewall
                  (lo +          (TAILSCALE_    (in memory)
                   tailscale0)    IPV4:80)
        │            │                │              │
        ▼            ▼                ▼              ▼
   master-modul   dnsmasq         caddy         MASTER-INPUT
   (from Konsol;   .service        .service      MASTER-FORWARD
    on loopback)
```

Only Caddy binds the Tailscale address (including Infuse
`${TAILSCALE_IPV4}:${SHARE_PORT}/s/<id>/`). dnsmasq and the firewall are written against
the *interface name*, and WebDAV binds loopback only (**DD-98**, **DD-158**).
That is what makes an address change a Caddy-only restart rather than a
stack-wide one. The legacy WAN HTTP share site exists only while a WAN
connection is enabled, unexpired and otherwise eligible. Configured HTTPS keeps
its listener for renewal even with no active folders, subject to the global
Caddy publication gate (**DD-179/190/191/192**).

Panel choices have a separate owner: `master_settings.py` commits firewall,
DNS and domain overrides to `/etc/master-stack/ayarlar.json`, which the installer
and service renderers preserve on re-runs. A confirmed domain takes precedence
over the installer input. qBittorrent account/path changes are the package worker's
(`magaza/torrent/ayar.py`, run by the backend as a transient unit) and go straight to
its own profile. The independent settings guard handles unconfirmed transactions;
DNS-only applies commit directly. WebDAV credentials go through
`master_shares.py` into a separate hash-only registry (§4).

---

## 2. `config.env` versus `state.env`

Two files, two lifetimes, two owners.

| | `config.env` | `state.env` |
|---|---|---|
| **Path** | `/etc/master-stack/config.env` | `/etc/master-stack/state.env` |
| **Contains** | Effective local domain and timezone | Detected facts plus runtime constants: WAN interface/addresses, `TAILSCALE_IPV4/6`, install version, paths/ports, the firewall's `VPN_BLOCK_DEST4/6`; no package setting (WireGuard's live in its package, **DD-201**) |
| **Source** | `config/defaults.env` + the domain answered in stage 0 (**DD-228**) | installer / `refresh-tailnet-config` at run time |
| **Written by** | The installer, once per run | The installer, `refresh-tailnet-config` when an address changes, and `master_settings.py` (only `LOCAL_DOMAIN`) on a confirmed domain change |
| **Lifetime** | Persistent; each run resolves defaults/input and any confirmed panel domain, then rewrites it | Regenerated from current constants and detected facts |
| **Hand-editable** | No — initial domain comes from installer input; later domain changes use Settings | No — it will be overwritten |
| **Read by** | The installer, template rendering | The installer, `master-firewall`, Caddy (`EnvironmentFile=`), `refresh-tailnet-config`, `wait-tailnet-addr`, `master-wg`, `master-modul` and the Konsol backends/workers (`master-panel`, `master_settings.py`, `master_shares.py`) |
| **Contains secrets** | **No** | **No** |

`config.env` is not a port editor. Constants live in `config/defaults.env`;
WireGuard network ports live in `/etc/wireguard/networks`. Panel overrides live
in `ayarlar.json`. Changing a detected address is not a human action.

`state.env` holds *current* facts only. The public IPv4 is re-detected on every
run; it is never recorded as an expectation that later checks compare against
reality.

---

## 3. File responsibilities

### 3.1 Repository layout

```
.
├── kur.sh                             server bootstrap: curl … | sudo bash downloads the repo and starts install.sh (DD-228)
├── wireguard.command                  WireGuard peer menu (double-click; calls master-wg over SSH)
├── kurulum/                           wireguard.command input: kurulum.env (SSH_HOST); wireguard/ (only profiles + QR .png that wireguard.command was asked to download; DD-143) (Git-ignored)
├── README.md, CLAUDE.md               entry points
├── .cursor/rules/master-stack.mdc     repository rules (not shipped to host)
└── Data/
    ├── install.sh                     orchestration
    ├── common.sh                      logging, guards, file writing, rendering
    ├── config/defaults.env            single source of truth for constants
    ├── templates/                     Caddyfile, dnsmasq.conf
    ├── scripts/                       installed to /usr/local/sbin (firewall.sh → master-firewall, …)
    ├── systemd/                       units, timers and drop-ins
    ├── magaza/<id>/                   store packages: WebDAV (paylasim), qBittorrent (torrent), WireGuard (wireguard) files
    ├── panel/                         Konsol root backend (master-panel; loads package API modules), settings and share workers, WebDAV service
    ├── files-panel/                   unprivileged file/archive backend (Python), API only
    ├── console/                       Konsol pages, styles and scripts (one origin, no external loads)
    ├── docs/                          contract, architecture, design decisions, feature notes; archive/
    ├── tests/                         Bats, Python, browser and Linux suites (not shipped)
    ├── CHANGELOG.md, SESSION.md       change log and working notes (not shipped)
    └── OKUBENI.txt                    Turkish operator notes (not shipped)
```

The root holds only what the operator double-clicks. Paths in the rest of this
document are relative to `Data/`. The exporter ships only the runtime subset
(§8), unpacked on the host under `/root/debian-server-installer`.

`.cursor/rules/` covers the repository tree. It describes how to build this
installer and ships no runtime behaviour — nothing installs it,
nothing reads it at run time — so it appears in the repository layout and
nowhere in §3.4's host layout.

One rule set, one active file:

| Path | Role |
|---|---|
| `.cursor/rules/master-stack.mdc` | **The active source.** Plain text with repository-wide frontmatter. Edits to the rules go here and only here. |
| `docs/archive/master-stack-rules-source.rtf` | **Archive.** The operator's original RTF, byte-for-byte, kept as the historical record. Never edited, never loaded. |

Cursor never parses the `.rtf` as a rule, so it lives in the archive rather
than beside the real rule file. There is deliberately **no synchronisation
mechanism and no test** comparing the two: the archive is a snapshot of
what was first written, not a second copy of the truth, and it is expected
to fall behind as the `.mdc` evolves.

Three documents govern the installer, and they are not interchangeable:

| Source | Governs |
|---|---|
| `.cursor/rules/` | How to work: process, Bash conventions, per-phase verification, the hard "do not" list |
| `docs/contract.md` | What the result must do, and the success criteria |
| `docs/architecture.md` | Where each part lives and how data moves |

The rules describe working constraints; the contract and its linked feature
documents describe runtime behaviour. Settled questions are listed in §10.
Update stale summaries instead of treating old wording as a new requirement.

### 3.2 One sentence per file

| File | Single responsibility | Deliberately does not know |
|---|---|---|
| `.cursor/rules/master-stack.mdc` | Carry the working rules for any AI assistant editing this tree — the single active, editable rule source | Anything about runtime behaviour — it is never installed to the host and never read by the installer |
| `install.sh` | Read the operator's input file, call the stages in order (including address detection), print the summary | What a firewall rule looks like, what Caddy syntax is |
| `common.sh` | Logging, error trapping, the root/OS gates, the stack lock, bounded network retry, atomic file installation, template rendering | Any stack-specific fact |
| `config/defaults.env` | Declare every constant exactly once: ports, paths, chain names, interface name, the WebDAV registry path | How any of them is used |
| `templates/Caddyfile` | The base HTTP sites and their upstreams (loopback, root backend socket), the admin API socket (**DD-180**), the timeouts of the optional WAN share listeners (**DD-179/190**), scoped proxy logging (**DD-193**), plus `import CADDY_MODULES_DIR/*.caddy` for module sites (**DD-149**) | The Tailscale address (read as `{$TAILSCALE_IPV4}` from `state.env` at daemon start); which modules are installed |
| `magaza/wireguard/master-wg` | Installed on the host only with the WireGuard package (**DD-196**). WireGuard networks and peers, profiles/QR, DNS settings; coordinate internet-only network firewall changes | Installer inputs or anything on the Mac |
| `panel/master-panel` | Root `/api/konsol/*` and, for installed packages, `/api/uygulama/<id>/*` handed to the package's API module (**DD-200**) on a Unix socket only Caddy's group and root can open (**DD-180**), Host/CSRF gates, resources, read-only health checks (**DD-182**), audit/settings views and fixed worker dispatch | Static pages; module installation implementation; any TCP listener |
| `panel/master_settings.py` | Validate/apply settings, snapshot/rollback/confirm with independent guard, render committed overrides | Arbitrary shell commands, client-visible password hashes |
| `panel/master_shares.py`, `panel/master_webdav.py` | Root-owned folder-account registry with independent Tailscale/WAN policies, WAN site projection and its guard; separate unprivileged WebDAV data service (§4) | Shared plaintext credentials or a writable symlink share tree |
| `panel/master_auth.py`, `scripts/master-konsol` | Konsol account (the public name's credential, **DD-205**), sessions, the per-address attempt limit and the shared public budget/bounded password checks (**DD-195**); the root CLI for reset/state/automation sessions (**DD-194**) | Passwords or tokens in clear text, multi-user roles, anything outside `KONSOL_AUTH_DIR` |
| `console/giris.html`, `giris.js`, `giris.css` | The public name's sign-in page (**DD-194**; **DD-205**: the tailnet needs no sign-in and is sent back to Konsol) | Any other Konsol data or API |
| `panel/master_https.py`, `panel/master_publications.py` | Public-name validation, DNS check and pinned certificate probe; the fixed Panel/qBittorrent/WebDAV publication table, its private 403 stubs (address line taken from the module template) and the public qBittorrent and Konsol sites (**DD-190/191/193/195**) | ACME keys or renewal (Caddy owns them), DNS writes, arbitrary upstreams |
| `panel/master_permissions.py` | Installer-only descriptor-pinned creation and selective owner/mode repair of the user data tree (**DD-187**) | Symlinks, special or hard-linked files, the private `.arsiv`/`.pay` trees |
| `panel/master_containers.py`, `panel/master_container_manager.py`, `console/konteynerler.{js,css}` | Main-sidebar container manager, the Podman page: read-only Podman mapper plus ownership-aware inventory, resource tabs, operation broker and console (**DD-211**, **DD-216**); host-network listening sockets from `/proc` (**DD-215**); reads remain in the backend sandbox, writes dispatch a bounded root transient unit | Raw shell execution from the browser; secret environment values in responses; taking over another controller |
| `panel/master_container_config.py`, `panel/master_container_worker.py` | Private definitions, validated Quadlet rendering, explicit generic lifecycle/recreation/adoption and resource operations under install/module/container locks; revision checks and durable operation results | Package lifecycle (uses `master-modul` and declared adapters); deleting bind data or volumes with a container; reconciliation |
| `panel/master_container_binds.py` | A Konsol container's `ExecStartPre`/`ExecStopPost`: walk each bind source without following links, pin it through its descriptor onto `KONTEYNER_BAGLAMA_DIR/<name>/<hash>`, verify, release on stop (**DD-226**); stdlib only, no store, package code or lock | Package containers; deciding which folders may be bound (save-time validation) |
| `panel/master_container_network.py` | Exact project-owned nftables forward guard for managed bridges (publications in; what a container may open out, **DD-224**), validated binding scopes and host-port conflicts; applied by the locked writers (firewall, worker, engine); container units only check it before they start (**DD-223**) | Netavark NAT, third-party chains, arbitrary host-network containers |
| `scripts/master-modul` | Package lifecycle from manifests and hooks (apt, tools, drop-ins, a container application's quadlet and digest-pinned image (**DD-209**), names, Konsol page files), the install form's private seed `RUNTIME_DIR/modul-<id>.kur` for packages with `PAKET_KUR_AYAR` (required, handed to hooks as `KUR_TOHUM`, always removed, **DD-210**), registry/progress/locks; installer-only `yerlesik` activates/checks built-in Files/WebDAV and their names, retaining accounts (**DD-159**, **DD-197**, **DD-200**) | Any application name; templates and inputs; user files; public removal of built-ins |
| `magaza/<id>/` | One package: `paket.env` manifest and `kanca` hooks (**DD-197**), its Konsol files `konsol.json` (App Store texts, page declaration, journal words), `sayfa.js`/`sayfa.css` (the page, served from `CONSOLE_WEB_DIR/uygulama/<id>/` while installed) and `api.py` (the backend module behind `/api/uygulama/<id>/*`, **DD-200**; qBittorrent's runs its worker `ayar.py` through `ctx.worker`, **DD-202**), an optional install/settings form (`konsol.json` `form` with the manifest's `PAKET_KUR_AYAR` worker, **DD-210**), its own settings file `<id>.env` and the folders it writes into (`PAKET_KLASORLER`, optional `klasorler.py` report) plus the paths the root backend may write for it (`PAKET_ARKAUC_YOLLAR`, **DD-203**) and an optional traffic module for the overview's network card (`PAKET_TRAFIK`, `trafik.py`, **DD-206**), plus its files as templates, rendered by the installer to `MODULES_DIR/<id>/`: `paylasim/master-paylasim.service` (the folder WebDAV unit), `paylasim.caddy`, `dnsmasq.conf` (**DD-148**, **DD-158**); `torrent/qBittorrent.conf` (first settings only), `qbittorrent.container` (the Podman quadlet: pinned image, its own bridge with the interface published on loopback and the peer port on the WAN IPv4, two same-path mounts, **DD-209**, **DD-217**), `torrent.caddy`, `dnsmasq.conf` (**DD-151**); `wireguard/master-wg` and `wg-quick-master-stack.conf`, placed on the host by `master-modul kur`/`uygula` and removed by `kaldir` (**DD-196**) | Whether the package is installed |
| `files-panel/master-files-panel` | File API as downloads uid; Host/CSRF gates, descriptor-safe paths, no-overwrite operations (the editor's version-checked atomic save the one exception, **DD-249**), `.cop` trash, text and archive jobs. In `--sistem` mode (unit `master-sistem-dosya`, root, **DD-235**): the same API under `/api/sistem/*` for `/`, tailnet peers only, permanent delete, no read-only roots (**DD-238**) | Anything outside `SERVER_ROOT` (the `/srv` unit); WebDAV credentials; WireGuard administration |
| `files-panel/master_archives.py`, `files-panel/master_rar.py` | Single bounded ZIP creation or ZIP/RAR extraction job; descriptor-safe paths, resource-limited RAR subprocess, private staging, atomic publication and history | Root privileges, shell extraction, backups or resumable jobs |
| `console/duzenleyici.js`, `tools/duzenleyici/` | Files' text editor: a CodeMirror 6 bundle loaded on first use, built reproducibly from pinned packages; `tools/` stays in the repository (**DD-249**) | Any request of its own; inline styles (CSP) |
| `console/panel.css`, `console/arsiv.js` | Model A shell styling and archive dialogs plus the running-job bar with cancellation (no jobs page; results in Günlük, **DD-183**), using the real file API | OS sessions, fake progress, service credentials |
| `console/index.html`, `konsol.css`, `konsol.js`, `ayarlar.{js,css}`, `dosyalar.{js,css}` | Files, folder shares, App Store, sidebar resources and tabbed Settings, plus the page registry (`window.Konsol.sayfa`) that mounts installed packages' pages from their declarations (**DD-200**; opened from Ana Menü tiles, no sidebar links, **DD-216**); served by Caddy from `CONSOLE_WEB_DIR`, same-origin only (**DD-160**) | Any application name or page of its own; Keys — it asks for a QR or profile only when the operator does; file contents as HTML — names and text are inserted as text only |
| `templates/dnsmasq.conf` | Base `panel` name and fail-closed resolver on `lo` + `tailscale0`; built-in WebDAV and installed qBittorrent add their own files | The current address (`bind-dynamic` tracks it) |
| `scripts/tailscale-udp-gro` | Set the two ethtool flags on the default-route interfaces | Tailscale itself |
| `scripts/firewall.sh` → `master-firewall` | Project INPUT/FORWARD/NAT plus `MASTER-SETTINGS`, using installed apps, network registry and confirmed overrides; `--check` verifies critical policy | Other software's chain contents; the Tailscale address (matches its interface) |
| `scripts/refresh-tailnet-config` | Detect Tailscale address changes, update state and restart Caddy; bounded failed-Caddy recovery, independent firewall check/reapply and reopening failed WireGuard networks once the firewall check passes (DD-87/94/180) | General module health, file drift, disk space or stack-wide reconciliation |
| `scripts/wait-tailnet-addr` | Caddy `ExecStartPre`: wait until `tailscale0` carries the expected IPv4; fail fast on a stale one | Caddy configuration |
| `systemd/` | Ordering, coupling, restart policy and schedules of units, timers and drop-ins | The contents of the scripts they start |
| `../kur.sh` | Download the repository archive, place the runtime tree atomically and start `install.sh` on the terminal | Anything the installer does |
| `tests/` | Assert the contract, once per fact | Implementation details of the scripts |

### 3.3 Placeholder convention

Templates use `__NAME__` tokens, not `${NAME}` and not `{$NAME}`. Both of
those already have meanings in the generated files: systemd expands
`${…}` in unit command lines, and Caddy expands
`{$TAILSCALE_IPV4}` from `state.env` at daemon start. A distinct install-time
token makes it impossible to confuse "substituted once, by the installer"
with "expanded later, by the consumer".

Rendering is a single function in `common.sh`; it substitutes tokens,
writes to a temporary file, sets owner and mode, and renames atomically. A
template with an unsubstituted `__…__` token left in the output is a hard
error, not a warning.

### 3.4 Runtime layout on the host

| Host path | Written by | Contents |
|---|---|---|
| `/etc/master-stack/config.env` | installer | operator choices, `0600` |
| `/etc/master-stack/state.env` | installer, `refresh-tailnet-config`, `master_settings.py` (domain) | detected addresses and identification, `0600` |
| `/etc/master-stack/webdav.json` | `master_shares.py` | Schema 4: independent folder accounts, scrypt hashes and folder identity; each item's `connections.tailscale` and `connections.wan` owns enabled/permission/expiry; 0600 root, systemd credential (DD-158, DD-192) |
| `/etc/master-stack/konsol/` (`KONSOL_AUTH_DIR`) | `master-panel`, `master-konsol` (installer creates it 0700) | `hesap.json` (user, scrypt hash), `oturumlar.json` (SHA-256 of tokens, expiry; at most 16), `duzen.json` (the overview layout: tile order, widget order and visibility, **DD-206**, **DD-242**); 0600 root (**DD-194**, **DD-205**) |
| `/etc/master-stack/ayarlar.json`, `ayarlar-bekleyen.json` | `master_settings.py` | Committed firewall/DNS/domain choices and pending transaction recovery; the independent guard rolls unconfirmed work back |
| `/var/lib/qbittorrent/` | qBittorrent (module) | hidden from Files, WebDAV and unrar (`PRIVATE_STATE_ROOT`, **DD-225**); its profile, the container's `/config`: settings (seeded once by `master-modul`) and torrent list, owned by the downloads uid (**DD-151**, **DD-209**) |
| `/etc/containers/systemd/qbittorrent.container` (`KONTEYNER_BIRIM_DIR`) | `master-modul` (qBittorrent) | the Podman quadlet; the generator writes `qbittorrent.service` from it; present only while the app is installed and not stopped (**DD-209**) |
| `/etc/containers/systemd/qbittorrent.container.d/90-konsol.conf` | qBittorrent's worker `ayar.py` | one same-path bind mount for a download folder outside the downloads tree (**DD-209**) |
| `/etc/master-stack/containers/` (`KONTEYNER_STATE_DIR`) | container worker (**DD-211**) | private definitions, environment files and operation results, 0700 directories/0600 files; no secret values returned by the broker |
| `/run/master-stack/konteyner-baglama/<name>/<hash>` (`KONTEYNER_BAGLAMA_DIR`) | `master_container_binds.py` (unit `ExecStartPre`) | bind anchors of running Konsol containers; root-owned 0700, recreated at every start, detached on stop, gone at reboot (**DD-226**) |
| `/etc/containers/systemd/konsol-<name>.container` | container worker | generated only on explicit operations; digest-pinned image, managed bridge, ports/mounts, startup policy; manual stop omits the boot target |
| `/etc/master-stack/package-overrides/` (`PACKAGE_OVERRIDES_DIR`) | declared package adapter | private, allowlisted settings that survive installer rendering; qBittorrent listener port also projects to `85-konteyner.conf` and Caddy; its peer port (DD-221) to the Quadlet's WAN publications, `TORRENTING_PORT` and the container guard |
| `/var/lib/containers/storage/` | Podman (base, **DD-208**) | images and container layers; qBittorrent's image is pinned by digest and removed by `kaldir --veri` |
| `/etc/wireguard/networks` | `master-wg` | Networks wg0…wg9 (`WG_NETWORKS_MAX` in the package's `wireguard.env` is the highest slot index): port, fixed `inet` policy column, addresses, default DNS, label; `0600` |
| `/etc/wireguard/wgN.conf` | `master-wg` (the installer writes none, **DD-143**) | that network's key, peer public keys, PSKs, `AllowedIPs` (**DD-124**), `0600` |
| `/etc/wireguard/clients-wgN/<name>.conf` | `master-wg` | device profiles for `profile`/`qr`, `0600` in a `0700` directory |
| `/etc/modules-load.d/master-stack-wireguard.conf` | `master-modul` (WireGuard) | `wireguard`, `0644`; removed with the module (**DD-150**) |
| `/usr/local/sbin/master-wg` | installer | peer list/add/remove/profile/qr, `0755` |
| `/usr/local/sbin/master-panel`, `master_settings.py`, `master_shares.py`, `master_webdav.py`, `master_https.py`, `master_publications.py` | installer | Root API, settings/account/publication workers and unprivileged WebDAV handler; pages are separate |
| `/usr/local/sbin/master-files-panel`, `master_archives.py`, `master_rar.py`; `/usr/local/share/master-stack/konsol/` | installer | file backend and archive workers, and the console pages Caddy serves (**DD-139**, **DD-140**) |
| `/usr/local/sbin/master-modul`, `/usr/local/share/master-stack/moduller/<id>/` | installer | module helper and rendered module files, `0755` / `0644` (**DD-148**) |
| `/etc/master-stack/moduller` | `master-modul` (installer creates it empty) | installed modules: `id<TAB>calisiyor\|durduruldu`, `0644` (**DD-148**) |
| `/etc/master-stack/moduller-bekleyen/<id>` (`MODULES_PENDING_DIR`) | installer | empty marker: the package's rendered files (or a built-in's code) changed and have not been applied yet; removed after a successful `uygula`/`yerlesik` or when the package is not installed; `0700` directory (**DD-222**) |
| `/run/master-stack/modul-<id>.ilerleme`, `modul.lock` | `master-modul` | the last operation's progress line; the module lock (**DD-148**) |
| `/etc/caddy/moduller/<id>.caddy` | installer (directory), `master-modul` (files) | module sites imported by the base Caddyfile; WebDAV: `paylas.<domain>` and `TAILSCALE_IPV4:SHARE_PORT` (**DD-98**, **DD-158**) |
| `/etc/caddy/moduller/paylasim-wan.caddy` | `master_shares.py` | Global-gated WAN WebDAV site, `/s/*` only: legacy `WAN_IPV4:SHARE_PORT` while an eligible WAN connection exists, or configured HTTPS on `SHARE_HTTPS_PORT` retained for renewal without active folders (**DD-179/190/191/192**); stale WAN binding fails closed (**DD-182**) |
| `/etc/caddy/moduller/torrent-wan.caddy` | `master_shares.py` (via `master_publications.py`) | Public qBittorrent HTTPS on the shared `SHARE_HTTPS_PORT`, only while enabled, running and its native login gates pass (**DD-191**) |
| `/etc/dnsmasq.d/modul-<id>.conf` | `master-modul` | module names; WebDAV: `interface-name=paylas.<domain>,tailscale0` (**DD-148**) |
| `SERVER_ROOT/.cop/` | installer (folder), file panel (contents) | Trash: `<id>/<item>` plus `<id>.json` (origin, time); outside downloads and excluded from WebDAV/qBittorrent access |
| `SERVER_ROOT/.arsiv/`, `jobs.json` | unprivileged archive worker | private staging (0700) and last 20 jobs (0600); excluded from installer recursive permission repair; never a backup (**DD-159**) |
| `SERVER_ROOT/.pay/` (`SHARE_DIR`) | nothing (reserved name) | Never created, read or removed; if present it stays hidden/blocked in Files, WebDAV and qBittorrent and is skipped by permission repair (**DD-171**) |
| `/etc/apt/apt.conf.d/20auto-upgrades`, `52master-stack-unattended` | installer | periodic unattended upgrades on, automatic reboot off (**DD-113**), Tailscale and Caddy origins added (**DD-184**), `0644` |
| `/etc/systemd/system/apt-daily-upgrade.timer.d/master-stack.conf` | installer | upgrade window at `APT_UPGRADE_TIME` (04:00, up to 30 min random delay) instead of 06:00 (**DD-184**) |
| `/etc/dnsmasq.d/local-services.conf` | installer | Base `panel` record/resolver policy, `0644`; other names in separate managed files |
| `/etc/caddy/Caddyfile` | installer | The `(konsol)` snippet (static/API routes, session check), the tailnet panel site importing it, and imported service sites, `0644`; `moduller/panel-wan.caddy` is the generated public Konsol site (**DD-195**) |
| `/usr/local/sbin/{tailscale-udp-gro,master-firewall,refresh-tailnet-config,wait-tailnet-addr}` | installer | `0755` |
| `/etc/systemd/system/{tailscale-udp-gro,master-firewall,refresh-tailnet-config,master-panel,master-settings-guard,master-share-network}.service`, `{refresh-tailnet-config,master-settings-guard,master-share-network}.timer` | installer | `0644`; the settings guard enforces rollback deadlines, the share-network timer runs the WebDAV WAN guard every 30 s (**DD-179**) |
| `/etc/systemd/system/master-sistem-dosya.service` | installer (`ensure_system_files`) | Files' "Sistem (/)" view as root on `SYSTEM_FILES_SOCKET` (**DD-235**) |
| `/etc/systemd/system/master-paylasim.service`, `master-files-panel.service` | `master-modul yerlesik`, from the installer's renders in `MODULES_DIR/paylasim/` and `MODULES_DIR/dosya/` | built-in WebDAV and file/archive backends, always enabled (**DD-159**) |
| `/etc/systemd/system/wg-quick@.service.d/master-stack.conf` | installer | a WireGuard network starts only after `master-firewall --check` passes (**DD-180**); `wg-quick@.service` comes from `wireguard-tools`; `master-wg` enables `wg-quick@wgN` |
| `/etc/systemd/system/{caddy,dnsmasq}.service.d/master-stack.conf` | installer | drop-ins, `0644` |
| `/run/master-stack/` | helpers | ephemeral runtime state (the stack lock) |
| `/var/log/master-setup/` | installer | run logs, `0700` dir / `0600` files |

`/usr/local/share/master-stack` contains live static assets and module templates,
not a canonical recovery copy. There is no generation pointer or runtime
restore manifest.

Two absences in that table are decisions rather than oversights.

**There is no rendered Caddy environment file.** Caddy's drop-in reads
`/etc/master-stack/state.env` directly as its `EnvironmentFile=`, so the
address exists in exactly one place on disk and `refresh-tailnet-config`
has one file to update instead of two. The cost is a formatting
constraint: `state.env` must be parseable both by `source` in bash and by
systemd's `EnvironmentFile=`, which means plain `KEY=value` lines with no
unescaped shell expansion or spaces around `=`. Prefix lists use double quotes. That constraint is
the writer's job to enforce, and the test suite asserts it.

**No module needs Tailscale or WAN facts in its own files.** Web UIs and
WebDAV bind loopback (**DD-151**, **DD-158**). The one exception is the opt-in
WAN share site, which `master_shares.py` projects from `WAN_IPV4` in
`state.env` (**DD-179**).

---

## 4. Folder WebDAV ownership (DD-158/DD-192)

Folder form / connection cards → root API → fixed master_shares.py worker
(stdin) → 0600 root webdav.json (scrypt hashes, root identity, independent
Tailscale/WAN enabled/permission/expiry policies) → systemd LoadCredential →
unprivileged master_webdav.py → validated descriptors.

Schema 4 has no authoritative shared permission/expiry/pause/networks fields.
Valid schema 3 loads convert in memory; `prepare` persists the conversion.
Both policies copy the exact old permission and absolute expiry; only previously
selected networks on an unpaused share are enabled. IDs, account salt/hash,
folder identity and creation/change timestamps stay unchanged. Schema 2 and
schema-4 legacy-policy conflicts are rejected. Nested partial API updates merge
under operation locks without resetting omitted policies or expiry; old global
updates and pause calls return a refresh-page error. Shared folder/account/password
management is separate from connection controls.

The file-manager backend sees no credential. Caddy's global publication gates
control the tailnet name and `TAILSCALE_IPV4:SHARE_PORT`, and configured WAN HTTPS
or consent-gated legacy `WAN_IPV4:SHARE_PORT`. `/s/<id>/` selects one folder/account
shared by both connection policies. The WebDAV process listens
on `127.0.0.1` (tailnet) and `SHARE_WAN_BACKEND` (WAN) on the same port; the
listener, not a header, selects enabled/permission/expiry enforcement, including
all DAV writes, live chunks and staged PUT/COPY final publication. Authentication
cache hits never bypass that authorization. Share edits restart the active data
service, cutting all existing transfers. Per-folder
isolation is in the handler, not separate OS sandboxes. No per-share listener
is needed.

`master_shares.py` also owns the WAN projection: it writes or removes
`paylasim-wan.caddy`, and `master-share-network.timer` runs its guard every
30 s to close ineligible legacy HTTP WAN publications and finish interrupted
changes. It retains configured HTTPS for renewal under the existing global gate.

The public projection feeds two cards, each with switch, permission, expiry,
address/copy and Infuse details. Each connection adds expired/available/active/reason
and a candidate URL when its transport is available, even if locally off or expired.
Global Caddy gates override both cards and explain unavailable routes; `row.urls`
contains only active connections. A candidate address is not proof of reachability.

See [folder-shares.md](folder-shares.md) for protocol limits, security boundaries
and tests.

---

## 5. Address change handling

Each consumer of an address is handled according to what it actually binds:

| Consumer | Binds to | On Tailscale address change |
|---|---|---|
| dnsmasq | `lo` and `tailscale0` **by name** | Nothing — `interface-name` + `bind-dynamic` follow the interface, and the config is never regenerated |
| Caddy | `{$TAILSCALE_IPV4}` read from `state.env`; the opt-in WAN share site binds `WAN_IPV4` | Restarted after `state.env` is updated |
| WebDAV | `127.0.0.1` (tailnet) and `SHARE_WAN_BACKEND` (WAN), loopback only | Nothing — loopback listeners do not track Tailscale |
| Module services | no Tailscale bind | Nothing — no App Store module binds a Tailscale address |
| Konsol containers | a port with Tailscale scope is published on `TAILSCALE_IPV4` | `refresh-tailnet-config` leaves `RUNTIME_DIR/containers-tailnet.pending` and starts the bounded `master-container-tailnet-refresh` worker (`RuntimeMaxSec=900`); it recreates only containers whose Tailscale bindings changed, keeps stopped ones stopped, and the marker stays for the next round if it fails (**DD-211**) |
| Firewall | `tailscale0` **by name**; configured service allowlist and registered WG ports; Self PeerAPI ports per family (DD-172) | Existing restart hook/watchdog regenerates changed PeerAPI ports; ordinary listener discovery never grants access |

`refresh-tailnet-config` owns the Tailscale side of this table, and its
scope is bounded: read IPv4/IPv6, compare with `state.env`, and update it and
restart Caddy when needed. Independently of address changes, it runs the
firewall's own check and reapplies a broken firewall (DD-94), can recover a
failed Caddy (DD-87), and reopens failed WireGuard networks once the firewall
check passes (DD-180). It has no general module health, file drift, disk-space or
binary-version reconciliation. The address-only rows above describe IP effects,
not these separately bounded recovery paths.

Two rows above say "nothing" for structural reasons worth naming, because
they are what keep the helper small. dnsmasq and the firewall are both
written against the *interface name* rather than the address it currently
carries, so the address can change — or `tailscale0` can be destroyed and
recreated — with no file to regenerate and no rule to reinstall.

**A Tailscale address change never restarts an App Store module.** Modules
publish on loopback or on the WAN address, so Caddy is the one service
restarted. Konsol containers with a Tailscale-scope port are the one bounded
exception (the hand-off in the table above, **DD-211**).

**Public IPv4 change.** These name the WAN address:
- the opt-in WAN share site and the public HTTPS sites of packages and Konsol
  (**DD-191**, **DD-195**), which Caddy binds to `WAN_IPV4`;
- qBittorrent's peer-port publication, rendered with `WAN_IPV4` into its
  Quadlet (**DD-217**);
- Konsol containers with a public-scope port, which listen on every address
  while the container guard admits them only for the WAN interface's addresses
  as of its last apply.

If the provider changes the address, `master_shares.py` reports WAN as
unavailable ("kurulumu yeniden çalıştırın"), the 30-second guard removes every
WAN site, and a Caddy that could not start on the old address is started without
it. qBittorrent's peer port stays closed, because the guard admits no stale
address, until an installer run re-renders and re-applies the package. An
installer re-run records the new `WAN_IPV4`, drops a site bound to the stale
address before restarting Caddy, and stage 7 republishes it (**DD-182**).
`master-firewall` re-applies on boot and on a Tailscale restart and reads
current WAN facts from `state.env` / the interface.
WireGuard profiles take `WAN_IPV4` from `state.env` as their endpoint at creation
time; profiles that baked an old endpoint still need manual client updates
(**DD-138**, **DD-201**). `refresh-tailnet-config` does not track the WAN address.

---

## 6. Decision ownership

Each question has exactly one owner, so two implementations can never disagree.

| Question | Single owner |
|---|---|
| What is the WAN interface / WAN IPv4 / WAN IPv6 / Tailscale IPv4 / IPv6? | `install.sh` (write) / `refresh-tailnet-config` (update) |
| Is the firewall policy in force? | `scripts/firewall.sh` installed as `/usr/local/sbin/master-firewall --check` |
| Has the Tailscale address changed? | `scripts/refresh-tailnet-config` |
| Is a module healthy? | **Nobody.** systemd's `Restart=` handles crashes; `master-modul` checks only when it installs, starts or re-applies |
| Has a managed file drifted? | **Nobody.** Re-running the installer is the repair |
| Is the stack working end to end? | The final verification stage, once |
| Is a port number correct? | `config/defaults.env` |

A check that appears in two of these rows is an installer bug, not defence in
depth. Konsol's health card (**DD-182**) only reads and reports; it answers
none of these questions for the installer.

---

## 7. Installer stage outline

| Stage | Work | Owns |
|---|---|---|
| 0 | Gates (root, tty, supported OS, nft `iptables`, ufw inactive, lock, inhibit); detect release change; reject pending Settings transaction, keep the confirmed or previous domain, ask it only on a first install (no default), one confirmation; write `config.env` | operator input |
| 1 | Suspend third-party restart managers (**DD-103**); `apt update`; `full-upgrade` on every run (**DD-228**); base packages — only what the base uses (**DD-153**: no gnupg, gawk or apache2-utils); `podman netavark aardvark-dns` without recommends and a `podman info` check (**DD-208**); timezone; unattended-upgrade policy and its 04:00 window (**DD-113**, **DD-184**) | `apt` |
| 2 | Tailscale: repository, package, sysctls, UDP GRO, login with 410 recovery, exit-node and SSH preferences | `tailscaled` |
| 3 | Address detection → `state.env`; selective downloads ownership/mode repair (**DD-84**) | installer |
| 4 | Install scripts and workers; render module files, units, timers and the firewall-first `wg-quick@` drop-in (**DD-180**); enable the settings guard timer | templates |
| 5 | Apply `master-firewall` (WireGuard rules come from the registry, and only while the WireGuard module is installed; none when it is empty), which also applies the container forward guard (`master_container_network.py`, **DD-211**, **DD-217**); enable refresh timer. The WireGuard layer (`wireguard-tools`, `qrencode`, kernel module, `/etc/wireguard`, starting the registry's networks) belongs to the WireGuard module since **DD-150** | firewall |
| 6 | dnsmasq/Caddy, Konsol root backend/pages, Files/archive code and staged unit; drop a WAN share site bound to a stale address (**DD-182**); restart changed services only | DNS/HTTP |
| 7 | `master-modul yerlesik` enables/checks Files/WebDAV; publish the WAN share site and enable its guard timer (**DD-179**); reapply changed optional apps (including changes a failed earlier run left pending, **DD-222**) and installed WireGuard; `master-firewall --check` (with the container guard) and the `podman info` check; core contracts, Caddy/API gates and optional network checks (**DD-159**) | verification |
| — | Print summary and the manual Tailscale admin steps | operator guidance |

**Addresses are detected once, in stage 3, into `state.env`**, and every later
stage reads them from there instead of re-deriving them.

---

## 7.1 OS-divergence inventory

Every point where behaviour depends on the host distribution is marked in the
source with `# OS-DIVERGENCE: <slug>` and listed here. The two sets are
asserted equal by `bats`, so a divergence cannot be added to the code without
appearing here, or removed from here while it still exists in the code.

`grep -n 'OS-DIVERGENCE:' install.sh` prints the live inventory.

The list is short on purpose. Prefer capability probes; use distribution
identity when selecting repository suites/components (including RAR dependencies).
See **DD-102** and **DD-104**, and `archive/os-aware-review.md` for why the tree is not
forked into per-distribution paths.

<!-- OS-DIVERGENCE-INVENTORY:BEGIN -->

| Slug | Kind | Affects | What differs | DD |
|---|---|---|---|---|
| `tailscale-repo-suite` | identity-derived | both | apt suite and keyring URL come from `OS_ID`/`OS_CODENAME`; both vendors publish the same URL shape | DD-102 |
| `rar-repository` | candidate probe + identity-derived | both | when RAR dependencies have no apt candidate, add only a managed signed source: Debian non-free, Ubuntu universe/multiverse; Ubuntu arm uses ports | DD-166 |
| `ufw-gate` | probe | ubuntu in practice | ufw active is a fail-closed stop; no package, no-op | DD-102 |
| `netfilter-binaries` | probe | debian | a minimal Debian image ships no `iptables`; stage 0 checks only what exists, stage 1 makes it mandatory | DD-108 |
| `needrestart-suspend` | probe-free no-op | ubuntu | `NEEDRESTART_SUSPEND=1`; Debian has no needrestart, so the variable is unread | DD-103 |
| `resolved-stub` | probe | ubuntu in practice | `DNSStubListener=no` written only when resolved is active; on Debian the whole block is skipped and no drop-in is created. Ubuntu 26.04 / systemd 259 accepts and ignores the key, so the achieved state is read back and reported rather than assumed | DD-102, DD-109 |
| `resolvconf-symlink` | probe | ubuntu | `/etc/resolv.conf` is repointed only when it targets the stub; Tailscale takes the file over later | DD-102 |

<!-- OS-DIVERGENCE-INVENTORY:END -->

The Caddy cloudsmith repository line (`any-version`, distro-agnostic) is
**deliberately not** a divergence and must not become a branch.

## 8. Implementation status

The `Data/` tree is executable: `install.sh` runs the seven stages on a
Debian 13 or Ubuntu 24.04/26.04 LTS host. The repository-root `kur.sh`, run on
the server with `curl … | sudo bash`, downloads the public repository archive and
copies only the runtime tree — `install.sh`, `common.sh` and the runtime
directories (`config`, `templates`, `scripts`, `systemd`, `panel`,
`files-panel`, `console`, `magaza`) — to `/root/debian-server-installer`, then
starts `install.sh` on the terminal (**DD-228**).

Static checks for this tree:

```bash
bats tests
bash -n install.sh common.sh scripts/*
shellcheck -x -s bash install.sh common.sh scripts/*
```

There is no root `scripts/check-all.sh` wrapper; run the three workstation
commands above directly. A missing tool must fail visibly — never report a
silent pass.

---

## 9. Per-phase verification

Use checks appropriate to the changed layer. Do not report a missing Linux
validator or an unrun fresh-host acceptance test as a pass:

| Check | Scope | Available on the dev workstation? |
|---|---|---|
| `bash -n` | Root `*.sh`, `scripts/*` and the exporter | **yes** |
| `shellcheck -x` | Same set; `-x` so sourced libraries are followed | **yes** |
| `bats tests/` | Shell/unit contracts; some require Linux tools | **yes**, with explicit skips for unavailable tools |
| Python unittest / browser suites | Backend and production UI with isolated fixtures | **yes**, with optional native-RAR tests skipped without Linux dependencies |
| `caddy validate` | The rendered `Caddyfile` | **no** — runs on the target, in stage 6, with the real env (**DD-106**) |
| `dnsmasq --test -C` | The rendered dnsmasq config | **no** — runs on the target, in stage 6 (**DD-106**) |
| `systemd-analyze verify` | Generated units and drop-ins | **no** — Linux suites only (`tests/settings-systemd.py`); the installer does not run it (**DD-106**) |

The split matters: workstation checks and Linux renderer checks are distinct.
A phase that changes a rendered template is
**not** verifiable on the workstation alone, and claiming otherwise is the
failure mode those host-only checks exist to prevent (a missing tool must
report *doğrulanamadı*, never a pass).

`install.sh` runs `caddy validate` and `dnsmasq --test` on the target, against
the file it just rendered, before the unit that consumes it is restarted
(**DD-106**). A bad render therefore fails with a line number and a directive
name instead of a failed `systemctl restart`. `refresh-tailnet-config` never
re-renders a config; on an address change it only rewrites `state.env` and
restarts Caddy (§5).

## 10. Settled questions and open checks

### 10.1 Settled questions

Where the working rules and the design once disagreed, the answer below is
current. Each has a full entry in `docs/design-decisions.md`.

| # | Question | Answer |
|---|---|---|
| **DD-58** | Single file or tree? | A repository tree; DD-9 is superseded. |
| **DD-59** | Chain names | `MASTER-INPUT`, `MASTER-FORWARD`/`MASTER-NAT` (WireGuard), `MASTER-SETTINGS` (Konsol overrides) and the `MASTER-NEXT-` staging prefix, declared only in `config/defaults.env`. |
| **DD-60** | Does dnsmasq listen on loopback? | Yes — `lo` and `tailscale0`, `bind-dynamic`, nothing else, no DHCP. |
| **DD-61** | Does the refresh helper re-render configs? | No. Address changes update `state.env` and restart Caddy; DD-87/94/180 add bounded Caddy, firewall and WireGuard recovery (§5), not general reconciliation. |
| **DD-158** | Where does WebDAV run? | Host unit `master-paylasim.service` (`master_webdav.py`) on loopback only, behind Caddy `reverse_proxy`. |
| **DD-98** | Apple TV without MagicDNS? | Caddy listens on `${TAILSCALE_IPV4}:${SHARE_PORT}` → loopback WebDAV; the service has no Tailscale bind. Folder URLs include `/s/<id>/`. |

### 10.2 Live checks

1. **`systemd-resolved` vs dnsmasq on `127.0.0.1:53`.** Stage 6 writes
   `DNSStubListener=no` when resolved is active. Confirmed on noble and
   resolute: dnsmasq owns loopback/Tailscale DNS, host DNS survives, and on
   resolute Tailscale can legitimately replace the uplink symlink with its
   direct-mode MagicDNS file after restart/reboot. Unusual images still need
   the same live check.
2. **What a loopback query actually answers.** `interface-name` is
   expected to return the `tailscale0` address regardless of the arrival
   interface, which is the entire reason the loopback listener is useful
   for testing. Stage 7 measures it on the live host: `dig +short NAME
   @127.0.0.1` and `dig +short NAME @${TAILSCALE_IPV4}` must agree, and must
   both return `${TAILSCALE_IPV4}`.
