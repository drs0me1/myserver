# Files and archives (DD-159, DD-166, DD-170, DD-183)

## Built-in capabilities and App Store

Konsol is one sidebar workspace, not a desktop or remote OS session. Selecting
items in Files shows a contextual action dock: six equal icon/label cells with a
separate count/dismiss header, disabled slots for ineligible actions and a
mobile 3×2 grid. Files is the initial view; Settings owns
system/firewall/Caddy/Dnsmasq/logs, and installed qBittorrent owns its
account/path form (DD-160).

Files, per-folder WebDAV and ZIP/RAR are built in. All folder accounts are listed
under Files → Paylaşımlar. The App Store has only WireGuard and qBittorrent as
installable/removable applications. Tailscale, DNS/Caddy and the firewall remain
protected base services; there is no arbitrary-package installation endpoint.

The installer calls `master-modul yerlesik` to enable/check the two data services
and publish the share name/port. An unchanged rerun does not restart them and
creates no folder account. Public module actions reject `dosya` and `paylasim`;
these are internal template/registry IDs used by DNS/Caddy/firewall rendering.
See [folder shares](folder-shares.md) for credential and recipient-ACL boundaries.

## Archive operations (DD-170)

Select files/folders in Files to reveal the bottom action dock; the breadcrumb
and search bar remain in place. “Arşiv oluştur” always creates ZIP (suffix added
automatically), while “Arşiv açıcı” recognizes supported archives/volumes. Choose
an existing destination folder, result name and outer-name collision policy
(rename, skip or stop). Results are new files/folders; sources and existing
destinations are never overwritten or deleted. The destination defaults to the
installer's `DOWNLOADS_SUBDIR`, exposed by `GET /api/state.downloads`, independently
of the source folder and qBittorrent's current save directory. A click-to-browse
picker uses the existing directories-only file API; no free-text path entry.
Nested extraction is automatic and retains inner archives beside their extracted
folders, without flattening conflicting paths. The first archive counts as layer
one. The UI has no depth option and shows no technical statistics/limits.
At the five-layer ceiling automatic extraction fails atomically, never reporting
incomplete nested work as success. A corrupt/unsupported inner archive fails the
whole job; no partial result folder is published.

**DD-183: no jobs page.** Starting a job keeps Files open. While a job is queued
or running, one bar above the Files list shows its name, state, server message
and "İptal et"; it disappears when the job ends and a toast reports the result.
Ayarlar → Günlük records the start (`arsiv-olustur`/`arsiv-ac`: sources → result
name), a cancel request (`arsiv-iptal`) and the result written by the Files
backend when the job ends or is found interrupted at startup (`arsiv-sonuc`:
message; `hata` for failed/interrupted). The private 20-job history is available
through `GET /api/archives`.

ZIP Store/Deflate and unencrypted RAR3/RAR5 (including solid archives) are supported,
not encrypted archives, multipart ZIP, large ZIP64 or 7z. All RAR volumes must be
in the same folder: `.rar/.r00/.r01…` or `.part01.rar/.part02.rar…`. Selecting a
later part resolves the first automatically. Missing/ambiguous parts fail closed;
nested multipart sets are opened once, not once per volume. RAR creation is not offered.
Limits are shared across each entire job, including
nested work: 2 GiB processed uncompressed bytes, 10,000 entries (directories
included), five layers, 900 seconds, and a 16 MiB central directory checked
before Python allocates its entry list. Nested archive bytes count when copied
and their contents count again when extracted. These are safety limits, not a
promise that every 2 GiB archive will finish under the service resource cap.
One job runs at a time; a second submission is rejected until it finishes.

Jobs run on a worker thread in the unprivileged file backend, never a root
shell. ZIP uses the standard library. RAR uses the signed distribution packages
`python3-rarfile` (metadata) and `unrar` (content/CRC); no pip or downloaded executable.
`master_rar.py` runs in a separate process with 192 MiB address-space/CPU limits,
bounded metadata output, a 30-second metadata deadline and process-group cancellation.
The service's existing systemd memory/CPU/task limits still apply. RAR volumes are
copied through validated descriptors into a private snapshot (compressed set <=2 GiB).
Only `unrar p` stdout is consumed; unrar never chooses/writes output paths.
The parent validates paths/types, opens new files without following links and
checks sizes/CRC before publishing. Password prompts, shell arguments, link/redirection
members and wildcard member names are refused. The page may close without stopping the job.
The Files bar shows state, server message and cancel; the result appears as a
toast and a Günlük entry. Byte/entry counters are available in the API only. A
destination identity change or source file change fails closed; this is not a
snapshot of a concurrently changing tree.

### Storage and safety

`FILES_ARCHIVE_DIR` in `config/defaults.env` names the private workspace below
`SERVER_ROOT` (currently `/srv/.arsiv`, mode 0700). `jobs.json` is mode 0600;
the installer permission sweep excludes this tree. It stores at most 20 jobs,
not file backups. Private job staging is not exposed by the file API. A complete
result is atomically renamed into place with no replacement on Linux. Failure
or cancellation removes staging. Restart marks unfinished jobs interrupted and
cleans their staging; it does not resume them. A crash between publication and
history persistence can leave a valid result without a success record: inspect
the destination before retrying. History can outlive an output manually removed
by the user.

Descriptor-based access refuses traversal, absolute/ambiguous paths, symlinks,
hard-linked regular files, device files and cross-device children. Internal paths
are reserved. Duplicate/unsafe archive entries fail the job, independently of the
outer-name collision policy. Job history bounds path and name lengths. Files
and DAV still share the downloads UID: this is not isolation from a trusted
host administrator or another process running as that UID.

### API

All endpoints retain the file backend's allowed-Host and `X-Konsol: 1` gates.

| Endpoint | Contract |
|---|---|
| `GET /api/archives` | `{items, limits}` including persisted terminal jobs and `limits.formats` |
| `POST /api/archives` | `{operation, path, names, target, name, nested, layers, conflict}`; relative paths; returns 202 `{job}` |
| `POST /api/archives/cancel` | `{id}`; cooperative cancellation, returns 202 |

`operation` is `zip` or `unzip` (`unzip` also opens RAR); `conflict` is `rename`,
`skip` or `stop`. `nested` and `layers` are optional and the UI never sends them:
when both are omitted, extraction is recursive to the five-layer maximum and the
job records `automatic:true`. When given, they limit nesting to the caller's
depth and the job reports inner archives left packed.
No operation accepts shell arguments, absolute paths or executable plugins.

## Verification

[`../tests/README.md`](../tests/README.md) lists the unit, browser and live
archive tests; actual runs are recorded in `../SESSION.md`. A fresh Ubuntu
install, native Finder/Infuse clients and recipient ACLs need separate acceptance.
