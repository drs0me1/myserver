# Debian / Ubuntu Server Installer

Lean Bash installer for a fresh **Debian 13 (trixie)**, **Ubuntu 24.04 LTS
(noble)** or **Ubuntu 26.04 LTS (resolute)** host: Tailscale exit node, host
dnsmasq + Caddy on the tailnet, a persistent firewall and Konsol, from which
the optional applications are installed. Files, folder WebDAV and ZIP/RAR tools
are built in (**DD-159**, **DD-166**). Podman is part of the base as the App Store's
container runtime, with a main-sidebar Konteynerler manager for lifecycle, ports,
volumes, images and networks (**DD-211**); no Docker
(**DD-152**), no reconcile engine.

**Current version:** `V2_VERSION` in `Data/install.sh`.

Folder shares can opt into Tailscale, WAN IPv4 or both (DD-179). New shares
default to Tailscale. WAN uses HTTP with explicit plaintext-risk consent,
credential-attempt and connection caps; no console/admin endpoint is published.

Model A opens on **Ana Menü** (**DD-213**, **DD-231**, **DD-242**): server, live-rate and application-traffic widgets, installed
application cards and a clock/date header, refreshed every five seconds. One sidebar
holds navigation and live CPU/RAM/disk indicators. See the
[clean-install checklist](Data/docs/model-a-clean-install.md).
App Store uses cards with a name, status and Install/Open actions; descriptions,
service controls and logs remain under Details.

The repository root holds the server bootstrap `kur.sh` (**DD-228**),
`wireguard.command` (WireGuard peer management from a Mac), `onar.command` (check and repair over SSH
when Konsol cannot be reached, **DD-239**) and the Git-ignored
`kurulum/` (its SSH host and device profiles/QR codes downloaded on request). Everything else lives under `Data/`; paths in the
documents there are relative to `Data/`. Turkish click order:
[`Data/OKUBENI.txt`](Data/OKUBENI.txt).

Authoritative behaviour: [`Data/docs/contract.md`](Data/docs/contract.md).
Layout and data flow: [`Data/docs/architecture.md`](Data/docs/architecture.md).
Design rationale: [`Data/docs/design-decisions.md`](Data/docs/design-decisions.md),
one line per decision in [`Data/docs/decisions-index.md`](Data/docs/decisions-index.md).
Historical material (earlier reviews, retired design decisions, older changelog
and session history; not current behaviour): [`Data/docs/archive/`](Data/docs/archive/).

## Quick start

SSH into the fresh server yourself, then run one line (**DD-228**):

```bash
curl -fsSL https://raw.githubusercontent.com/drs0me1/myserver/main/kur.sh | sudo bash
# minimal image without curl/sudo, as root: apt install -y curl sudo
# a specific commit or tag instead of main:
curl -fsSL https://raw.githubusercontent.com/drs0me1/myserver/main/kur.sh | sudo KUR_REF=<commit|tag> bash
```

`kur.sh` downloads the repository archive from GitHub, places the runtime files
in `/root/debian-server-installer` (atomic swap) and starts `install.sh` on the
terminal. The installer upgrades the system on every run. A first install asks for
the local domain (no default, e.g. `ev` gives `panel.ev`); re-runs keep the existing
name, which is changed in Konsol → Ayarlar (**DD-157**). It shows one summary and
waits for `E`. Approve the Tailscale login link it prints in a browser.

Root, interactive TTY (one confirmation), Debian 13 or Ubuntu 24.04/26.04 LTS
only. Re-runs are supported: run the same line again.

Later versions: Ana Menü shows **Güncelle** beside the clock when `main` on GitHub carries a newer
installer version. After a confirmation it re-runs the installer for exactly that commit, without a
terminal, while Konsol restarts; the page reloads when it ends (**DD-233**). The button starts
updates only over Tailscale; a first install and a missing Tailscale login still need the line above.

WireGuard peers from a Mac (after the install, optional):

```bash
mkdir -p kurulum && cp Data/config/kurulum.env.example kurulum/kurulum.env
chmod 600 kurulum/kurulum.env   # then set SSH_HOST
# double-click wireguard.command
# Pick the network: 6) Ağ seç; change a peer's DNS: 7) DNS değiştir
# New server key, all its peers removed: 8) Ağı yeniden üret
# Nothing is kept on the Mac but a profile you download, with its QR code as <name>.png
```

Repairs run on request, not in the background (**DD-239**): Konsol → Ayarlar → Sistem → Sağlık →
"Denetle" / "Onar". When Konsol cannot be reached, double-click `onar.command` (same SSH host) or run
`sudo master-onar` on the server (`--denetle` only reports).

## Repository layout

