# Container manager implementation interface

Status: implemented in v2-190 and live-verified on nrm (Debian 13), 2026-10-03. The user accepted the
[proposal](konsol-konteynerler-v01.md) and requested implementation. Baseline `5b91f65` / v2-189.
This document records the backend/console interface; exact acceptance evidence and platform limits are in `../../SESSION.md`.

## Ownership

Astra owns backend routing/read models, installer/defaults/publication integration, technical decisions
and live acceptance. Its bounded helper assignments own the new worker/config module, package adapter,
and network-policy helper in separate files. Opus owns console HTML/JS/CSS and browser tests.
No two agents edit the same file. No automatic commit or push. Only Astra operates nrm.

## Read routes

All routes keep the existing Konsol Host/CSRF/channel/session checks and no-store responses.
Base: `/api/konsol/konteynerler`.

- `GET /liste`: `{read_at,runtime,containers,images,volumes,networks,storage}`. Existing runtime
  `{version,ok,error}` and storage `{images,containers,size}` remain. Collection failures are explicit;
  a failed resource read must not look like an empty collection.
- `GET /ayrinti?ad=NAME`: the existing container detail, extended as below. A saved stopped definition
  or installed stopped application remains readable without a live Podman container.
- `GET /gunluk?ad=NAME&satir=200`: existing `{name,lines,truncated,masked}`; allowed tails 100/200/500/1000.
  Managed stopped containers use their unit journal where the runtime container is absent.
- `GET /islem?id=UUID`: operation state. UUID is 32 lowercase hexadecimal characters.
- `GET /guncellemeler[?yenile=1]` (DD-214): `{checked_at,items:{NAME:{state,channel,error}},cached}`;
  `state` is `guncel`, `var`, `sabit` or `denetlenemedi`. Registry manifests only, cached six hours,
  forced at most once a minute. Rows also carry the cached `update` object (or `null`).

Every container row retains `name,image,state,status,unit,network,ports,mounts,created,started,
exit_code,restarts`. Additional fields:

```json
{
  "management_id": "konsol:example",
  "source": "konsol",
  "module_id": null,
  "revision": "opaque-revision",
  "live": true,
  "actions": ["stop", "restart", "save", "remove"],
  "restricted_reason": "",
  "health": "healthy",
  "cpu_percent": 1.2,
  "memory_bytes": 31457280,
  "busy": null
}
```

