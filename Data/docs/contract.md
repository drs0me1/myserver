# Behaviour Contract

**Status:** current behaviour contract, evolved from the 2026-08-05 requirements.
Implemented by `Data/install.sh` and helpers. Where live code and this
document diverge, prefer the code and update this file.

This document is the authoritative statement of what the installer does
and — just as importantly — what it deliberately refuses to do. Companion
contracts: [folder-shares.md](folder-shares.md) (folder WebDAV),
[desktop-and-archives.md](desktop-and-archives.md) (Files and archives) and
[model-a-clean-install.md](model-a-clean-install.md) (Konsol layout and
clean-install acceptance).

**Relationship to `.cursor/rules/`:** those rules cover the repository and
govern *how* the work is done — process, Bash conventions, the
per-phase verification set, and the hard prohibitions (do not delete other
software's chains such as Tailscale's `ts-*`, do not silently turn the
UDP-only decision into TCP+UDP, do not grow
a general-purpose reconcile engine). This document governs *what the result
must do*. Where the rules do not specify a feature in detail, this contract
extends them. Settled disagreements with early rule drafts — dnsmasq
listening scope, chain name and refresh helper scope — are recorded as
**DD-59** through **DD-61** in `design-decisions.md`.

The single active rule source is `.cursor/rules/master-stack.mdc`. The
original RTF is archived unchanged at
`docs/archive/master-stack-rules-source.rtf` and is a historical record
only — it is not edited and nothing synchronises it back.

The twenty numbered requirements referenced as **R1**–**R20** throughout are
the ones agreed on 2026-08-05:

| | Requirement |
|---|---|
| R1 | Update the Debian system |
| R2 | Install required packages |
| R3 | Install Tailscale |
| R4 | Advertise the server as an exit node |
| R5 | Enable Tailscale SSH |
| R6 | Apply IP forwarding and the official Linux exit-node optimisations |
| R7 | Store the Tailscale IPv4 and IPv6 addresses as variables and in a state file |
| R8 | Create the user root `/srv`, downloads `/srv/downloads` and media `/srv/media` (**DD-144**) |
| R9 | Withdrawn (**DD-152**) |
| R10 | Optional qBittorrent is a Podman container application on its own bridge (**DD-151**, **DD-209**, **DD-217**); Files, per-folder Python WebDAV and bounded archive tools are built in (**DD-158**, **DD-159**) |
| R11 | Publish every web interface on loopback only (`127.0.0.1`; WebDAV's WAN scope on `SHARE_WAN_BACKEND`, **DD-179**) |
| R12 | Publish publicly the WireGuard UDP port of each network, only while WireGuard is installed (host kernel, **DD-120**). qBittorrent's peer port `TORRENT_PEER_PORT` (63851 unless changed in the Podman page, **DD-221**) is published on `WAN_IPV4` over TCP and UDP only while it is installed, through its Quadlet and the container guard (**DD-217**, **DD-219**, superseding DD-151's outgoing-only rule; §3.1) |
| R13 | Ask for the local domain on the server terminal on a first install, with no default (**DD-228**) |
| R14 | Resolve the defined service names to the Tailscale IPv4 with dnsmasq |
| R15 | Have Caddy serve selected private HTTP routes on the Tailscale IPv4, plus optional WAN WebDAV/qBittorrent/Konsol HTTPS publications; Konsol's tailnet address always stays (§3.1, **DD-179/190/191/195**) |
| R16 | Reverse-proxy the service names to the loopback interfaces through Caddy |
| R17 | Tell the operator to configure Custom DNS and Restrict-to-domain manually in the Tailscale admin panel |
| R18 | Reapply firewall on boot: default Tailscale access, Tailscale UDP, registered WireGuard UDP, WAN SSH and the selected optional WAN Caddy publication port (**DD-179/190/191**); confirmed panel overrides take precedence. qBittorrent's peer port is let through by the container guard on the forward path, not by MASTER-INPUT (**DD-217**, **DD-219**) |
| R19 | Withdrawn (**DD-152**) |
| R20 | Keep the installation re-runnable |

---

## 1. Included features

### 1.1 Base system

- Supported-OS hard gate (**R1**, **DD-102**): Debian 13 (trixie),
  Ubuntu 24.04 LTS (noble) or Ubuntu 26.04 LTS (resolute); the installer
  refuses any other OS or release. The Tailscale apt repo suite is derived
  from `os-release` (`OS_ID`/`OS_CODENAME`), never hardcoded, and its
  `dists/<codename>/Release` is probed before the source file is written
  (**DD-106**). On a host with
  ufw active the installer stops before any mutation. The
  `iptables`/`ip6tables` backend must be the nft one tailscaled uses, because
  `MASTER-INPUT` is ordered behind its `ts-input` (**DD-152**); stage 0
  asserts this for whichever binaries the host already has and stage 1
  asserts it unconditionally once the package is installed, because a
  minimal Debian image ships none (**DD-106**, **DD-108**).
- The detected release is **recorded**, not only used (**DD-104**):
  `state.env` carries `OS_ID`, `OS_CODENAME`, `OS_VERSION_ID`, `OS_ARCH`
  and `KERNEL_RELEASE`. A re-run whose recorded identity differs from the
  live one warns and re-applies the OS-dependent steps even when the
  written files are byte-identical. A missing record is not treated as a
  release change. Architecture outside
  `amd64` warns; it is not refused.
- Third-party restart managers are suspended for the installer's apt calls
  (`NEEDRESTART_SUSPEND=1`, **DD-103**). Ubuntu's `needrestart` otherwise
  restarts `sshd`, `tailscaled`, `caddy` and `dnsmasq` automatically in the
  middle of a stage.
- Every rendered config is validated on the target before the unit that
  consumes it restarts: `dnsmasq --test -C` and `caddy validate` with the
  real `TAILSCALE_IPV4` (**DD-106**); a module's Caddy site and dnsmasq name
  are validated by `master-modul` before they take effect (§1.11).
