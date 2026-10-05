# Container management proposal

Status: accepted by the user; implementation authorized, 2026-10-03. Baseline: `5b91f65`, v2-189.
This is the accepted design and implementation plan; delivery is in progress.
Astra owns the technical design and integration; Opus owns the companion visual prototype.

## Outcome and scope

Move Containers out of Settings into the main sidebar, after App Store. Build one integrated
Podman management page using the existing Konsol sign-in and visual language. The proposed
scope is this server's rootful Podman environment, including App Store applications and
containers created by the operator. Docker, another management server, and multi-host orchestration
are not required for this outcome.

Everyday management should include creating a container from an image; start, stop, restart and
remove; editing ports, mounts, environment and startup/resource settings; inspecting status,
resource use and logs; and managing the images, named volumes and networks those containers use.
An existing container must not become impossible to start merely because it disappeared from
`podman ps -a` after its systemd service stopped.

## Current constraints discovered in the source

- `console/konteynerler.js` and `panel/master_containers.py` implement read-only list/detail/log
  views. `master-panel` exposes only GET routes for them. The new feature requires a real write
  contract, not buttons around the existing view.
- qBittorrent is a systemd/Quadlet App Store package. `master-modul durdur` stops its service,
  removes the generated source `.container` file and records `durduruldu`; starting places it
  again. Management must include module registry and saved definitions, not only live Podman data.
- qBittorrent uses host networking, a protected profile mount and same-path download mounts.
  Its selected download directory also exists in native preferences and package validation.
  Changing a mount alone does not change where the application saves files.
- `paket_konteyner_koy` copies the package definition on start/reapply. Arbitrary edits to generated
  files would be lost. User choices need a persistent source consumed by start, restart and installer.
- The backend is sandboxed. Mutations should use the existing bounded external-worker pattern,
  not remove the backend sandbox or expose a generic Podman socket/command endpoint.
- Existing firewall rules were designed around host networking. Bridge networking and published
  ports require explicit integration and reachability tests; binding a port is not proof of isolation.

## Proposed page

Main navigation: Overview, Files, App Store, **Containers**, installed applications, Settings.
The old `#/ayarlar/konteynerler[/name]` links redirect to `#/konteynerler[/name]`.

The page has Containers, Images, Volumes and Networks tabs (Turkish labels: Konteynerler, İmajlar,
Birimler, Ağlar; explain "volume" in the Birimler description). Containers is the default. Its compact
summary shows running/stopped/unhealthy counts and storage, followed by search, state filters and
**New container**. The table shows name/image, status/health, CPU/RAM, ports and management source.
Each row offers a state-dependent start/stop action and an overflow menu for restart, edit and remove.
At phone width, rows become compact cards with the same actions.

Opening a container shows a full detail page with a stable link and sections for Overview, Ports and network,
Volumes, Environment, Startup and limits, and Logs. Avoid a dense dashboard of unrelated charts.
Settings are edited as a draft. Polling must not overwrite the draft or steal keyboard focus.

Creation and editing use the same side sheet, full width on phones, with Edit → Review → Apply steps.
Port rows contain access scope, host port, container port
and TCP/UDP. Mount rows contain named volume or server folder, container path and read-only/read-write.
Environment values marked secret stay masked: unchanged secrets are preserved without being sent
back to the browser. New images use a fully qualified reference; a tag is resolved to its actual digest
when pulled, and updates are explicit operator actions.

## One management path for each container

| Management source | Lifecycle | Editing and removal |
| --- | --- | --- |
| App Store | Existing module engine, extended with a real restart operation | A package adapter applies declared settings; removing the application also updates App Store, tiles and publication records |
| Created in Konsol | Saved definition rendered to a Quadlet, operated through systemd | Full supported form; recreate when required; named volumes remain separate resources |
| Created elsewhere | Discover actual systemd/Podman ownership first; confirmed standalone containers allow start/stop/restart | Confirmed standalone containers allow explicit removal or adoption; unknown controllers remain read-only, with the reason beside the control |

Use an explicit management badge and explain a restriction beside the affected control. Do not hide
external containers or claim unsupported Kubernetes/Compose/rootless resources are fully editable.
Adoption must present the imported settings, omitted/unsupported fields and a complete change preview.
An existing public binding must not silently become private or be republished: the operator selects its
intended scope in that preview. Unsupported options block adoption before any stop or replacement.
The first release targets ordinary standalone containers; multi-host and other users' rootless stores
remain outside this proposal. An interactive terminal and Compose editor can follow after this core.

App Store and Containers must share the same lifecycle status and lock. A stop from either page stays
stopped across reboot and installer rerun. A restart is one locked operation, not two browser requests.
Deleting an App Store container uses package removal; it must not leave a broken installed tile behind.
For managed definitions, persist an explicit manual-stop state separately from the auto-start preference.
Manual stop takes precedence; the Startup section shows the effective outcome ("Kapalı · siz durdurdunuz")
instead of an unconditional "Evet". Start clears that state; auto-start off still means a later reboot
does not start the container. Restarts are offered for running containers; stopped ones offer Start.
External controllers cannot receive a reboot-persistence promise. The overview's existing two icon
actions remain Settings and Start/Stop; Restart belongs in the container details/overflow menu.