`source` is `appstore`, `konsol` or `external`. Identity is stable across recreation. Do not infer
permission from source/state in the browser: honor `actions` and show `restricted_reason`.
`id` remains the observed runtime ID. `state` uses running/stopped/exited/unknown; health is separate.
Unknown measurements are null, not zero. Busy is an operation ID or null.
`listening` (DD-215) is null except for a running host-network container, where it lists the sockets its
processes listen on: `[{address, port, protocol: "tcp"|"udp", scope: "all"|"wan"|"tailscale"|"other"|"local"}]`
(TCP LISTEN and unconnected bound UDP from `/proc`, IPv6 link-local omitted); null there means unreadable.
`scope` is the kind of bound address, not reachability.
Existing port rows use `host_ip,host_port,container_port,protocol` plus (DD-217) `scope`: `local`,
`tailscale`, `public` (unspecified or the server's WAN address) or `other`; list `mounts` is a count,
detail `mounts` is the existing array with `type,source,destination,rw,name`.

Details additionally return `config`, `revision`, `editable`, `protected_mounts` and
`effective_autostart`. For an App Store adapter the initial config is
`{listener_port:62947,peer_port:63851,save:"/srv/downloads"}` (DD-219), with
`editable:["listener_port","peer_port","save"]`. `peer_port` is optional for an adapter (DD-221): the
page shows the field only when the adapter declares it, and sends it only then; an adapter treats an
omitted `peer_port` as unchanged. The UI labels this as an application listener, not a bridge mapping. Account settings remain in the
existing application settings form. Required package mounts are read-only in this generic editor.

Generic managed config:

```json
{
  "name": "example",
  "image": "docker.io/library/nginx@sha256:...",
  "image_ref": "docker.io/library/nginx:alpine",
  "network": "konsol",
  "ports": [{"scope":"local","host_port":8088,"container_port":80,"protocol":"tcp","public_ack":false}],
  "mounts": [{"type":"volume","source":"example-data","destination":"/data","read_only":false}],
  "environment": [{"name":"TZ","value":"Europe/Istanbul","secret":false},
                  {"name":"API_TOKEN","secret":true,"present":true}],
  "command": [],
  "autostart": true,
  "manual_stop": false,
  "restart": "on-failure",
  "cpus": "",
  "memory": "",
  "user": "downloads"
}
```

Name is immutable. Image references must be fully qualified. Mount types are bind/volume; scope is
local/tailscale/public. A new public binding requires explicit `public_ack:true`. Preserve secret
rows by name: omitted/blank value keeps the old secret; never put a placeholder back as the value.
Removing the environment row removes it. `manual_stop` is server-controlled and displayed via effective
startup state. A stopped save stays stopped unless `start:true` is explicitly selected.
`network:"bridge"` is the logical managed default: the worker creates the configured `konsol`
bridge on first use. Offer it even on an empty host. Other selectable bridge networks must have
`managed:true`; the runtime's default `podman` network is not an editable managed network.
App Store adapters preserve stopped state; their editor does not offer the generic start-after-save
checkbox. Every generic save currently rerenders/recreates, including resource/startup changes;
the preview must disclose that running containers are interrupted.
Optional `pids_limit` is a string: empty uses the runtime default, `-1` is unlimited and a
positive integer is an explicit process limit. Adoption preserves the inspected limit; omission
on later edits preserves the saved value, including clients without a process-limit control.
Likewise, adoption preserves `ulimits:[{name,soft,hard}]` and `stop_signal` (a validated signal
string). These optional fields remain unchanged when older editors omit them; they are not raw
Podman arguments and cannot add arbitrary unit directives.
`user` (DD-227) is `downloads` (the Files account: `User`/`Group` from `DOWNLOADS_UID`/`GID`,
`DropCapability=all`, `--umask=0002`) or `image` (the image's own account, often root). A writable
bind requires `downloads` (400 otherwise, before any pull or stop). Omitted on create means
`downloads`; omitted on a later save keeps the stored value, and a definition stored before DD-227
counts as `image`. Adoption maps an inspected user equal to the Files uid (with or without its gid)
to `downloads`; any other user that differs from the image is unsupported. Details add `user`, the
running process's `Config.User` (empty = the image default).

Resource rows preserve current image fields `name,size,created` and add `id,used_by,managed,pinned`.
Volume rows: `name,driver,size,used_by,managed`; networks: `name,id,driver,subnets,used_by,managed,internal`.
Resources in use cannot be deleted. Package-pinned images cannot be replaced/deleted through generic
controls. Named volume deletion is separate from container removal; no arbitrary folder deletion.

## Write and operation routes

`POST /islem` accepts `{action,...payload}`. Supported actions and payloads:

| Action | Payload |
| --- | --- |
| start, stop, restart, remove | `{name,revision}`; App Store remove may also use explicit `with_data:true` for its existing package-profile cleanup |
| create | `{config,start}` |
| save | `{name,revision,config,start:false}`; package config uses adapter fields above |
| adopt preview | `{name,preview:true}` |
| adopt apply | `{name,preview_fingerprint,config,start,confirm:true}` |
| image-pull | `{image:"fully.qualified/repository:tag"}` |
| image-remove | `{image:"sha256:..."}` |
| image-update | `{name,revision}`; explicit pull/compare/recreate for a managed container, or (DD-214) the package adapter's digest move for an App Store app that declares a channel; never automatic |
| volume-create, volume-remove | `{name}` |
| network-create | `{name,subnet,internal:false}`; bridge only, no privileged host networking |
| network-remove | `{name}` |

Accepted writes return HTTP 202 `{id,action,name,state:"running"}`; poll `GET /islem?id=...` at roughly
one second while active, back off when hidden. A page reload can reconnect using the operation ID.
Terminal operation: `{id,action,name,state:"done"|"failed",step,updated_at,result?,error?,status?}`.
The result of adopt preview is `{preview:{config,unsupported,fingerprint,requires_scope_review:true}}`;
no mutation occurs before the explicit apply request. Show all changed access scopes before applying.
For image updates present explicit intent and possible recreation before submitting.

Input rejection uses HTTP 400, unavailable target 404, stale revision/busy/unsupported ownership 409,
and execution/inventory failure 502/503, with `{error:"Turkish explanation"}`. A worker failure may
arrive as a terminal failed operation with `status`; success is not inferred from the initial 202.
Requests carry no arbitrary command strings, filesystem paths for job output or executable names.
Audit/operation logs contain the action/target/result, never submitted environment values or passwords.

## UI contract

Main sidebar route `#/konteynerler[/NAME]`, labelled "Podman" since v2-194 (DD-216); old Settings deep links redirect. Remove only the old
container Settings tab. The four resource tabs, mobile cards and detail/editor follow the accepted
prototype, with the corrected semantics in the plan. Drafts survive polling; late responses cannot
overwrite a newer editor. Disabled/busy actions keep accessible names and keyboard focus.
Lifecycle changes refresh App Store and overview state through existing shared refresh behavior.

## Integration notes

Root worker: `python3 master_container_worker.py --state PATH --operation UUID ACTION`, JSON stdin.
Definitions live under `KONTEYNER_STATE_DIR/definitions/`, operations under `operations/`, mode 0600.
Package adapter: manifest `PAKET_KONTEYNER_YONETIM`, function `container_config(env)` and existing worker
CLI `konteyner-ayar`. App lifecycle routes through the module engine (restart `yeniden-baslat`).
DD-214: an App Store package that also declares `PAKET_IMAJ_KANAL` offers `image-update`, handled by
the adapter CLI `konteyner-guncelle` with `{revision}` (870 s bound inside the 900 s transient unit).
Netavark retains NAT; a project-owned nftables guard restricts ingress to managed bridge interfaces.
Do not publish bridge ports until the worker has installed the matching policy.
