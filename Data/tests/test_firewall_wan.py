"""Exercise firewall shell functions with helper/iptables fixtures; no host changes."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest


DATA = Path(__file__).resolve().parents[1]
# Load the real definitions, stopping before locks or host policy are applied.
SOURCE, _ = (DATA / "scripts/firewall.sh").read_text().split(
    'if [[ -n "${RUNTIME_DIR:-}" ]]; then', 1)
FIXTURES = r'''
python3() {
    case "$*" in
        *wan-firewall) printf '%s\n' "$WAN_RESULT"; return "${HELPER_RC:-0}" ;;
        *'rules 4 '*) printf '%s\n' "$MANUAL_RULE" ;;
        *'rules 6 '*) return 0 ;;
        *tailnet-ports) printf '4 tcp %s\n4 tcp %s\n6 tcp %s\n' "$SSH_PUBLIC_PORT" "$SHARE_PORT" "$SSH_PUBLIC_PORT" ;;
        *) return 99 ;;
    esac
}
fixture_table() {
    local bin="$1" op args
    shift
    [[ "$1" != -w ]] || shift 2
    op="$1"; shift
    case "$op" in
        -S) printf '%s\n' "$LISTING" ;;
        -L)
            [[ "$HEALTHY" == 1 ]] || return 1
            printf '1 %s\n' "$CHAIN_SETTINGS"
            ;;
        -C)
            [[ "$HEALTHY" != 1 ]] || return 0
            args="$*"
            args="${args//ESTABLISHED,RELATED/RELATED,ESTABLISHED}"
            grep -qxF -- "-A $args" <<<"$LISTING"
            ;;
        *)
            [[ -z "${FAIL_CALL:-}" || "$bin $op $*" != *"$FAIL_CALL"* ]] || return 1
            printf '%s %s %s\n' "$bin" "$op" "$*" >>"$CALLS"
            ;;
    esac
}
iptables() { fixture_table iptables "$@"; }
ip6tables() { fixture_table ip6tables "$@"; }
create_staging() { printf 'fixture\n'; }
activate_named() { :; }
check_jump_exactly_one() { :; }
check_no_staging_artifacts() { :; }
check_ts_input_precedence() { :; }
input_line() { printf '1\n'; }
VPN_IFACES=(wg0) VPN_PORTS=(61001) VPN_NET4=(10.8.0.0/24) VPN_NET6=(fd00:3::/112)
'''


class FirewallWANTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="firewall-wan-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.calls = self.root / "calls"
        self.state = self.root / "state.env"
        self.state.write_text(
            "source " + shlex.quote(str(DATA / "config/defaults.env")) + "\n"
            "WAN_INTERFACE=eth0\nSHARE_HTTPS_PORT=443\n"
            "SETTINGS_FILE=fixture-settings\nSBIN_DIR=fixture-bin\n")
        self.env = dict(os.environ, STATE_FILE=str(self.state), DEFAULTS_FILE="",
                        CALLS=str(self.calls), WAN_RESULT="1 16 64 443", HELPER_RC="0",
                        MANUAL_RULE="", LISTING="", HEALTHY="0", LC_ALL="C")

    def shell(self, body, **env):
        self.calls.write_text("")
        return subprocess.run(["bash", "-c", SOURCE + FIXTURES + body],
                              env=dict(self.env, **env), text=True, capture_output=True, timeout=10)

    def ok(self, body, **env):
        result = self.shell(body, **env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def emitted(self, function, **env):
        self.ok("load_share_wan\n" + function, **env)
        return self.calls.read_text().splitlines()

    def input_listing(self, **env):
        return "\n".join(line.replace("iptables -A fixture", "-A MASTER-INPUT").replace(
            "ESTABLISHED,RELATED", "RELATED,ESTABLISHED")
            for line in self.emitted("apply_input4", **env))

    def test_four_fields_required_and_port_allowlisted_even_when_inactive(self):
        for record in ("1 16 64 443", "1\t16\t64\t61010", "0 16 64 443", "0 16 64 61010"):
            with self.subTest(record=record):
                output = self.ok('load_share_wan\nprintf "%s %s %s %s" "$SHARE_WAN_ACTIVE" '
                                 '"$SHARE_SOCKET_IP" "$SHARE_SOCKET_TOTAL" "$SHARE_WAN_PORT"',
                                 WAN_RESULT=record)
                self.assertEqual(output.split(), record.split())
        invalid = ("", "1 16 64", "0 16 64", "1 16 64 443 extra", "1 16 64 443\n0 16 64 61010",
                   "1 16 64 0", "1 16 64 65536", "1 16 64 -1", "1 16 64 https", "1 16 64 0443",
                   "1 16 64 22", "0 16 64 80", "1 16 64 443;true", "2 16 64 443",
                   "1 0 64 443", "1 16 x 443", "1 65 64 443", "1 16 64 99999999999999999999",
                   "1 16 4294967296 443", "1 18446744073709551632 64 443")
        for record in invalid:
            with self.subTest(record=record):
                result = self.shell("load_share_wan", WAN_RESULT=record)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("WebDAV WAN", result.stderr)
                self.assertEqual(self.calls.read_text(), "")

    def test_legacy_https_and_disabled_wan_allow_projections(self):
        for record, port in (("1 16 64 61010", "61010"), ("1 16 64 443", "443"),
                             ("0 16 64 443", None), ("0 16 64 61010", None)):
            with self.subTest(record=record):
                listing = self.input_listing(WAN_RESULT=record)
                self.assertIn("-i eth0 -p udp --dport 61001 -j ACCEPT", listing)
                self.assertTrue(listing.endswith("-A MASTER-INPUT -j DROP"))
                self.assertLess(listing.index("-i wg0 -j DROP"), listing.index("--ctstate"))
                for candidate in ("443", "61010"):
                    self.assertEqual(f"-i eth0 -p tcp --dport {candidate} -j ACCEPT" in listing,
                                     candidate == port)
                self.ok("load_share_wan\ncheck_input_chain iptables v4", WAN_RESULT=record, LISTING=listing)
                v6 = self.ok("load_share_wan\nwan_allow_pairs v6", WAN_RESULT=record)
                self.assertNotIn("tcp 443", v6)
                self.assertNotIn("tcp 61010", v6)

    def test_https_limits_precede_manual_denies_and_tailnet_remains_internal(self):
        manual = "-i eth0 -p tcp --dport 443 -m comment --comment konsol:deny -j DROP"
        output = self.ok('load_share_wan\nload_settings_rules\nprintf "%s\\n" "$SETTINGS4"',
                         MANUAL_RULE=manual)
        lines = output.splitlines()
        self.assertIn("--dport 443 -m connlimit --connlimit-above 64 --connlimit-mask 0", lines[0])
        self.assertIn("--dport 443 -m connlimit --connlimit-above 16 --connlimit-mask 32", lines[1])
        self.assertEqual(lines[2], manual)
        self.assertIn("-i tailscale0 -p tcp --dport 61010", output)
        self.assertNotIn("-i eth0 -p tcp --dport 61010", output)
        rules = ["-A MASTER-SETTINGS -i wg0 -j DROP", "-A MASTER-SETTINGS -i lo -j RETURN",
                 "-A MASTER-SETTINGS -m conntrack --ctstate RELATED,ESTABLISHED -j RETURN"]
        rules += ["-A MASTER-SETTINGS " + line for line in lines if line]
        body = 'load_share_wan\nload_settings_rules\ncheck_settings_rules iptables "$SETTINGS4"'
        self.ok(body, MANUAL_RULE=manual, LISTING="\n".join(rules))
        rules[3], rules[5] = rules[5], rules[3]
        self.assertNotEqual(self.shell(body, MANUAL_RULE=manual, LISTING="\n".join(rules)).returncode, 0)

    def test_off_removes_limits_and_preserves_tailnet_allowlist(self):
        output = self.ok('load_share_wan\nload_settings_rules\nprintf "%s\\n" "$SETTINGS4"',
                         WAN_RESULT="0 16 64 443")
        self.assertNotIn("connlimit", output)
        self.assertNotIn("--dport 443", output)
        self.assertIn("--dport 61010", output)
        self.assertTrue(output.rstrip().endswith("konsol-base:tail-drop -j DROP"))

    def test_check_rejects_stale_missing_and_misordered_https_rules(self):
        valid = self.input_listing()
        allow = "-A MASTER-INPUT -i eth0 -p tcp --dport 443 -j ACCEPT"
        stale = "-A MASTER-INPUT -i eth0 -p tcp --dport 61010 -j ACCEPT"
        invalid = (valid.replace(allow, stale), valid.replace(allow + "\n", ""),
                   valid + "\n" + stale, valid.replace(allow + "\n", "") + "\n" + allow)
        for listing in invalid:
            with self.subTest(listing=listing):
                result = self.shell("load_share_wan\ncheck_input_chain iptables v4", LISTING=listing)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.calls.read_text(), "")

    def test_invalid_helper_preserves_existing_rules_or_installs_cold_rescue(self):
        for record, rc in (("1 16 64 22", "0"), ("1 16 64", "0"), ("1 16 64 443", "1")):
            for healthy, mode in (("1", "apply"), ("0", "--check"), ("0", "apply")):
                with self.subTest(record=record, healthy=healthy, mode=mode):
                    body = "MODE=" + ("check" if mode == "--check" else mode)
                    result = self.shell(body + "\ntrap startup_failure EXIT\nload_share_wan",
                                        WAN_RESULT=record, HELPER_RC=rc, HEALTHY=healthy)
                    self.assertNotEqual(result.returncode, 0)
                    calls = self.calls.read_text()
                    if healthy == "1" or mode == "--check":
                        self.assertEqual(calls, "")
                    else:
                        for binary in ("iptables", "ip6tables"):
                            self.assertIn(binary + " -I INPUT 1 -j MASTER-NEXT-SAFE", calls)
                            self.assertIn(binary + " -A MASTER-NEXT-SAFE -i wg+ -j DROP", calls)
                            self.assertIn(binary + " -A MASTER-NEXT-SAFE -p tcp --dport 22 -j ACCEPT", calls)
                            self.assertIn(binary + " -A MASTER-NEXT-SAFE -j DROP", calls)
                            self.assertIn(binary + " -I FORWARD 1 -j MASTER-NEXT-SAFE-FW", calls)
                        self.assertNotIn("--dport 443", calls)
                        self.assertNotIn("--dport 61010", calls)

    def test_incomplete_rescue_input_is_not_attached_but_forward_guard_still_is(self):
        # A failed ICMPv6 accept must neither abort the remaining families nor attach a
        # partial INPUT chain (DD-193); the independent FORWARD guard is still installed.
        result = self.shell("MODE=apply\ntrap startup_failure EXIT\nload_share_wan",
                            WAN_RESULT="1 16 64", FAIL_CALL="ip6tables -A MASTER-NEXT-SAFE -p ipv6-icmp --icmpv6-type packet-too-big")
        self.assertNotEqual(result.returncode, 0)
        calls = self.calls.read_text()
        self.assertIn("iptables -I INPUT 1 -j MASTER-NEXT-SAFE", calls)
        self.assertIn("iptables -I FORWARD 1 -j MASTER-NEXT-SAFE-FW", calls)
        self.assertNotIn("ip6tables -I INPUT 1 -j MASTER-NEXT-SAFE", calls)
        self.assertNotIn("ip6tables -A MASTER-NEXT-SAFE -j DROP", calls)
        self.assertIn("ip6tables -I FORWARD 1 -j MASTER-NEXT-SAFE-FW", calls)
        self.assertIn("ip6tables kurtarma girişi kurulamadı", result.stderr)
        self.assertIn("iptables yalnız kurtarma erişiminde", result.stderr)


if __name__ == "__main__":
    unittest.main()
