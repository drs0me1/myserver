# Session history (archived)

Historical session notes moved verbatim from `Data/SESSION.md` on 2026-09-30
(v2-158 documentation trim): task entries from v2-153 back to the 2026-08
Docker/wg-easy era, the last status table (v2-79) and the 2026-08-28
"Evaluated and rejected" list. They describe past states, not current
behaviour; `Data/SESSION.md`, `Data/docs/contract.md` and
`Data/docs/design-decisions.md` take precedence. Relative paths inside the
entries are relative to `Data/` as originally written.

## Previous tasks (historical; newer decisions take precedence)

**2026-09-29 — HTTP WAN folder-share selection, v2-153 (DD-179):**
- User approved implementing/deploying the network-selection proposal but
  explicitly retained HTTP. WAN password-attempt and connection limits are
  mandatory. Existing shares remain Tailscale-only; no real share was opted in.
- Schema 3 stores per-folder networks; stable ID/hash/permission/expiry. Two
  loopback scopes on the same SHARE_PORT isolate WAN/tailnet budgets. Caddy
  overrides the socket-peer header, exposes only `/s/*` on explicit WAN IPv4,
  and projects/removes its site with the last active share. Public IPv6/NAT,
  certificates and Tailscale policy changes are outside this phase.
- Limits: 5 bad attempts/60s → 300s IP block; 4096 history entries; 4 hash slots;
  8 WAN connections, 4 requests/IP, independent 16 tailnet connections; backend
  idle 30s. Edge TCP 16/IP, 64 total, Caddy header 10s/idle 30s. Manual firewall
  denials remain ahead of base permission. Caddy startup waits for/checks FW.
- Root changes keep a private pending snapshot and restore on failure. The
  scoped 30s guard handles expiry and interrupted operations under existing
  locks. Installer recovery reloads the old credential before clearing pending.
- UI: checkboxes/HTTP acknowledgement, network column, labeled adjacent-copy
  URLs, limits note. Access and duration remain inline. Caddy inventory now
  recognizes proxy blocks and labels WAN separately; firewall has conditional
  IPv4 WebDAV permission only while needed.
- Deployed through the portable launcher with scratch `kurulum.env` (SSH_HOST
  nrm, blank LOCAL_DOMAIN), default no full-upgrade and E confirmation. Never
  opened the operator input file. Three incremental deployments succeeded;
  final payload SHA256 `ad705b542391b24940a2fd7ea013c4b0beefa45b56cc42ee210af39dad80f91f`.
  Root/Data/app launchers are identical; all 46 embedded runtime files match.
- Checks: 159 Bats (156 pass, 3 platform skips), 170 local Python (167 pass,
  3 optional native RAR/loopback skips); 66 installed Linux share tests all pass.
  Bash/ShellCheck, systemd-analyze verify, dnsmasq --test and firewall --check
  passed. Settings and Files browser suites passed. Files UI added a detached-DOM
  measurement regression: actual 6px copy-button adjacency stays asserted.
- External Mac → actual WAN IPv4 acceptance passed selection/isolation,
  GET/PROPFIND/ranges, RO/RW, forged Host/IP, TCP cap, concurrent request cap,
  login block, independent tailnet availability, last-share pause and timed
  expiry. WAN ingress counters prove this was not merely a loopback test;
  live Caddy configuration confirms public header/idle deadlines. Test fixtures
  were removed without targeting other accounts. Final nrm registry is empty,
  with no test folder, pending operation, failed unit or active WAN share left.
- Initial testing caught an unknown Host yielding empty 200 (now explicit
  public catch-all 404), a test expectation mismatch (expiry is 403), and
  cleanup colliding with the guard lock (fixture cleanup now retries). One
  parallel test upload hit the operator SSH local-forward config; tests now
  pass ClearAllForwardings=yes and never modify that config.
- Evidence: `/tmp/master-stack-v153.40w1Du/` logs and scratch launcher/input.
  No commit/push; pre-existing v152 qBittorrent changes remain included. No
  fresh Ubuntu/Debian install, reboot, or native Infuse/Finder acceptance run.

**2026-09-29 — qBittorrent integration-only seed, v2-152 (DD-178):**
- User requested only panel/functional integration settings; UPnP, automatic
  mapping and local peer discovery must be left to the user. Removed their
  forced values plus forced separate temporary storage from the first-profile
  template. Six keys remain: startup notice, current/compatibility download path,
  authenticated loopback WebUI address/port. No service sandbox/firewall changes.
- Existing profiles are not migrated: their values may already be intentional
  user choices. Reapply and remove/reinstall preserve them byte-for-byte.
  Conventional incomplete-path guards remain for existing/manual configurations.
- Bats uses the real rendered seed, enforces its exact key allowlist, checks
  preservation/no firewall calls and reports both absent and user-set temp paths.
  First full run exposed an obsolete expected forced-temp assertion; corrected
  the expectation and added user-selected temp-path/read-only coverage.
- Final checks: 155 Bats cases (152 pass, three missing-timeout skips), 126
  Python cases (124 pass, two optional RAR skips), Bash syntax and ShellCheck.
  No browser layout/code changes; browser suites were not rerun.
- Added `tests/torrent-defaults-linux.py`: disposable network namespace and
  uid-1000 profiles compare native defaults, anonymous/authenticated loopback,
  downloads and user-selected UPnP/discovery/temp storage across native restart.
  Ran twice on nrm's Debian qBittorrent 5.1.0-2; both passed. No torrent added,
  installed profile read/changed, host service control or firewall mutation.
- Exported v152 to repo root and Data/app (no Desktop copy); both identical,
  all 44 embedded runtime files match source. Payload SHA256:
  `a24f3e97c3796fea73ec31cac24416943e395fe3ba01ba89c3320ffe6b64a0a7`.
  Previous repo/app v151 launchers are recoverable from Git (`c0826c0`).
- Evidence: `/tmp/master-stack-v152.6BTcfb/` local test logs; nrm scratch
  `/tmp/master-stack-v152.Jw3WDO/` contains only test script/template. Private
  profiles were automatically removed. No extra package installed (remote rsync
  absent; copied these two files with tar over SSH). No active test process.
- Full v152 deployment, fresh OS install and reboot not performed; current live
  preferences remain untouched. No commit/push. v145–151 were committed in
  `c0826c0` before this task; older "no commit" notes below are historical.

**2026-09-28 — Internet-only WireGuard, v2-151 (DD-177), supersedes v150 below:**
- User retired Local access everywhere, including existing networks, creation,
  settings and server configuration. DNS remains editable without key/profile reset.
- Runtime updated: fixed inet policy column, no API/CLI scope, no WG host-rule
  overrides; WG ingress denied before established/ICMP/ts-input and private
  destinations blocked before WAN forwarding. Internet NAT/replies remain.
- Installer stage 4 runs a narrow locked retirement helper: exact old caddy-wg
  instances/template/env, old scope values and WG overrides only. No broad cleanup.
- Workstation: 155 Bats cases (152 pass, three missing-timeout skips); 126 Python
  cases (124 pass, two optional native-RAR skips); WG/Settings/Panel/Files browser
  suites, Bash/JS syntax, ShellCheck and diff whitespace passed.
- Native isolated Linux test passes both families: mandatory host deny including
  established UDP, internet forwarding/NAT, private destinations via WAN, tailnet
  isolation, stale-rule detection, fresh/repeat/missing-module states and unchanged
  third-party rules. Veth fixtures pin WG neighbors (real WG has no NDP).
- nrm Debian 13 upgraded via portable v151, stages 0–7 passed. Existing wg0
  changed only policy ui→inet, retaining addresses/port/DNS/label and config hash.
  Seven base/application services active, WG up; no failed units or caddy-wg
  artifacts/listeners. Settings/shares/qB hashes and qB process unchanged.
- Real kernel WG tests used own peers on wg0 and a tagged new wg1. Both reached
  public IPv4/IPv6 internet and DNS; host SSH/qB/WebDAV were blocked on WG/TS/public
  addresses. Transport used host-loopback UDP to WG, not an external WAN device.
  Removed only own peers and empty wg1; original registry/activity restored.
- Repeated installation preserved all snapshot hashes, qB process, registry and
  normalized IPv4/IPv6 rules. Final visual review removed stale Caddy proxy copy
  and irrelevant WG toggle hints; packaged and installed through the exporter.
- Live read-only browser: no creation/settings Local toggle or API scope, DNS
  unchanged, readonly WG firewall, four widths/no writes/errors. Screenshots
  inspected. Root/app/Desktop payload contains 44 source-matching runtime files.
- Final portable payload SHA256:
  `e5953cb9d19a1f3a0793ba613d47ff8ad279b58a52d57ae2f85786d1b2dc69ce`.
  All 44 files match nrm's installer source; nine changed installed runtime files
  match workstation hashes. Final repeat/live Caddy copy checks passed. Task-owned
  preview/launcher sessions closed; no background test client or network remains.
- Scratch `/tmp/master-stack-v151.DdGuqK/` contains evidence and recoverable v150;
  previous Desktop v150 remains. Root/app carry v151. Private operator inputs
  never read or edited. Pre-existing dirty v145–150 work retained; no commit.
- Fresh Debian/Ubuntu image installation, reboot and external-device acceptance
  were not run this turn. Hosts using private DNS in device profiles must switch
  to public DNS for internet-only use; nrm's saved defaults are already public.

**2026-09-28 — WireGuard Local access default, v2-150 (DD-176):**
- User requested all new WG users get Local access by default and removal of
  its creation selector. Existing Local scope is narrow: installed qB UI at the
  network's own IPv4 address, not general LAN/SSH/panel/WebDAV/peer access.
- Removed creation Erişim card, toggle/draft/listener and unused CSS. API
  defaults an omitted scope to ui; creation posts only port/DNS/label. Updated
  preview/empty-state/help. Existing network settings retain the Local switch;
  explicit CLI/API inet/ui remain valid, and re-runs preserve saved scopes.
- Fresh live inspection superseded prior-turn host inventory: nrm now has only
  wg0/main, already ui, active, zero peers (different tailnet IP). No existing
  scope migration was needed; did not recreate a previously removed wg1.
- Tests: all 157 Bats cases (154 pass, three macOS timeout skips); 121 Python
  (119 pass, two native-RAR skips); WireGuard, Panel and Settings Playwright
  suites; Bash/JS syntax, ShellCheck and diff checks. Added omitted/explicit/bad
  scope and request/module gates; first/additional network UI creation, retained
  settings switch, failure/retry/cancel, polling drafts and four widths/dark/CSP.
  One new UI test initially raced hash navigation; waiting for the rendered first
  port fixed the test. Complete rerun passed; no production workaround.
- Exported root/app/Desktop v150 match; all 45 runtime payload files equal
  source with no private inputs/docs/tests/caches. Payload SHA256:
  670ccd845ab6210f2b48d2987752e908f3fd399a1b27a29b51ec2b6f6cb65f99.
  Installed backend equals source SHA256:
  43fa0f18471f80ab8dcf7c1cddd0263bef78e166a3005146153d39be24953238.
- nrm upgrade through portable only, own SSH_HOST=nrm/blank-domain scratch
  input (600), h full-upgrade/E confirmation. Stages 0–7 passed; no packages
  changed/reboot. Caddy/dnsmasq unchanged; qB process unchanged.
- Live API created only a tagged empty wg1 fixture without scope. Verified ui,
  active WG/Caddy, narrow IPv4 qB permit, IPv4/IPv6 catch-all WG drops, full
  firewall --check, qB UI HTTP 200 on the new network address and matching panel
  firewall row. Finally removed only that verified empty fixture through the
  official confirmed API. wg0 registry/key/DNS/port/activity remained unchanged.
- Before/after snapshots are byte-identical: settings/shares/module/network
  registry/WG/qB profile hashes, qB PID/InvocationID and complete normalized
  IPv4/IPv6 rules including all third-party content. Eight services active;
  no failed units. Real desktop/mobile browser shows v150, correct preview,
  no creation switch, retained wg0 Local-on setting and zero writes/JS errors.
- Scratch `/tmp/master-stack-v150.cVpBgK/` has test inputs, probes, snapshots,
  screenshots and recoverable v149 portable. Root/app now carry v150; Desktop
  v149 remains. Earlier scratch server path and hardcoded wg1 snapshot failed
  safely before changes; replaced with current-registry inspection and hash-only
  dynamic snapshot. No clean OS/Ubuntu/reboot/real client traffic acceptance.
  Earlier dirty work preserved; no commit/push.

**2026-09-28 — actual firewall source/rule cleanup, v2-149 (DD-175):**
- User requested a complete rule-generation/install audit, not just catalogue
  filtering. Reviewed the producer, defaults, installer/module lifecycle,
  watchdog/settings ownership and live filter/NAT/mangle tables. No active
  retired Docker/wg-easy/shared-root WebDAV generator or chain was found.
- Removed the missing-module-registry fallback that activated preserved WG
  network files. Absent/empty/stopped module records now produce no WG policy.
  No configured networks -> remove/omit only project FORWARD/NAT chains/jumps.
  All registered networks still retain requirements regardless of interface
  state/peer count; wg1/61020 explicitly preserved. No profile/data deletion.
- Removed eight redundant terminal RETURN rules; conditional settings returns
  remain. Single qB UI match uses --dport, not legacy multiport. INPUT checks all
  expected guards/ICMPv6 types and exact cardinality; NAT also rejects extras.
  Panel reads both old/new port syntax and expects absent WG chains only when
  no networks exist. Raw technical diagnostics remain unfiltered.
- Final local tests: 157 Bats (154 pass/three timeout skips), 119 Python
  (117 pass/two native-RAR skips), Settings browser suite, syntax/ShellCheck and
  diff checks. One old static ICMP assertion required updating after factoring
  its unchanged type list; complete rerun passed. Live probe initially counted
  eight chain declarations as rules; corrected the test's position filter,
  not production code. Final API checks passed before and after repeat install.
- Isolated native Linux tests used the exported payload (not installed host
  chains): clean baseline, preserved network with missing/empty/stopped module,
  teardown/re-add, duplicate/redundant/stale rule detection and removal, repeated
  application, explicit user allow/deny, both address families. Real veth
  packets verify WAN/tailnet/WG INPUT, WG->WAN NAT round trips and denied WG->TS
  forwarding. Stub ts-input and third-party filter/NAT chains/jumps unchanged.
- Root/app/Desktop v149 exports match; all 45 embedded runtime files equal
  source and no private input/docs/tests/caches are included. Payload SHA256:
  8a2cd1a4e0e3af28fec84141c0120c4b23b8050c9256dd426648159438b503e6.
  Installed firewall SHA256 615427f88613a5911b1d443c7ed261fc5ff2202437e12a471250b4a09ed7fd46;
  panel SHA256 068f76a2970373c318d1f3f00eab1ddfe4ce7a3421666b17918842614759892c.
- nrm upgraded and immediately rerun using only exported portable and scratch
  SSH_HOST=nrm/blank-domain input, h full-upgrade/E confirmation both times.
  Both runs passed stages 0–7, no package changes or reboot. Repeat left firewall,
  panel, Caddy and dnsmasq unchanged; WG lifecycle verification is intentional.
- Exact normalized before/after comparison: project IPv4 rows 39->35, IPv6
  42->38. The only other syntax delta is single-port matching. Every third-party
  rule/table/order, settings/share/module/network/profile hash and qB process
  unchanged. Second installation snapshot matches first byte-for-byte after
  counter normalization. Eight services active, no failed units/pending settings.
  Live tailnet API/socket/desktop/mobile checks pass, including SSH/PeerAPI both
  families, panel/qB UI, share authentication boundary and blocked direct ports.
- Local scratch `/tmp/master-stack-v149.7roWmk/` holds own inputs, before/after/
  repeat snapshots, probes/screenshots and recoverable v148 portable. Native
  scratch `/tmp/master-stack-v149-native.6U0iJk/` holds exported test tree only.
  Root/app now carry v149; prior Desktop v148 remains. Preview process stopped.
  No clean OS image/Ubuntu/reboot/real WG client throughput/authenticated Infuse
  claim. Earlier dirty work preserved; no commit/push.

**2026-09-28 — Internet/WireGuard catalogue cleanup, v2-148 (DD-174):**
- User requested the same simplification as v147 for Internet and WireGuard:
  remove unused automatic closed rows, not required WG network ports. Live nrm
  audit confirmed the saved firewall override list is still empty.
- Backend `settings_ports` no longer duplicates local/tailnet services or socket
  discoveries into closed WAN rows. WAN has configured SSH/Tailscale in both
  families and registered WG UDP in IPv4 only (matching existing policy).
  Tunnel-local rows are only IPv4 qB UI permits on `ui` networks. Preserve
  configured permits regardless of stopped interfaces, missing sockets/peers.
  No raw-rule or listener filtering, service deletion or actual firewall edits.
- Unit tests cover both families, configured non-default ports, unknown sockets,
  stopped/inet/no-network cases and required WG endpoints. Browser fixture now
  uses an explicit blocked wg1 rule rather than an obsolete automatic placeholder;
  explicit allow/deny toggle/remove/cancel passes in tailnet, WAN and WireGuard.
- Initial Bats run failed one old expectation requiring unknown socket 8081 to
  create a closed WAN row. Updated that assertion to require retained raw/local
  visibility and no remote row; focused and complete reruns passed. Final totals:
  157 Bats (154 pass/three timeout skips), 117 Python (115 pass/two native-RAR
  skips), Settings browser suite, syntax/ShellCheck/diff checks. No frontend
  production edits or new dependencies needed for this change.
- Exported root/app/Desktop v148 copies match; payload SHA256:
  04afbde658816db8d43d27a59cca2cc348a854682dd3a415f1a1057099d01a6b.
  Installed on nrm through portable only with own SSH_HOST=nrm/blank-domain input,
  h full-upgrade/E confirmation. Stages 0–7 passed, no package changes/reboot.
