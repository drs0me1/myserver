# Tests

Narrow critical-behaviour suite for the lean installer tree. Not a framework
coverage suite.

```bash
cd Data   # from the repository root; paths below are relative to Data/
bats tests
bash -n install.sh common.sh scripts/*
shellcheck -x -s bash install.sh common.sh scripts/*
```

`bats tests` runs every Bats file (`common.bats` and `share-networks.bats`);
`bats tests/common.bats`, used in some sections below, runs only the first.

The Bats fixture resolves its temporary directory with `pwd -P`: macOS `/var`
is a symlink and production no-follow readers correctly reject it. No shell
wrapper or relaxed production traversal is needed.
Mode/inode checks capture only successful GNU/BSD stat output; hashes use the
fixture's Python helper. Linux Bats needs the source guards' docs, root
`.gitignore`, `kur.sh` and `wireguard.command` too, not only the runtime tree. Copy only these allowlisted test inputs; never include private
`kurulum/` or WG profiles.
For a root-created test checkout under `mktemp -d`, set that checkout directory
to mode `0755` (`chmod 0755 /absolute/path/to/test-checkout`): non-root fixture
processes must traverse it. Do not relax private input/credential permissions.
Template tests exercise literal ampersands/backslashes and preservation of
Bash 5.2's `patsub_replacement` setting (Bash 3.2 has no such option).

Host acceptance (Debian 13 or supported Ubuntu target, after install) is
separate: DNS loopback vs Tailscale answers, WebDAV PROPFIND/read-only,
firewall `--check`, and the public ports: WAN SSH TCP, Tailscale UDP, each
registered WireGuard UDP port (if installed), plus the mode-selected WAN IPv4
WebDAV port: legacy HTTP `SHARE_PORT` only while a WAN share is active, or
configured HTTPS `SHARE_HTTPS_PORT` retained for renewal with no active folders.
Explicit HTTPS disable closes both WAN ports; Tailscale HTTP is unchanged.
With DD-191, an independently enabled qBittorrent publication keeps the shared
HTTPS port open; disable both rows to close it. A Tailscale row switch gates
that named route, not the shared Caddy listener.

Portable validation should compare the complete embedded file set with runtime
sources, excluding Python caches, metadata, tests, docs and private input.

## Files favourites (v2-232, DD-250)

`test_favorites.py` drives `/api/konsol/favoriler` on the root backend's handler: add/remove in order,
duplicates, the 0600 file removed when empty, bad paths and requests (400), the 20-entry limit, a damaged
record, the gates, and the internet channel rule (system entries hidden and kept) through the Panel
methods. `files-ui.cjs` adds and removes a favourite with the detail star, checks it is listed before
Sunucu with its location, opens it, removes it with the row's ×, and does the same for a system-view
folder ("root · /"). The other UI suites answer the endpoint with an empty list.

## Files text editor (v2-231, DD-249)

`test_text_edit.py` covers the backend in temporary directories: the version and the reasons the text
view gives, an atomic replace that keeps mode, owner (as root) and extended attributes, CRLF and the
UTF-8 BOM kept, Windows-1254 written back, unencodable text refused, a changed file or a swap before the
rename refused (409), oversized text, symlinks and folders refused, and no `.konsol-kayit-*` left behind.
`test_system_files.py` saves through the real handler on the root view (a body above `MAX_BODY`, a stale
version, the gate). `files-ui.cjs` opens the editor under the production CSP: language label, cursor
position, Ctrl+S and Kaydet with the returned version, the unsaved-changes question on Kapat and Esc,
the read-only view of a large file, and the root view's warning and `/api/sistem/text/save`.
`common.bats` checks the bundle's banner against `tools/duzenleyici/package.json`. To rebuild the bundle:
`cd Data/tools/duzenleyici && npm ci && npm run derle` (the output is byte-identical for the same lockfile).

## Files "Sistem (/)" root view (v2-214, DD-235)