```
.
├── kur.sh                 # server bootstrap: curl … | sudo bash (DD-228)
├── wireguard.command      # WireGuard peer menu (double-click)
├── onar.command           # check and repair over SSH (double-click; DD-239)
├── kurulum/               # wireguard.command input, mode 600 (Git-ignored)
│   ├── kurulum.env        #   SSH host
│   └── wireguard/         #   only the profiles + QR pictures you downloaded (DD-143)
├── README.md, CLAUDE.md   # entry points
└── Data/
    ├── install.sh          # orchestrator
    ├── common.sh           # shared helpers
    ├── config/defaults.env # single source of truth for ports/paths/chain names
    ├── templates/          # Caddyfile, dnsmasq.conf
    ├── magaza/             # store packages: app and built-in service files (DD-196)
    ├── scripts/            # firewall, refresh-tailnet, GRO, wait, master-wg, master-modul
    ├── panel/              # Konsol root API, settings/share workers, WebDAV server
    ├── files-panel/        # file and archive backend
    ├── console/            # Konsol pages
    ├── systemd/            # units and drop-ins
    ├── tests/              # Bats, settings worker, browser and isolated Linux tests
    ├── docs/               # contract, architecture, design rationale and decision index
    ├── OKUBENI.txt         # Turkish click order
    └── CHANGELOG.md, SESSION.md
```

## Stack

| Service | Exposure | Role |
|---------|----------|------|
| qBittorrent (Podman container, **DD-151**, **DD-209**, **DD-217**) | loopback → Caddy `torrent.<domain>` (its own login); peer port 63851 TCP+UDP on the WAN IPv4 only (changeable on the Podman page, **DD-221**) | installed from Konsol → App Store (the linuxserver image, pinned by digest, its own bridge network; **DD-219** ports); torrent downloads. Account/folder settings remain in its application form; the Podman page manages lifecycle and its listener port, peer port and download folder through the package adapter |
| WireGuard (host kernel; app, **DD-150**) | public UDP; internet-only VPN | installed from Konsol → App Store; VPN; peers generated on the server with Konsol or `wireguard.command` |
| Built-in folder WebDAV (**DD-158**, **DD-159**) | loopback → Caddy on Tailscale (`paylas.<domain>`, `<tailscale-ip>:SHARE_PORT/s/<id>/`); internet only for folders that turn WAN on: HTTPS on a public name set in Settings → Caddy (**DD-190/191**), or legacy consented HTTP when none is set (**DD-179**) | Separate account per folder; Tailscale and WAN each have their own on/off, RO/RW and expiry (**DD-192**). Configure from Files → Details; manage together under Paylaşımlar. Passwords stored only as hashes. |
| Konsol Model A (**DD-160**, **DD-213**) | loopback → Caddy `panel.<domain>` on the tailnet, optionally also a public HTTPS name from Settings → Caddy (**DD-195**); no sign-in on the tailnet; the public name asks for the Konsol account created in Settings over Tailscale (**DD-194**, **DD-205**) | one sidebar: Ana Menü (clock/date title, Sunucu and Hız widgets side by side with the application-traffic row below, installed application cards with start/stop → settings → logs; edit mode for tile and widget order and widget visibility), Files (browse, upload, move, trash, text, archive creation/extraction), App Store, Konteynerler, installed qBittorrent/WireGuard and Settings; CPU/RAM/disk and IP/version/uptime below the menu |

qBittorrent's first profile contains only panel integration and headless-startup
settings (**DD-178**): download path, authenticated loopback WebUI and startup
notice acceptance. UPnP/automatic port mapping, local peer discovery and separate
temporary storage remain application defaults until the user changes them.
Existing profiles are never reset by an installer re-run or reinstall.

Host edge: dnsmasq + Caddy bound to the Tailscale address; firewall (custom INPUT/FORWARD/NAT chains) for
Tailscale, WireGuard and WAN SSH.
Tailnet host ingress uses an explicit service allowlist (**DD-172**); arbitrary
listeners do not become accessible automatically. Registered WireGuard ports and
outbound/established traffic remain protected; explicit WAN/tailnet rules take precedence.
The distribution's unattended updates also cover Tailscale and Caddy and run
daily between 04:00 and 04:30; an update briefly restarts that service and the
host never reboots on its own (**DD-113**, **DD-184**).

WireGuard is internet-only for all networks and peers (**DD-177**).
There is no Local access option in creation, settings, API or CLI.
WG cannot reach host services, other VPN networks or private destinations routed
through WAN. Firewall overrides are available only for WAN and Tailscale.

