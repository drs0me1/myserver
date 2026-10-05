# Changelog archive: entries before v2-145

Historical record, not current behaviour. Moved verbatim from
`Data/CHANGELOG.md` during v2-158; Git holds the full history. The current
changelog is [`../../CHANGELOG.md`](../../CHANGELOG.md).

The entries up to the first `##` heading (v2-144 down to v2-72) were part of
its `[Unreleased]` section. The second `## [Unreleased]` heading below is an
old V1-era duplicate. Paths and links inside the entries follow the
repository layout of their time (repository root, `v2/` or `Data/`) and may
no longer exist.

### 2026-09-28 — Files icon dock, approved model B (v2-144)

- Replace the mixed action strip with six equal icon-over-label cells and a
  separate selection-count/dismiss header. Use a compact floating surface,
  subtle hover treatment and red text/icon for trash, without a filled button.
- Keep unavailable actions disabled in stable positions; switch to a 3×2 grid
  on mobile. Preserve keyboard focus, selection lifecycle, address/search bar,
  confirmation dialogs and archive/share/download semantics (DD-170 follow-up).
- Extend browser regression coverage for selection types, action routing,
  keyboard activation, icon/label alignment and responsive light/dark rendering.
- **Verified:** 108 Python tests (two native RAR skips), 155 Bats cases (three
  macOS timeout skips), four browser suites and portable nrm deployment pass.
  Live read-only checks cover seven widths/both themes with zero writes/errors.
  Service/config checks pass; share/settings/qBittorrent profile hashes and
  qBittorrent process unchanged. No fresh Ubuntu or reboot acceptance claim.

### 2026-09-28 — Files action dock and automatic archive opener (v2-143)

- Keep the address/search bar visible during selection; move file actions to a
  responsive bottom dock. Reserve scroll space and place notifications above it.
- Simplify archive creation/extraction to name, destination picker and collision
  policy. Default destination comes from installer-configured downloads, not the
  source folder. Use generic archive labels and automatically append `.zip` on
  creation; remove depth/nested controls and verbose explanations/statistics.
- Extraction automatically resolves supported multipart/nested archives with
  existing safety limits. Automatic depth overflow fails atomically rather than
  reporting partially expanded work as success; sources and hierarchy remain
  intact. Explicit legacy API depth options remain compatible (DD-170).
- **Verified:** 108 local Python tests (two native RAR skips), 155 Bats cases
  (three macOS timeout skips), four browser suites, 27 native Debian archive
  tests including compressed/solid/multipart RAR and mixed nested formats.
  Portable nrm update and real browser ZIP/four-layer extraction pass; originals
  verified by hash. No new packages, qBittorrent restart or account changes.
  No fresh Ubuntu/reboot acceptance claim.

### 2026-09-28 — Compact trash confirmation and inline share controls (v2-142)

- Simplify move-to-trash to a short question, filename/count and two buttons;
  contain long names without overflowing. Permanent deletion safeguards remain.
- Align Shares into responsive columns; edit access and lifetime with inline
  dropdowns, retaining write/delete acknowledgement and the adjacent copy action.
  Manage now contains only folder/account fields (DD-169).
- Accept partial existing-share saves under the existing locks, preserving
  credentials/expiry/permissions not edited and never rebinding a replaced folder
  through list controls. Keep failed-save rollback and busy-state UI protection.
- **Verified:** 106 Python tests (two native RAR skips), 155 Bats cases (three
  macOS skips), all four browser suites, and 22 native Debian WebDAV tests.
  Portable nrm update and live desktop/mobile checks pass. A temporary account
  verifies actual API access/expiry changes, PUT/GET/RO denial, account-only edits,
  pause preservation and replaced-root refusal. It is removed afterward; original
  share registry/settings/qBittorrent profile and qBittorrent process unchanged.
  WebDAV restarts for the update and test changes; no fresh Ubuntu/reboot claim.

### 2026-09-28 — Eight-character service password minimum (v2-141)

- Lower the qBittorrent and folder WebDAV password minimum from 12 to 8
  characters in browser forms and server validation (DD-168). Keep the maximum,
  hashing, character restrictions, blank-edit preservation and strong generator.
- Add seven/eight-character boundary tests, WebDAV HTTP authentication and
  native qBittorrent login/restart coverage; no existing passwords are changed.
- **Verified:** 102 Python tests (two native RAR skips), 155 Bats cases (three
  macOS skips), both affected browser suites and portable nrm update. Isolated
  Debian qBittorrent 5.1.0 accepts eight characters and preserves login across
  restart; 18 WebDAV tests pass. Live forms enforce eight with zero account
  mutations. Existing account/settings hashes and qBittorrent process unchanged;
  WebDAV restarts during the update. No fresh Ubuntu/reboot acceptance.

### 2026-09-28 — WireGuard network DNS and local access settings (v2-140)

- Replace the destructive refresh shortcut with a network settings dialog:
  default DNS presets/custom IPs, local qBittorrent access, Save and a separate
  key-regeneration action retaining typed confirmation. Explain that default DNS
  applies only to new peers and existing device profiles are unchanged.
- Apply only registry DNS/scope, firewall and the selected Caddy instance;
  preserve keys, profiles, ports, labels, other networks and stopped WG state.
  Serialize and revision-check writes, block pending Settings transactions,
  roll back apply failures, and refresh the firewall view's read cache (DD-167).
- Give explicit local-access changes a fresh firewall/selected-Caddy start
  budget; preserve automatic restart-loop limits. DNS-only edits touch no service.
- Add API gate/validation, shell ordering/rollback/preservation and browser
  save/error/draft/mobile/confirmation regression tests.
- **Verified:** 155 Bats cases (three macOS skips), 99 Python tests (two native
  RAR skips), four browser suites and portable nrm update/reruns. A disposable
  encrypted WG client reaches qBittorrent only with local access enabled;
  14 repeated toggles, stopped-network editing, stale-write rejection and
  firewall read-back pass. Real desktop/mobile Save and new-peer DNS defaults
  pass; original WG profiles and WebDAV/qBittorrent settings/processes unchanged.
  No fresh Ubuntu/reboot acceptance in this update.

### 2026-09-28 — Multipart and nested RAR in Files (v2-139)

- Add “Arşivi aç” for ZIP/RAR3/RAR5, solid and multipart RAR, including mixed
  nested ZIP/RAR sets. Later-part selection resolves the first automatically.
  Keep all source/inner volumes, existing destinations, job limits and atomic
  publication; invalid/missing/encrypted/unsafe archives publish no partial result.
- Install distro-signed unrar/python3-rarfile, adding only a managed signed
  Debian non-free or Ubuntu universe/multiverse source if required. No new port
  or application module; ZIP creation stays unchanged.
- Stream RAR content through a bounded, cancellable unprivileged helper; never
  let the extractor write destination paths. Add multipart, safety, subprocess,
  native-format and browser regression coverage (DD-166).
- Keep long archive folder paths within the extraction dialog and file
  breadcrumbs on mobile, without hiding the full breadcrumb text.
- **Verified:** 94 local Python tests (two native-only skips), 149 Bats cases
  (three macOS skips), three browser suites and 25 unprivileged native ZIP/RAR
  tests on Debian. Portable update/reruns passed. The user's 17-volume RAR
  extracted via Files in 16 seconds; output size/CRC and all source hashes verified.
  WebDAV/qBittorrent accounts/processes unchanged; no fresh Ubuntu/reboot claim.

### 2026-09-28 — Keep the share copy action beside its address (v2-138)

- Place the copy button immediately after the WebDAV URL in both the Shares
  list and folder details. Keep long addresses wrapped beside their action on
  narrow screens; remove the distant duplicate action from the management row.
- URL generation and clipboard handling are unchanged. Read-only live v137
  checks found identical API, rendered, selected and actual clipboard text on
  Chromium desktop/mobile layouts, with no whitespace or hidden characters.
  This does not certify native iPhone clipboard behavior or identify where the
  previously observed extra request-path character originated.
- Browser regressions check address/button adjacency, exact copied text and
  overflow in the list/details at five widths. No account, permission or WebDAV
  backend changes.
- **Verified:** Bats and all three UI suites pass (three macOS timeout skips).
  Portable nrm update and read-only live geometry/actual clipboard checks pass;
  WebDAV/qBittorrent processes, accounts and settings are unchanged.

### 2026-09-27 — Keep Trash names and actions aligned (v2-137)

- **Fixed:** the general five-column file grid overrode Trash's four columns,
  squeezing names into the 26 px selection column. Give Trash its own scoped
  grid; wrap full names and origin paths without clipping or page overflow.
- Narrow layouts place the name/path above size/deletion time and actions.
  Restore stays legible in dark mode. No API, restore, deletion or confirmation
  behavior changes; no operator trash is changed by layout verification.
- Extend browser regression coverage to populated/empty Trash, 255-character
  names, long paths, seven widths/both themes and mocked restore/purge/empty
  confirmation flows under the production CSP.
- **Verified:** 144 Bats passes/3 macOS skips, all three browser suites and
  portable nrm update. Live seven-width/both-theme checks pass with zero
  mutation requests and unchanged Trash inventory. qBittorrent's profile and
  process remain unchanged; no reset or reboot.

### 2026-09-27 — Align qBittorrent account and download fields (v2-136)

- **Fixed:** prevent the password-confirmation field from stretching/lowering
  when the adjacent password field has help text. Equal control heights and
  shared left edges for headings, inputs and Save remove the double inset.
- Place the download path and folder action on one row on wide screens, stack
  them on mobile, wrap long paths and keep the folder action legible in dark mode.
- CSS is scoped to qBittorrent. Account saving, validation, credentials, folder
  confirmation and all other settings pages are unchanged.
- **Verified:** 144 Bats passes/3 macOS skips and all three browser suites.
  Portable nrm update and live read-only geometry checks pass at five widths
  in both themes, with no JS/CSP errors. Account/profile, settings and WebDAV
  hashes and the running qBittorrent process are unchanged.

### 2026-09-27 — One-click qBittorrent account save (v2-135)

- **Fixed (DD-165):** Save account now persists username/password in one
  request, without staging, review or timed confirmation. Show explicit saved
  status, disable duplicate submission, clear secrets and preserve other drafts.
- Fix username validation in modern browsers. Blank preserves the stored hash;
  explain that temporary startup passwords can rotate on service restart.
- Server-side eligibility is limited to account-only requests. Preserve failure/
  crash recovery, stale-revision/lock checks, stopped services and unrelated
  profile settings. Folder/mixed/firewall/domain confirmations are unchanged.
- **Verified:** 84 Python tests, 144 Bats passes/3 macOS skips, three browser
  suites and portable nrm update. Isolated real qBittorrent login/restart/
  failure recovery passes; deployed UI/API stale-write rejection and asset
  checks pass without changing the operator's live account.

### 2026-09-27 — Firewall incoming-network categories (v2-134)

- **Changed (DD-164):** Tailscale (default), Internet, conditional WireGuard
  with per-network selection, and protected loopback tabs. Technical rules
  remains an all-network read-only view including forwarding/NAT.
- Separate socket binding status from firewall permission. Fix IPv6 link-local
  zone formatting and preserve service names across scopes. No port scanning,
  policy changes or new dependencies. Draft/apply/confirmation/rollback and
  DNS-only immediate Apply are preserved.
- **Verified:** 77 Python tests, 144 Bats passes (3 macOS skips), all three
  browser fixture suites and portable nrm update. Live category/rule readback,
  both-family TCP deny/allow/confirm/reload/manual and timed rollback pass;
  owned test rules removed and original firewall/DNS choices restored.

### 2026-09-27 — Immediate Dnsmasq Apply (v2-133)

- **Changed (DD-163):** DNS-only edits persist on Apply after validation and
  dnsmasq restart, without a review dialog or one-minute connection confirmation.
  UI refreshes saved state and reports success; the panel's own DNS name stays
  protected and cannot be disabled. Failed applies retain snapshot recovery.
- Mixed firewall/qBittorrent drafts still require 60 s confirmation; domain
  migration retains 300 s/new-address confirmation. Revision/lock checks and
  crash-safe commit/guard recovery remain; no client confirmation bypass flag.
- **Verified:** portable nrm update and live UI/DNS apply/reload/63-second
  persistence/switch-off/panel-name rejection with fixture cleanup. 71 Python
  tests, 144 Bats passes (3 macOS skips), all three browser suites, 33 Linux
  settings unit tests and real systemd guard/worker recovery pass.

### 2026-09-27 — Full firewall tables (v2-132)

- **Changed (DD-162):** port permissions use an eight-column table with service
  descriptions, port/protocol, incoming interface/family, source CIDR, listeners
  and address notes, policy, switches and inline edit/remove actions. Details
  are no longer hidden behind disclosures; drafts are labelled, not shown as saved.
- All live rules retain raw specifications, order, counters and ownership,
  with short explanations. Both views stay real tables on mobile, with sticky
  headers and keyboard-accessible scrolling confined to the table.
- Existing on/off drafts, review/apply/confirmation/rollback, protected loopback
  and read-only third-party rules are unchanged. No backend or policy changes.
- **Verified:** portable nrm update, live IPv4/IPv6 switch/discard with zero
  mutation requests, five screen widths/light/dark; 66 Python tests, 144 Bats
  passes (3 macOS skips) and all three browser fixture suites.

### 2026-09-27 — Compact App Store list (v2-131)

- **Changed (DD-161):** approved model 2 replaces large app cards with compact
  icon/name/one-line-description rows, visible state and Install/Open actions.
  A single optional Details panel holds technical notes, logs, stop/start and
  removal. Account information stays on the qBittorrent page, loaded on request.
- Progress and failures remain visible with details closed. Polling preserves
  selection, keyboard focus and log scroll; mobile retains status and actions.
  Failed log requests are reported instead of displayed as successful log data.
- Existing APIs, install/remove confirmations and default data retention are
  unchanged. No new runtime dependency, package or network exposure.
- **Verified:** portable in-place update on nrm (Debian 13.7), desktop/mobile
  light/dark live read-only checks, 66 Python tests, 144 Bats passes (3 macOS
  skips) and all three fixture browser suites. No host reset or app/data removal.

### 2026-09-27 — Model A admin panel and clean-install preparation (v2-130)

- **Changed (DD-160):** Files is the landing page; one responsive sidebar,
  optional installed-app links and live CPU/RAM/disk. Removed Overview,
  Applications launcher, dock and imitation window controls; old bookmarks redirect.
- **Changed:** Settings owns System/Firewall/Caddy/Dnsmasq/Log. qBittorrent
  owns its service/account/download settings, sharing the existing transaction
  controller, review and server-side rollback with Settings.
- **Changed:** Files has Files/Shares/Archive jobs/Trash tabs; details are
  optional. ZIP submissions open history and result buttons return to Files.
- **Added:** independent, gated host-resource API/sampler, unknown/stale display,
  browser/API regressions and a clean-install checklist. No new runtime dependency
  or network exposure. Portable v130 prepared; no server deploy/reset this turn.

### 2026-09-25 — Konsol Desktop, built-in sharing and ZIP (v2-129)

- **Added (DD-159):** the approved desktop shell, application launcher, dock
  and workspace controls; existing live Settings and file operations remain.
- **Changed:** Files and folder WebDAV are installer-owned built-ins, not
  installable/removable apps. Files → Paylaşımlar lists all folder accounts.
  The App Store catalogue is WireGuard and qBittorrent; infrastructure is protected.
- **Added:** background ZIP creation/extraction, optional nested ZIP expansion,
  cancellation, result links and restart-persistent 20-job history. Source files
  are preserved; malformed/unsafe archives and bounded resource overruns fail
  without publishing partial results. Details: `docs/desktop-and-archives.md`.
- Upgrade enables both built-ins without resetting existing folder accounts.
  Same-version reruns preserve history/accounts and avoid unnecessary restarts.
- **Verified on disposable nrm (Debian 13.7):** portable install, rerun, reboot,
  real ZIP/DAV requests and browser qBittorrent install/stop/start/remove. Unit,
  Bats and browser regressions passed; fresh Ubuntu/native clients not certified.

### 2026-09-25 — Files v09 and independent folder WebDAV (v2-128)

- **Added (DD-158):** list/cards, selected-folder details and a WebDAV shares
  tab. Each folder has its own account, stable URL, RO/RW permission, expiry
  and pause switch. RW requires explicit deletion/overwrite acknowledgement.
- Passwords are stored only as salted scrypt hashes in a root-owned registry;
  a credential-loaded unprivileged server checks each account's folder boundary.
- **Breaking:** the shared rclone account/root is retired. Existing files stay;
  recreate folder accounts and update client URLs. Removing a share never deletes
  its files. Saving accounts interrupts current WebDAV transfers.
- Protocol/client limits and manual recipient ACL prerequisites are documented
  in `docs/folder-shares.md`. No Tailscale account policy is changed.
- User explicitly authorized deployment to disposable `nrm`; verification
  outcomes are recorded in `SESSION.md`. No fresh Ubuntu/native-client claim.

### 2026-09-25 — Clearer settings and transactional local-domain changes (v2-127)

- **Changed:** firewall listening addresses have short explanations; settings
  descriptions distinguish permissions, listeners, local names and upstream DNS.
- **Removed:** the redundant `health.<domain>` Caddy site, DNS name and stage-7
  probe. Real Konsol static-page and backend/gate checks remain.
- **Added** (**DD-157**): Caddy's local-domain field and Update action. DNS,
  Caddy sites, backend Host configuration and staged module templates move
  together; custom records retain their targets and enabled/disabled state.
  Passwords, files, VPN profiles and IP-based share links are not changed.
- A domain-only transaction requires confirmation through the new panel Host
  within five minutes, otherwise the existing independent guard restores it.
  An active file backend briefly restarts; stopped modules remain stopped.
  Tailscale Admin DNS changes are manual and explained before applying.
- The confirmed domain survives installer re-runs even with an older input
  file. Tailnet IP refresh and settings writes share a state lock; rollback
  restores only the domain field, not obsolete IP addresses.
- **Operator step:** run the v127 installer. No live host upgrade is performed
  by creating this release; no fresh Ubuntu acceptance run for this revision.
- **Verification:** 28 worker unit tests, 144 Bats passes (3 macOS skips),
  production-page browser checks, real Caddy/DNS/both-backend domain round trips
  in an isolated Debian network namespace, and real scratch systemd recovery.

### 2026-09-24 — Konsol · transactional settings management (v2-126)

- **Added** (**DD-156**): the approved v08 layout is now the live Ayarlar page:
  Güvenlik Duvarı, read-only Caddy, Dnsmasq and qBittorrent tabs.
- Firewall port switches and structured IPv4/IPv6 rules operate before
  Tailscale's general accept. Actual rules, counters and listening sockets
  are visible; third-party chains are not edited. No raw shell rule input.
- DNS names can be switched off or added within the private domain. Optional
  public upstreams resolve other names; missing/disabled private names never
  go upstream. Installer and module re-runs retain these choices.
- qBittorrent username, optional password and the default folder for new
  downloads can be changed. The service is stopped before updating its
  profile; existing torrents, unrelated settings and files are preserved.
  A narrow systemd write permission is added for the chosen folder.
- Changes are reviewed together and need confirmation within 60 seconds.
  A server-side systemd timer restores unconfirmed settings, even after a
  browser disconnect or host reboot. Stale edits and concurrent installer/
  module operations are rejected. Passwords never enter argv or logs.
- **Verification:** worker unit tests, production-page browser interactions
  and responsive layouts; real IPv4/IPv6 firewall, dnsmasq and qBittorrent
  transactions in an isolated network namespace on Debian 13; independent
  systemd worker/timer checks. No fresh Ubuntu install tested for this revision.
- **Operator step:** run the v126 installer. This change does not itself
  deploy to the running server. The frozen v08 HTML remains a reference only.

### 2026-09-19 — Konsol · Ayarlar: the server's settings, read-only (v2-125)

- **Added** (**DD-155**): an Ayarlar page in Konsol showing the server's
  current configuration without changing anything:
  - the firewall rules grouped by where traffic comes from (internet,
    Tailscale, each WireGuard network, the server itself), with how many
    packets each rule caught, an IPv4/IPv6 switch and the raw rules in a
    closed box; a rule Konsol does not recognise is listed as such;
  - the web addresses Caddy serves and where each one goes, with its module
    and who can reach it;
  - dnsmasq's names and policy;
  - qBittorrent's download and temporary folders, with a warning when they
    are outside the downloads folder (qBittorrent cannot write there).
- **Operator step:** run the installer again.

### 2026-09-19 — One console name, one current export (v2-124)

- **Removed** (**DD-154**): the old addresses `wg.`, `dosya.` and
  `file.<domain>`, which only redirected to Konsol. Use `http://panel.<domain>`.
- **Changed:** the exporter keeps only the current installer in `Data/app/`
  (older ones are in Git history), like the repository root.
- **Operator step:** update bookmarks to `panel.<domain>` and run the installer
  again.

### 2026-09-19 — The base installs only what it uses (v2-123)

- **Removed** (**DD-153**) from the base packages:
  - `gnupg` and about 15 packages it pulled in: Caddy's repository key is
    stored armored (`.asc`) and apt reads it directly.
  - `gawk`, left from the first installer: the system's `mawk` is enough.
  - `apache2-utils`: Paylaşım installs it when it needs `htpasswd`.
- **Operator step:** none for a fresh install; an existing server keeps the
  packages.

### 2026-09-19 — Fixes from the first host Paylaşım trial (v2-122)

- **Fixed** (**DD-152**):
  - "Yeni parola" changed the password but reported "uid 0": the check read
    the new process before systemd had switched it to the service account.
    The Paylaşım unit is now `Type=exec` (a start returns only once rclone
    runs), and every module check reads the process owner a few times
    before it judges it. The same latent race is closed for the Dosya
    yöneticisi and qBittorrent checks.
  - A stopped Paylaşım showed as failed: rclone exits with 143 on SIGTERM,
    which the unit now counts as a clean stop.
- **Operator step:** run the installer again.

### 2026-09-19 — No Docker: Paylaşım runs on the host, Arşiv açıcı is gone (v2-121)

- **Removed** (**DD-152**): Docker. The installer adds no Docker repository,
  packages, `daemon.json` or unit drop-in, and the firewall has no
  `MASTER-DOCKER` chain and never touches `DOCKER-USER`. This saves the
  engine's memory (about 110–150 MB on `nrm`) and a whole layer of settings.
- **Removed:** Arşiv açıcı (Unpackerr), with its module files, Konsol card and
  the `.unpackerr` folder. Nothing replaces it.
- **Changed:** Paylaşım (the share WebDAV for Infuse) runs on the server as
  `master-paylasim.service`, using rclone's official release (1.75.1). The
  version and one SHA256 per architecture are pinned in `defaults.env`, and
  the archive is checked before it is unpacked. The distribution's rclone
  (1.60.1 from 2022, with open security issues) is not used.
  - Same address, port, account and share links as before; Infuse sees no
    difference.
  - Konsol → Modüller → Paylaşım installs it in four steps: download rclone,
    generate the account, start the service, open the name and address.
  - The service runs as the downloads account, can write nothing, cannot
    connect out, gets its account as a systemd credential and sees the trash
    as an empty folder (a link into the trash disappears alone instead of
    breaking the whole list).
  - Removing it keeps the rclone program; a new pinned version is installed
    by the next installer run.
- **Operator step:** reset the server and install v2-121 fresh (a host from an
  earlier version keeps Docker and its containers). Then install Paylaşım from
  Konsol and enter its new account in Infuse.

### 2026-09-19 — First fixes from the live module trial (v2-120)

- **Changed** (**DD-151**): qBittorrent's first settings turn Local Peer
  Discovery off; it announced what the server downloads on the provider's
  local network. Only a new profile gets it: remove qBittorrent with its data
  and install it again to apply it on an existing server.
- **Fixed:**
  - Konsol's ports card listed the file backend's port without the Dosya
    yöneticisi module.
  - While a module operation ran, every status query wrote two "Failed to open
    /run/systemd/transient/…" lines to the system journal; the root backend
    now reads running operations with `systemctl list-units`. One such line
    per started operation remains: systemd writes it when `systemd-run`
    reuses the unit name.
  - The installer's summary said "Konsol → Modüller'den kurulur" for modules
    that were already installed; it now lists each module's state and, when
    installed, its address.
  - A re-run said WireGuard's "file changed"; it now says WireGuard is
    re-applied on every run.

### 2026-09-19 — Konsol starts on a fresh install again (v2-119)

- **Fixed** (**DD-150**): on a fresh v2-118 install Konsol's root backend did
  not start (`/etc/wireguard` missing, now that WireGuard is a module) and the
  installer stopped in stage 7. The installer now creates the folder before
  starting the backend, and the backend no longer refuses to start without it.
- **Operator step:** run the installer again; no reset is needed.

### 2026-09-18 — qBittorrent is a Konsol module; Dozzle and the base Compose project go (v2-118)

- **Changed** (**DD-151**): qBittorrent left the base install. Konsol →
  Modüller → qBittorrent installs the distribution's `qbittorrent-nox` in four
  steps (package, service unit, start, name) and runs it as the downloads
  account at `http://torrent.<domain>` (tailnet only).
  - Its settings are written once, at the first install: save path, the
    `incomplete` temporary folder, web UI on loopback, UPnP off. After that the
    installer never touches them; what you change in qBittorrent stays.
  - The login is qBittorrent's own. The card shows the user and, until you set
    a password in qBittorrent, the temporary password from its log (on
    request, hidden after 30 s). The log panel masks it.
  - No inbound peer port: 61005 is closed and qBittorrent only connects out.
  - Removing stops and disables the service and keeps the package; the data
    option also deletes the profile (settings and torrent list). Downloaded
    files are never deleted.
  - The service is sandboxed: it can write only its profile and the downloads
    folder, and cannot see the trash or the share root.
- **Removed:** Dozzle (every module card has a log), the base Compose project
  (`/root/docker/compose.yaml`), the image-pull question on re-runs, and the
  `DOZZLE_USER`, `DOZZLE_PASS`, `TORRENT_USER` and `TORRENT_PASS` inputs. The
  input file now holds only `SSH_HOST` and `LOCAL_DOMAIN`.
- **Operator steps:**
  - Delete the four account lines from the input file; otherwise the installer
    stops before changing anything:

    ```bash
    sed -i '' -E '/^(DOZZLE|TORRENT)_(USER|PASS)=/d' kurulum/kurulum.env
    ```

  - Reset the server and install v2-118 fresh; the old containers and
    qBittorrent data are not carried over.
  - Install qBittorrent from Konsol → Modüller, log in with the temporary
    password shown on its card and set your own in qBittorrent (Tools →
    Options → Web UI).

### 2026-09-18 — Dosya yöneticisi and WireGuard are Konsol modules (v2-117)

- **Changed** (**DD-150**): a clean install now brings only Konsol, Tailscale,
  names, the firewall and Docker. Konsol → Modüller installs **Dosya
  yöneticisi** (the file backend, in three steps) and **WireGuard** (packages,
  kernel module, firewall hook, the registry's networks — four steps).
  - The Dosyalar and WireGuard pages and menu items appear with their modules;
    a bookmark to a missing page opens Modüller. The disk card works without
    the file manager (total and free from the root backend).
  - Both are installed or removed, never stopped. Removing WireGuard closes
    every network and keeps the keys and profiles (a reinstall brings the
    networks back); its data option also deletes them. Removing the file
    manager keeps the trash; its data option empties it.
  - Paylaşım needs the file manager: "Dosya yöneticisi ile birlikte kur"
    installs both in order, and removing the file manager removes Paylaşım
    first ("Birlikte kaldır", keeping its account and links).
  - Without the WireGuard module the firewall opens no WireGuard port, even if
    a network registry was kept; `master-wg` and wireguard.command say the
    module is missing.
  - The installer renders the file backend's unit to the module folder and
    checks the file backend and WireGuard in stage 7 only while installed.
- **Operator step:** reset the server and install v2-117 fresh (a host from an
  earlier version runs the file backend and WireGuard outside the module
  registry); then install the modules you want from Konsol.

### 2026-09-18 — Paylaşım is a Konsol module with a generated account (v2-116)

- **Changed** (**DD-149**): the share WebDAV left the base install. Konsol →
  Modüller → Paylaşım installs it in four steps (image, account, container,
  name and address) and removes it with its name and port.
  - Base Compose has two services (Dozzle, qBittorrent). The module's files are
    `modules/paylasim/compose.yaml`, `paylasim.caddy` and `dnsmasq.conf`.
  - The account is generated on the server: user `paylasim` and a 20-character
    random password. The card shows the address, the Infuse address and the
    user. The password appears only on request and hides again after 30 s.
    **Yeni parola** makes a new one and restarts the share.
  - Removing keeps the account and the share links (a reinstall brings them
    back unchanged). "Hesabı ve paylaşım kayıtlarını da sil" removes the
    account, the registry and the links, never the shared files.
  - The name is a module file: `/etc/caddy/moduller/paylasim.caddy` (the base
    Caddyfile imports that folder) and `/etc/dnsmasq.d/modul-paylasim.conf`.
    Both are validated before Caddy reloads and dnsmasq restarts.
  - Stage 7's WebDAV checks moved into `master-modul`, which also proves the
    account with a `PROPFIND` (207) and takes a failed install back.
  - Dosyalar shows the share controls only while the module is installed, and
    warns when it is stopped. The file backend refuses a new share without the
    module and no longer holds the account (`LoadCredential` removed).
- **Fixed:** the share dialog retried forever when the share list could not
  be loaded; the list stayed on screen after the share went away; the
  unshare dialog showed `/downloads/…` instead of the real path.
- **Added:** Günlük names module actions and has a **Modüller** filter.
- **Operator steps:** delete the `SHARE_USER=` and `SHARE_PASS=` lines from
  `kurulum/kurulum.env` (the installer stops on an unknown key before
  changing anything); after the install, add Paylaşım from Konsol and enter
  its new account in Infuse.

### 2026-09-16 — Konsol installs modules; the archive extractor is the first (v2-115)

- **Added** (**DD-148**): Konsol → **Modüller**. A clean install now brings
  the base only, and optional parts are installed, started, stopped and removed
  from this page with one click. This release lays the groundwork and moves the
  first module; Paylaşım, Dosya yöneticisi, WireGuard and qBittorrent follow.
  - `master-modul` (root helper, `/usr/local/sbin`) knows a fixed catalogue and
    four verbs: `kur`, `baslat`, `durdur`, `kaldir [--veri]`, plus `liste` and
    `gunluk`. Nothing else is accepted.
  - The root backend starts each operation with `systemd-run` as its own unit
    (`master-modul-<id>.service`): closing the page does not stop it, and a
    second request for the same module gets `409` while it runs. Progress is
    one line in `/run/master-stack/modul-<id>.ilerleme`; the page follows it.
  - Installed modules live in `/etc/master-stack/moduller` (`id`, `calisiyor` or
    `durduruldu`). The installer writes module files to
    `/usr/local/share/master-stack/moduller/<id>/` and an empty registry; it
    never installs a module. On a re-run a changed module file restarts that
    module only if it is running.
  - A card shows the module's state, its steps while installing, a **Günlük**
    panel (last 80 lines) and, on removal, an option to delete the module's own
    data too. User files are never part of that.
- **Changed** (**DD-148**): **Arşiv açıcı** (Unpackerr) is a module. It left the
  base Compose file, which now has three services, and runs as its own Compose
  project `unpackerr` with the same image, mounts and hardening. Stage 7 no
  longer checks it; `kur` checks that the container sees neither the trash nor
  the share folder. Removing it with data empties `/srv/downloads/.unpackerr`.
  A re-run on a host with the old container removes it (`--remove-orphans`);
  install it again from Konsol if wanted.
- **Changed:** Caddy serves the Konsol pages itself (`file_server` from
  `/usr/local/share/master-stack/konsol`, with the CSP, `no-store`, `nosniff`,
  `X-Frame-Options` and referrer headers). The file backend serves only
  `/api/*`; `/api/wg/*` and `/api/konsol/*` go to the root backend.

### 2026-09-16 — FileBrowser is gone, Konsol needs no password, Tailscale joins by link only (v2-114)

- **Removed** (**DD-146**): the `filebrowser` container. Konsol's Dosyalar page
  now uploads, selects many items and searches (v2-113), which were the last
  things FileBrowser was installed for.
  - Gone with it: the `FILEBROWSER_USER` / `FILEBROWSER_PASS` input keys, port
    61007, the image, the Bolt database and its account create/sync code
    (~150 lines of the installer), and four tests.
  - `file.<domain>` stays as a name and redirects to the console, like `wg.`
    and `dosya.`.
  - WireGuard networks with "Local erişim" now reach Dozzle and qBittorrent
    only. Files are not reachable over WireGuard: Konsol stays tailnet-only.
  - Compose has four services. A re-run on a host that still runs the old
    container removes it (`--remove-orphans`); `/etc/master-stack/filebrowser-data`
    is left for the operator to delete.
- **Removed** (**DD-147**): the Konsol password. Access is tailnet-only and that
  is the boundary; narrowing it is a Tailscale ACL matter.
  - Gone: `WG_PANEL_USER` / `WG_PANEL_PASS`, the PBKDF2 account file
    (`/etc/master-stack/wg-panel.auth`), HTTP Basic, the 10-failure lockout,
    `master-wg-panel account`, and the `LoadCredential` that fed the file backend.
  - Kept and now load-bearing: the `Host` allowlist (DNS rebinding) and the
    `X-Konsol` header + same-origin check on `/api/*` (CSRF). Stage 7 proves
    both gates on both backends; the old "401 without the account" check is gone.
  - The audit log records the actor as `konsol` plus the client address.
- **Removed** (**DD-147**): the Tailscale auth key. `TS_AUTH_KEY`, the key file
  under `/run`, `--auth-key`, the fallback path and `TS_AUTHKEY_LOGIN_SECONDS`
  are gone; stage 2 always prints the login link and waits.
- **Fixed** (**DD-145**): an upload refused before its body was read (existing
  name, trash or share folder, missing folder) reached the browser as `502`
  through Caddy: the backend closed the connection with the body unread. It now
  drains the body (up to 256 MB) before answering `409`/`403`/`404`, and the
  console does not send a file whose name is already in the folder. Verified on
  `nrm` with 20 MB bodies through Caddy, three times each.
- **Operator step:** delete the `FILEBROWSER_USER=`, `FILEBROWSER_PASS=`,
  `WG_PANEL_USER=`, `WG_PANEL_PASS=` and `TS_AUTH_KEY=` lines from
  `kurulum/kurulum.env`; the installer stops on an unknown key before changing
  anything.
- **Fixed:** the `## [Unreleased]` heading above the v2-112/v2-113 entry, lost
  in the previous commit.

### 2026-09-16 — The user area is /srv and the console uploads into the list (v2-112, v2-113)

- **Changed** (**DD-144**, v2-112): the downloads path is no longer asked. The
  user area is the fixed `SERVER_ROOT=/srv` — FHS calls `/srv` the place for
  "site-specific data which is served by this system", and Debian Policy keeps
  packages out of it, which is exactly what this folder is.
  - Layout: `/srv/downloads` (qBittorrent writes here, with `incomplete/` and
    `.unpackerr/`), `/srv/media/{movies,series}`, `/srv/.cop` (trash),
    `/srv/.pay/w` (share root).
  - `qbittorrent` and `unpackerr` mount only `/srv/downloads`; FileBrowser and
    the share mount `/srv`. Because the trash and the share root are now
    *outside* the downloads folder, the tmpfs curtain that used to hide them
    from unpackerr is gone — stage 7 checks the containers cannot see them.
  - **Removed**: the `DOWNLOADS_PATH` input key. Delete that line from
    `kurulum/kurulum.env`; the installer stops on an unknown key before
    changing anything.
- **Added** (**DD-145**, v2-113): the console's Dosyalar page does what
  FileBrowser was there for.
  - **Upload**: drop files onto the list itself — there is no separate upload
    area. They appear as rows with progress in the row, and settle into the
    listing when done. `POST /api/upload` writes a temp name and renames it
    into place; an existing name is refused, a half file never appears.
  - **Multi-select**: row checkboxes (Shift for a range) turn the toolbar into
    an action bar — download, move, share, move to trash. Move and trash go in
    one request. `Esc` clears the selection.
  - **Search** filters the current folder as you type; the counter shows the
    number of matches.
  - A left rail replaces the old cards: the root, the top-level folders
    (`downloads`, `media`), Paylaşımlar, Çöp and the disk meter.
  - qBittorrent's own folder (`downloads/incomplete`) cannot be selected or
    shared, and still warns before a move or delete.
  - Design: `docs/design/konsol-dosyalar-v02.html`.

### 2026-09-16 — Nothing the installer writes describes a preset WireGuard network (v2-111)

- **Changed** (**DD-143**): the settings the installer writes carry only the
  layer, never a network. `state.env` had kept `wg0`'s own values from the era
  when the installer created it.
  - `WG_CONF_FILE=/etc/wireguard/wg0.conf` became `WG_CONF_DIR=/etc/wireguard`:
    a network's file name is derived per network by `master-wg`, not stored.
  - `WG_SERVER_IPV4` / `WG_SERVER_IPV6` / `WG_SUBNET4` / `WG_SUBNET6` became
    `WG_ADDR_BASE4="10.8"` and `WG_ADDR_BASE6="fdcc:ad94:bacf:61a4"`. The two
    subnet keys were dead: a selected network always overwrote them from its
    registry line. A network's addresses exist only in the registry.
  - `WG_PUBLIC_PORT` became `WG_PORT_DEFAULT`, and it is no longer written to
    `config.env`, where a port saved by an older run silently became the next
    run's suggestion.
  - `caddy-wg@.service` said the installer writes `caddy-wg-wg0.env`; only
    `master-wg` writes it, when the network is created.
  - `wireguard.command` no longer reads the server's config paths from
    `defaults.env` — nothing on the Mac has used them since the backup went.
  - Removing a network already left nothing behind (checked on `nrm`: no
    interface, conf, profile directory, unit link, firewall rule or route);
    this makes the same true of the settings files.
- **Docs**: the contract, architecture, README and `OKUBENI.txt` still described
  the installer creating `wg0`, restoring it from the Mac and refusing to remove
  it. They now describe the layer-only install, per-network files and the
  backup-free menu.

### 2026-09-16 — Every network card can be removed, wg0 included (v2-110)

- **Changed** (**DD-143**): the console's WireGuard cards all carry the same two
  actions — regenerate (↻) and remove (🗑). `wg0` was the last place where the
  installer's old ownership showed; it is a network like any other now. Removing
  the last one asks for `onayla`, says so in the confirm list, and leaves the
  page on "WireGuard yapılandırılmadı → Yapılandır".

### 2026-09-16 — The installer no longer creates WireGuard; Konsol does (v2-109)

- **Changed** (**DD-143**): a fresh install leaves WireGuard empty. The
  installer only prepares the layer (tools, kernel module, `/etc/wireguard`) and
  applies whatever the registry already holds. The first network — like every
  other — is created from Konsol: **WireGuard → Yapılandır**, which opens the
  existing "Arayüz ekle" page (wg0, 10.8.0.0/24, UDP 61001 by default).
  - `wg0` lost its special status: every network, including the first, lives in
    `/etc/wireguard/networks`, is created by `master-wg net-add`, can be
    switched off and removed, and keeps its profiles in `clients-wg<N>`.
  - The firewall builds WireGuard rules from the registry only and is valid
    with no networks at all.
  - **Removed**: the Mac-side link. No snapshot of `wg0.conf` and profiles is
    read from `kurulum/wireguard`, nothing is uploaded to the server, and
    `WG_PUBLIC_PORT` is no longer an input key. The launcher sends only
    `kurulum.env`.
  - `wireguard.command` keeps managing peers over SSH: it now picks the network
    (tek ağ varsa kendiliğinden), has no "Yedek al" and no auto-backup, and its
    option 8 regenerates the selected network.
  - **Rebuilding a server therefore starts with no WireGuard**: create the
    network in Konsol and add the devices again.

### 2026-09-16 — One rclone, and the downloads folder is no longer published (v2-108)

- **Changed** (**DD-142**): the WebDAV that served all of `DOWNLOADS_PATH` is
  gone. The only WebDAV left is the share (`paylas.<domain>`, port 61010): it
  serves the share root, so nothing leaves the server unless it was shared from
  Konsol. Infuse connects to that address with the share account.
  - Removed: the `webdav` container, `webdav.<domain>`, port 61003, the
    `WEBDAV_USER` / `WEBDAV_PASS` / `WEBDAV_PORT` input keys and
    `webdav.htpasswd`. `kurulum.env` now carries one WebDAV account
    (`SHARE_USER` / `SHARE_PASS`).
  - `docker compose up` now runs with `--remove-orphans`, so a service removed
    from the file does not stay up.
  - **Manual step after upgrading:** re-add the source in Infuse — address
    `http://paylas.<domain>` (or `http://<tailscale-ip>:61010`) with the share
    account; the old `webdav.<domain>` entry stops working.

### 2026-09-16 — The share also answers on IP:port, for Infuse (v2-107)

- **Added** (**DD-141**): besides `http://paylas.<domain>`, the share answers on
  `http://<tailscale-ip>:61010` — the same second address the Infuse WebDAV has
  had since **DD-98**, for clients that cannot resolve the MagicDNS name (seen
  live: an Apple TV). The console shows both, with a copy button each.

### 2026-09-16 — Share links over one read-only WebDAV (v2-106)

- **Added** (**DD-141**): a folder or a file can be shared from Konsol's
  Dosyalar page. Everything shared appears side by side at
  `http://paylas.<domain>` — one address, one account (`SHARE_USER` /
  `SHARE_PASS` in `kurulum.env`), read-only, tailnet only.
  - Sharing puts a relative symlink into the share root
    (`DOWNLOADS_PATH/.pay/w`); nothing is copied, and a file that lands in a
    shared folder later shows up by itself.
  - Duration per share: 1, 7 or 30 days, or open-ended. An expired share drops
    off the list and its link is removed; the files themselves are untouched.
  - The console shows the address, user and password with a reveal and copy
    button, and lists the active shares with when they were added and how long
    they have left.
  - A second rclone container (`paylasim`) serves it: `--read-only`,
    `--copy-links`, the downloads folder mounted read-only, and the account as
    a bcrypt htpasswd. Infuse and Unpackerr see the share folder as an empty
    read-only tmpfs, like the trash.
- **Fixed**: a service whose configuration file is newer than the service's own
  start is restarted even when the file did not change in this run. A run that
  died between rendering and restarting (seen live) otherwise left dnsmasq or
  Caddy serving the previous configuration for good.

### 2026-09-16 — Konsol: one admin console for WireGuard and files (v2-105)

- **Added** (**DD-140**): `http://panel.<domain>` — a single console that
  replaces the separate WireGuard and file pages. `wg.<domain>` and
  `dosya.<domain>` redirect to it, and one browser login covers both.
  - **Genel bakış**: a server card (CPU and memory graphs of the last two
    minutes, a disk bar split into downloads, trash and system, plus system,
    WAN and version), the connected WireGuard devices, the last actions, and a
    card listing every port in use, grouped by where it can be reached.
  - **WireGuard**: networks as cards with a lever switch, regenerate and
    remove; peer rows with their own switch, QR, delete and an edit dialog for
    DNS (Cloudflare, Cloudflare Aile, Quad9, AdGuard, Google or custom) and
    keepalive; "Arayüz ekle" opens as its own page.
  - **Dosyalar**: the downloads folder with a path bar, new folder, rename,
    move, download, a text viewer and the trash (restore, permanent delete,
    empty with `onayla`).
  - **Günlük**: what the console changed, from both backends' audit lines.
- **Added** (**DD-140**): a peer and a whole network can be switched off and on
  from the console. `master-wg peer AD ac|kapat` comments the peer's block out
  of the interface configuration (keys, address and profile stay, and it stays
  off across a reboot); `master-wg [--if wgN] net ac|kapat` stops or starts the
  interface. `master-wg keepalive AD SANİYE` changes the profile's
  `PersistentKeepalive`.
- **Changed**: the WireGuard backend serves no page any more and answers only
  under `/api/wg/*`; the file backend serves the console pages. Both use the
  `X-Konsol` header and the realm `Konsol`, and accept only the host
  `panel.<domain>`. `master-wg info` gained an eleventh field: whether the peer
  is switched on.

### 2026-09-15 — File panel for the downloads folder (v2-104)

- **Added** (**DD-139**): `http://dosya.<domain>`, a file manager for
  `/downloads` in the WireGuard panel's look.
  - Browse with a path bar, filter, sort, hidden files, and a list or icon view
    that the browser remembers.
  - Operations: new folder, rename, move (a folder picker, or drag and drop),
    download.
  - Delete moves items to a trash on the same disk. The trash restores items to
    where they were, deletes a single item permanently, and is emptied after
    typing `onayla`.
  - Text files (`.txt`, `.log`, `.nfo`, `.srt`, …) open read-only: the first
    1 MiB, encoding guessed (UTF-8, Windows-1254, CP437 for `.nfo`) or chosen,
    with previous/next file.
  - A switch at the top of both panels moves between WireGuard and Dosyalar.
- **Access:** tailnet only, with the WireGuard panel's account (no new input
  keys). The service runs as the downloads uid (not root) and can write only to
  `/downloads`.
  - The installer creates the system account `master-downloads` (no login)
    when that uid has no name.
- **Changed:**
  - `unpackerr` and `webdav` mount an empty read-only tmpfs over
    `/downloads/.cop`, so archives in the trash are not extracted again and
    Infuse sees only an empty folder.
  - Stage 7 checks the panel: 401 without login, opens with the account, runs as
    the downloads uid, nothing on the WireGuard address, trash hidden in both
    containers.
- **Unchanged:** FileBrowser stays.
- **Verified:**
  - bats 152 ok, with ten mutations caught.
  - Live on `nrm`: the install passed stage 7. Over Tailscale and Caddy: a link
    to `/etc` was listed but not followed. Rename onto an existing file was
    refused by `renameat2`. A Windows-1254 subtitle and a CP437 `.nfo` were
    decoded, and a download worked. A folder with a zip went to the trash and
    unpackerr did not extract it; restore, purge and empty worked. After a
    reboot the panel came back; the real accounts were restored.

### 2026-09-15 — Server IPv6 detected and stored; no fixed IP anywhere (v2-103)

- **Added** (**DD-138**): the installer also detects the server's global IPv6
  from its own routing table and writes `WAN_IPV6` to `state.env` (empty when
  the server has none). The summary's WAN line shows it.
- **Unchanged:** profiles and the panel keep the IPv4 endpoint,
  `WG_ENDPOINT_HOST`, which is still detected on every run (`ip route get`),
  never typed. The WireGuard port stays open on IPv4 only, so the IPv6 address
  is recorded, not offered as an endpoint. After an IP change, re-run the
  installer and give the devices new profiles; stage 5 warns about profiles
  with the old endpoint.
- **Tests:** the real server address in test fixtures was replaced with the
  documentation address `203.0.113.7`. A new test checks detection and that
  no public IP literal is left in the installer, `master-wg`, the panel or
  `defaults.env`.
- **Verified:** bats 147 ok.

### 2026-09-15 — Panel "Bağlı" follows traffic, not the handshake (v2-102)

- **Fixed** (**DD-137**): a peer that had disconnected stayed "Bağlı" for up
  to three minutes, because the status came from the last handshake. Now a
  peer is "Bağlı" only while data keeps arriving from it: its received bytes
  grew within the last 45 s and its handshake is under 3 minutes old.
- **Changed:** the panel samples every network every 10 s in the background,
  so the status does not depend on the page being open. Until a peer has been
  watched for 45 s, the handshake decides as before.
- **Verified:**
  - bats 146 ok, including a test that stops the traffic and waits for the
    peer to fall back to "Boşta".
  - Live on `nrm` with the Mac as a real peer: "Bağlı" 2–5 s after
    connecting, "Boşta" 47–48 s after disconnecting (was up to 3 minutes).

### 2026-09-15 — More WireGuard networks from the panel (v2-101)

- **Added** (**DD-136**):
  - "Arayüz ekle" in the panel creates `wg1`…`wg9`, each in its own tab with
    its own key, UDP port and addresses (`10.8.N.0/24`,
    `fdcc:ad94:bacf:61a4::N:0/112`).
  - Choose per network: internet only, or internet plus Dozzle, qBittorrent
    and FileBrowser on that network's server address.
  - Networks never see each other.
  - Each tab adds, removes and shows peers, changes DNS and regenerates its
    key. Extra networks can be removed with `onayla`.
  - `master-wg --if wgN`, `master-wg nets`, `net-add` and `net-remove` on the
    server.
- **Changed:**
  - The firewall builds and checks rules for every network.
  - `caddy-wg` became `caddy-wg@<interface>`.
  - The panel's API routes are now per network.
- **Removed:** the panel's "Mac yedeği" indicator and the backup marker file;
  `wireguard.command` is managed separately (`wg0` only).
- **Fresh install:** a server installed before v2-101 keeps its old
  `caddy-wg.service`, which clashes with `caddy-wg@wg0`; install on a fresh
  server.
- **Verified:**
  - bats 145 ok, with mutations caught.
  - Live on `nrm`: two networks were created from the panel. Namespaced
    WireGuard clients reached the internet and only their own allowed ports,
    and not the other networks. A network was removed, and everything came
    back after a reboot.
  - The page was checked in a browser.

### 2026-09-15 — Panel layout and the "onayla" confirmation (v2-100)

- **Changed** (**DD-134**):
  - Regenerating `wg0` is confirmed by typing `onayla` (any case) in both the
    panel and `wireguard.command` option 8. "SIL" no longer works.
  - The panel's regenerate section is a compact single row.
  - Table columns are resized: DNS and address get more room, headers stay on
    one line, and an address is never split across lines.
- **Changed** (**DD-135**): WireGuard IPv6 addresses no longer carry `cafe`.
  The server is `fdcc:ad94:bacf:61a4::1/112` and peers are `…::2`, `…::3`, …
  The snapshot check now accepts only a host number after the prefix.
- **Not migrated** (fresh install only): delete `kurulum/wireguard` (its
  `cafe` backup is refused), reset the server, install v2-100 and add the
  devices again.
- **Verified:**
  - bats 143 ok, with four mutations caught.
  - The page was checked in a browser with sample peers.
  - The old backup was refused as expected.

### 2026-09-15 — WireGuard web panel on the tailnet (v2-99)

- **Added** (**DD-133**): `http://wg.<domain>` — manage `wg0` peers from a
  browser. You can list them with status, handshake and traffic, add, remove,
  show the QR code (hidden until asked, hidden again after 60 s), download the
  profile or QR picture, change DNS and regenerate `wg0` after typing `SIL`.
  The page warns when the Mac backup is older than the last change.
- **Access:** tailnet only, with the new `kurulum.env` account
  `WG_PANEL_USER` / `WG_PANEL_PASS` (password at least 12 characters). **Add
  both lines before running v2-99**; the installer stops without them.
- The panel runs on the server (`master-wg-panel`, Python standard library,
  `127.0.0.1:61008`) and makes every change through `master-wg`.
  `wireguard.command` keeps working as before.
- Also:
  - `master-wg info`;
  - the menu's backup leaves a marker the panel reads;
  - stage 7 checks the panel with the input account.
- **Verified:**
  - bats 143 ok, with thirteen mutations caught.
  - Installed live on `nrm`: the panel was exercised through Caddy (add,
    duplicate, masked and full profile, QR, DNS, remove, refused reset) with
    `wg0` left byte-identical. The reset and the interface-restart path ran
    under the same sandbox on a throwaway interface.
  - The page was checked in a browser against sample data.

### 2026-09-15 — Fix: backup failed on a server with no peers (v2-98, menu only)

- **Fixed:** the backup script ended its `tar` command with `-C <temp dir>`
  even when there was no PNG to add. GNU tar 1.35 on the server rejects a
  `-C` with no member after it (exit 2), so the backup failed whenever the
  server had no profiles: after "8) wg0 yeniden üret" or removing the last
  peer. The Mac kept the old `wg0.conf`, profiles and pictures (**DD-132**).
  The `-C` part is now added only when there are pictures.
- The script is sent from the Mac at run time: no installer re-run is needed.
- **Verified:** a test now runs the script with a `tar` that rejects a
  trailing `-C` like GNU tar, with and without profiles; the old script
  fails it. On `nrm` (0 peers) the fixed script exited 0 and sent only
  `wg0.conf`. Option 6 then removed the operator's 3 stale profiles and 4
  pictures and wrote the new `wg0.conf` (0 peers). bats 137 ok.

### 2026-09-15 — QR code saved as PNG next to each WireGuard profile (v2-98)

- **Added** (**DD-132**):
  - `wireguard.command` saves `kurulum/wireguard/<name>.png` (mode 600)
    with every profile it saves: add, DNS change and the QR display refresh.
  - The backup (option 6 and the automatic one) pulls a PNG for every
    profile and removes pictures whose profile is gone.
  - `master-wg png NAME` on the server writes the PNG to a pipe; it refuses
    a terminal.
- The picture holds the client key, like the profile: keep it private. It is
  never sent to the server.
- Re-run the installer once (v2-98): the menu requires the same version on
  the server. Then run option 6 to create pictures for existing peers.
- **Verified:** bats 137 ok, eight mutations caught. Tested on `nrm` with a
  throwaway interface; the PNG decoded on the Mac to the exact profile.

### 2026-09-14 — WireGuard client DNS default: Cloudflare IPv4 first (v2-97, menu only)

- **Changed:** the DNS offered for a new peer is now
  `1.1.1.1, 1.0.0.1, 2606:4700:4700::1001` (was
  `1.1.1.1, 2606:4700:4700::1111`), based on measurements from `nrm`: IPv6
  pinged 0.5 ms lower, but about half its DNS answers took 12 ms or more,
  against under 7 ms over IPv4 (**DD-131**).
- Existing peers keep their DNS; change it with `wireguard.command` → 7.
- The installer is unchanged (still v2-97, re-exported); no re-run is needed.
- **Verified:** bats 135 ok; two mutations caught.

### 2026-09-14 — wireguard.command backs up after every change (v2-97, menu only)

- **Changed:** options 2 (add), 3 (remove) and 7 (DNS) take the backup
  (option 6) themselves after a successful change, like option 8. The
  "6) Yedek al" reminders are gone; option 6 stays for a manual backup
  (**DD-130**).
- The installer is unchanged (still v2-97): no re-run is needed.
- **Verified:** bats 135 ok; five mutations caught.

### 2026-09-14 — wireguard.command: change DNS, regenerate wg0 (v2-97)

- **Added** (**DD-130**):
  - Option 7 "DNS değiştir" changes one peer's DNS and keeps its keys and
    address. The current DNS is the default. The menu prints the new QR code
    and saves the new profile; import it on the device.
  - Option 8 "wg0 yeniden üret" issues a new server key and deletes every
    peer and profile. It runs only after you type `SIL`, then takes a backup
    (option 6) so `kurulum/` does not keep the old key.
  - `master-wg dns NAME DNS` and `master-wg reset --onay` on the server.
- Re-run the installer once: the menu requires the server to run the same
  version.
- **Verified:** bats 134 ok, with five mutations caught; both commands were
  run on `nrm` against a throwaway `wgtst0` interface, leaving `wg0`
  untouched.

### 2026-09-14 — Cleanup of transition code and stale references (v2-96)

- **Removed** (no host needs them after the v2-95 rebuild; **DD-96**):
  - the stage 0 Transmission leftover gate and the `TRANSMISSION_*`
    removed-key hint;
  - the stage 7 Portainer warning;
  - the v2-73 sysctl file-name migration;
  - the "no OS record (v2-73)" log branch.
- **Fixed:**
  - The downloads tree line now reports how many entries were actually
    fixed ("… girdinin sahibi ya da izni düzeltildi") and otherwise says
    ownership and modes are in place. It used to claim a repair on every run.
  - `V2_LOG_FILE` is exported, so the full apt output of the dnsmasq/Caddy
    installs (run by `retry` in a child bash) reaches `install.log`.
- **Changed:**
  - Comments no longer describe the WireGuard addresses as wg-easy's.
  - `optimization-review.md` and `os-aware-review.md` moved to
    `docs/archive/` with a historical note.
  - README drops the stale tag line and the `backup/` note.
- **Repository:**
  - Deleted: the empty `backup/` folder (and its `.gitignore` entry), the
    `wip/bats-negation-v2-84` and `claude/magical-shannon-e0b514` branches and
    their worktree.
  - Removed: the exports v2-79 to v2-95 from `Data/app/`, which Git history
    already holds.
- **Verified:** bats 131 ok; shellcheck clean.

### 2026-09-14 — WireGuard backup moves into wireguard.command (v2-95)

- **Changed:** `ayarlar.command` is removed. Its pull of the WireGuard server
  config and profiles is now option 6 "Yedek al" of `wireguard.command`, with
  the same behaviour: no content printed, files mode 600, profiles mirrored,
  and an old `kurulum/qbittorrent/` copy deleted (**DD-128**).
  - After adding or removing a peer, the menu reminds you to take a backup.
- **Fixed:** the menu's master-wg calls use `ssh -n`, so ssh can no longer
  swallow queued menu input.
- The installer's summary now points to option 6. Re-run the installer once:
  the menu requires the server to run the same version.
- **Verified:**
  - bats 132 ok, and three mutations were caught.
  - On `nrm`, option 6 pulled `wg0.conf` and 4 profiles byte-identical to the
    operator's existing copy; a second backup reported "aynı".

### 2026-09-14 — qBittorrent configured by the installer: template + kurulum.env account (v2-94)

- **Added:** `TORRENT_USER` and `TORRENT_PASS` in `kurulum.env` (required; add
  both lines) (**DD-129**).
- **Added:** `Data/templates/qBittorrent.conf`, the operator's qBittorrent
  settings taken from a diff against a clean file. Every run keeps those keys
  and the account in sync:
  - When nothing differs, nothing is written and nothing restarts.
  - When something differs, only the differing keys are fixed, with
    qBittorrent stopped around the write.
  - The password is stored only as qBittorrent's PBKDF2 hash.
- **Added:** stage 7 logs in with the input account and checks that
  authentication cannot be bypassed.
- **Removed:** pulling and restoring qBittorrent's file (`ayarlar.command`
  now handles WireGuard only and deletes an old `kurulum/qbittorrent/` copy).
- **Verified on `nrm`:**
  - Existing server synced (only the account and auth guards differed).
  - No-op re-run.
  - A UI change reverted.
  - A fresh config came up with every template value and no temporary
    password.
  - A no-op after qBittorrent rewrote its own file.
  - bats 132 ok.

### 2026-09-14 — Pulled settings rebuild a server: ayarlar.command (v2-93)

- **Added:** `ayarlar.command` at the repository root. It pulls into
  `kurulum/`, mode 600, without printing anything (**DD-128**):
  - the WireGuard server config (`wireguard/sunucu/wg0.conf`: key and peers);
  - the device profiles;
  - qBittorrent's `qBittorrent.conf` (settings and account). Categories, RSS
    and watched folders are not pulled.
- **Changed:** the installer `.command` sends those files with `kurulum.env`.
  On a fresh server the installer puts them back, and only where the server
  has none:
  - the same WireGuard key and peers, so devices reconnect untouched;
  - qBittorrent configured with its account.
  A server that already has its own files keeps them.
- **Security:** the files are validated before any change. A WireGuard file
  with `PostUp`-style lines, foreign fields, out-of-subnet addresses or bad
  keys stops the install.
- **Verified on `nrm`:**
  - The pull.
  - A run over an existing server that left everything untouched.
  - A fresh simulation restored identical keys, peers and the qBittorrent
    account; the Mac's unchanged tunnel reconnected.
  - bats 128 ok.

### 2026-09-14 — qBittorrent returns, configured in its own web UI (v2-92)

- **Changed:** the torrent client is qBittorrent again
  (`lscr.io/linuxserver/qbittorrent:latest`, 5.2.3), replacing Transmission
  (**DD-127**). The UI address (`torrent.${LOCAL_DOMAIN}`, `10.8.0.1:61006`),
  the peer port 61005 and Unpackerr are unchanged.
- **Changed:** the installer writes no torrent settings and no account.
  - On a first install, log in as `admin` with the temporary password from
    the `qbittorrent` log in Dozzle.
  - Then set the account and preferences in the UI.
- **Removed:** `TRANSMISSION_USER` and `TRANSMISSION_PASS` from `kurulum.env`.
  Delete both lines; if they remain, the installer names them and stops.
- **Added:**
  - Stage 7 requires qBittorrent's API to answer `403` without a login, which
    catches an authentication bypass.
  - A leftover `transmission` container stops the installer before any change
    (`docker rm -f transmission`).
- **Verified on `nrm`:**
  - The old keys and the leftover container were refused.
  - A switch from Transmission exited 0; the UI, API and peer port checks
    passed and the WireGuard peer was kept.
  - A re-run was a no-op.
  - bats 123 ok.

### 2026-09-14 — Negated test assertions that can fail, dead WebDAV migration removed (v2-91)

- **Removed:** stage 6 no longer recreates `webdav` when it still publishes
  `${TAILSCALE_IPV4}:${WEBDAV_PORT}`. Only the uncommitted v2-65 tree
  published that port, and migration cleanup is outside the installer's
  boundary (**DD-96**).
- **Fixed (tests):** under macOS `/bin/bash` 3.2 a `! cmd` or `[[ ]]` never
  failed a test, so most negative assertions checked nothing (**DD-126**).
  - All 115 are now `run !`, `[ ]` or `case`.
  - A guard test keeps bare negations out.
  - Four assertions that matched comments or operator messages now check code
    lines only. The fifth exposed the stage 6 step above.
- **Verified:**
  - bats 123 ok, 3 skipped as before.
  - Every negated command returned exactly 1.
  - Six mutations were caught.

### 2026-09-14 — Smaller install footprint (v2-90)

- **Changed:** Docker is installed without its recommended packages: no
  buildx, git/perl or rootless extras. `apparmor` and `pigz` are named
  explicitly (**DD-125**).
- **Changed:** apt no longer keeps the `.deb` files the installer downloads
  (`APT::Keep-Downloaded-Packages=false`), about 300 MB.
- **Removed:** `debian-keyring`. The Caddy repo is verified by its own
  keyring.
- **Fixed:** the dnsmasq and Caddy installs never received the apt options,
  such as the dpkg lock timeout, because `retry` runs them in a child shell.
- A fresh install uses about 450 MB less disk (2389 → 1940 MB on `nrm`).
  Existing hosts keep what they already have.
- **Verified on `nrm`:**
  - Fresh-path simulation with Docker, Caddy and dnsmasq purged, exit 0.
  - A no-op re-run.
  - Real accounts restored afterwards.
  - bats 122 ok.

### 2026-09-14 — WireGuard peers generated on the server, managed from wireguard.command (v2-89)

- **Added:**
  - `wireguard.command` at the repository root: list peers with their last
    handshake and transfer, add a peer (name, DNS, keepalive, MTU), remove
    one, show a QR code. The peer is generated on the server, the QR code
    is printed and the profile is saved to `kurulum/wireguard/<name>.conf`.
    Nothing is sent to the server (**DD-124**).
  - `master-wg` on the server does the work: `wg genkey`/`wg pubkey`/
    `wg genpsk`, the next free address, a `[Peer]` block applied with
    `wg syncconf`, and the profile kept in `/etc/wireguard/clients/`.
- **Changed:** the installer manages only `[Interface]` in `wg0.conf`. It
  generates the server key on a first install and keeps the key and every
  peer on re-runs. A reinstall starts with a new key and no peers.
- **Removed:** `WG_PEERS`, `WG_CLIENT_DNS`, `WG_CLIENT_KEEPALIVE` and
  `WG_CLIENT_DNS_OVERRIDE` from `kurulum.env` (delete those lines), and sending
  `kurulum/wireguard` to the server and fetching profiles back.
- **Fixed:** `state.env` quotes `WG_CLIENT_ALLOWED_IPS`, whose space broke
  sourcing the file.
- **Verified on a freshly reset `nrm`** with the operator's folder:
  - A fresh install (exit 0).
  - Two peers added from the menu, one with defaults and one with custom DNS,
    keepalive and MTU, each with a QR code and a saved profile; a duplicate
    name refused.
  - A generated profile working as a real client, with the internet and the
    UIs reachable and SSH, WebDAV, the tailnet and other peers blocked.
  - A removal from the menu.
  - A re-run and a reboot that kept the peers.
  - bats 120 ok.

### 2026-09-14 — WireGuard changes applied live (v2-88)

- **Changed:** adding or removing a peer, a PSK, the port or the server key
  is applied to the running interface with `wg syncconf`, the kernel
  WireGuard way. Connected devices and `caddy-wg` stay up. `wg-quick@wg0`
  restarts only when it is not running, when its address or MTU changes, or
  when `syncconf` fails (**DD-123**).
- **Verified on `nrm`:** removing a peer from `WG_PEERS` removed it live;
  `wg-quick@wg0` and `caddy-wg` did not restart, and the next run was a
  no-op.

### 2026-09-14 — container-backup retired

- **Removed:** `container-backup.command`, its worker, its document and its
  round-trip test (**DD-122**). Since v2-86 every setting it carried comes
  from `kurulum/`; keep that folder safe instead. Old archives in `backup/`
  stay Git-ignored and are no longer read.

### 2026-09-14 — WireGuard peers from kurulum.env (v2-87)

- **Changed:** `kurulum.env` lists the peers (`WG_PEERS`) and sets the DNS,
  PersistentKeepalive and per-peer DNS overrides for every profile. A listed
  peer without a `kurulum/wireguard/<name>.conf` gets a new key, PSK and the
  next free address on the server; the first install also generates
  `sunucu.key` (**DD-121**).
- **Added:**
  - New and changed profiles are handed back to `kurulum/wireguard/` by the
    launcher after the install, and deleted from the server afterwards.
  - A new peer's QR code is printed in the terminal.
  - Stage 0 rejects bad names, DNS lists, keepalive values and overrides for
    unknown peers, and warns about profiles not in `WG_PEERS`.
- **Changed:** `kurulum/wireguard/` is optional in the launcher.

### 2026-09-14 — Kernel WireGuard replaces wg-easy (v2-86)

- **Changed:**
  - WireGuard runs in the host kernel (`wg-quick@wg0`) with wg-easy's
    addresses and port, so existing client profiles connect unchanged
    (**DD-120**).
  - Peers come from `kurulum/wireguard/<device>.conf` (wg-easy's profile
    format) and the server key from `kurulum/wireguard/sunucu.key`. The
    launcher sends them with `kurulum.env` to `tmpfs`, and the installer
    deletes them first.
  - `wg0.conf` holds public keys and PSKs only, and changes only when the
    profiles do.
- **Added:**
  - WireGuard clients reach the Dozzle, Transmission and FileBrowser UIs at
    `http://10.8.0.1:<port>` through a second Caddy (`caddy-wg`) that does not
    depend on Tailscale.
  - New firewall chains: `MASTER-FORWARD` lets clients out to the internet and
    nowhere else (no tailnet, Docker networks or other peers), and `MASTER-NAT`
    masquerades both subnets. `MASTER-INPUT` limits `wg0` to the three UI ports
    and ping. `--check` asserts rules, order and count.
  - Stage 0 rejects malformed profiles, duplicate addresses or keys and a
    wrong endpoint port. Stage 7 checks the port, the peer count and the
    three UI ports.
- **Removed:**
  - The `wg-easy` container, its network and settings.
  - `wg.${LOCAL_DOMAIN}` from dnsmasq and Caddy.
  - The legacy netfilter modules wg-easy needed.
- **Verified on `nrm`:**
  - The four device profiles were generated from wg-easy's database and
    matched its running peers. wg-easy was removed and v2-86 installed with
    the operator's `kurulum/` folder (Tailscale logged back in with its auth
    key).
  - A namespace test peer reached the internet over IPv4 and IPv6 and the
    three UIs, and was refused SSH, WebDAV, the tailnet, Docker networks and
    other peers.
  - A second run was a no-op, and a reboot came back clean.
  - A real device connected with its unchanged profile and opened Dozzle at
    `http://10.8.0.1:61002`.
  - bats 119 ok.

### 2026-09-14 — Installer inputs from one file (v2-85)

- **Changed:**
  - Stage 0 no longer asks for anything it needs to configure. The domain,
    downloads path, ports, the WebDAV, Dozzle, Transmission and FileBrowser
    accounts and the optional Tailscale auth key come from
    `kurulum/kurulum.env` beside the `.command` in the repository root. The
    file is git-ignored and must have mode `600`; the template is
    `Data/config/kurulum.env.example` (**DD-119**).
  - The launcher takes the SSH host from that file and sends the file only to
    `/run/master-stack` on the server (`tmpfs`). The installer reads it and
    deletes it before any other step.
  - The file is the truth on every run. An account that differs from it is
    rewritten and only that container restarts; an account that matches is
    left alone. A password changed in FileBrowser's UI returns to the file's
    value on the next run.
  - Stage 0 shows the inputs without passwords and asks for one confirmation
    before the first write. The full-upgrade and image-pull questions stay
    for re-runs.
- **Added:** strict parsing: no `source`, values taken literally, and a clear
  stop naming the line and key for an unknown, duplicate, missing, quoted,
  padded or CRLF line. Values never appear in a message or the log.
- **Removed:** the hidden password and auth-key prompts, and the launcher's
  host prompt.
- **Verified on `nrm`:**
  - The exported `.command` refused a mode-644 file on the Mac.
  - Answering `h` at the confirmation changed nothing.
  - v2-84 → v2-85 exit 0: only the WebDAV account differed, so only `webdav`
    restarted.
  - A second run was a full no-op.
  - Three changed passwords updated exactly those three services: new
    passwords accepted, old ones refused, nothing in the log or
    `docker inspect`.
  - An unknown key and a short password each stopped stage 0 before any
    change.
  - The operator's WebDAV credential was restored byte-identical afterwards.
  - bats 116 ok.

### 2026-09-14 — FileBrowser account and Transmission preferences from the installer (v2-84)

- **Added:**
  - Stage 0 asks for a FileBrowser user name and password (at least 12
    characters, FileBrowser's own minimum) when no database exists.
  - Stage 4 builds the database with the image's CLI in a network-less
    one-shot container and installs it only after verifying it. The password
    reaches only `htpasswd`'s stdin; no first-start random admin password is
    created (**DD-118**).
  - An existing FileBrowser database is kept. Deleting it makes the next run
    ask again, and a running FileBrowser is restarted on the new database.
  - A fresh Transmission `settings.json` also turns off DHT, PeX and local
    peer discovery and limits active downloads to 12.
- **Changed:** container backups carry `wg-easy.db` only.
  - FileBrowser and Transmission are no longer stopped by a backup or
    restore.
  - Older archives still validate, and only their `wg-easy.db` is loaded.
- **Verified on `nrm`:**
  - A re-run over existing data asked nothing and touched no container.
  - A short password was refused before any change.
  - The new account logged in through Caddy while wrong and default
    passwords were refused, and nothing leaked to logs or `docker inspect`.
  - Transmission reported the seeded preferences over RPC and kept them
    across a restart.
  - A live backup held only `wg-easy.db`, and checks on older archives
    reported one file to load. A restore of a v2-83-era archive left
    FileBrowser and Transmission untouched.
  - Backup round-trip 20 checks; bats 108 ok.

### 2026-09-13 — Transmission replaces qBittorrent (v2-83)

- **Changed:** the torrent client is Transmission 4.1.3 (LinuxServer image)
  at `http://torrent.${LOCAL_DOMAIN}`. It keeps the peer port 61005 TCP+UDP
  and qBittorrent's download layout (`/downloads`, partial files in
  `/downloads/incomplete`). The `QBIT_*` settings become `TORRENT_*`,
  including `state.env` and the firewall (**DD-117**).
- **Added:**
  - Stage 0 asks for a Transmission user name and password.
  - They are stored in root-only files and passed with
    `FILE__USER`/`FILE__PASS`, never in `compose.yaml` or `docker inspect`.
    The image needs the plaintext at every start; this trade-off is
    recorded in DD-117.
  - On a fresh install the installer seeds `settings.json`, including the
    `rpc-port` that the image's clean shutdown depends on.
  - Stage 7 fails if Transmission's RPC answers without a login.
  - A leftover `qbittorrent` container stops the installer before any
    change. The installer does not remove it.
- **Fixed:** when the installer writes new Dozzle or Transmission
  credentials, it now restarts that container, so a password change takes
  effect at once. A replaced Dozzle `users.yml` used to wait for the next
  restart.
- **Changed:** container backups carry Transmission's `settings.json`.
  qBittorrent- and Portainer-era archives still restore FileBrowser and
  wg-easy and leave Transmission alone.
- **Removed:** the post-install step of reading qBittorrent's temporary
  password from its logs.
- **Verified on `nrm`:**
  - Throwaway containers established the credential and shutdown behaviour.
  - The stage-0 gate changed nothing, and the install recreated no other
    container.
  - Login was enforced through Caddy, the firewall check passed, and the
    peer port was reachable from outside.
  - Restarts were clean, and credential changes applied without a manual
    restart.
  - The backup round-trip, a live backup, a legacy check and a self-restore
    passed; bats 106 ok.

### 2026-09-13 — Dozzle replaces Portainer (v2-82)

- **Changed:** the `portainer` service is replaced by `dozzle`
  (`amir20/dozzle:v11`) at `http://dozzle.${LOCAL_DOMAIN}` (loopback 61002).
  It offers container state, live logs and start/stop/restart/remove.
  - Login is required.
  - Shell is off and analytics are off.
  - The container runs with a read-only root, all capabilities dropped,
    `no-new-privileges` and a healthcheck (**DD-116**).
- **Added:**
  - Stage 0 asks for a Dozzle user name and password; an existing
    `/etc/master-stack/dozzle/users.yml` is kept.
  - Stage 4 writes that file with the image's own `generate` command
    (bcrypt, `actions` role), password on stdin, in a container without
    network.
  - Stage 7 fails if Dozzle's API answers without a login, and warns while
    an old `portainer` container is still running. The installer does not
    remove it (**DD-96**).
- **Changed:** container backups carry three files (FileBrowser,
  qBittorrent, wg-easy). Portainer-era archives still validate and restore,
  with the Portainer part ignored.
- **Removed:**
  - The Portainer setup-token step after an install.
  - The loopback HTTPS upstream with `tls_insecure_skip_verify` (**DD-62**,
    superseded).
- **Verified on `nrm` (Debian 13.6):**
  - Before adopting, a throwaway hardened Dozzle ran and enforced its login.
  - The v2-81 → v2-82 re-run created a healthy Dozzle without recreating
    the other five containers.
  - DNS and Caddy worked, the login was enforced, and a login worked.
  - The Portainer warning appeared. After removing that container by hand, a
    second run was a no-op.
  - The backup round-trip passed 18/18; a live backup held three files, and
    `check` accepted a Portainer-era archive.
  - bats 104 ok.

### 2026-09-13 — Optional Tailscale auth key (v2-81)

- **Added:** stage 0 asks for an optional Tailscale auth key, hidden, only
  when the node is not already online. With a key, stage 2 logs in with
  `tailscale up --auth-key=file:…` from a `0600` file in the root-only
  runtime tmpfs, removed right after, and skips the browser step. An empty
  answer, a rejected key or a timeout (`TS_AUTHKEY_LOGIN_SECONDS`, 300 s)
  uses the interactive login URL as before. The key never reaches
  `config.env`, `state.env`, the log, a command line or child environments.
  OAuth client secrets are refused with a clear message (**DD-115**).
- **Verified:**
  - bats 102 ok. A new test caught an exit status that depended on
    `pipefail` and was fixed.
  - Live, the real function with a fake key against the host's Tailscale
    1.102.4, run in a throwaway container: rejected in 5 s, fallback taken,
    no residue.
  - A v2-81 re-run on the online production host skipped the prompt and
    changed nothing.
  - A successful real-key login is still to be seen on the next fresh
    install.

### 2026-09-13 — Repository root holds only what is double-clicked

- **Changed:** the installer tree (`install.sh`, `common.sh`, `config/`,
  `templates/`, `scripts/`, `systemd/`), `dev/`, `tests/`, `docs/`, `app/`,
  `CHANGELOG.md` and `SESSION.md` moved under `Data/` with `git mv`. The
  root keeps the current portable installer (`<V2_VERSION>.command`),
  `container-backup.command`, the Git-ignored `backup/`, `README.md`,
  `CLAUDE.md`, `.gitignore` and `.cursor/`. Paths in `Data/` documents are
  relative to `Data/`, which matches the installer's layout on the host.
- **Changed:** the exporter writes `Data/app/<V2_VERSION>.command` and
  replaces the root copy of the current version; `app/latest.command` is
  gone. `container-backup.command` runs its worker from
  `Data/dev/container-backup-remote.sh`.
- **Removed:** the Git-ignored `export/` folder. Its copies were
  byte-identical to the repository files, and the one backup in it was moved
  to `backup/` with its content hashes unchanged. The Turkish click-order
  note is now `Data/OKUBENI.txt`.
- **Unchanged:** installer behaviour and version. Re-exporting v2-80 from
  the new layout produced a file byte-identical to the committed one. bats
  99 ok (one new test pins the root copy to its `Data/app/` archive);
  `bash -n` and `shellcheck` clean from the root.

### 2026-09-13 — Container backups carry one file per service

- **Changed:** `container-backup` saves and restores only the files holding
  what an operator creates: `portainer.db`, `filebrowser.db`,
  `qBittorrent.conf` and `wg-easy.db`. Keys, certificates, `wg0.conf` and
  FileBrowser's `settings.json` are produced by the install or the
  application and are no longer copied or overwritten; restore touches
  nothing but the four files and clears SQLite side files beside them
  (**DD-114**).
- **Compatibility:** whole-directory archives from before this date still
  validate and restore; only the four files are taken from them, and `check`
  says so.
- **Verified on `nrm`:**
  - Throwaway Portainer and FileBrowser instances accepted a backed-up
    database with their own fresh keys.
  - The isolated round-trip passed.
  - A live backup held exactly four files (40 KB), and a self-restore left
    all 12 out-of-scope files unchanged, with 6/6 containers healthy.

### 2026-09-12 — Unattended security upgrades, reboot left to the operator (v2-80)

- **Added:** stage 1 installs `unattended-upgrades`, writes
  `/etc/apt/apt.conf.d/20auto-upgrades` (periodic list update and unattended
  upgrade on) and `52master-stack-unattended` (`Automatic-Reboot "false"`),
  and enables the `apt-daily` timers. The origin filter stays the
  distribution default (Debian stable + security; Ubuntu security), so
  Docker, Tailscale and Caddy are still updated only by re-running the
  installer. Stage 7 reads the effective policy back and warns on a mismatch
  (**DD-113**).
- **Why:** the netcup Debian 13 image ships without the package; Ubuntu's
  ships with it. The 2026-09-12 review of the freshly installed and restored
  Debian host (18/18 acceptance checks, all DD-105/109/110/111 effects in
  place) found nothing else worth changing.
- **Live-verified on Debian 13.6 (`nrm`, 2026-09-12):** a v2-79 → v2-80
  re-run installed the package (11 new packages, 4 MB), wrote both files,
  left the `apt-daily` timers active and recreated no container (6/6 ID
  signature unchanged, 3/3 healthy, 0 failed units). `apt-config dump` shows
  `Unattended-Upgrade "1"` and `Automatic-Reboot "false"`;
  `unattended-upgrade --dry-run --debug` lists only the three Debian origins
  as allowed, so Docker, Tailscale and Caddy stay outside the filter. The
  first attempt exited 141: the new stage-7 read-back piped `apt-config
  dump` into an `awk` that exited on its first match, which sends SIGPIPE
  to `apt-config` and, under `pipefail` + `set -e`, aborted verification
  after every stage had completed. Fixed by letting `awk` read to the end;
  the corrected run and a second no-op run exited 0 with no warnings.

### 2026-09-11 — Encrypted container backups and single-upload restore

- **Added:** backups are encrypted with a password asked twice when the backup
  is taken and once when it is checked or restored. Standard `openssl enc`
  format (AES-256-CBC, PBKDF2-HMAC-SHA256, 600,000 iterations), decrypted
  locally so the password never reaches the server; any OpenSSL or LibreSSL
  on any OS can decrypt the file. Existing plaintext backups stay usable;
  the archive layout and manifest schema are unchanged (**DD-112**).
- **Changed:** restore uploads the archive once and runs check and restore in
  one remote directory, instead of three SSH rounds with two uploads.
- **Removed (2026-09-12):** the `before-restore` backup that restore
  downloaded to the workstation before replacing data. It stopped the
  containers a second time and protected nothing on a fresh target. The
  server-side recovery snapshot and automatic rollback on failure remain; a
  successful restore cannot be undone (**DD-112**).
- **Scope:** the launcher is macOS only (`shasum`, the system
  `/usr/bin/openssl`, one multiplexed SSH connection). A Git Bash/WSL-portable
  variant was tried and dropped the next day, unexercised (**DD-112**); the
  encrypted file itself opens with any OpenSSL.
- **Considered and dropped the same day:** a `seed` action that carried
  `config.env` and `webdav.htpasswd` in the archive and placed them on a
  fresh host before `install.sh`. It was verified end to end, then removed at
  the user's request: `install.sh` asks for those few values anyway, and the
  tool stays a copy-and-load tool for container settings (**DD-112**).
- **Docs:** reinstall runbook (fresh OS → install with the same answers →
  restore → Tailscale admin → Infuse address) and the encryption format in
  `docs/container-backup.md`; `tests/backup-roundtrip.sh` is now part of the
  host acceptance sequence.
- **Live-verified on `nrm` (Debian 13.6):** isolated round-trip, and encrypted
  backup, check and restore from the Mac. A reinstall from a bare OS with this
  flow has not been run yet.
- Installer tree unchanged; `V2_VERSION` stays at v2-79.

### 2026-09-11 — TCP congestion control is BBR, measured before adopting it (v2-79)

- **Changed:** stage 2 now loads `tcp_bbr` and sets
  `net.ipv4.tcp_congestion_control = bbr` and `net.core.default_qdisc = fq` in
  `99-zz-master-tcp.conf` (**DD-111**). If the module cannot be loaded, the
  install continues on the kernel default and says so. Stage 7 reads the live
  value back and warns on a mismatch rather than failing.
- **Measured before adopting:** runs were interleaved and each run's congestion
  control was confirmed on the live socket. Peak throughput matched cubic's
  (~440 Mbit/s over the direct tailnet path). Cubic lost about 20% on three of
  six runs after bursts of packet loss; BBR did not. The gain is steadier
  throughput, not a higher peak.
- **Scope:** this affects only TCP that ends on this host: WebDAV to Infuse,
  qBittorrent uploads and the web UIs. Exit-node traffic is forwarded, and
  forwarded TCP is controlled by its endpoints. The review had claimed
  otherwise; **DD-111** corrects it.
- **Live-verified on Debian 13.6 (trixie)** (2026-09-11): a fresh install from
  a bare host (80 s), an idempotent re-run, a seeded release-change run, a cold
  reboot and a post-reboot re-run — all exit 0. `tcp_bbr` loads on the 6.12
  kernel, the DD-110 ordering holds, and every stage-7 check passes after the
  reboot. **v2-77 through v2-79 are now accepted on both supported
  distributions.**

### 2026-09-11 — Container log rotation and Docker DNS actually take effect (v2-78)

- **Fixed:** container log rotation (**DD-107**) never took effect on any host,
  including fresh installs. docker-ce's postinst starts dockerd as soon as the
  package installs, and `daemon.json` was written two seconds later. dockerd
  was not restarted, so all six containers were created without the log
  options. Their `LogConfig {}` stays that way permanently, because log
  configuration is fixed when a container is created. The same ordering also
  meant **DD-8's container DNS setting** did not apply between a fresh install
  and the first Docker restart. `daemon.json` is now written **before** the
  Docker packages are installed. No Docker package owns that file, so the
  install cannot overwrite it (**DD-110**). This is the same pattern **DD-18**
  already uses for Tailscale.
- **Changed:** log rotation now lives in `compose.yaml` as an `x-logging`
  anchor that every service references. The values still come from
  `defaults.env`. On an existing host this appears as a change to the service
  definitions, so the next run **recreates the six containers once** to apply
  it. Named volumes keep their data. `daemon.json` keeps its `log-opts` only as
  the host default for containers outside this stack.
- **Added:** if `daemon.json` changes while dockerd is already running, the
  installer now reports that daemon-level settings will apply at the next
  Docker restart, instead of assuming they are already in effect.
- **Corrected:** the v2-74 entry's "Takes effect for containers created after
  the change" did not hold for fresh installs, and the v2-76 Ubuntu acceptance
  checked `daemon.json` rather than the containers. Both are now noted in
  **DD-110**.
- **Live-verified on Ubuntu 26.04.1** (2026-09-11): on an existing host the run
  recreated the six containers once and all six now carry the log options; a
  second run recreated nothing. After Docker was purged completely,
  `daemon.json` was in place before dockerd's first start, and container DNS
  and the daemon log options were in effect with no restart. A stage-7
  `wg.ayc` 502 seen during that test came from stale kernel bridges left by
  purging Docker without a reboot. That is a test artifact, now documented in
  `tests/README.md`.
- **Clean record:** after a Docker purge and a reboot, v2-78 installed from a
  clean Docker state and exited 0. DNS and log options were in effect from
  dockerd's first start, and every stage-7 check passed.

### 2026-09-10 — A setting that silently did nothing now reports what happened (v2-77)

- **Fixed (review A1):** `stage_6` still writes `DNSStubListener=no` when
  systemd-resolved is active, but no longer assumes it worked. Ubuntu 26.04 /
  systemd 259 accepts and ignores the key — the stub keeps answering on
  `127.0.0.53`, on a fresh install and across a reboot — so the achieved state
  is now read back and logged either way (**DD-109**). No binding changes.
- **Withdrawn, after its premise failed a live test:** A1 also claimed a latent
  start-order race in which dnsmasq could take `127.0.0.53` and lock resolved
  out, with a proposed `listen-address=127.0.0.1` fix. Tested first: with
  resolved stopped and the address completely free, dnsmasq did **not** take
  it — `bind-dynamic` binds only the addresses *assigned* to an interface, and
  `127.0.0.53` is not assigned to `lo`, merely reachable via 127/8. The change
  would have altered a live DNS binding and dropped `[::1]:53` for no benefit.
  `docs/os-aware-review.md` §4 is corrected accordingly.
- **Verified:** the reporting line appears on Ubuntu 26.04 (stub up, reported
  immediately, run exits 0). The opposite branch cannot occur on a host where
  the key is ignored, so it was exercised in isolation along with a missing
  `ss`; both behave correctly and the wait is wall-clock bounded.

### 2026-09-11 — The OS-divergence surface becomes an enumerable inventory (v2-76)

- **No behaviour change.** Every distro-dependent point in `install.sh` now
  carries a `# OS-DIVERGENCE: <slug>` marker, and `architecture.md` §7.1 lists
  the same eight slugs in a delimited table. `grep -n 'OS-DIVERGENCE:'
  install.sh` prints the live inventory. Previously this surface was
  discoverable only by reading 1159 lines.
- **The inventory checks itself:** bats asserts the code marker set and the doc
  table set are equal and that every row cites a `DD-*`. A divergence cannot be
  added to the code without appearing in the doc, or dropped from the doc while
  it still exists. Verified by mutation — removing a marker, removing a table
  row, and removing a DD citation each fail the test.
- **Added:** coverage for the `resolved-stub` divergence, which had none. The
  suite now asserts that `DNSStubListener=no` is written *only* inside the
  `systemd-resolved` probe (so Debian, where resolved is inactive, writes no
  drop-in at all), that the stub repoint is nested in the same probe and
  target-tested, and that the restart is gated on a changed drop-in or a
  changed release. Verified by mutation.
- **Recorded:** the tree stays a single backbone rather than forking into
  per-distribution paths. Measured basis — of 1159 lines, exactly **one** is a
  real `if OS = debian` branch (`debian-keyring`), two are the same code with
  an `os-release` value substituted, and five are capability probes. See
  `os-aware-review.md`.
- **Version bump with no behaviour change** is deliberate: the markers ship
  inside the portable `.command`, so the embedded archive differs, and
  `app/<version>.command` must keep identifying exactly one archive.
- **Live-verified on Ubuntu 26.04.1 (resolute)** (2026-09-10): a fresh install
  from a bare host (95 s), an idempotent re-run, a seeded release-change run, a
  cold reboot and a post-reboot re-run — all exit 0. With the Debian 13
  acceptance at v2-75, **every capability probe has now been measured on both
  of its branches**, the acting one and the skipping one. `needrestart` was
  measured rather than assumed: zero journal records and `sshd` keeping its
  boot timestamp through a first-install `full-upgrade`.

### 2026-09-08 — Fresh Debian installs work again (v2-75)

- **Fixed:** v2-74's stage-0 netfilter backend gate made a **fresh Debian
  install impossible**. A minimal Debian 13 image ships no `iptables` at all —
  the package arrives in stage 1's base set — so the gate died at stage 0,
  before the stage that installs the binary it inspects. Ubuntu ships
  `iptables` preinstalled, which is why v2-74's acceptance did not catch it.
  The gate is now `check_nft_iptables optional|required`: stage 0 verifies
  whatever exists and defers otherwise, stage 1 makes it mandatory once the
  package is in place. Both `iptables` and `ip6tables` are checked, since each
  has its own alternatives link (**DD-108**).
- **Live-verified on Debian 13.6 (trixie)** (2026-09-08): a fresh install from
  a bare host through stages 0–7, an idempotent re-run, a cold reboot, a
  post-reboot re-run and a seeded release-change run — all exit 0, 6/6
  containers healthy, 0 failed units, and every §14 check passing after the
  reboot. Both supported distributions have now had the same acceptance.

### 2026-09-08 — OS-aware install: record the release, verify the result (v2-74)

- **Fixed:** `needrestart` — installed and hooked into apt on Ubuntu, and
  running in *automatic* restart mode there regardless of
  `DEBIAN_FRONTEND` — no longer restarts `sshd`, `docker`, `containerd`,
  `tailscaled`, `caddy` or `dnsmasq` in the middle of a stage. `stage_1`
  exports `NEEDRESTART_SUSPEND=1`; the installer owns its own restarts
  (**DD-103**). No-op on Debian.
- **Added:** `state.env` records `OS_ID`, `OS_CODENAME`, `OS_VERSION_ID`,
  `OS_ARCH` and `KERNEL_RELEASE`. A re-run whose recorded identity differs
  from the live one (for example after `do-release-upgrade`) warns and
  re-applies the OS-dependent steps — apt repo refresh, `systemd-resolved`,
  one dnsmasq/Caddy restart, firewall — even when the written files are
  byte-identical (**DD-104**). A host with no recorded OS (v2-73 or earlier)
  is not reported as a release change.
- **Fixed:** the two `sysctl.d` drop-ins move to `99-zz-master-*` so they sort
  after provider-supplied files (`99-nc-kernel.conf` on netcup sorted after
  them and writes the same keys); the old names are deleted on upgrade.
  `stage_7` now asserts the **live** `net.ipv4.ip_forward=1` and warns when
  `net.core.rmem_max` is below the floor — a silently lost forwarding sysctl
  would otherwise leave an exit node broken after a reboot with every unit
  green (**DD-105**).
- **Added:** three fail-early gates (**DD-106**) — the host `iptables`
  backend must be `nf_tables` (Docker's), with the exact `update-alternatives`
  remedy in the message; the Tailscale and Docker repo suites are probed for
  the detected codename before the source file is written; and every rendered
  config is validated on the target (`dnsmasq --test -C`, `caddy validate`
  with the real `TAILSCALE_IPV4`/`WEBDAV_PORT`, `docker compose config -q`)
  before the unit that consumes it is restarted.
- **Added:** container log rotation. `daemon.json` gains
  `log-opts.max-size=10m` / `max-file=3`, merged only when the logging driver
  is `json-file` or unset and added to any existing `log-opts` (**DD-107**).
  Takes effect for containers created after the change; Docker is
  deliberately not restarted.
- **Analysis:** [`docs/os-aware-review.md`](docs/os-aware-review.md) — the
  full OS-awareness and optimisation review this release implements, with
  live measurements from `nrm` (Ubuntu 26.04.1, systemd 259, kernel 7.0.0-31).
- **Live-verified on Ubuntu 26.04.1** (2026-09-08): the v73→v74 upgrade run,
  an idempotent re-run, a seeded release-change run that exercised the forced
  re-application, a cold reboot and a post-reboot re-run — all exit 0, with
  6/6 container IDs unchanged throughout and every §14 check passing after the
  reboot. Debian 13 acceptance is still outstanding.
- **Not taken here:** BBR/`fq` congestion control and the dnsmasq
  `listen-address` change both need before/after measurement on both OS
  families first; see the review's plan, steps 6–7.

### 2026-09-06 — Portable settings between provisioned v73 hosts

- **Changed:** differing container image IDs now warn instead of blocking
  backup restore; no override is required. The backup utility has no host
  distribution/release gate. Existing archives remain usable between
  provisioned Debian/Ubuntu hosts with the expected v73 container layout.
- **Preserved:** archive validation, mount/user/port checks, recovery snapshots
  and rollback. Arbitrary application/database version compatibility is not
  guaranteed. Installer behavior and its supported-OS matrix are unchanged.
- **Compatibility:** `--allow-image-change` remains accepted as a no-op.

### 2026-09-06 — Fix false backup restore UID/GID mismatch

- **Fixed:** compare PUID/PGID independently of Docker environment ordering,
  including in existing schema-1 backups. Matching values no longer block a
  restore merely because PUID and PGID appear in a different order.
- **Diagnostics:** real user/group or port mismatches show the affected
  service and source/target values; compatibility safeguards remain enabled.
- **Tests:** cover both environment orders and rejection of real PUID, PGID
  and port changes, including with the image-change override.

### 2026-09-05 — Separate SSH container settings backup utility

- **Added:** root-level `container-backup.command` with backup, restore and
  non-mutating target/archive check modes. SSH prompts accept a configured
  alias or `user@address`; timestamped, private, unencrypted snapshots live
  under Git-ignored `backup/`.
- **Scope:** Portainer data, FileBrowser database/config, wg-easy database and
  WireGuard keys/config, and only qBittorrent's `qBittorrent.conf`. Downloads,
  categories/session data, WebDAV, Unpackerr and Tailscale state are excluded.
- **Restore:** archive path/type/hash checks, image/port/UID compatibility,
  pre-restore local recovery backup, stopped-container copying and an error
  rollback attempt. Existing v73 installer/portable behavior is unchanged.

### 2026-09-02 — Flatten repository and portable runtime layout

- **Changed:** active installer files now live at the repository root instead
  of a nested `v2/` directory. Supporting directories (`config`, `templates`,
  `scripts`, `systemd`, `tests`, `dev` and `app`) moved with them; current
  documentation uses the shorter root-relative paths.
- **Changed:** the portable exporter is now `dev/export-installer.sh`. Its
  runtime archive stages an `installer/` tree and deploys directly to
  `/root/debian-server-installer/install.sh`, atomically replacing the old
  dedicated source tree, including a prior nested layout.
- **Unchanged:** installer version `2026.08.06-v2-73`, service configuration,
  prompts, ports, firewall policy and managed host paths. This is a source and
  delivery-layout cleanup, not a stack behaviour change.

### 2026-08-30 — v2-73: Ubuntu wg-easy legacy IPv4 netfilter modules

- **Fixed:** Stage 4 now preloads `ip_tables` and `iptable_nat` on the host
  and persists them in `/etc/modules-load.d/wg-easy.conf`, alongside the
  existing WireGuard and legacy IPv6 modules. Ubuntu 26.04 defaults to the
  nft iptables backend, so those IPv4 legacy modules were not otherwise
  loaded; wg-easy uses `iptables-legacy` internally and its `wg-quick up`
  failed while creating the IPv4 NAT rule.
- **Live-verified on resolute (2026-08-30):** loading the two modules and
  restarting only wg-easy recovered a healthy `wg0` on UDP 61001. A v2-73
  re-run wrote the five-module boot file without recreating any container;
  after a cold reboot `systemd-modules-load` reported success, all five
  modules were present, wg-easy started without iptables errors, and the full
  six-container, firewall, DNS/Caddy and read-only WebDAV checks passed with
  no failed units.

### 2026-08-29 — v2-72: Ubuntu 24.04/26.04 LTS support

- **Added:** the OS gate (`require_supported_os`, formerly
  `require_debian_trixie`) now accepts Debian 13 (trixie), Ubuntu 24.04
  LTS (noble) and Ubuntu 26.04 LTS (resolute). Tailscale and Docker apt
  repo lines are derived from `os-release` (`OS_ID`/`OS_CODENAME`) —
  both vendors' Ubuntu repos verified live; the Caddy line was already
  distro-agnostic. See **DD-102**.
- **Added:** Ubuntu guards — stage_0 dies if ufw is active (two owners
  for INPUT otherwise); stage_6 repoints an `/etc/resolv.conf` stub
  symlink to resolved's uplink file so host DNS survives
  `DNSStubListener=no`; every `apt-get` call waits on the dpkg lock
  (`-o DPkg::Lock::Timeout=60`) because Ubuntu ships
  unattended-upgrades enabled.
- **Changed:** `debian-keyring` is installed on Debian only; the
  full-upgrade prompt now says "Sistem" instead of "Debian".
- **Live-verified on noble (2026-08-29):** full install on a fresh
  Ubuntu 24.04.4 host (`nrm` reimaged) passed stages 0–7 and
  independent post-checks.
- **Live-verified on resolute (2026-08-30):** full install on a fresh
  Ubuntu 26.04.1 cloud image (`nrm`, kernel 7.0) passed stages 0–7 and
  independent contract checks. A default re-run kept 25/25 managed files
  byte-identical, preserved all six container IDs/start times and restarted
  no critical service. Tailscale and Docker restart recovery, asynchronous
  firewall re-application, and a full reboot also passed with six containers,
  DNS/Caddy, authenticated read-only WebDAV and host DNS healthy. On reboot,
  Tailscale direct DNS may replace stage 6's uplink symlink with its managed
  MagicDNS `resolv.conf`; this is the expected steady state, not resolver
  drift.

## [2026.08.06-v2-71] - 2026-08-28

Maintenance cut of the lean `v2/` installer: Infuse/WebDAV addressing via
Caddy (v2-65…67), the opt-in image pull with prune and disk floor
(v2-68/69/71), re-run cost reductions (v2-70/71). `V2_VERSION` is
`2026.08.06-v2-71`. Portable app: `v2/app/2026.08.06-v2-71.command`.
Git tag: `2026.08.06-v2-71`.

### 2026-08-28 — v2-71: Disk floor before pull, single-pass downloads repair

- **Added:** the opted-in image pull (v2-68) now refuses to start when the
  filesystem holding `/var/lib/docker` has less than `PULL_MIN_FREE_GB`
  (defaults.env, 5 GiB) free — a half-finished pull on a full disk can
  take running containers down with it, so the gate fails closed before
  any bytes are fetched. See **DD-101**.
- **Changed:** `ensure_downloads_tree` walks the downloads tree **once**
  instead of three times (one find whose `-exec … + -false` groups chain
  the chown and both chmod repairs — portable across GNU and BSD find,
  since the bats suite runs on the macOS workstation). Repair stays
  selective per **DD-84** — only entries whose owner or mode deviates are
  touched; behaviour is byte-identical, only the tree I/O drops to a
  third.

### 2026-08-23 — v2-70: Skip redundant apt-get update on a re-run

- **Changed:** `stage_2`/`stage_4` only run `apt-get update` after writing
  the Tailscale/Docker apt source files when the file's content actually
  changed (`V2_LAST_ATOMIC_CHANGED`). On a re-run — where both files
  already existed before `stage_1`'s own `apt-get update` — this drops
  two redundant full index refreshes per run. First install is
  unaffected (the files are new, so `V2_LAST_ATOMIC_CHANGED=1`). See
  **DD-100**.

### 2026-08-23 — v2-69: Prune dangling images after an opted-in pull

- **Changed:** When the operator accepts the v2-68 "pull güncel imaj"
  prompt, `stage_7` now runs `docker image prune -f` right after
  `docker compose up -d` recreates containers on the new digest, so the
  old (now-dangling, untagged) image layers left behind by the pull are
  reclaimed automatically. A prune failure is logged and does not abort
  the install. Declining the prompt (the default) leaves image cleanup
  untouched, as before. See **DD-99**.

### 2026-08-23 — v2-68: Optional image pull on re-run

- **Added:** On a re-run against an already-provisioned host, the
  installer asks "Konteyner imajları güncel sürüme çekilsin mi?"
  (default: hayır). Answering evet runs `docker compose pull` before
  `docker compose up -d`, so floating-tag images (`:lts`, `:v2`,
  `:latest`, …) refresh to their current upstream digest. Skipped on
  first install (`docker compose up -d` already pulls missing images)
  and answerable non-interactively via `V2_PULL_IMAGES=1`. See **DD-99**.

### 2026-08-10 — v2-67: Caddy WebDAV port from state.env

- **Changed:** Caddyfile Infuse/upstream ports use `{$WEBDAV_PORT}` (from
  `state.env` / Caddy `EnvironmentFile`), not a baked `__WEBDAV_PORT__`.
  Re-run port changes restart Caddy via `WEBDAV_PORT_CHANGED`.

### 2026-08-10 — v2-66: Infuse via Caddy on TS IP:WEBDAV_PORT

- **Changed:** Caddy WebDAV site is
  `http://webdav.*, http://{$TAILSCALE_IPV4}:${WEBDAV_PORT}` → loopback
  rclone (**DD-98**). Infuse uses port `61003`; Compose stays loopback-only
  (no Tailscale IP in `compose.yaml`).
- **Reverted:** v2-65 Compose `${TS_IPV4}:${WEBDAV_PORT}` publish and
  refresh-time `docker compose up -d webdav`.

### 2026-08-10 — v2-65: Infuse WebDAV on Tailscale IP:port (superseded by v2-66)

- Briefly published WebDAV on `${TAILSCALE_IPV4}:${WEBDAV_PORT}` in Compose
  and removed the Caddy bare-IP alias. Superseded the same day by **v2-66**
  (Caddy listens on that port; Compose stays loopback-only).

## [2026.08.06-v2-64] - 2026-08-10

GA cut of the lean `v2/` installer. `V2_VERSION` is `2026.08.06-v2-64`.
Portable app: `v2/app/2026.08.06-v2-64.command`. Git tag: `2026.08.06-v2-64`.

### 2026-08-09 — v2-64: FileBrowser `--disableExec`, quieter summary

- **Fixed:** Compose uses `--disableExec` (the old `--disable-exec` name is
  deprecated in current classic FileBrowser and only printed a notice).
- **Changed:** End-of-install summary drops container admin / password
  reminders (Portainer, wg-easy, FileBrowser, qBittorrent). Operators create
  those accounts in the UIs; Tailscale admin steps and WebDAV/wg endpoint
  hints remain.
- **Fixed:** `export-v2.sh` packs a Debian-quiet tarball: UTC mtime
  `2000-01-01` (not local 1970 → epoch 0), `--no-xattrs` /
  `--no-mac-metadata`, ustar + root/0 ownership. Stops GNU tar
  “implausibly old” and `LIBARCHIVE.xattr.com.apple.provenance` noise.

### 2026-08-09 — v2-63: Compose images follow upstream stable tracks

- **Changed:** Prefer the vendor's stable track tag over a frozen
  `patch@digest` (**DD-97**):
  - Portainer CE → `portainer/portainer-ce:lts` (official docs)
  - FileBrowser → `filebrowser/filebrowser:v2`
  - wg-easy → `ghcr.io/wg-easy/wg-easy:15`
  - Unpackerr → `ghcr.io/unpackerr/unpackerr:0.15`
  - rclone → `rclone/rclone:1.75` (was pinned on `1.74.4`; tips at `1.75.0`)
  - qBittorrent → `lscr.io/linuxserver/qbittorrent:latest` (LinuxServer’s
    documented stable + libtorrent v2 track; tip `5.2.3_v2.0.13-ls470`)
- **Forbidden still:** `libtorrentv1`, `sts`, `edge`, `nightly`, `beta`,
  and `latest` on every image except linuxserver/qbittorrent.

### 2026-08-09 — v2-62: No migration cleanup; the installer owns only its own

- **Removed:** `purge_host_webdav_leftovers` — the `master-webdav` unit,
  user, group and downloads ACL removal, plus `apt-get purge rclone` and
  `apt-get autoremove`. A global package purge and a `userdel` were never
  the installer's business (**DD-96**).
- **Removed:** `remove_stale_filebrowser` — container and legacy volume
  deletion. This also ends the last idempotency wart: a re-run recreated the
  FileBrowser container every time (~2 s downtime, new container id) even
  though all 16 managed files were byte-identical.
- **Removed:** `filebrowser.yaml` (Quantum era), `watch-tailnet-addr`
  unit/script disable, the retired `docker.service.wants` symlink, and the
  `$COMPOSE_DIR/.env` deletion.
- **Changed:** The upgrade path is a fresh install, or a re-run that
  overwrites the files the installer owns. Older revisions are not migrated.
- **Test:** A guard test fails the suite if migration cleanup returns —
  no `apt-get purge`, `userdel`, `setfacl`, `docker rm`, or `disable --now`.

### 2026-08-09 — v2-61: Extra WAN passes and referenced staging leftovers

- **Fixed:** `--check` counted only exact `-j ACCEPT`/`-j RETURN` bodies as a
  bypass, so an interface-qualified pass (`-i eth0 -j ACCEPT`, or any extra
  `--dport`) satisfied every expected pattern and went unnoticed. The number
  of WAN allows must now equal the allow list exactly, in `MASTER-INPUT` and
  `MASTER-DOCKER`, both families (**DD-95**).
- **Fixed:** A staging chain left *referenced* by an interrupted
  `activate_named` was skipped by the purge, which failed `--check` forever
  and left the unit failed with the watchdog restarting it in vain. Cleanup
  now runs at the end of a successful apply and removes the parent jump too.
- **Changed:** The allowed WAN `(proto, port)` pairs live in one list that
  drives both the per-rule checks and the count.
- **Docs:** The boot window is measured and stated: ~850 ms between the WAN
  address becoming usable and the policy landing, with sshd (already allowed)
  as the only WAN listener in it.

### 2026-08-09 — v2-60: Firewall converges instead of failing closed-open

- **Fixed:** The WAN interface is detected from the live default route at
  apply/check time. A renamed NIC now warns and still gets a correct policy
  instead of failing the unit and leaving the host with no `INPUT` policy
  (**DD-94**). `state.env` `WAN_INTERFACE` is a hint only.
- **Fixed:** `master-firewall --check` verifies chain *shape*: exactly one
  WAN DROP, after every WAN allow, with no unconditional `ACCEPT`/`RETURN`
  ahead of it in `MASTER-INPUT` / `MASTER-DOCKER`.
- **Fixed:** An apply deletes unreferenced leftover staging chains, so an
  interrupted earlier run cannot fail `--check` forever.
- **Added:** `refresh-tailnet-config` (already every 5 min) restarts
  `master-firewall` when the unit is `failed` or `--check` fails, with
  `reset-failed` first; skipped while the oneshot is mid-apply. Scope is the
  firewall unit only — no container or file reconcile.
- **Changed:** `master-firewall.service` no longer orders itself after
  Docker (`After=`/`Wants=`/`WantedBy=docker.service` removed; `PartOf=`
  kept as the second trigger next to the `docker.service.d` drop-in). The
  installer removes the retired `docker.service.wants` symlink.
- **Changed:** Restart pacing `RestartSec=10s`,
  `StartLimitIntervalSec=300`, `StartLimitBurst=12`.
- **Changed:** FileBrowser container / legacy volume removal now requires a
  matching `com.docker.compose.project` label; image-name matching is gone.

### 2026-08-09 — v2-59: Firewall Docker re-apply, safer install paths

- **Fixed:** `docker.service.d` `ExecStartPost` `--no-block` restarts
  `master-firewall` so an INPUT-only apply (Docker not yet up) cannot leave
  published peer ports unprotected after a later `docker start` (**DD-93**).
- **Fixed:** `master-firewall --check` asserts DOCKER allow rules
  (ESTABLISHED, Tailscale, qBit/wg RETURN) and WAN DROP order in INPUT /
  DOCKER chains.
- **Fixed:** `/etc/docker/daemon.json` restores **DD-8** `jq` merge (dns
  only); other daemon keys are preserved.
- **Fixed:** `DOWNLOADS_PATH` allowlist (`/downloads`, `/data`,
  `/srv/downloads`) before recursive ownership repair.
- **Fixed:** FileBrowser container removal is scoped to this Compose
  project / known images; legacy volume names only when unused.
- **Changed:** Compose `no-new-privileges=true` (Docker 29 deprecation).

### 2026-08-09 — v2-58: FileBrowser /config bind (no anonymous volume)

- **Fixed:** Classic FileBrowser image declares `VOLUME /config`; compose now
  binds `__FILEBROWSER_DATA_DIR__/config` so Docker does not create an
  anonymous volume. Install creates the host dir and uses `docker rm -fv`
  so a prior anonymous `/config` volume is removed on re-run.

### 2026-08-09 — v2-57: qBittorrent WebUI default 61006

- **Changed:** Fresh-install `QBIT_UI_PORT` default `61009` → `61006`
  (loopback). Caddy `qbit.*` follows the token. Existing hosts pick this up
  on re-run (port is not stored in `config.env`).

### 2026-08-09 — v2-56: classic FileBrowser (replace Quantum)

- **Changed:** Compose file UI is again `filebrowser/filebrowser` (digest-
  pinned `v2.63.23`) with `--disable-exec`, host Bolt DB at
  `/etc/master-stack/filebrowser-data`, root mount `/downloads` → `/srv`
  (**DD-92**). Quantum image + `filebrowser.yaml` removed.
- **Kept:** rclone WebDAV on `61003`, UI port `61007`, Caddy `file.*`.

### 2026-08-09 — Restore v2-51 (FileBrowser Quantum + rclone WebDAV)

- **Changed:** Abandoned the copyparty (v2-52/53) and FileGator (v2-54/55)
  experiments. Working tree restored to the **v2-51** surface: FileBrowser
  Quantum on loopback `61007`, separate rclone WebDAV on `61003`, qBit UI
  `61009`.

### 2026-08-09 — v2-51: memorable FileBrowser / qBit UI defaults

- **Changed:** Fresh-install loopback UI defaults in `defaults.env`:
  `FILEBROWSER_UI_PORT=61007`, `QBIT_UI_PORT=61009` (same 6100x odd
  series as peer/WebDAV). Portainer 9443 and wg-easy 51821 unchanged.
  Existing hosts keep `config.env` values on re-run.

### 2026-08-09 — v2-50: memorable high default peer/WebDAV ports

- **Changed:** Fresh-install defaults in `defaults.env`:
  `WG_PUBLIC_PORT=61001`, `WEBDAV_PORT=61003`, `QBIT_PUBLIC_PORT=61005`.
  Existing hosts keep `config.env` / `state.env` values on re-run.

### 2026-08-09 — v2-49: structural doc sync + Stage 7 UI Caddy checks

- **Docs:** `v2-contract`, `v2-architecture`, `master-stack.mdc`, root
  README/SESSION aligned with shipped behaviour (OnFailure/DD-87, Infuse
  bare-IP/DD-78, selective downloads/DD-84, R10 WebDAV, R18 peer
  TCP+UDP, WAN publish settled, DNS acceptance observed).
- **Added:** Stage 7 curls `portainer`/`wg`/`qbit`/`file` through Caddy
  and requires a non-5xx status (**DD-88**, contract §14.13).
- **Export:** portable `app/` rebuilt for `v2-49`.

### 2026-08-09 — v2-48: Caddy OnFailure runs refresh-tailnet

- **Added:** Caddy drop-in `OnFailure=refresh-tailnet-config.service` so a
  stale-state / start failure triggers refresh immediately instead of
  waiting for the five-minute timer (**DD-87**). Silent IP change with
  Caddy still active remains timer/`WantedBy=tailscaled` territory.

### 2026-08-09 — v2-47: refresh-tailnet warn names Online

- **Fixed:** `warn_if_tailnet_unusable` now prints both `BackendState` and
  `Online` so a Running-but-offline node is not logged as a bare
  `BackendState=Running` contradiction (**DD-86**).

### 2026-08-09 — v2-46: wait-tailnet matches state IP on the interface

- **Fixed:** `wait-tailnet-addr` (Caddy `ExecStartPre`) no longer treats
  “any IPv4 on `tailscale0`” as ready. When `TAILSCALE_IPV4` is set (from
  `state.env` via `EnvironmentFile`), that exact address must be present;
  a live interface with a different address fails immediately as stale so
  Caddy does not sit in `activating` until the next refresh (**DD-85**).

### 2026-08-09 — repository is v2-only

- **Removed:** root `install.sh`, `legacy/`, `versiyon/`, root `test/`,
  root `scripts/`, `SECURITY_REVIEW.md`, `TODO.md`, and v1-centric docs
  (`docs/architecture.md`, `docs/profiles.md`, `docs/testing.md`,
  `docs/v2-test-migration.md`). Active code and docs are `v2/` plus
  `docs/v2-*.md`, `docs/design-decisions.md`, and the changelog.
- **Changed:** root `README.md`, `CLAUDE.md`, and `SESSION.md` rewritten
  for the lean v2 tree; `docs/v2-contract.md` no longer describes a
  parallel v1 production path.

### 2026-08-09 — v2-45: selective downloads repair + P3 hygiene

- **Changed:** Stage 3 only repairs mismatched UID/GID/mode under
  downloads (`chown -h`, selective `chmod`) — no full-tree rewrite
  (**DD-84**).
- **Changed (P3):** refresh timer drops `Requires=`; wait/refresh comments
  no longer imply host WebDAV; Caddyfile `caddy fmt`-aligned; firewall
  drops unused `WAN_IPV4` and checks IPv6 `packet-too-big`; export uses
  epoch mtimes + `gzip -n` and stable `PORTABLE_BUILT_AT`.
  `render_template` keeps trailing newlines so `caddy fmt` stays clean.
- **Skipped:** Stage 7 WG listen/CGNAT checks (manual ops).

### 2026-08-09 — v2-44: pin all Compose images to tag@digest

- **Changed:** Replace floating `lts` / `stable` / `latest` (and unpinned
  semver) with the live `nrm` digest pins in `defaults.env` (**DD-83**):
  Portainer 2.39.5, FileBrowser 1.5.1-stable, qBittorrent
  `5.2.3_v2.0.13-ls469`, wg-easy 15.3, unpackerr 0.15.2; rclone already
  pinned. No automatic pull/updater — pin bumps remain intentional.

### 2026-08-09 — v2-43: WebDAV healthcheck + dedicated `webdav` network

- **Added:** Compose `webdav` healthcheck — unauthenticated `wget` must see
  HTTP `401` (auth gate up; no credentials in the probe) (**DD-82**).
- **Changed:** `webdav` joins only the named bridge `webdav`, not
  `docker_default` and not `wg`. Not `internal` — that dropped host port
  publish on live Docker 29. Host Caddy → `127.0.0.1:WEBDAV_PORT`
  path unchanged (Infuse / MagicDNS). No memory/pids limits.
- **Added:** Stage 7 `wait_webdav_healthy` + `assert_webdav_network`.

### 2026-08-09 — v2-42: Stage 7 WebDAV read-only via container inspect

- **Fixed:** Stage 7 no longer treats an unauthenticated PUT `401` as proof
  of read-only. It asserts Compose runtime invariants: Cmd contains
  `--read-only`, `ReadonlyRootfs=true`, `/downloads` mount `RW=false`
  (**DD-81**). Auth still checked separately via loopback/Caddy/bare-IP
  `401`.

### 2026-08-09 — v2-41: refresh-tailnet waits for Tailscale IP

- **Fixed:** `refresh-tailnet-config` now runs `tailscale wait --timeout=120s`
  before reading `tailscale0` addresses (**DD-80**). `WantedBy=tailscaled`
  used to fire while BackendState was still `NoState`, soft-skip, and rely
  only on the 5-minute timer. Unit gains `TimeoutStartSec=150s`. Timer kept
  as fallback.

### 2026-08-09 — v2-40: finish host WebDAV migration cleanup

- **Added:** `purge_host_webdav_leftovers` in Stage 4 — removes host unit /
  sbin / `webdav.env`, `master-webdav` user/group, `/downloads` ACL entries
  for that user, and `apt-get purge` of the Debian `rclone` package
  (**DD-79**). Idempotent; does not touch Compose rclone.
- **Verified live on `nrm`:** package/user/ACL gone; webdav container still
  `401` on loopback/Caddy/bare-IP.

### 2026-08-09 — v2-39: bump WebDAV rclone image to 1.74.4

- **Changed:** `RCLONE_IMAGE` from `rclone/rclone:1.69.1` (2025-02) to
  `rclone/rclone:1.74.4@sha256:c61954aa…` (stable 2026-07-08, digest-pinned).
  Compose still loopback-only. Live `nrm`: pull + recreate → rclone
  v1.74.4; loopback/Caddy/bare-IP `401`.

### 2026-08-09 — v2-38: Caddy WebDAV alias for bare Tailscale IPv4

- **Added:** Caddy site
  `http://webdav.${LOCAL_DOMAIN}, http://{$TAILSCALE_IPV4}` so Apple TV
  Infuse can use `http://<tailscale-ip>/` on port 80 without MagicDNS
  (**DD-78**). Compose stays loopback-only.
- **Added:** Stage 7 probe for the bare-IP alias; summary lists both Infuse
  URLs.

### 2026-08-09 — v2-37: purge host WebDAV/rclone leftovers from docs + apt

- **Removed:** host `acl` apt package (only used for the deleted WebDAV
  `setfacl` path). `apache2-utils` remains for `htpasswd`.
- **Docs:** `v2-contract.md`, `v2-architecture.md`, `v2/README.md`,
  `docs/testing.md`, `docs/profiles.md`, and **DD-61** (narrowed by
  **DD-77**) now describe Compose loopback WebDAV — no host unit,
  `webdav.env`, or Tailscale-direct WebDAV bind.
- **Tests:** base-package bats assert no host `rclone` / `acl` install.

### 2026-08-09 — v2-36: WebDAV moves into Compose (loopback)

- **Changed:** WebDAV is a Compose `rclone/rclone` service publishing only
  `127.0.0.1:WEBDAV_PORT→8080`, with `/downloads:ro`, `--read-only`, and
  the existing htpasswd mount. Caddy proxies `webdav.*` to loopback
  (**DD-77**).
- **Removed:** host `master-webdav.service`, `webdav.sh`, `webdav.env`,
  `WEBDAV_SERVICE_USER`, host `rclone` apt package, and refresh-tailnet
  restart of WebDAV (only Caddy remains address-bound).
- **Accepted cost:** WebDAV is down when Docker is down — same as the
  media producers. Infuse path remains `http://webdav.<domain>` via Caddy;
  direct Tailscale `IP:WEBDAV_PORT` bind is gone.
- **Verified live on `nrm`:** host unit removed; `webdav` container on
  `127.0.0.1:65113`; Caddy/loopback `401`; TS-direct closed; health ok;
  refresh bound units = Caddy only; `--check` clean; six containers up.

### 2026-08-09 — v2-35: Compose SSOT cleanups (P2 subset)

- **Removed:** writing `$COMPOSE_DIR/.env` with `WG_ENDPOINT_HOST` (Compose
  never read it; WAN IP changes could force a needless `compose up`).
  Stage 4 deletes any leftover `.env`. Endpoint hint stays in `state.env`
  and the install summary only (**DD-76**).
- **Added:** `DOWNLOADS_PATH` charset gate — absolute path,
  `[A-Za-z0-9._/-]` only, no `//`, no `..` segments.
- **Changed:** qBittorrent `PUID`/`PGID` and unpackerr `user:` use
  `__DOWNLOADS_UID__` / `__DOWNLOADS_GID__` instead of literal `1000`.
- **Deferred:** recursive chown/chmod narrowing (7b); WG listen-port /
  CGNAT checks (8) — not in this revision.
- **Verified live on `nrm`:** re-run to v2-35 removed leftover
  `/root/docker/.env`, recreated five containers once for UID token
  expansion, `--check`/health/WebDAV 401 clean; second unchanged re-run
  skipped `compose up` (`EXIT:0`).

### 2026-08-09 — v2-34: firewall `--check` invariants

- **Added:** `firewall.sh` fails closed on WAN interface drift (live
  default-route `dev` ≠ `WAN_INTERFACE` in `state.env`) on both `apply`
  and `--check`.
- **Added:** jump count must be exactly one for `INPUT→MASTER-INPUT` and
  (when Docker is present) `DOCKER-USER→MASTER-DOCKER`; leftover staging
  chains/jumps matching `CHAIN_STAGING_PREFIX` are rejected.
- **Added:** `--check` asserts WAN SSH ACCEPT (IPv4+IPv6), IPv6 Tailscale
  UDP ACCEPT, and neighbour solicitation/advertisement ACCEPT
  (**DD-75** / P1 invariant slice).
- **Verified live on `nrm`:** helper deploy + `master-firewall` restart;
  `--check` clean; jumps == 1; no staging leftovers; deliberate
  `WAN_INTERFACE` drift fails closed and restores cleanly. Full installer
  re-run for `V2_VERSION` bump still pending.

### 2026-08-09 — v2-33: WebDAV unit change flag survives write

- **Fixed:** Stage 4 wrote `master-webdav.service` via `sed | atomic_write`,
  so Bash ran `atomic_write` in a pipe subshell and
  `V2_LAST_ATOMIC_CHANGED` / `WEBDAV_NEEDS_RESTART` never reached Stage 5.
  Live nrm re-run of v2-32 installed the PartOf-free unit on disk but left
  the old WebDAV PID running. Now uses process substitution so the flag
  stays in the installer shell (**DD-75** follow-up).
- **Verified live on `nrm`:** forced unit change restarted WebDAV; restore
  re-run left unchanged units alone; `systemctl restart tailscaled` kept
  Caddy/WebDAV/dnsmasq PIDs and Tailscale IP, reapplied firewall; Docker
  restart reused the five container IDs, left Caddy/WebDAV alone,
  `--check` passed, health 200 / WebDAV 401, zero failed units.

### 2026-08-09 — v2-32: re-run convergence, firewall/Docker split, PartOf trim

Four small resilience fixes from the post-v2-31 report comparison
(live-validated on `nrm`; **DD-75**).

- **Fixed:** Stage 5 no longer relies on `enable --now` for already-active
  `master-firewall` / `master-webdav`. Changed `state.env`, helper scripts,
  unit files, or `webdav.env` set restart flags (same pattern as
  Caddy/dnsmasq), so port/config edits actually reach runtime.
- **Fixed:** Host INPUT policy no longer `Requires=docker.service`.
  `firewall.sh` applies/checks `MASTER-INPUT` always; `MASTER-DOCKER` is
  skipped cleanly when Docker is down, and still fail-closed when Docker is
  up but `DOCKER-USER` never appears. `PartOf`/`WantedBy` docker still
  re-applies Docker rules when the daemon comes back.
- **Fixed:** Caddy drop-in and `master-webdav` drop `PartOf=tailscaled`
  so a Tailscale restart does not bounce address-bound services when the
  IP is unchanged. Firewall keeps `PartOf=tailscaled`.
- **Fixed:** `tailscale_login` kills a stuck `tailscale up` child (TERM →
  bounded wait → KILL) before retrying; timeout/dead-auth no longer hangs
  on an unbounded `wait`.

### 2026-08-07 — v2-31: single-source cleanups from the optimisation review

- **Changed:** stage 0's port-collision guards use `$DNS_PORT` and
  `$CADDY_HTTP_PORT` instead of the literals `53` and `80`; both keys already
  existed in `defaults.env` and `DNS_PORT` was previously unread.
- **Changed:** `WEBDAV_SERVICE_USER` is now actually used by
  `ensure_webdav_user` and the `setfacl` call. A test asserts it matches
  `User=`/`Group=` in `master-webdav.service`, which is installed verbatim
  and cannot take a variable.
- **Changed:** stage 7 derives the expected container count from
  `docker compose config --services` instead of the literal `5`.
- **Removed:** `V2_CONFIG_SCHEMA`, `NET_RETRY_ATTEMPTS`,
  `ADDRESS_WAIT_DEADLINE_SECONDS` and `WEBDAV_READ_ONLY` from `defaults.env`
  — nothing read them. Read-only is a contract invariant (§6.5) fixed in
  `rclone --read-only`, not a tunable, so it must not look like a key that
  can be flipped. A test now fails if any of them return.
- **Removed:** `Persistent=true` from `refresh-tailnet-config.timer`; it only
  applies to `OnCalendar=` timers and this one is monotonic.
- **Decided:** Tailscale stateful filtering stays **on** (**DD-74**). The
  health warning is expected output here; no container needs the tailnet.
  The accepted cost is that wg-easy peers cannot reach tailnet devices.

### 2026-08-07 — v2-30: MASTER-INPUT no longer depends on ts-input

Final batch from the structural optimisation review
([`docs/v2-optimization-review.md`](docs/v2-optimization-review.md)).

- **Fixed:** `MASTER-INPUT` had no rule for Tailscale's UDP port and relied
  entirely on `ts-input` being present and ordered first. During the
  `tailscaled` restart test, with `ts-input` gone, the WAN `DROP` swallowed
  inbound 41641 while `tailscaled` was still listening. `TAILSCALE_UDP_PORT`
  is now declared in `defaults.env`, carried through `state.env`, and
  accepted on the WAN in both IPv4 and IPv6 chains (**DD-73**).
- **Added:** `refresh-tailnet-config` warns once per run when the tailnet is
  unusable (`BackendState` not `Running`, or `Self.Online` false). The node
  had been deleted from the tailnet for four hours with every unit green and
  `systemctl --failed` empty. This is a stderr line, not a repair path — a
  test asserts the helper never calls `tailscale up/set/login`.
- **Verified live:** both chains carry the rule, `--check` passes, and a
  `state.env` missing `TAILSCALE_UDP_PORT` fails the firewall script closed.

### 2026-08-07 — v2-29: address-bound units wait, fail visibly, and recover

Second batch from the structural optimisation review
([`docs/v2-optimization-review.md`](docs/v2-optimization-review.md)).

- **Fixed:** `refresh-tailnet-config` used `systemctl try-restart … || restart`.
  `try-restart` is a no-op on a failed unit **and returns 0**, so the fallback
  was unreachable and a failed `caddy`/`master-webdav` was never restarted
  when the address came back. It now uses `restart` (**DD-72**).
- **Fixed:** `caddy` had no wait for the `tailscale0` address and no start
  limit, so it restart-looped every 5 s indefinitely without ever reaching
  `failed` — the tailnet surface was down while `systemctl --failed` stayed
  empty. The drop-in now carries `ExecStartPre=wait-tailnet-addr`,
  `TimeoutStartSec=150s`, `StartLimitIntervalSec=600`, `StartLimitBurst=3`.
- **Added:** `v2/scripts/wait-tailnet-addr`, and a recovery pass in
  `refresh-tailnet-config` that restarts an address-bound unit left in
  `failed` even when the address has not changed. No new service, timer or
  watcher — the existing five-minute timer becomes the recovery path.
- **Verified live:** a `master-webdav` failed for 40+ minutes recovered from a
  single refresh run with no address change; a following `tailscaled` restart
  left `caddy` at `NRestarts=0` (previously 29), containers untouched,
  `systemctl --failed` empty, `--check` passing.

### 2026-08-07 — v2-28: IPv6 `MASTER-DOCKER` no longer blocks bridge egress

Found during the structural optimisation review
([`docs/v2-optimization-review.md`](docs/v2-optimization-review.md)) and
verified on `nrm`.

- **Fixed:** IPv6 `MASTER-DOCKER` ended in an unconditional `-j DROP`, which
  also blocked **egress** from the wg-easy bridge, not just WAN ingress.
  wg-easy peers hold a dual-stack address, so every connection to an
  AAAA-resolved host tried IPv6, got nothing, and fell back to IPv4. The
  chain now drops WAN-scoped traffic only and ends with `RETURN`, matching
  the IPv4 chain (**DD-71**).
- **Added:** `master-firewall --check` asserts the WAN-scoped `DROP` in both
  IPv6 chains, and `v2/tests/common.bats` rejects a bare
  `-A "$staging" -j DROP` inside `apply_docker6`. The previous grep-based
  suite would have passed the broken rule.
- **Verified live:** container `ping -6` 100% loss → 0% loss (3.98 ms); WAN
  ingress `DROP` still present; IPv4 chain byte-identical; `--check` passes.

### 2026-08-07 — Live verification of v2-23…v2-27 on `nrm` (no further tune)

Disposable host `nrm` after sync + idempotent re-run of
`2026.08.06-v2-27` (tmux; Stage 0 defaults; full-upgrade skipped; existing
WebDAV htpasswd kept). Results kept; **no timer/firewall/settings change**
after the run.

- **Install / reboot:** `state.env` `V2_VERSION=2026.08.06-v2-27`; units
  active (tailscaled, docker, master-firewall, dnsmasq, caddy,
  master-webdav, refresh timer); `watch-tailnet-addr` absent; peer publish
  IPv4-only (`0.0.0.0:65171/65173`, no `[::]`); `--check` reports critical
  policy OK. Reboot smoke fail=0 (firewall, five containers, Caddy/WebDAV,
  exit advertise `0.0.0.0/0` + `::/0`).
- **Natural Tailscale IPv4 change:** live `100.122.80.61` → `100.122.80.77`
  at ~14:53:52; Caddy/WebDAV stayed on old bind until
  `refresh-tailnet-config.timer` (~14:55:25); state updated; listeners on
  `.77`; `health` HTTP 200. Lag ~1.5 min inside the 5 min
  `OnUnitActiveSec` window. Operator accepted keeping the timer as-is
  (no watcher restore).
- **Exit node (Mac → nrm):** Mac external IP `203.0.113.10` (= nrm WAN).
  Path: Mac `utun4` → nrm `tailscale0` → `FORWARD` (`DOCKER-USER` /
  `MASTER-DOCKER` RETURN on TS → `ts-forward` MARK/ACCEPT) →
  `ts-postrouting` SNAT → `eth0`. Conntrack showed
  `100.103.124.125` rewritten to WAN. `MASTER-INPUT` not on this path.
- **DERP vs direct:** underlay used `Relay fra` while Mac was on
  `172.20.10.0/28` hotspot / `31.142.x` NAT. **Not** caused by
  `MASTER-INPUT`: `ts-input` is first and `udp dpt:41641 ACCEPT` counters
  were live (~1.3 MiB). No firewall change.

Portable export: `v2/app/2026.08.06-v2-27.command` (embedded archive SHA
only; no `.sha256` sidecar).

### 2026-08-07 — IPv4-only public peer Compose binds (`v2-27`)

wg-easy and qBittorrent public ports publish as `0.0.0.0:port:port/...`
instead of dual-stack unqualified maps (no `[::]` peer listeners). Host
IPv6 / Tailscale IPv6 / firewall IPv6 INPUT stay. Version
`2026.08.06-v2-27`.

### 2026-08-07 — Drop `watch-tailnet-addr` (`v2-26`)

Tailscale address updates use only `refresh-tailnet-config`
(`WantedBy=tailscaled` + 5-minute timer). The long-running netlink watcher
unit/script is removed; re-runs disable and delete leftovers (DD-64).
Version `2026.08.06-v2-26`.

### 2026-08-07 — Minimal firewall `--check` content (`v2-25`)

`--check` still verifies jumps and `ts-input` order, and now also asserts
IPv4 WAN DROP on `MASTER-INPUT`/`MASTER-DOCKER` plus WAN ACCEPT for wg UDP
and qBit TCP+UDP. Version `2026.08.06-v2-25`.

### 2026-08-07 — Re-apply firewall on Tailscale restart (`v2-24`)

`master-firewall.service` is also `PartOf=` / `WantedBy=` `tailscaled.service`,
so a Tailscale restart re-runs apply/check and restores `ts-input` vs
`MASTER-INPUT` order. Compose stays uncoupled. Version `2026.08.06-v2-24`.

### 2026-08-07 — Firewall oneshot retry and DOCKER-USER wait (`v2-23`)

`master-firewall.service` uses `Restart=on-failure`, `RestartSec=2s`, and
`StartLimitBurst=5` / 60s so a one-shot apply miss after Docker start is
retried. `firewall.sh` waits up to 10s for `DOCKER-USER` before applying
`MASTER-DOCKER` (DD-59). Version `2026.08.06-v2-23`.

### 2026-08-07 — Drop portable export `.sha256` sidecar

Archive SHA-256 stays embedded in the `.command` as
`PORTABLE_ARCHIVE_SHA256` (local + remote verify unchanged). Export no
longer writes or copies a separate `.sha256` file (DD-70).

### 2026-08-07 — `retry` can wrap bash functions under `timeout` (`v2-22`)

Stage 6 failed on live install with exit 127 because `timeout` cannot exec
a shell function (`apt_get_install_masked_quiet`). `retry` now detects
functions and runs them via `export -f` + `bash -c`. Version
`2026.08.06-v2-22`.

### 2026-08-07 — Doc sync, export sha256, install `acl` (`v2-21`)

Aligns v2 contract/architecture naming and stage table with the live
installer (`TAILSCALE_IPV4`, current stage ownership). Portable export
embeds/verifies archive SHA-256 and extracts on the host via a staging
directory before replacing `v2/`. Stage 1 installs the `acl` package for
`setfacl`. Version `2026.08.06-v2-21`.

### 2026-08-07 — Downloads tree owned 1000:1000 for stack R/W (`v2-20`)

Every run sets `${DOWNLOADS_PATH}` recursively to `DOWNLOADS_UID:GID`
(default 1000:1000), dirs `0775` / files `0664`. FileBrowser runs as the
same uid:gid. qBittorrent/Unpackerr already used 1000:1000. Version
`2026.08.06-v2-20`.

### 2026-08-07 — Broader stage-7 success checks (`v2-19`)

Stage 7 now verifies DNS via both loopback and Tailscale IPv4, out-of-domain
`REFUSED`, WebDAV 401 through Caddy, unauthenticated write rejected, public
wg/qBit publishes, and loopback-only UI publishes. Version
`2026.08.06-v2-19`.

### 2026-08-07 — Cheaper re-runs: gated upgrade and skip unchanged restarts (`v2-18`)

Re-runs prompt before `apt full-upgrade` (default no; first install and
`V2_FULL_UPGRADE=1` still upgrade). dnsmasq/Caddy restart and
`docker compose up` run only when their files changed or the service is
down. Edge packages are masked/installed only when missing. Version
`2026.08.06-v2-18`.

### 2026-08-07 — Tighten SSOT for firewall, services, wg bridge (`v2-17`)

Firewall no longer falls back to hardcoded ports/chain names; it requires
them from `state.env` (including `CHAIN_STAGING_PREFIX`). Stage 7 DNS checks
iterate `SERVICE_NAMES`. wg-easy bridge addresses move into `defaults.env`
and Compose tokens. Version `2026.08.06-v2-17`.

### 2026-08-07 — Reorder ts-input without INPUT gap (`v2-16`)

`master-firewall` inserts `MASTER-INPUT` after Tailscale's `ts-input` when
that jump exists, and `ensure_ts_input_precedence` fixes a wrong order by
adding the correct jump before deleting an earlier one (no
delete-all-then-reinsert window). Version `2026.08.06-v2-16`.

### 2026-08-07 — Restore edge fail-closed mask (`v2-15`)

Stage 6 again masks `dnsmasq`/`caddy` across apt + configure so an abort
leaves them off (contract §12). Known apt “preset … masked” lines are
filtered from the console; the full apt transcript still goes to the
install log. Drops the short-lived `policy-rc.d` approach (DD-65 revised).
Version `2026.08.06-v2-15`.

### 2026-08-06 — Versioned export apps under `v2/app/`

Each `export-v2` run writes `v2/app/<V2_VERSION>.command` and refreshes
`v2/app/latest.command` (optional Desktop copy with `--desktop`). The old
`v2/dist/` single-name artifact is replaced by this versioned `app/` tree.

### 2026-08-06 — Quiet dnsmasq/Caddy apt install (`v2-14`)

Stage 6 briefly used `policy-rc.d` instead of mask (superseded by `v2-15`).


### 2026-08-06 — Portable single-file macOS export

`v2/dev/export-v2.sh` embeds the v2 runtime into a portable `.command`.
That single file is the only install launcher — separate upload/sync helpers
removed. Asks for SSH host, uploads, starts interactive install; no local
repo at click time.

### 2026-08-06 — Export-ready v2 + edge systemd ordering (`v2-13`)

Caddy/dnsmasq drop-ins gain `After=`/`Wants=tailscaled` (Caddy also
`PartOf=tailscaled` + restart); `master-firewall` waits for `tailscaled`;
WebDAV is `PartOf=tailscaled` with `ReadOnlyPaths=/downloads`; install wraps
in `systemd-inhibit`. Docs/README aligned to the live tree. Version
`2026.08.06-v2-13`.

### 2026-08-06 — Align UDP netbuf floor with legacy (`v2-12`)

`apply_udp_netbuf_floor` writes `/etc/sysctl.d/99-master-stack-netbuf.conf`
with `net.core.rmem_max` / `wmem_max` = `max(current, 16 MiB)` before the
Tailscale package install (M11/DD-18). Forwarding sysctls stay in
`99-master-tailscale.conf` without the previous 7.5M buffer values.
Version `2026.08.06-v2-12`.

### 2026-08-06 — Tailscale address watch via netlink (`v2-11`)

Adds `watch-tailnet-addr` (`ip monitor address` on `tailscale0`) so a live
IPv4/IPv6 change starts `refresh-tailnet-config` within seconds instead of
waiting for the five-minute timer. The timer remains as a safety net.
Version `2026.08.06-v2-11`.

Note on the earlier live IP-change test: production refresh correctly
no-oped when addresses matched; the spurious `CHANGE` lines were from the
temporary test watcher treating journal updates as drift, not from the
timer restarting Caddy/WebDAV.

### 2026-08-06 — qBittorrent peer TCP+UDP (`v2-10`)

Restores the legacy peer publish: Compose maps
`${QBIT_PUBLIC_PORT}` for both TCP and UDP (still 1:1, no WAN IP embed),
and `master-firewall` allows the matching NEW WAN rules in `MASTER-INPUT`
and `MASTER-DOCKER`. Revises R12 (was UDP-only). Version
`2026.08.06-v2-10`.

### 2026-08-06 — Persistent UDP GRO oneshot (`v2-9`)

Installs `tailscale-udp-gro` + `tailscale-udp-gro.service` (`WantedBy=
multi-user.target`, `RemainAfterExit`) so `rx-udp-gro-forwarding` /
`rx-gro-list` are reapplied after every boot. Stage 2 enables the unit
instead of a one-shot inline `ethtool` call. Version `2026.08.06-v2-9`.

### 2026-08-06 — Periodic Tailscale address refresh timer (`v2-8`)

Adds `refresh-tailnet-config.timer` (`OnBootSec=2min`, `OnUnitActiveSec=5min`)
so Caddy/`state.env` catch Tailscale IP changes without a daemon restart.
The oneshot still runs on `tailscaled` start; missing `tailscale0` IPv4 is a
soft skip (exit 0) so the timer does not flap failed. Version `2026.08.06-v2-8`.

### 2026-08-06 — Bind master-firewall to Docker start/stop (`v2-7`)

`master-firewall.service` now `Requires=` / `WantedBy=docker.service` (keeps
`PartOf=`) so a Docker restart restarts the oneshot and re-applies INPUT +
DOCKER-USER policy. Stage 5 uses `enable --now` so the unit stays
`active (exited)` after install. Version marker `2026.08.06-v2-7`.

### 2026-08-06 — v2 wg-easy fixed bridge network `10.42.42.42`

Compose places `wg-easy` on a dedicated `wg` bridge (`10.42.42.0/24` +
ULA `/64`) with static `10.42.42.42` / `fdcc:ad94:bacf:61a3::2a`, matching
legacy isolation from the default Compose network.

### 2026-08-06 — v2 wg-easy healthcheck uses legacy H5 timing

`v2/templates/compose.yaml` now overrides the image HEALTHCHECK with the
legacy block: `wg show | grep interface`, `start_period: 60s`,
`start_interval: 5s` — so Docker does not sit in `starting` for a full
60s interval after `wg0` is already up.

### 2026-08-06 — Allow WAN SSH (TCP 22) in MASTER-INPUT (`v2-6`)

`MASTER-INPUT` accepts inbound TCP `${SSH_PUBLIC_PORT}` (default 22) on the
WAN interface before the terminal DROP, for both IPv4 and IPv6. This is a
host firewall exception only — not a Compose publication. `SSH_PUBLIC_PORT`
lives in `defaults.env` / `state.env`. Version marker `2026.08.06-v2-6`.

### 2026-08-06 — Portainer upstream is HTTPS 9443 again (`v2-5`)

Revises DD-62: Compose publishes `127.0.0.1:9443:9443` (no `--http-enabled`),
and Caddy proxies `https://127.0.0.1:9443` with loopback-only
`tls_insecure_skip_verify`. Version marker `2026.08.06-v2-5`.

### 2026-08-06 — v2 Stage 0 asks for wg public UDP port, not endpoint (`v2-4`)

Stage 0 no longer prompts for a wg-easy DNS/IP endpoint. `WG_ENDPOINT_HOST`
is set from the detected `WAN_IPV4` for first-run UI hints only.
`WG_PUBLIC_PORT` is prompted (default/previous from `config.env`), stored in
`config.env`/`state.env`, and Stage 4 always re-renders Compose so a changed
UDP port republishes `port:port` and the firewall follows on re-run.
Version marker `2026.08.06-v2-4`.

### 2026-08-06 — v2 firewall: `ts-input` before `MASTER-INPUT`, ICMPv6 for NDP (`v2-3`)

`v2/scripts/firewall.sh` now reorders INPUT so Tailscale's `ts-input` jump
sits above `MASTER-INPUT` (IPv4 and IPv6) after every apply, and `--check`
fails if that order regresses. IPv6 `MASTER-INPUT` no longer blanket-DROPs
before essential ICMPv6 (NDP/RA/PMTU/echo); WAN still drops other NEW
traffic, matching the IPv4 shape with a final RETURN. Live nrm had
`fe80::1` stuck `FAILED` and Tailscale `Online=false` because NDP replies
never reached the stack. Version marker `2026.08.06-v2-3`.

### 2026-08-06 — v2 carries DD-10 host WireGuard/ip6tables preload (`v2-2`)

`v2/install.sh` Stage 4 now runs `ensure_wg_kernel_modules` (best-effort
`modprobe` of `wireguard` / `ip6_tables` / `ip6table_nat`,
`/etc/modules-load.d/wg-easy.conf`, functional `wg-easy-probe0` probe) before
Compose is written. `v2/templates/compose.yaml` drops `SYS_MODULE` from
wg-easy (`NET_ADMIN` only), matching legacy DD-10 / H1. Live nrm failure mode
was unhealthy wg-easy after `wg-quick` could not load `ip6_tables` inside the
container. Version marker `2026.08.06-v2-2`.

### 2026-08-05 — a probe in a predicate position puts back what it measured (`Q1-39`)

Stage 4 pass item D5, the last of the five, and the one that changes no
behaviour today.

`probe_compose_runtime` resets four globals on every call:
`COMPOSE_RESTART_TARGETS`, which is the list the repair loop restarts, plus
`WG_SETUP_PENDING`, `WG_CONFIGURATION_INVALID` and `WG_OBSERVED_PORT`, which
are what the operator report and `--status`'s key=value line are built from.
Three of its call sites measure and consume those values. Two only ask a
yes/no question in a postcondition chain — and silently replaced the
measurement the cycle had already acted on with a measurement of the world
*after* the repair.

Nothing reads them after either postcondition, so this was latent rather than
live, and the ordering was checked rather than assumed: the last reader is the
eligible-target loop and both sites are below it. It is fixed because the
failure it sets up is invisible — the next line added under the postcondition
inherits the wrong data with nothing in the code to suggest it.

The two postcondition positions now call `compose_runtime_still_ok`, which
saves the four globals, runs the probe, restores them and returns the probe's
verdict. The three measurement positions are unchanged.

Six cases added. One derives the rule from the reconcile script's own call
sites, so a future predicate-position call fails the suite instead of quietly
clearing four globals; another pins the ordering that makes the wrapper's
reads safe under `set -u`, since nothing declares those globals at top level.
Seven mutations run and each caught — one only after the case that missed it
was rewritten to make the two measurements disagree.
`./scripts/check-all.sh` clean at 264 cases. See DD-57.

### 2026-08-05 — the Compose stack stops depending on the Tailscale address (`Q1-38`)

Stage 4 pass item D1, and DD-52's sibling from the same commit.

`V1-3` (`9b8d754`) deleted `"${TAILSCALE_IPV4}:${WEBDAV_PORT}:…"` when the
sftpgo container became the host rclone service — the only place compose ever
used that address. Two consumers were left pointing at it: `master-compose-ipv4`
blocked up to 120 seconds requiring it and `exit 1`ed otherwise, so the whole
stack failed to start without Tailscale; and reconcile routed
`TAILSCALE_ADDRESS_CHANGED` into `ADDRESS_CHANGED`, which stopped and started
all five containers.

Measured on the test host: `.env` carried the address, `compose.yaml`
referenced it zero times, it occurred zero times in the fully rendered `docker
compose config`, every container port bound `127.0.0.1` or the public IPv4, and
the only listeners on it were host services — dnsmasq :53, Caddy :80, rclone
WebDAV :65113, tailscaled :53071.

The helper now records the Tailscale address when it arrives and starts the
stack anyway when it does not. `PUBLIC_IPV4` remains a hard precondition, with
its wait unchanged, because it *is* interpolated into three container port
bindings.

The subtle half is the refresh. Removing the stack restart removes the only
thing that used to rewrite `.env`, and `.env` is what
`TAILSCALE_ADDRESS_CHANGED` is computed against — left alone, the flag would
latch at 1 and restart dnsmasq, Caddy and WebDAV every twenty minutes forever.
Reconcile now refreshes the record itself by running the same helper, which
only rewrites `.env` atomically and touches no container. Both the refresh and
the final postcondition ask one shared predicate,
`compose_env_addresses_current`, so the condition that triggers the repair and
the condition that accepts it cannot disagree.

The three services that genuinely need the address still repair directly on
`TAILSCALE_ADDRESS_CHANGED`, and a case pins all three arms — deleting the
signal along with the restart is the obvious way to get this wrong. Eight
cases added, five mutations run and each caught. `./scripts/check-all.sh`
clean at 258 cases. See DD-56.

### 2026-08-05 — every wait that promises a duration now measures one (`Q1-37`)

Stage 4 pass item D4, finishing what DD-50 and DD-52 started.

Four waits counted iterations while their error message named a number of
seconds: Stage 2's tailscaled-socket wait, `master-compose-ipv4`, reconcile's
address-ready retry and `master-webdav-serve`. Each now computes a deadline
from `SECONDS`, and each message interpolates the bound instead of repeating a
literal, so the number printed and the number honoured cannot drift apart
again.

The invariant is not "no `seq` loops" — it is that a loop must not count turns
while its message promises seconds. A survey of all nine remaining `for _ in
$(seq 1 N)` sites found exactly one more that qualified (the socket wait),
which is why this is four sites and not the three the pass originally listed.
The others are correctly iteration-bounded and were left alone:
`create_staging_chain` and `create_ts_guard_staging_chain` retry a random-name
collision with no `sleep` at all, and the post-repair retries claim no
duration. A whole-file test now states the rule that way rather than banning
`seq`.

The two sites that are whole embedded scripts were extracted and run for real
against a stub `ip` costing three seconds per probe with their budget cut to
three seconds: each exits 1 within three to seven seconds and names the bound
it honoured, where an iteration-bounded loop takes about four times as long.

`tailscale_daemon_ready` was found in the same survey and deliberately left:
it counts thirty turns around an untimed `tailscale status --json`, so its
probes are unbounded, but its caller claims no duration — recorded in
`TODO.md` instead. Five cases added, four mutations run and each caught.
`./scripts/check-all.sh` clean at 250 cases. See DD-55.

### 2026-08-05 — reconcile stops reading config from a bundle it rejected (`Q1-36`)

Stage 4 pass item D2, and the missing half of DD-46.

`state_value` preferred `$CANONICAL_DIR/state.env` whenever that file was
merely *readable*, and never consulted `CANONICAL_BUNDLE_INVALID`. Measured on
the test host: with `STACK_VERSION` edited in the canonical copy so
`sha256sum -c` fails, a single `--status` run printed both `canonical_bundle=1`
with "canonical kopyadan geri yükleme yapılmayacak" and `Kurulum sürümü :
TAMPERED-NOT-A-REAL-VERSION`, read from that same rejected file, while the
intact `/etc/master-stack/state.env` sat unread.

`STACK_VERSION` was only the visible symptom. The same call supplies
`QBIT_PUBLIC_PORT`, `WG_PUBLIC_PORT`, `WEBDAV_PORT`, `LOCAL_DOMAIN`,
`WG_ENDPOINT_HOST` and `DOWNLOADS_PATH`, which drive the DNAT checks, the
port-binding checks, the DNS/Caddy probes and the disk thresholds — so a bad
bundle could steer what reconcile repairs toward, not just what it prints.

The canonical copy is now read only once `canonical_bundle_ok` has returned
true. Both entry paths needed it: the main path decides at the existing gate,
and `--status` — which calls `state_value` about a hundred lines before that
gate, and is where the contradiction was measured — now decides first.
Verified side by side against the same tampered bundle: `Q1-34` prints the
tampered string, `Q1-36` prints the real value and says which file it fell
back to.

DD-46's gate test pinned the literal `if ! canonical_bundle_ok; then`, which
the new success arm does not use; it was rewritten to assert the behaviour
rather than the syntax, and its own non-final `! grep` converted to an
explicit status capture. Four cases added, three mutations run and caught.
`./scripts/check-all.sh` clean at 245 cases. See DD-54.

### 2026-08-04 — the media-tree chown stops dereferencing (`Q1-35`)

Stage 4 pass item D3, and the most serious thing the pass found.

Stage 4 repairs ownership across the media tree with `find
"$DOWNLOADS_PATH/media" \( ! -uid 1000 -o ! -gid 1000 \) -exec chown
1000:1000 {} +`. `find` defaults to `-P` and so does not follow symlinks — it
reports them — and `chown` without `-h` dereferences the path it is given. A
symlink in the tree owned by anything other than `1000:1000` therefore matched
the predicate and aimed the ownership change at its target, anywhere on the
host.

Measured on the test host before the fix: a root-owned
`tree/innocent.mkv -> /tmp/d3/SENTINEL` stayed at `0:0` while the sentinel
moved from `0:0` to `1000:1000`. Reachability was measured too — the tree is
bind-mounted into `qbittorrent` as `/downloads`, `docker exec qbittorrent id`
returns `uid=0(root)`, and a symlink planted from inside the container shows
up on the host as `lrwxrwxrwx 1 0 0`, exactly the ownership the predicate
selects. Since `1000` is the uid qbittorrent's own process runs under, the
target becomes a file the container can read or write. It fires on the next
installer run.

The fix is `chown -h`. After it, the same fixture leaves the sentinel at
`0:0`, moves the symlink itself to `1000:1000`, and still repairs a genuine
`0:0` regular file. `-xdev` was considered and deliberately left out; see
DD-53.

Three cases added in a new `test/media_tree_chown.bats`, which runs the
command extracted from `install.sh` against a fixture tree with a stub `chown`
on `PATH` — no root, no real ownership touched. Three mutations run and each
caught. `./scripts/check-all.sh` clean at 242 cases.

### 2026-08-04 — `--check` stops waiting for a value no rule uses (`Q1-34`)

First item of a fresh stage-by-stage pass over Stage 3, derived against the
current code rather than from the old B list.

`docker-tailscale-fw` opened with a 300-second gate that resolved three values:
`WAN4_IF`, `PUBLIC_IPV4` and `TAILSCALE_IPV4`. The third has been dead since
`V1-3` (`9b8d754`), which replaced the sftpgo container with the host rclone
WebDAV service and deleted both of its uses — the `--ctorigdst
"$TAILSCALE_IPV4" --ctorigdstport 65113` allow in `MASTER-TS-FORWARD` and the
matching entry in `check_ipv4_policy`'s expected set. The gate that produced it
was left in place. In the helper's 489 lines the name occurred four times, all
four inside that gate.

Measured on the test host against the deployed helper, byte-identical to the
repository's: a healthy `--check` returns in 0.162 s; with no IPv4 on
`tailscale0` it returns in 305.9 s and the error names the Tailscale branch, so
`check_policy` was never reached.

Reconcile calls `--check` three times a turn, and at the unconditional first
call a non-zero exit is indistinguishable from real policy drift — the wait
changes nothing except when the answer arrives. It then sets
`STACK_RESTART_REQUIRED`, spending `master-compose`'s restart budget, stopping
the stack, restarting `docker-tailscale-fw.service` (whose `apply` pays the
same gate again) and re-checking. On an addressless node that is roughly
fifteen of the timer's twenty minutes, plus a stack bounce.

`TAILSCALE_IPV4` is removed. The remaining resolution splits into
`resolve_wan_ipv4` (one attempt) and `wait_for_wan_ipv4` (a `SECONDS`-based
deadline, so the printed 300 seconds is the real bound — the 305.9 s
measurement was the old loop counting iterations, DD-50's finding in the other
program). `apply` waits, because `PUBLIC_IPV4` is interpolated into three
`MASTER-DOCKER` rules; `--check` resolves once and reports immediately.

The apply-side risk was measured rather than argued. A 200 ms probe across a
real reboot showed `ts-forward` present in both families with the `FORWARD`
jump installed at +1.16 s, while `tailscale0` had no IPv4 until +1.37 s. The
chain `ensure_forward_prefix` waits for is ready before the address, so the
removed gate was never what protected it.

Seven cases added. Five mutations run and caught; the fifth also exposed that
two of the new cases, written as `! resolve_wan_ipv4`, could not fail — bash
exempts `!`-inverted commands from `set -e` unless they end the test. Those now
capture the status. `./scripts/check-all.sh` clean at 239 cases. See DD-52.

### 2026-08-04 — Stage 2 bounces the daemon, not the stack (`Q1-33`)

Second item from the audit's B list. On a **reinstall**, every systemd job
Stage 2 enqueued against `tailscaled` reached the whole service stack, because
two drop-ins written later in the same run make `tailscaled` its runtime
anchor: `98-master-stack.conf` and `99-caddy-tailnet.conf` declare `Wants=` on
`docker-tailscale-fw`, `master-compose`, `master-webdav` and `caddy`, and those
four declare `PartOf=tailscaled.service` back. On a fresh install neither half
exists yet, which is why this was invisible.

Measured on the test host with the reconcile timer stopped and reconcile
confirmed inactive: `systemctl enable --now tailscaled` against an *already
active* `tailscaled` started `caddy` and `master-webdav` from inactive — and
returned in 0 seconds while `master-compose` was still `activating`. The pulled
jobs are not waited on, which is the bad news rather than the good: they run
concurrently with the rest of the installer. `master-compose` takes no lock —
neither its `ExecStart` (`docker compose up`) nor its `ExecStartPre`, which
rewrites `/root/docker/.env` — so the installer's own `master-stack.lock` does
not exclude it. A background compose run against the *previous* version's
`compose.yaml` overlaps Stage 4 rewriting that file and Stage 5 running its own
compose commands on the same project.

The case that bites is the repair reinstall: when all four units are active
`enable --now` is a no-op, which is why every upgrade on the test host looked
clean. They are inactive precisely when someone reruns the installer because
something is broken.

Two mechanisms, so two changes. A start job pulls `Wants=`; a restart job
propagates through `PartOf=`, and that clause lives on the four stack units,
not on `tailscaled` — deleting the drop-in would have silenced the first and
left the second. Stage 2 now enables `tailscaled` and starts it only when it is
not already running, and the login retry loop's daemon reset carries
`--job-mode=ignore-dependencies`, which suppresses both. Verified live: the
isolated restart bounced the daemon while `caddy`/`master-webdav` stayed
inactive and `master-compose`'s start timestamp did not move.

Three corrections to the audit note: it named the login-retry restart as the
trigger, but that runs only when a reinstall also needs a fresh login, while
the `enable --now` runs every single invocation; the affected set is four units
including `caddy`, which is Stage 6; and its proposed
`systemctl stop master-compose.service` would not have helped, since the
`Wants=` pull starts it straight back and the other three are uncovered.

The operator recovery hint still prints the plain `systemctl restart
tailscaled` — that is advice for a human running it with the installer
stopped, where pulling the stack up is the point. Five mutations run and
caught; a sixth (flag after the unit name) was measured on the host and turns
out not to be a defect, so the test pins the flag reaching `systemctl` in one
invocation rather than pinning argument order.
`./scripts/check-all.sh` clean at 232 cases.

### 2026-08-04 — One definition of "online", and waits that count time (`Q1-32`)

First item from the audit's B list. `tailscale_is_online()` decided from
human-readable output — `tailscale status --self | head -n 1`, true when the
line was non-empty and lacked the substring `offline` — standing next to two
JSON-based siblings, and it was the only one of the three with no tests.

It was not merely fragile. With `BackendState=Starting` the self line prints
and contains no "offline", so Stage 2's final 180-second gate could pass on a
node that was not Running. Its three call sites now use
`tailscale_login_complete()`, which requires `BackendState == "Running"`,
`Self.Online == true`, a non-empty `Self.ID` and non-empty `TailscaleIPs` —
and which already has fifteen test cases.

Both Stage 2 waits changed with it. `tailscale_login_complete` wraps
`tailscale status --json` in `timeout 3`, so against a wedged daemon
`for _ in $(seq 1 90); do …; sleep 2; done` would run 450 seconds while
printing "180 saniye içinde". Both now compute a deadline from `SECONDS`, the
idiom `tailscale_interactive_login` already uses, so the printed durations
hold whatever a probe costs.

Two corrections to the audit note: this does not take three definitions to
one — reconcile's `tailscale_online()` is in a separately generated script and
stays, so two JSON-based definitions remain in two programs and the
text-parsing one is gone. And the note missed the loop-duration consequence
entirely. Reconcile's predicate is deliberately left looser: it answers "is
this established node still online", not "did registration complete".

Five mutations run and caught, including one that keeps the deadline's shape
but moves it 30 seconds later — that one fails the wall-clock case after ~33
seconds, which is what shows the timing assertion measures the bound rather
than passing vacuously. Live-verified on `nrm`: the already-connected branch
ran, Stage 2 passed, `--check` rc=0. `./scripts/check-all.sh` clean at 224
cases.

### 2026-08-04 — Live verification of A1–A5 on the test host, and two defects it found (`Q1-31`)

`Q1-26`…`Q1-30` were upgraded onto the `nrm` test host (`Q1-22` → `Q1-31`,
in place, so the Tailscale login was skipped and the generation N→N+1 path
was exercised). Two defects surfaced that review had not.

**The restart exemption consumed the budget it was meant to bypass.** `Q1-30`
called `record_container_restart` on the exempt path too, so a legitimate
Caddyfile restore stamped the cooldown and a genuine caddy failure three
minutes later was refused for fifteen minutes — caddy sat `inactive` while
reconcile reported `cooldown içinde`, strictly worse than before `Q1-30`.
Each block now sets an explicit `*_RESTART_EXEMPT` flag and stamps only when
the budget path was actually taken. The brake still engages one restart
later, which is the intended semantics.

**The drift report promised a restore it would not perform.** With the bundle
invalid, reconcile printed "canonical kopya geri yüklenecek" and then
correctly withheld the restore — the sentence predates `Q1-27` and was
written when a restore always followed. The state/DNS/Caddy and filebrowser
policy lines are now conditional and say the restore will not happen.

**What the host confirmed.** A2: a broken canonical file mode reported the
bundle failure, repaired `net.ipv4.ip_forward` 0 → 1, left the drifted
Caddyfile alone, kept caddy running, exited 1 with `canonical_bundle=1`;
restoring the mode restored the file and exited 0. A3: the installer failed
at Stage 7 on the first attempt and `cleanup_master_setup` correctly kept the
published generation `current` pointed at. A4: the wg-easy port diagnostic
appeared **exactly once** in a reconcile run (four copies before), and
`wg_setup=`/`wg_config=` appear in `--check` and `--status`. A5: an exempt
restart leaves no stamp, the next failure is repaired, the one after that is
braked, and dnsmasq was repaired in the same run — per-unit scoping holds.
Incidentally `Q1-23`'s `tailscale_prefs` stayed 0, so `--ssh=true` took.

**A1 is not verifiable on this host by construction** — Stage 1's `iptables`
package always provides `ip6tables`, so the guard cannot fire. Stated rather
than glossed.

Unrelated to A1–A5, the upgrade surfaced a Docker Compose behaviour worth
recording: recreating `qbittorrent` left it running under the temporary name
`<id>_qbittorrent` with the `com.docker.compose.replace` label, never renamed
back. Stage 7 correctly failed, and reconcile correctly could not repair it —
it restarts by name. Logged in `TODO.md`.

`./scripts/check-all.sh` clean at 217 cases.

### 2026-08-04 — Every unit on the `OnFailure` arc is restarted behind the repair cooldown (`Q1-30`)

Fifth item from the stage-by-stage audit. The original note was "document the
circular arc"; measuring it turned up more than documentation.

Five units declare `OnFailure=master-network-reconcile.service` and reconcile
restarts all five, so every edge runs both ways. The synchronous case cannot
spin — the `OnFailure` job is raised while reconcile is still active and
systemd merges it into the running job — and the arc terminates at reconcile,
which carries neither `OnFailure=` nor `Restart=`. The asynchronous case is
the real one: a daemon that starts cleanly, lets reconcile exit, then dies
seconds later trips `Restart=on-failure`, hits its start limit, fails, and
fires `OnFailure` with reconcile inactive — invoking reconcile immediately
instead of on the twenty-minute timer.

`master-webdav`, `dnsmasq` and `caddy` were the only restart paths in
reconcile with no `restart_budget_available` gate, and they are also the three
arc units with `Restart=on-failure` plus a `StartLimit`. Each called
`systemctl reset-failed` first, which clears systemd's start-limit counter —
so the arc's three most restart-prone units had both brakes removed, one by
omission and one deliberately. DD-21 already defines the cooldown as "a brake
on the event-driven (`OnFailure`) paths" and `docs/testing.md` already calls
it "the only thing between a repeatedly-failing repair and a restart loop";
both were written while three of five arc units bypassed it.

All three now go through the budget, reporting `cooldown içinde;
tekrarlanmadı` and setting `RECOVERY_FAILED=1` when deferred, exactly like the
four paths that already did. `reset-failed` stays — without it a unit parked
in "start request repeated too quickly" could never be recovered — but is
unreachable until the budget allows. A Tailscale address change and a
canonical config restore bypass the cooldown, matching the exemption
`master-compose` already had for `ADDRESS_CHANGED`; `*_INACTIVE` and
`*_RUNTIME_DRIFTED` do not. `systemctl start master-compose.service` is left
ungated on purpose and the reason is written down.

On a live host a downed caddy is now restarted at most once per fifteen
minutes rather than once per reconcile run. Scheduled runs are unaffected —
DD-21 set the interval to twenty minutes precisely so it exceeds the cooldown.

`test/onfailure_arc.bats` derives the arc's unit set from install.sh's own
`OnFailure=` lines and walks every top-level if-block of the reconcile script,
so a new unit wired onto the arc and restarted unbraked fails the suite on its
own. Seven mutations run, seven caught. The systemd job-merging claim is
reasoning about documented behaviour, not a measurement.
`./scripts/check-all.sh` clean at 215 cases.

### 2026-08-04 — `probe_compose_runtime` measures; the caller reports (`Q1-29`)

Fourth item from the stage-by-stage audit. `check_compose_runtime` was a
predicate, a mutator of four globals, and a reporter — and a reconcile cycle
calls it **five** times: initial detection, the one-second retry, again after
the filebrowser policy repair, as the post-start postcondition, and in the
final sweep. Three of those are pure predicate positions, so each silently
recomputed `COMPOSE_RESTART_TARGETS`, `WG_CONFIGURATION_INVALID` and
`WG_SETUP_PENDING` where the caller wanted only a boolean.

This is DD-33 finished rather than a new idea: that decision moved the
filebrowser password probe out of this same function for this same reason,
and left the two `echo` lines behind. A host with a wg-easy port mismatch
therefore printed the same error four times per cycle, plus the caller's own
line, every twenty minutes, for a condition the script explicitly refuses to
auto-repair. `master-network --status` captures `--check` with `2>&1`, so
those prose lines landed inside the machine-readable `key=value` block.

The function is renamed `probe_compose_runtime`, stops printing, and hands
the observed WireGuard port back in `WG_OBSERVED_PORT`. The detection site
reports both wg-easy conditions once per cycle — there, not in the drift
report, because a pending wg-easy setup deliberately is not drift (DD-12/H6)
and such a host exits before the drift report is reached. `--check` gains
`wg_setup=` and `wg_config=` so `--status` shows them as data.

No live bug was found: every reset was traced against every reader and none
changes a decision today. The five calls are not reduced (three are
postconditions that must re-measure) and the retry asymmetry is left alone —
`master-compose.service` is `Type=oneshot` with `--wait`, so the
postcondition already runs after Docker settled health.

The function had no tests at all; its components did.
`test/compose_runtime_probe.bats` now pins the contract, including DD-12/H6's
rule that a pending setup must not fail the probe. Seven mutations run, seven
caught. DD-12 and DD-33 carry dated corrections — DD-12's claim that
`RECOVERY_FAILED` surfaces a pending setup every cycle stopped being true
when `WG_SETUP_PENDING` was split out, and DD-33 says four call sites where
there are now five. `./scripts/check-all.sh` clean at 206 cases.

### 2026-08-04 — `cleanup_master_setup` asks the shared predicate instead of re-deriving it (`Q1-28`)

Third item from the stage-by-stage audit, and the label in that audit was
wrong: there is no dead branch here. What there was is one question asked
twice, two different ways, inside one function.

`restore_dns_stack_on_failure` — called at the top of `cleanup_master_setup` —
used `canonical_stage_is_current`, which normalises **both** sides with
`readlink -f`. The staged-generation block a hundred lines later resolved only
the `current` symlink and compared it against the unresolved `mktemp` string,
with the root path hardcoded rather than taken from `$CANONICAL_ROOT`. Let any
component above the canonical root be a symlink and the two halves of one
cleanup answer differently: the DNS rollback snapshot is discarded as "already
published" while the directory `current` points at is `rm -rf`'d as "not
published", leaving a pointer to nothing and a `canonical_bundle_ok` that
fails on every later reconcile.

The block now calls the predicate. Five lines and a local variable go; the
`.generation.*` allowlist around `rm -rf` stays. The equality branch stays too
— a signal between the `mv -Tf` swap and the `CANONICAL_STAGE_DIR` reset
reaches it, which `test/dns_stack_rollback.bats` already pins on purpose.

`test/canonical_stage_cleanup.bats` lifts the block out of the un-sourceable
cleanup function and runs it twice: verbatim for the allowlist case, and with
the allowlist re-rooted at the fixture so the deleting branch is observable at
all. Four mutations run, each caught by a specific case.
`./scripts/check-all.sh` clean at 194 cases.

### 2026-08-04 — A failed canonical bundle verification degrades reconcile instead of aborting it (`Q1-27`)

Second item from the stage-by-stage audit. `canonical_bundle_ok` was
reconcile's first gate and it exited 1 on failure, before any detection or
repair ran. One wrong mode bit on one of the nine canonical entries therefore
disabled address re-binding, IP-forwarding repair, Tailscale prefs/netfilter
repair, firewall renewal, container restarts, WebDAV restart and disk
reporting — none of which read the bundle — and the timer went on failing
every 20 minutes with a single line of output. A host that changed public IP
in that state would never pick it up.

The result is now a flag, `CANONICAL_BUNDLE_INVALID`. Reconcile reports the
reason, withholds only the seven bundle-dependent blocks (compose.yaml
restore, filebrowser policy restore, `state.env`/dnsmasq/Caddy restores, and
the dnsmasq/Caddy restarts that follow them), runs everything else, and still
exits 1. This is not a new design: `CANONICAL_CONFIG_INVALID` already answers
the same question for unparseable canonical configs, and Q1-27 applies that
pattern to the broader case. Wherever the narrower flag gates, the new one
gates too.

Degrading is not passing. The flag joins `all_critical_state_healthy`, forces
`RECOVERY_FAILED=1`, and appears in `--check` output as `canonical_bundle=`;
the end-of-run postcondition sweep still calls `canonical_bundle_ok` directly.
The `STACK_SCHEMA` gate right after is deliberately left as a hard exit —
every later check consumes those values — which is why the bundle diagnosis is
printed at flag time rather than in the later drift report.

`test/canonical_bundle_degrade.bats` derives the invariant from install.sh's
own text instead of restating it: it splits reconcile's recovery half into
top-level `if` blocks and requires every block that consumes the canonical
bundle to be gated, so a new ungated restore site fails the suite on its own.
Four mutations were run and all four were caught.
`./scripts/check-all.sh` clean at 183 cases.

### 2026-08-03 — The firewall helper requires ip6tables instead of degrading toward it (`Q1-26`)

First item from the stage-by-stage audit. `docker-tailscale-fw` carried two
contradictory contracts: four branches promised to degrade gracefully when IPv6
tooling was unavailable, and `check_policy` then made the run `exit 1` anyway,
because `check_ipv6_policy` returns 1 outright on a missing binary. The
graceful path could not lead anywhere except that same failure.

It now fails at the top — before the lock, before any chain is touched — with a
message naming the reason. The early returns in `ensure_forward_prefix`,
`apply_tailnet_guard` and `apply_ipv6` are gone, and `apply_ipv6`'s
"DOCKER-USER missing → warn and skip" branch became the hard failure
`apply_ipv4` already used. That branch was **provably dead**: the same chain is
checked earlier by `ensure_forward_prefix`, which kills the helper under
`set -e` before `apply_ipv6` runs.

Requiring rather than skipping is the security-consistent choice. Stage 2 sets
`net.ipv6.conf.all.forwarding = 1`, so continuing without ip6tables would leave
IPv6 forwarding enabled with no Tailnet isolation guard behind it. In practice
nothing changes — the `iptables` package installed in Stage 1 provides
`ip6tables`.

`check_ipv6_policy`'s own missing-binary guard is deliberately kept: it is
**M5**'s remediation and has a Bats case. Removing it would delete a security
finding's test to save four lines.

Measured rather than asserted: the helper was extracted and run with a PATH
containing stub `ip`/`iptables`/`flock` and no `ip6tables`. It now exits 1 in
both modes with **zero `iptables` invocations**, proven by the stub's call log;
the previous revision reached the same exit code only after address resolution
and an `iptables` call in `--check`, and in `apply` installs the entire IPv4
policy first. `./scripts/check-all.sh` clean at 176 cases.

Not live-verified — this path is only reachable when ip6tables is absent, which
the package set makes impossible on the test host.

### 2026-08-03 — `install.sh` now carries no explanatory comments (`Q1-25`)

`Q1-24` had cut the commentary to one-to-six-line "what this does" blocks. The
operator's follow-up removed even those, on the grounds that comments are never
printed during an install and the script is not read in an editor: a comment
nobody reads is not neutral, it stands between the reader and the code and
decays silently because nothing verifies it.

508 further comment lines removed; 5868 → 5356 lines. Nine `#` lines survive
and both classes are load-bearing rather than editorial: eight `#!` shebangs,
which set the interpreter for the heredoc-generated helper scripts, and one
`# shellcheck disable=SC1091`, without which `shellcheck install.sh` — check 2
of `./scripts/check-all.sh` — fails. The eight `# AŞAMA N — …` banners were
**not** kept: each is immediately followed by a `progress_stage_begin N "…"`
call that prints the same information to the screen, so the banner duplicated a
line the code already emits. Stage boundaries are found with `grep -n
'progress_stage_begin [0-7] '`.

**No behaviour changed, and one new risk class was checked for.** Removal is a
blanket rule this time, so a `#` line that was *content* rather than a comment
would be destroyed silently. The only place in this file where that could
happen is a YAML block scalar (`key: |`) inside the `filebrowser.yaml` or
`compose.yaml` heredocs — there are none; the pattern does not occur anywhere
in the file. Every other generated format treats a leading `#` as a comment
(dnsmasq, systemd units, Caddyfile, `sysctl.d`, `modules-load.d`). The proof
that nothing else moved is a diff of both revisions with all whole-line
comments and blank lines stripped: **4790 lines, byte-identical**. Four
blank-line runs created by the removal were collapsed to one.

`./scripts/check-all.sh` clean at 176 cases. `docs/architecture.md`'s stage
table regenerated. `CLAUDE.md` and DD-44 now say plainly that explanations go
into a `DD-` entry, not into the script.

Re-running this revision on a host installed from an earlier one rewrites the
generated config files without their comments — `filebrowser.yaml`,
`compose.yaml`, the dnsmasq conf, the Caddyfile, the systemd units. That is
ordinary content change and the script handles it: the policy file's change
triggers a FileBrowser recreate that preserves the named volume, and a new
canonical generation is published. Expect one extra container recreate and a
dnsmasq/Caddy restart on the first run after upgrading.

### 2026-08-03 — `install.sh` comments cut from 1179 lines to 517 (`Q1-24`)

Comment blocks now state what the code does in one to six short lines and name
a constraint only where the choice would otherwise look wrong. The measurement
narratives, the superseded attempts and the dated evidence stay in
`docs/design-decisions.md`, `SECURITY_REVIEW.md`'s Review History and this
file; a comment that needs the full story points at it (`bkz. DD-42`, `M11`,
`H4`) rather than repeating it.

229 blocks were rewritten. The file went from 6527 to 5868 lines. Stage 2's
login section alone had carried 37 consecutive comment lines before its first
statement, the float-image-tag block 28, and several blocks recounted three
superseded designs before describing the current one.

**No behaviour changed and this is not an assertion.** The transformation was
applied through an explicit line-range map rather than a pattern rule, so
nothing outside the 229 listed ranges could be reached, and the script refuses
to run if any targeted line is not a comment, is a shebang, or is a
`shellcheck` directive. The proof is a diff of both revisions with every
whole-line comment stripped: 5351 lines, byte-identical. The eight `#!`
shebangs, the single `# shellcheck disable=SC1091` and the eight
`# AŞAMA N — …` banners are untouched.

`./scripts/check-all.sh` clean at 176 cases. `docs/architecture.md`'s stage
table was regenerated against the new line numbers. The convention is recorded
in `CLAUDE.md` and DD-44 so the blocks do not grow back.

### 2026-08-03 — Tailscale SSH enabled alongside exit-node advertisement (`Q1-23`)

The interactive login now runs `tailscale up --advertise-exit-node --ssh`
instead of a bare `tailscale up`, so a fresh node asks for both the exit-node
role and Tailscale SSH in the same step rather than waiting for the
`tailscale set` that follows.

`tailscale set` keeps carrying `--advertise-exit-node` and gains `--ssh=true`.
It is not redundant: `tailscale up` runs only when a login is actually needed,
so on an ordinary re-run against an already-joined host it never executes.
`tailscale set` is the unconditional, idempotent path. Naming the flags on
`up` also avoids Tailscale's refusal to silently revert non-default
preferences on a re-login where the profile already advertises an exit node.

Tailscale SSH is now part of the node's steady state rather than a one-time
setting: `tailscale_prefs_ok()` requires `.RunSSH == true`, so the 20-minute
reconcile timer sees a lost `--ssh` as drift and repairs it with the same
`tailscale set` it already used for exit-node/netfilter drift.

**Security note.** `--ssh` makes tailscaled answer SSH on the node's Tailscale
address, authenticated by the tailnet's ACL `ssh` block instead of the host's
`authorized_keys`. It is reachable only from the tailnet — the same boundary
that already governs every web interface here — and adds nothing to the
internet-facing surface. What changes is that tailnet ACL policy, not host SSH
configuration, decides who gets a root shell; a new tailnet's default policy
allows members into their own devices as root with a periodic browser check.
Narrow the tailnet `ssh` block if that is wider than you want. The installer
does not edit account-level ACLs. See DD-43.

Not live-verified.

### 2026-08-02 — `R2.6` refreshed to `Q1-22` and tagged before live verification

At the operator's explicit request, `Q1-22` and `R2.6` are tagged **before**
any live install, so the file can be carried to a machine and tested by
hand. This inverts the branch's normal order — every other release was
tagged only after a real run — so neither tag carries a live-success claim,
and the tag messages, `versiyon/R2.6/README.md` and `versiyon/README.md` all
say so plainly.

`versiyon/R2.6/install-R2.6.sh` refreshed from the `Q1-21` candidate to
`Q1-22`; the export is byte-identical to both tags and to `HEAD`. With the
tags now created, that directory's verification recipe returns to the normal
`git show R2.6:install.sh` form rather than being pinned to a source commit.
`R2.5` / `Q1-20` remains the last release that was actually live-verified and
is reachable through its tag.

What *has* been done for `R2.6`: full static verification clean, and every
behaviour changed since `R2.5` carries a unit test that was checked to fail
against the old behaviour. What has not: running it on a server.

### 2026-08-02 — a slow-to-come-online node no longer discards a successful login (`Q1-22`, DD-42)

`Q1-21` gave the node 15 seconds after `tailscale up` exits zero to reach
the fully verified LocalAPI state, and on expiry restarted the daemon and
asked the operator to authorize again. But exit code zero means the login
*succeeded* — so that path threw away a good authorization, which is
exactly the false-positive class DD-37 exists to prevent.

It was also the stricter of two gates for the same condition: the very
next block in Stage 2 already waits 180 seconds for `tailscale ip -4` plus
`tailscale_is_online`, and only the 15-second one had a destructive
remedy. A node that will not come online after an accepted login has a
connectivity problem, not an authentication one; a fresh browser link
cannot fix that, while the 180-second wait either resolves it or fails
with a clear error.

The grace window is now a fast path rather than a ceiling: it returns as
soon as the node is verified, and on expiry prints an explicit hand-off
note and returns success. The `incomplete` outcome is gone.

Covered by a fourteenth case in `test/tailscale_login.bats` (175 → 176),
mutation-verified against the `Q1-21` behaviour.

### 2026-08-02 — Q1-21 exported as an untagged R2.6 manual-test candidate

At the operator's explicit request, Q1-21 was exported before its exact
automatic browser-login recovery branch was exercised on the Debian target.
`versiyon/R2.6/install-R2.6.sh` is byte-identical to `install.sh` from source
commit `a10a300` and reports `2026.08.02-Q1-21`; the previous R2.5 directory
was retired under the single-current-export rule. The self-contained deploy
wrappers and operator README travel with the candidate.

This changes packaging status, not verification status. R2.6 is labelled as
a manual-test export throughout, while R2.5/Q1-20 remains the latest
live-verified tagged release. No `R2.6` or `Q1-21` tag was created. A later
successful manual run may close out and tag this exact installer; a failure
must produce a new installer revision rather than rewriting this candidate's
recorded identity.

### 2026-08-02 — persistent Tailscale auth-path death is recovered immediately (`Q1-21`, DD-42, M16)

A clean-image install reproduced the operator's original complaint twice in
one run without restarting the installer. Two distinct nodekeys and browser
links were authorized; each created an offline admin-console entry, while the
daemon remained `BackendState=NeedsLogin`, `Self.Online=false`, with an empty
node ID/IP and the LocalAPI health message `register request: http 410: auth
path not found`. The failures arrived 27 and 42 seconds after their links were
issued. Terminating only the second wedged `tailscale up` child exercised the
existing retry path immediately; its daemon restart produced a third link,
which registered successfully as `Running/Online`, and the exact R2.5 install
then completed 7/7 with five containers, reconcile rc 0 and no failed units.

Q1-15's five-minute timeout remains the fallback for slow operators,
unreachable control planes and every unknown stall. Q1-21 adds a structured
LocalAPI classifier instead of returning to journal parsing. Early recovery
requires three consecutive two-second samples that simultaneously show
`NeedsLogin`, offline, an empty node ID and the exact 410 health substring; any
different sample resets the counter. A successful `tailscale up` must now also
produce `Running`, online, a non-empty node ID and at least one Tailscale IP
within a 15-second grace period before the login function returns success.

Thirteen new cases pin the observed JSON shape, incomplete/unknown states, the
successful transient-410 case, the three-sample restart and the one-sample
reset. The suite grows 162 → 175 across thirteen files; `scripts/check-all.sh`
is clean with 12 expected macOS skips. The installer reports
`2026.08.02-Q1-21` and SHA256
`10b746f891f908f98efd92204a8c238c9e46eb500745c9daf68462d9ae3ccaf8`.
The failure signature and the equivalent early child-termination/restart path
were measured live; the exact Q1-21 automatic branch has not yet been run
through a fresh browser authorization, so no live-success or release-tag claim
is made. It was subsequently exported untagged for the operator's manual test.

### 2026-08-02 — correction: `server.database` does exist (DD-27)

Documentation only, no code change. DD-27 claimed there is no config key
for FileBrowser Quantum's database path, "so the environment variable is
the only surface". Wrong: `server.database` is the documented key, and a
newer upstream wording of the first-boot warning names it directly. The
claim came from checking the image's *sample* `config.yaml`, finding no
such key, and generalising to the schema — an inference written up as a
measurement.

The design is unaffected: `FILEBROWSER_DATABASE` is honoured and points at
the right path, so `Q1-12`'s pin still does what it says, and both
surfaces are equally protected as canonical bundle entries. The one rough
edge now recorded is that the policy file does not set `server.database`,
so an operator following the warning's advice opens `filebrowser.yaml` and
finds nothing.

### 2026-08-02 — `Q1-20` closed out and exported as `R2.5`

Live-verified the exact Q1-20 installer on the disposable Debian 13 host,
first as an R2.4 → Q1-20 upgrade and then as an unchanged idempotent rerun.
Both completed all seven stages; the second preserved all five container
`StartedAt` values. Final state was Tailscale `Running/Online`, no failed
units, five running containers and every reconcile drift flag zero.

The Q1-20 paths were then fault-injected. `--check` and `--status` produced
zero FileBrowser login POSTs; two immediate normal reconciles produced one
POST total and one daily stamp. Missing Compose was restored as `root:root
0600` through the real systemd unit without container restarts; edited content
survived, metadata was repaired independently, and a symlink returned rc 1
without being replaced. With tailscaled still active, `tailscale down`
produced `BackendState=Stopped`, `Self.Online=false`, a measured 30-second
wait, `ExecMainStatus=1` and explicit health diagnostics. Returning the same
node online and running the existing firewall/core recovery restored the same
Tailscale IP and a clean check. Repeating that destructive event inside the
15-minute restart budget intentionally failed loudly; the volatile test stamps
were removed and the normal recovery then completed successfully.

Tagged the live-verified installer revision as `Q1-20`, replaced the retired
`versiyon/R2.4/` directory with `versiyon/R2.5/`, and recorded the release on
the close-out commit as `R2.5`. The exported installer is byte-identical to
both repository states and has SHA256
`1762703ecc28e765e454ae32d05a08d3e82a1962734656384a0da12b3a416bb9`.

The same exported file was subsequently tested from scratch after the host
was reset to a clean Debian 13 image. Its live Tailscale browser link completed
in the original installer process, the node came online as an exit-node, and
all seven stages passed with only the expected unfinished-wg-easy warning. An
independent sweep found no failed units, all five containers running,
`master-network-reconcile --check` at rc 0, FileBrowser/Caddy at HTTP 200 and
WebDAV at 401 without credentials / 200 with them. FileBrowser's one-time
missing-database message was followed by `Creating new database` at the
persistent volume path; a controlled restart then logged `Using existing
database`. An immediate unchanged installer rerun preserved the Tailscale
identity, WebDAV credentials and every container `StartedAt` value and again
completed 7/7 without another browser login.

### 2026-08-02 — reconcile no longer hides persistent failures or mutates read-only checks (`Q1-20`, DD-41, H10/H11/M14/M15)

The timer previously used one `defer_or_fail()` path for both genuine
transaction overlap and persistent unavailability. In normal reconcile mode
that helper always returned success, so an inactive Docker/Tailscale daemon or
a missing WAN/Tailscale address could remain unhealthy forever while systemd
recorded every pass as successful. Q1-20 separates transient deferral from
hard failure, allows a bounded 30-second address grace period, and reports
Tailscale `BackendState`, `Self.Online`, health and key expiry without trying
an unsafe automatic logout/login or synchronous core-daemon restart.

`ConditionPathExists=/root/docker/compose.yaml` also made the timer skip the
entire check when the file it needed to diagnose was missing. The condition is
gone. A missing regular target is restored byte-identically from the verified
canonical generation without applying Compose or restarting containers;
modified content remains report-only, metadata is repaired independently, and
directories/symlinks fail closed.

The FileBrowser default-password probe is a real POST login, so `--check` and
`--status` were not actually read-only and the 20-minute timer shared 72 daily
requests with the operator's source-IP rate-limit bucket. The probe now runs
only in normal reconcile mode, only while FileBrowser is running, and at most
once per day using an atomic root-only `/run` stamp. Finally,
`master-webdav.service` now carries
`RequiresMountsFor=$DOWNLOADS_PATH/media`, matching the storage ordering that
already protected Docker/Compose when the media tree is a separate mount.

Fifteen new regression cases cover exit-code classification, address
readiness, Compose path/content states and restoration, audit throttling and
the two unit-file invariants. The Bats suite grows 147 → 162; the full local
verification wrapper is clean with 12 expected macOS-only skips.

### 2026-08-02 — FileBrowser policy repair survives directory mounts and cooldowns (`Q1-19`, DD-40, M13)

The reconcile path copied canonical `filebrowser.yaml` directly to its live
path before checking the restart budget. Two real recovery states broke that
order. If Docker had recreated a missing bind source as a directory, GNU
`install` successfully copied the file *inside* the directory and reported
success; restarting the existing container retained its directory mount. If
the path was a normal drifted file but the restart cooldown was active, the
disk copy became canonical while Quantum kept the old startup-only policy in
memory. The next cycle saw no file drift and never retried the restart.

Q1-19 checks the budget before mutation and keeps a root-only pending marker
until both container health and HTTP respond. Canonical content is staged in
the target filesystem and atomically renamed. A directory, symlink or other
non-regular bind source causes only the `filebrowser` container to be removed
and `master-compose.service` to recreate it; the `filebrowser_data` named
volume is never removed, so the database, users and index survive. Runtime
targets are then remeasured before generic container recovery, avoiding a
second restart and the cooldown collision.

The full installer update path now also compares generated policy content and
metadata. A change removes/recreates only FileBrowser after image pull and
unit verification; an identical healthy container is left untouched. Generic
runtime recovery also recreates an unhealthy FileBrowser, covering the legacy
state where an earlier swallowed removal failure left a stale directory mount
behind a now-regular host path. This closes the separate case where a
successful `install.sh` re-run could publish a new policy file without proving
the already-running container had loaded it.
Eleven regression cases cover normal files, Docker-created directories, absent
containers, daemon/removal failures, action selection, repair ordering and
the installer/runtime recreation couplings. The Bats suite grows 136 → 147.

### 2026-08-02 — deleted Tailscale nodes are classified reliably (`Q1-18`, DD-39, M12)

When a stored Tailscale profile stayed offline for 60 seconds, Stage 2
searched the current run's journal for `node not found`. The check used
`journalctl | grep -q` under global `pipefail`. With enough journal output
after an early match, grep exited immediately, journalctl received SIGPIPE,
and pipeline status became 141: a found match was intermittently reported
as absent. The installer then stopped with a generic control-plane error
instead of clearing the worthless local profile and opening a fresh login.

Q1-18 moves the classifier into a tested helper and uses normal fixed-string
grep with output redirected to `/dev/null`. Grep consumes the whole stream,
so an early match remains true; `pipefail` still preserves a genuine
journalctl failure. The old form was reproduced at rc 141 and the new form
at rc 0 against the same stream. Three regression cases cover a match ahead
of more than a pipe buffer of output, no match, and producer failure.

### 2026-08-02 — failed DNS/Caddy updates restore their files (`Q1-17`, DD-38, H9)

Stage 6 already captured whether dnsmasq and Caddy were active, enabled or
masked, but its EXIT rollback restored only that service-state vector. It
did not restore the six configuration/helper files overwritten before a
later failure. A previously-active service could therefore be restarted
with partial new configuration, or fail to start, while the old canonical
generation remained current.

Q1-17 snapshots those six managed paths under a root-only `/run` directory
before package/config mutation. On failure it stops any currently-loaded
daemons, restores both prior files and prior absence, reloads systemd, and
restarts only the services that were active at entry. The Q1-16 canonical
`current` swap is the transaction commit point: once it succeeds, live and
canonical configuration both represent the new run and rollback is
disabled.

The scope deliberately excludes package uninstall/downgrade and repository
files. Leaving an installed package behind is safe and idempotently handled
by the next run; attempting to reverse apt state would add a much larger and
less reliable transaction. Seven regression cases cover content/absence,
symlinks, unsafe paths, service restart order, commit-point ordering, and
the signal window immediately after the pointer swap; a failed restore is
also required to retain its recovery snapshot for manual intervention.

### 2026-08-02 — canonical bundle publication is actually atomic (`Q1-16`, DD-14, H8)

The Stage 6 code claimed to publish the canonical bundle atomically, but
only the final `SHA256SUMS` rename was atomic; the nine files it described
were copied one by one into the live directory. An interruption between
copies therefore left old and new files mixed behind the old manifest,
causing every later reconcile cycle to stop at its first integrity gate.

Q1-16 builds all nine files plus the manifest in a unique
`.generation.*` directory, verifies the completed generation, and only
then atomically replaces `/usr/local/share/master-stack/current` with a
relative symlink to it. An unpublished partial generation is invisible to
reconcile and the EXIT trap removes it. Regular re-runs retain at most the
active and previous generations.

The first upgrade from R2.4 has an explicit compatibility path: the new
reconcile helper accepts the old flat bundle until Stage 6 publishes the
first `current` pointer. After publication those legacy files are removed,
so a later missing or externally-directed pointer fails closed. Six
regression cases cover generation selection, an incomplete unpublished
generation, an outside-root target, the legacy transition, publish order,
and the existing manifest/source coupling.

### 2026-08-02 — `Q1-15` closed out: tagged, exported as `R2.4`

Tagged `Q1-15` after the live verification described in the previous
entry, and `R2.4` on the close-out commit. Exported to `versiyon/R2.4/`
with the full four files, byte-identical to both tags and to `HEAD`
(`7e2be32d…`), and functionally tested with a real copy-and-verify to the
test host. `versiyon/R2.3/` retired into it, per the rule that a release
directory supersedes the one before it rather than sitting beside it.

**`Q1-14` is tagged but must not be deployed.** It shipped the same
bounded-login feature with the journal-parsing wedge detector that
`Q1-15` removes; the detector can kill a login that is about to succeed.
The `Q1-15` tag message says so, and there is no export for `Q1-14`.

`docs/architecture.md`'s stage table regenerated whole — `Q1-14`/`Q1-15`
added 167 lines inside stage 2 and moved every boundary from stage 3 on
(5726 → 5893 lines). That is the same shape that produced the `V1-15`
drift, which is why the note under the table now records it.

The `Q1` line marker was **not** moved; it still points at the `R2.3`
close-out commit. Moving it means deleting a tag, which is only done on
an explicit request.

### 2026-08-02 — the interactive Tailscale login can no longer hang forever (`Q1-14`/`Q1-15`, DD-37)

Found by a real install wedging at the login step. `tailscale up` was run
bare and waited indefinitely; when the daemon got `410: auth path not
found` it retried the **same dead auth path** forever
(`doLogin(regen=false, hasUrl=true)`) and `tailscale status` kept printing
that dead link as though it were live. The operator's experience was "I
logged in and it is still waiting", with nothing in the script noticing.
Measured: two links, each dead ~13s after issue, four 410 events, and
`tailscale logout` did not clear it — only restarting `tailscaled` did.

The login now runs under `tailscale_interactive_login()`: output streams
to the terminal and the log as before, but if the login has not completed
within 300s the daemon is restarted and a fresh link is printed, up to
three attempts, after which the manual recipe is shown — including the
non-obvious part that `logout` is not enough.

**It deliberately does not try to detect the wedge.** Three versions that
parsed `journalctl` for the 410 were written and all three were wrong, each
caught by running the function against real journal data: a 410 also occurs
during a *successful* login; `journalctl | grep -q` under `pipefail`
reported found matches as failures via SIGPIPE; and an unbounded window let
a later login's success count as recovery for an earlier wedge. A false
positive there kills a login that is about to succeed, so the diagnosis was
dropped in favour of a plain timeout. Full reasoning in DD-37.

Verified with stub `tailscale`/`systemctl` binaries (never-completing login
→ two links, two restarts, correct banners and final recipe; successful
login → returns immediately, no restart) and live on a from-scratch install
plus an idempotent re-run: `STACK_VERSION=2026.08.02-Q1-15`, `--check
rc=0`, five containers, zero failed units.

### 2026-08-02 — three file-manager alternatives investigated, none adopted (DD-36)

No code change. Filestash (proposed as v3), a native non-Docker file manager
with RAR extraction, and Nextcloud in Docker were each researched and each
declined. Written up together in DD-36 because none of them left a trace in
the code, so without the entry the same searches get repeated.

The three findings worth keeping:

- **Filestash's `config.json` is runtime state, not policy** — `Save()` runs
  from `Initialise()`, so it is rewritten on first start. It therefore cannot
  be a read-only bind mount or a canonical bundle entry; reconcile would
  revert admin changes every twenty minutes. Adopting it would have deleted
  the policy-file mechanism this branch is built around. It also publishes
  only `latest`, which is the coarsest float in the bundle.
- **RAR extraction was never a file-manager problem here.** unpackerr already
  watches the whole media tree recursively and extracts rar/zip/7z/iso, so
  any file manager that can write into the tree already gives
  browser-triggered extraction. The one product that extracts RAR itself,
  elFinder, has that exact code path as its CVE history — which is the class
  this project deleted filebrowser's shell-command feature to escape.
- **Nextcloud's blocker is not weight.** Measured first: the host has 7.8 GB
  with 863 MB in use and the five containers total ~130 MB, so it would fit.
  It fails on reading its file list from `oc_filecache` rather than the disk
  — invisible to qBittorrent's and unpackerr's writes until `occ files:scan`
  — and on being unable to skip major versions, which would leave reconcile
  restarting a container it cannot repair.

### 2026-08-02 — `Q1-13` closed out: live-verified, tagged, exported

Verified on the test host *before* tagging, per the convention that tags
follow live verification. The idempotent re-run finished all seven stages
in 28 seconds: `STACK_VERSION=2026.08.02-Q1-13`, `STACK_SHA256` matching
the repository file exactly, `--check rc=0` with every drift flag `0`, no
failed units, five containers up, canonical bundle nine entries with
`sha256sum -c` clean. Stage 7's unpackerr assertion passed with the new
`UN_LOG_FILE_MB=10` entry — its first execution inside a real install.
The containers confirmed both revisions' changes directly: unpackerr now
reports `(3 @ 10Mb)` and `30m` where it reported `(10 @ 0Mb)` and `1m1s`,
and filebrowser carries the pinned `FILEBROWSER_DATABASE`.

Exported as `versiyon/Q1-13/`, byte-identical to the tag and to `HEAD`.
`versiyon/Q1-11/` retired per the standing one-current-directory rule.

The `Q1` line marker was moved on the operator's instruction, from
`Q1-11`'s commit to the branch head — it had fallen two revisions behind.
It now points at the head rather than at a revision tag, because since
`R2.3` the head carries the export directory and the resynced docs as
well as the installer, and `git show Q1:install.sh` returns the same
script either way. `Q1` remains the only tag in this repository that
moves; every `V*`/`Q*`/`R*` tag is a fixed identity.

Tagged `R2.3` on the operator's instruction. What it records is the
close-out: live verification before tagging, the export, and the
documentation resync — the installer is byte-identical to `Q1-13`.

**Export directories are now named after the release, not the revision**
(operator decision, same day, overriding the earlier reading that a
release point gets no directory at all). `versiyon/R2.3/` was created with
the full four files and `versiyon/Q1-13/` retired into it rather than kept
alongside — two directories holding a byte-identical installer is the one
ambiguity the retirement rule exists to prevent, so a release directory
supersedes the revision directory it was cut from. `versiyon/README.md`
now states that rule, and states that a release directory carries the
revision's version string: `install-R2.3.sh` prints `2026.08.02-Q1-13`,
which its own README explains up front so it does not read as a mismatch.
`R2.2` predates this and keeps no directory.

Documentation resynced in the same pass: `docs/architecture.md`'s stage
table regenerated whole (`Q1-12`/`Q1-13` added 48 lines inside stage 4,
moving every boundary from stage 5 on; 5678 → 5726 lines);
`docs/testing.md` gained the run write-up **and** an explicit note that
its Tier 3 log skipped the `Q1-1`…`Q1-11` runs, so the gap is stated
rather than left to look like completeness; `SESSION.md`'s live sections
rewritten, having still described the `v1rc` era — 57 tests, an execution
policy superseded by the standing test-host authorization, and a memory
inventory that no longer matched what exists.

### 2026-08-02 — folding the Quantum policy into `compose.yaml`: investigated, rejected (DD-35)

No code change. The operator asked to move
`/etc/master-stack/filebrowser.yaml` into `compose.yaml`, where the other
four containers are already configured in full. It cannot be done while
`read_only: true` stands: environment variables do not reach `sources`,
`cacheDir` or `signup`, and Compose refuses inline `configs: content:` on
a read-only service (`` `file` is the sole supported option ``) regardless
of where the target path points. Dropping `read_only` measures as free —
zero writes to the writable layer without it — which is exactly the
misleading measurement, since it is a containment control rather than a
functional one. Kept. Written up in DD-35 with the numbers, the gains that
were given up (bundle 9→8 entries, the policy drift/repair path, DD-29's
guard), and the conditions that would reopen it, so the three experiments
are not run a second time.

### 2026-08-02 — unpackerr's file log now rotates; queue heartbeat slowed (`Q1-13`)

Raised by the operator seeing a long repetitive tail in `docker logs
unpackerr`. The 10-second folder scan they suspected is silent; the lines
come from `log_queues` (default `1m1s`, two lines a minute, idle or not).
The Docker stream was already capped at 30 MB by the `json-file` options,
so that part was noise rather than risk.

The part that was a real defect is the *second* log: `UN_LOG_FILE` writes
into `/downloads/.unpackerr/unpackerr.log` and the container reported it
as `(10 @ 0Mb)` — rotation disabled. Upstream documents a 10 MB default,
but that only applies via the TOML config path; configured purely through
environment variables, as here, the value arrives as `0`. Measured at
~280 B/min, ~145 MB/year, growing forever inside the tree filebrowser
serves and Infuse indexes. Now `UN_LOG_FILE_MB: "10"` + `UN_LOG_FILES:
"3"`, the same 30 MB ceiling the Docker side already had; the container
reports `(3 @ 10Mb)`.

`UN_LOG_QUEUES: "30m"` for the heartbeat. Not `0` — measured, `0` does not
disable it but clamps it to a 15-second floor, four times noisier than the
default. Extraction events are unaffected, verified end to end:
`Tracking New Item` → `Queued` → `Extraction Started` → `Extraction
Finished` all still logged.

Stage 7's unpackerr environment assertion gains `UN_LOG_FILE_MB` only.
That list is for settings whose drift is silent, and this is the only one
of the three that qualifies — the other two degrade to "noisy" and "still
bounded". Checked against containers configured both ways, so it
discriminates.

### 2026-08-02 — `FILEBROWSER_DATABASE` pinned in `compose.yaml` (`Q1-12`)

The database path was inherited silently from the image's own `ENV`
(`/home/filebrowser/data/database.db`). It happened to be correct, but
`read_only: true` makes it a hard dependency on the `filebrowser_data`
volume mount: if upstream ever moves the default outside that directory,
Quantum tries to open its database on a read-only root and the container
dies at startup. The value is now written explicitly next to the volume
line it must agree with, so the two change together.

This does **not** silence the first-boot warning that prompted the
change. Measured on the live host on 2026-08-02: `[WARN] database file
could not be found. If this is unexpected, please set the
FILEBROWSER_DATABASE environment variable to the correct path` is emitted
*while the variable is already set to the correct path*, one second before
`Creating new database`. The warning distinguishes "file missing" from
"path wrong" not at all; on a first install the file is simply not there
yet. Restart and `--force-recreate` both log `Using existing database`
with no warning, and the operator's changed admin password survives both
(default `admin`/`admin` → `401`).

### 2026-08-02 — documentation resynced against the script

`docs/architecture.md`'s stage table still described `V1-20` at 5305
lines; `install.sh` is 5678. Stage 4 alone was understated by 348 lines
and every embedded-script line reference inside it was wrong, including
reconcile itself — listed as `2439-3905, 1466 lines` where it is
`2576-4236, 1659`. The whole table was regenerated the way the note under
it says to, rather than patching the rows that looked wrong; that habit is
what caused all three drifts now on record.

Also corrected: `README.md` claimed seven embedded scripts were six and
that Tier 2 had 57 tests across five files (it has 120 across eight), and
the canonical bundle was still described as state/dnsmasq/Caddy.

Two `quantum`-line reconcile behaviours were documented for the first
time — the Quantum policy file joining the bundle with a restart-backed
restore, and the once-per-cycle default-password probe with its `429`
branch. Both were only in the design decisions until now.

### 2026-08-02 — `scripts/check-all.sh`: the four checks in one command

`bash -n install.sh`, `shellcheck install.sh`,
`scripts/lint-embedded-scripts.sh` and `bats test/` in a single run — the
local substitute for the CI that will not exist while the repository has
no remote.

It does not stop at the first failure, because one command is only worth
having if it gives the complete picture. A check whose tool is missing is
reported as **doğrulanamadı** and exits non-zero rather than passing
silently — the same reasoning as the `429` branch in `Q1-10`. The first
run on the Debian target proved the point by finding `shellcheck` absent
and refusing to call the run clean. It also reports the bats skip count,
so a green run on the workstation does not read as full coverage.

All four failure paths were exercised. The most useful one: a syntax
error planted inside the reconcile heredoc is caught by check 3 alone —
`bash -n install.sh`, `shellcheck install.sh` and the whole bats suite
pass on it, which is exactly why the embedded lint exists.

### 2026-08-02 — unit tests for the last five uncovered reconcile helpers

`port_binding_exists`, `docker_network_tuple`, `record_container_restart`,
`forwarding_config_ok` and `gro_flags_ok` had no coverage at all. Four of
the five reach the outside world through a parsing step, and a parse that
is subtly wrong looks exactly like one that is right when the system is
healthy — `grep -Fx` versus `grep -F` decides whether a substring can
satisfy a port check, `head -n 1` decides which network a multi-homed
container reports, an awk program decides what counts as a configured
sysctl. None of that is visible to a live smoke test.

`record_container_restart` is tested against `restart_budget_available`
rather than alone, because nothing else pins that the writer and the
reader agree on the stamp's filename and format — and the restart
cooldown (DD-21) is the only thing between a repeatedly-failing repair and
a restart loop.

36 cases, mutation-verified. One mutation changed nothing and is recorded
in the test: the start-of-line anchor in the sysctl regex turns out to be
redundant with the string equality that follows it, not load-bearing as
its shape suggests. A stub-fidelity bug was also found and fixed — the
first stubs printed errors to stdout where the real `docker` and `ethtool`
use stderr, which every call site discards.

84 → 120 cases, no skips on the Debian target. No change to `install.sh`.

### 2026-08-02 — a test for the gap that hid the Quantum policy file

`Q1-9` fixed one file being outside the canonical bundle. It did not fix
the reason nothing noticed: **nothing anywhere compares the files
`install.sh` generates against the files the bundle covers.**
`test/canonical_bundle.bats` checks that Stage 6's manifest and
reconcile's expected list agree with each other, and two lists agreeing
says nothing about what is missing from both.

`test/generated_files_bundled.bats` supplies the third side. It derives
the generated set from install.sh's own write operations — with every
heredoc body stripped first, so the helper scripts' `install` calls don't
count as install.sh's — and requires every one of them to be either
published into the bundle or listed on an allowlist with a written reason.

Of the 32 generated files, 9 are bundled and 23 are excluded for four
stated reasons. Writing the allowlist surfaced what looked like an
inconsistency — two generated systemd drop-ins are neither bundled nor
named in reconcile, while three of the other five are bundled — and
measuring it closed it. Both were deleted on the test host, Docker was
restarted and the host rebooted with them absent: firewall policy still
applied, all containers up, reconcile clean, zero failed units. The units
they point at are enabled and carry their own ordering, so the drop-ins
are redundant except for a `RequiresMountsFor` that is inert unless the
download path is a separate mount.

Mutation-verified on scratch copies, all five assertions independently.
The load-bearing one reverts `Q1-9` itself — the suite fails on the real
historical defect. 79 → 84 cases, no skips on the Debian target. No
change to `install.sh`.

### 2026-08-02 — `Q1-11`: the Stage 4 progress note said six containers

There are five. The generated `compose.yaml` defines `portainer`,
`filebrowser`, `qbittorrent`, `unpackerr` and `wg-easy` — the sixth `wg:` in
that file is the network. The count was right before a service was dropped,
was corrected on `master`, and never made it across to `quantum`.
Reconcile's `expected_containers` list has said five all along.

### 2026-08-02 — `Q1-10`: the default-password probe stops fighting the rate limiter

Two defects in the DD-30 check, both found by re-reading `Q1-8` end to end
and then measuring the endpoint it talks to.

**It failed open on `429`.** Quantum's `POST /api/auth/login` is rate
limited, and the bucket is keyed on **source IP, not on the credential**:
measured on the target, 6 failures produce `429`, after which the *correct*
password also returns `429`. The check only warned on `200`, so a throttled
response fell through the same silent path as a plain `401` — the check
reported "nothing to see" at exactly the moment someone was hammering the
login screen. `429` now gets its own message that says the check could not
be performed and that this is not evidence the password was changed.

**It ran up to four times per cycle.** The probe lived inside
`check_compose_runtime`, which a single cycle calls up to four times
(detection, retry, post-repair, final postcondition). Against a 6-attempt
bucket that left the operator two tries before reconcile's own traffic
locked the login screen — and reconcile could trip the limit unaided. The
probe's source is `172.18.0.1`, the docker bridge gateway, which is also
where every Caddy-proxied browser login arrives from, so the bucket is
shared with the operator. It is now `report_default_filebrowser_password()`,
called once from the main flow. One attempt per 20-minute cycle cannot
accumulate: the timer interval is longer than the longest measured window
(3–8 minutes of silence).

Verified live on all four paths — clean, drifted, throttled, and the
regression case with the volume deleted — then end to end through systemd:
`Result=success`, the warning once in the journal, zero failed units. Full
reasoning in **DD-33**, which amends DD-30's cost claim.

### 2026-08-01 — `Q1-3`: the admin account goes back to the container

The installer no longer bootstraps FileBrowser Quantum's admin user. Reading
upstream's source settled it: `quickSetup()` runs only `if !exists` (no
database), creates `admin`/`admin` from a hardcoded fallback, never
re-asserts it on later starts, and sets `ShowFirstLogin` so the UI prompts
without forcing a change. That is a deliberate upstream design, not an
oversight, and overriding it bought less than it cost.

Removed: the Stage 5 `docker stop` + `docker run … set -u` block (~20 lines)
and the Stage 7 `admin/admin` assertion. `WEBDAV_PASSWORD` goes back to
being cleared in Stage 4.

**`minLength` had to drop from 8 to 5, and this is not optional.** `admin` is
exactly five characters, so 8 makes `quickSetup()` die with
`[FATAL] store.Users.Save: password must be at least 8 characters long` and
the container comes up with no user at all — healthy to Docker, 200 to the
reconcile probe, clean under `--check`, and impossible to log into. Upstream's
two numbers are tuned to each other.

**The change also fixed a latent behavioural bug.** The removed code ran
whenever Stage 0 re-collected credentials, so a re-run would have silently
reset a password the operator had already changed in the UI. Verified after
the change: password changed to something else, full installer re-run, and
the new password still works while `admin`/`admin` stays refused.

Also considered and rejected: `FILEBROWSER_ADMIN_PASSWORD`, which upstream
does support. It would have put a plaintext secret in `compose.yaml` —
`0600 root:root`, but still readable via `docker inspect` and the
container's `/proc/1/environ`.

Verified live on a reimaged volume: zero FATALs, zero restarts,
`admin`/`admin` 200 as intended, one user with `showFirstLogin: true`,
`--check` `rc 0`, zero failed units, and a re-run against the live stack
completing cleanly. Full reasoning in **DD-27**.


### 2026-08-01 — `Q1-2`: WebDAV directory cache lowered to one minute

`rclone serve webdav` was running on its 5-minute `--dir-cache-time`
default. That put five minutes between qBittorrent/unpackerr writing a file
and Infuse being able to see it — the exact producer/consumer path this
installer exists for.

Measured: a file created in the media tree was visible to FileBrowser
Quantum immediately (its SQLite index monitors in real time) and still
returned 404 over WebDAV at t+10s. After the change, with a properly warmed
cache, it appeared after 33 seconds.

`--poll-interval` was considered and deliberately not used: it applies
"only on supported remotes", and `rclone backend features` reports
`ChangeNotify: false` for a local directory. Directory cache lifetime is the
only effective lever on this backend. Full reasoning in **DD-28**.

The first verification of this change was invalid and is worth recording:
it appeared to show instant visibility, but the install had just restarted
`master-webdav`, so the cache was cold and the first request read from disk.
A cold cache proves nothing about cache expiry.


`MASTER_SETUP_VERSION` is `2026.07.31-V1-20`; `install.sh` is 5305 lines.

`V1-19` finishes what `V1-18` started. `V1-18` learned to *diagnose* a node
deleted from the Tailscale panel; it still told the operator to run
`tailscale logout && bash install.sh` by hand. But at that point the script
already knows everything it needs: the profile exists locally and has no
counterpart on the control plane, so it is worthless. It now clears the
profile itself and falls straight through to the interactive login.

Structurally this collapsed two paths into one. "No profile at all" and
"profile whose node was deleted" both set `TAILSCALE_NEEDS_LOGIN` and reach
the same single login block, instead of one exiting and the other logging
in.

If the automatic `tailscale logout` fails or takes longer than 60s, the
install stops and says so rather than continuing — `tailscale up` may not
open a fresh registration over a stale profile, and an operator dropped
into that state has no way to see why. The network/control-plane branch
still exits, because there the profile may be perfectly valid and deleting
it would be wrong.

**Live-verified** against a genuinely deleted node: the log shows the
diagnosis, `Yerel profil temizlenip yeni kayıt açılıyor...`, a fresh login
URL, and then a complete install — `STACK_SCHEMA=10`, five digests, nine
units, five containers, WebDAV 401/401/207 with the public IPv4 refusing,
`--check` rc 0.

**`V1-20` fresh-install verified (2026-07-31).** The host was reimaged and
`V1-20` installed from scratch: `STACK_VERSION=2026.07.31-V1-20`,
`STACK_SCHEMA=10`, five image digests recorded, nine units active, five
containers, **zero failed units**, `--check` every field 0 at `rc 0`.
WebDAV bound to the Tailscale IPv4 alone with the public IPv4 refusing,
five `.ayc` names resolving and answering through Caddy, firewall at
exactly two narrow public allows with a single `DOCKER-USER` jump and no
IPv6 allows, exit node advertised, GRO `off`/`on`.

Worth noting in that output: `--check` reported
`UYARI: wg-easy ilk kurulumu tamamlanmamış` and still returned `rc 0`.
That is `V1-11`'s fix working on a fresh install — the condition is
expected before the operator has opened `wg.ayc`, and it no longer
contaminates the exit code.

`V1-20` is a one-word consequence of reading that log: the first line still
said `HATA: Kayıtlı Tailscale profili 60 saniyede online olmadı`, so a
**successful** install left an error line behind it. The severity is now
decided per branch — `UYARI` when the script recovers, `HATA` only when it
exits. This is the same class as `V1-11`: a recoverable condition reported
as failure.

### Previously

`MASTER_SETUP_VERSION` was `2026.07.31-V1-18`; `install.sh` was 5275 lines.

**Deployment tooling (`versiyon/deploy.sh`, not part of `install.sh`).**
Copies the single export in `versiyon/` to a host, verifies the transfer by
SHA256 and optionally runs the installer. The expected hash is computed
from the local file at run time rather than stored — a stored constant
would be a second copy needing manual update on every export swap, and this
repository has been bitten by exactly that three times (the repair cooldown
across two heredocs, the architecture stage table twice, and the "sabit
image sürümleri" wording surviving four revisions past the change it
described). Both guards — exactly one export present, transferred hash
matching — were verified to fire rather than assumed.

`--run` executes the installer directly over SSH; the `tmux` wrapper was
dropped at the operator's request, since the install can equally be started
from the provider console. The cost is stated in the script and the README
rather than hidden: an SSH drop after Stage 1 leaves the install
incomplete, with re-running (25s, zero container restarts when nothing
moved) as the built-in remedy.

It also warns about the Tailscale login, which is what actually cost time:
restarting the installer generates a new nodekey and invalidates the
pending auth path, producing `410 auth path not found`. Three attempts went
to that before the cause was identified — and the cause was the restarts
themselves. The fix for a slow login is to wait, not retry.

`V1-18` makes Stage 2 say *why* a registered Tailscale profile failed to
come online. Three unrelated faults produced the same message and have
different fixes: the control plane is unreachable, the node key has
expired, or **the node has been deleted from the Tailscale admin panel**.

The third looks entirely healthy locally — profile registered, key valid
until 2027, `tailscaled` active, `tailscale ip -4` returning an address —
and is only distinguishable by `404: node not found` in journald. It
happened for real on 2026-07-31, most likely while clearing out the dead
tailnet entries this project accumulates on every reimage. The install
stopped correctly and left the host on its previous version, but the
message did not say that the only fix is `tailscale logout` followed by a
fresh browser login.

Stage 2 now greps journald for that signature and prints the specific
cause and the exact remedy. The window is scoped to
`MASTER_SETUP_STARTED_AT` rather than a fixed `-5min`, so a resolved
earlier fault cannot misdiagnose a different failure minutes later.

**Live-verified (2026-07-31).** The user deleted the node from the
Tailscale admin panel — an account-level action outside the standing
authorization, so it had to be theirs — and a re-run produced exactly the
intended output:

```
HATA: Kayıtlı Tailscale profili 60 saniyede online olmadı.
NEDEN: Kontrol düzlemi bu düğümü tanımıyor (404 node not found).
Düğüm Tailscale panelinden silinmiş; ...
  tailscale logout && bash /root/master.sh
```

The generic branch was correctly *not* taken, and the install stopped at
`rc=1, aşama=2` without leaving the host half-configured. The state it
diagnosed is worth recording, because it is why the message earns its
keep: `tailscale ip -4` returned an address, `tailscaled` was `active` and
`BackendState` read `Running` — three healthy indicators out of four, with
only `Online: false` and journald telling the truth.

### Previously

`MASTER_SETUP_VERSION` was `2026.07.31-V1-17`; `install.sh` was 5251 lines.

`V1-17` trims Stage 0's pre-confirmation summary to the four values the
operator actually chose: downloads path, timezone, WebDAV username and the
Tailnet DNS domain. Removed: operating system, Tailscale login behaviour,
public IPv4, the two fixed service ports, and the wg-easy admin reminder.

The block's job is "confirm your choices before anything is mutated", not
"inventory what will be installed", and it had drifted into the second.
Every removed line was verified to survive elsewhere before deleting it —
the public IPv4 and both ports appear in the final summary (which also
shows the resolved addresses rather than "will be auto-detected"), and the
wg-easy admin step appears there as a fuller warning covering Portainer
too. The OS line was pure redundancy: a host that is not Debian 13 exits at
the OS guard long before Stage 0 renders.

Both branches (new credential / existing `htpasswd` preserved) were
render-tested.

### Previously

`MASTER_SETUP_VERSION` was `2026.07.31-V1-16`; `install.sh` was 5250 lines.

`V1-16` is text only: three operator-facing strings still described the old
world. Stage 4 printed "Sabit image sürümleri" and Stage 5's progress note
said "Sabit container image sürümleri indiriliyor", both left over from
before `V1-12` moved the images to floating tags — the script was telling
the operator the opposite of what it does. The `--status` one-liner in the
final summary also predates `V1-12` and did not mention that the mode now
prints the running image digests.

Caught by the user reading the install output, not by any check. Worth
noting where the gap is: Stage 7 asserts behaviour thoroughly but asserts
nothing about the words the script uses to describe itself, and neither
does the bats suite. Every string of this kind found so far — three
documentation defects on 2026-07-31 plus these three — has been found by
reading, never by tooling.

Not live-verified: the test host was offline. The changed lines were
render-tested locally for alignment; no logic changed.

### Previously

`MASTER_SETUP_VERSION` was `2026.07.31-V1-15`; `install.sh` was 5249 lines.

`V1-15` closes the last structural item on the list: the repair cooldown
was written out independently in two embedded scripts, and the fact
"15 minutes" appeared in three more places as hardcoded prose in
operator-facing error messages.

The two code copies **stay**, and that is the decision rather than a
compromise. Every embedded script has to be self-contained because
`scripts/lint-embedded-scripts.sh` extracts each one and lints it as a
standalone program — the mechanism that answers **H4**. Binding them to a
shared variable, or splitting a heredoc so an unquoted prelude could
interpolate one, would leave the linted fragment referencing something it
never assigns: trading a real property (the linter checks exactly what
ships) for a cosmetic one.

What the duplication actually risked was *silent* divergence, and DD-21
makes that concrete — the reconcile timer moved to 20 minutes specifically
to stop fighting this cooldown, so the two numbers are coupled by a design
decision and one could have been changed with the other left behind.
`install.sh` now declares `MASTER_RESTART_COOLDOWN_SECONDS` as the single
source of truth and **Stage 7 asserts all three values agree**, naming
them all when they do not.

The three prose copies were removed outright — the messages derive the
figure (`$((RESTART_COOLDOWN_SECONDS / 60))`), so they cannot contradict
the behaviour. `StartLimitIntervalSec=900` in three systemd units is
deliberately untouched: same value, different mechanism.

**The assertion was verified to discriminate rather than assumed to.** A
copy of `install.sh` with the recovery constant set to `800` was installed
on the test host and failed at Stage 7 with `install.sh : 900 /
reconcile : 900 / recovery : 800`, then the real version was reinstalled
clean. Same discipline as the `all_critical_state_healthy` coverage guard
earlier the same day: a guard nobody has watched fail is not yet known to
work.

### Previously

`MASTER_SETUP_VERSION` was `2026.07.31-V1-14`; `install.sh` was 5198 lines.
**Live-verified:** 25s install, `STACK_SCHEMA=10`, five digests recorded,
`--check` rc 0, zero failed units, containers untouched.

**Test coverage corrected (2026-07-31):** `M7`'s inventory claimed the
only remaining scope was CI wiring. That was written on 2026-07-28 against
a ~4550-line script and had not been revisited as the file grew to 5198
lines. A re-survey found three genuinely unit-testable pure-logic functions
with no coverage at all — `restart_budget_available` (the 15-minute
cooldown gate whose mismatch with the old 5-minute timer motivated DD-21,
i.e. the constant that drove a design decision had no test behind it),
`disk_space_ok` (threshold parse, strict-`<` boundary, fail-closed on
unparseable output) and `all_critical_state_healthy` (pure, twenty flags,
no external calls). All three are now covered; the suite goes from 62 to
**74 cases, all passing with zero skips on the Debian target**.

The `all_critical_state_healthy` suite includes a guard case asserting the
fixture's flag list matches the flags the function actually reads, so a
flag added to the reconcile pass but forgotten in the gate becomes visible
rather than silently reducing what the loop covers. That guard was checked
against a deliberately shortened list and does fail — it is not vacuous.
Two smaller things surfaced while writing it: the `df` stub was built with
`printf` and the stubbed percentage's `%` was read as a format specifier,
so it emitted an error while still passing because `disk_space_ok`'s
`tr -dc '0-9'` cleaned up after it; and this is the third
documentation-accuracy defect of the day, after `docs/architecture.md`'s
18-line stage-table drift and its stale `OPTIONS` description of the WebDAV
probe.

**Reboot-verified (2026-07-31):** the host returned in 56 seconds with all
nine units active unaided, five containers up, `rclone` re-bound to the
Tailscale IPv4 by itself, the firewall rebuilt to exactly two narrow public
allows with a single `DOCKER-USER` jump, five `.ayc` names resolving and
answering, the exit node advertised and GRO flags correct, and `--check`
rc 0 with zero failed units. Also the **first reboot the `V1-12`/`V1-13`
digest record has been through**: `--status` showed all five short digests
with no divergence marker, so the `state.env` record still matches what is
actually running after a full restart — the mechanism had been introduced
and verified within a single uptime until now.

`V1-14` puts every network-dependent step behind `retry_network`: three
attempts, an explicit per-attempt `timeout`, 5s/15s backoff. Applied to
`apt-get update`, the Tailscale keyring and repo list, the Docker GPG key,
the Caddy GPG key and repo list, and `docker compose pull`.

**The timeout turned out to matter more than the retry**, which inverts
how the finding was originally written up. A Docker Hub 502 during
`docker compose pull` is what prompted it, and a retry does fix that — but
that failure was loud and safe: the install stopped and the immediate
re-run succeeded. Reading the surrounding code showed the worse case had
no bound at all. The script runs under `systemd-inhibit
--what=shutdown:sleep --mode=block` and holds the `flock` it shares with
`master-network-reconcile`, so a single hung download blocks shutdown
*and* leaves the 20-minute reconcile timer unable to run, indefinitely.

No error classification, deliberately. Permanent failures (`manifest
unknown`, `unauthorized`, a full disk) return within seconds, so three
blind attempts cost them about 20s of backoff and then the same clear
error; only transient faults and hangs consume real time, and those are
the target. Matching upstream stderr text would be locale- and
format-dependent for no gain.

Budgets came from measurement rather than guesswork: cold
`docker compose pull` 10.9s for 885 MB across three registries, warm pull
3.2s, `apt-get update` 0.9s, keyring fetches 36–127 ms. Bulk transfers get
300s then 180s (~27× the measured cold pull), small fetches 60s then 30s.
A hung pull is now bounded at about 11 minutes instead of forever.

Worth keeping in mind from those numbers: **the warm pull still costs
3.2s** because it re-checks manifests at all three registries. The pull is
a hard network dependency on every run, including runs where nothing has
changed — which is precisely how a transient registry fault reached an
otherwise no-op re-run.

`apt-get full-upgrade` and `apt-get install` are deliberately not wrapped:
they drive dpkg transactions, and reissuing an interrupted one is a
different problem class that interacts with the `--force-conf*` handling.
The Caddy GPG fetch was restructured rather than wrapped as-is — it was
`curl … | gpg --dearmor`, and retrying the pipeline would also retry a
local dearmor that retrying can never fix.

`test/retry_network.bats` covers all four control-flow paths plus argument
pass-through. The design note preceding this change claimed the recovery
path could not be tested deterministically without a real flaky network;
that was wrong, and a stub that fails once then succeeds reproduces it
exactly. The suite self-skips where GNU `timeout` is absent, so it skips
on the macOS workstation and runs for real on Debian — where the **full
62-case suite passes with zero skips** (74 after the `M7` coverage
correction later the same day).

### Previously

`MASTER_SETUP_VERSION` was `2026.07.31-V1-13`; `install.sh` was 5104 lines.
**Live-verified:** installed in 25s, `STACK_SCHEMA=10`, all five
`IMAGE_DIGEST_*` keys recorded and matching the running images, `--status`
printing the short digests, `--check` rc 0, zero failed units.

`V1-12` replaces the exact container image pins with floating tags and
records the digest each tag resolves to; `V1-13` fixes the digest lookup
that `V1-12` got wrong.

The change started as the opposite proposal. Re-running `install.sh` also
upgrades `docker-ce`, `tailscale` and `caddy`, because those three
third-party `sources.list` entries persist from the previous run and Stage
1's `full-upgrade` sees them — so pinning *those* was suggested. The user
rejected it: pinning trades away security updates. That reading is right,
and it also pointed at the real inconsistency — Debian-sourced packages
already behave as "patches arrive, majors do not" because trixie is
stable, while the container images were frozen at exact versions. The
stack was running two opposite policies at once.

Tags now (queried from the registries, because the upstreams' published
tags are uneven): wg-easy `15.3` and unpackerr `0.15` move at the patch
level; filebrowser `v2` moves within the major, since no `v2.63` tag is
published; portainer `lts` moves within the LTS line and will jump a major
when Portainer declares a new one; qbittorrent `latest`, because
linuxserver publishes no float tag at all. Both `lts` and `latest` were
verified to resolve to the same digests as the exact pins they replaced,
so adopting them changed nothing on the day.

A moving tag deletes the answer to "what is running" — `compose.yaml`
keeps its checksum while the image beneath it changes. So the five
resolved digests are appended to `state.env` after Stage 5, `--status`
prints them, and **Stage 7 asserts the recorded digest equals the running
one**. Floating tags without that record would be a straight loss of
auditability; the pair is the design.

Upgrading is safe — each container reads its existing data directory and
continues — but downgrading is not: Portainer migrates its database
forward with no reverse path, so re-pinning an old tag does not undo a bad
upgrade. Rollback is a provider-level (netcup) VPS snapshot, chosen over an
in-script snapshot because a whole-machine image also covers the migrated
databases and keeps rollback out of the installer's scope.

`V1-13` exists because `RepoDigests` is a field of the *image* object, not
the container: `docker inspect <container>` fails with `map has no entry
for key "RepoDigests"`, and `V1-12` wrote all five digests as `bilinmiyor`.
**Stage 7 caught it and failed the install with `rc=1, aşama=7`** — the
second time in three revisions that a Stage 7 literal assertion caught a
change that `bash -n`, `shellcheck` and the full bats suite had passed.
The same wrong lookup was present in `--status` and was fixed with it.

One incidental observation from the same session: a `V1-13` attempt died
at Stage 5 because Docker Hub's anonymous token endpoint returned **502
Bad Gateway** during `docker compose pull`. Nothing in the script is at
fault, but the pull has no retry, so a transient registry error fails the
whole install. Recorded in `TODO.md`.

### Previously

`MASTER_SETUP_VERSION` was `2026.07.31-V1-11`; `install.sh` was 4984 lines.
**Live-verified:** re-installed over `V1-10` on the same host via the
idempotent path, then both drift scenarios replayed against a wg-easy
still on `/setup/1` — healthy pass, WebDAV repair and Caddyfile repair all
exit 0, journal reading `UYARI`, zero failed units, `--check` rc 0,
`--status` reporting `V1-11` / `c33d84f7…`. Re-verified from scratch on a
second reimaged host, where the first attempt accidentally proved nothing:
wg-easy's web setup was completed three minutes after the install, so the
scenarios ran against a `/login` container, `WG_SETUP_PENDING` never fired,
and three `exit 0` results the old code would have produced identically
were briefly mistaken for evidence. After wiping wg-easy's config to
restore `/setup/1`, the replay gave five `UYARI` lines and **zero `HATA`**
across three runs, both repair runs printing the warning twice — the same
double-print that accompanied `exit 1` under `V1-10` — with all three
exiting 0. **The opposite branch is measured too**, once the user
completed wg-easy's web setup and made the failing `elif` reachable:
`wg set wg0 listen-port 51820` (runtime-only, reversible, `wg0.conf`
untouched) gave `HATA: wg-easy iç portu 51820; beklenen 65171.`,
`compose_runtime=1` and `exit 1`, with no automatic wg-easy restart;
restoring the port returned `exit 0`, `--check` all fields 0 and the peer
intact. Both branches of `V1-11` are therefore measured, not one measured
and one reasoned.

`V1-11` separates "wg-easy is waiting for its first web setup" from
"wg-easy is misconfigured". Both used to set `WG_CONFIGURATION_INVALID`,
and the consequence was a reconcile exit code that lied precisely when it
mattered. On a fresh install — before anyone has opened `wg.ayc` — a
healthy pass exited 0 via the `all_critical_state_healthy()` early return,
but any pass that actually *repaired* something fell past that gate into
the `RECOVERY_FAILED` check and exited 1, with every repair having
succeeded. Since `master-network-reconcile.service` is the `OnFailure=`
target of five other units, that turned the operator's red/green signal
red at the exact moment the system was doing its job.

The setup-pending case now has its own `WG_SETUP_PENDING` flag: reported
as `UYARI` rather than `HATA`, still suppressing wg-easy's automatic
restart (restarting a container that is waiting for its first web setup
fixes nothing), but no longer failing the run. A real internal-port
mismatch keeps `WG_CONFIGURATION_INVALID` and keeps failing.

**Found by live testing on a freshly reimaged host, not by review.** The
comment above the check already stated the intent — that a `/setup` screen
on a fresh install is expected and must not fail the run — and the code
delivered that intent only along the early-exit path. The two drift
scenarios (stopping `master-webdav`, appending a line to the Caddyfile)
were the first cases to exercise the other path.

Docs corrected in the same pass: `docs/architecture.md`'s stage table had
silently drifted 18 lines for stages 5–7, and its reconcile section still
described the WebDAV probe as `OPTIONS`, which `V1-6` had already changed
to `PROPFIND` after discovering rclone answers `OPTIONS` 200.

### Previously

`MASTER_SETUP_VERSION` was `2026.07.31-V1-10`; `install.sh` was 4975 lines.
**Live-verified:** timer reads `OnCalendar=*-*-* *:00/20:00` with the next
three firings at `23:40`, `00:00`, `00:20` — evenly spaced across the hour
boundary, which was the point of choosing 20. Install 7/7, `--check` rc 0,
WebDAV 401/207.

`V1-10` is `V1-9` plus one fix: Stage 7 asserts the timer's `OnCalendar`
line against a literal, and that literal still said `*:00/5:00`, so the
first `V1-9` install failed its own verification at Stage 7. Worth noting
as a small vindication of that assertion existing — the script caught an
incomplete change of mine that `bash -n`, `shellcheck` and the bats suite
all passed.

### Changed

- **The reconcile timer now runs every 20 minutes instead of every 5
  (`V1-9`, DD-21).** The user asked for a longer interval on the grounds
  that the system is stable; the measurement found a better reason. A
  healthy check costs about half a second, so cost was never the issue —
  but `RESTART_COOLDOWN_SECONDS` is 900, so on a persistent fault the
  5-minute timer gave one run that repaired and two that could only
  detect, each logging `cooldown içinde; tekrarlanmadı`, exiting
  non-zero and leaving a failed unit. Two thirds of the runs were noise
  that could not act. Above the cooldown, every scheduled run can repair.

  20 was chosen over the suggested 18–24 because it divides 60 evenly
  (`:00 :20 :40`). `*:00/18:00` would give `:00 :18 :36 :54` and then a
  6-minute gap at the hour boundary — a silently uneven interval.

  Cost, stated plainly: drift with no event trigger (address changes,
  manual config edits, GRO flag loss, disk filling) now takes up to 20
  minutes to correct rather than 5. Crash recovery is unaffected — the
  five `OnFailure=` hooks and the `PartOf`/`Wants` cascades still invoke
  reconcile immediately.

## [V1-8] - 2026-07-30

`MASTER_SETUP_VERSION` is `2026.07.30-V1-8`; `install.sh` is 4956 lines.
**Live-verified** by a full install on 2026-07-30 (23:01:37 → 23:01:58,
21 seconds): 7/7 stages, zero failed units, `--check` all-zero at exit 0.
The schema 8 → 9 migration was exercised in place — the host went in with
`STACK_SCHEMA=8` + `LOCAL_DNS_ENABLED=1` and came out with `9` and the key
gone, canonical manifest still eight entries. Two drift tests passed:
appending a line to `/etc/caddy/Caddyfile` was detected as
`config=1 caddy_config=1` and reverted, and the WebDAV checks stayed
green throughout.

### Changed

- **Tailnet DNS + Caddy are no longer optional (`V1-8`, `STACK_SCHEMA`
  8 → 9).** They were always installed in practice, so the "Kurulsun mu?"
  prompt was a branch that existed only to be answered the same way every
  time. Stage 0 now asks for the domain alone (default `ayc`, or the
  existing domain on a re-run; Enter still means "change nothing").

  The user asked whether it was enough to hardcode the flag to `1` and
  leave the plumbing, or better to remove it. Measured first: 36
  references and ~25 conditional branches, plus a two-shape canonical
  bundle and 6 of `canonical_bundle.bats`'s 8 tests devoted to the
  branching. Hardcoding would have kept all of that alive and
  permanently unreachable — still linted, still tested, still needing to
  stay consistent through every future refactor, while `state.env`
  advertised an option that no longer existed. Removed instead:
  - `SETUP_LOCAL_DNS` and `LOCAL_DNS_ENABLED` are gone entirely (0
    references remain).
  - `canonical_bundle_ok()` has **one** manifest shape instead of two,
    which is the part that matters for the planned modularization: the
    bundle contract is now a single fixed eight-entry list.
  - `LOCAL_DNS_ENABLED` dropped from `state.env`, hence the schema bump.
    A host built by an older revision will fail reconcile's state
    validation until it is re-installed — acceptable here because the
    deployment is reimaged routinely, but it *is* a breaking change.
  - `canonical_bundle.bats` rewritten: the DNS-disabled cases are gone,
    replaced by a guard that the old two-entry bundle is now **rejected**
    (a host still carrying one must be caught, not tolerated), plus new
    cases for an extra appended entry and for the manifest being exactly
    eight entries. 7 cases, no skips. Suite total 57 → 56.

  Net effect: `install.sh` 5046 → 4956 lines.

## [V1-7] - 2026-07-30

`MASTER_SETUP_VERSION` is `2026.07.30-V1-7`; `install.sh` is 5046 lines.
**Live-verified** by a full install on 2026-07-30 (22:35:51 → 22:36:13,
22 seconds): 7/7 stages, one expected warning (wg-easy's admin is a manual
step), zero failed units, `--check` all-zero at exit 0.

### Fixed

- **Stage 5 could not restart a rate-limited `master-webdav.service`
  (`V1-7`).** After a failed install the unit can be sitting in
  `failed` with its `StartLimitBurst` exhausted; `systemctl restart` then
  returns non-zero with `Start request repeated too quickly` and the
  install dies at Stage 5. Found on the very next re-run after `V1-6`.
  Stage 5 now issues `systemctl reset-failed` first — idempotent, a no-op
  on a healthy unit, and the same order reconcile's repair path already
  used. The inconsistency between the two paths was the actual defect.


- **Three bugs in the `V1-3` WebDAV service, all found by the first live
  install (`V1-6`, 2026-07-30).** The install failed at Stage 7; static
  analysis had passed cleanly on every one of them. See DD-20 for the
  measurements.
  - **`RestrictAddressFamilies` was missing `AF_NETLINK`.** `ExecStart`
    resolves the Tailscale address with `ip addr show`, and iproute2 uses
    a netlink socket. With only `AF_INET AF_INET6` the call failed with
    `Cannot open netlink socket`, so the service never bound. rclone
    itself needs only the two inet families.
  - **That failure was silent.** The wait loop discarded `ip`'s stderr,
    making a hard configuration error look identical to "the address
    hasn't appeared yet" — the unit read `active (running)` for the full
    300-second window. The loop now distinguishes the two and reports the
    first `ip` error immediately. stderr is captured into a variable
    rather than a temp file, since `mktemp` fails under
    `ProtectSystem=strict`.
  - **All three 401 probes used `OPTIONS`, which rclone does not
    authenticate.** rclone exempts the WebDAV discovery preflight and
    answers `200`; sftpgo had answered `401`, and the probes were written
    against that. Uncorrected, Stage 7 would fail every install and
    reconcile would mark WebDAV drifted every cycle. `webdav_direct_ok()`,
    Stage 7's direct check and `caddy_runtime_ok()`'s vhost check now use
    `PROPFIND` with `Depth: 0` — a protected method, so a 401 also proves
    the htpasswd is enforced. **Authentication itself was never broken:**
    unauthenticated `GET`/`PROPFIND` and wrong passwords all return 401,
    correct credentials return 207.

  Verified on the live host after the fixes: listener on
  `<tailscale-ip>:65113` only (refused on the public IPv4),
  unauthenticated `PROPFIND` 401, authenticated 207, and the
  `master-webdav` user reading the 0750 media tree via gid 1000.

## [V1-5] - 2026-07-30

`MASTER_SETUP_VERSION` is `2026.07.30-V1-5`; `install.sh` is 4996 lines.
Static analysis only.

### Changed

- **The final install summary's WebDAV block was reworked (`V1-4`, then
  trimmed in `V1-5`).** The `V1-3` version left it ambiguous which
  address to type into Infuse: it printed the Tailscale IP and port in
  one block and the served directory in another, with no full URL.
  `V1-4` added the username, the full URL, both access paths and their
  trade-offs; the user judged that over-long, so `V1-5` cut it back to
  the fields actually needed at the end of an install:

  ```
  WebDAV (host rclone servisi, salt okunur):
    Sunulan dizin : /downloads/media
    Kullanıcı adı : infuse
    Parola        : Aşama 0'da belirlediğiniz parola
    Adres         : 100.x.y.z veya webdav.<domain>
    Port          : 65113
    Protokol      : WebDAV (HTTP, HTTPS değil)
    Tam URL       : http://100.x.y.z:65113
    Kimlik dosyası: /etc/master-stack/webdav.htpasswd (bcrypt)
    Sıfırlama     : dosyayı silip install.sh'i yeniden çalıştırın
  ```

  The address line appends `veya webdav.<domain>` only when local DNS is
  enabled, using whichever domain the operator chose. The username is
  read back from the `htpasswd` file rather than from `$WEBDAV_USER`,
  which is empty on a re-run that preserved an existing credential. The
  printed IP has always been the live one — Stage 7 re-derives `TS_IP`
  from `tailscale0` before the summary — and the explanatory material
  (Caddy path trade-off, the removed `127.0.0.1:65113` binding,
  reconcile's re-bind on address change) now lives in DD-20 and
  `docs/architecture.md` rather than the console output.

- **WebDAV is now a host service, not a container (`V1-3`, DD-20).** The
  `sftpgo` container was removed and replaced by `master-webdav.service`,
  running `rclone serve webdav $DOWNLOADS_PATH/media --read-only` bound to
  the Tailscale IPv4 only. Consequences:
  - **The last Tailnet → Docker firewall exception is gone.** The narrow
    `--ctorigdst $TAILSCALE_IPV4 --ctorigdstport 65113` ACCEPT in the
    mangle guard chain existed solely for the sftpgo container; a host
    service receives traffic on the INPUT path the guard chain never
    inspects. That direction now has zero exceptions.
  - Stage 0 prompts for a WebDAV username and password (skipped when
    `/etc/master-stack/webdav.htpasswd` already exists, so re-runs keep
    the existing credential). Only the bcrypt hash is written; the
    plaintext never touches disk. The service reads it via systemd
    `LoadCredential=`, so the file stays `root:root 0600`.
  - The unit runs as a dedicated `master-webdav` system user holding gid
    1000 to read the 0750 media tree, under `ProtectSystem=strict`,
    `ProtectHome`, `PrivateTmp`, `PrivateDevices`, `NoNewPrivileges` and
    `RestrictAddressFamilies` — a tighter sandbox than the `:ro` bind
    mount it replaces.
  - `rclone` and `apache2-utils` (for `htpasswd` only) join the Stage 1
    base packages. The `sftpgo.<domain>` DNS name and Caddy vhost are
    gone; `webdav.<domain>` now proxies to `{$TS_IPV4}:65113` instead of
    loopback, because Debian's rclone (1.60.1) accepts a single `--addr`.
  - Reconcile monitors it on two independent signals — unit active, and a
    real `OPTIONS` 401 against the current Tailscale IPv4 — with restart
    repair, unconditionally (not gated on the local-DNS option).
  - **The user's motivating symptom is not addressed by this.** The
    change was requested to fix intermittent Infuse playback stalls
    attributed to the container layer; the more likely causes are DERP
    relay fallback or `wireguard-go` throughput, and DD-20 records that
    plainly so the question stays open.

  Two implementation notes worth carrying forward. Copying Caddy's
  `ExecStartPre` + `EnvironmentFile` pattern would have been **wrong
  here**: systemd reads environment files before any `Exec*` runs, so on
  first start `${TS_IPV4}` would expand to empty and `--addr :65113`
  would become a wildcard bind on the public IPv4. Caddy escapes this
  only because its binary re-reads the file via `--envfile`. The address
  is therefore resolved inside `ExecStart` by `master-webdav-serve`.
  Separately, `--config /dev/null` is passed explicitly so rclone does
  not search `$HOME/.config`, which does not exist under `ProtectHome`.

- **Test fixtures updated for the removed firewall rule.** The healthy
  IPv4 policy fixture no longer contains the WebDAV allow. Two tests
  changed meaning rather than being deleted: the stale-address test
  became "rejects a resurrected narrow WebDAV allow" (drift detection for
  a rule that should no longer exist anywhere), and the v4/v6 conflation
  test now swaps the *policy* chain instead of the guard chain, because
  with the WebDAV rule gone both families' guard chains are legitimately
  identical and the remaining real difference is the public-port RETURNs.

## [V1-2] - 2026-07-30

`MASTER_SETUP_VERSION` is `2026.07.29-V1-2`; `install.sh` is 4792 lines.

### Added

- **The host now self-reports which installer revision built it.**
  `install.sh` computes its own SHA256 at startup and writes
  `STACK_VERSION` + `STACK_SHA256` into `/etc/master-stack/state.env`
  (falling back to `bilinmiyor` if the script has no readable path, e.g.
  piped stdin). Both keys are informational — no consumer requires them —
  so `STACK_SCHEMA` stays `8`. This closes the server-side half of the
  gap that let the host run several fixes behind the repository on
  2026-07-28 without anything noticing (`MASTER_SETUP_VERSION` itself was
  the script-side half).
- **`master-network-reconcile --status`** — a lock-free, read-only
  one-screen summary: installed version + script hash from `state.env`,
  per-container state/health for all six services, failed systemd units,
  downloads-disk usage, the `/run`-based repair stamps, and a full
  `--check` run (executed as a child process, which takes the lock) whose
  exit code the mode passes through (0 = clean, 75 = another stack
  transaction holds the lock). Deliberately enforces no preconditions —
  not even the canonical-bundle validation — because a status command
  must work exactly when the system is broken; a broken bundle shows up
  in the embedded `--check` output instead. The final install summary
  now points at the command.

## [V1-1] - 2026-07-29

`MASTER_SETUP_VERSION` is `2026.07.29-V1-1`; `install.sh` is 4701 lines.
Exported as `versiyon/install-V1-1.sh`. **Live-verified** by a full
install on 2026-07-29 (19:52:55 → 19:54:45, 1m50s): 7/7 stages, zero
warnings, zero failed units, six containers up, `--check` all-zero exit 0,
7/7 DNS names, Caddy 200/200/200/302/302/401/200, WebDAV reachable on the
Tailscale IPv4 and refused on the public IPv4.

### Fixed

- **M11 — the UDP socket-buffer floor now takes effect before
  `tailscaled` opens its socket.** The netbuf `sysctl.d` write and its
  `sysctl -p` moved from after the Tailscale package install to
  immediately before it. Debian's `tailscale.postinst` runs
  `deb-systemd-invoke restart tailscaled.service`, so the daemon comes up
  *inside* `apt-get install -y tailscale` — the script's own `systemctl
  enable --now tailscaled` only guarantees the enable, it never performs
  the start. Verified from the 2026-07-29 install: `dpkg configure
  tailscale` 19:17:24, `systemd: Starting tailscaled.service` 19:17:24,
  `status installed` 19:17:25. Since `wireguard-go` requests its large UDP
  receive buffer once at socket-open time and is clamped against the
  ceiling then in effect, DD-18's 16 MiB floor was reaching the running
  daemon only after the first restart on any host whose provider image
  does not pre-set `net.core.rmem_max` — a ~70× shortfall against
  Debian's 208 KB default, silently costing exit-node throughput. The
  forwarding sysctl deliberately did **not** move: `ip_forward` is read
  dynamically and is only needed before `tailscale set
  --advertise-exit-node`, and hoisting IPv6 forwarding ahead of the
  package download would change routing state earlier than necessary.
  Invisible on the project's test host, whose VPS image sets 64 MiB at
  boot, which is why DD-18's original verification missed it.

  The install confirmed the **ordering** from the log —
  `Aşama 2: 22% - UDP soket buffer tabanı ayarlanıyor` and
  `net.core.rmem_max = 67108864` both precede
  `Aşama 2: 25% - Tailscale paketi kuruluyor` — but not the **effect**,
  for two independent reasons: the package was already at its newest
  version so the postinst never ran and `tailscaled` was never restarted,
  and the host's ceiling was already 64 MiB before either ordering could
  matter. What was fixed is correct; how much it was worth is still
  unquantified.

### Changed

- **Reverted the `v1.1-1` Stage 1/2 reordering.** It moved the Tailscale
  browser login ahead of `apt-get full-upgrade`, was installed and
  measured on a clean host, and was reverted the same day at the user's
  direction. The reorder did what it was designed to do — the login
  banner reached the screen 10 seconds after confirmation instead of
  4-6 minutes — but it did not fix the reported problem, because
  **4m41s of the wait is Tailscale's control plane answering the first
  `RegisterReq`** (`19:17:25` sent → `19:22:06` `AuthURL` received) and
  nothing in `install.sh` influences that. Reverting also restores the
  3-6 second settling window between `systemctl enable --now tailscaled`
  and `tailscale up` that the GRO block provides, which the reorder had
  cut to zero. See DD-19 for the full measurement and for what a future
  attempt would need to establish first.

### Added

- **DD-19** records the reordering experiment, its measurements, and why
  it was reverted, so it is not proposed a second time on the same
  reasoning. It also notes what was *not* the cause: the display path is
  immediate (`tee`'s stdout is a TTY and line-buffered), and the network
  was eliminated — IPv4/IPv6 both reached the control plane in ~25 ms
  with clean 1500-byte PMTU on both stacks.
- **M11** (Medium, open) — the UDP socket-buffer sysctl from DD-18 is
  applied *after* `tailscaled` is already running, but `wireguard-go`
  requests its large receive buffer once at socket-open time and is
  clamped against the ceiling then in effect. The daemon is started by
  Debian's `tailscale.postinst` (`deb-systemd-invoke restart`) inside
  `apt-get install -y tailscale`, not by the script's own `systemctl
  enable --now tailscaled`, which is a no-op — so a fix has to precede
  the package install. On a host whose provider
  image does not pre-set `net.core.rmem_max`, `tailscaled` runs at
  Debian's 208 KB ceiling — ~70× below its request — until the first
  restart. Invisible on the project's test host, whose VPS image sets
  64 MiB at boot, which is why DD-18's original verification missed it.
  Found while reordering, fixed incidentally by `v1.1-1`, reintroduced by
  the revert, and fixed on its own in `V1-1` (see **Fixed** above). One
  question remains unanswered but is no longer blocking: whether
  `tailscale up`/`set` rebinds magicsock's UDP socket later in the stage,
  which would mean the defect was narrower than described. Raising a
  permitting ceiling earlier cannot hurt either way (DD-18), so the fix
  is safe regardless — but the size of what was fixed is not quantified.

## [V1] - 2026-07-29

Final release. `MASTER_SETUP_VERSION` is `2026.07.29-V1`; `install.sh` is
4683 lines. Exported as `versiyon/install-V1F.sh`.

Everything below this heading shipped in V1. The functional content is
identical to the live-verified `v1rc-4` tag — the only `install.sh`
changes since it are the version string and the qBittorrent socket-buffer
reminder in the final summary, neither of which touches an executable
path.

## [Unreleased]

### Added

- Stage 2 now writes `/etc/sysctl.d/99-master-stack-netbuf.conf`, flooring
  `net.core.rmem_max` / `wmem_max` at `max(current, 16 MiB)`. These were
  previously only correct by accident on the live host — the 64 MiB
  values came from the VPS provider's own image, not from this installer,
  and would have fallen back to Debian's 208 KB anywhere else. The
  beneficiary is Tailscale (userspace WireGuard), whose `tailscaled` was
  measured holding a 14 MiB socket buffer; kernel WireGuard is unaffected.
  Raise-only, so a provider that already sets more keeps it. See DD-18.
- `master-network-reconcile` now checks `tailscale-udp-gro.service`'s
  `ActiveState` and restarts it, with the existing 15-minute cooldown,
  when it is not active. The unit is `Restart=no`, so a boot-time failure
  previously persisted until the next reboot. Reported as `gro_unit=` in
  `--check`; deliberately excluded from `all_critical_state_healthy()` and
  from the exit code, since GRO is throughput-only. Amends DD-11, which
  had removed continuous ethtool-flag polling — that part stays removed.

- `MASTER_SETUP_VERSION` now carries a revision suffix
  (`2026.07.29-v1rc-1`), incremented on every `install.sh` change. A
  deployed host previously could not report which revision it was built
  from, which is how the server ran several fixes behind the repository
  on 2026-07-28 with nothing noticing. Git tags stay separate and are
  created only after live verification. Convention recorded in
  `CLAUDE.md`.

- Reconcile now also verifies the UDP GRO **ethtool flags**, not just the
  unit's `ActiveState`, and repairs on either signal. Live fault injection
  showed the unit check alone proves nothing: after
  `systemctl stop tailscale-udp-gro`, `rx-udp-gro-forwarding` was still
  `on`, so the optimization had never actually degraded. Reported as
  `gro_flags=` in `--check`. Anything the check cannot evaluate (no
  `ethtool`, no WAN interface, feature unreported or `[fixed]`) counts as
  healthy, matching the helper's own success cases. Amends DD-11 a second
  time. (`v1rc-2`)

### Fixed

- The final install summary now names qBittorrent's socket receive buffer
  as a required manual step, with the measured reason and a suggested
  value. This script does not manage qBittorrent's configuration, so the
  setting reverts to the system default on any fresh install — measured
  on 2026-07-29 during a ~278 MB/s download: at the 208 KB default the
  uTP/DHT socket saturates and drops packets; once raised, the same load
  ran 288,201 packets in 30s with zero drops. The `rmem_max` floor from
  DD-18 is what permits the raise (the kernel clamps the request to it),
  so the two are complementary rather than alternatives. (`v1rc-5`)
- Stage 0 now asks a different question on a re-run. When a managed
  DNS/Caddy install is detected the prompt is no longer "should DNS be
  installed?" — DNS is already installed, so the only meaningful question
  is whether the domain changes. It reads
  "Alan adı değiştirilsin mi? [e/H]": `e` asks for the new domain, and
  Enter (or `H`) keeps the existing domain and structure untouched while
  the install continues. This removes the abort path entirely rather than
  just defaulting away from it — declining to change is now a normal
  outcome instead of a fatal one, and the protection against silently
  tearing down DNS becomes structural (the option is never offered)
  instead of a `exit 1`. Enter now means "change nothing" in both
  branches, fresh and re-run. Domain validation moved to a single block
  that every branch flows through, including the value read from
  `state.env`. (`v1rc-4`)
- Stage 0's domain prompt defaulted to a hardcoded `ayc` regardless of the
  domain the existing install actually uses, so on a host configured with
  any other domain, pressing Enter silently switched it — Stage 6 writes
  both `local-services.conf` and the `Caddyfile` with `>`, so the old
  names are replaced rather than duplicated, and the change would have
  been invisible until DNS stopped resolving. The default now comes from
  `LOCAL_DOMAIN` in `/etc/master-stack/state.env` and falls back to `ayc`
  only when there is nothing to read. The prompt also now names the
  detected domain and spells out what each answer does: `E` regenerates
  from the same domain, `h` stops the installer rather than skipping. The
  previous wording ("varsayılan: korunur") overstated the `E` branch,
  which regenerates rather than preserves, and said nothing about `h`
  aborting. (`v1rc-3`)
- Stage 0's Tailnet-DNS prompt defaulted to `H` even when a managed
  DNS/Caddy install was already present — and that answer makes the same
  Stage 0 abort with "Önceki yönetilen DNS/Caddy kurulumu bulundu".
  Pressing Enter on a re-run therefore killed the installer, which is
  exactly what happened during the 2026-07-29 verification run. The
  prompt now detects the existing install once, defaults to `E`, and
  shows `[E/h]`; the abort check reuses that same detection instead of
  re-testing the three files, so the two cannot drift apart. Fresh
  installs are unaffected and still default to `H`. (`v1rc-2`)
- `tailscale-udp-gro.service`'s unit comment claimed reconcile retried it
  every five minutes. That had been untrue since DD-11 removed the code
  in question on 2026-07-28. The change above makes the claim true again;
  the comment is rewritten to state what actually happens.

## [v1rc] - 2026-07-29

Tagged `v1rc` and exported to `~/Desktop/install-v1rc.sh`, hash-verified
identical to `install.sh` at the tag. `install.sh` is 4502 lines.

Consistency and coverage release. No new functionality: everything here
either removes an internal inconsistency, adds test coverage, or closes a
tracked finding by decision. Validated by a clean install on a reimaged
host, a re-run against that install, and two reboots.

### Validated

- **Clean install on a freshly reimaged host** (2026-07-28/29): all 7
  stages, `master-network-reconcile --check` reporting every field `0`
  and exiting `0`. Followed by a re-run to deploy the unit-permission fix
  — also clean, and a second exercise of the idempotent re-run path.
- **Two reboots.** Recovery is ~35s to SSH and ~13s from boot to all six
  containers healthy. `--check` clean afterwards both times, zero failed
  units, H1's kernel modules auto-loaded, wg-easy's two peers and its
  port intact.
- **Netfilter reconstruction analysed across a reboot.** Nothing persists
  rules to disk (`iptables-persistent` absent, `nftables.service`
  disabled), so the whole set is rebuilt every boot — confirmed by packet
  counters resetting. The rebuilt IPv6 set is byte-identical; the IPv4
  set differs only inside Docker's own chains, because containers get
  different bridge IPs depending on start order and Docker rewrites its
  DNAT/ACCEPT rules accordingly. `MASTER-DOCKER`, `MASTER-TS-FORWARD` and
  the `FORWARD` prefix come back byte-identical. See
  `docs/design-decisions.md` DD-16 for why that separation holds and why
  it matters for how reconcile checks Docker's rules.
- **Boot ordering measured:** `docker-tailscale-fw` starts at the exact
  moment `docker.service` becomes active, and Docker is only active once
  it has created its chains — so the `After=` ordering is a structural
  guarantee, not a race that happens to be won.

### Changed

- **`WEBDAV_PORT` is now a top-level variable** alongside
  `WG_PUBLIC_PORT` and `QBIT_PUBLIC_PORT`, which already existed. `65113`
  had been hand-written in **17 places**; the 13 in variable-expanding
  contexts now use it. This also shrinks **L7** from a 17-site problem to
  a 3-site one (the remainder is inside the single-quoted firewall
  heredoc, which cannot expand outer variables).
- **Named constants for two duplicated policy values** in
  `master-network-reconcile`: `DISK_USAGE_THRESHOLD_PCT` and
  `RESTART_COOLDOWN_SECONDS`. `master-docker-netfilter-recovery` is a
  separate script and cannot share them, so both sides now carry a
  comment saying they must change together.
- **`ensure_forward_prefix()` waits for Docker's chains** instead of
  testing once, via a new `wait_for_chain()` that `wait_for_docker_user`
  now wraps. It ran *before* the functions that already waited, and being
  fatal under `set -e` it could in principle have killed the helper at
  boot. Measured across two reboots: it never actually waits, because of
  the ordering guarantee above — so this is defensive consistency, not a
  demonstrated bug fix, and is recorded as such.
- **Comment language rule reversed to match reality** (`CLAUDE.md`).
  `install.sh` had always been ~73% Turkish-commented while the rule said
  English, so following the rule was producing English blocks inside
  Turkish ones — 45 such lines were translated back. The rule now records
  the actual convention, with the principle that each artifact is
  internally consistent: `install.sh` Turkish throughout, Markdown docs
  and commit messages English, `test/*.bats` and `scripts/*.sh` English
  (bats specifically because Turkish `@test` names break under a
  `tr_TR.UTF-8` locale).

### Fixed

- **systemd unit files were written mode `0600`**, so systemd logged
  `marked world-inaccessible ... has no effect` 12 times per boot. Cause:
  the script's top-level `umask 077`. Stage 6's three drop-ins were
  already chmod'ed to `0644` by hand, which is what made this an
  inconsistency rather than a uniform choice. Replaced with one
  `set_unit_file_mode()` helper used at all **eleven** write sites.
  Verified after the fix: **12 warnings → 0**, no `0600` unit files left.
  File contents are unchanged, so canonical checksums are unaffected.

### Added

- **`test/canonical_bundle.bats`** (8 cases) — `canonical_bundle_ok()`,
  reconcile's first gate, where a non-zero return silences the entire
  self-healing loop. Its correctness depends on Stage 6's manifest file
  list agreeing with a hardcoded expected list ~2000 lines away, which
  nothing enforced and no static check could see. The tests derive both
  lists from `install.sh`'s own source rather than restating them, and
  were mutation-verified on a scratch copy.
- **`test/policy_functions.bats`** (17 cases) —
  `check_ipv4_policy()`/`check_ipv6_policy()`, which hold the entire
  expected firewall rule set and produce the verdict
  `docker-tailscale-fw --check` returns. Covers the healthy policy plus
  eleven distinct failure shapes, and the IPv6 variants including **M5**'s
  missing-`ip6tables` diagnostic and the reduced no-IPv6-WAN set.
  `docs/testing.md` had assumed these were too integration-shaped to unit
  test; that judgement is now corrected in place.
- Test suite: **32 → 57 cases**, and the 25 new ones run with no skips on
  any POSIX host.

### Removed

- **M3 (installation profiles) and L7 (ports hardcoded in the firewall
  heredoc) closed as won't-do**, no code change. Same ground for both:
  this installer targets a single-purpose, single-operator host, always
  built from scratch, with all six services in active use and local DNS
  enabled every time. **M3**'s premise does not hold and its security
  motivation is already covered by **C1**'s accepted risk; **L7** has no
  scenario that can trigger it. `docs/profiles.md` is kept as a design
  note, marked closed. Either reopens if the installer is reused across
  hosts or by another author.
- **M7's remaining scope (CI) parked**, not closed: the repository stays
  local with no git remote by decision, so a runner has nowhere to build
  from. Tier 1 is complete and Tier 2 now has no identified gaps, so **M7
  is the only open finding and nothing about it is actionable today.**

## [v1b] - 2026-07-28

Post-R1.0 hardening and review pass. Exported as
`~/Desktop/install-v1b.sh` (hash-verified identical to `install.sh` at
tag `v1b`).

### Verified

- **First live re-run against an already-provisioned host (2026-07-28),**
  validating this whole batch (**M8**, **M9**, **L6**, **M10** and the
  version-string correction) on the production server. All 7 stages
  completed; `master-network-reconcile --check` reports every field `0`,
  including the new `compose_file=0`, and exits `0`.
  - This also closed the last un-exercised idempotency scenario in
    `docs/testing.md` — every prior live run had been against a freshly
    reimaged host.
  - **It immediately found something.** The deployed `compose.yaml`
    predated both **H7** and **M1**, so `TRUSTED_ORIGINS=portainer.ayc`
    and the `cap_drop`/`read_only` hardening only reached the server in
    this run. Portainer had therefore still been rejecting writes via
    `portainer.ayc` in real use, days after **H7** was "fixed" in the
    repository. A repository fix is not a deployed fix — which is
    exactly the gap **M10** was added to report, found by the very run
    that installed it.
  - Cost: all six containers were recreated rather than just
    `qbittorrent` (the compose diff alone had suggested otherwise);
    Docker was already at the candidate version so no daemon restart
    occurred; admin accounts, wg-easy peer configuration and qBittorrent
    state all survived on their volumes.

### Added

- **Reconcile now detects and reports drift in `/root/docker/compose.yaml`**
  (**M10**). The canonical bundle previously covered `state.env` and the
  six dnsmasq/Caddy files, but not the file that defines all six
  services, their capabilities, `security_opt`, port publications and
  mounts — so a change made directly to the deployed `compose.yaml` was
  never noticed, and `master-compose.service` applied it on every start.
  `compose.yaml` now has a canonical copy, a manifest entry and a
  `compose_file_ok()` comparison.
  - **Reported only, never restored**, and deliberately outside both
    `CONFIG_DRIFTED` and `all_critical_state_healthy()`: restoring the
    file has no effect until a `docker compose up -d`, which would risk a
    5-minute recreate loop if the drift recurs and would silently undo a
    deliberate operator change mid-experiment. It therefore produces no
    failed unit and does not block Stage 7. Same "surface it, don't act
    on it" precedent as the disk-space check (DD-13).
  - The originally proposed scope also covered
    `/usr/local/sbin/docker-tailscale-fw`; that was dropped on
    reflection. On a single-operator host that is always installed fresh
    the firewall helper is never hand-edited, and checking it is close to
    theater given reconcile validates the firewall by invoking that same
    helper. `compose.yaml` earns the check because it genuinely is edited
    live on this stack — the `mem_limit` A/B/C test is a worked example —
    so the real value is catching a live change not yet folded back into
    `install.sh`.
  - Note this changes the manifest's entry list, which
    `canonical_bundle_ok()` compares exactly, so a reconcile script from
    this version cannot validate a bundle published by an earlier one.
    Harmless under this project's deployment model (helper and bundle
    always come from the same run), but it does mean DD-14's
    "an interrupted re-run keeps enforcing the last known-good bundle"
    does not hold across a run that changes the manifest schema.

### Fixed

- **Reconcile could be left permanently unable to validate the canonical
  bundle after an interrupted re-run** (**M8**). Stage 4 unconditionally
  truncated the canonical `SHA256SUMS` to a single `state.env` entry
  while publishing a `state.env` that could say `LOCAL_DNS_ENABLED=1`;
  `canonical_bundle_ok()` cross-checks exactly those two against each
  other, so the bundle was self-inconsistent by construction for all of
  Stages 4-6. While `install.sh` is running this is harmless (reconcile
  defers on the shared lock), but a re-run that *failed* in that window
  left the `EXIT` trap restoring the previously-active timer, after
  which every 5-minute cycle hard-exited before reaching any repair
  logic — no self-healing at all on a half-configured host, reported
  with a message that reads like corruption rather than "interrupted
  install". The 2026-07-28 change moved publication to the end of Stage 6
  and described it as one atomic set. **H8 later corrected that claim:**
  only its manifest rename was atomic. Q1-16's verified generation pointer
  is the implementation that actually makes a failed re-run leave the
  previous complete bundle in place.
- **The stack-level repair path had no restart cooldown** (**L6**).
  Per-container restarts were budget-gated to once per 15 minutes, but
  `systemctl stop master-compose` + `systemctl restart
  docker-tailscale-fw` + `docker compose up --wait` was not, so any
  drift the pass could not actually repair re-ran that sequence every 5
  minutes indefinitely. Bounded in practice — `master-compose.service`
  has no `ExecStop`, so containers were never stopped — but a permanent
  failing unit plus a pointless firewall reapply every five minutes. It
  now reuses the existing `restart_budget_available`/
  `record_container_restart` helpers under a `master-compose`
  pseudo-target. `ADDRESS_CHANGED` is exempt: it self-clears after one
  successful pass, and deferring it would leave the published bindings
  on a stale IP.

### Changed

- `MASTER_SETUP_VERSION` corrected from the stale `2026.07.26-r8` to
  `2026.07.28-v1b`, and reconcile's two summary lines no longer print an
  "R8" prefix — logs, the install banner and the success summary now
  identify which release actually ran. `STACK_SCHEMA=8` is deliberately
  unchanged: it versions `state.env`'s on-disk format, which did not
  change. A comment at the definition site now states that distinction,
  since the two were easy to conflate.
- `ensure_forward_prefix()` (`docker-tailscale-fw`) now names the missing
  chain, the binary and the likely cause instead of returning a bare
  non-zero that `set -e` turns into a silent abort (**M9**). Behavior is
  unchanged; this turns a multi-minute diagnosis into one log line. The
  underlying coupling — the firewall assumes Docker's internal
  `DOCKER-USER`/`DOCKER-FORWARD`/`ts-forward` layout, and every re-run
  upgrades Docker via Stage 1's `full-upgrade` because Stage 3 leaves the
  Docker apt repository configured — was accepted rather than fixed;
  pinning `docker-ce` would freeze CVE fixes on a host that publishes
  ports to the public IPv4. See `docs/design-decisions.md` DD-15.
- `install.sh` 4376 → 4418 lines. Verified with `bash -n`, `shellcheck`,
  `scripts/lint-embedded-scripts.sh` and `bats test/` (all clean).

### Fixed

- Portainer rejected every write request (stop a container, remove an
  image, etc.) made through `portainer.$LOCAL_DOMAIN` — the Tailnet DNS
  name proxied through Caddy — with a CSRF "origin invalid" error.
  Found via real usage after R1.0. Root cause: Caddy always presents
  `Host: 127.0.0.1:9443` to Portainer (its own dial address), while the
  browser's `Origin`/`Referer` is `http://portainer.$LOCAL_DOMAIN` — a
  mismatch Portainer's CSRF protection treats as cross-origin. Fixed by
  setting Portainer's `TRUSTED_ORIGINS` environment variable, only when
  local DNS is enabled (**H7** in `SECURITY_REVIEW.md`).
  - **A wrong fix was caught before reaching `install.sh`.** The first
    attempt set `TRUSTED_ORIGINS=http://portainer.$LOCAL_DOMAIN`
    (`scheme://host`), matching how Portainer's current `develop` branch
    validates this value (it recently migrated to Go's native
    `http.CrossOriginProtection`). Tested directly against the live
    deployed `compose.yaml` first, specifically to verify before
    committing to `install.sh` — Portainer **crashed on startup**
    (fatal: "invalid url for trusted origin"). The pinned `2.39.5`
    release still uses the older `gorilla/csrf` library, whose validator
    does the *opposite*: it rejects any value containing `"://"` and
    expects a bare hostname. Caught by reading `2.39.5`'s actual tagged
    source on GitHub rather than trusting `develop`'s (newer, different)
    behavior. Reverted the live container immediately, corrected the
    value to `portainer.$LOCAL_DOMAIN` (no scheme), and confirmed live:
    container starts and stays up, and a simulated write request with
    the original failing `Origin`/`Referer` headers now returns `401`
    (reaches the authentication layer) instead of `403`
    ("origin invalid"). Applied to `install.sh` only after this live
    confirmation.
  - `install.sh` 4343 → 4365 lines. Verified with `bash -n`, `shellcheck`,
    `scripts/lint-embedded-scripts.sh`, and `bats test/` (all clean).

### Changed

- `qbittorrent`'s `mem_limit` raised from `2g` to `4g` after the user
  reported a real download-speed regression (~200MB/s → ~70-80MB/s)
  following **M1**'s container hardening. A live A/B/C comparison during
  an actual high-seed-count torrent download (recreating the container
  between each measurement window, same active transfer throughout)
  isolated the cause:
  - Original `cpus=2.0`/`mem=2g`: throughput capped ~170MB/s, CPU usage
    saturating near the 2-core limit (~197%) at peak.
  - All limits removed: 218-278MB/s, CPU using up to ~245% (more than 2
    cores) — confirming a real ceiling existed, not just swarm variance.
  - `cpus` held at `2.0`, only `mem_limit` raised to `4g`: also reached
    up to 275MB/s, with CPU comfortably under the 2-core cap throughout.
    This isolates the actual cause: the `2g` memory ceiling was
    constraining qBittorrent's disk cache/buffering, which was *also*
    driving up CPU usage indirectly (more frequent, smaller I/O) — the
    CPU saturation seen in the first test was a symptom of the memory
    limit, not an independent bottleneck. `cpus: 2.0` is unchanged,
    confirmed not to be the binding constraint.
  - Applied to the live deployed `compose.yaml` first (for the test
    itself), then to `install.sh` once confirmed. `install.sh` 4365 →
    4370 lines. Verified with `bash -n`, `shellcheck`,
    `scripts/lint-embedded-scripts.sh`, and `bats test/` (all clean).

### Removed

- `qbittorrent`'s `mem_limit` and `cpus` ceilings removed entirely
  (`compose.yaml` → `services.qbittorrent`). Even at `4g`, sustained
  high-throughput download load showed throughput fluctuating again; a
  further raise to `6g`/`3.0` was tried locally (never committed) before
  the user decided the ceiling itself was the problem, not its value. On
  a 4 CPU / ~8GB host, a limit that has to be raised each time real usage
  grows past it stops being containment and only remains a throughput
  risk — the last value tried (`6g`) already sat above the highest
  observed unlimited usage (~4.7GB), so it constrained nothing while
  still being able to throttle a future workload.
  - **What this does not change:** the hardening that actually contains
    this container is untouched — `security_opt: no-new-privileges`,
    `cap_drop: [ALL]`, and the minimal `cap_add` set (**M1**).
    `unpackerr` keeps its own `mem_limit: 512m` / `cpus: 1.0`, which
    never constrained it under a real extraction workload.
  - **Trade-off, accepted by the user:** a runaway `qbittorrent` is now
    bounded by the host's global OOM killer rather than its own cgroup,
    so the blast radius of that (unobserved so far) failure mode widens
    from one container to the host. Recorded under **M1** in
    `SECURITY_REVIEW.md` as an accepted deviation, not a regression to
    re-fix.
  - `install.sh` 4370 → 4376 lines. Verified with `bash -n`,
    `shellcheck`, `scripts/lint-embedded-scripts.sh`, and `bats test/`
    (all clean).

## [1.0.0] - 2026-07-28

### Added

- `master-network-reconcile`: a new `disk_space_ok()` check monitors the
  filesystem backing `$DOWNLOADS_PATH` (persisted to `state.env` as of
  this change) and reports (but cannot auto-repair — deleting user data
  isn't a safe automated action) once usage crosses 90%. Motivated by
  this server's actual workload (continuous downloading/extraction),
  which was previously the one realistic failure mode reconcile had zero
  visibility into. Tested against both a real disk and an artificially
  filled tmpfs on the live server.
- Project documentation scaffolding: `README.md`, `CLAUDE.md`,
  `SECURITY_REVIEW.md`, `TODO.md`, `CHANGELOG.md`, `SESSION.md`, and
  `docs/{architecture,design-decisions,profiles,testing}.md`.
- Full `README.md` description of `install.sh`'s current architecture,
  installation flow, Docker services, networking, and known limitations.
- `CLAUDE.md` working guide for future Claude Code sessions (language
  rules, execution restrictions, review-before-edit workflow, security and
  modularity conventions).
- `SECURITY_REVIEW.md` populated with 18 findings (2 Critical, 4 High, 7
  Medium, 5 Low; corrected from an initial miscount of 19) from a full
  static audit of `install.sh`.
- `TODO.md` populated with prioritized remediation tasks derived from the
  security review.
- `scripts/lint-embedded-scripts.sh`: extracts `install.sh`'s six embedded
  heredoc scripts and lints each independently with `bash -n` +
  `shellcheck` (with `SC2016` excluded as a documented false-positive
  class for intentional single-quoted `awk` programs). Resolves **H4**.
- `test/reconcile_functions.bats`: `bats-core` unit tests for
  `state_value` and `owned_file_ok` (`master-network-reconcile` heredoc),
  extracting only these two function bodies rather than sourcing the
  whole reconcile script. Part of **M7**.
- `test/firewall_functions.bats`: `bats-core` unit tests for six
  pure-logic functions from `docker-tailscale-fw` (`route_value`,
  `chain_rules_exact`, `jump_is_first_and_single`,
  `forward_prefix_is_exact`, `docker_forward_has_no_terminal_drop`,
  `no_stale_staging_chains`), using fake `ip`/iptables/ip6tables
  stand-ins instead of the real binaries. Part of **M7**.
- `test/gro_functions.bats`: `bats-core` unit tests for
  `add_default_netdev`, the only standalone function in
  `tailscale-udp-gro`, using a fake `ip` stand-in. All 5 cases self-skip
  on this macOS dev workstation's bash 3.2, which lacks associative
  arrays (the function's dedup guard needs `SEEN` declared as one); they
  run for real on the Debian target's bash 5.x. Part of **M7**.

### Changed

- Stage 2 (`install.sh`): the "already connected to a tailnet" path no
  longer contains an auth-key-conflict warning, since auth-key input no
  longer exists.
- Stage 4 (`install.sh`): the media tree `chown` no longer unconditionally
  rewrites ownership on every run — it now only touches entries whose
  ownership doesn't already match `1000:1000`, via a scoped `find -exec`
  instead of a blanket `chown -R`.
- `master-network-reconcile` (`install.sh`): `tailscale-udp-gro.service`
  is no longer part of the continuous 5-minute reconciliation pass — its
  one-time Stage 2 setup (which still re-applies at every boot) is
  unchanged, but reconcile no longer detects or repairs GRO drift that
  happens outside of a reboot.
- `compose.yaml` → `services.qbittorrent`, `services.unpackerr`: both now
  set `security_opt: ["no-new-privileges:true"]` and hardware-sized
  resource ceilings (`qbittorrent`: `mem_limit: 2g`, `cpus: 2.0`;
  `unpackerr`: `mem_limit: 512m`, `cpus: 1.0`), tuned against the target
  server's actual 4 CPU / 8 GB RAM and typical 1-2 concurrent torrents.
- `compose.yaml` → `services.unpackerr`: now `cap_drop: [ALL]` and
  `read_only: true` — confirmed empirically to run cleanly with neither
  (**M1**).
- `compose.yaml` → `services.qbittorrent`: now `cap_drop: [ALL]` with
  `cap_add: [CHOWN, SETUID, SETGID, DAC_OVERRIDE, FOWNER]` — the minimal
  set its linuxserver.io entrypoint needs, confirmed empirically
  (**M1**). `read_only: true` was tested and deliberately **not**
  applied — it breaks the entrypoint's `PUID`/`PGID` handling.

### Removed

- **`TS_AUTHKEY` input removed entirely** (`install.sh`, Stage 0 + Stage
  2): the installer no longer prompts for or accepts a Tailscale auth
  key. It now always uses Tailscale's interactive browser login when the
  host isn't already part of a tailnet.
- **wg-easy unattended-bootstrap subsystem removed entirely**
  (`install.sh`, Stages 0/4/5/7 + EXIT trap): the installer no longer
  prompts for or provisions a wg-easy admin account. The DB/marker
  detection state machine, `WG_INIT_ENV_FILE`/`WG_INIT_OVERRIDE_FILE`
  generation, the bootstrap-apply-verify-scrub-marker sequence, the
  `scrub_wg_bootstrap_container` cleanup, and the Stage 7 hard
  postcondition are all gone (248 lines net). wg-easy's admin account is
  now created manually via its web UI on first access, matching
  Portainer/SFTPGo — the script only provisions the container and
  infrastructure.
- **Legacy reboot-timer cleanup removed entirely** (`install.sh`, Stage 1
  + Stage 7): deleted `remove_managed_scheduled_reboot()` and its Stage 7
  re-verification block (61 lines). This existed only to clean up a daily
  04:15 automatic-reboot mechanism installed by versions of this script
  from the r3 era or earlier — dead weight for a deployment target that
  is always a fresh Debian 13 install with no such history.
- **UDP GRO continuous reconciliation removed** (`install.sh`,
  `master-network-reconcile`): deleted the `GRO_INACTIVE`/`GRO_DRIFTED`
  detection block, the `all_managed_state_healthy()` wrapper function
  (now redundant — its sole caller uses `all_critical_state_healthy`
  directly), the `--check` mode's `gro_unit`/`gro_runtime` output fields,
  the drift warning, and the repair (start/restart) action — roughly 54
  lines. Also removed two now-dead variables inside the same heredoc
  (`ETHTOOL_BIN`, `CURRENT_WAN6_IF`). Stage 2's one-time setup (helper
  script + oneshot systemd unit, re-applied at every boot) is unchanged.

### Fixed

- `check_ipv6_policy()` (`docker-tailscale-fw`) now reports a specific
  "ip6tables bulunamadı" diagnostic instead of a generic policy-drift
  failure when the `ip6tables` binary is missing.
- Stage 1 `apt-get full-upgrade` now passes explicit dpkg conffile-policy
  flags (`--force-confdef`/`--force-confold`) so a theoretical
  unattended conffile prompt can never stall the noninteractive install.
- Stage 4 now also `modprobe`s `ip6_tables` and `ip6table_nat` on the host
  (added to the existing `wireguard` modprobe/`modules-load.d` step) — a
  regression in **H1**'s fix that broke `wg-quick up wg0`'s legacy-mode
  ip6tables PostUp/PostDown rules, found via the first live Tier 3 install
  test (2026-07-28).
- wg-easy's `healthcheck` (`compose.yaml`) no longer asserts a fixed
  WireGuard listen port — only that `wg0` exists and is up. The port
  assertion could never pass on a fresh install now that **M6** made the
  port a manual, web-UI-only setting, deadlocking Stage 5 on every fresh
  install (**H5**, found via the same live test).
- `check_compose_runtime()` (`master-network-reconcile`) no longer counts
  wg-easy's still-pending first-run setup (`/setup` redirect) as
  `compose_runtime` drift — only the diagnostic message and
  `WG_CONFIGURATION_INVALID` are still set. Previously this made Stage
  7's own `master-network-reconcile --check` postcondition gate fail on
  every fresh install, even after **H1**/**H5** were fixed (**H6**, found
  via a second live Tier 3 test, 2026-07-28).

### Documentation

- Final install summary now explicitly warns about two previously-silent,
  confirmed-intentional behaviors: (1) reconcile reverts
  `state.env`/dnsmasq/Caddy config drift (including manual edits) every 5
  minutes; (2) `docker`/`tailscaled` restarts cascade into the firewall,
  Compose stack, and Caddy via `PartOf`. No functional change — both
  behaviors were already in place and are staying as-is by explicit user
  decision.
- Final install summary now also warns that Portainer, wg-easy, and
  SFTPGo all need a manually-created admin account on first access, and
  lists each service's URL (including its Tailnet hostname if local DNS
  is enabled).
- Added an inline comment above `INSECURE: "true"` (`compose.yaml` →
  `services.wg-easy`) explaining its Tailnet-only + Caddy-loopback
  dependency.
- Expanded the Docker daemon DNS override comment (Stage 3) to explicitly
  state the intentional host-vs-container DNS resolution split.
- Documented in `README.md` (Security Notes) that Tailscale device
  registration isn't ephemeral, so rebuilding this server leaves an
  orphaned device entry in the tailnet admin console.
- Rewrote the `README.md` "Docker socket exposure" note to record the
  final accepted-risk decision on Portainer's `docker.sock` mount: a
  socket-proxy was reconsidered and rejected as a weak fit for Portainer
  specifically, and a read-only socket mount was noted as an ineffective
  mitigation (Unix domain sockets aren't gated by the mount's `ro` flag).

### Security

- **Resolved C2** (`SECURITY_REVIEW.md`): the Tailscale auth key was
  previously echoed to the terminal (`read -rp` instead of `read -rsp`).
  Rather than just silencing the prompt, the auth-key input was removed
  entirely, closing the exposure at its source. See `SECURITY_REVIEW.md`
  for details.
- **Resolved M6** (`SECURITY_REVIEW.md`): removing the wg-easy
  unattended-bootstrap subsystem eliminates the dead-end failure state it
  previously documented, along with an entire secret-handling subsystem
  (bootstrap env files, container secret scrubbing). Trade-off: the
  installer can no longer distinguish "public IP changed since wg-easy
  was last configured" across separate `install.sh` reruns — see
  `docs/design-decisions.md`.
- **Resolved H1** (`SECURITY_REVIEW.md`): removed `SYS_MODULE` and the
  `/lib/modules` bind mount from wg-easy's `cap_add`/`volumes`. The
  WireGuard kernel module is now loaded independently on the host (Stage
  4, best-effort `modprobe wireguard`), so wg-easy runs with only
  `NET_ADMIN`. Hardened further: the module load is made persistent across
  reboots via `/etc/modules-load.d/wg-easy.conf`
  (`systemd-modules-load.service`), and a functional probe (`ip link add
  ... type wireguard` + delete) replaces reliance on `modprobe`'s exit
  code, correctly handling a built-in (non-module) WireGuard kernel too.
  See `docs/design-decisions.md` (DD-10) for the tun-vs-wireguard
  clarification and the open userspace-WireGuard alternative this
  surfaced. **Needs real-server functional verification** (wg-easy
  bringing up `wg0` successfully) — not something this assistant can check
  directly.
- **Resolved H4** (`SECURITY_REVIEW.md`): added
  `scripts/lint-embedded-scripts.sh` so `install.sh`'s six embedded
  heredoc scripts (previously invisible to `bash -n install.sh` /
  `shellcheck install.sh`) get independently linted. First real run
  surfaced no actual bugs — only the expected, excluded `SC2016`
  awk-quoting notices — but the ~1900 lines this covers are now checked
  going forward instead of trusted blindly.
- **Resolved C1** (`SECURITY_REVIEW.md`, accepted risk): Portainer's
  `docker.sock` mount stays as-is. A socket-proxy was reconsidered and
  found to be a weak mitigation specifically for Portainer (its
  management features need close to the same broad API access that makes
  the direct mount risky). User confirmed active use and accepted the
  risk, scoped by network exposure rather than API restriction.

## Today's Work — 2026-07-27

- Performed a full static audit of `install.sh` (4552 lines) covering
  security, secrets handling, destructive operations, firewall/network
  safety, Tailscale exit-node configuration, Docker Compose design,
  systemd services/timers, reconcile/self-healing behavior, idempotency,
  rollback/cleanup traps, error handling, service coupling, unnecessary
  services, installation profiles, modularization opportunities, and
  testing strategy. No changes were made to `install.sh` — it was read
  only.
- Created the target project structure (top-level docs + `docs/`
  subdirectory) without touching or deleting any existing file.
- Filled in `README.md` end-to-end based on the audit findings.
- Filled in `CLAUDE.md` as the working guide for future sessions, encoding
  the language, execution, and review-workflow rules the user specified.
- Filled in `SECURITY_REVIEW.md`, `TODO.md`, `CHANGELOG.md`, `SESSION.md`,
  and all four `docs/*.md` files based on the audit results.
- `install.sh` remained unmodified through all of the above documentation
  work. Later in the same session, the user walked through the intended
  target architecture verbally; it was cross-checked against `install.sh`
  and found to match, aside from one planned future change (moving
  wg-easy's admin account setup from automatic to manual).
- Made the first actual `install.sh` change: removed the `TS_AUTHKEY`
  prompt entirely (Stage 0 input/summary + Stage 2 connection logic),
  resolving **C2**. Verified with `bash -n` and `shellcheck` (both
  clean); diff shown to the user before any commit.
- Established a standing workflow rule (added to `CLAUDE.md`): update
  `TODO.md`, `SECURITY_REVIEW.md`, and `CHANGELOG.md` after every
  `install.sh` change.
- Agreed a stage-by-stage remediation order with the user (Stage 0 →
  Stage 4/5 wg-easy → Stage 3 firewall → reconcile scope → legacy
  reboot-timer cleanup → Stage 7), and worked through it together: the
  user explains intended architecture piece by piece, this assistant
  analyzes the matching code and flags risk before any edit, and applies
  only what's explicitly approved.
- Removed the entire wg-easy unattended-bootstrap subsystem from
  `install.sh` at the user's request (**M6**): admin/peer setup is now
  fully manual via wg-easy's web UI; the script only builds the container
  and infrastructure. 248 lines removed across Stages 0/4/5/7 and the
  EXIT trap; verified with `bash -n` and `shellcheck` (also cleaned up two
  helpers ShellCheck flagged as newly-dead: `wg_ui_configured()` and
  `WG_UI_CONFIGURED`).
- End-of-session documentation pass: reviewed every Markdown file in the
  repository against the current `install.sh` and fixed drift left over
  from the two remediations above — `README.md` (feature list, stage
  table, installation flow, security notes, limitations, roadmap all
  referenced the now-removed `TS_AUTHKEY` prompt and wg-easy bootstrap),
  `docs/testing.md` (manual test checklist had two scenarios for
  behavior that no longer exists), and `docs/profiles.md` (stale
  `install.sh` line numbers in the implementation sketch). `SECURITY_REVIEW.md`
  and `TODO.md` line numbers were already refreshed earlier in the
  session. `install.sh` itself was not touched during this pass.
- Reviewed Stage 3 (`install.sh:993-1682`, Docker install + firewall
  helper) fresh at the user's request: no new issues found beyond what was
  already tracked (**M5**, still open at that point).
- **Remediation 3 (M5, Medium — resolved):** added an explicit "ip6tables
  bulunamadı" diagnostic to `check_ipv6_policy()` instead of a generic
  policy-drift failure. Diagnostics-only; fail-closed behavior unchanged.
- Discussed **H1** (`wg-easy`'s `SYS_MODULE` capability) in depth with the
  user, including correcting an earlier overreach on this assistant's
  part: the assumption that Tailscale's own operation would already have
  loaded the kernel `wireguard` module turned out to be unsubstantiated —
  the script's own `modprobe tun` in Stage 2 points to Tailscale using a
  TUN device + userspace WireGuard, not the kernel module. Clarified for
  the user that `tun` and `wireguard` are two fully independent kernel
  modules, and that a kernel module is a host-kernel-wide change shared by
  every container on the host, unlike most other container-scoped
  operations — directly explaining why `SYS_MODULE` was the container's
  biggest remaining host-touching surface.
- **Remediation 4 (H1, High — resolved):** removed `SYS_MODULE` and the
  `/lib/modules` mount from wg-easy; added an independent, best-effort
  `modprobe wireguard` on the host in Stage 4. Also discussed and recorded
  (as an open trade-off in `docs/design-decisions.md`, not implemented) a
  cleaner long-term alternative: running WireGuard fully in userspace
  (`boringtun`/`wireguard-go`) to remove the kernel-module dependency
  entirely.
- Both remediations verified with `bash -n` and `shellcheck` (clean);
  refreshed every affected `install.sh:NNNN` reference across
  `SECURITY_REVIEW.md` and `TODO.md` again after these two changes shifted
  line numbers throughout the file (4304 → 4317 lines). **H1** still needs
  a real functional test on the target server, which this assistant
  cannot perform.
- User asked whether the `modprobe wireguard` assumption could be made
  more of a guarantee, whether it should persist across reboots, and
  whether it risks breaking Tailscale or any other WireGuard consumer.
  Answered: added `/etc/modules-load.d/wg-easy.conf` for boot persistence,
  and replaced the modprobe-exit-code check with a functional
  `ip link add/del` probe (correctly handles a built-in, non-module
  WireGuard kernel); confirmed no risk to Tailscale (unrelated TUN +
  userspace code path) or to any other service (wg-easy is the only
  kernel-WireGuard consumer on this host). Refreshed line references
  again across `SECURITY_REVIEW.md` and `TODO.md` (4317 → 4334 lines);
  verified with `bash -n` and `shellcheck`.
- User asked for a deeper look at the remaining H1 risk, pointing out that
  wg-easy's own entrypoint is what actually brings up `wg0` (not
  `compose.yaml` directly) and that our new host-level probe already
  exercises the same kernel operation. Narrowed the real residual risk
  down to two specific, well-defined questions (container-namespace
  interface creation behavior, and wg-easy's own image-internal handling
  of a missing `SYS_MODULE`) instead of a vague "might not work." Offered
  to research wg-easy's actual entrypoint source to resolve this without
  waiting for server access; user chose to defer that to a live SSH test
  at the end of the engagement instead.
- **Remediation 5 (H2) and 6 (H3), both resolved by confirming intent, not
  by changing behavior:** user confirmed reconcile's config-revert
  behavior and the `PartOf` cascading-restart coupling are both desired,
  not bugs. Added two explicit warning blocks to the final install
  summary (`install.sh:4253-4278`) naming the affected files/units, and
  added confirming notes to `docs/architecture.md`. Verified with
  `bash -n` and `shellcheck` (clean; also test-rendered the
  conditional-text logic standalone to confirm correct output in both the
  local-DNS-enabled and local-DNS-disabled cases before trusting it).
  `install.sh` now 4356 lines.
- Agreed a logical order for the remaining `SECURITY_REVIEW.md`/`TODO.md`
  items with the user (quick low-risk group first, then M2, legacy
  reboot-timer cleanup, L3, M1, C1, M3, H4, M7, then a final Stage 7
  review, with the live SSH test still deferred to the end).
- **Remediations 7–11 (M4, L1, L2, L4, L5), the agreed "quick low-risk
  group":** all documentation/comment-only, no functional changes to
  `install.sh`. Added an inline comment for `INSECURE: "true"`; added
  dpkg conffile-policy flags to `apt-get full-upgrade`; expanded the
  Docker DNS comment to state the host-vs-container split explicitly;
  documented non-ephemeral Tailscale device registration in `README.md`;
  and added a first-run-admin-setup warning (Portainer/wg-easy/SFTPGo,
  with URLs) to the final install summary. Verified with `bash -n` and
  `shellcheck` (clean); render-tested the new conditional summary text
  standalone before trusting it. `install.sh` now 4378 lines. While
  updating `SECURITY_REVIEW.md`/`TODO.md` afterward, caught and corrected
  a long-standing arithmetic error: both files had said "19 findings"
  since the original audit, but only 18 are actually named (2 Critical +
  4 High + 7 Medium + 5 Low = 18).

## Today's Work — 2026-07-28

- **Remediation 12 (M2, Medium — resolved):** replaced the unconditional
  `chown -R 1000:1000 "$DOWNLOADS_PATH/media"` in Stage 4 with `find
  "$DOWNLOADS_PATH/media" \( ! -uid 1000 -o ! -gid 1000 \) -exec chown
  1000:1000 {} +`, so a re-run against an already-correctly-owned tree no
  longer pays the I/O cost of rewriting every file's ownership — only
  genuinely mismatched entries (including newly added files, or the root
  directory itself if needed) get touched. Verified the `find` predicate
  standalone in an isolated scratch directory before trusting it in
  `install.sh`: matching the current user's own UID/GID selected nothing;
  a nonexistent UID selected every entry, root directory included.
  Verified with `bash -n` and `shellcheck` (clean). `install.sh` now 4385
  lines. Refreshed every downstream `install.sh:NNNN` reference in
  `SECURITY_REVIEW.md` and `TODO.md` that shifted as a result.
- Presented analysis of the next agreed topic (legacy reboot-timer
  cleanup): `remove_managed_scheduled_reboot()` (Stage 1) plus its Stage 7
  re-verification is the only "old script version" migration shim left
  anywhere in `install.sh` (confirmed via `grep` for `r3` — one match).
  It's already idempotent/safe (a no-op when the legacy units don't
  exist), but on this deployment target — always a fresh Debian 13 install
  — it's guaranteed to always be a no-op, since those units never existed
  there. Asked the user whether this script would ever run against a
  genuinely old (pre-r8) host; they confirmed it would not.
- **Unnumbered remediation (legacy reboot-timer cleanup, resolved):**
  deleted `remove_managed_scheduled_reboot()` and its Stage 7
  re-verification block entirely — 61 lines removed, `install.sh` now
  4324 lines. Updated the Stage 1/2/3/4/5/6/7 line-range tables in
  `README.md` and `docs/architecture.md` to match (Stage 1's description
  no longer mentions "legacy reboot-timer removal"). Verified with
  `bash -n` and `shellcheck` (clean); refreshed every downstream
  `install.sh:NNNN` reference across `SECURITY_REVIEW.md` and `TODO.md`
  that shifted as a result (a larger sweep this time, since the removal
  sits early in Stage 1 and shifts nearly the entire rest of the file).
- Presented analysis of the next agreed topic (**L3**,
  `tailscale-udp-gro.service` complexity): mapped its full ~160-line
  footprint across Stage 2 setup, reconcile detection, reconcile
  health-rollup/repair, and Stage 5/7 sanity checks; noted GRO was
  already excluded from `all_critical_state_healthy()`, so its drift
  never affected pass/fail postconditions — only the "do nothing, early
  exit" shortcut in reconcile. Proposed removing the continuous
  reconcile-side monitoring while keeping the one-time Stage 2 setup
  (needed for per-boot persistence, since ethtool flags reset on reboot).
- **Remediation 13 (L3, Low — resolved):** removed
  `tailscale-udp-gro.service`'s reconcile-side continuous monitoring
  entirely (~54 lines: detection, `all_managed_state_healthy()`,
  `--check` fields, warning, repair action), redirecting its sole caller
  to `all_critical_state_healthy` directly. While removing this, manually
  caught two variables that became dead as a side effect —
  `ETHTOOL_BIN` and `CURRENT_WAN6_IF` inside the same
  `master-network-reconcile` heredoc — since `shellcheck` cannot see
  inside heredoc content and didn't flag them (a live demonstration of
  **H4**'s blind spot). Removed those too. Net 57 lines off `install.sh`
  (4324 → 4267). Verified with `bash -n` and `shellcheck` (clean);
  refreshed every downstream `install.sh:NNNN` reference across
  `SECURITY_REVIEW.md` and `TODO.md`.
- Presented analysis of **M1** (container hardening for `qbittorrent`/
  `unpackerr`), tiered by risk: Tier 1 (`no-new-privileges`, zero risk),
  Tier 2 (`cap_drop: [ALL]`, moderate risk — flagged that qbittorrent's
  linuxserver.io entrypoint runs a root-level init for `PUID`/`PGID`
  volume-ownership fixing and likely needs some capabilities back, unlike
  `unpackerr` which already runs as non-root), Tier 3 (`mem_limit`/`cpus`,
  needs the user's actual hardware specs to size safely — asked for them).
  Also discussed, at the user's prompt, whether qBittorrent's peer port
  could avoid public-IP exposure entirely: laid out the three real
  options (keep the current narrowly-scoped public port; fully un-forward
  it and accept degraded connectivity/seed-ability; or route qBittorrent
  through a third-party commercial VPN sidecar à la `gluetun`, which is
  the self-hosting community's standard answer to this exact question).
  Recommended scoping the VPN-sidecar option as its own future decision
  rather than folding it into this hardening pass.
- User approved Tier 1 immediately, deferred Tier 2 to the live SSH test,
  provided hardware specs (4 CPU / 8 GB RAM, 1-2 concurrent torrents) for
  Tier 3, and chose to keep the public IP port open (accepted as a
  narrow, reasonable risk) rather than pursue the VPN-sidecar option.
- **Remediation 14 (M1, Medium — partially resolved):** applied Tier 1
  (`security_opt: ["no-new-privileges:true"]`) and Tier 3 (`mem_limit`/
  `cpus`: `2g`/`2.0` for `qbittorrent`, `512m`/`1.0` for `unpackerr`) to
  both containers in `compose.yaml`. Tier 2 (`cap_drop: [ALL]`) and
  `read_only` remain deliberately deferred to the live SSH test phase.
  Verified with `bash -n` and `shellcheck` (clean). `install.sh` now 4275
  lines.
- Presented analysis of **C1** (Portainer's `docker.sock` mount),
  revisiting the original "add a socket-proxy" recommendation more
  critically: found it a weak fit for Portainer specifically, since
  Portainer's real management features (creating/recreating containers,
  deploying stacks) need close to the same broad API surface that makes
  the direct mount risky — a proxy restrictive enough to help would break
  Portainer, one permissive enough to preserve it wouldn't meaningfully
  reduce risk. Also flagged that a read-only socket mount (`:ro`) is a
  commonly suggested but ineffective mitigation. Asked whether Portainer
  is actively used, since removing it entirely is the one change that
  would fully eliminate the finding.
- User confirmed the risk is acceptable: Portainer is actively used for
  container monitoring and manual intervention and considered the ideal
  interface for that; declined to remove it.
- **Remediation 15 (C1, Critical — resolved as accepted risk):** no
  `install.sh` change. Documented the full analysis and the
  accepted-risk decision in `README.md` (Security Notes), replacing the
  original "add a socket-proxy or make it opt-in" recommendation with the
  reasoning above and the network-exposure-based mitigation already in
  place. All Critical findings are now resolved.
- Analyzed **H4** (embedded heredoc scripts not covered by static
  analysis): confirmed exactly which six heredocs are actual bash scripts
  (`tailscale-udp-gro`, `docker-tailscale-fw`, `master-compose-ipv4`,
  `master-network-reconcile`, `master-docker-netfilter-recovery`,
  `caddy-tailnet-env` — the rest write YAML/INI/plain-text config, out of
  scope for shellcheck) and prototyped a `sed`-based extraction approach
  against the real file before writing the final tool.
- **Remediation 16 (H4, High — resolved):** added
  `scripts/lint-embedded-scripts.sh` (new file, `install.sh` untouched).
  Ran it for real: `master-docker-netfilter-recovery` came back
  completely clean; the other five had only `SC2016` (single-quoted `awk`
  program field references, e.g. `'$1 == "-A" {...}'` — intentional,
  correct, not real defects), which the tool now excludes so its output
  stays actionable. Verified the tool actually catches failures too:
  injected a synthetic syntax error into a scratch copy of `install.sh`
  (never the tracked file) and confirmed a non-zero exit with a clear
  `bash -n` error. CI wiring (e.g. GitHub Actions) intentionally not
  attempted — no CI exists in this repo yet, and standing this up wasn't
  confirmed as wanted; the tool runs manually
  (`./scripts/lint-embedded-scripts.sh`) for now. All High findings are
  now resolved. Only **M1** (partial), **M3**, and **M7** remain open.
- User asked to skip **M3** for now and move to **M7** (testing
  strategy). Presented the M7 analysis: Tier 1 (static analysis) already
  done via **H4**; Tier 2 (unit tests) is achievable now without root or
  live infrastructure; Tier 3 (VM integration) and CI wiring are not
  achievable/confirmed right now.
- **Remediation 17 (M7, Medium — partially resolved):** added
  `test/reconcile_functions.bats`, covering `state_value` and
  `owned_file_ok` from the `master-network-reconcile` heredoc. Reused the
  same `sed` marker-based extraction as `scripts/lint-embedded-scripts.sh`
  to pull the heredoc body out of `install.sh`, then an `awk` pass to
  isolate just these two function definitions — the full reconcile script
  is never sourced, since it runs real `flock`/`systemctl` calls at its
  top level the moment it's loaded. Fixture-based test cases (temp
  `state.env` files for `state_value`; temp files with controlled `chmod`
  for `owned_file_ok`) exercise both functions without root, systemd, or
  Docker. First run surfaced two issues, both fixed before trusting the
  suite: (1) Turkish-language `@test` names broke under this shell's
  `tr_TR.UTF-8` locale (bats failed to resolve three test names containing
  `ğ`) — renamed all test descriptions to English, consistent with the
  project's English-code/comments convention, which also resolved the
  locale issue; (2) `owned_file_ok`'s uid:gid:mode match/mismatch cases
  depend on GNU coreutils' `stat -c` syntax, which this macOS dev
  workstation's BSD `stat` doesn't support — added a `HAS_GNU_STAT` probe
  in `setup()` so those two cases self-skip with an explicit reason on
  non-GNU-stat platforms instead of failing on an environment gap
  unrelated to the function's logic (they run for real on the Debian
  production target). All 7 cases pass (2 skipped here). `chown` to an
  arbitrary UID/GID isn't testable without root, so the UID/GID-mismatch
  case for `owned_file_ok` is intentionally not covered. `install.sh`
  untouched. Remaining for **M7**: unit tests for `chain_rules_exact`,
  `jump_is_first_and_single`, `detect_ipv4_route` parsing (all in
  `docker-tailscale-fw`); Tier 3; CI wiring.
- **Remediation 18 (M7, Medium — still partial, further progress):** added
  `test/firewall_functions.bats`, covering six more pure-logic functions
  from the `docker-tailscale-fw` heredoc: `route_value`,
  `chain_rules_exact`, `jump_is_first_and_single`,
  `forward_prefix_is_exact`, `docker_forward_has_no_terminal_drop`, and
  `no_stale_staging_chains`. The five predicate functions each take an
  iptables/ip6tables binary path as their first argument and only ever
  call it with `-S`/`-C` to read state, never to mutate rules, so a fake
  shell-function stand-in (`fake_bin`) supplies canned `-S` rule
  listings/`-C` exit codes per test instead of calling real
  `iptables`/`ip6tables` — no root, no real firewall state touched.
  `route_value` (the shared parsing helper behind `WAN4_IF`/
  `PUBLIC_IPV4`/`WAN6_IF` detection, reused by `detect_ipv4_route` in
  Stage 2) is tested the same way against a fake `ip` returning canned
  `ip route get` output. Investigated `detect_ipv4_route` itself first:
  found it actually lives in `install.sh`'s outer script (not inside any
  heredoc) and calls `exit 1` directly on failure, so it's already
  covered by `bash -n install.sh`/`shellcheck install.sh` directly and
  isn't a fit for the extract-a-function-body technique used here — its
  reusable parsing logic (`route_value`) was tested instead, which is
  what was actually meant by "detect_ipv4_route's parsing logic" in the
  original Tier 2 candidate list. 20 new test cases, all passing (27
  total across both `.bats` files in `test/`). `install.sh` untouched.
  Remaining for **M7**: `check_ipv4_policy`/`check_ipv6_policy` (more
  integration-shaped — coupled to real global state and direct
  `$IPTABLES_BIN -C` calls — likely better suited to Tier 3 than a unit
  test); a survey of the other four embedded scripts
  (`tailscale-udp-gro`, `master-compose-ipv4`,
  `master-docker-netfilter-recovery`, `caddy-tailnet-env`) for further
  pure-logic candidates; Tier 3; CI wiring.
- Surveyed the four remaining embedded scripts for further Tier 2
  candidates, as agreed with the user. `tailscale-udp-gro` has one
  standalone function, `add_default_netdev` (dedupes discovered
  default-route interfaces). The other three
  (`master-compose-ipv4`, `master-docker-netfilter-recovery`,
  `caddy-tailnet-env`) turned out to have none: each is almost entirely a
  `sleep`-based wait loop plus real side effects (`mktemp`+`mv` file
  writes, `flock`, `systemctl restart/start`), with no isolable pure logic
  to extract without first refactoring `install.sh` itself (out of scope
  for a testing-only pass).
- **Remediation 19 (M7, Medium — still partial, further progress):** added
  `test/gro_functions.bats`, covering `add_default_netdev` from the
  `tailscale-udp-gro` heredoc, tested against a fake `ip` returning canned
  `ip route get` output — same extraction technique as the other two
  `.bats` files. 5 new test cases. All 5 self-skip here: the function's
  dedup guard reads/writes `SEEN`, a bash associative array (bash 4+
  only), and this macOS dev workstation's default `/bin/bash` is 3.2,
  which pre-dates associative arrays entirely, unlike the Debian 13
  target's bash 5.x — detected via a `declare -gA` probe in `setup()`,
  mirroring the existing `HAS_GNU_STAT` self-skip pattern from
  `test/reconcile_functions.bats`. 32 test cases total across all three
  `.bats` files in `test/`. `install.sh` untouched. Remaining for **M7**:
  `check_ipv4_policy`/`check_ipv6_policy` (Tier 3 candidate); Tier 3
  itself; CI wiring.
- **First live Tier 3 install test.** With the user's explicit approval,
  ran `install.sh` for real, end-to-end, against the user's own server —
  freshly reimaged to a clean Debian 13 install (same host/IP that had
  been running the pre-remediation, week-old production stack; the user
  wiped it themselves before this session). Verified the target was
  genuinely fresh first (2-minute uptime, 1% disk used, no Docker
  installed) rather than trusting the hostname alias alone. Transferred
  `install.sh` via `scp`, verified its SHA-256 matched the local copy.
  Since `install.sh`'s interactive prompts read from `/dev/tty` directly
  (not stdin — deliberate, so the script stays pipeable from `curl`), a
  simple stdin/heredoc-based automation wouldn't work; instead ran it
  inside a `tmux` session (real PTY) on the server, relaying each prompt's
  text into the conversation for the user to answer, then sending their
  answer back via `tmux send-keys`. This assistant did not choose any
  configuration values itself. Confirmed as instructed each time before
  the corresponding command ran (this includes: `apt-get install tmux`,
  `scp`, the interactive install itself, a targeted `qbittorrent`
  container restart to verify a previously-stale log line, and — after
  the failure below — a diagnostic `modprobe` + `systemctl restart
  master-compose.service`/`docker restart wg-easy` to confirm the root
  cause before touching `install.sh`).
- The install completed Stages 0-4 cleanly (package install, Tailscale
  browser re-authentication, Docker/image pulls, systemd units) and
  failed at Stage 5: `docker compose up --wait` timed out because
  `wg-easy` never reported healthy. Diagnosed via container health logs,
  `docker exec wg-easy wg show`/`ip link`, and `docker logs wg-easy`:
  `wg-quick up wg0` was aborting because its legacy-ip6tables PostUp rules
  needed `ip6_tables`/`ip6table_nat`, which were never loaded on this host
  (a regression in **H1**'s fix — see `SECURITY_REVIEW.md`). Host IPv6 WAN
  connectivity is real and was correctly detected (`ping6` to
  `2001:4860:4860::8888` succeeded, ~15ms) — a red herring raised and
  investigated at the user's prompt, ruled out once it became clear the
  host's own `ip6tables` uses the nftables backend and so never loads the
  legacy modules wg-easy's container needs.
- Loaded both modules by hand and restarted `wg-easy`: `wg0` came up
  successfully, but a **second**, unrelated problem surfaced — `wg show
  wg0 listen-port` returned the image's default (`51820`), not the
  install's configured `65171`, because wg-easy v15+ only accepts the
  WireGuard port via its web UI's first-run setup wizard (persisted to its
  own database), not an environment variable — something **M6** correctly
  designed around, but the healthcheck's fixed-port assertion didn't
  account for. Confirmed the fix (dropping the port assertion, checking
  only that the interface exists) would work by running the proposed
  healthcheck command directly against the live container before changing
  `install.sh`.
- **H1 regression + H5 (new finding), both resolved:** applied both fixes
  to `install.sh` — Stage 4's modprobe step now covers `ip6_tables`/
  `ip6table_nat` alongside `wireguard` (loop instead of one-off, plus
  `/etc/modules-load.d/wg-easy.conf` updated for reboot persistence), and
  the `compose.yaml` heredoc's wg-easy `healthcheck` no longer checks the
  listen port. `install.sh` 4275 → 4290 lines. Verified with `bash -n`,
  `shellcheck`, `scripts/lint-embedded-scripts.sh`, and `bats test/` (all
  clean/passing). Synced `SECURITY_REVIEW.md` (H1 addendum + new **H5**
  entry + updated findings table) and `TODO.md`.
- The server itself is still mid-install (Stage 5 failed before Stage 6/7
  ran) — a follow-up run is needed to actually reach a complete, verified
  install with these fixes in place.
- **Second live Tier 3 install test.** User reimaged the same server clean
  again and gave explicit approval to re-run the (now fixed) `install.sh`
  end-to-end. Same tmux-relay methodology as the first attempt. Progress
  this time: Stages 0-4 succeeded as before, and — for the first time —
  Stage 5 completed cleanly too (wg-easy's healthcheck now passed), then
  Stage 6 (DNS/Caddy, dnsmasq, Caddy, the 5-minute reconcile timer) also
  completed cleanly, all previously unreached. The install then failed at
  Stage 7's own `master-network-reconcile --check` postcondition call.
- Confirmed the underlying system was otherwise fully healthy: all 6
  containers up (wg-easy included, now reporting `healthy`), all core
  systemd units active. A manual `--check` run against the live host
  showed every diagnostic field at `0` except `compose_runtime=1`, traced
  to `check_compose_runtime()` treating wg-easy's still-pending first-run
  setup (`/setup` redirect) as drift — the same condition **H5** already
  accounts for, but this earlier, separate gate didn't. This directly
  contradicted the script's own stated intent (a comment at the final
  summary explicitly says this state shouldn't stop the installer) — an
  M6-era inconsistency invisible until Stage 7 was actually reached, which
  the H1/H5 fixes were themselves needed for.
- Attempted to verify the fix quickly by patching the already-deployed
  `/usr/local/sbin/master-network-reconcile` directly on the server
  (to avoid a third reimage) — this specific action was blocked by the
  auto-mode classifier as an unreviewed live edit outside the tracked
  `install.sh` source. Reasonable call; fixed in `install.sh` instead.
- **H6 (new finding), resolved:** removed `runtime_ok=1` from
  `check_compose_runtime()`'s `/setup/*` branch only — the diagnostic
  message and `WG_CONFIGURATION_INVALID=1` stay, so the periodic
  reconcile timer's own separate operator-facing reporting of this
  condition is unaffected, but it no longer counts as `compose_runtime`
  drift for `all_critical_state_healthy()` (and so Stage 7's `--check`
  gate). The sibling branches (port mismatch after setup, netfilter
  drift) are untouched and still count as real drift. `install.sh` 4290 →
  4296 lines. Verified with `bash -n`, `shellcheck`,
  `scripts/lint-embedded-scripts.sh`, and `bats test/` (all clean).
  Synced `SECURITY_REVIEW.md` (new H6 entry + updated findings
  table/count) and `TODO.md`.
- **Third live Tier 3 install test — first full success.** User reimaged
  the server clean a third time and gave explicit approval to re-run
  `install.sh` again, with all three fixes (H1 regression, H5, H6) in
  place. Same tmux-relay methodology, same default answers as before
  (default downloads path, local DNS enabled, domain `ayc`). All 7 stages
  completed successfully end-to-end for the first time, ending in
  "AŞAMA 7/7 TAMAMLANDI" and the script's own success summary.
- Confirmed live afterward: all 6 containers up (`wg-easy`/`filebrowser`
  reporting `healthy`), all core systemd units (`docker`, `tailscaled`,
  `docker-tailscale-fw`, `master-compose`, `caddy`, `dnsmasq`,
  `master-network-reconcile.timer`) active, zero failed units, and a
  manual `master-network-reconcile --check` now exits `0` — it still
  prints the informational "wg-easy ilk kurulumu tamamlanmamış" message
  (wg-easy's admin account still needs manual first-time setup via its
  web UI, exactly as **M6** intends), but no longer treats that as a
  blocking failure, exactly as **H6** intended.
- This closes out the first full validation cycle for the 2026-07-28
  remediation work (H1 regression, H5, H6) across three live attempts,
  each progressing one stage further than the last (Stage 5 → Stage 7 →
  full success). Synced `SECURITY_REVIEW.md` (Review History), `TODO.md`,
  and `docs/testing.md` to record the successful outcome.
- **M1's remainder, resolved via live capability testing.** User asked to
  test and apply M1's deferred Tier 2 items. Rather than guess at
  `qbittorrent`'s minimal capability needs, tested empirically: spun up
  isolated, throwaway `docker run` containers (same images, never the
  real running stack) with progressively adjusted `--cap-drop`/
  `--cap-add`/`--read-only` flags and inspected their logs.
  `unpackerr` (already non-root) started and ran cleanly with
  `--cap-drop=ALL` and `--read-only` together, no `cap_add` or `tmpfs`
  needed. `qbittorrent`'s root-level s6-overlay init failed under a bare
  `--cap-drop=ALL` (`chown: Operation not permitted`,
  `s6-applyuidgid: fatal: unable to set supplementary group list`);
  adding back `CHOWN`/`SETUID`/`SETGID` alone still failed to create
  `/config/qBittorrent` on a fresh config dir; adding `DAC_OVERRIDE`/
  `FOWNER` on top made it start cleanly — confirmed as the minimal
  working set. Separately tested `--read-only` for `qbittorrent`
  (needing `--tmpfs /run:exec`/`/tmp:exec`/`/var/run:exec` just to get
  past `s6-overlay-suexec` and `noexec`-tmpfs failures) and found it
  broke `PUID`/`PGID` handling outright: files ended up owned by the
  image's default `911:1001` instead of the requested `1000:1000` — a
  real conflict with the shared downloads-tree ownership model **M2**
  depends on, so deliberately not applied.
- **Incident during testing, caught and fixed the same turn:** while
  cleaning up throwaway test containers with `docker rm -f` filtered by
  image name, the filter also matched (and removed) the real, running
  production `qbittorrent` container. Noticed immediately via the
  container list, recreated it with `docker compose up -d --no-deps
  qbittorrent` — no data loss (`/config` is a host bind mount, and this
  fresh install had no real qBittorrent configuration set yet). All
  subsequent test containers were tracked and cleaned up by their exact
  container ID instead.
- **M1 (fully resolved):** applied the confirmed-safe config to
  `install.sh`'s `compose.yaml` heredoc for both containers. `install.sh`
  4296 → 4319 lines. Verified with `bash -n`, `shellcheck`,
  `scripts/lint-embedded-scripts.sh`, and `bats test/` (all clean).
  Synced `SECURITY_REVIEW.md` (M1 now fully resolved, findings table
  updated) and `TODO.md`.
- **Fourth live install + full operational stress test.** With M1's fix
  applied, the user reimaged the server clean a fourth time and re-ran
  `install.sh`; all 7 stages succeeded again, confirming the container
  hardening didn't regress Stage 5. The user then explicitly granted
  broad testing latitude ("test the server without worrying about data
  loss, we're using it for testing") and asked for the install to be
  exercised under realistic operating conditions rather than just
  idle/clean state — configuring real admin accounts, a real WireGuard
  client, and Tailscale exit-node routing from their own Mac.
- Investigated a perceived SFTPGo/WebDAV connection delay (a real client,
  the Infuse app, connecting as user "infuse"): server-side logs showed
  no technical delay whatsoever — 0-7ms request times on the very first
  login, no retries or errors. The delay was almost certainly client-side
  (Tailscale peer setup and/or manual admin-UI configuration time), not
  an `install.sh` or server issue.
- Confirmed reconcile already covers all 6 services (including Portainer,
  via `port_binding_exists`/`http_endpoint_responds`) — no monitoring gap
  found, nothing added.
- Tested the real WireGuard tunnel end-to-end: a real macOS client
  connected, confirmed via `wg show` (successful handshake, real transfer
  bytes) and `docker exec wg-easy ping` to the peer's tunnel IP *from
  inside the container's network namespace* (the host itself has no
  route to `10.8.0.0/24`, so pinging from the host gives a misleading
  100% loss) — 0% packet loss, ~58-107ms RTT.
- Tested the real Tailscale exit-node path: confirmed genuinely active
  (not just configured) via `tailscale status` showing the peer
  `active; direct` with real tx/rx bytes, and via the
  `MASTER-TS-FORWARD` mangle chain's packet counters actually
  incrementing on the `tailscale0 -> eth0` rules.
- **Reboot test.** Rebooted the fully-installed, now-realistically-used
  host. Confirmed **H1**'s fix is genuinely persistent, not incidental to
  the install session: `wireguard`/`ip6_tables`/`ip6table_nat` all
  auto-loaded via `/etc/modules-load.d/wg-easy.conf` alone. All 6
  containers were back up (2 already `healthy`) within 22 seconds, all
  core systemd units active, zero failed units, `master-network-reconcile
  --check` exit `0`, and wg-easy's peer configs/keys persisted correctly.
- **Deliberate drift injection, three at once.** Stopped `qbittorrent`,
  set `net.ipv4.ip_forward=0`, and deleted the
  `MASTER-DOCKER -i tailscale0 -o eth0 -j ACCEPT` firewall rule. The next
  scheduled reconcile cycle detected and repaired all three within 5
  minutes: container restarted, forwarding restored, firewall rule
  reinserted — confirmed via `--check` returning to a clean, exit-`0`
  state, and a second clean cycle 5 minutes later with no drift at all.
  This is the first time this project's self-healing reconcile loop has
  been proven to actively repair injected drift, not just passively
  report a healthy no-op state.
- **Resource-limit (M1) enforcement test.** An isolated throwaway
  container with a 256MB memory limit, pushed past it, was cleanly
  `SIGKILL`ed (exit 137) by the cgroup memory controller without
  affecting the host or any real container — confirms `mem_limit`
  actually enforces.
- **`unpackerr` real-workload test (M1).** With its new `cap_drop: [ALL]`
  + `read_only: true`, a real test archive placed in the watched
  downloads folder was detected, extracted, and cleaned up successfully
  within its normal ~10s poll interval — confirms the new hardening
  survives a genuine extraction workload, not only idle startup.
- **CPU stress test.** Loaded all 4 cores to ~100% for about a minute.
  All 5 web-facing services still responded in single-digit milliseconds
  throughout; a `master-network-reconcile.service` run happened to fall
  inside the stress window and still completed successfully in 4
  seconds. Zero failed systemd units throughout.
- No new bugs found in this round — confirmatory testing validating that
  the day's four fixes (H1 regression, H5, H6, M1) hold up under real
  operational conditions, not just a clean install. Synced
  `SECURITY_REVIEW.md` (H1 reboot-persistence note, M1 real-workload
  note, new Review History row), `TODO.md`, and `docs/testing.md` (Tier
  3 narrative + manual checklist items checked off).
- **Final architecture review, disk-space monitoring, R1.0.** At the
  user's request, considering the server's actual intended use (a
  personal, long-running download/media/VPN box) and how its systems
  relate to each other, did a deep-dive review of `master-network-reconcile`
  (what it tracks and how), systemd unit dependencies, IPv6, container
  DNS, and wg-easy's kernel-module approach, plus live verification of
  each. Findings, all confirmed working as intended:
  - IPv6 works end-to-end, including real egress from inside the
    `wg-easy` container (`ping -6` to Cloudflare succeeded).
  - Containers reach `1.1.1.1`/`1.0.0.1` directly for DNS via Docker's
    own embedded resolver, entirely independent of the host's
    Tailscale-overridden `/etc/resolv.conf` — confirmed by design (L4)
    and live (`nslookup ... 1.1.1.1` from inside a container).
  - wg-easy's host-side kernel-module approach (H1) is the standard
    hardening pattern, not an indirect workaround; the only more-isolated
    alternative (fully userspace WireGuard) would require forking the
    wg-easy image and wasn't pursued (already documented as DD-10's open
    alternative).
  - A Tailscale IP change correctly cascades through firewall refresh,
    `.env` regeneration, and container recreation (traced via
    `ADDRESS_CHANGED` → `STACK_RESTART_REQUIRED`).
  - Caddy/dnsmasq boot ordering was the most scrutinized part, given the
    real risk (losing Tailnet-DNS/Caddy access, though never root SSH
    access, which is independent) if they raced. Found it's already
    defended in depth: `dnsmasq` uses `bind-dynamic` so a missing
    interface at startup never crashes it; `caddy.service`'s
    `ExecStartPre` actively polls for `tailscale0`'s IPv4 (up to 300s)
    rather than trusting `After=` ordering alone; a reverse
    `Wants=`/`Before=` drop-in on `tailscaled.service` re-triggers Caddy;
    and `OnFailure=master-network-reconcile.service` is the final
    backstop. Confirmed via real boot logs: `tailscaled` → `dnsmasq` (2s)
    → `caddy` (1s), zero races observed.
  - Considered adding Tailscale key-expiry monitoring (the node's key
    expires 2027-01-24; nothing currently warns in advance) — the user
    opted to track this themselves rather than add it to `install.sh`.
- **New: disk-space monitoring for `master-network-reconcile`** (see
  Added, above) — the one concrete gap found, given this server's actual
  workload. `install.sh` 4319 → 4343 lines. Verified with `bash -n`,
  `shellcheck`, `scripts/lint-embedded-scripts.sh`, `bats test/`, and a
  live isolated-function test on the server (real disk: healthy;
  artificially filled 10MB tmpfs: correctly flagged unhealthy at 90%).
- **R1.0**: tagged as the first stable, validated release, given the
  cumulative result of today's work — all resolvable audit findings
  fixed (**H1**-**H6**, **M1**-**M2**, **M4**-**M6**, **C1**-**C2**,
  **L1**-**L5**), four successful live end-to-end installs, a full
  operational stress test (reboot, deliberate drift injection, resource
  limits, real WireGuard/Tailscale traffic, CPU stress), and this final
  architecture review turning up no functional defects. **M3** (install
  profiles) and **M7**'s remainder (CI wiring, a few more unit tests)
  remain open, deliberately deferred, not blocking this tag. The
  annotated `R1.0` git tag was created pointing at this state, and the
  resulting `install.sh` was exported to `~/Desktop/install-R1.0.sh`
  (hash-verified identical to the tracked copy) at the user's request.

## End-of-session documentation pass — 2026-07-28

Reviewed every Markdown document in the repository for accuracy against
the current `install.sh` (4343 lines, tagged `R1.0`) and updated the ones
affected by today's work, beyond what was already synced commit-by-commit
above:

- `README.md`: added a version header (`R1.0`); refreshed the **Current
  Limitations** section, which still claimed containers ran "without
  CPU/memory limits, `no-new-privileges`, or reduced capability sets"
  (stale since **M1** was fully resolved earlier today) and still listed
  the unconditional `chown -R` as a limitation (stale since **M2**,
  resolved in an earlier session) — replaced with an accurate note about
  the new disk-space check's inherent limitation (report-only, no
  auto-repair); refreshed the bats-core test count/list; added **M1**'s
  `cap_drop`/`cap_add`/`read_only` details and the `ip6_tables`/
  `ip6table_nat` addition to the **Docker Services** notes.
- `docs/architecture.md`: refreshed all stage/heredoc line-number ranges
  (shifted by today's edits, now 4343 lines total); added the disk-space
  check to reconcile's described check list; added **M1**'s container
  hardening to the service inventory notes; noted `DOWNLOADS_PATH` now
  being in `state.env`.
- `docs/design-decisions.md`: added **DD-12** (why wg-easy's pending
  first-run setup must never gate Stage 7/`--check` — the **H6** fix) and
  **DD-13** (why the new disk-space check reports but never
  auto-repairs); added a live-confirmation note to **DD-8** (container
  DNS independence, verified today); updated the "nftables vs. legacy
  backend" rejected-alternative note, since today's **H1** investigation
  concretely answered a question that note had previously left open.
- `docs/profiles.md`, `docs/testing.md`: reviewed, found already
  accurate and unaffected by anything not already captured in this
  file's entries above — no changes needed.
- `TODO.md`, `SECURITY_REVIEW.md`, `SESSION.md`: reviewed and confirmed
  current (see `SESSION.md` for this session's final Current
  Task/Completed/Remaining/Next-Step summary).

No changes to `install.sh` in this pass (documentation-only, per
instruction). No commit was created for this pass, per instruction — all
of the above are uncommitted working-tree changes as of this writing.