## Port and volume changes

Treat port, mount, network and image changes as **Apply and recreate**. The confirmation lists the
actual changed settings and the expected interruption. A stopped container remains stopped after
saving, unless the user explicitly asks to start it. CPU/memory changes can use supported live updates,
but the saved definition must reflect the same values.

This is an implementation choice based on Podman's available update surface: `podman update` covers
resource limits and health checks, while Quadlet definitions carry publish and mount settings.
See [Podman update 5.4.2](https://docs.podman.io/en/v5.4.2/markdown/podman-update.1.html) and
[Quadlet 5.4.2](https://docs.podman.io/en/v5.4.2/markdown/podman-systemd.unit.5.html).

For a host-network application such as qBittorrent, show the real application listener rather than an
invented host-to-container mapping. Its WebUI port change must update the native preference, image
environment, service definition, Caddy upstream and health/publication checks from one effective value.
Its download mount editor must use the same folder setting as the application's settings dialog.
Protected application mounts are identified; relocating profile data is a separate explicit operation,
not an accidental consequence of changing a path field.

Changing a mount does not copy files. The form distinguishes changing a mapping from moving data.
Removing a container normally retains named volumes and host directories; deleting an unused named
volume is a separate explicit action showing its references. A mount operation never recursively
deletes an arbitrary host directory. Recreating discards the container's writable layer, so the preview
identifies that consequence and requires persistent data to be mounted.
The App Store's existing optional package-profile cleanup remains a package operation; it is not
generic permission to delete named volumes or host folders.

Port validation checks numeric ranges, protocol, duplicate bindings, existing listeners, planned
bindings and project-reserved ports. Defaults are private. Access options distinguish this server,
Tailscale and explicitly requested public exposure. Test IPv4/IPv6 and Netavark forwarding as well as
host INPUT; preserve Tailscale and WireGuard isolation. A bridge port must not silently expose a service
to WAN. Preserve existing package publication policy for App Store applications.

### Network decisions required by the implementation

Bridge port mapping stays in the target scope; a host-only first batch does not satisfy the complete
request. Before exposing bridge mutations, verify Netavark's firewall driver on each supported OS,
its NAT/forwarding chains and their interaction with `master-firewall` reload and boot ordering.
Manage only project-owned policy chains; do not flush or recreate Netavark, Tailscale or other software's
chains. Prove allowed and denied paths from outside the server, including VPN-to-bridge access.

New bindings start private; Tailscale is an explicit selection. A Tailscale binding needs the actual
address and a ready interface, with bounded startup retry. Missing addresses produce an actionable
failure rather than falling back to all interfaces. Integrate address changes with the existing
tailnet refresh path; do not add continuous reconciliation.

App Store web publication continues through Caddy and the existing publication policy. Generic raw
public TCP/UDP mappings are an advanced, per-port opt-in, delivered only after the network checks above.
Explain that these bypass Konsol sign-in/Caddy TLS and rely on the container application's own protocol
and authentication. An arbitrary image does not inherit qBittorrent's approved web-publication behavior.
Do not automatically add arbitrary Caddy upstreams or public DNS records.

## Backend shape

- Extend read views with a stable management ID, source, allowed actions, effective configuration,
  desired startup state and observed runtime state. Union saved definitions/module registry with
  Podman inventory. Container IDs can change on recreation; UI identity must not.
- Keep the name immutable in the initial editor and reserve App Store/system names. Assign a stable
  management ID independently. Package capabilities declare editable fields, protected mounts and
  adapter actions through package metadata; do not hard-code qBittorrent rules into the base UI.
- Add a dedicated container worker and allowlisted API operations. Validate structured input before
  any mutation; use argv rather than a user-provided shell command. Secrets travel on stdin/private
  files and never in process arguments, logs or generic inspect responses.
- New generic definitions use bridge networking with no privileged mode, device passthrough or added
  capabilities in the initial form. Bind sources use an explicit allowed data-root policy, resolved
  server-side against symlinks and protected application/share/trash paths; client validation is only
  a convenience. App Store adapters handle their declared protected paths separately.
- Store operator definitions outside generated runtime files, with paths declared once in defaults.
  Proposed area: `STATE_DIR/containers/`. Resolve package defaults plus supported user overrides into
  an effective definition used by rendering, API readers and package adapters.
- Render only through explicit operations. Systemd handles service restart policy; do not add a
  background reconciliation engine, automatic image update or an additional control daemon.
- Long operations return an operation ID and progress. A per-container lock plus the existing
  installer/module lock order prevents App Store and container-manager races. Reject stale revision
  edits with a clear refresh/review message, and prevent duplicate submissions.
- Validate image availability, mappings and generated configuration before stopping the service.
  On failure show the failed step and actual running state; never report success because a process
  merely started. Persist enough operation state for diagnosis after a disconnect.
- Show existing health checks read-only initially. Logs use a bounded tail and manual refresh/search;
  avoid an unbounded stream. Sample current CPU/RAM approximately every ten seconds while visible.
  Preserve known-secret redaction server-side; a container's arbitrary output is not guaranteed free
  of sensitive text, so do not describe its logs as universally sanitized.
- No server-side installation backup workflow on nrm, per the user's rule. The proposal does not
  promise application-data rollback. Failure recovery must not silently pretend data was restored.

## Delivery batches and shared ownership

| Batch | Astra implements | Opus implements | Exit evidence |
| --- | --- | --- | --- |
| 1. Navigation and lifecycle | Inventory union, ownership dispatch, restart/remove workers, API/locking tests | Sidebar migration, list/detail/actions, old-link redirect, browser fixtures | The same qBittorrent stops/starts/restarts/removes consistently from either page; stopped definitions remain visible |
| 2. Configuration and creation | Persistent definitions, recreation, port/mount validation, App Store adapter and firewall integration | Shared create/edit forms, change preview, progress/errors and mobile layouts | Create a container, change a real port and mount, verify reachability/data location, preserve choices across reboot and rerun |
| 3. Complete daily management | Image/volume/network operations, resource statistics and operational hardening | Resource tabs, logs/search, empty/failure states and final usability | Image pull/update/removal, volume/network create/remove and resource-in-use refusals; complete user journey on nrm |

Files are partitioned before each batch: Astra owns backend/worker/package/firewall files and Python/
Linux tests; Opus owns console HTML/JS/CSS and browser fixtures. Each reviews the other's changes.
Astra integrates the candidate and runs live tests; Opus does not run simultaneous nrm tests.
The planning task made no runtime/server changes. The user subsequently accepted the prototype and
requested implementation. The shared [API interface](container-manager-api.md) coordinates that work;
existing nrm test-host authorization applies to integration and acceptance.

## Acceptance evidence

Exercise navigation, lifecycle, cancellation, busy/double click and failures through the real UI.
On nrm test real Podman/systemd operations, the App Store relationship, a host-network app and a
bridge test app, port conflicts, read-only mounts, stopped edits, failed image pull/start and stale
concurrent edits. Check persistence after restart/reboot/installer rerun. Confirm private/public
network policy externally, secret masking and safe volume deletion. Use scratch installer inputs
and no installation backups. Report any unsupported controller or OS/version instead of implying
universal Portainer parity.
Repeat relevant worker/Quadlet/network checks on Debian 13 and Ubuntu 24.04/26.04. Detect the installed
Podman/Netavark capabilities; the 5.4.2 reference does not establish compatibility with every distro
package. Installer reruns must retain user definitions and overrides outside generated package files.

The visual reference is Portainer's practical grouping of container configuration fields, especially
volume type/path/access and startup controls; the resulting page remains part of Konsol.
See [Portainer advanced container settings](https://docs.portainer.io/user/docker/containers/advanced).

## Visual proposal and review evidence

[Open the interactive prototype](konsol-konteynerler-v01.html). Opus authored the frozen visual reference;
Astra reviewed it independently and owns this integrated plan. It contains sample data only and makes
no server requests. The demo footer's "v2-190" is illustrative, not an exported or installed release.

Selected direction: compact list/cards, management-source badges, a full detail page, and a side-sheet
draft/review/apply flow. Astra's independent Chromium check passed desktop and 390 px dark layouts,
qBittorrent host-listener change preview, stopped-container edit preview with Start unchecked, and
App Store removal consequences with optional data removal unchecked. No page errors or HTTP requests
were observed. Screenshots were inspected; these checks verify simulated interactions, not Podman.
Opus also reports a broader 19-step desktop/mobile demo check including creation, adoption and logs.

The frozen prototype deliberately remains a proposal. This plan takes precedence where review found
differences; implementation must not copy these simulation shortcuts:

| Prototype limitation | Chosen implementation behavior |
| --- | --- |
| Container removal offers checkboxes to delete exclusive named volumes | Keep named volumes; delete them explicitly in Birimler after checking references |
| Stop can leave Startup showing "Evet" | Display effective startup state, including the persistent manual-stop override |
| Changing the qBittorrent listener does not update the demo's separate `WEBUI_PORT` row | One effective port updates native preferences, environment, service, Caddy and checks |
| External-container prose says Start/Stop only, while menus also offer restart/removal | Derive allowed actions from proven ownership; unknown controllers stay read-only |
| Adoption automatically converts a public binding to private | Require an explicit access choice in the adoption preview |
| Recreate preview estimates approximately ten seconds | Show measured progress and a possible interruption; no fixed-duration promise |
| Volume/network creation and parts of image updating are only notices | Build complete forms/operations and verify them in batch 3 |

No production feature, firewall isolation, real image pull, volume operation or deployment was tested
as part of this planning task. Real service behavior remains the v2-189 baseline until implementation.