`test_system_files.py` runs the backend's `--sistem` mode in temporary directories and on a temporary
Unix socket: read-only `/proc` `/sys` `/dev` `/run`, root modes for new items, no reserved names,
permanent delete refused at a mount point (or a mount below) and at a device change, `mountinfo`
unescaping, the channel/client/Host gate (200 only for another Tailscale device on the tailnet site),
system-only routes, name/`onayla` confirmation, and the Settings → Web parser leaving the route out of
the public site. `common.bats` checks the unit, the tailnet-only Caddy matcher, the installer wiring and
the stage-7 probes. `files-ui.cjs` checks the sidebar entry, the warning strip, the missing
trash/archive/share actions, `/api/sistem/` calls and the typed-name delete. The Caddy matcher was also
adapted with Caddy 2.10 (the `{args[0]}` placeholder needs Caddy ≥ 2.7; Debian's 2.6 cannot check it).

## Files account for writable folders (v2-205, DD-227)

`test_container_worker.py` checks:
- the Files-account render (`User`/`Group`, `DropCapability=all`, `--umask=0002`);
- the refusal of the image account with a writable folder before any Podman call, while read-only
  folders and volumes are allowed;
- the defaults: new definitions get the Files account, a value is preserved when omitted, and older
  definitions render as before;
- that invalid ids fail closed with 503;
- that `ready()` proves the account and the empty capability sets, printed as `null` (Podman 5.4.2)
  or `[]`, and fails closed when a field is missing (mutations that skip the check, accept a missing
  field or reject `null` turn it red);
- the adoption mapping.

The fake runtime reflects the Quadlet's account lines and prints a fully dropped capability set as
`null`, as Podman 5.4.2 does. `konteynerler-ui.cjs` checks:
- the preselected account and the payload on create;
- the running user in the details;
- the blocked review when an old definition's folder is made writable, cleared by switching;
- the review's account line and consequence;
- the account in the adopt payload.

The live worker fixture owns its writable folder by the downloads account, as `/srv` is.

## Pinned bind sources (v2-204, DD-226)

`test_container_binds.py` runs the real helper with fake mount calls. It checks that:
- the bound directory is the one behind the walked descriptor, even when the path is swapped for
  a link right after the walk;
- links (final or intermediate), hidden, outside, root, file, missing, `..` and bad-character
  sources are refused, and partial anchors are released;
- an unmounted anchor is never accepted;
- unsafe anchor directories are refused;
- `birak` removes only empty folders;
- a stale anchor is released first;
- the helper loads no package code and takes no lock.

`test_container_worker.py` checks the generated lines: guard check first, then `bagla`, the anchor in
`Volume=`, `RequiresMountsFor` with the real path, and `ExecStopPost` only with binds.
`containers-worker-linux.py` copies the helper, gives its fixture an anchor directory, and refuses
to delete its scratch tree while an anchor is still mounted.

## Private package state (v2-203, DD-225)

The Bats test "package private state is hidden" checks the new `PRIVATE_STATE_ROOT` key. The
WebDAV unit must have exactly one `InaccessiblePaths=` line (trash, `.arsiv`, `-.pay`,
`/var/lib`), `RequiresMountsFor` and no `SystemCallErrorNumber`. The Files unit must mask only
`/var/lib`, and the installer must pass the key. Neither unit may name an application, and
qBittorrent's profile directory must lie under `/var/lib`. The test also renders both templates
with every placeholder filled and checks the resulting mask lines.

## Container egress (v2-202, DD-224)

`test_container_network.py` pins the rule order:
- the one-rule path for traffic that neither enters nor leaves a bridge;
- the reply returns;
- then the IPv6, `tailscale0` and per-prefix drops, in `VPN_BLOCK_DEST4` order (from
  `config/defaults.env`, with no address literal in the module);
- a /32 rendered as an address.

It also checks that a missing, empty or invalid list fails closed with 503, and that health
detects a deleted or swapped egress rule. The live namespace suite `containers-network-linux.py`
adds echo servers next to the host and probes from the container namespace. 192.0.2.2 and
198.51.100.2 are reachable. The tailnet, WireGuard, 192.168, 169.254 and IPv6 peers are not.
Tailscale-scope and WAN publication replies still pass. `containers-worker-linux.py` gives its
fixture the same list.

## Container start precondition (v2-201, DD-223)

`test_container_worker.py` checks the generated Konsol Quadlet: `Wants=` and `After=` on
`master-firewall.service`, no `Requires=`, `BindsTo=` or `PartOf=`, one `ExecStartPre` that ends
in `--check`, `RestartSec=10s`, and no check for a container without a network.
`test_container_network.py` checks that `check()` names a missing guard table and still reports
other read errors as before. It also checks that a loopback-only port change leaves the policy
unchanged, which is what lets qBittorrent's interface-port restart pass its start check. A Bats
catalogue rule applies the same unit lines to every package that declares its own bridge.

## Pending package changes across a failed run (v2-200, DD-222)

The Bats test "pending module markers" runs the real `render_package_dir`,
`ensure_module_files` and `reapply_modules` against a fake one-package repository.
`install`/`chown` and `master-modul` are stubbed. Each simulated installer run is its own
subshell, as each real run is its own process. A run renders a changed Quadlet and then fails
before stage 7. The next run renders nothing new and still calls `uygula` exactly once; the run
after that calls nothing. The test also checks that a failed `uygula` keeps the marker and
warns, that the next run retries, and that a package that is not installed loses its marker
without a call. For the built-in WebDAV, a `paylasim` marker reaches `master-modul yerlesik`
after a failed run and is then cleared. The wiring of stages 4, 6 and 7 is checked statically.

## Container manager (v2-190, DD-211)

Local checks need no server:

```bash
python3 -m unittest discover -s tests -p 'test_container*.py'
node tests/konteynerler-ui.cjs  # console static server and Playwright required; see browser setup below
```

Use Python 3.11 or newer (nrm uses 3.13); macOS's system Python 3.9 does not parse
the nanosecond RFC3339 timestamps returned by the runtime. The suites cover merged
inventory/stopped definitions, real Podman JSON shapes, API gates, private results,
stale revisions, recreate/rollback, explicit adoption, volume/network boundaries,
package port overrides, bridge DNS INPUT permissions, ownership-aware listener
conflicts and the existing tailnet event's bounded refresh job.
Browser fixtures exercise actual console assets with mocked API state; they do not
prove Podman, firewall or server mutations.

`containers-network-linux.py` requires Linux/root and is run inside a disposable
network namespace (`unshare --net --fork`). It tests actual TCP/UDP packet paths,
scope revocation, direct/IPv6 ingress and preservation of foreign nftables tables.
`containers-worker-linux.py` requires a disposable rootful Podman/systemd host with
the project firewall already active. It creates only uniquely named test resources
and cleans them up; it checks real Quadlet execution and lifecycle behavior.
Do not run live fixtures concurrently with installation or another nrm test.
Installation/reboot persistence and the actual application/browser journey remain
separate acceptance checks; record exact runs and untested platforms in SESSION.md.

## Public Konsol over HTTPS (v2-167, DD-195)

`test_publications.py` covers the Panel row: the tailnet switch cannot close, an
account and the server-checked word `onayla` are required when turning on or
renaming, DNS/duplicate/legacy-HTTP checks, the generated
`panel-wan.caddy` (WAN bind, TLS-ALPN, HSTS, only `import konsol internet`), its
certificate status, the shared TCP 443 firewall output with WebDAV's WAN off,
removal at the next publish after an account reset and rollback after a
certificate failure. `test_konsol_auth.py` covers the shared public failure
budget, one password check per address and two at once, and the root backend's
channel rules on a Unix socket: closed publication, refused account creation, `Secure`
cookie, own-address and unmarked clients refused, `kanal` in the session state and
the 5-second publication cache, and the budget re-check after a hash slot.
`test_settings.py` checks that a local-domain change rewrites the snippet's
backend Host and that a confirmation through the public channel is refused.
`common.bats` checks the snippet, the Caddy-written channel header, the backend
connection cap, the forwarded host and channel on confirmations, and the
installer cleanup; `publications-ui.cjs`
drives the editable Panel row and the typed `onayla` dialog; `giris-ui.cjs` the
Tailscale/internet label.

v2-168: `test_resources.py` checks the module listing's `urls` for qBittorrent
(tailnet name always; the public name only while that publication is active or
`null`); `panel-ui.cjs` opens Konsol on an `https://` origin with intercepted
requests and checks that the qBittorrent page links the public name, falls back
to a Settings → Caddy hint without one, and keeps the tailnet link on `http://`.

v2-177 (DD-203, store phase 3): the shared share fixture (`test_share_manager_networks.
torrent_package`) renders the torrent package folder — manifest with `PAKET_KLASORLER`,
`klasorler.py`, `torrent.env` — so `test_shares.py`, `test_stage3_share_paths.py` and
`test_backend_hardening.py` exercise declared and reported folders through the package
module (fail closed on an unreadable profile); `test_shares.py` checks the WebDAV server
hides and refuses a reported folder inside a share by path; `test_webdav_*` configs use the
root-relative `protected` list; `test_torrent_api.py` covers `package_env`, the standalone
worker reading `torrent.env` beside itself and `klasorler.yazilan`; `test_resources.py`
resolves a `PAKET_PORTLAR` key from the package's env file; `test_publications.py`,
`firewall-linux.py` and `publications-proxy-linux.py` write `torrent.env` into their
package folders, and `settings-domain-linux.py` takes the torrent site's port from it. Bats checks the installer helpers (`paket_korunan_klasorler`,
`paket_arkauc_yollar`, `paket_ayar_oku`) against rendered manifests, the `--protected`
file-backend argument and that no base file names an application or carries a `TORRENT_*`
key. Browser fixtures return `protected: [{path, owner}]` from `/api/state`.

v2-176 (DD-202, store phase 2c): `test_torrent_api.py` drives the qBittorrent package
worker (`ayar.py`: hash format, INI preservation, the read-only view without the hash,
validation before any service change, stop/write/start order, failed-start recovery,
stopped-state preservation, the narrow drop-in and its rollback, the CLI) and its API
module through a fake context and through the real dispatcher (gates, the package-folder
rule for worker scripts, the private stdin run, the `torrent:hesap` audit line);
`torrent-ui.cjs` is the page's browser suite; `panel-ui.cjs` serves the page from the
package and fixtures `/api/uygulama/torrent/durum`; `settings-ui.cjs` has no application
section any more; `test_backend_hardening.py` points the profile-reader checks at
`ayar.read_conf`; `settings-linux.py` runs the worker's functions against real
qBittorrent; Bats checks the status view, the private worker run and that the shell
and the settings page name no application.

v2-173 (DD-199, store phase 1b): `test_publications.py` renders the qBittorrent
manifest and copies `yayin.py` into the fixture `MODULES_DIR`, so rows, sites and
checks come from the package; it also covers a failing, unparsable and missing
check module (row closed, app never exposed) and a manifest without a loopback
upstream (no row). `publications-proxy-linux.py` does the same against real
Caddy and qBittorrent, and `firewall-linux.py` copies the manifest and module so
the shared TCP 443 permission still follows an active qBittorrent row.

v2-172 (DD-198, store phase 1b): the firewall Bats test and `firewall-linux.py`
copy the WireGuard package's hook into the fake `MODULES_DIR` and drive the
firewall through its `vpn` declarations (malformed or clashing declarations stop
before any chain changes); `test_stage4_health.py` derives the fake
`master-modul saglik` output from the fixture registry; `test_resources.py` and
`test_firewall_view.py` build port rows from copied manifests, including a
malformed manifest whose rows are skipped.