- Live API + readonly desktop/mobile browser: WAN IPv4 only 22/TCP,41641/UDP,
  61001/UDP,61020/UDP; WAN IPv6 only 22/TCP,41641/UDP. WireGuard shows wg0 IPv4
  61006/TCP only; wg1 and IPv6 have no automatic UI rows. Empty wg1 retains its
  selector and Add rule control; wg1 itself and its endpoint remain active.
  Technical rules remain visible; browser had zero writes/errors. Tailnet rows,
  panel/qB UI, SSH/PeerAPI dual-stack and unauthenticated WebDAV 401 remain valid.
- All eight project services active, no failed units/pending settings; installed
  backend hash matches source. Settings/shares/module/network registry/WG profile/
  qB profile hashes and qB PID/InvocationID unchanged. Both complete iptables-save
  snapshots match after stripping generated comments and normalizing counters.
  Existing default denies remain, with fresh TCP probes still blocked.
- Scratch probes/screenshots and recoverable old v147 portable:
  `/tmp/master-stack-v148.667cPe/`; v147 also remains on Desktop. Root/app now
  carry only v148. Preview server stopped; all earlier dirty work preserved.
  No clean install/Ubuntu/reboot/VPN throughput/authenticated Infuse claim.
  No commit/push.

**2026-09-28 — remove synthetic Tailscale port entries, v2-147 (DD-173):**
- User requested source-level removal of unused closed Tailscale entries for
  20902 TCP/UDP, 61006, 61008, 61009 and 2019. Live audit confirmed no explicit
  overrides (`ayarlar.json` firewall list empty). They were automatic copies of
  host sockets, not stale firewall allowances. 20902 belongs to qBittorrent,
  61006 its local UI, 61008/61009 the panel backends, 2019 Caddy's reload admin.
- Changed only the backend catalogue generator (plus version/docs/tests): tail
  rows now come from per-family configured core permits and registered WG ports,
  including networks with no sockets/peers. No arbitrary listener becomes a
  Tailscale row. IPv6-only unsupported Caddy/WebDAV entries also disappear.
  Explicit user allow/deny rules remain editable; raw listeners and technical
  rules stay unfiltered. Default deny still blocks these ports. No port blacklist,
  service removal, bind/interface change, qB restart or firewall policy change.
- Local: all 157 Bats cases passed with three platform skips; all 114 Python
  cases passed with two native-RAR skips. Settings browser suite includes explicit
  tailnet allow/deny, toggle/remove/cancel and no automatic fallback-row tests.
  Syntax/ShellCheck/diff checks passed. Existing v145/v146 dirty work preserved.
- Exported root/app/Desktop v147 copies match. Embedded payload SHA256:
  d20bc7582dc84ffc2c310089199125947d4cc56852f8196d140e946af87df4fb.
  Deployed only through portable using own scratch SSH_HOST=nrm/blank domain,
  h full-upgrade/E confirmation; stages 0–7 passed, no package changes/reboot.
- Live API + read-only browser confirmed target rows absent in IPv4/IPv6, raw
  diagnostics/local rows preserved, WG endpoints 61001/61020 allowed and both
  networks active. New TCP connections to all reported ports remain blocked;
  SSH/PeerAPI dual-stack and panel/qB UI respond; WebDAV retains unauthenticated
  401. Eight services active, no failed units/pending settings. Installed backend
  hash matches source. Settings/shares/module/WG registry/WG configs/qB profile
  hashes and qB PID/InvocationID unchanged. No new live UDP packet probe was run;
  the unchanged dual-stack firewall checker passed (v146 isolated packet coverage).
- Scratch probes/screenshots and preserved v146 portable:
  `/tmp/master-stack-v147.xpHRjj/`. Root/app now carry only v147; v146 also remains
  on Desktop. Preview server stopped. No clean install/Ubuntu/reboot/live VPN
  throughput/authenticated Infuse claim. No commit/push.

**2026-09-28 — minimum firewall exposure, v2-146 (DD-172):**
- User authorized audit and restriction of unused exposure, then explicitly
  clarified that every user-created WireGuard network/port is a requirement.
  Do not disable/delete wg1 or close its endpoint based on zero peers/counters.
  wg0 UDP 61001 and wg1 UDP 61020 remain configured/active and unchanged.
- Audit found no legacy Docker/Portainer/Filebrowser/wg-easy listeners or rules.
  WAN already permits only SSH, Tailscale and registered WG UDP. The real excess
  was blanket tailnet ingress before host policy: qBittorrent peer TCP 20902
  was reachable from the Mac, although WAN peer ingress was already blocked.
- Added a core tailnet allowlist/default drop after operator overrides in
  CHAIN_SETTINGS, before ts-input. Keep loopback, established/related and ICMP;
  allow SSH/DNS, IPv4 Caddy/WebDAV, Self-only per-family PeerAPI endpoints and
  all registered WG UDP ports. WAN, WG local input, FORWARD/NAT and Tailscale
  chains are not changed. No service/listener/package removal or credential edit.
- Panel policy uses the shared allowlist; unknown listeners no longer imply
  tailnet permission. Current Caddy templates bind IPv4 only, so no unused
  IPv6 HTTP/WebDAV permission. Updated table explanation, contract and DD-172.
  Settings-helper edits now trigger firewall and panel refresh on reinstall.
- Local verification: 157 Bats (154 pass/three timeout skips), 113 Python
  (111 pass/two native-RAR skips), Settings browser suite, syntax/ShellCheck/diff.
  Native Debian: 113 Python pass with real RAR plus the final focused helper
  rerun; isolated firewall packet and settings/DNS/qBittorrent transaction tests
  pass. Packet fixture covers IPv4/IPv6 tailnet/WAN/WG, explicit user allow/deny,
  idempotency, extra-bypass detection and unchanged Tailscale-owned rules.
- Initial packet-fixture override assertion failed because its state included
  defaults' STATE_FILE instead of the scratch file; fixed the fixture. Only its
  private namespace firewall was modified. Concurrent SSH testing initially hit
  local-forward conflicts; use ClearAllForwardings=yes for all nrm checks.
- Deployed through the exported portable only, scratch SSH_HOST=nrm/blank domain,
  h upgrade/E confirm; stages 0–7 passed, no packages/reset/reboot. A final portable
  refinement removes unused IPv6 Caddy/WebDAV allowances. Root/app/Desktop
  copies match the scratch export; embedded SHA256:
  c472baccf0bf3d0d6268c7d712454611fdfdccde4f140a9780c185f88acf0b15.
- Live Mac checks: panel/qB UI, DNS UDP/TCP, IPv4/IPv6 SSH and PeerAPI respond;
  new qB TCP 20902 and direct backend connections are blocked. Both-family drop
  counters increment. WebDAV retains its 401 authentication boundary (no stored
  password was read). API permissions and desktop/mobile toggles agree; browser
  performed zero writes and had no JS errors. Eight services active, no failed
  units/pending settings. The temporary rollback timer was stopped after checks.
- Before/after SHA256s for settings, shares, module/network registries, both WG
  configs and qB profile are identical, as are Tailscale INPUT and WG FORWARD/NAT
  rule texts. qB PID/InvocationID remain 340708/c3a224de978a48dc8c6969043a79cbff.
  No external tailnet policy, user data or network configuration was removed.
- Scratch/live probes/screenshots/old v145 portable: `/tmp/master-stack-v146.HTNI8K/`.
  Native isolated test copy: `/tmp/master-stack-v146-native.95kSul/` on nrm.
  Only generated v145 root/app copies were replaced; scratch/Desktop retain it.
  No clean Ubuntu/reboot, live VPN-client throughput or authenticated Infuse
  acceptance claim. Existing v145 dirty work was preserved. No commit/push.

**2026-09-28 — remaining cleanup complete, v2-145 (DD-171):**
- Continued the approved phases 1–2 below, preserving their dirty changes.
  Removed unreachable public Files/WebDAV lifecycle/data-delete branches, shared
  password plumbing, `.pay` marker readers/writers and old credential defaults.
  Current built-in service/registry IDs, per-folder account API, safety boundaries
  and optional-app behavior remain. No dependency is unused enough to remove;
  no apt purge/autoremove or replacement runtime was introduced.
- Fresh installs no longer create `.pay/w` or `.pay/acik`; old metadata is not
  read/imported/deleted/repaired. Reserved path guards remain; the WebDAV unit
  permits an absent legacy directory while blocking one that exists. Files
  `/api/paylas` GET/HEAD/POST and `/api/paylas/kaldir` POST return 410 behind
  the existing gates; `/api/state` drops its misleading `share` summary.
- Corrected launcher/input-template/reset text, current docs and version links.
  Installer always verifies built-in Files. Portable packaging now explicitly
  excludes Python caches. All 45 runtime files still have active consumers;
  historical DD/designs/reviews and `versiyon/` were not rewritten or deleted.
- Local: 157 Bats cases (154 pass, three macOS timeout skips), 108 Python tests
  (106 pass, two native RAR skips), four browser suites, JS/bash syntax, core
  ShellCheck and diff checks pass. Initial failures were outdated text/shape
  assertions and a test issuing duplicate Host/header values; corrected the
  tests without weakening production gates. The pre-existing wireguard.command
  trap callback ShellCheck informational warning remains outside core checks.
- Root/Data-app/Desktop portable files and repeated export are byte-identical.
  Embedded SHA256: a2415a9aa05a1d37306926f4d90a640f88e4da997598438b7693148cce5292c4.
  Inspected the full archive: exactly 45 source-identical runtime files, no
  private input, docs, tests, caches or workstation metadata.
- Deployed through the portable launcher only, scratch SSH_HOST=nrm and blank
  LOCAL_DOMAIN, h full-upgrade/E confirm. Debian 13 stages 0–7 passed, no package
  changes, reset or reboot; permission sweep changed zero entries. Files, root
  panel and WebDAV restarted for changed code/unit; qBittorrent did not restart.
  Eight services active, no failed units/pending settings; firewall, DNS, Caddy
  and systemd unit checks pass. Installed code/assets equal portable sources.
- On native Debian all 108 Python tests pass as master-downloads, including real
  unrar and the existing upstream fixtures. Separate transient systemd sandbox
  probes verify missing `.pay` is accepted and existing `.pay`/trash contents
  remain inaccessible/unchanged. Live retired API/gates pass. Re-running
  `master-modul yerlesik` changes neither worker InvocationID nor registry hash.
- Live browser: seven widths × two themes, dock/dialog cancel/keyboard/routes,
  all non-GET/HEAD requests blocked, zero writes/CSP/JS errors. Local and live
  screenshots visually inspected. Share registry stays
  664fae636cb8e04388a82739974d725dd7bcbae049b213007812b29c00700f38;
  current settings stay 2c8d8303d7ae4c23d03908996493cdfeeb21b22256fa37d66c105abef243b791;
  qBittorrent profile stays c6f4f84a250237f3b64d21c5d03aacb21ba5f3e909889ac34b8438f3cf417048,
  PID/InvocationID 340708/c3a224de978a48dc8c6969043a79cbff. Both WG config hashes
  and old `.pay/acik` contents, mode/owner and mtime remain unchanged.
- Scratch/recoverable v144 export/live screenshots: `/tmp/master-stack-v145.ZynQVN/`.
  Native test copy: `/tmp/master-stack-v145-native.r3S2hJ/` on nrm. Only the two
  superseded v144 portable copies were replaced in the repo; Git and scratch
  retain them. No user data removed. No clean Ubuntu/full fresh-install/reboot
  acceptance claim. Operator input untouched; no commit or push requested/done.

**2026-09-28 — cleanup phases 1–2, source only (based on v2-144):**
- Approved first pass: reconcile current documentation/rules and remove dead
  frontend code/styles, without changing live service behaviour. No nrm access,
  package/dependency changes, deployment, export, version bump, commit or push.
  Existing v144 portable files still contain the previously released sources.
- Corrected active README/CLAUDE/rules/OKUBENI, architecture, contract and
  clean-install checklist: no automatic WireGuard backup/restore, built-in
  Files/WebDAV/archive tools, current paths and Caddy routing, mutable Settings,
  firewall overrides, bounded refresh recovery and contextual Files dock.
  Historical DD/CHANGELOG entries, archived reviews/designs and `versiyon/`
  remain untouched. The private operator input was not read.
- Removed unused helpers, constant built-in feature gates, retired shared-account
  UI and unreachable optional-app dependency queue. Removed obsolete Overview,
  module-card/progress, selection-toolbar and read-only Settings CSS. The four
  changed production assets shrink by 18,353 bytes (8.8% of those assets).
  Preserved current dock/sharing, qBittorrent first-login reveal, route aliases,
  backend/API compatibility, safety checks and every installed dependency.
- Added browser regression checks for qBittorrent opt-in secrets, 30-second
  expiry, hidden-tab/card-close/navigation clearing, no browser storage and
  non-revealable stored passwords. The browser clock is realigned with fixture
  timestamps after the expiry probe. Files copy geometry now waits for a visible
  address before measuring; an initial immediate hidden-view read was flaky.
- Local verification: 155 Bats cases (152 passed, 3 skipped: no `timeout`),
  108 Python tests (106 passed, 2 native-RAR skips), four browser suites,
  JS/bash syntax, core installer ShellCheck and `git diff --check` passed.
  macOS lacks `sha256sum`: baseline tests 132–137 failed before edits; a temporary
  test-only adapter to `/usr/bin/shasum -a 256` was used, never shipped.
  Unchanged `wireguard.command` has the same pre-existing ShellCheck SC2329
  informational warning at its trap callback on HEAD and working tree.
- Deferred: retire `.pay`/old share endpoints only with their migration and
  permission callers; review remaining launcher terminology; package and test
  a new release after the next approved cleanup stage. No fresh Linux install,
  reboot, native-RAR or live-server acceptance is claimed by this pass.

**2026-09-28 — v2-144, approved Files icon dock B (DD-170 follow-up):**
- Implemented the second visual alternative: compact floating surface, count
  left/dismiss right above six equal icon-over-label actions. Ineligible actions
  retain disabled slots, trash uses red ink without a filled button, mobile is
  3×2. No new dependencies or backend/API/archive semantics changes.
- Local: 108 Python tests pass (two native RAR skips), 155 Bats cases pass
  (three macOS timeout skips), all four browser suites pass; JS/bash syntax,
  ShellCheck and whitespace checks pass. Files coverage now checks eligibility
  for ordinary files, RAR volumes, folders and multiple selections, keyboard
  focus/activation, action-dialog routing, download links excluding folders,
  equal cell widths/icon-label geometry and eight widths in both themes.
  Initial download assertion used a route that Chromium downloads bypassed;
  changed the fixture to capture generated download anchors, not real transfers.
- Deployed only through the exported portable launcher using a scratch
  SSH_HOST=nrm/blank LOCAL_DOMAIN, h full-upgrade and E confirmation. Stages
  0–7 passed; no packages/reset/reboot. Normal permission sweep repaired one
  entry. Root/app/repeated exports are identical; embedded archive SHA256:
  4a82d1706db2fdec9771488d2cda90f03ae19d6424f022ed39568a94dc85283a.
- Installed JS/CSS/backend hashes match source and /api/state reports v144.
  Read-only live browser passed seven widths × two themes, dialog open/cancel,
  keyboard and dock visibility checks, blocking all non-GET/HEAD requests:
  zero writes, CSP or JS errors. Local and live screenshots visually inspected.
  Eight services active, zero failed units/pending settings; firewall --check,
  dnsmasq --test, Caddy and systemd unit validation pass.
- Pre/post WebDAV registry SHA256 remains
  664fae636cb8e04388a82739974d725dd7bcbae049b213007812b29c00700f38;
  settings remains 7d401335dcfe735657dde6b3d9767876247dcbf9ec3e91357d21d2020fa75e30;
  qBittorrent profile remains c6f4f84a250237f3b64d21c5d03aacb21ba5f3e909889ac34b8438f3cf417048.
  qBittorrent PID/InvocationID 340708/c3a224de978a48dc8c6969043a79cbff unchanged
  from this turn's preflight (operator changed it since the v143 record).
- No user data removed. Exporter replaced the two v143 portable copies; both
  are recoverable in /tmp/konsol-icon-dock.WNHmtj alongside the scratch input,
  repeated export, read-only live test and screenshots. No fresh Ubuntu/reboot
  acceptance claim. No commit or push requested/performed.

**2026-09-28 — v2-143, Files dock and automatic archive opener (DD-170):**
- Selected-item actions now appear in a bottom dock, keeping breadcrumbs/search
  in place. Selection filtering, leaving Files, clearing selection and navigation
  update/hide it; responsive controls and bottom spacing prevent clipping. Toasts
  sit above the dock. The compact trash and inline share controls are preserved.
- Archive dialog now has result name, directory picker and name-collision policy
  only. Default downloads comes from DOWNLOADS_SUBDIR -> unit --downloads-dir ->
  GET /api/state.downloads, independently of current source/qBittorrent save path.
  Picker uses dirs-only API, rejects failed/stale reads, supports root/up/subfolder,
  retains destination on cancel and draft on submit failure. Generic labels:
  Arşiv açıcı / Arşiv oluştur; creation automatically appends .zip.
- UI omits nested/layers; worker defaults to recursive/MAX_LAYERS. At five-layer
  ceiling the automatic job fails without publication (legacy explicit options
  remain compatible). RAR volume discovery and ZIP/RAR recursion stay in the
  existing bounded worker. Originals and nested archives remain; per-archive
  subfolders avoid flattening/overwrite. Job statistics hidden in UI, not removed
  from API. Shared 2 GiB/10,000-entry/900-second caps are unchanged.
