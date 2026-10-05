# OS-Awareness and Optimisation Review

> **Archived (v2-96):** this review describes the system at the version it names. Parts of that system are gone, such as wg-easy, Portainer and qBittorrent's defaults. For current behaviour see [`contract.md`](../contract.md) and [`design-decisions.md`](../design-decisions.md).

**Date:** 2026-09-08 · **Reviewed version:** `2026.08.06-v2-73`
**Target host:** `nrm` — Ubuntu 26.04.1 LTS (resolute), kernel `7.0.0-31-generic`,
amd64, systemd 259, Docker 29.8.0, Tailscale 1.102.3, netcup VPS, 8 GB / 248 GB
**Method:** full source review + read-only live discovery on `nrm` + one
controlled `systemd-resolved` restart. Workstation static gates re-run:
`bash -n` clean, `shellcheck -x` clean, `bats tests` 80 passed / 3 skipped.

Companion documents: [`contract.md`](../contract.md),
[`architecture.md`](../architecture.md), [`design-decisions.md`](../design-decisions.md),
[`optimization-review.md`](optimization-review.md) (2026-08-07, `v2-27`).

---

## 1. Summary

The installer already detects the OS correctly. `require_supported_os`
(**DD-102**) gates on the `ID`/`VERSION_CODENAME`/`VERSION_ID` triple and both
apt repo families are derived from it, never hardcoded. Everything else that
differs between Debian and Ubuntu is handled by *capability probes* rather than
distro identity — `command -v ufw`, `systemctl is-active systemd-resolved`,
`readlink /etc/resolv.conf`. **That design is right and should not be replaced
by a distro switch statement.**

The gap is not detection. It is that OS-conditional steps are applied and never
checked, and that identity is never recorded. Three consequences, all found on
the live host:

| # | Finding | Severity | Evidence |
|---|---|---|---|
| A1 | `DNSStubListener=no` has **no effect** on Ubuntu 26.04; the installer reported success for a step that did nothing. *Fixed in v2-77 by reading the state back (DD-109); the "bind race" this entry originally also claimed was disproved by experiment — see §4* | FIXED | `127.0.0.53:53` UDP+TCP bound by `systemd-resolve`; `dig example.com @127.0.0.53` answers, after a clean restart with the drop-in last in the merge order |
| A2 | `needrestart` **automatically restarts** sshd / docker / containerd / tailscaled / caddy / dnsmasq during every `apt-get` call on Ubuntu | MUST FIX | `needrestart 3.11` installed, apt `DPkg::Post-Invoke` hook active, `/usr/sbin/needrestart:255` sets `$nrconf{restart}='a'` in Ubuntu mode |
| A3 | The installer's `sysctl.d` drop-ins are **not guaranteed to win at boot** — a provider file sorts after them | SHOULD FIX | `/etc/sysctl.d/99-nc-kernel.conf` sorts after `99-master-stack-netbuf.conf` and `99-master-tailscale.conf` |
| B1 | `state.env` records no OS identity, so an in-place release upgrade is invisible to a re-run | SHOULD FIX | `state.env` head: `V2_VERSION`, `WAN_*`, `TAILSCALE_*` — no `OS_*` |
| C2 | No assertion that the host `iptables` backend matches Docker's | SHOULD FIX | `iptables v1.8.11 (nf_tables)`, alternatives `auto` — correct here, unchecked everywhere |

Two things turned out **better** than expected and must not be touched: the
`max(current, floor)` netbuf logic (**DD-18**) demonstrably preserved the
provider's 64 MiB values, and the probe-over-identity style absorbed every
Debian/Ubuntu difference the tree currently handles.

---

## 2. What OS-awareness exists today

`require_supported_os` produces exactly two facts, `OS_ID` and `OS_CODENAME`,
consumed in exactly three places:

| Consumer | Use |
|---|---|
| `install_tailscale_repo` | `pkgs.tailscale.com/stable/$OS_ID $OS_CODENAME main` + keyring URL |
| `install_docker_repo` | `URIs: …/linux/$OS_ID`, `Suites: $OS_CODENAME` |
| `stage_6` | `debian-keyring` added to the Caddy package set only when `OS_ID=debian` |

Every other divergence is a probe, not a branch:

| Divergence | How it is handled | Verdict |
|---|---|---|
| ufw ships on Ubuntu, inactive | `command -v ufw` + `ufw status` → fail-closed in stage 0 | correct |
| systemd-resolved active | `systemctl is-active` → write `DNSStubListener=no`, then read the achieved state back | correct since v2-77 (**DD-109**); was applied-but-unverified — A1 |
| `/etc/resolv.conf` → stub symlink | `readlink` target test → repoint to resolved uplink | correct, and correctly a no-op once Tailscale owns the file |
| unattended-upgrades holds the dpkg lock | `-o DPkg::Lock::Timeout=60` on every call + `retry` | correct at the lock level; the *upgrade* itself is unowned |
| nft-default host lacks legacy IPv4 modules | unconditional `modprobe` + `modules-load.d` (**DD-10**) | correct — a problem found on Ubuntu, solved for every OS |
| Caddy repo | cloudsmith `any-version`, distro-agnostic | correct |

Live confirmation of the resolv.conf path on `nrm`: `/etc/resolv.conf` is now a
**regular file written by Tailscale** (`nameserver 100.100.100.100`), not the
stub symlink. The stage-6 repoint was a bootstrap and Tailscale took over
afterwards, exactly as **DD-102** predicts. Host DNS and split DNS are healthy:
`dig health.ayc @127.0.0.1` → `100.73.86.24`, `systemctl --failed` empty, all six
containers up and healthy.

