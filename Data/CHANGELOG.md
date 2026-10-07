# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### 2026-10-07 — Files: one-line details with word buttons; "Seç" for picking several items (v2-226)

- Under the item's name the details panel shows one line: type, size, location, last change and, for a
  shared folder, its open connections.
- The actions are words again: Klasörü aç / İndir, Yeniden adlandır, Taşı, Arşiv oluştur, Arşivi aç,
  Paylaş, Paylaşımı yönet, Paylaşımı kaldır, Çöpe at, Seçimi bırak.
- A "Seç" button beside Yükle: while it is on, every item shows a round check and a click adds or
  removes it (nothing opens); "Tümünü seç" is in the details panel. Seç again, Esc, "Seçimi bırak" or
  opening another folder ends it (DD-244).

### 2026-10-07 — Files in three separate panels; a slimmer details line (v2-225)

- The file list, the details under it and the Favoriler/Konumlar column are separate panels with a
  small gap between them.
- The details panel is half as tall: one line with the item, its location and date (or a shared
  folder's connections) and the actions as icons; hover shows each action's name.
- The item count and total size are gone from the path bar, so it no longer changes width from folder
  to folder (with nothing selected, the details panel still shows them) (DD-243).

### 2026-10-07 — Ana Menü widgets in order; Ağ as a wide row (v2-224)

- Sunucu and Hız sit side by side; the Ağ card is one row tall and two tiles wide below them, the same
  on phones. Each application's totals carry the download/upload icons of the Hız card.
- Düzenle moves the widgets with ◀ ▶ like the application tiles; the order is saved with the layout.
  An arrow that would change nothing is disabled (DD-242).

### 2026-10-07 — "Onar" covers more; last check and a log on the Sağlık card (v2-223)

- Onar now also puts back exit-node forwarding, Tailscale's exit-node and SSH settings, the
  installer's timers, SSH, the clock sync and the record permissions; restarts only the part of
  Konsol (backend or Caddy) or Files that does not answer; frees disk space (apt cache, old journal;
  never your files or the trash) and finishes half-installed packages.
- It also reports what it does not change: a new WAN address, Caddy configuration errors, Podman,
  WireGuard peers that never connected, read-only disks, out-of-memory kills, a pending reboot, an
  expiring Tailscale key, a half-finished update or settings change.
- The Sağlık card shows the date and time of the last check (and whether it came over SSH) and a
  "Günlük" button with the checks and repairs of the last 72 hours or the last week (DD-241).

### 2026-10-07 — Nightly address refresh (v2-222)

- The Tailscale address and Caddy check now also runs once every night between 03:00 and 04:00,
  besides once after each boot. A changed address is picked up by the next night at the latest
  (DD-240).

### 2026-10-07 — "Denetle ve onar" instead of a 5-minute background check (v2-221)

- The Tailscale/Caddy/firewall check no longer runs every five minutes. It runs once after boot and
  when Caddy fails; the firewall alone is checked hourly.
- Ayarlar → Sistem → Sağlık has "Denetle" (report only) and "Onar". Onar checks and repairs the
  firewall, Tailscale and its address, Konsol's and the installed apps' services, DNS and Konsol
  itself, and shows each step as it runs. Only from a Tailscale device.
- When Konsol cannot be reached: `sudo master-onar` over SSH, or double-click `onar.command` on the
  Mac (it uses the SSH host in `kurulum/kurulum.env`) (DD-239).

### 2026-10-07 — "Sistem (/)": full access, no warning strip (v2-220)

- The red "Root olarak çalışıyorsunuz" strip is gone from Files' "Sistem (/)" view.
- `/proc`, `/sys`, `/dev` and `/run` are no longer read-only there: folders and files can be
  created, renamed, moved and deleted like anywhere else. The kernel still refuses most changes in
  `/proc` and `/sys` and says so. Deleting under `/run` or `/dev` can stop a service until it
  restarts or the server reboots. Nothing overwrites an existing file, and a mounted disk is still
  never deleted (DD-238).

### 2026-10-07 — Files: details under the contents, the folder in the address (v2-219)

- The selected item's details and actions moved from the right column to a fixed panel under the
  files. Its height never changes, so selecting something no longer resizes the file area.
- A shared folder shows one line there: Tailscale/WAN state with the days left, the account,
  Yönet and Kaldır. The full connection cards stay on Paylaşımlar.
- Favoriler lists the first eight folders and "Tümünü göster"; Konumlar and the disk stay in view.
- The open folder is in the address: a reload or a bookmark opens it, and the browser's back and
  forward buttons move between folders (DD-237).

### 2026-10-07 — Files behaves like a file manager (v2-218)

- Opening a folder changes only the folder's contents. The toolbar, search box, places column and
  menus stay as they are; nothing on the page is rebuilt or moves.
- On a computer the Files window fills the screen's height and only its parts scroll: the contents,
  the right column, the trash and share lists. Phones keep scrolling the page.
- While a folder loads, the previous one stays on screen, dimmed, with a thin bar under the toolbar.
  A folder that cannot be opened keeps you where you were instead of jumping to the top folder.
- New back/forward buttons; going back returns to the same scroll position. Recently opened folders
  show at once and are refreshed behind the scenes.
- Keyboard: arrows select, Enter opens, Backspace goes up, Alt+←/→ back and forward, Ctrl/⌘+A
  selects all (DD-236).

### 2026-10-06 — Konsol: the page no longer moves sideways (v2-217)

- Fixed: in Files, double-clicking a folder could still shake the page. The first click selects
  the folder and its details make the page taller than the window, so the browser's scroll bar
  appears; when the folder opens, the scroll bar goes away again. Konsol now always keeps the scroll
  bar's room (`scrollbar-gutter: stable`), so pages never move sideways when their height changes. With
  always-visible scroll bars, short pages show an empty strip of that width on the right.
- Fixed: since v2-216 a folder opened from far down a long list was shown from the middle. Opening a
  folder now always starts at its top.

### 2026-10-06 — Files: no jump while a folder opens (v2-216)

- Fixed: opening a folder made the whole page jump sideways and back. While the folder loaded,
  the Files window shrank for a moment, the browser's scroll bar disappeared and everything moved
  by half its width. The window now keeps its height until the folder's contents arrive.

### 2026-10-06 — Files: double-click opens a folder once (v2-215)

- Fixed: double-clicking a folder in Files' icon view opened it twice (`etc/etc`), showed
  "bulunamadı (taşınmış ya da silinmiş olabilir)" and jumped back to the top folder. It happened in
  `/srv` and in "Sistem (/)" alike. A double-click now opens the folder once, and downloads or opens
  a file once.

### 2026-10-06 — Files: "Sistem (/)", the whole server as root (v2-214)

- Files' right column has a new "Sistem (/)" entry under Favoriler. It shows the whole server from
  `/`, as root, with a red strip saying so. Browse, upload, download, new folder, rename, move and
  read text files work as in `/srv`; `/proc`, `/sys`, `/dev` and `/run` are read-only.
- There is no trash there: "Kalıcı sil" deletes at once and asks you to type the item's name (or
  `onayla` for several). A disk mounted at or below the item is never deleted.
- Only from a Tailscale device. The public HTTPS Konsol name never reaches it, and the `/srv` view
  keeps running as the downloads account. It runs as its own service, `master-sistem-dosya` (DD-235).
- Fixed: selecting a file in Files printed "nullnull" under its actions.

### 2026-10-06 — Sunucu widget fits the full addresses (v2-213)

- The Tailscale and WAN addresses in Ana Menü's "Sunucu" card were cut off with "…" when
  the card was narrow. The card's rows now size their text to the card's width: down to 9px in the
  narrowest cell, 11.5px as before in wide ones, so a 15-character IPv4 address always fits (DD-231).

### 2026-10-05 — "Güncelle" beside the clock (v2-212)

- Ana Menü shows the installed version's state next to the time: "Güncel", or "Güncelle v2-…" when
  GitHub has a newer installer. A click asks for confirmation, then the server installs exactly that
  version by itself; the button shows the installer stage and the page reloads when it ends.
- Only from a Tailscale device; a first install or a missing Tailscale login still needs the
  terminal line. Servers on v2-211 or older get the button after one terminal run (DD-233).

### 2026-10-05 — Finder-style Files and a two-card sidebar (v2-211)

- Files shows folders and files as icons, with a column on the right: Favoriler (Sunucu and its
  folders), Konumlar (Paylaşımlar, Çöp), the details and actions of the selection, and the disk.
  The bottom action bar is gone; every action is in the right column.
- One click selects, a second click opens; Ctrl/Cmd and Shift select several items, shown as one
  two-document icon with a count. The list view is one click away (▦/☰) and remembered per browser.
- The sidebar's server resources are a separate card under the navigation (DD-232).

### 2026-10-05 — Ana Menü widgets: Sunucu and Hız 1×1, Ağ 2×2 (v2-210)

- The network chart is gone. "Hız" is a small card with the server's live download/upload, shown
  with download/upload icons. "Ağ" is a double-size card that lists each application's total
  download/upload on one line; more applications scroll inside the card.
- "Sunucu" is a small card with the Tailscale and WAN address, uptime and version.
- On a computer the two small cards stack on the left, "Ağ" sits beside them; on a phone "Ağ"
  takes the full width and the two small cards share a row (DD-231).

### 2026-10-05 — Installer accepts a stopped WireGuard (v2-209)

- An installer run with WireGuard stopped from Ana Menü/App Store ended with "wg0 dinleme portu
  kayıttaki 61001 değil": the final check expected every network up. It now skips the interfaces
  of a stopped WireGuard and of a network closed on its own; open networks are still checked
  (found on the test server, DD-229).

### 2026-10-05 — Home widgets aligned to the tiles, "Sunucu" widget, uniform Store cards (v2-208)

- Application tiles say "Dur"/"Başla" in a larger type.
- Ana Menü: the address block (Tailscale IP, WAN IP, uptime, version, access) is a "Sunucu" widget
  next to the network card; the sidebar ends with the server resources.
- The network card is exactly as wide as two application tiles; its halves are balanced and
  application totals show the name on one line and download/upload below it.
- App Store cards have the same width and layout as the Ana Menü tiles.
- Settings → Caddy: the local-domain card lines up with the "Adresler ve erişim" table (DD-230).

### 2026-10-05 — Overview controls, stopping WireGuard, containers kept off the host (v2-207)

- Ana Menü: "Düzenle" sits in the bottom-right corner of the screen. Application tiles say
  "Durdur"/"Başlat" in words; settings is a gear and logs a terminal icon.
- WireGuard can be stopped and started from its tile and from App Store. Stopping closes every
  network and removes WireGuard's ports and forwarding from the firewall; it stays stopped after
  a reboot or an installer run. Starting reopens the networks that were open before (DD-229).
- Files has only the list view; the "Kartlar" view is gone.
- Containers can no longer open connections to the server itself (any of its addresses), only
  DNS on their own network gateway. Before, this relied on the host firewall alone (DD-229).

### 2026-10-05 — Install on the server with one curl line (v2-206)

- The repository is public (`drs0me1/myserver`). On the server:
  `curl -fsSL https://raw.githubusercontent.com/drs0me1/myserver/main/kur.sh | sudo bash`.
  `kur.sh` downloads the code from GitHub, places it in `/root/debian-server-installer` and
  starts the installer on the terminal. `KUR_REF` installs a specific commit or tag (DD-228).
- The Mac installer (`<version>.command`), its exporter and `Data/app/` are gone. The
  installer no longer reads an input file. A first install asks for the local domain instead,
  with no default (asked again until valid). Re-runs keep the existing name without asking;
  change it in Konsol → Ayarlar.
- Every run upgrades the system first (`full-upgrade`), re-runs included. The re-run question
  is gone.
- `kurulum/kurulum.env` now holds only `SSH_HOST`, for `wireguard.command`.

### 2026-10-05 — Containers write to server folders only as the Files account (v2-205)

- The Podman page has a new "Çalıştıran hesap" choice. The Files account runs the container as the
  downloads uid without any privileges, and its files stay group-writable like everything in `/srv`.
  "İmajın kendi hesabı" keeps the image's user, which is often root.
- A writable server folder now requires the Files account. An image that needs root can use volumes
  or read-only folders. New containers start with the Files account (DD-227).
- After a start, Konsol checks that the container really runs as that account with no privileges.
- Adopting a container that already runs as the downloads uid keeps that account.
- Existing Konsol containers keep running as before. One that writes into a server folder needs the
  account switched the next time it is saved.

### 2026-10-05 — A container's folders can no longer be swapped for another host directory (v2-204)

- A Konsol container bound to a folder under `/srv` used to look the folder up by name at every
  start. Anything running as the downloads account could replace the folder with a link to
  another directory, and a container running as root would then mount that directory.