v2-171 (DD-197, store phase 1a): the Bats fixtures copy each package's
`paket.env` and `kanca` from `magaza/` into the fake `MODULES_DIR`, so the
module tests run the real engine against the real hooks; the engine itself is
checked to contain no application id. Installer tests check the generic
renderer (`render_package_dir`), the manifest-driven reapply flag and the
summary built from manifests and `paket_ozet`.

v2-170 (DD-196, store phase 0): the Bats test "store phase 0" checks the repo
layout (`magaza/`, the WireGuard tool and drop-in inside the package), that the
base installer neither installs nor keeps them, that `master-modul` places and
removes them, the package-neutral stage-7 probe, the Caddy unit without
`--environ`, the backend's unit name and Konsol's log labels by source.

v2-169: `test_publications.py` adds the fresh-install case: with WebDAV in
legacy HTTP mode, Panel/qBittorrent HTTPS is refused only while a folder is
actually shared over plaintext HTTP, publishes once that connection is closed,
keeps legacy HTTP unavailable (cards and the WebDAV row say why) while the
HTTPS row is on, and reopens it when the row is turned off; the firewall port
follows. `settings-https-ui.cjs` checks both notes (`wan_active` on/off).

```bash
python3 Data/tests/panel-public-live.py --host nrm --domain konsol.example.com
```

`panel-public-live.py` is opt-in and **mutating**: it needs the operator's existing
Konsol account and a name with a DNS-only A record to the host's WAN IPv4 (no
AAAA). It publishes Panel on that name through the real Settings API, checks HSTS,
the sign-in page, session protection of pages/Files/root APIs, the refused setup
code, one wrong sign-in and a root-issued automation session over the public
address, then restores the Panel row exactly and checks that the name no longer
reaches Konsol. It exits 3 without changes when there is no account or Panel is
already public.

## Install form, app launch and tile actions (DD-210, DD-212/213)

Current home assertions cover service → settings → logs, three fixed 44 px slots
(unsupported WireGuard service slot is noninteractive), narrower cards with unchanged
height, safe log dialogs with timeout/retry, focus and draft retention, and light/dark
desktop/320/390 px geometry. `panel-ui.cjs` also asserts that Store card subtitles are
absent while full package descriptions remain in Details.

`test_torrent_api.py` covers the worker's `kur-hazirla` (every field refused before any write, the seed
only in `RUNTIME_DIR`, 0600, hash only, writability probed as the service user), `kur-uygula` into a kept
profile (only the four keys change, other preferences stay, the folder drop-in, no service command) and
`kur-geri` (profile and drop-in restored byte for byte), refusal of a readable, linked or malformed seed,
the combined `ayar` save (validation first, one stop/start, blank password keeps the hash, failure restores
both files, a stopped app stays stopped), the CLI, the API module's `/ayar` route, and the real backend's
install route on a Unix socket (form required, worker before engine, password only on stdin and never in
argv or audit, seed removed when the engine cannot start, installed package refused before the worker,
WireGuard refuses a form). `common.bats` runs the real engine and hook against the fake Podman/systemd:
no install without a seed or with a readable one (no image pulled), the form's account and folder in the
profile at the first start, the seed gone afterwards, a kept profile's preferences preserved with a
library-folder drop-in, failed installs restoring the previous profile and drop-in, and the backend's
worker-then-engine order. `app-install-ui.cjs` drives the shell with fixture APIs under the production
CSP: Kur opens the form (defaults, cancel/Escape send nothing, required and repeated password, folder
chooser), drafts survive a server refusal and a poll, one request per submission, WireGuard's Kur
unchanged, launch in a new tab with `noopener` from the tile and App Store, no sidebar entry (DD-216; stub page as the
target), the tile action row (v2-189: icons only — no text, transparent background, no border at rest, on
hover and pressed, at desktop and 390 px; aria-label and tooltip names; the keyboard focus ring; a finished
request leaving focus where the operator moved it; v2-188: Ayarlar opening the form for qBittorrent and linking WireGuard's
page, Durdur/Başlat only for qBittorrent and nothing on built-in tiles, beneath the icon in one row with a
larger touch area; Durdur's confirmation and cancel, the busy label without duplicate requests, focus kept
across poll redraws, the label after completion, a refused Başlat shown and recoverable), the settings
dialog (keyboard, focus return, only changed fields, blank password not sent, error draft, a late read
or a late install answer leaving a newer dialog alone), a stopped app's settings read and saved without
starting it, stopped state falling back to the page, edit mode without the row and with working arrows,
390 px dark screenshots and the public address (public name or the page, never the tailnet name). `panel-ui.cjs` installs qBittorrent through
the form and checks the new open actions.

## Peer port editor on the Podman page (v2-199, DD-221)

`test_container_package.py` changes the peer port through the package adapter (`konteyner_ayar`):
a stopped app gets both WAN `PublishPort` lines and `TORRENTING_PORT` moved in the rendered Quadlet,
`Session\Port` in the profile and an override holding only `TORRENT_PEER_PORT` (no interface-port
pin, no port drop-in, no Caddy change); a running app gets the placed Quadlet moved too and the
container guard applied before the start; a failed start restores every file and reapplies the guard
before the app starts again.
Refused before any service action: a non-integer, out-of-range or interface-equal port, another
service's port (base `*_PORT`, a saved definition's UDP port), a port the WAN probe finds taken, a
Quadlet whose WAN lines or `TORRENTING_PORT` do not match, and an unknown config key. The probe
itself refuses a held TCP and UDP port. `konteynerler-ui.cjs` edits the field (range and
interface-equal errors block the review, the review names the change and the closing old port, the
payload carries `peer_port`) and checks that an adapter without `peer_port` shows no field and sends
none. `common.bats` pins the guard-before-start order and the allowlist.

## Data removal keeps Konsol's choices (v2-198, DD-220)

The `common.bats` engine test sets a durable `TORRENT_UI_PORT` choice (`PACKAGE_OVERRIDES_DIR`) and the
port drop-in `85-konteyner.conf` before `kaldir --veri`, and asserts that both survive while the image
(removed by id) and the folder drop-in go and the fixture profile (outside `/var/lib`) stays; the
`/var/lib`-only profile guard is pinned statically. The later reinstall steps run with the override in
place; it holds the fixture's default port, so they do not exercise a non-default one.

## qBittorrent on its own bridge (v2-195, DD-217)