**So the thesis of this review is narrow:** the tree detects the OS well and
adapts well. It does not *record* what it detected, and it does not *verify*
that the OS-specific adaptation landed.

---

## 3. MUST FIX

### A2 — `needrestart` restarts the installer's own daemons mid-stage

Ubuntu ships `needrestart` and wires it into apt:

```
/etc/apt/apt.conf.d/99needrestart:
DPkg::Post-Invoke {"test -x /usr/lib/needrestart/apt-pinvoke && \
                    /usr/lib/needrestart/apt-pinvoke -m u || true"; };
```

`/usr/sbin/needrestart` detects Ubuntu and, with no explicit `$nrconf{ui}`,
takes this branch:

```perl
} else {
    $nrconf{restart} = 'a';                       # automatic
    $nrconf{ui} = 'NeedRestart::UI::Ubuntu';
}
```

`DEBIAN_FRONTEND=noninteractive` — which `stage_1` exports — does **not** disable
this; it only suppresses the prompt (`$is_tty = 0 if($opt_r eq 'i' && …)`), and
the mode here is already `a`.

Net effect: after any `apt-get install`/`full-upgrade` that pulls a library
update, a process the installer does not own restarts `sshd`, `docker`,
`containerd`, `tailscaled`, `caddy` and `dnsmasq` — in the middle of stages 1, 2,
4 and 6. A `docker` restart there also fires the `docker.service.d` drop-in
(`master-firewall restart`), and a `tailscaled` restart fires
`refresh-tailnet-config`. Both are re-entrant, so nothing has broken yet; but
this is the same "two owners for one thing" class that the ufw gate already
refuses to tolerate, and it is the most likely explanation for any future
non-reproducible mid-install failure.

**Fix:** one line beside the existing `DEBIAN_FRONTEND` export in `stage_1`:

```bash
export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_SUSPEND=1     # honoured by /usr/lib/needrestart/apt-pinvoke
```

Harmless on Debian (no needrestart installed by default), so it needs no
`OS_ID` branch. The installer then owns every restart it performs, which is
already what stages 2, 5, 6 and 7 assume.

---

## 4. SHOULD FIX

### A1 — `DNSStubListener=no` does nothing on Ubuntu 26.04

`stage_6` writes `/etc/systemd/resolved.conf.d/master-stack.conf` and restarts
resolved when it changed. On `nrm` the file is present and correct:

```
$ cat /etc/systemd/resolved.conf.d/master-stack.conf
[Resolve]
DNSStubListener=no
```

`systemd-analyze cat-config systemd/resolved.conf` confirms it is the **last**
fragment in the merge order, after `/etc/systemd/resolved.conf`
(`DNSStubListener=yes`) and the two `/usr/lib` drop-ins. `man 5 resolved.conf`
on the host still documents the key. And yet, after a clean
`systemctl restart systemd-resolved`:

```
udp UNCONN 127.0.0.53%lo:53   users:(("systemd-resolve",pid=59461,fd=17))
tcp LISTEN 127.0.0.53%lo:53   users:(("systemd-resolve",pid=59461,fd=18))
udp UNCONN 127.0.0.54:53      users:(("systemd-resolve",pid=59461,fd=19))

$ dig +short example.com @127.0.0.53
172.66.147.243
104.20.23.154
```

The stub is up and serving. The setting is accepted and ignored on this
release.

**Impact today: none.** dnsmasq holds `127.0.0.1:53`, `[::1]:53` and the
`tailscale0` addresses; resolved holds `127.0.0.53` and `127.0.0.54`. No
overlap, no conflict, and nothing on the host points at the stub.

**Correction (2026-09-10): the latent start-order race claimed here does not
exist.** The original text argued that `bind-dynamic` "claims every address on
the listed interfaces as they appear", so a dnsmasq restart while resolved was
down would let dnsmasq take `127.0.0.53:53` and lock resolved out. That
inference was wrong, and it was tested rather than re-argued.

`bind-dynamic` binds the addresses **assigned to** an interface. `lo` carries
exactly `127.0.0.1/8` and `::1/128`; `127.0.0.53` and `127.0.0.54` are not
assigned to anything — they are merely reachable because 127/8 routes to `lo`,
which is why resolved can bind them at all. The decisive experiment on `nrm`
(2026-09-10): stop `systemd-resolved` so `.53` is completely free, restart
dnsmasq, and look at what it takes.

```
[1] resolved stopped        → binders of 127.0.0.53: 0
[2] dnsmasq restarted       → binds 127.0.0.1, ::1, and the three tailscale0
                              addresses; 127.0.0.53 NOT taken
[3] resolved started again  → binds 127.0.0.53 without conflict, active
[4] health.ayc @127.0.0.1   → the tailnet address; 0 failed units
```

So the two resolvers never contend for the socket, and the proposed fix —
replacing `interface=lo` with `listen-address=127.0.0.1` — would have changed a
live DNS binding (and silently dropped `[::1]:53`) to buy nothing. It is
withdrawn. This is exactly the class of change `optimization-review.md` §7
protects `bind-dynamic` from.

**What remains true, and what was fixed instead.** The installer still writes a
setting that this release accepts and ignores, and still reported success for
it. That is a real defect even when harmless: a configuration claim that is not
true. v2-77 therefore reads the achieved state back and says which way it went
(**DD-109**), rather than changing any binding:

