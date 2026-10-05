#!/usr/bin/env bats

setup() { V2_ROOT="$(cd -- "$BATS_TEST_DIRNAME/.." && pwd)"; }

@test "WAN sharing is a separate loopback on the existing port and boot waits for firewall" {
    grep -qx 'SHARE_WAN_BACKEND="127.0.0.2"' "$V2_ROOT/config/defaults.env"
    grep -qx 'SHARE_WAN_BACKEND=$SHARE_WAN_BACKEND' "$V2_ROOT/install.sh"
    grep -qF -- '--wan-listen=__SHARE_WAN_BACKEND__' "$V2_ROOT/magaza/paylasim/master-paylasim.service"
    grep -qF 'ExecStartPre=+$SBIN_DIR/master-firewall --check' "$V2_ROOT/install.sh"
    grep -qx 'After=master-firewall.service' "$V2_ROOT/install.sh"
}

@test "public Caddy gets bounded header idle time without slowing tailnet transfers" {
    grep -qF 'servers __WAN_IPV4__:__SHARE_PORT__ {' "$V2_ROOT/templates/Caddyfile"
    grep -q 'read_header 10s' "$V2_ROOT/templates/Caddyfile"
    grep -q 'idle 30s' "$V2_ROOT/templates/Caddyfile"
    grep -qF 'header_up X-Share-Client-IP {http.request.remote.host}' "$V2_ROOT/magaza/paylasim/paylasim.caddy"
}

@test "WAN connection admission precedes operator overrides and is conditional" {
    local f="$V2_ROOT/scripts/firewall.sh"
    grep -qF 'load_share_wan' "$f"
    grep -qF '[[ "$SHARE_WAN_ACTIVE" != 1 ]] || printf' "$f"
    grep -qF -- '--connlimit-above $SHARE_SOCKET_TOTAL --connlimit-mask 0' "$f"
    grep -qF -- '--connlimit-above $SHARE_SOCKET_IP --connlimit-mask 32' "$f"
    grep -qF 'SETTINGS4="$core4$line"' "$f"
    grep -qF 'konsol-base:share-total' "$f"
    grep -qF 'konsol-base:share-ip' "$f"
}

@test "installer wires scoped expiry recovery and publishes only after builtins" {
    grep -qx 'OnUnitInactiveSec=30s' "$V2_ROOT/systemd/master-share-network.timer"
    grep -qF 'master_shares.py --state __STATE_FILE__ guard' "$V2_ROOT/systemd/master-share-network.service"
    grep -q 'systemctl enable --now master-share-network.timer' "$V2_ROOT/install.sh"
    local built publish
    built="$(awk '/master-modul" yerlesik/ {print NR}' "$V2_ROOT/install.sh")"
    publish="$(awk '/master_shares.py" publish/ {print NR}' "$V2_ROOT/install.sh")"
    [ "$publish" -gt "$built" ]
}
