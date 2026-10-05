#!/bin/bash
# WireGuard peer menüsü (DD-124, DD-143). Repo kökünde çift tıklanır; sunucudaki
# master-wg'yi SSH ile çağırır. Yapılandırma sunucuda üretilir; Mac'ten profil
# yüklenmez. Ağlar ve peer'lar sunucuda yaşar, QR kodu terminale basılır.
# İstenirse profil kurulum/wireguard/<ad>.conf ve QR resmi <ad>.png olarak indirilir
# (DD-132) — bu yalnız kolaylıktır, kurulum o klasöre bakmaz. "DNS değiştir" yalnız
# profildeki DNS satırını, "Ağı yeniden üret" sunucu anahtarını ve o ağdaki bütün
# peer'ları sıfırlar (DD-130). Ağları Konsol (panel.<alan>) ya da bu menü kurar.
# Finder bu dosyayı macOS /bin/bash 3.2 ile çalıştırır.
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "$0")" && pwd)"
INPUT_FILE="$ROOT/kurulum/kurulum.env"
DEFAULTS_FILE="$ROOT/Data/config/defaults.env"
# DD-201: WireGuard'ın varsayılanları paketindedir, temelin defaults.env'inde değil.
WG_DEFAULTS_FILE="$ROOT/Data/magaza/wireguard/wireguard.env"
INSTALLER="$ROOT/Data/install.sh"
WG_DIR="$ROOT/kurulum/wireguard"
NAME_RE='^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$'

pause_exit() {
    echo
    read -r -p "Pencereyi kapatmak için Enter..." || true
    exit "${1:-0}"
}

fail() {
    printf 'HATA: %s\n' "$*" >&2
    pause_exit 1
}

# defaults.env'den ya da paketin wireguard.env'inden tek bir değer (source edilmez).
value_of() {
    awk -F= -v k="$2" '$1 == k {v = substr($0, length(k) + 2); gsub(/^"|"$/, "", v); print v; exit}' "$1"
}
default_of() { value_of "$DEFAULTS_FILE" "$1"; }
wg_default_of() { value_of "$WG_DEFAULTS_FILE" "$1"; }

[[ -f "$DEFAULTS_FILE" && -f "$WG_DEFAULTS_FILE" && -f "$INSTALLER" ]] || fail "Data/ bulunamadı; betiği repo kökünden çalıştırın."
[[ -f "$INPUT_FILE" ]] || fail "girdi dosyası yok: $INPUT_FILE"
# kurulum.env'den yalnız SSH_HOST okunur.
HOST="$(awk 'index($0, "SSH_HOST=") == 1 {print substr($0, 10); exit}' "$INPUT_FILE")"
[[ "$HOST" =~ ^[A-Za-z0-9._@-]+$ ]] || fail "kurulum.env içinde SSH_HOST boş ya da geçersiz"
LOCAL_VERSION="$(awk -F= '/^V2_VERSION=/{gsub(/"/, "", $2); print $2; exit}' "$INSTALLER")"
MASTER_WG="$(default_of SBIN_DIR)/master-wg"
DEFAULT_DNS="$(wg_default_of WG_CLIENT_DNS_DEFAULT)"
DEFAULT_KEEPALIVE="$(wg_default_of WG_CLIENT_KEEPALIVE_DEFAULT)"
DEFAULT_MTU="$(wg_default_of WG_MTU)"

ctl_dir="$(mktemp -d "${TMPDIR:-/tmp}/wg-menu.XXXXXX")"
# ServerAlive: sunucu kaybolursa açık bağlantı dakikalarca asılı kalmasın.
ssh_base=(-o BatchMode=yes -o ClearAllForwardings=yes -o ConnectTimeout=20
    -o ServerAliveInterval=15 -o ServerAliveCountMax=3
    -o ControlMaster=auto -o "ControlPath=$ctl_dir/c" -o ControlPersist=120)
cleanup() {
    ssh "${ssh_base[@]}" -O exit "$HOST" >/dev/null 2>&1 || true
    rm -rf "$ctl_dir"
}
trap cleanup EXIT

# Seçili ağ (DD-143): sunucuda birden çok ağ olabilir; master-wg'ye --if ile gider.
NET=""

# Uzak komut: argümanlar %q ile tırnaklanır, sunucu kabuğu tek tek ayırır.
remote() {
    local cmd
    if [[ -n "$NET" ]]; then
        cmd="$(printf '%q ' "$MASTER_WG" --if "$NET" "$@")"
    else
        cmd="$(printf '%q ' "$MASTER_WG" "$@")"
    fi
    # -n: master-wg stdin okumaz; ssh menü girdisini yutmasın.
    ssh -n "${ssh_base[@]}" "$HOST" "$cmd"
}

ask() {
    local var="$1" msg="$2" def="${3:-}" reply=""
    if [[ -n "$def" ]]; then
        read -r -p "$msg [$def]: " reply || true
        reply="${reply:-$def}"
    else
        read -r -p "$msg: " reply || true
    fi
    printf -v "$var" '%s' "$reply"
}