- `apt-get update` + `full-upgrade` on every run (**DD-228**), then the package set the stack needs
  (**R1**, **R2**): only what the base itself uses (**DD-153**) — no `gnupg`
  (apt reads the armored Caddy key, `signed-by=…caddy-stable-archive-keyring.asc`),
  no `gawk` (the distribution's `mawk` is `awk`). Folder WebDAV uses the base
  Python runtime (**DD-158**). Distribution-signed `unrar` and `python3-rarfile`
  are base dependencies of the archive opener: if the existing apt sources lack
  them, one managed source enables Debian non-free or Ubuntu
  universe/multiverse with the installed distribution keyring; no operator
  source is overwritten (**DD-166**).
- `unattended-upgrades` is installed and enabled for the distribution's own
  origins (Debian stable + security; Ubuntu security), with automatic reboot
  off (**DD-113**). The Tailscale and Caddy repositories are added to its
  origins (`origin=Tailscale,label=Tailscale`, `origin=cloudsmith/caddy/stable`),
  and the daily run starts at `APT_UPGRADE_TIME` (04:00) plus a random delay of
  up to 30 min; an update restarts that service briefly (**DD-184**).
  WebDAV code updates with the installer (§7).
- Timezone set to the configured value.
- Root-only, single-host, `flock`-serialised, wrapped in `systemd-inhibit`
  so a shutdown cannot land mid-transaction.
- **Started on the server with one line (DD-228).** The operator SSHes in and runs
  `curl -fsSL https://raw.githubusercontent.com/drs0me1/myserver/main/kur.sh | sudo bash`.
  - `kur.sh` downloads the public repository archive (`main`, or `KUR_REF`), copies
    only the runtime tree (`install.sh`, `common.sh`, `config`, `templates`,
    `scripts`, `systemd`, `panel`, `files-panel`, `console`, `magaza`) to
    `/root/debian-server-installer` with an atomic swap, then `exec`s `install.sh`
    with the terminal as stdin.
  - The local domain has no default. A name confirmed in Konsol (**DD-157**) or the
    previous install's (`config.env`) is used without asking; only a first install
    asks, repeating the question until the answer is a valid label. It prints the values without passwords and asks for
    one confirmation before `config.env` is written. An interactive TTY stays required,
    except for Konsol's update below.
  - **Konsol update (DD-233).** Ana Menü offers the update (a round update icon with a red dot,
    **DD-245**; words appear only while an update runs, showing its stage) when the tip of `GUNCELLEME_DAL` on
    `GUNCELLEME_REPO` carries a higher `v2-<n>` than the installed version. The backend checks
    GitHub at most every six hours (a failed check after 15 minutes, a manual check once a minute)
    and pins the offer to that commit. The start is accepted only from a Tailscale device (or root
    on the socket), only for the offered commit/version, never beside a package operation, a
    pending settings change or a running update. `master-guncelle` runs as `GUNCELLEME_UNIT`,
    fetches that commit's `kur.sh`, which refuses any other version, and runs `install.sh` with
    `V2_GUNCELLEME=1`: no TTY, no questions, the confirmation is Konsol's. That mode refuses a
    first install (no saved domain) and a missing Tailscale login. The result and output are in
    `GUNCELLEME_DURUM_FILE`/`GUNCELLEME_LOG_FILE` (0600); Konsol shows the stage and the last line
    of a failure. No automatic update and no rollback; the previous code is in Git.
  - Every run, re-runs included, performs `full-upgrade`; there is no question.
- **Nothing from the operator's workstation reaches the server (DD-143, DD-228).**
  No WireGuard configuration, key or profile is read from `kurulum/` or uploaded,
  and nothing is fetched back. `wireguard.command` may download a profile and its
  QR picture on request (**DD-132**), for the operator only.

### 1.2 Tailscale

- Official Tailscale repository and package (**R3**).
- There is no auth key input (**DD-147**): the node always joins through the
  login link that stage 2 prints, and the operator approves it in a browser.
  Nothing Tailscale-related is typed into or stored by the installer.
- `tailscale up --advertise-exit-node --ssh`, then `tailscale set` to hold
  exit-node, SSH, stateful filtering, netfilter mode and subnet-route SNAT
  (**R4**, **R5**).
- **The 410 login-recovery mechanism is preserved** — three bounded
  attempts, `auth_path_dead` classified from the LocalAPI (never from the
  journal), daemon reset between attempts, dependency-isolated restart.
  This is the one failure mode an operator cannot recover from unaided, and
  it was earned by a real incident.
- IPv4 and IPv6 forwarding sysctls, UDP socket buffer floor, and the
  **UDP GRO optimisation** are all preserved (**R6**).
- The Tailscale IPv4 **and IPv6** are written to `/etc/master-stack/state.env`
  (**R7**).
- Exit-node recipient restrictions belong to the tailnet policy: grant
  `autogroup:internet`, not broad private-network access, and review existing
  grants because allows are additive. This selector excludes private/link-local
  destinations, including the usual metadata address. The installer does not
  edit the account's ACL/grants. See Tailscale's [selector definition](https://tailscale.com/docs/reference/targets-and-selectors).

### 1.3 Modules are host services (DD-151, DD-152, DD-208, DD-209)

- Every module and built-in service is a systemd unit on the host (§1.11). The
  base installs Podman (`podman`, `netavark`, `aardvark-dns`, no recommends) as the App Store's
  container runtime and requires `podman info` in stages 1 and 7 (**DD-208**); no
  Podman daemon, socket or auto-update timer is enabled and there is no Docker
  (**DD-152**). A container application is still a systemd unit: Podman's systemd
  generator writes it from the package's quadlet file (**DD-209**).
- The installer's own apt downloads are not kept in `/var/cache/apt/archives`
  (`APT::Keep-Downloaded-Packages=false`) (**DD-125**).
- **qBittorrent is a container application (DD-151, DD-209)**, installed from Konsol
  (§1.11): the `lscr.io/linuxserver/qbittorrent` image, pinned by digest, runs in
  Podman on its own bridge `torrent` as the downloads account (PUID/PGID), with the
  interface (`TORRENT_UI_PORT`, 62947) published on `127.0.0.1` only and the peer port
  (`TORRENT_PEER_PORT`, 63851) on the WAN IPv4 address only (**DD-217**, **DD-219**).
  `magaza/torrent/qBittorrent.conf` seeds minimal integration settings only when the
  profile is absent (**DD-178**).
  The installer holds no account: the account and the
  download folder come from the App Store install form (**DD-210**) and are written
  before the container's first start. Later account/download-folder edits go through
  the package's own page, the overview's settings action and its worker
  (`magaza/torrent/ayar.py`, **DD-202**, **DD-210**), never the base settings transaction.
- Every web interface and WebDAV listens on loopback only (`127.0.0.1`;
  WebDAV's WAN scope on `SHARE_WAN_BACKEND`, **DD-179**) (**R11**).
- Module services survive a reboot as enabled systemd units (a container
  application through its quadlet's `[Install]` section); a module stopped from
  Konsol is disabled and stays stopped — a container application's quadlet file
  is removed (§1.11). systemd's `Restart=` handles a crash.

### 1.4 Directories

- `/srv/downloads`, `/srv/media`, `/srv/media/movies` and
  `/srv/media/series` are created when absent (**R8**, **DD-144**).
- **The downloads tree is repaired selectively on every run** (**DD-84/DD-187**):
  pinned descriptors apply `fchown`/`fchmod` only to directories and single-link
  regular files whose UID/GID differ from `DOWNLOADS_UID`/`DOWNLOADS_GID`
  (defaults `1000:1000`) or modes differ from `0775`/`0664`. All path components
  are opened without following symlinks; links and special files are skipped.
  Matching entries are left untouched
  (no full-tree rewrite). qBittorrent and Konsol's file backend share
  read/write that way. WebDAV enforces each connection's RO/RW permission
  within the folder account (DD-158/DD-192).
- The private `.arsiv` work/history tree and the reserved `.pay` name
  (`SHARE_DIR`) are excluded from ordinary ownership/mode repair. `.pay` is
  never created or read; the file backend hides and refuses it (the name is
  reserved), WebDAV and qBittorrent cannot access it, and its contents are
  never deleted (**DD-171**).
  `.cop` and `.pay` are internal areas, not shareable folders.

### 1.5 DNS and Caddy

- dnsmasq bound to loopback and `tailscale0`, tracking the interface address with
  `interface-name` + `bind-dynamic`, resolving the installed service names to the
  current Tailscale IPv4 (**R14**).
- Caddy listening on the Tailscale IPv4, port 80 (and `SHARE_PORT` for folder
  WebDAV), plain HTTP inside the tailnet (Tailscale encrypts the transport),
  reverse-proxying to loopback upstreams (**R15**, **R16**). Public HTTPS is the
  separate WAN listener below. Client aborts are not logged as proxy warnings;
  proxy errors and failed upstream dials still are (**DD-193**).
- The real Konsol page and backend/gate checks verify the HTTP edge; there is
  no separate health endpoint or DNS name (**DD-157**).
- Optional WAN WebDAV uses HTTPS on `WAN_IPV4:SHARE_HTTPS_PORT` when a public
  domain is saved in Settings → Caddy; with no HTTPS setting, existing
  consent-gated HTTP on `WAN_IPV4:SHARE_PORT` remains. Explicitly clearing
  the domain closes WAN, not downgrades it (**DD-179/190**, §3.1).
- DD-191/199 additionally allow a package's HTTPS publication on that same port,
  declared in its manifest (`PAKET_YAYIN_*`: name, local name, loopback upstream,
  optional check module) and guarded by the application's own mandatory login and
  the package's checks; today qBittorrent. Caddy opens one WAN port for
  these publications: enabling an HTTPS publication is refused while folders
  are shared over legacy WebDAV HTTP, and while an HTTPS publication row is on,
  legacy HTTP WebDAV internet access is unavailable until an HTTPS name is saved
  (v2-169). No Caddy admin publication.
- DD-252 allows addresses the operator enters in Settings → Caddy: a name, a tailnet name
  (`http://<local>.${LOCAL_DOMAIN}`, its line in `modul-elle.conf`) and an upstream that is a port on
  `127.0.0.1`, with the same independent Tailscale/internet switches and HTTPS name. The public site
  shares the WAN port and its budgets; the application's own login is its only guard. Konsol's own
  loopback backends (`FILES_PANEL_PORT`, `SHARE_PORT`) and package publications' upstreams are refused;
  no other host, Tunnel or DNS write.
- DD-195 allows Konsol itself on that port (`moduller/panel-wan.caddy`). The
  public site imports the same `(konsol)` snippet as the tailnet site, so the
  Konsol session check covers its pages, Files API and root API alike; Caddy
  marks the channel (`X-Konsol-Kanal: internet`) and pins the backend Host to
  `panel.${LOCAL_DOMAIN}`. HSTS is one year. Enabling needs an existing Konsol
  account (created in Settings over Tailscale, **DD-205**); account creation is
  refused over the internet.

### 1.6 Firewall

- A host `INPUT` policy and, for WireGuard, a forwarding and NAT policy, all
  fail-closed (**R18**). Full contract in §8 and §9.
- The **staging-chain swap** is preserved wherever it applies: rules are
  built in a throwaway chain and swapped in atomically, so there is no
  window in which the host runs with a partial policy.
- Nothing is persisted to disk. `master-firewall.service` re-applies the
  policy on boot and whenever `tailscaled` restarts
  (`PartOf=tailscaled.service` only, **DD-152**), which keeps `MASTER-INPUT`
  behind tailscaled's `ts-input`.

### 1.7 WebDAV

The share WebDAV is a built-in host service (**DD-158**, **DD-159**).
Contract in §5–§7 and `folder-shares.md`.

### 1.8 Operator guidance

- The manual Tailscale admin steps are printed at the end (**R17**, §13).
- No service accounts come from installer input; folder accounts are set in
  Files and qBittorrent manages its own account (**DD-147/151/158**).
- **Konsol sign-in (DD-194, DD-205):** the tailnet address asks for no sign-in;
  the summary names it as passwordless. The public name (DD-195) needs the
  Konsol account — user name (3–32 characters) and password (10–256) — which
  the operator creates in Settings → Sistem → Konsol hesabı over Tailscale.
  There is no setup code and the installer prints none. `sudo master-konsol
  sifirla` deletes the account and all sessions (the public name closes);
  `master-konsol durum` shows the state.

### 1.9 WireGuard (DD-120, DD-124)

- **A fresh install has no WireGuard (DD-143, DD-150).** WireGuard is a Konsol
  module (§1.11). The installer only puts `master-wg` and an empty `/etc/wireguard` (`0700`, the root backend's
  writable path declared by the package) in place. Installing the module installs `wireguard-tools`
  and `qrencode` (`--no-install-recommends`), loads the kernel module (and
  writes `WG_MODULES_LOAD_FILE`), creates `/etc/wireguard`, re-applies the
  firewall and starts whatever networks the registry already holds. Nothing
  generates a key, writes a `.conf` or brings up an interface of its own.
- Without the module `master-firewall` ignores the network registry (no
  WireGuard port or rule), `master-wg` refuses every command but `version`,
  and the root backend serves no WireGuard route: `/api/uygulama/wireguard/*`
  answers `404` (GET) or `409` (POST) and Konsol shows no WireGuard page or link
  (**DD-200**). Removing the module closes every network
  (`wg-quick@` disabled) and keeps `/etc/wireguard`, so a
  reinstall brings the networks back; `--veri` also deletes the keys, the
  device profiles and the registry.
- **Networks are created from Konsol** (WireGuard → Yapılandır → Arayüz ekle) or
  with `master-wg net-add`. The first one defaults to `wg0`, `10.8.0.0/24`,
  `fdcc:ad94:bacf:61a4::/112` (peers `…::N`, the hex of the IPv4 host number;
  **DD-135**), UDP `${WG_PORT_DEFAULT}`, MTU `${WG_MTU}`; later ones take the next
  free `wgN` and a port from 61020 upward. No setting describes an installed
  network, and the base carries no WireGuard setting at all (**DD-201**): the
  address bases (`WG_ADDR_BASE4`, `WG_ADDR_BASE6`), the suggested first port, the
  peer profile defaults and the paths live in the package's own
  `magaza/wireguard/wireguard.env`, read by `master-wg`, the hooks, the Konsol API
  module and `wireguard.command` from the rendered package folder.
- **Internet-only (DD-177).** No access selector, no WG host-rule override and
  no per-network Caddy listener. API creation/settings reject a supplied
  `scope` field; CLI creation is `net-add PORT DNS LABEL`, and settings is
  `--if wgN net-settings DNS REVISION`. Network settings change only the
  default DNS for future peers, under revision and install-lock checks; they
  never regenerate keys, change existing profiles or start a stopped network
  (**DD-167**).
- **The server is the source of truth.** `/etc/wireguard/wgN.conf` (`0600`)
  holds that network's key and one `# peer: <name>` + `[Peer]` block per device;
  the registry holds the network's parameters. Nothing is restored from the
  workstation (§1.1).
- **Peers are managed with `master-wg`** (`/usr/local/sbin`, root), driven from
  the workstation by `wireguard.command`:
  - `add NAME DNS KEEPALIVE MTU` runs `wg genkey`, `wg pubkey` and `wg genpsk`,
    takes the next free address (IPv4 from `.2`, IPv6 with the same host
    number in hex), stores the device profile in `/etc/wireguard/clients-wgN/`
    (`0600`) and appends the `[Peer]` block. It validates the name, DNS list,
    keepalive (0–65535) and MTU (1280–1500) before any change.
  - `remove NAME` deletes the block and the stored profile.
  - `dns NAME DNS` rewrites only the `DNS =` line in the `[Interface]` part of
    the stored profile. Keys, address and the network's `.conf` stay the same and
    nothing is applied on the server: DNS is a client setting, so the device
    imports the new profile (**DD-130**).
  - `reset --onay` issues a new server key and drops every `[Peer]` block and
    every stored profile. The other `[Interface]` lines are kept. It applies
    like any change; a failed apply restores the network's previous `.conf`
    and keeps the profiles. Without `--onay` it changes nothing (**DD-130**).
  - `list` prints name, address, last handshake, transfer and whether a
    profile is stored; `profile NAME` and `qr NAME` print the stored profile
    or its QR code.
  - `png NAME` writes the profile's QR code as a PNG (8 pixels per module) to
    standard output, and refuses when that output is a terminal (**DD-132**).
  - It takes the installer's lock, so the two never write a `.conf` at once.
  - A failed apply restores the previous `.conf` and removes a new profile.
- **Changes reach a running interface with `wg syncconf`** (no restart;
  connected devices stay up). `wg-quick@wgN` restarts only when it is not
  running, when `Address`/`MTU` changed, or when `syncconf` fails; an empty
  `wg-quick strip` output is never passed on (**DD-123**).
- **`wireguard.command`** (repository root, macOS) reads only `SSH_HOST` from
  `kurulum.env`. It refuses a server whose `master-wg version` differs from
  the repository's `V2_VERSION`. It asks for the name, DNS, keepalive and MTU
  (defaults from `defaults.env`; DNS is Cloudflare IPv4 first, **DD-131**), prints the QR code and saves the profile as
  `kurulum/wireguard/<name>.conf` and its QR picture as `<name>.png` (both
  `600`, **DD-132**). A picture without the PNG signature is not kept; the
  menu warns and the profile stays.
  - Option 7 "DNS değiştir" offers the peer's current DNS as the default,
    then prints the new QR code and saves the new profile.
  - Option 8 "Ağı yeniden üret" lists the peers of the selected network that
    will be lost and runs
    `reset --onay` only after the operator types `onayla`, in any case (**DD-130**, **DD-134**).
  - The menu keeps nothing on the Mac beyond a profile the operator asked for
    (**DD-143**): it never uploads, and a reinstall cannot bring back a removed
    peer, a removed network or an old key.
- **What clients reach:** IPv4/IPv6 internet egress via WAN masquerading.
  All WG-originated host traffic (including existing connections and ping) is
  dropped before established/ICMPv6/Tailscale accepts. Other peers, VPN networks
  and private/CGNAT/link-local destinations routed via WAN are blocked (§9).
  There is no WG web proxy or listener; administration uses Tailscale.
- **WireGuard web panel (DD-133, DD-200).** Konsol's WireGuard page at
  `http://panel.${LOCAL_DOMAIN}` (**DD-140**) is the package's own
  (`magaza/wireguard/sayfa.js`, served from `CONSOLE_WEB_DIR/uygulama/wireguard/`
  while installed) and talks to the package's API module, which the root backend
  loads from the package folder and serves at `/api/uygulama/wireguard/*`: list,
  add and remove peers, show a peer's QR code, download its profile or picture,
  change its DNS and regenerate a network.
  - The backend runs Python 3's standard library only and has no TCP port: it listens
    on the Unix socket `PANEL_SOCKET` (`/run/master-panel/api.sock`,
    `0660 root:caddy`), and also checks the connecting process's identity
    (`SO_PEERCRED`: root or Caddy's group, **DD-180**). Caddy exposes it on the
    tailnet; nothing exposes it on a WireGuard network, the WAN or loopback TCP.
    A request Caddy relays must come from another tailnet device: a Tailscale
    address that is not the server's own (Caddy writes the real client address).
    So a compromised downloads-account process (qBittorrent, unrar) reaches it
    neither directly nor through Caddy's tailnet listener; stage 7 proves both.
  - Every change goes through `master-wg` (`info`, `add`, `remove`, `dns`,
    `reset --onay`, `profile`, `png`): same validation, lock and live apply as
    `wireguard.command`.
  - **Sign-in (DD-194, DD-205):** Caddy's `forward_auth` asks this backend
    (`GET /oturum-denetle` on its socket) before every panel request except
    `/giris.js`, `/giris.css`, `/konsol.css` and `/api/konsol/oturum[/*]`. The
    answer follows the channel Caddy wrote: on the tailnet site (another
    Tailscale device, DD-180) 204 without any cookie and 302 from `/giris.html`
    to `/`; on the public site, and for a caller without Caddy's forwarding
    headers, `/giris.html` is open and everything else needs a valid
    `konsol_oturum` cookie — a page gets 302 to `/giris.html`, `/api/*` gets 401
    `{giris: true}`. Routes: `GET /api/konsol/oturum` (state: `kurulum`, `giris`
    or `acik` + user — the user name also without a session on the tailnet,
    never to an anonymous internet visitor — plus `kanal`),
    `POST /api/konsol/oturum/kur` (user name + password, no code; tailnet only,
    403 over the internet, opens no session), `POST
    /api/konsol/oturum/{giris,cikis}` and `POST /api/konsol/hesap/parola`: over
    the internet with a session and the current password (keeps that session,
    ends the others), on the tailnet with `yeni` alone (no current password,
    every session ends). The cookie is `HttpOnly; SameSite=Strict; Path=/`,
    seven days from sign-in. Five failed sign-in or current-password attempts
    from one address within 60 s block it for 300 s (429, Retry-After). Records
    live in `KONSOL_AUTH_DIR` (0700 root): scrypt password hash, SHA-256 of
    session tokens. Tailscale ACLs decide which devices reach the tailnet
    address — and therefore who administers the server without a password.
  - **Public address (DD-195):** a request marked `internet` by Caddy is accepted
    only while the Panel publication is active (enabled row, assigned global
    WAN IPv4, existing account; re-read at most every 5 s) and the client is not
    one of the server's own addresses. There `kur` answers 403, the cookie adds
    `Secure`, and failures also count in one shared public budget: 20 within
    600 s close public sign-in for 900 s while Tailscale sign-in stays open. Each
    address runs one password check at a time; at most two run at once.
    `GET /api/konsol/oturum` also reports `kanal` (`tailscale`/`internet`).
    Timed Settings confirmations (firewall, local domain) need a Tailscale
    address and the `tailscale` channel; the domain check compares Caddy's
    `X-Forwarded-Host`. Each Caddy site opens at most 16 connections to this
    backend.
  - Two gates stay mandatory under the session check and stage 7 proves both
    on both backends: a request with another `Host` than
    `panel.${LOCAL_DOMAIN}` is refused (DNS rebinding; the root backend accepts
    no loopback name since **DD-180**),
    and `/api/*` needs the `X-Konsol: 1` header and a same-origin fetch, which a
    page on another site cannot send (CSRF). Adds, removes, DNS changes and regenerations need a
    JSON body; regeneration also needs `confirm` `onayla` (any case, **DD-134**).
  - Responses carry `Cache-Control: no-store`, a CSP with only `'self'` sources
    (plus `blob:` images), `X-Frame-Options: DENY` and no referrer. The page
    loads nothing from other hosts.
  - Keys are never in a listing or preview. The profile preview masks
    `PrivateKey` and `PresharedKey`. The full profile and the QR picture are
    returned only on an explicit request, and the audit line in the journal
    names the user, client, action and peer, never the content.
  - The unit runs with `NoNewPrivileges`, `ProtectSystem=full` with the paths
    packages declare (`PAKET_ARKAUC_YOLLAR`; WireGuard's `/etc/wireguard`) writable,
    each optional so a missing folder never keeps Konsol down (**DD-203**). systemd
    binds such a path writable only if it exists when the backend starts, so the
    installer creates every declared path (0700 root, empty while the package is not
    installed) before the backend starts and restarts a running backend whose mount
    table lacks a writable mount for one; the store engine repeats that check after
    `kur`, `baslat` and `uygula` and restarts the backend once if a path was removed
    and recreated while it ran; `master-wg` refuses writing commands with a plain
    message when its folder is read-only for the caller (**DD-207**),
    `ProtectHome`, `PrivateTmp`, the kernel
    protections and `AF_UNIX`/`AF_INET`/`AF_INET6`/`AF_NETLINK` only.
  - A peer shows "Bağlı" only while data arrives from it: its received bytes
    grew within the last 45 s and its handshake is under 3 minutes old. A
    background sampler reads every network every 10 s (**DD-137**).
  - The header shows the endpoint, the `WAN_IPV4` the installer detected on the
    server; no address is written by hand (**DD-138**, **DD-201**).
  - Nothing on the Mac is tracked (**DD-143**); `wireguard.command` is managed
    on its own and asks which network to work on.
- **WireGuard networks from the panel (DD-136/143).** "Arayüz ekle" creates
  `wg0`…`wg9` at run time with `master-wg net-add PORT DNS LABEL`; each
  network has its own tab, server key, UDP port and addresses.
  - Addressing: `wgN` is `10.8.N.0/24` (server `10.8.N.1`) and
    `fdcc:ad94:bacf:61a4::N:0/112` (server `…::N:1`); peers get `10.8.N.H`
    and `…::N:H` (H in hex). Profiles live in `/etc/wireguard/clients-wgN`;
    the interface in `/etc/wireguard/wgN.conf`.
  - The same internet-only policy applies to every network and peer.
  - The registry `/etc/wireguard/networks` (one tab-separated line per
    network: interface, port, reserved fixed `inet` field, server and subnet IPv4 and IPv6, default
    DNS, label) is written by `master-wg` and read by `master-firewall`
    and the panel. A malformed or clashing registry stops the firewall
    before any chain changes; stage 7 stops on a fixed field other than `inet`.
  - A new network's port may not be a base port (SSH, Tailscale, DNS, HTTP), a port
    any package manifest declares (`PAKET_PORTLAR`, installed or not, **DD-201**),
    another network's port or a UDP port already listened on; the next free number
    is taken (from `wg0`, at most `WG_NETWORKS_MAX + 1` slots, currently 10).
  - Order when adding: files and registry, `master-firewall` restart, then
    `wg-quick@wgN`. A failing step removes
    every trace of the network and restores the firewall.
  - `master-wg --if wgN` runs any peer command on that network;
    `net-remove wgN --onay` stops its units, deletes its files, key, peers and
    registry line and re-applies the firewall. Every network can be removed,
    `wg0` included (**DD-143**); removing the last one leaves the layer ready
    and Konsol back at "Yapılandır".
  - The panel confirms regenerating or removing a network with `onayla`.
  - **Switches (DD-140).** `master-wg [--if wgN] net ac|kapat` stops or starts
    `wg-quick@wgN`; the registry, keys and profiles stay
    and the UDP port stays open with nothing listening. `master-wg peer AD
    ac|kapat` comments the peer's block out of the interface configuration, so
    it leaves the running interface at once and stays off across a reboot with
    its key, address and profile intact. `master-wg keepalive AD SANİYE`
    rewrites only the profile's `PersistentKeepalive`.
  - Registered networks and their units survive reboots and installer re-runs.
    There is no special installer-owned wg0. The SSH menu operates on the
    selected network; downloaded profiles are for devices.

### 1.10 Konsol and the file backend (DD-139, DD-140, DD-150)

- The file backend and bounded ZIP/RAR worker are built in (**DD-159/166**). The
  installer prepares their downloads account, `SERVER_ROOT`, private archive
  workspace and staged unit; `master-modul yerlesik` installs/enables/checks the
  unit. Files is always present in Konsol, independent of the app catalogue.

- **One console (DD-140).** `http://panel.${LOCAL_DOMAIN}` is the only
  tailnet administration page; Settings → Caddy can add one public HTTPS name
  for the same console (**DD-195**). Caddy serves the page files itself from
  `CONSOLE_WEB_DIR` (CSP, `no-cache` so a browser revalidates instead of
  re-downloading, `nosniff`, `X-Frame-Options: DENY`, no referrer; pages and API
  replies are compressed with zstd/gzip, **DD-181**), sends `/api/konsol/*` and `/api/uygulama/*` to `master-panel` and
  every other `/api/*` to `master-files-panel`. Both backends
  accept only that host and require the header `X-Konsol` on `/api/*`
  (**DD-147**); on the public name every path except the sign-in page and API
  also needs a Konsol session, while the tailnet address asks for none
  (**DD-194**, **DD-205**).
  - Pages (**DD-160**, **DD-200**, **DD-204**, **DD-212/213**, **DD-216**): Ana Menü is the
    landing page, with only installed application tiles and the network widget.
    Dosyalar, Paylaşımlar, App Store and Ayarlar have no home cards. Dosyalar, App Store
    (§1.11, cards with name/status/actions and descriptions only in Details), Podman
    (the container page) and Ayarlar remain in
    one responsive sidebar; Paylaşımlar is a tab inside Dosyalar, not a separate
    sidebar entry. Installed applications have no sidebar entry: each opens from its
    Ana Menü tile (and App Store "Aç"), and Ana Menü stays marked while its page is open. The skin is
    a wallpaper (inline SVG, no external asset) behind translucent surfaces; readers who
    ask for reduced transparency get opaque surfaces. An
    application's section, App Store texts and journal words come from its
    package's `konsol.json`; its page script and stylesheet are loaded from
    `/uygulama/<id>/` only while the package is installed and register through
    `window.Konsol.sayfa` (since **DD-202** the qBittorrent page too; the shell
    names no application). The qBittorrent page links the app by its tailnet name
    on the tailnet address and by its own public HTTPS name on Konsol's public
    address, only while that publication is active; otherwise it points to
    Settings → Caddy (**DD-195**). `/api/konsol/moduller` carries both as `urls`. CPU, memory and disk sit below the sidebar menu, read
    from the gated `/api/konsol/kaynaklar` endpoint; missing or stale
    measurements show as unknown, never as zero, and close the sidebar. Clock/date replace only the
    home heading; WAN/Tailscale addresses, uptime, version and the access channel are Ana Menü's
    1×1 "Sunucu" widget (**DD-230**, **DD-231**). Separate home
    clock/system widgets, including their unused SVG/CSS, are removed. An unknown route opens
    Ana Menü (`#/genel`); a page of an absent application opens App Store.
  - **Opening an application and its actions (DD-210, DD-212/213).** An application with a native
    web interface (its `urls`) opens there in a new tab (`noopener`) from its overview
    tile and its App Store "Aç" while it runs: the public name on the
    public HTTPS address, the tailnet name on the tailnet address. A stopped, busy or
    unpublished application (on the public address without an active public name) opens
    its Konsol page instead; the public address never links a private name. Beneath the
    icon of every installed App Store application's tile is a row with three fixed
    positions: **Durdur/Başlat**, **Ayarlar**, **Günlükler**. Desktop cards are approximately
    16% narrower than v191, retaining their normal height and 44 px action targets. **Durdur/Başlat**
    is a short word ("Dur"/"Başla", 13 px; the accessible name keeps "Durdur"/"Başlat"); **Ayarlar** is
    a gear and **Günlükler** a terminal icon (**DD-229**, **DD-230**); all are bare
    (no background or border; accessible names and tooltips remain),
    siblings of the launch link and absent in edit mode. Unsupported actions leave a
    blank, non-interactive slot so supported actions stay aligned. **Ayarlar**
    opens the package's declared `form` (read/write routes) in a dialog for the same fields
    as the install form (current values from the package API, never a password; only
    changed fields are sent; a blank password keeps the stored one), or else links the
    package's page; **Durdur/Başlat** appears only for `durdurulabilir` packages, asks the
    App Store's stop confirmation before stopping and uses the same lifecycle request and
    progress; it is locked (`aria-disabled`, still focusable) from the click until the
    operation ends, shows a refusal and follows the server's state. WireGuard stops
    and starts as a whole (**DD-229**). **Günlükler** opens a dialog backed by the existing
    module journal. Settings stay usable while the app is stopped. The page stays
    reachable from App Store details and its route.
  - **Home layout and network card (DD-206, DD-212/213, DD-229, DD-230, DD-242).** "Düzenle" (fixed to the
    screen's bottom-right corner; the page keeps room below the last row) lets the operator move tiles (dragging with mouse or finger, or arrow
    buttons), move the widgets with ◀ ▶ and hide or show them (**DD-231**, **DD-242**): "Sunucu" (`sunucu`, 1×1: Tailscale and
    WAN address, uptime, short version with the full one as tooltip, access channel), "Hız"
    (`hiz`, 1×1: the server's live WAN download/upload with download/upload glyphs, no chart)
    and "Ağ" (`ag`, 2×1: each application's total download/upload with the same glyphs, one line per
    application, scrolling inside the card). The widgets fill a block over the first two tile columns
    in order, row by row: a 1×1 card is one tile wide and one row tall, "Ağ" a whole row. The default
    order is Sunucu, Hız, Ağ (the 1×1 cards side by side, "Ağ" below them), the same on phones. An arrow
    moves a widget one place and skips steps the block would show unchanged; an arrow that would change
    nothing is disabled. Sizes are fixed; there are no width controls. The network is read only while "Hız" or "Ağ" is
    shown. App Store cards use the same column template and width as the home tiles. "Bitti" saves, "Vazgeç"/Escape drops the
    draft, "Varsayılan" returns to the defaults. The layout lives on the server:
    `GET /api/konsol/duzen` → `{duzen: {schema, kareler, widgetlar} | null}`, `POST`
    `{duzen: …}` or `{sifirla: true}`; the root backend checks the shape only (keys
    `^[a-z]{2,16}$`, at most 32 tiles and 8 widgets, width 1–4, boolean visibility), writes
    `KONSOL_AUTH_DIR/duzen.json` (0600, atomic) and logs `duzen kaydet|sifirla`; a damaged
    record means the defaults. The frontend ignores saved IDs of removed tiles/widgets
    and normalizes older `ag` widths to 2, preserving visibility; a saved widget order counts only
    when it names every widget (older records keep the default order). Tiles missing from
    the saved order (a newly installed application) follow in the default order.
    The network card reads `GET
    /api/konsol/ag` every 5 s while shown, alongside host resources and module state.
    There is no home Refresh button or duplicate ten-second home poll; hidden tabs pause
    periodic reads. Other pages retain their ten-second poll and busy installations
    retain their progress polling. The endpoint returns the WAN interface's (`WAN_INTERFACE`) receive
    and send rates in bytes/s — computed from `/sys/class/net/<if>/statistics`, a point at
    most every 1.5 s plus one per background sample, the last 120 s returned — and, per
    installed package that declares `PAKET_TRAFIK`, its own module's cumulative totals
    `{down, up, since}` (cached 2 s; a stopped package shows as stopped, a failing module
    only empties its own row). qBittorrent's are its own all-time totals from
    `qBittorrent-data.conf` with the file's time (`at`); these can lag between the
    application's statistics-file saves. WireGuard's are its networks' interface
    counters since the networks came up (`since`; down = sent to the peers).
    Live server rates/chart and the application table occupy equal-width, equal-height
    compact sections beside one another, stacking at very narrow card widths. The table is borderless, with three columns:
    application icon/name, cumulative download total and cumulative upload total.
    Its fixed-height area scrolls when rows overflow. Application totals use byte
    units, never bytes/s; only the server rates/chart section shows live speeds.
    Missing, non-finite or stale measurements show as unknown, never as zero; one
    application's missing measurement does not hide other rows or the server rates.
    Existing backend traffic sources and authentication are unchanged; no new rate
    module or additional qBittorrent login is introduced.
  - **Podman (DD-211, DD-216)** is a main sidebar page at `#/konteynerler` (title and
    sidebar entry "Podman"; formerly Konteynerler), with
    containers, images, named volumes and networks. Old Settings deep links redirect.
    Inventory merges real Podman state, installed App Store applications and saved
    definitions, including stopped containers with no live runtime object. Failed
    reads are shown as unavailable, never as empty collections or zero measurements.
    Details include mounts, port bindings and log tails (100/200/500/1000 lines) exactly as written, with no
    masking (**DD-251**); a Konsol or App Store container's tail is its unit's journal, across restarts and
    re-creations, any other container's is its `podman logs`.
    The list (**DD-213**) shows only the application/container name, status, resources
    and access; no image subtitle or ownership column. Its three icon actions keep fixed
    places (**DD-214**): start/stop and edit immediately before the name, remove at the
    end of the row. They use the home tiles' bare icons (play/pause, settings sliders,
    trash) and are disabled when unsupported or busy. Image details and additional
    operations remain on the detail page; permissions and confirmations are unchanged.
    Access shows published port mappings; a host-network container has none, so it shows
    the sockets its own processes listen on (**DD-215**, read from `/proc`: TCP LISTEN and
    unconnected bound UDP, IPv6 link-local left out): one line per port with its widest
    address, protocols and address kinds, at most three and "+N port daha", every address
    in the detail. Labels name the bound address (all, WAN, Tailscale, other, loopback),
    not reachability, which the firewall decides; an unreadable read shows as unknown.
    An App Store row shows its container name until the module catalogue answers, never
    the package id, and repaints when it does.
  - **Image updates (DD-214)** are checked, never applied, by Konsol.
    `GET /api/konsol/konteynerler/guncellemeler` compares each managed container's
    installed digest with what its channel tag points to now (an App Store package's
    `PAKET_IMAJ_KANAL`, a Konsol definition's tag reference) using registry manifests
    only, inside the backend's sandbox; answers are `guncel`, `var`, `sabit` (digest
    reference, nothing to follow) or `denetlenemedi` with a reason. The answer is cached
    for six hours; the page asks on open and "Güncellemeleri denetle" forces a check at
    most once a minute; a successful image change empties the cache. A row with a newer
    build shows "Güncelleme var", the summary counts them and the detail shows the state,
    channel and check time. Only an explicit `image-update` operation after a confirmation
    changes an image; there is no timer and no automatic update.
    - Start, stop, restart and remove use the actual owner. App Store lifecycle goes
      through `master-modul`; another systemd/Compose/pod controller remains read-only.
      A standalone external container may be controlled or explicitly adopted after
      a preview; unsupported options refuse adoption. No implicit ownership transfer.
    - Konsol definitions persist in private `KONTEYNER_STATE_DIR`. Ports, volumes,
      environment, command, resource limits, startup policy and the running account are
      editable. The account is the Files account (`DOWNLOADS_UID`/`GID`, no capabilities,
      group-writable files) or the image's own. A writable server folder needs the Files
      account, so a root image gets only volumes or read-only folders (**DD-227**). New
      containers start with the Files account; a definition saved before keeps the image's
      until the operator switches it. Changed
      settings recreate the container after validation; stopped saves stay stopped
      unless explicitly started. Manual stop suppresses boot startup until Start.
      Images are resolved to digests; updating one is an explicit operation.
    - Ports select local, Tailscale or explicitly acknowledged internet access.
      Netavark owns NAT; a separate project nftables guard limits managed bridge
      ingress, including direct/IPv6 paths. It also limits what a container opens itself:
      the internet yes; IPv6, anything out of `tailscale0` and the `VPN_BLOCK_DEST4` ranges
      (private, CGNAT, link-local, loopback, multicast) no. Replies to its publications
      still pass (**DD-224**). The same table's input chain closes the host itself: a
      container opens nothing on any host address (bridge gateway, WAN, Tailscale, WireGuard,
      loopback); only replies to host-opened connections and Aardvark's TCP/UDP 53 on the
      incoming bridge's own address pass (**DD-229**), independent of MASTER-INPUT. No host networking or runtime socket
      mount is offered for generic containers. Bind mounts use existing, non-hidden,
      non-symlink user folders under `SERVER_ROOT`, excluding protected app/share paths.
      They are checked again and pinned at every start (**DD-226**). The unit's
      `ExecStartPre` walks each folder from `/` without following links and binds the
      directory behind that descriptor onto a root-owned anchor under
      `KONTEYNER_BAGLAMA_DIR`, which the Quadlet mounts instead of the path. A missing
      or symlinked folder keeps the container down (fail closed). `ExecStopPost`
      releases the anchors.
    - Removing a container retains its volumes and host files. Unused standard named
      volumes and managed bridge networks have separate removal actions. In-use
      resources and package-pinned images cannot be removed through generic controls.
    - qBittorrent exposes its real listener port, its WAN peer port (**DD-221**) and
      download folder through its package adapter. Required mounts remain protected;
      native Web UI, Caddy upstream, publications, the container guard, health checks
      and installer re-runs use the same durable port override. Only a changed port is
      recorded. A peer port must be 1024–65535, differ from the listener, belong to no
      other project service and be bindable on the WAN address over TCP and UDP; there is
      no install-time free-port search. Account editing remains in the application's
      existing settings form.
    - `GET /api/konsol/konteynerler/{liste,ayrinti,gunluk,islem}` and `POST
      /api/konsol/konteynerler/islem` retain the existing Host/channel/session/CSRF
      gates. Writes return 202 plus an operation ID, then a bounded root worker
      records actual success/failure. A stale revision or busy mutation is rejected.
      Submitted passwords/secret environment values never appear in read responses
      or operation/audit records. There is no background reconciliation engine.
  - Ayarlar (**DD-156**, superseding DD-155) has five tabs: Sistem, Güvenlik
    Duvarı, Caddy, Dnsmasq and Günlük. `GET
    /api/konsol/ayarlar` retains the same gates and 5 s cache (`?yenile=1`
    bypasses it); `/durum` reads transaction state and `/klasorler` lists
    allowed existing download folders. No password/hash is returned.
    - Sistem shows three cards (**DD-245**): "Panel ve sunucu" (facts, the Konsol account and
      "Yeniden başlat", **DD-246**: typed "onayla", tailnet only, refused beside an update, a repair or a
      package operation, `systemctl reboot` 5 s later), the two-row health card and "Denetle ve onar".
      The health card (`GET
      /api/konsol/saglik`, cached 30 s, **DD-182**): failed units, Tailscale
      state and key expiry, `master-firewall --check`, a pending reboot, NTP
      sync, free space and inodes against the upload reserve, a pending or
      stuck settings change and a WAN share whose address is gone. It never
      repairs anything.
      **DD-189:** required core units and running optional modules are checked
      for actual activity; deliberately stopped WG networks/modules stay valid.
      Absent reboot flags also trigger a same-flavor distribution boot-link,
      image/initrd comparison (module paths are hidden by the service sandbox).
      Unknown probes are warnings, never green.
    - Güvenlik Duvarı shows real IPv4/IPv6 rules and counters from all
      iptables tables, listening sockets, and the baseline policy check.
      Structured port overrides have family, WAN/tailnet scope,
      TCP/UDP port, optional source CIDR and allow/deny action. Only these
      overrides are editable; core and third-party rules are read-only.
      `CHAIN_SETTINGS` precedes `ts-input`, so a tailnet deny is effective.
      Loopback, established flows and ICMPv6 protections remain intact outside WG;
      the mandatory WG deny precedes them.
      Permission does not imply a reachable listener; no bind address is changed.
      **DD-164:** group port permissions by incoming network: Tailscale (default),
      Internet, WireGuard only when installed (selectable tunnel interfaces), and
      protected loopback. WireGuard public UDP endpoints belong to Internet,
      not to tunnel-client traffic. Technical rules is a separate, all-network
      read-only view including forwarding/NAT. Socket bindings carry explicit
      scope metadata; unknown/unreadable and no listener remain distinct from
      policy. Refresh re-reads the live state; switching tabs preserves drafts.
    - Caddy shows base/module sites and their routes. Its local-domain
      field changes the single-label suffix (1–63 lowercase letters/digits/hyphens,
      no leading/trailing hyphen) as a separate transaction (**DD-157**).
      Base/module DNS and Caddy renderings, custom record suffixes, disabled
      names, `state.env` and staged/installed file-backend units move together.
      Only an active file backend restarts; Caddy reloads gracefully. Credentials,
      VPN profiles, IP-based share links and download data stay untouched.
      Before applying, the operator adds the new restricted domain to Tailscale
      Admin DNS and retains the old mapping until confirmation. The server
      cannot edit those account settings. Confirmation must arrive through
      the new panel Host within five minutes; otherwise the guard restores
      the previous domain. No old-name alias or arbitrary Caddy editor is added.
    - **Publication table (DD-191, DD-195, DD-199):** Panel's Tailscale switch is
      fixed on; its internet switch and HTTPS name are editable, need an existing
      Konsol account and, when turning on or renaming, `confirm: onayla`
      (typed in the page, checked by the server). WebDAV and every installed
      package that declares a publication (today qBittorrent) have independent
      Tailscale/WAN toggles, a public hostname and a per-row Save. Toggles edit
      a draft, not the server. Tailscale off produces a 403 Caddy route without
      stopping the service; shared listener ports can remain. Per-folder
      connection policies/authentication remain mandatory (DD-192); cards show
      why a global gate prevents access. Disabled WAN names are kept
      for re-enabling; no plaintext fallback. qBittorrent requires permanent
      native password/login, CSRF/Host checks and active attempt bans; its own
      preferences remain unchanged. Stopped/uninstalled modules are not published.
      All active HTTPS names share one port/permission and its socket budget.
      Known private/public projections survive reruns and use Settings snapshots
      on failure/crash. A reset account or lost WAN address removes the public
      Panel site at the next 30 s guard run. No Tunnel or arbitrary proxy.
    - The separate **public HTTPS domain** field per row (**DD-190/191**) accepts
      a full domain, not a URL/IP/port/path/wildcard. Public DNS must resolve
      to exactly the assigned `WAN_IPV4`, with no AAAA or proxy. It does not
      alter `LOCAL_DOMAIN`, dnsmasq or Tailscale Admin DNS. Caddy owns Let's
      Encrypt issuance/renewal through TLS-ALPN on TCP `SHARE_HTTPS_PORT`
      (443), with HTTP challenge and automatic port-80 redirects disabled;
      no DNS provider token is needed. The standalone save uses durable
      pending state and commits only after chain/hostname verification.
      Failure or pre-commit crash restores the previous projection. Explicit
      removal saves an empty domain and closes WAN without an HTTP fallback;
      Caddy reload is graceful, so existing transfers may finish. The status
      probe connects locally to the assigned WAN IP, pinned independently
      of the domain's DNS, and verifies the name with SNI: readiness does
      not prove internet reachability. Settings shows certificate expiry;
      health warns when at most 14 days remain. Folder network/auth rules,
      all private admin/API boundaries remain unchanged; DD-191 can separately
      disable the WebDAV/qBittorrent private route.
    - Dnsmasq permits on/off for managed names, exact custom names within
      `LOCAL_DOMAIN`, and optional public upstream IPs. Missing/disabled
      private names stay local. Base/module collisions and local/self
      upstreams are rejected; loopback/tailnet listeners stay unchanged.
      This neither creates Caddy sites nor edits Tailscale Admin DNS.
      DNS-only Apply validates, restarts dnsmasq and commits immediately, with
      no 60 s confirmation (**DD-163**). The console's own name cannot be
      disabled; reject that request before writing files or restarting services.
    - Günlük lists both backends' audit lines from the last 7 days
      (`/api/konsol/islemler`), including archive job results (**DD-183**); a
      package API's events are `<id>:<verb>` lines, labelled by the package.
  - The qBittorrent page (only while installed, **DD-160**; the package's own
    `sayfa.js` since **DD-202**) holds its service controls, Web UI link,
    first-login card and account/folder form. The form posts to the package API
    (`POST /api/uygulama/torrent/{hesap,dizin}`), which runs the package worker
    `ayar.py` as a transient root unit with JSON on stdin (`ctx.worker`; the
    script must sit in the package folder). It permits username, optional new
    password (8–256 characters) and the default folder for new torrents; blank
    preserves the password. Only canonical existing non-hidden downloads/media
    directories may be chosen (the base's folder policy; write permission is
    probed as the service UID). A folder outside the downloads tree is bind-mounted
    into the container at the same path by one quadlet drop-in
    (`<container>.container.d/90-konsol.conf`, **DD-209**); a folder inside it removes
    that drop-in; a folder name with whitespace, `:` or `%` cannot be mounted and is
    refused. After a restart the change counts only once the interface answers on
    loopback. Existing files/torrent locations and
    incomplete paths are not moved. Every change is direct (**DD-165**,
    **DD-202**): stop/snapshot/write/start/verify with explicit success/failure
    feedback and no draft, review, countdown or pending record; a failure
    restores both files and starts the service again. A temporary startup
    password can rotate on restart. Stopped services remain stopped.
    `GET /api/uygulama/torrent/durum` is the page's read-only view (paths,
    interface, account name, service state); the password hash never leaves.
  - Settings transactions: `POST /api/konsol/ayarlar/{uygula,onayla,geri-al,birak}`
    runs an independent
    worker with JSON on stdin, never a password on argv/in logs. DNS-only
    and standalone HTTPS or Caddy publication-row (`web`) requests return
    `{pending: null, committed: true}`
    after a durable commit (HTTPS enablement first verifies the certificate);
    only the server determines eligibility from the supplied change sections.
    Other requests retain review and a 60 s confirmation window (300 s for a
    local-domain change), including mixed DNS/firewall requests. HTTPS cannot
    be combined with another settings section; an application's own settings
    are never part of it (**DD-202**).
    Failed immediate applies restore snapshots; interrupted pre-commit writes retain
    guard recovery. The commit marker prevents recovery from undoing a durable
    commit after a crash. The server-side guard timer
    restores unconfirmed settings after disconnect, timeout or reboot. It runs
    only while a change is pending (**DD-181**): apply starts it before the
    pending file exists, an idle run stops it while holding the locks, and at
    boot it runs once; the unit stays enabled;
    failed recovery remains pending and is retried after 15, 30, 60 and 120 s.
    After the fifth failure it is "stuck" (**DD-182**): no more automatic
    attempts; Konsol shows the last error with "Yeniden dene" and "Bırak"
    (typed `onayla`; files stay as they are, re-run the installer to apply the
    saved settings). The installer refuses to run while anything is pending. Stale revisions and concurrent
    installer/module writes are refused. Confirmation cannot preserve a rule
    that blocks the confirming client's new console/DNS connections or the
    console's own DNS name. `SETTINGS_FILE` owns confirmed firewall/DNS/local-domain
    and public-HTTPS choices across re-runs; `SETTINGS_PENDING_FILE` is root-only recovery data,
    not a portable backup. qBittorrent remains the owner of its profile.
  - The package worker's profile reader and the base's share path check both
    use descriptor-relative no-follow, nonblocking regular-file reads
    (**DD-186**): 64 KiB for the package's view and 1 MiB for share path checks. A missing profile is
    allowed; an unsafe/unreadable profile prevents share changes.
  - A peer or a whole network can be switched off and on (§1.9).
- **Folder shares (DD-158/DD-192):** each Shares entry has two connection cards,
  Tailscale and WAN, with independent switches, RO/RW, expiry, address/copy and
  Infuse connection details. WAN is labeled HTTPS when configured, or HTTP (WAN)
  with the plaintext warning in legacy mode. General Caddy gates override both
  cards and explain unavailable access. Manage edits the shared folder/account/
  password separately. Partial connection updates preserve all omitted values
  under the locks, including exact expiry, and never rebind a folder unless a
  path is explicitly supplied. Both switches may be off. Share edits still
  restart active WebDAV and interrupt all transfers; retain the UI warning.
  See §5–7.
- **Archives (DD-166, DD-170, DD-232):** selecting files shows their actions in
  the Files window's right-hand detail column. Archive creation produces ZIP; the archive opener automatically
  detects multipart RAR and nested ZIP/RAR (unencrypted RAR3/RAR5, solid and
  multipart sets) through an unprivileged, resource-limited RAR helper, never a
  shell extraction command. The destination defaults to downloads with a
  folder picker. Depth/size/time limits are enforced internally, without a
  nesting prompt; source archives are kept. Jobs, limits, private history and
  atomic publication are specified in
  [desktop-and-archives.md](desktop-and-archives.md).
- `master-files-panel.service` serves a file manager API for
  `SERVER_ROOT`: browse, search the current folder, select many items, new
  folder, rename, move, move to trash, restore, delete from the trash, empty
  the trash, read a text file, download a file and **upload** files
  (**DD-145**).
  - Upload is `POST /api/upload?path=&name=`, the body being the file itself.
    It writes a temp name in the target folder, `fsync`s, then renames into
    place, so a half-written file never appears in the listing and an existing
    name is never overwritten (409). The stream runs without the panel lock;
    only the final rename takes it. The file lands `0664`.
  - **Disk reserve (DD-180):** an upload is refused before its body (507) and
    stopped while streaming when free space would fall under min(5 GiB, 10% of
    the filesystem); the temporary file is removed. WebDAV PUT and file COPY
    keep the same reserve.
  - The console has no separate upload area: files are dropped onto the list
    itself, appear there as rows and show their progress in the row.
  - It runs Python 3's standard library only and listens on
    `127.0.0.1:61009`. Caddy exposes it on the tailnet; nothing exposes it on
    WireGuard or the WAN.
  - It runs as `DOWNLOADS_UID`/`DOWNLOADS_GID`, never as root.
    - systemd needs a user entry for that uid. The installer uses an existing
      name, or creates the system account and group `DOWNLOADS_ACCOUNT`
      (`master-downloads`, no login, no home). File ownership stays numeric.
    - The unit has no capabilities and `ProtectSystem=strict` with only
      `SERVER_ROOT` writable, plus `ProtectHome`, `PrivateTmp`,
      `PrivateDevices` and `NoNewPrivileges`. `PRIVATE_STATE_ROOT` (`/var/lib`), where
      packages keep their private state, is inaccessible (**DD-225**).
    - Because unrar opens untrusted RAR files here (**DD-180**): network only to
      and from loopback (`IPAddressDeny=any`, `IPAddressAllow=localhost`),
      `SystemCallFilter=@system-service`, `ProtectProc=invisible`,
      `PrivateIPC` and `MemoryDenyWriteExecute`. Loopback services such as DNS stay
      reachable from it. qBittorrent's interface does not: since **DD-217** its loopback
      port is a container publication, and a unit with this address filter gets no
      answer from it (measured on nrm, 2026-10-05).
  - It sees no sessions: Caddy asks the root backend before proxying (**DD-194**;
    **DD-205**: the tailnet passes, the public name needs a session); the
    stage-7 self-check uses its loopback port.
    `Host` check, CSP,
    `no-store` and the audit log match it (the actor is logged as `konsol` with
    the client address). `/api/*` needs the `X-Konsol: 1` header and a
    same-origin fetch; only a download, opened as a link, needs no header, and a
    cross-site download is still refused.
- The file panel never leaves its root and never overwrites.
  - Every path step is opened from a directory descriptor with `O_NOFOLLOW`. A
    symbolic link is listed but never followed, and `..` and `/` are refused.
  - Rename and move use `renameat2(RENAME_NOREPLACE)`. An existing target
    refuses the operation, and a folder cannot move into itself.
    Root `.cop`, `.pay` and `.arsiv` sources are rejected before any item in a
    move/trash batch is changed; nested reserved names cannot be moved into
    the root. Restore chooses an alternate name for a reserved root name
    (**DD-186**).
  - Names over 255 bytes or with `/` are refused; new names may not contain
    control characters or leading and trailing spaces.
- Delete moves the item into `SERVER_ROOT/.cop/<id>/` (`FILES_PANEL_TRASH`) with a
  small origin record, on the same disk.
  - Move-to-trash has a short confirmation; long names remain available in its
    subtitle/tooltip without overflowing. Permanent deletion guards are unchanged.
  - Restore puts it back where it was, or into the root if that folder is gone.
    A taken name gets a number.
  - Deleting permanently works only from the trash; emptying it needs
    `onayla`. The trash is not reachable through any path, and the root listing
    hides it.
  - The installer creates the folder. It lies outside `SERVER_ROOT/downloads`,
    so qBittorrent never sees it (**DD-144**). The WebDAV unit lists the trash, the
    archive staging area `.arsiv`, `.pay` when present and `PRIVATE_STATE_ROOT` in one
    `InaccessiblePaths=` line (**DD-225**), and a share can be neither the root nor
    contain a hidden or reserved name (**DD-158**, §7).
- Text view: the first 1 MiB of a regular file.
  - A file with a NUL in the first 8 KiB is refused as binary.
  - The encoding is guessed (UTF-8, else Windows-1254; `.nfo` in CP437) or chosen
    by the operator, and decoded on the server.
  - The page inserts the text as text nodes only.
- **Text editor (DD-249).** In both views a file the backend calls editable opens in the editor
  (CodeMirror 6, `console/duzenleyici.js`, loaded on first use from Konsol's origin; its rules go
  through a constructed style sheet, so the CSP stays `style-src 'self'`). Editable means: the whole
  file was read (at most `TEXT_LIMIT`, 1 MiB), it decodes without loss in the chosen encoding, it has
  one hard link, no setuid/setgid bit and, in the `/srv` view, the service account owns it.
  - `GET …/text` returns the bytes' SHA-256 as `version`; `POST …/text/save` (`path`, `text`,
    `encoding`, `version`; body up to `TEXT_BODY_MAX`) writes only while the file still has that
    version (409 otherwise) and the encoded text fits in `TEXT_LIMIT` (413).
  - The text is written in the same encoding (a UTF-8 BOM is kept) and with the file's line endings
    (CRLF if it had any); a character the encoding lacks is refused (400), never replaced.
  - The save is the one exception to "nothing overwrites": a temporary file in the same folder gets
    the old file's owner, group, mode and extended attributes, is synced, the old file is checked
    again (same device, inode, size and mtime) and the temporary file is renamed over it; any failure
    removes the temporary file. Audit: `duzenle <path>`.
  - In "Sistem (/)" the save runs as root: read-only modes (e.g. `0440`) are no obstacle and are kept.
    The editor says the previous content cannot be brought back (this view has no trash).
- The page refuses to select, share or trash the folders packages declare they
  write into (`PAKET_KLASORLER`, delivered root-relative with the owner's name in
  `/api/state.protected`, **DD-203**) and says which application writes there.
  Since DD-178 new qBittorrent profiles do not enable separate temporary
  storage; the declared folder is a reserved default, not an enabled setting.
- **Details and address (DD-237).** The selection's details/actions are a fixed-height panel under the
  contents (desktop width); a shared folder shows a one-line summary, the full share cards stay on
  Paylaşımlar. Favoriler shows the operator's favourites first (**DD-250**), then 8 top folders and a "show all" switch. The open folder is in the address
  (`#/dosyalar/klasor/…`, `#/dosyalar/sistem/…`); a malformed address opens the tree's root and the
  backends keep checking every path.
- **Separate panels (DD-243).** On screens of at least 1101 px the contents, the details and the places
  column are three glass panels with a small gap. The details are one fixed 82 px panel: the item's
  name with one info line under it (type, size, location, last change, a shared folder's open
  connections; **DD-244**) and the actions as words ("Seçimi bırak", "Paylaşımı yönet/kaldır" among
  them). The path bar shows no item count or size; with nothing selected the details name the open
  folder's count and size.
- **Folder count and size (DD-247).** A folder's icon-view tile and its info line give "N öge · size"; the
  size is the backend's walked total and is left out when the folder is empty or was not walked (walk
  budget, a non-local file system in "Sistem (/)" per DD-248, unreadable), leaving the count alone.
- **Favourites (DD-250).** In the details a star follows the folder's name (hollow: add, filled: remove;
  a long name is cut, the star stays) for a selected folder or the open one (not a tree's root), in both views. `GET /api/konsol/favoriler` →
  `{favoriler: [{yol, sistem}]}`, `POST` `{ekle: {yol, sistem}}` (appended last, once) or `{cikar: …}`;
  the root backend keeps them in order in `KONSOL_AUTH_DIR/favoriler.json` (0600, atomic, removed when
  empty; an account reset keeps it), at most 20, `yol` relative to its tree without empty, `.`/`..` or
  control-character parts (255 bytes a part, 1024 in all), and logs `favori +|- <path>`. Entries of the
  system view (`sistem: true`) are neither listed to nor changed from the internet channel (403). A
  favourite is not checked against the disk: a missing folder answers "bulunamadı" when opened. In the
  places column they come first, above Sunucu and Sistem (/), with their location and a × on hover or
  focus; on narrow screens the strip shows the name only (the filled star removes it).
- **Seç (DD-244).** A toggle beside Yükle: each item shows a check and a click adds or removes it without
  opening it; "Tümünü seç" is a detail action. Seç again, Esc, an empty-space click, "Seçimi bırak" or
  another folder ends it.
- **Navigation (DD-236).** Opening a folder repaints only the contents, the path, the
  places mark and the detail; the window's frame is built once per tree. The listing on screen stays
  (inert) until the next arrives; a failed open stays in place; back/forward keep each folder's
  scroll; a one-minute cache of 20 listings is always re-read. On screens of at least 1101 px the
  window has the viewport's height and only its parts scroll.
- **"Sistem (/)" (DD-235).** A separate unit, `master-sistem-dosya.service`, runs the same
  backend with `--sistem --root /` **as root**, for the whole server. The `/srv` view above is
  unchanged and still never runs as root.
  - It listens only on `SYSTEM_FILES_SOCKET` (0660 `root:CADDY_GROUP`, peer credentials checked),
    no TCP port, `IPAddressDeny=any`. Caddy routes `/api/sistem/*` to it in the Tailscale site only;
    on the public HTTPS name that path reaches the file backend and gets 404.
  - The backend refuses (403) any request whose Caddy-written `X-Konsol-Kanal` is not `tailscale`
    or whose client (`X-Forwarded-For`) is not another Tailscale device; a wrong `Host` is refused too.
  - Same traversal and no-overwrite rules as above. No trash, archives, shares or package-folder
    marks. Since DD-238 no root folder is read-only (`/proc`, `/sys`, `/dev`, `/run` included; the
    kernel's own refusals still apply) and no warning strip is shown; new folders are `0755`, uploads
    `0644`. Since DD-248 folder sizes are walked only for a folder on a local disk file system
    (`LOCAL_FS`, by its device in `/proc/self/mountinfo`) and never across into another device
    (`du -x`); `/proc`, `/sys`, `/dev`, overlay and network mounts give a count without a size.
  - Delete (`/api/sistem/delete`) is permanent: `confirm` must be the item's name, or `onayla` for
    several. An item that is a mount point or has a mount below it is refused (409), and the
    recursive delete stops at a device change.
  - Every write and download is in the audit log as `dosya: sistem <address> ...` and in Günlük.
  - Trade-off: every tailnet device gets root file access (Konsol has no tailnet sign-in, **DD-205**).

### 1.11 App Store and built-ins (DD-148, DD-149, DD-159, DD-197, DD-200)

- A clean install includes Files, folder WebDAV and archive tools. Optional applications
  are installed/removed from Konsol → App Store. The catalogue is the set of packages
  under `Data/magaza/<id>/` whose manifest is not built-in: today `wireguard` and
  `torrent`. Both support start/stop. Stopping WireGuard (**DD-229**) records its
  enabled networks in `WG_STOPPED_FILE`, disables them and marks the package `durduruldu`, so
  the firewall drops its UDP ports, forwarding and NAT; it stays down across reboots and
  installer re-runs, and `master-wg` refuses to open or add a network until Start, which
  reopens only the recorded networks. Its per-network switches remain. Public verbs reject `dosya`/`paylasim`: they are built-ins, not
  installable/removable applications. Podman is base infrastructure, not a catalogue
  item (§1.3, **DD-208**).
- **Container applications (DD-209).** `PAKET_CALISMA=konteyner` marks an application
  that runs in Podman; Konsol shows it like any other application (tile, App
  Store row with a "Konteyner" chip; its state is its unit's liveness, as for `host`).
  `PAKET_KONTEYNER` names the package's quadlet file (`<name>.container`), which the
  engine places into `KONTEYNER_BIRIM_DIR` (`/etc/containers/systemd`) with a
  `daemon-reload`, removes on `durdur`/`kaldir` (a generated unit cannot be disabled)
  and checks after removal like a drop-in. `PAKET_IMAJ` is the image, accepted only as
  `name@sha256:<digest>`; `paket_imaj_cek` pulls it (bounded to 900 s) only when absent,
  so re-runs and boots never download (`Pull=never`); `paket_imaj_sil` (hooks' `--veri`)
  removes it by image id and leaves an image another tag or container uses. A new
  digest in the package and an installer run updates installs without an approved update
  (no `TORRENT_IMAGE` override); after an approved update the recorded digest stays, also
  across `kaldir --veri` (**DD-220**), until the next approved update. `PAKET_IMAJ_KANAL`
  names the tag Konsol checks (**DD-214**); with a container adapter the application also
  offers `image-update`: the adapter validates the files that name the image, pulls the
  exact digest the check saw, rewrites that image line in the rendered and the placed
  Quadlet and in the rendered manifest (a Quadlet drop-in cannot replace `Image=`), saves
  the digest as the package's durable override so the installer renders the same, restarts
  a running app, verifies its interface and the container's image, and on any failure
  restores every file and the previous service. The previous image is removed only after
  success. There is no automatic update.
- **A container application's own bridge (DD-217).** `PAKET_KONTEYNER_AG` names the
  application's own Podman bridge network. The engine creates it when missing with the
  container guard's interface naming (`KONTEYNER_BRIDGE_PREFIX` plus the first ten hex digits
  of the name's SHA-256) and the label `io.master-stack.paket=<id>`, refuses a same-named
  network that is not the package's, refreshes the guard after placing or removing the quadlet,
  and removes the network with `kaldir`. The guard drops every forwarded packet into such a
  bridge except replies and what the registered package's placed quadlet publishes as an IPv4
  `address:port:port/protocol` on the server's WAN or Tailscale address; a loopback publication
  needs no forward path, and no IPv6 ingress is opened. qBittorrent runs on its own bridge
  `torrent` with exactly three publications: the interface `127.0.0.1:TORRENT_UI_PORT/tcp`
  (Caddy and the publication reach it there) and the peer port `WAN_IPV4:TORRENT_PEER_PORT`
  (63851, **DD-219**) over TCP and UDP; `TORRENTING_PORT` fixes qBittorrent's own peer port to the same
  number and its profile's interface address is `*` (the install sets it). The hook verifies
  that `podman port` lists exactly these three. The WAN address is the installer's
  `WAN_IPV4`; when it changes the installer must run again. qBittorrent has no IPv6 peers on
  this bridge. Changing the interface port in the Podman page also moves the loopback
  publication line in the rendered and the placed quadlet; changing the peer port moves both WAN
  lines and `TORRENTING_PORT` there, sets the profile's `Session\Port`, records the override and
  reapplies the container guard before the restart (**DD-221**). The Podman page labels a
  publication on the WAN address as internet access and shows the bridge's name.
- **Install form (DD-210).** A package may declare an install form: `konsol.json`
  `form` (generic fields `metin`/`parola`/`klasor`, texts, the package API's read and
  write routes) and the manifest's `PAKET_KUR_AYAR` (its worker). App Store's "Kur" then
  opens the form and sends nothing until a valid submission; cancel/Escape changes
  nothing. `POST /api/konsol/moduller/<id>/kur` requires `{"form": {...}}` for such a
  package (400 without it; a package without `PAKET_KUR_AYAR` refuses a form). Under one
  lock the backend refuses a busy or installed package (409), runs the worker as a
  transient root unit with the form on stdin (`<worker> --lib … --state … kur-hazirla
  --tohum RUNTIME_DIR/modul-<id>.kur`), and starts the engine only after the worker
  accepted; a refusal is the request's 400 and nothing is installed. The worker writes a
  seed file (0600, owner root) holding the validated values with the password only as
  the application's hash. `master-modul kur` of such a package refuses to run without a
  fresh (≤10 min), private, root-owned seed, hands its path to the hooks as `KUR_TOHUM`
  and removes it (and the hook's `.onceki` snapshot) when the install ends either way;
  the backend removes it if the engine could not be started. The password never reaches
  argv, environment, journal, audit, progress or a persistent plaintext file.
- **Package (DD-197).** `Data/magaza/<id>/` holds the manifest `paket.env` (`PAKET_AD`,
  `PAKET_SIRA`, `PAKET_CALISMA`, `PAKET_DURDURULABILIR`, `PAKET_HESAP`, `PAKET_APT`,
  `PAKET_ARACLAR`, `PAKET_EKLER`, `PAKET_ADLAR`, `PAKET_GUNLUK`, `PAKET_KUR_ADIM`,
  `PAKET_YAYIN`, `PAKET_UYGULA_HEP`, `PAKET_UYGULA_NEDEN`, `PAKET_YERLESIK`, and the Konsol
  keys `PAKET_KONSOL` (App Store texts and page declaration), `PAKET_SAYFA` (page files),
  `PAKET_API` (backend module), **DD-200**, `PAKET_TRAFIK` (traffic-totals module for
  the overview's network card, **DD-206**), `PAKET_KONTEYNER`/`PAKET_IMAJ` (a
  container application's quadlet and pinned image, **DD-209**), `PAKET_KUR_AYAR`
  (the install form's worker, **DD-210**), `PAKET_PORTLAR` (Settings port catalogue
  rows, **DD-198**), `PAKET_YAYIN_AD`/`PAKET_YAYIN_YEREL`/`PAKET_YAYIN_UPSTREAM`/
  `PAKET_YAYIN_PORT_ANAHTARI`/`PAKET_YAYIN_DENETIM` (the Caddy publication row,
  **DD-199**), `PAKET_KLASORLER`/`PAKET_KLASOR_MODUL`/`PAKET_ARKAUC_YOLLAR` (folders the
  package writes, its report module and the backend's write paths, **DD-203**),
  `PAKET_KONTEYNER_YONETIM`/`PAKET_AYAR_ANAHTARLAR` (the Podman editor adapter and the
  keys a durable override may change, **DD-211**, **DD-214**), `PAKET_IMAJ_KANAL` (the
  tag the update check follows, **DD-214**) and `PAKET_KONTEYNER_AG` (the package's own
  bridge, **DD-217**)), the hook
  file `kanca` (`paket_kur`, `paket_kaldir`, `paket_uygula`, `paket_baslat`, `paket_durdur`,
  `paket_birim`, `paket_hesap`, `paket_veri_sil`, `paket_gunluk_suz`, `paket_ozet`) and the
  package's files: `<id>.caddy`, `dnsmasq.conf`, units, drop-ins, tools, seeds,
  `konsol.json`, `sayfa.js`/`sayfa.css`, `api.py`. The engine
  reads the manifest with a strict line pattern (never sourced) and sources the hooks.
  A package keeps its private host state (profiles, keys, sessions) under
  `PRIVATE_STATE_ROOT` (`/var/lib`), which Files, WebDAV and unrar never see, or makes
  it readable by root only (**DD-225**).
- The installer, on every run:
  - installs `/usr/local/sbin/master-modul` and renders every package folder to
    `MODULES_DIR/<id>/` (`/usr/local/share/master-stack/moduller`): a file with
    `__KEY__` placeholders is filled from the installer's variable of that name (a
    missing variable stops the install), other files are copied, executables keep 0755;
  - creates `MODULES_FILE` (`/etc/master-stack/moduller`) empty when absent,
    and `CADDY_MODULES_DIR` (`/etc/caddy/moduller`), which the base Caddyfile
    imports (`import …/*.caddy`, after the global options); the file backend's
    unit is staged in `MODULES_DIR/dosya/` before built-in activation;
  - invokes `master-modul yerlesik` to enable/check Files and WebDAV, preserve
    their account/history state, and restart only changed/inactive services;
  - never automatically installs/removes optional apps. When a rendered file
    changed, or the manifest says `PAKET_UYGULA_HEP=1`, and the package is registered
    (`calisiyor` or `durduruldu`), stage 7 first runs `master-modul uygula <id>`.
    A failure is a warning, not a stop.
  - keeps a change until it is applied (**DD-222**): the first changed or removed
    rendered file of a package writes the empty marker `MODULES_PENDING_DIR/<id>`
    (`/etc/master-stack/moduller-bekleyen`, 0700 root; also `paylasim` for a changed
    `master_shares.py`/`master_webdav.py` and `dosya` for changed Files code or unit).
    A marked package counts as changed in every later run. The marker is removed only
    after `uygula` succeeded, after `yerlesik` for the built-ins, or when the package is
    not registered. So a run that fails between stage 4 and stage 7, or whose `uygula`
    fails, is applied by the next successful run. A marker that cannot be written stops
    the install.
  - always checks built-in Files/WebDAV; checks WireGuard networks only while
    the optional application is installed. The summary names each package from its
    manifest with one line from its `paket_ozet` hook.
- `master-modul` (root) knows no application:
  - `liste` prints, per catalogued package in `PAKET_SIRA` order, `id runtime registry
    live action step total text` separated by tabs; `runtime` is `PAKET_CALISMA`
    (`host`, `konsol` or `konteyner`, **DD-209**),
    `registry` is `yok`, `calisiyor` or `durduruldu`, `live` comes from the package's
    `paket_birim` unit when it has one.
  - `kur ID`, `baslat ID`, `durdur ID` (only `PAKET_DURDURULABILIR=1`), `kaldir ID
    [--veri]`, `gunluk ID [LINES]`, `uygula ID`; `hesap ID [--parola]` (only
    `PAKET_HESAP=1`); the installer's `yerlesik` activates the built-ins (below).
    Any other id, verb or argument is refused before anything runs.
  - Apt packages, tools (`SBIN_DIR`, 0755), unit drop-ins (`UNIT_DIR`, 0644), names and
    Konsol page files (`CONSOLE_WEB_DIR/uygulama/<id>/`, 0644, **DD-200**)
    are placed and removed by the engine's helpers, which the hooks call in the order
    the package needs. After `kaldir` the engine removes every declared artifact and
    fails the operation if any remains; `--veri` additionally runs `paket_veri_sil`.
  - Changes take `RUNTIME_DIR/modul.lock`; a second operation waits up to 5 s
    and then fails.
  - Progress is one line in `RUNTIME_DIR/modul-<id>.ilerleme`:
- WireGuard (`wireguard`, **DD-150**, package hooks since **DD-197**): `kur` in five
  steps — packages, tools (`master-wg` and the `wg-quick@` drop-in from the manifest),
  kernel module, firewall hook (the module is registered, then `master-firewall` is
  restarted), networks from the registry. `kaldir` closes the networks,
  unregisters the module, re-applies the firewall and removes
  `WG_MODULES_LOAD_FILE`; `--veri` also empties `WG_CONF_DIR`. `uygula`
  (every installer run while installed) makes sure of the packages, the kernel
  module, the Konsol page and the networks. `gunluk` reads `journalctl -u wg-quick@*`.
  Stage 7 runs the package's `paket_denetle` (tool, modules-load file, each network's
  listen port and address, no file-backend answer on a VPN address); the summary takes
  its note from `paket_not` and its counts from `paket_ozet` (**DD-201**).
- qBittorrent (`torrent`, **DD-151**, package hooks since **DD-197**, a Podman container
  since **DD-209**): `kur` in four steps — image (`TORRENT_IMAGE`, pulled by digest if
  absent), container unit (profile seed, the install form's account and folder, then the
  quadlet `qbittorrent.container`), service start, name. It is installed only with its
  App Store form (**DD-210**): username (`[A-Za-z0-9._@-]{1,64}`, default `admin`), a
  required password (8–256 characters) and the download folder (default
  `DOWNLOADS_PATH`; the same downloads/library policy as the page's folder choice).
  - It runs as `qbittorrent.service`, which Podman's generator writes from the quadlet:
    `Network=torrent` with exactly three `PublishPort` lines (**DD-217**), `Pull=never`,
    journald logging, `StopTimeout=45`, capabilities `NET_BIND_SERVICE SETFCAP SYS_CHROOT`
    dropped, `PUID`/`PGID` = the downloads account, `UMASK=002`, `WEBUI_PORT=TORRENT_UI_PORT`,
    `TORRENTING_PORT=TORRENT_PEER_PORT`,
    `Nice=10`/`CPUWeight=50`, started after `master-firewall` and only once the container
    guard is in place (an `ExecStartPre` check, retried every 10 s, **DD-223**). Only two folders are
    mounted: the profile `TORRENT_PROFILE_DIR` (the package's `torrent.env`,
    `/var/lib/qbittorrent`, **DD-203**) as `/config`, and `DOWNLOADS_PATH` at the same
    path; the trash and the share root are absent inside. No `no-new-privileges`: the
    image's init then ignores SIGTERM until SIGKILL (settings lost on stop).
  - Its settings are written once, when the profile has none (**DD-178**, **DD-219**):
    save path `DOWNLOADS_PATH`, the WebUI on `TORRENT_UI_PORT` at the container's address
    (`*`; the host publishes it on loopback only) with local authentication, and startup
    legal notice acceptance for the headless service. No UPnP/automatic port-mapping,
    Local Peer Discovery, encryption, anonymous mode, queue, temporary folder,
    preallocation, performance, peer-limit or other user-preference override is seeded
    (DD-218's chosen defaults were reverted). Those follow the installed qBittorrent
    version's defaults until the user changes them. Reapply preserves the entire
    existing profile. `kur` writes only the form's `WebUI\Username`,
    `WebUI\Password_PBKDF2`, the two save-path keys and `WebUI\Address=*` into the new
    or kept profile (and the folder drop-in when the folder is outside the downloads
    tree) before the first start; every other preference of a kept profile stays. A
    failed install restores the profile and the drop-in as they were (**DD-210**).
    Later account and folder changes go through Konsol's qBittorrent page and the
    overview's settings action (§1.10).
  - `kur` checks that the `qbittorrent-nox` process runs as `DOWNLOADS_UID` on the
    host (`podman top … huid`), that no mount is `/`, `SERVER_ROOT`, the trash or the
    share root, that Podman publishes exactly the three expected ports and the interface
    on `127.0.0.1` only, that its API answers
    `403` without a login on `127.0.0.1:TORRENT_UI_PORT` and through
    `torrent.${LOCAL_DOMAIN}`, and that the name resolves; a failed install is taken
    back. An active old Debian `qbittorrent-nox@` unit stops the install with the
    manual step (`systemctl disable --now …`).
  - Names: `torrent.${LOCAL_DOMAIN}` (Caddy site and dnsmasq name); no
    WireGuard publication.
  - Inbound peers (**DD-217**, **DD-219**, **DD-221**): only `WAN_IPV4:TORRENT_PEER_PORT` (63851 unless
    changed in the Podman page) over TCP and UDP is published, and
    the container guard lets only that through to the bridge; nothing is published on
    Tailscale or IPv6.
  - The account is not Konsol's; since **DD-210** it is the install form's. Should no
    password be set, qBittorrent prints a temporary password to
    its journal on each start until one is set in its UI. `hesap torrent`
    reads this run's journal (`_SYSTEMD_INVOCATION_ID`) and prints
    `user<TAB>gecici|ayarli` (with `--parola` also the temporary password);
    `gunluk` masks that line.
  - Its Konsol files (**DD-200**, **DD-202**): `konsol.json`, `sayfa.js`/`sayfa.css`
    (the page) and `api.py` with the worker `ayar.py`
    (`/api/uygulama/torrent/{durum,hesap,dizin,ayar}`; `ayar` is the overview dialog's
    single save of any of username, password and folder with one stop/start, **DD-210**;
    the worker also has `kur-hazirla`/`kur-uygula`/`kur-geri`; the worker edits the profile
    and the quadlet drop-in `90-konsol.conf`, §1.10). Its own settings `torrent.env`
    (`TORRENT_UI_PORT`, `TORRENT_PEER_PORT`, `TORRENT_NETWORK`, `TORRENT_PROFILE_DIR`,
    `TORRENT_CONTAINER`, `TORRENT_IMAGE`, `TORRENT_IMAGE_KANAL`, `TORRENT_SURUM`) and
    `klasorler.py`, which reports the
    folders it writes into beyond the manifest's `PAKET_KLASORLER` (**DD-203**).
  - `durdur` stops the unit and removes the quadlet so it does not start at boot (the
    name stays); `baslat` places it again. `kaldir` removes the names, the page and
    the quadlet and stops the unit but keeps the image; `--veri` also deletes the
    profile (settings and torrent list) — only under `/var/lib` — the folder drop-in
    and the image, never a downloaded file. Konsol's durable choices (the interface
    and peer ports and an approved image, with the port drop-in) stay, so a reinstall matches the
    rendered files without an installer run (**DD-220**).
- Built-in WebDAV (`paylasim`, **DD-158/159**): `yerlesik` runs `master_shares.py
  prepare`. It finishes an interrupted share change, creates the registry only if
  absent, and otherwise rewrites only the derived list of package folders, which
  WebDAV applies at its next start. Then `yerlesik` places/enables the unprivileged
  service, checks UID/anonymous 401, then publishes/checks Caddy and DNS. Unchanged reruns do not rewrite
  accounts or restart healthy services. Remove individual accounts through
  Files; no module verb stops or removes the service.
- The root backend (`master-panel`):
  - `GET /api/konsol/moduller` → `{items: [{id, runtime, installed, state,
    live, busy, progress, durdurulabilir, konsol?, sayfa?, urls?}]}`. `busy` is a running
    `master-modul-<id>.service`, read with `systemctl list-units`; `konsol` is the
    package's rendered `konsol.json` (every catalogued package), `sayfa` the declared
    page files (installed packages only), `urls` its publication addresses (**DD-200**).
  - `/api/uygulama/<id>/*` (any method) → the installed package's API module after the
    same gates; `404`/`409` while the package is absent (**DD-200**). An installed but
    stopped package (`durduruldu`) still answers its own requests, so its settings can be
    read and changed while it stays stopped; for it the module's `start()` is not run and
    background callers (the sampler, VPN networks) do not get it (**DD-210**).
  - `POST /api/konsol/moduller/<id>/(kur|baslat|durdur|kaldir)`, JSON
    body, `{"veri": true}` honoured for `kaldir` only; `kur` of a package with an install
    form needs `{"form": {...}}` (§1.11, **DD-210**). The id
    must be in `liste` (else `404`). It starts `systemd-run
    --unit=master-modul-<id>.service --collect master-modul <verb> <id>` and
    answers `202`; while that unit is active the answer is `409`. The audit
    line is `modul-<verb>`.
  - `GET /api/konsol/moduller/<id>/hesap` → `{user, temp, host}` for an installed
    package with `PAKET_HESAP=1` (the engine's `hesap` line `user<TAB>gecici|ayarli[<TAB>pass]`;
    `host` is the package's publication name); with
    `?parola=1` also the temporary password while one is in use (audited as
    `modul-hesap`). Any other or uninstalled module answers `404`.
  - Folder shares use `GET /api/konsol/paylasim` and `POST
    /api/konsol/paylasim/{kaydet,kaldir}`. The old `.../durum` global-pause
    request is rejected with a refresh message (DD-192, §6).
  - `GET /api/konsol/moduller/<id>/gunluk` → the last 80 log lines as text.
  - The same Host, `X-Konsol` and session gates as every root route apply (**DD-147**, **DD-194**).
- Konsol never retrieves a stored WebDAV password; enter or generate it in the
  folder form. Blank password on edit preserves its hash (DD-158).

---

## 2. Deliberately excluded features

The installer deliberately does not provide these:

- **No reconcile or self-healing engine.** `refresh-tailnet-config` reacts to
  a Tailscale address change and watches only the network edge (§10); there
  is no automatic health probe that restarts services and no reconcile
  `--check` surface. systemd's `Restart=` handles a crash. **A Tailscale
  restart must not restart a module.**
  - **Operator repair (DD-239).** `master-onar` checks and repairs on request only: from Konsol
    (Ayarlar → Sistem → Sağlık, tailnet only, its own unit `ONARIM_UNIT`), over SSH
    (`sudo master-onar`, or `onar.command` on the Mac) or `--denetle` to only report. Fixed steps:
    firewall (`--check`, re-apply), tailscaled (start; a login is never forced), the Tailscale
    address (hands over to `refresh-tailnet-config`), the base units and the running packages'
    units from `master-modul saglik` (restart only units that are not active; a stopped package and
    a network switched off in Konsol are left alone), DNS (`panel.<domain>`, dnsmasq), Konsol through
    Caddy; other failed units are only listed. It never rewrites configuration. The only schedule is
    `master-duvar-denetim.timer` (hourly, `--duvar`: the firewall step).
  - **Wider scope (DD-241).** It also re-applies the installer's own sysctl files when forwarding or
    the network buffers are overridden, restores `--advertise-exit-node --ssh=true`, re-enables the
    installer's timers, restarts SSH (`ssh.service`/`ssh.socket`), the clock sync, `tailscale-udp-gro`,
    and Konsol, Caddy or the Files backend only on the side that does not answer, narrows the modes of
    its private records, cleans apt's cache and shrinks the journal to 200 MB when a disk is below the
    upload reserve (never Konsol's trash or user files) and runs `dpkg --configure -a` when apt is idle.
    It only reports a changed WAN address, an invalid Caddyfile, Podman or its nft table, WireGuard
    peers that never connected, a read-only root, OOM kills, a pending reboot, the node key's expiry,
    a half-finished update and a pending settings change. Its lines go to the journal as `master-onar`;
    Konsol's "Günlük" shows them with `refresh-tailnet-config`'s for 72 hours or a week.
- **No canonical copies or automatic restore.** There is no generation
  directory, `SHA256SUMS` manifest or timer that reverts a managed file. An
  operator edit is the operator's decision; a drifted file is repaired by a
  re-run (**R20**).
- **No restart-cooldown stamp files.** systemd rate-limits restarts with
  `StartLimitIntervalSec`/`StartLimitBurst`.
- **No installer disk or inode threshold checks.** The installer does not
  monitor; Konsol's health card only reports (§1.10, **DD-182**).
- **No installer-stage DNS/Caddy rollback state machine.** A failed stage 6
  leaves dnsmasq and/or Caddy masked, which is safe; recovery is a re-run (§12).
  Later Settings changes use their separate durable transaction (§1.10).
- **No migration cleanup.** The upgrade path is a fresh install or a re-run
  that overwrites what the installer owns. The installer does not hunt for
  earlier revisions' units, users, packages or data; a global `apt-get
  purge` or a `userdel` is outside its boundary (**DD-96**). The narrow
  schema-3 → schema-4 WebDAV registry conversion in §6 is explicitly supported
  by DD-192; schema 2 remains unsupported.

---

## 3. Port publication contract

Three exposure classes, and nothing may straddle them.

### 3.1 Public (WAN IPv4)

The only module WAN port is qBittorrent's peer port (**DD-217**, **DD-219**, superseding
DD-151's outgoing-only rule by the user's choice): `${WAN_IPV4}:63851` (`TORRENT_PEER_PORT`;
the Podman page can change it, **DD-221**) over TCP and UDP, published by its Quadlet into its own bridge and let through by the
container guard on the forward path (not MASTER-INPUT). It is a fixed uncommon port outside
Linux's ephemeral range; nothing else of qBittorrent is published on the WAN.

**Konsol containers (DD-211):** each published port of a generic container has one
scope: `local` (127.0.0.1), `tailscale` (the current Tailscale IPv4) or `public`
(every address, IPv4 only, only after an explicit acknowledgement in the editor).
Tailscale and public publications are admitted on the forward path by the container
guard, from `tailscale0` or the WAN interface respectively, not by MASTER-INPUT.
Nothing is published until the operator saves such a container.

**WireGuard is a host listener (DD-120/143):** each registered network's UDP
port is admitted by the base WAN policy while the application is installed.
`WG_PORT_DEFAULT` (61001, in the package's `wireguard.env`) is only a suggestion
for a new network, not an automatically created listener.

**Host SSH is a separate MASTER-INPUT exception:** inbound TCP
`${SSH_PUBLIC_PORT}` (default 22) on the WAN interface is accepted so
console recovery and public-IP SSH keep working.

**Folder WebDAV is an opt-in WAN exception (DD-179/190):** Caddy binds only
the assigned, globally routable `${WAN_IPV4}`. The saved HTTPS setting determines
the public listener and firewall permission:

| Setting | WAN publication |
|---|---|
| No `https` key | Existing plaintext-consent HTTP on `${SHARE_PORT}` (61010), only while an enabled, unexpired, identity-valid WAN connection exists |
| Nonempty `https.domain` | HTTPS on `${SHARE_HTTPS_PORT}` (443), retained for certificate issuance/renewal even with no active folders, while WebDAV is registered as running and its registry/address are valid |
| Explicit empty `https.domain` | WAN off; no HTTP downgrade and no WAN URL advertised |

For the configured public Host, only `/s/*` reaches the WAN scope on
`SHARE_WAN_BACKEND`; paths outside `/s/*`, including `/api/*`, answer `404`.
Only the WAN HTTPS `servers` block enables
[`strict_sni_host on`](https://caddyserver.com/docs/caddyfile/options#strict_sni_host):
a Host/TLS-SNI mismatch returns `421`, not that site's path-level `404`.
Per-folder authentication/identity and the WAN connection's enabled,
permission and expiry checks remain mandatory (DD-192). The global WebDAV
publication gates in §1.10 take precedence over folder switches. New WAN sockets to the
selected port are capped per source IP and in total before any operator allow
rule; manual denials still apply. In legacy HTTP mode, disabling/removing the last active WAN connection
removes the listener/permission synchronously and expiry does so on the next
`master-share-network.timer` run. HTTPS retains them for renewal, without
publishing any otherwise unauthorized folder. Explicit domain removal closes
new WAN connections through a graceful Caddy reload; existing transfers may
finish. Exact limits and recovery are in [folder-shares.md](folder-shares.md).

**qBittorrent and Konsol HTTPS are opt-in WAN publications on the same port
(DD-191, DD-195):** each has its own public name in Settings → Caddy, shares
`${SHARE_HTTPS_PORT}`, strict SNI and the per-source/total socket budgets above,
and keeps `${SHARE_HTTPS_PORT}` admitted while active even when WebDAV's WAN is
off. Konsol's public site requires an existing Konsol account and keeps every
session, Host, CSRF and channel check (§1.9). The root backend socket, the Files
loopback port and Caddy's admin socket are never published themselves.

The firewall limits NEW WAN traffic to each WireGuard network's UDP port
(IPv4 only), host SSH, Tailscale's own UDP port (`TAILSCALE_UDP_PORT`) and the
mode-selected WebDAV TCP port above (IPv4 only). Public HTTPS permits only
HTTP/1.1 and HTTP/2 (`protocols h1 h2`); no HTTP/3, UDP 443 listener/permission
or WAN TCP 80 is added. No NAT discovery, provider forwarding or DNS API write
is performed.

### 3.2 Tailnet (Tailscale IPv4) — reachable only over `tailscale0`

| Service | Listen address | Port | Protocol |
|---|---|---|---|
| Caddy | `${TAILSCALE_IPV4}` | 80 and `${SHARE_PORT}` (61010, folder WebDAV) | TCP, HTTP only |
| dnsmasq | `${TAILSCALE_IPV4}` (via `bind-dynamic`) | 53 | UDP + TCP |

dnsmasq also listens on `127.0.0.1:53` (**DD-60**), so the host itself can
resolve the service names and the installation can verify DNS without
bringing a tailnet device into the loop. Those two interfaces — `lo` and
`tailscale0` — are the only ones it binds. No WAN interface, no ordinary
LAN interface, no unbounded `0.0.0.0` listener, and no DHCP service.

### 3.3 Loopback only

| Service | Listen address | Port |
|---|---|---|
| qBittorrent WebUI (`torrent` module; only while installed) | `127.0.0.1` | 62947 by default; the Podman page can change it (**DD-127**, **DD-151**, **DD-214**, **DD-219**) |
| Konsol root backend (`master-panel`; package API modules inside it, **DD-200**) | Unix socket `/run/master-panel/api.sock` (`0660 root:caddy`) | none (**DD-133**, **DD-140**, **DD-180**) |
| Caddy admin API | Unix socket `/run/caddy/admin.sock` (folder `0700 caddy`) | none; `systemctl reload caddy` uses it (**DD-180**) |
| Konsol file/archive backend (`master-files-panel`; built in) | `127.0.0.1` | 61009 (**DD-159**) |
| Per-folder WebDAV (`paylasim` internal ID; built in) | `127.0.0.1` (Tailscale scope) and `SHARE_WAN_BACKEND` `127.0.0.2` (WAN scope) | 61010 (**DD-158**, **DD-159**, **DD-179**) |

Reached from the tailnet through Caddy (**R11**, **R16**, **DD-98**):
the share WebDAV on `paylas.*:80` and `${TAILSCALE_IPV4}:${SHARE_PORT}`. No
loopback service names the Tailscale address. None of them listens on
`0.0.0.0` or a WAN address; the stack-owned WAN TCP listeners are Caddy's
opt-in WAN sites, qBittorrent's published peer port and public-scope ports of
Konsol containers (§3.1).

### 3.4 Single source of truth

The base's numbers above are declared exactly once, in `config/defaults.env`; a
package's numbers (qBittorrent's 62947 and 63851, WireGuard's 61001 suggestion)
once in its own `magaza/<id>/<id>.env` (**DD-203**). Konsol may keep a durable
override only for the keys a package allows (`PAKET_AYAR_ANAHTARLAR` in
`PACKAGE_OVERRIDES_DIR`, **DD-214**, **DD-220**, **DD-221**). Values reach the module
templates, the Caddyfile, the firewall script and the state file by
substitution. A port literal appearing twice is a bug.

### 3.5 WireGuard (`wgN`) — internet-only

No host service is exposed to WireGuard clients. Each registered network's UDP
transport endpoint remains admitted on WAN/Tailscale while the module is installed.
This transport permission does not grant tunnel clients access to the host.

---

## 4. DNS and Caddy service map

`${LOCAL_DOMAIN}` has no default: a first install asks for it on the server terminal
in stage 0 (**R13**, **DD-228**). Re-runs keep the previous install's name without
asking; a domain confirmed in Konsol (`SETTINGS_FILE.domain`) takes precedence
(**DD-157**), and Konsol → Ayarlar is where it changes.

| Name | dnsmasq answer | Caddy site | Upstream |
|---|---|---|---|
| `torrent.${LOCAL_DOMAIN}` (qBittorrent module only) | `${TAILSCALE_IPV4}` | `http://torrent.…` | `127.0.0.1:62947` (**DD-117**, **DD-151**, **DD-219**) |
| `paylas.${LOCAL_DOMAIN}` (built-in folder sharing) | `${TAILSCALE_IPV4}` | `http://paylas.…/s/<id>/` and `http://${TAILSCALE_IPV4}:61010/s/<id>/` | `127.0.0.1:61010` (**DD-158**, **DD-159**) |
| Public WebDAV domain (optional, separate from `LOCAL_DOMAIN`) | Not a private dnsmasq record; public DNS must resolve only to `${WAN_IPV4}` | `https://<public-domain>/s/<id>/`, bound to `${WAN_IPV4}:${SHARE_HTTPS_PORT}`; legacy HTTP/off modes in §3.1 (**DD-190**) | `SHARE_WAN_BACKEND:61010` |
| `panel.${LOCAL_DOMAIN}` (Konsol) | `${TAILSCALE_IPV4}` | `http://panel.…` (`import konsol tailscale`) | page files from `CONSOLE_WEB_DIR` (installed packages' pages under `uygulama/<id>/`); `/api/konsol/*` and `/api/uygulama/*` → Unix socket `PANEL_SOCKET` (`/run/master-panel/api.sock`, **DD-180**), other `/api/*` → `127.0.0.1:61009` (**DD-140**) |
| `<local>.${LOCAL_DOMAIN}` (manual address, **DD-252**) | `${TAILSCALE_IPV4}` (`modul-elle.conf`) | `http://<local>.…` (`moduller/elle-<local>.caddy`) | `127.0.0.1:<port>` the operator entered |
| Public name of a manual address (optional, **DD-252**) | Not a private dnsmasq record; public DNS must resolve only to `${WAN_IPV4}` | `https://<public-domain>`, bound to `${WAN_IPV4}:${SHARE_HTTPS_PORT}` (`moduller/elle-<local>-wan.caddy`) | the same loopback port |
| Public Konsol domain (optional, **DD-195**) | Not a private dnsmasq record; public DNS must resolve only to `${WAN_IPV4}` | `https://<public-domain>`, bound to `${WAN_IPV4}:${SHARE_HTTPS_PORT}` (`import konsol internet`) | the same routes as `panel.${LOCAL_DOMAIN}`, with backend Host `panel.${LOCAL_DOMAIN}` |

`SERVICE_NAMES` is `panel`.

Rules:

- dnsmasq answers locally for `${LOCAL_DOMAIN}`. Other queries are `REFUSED`
  by default; optional public upstream forwarding is configured in Ayarlar
  (**DD-156**). Private-domain misses/disabled names never go upstream.
- dnsmasq listens on `lo` and `tailscale0`, with `bind-dynamic`, and on
  nothing else (**DD-60**).
- **The current Tailscale IPv4 is never written into the dnsmasq
  configuration.** Records are interface-based (`interface-name=…,tailscale0`),
  which resolves to whatever address the interface currently holds, so
  tearing down and recreating `tailscale0` needs nothing regenerated.
- **Acceptance test:** a query arriving over loopback must answer
  `${TAILSCALE_IPV4}` — not `127.0.0.1` or `NXDOMAIN`. Stage 7 measures
  `dig +short … @127.0.0.1` and `@${TAILSCALE_IPV4}` for every name in
  `SERVICE_NAMES`; both must return `${TAILSCALE_IPV4}`.
- Private Caddy sites remain explicitly `http://`; Tailscale is their transport
  security boundary. Only the optional public WebDAV domain uses HTTPS/ACME
  (**DD-190**): Let's Encrypt via TLS-ALPN on TCP 443, HTTP challenge disabled,
  `auto_https disable_redirects`, no WAN port-80 listener or DNS API token.
- Every upstream is plain HTTP on loopback or the root backend's Unix socket.
- The base names live in one list (`SERVICE_NAMES`) mirrored in both templates;
  adding a service means editing that list and both templates. A module's
  names live in its own files and come and go with it (**DD-149**).

---

## 5. Folder WebDAV: purpose (DD-158/DD-192)

Selected folders, not a shared symlink root, are published through independent
accounts and stable `/s/<id>/` URLs. Each folder has independent `tailscale`
and `wan` policies for enabled state, RO/RW and absolute expiry. Both connections
use the same folder, ID, username and password; either or both may be disabled.
New shares default to Tailscale enabled, RO, seven days, and WAN disabled, RO,
seven days. RW includes permanent deletion/overwrite and requires explicit
acknowledgement for that connection. Enabling or re-enabling WAN in legacy
HTTP mode requires `ack_wan_http: true`; HTTPS needs no plaintext acknowledgement.
The listener scope, not a request header, chooses the applicable policy; each
scope has its own attempt limits and connection budget (§3.1). Global Caddy
publication gates can restrict access but cannot widen a folder policy.
The binding implementation details are in [folder-shares.md](folder-shares.md).

## 6. WebDAV credentials and permissions (DD-158/DD-192)

`SHARE_STATE_FILE` is a 0600 root-owned schema-4 JSON registry. Each item has
exactly two connection policies, `connections.tailscale` and `connections.wan`,
each with `{enabled: bool, permission: "ro"|"rw", expires: Unix-seconds|null}`.
`null` means unlimited. There is no authoritative shared `permission`, `expires`,
`paused` or `networks` field; schema-4 items containing any of those legacy fields
are rejected as conflicting, even if their values appear to agree.

Loading schema 3 validates and converts it in memory without writing the file:
both policies copy the exact shared permission and absolute expiry, including
expired values and `null`; each is enabled only if its network was selected and
the share was not paused. IDs, paths, names, usernames, salts/hashes, folder
identity, `created` and `changed` are preserved. No account is rotated and no
expiry is renewed. `prepare` persists schema 4; subsequent unchanged preparation
is a no-op. Schema 2 and other unsupported/malformed registries fail closed.

`POST /api/konsol/paylasim/kaydet` accepts nested partial `connections` with
one or both scopes. Each supplied scope patch accepts only
`{enabled?, permission?, days?, ack_write?}`. `enabled` is boolean,
`permission` is `ro` or `rw`, and `days` is integer `0`, `1`, `7` or `30`:
zero stores `null`; other values start that scope's duration at save time.
Omitted scopes and fields, including absolute expiry, are read from the current
registry under install/module/share locks and preserved. Switching on never
renews an expired connection. Every explicit `permission: "rw"` requires
`ack_write: true` in the same scope patch, even for an existing RW grant or an
off connection; unrelated edits preserving RW need no new acknowledgement.
Both connections off is valid and retains the account. Folder/path, username
and password are managed separately; blank or omitted password on edit preserves
the hash, and an omitted path never rebinds the folder identity.

Old shared-policy save fields (`permission`, `days`, `expires`, `networks`,
`paused`, top-level `ack_write`) and the old `POST .../durum`/`pause` operation
are rejected without applying a change, with a message asking to refresh the
page. They are never translated into updates to both policies.

`GET /api/konsol/paylasim` projects non-secret rows. Each `row.connections[scope]`
contains its saved policy plus `expired`, `available`, `active`, `reason` and
`url`. Connection `available` describes the global publication/transport gate;
row-level `available` describes the folder identity. `active` additionally
requires the connection enabled, unexpired, the folder valid and the WebDAV
service registered as running. `reason` explains denial, including global Caddy
gates. `url` is a candidate address when the transport is available, even with
the connection off or expired; it is empty when the global gate/transport is
unavailable. `row.urls` contains only active connections (`row.url` selects the
first active address). A candidate address is not proof of access or reachability.

No plaintext password copy exists. Fixed workers receive mutations on stdin
under the existing panel gates and operation locks. The unprivileged data service
receives a `LoadCredential` copy at start. No password enters argv, logs,
environment files or browser storage; salts/hashes and filesystem identity are
not returned to the browser.

Each request authenticates against exactly one share and enforces the trusted
listener's policy, including after an authentication-cache hit. `PUT`, `MKCOL`,
`DELETE`, `MOVE` and file `COPY` all require RW on that listener; Tailscale RW
never grants WAN write access, or vice versa. Enabled/expiry checks apply to
requests and live transfer chunks, with permission checks on writes. Staged
PUT/COPY revalidate that policy and the filesystem/preconditions under the
mutation lock before atomic publication. Directory descriptors, nofollow and
birth-time/inode checks enforce the root. Share edits restart the active data
service and interrupt **all** transfers; stopped services stay stopped. Remove
revokes both connections and their account, never shared files. Root administrators
and the Konsol administrator account remain outside this isolation boundary.

## 7. WebDAV service lifecycle (DD-158)

master-paylasim.service runs master_webdav.py as DOWNLOADS_UID/GID on loopback
(127.0.0.1 for the Tailscale scope, SHARE_WAN_BACKEND for the WAN scope),
with no capabilities, system paths read-only, user area writable, internal
trash/share paths, the archive staging area and `PRIVATE_STATE_ROOT` inaccessible
(**DD-225**), and network restricted to loopback. Caddy
publishes the `paylas.` name and Tailscale IP:SHARE_PORT over HTTP. The optional
WAN site follows §3.1: legacy HTTP on SHARE_PORT, HTTPS on SHARE_HTTPS_PORT or
off (DD-179/190). HTTPS stays available for renewal with zero active folders;
folder authorization still fails closed. No Tailscale policy change.

The installer prepares an empty registry only when absent and enables this
built-in service; on a rerun it refreshes only the derived package-folder list,
which WebDAV applies at its next start. Reruns preserve accounts; public module
removal is refused.
Address refresh changes Caddy, not WebDAV. No route broader than `/s/<id>/`
exists.

The supported DAV subset, filesystem and concurrency limits and test
commands are specified in [folder-shares.md](folder-shares.md). Finder/Infuse
and recipient ACL reachability need separate operator acceptance.

---

## 8. Host firewall contract (`INPUT`)

Base policy (confirmed panel overrides are applied by `MASTER-SETTINGS` before
Tailscale acceptance; WG host ingress is dropped first in both project chains):

0. Drop all WG host ingress before any established, ICMPv6 or Tailscale accept.

1. Loopback (`lo`) traffic.
2. `ESTABLISHED,RELATED` connections — this is what keeps the operator's
   **currently active SSH session alive** while the policy is installed.
3. Inbound traffic arriving on `tailscale0` only for SSH, Caddy, DNS TCP/UDP,
   folder WebDAV, self-advertised Tailscale PeerAPI TCP and registered WireGuard
   UDP endpoints, subject to confirmed overrides (**DD-172**). Other new tailnet
   host connections are dropped in `MASTER-SETTINGS` before `ts-input` can accept
   them. Listener binding and firewall permission remain separate facts.
   The Tailscale port catalogue comes from this per-family allowlist and the WG
   registry, not arbitrary host sockets; explicit user rules remain manageable.
   Raw listeners and technical rules stay unfiltered (**DD-173**).
4. New inbound TCP on the WAN interface to `${SSH_PUBLIC_PORT}` (host sshd).
5. New inbound UDP for Tailscale and each registered WireGuard network.
6. New DNS (TCP/UDP 53) from a Konsol container bridge (`ksl*`) to that bridge's
   own address, for Aardvark's container name service (**DD-211**); no other host
   address or service is reachable from a bridge.
7. When the WAN projection in §3.1 is enabled (**DD-179/190**), or a
   qBittorrent/Konsol HTTPS publication is active (**DD-191/195**): new inbound
   IPv4 TCP on the WAN interface to the selected `${SHARE_PORT}` or
   `${SHARE_HTTPS_PORT}`, after the per-source and total
   connection-limit rejects that `MASTER-SETTINGS` places before operator rules.

Dropped:

8. Every other new inbound connection arriving on the WAN interface, and any
   new tailnet host service connection outside the allowlist/explicit overrides.

Rules:

- The policy is applied through a staging chain and swapped in atomically,
  so there is no moment at which SSH is unreachable. At the **end** of a
  successful apply every leftover staging chain is removed together with its
  parent jump, including one left referenced by an interrupted earlier run
  (**DD-95**).
- Boot exposes a measured ~850 ms window between the WAN address becoming
  usable and the policy landing; sshd, which the policy allows anyway, was
  the only WAN listener in it when measured. Rules
  are not persisted to disk (**DD-66**), so this window is accepted, not
  closed (**DD-95**).
- Established/related acceptance precedes the default WAN drop.
- The WAN interface is the **live default route at apply time**, not the
  `WAN_INTERFACE` recorded in `state.env`. A renamed NIC produces a warning
  and a correct policy, never a failed unit with no policy at all
  (**DD-94**).
- There is no **default** WAN permission for WebDAV, Caddy, dnsmasq or an
  application web interface; WAN WebDAV and optional qBittorrent and Konsol
  HTTPS are conditional publications (DD-191, DD-195). Explicit HTTPS retains its renewal port without active
  folders, but never removes per-folder opt-in/authentication.
  Custom firewall allows do not change socket binds.
- The Internet port catalogue lists only configured per-family base permits;
  local/tailnet sockets do not create closed WAN placeholders. WireGuard lists
  the fixed internet-only policy with no editable host port. Explicit WAN/tailnet
  rules, required VPN endpoints and technical diagnostics remain visible; these
  lists do not discard requirements based on activity or peer count (**DD-174**).
- IPv6 `INPUT` follows the same shape and is equally fail-closed. Tailscale
  IPv6 traffic uses the service allowlist except Caddy/WebDAV (their templates
  bind IPv4 only); WAN IPv6 allows NDP/ICMPv6 essentials, host
  SSH TCP and Tailscale UDP, and drops other NEW WAN traffic, including the
  WebDAV share port.
- Both policies finish with an unconditional DROP for otherwise unhandled
  interfaces (**DD-187**). On registry-validation failure an apply keeps the
  existing owned default-deny policy; a cold family receives a narrow rescue
  guard (SSH/Tailscale transport, established/loopback/IPv6 control only).
  This is still a failed firewall, not a successful degraded configuration:
  Caddy/WireGuard pre-start checks remain closed. `--check` is read-only.

---

## 9. Forwarding firewall contract (WireGuard)

This section covers the WireGuard forwarding and NAT policy and the shape
check shared with §8.

**Chain names are fixed** (**DD-59**): `MASTER-INPUT` for the host policy,
`MASTER-FORWARD` and `MASTER-NAT` for WireGuard (**DD-120**).
`MASTER-SETTINGS` owns confirmed panel overrides, followed by the core tailnet
allowlist/default drop, before the `ts-input` jump (**DD-156**, **DD-172**);
`MASTER-INPUT` remains behind it. User-created WireGuard endpoint ports remain
requirements regardless of current peer count or recent activity.
The same logical
names serve IPv4 and IPv6 — separate tables mean no collision — and all are
declared in `config/defaults.env` and nowhere else.

- The installer creates **only its own chains** and inserts **one
  idempotent jump** to each (`INPUT` → `MASTER-INPUT` behind `ts-input`,
  `FORWARD` → `MASTER-FORWARD`, `nat POSTROUTING` → `MASTER-NAT`; the latter
  two exist only while the installed WireGuard module has registered networks).
- tailscaled's own chains (`ts-input`, `ts-forward`) are **never** flushed or
  deleted; the firewall only orders `MASTER-INPUT` behind the `ts-input`
  jump (re-adding that jump when it is missing), which is why the
  nft-backend gate stays (§1.1).
- **Third-party rules already present in `INPUT`, `FORWARD` and
  `POSTROUTING` are never deleted**: the installer adds its jumps and leaves
  everything else in place.
- WireGuard (**DD-120/143/150**), for registered networks while installed:
  - `MASTER-SETTINGS` and `MASTER-INPUT` drop all WG ingress first.
    WG-scoped user rules are refused; no user rule can bypass the mandatory
    policy.
  - `MASTER-FORWARD` first drops destinations in `VPN_BLOCK_DEST4/6`
    (private, CGNAT, loopback, link-local, multicast/reserved and standard NAT64
    prefixes), then accepts `wgN` → WAN. Other WG ingress is dropped.
    Only established/related replies arriving from WAN can reach WG; all other
    traffic toward WG is dropped. Prefix lists have one owner: defaults.env.
  - `MASTER-NAT`, in `nat POSTROUTING`, masquerades the WireGuard subnets out
    of the WAN.
  - wg-quick carries no `PostUp`: every rule belongs to `master-firewall`.
- IPv6 policy is explicit and fail-closed; it is generated even without an
  IPv6 WAN route. Missing IPv6 connectivity never switches off its protection.
- The helper refuses to run if `ip6tables` is unavailable while IPv6
  forwarding is enabled, rather than degrading to an IPv4-only policy.
- The policy lives only in memory; `master-firewall.service` re-applies it
  after boot and after a `tailscaled` restart (`PartOf=tailscaled.service`
  only, **DD-152**).
- `master-firewall --check` verifies **shape and cardinality, not just
  presence**: each parent holds exactly one jump to its chain; in
  `MASTER-INPUT` (both families) there must be exactly one
  WAN DROP, it must follow every WAN allow, no unconditional
  `ACCEPT`/`RETURN` may precede it (**DD-94**), and the number of WAN allows
  must equal the allow list exactly — for IPv4 Tailscale's UDP port, host
  SSH, the conditional WebDAV TCP port from §3.1 and one UDP port per
  WireGuard network (none without the module), for IPv6 the first two. `MASTER-FORWARD` must hold four base rules plus the configured blocked-prefix rules per
  network, `MASTER-NAT` one per subnet, and INPUT's entire rule count and
  all IPv6 control types are checked. No managed chain emits a redundant
  terminal `RETURN`; intermediate settings returns remain essential. Any extra WAN pass, whether a blanket
  `-i eth0 -j ACCEPT` or one more port, fails the check (**DD-95**).
- **DD-175:** absent/empty/non-running WireGuard module registration never
  activates a retained network file. With no configured active-module networks,
  `MASTER-FORWARD`/`MASTER-NAT` and their jumps are absent, not empty placeholders.
  Removing the final network/module removes only these project-owned chains;
  adding a network recreates them. Interface state/peer count never decides
  whether a registered network's required endpoint or policy is kept.

---

## 10. systemd lifecycle

| Unit | After | Coupling | Restart |
|---|---|---|---|
| `tailscale-udp-gro.service` | `network-online.target` | none | `no`, oneshot, `RemainAfterExit` |
| `master-firewall.service` | `network-online.target tailscaled.service` | `PartOf=tailscaled.service` only (**DD-152**) | `on-failure` (oneshot, `RemainAfterExit`, `RestartSec=10s`, `StartLimitBurst=12` / 300s) |
| `refresh-tailnet-config.timer` | — | address refresh + firewall watchdog (checked again once Tailscale answers); resets a failed Caddy's start limit before restarting it; reopens failed WireGuard networks (**DD-180**, **DD-182**); hands a recorded Tailscale address change to the bounded container worker (**DD-211**) | once after boot (`OnBootSec=2min`) and nightly between 03:00 and 04:00 (`OnCalendar` + `RandomizedDelaySec=55min`); otherwise Caddy's `OnFailure` and `master-onar` (**DD-239**, **DD-240**) |
| `master-duvar-denetim.timer` | — | `master-onar --duvar`: re-applies the owned firewall rules when `master-firewall --check` fails (**DD-239**) | hourly (`OnBootSec=10min`, `OnUnitActiveSec=1h`) |
| `caddy.service` (drop-in) | `tailscaled.service master-firewall.service` | `Wants=` both (no `PartOf`); `ExecStartPre=+master-firewall --check` (**DD-179**); `OnFailure=refresh-tailnet-config.service` (**DD-87**) | `on-failure` + StartLimit (drop-in) |
| `dnsmasq.service` (drop-in) | `tailscaled.service` | `Wants=tailscaled.service` | `on-failure`, `RestartSec=5s` (drop-in) |
| `master-panel.service` (Konsol root backend) | `network-online.target` | none; Unix socket only (**DD-180**) | `on-failure`, `RestartSec=3s` |
| `master-files-panel.service` (built in) | `network-online.target` | none; `127.0.0.1` listener, `RequiresMountsFor=SERVER_ROOT`, always enabled by `master-modul yerlesik` | `on-failure`, `RestartSec=3s` |
| `master-sistem-dosya.service` (Files' "Sistem (/)", root, **DD-235**) | `network-online.target` | none; Unix socket only, enabled by the installer | `on-failure`, `RestartSec=3s` |
| `master-paylasim.service` (built-in WebDAV) | `network-online.target` | none; `127.0.0.1` and `SHARE_WAN_BACKEND` listeners, `RequiresMountsFor=SERVER_ROOT` (**DD-225**), always enabled by `master-modul yerlesik` | `on-failure`, `RestartSec=3s` |
| `master-share-network.timer` | — | closes expired legacy HTTP WAN projections, retains configured HTTPS for renewal and recovers interrupted share operations (**DD-179/190**) | starts oneshot 30 s after boot and 30 s after each run |
| `master-settings-guard.timer` | — | rollback deadline of an unconfirmed Settings change; active only while one is pending (**DD-181**) | starts oneshot every 2 s while active; once 15 s after boot |
| `apt-daily-upgrade.timer` (drop-in, **DD-184**) | — | distribution unit; `OnCalendar` at `APT_UPGRADE_TIME` (04:00), `RandomizedDelaySec=30m`, the distribution's `Persistent=true` kept | daily |
| `wg-quick@wgN.service` (drop-in, **DD-180**) | `master-firewall.service` | `Wants=`; `ExecStartPre=+master-firewall --check`, so a network never forwards without the owned rules | package default; a network left failed is reopened by `refresh-tailnet-config` once the check passes |
| `<PAKET_KONTEYNER>.service` (App Store container, e.g. `qbittorrent.service`; Quadlet) | `network-online.target master-firewall.service` | `Wants=` both, no `Requires=`/`PartOf=`; `ExecStartPre` checks (never writes) the container guard, so it never starts unguarded (**DD-223**) | `on-failure`, `RestartSec=10s`: retried until the guard is in place |
| `konsol-<ad>.service` (Konsol container; Quadlet) | `network-online.target master-firewall.service` | `Wants=` both, no `Requires=`, so a firewall restart leaves it running; the same guard check unless it has no network (**DD-211**, **DD-223**) | the operator's choice; `RestartSec=10s` |

The Caddy drop-in also carries
`EnvironmentFile=/etc/master-stack/state.env`, which is how
`{$TAILSCALE_IPV4}` in the Caddyfile is resolved at daemon start. There is
no separately rendered environment file (**DD-61**), so `state.env` must be
written in a form both bash and systemd can parse: plain `KEY=value`,
no spaces around `=`; whitespace-separated prefix lists use double quotes
with no shell expansion. `ExecStartPre=wait-tailnet-addr` requires
that address on `tailscale0` (**DD-85**).

Invariants:

- **Restarting `tailscaled` re-applies the firewall
  (`master-firewall` is `PartOf=tailscaled.service`) and leaves every module
  and container running** (**DD-223**). Caddy is restarted when `refresh-tailnet-config` sees an
  address change, when Caddy fails and `OnFailure=` starts that oneshot
  (**DD-87**), or when the operator restarts it. The share WebDAV is a host
  service with no tie to `tailscaled`.
- **The firewall unit orders itself only after `network-online.target` and
  `tailscaled.service`.** Host `INPUT` must land as early as possible
  (**DD-94**).
- **One bounded watchdog, at the network edge only.**
  `refresh-tailnet-config` (after boot, nightly and on demand) and the hourly `master-duvar-denetim` restart
  `master-firewall` when the unit is `failed` or `--check` fails, after a
  `reset-failed` so an exhausted start limit cannot block the recovery. It
  skips the round while the oneshot is mid-apply. Beyond the firewall it only
  restarts a failed Caddy, reopens failed enabled WireGuard networks
  (**DD-180**, **DD-182**) and, after a recorded Tailscale address change, starts
  the bounded `master-container-tailnet-refresh` worker (`RuntimeMaxSec=900`), which
  recreates only Konsol containers whose Tailscale bindings changed (**DD-211**): no
  module, file, or binary is reconciled (**DD-94**).
- **No general-purpose repair engine.** The only `OnFailure=` in the stack
  is Caddy → `refresh-tailnet-config` (same oneshot the timer /
  `WantedBy=tailscaled` already use). There is no reconcile loop that
  reverts files or restarts arbitrary units.
- Module services come back after a reboot as enabled units; a module
  registered `durduruldu` stays disabled.

---

## 11. Idempotency expectations

**R20**: a second run against an already-provisioned host must be safe.

- Every managed file is rendered from a template and written through a
  temporary file plus atomic rename, with explicit owner and mode.
- Re-running must not change a single byte of any generated file when the
  inputs are unchanged. This is verifiable: `sha256sum` the generated set
  before and after a second run.
- Existing state that must survive a re-run: the folder share registry
  (IDs, hashes and both connection policies), qBittorrent's profile (its settings are
  written once, by the module, **DD-151**),
  every `wgN.conf` and `clients-wgN/` with the networks registry (keys and
  device profiles are never rewritten), the operator's chosen local domain
  and public HTTPS setting (including explicit WAN-off).
- Firewall application is idempotent by construction: each chain is rebuilt
  from scratch and swapped in, and each parent jump is inserted only when
  absent.
- Directory creation is conditional; ownership/mode repair under downloads
  is selective (mismatched UID/GID/mode only — **DD-84**), not a full-tree
  rewrite and not limited to newly created directories.
- No step is unconditionally expensive: package installation and daemon
  restarts happen only when something actually
  changed.
- A re-run asks only the one confirmation (the domain is kept);
  `full-upgrade` always runs (**DD-228**).
  Folder WebDAV code is part of the installer (§7).

---

## 12. Fail-closed behaviour on error

The rule: **a failure must never leave the host more exposed than before
the run started.**

| Failure point | Behaviour |
|---|---|
| Any stage aborts | The installer exits non-zero with the failing stage and line, and the log path |
| Firewall application fails partway | The staging chain is discarded; the previously active policy stays in force. A host that cannot get a complete policy does not get a partial one |
| `ip6tables` missing while IPv6 forwarding is on | Hard failure. No IPv4-only degradation |
| dnsmasq installed but not yet configured | The unit is **masked** during the window between package installation and configuration, so it cannot start as an open resolver on `0.0.0.0:53` |
| Caddy installed but not yet configured | Same masking window |
| Stage 6 aborts midway | dnsmasq and/or Caddy remain masked — i.e. **off**. There is no rollback machinery; recovery is a re-run |
| Tailscale never comes online | Hard failure before anything is published. The stack is not started against a missing address |
| WebDAV registry preparation (`master_shares.py prepare`) fails | `master-modul yerlesik` stops before the service is started; systemd also refuses a unit whose credential file (the registry) is missing |
| Folder account service renewal fails | Previous registry is restored and restart retried; if recovery also fails, report it explicitly. No plaintext password is returned (**DD-158**) |
| Public HTTPS apply fails or crashes before commit | Restore the previous saved projection using durable Settings pending/guard recovery; report incomplete rollback. An initial failed enablement may restore the previously consented HTTP mode, but a committed HTTPS configuration never silently falls back to HTTP on certificate failure (**DD-190**) |
| A module's Caddy site or dnsmasq name does not validate | The previous file is put back and a `kur` is taken back (§1.11) |
| A generated file cannot be written with the intended owner/mode | Hard failure, temporary file removed |

Nothing is repaired silently. Nothing is retried indefinitely: every wait
has a wall-clock deadline and reports which deadline it hit.

---

## 13. Manual Tailscale admin steps (R17)

The installer prints these and cannot perform them; they live in the
Tailscale control plane, not on the host.

1. **DNS → Nameservers → Add nameserver → Custom**
   - Nameserver IP: the Tailscale IPv4 printed at the end of the run.
2. **Restrict to domain** — enable it, and enter `${LOCAL_DOMAIN}`.
   Without this the tailnet sends *all* DNS to this host, which will answer
   `REFUSED` for everything outside `${LOCAL_DOMAIN}` unless upstream
   forwarding was explicitly enabled in Ayarlar.
3. **Machines → this host → Review exit-node route → Approve.** An
   advertised exit node is not usable until it is approved.
4. **Machines → this host → key expiry** — decide whether to disable it for
   an always-on server.

Note printed alongside: dnsmasq and Caddy follow the current `tailscale0`
address automatically, so if the device is deleted and re-registered, the
only thing that needs updating is the nameserver IP in step 1.

---

## 14. Success criteria

An installer run is successful when every one of these holds on the target host.

### Base and Tailscale

1. `tailscale status --json` reports `BackendState=Running` and
   `Self.Online=true`.
2. `tailscale debug prefs` shows exit-node advertisement for `0.0.0.0/0`
   and `::/0`, `RunSSH=true`, stateful filtering on, netfilter mode 2.
3. `net.ipv4.ip_forward` and `net.ipv6.conf.all.forwarding` are `1`.
4. `state.env` contains a valid `TAILSCALE_IPV4` **and** `TAILSCALE_IPV6`.

### Ports

5. No application web service gets a default WAN listener. A clean install
   creates no WireGuard network. With WireGuard installed, each active network
   matches the registry's address/port, `master-wg version` runs, and all
   networks are internet-only with no WG service listener.
6. No module web interface listens on a non-loopback address.
7. The loopback services of §3.3 (Konsol file backend, built-in WebDAV and the
   installed qBittorrent UI) listen on loopback only (`127.0.0.1`; WebDAV
   also on `SHARE_WAN_BACKEND`). The root backend and Caddy's admin API have no TCP port; stage 7 checks
   the socket modes, that the downloads account cannot connect to either, that
   `127.0.0.1:2019` is closed and that `systemctl reload caddy` still works (**DD-180**).
8. Main Caddy listens on `${TAILSCALE_IPV4}:80` and
   `${TAILSCALE_IPV4}:${SHARE_PORT}` (Infuse). WAN publication follows §3.1:
   active-folder legacy HTTP, configured HTTPS retained for renewal, or off;
   no WG web listener exists.
9. dnsmasq answers on `${TAILSCALE_IPV4}:53` **and** `127.0.0.1:53`, and on no
   other address; it serves no DHCP.

### DNS and Caddy

10. Enabled base/installed-module names resolve to `${TAILSCALE_IPV4}` when queried
    against `${TAILSCALE_IPV4}`; `health.` is not a built-in name.
11. A query for an out-of-domain name against `${TAILSCALE_IPV4}` returns
    `REFUSED` by default (or resolves via configured upstreams when enabled).
12. `curl -H "Host: panel.${LOCAL_DOMAIN}" http://${TAILSCALE_IPV4}/` returns
    the Konsol page, HTTP 200; both installed API backends pass their checks.
13. Backend API gates reject missing `X-Konsol` and unrelated Host headers.
    With the qBittorrent module installed, `master-modul kur torrent` checks
    that `/api/v2/app/version` answers `403` without a login on loopback and
    through `torrent.${LOCAL_DOMAIN}`; a `200` means a localhost or subnet
    authentication bypass is on (**DD-127**, **DD-151**).
14. WebDAV listens only on loopback as DOWNLOADS_UID; Caddy owns the tailnet
    port and the optional mode-selected WAN listener (§3.1).
15. Anonymous requests return 401; each account opens only its selected folder.
16. PROPFIND/read/range succeed; RO write methods are rejected.
17. RW changes stay inside the share; cross-share Destination and unsafe paths fail.
18. Each connection's disable/expiry revokes that scope independently; password
    rotation and removal affect both, as specified in §6. Cached authentication
    and staged uploads cannot bypass the applicable policy.
19. URLs include /s/<id>/; native-client acceptance is a separate test.

### WebDAV credential handling (§6)

20. SHARE_STATE_FILE remains 0600 root, with hashes only.
21. No secret enters environment files, argv, browser storage or audit logs.
22. The service command line contains only the credential path.
23. Reruns and reboot preserve IDs, hashes and both connection policies;
    schema-3 preparation persists the lossless schema-4 conversion in §6.

### Firewall

24. The base policy accepts loopback, `ESTABLISHED,RELATED`, Tailscale,
    WAN SSH/Tailscale UDP, registered WireGuard UDP ports and the conditional
    WAN IPv4 WebDAV TCP port of §3.1; other NEW WAN
    input is dropped. Confirmed `MASTER-SETTINGS` overrides are tested separately.
25. `INPUT` holds exactly one jump to `MASTER-INPUT`, behind `ts-input`;
    `FORWARD` exactly one to `MASTER-FORWARD` and `nat POSTROUTING` exactly
    one to `MASTER-NAT`, in both families, while WireGuard networks are
    registered (§9). `MASTER-SETTINGS` has its own single jump before `ts-input`.
26. A third-party rule planted in `INPUT` or `FORWARD` before the run is
    still present after it.
27. tailscaled's own chains (`ts-input`, `ts-forward`) are not flushed or
    deleted.
28. `MASTER-FORWARD` permits no NEW WAN traffic into a WireGuard network.
29. The active SSH session survives policy application.

### Lifecycle

30. `systemctl restart tailscaled` leaves every installed module running.
31. `systemctl restart tailscaled` also results in a re-applied firewall
    policy, `MASTER-INPUT` behind `ts-input`.
32. After a full reboot: every module marked `calisiyor` running, every name resolving,
    public wg UDP published, built-in WebDAV answering `401` via Caddy.
33. `systemctl --failed` is empty.

### Idempotency

34. A second complete run changes no byte of any generated file, restarts
    no module service it did not need to, and preserves the folder share
    registry (`SHARE_STATE_FILE`).
