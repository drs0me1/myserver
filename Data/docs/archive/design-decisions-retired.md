# Retired design decisions

These entries describe removed or replaced behaviour and are kept for history.
They were moved verbatim, in their original order, from
[`../design-decisions.md`](../design-decisions.md), which holds the current
rules; [`../decisions-index.md`](../decisions-index.md) gives each entry's status
and successor. Paths, line numbers and services named here may no longer exist.

### DD-2: Canonical-bundle SHA256 manifest for reconcile

- **Decision:** Managed config files (state, dnsmasq, Caddy) are copied
  into `/usr/local/share/master-stack/` alongside a `SHA256SUMS` manifest;
  reconcile compares live files against these canonical copies rather than
  re-generating and diffing content on every check.
- **Context:** `install.sh:2235-2268` (`canonical_bundle_ok`).
- **Rationale:** A cheap, atomic-manifest-based comparison is faster than
  re-deriving expected file content every 5 minutes, and it gives a single
  place (the manifest) to validate that the *whole* canonical bundle is
  self-consistent before trusting any individual file comparison.
- **Trade-off:** Any manual edit to the live config files (not the
  canonical copies) is treated as drift and reverted — see DD-3.

### DD-3: Reconcile reverts operator edits instead of merging them

- **Decision:** When live firewall/dnsmasq/Caddy config differs from the
  canonical copy, reconcile restores the canonical version rather than
  attempting to detect or preserve manual changes.
- **Rationale:** Merging arbitrary manual edits safely is not tractable
  for this kind of security-sensitive configuration; a deterministic
  "known-good state always wins" model is simpler to reason about and
  guarantees the fail-closed security posture can't erode over time.
- **Trade-off:** Operators cannot make ad hoc persistent changes without
  either editing `install.sh` and re-running it, or (not currently
  implemented) using an explicit opt-out. Flagged as **H2** in
  `SECURITY_REVIEW.md` for better operator-facing documentation of this
  behavior.

### DD-4: `PartOf` fate-sharing between core daemons and managed units

- **Decision:** `docker-tailscale-fw.service`, `master-compose.service`,
  and (optionally) `caddy.service` declare `PartOf=docker.service` and/or
  `PartOf=tailscaled.service`.
- **Rationale:** If the underlying daemon (Docker or Tailscale) is
  stopped, the firewall/Compose/Caddy state built on top of it is no
  longer meaningful and should not be left running against a torn-down
  dependency.
- **Trade-off:** A routine restart of `docker` or `tailscaled` cascades
  into stopping and restarting the entire dependent stack — a real
  operational surprise, flagged as **H3** in `SECURITY_REVIEW.md`.

### DD-5: Reconcile avoids restarting core daemons synchronously

- **Decision:** `master-network-reconcile.service` does not sit in the
  `After=` graph of the units it manages, and never issues a synchronous
  `systemctl restart docker`/`tailscaled` from within its own execution.
- **Context:** Comment at `install.sh:3462-3467`.
- **Rationale:** Doing so from inside a unit that is itself triggered via
  `OnFailure=` from those same units' dependents would risk a systemd
  self-ordering wait/cycle. Core daemon recovery is left to their own
  built-in restart policies; reconcile only acts once they're confirmed
  active.

### DD-7: wg-easy admin/peer setup is manual (superseded, 2026-07-27)

- **Original decision (r8 and earlier):** First-run wg-easy admin
  credentials were supplied via a root-only `/run`-based env file and a
  Compose override (`restart: "no"`), then the container was
  force-recreated without that override once the bootstrap was verified,
  so the secret never persisted in the container's running environment.
  This closed the credential-exposure window as tightly as the
  Compose/Docker model allowed, but meant a script failure in the narrow
  window between database creation and the bootstrap marker being written
  left a hard-to-recover dead-end state (**M6** in `SECURITY_REVIEW.md`).
- **New decision (2026-07-27):** At the user's explicit request, the
  entire unattended-bootstrap subsystem was removed. `install.sh` now only
  provisions the wg-easy container and its infrastructure (port, volumes,
  network, firewall rules); the admin account is created manually through
  wg-easy's own web UI on first access — the same model already used for
  Portainer and SFTPGo. See `install.sh` Stage 0 (no more admin prompt),
  Stage 5 (no more bootstrap-apply-verify-scrub sequence), and Stage 7
  (the postcondition is now informational only, feeding the existing
  "complete setup manually" message in the final summary rather than
  failing the install).
- **Rationale:** The user considers wg-easy's admin credentials out of
  scope for the installer to manage at all — consistent with how every
  other service's admin account already works. This also deletes an
  entire secret-handling subsystem (bootstrap env files, container secret
  scrubbing, marker-gated rerun safety), directly resolving **M6** and
  reducing the script by 248 lines.
- **Trade-off:** The removed marker also recorded which public IP was
  baked into already-configured wg-easy peer configs. Without it,
  `state.env`'s `WG_ENDPOINT_HOST` is simply overwritten with the current
  public IPv4 on every `install.sh` run (see `install.sh` Stage 4). The
  reconcile timer still detects a public-IP change that happens *between*
  its own 5-minute checks, but a change that happens between two separate
  `install.sh` reruns is no longer specifically flagged — reconcile will
  just record the new IP as if it were always correct. Operators should
  manually verify existing peer configs after any public-IP change
  followed by a re-run of `install.sh`.

### DD-8: Docker daemon DNS hardcoded to public resolvers

- **Decision:** `/etc/docker/daemon.json`'s `dns` key is forced to
  `["1.1.1.1", "1.0.0.1"]`, merged in via `jq` so other daemon settings are
  preserved.
- **Context:** `install.sh:1014-1039`.
- **Rationale:** If Tailscale's MagicDNS/accept-dns rewrites the host's
  `resolv.conf` to `100.100.100.100`, a container on the default bridge
  that inherits it would have its DNS queries routed through the
  restrictive `FORWARD` firewall path and dropped. Forcing stable public
  resolvers for Docker avoids that failure mode independent of host DNS
  configuration.
- **Trade-off:** Host-level and container-level name resolution now follow
  two different paths on the same machine (see **L4** in
  `SECURITY_REVIEW.md`).
- **Confirmed live (2026-07-28):** on a real installed host with Tailscale
  DNS override active (`/etc/resolv.conf` → `100.100.100.100`), a
  container's own `resolv.conf` correctly showed `127.0.0.11` (Docker's
  embedded resolver) forwarding to `1.1.1.1`/`1.0.0.1`, and
  `nslookup ... 1.1.1.1` from inside a container succeeded with both A and
  AAAA records — the firewall does not block this egress path.

### DD-9: Everything lives in one script, deployed via heredocs

- **Decision:** All generated helper scripts (firewall, reconcile,
  recovery, IP-refresh, Caddy env) are embedded as heredocs inside
  `install.sh` rather than shipped as separate files.
- **Rationale (inferred):** Keeps the installer a single, copy-pasteable /
  curl-pipeable artifact with no additional download or packaging step.
- **Trade-off:** These embedded scripts are invisible to `shellcheck
  install.sh` / `bash -n install.sh` (see **H4** in `SECURITY_REVIEW.md`),
  and the file is large and harder to navigate/test as a result.
  `scripts/lint-embedded-scripts.sh` (static analysis) and `test/*.bats`
  (unit tests for a growing subset of pure-logic functions) now mitigate
  this without abandoning the single-file model — see `docs/testing.md`
  for what's covered and what remains open.
- **Superseded for v2 by DD-58 (2026-08-05).** This entry still describes
  `install.sh`, which is frozen and keeps the single-file model. v2
  abandons it.

### DD-10: `wg-easy`'s WireGuard kernel module is loaded independently of Tailscale (2026-07-27)

- **Superseded by DD-120 (2026-09-14):** wg-easy is removed; WireGuard runs in
  the host kernel from `kurulum/wireguard`.

- **v2 (2026-08-06):** Same policy in `install.sh` (`ensure_wg_kernel_modules`
  during Stage 4, before Compose is written) and `templates/compose.yaml`
  (`cap_add: [NET_ADMIN]` only). Host preloads `wireguard`, `ip_tables`,
  `iptable_nat`, `ip6_tables`, and `ip6table_nat`, persists them via
  `/etc/modules-load.d/wg-easy.conf`, and
  probes with a temporary `wg-easy-probe0` link. Confirmed on a live v2 host:
  without the host preload, container `wg-quick up` failed on legacy
  `ip6tables` (`Module ip6_tables not found`) even with `SYS_MODULE`, because
  `/lib/modules` is not mounted; after host `modprobe`, `wg0` and the
  healthcheck recovered. `SYS_MODULE` was therefore removed from the v2
  compose template rather than kept as a false safety net.
- **v2-73 follow-up (2026-08-30):** Ubuntu 26.04 exposed the symmetric IPv4
  failure. Its host defaults to nft-backed iptables, so the stock kernel's
  loadable `ip_tables`/`iptable_nat` modules remained unloaded. wg-easy uses
  `iptables-legacy` inside the container and cannot load host modules without
  `SYS_MODULE` plus `/lib/modules`; `wg-quick up wg0` therefore failed at its
  IPv4 NAT rule. Stage 4 now preloads and boot-persists both legacy IPv4
  modules as well. Loading them live and restarting only wg-easy recovered a
  healthy interface on the configured UDP port; v2-73's cold-reboot test
  confirmed that `systemd-modules-load` closes the boot path too, with all
  five modules present and no current-boot wg-easy iptables errors.
- **Decision:** Instead of granting `wg-easy` the `SYS_MODULE` capability
  (so it could `modprobe wireguard` itself if needed), `install.sh` now
  runs a standalone `modprobe wireguard` on the **host** in Stage 4 (next
  to the `/data/wg-easy/config` directory creation), mirroring the
  existing `modprobe tun` step already used for Tailscale in Stage 2
  (`install.sh:770-774`) — same best-effort pattern (warn on failure,
  never hard-fail the install), but a separate, independent call.
- **Context/clarification:** `tun` and `wireguard` are two unrelated
  Linux kernel modules — `tun` is a generic virtual-network-device driver
  used by many userspace VPN engines (including, very likely, Tailscale's
  own `tailscaled`, which brings up `tailscale0` via a TUN device plus its
  bundled userspace WireGuard engine, evidenced by the script's own
  `modprobe tun` — not `modprobe wireguard` — in Stage 2); `wireguard` is
  the in-kernel WireGuard protocol implementation that wg-easy's `wg0`
  interface uses instead. Loading one has no effect on, and no dependency
  relationship with, the other. All containers and the host share a
  single Linux kernel (unlike filesystem/network namespaces, a kernel
  module is not container-scoped), which is exactly why granting a
  container the ability to load one (`SYS_MODULE`) reaches further outside
  container isolation than almost anything else a container normally
  does — and why removing it here was worth the trade-off below.
- **Rationale:** Resolves **H1** in `SECURITY_REVIEW.md` — wg-easy now
  runs with only `NET_ADMIN`, no `SYS_MODULE`, no `/lib/modules` mount.
- **Hardening added:** Two follow-up questions from the user — "can we
  guarantee this," "should it persist across reboots," "does it risk
  Tailscale or other WireGuard services" — led to two more changes in the
  same Stage 4 block: (1) `/etc/modules-load.d/wg-easy.conf` makes the
  WireGuard and legacy netfilter loads persistent across reboots via
  `systemd-modules-load.service`, not just the current session; (2) a
  functional probe (`ip link add wg-easy-probe0 type wireguard` then
  delete) replaces reliance on `modprobe`'s exit code — this correctly
  detects a kernel where WireGuard is compiled in directly (`=y`, no
  loadable module at all), which would otherwise make `modprobe` report a
  false "not found" warning. No risk to Tailscale or other services: the
  kernel module is orthogonal to Tailscale's TUN + userspace path, and
  wg-easy is the only kernel-WireGuard consumer on this host — modules
  don't share state or interfere with each other once loaded.
- **Trade-off / open risk:** This assumes the host kernel can provide
  WireGuard and legacy IPv4/IPv6 netfilter support (modules or built-ins).
  That is true for the stock Debian 13 and supported Ubuntu kernels; the
  end-to-end wg-easy path is live-verified on Ubuntu 26.04. A custom kernel
  that omits those features can still leave wg-easy unhealthy because the
  preloads intentionally remain best-effort rather than aborting the whole
  stack installation.
- **Open alternative (not implemented):** Running WireGuard fully in
  userspace inside the container (e.g. `boringtun` or `wireguard-go`)
  would remove any kernel-module dependency at all — no `SYS_MODULE`
  ever, regardless of host kernel state, at a modest throughput cost
  (`boringtun` is typically ~80–90% of kernel WireGuard speed on modern
  hardware, likely immaterial for this server's use case). Not pursued
  because stock wg-easy doesn't officially support a userspace backend;
  doing this would mean forking/customizing the image, a larger effort
  than the host-modprobe approach above.

### DD-12: wg-easy's pending first-run setup must never gate Stage 7 or `--check` (2026-07-28)

- **Superseded by DD-120 (2026-09-14):** wg-easy is removed; WireGuard runs in
  the host kernel from `kurulum/wireguard`.

- **Decision:** `probe_compose_runtime()`'s `/setup`-redirect branch (the
  case where wg-easy's admin account hasn't been created yet) sets a flag
  but deliberately **not** `runtime_ok=1` —
  so it doesn't count toward `COMPOSE_RUNTIME_DRIFTED` or
  `all_critical_state_healthy()`. The other two branches in the same
  `if`/`elif` chain (WireGuard port mismatch after setup, netfilter
  drift) are unaffected and still count as real drift.
- **Context:** `SECURITY_REVIEW.md` finding **H6**, found via the second
  live Tier 3 install attempt (2026-07-28) — every fresh install failed
  at Stage 7's `master-network-reconcile --check` postcondition call
  specifically because of this branch, before this fix.
- **Rationale:** A pending wg-easy setup is the *expected* state of every
  fresh install (M6 made it fully manual) — not a real problem
  `--check`/Stage 7 should ever fail on. The periodic reconcile timer's
  own, separate `RECOVERY_FAILED` reporting (keyed directly on
  `WG_CONFIGURATION_INVALID`, further down the script) still surfaces it
  to operators via journald on every cycle until the human completes
  setup — this decision only affects the two callers of
  `all_critical_state_healthy()` (`--check` mode and the non-check mode's
  own early-exit), not operator visibility.
- **Trade-off:** None identified — this is a strict correction of an
  oversight in how **M6** interacted with a check written before it.
  Anyone extending `probe_compose_runtime()` with a new "expected,
  non-actionable" state should follow the same pattern: track it via a
  separate flag consumed by `RECOVERY_FAILED`, not `runtime_ok`.

> **Corrected 2026-08-04 (`Q1-29`).** Two details above went stale and were
> wrong as written. (1) The flag: a later revision split the pending-setup
> case into its own `WG_SETUP_PENDING`, so the `/setup` branch has not set
> `WG_CONFIGURATION_INVALID` for some time. (2) The consequence: because
> `RECOVERY_FAILED` is keyed on `WG_CONFIGURATION_INVALID` alone, the claim
> that "the periodic reconcile timer's own, separate `RECOVERY_FAILED`
> reporting still surfaces it to operators via journald on every cycle" had
> stopped being true. After the split the *only* remaining signal for a
> pending setup was a stderr line emitted from inside the probe itself.
> `Q1-29` restores the visibility this decision assumed, deliberately and in
> one place: the detection site reports it once per cycle, and `--check`
> carries `wg_setup=` so `master-network --status` shows it as data. The
> substance is unchanged — a pending setup is still not drift and still must
> not fail `--check` or Stage 7. See DD-48.

### DD-13: Reconcile's disk-space check reports but never auto-repairs (2026-07-28)

- **Decision:** `disk_space_ok()` (checks the filesystem backing
  `$DOWNLOADS_PATH`, now persisted in `state.env`) is wired into
  `all_critical_state_healthy()` and the final postcondition
  re-verification block, but there is **no** repair action anywhere in
  the script for low disk space.
- **Context:** Added after a user-requested final architecture review
  considering the server's actual workload (continuous
  downloading/extraction) — previously the one realistic operational
  failure mode reconcile had zero visibility into.
- **Rationale:** Every other reconcile-managed drift has a safe,
  well-defined repair (reapply a sysctl, rewrite a firewall chain,
  restart a container from a known-good image). There is no equivalent
  safe action for "disk is full" — deleting files would mean guessing at
  which of the user's downloaded/extracted data is safe to remove, which
  this project has no basis to do automatically. The check exists purely
  to surface the condition early (via `--check`'s exit code and the
  periodic timer's own failed-unit visibility), not to fix it.
- **Trade-off:** Unlike most other critical-state components, this one
  will not resolve itself on the next cycle — it stays failed until a
  human frees space or grows the disk. Considered and rejected: an
  automatic prune of the oldest files in the downloads tree (too risky/
  presumptuous to implement without the user's explicit, scoped
  instruction on what's safe to delete).

### DD-20: WebDAV is a hardened host service (rclone), not a container (2026-07-30)

The `sftpgo` container was removed and replaced by
`master-webdav.service`, a systemd unit running `rclone serve webdav
$DOWNLOADS_PATH/media --read-only`, bound to the Tailscale IPv4 only.

**Why, honestly.** The user's stated motivation was intermittent playback
stalls on Apple TV/Infuse, attributed to the container layer. That
attribution is probably wrong and was said so at the time: on the direct
path (`TS_IP:65113`) Docker's DNAT happens in the kernel and
`docker-proxy` is not involved — Docker's own OUTPUT rule excludes
loopback (`! -d 127.0.0.0/8`), so only the `webdav.<domain>` Caddy path
went through a userspace relay. The likelier causes of intermittent
stalls are Tailscale falling back to a DERP relay, `wireguard-go`'s
single-core userspace throughput, or the send-side socket buffer. **None
of those are fixed by this change**, and if the stalls persist, that is
where to look next — not here.

What the change *is* justified by, independently of throughput:

- **The security win is the real one.** The narrow `--ctorigdst
  $TAILSCALE_IPV4 --ctorigdstport 65113` ACCEPT in the mangle guard chain
  was the **only** Tailnet → Docker exception in an otherwise fail-closed
  policy. A host service receives its traffic on the INPUT path, which
  the guard chain never inspects (the same reason Caddy and dnsmasq need
  no exception), so that rule is simply gone. The Tailnet → Docker
  direction now has zero exceptions.
- **Less to keep alive.** One container, one image pin, one DNAT rule,
  three port-binding checks, two `assert_docker_binding` calls and the
  `--ctorigdst` install-time assertion all disappeared.
- **Sandboxing did not regress.** The container gave a `:ro` bind mount.
  The unit gives `ProtectSystem=strict` + `ProtectHome` + `PrivateTmp` +
  `PrivateDevices` + `NoNewPrivileges` + `RestrictAddressFamilies`, plus
  `rclone --read-only`, running as a dedicated `master-webdav` system
  user that holds gid 1000 purely to read the 0750 media tree.

**Why rclone and not Apache/mod_dav or a host SFTPGo.** rclone is in
Debian trixie (1.60.1), is a single binary with no configuration file,
and takes everything as flags. Apache would deliver higher raw throughput
via `sendfile` and could natively `Listen` on two addresses, but the
bottleneck here is `wireguard-go`, not the file server — the extra
package tree and config surface buys nothing. Host SFTPGo was rejected
outright: it is not in Debian, so it would add an external apt repo or a
GitHub release to a project that pins everything, and it keeps all of
SFTPGo's complexity while removing only the veth hop.

**Two constraints that shaped the implementation.**

1. *Single `--addr`.* Debian's rclone is 1.60.1; repeatable `--addr` came
   later. The service therefore binds the Tailscale IPv4 **only**, and
   Caddy's `webdav.<domain>` vhost proxies to `{$TS_IPV4}:65113` rather
   than loopback. Binding `0.0.0.0` and relying on a firewall rule was
   rejected: a specific bind is a stronger primitive than a rule that can
   drift.
2. *`EnvironmentFile` is read before `ExecStartPre`.* The obvious design —
   copy Caddy's `caddy-tailnet-env` `ExecStartPre` writing
   `/run/.../tailscale.env`, consumed via `EnvironmentFile=` — is **broken
   for this service**, and was caught in review before it shipped. systemd
   loads environment files when the unit starts, before any `Exec*`
   command runs, so on a first start the file does not exist yet,
   `${TS_IPV4}` expands to empty, and `--addr :65113` becomes a **wildcard
   bind — the public IPv4**. Caddy escapes this only because the `caddy`
   binary re-reads the file itself via `--envfile`; rclone has no
   equivalent. The fix is to resolve the address *inside* `ExecStart`:
   `master-webdav-serve` waits for `tailscale0`, then `exec`s rclone. This
   removes the failure class rather than working around it.

`rclone --config /dev/null` is passed explicitly: the service uses no
remotes, and without it rclone searches `$HOME/.config`, which does not
exist under `ProtectHome=yes` — behavior there varies by version, so it
is pinned rather than left to chance.

**Candidate cleanup, not done:** `master-webdav-serve` and
`caddy-tailnet-env` now contain the same tailscale0-address wait loop.
They were left separate because `caddy-tailnet-env` is generated only when
local DNS is enabled and is part of the canonical bundle contract, while
the WebDAV helper is unconditional. Merging them means reworking that
contract — worth doing, but not inside this change.

**Live verification (2026-07-30) — the first install failed, and found
three real bugs.** Static analysis had passed cleanly on all of them.

1. **`RestrictAddressFamilies=AF_INET AF_INET6` broke the service.**
   `ExecStart`'s first act is `ip addr show` to find the Tailscale
   address, and iproute2 talks to the kernel over a **netlink** socket —
   a separate address family. Measured directly: with the two-family
   restriction, `Cannot open netlink socket: Address family not supported
   by protocol`; adding `AF_NETLINK`, it works. rclone itself needs only
   AF_INET/AF_INET6.
2. **The failure was invisible.** The wait loop had `2>/dev/null … ||
   true` on the `ip` call, so a hard configuration error was
   indistinguishable from "the address hasn't appeared yet". The unit
   reported `active (running)` for the full 300-second window while
   getting nowhere; the install only failed later, at Stage 7's listener
   assertion. The loop now separates the two cases and reports the first
   `ip` error immediately. (The first attempt at this used `mktemp` for
   stderr, which itself failed under `ProtectSystem=strict` with
   `Read-only file system` — caught in the same session. stderr is now
   captured into a variable, which also avoids creating 300 temp files.)
3. **Every 401 probe was wrong.** rclone deliberately exempts `OPTIONS`
   — the WebDAV discovery preflight — from authentication and answers
   `200`. sftpgo returned `401` there, and all three probes
   (`webdav_direct_ok()`, Stage 7's direct check, `caddy_runtime_ok()`'s
   vhost check) had been written against that behavior. Left as-is,
   Stage 7 would fail every install and reconcile would classify WebDAV
   as drifted on every cycle and restart it. They now use `PROPFIND`
   with `Depth: 0`, a protected method — which is a **stronger** signal
   than the original, since a 401 there proves the htpasswd is actually
   being enforced rather than merely that something answered.

   Worth stating plainly because it looked alarming mid-diagnosis:
   authentication was never broken. Measured on the running service —
   unauthenticated `GET` and `PROPFIND` both `401`, wrong password `401`,
   correct password `207`, and an unauthenticated `GET` returns the body
   `Unauthorized`. Only `OPTIONS` is open, and it discloses nothing.

**Confirmed working after the fixes**, on the live host: the listener
binds `<tailscale-ip>:65113` and nothing else (connection refused on the
public IPv4), unauthenticated `PROPFIND` → 401, authenticated → 207, and
the `master-webdav` user reads the 0750 media tree through its gid 1000
membership exactly as designed. **Still unconfirmed:** Infuse itself has
not been pointed at the service, so real-client `Range`/seek behavior and
playback remain untested.

### DD-21: The reconcile timer runs every 20 minutes, aligned with the repair cooldown (2026-07-31)

- **Decision:** `master-network-reconcile.timer` fires every 20 minutes
  (`OnCalendar=*-*-* *:00/20:00`), not every 5 as it did from R1.0
  through `V1-8`.
- **Rationale — not cost.** A healthy check takes about half a second, so
  at 5-minute intervals the duty cycle was under 0.2%; CPU was never the
  argument. The real problem was a cadence mismatch that had been there
  all along: `RESTART_COOLDOWN_SECONDS` is 900. On a *persistent* fault
  the 5-minute timer produced one run that repaired and then two that
  could only detect — each logging `cooldown içinde; tekrarlanmadı`,
  setting `RECOVERY_FAILED=1`, exiting non-zero and leaving a failed
  unit behind. Two thirds of the runs were noise that could not act. With
  the interval above the cooldown, every scheduled run can actually
  repair, and the budget goes back to being what it was meant to be — a
  brake on the event-driven (`OnFailure`) paths, which can fire at any
  moment.
- **Why 20 specifically:** it divides 60, so the schedule is `:00 :20
  :40` — evenly spaced. Values that do not divide 60 leave a short gap at
  the hour boundary: `*:00/18:00` yields `:00 :18 :36 :54` and then only
  6 minutes to the next `:00`. An interval that is silently uneven is
  worse than a longer even one.
- **What this costs:** drift with no event trigger now takes up to 20
  minutes to be corrected instead of 5 — address changes (Tailscale or
  public IPv4), manual edits to managed config, GRO flags cleared by a
  driver reload, a filling disk. The address case is the one a user would
  feel, since WebDAV, Caddy and dnsmasq all bind the Tailscale IPv4. It
  is accepted because on this deployment the public IPv4 is static and
  the Tailscale address only changes on node re-registration, which in
  practice means a reinstall — and `install.sh` corrects it directly.
- **What this does not change:** crash recovery. Five `OnFailure=` hooks
  plus the `PartOf`/`Wants` cascades from `docker.service` and
  `tailscaled.service` invoke reconcile immediately, independent of the
  timer. The timer was never the mechanism for a service falling over; it
  is the net for *silent* drift, and only that latency moved.
- **Reversing it:** change the single `OnCalendar` line. Nothing else
  depends on the interval — the cooldown is expressed in seconds and the
  checks are stateless.

## Rejected Alternatives

- **Using `nftables` directly instead of `iptables`/`ip6tables`:** not
  pursued; Debian 13's `iptables` package already provides the
  nftables-backed `iptables`/`ip6tables` compatibility binaries, so the
  existing rule-based logic works without a rewrite. **Partially
  verified 2026-07-28:** the host's own `iptables`/`ip6tables` do run
  through the nftables backend (`nf_tables`/`nft_compat` kernel modules)
  — discovered as the root cause of the **H1** regression, where
  wg-easy's container uses the **legacy** backend instead (needing its
  own separate `ip6_tables`/`ip6table_nat` modules the host's nft-backed
  usage never loads). Not verified beyond this one concrete case whether
  anything else in the script assumes one backend over the other.
- **Merging operator config changes into the canonical bundle instead of
  reverting them (see DD-3):** rejected as intractable to do safely for
  security-sensitive firewall/proxy configuration; a deterministic
  "canonical always wins" model was chosen instead.

## Open Trade-offs

- Whether to keep the fixed six-service bundle (simple, one config to
  reason about) vs. introduce installation profiles (more flexible, more
  combinations to test) — see `docs/profiles.md`.
- Whether the `PartOf` fate-sharing model (DD-4) should be loosened for
  operator convenience at the cost of weaker failure-isolation guarantees.
- Whether to keep all logic in one file (DD-9) vs. extract embedded
  scripts into separate, independently lintable/testable files at the
  cost of a more complex deployment/packaging story.
- Whether wg-easy's host-kernel WireGuard module dependency (DD-10) is
  acceptable long-term, or worth replacing with a userspace WireGuard
  backend (`boringtun`/`wireguard-go`) that would need no kernel module at
  all — the latter needs a forked/customized image and hasn't been
  attempted.

### DD-14: The canonical bundle is published through a verified generation pointer (2026-07-28; corrected 2026-08-02)

- **Decision:** Stage 4 writes `/etc/master-stack/state.env` but does not
  publish a canonical copy or a `SHA256SUMS` manifest. At the end of
  Stage 6, all nine bundle files and the manifest are written into a new
  `.generation.*` directory and verified there. Only then is the
  `/usr/local/share/master-stack/current` symlink replaced with one
  same-filesystem `rename(2)` operation. Reconcile reads through that
  pointer.
- **Context:** `SECURITY_REVIEW.md` findings **M8** and **H8**.
- **Rationale:** `canonical_bundle_ok()` validates the manifest's entry
  list, and a partial bundle fails that check. Publishing `state.env` in
  Stage 4 alongside a state.env-only manifest left the bundle incomplete
  for the whole of Stages 4-6, and an interrupted re-run left reconcile
  hard-exiting on every cycle with no self-healing.
  *(As originally written this rationale turned on the manifest being
  validated against the `LOCAL_DNS_ENABLED` value inside the canonical
  `state.env`. `V1-8` removed that key — local DNS is no longer optional —
  so the manifest now has a single fixed shape. The decision stands
  unchanged; only its justification simplified.)*
- **Correction recorded by H8:** the first M8 remediation moved the nine
  individual copies to the end of Stage 6 and atomically renamed only the
  manifest. That narrowed the interruption window but did **not** make the
  bundle atomic: a failed fourth or fifth copy left a mix of old and new
  files behind the old manifest, which then failed its hashes. The word
  "atomic" applies only after Q1-16's generation-pointer design.
- **Alternatives rejected:** deleting Stage 4's manifest write alone (a
  fresh install then has no manifest, and a re-run's stale manifest no
  longer matches the newly written `state.env` — both still fail
  validation); writing the full manifest in Stage 4 (impossible on a fresh
  install, where those files don't exist yet); treating an atomic manifest
  rename as an atomic multi-file publication (the H8 defect).
- **Consequence worth knowing:** during Stages 4-6 of a re-run,
  `state_value()` still reads the *previous* run's canonical values. That
  is deliberate — for a half-applied re-run, the last known-good
  configuration is the right thing to enforce. On the first upgrade from
  Q1-15/R2.4, the new reconcile script temporarily accepts the legacy flat
  bundle until Stage 6 publishes `current`; after that publication the
  legacy files are removed so a later missing pointer fails closed rather
  than silently reverting to stale data. Publication retains at most the
  active and immediately previous generations across regular re-runs.

### DD-15: Docker's chain layout is assumed, and Docker itself is deliberately not pinned (2026-07-28)

- **Superseded by DD-152 (2026-09-19):** Docker is no longer installed.

- **Decision:** `docker-ce`/`containerd.io`/`tailscale`/`caddy` stay
  unpinned even though container images are pinned to exact tags, and the
  firewall helper keeps assuming Docker's internal chain layout
  (`DOCKER-USER`, `DOCKER-FORWARD` and `ts-forward` existing, and being
  the first three `FORWARD` rules in that order).
- **Context:** `SECURITY_REVIEW.md` finding **M9**.
- **Operational fact worth stating explicitly:** because Stage 3 leaves
  the Docker apt repository configured, **every re-run upgrades Docker to
  the newest upstream release** via Stage 1's `full-upgrade`. A re-run is
  therefore also a Docker upgrade, whether or not that was the intent.
- **Rationale for not pinning:** this host publishes ports to the public
  IPv4, so freezing Docker's version would trade a hypothetical layout
  change for a certain loss of CVE fixes. The coupling is the lesser
  risk.
- **Failure mode, for the record:** if a Docker release restructures
  those chains, `ensure_forward_prefix()` returns non-zero and `set -e`
  aborts the helper before any rule is applied. On a re-run the
  previously-applied chains survive (the staging swap only happens at the
  end), so that path fails safe. The real exposure is a **reboot** after
  such an upgrade: these rules have no persistence layer and are rebuilt
  from scratch at every boot, so a broken helper means the fail-closed
  WAN DROP and the Tailnet → Docker/LAN DROP backbone are simply never
  created.
- **Mitigation applied:** diagnostics only — the helper now names the
  missing chain and the likely cause rather than aborting silently.
  Verified live on 2026-07-28 that Docker 29.6.2 still produces exactly
  the assumed layout.
- **Known asymmetry, deliberately left alone:** `apply_ipv6()` degrades
  gracefully when Docker's IPv6 `DOCKER-USER` chain is missing (warns and
  skips the IPv6 policy), but `ensure_forward_prefix()` treats the same
  condition as fatal for either family. Changing it would loosen a
  fail-closed path, so it is recorded rather than "fixed".