`test_container_network.py` builds a registered package with a placed Quadlet: the guard lets
through only its WAN publications (TCP and UDP) into the package bridge, needs no rule for the
loopback interface, ignores an address that is not the server's, and publishes nothing for a stopped
or unregistered package or for a placed Quadlet on another network (the installer's upgrade window).
`test_container_package.py` moves the loopback `PublishPort` line with the interface port in the
rendered and the placed Quadlet, restores both on failure and refuses a Quadlet without that line
before stopping anything; `test_torrent_api.py` checks that the install writes `WebUI\Address=*`.
`test_container_listening.py` labels published addresses (the WAN one as internet access) and names
the bridge in the detail. `common.bats` drives the engine with fake podman: the bridge is created
once with the guard's interface name and the package label, removed with the package, and an
unexpected publication stops the install; it also pins the three `PublishPort` lines.
`konteynerler-ui.cjs` shows the three publications in the row and the detail, and keeps the host-socket
view on another host-network fixture container.

## Podman page, listening ports and app navigation (v2-194, DD-215, DD-216)

`test_container_listening.py` builds a small `/proc` and cgroup v2 tree: only the container's own
processes' sockets count (TCP LISTEN, unconnected bound UDP; peer connections, connected UDP, unbound
and link-local binds, and the host's own listeners left out), IPv4-mapped and IPv6 addresses, child
cgroups, the root cgroup never widening to the host, unknown as `None` and never an empty list, the
address kinds (the server's own WAN address wins over the CGNAT range), and the manager reading only
running host-network rows with the installer's WAN/Tailscale addresses. `konteynerler-ui.cjs` checks
the Podman title, eyebrow and sidebar entry, the absence of application entries, a cold load whose
list answers before the module catalogue (container name first, repaint without another list read),
the per-port access lines with "+N port daha" and the detail's full address table. `panel-ui.cjs`,
`wireguard-ui.cjs` and `app-install-ui.cjs` assert that an installed application has no sidebar entry
and that Ana Menü stays marked on its page; `common.bats` pins both.

## Image update check and row controls (v2-193, DD-214)

`test_container_updates.py` covers `update_status()` (index by host platform digest, single
manifest by config digest, pinned/unreachable/missing answers, manifests only), the manager's
cached status (TTL, one forced check a minute, cache emptied after a successful image change,
no pull target to the browser), `image-update` only for packages with a channel and an adapter,
and the GET-only route behind the gates. `test_torrent_api.py` `ImageUpdateTests` drives the
qBittorrent adapter: no-op when current, exact-digest pull after validation, patched Quadlet and
manifest lines plus the override (port choice kept), restart/UI/ImageName checks, full rollback on
a failed restart or a wrong image, a stopped app, and refusals that change nothing.
`konteynerler-ui.cjs` asserts the lead controls before the name, the home-tile glyphs and bare
style, keyboard order, the cached check on open, the forced check, the chip, count, confirmation
and the detail state. `common.bats` pins the manifest-only check, the adapter order, the channel
keys and the absence of any automatic update.

## Podman in the base and qBittorrent in Podman (v2-186, DD-208, DD-209)

`test_containers.py` drives `panel/master_containers.py` with canned `podman` JSON: the list
(containers, host network, ps ports, images, storage size), a calm answer when podman is
missing or fails, `inspect` mapping (sorted mounts, port bindings, three labels, health, never
the environment), log masking of password/token/key values with a bounded tail, name and path
gates and RFC 3339 parsing; a route test runs the real backend handler on a Unix socket (shared
gates, 400/404 answers, no write route: POST → 404, no podman write verb).
`konteynerler-ui.cjs` now drives the main-sidebar manager (DD-211) under the production CSP:
five Settings tabs and old-link redirects; saved stopped definitions; ownership-derived actions,
busy/error handling, details and logs; create/edit/review/async apply; private secret preservation,
explicit public scopes and accurate recreation/stopped-save behavior; a logical default network
on a fresh host; the App Store listener/folder adapter; images, volumes, networks and adoption.
Drafts survive polling, stale responses cannot replace a newer sheet, leaving the page closes it,
and 320/390/768/1024/1440 px layouts retain keyboard access without horizontal overflow.
DD-213 adds name-only rows, retained status/resources/access columns, three capability-gated
44 px start/stop/edit/remove controls, busy/disabled refusal, row editor focus return,
and direct removal that keeps generic data and defaults package data deletion to off.
`common.bats` pins the stage-1/7 Podman install and check (no daemon units), the base view's
files and routes, the engine's quadlet slot and digest-only image (`docker|compose` stay banned,
no `/etc/containers` literal in the engine), the qBittorrent quadlet (its own bridge
`Network=__TORRENT_NETWORK__` with exactly three `PublishPort` lines since DD-217, `Pull=never`,
two same-path mounts, no `NoNewPrivileges`), and the qBittorrent lifecycle against a fake
`podman`/`systemctl`/`ss`: pull once by digest, seed before the first start, host uid / mount /
exact `podman port` set / loopback-listener checks with rollback, stop removes the quadlet, a changed quadlet restarts,
`--veri` removes the image by id, an active old `qbittorrent-nox@` unit is refused.
`test_torrent_api.py` covers the worker's quadlet drop-in (same-path `Volume=` only outside the
downloads tree, unmountable names refused, the wait for the interface after a restart) and
`settings-linux.py` runs the same worker against a real qBittorrent with a scratch
`KONTEYNER_BIRIM_DIR`.

## Backend write paths (v2-184, DD-207)

`common.bats` checks that the installer lists declared write paths one per line, creates them
before the backend (re)starts and restarts a backend whose mount table lacks a writable mount
for one (fixture mountinfo: present rw, missing, read-only, no running backend); that the store
engine creates a missing path and restarts the backend only when needed after `kur`, `baslat`
and `uygula`; and that `master-wg` refuses writing commands on a read-only folder with the
Turkish remedy while reading still works (skipped when the runner is root). `wireguard-ui.cjs`
checks the new-network screen is one card no wider than the windows.

## Home edit mode and network card (DD-206, DD-212/213)

`test_overview.py` covers the layout's shape check, the root backend's layout endpoints
(save, read back, reset, 0600 file next to the account records, audit lines, refused bodies,
a damaged record read as the defaults, the X-Konsol and Host gates), the WAN rate sampler
(deltas, the 1.5 s step, counter resets, a stale baseline, interface name checks, a new
interface), `/api/konsol/ag` with package traffic modules in a temporary catalogue (installed,
stopped, unregistered, undeclared and built-in packages; broken modules reported once; the
2 s cache; no bytecode in the package folder; the 120 s window) and both packages'
`trafik.py` (qBittorrent's real `AllStats` line from nrm, large totals through a Qt-style
escaper, no file yet and damaged records; the WireGuard registry and interface counters).
`panel-ui.cjs` drives Ana Menü: installed-only tiles, clock/date in the home heading,
sidebar context, the compact two-of-six-slot network widget, cumulative/missing/zero totals,
fixed-height overflow and scroll/focus retention. The page clock verifies five-second
resources/modules/network reads, no duplicate ten-second home tick and no hidden-page
polling. Düzenle covers wiggle/reduced motion, keyboard moves, mouse drag, legacy layout
normalization, hide/show, Bitti, another device's order, Escape and Varsayılan. Both themes
and phone widths are checked. `common.bats` pins the source guards; fixture browsers do
not establish live deployment or fresh-install acceptance.

## Konsol sign-in (v2-166, DD-194; v2-181, DD-205)

`test_konsol_auth.py` covers the account store (creation without a code and without a
session, user and password rules, scrypt-only storage, the name revealed only to a
trusted caller, decoy work for unknown users, session expiry/limit/malformed tokens,
password change keeping only the current session, the tailnet password change ending
every session, reset, automation sessions, unsafe directory/symlink/FIFO/oversized/corrupt
records), the per-address attempt limit, the root CLI and the real root-backend
endpoints on a Unix socket: `/oturum-denetle` answers by channel (tailnet 204 without a
cookie and `/giris.html` → `/`; without Caddy's headers 302 page, 401 API, 204 with a
session and an open sign-in page; 403 for host-local or foreign Host), account creation
from the tailnet only, cookie attributes, 429 with Retry-After, sign-out and both
password changes, and audit lines without secrets. `common.bats` checks the Caddy
`forward_auth` matcher and order, the open sign-in files, the backend's channel
branches, installer wiring/stage-7 probes and that no setup code remains anywhere.

`giris-ui.cjs` (shared preview on port 8766) drives `giris.html` with intercepted
APIs and the production CSP: internet sign-in failure/limit/success, return to the
original page, the no-account notice, the tailnet and signed-in shortcuts back to
Konsol and Konsol's redirect after a 401. `settings-ui.cjs` covers the account card on
both channels (signed-in user with current password and sign-out; internet account, new
password only, account creation, no sign-out) and the sidebar sign-out.

```bash
PLAYWRIGHT_MODULE="$(npm root -g)/playwright" node Data/tests/giris-ui.cjs
python3 Data/tests/konsol-login-live.py --host nrm
```

`konsol-login-live.py` is an opt-in **mutating** test for an authorized host that
has **no** Konsol account yet (it exits 3 otherwise and changes nothing). From the
Mac, a tailnet device, it checks that Konsol, Files and the root API open without a
sign-in and that the sign-in page goes back to Konsol, creates a temporary internet
account through the real Caddy path, changes its password from the tailnet, signs
in/out with it, checks the attempt limit, then resets the account and restarts the
root backend to clear the limit. Passwords and tokens are never printed.

