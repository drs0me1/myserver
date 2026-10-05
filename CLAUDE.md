# CLAUDE.md

Working guide for any AI assistant in this repository. Read this first.

## Project Overview

Active code lives under `Data/`; the repository root holds only what the
operator double-clicks — the current portable installer (`<V2_VERSION>.command`)
and `wireguard.command` — plus the Git-ignored `kurulum/` (installer inputs and downloaded WireGuard device profiles/QR codes),
`versiyon/` (frozen copies of verified working versions), this file and `README.md`. Bare paths in this file and in `Data/docs/` (`install.sh`,
`config/defaults.env`, `tests/`, `CHANGELOG.md`, …) are relative to `Data/`.

The installer turns a fresh Debian 13
(trixie) or Ubuntu 24.04/26.04 LTS host
into a Tailscale exit-node with host dnsmasq + Caddy on the tailnet and a
persistent firewall. Files, folder WebDAV and ZIP/RAR are built in; optional
WireGuard and qBittorrent are installed from App Store (**DD-159**).
There is no Docker (**DD-152**); Podman is base infrastructure, the App Store's container runtime
(**DD-208**), and qBittorrent runs in it (**DD-209**). There is no
reconcile / self-healing engine by design.

Authoritative behaviour: [`Data/docs/contract.md`](Data/docs/contract.md).
Architecture: [`Data/docs/architecture.md`](Data/docs/architecture.md).
Non-obvious rationale: [`Data/docs/design-decisions.md`](Data/docs/design-decisions.md)
(`DD-*` entries; one-line index in [`Data/docs/decisions-index.md`](Data/docs/decisions-index.md)).
Cursor rules for the tree:
`.cursor/rules/master-stack.mdc`.

The installer is destructive: firewall, systemd, network state. Treat every change as production-infrastructure work.

## Language Rules

- **Speak to the user in Turkish.** Conversational replies only.
- **Operator-facing strings are Turkish** (messages printed by
  `install.sh` and helpers). Match existing style in each file.
- **Markdown documentation and commit messages stay in English.**
- **`tests/*.bats` stay English** for comments and `@test` names
  (Turkish `@test` names break `bats` under `tr_TR.UTF-8`).
- Keep each artifact internally consistent.

## Execution Rules

- **The `nrm` host is a disposable test target under standing
  authorization (2026-07-31, reaffirmed 2026-10-03; data loss is acceptable
  until explicitly revoked).** Unless the user says otherwise, on `nrm`
  only: run the installer, `sudo`, mutating `systemctl`, firewall
  changes, wipes, and reboots without per-turn approval. Drive the installer
  with a scratch test input file, never the operator's `kurulum/kurulum.env`:
  empty domain, path and ports (defaults). The input file holds no accounts:
  the Konsol account is the operator's, created by them in Settings over
  Tailscale (**DD-205**; the tailnet asks for no sign-in, the public name needs
  the account) — never create or keep one on their behalf; scripted checks use
  `sudo master-konsol oturum-ac` sessions where a session matters, and
  `konsol-login-live.py` runs only while no account exists and resets afterwards.
  Folder shares are managed in Konsol and qBittorrent's
  account is chosen in its App Store install form (**DD-210**). Add and
  remove test peers with `master-wg`/`wireguard.command` (never print a
  profile; QR codes of test peers only). Answer the
  re-run questions with their defaults and `E` at the confirmation, and report
  what was used. **Do not create server-side backups for installations on `nrm`
  (explicit instruction, 2026-10-03).** The goal is to prove the written code works
  on the real server; data loss is acceptable. Use scoped fixtures when useful,
  without adding preservation or backup steps to the installation workflow.
  The earlier instruction to preserve a real Infuse credential on `nrm` is
  superseded by the user's latest test-host instruction. Other hosts are not covered.
  Non-default config values still need the user.
- **Never open, print or copy `kurulum/kurulum.env`** — it holds the
  operator's private installer inputs (SSH host and local domain), not service
  passwords. Downloaded device profiles contain private keys and must also stay
  private. There is no Tailscale auth key any more
  (**DD-147**): the node joins through the login link. Running the launcher
  with the operator's folder is allowed only when the user asks for it in chat.
- **Relay only the Tailscale login URL** (`https://login.tailscale.com/a/...`)
  and wait; it expires if left unused.
- That authorization does **not** cover: local Mac outside this repo;
  `git reset --hard`, `git push`, force-push, tag deletion, history
  rewrite; other hosts; Tailscale account/ACL changes; publishing repo
  content elsewhere.
- Read-only inspection is always fine.
- **Report what was actually run** and the real outcomes.