- Now each start walks the folder without following links and pins exactly that directory. The
  container mounts the pinned copy. A missing or linked folder keeps the container down, with a
  clear reason in its log (DD-226).
- Existing Konsol containers get this the next time they are saved or started from Konsol.

### 2026-10-05 — Files and WebDAV no longer see packages' private data (v2-203)

- Files, WebDAV and the RAR helper run as the downloads account. They can no longer read
  `/var/lib`, where packages keep private state such as qBittorrent's profile with its interface
  password hash. WebDAV also no longer sees the archive staging folder `.arsiv` at all.
- The new `PRIVATE_STATE_ROOT` setting names that folder once, and packages keep private state
  there or readable by root only (DD-225).
- The next installer run restarts Files and WebDAV once. A running archive job is marked
  interrupted, and open WebDAV transfers are cut.

### 2026-10-05 — Containers reach the internet, not the LAN or the tailnet (v2-202)

- Konsol's container guard now also limits what a container opens itself. Allowed: the internet.
  Not allowed: IPv6, the tailnet (it would leave as this exit node), and the private, CGNAT,
  link-local, loopback and multicast ranges of `VPN_BLOCK_DEST4`. This applies to qBittorrent
  and to Konsol containers.
- Replies to a container's publications still pass, and exit-node and WireGuard traffic still
  meets the guard's first rule only.
- On nrm nothing reachable changes: Tailscale already dropped the tailnet path, and the
  provider has no private network or metadata service. On a home LAN or with a cloud provider
  it closes real paths (DD-224).

### 2026-10-05 — Containers wait for the firewall and no longer restart with it (v2-201)

- qBittorrent no longer starts while Konsol's container guard is missing. If the firewall
  failed at boot, it used to start anyway. Now it waits and retries every 10 seconds until the
  guard is in place (measured on nrm, DD-223).
- Konsol containers no longer restart when the firewall restarts: a Tailscale update, a
  WireGuard network change, an installer run or a watchdog repair. Before, each of these
  restarted them and could leave them stopped.
- Container units only check the guard before they start. The firewall, the package engine and
  the container workers, which hold the locks, write it. A missing guard is reported as such.
- The next installer run restarts qBittorrent once, because its Quadlet changes. Existing
  Konsol containers keep their old unit until they are saved once in Konsol.

### 2026-10-05 — Documentation matches the code again (no version change)

- Contract, architecture, folder-shares and three DD records described an older state.
  - The Files unit writes all of `SERVER_ROOT`, and the trash is `SERVER_ROOT/.cop`.
  - WebDAV masks the trash with `InaccessiblePaths` (no tmpfs).
  - The WebDAV registry's package-folder list refreshes on a share save, a removal or an
    installer run (applied at WebDAV's next start), never through the 30-second guard.
- Added what was missing:
  - Konsol container publications and the bridge DNS exception in the port and INPUT
    contracts.
  - Every WAN-address binder in the architecture's address section.
  - The Tailscale-address hand-off to the container worker.
  - The full manifest key list.
  - Package settings files in the single-source rule.
  - Podman, the container guard and the `podman info` check in the stage table.
- Measured on nrm on 2026-10-05: the Files/unrar sandbox no longer reaches qBittorrent's
  interface (DD-180 amended). DD-152 and DD-208 carry amendment notes.
- No code or installer payload changed.

### 2026-10-05 — A failed install no longer loses a package's pending changes (v2-200)

- If an install wrote new package files and then failed before stage 7, the next successful
  run no longer skips applying them. Found on nrm on 2026-10-04: stage 5 (`master-firewall`)
  failed after stage 4, and a later successful run left the package's old placed Quadlet/unit
  in place until `master-modul uygula <id>` was run by hand.
- The installer now leaves an empty marker per package in `/etc/master-stack/moduller-bekleyen/`
  as soon as one of the package's rendered files changes (also when a WebDAV or Files helper
  changes). The marker is removed only after `master-modul uygula` (or `yerlesik` for the
  built-ins) succeeded, or when the package is not installed. A failed `uygula` is still a
  warning, and now the next run tries again (DD-222).
- No manual step for future runs. A host that already missed a reapply before this version
  still needs `master-modul uygula <id>` once, unless the package's files change again.

### 2026-10-05 — qBittorrent's peer port can be changed on the Podman page (v2-199)

- The Podman page's editor for qBittorrent has a new "Eş portu" field next to the interface port
  (DD-221). Saving moves the internet-facing peer port (TCP and UDP on the WAN IPv4 address) with
  everything that depends on it: the container's published ports, qBittorrent's own setting, the
  forwarding guard and the value the installer uses on its next run. The old port closes.
- Saving is refused for a port outside 1024–65535, the interface port, a port another service of
  the server uses and one that is already taken on the WAN address; the form recommends 61000–65535.
- Only a port you actually change is kept across updates, and removing qBittorrent with its data
  keeps it, like the interface port.
- The App Store no longer prints the peer port number (it could be out of date after a change);
  the Podman page and Settings show the current port.

### 2026-10-05 — Reinstalling qBittorrent after deleting its data works again (v2-198)

- Removing qBittorrent with "Profili, torrent listesini ve imajı da sil" no longer forgets the
  interface port chosen on the Podman page or an approved image update (DD-220). Before, a reinstall
  from App Store after such a removal could fail until the installer ran again, because the files the
  installer had prepared still used the chosen port. The removal dialog now says these choices stay.
- Such a choice also outlasts newer package versions: after an approved image update, a newer image
  pinned in the package does not replace it; the image moves with the next approved update. To return
  to the package's values, delete `/etc/master-stack/package-overrides/torrent.env` and the drop-in
  `qbittorrent.container.d/85-konteyner.conf` as root and run the installer.

### 2026-10-04 — qBittorrent's own defaults again, on uncommon ports (v2-197)

- The defaults chosen in v2-196 are withdrawn (DD-219): a new qBittorrent profile again gets only
  what Konsol needs (download folder, interface address and port, login required, legal notice);
  everything else is qBittorrent's own default.
- qBittorrent's ports moved away from the 610xx block to fixed, rarely scanned ports: the interface
  to 62947 (still only on 127.0.0.1) and the peer port to 63851 (TCP and UDP on the WAN address).
  Both are outside the range Linux uses for outgoing connections. An installer run moves an existing
  install; a port chosen earlier on the Podman page keeps its value.
- SSH (22), the share's HTTP port (61010), WireGuard (61001) and Tailscale (41641) are unchanged;
  443 must stay for Let's Encrypt.
- The App Store no longer says qBittorrent opens no peer port; it names the peer port and that it is
  open on the WAN IPv4 address only. In Settings the peer port appears for IPv4 only and without an
  on/off switch: it is a container publication that opens and closes with the app.
- Saving only the download folder on the Podman page no longer fixes the interface port; only a port
  you actually change is kept across updates. An install where qBittorrent was saved there before
  stays on its old interface port until you enter the new one.

### 2026-10-04 — qBittorrent defaults chosen for new installs (v2-196)

- A new qBittorrent profile now starts with the settings chosen in Konsol's review (DD-218): no
  UPnP/NAT-PMP port mapping, no local peer discovery, encryption required, anonymous mode on, up to
  15 active downloads, uploads and torrents, half-finished files kept in
  `/srv/downloads/incomplete` until they finish, and disk space reserved when a download starts.
  Seeding stays unlimited and the interface English, as qBittorrent ships them.
- These are starting values: changes made later in qBittorrent stay. An existing qBittorrent keeps
  its own settings; it gets these only after a reinstall that deletes its data, or by changing them
  in qBittorrent.

### 2026-10-04 — qBittorrent on its own network with only two ports open (v2-195)

- qBittorrent now runs on its own Podman bridge network instead of the server's network (DD-217).
  Its Quadlet file publishes exactly three things: the interface on 127.0.0.1:61006 (Caddy and the
  publication reach it there) and the peer port 61008 on the server's WAN IPv4 address over TCP and
  UDP. Nothing is published on Tailscale or any other address, and Konsol's container guard drops
  every other packet into that network.
- The peer port is fixed at 61008 and is reachable from the internet, so other peers can connect
  to the server. Before, qBittorrent listened on every address but the firewall closed all of them
  on the WAN.
- On this network qBittorrent has no IPv6 peers. If the server's WAN address changes, run the
  installer again.
- Existing qBittorrent installs: reinstall it from App Store once (the install sets the interface to
  listen inside its network); without that its interface does not answer after the update.
- The Podman page shows the network's name and labels the WAN publication as internet access.
  Changing the interface port there also moves its line in the Quadlet file.

### 2026-10-04 — Podman page, open ports and app navigation (v2-194)

- The container page is now called Podman in the sidebar and in its title (DD-216); its address,
  bookmarks and the old Settings links stay the same. The installer summary points to Konsol → Podman.
- The Access column shows the ports a host-network container opens (DD-215). qBittorrent used to
  show only "Sunucu ağı (host)"; now each port appears as ip:port with its protocols, for example the
  peer port on the WAN, Tailscale and local addresses and the interface on 127.0.0.1. The list shows
  up to three ports and "+N port daha"; the detail lists every address. The labels say which address a
  port is bound to; whether it is reachable from outside is still the firewall's decision.
- Installed applications no longer appear in the sidebar ("Kurulu uygulamalar" is gone, DD-216):
  WireGuard and qBittorrent open from their Ana Menü icons, as before also from App Store.
- Fixed: on a fresh load the qBittorrent row could read "torrent" for up to ten seconds; it now shows
  the container name until the app list arrives and then the application name right away.

### 2026-10-04 — Image update check and container row controls (v2-193)

- Konsol checks whether a newer image build is published (DD-214): the Konteynerler page asks
  on open (answers cached for six hours) and "Güncellemeleri denetle" checks again. Only registry
  manifests are read; nothing is downloaded and nothing updates by itself.
- A row with a newer build shows "Güncelleme var"; the summary counts them and the detail shows
  the state, the followed tag and the check time. After a confirmation the image is updated:
  qBittorrent follows `lscr.io/linuxserver/qbittorrent:latest`, pulls the new digest, restarts and
  is verified; on failure the previous image and files return. The Quadlet file always names the
  exact running digest, and the choice survives installer runs.
- Container rows: start/stop and edit now sit right before the name, remove stays at the end; the
  icons are the home tiles' own (play/pause, settings sliders, trash), bare like them. The rows follow
  the table's own width, so with the sidebar open a narrow window shows cards instead of squeezed names.

### 2026-10-04 — Compact Ana Menü and container controls (v2-192)

- The network widget occupies two of six desktop slots; narrower screens use four
  or two slots. Fixed-height chart and traffic-table areas keep the widget compact.
  Application traffic remains cumulative; only server traffic shows live rates.
- Home application cards are about 16% narrower on desktop, with the same height
  and 44 px action targets. The order is start/stop, settings, logs.
- The sidebar entry is Ana Menü. Clock/date replace the home title instead of
  appearing in the sidebar. Home refreshes every five seconds, without a Refresh
  button, duplicate ten-second reads or hidden-page polling.
- App Store cards omit subtitles; descriptions remain in Details. Container rows
  show only the application/container name, status, resources and access, followed
  by start/stop, edit and remove. Unsupported actions remain disabled; ownership,
  confirmations and data-retention behavior are unchanged.
- DD-213 records the contract. Five fixture browser suites and 174 Bats checks
  passed; three checks skipped because this Mac lacks GNU timeout. Root and
  `Data/app` contain the verified v2-192 portable installer. No server deployment.

### 2026-10-04 — Installed applications and one network widget on the overview (v2-191)

- The home tiles contain only installed applications. Dosyalar, Ayarlar and App Store
  remain in the sidebar; Paylaşımlar remains a tab inside Dosyalar, not a separate
  sidebar entry. None has a duplicate home card.
- Each application has three fixed icon positions: settings, start/stop and logs.
  Unsupported actions leave an empty position; WireGuard has no start/stop action.
  Logs open a dialog using the existing module journal.
- Clock/date move below the sidebar resources, alongside WAN/Tailscale addresses,
  version and uptime. The separate home clock/system widgets and their unused SVG/CSS
  are removed.
- Network is the only home widget, fixed at full width. Hide/show and application
  reordering keep the existing server layout contract; removed saved IDs are ignored
  and an older network width is normalized to four columns.
- The live server rates/chart and the borderless application table share equal width
  and height. The table has application icon/name, cumulative download total and
  cumulative upload total columns in a fixed-height scrolling area. Only the server
  section shows rates; application totals use byte units, never bytes/s. Unavailable
  totals remain unknown. Existing traffic sources and authentication are unchanged;
  qBittorrent's all-time totals can lag until its next statistics-file save.
- Regression coverage includes log timeout/retry and late answers, table scroll/focus
  retention, three icon hit targets and responsive layout in both themes. The mobile
  edit toolbar stays below the tiles rather than covering them on short screens.