Live tests that call Konsol through Caddy from the Mac (`share-connections-live`,
`https-live`, `publications-live`, `backend-hardening-live`) open a short
root-issued session with `master-konsol oturum-ac` via `konsol_session.py` and close
it at the end. Host-side tests (`shares-live.py`, `archives-live.py`) use the
loopback Files backend and the root socket instead, because Caddy refuses
host-local Konsol callers (DD-180). The browser live suites
(`share-connections-browser.cjs`, `desktop-live.cjs`) take a session value in
`KONSOL_COOKIE`.

## Per-connection WebDAV policies and dual-card Shares (v2-164, DD-192)

From the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s Data/tests -p 'test_share_connections.py'
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s Data/tests -p 'test_webdav_connections.py'
```

These fixtures cover exact schema-3 migration and idempotent schema-4 preparation,
malformed/conflicting policies, independent defaults, nested partial saves under
locks, preserved omitted expiry, both-off, per-scope RW acknowledgement, legacy
HTTP consent, global publication gates and candidate-versus-active URLs. Protocol
checks cover both RO/RW directions, listener/header isolation, cached authentication,
all DAV writes, disabled/expired scopes, live chunks and staged-publication checks.
`files-ui.cjs` checks the two-card controls and scoped payloads with intercepted
APIs; its responsive matrix covers ten widths from 320 to 2560 in both themes.

Optional read-only acceptance against the installed console (Playwright required):

```bash
PLAYWRIGHT_MODULE="$(npm root -g)/playwright" node Data/tests/share-connections-browser.cjs
# Override the default http://panel.ayc when needed:
KONSOL_URL=http://panel.example PLAYWRIGHT_MODULE="$(npm root -g)/playwright" node Data/tests/share-connections-browser.cjs
```

This requires at least one existing share and creates none. Every API mutation
(any method other than GET/HEAD) is aborted and fails the check. It checks two
cards, four selects and two switches per share, address/Infuse host-port-path
consistency and copy-button presence, no overflow at 1440/900/390 in both themes,
and no browser errors. It does not exercise actual clipboard writes. Screenshots
go to an OS temporary directory, not the Desktop.

Opt-in **mutating** acceptance from an authorized Tailscale client against a
disposable host with schema 4, working public HTTPS and both global routes enabled:

```bash
python3 Data/tests/share-connections-live.py --host nrm
```

It creates one temporary folder/account and checks independent RO/RW in both
directions, listing/ranges, scope-header spoof rejection, both switches/both-off,
preserved peer expiry and stale global-policy/pause API rejection. WAN-only expiry
is accelerated only for its fixture using an atomic registry write under
`install.lock` → `modul.lock` → `paylasim.lock`, then restart/publication. Cleanup
removes only its own account/files and verifies the original registry is
byte-identical by SHA-256. Credentials remain in memory/SSH stdin and are not
printed; Caddy settings are not changed. **Share edits restart active WebDAV and
interrupt all transfers/playback.** Run outside active playback and do not edit
real shares concurrently.

The main implementation task reports: 36 new tests passed on macOS and Debian;
full Python suite 366 tests (macOS four skips, Linux one); Bats 165 tests (three
skips); six browser fixture suites passed with screenshots reviewed. After a
successful portable deployment on `nrm`, both opt-in scripts above passed: live
HTTPS/Tailscale policies and byte-identical cleanup, and installed UI at three
widths/two themes with zero errors or API writes. See [SESSION.md](../SESSION.md)
for exact run evidence and final host health. These results do not certify native
Infuse/Finder clients or a fresh supported-OS installation.

## Caddy publication table (v2-162, DD-191)

`test_publications.py` covers immutable Panel, exact catalogue/payloads,
independent DAV network gates, remembered off domains, native qBittorrent auth
requirements, duplicate/DNS rejection, first-row certificate failure, crash
rollback and module projection persistence. It reuses isolated transaction
fixtures and does not claim real ACME issuance.

`PLAYWRIGHT_MODULE="$(npm root -g)/playwright" node Data/tests/publications-ui.cjs`
starts its own local static server and runs the actual console with intercepted
APIs/CSP. It checks draft-only switches, single-click saves after typing, locked
Panel, validation, pending/failure/retry, reload and five widths in both themes.
Screenshots go to an OS temporary directory, not the Desktop.

`python3 Data/tests/publications-live.py --host nrm` is an opt-in **mutating**
test for a provisioned disposable host with verified DAV HTTPS and qBittorrent
installed (private or already public). It reads the public names from the host
and probes a missing name under the reserved `example.net`. It rejects Panel
WAN/duplicate/missing DNS through the real API, toggles each private route across
module reapply (every template address must answer 403, DD-193), and
disables/restores DAV HTTPS; a public qBittorrent must keep serving meanwhile.
It restores effective network choices and checks the folder-account digest. It
may interrupt transfers, never enables a new public hostname and never changes
application credentials.

On a Linux host with Caddy, qBittorrent, OpenSSL, iproute2 and setpriv:

```bash
unshare --net --fork python3 Data/tests/publications-proxy-linux.py --port 443
unshare --net --fork python3 Data/tests/publications-proxy-linux.py --port 18443
# exits 3 without changes when the host has no qbittorrent-nox package
```

This refuses the host network namespace and uses a temporary profile and local
test certificate (no ACME or trust-store change). The generated Caddy route is
real: native login/cookies, API access, incorrect password, CSRF, overwritten
forwarded Host, strict SNI/Host and Panel isolation are tested on both ports.
Host omits the public port for native listener validation; X-Forwarded-Host
keeps the external authority for CSRF. This does not certify public DNS/ACME.
`firewall-linux.py` additionally tests qBittorrent-only and shared DAV HTTPS
permissions, one shared port rule, and stopped/unsafe-native-auth closure.

## Public WebDAV HTTPS (v2-161, DD-190)

From the repository root, run the local tests without a live domain:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s Data/tests -p 'test_https_*.py'
```

`test_https_settings.py` covers full-domain/DNS validation (exact assigned WAN
IPv4, no AAAA/proxy), pinned chain/hostname verification, durable commit,
failure/crash rollback, explicit off without HTTP downgrade, retained renewal
listener after last-share pause, preserved accounts/local domain and legacy
HTTP consent. `test_https_panel.py` covers status/expiry warnings at 14 days or
less, unknown/error handling, selected firewall ports, Caddy scheme/source
parsing and the existing gated Settings API. These are fixtures, not real
Let's Encrypt issuance or public-reachability tests.

With the local console preview below running on port 8766 and Playwright installed:

```bash
PLAYWRIGHT_MODULE="$(npm root -g)/playwright" node Data/tests/settings-https-ui.cjs
```

This runs the production Settings/Shares UI with intercepted APIs and the actual
Caddy CSP. Since DD-193 public WebDAV HTTPS is edited only in the “Adresler ve
erişim” table, so the suite drives that row: isolated publication/local-domain
drafts, validation, long pending saves, repeated-click blocking,
ready/pending/error/expiry displays, failure/retry, draft switch/discard,
persisted off with the remembered name, the legacy-HTTP port note,
scheme-specific share links (a closed WAN card is labelled “WAN”) and HTTP
consent. It checks four widths in both themes. It does not modify a server.

External acceptance is opt-in, from an authorized Tailscale client to a disposable
host. Supply a real public domain whose DNS resolves only to that host's assigned
WAN IPv4, with no AAAA/proxy, and permit inbound TCP 443. Settings' pinned local
certificate probe does not itself prove that external path. From the repository root:

```bash
# Requires the matching domain already saved and certificate status ready:
python3 Data/tests/https-live.py --host nrm --domain dav.example.com
# Alternatively, deliberately save the real domain through Settings first:
python3 Data/tests/https-live.py --host nrm --domain dav.example.com --configure
```