- Local 108 Python tests pass (two native RAR skips), 155 Bats pass (three macOS
  timeout skips), four browser suites pass. Updated obsolete structural guards
  for search's dock refresh and retired-Unpackerr versus built-in action label.
  Initial Bats environment omitted /sbin (sha256sum); full rerun with normal
  system paths passes. Parallel preview browser starts timed out; sequential
  suites pass. Files dock tested at eight widths/both themes, archive picker at
  four widths/long names/failed reads and saves. JS/bash syntax, shellcheck -x,
  whitespace checks pass. Screenshots visually inspected.
- Portable-only nrm update: scratch SSH_HOST=nrm, blank LOCAL_DOMAIN, h full
  upgrade and E confirm. Initial attempt stopped before confirmation to include
  toast positioning fix, final stages 0–7 pass. No packages/reset/reboot. Normal
  permissions pass repaired one entry; Files service restarted. Export root/app
  and repeat output match; archive SHA256:
  84e02095ad3765130cf91a7a6f2e08b73f39f42b7124ac87b7f21e4a36c6a140.
  Installed JS/CSS/backend hashes match local; file state reports v143/downloads.
- Native Linux: 27 ZIP/RAR tests pass as master-downloads, including actual
  unrar compressed/solid/old/new multipart/unsafe/encrypted rejection and mixed
  recursion. Existing upstream fixtures reused read-only. Live production browser
  creates ZIP and automatically expands four layers through the real service;
  exact payload and original source SHA256 match. It tests picker/default target,
  invalid-name error recovery, shares/settings/navigation and five widths.
  Initial live test's mobile navigation race was fixed by awaiting hash/menu
  completion; repeat passes. No optional application lifecycle was enabled.
- Both owned /srv/archive-test-* trees were verified then removed permanently;
  ordinary archive job audit history retained. No user archives were extracted,
  moved or deleted. Final eight services active, no failed units/pending settings;
  firewall --check, dnsmasq --test, Caddy and systemd unit validation pass.
  WebDAV/settings/qBittorrent hashes remain exactly as v142 below; qBittorrent
  PID/InvocationID still 320350/08757c3722ff491593e33fa6fa3ad9dd.
- Scratch inputs/helpers and recoverable v142 exports:
  `/tmp/konsol-archive-dock.BjrfwF/`; native helpers:
  `/tmp/konsol-archive-v143.wFowc1/`. Final live screenshots:
  `/var/folders/hz/s9hhjptx181_cspndbzdz7c80000gn/T/konsol-v130-live-aVBybE/`.
  Operator input, frozen versions and unrelated dirty changes preserved. No
  commit/push; no fresh Ubuntu/reboot acceptance claim.

**2026-09-28 — v2-142, compact trash and inline share controls (DD-169):**
- User supplied overflow/sparse-layout screenshots. Move-to-trash now shows
  a short question, filename (one line, full title tooltip) or item count and
  Cancel/Move. No path/size/explanation rows; shared confirmation content is
  bounded. Permanent purge warnings and typed empty-trash confirmation remain.
- Shares use aligned folder/URL, username, access, expiry, state and action
  columns, folding to labeled cells on narrower screens. Native selects save
  immediately; RW still confirms permanent-write/delete permission. Durations
  1/7/30 days begin now; unlimited and current absolute expiry are explicit.
  Manage edits only folder/username/password; new-share defaults are still RO/7d.
- Existing `kaydet` endpoint accepts partial existing-share bodies. Under the
  existing locks, omitted fields retain current registry values; list-only
  edits preserve folder identity rather than rebinding missing/replaced roots.
  Explicit RW requires acknowledgement; unrelated edits of existing RW do not.
  Block conflicting list controls during writes and suppress stale/focused-select
  polling redraws. Keep restart/rollback, stopped-service and expiry behavior.
- Local: 106 Python tests (two native RAR skips), 155 Bats cases (three expected
  macOS skips), all four UI suites, JS/bash syntax, ShellCheck and whitespace
  checks pass. The first Bats run caught an obsolete structural keep-duration
  expression; the equivalent keep/null conversion now lives in the inline
  selector. Full rerun passed without changing its guard. Native Debian: 22
  WebDAV fixture tests pass in a private network namespace.
- Portable-only nrm update: scratch SSH_HOST=nrm, blank LOCAL_DOMAIN,
  full-upgrade h, confirmation E; stages 0–7 passed. No packages/reset/reboot.
  Installer's normal permissions pass repaired one entry. WebDAV restarted for
  its updated helper. Installed Python/JS/CSS hashes match local; repeated root/
  app exports match with archive SHA256:
  98811e88adc37e4ba1102ff3344208cf9973b405a6d9cdeb77c6783a75acd1e2.
- Live production Caddy/API/worker test created only a random owned share/tree:
  acknowledge RW, real PUT/GET, RO write/delete rejection, all durations,
  account-only edit retaining hash/access/expiry, paused expiry edit and replaced
  root failing closed. Cleanup revoked its account and deleted only its test
  files. Original share registry is byte-identical. Read-only live browser checks
  pass eight widths/both themes plus compact confirmation/account editor, with
  zero writes or JS errors. Existing trash was never mutated by UI checks.
- Final eight services active, no failed units/pending settings; firewall,
  dnsmasq, Caddy and systemd unit validation pass. Before/after hashes unchanged:
  WebDAV 664fae636cb8e04388a82739974d725dd7bcbae049b213007812b29c00700f38;
  settings 7d401335dcfe735657dde6b3d9767876247dcbf9ec3e91357d21d2020fa75e30;
  qBittorrent 35b23611c5c2680ede1cd8211b746788d5f15c46aff4dd4c3aaf2f4b76340502.
  Real qBittorrent PID/InvocationID remain 320350/08757c3722ff491593e33fa6fa3ad9dd.
- Scratch inputs, live helpers/screenshots and recoverable v141 exports are in
  `/tmp/konsol-shares-layout.Qb6T2N/`; server test helpers (not account secrets)
  in `/tmp/konsol-share-controls.QD2iPw/`. Local preview/launcher/test processes
  closed. Operator input, frozen versions and prior dirty work preserved;
  no commit/push and no fresh Ubuntu/reboot acceptance.

**2026-09-28 — v2-141, eight-character service passwords (DD-168):**
- User requested qBittorrent/WebDAV minimum 12 -> 8 if supported. The old
  minimum was a Konsol policy: change both browser inputs/messages and backend
  validators. Keep maximum 256, character restrictions, password hashes,
  blank-edit preservation and the long random WebDAV generator. No real account
  password is changed. Historical design demos/retired policies remain historical.
- Local: 102 Python tests (two native RAR skips), 155 Bats cases (three macOS
  timeout skips), settings/files browser suites, JS/bash syntax, ShellCheck and
  diff whitespace checks pass. Boundaries include seven rejected/eight accepted,
  existing upper/control-character restrictions and real WebDAV GET/PROPFIND
  authentication/old-password rejection/read-only write denial.
- Portable nrm update completed stages 0–7 using scratch SSH_HOST=nrm and blank
  LOCAL_DOMAIN, full-upgrade h and confirmation E. No package changes, reset or
  reboot. The normal installer corrected one download entry's ownership/mode.
  WebDAV was restarted because its imported validator changed; the real
  qBittorrent PID/InvocationID stayed 55839/8ffc2db03d9d4ffba9e01e79d648347f.
- Existing WebDAV registry, panel settings and qBittorrent configuration SHA256
  remain identical to pre-install values. Installed Python/JS hashes match local
  sources; eight services are active, no failed units or pending settings;
  firewall/Caddy/dnsmasq checks pass. Live browser forms enforce 8 and reject 7
  with zero mutation requests/JS errors. Eighteen isolated Debian WebDAV tests pass.
- Disposable native qBittorrent 5.1.0 test passes: seven characters rejected,
  eight-character login, persistence after process restart, old credentials
  rejected, blank password retained, failed-commit rollback and stopped-service
  preservation. Its real firewall/DNS checks also pass, in a private network
  namespace and temporary profile, never the installed services/configuration.
- Root/app/repeated export match; embedded archive SHA256:
  d20de3bef708357d4a0adbc9719af530bd51d9fc48cd3d145fcee26fd2fdf305.
  Scratch input, read-only browser helper and recoverable v140 installer copies:
  `/tmp/konsol-password.WIRBnD/`. Only tests were copied separately to the server;
  runtime delivery used the portable installer. Operator input and frozen versions
  untouched; prior dirty work preserved; no commit/push. No fresh Ubuntu/reboot claim.

**2026-09-28 — v2-140, WireGuard network settings (DD-167):**
- User requested default DNS and local-access editing from the network-card
  refresh action. Replace that destructive shortcut with a settings dialog;
  keep key regeneration separate with typed `onayla`. Save is immediate and
  preserves existing profiles/keys/ports/addresses/labels and WG running state.
  Default DNS only preselects the new-peer form; per-peer DNS editing is unchanged.
  Local access retains its narrow qBittorrent-only meaning, not Konsol/SSH/WebDAV.
- Add gated `POST /api/wg/nets/<iface>/ayarlar` and locked `net-settings` helper.
  Validate DNS IPs, compare exact registry-row SHA256 revision under the install
  lock, reject pending Settings transactions, invalidate the firewall read cache.
  Close listener before tightening policy; open policy before listener. Roll back
  ordinary failures/signals, with explicit incomplete-rollback errors. No durable
  power-loss/SIGKILL recovery claim or general reconcile loop.
- Live stress testing exposed systemd's firewall 12/300s and Caddy 5/600s start
  budgets. Explicit local changes now reset only these two counters, retaining
  automatic restart-loop limits. A never-loaded Caddy instance rejects reset;
  ignore that case and still strictly check actual enable/start. DNS-only changes
  invoke no service actions. Unit tests cover both cases and rollback.