- DD-212 records the contract; local validation results are in `SESSION.md`.
  Source and both repository portable installers are v2-191. Each version change also
  rebuilds its installer in the repository; no Desktop copies or separate snapshots.
  No live deployment performed.

### 2026-10-03 — Main-sidebar container manager (v2-190)

- Containers moves from Settings into the main sidebar with containers, images, volumes
  and networks. The accepted design gains real lifecycle controls, details/logs, creation
  and configuration forms; old links redirect to the new page.
- Generic containers retain ports, mounts, environment and startup settings across
  recreation. Manual stop remains effective at boot; stopped editing does not start the
  container. Resources in use cannot be deleted, and removing a container keeps its data.
- App Store applications retain their package lifecycle. qBittorrent's listener port and
  download folder can be changed through its adapter; publication and installer re-runs
  use the durable port setting. Existing account settings remain in the app form.
- Explicit local/Tailscale/internet port scopes are enforced on managed bridges. Operations
  report actual completion or failure, reject stale edits and keep secret values private.
- Implementation and acceptance evidence: see `SESSION.md` (DD-211).

### 2026-10-03 — Icon-only tile actions; v2-188 live acceptance (v2-189)

- **Tile actions are bare icons** (DD-210; user: "fon rengi olmadan sadece simge"): Ayarlar and Durdur/Başlat
  under the overview's application tiles show only their icon — no text, background or border, also on
  hover and press. Their names are the accessible label and the tooltip ("qBittorrent ayarları",
  "qBittorrent: Durdur", "…: Durduruluyor…"); the keyboard focus ring stays; each keeps a ~44 px invisible
  touch area. Confirmation, busy lock and state follow-up are unchanged.
- Fixed: when a Durdur/Başlat request finished, its redraw pulled keyboard focus back to the tile even if
  the operator had moved elsewhere.
- **v2-188 on nrm (Astra, 2026-10-03):** installed from the frozen runtime archive (sha256
  `3739392986a2369522eff6e0d0b6c986a527e50fc297aaa749f0c401e81b3b5f`) with scratch inputs, defaults and `E`;
  exit 0, core services active, the operator's qBittorrent username, password hash and save path unchanged
  (digest before/after). Real browser: native qBittorrent popup (new tab, noopener), settings prefill with a
  blank password while running and stopped, cancelled stop, stop → start from the tile. Isolated Podman
  fixture with the deployed worker, quadlet and pinned image: the install form's account, password and
  folder accepted by native qBittorrent at first start, a running change with a library bind and old-login
  rejection, a stopped save keeping the hash; cleanup complete. qBittorrent 5.2 answers a successful login
  with 204 (no body) and a wrong one with 401; the fixture first expected 5.1's "Ok." (test fixed, no
  product change). Linux Bats `master-modul installs qBittorrent` 1/1 on nrm; Konsol health all ok.
- **Verified locally:** see SESSION.md.

### 2026-10-03 — Ayarlar and Durdur/Başlat under the overview's application tiles (v2-188)

- **Action row under installed applications** (DD-210): each installed App Store application's tile on
  Genel bakış now has a compact row beneath its icon. **Ayarlar** opens the app's settings form
  (qBittorrent) or, without one, its Konsol page (WireGuard). **Durdur/Başlat**, only for apps that can
  stop (qBittorrent), follows the server's state: Durdur asks the same confirmation as App Store, both go
  through the usual lifecycle and progress, the button is locked while the operation runs and shows
  "Duruyor…"/"Başlıyor…", a refusal is shown and the button stays usable. Built-in tiles (Dosyalar,
  Paylaşımlar, App Store, Ayarlar) get no row; edit mode shows none. This replaces v2-187's single settings
  icon. The icon itself still opens the app's web UI while it runs.
- **Verified:** see SESSION.md.

### 2026-10-03 — qBittorrent install form, direct app launch, settings action (v2-187)

- **App Store → qBittorrent → Kur opens a form** (DD-210): username (default `admin`), password
  (required, twice) and download folder (default the downloads folder; the safe folder chooser). Nothing
  is sent until a valid submission; Vazgeç/Escape changes nothing; a server refusal keeps the typed
  values and no install starts. The values are written into qBittorrent's profile before the container
  first starts, so there is no temporary password step. A failed install returns a kept profile and
  folder to what they were.
- **The app opens itself:** while qBittorrent runs, its overview tile, its sidebar entry and App Store's
  "Aç" open qBittorrent's web UI in a new tab (the public name on Konsol's public address, the tailnet
  name on the tailnet). Stopped, or without a public name on the public address, they open its Konsol
  page instead.
- **Settings action:** a small settings button beneath the qBittorrent tile opens a dialog for the
  username, a new password (blank keeps the current one) and the download folder; one save, one short
  restart, a stopped app stays stopped.
- Generic: `konsol.json` `form` + manifest `PAKET_KUR_AYAR`; the shell, backend and engine name no
  application. WireGuard installs as before.
- **Verified:** see SESSION.md.

### 2026-10-03 — Podman in the base, qBittorrent as a Podman container, Settings → Konteynerler (v2-186)

- **Podman is part of the base** (DD-208): stage 1 installs `podman` and `netavark` without
  recommends and requires `podman info` (checked again in stage 7; the summary prints the
  version). No daemon, socket or auto-update timer is enabled; Docker stays out (DD-152).
  v2-185's App Store package "Podman" (never released) is gone: Podman is not an application.
- **Settings → Konteynerler** (a sixth tab): the read-only container view — every container with
  state, image, unit, mounts, ports and a masked log tail (100–1000 lines) — now from
  `GET /api/konsol/konteynerler/*` in the base. No start/stop/remove; environments never shown.
- **qBittorrent runs in Podman** (DD-209) and stays an ordinary App Store application (tile,
  sidebar, page; a "Konteyner" chip in the App Store): the linuxserver image pinned by digest,
  a quadlet unit `qbittorrent.service`, host network, the downloads account's uid, only the
  profile and the downloads folder mounted (same path), UI on 127.0.0.1 only. The page links
  to its container view. Stop removes the unit so nothing starts at boot; remove keeps the
  image, `--veri` also deletes it. A download folder outside the downloads tree is bind-mounted
  through a quadlet drop-in. The Debian package `qbittorrent-nox` is no longer used.
- Engine: `PAKET_CALISMA=konteyner`, `PAKET_KONTEYNER` (quadlet into `/etc/containers/systemd`)
  and `PAKET_IMAJ` (digest-only image, pulled once; removed by image id).
- qBittorrent page: the account form no longer loses a typed password (or the half-typed repeat,
  focus and caret) when the 10 s status poll or Yenile redraws the page; the service bar no
  longer shows the text "null" for an absent item.
- Manual step for a host that ran an earlier version with qBittorrent installed (fresh-install
  rule, no migration): `systemctl disable --now qbittorrent-nox@<user>.service` before
  installing qBittorrent from the App Store again; the old profile in `/var/lib/qbittorrent`
  is reused by the container as is.
- **Verified:** see SESSION.md.

### 2026-10-02 — WireGuard network creation on a fresh host; a one-card creation screen (v2-184)

- Fixed (DD-207): creating a WireGuard network from Konsol failed with "install: cannot change
  permissions of '/etc/wireguard/clients-wg0'" when `/etc/wireguard` did not exist while the
  root backend started (a host where WireGuard was installed later, or the folder was removed and
  created again): systemd had skipped its writable bind. The installer now creates every
  package-declared backend write path before starting the backend and restarts a backend that
  sees one read-only; the store engine repeats the check after installing, starting or applying
  a package; Konsol keeps following an operation through that brief restart; `master-wg` names
  the problem and the remedy instead of a raw `install` error.
- The new-network screen is one card as wide as the windows (label and port side by side, DNS,
  what will happen, buttons). DNS options are two lines, so the network settings, peer add and
  peer edit windows show the whole list without scrolling inside.
- **Verified:** Mac — 174 Bats (two new), 426 Python, all eight fixture browser suites. nrm —
  174 Linux Bats; the faulty state reproduced (backend started without `/etc/wireguard`, a
  later folder read-only for it), then the v2-184 installer created the folder and restarted the
  backend with a writable mount; App Store install of WireGuard and a network created through
  Konsol's API (HTTP 201, wg0 up) and removed again; the folder removed and recreated under the
  running backend was repaired by `master-modul uygula` with one backend restart (none on the
  second run); the creation screen is one 560 px card on the live host.

### 2026-10-02 — Overview edit mode, server-side layout and a network card (v2-183)

- Genel bakış has a **Düzenle** pill bottom-left (DD-206): tiles can be dragged (mouse or
  finger) or moved with arrow buttons, each widget gets a width of 1–4 columns and a hide/show
  switch; Bitti saves, Vazgeç/Escape discards, Varsayılan restores the defaults. The layout is
  stored by the root backend (`KONSOL_AUTH_DIR/duzen.json`), so every device shows the same.
- The clock card shows time, date, uptime and the Tailscale and WAN addresses; the host/OS/kernel
  line moved out (Ayarlar → Sistem has it).
- New **Ağ** card: the WAN interface's download/upload rates every 2 s with a two-minute chart,
  and each installed application's totals — qBittorrent's own all-time figures from its
  statistics file (with the time it saved them), WireGuard's interfaces since the networks came
  up — through a new optional package module (`PAKET_TRAFIK`, `trafik.py`); the shell still names
  no application. systemd IP accounting was tried and dropped: on Debian 13 a daemon-reload loses
  those counters.
