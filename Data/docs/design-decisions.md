# Design Decisions

## Design decisions and rationale

This document records the *why* behind non-obvious choices in
`install.sh`, so future changes don't accidentally "fix" something that
was deliberate. Entries are derived from reading the script's own inline
comments plus structural inference from the 2026-07-27 audit
(`SECURITY_REVIEW.md`).

Entries that describe removed or replaced behaviour are kept verbatim in
[`archive/design-decisions-retired.md`](archive/design-decisions-retired.md),
and [`decisions-index.md`](decisions-index.md) lists every `DD-*` number
with its status and the file that holds it.

### DD-227: Writable server folders only through the Files account (v2-205)

- **Finding (measured on nrm, 2026-10-05):** a generic container ran as its image's user. For alpine
  that was root, with 11 effective capabilities (`podman inspect`). Podman is rootful without user
  namespaces (DD-208/209), so such a container, or an exploit in it, was host root over every writable
  `/srv` bind. It could chown or plant setuid files, and leave root-owned files that the installer's
  repair walk would silently fix. DD-226 closed the path swap; this closes the privilege.
- **Decision:** a definition carries `user`: `downloads` or `image`.
  - `downloads` renders `User=`/`Group=` from the state's `DOWNLOADS_UID`/`GID`, which must be digits
    and non-zero, else 503. It also renders `DropCapability=all` and a fixed `--umask=0002`, because
    `/srv` is 0775/0664 by the repair walk. `NoNewPrivileges` stays.
  - `validate()` refuses `image` together with any writable bind, before any pull or stop: "Sunucu
    klasörüne yalnız Dosyalar hesabıyla yazılabilir…".
  - After each start the worker proves the account: `Config.User` is `uid:gid`, and the effective and
    bounding capability sets are empty. Podman 5.4.2 prints an empty set as `null`, others may print
    `[]`; both count. A missing field fails closed.
  - A new definition defaults to `downloads`. An omitted value on save keeps the stored one. A
    definition stored before this counts as `image` and keeps running unchanged; it needs the switch
    only when it is saved with a writable folder.
  - Adoption maps the Files uid to `downloads`.
  - The Podman page has "Çalıştıran hesap" (Dosyalar preselected on create), blocks the review until
    the rule holds, and lists the change with its consequences. Details show the running user.
- **Rejected:**
  - An acknowledgement path for root images on writable folders: one preserved boolean is weaker than
    the per-port public acknowledgement. Root-init images that must write `/srv` (LSIO style) belong in
    App Store packages, which have a reviewed home.
  - User namespaces (`UserNS=auto`): they change `/etc/subuid`/`subgid`, and Ubuntu is unverified.
- **Consequences:**
  - Podman sets a named volume's owner once, at its first use (measured on nrm). A new volume at a path
    the image lacks becomes the Files account's. Over an image directory it takes that directory's owner,
    and a volume used before keeps its owner. Either may be root-owned and so read-only for the Files
    account.
  - Images that need root or a port below 1024 may not start under it. The UI says so.
  - qBittorrent's own LSIO image is out of scope.

### DD-226: A Konsol container's bind sources are pinned at every start (v2-204)

- **Finding (measured on nrm, 2026-10-05):**
  - A temporary alpine Quadlet bound `/srv/bindsrc-test/data` read-only.
  - Acting as uid 1000, the test renamed the folder and left a symbolic link to a root-only
    directory in its place.
  - At the next `systemctl start` the container listed the root-only canary file.
  - `podman inspect` still showed the old path.
  - Podman resolves `Volume=` sources by path at every start. Konsol validated them only when
    saving. Under `SERVER_ROOT`, which the downloads account writes, a uid-1000 compromise (Files,
    WebDAV, unrar, qBittorrent) plus any restart of a root generic container meant host root
    access through the bind.
- **Decision:** a base helper, `master_container_binds.py`, runs in each generated unit.
  - `ExecStartPre … bagla NAME SOURCE…` runs after the guard check. It walks each source from `/`
    component by component with `O_DIRECTORY|O_NOFOLLOW` and requires a directory. It checks that
    `/run`, `RUNTIME_DIR` and `KONTEYNER_BAGLAMA_DIR` are root-owned and writable by no one else,
    and releases stale anchors.
  - It then binds the descriptor (`/proc/self/fd/N`, `MS_BIND|MS_REC`, then `MS_PRIVATE`) onto
    `KONTEYNER_BAGLAMA_DIR/NAME/<sha256(index:source)[:16]>`. It verifies that the anchor is a
    mount point with the walked `(st_dev, st_ino)`. On any failure it releases what it pinned and
    the unit fails.
  - `ExecStopPost=-… birak NAME` detaches and removes only empty anchor folders, never data.
  - The Quadlet mounts the anchor, never the path. `RequiresMountsFor=` keeps the real folder as
    a mount dependency. Anchor names are deterministic, so refresh_tailnet's byte comparison holds.
  - Start-time checks are the base invariants only: absolute, no `..`, a non-hidden subfolder of
    `SERVER_ROOT`. Package-declared folders stay a save-time check, so no package code (or its
    uid-1000-owned report) can block an unrelated container at start. The helper takes no lock.
- **Limits:**
  - The pinned directory is the one the walk found. A folder swapped before the start is either
    refused (a link) or a different real folder that uid 1000 could have bound anyway.
  - App Store containers are out of scope: qBittorrent's `torrent_verify` compares the inspected
    source.
  - Existing Konsol containers get the new unit when saved, started from Konsol or re-rendered for
    Tailscale; there is no migration code.
- **Reverse direction:** a root container planting files in `/srv` is DD-227's subject.

### DD-225: Packages' private state is hidden from the uid-1000 data units (v2-203)

- **Finding (measured on nrm, 2026-10-05):**
  - Inside WebDAV's mount namespace `.cop` is mode 000, but `/srv/.arsiv` (the archive staging
    area, 0700 uid 1000) is visible and accessible. The handler alone keeps it out.
  - `/var/lib/qbittorrent`, which holds the WebUI hash and tracker passkeys and is owned by uid
    1000, is readable from WebDAV's namespace as uid 1000, and so from Files and its unrar child.
  - Reads only: `ProtectSystem=strict`.
  - The pivot the hash once allowed is closed since DD-217. A sandboxed unit gets no answer from
    the loopback publication (measured), so this is a confidentiality leak of low severity.
- **Decision:**
  - New `defaults.env` key `PRIVATE_STATE_ROOT="/var/lib"`. The base names no application.
  - `master-paylasim.service` keeps exactly one `InaccessiblePaths=` line: trash, `.arsiv`,
    `-.pay` and `PRIVATE_STATE_ROOT`. A second assignment would reset the list. `.arsiv` has no
    `-`: the Files backend creates it at start, and a missing one keeps WebDAV down (fail closed).
  - WebDAV also gets `RequiresMountsFor=SERVER_ROOT`, like Files.
  - `master-files-panel.service` gets `InaccessiblePaths=PRIVATE_STATE_ROOT` only, because Files
    owns the trash, the staging area and the share name.
  - Package rule: a package's private host state lives under `PRIVATE_STATE_ROOT` or is
    root-only. qBittorrent (`/var/lib/qbittorrent`) and WireGuard (`/etc/wireguard`, 0600 root)
    already comply.
- **Rejected:**
  - A per-package manifest list of masked paths (`-` masks): a path created after the unit
    started stays visible (the DD-207 lesson), and keeping it right needs mountinfo-driven
    restarts.
  - `SystemCallErrorNumber=EPERM` on WebDAV: it weakens the SIGSYS default on the WAN-facing
    service.
- **Cost:** the next installer run restarts Files (a running archive job is marked interrupted)
  and WebDAV (open transfers are cut) once.

### DD-224: Containers may reach the internet, not private or tailnet destinations (v2-202)

- **Finding:** no project layer filtered what a container opens itself. The guard's first rule
  returned every packet not entering a bridge. MASTER-FORWARD matches only WireGuard
  interfaces, and `VPN_BLOCK_DEST4` applied only to WireGuard clients.
- **Measured on nrm (2026-10-05)** from qBittorrent's network namespace:
  - internet by IP: reachable;
  - a tailnet peer: dropped by Tailscale's stateful filtering (`--stateful-filtering=true`,
    DD-74), while the host itself reaches it;
  - quad-100: dropped;
  - the metadata address: no answer; nrm has no private networks.

  So on nrm the change is defense in depth. On a home LAN, or with a provider that serves
  metadata, it closes real paths. It does not depend on a Tailscale flag.
- **Decision:** the guard keeps one rule for traffic that neither enters nor leaves a bridge
  (exit node, WireGuard), so that path still costs one rule (DD-181). Next come the existing
  reply returns, so replies to Tailscale and WAN publications pass. Then, for traffic that leaves
  a bridge for another interface:
  - IPv6 dropped (the bridges are IPv4-only);
  - anything out of `TAILSCALE_IF` dropped;
  - one rule per `VPN_BLOCK_DEST4` prefix, in list order, dropped.

  The list's single owner stays `defaults.env`, and no literal is repeated in the code. A missing,
  empty or invalid list fails closed with 503, so no guard is written and master-firewall reports
  it. Health stays an exact comparison, with one rule per prefix and no anonymous set that nft
  could merge or reorder.
- **Consequences:** a container can no longer reach a NAS or anything else on the LAN, the tailnet,
  or a provider's private network. Konsol's internal networks ("iç ağ") still give no egress at
  all. Internet exfiltration of mounted data stays possible for containers that need the internet;
  qBittorrent does.
- **Not done:** per-network egress modes (no workload needs them yet) and a TCP 25 block.

### DD-223: Container units wait for the checked guard, without Requires= (v2-201)

- **Finding (measured on nrm, 2026-10-05):**
  - qBittorrent's Quadlet had only `After=master-firewall.service`. With the container guard
    table deleted, `systemctl restart qbittorrent` started it anyway: `After=` orders a start,
    it does not hold one back when the firewall failed.
  - Konsol's generated units had `Requires=master-firewall.service` and an `ExecStartPre` that
    applied the guard. `systemctl restart master-firewall` restarted a running Konsol container
    (measured). Every restart source restarted them: a Tailscale upgrade (`PartOf`), a WireGuard
    network change, an installer run or a watchdog repair. A failed apply inside such a restart
    left them stopped.
  - The unit's own apply was an unlocked writer. It could re-open a publication the worker had
    just revoked.
- **Decision:**
  - Package and Konsol container units use `Wants=` + `After=master-firewall.service`, with no
    `Requires=`, `BindsTo=` or `PartOf=`.
  - Their `ExecStartPre` only checks the guard (`master_container_network.py --check`), and
    `RestartSec=10s` retries until it is in place. A container without a network gets no check.
  - Only the locked writers write the guard:
    - `master-firewall`, at boot and on every restart;
    - the package engine, after placing a quadlet;
    - the container and package workers, before a start that changes publications.
  - `check()` now names a missing table ("Konteyner yönlendirme koruması eksik veya güncel
    değil.") instead of a generic read error.
- **Trade-offs:**
  - A container waits until the firewall has applied the guard, retrying every 10 s with no start
    limit.
  - A crash-looping container also retries every 10 s, instead of stopping at the start limit.
  - qBittorrent's interface-port change restarts it without reapplying the guard. Loopback
    publications are not part of the policy, so its start check passes; a test pins this.
- **Not done:** a fail-closed bridge drop in the firewall's cold recovery, and listing waiting or
  dependency-stopped Konsol containers on the Sağlık card.
- **Upgrade:** the next installer run re-places qBittorrent's Quadlet and restarts it once. That
  goes through the DD-222 path, so a failed run cannot skip it. Existing Konsol containers keep their
  old unit, with `Requires=`, until they are saved once in Konsol; there is no migration code.

### DD-222: A package's unapplied change survives a failed install (v2-200)

- **Finding (nrm, 2026-10-04):** stage 7 re-applied a package only when `MODULES_CHANGED`
  named it, and that list existed only in the running installer's memory. Stage 4 had
  already written the new files to `MODULES_DIR/<id>/`, so after a failure in stage 5
  (`master-firewall`) the next successful run rendered byte-identical files, reported no
  change and never ran `master-modul uygula <id>`. The placed Quadlet/unit stayed old until
  someone ran it by hand. A change to a WebDAV or Files helper had the same gap: its restart
  signal for `master-modul yerlesik` was lost the same way.
- **Decision:** a durable marker per package, `MODULES_PENDING_DIR/<id>`
  (`/etc/master-stack/moduller-bekleyen/`, 0700 root, empty files). `render_package_dir`
  writes it at the first changed or removed file, before the package's remaining files are
  processed. Stage 4 writes `paylasim` when `master_shares.py` or `master_webdav.py` changes,
  and stage 6 writes `dosya` when the Files code or unit changes. `ensure_module_files` puts
  every marked package into `MODULES_CHANGED`, together with changed packages and
  `PAKET_UYGULA_HEP=1` packages. `reapply_modules` removes a marker only after `uygula`
  succeeded, or when the package is not installed (Konsol's `kur` places the current rendered
  files). It also removes the built-ins' markers, because `yerlesik` ran earlier in stage 7
  and stops the install if it fails. A failing `uygula` stays a warning, as before, and
  keeps the marker, so the next run tries again. A marker that cannot be written stops the
  install.
- **Why not `/run`:** `RUNTIME_DIR` is tmpfs; a reboot between the failed and the next run
  would drop the marker and bring the bug back. Why not compare rendered and placed files:
  only the hooks know where each file goes, and the engine stays application-neutral.
  `MODULES_DIR` cannot hold it either: the renderer deletes anything that is not a package
  file.
- **Bounds:** markers stand only for "rendered, not yet applied". They are not a reconcile
  queue. Nothing else reads them, no timer runs, and a marker for a package that was
  removed from the repository is never read. An extra re-apply is harmless (`uygula` is
  idempotent); a missed one is the bug. Hosts that missed a reapply before v2-200 are not
  detected (no migration); run `master-modul uygula <id>` once there.
- **Not covered:** `PANEL_HELPERS_CHANGED` (Konsol backend restart in stage 6) and
  `FIREWALL_NEEDS_RESTART` are in-memory signals of the same kind. They are outside this
  decision.

### DD-221: The Podman page changes qBittorrent's peer port (v2-199)

- **Request (user, 2026-10-05):** "portların boş olduğunu denetleyen sisteme gerek yok. eş portunu
  Podman sayfasından değiştirme imkânı eklenebilir." Asked how the ports are chosen (fixed numbers in
  `torrent.env`, no decision mechanism), the user declined an install-time free-port search and asked
  for the peer port to be editable like the interface port.
- **Decision:** the package adapter declares `peer_port` next to `listener_port` and `save` (`config`
  and `editable`); the base page shows the field only for an adapter that declares it and still names
  no application. A request without `peer_port` keeps the current one.
- **What moves together** (one transaction under the settings lock: stop → write → daemon-reload →
  guard → start → interface answers; any failure restores every file, reloads, reapplies the guard and
  only then restores the previous service state): both WAN `PublishPort` lines (TCP and UDP) and the image's
  `TORRENTING_PORT` in the rendered and the placed Quadlet, the profile's `Session\Port`, and
  `TORRENT_PEER_PORT` in the durable override (now in `PAKET_AYAR_ANAHTARLAR`), so the installer renders
  the same values and the hook's `podman port` check, Settings' port catalogue and the container guard
  agree. The guard (`master_container_network.py apply`) runs before the start: it reads the placed
  Quadlet, so the new publication is let through and the old one no longer. The main Quadlet is
  patched, not a drop-in: Quadlet merges `PublishPort` lists from drop-ins, and the patched file is
  exactly what the installer writes from the override (the DD-214/DD-217 pattern). `TORRENTING_PORT`
  is patched in the same `Environment=` line, so each value has one place.
- **Checks (the edit's own, before the service stops):** an integer 1024–65535, different from the
  interface port, not another project service's port (base `*_PORT` values, other packages' declared
  ports, saved Konsol container definitions over TCP or UDP), and bindable on the WAN address over
  TCP and UDP (catches a WireGuard network's UDP port or another container's publication). No
  install-time free-port search exists or was added (the user's call). The form recommends
  61000–65535 (outside the ephemeral range, DD-219) but does not enforce it.
- **Consistency:** only a changed peer port is recorded (DD-219's rule) and `kaldir --veri` keeps it
  like the interface port (DD-220). The App Store text no longer names the number, which is rendered at
  install time and would go stale after an edit; the Podman page and Settings show the effective port.
  The Quadlet's comment lines no longer repeat port numbers for the same reason.
- **Limits:** existing peer connections drop with the restart; trackers and the DHT learn the new port
  on the next announce. qBittorrent's own listening-port option is overwritten by `TORRENTING_PORT` at
  every start, so the port is changed here, not in its UI.

### DD-220: Removing qBittorrent with its data keeps Konsol's port and image choice (v2-198)

- **Request (user, 2026-10-05):** "öneriyi çalış ve düzeltelim" — the follow-up a multi-agent review
  of v2-197 found and filed as a separate task.
- **Problem:** the package's durable choices (`PAKET_AYAR_ANAHTARLAR`: `TORRENT_UI_PORT` from the
  Podman page, `TORRENT_IMAGE` from an approved update, DD-214) are baked into rendered files by the
  installer: the Quadlet's `PublishPort` loopback line, `WEBUI_PORT` and `Image=`, the manifest's
  `PAKET_IMAJ`, the seed's `WebUI\Port`. `kaldir --veri` deleted the override (and the port drop-in
  `85-konteyner.conf`) but no one re-rendered those files, so a reinstall from App Store before the
  next installer run placed a Quadlet on the chosen port while the hook, Caddy's filter
  (`master_publications.private_site`, override-aware) and the publication expected the package
  default: `torrent_verify` failed and `torrent.<domain>` pointed at the wrong port.
- **Decision:** `--veri` deletes what its dialog names — the profile, the torrent list, the folder
  drop-in and the image — and keeps Konsol's choices: the override and the port drop-in. Every consumer
  then agrees again (rendered files, hook, Caddy filter, publication). The dialog says so. Rejected:
  rewriting the rendered lines back to defaults on `--veri` (a second renderer outside the installer,
  and it would silently downgrade an approved image to the package's older pinned digest).
- **Consequence:** a reinstall after `--veri` uses the chosen port and re-pulls the approved image
  digest. A recorded choice wins over the package's `torrent.env` on every render (`paket_ayar_oku`,
  DD-203/DD-214), so a newer package's `TORRENT_IMAGE` pin or default port does not reach an install
  that has one: the image moves only by another approved update (to the channel's digest), and
  entering the default port on the Podman page records that value as a choice too. There is no
  in-product way back to following the package's values; the manual step is to delete
  `PACKAGE_OVERRIDES_DIR/torrent.env` and `qbittorrent.container.d/85-konteyner.conf` as root and run
  the installer (found by the v2-198 review: the first draft of this entry wrongly promised that a
  newer package version restores the pin).
- Supersedes DD-214's sentence "`kaldir --veri` drops the override with the other package settings".

### DD-219: qBittorrent back to its own defaults; its ports moved to uncommon fixed ports (v2-197)

- **Request (user, 2026-10-04):** "ayar değişikliğini iptal edelim image dosyası varsayılan config
  ayarları ile kurulsun değişikliği geri alalım. arayüz portunu ve peer portlarını değiştirelim. wan
  arayüzden internete açılan portları random taramalardan uzak portlar olarak güncelleyelim." Asked
  to choose, the user picked qBittorrent's own defaults (not the image's `/defaults/qBittorrent.conf`,
  whose `/downloads` paths do not match the same-path mounts; its only other difference is UPnP off),
  kept SSH on 22, left the share HTTP (61010), WireGuard (61001) and Tailscale (41641) ports alone
  ("aralık uzak zaten"), and chose fixed uncommon ports over per-install random ones.
- **Revert:** DD-218 (v2-196) is retired; the seed is again the six integration keys of DD-178 with
  DD-217's `WebUI\Address=*`. A profile seeded by v2-196 keeps its values (fresh-install rule; nrm's
  live profile never received them).
- **Ports:** `TORRENT_UI_PORT=62947` (published on loopback only) and `TORRENT_PEER_PORT=63851` (TCP+UDP
  on the WAN IPv4 address). Both are outside Linux's ephemeral range (32768–60999, so an outgoing
  connection can never hold them first), away from the 610xx block of the other services, and not a
  commonly scanned or registered service port. Everything that names them renders from the package's
  `torrent.env`: Quadlet `PublishPort`/`WEBUI_PORT`/`TORRENTING_PORT`, Caddy upstream, publication
  upstream, the Settings port catalogue, the guard and the hook's checks.
- **Honest limits:** an uncommon port only keeps opportunistic scans of common ports away; full-range
  scanners still find an open TCP port. The peer port is announced to every tracker and peer by
  design, so it cannot be hidden from the swarm. 443 stays (Let's Encrypt TLS-ALPN needs it); UDP
  WireGuard/Tailscale ports do not answer unauthenticated probes.
- **Existing installs:** an installer run re-renders the package and recreates the container on the
  new ports; qBittorrent takes both from its start flags. An operator override of `TORRENT_UI_PORT`
  (Podman page) keeps its value. Before v2-197 every Podman-page save of qBittorrent, even a
  folder-only one, recorded the port shown at the time as such an override, so such an install stays
  on 61006 (loopback only); the manual step is to enter the new port there. Since v2-197 only a
  changed port is recorded.
- **Review fixes (multi-agent review, v2-197):** the App Store text claimed "İnternete eş portu
  açılmaz" since DD-217; it now states the rendered peer port and that it is WAN IPv4 only. Settings'
  port catalogue showed the peer port as an IPv4+IPv6 INPUT permission with a toggle that cannot
  affect a forwarded container publication; package internet ports of a bridge package are now IPv4
  rows marked fixed (no toggle). Stale "host network / outgoing only" statements in the contract
  (R10/R12/R18, §3.1), README, architecture, defaults.env and the Cursor rules were corrected.

### DD-217: qBittorrent on its own bridge; ports published per address in its Quadlet (v2-195)

- **Request (user, 2026-10-04):** the Podman page showed many qBittorrent ports on every address
  (DD-215): "hangileri gerekli ise sadece onu açalım. arayüz erişimi, peer yayın portu açmamız
  yeterli. tüm yüzeylerde peer yayın portu açılması gerekli olmayabilir. quadlet dosyasında port
  açılmasını yüzey bazında kısıtlama yapabilir miyiz". Asked to choose, the user opened the peer
  port to the internet and chose a bridge network with Quadlet `PublishPort` over the recommended
  host network plus qBittorrent's own binding and the firewall.
- **What was found (nrm):** on the host network qBittorrent listened on every address (its peer
  port on WAN, Tailscale and loopback, LSD 6771/udp, UPnP/NAT-PMP sockets), but the WAN INPUT chain
  dropped all of them; the tailnet accepted everything. With `Network=host` Quadlet cannot restrict
  anything: Podman ignores published ports there.
- **Decision:** the container joins its own bridge `torrent` (`PAKET_KONTEYNER_AG`, generic engine
  key) and the quadlet publishes exactly `127.0.0.1:TORRENT_UI_PORT/tcp` and
  `WAN_IPV4:TORRENT_PEER_PORT` over TCP and UDP (`TORRENT_PEER_PORT=61008`, fixed through the image's
  `TORRENTING_PORT`). Inside the bridge the interface listens on the container's address
  (`WebUI\Address=*`, written by the seed template and the install for fresh and kept profiles);
  only the loopback publication reaches it. LSD/UPnP keep their defaults (DD-178): their sockets stay
  inside the container and nothing is published for them.
- **Why the guard changes:** Netavark DNATs a publication into the bridge, so the packet takes the
  forward path, not INPUT. The bridge is named with the guard's prefix, so the existing default drop
  covers it from the first second; `package_publications()` reads registered packages' placed
  quadlets and lets through only their WAN/Tailscale IPv4 publications (an unparseable or foreign
  address, or a placed quadlet on another network, is simply not let through; found live: an
  installer run renders the new manifest at stage 4 but places the new quadlet at stage 7, and
  refusing the mismatch stopped the firewall at stage 5). The engine refreshes
  the guard after placing and removing the quadlet; `master-firewall` refreshes it at boot before
  containers start.
- **Port moves:** a Quadlet drop-in cannot replace `PublishPort` (lists merge), so a Podman-page
  interface port change patches the single loopback line in the rendered and the placed quadlet,
  like DD-214's image line; the durable override makes the next render identical.
- **Trade-offs, stated:** NAT on the peer path; no IPv6 peers (the managed bridges are IPv4-only and
  the guard opens no IPv6); the WAN address is baked in at render time, so a changed WAN address
  needs an installer run; the peer port is internet-facing (libtorrent's listener).
- **Amended (v2-197, DD-219):** the interface port is 62947 and the peer port 63851 (were 61006 and 61008).
- **Existing installs:** fresh-install rule; a profile written by earlier versions carries
  `WebUI\Address=127.0.0.1` and the interface would not answer on the bridge. The manual step is
  reinstalling qBittorrent from App Store (the install writes `*`), or setting that key to `*` while
  the app is stopped.
- **Amended (v2-201, DD-223):** `After=master-firewall.service` did not hold the start back when the
  firewall failed. The package Quadlet now also checks the guard in `ExecStartPre` and retries
  every 10 s until it is in place.

### DD-216: Applications open from Ana Menü only; the container page is named Podman (v2-194)

- **Request (user, 2026-10-04):** remove the sidebar's "Kurulu uygulamalar" group: WireGuard and
  qBittorrent must not appear in the sidebar after installation; an application is opened from its
  Ana Menü icon, and a package that gets a home icon gets no sidebar hook. Same request: rename the
  Konteynerler page in the sidebar to Podman.
- **Navigation:** every installed package already has a home tile (DD-212), whose link opens the
  native interface while the app runs and its Konsol page otherwise (DD-210), and whose actions hold
  start/stop, settings and logs. The sidebar entry only duplicated that link, so the shell builds no
  application link at all: `paintNav()`, the `installed-label` span and its styles are gone. Package
  pages are unchanged (DD-200): created from `konsol.json`, reached at `#/<rota>` from the tile, the
  App Store "Aç" and bookmarks. While one is open, Ana Menü stays marked as the current section.
- **Podman page:** the sidebar entry, page title and the detail page's way back read "Podman"; the
  list's eyebrow says "Konteynerler · bu sunucu" and the resource tab keeps "Konteynerler". The route
  stays `#/konteynerler`, so bookmarks and the Settings redirect keep working. The installer summary
  points to "Konsol → Podman".
- **Cold load (fix):** an App Store row's name and icon come from the module catalogue. When the
  container list answered first, the row showed the internal package id ("torrent") until the next
  ten-second refresh. The page now repaints when the catalogue arrives (no extra list read), and
  before that it shows the container's own name, never the package id.

### DD-215: The Podman page shows the ports a host-network container listens on (v2-194)

- **Request (user, 2026-10-04):** the Access column showed only "Sunucu ağı (host)" for qBittorrent;
  show the ports the container opens (for example the peer port and the interface port) as ip:port.
- **Why not Podman:** a host-network container has no port mappings, so `podman ps`/`inspect` know no
  ports. The ports are the sockets its processes hold. `master_containers.listening()` takes the
  container's init PID (`State.Pid`), the processes of its own cgroup v2 subtree (never the root
  cgroup: then only the init process), their socket fds, and matches them against
  `/proc/<pid>/net/{tcp,tcp6,udp,udp6}` of that network namespace: TCP in LISTEN and unconnected bound
  UDP. IPv4-mapped addresses read as IPv4, IPv6 link-local binds are left out, duplicates collapse. No
  `ss`, no new tool, no podman call; it runs only for running host-network containers on each list or
  detail read (about 5 ms for qBittorrent on nrm, inside a replica of the backend's sandbox).
- **Honest labels:** each socket carries the kind of address it is bound to: all addresses, the
  server's WAN or Tailscale address (from the installer's state, then the tailnet ranges), another
  address, or loopback ("Yalnız bu sunucu"). This is not reachability: on the host network the
  firewall decides, and the detail says so. Unreadable processes or tables give `null` (unknown),
  never an empty "no ports".
- **Display:** the list shows one line per port with its widest address (IPv4 first), the protocols
  and the address kinds, at most three ports and "+N port daha"; the detail's "Ağ ve portlar" lists
  every address. Published bridge ports keep their mapping lines unchanged.
- **Not done:** no firewall evaluation, no process names, no per-port labels from packages.
- **Amended (v2-195, DD-217):** qBittorrent left the host network; the reader remains for any other
  host-network container.

### DD-214: Konsol checks image updates, the operator applies them; row controls before the name (v2-193)

- **Request (user, 2026-10-04):** after the explanation of Podman, Quadlet files and digest pins, the
  user chose the "approved update" model for qBittorrent: "konsol güncelleme olup olmadığını
  denetlesin kullanıcı isterse güncellesin". Same request: on the Konteynerler page put start/stop and
  edit right before the container name, keep remove at the end, and use icons that suit the theme.
- **Check, never apply:** `master_containers.update_status()` compares the installed digest with what a
  channel tag points to now using `podman manifest inspect` (manifests only, no layer download): a
  multi-arch index by this host's platform manifest digest, a single manifest by its config digest
  (the local image id). It runs inside the backend's sandbox (verified on nrm with a replica of the
  unit's hardening). App Store packages name their channel with `PAKET_IMAJ_KANAL`; a Konsol
  definition's channel is its tag reference; digest references are `sabit`. `Service.updates()` caches
  the answers for six hours, forced checks are limited to one a minute, and a successful image-changing
  operation empties the cache. The page asks on open and on the operator's button only; there is no
  timer, no `AutoUpdate=`, no `podman-auto-update.timer`, and the browser never sees a pull target.
- **Apply on request (App Store):** `image-update` is offered when a package declares both a channel and
  a container adapter. qBittorrent's adapter (`ayar.py konteyner-guncelle`) re-checks under the settings
  lock, validates the files that name the image, then pulls the exact digest the check saw, rewrites the
  single `Image=` line of the rendered and the placed Quadlet and the `PAKET_IMAJ` line of the rendered
  manifest, records `TORRENT_IMAGE` as the package's durable override (`PAKET_AYAR_ANAHTARLAR`), restarts a
  running app, waits for its interface and checks the container's `ImageName`. Any failure restores every
  file and the previous service; the previous image is removed (by id, never forced) only after success.
- **Why patch files instead of a drop-in:** live check on nrm (Podman 5.4.2): a Quadlet drop-in's
  `Image=` is ignored (the generator keeps the main file's value), while multi-valued keys such as
  `Volume=`/`Environment=` merge. Patching exactly the image line keeps the Quadlet the readable truth
  about what runs, and the override makes the installer's next render produce the same bytes, so the
  engine's placement never reverts the update. A stopped app only gets the rendered files; its next
  start uses them. `kaldir --veri` drops the override with the other package settings (superseded by
  DD-220, v2-198: `--veri` keeps the override and the port drop-in).
- **Row controls:** start/stop and edit move into the name cell, before the application icon and name;
  remove stays in the last column (DD-213's fixed slots and capabilities unchanged). The icons and their
  bare style are the home tiles' own (`.tile-act`): play/pause, the settings sliders, trash; colour only
  on hover, remove turns to the danger colour. Keyboard order follows: start/stop, edit, name, the
  "Güncelleme var" chip when present, remove.
- **Not done:** no update for external or Compose/pod containers, no image signature verification, no
  automatic or scheduled update, no rollback after a successful update other than updating again.

### DD-213: Compact Ana Menü, five-second refresh and direct container actions (v2-192)

- **Request (2026-10-04):** refine the installed v191 presentation without changing
  the underlying service configuration or control authority.
- **Space:** six desktop widget slots; network spans two. At narrower widths the grid
  becomes four, then two slots. The network chart and borderless totals table retain
  fixed, equal-height areas and internal scrolling. Saved network widths normalize
  to two; visibility and application order keep the existing layout schema.
- **Applications:** home cards are approximately 16% narrower at desktop sizes, with
  the same 193 px normal height and 44 px action targets. Bare icons are ordered
  start/stop → settings → logs; unsupported slots stay blank. Store cards show no
  subtitle; full descriptions remain in Details.
- **Header and updates:** Ana Menü labels the sidebar entry; the compatible route
  remains `#/genel`. Clock/date replace its heading and no longer appear in the
  sidebar. Home has one five-second resources/modules/network tick, no manual Refresh
  and no overlapping ten-second home tick. Other pages retain ten-second polling;
  hidden tabs pause periodic reads and active installation progress keeps its own poll.
- **Containers:** name only, status/resources/access and three icon controls ordered
  start/stop → edit → remove. Remove the owner column and overflow menu from the list.
  Ownership still controls permissions, unsupported actions remain disabled, and
  details retain image information and additional operations. Existing confirmation,
  package lifecycle, stopped-save behavior and data-retention semantics are unchanged.
- **Scope:** frontend presentation only; cumulative traffic sources, authentication,
  firewall and backend APIs are unchanged. Local browser and source checks are recorded
  in `SESSION.md`; the portable installer is exported in the repo, not deployed.

### DD-212: Installed application home tiles and one fixed network widget (v2-191)

Presentation amended by DD-213; installed-only tiles and cumulative traffic semantics remain.

- **Request (2026-10-04):** simplify the overview to installed applications and the
  network widget. Dosyalar, Ayarlar and App Store keep their sidebar navigation;
  Paylaşımlar remains a tab inside Dosyalar, not a separate sidebar entry. None has a
  duplicate home card. This changes the overview composition from DD-204 and DD-206
  and extends the DD-210 action row.
- **Stable action positions:** every installed application has three bare-icon slots
  in this order: settings, start/stop, logs. Unsupported slots remain blank and
  non-interactive, so other actions do not move; WireGuard's start/stop slot is empty.
  Keep accessible labels/tooltips, focus, existing settings forms and lifecycle
  confirmation/progress. Logs open a dialog through the existing module journal.
- **Sidebar context:** move clock/date below CPU, memory and disk; retain WAN and
  Tailscale addresses, version and uptime there. Remove the separate home clock/system
  widgets and their unused SVG/CSS. Resource information remains available without
  repeating it in home widgets.
- **Layout compatibility:** `ag` is the only widget, always full width (four columns).
  Keep hide/show, tile reordering and the existing server layout API/schema and safe
  writer. The frontend ignores removed saved widget/tile IDs and normalizes any older
  `ag` width to 4 while retaining its visibility. There is no server data migration
  or per-device layout; new installed tiles follow the saved order as before. On phones
  the edit toolbar stays in normal flow below the tiles, preventing a short viewport
  from covering a card; the desktop toolbar retains its sticky behavior.
- **Network presentation:** equal-width and equal-height sections place live server
  download/upload rates and chart beside a borderless three-column application table:
  icon/name, cumulative download total, cumulative upload total. The table has a
  fixed-height overflow area so more applications do not stretch the widget.
- **Measurement meaning:** the user's clarified contract keeps application `down`/`up`
  counters as cumulative totals formatted in byte units, never bytes/s. Only the server
  rates/chart section shows live speeds. Missing, non-finite or stale measurements stay
  unknown rather than zero, without suppressing other rows or server measurements.
  Existing backend traffic sources and authentication stay unchanged: no new rate
  module or additional qBittorrent login. qBittorrent's existing all-time totals can
  lag between its statistics-file saves; they are not live measurements.
- **Delivery and evidence:** source and repository portable installers are v2-191.
  Per the user's clarified workflow, every version change rebuilds the root and
  `Data/app` installers for the version commit, without a Desktop copy or separate
  snapshot. Local validation is recorded in `SESSION.md`; no live acceptance is claimed.

### DD-211: Main-sidebar container management with explicit ownership (v2-190)

- **Amended (v2-194, DD-216):** the sidebar entry and page title read "Podman"; the route stays
  `#/konteynerler`. Host-network containers show their listening sockets (DD-215).

- **Request (2026-10-03):** move Containers out of Settings and implement the accepted
  Portainer-like prototype: lifecycle, editable ports/mounts and real resource management.
  The frozen proposal is `docs/design/konsol-konteynerler-v01.html`; corrected semantics
  and the implementation interface are recorded alongside it.
- **Ownership:** App Store applications retain `master-modul` and package-owned settings.
  Generic containers created/adopted in Konsol have private persisted definitions and
  `konsol-<name>.container` Quadlets. Unmanaged standalone containers have explicit
  lifecycle controls and an adoption preview. Compose/pod/systemd-controlled or unsupported
  definitions are never silently converted. The worker rechecks ownership under locks.
- **Writes:** the root socket backend brokers a fixed set of actions to a transient root
  systemd unit with a 900-second runtime bound. HTTP 202 means accepted, not successful.
  Private operation records expose progress and terminal success/failure, including an
  interrupted worker. Install/module/container locks serialize mutations; stale revisions
  refuse overwrite. Reads stay in the existing backend sandbox.
- **Persistence:** validate image, network, mounts and generated unit before stopping the
  old container. Images resolve to immutable digests. Explicit save/update can recreate;
  a failed replacement attempts configuration/runtime rollback and reports failure.
  This does not roll application data back. Stopped saves stay stopped; manual stop
  suppresses boot startup independently of the configured autostart preference. Secret
  environment values stay in 0600 files, with only presence returned by the API.
- **Networking:** Netavark retains NAT. A separate `inet` nftables forward guard at
  priority -10 covers only managed bridge interfaces. Local/Tailscale/public mappings
  are explicit; public access requires acknowledgement. Original DNAT destination and
  host port are checked, direct ingress and IPv6 are denied, and an established inbound
  flow does not bypass a newly revoked scope. Foreign tables/chains remain untouched.
  Aardvark DNS is an explicit dependency: managed bridge TCP/UDP 53 can reach only
  that bridge's own host address, including after the project firewall is reapplied.
  Existing tailnet address events mark a bounded refresh job; only changed Tailscale
  bindings are rerendered, stopped state is retained. There is no new timer/reconciler.
- **Data/resources:** container removal keeps volumes and bind data. Volume deletion is
  a separate unused-resource operation; custom volume drivers/options cannot bypass
  bind-path restrictions. Generic host binds are confined to real user folders under
  `SERVER_ROOT`, excluding protected package/share/trash paths. Managed bridge creation
  checks explicit subnet overlaps; runtime sockets, host networking and raw Podman flags
  are not part of the editor. In-use resources and package-pinned images are protected.
- **Package settings:** manifests may declare a container adapter and allowlisted durable
  overrides. qBittorrent's one listener port drives its profile, Quadlet drop-in, Caddy
  upstream, health/publication checks and installer rendering. Its existing account form
  remains the account owner. Required mounts are shown as protected in the generic editor.
  DD-221 (v2-199) adds the peer port: both WAN publications, `TORRENTING_PORT`, the profile's
  `Session\Port`, the container guard and installer rendering follow the same kind of override.
- **Scope:** one host/rootful Podman, no Docker daemon, shell console, Compose editor,
  cluster scheduler or automatic image updates. DD-208 still owns Podman base installation;
  its former read-only Settings placement is superseded by this decision.
- **Verification:** tests and live evidence are recorded in `SESSION.md`; the mockup is
  design evidence only, not proof of runtime or OS compatibility.
- **Amended (v2-205, DD-227):** writable server folders need the Files account (no capabilities);
  a root image gets volumes or read-only folders only.
- **Amended (v2-204, DD-226):** bind sources are walked and pinned at every start; the Quadlet
  mounts the anchor, and a missing or symlinked folder keeps the container down.
- **Amended (v2-201, DD-223):** generated units no longer carry `Requires=master-firewall.service`,
  so a firewall restart leaves running containers alone. Their `ExecStartPre` only checks the guard
  that the locked writers apply.

### DD-210: App Store install form, direct app launch and the tile action row (v2-187…v2-189)

- **Request (user via the project lead, 2026-10-03):** qBittorrent's App Store "Kur" opens a window
  asking for a username, a password and the download folder, and the install uses them; afterwards the
  application's icon on the main menu opens qBittorrent's own web UI, and a small settings icon beneath
  it changes the same three values.
- **Why the install takes the values (instead of the temporary password, DD-151):** with a password
  chosen up front there is no temporary-password step and no window in which the web UI runs with a
  journal password. A "temporary default, patch later" install was rejected: the container would start
  once with credentials the operator did not choose, and a failed patch would leave it that way.
- **Generic, two declarations:** `konsol.json` `form` (generic field types `metin`, `parola`, `klasor`,
  texts, the package API's read and write routes) drives the shell's dialogs; the manifest key
  `PAKET_KUR_AYAR` names the worker that validates the form. The shell, the backend and the engine name
  no application. A package without `PAKET_KUR_AYAR` (WireGuard) installs exactly as before and refuses
  a form.
- **Validation before anything starts:** the backend, under one lock per install, refuses a busy or
  installed package, runs the package worker as a transient root unit with the form on stdin
  (`kur-hazirla`; the same `run_worker` path as every settings write, so the password never reaches
  argv, environment or journal) and spawns `master-modul kur` only after the worker accepted. The worker
  reuses the package's own rules: username pattern, password 8–256 printable characters, the base's
  `safe_dir(writable=True)` user-area policy probed as the downloads user, and the same-path bind-mount
  character check. A refusal is the request's 400; no image is pulled and nothing is written.
- **Seed, not a password, crosses into the engine:** the engine runs detached (`systemd-run`, DD-148), so
  stdin cannot reach it. The worker writes `RUNTIME_DIR/modul-<id>.kur` (tmpfs, 0600, root) with the
  validated username, folder and the password **already hashed** in qBittorrent's PBKDF2 format; no
  plaintext is ever stored. The engine refuses to install such a package without a fresh (≤10 min),
  private, root-owned seed, exposes its path to the hooks as `KUR_TOHUM` and removes it and the hook's
  snapshot on every exit; the backend removes it when the engine could not be started.
- **Before the first start, and reversible:** the hook writes the seed into the new or kept profile
  (`kur-uygula`: only `WebUI\Username`, `WebUI\Password_PBKDF2` and the two save-path keys, plus the
  folder drop-in when outside the downloads tree) after `torrent_profile` and before the quadlet and the
  first `systemctl start`; the image's init copies its defaults only when no profile exists, so the
  values hold. The files as they were are snapshotted next to the seed; every failure path of `kur`
  (`torrent_kur_geri`) stops and removes the unit, then restores the profile and the drop-in
  (`kur-geri`), so a failed reinstall never loses the previous working account, folder, unrelated
  preferences or torrents.
- **Edit:** `POST /api/uygulama/torrent/ayar` takes any of the three fields; the worker validates all of
  them first and makes one stop/write/start (`change()`, DD-165 direct apply with rollback), keeping a
  stopped app stopped. A blank password is simply not sent and the stored hash stays. The dialog reads
  current values from `/durum`, which never carries the hash.
- **Launch:** an app with publication names (`urls`, DD-195/199) opens its web UI in a new tab
  (`noopener noreferrer`) from the tile, the sidebar entry (removed by DD-216) and App Store's "Aç" while it runs — the
  public name on the public HTTPS address, the tailnet name on the tailnet. Stopped, busy or (on the
  public address) unpublished apps open their Konsol page instead; no name is constructed in the page
  and the public address never falls back to a private one. The page remains reachable from App Store
  details and its route, and it keeps its own forms.
- **Stopped apps keep their settings (review fix):** the tile keeps the settings action while the app is
  stopped, so the root backend hands a stopped (`durduruldu`) package's own `/api/uygulama/<id>/*`
  requests to its API module too (`package_api(..., stopped=True)`). For that object `start()` is not run,
  and background callers (`package_apis()`: the sampler, VPN networks) never get it; a state change
  rebuilds the object (stopping a running one). Absent packages still answer 404/409. The qBittorrent page
  reads its status while stopped for the same reason.
- **Dialog ownership (review fix):** the form shares Konsol's one dialog with every other flow. Each call
  puts its content under its own root node and owns the dialog only while that node is the content and
  the dialog has not closed since. A late install or save answer then closes only its own dialog (else it
  only toasts), a late refusal toasts instead of writing into another dialog, and a late settings read
  never replaces a newer dialog; closing still clears the call's password fields and returns focus.
- **Tile action row (v2-188, user: "ana ekran uygulamalarının altında ayarlar, durdur başlat iki seçenek
  olsun"):** v2-187's single settings icon became a compact row beneath the icon of every installed
  App Store application: **Ayarlar** (the declared form; without one, a link to the package's page, so
  WireGuard gets its page) and, only for packages that declare `PAKET_DURDURULABILIR=1`, one
  **Durdur/Başlat** button. WireGuard cannot stop as a whole (its networks switch one by one) and gets no
  invented all-networks switch; built-in navigation tiles get no row. The tile is a container with a
  stretched launch link and the row as a sibling (no nested interactive elements). Durdur asks the App
  Store's own confirmation (`askStop`, the package's stop note); both actions use the same lifecycle
  request and progress (`modStart`), so no backend change. From the click until the server's operation
  ends the button is `aria-disabled` (still focusable, so keyboard focus survives the 1.5 s progress
  redraws) and ignores clicks; its visible label is the short "Duruyor…"/"Başlıyor…" (the narrow tile),
  its accessible name "<app>: Durduruluyor…/Başlatılıyor…". A refused request is a toast and the button
  is usable again; the label follows the server's state when the operation ends. **v2-189** (user: "fon
  rengi olmadan sadece simge"): the controls are bare icons — no visible text, background or border, also
  on hover/press; the name is the `aria-label` and the `title` tooltip, the focus ring stays, the touch area
  is an invisible 44 px pseudo-element. The redraw at the end of a lifecycle request keeps whatever has focus
  by then instead of pulling it back to the tile. Edit mode renders the
  tiles exactly as before (no row, no link). A poll that redraws the tiles keeps keyboard focus on the same
  tile part (`data-act`), and closing the settings dialog returns focus to Ayarlar.

### DD-209: qBittorrent runs as a Podman container: quadlet, digest-pinned image, host network (v2-186)

- **Request (user, 2026-10-03):** "sunucuda podman üzerinden yüklü qbittorrent ama ekranda ve app
  store içerisinde uygulama gibi görülmesi daha iyi olur" — after the Podman trial
  (DD-208) and having removed the native qBittorrent from Konsol themselves, the qBittorrent that
  runs in Podman should be *the* qBittorrent application. An earlier message had already named
  qBittorrent as the one application worth moving into a container.
- **Decision:** one App Store application `torrent`, now a container. No second "qBittorrent
  (container)" entry: two would collide on the UI port, the Caddy name `torrent.<domain>`, the
  publication row, the page route and the downloads folder. The Debian package `qbittorrent-nox`
  is no longer installed (fresh-install rule: an old enabled `qbittorrent-nox@` unit stops the
  install with the manual `systemctl disable --now …` step instead of a migration).
- **Engine (generic, no application name):** `PAKET_CALISMA=konteyner` (Konsol shows a
  "Konteyner" chip; liveness is the unit's, like `host`); `PAKET_KONTEYNER` names the package's
  quadlet file, placed into `KONTEYNER_BIRIM_DIR` (`/etc/containers/systemd`, from
  `defaults.env`/state) with a `daemon-reload` when it changed, removed on `kaldir`, checked by
  the engine's and the installer's leftover checks and pruned for uninstalled packages like a
  drop-in; `PAKET_IMAJ` is the image, accepted only as `name@sha256:<64 hex>`;
  `paket_imaj_cek` pulls it only when `podman image exists` says no (bounded by `timeout 900`),
  `paket_imaj_sil` removes it by image id (`podman rmi NAME@sha256:…` answers "tag not known",
  found live) and leaves an image that another tag or container uses.
- **Quadlet (`magaza/torrent/qbittorrent.container`):** `Network=host` (no bridge, no
  netavark NAT chains: the firewall stays the project's), `Pull=never` (boots and re-runs never
  download), journald logging (`podman logs` and `journalctl -u` both work), `StopTimeout=45`,
  `DropCapability=NET_BIND_SERVICE SETFCAP SYS_CHROOT`, PUID/PGID = the downloads account,
  `UMASK=002`, `WEBUI_PORT=TORRENT_UI_PORT`, `[Service] Nice=10 CPUWeight=50` (DD-181),
  `After=master-firewall.service`, `[Install] WantedBy=multi-user.target`. Two mounts only: the
  profile `TORRENT_PROFILE_DIR` as `/config` (the image's layout `/config/qBittorrent/` equals the
  native XDG layout, so `ayar.py`, `yayin.py`, `klasorler.py`, `trafik.py` read the same paths) and
  `DOWNLOADS_PATH` **at the same path**, so every path qBittorrent stores is a host path (Files'
  protected folders, share validation and `save_inside` keep working). The trash and the share
  root are simply absent inside. The image is the linuxserver build pinned by its OCI index
  digest (amd64 + arm64) in the package's own `torrent.env` (`TORRENT_IMAGE`; `TORRENT_SURUM`
  only for the App Store text); an update is a new digest plus an installer run (the changed
  quadlet recreates the container). No `AutoUpdate=` and no `podman-auto-update.timer`.
  Amended by DD-214: Konsol checks the channel and the operator may apply a newer digest.
  Amended by DD-217 (v2-195): the container runs on its own bridge with per-address publications,
  not on the host network.
- **Live findings that shaped it (nrm, 2026-10-03):** with `NoNewPrivileges=true` the image's s6
  init ignored SIGTERM and was SIGKILLed after the stop timeout (30–45 s instead of 3 s, the unit
  left "failed" — qBittorrent writes settings and resume data on shutdown), so the quadlet
  carries no `NoNewPrivileges` and the hook resets a failed unit when it stops it. The seeded
  `WebUI\Address=127.0.0.1` survives the image's init (it copies its defaults only when no
  `qBittorrent.conf` exists), so the profile seed must precede the first start. The unit is
  `active` before qBittorrent listens, so the worker waits (≤40 s) for the loopback port before a
  change counts. Journal lines of the container carry the unit's `_SYSTEMD_INVOCATION_ID`, so the
  first-login password is read exactly as before.
- **Lifecycle:** a generated unit cannot be enabled or disabled; `durdur` stops it and removes the
  quadlet (nothing starts at boot), `baslat` places it again, an installer run keeps a stopped app
  stopped. `kaldir` keeps the image (as a kept Debian package was); `--veri` deletes the profile,
  the folder drop-in and the image. Verification on `kur`/`baslat`/`uygula`: the
  `qbittorrent-nox` process's host uid (`podman top … huid`) is `DOWNLOADS_UID`; no mount is `/`,
  `SERVER_ROOT`, the trash or the share root; the UI port listens on `127.0.0.1` only; first
  install still requires the unauthenticated 403 on loopback and through `torrent.<domain>`.
- **Folder choice:** a download folder inside the downloads tree needs nothing; one outside it
  (the library) becomes one quadlet drop-in `qbittorrent.container.d/90-konsol.conf` with a
  same-path `Volume=` (Podman merges drop-ins), replacing the old `ReadWritePaths` drop-in.
  Names with whitespace, `:` or `%` cannot be expressed as a bind mount and are refused.
- **Trade-offs, stated:** memory ~100 MB for the service cgroup versus ~53 MB native; a 228 MB
  image (pulled once, ~1 min); the container's init runs as root inside its namespaces (the app
  itself as PUID), weaker than the native unit's `ProtectSystem=strict` + `NoNewPrivileges`, but
  the container sees only its two mounts. Updates no longer come from apt; they are a digest
  bump in the repository. Not done: rootless/user-namespace mapping, image signature checks,
  automatic updates, a container log view on the app's own page (it links to Settings →
  Konteynerler instead).

### DD-208: Podman is base infrastructure; Settings → Konteynerler is its read-only view (v2-185, v2-186)

- **Request (user, 2026-10-02):** after setting the "iOS-like store" restructuring aside
  ("amacımız stabilite"), the user asked to try qBittorrent as a container beside the native
  one and, on the assistant's comparison, chose Podman over Docker ("öneriyi kabul ediyorum");
  the trial on nrm (quadlet unit, host network, PUID 1000) left the firewall rule set untouched,
  needed no daemon and survived a reboot (SESSION.md, 2026-10-02). Then: "podman da çalışan
  konteyner'ı panelden görebileceğimiz bir yapı … kabaca kontainer durumu, mount dosyaları,
  portlar ve log görmek istiyorum sadece". v2-185 first shipped this as an App Store package
  (`magaza/podman/`, never committed). On 2026-10-03 the user corrected it: "podman bir platform
  sonuçta ayrı bir uygulama gibi görülmesin … app store tarafından kullanılabilen bir taban
  yapı olarak birlikte kurulsun".
- **Decision (v2-186):** Podman is part of the base. Stage 1 installs `podman netavark` without
  recommends (no buildah, criu, slirp4netns, passt or uidmap: host-network rootful containers
  need none; `netavark` is named because Ubuntu noble's podman does not depend on it) and dies
  unless `podman info` answers; stage 7 checks it again and the summary prints its version. No
  daemon: Debian ships `podman.socket`, `podman.service` and `podman-auto-update.timer`
  disabled and the installer never enables them. The App Store catalogue is the applications
  only; container applications use the runtime (DD-209).
- **The view:** Settings → **Konteynerler** (a sixth tab; the sidebar's "installed applications"
  stays for applications). `panel/master_containers.py` maps `podman ps/inspect/images/system
  df/logs` for `GET /api/konsol/konteynerler/{liste,ayrinti,gunluk}` (shared Konsol gates, no
  write route at all); `console/konteynerler.js`/`.css` render every container on the host with
  state, image, unit, mounts, ports and a masked log tail (100–1000 lines, in-place refresh that
  keeps the scroll). The tab's DOM node is persistent across Settings redraws, does not load
  the settings document, and opens a named container from `#/ayarlar/konteynerler/<name>` —
  the link an application page uses for its own container.
- **Safety of the read path:** the reads run inside `master-panel`'s sandbox (verified on nrm:
  `ProtectSystem=full`, `RestrictNamespaces`, `NoNewPrivileges` do not block them), container
  names are validated, `Config.Env` is never returned (images carry passwords there) and
  `password|parola|passwd|secret|token|api key|private key … : value` is masked in log lines
  before they leave the server. Nothing here starts, stops or removes a container: that belongs
  to the application that owns it.
- **Why base and not a package:** a runtime is not something an operator "uses"; applications
  depend on it, and the engine has no dependency key. As a package it would also have needed a
  removal refusal ("remove the containers first") and a store-wide `podman system reset` for
  `--veri`, both wrong once applications run in it. DD-152 holds: no Docker, no daemon, no
  iptables churn (host network only).
- **Amended (v2-190, v2-195):** the read-only Settings tab became the main-sidebar Podman page
  with brokered writes (DD-211, DD-216). Stage 1 installs `podman netavark aardvark-dns`.
  Containers no longer use the host network only: Konsol's managed bridges (DD-211) and a
  package's own bridge (DD-217) run with Netavark-owned NAT, a project-owned `inet` forward
  guard and a MASTER-INPUT exception for each bridge's own DNS. The project never edits
  Netavark's or Tailscale's rules.

### DD-207: A package's backend write paths exist before the backend starts (v2-184)

- **Report (user, 2026-10-02):** creating the first WireGuard network from Konsol failed with
  "install: cannot change permissions of '/etc/wireguard/clients-wg0': No such file or
  directory". Reproduced on nrm inside the root backend's mount namespace: `/etc/wireguard`
  was read-only there (`mkdir` → EROFS) while writable on the host.
- **Cause.** DD-203 renders `ReadWritePaths=-/etc/wireguard` into `master-panel.service`; systemd
  binds such a path writable only if it exists when the service starts and silently skips it
  otherwise (the `-`). On a host where WireGuard was never installed, `/etc/wireguard` appears
  only when the App Store installs the package (its hook, or `wireguard-tools`), after the
  backend started, so the backend keeps seeing it through the read-only `/etc` until it
  restarts. The same happens when the folder is removed while the backend runs (the kernel
  detaches the bind) and created again — on nrm the assistant's test cleanup purged
  `wireguard-tools`, which removed the empty folder, and the operator's reinstall surfaced it.
  The v2-177 live test passed only because `/etc/wireguard` already existed when the backend
  started.
- **Fix.** (1) The installer creates every catalogued declared path (0700 root) before it
  (re)starts the backend, so a fresh host binds `/etc/wireguard` from the start; while
  WireGuard is not installed the folder is empty. (2) The installer also restarts a running
  backend whose `/proc/<pid>/mountinfo` lacks a writable mount at a declared path, so a re-run
  repairs a host in that state. (3) The store engine runs the same check after `kur`, `baslat`
  and `uygula` and restarts the backend once when needed (only in the removed-and-recreated
  case); Konsol keeps following a running operation quietly through that brief restart instead
  of dropping it after one failed poll. (4) `master-wg` checks that its folder is writable
  before any writing command and otherwise says so in Turkish with the remedy.
- **Rejected:** running every `master-wg` call through a transient unit outside the backend's
  sandbox (latency on every peer action and a larger change), and a per-install drop-in with an
  unconditional backend restart (DD-203's reason still holds).
- **UI in the same version:** the new-network screen became one card as wide as the windows
  (560 px: label and port side by side, the DNS picker, the outcome lines, the buttons) instead
  of three cards and a summary column; DNS options take two lines (name and badge, then
  description · addresses), so the network settings, peer add and peer edit windows show the
  whole list without an inner scroll; the network settings window has one hint instead of two.

### DD-206: Overview edit mode, a server-side layout and a network card (v2-183)

- **Request (user, 2026-10-02):** "ana ekrana sol alta bir düzenle seçeneği ekleyelim … uygulama
  simgelerinin yerini değiştirebilelim ve widgetlarda boyut ayarlaması yapabilelim", then, on the
  assistant's plan: width only ("yükseklik sabit"), a show/hide switch, the clock card without
  version details (time, date, uptime, Tailscale and WAN addresses), and a network card with the
  server's download/upload every 1–2 s plus WireGuard's and qBittorrent's totals in one card.
- **Edit mode.** A "Düzenle" pill bottom-left, below the tiles and sticky to the bottom of the
  screen on a long page (a fixed pill covered the last row's controls on a short page — seen in the
  live look; sticky rests below the tiles at the end), opens a draft: tiles wiggle and become non-link groups with ‹ › buttons, and can be dragged with
  pointer events (one path for mouse and touch; listeners sit on the document because moving the
  dragged tile in the DOM drops pointer capture — found by the browser test). Widgets get − / +
  (1–4 of four columns) and Gizle/Göster; a hidden widget stays visible, dimmed, while editing.
  "Bitti" saves, "Vazgeç"/Escape/leaving the page drops the draft, "Varsayılan" returns to the
  defaults (a draft equal to the defaults deletes the record). Data refreshes do not redraw while
  editing; numbers keep updating in place. Reduced motion stops the wiggle. The tiles (and
  Düzenle) wait for the module list's first answer, so installed applications do not jump in
  after the page and a draft never misses them.
- **Layout on the server, not in the browser:** the same overview on every device. The root
  backend stores `KONSOL_AUTH_DIR/duzen.json` through the account store's safe writer (0600,
  atomic, no-follow, its lock), checks only the shape — keys, counts, width 1–4, boolean
  visibility — and leaves meaning to the shell, so the backend names no tile or widget. A damaged
  record falls back to the defaults. Widgets keep a fixed order (clock, status, network); only
  tiles are reordered. Grid: four columns (two below 1100 px, one below 480 px), the row sets the
  height; charts shrink inside a one-column card (container queries).
- **Network card.** Server rates come from the WAN interface's sysfs counters: the background
  sampler adds a point every 10 s and each `/api/konsol/ag` request one more when 1.5 s passed,
  so the card's 2-s polling gives live rates and the chart has the last 120 s at once; no command
  runs. Applications report through a new optional manifest key, `PAKET_TRAFIK` (a module in the
  package folder exposing `trafik(env) → {down, up, since}`, loaded like `yayin.py`/`klasorler.py`
  and cached 2 s), so the shell and the backend still name no application. Direction is as the
  application's users see it. qBittorrent: its own all-time totals (AlltimeDL/AlltimeUL), read
  from `qBittorrent-data.conf` ([Stats] AllStats, a QVariantHash that QSettings streams in the Qt
  4.0 format behind INI escapes) with the file's time as `at` — no login, no command; qBittorrent
  writes the file every few minutes while transferring and when it stops, so the figure can lag
  by that much and the card says when it was saved. WireGuard: the bytes its interfaces sent to
  (down) and received from (up) the peers, `since` the earliest running network's unit start.
- **Rejected on the live host — systemd IP accounting.** The first version counted qBittorrent's
  unit with `IPAccounting=yes`. On nrm (Debian 13, systemd 257) every `daemon-reload` dropped the
  counters of units loaded from disk ("[no data]" until the service restarts; transient units kept
  theirs), and installer runs, package installs and apt all reload systemd, so the card showed
  "ölçülemedi" most of the time. qBittorrent's API would give live all-time figures but needs its
  login, and a localhost bypass would open it to every local client behind Caddy.
- **Clock card:** time, date, uptime, Tailscale and WAN IPv4; host, OS and kernel stay in
  Ayarlar → Sistem.
- **Not done:** widget reordering, per-device layouts, all-time application totals, per-peer or
  per-network breakdown in the card.

### DD-205: No sign-in on the tailnet; the account is the public name's credential (v2-181)

- **Request (user, 2026-10-02):** "Panel girişinde eğer tailscale adı ile panel erişimi varsa
  parola sormadan açabilelim. ama https arayüzden erişim olursa kullanıcı adı ve parola ile
  erişim sağlayalım. kullanıcı ilk kullanımı tailscale arayüz ile yapar ve https arayüz
  kullanıcı adı ve şifresini oluşturur sonra giriş yapabilir olsun" — accepted with the
  assistant's recommendation: passwordless tailnet, the account made in Settings, no setup
  code, tailnet password change without the current one.
- **Trade-off (flagged):** every device in the tailnet is a full administrator without a
  password — a shared node, another tailnet user or an unlocked phone included. DD-194 was
  added one day earlier against exactly that; the user now prefers the convenience on the
  tailnet and keeps the password for the public name. Tailscale ACLs remain the only limit
  on who reaches `panel.<domain>`; the installer does not touch them.
- **The channel decides:** Caddy still asks the root backend before every protected request
  (`forward_auth`); the backend answers by the channel Caddy wrote (`X-Konsol-Kanal`,
  DD-195). `tailscale`: 204 without a cookie — `gate()` has already required another
  Tailscale device (DD-180), so host-local programs still cannot reach Konsol or the Files
  API through Caddy — and `/giris.html` gets 302 to `/`. `internet`, and a caller without
  Caddy's forwarding headers: a `konsol_oturum` session as before; only `/giris.html` is
  open without one. The sign-in page therefore moved behind `forward_auth` (its files and
  the sign-in API stay open in Caddy), which is what lets the backend redirect it on the
  tailnet.
- **Account = public credential:** the one-time setup code is gone (file, CLI verb,
  installer printout, sign-in form). `POST /api/konsol/oturum/kur` takes only user name and
  password, is refused over the internet (403) and opens no session; Settings → Sistem →
  Konsol hesabı offers it on the tailnet while no account exists. The Panel's internet switch
  (DD-195) keeps requiring an existing account, so the public site cannot open before the
  operator chose a password. `GET /api/konsol/oturum` tells the account name to the tailnet
  without a session (`reveal`), never to an anonymous internet visitor, and names the
  channel; the page shows the sign-out and the current-password field only on the public
  name and never guesses the channel from the URL.
- **Password change:** on the public name as before (current password, this session stays,
  the others end). On the tailnet `{yeni}` alone: the device is the credential, no session
  is needed and every session ends (`Store.set_password`). This replaces the SSH reset as
  the recovery path; `sudo master-konsol sifirla` still deletes the account and closes the
  public name, and `durum`, `oturum-ac`, `oturum-kapat` stay for state and scripted checks.
- **Budgets:** unchanged for the public name (per address and shared). `kur` and the tailnet
  password change check no secret, so they only use the bounded hash slots; the audit journal
  records them as `hesap-kur` and `parola-degis` with the device's address.
- **Not done:** no per-device identity on the tailnet (`tailscale whois`), no roles, no
  second factor for the public name, no account deletion in the UI.

### DD-204: CasaOS-inspired skin and an overview page for Konsol (v2-178)

- **Scope (user, 2026-10-02: "casaos yapısına internetten bak … panel yapısını tema olarak
  casaos temasına uydurabilir miyiz", then "tasarım çok güzel olmuş uygulayalım" on the
  frozen mockup `docs/design/konsol-casa-v01.html`):** Konsol takes the look of CasaOS — a
  wallpaper behind translucent, blurred ("glass") surfaces, rounded application tiles with
  big tinted icons, an overview with widgets — while keeping its own navigation model.
  CasaOS (studied from casaos.zimaspace.com, the `CasaOS-UI` Vue source and its published
  screenshots; the public demo needs a login the assistant does not enter) is a single
  launcher page: a top bar with account/settings/terminal menus, a widget column, a search
  box and an icon grid; Files and the App Store open as modals. Konsol has deep pages (five
  Settings tabs, package pages), so the sidebar stays and the launcher idea becomes a new
  landing page. This is option C of the analysis: A (theme) plus tiles and an overview.
- **Theme (CSS only, `panel.css`).** The Model A override sheet now carries the palette
  (blue-teal accent, blue-grey neutrals, light and dark), the glass tokens (`--glass`,
  `--glass-2`, `--glass-line`, `--glass-shadow`, `--blur`, `--radius`) and the wallpaper
  colours (`--sky1/2`, `--m1…4`). `index.html` paints the wallpaper with a fixed `.wall`
  (gradient + inline SVG ridges, `fill="url(#…)"` as an attribute) behind a transparent body;
  no external asset, so the CSP (`img-src 'self'`, `style-src 'self'`) is untouched. Sidebar,
  cards, tables, dialogs, rails and store entries are glass; buttons are pills.
  `prefers-reduced-transparency` and engines without `backdrop-filter` get opaque surfaces
  and no wallpaper. The Files panel is translucent without blur on purpose: a
  `backdrop-filter` there would become the containing block of the fixed selection dock
  (found by `files-ui.cjs`). Eyebrows stay untransformed (Model A).
- **Overview (`genel`, the landing page).** A shell route like Dosyalar/App Store/Ayarlar:
  two widgets — clock with host/OS/kernel/uptime, and system status with CPU/RAM rings, a
  storage pie (used share of the data disk, warn colour from 90 %) and the health checks'
  pill (v2-178 also had a storage card with the disk bar and a CPU-history sparkline; the
  user dropped both in v2-179 — the sidebar already carries the figures; v2-182 removed the
  health-check lines from the card and enlarged the three charts to fill it, the pill alone
  carries the verdict and Ayarlar → Sistem → Sağlık has the texts) — and the tiles: Dosyalar, every installed application (name,
  icon and tone from its `konsol.json`, state as text and dot, link to its page), Paylaşımlar,
  App Store (installed/installable counts) and Ayarlar. Everything comes from the existing
  endpoints (`kaynaklar`, `saglik`, `/api/state`, `paylasim`, `moduller`); the page computes
  nothing and polls only while shown. SVG rings and the pie are built from templates like
  the icons (no namespace URL literal, no inline style). An unknown route opens the overview;
  DD-160 made Dosyalar the landing page and Model A removed the old overview — this brings a
  smaller, data-driven one back by the user's choice.
- **App Store as tiles.** The rows keep their markup, ids, buttons, progress lines and the
  details panel (`panel-ui.cjs` still drives them); only CSS lays them out as tiles with the
  same icon shape as the overview. The compact-row height check became a tile check.
- **Not done, deliberately:** no theme/wallpaper switch in production (the mockup's demo
  controls were for evaluation; the system colour scheme decides), no operator wallpaper
  upload (needs a backend and storage), no CasaOS artwork or icons.

### DD-203: Package-declared folders, settings and backend write paths, phase 3 (v2-177)

- **Scope (user, 2026-10-02: "Faz 3 tamamla, kalan kozmetik temizliği de yap"):** the crumbs
  DD-202 left in the base and every remaining application name in base code and comments.
  After this phase the base — installer, `defaults.env`, `state.env`, root backend,
  settings/share/WebDAV helpers, file backend, Konsol shell, unit templates — carries no
  application name or key; adding an application means writing `Data/magaza/<id>/` only.
- **Declared folders (`PAKET_KLASORLER`, `PAKET_KLASOR_MODUL`).** A package declares, as
  absolute paths the installer renders, the folders it writes into
  (`__DOWNLOADS_PATH__/incomplete`: qBittorrent's conventional incomplete folder) and,
  optionally, a Python module (`klasorler.py`, `yazilan(env) → [paths]`) that reports what
  it writes into right now (the temporary folder the user chose in qBittorrent itself, read
  from its profile). The base applies one policy to both: the file backend receives every
  catalogued package's declared folders as root-relative `path=owner` pairs (`--protected`,
  `/api/state.protected`), so the Files page refuses to select, share or trash them and
  says which application writes there; the share manager refuses a share on, inside or
  around them (`validate_path`: declared + reported, fail closed when a report cannot be
  read); the WebDAV server hides and refuses them inside any share that contains them (the
  registry's `protected` list, root-relative, recomputed by `read()` from the catalogue and
  the reports instead of trusted from the saved file). Protection is by actual path, not by
  folder name as before: a folder merely named `incomplete` elsewhere is ordinary.
  `TORRENT_TEMP_DIR`, `temp_name`, `--temp-dir` and the base's reader of qBittorrent's
  profile are gone.
- **Package settings (`<id>.env`).** `magaza/torrent/torrent.env` holds `TORRENT_UI_PORT`
  and `TORRENT_PROFILE_DIR`, as `wireguard.env` holds the `WG_*` keys (DD-201). The
  installer fills a package's own `__KEY__` placeholders from its env file before its own
  variables (`paket_ayar_oku`), so the templates, `PAKET_YAYIN_UPSTREAM` and
  `PAKET_KLASORLER` render without base keys; `defaults.env`/`state.env` carry no
  `TORRENT_*`. The hook sources the file; `api.py`, `ayar.py`, `yayin.py` and
  `klasorler.py` merge it over the state (`package_env`). A `PAKET_PORTLAR` key resolves
  from the state or, failing that, from the package's own env file (root backend `ports()`,
  `master-wg declared_ports`), keeping DD-198's key semantics.
- **Backend write paths (`PAKET_ARKAUC_YOLLAR`).** `master-panel.service` no longer names
  `/etc/wireguard`: the installer renders `ReadWritePaths` from every catalogued manifest's
  declaration (`__WG_CONF_DIR__` for WireGuard), each with `-` so an absent folder never
  keeps the backend down, installed or not — the same catalogue-wide rule as the port
  reservation (DD-201), chosen over a per-install drop-in because that would restart the
  backend the Konsol is talking to in the middle of an install. **Amended by DD-207:** a
  `-` path is bound only if it exists when the backend starts; the installer now creates
  them first.
- **One package-module loader.** `master_settings.load_package_module(env, mid, name,
  attr, label)` replaces the publication-only loader of DD-199: regular file, no symlink,
  mtime cache, `sys.dont_write_bytecode` while executing — the `__pycache__` the base used
  to write into the rendered package folder (found on nrm) is gone. `yayin.py`
  (`security`) and `klasorler.py` (`yazilan`) both load through it.
- **Cosmetics.** The installer's summaries list the catalogue's `PAKET_AD` names
  (`paket_katalog_adlar`), stale WAN sites are removed by the `*-wan.caddy` pattern, the
  Files page's protected-folder notice names the owner the backend reports, the Settings
  port descriptions and the public-panel warning name no application, and base comments
  describe roles ("a package's service", "the download account's services") instead of
  products. Historical DD entries and archived documents keep their names.
- **Fresh install only**, like the rest of the store model (DD-196); an in-place host gets
  the new unit lines, state and package files on the next installer run.

### DD-202: The qBittorrent page and its settings in the package, phase 2c (v2-176)

- **Scope (user, 2026-10-02: "Öneri ile devam" on the phase 2c recommendation):** the last
  application piece leaves the base. The qBittorrent page (service bar, first-login card,
  account and download-folder form) is the package's `sayfa.js`/`sayfa.css`, registered
  through `window.Konsol.sayfa` like WireGuard's; its reads and writes go to the package's
  `api.py` behind `/api/uygulama/torrent/*`; the base settings transaction
  (`master_settings.py`, `ayarlar.js`) has no `torrent` family, no application tab and no
  application draft. The shell, the settings page, `index.html` and the root backend contain
  no qBittorrent code.
- **Option chosen (A, direct apply through a package worker)** over keeping the
  account/folder change inside the base's reviewed transaction. That transaction exists for
  changes that can lock the operator out (firewall, DNS, domain) and so needs the
  confirmation window; a wrong qBittorrent account or folder locks nobody out of Konsol,
  and the account-only path already committed directly (**DD-165**). The folder change
  therefore loses the 60 s confirmation it had; in exchange the base knows nothing about
  the application. A generic "package settings" family inside the base transaction (option
  B) would have kept application knowledge in the base and was not taken.
- **Worker.** `magaza/torrent/ayar.py` (`--state STATE hesap|dizin|durum`, JSON on stdin,
  JSON on stdout, exit 1 with `{"error"}`): validation (username `[A-Za-z0-9._@-]{1,64}`,
  password 8–256 printable characters; the folder through the base's
  `Manager.safe_dir(writable=True)`, so the downloads/library policy and the write probe as
  the service user stay the base's), then stop → snapshot → optional drop-in +
  `daemon-reload` → INI patch of the touched keys only (0640, downloads uid) → start →
  `is-active`; any failure restores both files, reloads systemd and starts the service
  again. The drop-in is `UNIT_DIR/qbittorrent-nox@.service.d/90-konsol.conf` with one
  `ReadWritePaths` line. The worker takes the base settings lock (`Manager.locked()`), so it
  never interleaves with a base transaction. `durum` is the page's read-only view: paths,
  inside-downloads flags, interface, peer port and account name; never the hash.
- **Backend.** `PackageContext.worker(argv, data)` runs a script that must sit under
  `MODULES_DIR/<id>/` (real path; a symlink out of the folder is refused with 400) through
  the same `systemd-run --wait --pipe --collect` path as the base settings/share workers
  (`run_worker`), so a password reaches stdin only, never argv, the environment, the journal
  or the reply; `PackageContext.state_path()` hands the state file to the worker, and the
  module passes the engine's folder as `--lib` so the standalone process finds the base's
  `master_settings.py` (a hand run finds `master-modul` on `PATH`; found live, the first run
  answered 502 because the worker could not import the base). `api.py`
  checks shapes before starting the worker (400), audits `torrent:hesap` with `kullanıcı
  adı`/`parola` and `torrent:dizin` with the path, and returns the worker's error as the
  request's error. `torrent_view`, `TORRENT_KEYS` and `read_torrent_conf` are gone from
  `master-panel`; `GET /api/konsol/ayarlar` carries no `torrent` key and `manage` no
  `username`/`save`.
- **Settings transaction.** Families are firewall, dns, domain, https and web.
  `ini_values`, `ini_patch`, `password_hash`, `q_unit`, `torrent_apply` and the account-only
  shortcut left `master_settings.py`; the package's publication check `yayin.py`
  (**DD-199**) carries its own `ini_values`. A mixed DNS request needs confirmation only
  together with firewall or domain.
- **Shell.** `PAGE_API` gained `credRow`, `copyButton`, `copyText`, `module(id)`, `modPill`,
  `modAct(id, action)` and `reloadModules()`, so a package page can show an account card and
  drive its own service through Konsol's module API; `loadModules` calls the current page's
  `modules()` hook. The page keeps the DD-151/DD-195 behaviour: the temporary password is
  read only on request, shown for 30 s, hidden on tab change or navigation; the Web UI link
  follows the Konsol address in use.
- **Remaining base knowledge, left for a later step on purpose:** `master_shares.py` still
  reads the qBittorrent profile for the incomplete-folder guard of folder shares, the Files
  page still names qBittorrent next to the downloads temp folder, and
  `TORRENT_PROFILE_DIR`/`TORRENT_UI_PORT`/`TORRENT_TEMP_DIR` are still base defaults.
  Moving them needs a package declaration for "folders a package writes to" (done in
  **DD-203**).
- **Hooks.** The package's `paket_kur` places the page (`paket_sayfa_koy`) after the service
  and its name are verified and before the registry line, `paket_uygula` places it on every
  re-run, and the rollback removes it; found live on nrm, where the first v2-176 run left
  `CONSOLE_WEB_DIR/uygulama/torrent` absent because only WireGuard's hooks called the helper.
  The engine's `kaldir` removes the folder for every package (DD-200).
- **Fresh install only**, like the rest of the store model; an in-place host gets the new
  package files on the next installer run (`master-modul uygula`).

### DD-201: A neutral backend, package-owned settings and self-checking packages, phase 2b (v2-175)

- **Scope (user, 2026-10-02: "faz 2b ye başla"):** the second half of phase 2 of the store
  model (DD-196). After it the base names no application in its code, state or defaults:
  the root backend and its socket are renamed, WireGuard's settings live in its package,
  stage 7 asks installed packages to verify themselves, and the launcher and the peer tool
  know other packages only through their manifests. The qBittorrent page and its Settings
  form are the one remaining application piece in the shell (phase 2c, with the settings
  transaction they use).
- **Rename.** `master-wg-panel` → `master-panel` (file, unit, journal unit, `HEALTH_UNITS`,
  `server_version`), `WG_PANEL_SOCKET` → `PANEL_SOCKET` = `/run/master-panel/api.sock`,
  `WG_PANEL_RUNTIME` → `PANEL_RUNTIME`, `ensure_wg_panel` → `ensure_panel`. A fresh-install
  change like the rest of the store model; historical entries and archived documents keep
  the old names.
- **Package-owned settings.** `Data/magaza/wireguard/wireguard.env` holds every `WG_*`
  default (address bases, MTU, client DNS/keepalive/AllowedIPs defaults, config and
  profile directories, the network registry path and slot limit, the modules-load file,
  the suggested first port). The installer copies it into the rendered package folder like
  any other package file; `master-wg`, the hooks (`kanca`, sourced wherever
  `MODULES_DIR` is known: engine, firewall, installer) and the Konsol API module
  (`ctx.read_env`) read it there. `defaults.env` and `state.env` carry no `WG_*` key any
  more; the VPN endpoint is the detected `WAN_IPV4` (no `WG_ENDPOINT_HOST`), and the
  destination block lists the firewall applies to every `vpn` declaration are the base's
  own vocabulary, `VPN_BLOCK_DEST4/6`. The Mac launcher reads the peer-prompt defaults
  from the package file. `master_settings.py` no longer hashes the network registry into
  its revision: a package's own state changes go through its API.
- **Self-checking packages.** Stage 7 runs, for every registered package, the hook
  `paket_denetle` (sourced in a subshell with the installer's variables; a failure prints
  its reason and stops the install under the package's name) and, for every absent
  package, checks that none of its declared tools or drop-ins remain; the re-run prune
  removes such leftovers from the manifests instead of naming WireGuard. The summary takes
  each installed package's note from `paket_not` and its counts from `paket_ozet`, which
  now computes them itself. WireGuard's `paket_denetle` carries the former stage-7 block:
  `master-wg version`, the modules-load file, each registry network's listen port and
  address, and that the file backend does not answer on a VPN address.
- **Reserved ports.** `master-wg net-add` reserves the base ports (SSH, Tailscale, DNS,
  HTTP) and every `PAKET_PORTLAR` key of every package manifest in `MODULES_DIR`,
  installed or not, instead of naming qBittorrent, Files and WebDAV.
- **Still in the shell (phase 2c):** the qBittorrent page (`ROUTES.torrent`,
  `renderTorrentStatus`, the account card) and the Settings form (`torrent` key of the
  settings transaction in `master_settings.py`, `ayarlar.js`).

### DD-200: Konsol pages and application API from packages, phase 2a (v2-174)

- **Scope (user, 2026-10-01: "faz 2 ye başla"):** the first half of phase 2 of the store
  model (DD-196): Konsol's App Store texts, an installed application's page and its
  root-backend API come from the package. The base shell and the root backend no
  longer contain the word WireGuard. The second half (phase 2b) renames the backend and
  socket (`master-wg-panel` → a neutral name), moves the `WG_*` state keys and the
  qBittorrent page/settings form into their package, and fixes the launcher text and
  `master-wg`'s port-collision list. Each phase is a fresh-install change.
- **Declaration.** Three optional manifest keys: `PAKET_KONSOL="konsol.json"` (App
  Store texts, the page declaration `sayfa {rota, baslik, ustbilgi, detay}` and the
  journal templates `gunluk {verb: "…{detail}…{0}…"}`; a JSON object rendered by the
  installer, so `__LOCAL_DOMAIN__`-style placeholders are filled), `PAKET_SAYFA="sayfa.js
  sayfa.css"` (the page files) and `PAKET_API="api.py"` (the backend module). Names are
  plain file names; folder paths and other extensions are refused.
- **Page files.** `master-modul` copies the declared page files to
  `CONSOLE_WEB_DIR/uygulama/<id>/` on `kur`/`uygula` (`paket_sayfa_koy`, 0644 root) and
  removes the folder on `kaldir`; the trace check fails a removal that leaves it. Caddy
  serves them like the shell's own files, behind the same session gate and CSP
  (`script-src 'self'`). The installer removes an `uygulama/<id>/` folder whose package
  is not registered. Konsol loads `/uygulama/<id>/<file>` only for an installed package
  whose listing carries `sayfa`; the script registers with `window.Konsol.sayfa(id,
  factory)` and receives a small, frozen API (`h`, `svg`, `api`, `post`, `ask`, the
  shared dialog, the clock, the current route and a header repaint). The shell creates
  the section and the sidebar link (removed by DD-216) from `konsol.json`, keeps a bookmark of an
  application until the module list arrives, sends a bookmark of an absent application
  to App Store and unmounts the page when the package is removed; a package that is
  removed and reinstalled is mounted again from the already loaded factory.
- **API module.** The root backend loads `MODULES_DIR/<id>/<PAKET_API>` with importlib
  only while the package is registered `calisiyor` (regular file, cached by mtime; a
  changed file is reloaded, a removed package's object is stopped). `/api/uygulama/<id>/*`
  passes the existing Host, CSRF, channel and session gates first and is then handed to
  `module.create(ctx).handle(request)`. The module sees only `ctx` (state.env, its own
  tool beside `master-modul`, a subprocess runner with the backend's environment, the
  read-only port catalogue, `error(code, text)`, a settings-cache reset and a journal
  line) and the request (method, sub-path, query, JSON body, actor, `audit(verb, detail,
  ok)`). Audit lines are `<id>:<verb>`; Konsol labels the event by the package and reads
  the sentence from the package's templates. A missing, broken or failing module answers
  404/409/502 for that package alone. An absent package: `409 <Ad> kurulu değil; Konsol →
  App Store'dan kurun` on POST, 404 on GET.
- **What the base still knows about VPNs.** Settings → Güvenlik Duvarı keeps its VPN
  category: the networks come from the package modules' `networks()` hook (validated
  fields, no keys), the tab is named after the first such package (`vpn_name`), the port
  rows carry a structural `vpn` flag instead of a name prefix, and the rule kind is `vpn`.
  The resources sampler also refreshes the package API list every 10 s so a package's own
  sampler (WireGuard's connected-peer window, DD-137) runs before any page asks.
- **Still base, by design for now (phase 2b):** the unit and socket names, the `WG_*`
  keys in `state.env` (`WG_CLIENT_DNS_DEFAULT`/`WG_CLIENT_KEEPALIVE_DEFAULT` joined them
  so the package reads its defaults from state instead of unit environment lines), the
  qBittorrent page and its Settings form, `master-wg`'s port-collision list and the
  launcher's intro text.

### DD-199: Publication rows from package declarations, phase 1b (v2-173)

- **Scope:** the last base piece that named an application: Settings → Caddy. The
  built-in WebDAV row and the Konsol row stay fixed (they belong to the base); every
  other row comes from a package manifest.
- **Declaration.** A package publishes by setting `PAKET_YAYIN=1`, `PAKET_YAYIN_AD`
  (row name), `PAKET_YAYIN_YEREL` (local name, `<local>.<domain>` on the tailnet),
  `PAKET_YAYIN_UPSTREAM` (must be `127.0.0.1:PORT`; a placeholder is filled by the
  installer) and optionally `PAKET_YAYIN_DENETIM`, a Python file inside the package
  folder with `security(env, name, probe)`. A manifest that declares publication
  without a loopback upstream produces no row at all: the catalogue never guesses an
  upstream, and no tunnel or arbitrary host can be declared.
- **Engine side.** `master_publications.packages(env)` reads the rendered manifests
  (shared `master_settings.read_manifests`, line pattern, never sourced) and builds
  the rows, the private 403 stubs, the generated `<id>-wan.caddy` sites (one name,
  TLS-ALPN, the loopback upstream, `Host`/`X-Forwarded-Host`/`X-Forwarded-For`
  headers) and the status messages from the declared name. The security module is
  loaded from the package folder as a regular file, cached by mtime; a missing,
  broken or failing module closes the row instead of exposing the app. Saved rows
  of a package that no longer ships stay in the file unused, and its leftover
  public site is removed at the next publish.
- **Consumers.** Settings transactions snapshot every module site, `https_apply`
  waits for the certificate only when the package is active, the share publisher
  signs its projection with the active publication names, the firewall helper opens
  TCP 443 while any publication is active, and Konsol's module listing carries each
  publishing package's tailnet and public addresses. qBittorrent's checks moved
  verbatim into `magaza/torrent/yayin.py`; nothing in the base names it any more.
- **Still base:** the WebDAV row's HTTPS machinery (`master_https`, `master_shares`)
  and the Konsol row (DD-195). Phase 2 moves Konsol's App Store texts and pages into
  packages and renames the backend.

### DD-198: Firewall, health and port catalogue from package declarations, phase 1b (v2-172)

- **Scope (user, 2026-10-01):** the second half of phase 1 of the store model
  (DD-196/197): the base derives firewall rules, health units and the port
  catalogue from what installed packages declare. Publication rows (Settings →
  Caddy) follow in the next version; Konsol metadata and the backend rename are
  phase 2.
- **Firewall.** Packages never write rules. `master-firewall` reads the registry
  and, for every package in state `calisiyor` whose `kanca` defines
  `paket_firewall`, sources the hook in a subshell and collects its output lines.
  The vocabulary is deliberately one word today: `vpn IFACE UDP_PORT NET4 NET6`,
  which means a WAN UDP endpoint, a tailnet permit for that port, internet-only
  forwarding (DD-177 destination blocks from `WG_BLOCK_DEST4/6`) and NAT for the
  subnets. Every line is validated against strict patterns, interfaces and ports
  must be unique across packages, and a malformed or unknown line stops the run
  before any chain changes, exactly as a corrupt registry did before. The
  WireGuard package's hook prints one `vpn` line per network of its own registry
  and a deliberately invalid line for a non-`inet` scope. `--check` recomputes
  expectations from the same declarations. The recovery guards keep the static
  `-i wg+ DROP`; a package cannot change recovery behaviour. No WAN TCP word
  exists: web interfaces reach the internet only through Caddy's publication port.
- **Health.** `master-modul saglik` prints `id<TAB>unit<TAB>gerekli|ag` for every
  installed package: `paket_saglik` when the hook defines it (WireGuard: one
  `wg-quick@wgN.service` per network, type `ag`, which may be disabled from
  Konsol), otherwise the unit from `paket_birim` as `gerekli`. A hook that finds
  a corrupt registry fails the call and the card says the package services could
  not be verified. The backend keeps its base units and its registry format check
  and no longer knows qBittorrent's or WireGuard's units.
- **Port catalogue.** `PAKET_PORTLAR="KEY:proto:scope:name;…"` in a manifest adds
  rows to Settings → Güvenlik Duvarı while the package is registered; `dosya` got
  a manifest (built-in) for its loopback row and `paylasim` declares the WebDAV
  port. The backend reads manifests with the engine's line pattern (never
  sourcing them) and skips a malformed manifest's rows instead of guessing. The
  base rows are only Tailscale, SSH, Caddy and dnsmasq.
- **Trust:** hooks run as root in the firewall and the engine, like `master-modul`
  did before DD-197; packages come only from this repository, and the firewall's
  validation treats their output as data.

### DD-197: The store engine and package format, phase 1a (v2-171)

- **Scope (user, 2026-10-01: "Faz 1'e başla"):** the first half of phase 1 of the
  store model (DD-196): the engine and the package format. The second half (phase
  1b) makes firewall, health, port catalogue and publication rows derive from
  package declarations; phase 2 renames the backend and loads Konsol pages from
  packages.
- **Package format.** A package is `Data/magaza/<id>/`, rendered by the installer to
  `MODULES_DIR/<id>/`. It holds:
  - `paket.env`, the manifest: `PAKET_AD`, `PAKET_SIRA` (catalogue order),
    `PAKET_CALISMA` (`host`/`konsol`), `PAKET_DURDURULABILIR`, `PAKET_HESAP`,
    `PAKET_APT` (Debian packages), `PAKET_ARACLAR` (files placed in `SBIN_DIR`
    0755), `PAKET_EKLER` (`source:unit.d/file` drop-ins placed under `UNIT_DIR`),
    `PAKET_ADLAR` (has `<id>.caddy` and `dnsmasq.conf` names), `PAKET_GUNLUK`
    (journal unit patterns), `PAKET_KUR_ADIM` (progress total), `PAKET_YAYIN`
    (registry changes republish Caddy), `PAKET_UYGULA_HEP`/`PAKET_UYGULA_NEDEN`
    (re-applied on every installer run, and why) and `PAKET_YERLESIK` (built-in:
    outside the catalogue, never removable). The engine reads it line by line
    with a strict pattern and never sources it.
  - `kanca`, the hooks: a bash file the engine sources, defining only `paket_*`
    functions: `paket_kur`, `paket_kaldir`, `paket_uygula STATE`, `paket_baslat`,
    `paket_durdur`, `paket_birim` (the unit name), `paket_hesap`, `paket_veri_sil`,
    `paket_gunluk_suz` (log filter) and `paket_ozet` (installer summary). Hooks run
    as root like the engine did before; packages come only from this repository.
  - Slot files: `<id>.caddy`, `dnsmasq.conf`, units, drop-ins, tools and seeds.
    Any file with `__KEY__` placeholders is a template filled from the installer's
    own variable of that name; a missing variable stops the install.
- **Engine.** `master-modul` knows no application: the catalogue is the set of
  rendered package folders with a manifest, ordered by `PAKET_SIRA`; `liste`,
  `kur`, `baslat`, `durdur`, `kaldir [--veri]`, `gunluk`, `hesap` and `uygula`
  keep their names, locks, progress file and output format. Apt packages, tools,
  drop-ins and names are placed and removed by engine helpers the hooks call in
  the order the package needs (`paket_apt`, `paket_araclar_koy`, `paket_ekler_koy`,
  `paket_adlar_ac`, their `kaldir`/`kapat` counterparts, `progress_step`,
  `registry_set`, `firewall_apply`). After `kaldir` the engine removes every
  declared artifact itself and fails the operation if any trace remains
  (`paket_iz_kontrol`), so a package cannot leave a tool, drop-in or name behind.
  Built-in Files and WebDAV keep their installer-only `yerlesik` path; `paylasim`
  carries a manifest with `PAKET_YERLESIK=1` so the renderer treats it like any
  package while the catalogue excludes it.
- **Installer.** `render_package_dir` renders or copies every file of every
  package folder (executables 0755); `ensure_module_files` marks a package for
  `uygula` when a file changed or the manifest says always. Summary lines take the
  name from the manifest and one line from the package's `paket_ozet` hook.
- **Unchanged for now:** Konsol's `MOD_META` texts and routes, the backend's
  `ACCOUNT_MODULES`/`PORT_MODULES`/health units and `master_publications`'
  module ids, the firewall's WireGuard registry logic, the `WG_*` state keys.
  Those are phase 1b and phase 2.

### DD-196: The store model, phase 0 (v2-170)

- **Request (user, 2026-10-01):** after a clean install without WireGuard, Konsol's log
  still showed "WireGuard" rows and errors. The user asked for a fully independent App
  Store: an app sets up everything it needs on install and takes it all away on removal,
  and for a structural "store" design. They approved the model below and the folder name
  `magaza`, and asked to start with phase 0.
- **Finding:** the rows were mislabelled base events. Konsol's log called every root-backend
  event that was not a module action "WireGuard" (sign-ins, settings, shares), and failed
  sign-ins became "WireGuard errors". Beyond that, the base owned real WireGuard pieces
  with the package absent: the `master-wg` tool and the `wg-quick@` drop-in were installed
  unconditionally, `/etc/wireguard` was created by the base, the root backend's unit was
  described as the "WireGuard backend", the installer probed it through `/api/wg/state`,
  the summary always printed "WireGuard: 0 ağ, 0 peer", Caddy's `--environ` dumped every
  `WG_*` variable of `state.env` into the journal, and the five-minute tailnet timer scanned
  for `wg-quick@` units.
- **Model (approved):** the base knows no app. A package is a folder under `Data/magaza/<id>/`
  that will carry a manifest, lifecycle hooks (`kur`, `kaldir`, `baslat`, `durdur`, `uygula`,
  `saglik`, `hesap`, `gunluk`, `firewall`) and slot files (`<id>.caddy`, `dnsmasq.conf`,
  units, `konsol.js`). One root engine runs the hooks, keeps the registry with each package's
  footprint and verifies that a removal leaves nothing behind. Firewall, health, port catalogue,
  publication rows and Konsol pages derive from installed packages' declarations, validated
  against a narrow vocabulary; packages never write rules themselves. The catalogue stays in
  this repository; no remote store, no third-party packages.
- **Phase 0 (this version):** the repo folder `modules/` became `magaza/`; `master-wg` and
  `wg-quick-master-stack.conf` moved into `magaza/wireguard/`. The installer only renders
  them into `MODULES_DIR/wireguard/`; `master-modul kur`/`uygula wireguard` place the tool
  and the drop-in, `kaldir` removes them (the key folder is data, removed with `--veri`),
  and a re-run removes a tool or drop-in left by an older base install when the package is
  absent. Stage 7 checks the tool only with the package and its absence without it, and
  probes the backend with `/api/konsol/kaynaklar`. The unit is "Konsol root backend"; Caddy
  starts without `--environ`; the tailnet timer and the module log route look at WireGuard
  only while it is installed; the summary and the confirmation screen name WireGuard only
  as a package. Konsol's log labels events by source (Konsol, Ayarlar, Paylaşımlar, Dosyalar,
  Uygulamalar, WireGuard) with words for sign-in, settings and share events, and offers filter
  chips only for kinds present.
- **Still base, by design for now:** `WG_*` keys in `state.env` and `defaults.env` (the
  firewall reads the network registry and block lists), the service and socket names
  `master-wg-panel`, the `/api/wg/*` route and the `wireguard_installed` gates. Phase 1 moves
  the hooks and declarations into the package folders and makes the firewall, health and port
  views manifest-driven; phase 2 renames the backend and API and loads Konsol pages from
  packages. Each phase is a fresh-install change; no compatibility code for earlier state.

### DD-195: Konsol over public HTTPS through the publication table (v2-167)

- **Amended by DD-205:** there is no setup code any more; account creation stays
  refused over the internet, and the tailnet site no longer asks for a sign-in.
- **Request (user, 2026-10-01):** after creating the first Konsol account, "panel
  sayfası için caddy adresini de https olarak açabilelim" — the Panel row of
  Settings → Caddy gets an internet switch and a public name like qBittorrent and
  WebDAV. The tailnet address stays the always-open management path.
- **Trade-off (flagged):** a public Konsol is full administration (firewall,
  WireGuard, files, App Store) behind one password and no second factor. The
  operator chooses it explicitly; the dialog asks for the typed word `onayla` and
  recommends a long, unique password. Tailscale-only stays the default.
- **One set of routes:** the panel site's routes move into the Caddy snippet
  `(konsol)`. `http://panel.<domain>` imports it as `tailscale`; the generated
  `moduller/panel-wan.caddy` (`https://<name>:SHARE_HTTPS_PORT`, bound to the WAN
  IPv4, TLS-ALPN, HSTS one year) imports it as `internet`. Both therefore have the
  same `forward_auth` session check, sign-in exceptions, CSP and backends; there is
  no other upstream. Backends always see `Host: panel.<domain>` (a local-domain
  change rewrites those lines too), so their DNS-rebinding checks are unchanged.
- **Channel, written only by Caddy:** the snippet sets `X-Konsol-Kanal` on
  `forward_auth` and the root backend route, overwriting anything a client sent.
  The root backend keeps DD-180 for `tailscale` (the client must be another
  tailnet device). For `internet` it requires an active publication (re-read at
  most every 5 s: enabled row, assigned global WAN IPv4, existing Konsol account)
  and a client that is not one of the server's own addresses. A request without
  the mark from a non-tailnet address is refused as before. Timed Settings
  confirmations also require the `tailscale` channel, not only a 100.64.0.0/10
  address (that range is carrier NAT space too), and the domain-change check
  reads the browser's real name from Caddy's `X-Forwarded-Host`, because `Host`
  is now pinned.
- **Load from the internet:** every public request costs one `forward_auth`
  round trip to the single Python root backend, and HTTP/2 lets one connection
  carry many requests. Each site therefore opens at most 16 connections to the
  backend (`max_conns_per_host`, session check and root API separately), and the
  unit raises `LimitNOFILE`: with exhausted descriptors the own-address probe
  fails closed and would have refused Tailscale too. Scanners can still keep the
  public sign-in locked (20 failures per 15 minutes); that is the accepted cost.
- **Sign-in over the internet:** the one-time setup code is refused (403); the
  first account is created only on the tailnet address, and enabling the row
  requires an existing account. The session cookie gets `Secure` whenever Caddy
  reports HTTPS. Failures over the internet also count in one shared budget:
  20 within 600 s close public sign-in for 900 s (429 + Retry-After) while
  Tailscale sign-in stays open; existing sessions keep working. Each address may
  run one password check at a time and at most two scrypt checks (16 MiB each)
  run at once, because one HTTP/2 connection can carry many requests.
- **Publication lifecycle:** a Settings transaction like qBittorrent's: DNS check
  before mutation, listener check, certificate wait, rollback on failure. The
  row's Tailscale switch is fixed on. Turning the internet on, or changing the
  public name, carries `confirm: onayla`, which the server checks as well as the
  page. Like qBittorrent it shares TCP 443 and the WebDAV socket budgets and
  cannot run beside folders shared over legacy WebDAV HTTP right now (v2-169: the
  live listener, not WebDAV's mode; the page says so before the dialog).
  The 30 s share guard re-runs the projection outside a pending Settings
  transaction, so a reset account (`master-konsol sifirla`) or a lost WAN address
  removes the public site and, if nothing else needs it, closes TCP 443; the
  backend refuses within 5 s before that.
- **Unchanged:** Settings changes that need a timed confirmation (firewall, local
  domain) are still confirmed only from a Tailscale address, so a public session
  cannot make them permanent. No Tunnel, no DNS writes, no IPv6 listener.
- **Amendment (v2-168, user report):** opened on its public address, Konsol
  linked qBittorrent as `torrent.<domain>`, unreachable from the internet. The
  module listing now carries `urls.tailscale` and `urls.internet` (the latter
  only while the qBittorrent publication is active, DD-191); the page picks by
  its own scheme and otherwise points to Settings → Caddy. Konsol never proxies
  qBittorrent under its own name: the app keeps its Host/CSRF checks and login.

### DD-194: Konsol sign-in with a one-time setup code (v2-166)

- **Amended by DD-195:** Konsol can also be published over HTTPS. The public site
  shares this `forward_auth` check; there the setup code is refused, the cookie is
  `Secure`, and public failures also count in one shared budget.
- **Amended by DD-205:** the tailnet address asks for no sign-in any more and the
  one-time code is gone; the account is the public name's credential, created in
  Settings over Tailscale. The session, cookie and budget rules below now apply to
  the public name only.
- **Request (user, 2026-10-01):** "panel girişine kullanıcı adı ve parola" — option B
  (Konsol's own sign-in page) with option 1 (a one-time code shown at the end of the
  install), seven-day sessions. This reverses DD-147's "no password" for Konsol; its
  other part (Tailscale joins by the login link only) is unchanged.
- **Threat model:** protects Konsol from someone using one of the operator's tailnet
  devices or a device shared into the tailnet, and is the prerequisite for any later
  public panel (still locked, DD-191). It does not protect the server itself: Tailscale
  SSH (`--ssh`) and the public SSH port keep their own access rules; WebDAV and
  qBittorrent keep their own logins.
- **Enforcement point:** Caddy's `forward_auth` on the panel site asks the root backend
  (`GET /oturum-denetle` over its Unix socket) before every request except the sign-in
  page, its three files and the sign-in API. Pages, Files API, archive downloads and the
  root API are therefore covered in one place, including the Files backend, which never
  sees sessions. A missing session answers 302 to `/giris.html` for pages and 401
  `{giris: true}` for `/api/*`, which Konsol turns into the same redirect. The backend's
  existing Host, `X-Konsol`, same-origin and DD-180 local-caller rules stay in front of
  the session check, so host-local programs going through Caddy are still refused.
- **Records:** `KONSOL_AUTH_DIR` (`/etc/master-stack/konsol`, 0700 root) holds the account
  (`hesap.json`: user name, scrypt n=16384 hash with salt), sessions (`oturumlar.json`:
  SHA-256 of a 256-bit token, creation and absolute expiry, at most 16) and the setup code
  (`kurulum-kodu.json`: scrypt hash, 24-hour expiry). Files are 0600, read without
  following links and bounded; writes are atomic under one `flock`. The root backend gets
  write access to that folder only (`ReadWritePaths`); sessions survive service restarts.
- **First account:** when no account exists the installer runs `master-konsol kod` at the
  very end and prints the code with `printf` to the operator's terminal only — never through
  `log()`, so it is not in `install.log`; the launcher keeps no local transcript. Each such
  run replaces the previous code. The code (12 characters without 0/O/1/I/L) is single use;
  the account name (3–32 characters) and password (10–256, no control characters) are
  chosen on `/giris.html`. `kurulum.env` still holds no account.
- **Sessions:** cookie `konsol_oturum`, `HttpOnly; SameSite=Strict; Path=/; Max-Age=604800`,
  no `Secure` because the panel is HTTP inside the tailnet (Tailscale encrypts the
  transport). Seven days from sign-in, not renewed by use. Changing the password keeps the
  browser that changed it and ends every other session; sign-out ends the current one.
- **Attempt limit:** sign-in, setup-code and current-password failures share the WebDAV
  numbers (DD-180): five per client address within 60 s block that address for 300 s
  (429 with Retry-After); the table is bounded and fails closed. A wrong user name costs
  the same scrypt check as a wrong password. The limit is in memory; a backend restart
  clears it. The audit journal records only the action, address and result.
- **Recovery and automation:** `sudo master-konsol sifirla` deletes the account and all
  sessions and prints a new code; `durum` shows the state. `oturum-ac --sure N` (60–3600 s)
  prints a short root-issued session token for scripted checks; live tests read it over
  SSH, keep it in memory and close it with `oturum-kapat` (stdin). Root can already do
  everything on the host, so this adds no new authority.
- **Installer checks:** stage 7 loads `/giris.html` through Caddy, proves a host-local page
  request reaches the backend and gets 403 (DD-180), and asks `/oturum-denetle` over the
  socket for 401 (API) and 302 (page). The Files self-check now uses its loopback port.
- **Not done:** no multi-user roles, no account in `kurulum.env`, no session list in the UI,
  no public panel publication. Host-side test helpers use the loopback Files backend or the
  root socket instead of Caddy.

### DD-193: Cross-review follow-ups for v2-159..v2-164 (v2-165)

- **Request:** after reading v2-159..v2-164 (implemented with another assistant),
  the user asked to fix every open item of that review.
- **Publication saves fail fast:** a `web` row that enables internet access now
  checks the real listener before waiting for a certificate: WebDAV through
  `wan_active()` (with `wan_info()`'s reason), qBittorrent through
  `torrent_active()`. An unavailable WAN used to cost the full 60 s certificate
  wait and end with a misleading DNS/CAA hint.
- **Recovery chains:** `startup_input_guard` and `startup_forward_guard` are
  separate and all-or-nothing. An incomplete INPUT guard is never attached, so a
  failed accept rule cannot lock out SSH; the FORWARD guard no longer depends on
  it. A failed ICMPv6 rule used `return` while every other step skipped the
  family. The command still fails and a later good apply purges leftovers.
- **Tailscale gate in shares:** a new folder starts with Tailscale on only while
  Settings → Caddy publishes WebDAV on Tailscale, and an off→on folder switch is
  refused while that gate is closed — the same rule as WAN and the UI. A policy
  that is already on stays on (the gate still blocks access) and can be turned off.
- **Single-flight logins:** requests carrying the byte-identical Authorization
  value for the same share and listener wait up to 2 s for the verification in
  progress and reuse its success; a failed or slow leader makes each follower
  check itself under the normal bounded path. A cold Infuse burst therefore costs
  one scrypt check instead of competing for the WAN 4 / Tailscale 2 slots. Slot
  counts, the 200 ms slot wait, 503/429 replies and all budgets are unchanged;
  different credentials (or spellings) still need their own slot, and decoy
  hashes still occupy slots by design (DD-180).
- **One HTTPS editor:** the standalone public-HTTPS card could not appear (the
  panel always returns the DD-191 table) and its browser test exercised a path no
  host showed; it is removed with its CSS. The table edits public WebDAV HTTPS;
  turning its internet switch off remembers the name. The stored `https` key and
  its API writer stay (data model and `https-live.py --configure`).
  `master_https.status()` adds `https_port`, so the table names the HTTPS port in
  legacy HTTP mode too, where `port` is `SHARE_PORT`.
- **Console details:** a forced settings refresh requested while another load is
  in flight now runs after it, so a save never redraws pre-commit data. A closed
  WAN share card is labelled "WAN" with a neutral icon instead of HTTPS/lock; the
  create form starts Tailscale off and locked while its publication is closed.
- **Caddy journal:** the default logger excludes `http.handlers.reverse_proxy`; a
  named logger keeps that namespace at ERROR and above. Media players closing a
  probe or stream no longer log a WARN per request; dial errors and 5xx answers
  are still logged by `http.log.error`. Trade-off: an upstream that truncates a
  response is no longer reported by Caddy; the backend's journal and health stay.
- **Installer temp-file leak (found while cleaning the test host):**
  `render_template` removed its `/tmp` copy through a `RETURN` trap, but Bash
  traps are global and `atomic_write` set its own `RETURN` trap, replacing it.
  On Bash 5 (Debian/Ubuntu) every rendered template left a root-only 0600 file
  in `/tmp` until reboot; Bash 3.2 on the Mac hid it. Neither function uses a
  trap any more: `render_template` streams into `atomic_write`, which cleans up
  explicitly and returns non-zero on a write failure. A Bats test checks Bash 5
  leaves no file and that a caller's own `RETURN` trap still runs.
- **Smaller fixes:** 403 stubs take the module template's address line instead
  of hard-coded names (single source); an unknown publication service gets its
  own message; stopped, uninstalled or unsafe qBittorrent rows name the cause;
  the two remaining panel JSON parse sites catch deep nesting; the health WAN
  card shows the share manager's reason; Files names the reserved-destination case.
- **Test tooling:** `publications-live.py` reads the operator's names from the
  host (missing-DNS probe under reserved `example.net`) and accepts an already
  public qBittorrent; `backend-hardening-live.py` uses the host's WAN mode;
  `share-networks-live.py` exits 3 before any change unless legacy HTTP is
  active; `settings-https-ui.cjs` drives the table.
- **Unchanged on purpose:** TCP/HTTP budgets (DD-188), restart on share save
  (DD-158/192), the refresh-page refusal of `durum`/`pause` (DD-192) and the
  schema-3 migration.

### DD-192: Per-connection WebDAV policies and dual-card Shares (v2-164)

- **Decision:** retain one folder, stable share ID and account/password while
  giving Tailscale and WAN independent enabled state, RO/RW and absolute expiry.
  This permits Tailscale RW with WAN RO, or the reverse, without overlapping
  folder grants or duplicated accounts. Both off is valid and keeps the account.
  New shares default to Tailscale enabled/RO/seven days and WAN off/RO/seven days.
- **One policy source:** schema 4 stores `connections.tailscale` and
  `connections.wan`, each exactly `{enabled: bool, permission: "ro"|"rw",
  expires: Unix-seconds|null}`. Shared `permission`, `expires`, `paused` and
  `networks` are removed; their presence in a schema-4 item is a conflict and
  fails closed. Valid schema 3 converts in memory, copying the exact shared
  permission/expiry to both policies, enabled only for a previously selected
  network when not paused. IDs, path/account, salt/hash, folder identity and
  `created`/`changed` stay unchanged; `prepare` persists schema 4. This is a
  narrow exception to DD-185, not restored schema-2 support or general cleanup.
- **Partial writes:** `POST /api/konsol/paylasim/kaydet` accepts one or both
  nested scope patches with `enabled?`, `permission?`, `days?` (0/1/7/30) and
  `ack_write?`. Read omitted values under the existing operation locks; never
  reset the other scope or extend an omitted expiry. Toggling does not renew an
  expired connection. Explicit RW requires `ack_write: true` in that same scope,
  even when already RW or off. Shared account/path/password edits stay separate.
  Old global-policy fields and `.../durum`/`pause` requests are rejected with a
  refresh-page message, so a stale browser cannot silently rewrite both policies.
- **Enforcement:** the receiving loopback listener selects the policy, never a
  client header. Every DAV write, live transfer chunk and staged PUT/COPY final
  publication enforces the applicable enabled/permission/expiry checks. A cached
  password success cannot bypass authorization. Descriptor/root checks, budgets,
  rollback and secret handling remain mandatory.
- **UI and state:** each Shares entry has two cards with its own switch,
  permission, expiry, address/copy and Infuse details. WAN is HTTPS when
  configured; legacy HTTP is labeled honestly with its plaintext warning and
  consent. Manage edits the shared folder/account/password. Public connection
  state adds `expired`, `available` (global gate), `active`, `reason` and `url`.
  An available transport can supply a candidate URL even while the card is off
  or expired; `row.urls` contains only active connections. A card explains why a
  DD-191 global Caddy gate blocks access and cannot override that gate.
- **Retained lifecycle:** configured HTTPS keeps its renewal listener with no
  active folders, subject to the global publication gate and DD-190 prerequisites.
  Share edits still restart active WebDAV and interrupt all transfers; retain
  that warning. This does not add hot reload, new listeners or a new ACL model.
- **Verification:** see [the test runbook](../tests/README.md) for fixture and
  opt-in live/UI checks, and [SESSION.md](../SESSION.md) for the main implementation
  task's exact v2-164 results and host health. Main reports successful `nrm`
  deployment, exact migration preservation, real HTTPS/Tailscale acceptance with
  byte-identical registry cleanup, and read-only installed UI acceptance.

### DD-191: Fixed publication table with independent private and public gates (v2-162)

- **Amended by DD-195:** the Panel row's internet switch and name are editable;
  its Tailscale switch stays fixed on. See DD-195 for the extra backend gate.
- **Amended (v2-169, user report):** a fresh install refused the first HTTPS
  publication because WebDAV without a saved name is "legacy HTTP mode". The
  real constraint is Caddy's single WAN port, so the rule now follows the live
  listener: enabling qBittorrent or Panel HTTPS is refused only while folders
  are actually shared over plaintext HTTP; while an HTTPS row is on, legacy HTTP
  WebDAV internet access is unavailable (cards name the reason) until an HTTPS
  name is saved. Folder connections are never rewritten.
- **Amended by DD-194:** a Konsol sign-in now exists; publishing the panel on the
  internet remains a separate, not yet taken decision, so its WAN row stays locked.
- **Amended by DD-192:** folder gates are now per-connection policies. Cards
  expose candidate addresses while locally off, but globally disabled routes
  still have no advertised address and `row.urls` contains only active scopes.

- **Decision:** extend DD-190 to a real Settings → Caddy table, not a general
  proxy editor. The fixed catalogue is Panel, qBittorrent and WebDAV. Panel
  Tailscale is on and WAN is locked in both UI and API until a separate login
  design exists. No Cloudflare Tunnel, arbitrary upstream or DNS API token.
- `master_publications.py` reads saved `web.<service>` rows containing `tail`,
  `enabled` and `domain`. A disabled public name is remembered, never converted
  to plaintext HTTP. Existing DD-190 HTTPS settings migrate on first row save;
  the old HTTPS endpoint remains compatible. Two enabled rows cannot share a
  hostname. qBittorrent HTTPS cannot run while folders are shared over legacy
  WebDAV HTTP: convert that row to HTTPS or close those folders' internet
  connections first (v2-169; earlier the mode alone blocked it).
- Both public names use the same assigned IPv4/TCP `SHARE_HTTPS_PORT`, strict
  SNI/Host and existing socket limits. qBittorrent upstream remains fixed to
  loopback `TORRENT_UI_PORT`; its permanent native password, mandatory local
  login, disabled subnet bypass, CSRF/Host checks and login-attempt ban are
  prerequisites. An anonymous API probe must return 403. Preferences, peer
  discovery and UPnP are not rewritten. Native application bans may cover
  the proxy address unless the operator configures trusted reverse proxies;
  these are not WebDAV's per-client password budgets.
- Saving is an isolated revision-checked Settings transaction. DNS is checked
  before mutation and certificate trust/name before commit. Private projections
  are snapshotted too: first-row failure or process crash must restore the old
  route even when no saved `web` row existed. No extra timed user confirmation.
- Disabling a Tailscale publication renders an explicit 403 route (including
  WebDAV by IP); it does not stop the app or remove shared Caddy ports. Folder
  network/account/RO/RW/expiry remains a second gate. No folder records change,
  and Files omits URLs for globally disabled networks. Graceful Caddy reload
  permits in-flight transfers to finish; account edits still restart WebDAV.
- The existing narrowly scoped publication guard and module lifecycle refresh
  known projections; unchanged output is a no-op. Module reapply and installer
  consume saved choices. Stopped/removed qBittorrent loses its WAN site; unsafe
  native auth configuration also suppresses it on the next guard run. This is
  not instantaneous monitoring of qBittorrent's in-memory preferences.
- Unit/browser fixtures are not public reachability or native-client proof.
  Live acceptance must separately check DNS, real TLS, both network gates,
  private API isolation, rerun persistence and unchanged folder accounts.

### DD-190: Optional public WebDAV HTTPS without widening private administration (v2-161)

- **Amended by DD-193:** the separate Settings card is gone; the DD-191 table is
  the only editor. The stored `https` key and its API writer remain.

- **Decision:** Settings → Caddy accepts a separate full public domain for
  folder WebDAV. `master_https.py` interprets the saved mode, checks DNS and
  certificates and generates the WAN site; `master_settings.py` owns the
  existing revision/lock/pending/commit workflow, and `master_shares.py` owns
  publication. This supersedes DD-179's HTTP-only boundary, not its per-folder
  network selection, authentication, limits or private administration boundary.
- **DNS and transport:** the name must resolve to exactly the host's assigned,
  globally routable `WAN_IPV4`, with no AAAA or proxy. Caddy owns Let's Encrypt
  keys, issuance and renewal through TLS-ALPN on TCP `SHARE_HTTPS_PORT` (443).
  HTTP challenge is disabled and `auto_https disable_redirects` avoids a WAN
  port-80 listener. No Cloudflare/DNS API token, DNS write, NAT discovery, new
  certificate daemon or public IPv6 publication. Private names and Tailscale
  HTTP on `SHARE_PORT` (61010) remain unchanged.
- **Host/SNI boundary:** only the WAN HTTPS `servers` block enables
  [`strict_sni_host on`](https://caddyserver.com/docs/caddyfile/options#strict_sni_host),
  rejecting a request whose Host differs from its TLS SNI with 421. Previously,
  an unmatched/spoofed Host could receive Caddy's empty default 200; it exposed
  neither an API nor private content. This makes rejection explicit without
  changing private HTTP listeners. `protocols h1 h2` permits only HTTP/1.1 and
  HTTP/2 over TCP; HTTP/3 is disabled and no UDP 443 listener or firewall
  permission is added.
- **Three deliberate modes:** no `https` key preserves the existing explicitly
  consented HTTP WAN behavior. A nonempty domain selects HTTPS; an explicitly
  empty domain selects off, never HTTP fallback. Accounts, network selections,
  IDs, hashes, permissions and expiry are not rewritten by this setting.
  In HTTPS mode the listener/permission remains for renewal even with no active
  folders, while the assigned address, valid registry and running registration
  remain available. Every folder still authenticates and enforces its network,
  identity, permission, pause and expiry. For the configured public Host, only
  `/s/*` is proxied; other paths, including the administrative APIs, return 404.
- **Save is a transaction, not a second connectivity confirmation:** reject
  mixed/stale requests; record durable pending state before publication;
  commit only after a trusted chain and matching hostname verify. Caddy/firewall
  or certificate failure restores the previous saved projection. The independent
  Settings guard recovers a pre-commit crash; the durable commit marker protects
  a completed save. Restoring the prior mode after a failed first enablement
  can restore its consented HTTP endpoint; a committed HTTPS setting never
  silently downgrades when a certificate later fails. Explicit removal closes
  new WAN connections through graceful Caddy reload; existing transfers may
  finish. Account mutations still restart DAV and interrupt transfers.
- **Status is narrowly evidenced:** connect locally to the assigned WAN IPv4,
  with the domain used for SNI and chain/hostname verification, never as an
  arbitrary connection target. Report expiry and warn at 14 days or less.
  “Ready” proves that local certificate check, not public DNS propagation,
  provider firewall reachability or native-client compatibility. Public access
  requires separate external acceptance.
- **Coverage and limits:** `test_https_settings.py`, `test_https_panel.py` and
  `settings-https-ui.cjs` exercise transactions, rollback/recovery, mode-specific
  URLs/ports, certificate status and the private UI/API boundary. Opt-in
  `https-live.py` uses three temporary shares and turns their connections off,
  removes its own fixtures and checks the original registry digest;
  `--configure` deliberately leaves the real public domain saved. Run instructions are in `tests/README.md`;
  execution results belong in `CHANGELOG.md`/`SESSION.md`, not inferred here.

### DD-189: Audit stage 4 distinguishes unknown health and IPv4-only names (v2-160)

- Generated `interface-name` records for IPv4-bound services use `/4`. Both
  DNS readers understand the suffix; explicitly supplied IPv6 host records
  remain IPv6. Returning an unusable AAAA is not a reachability improvement.
- Health checks the desired core services/timers and running optional modules,
  including enabled WG networks, not merely systemd's failed list. Deliberately
  stopped optional services are not failures. Unreadable probes/registries show
  unknown/warning instead of success. Deep JSON is a controlled input error.
- `/run/reboot-required` remains authoritative when present. Without it, compare
  the running kernel with the distribution's `/vmlinuz` or `/boot/vmlinuz`
  target, requiring matching flavor and a nonempty boot image/initrd pair. No
  lexical package-version guess; missing, broken or custom boot evidence is
  unknown. `ProtectKernelModules` hides module directories inside the panel;
  their invisibility is not treated as a missing kernel and the sandbox stays
  unchanged. The comparison is a distribution boot-link check, not a certification
  of an administrator's custom bootloader choice. Reboot remains manual.

### DD-188: Audit stage 3 bounds authentication and shortens write locks (v2-160)

- **Amended by DD-193:** identical concurrent credentials first share one
  verification (single flight); only then do requests compete for a slot.

- WAN and Tailscale have separate four-slot/two-slot scrypt budgets. A request
  waits up to 200 ms and rechecks the successful-login cache before hashing.
  Exhausted processing capacity yields 503 plus Retry-After; bad-password
  throttling remains 429. Full connection pools send a best-effort nonblocking
  503 without spawning another worker. No unbounded admission queue is added.
- PUT/COPY receive/copy/fsync a private sibling outside the mutation lock.
  Final publication rechecks share identity, permission, scope, expiry, pinned
  parents, source/target versions and HTTP preconditions under the lock. A
  conflict removes the temporary result; it never silently replaces a concurrent
  write. Existing disk reserve, size limits and atomic publication remain.
- WebDAV adds syscall/process/IPC isolation, TasksMax=96, MemoryMax=512M and a
  5-per-10-minute automatic start budget. Explicit operator renewals still reset
  start throttling. Page cache counts toward MemoryMax and is reclaimable; a
  historical memory peak is not evidence of a process leak.
- Tailnet proxy keepalive becomes 30 s, below the backend's 60 s idle limit;
  WAN remains nonpersistent upstream. Files gets a 180 s inactivity timeout
  (longer than its proxy keepalive) and controlled deep-JSON rejection.
- Keep TCP 16/IP, 64 total and HTTP 4/IP, 8 WAN/64 tailnet workers for now.
  Zero measured TCP overflow does not justify removing the resource ceiling;
  these budgets are not volumetric DDoS protection. Account edits still restart
  DAV and interrupt transfers. HTTP WAN risks and the local proxy-header trust
  boundary remain explicit; this package does not add TLS or a hot-reload engine.

### DD-187: Audit stage 2 keeps boot failure closed and pins privileged paths (v2-160)

- **Amended by DD-193:** the INPUT and FORWARD recovery guards are independent
  and each is all-or-nothing; an incomplete INPUT guard is never attached.

- **Registry failure:** validation remains strict. An apply with unreadable
  settings/share/WireGuard data preserves an existing owned default-deny policy
  and manual denials. If none exists, a small owned guard before `ts-input`
  allows loopback, established replies, SSH, Tailscale transport and essential
  IPv6 control traffic; unknown WG interfaces cannot forward. The command still
  fails, so the firewall health/pre-start gates cannot call recovery healthy.
  A subsequent successful apply removes these temporary owned guards. Read-only
  `--check` never repairs or mutates, and third-party chains remain untouched.
- **Other interfaces:** both INPUT policies end with an unconditional DROP,
  after the explicit WAN DROP. An extra interface no longer falls through to
  the host's ACCEPT policy; explicit operator rules remain authoritative.
- **Privileged paths:** installer directory creation, private archive mode and
  selective data-tree repair use pinned directory descriptors and no-follow
  traversal. Only directories and single-link regular files are changed, only
  where UID/GID/mode differs. Symlinks, special files, hard links and the reserved
  top-level `.pay`/private `.arsiv` trees are not traversed by ordinary repair.
  This replaces path-based `find -exec chown/chmod` (DD-53/DD-84 implementation).
- **Lock order:** module mutations take install then module locks. A child
  invoked by the locked installer reuses its inherited flock descriptor only
  after checking the descriptor's inode against the canonical install lock;
  an environment flag alone is not a bypass. Standalone modules acquire it.
- **Third qBittorrent read:** the CLI's first-login username lookup also reuses
  the bounded no-follow reader; FIFO input cannot hold the module/install locks.
- **Linux verification follow-up:** Bash 5.2 enables `patsub_replacement`, unlike
  macOS Bash 3.2. Template rendering temporarily disables it, then restores the
  caller's option, so literal `&` and backslashes are not interpreted as a match.

### DD-186: Audit stage 1 separates admission queues from workload limits (v2-159)

- **Evidence:** the v2-158 review found Caddy 502s from `EAGAIN` on the root
  backend's Unix socket. All three Python server classes inherited a listen
  backlog of 5. No TCP listen overflow was observed, so a larger TCP backlog
  is preventive, not proof of the first Infuse delay's cause.
- **Decision:** set `request_queue_size = 128` on all three server classes.
  This queues pending connections; it does not raise WebDAV's simultaneous
  request/hash budgets, the firewall TCP limits or bandwidth. Capacity tuning
  and authentication admission belong to a separate, measured stage.
- **Service-owned configuration:** reuse `master_settings.read_regular` in
  both qBittorrent readers: descriptor-relative no-follow traversal,
  nonblocking open, regular-file check and bounded reads. The panel retains
  its 64 KiB limit and allowlist; sharing uses the helper's 1 MiB limit and
  fails closed on unsafe/unreadable input. Missing profiles remain allowed.
- **Internal directory sources:** listing/path guards and destination-name
  checks did not protect root `.cop`, `.pay` and `.arsiv` as mutation sources.
  Validate every selected source before any rename/move/trash work; also
  disallow promoting a nested reserved name into the root. Trash restore uses
  an alternate name instead of creating a reserved root entry. This is an
  administrative Files API guard, not an anonymous WAN authentication issue.
- **Scope:** no share/account changes, migrations, automatic reboot, WAN
  exposure changes or new dependencies. The historical 670 MB memory peak
  may include page cache but cannot be attributed retrospectively without
  that invocation's `memory.stat` samples.

### DD-185: Fresh-install-only cleanup and a documentation index (v2-158)

- **Narrow exception in DD-192:** valid schema-3 WebDAV registries now convert
  to schema 4 without changing identity/account or renewing expiry. Schema 2
  and the other retired migrations below remain unsupported.

- **Request:** the user accepted the 2026-09-29 maintenance recommendation: trim
  the documentation first, then delete code that only served upgrades from
  earlier versions (fresh install only, no migrations).
- **Removed:** `panel/master_wg_upgrade.py` and its stage-4 call (DD-177 upgrade
  helper) with the settings filter for old wgN-scope rules; `GET /api/wg/sistem`
  and the `ports`/`share` keys it added to the resources reply; schema-2 share
  registry conversion (only schema 3 loads); the retired `health.<domain>`
  cleanup; the HTTP 410 answers for `/api/paylas*` (now 404); master-modul's old
  shared-account warning; the `ui`/`ping` WireGuard input kinds in the settings
  view (a hand-added WG→host ACCEPT is now shown as unknown); Konsol's rewrites of
  retired bookmarks; log labels for actions no backend writes; the retired login
  event kind, unused JS identifiers and 93 lines of CSS no page uses.
- **Kept on purpose:** the reserved `.pay` protection (it hides data a reused
  disk could still hold, DD-171); the registry's fixed `inet` column (a format
  change, not a deletion); the refusal of a `scope` field (rejects input, stores
  nothing); the archive API's `nested`/`layers` options and the
  missing-`SHARE_WAN_BACKEND` guards (option handling and fixtures, little gain).
  Tests that assert removed features stay absent are kept as regression guards.
- **Documentation:** retired and superseded decisions moved verbatim to
  `docs/archive/design-decisions-retired.md` (75 entries; DD-133, DD-149 and
  DD-155 stay live because parts are still current), with a one-line-per-entry
  `docs/decisions-index.md`; CHANGELOG entries before v2-145 and SESSION history
  moved verbatim to `docs/archive/`; contract, architecture, README, CLAUDE.md
  and test notes describe current behaviour only.
- **Consequence:** a host installed with an older version needs a fresh install;
  the installer no longer rewrites its WireGuard registry, settings or shares.

### DD-184: Tailscale and Caddy join unattended upgrades, at night (v2-158)

- **Request:** the user accepted the 2026-09-29 recommendation to update these
  automatically. Supersedes DD-113's "Tailscale/Caddy only on a re-run".
- **Why:** tailscaled is always reachable from the internet (UDP 41641) and Caddy
  is while a WAN share is published; a fix in either waited for a manual re-run.
- **How:** `52master-stack-unattended` adds `Unattended-Upgrade::Origins-Pattern`
  entries for the two repositories' Release fields (read on nrm: Tailscale
  `Origin/Label: Tailscale`, Caddy `Origin: cloudsmith/caddy/stable`). The list is
  appended to the distribution's, never replaces it. A timer drop-in moves the
  daily upgrade from 06:00 (+60 min) to `APT_UPGRADE_TIME` 04:00 (+30 min);
  `Persistent=true` from the distribution unit still catches up after downtime.
  Stage 7 warns when the effective configuration lacks either pattern.
- **Trade-off:** an update restarts tailscaled (the exit node and tailnet drop for
  a few seconds; the firewall reapplies through `PartOf`) or Caddy; a bad upstream
  release can arrive unattended. Automatic reboot stays off. Tailscale's own
  `--auto-update` was not used, to keep one mechanism and one schedule.

### DD-183: No archive jobs page; results in Günlük, running job as a bar (v2-157)

- **Request:** remove the "Arşiv işleri" tab from Files: if the job states are in
  the log, a separate page is not needed.
- **Finding:** the log held only the start, as an opaque job id, and never the
  result; the page was also the only place for progress and cancel, and
  starting a job navigated to it.
- **Decision (user chose "Günlük + ince çubuk"):** the Files backend audits the
  start (`arsiv-olustur`/`arsiv-ac`, "sources → result name"), the cancel
  request (`arsiv-iptal`) and, from the job worker, the result (`arsiv-sonuc`,
  client "-", ok for done/skipped/cancelled, hata for failed/interrupted,
  including jobs found interrupted at startup). Konsol shows a one-line bar
  above the Files list only while a job is queued/running, with "İptal et";
  completion keeps the existing toast and list refresh. The "Sonucu göster"
  button went with the page. API and private history are unchanged.

### DD-182: Capped rollback, WAN address change, watchdog resets, damaged history, health card (v2-156)

- **Source:** the 2026-09-29 resilience review (risks 1, 3, 8, 9, 10) and the
  health-card proposal. User approved "v2-156 için başla".
- **Stuck rollback:** an unconfirmed settings change whose rollback keeps
  failing used to be retried every 2 s forever while the installer, modules and
  shares refused to run. Automatic attempts now wait 15, 30, 60, 120 s; the
  fifth failure sets phase `stuck`: the guard stops trying and its timer sleeps.
  Konsol shows the last error with "Yeniden dene" (a manual attempt) and
  "Bırak" (only when stuck, typed `onayla`): the pending file is removed and
  files stay as they are; re-running the installer applies the saved settings.
  Chosen over an automatic give-up so a person sees why the rollback failed.
- **WAN address change:** the share site binds WAN_IPV4 from the install; a new
  provider address made Caddy fail (Konsol included) and the installer die in
  stage 6. `wan_info()` now also requires the address to be assigned (probe
  bind without a port; only EADDRNOTAVAIL means gone), so the 30 s guard removes
  the site. If Caddy is already down, a failed reload starts it with the new
  projection instead of restoring the old one; the next guard run confirms.
  Stage 6 removes a site bound to another address before restarting Caddy.
- **Watchdog:** `reset-failed` before restarting a failed Caddy (a boot race
  could use up 3 starts/600 s and leave Konsol down ~10 min); the firewall is
  checked again after `tailscale wait`, since the tailnet allowlist includes
  PeerAPI read from tailscaled.
- **Archive history:** invalid `jobs.json` is renamed to
  `jobs.json.bozuk-<time>` in the private workspace and history starts empty;
  I/O errors still stop the service (a real disk problem).
- **Health card:** `GET /api/konsol/saglik`, read-only, cached 30 s, shown on
  Settings → Sistem: failed units, Tailscale state/online/key expiry (warn
  under 14 days), `master-firewall --check`, `/run/reboot-required`, NTP sync,
  free space/inodes of `/` and SERVER_ROOT against the upload reserve, pending
  or stuck settings change, and a WAN share whose address is gone. No
  notifications and no automatic repair.

### DD-181: Remember WebDAV logins, idle rollback timer, quieter journal, compressed Konsol (v2-155)

- **Measured on nrm (2026-09-29):** each WebDAV request re-ran scrypt (~22 ms
  locally, more on a VPS vCPU; Infuse browsing sends hundreds). The settings
  guard ran 1266 times an hour and made 77% of the journal; the WAN-share timer
  added 354 lines an hour. Konsol re-downloaded ~270 KB uncompressed on each
  load. The root backend logged every request, pushing audit lines out of the
  400 lines "Son işlemler" reads.
- **WebDAV:** successful logins are remembered in memory (10 min, 256 entries;
  key: share, stored hash, HMAC of the Authorization value under a per-process
  key). No change to what is checked: pause, expiry, scope, per-IP and
  per-share limits apply to every request. A registry edit restarts the service,
  which clears the memory. Tailnet slots go from 16 to 64 because Caddy keeps up
  to 32 idle upstream connections that could hold every slot; every closing
  reply now says `Connection: close`.
- **Nagle (found while measuring on nrm):** the WebDAV and Files backends write
  headers and body separately. On Caddy's kept-alive loopback connection Nagle
  held the second write for the peer's delayed ACK, so every request through
  Caddy took ~44 ms (a new connection: 1 ms). Both handlers now set
  `TCP_NODELAY` (`disable_nagle_algorithm`). The root backend uses a Unix socket
  and was not affected.
- **Rollback timer:** apply starts it (under the locks, before the pending
  file); an idle guard run stops it only while holding the same locks, so it
  cannot stop a timer an apply still needs. Enabled for boot. Stage 7 checks
  "enabled", not "active".
- **Journal:** both 30 s/2 s oneshots set `SyslogLevel=notice` and
  `LogLevelMax=notice`: PID 1's per-run start/finish lines are dropped, the
  helpers' own messages are kept. The root backend no longer logs request lines
  (the Files backend never did); audit lines remain.
- **Konsol:** `encode zstd gzip` on the panel site; page files use `no-cache`
  (ETag revalidation) instead of `no-store`. API replies keep `no-store`. The
  WebDAV sites are not compressed (video).
- **Settings view:** concurrent refreshes share one computation; "Yenile" still
  recomputes unless one finished while it waited.
- **CPU priority:** qBittorrent runs with `Nice=10` and `CPUWeight=50`, so
  tailscaled (the exit node's throughput limit) and Konsol come first. Archive
  job threads (and the unrar they start) are niced to 10; already-compressed
  media is stored, not deflated, in ZIPs.
- **Not done:** folder-size caching in Files, reusing the WireGuard sampler for
  `/api/wg/state`, building the settings view from one `iptables-save`.

### DD-180: Private sockets, shared login limits, disk reserve, sandboxed unrar, firewall-first WireGuard (v2-154)

- **Finding (2026-09-29 review):** loopback was treated as a trust boundary. The
  password-less root backend accepted any local process on `127.0.0.1:61008`
  (its only other gate, `X-Konsol`, is a header a client sets), and Caddy's
  admin API on `127.0.0.1:2019` was open to every uid; verified from the
  downloads account on nrm. A code-execution bug in a downloads-uid process
  (qBittorrent with untrusted peers, unrar with untrusted RARs, the WAN-facing
  WebDAV) could therefore become root or publish the root backend.
- **Decision:** the root backend listens only on `WG_PANEL_SOCKET` (`0660
  root:CADDY_GROUP`, folder `0755` via `RuntimeDirectory`) and also checks
  `SO_PEERCRED` (root or Caddy's group). Loopback Host names are no longer
  accepted. Caddy's admin API moves to `CADDY_ADMIN_SOCKET` in a `0700 caddy`
  runtime folder; `admin off` was rejected because `systemctl reload caddy`
  (modules, domain rename) needs the API. Stage 7 proves both as the downloads
  account and reloads Caddy once.
- **Relayed from the host itself (found by the v2-154 review):** Caddy's
  tailnet listener is reachable from local programs too, so the socket alone
  still let the downloads account reach the root backend through Caddy
  (reproduced: HTTP 200). A request that carries Caddy's X-Forwarded-For is now
  accepted only from a Tailscale address (100.64.0.0/10, fd7a:115c:a1e0::/48)
  that is not one of the server's own (a probe bind succeeds only for local
  addresses; loopback/link-local always count as local). Caddy overwrites the
  client's header, so it cannot be forged. Stage 7 proves the 403 as the
  downloads account and runs its own backend check over the socket. The probe
  does not reserve a port (`IP_BIND_ADDRESS_NO_PORT`) and only
  `EADDRNOTAVAIL` counts as "not local": port or descriptor exhaustion caused
  by a local attacker rejects the request instead of letting it through.
  `net.ipv4.ip_nonlocal_bind=1` would make every client look local (Konsol
  refuses everything); the installer never sets it.
- **WebDAV logins:** the per-IP rule (5/60 s → 300 s) now also covers the
  Tailscale listener, keyed on Caddy's header; local probes share one key and
  still receive the uncounted 401 challenge. A per-share, per-listener budget
  (100 failures/hour) closes that share for an hour to addresses that have not
  logged in since the service started, so distributed guessing is bounded
  while the connected recipient keeps working. A wrong user, paused or unknown
  share costs one scrypt check (decoy record), closing the timing oracle. The
  one-hour lock and forgetting known addresses on restart are accepted
  trade-offs; a Konsol flag is left to the planned health card.
- **Disk reserve:** WebDAV PUT/COPY and Files uploads refuse (507) before and
  while writing when free space would drop under min(5 GiB, 10%). The review
  suggested max(5%, 5 GiB); a flat 5 GiB protects journald/apt/state on large
  disks without idling tens of GB, and 10% keeps small disks usable.
  qBittorrent and archive jobs are outside this reserve.
- **unrar sandbox:** the Files unit adds `IPAddressDeny=any` with loopback
  allowed, `SystemCallFilter=@system-service`, `ProtectProc=invisible`,
  `PrivateIPC` and `MemoryDenyWriteExecute`. This blocks direct egress and the
  Caddy tailnet path, not loopback services: dnsmasq (which forwards when Konsol
  DNS forwarding is on), resolved on Ubuntu and the password-protected
  qBittorrent WebUI remain reachable. A separate network namespace for the RAR
  helper is left for later.
  - **Amended (2026-10-05):** since DD-217 qBittorrent's interface is a container
    publication on loopback, not a host socket. A uid-1000 unit with this address
    filter got no answer from it on nrm (control without the filter: HTTP 200), so
    only host loopback services such as dnsmasq remain reachable.
- **Request smuggling (pre-existing, found by the review):** the root backend
  answered rejected POSTs without reading their body on a keep-alive
  connection, so a body hidden in a cross-site text/plain POST was parsed as a
  second request that passed the CSRF gate (and could forge the client
  address). It now closes the connection after every error and whenever a
  request body was not fully read, as the Files backend already did.
- **WireGuard:** a template drop-in orders `wg-quick@` after
  `master-firewall.service` and runs `master-firewall --check` first, as Caddy
  does. Without owned rules the default FORWARD policy is open and DD-177's
  private-destination block does not exist. A network that fails for this
  reason is reopened by `refresh-tailnet-config` once the check passes.
- **Not changed:** qBittorrent's own sandbox, the Files backend's loopback TCP
  (uid 1000 already owns its data), HTTP on WAN (DD-179), Konsol identity.

### DD-179: Per-folder HTTP WAN opt-in with separate admission budgets (v2-153)

- **Amended by DD-190/DD-192:** HTTPS is optional; connection policies are
  independent in schema 4, both may be off, and valid schema 3 converts safely.
  The shared-policy/schema wording below records the earlier implementation.

- **Changed in v2-158:** the schema-2 registry migration is removed; only a
  schema-3 `webdav.json` is accepted. New shares still default to Tailscale only.

- **Decision:** keep HTTP as explicitly requested. A folder selects Tailscale,
  WAN IPv4 or both; schema-2 migration/new shares are Tailscale-only. Adding WAN
  requires explicit plaintext-risk consent; TLS and provider/NAT automation are
  not implied. The same account, ID, permissions and expiry serve both addresses.
- **Boundary:** Caddy binds an explicit WAN IP only when needed, proxies only
  `/s/*` to a distinct loopback address on the same port, and overwrites the
  real-client-IP header. Listener scope decides access before credentials/file
  IO; forwarded headers cannot turn a WAN request into a Tailscale request.
- **Limits:** 5 failures/60s blocks the IP for 300s; bounded 4096-entry history,
  4 concurrent scrypt checks; 8 WAN backend connections, 4 requests/IP, 16 separate
  tailnet slots, 30s WAN idle timeout. Edge TCP connlimit is 16/IP and 64 total,
  before manual allows; denials remain effective. These are not bandwidth caps.
- **Lifecycle:** locked atomic registry plus private pending snapshot; failed
  publication rolls back. A narrow 30s expiry/recovery timer removes the last
  expired WAN projection; unchanged projections do nothing. Immediate request
  expiry remains in the unprivileged handler. No broad reconcile engine.
- **Trade-offs:** HTTP reveals credentials/content on the internet; account
  edits still interrupt all DAV streams and reset in-memory attempt blocks.
  Conntrack can retain closing sockets temporarily. TLS and native-client/fresh
  Ubuntu acceptance remain separate from this initial disposable-host test.

### DD-1: Atomic staging-chain swap for firewall rules

- **Decision:** Firewall updates build a brand-new, randomly named chain
  fully, then splice it in and only afterward tear down the old one,
  instead of flushing and rebuilding the canonical chain in place.
- **Context:** `install.sh:1336-1390` (`create_staging_chain`,
  `activate_staging_chain`) and the mangle-table equivalent.
- **Rationale:** Flushing `MASTER-DOCKER`/`MASTER-TS-FORWARD` in place
  would leave a window where the chain is empty — either briefly
  fail-open (dangerous) or briefly fail-closed (drops exit-node traffic).
  The staging-chain-then-rename approach keeps the previous, complete rule
  set live until the new one is fully ready.
- **Trade-off:** More complex code (stale-chain cleanup, `$RANDOM`-based
  naming) than a simple flush-and-rebuild, but avoids any exposure window.

### DD-6: Fail-closed masking for optional DNS/Caddy services

- **Decision:** `dnsmasq` and `caddy` are installed already `mask`ed, and
  only `unmask`ed after their generated configuration has been validated
  (`dnsmasq --test`, `caddy validate`).
- **Rationale:** Prevents the packaged default (wildcard-listening)
  configuration from ever being reachable — even transiently across a
  reboot mid-install — before the Tailnet-only configuration is confirmed
  good.
- **Trade-off:** Adds bookkeeping (capturing and restoring prior
  mask/enable/active state in the `EXIT` trap) but is necessary for the
  security guarantee to hold across a failed or interrupted install.

### DD-11: UDP GRO forwarding is applied once, not continuously reconciled (2026-07-28)

- **Decision:** `tailscale-udp-gro.service`'s one-time Stage 2 setup
  (helper script + oneshot systemd unit, re-applied at every boot) is
  kept, but the ~54 lines that used to make `master-network-reconcile`
  detect and repair GRO drift every 5 minutes were removed.
- **Context:** `install.sh:830-940` (setup); the removed reconcile logic
  previously lived around where `all_critical_state_healthy()` is now
  defined in the `master-network-reconcile` heredoc.
- **Rationale:** UDP GRO forwarding is a pure throughput optimization for
  Tailscale's exit-node traffic — it never affects connectivity, only
  performance under load. It was already excluded from
  `all_critical_state_healthy()`, so its drift never affected any
  pass/fail postcondition; the only thing continuous reconciliation
  bought was auto-fixing a drift that isn't caused by a reboot (ethtool
  NIC flags don't persist across reboots on their own, which is why the
  one-time, per-boot setup step still exists and is not being removed).
  Resolves **L3** in `SECURITY_REVIEW.md`.
- **Trade-off:** If GRO settings are reset by something other than a
  reboot (rare — e.g. a NIC driver hot-reload, or certain virtualization
  live-migration events), the script no longer notices or fixes this
  within 5 minutes. It will be re-applied on the next reboot or the next
  `install.sh` re-run instead. Accepted by the user as a reasonable trade
  given GRO is throughput-only.
- **Side effect caught during this change:** two variables
  (`ETHTOOL_BIN`, `CURRENT_WAN6_IF`) inside the `master-network-reconcile`
  heredoc were only ever used by the removed GRO check, and became dead
  code. `shellcheck install.sh` did **not** flag them, since it cannot see
  inside heredoc bodies (see **H4**) — this had to be caught by manual
  review, a concrete illustration of why H4 is a real gap and not just a
  theoretical one.
- **Amended 2026-07-29 (first pass) — the unit is checked again.**
  Reconcile reads `tailscale-udp-gro.service`'s `ActiveState` and restarts
  it (15-minute cooldown via the existing `restart_budget_available`
  stamp) when it is not active.
- **Amended again 2026-07-29 (second pass) — the flags are checked too,
  because live testing showed the unit check alone proves nothing about
  throughput.** The fault-injection run made the gap concrete: after
  `systemctl stop tailscale-udp-gro`, `ethtool -k eth0` still reported
  `rx-udp-gro-forwarding: on`. Stopping the unit does not undo the flags,
  so a unit-only check verifies bookkeeping rather than the optimization
  it exists to protect. Reconcile now also runs `gro_flags_ok()` against
  `CURRENT_WAN4_IF` (already computed for address-drift detection) and
  repairs on either signal. `ETHTOOL_BIN` is reinstated for this — the
  variable this decision originally noted as dead code.
  - **What is still *not* re-added:** the removed logic polled both the
    IPv4 and IPv6 default interfaces and reimplemented the helper's apply
    path. The new check reads the IPv4 WAN interface only and never
    applies anything itself — repair is always `systemctl restart`, so
    systemd stays the single execution path and the unit's state keeps
    reflecting reality. That is why this is ~15 lines rather than the ~54
    that were removed.
  - **Everything the check cannot evaluate is treated as healthy:** no
    `ethtool` binary, no detected WAN interface, a driver that does not
    report the two features, or one that reports them `[fixed]`. This
    mirrors the helper, which exits successfully in exactly those cases,
    so the two cannot disagree and produce a restart loop.
  - Reported as `gro_flags=` alongside `gro_unit=` in `--check`; both stay
    outside `all_critical_state_healthy()` and the exit code.
- **The gap that motivated the amendment.** The unit is `Type=oneshot`
  with `Restart=no`. If it fails at boot — the exact case Stage 2 already
  anticipates, where the network is not ready yet and `install.sh` prints
  "reconcile yeniden deneyecek" and calls `reset-failed` — then nothing
  retried it. It stayed `failed` until the next reboot or `install.sh`
  re-run. The unit file's own comment claimed reconcile retried every five
  minutes, which had been **false since this decision removed that code**;
  that stale comment is corrected in the same change.
- **Placement detail worth knowing.** The repair runs *before* the
  `all_critical_state_healthy()` early `exit 0`, because otherwise a
  healthy system would return before ever reaching it. It is still
  excluded from that function and from the exit code: a GRO failure is
  throughput-only and must not make `--check` report an unhealthy host.
  It is reported as `gro_unit=` in `--check` output.

### DD-17: Nothing persists firewall rules to disk (2026-07-29)

- **Decision/observation:** no `iptables-persistent`, no `/etc/iptables`,
  and `nftables.service` left disabled. The complete rule set is rebuilt
  from scratch on every boot by `docker.service` (its own chains),
  `tailscaled` (`ts-*`) and `docker-tailscale-fw.service` (`MASTER-*`).
- **Confirmed 2026-07-29:** packet counters reset across a reboot, proving
  the rules are new objects rather than a restored dump, and the rebuilt
  set matches the previous one apart from Docker's container-IP churn
  (DD-16).
- **Rationale:** a persisted dump would be a second source of truth that
  could drift from `install.sh`, and would restore stale addresses at boot
  before the helpers had a chance to detect the current ones. Rebuilding
  is slower by roughly a second and always correct.
- **Consequence for failure analysis:** if the firewall helper ever fails
  to run, the host does not fall back to an older policy — it has *no*
  managed policy until the helper succeeds. That is why
  `docker-tailscale-fw.service` failing triggers reconcile via
  `OnFailure=` immediately rather than waiting for the 5-minute timer.

### DD-18: UDP socket buffer ceilings are floored by the installer, and they are a Tailscale setting — not a WireGuard one (2026-07-29)

- **Decision:** Stage 2 writes `/etc/sysctl.d/99-master-stack-netbuf.conf`
  with `net.core.rmem_max` / `wmem_max` set to
  `max(current_value, 16 MiB)`. `rmem_default` is deliberately left alone.
- **v2 realignment (2026-08-06, `v2-12`):** Early v2 had hardcoded
  `7500000` in `99-master-tailscale.conf` after `apt install tailscale`.
  That under-shot the legacy floor and violated M11 ordering. v2 now
  matches this decision again via `apply_udp_netbuf_floor` before the
  Tailscale package install; forwarding stays in a separate conf file.
- **Why it was needed:** on the live host both values were already 64 MiB
  — but from `/etc/sysctl.d/99-nc-kernel.conf`, a **file shipped by the
  VPS provider's image**, not by this installer. Nothing in `install.sh`
  set them. On any host without that file they fall back to Debian's
  default of 208 KB.
- **Who actually benefits — and the mis-attribution that produced this
  entry.** This was first proposed as a *WireGuard* optimization. That was
  wrong, and measurement is what caught it. Kernel WireGuard (what
  `wg-easy` uses) attaches an `encap_rcv` callback to its UDP socket;
  `udp_queue_rcv_one_skb()` hands the packet to that callback **before**
  the socket receive queue is involved, so `rmem_max` never gates its data
  path. The evidence, taken inside the container's netns after 6.19 GiB of
  real peer traffic:

  ```
  Udp: InDatagrams 5074319 ... RcvbufErrors 0  SndbufErrors 0  MemErrors 0
  /proc/net/udp  00000000:FE93 (port 65171 = wg0)  rx_queue=00000000  drops=0
  ```

  The setting matters for **Tailscale**, which is *userspace* WireGuard
  (`wireguard-go`) and does read from a UDP socket: `tailscaled` was
  observed holding `rb14680064` (14 MiB). At Debian's 208 KB ceiling that
  request would have been clamped ~70× smaller, silently costing
  exit-node throughput. Since being a Tailscale exit-node is this host's
  primary function, the finding survived — it just changed owner.
- **Why raising a ceiling is safe here, and why the qBittorrent
  experience does not apply.** `mem_limit`/`cpus` are cgroup ceilings that
  *constrain*: hitting one takes throughput away, which is exactly what
  happened in **M1**. `rmem_max` is the opposite kind of ceiling — it
  allocates nothing and only sets the largest value a process may request
  via `setsockopt(SO_RCVBUF)`. Raising it cannot slow anything down; it
  can only stop clamping. `rmem_default` *is* applied to every socket that
  does not ask for a size, so touching that one would have raised baseline
  memory use across the system — which is why it is excluded.
- **Raise-only, never lower.** The value is computed as a `max()` against
  whatever is already in effect, so a provider that sets 64 MiB keeps it
  and a re-run is idempotent. Simulated across the Debian default, a
  provider 64 MiB, an exact-floor value, and malformed/empty input.
- **Not reconciled, and that is deliberate.** Unlike ethtool flags, a
  `sysctl.d` file survives reboots by construction — the file on disk *is*
  the guarantee, so there is nothing for a 5-minute loop to repair. This
  is the same reasoning as DD-11, applied to a setting that happens to be
  persistent rather than volatile.
- **Known limitation:** `sysctl.d` applies files in lexical order, so a
  provider file sorting after ours that sets a *lower* value would win.
  The `max()` handles the realistic case (provider sets it higher); the
  inverted case is accepted as exotic and is not defended against.

### DD-19: The Tailscale login stays in Stage 2 — reordering it was tried, measured, and reverted (2026-07-29)

`install.sh` has exactly one step that blocks on a human: `tailscale up`
prints a `login.tailscale.com` URL and waits for the browser flow. It sits
in the middle of Stage 2, behind `apt-get full-upgrade` and two package
installs. A user reported it as "the link falls behind, I can't see it; it
only shows up after a very long wait", and a reordering was built and
shipped as `v1.1-1`: TUN check, Tailscale repo, sysctls, package install,
daemon start and login all moved into Stage 1, with `full-upgrade` moved
behind them. **It was reverted the same day.** Keep this entry so the
reordering is not proposed a second time on the same reasoning.

- **What the measurement showed.** On a clean install of `v1.1-1`:

  ```
  19:17:15  Stage 1 begins
  19:17:25  login banner on screen        (+10s, was ~4-6 min)
  19:17:25  control: RegisterReq sent
  19:22:06  control: AuthURL is https://login.tailscale.com/a/...
  ```

  The reorder did exactly what it was designed to do — the script reaches
  the login in ten seconds instead of minutes. It did **not** fix the
  complaint, because **4m41s of the wait is Tailscale's control plane
  taking that long to answer the first `RegisterReq`**, and nothing in
  `install.sh` influences that. The URL reached the terminal in the same
  second `tailscaled` received it, which also disproves the buffering
  hypothesis for good: `tee`'s stdout is fd 5 (`/dev/tty`), glibc
  line-buffers it, and delivery is immediate.
- **The network was eliminated as a cause.** IPv4 and IPv6 both reached
  `controlplane.tailscale.com` in ~25 ms, 1500-byte frames passed `-M do`
  on both stacks (no PMTU blackhole), and the TCP connection to the
  control plane was `ESTAB` with an empty queue the whole time.
  `tailscaled` logged nothing between `19:17:30` and `19:22:06`; it was
  simply waiting.
- **Why it was reverted.** The user's call: the reorder bought ~4-6
  minutes of apt work moved behind the login while leaving the dominant
  ~4m41s untouched, so it did not solve the reported problem.
- **The `RegisterReq` latency is control-plane variance, and a warm-up
  race was ruled out.** A V1 install run 22 minutes later on the same
  host, with the original ordering, produced:

  ```
  19:39:47  Starting tailscaled.service
  19:39:48  health(warnable=warming-up): error: Tailscale is starting.
  19:39:48  StartLoginInteractiveAs("root")
  19:39:48  control: RegisterReq: fup=false
  19:39:53  health(warnable=warming-up): ok
  19:39:54  control: RegisterReq: got response; authURL=true
  ```

  **6 seconds instead of 4m41s** — and note that the original ordering
  issues `LoginInteractive` one second after the daemon starts, *inside*
  the same warm-up window. An earlier draft of this entry claimed the GRO
  block gives the daemon "3-6 seconds to settle" that the reorder removed;
  that is wrong, and this measurement is what disproves it. Both orderings
  log in during warm-up, so warm-up cannot explain the difference. The
  4m41s was Tailscale-side variance, not something either ordering
  caused.
- **What a future attempt would have to beat.** With the control-plane
  latency established as variable and usually small, the only thing left
  for a reorder to buy is the apt time ahead of the login — real on a
  genuinely fresh host, near-zero on a re-install (the V1 run above
  completed Stage 1 in 7 seconds because `full-upgrade` and the packages
  were already current). Measure that on a cleanly reimaged host before
  proposing the restructuring again.
- **Separable ideas that did not cause the revert.** The framed login
  banner (bell + bold-cyan frame closing *before* the URL, so the link is
  the last thing on screen) and the Stage 0 heads-up are independent of
  ordering and could be re-applied on their own. So was the **M11** sysctl
  ordering defect, which the reorder happened to fix as a side effect and
  which the revert reintroduced — it was then fixed on its own in `V1-1`
  by moving the netbuf block ahead of `apt-get install -y tailscale`,
  without any of the Stage 1/2 restructuring.
- **A packaging fact both orderings have to respect.** Debian's
  `tailscale.postinst` runs `deb-systemd-invoke restart
  'tailscaled.service'`, so the daemon starts inside `apt-get install -y
  tailscale`; the script's own `systemctl enable --now tailscaled` is a
  no-op. Verified 2026-07-29: `dpkg configure tailscale` 19:17:24,
  `systemd: Starting tailscaled.service` 19:17:24, `status installed`
  19:17:25. This makes the intuitive "install Tailscale first, tune for it
  afterwards" ordering wrong for anything that must be in place before the
  daemon opens its UDP socket — `net.core.rmem_max` in particular. It does
  not apply to `ip_forward`, which is read dynamically and only needs to
  be set before `tailscale set --advertise-exit-node`.

### DD-24: Network steps get a bounded retry and a mandatory timeout (2026-07-31)

- **Decision:** every network-dependent step in `install.sh` runs through
  `retry_network` — three attempts, an explicit per-attempt `timeout`,
  5s/15s backoff. Applied to `apt-get update`, the three keyring/repo
  fetches, and `docker compose pull`. Not applied to
  `apt-get full-upgrade` or `apt-get install`.
- **The timeout is the point, not the retry** — the reverse of how the
  finding (L8) was originally framed. What prompted it was a Docker Hub
  502 during `docker compose pull`, and a retry does fix that. But
  reading the surrounding code moved the priority: the script runs under
  `systemd-inhibit --what=shutdown:sleep --mode=block` and holds the
  `flock` it shares with `master-network-reconcile`. A hung download
  therefore blocks shutdown *and* prevents the 20-minute reconcile timer
  from running, with no bound at all. The 502 failed loudly and safely —
  install stopped, re-run succeeded. A hang would have failed silently
  and held two locks while doing it.
- **No error classification, deliberately.** The first design sketched
  matching stderr to decide what was retryable. It is unnecessary:
  permanent failures (`manifest unknown`, `unauthorized`, a full disk)
  return within seconds, so three blind attempts cost them roughly 20s of
  backoff and then the same clear error. Only transient faults and hangs
  consume meaningful time, and those are precisely what we want retried
  or bounded. String-matching upstream error text would also be locale-
  and format-dependent — fragile, for no gain.
- **Budgets measured, not guessed** (2026-07-31, netcup host): cold
  `docker compose pull` 10.9s for 885 MB across three registries, warm
  pull 3.2s, `apt-get update` 0.9s, keyring fetches 36–127 ms. Bulk gets
  300s then 180s (~27× the measured cold pull); small fetches 60s then
  30s. A link would have to be ~27× slower than this host for a legitimate
  pull to be cut — and even then the operator gets a timeout message
  naming the budget rather than a silent stall.
- **Why apt transactions are excluded:** `full-upgrade` and `install`
  drive dpkg. Interrupting one mid-transaction and reissuing it is a
  different problem class, and it interacts with the `--force-confdef
  --force-confold` handling. Wrapping them would relocate the risk rather
  than reduce it. `apt-get update` is wrapped because it is genuinely
  idempotent.
- **The Caddy GPG fetch was restructured** rather than wrapped as-is: it
  used to be `curl … | gpg --dearmor`, and retrying the whole pipeline
  would also retry the local dearmor step, which can never be fixed by
  retrying (bad input is bad three times). The download now goes to a
  temp file inside the retry, and `gpg` runs once outside it.
- **All four control-flow paths are verified**, and the design note that
  preceded this entry was wrong to claim otherwise. It said the recovery
  path — transient failure followed by success — could not be tested
  deterministically without a real flaky network. A stub that fails once
  and then succeeds reproduces it exactly. `test/retry_network.bats`
  covers first-attempt success, exhaustion, timeout (asserting `124` and
  that the message differs from an ordinary failure), recovery, and
  argument pass-through. The suite self-skips where GNU `timeout` is
  absent, so it skips on the macOS workstation and runs for real on the
  Debian target — where the full suite passes with zero skips (62 cases at
  the time; 74 after the `M7` coverage correction later the same day).

### DD-37: The interactive Tailscale login recovers by timeout, not by diagnosing the failure (2026-08-02)

The installer used to run a bare `tailscale up` and wait forever. On
2026-08-02 a real install wedged there and nothing in the script noticed.

**The failure.** The daemon generates a nodekey, gets an auth path
(`/a/<id>`) bound to it from the control plane, and long-polls that path.
A *new* registration for the same node — which is exactly what restarting
the installer causes — or completing an *older* link in the browser
invalidates the pending path, and the poll returns `410: auth path not
found`. What makes it unrecoverable is the next line:

```
control: doLogin(regen=false, hasUrl=true)
```

`regen=false`: the daemon retries the **same dead path** forever instead of
generating a new key. So one 410 wedges the login permanently, `tailscale
up` blocks indefinitely, and — the part that misleads the operator —
`tailscale status` keeps printing the dead link as though it were live.
The reported symptom was "I logged in but it is still waiting."

Measured on the host: two separate links, each dead ~13 seconds after being
issued, four 410 events, the install stuck until it was killed by hand.
`tailscale logout` did **not** clear it — the daemon still returned the same
dead URL afterwards. Only `systemctl restart tailscaled` cleared it, which
is why recovery is built on the restart.

**The fix deliberately does not diagnose anything.** Three earlier versions
tried to detect the wedge from `journalctl`, and all three were wrong in
different ways. Each was caught by running the function against the real
journal, not by reading it:

1. *"A 410 appeared, therefore wedged."* Wrong — a 410 is part of the
   **successful** flow too. When the operator completes the browser step
   the control plane retires the auth path, the in-flight poll takes a 410,
   and the daemon immediately re-registers and gets `machineAuthorized=true`.
   All within the same second, measured at 18:12:49.
2. *"A 410 with no recovery after it."* The check was
   `journalctl … | grep -q`, and under `pipefail` `grep -q` exits on first
   match, `journalctl` takes SIGPIPE, and 141 becomes the pipeline's status
   — so a **found** match reported failure. Intermittent, because it
   depended on whether journalctl had finished writing.
3. *"No recovery after the last 410", with no upper bound.* A later,
   unrelated login's success counted as recovery for an earlier wedge.

The direction of the false positive is what settled it: wrongly declaring a
wedge kills a login that is one second from succeeding, restarts the daemon
and forces the operator to authenticate again — the fix would manufacture
the very failure it exists to repair. Three wrong iterations were treated as
evidence that the diagnosis itself is fragile, not that the third attempt
needed a fourth.

**What replaced it is dumber and therefore safer.** If the login has not
completed within `TAILSCALE_LOGIN_TIMEOUT` (300s), for *any* reason, the
daemon is restarted and a fresh link is printed, up to
`TAILSCALE_LOGIN_ATTEMPTS` (3). This covers the wedge and every other stall
class, and its worst failure mode is "the operator was handed a new link".
The retry banner says the previous link is dead and that opening an old tab
will kill the new one, since that is what produces the 410 in the first
place. After three attempts it prints the manual recipe, including the
non-obvious part: **`logout` is not enough, restart the daemon.**

**Verified before shipping.** The retry machinery was exercised against
stub `tailscale`/`systemctl` binaries: a login that never completes
produced two links, two `systemctl restart tailscaled` calls, the
"previous link is void" banner between them, and the manual recipe at the
end. The success path was tested the same way — it returns as soon as
`tailscale up` exits, with **no** restart, and streams the URL to both the
terminal and the log. The live success path itself was exercised on a real
from-scratch install the same day.

> **Amended by DD-42 / Q1-21.** The live `login-state` shape was later
> observed twice with two distinct nodekeys, so early recovery no longer
> requires guessing. The timeout remains the unknown-state fallback; only the
> measured, persistent LocalAPI signature can bypass it.

### DD-42: Persistent Tailscale 410 is classified from LocalAPI, never the journal (2026-08-02)

DD-37 deliberately rejected three journal-based attempts to identify a dead
interactive-login auth path. The rejection remains correct: a 410 also occurs
inside a successful authorization, journal producer/consumer timing caused a
separate SIGPIPE inversion, and an unbounded window let an unrelated later
success satisfy an earlier failure. A false positive restarts a daemon whose
login may be one second from succeeding.

Q1-21 changes the evidence, not that safety rule. A later clean-image R2.5 run
produced two independent failures without an installer restart. The first
nodekey received its link and entered the dead state 27 seconds later; the
second did so after 42 seconds. In both cases `tailscale status --json` exposed
the same simultaneous state: `BackendState=NeedsLogin`, `Self.Online=false`,
empty `Self.ID`, no Tailscale IP and a `Health` entry containing `http 410:
auth path not found`. The admin console showed an offline record because the
browser side had created/authorized one, but the daemon had never received a
usable machine identity. Restarting only tailscaled and issuing a third link
then produced a non-empty node ID/IP and `Running/Online`; the install finished
7/7.

That structured state is now a named classifier. One sample is still not a
decision: the main loop requires three consecutive samples, two seconds apart,
and resets the count on `pending`, `unknown` or successful state. Thus the
known successful transient 410 cannot survive the persistence gate. A
confirmed dead path terminates only the waiting `tailscale up` child and uses
DD-37's existing daemon restart/fresh-link path immediately. The 300-second
timeout remains unchanged for every state that does not match exactly, so
operator thinking time and unknown control-plane delays are not shortened.

Success is also stronger. Exit code zero from `tailscale up` is followed by a
15-second LocalAPI grace and is accepted only with `Running`, online, a
non-empty node ID and at least one Tailscale IP. Failure of that postcondition
uses the same bounded retry instead of allowing the later Stage 2 probe to be
the first place the inconsistency appears.

> **Amended by `Q1-22` (2026-08-02).** The postcondition stays; its *remedy*
> does not. Sending a failed 15-second grace into the bounded retry restarts
> the daemon and demands a second browser authorization — for a login that
> already succeeded, since `tailscale up` returned zero. That is DD-37's
> false-positive class arriving through a different door, and this time the
> door was narrower than the one already behind it: the very next block in
> Stage 2 waits **180 seconds** for the same condition (`tailscale ip -4` plus
> `tailscale_is_online`). Two gates for one condition, and the strict one held
> the destructive remedy.
>
> The goal above — surface the inconsistency here rather than letting a later
> probe be the first to mention it — was right, and is kept: the grace window
> now prints an explicit note when it expires. What changed is that it returns
> **success** and lets the 180-second check adjudicate. The reasoning is that
> a node which will not come online after an accepted login has a connectivity
> problem, not an authentication one; a fresh browser link cannot fix it,
> while the 180-second wait either resolves it or fails with a clear error.
> The 15 seconds is now a fast path, not a ceiling.
>
> Covered by a fourteenth Bats case, mutation-verified: it fails against the
> `Q1-21` behaviour (`status` non-zero, daemon restarted, a second `tailscale
> up` demanded) and passes against `Q1-22`.

Thirteen Bats cases cover the live JSON signature, incomplete and malformed
states, command failure, a completed node carrying a transient 410 line, the
three-sample early restart and a one-sample 410 followed by success with no
restart. The full local wrapper is clean. The real input signature and the
equivalent manual child-termination/restart path are live measurements; the
exact automatic Q1-21 branch remains deliberately unclaimed until a later
fresh authorization run exercises it. At the operator's explicit request the
same installer was exported untagged as an R2.6 manual-test candidate; that
packaging action does not change the pending live-verification claim.

### DD-43: Exit-node and Tailscale SSH are requested by `tailscale up`, then held by `tailscale set` (2026-08-03)

- **Decision:** the interactive login runs `tailscale up --advertise-exit-node
  --ssh` instead of a bare `tailscale up`, and the `tailscale set` call that
  follows gains `--ssh=true` alongside the flags it already carried. Tailscale
  SSH is now part of the node's steady state: `tailscale_prefs_ok()` requires
  `.RunSSH == true`, so the reconcile timer treats a lost `--ssh` as drift and
  repairs it with the same `tailscale set` invocation it already used for
  exit-node/netfilter drift.
- **Why both places, not one.** `tailscale up` runs **only** when
  `TAILSCALE_NEEDS_LOGIN` is 1 — a fresh node, an expired key, or a node
  deleted from the tailnet. On the ordinary re-run against an already-joined
  host it never executes. So it cannot be the only place these preferences are
  set without making them silently optional on every re-install. `tailscale
  set` runs unconditionally and is the idempotent path; `tailscale up` now
  merely asks for the same end state one step earlier.
- **A second reason to name the flags on `up`.** `tailscale up` refuses to
  silently revert non-default preferences: when the current profile has flags
  set that the command line does not mention, it errors and asks the operator
  to re-run mentioning them. On the re-login paths above the profile can
  already carry `--advertise-exit-node`, which a bare `tailscale up` would be
  proposing to drop. Naming the flags removes that failure mode rather than
  adding one.
- **The security trade-off, stated rather than assumed.** `--ssh` makes
  tailscaled answer SSH on the node's Tailscale address itself, authenticated
  by the tailnet's ACL `ssh` block rather than by the host's `authorized_keys`.
  It is reachable only from the tailnet — the same trust boundary that already
  governs every web interface in the bundle — and adds nothing to the
  internet-facing surface, which stays behind the fail-closed firewall. What it
  does change is that tailnet ACL policy, not the host's SSH configuration,
  becomes the thing that decides who gets a root shell. A new tailnet's default
  policy permits `autogroup:member` → `autogroup:self` as root with `check`
  (periodic browser re-authorization). An operator who does not want that must
  narrow the tailnet's `ssh` block; the installer deliberately does not edit
  account-level ACLs.

### DD-45: The firewall helper requires ip6tables instead of degrading toward it (2026-08-03)

- **Decision:** `docker-tailscale-fw` hard-fails at the top when
  `command -v ip6tables` finds nothing, before it takes its lock and before it
  touches a single chain. The three `[[ -n "$bin" ]] || return 0` early
  returns in `ensure_forward_prefix`, `apply_tailnet_guard` and `apply_ipv6`
  are gone, and `apply_ipv6`'s "DOCKER-USER missing → warn and skip" branch is
  now the same hard failure `apply_ipv4` already used.
- **Why:** the helper claimed two contradictory contracts. Four branches
  promised graceful degradation when IPv6 tooling was unavailable, and then
  `check_policy` — `check_ipv4_policy && check_ipv6_policy`, with
  `check_ipv6_policy` returning 1 outright on a missing binary — made the run
  exit 1 anyway. The graceful path could not lead anywhere except the same
  failure, so it bought nothing and cost a reader the time to work that out.
- **Why *require* rather than *skip*.** Stage 2 writes
  `net.ipv6.conf.all.forwarding = 1`. Without ip6tables there is no
  `MASTER-DOCKER`/`MASTER-TS-FORWARD` on the v6 side, so continuing would mean
  IPv6 forwarding enabled with no Tailnet isolation guard behind it — the
  exposure the helper exists to prevent. Failing closed is the only answer
  consistent with the rest of the file. In practice nothing changes: the
  `iptables` Debian package installed in Stage 1 provides `ip6tables`.
- **One branch was provably dead, not merely redundant.** `apply_ipv6`'s
  DOCKER-USER warning could never fire: `ensure_forward_prefix
  "$IP6TABLES_BIN"` runs first and returns 1 — under `set -e`, killing the
  helper — if that same chain is absent.
- **`check_ipv6_policy`'s own `[[ -z "$IP6TABLES_BIN" ]]` guard is deliberately
  kept.** It is **M5**'s remediation ("this must not be masked behind the
  generic policy-drift error") and it has a Bats case that calls the extracted
  function directly. The top-level guard makes it unreachable in production,
  but removing it would delete a security finding's test to save four lines,
  and the suite's function-extraction technique cannot test a top-level guard
  in its place. It stands as an independently verified precondition on the
  function rather than as dead code.
- **Measured, not assumed.** The embedded helper was extracted and run against
  a PATH containing stub `ip`/`iptables`/`flock` and **no** `ip6tables`. New
  behaviour: rc 1 in both `apply` and `--check`, the specific message, and
  **zero `iptables` invocations** — proven by an invocation log the stub wrote.
  Old behaviour under the same conditions: `--check` reached rc 1 only after
  address resolution and an `iptables` call, printing the specific message
  *and* the generic "politika sapmış" line; `apply` installs the full IPv4
  policy first, because the apply order is `ensure_forward_prefix →
  apply_tailnet_guard → apply_ipv4 → apply_ipv6 → check_policy`. The old
  `apply` run could not be driven to completion — the crude `iptables` stub
  answers every `-C` probe with success, which makes `remove_legacy_wide_rules`
  loop forever; that is the stub's defect, not the helper's.
  `./scripts/check-all.sh` clean at 176 cases, M5's case among them.

### DD-50: The installer has one definition of "online", and its waits count time rather than iterations (2026-08-04)

- **Decision:** `tailscale_is_online()` is deleted. Its three call sites in
  Stage 2 now call `tailscale_login_complete()`, which is JSON-backed. Both
  Stage 2 waits are bounded by a wall-clock deadline instead of an iteration
  count.
- **Why the old predicate had to go.** It decided from human-readable output:
  `tailscale status --self | head -n 1`, true when the line was non-empty and
  did not contain the substring `offline`. That is a locale- and
  format-dependent parse standing next to two JSON-based siblings, and it was
  the only one of the three with no test coverage at all.
- **It was not merely fragile — it could say yes when the answer was no.**
  With `BackendState=Starting` the self line prints and contains no "offline",
  so Stage 2's final 180-second gate could pass on a node that was not
  Running. `tailscale_login_complete` requires `BackendState == "Running"`,
  `Self.Online == true`, a non-empty `Self.ID` and non-empty
  `Self.TailscaleIPs`; the `Self.ID` clause is also the signal the surrounding
  code was already trying to infer from the journal for a node deleted in the
  admin panel.
- **Why the loops changed too.** `tailscale_login_complete` wraps
  `tailscale status --json` in `timeout $TAILSCALE_LOGIN_STATUS_TIMEOUT` (3
  seconds). Against a wedged daemon each probe costs seconds rather than
  milliseconds, so `for _ in $(seq 1 90); do …; sleep 2; done` would run for up
  to 450 seconds while its own error message says "180 saniye içinde". Both
  waits now compute a deadline from `SECONDS` — the idiom
  `tailscale_interactive_login` already uses — so the printed durations stay
  true whatever a probe costs. This also removes a smaller pre-existing
  inaccuracy: the old loops were never exactly 60 or 180 seconds either, since
  each probe's own runtime was unaccounted for.
- **Precondition checked, not assumed:** `jq` is in Stage 1's package list, so
  it is present at the first call site, which runs before the interactive
  login.
- **Two things the original audit note got wrong, corrected here.** It claimed
  the change takes three definitions to one; it does not. Reconcile's
  `tailscale_online()` lives in a separately generated script that cannot call
  an installer function, so **two** JSON-based definitions remain in two
  programs, and what is removed is the text-parsing one. The note also missed
  the loop-duration consequence entirely.
- **Reconcile's predicate is deliberately left looser** (`BackendState` and
  `Self.Online` only). It answers a different question — "is this established
  node still online", asked every twenty minutes — rather than "did
  registration complete". Tightening a steady-state health predicate is a
  separate behaviour change with its own blast radius and its own tests.
- **`tailscale status --self` still runs once**, purely to print which node was
  found. That is output, not a decision, and `test/tailscale_online_gate.bats`
  pins that exactly one use survives.
- **Verified by mutation, including the timing claim.** Five mutations were
  applied to install.sh and each was caught: restoring the text predicate and
  using it at the gate, reverting either wait to an iteration-bounded loop, and
  removing the `break` so the success path waits out the deadline. A fifth —
  moving the deadline 30 seconds later while keeping its shape — made the
  wall-clock case fail after ~33 seconds, which is what shows that assertion
  measures the bound rather than passing vacuously. `./scripts/check-all.sh`
  clean at 224 cases.

### DD-51: Stage 2 bounces the tailscaled daemon without bouncing the stack (2026-08-04)

- **Decision:** Stage 2 no longer enqueues dependency-carrying jobs against
  `tailscaled`. `systemctl enable --now tailscaled` became
  `systemctl enable tailscaled` followed by
  `systemctl is-active --quiet tailscaled || systemctl start tailscaled`, and
  the login retry loop's daemon reset became
  `systemctl restart --job-mode=ignore-dependencies tailscaled`.
- **What couples them.** Two drop-ins written later in the same run make
  `tailscaled` the runtime anchor of the whole stack:
  `tailscaled.service.d/98-master-stack.conf` declares
  `Wants=docker-tailscale-fw.service master-compose.service
  master-webdav.service` and `99-caddy-tailnet.conf` adds `Wants=caddy.service`;
  the same four units declare `PartOf=tailscaled.service` back. On a **fresh**
  install neither half exists yet when Stage 2 runs, so this is invisible. On a
  **reinstall** both already exist on disk, and every job Stage 2 enqueues
  against `tailscaled` reaches all four.
- **Two different mechanisms, which is why one fix would not have done.** A
  *start* job pulls the `Wants=` set; a *restart* job propagates through
  `PartOf=`, and that clause lives on the four stack units, not on `tailscaled`.
  Deleting the drop-in would therefore have silenced the first and left the
  second untouched. `--job-mode=ignore-dependencies` suppresses both, which is
  why the restart path needs nothing else.
- **Measured, not reasoned.** On the test host, with the reconcile timer stopped
  and reconcile confirmed inactive so it could not be the cause:
  `systemctl enable --now tailscaled` against an *already active* `tailscaled`
  started `caddy` and `master-webdav` from inactive. The same command returned in
  0 seconds while `master-compose` was still `activating`, so the pulled jobs are
  **not** waited on. And `systemctl restart --job-mode=ignore-dependencies
  tailscaled` restarted the daemon while leaving `caddy`/`master-webdav`
  inactive and `master-compose`'s `ExecMainStartTimestampMonotonic` unchanged.
- **Why non-blocking is the bad news, not the good news.** The pulled units run
  *concurrently* with the rest of the installer. `master-compose`'s `ExecStart`
  (`docker compose up -d --remove-orphans --wait`) and its `ExecStartPre`
  (`master-compose-ipv4`, which rewrites `/root/docker/.env`) take no lock —
  unlike reconcile, which takes `master-stack.lock` with `flock -n` and defers
  with exit 75, and unlike `docker-tailscale-fw`, which has its own separate
  lock. So the installer's own `flock` on `/run/lock/master-stack.lock` does not
  exclude them. A background `docker compose up` against the *previous* version's
  `compose.yaml` therefore overlaps Stage 4 rewriting that file and Stage 5
  running its own compose commands on the same project — the same class as the
  `<id>_<name>` replace-name orphan recorded in `TODO.md`.
- **The case that actually bites is the repair reinstall.** When all four units
  are active, `enable --now` is a no-op for them; that is why every upgrade on
  the test host looked clean. The units are inactive precisely when someone
  reruns the installer *because* something is broken.
- **What the original audit note got wrong.** It named the login retry loop's
  `systemctl restart tailscaled` as the trigger and proposed
  `systemctl stop master-compose.service` before it. Three errors: that line runs
  only when a reinstall *also* needs a fresh login, while the unconditional
  trigger is the `enable --now` that runs on every single invocation; the
  affected set is four units including `caddy`, which is Stage 6, not "Stage 3/4
  units"; and stopping `master-compose` would not have helped, because the
  restart's `Wants=` pull starts it straight back and the other three units are
  not covered at all.
- **The operator recovery hint is deliberately left alone.** The message that
  prints `systemctl restart tailscaled && tailscale up` is advice for a human
  running it with the installer stopped, where pulling the stack back up is the
  entire point. `test/tailscaled_job_isolation.bats` distinguishes the two by
  requiring the guard only on lines whose first word is `systemctl`.
- **Verified by mutation.** Five mutations, each caught by a specific set of
  cases: restoring `enable --now` (cases 2, 3, 6, 7), dropping the job-mode flag
  (4, 8), splitting the restart into a `stop`/`start` pair (4, 8), and removing
  the drop-in's `Wants=` line (1, the case that asserts the coupling still
  exists). A sixth — moving the flag *after* the unit name — was measured on the
  test host and turns out **not** to be a defect: `systemctl` permutes its
  arguments and the job is isolated either way, so the test pins the flag
  reaching `systemctl` in one invocation rather than pinning argument order.
  `./scripts/check-all.sh` clean at 232 cases.

### DD-53: The media-tree ownership repair never dereferences (2026-08-04)

- **Decision:** Stage 4's `find "$DOWNLOADS_PATH/media" \( ! -uid 1000 -o
  ! -gid 1000 \) -exec chown …` now runs `chown -h`.
- **The defect.** `find` defaults to `-P`: it does not follow symlinks, it
  *reports* them. `chown` without `-h` dereferences whatever path it is
  handed. A symlink inside the media tree owned by anything other than
  `1000:1000` therefore satisfied the predicate and redirected the ownership
  change onto its target, anywhere on the host.
- **Measured before the fix, on the test host.** A root-owned
  `tree/innocent.mkv -> /tmp/d3/SENTINEL` left the symlink at `0:0` and moved
  the sentinel from `0:0` to `1000:1000`. After the fix the same fixture
  leaves the sentinel at `0:0`, moves the symlink itself to `1000:1000`, and
  still repairs a genuine `0:0` regular file — so the repair's actual job is
  intact.
- **Reachability was measured, not assumed.** The tree is bind-mounted into
  `qbittorrent` as `/downloads`; `docker exec qbittorrent id` reports
  `uid=0(root)` because the compose service sets no `user:`; and a symlink
  planted from inside the container appears on the host as `lrwxrwxrwx 1 0 0`,
  which is exactly the ownership the predicate selects. `1000` is the uid
  qbittorrent's own process runs under, so the target becomes a host file the
  container can then read or write. The trigger is an installer re-run, which
  this project does routinely.
- **Why `-h` rather than `! -type l`.** Skipping symlinks would leave a
  root-owned symlink in a tree that is otherwise uniformly `1000:1000`, and
  would leave the next reader to rediscover why. `-h` repairs the link's own
  ownership, which is what the loop was always trying to express, and removes
  the dereference as a class rather than excluding one case of it. On a
  non-symlink `-h` is a no-op, so the regular-file path is unchanged.
- **Deliberately out of scope:** `-xdev`. A separate filesystem mounted inside
  the media tree would still be walked. That is surprising but is not the
  same failure — it cannot be aimed at a chosen file — and bounding the walk
  is its own decision with its own blast radius.
- **Verified by mutation.** Three mutations, each caught by the case that
  claims it: dropping `-h`, moving `-h` after the owner spec where it no
  longer guards the first operand, and adding `! -type l` to the predicate —
  the last one confirms the "find selects the symlink" case measures
  selection rather than passing vacuously. The suite stubs `chown` on `PATH`
  and records its arguments, so the cases need no root and change no real
  ownership. `./scripts/check-all.sh` clean at 242 cases.

### DD-55: Every wait that promises a duration now measures one (2026-08-05)

- **Decision:** the four remaining waits whose error message names a number of
  seconds compute a deadline from `SECONDS` instead of counting iterations:
  Stage 2's tailscaled-socket wait, `master-compose-ipv4`,
  `master-network-reconcile`'s address-ready retry, and
  `master-webdav-serve`. This finishes what DD-50 started in Stage 2 and
  DD-52 continued in the firewall helper.
- **The rule, stated precisely.** Not "no `seq` loops" — the invariant is that
  *a loop must not count turns while its message promises seconds*. Several
  `for _ in $(seq 1 N)` loops in this file are correctly iteration-bounded and
  were deliberately left alone: `create_staging_chain` and
  `create_ts_guard_staging_chain` retry on a random-name collision and take no
  `sleep` at all, so turns are the right unit; and the postcondition retries
  after a repair (`tailscale_prefs_ok`, filebrowser health, WebDAV, Stage 7's
  probe) make no duration claim to be wrong about. A survey of all nine
  remaining sites found exactly one that qualified — the socket wait — which
  is why this revision fixes four sites rather than three.
- **Measured, on the two sites that are whole embedded scripts.** Both were
  extracted and run for real against a stub `ip` costing three seconds per
  probe, with their budget rewritten to three seconds. Each exits 1 in three
  to seven seconds and names the bound it honoured; an iteration-bounded loop
  under the same stub takes roughly four times as long, which is the
  separation the assertions measure. Lower bounds are asserted too, so a loop
  that never waited would fail rather than pass.
- **The messages now interpolate the bound** rather than repeating a literal,
  so the number printed and the number honoured cannot drift apart again —
  which is how all four got out of step in the first place.
- **One related loop was found and deliberately not changed.**
  `tailscale_daemon_ready` counts thirty turns around `tailscale status
  --json` with no `timeout` wrapper, so an unresponsive daemon makes each
  probe arbitrarily expensive. Its caller's message claims no duration, so it
  is not this defect; but it is the unbounded-probe half of DD-50's argument
  and is recorded in `TODO.md` rather than fixed here.
- **Two older tests pinned the shapes being replaced** and were updated to
  assert the new one: `reconcile_control_flow.bats`'s address-readiness case
  pinned `ADDRESS_READY_WAIT_SECONDS / 2`, and the new suite's whole-file
  backstop replaced an early draft that banned `seq` outright — which would
  have condemned the four legitimate loops above.
- **Verified by mutation.** Four, one per site, each caught by the case that
  claims it; the whole-file invariant independently caught two of them.
  `./scripts/check-all.sh` clean at 250 cases.

---

## Installer design decisions

The entries below describe the multi-file successor historically released
with `v2-*` version identifiers (see `docs/contract.md` and
`docs/architecture.md`). The active files now live under `Data/`.
They do not apply to the retired single-file monolith, which remains only in
Git history. They are numbered in the same sequence deliberately: a decision
that supersedes an earlier one should be findable next to it, not in a
separate document with its own numbering.

### DD-58: v2 abandons the single-file model — supersedes DD-9 (2026-08-05)

- **Decision:** v2 is a repository tree — one orchestrating `install.sh`,
  two libraries, four templates, four helper scripts and three systemd
  units — rather than a single script that carries its helpers as heredocs.
  DD-9 is superseded for the successor. At the time of this decision, the
  retired monolith kept its single-file model unchanged; DD-9 remains the
  accurate historical record of that file.
- **Rationale:** DD-9's trade-off line predicted this. The embedded scripts
  are invisible to `shellcheck install.sh` and `bash -n install.sh`, which
  is why `scripts/lint-embedded-scripts.sh` had to be written to lint
  string literals. At 5495 lines the mitigation stopped scaling: the file
  had 1179 comment lines removed in `Q1-24`/`Q1-25` partly because nobody
  read it in an editor, and three real bugs (**H1**'s regression, **H5**,
  **H6**) were reachable only through live execution because static review
  could not see into the heredocs. A file per responsibility gets all seven
  helpers under the normal linter with no custom tooling.
- **Replacement delivery model:** `git clone` (or a release tarball of the
  same tree), then `install.sh`. The curl-pipeable single artefact is
  the thing being given up, and that is the real cost of this decision —
  provisioning now needs the repository present on the host.
- **Trade-off accepted:** more files to keep in sync, and a class of bug
  that could not previously exist (a helper referring to a constant the
  installer never rendered). `config/defaults.env` as the single source of
  truth and the hard-error-on-unsubstituted-token rule in the renderer
  exist to bound that class.

### DD-59: The firewall owns two chains, named once (2026-08-05)

- **Decision:** `MASTER-INPUT` holds the host INPUT policy; `MASTER-DOCKER`
  holds the container policy reached through a single jump from
  `DOCKER-USER`. `MASTER-DOCKER-FILTER` is not used. The same two logical
  names are used for IPv4 and IPv6 — the tables are separate, so there is
  no collision — and both are declared in `config/defaults.env` and
  nowhere else. A chain name appearing as a literal in a second file is a
  defect.
- **Rationale:** Two sources proposed names (`MASTER-DOCKER` in
  conversation, `MASTER-DOCKER-FILTER` in `.cursor/rules/`), both as
  examples. The value is cosmetic but it is a single-source-of-truth value:
  the failure it prevents is a helper that creates one chain while the
  verification step looks for another, which fails open — an absent chain
  filters nothing.
- **A third chain was dropped.** `defaults.env` also carried
  `MASTER-TS-FORWARD`, inherited from v1's mangle-table chain. No clause of
  the v2 contract requires it and it was not part of the decided set, so it
  was removed rather than kept in case it turns out to be needed. If the
  firewall phase finds a genuine need for a `FORWARD`- or mangle-table
  chain, that is a new decision with an explicit name.
- **`MASTER-INPUT` is new in v2.** v1 filtered container traffic through
  `DOCKER-USER` but never wrote a host INPUT policy at all, so services
  listening on the host — WebDAV among them — were protected only by what
  they chose to bind to.
- **v2-3 (2026-08-06): `ts-input` must precede `MASTER-INPUT`.** Our
  INPUT jump must not shadow Tailscale's `ts-input` (UDP 41641 / spoof
  guards). `--check` asserts the order when the Tailscale chain exists.
- **v2-16 (2026-08-07): reorder without a gap.** The first
  `ensure_ts_input_precedence` deleted every `MASTER-INPUT` jump and then
  re-inserted it after `ts-input`, leaving INPUT briefly without our
  policy (default ACCEPT risk). Apply now inserts INPUT jumps after
  `ts-input` when present (`activate_named` / `ensure_jump`), and
  precedence repair uses insert-before-delete so a `MASTER-INPUT` jump
  always remains while wrong earlier jumps are removed.
- **v2-3: IPv6 INPUT must allow NDP/ICMPv6.** A terminal DROP of all NEW
  IPv6 (the first `apply_input6` shape) broke neighbor discovery for the
  provider's link-local default (`fe80::1` → `FAILED`), so IPv6 egress and
  Tailscale control-plane Happy Eyeballs paths hung while IPv4 stayed up.
  Essential ICMPv6 types are accepted before the WAN DROP.
- **v2-23 (2026-08-07): oneshot retry + DOCKER-USER wait.** Boot/Docker
  races where `DOCKER-USER` is briefly missing used to fail the oneshot
  once with no retry (`Restart=no`). The unit now uses `Restart=on-failure`,
  `RestartSec=2s`, and `StartLimitBurst=5` / `StartLimitIntervalSec=60`.
  `firewall.sh` waits up to 10s (`DOCKER_USER_WAIT_SECONDS`) for
  `DOCKER-USER` on both iptables and ip6tables before applying
  `MASTER-DOCKER`. No extra timer or recovery script.
- **v2-24 (2026-08-07): also `PartOf`/`WantedBy` `tailscaled`.** A
  Tailscale restart recreates `ts-input` but did not re-run firewall apply,
  so `MASTER-INPUT` ordering was not re-guaranteed. `master-firewall` now
  follows both `docker.service` and `tailscaled.service` stop/restart
  (Compose is never coupled). Expected after **DD-75**: `tailscaled`
  restart → firewall apply only; Caddy/WebDAV stay unless their address
  binding needs refresh.
- **v2-25 (2026-08-07): minimal `--check` content.** Beyond jumps and
  `ts-input` order, `--check` asserts IPv4 `MASTER-INPUT`/`MASTER-DOCKER`
  WAN DROP, WAN wg UDP ACCEPT, and WAN qBit TCP+UDP ACCEPT. Not a return
  to the old multi-flag reconcile surface.
- **v2-32 (2026-08-09): host INPUT no longer `Requires=docker`.** See
  **DD-75**.
- **v2-34 (2026-08-09): stronger invariants.** Exactly one jump, no
  staging leftovers, WAN if drift fail-closed, SSH + IPv6 TS UDP + NS/NA
  in `--check` (still not a reconcile surface).

### DD-60: dnsmasq binds loopback and `tailscale0`, and nothing else (2026-08-05)

- **Decision:** dnsmasq listens on `lo` and `tailscale0` with
  `bind-dynamic`. Not on WAN interfaces, not on ordinary LAN interfaces,
  never on an unbounded `0.0.0.0`, and it serves no DHCP. Records are
  interface-based (`interface-name=…,tailscale0`); the current Tailscale
  IPv4 is never written into the configuration.
- **Rationale for loopback:** the host must be able to resolve its own
  service names, and the installation must be able to verify DNS without
  borrowing a tailnet device to ask from. v1 bound `tailscale0` only, with
  `except-interface=lo`, which made the cheapest possible verification —
  `dig @127.0.0.1` — impossible.
- **Why the address stays out of the file:** `interface-name` resolves to
  whatever address the named interface currently holds, so destroying and
  recreating `tailscale0` requires no file to be regenerated. This is what
  lets **DD-61** leave dnsmasq alone entirely.
- **What a loopback query returns is an expectation, not a measurement.**
  Reading dnsmasq's documentation, `interface-name=NAME,tailscale0` should
  answer with the `tailscale0` address regardless of which interface the
  query arrived on — but this has not been observed on a real host, and the
  whole loopback-testability argument rests on it. It is therefore recorded
  as an acceptance test for the DNS phase, to be run on a clean Debian 13
  target: `dig +short NAME @127.0.0.1` must return the same address as
  `dig +short NAME @${TS_IPV4}`, and that address must be `${TS_IPV4}`. If
  the measurement disagrees — if a loopback query answers `127.0.0.1` or
  `NXDOMAIN` — the loopback listener stops being a test path and this
  decision needs revisiting, not a workaround.
- **Open implementation question, not a decision:** whether
  `systemd-resolved`'s stub listener already holds `127.0.0.1:53` on the
  target host. That is answered by looking at the host during the DNS
  phase.

### DD-61: `refresh-tailnet-config` restarts address-bound units and does nothing else (2026-08-05)

- **Superseded in part by DD-77 (2026-08-09):** host WebDAV no longer
  binds `${TS_IPV4}`; the live restart set is **Caddy only**.
- **Decision:** the helper reads the current Tailscale IPv4 and IPv6,
  compares them with `/etc/master-stack/state.env`, exits successfully
  without touching any service if they match, and otherwise updates
  `state.env` atomically and restarts the units that bind the address
  (originally Caddy and `master-webdav`; after DD-77, Caddy alone).
  Explicitly excluded: regenerating the dnsmasq configuration, restarting
  dnsmasq, restarting the Compose stack or any container, re-applying the
  firewall, cooldown stamps, drift flags, container recovery, and health
  repair of any kind.
- **Rationale:** this is the scope boundary that keeps v2 from regrowing
  `master-network-reconcile`, whose 1821 lines were one third of v1 and
  produced 25 drift flags, a stamp-based cooldown ledger and an image
  digest recovery path — none of which any requirement asked for. The rule
  that makes the small version sufficient is architectural rather than
  disciplinary: only address-bound consumers are restarted, because
  dnsmasq and the firewall are written against the *interface name*
  (**DD-60**) and (after DD-77) WebDAV binds loopback only.
- **Consequence for Caddy:** there is no rendered Caddy environment file.
  The drop-in reads `state.env` directly as its `EnvironmentFile=`, so the
  address exists in one place on disk and the helper has one file to
  update. The cost is that `state.env` must satisfy both `source` in bash
  and systemd's `EnvironmentFile=` parser: plain `KEY=value`, no quoting,
  no spaces around `=`, no expansion.
- **Consequence for a public IPv4 change:** it cannot be solved inside this
  helper without breaking the decision, because it would mean recreating
  containers. That remains an open question with a documented interim
  answer (re-run the installer).

### DD-64: Tailscale address refresh without a long-running watcher (revised 2026-08-07)

- **Decision (v2-26):** Drop `watch-tailnet-addr`. Address updates go through
  `refresh-tailnet-config` only: `WantedBy=tailscaled.service` (restart path)
  plus `refresh-tailnet-config.timer` (`OnBootSec=2min`,
  `OnUnitActiveSec=5min`). Installer disables/removes any leftover watch
  unit and sbin helper on re-run.
- **Context:** The netlink watcher and the five-minute timer both drove the
  same oneshot. Dual paths added always-on process cost for little gain
  once Tailscale restart already re-applies firewall and restarts
  Caddy/WebDAV (`PartOf=tailscaled`).
- **Rationale:** Prefer one refresh owner. Worst case for a silent CGNAT
  readdress without `tailscaled` restart is up to one timer interval before
  Caddy/WebDAV rebind — accepted for a simpler unit graph.
- **Supersedes:** The 2026-08-06 netlink watcher decision (sub-second IP
  change recovery via `ip monitor address`).

### DD-70: Portable export verifies SHA-256 and extracts atomically (2026-08-07)

- **Decision:** `export-installer.sh` records the runtime tarball SHA-256 only
  inside the `.command` (`PORTABLE_ARCHIVE_SHA256`). The launcher checks
  the hash after decode and again on the host before extract. Remote
  install unpacks into a temp directory, then moves the staged runtime into place
  (no `rm -rf` of the live tree until the new tree is ready to move).
  No separate `.sha256` sidecar is written.
- **Context:** A truncated scp/tar could leave the host without a usable
  installer tree mid-sync. An external sidecar duplicated the same digest
  without adding trust (it travels with the same file).
- **Rationale:** Hash catches corruption; staging extract avoids a window
  with no installer on disk. One deliverable keeps the Desktop/app
  surface a single double-clickable file.
- **Trade-off:** Slightly more remote disk during sync. External
  “checksum without opening the launcher” requires grepping
  `PORTABLE_ARCHIVE_SHA256` from the `.command` (or re-exporting).
- **Amendment (v2-64):** Deterministic pack uses `TZ=UTC` mtime
  `2000-01-01` and bsdtar `--no-xattrs --no-mac-metadata` (plus
  `xattr -cr` on the stage). Local `touch -t 197001010000` in TZ east of
  UTC lands before Unix epoch (stored as 0 → Debian “implausibly old”);
  Apple provenance xattrs became `LIBARCHIVE.*` pax keywords GNU tar
  does not understand. Reproducible hash stays; extract stays quiet.
- **Layout amendment (2026-09-02):** Repository and remote runtime files live
  directly under `debian-server-installer/`. The portable archive uses an
  `installer/` staging directory, atomically replaces the dedicated remote
  root, and starts `/root/debian-server-installer/install.sh`.

### DD-68: Stage 7 covers the cheap contract §14 checks (2026-08-07)

- **Decision:** End-of-install verification includes DNS against
  `127.0.0.1` and `${TAILSCALE_IPV4}`, an out-of-domain `REFUSED`, Caddy
  health, WebDAV unauthenticated `401` (direct + `webdav.` host),
  unauthenticated write rejected (`401`/`403`/`405`), public peer
  publishes for wg/qBit, and non-peer UI publishes only on `127.0.0.1`.
- **Context:** Stage 7 previously only checked loopback DNS, health, and
  WebDAV 401 — below contract §14’s success bar.
- **Rationale:** These checks are fast, deterministic, and catch the
  common “install said OK but ports/DNS wrong” failures without needing
  stored WebDAV passwords (authenticated PROPFIND/write remain manual /
  live Tier-3).
- **Trade-off:** Authenticated WebDAV list/write and full Caddy site
  non-5xx for every UI are still not asserted here.

### DD-67: Re-runs skip full-upgrade and unchanged edge/compose restarts (2026-08-07)

- **Decision:** `apt full-upgrade` runs on first install (no `state.env`),
  when `V2_FULL_UPGRADE=1`, or when the operator answers yes to a prompt
  (default **no** on re-run). `apt-get update` and package `install -y`
  still run. dnsmasq/Caddy are restarted only if their rendered files or
  drop-ins changed, or the unit is inactive; Compose `up -d` runs only if
  `compose.yaml`/`.env` changed or fewer than five containers are running.
  Edge `mask`+apt runs only when `dnsmasq`/`caddy` packages are missing.
- **Context:** Every re-run previously paid for a full upgrade and bounced
  the edge and Compose stack even when nothing changed.
- **Rationale:** Matches contract §11 (“no unconditionally expensive
  step”) while keeping first-install freshness and an explicit upgrade
  path.
- **Trade-off:** Operators who want updates on every re-run must answer
  yes or set `V2_FULL_UPGRADE=1`.

### DD-66: Runtime firewall values come from state, not script fallbacks (2026-08-07)

- **Decision:** `master-firewall` requires `CHAIN_*`, `CHAIN_STAGING_PREFIX`,
  and public ports from `state.env` (`${VAR:?}`). Staging chain names are
  `${CHAIN_STAGING_PREFIX}` + `IN-` / `DK-` / `IN6-` / `DK6-`. DNS
  verification loops `SERVICE_NAMES`; wg bridge IPs/subnets live in
  `defaults.env` and are rendered into Compose.
- **Context:** Fallbacks in `firewall.sh` could silently keep an old port
  after the operator changed `defaults.env` / config. `SERVICE_NAMES` and
  bridge literals were declared but not wired.
- **Rationale:** Missing state must fail closed at apply time; a re-run of
  the installer rewrites a complete `state.env`.
- **Trade-off:** Hosts with a pre-v2-17 `state.env` need one installer
  re-run (or a manual state edit) before `master-firewall apply` succeeds.

### DD-65: Edge apt install keeps units masked; quiet the preset noise (revised 2026-08-07)

- **Decision:** Stage 6 **masks** `dnsmasq.service` and `caddy.service`
  before `apt-get install`, writes config/drop-ins, then `unmask` +
  `enable` + `restart`. Apt stdout/stderr is filtered only for the known
  `Failed to preset … is masked` / `deb-systemd-helper` / “static unit,
  not starting” lines (full apt text still appends to the install log).
  `policy-rc.d` is **not** used for this window.
- **Context:** An earlier revision replaced mask with `policy-rc.d` to
  silence apt. That removed the contract’s abort guarantee (§12): a failed
  stage 6 must leave the optional edge units **off** (masked), not merely
  “did not start during postinst”.
- **Rationale:** Mask is the fail-closed primitive the contract already
  documents. Log filtering restores operator clarity without weakening
  abort safety.
- **Trade-off:** Filter patterns are string-matched; a future apt wording
  change could let noise through again — not a safety regression.
- **Follow-up (2026-08-07, `v2-22`):** `retry` passes the command to
  `timeout`, which can only exec PATH binaries. Calling
  `apt_get_install_masked_quiet` through `retry` therefore failed with
  127 on the live host. `retry` now detects shell functions
  (`declare -F`) and wraps them as `export -f` +
  `timeout … bash -c '"$0" "$@"' fn args…`.

### DD-72: Address-bound units wait, fail visibly, and get recovered (2026-08-07)

- **Decision:** Three changes to the Tailscale-address recovery path.
  1. `refresh-tailnet-config` calls `systemctl restart` instead of
     `systemctl try-restart … || systemctl restart …`.
  2. It also calls `recover_failed_bound_units` on the **no-change** path,
     restarting `caddy` / `master-webdav` if they are in `failed`.
  3. The `caddy` drop-in gains `ExecStartPre=$SBIN_DIR/wait-tailnet-addr`,
     `TimeoutStartSec=150s`, `StartLimitIntervalSec=600` and
     `StartLimitBurst=3`.
- **Context:** `try-restart` restarts a unit **only if it is already
  running**. On a failed unit it does nothing *and returns 0*, so the `||`
  fallback was unreachable. Measured on the test host:
  `systemctl try-restart master-webdav.service; echo $?` → `0`, unit still
  `failed`. Separately, `caddy` had no wait for the address: it read
  `{$TAILSCALE_IPV4}` from `state.env`, failed to bind, and retried every
  5 s forever. With no `StartLimit*` it never reached `failed`, so
  `systemctl --failed` stayed empty while the whole tailnet surface was
  down (`NRestarts` observed climbing past 29).
- **Rationale:** The two failure shapes were mirror images. WebDAV waited
  correctly but then exhausted its start limit and stayed `failed` with
  nothing able to resurrect it; Caddy never failed and so was never
  visible. The combination — bounded wait, then visible failure, then
  recovery by the timer that already runs every five minutes — fixes both
  without adding a watcher, a timer, or a service.
- **Why the two waits stay separate:** `wait-tailnet-addr` only answers
  "does an address exist", which is all Caddy needs because it reads the
  value from `state.env`. `webdav.sh` keeps its own in-process wait because
  it needs the address *value* to pass to `rclone --addr`. These are
  different questions, not duplicated code.
- **Trade-off:** Caddy now takes up to 120 s to fail instead of crash-looping
  instantly, and `refresh-tailnet-config` does two `systemctl is-failed`
  checks per five-minute tick. Both are negligible next to a silent outage.
- **Verified live:** a `master-webdav` that had been `failed` for over forty
  minutes was recovered by one `refresh-tailnet-config` run with **no**
  address change. A subsequent `systemctl restart tailscaled` left
  `caddy` at `NRestarts=0` (previously 29 and climbing), containers
  untouched, `systemctl --failed` empty.

### DD-73: `MASTER-INPUT` accepts the Tailscale UDP port itself (2026-08-07)

- **Decision:** `TAILSCALE_UDP_PORT="41641"` is declared once in
  `defaults.env`, written to `state.env`, required by `firewall.sh`
  (`: "${TAILSCALE_UDP_PORT:?}"`), and accepted on the WAN interface in both
  `apply_input4` and `apply_input6`. Stage 0 rejects it as an operator port
  choice. `--check` asserts the IPv4 rule. `refresh-tailnet-config` also
  gains a one-line warning when the tailnet is unusable.
- **Context:** `MASTER-INPUT` carried no rule for Tailscale's own port and
  worked only because `ts-input` sits ahead of it in `INPUT` and accepts
  41641 there. Measured during the `tailscaled` restart test: with no
  netmap, Tailscale removed `ts-input` entirely, and `MASTER-INPUT`'s
  `-i eth0 -j DROP` counted 52 packets while `tailscaled` was still bound to
  `0.0.0.0:41641`. Separately, the node was deleted from the tailnet at
  15:08 and logged `404: node not found` 501 times over four hours while
  `systemctl --failed` stayed empty and every unit reported green.
- **Rationale:** Tailscale reinserts `ts-input` at `INPUT` position 1, so
  the ordering does self-correct and the impact is bounded — a fallback to
  DERP relay rather than an outage. But the correctness of this project's
  chain should not depend on a chain owned by another daemon being present
  and correctly positioned. One additive rule removes the coupling;
  `ensure_ts_input_precedence` stays, demoted from load-bearing to
  belt-and-braces.
- **Trade-off:** One more explicit WAN `ACCEPT`. It duplicates what
  `ts-input` already permits, which is the point: the two are independent
  now. If Tailscale is ever started on a non-default port the constant must
  follow, which is why it lives in `defaults.env` and not in the script.
- **On the warning:** it is a `printf` to stderr, nothing more. It does not
  attempt `tailscale up`, does not retry, and does not gate anything — a
  bats test asserts the helper never calls `tailscale up/set/login`. The
  four-hour silent outage needed visibility, not a repair engine.
- **Verified live:** both chains carry the rule, `--check` passes, and a
  missing `TAILSCALE_UDP_PORT` in `state.env` fails the script closed.

### DD-74: Tailscale stateful filtering stays on, deliberately (2026-08-07)

- **Decision:** `tailscale set … --stateful-filtering=true` is kept.
  Tailscale's own health warning about it in the presence of Docker is
  **expected output on this host**, not a defect to chase.
- **Context:** Tailscale made stateful filtering default-**off** in 1.78
  because it breaks containers that need to reach tailnet nodes, and the
  daemon reports:
  *"Stateful filtering is enabled and Docker was detected; this may prevent
  Docker containers on this host from resolving DNS and connecting to
  Tailscale nodes."*
  The rule it installs is visible in `ts-forward`:
  `-o tailscale0 -m conntrack ! --ctstate RELATED,ESTABLISHED -j DROP`.
- **Rationale:** The warning describes a capability this stack does not use.
  No container needs the tailnet: Docker's resolver is pinned to
  `1.1.1.1`/`1.0.0.1` in `daemon.json`, and none of the five services talks
  to a tailnet peer. Turning the filter off to silence a warning would
  loosen what may leave the host toward the tailnet in exchange for nothing.
- **The one real consequence, accepted:** wg-easy peers cannot reach tailnet
  devices — traffic from the wg bridge toward `tailscale0` is dropped by
  that rule (and by `ts-forward`'s `-s 100.64.0.0/10 -o tailscale0 -j DROP`).
  Reaching tailnet devices over the WireGuard VPN is not a requirement;
  tailnet devices are reached with the Tailscale client. Operator decision,
  2026-08-07.
- **Revisit if:** wg peers ever need to reach tailnet nodes, or a container
  is added that must. Then this is the setting to change first, and the
  contract's §14.2 success criterion must change with it.

### DD-75: Host firewall converges without Docker; address units drop PartOf (2026-08-09)

- **Decision (four changes, one revision):**
  1. `master-firewall.service` uses `Wants=docker.service`, not
     `Requires=`. Host INPUT apply/check always run; `MASTER-DOCKER` is
     applied/checked only when `DOCKER-USER` is present (or Docker is
     active and the wait for the chain succeeds). Docker inactive → skip
     Docker stage without failing the unit; Docker active but chain missing
     after the wait → fail closed.
  2. Stage 5 restarts `master-firewall` / `master-webdav` when
     `state.env`, helper scripts, unit files, or `webdav.env` actually
     changed (`FIREWALL_NEEDS_RESTART` / `WEBDAV_NEEDS_RESTART`), matching
     the Caddy/dnsmasq pattern. Bare `enable --now` on an already-active
     unit is not convergence.
  3. Caddy drop-in and `master-webdav.service` no longer declare
     `PartOf=tailscaled.service`. Firewall keeps `PartOf` for both
     `docker` and `tailscaled` so netfilter order is rebuilt on those
     restarts. Address binding recovery stays on `refresh-tailnet-config`
     (`WantedBy=tailscaled` + 5-minute timer) and `wait-tailnet-addr`.
  4. `tailscale_login` reaps a stuck `tailscale up` child with TERM, a
     bounded wait, then KILL before the next attempt — never an unbounded
     `wait` on a still-running auth process.
- **Why:** Live nrm tests (2026-08-09) showed (a) `systemctl start` on
  active firewall/WebDAV is a no-op so port/state edits never apply on
  re-run, (b) Tailscale restart bounced Caddy/WebDAV while containers and
  IPs stayed put, and (c) Docker boot failure would have blocked host
  INPUT via `Requires=docker` plus a hard `die` when `DOCKER-USER` was
  absent. Rejected on the same evidence: `accept_ra=2`,
  `stateful-filtering=false` (DD-74), treating start-limit as a permanent
  lock, and restoring `watch-tailnet-addr`.
- **Apply order:** host INPUT (IPv4 then IPv6, with `ts-input`
  precedence) first; Docker chains afterward so a missing Docker path
  cannot leave the host without WAN DROP.
- **v2-33 follow-up:** `sed | atomic_write` runs the function in a Bash
  pipe subshell, so `V2_LAST_ATOMIC_CHANGED` is discarded. WebDAV unit
  writes use process substitution (`atomic_write … < <(sed …)`) instead.
  Found on the first live v2-32 re-run: unit on disk updated, PID unchanged.
- **v2-34 follow-up:** `--check` (and apply) fail closed on WAN if drift;
  require exactly one final-chain jump; reject staging-prefix leftovers;
  assert SSH ACCEPT (v4/v6), IPv6 Tailscale UDP, and NS/NA. No automatic
  state rewrite on drift — operator re-runs the installer.

### DD-84: Selective downloads ownership repair + P3 hygiene (2026-08-09)

- **Decision (chown):** Stage 3 `ensure_downloads_tree` only `chown -h` /
  `chmod`s entries whose UID/GID or mode already diverge from
  `${DOWNLOADS_UID}:${DOWNLOADS_GID}` / `0775` dirs / `0664` files. No
  unconditional `chown -R`. Symlink targets are not rewritten (`-h`).
- **Decision (P3):** Drop timer `Requires=` (Unit= is enough); strip stale
  host-WebDAV wording from wait/refresh helpers; Caddyfile matches
  `caddy fmt`; firewall helper drops unused `WAN_IPV4` and `--check`s
  IPv6 `packet-too-big`; export builds a deterministic tarball (`touch`
  epoch + `gzip -n`, stable `PORTABLE_BUILT_AT`). `render_template`
  preserves trailing newlines (so `caddy fmt` stays clean).
- **Why:** Large media trees made every re-run pay a full rewrite; P3 items
  were low-risk noise that dirtied exports and docs without changing
  intent. WG Stage 7 listen/CGNAT checks stay out — operator tracks
  manually.
- **Not doing:** automatic image pull; Watchtower; WG endpoint Stage 7.

### DD-80: `refresh-tailnet-config` waits with `tailscale wait` (2026-08-09)

- **Decision:** Before reading `tailscale0` addresses, the helper runs
  `tailscale wait --timeout=${REFRESH_TAILNET_WAIT_TIMEOUT:-120s}` when the
  CLI supports it. On timeout it soft-exits 0 (timer retries). The unit sets
  `TimeoutStartSec=150s` so systemd does not kill the wait. The 5-minute
  timer and `WantedBy=tailscaled` both stay.
- **Why:** `WantedBy=tailscaled` fires when the daemon process starts, not
  when the interface has an IP. Live logs showed `BackendState=NoState` and
  immediate “IPv4 yok; atlanıyor”, deferring recovery to the timer.
  `tailscale wait` (supported on host 1.102.2) is the upstream tool for
  “backend running + interface + IP”.
- **Not doing:** removing the timer; infinite wait (`--timeout=0`); coupling
  Compose/WebDAV to this path.

### DD-98: Infuse uses Caddy on Tailscale IP:WEBDAV_PORT (2026-08-10)

- **Decision:** Caddyfile WebDAV site is
  `http://webdav.${LOCAL_DOMAIN}, http://{$TAILSCALE_IPV4}:{$WEBDAV_PORT}`
  → `127.0.0.1:{$WEBDAV_PORT}` (both placeholders from `state.env` via
  Caddy `EnvironmentFile=`). Compose stays loopback-only and never names
  the Tailscale address. Refresh-tailnet still restarts only Caddy; a
  re-run that changes `WEBDAV_PORT` sets `WEBDAV_PORT_CHANGED` so Caddy
  restarts even when the Caddyfile text is unchanged.
- **Why:** Infuse on Apple TV wants an explicit port (`61003`) without
  MagicDNS. Binding that port in Caddy (from `state.env`) keeps Compose
  free of Tailscale IPs while matching Infuse UX. Bare `:80` on the TS IP
  is no longer WebDAV (avoids Host=IP confusion with other sites).
- **Rejected (same day):** Compose publish on `${TS_IPV4}:${WEBDAV_PORT}`
  (brief v2-65) — embeds a moving address into Compose and forces
  `docker compose up -d webdav` on every Tailscale IP change.
- **Supersedes:** DD-78’s bare `http://{$TAILSCALE_IPV4}` (port 80) alias.

### DD-85: `wait-tailnet-addr` requires the state IPv4 on the interface (2026-08-09)

- **Decision:** When `TAILSCALE_IPV4` is set in the ExecStartPre
  environment (systemd `EnvironmentFile=state.env`),
  `wait-tailnet-addr` succeeds only if that exact address is present on
  `tailscale0`. If the interface already has a different global IPv4, the
  helper exits `1` immediately with a stale-state message instead of
  waiting out the deadline. If the variable is unset, “any global IPv4”
  remains sufficient.
- **Why:** Caddy binds `{$TAILSCALE_IPV4}` from state, not “whatever is on
  the iface”. The previous any-IP check turned green while Caddy stayed
  `activating` on a poisoned/stale address (measured on `nrm`, 2026-08-09
  resilience pass). Fail-fast hands recovery to the existing
  `refresh-tailnet-config` path (`recover_failed` / IP rewrite + restart)
  without a new watcher.
- **Amends:** DD-72’s “wait only answers does an address exist” for the
  Caddy pre-start helper; refresh still owns rewriting state.

### DD-86: Unusable-tailnet warning names BackendState and Online (2026-08-09)

- **Decision:** `warn_if_tailnet_unusable` logs
  `BackendState=… Online=…` when the node is not both `Running` and
  `Self.Online=true`. Still warning-only; no Tailscale repair.
- **Why:** Live `nrm` resilience pass printed
  `UYARI … (BackendState=Running)` while `Online` was false during a
  `tailscaled` restart — correct trigger, contradictory message. Naming
  both fields makes the line greppable without false “daemon is fine”
  readings.
- **Not doing:** hard-failing refresh; waiting for Online here (`tailscale
  wait` already covers readiness).

### DD-87: Caddy `OnFailure` starts `refresh-tailnet-config` (2026-08-09)

- **Decision:** The Caddy master-stack drop-in sets
  `OnFailure=refresh-tailnet-config.service`. No new timer, watcher, or
  probe oneshot.
- **Why:** After **DD-85**, a stale `state.env` IP fails `ExecStartPre`
  immediately and leaves Caddy `failed` until the next refresh tick
  (up to five minutes, or `OnBootSec=2min`). Wiring failure to the
  existing oneshot updates `state.env` from the interface and restarts
  Caddy in seconds. Refresh still writes the new address *before*
  restarting Caddy when the iface IP differs — it does not resurrect
  Caddy on the stale value.
- **Does not cover:** Silent Tailscale readdress while Caddy stays
  `active` (DD-64 timer / `WantedBy=tailscaled` remain that path).
- **Bounds:** Caddy `StartLimitBurst=3` / `600s` still caps fail loops if
  the tailnet never becomes usable.

### DD-93: Firewall Docker re-apply + install path hygiene (2026-08-09)

- **Decision (three fixes, one package):**
  1. Install `docker.service.d/master-stack.conf` with
     `ExecStartPost=-/bin/systemctl --no-block restart master-firewall.service`.
     DD-75 still allows INPUT without Docker, but a later `docker start`
     must not leave published peer ports unprotected when
     `RemainAfterExit` made `WantedBy` start a no-op. `--no-block` avoids
     a start-post deadlock (`After=docker` waiting while Docker waits for
     ExecStartPost).
  2. `master-firewall --check` requires DOCKER allow rules and asserts
     WAN DROP sits after WAN ACCEPT/RETURN in INPUT and DOCKER chains.
  3. Restore DD-8: merge `dns` into `/etc/docker/daemon.json` via `jq`
     instead of overwriting the file. Restrict `DOWNLOADS_PATH` to
     `/downloads`, `/data`, `/srv/downloads` (and subpaths) before
     recursive ownership repair. Scope `filebrowser` container removal to
     this Compose project / known images.
- **Why:** GPT live review of v2-58 on `nrm` (2026-08-09): healthy runtime,
  but fail-open gap after INPUT-only firewall apply, weak `--check`,
  daemon.json clobber, and over-broad downloads/FB cleanup on shared hosts.
- **Not doing:** disk-persisted iptables, reconcile engine, automatic WAN
  endpoint rewrite, or broadening healthchecks beyond the contract.

### DD-94: The firewall converges; it does not fail with no policy (2026-08-09)

- **Decision (one package, v2-60):**
  1. **Live WAN interface.** `resolve_wan_interface` reads the current
     default route on every apply and check. `state.env` `WAN_INTERFACE` is
     a hint: a mismatch is a warning, not a fatal error, and the live name
     is used. It is deliberately not written back — the value is consumed by
     this script alone at runtime.
  2. **Shape check, not presence check.** `check_chain_shape` replaces
     `check_wan_drop_after_allows`: exactly one WAN DROP per chain, after
     every WAN allow, and no unconditional `ACCEPT`/`RETURN` (no `-i`/`-p`/
     `-m`/`--dport` match) before it. The terminal `-j RETURN` is legal
     because it sits after the DROP.
  3. **Orphan staging purge.** An apply removes leftover staging chains that
     nothing jumps to. A referenced one may be the live policy mid-swap and
     is left alone.
  4. **No Docker ordering on the unit.** `After=`, `Wants=` and
     `WantedBy=docker.service` are removed so host `INPUT` lands as early as
     possible and cannot be delayed by a slow Docker start. `MASTER-DOCKER`
     comes from the DD-93 drop-in; `PartOf=docker.service` is kept as a
     belt-and-braces second trigger. The installer deletes the retired
     `docker.service.wants/master-firewall.service` symlink.
  5. **One bounded watchdog.** `refresh-tailnet-config`, which the timer
     already runs every 5 minutes, restarts `master-firewall` when the unit
     is `failed` or `--check` fails, after `reset-failed` so an exhausted
     start limit cannot block recovery. It runs before the Tailscale wait so
     a dead tailnet does not skip it, and it skips the round while the
     oneshot is `activating`.
  6. **Restart pacing** `RestartSec=10s` / `StartLimitIntervalSec=300` /
     `StartLimitBurst=12`: a transient netfilter or Docker-chain race gets
     ~2 minutes of retries instead of burning 5 attempts in 10 seconds.
  7. **Label-only FileBrowser cleanup.** Container and legacy volume removal
     requires `com.docker.compose.project` to match this project. The
     v2-59 image-name fallback could still delete a foreign `filebrowser`.
- **Why:** the v2-58 review's P1 was that the firewall could fail *with the
  host unprotected*: a renamed NIC or a stale state value aborted the apply
  while `INPUT`'s default policy stayed `ACCEPT`. Converging on the live
  interface, checking chain shape instead of rule existence, and giving the
  unit one bounded recovery path removes that class of outcome without
  persisting rules to disk.
- **Not doing:** disk-persisted iptables (DD-66 stands: the unit is the
  single source of policy), a general reconcile engine (contract §2), a
  `PartOf=docker.service` removal (the drop-in plus PartOf is cheap; a
  duplicate apply is idempotent), automatic `WG_ENDPOINT_HOST` rewrite on
  public-IP change, or watchdog coverage of anything but the firewall unit.

### DD-100: Skip a repo's apt-get update when its source file didn't change (2026-08-23)

- **Decision:** `stage_2` and `stage_4` each write an apt source file
  (`tailscale.list`, `docker.sources`) via `atomic_write`, then only run
  `apt-get update` when `V2_LAST_ATOMIC_CHANGED` is `1` from that write.
  Otherwise they log and skip it.
- **Why this is safe, not a staleness risk:** `stage_1` already runs
  `apt-get update` before either repo file is touched. On a re-run both
  files already exist on disk from the prior run, so they're already
  part of the sources `stage_1`'s update just refreshed — a second
  `apt-get update` moments later, with the file byte-identical, re-fetches
  the exact same index data. On first install the files are new
  (`V2_LAST_ATOMIC_CHANGED=1`), so the update still runs — apt has never
  seen that source before.
- **Why not drop the per-stage updates entirely:** a re-run where the
  operator's Tailscale/Docker apt config genuinely changed (key rotation,
  suite bump) still needs its own fresh index before `apt-get install`
  in that same stage; gating on the write result keeps that case correct
  while eliminating the common no-op case (**R20**: no step is
  unconditionally expensive).
- **Not doing:** consolidating all three `apt-get update` calls into one
  pass after every repo file is written — that would cross stage
  boundaries (Tailscale must be installed in stage_2, Docker in stage_4)
  for a saving only the re-run path has; smallest-change preferred.

### DD-102: Supported-OS matrix — Debian 13 plus the two Ubuntu LTS lines (2026-08-29)

- **Decision:** `require_debian_trixie` became `require_supported_os`,
  accepting exactly three ID/codename/major triples: `debian/trixie/13`,
  `ubuntu/noble/24`, `ubuntu/resolute/26`. The gate sets `OS_ID` and
  `OS_CODENAME`, and the Tailscale/Docker apt repo lines are rendered from
  those — verified live (2026-08-29) that both vendors publish
  `stable/ubuntu {noble,resolute}` and `linux/ubuntu` dists with the same
  URL shape as Debian. The Caddy cloudsmith line is already
  distro-agnostic (`any-version`) and Caddy's own Ubuntu instructions use
  the identical line.
- **Why pinned LTS releases, not `ID=ubuntu`:** same reason trixie was a
  hard gate — the installer's behaviour is only known on releases it was
  written against. Interim releases (25.04/25.10) have 9-month lives and
  add nothing; the two LTS lines cover real hosts through 2029+.
- **Ubuntu-specific guards that came with this:**
  - **ufw:** Ubuntu server ships it (inactive by default). If active, it
    manages INPUT alongside MASTER-INPUT — two owners for one chain.
    stage_0 dies before any mutation; the operator runs `ufw disable`
    first. Fail-closed, consistent with the rest of the tree.
  - **resolv.conf stub:** stage_6 already wrote `DNSStubListener=no` when
    systemd-resolved is active; on Ubuntu `/etc/resolv.conf` is a symlink
    to the stub (`127.0.0.53`), so disabling the stub alone breaks host
    DNS. When the symlink targets `stub-resolv.conf` it is repointed to
    `/run/systemd/resolve/resolv.conf` (resolved's uplink file). No-op on
    hosts without the stub symlink, including Debian. This is a safe
    bootstrap, not a permanent ownership claim: with Tailscale DNS enabled,
    Tailscale may later replace the symlink with its direct-mode MagicDNS
    `resolv.conf`. The resolute reboot test confirmed that steady state keeps
    host and split DNS healthy; forcing Tailscale onto the resolved stub would
    create a resolver loop on this dnsmasq layout and is deliberately not done.
    Confirmed end to end on a fresh v2-76 install (2026-09-10): the stub
    symlink was repointed at install time, Tailscale had replaced the file with
    its own after the reboot, host and split DNS stayed healthy throughout, and
    the post-reboot re-run correctly left the repoint alone because `readlink`
    no longer matches the stub.
  - **apt lock:** Ubuntu enables unattended-upgrades by default, so the
    dpkg lock can be held for minutes right when the installer starts.
    Every `apt-get` call now carries `-o DPkg::Lock::Timeout=60`
    (`APT_OPTS`), waiting on the lock instead of failing instantly;
    `retry` still wraps each call above that.
  - **debian-keyring:** installed only when `OS_ID=debian` — it came from
    Caddy's official Debian install set and has no function on Ubuntu
    (repo signing uses the downloaded cloudsmith keyring). **Dropped on every
    OS in v2-90 (DD-125).**
    - The two `apt_get_install_masked_quiet` installs (dnsmasq, Caddy) never
      received `APT_OPTS`, because `retry` runs functions in a child bash that
      does not inherit arrays. This was fixed in v2-90 (DD-125).
- **Verification status:** bats covers the gate matrix (accept ×3,
  reject ×5 including ID/codename and codename/version mismatches) and
  the repo-line derivation. **Live-verified on both Ubuntu lines:** noble
  24.04.4 on 2026-08-29 and resolute 26.04.1 on 2026-08-30. Both fresh
  installs passed stages 0–7 and independent checks for derived repos, host
  DNS, firewall, DNS/Caddy, WebDAV and 6/6 containers. Resolute additionally
  passed a byte/container/service-stable re-run, Tailscale and Docker restart
  recovery, firewall re-application, and a full reboot with no failed units.
- **Not doing:** distro-conditional package name mapping (the full
  package set — dnsmasq, caddy via vendor repo, apache2-utils, dnsutils,
  ethtool, jq, … — resolves identically on both), and no support for
  derivatives (Mint, Pop!_OS) whose os-release IDs differ.

### DD-103: The installer owns every restart it triggers (2026-09-08)

- **Decision:** `stage_1` exports `NEEDRESTART_SUSPEND=1` next to
  `DEBIAN_FRONTEND=noninteractive`.
- **Why:** Ubuntu ships `needrestart` with an apt `DPkg::Post-Invoke` hook.
  `/usr/sbin/needrestart` detects Ubuntu and, absent an explicit
  `$nrconf{ui}`, sets `$nrconf{restart} = 'a'` — **automatic**. Verified on
  `nrm` (needrestart 3.11, Ubuntu 26.04.1). `DEBIAN_FRONTEND=noninteractive`
  does not disable this: it only suppresses the prompt, and only for
  restart mode `i`, which Ubuntu mode has already replaced.
  The effect is that after any `apt-get install`/`full-upgrade` that pulls a
  library update, a process the installer does not own restarts `sshd`,
  `docker`, `containerd`, `tailscaled`, `caddy` and `dnsmasq` in the middle
  of stages 1, 2, 4 and 6. A `docker` restart there also fires the
  `docker.service.d` drop-in (`master-firewall restart`); a `tailscaled`
  restart fires `refresh-tailnet-config`. Both paths are re-entrant, so
  nothing has been observed to break — but this is the same "two owners for
  one thing" class the ufw gate refuses (**DD-102**), only silent.
- **Why the env var and not a config file:** `NEEDRESTART_SUSPEND` is read by
  `/usr/lib/needrestart/apt-pinvoke` and scoped to the installer's own
  process tree. Writing `/etc/needrestart/conf.d/*` would be the installer
  claiming a host policy it does not own after it exits (**DD-96**).
- **Not doing:** an `OS_ID` branch. Debian does not install needrestart by
  default, and an unread environment variable is a no-op there.
- **Live-measured (`nrm`, fresh Ubuntu 26.04.1, 2026-09-10):** with
  needrestart 3.11 installed and hooked into apt, a first install — which
  forces `full-upgrade` — produced zero needrestart journal records, and every
  service start time was attributable to an installer stage. `sshd` kept its
  boot timestamp throughout, which is the direct evidence: it is the daemon
  needrestart would otherwise have restarted mid-stage.

### DD-104: The OS is recorded, not just detected (2026-09-08)

- **Decision:** `require_supported_os` additionally sets `OS_VERSION_ID` and
  `OS_ARCH`; `write_state` records `OS_ID`, `OS_CODENAME`, `OS_VERSION_ID`,
  `OS_ARCH` and `KERNEL_RELEASE`; `stage_0` calls `detect_os_change`, which
  compares the recorded identity against the live one and, on a mismatch,
  sets `OS_CHANGED=1` and `FIREWALL_NEEDS_RESTART=1`. `OS_CHANGED` forces the
  Tailscale and Docker `apt-get update`, the `systemd-resolved` restart and
  one dnsmasq/Caddy restart, even when the written files are byte-identical.
- **Why:** the tree handles Debian/Ubuntu differences by *probing* the host
  (`command -v ufw`, `systemctl is-active systemd-resolved`, `readlink
  /etc/resolv.conf`) rather than branching on the distro label. That design
  is better than a switch statement and is kept. What it lacked was memory:
  after a `do-release-upgrade` from noble to resolute the repo lines change
  (so **DD-100**'s skip correctly triggers an update), but nothing else
  re-evaluates — the probes happen to still be right, by luck rather than by
  design. Recording the identity turns that luck into a decision, and gives
  a provisioned host a support record that previously had to be read live.
- **Absent record is not a change:** a host installed by v2-73 or earlier has
  no `OS_*` lines. That case logs "no OS record" and leaves `OS_CHANGED=0`;
  the fields are simply added on this run. Claiming a release change there
  would force needless work on every upgrading host.
- **Not doing:** gating on the recorded value, migration logic per release
  pair, or any comparison of non-OS state. `OS_CHANGED` re-runs steps that
  already exist unconditionally — it is a cache invalidation, not the
  reconcile engine contract §2 refuses.
- **Architecture:** recorded, warned about outside `amd64`/`arm64`, and not
  gated on. arm64 is untested, not unsupported; both apt vendors and all six
  images publish it.
- **Live-verified (`nrm`, 2026-09-08):** the v73 host logged "no OS record" and
  gained the fields without claiming a change. Seeding
  `OS_CODENAME=noble`/`OS_VERSION_ID=24.04` then produced
  `işletim sistemi değişmiş: ubuntu/noble/24.04 → ubuntu/resolute/26.04` and
  suppressed **every** skip path — both apt updates ran, and the firewall,
  dnsmasq and Caddy all restarted — after which `state.env` self-corrected.

### DD-105: sysctl drop-ins must sort last, and the runtime value is what counts (2026-09-08)

- **Decision:** the two drop-ins move to `99-zz-master-stack-netbuf.conf` and
  `99-zz-master-tailscale.conf` (paths in `defaults.env`), the v2-73 names are
  deleted on upgrade, and `stage_7` asserts the **live**
  `net.ipv4.ip_forward=1` and warns when `net.core.rmem_max` sits below
  `NET_BUF_FLOOR_BYTES`.
- **Why:** `/etc/sysctl.d` is applied in lexicographic order and the last
  assignment wins. On `nrm` the provider image ships
  `/etc/sysctl.d/99-nc-kernel.conf`, which sorts **after** both
  `99-master-*` files and writes `net.core.rmem_max`/`wmem_max` itself. Here
  it is harmless — it sets 64 MiB, four times the floor, and **DD-18**'s
  `max(current, floor)` correctly preserved it. But the same ordering applies
  to `99-master-tailscale.conf`, which carries `ip_forward`. On a host whose
  provider file sorts later and sets `ip_forward = 0`, the installer would
  apply forwarding at install time (`sysctl -p`, immediate) and lose it at the
  next reboot: an exit node that silently stops forwarding, with every unit
  green and every file on disk correct.
- **Why also assert at runtime:** file placement is a claim, not a
  measurement. A `99-zzz-*` file from a future image would beat the rename;
  reading the live value catches the class rather than the instance. This is
  the same reasoning as `master-firewall --check` (**DD-94**) — assert the
  effect, not the intent.
- **Why delete the old names:** two files writing one key is a second source
  of truth, and the old ones would keep losing the same race.
- **Live-verified across a cold reboot (`nrm`, 2026-09-08):** `/etc/sysctl.d`
  now lists `99-nc-kernel.conf` before `99-zz-master-stack-netbuf.conf` and
  `99-zz-master-tailscale.conf`, and after the boot `ip_forward=1`,
  `net.ipv6.conf.all.forwarding=1` and `rmem_max=67108864` (the provider's
  value, preserved by DD-18's `max()`). The rename only matters across a boot,
  so this is the test that counts.

### DD-106: Fail early, with the real cause (2026-09-08)

Three gates, one rationale: every one of them replaces a late, misleading
failure with an early, named one.

1. **Netfilter backend (`require_nft_iptables`, stage 0).** `firewall.sh` and
   Docker must use the same backend. With the alternatives set to
   `iptables-legacy`, Docker writes nft and the script reads legacy, so
   `DOCKER-USER` appears absent and `wait_for_docker_user` dies after 10 s
   with "Docker çalışıyor ama zincir yok" — the symptom, not the cause. The
   gate names the remedy (`update-alternatives --set iptables
   /usr/sbin/iptables-nft`). `nrm` verified `iptables v1.8.11 (nf_tables)`.
2. **Repo suite preflight (`assert_repo_suite`).** A codename the vendor has
   not published yet fails inside `apt-get update`, after 3 attempts of up to
   `APT_LOCK_TIMEOUT` each, with apt's own wording. One `curl -I` against
   `…/dists/$OS_CODENAME/Release` per repo says which vendor is missing which
   suite. Three attempts, because a transient network failure must not be
   reported as an unpublished release. All six current combinations verified
   to return 200 (2026-09-08).
3. **Rendered-config validation.** `dnsmasq --test -C`, `caddy validate` and
   `docker compose config -q` all run on the target — every binary is present
   there — before the unit that consumes the file is restarted. Previously the
   first sign of a bad render was `systemctl restart dnsmasq` failing under
   `set -e`, or Caddy burning its `StartLimitBurst` (**DD-72**). Both work;
   both say "restart failed" instead of "line 20: bad option". The realistic
   trigger is exactly what **DD-104** is about — a dnsmasq or Caddy version
   bump between OS releases dropping a directive. Verified on `nrm` that both
   validators accept the live configs and reject seeded errors with a line
   number and the offending directive.
- **Caddy is validated with the real environment.** The Caddyfile resolves
  `{$TAILSCALE_IPV4}` and `{$WEBDAV_PORT}` at daemon start; validating with an
  empty environment accepted a meaningless `http://:` site, so the values are
  passed in.
- **Not doing:** `systemd-analyze verify` on the generated units. The units are
  static files in the tree, not renders, and the bats suite already reads them.

### DD-108: A gate may only assert what the host already has (2026-09-08)

- **Decision:** `require_nft_iptables` becomes `check_nft_iptables
  optional|required`. Stage 0 calls it `optional`: it verifies the backend of
  whichever of `iptables`/`ip6tables` exist and, when neither does, logs that
  the check is deferred. Stage 1 calls it `required` immediately after the
  base package install, where the binaries are guaranteed.
- **Why:** DD-106 put the backend gate in stage 0 so a misconfigured host dies
  before any mutation. That was verified on Ubuntu, which ships `iptables`
  preinstalled — and it made **fresh Debian installs impossible**. A minimal
  Debian 13 image has no `iptables` at all (`command not found`, no dpkg
  entry, no `/usr/sbin/iptables*`); the package arrives in stage 1's base set.
  v2-74's gate therefore killed the run at stage 0, before the stage that
  would have installed the very binary it was inspecting. Verified on a fresh
  trixie host on 2026-09-08.
- **The general rule this encodes:** an early gate can only assert properties
  of a host as it *arrives*. A check whose subject the installer itself
  provides belongs after the step that provides it. Stage 0's other gates all
  satisfy this — `root`, `os-release`, TTY, ufw (`command -v` guarded), and
  `flock`, `ip`, `cmp` and `dpkg`, which are `required`/`essential` on both
  distributions and present on any minimal image.
- **Why not simply drop the stage-0 call:** a host whose alternatives were
  deliberately pointed at `iptables-legacy` still has the binaries, and that
  is the case the gate exists for. Checking what is present costs nothing and
  keeps the fail-before-mutation property for every host that can fail it.
- **Both families are checked.** `iptables` and `ip6tables` have separate
  `update-alternatives` links and `firewall.sh` drives both, so the loop
  covers both and names the failing one in the remedy.
- **Not doing:** installing `iptables` earlier just to keep the gate in stage
  0. That would move package installation before the input prompts and the
  lock, for no gain.
- **Live-verified (`nrm`, fresh Debian 13.6 trixie, 2026-09-08):** stage 0
  logged `iptables henüz kurulu değil (Debian minimal); nft arka uç denetimi
  aşama 1'e ertelendi` and the install ran through to stage 7 in 90 seconds.
  After stage 1 both binaries report `v1.8.11 (nf_tables)`. On the second
  run the stage-0 check passes silently, because the package is now present.

### DD-109: A setting whose effect is not guaranteed gets read back (2026-09-10)

- **Decision:** `stage_6` keeps writing `DNSStubListener=no` when
  systemd-resolved is active, and then calls `report_resolved_stub_state`,
  which reads whether `127.0.0.53` is actually bound and logs which way it
  went. Bounded by `RESOLVED_STUB_SETTLE_SECONDS`, because the stub socket
  appears a moment after a resolved restart.
- **Why:** on Ubuntu 26.04 / systemd 259 the key is accepted and ignored — the
  drop-in is present, last in the merge order, and `man resolved.conf` still
  documents it, yet the stub stays up and answering, on a fresh install and
  across a reboot. The installer was reporting success for a step that did
  nothing. Harmless is not the same as true.
- **What was NOT done, and why — a claim of ours that failed its own test.**
  The review's A1 entry also asserted a latent start-order race: that
  `bind-dynamic` "claims every address on the listed interfaces as they
  appear", so a dnsmasq restart while resolved was down would let dnsmasq take
  `127.0.0.53` and lock resolved out. The proposed fix was to replace
  `interface=lo` with `listen-address=127.0.0.1`. Tested on `nrm` before
  implementing: with resolved stopped and `.53` completely free, dnsmasq was
  restarted and **did not take it** — `bind-dynamic` binds the addresses
  *assigned to* an interface, and `lo` carries only `127.0.0.1/8` and
  `::1/128`; `127.0.0.53` is merely reachable through the 127/8 route.
  Resolved then rebound it cleanly. The race does not exist, so the binding
  change would have bought nothing while dropping `[::1]:53` — it was
  withdrawn. `archive/optimization-review.md` §7's protection of `bind-dynamic` now
  rests on a measurement rather than on reputation.
- **Why not delete the ineffective drop-in instead:** it would change behaviour
  on any host where the key still works, and there is no such host to verify
  against — Debian keeps resolved inactive, Ubuntu 26.04 ignores the key.
  Writing it and measuring the result is the honest position until one exists.
- **The general rule:** where the installer cannot guarantee that a setting
  takes effect, it reads the achieved state back and says so. Same principle as
  `master-firewall --check` (**DD-94**) and stage 7's live `ip_forward`
  assertion (**DD-105**): assert the effect, not the intent.
- **Not doing:** failing the install over it. The state is benign here, and a
  gate on a third party's configuration parser would be a new failure mode for
  no gain.

### DD-111: TCP congestion control is BBR, measured before adopting it (2026-09-11)

- **Decision:** stage 2 loads `tcp_bbr` and writes
  `net.ipv4.tcp_congestion_control = bbr` and `net.core.default_qdisc = fq` to
  `99-zz-master-tcp.conf` (values in `defaults.env`), plus a `modules-load.d`
  entry. If the module cannot be loaded, the install continues on the kernel
  default and says so. Stage 7 reads the live value back and warns on a
  mismatch; it does not fail, because this is an optimisation, not a contract
  item.
- **Why — measured on `nrm` (Ubuntu 26.04.1, kernel 7.0.0-31, 2026-09-11):** a
  256 MiB file served by Caddy over WebDAV was downloaded by a MacBook over the
  direct tailnet path (RTT ~59–67 ms, MSS 1228). The runs were interleaved
  (cubic, bbr, bbr, cubic, cubic, bbr), and each run's congestion control was
  confirmed on the live socket with `ss -tin`:

  | | Runs (Mbit/s) | Mean |
  |---|---|---|
  | cubic | 439.9 · 444.8 · 355.1 | 413.3 |
  | bbr + fq | 445.4 · 435.4 · 442.0 | 440.9 |

  An earlier batch adds three more cubic runs: 436.4, 361.1 and 348.4. That
  batch was meant to alternate with BBR, but a harness bug left every run on
  cubic, which the same socket probe confirmed. Across all six cubic runs,
  three hit a burst of about 2,000 retransmissions and lost roughly 20%. None
  of BBR's three runs did. **Peak throughput is the same (~440 Mbit/s, the
  path's ceiling).** BBR's gain is that cubic's loss-driven dips go away.
- **Scope, and a correction to the review:** `archive/os-aware-review.md` D1 said BBR
  would help "an exit node relaying other devices' TCP". It does not. The two
  endpoints of a TCP connection run its congestion control; a router that only
  forwards the flow never does. On this host BBR affects only TCP that ends
  here: Caddy's WebDAV stream to Infuse, qBittorrent's uploads and the web
  UIs. For WebDAV that is the path that matters, and on lossy client networks
  such as a phone or a remote Infuse session, cubic's sensitivity to loss grows
  where BBR's does not.
- **Why adopt it when nothing is broken:** even cubic's worst run (348
  Mbit/s) is 3.5–7× what a 4K HDR remux needs (50–100 Mbit/s), so this does
  not remove a bottleneck. It is adopted because the measured effect was
  consistent, the mechanism is standard, it costs two sysctls in a pattern the
  tree already uses, and a host that cannot load the module simply keeps its
  default. It is an opportunistic improvement, not a fix, and is recorded that
  way.
- **Trade-offs accepted:** mainline `tcp_bbr` is BBRv1. It can take more than
  its share against cubic flows at a shared bottleneck, and it retransmits
  more on shallow buffers. Neither matters on a single-tenant host serving one
  household. qBittorrent uploads become somewhat more assertive toward peers'
  links.
- **Not doing:** replacing existing qdiscs at runtime. `default_qdisc` only
  applies to interfaces created afterwards, so on a re-run `tailscale0` keeps
  `fq_codel` until tailscaled restarts or the host reboots. BBR has paced
  internally since Linux 4.13, so `fq` complements it but is not required.
  Also not doing: per-socket `setsockopt(TCP_CONGESTION)` in any service.
- **Not an OS divergence:** this is a capability probe, not an
  `OS-DIVERGENCE` entry. `tcp_bbr` ships as a module on the Ubuntu 26.04
  kernel and on the Debian 13 kernel (`6.12.107+deb13-amd64`,
  `tcp_bbr.ko.xz`) — both verified live. If a future kernel drops it, the
  install stays on the default, which is what the probe is for.
- **Live-verified on Ubuntu 26.04.1 (`nrm`, 2026-09-11):** before the run the
  host was on cubic with `fq_codel`, and `tcp_bbr` was not loaded. The v2-79
  run logged `TCP: congestion_control=bbr default_qdisc=fq`, stage 7 raised no
  warning, and the run exited 0. Both files were written and no container was
  recreated. **`ss -tin` showed `bbr` on the WebDAV socket Caddy had accepted,**
  so the setting reached the socket that matters. Both qdisc predictions
  held. On the re-run `tailscale0` kept `fq_codel`, because existing qdiscs
  are not replaced. **After a reboot it came up with `fq`,** because
  `default_qdisc` was applied before tailscaled created the interface. After
  the reboot, `modules-load.d` had loaded `tcp_bbr` and the live value was
  still `bbr`. There were 0 failed units, and the post-reboot re-run exited 0
  and recreated nothing. The live-tested code differs from the committed code
  in one comment only. That comment was corrected afterwards so that it no
  longer describes the Debian module as verified.
- **Live-verified on Debian 13.6 (`nrm`, 2026-09-11), fresh install:** the
  preflight found `tcp_bbr.ko.xz` in the 6.12 kernel; stage 2 logged
  `TCP: congestion_control=bbr default_qdisc=fq`; the WebDAV socket Caddy
  accepted ran `bbr`; and after a reboot the module was loaded from
  `modules-load.d`, the live value was still `bbr` and `tailscale0` came up
  with `fq`. Both supported distributions have now had the same measurement.

### DD-113: Security updates install themselves; reboots stay with the operator (2026-09-12)

- **Partly superseded by DD-184 (v2-158):** Tailscale and Caddy now join
  the unattended upgrades at `APT_UPGRADE_TIME`; the "Why the distribution's
  filter" clause below no longer holds for them, and Docker is gone (DD-152).

- **Decision:** stage 1 installs `unattended-upgrades` and writes
  `20auto-upgrades` (`Update-Package-Lists "1"`, `Unattended-Upgrade "1"`)
  and a `52master-stack-unattended` drop-in with `Automatic-Reboot "false"`,
  then enables the `apt-daily` timers. The package's origin filter is left
  at the distribution default: Debian stable + security, Ubuntu security
  (+ESM). Stage 7 reads the effective `APT::Periodic::Unattended-Upgrade`
  back and checks `apt-daily-upgrade.timer`; a mismatch warns, as in DD-111.
- **Why:** the netcup Debian 13 image ships without `unattended-upgrades`
  (Ubuntu's ships with it, enabled). Until now a Debian host got security
  fixes only when the operator re-ran the installer and answered the
  full-upgrade prompt. For a host with sshd, WireGuard and Tailscale on the
  WAN, that gap was the one thing the 2026-09-12 review of the fresh Debian
  host found worth changing; everything else measured was already where it
  should be.
- **Why the distribution's filter:** Docker, Tailscale and Caddy come from
  their own repositories (origins `Docker`, `Tailscale`,
  `cloudsmith/caddy/stable`), which the default `Origins-Pattern` does not
  match. So the daemon that runs the containers, the tailnet daemon and the
  reverse proxy are never upgraded behind the operator's back; a re-run of
  the installer updates them, as before. Debian's default also takes stable
  point-release updates (`label=Debian`), which are conservative by design.
- **Why no automatic reboot:** a kernel update lands but takes effect at the
  next reboot, and `/var/run/reboot-required` says so. Rebooting an exit
  node in the night because a kernel arrived is a policy the operator
  should hold, not the package. The drop-in pins the default so a future
  distribution change cannot flip it.
- **Ubuntu interplay:** on Ubuntu `needrestart` runs in automatic mode during
  unattended upgrades and may restart sshd, tailscaled or dockerd after a
  library update; that was already the case before this change, because the
  package was present and enabled. DD-103 suspends it only for the
  installer's own apt calls. On Debian `needrestart` is absent, so updated
  libraries are picked up at the next service restart or reboot.
- **Not an OS divergence:** the same package and files on both
  distributions; on Ubuntu the install is a no-op and the periodic file
  matches what the image already had. Not adding a mail/report hook,
  `-updates` on Ubuntu, or `Remove-Unused-Dependencies`.
- **Live-verified on Debian 13.6 (`nrm`, 2026-09-12):** a re-run over the
  restored v2-79 host installed the package, wrote both files and changed no
  container; the effective apt-config shows the periodic upgrade on and
  automatic reboot off, and a `--dry-run --debug` lists only the three Debian
  origins as allowed. The first attempt exited 141 at the new read-back —
  `apt-config dump | awk '...; exit'` under `pipefail` — after every stage
  had completed; the read-back now lets `awk` consume the whole stream (see
  `tests/README.md`). Ubuntu: not re-run; the files match what the Ubuntu
  image already carries, and the package is present there by default.

### DD-119: Installer inputs come from one git-ignored file, and that file is the truth (2026-09-14)

- **Decision:**
  - **Where the inputs live:**
    - Every operator input is in `kurulum/kurulum.env` at the repository root:
      SSH host, local domain, downloads path, WireGuard and WebDAV ports, the
      four service accounts and the optional Tailscale auth key.
    - The file is git-ignored and must have mode `600` (or `400`).
    - The template `config/kurulum.env.example` lists every key with no value.
      A test keeps its keys equal to `INPUT_KEYS`.
  - **The launcher:**
    - It stops locally if the file is missing or has a wider mode.
    - It reads `SSH_HOST` and nothing else; no host prompt remains.
    - It sends the file over SSH to `INPUT_FILE`
      (`/run/master-stack/kurulum.env`, declared in `defaults.env`). It
      refuses when that directory is not `tmpfs`.
    - It removes any leftover when it exits.
  - **Stage 0 reads the file right after the root check and deletes it before
    any other gate**, whether or not the file validates. `read_input_file`
    (`common.sh`) never sources it:
    - One `KEY=value` per line, with the value taken literally.
    - An unknown key, a duplicate, a missing key, CRLF, surrounding quotes,
      surrounding whitespace or a malformed line stops the install. The
      message gives the line number and key name, never a value.
    - Every key must be present, and the account keys must be non-empty. An
      empty domain, path or port takes the `defaults.env` value; an empty
      `TS_AUTH_KEY` means the browser login.
  - **Validation and confirmation:**
    - The old prompt rules still apply: user-name character sets, minimum
      password lengths, port conflicts and the `tskey-` shape.
    - The `INPUT_*` variables are unset once mapped.
    - Stage 0 prints a summary without passwords and asks for one `E` before
      `config.env` is written. The re-run questions (full-upgrade, image pull)
      remain.
  - **The file is the single source of truth.** Every run compares each
    account with the file, rewrites only what differs and restarts only that
    container:
    - **WebDAV:** kept when the htpasswd has one line and `htpasswd -vi`
      accepts the password. A rewrite restarts `webdav`, because the secret is
      a bind mount and still points at the replaced file.
    - **Dozzle:** kept when `users.yml` holds exactly one user with that name
      and `htpasswd -vi` accepts the stored hash.
    - **Transmission:** kept when both root-only files hold the file's values.
    - **FileBrowser:** users are exported from a copy of the database. When
      the account differs:
      - the container is stopped;
      - `users import --overwrite` writes the name and hash into a fresh copy,
        keeping the same id;
      - the result is verified and moved in with one `mv`, then the container
        is started.

      Any failure starts the container again on the untouched database. The
      target is the user with the file's name, else the lowest-id admin. Other
      users are left alone.
- **Why:**
  - The user runs a fixed setup and wants a reinstall to need no typed
    answers. Until now the reinstall runbook depended on repeating the same
    answers by hand.
  - This reverses DD-118's choice of the prompt over "a git-ignored local
    secrets file sent over SSH". The two costs recorded there are accepted and
    bounded:
    - Plaintext on the workstation: git-ignored and `600`.
    - A new transfer path: a `tmpfs`-only target, deleted by the installer as
      its first read.
- **Why the file wins over changes made in a UI:** a password changed in
  FileBrowser's UI returns to the file's value on the next run. The user
  agreed to this. The alternative, applying a file change only when the file
  itself changes, would need a stored fingerprint of every password.
- **Measured on `nrm` (2026-09-14, apache2-utils 2.4.68-1~deb13u1, FileBrowser
  v2):**
  - `htpasswd -vi` verifies both a `$2y$` hash (htpasswd) and Dozzle's `$2a$`
    hash from stdin. It returns 0 on a match, 3 on a mismatch and 6 for an
    unknown user.
  - A running FileBrowser holds the Bolt lock: the CLI on the live database
    fails with `Error: timeout`, while `users export` on a copy works.
  - `users import --replace` fails with "the sole admin can't be deleted".
    `users import --overwrite` updates the same id, including a rename, and
    leaves every other field byte-identical.
- **Not doing:**
  - A prompt fallback when the file is absent: two input paths to test and
    document.
  - Validating fields on the Mac: Finder's bash 3.2 would need a second
    validator.
  - Encrypting the file: a password at every run for a file that leaves the
    workstation only as RAM on the server.
- **Consequences:**
  - "No unattended mode" now means one confirmation. The Tailscale login URL
    still needs a browser when no key is given.
  - DD-115's hidden prompt is gone. Its `--auth-key=file:` login and the
    fallback to the browser are unchanged.
- **Verified (2026-09-14):**
  - bats 116 ok, with `bash -n` and `shellcheck` clean.
  - New functional tests: the parser (literal values, eight rejection cases
    and a wrong mode, all deleting the file and never echoing a value),
    `bcrypt_matches`, the WebDAV keep/rewrite, the Dozzle match, the
    Transmission keep, and the FileBrowser sync (match, overwrite that keeps
    other fields and users, failed import that restarts the container on the
    untouched database).
  - Three deliberate code mutations each failed their test.
  - A mid-test `! cmd` or `[[ ]]` does not fail a bats test under macOS bash
    3.2, so the new negative checks use `run !`, `[ ]` or `case`.
  - Live on `nrm`, driving the exported v2-85 `.command` from the Mac under
    `expect`:
    - **Mode 644:** refused on the Mac, before SSH.
    - **Answering `h` at the confirmation:** exit 1; the summary showed no
      password, `config.env` was unchanged, `/run/master-stack` held only the
      lock and the log had no password.
    - **v2-84 → v2-85:** exit 0 in 15 s. The operator's real WebDAV hash was
      saved beforehand and differed from the test file, so the htpasswd was
      rewritten and only `webdav` restarted. Dozzle, Transmission and
      FileBrowser were logged unchanged, and the six container ids plus the
      other five start times were identical. WebDAV answered 401 without
      credentials and 207 with them; the FileBrowser login returned 200.
    - **Same file again:** a full no-op, with every restart skipped.
    - **Three passwords changed in the file:** Dozzle regenerated and
      restarted, Transmission rewritten and restarted, FileBrowser stopped,
      overwritten and started. New passwords: 200, 200, 409 (Transmission's
      RPC session handshake, authenticated). Old passwords: 403, 401, 401.
      `webdav`, `wg-easy` and `unpackerr` were untouched, and there was no
      password in the log or `docker inspect`.
    - **An unknown key (`WEBDAV_PAS`) and an 11-character FileBrowser
      password:** both stopped stage 0 with the line and key named.
      `config.env` and the database were unchanged, and the values were absent
      from the log.
    - **The test passwords restored:** all three services updated and logged
      in again.
    - **Cleanup:** the operator's original WebDAV htpasswd was put back
      byte-identical, `webdav` was restarted, and the saved copy was removed.

### DD-120: WireGuard runs in the host kernel from kurulum/wireguard; wg-easy is removed (2026-09-14)

- **Decision:**
  - **What goes away:** the `wg-easy` Compose service, its bridge network,
    volume definition, `WG_EASY_IMAGE`, `WG_UI_PORT` and `WG_BRIDGE_*`, plus
    the tailnet name `wg.${LOCAL_DOMAIN}` and its Caddy site. WireGuard is
    `wg-quick@wg0` on the host with the same addresses as wg-easy
    (`10.8.0.1/24`, `fdcc:ad94:bacf:61a4::cafe:1/112`, UDP `WG_PUBLIC_PORT`,
    MTU 1420), so existing client profiles connect unchanged.
  - **Inputs:** `kurulum/wireguard/sunucu.key` (the server private key) and
    one wg-easy-format profile per device, `kurulum/wireguard/<device>.conf`.
    The launcher sends them with `kurulum.env` as a tar stream to `INPUT_DIR`
    on `tmpfs`, each file mode-checked. Stage 0 reads the WireGuard folder
    into memory and deletes it before parsing `kurulum.env`, then deletes the
    whole input folder.
  - **Validation in stage 0, before any change:**
    - One `[Interface]` and one `[Peer]` per profile.
    - Well-formed keys and a PSK when present.
    - An IPv4 inside `WG_SUBNET4` that is not the network, broadcast or server
      address, and has no leading zeros.
    - An optional IPv6 in the server's `/112` written the wg-easy way.
    - Unique addresses and private keys, an `Endpoint` port equal to
      `WG_PUBLIC_PORT`, and a safe file name.
    - Messages name the file and the address, never a key.
  - **`ensure_wireguard`, at the end of stage 5, after the firewall:**
    - Installs `wireguard-tools` with `--no-install-recommends`, so no
      `wireguard-dkms`.
    - Checks that every profile's `[Peer] PublicKey` equals `wg pubkey` of
      `sunucu.key`.
    - Derives each peer's public key from its private key, key on stdin.
    - Writes `/etc/wireguard/wg0.conf` (`0600`) with the server key, peer
      public keys, PSKs and `AllowedIPs` only. Client private keys never reach
      the disk, and the file carries no `PostUp`.
    - Restarts `wg-quick@wg0` only when the file changed.
  - **Firewall (`firewall.sh` owns every rule, DD-16/DD-17):**
    - `MASTER-INPUT` accepts, from `wg0`, only TCP to `10.8.0.1` on the three
      UI ports and ping; everything else from `wg0` is dropped (IPv6: all).
    - A new `MASTER-FORWARD` chain at the top of `FORWARD` accepts `wg0` → WAN
      and replies, and drops everything else to or from `wg0`: the tailnet,
      Docker networks, other peers.
    - A new `MASTER-NAT` chain in `nat POSTROUTING` masquerades both WireGuard
      subnets out of the WAN.
    - The WireGuard `ctorigdstport` return leaves `MASTER-DOCKER`; the port
      stays in `MASTER-INPUT`.
    - `--check` asserts the new rules, their order (read from `iptables -S`,
      where `-d` precedes `-i`) and the exact `MASTER-FORWARD` rule count.
  - **UIs over WireGuard:** a second Caddy, `caddy-wg.service` with
    `templates/Caddyfile.wg`, has `admin off` and `default_bind 10.8.0.1`. It
    proxies `http://10.8.0.1:{61002,61006,61007}` to the loopback UIs, with no
    names and no WebDAV. It `Requires`/`PartOf` `wg-quick@wg0` and has no
    Tailscale dependency.
  - **Stage 7:** checks the listen port, that the peer count equals the
    profile count, the `wg0` address, and a non-5xx from each `caddy-wg` port.
  - **No leftover gate:** a stale `wg-easy` container is not detected. The
    operator reinstalls from scratch, and the migration host had it removed by
    hand.
- **Why:** the peers never change, and wg-easy's layers were the source of
  past failures:
  - in-container `iptables-legacy` needing host modules (DD-10);
  - the IPv6 egress drop (DD-71);
  - the fixed bridge IP;
  - the first-run web setup (DD-12/DD-22).

  The tunnel itself was already the host kernel module; only the management
  layer changes.
- **Why a second Caddy and not the tailnet one:** Caddy refuses to start when
  any listener cannot bind, and the tailnet Caddy binds the Tailscale address.
  One process would take the WireGuard path down whenever Tailscale is down,
  which is exactly when the user wants the backup path.
- **Why no tailnet over WireGuard (the user's call, 2026-09-14):** it would
  need NAT to `tailscale0`, and a lost device would become a tailnet member
  with this node's rights. `ts-forward` already drops new connections into the
  tailnet from other interfaces; `MASTER-FORWARD` is a second layer.
- **Measured on `nrm` (2026-09-14):**
  - The OpenSSL 3.5 X25519 derivation equals `wg pubkey`, and macOS LibreSSL
    3.3.6 cannot derive, so key checks run on the server.
  - wg-easy v15's client template is `Address = <v4>/32, <v6>/128`, `DNS`,
    `MTU`, and `[Peer]
    PublicKey`/`PresharedKey`/`AllowedIPs`/`PersistentKeepalive`/`Endpoint =
    host:port`.
  - `caddy validate` accepts the `Caddyfile.wg` shape, and `caddy adapt` shows
    listeners `10.8.0.1:<port>`.
  - Docker leaves the `FORWARD` policy `ACCEPT` here because forwarding was
    already on.
  - `wireguard-tools` recommends `wireguard-dkms`.
- **Rollback:** the `docker_wg_easy_data` volume is kept. Disabling
  `wg-quick@wg0` and `caddy-wg` and re-running v2-85 brings wg-easy back with
  the same keys.
- **Verified (2026-09-14):**
  - bats 119 ok, with `bash -n` and `shellcheck` clean. The new tests cover
    input parsing in wg-easy's format, thirteen rejection cases that never
    echo a key, `wg0.conf` rendering (public keys only, restart only on
    change, a foreign server key stopping before the file changes), firewall
    rule presence and order, the `MASTER-FORWARD` count and order checks, and
    the `caddy-wg` wiring. Four deliberate mutations each failed their test.
  - **Migration on `nrm`:**
    - The four device profiles were generated from wg-easy's database into
      `kurulum/wireguard/` without printing a key.
    - Each profile's derived public key, PSK and server key matched the
      running wg-easy peers, and the interface key matched `sunucu.key`.
    - `docker rm -f wg-easy` (volume kept).
    - The exported v2-86 `.command` then ran with the operator's own
      `kurulum/` folder, never opened. That night the node had been deleted
      from the tailnet (00:52 CEST); the auth key in the file logged it back
      in during stage 2, and it kept its Tailscale IP.
    - Result: exit 0 in 20 s. `wg0` listened on 61001 with 4 peers, `wg0.conf`
      was `0600` with one `PrivateKey`, and `caddy-wg` listened on the three
      `10.8.0.1` ports. `--check` passed, `MASTER-FORWARD` was first in
      `FORWARD`, the input folder was gone and the log held no key material.
  - **A temporary runtime peer in a network namespace** (`wg set`, never
    written to a file):
    - Allowed: ping `10.8.0.1`; Dozzle 307, Transmission 401 and FileBrowser
      200 on `10.8.0.1`; IPv4 and IPv6 internet egress, seen as the WAN
      addresses.
    - Blocked: SSH to `10.8.0.1` and to the WAN address, WebDAV on the TS IP,
      tailnet Caddy, dnsmasq, the WebDAV container's bridge IP, an online
      tailnet device (reachable from the host itself) and another peer.
    - The peer and the namespace were removed afterwards.
  - **A second run with the same folder:** a full no-op; every account, the
    firewall, WireGuard, dnsmasq, Caddy and `caddy-wg` were unchanged, and no
    container or unit start time moved.
  - **A reboot:** every unit active and none failed, Tailscale online, `wg0`
    with 4 peers, `caddy-wg` on its three ports, `--check` passing with
    `MASTER-FORWARD` first, and the UIs, DNS and WebDAV (401) answering.
  - **A real device** (one of the four migrated profiles, unchanged on the
    device) connected, handshook and opened Dozzle at
    `http://10.8.0.1:61002`, confirmed by the user.
  - **Not verified:** a fresh install on a bare Debian host with these
    inputs.

### DD-122: container-backup is retired; kurulum/ is the only thing to keep (2026-09-14)

- **Note (DD-128, 2026-09-14):** `kurulum/` now also holds settings pulled by
  `ayarlar.command` (WireGuard, qBittorrent). This is a narrow snapshot the
  installer restores where absent, not a container backup.

- **Decision:** `container-backup.command`, its worker
  `dev/container-backup-remote.sh`, `docs/container-backup.md` and
  `tests/backup-roundtrip.sh` are removed. A test fails if any of them
  returns. `/backup/` stays Git-ignored so old archives cannot be committed;
  nothing reads them.
- **Why:** since v2-86 the backup had nothing left to carry. It saved one file
  per service (DD-114), and every one of them now comes from the installer:
  the accounts from `kurulum.env` (DD-119), the Transmission preferences from
  the installer (DD-118), and the WireGuard keys and peers from
  `kurulum/wireguard/` (DD-120, DD-121) instead of `wg-easy.db`. A reinstall
  from `kurulum/` produces the same host. The user keeps that folder on the
  workstation and asked for the tool to go.
- **Not doing:** a replacement that archives `kurulum/`. The user keeps the
  folder on the workstation and does not want it copied elsewhere.
- **Supersedes:** DD-112 and DD-114 (the tool they describe no longer exists).

### DD-123: WireGuard changes are applied the kernel WireGuard way, without a restart (2026-09-14)

- **Decision:** when `wg0.conf` changes and `wg-quick@wg0` is running with the
  same `Address` and `MTU`, the installer applies it with `wg syncconf wg0
  <(wg-quick strip wg0)`. That covers adding or removing a peer, a PSK, the
  listen port and the server key. The interface is restarted only when it is
  not running, when `Address` or `MTU` changed (the settings only `wg-quick`
  applies), or when `syncconf` fails. An empty `wg-quick strip` is never
  passed on: syncconf would remove the key and every peer.
- **Why:** this is how kernel WireGuard is meant to be changed, and the user
  asked to follow the native protocol rather than wg-easy. v2-86/87 restarted
  the interface on any change, dropping every connected device and restarting
  `caddy-wg` (`PartOf`) just to add one `[Peer]` block. `syncconf` updates
  only what differs, so existing sessions and handshakes stay up.
- **How the WireGuard model maps (for the record):** the server has one key
  pair. Every device has its own random key pair, unrelated to the server's.
  The device profile carries the server's public key, and the server's
  `wg0.conf` carries one `[Peer]` block per device (its public key, PSK and
  `AllowedIPs`). Adding a device adds such a block; nothing is derived from
  the server's private key.
- **Verified:** bats covers the live path, a no-op, a failed syncconf falling
  back to a restart, an empty strip output never reaching syncconf, and an MTU
  change restarting. Two deliberate mutations each failed the test.
- **Live on `nrm` (v2-88, the operator's folder):**
  - The temporary peer `deneme` was removed from `WG_PEERS`. The run logged
    the change as applied live and the unlisted-profile warning for
    `deneme.conf`, and went from 5 peers to 4, the other four unchanged.
  - `wg-quick@wg0` and `caddy-wg` kept their start times. `master-firewall`
    restarted because the version change rewrote `state.env`, as on every
    version bump.
  - After `deneme.conf` was deleted, a further run reported WireGuard, the
    firewall, dnsmasq, Caddy and `caddy-wg` unchanged.

### DD-124: The server generates and owns WireGuard peers; wireguard.command manages them (2026-09-14)

- **Amended by DD-128 (2026-09-14):** the server stays the source of truth
  while it lives, but `ayarlar.command` pulls `wg0.conf` and the profiles into
  `kurulum/`, and a fresh install restores them. A reinstall then keeps the
  key and peers, instead of "nothing sent, new key".

- **Decision:**
  - `/etc/wireguard/wg0.conf` on the server is the WireGuard source of truth.
    The installer writes only its `[Interface]` part: the server key is
    generated with `wg genkey` when the file is missing and kept afterwards,
    together with every `[Peer]` block.
  - Peers are added and removed on the server by `master-wg`, installed to
    `/usr/local/sbin`. It generates the keys and PSK with the `wg` tools,
    allocates the next address, stores the device profile in
    `/etc/wireguard/clients/` and applies the change with `wg syncconf`
    (DD-123). A failed apply is rolled back, and it shares the installer's
    lock.
  - `wireguard.command`, at the repository root, is the operator's menu: list,
    add (name, DNS, keepalive, MTU), remove, show QR. It calls `master-wg`
    over SSH with `%q`-quoted arguments, prints the QR code and saves the
    profile to `kurulum/wireguard/<name>.conf` (`600`). It reads only
    `SSH_HOST` from `kurulum.env` and refuses a server running another
    version.
  - Removed: `WG_PEERS`, `WG_CLIENT_DNS`, `WG_CLIENT_KEEPALIVE` and
    `WG_CLIENT_DNS_OVERRIDE` in `kurulum.env`; profile parsing, validation and
    regeneration in the installer; sending `kurulum/wireguard` to the server;
    and the launcher's fetch-back. The DNS and keepalive defaults moved to
    `defaults.env` as prompt defaults (keepalive 21, the user's value).
- **Why:** the user wanted peer management to work the way WireGuard is
  administered natively, easy to add and remove, with nothing secret sent to
  the server: "the server generates, we take it". Each device profile carries
  its own DNS, keepalive and MTU, which are client-side settings the server
  never uses. Keeping a workstation folder as the truth (DD-120/121) would
  have made the installer overwrite per-peer choices or require sending keys
  up.
- **Trade-off (accepted by the user):** a reinstall generates a new server key
  and starts with no peers; devices are added again with the menu. The copies
  in `kurulum/wireguard/` are for re-importing on a device, not for rebuilding
  the server. `nrm` is a test host and its old peers were not carried over.
- **Also fixed while testing:**
  - `state.env` now quotes `WG_CLIENT_ALLOWED_IPS`: its space made `source
    state.env` run `::/0` as a command, which would have broken `master-wg`
    and `master-firewall`.
  - `master-wg list` used a helper that overwrote the loop's `line` variable,
    losing the next peer's name.
- **Supersedes:** DD-121, and DD-120's input model (the kernel interface,
  firewall and `caddy-wg` parts of DD-120 stand).
- **Verified:** bats 120 ok, with `bash -n` and `shellcheck` clean. Functional
  tests run the real `master-wg` against PATH stand-ins for `wg`, `wg-quick`,
  `systemctl`, `flock` and `qrencode`. They cover: add (keys generated
  server-side, profile `0600` with the asked DNS/keepalive/MTU, next address,
  live apply), list, profile, QR and version; eight rejected inputs and a
  duplicate that change nothing; removal of exactly one block and reuse of its
  address; rollback of a failed apply; an empty strip never reaching syncconf.
  `ensure_wireguard` is covered for a first install, a re-run that keeps the
  peers byte for byte, a live port change, an MTU restart and a missing server
  key. Three deliberate mutations each failed their test.
- **Live on a freshly reset `nrm` (Debian 13), with the operator's `kurulum/`
  folder:**
  - The exported v2-89 `.command` installed from bare metal: exit 0 in about a
    minute. The auth key logged in to Tailscale, a server key was generated,
    `wg0.conf` held `[Interface]` only (`0600`), `master-wg` answered its
    version, `--check` passed, and neither password nor auth key reached the
    log.
  - `wireguard.command`, driven under `expect`:
    - `test1` with the defaults got `10.8.0.2`: DNS `1.1.1.1,
      2606:4700:4700::1111`, keepalive 21, MTU 1420.
    - `test2` with DNS `9.9.9.9, 149.112.112.112`, keepalive 0 and MTU 1380
      got `10.8.0.3`.
    - Both printed a QR code and saved a `600` profile to
      `kurulum/wireguard/`.
    - A second `test1` was refused. The list showed both; the QR display
      re-fetched a profile.
  - The fetched `test1` profile, used as a client in a network namespace:
    handshook and the list showed its transfer. It reached ping, the three UIs
    and the internet over IPv4 and IPv6, and was refused SSH, WebDAV on the TS
    IP, tailnet Caddy and the other peer.
  - Removing `test2` from the menu deleted its block, its server profile and
    the local copy.
  - A re-run with the same folder restarted no unit and no container and left
    `wg0.conf` byte-identical, with `test1` kept.
  - After a reboot every unit was active and none failed, `test1` was still
    there, `--check` passed with `MASTER-FORWARD` first, and the UIs answered.
  - `test1` was removed at the end: the server has no peers and
    `kurulum/wireguard/` is empty.
- **Real devices (2026-09-14):**
  - The operator added `pppp` (`10.8.0.2`) and this Mac, `mmmm` (`10.8.0.3`),
    from the menu. Both handshook and passed traffic.
  - On the Mac, over the tunnel:
    - Egress used the server's IPv4 and IPv6, and the MTU of 1420 held.
    - DNS did not leak: Tailscale's resolver forwards to the tunnel's `1.1.1.1`.
    - The three UIs answered on `10.8.0.1`.
    - These stayed closed when bound to the tunnel interface: SSH on all three
      addresses, WebDAV, tailnet Caddy, dnsmasq, another tailnet node, the other
      peer and the UIs over IPv6. The `wg0` DROP counters rose.
    - With Tailscale also up, the `*.ayc` names and WebDAV kept working.
  - Speed to public test sites was 120–210 Mbit/s through the tunnel against
    265–407 Mbit/s direct. The server CPU stayed about 97% idle, so the limit
    was the server's path to those sites. The Mac-to-server measurement under
    "Failure tests" below replaces it.
- **Known limit, kept by choice:**
  - `SSH_HOST` points at the server's public IP. While the Mac itself is on
    the full tunnel, that IP is routed into `wg0`, where SSH is dropped, so
    `wireguard.command` times out.
  - The operator switches WireGuard off on the Mac before using the menu.
  - A hint, a Tailscale fallback or SSH over `wg0` were offered and declined.
- **Failure tests on `nrm` (2026-09-14), with this Mac on the tunnel:**
  - Setup:
    - Each disruptive step ran as a transient `systemd-run` script on the
      server, so a lost SSH session could not leave it half done. A Mac loop
      polled `10.8.0.1` and the internet meanwhile.
    - Temporary pieces (a sender on `10.8.0.1:5201-5205`, its `MASTER-INPUT`
      accept rule, the scripts and a safety timer) were removed afterwards, and
      `--check` passed.
  - **Throughput, Mac to server** (zeros, no compression; outside the tunnel
    over SSH on the Mac's physical interface):

    | | Through `wg0` | Outside the tunnel (SSH) |
    |---|---|---|
    | Download, 1 stream | 461–498 Mbit/s | 237–241 Mbit/s |
    | Download, 4 streams | 386–465 Mbit/s | 495–526 Mbit/s |
    | Upload, 1 stream | 48 Mbit/s | 51 Mbit/s |

    - With 4 streams the server was 75–80% idle, with the `wg-crypt-wg0`
      workers spread over all 4 cores. The Mac was only about 40% idle.
    - The ceiling is the Mac's WireGuard client and the home line (about 50
      Mbit/s up), not the server.
    - Public test sites began answering 429 and were dropped as a
      measurement.
  - **`wg-quick@wg0`:**
    - `restart`: `caddy-wg` restarted with it (`PartOf`). Both peers came
      back, `wg0.conf` was unchanged, and `--check` passed. The Mac recovered
      in about 15 s, the WireGuard handshake retry.
    - `stop`: `caddy-wg` stopped with it, and the Mac's internet stopped too:
      the client fails closed.
    - `start`: `caddy-wg` came back through its `WantedBy`, and the Mac
      recovered at once.
  - **`systemctl restart docker`:**
    - Containers were healthy again in 11 s; `caddy-wg` answered 502 in
      between.
    - `master-firewall` re-applied itself (`PartOf`), with `MASTER-FORWARD`
      still first and `DOCKER-USER` jumping to `MASTER-DOCKER`.
    - Transmission's bridge IP moved from `.5` to `.4` (DD-16). Bridge IPs
      were unreachable over WireGuard before and after.
    - The Mac's poll with a 1 s timeout showed scattered timeouts around this
      step, some before the restart. They did not recur: 40/40 polls
      succeeded afterwards and ping loss was 0%.
  - **`tailscaled` stopped for 3 min 37 s:**
    - The WireGuard path held: 109/109 Mac polls got the three UIs and
      internet egress.
    - `caddy-wg`, `wg0`, dnsmasq and Docker stayed active, and the firewall
      rules and `--check` held. `master-firewall` showed inactive through
      `PartOf`, but has no `ExecStop`, so its rules stayed in place.
    - Tailnet names, WebDAV and DNS on the TS IP were unreachable, as
      expected.
    - `tailscaled` came back online in 1 s, and names, WebDAV and DNS
      answered at once. Caddy was not restarted: its sockets on the TS IP
      stayed bound.
    - `master-firewall` re-applied with `MASTER-FORWARD` first, the exit node
      was offered again and no unit failed.
  - **Open:** `pppp` had not handshaken since the `wg0` restart. Its tunnel was
    probably off or the phone asleep; the user checks it on the phone.

### DD-125: A smaller footprint — no Docker recommends, no kept apt downloads, no debian-keyring (2026-09-14)

- **Docker part superseded by DD-152 (2026-09-19):** Docker is not installed at all.

- **Context:** after a fresh v2-89 install the operator saw disk use grow by
  about 1.7 GB.
  - Measured on `nrm`: 672 MB of new packages, 421 MB of images and a 303 MB
    apt cache holding all 73 downloaded `.deb` files.
  - Of the packages, about 200 MB served nothing in this stack: Docker's
    recommends (`git` with `perl`, `docker-ce-rootless-extras`) and
    `docker-buildx-plugin`.
  - The rest of the gap in the provider panel was freed but untrimmed blocks,
    released by the weekly `fstrim.timer`.
- **Decision:**
  - **Docker:** installed with `--no-install-recommends` as `docker-ce
    docker-ce-cli containerd.io docker-compose-plugin apparmor pigz`.
    - The stack never builds images and never runs rootless, so buildx, git
      and rootless-extras go.
    - Two recommends the runtime uses are named explicitly. `apparmor`
      provides the parser for the `docker-default` profile when the kernel has
      AppArmor on. `pigz` speeds up layer decompression.
  - **apt downloads:** `APT_OPTS` carries `APT::Keep-Downloaded-Packages=false`,
    so every `.deb` the installer downloads is deleted once installed.
    Nothing else in the cache is touched (DD-96), and unattended-upgrades is
    not reconfigured.
  - **debian-keyring:** no longer installed. The Caddy repo is verified by
    its `signed-by` cloudsmith keyring, so the package did nothing. This
    removes the tree's only real `if OS = debian` branch (`caddy-keyring-pkg`
    in the OS-divergence inventory).
  - **Fix found on the way:** `retry` runs a shell function through
    `export -f` and `bash -c`, and arrays do not cross into that child.
    - As a result, `apt_get_install_masked_quiet` (dnsmasq, Caddy) had run
      with an empty `APT_OPTS` since DD-102: no lock timeout, and now no
      download cleanup.
    - The callers now pass `"${APT_OPTS[@]}"` as arguments, and a bats test
      runs the helper under `retry` with a mocked `apt-get`.
- **Not doing:**
  - Switching Docker from the containerd image store back to `overlay2`. It
    would drop about 114 MB of compressed layers, but go against the Docker 29
    default.
  - Removing anything from existing hosts. A re-run installs nothing new and
    removes nothing, so buildx, git or debian-keyring already on a host stay
    until the operator removes them.
- **Trade-off:** `apparmor` and `pigz` become manually installed packages in
  apt's view. Both were already present, from the image or through Docker.
- **Verification:**
  - bats 122 ok. `shellcheck -x` is clean.
  - Deliberate mutations each failed a test: recommends back, the apt option
    dropped, buildx back, a masked-quiet caller without `APT_OPTS`.
  - **Live on `nrm` (Debian 13), with the scratch test inputs and the real
    account files saved and restored:**
    - Fresh-path simulation:
      - `apt-get clean`.
      - Docker, containerd, compose, buildx, rootless-extras, git/perl, pigz,
        Caddy, dnsmasq and debian-keyring purged, `/var/lib/docker` and
        `/var/lib/containerd` removed.
      - The Caddy repo list and keyring deleted.
    - The first v2-90 run stopped at stage 7 on a transient registry error
      (`error from registry: retry-after …`) while pulling. A plain re-run
      finished with exit 0.
      - That run showed the two masked-quiet installs without the options: 4
        `.deb` files left, and apt history lines without `-o`. This led to the
        fix above.
    - After the fix, purged again, one run with exit 0 in 41 s:
      - apt's "Recommended packages" listed rootless-extras, git and buildx as
        not installed.
      - All three apt history lines carried both options, and the cache held
        0 `.deb` files.
      - The cloudsmith InRelease verified with no warning and no
        debian-keyring.
      - Docker 29.8.0 with Compose v5.5.1 and no buildx. The AppArmor
        `docker-default` profile was enforced.
      - All 5 containers were up (the 3 with health checks healthy), and every
        unit was active with none failed.
      - `--check` passed with `MASTER-FORWARD` first. Both WireGuard peers were
        kept.
      - The UIs, tailnet names, DNS and WebDAV answered.
      - The log held no test password.
    - A second run was a full no-op, and its before/after snapshot was
      identical: unit and container start times, `wg0.conf`, both
      Caddyfiles, `compose.yaml` and the cache.
    - `df` used on `/`: 2389 MB with v2-89, 1940 MB with v2-90 (−449 MB).
      `fstrim` then returned freed blocks to the virtual disk.

### DD-126: Negated bats assertions must be able to fail under bash 3.2 (2026-09-14)

- **Context:** the suite runs under macOS `/bin/bash` 3.2 (Bats 1.14.0).
  - A mid-test `! cmd` never fails a test, because errexit ignores negated
    commands.
  - A mid-test `[[ ]]` does not fail under bash 3.2 either.
  - So most negative assertions in `tests/common.bats` checked nothing.
  - The finding and a first conversion came from a separate session on a
    v2-84 base. That work was never merged and is kept on branch
    `wip/bats-negation-v2-84`; v2-91 redoes it on the current tree.
- **Decision:**
  - Every negation is `run !`: 115 statements, 86 simple ones converted
    mechanically and the rest by hand. Pipelines are captured into a variable,
    guarded with `[ -n ]` so an empty awk range cannot pass, and checked with
    `run ! grep … <<<"$var"`.
  - Every `[[ ]]` is `[ ]` or `case`.
  - A guard test fails the suite if a bare `! ` or `[[ ` statement appears
    again.
- **What the now-effective assertions exposed:**
  - **Four tests matched comments or deliberate text** and now look at code
    lines only:
    - the deprecated `--disable-exec` named in a compose comment;
    - `try-restart` in refresh-tailnet-config's DD-72 comment;
    - the old FileBrowser password hints matching the DD-118 comment in
      `install.sh`;
    - `docker rm` / `docker volume rm` in the qBittorrent and Portainer
      `die`/`log` messages, which tell the operator what to run
      (DD-116, DD-117). DD-96's guard wording now says so.
  - **One was real:**
    - `stage_6` still recreated `webdav` when it published
      `${TAILSCALE_IPV4}:${WEBDAV_PORT}`. Only the uncommitted v2-65 working
      tree ever had that layout, so no host needs the step.
    - It is migration cleanup, which DD-96 excludes, and the test forbidding
      it had been silent since v2-67. The block is removed. The user chose
      this (option A).
- **Verification:**
  - bats 123 ok; the same 3 `timeout yok` skips as before.
  - `shellcheck -x` is clean.
  - A diagnostic copy of the suite logged the exit code of every negated
    command: all 144 evaluations returned 1, and none passed on a grep error
    (2).
  - Deliberate mutations each failed their test:
    - a real `docker rm` command;
    - a real `try-restart` line;
    - `--disable-exec` in code;
    - the removed WebDAV log line put back;
    - a code line with the old password hint;
    - a bare `!` assertion.
  - The removed block could only run on the uncommitted v2-65 layout, so no
    live run was needed.

### DD-130: wireguard.command changes a peer's DNS and regenerates wg0 (2026-09-14)

- **Extended the same day:** the user did not want to wait for a manual
  backup. Options 2 (add), 3 (remove) and 7 (DNS) now run option 6 after a
  successful change, as option 8 already did.
  - Before, the menu only printed a reminder. A forgotten backup left
    `kurulum/wireguard/` behind the server, and a reinstall on a fresh server
    brought back a removed peer or missed a new one (DD-128).
  - A refused confirmation or a failed server call takes no backup. A failed
    backup does not undo the change; it warns and points to option 6.
  - Only `wireguard.command` changed. It is not part of the installer
    archive, so `V2_VERSION` stays v2-97 and the server needs no re-run.
  - bats 135 ok. Mutations were each caught: no backup after add, remove or
    DNS; a backup after a failed add; a backup after a declined remove.

- **Context:** the user benchmarked resolvers and wanted to point one peer at
  NextDNS without removing it. They also wanted a clean `wg0`: a new server
  key, with every peer and profile deleted when some exist.
- **Decision — DNS change (option 7, `master-wg dns NAME DNS`):**
  - Only the `DNS =` line of the stored profile's `[Interface]` changes. The
    keys, PSK, address and `wg0.conf` stay the same.
  - DNS is a client setting the server never sees, so nothing is applied and
    connected devices stay up. The device imports the new profile or QR code.
  - The list is validated as IPv4/IPv6 addresses and normalised to
    `a, b`, the form `add` writes.
  - The menu offers the current DNS as the default and saves the new profile
    to `kurulum/wireguard/`.
- **Decision — regenerate `wg0` (option 8, `master-wg reset --onay`):**
  - The `[Interface]` lines are kept (comment, address, port, MTU); only
    `PrivateKey` is new. Every `[Peer]` block and every profile in
    `/etc/wireguard/clients/` is removed. With no peers it is just a new key.
  - It goes through the same `write_and_apply` as `add`/`remove`, under the
    installer lock. A failed apply restores the previous `wg0.conf`, and
    profiles are deleted only after a successful apply.
  - Two guards: the server tool refuses without `--onay`, and the menu lists
    the peers and asks for `SIL` (or `SİL`). Anything else changes nothing.
  - The menu then runs option 6 "Yedek al". Otherwise `kurulum/wireguard/`
    would keep the old `wg0.conf` and profiles, a reinstall on a fresh server
    would restore the old key (DD-128), and deleted profiles would come back.
- **Rejected:**
  - Rebuilding `wg0.conf` from `defaults.env`: it would override a live
    interface the installer already manages (DD-124); a re-run of the
    installer does that part anyway.
  - Keeping peers with a new server key: every device would still need a new
    profile, so it is no better than adding them again.
  - Changing DNS by removing and re-adding the peer: new keys and address
    for a client-only setting.
- **Verified (2026-09-14):**
  - bats 134 ok; mutations of the `--onay` guard, the profile deletion, the
    `[Interface]` scoping of the DNS rewrite, the `SIL` check and the backup
    after reset were each caught.
  - On `nrm`, the new `master-wg` ran against a throwaway `wgtst0` interface
    (its own `STATE_FILE`, subnet `10.99.0.0/24`, port 61901) with two test
    peers.
    - `dns` wrote the NextDNS IPv6 pair; every other profile line,
      `wgtst0.conf` and the interface key were unchanged, with 2 peers still
      up. A hostname was refused.
    - `reset` without `--onay` was refused. With it: "2/2", a new key, 0
      peers on the interface and in the file, no profiles, the four
      `[Interface]` lines kept, mode 600, the unit still active on its port.
    - `wg0` (key and peers) was unchanged; the test interface and files were
      removed afterwards.

### DD-131: WireGuard client DNS default — Cloudflare IPv4 first, one IPv6 third (2026-09-14)

- **Context:** the user wanted the lowest-latency Cloudflare setup as the
  default of `wireguard.command` → 2) ekle. The old default was
  `1.1.1.1, 2606:4700:4700::1111`. Peers' DNS queries leave through `nrm`,
  so the `nrm`→Cloudflare leg is the part the address choice can change.
- **Measured from `nrm` (2026-09-14, raw UDP queries, orders shuffled):**
  - All four addresses reach Cloudflare's Frankfurt PoP (`colo=FRA`), with
    no loss.
  - Ping: IPv4 about 4.3 ms, IPv6 about 3.8 ms.
  - Uncached names (random `*.cloudflare.com`): IPv4 median 7.3–8.4 ms, IPv6
    median 16.8–17.8 ms.
  - The same cached name 100 times: `1.1.1.1` answered 97–99 under 7 ms.
    `2606:4700:4700::1111` was bimodal: 46–53 under 7 ms and 46–54 at 12 ms
    or more. Ping answers at the edge; the DNS answer comes from a resolver
    behind it, so the lower ping did not mean faster DNS.
  - `::1001` against `::1111`, three runs of 120 cached and 60 uncached
    queries each:
    - Cached: `::1001` was ahead in every run (median 5.3–5.9 against 14.8 ms;
      mean 9.4–9.8 against 10.1–10.5 ms; 50–54% against 43–46% under 7 ms).
    - Uncached: mixed, overall mean 13.2 against 13.5 ms. Both stayed bimodal.
- **Decision:** `WG_CLIENT_DNS_DEFAULT="1.1.1.1, 1.0.0.1, 2606:4700:4700::1001"`.
  - The two IPv4 anycast addresses come first; either covers the other.
  - One IPv6 address is third, as a fallback for a client that only
    reaches IPv6; `::1001` for its slightly better cached answers.
  - IPv4 resolvers still return AAAA records, so IPv6 browsing through the
    tunnel is unaffected.
  - No other provider is mixed in: clients may spread queries across the
    list.
- **Scope:** only the menu's default for new peers. Existing peers keep their
  DNS until changed with option 7. The server never reads this key, so
  `V2_VERSION` stays v2-97 and the launcher is re-exported under the same
  version.
- **Revisit:** a single day's measurement from one host. If Cloudflare's
  IPv6 answers stop being bimodal, measure again before reordering.
- **Verified:** bats 135 ok. Option 2 with Enter sends exactly the defaults.env
  value, and `master-wg` writes it back unchanged, so option 7 offers it
  as-is. A hard-coded menu default and an unnormalised default list were each
  caught.

### DD-132: The QR code comes to the Mac as a PNG with the profile (2026-09-15)

- **Context:** the user wanted each profile's QR code saved next to it in
  `kurulum/wireguard/`, as JPG or PNG, to show it on a screen or another
  device without opening the menu.
- **Decision:**
  - PNG, not JPG: a QR code needs sharp module edges, and JPG compression
    blurs them. `qrencode` writes PNG directly.
  - The server makes it. `master-wg png NAME` runs
    `qrencode -t PNG -s 8 -o -` on the stored profile (616×616 px and about
    1.4 KB for a 388-byte profile).
    - It refuses when standard output is a terminal, so binary data is never
      printed.
  - `wireguard.command` saves `<name>.png` whenever it saves `<name>.conf`:
    add, DNS change, and "4) QR göster" with the refresh answer.
    - It goes through a temporary file, mode `600`, and is kept only when it
      starts with the PNG signature. Otherwise the menu warns and the profile
      stays.
  - "3) Peer çıkar" deletes both files locally, even when the backup after
    it fails.
  - The backup (option 6, and the automatic one) makes a PNG for every
    profile on the server.
    - They are made in `mktemp -d /run/wg-yedek.*` (tmpfs, root-only, removed
      on exit) at the same relative path as the profiles, and sent in the
      same tar.
    - A profile whose PNG fails still comes through, with a warning.
    - The Mac mirrors `.png` like `.conf`: a picture whose profile the server
      no longer has is removed.
  - The launcher still sends only `*.conf` (and `sunucu/wg0.conf`), so
    pictures never reach the server and stage 0's allow-list is unchanged.
- **Security:** the picture encodes the whole profile, client private key
  included, so it is protected exactly like the `.conf` file: mode `600` in
  the Git-ignored `kurulum/`, never printed, never sent to the server.
  Sharing the picture shares the tunnel.
- **Rejected:**
  - Making the PNG on the Mac: macOS has no QR encoder, and adding Homebrew
    `qrencode` would add a tool to install.
  - Keeping the PNG on the server: nothing there needs it, and it would be a
    second copy of the key to manage.
- **Fixed the same day:** with no profiles the script ended with
  `tar … -C <temp dir>` and no member after it. GNU tar 1.35 rejects that
  (exit 2), so the automatic backup after "8) wg0 yeniden üret" failed and
  the Mac kept the old files. macOS tar accepts it, which is why bats missed
  it. The `-C` part is now added only when a picture exists. A test runs the
  script with a GNU-strict `tar` wrapper, with and without profiles.
- **Cost:** `master-wg` changed, so this is v2-98. The menu refuses a server
  on another version; re-run the installer once. Peers, keys and accounts
  are kept.
- **Verified (2026-09-15):**
  - bats 137 ok. Eight mutations were each caught: terminal QR instead of PNG;
    no terminal check; no PNG-signature check; no PNG download in the
    backup; no stale-PNG removal; PNG not added to the tar; the server
    temporary directory kept; no local PNG removal on a remove whose backup
    fails.
  - On `nrm`, with the new `master-wg` against a throwaway `wgtst0`
    interface and two test peers:
    - `png` gave a valid PNG (616×616, 1,397 bytes), identical when made
      twice. On a pseudo-terminal it was refused; an unknown peer was
      refused.
    - The backup script listed `wgtst0.conf`, both profiles and both
      pictures, and left nothing in `/run/wg-yedek.*`. Its picture matched
      the one `png` made.
    - The test picture, decoded on the Mac with CoreImage, gave the
      388-byte profile byte for byte.
    - `wg0` (4 peers, 4 profiles) was untouched, and the test interface and
      files were removed.

### DD-133: A WireGuard web panel on the tailnet, built on master-wg (2026-09-15)

- **Partly superseded by DD-140, DD-147 and DD-180:** the separate
  `wg.<domain>` panel, its input-file account, Basic auth, lockout and the
  `127.0.0.1:61008` listener are gone; the backend is Konsol's root backend on
  a Unix socket. Still current: every change goes through `master-wg`,
  previews mask the keys, and the CSP, `no-store`/`DENY` headers and the unit
  sandbox stay.

- **Context:** the user liked the menu but wanted to manage peers from a
  browser as well: add, remove, show and download the QR code and profile,
  change DNS. A design prototype was approved, including tabs per interface.
  - Multiple interfaces (`wg1`, `wg2`, …) were agreed as a second step. This
    decision covers `wg0` only; the tab strip is ready for more.
  - Access option A was chosen: the tailnet only, with a password.
- **Decision:**
  - **Server-side and small.** `master-wg-panel` uses Python 3's standard
    library (already installed for the qBittorrent hash). There is no Docker
    and no new package. It listens on `127.0.0.1:61008`, and the tailnet
    Caddy proxies `http://wg.${LOCAL_DOMAIN}` to it. Nothing listens on `wg0`
    or the WAN, and stage 7 proves that.
  - **One rule set.** Every change calls `master-wg`, so the panel and
    `wireguard.command` share validation, the installer lock, the live
    `wg syncconf` apply and the rollback. `master-wg info` was added for the
    listing: `list`'s six fields plus IPv6, DNS, keepalive and MTU, never a
    key. `list` keeps its format for the menu.
  - **Account from the input file (DD-119).** `WG_PANEL_USER`/`WG_PANEL_PASS`
    are required keys; the password needs at least 12 characters, like
    FileBrowser, because the panel can mint tunnels.
    - The installer runs `master-wg-panel account` with the password on stdin.
      It stores PBKDF2-SHA256 (600000 rounds, 16-byte salt) in a `0600` file
      and keeps it while it verifies. The panel re-reads the file when it
      changes.
    - Stage 7 signs in with the input account through Caddy (`check`, also
      password on stdin) and then forgets the password.
  - **Authentication and abuse.**
    - HTTP Basic, the browser's own prompt. The tailnet (WireGuard) encrypts
      it, as for the other UIs.
    - A verified `Authorization` header is cached in memory for 15 minutes as
      a SHA-256 digest, so PBKDF2 runs once, not on every request.
    - Each wrong password waits one second. Ten in 15 minutes lock that client
      out for 15 minutes, keyed by the `X-Forwarded-For` Caddy sets, trusted
      only from loopback.
  - **Browser attacks.**
    - Basic credentials are sent automatically, so every `/api/*` request
      needs `X-WG-Panel: 1`. A cross-site page cannot add that header without
      a CORS preflight the panel never grants. A `Sec-Fetch-Site` other than
      `same-origin` or `none` is refused.
    - A `Host` other than `wg.${LOCAL_DOMAIN}` or the loopback port is refused
      (DNS rebinding).
    - The CSP allows only `'self'` (plus `blob:` for the QR picture), with no
      inline code. Responses are `no-store`, no-referrer and `DENY` for
      frames.
    - The page uses system fonts and loads nothing from other hosts.
  - **Secrets on demand.** The profile preview masks `PrivateKey` and
    `PresharedKey` on the server. The QR picture is fetched only after "QR'ı
    göster" and dropped after 60 seconds. Downloads fetch the full profile or
    picture only when clicked. The journal names user, client, action and
    peer.
  - **Least privilege that still works.** `master-wg` needs root
    (`wg syncconf`, `/etc/wireguard`). The unit adds `NoNewPrivileges`,
    `ProtectSystem=full` with only `/etc/wireguard` writable (the lock lives in
    `/run`), `ProtectHome`, `PrivateTmp`, kernel protections, no namespaces or
    realtime, and four address families.
  - **Backup state.** `wireguard.command`'s backup script touches
    `/etc/master-stack/wg-backup.at` after a successful archive. The panel
    shows "Mac yedeği eski" while `wg0.conf` or the profile directory is
    newer. Panel changes still reach the Mac only through option 6, since the
    server cannot write to it.
  - **DNS choices.** The default comes from `WG_CLIENT_DNS_DEFAULT` (DD-131),
    plus Google, Quad9 and every DNS list already used by a peer (for example
    the operator's NextDNS pair), and custom. No personal resolver address is
    hard-coded.
  - `wg` becomes a service name again. wg-easy's use ended with DD-120; the
    wg-easy test now checks that `wg.` points to the loopback panel.
- **Rejected:**
  - A login form with a session cookie: more code (cookie flags without
    HTTPS, session store, logout) for the same protection on the tailnet.
  - Caddy `basic_auth`: the hash would sit in the world-readable Caddyfile or
    need a group-readable import. Local processes could reach the upstream
    without a password. The panel would need a shared secret header to tell
    Caddy's requests apart.
  - A Unix socket: tighter, but the panel would need `caddy` group handling,
    and loopback with its own authentication already refuses local callers
    without the password.
  - Exposing the panel on WireGuard (option B): a device on `wg0` could delete
    its own tunnel or regenerate `wg0` and lock everyone out.
  - Reading `/etc/wireguard` directly from Python: a second parser and a
    second writer beside `master-wg`.
- **Cost:** v2-99 adds two required keys to `kurulum.env`; the installer stops
  with a clear message until they are there. One service, one Caddy site, one
  DNS name and port 61008 are added.
- **Verified (2026-09-15, bats):**
  - 143 ok. The panel was started against a fake `master-wg` for these checks:
    - 401 without or with a wrong password and 200 with the account;
    - the CSP, `no-store` and `DENY` headers;
    - 403 for another `Host`, for `/api` without the header and for a
      cross-site fetch;
    - JSON state with backup freshness;
    - exact `add`/`dns`/`remove`/`reset --onay` arguments;
    - bad names, bodies and confirmations never reaching `master-wg`;
    - `master-wg` refusals returned as messages;
    - a masked preview against a full download;
    - PNG only on request;
    - an audit log without secrets;
    - a new account read without a restart;
    - a 429 lockout for one client while another passes.
  - `account` keeps a matching hash, rewrites a changed one, stores no
    plaintext and leaves no temporary file.
  - `master-wg info` gives exact fields: keepalive 0 when absent, empty profile
    fields without a profile, no key material.
  - Thirteen mutations were caught, one of each guard: the panel header,
    `Sec-Fetch-Site`, `Host`, account reload, masking, the name check, the
    reset confirmation, the lockout, keeping a matching hash, keepalive 0 and
    the API origin gate.
- **Verified live (2026-09-15, `nrm`, Debian 13):**
  - The v2-99 launcher ran with a scratch input file and exited 0. Stage 7
    signed in to the panel through Caddy ("4 peer"). The operator's account
    files were saved and restored; FileBrowser's account export matched.
  - Through the tailnet Caddy (`Host: wg.ayc`):
    - 401 without or with a wrong password, and 200 with the account;
    - CSS and JS served with their types and the CSP; 403 for `/api` without
      the header;
    - state with the four real peers;
    - `paneltest` added (4 → 5 peers on `wg0`), a duplicate refused with
      master-wg's message;
    - the masked preview carried no key, the download carried it, and the QR
      PNG equalled `qrencode` of the stored profile;
    - DNS changed and a hostname refused;
    - removed (back to 4); `wg0.conf` and the profile list byte-identical to
      before the test;
    - a reset without `SIL` refused.
  - Another `Host` never reached the panel: Caddy answered its empty default.
    Nothing answered on `10.8.0.1:61008` or the WAN.
  - The unit showed `NoNewPrivileges=yes`, `ProtectSystem=full`, `/etc/wireguard`
    writable and four address families. The journal had audit lines and no
    password or key.
  - With the same sandbox (`systemd-run`) on a throwaway `wgtst0`:
    - two adds;
    - an add while the interface was stopped, which restarted it through
      `systemctl` from inside the sandbox;
    - a `SİL` reset (3 peers and 3 profiles removed, new key, unit active);
    - no permission errors, `wg0` untouched.
  - The scratch panel account was deleted afterwards, so the panel stays
    locked until the operator's install writes theirs.
- **Browser check (2026-09-15):** the real page ran against a loopback copy
  with sign-in removed, sample peers and a fake `master-wg`, never published.
  - Add opened the QR dialog with the masked profile, and the QR appeared on
    "QR'ı göster" with the 60 s countdown. The DNS presets included the
    operator's NextDNS pair as "Bu sunucuda". DNS change and inline remove
    confirmation worked, and typing `sil` enabled regeneration, which ended in
    the empty state.
  - A mouse click on "Çıkar" was lost once because the 10-second refresh
    replaced the rows. The refresh now updates status, age, traffic and
    totals in place while the peer set is unchanged; the same button element
    survived a refresh, and the click then worked.

### DD-134: Regenerating wg0 is confirmed with "onayla"; the panel layout is tightened (2026-09-15)

- **Context:** after using v2-99, the user asked for three changes:
  - a smaller regenerate section;
  - the confirmation word "onayla" instead of "SIL";
  - wider table columns, because the DNS column wrapped a single character
    onto a new line and spare room sat beside the traffic column.
- **Decision:**
  - **One word everywhere.** The panel (page and server check) and
    `wireguard.command` option 8 accept `onayla` in any case; "SIL" no longer
    confirms. `master-wg reset --onay` is unchanged. The word lives once in
    each tool: `CONFIRM_WORD` in `master-wg-panel` and `panel.js`, the `case`
    in the menu.
  - **Compact danger row.** Smaller padding, title and text, a short input
    with `onayla` as placeholder, and a small button on one line. It keeps
    the red border, stays at the bottom, and the button stays disabled until
    the word is typed.
  - **Columns sized to their content.**
    - Status 7rem, name `minmax(6rem, .7fr)`, address `minmax(13rem, 1.2fr)`,
      DNS `minmax(14rem, 1.5fr)`, handshake 7.5rem, traffic 6rem, actions
      10.5rem.
    - Headers stay on one line.
    - An address never breaks: the IPv6 address is `nowrap`, and each DNS
      address is its own `nowrap` span, so lists wrap only after a comma.
- **Found in the browser check:** the confirmation input was full width. The
  generic `input[type="text"]` rule came later with equal specificity; the
  danger rule is now more specific.
- **The `cafe` in the IPv6 addresses:** not a protocol requirement. The
  `fdcc:ad94:bacf:61a4::cafe:0/112` range is wg-easy's default. DD-120 kept it
  so existing profiles connected unchanged; `cafe` is just a readable hex
  group. Changing it would give every peer a new address and profile, so it
  stays.
- **Verified (2026-09-15):**
  - bats 143 ok. The panel test now refuses `SIL` and accepts `Onayla`; the
    menu test refuses `SIL` and accepts `Onayla`. Two mutations were caught:
    accepting `sil` again in the panel and dropping the menu's lower-casing.
  - Browser check of the page against sample peers (Cloudflare, Google, Quad9)
    at 1440 px: one-line headers, no address split, and a one-line danger row.

### DD-135: WireGuard IPv6 addresses without a word: fdcc:ad94:bacf:61a4::N (2026-09-15)

- **Context:** the user asked to replace `cafe` in `fdcc:ad94:bacf:61a4::cafe:N`,
  the range kept from wg-easy by DD-120.
  - `root` and `peer` are not valid: IPv6 groups are hexadecimal (0–9, a–f).
  - Among the valid choices the user picked plain numbers.
- **Decision:**
  - `WG_SERVER_IPV6="fdcc:ad94:bacf:61a4::1"` and
    `WG_SUBNET6="fdcc:ad94:bacf:61a4::/112"` (the canonical form `ip6tables`
    prints). A peer's address stays the hex of its IPv4 host number:
    `10.8.0.2` → `…::2`, `10.8.0.10` → `…::a`.
  - `master-wg`, the panel and the firewall already derive everything from
    these two values; no code depended on `cafe`.
  - **Stricter snapshot check.** `wg_snapshot_check` used to test only that
    an address starts with the prefix. With `…::` as the prefix, `…::1:2`
    (outside the /112) or `…::cafe:2` would have passed. Now the part after
    the prefix must be only a hex host number (`/128`), and for IPv4 only
    digits (`/32`).
  - **No migration, by the user's rule (2026-09-15):**
    the scenario is a fresh install on a test server. Nothing converts, keeps
    or accepts peers, profiles or backups made with the `cafe` range.
    - A pulled `kurulum/wireguard` from before stops stage 0 with "AllowedIPs
      WireGuard alt ağı dışında"; delete it and install fresh.
    - Installing over a server that still has `cafe` peers leaves those peers
      without IPv6; reset and re-add them.
  - A stage-0 gate for old peers and an exception for an old backup were
    written and then removed at the user's request.
- **Verified (2026-09-15):**
  - bats 143 ok. Fixtures use the new range: `master-wg add` writes `…::2/128`
    and `info` lists it.
  - The snapshot check rejects `…::cafe:3/128`, `…::1:3/128` and
    `10.8.0.3.4/32`; two mutations (prefix-only IPv6 and IPv4 checks) were
    caught.
  - On `nrm`, `ip6tables -t nat -C … -s fdcc:ad94:bacf:61a4::/112` parsed the
    subnet (read-only).
  - The operator's pulled backup was rejected as expected (`…::cafe:2/128`).

### DD-136: More WireGuard networks from the panel; the panel stops pointing to the Mac backup (2026-09-15)

- **Context:** the user approved the tabbed design and asked for the second
  step: "Arayüz ekle" in the panel creating `wg1`, `wg2`, … with peers added
  and removed per network. They also asked to drop "Mac yedeği alınmadı" from
  the panel: `wireguard.command` is tracked separately, and the panel does not
  redirect to it.
- **Decision:**
  - **Runtime networks, not installer inputs.** Extra networks are created
    and removed from the panel through `master-wg net-add`/`net-remove`; the
    installer manages only `wg0`. Re-runs, reboots and firewall restarts keep
    them.
  - **One registry, three readers.** `/etc/wireguard/networks` holds one
    tab-separated line per network with every value spelled out (interface,
    port, scope, server and subnet IPv4/IPv6, default DNS, label).
    - `master-wg` computes the addresses once and writes the line;
      `master-firewall` and the panel read it and derive nothing.
    - It sits in `/etc/wireguard` because the hardened panel service may
      write only there (`ProtectSystem=full`), as do the per-instance Caddy
      env files.
  - **Addressing** follows DD-135: `wgN` = `10.8.N.0/24` and
    `fdcc:ad94:bacf:61a4::N:0/112`, a peer `10.8.N.H` / `…::N:H`. `wg0` stays
    `…::H`. At most `WG_NETWORKS_MAX` (9) extra networks.
  - **`master-wg --if wgN`** swaps every `WG_*` value (interface, port,
    addresses, `wgN.conf`, `clients-wgN`) before any command runs. So `add`,
    `remove`, `dns`, `reset`, `info`, `profile`, `qr` and `png` are unchanged
    and share one code path, lock and rollback.
  - **Safe order when adding.** Files and registry, then the firewall (the
    port opens and forwarding/NAT exist before the interface), then
    `wg-quick@wgN`, then `caddy-wg@wgN` for `ui`. A failure tears the network
    down and re-applies the firewall.
    - Ports are checked against the stack's ports (from `state.env`: SSH,
      torrent, WebDAV, UIs, Tailscale, panel, DNS, HTTP), wg0, other networks
      and live UDP listeners.
    - Stage 0 in turn refuses a `wg0`/WebDAV port a panel network uses.
  - **Firewall loops over networks.** `load_wg_networks` reads `wg0` from
    `state.env` plus the registry and validates everything (interface names,
    ports, scopes, addresses, duplicates) before any chain is built.
    - Per network: a WAN UDP accept; on INPUT an echo-request and a DROP, plus
      the UI ports on its own address only for `ui`; on FORWARD
      `-i wgN -o WAN ACCEPT`, `-i wgN DROP`, replies back and `-o wgN DROP`;
      a NAT masquerade per subnet.
    - A packet from one network to another dies at its own `-i … DROP`.
    - `--check` asserts every rule, forbids UI ports on an `inet` network and
      expects exactly `4 × networks + 1` FORWARD rules.
  - **`caddy-wg` becomes a template.** One `Caddyfile.wg` with
    `default_bind {$WG_BIND}`; `caddy-wg@<interface>` reads
    `/etc/wireguard/caddy-wg-<interface>.env`, requires and follows its
    `wg-quick@`. The installer restarts panel networks' instances when the
    shared file changes.
  - **Panel.**
    - `/api/state` returns every network with its peers.
    - Peer routes move under `/api/nets/<iface>/…`.
    - `POST /api/nets` adds a network; `/api/nets/<iface>/remove` and
      `/reset` need `onayla`.
    - The page shows a tab per network, a split "Peer ekle" button with
      "Arayüz ekle", a network drawer (next free `wgN`, suggested port, label,
      scope, default DNS) and a danger row per network (regenerate; remove for
      `wg1+`).
    - The network's default DNS leads the presets when adding a peer.
  - **Backup marker removed.** The panel's backup pill, the
    `/etc/master-stack/wg-backup.at` marker and its `touch` in
    `wireguard.command` are gone.
- **Not covered, by the user's split:** `wireguard.command` manages `wg0`
  only, and the Mac backup and the restore on a fresh install cover `wg0`
  only; panel networks are recreated in the panel. Earlier single-network
  servers are not migrated: the old `caddy-wg.service` stays on a server
  installed before v2-101, so install fresh (DD-135 rule).
- **Rejected:**
  - Networks in `kurulum.env`: the user wanted them created from the page.
  - A second Caddy per network file: one shared file and a template instance
    keep the UI surface identical.
  - Deriving addresses in each reader: three copies of the same arithmetic.
  - Letting the panel write `/etc/master-stack`: a wider sandbox for no gain.
- **Verified (2026-09-15):**
  - bats 145 ok.
    - The firewall's rules are generated for wg0 + an `inet` wg1 + a `ui` wg2
      and checked line by line (ports, UI only on `ui`, FORWARD order and the
      count of 13, NAT per subnet); a broken or clashing registry is refused
      before any rule.
    - `master-wg` tests cover `net-add` (addresses, registry, env file, order
      firewall → interface → Caddy, refusals, rollback on an interface or
      Caddy failure, the limit), `--if`, `nets` and `net-remove`.
    - The panel passes each network's actions with the right `--if` and
      refuses bad interfaces and confirmations.
    - Mutations were caught: WAN port only for wg0, UI ports on `inet`, no
      FORWARD DROP between networks, a duplicate port accepted, the interface
      before the firewall, a registry line left after rollback, wg0 removable,
      a panel network writing wg0's profiles, no interface check in the panel
      and removal without confirmation.
  - **Live on `nrm`** (v2-101 over a v2-100 install with scratch inputs; the
    old `caddy-wg.service` was removed by hand first):
    - Stage 7 passed ("1 ağ, 0 peer").
    - Through the panel API: wg1 (`inet`, 61011) and wg2 (`ui`, 61021) were
      created and a duplicate port was refused. The firewall showed three WAN
      UDP ports, 13 FORWARD rules in IPv4 and IPv6 and three NAT subnets, and
      `--check` passed. `caddy-wg@wg2` listened on `10.8.2.1`.
    - Real WireGuard clients in network namespaces:
      - wg1 reached the internet over IPv4 and IPv6 and its own server by
        ping. It was refused its own UI ports, wg0's and wg2's addresses,
        the tailnet Caddy, SSH and port 61008.
      - wg2 reached the internet and its own Dozzle (307), qBittorrent (200)
        and FileBrowser (200), and was refused wg0's and wg1's addresses.
      - wg1 ↔ wg2 and wg2 → a wg0 peer address were blocked.
    - Removing wg1 needed `onayla`. It stopped the unit, deleted its files,
      closed 61011, left 9 FORWARD rules and passed `--check`.
    - After a reboot, wg0, wg2, both `caddy-wg@` instances, the firewall and
      the panel came back with no failed unit.
    - wg2 and the test peer were removed through the panel. The operator's
      accounts, including the panel account, were restored.
  - **Browser check** of the page against sample networks: tabs with labels
    and counts, per-network header and chips, the network drawer with the
    next free `wg2`, port 61021 and addresses, and the new tab opening after
    creation.

### DD-137: The panel's "Bağlı" follows traffic, not the handshake (2026-09-15)

- **Context:** the user connected two peers, disconnected one, and both still
  showed "Bağlı". The status came from the last handshake (< 180 s), and a
  WireGuard handshake stays fresh for up to three minutes after a device
  goes away, whether or not it sends anything.
- **Decision:**
  - A peer is online when its received bytes grew within `ACTIVE_WINDOW`
    (45 s) **and** its last handshake is under 180 s. A connected device
    sends at least a keepalive (25 s by default) within that window.
  - A sampler thread reads every network every `SAMPLE_SECONDS` (10 s), so
    the counter history does not depend on an open page.
  - Until a peer has been watched for a whole window (after a panel restart
    or a new peer), the handshake decides as before.
  - The page shows "Bağlı" from `online`, otherwise "Boşta" within 24 hours
    of a handshake and "Görülmedi" after. The hint explains the window.
  - `PANEL_ACTIVE_WINDOW` and `PANEL_SAMPLE_SECONDS` exist only for tests.
- **Rejected:**
  - A shorter handshake limit: a quiet but connected device (keepalive off)
    would flap.
  - Probing the device: the server has no way to ping through a peer's
    firewall, and a probe would be traffic it never asked for.
- **Verified (2026-09-15):** bats 146 ok. Live on `nrm` with the Mac as a peer:
  "Bağlı" 2–5 s after connecting, "Boşta" 47–48 s after disconnecting.

### DD-138: The server's IPv4 and IPv6 are detected and stored, never written by hand (2026-09-15)

- **Context:** the user asked whether the endpoint `203.0.113.10` had been
  typed by hand. Server addresses may change, so no file may hold a fixed IP;
  the installer should detect IPv4 and IPv6 on the server, store them, and
  every part should read them from there.
- **Finding:** the IPv4 endpoint was already detected on every run
  (`ip -4 route get 1.1.1.1` → `WAN_IPV4` → `WG_ENDPOINT_HOST` in
  `state.env`), and `master-wg` and the panel read it from there. The literal
  address appeared only in test fixtures and history. IPv6 was not detected.
- **Decision:**
  - `detect_wan` also reads the source of `ip -6 route get 2606:4700:4700::1111`
    and keeps it only if it is a global address on the WAN interface; otherwise
    `WAN_IPV6` is empty. Nothing is sent and no outside service is asked.
  - `state.env` gets `WAN_IPV6`, and the summary's WAN line shows it.
  - It is not an endpoint. The firewall opens WireGuard's UDP ports on the
    IPv4 WAN only (IPv6 WAN allows Tailscale and SSH, contract §9), so
    profiles and the panel keep the IPv4 `WG_ENDPOINT_HOST`. A first draft
    showed an IPv6 endpoint; the live check on `nrm` found the port closed on
    IPv6 and the label was dropped.
  - Opening WireGuard on the IPv6 WAN is left to the user: it changes the
    firewall contract (2 → 2 + networks IPv6 allows).
  - Test fixtures use the documentation address `203.0.113.7`; a test fails
    if a public IPv4 literal appears in the installer, `master-wg`, the panel
    or `defaults.env`.
- **Not doing:** rewriting profiles or `state.env` automatically when the
  address changes (DD-76 still applies). A re-run detects the new address;
  existing devices need a new profile, and stage 5 warns about stale ones.
- **Verified (2026-09-15):**
  - bats 147 ok.
  - Live on `nrm` (v2-103 over v2-102, scratch inputs, accounts restored):
    `state.env` holds `WAN_IPV4` and the detected `WAN_IPV6`, the summary
    shows both, profiles keep `Endpoint = <WAN_IPV4>:port`, `--check`
    passes, 0 failed units.

### DD-139: A file panel for the downloads folder, run as the downloads uid (2026-09-15)

- **Context:** after the WireGuard panel, the user asked for a second
  FileBrowser-like page. It should browse the server's folders, and delete,
  move and rename.
  - They approved the design artifact (list/icon view, trash, text viewer) and
    asked for text files to open in the page.
  - Their decisions: `/downloads` only, delete goes to a trash, the same account
    as the WireGuard panel, FileBrowser stays, no access over WireGuard.
- **Decision:**
  - **A separate service, not a tab of the WireGuard panel.** The WireGuard
    panel runs as root because `master-wg` needs it. A file manager inside it
    would move files with root rights. `master-files-panel` runs as
    `DOWNLOADS_UID`, the owner of every file qBittorrent, Unpackerr and
    FileBrowser write, with no capabilities and only `DOWNLOADS_PATH` writable.
    - systemd refused a numeric `User=1000` without a user entry (seen live:
      `217/USER`). The installer therefore uses the uid's existing name or
      creates `master-downloads` (system, no login, no home). Ownership on disk
      stays numeric.
  - **Same account without a second copy on disk.** `/etc/master-stack` is
    `0700 root`. `LoadCredential` gives the service its own copy of
    `wg-panel.auth` at start. When the installer rewrites the account, the file
    panel restarts.
    - The PBKDF2 check and the lockout are duplicated from the WireGuard panel
      (a few dozen lines) instead of refactoring the working panel. A bats test
      signs in to the file panel with an account written by
      `master-wg-panel account`, so the two cannot drift apart silently.
  - **Root confinement in the server, not the page.** Every request names a
    path relative to the root. The server walks it from a directory descriptor,
    one `O_NOFOLLOW` open per step, and acts with `*at` calls on single names.
    A symlink is shown but never followed, so a link to `/etc` or a swapped
    directory cannot lead outside.
  - **Nothing is overwritten.** Renames and moves use `renameat2` with
    `RENAME_NOREPLACE` through `ctypes`. Where the file system lacks it (and
    in the macOS tests), a check-then-rename under the panel lock is used.
    Moves check every target first and refuse the whole request on a clash.
  - **Trash on the same disk.** Delete renames the item into
    `DOWNLOADS_PATH/.cop/<id>/`, with `<id>.json` holding the origin and time,
    so deleting is instant and reversible.
    - Restore goes back to the origin, or to the root when it is gone, with a
      free numbered name.
    - Permanent delete is fd-based and never follows a link. It works only on
      trash entries, and emptying needs `onayla`.
  - **Unpackerr and WebDAV must not see the trash.** Live test: Unpackerr
    watches hidden folders too and extracted a zip inside `/downloads/.coptest`.
    `UN_FOLDER_0_EXCLUDE_PATHS_0` did not stop it.
    - An empty read-only tmpfs over `/downloads/.cop` in `unpackerr` and
      `webdav` did: a zip placed in the trash stayed packed while a visible one
      was extracted.
    - Infuse sees an empty `.cop`, like `.unpackerr`. Stage 7 checks the mount
      in both containers.
  - **Text view on the server.** The server reads the first 1 MiB and refuses a
    NUL in the first 8 KiB. It decodes with the guessed or chosen encoding:
    UTF-8, else Windows-1254 for Turkish subtitles, CP437 for `.nfo`. The page
    inserts the result as text nodes; a download is `application/octet-stream`
    as an attachment.
  - **CSRF for downloads.** API calls need `X-Files-Panel: 1`. A download is a
    link and cannot send a header; it only reads, and it is still refused when
    `Sec-Fetch-Site` says `cross-site` or `same-site`.
- **Rejected:**
  - Running as root with a path check: one missed case would expose the host.
  - A copy of the hash owned by uid 1000: a second secret file to keep in sync.
  - Dropping privileges inside Python, or `setpriv`: more code or a lost
    credential, for what `User=` already does.
  - A trash outside `/downloads`: not guaranteed to be on the same disk, so
    delete would become a copy.
  - Upload, copy, thumbnails and cross-disk moves in the first version:
    FileBrowser already has them.
- **Verified (2026-09-15):**
  - bats 152 ok.
    - Five new tests: login and gates; root confinement and no overwrite; the
      trash round trip; text, encodings, the 1 MiB cut and downloads; installer
      wiring.
    - Ten mutations were caught: no `O_NOFOLLOW`, an overwriting fallback, the
      trash reachable by path, empty without `onayla`, no cross-site check, no
      header check, wrong host accepted, binary shown as text, the service as
      root, and the WebDAV tmpfs missing.
  - **Live on `nrm`** (v2-104 over v2-103, scratch inputs):
    - The first run failed at stage 7 with `217/USER`. The account fix above,
      a `getent` exit status under `pipefail`, and a start limit left by the
      failed runs (`reset-failed`) followed.
    - The third run passed stage 7 ("kök /downloads, çöpte 0 öge"). The service
      runs as `master-downloads` (uid 1000); `systemd-analyze security` gives
      3.0 OK.
    - From the Mac over Tailscale and Caddy:
      - A symlink to `/etc` was listed, and neither listing nor reading through
        it worked.
      - A rename onto an existing file was refused on ext4 (`renameat2`).
      - Windows-1254 and CP437 files were decoded; the download worked.
      - Move and mkdir worked, and a move into itself was refused.
      - A folder with a zip and the `/etc` link went to the trash. Unpackerr
        left the zip packed and both containers saw an empty `.cop`.
      - Restore went to the origin. Purging the link left `/etc` intact, and
        emptying needed `onayla`.
    - After a reboot the panel and both tmpfs mounts came back, with 0 failed
      units. The operator's accounts were restored and the file panel
      restarted; the test account now gets 401 on both panels.

### DD-178: Seed qBittorrent integration, not user preferences (2026-09-29)

- **Request:** limit configuration to panel integration and correct service
  operation; leave UPnP/automatic port mapping and local peer discovery to users.
- **Decision (v2-152):** remove forced UPnP, port-mapping and LSD values, and
  forced separate temporary storage, from the new-profile template. Keep only
  the writable default download location (current/compatibility keys), loopback
  WebUI address/port, localhost authentication and the existing headless-startup
  notice acceptance. Absent keys use the installed application's defaults;
  removing `false` does not mean writing `true` instead.
- **Preserve:** nonroot service account, profile ownership, systemd sandbox,
  DNS/Caddy integration and host firewall. No new peer-port permission, routing
  change, automatic tuning or extra package. Existing Files/share guards for the
  conventional incomplete path remain; they do not enable temporary storage.
- **Existing profiles:** no automatic deletion or migration of preference keys;
  old installer defaults cannot be distinguished safely from deliberate user
  choices. Reapply and remove/reinstall without data deletion preserve all of
  them. Users change their current preferences in qBittorrent's own settings.
- **Verification:** exact seed-key allowlist and lifecycle/profile-preservation
  Bats tests; isolated native Linux comparison against the same qBittorrent's
  defaults, anonymous/login gates, nonroot startup and preference persistence
  after restart. Live installed accounts/services are not used by this fixture.
- Supersedes DD-151's enforced UPnP/LSD/temporary-storage defaults only; the
  firewall and other module lifecycle decisions are unchanged.
- **Amended (v2-195, DD-217):** on its own bridge the seeded and installed `WebUI\Address` is `*`
  (loopback is now the Quadlet's only interface publication), and the peer port 61008 is published
  on the WAN address by the user's choice.
- **Amended (v2-196, DD-218; reverted v2-197, DD-219):** chosen fresh-profile defaults were seeded for
  one version and then reverted; the seed is again integration keys only.

### DD-177: Retire Local access; WireGuard is internet-only (2026-09-28)

- **Changed in v2-158:** the stage-4 upgrade helper (`master_wg_upgrade.py`)
  and the Settings filter that dropped old `wgN`-scope overrides are removed; a
  fresh install never has those rows. Settings still rejects WG scopes, the API
  still refuses a `scope` field, and stage 7 still checks that registry column 3
  is `inet`.

- **Decision (v2-151):** supersedes DD-176 and DD-167's Local toggle. All
  existing/new WG networks and peers get internet egress only. Remove selectors
  from creation/settings, reject API scope, remove the CLI scope argument and
  reject/filter WG host overrides in Settings. DNS-only editing remains.
- **Enforcement:** WG INPUT drops precede established/ICMP and Tailscale accepts;
  FORWARD blocks private/CGNAT/link-local/multicast/reserved destinations before
  WAN allow, permits replies only from WAN and drops other WG traffic. NAT and
  required per-network transport UDP ports remain. Constants live in defaults.env.
- **Upgrade:** a stage-4 helper under install/module/settings locks normalizes
  only registry column 3 to fixed inet, removes WG overrides, disables exact old
  caddy-wg instances and removes their template/config/env files. It is fatal on
  failure and idempotent, not a general cleanup engine (narrow DD-96 exception).
  Keys, profiles, addresses, ports, DNS and other services remain unchanged.
- **Compatibility:** keep the nine-column registry layout to avoid unrelated
  data migration; no access setting is exposed. History remains historical.
  Existing profiles need no reimport unless they use a private DNS server,
  which is no longer reachable through this internet-only tunnel.
- **Verification:** HTTP/CLI refusal, upgrade/fresh/repeat/failure tests, UI
  creation/settings and read-only WG firewall category, plus real isolated
  Linux IPv4/IPv6 internet NAT/return and blocked host/private/tailnet traffic.

### DD-175: Remove obsolete firewall generation, not VPN requirements (2026-09-28)

- **Decision (v2-149):** remove the pre-module fallback that treated a missing
  module registry as WireGuard installed. Only an explicit `wireguard/calisiyor`
  record activates preserved network definitions. No configured networks means
  no project FORWARD/NAT chains or parent jumps, including after removal/rerun.
- Remove eight redundant terminal `RETURN` rules (four chains, two families)
  on a host with WG networks. User-chain fall-through has the same result;
  conditional settings returns, ordering, staging and recovery remain intact.
  Replace the obsolete one-element multiport generator with a single qB UI port
  match. The diagnostic reader accepts both spellings during upgrades.
- Check INPUT's full cardinality/guards/all ICMPv6 types and NAT cardinality,
  in addition to existing WAN/order/forward/settings checks. Stale extra rules
  must fail verification; applying the current source replaces them rather than
  importing old raw firewall dumps. A missing expected WG chain is still an error.
- **Not dead:** registered VPN endpoints (even stopped/zero-peer networks),
  loopback/established/control traffic, Tailscale's own chains and marks, exit-node
  forwarding, and the WAN Tailscale UDP fallback (DD-73). No counters-based deletion,
  package purge, network/profile deletion, peer-port opening or account change.
  Built-in Files/WebDAV/archive services remain; retired Docker/wg-easy/shared-root
  WebDAV generation is not reintroduced. Explicit user overrides stay authoritative.
- **Verification:** isolated Linux tests cover clean/repeated policy application,
  missing/empty/stopped module records with preserved networks, teardown/re-add,
  stale INPUT/FORWARD/NAT detection/removal and untouched third-party chains.
  Packet tests exercise IPv4/IPv6 allow/deny behavior. This is not a new OS image
  installation, reboot or real WireGuard-client throughput acceptance.

### DD-174: Remove synthetic closed WAN and tunnel-local port rows (2026-09-28)

- **Decision (v2-148):** extend DD-173 to Internet and WireGuard. WAN rows now
  describe only configured SSH/Tailscale ingress and registered IPv4 WG UDP
  endpoints; do not duplicate local/tailnet services, arbitrary listeners or
  PeerAPI into closed WAN entries. IPv6 WG endpoint placeholders are omitted
  because the existing WAN IPv6 policy does not permit those endpoints.
- Tunnel-local rows follow `master-firewall`: only IPv4 qBittorrent UI permits
  for networks whose Local access (`ui`) is configured. No closed placeholder
  for an `inet` network or IPv6 UI. Keep configured permissions independently
  of live sockets, stopped interfaces, peer count or recent traffic; the network
  selector and required VPN UDP endpoints remain intact even for an empty list.
- Explicit user allow/deny rules remain visible and editable through the existing
  draft merge, including a required base port the operator has turned off. Only
  synthetic defaults disappear. Loopback inventory, raw listeners and all technical
  rules are untouched. No service, saved rule, WG network or actual firewall policy
  is removed; unlisted ingress remains blocked by the existing default deny.

### DD-173: Tailnet port catalogue is configuration-driven, not socket-driven (2026-09-28)

- **Decision (v2-147):** stop synthesizing Tailscale management rows from every
  host listener. Generate them only from the shared per-family core allowlist
  and registered WireGuard endpoints, even when no socket is currently present.
  Operator-defined allows/denies remain independently visible and editable.
- The reported ports were not stale allow/deny rules: 20902 was qBittorrent peer
  traffic, 61006 its local UI, 61008/61009 the panel backends, and 2019 Caddy's
  loopback admin endpoint used for reload. Keep these required service settings;
  remove their implicit tailnet catalogue entries at the backend source, with
  no hardcoded port blacklist or frontend-only concealment. IPv6 Caddy/WebDAV
  entries are likewise absent while their configured service is IPv4-only.
- Default deny still blocks unconfigured new tailnet ingress. Keep raw listener
  inventory, technical firewall rules and explicit user overrides unfiltered.
  Do not alter socket bindings, qBittorrent's interface choice, Tailscale-owned
  chains, credentials, WG networks, forwarding or NAT. This is catalogue cleanup,
  not removal of listening services or a new firewall policy.

### DD-172: Minimum tailnet host ingress without changing VPN requirements (2026-09-28)

- **Decision (v2-146):** retain operator overrides at the head of CHAIN_SETTINGS,
  then allow only host SSH, Caddy, DNS TCP/UDP, folder WebDAV, Self PeerAPI TCP
  endpoints and registered WireGuard UDP endpoints from the tailnet. Caddy and
  WebDAV permits are IPv4-only, matching their actual template binds. Return these
  to the existing downstream policy; drop other new tailnet ingress before the
  unconditional acceptance in `ts-input`. Never edit Tailscale-owned rules.
- Registered WireGuard ports are intentional requirements, regardless of peers,
  handshakes or counters. Preserve their WAN/tailnet permissions, tunnel-local
  UI rules, interface state, forwarding, NAT, profiles and keys. Leave outbound
  torrent connections and established/related replies untouched.
- Use existing defaults/state port keys, not socket discovery, to admit ordinary
  services. Only Tailscale's own Self-advertised PeerAPI URLs may add dynamic TCP
  ports, validated against Self addresses and split by address family. Never
  allow a dynamic range, another peer's endpoint or an arbitrary listening app.
  Missing/not-ready daemon status does not prevent base host protection. The
  existing restart hook/watchdog checks changed endpoints; no new timer/cache.
- The port table derives tailnet baseline permissions from the same helper.
  Kernel firewall permission, socket binding and Tailscale's userspace services
  remain separate concepts: host INPUT is not a replacement for tailnet ACLs.
- Loopback/established guards precede overrides; overrides precede core allow/drop.
  Presence, exact cardinality and ordered comment identities are checked together
  so inserting a blanket RETURN/ACCEPT cannot silently bypass the new default.
  ICMP control traffic remains allowed. No package removal or listener restart is
  needed to close unnecessary *new inbound* qBittorrent peer connections.

### DD-171: Remove dead sharing lifecycle without deleting legacy data (2026-09-28)

- **Changed in v2-158:** the retired `/api/paylas` and `/api/paylas/kaldir`
  routes lost their 410 handlers and now answer like any unknown route (404). The
  reserved `.pay` name and its exclusions below stay.

- **Decision (v2-145):** remove unreachable public Files/WebDAV lifecycle and
  data-deletion branches, legacy marker readers/writers, shared-password command
  plumbing and credential-path defaults. Built-ins retain their installer-only
  lifecycle and internal registry IDs used by firewall, settings and DNS.
- Fresh installs create no `.pay/w` or `.pay/acik`. Existing `.pay` contents are
  neither migrated/deleted nor included in permission repair. Keep the reserved
  name and service/path exclusions: removing them would expose old metadata.
  The WebDAV unit tolerates a missing legacy path, not an accessible existing one.
- Retired Files endpoints return explicit 410 after security gates; `/api/state`
  stops reporting the misleading marker-derived summary. Current per-folder
  accounts remain exclusively in root-owned `webdav.json` and its gated API.
- Remove dead frontend helpers/styles and stale operational instructions. Keep
  historical decisions/designs/releases as history. Optional-app profiles, keys,
  user files, active API aliases and all actual runtime dependencies remain.
- Dependencies are already minimal for the current feature set: Python/RAR,
  network/firewall/DNS tools, systemd/core utilities and security-update packages
  all have callers. No apt purge/autoremove, package upgrades solely for cleanup,
  replacement runtime or new background service.
- Regression coverage exercises absent legacy directories, preserved metadata
  and private modes, marker symlinks, explicit retired-route errors/gates,
  built-in idempotency, current module lifecycle and temporary-login secrecy.

### DD-170: Contextual Files dock and automatic archive extraction (2026-09-28)

- **Decision (v2-143):** keep the address/search bar stable and show selected-file
  actions in a bottom dock, confined to Files. Reserve scroll space for the last
  row and wrap controls on mobile. Other pages never retain the dock.
- One archive vocabulary: creation always ZIP; extraction resolves supported
  RAR volumes and nested ZIP/RAR automatically. Default destination comes from
  `DOWNLOADS_SUBDIR` via file state, not the current source or torrent save path.
  Browse existing directories with the gated file API; failed/stale picker reads
  cannot select an unverified folder. Submit failures retain the form draft.
- Hide nested/depth controls and verbose explanations/statistics, not server
  protections. Keep shared byte/entry/time/depth limits, cancellation, safe paths,
  private staging and atomic no-replace publication. Automatic depth overflow
  fails the whole job; explicit legacy depth requests keep their earlier contract.
- Preserve original archives and per-archive output directories; assembling
  multipart contents does not mean flattening paths or overwriting same-name data.
- **Visual follow-up (v2-144):** implement approved alternative B: six equal
  icon-over-label cells, count and dismiss in a separate header, compact floating
  surface and a mobile 3×2 grid. Keep ineligible actions disabled in fixed slots
  so selection changes do not shift targets. Trash uses red ink, not a filled
  button; global keyboard focus and existing action/confirmation guards remain.
  No API, archive-worker, permission or sharing behavior changes.

### DD-169: Compact trash confirmation and inline share controls (2026-09-28)

- **Shares layout superseded by DD-192:** two connection cards replace the
  shared permission/duration columns. Partial updates, per-scope RW consent,
  exact expiry preservation and separate account management retain this rationale.

- **Decision (v2-142):** remove move-to-trash explanations/path/size and show
  only a short question, filename (ellipsized with full tooltip) or count,
  Cancel and Move. Bound dialog content so long names cannot push buttons out.
  Permanent purge warnings and typed confirmation for emptying Trash remain.
- Replace the stretched share cards with aligned responsive columns: folder/URL,
  username, access, duration, state and actions. Use native selects for access
  and 1/7/30-day or unlimited lifetime; save on change, still explicitly confirm
  granting write/delete access. Keep address and copy button adjacent.
- Manage now changes folder/account only; creation still offers RO/seven-day
  defaults. Reuse the existing save endpoint with partial existing-share bodies.
  Read omitted fields from the registry under its existing locks, not from a
  potentially stale browser row. Do not recalculate folder identity when only
  access/expiry changes. Existing RW grants need no new acknowledgement for an
  unrelated account/expiry edit; an explicitly supplied RW setting still does.
- Disable conflicting list actions during saves; ignore older list reads, retain
  confirmed values on failure and avoid polling redraws while a select has focus.
  The existing active WebDAV restart/rollback and stopped-service behavior remain.
  Durations start now, never silently extend during account/permission changes.

### DD-168: Eight-character minimum for service passwords (2026-09-28)

- **Decision (v2-141):** at the operator's request, lower the Konsol minimum
  from 12 to 8 characters for qBittorrent and folder WebDAV, in both browser
  forms and server validation. This was a panel policy, not a service limit.
  qBittorrent 5.1.0 accepts eight-character passwords; WebDAV's scrypt verifier
  has no twelve-character requirement.
- Keep the 256-character maximum, existing character restrictions, salted
  password hashing, blank-on-edit preservation and long random WebDAV password
  generator unchanged. Existing accounts are not rewritten or shortened.
- Eight characters allow weaker choices than twelve. This is a minimum, not
  a recommendation; longer unique passwords remain preferable.
- Regression tests reject seven characters before a write, accept eight,
  preserve blank edits, and check real HTTP authentication using isolated
  WebDAV fixtures and a disposable native qBittorrent profile.

### DD-167: Edit a WireGuard network without regenerating it (2026-09-28)

- **Need:** the network-card refresh action should also expose default DNS and
  local access. Previously the refresh icon meant destructive regeneration.
- **Decision:** replace that entry with “Arayüz ayarları”. Save edits the selected
  registry row's default DNS and `inet`/`ui` scope only. Keep key regeneration
  inside a separate danger section with the existing typed `onayla` confirmation;
  unsaved form choices are never silently applied by regeneration.
- **DNS:** a default for newly added peers, not a DNS server setting or a push
  to existing client devices. Existing profiles, keys, addresses, peer states,
  labels and ports are untouched. Existing peer DNS retains its own edit/QR flow.
- **Local access:** same narrow boundary as before: qBittorrent's UI via that
  network's IPv4-bound `caddy-wg@`, not Konsol/SSH/WebDAV/DNS or other networks.
  Explicit firewall overrides remain authoritative. Close the Caddy listener
  before restricting policy; open policy before starting it. Never restart
  WireGuard or wake a stopped network; stage its Caddy enablement for next start.
- **Concurrency/failures:** `master-wg --if wgN net-settings` holds the existing
  installer lock, checks the selected row's SHA256 revision under lock, and
  refuses pending settings transactions. Use bounded systemctl calls; ordinary
  failures/signals restore registry, Caddy env, firewall and prior listener state.
  Report incomplete rollback explicitly. This is a scoped command transaction,
  not a power-loss/SIGKILL recovery engine. Save is immediate: this setting does
  not change the Tailscale-only access path to Konsol.
- **Explicit attempts:** local-access changes reset the start-limit counters
  of the firewall and selected Caddy instance before applying, as module actions
  already do. Live repeated toggles exhausted the firewall's 12/300s budget and
  prevented rollback. Do not change the automatic restart-loop limits or reset
  other networks' counters; DNS-only changes still perform no service actions.
- **API/UI:** `POST /api/wg/nets/<iface>/ayarlar` accepts `{scope,dns,revision}`,
  retains Host/header/origin/module gates and validates IPs before delegation.
  Invalidate Settings' read cache after the attempt. Polling never overwrites
  the open form; failures preserve the draft and stale forms must be reopened.

### DD-166: Bounded multipart and nested RAR in Files (2026-09-28)

- **Need:** downloaded multipart RAR and inner RAR sets must open through the
  same Files workflow as ZIP, without deleting seeding/source files.
- **Decision:** install distribution `unrar` + `python3-rarfile` as base
  dependencies. Full unrar supports solid/RAR3/RAR5/volumes consistently;
  unrar-free/libarchive is not an equivalent backend. When apt has no candidate,
  add a dedicated signed Debian non-free or Ubuntu universe/multiverse source,
  including updates/security and Ubuntu ports for non-x86. Preserve other sources.
  The package carries the distro's non-free unrar license; no arbitrary binary,
  pip install or root extraction endpoint is introduced.
- **Boundary:** the existing unprivileged worker owns all destination writes.
  Copy descriptor-validated source volumes into bounded private staging, inspect
  metadata in a resource-limited child, then stream each member using `unrar p`.
  Never use extractor-controlled output paths. Bound time/output/memory, kill
  and reap the whole helper process group on cancel/error; reject links, duplicate
  or ambiguous names, encrypted/invalid archives, missing parts and changed sources.
  Preserve atomic publication and the existing aggregate ZIP byte/entry/layer limits.
- **Compatibility:** keep API operation `unzip` for both formats; label it
  “Arşivi aç”. Normalize later-part selection to the first, deduplicate nested
  volume sets and retain every source and inner archive. Compression still creates ZIP.
  Solid archives may re-decompress earlier members per streamed file; time limits
  deliberately win over unlimited CPU for pathological inputs.
- **Evidence:** `test_rar.py` covers volume selection, traversal/link/duplicate
  boundaries, budgets, CRC/source mutation, mixed nesting and real subprocess
  cancellation. Optional upstream fixtures exercise real RAR3/RAR5/solid/volumes;
  current live verification is recorded in `SESSION.md`, not inferred for Ubuntu.

### DD-165: One-click qBittorrent account save (2026-09-27)

- **Decision (v2-135):** replace account staging/review/60-second confirmation
  with one explicit Save. The former first button only staged credentials;
  opening the Web UI immediately afterward therefore still required the old
  login. Native browser username validation also needs an escaped hyphen for
  the modern HTML pattern `v` flag.
- Only an isolated username/password request commits immediately. Eligibility
  is decided by the worker, never a client flag. Folder and mixed requests keep
  confirmation, as do firewall edits; domain migration retains five minutes.
  Account edits cannot remove Konsol's network access, so connectivity approval
  adds no protection here. Successful saves do not revert after disconnect.
- Preserve revision/lock validation, stop/flush/snapshot/write/restart, durable
  pre-write recovery, commit markers and guard recovery for failure/process death.
  Keep stopped services stopped and unrelated profile keys untouched. A blank
  password preserves a stored hash, not a rotating temporary startup password.
- The UI reports success only for an explicit committed response, disables
  duplicate submission, clears secret fields and never stages the password.
  Unrelated drafts remain unapplied and use the refreshed revision afterward.
  Failed/ambiguous requests ask the operator to refresh and re-enter the password;
  no automatic credential retry or new dependency is introduced.

### DD-164: Incoming-network firewall tabs, not service buckets (2026-09-27)

- **Decision (v2-134):** implement the approved Tailscale (default), Internet,
  optional WireGuard and protected loopback categories. A service can have
  different permissions on different incoming networks, so it must not be
  assigned to just one global service bucket. WireGuard supports per-interface
  selection; installed-without-networks gets an empty state, not a fictional wg0.
- Public VPN UDP endpoints stay under Internet. Tunnel-client INPUT permissions
  are under WireGuard; Technical rules remains an all-network read-only view
  with original specs, order, ownership and counters, including FORWARD/NAT.
- A socket binding is not an end-to-end reachability test. The backend annotates
  addresses using state/network metadata and IPv6 zones, without scanning ports
  or inferring ownership from private IP prefixes. Fix ss's bracketed link-local
  zone parsing; keep unreadable/unknown distinct from no listener. Preserve known
  service names when the same listener appears under another traffic category.
- No firewall policy/worker, API write contract, dependency, bind address or
  privilege change. Preserve drafts across tabs, keyboard navigation, protected
  loopback and the existing apply/confirmation/rollback flow. DNS-only immediate
  Apply (DD-163) remains unchanged. Refresh is explicit, not background polling.

### DD-163: Immediate DNS-only Apply, retaining transactional recovery (2026-09-27)

- **Decision (v2-133):** remove the one-minute connection confirmation for
  DNS-only edits as requested. One Apply action validates, projects and restarts
  dnsmasq, then durably commits. Return an explicit committed result and refresh
  the UI without a review dialog, countdown or confirmation POST.
- The worker, not a client bypass flag, classifies DNS-only requests. Mixed
  firewall/qBittorrent drafts retain the existing review and 60 s confirmation;
  domain migration retains its separate 300 s/new-Host confirmation.
- Protect `panel.<LOCAL_DOMAIN>` before any mutation and disable its UI switch.
  Previously its disable could be staged but could never be confirmed. This
  preserves that restriction without relying on a now-removed confirmation.
- Keep locks, revision checks, validators, snapshots and the independent guard
  for apply failures/process death. Share the existing durable commit marker
  with confirmed transactions: a post-commit crash must not undo saved DNS.
  Successful DNS changes no longer automatically revert after disconnection.

### DD-162: Explicit firewall tables without changing policy authority (2026-09-27)

- **Decision (v2-132):** the user requested a full table, including short
  explanations, retaining on/off controls. Replace per-row disclosures and
  mobile cards with semantic row/column headers and bounded table scrolling.
  Service descriptions, source CIDR, address scope, draft/saved policy and
  edit/remove actions are visible together. Keep family/scope filters.
- Preserve the distinction between intended permission, an observed listener
  and actual reachability. No port scan or Tailscale ACL claim is inferred from
  an enabled switch. Loopback is protected; existing connections are not cut.
- The all-rules view adds conservative explanations without replacing raw
  specifications/order/counters. Foreign chains remain read-only. This is not
  an iptables editor/parser; port changes use the existing validated controller.
- No API, firewall worker, transaction deadline or privilege boundary changes.
  Switching a row only edits the in-memory draft until reviewed and applied.

### DD-161: Compact App Store with optional details (2026-09-27)

- **Decision (v2-131):** implement the user's approved second model: a compact
  list, not a grid of large cards. Each row shows icon, name, one-line description,
  live status, Details and Install/Open. A single selected panel below the list
  holds technical information and service/log/removal controls.
- Collapse explanations, not operational feedback. Server progress and failures
  stay visible in rows; mobile keeps both status and controls. Polling retains
  selected details, keyboard focus and log position; unchanged data avoids DOM
  replacement. Log HTTP errors cannot masquerade as successfully fetched logs.
- qBittorrent credentials are requested only from its own page, not by opening
  App Store or expanding technical details. Removal still requires confirmation
  and defaults to retaining profiles; files are not deleted.
- This changes presentation only: no backend/catalogue/dependency, firewall,
  DNS, privilege, CSP or transaction changes. Existing Model A routes remain.

### DD-160: Model A, one admin workspace and independent resources (2026-09-27)

- **Decision (v2-130):** implement the user's approved Model A. Remove the
  Applications launcher, Overview, dock and imitation window controls. Files is
  the default route; the sidebar contains App Store, installed apps and Settings.
  This supersedes DD-159's shell presentation only, not its service boundaries.
- CPU/RAM/disk belong below the sidebar menu. Sample CPU on a separate backend
  thread so a slow WireGuard command cannot stall host measurements. The gated
  resource endpoint does not enumerate ports/networks or invoke subprocesses;
  the legacy system API remains available. The browser polls independently and
  displays unknown values after failure/staleness instead of stale healthy data.
- Settings has System, Firewall, Caddy, Dnsmasq and Log. qBittorrent's own page
  holds its service controls, Web UI link and account/path forms. One shared
  draft/transaction controller prevents duplicated state or rollback logic.
- Files has Files, Shares, Archive jobs and Trash tabs, optional item details,
  and folder shortcuts only. ZIP submission opens job history; results return
  to Files. Background work and the existing unprivileged sandbox are unchanged.
- Clean installation still provisions protected infrastructure/Files/WebDAV,
  never optional apps or old credentials. No new production dependencies,
  external assets, auth bypass, network ports or automatic restore are introduced.
- v130 is prepared locally. Deployment/reset and fresh Debian/Ubuntu acceptance
  are separate steps; details and verification are in `model-a-clean-install.md`.

### DD-159: Desktop shell with protected Files, sharing and bounded ZIP (2026-09-25)

- **Decision (v2-129):** implement the approved desktop prototype after explicit
  authorization to deploy/test on `nrm`. A lightweight single-workspace web shell,
  not KDE; existing Settings and backend authority boundaries are retained.
- Files and folder WebDAV are permanent panel capabilities. ZIP is part of Files,
  not a separately installed unpacker. Only WireGuard/qBittorrent remain in the
  public App Store catalogue; infrastructure cannot be removed from its UI/API.
- Retain the internal `dosya`/`paylasim` template paths and registry rows so
  domain renaming, status and firewall consumers remain compatible. The installer
  activates/checks both; unchanged reruns do not bounce healthy services or
  rewrite account/history data. Older stopped instances become enabled built-ins.
  This supersedes DD-148/150/158's optional Files/WebDAV lifecycle only.
- Use a stdlib ZIP worker inside the unprivileged file service, with one job at
  a time, global byte/entry/depth/deadline limits, early central-directory checks
  and descriptor-safe access. Atomic no-replace publication avoids half-extracted
  visible results; errors/cancellation discard private staging. This is bounded
  ZIP support, not an arbitrary-format archive daemon or a filesystem snapshot.
- `/srv/.arsiv` is private staging and bounded history, not a backup. Installer
  permission repair excludes it. Restart records interruption rather than claiming
  to resume work. Source ZIPs remain, including nested ZIPs; unsafe duplicates,
  links and cross-device paths fail closed.
- Exact limits, API and recovery caveats: `desktop-and-archives.md`.

### DD-158: Independent folder accounts and descriptor-safe WebDAV (2026-09-25)

- **Extended by DD-192:** the account/folder remains shared between its two
  connections; enabled state, permission and expiry are now per connection.

- **Decision (v2-128):** implement Files v09 and replace the single shared
  account with a bounded folder registry, separate users, RO/RW and stable IDs.
  The user authorized implementation and deployment to disposable `nrm`.
- **Implementation choice:** reuse the existing Python stdlib backend approach
  with a descriptor-based DAV handler, not the proposal's tentative per-share
  rclone processes. A single credential-loaded service avoids per-share ports,
  Caddy configuration and process lifecycle. Root management and unprivileged
  data access stay separate; hashes never go to the file-manager API/browser.
- **Trade-off:** filesystem isolation between shares is application-level,
  not one OS sandbox per account. The supported DAV subset deliberately lacks
  locks, PROPPATCH and directory COPY; native-client acceptance is still required.
  No claim of full WebDAV compliance. See `folder-shares.md` for exact limits.
- Per-request root birth-time/inode checks fail closed on a replaced folder;
  explicit path editing keeps the share ID. Parent/child grants are rejected.
  Expiry runs on access/transfer chunks. Registry mutation restarts the active
  server and cuts existing transfers; stopped modules stay stopped.
- Passwordless Konsol remains an administrator interface. Recipient access must
  be restricted to WebDAV by manually reviewed Tailscale policy; the installer
  does not edit policy. Legacy broad accounts/URLs are not kept as a bypass.
- Supersedes DD-141/149/152's common-account, writable-symlink-root and rclone
  details, not their Tailscale-only publication or module lifecycle boundaries.

### DD-157: Rename the local domain as a confirmed transaction (2026-09-25)

- **Request:** explain firewall addresses, remove the unnecessary health site,
  and let the operator rename `ayc` from the Caddy tab. The static v08 mockup
  remains frozen; this extends the production implementation only.
- **Health:** the standalone `ok` response duplicates stage 7's real Konsol
  page and backend checks. Remove its site, DNS record and dedicated probe;
  retain the stronger page/API/Host/header checks. An unmatched Host may receive
  an empty Caddy response; HTTP status alone is not evidence of a health route.
- **Scope:** a single validated local suffix, not an arbitrary Caddy editor or
  public-domain/HTTPS workflow. All installer-owned active and staged names move
  together. Custom DNS targets and disabled state survive; account/profile/data
  files and IP-based share links are not part of the write set.
- **Transaction:** use DD-156's worker, durable snapshots and independent guard,
  but prohibit combining a domain change with other settings. Give five minutes
  for a new-address connection. Only the HTTP Host supplied by the server, not
  one in the client's JSON body, proves the new panel name at confirmation.
  No retained aliases. The root backend reads state dynamically and is not
  restarted; Caddy reloads gracefully. Restart the file backend only if active,
  since its allowed Host is a startup argument. Warn about active file transfers.
- **Persistence:** `SETTINGS_FILE.domain` becomes authoritative only on commit,
  and overrides stale installer input on re-runs. The portable installer never
  copies or rewrites the operator's input file. Module renderings are included
  so reinstalling a module cannot reintroduce the old suffix.
- **Concurrency/recovery:** settings and tailnet refresh share `state.lock`;
  refresh skips a busy cycle. Rollback replaces only `LOCAL_DOMAIN`, preserving
  any newly detected Tailscale addresses. File snapshots and commit-marker crash
  recovery retain DD-156's behavior. A stopped file module is never started.
- **Manual boundary:** the user must first add the new restricted DNS suffix in
  Tailscale Admin and retain the old mapping until successful confirmation.
  The UI shows both URLs even if the old request disconnects. No Tailscale
  account/ACL writes are attempted. See [Tailscale DNS reference](https://tailscale.com/docs/reference/dns-in-tailscale)
  and [Caddy reload](https://caddyserver.com/docs/command-line#caddy-reload).

### DD-156: Transactional settings management in Konsol (2026-09-24)

- **Context:** the operator approved the four-tab v08 prototype and then
  requested implementation and a version bump. This supersedes DD-155's
  read-only restriction for firewall, DNS and the selected qBittorrent fields;
  Caddy and third-party firewall chains remain read-only.
- **One persistent owner:** `SETTINGS_FILE` holds confirmed firewall overrides
  and DNS choices. The installer, module DNS rendering and firewall refresh
  consume it, rather than resetting it. qBittorrent's own profile remains
  its account/path source; no duplicate account store or backup exporter.
- **Safety transaction:** a separate systemd worker consumes JSON on stdin,
  under install/module/settings locks. Before any mutation, root-only
  `SETTINGS_PENDING_FILE` records the previous affected files, service state,
  candidate policy, boot ID and monotonic deadline. A permanent systemd timer
  recovers abandoned work (180 s apply deadline, then 60 s to confirm).
  Failed rollback remains pending for retry. A commit marker makes recovery
  safe across a crash between writing the confirmed file and deleting pending.
- **Confirmation:** trusted proxy client information must identify a tailnet
  address. An existing TCP connection alone is not proof that the next one
  will work: effective denies of the confirming client's Caddy/DNS ports, or
  disabling the console's own DNS name, cannot be committed. This is not an
  external port scan or a test of Tailscale ACLs. The UI separates permissions
  and listeners, and warns before applying exposure changes.
- **Firewall:** a dedicated `CHAIN_SETTINGS`, before `ts-input`, holds only
  validated TCP/UDP port rules (family, scope, optional source CIDR, action).
  Loopback/established flows return to the baseline; ICMPv6 is not editable.
  No Tailscale/third-party chain is rewritten. All live table rules/counters
  are visible; only operator port overrides are editable. Ordering and exact
  membership are verified. The existing refresh mechanism consumes overrides.
- **DNS:** base/module interface-name entries retain their owner and get a
  reversible disabled marker; custom exact records and upstream IPs have a
  separate file. Only names inside `LOCAL_DOMAIN` may be added. Base/module
  name collisions, non-public upstreams and configured self-addresses are
  rejected. `no-resolv` and `local=/DOMAIN/` stay; forwarding never leaks
  disabled/missing private names or changes Tailscale Admin DNS. DNS is
  syntax-checked before restart. No public listener is added.
- **qBittorrent:** stop, snapshot the flushed profile, change only requested
  keys, restart if it was running. New passwords use qBittorrent's PBKDF2
  format; absent password means preserve. UI/API/logs never return a hash or
  new password. Snapshot files contain only existing profile data, mode 0600.
  Descriptor-relative no-follow file access protects the user-owned profile
  path. Download targets must exist, be canonical and non-hidden, and lie
  under downloads/media; a write probe runs as the service UID, with no
  recursive ownership changes. A dedicated unit drop-in grants that path.
  Existing torrent data and incomplete locations are never migrated.
- **Scope:** new HTTP APIs retain Host, `X-Konsol`, same-origin and no-store
  protections. Drafts are browser-memory-only. No new dependency, Docker,
  reconciliation engine, automatic deployment or server backup is introduced.
- **Verification:** isolated real-binary Debian 13 tests, including actual
  qBittorrent login with the new hash, DNS forwarding/private-zone separation,
  firewall order/tailscale preservation and rollback; real systemd timer/worker;
  Python/Bats tests and Playwright on the production page at desktop/mobile
  widths. Ubuntu was not freshly provisioned for this revision.

### DD-155: Konsol shows the server's settings, read-only (2026-09-19)

- **Partly superseded by DD-156:** the read-only restriction is lifted by
  transactional settings. Still current: `GET /api/konsol/ayarlar`, the
  classification of live firewall rules and the `TORRENT_KEYS` read.

- **Context:** the user wanted to see, in Konsol, the firewall rules, the
  Caddy addresses, qBittorrent's download path and dnsmasq's names. The
  design (`docs/design/konsol-ayarlar-v07.html`, values read from `nrm`) was
  accepted with three choices the user confirmed: read-only, raw views kept
  in closed boxes, packet counters shown.
- **Decision:**
  - A new page, Ayarlar, fed by one `GET /api/konsol/ayarlar` on the root
    backend (it already runs as root and behind the Host and `X-Konsol`
    gates). It reads only when the page asks; a 5 s cache absorbs repeated
    loads and "Yenile" (`?yenile=1`) skips it.
  - **Read-only on purpose.** Every value already has one owner: the
    installer (`kurulum.env` and the defaults), a module, or qBittorrent
    itself (**DD-151**). Writing from Konsol would open a second source of
    truth that the next install reverts, and move towards the reconcile
    engine the project refuses. Each row says where its value is changed.
  - **Firewall from the live rules, not from the intent.** The backend runs
    `iptables`/`ip6tables -v -S` on the three project chains and classifies
    each rule by interface using the same `state.env` and network registry
    the ports card reads. A rule it does not recognise (added by hand, or
    drift) is listed under "Tanımsız kurallar" instead of being hidden.
    `master-firewall --check` gives the status. Counters show what each rule
    caught since boot (on `nrm`: over 1600 packets dropped on the WAN within
    hours).
  - **Caddy and dnsmasq from their files.** A small parser reads the
    installer's own templates as rendered (site lines, `@matcher path`,
    `handle`, `reverse_proxy`, `file_server`, `respond`), not Caddy's full
    grammar. Module files are attributed to their module; `Caddyfile.wg`
    is expanded per `ui` WireGuard network. `CADDY_WG_FILE` joins
    `state.env` for this.
  - **qBittorrent: paths only.** Only the path and port keys of
    `qBittorrent.conf` are read (`TORRENT_KEYS`); the password hash never is.
    The page warns when the save or temporary path leaves `DOWNLOADS_PATH`:
    the unit's sandbox (**DD-151**) refuses writes there, so downloads would
    fail and never show in Dosyalar.
- **Found on `nrm`:** the WireGuard registry writes an IPv6 subnet as
  `…::0:0/112` while `ip6tables` prints `…::/112`; subnets are compared as
  networks (`ipaddress`), not as text.

### DD-154: One console name, one current export (2026-09-19)

- **Context:** simplifying after **DD-152**/**DD-153**. The Caddyfile still
  redirected `wg.`, `dosya.` and `file.${LOCAL_DOMAIN}` to Konsol (the old
  WireGuard panel, file panel and FileBrowser names, **DD-140**, **DD-146**),
  each with a dnsmasq name and a stage 7 check. `Data/app/` held every
  exported installer since v2-96.
- **Decision (the user agreed to both, 2026-09-19):**
  - The three old names are gone: no Caddy site, no dnsmasq record, no check.
    `SERVICE_NAMES` is `health panel`. Bookmarks must use `panel.<domain>`.
    The backends already accepted only `panel.<domain>` as Host.
  - The exporter keeps only the current version in `Data/app/`, as it already
    did in the repository root; older exports live in Git history.

### DD-153: The base installs only what the base uses (2026-09-19)

- **Context:** after **DD-152** the user asked to clean the services' old
  dependencies before simplifying further. A fresh v2-122 install on `nrm`
  pulled 51 packages. Checked one by one against the code: every
  `defaults.env` and `state.env` key has a reader, every shell function is
  called and no unit names a removed service — but three base packages
  served nothing the base does.
- **Decision:**
  - `gnupg` goes. It was there for one `gpg --dearmor` of Caddy's repository
    key and brought about 15 packages (dirmngr, gpg-agent, gpgsm, pinentry…).
    The armored key is now stored as `caddy-stable-archive-keyring.asc` and
    named in `signed-by=`; apt reads armored keys itself (apt 1.4+, measured
    with apt 3.0.3 on `nrm`: `InRelease` verified). Tailscale's key is already
    a binary `.gpg` download.
  - `gawk` goes. It came with the v1 installer; no script uses a gawk-only
    feature (no regex intervals, `gensub`, `strftime`, `asort`, `IGNORECASE`,
    `PROCINFO`), and the code already avoided intervals for mawk. `awk` is the
    distribution's `mawk` (1.3.4 on Debian 13).
  - `apache2-utils` leaves the base: only Paylaşım's account uses `htpasswd`,
    so `master-modul` installs it (`share_tools`) before every step that
    writes or checks the account (`kur`, `baslat`, `parola`, `uygula`).
    `hesap` only reads the plain account file and never needs it.
- **Kept on purpose:** `jq` (Tailscale login state), `dnsutils` (`dig` in the
  name checks), `python3` (Konsol and `master-modul`), `ethtool` (UDP GRO),
  `unattended-upgrades` (**DD-113**) and the essential tools listed for
  clarity (`coreutils`, `util-linux`, `diffutils`).
- **Upgrading:** a host installed earlier keeps the packages; nothing removes
  them (fresh-install rule).

### DD-152: No Docker — Paylaşım runs rclone on the host, Arşiv açıcı is dropped (2026-09-19)

- **Context:** after **DD-151** only two modules used Docker: Paylaşım (rclone)
  and Arşiv açıcı (unpackerr). For them the installer kept a whole layer:
  Docker's apt repository and packages, `daemon.json`, a `docker.service`
  drop-in, the `MASTER-DOCKER` chain behind a `DOCKER-USER` jump, and the
  engine itself (dockerd, containerd, shims and port proxies: about 110–150 MB
  of memory measured on `nrm`). On 2026-09-19 the user decided to remove the
  Docker dependency completely, to drop Arşiv açıcı, and to run the share
  WebDAV on the host.
- **Decision:**
  - The installer installs no Docker: no repository, packages, daemon
    settings or drop-in. The firewall has no `MASTER-DOCKER` chain and never
    touches `DOCKER-USER`; `CHAIN_DOCKER` is gone from the defaults and the
    state file; `master-firewall.service` is `PartOf=tailscaled.service` only.
    The nft backend gate (**DD-106**) stays: the firewall still orders its
    chain behind tailscaled's `ts-input`.
  - Arşiv açıcı (unpackerr) leaves the catalogue, the templates, Konsol and
    the downloads tree (`.unpackerr`). Nothing replaces it.
  - Paylaşım becomes `master-paylasim.service` with the container's exact
    command: `rclone serve webdav SERVER_ROOT/SHARE_DIR/w --copy-links
    --read-only --dir-cache-time=10s` with the htpasswd account, on
    `127.0.0.1:SHARE_PORT`. Caddy, the names, the account (**DD-149**) and the
    share links (**DD-141**) are unchanged, so Infuse sees no difference.
- **Which rclone (the user chose among three):**
  - Chosen: rclone's official release binary. `RCLONE_VERSION` (1.75.1) and one
    SHA256 per architecture are pinned in `defaults.env`, taken from rclone's
    signed `SHA256SUMS` (key `FBF7 37EC E9F8 AB18 604B D2AC 9393 5E02 FF3B 54FA`,
    good signature checked on `nrm`); downloads.rclone.org and the GitHub
    release list the same values. This is the program the container ran.
  - Rejected: the distribution package. Debian 13, Ubuntu 24.04 and 26.04 ship
    1.60.1 (2022); Debian's security tracker lists about 25 open CVEs for it in
    trixie, one of them (CVE-2026-88015, a Range-header panic) in HTTP/WebDAV
    serving itself.
  - Rejected: nginx with the WebDAV module — a second web server next to Caddy,
    a new configuration never tried with Infuse, and on Ubuntu the module
    lives in universe.
- **Getting rclone:** `master-modul` downloads only when the installed binary's
  `rclone version` is not the pinned one: HTTPS only, the checksum before the
  archive is opened (Python's `zipfile`, no `unzip` package), the binary
  written next to `RCLONE_BIN` (`/usr/local/lib/master-stack/rclone`) and
  moved over it. `kaldir` keeps it, as qBittorrent's package stays
  (**DD-151**). The unit's description carries the version, so a new pin
  changes the rendered unit and the next installer run re-applies an
  installed share: download, then restart.
- **Sandbox:** the service runs as `DOWNLOADS_UID` (it reads what qBittorrent
  and Konsol write, never as root), with `ProtectSystem=strict` and nothing
  writable, `ProtectHome`, private `/tmp` and devices, no new privileges, an
  empty capability set, `IPAddressDeny=any` with `IPAddressAllow=localhost`
  (it cannot connect out), the kernel protections and
  `MemoryDenyWriteExecute`. The account file stays root-only on disk and
  reaches the service as a systemd credential (`LoadCredential=`); systemd
  copies it at start, so "Yeni parola" restarts the service.
- **The trash is an empty tmpfs, not an inaccessible path:** measured on
  `nrm`, a single share link pointing into an `InaccessiblePaths=` directory
  makes rclone's whole listing fail (`EACCES`, HTTP 500, every share gone),
  while a dangling link (`ENOENT`) is only skipped.
  `TemporaryFileSystem=SERVER_ROOT/.cop:ro` turns a link into the trash into a
  dangling one. The container, which mounted all of `/srv`, could see the
  trash; the service cannot.
- **Checks (`kur`, `baslat`, `uygula`, `parola`):** the unit is active, runs as
  `DOWNLOADS_UID` with the expected command line, has the trash tmpfs, its
  own sockets are only `127.0.0.1:SHARE_PORT`, an unauthenticated request gets
  `401` and the account `207`; then the name and the Infuse address as
  before. A failed install is taken back (names, marker, unit).
- **Upgrading:** per the fresh-install rule there is no clean-up code: a host
  from an earlier version keeps Docker, its containers and images until it
  is reset. Reset and install fresh; Paylaşım generates a new account.
- **Amended (recorded 2026-10-05):** rclone and its trash tmpfs are gone. Since
  v2-126..v2-129 (commit 18b7ba7, DD-158) the Python WebDAV unit lists the trash,
  and `.pay` when present, in `InaccessiblePaths=` (mode 000 inside the unit, checked
  on nrm 2026-10-05). The tmpfs reasoning above applied to rclone's link following.
- **Found in the live trial (v2-122):** right after `systemctl restart` a
  `Type=simple` unit is "active" while its process is still root (systemd
  switches to `User=` just before exec), so an immediate owner check failed
  once ("Yeni parola"). The unit is `Type=exec` now, and `master-modul` reads
  the owner of every module's main process until it matches (about 5 s at
  most). rclone exits with 143 on SIGTERM; `SuccessExitStatus=143` keeps a
  stopped share from showing as failed.

### DD-151: qBittorrent is a host module; Dozzle and the base Compose project go (2026-09-18)

- **Context:** stage 4 of **DD-148**. qBittorrent (LinuxServer image) and
  Dozzle were the base Compose project, the input file held both accounts and
  **DD-129** rewrote qBittorrent's settings on every run. The approved design
  lists qBittorrent as a Konsol module. The operator chose (2026-09-18): the
  settings are written once, no peer port is opened, the package stays on
  removal.
- **Decision — qBittorrent:**
  - It becomes the `torrent` module with runtime `host`: the distribution's
    `qbittorrent-nox`, run through the package's template unit as
    `qbittorrent-nox@<downloads account>.service`. Its files keep the owner
    Konsol and Arşiv açıcı use. No image, no container, no bind mounts; its log
    is the unit's journal.
  - The drop-in `qbittorrent-nox@.service.d/master-stack.conf` does what the
    container's mount list did: profile in `TORRENT_PROFILE_DIR`
    (`/var/lib/qbittorrent`, `HOME` and `XDG_*`), `UMask=0002`,
    `ProtectSystem=strict` and `ProtectHome` with only the profile and
    `DOWNLOADS_PATH` writable, the trash and the share root inaccessible (the
    **DD-144** promise), no new privileges, kernel and clock protections,
    address families limited to UNIX, IPv4, IPv6 and netlink.
  - **Settings once (reverses DD-129):** when the profile has no
    `qBittorrent.conf`, `master-modul` seeds a minimal one — save and
    temporary paths, web UI on `127.0.0.1:TORRENT_UI_PORT` with localhost
    authentication on, UPnP and port forwarding off, the legal notice
    accepted. Nothing rewrites it afterwards; `uygula` refreshes only the
    drop-in and the names. What the operator changes in qBittorrent stays.
  - **No account in the installer:** `TORRENT_USER`/`TORRENT_PASS` and
    `DOZZLE_USER`/`DOZZLE_PASS` leave the input file, which now holds only
    `SSH_HOST` and `LOCAL_DOMAIN`. Until a password is set in its UI,
    qBittorrent prints a temporary one to its journal on every start.
    `master-modul hesap torrent` reads only the current start's journal
    (`_SYSTEMD_INVOCATION_ID`), so an old password is never shown. Konsol's
    card shows the user and whether the password is temporary. The temporary
    password itself appears only on request, for 30 s, and is audited like
    Paylaşım's. `gunluk` masks that line.
  - **No inbound peer port (reverses DD-63's publication and the torrent half
    of R12):** qBittorrent only connects out. `TORRENT_PUBLIC_PORT`, the WAN
    `ACCEPT` in `MASTER-INPUT`, the `RETURN` in `MASTER-DOCKER` and the port
    rows go. Trade-off, accepted: fewer peers on poorly seeded torrents, and
    nothing of the torrent client listens on the WAN.
  - **Names:** `torrent.<domain>` comes and goes with the module (a Caddy
    import and a dnsmasq file, as for Paylaşım). `caddy-wg` keeps serving only
    the qBittorrent port on `ui` networks; without the module it answers `502`.
  - **Install checks:** the unit is active, runs as `DOWNLOADS_UID` and
    carries the two inaccessible paths; the API answers `403` without a login
    on loopback and through `torrent.<domain>`; the name resolves. A failed
    install is taken back.
  - **Removal:** `kaldir` removes the names and the drop-in and disables the
    unit; the package stays, as WireGuard's do (**DD-150**). `--veri` deletes
    the profile (settings and torrent list), only under `/var/lib`. A
    downloaded file is never deleted.
- **Superseded in part by DD-209 (2026-10-03):** qBittorrent now runs as a Podman container
  (quadlet, digest-pinned image); the settings seed, account, journal and folder rules below
  still hold. The paragraph that follows is the 2026-09-18 reasoning.
- **Why host and not the container:** one image fewer to follow and pin, a
  sandbox that says what the mounts said, the first-login password in a
  journal Konsol already reads, and the same start/stop path as the other host
  units.
- **Dozzle goes:** every module card has a Günlük panel (**DD-148**) and the
  only containers left belong to modules. Dozzle was the last input-file
  account and an image to follow.
- **No base Compose project:** the installer still installs the Docker engine
  and the Compose plugin for the Docker modules, but renders no
  `/root/docker/compose.yaml`, pulls no image and asks no pull question on
  re-runs. Stage 7 no longer checks containers.
- **Upgrading a v2-117 host:** per the fresh-install rule there is no clean-up
  or adoption code: the old containers, `/root/docker` and the old qBittorrent
  data stay until the host is reset. The four account lines must leave
  `kurulum/kurulum.env`, or the unknown-field gate stops the run before any
  change.
- **Verified:** bats (module lifecycle with fakes, first-login parsing, the
  root backend's account route, Konsol's card) and the Konsol page against a
  mock backend; live on `nrm` (Debian 13, `qbittorrent-nox` 5.1.0) on
  2026-09-18 with v2-119: install, stop/start, remove and reinstall (settings
  file unchanged), `--veri` (profile gone, new temporary password), reboot.
  Inside the unit's mount namespace the trash and the share root are
  unreadable and only `DOWNLOADS_PATH` and the profile are writable.
- **Local Peer Discovery off (v2-120):** the live run showed qBittorrent
  announcing on UDP 6771 on every interface, the provider's LAN included —
  it multicasts the info-hashes of what the server downloads to that
  segment, and there are no local peers to find on a server. The first
  settings now carry `Session\LSDEnabled=false`. The random peer port itself
  still listens on every interface; binding it to the WAN interface was
  rejected because a renamed interface would stall every torrent without a
  clear error, and the firewall already drops new WAN traffic to it.

### DD-150: Dosya yöneticisi and WireGuard are Konsol modules (2026-09-18)

- **Context:** stage 3 of **DD-148**. The file backend and the WireGuard layer
  were part of every install; the approved design (v06) lists both as
  one-click Konsol modules, with Paylaşım depending on the file manager.
- **Decision:**
  - `dosya` (Dosya yöneticisi) and `wireguard` (WireGuard) join the catalogue
    as Konsol modules. They are installed or removed, never stopped: a
    stopped file manager or WireGuard layer would only be a broken page.
  - The installer still installs the tools (`master-files-panel`, `master-wg`),
    the downloads account, the `SERVER_ROOT` tree, the `caddy-wg@` template and
    `Caddyfile.wg`. It renders the file backend's unit to `MODULES_DIR/dosya/`
    instead of `UNIT_DIR`, and no longer installs WireGuard packages, loads the
    kernel module or starts networks.
  - `master-modul kur dosya` places the unit, starts it and proves what stage 7
    used to prove (runs as `DOWNLOADS_UID`, answers through Caddy, `403`
    without `X-Konsol`); a failed start is taken back. `kaldir` removes the
    unit; `--veri` empties the trash, which the operator had already deleted.
  - `master-modul kur wireguard` installs the packages, loads the kernel module,
    registers itself, re-applies the firewall and starts the registry's
    networks. `kaldir` closes every `wg-quick@`/`caddy-wg@` unit, unregisters,
    re-applies the firewall and keeps `/etc/wireguard` (a reinstall brings the
    networks back); `--veri` deletes the keys, profiles and registry. The
    packages stay installed: removing them buys nothing and a reinstall
    would only fetch them again.
- **Firewall hook:** `master-firewall` reads the module registry and ignores
  the network registry unless `wireguard` is registered, so a kept registry
  never opens ports after removal. It checks the registry, not a running unit:
  the firewall must be right at boot, before any unit starts. The module is
  registered before the firewall is re-applied on install and unregistered
  before it is re-applied on removal.
- **Other consumers:** `master-wg` refuses every command but `version` without
  the module (wireguard.command then shows why). The root backend never runs
  `master-wg` without it: `/api/wg/state` answers `installed: false` with no
  networks, changes get `409`, profiles `404`.
- **Dependencies:** `kur paylasim` needs `dosya`, `kaldir dosya` refuses while
  `paylasim` is installed. Konsol queues the pair: "… ile birlikte kur"
  installs the dependency first; "Birlikte kaldır" removes the dependent
  first (keeping its data). The queue lives in the page; if the page closes
  mid-way the operator clicks again.
- **Konsol without the modules:** the Dosyalar and WireGuard pages and menu
  items appear with their modules; a bookmark to a missing page opens Modüller.
  The page never asks a backend that is not there (the file backend is behind
  Caddy, which would answer 502). The disk card takes total and free from the
  root backend (`/api/konsol/kaynaklar` → `root`, `disk`) and shows the
  downloads/trash breakdown only with the file manager.
- **Re-runs:** a changed unit or script re-applies an installed file manager
  (restart and checks); WireGuard is re-applied on every run while installed
  (packages after an OS upgrade, kernel module, networks). Stage 7 checks each
  only while its module is installed.
- **Fixed in v2-119:** the root backend's sandbox makes `/etc/wireguard`
  writable, and systemd refuses to start a unit whose `ReadWritePaths=` is
  missing. Before DD-150 `wireguard-tools` created the folder during the
  install; after it, a fresh v2-118 install stopped in stage 7 with Konsol
  down. The installer now creates the folder (`0700`) before starting the
  backend, and the unit marks the path optional (`-`), so a folder deleted by
  hand degrades WireGuard changes instead of taking Konsol down. The folder is
  created in the base rather than by the module because the backend's mount
  namespace is fixed at its start: a folder that appears later is read-only
  inside it until a restart.
- **Upgrading a host installed before v2-117:** its file backend and WireGuard
  layer were started by the installer and are not in the module registry.
  Per the fresh-install rule there is no adoption code; reset the host and
  install the modules from Konsol.

### DD-149: Paylaşım is a module with a generated account (2026-09-18)

- **Partly superseded by DD-158 (and DD-152, DD-159, DD-171):** the generated
  shared account, htpasswd, rclone and `.pay/acik` marker are gone and WebDAV
  is built in. Still current: the module-name lifecycle (Caddy imports from
  `CADDY_MODULES_DIR`, dnsmasq drop-ins, validate-then-swap, Caddy reloaded
  and dnsmasq restarted, `master-modul uygula` re-applies changed files).

- **Context:** stage 2 of **DD-148**. The share WebDAV (rclone, `paylas.<domain>`,
  `<ts-ip>:61010` for Infuse) was wired into every installer stage and took
  its account from `SHARE_USER`/`SHARE_PASS` in `kurulum.env`. The approved
  design (`docs/design/konsol-moduller-v06.html`) makes it a Konsol module
  that generates a strong account and offers "Yeni parola".
- **Decision:**
  - The base Compose file keeps Dozzle and qBittorrent. `modules/paylasim/`
    holds the rclone service (unchanged hardening), a Caddy site and a dnsmasq
    name; the installer renders them and never installs the module.
  - The account is generated on the server: user `SHARE_ACCOUNT` (`paylasim`),
    `SHARE_PASSWORD_LENGTH` (20) characters from an alphabet without
    `0 O 1 l I` (it is typed on a TV remote), from Python's `secrets`. The
    plain `paylasim.cred` is the source of truth and the bcrypt
    `paylasim.htpasswd` is derived from it; both are `0600 root`. The password
    goes through stdin only (`htpasswd -i`, curl `-K -`): never an argv, the
    progress file, the journal, `state.env` or Caddy's environment (Caddy
    runs with `--environ`, which logs its environment).
  - bcrypt keeps htpasswd's default cost: the password is random with about
    117 bits, and rclone checks Basic auth on every Infuse request.
  - **DD-119** ("the input file is the truth") no longer covers the share:
    there is no input. A valid existing account is reused on `kur`, so a
    reinstall keeps Infuse working; `kaldir --veri` or "Yeni parola" changes it.
- **Why the root backend shows the account:** the file backend used
  `LoadCredential=` with an absolute path. systemd refuses to start a unit
  whose credential file is missing, so without the module (or after
  `kaldir --veri`) the whole file API would be down, and the copy it held
  would go stale after "Yeni parola". The root backend reads the file through
  `master-modul hesap` inside its read-only sandbox; the password is returned
  only on `?parola=1`, audited without the value, and hidden again in the
  page after 30 s. The file backend never sees the account.
- **Why a marker file:** `/etc/master-stack` is `0700`, so the file backend
  (uid 1000) cannot read the module registry. `master-modul` writes
  `SERVER_ROOT/.pay/acik` on `kur` and removes it on `kaldir`; without it the
  backend refuses new shares (`409`) and Konsol hides the share controls. It
  is created with `mktemp` and renamed, because `.pay` belongs to uid 1000.
- **Names come and go with the module:** the base Caddyfile imports
  `CADDY_MODULES_DIR/*.caddy` (after the global options; an empty glob is
  valid), and the name is a drop-in in `/etc/dnsmasq.d`. Temporary files
  start with a dot, which Caddy's glob and dnsmasq's directory scan skip. Each
  change is validated first (Caddy with the real address; the whole dnsmasq
  configuration, not only the base file) and taken back if it fails. Caddy
  is reloaded, never restarted: it also serves Konsol, whose page is polling
  the progress, and a failed reload keeps the old configuration. dnsmasq is
  restarted, because SIGHUP does not re-read `interface-name`.
  - The port is written into the site literally. An unset `{$SHARE_PORT}`
    would silently fold the site onto port 80. The address stays
    `{$TAILSCALE_IPV4}`, which `refresh-tailnet-config` keeps current.
  - The names follow the *installed* state: they stay while the module is
    stopped (the name answers 502) and go on `kaldir`, before the container.
    The container is started and checked before the names are published.
- **Checks move with the module:** stage 7's share checks (health, single
  network, read-only runtime, loopback-only publish, `401`, the name and the
  Infuse address) run in `master-modul`, plus a `207` with the account. A
  failed `kur` takes back the names, the marker and the container. Stage 7
  keeps the share-root owner and the qBittorrent-cannot-see-`.pay` checks.
- **Re-runs:** `master-modul uygula` re-applies an installed module whose
  rendered files changed (a new domain, a new image) and starts it only if it
  is registered as running; it writes no progress line.
- **Removal:** `kaldir` keeps the account, the registry and the links, so a
  reinstall restores the same links and login. `--veri` deletes the account
  files, `.pay/kayit.json` and the symbolic links in `.pay/w` with
  `find -maxdepth 1 -type l -delete`; link targets and anything else in that
  folder stay. **DD-148**'s "files under `SERVER_ROOT` are never module data"
  now reads "user files are never module data".
- **Network name:** the module uses its project's default network
  (`paylasim_default`), so it never collides with the `paylasim` network the
  old base project left on an upgraded host. Per the fresh-install rule there
  is no migration code; the leftover network is harmless.
- **Not doing:** a periodic sweep of expired shares (they are still swept
  when Konsol lists them) and account changes other than a new password.

### DD-148: A clean install is the base; Konsol installs modules (2026-09-16)

- **Context:** the installer shipped a fixed bundle. The user wants the server
  to come up with the base only and to add parts from Konsol with one click,
  as an administrator would — "temiz kurulumda sadece docker hazır olarak
  gelsin kalan kontainer yapıyı panelden ayarlalım". The model was tried in
  mockups first (`docs/design/konsol-moduller-v04…v06.html`, v06 approved).
- **Decision (user):**
  - **Base (installer):** Konsol, Tailscale by login link, dnsmasq + Caddy,
    the firewall and an empty Docker engine.
  - **Modules (Konsol → Modüller):** Dosya yöneticisi and WireGuard (Konsol
    pages), qBittorrent (on the host, Debian's `qbittorrent-nox`, no settings
    sync), Paylaşım (rclone, needs Dosya yöneticisi) and Arşiv açıcı
    (Unpackerr, its own module). Dozzle goes; each module card has a
    **Günlük** panel instead.
  - Delivered in stages, each verified on `nrm`: (1) the module mechanism and
    Arşiv açıcı (v2-115); (2) Paylaşım; (3) Dosya yöneticisi and WireGuard;
    (4) qBittorrent on the host and Dozzle's removal.
- **Mechanism:**
  - **The installer renders, Konsol runs.** Module files are templates with
    installer-only values (image pins, uid, paths, log limits), and
    `render_template` refuses leftovers. So the installer renders every
    module's files to `MODULES_DIR/<id>/` on each run and Konsol never renders
    anything; `config/defaults.env` stays the single source.
  - **One root helper, a fixed vocabulary.** `master-modul` accepts a
    catalogued id and `liste`, `kur`, `baslat`, `durdur`, `kaldir [--veri]`,
    `gunluk`. The root backend validates the id against `liste` before
    calling it, so a request can name a module but never a path or an
    argument.
  - **Operations outlive the request.** The backend runs
    `systemd-run --unit=master-modul-<id>.service --collect`. The unit is
    outside the backend's sandbox (an image pull or a package install needs
    more than the backend may do), keeps running when the page closes, and its
    name doubles as the busy check (`systemctl is-active` → `409`). Tried on
    `nrm` before writing it.
  - **State the page can read.** `/etc/master-stack/moduller` holds only
    installed modules and whether the operator left them running or stopped;
    a missing line means "not installed". Progress is one tab-separated line
    in `RUNTIME_DIR/modul-<id>.ilerleme`, ending in `bitti` or `hata` with the
    reason. Changes run under one `flock`, so two modules never pull or
    install at the same time.
  - **Each Docker module is its own Compose project** (`-p <id>`): the base
    project's `--remove-orphans` never touches a module, and removing a module
    (`down --rmi all`) never touches the base.
  - **Re-runs respect the operator's choice.** A module whose rendered file
    changed is restarted only if it is registered as running; a stopped module
    stays stopped and an absent one stays absent. The installer never runs
    `kur`, `durdur` or `kaldir`.
  - **Removal keeps user files.** `kaldir --veri` deletes only what the module
    owns (for Arşiv açıcı, the contents of `downloads/.unpackerr`); files under
    `SERVER_ROOT` are never part of a module's data.
- **Checks move with the module.** Stage 7 no longer checks Unpackerr; `kur`
  checks that the container cannot see the trash or the share folder
  (**DD-144**) and takes the container down if it can.
- **Trade-off:** anyone who can open Konsol can now start root operations —
  bounded to the catalogue and verbs above. That follows from **DD-147**
  (tailnet membership is the boundary) and is why the Host and `X-Konsol` gates
  cover `/api/konsol/*` too.
- **Not doing:** a plugin system, remote catalogues or module versions chosen
  at runtime. The catalogue lives in this repository and changes with a
  release, like everything else.
- **Pages:** Caddy now serves the Konsol pages itself (`file_server`, same
  security headers). A page that must show modules the file backend may not
  exist any more once Dosya yöneticisi becomes a module, so pages cannot
  depend on that backend.

### DD-147: Konsol without a password; Tailscale joins by link only (2026-09-16)

- **Superseded in part by DD-194 (2026-10-01):** Konsol has a user name/password sign-in
  again, enforced by Caddy's forward_auth. Joining Tailscale by the login link is unchanged.

- **Context:** the user is turning Konsol into the place where modules are
  installed with one click and service accounts live (Hesaplar design v03). A
  Konsol account in `kurulum.env` was one more secret on the Mac, and Konsol is
  reachable only from the tailnet anyway. The Tailscale auth key was the other
  secret in that file, used only to skip one browser click.
- **Decision (user):** Konsol has no password — "erişim sadece tailscale olacağı
  için katman yeterince güvenli". Tailscale always joins through the login link
  shown during the install; the auth key input is removed.
- **What keeps it safe:** Caddy serves `panel.<domain>` on the Tailscale address
  only, so who can open Konsol is decided by tailnet membership and ACLs. Two
  gates remain and become load-bearing: the backends refuse any `Host` but
  `panel.<domain>` (a DNS-rebinding page cannot reach them), and `/api/*`
  requires the `X-Konsol` header with a same-origin fetch (a page on another
  site cannot send it, so it cannot drive Konsol through the operator's
  browser). Stage 7 proves both on both backends.
- **Accepted trade-off:** every member of the tailnet — and any device shared
  into it that ACLs allow to reach the server — gets full Konsol rights. For a
  single-owner tailnet that is the operator; for more, restrict with ACLs.
- **Removed with it:** PBKDF2 account file, HTTP Basic, lockout, the account CLI,
  `LoadCredential` for the file backend, the auth-key file and fallback path.

### DD-145: The console uploads into the list; no separate upload area (2026-09-16)

- **Context:** the file panel could do everything FileBrowser could except
  upload, select many items and search — the three reasons the container was
  still installed. The user asked for the upload to live *inside* the file list
  ("yükleme alanını ayrıca alta almak yerine dosyalar alanının içerisine
  sürükle bırak"), not as a panel at the bottom.
- **Decision:** the list is the drop target. While files are dragged over it the
  list draws a dashed frame and a target strip; on drop each file becomes a row
  at the top of that list with its progress bar inside the row, and turns into
  an ordinary row when it finishes. The only permanent chrome is a small summary
  in the toolbar. Selection turns the same toolbar into an action bar rather
  than adding a second bar. The dashed frame is drawn only during `dragover`.
- **Mechanics:** `POST /api/upload?path=&name=` takes the file as the body
  (`XMLHttpRequest`, so the row can show progress). The panel writes
  `.yukleniyor-<rastgele>` in the target folder, `fsync`s, then
  `renameat2(RENAME_NOREPLACE)`s it into place: a half file is never listed and
  an existing name is never overwritten. The stream runs without the panel
  lock — a multi-gigabyte upload must not freeze listing, rename or trash — and
  only the rename takes it. Uploads run one at a time, in order.
- **Why not multipart:** the body-is-the-file form needs no parser in the panel
  (stdlib only, **DD-139**) and streams straight to disk.
- **Cost:** the frontend grew a selection model and an upload queue; the backend
  gained one endpoint. In return FileBrowser, its account, its port and its name
  can be retired next.

### DD-144: The user area is a fixed /srv, not an asked-for path (2026-09-16)

- **Context:** `DOWNLOADS_PATH` was an input key with an allowlist
  (`/downloads`, `/data`, `/srv/downloads`). The user wanted one fixed area
  "completely outside the system" and asked whether `/srv` is what that is.
- **Decision:** it is. FHS 3.0 defines `/srv` as "site-specific data which is
  served by this system" and Debian Policy reserves it for the local
  administrator — no package writes there. `SERVER_ROOT=/srv` is a constant in
  `defaults.env`, the question is gone from `kurulum.env`, and `config.env` no
  longer stores a path the operator could have chosen.
- **Layout:** `downloads/` (torrents, with `incomplete/` and `.unpackerr/`),
  `media/{movies,series}`, `.cop` (trash) and `.pay/w` (share root) are
  siblings under the root.
- **Consequence that removed code:** the torrent client and unpackerr mount
  only `/srv/downloads`, so the trash and the share root are outside their
  mount. The `ro,size=16k` tmpfs curtain that used to hide those folders from
  unpackerr is deleted, and stage 7 asserts the containers cannot see them.
- **Cost:** a rebuild starts with an empty `/srv`; data under an old
  `/downloads` is moved by hand (fresh-install rule). The operator must delete
  the `DOWNLOADS_PATH` line from `kurulum/kurulum.env`.

### DD-143: The installer prepares WireGuard; Konsol creates it (2026-09-16)

- **Context:** the user asked to cut the Mac-side link — no reading of
  `kurulum/wireguard`, no peer preservation, no upload — so that every install
  leaves a clean WireGuard, with interfaces and devices created from the panel.
  They approved the shape below, including "a re-run must not wipe the networks
  the panel created".
- **Decision:**
  - **No privileged `wg0`.** Every network lives in `/etc/wireguard/networks`
    and is created by `master-wg net-add`, which already ordered the steps
    correctly (files and registry → firewall → `wg-quick@wgN` → `caddy-wg@wgN`,
    with a full teardown when a step fails). Allocation now starts at `wg0`;
    profiles live in `clients-wg<N>` for every network.
    - `state.env`'s `WG_SERVER_IPV4`, `WG_SUBNET*` and `WG_PUBLIC_PORT` are now
      *defaults* (address base, suggested first port), not "the wg0 network".
      `WG_INTERFACE` is gone.
  - **The installer prepares, never creates.** `ensure_wireguard_ready`
    installs `wireguard-tools`/`qrencode`, loads the module and creates
    `/etc/wireguard`; `ensure_wg_networks_running` enables and starts what the
    registry holds. No key is generated, no `.conf` written, no interface
    started by the installer — so a re-run cannot overwrite or resurrect
    anything, and a fresh server simply has no WireGuard.
  - **The firewall is registry-only and valid with zero networks.** Empty
    arrays are guarded for bash 3.2 (the tests run there), and the NAT chain is
    created empty rather than skipped.
  - **The panel's empty state is the entry point.** With no networks the
    WireGuard page shows one card — what will happen, then **Yapılandır** —
    which routes to the same "Arayüz ekle" page. One creation path, no second
    bootstrap code.
  - **`wireguard.command` stays an SSH client.** It picks the network (asks
    only when there is more than one), and lost "Yedek al", the auto-backup and
    the embedded server-side tar script.
- **Why:** the old flow had two ways to get a network (installer for `wg0`,
  panel for the rest), kept server keys on the Mac, and made a rebuild silently
  restore old peers. Measured before the change (live on `nrm`): deleting
  `wg0.conf` left `master-wg list` failing with a raw shell error and the panel
  logging "sayaç okunamadı" every 10 s, while the panel still showed a phantom
  `wg0` card that could not be switched on — the fragility came from `wg0`
  being special, not from the panel.
- **Cost:** rebuilding a server means creating the network and re-adding the
  devices from Konsol. Accepted by the user; nothing on the Mac holds a server
  key any more.
- **Follow-up (v2-111):** the settings files kept describing `wg0` after the
  installer stopped creating it — `WG_CONF_FILE=/etc/wireguard/wg0.conf`, the
  first network's server addresses and subnets, and a `WG_PUBLIC_PORT` in
  `config.env` that an older run could still impose. They are a base only now
  (`WG_CONF_DIR`, `WG_ADDR_BASE4`, `WG_ADDR_BASE6`, `WG_PORT_DEFAULT`), so the
  host carries no preset network anywhere: not on disk, not in `state.env`, not
  in `config.env`. A bats test holds the line.

### DD-140: One console (Konsol) instead of two panels, and switchable peers (2026-09-16)

- **Context:** after the file panel the user asked for the WireGuard and file
  pages to become one server-administration tool. The design was iterated as a
  mockup until they approved it (frozen in `docs/design/konsol-v01.html`).
  Their decisions: the address is `panel.<domain>` with `wg.` and `dosya.`
  redirecting, the browser's own login prompt is enough, no services page or
  status collector anywhere, and a network turned off in the console comes back
  with an installer re-run.
- **Decision:**
  - **One page, two backends.** The privileges that made two services necessary
    (DD-139) do not change: `master-wg-panel` stays root because `master-wg`
    needs it, and `master-files-panel` stays the downloads uid. Caddy sends
    `/api/wg/*` to the first and everything else — the pages included — to the
    second, so the console is one origin with one login.
    - The WireGuard backend no longer serves files: its `--web` argument and
      the old page files are gone, and every route moved under `/api/wg/`.
    - Both backends answer only to the host `panel.<domain>`, use the header
      `X-Konsol` for CSRF and the realm `Konsol`, so the browser reuses the
      same credentials for both.
  - **Switching a peer off keeps everything.** `master-wg peer AD kapat`
    prefixes the peer's block in `wgN.conf` with `#kapali#`. `wg-quick` and
    `wg-quick strip` ignore comments, so the peer leaves the running interface
    at once and stays off after a reboot, while its key, preshared key, address
    and client profile stay untouched. `master-wg info` reports the state as an
    eleventh field, `cmd_add` skips a disabled peer's address when it hands out
    the next one, and `peer_count` counts it.
    - `write_and_apply` no longer starts an interface that is switched off: it
      writes the file and returns when the unit is disabled.
  - **Switching a network off is the unit.** `master-wg [--if wgN] net kapat`
    disables `wg-quick@wgN` (and `caddy-wg@wgN`); the registry, keys and
    profiles stay. The firewall keeps the UDP port open — nothing listens on
    it — instead of a second, drifting source of truth for "which port is
    open".
  - **The overview reads the server, not the containers.** The root backend
    samples `/proc/stat` and `/proc/meminfo` every 10 s and keeps the last two
    minutes, reads `/proc/uptime` and `/etc/os-release`, and builds the ports
    card from `state.env` plus the network registry — no scanning, no container
    status collector (the user rejected one). "Son işlemler" parses the two
    services' own audit lines out of the journal, cached for 15 s.
    - The disk bar needs a size the root backend cannot cheaply get, so the
      file backend walks the downloads tree at most every 5 minutes (the same
      budget as a listing) and reports `null` when the budget is exceeded; the
      console then shows a single "Kullanılan" segment.
- **Why:** two pages meant two logins, two looks and no place for anything that
  belongs to the server rather than to one of them (load, disk, ports, log).
  One console also makes the switches possible: they are the first controls
  that touch both a unit and a configuration file.
- **Verified (2026-09-16):** bats 152 ok. The page was exercised against a mock
  backend (all four pages, the move, peer-add and confirm dialogs, no console
  errors) before the live run.

### DD-96: The installer owns its own files and nothing else (2026-08-09)

- **Cleanup (v2-96, 2026-09-14):** with the only host freshly rebuilt on v2-95,
  the last transition aids went:
  - the stage 0 Transmission container gate and `TRANSMISSION_*` removed-key
    hints (with `read_input_file`'s removed-keys argument);
  - the stage 7 Portainer warning;
  - the v2-73 sysctl file-name migration (`remove_legacy_sysctl_files`,
    `SYSCTL_LEGACY_FILES`);
  - the "no OS record (v2-73)" log branch.

  Stale wg-easy wording in comments was corrected, and the two dated reviews
  moved to `docs/archive/`.

- **Decision:** All migration cleanup is removed (v2-62). The installer no
  longer deletes `master-webdav.service`, its user, group and downloads ACL,
  no longer runs `apt-get purge rclone` / `apt-get autoremove`, no longer
  removes the `filebrowser` container or the legacy `*_filebrowser_data`
  volumes, and no longer deletes `filebrowser.yaml`, the `watch-tailnet-addr`
  unit, the retired `docker.service.wants` symlink, or `$COMPOSE_DIR/.env`.
  The upgrade path is a fresh install, or a re-run that overwrites the files
  the installer itself renders.
- **Why:** three reasons converged.
  1. **Boundary.** A global `apt-get purge`, an `apt-get autoremove` and a
     `userdel` are host-wide actions taken on the installer's own guess about
     what an older revision left behind. The v2-58 review flagged exactly
     this as cleanup exceeding the stack boundary, and narrowing the scope
     (v2-59, v2-60) treated the symptom, not the cause.
  2. **Idempotency.** `remove_stale_filebrowser` ran unconditionally, so a
     re-run recreated the container every time. Measured on `nrm`: all 16
     managed files byte-identical, Caddy/dnsmasq/Docker untouched, but the
     FileBrowser container id changed and the service blinked for ~2 s. That
     is a re-run changing state for no reason (**R20**).
  3. **Cost.** 83 lines and five bats assertions existed only to migrate
     hosts provisioned by revisions we no longer run.
- **Consequence (accepted):** a host installed by an old revision keeps its
  leftovers. It is not repaired by a re-run; it is reinstalled. Single-host,
  interactive, destructive-by-design — reinstalling is the cheap path.
- **Guard:** a bats test fails the suite if `apt-get purge`, `userdel`,
  `setfacl`, `docker rm`, `docker volume rm` or `disable --now` reappear in
  `install.sh`, so the pattern cannot creep back one convenience at a time.
  - `docker rm` and `docker volume rm` count only as commands the installer
    runs. A leftover gate may name them in a `die` or `log` message for the
    operator to run by hand (DD-116, DD-117).
  - Until v2-91 the negated assertions never failed under macOS bash 3.2
    (DD-126), so the guard was silent.
- **Not doing:** an uninstall command. Removing what v2 installed is a
  separate, explicit operation, not a side effect of installing.

### DD-95: Counting WAN allows, and adopting referenced staging (2026-08-09)

- **Decision (two fixes, v2-61):**
  1. **The WAN allow count must match the list.** DD-94's `check_chain_shape`
     treated only a bare `-j ACCEPT` / `-j RETURN` body as a bypass. An
     interface-qualified pass — `-i eth0 -j ACCEPT` in `MASTER-INPUT`, or
     `-i eth0 -j RETURN` in `MASTER-DOCKER` — was instead recorded as a
     legitimate WAN allow, so it satisfied the ordering rule and passed. So
     did an extra port (`--dport 3306`). Pattern checks find a *missing*
     rule; they structurally cannot find an *extra* one. `check_wan_allow_count`
     now asserts that the number of `-i WAN … -j ACCEPT|RETURN` rules equals
     the length of the allow list (5/2 for INPUT v4/v6, 3/0 for DOCKER),
     and the same list feeds the per-rule `check_rule` calls, so the ports
     are still written once.
  2. **Staging cleanup runs at the end of apply and removes the jump.**
     `activate_named` jumps the staging chain from its parent before the
     rename, so an interruption in that window leaves it *referenced*.
     DD-94's purge skipped referenced chains to avoid deleting a live policy;
     the result was a chain nothing would ever adopt, a permanently failing
     `check_no_staging_artifacts`, a permanently failed unit and a watchdog
     restarting it every 5 minutes with the same outcome. Moving the purge to
     the end of a successful apply removes the dilemma: the final chain is
     already bound to the parent, so any remaining staging artifact is dead
     by definition and its parent jump can go with it.
- **Why:** a second review of v2-60 (2026-08-09). Both are drift the stack
  never produces itself; they matter because `--check` is what the watchdog
  trusts, and a check that cannot see a hole is worse than no check.
- **Boot window (no change, measured):** ~850 ms passes between the WAN
  address becoming usable and the policy landing (eth0 DAD 21:33:42.742 →
  apply finished ~21:33:43.6 on `nrm`). The only WAN listener in that window
  is sshd, which the policy allows anyway; Docker and every published
  container port start ~2 s later, behind the policy. Closing it would mean
  either persisting rules to disk (a second source of policy, against DD-66)
  or ordering the unit before `network-online.target`, which DD-94's live
  WAN detection needs. Accepted and documented instead.