```
resolved stub'ı 127.0.0.53'te ayakta — DNSStubListener=no bu sürümde
yok sayılıyor; bu yerleşimde zararsız (DD-109)
```

The drop-in itself stays. Removing it would change behaviour on any host where
the key still works — and there is currently no such host to verify against,
since Debian keeps resolved inactive and Ubuntu 26.04 ignores the key. Writing
a setting whose effect is then measured and reported is the honest position
until one exists.

### A3 — the installer's `sysctl.d` files do not sort last

```
$ ls /etc/sysctl.d/
50-IPv6.conf  99-cloudimg-ipv6.conf  99-master-stack-netbuf.conf
99-master-tailscale.conf  99-nc-kernel.conf  README.sysctl
```

`sysctl --system` and `systemd-sysctl` apply files in lexicographic order and
the last assignment wins. `99-nc-kernel.conf` — the netcup image's file — sorts
**after** both master-stack files.

On this host it is harmless, because the provider sets the same two keys the
installer's floor cares about, and higher:

```
99-nc-kernel.conf:  net.core.rmem_max = 67108864
                    net.core.wmem_max = 67108864
99-master-stack-netbuf.conf: net.core.rmem_max = 67108864   # max() preserved it
```

This is **DD-18's `max(current, floor)` working exactly as designed** — verified,
and a point in the design's favour.

But the same ordering applies to `99-master-tailscale.conf`, which carries
`net.ipv4.ip_forward = 1` and `net.ipv6.conf.all.forwarding = 1`. On a host or
image whose provider file sorts later and sets `ip_forward = 0`, the installer
would apply forwarding at install time (`sysctl -p`, immediate) and **lose it at
the next reboot** — an exit node that silently stops forwarding after a reboot,
with every unit green. Nothing in the tree asserts the runtime value after boot.

**Fix:** rename both files so master-stack sorts last — e.g.
`99-zz-master-stack-netbuf.conf`, `99-zz-master-tailscale.conf` — and remove the
old names on upgrade. Two `atomic_write` targets and one `rm -f`. Alternatively
(or additionally) assert `net.ipv4.ip_forward=1` in stage 7, which costs one
line and catches the class rather than the instance.

### B1 — `state.env` carries no OS identity

`write_state` records the version, WAN, Tailscale, domain, ports and chain
names. It records nothing about the operating system it ran on.

Consequences:

- **In-place release upgrade is invisible.** `do-release-upgrade` from noble to
  resolute rewrites `os-release`; the next installer run rewrites the apt repo
  lines (so `V2_LAST_ATOMIC_CHANGED=1` correctly triggers `apt-get update`), but
  nothing else re-evaluates. The kernel-module set, the resolved handling and
  the firewall are all left to their probes, which happen to be correct today —
  by luck, not by design.
- **No support record.** After the fact there is no way to tell from the host
  which OS a given `V2_VERSION` was installed against. This review had to read
  `os-release` live.
- **The backup tooling has no source-OS field.** `SESSION.md` (2026-09-06)
  deliberately removed the OS gate from settings transfer — correct — but
  *recording* the source OS in the snapshot costs nothing and makes a failed
  restore diagnosable.

**Fix:** add `OS_ID`, `OS_CODENAME`, `OS_VERSION_ID`, `OS_ARCH` and
`KERNEL_RELEASE` to `write_state`, and in `stage_0` compare the live values
against the recorded ones. On mismatch: log a prominent INFO/WARN naming both
sides and set `OS_CHANGED=1`, which forces the OS-conditional work to re-run
(repo rewrite + `apt-get update`, `ensure_wg_kernel_modules`, the resolved and
resolv.conf blocks, `FIREWALL_NEEDS_RESTART=1`). This is five extra state lines
and one comparison — it is *verification*, not a reconcile engine, and it stays
inside the existing linear stages.

### C2 — no `iptables` backend assertion

`nrm` is consistent:

```
$ iptables --version            → iptables v1.8.11 (nf_tables)
$ update-alternatives --query iptables
Status: auto
Value:  /usr/sbin/iptables-nft
```

`scripts/firewall.sh` calls the `iptables`/`ip6tables` wrappers and Docker picks
its backend independently. If an operator (or a differently-provisioned Debian
host) has the alternatives set to `iptables-legacy`, the two write into
different rule sets: `DOCKER-USER` never appears in the table the script reads,
and `wait_for_docker_user` dies after 10 s with
`DOCKER-USER yok; Docker çalışıyor ama zincir yok` — a message that describes the
symptom and hides the cause.

**Fix:** in `stage_0`, assert that `iptables --version` reports `nf_tables` and
die with the actual remedy (`update-alternatives --set iptables
/usr/sbin/iptables-nft`) when it does not. Two lines, fail-closed, consistent
with the ufw gate.

### C1 — rendered configs are never validated before activation

`docs/architecture.md` §"Debian target only" is accurate: `dnsmasq --test`,
`caddy validate`, `docker compose config` and `systemd-analyze verify` are never
run. All the binaries are present on the target — verified on `nrm`:
`/usr/sbin/dnsmasq`, `/usr/bin/caddy`, `docker compose 5.5.1`.