Replace the example domain; the script uses public TCP 443. `--configure` is a
real, persistent Settings change: **the domain remains saved after cleanup**.
Without that flag, the script requires the matching saved domain to be ready.
It verifies public TLS trust, denies `/` and administrative routes, checks old
WAN HTTP closed, and creates three temporary shares: RO and RW on both networks,
plus Tailscale-only. It exercises HTTPS/Tailscale reads, PROPFIND, ranges, download
integrity, RO rejection, WAN scope, PUT/MOVE/DELETE and both connections off.
Cleanup removes only its accounts/files and checks the original registry digest;
credentials stay in memory/SSH stdin and are not printed. Account creation,
connection changes and removal restart
WebDAV and interrupts current transfers: run outside active playback and do not
edit real shares concurrently. Domain disable/re-enable, reboot, supported-OS
fresh installs and native-client acceptance are separate tests.

This runbook describes test scope, not completed results. Record actual runs in
`CHANGELOG.md`/`SESSION.md`.

## Remaining audit stages (v2-160, DD-187–189)

`test_install_hardening.py` checks descriptor-based selective permission repair,
unsafe parents, replacement races, hard links, special files and excluded trees.
`install-hardening-linux.py` adds real root ownership and competing/inherited
flock tests; run as root in a temporary test tree, never by sourcing install.sh.
`firewall-linux.py` adds cold malformed-registry rescue, valid-policy/manual-deny
preservation, secondary-interface default drop and successful recovery in isolated
network namespaces. It does not alter the host's policy.

`test_stage3_webdav.py` covers separate auth pools, short waits/cache rechecks,
single-flight sharing of identical concurrent logins and its failed/slow-leader
fallbacks (DD-193), 503 versus credential 429, bounded overload replies, slow PUT/COPY independence,
late target/source/parent/share/expiry/precondition conflicts and stage cleanup.
`test_stage3_files.py` covers deep JSON and socket inactivity; share-path tests
distinguish incomplete/internal roots from existing-share overlap.
`test_stage4_dns_json.py` covers `/4` projection and explicit IPv6 records plus
controlled deep HTTP/worker JSON. `test_stage4_health.py` tests required/inactive
and deliberately stopped units, unknown probes and kernel boot-link evidence.

Live acceptance must additionally validate Caddy/dnsmasq/systemd, cgroup OOM
events under WAN/Tailscale transfers, real A/AAAA replies and health before/after
reboot. Synthetic clients do not certify native Infuse or a fresh Ubuntu image.

## Backend admission and filesystem guards (v2-159, DD-186)

`test_backend_hardening.py` opens 24 real sockets per server before starting
the accept loop, isolating the listen backlog from HTTP processing limits.
Temporary fixtures exercise both qBittorrent readers against FIFOs (with a
subprocess deadline), final/parent symlinks, directories and oversized files.
Files tests cover reserved sources, all-selection validation before mutation,
reserved destination promotion, safe restore and ordinary file operations.
Run this suite on Linux too; no host configuration or credentials are used.
The backlog test is not a throughput benchmark or a substitute for cold-cache
Infuse concurrency tests. Existing WAN budgets are intentionally unchanged.

`backend-hardening-live.py --host nrm` runs 100 requests per API with 20
parallel fresh client connections and 120 direct cold Unix-socket requests.
It then creates a disposable RO WAN+Tailscale share, reads two 256 MiB files
with SHA256 verification, samples cgroup `anon`/`file`/`current`/`peak`, and
checks parallel PROPFIND and ranges on each network. Only the test files'
clean cache pages are evicted before reading, not the host cache. Cleanup
removes the temporary account/files and compares the original registry digest.
This restarts WebDAV twice; use an authorized test host outside active playback.
The measured cache increase does not prove the cause of a historical peak.
The WAN half follows the host's mode (DD-193): HTTPS on the configured public
name, or legacy HTTP on `SHARE_PORT`; a host with WAN off is refused up front.

## Folder network selection and WAN admission (v2-153, DD-179)

`test_share_manager_networks.py` covers opt-in, immutable
credentials/identity/expiry on network edits, public projection, rollback and
interrupted-change recovery. `test_webdav_networks.py` checks scope before
hash/filesystem work, header spoofing, sliding failure windows, bounded tables,
parallel hashes/requests, distinct loopback pools, timeout/abort cleanup and
expect-continue/pipeline behavior. Run on Linux as well: macOS skips the test
that binds the same port on a second loopback address. `share-networks.bats`
checks deployment wiring and conditional firewall/edge limits.

With explicit disposable-host authorization, run from an external client against
legacy HTTP WAN mode (no HTTPS setting; use `https-live.py` for HTTPS). On any
other host it prints `SKIP` and exits 3 before creating anything (DD-193):

```bash
python3 Data/tests/share-networks-live.py --host nrm
```

Only temporary folders/accounts are published, with random credentials kept in
memory/SSH stdin. The test exercises actual WAN and Tailscale Caddy endpoints,
cross-scope refusal, GET/PROPFIND/ranges, RO/RW, forged Host/client-IP, idle TCP
admission, simultaneous-request/login caps, tailnet availability, last-share
pause and timed expiry. WAN ingress packet counters confirm external routing.
Cleanup removes only the fixture prefix/accounts, never existing shares.
Fresh supported-OS installation, reboot and native Infuse/Finder acceptance are
separate; protocol tests do not certify every DAV client.

## Model A and compact App Store (DD-160/DD-161, v2-131)

Serve the real `Data/console` tree locally as below, then run
`node Data/tests/panel-ui.cjs` from the repository root. It applies the actual
Caddy CSP and fixtures all API calls: clean/installed sidebar, qBittorrent
lifecycle and own settings, keyboard tabs, five widths, resource
stale/offline/recovery, ZIP create/cancel/nested-unzip/result routes, and async
WireGuard new-network bookmarks. No server is modified.
App Store checks include compact row height, only one details panel, keyboard
focus across polls, real-progress fixtures, failures with details closed,
stop/start/removal and cancellation, default data retention, log HTTP errors
and safe text rendering, no account reads, and visible status at mobile widths.
`test_resources.py` covers independent sampling, guest CPU accounting, unknown
measurements and real HTTP Host/header/origin gates.

## qBittorrent integration-only seed (DD-178, v2-152)

Bats requires an exact six-key seed allowlist (startup notice, two download-path compatibility keys
and three authenticated WebUI keys; DD-218's chosen defaults were reverted by DD-219). The module
fixture renders that real seed; reapply and remove/reinstall must preserve user
UPnP/discovery/temporary-path choices byte-for-byte and never apply the firewall.

On an authorized Linux test host with Podman and the package's image present (set
`TORRENT_TEST_IMAGE` to the digest the host runs when it differs from `torrent.env`):

```bash
PYTHONDONTWRITEBYTECODE=1 unshare --net --fork python3 Data/tests/torrent-defaults-linux.py
```

This refuses the host network namespace, runs the package image (`--network host` of the private
namespace, never the server's, no pull) as uid 1000 in disposable profiles, and compares the actual
seed against the same qBittorrent's defaults: no user preference is forced (UPnP, LSD, encryption,
anonymous mode, queue, temporary folder, preallocation and the rest stay native). It checks local
authentication (qBittorrent 5.2 answers a good login with an empty 204),
the download location and restart persistence of user choices (UPnP, LSD, a temporary folder, the
active-download limit). No torrents are added, no installed config
is read, no host service is controlled, and fixture passwords are never printed.
It does not replace clean Debian/Ubuntu installation or service-sandbox tests.

## Reserved `.pay` path (DD-171)

