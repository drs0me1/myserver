# Model A and clean-install readiness

## What ships

This is the approved Model A implemented in the real panel, not a new mockup.
Ana Menü (`#/genel`, DD-213) is the landing page: clock/date in the heading,
one compact network widget and only installed application cards. The sidebar contains
Ana Menü, Files, App Store, Konteynerler, installed applications and Settings, then live
CPU/RAM/disk indicators and IP/version/uptime. Mobile uses the same sidebar behind an
accessible menu button. The old desktop dock, Applications and window controls are
removed. Files is a Finder-style
window whose right-hand column holds places and the selection's actions (DD-232).
App Store uses compact cards with no description below the name. Install/Open stays on the card;
technical details, logs, service controls and removal share an optional panel.

| Area | Responsibility |
| --- | --- |
| Ana Menü | Five-second refresh; network uses two of six desktop slots; narrower cards with start/stop → settings → logs |
| Files | Icons or list; right column: Favoriler, Konumlar (Shares, Trash), details/actions, disk (DD-232); running archive-job bar |
| App Store | Install/remove optional WireGuard/qBittorrent, progress and service logs |
| qBittorrent | Start/stop, Web UI, first login, account and new-download directory |
| WireGuard | Existing networks, peers, profiles and switches |
| Settings | System, Firewall, Caddy, Dnsmasq, Log |
| Konteynerler | Name/status/resources/access; start/stop → edit → remove; image and other operations in details |

Unknown routes open Ana Menü. A bookmark for an absent app opens App Store.
Old Settings/Containers links redirect to Konteynerler; installed application pages
and the compatible `#/genel` route remain available.
CPU sampling is independent of WireGuard. Resource polling is single-flight,
has a 12-second timeout and hides measurements after failure or 30-second
staleness. Missing CPU samples do not hide valid RAM/disk measurements. Disk is
the filesystem containing the configured user root, not a sum of directory sizes.

No production dependency or privilege boundary changed. Tailscale, Caddy,
Dnsmasq, firewall, Files, per-folder WebDAV and ZIP/RAR remain protected. Optional
app removal preserves profiles unless the user separately confirms data deletion.
Existing Settings review, timed confirmation, server rollback, folder boundaries,
archive limits, same-origin gates and CSP remain in force.

## Before installing

1. Prepare a supported fresh Debian 13 host. Ubuntu 24.04/26.04 remain supported
   targets, but this release has not yet had a fresh Ubuntu acceptance run.
2. A provider reset is separate from running the installer. This package does
   not wipe the host, restore backups or recover old credentials/peer identities.
   Save any data that must survive before a reset. On an existing host, rerunning
   the installer preserves managed data and is **not** a clean installation.
3. The installer is started on the server (**DD-228**):
   `curl -fsSL https://raw.githubusercontent.com/drs0me1/myserver/main/kur.sh | sudo bash`.
   The only input is the local domain, asked in stage 0 on a first install (no default).
4. Confirm SSH works. If a reset changed the SSH host key, independently verify
   its new fingerprint before replacing only that server's known-host entry.
   Injecting the same client public key does not preserve the server host key.
5. Run that line over SSH, inspect the summary and confirm.
   Complete the Tailscale login URL if requested; configure the restricted
   local domain and exit-node approval in Tailscale Admin. A fresh node can
   receive a different Tailscale address. Account/ACL changes are manual.

For agent-driven tests on `nrm`, type a scratch domain on a first install. Historical acceptance: v131 and v132 were deployed as in-place updates on the user's
v130 Debian installation. Portable validation, live read-only Store/firewall checks and
local regression suites passed; no reset/reboot or fresh Ubuntu run was performed.
Those results do not certify a fresh install of later releases. See `SESSION.md`
for exact scope and results.

## Fresh-host acceptance checklist (pending)

- Installer exits 0 after all seven stages, including rendered Caddy/dnsmasq/
  systemd validation and firewall/API gate checks.
- `panel.<domain>` opens Ana Menü over the tailnet, with no application tiles before
  installation; an empty-state link opens App Store. Initial navigation includes
  Ana Menü/Files/App Store/Konteynerler/Settings. No old settings, peers or accounts appear.
- Resource values become live without installing WireGuard. Disconnecting
  marks values unknown; reconnecting recovers them.
- File upload/create/move/trash/restore, per-folder RO/RW/pause sharing, ZIP
  creation and automatic nested ZIP/RAR extraction work. Check multipart RAR,
  the downloads default destination and folder picker. The file backend remains
  unprivileged; sources and archive safety limits remain protected.
- App Store qBittorrent install → own page → settings → stop/start → removal
  succeeds; menu entries follow installed state. WireGuard install → first
  network → test peer succeeds; removal closes network access.
- DNS-only Apply and qBittorrent account-only Save commit immediately. Account
  save must accept the new login after restart, preserve unrelated drafts and
  report failures without claiming success. Folder/firewall and mixed drafts
  still confirm or roll back after 60 seconds.
  Domain changes require the existing separate five-minute new-host confirmation.
- Same-version rerun preserves accounts/profiles/history; reboot returns core
  services, DNS, panel and firewall. Test Ubuntu targets separately.

The existing `tests/desktop-live.cjs` is adapted to Model A; it writes only
inside a named disposable archive fixture. Optional lifecycle mutation still
requires `TEST_APP_LIFECYCLE=1`. See `tests/README.md` before running live suites.
Local fixtures validate UI/API integration, not a real apt installation or boot.