Today a bad render is caught late: `systemctl restart dnsmasq` fails under
`set -e`, or Caddy burns its `StartLimitBurst=3` and fails visibly (**DD-72**).
Both work; both report "restart failed" rather than "line 12: unknown
directive". The realistic trigger for this is exactly what this review is about
— a dnsmasq or Caddy version bump between OS releases dropping a directive.

**Fix (low priority, real value):** after each `render_template` and before the
restart, run the matching validator on the rendered file and `die` with its
output. `dnsmasq --test -C "$DNSMASQ_CONF_FILE"`, `caddy validate --config
"$CADDYFILE" --adapter caddyfile`. Three lines; turns a class of OS-drift
failures into a precise error.

---

## 5. Lower-priority OS-detection hardening

| # | Item | Note |
|---|---|---|
| B2 | `require_supported_os` requires `VERSION_CODENAME` | Present on all three supported releases; a `UBUNTU_CODENAME` fallback costs two lines and covers derivative images. Rejecting them is also a valid decision — but it should be a decision, and the current death message does not distinguish "unsupported" from "missing key" |
| B3 | `line` is not declared `local` in `require_supported_os` | Leaks a global into the caller. `common.sh:45`. Cosmetic; one word |
| B4 | No repo-suite preflight | A codename not yet published by Docker or Tailscale surfaces as `apt-get update` failing 3× over up to 300 s each. One `curl -fsI …/dists/$OS_CODENAME/Release` per repo, before the `.list` is written, turns that into "vendor has not published `<codename>` yet" |
| B5 | No architecture check | `nrm` is amd64. All six images are multi-arch and both apt vendors publish arm64, so arm64 would probably work — untested. Record `OS_ARCH` in `state.env` (B1) and warn outside `amd64`/`arm64` |
| B6 | `TIMEZONE` is applied unconditionally on every run | `defaults.env` hardcodes `Europe/Berlin` and `stage_1` calls `timedatectl set-timezone` each run, silently overriding an operator's host setting. It belongs with the other `config.env` prompts, or should at least be skipped when it already matches |

---

## 6. Performance and compatibility (measure before applying)

All values below are live readings from `nrm`, idle.

### D1 — BBR + `fq` are available and unused

**Measured and adopted on 2026-09-11 (v2-79, DD-111).** The test was an
interleaved A/B over the direct tailnet path, with each run's congestion
control confirmed on the live socket. Peak throughput was the same, about 440
Mbit/s. Cubic lost roughly 20% on three of six runs after bursts of about 2,000
retransmissions; BBR lost none of its three. **Correction to the paragraph
below:** BBR does not help "an exit node relaying other devices' TCP". The
endpoints of a TCP connection run its congestion control, and a forwarding
router never runs it for flows it only passes through. It helps only TCP that
terminates on this host: WebDAV to Infuse, qBittorrent uploads and the web UIs.

```
net.ipv4.tcp_available_congestion_control = reno cubic
net.ipv4.tcp_congestion_control           = cubic
net.core.default_qdisc                    = fq_codel
/lib/modules/7.0.0-31-generic/kernel/net/ipv4/tcp_bbr.ko.zst   present, not loaded
```

This is the single highest-value kernel change available to this host profile:
an exit node relaying other devices' TCP, plus WebDAV video streaming to Infuse,
plus torrent traffic, over a `tailscale0` path with MTU 1280. `tcp_bbr` ships as
a module on both Debian 13 and Ubuntu 24.04/26.04, so it is OS-agnostic — one
`modules-load.d` entry plus two sysctls, in the same shape as the existing
`ensure_wg_kernel_modules` and `apply_udp_netbuf_floor` helpers.

**It must not be applied on the strength of general reputation.** This repo's
culture is measurement-first, and BBR's advantage over CUBIC is
path-dependent. Proposed measurement, before and after, on the real paths:
a sustained WebDAV read through Caddy from a tailnet client, and an
exit-node throughput sample. If the difference is inside the noise, the correct
outcome is a `DD-*` entry recording that it was measured and rejected.

Note that `default_qdisc` only affects interfaces brought up afterwards, and
that `fq` (not `fq_codel`) is what BBR's pacing expects.

### D2 — Docker container logs are unbounded

```
LoggingDriver: json-file      /etc/docker/daemon.json: { "dns": [...] }  only
/var/lib/docker/containers: 360K
```

360 K today, no rotation configured, `restart: unless-stopped` on six
containers, one of which is a torrent client. `merge_docker_daemon_dns` already
establishes the safe pattern (**DD-8**: merge one key with `jq`, preserve the
rest); adding `log-opts` is the same three lines.

Caveat worth recording in the DD entry: `log-opts` in `daemon.json` applies to
containers **created after** the change. The six existing containers keep
`max-size: unset` until they are recreated, so the fix does not become effective
on a provisioned host until the next compose recreation.

### D3 — `tcp_mtu_probing` is off

`net.ipv4.tcp_mtu_probing = 0`. With `tailscale0` at MTU 1280 and an exit-node
path that crosses networks the host does not control, `= 1` (enable on ICMP
black-hole detection) is a cheap robustness win with no measured downside. Group
it with D1 if D1 is taken; not worth its own change otherwise.

### D4 — conntrack: no change

```
net.netfilter.nf_conntrack_max     = 262144
net.netfilter.nf_conntrack_buckets = 262144      (1:1 — good)
net.netfilter.nf_conntrack_count   = 10          (idle)
net.netfilter.nf_conntrack_tcp_timeout_established = 432000
```