- Native Debian integration uses its own temporary WG network/peer and Linux
  client namespace. Client UDP socket stays in its birth host namespace; actual
  encrypted traffic reaches the selected WG interface and real input firewall.
  OFF blocks qBittorrent; ON returns HTTP 200. Fourteen rapid additional toggles
  pass without rate-limit lockout. Stale revisions return 409; firewall view
  baseline updates; server config/profile and WG InvocationID stay unchanged.
  Editing a stopped network does not start WG/Caddy; explicit start restores
  access. Allow handshake re-establishment after that intentional restart (the
  first test's immediate 3-second probe was too short). Owned test network,
  peer and namespace are removed; original registry/configs match byte-for-byte.
- Local: 155 Bats cases (three expected macOS timeout skips), 99 Python tests
  (two native RAR skips) and all four browser fixture suites pass. WireGuard
  checks save/failure/draft retention, new-peer DNS default, stopped networks,
  separate regeneration confirmation, four widths/dark/production CSP.
- Portable-only nrm update/reruns: scratch SSH_HOST=nrm, blank LOCAL_DOMAIN,
  full-upgrade h, confirmation E. All three completed installers pass stages 0–7;
  no package changes, reset or reboot. One intermediate browser stress attempt
  exhausted the pre-fix start budget; scratch network was removed and project
  firewall explicitly reset/restarted before the corrected portable reruns.
- Root/app/repeat exports match. Embedded archive SHA256:
  9d8cca47cf9aedf21c357d5b1346c5460ba26b45c396ddf8fa7f70317dac59d5.
  Installed helper/backend/JS/CSS hashes equal local sources. Scratch input,
  test helpers/logs/screenshots and recoverable v139 exports:
  `/tmp/konsol-wg-settings.uxzX1D/`; server helper (no secrets) in
  `/tmp/konsol-wg-settings-live.90jN4B/`. Prior dirty work preserved;
  no commit/push, operator input/frozen versions/Desktop untouched.
- Final live Chromium Save ON/OFF, reopen persistence, new-peer DNS preselection
  and 1440/390/320px layouts pass, with zero JS/CSP errors. Browser-owned network
  removed. Baseline `before.txt` equals final hashes for original registry,
  wg0/wg1 configs, existing peer, WebDAV/settings/qBittorrent config and both
  WebDAV/qBittorrent PIDs/InvocationIDs. Eight services active; no failed units,
  pending settings or test namespaces. Firewall/Caddy/dnsmasq/unit checks pass.
  Launcher/browser sessions and task-owned local preview are closed.
  No fresh Ubuntu or reboot acceptance; committed history remains unchanged.

**2026-09-28 — v2-139, multipart/nested RAR in Files (DD-166):**
- User requested unrar and file-manager support for multipart/nested RAR.
  Keep the existing ZIP API/job manager; `unzip` accepts ZIP/RAR3/RAR5,
  solid/old-style/new-style volumes, later-part selection and mixed nesting.
  Sources/inner volumes are retained. Job limits remain 2 GiB/10,000 entries/
  five layers/900 seconds; missing/unsafe/encrypted/corrupt archives fail closed.
- Add distro `unrar` and `python3-rarfile`, with a managed signed non-free
  Debian or universe/multiverse Ubuntu apt source only if candidates are missing.
  RAR metadata is parsed in a resource-limited process. Snapshot validated source
  volumes privately; stream `unrar p` output through parent-owned safe writes,
  size/CRC checks, cancellation/time/output caps and atomic publication.
- Native tests caught unnamed metadata headers and Windows attribute bits
  overlapping Unix device types; both fixed and covered by real fixtures.
  The UI offers “Arşivi aç”; long archive paths now wrap in the dialog and
  breadcrumbs without forcing the Files grid offscreen. Share copy placement,
  account/permission flows and ZIP creation are preserved.
- Local: 94 Python tests (two explicit Linux/optional-fixture skips), 149 Bats
  cases (three expected macOS timeout skips), all three browser suites pass.
  Bash/ShellCheck/JS syntax and diff whitespace pass. Browser fixture coverage
  includes RAR/.r00/.part01 selection, submission and long-path dialogs at four widths.
- Debian 13 nrm: 25 ZIP/RAR tests pass as the unprivileged master-downloads user,
  against installed code and real distro unrar 1:7.1.8-1 / python3-rarfile 4.2-3.
  Test genuine RAR3/RAR5, solid, old/new multipart, Unicode/BLAKE2, encrypted/link/
  duplicate rejection, missing final volume, RAR→ZIP→RAR and multipart RAR inside
  RAR (reverse member order, extracted once). Upstream test fixtures are scratch
  only, pinned to markokr/rarfile d2f7df6fc843dae356fd6b0a85971dc36fd6e757.
- Portable launcher deployed/re-ran with scratch SSH_HOST=nrm, blank domain,
  full-upgrade h, confirmation E. All completed installs passed stages 0–7.
  One stale-launcher attempt was interrupted at the pre-install prompt, before
  confirmation. Only the two RAR packages were added; non-free source is managed
  separately. Final UI-only rerun left Files PID 91508 unchanged. No reset/reboot.
- Real browser selected `rg-42386.rar` in
  `/srv/downloads/Acronis.True.Image.Build.42386.Multilingual.Bootable.iSO-rG`.
  Job 52254606ec18176e5245dd41 opened all 17 volumes in 16 seconds, output
  `rg-42386-acilan-test/rg-42386.iso` (881,197,056 bytes, CRC32 3452295790).
  SHA256 e892719cb1c71b42fe33600d0b29c8bc6a1991fa1762cf5451d4cbb953b273bc.
  All 17 source SHA256 values match before/after. This actual archive contains
  an ISO, not an inner RAR; nesting was verified separately above. No extracted
  software was executed. Output is retained for the user, staging contains only jobs.json.
- Live dialog verified at 1440/390/320 px. The scratch browser's asynchronous
  wait assertion initially returned while the job was running; no resubmission.
  A read-only follow-up waited for the terminal UI row and verified result
  navigation/ISO listing, with zero writes or JS/CSP errors. Source/runtime hashes match.
- WebDAV registry, confirmed settings and qBittorrent profile hashes match the
  v138 baseline below; WebDAV PID 70392 and qBittorrent PID 55839/invocations
  unchanged. Eight checked services active, no failed units/pending settings;
  firewall --check, dnsmasq and Caddy validation pass. Ubuntu repo selection is
  unit tested, not a new fresh Ubuntu/live/reboot acceptance.
- Root/app/repeat exports identical. Embedded archive SHA256:
  9e4b7f62887798f368f6b4967751b37585b6ecd75a2c0c2302999d26b8f542df.
  Scratch sources, screenshots, test logs, input and recoverable v138 packages:
  `/tmp/konsol-rar.uHiKcV/`; Linux fixtures `/tmp/konsol-rar-test.uZ431f/`.
  Preview and launcher/browser sessions closed. Prior dirty work preserved;
  no commit/push, operator input/frozen versions/Desktop untouched.

**2026-09-28 — v2-138, share address copy placement and Infuse diagnosis:**
- User confirmed Infuse on their phone now browses/plays the existing media
  share after re-entering the path, then reported a successful transfer test.
  Earlier passive WebDAV metadata inspection saw authenticated PROPFIND to a
  nonexistent one-character child path returning 404. The exact character and
  its origin were not established; do not blame the panel or iOS without proof.
- Read-only live v137 and v138 audits compared API URL, textContent, innerText,
  Range selection, fallback textarea value and actual isolated Chromium
  clipboard. All are identical (53 printable ASCII characters, final slash),
  desktop and mobile emulation. Native iPhone clipboard was not instrumented;
  WebKit was not installed. No password was read, reset or logged.
- On request, move copy beside the URL in both the Shares list and folder
  details, using a shared compact address group with 6 px spacing, wrapping and
  a non-shrinking button. Remove the distant list action. URL generation,
  clipboard implementation, account APIs and WebDAV backend are unchanged.
- Files fixtures check exact copied text and geometry in both places at five
  widths; original forms, ZIP/navigation, Trash and dark/CSP coverage passes.
  Files, Settings and Model A browser suites pass; all Bats tests pass apart
  from the three expected macOS timeout skips. Bash/ShellCheck/JS syntax and
  whitespace checks pass. Existing WebDAV Python tests passed during the prior
  diagnostic (16 tests); no backend changed in this UI-only release.
- Portable nrm update exit 0, all seven stages passed. Scratch SSH_HOST=nrm,
  blank LOCAL_DOMAIN, full-upgrade h, confirmation E; no package changes or
  reset/reboot. Installer repaired one data-tree permission/ownership entry
  and reapplied the existing WireGuard network (actual interface wg0, one peer).
  Live firewall --check, dnsmasq and Caddy validation pass; no failed units or
  pending settings. An initial inspection used wrong settings/unit names and
  the wrong firewall CLI spelling; corrected checks above are authoritative.
- Before/after WebDAV registry, settings and qBittorrent profile hashes match.
  WebDAV PID 70392/invocation 3f2317e98a3e4b8892c0dd7f21bb7714 and qBittorrent
  PID 55839/invocation 8ffc2db03d9d4ffba9e01e79d648347f are unchanged.
  WebDAV hash: 664fae636cb8e04388a82739974d725dd7bcbae049b213007812b29c00700f38.
- Postdeploy read-only live audit passes list geometry at five widths,
  desktop/mobile actual clipboard, selected URL and served-source hashes;
  zero JS errors or mutation requests. This is in-place Debian acceptance,
  not a new clean Ubuntu/reboot test. Preview/launcher/browser sessions closed.
- Root/app/repeat exports identical. Embedded archive SHA256:
  888d8839bac562e488b1df761304bcf61ce9b649787e7ea5d5d26a7a5707d12f.
  Scratch audit/screenshots/input and recoverable v137 root/app packages:
  /tmp/share-copy-audit.67r26b/. Existing dirty v130–v137 work preserved;
  no commit/push, operator input/frozen versions/Desktop untouched.

**2026-09-27 — v2-137, Trash column/name layout:**
- User reported the Trash page collapsing filenames. Live inspection confirmed
  the later `.fs-t .tr` five-column rule overrode `.trash-t .tr`: the filename
  was placed in a 26 px selection column (47-character name, 876 px row height).
  Previous Files fixtures only exercised empty Trash, so they missed it.
- Add scoped `.fs-t.trash-t` rules in dosyalar.css: four desktop columns,
  wrap full names/origin paths, min-width guards, aligned headers/actions,
  dark-mode Restore text. At <=1100 px the name spans both columns, metadata
  stays visible and actions move below it. No runtime JS/API/backend changes.
- Files UI fixtures now cover empty/populated Trash, short/Turkish/255-character
  unbroken names, long paths, seven widths including both breakpoint edges,
  light/dark and production CSP. Assert bounds/alignment/overlap and mocked
  restore, purge cancel/confirm and typed empty confirmation. Wait two render
  frames after resizing; an initial live geometry assertion was transient,
  a rerun and the frame-synchronized final test both pass. All live mutation
  requests are blocked; no real Trash item is restored/purged/emptied.
- Local: 144 Bats passes/3 macOS timeout skips; Files, Settings and Model A
  browser suites pass. Bash/ShellCheck/JS syntax/whitespace checks pass.
  Python unit suites were not rerun for this CSS-only change. Desktop/mobile
  fixture and live screenshots inspected; long text stays inside its cells.
- Portable nrm update exit 0/all stages passed. Scratch SSH_HOST=nrm,
  LOCAL_DOMAIN blank; full-upgrade default no, confirmation E. No package
  additions/upgrades/removals, host reset or reboot. Installer repaired two
  data-tree ownership/permission entries and reapplied the existing WireGuard
  network (one peer); qBittorrent's PID/invocation/profile hash and confirmed
  settings hash unchanged. WebDAV registry changed during the predeployment
  interval (mtime 22:37:24 +02, deployment started 22:38:18), with one RO share;
  do not claim its initial-turn hash was preserved or revert this operator state.
- Live v137 CSS matches source; seven widths/both themes, zero JS/CSP errors
  or mutation requests. Trash API inventory hash identical before/after
  deployment: `8fffbceb8c5c33fe0953889d69ae137b64a12dce7d2d4c14a1408602db4ed642`
  (one item). Filename column is 664 px at 1440 px and 254 px at 320 px.
  Eight core/app services active, no failed units/pending transaction;
  firewall, Caddy, dnsmasq and systemd validation pass. In-place Debian only,
  not fresh Ubuntu/reboot acceptance.
- Scratch screenshots/scripts and recoverable previous v136 root/app copies:
  `/tmp/konsol-v137.QxsVK1/`. Root/app/repeat exports identical; embedded runtime
  matches sources. Archive SHA256:
  `8656dac3dbcc3c8e9ae3078e0f1edbe3bbaa9cd55358f57d366278746585d447`.
  Existing dirty v130–v136 work retained; no commit/push. Operator input file,
  frozen versions and Desktop untouched.

**2026-09-27 — v2-136, qBittorrent field alignment:**
- User confirmed their password change works and requested layout alignment.
  Read-only live inspection found the repeat-password input 12 px lower/taller
  than its neighbour and an extra 18 px body inset beneath card headings.
- Scoped panel.css rules align labels/inputs/Save, equalize control heights,
  remove the double inset and place the boxed download path beside its action
  on desktop. Mobile stacks controls; long paths wrap; dark-mode folder action
  stays legible. No account API, worker, validation or save-flow changes.
- Local: 144 Bats passes/3 macOS timeout skips; Settings, Model A and Files
  browser suites pass. Settings geometry now covers five widths in both themes
  and very long paths; existing single-save/validation/failure/retry checks pass.
  Bash/ShellCheck/JS syntax and whitespace checks pass. Python unit suites were
  not rerun for this CSS-only change (84 passed in v135).
- Portable nrm update exit 0/all stages passed. Scratch SSH_HOST=nrm and blank
  LOCAL_DOMAIN; full-upgrade default no, confirmation E. No packages upgraded,
  added or removed; no host reset/reboot. Installer repaired one downloads
  ownership/permission entry. qBittorrent profile, settings and WebDAV hashes
  are unchanged; qBittorrent PID/invocation unchanged. User's live account was
  never submitted/revealed by these tests. WireGuard is now installed with one
  network/peer (operator change since v135); installer retained/reapplied it.
- Live read-only browser checks pass at 1440/1024/736/390/320 px in light/dark:
  headings/input/action alignment, equal heights, responsive stacking, no
  overflow, no JS/CSP errors, zero mutation requests. Served v136 CSS matches
  source. Desktop/mobile screenshots inspected. Eight core/app services active,
  zero failed units/no pending settings; firewall, Caddy, dnsmasq and systemd
  validation pass. This is an in-place Debian update, not fresh Ubuntu or
  reboot acceptance. Local preview and portable launcher sessions closed.
- Scratch scripts/screenshots and preserved untracked v135 root/app copies:
  `/tmp/konsol-v136.yytewk/`. Root/app/repeat exports identical and embedded
  runtime sources match. Archive SHA256:
  `913f5d62dcff265fb7385482b4a09a2d768cd8b408e40029f29d660d4d8693f1`.
  Existing dirty v130–v135 work retained; no commit/push. Operator input file,
  frozen versions and Desktop untouched.

**2026-09-27 — v2-135, one-click qBittorrent account save (DD-165):**
- User approved simplifying the confusing staged account flow. Read-only
  diagnosis found admin/temporary login unchanged, no account apply POST, and
  working qBittorrent/API connectivity. Staging was being mistaken for saving.
- Account Save now sends username/password alone, commits immediately, reports
  explicit success/failure, disables duplicate submission and clears passwords.
  Other DNS/firewall/folder drafts remain unapplied and use the refreshed revision.
  Fix the HTML username pattern's unescaped hyphen. Explain temporary-password
  rotation; blank preserves an existing stored hash. Hide the empty draft footer
  on the account page. No password persistence in the browser or worker metadata.
- Worker classifies account-only requests (no save path or other sections),
  retaining validation/locks, stop/flush/snapshot/write/restart, stopped state and
  crash-safe rollback/commit markers. Folder/mixed/firewall/domain confirmation
  and DNS-only immediate Apply are unchanged. No new packages or network exposure.
- Local: 84 Python tests; 144 Bats passes/3 macOS timeout skips; Settings,
  Model A and Files browser suites pass. Tests cover single Save, validation,
  mismatch, duplicate blocking, username-only/password-only, failure/retry,
  reload, unrelated drafts and revision refresh; no browser regex/CSP errors.
  Bash/ShellCheck/JS syntax and whitespace checks pass; desktop/mobile inspected.
- Portable nrm update exit 0/all stages passed, using scratch SSH_HOST=nrm and
  blank LOCAL_DOMAIN, full-upgrade default no and confirmation E. No package
  changes, host reset or reboot. Installer repaired one downloads permission/
  ownership entry. qBittorrent's process/invocation and profile hash unchanged;
  WebDAV registry hash unchanged. Existing optional qBittorrent retained, WG absent.
- On nrm, 40 settings unit tests and real isolated Linux tests pass: actual
  qBittorrent new login/old login rejection, restart persistence, stored-password
  preservation, failed-commit rollback and stopped-state retention. The fixture
  uses a private network namespace/profile and never controls production services.
  Real IPv4/IPv6 firewall and dnsmasq regressions and systemd guard/worker pass.
- Deployed browser check verifies served asset equality, one account POST, real
  API/systemd stale-revision rejection before mutation (forced stale revision,
  disposable input only), explicit error/no false success, secret clearing and
  unchanged account/config/revision. Missing-header gate returns 403. Three
  widths/light/dark pass. Successful credential changes were tested in the
  isolated real qBittorrent fixture, not by changing the operator's live account.
- Caddy/dnsmasq/firewall/systemd verify pass; eight core/app services active,
  zero failed units/no live pending transaction. User should reload the panel
  and set their preferred account with Hesabı kaydet; no password was chosen
  for them. In-place Debian verification, not fresh Ubuntu/reboot acceptance.
- Scratch scripts/screenshots and preserved v134 root/app copies:
  `/tmp/konsol-v135.3gfPpL/`. Root/app/repeat v135 exports identical, embedded
  runtime tree matches sources. Archive SHA256:
  `979b3a833f86a341428c36844cd72838e9024095063be0d55019fe99fe7d4e06`.
  Existing dirty v130–v134 work retained; no commit/push. Operator inputs,
  frozen versions and Desktop untouched.

**2026-09-27 — v2-134, incoming-network firewall tabs (DD-164):**
- User approved the proposed categorization. Implemented Tailscale (default),
  Internet, conditional WireGuard with per-interface selection, and protected
  loopback. Technical rules stays an all-network read-only view, including
  INPUT/FORWARD/NAT, full specs/order/counters/ownership. Incoming scope replaces
  the redundant table column; service rows retain interface/family and descriptions.
- Socket binding status is separate from permission: matching network, loopback
  only, another address, no listener and unknown/unreadable. Backend read-only
  metadata classifies actual addresses/zones, fixes ss IPv6 `]%tailscale0`
  formatting and reuses known service names across scopes. No worker/policy,
  write-API, dependency, bind address, deadline or privilege changes.
- Preserve drafts across tabs, keyboard focus/navigation, edit/remove/on-off,
  protected loopback, confirmation and server rollback. DNS-only immediate
  Apply remains. WireGuard public UDP endpoints stay in Internet; installed
  with no available networks has an explicit empty state. Explicit Refresh,
  not background polling, reads external changes.
- Local: 77 Python tests pass, including six new firewall-view tests; Bats
  147 total (144 pass/3 macOS timeout skips). Settings/Model A/Files browser
  suites pass with production CSP. New fixtures cover absent/empty/multiple
  VPN networks, per-interface rule defaults, bindings versus permissions,
  draft retention and nested keyboard tabs. Five widths/light/dark pass.
  Fixed a wrapper min-width overflow and firewall button theme contrast found
  during visual checks. Bash/ShellCheck/JS syntax and whitespace checks pass.
- Portable nrm update used scratch SSH_HOST=nrm, blank LOCAL_DOMAIN,
  full-upgrade default no, confirmation E. Exit 0/all stages passed; no package
  upgrades/additions/removals, reset or reboot. Installer repaired one downloads
  ownership/permission entry. Installed optional apps remain absent. Six new
  backend unit tests pass on Debian Python against the portable runtime.
- Live browser audit passes: category rows match the API, every raw IPv4/IPv6
  rule specification/order matches the kernel, scoped IPv6 addresses are valid,
  loopback switches disabled, WireGuard absent as expected. Five widths and
  light/dark inspected; no browser JS/CSP errors. On owned tailnet-only TCP
  port 49429, both families pass draft-only/deny/confirm/reload/allow/manual
  rollback/60-second guard rollback, verified using fresh connections and
  actual kernel rules. Removed only the two owned test rules through the UI;
  complete normalized kernel rules (including foreign chains) and DNS choices
  match the starting state. No pending transaction remains. Screenshots/script/
  report are in the scratch directory. No actual WireGuard installation was
  needed: multi-network behavior is fixture/unit tested, not live VPN certified.
- Core services and guard active, zero failed units/recent service errors;
  firewall/Caddy/dnsmasq/systemd verify (--man=no) pass. Initial deployment
  preserved settings/WebDAV/ZIP file hashes; after the scoped test, semantic
  settings are restored (only transaction metadata changes).
- Scratch work and preserved untracked v133 root/app installers:
  `/tmp/konsol-v134-deploy.2PWIKt/`. Existing dirty v130–v133 work preserved;
  no commit/push. Operator input file, frozen versions and Desktop untouched.
- Final portable archive SHA256 (root/app/repeat exports identical; all 44
  embedded runtime files match source):
  `d0c0742a4ed63a4ce9009a4e466a4b07927199ac66923c05ef134ad2bd5f0d54`.
- Final theme contrast patch was re-exported and deployed through the portable
  launcher, with the same scratch inputs/defaults. Re-run exit 0; unchanged
  firewall, DNS, Caddy and panel backend were not restarted. Live source hashes
  match; missing API header still gets 403. WebDAV/ZIP hashes remain unchanged.
  Test responder PID 34826 was identified by its port, then terminated; no
  socket at 49429 or test rules/pending records remain. This is in-place Debian
  acceptance, not a fresh Ubuntu install, VPN data-plane or reboot certification.
- Final deployed read-only browser check passes both families, all categories,
  full raw-rule/API equality, and five widths in both themes with zero writes
  or JS/CSP errors. Final screenshots inspected; local preview stopped.

**2026-09-27 — v2-133, immediate Dnsmasq Apply deployed (DD-163):**
- User requested removal of the one-minute DNS confirmation. DNS-only Apply
  now validates/restarts/commits in one request, returning explicit committed
  state. UI clears its draft, refreshes and has no review dialog/countdown.
  Mixed firewall/qBittorrent drafts retain 60 s confirmation; local-domain
  changes retain 300 s/new-Host confirmation.
- Protect the panel's own DNS name before any mutation and disable its switch.
  Keep snapshots, revision/lock checks and guard recovery on failed/interrupted
  applies. The shared durable commit marker prevents rollback after a committed
  DNS write. Prior dirty v130–v132 work retained; no commit/push.
- Local: 71 Python tests pass; Bats 147 total (144 pass/3 missing-timeout macOS
  skips); Settings/Model A/Files browser suites pass. New checks cover single
  Apply, reload, failure/retry, protected panel, mixed confirmation, restart/
  commit failure and pre/post-commit crash recovery. Bash/ShellCheck/JS syntax,
  diff whitespace and post-export consistency pass.
- Portable nrm in-place update exit 0/all seven stages passed. Scratch inputs:
  SSH_HOST=nrm, LOCAL_DOMAIN blank; full-upgrade default no; confirmation E.
  No packages upgraded/added/removed, no reset/reboot. Installer repaired one
  downloads ownership/permission entry. Optional WireGuard/qBittorrent absent.
- On nrm, 33 settings unit tests and a real transient systemd worker/timer
  recovery test pass against the portable runtime, using scratch state only.
  Full settings-linux.py was adapted but not run (qBittorrent binary absent).
- Live browser test creates a unique DNS record through the real UI, verifies
  one Apply request/no confirmation, real DNS response and reload persistence,
  waits 63 s, then verifies the record still resolves. Switch-off takes effect
  immediately. A direct attempt to disable panel.ayc returns 400 before mutation.
  Only the owned fixture is removed afterward; original DNS choices restored.
  First live attempt hit local SSH forwarding conflicts and cleaned its record;
  rerun with ClearAllForwardings passed. Desktop/mobile screenshots inspected;
  no JS/CSP errors. Test script/screenshots remain in the scratch directory.
- Core services/guard active, zero failed units/recent errors; firewall/Caddy/
  dnsmasq/systemd verify (--man=no) pass. Missing API header remains 403. Installed
  worker/frontend SHA256 match source; WebDAV registry/ZIP history unchanged.
  Live DNS already had Cloudflare addresses saved with forwarding disabled;
  these operator choices, empty records/disabled list and firewall were preserved.
- v133 root/Data/app copies and repeat export match; all 44 embedded runtime
  files match sources. Archive SHA256:
  `4747f590a85c176603477829a19bf7a9cf84bd2a997ad74749f7706b80f07be8`.
  Before exporter replacement, both untracked v132 copies were preserved under
  `/tmp/konsol-v133-deploy.HKOJ5r/previous-{root,app}-v132.command`.
  Operator inputs, frozen versions and Desktop were untouched; local preview
  stopped. This was an in-place Debian update, not clean Ubuntu/reboot acceptance.

**2026-09-27 — v2-132, full firewall tables deployed (DD-162):**
- User requested a full firewall table with details/short explanations and
  retained on/off controls. Preserved all existing dirty v130/v131 work; no
  commit/push, reset/reboot, operator-input access or account/ACL changes.
- Changed `console/ayarlar.js` and `ayarlar.css`: eight-column port table,
  service/address descriptions, source CIDRs, scope/interface/family, visible
  draft markers, inline edit/remove and existing switches. All-rules view has
  six columns including conservative explanations, full raw specs/counters and
  ownership. No hidden disclosures or mobile cards; bounded scroll region,
  sticky headers, keyboard scrolling, captions and row/column semantics.
- Backend and policy authority unchanged. Loopback remains protected; foreign
  chains read-only. Draft/review/apply/confirm/rollback flow retained. Fixed a
  grid intrinsic-width overflow caught in the 1024px all-rules test.
- Tests: settings UI covers on/off drafts, CIDR edit/remove/discard, family/
  scope/empty states, locked confirmation, payload/rollback and five widths
  under production CSP. Model A and Files suites also pass. Python 66 pass;
  Bats 147 total, 144 pass/3 missing-timeout macOS skips. Bash/ShellCheck/JS,
  diff whitespace and post-export consistency pass.
- Portable in-place nrm update exit 0/all seven stages passed: scratch
  SSH_HOST=nrm, LOCAL_DOMAIN blank, full-upgrade default no, confirmation E.
  No packages upgraded/installed/removed. Installer repaired one downloads
  ownership/permission entry. Existing data retained; no fresh-host claim.
- Live read-only browser verification passes both families (30/23 port rows,
  51/58 raw-rule rows), switch/discard with zero POST requests, five widths,
  light/dark, keyboard scrolling, no JS/CSP errors. Screenshots inspected.
  Six core services active; no failed units/recent backend errors. Firewall,
  Caddy, dnsmasq, systemd verify (--man=no) pass; live assets match local SHA256.
  Settings override file remains absent/default policy; WebDAV registry and
  ZIP history hashes unchanged. No live port permission was applied by the test.
- v132 root/Data/app exports match; two builds byte-identical and all 44
  embedded runtime files match sources. Archive SHA256:
  `90e5724c250a5e358b5aa0edbd4975406ec92448523adf5850cf987c0461b7ab`.
  Before normal exporter replacement, both untracked v131 copies were saved
  in `/tmp/konsol-v132-deploy.TroDNM/previous-{root,app}-v131.command`.
  Scratch inputs, verification extraction, read-only test and screenshots also
  remain there. Frozen versions and the Desktop were not modified.

**2026-09-27 — v2-131, compact App Store model 2 deployed (DD-161):**
- User approved the second, list-based design. Preserved all uncommitted v130
  work; no commit/push, reset, reboot or operator input access. Only store UI,
  regression coverage, version and documentation changed in this turn.
- Compact rows show name, short description, status and Install/Open. One
  optional Details panel owns technical information, service controls, logs and
  confirmed removal. Progress/errors remain visible while collapsed. Polling
  retains details/focus/log scroll; failed log reads report HTTP errors. Store
  no longer requests qBittorrent account data; its own page still handles login.
- Verified before update: nrm core services active; both optional apps absent.
  Exported and deployed using the portable launcher with scratch SSH_HOST=nrm,
  blank LOCAL_DOMAIN, full-upgrade default no and confirmation E. Exit 0, all
  seven stages passed. No packages upgraded/added/removed; installer repaired
  one downloads ownership/permission entry. File backend restarted; WebDAV
  InvocationID unchanged. Share registry/archive history hashes unchanged.
- nrm: Debian 13.7, kernel 6.12.107+deb13-amd64, tailnet 100.79.17.10, ayc.
  Canonical tree and live frontend are v131, all three changed UI assets match
  local SHA256. Both optional apps remain absent; no actual lifecycle mutations
  were needed for this UI update.
- Local: 66 Python tests pass; Bats 147 cases, 144 pass/3 macOS timeout skips.
  Bash/ShellCheck/JS syntax, diff whitespace and post-export consistency pass.
  Model A/Files/Settings browser suites pass. New fixture checks cover progress,
  failure/retry, lifecycle, cancelled removal/default retention, log HTTP errors/
  safe text rendering, no credential reads, keyboard/poll focus and five widths.
- Live read-only browser acceptance passes 1440/1024/736/390/320 in light/dark,
  details/focus across polling, Files/Settings navigation, zero JS/CSP errors
  and zero mutation requests. Desktop rows measure 75/76px. Screenshots inspected.
  Six core services active, zero failed units/error logs; Caddy/dnsmasq/firewall
  checks pass. systemd verify passes with --man=no (default check failed only
  because dnsmasq's man page is unavailable). Missing API header still gives 403.
- Portable root/Data/app v131 copies match; two exports byte-identical, all 44
  embedded runtime files match sources. Archive SHA256:
  `0e7192cab8f3e52abc8c2cb34d2d36cd87f4ff4d6a3e0d68232777b453164671`.
  Exporter replaced generated v130 copies; both untracked originals were first
  preserved under `/tmp/konsol-v131-deploy.P5014r/previous-{root,app}-v130.command`.
  Scratch inputs, extracted verification tree, read-only live test and screenshots
  remain in that directory. No frozen archive/Desktop copy changed.
- This is an in-place Debian update, not fresh-host/Ubuntu or reboot acceptance.

**2026-09-27 — v2-130, approved Model A implemented; clean installer prepared (DD-160):**
- User approved Model A and requested implementation/clean-install preparation.
  Started from clean commit `18b7ba7`. No commit/push, server reset, deployment,
  Tailscale changes or operator input access this turn. Active checkout is
  `/Users/<user>/Documents/debian-server-installer`, not the stale iCloud cwd.
- Replaced desktop shell with a responsive sidebar. Removed Overview/Applications,
  dock/window controls; Files is default. CPU/RAM/disk below menu, optional app
  entries follow registry. System and Log moved into Settings; qBittorrent has
  its own service/account/path page. Shared drafts/review/rollback preserved.
- Files has Files/Shares/Archive jobs/Trash, folder-only shortcuts and optional
  details. ZIP submission opens jobs, results return to Files. Fixed async WG
  new-network bookmarks, keyboard tab navigation and skip-link route preservation.
- New gated `/api/konsol/kaynaklar`; independent sampler, no WG/port enumeration.
  Missing/stale CPU is unknown, fetch failure hides all meters, recovery resumes.
  Guest CPU time is no longer double-counted. Legacy system API remains compatible.
- Verified: 66 Python tests; 147 Bats cases (144 pass, 3 skipped: macOS lacks
  `timeout`); Bash/ShellCheck/JS syntax and whitespace checks. Model A browser
  fixtures passed production CSP, clean/installed navigation, lifecycle requests,
  resource failure/recovery, archive routes, keyboard/mobile (5 widths). Existing
  Files and transactional Settings browser suites also pass. Screenshots inspected.
- Caddy, dnsmasq and systemd-analyze are unavailable on this Mac. Target validators,
  apt installation, rerun/reboot and fresh Debian/Ubuntu acceptance remain pending.
  `desktop-live.cjs` was adapted, not run against nrm in this turn. No claim that
  local browser lifecycle fixtures install actual packages.
- Built portable root and Data/app v130 copies; replaced their generated v129
  copies (recoverable in Git), no frozen archive modified. Two exports produced
  identical archive SHA256 `96a03a0b168b876955d5fb499d1b52369a0b63546774c1057fafa43ca0330b1d`.
  Verified 44 runtime files match sources byte-for-byte, all eight linked UI assets
  included, no operator inputs/tests/cache/retired desktop.css. No desktop copy made.
- Updated operator instructions to remove obsolete restore promises and explain
  fresh vs rerun. Next: `docs/model-a-clean-install.md` acceptance on a fresh host;
  use scratch inputs for authorized nrm tests, never `kurulum/kurulum.env`.

**2026-09-25 — v2-129, Konsol Desktop and built-in ZIP deployed to nrm (DD-159):**
- User explicitly requested implementation, deployment and tests, superseding
  the previous mockup-only restriction. No commit/push requested. Preserved the
  pre-existing dirty v126–128 work; no frozen version or operator input accessed.
- Desktop launcher/dock/window controls wrap the existing live pages. Files,
  folder WebDAV and ZIP are built-ins; only WireGuard/qBittorrent are installable
  App Store apps. All accounts are visible under Files → Paylaşımlar.
- Added `master_archives.py` and `arsiv.js`: bounded background ZIP/nested ZIP,
  cancel/status/result links, atomic no-replace publication, private staging and
  20-job history. Exact limits/recovery: `docs/desktop-and-archives.md`.
- Installer uses `master-modul yerlesik`; preserves internal IDs/templates for
  existing settings/domain/firewall consumers. Public module verbs refuse both
  built-ins. Rerun does not bounce unchanged healthy services or reset data.
- Deployed twice through the exported portable launcher using scratch
  SSH_HOST=nrm, LOCAL_DOMAIN blank, full-upgrade default no, confirmation E.
  Both completed exit 0. Canonical server tree and installed runtime are v129.
  `nrm` is Debian 13.7, kernel 6.12.107+deb13-amd64, tailnet 100.91.157.4, ayc.
- Verification: 59 Python tests pass; 15 archive tests also pass against the
  installed Debian Python 3.13 backend. Bats: 147 cases, 144 pass, 3 macOS
  skips for missing timeout. Bash/ShellCheck/JS syntax and diff checks pass.
- Fixture browser regressions pass Files forms/list/cards and four-tab Settings.
  Real browser tests pass ZIP create/extract, failed-target correction, shares,
  launcher/dock/window controls, Settings, five widths and dark mode. Real App
  Store qBittorrent install → stop → start → remove passed. It was absent before
  and remains unregistered afterward; package/profile retained, no data deletion.
  WireGuard was absent and not installed by this task.
- Live ZIP checks pass round trip, nested on/off/depth, collision policies,
  malformed/path attacks, atomic rollback and cancellation. Existing v128 test
  DAV accounts retained IDs/hashes/policies/pause through upgrade, rerun and
  reboot; active reader works, paused writer is denied.
- Same-version rerun retained both service InvocationIDs and byte-identical
  archive history/share registry. Real reboot changed boot ID; all five core/
  data services returned active, zero failed units, firewall check passed and
  both persistence suites passed. No Tailscale account/ACL changes.
- Removed only generated DAV/archive test trees, accounts and private manifests;
  synthetic files are not recoverable, ordinary archive history is retained.
  No user's files were removed. Built-in shares are running with an empty registry.
- Portable archive SHA256:
  `bbf1d46a3fe1b803e80e8a17e363042eb2f2b39e2ada42ece7303a3896522d66`.
  Root and Data/app exports match. Prior untracked v128 export was copied to
  `/tmp/konsol-v129-deploy.3JVo6X/previous-v128.command` before normal exporter
  pruning. Scratch deployment inputs remain there without service credentials.
- Fresh Ubuntu install, native Finder/Infuse clients, recipient ACL acceptance
  and a live interrupted-job reboot are not claimed (job recovery has unit tests).

**2026-09-25 — v2-128, Files v09 and folder WebDAV deployed to nrm (DD-158):**
- User requested implementation/server update and reaffirmed disposable-test
  authorization: data loss on `nrm` is acceptable until explicitly revoked.
  Recorded in `CLAUDE.md`; other hosts and Tailscale account policies remain out
  of scope. No commit/push requested. Existing dirty v126/v127 work preserved.
- Files defaults to a list with selected-item details, optional cards and a
  separate WebDAV tab. Existing upload/text/move/rename/trash actions remain.
- Root worker owns per-folder usernames, hash-only passwords, stable IDs,
  RO/RW, expiry and pause; unprivileged descriptor-based Python WebDAV serves
  them on the existing Caddy tailnet port. Legacy shared rclone accounts/URLs
  are retired. Actual boundaries and protocol/client limits: `docs/folder-shares.md`.
- Live discovery: Debian 13.7, kernel 6.12.107+deb13-amd64, Tailscale
  100.91.157.4, domain ayc; v127 and only the file-manager module were present.
  Installed v128 and the Paylaşım module. WireGuard/qBittorrent were not installed
  by this task. Operator `kurulum/kurulum.env` was never accessed: scratch input
  SSH_HOST=nrm, blank LOCAL_DOMAIN (defaults), full-upgrade default no, E to confirm.
- Live rapid-update test exposed systemd start-limit-hit: explicit account
  renewals now reset its counter, wait for HTTP 401 readiness and roll back on
  failure. A crashed registered-running service is recovered; module-stopped
  services stay stopped. Corrected v128 was re-exported and redeployed.
- Verification: 44 Python tests passed on macOS/OpenSSL Python and real Debian
  Python 3.13; Bats 147 cases (144 passed, 3 macOS timeout skips); Bash/ShellCheck/
  JS syntax and diff whitespace clean. Production UI fixtures passed settings
  and Files forms/list/cards/5 widths/dark mode. Real browser on panel.ayc passed
  create → edit RW → pause → remove, without modifying media files.
- Real Caddy + systemd worker tests passed separate credentials, RO refusal,
  RW mkdir/upload/overwrite/file-copy/move/delete, Unicode, ranges, cross-account/
  Destination/traversal/symlink refusal, rotation, pause and API gates. Registry
  remained 0600 root; test passwords absent from registry/env/argv/service logs.
- Corrected installer rerun and a cold reboot passed: byte-identical share
  registry (IDs/hashes/policies/expiry/paused state), active reader works, paused
  writer denied; all five core/data services active, firewall check passes,
  zero failed units. The canonical `/root/debian-server-installer` tree is v128.
- Temporary test accounts, private test manifests and `dav-test-*` folders were
  removed after verification. Paylaşım remains enabled/running with an empty
  registry, ready for the user's folders; the live panel returns HTTP 200.
- Portable archive SHA256:
  `035560de5838809dc4e39a2db15a95c9ecbd28df4f10a521063388e3867ad733`.
  Root and Data/app exports are identical. No embedded account/data backup.
- No fresh Ubuntu install, Finder/Infuse native-client or recipient ACL
  certification in this turn. No Tailscale policy changes. The old prototype
  is frozen; production is a limited DAV subset, not full conformance.

**2026-09-25 — v2-127, settings copy and local-domain update (DD-157):**
- Firewall listener-address explanations and clearer settings copy. Removed
  the redundant health site/name/probe; real panel/API checks stay.
- Caddy local-suffix form updates DNS, custom/disabled names, active/staged
  Caddy/module files and both backend Host configurations. Five-minute new-Host
  confirmation; independent rollback on disconnect/timeout/reboot. Shared state
  lock prevents tailnet refresh races; rollback preserves current tailnet IPs.
- Confirmed domain overrides stale installer input on re-runs. No passwords,
  VPN profiles, files or IP-based share URLs changed. Tailscale Admin DNS is a
  manual prerequisite; the UI explains it and retains old/new recovery links.
- Workstation unit/browser/Bats verification and isolated Debian Caddy/DNS/API
  tests; no host deployment, no fresh Ubuntu acceptance and no commit requested.
- Results: 28 worker tests passed; all 147 Bats cases checked (144 passed,
  3 skipped because macOS lacks `timeout`); shellcheck, Bash/JS syntax and
  production-page desktop/mobile browser checks passed. Real isolated Caddy
  reload + dnsmasq + both backend Host/header gates passed, as did real transient
  systemd worker/timer recovery. Test processes and scratch units were cleaned.

**2026-09-24 — v2-126, approved v08 settings implemented (DD-156):**
- Four live Ayarlar tabs; port overrides/all rules+listeners, local DNS
  records and optional upstreams, qBittorrent account/default folder. Caddy
  remains read-only. Root helper owns validated transactions; an independent
  systemd timer restores unconfirmed changes. Installer/module re-runs consume
  confirmed preferences. No portable backup or embedded credentials added.
- Verified real firewall IPv4/IPv6/order/Tailscale preservation, DNS forwarding
  and private-zone isolation, qBittorrent login/hash/path/rollback in a private
  network namespace with scratch profiles on Debian 13 `nrm`. Real systemd
  worker and timer tested separately against scratch transaction files.
  Existing host services and operator settings were not changed; v126 is not
  deployed. Ubuntu fresh-install acceptance remains outstanding.
- Workstation: settings unit tests, HTTP gate/secret handling regression tests,
  production UI Playwright flow and responsive/dark layouts. Frozen v08 HTML
  remains sample-only. User requested implementation/version, not a commit.

**2026-09-08 — v2-74, OS-aware install (live-verified on `nrm`):**
Full OS-awareness + optimisation review written to
[`docs/os-aware-review.md`](docs/os-aware-review.md), based on source review
plus read-only live discovery on `nrm` (Ubuntu 26.04.1, systemd 259, kernel
7.0.0-31, Docker 29.8.0, Tailscale 1.102.3). Conclusion: detection was already
correct and the probe-over-identity design is kept; what was missing was
*recording* the detected OS and *verifying* that OS-conditional steps landed.
Plan steps 1–5 implemented as v2-74 (**DD-103…107**): needrestart suspended
during apt (it runs in automatic restart mode on Ubuntu and was silently
restarting sshd/docker/tailscaled/caddy/dnsmasq mid-stage); OS identity in
`state.env` with `OS_CHANGED` forcing re-application; `sysctl.d` drop-ins
renamed `99-zz-*` so they sort after provider files, plus a live `ip_forward`
assertion in stage 7; three fail-early gates (nft backend, repo-suite preflight,
rendered-config validation on the target); Docker container log rotation.
Verified: `bash -n` and `shellcheck -x` clean, bats **86 passed / 3 skipped**,
`detect_os_change` exercised across four state files, `assert_repo_suite` and
the `jq` merge exercised against real inputs, and both validators plus the nft
gate and stage-7 assertions exercised read-only on `nrm`.
**Live acceptance on `nrm` (Ubuntu 26.04.1):** four default re-runs plus a cold
reboot, all exit 0. Run 1 (v73→v74) logged "no OS record", deleted both legacy
`99-master-*` sysctl files and rewrote them as `99-zz-*`, added the five `OS_*`
lines to `state.env` and `log-opts` to `daemon.json` — **6/6 container IDs and
start times bit-identical**. Run 2 a full no-op. Run 3 with a seeded
`OS_CODENAME=noble` proved DD-104: logged the release change and re-applied both
apt updates, the firewall, dnsmasq and Caddy (every skip message absent), then
self-corrected `state.env`. After the reboot — the real DD-105 test —
`99-zz-*` sorts after the provider's `99-nc-kernel.conf`, `ip_forward=1`,
`rmem_max` 64 MiB preserved, 0 failed units, 6/6 healthy, firewall `--check`
passes, all five wg modules loaded, dual-path DNS + out-of-domain REFUSED,
Caddy health `ok`, WebDAV 401 on both paths, Tailscale Running/Online/exit-node.
Run 4 (post-reboot) a no-op with container start times unchanged.
**2026-09-11 — first production restore with container-backup:** the
2026-09-06 archive (old Debian 13 nrm, v2-73) was restored onto the fresh
Debian 13.6 v2-79 host from this Mac at 13:39 (+03), followed by a reboot.
Verified afterwards: wg-easy config/db byte-identical to the archive with the
three old peers on `wg0`, qBittorrent password hash identical, FileBrowser
settings identical, Portainer admin present, host fully healthy. Recorded in
`docs/container-backup.md`; its stale "v73" wording was corrected (the tool is
version-agnostic and was exercised at v2-79). Open question raised by the user:
whether WebDAV/Infuse state belongs in the backup — analysis in the session
reply; no code change yet.
**2026-09-16 — v2-110, every network card can be removed (DD-143):**
- The console's wg0 card now carries the same actions as the others: ↻ regenerate and 🗑 remove. Removing
  the last network warns that the page returns to "Yapılandır".
- Live on nrm: wg0 removed from the console (interface gone, registry empty, units disabled, firewall clean,
  0 networks in the console), then re-created with Yapılandır and up again. bats 150 ok.

**2026-09-16 — v2-109, the installer no longer creates WireGuard (DD-143):**
- User's decision: cut the Mac link (no snapshot, no peer preservation, no upload) and let the panel create
  interfaces and devices; `wireguard.command` keeps working over SSH.
- Measured first on nrm: deleting `wg0.conf` left `master-wg list` failing with a raw error, the panel
  logging "sayaç okunamadı" every 10 s and a phantom `wg0` card — the fragility was `wg0` being special.
- Built: every network (including the first) lives in the registry and is created by `master-wg net-add`
  (`wg0` allocatable, `clients-wg<N>` for all, `net-remove` allowed for any); the firewall reads only the
  registry and is valid with zero networks; the installer only prepares the layer and applies the registry;
  Konsol shows a "WireGuard yapılandırılmadı → Yapılandır" card; `wireguard.command` picks a network and
  lost its backup; `WG_PUBLIC_PORT` and the whole snapshot/restore path are gone.
- bats 150 ok. Live on nrm: WireGuard wiped, clean install (0 networks, firewall passes, module loaded),
  first network created from the console (wg0 up with caddy-wg, peer added, profile in clients-wg0), second
  network added and removed, off/on, installer re-run keeps the network, reboot brings everything back,
  `wireguard.command` lists the peer through the selected network.

**2026-09-16 — v2-107 and v2-108, the share is the only WebDAV (DD-141, DD-142):**
- v2-107: the share also answers on `{$TAILSCALE_IPV4}:{$SHARE_PORT}`, like the Infuse WebDAV did (DD-98) —
  an Apple TV could not resolve the MagicDNS name. The console shows both addresses; copy falls back to
  `execCommand` because the console is plain HTTP.
- v2-108 (user's decision): the WebDAV that served all of `DOWNLOADS_PATH` is gone. One rclone
  (`paylasim`) serves only the share root, so nothing is published unless it was shared from Konsol.
  Removed: the `webdav` service, `webdav.<domain>`, port 61003, `WEBDAV_USER/PASS/PORT` and
  `webdav.htpasswd`. `docker compose up` now runs `--remove-orphans`.
- bats 156 ok. Live on nrm: install, the retired container gone, 61003 closed, `webdav.ayc` no longer
  resolving, share round trip on both addresses, non-shared paths 404. Leftovers the installer does not
  touch (no migration code): `/etc/master-stack/webdav.htpasswd` and the `webdav` docker network — removed
  by hand on nrm; the operator must do the same on their own server.

**2026-09-16 — v2-106, share links (DD-141):**
- The user's decision from the design round: one account for everything. Built
  `paylas.<domain>`: a second rclone (`paylasim`), read-only, root
  `DOWNLOADS_PATH/.pay/w`, `--copy-links`; the file backend creates a relative symlink per share and keeps
  the registry (`.pay/kayit.json`) outside the served root. Expiry (1/7/30 days or open-ended) is swept on
  every listing. `.pay` is an empty tmpfs in unpackerr and webdav, and hidden from the file panel.
- Console: share icon per row, a chip on shared items, a Paylaşımlar card with the address/user/password
  (reveal + copy, with an `execCommand` fallback because the console is plain HTTP) and the active list.
- Two bugs found by the live runs, both fixed with a test: a template placeholder with no render variable
  (the new `SHARE_PORT` in the Caddyfile) and a service left on the old configuration when an earlier run
  died between render and restart (`config_newer_than_unit`).
- bats 156 ok. Live on nrm: clean install of v2-105 on a wiped host, then v2-106; WebDAV listing, folder and
  single-file shares, PROPFIND, download, refusal of non-shared paths and writes, expiry, removal, reboot.

**2026-09-16 — v2-105, Konsol (DD-140):**
- The user asked for the WireGuard and file panels to become one admin console; the design was iterated as a
  mockup and frozen as `Data/docs/design/konsol-v01.html` ("Konsol v01").
- Built: `Data/console/` (index.html, konsol.css, konsol.js) served by the file backend at
  `http://panel.<domain>`; Caddy sends `/api/wg/*` to `master-wg-panel` (root, API only now) and the rest to
  `master-files-panel`; `wg.` and `dosya.` redirect. Both backends: host `panel.<domain>`, header `X-Konsol`,
  realm `Konsol`. New: system metrics and the ports card from config, the action log from journald, peer and
  network switches (`master-wg peer|net ac|kapat`, the `#kapali#` marker) and `master-wg keepalive`.
- bats 152 ok. Live on nrm: install, re-run, reboot; peer off/on (the peer leaves and rejoins the running
  interface), network off/on/remove, keepalive and DNS, QR, and the whole file API including the trash; the
  operator's accounts were restored afterwards.
- Left for the operator: the old page directories `/usr/local/share/master-stack/{wg-panel,files-panel}` are
  not removed by the installer (no migration code by design) — delete them by hand.
- Next (designed, not built): share links over a single read-only WebDAV account (`paylas.<domain>`).

**2026-09-15 — v2-104, file panel (DD-139):**
- The user approved the design artifact (https://claude.ai/artifact/9EP7Z5awyKe2h5QizmaDqN) and decided:
  `/downloads` only, trash, the WireGuard panel's account, FileBrowser stays, no access over WireGuard.
- Built `Data/files-panel/` (Python stdlib server plus page), the unit as the downloads uid with
  `LoadCredential`, the Caddy/dnsmasq name `dosya`, the trash tmpfs in unpackerr and webdav, stage 7 checks
  and a panel switch in both pages.
- Live findings: Unpackerr extracts inside hidden folders and ignores `UN_FOLDER_0_EXCLUDE_PATHS_0`, hence the
  tmpfs. systemd needs a user entry for `User=1000`, hence `master-downloads`.
- bats 152 ok, ten mutations caught. Live on nrm: stage 7, the API end to end over Tailscale, and a reboot; the
  operator's accounts were restored.
**2026-09-15 — v2-102 and v2-103 (DD-137, DD-138):**
- v2-102: the panel's "Bağlı" follows received traffic (45 s window, 10 s
  sampler). Live on nrm with the Mac: connect 2–5 s, disconnect 47–48 s.
- v2-103: the user asked that no IP be fixed anywhere. The IPv4 endpoint was
  already detected; `detect_wan` now also stores `WAN_IPV6` (summary only).
  The live check found WireGuard's port closed on the IPv6 WAN, so IPv6 is not
  offered as an endpoint; opening it is the user's call. Test fixtures use
  `203.0.113.7`; a test forbids public IPv4 literals. bats 147 ok; live on nrm.
**2026-09-15 — v2-101, multiple WireGuard networks (user: "wg0-wg1-wg2 … panel arayüz ekle", DD-136):**
- Committed first: `3e9c381` (versiyon/) and `6a711ab` (v2-99/v2-100).
- Built:
  - `master-wg --if/nets/net-add/net-remove`, with the registry at
    `/etc/wireguard/networks`;
  - a multi-network firewall with validation;
  - the `caddy-wg@` template;
  - the panel networks API and tabs;
  - "Mac yedeği" and the backup marker removed.
- bats 145 ok, mutations caught.
- Live on nrm: namespaced clients confirmed per-network internet, `ui`/`inet`
  scope and isolation; remove, reboot, then cleanup. The accounts and the
  user's panel auth were restored.
- nrm now runs v2-101 with wg0 only (0 peers).
- Open: the menu still covers wg0 only (the user tracks it separately).

**2026-09-15 — v2-100, panel tweaks (DD-134):**
- The user installed v2-99 with their own account ("sorunsuz görülüyor").
- They asked for a smaller regenerate section, "onayla" instead of "SIL" and
  wider columns. Done in the panel and in menu option 8.
- Answered: the `cafe` in `fdcc:…::cafe:N` is wg-easy's default range, kept by
  DD-120.
- bats 143 ok; browser-checked at 1440 px.
- Also in v2-100 (DD-135): the IPv6 range is `fdcc:ad94:bacf:61a4::N`
  without `cafe` (the user picked plain numbers).
- No migration: the user said to design for a fresh install and not to
  preserve or fix earlier state. A gate and an old-backup exception were
  written and removed.
- The user must delete `kurulum/wireguard` (a cafe backup, refused) and
  reinstall.
- Multiple interfaces become v2-101.

**2026-09-15 — v2-99, WireGuard web panel (user: "A seçeneği, önerdiğin sıra ile başlayalım", DD-133):**
- The design artifact was approved (tabs per interface). Multiple interfaces
  come as a second step (v2-100).
- Built: `Data/panel/master-wg-panel` (Python stdlib), `index.html`,
  `panel.css`, `panel.js`, `systemd/master-wg-panel.service`, `master-wg
  info`, Caddy `wg.` site, dnsmasq name, `WG_PANEL_*` keys, stage 6
  `ensure_wg_panel`, stage 7 checks, a backup marker in `wireguard.command`.
- bats 143 ok; 13 mutations caught.
- Live on `nrm` with scratch inputs (accounts saved and restored):
  - the panel through Caddy — add, dup, masked/full profile, QR, DNS,
    remove; `wg0` byte-identical;
  - the sandboxed reset and restart on `wgtst0`.
  - The scratch panel account was deleted afterwards: the panel is locked
    until the operator's install.
- Browser check on a loopback copy without sign-in: flows OK. A lost click
  was fixed by updating rows in place on refresh.
- Open:
  - the operator adds `WG_PANEL_USER`/`WG_PANEL_PASS` and re-runs v2-99
    (that also installs the final page files);
  - they try `http://wg.ayc`;
  - offer a `versiyon/` snapshot once it is verified.

**2026-09-15 — versiyon/ folder (user: "çalışan sistemi /versiyon klasörüne kopyala"):**
- `versiyon/2026.08.06-v2-98/` is `git archive` of a4fc938: root commands,
  README and `Data/` without `Data/app`, 36 files. It has a Turkish
  `OKUBENI.txt`, and `versiyon/OKUBENI.txt` is the index.
- Health at snapshot time: every unit active, 5 containers up, `--check`
  passed, Tailscale exit node, 4 peers.
- Future snapshots only on the user's instruction.

**2026-09-15 — fix: backup with zero peers (user: "8 SIL yaptım ama conf dosyaları halen duruyor"):**
- The reset worked on the server (0 peers, new key), but the automatic
  backup failed.
- Cause: the v2-98 backup script's trailing `tar -C "$work"` with no PNGs.
  GNU tar 1.35 exits 2; bsdtar in bats does not.
- Fixed in `wireguard.command` only (no version bump). The test now uses a
  GNU-strict tar wrapper.
- Ran option 6 for the user: the Mac copy now matches the server (0 peers;
  stale profiles and PNGs removed).

**2026-09-15 — v2-98, QR PNG with each profile (user: "sunucu üretsin mac insin profille beraber", DD-132):**
- `master-wg png AD` (qrencode PNG, `-s 8`, refuses a tty).
- `wireguard.command` saves `<ad>.png` next to `<ad>.conf` (600, PNG-signature
  check).
- The backup script makes PNGs in `/run/wg-yedek.*` and tars them; the Mac
  mirrors them.
- The launcher still sends only `*.conf`.
- bats 137 ok; eight mutations caught. Live test on `nrm` with `wgtst0`; the
  test PNG decoded on the Mac (CoreImage) to the exact profile.
- Open: the user re-runs the installer (v2-98), then option 6 creates PNGs
  for the 4 existing peers.

**2026-09-14 — WireGuard DNS default (user: "cloudflare en düşük ping", DD-131):**
- Measured from `nrm`: IPv4 Cloudflare answers consistently under 7 ms; IPv6
  pings 0.5 ms lower but half its answers take 12 ms or more. Uncached: 8 ms
  against 17 ms.
- `WG_CLIENT_DNS_DEFAULT="1.1.1.1, 1.0.0.1, 2606:4700:4700::1001"`
  (`::1001` slightly ahead of `::1111` on cached answers).
- Menu-only default, so v2-97 was re-exported without a version bump. bats
  135 ok.
- Open: the user may move existing peers to it with option 7.

**2026-09-14 — wireguard.command auto backup (user: "2-3-7-8 otomatik yedek"):**
- Options 2, 3 and 7 now call `auto_backup` (option 6) after a successful
  server change; option 8 uses the same helper.
- Menu only, so `V2_VERSION` stays v2-97. bats 135 ok, five mutations caught.

**2026-09-14 — v2-97, DNS change and wg0 regenerate in wireguard.command (DD-130):**
- `master-wg dns NAME DNS` (profile `DNS =` line only) and
  `master-wg reset --onay` (new key, all peers and profiles removed,
  rollback on failed apply).
- Menu: 7) DNS değiştir (new QR), 8) wg0 yeniden üret (asks `SIL`, then
  backs up).
- bats 134 ok; tested live on `nrm` with a throwaway `wgtst0` interface.
- Meanwhile the user reinstalled `nrm` (Tailscale IP now `100.109.236.5`) and
  removed every peer themselves, to add them again; the Mac backup has no
  peers either. `nrm` still runs v2-96.
- Open: the user re-runs the installer (v2-97) before using the menu.
**2026-09-14 — v2-96, cleanup (user: "tüm önerileri uygula"):**
- Removed transition code no host needs anymore:
  - the Transmission gate and removed-key hint;
  - the Portainer warning;
  - the v2-73 sysctl migration and OS-record log branch.
- Fixed:
  - the always-on "sapma düzeltildi" log, which now counts real fixes;
  - `V2_LOG_FILE`, now exported so retry children log apt output.
- Stale wg-easy comments were corrected, and the old reviews moved to
  `docs/archive/`.
- Deleted:
  - the empty `backup/` folder;
  - the two wip branches and their worktree;
  - `Data/app` exports v2-79 to v2-95.
- Kept: the `master` branch and the tags. Not touched (outside the repo):
  `~/.ssh/config` `LocalForward 51821`.

**2026-09-14 — first real rebuild with v2-95 (by the user):**
- The user reset `nrm` and installed v2-95 with their own `kurulum/`.
  Accounts came from `kurulum.env` and qBittorrent from the template.
- WireGuard was restored from the option-6 backup (key, 4 peers, 4
  profiles); `Mcp0` and `NxiPh0` reconnected unchanged.
- Tailscale is now `nrm` on **100.102.206.71**, with the panel already
  updated.
- The read-only check was all green (units, firewall, containers, tailnet
  UIs, auth checks, DNS), and the Mac backup is identical to the server.
- Open:
  - `iPh0` and `iPd0` have not handshaken yet (devices offline).
  - Confirm the Infuse address.
  - Proposed, not started: a Tailscale identity backup
    (`tailscaled.state`) so a rebuild keeps the same IP and name.

**2026-09-14 — v2-95, backup merged into wireguard.command:**
- At the user's request `ayarlar.command` became option 6 "Yedek al" of
  `wireguard.command`, and the separate file was removed.
- The live test piped the choices on stdin. The first `remote version` ssh
  read and swallowed that input, so `remote()` now uses `ssh -n`.
- On `nrm`, from a scratch copy pinned to the server's v2-94, the option
  pulled `wg0.conf` and 4 profiles identical to the user's copy; a second run
  showed "aynı". bats 132.
- Open: the user re-runs the installer (v2-95); the menu version check
  needs it.

**2026-09-14 — v2-94, qBittorrent settings from a template, account from kurulum.env (DD-129):**
- The user dropped pulling qBittorrent and asked the installer to write it,
  with the password in `kurulum.env`.
- To isolate real changes:
  - qBittorrent on `nrm` was reset to a clean file; the old config was kept
    at `/root/qbittorrent-onceki-20260914-182545`.
  - The user set it up in the UI; a second reset was needed after a wrong
    pick.
  - The two files were diffed into `templates/qBittorrent.conf`.
  - DHT/PeX/LSD and anonymous mode stayed default this time.
- Code:
  - `TORRENT_USER`/`TORRENT_PASS` inputs and `python3` in base packages.
  - `qbit_pbkdf2`, which keeps a verifying hash.
  - INI-aware `qbit_conf_diff`/`qbit_conf_merge`.
  - `sync_qbittorrent_config`, which stops the client only to change.
  - Stage 7 `qbit_login_check`: qBittorrent 5.2.3 returns `204` on success,
    found live.
  - The qBittorrent parts of DD-128 were removed.
- Live on `nrm`:
  - sync over the user's config: only the account and auth guards differed;
  - no-op re-run;
  - API change reverted;
  - fresh config correct;
  - no-op after qBittorrent's own rewrite.
  - The user's qBittorrent config and the real accounts were restored
    byte-identical. bats 132.
- Open:
  - The user adds `TORRENT_USER`/`TORRENT_PASS` (their qBittorrent login) to
    `kurulum/kurulum.env`.
  - Delete `/root/qbittorrent-onceki-*` on `nrm` if not needed.

**2026-09-14 — v2-93, ayarlar.command and restore-where-absent (DD-128):**
- The old Transmission dirs on `nrm` were deleted at the user's request.
- New:
  - `ayarlar.command` pulls `wg0.conf`, the profiles (mirrored) and
    qBittorrent's `qBittorrent.conf` only (the user's call: categories, RSS
    and watched folders are unused) into `kurulum/`, printing no content.
  - The launcher sends them.
  - Stage 0 moves them to `RESTORE_DIR` and validates strictly (no `PostUp`,
    subnet-bound AllowedIPs, key format, whitelist, size).
  - Stages 4/5 restore only when the server file is absent, and
    `RESTORE_DIR` is removed after stage 5.