## Working Conventions

- Prefer static analysis first (`bash -n`, `shellcheck`, `bats tests`).
  Escalate to live `nrm` installs when static review cannot catch the
  failure mode — still report destructive commands.
- Analyze before editing; check `docs/design-decisions.md` and
  `docs/contract.md` before "fixing" intentional behaviour.
- Wait for approval before making changes unless the user already asked
  for that change.
- Smallest possible change. No opportunistic refactors.
- Show the diff before committing. Commit only when the user asks (unless
  a user rule says otherwise for that turn).
- Keep version history in Git. For every `V2_VERSION` change, rebuild the current
  portable installer with `Data/dev/export-installer.sh` without `--desktop`.
  Keep matching `<V2_VERSION>.command` files in the repository root and `Data/app/`,
  verify them against the final source, and include them in the version's commit
  when the user requests a commit. Keep only the current installer in these two
  locations; older versions remain in Git. Do not create Desktop copies or separate
  version snapshots. Copy outside the repository only on an explicit user request.
  Leave existing Desktop copies and frozen versions untouched.
- Bump `V2_VERSION` in `install.sh` on every behavioural change to the
  installer tree. Record user-facing changes under `[Unreleased]` in
  `CHANGELOG.md` and add a `DD-*` entry when rationale is non-obvious.
- Preserve idempotency: re-runs against a provisioned host must stay safe.
- Prefer security over convenience when both achieve the same result; flag
  the trade-off.
- Single source of truth for ports/paths/chain names:
  `config/defaults.env`. Do not restate literals elsewhere.
- Do not grow a general-purpose reconcile engine (contract + rules).

## Key Paths