The table is correctly sized for 8 GB and the bucket ratio is right. The
5-day established timeout is the kernel default and is the only value a busy
torrent box might want lower — but `count = 10` at idle is not evidence of
pressure. **Recommendation: no change.** Re-measure `nf_conntrack_count` during
a real torrent session before touching anything.

### D5 — UDP socket buffers: no change, and a validated design

`apply_udp_netbuf_floor`'s `max(current, 16 MiB)` preserved the provider's
64 MiB. This is the one place where the tree already does the right thing about
an environment it does not control. See A3 for the boot-ordering caveat.

### D6 — minor re-run cost

`install_tailscale_repo` and `install_docker_repo` fetch their keyrings on
**every** run (`curl` + `install -m 0644`), unconditionally, before the `.list`
comparison that decides whether `apt-get update` is needed. Two HTTPS round
trips per run that almost always write identical bytes. Guarding each with
`[[ -s <keyring> ]] ||` (or routing through `atomic_write`) removes them.
Marginal, but it is in the same family as the `apt-get update` skip already
taken in v2-70.

### Not recommended

| Item | Why not |
|---|---|
| `userland-proxy: false` | Already rejected in `optimization-review.md` §10 — the WAN path is DNAT, not the proxy |
| `live-restore: true` | Interacts with `master-firewall`'s `PartOf=docker.service` and the `ExecStartPost` drop-in; would need a full restart-behaviour re-verification for a benefit this host has never needed |
| `nf_conntrack` tuning | No measured pressure (D4) |
| Distro switch statement replacing the probes | The probes are more robust than identity and already absorb the differences; identity should be *recorded*, not *branched on* |
| A general OS-abstraction layer / plugin per distro | Contract §2 and `CLAUDE.md` both refuse this shape. Two families, five OS-conditional facts — a switch that big would be larger than what it abstracts |

---

## 7. Cost / benefit

| # | Proposal | Benefit | Complexity | Risk | Change | Verdict |
|---|---|---|---|---|---|---|
| A2 | `NEEDRESTART_SUSPEND=1` | Installer owns every restart again | Very low | Very low | `install.sh` +1 line | **APPLY** |
| C2 | iptables backend assertion | Confusing failure becomes a named cause | Very low | None | `install.sh` +2 lines | **APPLY** |
| B3 | `local line` | Removes a global leak | Trivial | None | `common.sh` 1 word | **APPLY** |
| B1 | OS identity in `state.env` + change detection | Release upgrades stop being invisible; support record | Low | Low | `install.sh` ~10 lines, `common.sh` +3 | **APPLY** |
| A3 | `99-zz-` sysctl prefix (+ `ip_forward` assertion in stage 7) | Forwarding and netbuf floor survive a hostile boot order | Low | Low | 2 renames + 1 `rm -f` + 1 assertion | **APPLY** |
| A1 | dnsmasq `listen-address=127.0.0.1` (option 2) | ~~Removes a bind race~~ — the race was disproved by experiment (§4); buys nothing and drops `[::1]:53` | Low | Medium — changes a binding | template 1 line | **WITHDRAWN** |
| A1 | Read the stub state back and report it (option 1) | A setting that silently does nothing becomes a stated fact | Very low | None — no binding changes | `install.sh` +1 helper | **APPLIED (v2-77, DD-109)** |
| C1 | `dnsmasq --test` / `caddy validate` on the render | OS/package drift fails with a precise message | Low | Low | `install.sh` +3 lines | **APPLY** |
| B4 | Repo-suite preflight | 15-minute timeout becomes a one-line explanation | Low | Low | `install.sh` +4 lines | **APPLY** opportunistically |
| D2 | Docker `log-opts` | Removes an unbounded disk consumer | Very low | Low | `install.sh` +3 lines | **APPLY** |
| D1 | BBR + `fq` (+ D3) | Potentially the largest throughput gain available | Low | Medium | modules-load + 2 sysctls | **APPLIED (v2-79, DD-111)** — measured first |
| B2 | `UBUNTU_CODENAME` fallback | Derivative images | Very low | Low | `common.sh` +2 lines | **DECIDE** — rejecting them is also valid |
| B6 | Timezone from `config.env` | Stops overriding the operator each run | Low | Low | prompt + `config.env` key | **DECIDE** |
| B5 | Architecture record/warning | arm64 is untested, not unsupported | Very low | None | folded into B1 | **APPLY** with B1 |
| D4, D5 | conntrack, netbuf | — | — | — | — | **NO CHANGE** |

---

## 8. Plan

```
1. A2 + C2 + B3                one-line gates and the needrestart suspend
2. B1 (+ B5)                   OS identity in state.env; OS_CHANGED forces the
                               OS-conditional blocks to re-run
3. A3 + stage-7 ip_forward     sysctl files sort last; runtime value asserted
4. C1 + B4                     validate the render; preflight the repo suite
5. D2                          docker log rotation (jq merge, DD-8 pattern)
6. A1                          (superseded — see §4; done as DD-109 in v2-77)
   [withdrawn]                 dnsmasq listen-address — needs a live DNS
                               re-verification on Ubuntu 26.04 AND Debian 13
7. D1 (+ D3)                   measure BBR/fq on a WebDAV stream and an
                               exit-node sample; apply or record the rejection
8. End-to-end on nrm           fresh-equivalent re-run, reboot, tailscaled
                               restart, docker restart, all stage-7 assertions
```

