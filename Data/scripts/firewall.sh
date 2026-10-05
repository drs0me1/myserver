#!/usr/bin/env bash
# Host INPUT + VPN FORWARD/NAT politikası. Staging zincir, atomik swap.
# Üçüncü taraf kurallar silinmez. Docker yoktur (DD-152): DOCKER-USER'a dokunulmaz.
# DD-198: paketler güvenlik duvarına dokunmaz. Kurulu (calisiyor) bir paketin kancası sabit bir
# sözlükte bildirir, kuralları yalnız bu betik yazar ve denetler. Sözlük: "vpn ARAYÜZ UDP_PORT
# AĞ4 AĞ6" — WAN UDP ucu, tailnet izni, internet-only yönlendirme (DD-177) ve NAT. Bozuk ya da
# bilinmeyen bir satır hiçbir kuralı değiştirmez; korumasız açılışta kurtarma erişimi kalır.
set -Eeuo pipefail

STATE_FILE="${STATE_FILE:-/etc/master-stack/state.env}"
DEFAULTS_FILE="${DEFAULTS_FILE:-}"
MODE="${1:-apply}"

die() { printf 'HATA: %s\n' "$*" >&2; exit 1; }

usage() {
    cat <<'EOF'
Kullanım: firewall.sh [apply|--check]
EOF
}

case "$MODE" in
    apply | "") MODE=apply ;;
    --check) MODE=check ;;
    -h | --help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
esac

# shellcheck disable=SC1090
[[ -r "$STATE_FILE" ]] || die "state.env yok: $STATE_FILE"
# shellcheck source=/dev/null
source "$STATE_FILE"
if [[ -n "${DEFAULTS_FILE:-}" && -r "$DEFAULTS_FILE" ]]; then
    # shellcheck source=/dev/null
    source "$DEFAULTS_FILE"
fi

# WAN_INTERFACE state'te yalnız ipucu; belirleyici olan canlı default-route
# (resolve_wan_interface). Diğer değerler state'ten zorunlu (DD-66).
: "${TAILSCALE_IF:?}"
: "${CHAIN_INPUT:?}"
: "${CHAIN_STAGING_PREFIX:?}"
: "${SSH_PUBLIC_PORT:?}"
: "${TAILSCALE_UDP_PORT:?}"
: "${CHAIN_FORWARD:?}"
: "${CHAIN_NAT:?}"
: "${VPN_BLOCK_DEST4:?}"
: "${VPN_BLOCK_DEST6:?}"

# nat tablosu aynı yardımcılarla yönetilir: "$bin" tek kelime olduğu için tablo
# seçimi bu sarmalayıcılardadır.
iptables_nat() { iptables -t nat "$@"; }
ip6tables_nat() { ip6tables -t nat "$@"; }

# DD-175: Kullanıcı zincirinin sonuna ulaşmak zaten çağırana döner; sonda
# koşulsuz RETURN üretilmez. Ara RETURN izinleri/korumaları bunun dışındadır.
ICMP6_TYPES=(destination-unreachable packet-too-big time-exceeded parameter-problem
    echo-request echo-reply router-solicitation router-advertisement
    neighbour-solicitation neighbour-advertisement)

