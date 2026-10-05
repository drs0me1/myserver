# Files v09 — folder navigation and independent WebDAV shares

Status: implemented as v2-128 / DD-158, 2026-09-25. The original conversation
preview remains sample-only and frozen. Actual behavior, deviations from the
tentative implementation direction, protocol limits and acceptance scope are
recorded in [folder-shares.md](../folder-shares.md) and `Data/SESSION.md`.
The proposal below is retained as the design rationale, not a test certificate.

## Proposed interaction

- Default to a list: folder name/content summary, sharing state, Details action.
  Folder name opens the folder; Details selects it without navigating. Keep
  breadcrumbs, current-folder search, new-folder creation, and a card alternative.
- Show the selected folder's path, account, access and address in a right-hand
  panel; stack it below on narrow screens. Compare compact/comfortable density
  and right/below panel placement before implementing.
- Keep a separate WebDAV shares tab, with one row per folder: username, access,
  expiration, active/paused state, copy address and manage. Never show passwords
  in rows. Pausing preserves the URL/account; removing a share never deletes data.
- Create/edit form: independent username, password, read-only/read-write,
  lifetime. Default read-only; password omitted on edit means preserve it.
  New passwords are entered or generated once and not subsequently retrievable.
- Read-only means browse, stream and download. Read-write includes create,
  upload, overwrite, rename and delete; require an explicit acknowledgement.
  Do not imply that remote WebDAV deletes use Konsol's trash. An upload-only
  preset or per-operation permissions require separate enforcement and are
  not part of this initial two-preset proposal.
- Do not expose the server root, internal share registry, trash, configuration,
  symbolic links or active incomplete-download directory. Avoid overlapping
  parent/child shares by default: a broader parent grant would defeat a narrower
  child's restriction. Surface this conflict, not silently merge permissions.

## Why the existing server needs more than a UI change

Current code (`modules/paylasim/master-paylasim.service`,
`files-panel/master-files-panel:share_add`, `scripts/master-modul`) publishes
symlinks under one shared root through a single read-only rclone service and a
single generated account. Adding usernames to that shared htpasswd file would
not by itself restrict each account to a different folder.

Proposed implementation direction, subject to security and client trials:

1. Keep one Tailscale-facing WebDAV port (`SHARE_PORT`, currently 61010).
   Assign an opaque, stable path per share: `http://<tailscale-ip>:<port>/s/<id>/`.
   A folder rename should not rename the public ID; removing/replacing its
   filesystem target must fail closed instead of publishing unrelated contents.
2. Reuse the pinned rclone binary with a bounded per-share service instance:
   one validated folder root, account and read-only/read-write policy per
   instance. Caddy routes the share's URL to a private listener or Unix socket.
   Decide authentication ownership explicitly: rclone documents that Unix-socket
   mode has no HTTP authentication, so that variant must authenticate in Caddy.
   Never keep a shared symlink tree with `--copy-links` as the writable root.
3. Use a root-owned share registry and password hashes outside served directories,
   fixed worker verbs, no passwords in command arguments/logs, and service
   credentials for loading secrets. Restrict filesystem visibility to the
   selected folder; read-write sandbox exceptions only for that folder. Validate
   against path races, encoded traversal, symlinks, hard links and WebDAV
   `Destination`/MOVE/COPY before claiming isolation.
4. Reuse fixed module lifecycle and atomic updates, with rollback on failure.
   Stopped modules stay stopped. Expiry must stop access even if nobody opens the
   console: the current list-triggered cleanup is insufficient for that promise.
5. Migrate only with an explicit operator choice: the current shared account
   can see all legacy shares. Do not retain that broader route as an unnoticed
   bypass; do not silently invalidate existing Infuse credentials or links.

The sample form uses distinct usernames to reduce account ambiguity. Exact-path
routes and per-share authentication realms still need real-client testing:
some WebDAV clients cache one credential set per host. If a required client
cannot mount multiple accounts on one IP/port, evaluate separate tailnet ports
as an explicit compatibility option, not a silent network-surface expansion.

## Mandatory network boundary

Konsol currently has no login and grants administration to reachable tailnet
clients. Folder passwords cannot protect data from a recipient who can also
open the management panel. Before multi-recipient use, restrict recipient
identities to the WebDAV port and keep Konsol/SSH admin-only in Tailscale grants
or ACLs. Existing broad allow rules must be reviewed; adding a narrow grant
does not override a broader allow. Account policy changes require the operator
and must not be performed implicitly by the installer or this design preview.

The raw-IP HTTP address travels inside Tailscale, but some native WebDAV clients
still require HTTPS for Basic authentication. Do not recommend weakening client
security settings as the default fix; validate target clients before promising
support. A compatible HTTPS hostname is a separate choice if necessary.

## Acceptance before implementation is considered complete

- Two accounts can mount two folders simultaneously; A cannot list, read, write,
  MOVE/COPY into, or infer B's folder via alternative URLs or Destination headers.
- Read-only requests cannot modify data; read-write changes remain inside the
  allowed folder; interrupted writes never reveal a partial replacement.
- Pausing, expiry, deletion and password rotation revoke new access as advertised;
  existing-stream behavior is defined and tested, not claimed instant by default.
- Path traversal, symlink/hard-link escapes, overlapping roots, rename, target
  removal/recreation, volume unmount and service restart fail closed.
- Secret files/arguments/logs and browser storage reveal no plaintext password.
- Installer rerun and reboot preserve share IDs, hashes, policies and paused state
  on Debian/Ubuntu; file-manager upload/move/trash functionality does not regress.
- Tailnet recipients reach only their permitted WebDAV port, not Konsol/SSH.
- Infuse, macOS Finder and the operator's other required clients pass multi-account
  mounting, Unicode paths, large files, range streaming and read/write tests.

## References

- [rclone serve webdav](https://rclone.org/commands/rclone_serve_webdav/):
  read/write serving, htpasswd, base URLs, Unix-socket authentication behavior,
  symlink handling and Windows Basic-auth/HTTPS limitation.
- [Tailscale shared machines and access policies](https://tailscale.com/docs/features/sharing):
  shared-machine access can be restricted to ports; broad wildcard grants matter.
- [Tailscale access control](https://tailscale.com/docs/features/access-control).