human_bytes() {
    awk -v b="$1" 'BEGIN {
        split("B KiB MiB GiB TiB", u, " "); i = 1
        while (b >= 1024 && i < 5) { b /= 1024; i++ }
        printf (i == 1 ? "%d %s" : "%.1f %s"), b, u[i]
    }'
}

list_peers() {
    local out name ip hs rx tx profile now ago
    out="$(remote list)" || return 1
    if [[ -z "$out" ]]; then
        echo "  (peer yok)"
        return 0
    fi
    now="$(date +%s)"
    # printf bayt sayar: çok baytlı başlıklar (Ş, İ) satırlarla aynı hizaya çekilir.
    printf '  %-16s %-12s %-18s %-12s %-13s %s\n' AD IP "SON EL SIKIŞMA" GELEN GİDEN PROFİL
    while IFS=$'\t' read -r name ip hs rx tx profile; do
        if [[ "$hs" == 0 ]]; then
            ago="hiç"
        elif (( now - hs < 120 )); then
            ago="$(( now - hs )) sn önce"
        elif (( now - hs < 7200 )); then
            ago="$(( (now - hs) / 60 )) dk önce"
        else
            ago="$(( (now - hs) / 3600 )) sa önce"
        fi
        printf '  %-16s %-12s %-18s %-12s %-12s %s\n' "$name" "$ip" "$ago" \
            "$(human_bytes "$rx")" "$(human_bytes "$tx")" "$profile"
    done <<<"$out"
}

fetch_profile() {
    local name="$1" tmp
    mkdir -p "$WG_DIR"
    chmod 700 "$WG_DIR"
    tmp="$WG_DIR/.$name.conf.gelen"
    (umask 077 && remote profile "$name" >"$tmp") || { rm -f "$tmp"; return 1; }
    chmod 600 "$tmp"
    mv -f "$tmp" "$WG_DIR/$name.conf"
    echo "Profil alındı: kurulum/wireguard/$name.conf"
    # DD-132: QR resmini sunucu üretir; profille aynı anahtarı taşır (izin 600).
    tmp="$WG_DIR/.$name.png.gelen"
    if (umask 077 && remote png "$name" >"$tmp") && is_png "$tmp"; then
        chmod 600 "$tmp"
        mv -f "$tmp" "$WG_DIR/$name.png"
        echo "QR resmi alındı: kurulum/wireguard/$name.png"
    else
        rm -f "$tmp"
        echo "UYARI: QR resmi alınamadı; '4) QR göster' ile yeniden deneyin." >&2
    fi
}

is_png() {
    [[ "$(head -c 8 "$1" | od -An -tx1 | tr -d ' \n')" == 89504e470d0a1a0a ]]
}

add_peer() {
    local name dns keepalive mtu result
    ask name "Peer adı (harf, rakam, . _ -)"
    [[ "$name" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$ ]] || { echo "Geçersiz ad."; return 1; }
    ask dns "DNS" "$DEFAULT_DNS"
    ask keepalive "PersistentKeepalive (sn, 0 = kapalı)" "$DEFAULT_KEEPALIVE"
    ask mtu "MTU" "$DEFAULT_MTU"
    result="$(remote add "$name" "$dns" "$keepalive" "$mtu")" || return 1
    printf '\nEklendi: %s (%s) — sunucuda üretildi ve bağlantılar kopmadan uygulandı.\n' \
        "$name" "${result##*$'\t'}"
    fetch_profile "$name" || echo "UYARI: profil alınamadı; menüden '4) QR göster' ile yeniden alabilirsiniz." >&2
    printf '\n%s — WireGuard uygulamasıyla okutun:\n' "$name"
    remote qr "$name" || true
}

remove_peer() {
    local name confirm=""
    list_peers || return 1
    echo
    ask name "Çıkarılacak peer adı"
    [[ -n "$name" ]] || return 0
    ask confirm "'$name' sunucudan kaldırılsın, profili silinsin mi? (E/h)" "h"
    [[ "$confirm" =~ ^[EeYy]$ ]] || { echo "Vazgeçildi."; return 0; }
    remote remove "$name" >/dev/null || return 1
    rm -f "$WG_DIR/$name.conf" "$WG_DIR/$name.png"
    echo "Kaldırıldı: $name"
}

# DD-130: profildeki DNS satırını değiştirir; anahtarlar ve ağın conf dosyası aynı kalır.
# Cihaz yeni QR'ı (ya da kurulum/wireguard'daki dosyayı) içe aktarınca geçerli olur.
change_dns() {
    local name current dns result
    list_peers || return 1
    echo
    ask name "DNS'i değiştirilecek peer adı"
    [[ -n "$name" ]] || return 0
    [[ "$name" =~ $NAME_RE ]] || { echo "Geçersiz ad."; return 1; }
    # awk boruyu sonuna kadar okur: erken çıkış ssh'e SIGPIPE verirdi.
    current="$(remote profile "$name" | awk -F' = ' '$1 == "DNS" {v = $2} END {print v}')" || return 1
    ask dns "Yeni DNS" "${current:-$DEFAULT_DNS}"
    result="$(remote dns "$name" "$dns")" || return 1
    printf '\nDNS değişti: %s → %s (anahtarlar aynı).\n' "$name" "${result#*$'\t'}"
    fetch_profile "$name" || echo "UYARI: profil alınamadı; menüden '4) QR göster' ile yeniden alabilirsiniz." >&2
    printf '\n%s — yeni profil; cihazda WireGuard uygulamasıyla okutun (eski tüneli silin):\n' "$name"
    remote qr "$name" || true
}