# Kurulu paketlerin bildirimlerinden türeyen VPN ağları: arayüz, UDP portu, alt ağ IPv4/IPv6.
# Önce bildirimler doğrulanır. Bozuk bildirim mevcut korumayı tutar.
VPN_IFACES=() VPN_PORTS=() VPN_NET4=() VPN_NET6=()
SHARE_WAN_ACTIVE=0 SHARE_SOCKET_IP=0 SHARE_SOCKET_TOTAL=0 SHARE_WAN_PORT=0
load_share_wan() {
    local values pattern
    [[ -n "${SHARE_WAN_BACKEND:-}" ]] || return 0
    values="$(python3 "$SBIN_DIR/master_shares.py" --state "$STATE_FILE" wan-firewall)" ||
        die "WebDAV WAN kaydı okunamadı; kurallar değiştirilmedi"
    # Exactly one four-field record; a missing port must never reopen legacy HTTP.
    pattern='^[01][[:blank:]]+[1-9][0-9]{0,9}[[:blank:]]+[1-9][0-9]{0,9}[[:blank:]]+[1-9][0-9]{0,4}$'
    [[ "$values" =~ $pattern ]] || die "WebDAV WAN sınırları veya portu geçersiz"
    read -r SHARE_WAN_ACTIVE SHARE_SOCKET_IP SHARE_SOCKET_TOTAL SHARE_WAN_PORT <<<"$values"
    [[ "$SHARE_WAN_PORT" -le 65535 &&
        ( "$SHARE_WAN_PORT" == "${SHARE_PORT:-}" || "$SHARE_WAN_PORT" == "${SHARE_HTTPS_PORT:-}" ) ]] ||
        die "WebDAV WAN portu geçersiz"
    [[ "$SHARE_SOCKET_IP" -le "$SHARE_SOCKET_TOTAL" && "$SHARE_SOCKET_TOTAL" -le 4294967295 ]] ||
        die "WebDAV WAN sınırları geçersiz"
}
# DD-150/198: yalnız kayıtta "calisiyor" olan paketlerin kancası okunur; kaldırılmış bir paketin
# korunan kaydı (anahtarlarla birlikte) yok sayılır: hiçbir portu ya da kuralı açılmaz.
# Her satır "<id> <sözcük> <alanlar…>" biçiminde toplanır; kanca yalnız işlev tanımlar.
package_declarations() {
    local id state kanca
    [[ -n "${MODULES_FILE:-}" && -f "$MODULES_FILE" && -n "${MODULES_DIR:-}" ]] || return 0
    while IFS=$'\t' read -r id state; do
        [[ "$id" =~ ^[a-z]{2,16}$ && "$state" == calisiyor ]] || continue
        kanca="$MODULES_DIR/$id/kanca"
        [[ -f "$kanca" && ! -L "$kanca" ]] || continue
        # shellcheck source=/dev/null
        ( source "$kanca" && if declare -F paket_firewall >/dev/null; then paket_firewall; fi ) 2>/dev/null |
            sed "s/^/$id /" ||
            die "paket güvenlik duvarı bildirimi okunamadı ($id); hiçbir kural değiştirilmedi"
    done <"$MODULES_FILE"
}
load_package_rules() {
    local id word iface port n4 n6 rest i j
    VPN_IFACES=() VPN_PORTS=() VPN_NET4=() VPN_NET6=()
    while read -r id word iface port n4 n6 rest; do
        [[ -n "$id" ]] || continue
        case "$word" in
            vpn)
                [[ "$iface" =~ ^[a-z][a-z0-9]{1,14}$ && "$port" =~ ^[0-9]{1,5}$ && "$port" -ge 1 && "$port" -le 65535 &&
                    "$n4" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}/[0-9]{1,2}$ && "$n6" =~ ^[0-9a-f:]+/[0-9]{1,3}$ && -z "$rest" ]] ||
                    die "güvenlik duvarı bildirimi bozuk ($id: '$word $iface $port'); hiçbir kural değiştirilmedi"
                VPN_IFACES+=("$iface") VPN_PORTS+=("$port")
                VPN_NET4+=("$n4") VPN_NET6+=("$n6")
                ;;
            *) die "güvenlik duvarı bildiriminde bilinmeyen sözcük ($id: '$word'); hiçbir kural değiştirilmedi" ;;
        esac
    done < <(package_declarations)
    for ((i = 0; i < ${#VPN_IFACES[@]}; i++)); do
        for ((j = i + 1; j < ${#VPN_IFACES[@]}; j++)); do
            [[ "${VPN_IFACES[i]}" != "${VPN_IFACES[j]}" && "${VPN_PORTS[i]}" != "${VPN_PORTS[j]}" ]] ||
                die "güvenlik duvarı bildiriminde tekrar eden arayüz ya da port (${VPN_IFACES[j]}); hiçbir kural değiştirilmedi"
        done
    done
}

input_line() {
    local bin="$1" target="$2"
    "$bin" -w 5 -L INPUT -n --line-numbers |
        awk -v t="$target" '$2 == t { print $1; exit }'
}

insert_pos_after_ts_input() {
    local bin="$1" ts_pos=""
    if "$bin" -w 5 -C INPUT -j ts-input 2>/dev/null; then
        ts_pos="$(input_line "$bin" ts-input)"
        if [[ -n "$ts_pos" ]]; then
            printf '%s\n' "$((ts_pos + 1))"
            return 0
        fi
    fi
    printf '1\n'
}

ensure_jump() {
    local bin="$1" parent="$2" chain="$3" pos=1
    if "$bin" -w 5 -C "$parent" -j "$chain" 2>/dev/null; then
        return 0
    fi
    if [[ "$parent" == "INPUT" ]]; then
        pos="$(insert_pos_after_ts_input "$bin")"
    fi
    "$bin" -w 5 -I "$parent" "$pos" -j "$chain"
}

ensure_ts_input_precedence() {
    local bin="$1" ts_pos="" master_before="" master_after="" _
    if ! "$bin" -w 5 -L ts-input -n >/dev/null 2>&1; then
        return 0
    fi
    if ! "$bin" -w 5 -C INPUT -j ts-input 2>/dev/null; then
        "$bin" -w 5 -I INPUT 1 -j ts-input
    fi

    for _ in $(seq 1 20); do
        ts_pos="$(input_line "$bin" ts-input)"
        [[ -n "$ts_pos" ]] || return 0

        master_before="$("$bin" -w 5 -L INPUT -n --line-numbers |
            awk -v c="$CHAIN_INPUT" -v ts="$ts_pos" \
                '$2 == c && $1+0 < ts+0 { print $1; exit }')"
        master_after="$("$bin" -w 5 -L INPUT -n --line-numbers |
            awk -v c="$CHAIN_INPUT" -v ts="$ts_pos" \
                '$2 == c && $1+0 > ts+0 { print $1; exit }')"

        if [[ -z "$master_before" ]]; then
            if [[ -z "$master_after" ]] &&
                ! "$bin" -w 5 -C INPUT -j "$CHAIN_INPUT" 2>/dev/null; then
                "$bin" -w 5 -I INPUT "$((ts_pos + 1))" -j "$CHAIN_INPUT"
            fi
            while true; do
                ts_pos="$(input_line "$bin" ts-input)"
                master_after="$("$bin" -w 5 -L INPUT -n --line-numbers |
                    awk -v c="$CHAIN_INPUT" -v ts="$ts_pos" \
                        '$2 == c && $1+0 > ts+0 { n++; if (n==2) { print $1; exit } }')"
                [[ -n "$master_after" ]] || break
                "$bin" -w 5 -D INPUT "$master_after"
            done
            return 0
        fi

        if [[ -z "$master_after" ]]; then
            "$bin" -w 5 -I INPUT "$((ts_pos + 1))" -j "$CHAIN_INPUT"
        fi
        master_before="$("$bin" -w 5 -L INPUT -n --line-numbers |
            awk -v c="$CHAIN_INPUT" -v ts="$ts_pos" \
                '$2 == c && $1+0 < ts+0 { print $1; exit }')"
        [[ -n "$master_before" ]] || continue
        "$bin" -w 5 -D INPUT "$master_before"
    done
    die "$bin: ts-input / $CHAIN_INPUT sırası düzeltilemedi"
}

# Yarıda kalan bir apply iki tür artık bırakır: hiç bağlanmamış bir staging
# zinciri, ya da activate_named'in -I ile bağlayıp rename'e yetişemediği
# REFERANSLI bir zincir. İkincisini apply başında silmek yürürlükteki tek
# politikayı yok edebilirdi; bu yüzden temizlik apply'ın SONUNDA yapılır —
# o noktada final zincir parent'a bağlıdır ve kalan her staging artığı ölüdür.
# Referanslıyı atlamak politikayı korurdu ama check_no_staging_artifacts'i
# kalıcı fail bırakır, unit failed kalır ve watchdog sonuçsuz döner (DD-95).
purge_staging_leftovers() {
    local bin="$1" chain parent rules
    rules="$("$bin" -w 5 -S 2>/dev/null)" || return 0
    while read -r chain; do
        [[ -n "$chain" ]] || continue
        while read -r parent; do
            [[ -n "$parent" ]] || continue
            while "$bin" -w 5 -C "$parent" -j "$chain" 2>/dev/null; do
                "$bin" -w 5 -D "$parent" -j "$chain"
            done
        done < <(awk -v c="$chain" \
            '$1 == "-A" && $NF == c && $(NF - 1) == "-j" { print $2 }' <<<"$rules")
        "$bin" -w 5 -F "$chain" 2>/dev/null || true
        "$bin" -w 5 -X "$chain" 2>/dev/null || true
        printf 'firewall: staging artığı silindi (%s %s)\n' "$bin" "$chain"
    done < <(awk -v p="$CHAIN_STAGING_PREFIX" \
        '$1 == "-N" && index($2, p) == 1 { print $2 }' <<<"$rules")
}

create_staging() {
    local bin="$1" prefix="$2" name="" _
    for _ in $(seq 1 20); do
        name="${prefix}$RANDOM"
        if "$bin" -w 5 -N "$name" 2>/dev/null; then
            printf '%s\n' "$name"
            return 0
        fi
    done
    die "staging zinciri oluşturulamadı ($bin)"
}

activate_named() {
    # Staging önce parent'a bağlanır; sonra eski final kaldırılır ve rename yapılır.
    # INPUT / FORWARD / POSTROUTING içindeki diğer (üçüncü taraf) kurallar silinmez.
    # INPUT'ta staging, varsa ts-input'un hemen arkasına girer (gölgelememek için).
    local bin="$1" parent="$2" staging="$3" final="$4" pos=1
    if [[ "$parent" == "INPUT" ]]; then
        pos="$(insert_pos_after_ts_input "$bin")"
    fi
    "$bin" -w 5 -I "$parent" "$pos" -j "$staging"
    while "$bin" -w 5 -C "$parent" -j "$final" 2>/dev/null; do
        "$bin" -w 5 -D "$parent" -j "$final"
    done
    if "$bin" -w 5 -L "$final" -n >/dev/null 2>&1; then
        "$bin" -w 5 -F "$final"
        "$bin" -w 5 -X "$final"
    fi
    "$bin" -w 5 -E "$staging" "$final"
    ensure_jump "$bin" "$parent" "$final"
    while "$bin" -w 5 -C "$parent" -j "$staging" 2>/dev/null; do
        "$bin" -w 5 -D "$parent" -j "$staging"
    done
}

# Ağ yokken boş FORWARD/NAT zinciri ve jump oluşturulmaz. Yalnız bize ait
# zincir kaldırılır; ts-* ve diğer yazılımların kuralları olduğu gibi kalır.
remove_named() {
    local bin="$1" parent="$2" chain="$3"
    while "$bin" -w 5 -C "$parent" -j "$chain" 2>/dev/null; do
        "$bin" -w 5 -D "$parent" -j "$chain"
    done
    if "$bin" -w 5 -L "$chain" -n >/dev/null 2>&1; then
        "$bin" -w 5 -F "$chain"
        "$bin" -w 5 -X "$chain"
    fi
}

check_absent() {
    local bin="$1" parent="$2" chain="$3"
    if "$bin" -w 5 -L "$chain" -n >/dev/null 2>&1 ||
        "$bin" -w 5 -C "$parent" -j "$chain" 2>/dev/null; then
        die "$bin: ağ yokken gereksiz $chain zinciri/jump mevcut"
    fi
}

check_rule_count() {
    local bin="$1" chain="$2" expected="$3" count
    count="$("$bin" -w 5 -S "$chain" | grep -c "^-A $chain " || true)"
    [[ "$count" -eq "$expected" ]] || die "$bin: $chain kural sayısı $count (beklenen $expected)"
}

container_dns_iface() {
    # Older state files predate the managed bridge key. Match the network helper's
    # default and validation, never accept a caller-supplied wildcard interface.
    local prefix="${KONTEYNER_BRIDGE_PREFIX-ksl}"
    [[ "$prefix" =~ ^[a-z][a-z0-9]{1,4}$ ]] || die "konteyner köprü öneki geçersiz"
    printf '%s+\n' "$prefix"
}

apply_input4() {
    local bin=iptables staging i proto dns_iface
    dns_iface="$(container_dns_iface)"
    staging="$(create_staging "$bin" "${CHAIN_STAGING_PREFIX}IN-")"
    for ((i = 0; i < ${#VPN_IFACES[@]}; i++)); do
        "$bin" -w 5 -A "$staging" -i "${VPN_IFACES[i]}" -j DROP
    done
    "$bin" -w 5 -A "$staging" -i lo -j ACCEPT
    "$bin" -w 5 -A "$staging" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
    "$bin" -w 5 -A "$staging" -i "$TAILSCALE_IF" -j ACCEPT
    # Aardvark serves only its bridge gateway. Keep container DNS working after
    # firewall reload without allowing other host addresses, services or VPNs.
    for proto in udp tcp; do
        "$bin" -w 5 -A "$staging" -i "$dns_iface" -p "$proto" --dport 53 \
            -m addrtype --dst-type LOCAL --limit-iface-in -j ACCEPT
    done
    # Tailscale'in kendi UDP portu: ts-input da kabul eder ama o zincirin
    # varlığına/sırasına bağlı kalmamak için burada da açık (DD-73).
    "$bin" -w 5 -A "$staging" -i "$WAN_INTERFACE" -p udp \
        --dport "$TAILSCALE_UDP_PORT" -j ACCEPT
    "$bin" -w 5 -A "$staging" -i "$WAN_INTERFACE" -p tcp --dport "$SSH_PUBLIC_PORT" -j ACCEPT
    for ((i = 0; i < ${#VPN_IFACES[@]}; i++)); do
        "$bin" -w 5 -A "$staging" -i "$WAN_INTERFACE" -p udp --dport "${VPN_PORTS[i]}" -j ACCEPT
    done
    if [[ "$SHARE_WAN_ACTIVE" == 1 ]]; then
        "$bin" -w 5 -A "$staging" -i "$WAN_INTERFACE" -p tcp --dport "$SHARE_WAN_PORT" -j ACCEPT
    fi
    "$bin" -w 5 -A "$staging" -i "$WAN_INTERFACE" -j DROP
    "$bin" -w 5 -A "$staging" -j DROP
    activate_named "$bin" INPUT "$staging" "$CHAIN_INPUT"
}

apply_input6() {
    local bin=ip6tables staging i type
    command -v "$bin" >/dev/null || die "ip6tables gerekli"
    staging="$(create_staging "$bin" "${CHAIN_STAGING_PREFIX}IN6-")"
    for ((i = 0; i < ${#VPN_IFACES[@]}; i++)); do
        "$bin" -w 5 -A "$staging" -i "${VPN_IFACES[i]}" -j DROP
    done
    "$bin" -w 5 -A "$staging" -i lo -j ACCEPT
    "$bin" -w 5 -A "$staging" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
    "$bin" -w 5 -A "$staging" -i "$TAILSCALE_IF" -j ACCEPT
    # NDP/RA ve PMTU: WAN IPv6 default (fe80::…) komşu çözümü buna bağlı.
    for type in "${ICMP6_TYPES[@]}"; do
        "$bin" -w 5 -A "$staging" -p ipv6-icmp --icmpv6-type "$type" -j ACCEPT
    done
    "$bin" -w 5 -A "$staging" -i "$WAN_INTERFACE" -p udp \
        --dport "$TAILSCALE_UDP_PORT" -j ACCEPT
    "$bin" -w 5 -A "$staging" -i "$WAN_INTERFACE" -p tcp --dport "$SSH_PUBLIC_PORT" -j ACCEPT
    "$bin" -w 5 -A "$staging" -i "$WAN_INTERFACE" -j DROP
    "$bin" -w 5 -A "$staging" -j DROP
    activate_named "$bin" INPUT "$staging" "$CHAIN_INPUT"
}

# DD-177/198: declared VPN networks are internet-only. Deny private destinations even when routed via WAN.
# All ingress guards precede return-path permits (including between WG networks).
apply_forward() {
    local bin="$1" prefix="$2" staging i dest blocked="$VPN_BLOCK_DEST4"
    [[ "$bin" != ip6tables ]] || blocked="$VPN_BLOCK_DEST6"
    if [[ "${#VPN_IFACES[@]}" -eq 0 ]]; then
        remove_named "$bin" FORWARD "$CHAIN_FORWARD"
        return 0
    fi
    staging="$(create_staging "$bin" "$prefix")"
    for ((i = 0; i < ${#VPN_IFACES[@]}; i++)); do
        for dest in $blocked; do
            "$bin" -w 5 -A "$staging" -i "${VPN_IFACES[i]}" -d "$dest" -j DROP
        done
        "$bin" -w 5 -A "$staging" -i "${VPN_IFACES[i]}" -o "$WAN_INTERFACE" -j ACCEPT
        "$bin" -w 5 -A "$staging" -i "${VPN_IFACES[i]}" -j DROP
    done
    for ((i = 0; i < ${#VPN_IFACES[@]}; i++)); do
        "$bin" -w 5 -A "$staging" -i "$WAN_INTERFACE" -o "${VPN_IFACES[i]}" \
            -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
        "$bin" -w 5 -A "$staging" -o "${VPN_IFACES[i]}" -j DROP
    done
    activate_named "$bin" FORWARD "$staging" "$CHAIN_FORWARD"
}

# DD-120: VPN alt ağı WAN'a çıkarken maskelenir (wg-quick PostUp'ı yok;
# kural sahibi bu betik, DD-16/DD-17).
apply_nat() {
    local bin="$1" prefix="$2" subnet staging
    shift 2
    if [[ "$#" -eq 0 ]]; then
        remove_named "$bin" POSTROUTING "$CHAIN_NAT"
        return 0
    fi
    staging="$(create_staging "$bin" "$prefix")"
    for subnet in "$@"; do
        "$bin" -w 5 -A "$staging" -s "$subnet" -o "$WAN_INTERFACE" -j MASQUERADE
    done
    activate_named "$bin" POSTROUTING "$staging" "$CHAIN_NAT"
}

check_jump_exactly_one() {
    local bin="$1" parent="$2" chain="$3" n
    n="$("$bin" -w 5 -L "$parent" -n --line-numbers 2>/dev/null |
        awk -v c="$chain" '$2 == c { n++ } END { print n+0 }')"
    [[ "$n" -eq 1 ]] ||
        die "$bin: $parent -> $chain jump sayısı $n (beklenen 1)"
}

check_rule() {
    local bin="$1"
    shift
    "$bin" -w 5 -C "$@" 2>/dev/null ||
        die "$bin: eksik kural: $*"
}

check_no_staging_artifacts() {
    local bin="$1" hit
    hit="$("$bin" -w 5 -S 2>/dev/null | awk -v p="$CHAIN_STAGING_PREFIX" '
        $1 == "-N" && index($2, p) == 1 { print $2; exit }
        $1 == "-A" {
            for (i = 1; i < NF; i++)
                if ($i == "-j" && index($(i + 1), p) == 1) {
                    print $(i + 1)
                    exit
                }
        }
    ')"
    [[ -z "$hit" ]] || die "$bin: staging artığı: $hit"
}

check_ts_input_precedence() {
    local bin="$1" ts_pos="" master_pos=""
    if ! "$bin" -w 5 -L ts-input -n >/dev/null 2>&1; then
        return 0
    fi
    if ! "$bin" -w 5 -C INPUT -j ts-input 2>/dev/null; then
        return 0
    fi
    ts_pos="$("$bin" -w 5 -L INPUT -n --line-numbers |
        awk '$2 == "ts-input" { print $1; exit }')"
    master_pos="$("$bin" -w 5 -L INPUT -n --line-numbers |
        awk -v c="$CHAIN_INPUT" '$2 == c { print $1; exit }')"
    [[ -n "$ts_pos" && -n "$master_pos" ]] ||
        die "$bin: ts-input / $CHAIN_INPUT satır numarası okunamadı"
    [[ "$ts_pos" -lt "$master_pos" ]] ||
        die "$bin: INPUT sırası hatalı (ts-input=$ts_pos, $CHAIN_INPUT=$master_pos)"
}

current_wan_interface() {
    local route
    route="$(ip -4 -o route get 1.1.1.1)" || die "WAN rotası okunamadı"
    awk '{for (i=1;i<=NF;i++) if ($i=="dev") {print $(i+1); exit}}' <<<"$route"
}

# NIC yeniden adlandırılırsa state ipucu bayatlar. Eskiden bu ölümcüldü ve host
# hiç INPUT politikası almıyordu; artık canlı arayüz belirleyici (DD-94).
# state.env yazılmaz: WAN_INTERFACE'i çalışma zamanında yalnız bu betik tüketir.
resolve_wan_interface() {
    local live
    live="$(current_wan_interface)"
    [[ -n "$live" ]] || die "güncel WAN arayüzü okunamadı"
    if [[ -n "${WAN_INTERFACE:-}" && "$live" != "$WAN_INTERFACE" ]]; then
        printf 'firewall: UYARI WAN arayüzü drift: state=%s live=%s (canlı kullanılıyor)\n' \
            "$WAN_INTERFACE" "$live" >&2
    fi
    WAN_INTERFACE="$live"
}

# Zincir şekli: tek WAN DROP, WAN izinlerinden sonra ve öncesinde koşulsuz
# (arayüz/port/proto/conntrack kısıtı olmayan) ACCEPT/RETURN bulunmamalı.
# Sıra `iptables -S` üzerinden okunur; -L -v sütun düzeni sürüme göre değişir.
check_chain_shape() {
    local bin="$1" chain="$2" allow_target="$3"
    local drop_pos=0 drop_count=0 allow_max=0 bypass="" n=0 line body
    while IFS= read -r line; do
        [[ "$line" == "-A $chain "* ]] || continue
        n=$((n + 1))
        body="${line#-A "$chain" }"
        # Koşulsuz kural: yalnız -j <target>, hiçbir match seçeneği yok.
        if [[ "$body" == "-j ACCEPT" || "$body" == "-j RETURN" ]]; then
            [[ -n "$bypass" ]] || bypass="$n:$body"
        fi
        case "$line" in
            *"-i ${WAN_INTERFACE} "*)
                case "$line" in
                    *"-j DROP") drop_pos=$n; drop_count=$((drop_count + 1)) ;;
                    *"-j ${allow_target}") allow_max=$n ;;
                esac
                ;;
        esac
    done < <("$bin" -w 5 -S "$chain")
    [[ "$drop_pos" -gt 0 ]] ||
        die "$bin: $chain içinde WAN DROP satırı yok"
    [[ "$drop_count" -eq 1 ]] ||
        die "$bin: $chain WAN DROP sayısı $drop_count (beklenen 1)"
    [[ "$drop_pos" -gt "$allow_max" ]] ||
        die "$bin: $chain WAN DROP ($drop_pos) allow ($allow_target max=$allow_max) önünde veya eşit"
    if [[ -n "$bypass" ]]; then
        local pos="${bypass%%:*}" rule="${bypass#*:}"
        [[ "$pos" -gt "$drop_pos" ]] ||
            die "$bin: $chain WAN DROP öncesi koşulsuz kural ($pos: $rule) — bypass"
    fi
}

# WAN'dan izinli (proto, port) çiftleri — tek liste. check_rule çağrıları da
# beklenen sayı da buradan üretilir; ikinci bir yerde tekrarlanmaz.
wan_allow_pairs() {
    printf '%s\n' "udp $TAILSCALE_UDP_PORT" "tcp $SSH_PUBLIC_PORT"
    [[ "$1" == v4 ]] || return 0
    [[ "$SHARE_WAN_ACTIVE" != 1 ]] || printf 'tcp %s\n' "$SHARE_WAN_PORT"
    # Ağ yoksa dizi boştur; bash 3.2'de "boş dizi + set -u" hata verir (DD-143).
    [[ "${#VPN_PORTS[@]}" -eq 0 ]] || printf 'udp %s\n' "${VPN_PORTS[@]}"
    # DD-151/198: paketler yalnız bildirdikleri portları alır; başka gelen port açılmaz.
    return 0
}

# Tek tek desen kontrolü "eksik kural" bulur, "fazladan kural" bulamaz:
# '-i WAN -j ACCEPT' gibi port nitelemesi olmayan bir geçiş, beklenen
# kuralların hepsi yerinde olduğu için denetimden sağ çıkardı. Sayı birebir
# tutmak zorunda: her fazladan WAN geçişi — blanket ya da portlu — düşer.
check_wan_allow_count() {
    local bin="$1" chain="$2" target="$3" expected="$4" actual
    actual="$("$bin" -w 5 -S "$chain" 2>/dev/null |
        grep -cE -- "^-A $chain .*-i $WAN_INTERFACE .*-j $target\$" || true)"
    [[ "$actual" -eq "$expected" ]] ||
        die "$bin: $chain WAN $target sayısı $actual (beklenen $expected) — fazladan geçiş"
}

check_input_chain() {
    local bin="$1" family="$2" n=0 proto port i type expected=5 dns_iface
    check_jump_exactly_one "$bin" INPUT "$CHAIN_INPUT"
    check_no_staging_artifacts "$bin"
    check_ts_input_precedence "$bin"
    check_rule "$bin" "$CHAIN_INPUT" -i lo -j ACCEPT
    check_rule "$bin" "$CHAIN_INPUT" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
    check_rule "$bin" "$CHAIN_INPUT" -i "$TAILSCALE_IF" -j ACCEPT
    if [[ "$family" == v4 ]]; then
        dns_iface="$(container_dns_iface)"
        for proto in udp tcp; do
            check_rule "$bin" "$CHAIN_INPUT" -i "$dns_iface" -p "$proto" --dport 53 \
                -m addrtype --dst-type LOCAL --limit-iface-in -j ACCEPT
        done
        expected=$((expected + 2))
    fi
    check_rule "$bin" "$CHAIN_INPUT" -i "$WAN_INTERFACE" -j DROP
    check_rule "$bin" "$CHAIN_INPUT" -j DROP
    [[ "$("$bin" -w 5 -S "$CHAIN_INPUT" | tail -n 1)" == "-A $CHAIN_INPUT -j DROP" ]] ||
        die "$bin: son koşulsuz DROP yerinde değil"
    while read -r proto port; do
        [[ -n "$proto" ]] || continue
        check_rule "$bin" "$CHAIN_INPUT" -i "$WAN_INTERFACE" \
            -p "$proto" --dport "$port" -j ACCEPT
        n=$((n + 1))
    done < <(wan_allow_pairs "$family")
    check_wan_allow_count "$bin" "$CHAIN_INPUT" ACCEPT "$n"
    check_chain_shape "$bin" "$CHAIN_INPUT" ACCEPT
    expected=$((expected + n))
    if [[ "$family" == v6 ]]; then
        for type in "${ICMP6_TYPES[@]}"; do
            check_rule "$bin" "$CHAIN_INPUT" -p ipv6-icmp --icmpv6-type "$type" -j ACCEPT
        done
        expected=$((expected + ${#ICMP6_TYPES[@]}))
    fi
    for ((i = 0; i < ${#VPN_IFACES[@]}; i++)); do
        check_rule "$bin" "$CHAIN_INPUT" -i "${VPN_IFACES[i]}" -j DROP
        expected=$((expected + 1))
        check_before "$bin" "$CHAIN_INPUT" "-m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT" \
            "-i ${VPN_IFACES[i]} -j DROP"
    done
    check_rule_count "$bin" "$CHAIN_INPUT" "$expected"
}

# check_before BIN CHAIN SON_KURAL ÖNCEKİ_DESEN — ÖNCEKİ_DESEN'le başlayan her
# kural (-A CHAIN sonrası) SON_KURAL'dan önce gelmeli. -C sırayı görmez.
check_before() {
    local bin="$1" chain="$2" last="$3" earlier="$4" n=0 last_pos=0 max_earlier=0 line body
    while IFS= read -r line; do
        [[ "$line" == "-A $chain "* ]] || continue
        n=$((n + 1))
        body="${line#-A "$chain" }"
        [[ "$body" == "$last" ]] && last_pos=$n
        [[ "$body" == "$earlier"* ]] && max_earlier=$n
    done < <("$bin" -w 5 -S "$chain")
    [[ "$last_pos" -gt 0 ]] || die "$bin: $chain içinde '$last' yok"
    [[ "$last_pos" -gt "$max_earlier" ]] ||
        die "$bin: $chain sırası hatalı: '$earlier…' ($max_earlier) '$last' ($last_pos) önünde değil"
}

check_forward_chain() {
    local bin="$1" i w dest blocked="$VPN_BLOCK_DEST4" count=0
    [[ "$bin" != ip6tables ]] || blocked="$VPN_BLOCK_DEST6"
    if [[ "${#VPN_IFACES[@]}" -eq 0 ]]; then
        check_absent "$bin" FORWARD "$CHAIN_FORWARD"
        return 0
    fi
    check_jump_exactly_one "$bin" FORWARD "$CHAIN_FORWARD"
    for ((i = 0; i < ${#VPN_IFACES[@]}; i++)); do
        w="${VPN_IFACES[i]}"
        for dest in $blocked; do
            check_rule "$bin" "$CHAIN_FORWARD" -i "$w" -d "$dest" -j DROP
            count=$((count + 1))
            check_before "$bin" "$CHAIN_FORWARD" "-i $w -o $WAN_INTERFACE -j ACCEPT" "-d $dest -i $w "
        done
        check_rule "$bin" "$CHAIN_FORWARD" -i "$w" -o "$WAN_INTERFACE" -j ACCEPT
        check_rule "$bin" "$CHAIN_FORWARD" -i "$w" -j DROP
        check_rule "$bin" "$CHAIN_FORWARD" -i "$WAN_INTERFACE" -o "$w" \
            -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
        check_rule "$bin" "$CHAIN_FORWARD" -o "$w" -j DROP
        check_before "$bin" "$CHAIN_FORWARD" "-i $w -j DROP" "-i $w -o $WAN_INTERFACE "
        check_before "$bin" "$CHAIN_FORWARD" "-o $w -j DROP" \
            "-i $WAN_INTERFACE -o $w -m conntrack --ctstate RELATED,ESTABLISHED "
    done
    # Fazladan kural (ör. -i wg0 -j ACCEPT) -C ile görünmez; sayı birebir tutmalı.
    check_rule_count "$bin" "$CHAIN_FORWARD" "$((4 * ${#VPN_IFACES[@]} + count))"
}

check_nat_chain() {
    local bin="$1" subnet
    shift
    check_no_staging_artifacts "$bin"
    if [[ "$#" -eq 0 ]]; then
        check_absent "$bin" POSTROUTING "$CHAIN_NAT"
        return 0
    fi
    check_jump_exactly_one "$bin" POSTROUTING "$CHAIN_NAT"
    for subnet in "$@"; do
        check_rule "$bin" "$CHAIN_NAT" -s "$subnet" -o "$WAN_INTERFACE" -j MASQUERADE
    done
    check_rule_count "$bin" "$CHAIN_NAT" "$#"
}

# DD-156: structured operator rules are separate from the fixed baseline and
# precede ts-input (whose blanket tailnet ACCEPT would otherwise bypass denies).
# No Tailscale-owned chain is edited. Values are emitted by the validated helper;
# no eval, shell commands or arbitrary match expressions are accepted.
SETTINGS4="" SETTINGS6=""
load_settings_rules() {
    local ports family proto port line core4="" core6=""
    [[ -n "${SETTINGS_FILE:-}" ]] || return 0
    SETTINGS4="$(python3 "$SBIN_DIR/master_settings.py" rules 4 "$WAN_INTERFACE")" || die "Konsol IPv4 kuralları okunamadı"
    SETTINGS6="$(python3 "$SBIN_DIR/master_settings.py" rules 6 "$WAN_INTERFACE")" || die "Konsol IPv6 kuralları okunamadı"
    if [[ "$SHARE_WAN_ACTIVE" == 1 ]]; then
        # Before operator ACCEPT rules: cap even unauthenticated idle TCP sockets.
        # Existing manual DENY rules remain effective; no third-party chains touched.
        line="-i $WAN_INTERFACE -p tcp --dport $SHARE_WAN_PORT -m connlimit --connlimit-above $SHARE_SOCKET_TOTAL --connlimit-mask 0 --connlimit-saddr -m comment --comment konsol-base:share-total -j REJECT --reject-with tcp-reset"
        core4="$line"$'\n'
        line="-i $WAN_INTERFACE -p tcp --dport $SHARE_WAN_PORT -m connlimit --connlimit-above $SHARE_SOCKET_IP --connlimit-mask 32 --connlimit-saddr -m comment --comment konsol-base:share-ip -j REJECT --reject-with tcp-reset"
        SETTINGS4="$core4$line"$'\n'"$SETTINGS4"
        core4=""
    fi
    ports="$(python3 "$SBIN_DIR/master_settings.py" tailnet-ports)" || die "Tailscale izinleri okunamadı"
    while read -r family proto port; do
        [[ "$family" =~ ^[46]$ && "$proto" =~ ^(tcp|udp)$ && "$port" =~ ^[0-9]+$ && "$port" -ge 1 && "$port" -le 65535 ]] ||
            die "Tailscale port kaydı geçersiz; kurallar değiştirilmedi"
        line="-i $TAILSCALE_IF -p $proto --dport $port -m comment --comment konsol-base:tail-$proto-$port -j RETURN"
        if [[ "$family" == 4 ]]; then core4+="$line"$'\n'; else core6+="$line"$'\n'; fi
    done <<<"$ports"
    # Declared VPN endpoints are requirements, including access over tailnet.
    # Do not infer obsolescence from peer counts or traffic counters.
    for port in ${VPN_PORTS[@]+"${VPN_PORTS[@]}"}; do
        line="-i $TAILSCALE_IF -p udp --dport $port -m comment --comment konsol-base:wg-$port -j RETURN"
        core4+="$line"$'\n'; core6+="$line"$'\n'
    done
    # Ping/error control traffic has no service port; IPv6 PMTU/NDP must survive.
    core4+="-i $TAILSCALE_IF -p icmp -m comment --comment konsol-base:icmp -j RETURN"$'\n'
    core6+="-i $TAILSCALE_IF -p ipv6-icmp -m comment --comment konsol-base:icmp -j RETURN"$'\n'
    line="-i $TAILSCALE_IF -m comment --comment konsol-base:tail-drop -j DROP"
    # Operator overrides remain first; the default deny MUST precede ts-input,
    # whose blanket ACCEPT would bypass a restriction inside CHAIN_INPUT.
    SETTINGS4+=$'\n'"$core4$line"
    SETTINGS6+=$'\n'"$core6$line"
}
apply_settings_rules() {
    local bin="$1" rules="$2" staging line i
    local -a args
    [[ -n "${SETTINGS_FILE:-}" ]] || return 0
    staging="$(create_staging "$bin" "${CHAIN_STAGING_PREFIX}USER-")"
    # Before established/ICMP and ts-input: no old flow or override bypass.
    for ((i = 0; i < ${#VPN_IFACES[@]}; i++)); do
        "$bin" -w 5 -A "$staging" -i "${VPN_IFACES[i]}" -j DROP
    done
    "$bin" -w 5 -A "$staging" -i lo -j RETURN
    "$bin" -w 5 -A "$staging" -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
    while IFS= read -r line; do
        [[ -n "$line" ]] || continue
        read -r -a args <<<"$line"
        "$bin" -w 5 -A "$staging" "${args[@]}"
    done <<<"$rules"
    "$bin" -w 5 -I INPUT 1 -j "$staging"
    while "$bin" -w 5 -C INPUT -j "$CHAIN_SETTINGS" 2>/dev/null; do
        "$bin" -w 5 -D INPUT -j "$CHAIN_SETTINGS"
    done
    if "$bin" -w 5 -L "$CHAIN_SETTINGS" -n >/dev/null 2>&1; then
        "$bin" -w 5 -F "$CHAIN_SETTINGS"
        "$bin" -w 5 -X "$CHAIN_SETTINGS"
    fi
    "$bin" -w 5 -E "$staging" "$CHAIN_SETTINGS"
}
check_settings_rules() {
    local bin="$1" rules="$2" line expected=2 actual listing ids="" actual_ids i
    local -a args
    [[ -n "${SETTINGS_FILE:-}" ]] || return 0
    check_jump_exactly_one "$bin" INPUT "$CHAIN_SETTINGS"
    [[ "$(input_line "$bin" "$CHAIN_SETTINGS")" == 1 ]] || die "$bin: Konsol kuralları INPUT başında değil"
    for ((i = 0; i < ${#VPN_IFACES[@]}; i++)); do
        check_rule "$bin" "$CHAIN_SETTINGS" -i "${VPN_IFACES[i]}" -j DROP
        expected=$((expected + 1))
    done
    check_rule "$bin" "$CHAIN_SETTINGS" -i lo -j RETURN
    check_rule "$bin" "$CHAIN_SETTINGS" -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
    while IFS= read -r line; do
        [[ -n "$line" ]] || continue
        read -r -a args <<<"$line"
        check_rule "$bin" "$CHAIN_SETTINGS" "${args[@]}"
        ids="$ids$(sed -n 's/.*--comment \(konsol\(-base\)\{0,1\}:[a-zA-Z0-9_-]*\).*/\1/p' <<<"$line") "
        expected=$((expected + 1))
    done <<<"$rules"
    listing="$("$bin" -w 5 -S "$CHAIN_SETTINGS" | grep "^-A $CHAIN_SETTINGS " || true)"
    actual="$(grep -c . <<<"$listing" || true)"
    [[ "$actual" -eq "$expected" ]] || die "$bin: Konsol zincirinde beklenmeyen kural var"
    for ((i = 0; i < ${#VPN_IFACES[@]}; i++)); do
        [[ "$(sed -n "$((i + 1))p" <<<"$listing")" == "-A $CHAIN_SETTINGS -i ${VPN_IFACES[i]} -j DROP" ]] ||
            die "$bin: VPN engeli Konsol zincirinin başında değil"
    done
    [[ "$(sed -n "$((${#VPN_IFACES[@]} + 1))p" <<<"$listing")" == "-A $CHAIN_SETTINGS -i lo -j RETURN" &&
        "$(sed -n "$((${#VPN_IFACES[@]} + 2))p" <<<"$listing")" == "-A $CHAIN_SETTINGS -m conntrack --ctstate RELATED,ESTABLISHED -j RETURN" ]] || die "$bin: Konsol koruma kurallarının sırası bozuk"
    actual_ids="$(sed -n 's/.*--comment "\{0,1\}\(konsol\(-base\)\{0,1\}:[a-zA-Z0-9_-]*\)"\{0,1\}.*/\1/p' <<<"$listing" | tr '\n' ' ')"
    [[ "$actual_ids" == "$ids" ]] || die "$bin: Konsol kullanıcı kurallarının sırası bozuk"
}

# Each recovery chain is all-or-nothing: an incomplete INPUT guard is never
# attached, so a failed accept rule cannot lock out SSH. A later good apply
# purges the unattached chain with the other staging leftovers.
startup_input_guard() {
    local bin="$1" guard="${CHAIN_STAGING_PREFIX}SAFE" type
    ! "$bin" -w 5 -C INPUT -j "$guard" 2>/dev/null || return 0
    "$bin" -w 5 -N "$guard" 2>/dev/null || "$bin" -w 5 -F "$guard" || return 1
    "$bin" -w 5 -A "$guard" -i wg+ -j DROP || return 1
    "$bin" -w 5 -A "$guard" -i lo -j ACCEPT || return 1
    "$bin" -w 5 -A "$guard" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT || return 1
    "$bin" -w 5 -A "$guard" -p tcp --dport "$SSH_PUBLIC_PORT" -j ACCEPT || return 1
    "$bin" -w 5 -A "$guard" -p udp --dport "$TAILSCALE_UDP_PORT" -j ACCEPT || return 1
    if [[ "$bin" == ip6tables ]]; then
        for type in "${ICMP6_TYPES[@]}"; do
            "$bin" -w 5 -A "$guard" -p ipv6-icmp --icmpv6-type "$type" -j ACCEPT || return 1
        done
    fi
    "$bin" -w 5 -A "$guard" -j DROP || return 1
    "$bin" -w 5 -I INPUT 1 -j "$guard"
}

# Even an unknown/pre-existing WG interface cannot forward on a cold boot. This
# does not depend on the INPUT guard having been attached.
startup_forward_guard() {
    local bin="$1" guard="${CHAIN_STAGING_PREFIX}SAFE-FW"
    ! "$bin" -w 5 -C FORWARD -j "$guard" 2>/dev/null || return 0
    "$bin" -w 5 -N "$guard" 2>/dev/null || "$bin" -w 5 -F "$guard" || return 1
    "$bin" -w 5 -A "$guard" -i wg+ -j DROP || return 1
    "$bin" -w 5 -A "$guard" -o wg+ -j DROP || return 1
    "$bin" -w 5 -I FORWARD 1 -j "$guard"
}

# An unreadable registry must not leave a fresh boot unfiltered. Existing owned
# policies (including manual denies) stay intact. A cold family gets a minimal
# recovery guard BEFORE ts-input; full --check still fails, keeping Caddy/WG shut.
startup_failure() {
    local rc=$? bin
    trap - EXIT
    [[ "$rc" -ne 0 && "$MODE" == apply ]] || return "$rc"
    for bin in iptables ip6tables; do
        if "$bin" -w 5 -C INPUT -j "$CHAIN_INPUT" 2>/dev/null &&
            "$bin" -w 5 -C "$CHAIN_INPUT" -j DROP 2>/dev/null &&
            { [[ -z "${SETTINGS_FILE:-}" ]] || [[ "$(input_line "$bin" "$CHAIN_SETTINGS")" == 1 ]]; }; then
            continue
        fi
        if startup_input_guard "$bin"; then
            printf 'firewall: UYARI kayıt okunamadı; %s yalnız kurtarma erişiminde. Kayıt düzeltilmeli.\n' "$bin" >&2
        else
            printf 'firewall: HATA kayıt okunamadı ve %s kurtarma girişi kurulamadı; giriş filtrelenmiyor.\n' "$bin" >&2
        fi
        startup_forward_guard "$bin" ||
            printf 'firewall: HATA %s kurtarma yönlendirme engeli kurulamadı.\n' "$bin" >&2
    done
    return "$rc"
}

if [[ -n "${RUNTIME_DIR:-}" ]]; then
    mkdir -p "$RUNTIME_DIR"
    exec 7>"$RUNTIME_DIR/firewall.lock"
    flock -w 5 7 || die "başka bir firewall işlemi sürüyor"
fi
trap startup_failure EXIT
container_dns_iface >/dev/null
load_package_rules
load_share_wan
resolve_wan_interface
load_settings_rules
if [[ -n "${KONTEYNER_STATE_DIR:-}" ]]; then
    # Netavark kendi NAT kurallarını tutar. Yalnız Konsol köprülerine gelen trafiğin
    # kapsamını ayrı inet tablosuyla sınırlarız; başka yazılımın zincirine dokunulmaz.
    if [[ "$MODE" == check ]]; then
        python3 "${SBIN_DIR:?}/master_container_network.py" --state "$STATE_FILE" --check
    else
        python3 "${SBIN_DIR:?}/master_container_network.py" --state "$STATE_FILE" apply
    fi
fi
trap - EXIT

if [[ "$MODE" == check ]]; then
    resolve_wan_interface
    check_input_chain iptables v4
    check_input_chain ip6tables v6
    check_forward_chain iptables
    check_forward_chain ip6tables
    check_nat_chain iptables_nat ${VPN_NET4[@]+"${VPN_NET4[@]}"}
    check_nat_chain ip6tables_nat ${VPN_NET6[@]+"${VPN_NET6[@]}"}
    check_settings_rules iptables "$SETTINGS4"
    check_settings_rules ip6tables "$SETTINGS6"
    printf 'firewall: kritik politikalar yerinde\n'
    exit 0
fi

resolve_wan_interface
apply_input4
ensure_ts_input_precedence iptables
apply_input6
ensure_ts_input_precedence ip6tables
apply_forward iptables "${CHAIN_STAGING_PREFIX}FW-"
apply_forward ip6tables "${CHAIN_STAGING_PREFIX}FW6-"
apply_nat iptables_nat "${CHAIN_STAGING_PREFIX}NAT-" ${VPN_NET4[@]+"${VPN_NET4[@]}"}
apply_nat ip6tables_nat "${CHAIN_STAGING_PREFIX}NAT6-" ${VPN_NET6[@]+"${VPN_NET6[@]}"}
apply_settings_rules iptables "$SETTINGS4"
apply_settings_rules ip6tables "$SETTINGS6"
purge_staging_leftovers iptables
purge_staging_leftovers ip6tables
purge_staging_leftovers iptables_nat
purge_staging_leftovers ip6tables_nat
check_no_staging_artifacts iptables
check_no_staging_artifacts ip6tables
check_no_staging_artifacts iptables_nat
check_no_staging_artifacts ip6tables_nat
printf 'firewall: politika uygulandı (WAN if=%s)\n' "$WAN_INTERFACE"
