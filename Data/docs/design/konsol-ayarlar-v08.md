# Ayarlar management proposal — v08

Date: 2026-09-24. Interactive reference: `konsol-ayarlar-v08.html`.

The operator requested a redesign and then explicitly chose a clickable
prototype first, with four tabs: Güvenlik Duvarı, Caddy, Dnsmasq and
qBittorrent. The operator subsequently approved implementation on 2026-09-24.
The live implementation is v2-126 / DD-156; this HTML remains a frozen,
disconnected reference. The details below describe the prototype, not the
production safety mechanism; see `../contract.md` for the live contract.

## Interaction model

- The existing Konsol visual language is retained. The four tabs replace the
  long read-only page. Caddy stays read-only because editing it was not requested.
- Changes remain drafts until reviewed together. Cancel restores the last
  confirmed sample state. Every screen identifies the prototype as disconnected.
- Firewall changes simulate a 60-second connectivity confirmation. Expiry or
  the explicit rollback button restores the previous sample configuration.
  **This browser timer is a demonstration, not a production safety mechanism.**
- The surrounding conversation may remember the selected tab, IP family,
  traffic scope and row density. It never stores entered passwords or user
  credentials. Password fields are validated and cleared immediately when
  the account change is staged; only a boolean describes the sample change.

## Firewall

Ports and rules are separate views. The port view distinguishes permission
from a listening service and its binding address. An allowed port with no
reachable listener is not described as externally reachable. The list is
not a port scan; unlisted WAN ports fall under the default deny policy.

IPv4/IPv6 and source network are explicit. Rows expose table, chain,
interface, protocol, destination port, source, owner and an example rule.
The rule view includes connection protections, Tailscale-owned chains,
forwarding/isolation and NAT rather than hiding them behind port switches.
Its counters are illustrative, not live measurements. Custom port rules
use structured, validated fields; there is no shell command input.

Implementation prerequisites:

- Persist overrides in one dedicated operator-owned configuration. Installer
  re-runs and module/network lifecycle must consume, not overwrite, it.
- Current `MASTER-INPUT` accepts all traffic on `tailscale0`. A per-port deny
  must precede that broad acceptance (or explicitly replace the policy).
  Appending a rule after it cannot implement a working off switch.
- Derive actual chain order, rules, IPv4/IPv6, listener information and counters
  from the host. Never infer reachability solely from an ACCEPT rule.
- Keep Tailscale-owned chains read-only and protect established connections,
  loopback and essential IPv6 traffic. Full visibility is not permission to
  overwrite another service's chains. The prototype does not implement general
  rule reordering or raw iptables editing.
- Validate and apply atomically under a lock, arm independent **server-side**
  rollback before applying, and require a fresh request over the management
  path to confirm. Recover even if the tab or SSH connection disappears.
- Public exposure is an explicit policy change from the current contract.
  A port switch must not silently change application bind addresses.

## Dnsmasq

Defined names can be enabled/disabled; new exact names target either the
dynamic Tailscale address or a validated fixed IPv4/IPv6 address. Disabling
a name does not stop its service and cannot instantly invalidate client caches.
Adding a DNS name does not create a corresponding Caddy site.

Optional upstream forwarding applies to general names not served locally.
The private `ayc` zone stays local even for missing/disabled records. The
prototype does **not** send private-name queries to public resolvers, duplicate
queries to all providers, or promise encrypted DNS. The listener remains
loopback + Tailscale; no public recursive resolver is opened. The selected
provider is a choice, not a strict primary/fallback ordering guarantee.

Reference: [dnsmasq manual](https://dnsmasq.org/docs/dnsmasq-man.html),
particularly `--local`, `--server`, `--no-resolv` and `--interface`.

Implementation prerequisites: persistent record ownership/overrides, collision
checks against base and module names, provider/IP validation and loop
prevention, `dnsmasq --test`, protected apply/revert, and real DNS tests from
both allowed and disallowed interfaces. Tailscale Admin DNS remains a separate
operator setting; upstream forwarding here does not change that account policy.

## qBittorrent

The account form changes a username and optionally a password; an empty new
password preserves the existing one. The prototype accepts only sample values,
clears the password immediately, and never sends it or stores it as widget state.
The path chooser uses fixed sample directories. Neither it nor any other
prototype interaction reads the real server filesystem.

The chosen download path applies to new torrents only. Existing files and
torrent locations are not migrated. Choosing `/srv/media` is shown as requiring
a scoped systemd write-permission update: the current module only allows the
profile and downloads directory. Real implementation must validate canonical
paths, symlinks, owner/mode, disk space and module state, and keep trash,
share internals and system paths inaccessible. Account changes require a
supported authenticated API or a stopped-service configuration transaction;
never overwrite a live application's file blindly or expose secrets in
argv, logs, URLs or returned settings.

## Verification scope

Browser tests exercise tab navigation, staging/cancel, rule and DNS validation,
provider selection, folder/account editing, confirmation and timed rollback.
Desktop and phone layouts are checked in light/dark mode. These are prototype
tests only; no host firewall, DNS, account or file is changed.