The Bats suite checks that stage 3 never creates the reserved `SHARE_DIR`
(`.pay`), that stage 3 and `master-modul yerlesik` leave an existing one (contents,
modes, marker symlink) untouched, that registry preparation is idempotent and
public lifecycle actions refuse, and that the Files backend refuses to list it
and writes nothing into it. Folder-sharing tests are described below.

## Built-in ZIP/RAR (DD-159, DD-166, DD-170)

v143 adds automatic nested extraction/default depth-ceiling rollback tests and
installer-driven default-destination state. The native RAR suite submits without
the optional depth fields. `panel-ui.cjs` checks the compact form, automatic ZIP
suffix, default downloads, folder picker navigation/cancel/read-error/retry and
failed submit draft retention. `files-ui.cjs` checks the bottom selection dock at eight
widths/both themes, stable breadcrumbs/search, hidden-view/selection lifecycle,
and notifications never covering its actions. Run browser suites sequentially
against the simple preview server to avoid parallel request-queue timeouts.
v144 additionally checks six stable icon/label slots, single-file/archive/folder
and mixed-selection eligibility, keyboard focus and activation, download excluding
folders, archive/share/move dialog routing, equal cells, a mobile 3×2 grid and
unfilled danger styling under both themes.

From the repository root, run all Python suites with an OpenSSL-enabled Python:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s Data/tests -p 'test_*.py'
```

`test_archives.py` covers round trips, nested depth on/off, name collisions,
traversal/links/duplicates, byte/entry/central-directory/deadline limits,
malformed inner archives, cancellation/concurrency and interrupted-job recovery.
`KONSOL_FILES_BACKEND` can point at the installed backend for Linux tests.

`test_rar.py` adds mocked multipart/unsafe-input/budget tests and real subprocess
deadline/cancel/output-cap checks on all hosts. Native RAR→ZIP→RAR is tested on
Linux with `/usr/bin/unrar` and distro `python3-rarfile`; otherwise it is explicitly
skipped. Set `RAR_FIXTURES` to a private directory containing the upstream
markokr/rarfile `test/files` fixtures named by the optional native test to cover
compressed RAR3/RAR5, solid/old/new volumes, Unicode, encryption and link rejection.
Tests copy them into TemporaryDirectory; no downloads or package installs happen
inside tests. Browser fixtures test `.rar`, `.r00`, `.part01.rar` selection and
submission as well as ZIP; ordinary files never offer extraction.

`archives-live.py prepare` is a **mutating disposable-host test** through the
installed Caddy/file service. Keep the printed manifest for `verify <manifest>`
after rerun/reboot and `cleanup <manifest>` afterward. Cleanup removes only its
scratch tree/manifest, retaining ordinary job history as an audit record.

`desktop-live.cjs` tests the **real host**, not fixtures. Set `ARCHIVE_FIXTURE`
to the basename of that live test tree; it creates/extracts browser ZIP outputs.
It checks Model A navigation/resource indicators, built-in shares, settings and five
viewport widths. `TEST_APP_LIFECYCLE=1` explicitly enables qBittorrent
install/stop/start/remove (requires it absent initially, leaves its package and
profile, never requests data deletion). `KONSOL_URL` defaults to `http://panel.ayc/`.
Playwright variables below also apply; screenshots go to a temporary directory.
Do not run live tests against an unauthorized host.

## Settings management (DD-156/DD-157, v2-127)

WireGuard internet-only (DD-177): `wireguard-ui.cjs` tests creation/settings with
no Local selector, DNS-only saves, polling/error/cancel/stopped-network behavior,
explicit regeneration and four widths/CSP. Since DD-200 the page is the package's
(`magaza/wireguard/sayfa.js`): the suite serves `/uygulama/wireguard/*` from the
`magaza/` folder through Playwright routes and uses `/api/uygulama/wireguard/*`;
`panel-ui.cjs` does the same for the WireGuard deep link and reads both packages'
`konsol.json` for the App Store texts. `test_wg_settings.py` drives the package's
API module through the root backend's dispatcher: it rejects a supplied `scope`
field on both routes, checks revision/gates, the `master-wg` argument lines and
the `wireguard:<verb>` audit prefix; `test_resources.py` covers the module listing's
`konsol`/`sayfa` fields and the API module's load/unload with the registry. Bats
verifies DNS-only preservation and rejects access-scope CLI arguments.
`firewall-linux.py` tests actual IPv4/IPv6 host deny (including prior flows),
internet forwarding/NAT, private destinations through WAN, and tailnet isolation.
Veth fixtures pin WG IPv6 neighbors because real WireGuard uses no NDP.

Firewall categories (DD-164, v2-134): `test_firewall_view.py` covers read-only
socket scope classification, IPv6 normalization/zones, read failures, public-only
network metadata, service-name reuse and WAN endpoint versus tunnel permissions.
`settings-ui.cjs` tests default Tailscale, nested keyboard tabs, draft retention,
absent/empty/multiple WireGuard networks, read-only internet-only WG policy, protected
loopback and listener-versus-policy labels (including unknown/unreadable).

Minimum tailnet exposure (DD-172, v2-146): `test_tailnet.py` verifies configured
service ports, validated Self-only PeerAPI discovery and daemon-startup fallback.
The view suite also rejects listener-implies-access and preserves WG endpoints.
Run `unshare --net --fork python3 Data/tests/firewall-linux.py` as root on the
authorized Linux test host. It refuses the host namespace and uses nested veth
clients/echo listeners to test actual IPv4/IPv6 WAN, tailnet and WG input packets,
operator allow/deny precedence, idempotency and extra-rule detection. No installed
service, account or host firewall is modified; all fixtures are temporary.

Tailnet catalogue cleanup (DD-173, v2-147): the view tests exclude arbitrary
peer/backend/admin sockets, retain configured per-family ports even without
listeners, and keep registered WG endpoints with no active peers/sockets.
Browser fixtures preserve explicit tailnet allow/deny rules, editable drafts,
remove/cancel behavior and fallback to default deny without invented port rows.
Live checks must also verify raw diagnostics and required local services remain.

WAN/tunnel catalogue cleanup (DD-174, v2-148): view tests cover configured SSH/
Tailscale ports and IPv4-only WAN WG endpoints independent
of sockets/peer count; retired tunnel permits stay absent. Browser fixtures exercise
explicit allow/deny toggle/remove/cancel for WAN and Tailscale; a closed
user rule remains visible even where no automatic row exists.

Firewall source cleanup (DD-175, v2-149): `firewall-linux.py` additionally starts
from absent module/network files, then verifies preserved networks cannot revive
an absent/empty/stopped module. Test teardown/re-add, no empty forwarding/NAT
chains, repeatability of both tables/families, stale extra INPUT/FORWARD/NAT rules,
unchanged third-party jumps/chains and retained network files. The view suite
covers single-port WG rules and intentionally absent chains versus real failures.
These are isolated policy fixtures, not a fresh Debian/Ubuntu image installation.

DNS-only Apply (DD-163, v2-133): unit tests cover immediate persistence past
the old deadline/reboot, pre-write panel-name protection, mixed confirmation,
restart/commit failure rollback, pre/post-commit crashes and recovery retries.
Browser fixtures assert a single Apply request, no dialog/countdown/confirmation,
reload persistence, failed-apply draft retention and retry. The isolated Linux
DNS test checks immediate commit and failed-apply recovery with real dnsmasq.

Firewall tables (DD-162, v2-132): `settings-ui.cjs` additionally verifies full
semantic tables at five widths, row explanations/source CIDRs, filter/empty
states, protected loopback, on/off drafts, edit/remove, lock during confirmation,
payload/rollback, production CSP and keyboard scrolling without page overflow.