- Live on `nrm` (the user's real host), with real accounts, `/etc/wireguard`
  and qBittorrent `/config` saved and put back:
  - pull OK;
  - a run over the existing server was untouched and no-op;
  - a fresh simulation restored identical key, peers and qBittorrent account
    lines, and the Mac's `iph0` reconnected unchanged.
  - bats 128.
- Open:
  - The user runs `ayarlar.command` into their real `kurulum/`, with the Mac
    off WireGuard.
  - Infuse and Tailscale admin for `100.85.4.106`, if not done.

**2026-09-14 — v2-92, qBittorrent returns (DD-127):**
- The user found Transmission slow.
  - We discussed that DHT/PeX off limits peers in any client; the user keeps
    them off.
  - Docker vs. a host package: Docker stays.
  - The user asked for no installer-written qBittorrent settings. They will
    configure the UI once, then (v2-93) an `ayarlar.command` pulls the
    whole `qBittorrent.conf` plus the WireGuard server config and profiles
    into `kurulum/`. A fresh install restores them, and only when absent on
    the server.
- v2-92 changes:
  - The `qbittorrent` service with `/config` on
    `/etc/master-stack/qbittorrent`; ports come from the image's command line.
  - Stage 7 requires API `403` without a login.
  - `TRANSMISSION_*` input keys are removed and named when present.
  - A leftover `transmission` container gate.
- Live on `nrm`:
  - The host was the user's own fresh v2-90 manual install: Tailscale node
    `nrm-1`, **100.85.4.106**, WG peer `iph0`, installed 14:38 server time.
  - Old keys refused, gate refused, then exit 0 after `docker rm -f
    transmission`, and a no-op re-run.
  - Real account files restored. The Mac's `iph0` tunnel was paused for the
    launcher and reconnected. bats 123.
- Open:
  - **v2-93**: `ayarlar.command` plus the restore.
  - The user sets qBittorrent up in the UI (temporary password in Dozzle).
  - The old `/etc/master-stack/transmission{,-auth}` dirs on `nrm`, to delete
    (they hold the old Transmission password in plaintext).

**2026-09-14 — v2-91, negated bats assertions made effective (DD-126):**
- The work from the merged worktree session was redone on the current tree.
  - 115 bare `!`/`[[ ]]` statements were converted, and a guard test was
    added.
  - Four over-broad assertions were narrowed to code lines: `--disable-exec`,
    `try-restart`, the old FileBrowser password hints, and `docker rm` in
    `die`/`log`.
  - The dead v2-65 `webdav` recreate block in `stage_6` was removed, as the
    user had chosen.
  - The DD-96 guard wording was updated.
- Checks:
  - bats 123 ok, 3 `timeout yok` skips.
  - An exit-code diagnostic showed all 144 negated evaluations returning 1.
  - Six mutations were caught.
- No live run: the removed path needed the uncommitted v2-65 layout.
- `wip/bats-negation-v2-84` is kept for reference.

**2026-09-14 — other sessions merged into this one:** at the user's request,
so nothing is lost when those sessions are archived.
- **"SERVER SETUP" (2026-09-08..13):** v2-74..v2-84 decisions. They are all
  committed (`d2f778b` and earlier) and recorded in the entries below and in
  the DDs. Durable user preferences went to Claude's memory.
- **"Make bats negative assertions actually fail" (worktree
  `claude/magical-shannon-e0b514`):**
  - Its uncommitted work was on a v2-84 base. It is now preserved as `fab2643`
    on branch `wip/bats-negation-v2-84`, not merged.
  - Under macOS bash 3.2 a mid-test `! cmd` or `[[ ]]` never fails a test.
  - Open work:
    - Redo the conversion on the current base (~98 `!`, 17 `[[` at v2-90).
    - Remove the dead v2-65 block in `stage_6` that recreates `webdav` when
      it still publishes `${TAILSCALE_IPV4}:${WEBDAV_PORT}`. The user chose
      removal (DD-96).
    - Fix four tests that match comments or operator messages.
    - Update the DD-96 "Guard" wording.
  - That session's read-only disk check listed `kurulum/kurulum.env` keys
    with the values stripped, which showed only `SSH_HOST=nrm`.
- **"DATABASE CORE" (archived, 2026-09-02, old iCloud copy):** the transcript
  and the path are gone, so nothing was recoverable. Its work predates the
  entries here.

**2026-09-14 — v2-90, smaller install footprint (DD-125):**
- The user saw a fresh install grow disk use by 1.7 GB.
  - Measured: Docker recommends and buildx about 200 MB, the kept apt cache
    303 MB, and debian-keyring 34 MB.
  - The rest was untrimmed blocks.
- v2-90 installs Docker with `--no-install-recommends` plus `apparmor pigz`,
  without buildx. apt deletes its downloaded debs, and debian-keyring is
  dropped (the OS-divergence branch goes with it).
- Found live: `retry` runs functions in a child bash, so the masked-quiet
  dnsmasq/Caddy installs never had `APT_OPTS`. Callers now pass it; a bats
  test covers it.
- Live on `nrm`:
  - Purged Docker/Caddy/dnsmasq and ran with the scratch inputs.
  - The first run hit a transient registry rate-limit at the stage 7 pull.
    The re-run was fine but exposed the `APT_OPTS` bug.
  - After the fix: exit 0, 0 debs, no buildx/git/perl/keyring, no-op re-run,
    df 2389 → 1940 MB.
  - Real account files were restored (hash-identical), and `fstrim` ran. The
    Mac's WireGuard was switched off for the launcher. bats 122.
- Open:
  - The user runs the first install manually.
  - `pppp` handshake.
  - Infuse address.

**2026-09-14 — v2-89, server-generated WireGuard peers and wireguard.command (DD-124):**
- The user wanted peers handled the native admin way, with nothing sent to
  the server.
- `master-wg` on the server generates keys, allocates addresses, keeps
  profiles in `/etc/wireguard/clients` and applies them with `wg syncconf`.
- `wireguard.command` on the Mac lists, adds (name/DNS/keepalive/MTU), removes
  and shows QR codes, saving profiles to `kurulum/wireguard/`.
- The installer now manages only `[Interface]`. `WG_PEERS`/`WG_CLIENT_*`,
  profile parsing and the launcher's WireGuard send/fetch were removed.
- A reinstall means new keys, with devices re-added from the menu.
- Found by tests: `state.env` needed quotes for `WG_CLIENT_ALLOWED_IPS`;
  `master-wg list` clobbered its loop variable.
- `nrm` was reset by the user for a clean test; the old WireGuard files in
  `kurulum/wireguard/` were deleted at their request.
- Live: fresh install with the operator's folder; menu adds, duplicate
  refused, list, QR, removal; namespace client test; no-op re-run; reboot.
  Test peers were removed, so `nrm` has 0 peers. bats 120.
- The user set up the Tailscale admin side: the exit node is offered and
  `ayc` splits to `100.73.123.57`.
- Real devices `pppp` and `mmmm` (this Mac) were added from the menu and
  verified over the tunnel: egress, DNS, UIs, MTU and every blocked path.
  Public-site speed tests were path-limited and later rate-limited.
- Found: `wireguard.command` cannot reach `SSH_HOST` (public IP) while the Mac
  itself is on WireGuard. The user chose no code change: switch WireGuard off
  on the Mac first. This is noted in `OKUBENI.txt` and DD-124.
- Failure tests, with this Mac on the tunnel; the steps ran as transient server
  scripts and were cleaned up afterwards (DD-124):
  - Mac-to-server throughput: `wg0` 461–498 Mbit/s single stream against
    237–241 over SSH, and 386–465 with 4 streams. The server was 75–80% idle;
    the Mac and the home line are the ceiling.
  - `wg-quick@wg0` restart, stop and start: `caddy-wg` followed, peers were
    kept, and the client failed closed and recovered.
  - Docker restart: healthy in 11 s, firewall re-applied with `MASTER-FORWARD`
    first, and bridge IPs closed over WireGuard.
  - `tailscaled` down for 3.5 min: WireGuard UIs and egress 109/109, and
    everything recovered when it came back, without a Caddy restart.
- Open:
  - `pppp` has not handshaken since the `wg0` restart; the user checks the
    phone.
  - Update the Infuse address, if not done yet.

**2026-09-14 — container-backup retired (DD-122) and v2-88, live WireGuard changes (DD-123):**
- The backup tool, its worker, document and round-trip test were removed
  (commit `dccdfbb`); `backup/` stays Git-ignored.
- The user wanted peers handled the kernel WireGuard way: `wg genkey`,
  `wg pubkey` and `wg genpsk`, a `[Peer]` block, then `wg syncconf wg0
  <(wg-quick strip wg0)` with no restart. The installer already did the
  first steps; v2-88 now restarts `wg-quick@wg0` only when it is down, when
  its `Address`/`MTU` changed or when `syncconf` fails, and never passes an
  empty strip.
- Live on `nrm`: removing `deneme` from `WG_PEERS` went from 5 peers to 4
  with `wg-quick@wg0` and `caddy-wg` untouched. `deneme.conf` was deleted and
  the next run was a full no-op. bats 120.
- **Open:**
  - Commit v2-88.
  - Tailscale exit-node re-approval.
  - Fresh-install test when `nrm` is reimaged.

**2026-09-14 — v2-87, WireGuard peers from kurulum.env (DD-121):**
- `WG_PEERS` lists the peers; `WG_CLIENT_DNS`, `WG_CLIENT_KEEPALIVE` and
  `WG_CLIENT_DNS_OVERRIDE` (`name=dns; …`) shape every profile.
- A listed peer without a `kurulum/wireguard/<name>.conf` gets `wg genkey`,
  `wg genpsk` and the next free address on the server (plus `sunucu.key` on a
  first install).
- New and changed profiles go to tmpfs `OUTPUT_WG_DIR`, a QR is printed for
  new ones, and the launcher fetches them back into `kurulum/wireguard/`
  before removing the server copy.
- Verified: bats 121 and three mutations caught.
- Live on `nrm` with the operator's folder (4 devices + temporary `deneme`,
  keepalive 21, one DNS override): exit 0, `deneme` = 10.8.0.6, five profiles
  back and matching `wg0` exactly.