Steps 1–5 are roughly twenty-five lines across `install.sh` and `common.sh`,
with no new file, no new unit and no new timer. Steps 6 and 7 each need live
verification on both OS families before they can be called done. Every step
needs a `V2_VERSION` bump, a `CHANGELOG.md` entry under `[Unreleased]`, and
steps 2, 3, 6 and 7 need `DD-*` entries.

---

## 8.1 Status after implementation — `2026.08.06-v2-74` (2026-09-08)

Plan steps 1–5 were implemented the same day. Steps 6 and 7 are deliberately
not taken: both change a runtime binding or a kernel default and need
before/after measurement on both OS families first.

| Item | Change | Recorded |
|---|---|---|
| A2 | `NEEDRESTART_SUSPEND=1` exported beside `DEBIAN_FRONTEND` in `stage_1` | DD-103 |
| B1, B5 | `OS_ID`/`OS_CODENAME`/`OS_VERSION_ID`/`OS_ARCH`/`KERNEL_RELEASE` in `state.env`; `detect_os_change` sets `OS_CHANGED`, which forces the apt refresh, the resolved restart, one dnsmasq/Caddy restart and a firewall restart; arch warning | DD-104 |
| B3 | `line` declared `local` in `require_supported_os` | DD-104 |
| A3 | Drop-ins renamed `99-zz-master-*`, old names deleted; stage 7 asserts live `ip_forward` and warns on a below-floor `rmem_max` | DD-105 |
| C2 | `require_nft_iptables` gate in stage 0, with the `update-alternatives` remedy in the message | DD-106 |
| B4 | `assert_repo_suite` probes `dists/<codename>/Release` for both vendors, 3 attempts | DD-106 |
| C1 | `dnsmasq --test -C`, `caddy validate` (with the real `TAILSCALE_IPV4`/`WEBDAV_PORT`) and `docker compose config -q` run on the target before the consuming unit restarts | DD-106 |
| D2 | `merge_docker_daemon_dns` → `merge_docker_daemon_config`; `log-opts` merged only for the `json-file` driver | DD-107 |
| A1 | **Done in v2-77**, but not as planned: the binding change was withdrawn after the race it targeted was disproved by experiment, and the achieved stub state is read back and reported instead | DD-109 |
| D1 | **Done in v2-79** after an interleaved A/B: peak identical, cubic's loss-driven dips removed. Module verified on both kernels (Ubuntu 7.0, Debian 6.12) | DD-111 |
| D3 | **Not taken.** `tcp_mtu_probing` — no measured PMTU problem | — |
| B2, B6 | **Not taken.** `UBUNTU_CODENAME` fallback and operator-owned timezone are open decisions, not defects | — |

Verification performed for v2-74:

- Workstation: `bash -n` clean, `shellcheck -x -s bash` clean, `bats tests`
  **86 passed / 3 skipped** (no workstation `timeout`), including five new
  cases covering the OS record, the restart-manager suspend, the sysctl
  ordering and runtime assertion, and the three fail-early gates.
- `detect_os_change` exercised in isolation across four state files: no record
  (no change claimed), identical OS, noble→resolute, and debian→ubuntu. Only
  the last two set `OS_CHANGED=1` and `FIREWALL_NEEDS_RESTART=1`.
- `assert_repo_suite` passes against the real Docker suite and dies in ~6 s
  with the named cause against a nonexistent codename. All six current
  vendor/codename combinations return HTTP 200.
- `merge_docker_daemon_config`'s jq expression checked against four inputs:
  empty, a document with unrelated keys (`live-restore` preserved), a
  non-`json-file` driver (its `log-opts` untouched), and existing
  `json-file` `log-opts` (`compress` preserved, the two keys added).
- On `nrm`, read-only: both validators accept the live `dnsmasq` and `Caddy`
  configs in the exact code shape used by `install.sh`, and reject seeded
  errors with a line number and the offending directive. `require_nft_iptables`
  and both stage-7 sysctl assertions pass against the live host.

**Live acceptance on `nrm` (Ubuntu 26.04.1, 2026-09-08).** Four default
re-runs (all prompts left at their defaults: `ayc`, `/downloads`, 61001,
61003, no full-upgrade, no image pull) plus a cold reboot, all exiting 0:

| Run | What it proves | Result |
|---|---|---|
| 1 — first v2-74 run | Upgrade path from v2-73 | `OS kaydı yok` logged (no false release change); both legacy `99-master-*` files deleted and rewritten as `99-zz-*`; `state.env` gained the five `OS_*`/`KERNEL_*` lines; `daemon.json` gained `log-opts` with `dns` preserved; firewall restarted because `state.env` changed. **6/6 container IDs and start times bit-identical to the pre-run capture.** |
| 2 — immediate re-run | Idempotency | Full no-op: both apt updates skipped, firewall, dnsmasq and Caddy all reported *yapılandırması aynı; yeniden başlatılmadı*, compose up skipped. ~10 s. |
| 3 — seeded `OS_CODENAME=noble`, `OS_VERSION_ID=24.04` | **DD-104**'s forced re-application | Logged `işletim sistemi değişmiş: ubuntu/noble/24.04 → ubuntu/resolute/26.04`; every "atlandı / yeniden başlatılmadı" skip message was **absent**, i.e. both apt updates, the firewall, dnsmasq and Caddy were all re-applied. `state.env` self-corrected to `resolute`/`26.04`. |
| 4 — after the reboot | Steady state | No-op again; container start times unchanged from boot. |

