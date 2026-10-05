"""Execute the real INPUT rule builder/checker without touching host firewall state."""
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "scripts/firewall.sh"


class ContainerDnsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.rules = Path(self.tmp.name) / "rules"
        self.rules.write_text("")

    def shell(self, extra="", prefix=None):
        source = SOURCE.read_text()
        names = ("container_dns_iface", "apply_input4", "check_input_chain", "check_rule",
                 "check_rule_count", "check_before", "check_chain_shape", "check_wan_allow_count", "wan_allow_pairs")
        functions = []
        for name in names:
            match = re.search(r"(?ms)^" + name + r"\(\) \{\n.*?^\}", source)
            if match:
                functions.append(match.group())
        harness = r'''
set -Eeuo pipefail
die() { printf '%s\n' "$*" >&2; exit 1; }
create_staging() { printf '%s\n' MASTER; }
activate_named() { :; }
check_jump_exactly_one() { :; }
check_no_staging_artifacts() { :; }
check_ts_input_precedence() { :; }
iptables() {
    shift 2
    case "$1" in
        -A) printf '%s\n' "$*" | sed 's/ESTABLISHED,RELATED/RELATED,ESTABLISHED/' >>"$RULES" ;;
        -S) cat "$RULES" ;;
        -C) shift; local wanted; wanted="$(printf '%s\n' "-A $*" | sed 's/ESTABLISHED,RELATED/RELATED,ESTABLISHED/')"; grep -Fxq -- "$wanted" "$RULES" ;;
        *) die "unexpected iptables argument: $*" ;;
    esac
}
TAILSCALE_IF=tailscale0 CHAIN_INPUT=MASTER CHAIN_STAGING_PREFIX=TEST
WAN_INTERFACE=eth0 SSH_PUBLIC_PORT=22 TAILSCALE_UDP_PORT=41641 SHARE_WAN_ACTIVE=0
VPN_IFACES=(wg0) VPN_PORTS=(51820)
ICMP6_TYPES=()
'''
        env = dict(os.environ, RULES=str(self.rules))
        env.pop("KONTEYNER_BRIDGE_PREFIX", None)
        if prefix is not None:
            env["KONTEYNER_BRIDGE_PREFIX"] = prefix
        return subprocess.run(["bash", "-c", harness + "\n" + "\n".join(functions) +
                               "\napply_input4\n" + extra], env=env, capture_output=True, text=True, timeout=5)

    def verdict(self, interface, protocol, port, local_on_input=True):
        # Evaluate the NEW packet predicates emitted by the actual shell builder.
        for line in self.rules.read_text().splitlines():
            args = shlex.split(line)
            value = lambda key: args[args.index(key) + 1] if key in args else None
            match_iface = value("-i")
            if match_iface and not (interface.startswith(match_iface[:-1]) if match_iface.endswith("+") else interface == match_iface):
                continue
            if value("--ctstate"):
                continue
            if value("-p") and value("-p") != protocol:
                continue
            if value("--dport") and int(value("--dport")) != port:
                continue
            if value("--dst-type") == "LOCAL" and not local_on_input:
                continue
            if value("-j") in ("ACCEPT", "DROP"):
                return value("-j")
        self.fail("rule builder emitted no terminal decision")

    def test_default_and_custom_owned_bridge_dns_only(self):
        for prefix in (None, "box"):
            with self.subTest(prefix=prefix):
                self.rules.write_text("")
                result = self.shell(prefix=prefix)
                self.assertEqual(result.returncode, 0, result.stderr)
                bridge = (prefix or "ksl") + "1234567890"
                for protocol in ("tcp", "udp"):
                    self.assertEqual(self.verdict(bridge, protocol, 53), "ACCEPT")
                    self.assertEqual(self.verdict(bridge, protocol, 53, local_on_input=False), "DROP")
                    self.assertEqual(self.verdict(bridge, protocol, 22), "DROP")
                    for interface in ("eth0", "wg0", "foreign0"):
                        self.assertEqual(self.verdict(interface, protocol, 53), "DROP")
                dns = [shlex.split(line) for line in self.rules.read_text().splitlines() if "--dport 53 " in line]
                self.assertEqual(len(dns), 2)
                self.assertTrue(all("--limit-iface-in" in rule for rule in dns))

    def test_health_accepts_builder_and_rejects_missing_or_broad_dns_rule(self):
        result = self.shell("check_input_chain iptables v4")
        self.assertEqual(result.returncode, 0, result.stderr)
        for mutation in ("sed '/--dport 53 /{ /-p tcp /d; }'", "sed 's/ -m addrtype --dst-type LOCAL --limit-iface-in//g'"):
            with self.subTest(mutation=mutation):
                self.rules.write_text("")
                result = self.shell(mutation + ' "$RULES" >"$RULES.tmp"\nmv "$RULES.tmp" "$RULES"\ncheck_input_chain iptables v4')
                self.assertNotEqual(result.returncode, 0, "health check accepted altered DNS permissions")

    def test_invalid_prefix_fails_before_any_rule_is_written(self):
        for prefix in ("+", "ksl+", "x", "toolong", "WG", "a b"):
            with self.subTest(prefix=prefix):
                self.rules.write_text("")
                result = self.shell(prefix=prefix)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.rules.read_text(), "")


if __name__ == "__main__":
    unittest.main()