# DD-130: sunucuda yeni anahtar üretir, bütün peer kayıtlarını ve profilleri
# siler. İndirilmiş yerel profil kopyalarına dokunmaz. Yazılı onay ister.
regenerate_net() {
    local out confirm=""
    echo
    echo "UYARI: sunucuda yeni bir WireGuard anahtarı üretilir; bütün peer kayıtları ve profilleri silinir."
    echo "       Kayıtlı cihazların hiçbiri bağlanamaz; hepsinin '2) Peer ekle' ile yeniden eklenmesi gerekir."
    echo "       Mac'e indirilmiş profil kopyaları silinmez; bu ağın eski profilleri artık geçersizdir."
    echo
    list_peers || return 1
    echo
    ask confirm "Devam etmek için onayla yazın"
    # Büyük/küçük harf fark etmez (ONAYLA, Onayla); başka her şey vazgeçmektir.
    case "$(printf '%s' "$confirm" | tr '[:upper:]' '[:lower:]')" in
        onayla) ;;
        *) echo "Vazgeçildi; hiçbir şey değişmedi."; return 0 ;;
    esac
    out="$(remote reset --onay)" || return 1
    printf '\n%s yeniden üretildi: %s peer ve %s profil silindi; yeni sunucu anahtarı etkin.\n' \
        "$NET" "${out%%$'\t'*}" "${out##*$'\t'}"
}

# DD-143: ağlar sunucuda yaşar. Tek ağ varsa o seçilir; birden çoksa sorulur.
select_net() {
    local ask_always="${1:-}" out lines i reply
    NET=""
    out="$(remote nets)" || return 1
    if [[ -z "$out" ]]; then
        echo
        echo "Sunucuda WireGuard ağı yok."
        echo "Konsol'u açın (http://panel.<alan adı>) → WireGuard → Yapılandır ile ilk ağı kurun."
        return 1
    fi
    lines=""
    i=0
    while IFS=$'\t' read -r iface port _policy s4 rest; do
        [[ -n "$iface" ]] || continue
        i=$((i + 1))
        lines="$lines$i) $iface  UDP $port  $s4  yalnız internet"$'\n'
        eval "net_$i=\$iface"
    done <<<"$out"
    if [[ "$i" -eq 1 && "$ask_always" != "--ask" ]]; then
        eval "NET=\$net_1"
        return 0
    fi
    echo
    echo "Sunucudaki WireGuard ağları:"
    printf '  %s' "$lines"
    ask reply "Ağ numarası" "1"
    [[ "$reply" =~ ^[0-9]+$ && "$reply" -ge 1 && "$reply" -le "$i" ]] || { echo "Geçersiz seçim."; return 1; }
    eval "NET=\$net_$reply"
    echo "Seçilen ağ: $NET"
}

show_qr() {
    local name refresh=""
    list_peers || return 1
    echo
    ask name "QR'ı gösterilecek peer adı"
    [[ -n "$name" ]] || return 0
    remote qr "$name" || return 1
    ask refresh "Profil ve QR resmi kurulum/wireguard'a da alınsın mı? (E/h)" "h"
    [[ ! "$refresh" =~ ^[EeYy]$ ]] || fetch_profile "$name" || true
}

printf '\n=== WireGuard peer yönetimi ===\n'
echo "==> Sunucu: $HOST"
remote_version="$(remote version 2>/dev/null)" ||
    fail "sunucuda master-wg yok ya da çalışmıyor; önce güncel kurulumu (<sürüm>.command) çalıştırın."
[[ "$remote_version" == "$LOCAL_VERSION" ]] ||
    fail "sunucudaki kurulum $remote_version, bu repo $LOCAL_VERSION; önce güncel kurulumu çalıştırın."

select_net || pause_exit 1

while true; do
    printf '\n--- %s · %s (%s) ---\n' "$HOST" "$NET" "$LOCAL_VERSION"
    printf '  1) Peer listesi\n  2) Peer ekle\n  3) Peer çıkar\n  4) QR göster\n  5) Çıkış\n'
    printf '  6) Ağ seç (sunucudaki WireGuard ağları)\n'
    printf '  7) DNS değiştir (anahtarlar aynı, yeni QR)\n'
    printf '  8) Ağı yeniden üret (yeni anahtar, bu ağdaki bütün peer%s silinir)\n' "'lar"
    choice=""
    read -r -p "Seçim: " choice || break
    case "$choice" in
        1) list_peers || true ;;
        2) add_peer || true ;;
        3) remove_peer || true ;;
        4) show_qr || true ;;
        5 | q | Q) break ;;
        6) select_net --ask || true ;;
        7) change_dns || true ;;
        8) regenerate_net || true ;;
        "") ;;
        *) echo "1-8 arası seçin." ;;
    esac
done
pause_exit 0