### DD-16: Managed firewall rules never reference container IPs (2026-07-29)

- **Decision:** every rule the `docker-tailscale-fw` helper writes matches
  on interface names (`tailscale0`, the detected WAN interface) and *host*
  addresses (the public IPv4, the Tailscale IPv4). None of them names a
  container's bridge address.
- **Why this matters, measured 2026-07-29:** across a reboot, Docker
  assigns container bridge IPs in start order, and that order is not
  deterministic. On one boot `qbittorrent` held `172.18.0.6`; on the next
  it held `172.18.0.2`, with `filebrowser`, `sftpgo` and `portainer`
  likewise shuffled. Docker correctly rewrote all of its own DNAT and
  ACCEPT rules to match. Because our rules never mention those addresses,
  `MASTER-DOCKER`, `MASTER-TS-FORWARD` and the `FORWARD` prefix came back
  **byte-identical** while Docker's chains legitimately changed.
- **Two consequences worth keeping:**
  - `check_ipv4_policy()`/`check_ipv6_policy()` assert the exact contents
    of our chains and the ordering of the `FORWARD` prefix, but say
    nothing about the contents of Docker's `DOCKER` chain. If they did,
    `--check` would report drift after every reboot.
  - `docker_dnat_rule_exists()` in reconcile resolves the container's
    current IP at check time via `docker_network_tuple()` rather than
    comparing against a stored value. That is what lets it verify Docker's
    DNAT rules without breaking when the address changes.
- **Trade-off:** the narrow public allows are therefore expressed against
  `--ctorigdst` (the pre-DNAT destination) rather than the container, which
  is slightly less obvious to read but is the only formulation stable
  across restarts.
- **What would break this:** giving containers static bridge addresses and
  then writing rules against them. Do not — the current arrangement is why
  a reboot needs no reconciliation at all.

### DD-22: A wg-easy still on its `/setup` screen is reported, not failed (2026-07-31)

- **Superseded by DD-120 (2026-09-14):** wg-easy is removed; WireGuard runs in
  the host kernel from `kurulum/wireguard`.

- **Decision:** the reconcile helper distinguishes "wg-easy is waiting for
  its first web setup" (`WG_SETUP_PENDING`, reported as `UYARI`, no effect
  on the exit code) from "wg-easy's internal WireGuard port does not match
  `WG_PUBLIC_PORT`" (`WG_CONFIGURATION_INVALID`, `HATA`, sets
  `RECOVERY_FAILED` → exit 1). Both still suppress wg-easy's automatic
  restart.
- **Why:** until `V1-11` both used the single `WG_CONFIGURATION_INVALID`
  flag, and the resulting exit code was wrong in a specific and unhelpful
  way. Because `all_critical_state_healthy()` returns early with `exit 0`,
  a fresh install where nothing had drifted looked fine — while any pass
  that actually *repaired* something fell through that gate to the
  `RECOVERY_FAILED` check and exited 1, with every repair having
  succeeded. The signal was therefore correct only while reconcile was
  idle and wrong as soon as it did work, which is the inverse of what a
  monitoring signal is for. `master-network-reconcile.service` being the
  `OnFailure=` target of five other units made it worse: a chronically
  red unit is one an operator learns to ignore.
- **How it was found:** two drift scenarios on a live host on 2026-07-31 —
  stopping `master-webdav.service`, and appending a line to
  `/etc/caddy/Caddyfile`. Both repaired correctly (WebDAV back to 207, the
  Caddyfile restored byte-for-byte) and both exited 1. The healthy pass
  immediately afterwards exited 0. Static review had not caught it, and
  would have had a hard time: the comment above the check already
  described the intended behavior, so reading the comment and the code
  together produced a false sense that the intent was implemented. It was
  — but only along one of the two paths out of the function.
- **The restart suppression stays in both branches** deliberately.
  Restarting a container that is waiting for its first web setup does not
  advance it, and would reset whatever partial setup state exists.
- **Both branches are measured, not one measured and one reasoned.** The
  failing branch stayed untestable while wg-easy sat on `/setup`, because
  `wg show wg0 listen-port` has no interface to report on until setup is
  done. Once the operator completed it (2026-07-31),
  `wg set wg0 listen-port 51820` — runtime-only, reversible, `wg0.conf`
  untouched — produced `HATA: wg-easy iç portu 51820; beklenen 65171.`,
  `compose_runtime=1` and `exit 1`, with wg-easy correctly *not*
  restarted. Restoring the port returned `exit 0` with the peer intact.
  This is worth recording as a method as much as a result: the two
  branches of a split like this one are only trustworthy when the
  *negative* case has been shown to still fail, otherwise "we stopped
  failing" is indistinguishable from "we stopped checking".
- **What would remove the condition entirely:** provisioning wg-easy's
  admin account unattended (the open `INIT_*` item), which is the real fix
  for the underlying awkwardness — a freshly installed stack that is not
  actually finished. `V1-11` only stops it from being misreported.

### DD-23: Container images float at the patch level, and their digests are recorded (2026-07-31)

- **Decision:** the five container images use moving tags rather than
  exact versions, and the digest each tag resolved to is written into
  `state.env` after Stage 5 (`STACK_SCHEMA` 10).

  | Image | Tag | How far it moves |
  |---|---|---|
  | wg-easy | `15.3` | patch only |
  | unpackerr | `0.15` | patch only |
  | filebrowser | `v2` | anything within the major — no `v2.63` tag is published |
  | portainer | `lts` | within the LTS line; jumps a major when Portainer declares a new LTS |
  | qbittorrent | `latest` | upstream stable, including a libtorrent major |

- **Why not exact pins:** they made a re-run deterministic but also froze
  security and bugfix updates. Debian-sourced host packages (kernel,
  dnsmasq, systemd) already behave as "patches arrive, majors do not"
  because trixie is stable; floating container tags extend the same rule
  to the rest of the stack instead of running two opposite policies side
  by side.