- **Verified:** Mac — 426 Python (17 new in `test_overview`), 172 Bats, all eight fixture browser
  suites (panel-ui drives the whole edit flow, a mouse drag included). nrm — 172 Linux Bats, the
  overview tests with Debian's Python; installer runs over v2-182 (exit 0); live from the Mac
  without a session: rates every 2 s, a 120 s chart filled at once, a layout saved through the real
  backend, read back after a reload and reset (`duzen.json` gone); with qBittorrent and WireGuard
  installed for the test, their totals (qBittorrent's survive a daemon-reload); both removed
  afterwards with their data and apt packages.

### 2026-10-02 — Status widget: charts only, larger (v2-182)

- Genel bakış → Sistem durumu no longer repeats the health-check texts (Ayarlar → Sistem →
  Sağlık has them); the pill in the card head keeps the verdict. The CPU and RAM rings and
  the storage pie grew from 58 to 84 px and sit in three equal columns that fill the card.
- **Verified:** Mac — 171 Bats, all eight fixture browser suites (panel-ui: no check lines,
  ring ≥ 80 px, both widgets about the same height). nrm — installer run over v2-181
  (exit 0); live from the Mac without a session: rings 84 × 84 px, no explanation lines, the
  two widgets exactly the same height; light/dark/mobile screenshots reviewed.

### 2026-10-02 — No sign-in on the tailnet; the account is the public name's credential (v2-181)

- Konsol's tailnet address (`panel.<domain>`) asks for no sign-in any more (DD-205): Caddy
  still asks the root backend before every request, and on the Tailscale site the backend
  passes every request from another Tailscale device; its sign-in page goes back to Konsol.
  The public HTTPS name keeps the user name and password, the `Secure` cookie and the
  attempt budgets.
- The one-time setup code is gone: no installer printout, no code form, no `master-konsol
  kod`. The operator creates the account — the public name's credential — in Settings →
  Sistem → Konsol hesabı over Tailscale (user name + password, no code); the Panel's
  internet switch still needs it. From the tailnet the password is changed without the
  current one and every session ends; over the internet the current password is required
  as before. The sidebar's "Çıkış yap" and the account name shown to anonymous visitors
  exist only on the public name. `sudo master-konsol sifirla` deletes the account and
  closes the public name.
- **Flagged trade-off:** every device in the tailnet administers the server without a
  password; Tailscale ACLs decide who reaches the panel.
- **Verified:** Mac — 409 Python (22 in `test_konsol_auth`), 171 Bats, browser suites
  `giris-ui`, `settings-ui`, `panel-ui`, `files-ui`, `torrent-ui`, `wireguard-ui`,
  `publications-ui`, `settings-https-ui`. nrm (Linux) — 171 Bats on a fresh copy of the
  tree, `test_konsol_auth`/`test_publications` with Debian's Python; installer run over
  v2-180 (exit 0, stage 7 proves the tailnet gate: 204 and `/giris.html` → `/`); from the
  Mac without any cookie `panel.ayc` pages, Files API and root API answer 200,
  `/giris.html` redirects to `/`, the account name is shown to the tailnet; the public name
  still redirects to the sign-in page, answers 401 on the API, hides the account name and
  refuses account creation (403); Settings → Sistem shows "İnternet hesabı: …" with
  "Parolayı değiştir" only and no sidebar sign-out. `konsol-login-live.py` skips (exit 3)
  because the operator's account exists.

### 2026-10-02 — Public HTTPS address shown without WebDAV's port (v2-180)

- Settings → Caddy showed a ready Panel or application name as `https://<name>:61010`
  whenever WebDAV still used legacy HTTP: the link took WebDAV's own WAN port
  (`manage.https.port`, which is `SHARE_PORT` in that state) instead of the HTTPS listener
  port (`https_port`, `SHARE_HTTPS_PORT`). Caddy itself always listened on 443, so the shown
  address did not open. Only the display changed; site generation, share URLs and package
  URLs already used the right port.
- **Verified:** Mac — 409 Python, 171 Bats, all fixture browser suites; the new
  `settings-https-ui` assertion fails against the previous `ayarlar.js` with exactly
  `https://panel.example.net:61010`. nrm — installer run over v2-179 (exit 0); live
  Settings → Caddy shows the ready Panel name without a port while WebDAV is still on
  legacy HTTP; no `:61010` anywhere in the table.

### 2026-10-02 — Overview widgets trimmed (v2-179)

- Genel bakış keeps two widgets: the clock and **Sistem durumu**, which now shows storage as
  a pie beside the CPU and RAM rings (warn colour from 90 %). The separate Depolama card
  (disk bar, trash size) and the İşlemci history sparkline are gone; the sidebar meters still
  carry the figures. No endpoint or markup change elsewhere.
- **Verified:** Mac — 409 Python, 171 Bats, browser suites `panel-ui` (two widgets, three
  charts, pie caption from the fixture's disk figures), `files-ui`, `settings-ui`,
  `torrent-ui`, `wireguard-ui`, `publications-ui`, `settings-https-ui`, `giris-ui`. nrm —
  installer run over v2-178 (exit 0); live Playwright look at `panel.ayc`: clock and status
  cards only, CPU/RAM rings with the storage pie, health pill healthy after the host's reboot,
  `backdrop-filter` active, no CSP report; light/dark/mobile screenshots reviewed.

### 2026-10-02 — CasaOS-inspired skin and an overview page for Konsol (v2-178)

- Konsol wears a CasaOS-inspired skin (DD-204): a wallpaper (inline SVG, no external
  asset) behind translucent glass surfaces, pill buttons, rounded application tiles with
  tinted icons; light and dark follow the system; reduced-transparency readers and engines
  without `backdrop-filter` get opaque surfaces.
- New landing page **Genel bakış**: clock with host/OS/kernel/uptime, CPU/RAM rings with
  the health pill, storage with trash size, CPU history, and tiles for Dosyalar, every
  installed application (icon and tone from its package), Paylaşımlar, App Store and
  Ayarlar — all from the existing endpoints. An unknown route opens it.
- App Store entries are tiles (same markup and controls, new layout).
- **Verified:** Mac — 409 Python, 171 Bats, browser suites `panel-ui`, `files-ui`,
  `settings-ui`, `torrent-ui`, `wireguard-ui`, `publications-ui`, `settings-https-ui`,
  `giris-ui`. nrm — portable installer run over v2-177 (exit 0); live Playwright look
  at `panel.ayc` with a root-opened session: Genel bakış lands, tiles Dosyalar ·
  qBittorrent (running) · Paylaşımlar · App Store · Ayarlar, health pill shows the host's
  real pending-reboot warning, `backdrop-filter` active, no CSP report in the console;
  light/dark/mobile and App Store screenshots reviewed.

### 2026-10-02 — Package-declared folders, settings and backend write paths, phase 3 (v2-177)

- Packages declare the folders they write into (`PAKET_KLASORLER`; qBittorrent's
  `downloads/incomplete`) and may report the user's current choice through a module
  (`klasorler.py`). Files refuses to select/share/trash them and names the owner,
  share creation refuses them (fail closed on an unreadable report) and WebDAV hides and
  refuses them inside shares — by path, not by folder name (DD-203). The base's
  `TORRENT_TEMP_DIR`, `temp_name`, `--temp-dir` and its reader of qBittorrent's profile are gone.
- `magaza/torrent/torrent.env` holds `TORRENT_UI_PORT` and `TORRENT_PROFILE_DIR`; the
  installer fills a package's own placeholders from its env file, so `defaults.env` and
  `state.env` carry no `TORRENT_*` key. A `PAKET_PORTLAR` key also resolves from the
  package's env file.
- `master-panel.service` takes its `ReadWritePaths` from the packages' `PAKET_ARKAUC_YOLLAR`
  declarations (WireGuard: `/etc/wireguard`), each optional; the unit names no application.
- One package-module loader in `master_settings.py` (publication checks and folder
  reports) that writes no `__pycache__` into the rendered package folder.
- Cosmetics: summaries list the catalogue's names, stale WAN sites are removed by pattern,
  Settings port descriptions and the public-panel warning name no application, base
  comments describe roles instead of products.
- Fresh install only; an in-place host gets the new unit lines and files on the next run.
- **Verified:** Mac — 409 Python, 170 Bats, all fixture browser suites. nrm — two portable
  runs with scratch inputs on the in-place host (exit 0, no warnings; the second confirmed
  the rendered-folder prune removed the stale `__pycache__`); live acceptance: no `TORRENT_*`
  in `state.env`, `torrent.env` rendered and its values in the Caddy site, manifest and
  package API, `--protected="downloads/incomplete=qBittorrent"` on the file backend and the
  same list with owner in `/api/state`, `ReadWritePaths=-/etc/wireguard -…` rendered from the
  WireGuard manifest, the port catalogue resolving `TORRENT_UI_PORT` from the package env, a
  share on or inside the declared folder refused, a temporary folder pointed into a library
  folder reported by `klasorler.py` and refused (profile restored), an ordinary folder shared
  and unshared with no bytecode written into the package folder, WireGuard installed from
  the engine with a network and peer created through the API over the declared write path,
  the firewall check passing and `master-wg` refusing the torrent port by name; WireGuard
  removed again. Linux (nrm) — 409 Python, 170 Bats, firewall, settings, settings-domain,
  torrent-defaults, publications-proxy and install-hardening suites.

### 2026-10-02 — qBittorrent page and settings in its package, phase 2c (v2-176)

- The qBittorrent page is the package's `sayfa.js`/`sayfa.css`; its account and
  download-folder form posts to the package API `/api/uygulama/torrent/{hesap,dizin}`
  and reads `…/durum` (DD-202). Changes apply directly through the package worker
  `ayar.py` (stop, snapshot, write, start; a failure restores both files and restarts);
  the folder change no longer has a 60 s confirmation window.
- Settings has no qBittorrent tab and no `torrent` section; `GET /api/konsol/ayarlar`
  carries no `torrent` key and no account/folder fields. The shell, `ayarlar.js` and
  the root backend contain no qBittorrent code.
- Backend: `PackageContext.worker()` runs a package script that lives under the
  package's own folder as a transient root unit with JSON on stdin, the same private
  path as the base settings and share workers.
- The torrent package's hooks place the page files on install and re-run and remove
  them on rollback (the first live run showed only WireGuard's hooks did).
- Fresh install only; an in-place host receives the new package files on the next
  installer run.
- **Verified:** Mac — 408 Python, 169 Bats, browser suites `torrent-ui` (new),
  `panel-ui`, `settings-ui`, `files-ui`, `publications-ui`, `settings-https-ui`,
  `wireguard-ui`, `giris-ui`. nrm — portable run with scratch inputs on the in-place
  host (exit 0, no warnings; three runs, the first two surfaced the hook and `--lib`
  fixes); live acceptance: package files rendered, the page under
  `CONSOLE_WEB_DIR/uygulama/torrent` (0644 root) and served by Caddy, the module listing
  offers it, `GET /api/konsol/ayarlar` has no `torrent` key, `/api/uygulama/torrent/durum`
  answers 401 without a session and the paths without any hash, bad shapes answer 400
  before the worker, the folder policy refusal comes from the worker, a username change
  and its restore went through the worker (service restarted, profile 0640 uid 1000,
  password hash untouched, audit lines), a folder change to `/srv/media` and back wrote
  the `90-konsol.conf` drop-in and qBittorrent's default save path. Linux (nrm) — 408
  Python, 169 Bats, firewall, settings (package worker block), settings-domain,
  torrent-defaults, publications-proxy and install-hardening suites.

### 2026-10-02 — Neutral backend, package-owned settings, self-checking packages, phase 2b (v2-175)

- The root backend is `master-panel` on `PANEL_SOCKET` (`/run/master-panel/api.sock`);
  `master-wg-panel`, `WG_PANEL_SOCKET` and `WG_PANEL_RUNTIME` are gone (DD-201).
- WireGuard's settings moved into its package: `magaza/wireguard/wireguard.env` holds
  every `WG_*` default and path; `master-wg`, the hooks, the Konsol API module and the
  Mac launcher read it there. `defaults.env`/`state.env` carry no `WG_*` key; the VPN
  endpoint is `WAN_IPV4`; the firewall's destination block lists are `VPN_BLOCK_DEST4/6`.
- Stage 7 asks each installed package to check itself (`paket_denetle`) and verifies
  that absent packages left no tool or drop-in; the re-run prune and the summary note
  (`paket_not`) and counts (`paket_ozet`) come from the manifests and hooks.
- `master-wg net-add` reserves the ports every package manifest declares instead of
  naming qBittorrent, Files and WebDAV; the launcher's intro line names App Store.
- Fresh install only, as the whole store model: a host updated in place keeps the
  old `master-wg-panel.service` running beside the new one until the operator
  runs `systemctl disable --now master-wg-panel.service`, removes
  `/etc/systemd/system/master-wg-panel.service` and `/usr/local/sbin/master-wg-panel`
  and reloads systemd (done by hand on nrm).
- **Verified:** Mac — 403 Python, 169 Bats (browser suites unchanged by this phase).
  nrm — portable run with scratch inputs (exit 0, no warnings) on the in-place host;
  live acceptance: `master-panel` active on `/run/master-panel/api.sock`
  (`root:caddy 0660`), no `WG_*` key in `state.env`, `VPN_BLOCK_DEST4/6` present,
  the package env rendered; `master-wg net-add` refused 61006/61010/61009 naming
  `torrent`/`paylasim`/`dosya` from their manifests; the API state's endpoint and a
  masked profile's `Endpoint` carried `WAN_IPV4`, defaults came from `wireguard.env`,
  `master-firewall --check` passed and the journal lines sat under `master-panel`;
  a second installer run with wg0 and one peer installed passed the package's
  `paket_denetle`, and the summary printed "WireGuard: kurulu — 1 ağ, 1 peer" with
  the package's note; the network and the package were then removed (`--veri`),
  leaving the registry, `/etc/wireguard` and the console folder clean. Linux (nrm) —
  403 Python, 169 Bats, firewall, settings, settings-domain, torrent-defaults,
  publications-proxy and install-hardening suites.

### 2026-10-02 — Konsol pages and application API from packages, phase 2a (v2-174)

- The Konsol shell and the root backend no longer know WireGuard (DD-200). A
  package declares `PAKET_KONSOL` (App Store texts, page declaration and journal
  words in `konsol.json`, rendered by the installer), `PAKET_SAYFA` (its page files,
  placed under `CONSOLE_WEB_DIR/uygulama/<id>/` on install and removed with the
  package) and `PAKET_API` (a Python module the root backend loads from the
  package folder while the package is registered and serves at
  `/api/uygulama/<id>/*` behind the existing gates). WireGuard's page, stylesheet
  and API moved into `magaza/wireguard/`; qBittorrent's App Store texts into
  `magaza/torrent/konsol.json`.
- Konsol builds the "Kurulu uygulamalar" links and sections from the package
  declarations, loads an installed package's page on demand, unmounts it on
  removal and labels journal lines of package APIs (`<id>:<verb>`) with the
  package's own words. `/api/wg/*` is gone; the audit list is
  `/api/konsol/islemler`; Settings → Güvenlik Duvarı names its VPN category after
  the installed package (`vpn_installed`, `vpn_name`).
- Backend unit: no `--master-wg` argument and no WireGuard environment lines;
  `WG_CLIENT_DNS_DEFAULT`/`WG_CLIENT_KEEPALIVE_DEFAULT` are written to `state.env`.
  Stage 7 probes the package-neutral resources endpoint only.
- Found live and fixed before release: the installer did not write
  `CONSOLE_WEB_DIR` to `state.env` (the engine needs it for the page files), and the
  WireGuard hook placed the page after the registry line, so a failed step could
  leave a half-registered package; the page now goes in before the registry, and
  the last package's empty `uygulama/` folder is removed with it. The Linux lock
  tests (`install-hardening-linux.py`) gained the real torrent manifest; their
  fixture had carried no catalogue since the engine became manifest-driven.
- **Verified:** Mac — 403 Python, 169 Bats, all fixture browser suites
  (wireguard-ui, panel-ui, files-ui, settings-ui, settings-https-ui,
  publications-ui, giris-ui). Linux (nrm) — 403 Python, 169 Bats, firewall,
  settings, settings-domain, torrent-defaults, publications-proxy and
  install-hardening suites. nrm — portable run with scratch inputs (exit 0, no
  warnings); live acceptance through Caddy with a root-issued session: the module
  listing carries both packages' texts; without WireGuard its page file is 404
  (302 without a session) and its API 404/409; `kur` placed `sayfa.js`/`sayfa.css`
  (0644 root) and Caddy served them behind the session; network, peer, masked
  profile, QR, peer switch and DNS settings worked through
  `/api/uygulama/wireguard/*`; `master-firewall --check` passed; the journal
  carried `wireguard:<verb>` lines; Settings showed the VPN category, networks
  and port rows from the package; `kaldir --veri` removed the page, the API and
  the VPN category with the firewall check still clean.

### 2026-10-01 — Publication rows from package declarations, phase 1b (v2-173)

- Settings → Caddy no longer names qBittorrent (DD-199). A package publishes by
  declaring a row name, a local name, a loopback upstream and an optional check
  module in its manifest; `master_publications` builds rows, private stubs,
  public sites and status messages from that, loads the check module from the
  package folder and closes the row when the module is missing, broken or
  failing. A declaration without a loopback upstream produces no row.
- qBittorrent's native-login checks moved verbatim into `magaza/torrent/yayin.py`.
  The settings worker, share publisher, firewall helper and Konsol module
  listing use the generic package functions; the WebDAV and Konsol rows stay
  fixed. The manifest reader is shared by the backend and the publication module.
- **Verified:** Mac — 400 Python, 169 Bats, settings browser suites. Linux (nrm) —
  400 Python, both qBittorrent proxy suites (real Caddy and qBittorrent against
  the package's manifest and check module), firewall and domain suites. nrm —
  portable run with scratch inputs (exit 0, no warnings); the rendered package
  folder carries the manifest with its filled upstream and the check module,
  the table lists Panel, qBittorrent and WebDAV from the package catalogue, and
  turning the qBittorrent row on through the real API ran the package's checks,
  obtained the certificate and reached the module listing's public address; the
  row was then restored to its previous off state.

### 2026-10-01 — Firewall, health and ports from package declarations, phase 1b (v2-172)

- `master-firewall` no longer knows WireGuard (DD-198). Installed packages
  declare their needs through a `paket_firewall` hook in a one-word vocabulary
  (`vpn IFACE UDP_PORT NET4 NET6`); the firewall validates every line, keeps
  interfaces and ports unique, writes and checks the rules itself, and a
  malformed or unknown line changes nothing, as a corrupt registry did before.
- The health card asks `master-modul saglik` which units installed packages
  require; WireGuard's networks and qBittorrent's unit come from their hooks.
- Settings → Güvenlik Duvarı port rows for qBittorrent, WebDAV and the Files
  backend come from `PAKET_PORTLAR` in the manifests; the built-in Files got a
  manifest. Base rows are only Tailscale, SSH, Caddy and dnsmasq.
- **Verified:** Mac — 400 Python, 169 Bats, ShellCheck. Linux (nrm) — 400
  Python, firewall, settings and domain suites. nrm — portable run with scratch
  inputs (exit 0, no warnings); then on the real host: `master-firewall --check`
  clean, `master-modul saglik` names qBittorrent's unit, a WireGuard install plus
  `net-add` produced the UDP permit, 13 forward rules, NAT and the tailnet permit
  from the package's declaration with the check clean, a corrupt registry line
  made the firewall refuse without changing a rule, and `kaldir --veri` removed
  every rule again. Settings → Güvenlik Duvarı shows the manifest-declared port
  rows and the health card reads the package units.

### 2026-10-01 — Store engine and package format, phase 1a (v2-171)

- `master-modul` is now a package engine that knows no application (DD-197).
  Each package under `magaza/<id>/` carries a manifest (`paket.env`) and a hook
  file (`kanca`); the catalogue, runtime, start/stop and account capabilities,
  apt packages, tools, unit drop-ins, names and log units come from the
  manifest. The engine places and removes the declared artifacts itself and
  refuses to finish a removal that left any of them behind.
- The installer renders every package folder generically: files with `__KEY__`
  placeholders are filled from its own variables, executables keep 0755, and a
  package is re-applied when a file changed or its manifest says always. The
  summary takes names and info lines from the packages.
- WireGuard and qBittorrent lifecycles moved verbatim into their hooks; the
  built-in WebDAV got a manifest marked built-in. Commands, locks, progress and
  `liste` output are unchanged for Konsol.
- **Verified:** Mac — 400 Python, 169 Bats (fixtures now run the real engine
  against the real hooks), ShellCheck. Linux (nrm) — 400 Python, 169 Bats. nrm —
  portable run with scratch inputs (exit 0, no warnings): every package folder
  carries its manifest and hooks, qBittorrent was re-applied and kept running
  with its name and login state, and a real `kur wireguard`, `master-wg net-add`,
  `kaldir --veri` cycle left no tool, drop-in, modules-load file, key, registry
  row or interface behind, with the firewall check clean.

### 2026-10-01 — Store model, phase 0: the base owns no WireGuard (v2-170)

- Konsol → Ayarlar → Günlük labelled every root-backend event "WireGuard", so
  failed sign-ins and settings saves looked like WireGuard errors. Events are
  now labelled Konsol, Ayarlar, Paylaşımlar, Dosyalar, Uygulamalar or WireGuard
  by their real source, sign-in/settings/share events have their own words, and
  filter chips appear only for kinds present (DD-196).
- The repo folder `modules/` is now `magaza/`, and the WireGuard tool and
  `wg-quick@` drop-in live in `magaza/wireguard/`. The installer renders them
  into the package folder only; App Store install places them, removal takes
  them away, and a re-run removes leftovers when the package is absent. Stage 7
  requires the tool only with the package and its absence without it.
- The root backend's unit is "Konsol root backend"; the installer probes it
  through `/api/konsol/kaynaklar`; Caddy starts without `--environ`, so
  `state.env` is no longer dumped into the journal; the five-minute tailnet
  timer and the module log route look at WireGuard only while it is installed;
  the install summary and confirmation screen mention WireGuard only as a
  package.
- Fixed (found by the live removal test): `master-modul kaldir wireguard` never
  closed the networks on a real host. `systemctl list-unit-files` exits 1 when
  nothing matches, which ended the shutdown listing before the registry was
  read, so `wg0` stayed up with its unit enabled while keys and registry were
  gone. Each source is now read independently; the Bats fixture's systemctl
  exits like the real one.
- **Verified:** Mac — 400 Python, 169 Bats, panel and settings browser suites,
  ShellCheck. Linux (nrm) — 400 Python, 169 Bats, firewall, domain, torrent
  defaults and install-hardening suites. nrm — the fresh v2-169 host re-run
  with scratch inputs (exit 0, no warnings, account kept): the re-run removed
  the tool and drop-in the older base had left, the backend unit is named
  generically, Caddy runs without `--environ`, and the journal since the
  install carries no WireGuard line from our units. Then `master-modul kur
  wireguard`, `master-wg net-add`, and `kaldir --veri` on the real host: unit
  inactive and disabled, `wg0` gone, tool, drop-in, keys, registry row, UDP
  rule and forward chain gone, firewall check clean.

### 2026-10-01 — HTTPS publications no longer depend on WebDAV's mode (v2-169)

- On a fresh install, publishing Panel (or qBittorrent) over HTTPS failed with
  "Önce WebDAV için HTTPS kaydedin veya eski HTTP WAN erişimini kapatın" although
  no folder was shared on the internet: WebDAV without a saved HTTPS name counts
  as legacy HTTP mode, and the DD-191 rule looked at that mode. The real limit is
  Caddy's single WAN port. The rule now checks the live listener: enabling an
  HTTPS publication is refused only while folders are actually shared over
  plaintext HTTP, with a message naming both ways out. While a qBittorrent or
  Panel internet row is on, legacy HTTP WebDAV internet access stays closed and
  the folder cards say that an HTTPS name is needed; saved folder connections are
  not changed.
- Settings → Caddy shows whether legacy HTTP is live (`wan_active` on the WebDAV
  row) and words its note accordingly.
- **Verified:** Mac — 400 Python, 168 Bats, browser suites (publications,
  HTTPS settings with both notes, files, settings). Linux (nrm) — 400 Python,
  168 Bats, firewall and domain suites; the qBittorrent proxy suite needs the
  qbittorrent-nox package, which the fresh host does not have, and now exits 3
  there. nrm — the user's fresh install re-run with scratch inputs (exit 0, no
  warnings, account kept); `panel-public-live.py` then published Panel on
  `panel.example.com` from exactly the refused state (WebDAV in legacy HTTP mode,
  nothing shared) and restored the row.

### 2026-10-01 — qBittorrent link follows the Konsol address (v2-168)

- Konsol opened on its public HTTPS address linked qBittorrent by its tailnet
  name, which the internet cannot reach. The module listing now carries both
  addresses (`urls.tailscale`, `urls.internet`); the qBittorrent page's "Web
  arayüzünü aç" button and the first-login card's address use the public name
  when Konsol itself is on HTTPS and the qBittorrent row in Settings → Caddy is
  on and verified. Otherwise the page says to turn that row on, with a link to
  Settings → Caddy (DD-195 amendment). The tailnet address is unchanged.
- **Verified:** Mac — 399 Python, 168 Bats, seven browser suites including a
  new `https://` origin scenario. Linux (nrm) — 399 Python, 168 Bats. nrm — one
  portable run with scratch inputs (exit 0); on the public Konsol address the
  module listing names `https://qbit.example.com` for qBittorrent and that name
  answers; the public sign-in page keeps HSTS and the session redirect.

### 2026-10-01 — Konsol over public HTTPS (v2-167)

- The Panel row in Settings → Caddy now has an internet switch and an HTTPS name
  like qBittorrent and WebDAV (DD-195). Its Tailscale switch stays on. Enabling
  it needs an existing Konsol account, a DNS-only A record and the typed word
  `onayla`; the dialog states that a public Konsol is full administration behind
  one password.
- Caddy keeps the Konsol routes in one `(konsol)` snippet. The tailnet site and
  the generated public site (`moduller/panel-wan.caddy`, TLS-ALPN, HSTS) both
  import it, so the session check, sign-in exceptions, CSP and backends are the
  same. Backends always see `Host: panel.<domain>`; Caddy alone writes
  `X-Konsol-Kanal`.
- The root backend accepts the public channel only while the publication is
  active and never from the server's own addresses. The one-time setup code is
  refused there; the session cookie is `Secure` over HTTPS. Twenty failed public
  sign-ins within ten minutes close public sign-in for fifteen minutes while
  Tailscale sign-in stays open. One password check per address, two at once.
- The public site shares TCP 443 and the WebDAV socket budgets; it stays open
  even with WebDAV's WAN off. The 30-second guard removes it after an account
  reset or a lost WAN address. Firewall and local-domain changes are still
  confirmed only over Tailscale.
- Review follow-ups before release: each Caddy site opens at most 16 backend
  connections and the unit raises the descriptor limit, so an internet flood
  cannot make the backend refuse Tailscale; the shared sign-in budget is checked
  again after waiting for a hash slot; the typed `onayla` is verified by the
  server; timed confirmations require the Tailscale channel (100.64/10 is also
  carrier NAT) and the domain check reads the browser's real name; the page
  explains legacy WebDAV HTTP before the dialog and warns when renaming from the
  public address.
- Fixed: the installer's confirmation screen still said Konsol had no password.
- New tests: Panel row and site in `test_publications.py`, public channel and
  budget in `test_konsol_auth.py`, snippet wiring in `common.bats`, the editable
  row in `publications-ui.cjs`, opt-in `panel-public-live.py`.
- **Verified:** Mac — 398 Python (4 platform skips), 168 Bats, seven browser
  fixture suites, ShellCheck, Bash/JavaScript syntax. Linux (nrm) — 398 Python
  (1 optional skip), 168 Bats, domain (real Caddy), firewall, settings,
  qBittorrent defaults, settings-systemd, install-hardening and both
  publication-proxy suites. The snippet, `{args[0]}`, `header_up` inside
  `forward_auth`, `max_conns_per_host` and a generated public Konsol site were
  validated with nrm's Caddy 2.11.4.
- **nrm:** two portable runs with scratch inputs, both exit 0 with no warnings;
  the operator's Konsol account and sessions survived. `publications-live` and
  `backend-hardening-live` pass; a spoofed `X-Konsol-Kanal` on the tailnet site
  is overwritten by Caddy. The public acceptance (`panel-public-live.py`) still
  needs a real DNS-only name for the panel and has not run yet.

### 2026-10-01 — Konsol sign-in with a one-time setup code (v2-166)

- Konsol asks for a user name and password again (DD-194). Every page, file and
  API request is checked by the root backend through Caddy's `forward_auth`; only
  the sign-in page and its API are open. A missing session goes to the sign-in
  page and returns to the same Konsol page afterwards.
- The first account is created on the sign-in page with a one-time code that the
  installer prints at the very end while no account exists (24 hours, single use,
  never written to `install.log`). The input file still holds no account.
- Sessions last seven days (HttpOnly, SameSite=Strict cookie). Settings → Sistem
  shows the account with a password change that ends every other session, and
  the sidebar has "Çıkış yap". Five failed attempts from one address within a
  minute block it for five minutes.
- Server command `sudo master-konsol sifirla` deletes the account and sessions
  and prints a new code; `durum` shows the state.
- Stage 7 now checks the open sign-in page, that host-local page requests are
  refused and that the session check answers 401/302; the Files self-check uses
  its loopback port. The Panel row in Settings → Caddy stays Tailscale-only.
- Live tests use a short root-issued session (`master-konsol oturum-ac`) for
  Konsol calls through Caddy; host-side tests use the loopback Files backend.
  New: `test_konsol_auth.py`, `giris-ui.cjs`, `konsol-login-live.py`.
- **Verified:** Mac — 391 Python (4 platform skips), 167 Bats (3 skips), seven
  browser fixture suites, ShellCheck, Bash/JavaScript syntax. Linux (nrm) — 391
  Python (1 optional skip), 167 Bats (1 skip), domain (real Caddy), firewall,
  settings, qBittorrent defaults, settings-systemd and install-hardening suites.
  The panel site with `forward_auth` was validated by nrm's Caddy before release.
- **nrm:** the first two portable runs stopped at stage 7 — master-modul still
  checked Files through Caddy, then the sign-in files were missing from the
  installed page list; both fixed (and a Bats guard now requires every console
  file to be installed). Third run with scratch inputs exit 0. The one-time code
  appears only at the end of the terminal output: not in `install.log`, not in
  the journal. Share registry, qBittorrent profile, WireGuard registry and
  qBittorrent PID unchanged. Live: `konsol-login-live.py` (open sign-in files;
  302/401 for every page, file and API without a session; code creates the
  account once; sign-in, password change ending other sessions, old password
  refused, sign-out; 429 after five failures), share-connections, publications,
  backend-hardening over HTTPS WAN and Tailscale (100/100 Konsol and Files
  requests at 20 parallel with a session; 256 MiB SHA-verified 52.9/57.3 MB/s) and
  the read-only installed-UI browser suite with a session all pass. The test
  account was removed; the host waits for the operator's own first account.
- `publications-live.py` once hit a transient settings lock while restoring and
  left public WebDAV off for a few minutes; it was restored at once, and the test
  now retries that answer and restores every row independently.

### 2026-10-01 — Cross-review fixes for v2-159..v2-164 (v2-165)

- Saving an internet publication in Settings → Caddy now fails at once with the
  real cause when its listener cannot open, instead of waiting a minute for a
  certificate and suggesting a DNS/CAA problem (DD-193).
- Cold-boot recovery firewall: the INPUT and FORWARD guards are independent and
  each is all-or-nothing, so a failed rule can neither lock out SSH nor skip the
  WireGuard forwarding block.
- New folder shares start with Tailscale on only while WebDAV is published on
  Tailscale; turning a folder's Tailscale connection on is refused while that
  publication is closed (same rule as WAN). The create form starts that switch
  off and locked.
- Concurrent requests with the same credentials (an Infuse library scan) share
  one password check instead of competing for the hash slots, so a cold first
  connection no longer gets 503 replies. Limits are unchanged.
- The unreachable standalone HTTPS card is removed; public WebDAV HTTPS is edited
  in the address table, which now names the HTTPS port in legacy HTTP mode too.
  A save's refresh no longer draws data read before the save. A closed WAN share
  card says “WAN” instead of “HTTPS”.
- Caddy no longer logs a warning each time a media player closes a stream;
  proxy errors and failed upstream connections are still logged.
- Installer runs no longer leave a copy of every rendered template in the
  server's `/tmp` (a Bash 5-only cleanup bug; the files were root-only and
  vanished at reboot).
- Smaller: private 403 routes follow the module templates' addresses; clearer
  qBittorrent publication, Files and health messages; deep JSON handled in two
  more parse sites; `__pycache__/` ignored by Git.
- Live tests: `publications-live.py` no longer contains the operator's domain and
  works with a public qBittorrent; `backend-hardening-live.py` follows the
  host's WAN mode; `share-networks-live.py` skips (exit 3) on HTTPS hosts.
- **Verified:** Mac — 374 Python (4 platform skips), 166 Bats (3 skips), six
  browser fixture suites, ShellCheck, Bash/JavaScript syntax. Linux (nrm, Bash
  5.2) — 374 Python (1 optional skip), 166 Bats (1 skip), firewall (including
  cold rescue), settings, domain, qBittorrent defaults, publication proxy on 443
  and 18443, settings-systemd and install-hardening suites. The scoped Caddy
  logging validated against nrm's Caddy 2.11.4 before release.
- **nrm:** portable run with scratch inputs (SSH_HOST=nrm, blank LOCAL_DOMAIN,
  default no full-upgrade, `E`), exit 0. Share registry, qBittorrent profile and
  WireGuard registry digests and qBittorrent PID unchanged; installed helpers
  match source; no new `/tmp` file. Live: share-connections, publications
  (private 403 on every template address, DAV public off/on, restored choices)
  and backend-hardening over HTTPS WAN (57.9 MB/s) and Tailscale (56.9 MB/s,
  SHA-verified, OOM 0) pass; `share-networks-live.py` skipped with exit 3. A
  cold identical-login burst returned 8/8 (Tailscale) and 4/4 (WAN) HTTP 207,
  no 503; six mid-stream client resets wrote no Caddy log line. Health green.
  137 leaked template copies and old test trees were removed from `/tmp`.

### 2026-10-01 — Per-connection WebDAV policies and dual-card Shares (v2-164)

- Each folder keeps one ID/account while Tailscale and WAN independently control
  enabled state, RO/RW and expiry (DD-192). Both off is valid. New shares use
  Tailscale on/RO/seven days and WAN off/RO/seven days.
- Schema 4 stores both connection policies. Valid schema 3 converts in memory
  and `prepare` persists it without rotating accounts, changing identity/timestamps
  or renewing expiry. Schema 2 and conflicting legacy fields in schema 4 fail
  closed. Stale global-policy updates and pause requests require a page refresh.
- Nested partial saves preserve omitted values under the locks. Explicit RW needs
  acknowledgement in the selected scope; toggles never renew expiry. The receiving
  listener enforces its policy on DAV writes, transfer chunks and staged uploads,
  including cached logins.
- Shares shows two cards with independent controls, address/copy and Infuse
  details, HTTPS or honest legacy-HTTP labeling, and global Caddy gate reasons.
  Candidate card URLs may remain while off; `row.urls` lists only active scopes.
  Shared account/path/password management remains separate. Share edits still
  restart active WebDAV and interrupt all transfers; configured HTTPS renewal
  remains available with no active folders under its existing global gate.
- **Verification (reported by the main implementation task):** 36 new tests
  passed on macOS/Debian; full Python 366 (four macOS skips, one Linux skip);
  Bats 165 (three skips); six browser fixture suites passed, including Files at
  ten widths in both themes, with screenshots reviewed. Portable deployment on
  `nrm` exited 0; schema-3 migration matched the expected normalized schema 4
  exactly, preserving credentials, identities, IDs and absolute expiry. Settings
  and qBittorrent bytes and qBittorrent PID stayed unchanged. Real HTTPS/Tailscale
  connection acceptance passed with byte-identical registry cleanup; read-only
  installed UI passed at three widths/two themes with zero errors or API writes.
  See [SESSION.md](SESSION.md) for exact evidence and final host health; native
  client acceptance is not implied.

### 2026-09-30 — Compact local-domain settings and DNS guide (v2-163)

- Limit the Caddy local-domain card to 620 px, with its input and Update button
  on one row. Keep the publication table full-width and the mobile layout fluid.
- Add four manual Tailscale Admin DNS steps below the input, linking to the DNS
  console and showing the current server IP and saved local suffix. Unsaved
  edits do not change the guide. No Tailscale account/API changes are made.
- Preserve local-domain validation/confirmation/rollback and all independent
  HTTPS settings. The operator has now enabled `qbit.example.com` successfully.
- **Verified locally:** publication-table browser/CSP tests at five widths in
  both themes, dynamic guide values, cancelled domain-change flow, existing
  Settings and HTTPS UI regressions; 330 Python cases (4 platform/optional skips),
  JavaScript/Bash syntax, ShellCheck and exact 49-file portable payload parity.
- **nrm:** portable upgrade with scratch inputs, default no full-upgrade and E,
  exit 0. Read-only live browser checks pass at three widths in both themes;
  current IP/suffix and both ready certificates appear without browser errors.
  Settings/share/qBittorrent file digests and qBittorrent PID are unchanged.
  External trusted HTTPS returns qBittorrent login 200, anonymous API 403 and
  WebDAV root 404. Health is green; eight services active, no failed units;
  Caddy, dnsmasq, firewall and systemd validation pass. No fresh OS/reboot,
  authenticated client/transfer test, commit or Desktop copy for this UI change.

### 2026-09-30 — Independent Caddy address table (v2-162)

- Settings → Caddy now lists Panel, qBittorrent and WebDAV with independent
  Tailscale/Internet choices, public domain, certificate state and per-row Save.
  Panel stays private and locked in both UI/API. Local-domain configuration
  remains separate; the effective Caddy configuration is a collapsed detail.
  Responsive rows support both themes (DD-191).
- Direct HTTPS only; no Tunnel, DNS API, arbitrary upstream or new daemon.
  Native qBittorrent login, CSRF/Host protection and login-attempt limits are
  prerequisites, not silently rewritten preferences. Public names share one
  TCP443 permission and the existing connection budgets. Legacy DAV HTTP must
  be disabled or converted before enabling public qBittorrent.
- Off retains the domain without HTTP fallback. Private off answers 403 and
  survives module reapply. Folder accounts/network permissions are unchanged;
  disabled global networks no longer produce copyable share URLs. Transaction
  snapshots restore private routes after first-save failure/crash too.
- Real API rejection exposed duplicate Python exception classes when the
  Settings CLI imported itself via helpers; fixed module identity and added a
  subprocess regression. Native proxy tests caught nondefault-port Host
  rejection: upstream Host omits the public port, while X-Forwarded-Host keeps
  the external authority for CSRF without weakening either protection.
- **Verified:** 330 Python cases on macOS/Linux (4/1 skips), 165 Bats on both
  (3/1 skips), publication-table browser/CSP tests at five widths in both themes,
  existing HTTPS/settings/files/panel/WireGuard browser regressions,
  actual nrm page with no browser errors, syntax/ShellCheck and exact 49-file
  source/bundle/installed-tree parity. Linux firewall packet tests cover
  qBittorrent-only/shared HTTPS, stopped/unsafe-auth closure, manual denies and
  cold recovery. Real native password/settings and isolated Caddy/qBittorrent
  login/cookie/CSRF/Host/Panel-isolation tests pass on ports 443 and 18443.
- **nrm:** three portable runs with scratch SSH_HOST=nrm/blank LOCAL_DOMAIN,
  default no full-upgrade, E, exit 0. Actual private off/on, module reapply and
  public DAV off/on preserve effective choices, verified TLS and folder-account
  bytes. External HTTPS/Tailscale PROPFIND, RO/RW, Unicode PUT, absolute MOVE,
  DELETE, ranges and SHA-verified download pass (31.07 MB/s on a short 32 MiB
  sample; not a speed ceiling). Temporary test accounts/files were removed.
- Final state: Panel private/locked; qBittorrent private; WebDAV Tailscale plus
  `dav.example.com` HTTPS, certificate expiry 2026-12-29. `torrent.example.com` has no
  DNS record yet, so its public DNS/ACME path was not enabled or claimed tested.
  Caddy/dnsmasq/firewall checks pass, no failed units. Final Settings API burst
  (8 parallel, 32 requests) returns 32/32 HTTP200, slowest 213 ms; health is green.
  No fresh OS, reboot,
  native Infuse or future renewal test; no commit or Desktop copy.

### 2026-09-30 — Panel-managed public WebDAV HTTPS (v2-161)

- Settings → Caddy gains a separate public-domain card with DNS guidance,
  save/disable actions, certificate status and expiry. Local names and private
  administration stay unchanged. Only the public WebDAV endpoint moves to HTTPS;
  Files → Shares shows its new copyable address (DD-190).
- DNS must resolve exactly to the assigned public IPv4, without AAAA or proxy.
  Caddy obtains/renews Let's Encrypt certificates using TLS-ALPN on TCP 443;
  no DNS token, WAN port 80, UDP 443 or new daemon. The HTTPS listener requires
  matching Host/SNI. Account scope, password throttles and connection limits stay.
- Existing revision/lock/pending recovery owns the operation. Save commits after
  verified certificate chain/hostname; failure restores the prior setting.
  Explicit removal closes WAN without HTTP downgrade; accounts and Tailscale
  URLs survive. The configured HTTPS listener stays for renewal with no active
  folders. Certificate health is a local probe, not public-reachability proof.
- **Verified:** 318 Python cases on macOS/Linux (4/1 skips); 165 Bats on macOS/Linux
  (3/1 skips), five fixture browser suites, shell syntax/ShellCheck and exact
  48-file portable parity. Linux settings/DNS/domain/native qBittorrent tests
  pass. Isolated firewall packets cover HTTPS renewal/limits, legacy closure,
  Tailscale/WG preservation and cold corruption/recovery. DNS/certificate
  failure, pending crash recovery, stale/mixed requests,
  renewal with paused folders and no-plaintext fallback have regression coverage.
- **nrm:** three portable runs, scratch inputs, no full-upgrade, confirmation E,
  exit 0. Saved `dav.example.com` through the real Settings API; trusted TLS 1.3,
  Let's Encrypt certificate expires 2026-12-29. External HTTPS PROPFIND, RO/RW,
  GET/Range, Unicode PUT, absolute MOVE, DELETE, pause and network isolation pass.
  Private paths return 404; mismatched TLS/Host returns 421. A SHA-verified
  ~32 MiB transfer measured 29.53 MB/s (short acceptance run, not a speed ceiling).
- Actual disable/re-enable closes both WAN ports without breaking Tailscale;
  rerun preserves the domain/certificate. Original share registry remains
  byte-identical after temporary test-account cleanup. Live Caddy page has no
  browser errors, health is green and Caddy/dnsmasq/firewall validation passes.
  No fresh OS, reboot, native Infuse UI or real future certificate renewal was
  exercised. The old WAN HTTP URL no longer works after HTTPS is enabled;
  clients must use the newly displayed HTTPS address. No commit or Desktop copy.

### 2026-09-30 — Remaining audit stages: boot safety, WebDAV and health (v2-160)

- Firewall retains valid owned protection on registry errors; a cold boot gets
  a narrow rescue guard while strict health/pre-start checks still fail. Both
  INPUT policies deny otherwise unhandled interfaces (DD-187).
- Installer creates/repairs user directories through no-follow descriptors,
  skipping special/multiply-linked files and private trees. Module mutations
  share the install lock without nested deadlock; CLI account lookup also uses
  the safe qBittorrent reader.
- Full Linux shell verification found Bash 5.2's `patsub_replacement` changing
  literal ampersands in templates. Rendering now temporarily disables that
  option and restores the caller's setting; Bash 3.2 remains supported.
- Separate bounded scrypt pools, short wait/cache recheck and overload 503 with
  Retry-After preserve credential throttles. PUT/COPY stage outside the global
  mutation lock and revalidate before atomic publication. WebDAV sandbox,
  process/memory/start limits and proxy/backend idle ordering are tightened
  (DD-188); TCP/request budgets and explicit HTTP WAN remain unchanged.
- IPv4-only generated DNS, accurate parser projection, desired-service health,
  Debian kernel reboot detection, controlled deep-JSON errors and actionable
  incomplete-folder versus share-overlap messages (DD-189).
- **Verified:** 281 Python tests on macOS (4 skips) and Linux (1 optional RAR
  corpus skip); 165 Bats on both (Mac 3 skips, Linux 1 negative-flock skip),
  four fixture browser suites, shell syntax/shellcheck and complete 47-file
  portable parity. Real Linux ownership/flock: 28 tests. Isolated firewall
  (including cold settings/share/WG corruption, preserved denies, retry/recovery,
  second NIC and third-party rules), settings, domain/DNS, native qBittorrent
  defaults and transient systemd recovery all pass.
- **nrm:** three portable runs, exit 0; rebooted from 6.12.107 to
  6.12.111+deb13-amd64. Core/optional services and firewall healthy, two WG peers
  retained; kernel warning before reboot becomes green after. All three service
  names return A only, not unusable AAAA. Caddy/dnsmasq/unit validation passed.
- After reboot, 320 burst API requests all 200; 80 parallel PROPFIND all 207;
  WAN 59.36 MB/s and Tailscale 55.22 MB/s on separate SHA-verified 256 MiB
  transfers. Peak DAV cgroup usage reaches its 512 MiB cap by reclaiming cache,
  not growing anonymous memory (~35 MB); OOM and oom_kill remain zero.
- Temporary RO/RW accounts prove password rotation, isolation, pause, Unicode,
  ranges and persistence across rerun/reboot; cleaned afterwards. Original share
  account metadata is identical. qBittorrent config bytes stayed identical across
  installer reruns but its digest changed across the native service reboot;
  the pre-boot contents were not saved, so byte-for-byte profile persistence is
  not claimed. Native fixture tests do prove preservation of chosen preferences.
  No Desktop copy or commit. No fresh Ubuntu installation, native Infuse UI or remote WG-client
  session was tested; HTTP WAN and account-level Tailscale policy are unchanged.

### 2026-09-30 — Audit stage 1: burst admission and filesystem guards (v2-159)

- The Konsol Unix socket, Files and both WebDAV listeners now queue up to
  128 pending connections instead of Python's default 5. This addresses the
  observed Unix-socket admission failures; WAN request, login and TCP limits
  are unchanged (DD-186).
- Both root readers of the service-owned qBittorrent configuration use the
  existing descriptor-safe, bounded regular-file reader. Symlink components,
  FIFOs and other special files are rejected without waiting for input. A
  missing profile still works; an unsafe profile prevents share changes.
- Files rejects root `.cop`, `.pay` and `.arsiv` sources before a rename,
  move or trash batch starts. Moving a nested reserved name into the root is
  also refused; restoring an old trash entry chooses a harmless alternate name.
- Regression tests cover actual socket bursts, bounded FIFO rejection,
  symlink parents, oversized files, mixed selections and ordinary file actions.
- **Verified:** portable payload matches all 46 runtime files; deployed to nrm
  using scratch inputs, default no full-upgrade and `E` (exit 0). All four
  backend listeners report backlog 128; services active and firewall check
  passes. Local Python: 206 tests (4 skips); Linux Python: 206 (1 skip).
  Mac Bats: 163 (3 skips), with physical temporary paths for the no-follow
  fixtures. Shell syntax, shellcheck and diff whitespace checks pass.
  Live: Konsol and Files each 100/100 HTTP 200 at 20 parallel fresh client
  connections; direct Unix socket 120/120 at 24 parallel. Separate 256 MiB
  downloads: WAN 59.72 MB/s, Tailscale 57.53 MB/s, both SHA256 verified;
  each network passed 40 PROPFINDs at four parallel and byte ranges.
  Service memory grew from 15.3 MB to 559.2 MB, including 523.0 MB file cache
  and 34.4 MB anonymous memory. This demonstrates the speed-test/cache
  mechanism, not the cause of the historical 670 MB peak. Test account/files
  removed, existing share registry byte-for-byte unchanged. No reboot or
  fresh-OS/native Infuse test in this stage.

### 2026-09-30 — Tailscale/Caddy auto-updates and maintenance cleanup (v2-158)

- Unattended upgrades now also install Tailscale and Caddy updates from their
  own repositories, besides Debian/Ubuntu security updates. The daily run is
  moved to 04:00 (up to 30 min random delay) so a Tailscale or Caddy restart
  happens at night; stage 7 warns if either repository is missing from the
  policy (DD-184). Reboots stay manual.
- Removed code that only served hosts installed with earlier versions (fresh
  install only, DD-185): the WireGuard registry upgrade helper, the old
  `GET /api/wg/sistem` view, schema-2 share registry conversion, the retired
  health-site and old-share-link answers (now 404), Konsol's rewrites of retired
  bookmarks, the `ui`/`ping` WireGuard rule kinds in the settings view, log
  labels no backend writes and 93 lines of unused CSS. A host installed with an
  older version needs a fresh install.
- Documentation trimmed to current behaviour: retired decisions, CHANGELOG
  entries before v2-145 and older session notes moved verbatim to
  `docs/archive/`; new `docs/decisions-index.md` lists every DD with its status.
- **Verified on nrm:** deployed with the portable launcher and scratch inputs
  (exit 0). `apt-config` lists both new patterns; `unattended-upgrade --dry-run`
  names them as allowed origins and the installed tailscale and caddy packages
  match them; the timer's next run is 04:00. Over the tailnet
  `/api/wg/sistem` and `/api/paylas*` answer 404, resources and health 200.
  Linux unit tests (197), firewall/settings/domain/torrent namespace suites,
  settings-systemd, shares/archives/RAR live and the external WAN share test
  pass. Locally: 163 Bats, 197 Python, the four browser suites, shellcheck.

### 2026-09-30 — Archive jobs page removed (v2-157)

- Files no longer has an "Arşiv işleri" tab. A running job shows as one bar above
  the list with its progress and "İptal et"; starting a job stays in Files (DD-183).
- Ayarlar → Günlük now shows archive jobs readably: start ("sources → result"),
  cancel request and the result with the server's message, including jobs found
  interrupted after a restart. Before, only an opaque job id was logged.
- **Verified:** deployed to nrm; archives-live (ZIP, nested, conflict, invalid
  path, cancel) wrote readable arsiv-olustur/ac/iptal/sonuc lines and Konsol's
  Günlük API returned them. Local mock with recorded nrm replies: no jobs tab,
  bar with İptal et while running, gone after completion, old bookmark opens
  Files, no console errors. 163 Bats, 203 Python. With Node/Playwright now on the
  Mac, all four fixture browser suites pass, updated for the archive bar
  (panel-ui) and the health card plus typed discard (settings-ui).

### 2026-09-30 — Stuck rollback, WAN address change, watchdog, health card (v2-156)

- A settings rollback that keeps failing is retried after 15/30/60/120 s and
  then waits as "takıldı": Konsol shows the error with "Yeniden dene" and
  "Bırak" (typed onayla) instead of retrying every 2 s forever (DD-182).
- A WAN share whose address the provider changed is closed with a reason; a
  Caddy that could not start on the old address is started without it, and the
  installer no longer dies in stage 6 on that address.
- The Tailscale watchdog resets Caddy's start limit before restarting it and
  checks the firewall again once Tailscale answers.
- A damaged archive history is set aside instead of keeping Files from starting.
- New read-only Sağlık card on Settings → Sistem: failed services, Tailscale and
  key expiry, firewall, reboot needed, clock sync, disk/inodes, pending settings.
- A new archive job waits for the previous one to finish removing its staging
  area instead of answering "işlem sürüyor" right after it showed "done".
- **Verified on nrm:** installer removed a WAN site bound to a stale address in
  stage 6 and republished it; a runtime address change closed the site with a
  reason and a Caddy stuck on the old address came back; five failing rollbacks
  became "takıldı" (health red, timer idle), then retry and discard (wrong word
  refused) both worked; damaged history set aside with no restart; reboot into
  kernel 6.12.111: all units active, wg0 after the firewall, sockets 0660/0700,
  no TCP 61008/2019, health green after NTP sync. Caddy's start limit could not
  be reached on Debian 13 (automatic restarts continued), so the reset-failed
  change is precautionary. Local 163 Bats, 201 Python; Linux unit, namespace,
  systemd, share/archive/RAR and external WAN suites pass.

### 2026-09-30 — Faster WebDAV logins, quieter journal, compressed Konsol (v2-155)

- WebDAV remembers a successful login for 10 minutes, so Infuse/Finder requests
  no longer pay one scrypt check each; every limit and check still applies
  (DD-181). Tailnet WebDAV slots 16 → 64; closing replies say so.
- WebDAV and Files replies through Caddy no longer wait ~40 ms each for a
  delayed ACK (Nagle was on for the kept-alive loopback connection).
- The settings rollback timer runs only while a change is pending (it used to
  start every 2 s). Both short timers keep systemd's per-run lines out of the
  journal. The root backend logs audit lines only, no request lines.
- Konsol pages and API replies are compressed; page files revalidate (304)
  instead of downloading again. Concurrent settings refreshes share one run.
- qBittorrent gets lower CPU priority than Tailscale and Konsol; archive jobs
  run niced and store already-compressed media without re-deflating it.
- **Verified on nrm (with v2-154):** WebDAV PROPFIND through Caddy 44 → 1 ms;
  konsol.js 119 → 37 KB (zstd) and 304 on revalidation; guard/share timers wrote
  0 journal lines in 3 min (was ~200); real apply started and then stopped the
  timer; an unconfirmed firewall rule was rolled back after 66 s and the timer
  stopped; qBittorrent nice 10 / CPUWeight 50.

### 2026-09-30 — Private sockets and login, disk and WireGuard safeguards (v2-154)

- The root Konsol backend has no TCP port: a Unix socket for root and Caddy's
  group (`SO_PEERCRED` checked); Caddy's admin API moves from `127.0.0.1:2019`
  to a socket in a `0700` folder. What Caddy relays to the root backend must
  come from another tailnet device, not from the server itself. Downloads-account
  programs (qBittorrent, unrar) can no longer reach either, directly or through
  Caddy. Stage 7 proves it and reloads Caddy (DD-180).
- WebDAV: the 5-failure/60 s IP block also covers Tailscale; 100 failures in
  an hour close a share for an hour to addresses not yet logged in; wrong user,
  paused or unknown shares cost the same hash as a real check.
- WebDAV PUT/COPY and Files uploads stop with 507 before free space falls under
  min(5 GiB, 10%) and remove their temporary file.
- Files backend (unrar) sandbox: loopback-only network, system-call filter,
  hidden processes, private IPC, no writable-executable memory.
- WireGuard networks start only after `master-firewall --check` passes; the
  refresh timer reopens a network that failed for that reason.
- Root backend closes the connection after an error or an unread request body,
  so a body hidden in a cross-site POST can no longer run as a second request.
- **Verified on nrm (installed as v2-154, then v2-155):** no TCP 61008/2019;
  socket modes; downloads uid refused on both sockets and through Caddy (403);
  a supplementary-caddy-group user refused by SO_PEERCRED; Caddy reload works;
  tailnet WebDAV 5th bad login → 429 while local probes stay 401; nested
  RAR/ZIP/RAR extracted by real unrar in the sandbox (exposure 3.0 → 1.4); a
  broken firewall kept wg0 down until the timer repaired both. Local: 162 Bats
  (3 macOS skips), 191 Python (4 skips); Linux: 191 Python (1 skip), four
  namespace suites, real-systemd timer test, share/archive/WAN acceptance pass.

### 2026-09-29 — Per-folder Tailscale / HTTP WAN sharing (v2-153)

- Select Tailscale, WAN IPv4 or both per folder; one account/ID/permission/expiry.
  Existing schema-2 and new shares default to Tailscale; adding WAN requires
  explicit acknowledgement that HTTP exposes credentials/content (DD-179).
- Separate trusted listener scopes and connection pools; Caddy replaces the
  client-IP header. WAN: 5 bad logins/60s → 300s IP block with Retry-After,
  4096-entry bounded history, 4 parallel hashes, 8 backend connections total,
  4 requests/IP. Tailnet retains 16 connections. Edge TCP: 16/IP, 64 total;
  WAN header/idle timeouts are 10s/30s. No bandwidth limiter or new package.
- Open only the existing WebDAV port and `/s/*`; no admin interfaces, public
  IPv6, wildcard bind, NAT/ACL change or automatic exposure of existing shares.
  Manual firewall denies remain effective. Last active WAN share removal/pause
  closes the listener/owned rules; a scoped timer projects expiry and recovers
  interrupted registry operations. Caddy startup checks the firewall first.
- Show labeled copyable URLs/network badges, HTTP consent and limits. Keep
  inline RO/RW and duration controls. Caddy/firewall inventory identifies WAN
  correctly and parses proxy blocks as well as single-line upstreams.
- Add manager migration/publication/recovery tests, real-HTTP budget/scope
  regressions, UI network tests and a disposable external-client acceptance
  script. HTTP remains unsuitable for confidential internet traffic.
- **Verified on nrm:** portable upgrade, Caddy/systemd/DNS/firewall checks,
  external WAN/Tailscale isolation, TCP/request/login caps, pause/expiry cleanup
  and 66 installed Linux share tests. Local 159 Bats and 170 Python cases have
  three platform skips each. No fresh-OS/reboot/native-client certification.

### 2026-09-29 — Integration-only qBittorrent defaults (v2-152)

- Stop forcing UPnP/automatic port mapping, local peer discovery and separate
  temporary storage in new qBittorrent profiles (DD-178). Leave these and other
  user preferences at the installed application's defaults until changed.
- Keep the download path, authenticated loopback WebUI and headless startup
  notice, plus existing nonroot service/sandbox and DNS/Caddy integration.
  Existing profiles and host firewall permissions are unchanged.
- Add exact seed-key and reapply/reinstall preservation checks, plus a native
  isolated Linux comparison and user-choice restart test.
- **Verified:** 155 Bats cases (three platform skips), 126 Python cases (two
  optional native-RAR skips), Bash syntax/ShellCheck and 44-file portable payload
  equality. Native Debian qBittorrent 5.1.0-2 passed the isolated default/login/
  preference-persistence test twice. No installed profile/service was changed;
  full host upgrade, fresh OS installation and reboot were not run this turn.

### 2026-09-28 — WireGuard internet-only (v2-151)

- Retire Local access entirely (DD-177): no creation/settings selector, API
  scope or CLI argument. Network settings now change default DNS only.
- Drop WG host ingress before established/ICMP/Tailscale acceptance; block
  private/CGNAT/link-local destinations even via WAN. Keep internet NAT/return
  traffic and required user-created UDP endpoints.
- Upgrade existing registry policies without modifying keys, profiles, DNS,
  ports or addresses. Remove WG host-rule overrides and only the retired WG
  Caddy instances/template/env files; clean/repeat installs never recreate them.
- Firewall host overrides remain available for WAN/Tailscale only.
- **Verified:** 155 Bats cases (three platform skips), 126 Python cases (two
  native-RAR skips), WireGuard/Settings/Panel/Files browser suites and syntax/
  ShellCheck. Isolated Linux tests cover IPv4/IPv6 NAT, host/old-flow denial,
  private WAN destinations, retained networks and third-party chain preservation.
  nrm upgrade passed stages 0–7; real kernel WG clients on existing wg0 and an
  own new test network reached IPv4/IPv6 internet and public DNS, not host services.
  Test peers/network were removed; original keys/settings/accounts and qB process
  stayed unchanged. Transport was host-loopback to WG, not an external WAN device.
  Fresh OS installation and reboot acceptance are separate, not claimed here.

### 2026-09-28 — Default WireGuard Local access (v2-150)

- New Konsol networks default to Internet + local at the backend. Remove the
  creation access card/toggle and its unused code/styles; update preview/help.
- All peers inherit access to the installed qBittorrent UI on their own network;
  all other isolation remains. Existing network settings can still disable Local,
  and re-runs preserve that saved choice. Explicit CLI/API scopes remain supported
  (DD-176). No key/profile regeneration, new dependency or firewall widening.
- **Verified:** 157 Bats cases (three macOS skips), 121 Python cases (two
  native-RAR skips), WireGuard/Panel/Settings browser suites, syntax/ShellCheck.
  nrm portable upgrade passed stages 0–7. A scope-less test network created with
  `ui`, active WG/Caddy, the narrow firewall permit and qB UI HTTP 200; removed
  only that empty fixture. Eight services healthy, live desktop/mobile passed;
  original registry/configuration hashes, qB process and full normalized firewall
  match before/after. Existing wg0 was already Local-enabled. No fresh OS/reboot
  or external WG-client acceptance claimed.

### 2026-09-28 — Firewall source and rule cleanup (v2-149)

- Missing WireGuard module registration no longer revives retained networks.
  Omit/remove unused project forwarding/NAT chains when no networks are configured.
- Remove redundant terminal returns and single-element multiport generation.
  Preserve required VPN endpoints, actual permissions, user overrides and all
  third-party rules; no legacy service installer is restored (DD-175).
- Strengthen INPUT/NAT drift checks and add clean/repeat/removal regression
  fixtures, while keeping the panel accurate for intentionally absent chains.
- **Verified:** 157 Bats cases (three platform skips), 119 Python cases (two
  native-RAR skips), Settings browser suite, isolated Linux IPv4/IPv6 input and
  routed WG NAT/isolation tests. Portable upgrade and repeat install on nrm
  passed stages 0–7. Project rules decreased 81 → 73; all other firewall content,
  user settings, WG profiles and qB process remained unchanged. Eight services
  healthy; live API/desktop/mobile tests passed. No fresh OS/reboot claim.

### 2026-09-28 — Simplify Internet and WireGuard port lists (v2-148)

- Remove synthetic closed WAN rows for local/tailnet services, arbitrary sockets
  and unsupported IPv6 WG endpoints at the backend source (DD-174).
- List tunnel-local qBittorrent permissions only for IPv4 networks with Local
  access configured. Keep required VPN UDP endpoints regardless of peer/socket
  activity, explicit user allows/denies, network selectors and raw diagnostics.
  Actual firewall policy, services and saved settings are unchanged.
- **Verified:** 157 Bats cases (three platform skips), 117 Python cases (two
  native-RAR skips), Settings browser tests, syntax/ShellCheck and portable nrm
  upgrade. Live API/browser checks confirm WAN 4/2 rows (IPv4/IPv6), one wg0
  IPv4 UI row and no synthetic wg1/IPv6 UI rows; explicit-rule fixtures remain
  editable. Normalized full firewall rules, configuration hashes and qB process
  match before/after; eight services healthy. No fresh-install/reboot claim.

### 2026-09-28 — Remove synthetic Tailscale port entries (v2-147)

- Generate Tailscale port rows from the configured per-family allowlist and WG
  registry, not arbitrary host listeners (DD-173). Remove irrelevant peer/local
  backend/Caddy admin rows at their source; preserve explicit user rules and
  unfiltered technical diagnostics. No hardcoded port exclusions.
- Preserve default-deny protection, required local services, every configured
  WG endpoint, socket bindings, torrent settings and all forwarding/NAT policy.
- **Verified:** 157 Bats cases (three platform skips), 114 Python cases (two
  native-RAR skips), Settings browser suite, portable nrm upgrade and live
  IPv4/IPv6 API/socket checks. Desktop/mobile show only configured tailnet rows;
  raw diagnostics remain intact. Eight services active, no failed units; account,
  share, module/WG registry/profile hashes and qBittorrent process unchanged.
  No fresh install, Ubuntu, reboot or authenticated Infuse claim for this change.

### 2026-09-28 — Minimum tailnet host exposure (v2-146)

- Replace implicit all-port tailnet access with an explicit host allowlist before
  Tailscale's own INPUT acceptance (DD-172). Keep SSH, Caddy, DNS, folder WebDAV,
  self-advertised PeerAPI and every registered WireGuard endpoint. Block other
  new inbound ports by default, including qBittorrent peers and direct backends.
- Preserve operator overrides, loopback, established replies, ICMP, all WAN/WG
  and forwarding/NAT policies. No network deletion, credential change or package
  removal. Peer counts and counters never determine whether a WG port is needed.
- Make the port table use the same allowlist instead of treating any listener
  as tailnet-accessible. Add real IPv4/IPv6 packet, override and drift tests;
  helper changes now trigger both firewall refresh and panel restart.
- **Verified:** 157 Bats cases (three platform skips), 113 Python cases (two
  local RAR skips, native Debian coverage), Settings browser suite and isolated
  Linux packet/settings tests. Portable nrm upgrade and live dual-stack checks
  preserve service/config/WG state; qBittorrent's PID is unchanged. No clean
  Ubuntu/reboot, VPN client throughput or authenticated Infuse acceptance claim.

### 2026-09-28 — Runtime and installer cleanup (v2-145)

- Align active documentation, input-template and launcher messages with built-in
  Files/WebDAV/archive tools, App Store, current settings and no automatic backup.
  Remove unused frontend helpers, old shared-account UI and obsolete CSS.
- Remove unreachable built-in module install/remove/data-delete branches and
  shared-password plumbing. Stop creating `.pay/w` and its marker, exporting old
  credential paths or repairing legacy metadata permissions (DD-171).
- Preserve current folder accounts and all existing data; retain reserved-path
  guards and tolerate absent legacy paths in the WebDAV sandbox. Retired Files
  share routes now consistently answer 410; drop their obsolete state summary.
- Keep all used dependencies and runtime files; no package purge, automatic
  migration, data deletion or extra background service. Add regression checks
  for fresh/legacy trees, retired API gates and first-login secret handling.
- **Verified:** 157 local Bats cases (three platform skips), 108 local Python
  cases (two native RAR skips), four browser suites; all 108 Python cases pass
  on native Debian including real RAR. Reproducible 45-file portable payload,
  nrm upgrade, live UI/API, systemd absent/present-path sandbox and built-in
  idempotency checks pass. Accounts, settings, WG configs and qBittorrent process
  are unchanged. No fresh Ubuntu/full fresh-install/reboot acceptance claim.

Older entries (v2-144 and earlier) are archived verbatim in [`docs/archive/CHANGELOG-before-v2-145.md`](docs/archive/CHANGELOG-before-v2-145.md).