- The fetched `deneme` profile worked as a namespace client (UIs, IPv4/IPv6
  egress; SSH, WebDAV and other peers refused).
- **Open:**
  - The operator removes `deneme` from `WG_PEERS`, then one run removes the
    peer; delete `deneme.conf` by hand.
  - Re-import profiles on devices if DNS/keepalive changed.
  - Commit v2-87.
  - Retire `container-backup`.

**2026-09-14 — v2-86, kernel WireGuard replaces wg-easy (DD-120):**
- `kurulum/wireguard/sunucu.key` plus one wg-easy-format `<device>.conf` per
  peer feed `wg-quick@wg0`, using wg-easy's addresses and port 61001.
- The launcher tars them with `kurulum.env` to `/run`. Stage 0 slurps and
  deletes the folder and validates it.
- After the firewall, `wireguard-tools` is installed and the key match is
  checked with `wg pubkey`. `wg0.conf` then gets public keys and PSKs only.
- `master-firewall` gained `MASTER-FORWARD` (`wg0` → WAN only) and
  `MASTER-NAT`; `MASTER-INPUT` lets `wg0` reach only `10.8.0.1` on the three
  UI ports plus ping.
- `caddy-wg` (admin off, bound to `10.8.0.1`) serves the UIs, independent of
  Tailscale.
