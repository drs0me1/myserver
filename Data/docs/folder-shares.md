# Folder WebDAV (DD-158/DD-159/DD-179/DD-190/DD-191/DD-192)

## Caddy publication gates (DD-191)

Settings → Caddy now lists Panel, qBittorrent and WebDAV. The WebDAV row saves
Tailscale and Internet independently; a disabled HTTPS domain is remembered.
Panel's Tailscale address always stays; its optional public HTTPS name (DD-195)
shares TCP 443 and the socket budgets below. The global WebDAV choice only restricts
folder connection policies; it never widens them or changes accounts. Both
connection cards remain visible and explain a disabled global gate; no address
is advertised through that gate. Private off returns 403, including the
Tailscale IP address; it does not stop WebDAV or remove shared Caddy listeners.
Row saves reload Caddy gracefully. Existing transfers may finish.

qBittorrent may share the HTTPS port with a different hostname and its own
native login, not the WebDAV account. TCP limits apply to their shared public
port; WebDAV's request/password budgets still apply only to WebDAV. If both
publications are off, no public Caddy listener is generated. For qBittorrent
HTTPS while folders are shared over legacy WebDAV HTTP, first save an HTTPS name
or close those folders' internet connections; with a qBittorrent or Panel row on,
legacy HTTP internet access stays unavailable until an HTTPS name is saved (v2-169).
These choices persist through module reapply and installer reruns.

The DD-190 text below also describes the compatible older HTTPS-only API;
the new row's Internet toggle preserves its domain when turning WAN off.

## Connection policies and WAN limits (DD-179/DD-192)

Each folder has independent `connections.tailscale` and `connections.wan`
policies: enabled state, RO/RW and absolute expiry. They share the folder, ID,
username and password hash. New shares default to Tailscale enabled, RO, seven
days, and WAN disabled, RO, seven days. Either or both connections may be off;
both off retains a paused account without a separate global pause field.
With no HTTPS configuration, enabling or re-enabling WAN requires
explicit `ack_wan_http: true`: that mode is **unencrypted HTTP**, so credentials
and content can be observed or modified in transit. Limits do not provide TLS.
Configured HTTPS removes only the plaintext acknowledgement, never the explicit
WAN opt-in or per-folder authentication/authorization.

Caddy binds only the server's assigned, globally routable WAN IPv4. Publication
depends on the saved HTTPS mode (below), not just the folder count. No NAT discovery,
provider forwarding, IPv6 WAN, wildcard bind, admin/API route or ACL change.
Manual firewall denials remain effective; the form notes this prerequisite.
Public results distinguish candidate card URLs from active `row.urls`; an off
or expired connection may retain a candidate address while its global transport
is available. Unavailable WAN is not advertised. See Ownership and API below.
**DD-182:** the address must still be assigned to this host (a probe bind). If
the provider changes it, WAN is unavailable with "kurulumu yeniden çalıştırın",
the 30 s guard removes the public site, and a Caddy that could not start on the
old address is started without it. The installer drops a site bound to a stale
address before restarting Caddy; stage 7 publishes it with the new address.

The unprivileged process uses separate loopback addresses on SHARE_PORT:
127.0.0.1 for Tailscale, SHARE_WAN_BACKEND for WAN. Listener scope, not an HTTP
header, selects that connection's enabled/permission/expiry policy. Caddy overwrites X-Share-Client-IP using
the socket peer; client X-Forwarded-For is not trusted. All DAV methods require
an enabled, unexpired connection, including OPTIONS and unsupported methods.
Every supported write method requires RW on the receiving listener; the other
connection's permission cannot authorize it.

- WAN: 8 backend connections total, 4 simultaneous requests per source IP
  and a 30-second socket inactivity timeout. WAN and Tailscale each have an
  independent four-slot/two-slot scrypt budget; authentication waits up to 200 ms and
  checks the success cache again before doing expensive work (**DD-188**).
  Capacity exhaustion returns 503 with Retry-After (connection admission uses
  one best-effort nonblocking reply); bad-credential blocks remain 429.
- Five supplied bad credentials in a sliding 60 seconds block that IP for
  300 seconds; 429 includes Retry-After. Missing Authorization is the usual
  uncounted 401 challenge. Unknown accounts and malformed credentials count.
  The 4096-entry table fails closed when full; active blocks are never evicted.
- **DD-180:** the same per-IP rule also applies on the Tailscale listener, keyed
  on Caddy's X-Share-Client-IP (local probes without it share one key). Per
  share and listener, 100 bad credentials within an hour close that share for
  an hour to every address that has not logged in to it since the service
  started; the recipient already connected keeps working. The service logs only
  the share ID and the fixed numbers. A wrong user or unknown share
  also costs one scrypt check, so timing does not reveal which part was wrong.