Cold reboot — the real test for **DD-105**, since the rename only matters
across a boot:

```
/etc/sysctl.d/  →  50-IPv6.conf  99-cloudimg-ipv6.conf  99-nc-kernel.conf
                   99-zz-master-stack-netbuf.conf  99-zz-master-tailscale.conf
net.ipv4.ip_forward = 1      net.ipv6.conf.all.forwarding = 1
net.core.rmem_max   = 67108864      (provider's 64 MiB preserved)
```

Also verified after the reboot: 0 failed units; 6/6 containers healthy;
`master-firewall --check` passes; all five wg-easy netfilter modules loaded;
`health.ayc` resolves to the tailnet IP from both `127.0.0.1` and the
Tailscale address, with an out-of-domain query `REFUSED`; Caddy health `ok`;
WebDAV `401` on both the Caddy vhost and the direct `TS-IP:61003` Infuse path;
`BackendState=Running`, `Online=true`, `ExitNodeOption=true`.

Two Ubuntu-specific behaviours were observed in passing during run 1 and are
consistent with the design: apt reported *Waiting for cache lock … held by
process 266758 (apt-get)* and waited it out under `DPkg::Lock::Timeout`
(**DD-102**), and `dnsutils` resolved to `bind9-dnsutils` without incident.

### Debian 13 acceptance — and what it caught (`v2-75`, 2026-09-08)

The argument that every v2-74 change was "OS-agnostic or a no-op on Debian by
construction" was wrong, and the measurement found it immediately.

**A minimal Debian 13 image ships no `iptables` at all** — no binary, no dpkg
entry, no `/usr/sbin/iptables*`. The package arrives in stage 1's base set.
v2-74's stage-0 backend gate (C2 above) therefore died before the stage that
installs the very binary it inspects, making **fresh Debian installs
impossible**. Ubuntu ships `iptables` preinstalled, which is exactly why the
Ubuntu acceptance could not see it. Fixed in v2-75 as a two-phase check
(**DD-108**), with the general rule recorded: an early gate may only assert
properties of a host as it *arrives*.

Nothing else needed changing. A dry run of stage 1's full package set on
trixie resolved cleanly — `dnsutils` maps to `bind9-dnsutils` with no error,
and every other name exists.

Fresh install on a bare trixie host, then the same sequence Ubuntu got:

| Run | Result |
|---|---|
| 1 — fresh install | Stage 0 logged the deferred backend check, then stages 0–7 in **90 s**, exit 0. `state.env`: `debian`/`trixie`/`13`/`amd64`, kernel `6.12.107+deb13-amd64`. |
| 2 — re-run | Full no-op in 7 s; 6/6 container IDs and start times bit-identical. |
| reboot | `99-zz-master-*` sorts after the provider's `99-nc-kernel.conf`; `ip_forward=1`, IPv6 forwarding `1`, `rmem_max` 64 MiB preserved. |
| 3 — post-reboot re-run | No-op again, exit 0. |
| 4 — seeded `ubuntu/noble/24.04` | Logged `işletim sistemi değişmiş: ubuntu/noble/24.04 → debian/trixie/13`, re-applied every OS-dependent step, and self-corrected `state.env`. |

The Debian-specific paths all behaved as the probe design predicts, and each
was confirmed rather than assumed:

| Probe | Debian reality | Outcome |
|---|---|---|
| `systemd-resolved` | **inactive** | Whole resolved block skipped; `/etc/systemd/resolved.conf.d/` never created — so A1's Ubuntu-only stub problem simply does not exist here |
| `/etc/resolv.conf` | regular file, later owned by Tailscale | No stub symlink to repoint |
| `needrestart` | **not installed** | `NEEDRESTART_SUSPEND=1` is the intended no-op (**DD-103**) |
| `ufw` | **not installed** | Gate no-ops |
| `debian-keyring` | installed | The one genuine `OS_ID=debian` branch (**DD-102**) |
| `unattended-upgrades` | not installed | No dpkg-lock contention; `DPkg::Lock::Timeout` harmless |

Post-reboot: 0 failed units, 6/6 containers healthy, `master-firewall --check`
passes, all five wg modules loaded, `health.ayc` resolves from both
`127.0.0.1` and the tailnet address with out-of-domain `REFUSED`, Caddy health
`ok`, WebDAV `401` on both paths, `BackendState=Running`, `Online=true`,
`ExitNodeOption=true`, and `daemon.json` carries the rotation keys.

**Both supported distributions have now had the same acceptance.** systemd
differs across them (257 on trixie, 259 on resolute) and so does the kernel
(6.12 vs 7.0), which is what makes the probe-over-identity design worth
keeping.

### Ubuntu 26.04 acceptance at v2-76 — both sides of every probe (2026-09-10)

`nrm` was reinstalled as Ubuntu 26.04.1 (resolute, systemd 259, kernel
7.0.0-31) and v2-76 was accepted there from bare metal. This closes the gap
left open at v2-75: **every supported distribution has now run the current
version**, and — more usefully — each capability probe has been measured on
*both* of its branches, the acting one and the skipping one.

| Run | Result |
|---|---|
| 1 — fresh install | Stages 0–7 in **95 s**, exit 0. `state.env`: `ubuntu`/`resolute`/`26.04`/`amd64`, kernel `7.0.0-31-generic` |
| 2 — re-run | Full no-op in 11 s; 6/6 container ids and start times bit-identical |
| 3 — seeded `debian/trixie/13` | Logged the release change, re-applied every OS-dependent step, self-corrected `state.env` |
| reboot | `99-zz-master-*` sorts after `99-nc-kernel.conf`; `ip_forward=1`, IPv6 forwarding `1`, `rmem_max` 64 MiB |
| 4 — post-reboot re-run | No-op again; container start times unchanged from boot |