- The wg-easy service, network, UI name and legacy modules are gone.
- On `nrm`, before the migration run:
  - The user had deleted the node from the tailnet at 00:52 CEST. A first
    test run with a test file therefore stopped at stage 2 (no auth key,
    410 retries); only the WebDAV htpasswd had changed, and it was restored
    byte-identical.
  - The four device profiles were generated from wg-easy's DB into
    `kurulum/wireguard/` without printing keys, and they matched the running
    peers.
  - `docker rm -f wg-easy`, keeping the volume.
- Migration and checks on `nrm`:
  - v2-86 ran with the operator's own `kurulum/` folder, at the user's
    request and never opened: the auth key logged back in, the node kept
    100.76.190.121 and the run exited 0.
  - A namespace test peer confirmed the allowed and blocked matrix; a no-op
    re-run and a reboot came back clean.
  - A real device then handshook and opened Dozzle at `10.8.0.1:61002`
    (the user confirmed it).
- bats 119.
- **Open:**
  - The operator re-approves the exit node and re-checks DNS in the Tailscale
    admin console.
  - Retire `container-backup` in a separate commit.
  - Run a fresh-install test when `nrm` is reimaged.

**2026-09-14 — v2-85, installer inputs from one file (DD-119):** the user runs
a fixed setup and wants a reinstall with no typed answers.
- `kurulum/kurulum.env` holds every input and is the truth on every run.
  - It is git-ignored with mode 600; the template is
    `config/kurulum.env.example`.
  - The launcher reads `SSH_HOST` and sends the file only to `/run` (tmpfs).
  - Stage 0 parses it strictly (never sourced) and deletes it first, then
    validates, shows a summary without passwords and asks for one `E`.
  - Accounts that differ are rewritten and only their container restarts.
    FileBrowser is compared on a DB copy and updated by stop, then
    `users import --overwrite`, then start.
- Verified: bats 116 (new negative checks use `run !`/`[ ]`, because
  mid-test `!` and `[[ ]]` do not fail under macOS bash 3.2 — a suite-wide
  fix was offered as a separate task), static checks clean, three mutations
  caught.
- Live on `nrm` with the exported `.command` under `expect`: mode 644 refused
  on the Mac; cancel changed nothing; v2-84→v2-85 rewrote only WebDAV; a no-op
  re-run; three password changes hit exactly three services; an unknown key
  and a short password stopped stage 0.
- The operator's real WebDAV htpasswd was saved first and restored
  byte-identical (sha prefix `fead38157cb39fb2`). Test credentials on `nrm`
  are unchanged.
- **Next (agreed, not started):** step 2 — kernel WireGuard replaces wg-easy.
  - Peers are `kurulum/wireguard/*.conf`; the 4 existing peers on
    10.8.0.2–.5 migrate without touching devices.
  - Peers get internet egress plus the container UIs on `10.8.0.1:<UI port>`
    only, through a second, Tailscale-independent Caddy. They get no tailnet
    access, and WebDAV stays Tailscale-only.
  - `container-backup` is retired after the migration is verified.