| Path | Purpose |
|------|---------|
| `<V2_VERSION>.command` (root) | Current portable installer, copied from `Data/app/` by the exporter |
| `kurulum/kurulum.env` (root) | Installer inputs, Git-ignored, mode 600; template `Data/config/kurulum.env.example` |
| `wireguard.command` (root) | WireGuard peer menu over SSH (**DD-124**, **DD-143**): pick a network, list/add/remove/QR, 7) DNS change, 8) regenerate the network after typing `onayla`. No server backup/restore; only explicitly downloaded device profiles and QR codes are kept on the Mac |
| `versiyon/` (root) | Copies of verified working versions on the user's request: `<V2_VERSION>/` from a commit via `git archive` (no `Data/app`, no `kurulum/`), each with a Turkish `OKUBENI.txt`; index in `versiyon/OKUBENI.txt`. Frozen: never edit a saved copy |
| `kurulum/wireguard/` (root) | Only what `wireguard.command` downloads on request: device profiles and their QR pictures (**DD-132**), mode 600. Since **DD-143** the installer never reads this folder and nothing is sent to the server |
| `Data/magaza/wireguard/master-wg` | Server-side peer tool; the WireGuard package installs it to `/usr/local/sbin` and removes it with the package (**DD-196**) |
| `Data/scripts/master-modul`, `Data/magaza/<id>/` | Store engine (root; `liste`/`kur`/`baslat`/`durdur`/`kaldir`/`gunluk`/`uygula`/`hesap`) that knows no application, and the packages it runs: `paket.env` manifest, `kanca` hooks, slot files, the package's own settings file (`<id>.env`: `wireguard.env` with every `WG_*` key, `torrent.env` with the interface port and profile; the base carries none, **DD-201/203**), the folders it writes into (`PAKET_KLASORLER`, optional `klasorler.py` report) and the paths the root backend may write for it (`PAKET_ARKAUC_YOLLAR`, **DD-203**; the installer creates them before the backend starts, **DD-207**), an optional traffic module for the overview's network card (`PAKET_TRAFIK`, `trafik.py`: qBittorrent's own all-time statistics file, WireGuard's interface counters, **DD-206**), a container application's quadlet and digest-pinned image (`PAKET_KONTEYNER`, `PAKET_IMAJ`; the engine places the quadlet into `KONTEYNER_BIRIM_DIR`, **DD-209**) and its own bridge network (`PAKET_KONTEYNER_AG`; the engine creates and removes it, the container guard passes only the quadlet's WAN/Tailscale publications, **DD-217**) and the tag Konsol checks for newer builds (`PAKET_IMAJ_KANAL`; updates only on the operator's confirmation, **DD-214**), an install/settings form (`konsol.json` `form` + `PAKET_KUR_AYAR` worker; the engine requires the private seed `RUNTIME_DIR/modul-<id>.kur`, **DD-210**) and the Konsol files `konsol.json` (App Store texts, page declaration), `sayfa.js`/`sayfa.css` (the page, placed under `CONSOLE_WEB_DIR/uygulama/<id>/` while installed) and `api.py` (root-backend module behind `/api/uygulama/<id>/*`; qBittorrent's runs its settings worker `ayar.py` through `ctx.worker`, **DD-202**), rendered by the installer to `/usr/local/share/master-stack/moduller/` (**DD-197**, **DD-200**); registry `/etc/master-stack/moduller`. Folder accounts are managed by `master_shares.py` (**DD-158**) |
| `Data/console/` | Konsol shell (`index.html`, `konsol.js`/`konsol.css`, the skin `panel.css` — CasaOS-inspired glass over an inline-SVG wallpaper, overview landing page with widgets and tiles, **DD-204**; edit mode with tile order, widget width/visibility saved in `KONSOL_AUTH_DIR/duzen.json` and the network card, **DD-206**; installed applications open from their home tiles and have no sidebar entry, **DD-216** — and per-page scripts/styles; `giris.html`/`.js`/`.css` sign-in and first account) at Caddy `panel.<domain>` on the tailnet, optionally a public HTTPS name (**DD-140**, **DD-194**, **DD-195**). The shell names no application: installed packages' pages register through `window.Konsol.sayfa` (**DD-200**). Design mockups in `Data/docs/design/` |
| `Data/panel/master_auth.py`, `Data/scripts/master-konsol` | Konsol account and sessions (**DD-194**, **DD-205**): Caddy `forward_auth` asks the root backend's `/oturum-denetle` before every protected panel request and the answer follows the channel — the tailnet address passes without a sign-in, the public name needs the account (scrypt hash, SHA-256 session tokens in `KONSOL_AUTH_DIR`, 0700 root), which the operator creates in Settings over Tailscale; no setup code. Root CLI: `master-konsol durum|sifirla|oturum-ac|oturum-kapat` |
| Built-in WebDAV (`paylasim` internal ID) | **DD-158/159/192:** `master_shares.py` owns `/etc/master-stack/webdav.json` (0600 root, scrypt hashes); `master_webdav.py` runs as the downloads uid with a systemd credential. Each folder's `/s/<id>/` and account are shared by two independent Tailscale/WAN policies: enabled, RO/RW and expiry. Shares shows two cards; Manage edits the shared folder/account/password. Caddy serves Tailscale HTTP on `SHARE_PORT`; optional public HTTPS uses `SHARE_HTTPS_PORT` and `master_https.py` (**DD-179/190**). No cross-folder shared account or writable symlink tree. See contract §3 and §5–7 for publication modes, limits and manual recipient ACL requirements. |
| `Data/panel/` | Konsol's root backend (`master-panel`, Python stdlib, root, Unix socket `/run/master-panel/api.sock` only — no TCP port since **DD-180** — `/api/konsol/*` and `/api/uygulama/<id>/*`, the latter handed to the installed package's `api.py` loaded from its folder, **DD-200**); WireGuard networks wg0…wg9 and peer/network switches live in `Data/magaza/wireguard/api.py` over `master-wg` (**DD-133**, **DD-136**, **DD-140**) |
| `Data/files-panel/` | Built-in file backend (`master-files-panel`, Python stdlib, loopback, downloads uid, no password; trash in `.cop`); `master_archives.py` and `master_rar.py` run bounded archive jobs with private `.arsiv` staging/history. ZIP creation, automatic nested ZIP/RAR extraction and multipart RAR detection are built in. Installer activates both data services through `master-modul yerlesik` (**DD-159**, **DD-166**, **DD-170**). |
| `/etc/wireguard/networks` (host) | Panel networks registry written by `master-wg net-add/net-remove`, read by `master-firewall` and the panel (**DD-136**) |
| `Data/install.sh` | Orchestrator |
| `Data/common.sh` | Shared helpers |
| `Data/config/defaults.env` | Ports, paths, chain names of the base (no package setting; `VPN_BLOCK_DEST4/6` is the firewall's own vocabulary) |
| `Data/templates/` | Caddy, dnsmasq |
| `Data/scripts/` | Firewall, refresh-tailnet, GRO, wait |
| `Data/systemd/` | Unit/timer templates |
| `Data/tests/` | Bats, Python unittest, Playwright and isolated Linux suites; see `Data/tests/README.md` |
| `Data/dev/export-installer.sh` | Portable `.command` exporter |
| `Data/app/` | The current exported `<V2_VERSION>.command` only; the exporter removes older ones (**DD-154**; history is in Git) |
| `Data/docs/contract.md` | What the installer does / refuses |
| `Data/docs/architecture.md` | Layout and data flow |
| `Data/docs/design-decisions.md` | `DD-*` rationale |
| `Data/docs/decisions-index.md` | One line per `DD-*` entry |
| `Data/docs/archive/` | Historical reviews (v2-27, v2-73), the original rules source, retired `DD-*` entries (`design-decisions-retired.md`) and older history moved out of `CHANGELOG.md`/`SESSION.md` (`CHANGELOG-before-v2-145.md`, `SESSION-history.md`); not current behaviour |

## Constraints

- DD-179/190/192: each folder has independent Tailscale/WAN connection policies;
  both off is valid. New shares use Tailscale on/RO/seven days and WAN off/RO/seven
  days. Schema 4 stores only nested `connections` policies; valid schema 3 loads
  migrate in memory without changing IDs, credentials, folder identity, timestamps
  or absolute expiry, and `prepare` persists schema 4. Schema 2 and conflicting
  legacy fields fail closed. Nested partial saves preserve omitted fields under
  locks; explicit RW requires same-scope acknowledgement. Old global-policy and
  pause requests require a page refresh. Share edits still restart active WebDAV
  and interrupt transfers. Settings → Caddy optionally configures a
  public domain for Let's Encrypt TLS-ALPN on `SHARE_HTTPS_PORT` (443), with
  DNS resolving only to the assigned WAN IPv4. No WAN port 80 or DNS API token.
  Absent HTTPS configuration retains consent-gated HTTP on `SHARE_PORT` (61010);
  explicitly clearing the domain closes WAN, never downgrades to HTTP.
  Configured HTTPS keeps its listener for renewal even with no active folders.
  Independent scope/auth enforcement and attempt/connection budgets remain
  mandatory; the Konsol backends themselves stay private (socket/loopback). DD-191 adds an independent
  Tailscale/HTTPS table for WebDAV and for packages that declare a publication in their manifest
  (`PAKET_YAYIN_*`, loopback upstream only, optional check module; DD-199) through `master_publications.py`.
  Its global gates override the DD-192 cards and supply an unavailable reason.
  Available transports may show candidate card URLs while locally off/expired;
  `row.urls` contains only active connections. Each listener enforces its own
  policy on writes, live chunks and staged publication, including cached logins.
  DD-195: the Panel row's Tailscale switch is fixed on; its optional public HTTPS
  name imports the same `(konsol)` Caddy snippet (session check, Host pinned to
  `panel.<domain>`, Caddy-written `X-Konsol-Kanal`), needs an existing Konsol
  account, refuses account creation and adds a shared public sign-in budget.
  qBittorrent WAN requires its permanent
  native login, CSRF/Host checks and login-attempt ban; no preferences are
  rewritten. All public names share TCP443 and its existing socket budgets.
  No Tunnel, arbitrary upstreams or automatic DNS writes. Certificate readiness is a
  local pinned-IP trust/hostname check, not proof of public reachability.
  See `Data/docs/folder-shares.md` for limits and the scoped expiry/recovery timer.

- Root-only, single-host. Inputs come from `kurulum/kurulum.env`; the
  installer still needs a TTY and one confirmation. No unattended mode.
- Debian 13 (trixie), Ubuntu 24.04 (noble) or Ubuntu 26.04 (resolute)
  only (**DD-102**). Noble live-verified 2026-08-29; resolute
  live-verified 2026-08-30, including re-run, service restarts and reboot.
- The fixed base includes Files, folder WebDAV and ZIP/RAR (**DD-159**, **DD-166**).
  Podman is part of the base (daemon-less container runtime, `podman info` checked in
  stages 1 and 7; the main-sidebar Podman page (`#/konteynerler`) adds explicit lifecycle,
  configuration and resource operations, **DD-211**, **DD-216**; no Docker). App Store containers
  retain their package lifecycle; generic definitions are private, digest-pinned Quadlets
  with managed bridge ingress. No implicit adoption, automatic image update or reconciliation.
  The App Store catalogue is WireGuard and qBittorrent; qBittorrent is a container
  application (`PAKET_CALISMA=konteyner`, quadlet + digest-pinned image, **DD-209**) on its own
  bridge `torrent`: interface (62947) published on 127.0.0.1 only, peer port 63851 on the WAN IPv4 address
  (TCP+UDP) only, no IPv6 peers (**DD-217**); both ports are changeable on the Podman page
  (**DD-211**, **DD-221**). Public module
  verbs refuse `dosya`/`paylasim`; these are internal template/registry IDs used
  by DNS/Caddy/firewall rendering. No profiles.
- Do not delete or recreate other software's iptables chains (Tailscale's
  `ts-*`); manage only the project chains.