Konsol → Ayarlar (**DD-156/160**) contains System, Firewall, Caddy, Dnsmasq
and Log tabs. **Konteynerler** is a main-sidebar page (**DD-211**): create, start,
stop, restart and remove containers; edit ports, mounts and startup settings;
manage images, named volumes and bridge networks. App Store applications retain
their package lifecycle. Removing a container keeps its volumes and host files;
internet port exposure requires an explicit choice. qBittorrent's account and
download folder remain editable from its existing application settings form.
Firewall uses full tables with service/address explanations, source CIDRs,
policy and on/off controls. Incoming-network tabs are Tailscale (default), Internet,
WireGuard (when installed, with per-network selection) and protected loopback.
Listener binding is labelled separately from permission; Technical rules shows
all chains read-only (**DD-164**). Details stay visible; narrow screens scroll the table.
Caddy shows routes and offers a local-domain suffix change (**DD-157**); "+ Elle adres" gives a port
on this server (127.0.0.1, e.g. a Podman container's interface) a Tailscale name and an optional public
HTTPS name, guarded by the application's own login (**DD-252**).
DNS-only changes use one Apply action and persist immediately after validation
and restart, without a timed confirmation (**DD-163**). The panel's own DNS
name cannot be disabled; failed applies restore previous settings.
Account Save sends only username/password, keeps other drafts untouched and
reports success after durable commit. Blank preserves a stored password;
temporary first-login passwords can rotate on restart. Failed applies retain
snapshot recovery. Firewall/qBittorrent folder changes (including mixed drafts) require review,
apply and confirmation within 60 seconds; an independent server-side timer
rolls unconfirmed changes back.
Domain changes are separate: configure the new restricted domain in Tailscale
Admin DNS first, then update in Caddy and confirm from the new panel address
within five minutes. Old DNS mapping should stay until confirmation. Service
names, custom DNS records, disabled states and module renderings move together;
IP-based share links do not change.
Confirmed firewall/DNS/domain choices survive installer re-runs.

Files shows icons or a list and a right-hand places/details column (below on narrow screens).
See [folder WebDAV boundaries](Data/docs/folder-shares.md) before
sharing with other people: recipients must not reach Konsol/SSH or get the Konsol password.
Native Finder/Infuse compatibility and fresh Ubuntu acceptance are separate tests.

Konsol is one sidebar workspace, not an OS session. Files is a Finder-style window:
icons (or a list) on the left, places, the selection's details and actions on the right
(**DD-232**). Files/WebDAV are always installed.
ZIP creation and ZIP/RAR extraction jobs run on the server after the page closes,
with cancellation and bounded nested extraction. A running job shows as a bar
above the Files list; the result appears as a notification and in Ayarlar → Günlük
(**DD-183**).
Archive creation produces ZIP. Extraction automatically finds multipart RAR and
nested archives; the destination defaults to downloads and can be chosen with
the folder picker (**DD-170**). RAR3/RAR5, solid and multipart sets are supported;
keep all volumes together. The internal depth limit is five layers.
All source archives are retained. Encrypted archives/ZIP64/7z are not supported;
the existing 2 GiB aggregate job limit also applies to RAR.
See [Files and archive boundaries](Data/docs/desktop-and-archives.md) and
[Model A navigation and acceptance](Data/docs/model-a-clean-install.md).

## Rebuilding a host

Nothing but the domain answer reaches a fresh install; there is no server data to carry:
- The Konsol account (the public name's credential; the tailnet asks for no sign-in) is
  created in Settings over Tailscale (**DD-205**; forgotten: set a new password
  there, or `sudo master-konsol sifirla`), and the modules make or show their own.
- qBittorrent keeps its settings and torrent list on the server only; a
  fresh install starts it with minimal settings and a new login (**DD-151**).
- WireGuard is not part of that: a fresh install has no WireGuard at all
  (**DD-143**, **DD-150**). Install it from Konsol → App Store → WireGuard, create
  the first network in WireGuard → Yapılandır and add the devices again.

## Verify (workstation)

```bash
bats Data/tests
bash -n kur.sh Data/install.sh Data/common.sh Data/scripts/*
shellcheck -x -s bash kur.sh Data/install.sh Data/common.sh Data/scripts/*
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s Data/tests -p 'test_*.py'
# Browser: PLAYWRIGHT_MODULE=<module path> PLAYWRIGHT_CHROMIUM=<binary> node Data/tests/settings-ui.cjs
# Linux root, disposable network namespace (existing services are not touched):
# unshare --net --fork python3 Data/tests/settings-linux.py
# unshare --net --fork python3 Data/tests/settings-domain-linux.py
# python3 Data/tests/settings-systemd.py
```

## Working conventions

Version history stays in Git. `kur.sh` installs whatever `main` holds, so every
pushed change to `main` reaches the next install; there is no exported installer
to rebuild (**DD-228**).

See [`CLAUDE.md`](CLAUDE.md). Change history: [`Data/CHANGELOG.md`](Data/CHANGELOG.md).
Session continuity: [`Data/SESSION.md`](Data/SESSION.md).