**Each divergence, now measured on both branches:**

| Slug | Debian branch (v2-75) | Ubuntu branch (v2-76) |
|---|---|---|
| `caddy-keyring-pkg` | `debian-keyring` installed | **not** installed — the one real branch, correct on both sides |
| `ufw-gate` | package absent → no-op | package present, inactive → no-op |
| `netfilter-binaries` | absent → check deferred to stage 1 | present → verified at stage 0, both families `nf_tables` |
| `needrestart-suspend` | package absent → variable unread | package present → **measured, see below** |
| `resolved-stub` | resolved inactive → block skipped, no drop-in created | resolved active → drop-in written |
| `resolvconf-symlink` | no stub symlink → no-op | stub symlink → repointed |
| `tailscale-repo-suite` / `docker-repo-suite` | `…/debian trixie` | `…/ubuntu resolute` |

**`needrestart-suspend` (DD-103) measured rather than assumed.** The install
ran 23:08:45–23:10:20 with `needrestart 3.11` installed and hooked into apt.
Zero needrestart records in the boot journal, and the service start times
account for every restart:

```
ssh          23:05:06   ← boot; never restarted during the install
tailscaled   23:08:58   ← stage 2, the installer's own enable --now
containerd   23:09:42   ← stage 4
docker       23:09:43   ← stage 4
dnsmasq      23:10:01   ← stage 6
caddy        23:10:02   ← stage 6
```

`sshd` surviving a first-install `full-upgrade` untouched is the direct
evidence: without the suspend this is the daemon needrestart would restart.

**A1 is confirmed as a standing Ubuntu 26.04 defect, not an upgrade artifact.**
It was first seen on a host upgraded v73→v74. On this *fresh* v76 install the
drop-in is written correctly and `127.0.0.53` is still bound and answering, and
it is still bound after the reboot. So the finding does not depend on install
history — systemd 259 accepts `DNSStubListener=no` and ignores it. Still
benign here (dnsmasq holds `127.0.0.1`, resolved holds `127.0.0.53`), still a
latent start-order bind race, still deliberately unfixed pending the
measurement the fix needs on both families.

**DD-102's resolv.conf prediction confirmed end to end.** At install the
`stub-resolv.conf` symlink was repointed to resolved's uplink; after the reboot
Tailscale had replaced it with its own regular file, and host DNS stayed
healthy throughout. On the post-reboot re-run the divergence correctly went
quiet — `readlink` no longer matches the stub, so the repoint is a no-op. The
bootstrap-not-ownership framing in DD-102 is exactly what the host does.

## 9. Do not change

| Area | Why it stays |
|---|---|
| **Probe-over-identity for OS differences** | ufw, resolved, resolv.conf and the dpkg lock are all handled by asking the host, not the label. Verified correct on resolute; the only thing missing is verification of the result |
| **`require_supported_os`'s hard three-release matrix** | **DD-102**'s reasoning holds: behaviour is only known on releases the installer was written against. Do not loosen it to `ID=ubuntu` |
| **Repo suites derived from `os-release`** | Verified live: `docker-ce 5:29.8.0-1~ubuntu.26.04~resolute` and `tailscale 1.102.3` both installed from codename-derived lines |
| **`max(current, floor)` netbuf logic (DD-18)** | Proved itself against a provider file that sets 4× the floor |
| **Unconditional legacy-netfilter `modprobe` (DD-10)** | A problem found on one OS, fixed for all of them. Correct instinct; do not turn it into an `OS_ID` branch |
| **dnsmasq `bind-dynamic`** | Unchanged from `optimization-review.md` §7 — and now with a measured reason: it binds only the addresses *assigned* to `lo` and `tailscale0`, so it never contends with resolved's `127.0.0.53`. The A1 proposal to narrow it was withdrawn |
| **Everything in `optimization-review.md` §7** | Staging-chain swap, third-party `DOCKER-USER` preservation, Compose decoupled from `tailscaled`, `--check`'s narrow scope, 1:1 publish style, MTU 1280 |
| **No reconcile engine** | B1's `OS_CHANGED` flag forces a re-run of steps that already exist. It must not grow into state comparison for anything else |

---

## 10. Verdicts

As reviewed, at `2026.08.06-v2-73` on Ubuntu 26.04.1:

```
OS DETECTION:            CORRECT
OS-CONDITIONAL APPLY:    CORRECT
OS-CONDITIONAL VERIFY:   ADDRESSED        (A1 v2-77; A3, C1, C2 v2-74)
OS IDENTITY RECORD:      MISSING          (B1)
THIRD-PARTY OWNERSHIP:   NEEDS CHANGES    (A2 — needrestart)
PERFORMANCE HEADROOM:    UNMEASURED       (D1)
RUNNING SYSTEM HEALTH:   GREEN            (6/6 containers, 0 failed units,
                                           DNS/Caddy/WebDAV paths verified)

OVERALL:                 SMALL CHANGES RECOMMENDED
```

The system on `nrm` is healthy and the design is sound. Nothing in this review
argues for growing the architecture; every item is either a one-line gate, a
recorded fact, or a verification of a step the installer already performs.