Folder sharing (v2-128, DD-158): also run `python3 -m unittest discover -s
Data/tests -p test_shares.py` and `node Data/tests/files-ui.cjs` from the repository
root. Python must have OpenSSL scrypt (the macOS system Python may not; use an
OpenSSL-enabled Python 3.12+). Linux distribution Python is the production runtime.
The Files UI suite also checks exact share clipboard input and adjacent address/
copy-button geometry in the list and folder details at five widths (v2-138).
Copy APIs are intercepted in fixtures; native iPhone clipboard behavior is not
covered by those checks.
Inline Shares and compact trash (v2-142, DD-169): `files-ui.cjs` checks partial
access/expiry payloads, RW confirmation/cancel/Escape, failed saves, disabled
in-flight controls, account-only editing, eight responsive widths and short
long-filename trash dialogs in both themes. Existing permanent-delete guards
remain tested. `test_shares.py` covers omitted-field preservation, required RW
acknowledgement, rollback and never rebinding a replaced folder via inline edits.
Password policy (v2-141, DD-168): the settings/shares Python and browser suites
reject seven-character passwords and accept eight, preserving blank edits.
`test_shares.py` also verifies real WebDAV GET/PROPFIND authentication and the
read-only write boundary with eight characters. `settings-linux.py` verifies
native qBittorrent login and restart persistence with a disposable eight-character
account inside its private network namespace; it never changes installed accounts.
`shares-live.py prepare` is a **mutating disposable-host test**, using installed
services, two scratch accounts and a random folder. Keep its printed manifest
path for `verify <manifest>` after rerun/reboot and `cleanup <manifest>` afterward.
It does not certify Finder/Infuse clients or Tailscale recipient ACLs.

From the repository root:

```bash
LC_ALL=C PYTHONDONTWRITEBYTECODE=1 bats Data/tests/common.bats
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s Data/tests -p test_settings.py
python3 -m http.server 8766 --bind 127.0.0.1 --directory Data/console
# In a second terminal, with Playwright installed:
node Data/tests/settings-ui.cjs
```

On the operator Mac (2026-09-30) Node comes from Homebrew and Playwright is a
global npm package outside the repository, so point the suites at it:

```bash
PLAYWRIGHT_MODULE="$(npm root -g)/playwright" node Data/tests/panel-ui.cjs
```

The fixture suites (`panel-ui`, `files-ui`, `settings-ui`, `settings-https-ui`, `wireguard-ui`,
`torrent-ui`, `giris-ui`, `app-install-ui`, `update-ui`, `files-nav-ui`) share the same `http.server` on port 8766. `settings-ui.cjs` also covers the
health card and the stuck-rollback discard (DD-182); `panel-ui.cjs` the archive
bar that replaced the jobs page (DD-183).

`PLAYWRIGHT_MODULE`, `PLAYWRIGHT_CHROMIUM` and `KONSOL_URL` may override the
module, browser executable and preview URL. The test intercepts APIs with
fixtures; it never modifies a server. It covers tabs, review/discard, custom
rules, DNS, confirmation/rollback, address explanations (the qBittorrent
account/folder form is `torrent-ui.cjs` since DD-202),
domain review/new-address links/old-host confirmation refusal, four widths and dark
mode. Screenshots go to a fresh temporary directory.

On a Linux test host with root, iptables/ip6tables, dnsmasq, dig, qBittorrent
and systemd (no additional packages are installed by these tests):

```bash
PYTHONDONTWRITEBYTECODE=1 unshare --net --fork python3 Data/tests/settings-linux.py
PYTHONDONTWRITEBYTECODE=1 python3 Data/tests/settings-systemd.py
PYTHONDONTWRITEBYTECODE=1 unshare --net --fork python3 Data/tests/settings-domain-linux.py
```

The first refuses the host network namespace, uses scratch profiles and
dummy interfaces, and substitutes only service control; firewall, DNS and
qBittorrent are real. The package worker's account and folder functions (DD-202)
verify real new/old login results, restart persistence, failed-restart recovery,
the save path with its drop-in, and stopped-state preservation.
A local upstream fixture verifies forwarding without
internet access and proves private names are not forwarded. The second uses
real transient systemd work/timer units with a scratch pending record and no
firewall/DNS/qBittorrent changes. Both remove only their own scratch state.
These checks do not replace a fresh Debian/Ubuntu installer acceptance run.

`settings-domain-linux.py` needs Caddy, dnsmasq, dig, curl, setpriv and Python,
but not qBittorrent. It starts the real Caddy and both production API backends
against scratch files, with private DNS/network interfaces. It checks domain
apply/rollback/confirm, real Caddy reload, both Host/header gates, no `health.`
name or site, persisted domain and staged templates. Only systemctl is adapted to
those processes; host services and their settings are never touched. Unit tests
also cover timeout/reboot/crash recovery, state IP preservation, invalid suffixes,
stale renderings, inactive services and installer saved-domain readback.

## Acceptance-check lessons (2026-09-11)

- `tailscale status --json .Self.ExitNodeOption` is **not** an installer
  assertion. It turns true only after the exit node is approved in the admin
  console — the manual step the install summary lists. The installer's own
  obligation is `AdvertiseRoutes` containing `0.0.0.0/0` in
  `tailscale debug prefs`; assert that, and report `ExitNodeOption` as
  information.

## Pitfall: an early-exiting pipe consumer under `pipefail` (2026-09-12)

`install.sh` runs with `set -Eeuo pipefail`. A read-back written as
`apt-config dump | awk '/pattern/{print $2; exit}'` looked harmless and
passed every static check, but on the host it aborted the install with exit
141 after all seven stages had run: `awk` exits on the first match,
`apt-config` gets SIGPIPE writing the rest, `pipefail` turns that into 141,
and `set -e` exits at the assignment. Let the consumer read the whole stream
(`{v=$2} END{print v}`) or guard the pipeline with `|| true`, as the `dig |
head -n1 || true` read-backs do. A bats test now rejects `| awk … exit`
patterns in the installer tree.

## Pitfall: a second `tailscaled` on a provisioned host (2026-09-13)

`tailscaled --statedir=DIR` does not isolate a test daemon. `--state` has a
compiled default of `/var/lib/tailscale/tailscaled.state`, so the daemon
loads the production node's identity and preferences. On `nrm` such a daemon
came up `Running` as the production node for a few seconds and rewrote
`/etc/resolv.conf`; the production daemon restored it within the same second
(`trample: resolv.conf again matches expected content`). The state file,
login and prefs were unaffected, and a `BackendState == NeedsLogin` gate
stopped the test before `tailscale up`.

Run test daemons inside a container with the binaries bind-mounted
read-only, pass `--state` explicitly, and gate on `NeedsLogin` before any
`up`.

## Konsol update button (v2-212, DD-233)

`test_update.py` covers the GitHub check (tip commit, version at that commit, cache, failure
back-off, forced-check gap, malformed answers), the job state/stage, the start rules, the pinned
`systemd-run` call and the Tailscale-only start route. `common.bats` runs `kur.sh` in update mode
(pinned commit, refused version mismatch, no terminal) and `master-guncelle` with local fixtures.
`update-ui.cjs` checks the button beside the clock, confirmation, payload, stage, failure, reload,
internet lock and phone widths with fixtured APIs.

## Files navigation (v2-218, DD-236)

`files-nav-ui.cjs` drives a 60-folder fixture: the fixed window (no page scroll at 1440×900), the
frame's DOM nodes surviving every open, no layout shift, the contents' scroll reset on open and
restored on back, the cache shown at once and read again, the dimmed inert old listing while a held
folder loads, a stale answer dropped, a failed open staying put, a poll that keeps tile nodes, the
keyboard, the search box, and the page scroll at 1024 and 390 px.

`files-nav-ui.cjs` also checks DD-237 (v2-219): the detail panel under the contents with a height that
selecting never changes, the right column without details, Favoriler's eight entries and switch, the
folder in the address (pushed on open, opened after a reload, browser back/forward, bare `#/dosyalar`
keeping the folder, an undecodable address opening the root). `files-ui.cjs` checks the one-line share.