**2026-09-14 — v2-84, FileBrowser account and Transmission preferences from
the installer (DD-118):** the user wants to rely on the backup as little as
possible. Stage 0 asks for the FileBrowser account (12-character minimum);
stage 4 builds the Bolt DB with `config init` (flags matching quick setup)
and `users import` of an htpasswd-made bcrypt hash, in a network-less one-shot
container, verifies it and moves it into place. The user first suggested
embedding the password from the backup or in `defaults.env`, then chose the
prompt after the trade-offs were laid out. The Transmission seed adds DHT/PeX/LPD
off and a download queue of 12. The backup now carries `wg-easy.db` only.
Verified live on `nrm`. Test credentials on `nrm`: FileBrowser `admin` /
`12345test1234`; Dozzle and Transmission `admin` / `12345test`.
**2026-09-13 — v2-83, Transmission replaces qBittorrent (DD-117):** the user
downloads only and wanted a simpler client. Transmission (LinuxServer, 4.1.3)
at `torrent.ayc`, peer port 61005 unchanged, `QBIT_*` → `TORRENT_*`
everywhere (incl. `state.env` and firewall). Credentials are asked in stage 0
and kept as plaintext root-only files passed via `FILE__` — measured necessary:
the image disables auth without them and its clean-shutdown RPC needs the
plaintext (a hash made stops hang and lose settings). The settings seed must
contain `rpc-port` (without it every stop hung). A leftover qbittorrent
container gates stage 0. Credential rewrites now restart the container (also
fixes Dozzle's password change). Backup scope: Transmission `settings.json`.
Verified live on `nrm`, which the user now treats as a test host again and
will reimage. Test credentials on `nrm`: Dozzle and Transmission `admin` /
`12345test`; `docker_portainer_data` and `docker_qbit_config` volumes remain.
**2026-09-13 — v2-82, Dozzle replaces Portainer (DD-116):** the user uses
Portainer only for state, logs and removal. Dozzle (`amir20/dozzle:v11`) is
now the sixth service at `dozzle.ayc`, with login from a stage-0 prompt
(`users.yml` via the image's `generate`, password on stdin, role `actions`),
actions on, shell off, hardened container, stage-7 login check, and a warning
for a leftover Portainer. The backup scope became three files; Portainer-era
archives still restore. Verified live on `nrm`. **On `nrm`:** Dozzle account
set to `admin` / `12345test` (test answer — the user should replace it); the
Portainer container was removed by hand, and its volume
`docker_portainer_data` is kept pending the user's decision.
**2026-09-13 — v2-81, optional Tailscale auth key (DD-115):** stage 0 asks
for an optional key (hidden, skipped when already online); stage 2 logs in
via `--auth-key=file:` from a 0600 tmpfs file and falls back to the browser
URL on rejection/timeout. Verified by bats (including a fixed
pipefail-dependent exit status), a container-isolated real Tailscale
rejecting a fake key, TTY trimming, and a no-op re-run on the online
production host. A successful real-key login is pending the next fresh
install. **Test incident:** the first isolated test started a host-level
`tailscaled` with only `--statedir`; it loaded the production state for a
few seconds and rewrote `/etc/resolv.conf`, which production restored the
same second — no lasting effect (verified: state file, prefs, DNS, peers,
Caddy). Pitfall recorded in `tests/README.md`.
**2026-09-13 — repository reorganised:** at the user's request the root now
holds only what is double-clicked (current `<V2_VERSION>.command`,
`container-backup.command`, `backup/`) plus `README.md`, `CLAUDE.md`,
`.gitignore`, `.cursor/`; everything else moved under `Data/` (`git mv`).
Exporter keeps the root copy current and archives every version in
`Data/app/`; `latest.command` and the `export/` folder are gone (its backup
moved to `backup/`, click-order note to `Data/OKUBENI.txt`). Re-export was
byte-identical; bats 99 ok. Test backups (`…eVtDgc`, `…DGguu4`, `…j8xNnG`,
test password) are still in `backup/` next to the user's real
`…G3rRfA`; deleting them is pending the user's go-ahead.
**2026-09-13 — container-backup narrowed to one file per service (DD-114):**
the user described their whole post-install routine (Portainer admin,
FileBrowser and qBittorrent passwords and a few preferences, wg-easy account
and peers) and asked to minimise the scope. The same morning's uncommitted
widening of qBittorrent to its settings tree was reverted. Backups now carry
`portainer.db`, `filebrowser.db`, `qBittorrent.conf` and `wg-easy.db` only;
restore writes those four and clears SQLite side files, leaving keys,
certificates, `wg0.conf` and `settings.json` to the install/app. Proven with
throwaway Portainer/FileBrowser instances and a live self-restore on `nrm`
(12 out-of-scope files unchanged). The user's 2026-09-12 real backup stays
valid. The test archive `backup/20260913T105036Z-nrm-settings.DGguu4` came
from the reverted widening and is rejected; delete it.
**2026-09-12 — v2-80, unattended security upgrades (DD-113):** the user
reimaged `nrm` as Debian 13.6, installed v2-79 by hand and restored the real
backup — the first bare-OS run of the runbook; the outcome was verified
(18/18 acceptance, 3 wg peers, restored settings, all DD effects). The
optimisation review found one gap: the netcup Debian image has no
`unattended-upgrades`. v2-80 installs it with the distribution's default
origin filter and `Automatic-Reboot "false"`, and stage 7 reads the policy
back. Live-verified on the Debian host (re-run + no-op re-run, exit 0, no
container recreated, Docker/Tailscale/Caddy outside the filter) after a
first attempt exited 141 on a pipefail/SIGPIPE in the new read-back — now a
bats guard and a tests/README pitfall. Portable v2-80 exported; `export/`
refreshed. Not re-run on Ubuntu (package and files pre-exist there).
**2026-09-11 — container-backup: encryption and single upload (DD-112):**
new backups are `settings.tar.gz.enc` (standard `openssl enc`, AES-256-CBC +
PBKDF2-SHA256 600k; password asked twice on backup, once on check/restore;
decrypted locally, never sent to the server; old plaintext backups stay
usable; archive layout/schema unchanged). Restore uploads once and, since
2026-09-12, no longer downloads a before-restore backup (single copy on
backup, direct load on restore; server-side rollback snapshot kept). The
launcher is macOS only again: a Git Bash/WSL-portable variant was dropped
on 2026-09-12 at the user's request. A `seed` action (installer inputs in the
archive, placed before `install.sh`) was built, verified end to end and
removed the same day at the user's request — see DD-112; the design is in
`d92b338`. Verified: static checks, bats green, round-trip on `nrm`, encrypted
backup/check/restore from the Mac. Ready-to-run copies for the operator live
in git-ignored `export/` with a Turkish click-order note (`OKUBENI.txt`).
**Open:** the user will reimage `nrm` (netcup), install by hand with real
answers and a real WebDAV password, configure the services and take the real
backup; the full runbook (bare OS → install → restore) is then the next
acceptance item. The four test
backups under `backup/` are throwaway (two use a session test password; the
two from the seed build contain `host/` and are rejected by the final tool).

**2026-09-11 — Debian 13 acceptance of v2-79 (nrm reinstalled as trixie):**
closes the Debian gap for v2-77…v2-79. Fresh install from bare metal in 80 s,
no-op re-run (0/6 recreated), seeded `ubuntu/resolute` → `debian/trixie`
release-change run, cold reboot, post-reboot re-run — all exit 0. On the
settled post-reboot system the acceptance check passed 20/20: DD-108 deferred
the netfilter gate (`iptables` absent on minimal Debian), DD-109's resolved
block was skipped (resolved inactive, no drop-in created), DD-110's ordering
held (daemon.json before dockerd's only init; container DNS and log options in
effect with no restart), and DD-111's `tcp_bbr` — previously "expected but
unverified" on Debian — loads on the 6.12 kernel, with `bbr` on Caddy's
accepted socket and `fq` on `tailscale0` after the reboot. Two lessons about
the *acceptance script itself* went into tests/README.md: `Self.ExitNodeOption`
depends on admin approval, so it is informational, not an installer assertion;
and healthchecks need settle time after a reboot (filebrowser's first healthy
came 8 s after a premature check). Neither was an installer defect.
**Both supported distributions have now had the same acceptance at v2-79.**
Ubuntu 24.04 remains unverified since v2-72.

**2026-09-11 — v2-79, BBR adopted after measuring it:** stage 2 now loads
`tcp_bbr` and sets `bbr` and `fq` in `99-zz-master-tcp.conf`. If the module
does not load, the install stays on the kernel default (the DD-108 lesson).
Stage 7 reads the live value back and warns on a mismatch instead of failing
(DD-111). Live on nrm (Ubuntu 26.04): the run logged bbr/fq, the WebDAV socket
Caddy accepted used `bbr`, no container was recreated, and the install exited
0. `tailscale0` stayed on `fq_codel` until the reboot and came up on `fq`
afterwards, as predicted. After the reboot the module was loaded from
modules-load.d, the setting was still bbr, and a re-run exited 0. This also
corrects the review's D1 claim that BBR speeds up exit-node traffic.
Congestion control runs on the endpoints of a connection, so only TCP that
terminates on this host benefits. **Debian verification of v2-77 through
v2-79 is still outstanding** (nrm runs Ubuntu). These changes are either
OS-agnostic or behind a probe, but that is an argument, not a measurement.

**2026-09-11 — Ubuntu smoke test → v2-78 (Docker DNS and log rotation now take
effect):** The smoke test passed 23/23. The one FAIL on the first pass was a
mistake in the test: it expected 403/405/500 from WebDAV, but rclone's
read-only mode returns 404. Nothing was written, and both read-only layers
were intact. An optimisation survey measured the host instead of assuming
anything:
- resources were idle;
- boot took 8.4 s, most of it in the provider's devices;
- tailnet peers sat on DERP while idle and switched to a direct path once
  traffic started (70 → 58 ms);
- the WebDAV hot path has no userspace bottleneck (rclone 475, docker-proxy
  476, Caddy 500 MiB/s);
- UDP offloads already match Tailscale's recommendation;
- no MSS clamp is needed, because the tailnet client advertises an MSS of 1240.
**The real finding:** DD-107's log rotation had never reached a single
container. docker-ce's postinst starts dockerd 2 s before the installer
wrote daemon.json, so every container was created with `LogConfig {}`. The
same ordering left DD-8's container DNS off until the first Docker restart.
v2-78 writes daemon.json before the Docker packages are installed (the DD-18
pattern) and moves the log policy into compose.yaml as an `x-logging` anchor,
so existing hosts get it through a one-time recreate (DD-110). Verified on
the existing-host path, on the fresh-Docker path, and as a clean
purge → reboot → install that exited 0. Along the way, a test-method pitfall
turned up and is now in tests/README.md: a Docker purge without a reboot
leaves stale kernel bridges that collide with the fixed `wg` subnet. That was
the cause of the stage-7 `wg.ayc` 502, and deleting the bridges proved it.
**BBR** was measured with an interleaved A/B, confirming the congestion
control on each run's socket. Peak throughput was identical (~440 Mbit/s).
Cubic dropped ~20% after loss bursts on 3 of 6 runs; BBR did not drop on any
of its 3. BBR is adopted separately as v2-79 (DD-111).

**2026-09-10 — v2-77, A1 closed (and a claim of ours withdrawn):** the fix that
was planned for A1 — narrowing dnsmasq from `interface=lo` to
`listen-address=127.0.0.1` — was tested before implementing and its premise
failed. With resolved stopped and `127.0.0.53` completely free, dnsmasq was
restarted and did **not** take it: `bind-dynamic` binds the addresses *assigned
to* an interface, and `lo` carries only `127.0.0.1/8` and `::1/128`, so the
"start-order bind race" the review claimed cannot happen. The binding change
would have bought nothing and dropped `[::1]:53`; it is withdrawn and
`os-aware-review.md` §4 is corrected. What remained real is that the installer
wrote a setting this release ignores and called it success, so v2-77 reads the
achieved stub state back and reports it either way (**DD-109**), with no
binding change. Live on Ubuntu 26.04: the line appears immediately, run exits 0.
The opposite branch cannot occur where the key is ignored, so it plus a missing
`ss` were exercised in isolation; the wait is wall-clock bounded.
**Debian re-verification of v2-77 is outstanding** — the resolved block is
skipped entirely there, so the change is a no-op by construction, but nrm is
Ubuntu now and that is an argument, not a measurement.

**2026-09-10 — v2-76 accepted on Ubuntu 26.04.1 (nrm reinstalled as resolute):**
closes the gap left at v2-75. Fresh install from bare metal in 95 s, no-op
re-run (6/6 container ids identical), seeded release-change run, cold reboot,
post-reboot re-run — all exit 0, 0 failed units, every §14 check passing.
With the Debian run, **each capability probe is now measured on both branches**:
resolved active (drop-in written) vs inactive (block skipped); stub symlink
repointed vs absent; needrestart present vs absent; iptables present vs
deferred; `debian-keyring` installed vs not. DD-103 measured rather than
assumed — zero needrestart journal records and `sshd` kept its boot timestamp
through a first-install full-upgrade, while every other service start mapped to
an installer stage. DD-102's resolv.conf lifecycle confirmed end to end:
repointed at install, replaced by Tailscale after the reboot, and correctly a
no-op on the next run. **A1 is a standing Ubuntu 26.04 defect, not an upgrade
artifact** — reproduced on a fresh install and across a reboot; still benign,
still deliberately unfixed.

**2026-09-11 — v2-76, OS-divergence inventory (no behaviour change):** after
the Debian regression, the distro-dependent surface was made enumerable rather
than forked. Measured first: of 1159 lines exactly one is a real
`if OS = debian` branch, two are identity-substituted repo URLs, five are
capability probes — so a per-distribution fork would duplicate ~1150 lines to
isolate ~10, double every OS-agnostic fix (5 of this week's 6 DD entries), and
break the single-artifact export model, without creating any test coverage.
Instead: `# OS-DIVERGENCE: <slug>` markers in code, a delimited table in
`architecture.md` §7.1, and bats asserting the two sets are equal with a `DD-*`
on every row. Added the missing `resolved-stub` coverage. Both new tests were
verified by mutation (remove a marker / a table row / a DD citation / move
`DNSStubListener` outside the probe — each fails). A1 stays open.

**2026-09-08 — v2-75, Debian 13 acceptance (nrm reinstalled as trixie):** the
Debian run immediately caught a v2-74 regression: a minimal Debian image ships
**no `iptables` at all**, so the stage-0 netfilter gate died before stage 1
could install it — fresh Debian installs were impossible. Ubuntu ships the
package preinstalled, which is why its acceptance missed it. Fixed as a
two-phase `check_nft_iptables optional|required` (**DD-108**), with the rule
recorded: an early gate may only assert what the host arrives with. Nothing
else needed changing; a dry run of stage 1's package set on trixie resolved
cleanly (`dnsutils` → `bind9-dnsutils`).
Fresh install on a bare trixie host: stages 0–7 in 90 s, exit 0; re-run a
7 s no-op with 6/6 container IDs identical; cold reboot with `99-zz-*` sorting
after the provider file and `ip_forward=1`; post-reboot re-run a no-op; a
seeded `ubuntu/noble/24.04` proved DD-104 on Debian too. All Debian probe
paths confirmed rather than assumed: resolved **inactive** (block skipped,
no drop-in created), no needrestart, no ufw, `debian-keyring` installed.
**Both supported distributions have now had the same acceptance** (trixie
systemd 257 / kernel 6.12; resolute systemd 259 / kernel 7.0).
Steps 6 (dnsmasq `listen-address`) and 7 (BBR/`fq`) still deliberately not
taken; both need before/after measurement on both OS families.

**2026-09-06 follow-up:** Per user request, backup transfer between already
provisioned v73 Debian/Ubuntu hosts no longer requires matching image IDs.
Differences warn by default; `--allow-image-change` is a compatibility no-op.
There is no backup OS/release gate; the installer's OS matrix is unchanged.
Keep actual user/group/port, mount and archive checks, recovery snapshots and
rollback. The suite and existing 11-file settings backup passed on Debian and
inside disposable Ubuntu 24.04/26.04 containers; these are isolated file and
rollback tests, not application-version migration guarantees. Live `nrm`
archive/target check passed; no production restore was performed.

**2026-09-06:** Fixed a false restore UID/GID incompatibility: the saved
qBittorrent environment listed `PGID=1000` before `PUID=1000`, while the
live `nrm` listed them in the opposite order. Normalize both sides when
checking existing schema-1 backups; retain real user/group/port checks and
print field-specific mismatch details. The regression failed with the old
helper and passed with the fix. Existing snapshot
`backup/20260905T174849Z-nrm-settings.iGQ0JK/settings.tar.gz` passed the live
non-mutating target check and isolated 11-file restore/hash/ownership/mode
verification. No production restore or installer change was made. Bash
syntax and ShellCheck passed; Bats: 80 passed, 3 skipped (no local `timeout`).

**2026-09-05:** Added separate `container-backup.command` and Linux helper
`dev/container-backup-remote.sh`. Scope: Portainer data, FileBrowser DB/config,
wg-easy DB/keys/config, qBittorrent `qBittorrent.conf` only. Backups are private,
unencrypted and Git-ignored under `backup/`; no installer seed integration.
Initial live snapshot: `backup/20260905T173254Z-nrm-settings.nceicd/settings.tar.gz`.
All 11 data files passed isolated restore/hash/ownership/mode verification;
production restore was not performed. See `docs/container-backup.md`.

**v2-73 in [Unreleased] (2026-08-30):** Ubuntu 26.04's nft-default host did
not load the legacy IPv4 `ip_tables`/`iptable_nat` modules required by
wg-easy's in-container `iptables-legacy`; `wg-quick up wg0` therefore failed
at its IPv4 NAT rule. Stage 4 now preloads and boot-persists those modules
alongside `wireguard`, `ip6_tables` and `ip6table_nat` (**DD-10**). The live
host recovered after loading both modules and restarting only wg-easy. A
v2-73 default re-run preserved all six container IDs/start times; a cold
reboot then loaded all five modules through `systemd-modules-load`, brought
wg-easy up healthy on UDP 61001 with no current-boot iptables errors, and
passed firewall, dual-path DNS, Caddy, authenticated/read-only WebDAV and
zero-failed-unit checks.

**v2-72 (2026-08-29):** Ubuntu 24.04/26.04 LTS support —
`require_supported_os` matrix, repo lines from `os-release`, ufw gate,
resolv.conf stub repoint, dpkg-lock wait (**DD-102**). **Live-verified on
both Ubuntu lines:** noble 24.04.4 on 2026-08-29 and resolute 26.04.1 on
2026-08-30. The resolute run covered a fresh install through stages 0–7,
independent contract checks, a byte/container/service-stable re-run,
Tailscale and Docker restart recovery, firewall re-application, and a full
reboot. Six containers, dual-resolver DNS, Caddy, authenticated/read-only
WebDAV and host DNS all passed. On reboot Tailscale may replace the stage-6
uplink symlink with its direct-mode MagicDNS `resolv.conf`; this is expected
and host DNS remains healthy. Last release: **v2-71** (2026-08-28, tag
`2026.08.06-v2-71`) — pull disk floor, single-pass downloads repair,
plus the v2-65…70 line (**DD-98…101**).

| | |
|---|---|
| Version | `2026.08.06-v2-79` (unreleased) |
| Branch | `quantum` |
| Last tag | `2026.08.06-v2-71` |
| Tests | 95 Bats: 92 passed, 3 skipped (no workstation `timeout`); isolated backup tests passed |

### Evaluated and rejected (2026-08-28 review)

- Gating `apt-get install` calls on dpkg state — would silently drop the
  "re-run refreshes docker/tailscale to the current repo version"
  behaviour.
- Timestamp/state gating of the downloads-tree repair — reconcile-engine
  shaped; the single-pass find is the accepted optimization instead.