- **Why not pin the third-party host packages instead.** That was the
  first proposal (`docker-ce`, `tailscale`, `caddy` from their own repos
  can jump majors on a re-run, since their `sources.list` entries persist
  and Stage 1's `full-upgrade` sees them). The user rejected it on the
  grounds that it trades away security updates, and that is the correct
  reading: the existing safety net — upgrade first, rewrite all managed
  configuration afterwards, then assert in Stage 7 — is what makes an
  unpinned upgrade survivable, and it is already in place.
- **Why the float levels are uneven:** because the upstreams' published
  tags are uneven. Queried from the registries on 2026-07-31; filebrowser
  publishes no minor tag at all, and linuxserver publishes no float tag
  for qbittorrent beyond `latest`. Both `lts` and `latest` were verified
  to resolve to the same digests as the exact pins they replaced, so
  adopting them changed nothing on the day — which is the safest way to
  take on a moving tag.
- **Why digests are recorded, and why that is not optional.** A moving
  tag deletes the answer to "what is actually running": `compose.yaml`
  keeps the same checksum while the image underneath it changes. The
  five `IMAGE_DIGEST_*` keys restore it, `--status` prints the short form
  next to each container, and Stage 7 asserts that the recorded digest
  equals the running one — so the record cannot quietly drift from
  reality. Floating tags without this record would be a straight loss of
  auditability; the pair is the design, not the tag change alone.
- **The asymmetry to keep in mind:** upgrading is safe — every one of
  these containers reads its existing data directory and continues — but
  **downgrading is not.** Portainer migrates its database forward on
  start with no reverse path. Re-pinning an old tag therefore does not
  undo a bad upgrade. The recovery path is a provider-level (netcup) VPS
  snapshot taken before the run, which the user chose deliberately over
  an in-script snapshot: a whole-machine image covers the migrated
  databases, and it keeps rollback out of the installer's scope.
- **Cost accepted:** a patch-level regression can arrive on a routine
  re-run. Two things bound it — reconcile never pulls (only Stage 5's
  explicit `docker compose pull` does, so images never move on the
  20-minute timer), and the digest record names the version to go back
  to.
- **Found while implementing, worth recording:** `RepoDigests` is a field
  of the *image* object, not the container. `docker inspect <container>`
  fails with `map has no entry for key "RepoDigests"`, and the first
  `V1-12` attempt wrote all five digests as `bilinmiyor`. Stage 7's
  assertion caught it and failed the install with `rc=1, aşama=7` — the
  intended behaviour, and the second time in three revisions that a Stage 7
  literal assertion caught a change that `bash -n`, `shellcheck` and the
  bats suite all passed.

### DD-25: The repair cooldown is duplicated on purpose, and asserted (2026-07-31)

- **Decision:** the 15-minute repair cooldown stays written out in both
  embedded scripts — `RESTART_COOLDOWN_SECONDS` in
  `master-network-reconcile`, `COOLDOWN_SECONDS` in
  `master-docker-netfilter-recovery` — with `install.sh` declaring
  `MASTER_RESTART_COOLDOWN_SECONDS` as the single source of truth and
  **Stage 7 asserting all three agree**.
- **Why not actually share one variable.** Every embedded script must be
  self-contained, because `scripts/lint-embedded-scripts.sh` extracts each
  one by its heredoc marker and runs `bash -n` + `shellcheck` on it as a
  standalone program — the mechanism that answers **H4**, since the outer
  `shellcheck install.sh` sees these bodies only as string data. Binding
  the two scripts to a shared variable, or splitting a heredoc so an
  unquoted prelude could interpolate one, would leave the linted fragment
  referencing a variable it never assigns. That trades a real property
  (the linter checks exactly what ships) for a cosmetic one.
- **What the duplication actually risked** was never the second copy
  itself; it was *silent* divergence. DD-21 moved the reconcile timer to
  20 minutes specifically to stop fighting this cooldown, so the two
  numbers are coupled by a design decision — and one of them could have
  been changed with the other quietly left behind. Stage 7 now turns that
  into a failed install naming all three values.
- **Three copies were removed outright**, which is the part that is a
  genuine deduplication rather than a guard: the operator-facing messages
  in both scripts hardcoded the string "15 dakikalık cooldown". They now
  derive it (`$((RESTART_COOLDOWN_SECONDS / 60))`), so the prose cannot
  contradict the behaviour.
- **`StartLimitIntervalSec=900` in three systemd units is deliberately
  left alone.** It shares the value but not the meaning — systemd's
  start-rate limiter is a different mechanism from the repair budget, and
  folding them together would create a coupling that does not exist.
- **The assertion was verified to discriminate, not assumed to:** a copy
  of `install.sh` with the recovery constant changed to `800` was
  installed on the test host and failed at Stage 7 with
  `install.sh : 900 / reconcile : 900 / recovery : 800`. This is the same
  discipline applied to `all_critical_state_healthy`'s coverage guard the
  same day — a guard nobody has seen fail is not yet known to work.

## DD-26 — reserved

**Not used on this branch.** `DD-26` belongs to the dufs migration on
`master` (`V2-1`/`V2-2`). This branch forks from `V1-20`, which predates
it, so the number is left empty rather than reused — two different DD-26s
across two branches would collide the moment they are compared or merged.

### DD-27: FileBrowser Quantum replaces filebrowser, and its admin password is deliberately not set (2026-08-01)

**Decision.** On the `quantum` branch (forked from `V1-20`), swap
`filebrowser/filebrowser:v2` for `ghcr.io/gtsteffaniak/filebrowser:stable`
— FileBrowser Quantum, the actively maintained fork — keeping the
container name, the host port, and every piece of surrounding plumbing
unchanged. Do **not** bootstrap its admin password from the installer.

**Why this branch exists at all.** `master` already answered "what
replaces filebrowser" with dufs (DD-26), driven by filebrowser's
2026-09-01 archival and its three permanently unpatched advisories. That
answer holds on its own terms, but it cost interface quality — recorded as
**L11**, the one axis where the swap went backwards. Quantum is the other
candidate from that same evaluation. This branch tests it against the
`V1-20` line rather than against `master`, because `V1-20` is what is
installed on the host today and because leaving `master` untouched means
the experiment can be abandoned by deleting a branch.

**What Quantum is better at.**

- **Tag hygiene, and it is the best in the stack.** Upstream publishes
  both a moving `stable` tag and exact pins (`1.5.0-stable`). Original
  filebrowser offered only major-wide `v2`; dufs offers no float at all,
  which is precisely what **L9** records as an open cost. `stable` is
  therefore chosen here, and it satisfies DD-23's rule ("take the finest
  float the upstream actually publishes") for the first time in this slot.
  The risk is named rather than hidden: `2.0.0-preview-*` tags already
  exist, so `stable` will one day cross a major boundary silently.
- **Shell commands are removed from the codebase entirely**, per
  upstream's own feature list. That is filebrowser's unpatched
  `GHSA-8c9q-7855-wfxq` (command-allowlist bypass via shell
  metacharacters) eliminated by deletion rather than by configuration —
  strictly stronger than the `Exec Enabled: false` that made it
  unreachable on the old build.
- The interface is the reason the branch exists; that judgement is the
  operator's and is not argued here.

**What it costs.** Quantum is **stateful**: the image declares
`FILEBROWSER_DATABASE=/home/filebrowser/data/database.db`, so a named
volume returns where dufs needed none. Since `Q1-12` the compose file
repeats that value instead of inheriting it. Nothing was wrong with the
inherited one — the point is that `read_only: true` turns it into a
constraint rather than a preference: the path has to land inside the
`filebrowser_data` mount, because a Quantum that opens its database
anywhere else opens it on a read-only root and dies at startup. Two lines
that must agree now sit next to each other in the same file, rather than
one of them living in an image the project does not control. The failure
this guards against is loud (a boot-loop `reconcile` catches), not silent,
which is why it is a small hardening and not a fix.

**The first-boot warning is upstream noise, and pinning does not remove
it.** A first install logs `[WARN] database file could not be found. If
this is unexpected, please set the FILEBROWSER_DATABASE environment
variable to the correct path` one second before `Creating new database`.
Measured on the live host on 2026-08-02: the variable *was* already set to
exactly the path Quantum then created. The message does not distinguish
"the file is missing" from "the path is wrong" — on a first install only
the former is true. It is emitted before the `Using Config file` banner,
i.e. during store initialisation, when the environment variable is the
only knob the program has read yet; that is why the advice names it.
Restart and `docker compose up -d --force-recreate` both log `Using
existing database` with no warning at all, and the operator's changed
admin password survives both (`admin`/`admin` → `401`, and no `Resetting
admin user to default username and password.` line).

> **Correction (2026-08-02, same day).** This entry originally claimed
> there is no config key for the database path, "so the environment
> variable is the only surface". That was wrong. `server.database` exists
> and is the documented way to set the path in `config.yaml`; a newer
> upstream wording of the same first-boot warning names it directly ("please
> double check your configuration file for `server.database` path"). The
> error came from checking the image's *sample* `config.yaml`, finding no
> such key, and generalising from that to the schema — an inference
> presented as a measurement, which is the exact failure this file exists to
> stop.
>
> Nothing about the design changes. `FILEBROWSER_DATABASE` is honoured and
> points at the right path, measured on the live host; `Q1-12`'s pin is
> effective. Both surfaces are equally protected, since `compose.yaml` and
> `filebrowser.yaml` are both canonical bundle entries. The policy file
> deliberately does **not** set `server.database`, which leaves one rough
> edge worth knowing: an operator who follows the warning's advice will open
> `filebrowser.yaml` and find nothing there. Setting it in the policy file
> would be the tidier home for it, and is unclaimed work rather than a
> defect.

`cap_drop: [ALL]` and
`no-new-privileges` are kept; the image already runs as a non-root
`filebrowser` user, which is why no `user:` line is set (the image's own
UID must own the data directory).

**`read_only: true` was first written off here as impossible, and that was
wrong.** The claim was an inference from "Quantum is stateful", never a
measurement — the same shortcut this project avoided for unpackerr (tried,
it worked, kept) and qBittorrent (tried, it broke `PUID`/`PGID`, removed).
Measured on 2026-08-01: the only thing Quantum writes outside its volume is
its cache directory, and `server.cacheDir` is configurable. Pointing it at
`/home/filebrowser/data/cache` puts the cache inside the volume that already
exists, and the root filesystem can then be read-only with **no tmpfs at
all**. Changes in the container's writable layer went from **18 to 1** — the
one remaining entry being the read-only bind mount itself — while login,
listing and writes to the media tree were unaffected.

A tmpfs was tried first and rejected on evidence: Quantum recommends at
least 20 GB of free space for the cache and warned with a 256 MB tmpfs
(`cacheDir only has 0.25 GB of free space`). Thumbnail generation over a
real media library is not something to hold in RAM. Putting the cache on
disk also fixed a smaller thing nobody had noticed — thumbnails and the
search index used to live in the container's writable layer and were
therefore discarded every time the container was recreated; they now
survive, including across a reboot (verified).

So the hardening dufs gave up nothing for is recovered on this line too.
The one thing that genuinely does not carry over is statelessness itself.

> **`read_only: true` later turned out to have a second price — see DD-35
> (2026-08-02).** It is what makes the policy file impossible to fold into
> `compose.yaml`: Compose refuses inline `configs.content` on a read-only
> service. The operator was shown the trade and chose to keep `read_only`.

**The initial admin account is left to the container — revised 2026-08-01
after reading upstream's source.** The installer briefly did bootstrap it,
and that was the wrong call. What upstream actually does:

```go
if !exists {                       // only when the database is absent
    settings.Env.IsFirstLoad = true
    quickSetup(store)
}

func quickSetup(store *bolt.BoltStore) {
    if settings.Config.Auth.AdminPassword == "" {
        settings.Config.Auth.AdminPassword = "admin"   // hardcoded fallback
    }
    user.ShowFirstLogin = settings.Env.IsFirstLoad && user.Permissions.Admin
```

So `admin`/`admin` is a real default rather than a documentation example; it
is created **once**, only when the database does not exist; it is never
re-asserted on later starts; and the UI raises a first-login notice
(`ShowFirstLogin`) without forcing a change. Two supported ways to set it
exist — a `FILEBROWSER_ADMIN_PASSWORD` environment variable read in
`loadEnvConfig()`, and the `filebrowser set -u user,pass -a` CLI.

Neither is used, and the reason is not only the secret-at-rest question:

- The env var would put a plaintext password in `compose.yaml`. That file is
  `0600 root:root` and inside the canonical bundle, so it is better than a
  world-readable file — but it is still plaintext at rest, visible via
  `docker inspect` and in the container's own `/proc/1/environ`.
- The CLI needs the container stopped, because the running process holds the
  SQLite file. The first implementation of that shipped an **idempotency
  bug**: it worked on a fresh host and died on a re-run with `the database is
  locked` (`rc=1, aşama=5`).
- **The decisive reason is behavioural.** The CLI approach ran whenever Stage
  0 re-collected credentials, which means a re-run would have silently reset
  a password the operator had already changed in the UI. Leaving the account
  to the container gets that right for free: upstream's `if !exists` guard
  makes the credential the operator's from first login onward. Verified —
  after changing the password to something else, a full re-run of the
  installer left it untouched (`401` on `admin`/`admin`, `200` on the new
  password).

**`minLength` is therefore fixed at upstream's 5 and cannot be raised.**
`admin` is exactly five characters, so `minLength: 8` makes `quickSetup()`
die with `[FATAL] store.Users.Save: password must be at least 8 characters
long` — and the container then comes up with *no user at all*: healthy to
Docker, 200 to the reconcile probe, clean under `--check`, and impossible to
log into. That was measured, not theorised. The two numbers are tuned to
each other upstream.

**The consequence is stated plainly in the install summary and is the
operator's to close:** unlike Portainer and wg-easy, which ship with no
account, Quantum ships a working `admin`/`admin` login. Until it is changed,
any device on the tailnet has full access to the media tree. The summary
promotes changing it to the first post-install action and says the container
owns the account, so the change can only be made through the web UI.

**Measured on a live host (2026-08-01), and the design changed as a
result.** Everything below replaces the "unverified" list this entry
originally carried.

`FILEBROWSER_CONFIG` **is** honoured, so the policy file lives outside the
volume as intended (`Using Config file: /config.yaml` in the startup log,
sources resolved to `srv: /srv`). The container user is `uid=1000(filebrowser)
gid=1000` — the same 1000:1000 as the media tree's ownership model — and a
fresh named volume comes up correctly owned. `stable` resolved to
`v1.5.0-stable`.

**The default credential is real, and `minLength` does not stop it.** The
config sets `minLength: 8`, and on the very first start that made Quantum's
own bootstrap die with `[FATAL] store.Users.Save: password must be at least
8 characters long` — `admin`/`admin` is 5 characters. The container
restarted into a state with *no* user at all: healthy to Docker, 200 to the
reconcile probe, `--check` clean, and impossible to log into. Worse, the
first reading of that result — "so `minLength` blocks the default" — was
wrong. Creating a user through the CLI against an empty volume produced
**two** admins, `admin` and the requested one: the database-initialisation
path creates the default account and **bypasses the `minLength` check that
only the server's own bootstrap path enforces**.

So the installer now closes it explicitly rather than relying on
configuration. After the image pull and before the stack starts, Stage 5
runs `filebrowser set -u admin,<Stage-0 password> -a`. One call covers both
states: it creates the account if absent and overwrites the auto-created
default if present. Verified — afterwards `admin`/`admin` returns 401,
`admin`/<password> returns 200, and exactly one user exists.

Three consequences worth stating:

- **`minLength: 8` is kept deliberately, as a fail-closed backstop.** If
  Stage 5's bootstrap ever fails to run, the server's own path hits the
  FATAL and the container dies loudly instead of quietly coming up on
  `admin`/`admin`. Lowering it to upstream's 5 would choose the silent
  option.
- **The password is passed as a CLI argument**, so it is briefly visible in
  the host's process list. It is never written to disk. That is the cost
  accepted in exchange for not putting plaintext in a config file, which
  would be permanent and would break **C2**.
- **Stage 7 asserts the property rather than assuming it**: a `POST` to
  `/api/auth/login?username=admin` with `X-Password: admin` must return
  401, or the install stops. This mirrors `V2-2`'s dufs anonymous-401
  assertion, and for the same reason — the health check, the reconcile
  probe and `--check` all report a service with a live default credential
  as perfectly healthy. Proven, not assumed: the admin password was set
  back to `admin` deliberately and the install stopped with
  `rc=1, aşama=7`.

**One idempotency bug was introduced and fixed in the same session.** The
first version of the Stage 5 bootstrap ran fine on a fresh host and failed
on a re-run: the running container holds the SQLite file, so the CLI died
with `the database is locked` and took the install with it
(`rc=1, aşama=5`). Stage 5 now stops the container first, which is safe
because `master-compose` is restarted a few lines later anyway. Both paths
were then re-tested end to end — re-run against a live stack, and a fresh
install with the volume deleted — each completing with `admin`/`admin`
closed, zero FATALs, zero restarts and `--check` at `rc 0`.

**Still unmeasured:** whether the SQLite indexer's first pass over a large
media tree costs anything noticeable. The test host's tree is nearly empty,
so this proves nothing about a real library.

### DD-28: The WebDAV directory cache is one minute, and `--poll-interval` is deliberately absent (2026-08-01)

**Decision.** Pass `--dir-cache-time 1m` to `rclone serve webdav`, overriding
rclone's 5-minute default. Do not pass `--poll-interval`.

**Why it matters here specifically.** This installer exists to serve a media
tree to Infuse over WebDAV while qBittorrent and unpackerr write into that
same tree. The two halves are therefore in a producer/consumer relationship,
and rclone's default put five minutes between them.

Measured on 2026-08-01, with a file created in the media tree:

| | t+0s | t+5s | t+10s |
|---|---|---|---|
| FileBrowser Quantum | visible | visible | visible |
| WebDAV (rclone) | **404** | **404** | **404** |

Quantum sees it immediately because it runs its own SQLite index with
real-time monitoring; rclone was still serving a cached listing. So a
finished download or a freshly extracted archive could be invisible in
Infuse for up to five minutes, with nothing wrong and nothing to see in any
log.

**Why not `--poll-interval`.** It looks like the more precise instrument —
poll for changes rather than blanket-expire the cache — and it is a no-op
here. rclone's own help says "only on supported remotes", and
`rclone backend features` on the media directory reports
`ChangeNotify: false` (measured the same day). The local backend has no
change-notification mechanism, so the poll interval never fires. Directory
cache lifetime is the only effective lever on this backend.

**Why one minute.** The value trades freshness against re-reading the tree:

| Value | Worst-case delay | Judgement |
|---|---|---|
| `5m` (rclone default) | 5 min | The problem above |
| **`1m`** | 1 min | **Chosen** — short enough that "the download finished but it isn't there" never becomes a question |
| `30s` | 30 s | Twice the re-listing cost for a difference the user cannot perceive |
| `0` | none | Disk read on every request; deletes the reason the cache exists, and would degrade browsing a large library |

**Verified, and the first measurement was wrong.** The initial check appeared
to show instant visibility — but the install had just restarted
`master-webdav`, so the cache was *cold* and the first `PROPFIND` read from
disk. That measured nothing about the cache. Re-run correctly — warm the
cache with a `PROPFIND`, then create the file, then poll — the file appeared
after **33 seconds**, consistent with a one-minute entry that was already
partway through its life. Byte-range requests were re-verified at three
offsets afterwards and still return 206 with correct content.

### DD-29: The policy file's target is normalised before writing, container included (2026-08-01)

**Decision.** Before writing `/etc/master-stack/filebrowser.yaml`, delete it
if it is a *directory*, and remove the `filebrowser` container as well.

**The failure it prevents was the only one a re-run could not fix.** This
project's standing answer to a broken host is "run `install.sh` again" —
every other repair path relies on that. One state broke it:

1. The policy file is missing for any reason.
2. Compose starts and cannot find the bind-mount source, so **Docker creates
   a directory** at that path — its documented behaviour for a missing
   source.
3. Quantum reads the directory as its config and fails validation with
   `Settings.Server.Sources ... required`. The container serves nothing.
4. The operator re-runs the installer. `mv -f file dir/` **does not fail** —
   it silently moves the file *into* the directory. The bind mount is still a
   directory, the service is still broken, and the only visible change is one
   more file accumulating inside.

Reconcile does detect the outage (`compose_runtime=1`, `rc=1`, HTTP probe
failing), so it is not silent — but it cannot repair it, and neither could
the installer.

**The first fix was insufficient, and testing is what showed it.**
Normalising the host path alone left the install failing at stage 5. Once a
container has been created with a *directory* mounted at `/config.yaml`, that
mount type is recorded in the container and `runc` rejects the corrected
file with `not a directory: Are you trying to mount a directory onto a file
(or vice-versa)?` — a restart loop rather than a recovery. The container has
to be removed so compose recreates it with a clean mount spec. No data is at
risk: everything persistent lives in the `filebrowser_data` volume, which
outlives the container.

Verified end to end: the broken state was reproduced deliberately
(directory at the config path, container running but serving nothing,
`--check` `rc 1`), then a single installer run restored `-rw-r--r--` at the
path, a healthy container with `RestartCount 0`, HTTP 200, a working admin
login, and `--check` `rc 0`.

**Scope.** `${QUANTUM_CONFIG_FILE}` is the only single-*file* bind mount in
the stack, so it is the only place this applies. Every other bind mount is a
directory, where Docker creating one is correct, and `webdav.htpasswd`
reaches its service through systemd `LoadCredential` rather than a mount —
if that file goes missing the unit fails loudly, which is the behaviour we
want.

### DD-30: Reconcile reports the default filebrowser password without failing on it (2026-08-01)

**Decision.** On every reconcile cycle, attempt a login as `admin`/`admin`
against filebrowser. If it succeeds, warn — and do nothing else. The exit
code, `compose_runtime`, and the restart logic are all untouched.

**Why report at all.** DD-27 leaves the initial account to the container, so
`admin`/`admin` on a fresh install is the *expected* state, not a fault.
What makes it worth surfacing is that it can come back **after** install: if
the volume is deleted or the container is recreated from scratch, Quantum
runs `quickSetup()` again and re-creates the default account. Nothing else in
the system notices — Docker reports the container healthy, the HTTP probe
gets its 200, and `--check` is clean. A security property that can silently
regress and that no existing signal covers is exactly what a 20-minute
reconcile loop is for.

**Why a warning rather than a failure.** Failing would make every fresh
install report `rc 1` until the operator got round to changing the password,
which trains people to ignore the exit code — the precise failure mode
`V1-11` was fixed to avoid. This is the same shape as wg-easy's
`WG_SETUP_PENDING`: an operator step that has not happened yet is reported,
not treated as a fault.

**Why no flag variable.** `WG_SETUP_PENDING` exists because it is *read* —
it suppresses a pointless wg-easy restart. Here there is nothing to suppress:
restarting the container does not change a password. An unread flag would
also fail `shellcheck` (SC2034), which is how the first draft was caught.
The warning is the whole feature.

**Why a login attempt, when something less invasive would be preferable.**
One was looked for and does not exist. The user object exposes
`showFirstLogin`, which tracks whether the first-login notice has been
displayed — not whether the password changed. Measured on 2026-08-01: it had
already flipped to `false` on a host whose password was still `admin`, so
relying on it would produce false negatives for exactly the operator who
dismissed the notice and moved on. The cost of the real check is one log line
per cycle — 72 a day against a `json-file` driver capped at 10 MB × 3.

> **Amended by DD-33 (2026-08-02).** "One log line per cycle" was true of
> the *output* but not of the *requests*: living inside
> `probe_compose_runtime` meant up to four login attempts on a drifted
> cycle, and the endpoint turned out to be rate-limited per source IP.
> DD-33 moves the probe out into its own function called once per cycle,
> and gives `429` its own message.

Verified in both directions: with the default password the warning appears in
`--check`, in `--status`, and in the timer-driven run's journal, with `rc 0`
and `compose_runtime=0` throughout; after changing the password it goes
silent, still at `rc 0`.

### DD-31: Inodes are checked separately from bytes, and `-` counts as healthy (2026-08-01)

**Decision.** `inode_space_ok()` sits alongside `disk_space_ok()` with its
own flag, its own message, and a shared threshold — and treats a `-` in the
`IUse%` column as healthy rather than as unreadable.

**Why a second check at all.** The two are not the same measurement. ext4
fixes its inode table at `mkfs` time, so a tree of many small files can
exhaust it while the filesystem is nearly empty in bytes. Measured on the
Debian target on 2026-08-01 with a 32 MB image made with `-N 64`: after 52
files, `df -h` read **1% used** and `df -i` read **100% used**. The byte
check returned healthy on that filesystem while `touch` returned `ENOSPC` —
which is exactly the state a torrent tree can reach, and exactly what the
existing check structurally cannot see.

**Why a separate flag rather than folding it into `DISK_SPACE_LOW`.** The
remedy differs, and it is counter-intuitive: deleting large files frees
bytes and no inodes at all. An operator reading "filesystem over 90% full"
against a `df -h` showing hundreds of free gigabytes would reasonably
conclude the check was broken. The message says which resource ran out and
that the fix is deleting *many small* files. A separate flag also keeps
`--check` diagnostic (`inode_space_low=`) instead of overloading one key.

**Why `-` is healthy and not fail-closed.** Filesystems that allocate inodes
dynamically report `-` in this column. Measured on the target the same day
against a btrfs loop device: `IUse%` is `-`, and the digit filter the byte
check uses leaves an empty string — which under that check's fail-closed
rule would raise a permanent, unfixable warning on every 20-minute cycle for
anyone on btrfs. `-` does not mean "could not read", it means "there is no
table to exhaust". Genuinely unparseable output still fails closed, and the
two cases are separated by testing the raw field for `-` before filtering
digits, not after.

**Why the threshold is shared.** Both are the same "this filesystem is
filling up" policy; a second constant would be a second thing to keep in
sync for no gain.

Reported, never repaired — the same contract as the byte check, for the same
reason. Wired through detection, `all_critical_state_healthy`, `--check`,
`--status` (a new `inode` column), and the post-repair postcondition. Five
bats cases added, including the btrfs `-` case; suite 74 → 79.

### DD-32: The Quantum policy file joins the canonical bundle (2026-08-02)

**Decision.** `/etc/master-stack/filebrowser.yaml` becomes the ninth entry
in the canonical bundle, verified and restored on every reconcile cycle like
the dnsmasq and Caddy files — and the restore is followed by a container
restart.

**Why it was missing.** It is new to this line. `V1-20`'s filebrowser kept
its settings in the `filebrowser_config` volume, so there was no host file to
drift; DD-27 moved policy to a host file and never added it to the bundle.
Nothing flagged the omission because nothing checks bundle membership against
"files install.sh generates".

**What that cost, measured on 2026-08-01.** Flipping `signup: false` to
`true` moved none of reconcile's signals — `config=0`, `state_config=0`,
`compose_file=0`, `compose_runtime=0`, `rc=0`. Restarting the container then
took the change live: `/api/auth/signup` went from `405` (route absent) to
`400` (route present, payload rejected). So the drift was invisible *and*
self-activating, since reconcile itself restarts containers routinely.
`signup` is not an arbitrary example — self-signup was the mechanism of the
original filebrowser's worst unpatched vulnerability (GHSA-6759, critical),
which is why the generated policy disables it.

**Why restore, not report.** `compose.yaml`'s report-only treatment (M10)
does not transfer: it is report-only because restoring it does nothing
without `docker compose up`, and because it is where an operator legitimately
experiments. Neither holds here. Rewriting this file directly fixes the
policy the container will load, and the file is generated wholesale on every
install run, so there is no operator edit to preserve.

**Why a restart follows the restore.** Quantum reads its config only at
startup, and there is no way from outside to tell whether the drifted file
was already loaded. The property worth guaranteeing is "the policy in force
equals the canonical copy", and only a restart delivers it. It shares the
15-minute per-container budget with every other filebrowser restart, so a
file that keeps being rewritten does not produce a restart loop — it produces
one restart, then a cooldown message.

**One defect found by testing this, worth recording because it recurs.** The
first version waited only for HTTP before returning, and reported `rc 1`
after a repair that had actually succeeded — the `V1-11` class again.
Measured cause: the Quantum image ships its own `HEALTHCHECK` (`start_period
10s`), and after a restart HTTP answers at t+2s while health reaches
`healthy` at t+5s; the wait exited in that gap and the postcondition caught
`starting`. The wait now checks both signals — the same two
`probe_compose_runtime` applies to filebrowser.

**Unplanned benefit.** DD-29 described a deleted policy file as the one state
a re-run could not repair, because Docker recreates the missing bind-mount
source as a *directory*. Reconcile now restores the file within twenty
minutes, long before a container recreate could reach that state. Verified:
file deleted, one reconcile run, file back at `0644 root:root`, container
healthy, `rc 0`.

### DD-33: The default-password probe runs once per cycle, and `429` is reported as unknown (2026-08-02)

**Decision.** The DD-30 check moves out of `probe_compose_runtime` into
`report_default_filebrowser_password()`, called exactly once from the main
flow, and grows a `429` branch that says the check could not be performed.

**Why once.** `probe_compose_runtime` is called up to four times in a single
cycle — initial detection, the one-second retry, again after a repair, and
once more as the final postcondition. *(Corrected 2026-08-04: five, not
four — the filebrowser policy repair added a fifth call site. The reasoning
is unaffected, the multiplier is simply larger than stated. See DD-48.)* The probe rode along with all four, so
a *drifted* cycle sent four login attempts where a clean one sent one. That
went unnoticed until the endpoint was measured.

**What the measurement found (2026-08-02).** Quantum's
`POST /api/auth/login` is rate-limited, and the bucket is keyed on **source
IP, not on the credential**: after 6 failures the endpoint returns `429`, and
from then on the *correct* password also returns `429`. The window is between
3 and 8 minutes of silence. The probe's source is `172.18.0.1`, the Docker
bridge gateway — the same address every Caddy-proxied browser login arrives
from, so reconcile and the operator share one bucket.

Those numbers decide the design. A bucket of 6 against four attempts per
cycle leaves an operator two tries before reconcile's own traffic locks the
login screen — and reconcile can trip the limit unaided. At one attempt per
cycle it cannot: the 20-minute timer interval is longer than the longest
measured window, so attempts never accumulate.

**Why `429` gets its own message.** Without the branch it fell through to the
same silent path as `401`, which means the check reported "nothing to see"
at precisely the moment someone was hammering the login screen — the one
moment it should be loudest. A security check that fails open is worse than
one that does not exist, because it is trusted. The message states plainly
that this is **not** evidence the password was changed, and that the next
cycle will retry.

**Why not fail the run instead.** Same reason as DD-30: a temporary,
self-clearing condition that the operator cannot act on must not produce
`rc 1`. It is reported, not counted.

**Why a separate function rather than a guard variable.** An "already
probed this cycle" flag would have to survive across four call sites and be
reset per-cycle — state to get wrong for no benefit. The probe has nothing to do
with the container-runtime checks it was living among; a named function
called once from the main flow says what it does and cannot be called four
times by accident.

All four paths verified live on `nrm`: the clean case (`rc 0`, one attempt,
down from four on a drifted cycle), the drifted cycle (still one attempt),
the throttled case (the `429` message, `rc 0`), and the regression case
(volume deleted → default account back → the warning fires, `rc 0` in both
the direct run and `--check`). Then confirmed end-to-end through systemd:
`Result=success`, `ExecMainStatus=0`, the warning once in the journal, zero
failed units.

> **Amended by DD-41 / Q1-20.** Once per 20-minute cycle was bounded, but
> still made the documented read-only modes send a real login request and
> spent up to 72 attempts per day after the password changed. The probe is now
> normal-reconcile-only and at most daily; `--check`/`--status` never call it.
> Live R2.5 logs measured zero POSTs for both read-only modes and one total
> across two immediate normal runs.

### DD-34: Unpackerr's file log is given a rotation cap, and the queue heartbeat is slowed to 30m (2026-08-02)

Raised by the operator noticing a long, repetitive tail in `docker logs
unpackerr` and attributing it to the 10-second folder scan. The scan was
the wrong suspect — it is completely silent (`[Folder] Polling @ 10s:
/downloads` and nothing after it). The lines come from `log_queues`,
whose default is `1m1s`: two lines a minute (`Queue: 0 waiting…` and
`Totals: …`) whether or not anything is happening. Measured on the live
host: 62 lines in 20 minutes, exactly 2/min.

**The Docker side was never the problem.** `json-file` with `max-size:
10m`, `max-file: 3` caps that stream at 30 MB, and at the measured
~226 B/min a file fills in about a month, so roughly a quarter of a year
of history is retained. The cost is legibility, not disk: while idle, the
log is 100% heartbeat.

**The real defect was the second log, the one written into the media
tree.** `UN_LOG_FILE` points at `/downloads/.unpackerr/unpackerr.log`, and
the container reported it as `(10 @ 0Mb, mode: 600)` — ten files retained,
rotation threshold zero. Upstream's example config documents
`log_file_mb`'s default as 10 MB, but that default only applies down the
TOML path; this stack configures unpackerr purely through environment
variables (`Using env variables only. Config file not found.`), and on
that path the value arrives as `0`, which upstream defines as "no
size-based rotation". So "keep 10 files" never engaged and one file grew
without bound: ~280 B/min measured, ~400 KB/day, ~145 MB/year — inside the
tree filebrowser serves, Infuse indexes and `disk_space_ok` watches.
`UN_LOG_FILE_MB: "10"` and `UN_LOG_FILES: "3"` bring it to the same 30 MB
ceiling the Docker side already had; the container now reports
`(3 @ 10Mb)`.

**`UN_LOG_QUEUES: "0"` is the intuitive fix and it is wrong.** Upstream
does not document what `0` does here, so it was measured rather than
assumed, in throwaway containers:

| `UN_LOG_QUEUES` | reported at startup | `Queue:` lines in 75s |
|---|---|---|
| unset | `1m1s` | 1 |
| `0` | **`15s`** | **5** |
| `30m` | `30m` | 0 |

Zero does not disable the heartbeat, it clamps it to a 15-second floor —
four times noisier than leaving it alone. `30m` is used instead.

**Nothing real is lost by slowing it.** Verified end to end rather than
inferred: with `log_queues` at `30m`, dropping an archive into a watched
folder still logged `Tracking New Item`, `Queued`, `Extraction Started`
and `Extraction Finished` with the file count and byte total. Only the
idle pulse goes away.

**Only `UN_LOG_FILE_MB` joins the Stage 7 environment assertion.** That
list exists for settings whose drift is *silent*. `UN_LOG_QUEUES` drifting
makes the log noisy, which is visible by definition. `UN_LOG_FILES`
drifting raises the ceiling from 30 MB to 100 MB — still bounded.
`UN_LOG_FILE_MB` drifting to `0` removes the ceiling altogether and puts
an unbounded file back inside the media tree with nothing to announce it.
The assertion was checked against a container configured both ways: it
passes on the configured one and fails on an unconfigured one, so it
discriminates rather than merely passing.

### DD-35: The Quantum policy file stays a separate host file, because `read_only: true` forbids the alternative (2026-08-02)

The operator asked to fold `/etc/master-stack/filebrowser.yaml` into
`compose.yaml` — the file the other four containers are already fully
configured from — on the reasonable grounds that a stack with one
configuration surface is easier to reason about than a stack with two.
Investigated, measured, and **not done**. Recorded here so the same three
experiments are not repeated.

**Environment variables cannot express this policy.** Every
`FILEBROWSER_*` string in the `stable` (v1.5.0) binary is either a secret
or a path: `CONFIG`, `DATABASE`, `FFMPEG_PATH`, `ADMIN_PASSWORD`,
`JWT_TOKEN_SECRET`, `OIDC_*`, `LDAP_USER_PASSWORD`, `TOTP_SECRET`,
`RECAPTCHA_SECRET`, `ONLYOFFICE_SECRET`, `GENERATE_CONFIG`,
`DISABLE_AUTOMATIC_BACKUP`. There is no variable for `server.sources`,
`server.cacheDir`, `auth.methods.password.signup` or `minLength` — that
is, for every setting this stack actually depends on. A YAML file has to
exist.

**Compose can inline it, and that part works.** A `configs:` block with
inline `content:` was tried against the real image: Quantum came up with
`Using Config file: /home/filebrowser/data/config.yaml`, `Sources: [srv:
/srv]`, and served `200`. Compose is v5.3.1 here, far past the v2.23 that
introduced inline content.

**But not on a read-only service.** With `read_only: true` the same file
is refused before the container is created:

```
cannot create config "quantum_policy" in read-only service fbprobe:
`file` is the sole supported option
```

Inline content is materialised *inside* the container at startup, which a
frozen root filesystem forbids; `file:` — a host file that already exists,
i.e. exactly today's bind mount — is all that remains. Pointing the target
at a path inside the writable volume (`/home/filebrowser/data/config.yaml`)
was tried and refused identically: the check is service-level, not
path-level. So the two goals are mutually exclusive, with no third form
available.

**What dropping `read_only` would have cost, measured rather than
asserted.** Nothing functional: `docker diff` against a container running
the same image *without* `read_only` showed **zero** writes to the
writable layer, because DD-27 already moved `cacheDir` into the volume.
That measurement is also the trap — `read_only` is a containment control,
not a functionality one. What it buys is that a compromised Quantum cannot
drop a binary in `/tmp`, edit `/etc`, or alter the application's own files;
it is confined to the two mounts it legitimately needs (`/srv` and
`/home/filebrowser/data`, both still writable, since mounts are exempt).
`docker diff` cannot see the absence of an attack, so a zero there argues
for nothing.

**What the move would have gained, so the rejected side is not
strawmanned.** The canonical bundle would drop from nine entries to eight;
the policy file's separate drift comparison and its restore-plus-restart
repair path (with the restart-budget and cooldown handling around it)
would disappear, since `compose.yaml` is already covered by both; and
DD-29's guard — the one for Docker creating a *directory* where a missing
bind-mount source should be — would become unnecessary, because that
failure mode cannot occur when the content is inline. This was a real
simplification, not a cosmetic one.

**Decision (operator, 2026-08-02): keep `read_only: true`.** The thing
being simplified away is a file the operator never touches — the installer
generates it, the bundle hashes it, reconcile repairs it. The thing given
up would have been a containment control on the one service that is
reachable across the tailnet and serves the entire media tree, and no
other mechanism substitutes for it.

**Reopen if either side of the conflict moves:** Compose gaining support
for inline configs on read-only services, or Quantum gaining environment
variables for `sources`, `cacheDir` and `signup`. Neither is true as of
Compose v5.3.1 and filebrowser Quantum v1.5.0-stable.

### DD-36: Three file-manager alternatives investigated, FileBrowser Quantum kept (2026-08-02)

Three separate investigations in one day, each ending in no change. Recorded
together because they share a conclusion and because none of them left a
trace in the code — without this entry the same searches get run again.

#### Filestash, proposed as the v3 file manager

Named "Filetash" in the request; the software is
[Filestash](https://www.filestash.app) (`machines/filestash`). Rejected on
one structural fact, found in upstream's source rather than its docs.

**Its `config.json` is runtime state, not policy.** `Save()` is called from
`Set()` (admin console writes), from `Default()`, and from `Initialise()` —
so the file is rewritten on the very first start, before anyone touches
anything. That single fact removes the architecture this branch spent most
of its effort on: the file cannot be a read-only bind mount, and it cannot
join the canonical bundle, because reconcile would revert every admin change
within twenty minutes. Going ahead would have deleted the policy-file
mechanism entirely — bundle nine entries → eight, the `quantum_config` drift
flag, the restore-plus-restart repair path, DD-29's directory guard, and
`report_default_filebrowser_password` with DD-30/DD-33 behind it.

Also weighed, none of them decisive on their own:

- **Tag hygiene is a regression.** Only `latest` is maintained (last push
  2026-07-31). No semver tags; commit-hash tags stop in 2023. DD-23 says to
  take the finest float upstream publishes — here the finest available is
  the coarsest there is, worse than every other service in the bundle.
- **The admin window is silent.** Whoever reaches `/admin/setup` first
  becomes the administrator. Quantum at least ships a *known* default that
  the installer and reconcile can both warn about.
- Upstream's own warning that the Local backend "exposes the container
  filesystem to the admin", which makes `read_only` matter more, not less.
- AGPLv3, where the current and previous file managers were not.
- Port 8334, non-root `filestash` user, `debian:stable-slim` carrying ffmpeg
  and ImageMagick.

**One thing was deliberately left unverified rather than assumed.** A
secondary source claims an `ADMIN_CONSOLE` environment variable presets the
admin bcrypt hash, which would close the setup window entirely. The primary
source does not list it and two source lookups failed. No design was built
on it. If Filestash is ever revisited, confirm it against the image first.

Blast radius, for whoever picks this up: `filebrowser` appears 56 times in
`install.sh` across roughly eighteen clusters, and `STACK_SCHEMA` would have
to bump because `IMAGE_DIGEST_FILEBROWSER` is a `state.env` key.

#### A native, non-Docker file manager that extracts RAR

Asked for next. The requirement barely has answers, and the one product that
satisfies it literally is the one to avoid.

- **FileBrowser Quantum** does not extract in place — it only zips a
  selection for download. Still an open upstream request
  ([discussion #1633](https://github.com/gtsteffaniak/filebrowser/discussions/1633)).
- **[copyparty](https://github.com/9001/copyparty)** creates archives but
  does not extract them. Otherwise the strongest candidate: one Python file,
  no dependencies, an upstream systemd unit, a plain config file that *would*
  satisfy the canonical-bundle test Filestash failed, upload hooks, and
  native WebDAV — which could absorb the separate rclone WebDAV service.
- **elFinder** does extract RAR, and that exact code path is its CVE history:
  [CVE-2019-9194](https://vuldb.com/vuln/131229) is command injection through
  crafted archive requests with filenames passed to an external utility
  unsanitised, alongside
  [CVE-2021-32682](https://www.sonarsource.com/blog/elfinder-case-study-of-web-file-manager-vulnerabilities/)
  (multiple RCEs at minimal configuration) and CVE-2022-26960. This project
  deleted filebrowser's shell-command feature specifically to be rid of this
  class; taking elFinder would walk it back in through the same door.
- **Webmin** extracts, and is a root-level system administration panel —
  far too much surface for a service published on the tailnet.

**The reframe is the useful part: RAR extraction is already solved here.**
unpackerr watches the entire media tree recursively every ten seconds and
extracts rar/zip/7z/iso with `move_back`, verified working this same day. Any
file manager that can *write* into the tree therefore already gives
browser-triggered extraction — drop the archive in, it is unpacked within
seconds. The wanted capability was never in the file manager.

Separately, leaving Docker is not free: `cap_drop: ALL`, `read_only: true`,
`mem_limit` and `no-new-privileges` all go, and an equivalent has to be
rebuilt with systemd (`DynamicUser`, `ProtectSystem=strict`,
`ReadWritePaths`, `MemoryMax`, `CapabilityBoundingSet`). That rebuild, not
the file-manager swap, is the actual work of such a migration.

#### Nextcloud as a Docker service

**Capacity is not the objection, and it was measured before saying so.** The
host is 4 vCPU / 7.8 GB RAM / 251 GB, using 863 MB, and the five containers
total roughly 130 MB. Nextcloud with MariaDB and Redis fits comfortably. The
first instinct — "too heavy" — would have been wrong.

Two things block it, both structural:

1. **Nextcloud reads its file list from `oc_filecache`, not from the disk.**
   Anything written outside it is invisible until `occ files:scan`. In this
   stack *two* services write into the media tree — qBittorrent and unpackerr
   — so every finished download and every extracted archive would be missing
   until the next scan, which upstream recommends running about every fifteen
   minutes and warns is "time- and resource-consuming if the whole storage is
   periodically scanned". Quantum reads the disk directly and simply does not
   have this problem.
2. **Major versions cannot be skipped** — "updates between multiple major
   versions and downgrades are unsupported". Bump the pin two majors and the
   container fails unrecoverably; reconcile would then restart it repeatedly
   inside its budget, the self-healing loop grinding against a state it
   cannot repair. No service currently in the bundle has this failure class.

The rest is cost rather than blockage: five containers become eight;
`read_only` is impossible for Nextcloud, which writes to `/var/www/html`
continuously; a database introduces a backup concern this stack has never
had, since losing MariaDB loses every user, share and piece of file
metadata; `cron.php` every five minutes joins `files:scan`; and Caddy needs
`OVERWRITEHOST`/`OVERWRITEPROTOCOL`/`TRUSTED_PROXIES` plus `.well-known`
redirects. The All-in-One image is structurally incompatible — it takes the
Docker socket and manages its own containers, which is the fixed-bundle
model inverted. And it does not solve RAR either.

**Verdict: the wrong tool for replacing the file manager, and the right tool
for something not being asked for.** The valid reasons to want Nextcloud are
groupware — multi-user sharing with public links, calendar and contacts,
phone photo backup, a desktop sync client, in-browser office editing. If any
of those are ever wanted, the shape is *alongside* rather than *instead*:
its own storage and subdomain, the media tree attached read-only through
`files_external`, Quantum still owning the tree. Operator's decision
(2026-08-02): excessive for a single-operator media box.

#### What would reopen each

- **Filestash** — if it starts publishing versioned tags *and* gains a way
  to hold policy separately from mutable state. One without the other is not
  enough; the config-as-state problem is the blocking one.
- **A native file manager** — if the systemd hardening equivalent is
  actually written and confinement equal to `read_only: true` is
  demonstrated, not assumed. copyparty is the candidate to start from, and
  absorbing the WebDAV service is the thing that would justify the move.
- **Nextcloud** — if groupware features are genuinely wanted. Then alongside,
  never instead.

### DD-38: DNS/Caddy file rollback commits with the canonical pointer (2026-08-02)

Stage 6 has a real transaction boundary, not merely a sequence of service
commands. Before it installs packages or writes configuration, Q1-17
snapshots these six managed paths into a root-only directory under `/run`:

- the dnsmasq zone file and dnsmasq systemd drop-in;
- the Caddyfile, Caddy systemd drop-in and `caddy-tailnet-env` helper;
- the tailscaled drop-in that pulls Caddy back after a tailscaled restart.

The snapshot records absence by the absence of a backup entry. That detail
is load-bearing on a fresh install: rollback must remove files introduced by
the failed attempt, not preserve a partial first configuration. Existing
files, directories or symbolic links are copied with metadata. Every managed
path must be absolute and must not be `/`; the restore loop refuses anything
outside that narrow shape before using recursive removal.

On failure, currently-loaded dnsmasq/Caddy units are stopped, the six paths
are restored (or removed if previously absent), systemd is reloaded, and the
entry-time active/enabled/masked vector is restored. An entry-time active
service is `restart`ed rather than merely `start`ed, so even a failed initial
stop cannot leave it running with the new in-memory configuration. The
snapshot is deleted only after every file restores successfully; otherwise
its path is printed and the root-only recovery copy remains available for
manual intervention.

The commit point is Q1-16's atomic canonical `current` swap. Before it, the
old canonical generation is authoritative and a failure restores the old
live files to match. After it, the new generation and new live files are a
consistent pair, so rollback is disabled before any later housekeeping.
This avoids the opposite mixed state: old live files under a new canonical
generation. Because pointer replacement and the shell flag update are two
commands, EXIT also resolves `current` directly: if it already names the
staging generation, the transaction is committed even if INT/TERM arrived
in the few instructions before the flag changed.

Package and apt-repository changes are deliberately outside this rollback.
Uninstalling or downgrading a package during EXIT cleanup is a much broader,
network- and maintainer-script-dependent operation. A newly installed but
disabled/masked daemon is safe, takes little space, and is reused
idempotently on the next run; reversing it adds risk without improving the
continuously-running service state this transaction protects.

### DD-39: Journal classifiers consume their complete producer stream (2026-08-02)

Stage 2 distinguishes a deleted Tailscale node from a general connectivity
failure by looking for `node not found` in tailscaled's journal since the
current install began. The distinction is useful and evidence-based: the
deleted-node branch can safely discard the worthless local profile and open
a new interactive login; the generic branch must stop and ask the operator
to diagnose network/control-plane reachability.

The classifier originally used `journalctl | grep -q` while the whole
installer runs with `set -o pipefail`. That combination is not a reliable
boolean query. `grep -q` exits as soon as it sees a match; if journalctl
still has more than a pipe buffer to write, it receives SIGPIPE and exits
141. Pipefail then makes the **matched** pipeline false. Whether the bug
appears depends on how much unrelated journal data follows the match, which
is why it presents as intermittent.

Q1-18 keeps the pipeline and its failure semantics but replaces quiet grep
with `grep -F ... >/dev/null`. The output stays silent, grep reads to EOF,
and journalctl completes normally. A real journalctl failure still makes the
pipeline fail; capturing output with `|| true` would have fixed SIGPIPE by
hiding that separate error and was therefore rejected.

This is the same shell failure mode encountered while developing DD-37's
abandoned 410 classifier, but the conclusion differs. DD-37 removed journal
diagnosis because 410 itself was ambiguous even with a correct pipeline.
Here `node not found` identifies a distinct recoverable state, so the right
fix is to preserve the classifier and make its transport correct. The old
and new forms were run against one producer with an early match plus 6,000
tail lines: rc 141 versus rc 0. Dedicated tests also cover no match and a
producer that genuinely fails after emitting a matching line.

### DD-40: FileBrowser policy replacement and activation are one retryable operation (2026-08-02)

Quantum reads `filebrowser.yaml` only at process startup. Therefore “the
live file equals the canonical file” is necessary but not sufficient: the
running process must also have restarted after that equality was established.
The earlier reconcile order violated this invariant by copying first and
checking the 15-minute restart cooldown second. If the cooldown refused the
restart, the next cycle saw equal files and lost the only evidence that the
process still held the old policy.

Q1-19 checks the budget before mutation and creates a root-only pending marker
under `/run/master-network-reconcile` before publishing the staged file. The
marker is part of `quantum_config_ok()` and is removed only after Docker health
and the direct HTTP probe both pass. Thus a failed restart, slow healthcheck or
Compose failure remains visible on the next run even though the on-disk file
is already correct. `/run` is intentionally volatile: a reboot clears the
marker, but that same reboot necessarily starts the container against the
current host path, satisfying the activation half of the invariant.

The second state is structural. Docker Compose can create a missing bind-mount
source as a directory. Copying a file to that path succeeds by placing the file
inside it, and restarting the already-created container preserves the wrong
mount contract. For a directory, symlink or other non-regular source, repair
therefore stages the canonical file first, verifies Docker is reachable,
removes only the `filebrowser` container, replaces the host path atomically,
and runs `master-compose.service` to recreate the container. It never removes
the `filebrowser_data` named volume, which is where the database, users, index
and cache live.

The full installer follows the same activation rule. Stage 4 compares both
content and metadata before replacing the generated policy; Stage 5 removes
only FileBrowser when a change was recorded, after image pull and unit
verification, and the normal Compose start recreates it. An unhealthy
FileBrowser is handled the same way, which repairs the legacy state where an
earlier swallowed removal failure left a stale directory mount behind a
now-regular host path. An identical policy on a healthy container is left
untouched. This is not a general “force recreate on every update” policy: the
extra downtime is scoped to the one service whose startup-only host policy
changed or whose runtime has already failed.

### DD-41: Reconcile repairs bounded local state, but exposes core failures (2026-08-02)

The reconcile timer is a post-install safety net, not a second installer or
an autonomous control plane. Q1-20 makes that boundary explicit by separating
two outcomes that previously shared one success-returning helper. A lock
collision or an already-active OnFailure job is transient overlap: normal
timer mode exits zero and lets the existing execution finish. Docker or
tailscaled remaining inactive, or required WAN/Tailscale addresses remaining
absent after a 30-second grace period, is an unhealthy server: reconcile exits
non-zero so systemd and the journal retain a real failure signal.

It deliberately does not restart, logout or authenticate tailscaled, and does
not restart Docker in that precondition path. Restarting either core daemon
propagates through the accepted `PartOf=` graph and can interrupt every
dependent service; a Tailscale login also requires a human browser decision.
Instead, failure reports the daemon state plus Tailscale's backend, self-online,
health and key-expiry fields. The core daemon's own restart policy, an explicit
installer rerun, or the operator remains responsible for the broader action.

Compose recovery follows the same bounded-local-state rule. An existing
regular `root:root 0600` file with different content may be an intentional
operator edit and remains report-only. A genuinely absent file is not an edit:
reconcile restores it atomically from the checksum-verified canonical
generation without restarting healthy containers. Metadata drift is repaired;
a directory, symlink or other unsafe target is refused rather than removed.
The service's `ConditionPathExists` gate was removed because it prevented the
very recovery process that could reconstruct the file from running.

Observation must also be read-only in practice, not only by name. The
FileBrowser default-password check is a real login POST and consumes a
source-IP rate limit, so `--check` and `--status` no longer issue it. Normal
reconcile may probe only a running container and only once per 24 hours, with
an atomic root-only `/run` stamp recorded before the request. This preserves
the useful reminder without turning a 20-minute health timer into a login
storm.

Finally, the host WebDAV unit independently declares
`RequiresMountsFor=$DOWNLOADS_PATH/media`. Compose's mount dependency cannot
protect a separate host service; without its own ordering rclone could serve
the empty directory hidden underneath a late or failed mount while every HTTP
probe still looked healthy. This dependency fails or delays WebDAV instead of
presenting the wrong tree as a healthy service.

**Live confirmation before R2.5.** On Debian, an active tailscaled daemon was
taken offline with `tailscale down`. Reconcile observed `Stopped/false`, waited
exactly 30 seconds, exited 1 and journaled the backend and health messages; it
did not restart or reauthenticate the daemon. Bringing the same node/IP online
and allowing the existing firewall/core recovery returned every drift flag to
zero. Missing, edited, metadata-drifted and symlink Compose targets each took
the branch described above without changing container start times. Container
logs also proved `--check`/`--status` issued no login POST and two immediate
normal runs issued one total. WebDAV's dependency passed both full Stage 7
runs; the host does not use a separate media mount, so no artificial mount
failure was claimed.

### DD-44: `install.sh` comments say what a block does; the rationale lives here (2026-08-03)

- **Decision:** comment blocks in `install.sh` are one to six short lines
  stating what the code does and, where a choice is non-obvious, naming the
  constraint in a clause — not reconstructing how it was found. The
  measurement narratives, the wrong first attempts and the dated evidence stay
  in this file, in `SECURITY_REVIEW.md`'s Review History and in `CHANGELOG.md`.
  A comment that needs the full story points at it (`bkz. DD-42`, `M11`, `H4`)
  rather than repeating it. Applied wholesale in `Q1-24`: 1179 comment lines
  became 517 across 229 blocks, with no change to any non-comment line.
- **Why:** the file had reached the point where reading the code meant reading
  around the commentary. Stage 2's login section carried 37 consecutive comment
  lines before its first statement; the image-tag block ran 28; several blocks
  recounted three superseded designs before describing the current one. That
  material is genuinely valuable — it is why `UN_LOG_QUEUES=0` was not used and
  why the journal is not consulted for the 410 wedge — but it is reference
  material, consulted when changing a decision, not when reading the code that
  implements it. Keeping it inline taxed every read to serve the rare one.
- **Why the rationale is not simply deleted.** Every long block removed here
  already had a durable home. `DD-37`/`DD-42` hold the login archaeology,
  `DD-18`/`M11` the socket-buffer ordering, `DD-23` the float-tag digests,
  `M1` the absent `mem_limit`, `DD-27` the FileBrowser admin account, `DD-40`
  the policy-file activation. The reduction moved the reader one hop away from
  the story, it did not end it — and the surviving one-liners keep the pointer
  so the hop is findable.
- **What was deliberately not touched:** the eight `#!` shebangs, the single
  `# shellcheck disable=SC1091` directive, and the eight `# AŞAMA N — …`
  banners. The first two are load-bearing, and the banners are the file's
  only structural navigation.
- **How it was verified.** The transformation was applied by an explicit
  line-range map rather than a pattern rule, so nothing outside the 229 listed
  ranges could be reached; the script asserts every targeted line is a comment,
  is not a shebang and is not a `shellcheck` directive before writing anything.
  The proof that no behaviour changed is a diff of both revisions with all
  whole-line comments stripped: 5351 lines, byte-identical.
  `./scripts/check-all.sh` clean at 176 cases.

> **Amended 2026-08-03 (`Q1-25`).** The decision above kept a one-to-six-line
> "what this does" comment on each block. The operator's follow-up removed even
> those: *"yorum satırlarını eğer yükleme esnasında ekrana yazılmıyorsa direkt
> kaldırabiliriz. koda çıplak bakmayacağımız için görmemiz mümkün değil
> aslında."* `install.sh` now carries **no explanatory comments at all** —
> 508 further lines removed, 5868 → 5356, leaving nine `#` lines: eight `#!`
> shebangs and one `# shellcheck disable=SC1091`.
>
> Both survivors are load-bearing rather than editorial. The shebangs set the
> interpreter for the seven heredoc-generated helper scripts. The `SC1091`
> directive suppresses a real warning on `source /etc/os-release`; deleting it
> breaks `shellcheck install.sh`, which is check 2 of `./scripts/check-all.sh`.
> The eight `# AŞAMA N — …` banners did **not** survive: each is immediately
> followed by a `progress_stage_begin N "…"` call that prints the same
> information to the operator's screen, so the banner duplicated a line the
> code already emits. Stage boundaries remain locatable by `grep -n
> 'progress_stage_begin [0-7] '`, which is what `docs/architecture.md` already
> told readers to use.
>
> The premise is the operator's own working method rather than a general claim
> about comments: this script is read through its documentation and its printed
> output, not opened in an editor. A comment nobody reads is not neutral — it
> is 22% of the file standing between the reader and the code, and it decays
> silently because nothing verifies it. The rationale is unaffected; it was
> already relocated by `Q1-24` and is still here, in `SECURITY_REVIEW.md`'s
> Review History and in `CHANGELOG.md`.
>
> **Verified the same way, and one class was checked that `Q1-24` did not
> need.** Removal is a blanket rule this time, so a `#` line that was *content*
> rather than a comment would be silently destroyed — a YAML block scalar
> (`key: |`) is the one place in this file where that could happen, since
> `filebrowser.yaml` and `compose.yaml` are both generated from heredocs.
> There are none: the pattern `:\s*[|>]` does not occur anywhere in the
> pre-removal file. Every other generated format treats a leading `#` as a
> comment (dnsmasq, systemd units, Caddyfile, `sysctl.d`, `modules-load.d`).
> The proof that nothing else moved is a diff of both revisions with all
> whole-line comments and blank lines stripped: **4790 lines, byte-identical**.
> Four blank-line runs created by the removal were collapsed to one.
> `./scripts/check-all.sh` clean at 176 cases.

### DD-46: A failed canonical bundle verification degrades reconcile instead of aborting it (2026-08-04)

- **Decision:** `canonical_bundle_ok`'s result is now a flag,
  `CANONICAL_BUNDLE_INVALID`, not an immediate `exit 1`. When it is set,
  reconcile reports the reason, skips **only** the blocks that read the
  canonical bundle, runs every other check and repair as usual, and still
  exits 1 at the end.
- **What is withheld:** the compose.yaml restore, the filebrowser policy
  restore and its container recreate, the `state.env`/dnsmasq/Caddy restores,
  and the dnsmasq/Caddy restarts that only make sense after those restores.
- **What now keeps working:** address re-binding into `/root/docker/.env`,
  IP-forwarding sysctl repair, `tailscale set` prefs/netfilter repair, the
  MASTER firewall renewal and `docker-tailscale-fw` restart, the Docker
  netfilter core-recovery hand-off, the UDP GRO repair, container restarts,
  the master-compose lifecycle, host WebDAV restart, and all disk/inode
  reporting. None of them reads the bundle.
- **Why:** the old gate was the widest blast radius in the script. Any one of
  the nine canonical entries carrying a wrong mode bit — or `SHA256SUMS`
  disagreeing on one byte — disabled the entire self-healing loop, including
  every repair that has nothing to do with the bundle, and produced one line
  of output every 20 minutes forever. A public-IP change on such a host would
  never be picked up; the firewall would never be renewed. The failure the
  gate protects against is "the reference copy is untrustworthy", which is a
  reason to refuse to *copy from* it, not a reason to stop looking at
  anything.
- **Why this shape and not a new one:** the script already answers this exact
  question in `CANONICAL_CONFIG_INVALID` — set a flag when the canonical
  runtime configs do not parse, report it, gate the dependent restore and
  restart blocks, force `RECOVERY_FAILED=1`. Q1-27 applies that established
  pattern to the second, broader case rather than inventing a third
  behaviour. Wherever `CANONICAL_CONFIG_INVALID` gates,
  `CANONICAL_BUNDLE_INVALID` gates too: an unverifiable bundle subsumes an
  unparseable config.
- **Degrading is not passing.** The flag is a member of
  `all_critical_state_healthy`, so `--check` cannot return 0 while it is set;
  it forces `RECOVERY_FAILED=1` alongside `CANONICAL_CONFIG_INVALID`; and the
  end-of-run postcondition sweep still calls `canonical_bundle_ok` directly,
  so a bundle broken *during* the run fails it even if the flag was clear at
  start. `--check` now emits `canonical_bundle=` so the reason is visible in
  `master-network --status` rather than only in the journal.
- **One hard exit is deliberately left in place.** The `STACK_SCHEMA` /
  port-shape gate immediately after still exits 1, because every later check
  consumes those values and there is no honest default to substitute. If the
  bundle is invalid *because* `state.env` is unreadable, reconcile stops
  there — but it prints the bundle diagnosis first, which is why the message
  is emitted at flag time rather than in the later drift report.
- **Amended 2026-08-04 (`Q1-31`) — the drift report was promising a restore
  it would not perform.** Live testing showed reconcile printing "canonical
  kopya geri yüklenecek" and then correctly withholding the restore, because
  that sentence predates this decision and was written when a restore always
  followed. The state/DNS/Caddy and filebrowser policy report lines are now
  conditional: with the bundle or the runtime configs unverifiable they say
  the restore will *not* happen, and go to stderr. The gating itself was
  right the whole time; only the sentence was wrong.
- **Live-verified 2026-08-04.** With one canonical file's mode broken,
  reconcile reported the bundle failure, repaired `net.ipv4.ip_forward`
  0 → 1 (a bundle-independent repair `Q1-22` would never have reached), left
  the drifted `/etc/caddy/Caddyfile` untouched, kept caddy running and exited
  1 with `canonical_bundle=1` in `--check`. Restoring the mode made the next
  run restore the file and exit 0.
- **Verified by mutation.** `test/canonical_bundle_degrade.bats` derives the
  invariant from install.sh's own text rather than restating the current
  lines: it splits reconcile's recovery half into top-level `if` blocks and
  asserts that every block whose body touches `$CANONICAL_DIR/` or calls
  `restore_missing_compose_file`/`restore_quantum_config` is gated on the
  flag, so a *new* ungated restore site fails the suite without anyone
  remembering to extend it. Four mutations were run against install.sh and
  each was caught: ungating the `state.env` restore, restoring the old
  `exit 1`, dropping the flag from `all_critical_state_healthy`, and
  over-gating the bundle-independent forwarding repair.
  `./scripts/check-all.sh` clean at 183 cases.

### DD-47: `cleanup_master_setup` asks `canonical_stage_is_current` instead of re-deriving it (2026-08-04)

- **Decision:** the staged-generation cleanup in `cleanup_master_setup` now
  calls `canonical_stage_is_current` rather than resolving
  `/usr/local/share/master-stack/current` itself and comparing the result
  against the raw `$CANONICAL_STAGE_DIR` string. The local
  `canonical_active_target` and its `readlink` are gone; the
  `.generation.*` `case` allowlist around `rm -rf` stays untouched.
- **Why:** one question was asked twice, two different ways, inside one
  function. `restore_dns_stack_on_failure` — called at the top of the same
  cleanup — used the predicate, which normalises **both** sides with
  `readlink -f`. The staged-directory block a hundred lines later resolved
  only the `current` symlink and compared it against the unresolved `mktemp`
  output, and hardcoded the root path instead of using `$CANONICAL_ROOT`.
- **The failure mode is self-destructive, not merely untidy.** Let any path
  component above the canonical root be a symlink and the two halves of one
  cleanup run answer differently: the DNS rollback snapshot is discarded as
  "already published" while the directory `current` points at is `rm -rf`'d
  as "not published". What remains is a `current` symlink to nothing, so
  `canonical_bundle_ok` fails on every subsequent reconcile. Since Q1-27 that
  no longer stops all repair (DD-46), but canonical restore is dead for good
  and no automatic path recreates the generation.
- **The equality branch is not dead and was not removed.** A signal arriving
  between the `mv -Tf` pointer swap and the `CANONICAL_STAGE_DIR=""` reset
  lands in `cleanup_master_setup` with the variable still set and `current`
  already pointing at the staged directory; keeping it is correct, and
  `test/dns_stack_rollback.bats` pins that ordering deliberately ("a
  committed current pointer closes the signal window before the flag
  update"). What Q1-28 removes is the second implementation of the
  predicate, not the branch it guards.
- **`[[ -n "$CANONICAL_STAGE_DIR" ]]` is kept** even though
  `canonical_stage_is_current` already returns 1 on an empty value. It makes
  "nothing was staged, so there is nothing to clean" explicit instead of
  leaving the `rm -rf` to be stopped by the `case` allowlist alone.
- **Verified by mutation.** `test/canonical_stage_cleanup.bats` lifts the
  block out of `cleanup_master_setup` (which cannot be sourced — it resets
  traps and exits) and runs it, in two forms: verbatim, for the allowlist
  case, and with the allowlist re-rooted at the fixture, without which the
  hardcoded `/usr/local` prefix would make every fixture path survive and
  the behavioural cases would pass vacuously. Four mutations were applied to
  install.sh and each was caught by a specific case: restoring the old inline
  comparison, dropping the allowlist, inverting the predicate, and removing
  the stage-side `readlink -f` inside the predicate — the last of which also
  fails an existing `dns_stack_rollback.bats` case, which is the point.
  `./scripts/check-all.sh` clean at 194 cases.

### DD-48: `probe_compose_runtime` measures; the caller reports (2026-08-04)

- **Decision:** `check_compose_runtime` is renamed `probe_compose_runtime`,
  its two `echo ... >&2` lines are removed, the observed WireGuard port is
  handed back in a new `WG_OBSERVED_PORT` global, the detection site reports
  both wg-easy conditions once per cycle, and `--check` gains
  `wg_setup=`/`wg_config=`.
- **Why:** the function is a predicate, a mutator of four globals, and — until
  now — a reporter, and it is called **five** times in a reconcile cycle:
  initial detection, the one-second retry, again after the filebrowser policy
  repair, as the post-start postcondition, and in the final sweep. Three of
  those five are pure predicate positions (`if ! …`, `elif ! …`, `! … ||`
  inside a compound condition), so each silently recomputed
  `COMPOSE_RESTART_TARGETS`, `WG_CONFIGURATION_INVALID` and
  `WG_SETUP_PENDING` where the caller wanted only a boolean.
- **This is DD-33 finished, not a new idea.** DD-33 moved the filebrowser
  password probe out of this same function for this same reason — "the probe
  rode along with all four" calls. The two stderr lines were left behind and
  kept the multiplier: a host with a wg-easy port mismatch printed the same
  error four times per cycle, plus the caller's own line, every twenty
  minutes, for a condition the script explicitly refuses to auto-repair.
- **`--status` was the visible damage.** It captures `--check` with `2>&1`
  (`status_check_output="$("$0" --check 2>&1)"`), so those prose lines landed
  inside the machine-readable `key=value` block, one or two copies deep.
  They are now data in that block instead.
- **Where the report goes matters.** It sits at the detection site rather
  than in the drift report, because `WG_SETUP_PENDING` deliberately does not
  set `runtime_ok` (DD-12/H6) — a host whose only issue is a pending wg-easy
  setup passes `all_critical_state_healthy` and exits before the drift report
  is ever reached. Reporting there would have silently deleted the signal.
- **No live bug was found.** Every reset was traced against every reader:
  none of them changes a decision today, because `RECOVERY_FAILED` latches
  one-way and the final sweep re-measures. The finding is that correctness
  rests on "nothing reads these after the reset", which nothing enforces.
- **Two things deliberately left alone.** The five calls are not reduced —
  three of them are postconditions whose whole purpose is to re-measure after
  a mutation, and caching would defeat them. And the retry asymmetry (the
  detector retries after `sleep 1`, the postcondition does not) is correct,
  not an oversight: `master-compose.service` is `Type=oneshot` with
  `docker compose up -d --wait --wait-timeout 180`, so `systemctl start`
  returns only after Docker has settled health, while the detector runs cold.
- **The function had no tests at all.** Its component probes are covered in
  `test/reconcile_probes.bats`; the 110-line composite that resets four
  globals from five call sites was not. `test/compose_runtime_probe.bats`
  now pins the contract with stubbed component probes, including DD-12/H6's
  rule that a pending setup must not fail the probe — a regression there
  breaks every fresh install at Stage 7, which is how H6 was found. Seven
  mutations were applied to install.sh and each was caught by a specific
  case: printing from inside the probe, making `/setup` count as drift,
  dropping the reset block, queueing a restart for a port mismatch, treating
  `starting` health as healthy, removing the caller's report, and dropping
  the new `--check` keys. `./scripts/check-all.sh` clean at 206 cases.
- **Corrections made along the way:** DD-12 claimed the `/setup` branch sets
  `WG_CONFIGURATION_INVALID` and that `RECOVERY_FAILED` therefore surfaces it
  every cycle; both stopped being true when `WG_SETUP_PENDING` was split out.
  DD-33 says four call sites; there are five. Both entries carry dated
  amendments. The old function name is kept verbatim in `CHANGELOG.md`,
  `SECURITY_REVIEW.md` and completed `TODO.md` items, which record what was
  true at the time.

### DD-49: Every unit on the `OnFailure` arc is restarted behind the repair cooldown (2026-08-04)

- **The arc.** Five units declare `OnFailure=master-network-reconcile.service`
  — `docker-tailscale-fw`, `master-compose`, `master-webdav`, and the `dnsmasq`
  and `caddy` drop-ins — and reconcile restarts all five. Every edge runs in
  both directions.
- **Why the synchronous case does not spin.** When reconcile's own
  `systemctl restart X` fails, X enters `failed` and raises an `OnFailure`
  start job for reconcile *while reconcile is still active*; systemd merges it
  into the running job, so no second run happens. `master-network-reconcile`
  itself carries neither `OnFailure=` nor `Restart=`, so the arc terminates
  there rather than re-entering.
- **The asynchronous case is the real one.** A daemon that starts cleanly
  (`systemctl restart` returns 0), lets reconcile finish and exit, then dies
  seconds later trips `Restart=on-failure`, hits its start limit, fails, and
  fires `OnFailure` with reconcile inactive. That runs reconcile *immediately*
  rather than on the twenty-minute timer, and the run's first act is to
  restart the same daemon again.
- **Decision:** the `master-webdav`, `dnsmasq` and `caddy` restart paths now
  go through `restart_budget_available` / `record_container_restart`, matching
  the four paths that already did (`tailscale-udp-gro`, `master-compose`,
  the filebrowser policy repair, the generic container targets). A deferred
  restart reports `cooldown içinde; tekrarlanmadı` and sets
  `RECOVERY_FAILED=1`, exactly as the existing paths do.
- **Why those three specifically:** they were the only restart sites in
  reconcile with no budget call, and they are also the three arc units with
  `Restart=on-failure` plus a `StartLimit`. Worse, each called
  `systemctl reset-failed` first — which clears systemd's start-limit counter,
  the *other* brake. So the arc's three most restart-prone units had both
  brakes removed, one by omission and one deliberately.
- **`reset-failed` stays.** Without it a unit parked in "start request
  repeated too quickly" can never be recovered by reconcile at all. It is now
  simply unreachable until the budget allows a restart.
- **This is DD-21's own stated purpose, applied where it was missing.** DD-21
  calls the cooldown "a brake on the event-driven (`OnFailure`) paths, which
  can fire at any moment", and `docs/testing.md` calls it "the only thing
  between a repeatedly-failing repair and a restart loop". Both were written
  while three of the five arc units bypassed it.
- **What bypasses the budget, and why.** `TAILSCALE_ADDRESS_CHANGED` — all
  three daemons bind that address, so deferring the rebind would leave them
  listening on an address that no longer exists; this is the same exemption
  `master-compose` already had for `ADDRESS_CHANGED`. And
  `DNS_CONFIG_DRIFTED` / `CADDY_CONFIG_DRIFTED` — restoring a canonical config
  and then not restarting the daemon would leave it serving the old one.
  Neither is a failure signal. `*_INACTIVE` and `*_RUNTIME_DRIFTED` are, and
  they are gated.
- **One site is deliberately left ungated:** `systemctl start
  master-compose.service`, which is also reached via `COMPOSE_INACTIVE`. There
  the whole stack is down, and a fifteen-minute wait costs far more than a
  slow retry. That loop is bounded by construction anyway — each attempt runs
  `docker compose up -d --wait --wait-timeout 180` under
  `TimeoutStartSec=330`. The `docker-tailscale-fw` restart is also not gated
  in its own block, because it only runs under `STACK_RESTART_REQUIRED`, which
  an earlier block sets behind `restart_budget_available master-compose`.
  Both exemptions are named in `test/onfailure_arc.bats` with their reasons,
  so adding a third is a conscious act rather than an omission.
- **What changes on a live host.** A caddy (or dnsmasq, or WebDAV) that is
  down is now restarted at most once per fifteen minutes instead of once per
  reconcile run. Scheduled runs are unaffected: DD-21 set the interval to
  twenty minutes precisely so it exceeds the cooldown. Only the event-driven
  storm is braked.
- **Verified by mutation.** `test/onfailure_arc.bats` derives the arc's unit
  set from install.sh's own `OnFailure=` lines and walks every top-level
  if-block of the reconcile script, so a *new* unit wired onto the arc and
  restarted unbraked fails the suite without anyone extending it. Seven
  mutations were applied and each was caught: removing caddy's gate, letting
  `CADDY_INACTIVE` bypass it, removing the address-change exemption, renaming
  the restart stamp so writer and reader disagree, dropping the deferral's
  `RECOVERY_FAILED`, giving `master-network-reconcile.service` a `Restart=`,
  and adding a sixth unit to the arc with an ungated restart.
  `./scripts/check-all.sh` clean at 215 cases.
- **Amended 2026-08-04 (`Q1-31`) — the exemption must bypass the brake, not
  consume it.** The first live run found a defect in this decision as
  originally shipped: `record_container_restart` was called on the exempt
  path too, so a legitimate Caddyfile restore stamped the budget and then a
  genuine caddy failure three minutes later was refused for fifteen minutes.
  Caddy sat `inactive` while reconcile reported `cooldown içinde` — strictly
  worse availability than before `Q1-30`. Each block now sets an explicit
  `*_RESTART_EXEMPT` flag and stamps only when the budget path was actually
  taken. The brake still engages, one restart later: a failure-driven restart
  always consults and stamps, so the second one in fifteen minutes is
  refused. Verified on the host in both directions — exempt restart leaves no
  stamp and the following failure is repaired; the failure after that is
  braked, with dnsmasq repaired in the same run to confirm per-unit scoping.
- **`master-compose` has the same property and was left alone.** Its
  `ADDRESS_CHANGED` bypass still calls `record_container_restart`, so an
  address change spends the stack's budget. That is pre-existing behaviour
  outside this decision's scope; it is recorded in `TODO.md` rather than
  changed unasked.
- **Live-verified 2026-08-04** except the systemd job-merging claim, which is
  reasoning about documented behaviour rather than a measurement; confirming
  it needs a deliberately crash-looping daemon.

### DD-52: `--check` does not pay a readiness wait for a value no rule uses (2026-08-04)

- **Decision:** `TAILSCALE_IPV4` is deleted from `docker-tailscale-fw`. The WAN
  IPv4 resolution it shared is split into `resolve_wan_ipv4` (one attempt) and
  `wait_for_wan_ipv4` (a wall-clock deadline). `apply` waits; `--check`
  resolves once and exits 1 immediately when the addresses are absent.
- **The value was dead, and its origin is in the history rather than in a
  design.** `V1-3` (`9b8d754`, 2026-07-30) replaced the sftpgo container with
  the host rclone WebDAV service and deleted the only two places
  `$TAILSCALE_IPV4` was used inside the helper — the
  `--ctorigdst "$TAILSCALE_IPV4" --ctorigdstport 65113` allow in
  `MASTER-TS-FORWARD` and its matching string in `check_ipv4_policy`'s expected
  set. The 300-second gate that resolved the value stayed behind. Across the
  helper's 489 lines the name appeared four times, all four inside that gate.
- **Measured before the change, on the test host, against the deployed helper**
  (byte-identical to the repository's, `8ae63f6c…`): a healthy `--check`
  returns in **0.162 s**; with no IPv4 on `tailscale0` it returns in
  **305.9 s** with `HATA: Firewall için Tailscale IPv4 300 saniyede hazır
  olmadı.` The message identifies the branch, which is how we know
  `check_policy` was never reached.
- **What those five minutes cost reconcile.** Reconcile calls `--check` at
  three sites. The first (`FIREWALL_DRIFTED`) is unconditional, and a non-zero
  exit there is indistinguishable from real policy drift, so the wait cannot
  change the outcome — it only delays it. `FIREWALL_DRIFTED=1` then sets
  `STACK_RESTART_REQUIRED=1`, which consumes `master-compose`'s restart budget,
  stops the stack, restarts `docker-tailscale-fw.service` (whose `apply` pays
  the same gate again under `TimeoutStartSec=600s`) and re-runs `--check`. On a
  host whose node has gone addressless one reconcile turn spends roughly
  fifteen of the timer's twenty minutes and bounces the Compose stack — driven
  entirely by a value no rule references. The third call site is spared only
  incidentally: `! tailscale_online` precedes it in the same `||` chain.
- **The apply-side risk was measured, not reasoned about.** Removing the gate
  shortens `apply`'s settling window, so the question is whether it was
  guarding `ensure_forward_prefix`'s real precondition — the `ts-forward`
  chain. A probe sampling every 200 ms across a real reboot of the test host
  answered it: at **+1.16 s** `ts-forward` existed in both families and the
  `FORWARD` jump was installed while `tailscale0` still had **no** IPv4, which
  arrived at **+1.37 s**. The chain is ready *before* the address, so the
  address gate never was what protected it; `ensure_forward_prefix`'s own
  30-second `wait_for_chain` is the guard, and it is unchanged.
  `docker-tailscale-fw.service` ran at +4.6 s and finished in 0.77 s.
- **Why the deadline shape changed too.** The old loop was `for _ in $(seq 1
  300)` with `sleep 1` and three `ip` invocations per turn, so it counted
  iterations while its message promised seconds — DD-50's finding, in the other
  program. The 305.9 s measurement is that drift. `wait_for_wan_ipv4` computes
  a deadline from `SECONDS`, so the printed 300 seconds is the real bound
  whatever a probe costs.
- **`apply` still waits, deliberately.** `PUBLIC_IPV4` is interpolated into
  three `MASTER-DOCKER` rules, so it is load-bearing there and a boot-time
  absence is worth waiting out. In `--check` the same absence means only "this
  cannot be verified right now", which is already what the caller does with it.
- **Verified by mutation, and one mutation corrected the tests rather than the
  code.** Five mutations were applied and each was caught: reintroducing the
  `TAILSCALE_IPV4` resolution, routing `--check` through `wait_for_wan_ipv4`,
  reverting the deadline to an iteration count, sleeping before the first
  attempt, and making `resolve_wan_ipv4` always succeed. The last one initially
  escaped two cases written as `! resolve_wan_ipv4`: bash exempts an
  `!`-inverted command from `set -e`, so that form asserts nothing unless it is
  a test's final line. Those cases now capture the status explicitly. Nine
  other non-final `!` assertions exist across seven `.bats` files and are
  recorded in `TODO.md` as their own item — not all are dead, since several are
  followed by a stronger sibling, but none of them currently prove that.
  `./scripts/check-all.sh` clean at 239 cases.

### DD-54: Readability is not trust — reconcile stops reading configuration from a bundle it rejected (2026-08-05)

- **Decision:** `state_value` consults `$CANONICAL_DIR/state.env` only when
  `CANONICAL_STATE_TRUSTED` is set, which happens exactly where
  `canonical_bundle_ok` returns true. Otherwise it reads `$STATE_FILE`, the
  live configuration the running system was actually built with.
- **The contradiction, measured in a single run.** With `STACK_VERSION` edited
  in the canonical copy so `sha256sum -c` fails, one `--status` printed
  `canonical_bundle=1` and "bundle doğrulaması başarısız; canonical kopyadan
  geri yükleme yapılmayacak" *and* `Kurulum sürümü :
  TAMPERED-NOT-A-REAL-VERSION` — read from the file it had just declared
  untrustworthy, while the intact `/etc/master-stack/state.env` sat unread.
  Side by side afterwards on the same tampered bundle: `Q1-34` prints the
  tampered string, `Q1-36` prints the real `2026.08.04-Q1-34`.
- **`STACK_VERSION` was only the visible symptom.** The same call supplies
  `QBIT_PUBLIC_PORT`, `WG_PUBLIC_PORT`, `WEBDAV_PORT`, `LOCAL_DOMAIN`,
  `WG_ENDPOINT_HOST` and `DOWNLOADS_PATH`. Those feed the DNAT rule checks,
  the container port-binding checks, the DNS and Caddy probes and the disk
  thresholds — so a bad bundle could have redirected what reconcile *repairs
  toward*, not merely what it reports.
- **This is the missing half of DD-46.** That decision stopped a failed bundle
  check from aborting the run, so bundle-*independent* drift still gets
  repaired. It did not notice that the repairs were still taking their
  parameters from the distrusted file. The two together now say the same
  thing: a bundle that fails verification is not read for any purpose.
- **Why the live file is the right fallback rather than the built-in
  defaults.** `$STATE_FILE` is what the installer wrote and what the running
  units were configured from. Falling back to `state_value`'s defaults would
  invent a configuration the host never had. The existing `STACK_SCHEMA != 10`
  guard still fails the run closed if the live file is missing or malformed.
- **Both entry paths had to be fixed, and only one was obvious.** The main
  path decides at the existing gate. `--status` calls `state_value` roughly a
  hundred lines *earlier* than that gate, which is exactly where the
  contradiction was measured, so it now evaluates `canonical_bundle_ok` before
  printing anything. That is a second `sha256sum -c` over nine small files per
  `--status`; measured as immaterial next to the `--check` subprocess that
  mode already spawns.
- **One older test was rewritten rather than worked around.** DD-46's
  "the bundle gate sets a flag instead of exiting" pinned the literal string
  `if ! canonical_bundle_ok; then`, which the new success arm no longer uses.
  It now asserts the behaviour — the gate calls the predicate, sets the flag,
  never exits, still explains itself, and raises the trust flag — instead of
  the syntax. Its `! grep` line was also converted to an explicit status
  capture, since a non-final `!` asserts nothing.
- **Verified by mutation.** Three, each caught by the case that claims it:
  restoring the readability-only condition, defaulting the flag to trusted,
  and deleting the `--status` branch's decision. `./scripts/check-all.sh`
  clean at 245 cases.

### DD-56: The Compose stack does not depend on the Tailscale address (2026-08-05)

- **Decision:** `master-compose-ipv4` no longer treats the Tailscale IPv4 as a
  precondition for starting the stack — it waits for it, records it when it
  arrives, and starts anyway when it does not. `STACK_RESTART_REQUIRED` is
  keyed on `PUBLIC_ADDRESS_CHANGED` rather than the union `ADDRESS_CHANGED`.
  A stale address record is refreshed by running the helper directly, without
  touching any container.
- **The same origin as DD-52.** `V1-3` (`9b8d754`) replaced the sftpgo
  container with the host rclone WebDAV service and deleted
  `"${TAILSCALE_IPV4}:${WEBDAV_PORT}:…"`, the only place compose ever used the
  address. Two consumers were left behind pointing at it: a 120-second hard
  gate in front of the whole stack, and a five-container restart on every
  change.
- **Measured on the test host before the change.** `.env` carried
  `TAILSCALE_IPV4=100.121.18.22`; `compose.yaml` referenced it zero times; the
  address occurred **zero times in the fully rendered `docker compose
  config`**; every container port bound `127.0.0.1` or the public IPv4; and
  the only listeners on the Tailscale address were host services — dnsmasq
  :53, Caddy :80, rclone WebDAV :65113 and tailscaled :53071.
- **`PUBLIC_IPV4` stays a hard precondition** and its wait is unchanged,
  because it *is* interpolated into three container port bindings. The
  asymmetry is the point: one address is in the compose file, the other is
  not.
- **The refresh is the part that is easy to get wrong.** Removing the stack
  restart removes the only thing that used to rewrite `.env`, and `.env` is
  what `TAILSCALE_ADDRESS_CHANGED` is computed against. Left there, the flag
  would latch at 1 and restart dnsmasq, Caddy and WebDAV every twenty minutes
  forever. So reconcile now refreshes the record itself whenever it is stale,
  through the same `master-compose-ipv4` helper, which only rewrites `.env`
  atomically and never touches a container.
- **The predicate is shared rather than duplicated.**
  `compose_env_addresses_current` is what both the refresh and the final
  postcondition ask, so the condition that triggers the repair and the
  condition that accepts it cannot disagree. It is also the reason the refresh
  is correct regardless of which earlier block ran: it asks whether the record
  is stale *now*, not whether some particular repair happened.
- **The three genuine consumers are untouched.** `master-webdav`, `dnsmasq`
  and `caddy` still repair directly on `TAILSCALE_ADDRESS_CHANGED`; a test
  pins that all three arms survive, because the obvious way to get this wrong
  is to delete the signal along with the restart.
- **Verified by mutation.** Five, each caught by the case that claims it:
  restoring the Tailscale hard gate, dropping the WAN hard failure, routing
  the union flag back into the stack restart, deleting the refresh, and
  removing one of the three host-service repair arms. `master-compose-ipv4`
  is extracted and run for real against stub `ip` output, with `STACK_DIR`
  redirected out of `/root` and the budget shortened — both substitutions
  asserted after the fact so the case cannot silently test the wrong script.
  `./scripts/check-all.sh` clean at 258 cases.

### DD-57: A probe in a predicate position puts back what it measured (2026-08-05)

- **Decision:** the two postcondition positions that ask "is the Compose
  runtime still healthy?" call `compose_runtime_still_ok`, a wrapper that saves
  the four globals `probe_compose_runtime` resets, runs the probe, restores
  them and returns the probe's verdict. The three positions that *measure*
  still call the probe directly, because they consume what it publishes.
- **Why it is not simply a probe with no side effects.** DD-48 already moved
  the printing out of this function; the four globals could not follow, because
  they are the function's actual output. `COMPOSE_RESTART_TARGETS` is the list
  the repair loop restarts, and `WG_SETUP_PENDING` /
  `WG_CONFIGURATION_INVALID` / `WG_OBSERVED_PORT` are what the operator report
  and `--status`'s key=value line are built from. A predicate that computes
  them is fine. A predicate that *replaces* them behind the caller's back is
  not, and both shapes were the same call.
- **Latent, not live, and recorded that way.** Nothing reads the four globals
  after either postcondition — the report at the detection site, the wg-easy
  diagnostics and the restart loop all run earlier in the linear script. This
  was measured by ordering, not assumed: the last reader is the eligible-target
  loop, and both wrapper sites are below it. So this changes no behaviour
  today. It is fixed because the failure it sets up is invisible: a later line
  added below the postcondition reads a measurement of the world *after* the
  repair, silently, with nothing in the code to suggest that is what happened.
- **What makes the wrapper's reads safe.** Nothing declares those three `WG_*`
  globals at top level — the probe is their only writer. Under the reconcile
  script's `set -Eeuo pipefail` a wrapper call with no prior probe would abort
  the cycle on an unbound variable rather than measure anything. That is
  currently impossible because the detection call is unconditional, at top
  level, and above both wrapper sites; a case pins exactly that ordering rather
  than trusting it. Adding `:-` defaults was considered and rejected: it would
  turn "this ran too early" from a loud abort into a silent zero.
- **The restart-target restore is guarded on count.** `saved_targets=(
  "${COMPOSE_RESTART_TARGETS[@]}" )` on an empty array is an unbound expansion
  under `set -u` on the target's bash, so both the save and the restore sit
  behind `(( saved_count > 0 ))`, with an unconditional `COMPOSE_RESTART_TARGETS=()`
  ahead of the restore so the probe's own findings cannot leak into a caller
  that had queued nothing.
- **Verified by mutation.** Seven, each caught by a case that names it:
  dropping each of the three `WG_*` restores individually, dropping the array
  clear that precedes the restore, returning `0` instead of the probe's status,
  putting the probe back in a postcondition position, and using the wrapper at
  the detection site so nothing publishes the globals first. The sixth of these
  is the one that matters most — it is the regression this whole item exists to
  prevent, and the derived case catches it by reading the reconcile script's
  own call sites rather than restating them.
- **One mutation initially survived and the test was wrong, not the code.**
  Dropping the `WG_SETUP_PENDING` restore changed nothing, because the case
  left the fixture identical between the two measurements — so the value the
  wrapper restored and the value its probe recomputed were the same number. The
  case now completes the wg-easy setup wizard *between* the measurement and the
  postcondition, which is the realistic shape and the only one where a missing
  restore is observable. Same lesson as `Q1-33`, from the other direction: a
  surviving mutation is either a missing test or a defect that is not one, and
  the way to tell is to make the two measurements disagree.

### DD-62: Portainer is proxied to loopback HTTPS on 9443 (revised 2026-08-06)

> **Superseded by DD-116 (2026-09-13):** Portainer was replaced by Dozzle,
> which is proxied over plain loopback HTTP. Kept as history.

- **Decision (revised):** Caddy's upstream for `portainer.${LOCAL_DOMAIN}` is
  `https://127.0.0.1:9443`. Compose publishes `127.0.0.1:9443:9443` only
  (image default HTTPS listener). `--http-enabled` / port 9000 are not used.
  Because Portainer's certificate is self-signed, the site block uses
  `transport http { tls_insecure_skip_verify }` on that **loopback** hop
  only. Operator access remains `http://portainer.${LOCAL_DOMAIN}` on the
  Tailscale-bound Caddy front door (`auto_https off`).
- **Supersedes (2026-08-05):** The earlier choice of plain HTTP `127.0.0.1:9000`
  avoided skip-verify by forcing `--http-enabled`. The operator preferred
  Portainer's native HTTPS listener on 9443; the skip-verify trade-off is
  accepted for same-host loopback and documented here.
- **Rationale for skip-verify on loopback:** TLS to a self-signed process on
  the same host does not add a meaningful trust boundary beyond plain HTTP
  on loopback; skip-verify is the practical way to speak Portainer's
  default listener without mounting its cert into Caddy. It must never be
  copied onto a non-loopback upstream.
- **The publication set is exactly one line:** `127.0.0.1:9443:9443`. Neither
  9443 nor 9000 is published on the tailnet or the WAN.

### DD-62-archive: Portainer plain loopback HTTP (2026-08-05, superseded)

- **Former decision:** Caddy upstream `127.0.0.1:9000` with Compose
  `--http-enabled` and no `tls_insecure_skip_verify`. Kept only as history;
  see the revised DD-62 above.

### DD-69: Downloads tree is recursively `1000:1000` for stack R/W (2026-08-07)

- **Decision:** Stage 3 always `chown -R ${DOWNLOADS_UID}:${DOWNLOADS_GID}`
  on `${DOWNLOADS_PATH}` (default `1000:1000`), with `0775` dirs and `0664`
  files. FileBrowser Compose service runs as the same uid:gid. qBittorrent
  (`PUID`/`PGID`) and Unpackerr (`user:`) already matched.
- **Context:** Creating only new dirs as `1000:1000` left existing trees
  unreadable/unwritable to the stack; the operator asked for a permanent
  shared R/W setup rather than a warning-only path.
- **Rationale:** One host identity shared by the three writers avoids ACL
  sprawl; WebDAV stays a separate read-only host user.
- **Trade-off:** Custom ownership/modes under downloads are still
  normalized toward the stack identity when they diverge. As of **DD-84**,
  matching entries are left untouched (no full-tree rewrite every re-run).

### DD-63: qBittorrent peer port is TCP+UDP (2026-08-06)

- **Superseded by DD-151 (2026-09-18):** no torrent peer port is opened any
  more; qBittorrent is a host module that only connects out.

- **Decision:** Compose publishes `${QBIT_PUBLIC_PORT}` for **both** TCP and
  UDP (1:1 host map, no WAN IP embed). `master-firewall` allows the matching
  NEW WAN rules in `MASTER-INPUT` and `MASTER-DOCKER`. wg-easy remains
  UDP-only.
- **Context:** v2 initially followed an early R12 “qBit UDP only” reading.
  Live review on the test host showed qBittorrent listening on TCP inside
  the container while only UDP was published, which matched weaker peer
  connectivity than legacy (`TCP+UDP` on `${PUBLIC_IPV4}`).
- **Rationale:** BitTorrent peer traffic is still predominantly TCP; UDP
  alone (µTP) is insufficient for expected swarm performance. Restoring TCP
  aligns v2 with legacy behaviour while keeping the v2 “no WAN IP in
  Compose” publish style.
- **Trade-off:** One additional public TCP port on the WAN versus the
  earlier narrower surface. Accepted explicitly by the operator (R12
  revised).
- **v2-27 (2026-08-07): IPv4-only peer publish.** Unqualified Compose
  `host:port` maps also bind `[::]`, while IPv6 `MASTER-DOCKER` drops all
  NEW WAN peer traffic — so `[::]:65171/65173` was dead surface. Peer
  maps are now explicit `0.0.0.0:port:port/...`. Host/Tailscale IPv6,
  NDP INPUT rules, and the wg-easy IPv6 bridge are unchanged.

### DD-71: IPv6 `MASTER-DOCKER` drops WAN only, like IPv4 (2026-08-07)

- **Superseded by DD-152 (2026-09-19):** there is no `MASTER-DOCKER` chain.

- **Decision:** `apply_docker6` ends with `-i $WAN_INTERFACE -j DROP`
  followed by `-j RETURN`, the same shape as `apply_docker4`, instead of an
  unconditional `-j DROP`. `--check` gains two IPv6 assertions
  (`MASTER-INPUT` and `MASTER-DOCKER` each carry the WAN-scoped `DROP`), and
  a bats test rejects a bare `-A "$staging" -j DROP` in that function.
- **Context:** The unconditional `DROP` sat in `DOCKER-USER`, which every
  IPv6 `FORWARD` packet traverses — so it dropped **egress** from the
  wg-easy bridge as well as WAN ingress. Compose enables IPv6 on that
  network, wg-easy issues peers an address out of
  `fdcc:ad94:bacf:61a4::/112`, and Docker installs a matching
  `POSTROUTING … MASQUERADE`; the project's own rule then cancelled all of
  it. Measured on the test host: `ping -6` from inside the container lost
  100% of packets while the host itself reached the same address in 3.8 ms,
  and the rule's counter incremented by exactly the test packets.
- **Rationale:** **DD-63**'s v2-27 note justified the rule from its inbound
  effect ("drops all NEW WAN peer traffic — so `[::]:65171/65173` was dead
  surface") and explicitly left the wg-easy IPv6 bridge alone. The outbound
  consequence was not part of that reasoning. A dual-stack peer therefore
  tried IPv6 first for every AAAA-resolved host and fell back to IPv4 after
  a timeout — a per-connection latency cost, not merely "no IPv6".
- **Trade-off:** Container IPv6 egress is now permitted, matching what IPv4
  has always allowed. No public IPv6 publish exists, so no `ACCEPT` precedes
  the WAN `DROP`; NEW WAN → container IPv6 stays closed. Verified live:
  egress 0% loss, `ip6tables -C MASTER-DOCKER -i eth0 -j DROP` still
  present, IPv4 chain unchanged.
- **Alternative rejected:** setting `enable_ipv6: false` on the wg network
  would also remove the fallback delay, but by removing peer IPv6 entirely
  rather than by fixing an asymmetry the contract (§9, "the same shape")
  already required.

### DD-83: Compose images are tag@digest pins, not floating tags (2026-08-09)

> **Partially superseded by DD-97 (v2-63).** Images with an upstream stable
> track now use that track without a digest. Digest pins remain for images
> that only offer `:latest` (qBittorrent). The ban on `latest` / Watchtower
> still stands; Portainer `lts` is an allowed named track under DD-97.

- **Decision:** Every Compose image in `defaults.env` is a concrete
  `name:tag@sha256:…` pin taken from the live `nrm` stack (2026-08-09).
  `latest` / `stable` / `lts` are forbidden. Installer still skips
  `compose up` when the rendered file is unchanged and still does not
  auto-pull on a timer.
- **Why:** Floating tags made “unchanged re-run” quietly freeze an old
  digest while a later recreate could jump unpredictably. Digest pins make
  re-runs and new installs reproduce the accepted set; updates are an
  explicit pin bump + acceptance, not an automatic updater.
- **Not doing:** Watchtower / reconcile-driven pulls.

### DD-82: WebDAV healthcheck and isolated `webdav` network (2026-08-09)

- **Superseded by DD-152 (2026-09-19):** the share WebDAV is a host service; systemd restarts it.

- **Decision:** Compose `webdav` gets a Docker healthcheck that treats an
  unauthenticated local `401` as healthy, and attaches only to a named
  bridge `webdav` (not `internal`). It does **not** join `wg` or the
  project default network. Caddy keeps proxying via host loopback publish.
  No memory or pids limits on this service.
- **Why:** Health makes Compose/`docker compose ps` report real readiness
  without embedding credentials. A dedicated network removes lateral
  reachability from Portainer/qBit/FileBrowser on `docker_default` without
  opening WireGuard-peer bypass of Caddy/Tailscale (which attaching to
  `wg` would allow for peers with `AllowedIPs 0.0.0.0/0`).
- **Not `internal: true`:** On Docker 29 / compose here, a container that
  only joins an `internal` network drops host port bindings
  (`NetworkSettings.Ports` empty → loopback `000`). Live nrm failed Stage 7
  that way; non-internal named bridge restores `127.0.0.1:WEBDAV_PORT`
  while keeping service isolation from `docker_default`.
- **Not doing:** publishing WebDAV on `wg`; memory ceilings (deferred /
  declined for this pass).

### DD-81: Stage 7 proves WebDAV read-only via inspect, not PUT 401 (2026-08-09)

- **Superseded by DD-152 (2026-09-19):** `master-modul` checks the service's command line and sandbox.

- **Decision:** `assert_webdav_readonly_runtime` checks the running
  `webdav` container: `Config.Cmd` contains `--read-only`,
  `HostConfig.ReadonlyRootfs` is true, and the `/downloads` mount has
  `RW=false`. Unauthenticated HTTP PUT is not used as a read-only proof.
- **Why:** A credential-less PUT returns `401` even if the serve were
  writable; that only proved auth. Secrets-free install-time proof belongs
  on Compose/runtime configuration, not on a confused HTTP status set.
- **Still separate:** loopback / Caddy / bare-IP unauthenticated `401`
  checks remain for the auth surface.

### DD-79: Host WebDAV leftovers are purged on every Stage 4 (2026-08-09)

> **Superseded by DD-96 (v2-62).** The purge was removed: v2 no longer
> migrates hosts provisioned by older revisions. Kept as the record of why
> it existed.

- **Decision:** After Compose WebDAV (**DD-77**), Stage 4 calls
  `purge_host_webdav_leftovers` to remove the host unit/script/`webdav.env`,
  the dedicated `master-webdav` user/group, `u:master-webdav` ACL entries
  under `DOWNLOADS_PATH`, and the Debian `rclone` package (`apt-get purge`).
- **Why:** v2-37 stopped *installing* those artifacts but left them on
  upgraded hosts; contract and GPT re-audit required a real cleanup. Scoped
  to the known v1/v2 identity (`master-webdav` + package name `rclone`) —
  no broad user wipe.
- **Safety:** Idempotent; Compose image rclone is untouched; `setfacl`
  installed only if the user still exists and the tool is missing.

### DD-78: Caddy WebDAV site aliases the Tailscale IPv4 (2026-08-09) — superseded by DD-98

- **Former decision:** The Caddyfile WebDAV site is
  `http://webdav.${LOCAL_DOMAIN}, http://{$TAILSCALE_IPV4}` → loopback
  rclone (port 80). Compose stays `127.0.0.1` only.
- **Why (then):** Apple TV / tvOS Infuse often cannot use MagicDNS.
- **Superseded (v2-66 / DD-98):** same Caddy ownership, but the Infuse
  address is `${TS_IPV4}:${WEBDAV_PORT}` rather than bare `:80`.

### DD-77: WebDAV runs in Compose on loopback, not as a host unit (2026-08-09)

- **Superseded by DD-152 (2026-09-19):** the share WebDAV runs on the host as `master-paylasim.service`.

- **Decision:** Replace host `master-webdav` (systemd + distro rclone +
  dedicated user) with a Compose service using `rclone/rclone`, published
  only on `127.0.0.1:WEBDAV_PORT`, reverse-proxied by Caddy. htpasswd
  stays at `/etc/master-stack/webdav.htpasswd` (0600). Refresh-tailnet
  restarts only Caddy.
- **Why:** Tailscale IP changes no longer require a WebDAV rebind; WebDAV
  updates with the rest of the stack; host ACL/user/rclone package surface
  shrinks. Double read-only (`:ro` mount + `--read-only`) is preserved.
- **Trade-off accepted:** Docker down ⇒ WebDAV down. Media producers are
  already Docker-backed, so the dependency matches the data path.
- **Follow-up:** Infuse without MagicDNS uses Caddy on
  `${TS_IPV4}:${WEBDAV_PORT}` (**DD-98**), not a Compose publish on the
  Tailscale address.

### DD-76: Compose does not own the WireGuard endpoint hint (2026-08-09)

- **Decision:** `WG_ENDPOINT_HOST` lives only in `state.env` (and the
  install summary). `$COMPOSE_DIR/.env` is not written; Stage 4 removes
  a leftover file. qBittorrent/unpackerr identity tokens are
  `__DOWNLOADS_UID__` / `__DOWNLOADS_GID__`. `DOWNLOADS_PATH` must match
  a narrow absolute charset with no `..` or `//`.
- **Why:** Compose never consumed `.env`; rewriting it on WAN IP change
  set `COMPOSE_NEEDS_UP` for no container benefit. Literal `1000` in the
  template duplicated `defaults.env`. Path charset closes obvious
  injection/traversal shapes without a full path sandbox.
- **Follow-up:** media-tree chown/chmod narrowing done in **DD-84**.
  Stage 7 WG listen / CGNAT warnings remain deferred (operator-tracked).

### DD-88: Stage 7 asserts Caddy UI sites are non-5xx (2026-08-09)

- **Decision:** After the health probe, Stage 7 requests
  `portainer` / `wg` / `qbit` / `file` via `Host:` on `${TAILSCALE_IPV4}`
  and requires an HTTP status in `1xx–4xx` (not empty/5xx). WebDAV stays
  on its separate `401` checks; `health` stays the `ok` body check.
- **Why:** Contract §14.13 already required this; Stage 7 previously
  stopped at DNS + health + WebDAV auth surface, so a dead upstream behind
  Caddy could still pass install. Cheap and secrets-free.
- **Not doing:** asserting exact `200` (wg returns `302`; first-run UIs
  vary) or authenticated probes.

### DD-92: Classic FileBrowser replaces Quantum (2026-08-09)

- **Decision:** Compose `filebrowser` uses `filebrowser/filebrowser`
  (digest-pinned `v2.63.23`), not FileBrowser Quantum. WebDAV stays
  separate rclone (**DD-77**). UI remains `file.*` → loopback `61007`.
- **Why:** Operator preference after side-by-side trials (classic UI).
  Known shell CVEs are mitigated with `--disableExec` (and no auth
  hooks). Tailnet-only + Caddy exposure is accepted; the residual risk is
  **maintenance-only / planned archive** (no future patches) — recorded
  consciously, not ignored.
- **Data:** Host dir `/etc/master-stack/filebrowser-data` (DOWNLOADS_UID)
  holds the Bolt DB (`/database`) and binds `config/` over the image
  `VOLUME /config` so Compose does not allocate an anonymous volume
  (v2-58). `/downloads` mounts at `/srv`. Quantum `filebrowser.yaml` and
  named volume `filebrowser_data` are removed on Stage 4.
- **Accounts:** Default `admin`/`admin` on first DB bootstrap — end-of-
  install warning; operator must change. *(Superseded by **DD-118**: the
  installer creates the only account from a stage-0 prompt.)*

### DD-97: Prefer upstream stable tracks over patch@digest pins (2026-08-09)

- **Superseded by DD-152 (2026-09-19):** no images remain; rclone is pinned by version and SHA256.

- **Decision:** Where the vendor publishes a stable track tag, Compose uses
  that tag with **no** `@sha256`. Where it does not, the digest pin stays.

  | Image | Tag | Why this track |
  |---|---|---|
  | Portainer CE | `lts` | Official install docs; Long-Term Support line (`sts` rejected) |
  | FileBrowser | `v2` | Major track; equals current `v2.63.23` tip |
  | qBittorrent (linuxserver) | `latest` | Documented as “Stable qbittorrent + libtorrent v2”; `libtorrentv1` is the other stable line and is rejected |
  | wg-easy | `15` | Official getting-started tag; major line |
  | Unpackerr | `0.15` | Minor track; equals `0.15.2` |
  | rclone | `1.75` | Current stable minor (tips at `1.75.0`; was frozen on `1.74.4`) |

- **Why:** Patch@digest pins made every upstream patch an installer bump.
  The operator wants the current *stable line*. For LinuxServer qBittorrent
  the stable+libtorrent-v2 line is literally named `latest` (there is no
  `libtorrentv2` tag); that is an allowed exception, not a licence to use
  `latest` elsewhere. `libtorrentv1`, `sts`, `edge`, `nightly`, beta stay
  forbidden.
- **Trade-off (accepted):** a pull/recreate can change the running digest
  without a git change. Re-runs that leave `compose.yaml` byte-identical
  still skip `compose up` (**R20**). First install or an explicit recreate
  moves the tip. qBittorrent tip as of this decision:
  `5.2.3_v2.0.13-ls470` (was pinned at `ls469`).
- **Supersedes DD-83** for track-tagged images. Watchtower still out.
- **Not doing:** `libtorrentv1`, Portainer `sts`, or `latest` on any image
  other than linuxserver/qbittorrent.
- **Follow-up:** the "first install or an explicit recreate moves the tip"
  gap is now also reachable on a re-run via an opt-in prompt (**DD-99**),
  without turning the installer into a reconcile engine.

### DD-99: Image pull is a re-run prompt, not a background reconciler (2026-08-23)

- **Decision:** `stage_0` asks, only when `state.env` already exists
  (i.e. a re-run, never on first install), "Konteyner imajları güncel
  sürüme çekilsin mi?" default **hayır**. Answering evet sets
  `PULL_IMAGES=1`; `stage_4` then runs `docker compose pull` right after
  rendering `compose.yaml` and forces `COMPOSE_NEEDS_UP=1` so `stage_7`
  recreates any container whose digest moved. `V2_PULL_IMAGES=1`
  answers the same question non-interactively (same shape as
  `V2_FULL_UPGRADE`).
- **Why:** DD-97 deliberately pins track tags (`lts`, `v2`, `latest`, …)
  and accepts that a byte-identical re-run skips `compose up` (**R20**),
  so a floating tag can drift stale for months with no supported way to
  catch up short of a fresh install. An explicit, operator-driven pull
  closes that gap without adding drift-detection or a timer — the
  operator decides *when*, the installer still does nothing on its own.
- **Why default hayır, not evet:** an unattended `Enter` on a routine
  re-run (e.g. fixing a port) must not silently swap running image
  digests — that is a bigger blast radius than what the operator asked
  for. Matches `upgrade_ans`'s existing default (**R20** intro block).
- **Why skipped on first install:** `docker compose up -d` already pulls
  every missing image; a redundant `pull` right before it is a no-op that
  only adds network time.
- **Cleanup (v2-69):** once `stage_7`'s `docker compose up -d` has
  recreated containers on the new digest, the same `PULL_IMAGES=1` gate
  also runs `docker image prune -f`, so the old (now dangling, untagged)
  layers a pulled floating tag leaves behind don't sit on disk
  indefinitely. A prune failure is logged (`log WARN`) and does not fail
  the run — reclaiming disk is a courtesy, not a correctness requirement.
- **Trade-off accepted (prune scope):** `docker image prune -f` is
  host-wide, not scoped to this stack's images — any dangling image on
  the box is reclaimed, not just ones this pull produced. Acceptable
  under the installer's single-host, root-only contract; an
  image-ID-scoped `docker rmi` of just the pre-pull digests would need
  capturing them before the pull, which the plain `pull` output doesn't
  hand back cheaply.
- **Not doing:** a scheduled/automatic pull (Watchtower-shaped — rejected
  by DD-97), and no attempt to pin/report the pre-pull digest for audit;
  `docker compose pull`'s own output is the record.

### DD-101: The opted-in pull has a fail-closed disk floor (2026-08-28)

- **Decision:** when the operator accepts the image-pull prompt (DD-99),
  `stage_4` measures free space on the filesystem holding
  `/var/lib/docker` (`df -Pk`) before running `docker compose pull` and
  `die`s if it is below `PULL_MIN_FREE_GB` (declared once, in
  `defaults.env`; default 5 GiB). An unreadable measurement also dies —
  guessing about disk space before a multi-GB download is not an option.
- **Why:** a pull that fills the disk mid-download does not just fail the
  pull — a full `/var/lib/docker` can wedge the running containers and
  the Docker daemon itself, which is exactly the "failure leaves the host
  worse than before" outcome §12 of the contract forbids. Checking before
  the first byte keeps the failure mode at "nothing happened, message
  says why".
- **Why die, not warn-and-continue:** the operator opted into the pull at
  a prompt seconds earlier; a warning scrolling past in pull output is
  not a decision. Declining is cheap: free space or re-run without the
  pull. Matches the fail-closed posture everywhere else in the tree.
- **Why a fixed floor, not a computed image-size estimate:** the real
  space needed depends on layer overlap the registry only reveals during
  the pull; estimating it would be reconcile-engine-shaped complexity for
  a number that a single conservative constant covers on this fixed
  six-image stack.
- **Not doing:** any disk check on the non-pull path — the ordinary
  re-run downloads nothing and stays gate-free (R20: no step is
  unconditionally expensive).

### DD-107: Container logs are rotated (2026-09-08)

- **Superseded by DD-152 (2026-09-19):** no containers remain; every module logs to the journal.

- **Decision:** `merge_docker_daemon_dns` becomes
  `merge_docker_daemon_config` and additionally merges
  `log-opts.max-size`/`max-file` (`defaults.env`) — but **only** when
  `log-driver` is `json-file` or unset, and by adding to any existing
  `log-opts` rather than replacing it.
- **Why:** the json-file driver's default is unbounded, six services run
  `restart: unless-stopped`, and one of them is a torrent client. Measured on
  `nrm`: `/var/lib/docker/containers` at 360 K with no rotation configured —
  small today, unbounded by design.
- **Why conditional:** **DD-8** says write the keys we own and preserve the
  rest. An operator who selected another logging driver has chosen its
  options too; overwriting them would be the installer claiming a setting it
  does not own.
- **Known limitation, deliberately not worked around:** `log-opts` applies to
  containers **created after** the change, and this function does not restart
  Docker (a restart would stop the running containers). On a provisioned host
  the setting therefore takes effect at the next compose recreation, not at
  the end of this run. Forcing it would cost a service interruption to fix a
  problem that has not yet occurred.
- **Superseded in part by DD-110 (2026-09-11):** the limitation above was
  real, but it also applied to fresh installs, not only existing hosts. The
  file was written after the package had already started dockerd, so no
  container ever received these options. DD-110 corrects the order and moves
  the log policy into `compose.yaml`.

### DD-110: Daemon config before the daemon; log policy in the service definition (2026-09-11)

- **Superseded by DD-152 (2026-09-19):** Docker and its `daemon.json` are gone.

- **Decision:** two changes.
  1. `stage_4` writes `/etc/docker/daemon.json` **before** installing the
     Docker packages, instead of after.
  2. Log rotation moves into `templates/compose.yaml` as an `x-logging`
     anchor that every service references. The values still come from
     `DOCKER_LOG_MAX_SIZE`/`DOCKER_LOG_MAX_FILE` in `defaults.env`.
     `daemon.json` keeps its `log-opts` copy, but only as the host default for
     containers outside this stack.
  When `daemon.json` changes while dockerd is already running, the installer
  says the new daemon-level settings wait for the next Docker restart instead
  of assuming they took effect.
- **Why 1 — measured on a fresh Ubuntu 26.04 install (`nrm`, 2026-09-10):**
  docker-ce's postinst starts dockerd straight away
  (`deb-systemd-invoke … docker.service`). The journal shows it finished
  initialising at **23:09:43**. `daemon.json` was written at **23:09:45**.
  `systemctl enable --now docker` does nothing to a unit that is already
  running, so dockerd kept its original configuration. The six containers
  created at **23:10:11** all carry `LogConfig {}`, and that is permanent
  because log configuration is fixed when a container is created. After a
  reboot, a probe container created with `docker create` did get
  `{"max-file":"3","max-size":"10m"}`, so the file was correct all along;
  only the order was wrong. The same ordering meant **DD-8's `dns` setting did
  not apply between a fresh install and its first Docker restart**. DNS is
  applied when a container starts, so the reboot fixed it, but until then the
  failure mode DD-8 exists to prevent (containers inheriting
  `100.100.100.100`) was open.
- **Why moving the write earlier is safe:** none of the five Docker packages
  owns `daemon.json`. `dpkg -S` finds no owner, it appears in no package's
  file list, and it is not a conffile. docker-ce only creates the
  `/etc/docker` directory, so the package install cannot overwrite a file that
  is already there, and dockerd reads it on its first start. This is the same
  pattern as **DD-18**, where Tailscale's netbuf floor is written before the
  tailscale package starts its daemon.
- **Why 2 — the order fix alone cannot reach existing hosts.** Log
  configuration is fixed when a container is created. Every container made
  before this fix keeps `{}` until it is recreated, and restarting dockerd
  would not change that. In `compose.yaml` the setting shows up as a change to
  the service definition, so the existing `COMPOSE_NEEDS_UP` path recreates the
  affected services on the next run with no daemon restart. The cost is one
  recreation of the six containers on the upgrading run. Named volumes keep
  their data and the interruption lasts seconds, the same as any other change
  to the service definition.
- **Correction of DD-107 and of the v2-76 acceptance record:** DD-107 said
  `log-opts` "applies to containers created after the change". That is
  technically true, but on a fresh install the containers were created before
  dockerd had read the file, so rotation never applied anywhere. The v2-76
  Ubuntu acceptance reported that `daemon.json` "carries the rotation keys".
  The file did, but the containers did not. The check confirmed what was
  written, not what took effect: the mistake **DD-109** warns against.
- **Not doing:** having the installer restart dockerd. On an existing host that
  would stop and start every running container without changing their fixed
  log configuration, so it would cause an outage and fix nothing.
- **Live-verified on Ubuntu 26.04.1 (`nrm`, 2026-09-11), on both paths:**
  - *Existing host (v2-77 → v2-78):* the rendered `compose.yaml` changed, so
    the run recreated all six containers once. All six ids changed, all six now
    carry `{"max-file":"3","max-size":"10m"}`, 3/3 healthchecks are healthy and
    stage 7 passed. `daemon.json` was untouched, and the new "changed under a
    running dockerd" message correctly stayed silent. A second run recreated
    nothing (0/6), so the anchor does not cause churn on every run.
  - *Fresh Docker install (the ordering itself):* after Docker was purged
    completely and the installer re-run, `daemon.json` was written at 08:50:44
    and dockerd completed its first and only initialisation at 08:50:51. With no
    restart or reboot, container DNS showed `ExtServers: [1.1.1.1 1.0.0.1]`, so
    the DD-8 gap is closed. A `docker create` probe outside compose received the
    daemon `log-opts`, and all six compose containers carry the log options.
- **A test-method pitfall found along the way, not an installer defect:**
  purging Docker without a reboot leaves the old dockerd's kernel bridges in
  place. The networks with dynamic subnets avoided them, because Docker's IPAM
  saw the existing routes and chose new ranges. The fixed-subnet `wg` network,
  however, was created a second time on `WG_BRIDGE_SUBNET`, and the kernel kept
  routing its addresses through the dead old bridge. Stage 7 correctly failed
  on `wg.ayc` (502, `connection reset by peer`), but its message points at Caddy
  rather than at the duplicate route. Deleting the three stale bridges (all
  down, none known to Docker) restored the route, `wg.ayc` returned 302, and
  the re-run exited 0. Recorded in `tests/README.md`.
- **Clean record (2026-09-11):** Docker was purged and the host rebooted, so
  no stale bridge survived (0 kernel bridges before the install). v2-78 then
  installed from a clean Docker state and exited 0 (`INSTALL_EXIT=0`).
  `daemon.json` was written at 09:01:21 and dockerd initialised once, at
  09:01:27. With no restart, container DNS showed
  `ExtServers: [1.1.1.1 1.0.0.1]` and the daemon `log-opts` were in effect. All
  six containers carry the log options and all four UIs returned non-5xx
  responses (`wg` 302). Exactly one interface held the `wg` gateway address,
  there were 0 failed units, 3/3 healthchecks were healthy, and firewall
  `--check` passed.
- **Debian 13.6, fresh install (`nrm`, 2026-09-11):** the same ordering held
  on the other distribution. `daemon.json` was written at 10:23:06 and dockerd
  initialised once, at 10:23:14. With no restart, both probed containers
  showed `ExtServers: [1.1.1.1 1.0.0.1]`, a `docker create` probe received the
  daemon `log-opts`, and all six compose containers carry the log options.

### DD-112: Backups are password-encrypted with the OS's `openssl`; restore uploads once (2026-09-11)

- **Superseded by DD-122 (2026-09-14):** container-backup is retired.

- **Decision:** `container-backup.command` encrypts every new backup on the
  workstation with `openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -md sha256
  -salt`, asking for the password twice at backup and once at check and
  restore. Decryption is local, so the password never reaches the server.
  The restore flow uploads the archive once and runs check and restore in
  one remote directory; it no longer downloads a before-restore backup.
- **Why encrypt now:** the archives hold bcrypt hashes for four services and
  wg-easy's server and peer private keys. They live in a `0700` directory on
  one laptop, but a laptop backup, a sync folder or a copied disk carries
  them unchanged. The user asked for a password on backup and on restore;
  that is what was built.
- **Why `openssl enc`, not `age` or gpg:** the constraint was "works on
  this Mac without installing anything", and at decision time also on
  Windows — a requirement the user withdrew the next day (below). macOS
  ships LibreSSL and every OpenSSL reads and writes this one format.
  Measured: LibreSSL 3.3.6 and OpenSSL 3.6.3 derive the identical key and
  IV from the same salt and password and decrypt each other's files
  byte-for-byte; the host's OpenSSL 3.5.7 does too, which is what lets a
  backup be opened without this script. `age` and gpg are not on the Mac,
  and installing them is outside this repository. Encrypting on the server
  would have sent the password to the one place it must not go.
- **Why no MAC:** `openssl enc` has no authentication tag, and
  encrypt-then-MAC in bash means a second PBKDF2 run plus a hand-rolled HMAC
  (it works under bash 3.2 — checked against RFC 4231 and Python's `hmac` —
  but it is more code than the whole encryption step). The threat encryption
  addresses here is a *copied* file, not an attacker who can rewrite files
  on the workstation; that attacker can rewrite the script. In place of a
  tag, the decrypted archive's SHA-256 is checked against `settings.sha256`,
  which the server computed over the plaintext, and the server checks every
  file against the manifest. Without the password nobody can produce a
  ciphertext whose decryption passes either. The hash check also catches the
  one-in-256 wrong password that passes CBC padding. `settings.sha256` and
  `files.txt` stay plaintext for this reason; they reveal names and a hash,
  not contents.
- **Why the password travels on stdin and fd 3:** `read -s` from standard
  input like every other prompt in the script, then `-pass fd:3` from a
  process substitution. It never appears in `argv` (visible in `ps`) or the
  environment, and the variable is cleared on exit. Standard input rather
  than `/dev/tty` keeps automation possible; a piped password in shell
  history is the caller's choice and is documented.
- **Why one upload:** the old restore ran check, then a fresh remote
  directory for the before-restore backup, then a third for the restore,
  uploading the archive twice. The worker now removes its own intermediate
  outputs at the start of each action, so the steps share one directory and
  the archive goes up once. Same worker, same checks, one round.
- **No before-restore download (2026-09-12):** restore used to take a backup
  of the target and download it to the workstation before replacing
  anything, which stopped the four containers a second time and left a
  `before-restore` directory beside every real backup. The user asked for a
  single copy on backup and a direct load on restore. In this workflow the
  restore target is always a fresh install, so the copy protected nothing.
  What stays is the server-side recovery snapshot taken while the containers
  are already stopped: it costs no extra stop or transfer and is what the
  automatic rollback on a write/start/health failure uses. The trade-off is
  stated at the prompt and in the docs: a *successful* restore cannot be
  undone; back the target up first if its settings matter.
- **macOS only (2026-09-12):** the first version also tried to run from Git
  Bash/WSL (`sha256sum` fallback, `openssl` from `PATH` with a `-pbkdf2`
  preflight, SSH multiplexing probed and dropped where absent, LF forced by
  `.gitattributes`). It was never exercised on Windows, and the user dropped
  the requirement the next day. The launcher went back to the macOS tools
  it is verified with — `shasum`, the system `/usr/bin/openssl`, one
  multiplexed SSH connection — and `.gitattributes` was removed. The file
  format is still standard OpenSSL, so a backup can be decrypted anywhere;
  only the script is Mac-only.
- **Built and removed the same day — `seed`:** the first version of this
  change also saved `/etc/master-stack/config.env` and `webdav.htpasswd` in
  every archive (manifest schema 2) and added a `seed` action that placed
  them on a fresh host before `install.sh`, so the reinstall would reuse the
  previous answers and WebDAV account. It was verified end to end (isolated
  round-trip, minimal Debian/Ubuntu containers without jq or Docker, and a
  seed → `install.sh` re-run on `nrm` that took the seeded values as prompt
  defaults). The user then judged that five installer answers and one
  WebDAV account, which `install.sh` asks for anyway, did not justify a
  third step, a second archive schema and the content validation that came
  with sourcing a restored file as root. The tool went back to copying and
  loading container settings only; the archive layout and schema are the
  ones from 2026-09-05. The verified design is in the history (`d92b338`)
  if it is ever wanted.
- **Not doing:** encrypting `settings.sha256` or `files.txt`; a key file or
  keychain integration; re-encrypting the two existing plaintext backups
  (they stay usable and are reported as unencrypted); a `.bat` wrapper that
  cannot be tested here.
- **Verified (2026-09-11):** `/bin/bash -n` under macOS bash 3.2 and
  `shellcheck` clean on all three scripts; bats green. The isolated
  round-trip passed on the Debian 13.6 `nrm`. From the Mac under Finder's
  `/bin/bash`: an encrypted backup in 17 s that the LibreSSL one-liner
  decrypted to the server's hash; a wrong password stopped before any SSH;
  short and mismatched passwords rejected; `check` passed on the encrypted
  archive and on the 2026-09-06 plaintext archive (unencrypted warning);
  `restore` of the encrypted archive onto `nrm` in 30 s with one upload, its
  before-restore backup encrypted (`kind: rollback`), 6/6 containers, 3/3
  healthy, 3 WireGuard peers, no remote directory left. Not yet run: the
  full runbook from a bare OS; it is the next acceptance item when `nrm` is
  reimaged.

### DD-114: Container backups carry one operator-state file per service (2026-09-13)

- **Superseded by DD-122 (2026-09-14):** container-backup is retired.

- **Decision:** `container-backup` saves and restores exactly four files:
  Portainer's `portainer.db`, FileBrowser's `filebrowser.db`, qBittorrent's
  `qBittorrent.conf` and wg-easy's `wg-easy.db`. Restore replaces each one
  atomically with its recorded owner and mode, removes SQLite side files
  beside it, and touches nothing else on the destination. Whole-directory
  archives from before this date still restore; only these four files are
  taken from them.
- **Why:** the user listed everything they do after an install: create the
  Portainer admin from the setup token, change the FileBrowser password,
  change the qBittorrent user name, password and a few preferences, create
  the wg-easy account and the peers. Each of those lives in one file. The
  user's concern was that writing more back — keys, certificates, derived
  configuration — could interfere with what a newer image produces for
  itself. Carrying only the state the operator created removes that
  question.
- **Why the other files are safe to leave behind (measured on `nrm`):**
  - wg-easy wrote `wg0.conf` one second after its container started, so the
    file is rendered from `wg-easy.db` on every start.
  - FileBrowser's `config/settings.json` carries a July image-build date,
    and a fresh FileBrowser created it on first start. The Compose command
    line overrides its address, port, root and database.
  - Portainer's keys, certificates and Edge tunnel key are dated from the
    install. A throwaway Portainer, started once so it generated its own
    keys, was then given only a backed-up `portainer.db`. It served
    `/api/status`, reported the admin as present and rejected a wrong
    password with 422 (the user table was read), and its own keys stayed in
    place. It logged no errors.
  - A throwaway FileBrowser run with the Compose restrictions behaved the
    same with only `filebrowser.db`: healthy, and 403 for a wrong login.
  - Both throwaway containers had no published port and no Docker socket,
    and were removed.
- **SQLite side files:** replacing a single SQLite database while an old
  `-wal` is left beside it would let SQLite replay the destination's
  transactions onto the restored file. Restore removes `-wal`, `-shm` and
  `-journal` next to each restored file. A backup refuses a database whose
  WAL or journal is not empty after the clean stop, and validation refuses an
  archive that carries one. BoltDB and the `.conf` file have none. This
  replaces the protection the old whole-directory copy gave implicitly.
- **Trade-offs:** the following are not carried:
  - Portainer stacks deployed from Portainer, whose compose files live under
    `/data/compose/`.
  - Edits to FileBrowser's `settings.json`.
  - qBittorrent's categories, RSS, watched folders and torrent list.
  - Stale files on the destination, which are no longer cleaned; there is
    nothing to clean on a fresh install.

  The restore semantics also changed: a scope file absent from the archive is
  removed, which is how the server-side recovery snapshot brings back a file
  that did not exist before.
- **Considered and not committed:** widening qBittorrent to its whole
  settings tree minus GeoDB, logs, the RSS article cache and runtime files.
  It was built and verified on 2026-09-13, then reverted before commit when
  the user described what they actually change.
- **Verified (2026-09-13):**
  - The isolated round-trip on `nrm` passed, 18 checks including an archive
    with exactly four files, untouched out-of-scope files, side-file
    clearing, a qBittorrent that never started, whole-directory archives,
    rollback, and non-empty-WAL rejection.
  - Live from the Mac: the backup held exactly the four files (40 KB), and a
    self-restore took 16 s.
  - After the restore, `qBittorrent.conf` and `wg-easy.db` were
    byte-identical to the archive. The two BoltDB files had been updated by
    their applications on open. Owners and modes matched on all four.
  - All 12 out-of-scope files were unchanged in content; 6/6 containers ran,
    3/3 healthy, every peer was present and the web UIs answered.
  - The user's real 2026-09-12 backup lists only entries the validator
    accepts, and `check` on a same-format archive reported "4 to load".

### DD-115: An optional Tailscale auth key replaces the browser step (2026-09-13)

- **Decision:** stage 0 asks `Tailscale auth key (boş bırakın = tarayıcıdan
  giriş)` with hidden input, after the WebDAV prompts, and only when the node
  is not already online.
  - With a key, stage 2 writes it to `$RUNTIME_DIR/tailscale-authkey`
    (tmpfs, root-only directory, file mode `0600`). It runs `tailscale up
    --auth-key=file:<that path> --advertise-exit-node --ssh` under
    `TS_AUTHKEY_LOGIN_SECONDS` (300 s), then removes the file.
  - An `EXIT` trap removes the file if the run is interrupted.
  - If `tailscale up` fails and the node is not online, the installer logs
    a warning and runs the existing interactive login.
  - The variable is unset after stage 2.
- **Why:** the user asked for it. The login URL is the one step of an
  install that needs a browser, and a key lets the install continue by
  itself once the prompts are answered. It is not an unattended mode: every
  other prompt stays, and an empty answer keeps today's behaviour exactly.
- **Why a file, not the argument:** `--auth-key=tskey-…` would be readable by
  any local user in `ps` and `/proc/<pid>/cmdline` for as long as `tailscale
  up` runs. Tailscale 1.102.4 documents `file:` for exactly this ("a path to
  a file containing the authkey"). The key also stays out of `config.env`,
  `state.env`, the install log, the environment of child processes and,
  therefore, container backups. The prompt reuses the `read -s` pattern of
  the WebDAV password, and a bats test rejects any `--auth-key=$TS_AUTH_KEY`,
  `export TS_AUTH_KEY` or a log line carrying it.
- **Why fall back instead of stopping:** a key is a convenience with a
  shelf life. A one-off key already used, an expired key or a typo must not
  strand a fresh install half-way through stage 2. The browser path, with
  its three-attempt 410 recovery (**DD-37**, **DD-42**), is unchanged and
  follows directly.
  - A successful `tailscale up` returns straight to stage 2's online wait,
    which also covers a tailnet with device approval.
  - The exit status is read from `PIPESTATUS`, not from the `tee` it is piped
    through. The first version returned success for a rejected key whenever
    `pipefail` was off; a test caught it.
- **Why validate the shape:** keys start with `tskey-` and contain only
  letters, digits and `-`. OAuth client secrets (`tskey-client-…`) also log
  in only with `--advertise-tags`; stage 0 names that mistake instead of
  letting it fail in stage 2.
- **Which key to create (operator guidance, not enforced):**
  - Reusable or one-off.
  - **Not ephemeral:** an ephemeral node is removed once it has been offline
    for a while, so an exit node that reboots would disappear from the
    tailnet.
  - Pre-approved if the tailnet requires device approval.
  - Exit-node approval and the DNS settings stay manual unless the tailnet
    policy auto-approves them; the install summary still lists them.
- **Verified (2026-09-13):**
  - bats: three tests check that the key reaches `tailscale up` only through
    a `0600` file that is gone afterwards, never appears in argv or the log,
    that a rejected key falls back, and the prompt and persistence rules.
  - Live on `nrm`, inside a throwaway container running the host's
    `tailscaled` 1.102.4 with its own state: the installer's real function
    passed a fake key by `file:`. Tailscale read it and rejected it in 5 s
    (`backend error: invalid key: API key does not exist`); the function
    fell back with the warning, no key file remained and the key was in
    neither log.
  - The prompt trimmed pasted whitespace over a real TTY.
  - A v2-81 re-run on the online production host skipped the prompt, exited
    0 with no warnings and recreated no container.
  - Not yet verified: a successful login with a real key; that needs a key
    from the user's tailnet on the next fresh install.
  - The first attempt at the isolated test had a test-procedure flaw,
    recorded in `tests/README.md`.

- **Amended by DD-119 (2026-09-14):** the key comes from `TS_AUTH_KEY` in
  the installer input file instead of a hidden prompt, and is dropped when
  the node is already online. The `file:` login, the fallback and the
  persistence rules are unchanged.

### DD-116: Dozzle replaces Portainer (2026-09-13)

- **Superseded by DD-151 (2026-09-18):** Dozzle was removed; each Konsol
  module card has its own log.

- **Decision:** the Compose `portainer` service becomes `dozzle`
  (`amir20/dozzle:v11`, loopback `127.0.0.1:61002` → 8080, site
  `dozzle.${LOCAL_DOMAIN}`).
  - It runs with `DOZZLE_AUTH_PROVIDER=simple`,
    `DOZZLE_ENABLE_ACTIONS=true` and `DOZZLE_NO_ANALYTICS=true`. Shell is
    left disabled.
  - Hardening: read-only root, a `/tmp` tmpfs, `cap_drop: ALL`,
    `no-new-privileges`, and a Compose healthcheck (`/dozzle healthcheck`,
    which the image does not wire in by itself).
  - Stage 0 asks for a Dozzle user name and password when
    `/etc/master-stack/dozzle/users.yml` does not exist. Stage 4 writes it
    with the image's own `generate --user-roles actions`, password on stdin,
    in a container without network; `/etc/master-stack/dozzle` is bound to
    `/data`.
  - Stage 7 requires `401` from `/api/events/stream` through Caddy, so a
    Dozzle without its login fails the install.
- **Why:** the user uses Portainer for three things only — container state,
  logs, and removing a container when needed — and said most of its features
  do not fit. Dozzle is built for exactly those three: live logs with search,
  container state and resource use, and start/stop/restart/remove.
  - Two burdens go away: the post-install setup-token step (create the
    Portainer admin within its timeout) and `portainer.db` in the backup.
  - Portainer also offered a way to edit and recreate the installer's
    containers outside `compose.yaml`; Dozzle does not, apart from `update`
    (below).
  - Resource use was not the reason: Portainer used about 96 MB of a 7.8 GB
    host.
- **Why the login comes from the installer:** Dozzle with actions can stop
  and remove every container, and `docker.sock` is root-equivalent whether or
  not it is mounted `:ro` (Dozzle's own documentation says the flag does not
  limit the API). Tailnet-only reachability was offered and not chosen.
  - The account follows the WebDAV pattern: asked once, kept on re-runs,
    replaced by deleting the file and re-running.
  - `generate` owns the file format and bcrypt hashing, so nothing is
    reimplemented. Stdin keeps the password out of `argv`.
  - The `actions` role instead of the empty default (all roles) leaves
    shell and cloud linking out even if they are enabled later.
- **Why `v11`:** DD-97 prefers the vendor's major track. v11.0.0 was
  published on 2026-09-11 with no breaking changes listed; `v10` stopped at
  10.10.0.
- **Measured before adopting (2026-09-13, throwaway container on `nrm`):**
  - The hardened settings ran without restarts, and `/healthcheck`
    answered 200.
  - Without a login: `/` → 307 to `/login` and `/api/events/stream` → 401.
    A wrong password → 401. The right one → 200, and the event stream then
    delivered.
  - The page configuration reported `authProvider: simple`,
    `enableActions: true`, `enableShell: false`.
  - Dozzle writes `session_secret` next to `users.yml` in `/data`, so the
    directory stays writable.
- **Trade-offs:**
  - Dozzle's single actions switch also enables `update`, which pulls and
    recreates a container outside the installer. A re-run restores the
    Compose definition; updating images remains the installer's job
    (DD-97).
  - Portainer's stack/volume/image management is gone.
  - Old backups still restore, with Portainer ignored (**DD-114**).
- **Existing hosts:** per DD-96 the installer does not delete the
  `portainer` container or its `docker_portainer_data` volume. `docker
  compose up` reports it as an orphan, and stage 7 logs a warning with the
  removal commands while it runs. On `nrm` the container was removed by hand
  after verification; the volume was left for the operator.
- **Verified on `nrm` (Debian 13.6, 2026-09-13):**
  - Static: bats 104 ok; `bash -n` and `shellcheck` clean.
  - Install: a v2-81 → v2-82 re-run answered the new prompts, wrote
    `users.yml` (`0600 root:root`, role `actions`) and created a healthy
    `dozzle` with the hardening in effect. The other five containers were not
    recreated.
  - DNS and login: `dozzle.ayc` resolved to the Tailscale IP and
    `portainer.ayc` became NXDOMAIN. Through Caddy the login was enforced
    and a login worked. Stage 7 warned about the running Portainer.
  - After removing the Portainer container, a second run skipped the prompt,
    warned nothing and changed nothing.
  - Backup: the round-trip passed 18/18. A live backup held three files, and
    `check` on a four-file Portainer-era archive reported "4 files, 3 to
    load".

### DD-117: Transmission replaces qBittorrent (2026-09-13)

- **Superseded by DD-127 (2026-09-14):** the user found Transmission slow and
  went back to qBittorrent, with no installer-written settings or account.

- **Decision:** the `qbittorrent` service becomes `transmission`
  (`lscr.io/linuxserver/transmission:latest`, Transmission 4.1.3).
  - Web UI at `torrent.${LOCAL_DOMAIN}` (loopback 61006 → 9091).
  - The peer port stays 61005 TCP+UDP (`PEERPORT`).
  - `QBIT_PUBLIC_PORT`/`QBIT_UI_PORT` become
    `TORRENT_PUBLIC_PORT`/`TORRENT_UI_PORT` in `defaults.env`, `state.env`
    and the firewall script alike.
  - `/config` is a bind mount on `/etc/master-stack/transmission`.
  - Credentials: stage 0 asks for a user name and password, stored in
    `/etc/master-stack/transmission-auth/{user,pass}` (`0600 root`, directory
    `0700`), mounted read-only and read through `FILE__USER`/`FILE__PASS`.
  - The installer seeds `settings.json` on a fresh install (download layout,
    port forwarding off, `rpc-port` 9091) and never touches it again.
  - Stage 7 requires `401` from `/transmission/rpc` without a login.
  - A leftover `qbittorrent` container stops stage 0 before any change.
- **Why:** the user uses the torrent client only to download and wanted
  something simpler than qBittorrent. Resource use was not the argument:
  qBittorrent idled at 15.7 MB on `nrm`. The gain is a plain interface and one
  post-install step fewer — reading qBittorrent's temporary password from the
  logs and changing it — because the installer now sets the account.
- **Why the credentials are a plaintext root-only file — measured, not
  assumed (throwaway containers on `nrm`):**
  - Without `USER`/`PASS` the image's init script sets
    `rpc-authentication-required = false` on every start, so authentication
    survives only if the credentials are supplied every time.
  - Its clean-shutdown script calls `transmission-remote --exit` with them.
  - A pre-hashed Transmission password (`{sha1…salt}`) did log in through the
    web UI, but broke that shutdown RPC. `docker stop` waited out its timeout
    and killed the container (exit 137), and a changed setting was lost.
  - `FILE__` keeps the value out of `compose.yaml` and `docker inspect`
    (verified).
  - The host file is `0600 root`, which docker access already trumps.
    Transmission itself keeps only a hash in `settings.json`, even while
    running.
  - The file must hold the plaintext; that is the trade-off, recorded here
    rather than hidden.
- **Why the settings seed includes `rpc-port`:** the image's shutdown and
  readiness scripts read the port with `jq '.["rpc-port"]'`.
  - A first seed without it produced `127.0.0.1:null`, and every stop hung
    until killed, whichever way the password was supplied.
  - With the key, stops took 4–6 s, exited 0, and a changed setting survived
    a restart.
  - The seed is written only when the file is absent; afterwards Transmission
    owns it.
- **Why that layout:** qBittorrent saved to `/downloads/` with partial files in
  `/downloads/incomplete/`. Transmission's LinuxServer default is
  `/downloads/complete`, which would add a level for FileBrowser, WebDAV,
  Infuse and Unpackerr. DHT, PeX and queue limits are left to the operator,
  who sets them in the UI once; the backup then carries them. *(Superseded
  by **DD-118**: the installer writes them.)*
- **Why no host whitelist:** with authentication on, Transmission accepted
  requests under an arbitrary `Host:` (verified), so `HOST_WHITELIST` would add
  nothing.
- **Why a stage-0 gate instead of removing qBittorrent:** its container
  publishes the same peer port, so Compose cannot start Transmission next to
  it. DD-96 keeps deletion with the operator. The gate fails before anything
  changes, prints `docker rm -f qbittorrent`, and leaves the
  `docker_qbit_config` volume alone.
- **Credential changes take effect immediately:** when the installer writes new
  credentials for Dozzle (DD-116) or Transmission, it restarts that container.
  Before, deleting Dozzle's `users.yml` and re-running wrote the file but left
  the running Dozzle on the old account until its next restart. The procedure
  previously given to the user was therefore incomplete.
- **Backups:** the scope becomes `transmission/settings.json` next to
  `filebrowser.db` and `wg-easy.db` (DD-114).
  - qBittorrent- and Portainer-era archives still validate; their extra
    entries are ignored.
  - A service such an archive does not carry (Transmission) is neither
    compared nor written. Restore now skips services absent from the archive
    instead of removing the destination file. A rollback snapshot still
    removes a file that did not exist.
- **Verified on `nrm` (2026-09-13):**
  - bats 106 ok, including functional tests for the settings seed, the
    credential files and the restart; `bash -n` and `shellcheck` clean.
  - With qBittorrent present, the installer exited 1 at stage 0 and
    `state.env`, `compose.yaml` and every container were unchanged.
  - After qBittorrent was removed, the v2-82 → v2-83 run created
    Transmission with the seed and credentials and recreated none of the
    other five containers.
    - `settings.json` showed `/downloads`, peer-port 61005, `rpc-port` 9091
      and a hashed password; `docker inspect` held no password.
    - `state.env` carried `TORRENT_PUBLIC_PORT` and no `QBIT` key.
  - DNS: `torrent.ayc` resolved; `qbit.ayc` became NXDOMAIN.
  - Login through Caddy: the RPC answered 401 without or with a wrong
    login, 409 (authorized) with the right one; the web UI answered 200.
  - `--check` passed and both firewall chains held the 61005 rules. From the
    Mac the public peer port was reachable and 61006 was not.
  - `docker restart` took 4 s and was clean.
  - Credential change: after deleting the Dozzle and Transmission credential
    files and re-running with a new password, the new password worked and
    the old one was rejected, with no manual restart. Reverting worked the
    same way, and a final run asked nothing and changed nothing.
  - Backup: the round-trip passed 19 checks. A live backup held three files,
    and a qBittorrent-era `check` reported two to load. A self-restore
    stopped and started Transmission cleanly.

### DD-118: The installer sets up FileBrowser and Transmission; the backup keeps only wg-easy (2026-09-14)

- **Transmission part superseded by DD-127 (2026-09-14):** qBittorrent
  returned, and the installer no longer writes torrent preferences. The
  FileBrowser account part stands (now from the input file, DD-119).

- **Decision:**
  - Stage 0 asks for a FileBrowser user name and password (at least
    `FILEBROWSER_MIN_PASSWORD_LENGTH`, 12) when `filebrowser.db` is absent.
    Stage 4 creates the database before Compose starts. An existing database
    is kept and nothing is asked.
  - The Transmission settings seed adds `dht-enabled`, `pex-enabled` and
    `lpd-enabled` false, `download-queue-enabled` true and
    `download-queue-size` 12. As before, it is written only when
    `settings.json` is absent.
  - `container-backup` carries `wg-easy.db` only. FileBrowser and
    Transmission join Portainer and qBittorrent as legacy archive entries:
    validated, never written. A backup or restore no longer stops their
    containers.
- **Why:** the user wants the installer to take over from the backup wherever
  it can. After an install they changed only the FileBrowser password and a
  few torrent preferences (DHT/PeX/local discovery off, at most 12 active
  downloads, as they had set in qBittorrent). Both are fixed answers an
  installer can give on every install. wg-easy's server key and peers cannot
  be recreated without re-provisioning every client, so they stay in the
  backup.
- **Where the FileBrowser password comes from — the user chose the prompt
  (2026-09-14) over:**
  - The password from the existing backup: the backup holds only a bcrypt
    hash, and it is encrypted with a password that must not leave the
    workstation (DD-112).
  - A plaintext password in `defaults.env`: it would enter git history and
    every exported `.command`.
  - A git-ignored local secrets file sent over SSH: plaintext on the
    workstation, and a new transfer path in the launcher.
- **How the account is created — measured on `nrm` with throwaway containers
  (FileBrowser 2.63.23):**
  - A first start without a database ("quick setup") creates `admin` with a
    random password written to the container log. Quick setup takes a user
    name and a bcrypt hash as flags of the serving process itself.
  - `config init --viewMode mosaic --sorting.by '' --redirectAfterCopyMove
    --hideLoginButton` produced settings identical to quick setup's apart
    from the random key. Without those flags four defaults differed.
  - The user record is `.settings.defaults` from `config export` plus id,
    name, hash, `lockPassword: false`, `rules: []` and `perm.admin`.
    `users import` reads it from a file. The imported user matched quick
    setup's user field for field apart from name and hash.
  - `htpasswd -niB -C 10` reads the password from stdin. FileBrowser accepted
    its `$2y$` hash: login 200, a wrong password 403, `admin`/`admin` 403.
    Cost 10 is FileBrowser's own.
  - `users import --replace` writes `users.backup.json` into the working
    directory and failed on the container's `/`. A plain import into an
    empty database needs no backup file, and `-w /database` keeps the
    working directory writable anyway.
- **Safety properties:**
  - The CLI runs as `DOWNLOADS_UID` in a one-shot container with
    `--network none` and only a temporary directory mounted. Its stdout
    (`config init` prints the settings, key included) is discarded; stderr
    goes to a file in that directory and is shown only on failure.
  - The password reaches `htpasswd`'s stdin and nothing else: not argv, a
    log, `docker inspect` or a plaintext file.
  - The database is verified — exactly one user, that name, admin, a bcrypt
    hash — and moved into place with one `mv`. A failure removes the
    temporary directory, so no half-made database is left for a re-run to
    keep.
  - A database deleted under a running container is rebuilt, and the
    container restarted, the same rule as the Dozzle and Transmission
    credentials (DD-117).
- **Why 12:** FileBrowser refuses a shorter password when it is changed in its
  UI. The installer enforces the same minimum at the prompt and stores it in
  the database.
- **Trade-offs:** not carried to a new host any more:
  - A FileBrowser password changed later in its UI, other FileBrowser users
    and share links.
  - Transmission preferences changed later in its UI.

  Existing installs keep their `settings.json`: the preference keys reach
  only a fresh install, or a Transmission whose `settings.json` was removed
  while it was stopped. Deleting `filebrowser.db` is the way to recover a
  forgotten FileBrowser password; shares go with it.
- **Verified on `nrm` (2026-09-14):**
  - bats 108 ok, including functional tests for the account creation
    (success, a rebuilt database under a running container, a failed import
    that leaves nothing) and the preference seed; `bash -n` and `shellcheck`
    clean. The isolated backup round-trip passed 20 checks.
  - v2-83 → v2-84 over existing data: exit 0, no FileBrowser prompt, and no
    container recreated or restarted.
  - With `filebrowser.db` deleted, an 11-character password stopped stage 0
    with exit 1; `state.env`, `compose.yaml` and the missing database were
    unchanged.
  - The fresh account, in the same run as a Transmission seed (Transmission
    stopped, `settings.json` moved aside):
    - Exit 0; FileBrowser was restarted on the new database.
    - Through Caddy: login 200, wrong password 403, `admin`/`admin` 403.
    - One user, an admin; `minimumPasswordLength` 12; new-user view `mosaic`.
    - Database `0640 1000:1000`, no temporary directory left, no password line
      in the container log and none in `docker inspect`.
  - Transmission, started by stage 7's `compose up`:
    - RPC `session-get` reported DHT, PeX and LPD off, the queue on at 12,
      `/downloads` and peer port 61005.
    - The image's init script kept the keys and authentication on.
    - After a restart (exit 0) the file still held them.
  - A no-op re-run: exit 0, no prompt, database and containers unchanged,
    firewall `--check` passed.
  - Backup from the Mac:
    - Took 11 s and held `manifest.json` and `wg-easy/wg-easy.db`. Only
      wg-easy was restarted.
    - `check` reported one file to load for the new archive, a v2-83-era
      archive (three files) and a Portainer-era archive (four files), with
      the legacy note on the older two.
    - Restoring the v2-83-era archive took 11 s and restarted only wg-easy.
      The FileBrowser database and Transmission settings were untouched,
      the FileBrowser login still worked, every peer was present and no
      remote temporary directory was left.
- **Superseded in part by DD-119 (2026-09-14):** the accounts come from a
  git-ignored input file instead of prompts. An existing database is synced
  to that file on every run instead of being kept, so a password changed in
  FileBrowser's UI is reset on the next run.

### DD-121: kurulum.env lists the WireGuard peers; the server generates what is missing and hands it back (2026-09-14)

- **Superseded by DD-124 (2026-09-14):** peers are generated and kept on the
  server and managed with `wireguard.command`; `WG_PEERS` and the fetch-back
  are gone.

- **Decision:**
  - **What the operator writes:** `kurulum.env` names the peers (`WG_PEERS`,
    space-separated) and sets `WG_CLIENT_DNS`, `WG_CLIENT_KEEPALIVE` and
    `WG_CLIENT_DNS_OVERRIDE` (`name=dns; name=dns`) for every profile. Empty
    fields take `defaults.env`: wg-easy's DNS, keepalive 0, `AllowedIPs
    0.0.0.0/0, ::/0`.
  - **What `kurulum/wireguard/` holds:** the keys. A listed peer with a
    `<name>.conf` keeps its private key, PSK and addresses. A listed peer
    without one is new: stage 0 gives it the lowest free host in the `/24` and
    the same number in hex on the `/112` (wg-easy's `.2` ↔ `:2`), and
    `ensure_wireguard` generates its key and PSK with `wg genkey`/`wg genpsk`.
    With no `sunucu.key` and no profiles the server key is generated too; with
    profiles but no `sunucu.key` stage 0 stops, since those profiles only work
    with their own server key. A profile not in `WG_PEERS` is ignored with a
    warning and is never deleted.
  - **Profiles are rendered from the keys plus the env settings** (wg-easy's
    layout, `Endpoint = WG_ENDPOINT_HOST:WG_PUBLIC_PORT`). Every profile that
    is new or differs from the one sent — and a generated `sunucu.key` — is
    written only to `OUTPUT_WG_DIR` on `tmpfs`, and a new peer's QR code is
    printed to the terminal, never the log. `wg0.conf` still holds public keys
    and PSKs only.
  - **The launcher fetches the output after the install session, whatever its
    exit code,** into `kurulum/wireguard/` (`600`), and removes the server
    copy only after every file is in place. Stage 0 of the next run clears any
    output that was never fetched; a peer whose profile was lost is generated
    again.
  - `wireguard/` is optional in the launcher; `sunucu.key` is sent only when
    present.
- **Why:** the user asked to manage peers from the one file: they set a
  keepalive of 21 everywhere and a different DNS on one device, and want to
  add a device by adding a name. The Mac cannot generate a profile: macOS
  LibreSSL cannot derive an X25519 public key (measured for DD-120), and the
  server already has `wireguard-tools`.
- **Why the keys stay in files and not in `kurulum.env`:** a profile is what
  the device imports, and the private keys must survive reinstalls. Keeping
  them per device lets the env stay readable and lets a lost device be
  re-provisioned by deleting its file.
- **Why nothing is deleted automatically:** removing a name from `WG_PEERS`
  removes the peer from the server, but deleting its `.conf` would destroy a
  key that cannot be recovered. The warning names the file.
- **Trade-offs:**
  - A client private key now exists on the server for the length of one run
    (memory and `tmpfs`), as with wg-easy's download; it never reaches the
    disk.
  - The QR code shows a private key on screen.
  - An existing profile's `Endpoint` host is rewritten to `WG_ENDPOINT_HOST`
    (the WAN IPv4).
- **Verified (2026-09-14):**
  - bats 121 ok, with `bash -n` and `shellcheck` clean. The new tests cover
    peer planning (kept vs new, the lowest free address skipping used ones,
    hex IPv6 for host 10, DNS overrides, unlisted profiles, a fresh folder),
    twenty rejection cases for profiles and env fields that never echo a key,
    key generation with only public keys in `wg0.conf`, the hand-back of new
    and changed profiles only (with a generated `sunucu.key` when there was
    none), the QR for new peers only, and the launcher removing the server
    copy only after the files are in place. Three deliberate mutations each
    failed their test.
  - **Live on `nrm`, running the exported v2-87 `.command` with the operator's
    `kurulum/` folder:**
    - The operator added `WG_PEERS` with the four migrated devices plus a
      temporary `deneme`, keepalive 21 and a DNS override on one device.
    - Exit 0. `deneme` got `10.8.0.6` (`:6`), a generated key and PSK, and a
      QR code in the terminal.
    - All five profiles came back into `kurulum/wireguard/` (`600`): the four
      existing ones rewritten with keepalive 21 and their DNS, the override on
      its device only.
    - Each profile's derived public key, PSK, server key and `AllowedIPs`
      matched `wg show wg0 dump`, and the server's output folder was gone.
  - **The fetched `deneme` profile, used as a client in a network namespace:**
    handshook; reached the three UIs and the internet over IPv4 and IPv6; was
    refused SSH, WebDAV on the TS IP and another peer.

### DD-127: qBittorrent returns; its settings and account are its own (2026-09-14)

- **Settings part superseded by DD-129 (2026-09-14):** the installer now writes
  qBittorrent's managed settings from a template and the account from
  `TORRENT_USER`/`TORRENT_PASS`. The image choice, ports, the stage 7 `403`
  check and the Transmission gate stand.

- **Context:** the user found Transmission slow again and asked to go back to
  qBittorrent.
  - They were told that the v2-84 preferences carried over from Transmission
    (DHT, PeX and local discovery off, a queue of 12) limit peer discovery
    whatever the client.
  - They chose to keep DHT/PeX/LSD off.
  - Docker against a host package (`qbittorrent-nox` 5.1.0 on Debian 13) was
    weighed. Writing the config is the same work either way (PBKDF2 password,
    qBittorrent rewrites the file on exit), while Docker keeps a current
    version on every OS, logs in Dozzle and one layout. Docker stays.
- **Decision:**
  - `qbittorrent` service, `lscr.io/linuxserver/qbittorrent:latest`
    (measured 5.2.3 with libtorrent 2.0.14):
    - `/config` on `/etc/master-stack/qbittorrent` (`QBITTORRENT_DATA_DIR`),
      and `/downloads`.
    - Web UI `127.0.0.1:61006 → 61006` behind Caddy `torrent.${LOCAL_DOMAIN}`
      and `caddy-wg`. Peer port 61005 TCP+UDP. Stop grace 30 s.
  - **No installer-written settings or account**, at the user's request: they
    set everything in the web UI once. The planned next step (v2-93) pulls the
    whole config file into `kurulum/` and restores it on a fresh install.
    - `ensure_qbittorrent_dir` only creates the directory
      (`0750`, `DOWNLOADS_UID:GID`).
    - The first start prints a temporary `admin` password to the container
      log. The summary points to Dozzle; the installer never reads or logs
      the value.
  - **Ports cannot drift with a restored file:**
    - The image's `svc-qbittorrent/run` passes `--webui-port=${WEBUI_PORT}`
      and `--torrenting-port=${TORRENTING_PORT}` on every start (read from
      the image).
    - `init-qbittorrent-config` copies the default file only when
      `qBittorrent.conf` is absent.
  - **Stage 7:** unauthenticated `GET /api/v2/app/version` through Caddy must
    be `403` (measured: `403`; a wrong login gets `401`).
    - Requests reach the container from the Docker gateway, not localhost.
    - An authentication bypass for localhost or a whitelisted subnet set in
      the UI would therefore let every tailnet or WireGuard client in, and
      the check fails the install.
    - The `docker port qbittorrent` publish checks return.
  - **Input file:**
    - `TRANSMISSION_USER`/`TRANSMISSION_PASS` are removed.
    - `read_input_file` takes an optional list of removed keys and names them
      ("artık kullanılmıyor; bu satırı silin") instead of "unknown field". The
      value is still never echoed.
  - **Leftover gate:** a `transmission` container stops stage 0 before any
    change (it holds the peer port) and prints `docker rm -f transmission`.
    Its directories are not removed (DD-96).
- **Verification:**
  - bats 123 ok (3 skips as before). `shellcheck -x` is clean.
  - Five mutations each failed a test: stage 7 expecting `401`, `WEBUI_PORT`
    dropped, the removed-key message dropped, the gate on `qbittorrent`, and
    a settings write in `ensure_qbittorrent_dir`.
  - **A throwaway container on `nrm`** confirmed:
    - the config paths (`qBittorrent.conf`, `categories.json`,
      `watched_folders.json`, `rss/feeds.json`);
    - the temporary password line in the log (value not printed);
    - `GET /` 200, API 403, wrong login 401;
    - stop in 3 s with exit 0.
  - **Live on `nrm`:** the host held the operator's own v2-90 manual install
    (Tailscale node `nrm-1`, `100.85.4.106`, WireGuard peer `iph0`). The run
    used the scratch test inputs, with the real account files saved and
    restored.
    - The old input file with `TRANSMISSION_*` stopped at stage 0 with
      "satır 37: TRANSMISSION_USER artık kullanılmıyor", changing nothing.
    - With the lines deleted, the Transmission gate stopped at stage 0 and
      the host stayed on v2-90.
    - After `docker rm -f transmission`, the install exited 0 in 22 s:
      - `qbittorrent` was up with 61005 TCP/UDP on `0.0.0.0` and 61006 on
        loopback, and the log held a temporary password line.
      - Through Caddy, `torrent.ayc` answered 200, the API 403 and a wrong
        login 401; `10.8.0.1:61006` answered 200 and 403.
      - 61005/tcp was reachable from the Internet, `--check` passed, no unit
        had failed, and `iph0` was kept.
    - A re-run was a no-op: unit and container start times, `wg0.conf`, both
      Caddyfiles and `compose.yaml` were unchanged.
    - The real WebDAV, Dozzle and FileBrowser files were restored
      hash-identical.
    - The old `/etc/master-stack/transmission{,-auth}` directories remain
      for the operator to delete.

### DD-128: Pulled WireGuard and qBittorrent settings rebuild a server; restored only where absent (2026-09-14)

- **First real rebuild (v2-95, 2026-09-14, by the operator):** `nrm` was reset
  to a bare Debian 13 and the v2-95 `.command` ran with the operator's own
  `kurulum/`, which held the backup from option 6.
  - The install log recorded the accounts written and the qBittorrent file
    created from the template (DD-129).
  - It also recorded "WireGuard kurulum/wireguard'tan geri yüklendi: sunucu
    anahtarı, 4 peer, 4 profil", the login check, "Temel doğrulamalar geçti",
    and no hash or auth-key trace.
  - Checked read-only afterwards:
    - every unit was active with none failed, `--check` passed with
      `MASTER-FORWARD` first, and all 5 containers were up;
    - Tailscale came back as `nrm` on a new IP (100.102.206.71), exit node
      offered and `ayc` split DNS already repointed by the operator;
    - the tailnet UIs, WebDAV `401`, qBittorrent API `403` and DNS/`REFUSED`
      all held.
  - Two devices (`Mcp0`, `NxiPh0`) reconnected with untouched profiles; the
    other two had not come online yet.
  - The server's `wg0.conf` and profiles still hashed identical to the Mac
    backup, and no `RESTORE_DIR` was left.
- **Tool merged (v2-95, 2026-09-14):** `ayarlar.command` is gone. The same pull
  is option 6 "Yedek al" of `wireguard.command`, reusing its SSH connection
  and version check. `remote()` now runs `ssh -n`: a live test showed that an
  ssh reading stdin could swallow queued menu input. The installer and
  launcher only changed their wording.
- **qBittorrent part removed by DD-129 (2026-09-14):** qBittorrent is no longer
  pulled or restored. `ayarlar.command` pulls WireGuard only and deletes a
  `kurulum/qbittorrent/` copy left by v2-93. Stage 0 now rejects a
  `qbittorrent/` file, and the WireGuard part stands.

- **Context:** the user wants a reset server back in one pass, with the same
  WireGuard devices working and qBittorrent configured as they left it.
  - v2-92 deliberately writes no qBittorrent settings: the operator sets them
    once in the UI.
  - DD-124 made a reinstall generate a new WireGuard key.
  - The user proposed pulling both from the server into `kurulum/` and having
    the installer put them back.
- **Decision:**
  - **`ayarlar.command`** (repository root, macOS `/bin/bash` 3.2, reads only
    `SSH_HOST`):
    - One SSH call runs a server-side script. It needs `state.env`, lists only
      `wg0.conf`, `clients/*.conf` and qBittorrent's `qBittorrent.conf`, and
      streams them as a tar relative to `/`.
    - qBittorrent's `categories.json`, `watched_folders.json` and
      `rss/feeds.json` are not pulled: the user changes only the settings
      file. The stage 0 whitelist rejects them.
    - The Mac extracts into a temporary directory inside `kurulum/`, then
      places `wireguard/sunucu/wg0.conf`, `wireguard/<name>.conf` (mirrored:
      a local profile the server no longer has is removed) and
      `qbittorrent/qBittorrent.conf`, all `600` in `700` directories.
    - It prints per file only "değişti/aynı/silindi", plus the peer count, and
      warns if qBittorrent has no password yet.
  - **Launcher:** sends those files with `kurulum.env` when present.
    - Profile names are filtered, and profiles go only with a server
      `wg0.conf`.
    - Each file must be mode `600`.
    - The confirmation summary shows what was sent.
    - Its exit cleanup also removes `RESTORE_DIR`.
  - **Stage 0:** moves `wireguard/` and `qbittorrent/` into the root-only
    `RESTORE_DIR` (`/run`) before the input directory is deleted, then
    validates before any change:
    - Only the names above are allowed, each at most `SNAPSHOT_MAX_BYTES`
      (1 MiB), with no links or special files.
    - `wg_snapshot_check` accepts in `wg0.conf` only what master-stack
      writes:
      - `[Interface]`: `Address`, `ListenPort`, `MTU`, `PrivateKey`.
      - `[Peer]`: `PublicKey`, `PresharedKey`, `AllowedIPs` inside the
        WireGuard `/24` and `/112` as `/32` and `/128`.
      - Peer names must be valid and unique, and public keys unique.
    - Profiles may hold `PrivateKey`/`Address`/`MTU`/`DNS` and one `[Peer]`
      with `PublicKey`/`PresharedKey`/`AllowedIPs`/`PersistentKeepalive`/
      `Endpoint`.
    - Keys are checked by length and alphabet; mawk has no `{n}` intervals.
    - Messages name the line and field, never a key.
  - **Stage 4 / stage 5:** qBittorrent's files are placed only when
    `qBittorrent.conf` is absent, and `wg0.conf` and the profiles only when
    `wg0.conf` is absent.
    - A running qBittorrent is stopped first, because it rewrites its file
      on exit.
    - Profiles whose `Endpoint` is not `${WG_ENDPOINT_HOST}:${WG_PUBLIC_PORT}`
      are counted in a warning.
    - `ensure_wireguard` then keeps the key and peers and rewrites
      `[Interface]` from the installer's values.
  - `RESTORE_DIR` is removed right after stage 5.
- **Why "only where absent":**
  - While a server lives, peers are added with `master-wg` and preferences
    change in the UI. An older snapshot must not undo that.
  - qBittorrent and wg-quick rewrite or compare their own files, so
    enforcing a snapshot on every run would restart services.
  - The rule keeps re-runs no-ops. The operator pulls again after changes.
- **Why validation is strict:** wg-quick runs `PostUp`/`PreUp` lines as root,
  and the file arrives from the workstation. A tampered or hand-edited
  snapshot must stop the install, not execute. qBittorrent's `AutoRun`
  program runs inside the container as the unprivileged user; it is the
  operator's own setting and is not filtered.
- **Trade-off, stated:**
  - `kurulum/` on the Mac now holds the WireGuard server and device private
    keys and qBittorrent's password hash, next to the Tailscale auth key and
    passwords it already held.
  - They stay Git-ignored, `600`, and reach the server only in tmpfs.
  - Protecting that folder (FileVault) is the operator's part.
- **Limits:**
  - A server with a different public IP needs new device profiles; the
    installer warns about this.
  - `ayarlar.command` uses SSH to the public IP, so the Mac must be off its
    own WireGuard tunnel (DD-124's accepted limit).
- **Verification:**
  - bats 128 ok. `shellcheck -x` is clean on install.sh, common.sh and the
    exporter; the launcher and `ayarlar.command` parse under `/bin/bash`.
  - New tests cover:
    - rejection of `PostUp`, out-of-subnet `AllowedIPs`, short keys,
      duplicate or bad names, a missing key, extra `[Peer]` fields,
      `PostDown` and two `[Peer]`s in a profile, with no key echoed;
    - the file whitelist, links, the size limit and profiles dropped without
      a server file;
    - restore versus no-touch, stop/start around the qBittorrent file, bad
      and the Endpoint warning;
    - the stage wiring and `RESTORE_DIR` removal;
    - `ayarlar.command` against a fake server: byte-identical `600` copies,
      a stale profile removed, "aynı" on a second pull, and no key, hash or
      password in the output.
  - Six mutations were each caught.
  - **Live on `nrm`** (the operator's real host: `nrm-1`, peer `iph0`,
    qBittorrent account set), with the scratch inputs. Real account files,
    `/etc/wireguard` and qBittorrent's `/config` were saved and put back:
    - `ayarlar.command` pulled `wg0.conf`, `iph0.conf` and four qBittorrent
      files, all `600`, printing no content. After it was narrowed to
      `qBittorrent.conf` only, a second pull brought exactly `wg0.conf`,
      `iph0.conf` and `qBittorrent.conf`. The restore test was not repeated
      live: the only change removed three optional files from a copy loop,
      and bats covers it.
    - The v2-93 install over the existing v2-92 server reported both
      snapshots "sunucuda var; kullanılmadı". WireGuard, both Caddies,
      qBittorrent and both config files were unchanged, and no restore
      directory was left.
    - **Fresh simulation:** `wg-quick@wg0` was stopped, `wg0.conf`, the
      profiles and qBittorrent's `/config` removed, and the container
      stopped.
      - The install exited 0 in 15 s with both "geri yüklendi" lines.
      - The server public key, `wg0.conf`, the profiles and qBittorrent's
        account lines hashed identical to before.
      - qBittorrent printed no temporary password; the API answered 403 and
        `caddy-wg` was active.
      - The Mac's `iph0` tunnel, never touched, reconnected (handshake 9 s)
        and opened `10.8.0.1:61006`.
    - Afterwards `/etc/wireguard` compared identical to the saved copy, and
      qBittorrent's original `/config` (torrent state included) went back
      while stopped. Only its lockfile and log changed on start. The real
      accounts were restored, and the pulled test copies deleted.

### DD-129: The installer writes qBittorrent's settings from a template and the account from kurulum.env (2026-09-14)

- **Superseded by DD-151 (2026-09-18):** qBittorrent is a host module; its
  settings are seeded once and never rewritten, and the input file holds no
  qBittorrent account.

- **Context:** after DD-128 the user preferred no file pulling for
  qBittorrent: its settings should be part of the installer, the password in
  `kurulum.env`.
  - To take only real changes, qBittorrent was reset on `nrm` and its clean
    file kept. The user then set everything in the UI, and the two files were
    compared.
  - A reset was repeated once when the user picked a wrong option.
- **What the diff showed:** 22 keys in the clean file and 48 after.
  - The user's changes:
    - `Session\MaxActiveDownloads/Torrents/Uploads=12`;
    - `MaxConnections=800`, `MaxConnectionsPerTorrent=220`;
    - `MaxUploads=120`, `MaxUploadsPerTorrent=64`;
    - `Preallocation=true`, `RefreshInterval=600`, `TempPathEnabled=true`;
    - `General\Locale=en`.
  - Written by qBittorrent when options are saved, at their defaults, and not
    managed: `FileLogger\*`, `AutoDeleteAddedTorrentFile`,
    `MailNotification\req_auth`, `WebUI\AuthSubnetWhitelist`, RSS
    `AutoDownloader\*`.
  - DHT, PeX, LSD and anonymous mode stayed at their defaults this time, unlike
    the earlier configuration.
- **Decision:**
  - **`templates/qBittorrent.conf`** holds the managed keys:
    - The clean-file keys the image default provides: `[AutoRun]
      enabled=false`, save/temp paths, `QueueingSystemEnabled`,
      `[LegalNotice] Accepted`, `PortForwardingEnabled=false`, `UPnP=false`,
      `WebUI\Address=*` and `ServerDomains=*`. Without them a fresh file
      would lack what the image would have copied.
    - The user's changes.
    - `WebUI\LocalHostAuth=true` and `WebUI\AuthSubnetWhitelistEnabled=false`,
      so the UI cannot be opened without a login through Caddy.
    - Not managed: ports (`Session\Port`, `WebUI\Port`,
      `Connection\PortRangeMin`: the image passes them on the command line),
      generated values (`Session\SSL\Port`, `MigrationVersion`, `Cookies`)
      and the account lines.
  - **Input:** `TORRENT_USER` (`^[A-Za-z0-9][A-Za-z0-9._@-]{0,63}$`) and
    `TORRENT_PASS` (at least `TORRENT_MIN_PASSWORD_LENGTH`, 8), required.
    `python3` joins the base packages.
  - **`sync_qbittorrent_config`** (stage 4, before Compose):
    - Flattens the template, adds `WebUI\Username` and
      `WebUI\Password_PBKDF2`, and compares key by key (INI-aware awk; keys
      contain backslashes and values `=`).
    - No difference: nothing happens.
    - A difference: `docker stop qbittorrent` first, because qBittorrent
      rewrites its file on exit. The merge then sets managed keys in place,
      adds missing ones to their section and missing sections at the end,
      drops a duplicate managed key and keeps every other line. The file is
      written atomically (`0600`, `DOWNLOADS_UID:GID`), and the container
      started again.
    - The log names the changed keys, never a value.
  - **Password hash:** qBittorrent's format `"@ByteArray(salt:key)"`,
    PBKDF2-HMAC-SHA512 with 100000 iterations, a 16-byte salt and a 64-byte
    key.
    - `python3` reads the password from stdin, and the existing hash from the
      environment rather than argv.
    - A new salt every run would be a false change on every run, so the
      existing hash is verified against `TORRENT_PASS` and kept when it
      matches. This is the WebDAV bcrypt pattern.
  - **Stage 7 `qbit_login_check`:**
    - Logs in on loopback with the input account; the body is urlencoded by
      `python3` from stdin and posted with `curl --data @-`.
    - qBittorrent 5.2.3 answers a good login with `204` (measured), so `200`
      or `204` plus a `SID` cookie counts as success.
    - Only "not ready" (`000`/`5xx`) is retried. A refusal stops at once,
      because qBittorrent bans an IP after repeated failures, and every Caddy
      request arrives from the same Docker gateway.
    - It then requires the username and both bypasses off in
      `/api/v2/app/preferences`.
    - `TORRENT_NEW_PASS` is unset afterwards.
  - **Removed:** `restore_qbittorrent_snapshot` and the qBittorrent parts of
    `ayarlar.command`, the launcher and `validate_snapshot` (DD-128).
- **Why this over pulling the file:**
  - The template holds only settings, reviewed in Git, while the file held a
    password hash on the Mac.
  - Password changes follow `kurulum.env` like every other account.
  - A reset server comes up configured without a prior pull.
- **Trade-off:**
  - A managed setting changed in the UI returns to the template on the next
    run. Changing it for good means editing the template.
  - If a future qBittorrent renames a managed key, every run would see a
    difference and restart the client. The log names the key, so this cannot
    go unnoticed.
- **Verification:**
  - bats 132 ok. `shellcheck -x` is clean.
  - New tests cover:
    - the template contents, and the absence of ports, generated keys and the
      account;
    - PBKDF2 format, salt and key length, verify/mismatch/bad-format exit
      codes, fresh salts and a known vector;
    - diff/merge with in-place change, added keys and sections, preserved
      unmanaged lines, `=` in values, duplicate dropping, idempotence and a
      file built from nothing;
    - the sync: write once, no-op, UI-change revert plus a new password with
      stop/start, and no password or hash in the log;
    - the login check: stdin only, no retry on refusal, `204` plus `SID`.
  - Six mutations were each caught (after a duplicate-key fixture was added
    for the merge).
  - **Live on `nrm`** (the operator's host). The real account files and the
    user's own qBittorrent `/config` were saved and put back byte-identical;
    scratch inputs with `TORRENT_USER=admin`:
    - First run over the user's configured qBittorrent: the diff was exactly
      `WebUI\AuthSubnetWhitelistEnabled`, `WebUI\LocalHostAuth` and the two
      account lines, confirming that the template matches the user's
      settings.
      - The login check failed on `HTTP 204`, qBittorrent's success code, and
        was fixed.
      - The Python-generated hash logged in (`204` with a `SID` cookie).
    - Re-run: "şablonla aynı; dokunulmadı". The container start time and the
      file hash were unchanged.
    - A UI change through the API (`max_active_downloads=3`, `dht=false`)
      logged exactly `[BitTorrent] Session\MaxActiveDownloads`. The API
      then showed 12, and `dht` stayed false (unmanaged).
    - A fresh `/config`: "(yeni dosya)", `600 1000:1000`, no temporary
      password. The API showed every template value (12/12/12, 800/220,
      120/64, preallocation, 600 ms, temp path, `en`, queueing, paths, UPnP
      off, ports 61005/61006) and the `403` check held.
    - After `docker restart` made qBittorrent rewrite its file (47 lines),
      the next run was still a no-op.

### DD-176: Local access by default when creating a WireGuard network (2026-09-28; superseded by DD-177)

- **Decision (v2-150):** remove the creation screen's access card, toggle, draft
  state and unused styles. The backend defaults an omitted scope to `ui`; the
  browser submits only port, DNS and label. First and additional networks use
  the same default. Preview and empty-state copy describe Internet + local.
- **Boundary:** Local still means the installed qBittorrent UI at that network's
  own IPv4 address. It never grants SSH, Konsol, WebDAV, DNS, tailnet, cross-network
  or peer access. No new firewall generator or global exception is introduced;
  existing `net-add`/`net-settings` and Caddy/firewall lifecycle remain authoritative.
- Existing network settings retain their Local switch. Explicit API `inet`/`ui`
  and the CLI's required scope remain compatible; invalid explicit scope is not
  silently defaulted. Re-runs never overwrite a saved internet-only choice.
- Existing internet-only networks on nrm may be enabled once through the
  revision-checked settings API, never through an installer migration. Live
  inspection found only wg0, already `ui`, so no existing scope change was needed.
  Keys, peer profiles, DNS, ports and network activity must be preserved.
- Tests cover absent scope, explicit/invalid scopes, request/module gates, first
  and additional network creation, preview, cancelled/failed saves, polling drafts,
  mobile layout and the retained settings switch.

### DD-146: Retire FileBrowser; Konsol is the file manager (2026-09-16)

- **Context:** FileBrowser (classic) was kept beside the console's file
  manager (**DD-139**) because it could still upload, select many items and
  search. **DD-145** added all three to Konsol. The image is maintenance-only
  with an archive risk already recorded in **DD-92**, and it carried its own
  account, port, name, Bolt database and ~150 lines of account code.
- **Decision:** remove it. The input keys, port 61007, the image, the database
  handling and the WireGuard edge entry go; `file.<domain>` keeps resolving and
  redirects to `panel.<domain>` so bookmarks still work.
- **Trade-off, accepted:** FileBrowser was also reachable on a WireGuard network
  with `ui` scope. Konsol is tailnet-only by design (**DD-140**: it manages
  WireGuard itself), so after this change a device that is only on WireGuard
  has no file manager. Exposing the file backend on WireGuard would put the
  account that can create tunnels on that edge; not done.
- **No migration code** (fresh-install rule): a re-run drops the container
  through `docker compose up --remove-orphans`; the old data directory is left
  in place and named in the changelog.

### DD-142: One rclone; the downloads folder is never published (2026-09-16)

- **Context:** with shares working, the user asked to drop the full-folder
  WebDAV and keep a single rclone: "kullanıcı panelden paylaşılacakları seçerek
  ayarlasın, paylaşım için altyapı hazır olsun sadece". They chose to keep the
  share's name and account (`paylas.<domain>`, `SHARE_USER`) and to retire
  `webdav.<domain>`, port 61003 and the `infuse` account.
- **Decision:** the `webdav` service, its name, port, htpasswd and the three
  input keys are removed. What used to be the "share" WebDAV is now simply *the*
  WebDAV: `paylasim`, read-only, rooted at `DOWNLOADS_PATH/.pay/w`.
  - The blast radius of the WebDAV account drops from "every download" to "what
    the operator picked in Konsol", and there is one account, one port and one
    name instead of two of each.
  - `docker compose up -d --remove-orphans` keeps the file the single source of
    truth: the retired container is removed on the next run instead of lingering
    with the old, wide-open root.
  - `unpackerr` still needs the trash and the share folder hidden; the WebDAV
    that needed the same tmpfs is gone with the service.
- **Cost:** devices configured against `webdav.<domain>` must be re-added once
  with the share address and account. Accepted by the user; it is a one-time
  step per device and the reason the whole-folder endpoint existed (Infuse) is
  served by the share.

### DD-141: Share links over one read-only WebDAV, built from symlinks (2026-09-16)

- **Context:** the user asked for a share link for files, served by WebDAV so
  Infuse can open it. Their decision after the design round: **one account for
  everything** — the address, user, password and port stay the same for every
  share, and the duration options (1/7/30 days, open-ended) stay.
- **Decision:**
  - **A second rclone, not the existing WebDAV.** The Infuse WebDAV serves the
    whole downloads folder with the operator's own account; a guest must see
    only what was shared. `paylasim` runs the same image with `--read-only`,
    the downloads folder mounted `:ro`, and its root at
    `DOWNLOADS_PATH/.pay/w`.
  - **Sharing is a symlink, not a copy or a mount.** The panel (uid 1000)
    creates `.pay/w/<name> -> ../../<path>` and rclone follows it with
    `--copy-links`. No data is copied, a file that lands in a shared folder
    later appears by itself, and unsharing is one `unlink`.
    - Per-share bind mounts would need root and mount propagation into the
      container; per-share Docker volumes would mean recreating the container
      for every share, which would give the panel Docker access — that is root.
      The user's own question ("can we add more volumes?") is answered by one
      fixed mount plus links.
    - The registry (`.pay/kayit.json`) lives one level above the served root,
      so it is never served. A link with no registry entry is swept away, and
      so is an expired one; the sweep runs on every listing.
  - **One account, held twice on purpose.** rclone reads a bcrypt htpasswd;
    the console shows and copies the password, so the installer also writes a
    root-only plaintext copy that reaches the file backend as a systemd
    credential. Both come from `kurulum.env` in the same step, so they cannot
    drift. The trade-off is deliberate: the share password protects read access
    to files the operator chose to share, and being able to hand it out (or see
    what it is) is the point of the feature.
  - **What the account holder sees.** Everything currently shared, and nothing
    else: the share root holds only the links. The cost of one account is that
    the password cannot separate one guest from another — stated in the console
    before the share is created.
  - **Hidden from the rest of the stack.** `.pay` is an empty read-only tmpfs
    in `unpackerr` and `webdav` (the trash trick from DD-139), so Infuse does
    not list the same film twice and Unpackerr does not extract an archive a
    second time through a link. The file panel hides `.pay` from listings and
    refuses to walk into it.
- **Second address (v2-107):** Infuse on an Apple TV could not resolve
  `paylas.<domain>` (mobile clients could). The share therefore answers on
  `{$TAILSCALE_IPV4}:{$SHARE_PORT}` as well, exactly as the Infuse WebDAV does
  for the same reason (**DD-98**); the console shows both addresses.
- **Why not Tailscale Funnel or node sharing:** both need changes in the
  Tailscale admin console, which is outside what the installer touches.
- **Known limit:** a malicious symlink *inside* shared content is followed like
  any other (that is what `--copy-links` means); the container only has the
  downloads folder, read-only, so the blast radius is the operator's own
  downloads.
- **Verified (2026-09-16):** bats 154 ok, including the sweep, the refusals
  (root, trash, share folder, escape) and the installer wiring.

### DD-218: qBittorrent's fresh-profile defaults are the user's choice (v2-196)

- **Request (user, 2026-10-04):** after the audit of what the install writes, "qbittorrent için
  düzenlenebilir ayarları listele bir tercihte bulunalım ve default olarak kaydedelim". The list came
  from the shipped qBittorrent 5.2.4 itself (a throwaway, network-less container's
  `/api/v2/app/preferences`). The user chose: no UPnP/NAT-PMP, no LSD, required encryption, anonymous
  mode, 15 active downloads/uploads/torrents, half-finished files in a separate folder, preallocated
  files; seeding unlimited and the English interface (qBittorrent's defaults) were kept.
- **Seed:** `magaza/torrent/qBittorrent.conf` adds exactly `Session\LSDEnabled=false`,
  `[Network] PortForwardingEnabled=false`, `Session\Encryption=1`, `Session\AnonymousModeEnabled=true`,
  `Session\MaxActive{Downloads,Uploads,Torrents}=15`, `Session\TempPathEnabled=true`,
  `Session\TempPath=DOWNLOADS_PATH/incomplete/` and `Session\Preallocation=true`. The key names
  were not assumed: a throwaway container got the values through `setPreferences` and wrote these
  keys itself. The incomplete folder is the package's declared `PAKET_KLASORLER`, already refused by
  shares and reported by `klasorler.py`.
- **Still DD-178's rule otherwise:** the seed is written only into an empty profile; `kur` writes
  only the form's account and folder (and `WebUI\Address`); reapply and reinstall keep every
  preference of an existing profile; the user changes them in qBittorrent, and the defaults test
  proves such a change survives a restart. Existing installs get these defaults only from a fresh
  profile (reinstall with its data removed) or by changing them in qBittorrent.
- **Trade-offs, stated:** required encryption and anonymous mode reduce the number of peers and
  some private trackers refuse anonymous clients; preallocation reserves the full size at the start.
- **Verification:** `tests/torrent-defaults-linux.py` now runs the package's container image (the
  native binary left with DD-209) inside a private network namespace: the chosen values are applied,
  everything else equals the same qBittorrent's defaults, the login gate holds (5.2 answers a good
  login with an empty 204), and user changes persist.
- **Retired (v2-197):** reverted by DD-219 at the user's request; qBittorrent's own defaults apply again.