- Tailscale keeps its independent pool of 64 connections (Caddy keeps up to 32
  idle upstream connections for at most 30 s, below DAV's 60 s idle timeout).
  WAN connections close after each
  response; proxy keepalive is off for that upstream. Every closing reply says
  `Connection: close`.
- **DD-181:** a successful login is remembered in memory for 10 minutes (256
  entries, keyed by share, stored hash and an HMAC of the exact Authorization
  value), so repeated Infuse/Finder requests skip the scrypt check. Cache hits
  never bypass the receiving connection's enabled state, permission or expiry;
  another password or listener needs its own verification. A registry edit
  restarts the service and clears the memory. Per-IP and per-share limits still
  apply to every request. Replies are sent without Nagle delay
  (`TCP_NODELAY`).
- **DD-193:** concurrent requests with the same exact Authorization value on the
  same share and listener share one verification: they wait up to 2 s for the
  one in progress and reuse its success. A failed or slow first check makes each
  of them check itself through the normal bounded path above.
- Host TCP admission additionally caps new WAN sockets at 16 per source IP and
  64 total, before manual allow rules. Conntrack can temporarily retain closing
  sockets. These are connection counts, not bandwidth caps or DDoS protection.
- The WAN Caddy listener has a 10-second header deadline and 30-second keepalive
  idle limit; other listener timeouts are unchanged. Caddy startup waits for and
  checks the owned firewall before serving. See the official [Caddy listener
  binding](https://caddyserver.com/docs/caddyfile/directives/bind) and [server
  timeout](https://caddyserver.com/docs/caddyfile/options#timeouts) semantics.
- In-memory login blocks reset on service restart, including account edits;
  unauthenticated clients cannot trigger such restarts.

Registry changes restart the data service, then validate/project Caddy and the
owned firewall rules. Failures restore the old registry/projection; a private
pending snapshot recovers interrupted changes under the same locks. A focused
30-second `master-share-network.timer` closes expired legacy HTTP WAN projections and
recovers pending operations, without rewriting unchanged state or restarting
healthy services. Request/chunk expiry remains immediate; listener/rule cleanup
is normally within the next tick and defers during locked/pending settings
operations. In legacy HTTP mode, disabling/removing the last active WAN
connection closes the projection
synchronously. Configured HTTPS retains its listener and firewall permission for
ACME renewal even with zero active folders; every request still checks scope,
account, identity and that connection's enabled state, permission and expiry.
Reboot reprojects from the saved settings
and registry. This is not a general service reconciliation engine.

## Optional public HTTPS (DD-190)

Settings → Caddy has a separate full public-domain field, such as
`dav.example.com`; it does not rename `LOCAL_DOMAIN` or the private service names.
Enter only the name, not a URL, port, path, IP address or wildcard. DNS must
resolve to exactly the assigned `WAN_IPV4`: use a DNS-only A record, with no AAAA
record or provider proxy. The installer does not edit public DNS.

| Saved HTTPS setting | WAN endpoint and lifetime |
|---|---|
| No `https` key | Existing consent-gated HTTP at `WAN_IPV4:SHARE_PORT` (61010), only while an enabled, unexpired, identity-valid WAN connection exists |
| `https.domain` is a public name | HTTPS at `WAN_IPV4:SHARE_HTTPS_PORT` (443); retained for issuance/renewal with no active folders, provided the address is assigned, the registry is valid and WebDAV is registered as running |
| Explicit `https.domain: ""` | WAN off: no HTTP fallback or advertised WAN URL; saved folder accounts/connection policies remain |

Caddy owns certificate keys, Let's Encrypt issuance and renewal through
TLS-ALPN on TCP 443. HTTP challenge is disabled and `auto_https disable_redirects`
prevents a WAN port-80 redirect listener. No Cloudflare/DNS API token or new
certificate daemon is used. The public site proxies only `/s/*` to the existing
WAN backend; `/`, `/api/*` and all other paths return 404. All existing scope,
authentication, resource and firewall limits apply equally to HTTP and HTTPS.

Save uses the existing Settings worker, revision and operation locks, with durable
pending state before any projection. It commits immediately only after a trusted
certificate chain and hostname verify; there is no second connectivity-confirmation
step. DNS, Caddy, firewall or certificate failure leaves/restores the previous
configuration, and the independent Settings guard recovers interrupted pre-commit
work. A durable commit is not undone by a later crash. An unsuccessful first
HTTPS attempt may restore the previous explicitly consented HTTP mode; a committed
HTTPS configuration never silently falls back to HTTP when its certificate fails.

The certificate probe connects locally to the assigned WAN IPv4 and uses the
domain for SNI and hostname verification; it does not connect to an arbitrary
resolved target. “Certificate ready” is **not proof of internet reachability**.
Settings shows expiry, and health warns at 14 days or less remaining. Check public
DNS, CAA and inbound TCP 443 separately if issuance or external access fails.

Public WebDAV HTTPS is edited in Settings → Caddy → “Adresler ve erişim”
(**DD-191**, **DD-193**). Turning the WebDAV internet switch off and saving it
removes the public site/permission through a graceful Caddy reload, closing new
WAN connections; existing transfers may finish. The name is remembered for a
later re-enable. The API form `{"https": {"domain": ""}}` (test tooling) has the
same effect without remembering the name. This is distinct from account
mutations, which restart WebDAV and interrupt all transfers. Tailscale HTTP on
port 61010 and private names remain unchanged in every mode. A save that enables
internet access first checks that the listener is up and fails at once with the
cause otherwise, instead of waiting for a certificate.

The Files layout is implemented in `console/konsol.js`, `dosyalar.js`
and `dosyalar.css`: list by default, optional cards, selected-item details on
the right (below on mobile), folder search/breadcrumbs and a WebDAV shares tab,
next to upload, text view, move, rename and trash.

## Accounts and lifecycle

- Files and WebDAV are built in. Select a folder, open Details,
  then WebDAV sharing. All accounts appear under Files → Paylaşımlar.
  No folder is published by default; no App Store installation is needed.
- Each of at most 32 non-overlapping folders has an opaque stable 24-hex ID
  and its own unique username/password, shared by its two connections. Each
  connection has its own RO/RW permission and 1/7/30-day or unlimited lifetime.
- Each Shares entry and its details show two cards: Tailscale and WAN. Each has
  its own switch, permission and expiry controls, status/reason, address/copy
  action and Infuse protocol, host, port and path details when an address is
  available. WAN says HTTPS when configured, or HTTP (WAN) with an explicit
  plaintext warning in legacy mode. A switch shows the saved choice; a global
  Caddy gate can still make access unavailable, with the reason shown.
- Connection controls save nested partial updates immediately. Explicit RW
  requires acknowledgement for that card. Choosing 1/7/30 days starts only that
  connection's duration now; otherwise its exact absolute expiry is preserved.
  Switching off/on never renews expiry. Both off retains the account. Manage
  edits only the shared folder/username/password; connection edits never rebind
  a missing or replaced root. Failed writes retain the last confirmed UI values.
- Address: `http://<tailscale-ip>:<SHARE_PORT>/s/<id>/`. The same path works
  through `paylas.<LOCAL_DOMAIN>` when Tailscale is selected. A WAN-enabled share
  gets `https://<public-domain>/s/<id>/` in HTTPS mode (including a nondefault
  port when configured), or `http://<wan-ipv4>:<SHARE_PORT>/s/<id>/` in legacy
  HTTP mode. A connection card may show/copy its candidate URL even while off
  or expired; its status does not claim that the address grants access. A global
  off mode advertises no WAN URL. The UI labels each network/scheme;
  the IP/domain and port come from runtime state and saved HTTPS settings.
- Blank password on edit keeps its hash; keep-duration preserves the exact
  expiry. New passwords have 8–256 characters and can be generated in the
  form. They are never retrievable after saving. No password goes into browser
  storage, argv, environment files, progress or audit logs.
- RW explicitly includes upload, overwrite, mkdir, move, file copy and deletion.
  Each explicit RW selection needs its own acknowledgement: WebDAV deletion
  is permanent, not Konsol trash.
- Disabling a connection preserves its policy, the shared account and stable
  path. Remove revokes both connections/account, never the folder. Each
  connection's expiry is enforced on requests and live transfer chunks without
  opening the console; expiry on WAN does not expire Tailscale or vice versa.
  A folder moved/replaced on disk fails closed;
  edit its path to deliberately reconnect the same public ID.
- Every share edit, including a connection switch/permission/expiry change,
  atomically writes the registry and restarts an active
  WebDAV service to reload its credential, interrupting **all** current WebDAV
  transfers. The Shares and Manage restart warnings remain visible. A stopped
  service stays stopped. A failed restart restores the
  previous registry and attempts to restart it. Confirm the list after an
  uncertain/timeout response before repeating a mutation.
  Explicit renewals reset systemd's start counter and wait for the anonymous
  HTTP 401 gate before returning success; automatic crash throttling remains.
- Installer reruns and reboot preserve the registry. Public module
  operations cannot stop/remove Files or WebDAV, even with `--veri`. Remove
  individual accounts in Files → Paylaşımlar; this never removes their files.

## Ownership and API

- `panel/master_shares.py`: root-only registry owner, fixed
  prepare/status/save/remove operations, scrypt hashes with random salts. The
  source is `SHARE_STATE_FILE` (`/etc/master-stack/webdav.json`, 0600 root),
  schema 4. Every item has exactly two policies, `connections.tailscale` and
  `connections.wan`, each exactly
  `{enabled: bool, permission: "ro"|"rw", expires: Unix-seconds|null}`.
  `null` is unlimited. Shared `permission`, `expires`, `paused` and `networks`
  are not authoritative; schema-4 records containing any of them are rejected.
- Loading valid schema 3 converts only in memory. Each policy copies the exact
  old shared permission/expiry, even when off, expired or unlimited. It is
  enabled only when its scope was selected and `paused` was false. IDs, paths,
  names, usernames, salts/hashes, identity, `created` and `changed` remain
  unchanged. `prepare` persists schema 4 once; unchanged preparation does not
  rewrite it. Schema 2 is unsupported; malformed/conflicting input fails closed.
- `master-panel`: existing Host, same-origin and `X-Konsol: 1` gates.
  `GET /api/konsol/paylasim` lists public metadata; POST `.../kaydet` and
  `.../kaldir` dispatch fixed transient workers with JSON on stdin.
  The worker locks install, module and share operations, in that order; pending
  settings transactions block account changes.
- Save accepts `connections` with one or both scope patches, each containing
  only `{enabled?, permission?, days?, ack_write?}`. `enabled` is boolean and
  `days` is integer 0/1/7/30; zero means unlimited, other values start at save
  time. Omitted scopes/fields preserve current values under those locks,
  including exact expiry. Explicit RW always needs `ack_write: true` in that
  same scope, even if already RW or disabled. Unrelated edits preserving RW
  need no new acknowledgement. Shared path/account/password fields remain
  separate; `ack_wan_http` remains top-level for legacy HTTP opt-in.
- The old global `.../durum`/`pause` operation and save fields `permission`,
  `days`, `expires`, `networks`, `paused` and top-level `ack_write` are rejected
  with a refresh-page message, without changing either policy.
- Public `row.connections[scope]` adds `expired`, `available`, `active`,
  `reason` and `url` to the saved policy. Connection `available` is the global
  publication/transport gate; row-level `available` is folder identity validity.
  `active` also requires enabled, unexpired, valid folder and running service
  registration. `reason` explains why access is inactive. `url` is a candidate
  whenever the global transport is available, even with the connection off or
  expired; otherwise it is empty. `row.urls` contains only active connections;
  `row.url` is the first active URL, or empty. No hashes, salts or filesystem
  identities are returned; availability is not an external reachability probe.
- `panel/master_https.py` owns HTTPS configuration interpretation, bounded DNS
  checks, pinned verified-certificate probes and the generated WAN site.
  `master_settings.py` owns the `SETTINGS_FILE.https` choice and its durable
  transaction; HTTPS uses the existing gated Settings API, not a public API.
  The firewall helper receives four fields: active, per-IP limit, total limit
  and selected port. `SHARE_PORT` and `SHARE_HTTPS_PORT` come from defaults/state.
- `panel/master_webdav.py`: Python stdlib server, loopback only, never root,
  runs as DOWNLOADS_UID/GID in `master-paylasim.service`. The service receives
  the registry through `LoadCredential=registry:...`; command line contains
  only its path. Capabilities are empty; system files are read-only, home and
  internal trash/share paths, the archive staging area and packages' private state
  (`PRIVATE_STATE_ROOT`, `/var/lib`) inaccessible, outgoing traffic limited to
  loopback (**DD-225**).
  `SERVER_ROOT` is writable to support shares anywhere inside the user area.
  **Per-folder isolation is enforced in the request handler, not by a separate
  OS sandbox per account**; the supported DAV subset is intentionally bounded.
  The process also uses a system-service syscall filter, private IPC and hidden
  foreign processes, TasksMax=96 and MemoryMax=512M (including reclaimable page
  cache). Automatic crash restarts are capped at five starts in ten minutes.
- Caddy proxies the tailnet name/IP port and an opted-in WAN IPv4 site.
  No Tailscale ACL/grant is created. An address refresh
  restarts only Caddy; WebDAV remains on loopback.

## Filesystem and protocol boundaries

Paths are resolved from directory descriptors with O_NOFOLLOW. Root identity
includes device, inode and birth time (Linux statx); unsupported filesystems
fail closed. Root/internal/hidden directories, the folders packages declare or
report they write into (DD-203), symlinks, multiply linked regular files,
cross-device children and overlapping share roots are refused. `SHARE_DIR` (`.pay`) below `SERVER_ROOT` is a reserved
internal name (DD-171): the installer never creates, reads or deletes it, Files
hides it and refuses to create it, and WebDAV and the packages' services cannot
access it when it exists. If an application's temporary folder is later pointed
into an existing shared subtree, WebDAV keeps serving it until the registry's
derived folder list is rewritten and WebDAV restarts. A Konsol share save or
removal does both (and cuts running transfers). An installer run rewrites the
list, which WebDAV applies at its next start. The 30-second guard never does.
A share whose path would contain such a folder cannot be created or re-pointed.
After such an external change, save or remove the share in Konsol.

PUT/COPY stage content in a hidden sibling without holding the global mutation
lock. Publication revalidates the receiving connection's enabled/RW/expiry
policy, share identity, root and parents, target
and source versions, and request preconditions under the lock; a concurrent
change fails rather than overwriting it. Fsync and atomic rename ensure an interrupted
request does not replace the previous file. A process kill may leave a hidden
temporary file; it is never served and there is no automatic cleanup daemon.
DELETE may partially complete if a later child cannot be removed; it is not a
transaction and cannot be undone. Trusted host administrators can change the
filesystem concurrently; this is not an isolation boundary against root.

Supported: OPTIONS, GET/HEAD (single byte ranges and ETags), PROPFIND Depth 0/1,
PUT (fixed-length/chunked, up to 64 GiB), MKCOL, DELETE, MOVE and **file** COPY.
PUT and COPY stop with 507 before the filesystem falls under min(5 GiB, 10%)
free space, and remove their temporary file (**DD-180**).
Destination must stay in the same share/host. No DAV locks, PROPPATCH or directory
COPY: these explicitly fail, never report false success. Full WebDAV conformance
and Finder/Infuse interoperability are **not certified** by protocol tests.
Connection limits are listed above; 10,000 entries per PROPFIND listing.

## Network prerequisite

Konsol is administrative: any tailnet device, or the single internet account (DD-194, DD-205), manages every folder and
share. Never give recipients the Konsol password. Recipients must be allowed only the
WebDAV port, with Konsol/SSH restricted to administrators in Tailscale ACL/grants.
Review broader existing grants; adding a narrow allow does not remove them.
The installer does not change account policy. Private HTTP is carried inside the
Tailscale tunnel; public HTTPS is the separate opt-in above. DAV locking remains
unsupported, and clients requiring it need a separately validated solution.
Neither TLS nor protocol tests certify native-client compatibility. Do not weaken
client security settings to claim compatibility.

## Verification

`tests/test_shares.py` tests real HTTP requests and descriptor boundaries;
`tests/files-ui.cjs` checks production-page forms and ten viewport widths in both themes.
`tests/shares-live.py prepare` runs through the installed Caddy and systemd
workers on an explicitly authorized disposable host; it prints a private
manifest path (not credentials). Use `verify <manifest>` after rerun/reboot,
then `cleanup <manifest>` to remove only its own test accounts and files.
HTTPS-specific coverage is in `test_https_settings.py`, `test_https_panel.py`
and `settings-https-ui.cjs`; opt-in `https-live.py` creates three temporary
shares, tests both networks and connection disabling, then removes its fixtures and checks the
original registry digest. Its `--configure` option deliberately leaves the real
domain saved. See [the test runbook](../tests/README.md) for commands and limits;
these descriptions do not imply a completed live run. DD-192 acceptance uses
`test_share_connections.py`, `test_webdav_connections.py` and the opt-in
`python3 Data/tests/share-connections-live.py --host nrm` from the repository
root. The latter creates one temporary folder/account to test independent
RO/RW, switches and WAN-only expiry, then checks byte-identical registry
cleanup. It restarts WebDAV and interrupts transfers. The optional read-only
`share-connections-browser.cjs` requires an existing share, creates none and
rejects every API mutation while checking installed cards at three widths in
both themes. Main reports both live checks passed after the v2-164 `nrm`
deployment; see [SESSION.md](../SESSION.md) for exact results and host health.
Native clients and a fresh Ubuntu install require separate acceptance.
