#!/usr/bin/env bash
# Kurulum — Debian 13 / Ubuntu 24.04 / 26.04 LTS, doğrusal aşamalar,
# tekrar çalıştırılabilir.
# shellcheck source-path=SCRIPTDIR
set -Eeuo pipefail
umask 077

V2_VERSION="2026.08.06-v2-228"
V2_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=common.sh
source "$V2_ROOT/common.sh"
# shellcheck source=config/defaults.env
source "$V2_ROOT/config/defaults.env"

mkdir -p "$LOG_DIR" "$STATE_DIR" "$RUNTIME_DIR"
V2_LOG_FILE="${V2_LOG_FILE:-$LOG_DIR/install.log}"
# retry fonksiyonları ayrı bash'te çalıştırır; apt çıktısı loga oradan da yazılsın.
export V2_LOG_FILE
RUN_FULL_UPGRADE=0
FIREWALL_NEEDS_RESTART=0
# DD-233: Konsol'daki "Güncelle" düğmesi kurulumu master-guncelle birimiyle, terminalsiz yeniden
# çalıştırır (V2_GUNCELLEME=1). Bu kip ilk kurulum yapmaz: alan adı ve Tailscale oturumu önceden
# hazır olmalı; onayı operatör Konsol'da verir. Başka hiçbir yol terminalsiz kurulum yapmaz.
UPDATE_MODE=0
[[ "${V2_GUNCELLEME:-0}" != "1" ]] || UPDATE_MODE=1
# state.env'de kayıtlı OS kimliği canlı os-release ile uyuşmuyorsa 1 olur;
# OS'a bağlı adımlar dosya içeriği aynı kalsa bile yeniden uygulanır (DD-104).
OS_CHANGED=0
# Ubuntu'da unattended-upgrades varsayılan açık: apt kilidi dakikalarca
# tutulabilir. Kilitte hemen düşmek yerine bekle; retry üstte ayrıca sarar.
# Kurulumun indirdiği .deb'ler kurulduktan sonra önbellekte bırakılmaz
# (~300 MB; DD-125). Başkasının önbelleğe koyduğu dosyaya dokunulmaz.
APT_OPTS=(-o DPkg::Lock::Timeout=60 -o APT::Keep-Downloaded-Packages=false)

prompt() {
    local var="$1" msg="$2" default="${3:-}"
    local reply=""
    if [[ -n "$default" ]]; then
        read -r -p "$msg [$default]: " reply </dev/tty || true
        reply="${reply:-$default}"
    else
        read -r -p "$msg: " reply </dev/tty || true
    fi
    [[ -n "$reply" ]] || die "değer boş olamaz: $msg"
    printf -v "$var" '%s' "$reply"
}

write_state() {
    atomic_write "$STATE_FILE" 0600 <<EOF
V2_VERSION=$V2_VERSION
WAN_INTERFACE=$WAN_INTERFACE
WAN_IPV4=$WAN_IPV4
WAN_IPV6=$WAN_IPV6
TAILSCALE_IF=$TAILSCALE_IF
TAILSCALE_UDP_PORT=$TAILSCALE_UDP_PORT
TAILSCALE_IPV4=$TAILSCALE_IPV4
TAILSCALE_IPV6=$TAILSCALE_IPV6
LOCAL_DOMAIN=$LOCAL_DOMAIN
SERVER_ROOT=$SERVER_ROOT
DOWNLOADS_PATH=$DOWNLOADS_PATH
MEDIA_SUBDIR=$MEDIA_SUBDIR
DNS_PORT=$DNS_PORT
CADDY_HTTP_PORT=$CADDY_HTTP_PORT
DNSMASQ_CONF_FILE=$DNSMASQ_CONF_FILE
SETTINGS_FILE=$SETTINGS_FILE
SETTINGS_PENDING_FILE=$SETTINGS_PENDING_FILE
SETTINGS_DNS_FILE=$SETTINGS_DNS_FILE
SSH_PUBLIC_PORT=$SSH_PUBLIC_PORT
CHAIN_INPUT=$CHAIN_INPUT
CHAIN_FORWARD=$CHAIN_FORWARD
CHAIN_NAT=$CHAIN_NAT
CHAIN_SETTINGS=$CHAIN_SETTINGS
CHAIN_STAGING_PREFIX=$CHAIN_STAGING_PREFIX
PANEL_SOCKET=$PANEL_SOCKET
KONSOL_AUTH_DIR=$KONSOL_AUTH_DIR
CADDY_ADMIN_SOCKET=$CADDY_ADMIN_SOCKET
MODULES_FILE=$MODULES_FILE
MODULES_DIR=$MODULES_DIR
FILES_PANEL_PORT=$FILES_PANEL_PORT
SHARE_PORT=$SHARE_PORT
SHARE_HTTPS_PORT=$SHARE_HTTPS_PORT
SHARE_WAN_BACKEND=$SHARE_WAN_BACKEND
SHARE_STATE_FILE=$SHARE_STATE_FILE
SHARE_DIR=$SHARE_DIR
STATE_DIR=$STATE_DIR
SBIN_DIR=$SBIN_DIR
UNIT_DIR=$UNIT_DIR
KONTEYNER_BIRIM_DIR=$KONTEYNER_BIRIM_DIR
KONTEYNER_STATE_DIR=$KONTEYNER_STATE_DIR
KONTEYNER_LOCK=$KONTEYNER_LOCK
KONTEYNER_BAGLAMA_DIR=$KONTEYNER_BAGLAMA_DIR
KONTEYNER_NETWORK=$KONTEYNER_NETWORK
KONTEYNER_BRIDGE_PREFIX=$KONTEYNER_BRIDGE_PREFIX
KONTEYNER_NFT_TABLE=$KONTEYNER_NFT_TABLE
PACKAGE_OVERRIDES_DIR=$PACKAGE_OVERRIDES_DIR
DOWNLOADS_UID=$DOWNLOADS_UID
DOWNLOADS_GID=$DOWNLOADS_GID
FILES_PANEL_TRASH=$FILES_PANEL_TRASH
FILES_ARCHIVE_DIR=$FILES_ARCHIVE_DIR
CADDYFILE=$CADDYFILE
CADDY_MODULES_DIR=$CADDY_MODULES_DIR
VPN_BLOCK_DEST4="$VPN_BLOCK_DEST4"
VPN_BLOCK_DEST6="$VPN_BLOCK_DEST6"
DNSMASQ_CONF_DIR=$DNSMASQ_CONF_DIR
CONSOLE_WEB_DIR=$CONSOLE_WEB_DIR
RUNTIME_DIR=$RUNTIME_DIR
LOG_DIR=$LOG_DIR
GUNCELLEME_REPO=$GUNCELLEME_REPO
GUNCELLEME_DAL=$GUNCELLEME_DAL
GUNCELLEME_UNIT=$GUNCELLEME_UNIT
GUNCELLEME_DURUM_FILE=$GUNCELLEME_DURUM_FILE
GUNCELLEME_LOG_FILE=$GUNCELLEME_LOG_FILE
ONARIM_UNIT=$ONARIM_UNIT
ONARIM_DURUM_FILE=$ONARIM_DURUM_FILE
CONFIG_FILE=$CONFIG_FILE
SYSCTL_FORWARD_FILE=$SYSCTL_FORWARD_FILE
SYSCTL_NETBUF_FILE=$SYSCTL_NETBUF_FILE
SYSCTL_TCP_FILE=$SYSCTL_TCP_FILE
NET_BUF_FLOOR_BYTES=$NET_BUF_FLOOR_BYTES
OS_ID=$OS_ID
OS_CODENAME=$OS_CODENAME
OS_VERSION_ID=$OS_VERSION_ID
OS_ARCH=$OS_ARCH
KERNEL_RELEASE=$(uname -r)
EOF
}

# Kurulumun hangi OS üzerinde yapıldığını state.env'den okur. Kayıt eksikse
# sürüm değişimi iddia edilmez.
detect_os_change() {
    [[ -r "$STATE_FILE" ]] || return 0
    local prev_id prev_codename prev_version
    prev_id="$(awk -F= '/^OS_ID=/{print $2; exit}' "$STATE_FILE" || true)"
    prev_codename="$(awk -F= '/^OS_CODENAME=/{print $2; exit}' "$STATE_FILE" || true)"
    prev_version="$(awk -F= '/^OS_VERSION_ID=/{print $2; exit}' "$STATE_FILE" || true)"
    [[ -n "$prev_id" && -n "$prev_codename" ]] || return 0
    if [[ "$prev_id" == "$OS_ID" && "$prev_codename" == "$OS_CODENAME" &&
        "$prev_version" == "$OS_VERSION_ID" ]]; then
        return 0
    fi
    OS_CHANGED=1
    log WARN "işletim sistemi değişmiş: ${prev_id}/${prev_codename}/${prev_version:-yok} → ${OS_ID}/${OS_CODENAME}/${OS_VERSION_ID}"
    log WARN "OS'a bağlı adımlar (apt depoları, çekirdek modülleri, resolved, dnsmasq/Caddy, firewall) yeniden uygulanacak"
    FIREWALL_NEEDS_RESTART=1
}

write_config() {
    atomic_write "$CONFIG_FILE" 0600 <<EOF
LOCAL_DOMAIN=$LOCAL_DOMAIN
TIMEZONE=$TIMEZONE
EOF
}

detect_wan() {
    local route
    route="$(ip -4 -o route get 1.1.1.1)" || die "WAN rotası okunamadı"
    WAN_INTERFACE="$(awk '{for (i=1;i<=NF;i++) if ($i=="dev") {print $(i+1); exit}}' <<<"$route")"
    WAN_IPV4="$(awk '{for (i=1;i<=NF;i++) if ($i=="src") {print $(i+1); exit}}' <<<"$route")"
    [[ -n "$WAN_INTERFACE" && -n "$WAN_IPV4" ]] || die "WAN arayüzü/IPv4 tespit edilemedi"
    ip -4 -o addr show dev "$WAN_INTERFACE" | grep -q " $WAN_IPV4/" ||
        die "WAN_IPV4 ($WAN_IPV4) $WAN_INTERFACE üzerinde değil"
    # DD-138: IPv6 da sunucunun kendi yönlendirme tablosundan (paket gönderilmez, dış
    # site sorulmaz). Yoksa ya da WAN arayüzünde global adres değilse boş kalır.
    WAN_IPV6="$(ip -6 -o route get 2606:4700:4700::1111 2>/dev/null |
        awk '{for (i=1;i<=NF;i++) if ($i=="src") {print $(i+1); exit}}')" || WAN_IPV6=""
    if [[ -n "$WAN_IPV6" ]] &&
        ! ip -6 -o addr show dev "$WAN_INTERFACE" scope global | grep -q " $WAN_IPV6/"; then
        WAN_IPV6=""
    fi
}

detect_tailscale() {
    TAILSCALE_IPV4="$(
        ip -4 -o addr show dev "$TAILSCALE_IF" scope global |
            awk 'NR==1 {sub(/\/.*/,"",$4); print $4}'
    )"
    [[ "$TAILSCALE_IPV4" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] ||
        die "Tailscale IPv4 yok ($TAILSCALE_IF)"
    TAILSCALE_IPV6="$(
        ip -6 -o addr show dev "$TAILSCALE_IF" scope global |
            awk 'NR==1 {sub(/\/.*/,"",$4); print $4}'
    )" || TAILSCALE_IPV6=""
    if [[ -z "$TAILSCALE_IPV6" ]]; then
        log WARN "Tailscale IPv6 yok; devam (IPv4 zorunlu)"
    fi
}

tailscale_login_state() {
    local json state
    json="$(tailscale status --json 2>/dev/null)" || { printf 'unknown\n'; return 0; }
    state="$(
        jq -r '
            if (.BackendState == "Running" and .Self.Online == true and
                ((.Self.ID // "") | length) > 0 and
                ((.Self.TailscaleIPs // []) | length) > 0)
            then "complete"
            elif (.BackendState == "NeedsLogin" and .Self.Online != true and
                  (.Self.ID // "") == "" and
                  any(.Health[]?; contains("http 410: auth path not found")))
            then "auth_path_dead"
            else "pending" end
        ' <<<"$json" 2>/dev/null
    )" || state="unknown"
    printf '%s\n' "$state"
}

reap_bg_pid() {
    local pid="${1:?}" grace="${2:-10}" waited=0
    kill -0 "$pid" 2>/dev/null || {
        wait "$pid" 2>/dev/null || true
        return 0
    }
    kill "$pid" 2>/dev/null || true
    while kill -0 "$pid" 2>/dev/null && [[ "$waited" -lt "$grace" ]]; do
        sleep 1
        waited=$((waited + 1))
    done
    if kill -0 "$pid" 2>/dev/null; then
        kill -KILL "$pid" 2>/dev/null || true
    fi
    wait "$pid" 2>/dev/null || true
}

tailscale_login() {
    local attempt=1 max=3 out up_pid streamed total elapsed state dead_samples=0
    out="$(mktemp)"
    while [[ "$attempt" -le "$max" ]]; do
        : >"$out"
        streamed=0
        dead_samples=0
        log INFO "Tailscale giriş denemesi $attempt/$max"
        tailscale up --advertise-exit-node --ssh >"$out" 2>&1 &
        up_pid=$!
        elapsed=0
        while kill -0 "$up_pid" 2>/dev/null; do
            total="$(wc -l <"$out")"
            if [[ "$total" -gt "$streamed" ]]; then
                sed -n "$((streamed + 1)),${total}p" "$out" | tee -a "$V2_LOG_FILE"
                streamed="$total"
            fi
            state="$(tailscale_login_state)"
            if [[ "$state" == "complete" ]]; then
                wait "$up_pid" 2>/dev/null || true
                rm -f "$out"
                return 0
            fi
            if [[ "$state" == "auth_path_dead" ]]; then
                dead_samples=$((dead_samples + 1))
                [[ "$dead_samples" -ge 3 ]] && break
            else
                dead_samples=0
            fi
            elapsed=$((elapsed + 2))
            [[ "$elapsed" -ge 300 ]] && break
            sleep 2
        done
        reap_bg_pid "$up_pid" 10
        if [[ "$(tailscale_login_state)" == "complete" ]]; then
            rm -f "$out"
            return 0
        fi
        log WARN "Tailscale giriş başarısız/410; daemon sıfırlanıyor"
        systemctl restart --job-mode=ignore-dependencies tailscaled
        sleep 2
        attempt=$((attempt + 1))
    done
    rm -f "$out"
    die "Tailscale girişi tamamlanamadı"
}

# DD-124/DD-143: VPN ağlarının kaynağı sunucudaki kayıt ve wgN.conf dosyalarıdır.
# Yayıncı bu ID/codename için gerçekten bir suite yayınlamış mı? Yayınlamadıysa
# hata `apt-get update`in içinde, 3 deneme x APT_LOCK_TIMEOUT sonra ve sebebi
# gizleyen bir mesajla çıkardı. Ağ dalgalanmasında yanlış ölmemek için 3 deneme
# yapılır; hepsi başarısızsa sebep adıyla söylenir (DD-106).
assert_repo_suite() {
    local label="$1" url="$2" n=1
    while [[ "$n" -le 3 ]]; do
        curl -fs -I --max-time 15 "$url" >/dev/null 2>&1 && return 0
        n=$((n + 1))
        [[ "$n" -le 3 ]] && sleep 2
    done
    die "$label deposunda $OS_ID/$OS_CODENAME suite'i yok ($url) — yayıncı bu sürümü henüz yayınlamamış olabilir"
}

# Depo suite'i os-release'ten (require_supported_os → OS_ID/OS_CODENAME);
# Tailscale debian/ubuntu için aynı URL kalıbını yayınlar.
install_tailscale_repo() {
    # OS-DIVERGENCE: tailscale-repo-suite (debian+ubuntu) — depo suite'i ve
    # keyring URL'i os-release'ten türer; iki yayıncı da aynı kalıbı kullanır [DD-102]
    local keyring=/usr/share/keyrings/tailscale-archive-keyring.gpg
    assert_repo_suite "Tailscale" \
        "https://pkgs.tailscale.com/stable/${OS_ID}/dists/${OS_CODENAME}/Release"
    local tmp
    tmp="$(mktemp)"
    retry "tailscale-gpg" 3 60 -- \
        curl -fsSL "https://pkgs.tailscale.com/stable/${OS_ID}/${OS_CODENAME}.noarmor.gpg" -o "$tmp"
    # apt/sqv keyring'i _apt kullanıcısı olarak okur; 0600 Permission denied verir.
    install -m 0644 "$tmp" "$keyring"
    rm -f "$tmp"
    atomic_write /etc/apt/sources.list.d/tailscale.list 0644 <<EOF
deb [signed-by=/usr/share/keyrings/tailscale-archive-keyring.gpg] https://pkgs.tailscale.com/stable/$OS_ID $OS_CODENAME main
EOF
}

# firewall.sh ve tailscaled aynı netfilter arka ucunu kullanmak zorunda: betik kendi
# zincirini INPUT'ta ts-input'un arkasına sıralar. Alternatif legacy'ye alınmışsa betik
# başka bir tabloyu okur ve ts-input "yok" görünür — semptomu bildiren, sebebi gizleyen
# bir ölüm. Kapıyı koyup gerçek çareyi söylüyoruz (DD-106; Docker DD-152 ile gitti).
#
# İki çağrı yeri (DD-108): Ubuntu iptables'ı önyüklü getirir, Debian minimal
# getirmez — paketi aşama 1 kurar. Aşama 0'da binary yoksa denetlenecek bir
# yanlış yapılandırma da yoktur; kapı ertelenir. Aşama 1'den sonra zorunludur.
check_nft_iptables() {
    local required="${1:-optional}" bin ver missing=0
    for bin in iptables ip6tables; do
        ver="$("$bin" --version 2>/dev/null || true)"
        if [[ -z "$ver" ]]; then
            missing=1
            continue
        fi
        [[ "$ver" == *"nf_tables"* ]] ||
            die "$bin arka ucu nft değil ($ver); Tailscale ve güvenlik duvarı nft kullanır. Çare: update-alternatives --set $bin /usr/sbin/${bin}-nft"
    done
    [[ "$missing" -eq 1 ]] || return 0
    [[ "$required" != "required" ]] ||
        die "iptables/ip6tables bulunamadı (aşama 1 kurmuş olmalıydı)"
    log INFO "iptables henüz kurulu değil (Debian minimal); nft arka uç denetimi aşama 1'e ertelendi"
}

# DD-208: Podman tabanın parçasıdır (App Store'un konteyner çalışma ortamı). Daemon yok: Debian'ın
# podman.socket, podman.service ve podman-auto-update.timer birimleri kapalı gelir, kurulum açmaz.
# Aşama 1 kurar ve burada zorunlu denetler; aşama 7 yeniden denetler.
check_podman() {
    local out
    out="$(podman info --format '{{.Version.Version}} {{.Host.OCIRuntime.Name}}' 2>&1)" ||
        die "Podman çalışmıyor: ${out##*$'\n'}"
    [[ "$out" =~ ^[0-9]+\.[0-9]+ ]] || die "Podman sürümü okunamadı: $out"
    PODMAN_VERSION="${out%% *}"
}

stage_0() {
    log INFO "Aşama 0/7 — kapılar ve girdi"
    require_root
    require_supported_os
    log INFO "İşletim sistemi: ${OS_ID} ${OS_VERSION_ID} (${OS_CODENAME}) ${OS_ARCH}, çekirdek $(uname -r)"
    case "$OS_ARCH" in
        amd64) ;;
        arm64) log WARN "arm64: apt depoları ve imajlar bu mimariyi yayınlıyor ama canlı doğrulanmadı" ;;
        *) log WARN "beklenmeyen mimari ($OS_ARCH); yalnız amd64 canlı doğrulandı" ;;
    esac
    detect_os_change
    # OS-DIVERGENCE: netfilter-binaries (debian) — minimal Debian iptables'ı
    # getirmez; aşama 0 yalnız var olanı denetler, aşama 1 zorunlu kılar [DD-108]
    check_nft_iptables optional
    if [[ "$UPDATE_MODE" == 1 ]]; then
        log INFO "Konsol'dan güncelleme: sorular yok, onay Konsol'da verildi (DD-233)"
    else
        [[ -t 0 || -r /dev/tty ]] || die "etkileşimli TTY gerekli"
    fi
    # OS-DIVERGENCE: ufw-gate (pratikte ubuntu) — yoklama; paket yoksa no-op [DD-102]
    # Ubuntu server ufw ile gelir (varsayılan pasif). Aktifse INPUT'u ikinci
    # bir el yönetir ve MASTER-INPUT ile çelişir — fail-closed: önce kapat.
    if command -v ufw >/dev/null 2>&1 &&
        ufw status 2>/dev/null | grep -q '^Status: active'; then
        die "ufw aktif: INPUT politikası iki elden yönetilemez. Önce 'ufw disable' çalıştırın"
    fi
    acquire_lock "$RUNTIME_DIR/install.lock" "$LOCK_WAIT_SECONDS"
    [[ ! -f "$SETTINGS_PENDING_FILE" ]] ||
        die "Konsol'da bekleyen ayar işlemi var; Ayarlar'da onaylayın veya geri alın (geri alma takıldıysa: Yeniden dene ya da Bırak)"

    LOCAL_DOMAIN=""
    if [[ -r "$CONFIG_FILE" ]]; then
        # shellcheck source=/dev/null
        source "$CONFIG_FILE"
    fi

    # DD-228: alan adının varsayılanı yoktur. Sıra: Konsol'da onaylanmış ad (DD-157), önceki
    # kurulumun adı (config.env); ikisi de yoksa (ilk kurulum) sorulur. Sonradan Konsol →
    # Ayarlar'dan değişir. İlk kurulumda ayar dosyası yoktur; henüz Python gerekmez.
    local saved_domain="" domain_re='^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$'
    if [[ -f "$SETTINGS_FILE" ]]; then
        saved_domain="$(python3 "$V2_ROOT/panel/master_settings.py" saved-domain "$SETTINGS_FILE")" ||
            die "Konsol'daki alan adı kaydı okunamadı"
    fi
    if [[ -n "$saved_domain" ]]; then
        LOCAL_DOMAIN="$saved_domain"
        log INFO "alan adı Konsol'daki kayıttan: $LOCAL_DOMAIN"
    elif [[ -n "$LOCAL_DOMAIN" ]]; then
        log INFO "alan adı önceki kurulumdan: $LOCAL_DOMAIN (değiştirmek için Konsol → Ayarlar)"
    elif [[ "$UPDATE_MODE" == 1 ]]; then
        die "Konsol'dan güncelleme ilk kurulumu yapmaz (alan adı kaydı yok); kurulumu terminalden çalıştırın"
    else
        local reply
        while :; do
            read -r -p "Yerel alan adı (ör. ev; panel.<ad> olur): " reply </dev/tty ||
                die "alan adı okunamadı"
            [[ "$reply" =~ $domain_re ]] && break
            echo "geçersiz alan adı; küçük harf, rakam ve '-' kullanın (en çok 63 karakter)" >&2
        done
        LOCAL_DOMAIN="$reply"
    fi
    [[ "$LOCAL_DOMAIN" =~ ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$ ]] ||
        die "geçersiz alan adı: $LOCAL_DOMAIN"
    # DD-144: kullanıcı alanı sorulmaz. Kök defaults.env'de sabittir; indirme klasörü
    # ve kütüphane onun altındadır. Sabit yanlış düzenlenirse allowlist durdurur.
    [[ "$SERVER_ROOT" == /* && "$SERVER_ROOT" != */ ]] ||
        die "SERVER_ROOT mutlak ve sonu '/' olmayan bir yol olmalı: $SERVER_ROOT"
    [[ "$DOWNLOADS_SUBDIR" =~ ^[A-Za-z0-9._-]+$ && "$MEDIA_SUBDIR" =~ ^[A-Za-z0-9._-]+$ ]] ||
        die "DOWNLOADS_SUBDIR ve MEDIA_SUBDIR tek bir klasör adı olmalı"
    assert_downloads_path_allowed "$SERVER_ROOT"
    DOWNLOADS_PATH="$SERVER_ROOT/$DOWNLOADS_SUBDIR"

    # DD-143/201/203: hiçbir paket ayarı girdi ya da state değildir; her paket kendi ayarlarını
    # taşır (magaza/<id>/<id>.env) ve uç nokta olarak state'teki WAN_IPV4'ü kullanır.

    detect_wan

    # DD-147: Tailscale'e yalnız giriş bağlantısıyla katılınır; auth key girdisi yok.
    local ts_note="aşama 2'de giriş bağlantısı gösterilir; tarayıcıda onaylayın"
    if command -v tailscale >/dev/null 2>&1 && command -v jq >/dev/null 2>&1 &&
        [[ "$(tailscale_login_state)" == "complete" ]]; then
        ts_note="zaten online"
    elif [[ "$UPDATE_MODE" == 1 ]]; then
        die "Tailscale oturumu açık değil; giriş bağlantısı gerektiği için kurulumu terminalden çalıştırın"
    fi
    # DD-228: sistem her kurulumda (yeniden kurulum dahil) önce güncellenir.
    RUN_FULL_UPGRADE=1

    # Girdiler tek ekranda, parolasız; ilk yazımdan (config.env) önce tek onay.
    local yes_no_upgrade="evet" confirm_ans="h"
    cat <<EOF

Kurulum girdileri:
  Alan adı:      $LOCAL_DOMAIN
  Kullanıcı alanı: $SERVER_ROOT (sabit; indirmeler $DOWNLOADS_PATH)
  Yerleşik:     Dosyalar, klasör WebDAV paylaşımları, arşiv aracı ve Podman (konteyner ortamı)
  App Store:    $(paket_katalog_adlar); isteğe bağlı kurulur
  Konsol:        kullanıcı adı ve parolayla; Tailscale'den, isteğe bağlı internet HTTPS (DD-194, DD-195)
  Tailscale:     $ts_note
  full-upgrade:  $yes_no_upgrade

EOF
    if [[ "$UPDATE_MODE" == 1 ]]; then
        confirm_ans="E"
    else
        prompt confirm_ans "Bu değerlerle kurulum başlasın mı? (E/h)" "h"
    fi
    [[ "$confirm_ans" =~ ^[EeYy]$ ]] || die "kurulum iptal edildi; hiçbir ayar değiştirilmedi"

    write_config
}

# DD-113: dağıtımın güvenlik güncellemeleri kendiliğinden insin. Kaynak
# süzgeci paketin dağıtım varsayılanı (Debian: stable + security; Ubuntu:
# security). DD-184: Tailscale ve Caddy depoları da eklenir (dağıtımın
# listesine eklenir, yerine geçmez); güncelleme gece APT_UPGRADE_TIME'da.
# Reboot kararı operatörde; Ubuntu'da unattended-upgrades paketi imajla gelir.
apply_unattended_upgrades() {
    local timer_changed=0
    atomic_write "$APT_PERIODIC_FILE" 0644 <<EOF
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
    atomic_write "$APT_UNATTENDED_POLICY_FILE" 0644 <<EOF
// master-stack (DD-113): otomatik reboot yok; yeniden başlatma operatörün kararı.
Unattended-Upgrade::Automatic-Reboot "false";
// master-stack (DD-184): internete açık Tailscale ve Caddy de kendi depolarından güncellenir.
Unattended-Upgrade::Origins-Pattern {
        "$TAILSCALE_APT_ORIGIN";
        "$CADDY_APT_ORIGIN";
};
EOF
    install -d -m 0755 "${APT_UPGRADE_TIMER_DROPIN%/*}"
    atomic_write "$APT_UPGRADE_TIMER_DROPIN" 0644 <<EOF
# master-stack (DD-184): güncellemeler gece; boşta kalan zamanlama boot'ta telafi edilir.
[Timer]
OnCalendar=
OnCalendar=*-*-* $APT_UPGRADE_TIME
RandomizedDelaySec=30m
EOF
    [[ "${V2_LAST_ATOMIC_CHANGED:-0}" -eq 0 ]] || timer_changed=1
    systemctl daemon-reload
    systemctl enable --now apt-daily.timer apt-daily-upgrade.timer >/dev/null 2>&1 ||
        log WARN "apt-daily zamanlayıcıları etkinleştirilemedi"
    # Yeni saat, zamanlayıcı yeniden başlayınca geçerli olur.
    [[ "$timer_changed" -eq 0 ]] || systemctl restart apt-daily-upgrade.timer >/dev/null 2>&1 ||
        log WARN "apt-daily-upgrade zamanlayıcısı yeniden başlatılamadı"
}

# DD-166: distribution-signed RAR dependencies; preserve operator source files.
# OS-DIVERGENCE: rar-repository (debian/ubuntu) — non-free vs universe/multiverse [DD-166]
ensure_rar_repository() {
    local mirror security components keyring package candidate missing=0
    for package in unrar python3-rarfile; do
        candidate="$(LC_ALL=C apt-cache policy "$package" | awk '/Candidate:/ {value=$2} END {print value}')"
        [[ -n "$candidate" && "$candidate" != '(none)' ]] || missing=1
    done
    [[ "$missing" -eq 1 ]] || return 0
    case "$OS_ID" in
        debian)
            mirror="https://deb.debian.org/debian"; security="https://security.debian.org/debian-security"
            components="non-free"; keyring="/usr/share/keyrings/debian-archive-keyring.gpg"
            ;;
        ubuntu)
            mirror="https://archive.ubuntu.com/ubuntu"; security="https://security.ubuntu.com/ubuntu"
            case "$OS_ARCH" in amd64|i386) ;; *) mirror="https://ports.ubuntu.com/ubuntu-ports"; security="$mirror" ;; esac
            components="universe multiverse"; keyring="/usr/share/keyrings/ubuntu-archive-keyring.gpg"
            ;;
        *) die "RAR deposu için desteklenmeyen işletim sistemi" ;;
    esac
    [[ -f "$keyring" ]] || die "Dağıtım arşiv anahtarlığı bulunamadı: $keyring"
    log INFO "RAR desteği: resmi $OS_CODENAME $components deposu ekleniyor (unrar lisanslı/freeware)."
    atomic_write "$RAR_APT_SOURCE_FILE" 0644 <<EOF
# master-stack: RAR dependencies (DD-166); operator repositories are untouched.
deb [signed-by=$keyring] $mirror $OS_CODENAME $components
deb [signed-by=$keyring] $mirror $OS_CODENAME-updates $components
deb [signed-by=$keyring] $security $OS_CODENAME-security $components
EOF
    retry "apt-rar-update" 3 "$APT_LOCK_TIMEOUT" -- apt-get "${APT_OPTS[@]}" update
}

stage_1() {
    log INFO "Aşama 1/7 — sistem ve paketler"
    export DEBIAN_FRONTEND=noninteractive
    # OS-DIVERGENCE: needrestart-suspend (ubuntu) — env değişkeni; Debian'da
    # paket kurulu olmadığı için no-op [DD-103]
    # Ubuntu'da needrestart apt kancasıyla gelir ve "Ubuntu modunda" restart
    # kipini OTOMATİK'e ayarlar ($nrconf{restart}='a'); DEBIAN_FRONTEND bunu
    # kapatmaz. Kütüphane güncellemesinden sonra sshd/tailscaled/caddy/
    # dnsmasq'ı aşamaların ortasında yeniden başlatır —
    # ufw kapısının reddettiği "tek şeyin iki sahibi" sınıfının aynısı.
    # SUSPEND apt kancasınca okunur; Debian'da needrestart kurulu değil, no-op.
    export NEEDRESTART_SUSPEND=1
    retry "apt-update" 3 "$APT_LOCK_TIMEOUT" -- apt-get "${APT_OPTS[@]}" update
    ensure_rar_repository
    if [[ "$RUN_FULL_UPGRADE" -eq 1 ]]; then
        retry "apt-upgrade" 2 "$APT_LOCK_TIMEOUT" -- \
            apt-get "${APT_OPTS[@]}" -y -o Dpkg::Options::=--force-confdef \
                -o Dpkg::Options::=--force-confold full-upgrade
    fi
    # DD-153: yalnız temelin kullandıkları. gnupg (Caddy anahtarı artık .asc), gawk (v1'den
    # kalma; awk sistemin mawk'ı) ve apache2-utils (ortak htpasswd hesabı kaldırıldı) yok.
    retry "apt-base" 2 "$APT_LOCK_TIMEOUT" -- apt-get "${APT_OPTS[@]}" install -y \
        ca-certificates curl ethtool iproute2 procps kmod \
        iptables nftables coreutils util-linux diffutils jq \
        dnsutils unattended-upgrades python3 python3-rarfile unrar
    # Artık binary kesin var: arka uç denetimi burada zorunlu (DD-108).
    check_nft_iptables required
    # DD-208: konteyner çalışma ortamı, önerileri olmadan (buildah, criu, slirp4netns gelmez).
    # Netavark köprü/NAT kurallarını, master-firewall yalnız kendi giriş korumasını yönetir.
    retry "apt-podman" 2 "$APT_LOCK_TIMEOUT" -- apt-get "${APT_OPTS[@]}" install -y --no-install-recommends \
        podman netavark aardvark-dns
    check_podman
    timedatectl set-timezone "$TIMEZONE" || log WARN "saat dilimi ayarlanamadı"
    apply_unattended_upgrades
}

apply_udp_netbuf_floor() {
    # Legacy / DD-18: max(current, 16 MiB); asla düşürme. tailscaled socket
    # açılmadan önce yazılmalı (paket postinst daemon'ı başlatır).
    local current_rmem=0 current_wmem=0 target_rmem target_wmem
    current_rmem="$(sysctl -n net.core.rmem_max 2>/dev/null || echo 0)"
    current_wmem="$(sysctl -n net.core.wmem_max 2>/dev/null || echo 0)"
    [[ "$current_rmem" =~ ^[0-9]+$ ]] || current_rmem=0
    [[ "$current_wmem" =~ ^[0-9]+$ ]] || current_wmem=0
    target_rmem="$NET_BUF_FLOOR_BYTES"
    target_wmem="$NET_BUF_FLOOR_BYTES"
    if (( current_rmem > target_rmem )); then
        target_rmem="$current_rmem"
    fi
    if (( current_wmem > target_wmem )); then
        target_wmem="$current_wmem"
    fi
    atomic_write "$SYSCTL_NETBUF_FILE" 0644 <<EOF
net.core.rmem_max = $target_rmem
net.core.wmem_max = $target_wmem
EOF
    sysctl -p "$SYSCTL_NETBUF_FILE" >/dev/null
    log INFO "UDP netbuf floor: rmem_max=$target_rmem wmem_max=$target_wmem"
}

# TCP tıkanıklık denetimi (DD-111). Yalnız bu host'ta SONLANAN TCP'yi etkiler:
# Caddy'nin Infuse'a WebDAV akışı, uygulamaların indirmeleri, arayüzler.
# Exit-node üzerinden yönlendirilen akışların denetimi uç noktalardadır;
# router'ın ayarı onlara dokunmaz. tcp_bbr Ubuntu 26.04 çekirdeğinde modül
# olarak doğrulandı; Debian 13 için beklenir ama doğrulanmadı. Yüklenemezse
# kurulum durmaz, varsayılanda kalır — bir kapı yalnız host'un sahip olduğunu
# doğrulayabilir (DD-108).
apply_tcp_congestion_control() {
    if ! modprobe "tcp_${TCP_CONGESTION_CONTROL}" 2>/dev/null; then
        log INFO "tcp_${TCP_CONGESTION_CONTROL} yüklenemedi; varsayılan tıkanıklık denetimi korunuyor ($(sysctl -n net.ipv4.tcp_congestion_control 2>/dev/null))"
        return 0
    fi
    atomic_write "$TCP_MODULES_LOAD_FILE" 0644 <<EOF
tcp_${TCP_CONGESTION_CONTROL}
EOF
    atomic_write "$SYSCTL_TCP_FILE" 0644 <<EOF
net.core.default_qdisc = $TCP_DEFAULT_QDISC
net.ipv4.tcp_congestion_control = $TCP_CONGESTION_CONTROL
EOF
    if ! sysctl -p "$SYSCTL_TCP_FILE" >/dev/null 2>&1; then
        log WARN "TCP ayarları uygulanamadı ($SYSCTL_TCP_FILE); varsayılan korunuyor"
        return 0
    fi
    log INFO "TCP: congestion_control=$(sysctl -n net.ipv4.tcp_congestion_control) default_qdisc=$(sysctl -n net.core.default_qdisc)"
}

stage_2() {
    log INFO "Aşama 2/7 — Tailscale"
    install_tailscale_repo
    if [[ "${V2_LAST_ATOMIC_CHANGED:-0}" -eq 1 || "$OS_CHANGED" -eq 1 ]]; then
        retry "apt-update-ts" 3 "$APT_LOCK_TIMEOUT" -- apt-get "${APT_OPTS[@]}" update
    else
        log INFO "tailscale.list aynı; apt-get update atlandı (stage_1 zaten günceldi)"
    fi
    # M11/DD-18: buffer tabanı paket kurulumundan önce
    apply_udp_netbuf_floor
    # DD-111: default_qdisc tailscale0 oluşmadan önce yazılsın (taze kurulumda)
    apply_tcp_congestion_control
    retry "apt-tailscale" 2 "$APT_LOCK_TIMEOUT" -- apt-get "${APT_OPTS[@]}" install -y tailscale
    systemctl enable --now tailscaled

    # Forwarding ayrı dosyada; rmem/wmem yalnız netbuf conf'ta (DD-18).
    atomic_write "$SYSCTL_FORWARD_FILE" 0644 <<'EOF'
net.ipv4.ip_forward = 1
net.ipv6.conf.all.forwarding = 1
EOF
    sysctl -p "$SYSCTL_FORWARD_FILE" >/dev/null || true
    install -m 0755 "$V2_ROOT/scripts/tailscale-udp-gro" "$SBIN_DIR/tailscale-udp-gro"
    install -m 0644 "$V2_ROOT/systemd/tailscale-udp-gro.service" \
        "$UNIT_DIR/tailscale-udp-gro.service"
    systemctl daemon-reload
    systemctl enable --now tailscale-udp-gro.service ||
        log WARN "tailscale-udp-gro başlatılamadı"

    if [[ "$(tailscale_login_state)" != "complete" ]]; then
        tailscale_login
    else
        log INFO "Tailscale zaten online"
    fi
    tailscale set --advertise-exit-node --ssh=true \
        --stateful-filtering=true --netfilter-mode=on --snat-subnet-routes=true

    local deadline=$((SECONDS + TS_ONLINE_DEADLINE_SECONDS))
    while [[ "$(tailscale_login_state)" != "complete" ]]; do
        [[ "$SECONDS" -lt "$deadline" ]] || die "Tailscale online olmadı"
        sleep 2
    done
}

ensure_downloads_tree() {
    local root="$1" uid="$2" gid="$3"
    [[ -d "$root" ]] || die "downloads dizini yok: $root"
    # No pathname-based chown/chmod of service-writable data. Keep one selective
    # descriptor walk; links/special files and private work areas stay untouched.
    python3 "$V2_ROOT/panel/master_permissions.py" "$root" "$uid" "$gid" \
        "${FILES_ARCHIVE_DIR:-.arsiv}" "${SHARE_DIR:-.pay}"
}

# Recursive chown/chmod only under an allowlisted data root (DD-93).
assert_downloads_path_allowed() {
    local p="$1"
    case "$p" in
        / | /etc | /etc/* | /usr | /usr/* | /bin | /bin/* | /sbin | /sbin/* | \
        /boot | /boot/* | /dev | /dev/* | /proc | /proc/* | /sys | /sys/* | \
        /run | /run/* | /root | /root/* | /var | /var/* | /tmp | /tmp/* | \
        /home | /home/* | /lib | /lib/* | /lib64 | /lib64/* | /opt | /opt/* | \
        /media | /media/* | /mnt | /mnt/* )
            die "kullanıcı alanı sistem dizininde olamaz: $p"
            ;;
    esac
    # DD-144: /srv FHS'te zaten "bu sistemin sunduğu veri" dizini ve Debian paketleri
    # oraya dosya koyamaz; kullanıcı alanının yeri orası.
    case "$p" in
        /srv | /srv/* | /data | /data/* )
            return 0
            ;;
        *)
            die "kullanıcı alanı allowlist dışı (/srv, /data): $p"
            ;;
    esac
}

# DD-148: modüllerin dosyaları. Kurulum her modülün şablonunu yer tutucuları doldurarak
# MODULES_DIR/<id>/ altına yazar ve kayıt dosyasını (yoksa boş) oluşturur; hiçbir modülü
# isteğe bağlı uygulamayı kendiliğinden kurmaz ya da kaldırmaz. Aşama 7 yerleşik
# Dosyalar/WebDAV'ı doğrular; kurulu isteğe bağlı uygulamaların değişen dosyalarını uygular.
MODULES_CHANGED=""
PANEL_HELPERS_CHANGED=0
# DD-235: master-files-panel değişince Sistem görünümünün servisi de yeniden başlar.
FILES_PANEL_SCRIPT_CHANGED=0
module_state() { # ID → calisiyor | durduruldu | (boş: kurulu değil)
    awk -F'\t' -v i="$1" '$1 == i {print $2; exit}' "$MODULES_FILE" 2>/dev/null || true
}
# DD-222: MODULES_CHANGED yalnız bu çalıştırmanın belleğindedir. Değişiklik yazılır yazılmaz paket
# kalıcı olarak işaretlenir; işaret yalnız paket uygulanınca (reapply_modules) kalkar. Aşama 4'ten
# sonra düşen bir kurulumun değişikliğini böylece bir sonraki kurulum yine uygular. İşaret
# yazılamazsa kurulum durur (çağıran bir koşulun içinde olsa da: die).
mark_module_pending() { # ID
    local dir="${MODULES_PENDING_DIR:?}"
    [[ -d "$dir" ]] || install -d -m 0700 -o root -g root "$dir" || die "bekleyen paket klasörü açılamadı: $dir"
    : >"$dir/$1" || die "bekleyen paket işareti yazılamadı: $dir/$1"
}
# DD-197: bir paketin repo klasörü olduğu gibi işlenir. __KEY__ içeren dosya şablondur ve
# kurulumun aynı adlı değişkeniyle doldurulur; öbürleri kopyalanır. Çalıştırılabilir dosyalar
# (araçlar) 0755, geri kalanı 0644. 0: bir dosya değişti, 1: hepsi aynıydı.
# DD-203: paketin kendi ayar dosyası (magaza/<id>/<id>.env, KEY=değer; `source` edilmez).
paket_ayar_oku() { # ID ANAHTAR → değer (yoksa boş)
    local file="$V2_ROOT/magaza/$1/$1.env" override
    override="$(python3 - "$V2_ROOT/panel" "$V2_ROOT/magaza" "$PACKAGE_OVERRIDES_DIR" "$1" "$2" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
from master_settings import package_overrides
print(package_overrides({'MODULES_DIR': sys.argv[2], 'PACKAGE_OVERRIDES_DIR': sys.argv[3]}, sys.argv[4]).get(sys.argv[5], ''))
PY
)" || return 1
    if [[ -n "$override" ]]; then printf '%s\n' "$override"; return; fi
    [[ -f "$file" ]] || return 0
    sed -n "s/^$2=\"\{0,1\}\([^\"]*\)\"\{0,1\}\$/\1/p" "$file" | head -n 1
}

paket_islenmis_oku() { # ID ANAHTAR → işlenmiş bildirimden (MODULES_DIR) değer
    sed -n "s/^$2=\"\{0,1\}\([^\"]*\)\"\{0,1\}\$/\1/p" "$MODULES_DIR/$1/paket.env" 2>/dev/null | head -n 1
}

# DD-203: paketlerin yazdığı klasörler (işlenmiş bildirimlerdeki PAKET_KLASORLER, mutlak yol), dosya
# arka ucuna köke göre "yol=sahip;..." olarak verilir: Dosyalar seçtirmez, paylaştırmaz, sahibini söyler.
paket_korunan_klasorler() {
    local manifest id ad p out=""
    for manifest in "$MODULES_DIR"/*/paket.env; do
        [[ -f "$manifest" ]] || continue
        id="${manifest%/paket.env}"; id="${id##*/}"
        ad="$(paket_islenmis_oku "$id" PAKET_AD)"; [[ -n "$ad" ]] || ad="$id"
        for p in $(paket_islenmis_oku "$id" PAKET_KLASORLER); do
            [[ "$p" == "$SERVER_ROOT/"* ]] || continue
            out="${out:+$out;}${p#"$SERVER_ROOT"/}=$ad"
        done
    done
    printf '%s' "$out"
}

# DD-203: root arka ucun yazabileceği yollar paketlerin bildiriminden (PAKET_ARKAUC_YOLLAR, mutlak);
# kurulu olsun olmasın '-' ile verilir (yoksa atlanır), böylece bir kurulum birimi yeniden başlatmaz.
paket_arkauc_klasorler() { # bir satıra bir mutlak yol, katalog sırasıyla
    local manifest id p
    for manifest in "$MODULES_DIR"/*/paket.env; do
        [[ -f "$manifest" ]] || continue
        id="${manifest%/paket.env}"; id="${id##*/}"
        for p in $(paket_islenmis_oku "$id" PAKET_ARKAUC_YOLLAR); do
            [[ "$p" == /* ]] || continue
            printf '%s\n' "$p"
        done
    done
    return 0
}

paket_arkauc_yollar() {
    local p out=""
    while IFS= read -r p; do
        out="${out:+$out }-$p"
    done < <(paket_arkauc_klasorler)
    printf '%s' "$out"
}

# DD-207: systemd, ReadWritePaths'te "-" ile yazılan bir klasörü arka uç başlarken yoksa atlar; klasör
# sonradan oluşsa da (ör. WireGuard'ın ilk ağı) arka ucun gördüğü kopya salt okunur kalır. Çalışan
# arka ucun bağlamalarında her bildirilen klasör yazılabilir (rw) bir bağlama noktası olmalı.
panel_yollari_bagli() { # [MOUNTINFO]
    local pid info p
    pid="$(systemctl show -p MainPID --value master-panel.service 2>/dev/null || true)"
    [[ "$pid" =~ ^[1-9][0-9]*$ ]] || return 1
    info="${1:-/proc/$pid/mountinfo}"
    while IFS= read -r p; do
        awk -v p="$p" '$5 == p && $6 ~ /(^|,)rw(,|$)/ {f = 1} END {exit !f}' "$info" 2>/dev/null || return 1
    done < <(paket_arkauc_klasorler)
}

# Kataloğun adları ("A ve B"), özetler için.
paket_katalog_adlar() {
    local id names=() n
    for id in $(paket_katalog); do names+=("$(paket_bildirim_oku "$id" PAKET_AD)"); done
    n=${#names[@]}
    case "$n" in
        0) printf 'yok' ;;
        1) printf '%s' "${names[0]}" ;;
        *) printf '%s ve %s' "$(IFS=,; printf '%s' "${names[*]:0:n-1}" | sed 's/,/, /g')" "${names[n-1]}" ;;
    esac
}

render_package_dir() { # ID
    local id="$1" src dst name mode changed=0 key value
    local -a args
    install -d -m 0755 -o root -g root "$MODULES_DIR/$id"
    for src in "$V2_ROOT/magaza/$id"/*; do
        [[ -f "$src" ]] || continue
        name="${src##*/}"
        dst="$MODULES_DIR/$id/$name"
        mode=0644
        [[ ! -x "$src" ]] || mode=0755
        args=()
        while IFS= read -r key; do
            [[ -n "$key" ]] || continue
            # DD-203: paketin kendi ayarı (magaza/<id>/<id>.env) önce, kurulumun değişkeni sonra.
            value="$(paket_ayar_oku "$id" "$key")"
            if [[ -n "$value" ]]; then
                args+=("$key=$value")
            elif [[ -n "${!key+x}" ]]; then
                args+=("$key=${!key}")
            else
                die "paket dosyasında tanımsız yer tutucu: __${key}__ ($src)"
            fi
        done < <(grep -oE '__[A-Z][A-Z0-9_]*__' "$src" | sort -u | sed 's/^__//; s/__$//')
        if [[ ${#args[@]} -gt 0 ]]; then
            render_template "$src" "$dst" "$mode" "${args[@]}"
        else
            atomic_write "$dst" "$mode" <"$src"
        fi
        # DD-222: işaret ilk değişiklikte, paketin kalan dosyalarından önce konur.
        [[ "${V2_LAST_ATOMIC_CHANGED:-0}" -eq 0 ]] || { changed=1; mark_module_pending "$id"; }
    done
    # DD-203: işlenmiş klasörde yalnız paketin dosyaları durur; eski sürümlerin bıraktıkları
    # (ör. önceki sürümlerin yazdığı __pycache__) kalkar.
    for dst in "$MODULES_DIR/$id"/* "$MODULES_DIR/$id"/.[!.]*; do
        [[ -e "$dst" || -L "$dst" ]] || continue
        name="${dst##*/}"
        [[ -f "$V2_ROOT/magaza/$id/$name" ]] || { mark_module_pending "$id"; rm -rf -- "$dst"; changed=1; }
    done
    [[ "$changed" -eq 1 ]]
}

paket_bildirim_oku() { # ID ANAHTAR → değer (repo bildirimi; `source` edilmez)
    sed -n "s/^$2=\"\{0,1\}\([^\"]*\)\"\{0,1\}\$/\1/p" "$V2_ROOT/magaza/$1/paket.env" | head -n 1
}

# Katalog sırası: yerleşik olmayan paketler, PAKET_SIRA'ya göre.
paket_katalog() {
    local dir id
    for dir in "$V2_ROOT"/magaza/*/; do
        id="${dir%/}"; id="${id##*/}"
        [[ -f "$dir/paket.env" ]] || continue
        [[ "$(paket_bildirim_oku "$id" PAKET_YERLESIK)" == 1 ]] && continue
        printf '%s\t%s\n' "$(paket_bildirim_oku "$id" PAKET_SIRA)" "$id"
    done | sort -n | cut -f2 | tr '\n' ' '
}

# DD-201: kurulu paketin kendi doğrulaması (paket_denetle). Kanca alt kabukta, kurulumun
# değişkenleriyle çalışır; hatada açıklamayı stderr'e yazıp sıfır dışı döner.
paket_denetle_calistir() { # ID
    local id="$1" out
    [[ -f "$V2_ROOT/magaza/$id/kanca" ]] || return 0
    # shellcheck source=/dev/null
    out="$( ( source "$V2_ROOT/magaza/$id/kanca" && { ! declare -F paket_denetle >/dev/null 2>&1 || paket_denetle; } ) 2>&1 )" ||
        die "$(paket_bildirim_oku "$id" PAKET_AD): ${out##*$'\n'}"
}

# DD-201: kurulu olmayan paketin bildirdiği araçlar, birim ekleri ve konteyner birimi (DD-209)
# sunucuda yoksa 0.
paket_iz_yok() { # ID
    local id="$1" name pair
    for name in $(paket_bildirim_oku "$id" PAKET_ARACLAR); do
        [[ ! -e "$SBIN_DIR/$name" ]] || return 1
    done
    for pair in $(paket_bildirim_oku "$id" PAKET_EKLER); do
        [[ ! -e "$UNIT_DIR/${pair#*:}" ]] || return 1
    done
    name="$(paket_bildirim_oku "$id" PAKET_KONTEYNER)"
    [[ -z "$name" || ! -e "$KONTEYNER_BIRIM_DIR/$name" ]] || return 1
    return 0
}

ensure_module_files() {
    local dir id
    install -d -m 0755 -o root -g root "$MODULES_DIR"
    # Her paket (yerleşik WebDAV dahil) MODULES_DIR/<id>/ altına işlenir; canlı kopyaları
    # master-modul koyar, kullanıcı kayıtları yeniden üretilmez (DD-158). Değişen, uygulanmayı
    # bekleyen (DD-222: bu ya da yarıda kalmış önceki bir kurulumdan) ya da her kurulumda uygulanan
    # (PAKET_UYGULA_HEP=1) paket MODULES_CHANGED'e girer.
    for dir in "$V2_ROOT"/magaza/*/; do
        id="${dir%/}"; id="${id##*/}"
        [[ -f "$dir/paket.env" ]] || die "paket bildirimi yok: $dir"
        if render_package_dir "$id" || [[ -e "$MODULES_PENDING_DIR/$id" ]] ||
            [[ "$(paket_bildirim_oku "$id" PAKET_UYGULA_HEP)" == 1 ]]; then
            MODULES_CHANGED="$MODULES_CHANGED $id"
        fi
    done
    if [[ ! -f "$MODULES_FILE" ]]; then
        atomic_write "$MODULES_FILE" 0644 </dev/null
    fi
    chown root:root "$MODULES_FILE"
    chmod 0644 "$MODULES_FILE"
}

# DD-148/DD-149: dosyası değişen kurulu modül yeniden uygulanır (adları, hesabı; çalışıyorsa
# servisi). Durdurulmuş modül durur, kurulmamış modüle dokunulmaz, hiçbiri kaldırılmaz.
# DD-222: bekleyen işaret yalnız uygulama başarılıysa kalkar. Yerleşikleri aşama 7'nin başında
# master-modul yerlesik uyguladı (başarısızsa kurulum orada durur); kurulu olmayan paketi Konsol
# kurarken işlenmiş dosyalarıyla koyar, bekleyecek bir şey kalmaz.
reapply_modules() {
    local id state
    for id in $MODULES_CHANGED; do
        if [[ "$id" == dosya || "$id" == paylasim ]]; then rm -f -- "${MODULES_PENDING_DIR:?}/$id"; continue; fi
        state="$(module_state "$id")"
        [[ "$state" == calisiyor || "$state" == durduruldu ]] || { rm -f -- "${MODULES_PENDING_DIR:?}/$id"; continue; }
        if [[ "$(sed -n 's/^PAKET_UYGULA_HEP=//p' "$V2_ROOT/magaza/$id/paket.env" 2>/dev/null)" == 1 ]]; then
            log INFO "Modül $id: yeniden uygulanıyor (her kurulumda: $(sed -n 's/^PAKET_UYGULA_NEDEN="\(.*\)"$/\1/p' "$V2_ROOT/magaza/$id/paket.env" 2>/dev/null))"
        else
            log INFO "Modül $id: dosyası değişti, yeniden uygulanıyor"
        fi
        if "$SBIN_DIR/master-modul" uygula "$id" >/dev/null; then
            rm -f -- "${MODULES_PENDING_DIR:?}/$id"
        else
            log WARN "Uygulama $id yeniden uygulanamadı; bir sonraki kurulum yeniden dener. Konsol → App Store'dan bakın"
        fi
    done
    # DD-196/201: kurulu olmayan bir paketin bildirdiği araç ya da birim eki sunucuda durmaz
    # (önceki sürümlerin bıraktıkları dahil). Paket verisi kalır; kaldir --veri siler.
    local pkg name pair dst pruned
    for pkg in $(paket_katalog); do
        [[ -z "$(module_state "$pkg")" ]] || continue
        pruned=0
        for name in $(paket_bildirim_oku "$pkg" PAKET_ARACLAR); do
            [[ ! -e "$SBIN_DIR/$name" ]] || { rm -f -- "$SBIN_DIR/$name"; pruned=1; }
        done
        for pair in $(paket_bildirim_oku "$pkg" PAKET_EKLER); do
            dst="$UNIT_DIR/${pair#*:}"
            [[ ! -e "$dst" ]] || { rm -f -- "$dst"; rmdir -- "$(dirname -- "$dst")" 2>/dev/null || true; pruned=1; }
        done
        name="$(paket_bildirim_oku "$pkg" PAKET_KONTEYNER)"
        [[ -z "$name" || ! -e "$KONTEYNER_BIRIM_DIR/$name" ]] || { rm -f -- "$KONTEYNER_BIRIM_DIR/$name"; pruned=1; }
        [[ "$pruned" -eq 0 ]] || {
            systemctl daemon-reload
            log INFO "$(paket_bildirim_oku "$pkg" PAKET_AD) kurulu değil; aracı ve birim eki sunucudan kaldırıldı"
        }
    done
}

stage_3() {
    log INFO "Aşama 3/7 — adresler ve dizinler"
    detect_wan
    detect_tailscale
    write_state
    [[ "${V2_LAST_ATOMIC_CHANGED:-0}" -eq 1 ]] && FIREWALL_NEEDS_RESTART=1

    local d
    # DD-144/171: downloads, media and trash are siblings. No legacy share tree.
    for d in \
        "$SERVER_ROOT" \
        "$DOWNLOADS_PATH" \
        "$SERVER_ROOT/$MEDIA_SUBDIR" \
        "$SERVER_ROOT/$MEDIA_SUBDIR/movies" \
        "$SERVER_ROOT/$MEDIA_SUBDIR/series" \
        "$SERVER_ROOT/$FILES_PANEL_TRASH"; do
        python3 "$V2_ROOT/panel/master_permissions.py" --mkdir "$d" "$DOWNLOADS_UID" "$DOWNLOADS_GID"
    done
    local fixed
    fixed="$(ensure_downloads_tree "$SERVER_ROOT" "$DOWNLOADS_UID" "$DOWNLOADS_GID")"
    if [[ "$fixed" -gt 0 ]]; then
        log INFO "Downloads: $fixed girdinin sahibi ya da izni düzeltildi (${DOWNLOADS_UID}:${DOWNLOADS_GID}; indirme hesabı R/W)"
    else
        log INFO "Downloads sahipliği ve izinleri yerinde (${DOWNLOADS_UID}:${DOWNLOADS_GID})"
    fi
}

stage_4() {
    log INFO "Aşama 4/7 — betikler ve şablonlar"
    # DD-152: Docker yok; modüller sunucuda systemd servisi olarak çalışır.
    atomic_write "$SBIN_DIR/master-modul" 0755 <"$V2_ROOT/scripts/master-modul"
    atomic_write "$SBIN_DIR/master_settings.py" 0755 <"$V2_ROOT/panel/master_settings.py"
    if [[ "${V2_LAST_ATOMIC_CHANGED:-0}" -eq 1 ]]; then
        PANEL_HELPERS_CHANGED=1
        FIREWALL_NEEDS_RESTART=1
    fi
    atomic_write "$SBIN_DIR/master_shares.py" 0755 <"$V2_ROOT/panel/master_shares.py"
    [[ "${V2_LAST_ATOMIC_CHANGED:-0}" -eq 0 ]] || PANEL_HELPERS_CHANGED=1
    # DD-222: WebDAV'ın araçları değişince paylasim işaretlenir; ensure_module_files onu MODULES_CHANGED'e alır.
    [[ "${V2_LAST_ATOMIC_CHANGED:-0}" -eq 0 ]] || mark_module_pending paylasim
    atomic_write "$SBIN_DIR/master_https.py" 0755 <"$V2_ROOT/panel/master_https.py"
    [[ "${V2_LAST_ATOMIC_CHANGED:-0}" -eq 0 ]] || PANEL_HELPERS_CHANGED=1
    atomic_write "$SBIN_DIR/master_publications.py" 0755 <"$V2_ROOT/panel/master_publications.py"
    [[ "${V2_LAST_ATOMIC_CHANGED:-0}" -eq 0 ]] || PANEL_HELPERS_CHANGED=1
    # DD-194: Konsol hesabı/oturumları; master-konsol root CLI'si aynı modülü çalıştırır.
    atomic_write "$SBIN_DIR/master_auth.py" 0755 <"$V2_ROOT/panel/master_auth.py"
    [[ "${V2_LAST_ATOMIC_CHANGED:-0}" -eq 0 ]] || PANEL_HELPERS_CHANGED=1
    # DD-233: Konsol'un "Güncelle" düğmesi: sürüm denetimi (arka uç) ve işi yürüten root aracı.
    atomic_write "$SBIN_DIR/master_update.py" 0755 <"$V2_ROOT/panel/master_update.py"
    [[ "${V2_LAST_ATOMIC_CHANGED:-0}" -eq 0 ]] || PANEL_HELPERS_CHANGED=1
    atomic_write "$SBIN_DIR/master-guncelle" 0755 <"$V2_ROOT/scripts/master-guncelle"
    # DD-239: denetle ve onar (Konsol'un Sağlık kartı ve SSH: sudo master-onar).
    atomic_write "$SBIN_DIR/master_onar.py" 0755 <"$V2_ROOT/panel/master_onar.py"
    atomic_write "$SBIN_DIR/master-onar" 0755 <"$V2_ROOT/scripts/master-onar"
    # Konteyner okuma/yönetim araçları. Yazma çalışanı backend sandbox'ının dışında çalışır.
    atomic_write "$SBIN_DIR/master_containers.py" 0755 <"$V2_ROOT/panel/master_containers.py"
    [[ "${V2_LAST_ATOMIC_CHANGED:-0}" -eq 0 ]] || PANEL_HELPERS_CHANGED=1
    local container_helper
    for container_helper in master_container_config master_container_network master_container_worker master_container_manager; do
        atomic_write "$SBIN_DIR/$container_helper.py" 0755 <"$V2_ROOT/panel/$container_helper.py"
        if [[ "${V2_LAST_ATOMIC_CHANGED:-0}" -eq 1 ]]; then
            PANEL_HELPERS_CHANGED=1
            FIREWALL_NEEDS_RESTART=1
        fi
    done
    # DD-226: Konsol konteynerinin birimi her açılışta bağlanan klasörlerini bununla sabitler.
    atomic_write "$SBIN_DIR/master_container_binds.py" 0755 <"$V2_ROOT/panel/master_container_binds.py"
    install -d -m 0700 "$KONTEYNER_STATE_DIR" "$PACKAGE_OVERRIDES_DIR"
    atomic_write "$SBIN_DIR/master-konsol" 0755 <"$V2_ROOT/scripts/master-konsol"
    atomic_write "$SBIN_DIR/master_webdav.py" 0755 <"$V2_ROOT/panel/master_webdav.py"
    [[ "${V2_LAST_ATOMIC_CHANGED:-0}" -eq 0 ]] || mark_module_pending paylasim
    render_template "$V2_ROOT/systemd/master-settings-guard.service" "$UNIT_DIR/master-settings-guard.service" 0644 \
        SBIN_DIR="$SBIN_DIR" STATE_FILE="$STATE_FILE"
    atomic_write "$UNIT_DIR/master-settings-guard.timer" 0644 <"$V2_ROOT/systemd/master-settings-guard.timer"
    render_template "$V2_ROOT/systemd/master-share-network.service" "$UNIT_DIR/master-share-network.service" 0644 \
        SBIN_DIR="$SBIN_DIR" STATE_FILE="$STATE_FILE"
    atomic_write "$UNIT_DIR/master-share-network.timer" 0644 <"$V2_ROOT/systemd/master-share-network.timer"
    ensure_module_files
    atomic_write "$SBIN_DIR/master-firewall" 0755 <"$V2_ROOT/scripts/firewall.sh"
    [[ "${V2_LAST_ATOMIC_CHANGED:-0}" -eq 1 ]] && FIREWALL_NEEDS_RESTART=1
    atomic_write "$SBIN_DIR/refresh-tailnet-config" 0755 \
        <"$V2_ROOT/scripts/refresh-tailnet-config"
    atomic_write "$SBIN_DIR/wait-tailnet-addr" 0755 \
        <"$V2_ROOT/scripts/wait-tailnet-addr"

    atomic_write "$UNIT_DIR/master-firewall.service" 0644 \
        <"$V2_ROOT/systemd/master-firewall.service"
    [[ "${V2_LAST_ATOMIC_CHANGED:-0}" -eq 1 ]] && FIREWALL_NEEDS_RESTART=1
    atomic_write "$UNIT_DIR/refresh-tailnet-config.service" 0644 \
        <"$V2_ROOT/systemd/refresh-tailnet-config.service"
    atomic_write "$UNIT_DIR/refresh-tailnet-config.timer" 0644 \
        <"$V2_ROOT/systemd/refresh-tailnet-config.timer"
    render_template "$V2_ROOT/systemd/master-duvar-denetim.service" "$UNIT_DIR/master-duvar-denetim.service" 0644 \
        SBIN_DIR="$SBIN_DIR" STATE_FILE="$STATE_FILE"
    atomic_write "$UNIT_DIR/master-duvar-denetim.timer" 0644 <"$V2_ROOT/systemd/master-duvar-denetim.timer"
    systemctl daemon-reload
    systemctl enable --now master-settings-guard.timer
}

stage_5() {
    log INFO "Aşama 5/7 — firewall"

    systemctl enable master-firewall.service
    systemctl enable refresh-tailnet-config.service
    # DD-239/DD-240: after boot and nightly 03-04 (no 5-minute loop); the firewall keeps an hourly check.
    systemctl enable --now refresh-tailnet-config.timer
    systemctl enable --now master-duvar-denetim.timer

    if [[ "$FIREWALL_NEEDS_RESTART" -eq 1 ]] ||
        ! systemctl is-active --quiet master-firewall.service; then
        systemctl reset-failed master-firewall.service 2>/dev/null || true
        systemctl restart master-firewall.service
    else
        log INFO "firewall yapılandırması aynı; yeniden başlatılmadı"
    fi
    # DD-150: VPN katmanı (paketler, çekirdek modülü, ağların açılması) VPN paketindedir;
    # kurulu değilse güvenlik duvarı hiçbir VPN portu açmaz.
}

# retry fonksiyonu export -f + bash -c ile ayrı süreçte çalıştırır; diziler
# oraya geçmez. APT_OPTS bu yüzden çağırandan argüman olarak gelir (DD-125).
apt_get_install_masked_quiet() {
    local tmp rc=0 line
    tmp="$(mktemp)"
    set +e
    apt-get install -y "$@" >"$tmp" 2>&1
    rc=$?
    set -e
    if [[ -n "${V2_LOG_FILE:-}" ]]; then
        cat "$tmp" >>"$V2_LOG_FILE" 2>/dev/null || true
    fi
    while IFS= read -r line || [[ -n "$line" ]]; do
        if [[ "$line" == *"Failed to preset unit: Unit "* && "$line" == *" is masked" ]] ||
            [[ "$line" == *"deb-systemd-helper: error: systemctl preset failed"* ]] ||
            [[ "$line" == *".service is a disabled or a static unit"* ]]; then
            continue
        fi
        printf '%s\n' "$line"
    done <"$tmp"
    rm -f "$tmp"
    return "$rc"
}

# DNSStubListener=no yazıldı; yürürlüğe girdi mi? systemd 259 (Ubuntu 26.04)
# anahtarı kabul edip yok sayıyor. Bu yerleşimde zararsızdır ve ÖLÇÜLDÜ:
# dnsmasq yalnız arayüze ATANMIŞ adresleri bağlar (127.0.0.1, ::1, tailscale0);
# 127.0.0.53 atanmış bir adres değil, yalnız 127/8 rotasıyla erişilebilir, bu
# yüzden iki çözümleyici aynı sokete hiç talip olmaz. Yine de uygulanan bir
# ayarın sonucunu okumak, sessizce başarılı saymaktan iyidir (DD-109).
report_resolved_stub_state() {
    local deadline=$((SECONDS + RESOLVED_STUB_SETTLE_SECONDS))
    while [[ "$SECONDS" -lt "$deadline" ]]; do
        if ss -lnu 2>/dev/null | grep -q '127\.0\.0\.53'; then
            log INFO "resolved stub'ı 127.0.0.53'te ayakta — DNSStubListener=no bu sürümde yok sayılıyor; bu yerleşimde zararsız (DD-109)"
            return 0
        fi
        sleep 1
    done
    log INFO "resolved stub'ı kapalı — DNSStubListener=no yürürlükte"
}

# Yapılandırma dosyası servisin başlangıcından yeniyse servis onu okumamıştır:
# önceki çalıştırma render ile restart arasında düşmüş olabilir. O zaman "dosya
# aynı" demek yetmez; birim yine de yeniden başlatılır.
config_newer_than_unit() {
    local file="$1" unit="$2" started file_ts unit_ts
    started="$(systemctl show -p ActiveEnterTimestamp --value "$unit" 2>/dev/null || true)"
    [[ -n "$started" ]] || return 0
    unit_ts="$(date -d "$started" +%s 2>/dev/null || echo 0)"
    file_ts="$(stat -c %Y "$file" 2>/dev/null || echo 0)"
    [[ "$unit_ts" -eq 0 || "$file_ts" -gt "$unit_ts" ]]
}

stage_6() {
    log INFO "Aşama 6/7 — dnsmasq ve Caddy"
    local need_pkg=0
    dpkg-query -W -f='${Status}' dnsmasq 2>/dev/null | grep -q 'install ok installed' || need_pkg=1
    dpkg-query -W -f='${Status}' caddy 2>/dev/null | grep -q 'install ok installed' || need_pkg=1

    if [[ "$need_pkg" -eq 1 ]]; then
        systemctl stop dnsmasq caddy 2>/dev/null || true
        systemctl mask dnsmasq.service caddy.service >/dev/null 2>&1 || true
        # debian-keyring kurulmaz (DD-125): Caddy deposunun imzası indirilen
        # cloudsmith keyring'iyle (signed-by) doğrulanır.
        retry "apt-dns-caddy" 2 "$APT_LOCK_TIMEOUT" -- \
            apt_get_install_masked_quiet "${APT_OPTS[@]}" dnsmasq
        if [[ ! -f /usr/share/keyrings/caddy-stable-archive-keyring.asc ]]; then
            # DD-153: apt zırhlı anahtarı kendisi okur (signed-by *.asc); gnupg gerekmez.
            local caddy_key
            caddy_key="$(mktemp)"
            retry "caddy-key" 3 60 -- curl -1sLf \
                'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' -o "$caddy_key"
            install -m 0644 "$caddy_key" /usr/share/keyrings/caddy-stable-archive-keyring.asc
            rm -f "$caddy_key"
            atomic_write /etc/apt/sources.list.d/caddy-stable.list 0644 <<'EOF'
deb [signed-by=/usr/share/keyrings/caddy-stable-archive-keyring.asc] https://dl.cloudsmith.io/public/caddy/stable/deb/debian any-version main
EOF
            retry "apt-update-caddy" 3 "$APT_LOCK_TIMEOUT" -- apt-get "${APT_OPTS[@]}" update
        fi
        retry "apt-caddy" 2 "$APT_LOCK_TIMEOUT" -- apt_get_install_masked_quiet "${APT_OPTS[@]}" caddy
    fi

    mkdir -p /etc/dnsmasq.d
    local dnsmasq_changed=0 caddy_changed=0 dns_tmp
    dns_tmp="$(mktemp "$RUNTIME_DIR/.dns-XXXXXX")"
    render_template "$V2_ROOT/templates/dnsmasq.conf" "$dns_tmp" 0644 \
        TAILSCALE_IF="$TAILSCALE_IF" \
        LOCAL_DOMAIN="$LOCAL_DOMAIN"
    python3 "$SBIN_DIR/master_settings.py" filter-dns "$dns_tmp"
    atomic_write "$DNSMASQ_CONF_FILE" 0644 <"$dns_tmp"
    [[ "${V2_LAST_ATOMIC_CHANGED:-0}" -eq 1 ]] && dnsmasq_changed=1
    rm -f -- "$dns_tmp"
    # DD-156: rendered defaults consume confirmed operator choices on every re-run.
    python3 "$SBIN_DIR/master_settings.py" project-dns
    # OS/paket sürümü değişince kaybolan bir direktif, aksi hâlde ilk belirtisini
    # "systemctl restart dnsmasq başarısız" olarak verirdi. --test satır numarası
    # ve direktif adı söyler (DD-106).
    local validate_out=""
    if ! validate_out="$(dnsmasq --test -C "$DNSMASQ_CONF_FILE" 2>&1)"; then
        die "dnsmasq yapılandırması geçersiz ($DNSMASQ_CONF_FILE): ${validate_out:-sebep bildirilmedi}"
    fi

    # OS-DIVERGENCE: resolved-stub (pratikte ubuntu) — yoklama: resolved pasifse
    # (Debian varsayılanı) blok tamamen atlanır ve drop-in hiç oluşturulmaz.
    # Ubuntu 26.04 / systemd 259 anahtarı kabul edip yok sayıyor; sonuç
    # okunup bildirilir, sessizce başarılı sayılmaz [DD-102, DD-109]
    if systemctl is-active --quiet systemd-resolved 2>/dev/null; then
        mkdir -p /etc/systemd/resolved.conf.d
        atomic_write /etc/systemd/resolved.conf.d/master-stack.conf 0644 <<'EOF'
[Resolve]
DNSStubListener=no
EOF
        if [[ "${V2_LAST_ATOMIC_CHANGED:-0}" -eq 1 || "$OS_CHANGED" -eq 1 ]]; then
            systemctl restart systemd-resolved || true
        fi
        report_resolved_stub_state
        # OS-DIVERGENCE: resolvconf-symlink (ubuntu) — hedef testi; stub symlink
        # yoksa (Debian) no-op. Tailscale sonradan dosyayı devralır [DD-102]
        # Ubuntu: /etc/resolv.conf stub'a (127.0.0.53) symlink gelir; stub
        # kapanınca host DNS kırılır. resolved'in gerçek uplink dosyasına çevir.
        if [[ "$(readlink /etc/resolv.conf 2>/dev/null)" == *stub-resolv.conf ]]; then
            ln -sf /run/systemd/resolve/resolv.conf /etc/resolv.conf
            log INFO "resolv.conf stub yerine resolved uplink dosyasına bağlandı"
        fi
    fi

    render_template "$V2_ROOT/templates/Caddyfile" "$CADDYFILE" 0644 \
        WAN_IPV4="$WAN_IPV4" SHARE_PORT="$SHARE_PORT" SHARE_HTTPS_PORT="$SHARE_HTTPS_PORT" \
        CADDY_HTTP_PORT="$CADDY_HTTP_PORT" \
        LOCAL_DOMAIN="$LOCAL_DOMAIN" \
        CADDY_ADMIN_SOCKET="$CADDY_ADMIN_SOCKET" \
        PANEL_SOCKET="$PANEL_SOCKET" \
        SYSTEM_FILES_SOCKET="$SYSTEM_FILES_SOCKET" \
        FILES_PANEL_PORT="$FILES_PANEL_PORT" \
        CONSOLE_WEB_DIR="$CONSOLE_WEB_DIR" \
        CADDY_MODULES_DIR="$CADDY_MODULES_DIR"
    [[ "${V2_LAST_ATOMIC_CHANGED:-0}" -eq 1 ]] && caddy_changed=1
    # DD-149: modüllerin site dosyaları bu dizinden içe aktarılır; boş dizin geçerlidir.
    install -d -m 0755 -o root -g root "$CADDY_MODULES_DIR"
    # DD-182: WAN paylaşım sitesi son yayındaki WAN_IPV4'e bağlanır. Sağlayıcı adresi
    # değiştirdiyse Caddy onunla açılamaz; site burada kalkar, 7. aşama yeni adresle yazar.
    local wan_site
    for wan_site in "$CADDY_MODULES_DIR"/*-wan.caddy; do
        if [[ -f "$wan_site" ]] && ! grep -qxF "$(printf '\tbind %s' "$WAN_IPV4")" "$wan_site"; then
            rm -f -- "$wan_site"
            caddy_changed=1
            log WARN "WAN IPv4 değişmiş; Caddy yayını 7. aşamada yeni adresle yazılacak"
        fi
    done
    ensure_console_pages
    # Caddy env yer tutucularını çalışma anında çözer; boş ortamla doğrulamak
    # `http://:` gibi anlamsız bir siteyi geçerli sayardı — gerçek değerlerle
    # doğrula (DD-106). Çıktı normalde JSON log satırları; hata satırını süz,
    # bulunamazsa son satırı göster.
    if ! validate_out="$(
        TAILSCALE_IPV4="$TAILSCALE_IPV4" \
            caddy validate --config "$CADDYFILE" --adapter caddyfile 2>&1
    )"; then
        die "Caddyfile geçersiz ($CADDYFILE): $(
            grep -i -m1 'error' <<<"$validate_out" || tail -n1 <<<"$validate_out"
        )"
    fi
    # Sürüm yükseltmesinden sonra dosyalar bayt olarak aynı kalsa bile paketler
    # değişti; iki kenar servisi bir kez yeniden başlasın (DD-104).
    if [[ "$OS_CHANGED" -eq 1 ]]; then
        dnsmasq_changed=1
        caddy_changed=1
    fi

    mkdir -p /etc/systemd/system/dnsmasq.service.d
    atomic_write /etc/systemd/system/dnsmasq.service.d/master-stack.conf 0644 <<'EOF'
[Unit]
Wants=tailscaled.service
After=tailscaled.service

[Service]
Restart=on-failure
RestartSec=5s
EOF
    [[ "${V2_LAST_ATOMIC_CHANGED:-0}" -eq 1 ]] && dnsmasq_changed=1

    mkdir -p /etc/systemd/system/caddy.service.d
    # ExecStartPre: state.env TAILSCALE_IPV4 arayüzde olmalı (DD-72/DD-85).
    # StartLimit, adres hiç gelmezse veya stale kalırsa unit'i failed yapar.
    # OnFailure: stale/fail sonrası refresh'i timer beklemeden çalıştırır (DD-87).
    # DD-180: yönetim arayüzünün soket klasörü yalnız Caddy'ye açık (0700); TCP 2019 yok.
    local caddy_runtime="${CADDY_ADMIN_SOCKET%/*}"
    atomic_write /etc/systemd/system/caddy.service.d/master-stack.conf 0644 <<EOF
[Unit]
Wants=tailscaled.service
After=tailscaled.service
OnFailure=refresh-tailnet-config.service
Wants=master-firewall.service
After=master-firewall.service
StartLimitIntervalSec=600
StartLimitBurst=3

[Service]
RuntimeDirectory=${caddy_runtime#/run/}
RuntimeDirectoryMode=0700
EnvironmentFile=$STATE_FILE
# DD-196: paket birimi --environ ile tüm ortamı (state.env) günlüğe döker; burada dökülmez.
ExecStart=
ExecStart=/usr/bin/caddy run --config $CADDYFILE --adapter caddyfile
ExecStartPre=+$SBIN_DIR/master-firewall --check
ExecStartPre=$SBIN_DIR/wait-tailnet-addr
TimeoutStartSec=150s
Restart=on-failure
RestartSec=5s
EOF
    [[ "${V2_LAST_ATOMIC_CHANGED:-0}" -eq 1 ]] && caddy_changed=1

    systemctl daemon-reload
    systemctl unmask dnsmasq caddy 2>/dev/null || true
    systemctl enable dnsmasq caddy
    if [[ "$dnsmasq_changed" -eq 1 ]] || ! systemctl is-active --quiet dnsmasq ||
        config_newer_than_unit "$DNSMASQ_CONF_FILE" dnsmasq.service; then
        systemctl restart dnsmasq
    else
        log INFO "dnsmasq yapılandırması aynı; yeniden başlatılmadı"
    fi
    if [[ "$caddy_changed" -eq 1 ]] || ! systemctl is-active --quiet caddy ||
        config_newer_than_unit "$CADDYFILE" caddy.service; then
        systemctl restart caddy
    else
        log INFO "Caddy yapılandırması aynı; yeniden başlatılmadı"
    fi
    ensure_panel "$OS_CHANGED"
    ensure_files_panel "$OS_CHANGED"
    ensure_system_files "$OS_CHANGED"
}

# DD-133, DD-140, DD-200: Konsol'un root arka ucu. DD-180: TCP yok, PANEL_SOCKET
# Unix soketinde dinler (0660 root:CADDY_GROUP); Caddy tailnet'e ve isteğe bağlı genel HTTPS adına açar
# (panel.LOCAL_DOMAIN altında /api/konsol/* ve /api/uygulama/*; DD-195). DD-194: Konsol
# girişini ve Caddy'nin her panel isteği için sorduğu oturumu da bu arka uç denetler.
# Yalnız betik ya da unit değişince servis yeniden başlar.
ensure_panel() {
    local changed="${1:-0}" f out
    [[ "$PANEL_HELPERS_CHANGED" -eq 0 ]] || changed=1
    # DD-196/203/207: paket araçlarının yazdığı klasörler (PAKET_ARKAUC_YOLLAR) arka uç başlamadan
    # açılır; systemd yalnız o an var olan klasörü yazılabilir bağlar (ReadWritePaths -). Paket kurulu
    # değilse boş kalır. DD-194: hesap ve oturum kayıtları; arka ucun /etc altında yazabildiği kalıcı yer.
    while IFS= read -r f; do
        [[ -d "$f" ]] || install -d -m 0700 -o root -g root -- "$f"
    done < <(paket_arkauc_klasorler)
    install -d -m 0700 -o root -g root -- "$KONSOL_AUTH_DIR"
    atomic_write "$SBIN_DIR/master-panel" 0755 <"$V2_ROOT/panel/master-panel"
    [[ "${V2_LAST_ATOMIC_CHANGED:-0}" -eq 1 ]] && changed=1
    render_template "$V2_ROOT/systemd/master-panel.service" "$UNIT_DIR/master-panel.service" 0644 \
        SBIN_DIR="$SBIN_DIR" \
        PANEL_SOCKET="$PANEL_SOCKET" \
        PANEL_RUNTIME="$(basename -- "${PANEL_SOCKET%/*}")" \
        CADDY_GROUP="$CADDY_GROUP" \
        STATE_FILE="$STATE_FILE" \
        PANEL_WRITE_PATHS="$(paket_arkauc_yollar)" \
        KONSOL_AUTH_DIR="$KONSOL_AUTH_DIR"
    [[ "${V2_LAST_ATOMIC_CHANGED:-0}" -eq 1 ]] && changed=1
    systemctl daemon-reload
    systemctl enable --quiet master-panel.service
    # DD-207: çalışan arka uç bir klasörü salt okunur görüyorsa (klasör o başladıktan sonra oluştu)
    # yeniden başlar; böylece yeniden kurulum böyle bir sunucuyu da onarır.
    if [[ "$changed" -eq 1 ]] || ! systemctl is-active --quiet master-panel.service || ! panel_yollari_bagli; then
        systemctl restart master-panel.service
    else
        log INFO "Konsol arka ucu aynı; yeniden başlatılmadı"
    fi
}

# Built-in Files listens on loopback as DOWNLOADS_UID, writing only SERVER_ROOT.
# Stage 7 applies changed worker/unit files through master-modul yerlesik (DD-159).
# Caddy directly serves the console's static assets.
ensure_console_pages() {
    local f dir id
    install -d -m 0755 -o root -g root "$CONSOLE_WEB_DIR"
    for f in index.html konsol.css konsol.js ayarlar.css ayarlar.js dosyalar.css dosyalar.js panel.css arsiv.js \
        konteynerler.css konteynerler.js giris.html giris.js giris.css; do
        atomic_write "$CONSOLE_WEB_DIR/$f" 0644 <"$V2_ROOT/console/$f"
    done
    # DD-200: kurulu paketlerin sayfa dosyaları uygulama/<id>/ altındadır (master-modul koyar ve
    # kaldırır). Kayıtta olmayan bir paketin klasörü sunucuda durmaz.
    for dir in "$CONSOLE_WEB_DIR"/uygulama/*/; do
        [[ -d "$dir" ]] || continue
        id="${dir%/}"; id="${id##*/}"
        [[ -z "$(module_state "$id")" ]] || continue
        rm -rf -- "$dir"
        log INFO "Konsol: kurulu olmayan $id paketinin sayfa dosyaları kaldırıldı"
    done
}

ensure_files_panel() {
    local changed="${1:-0}" protected user group
    # systemd User= sayısal uid için de kullanıcı kaydı ister. Varsa mevcut ad (ör. ubuntu),
    # yoksa girişsiz, ev dizinsiz bir sistem hesabı; dosya sahipliği sayısal kaldığı için değişmez.
    # getent bulamayınca 2 döner; pipefail altında kurulumu düşürmesin.
    group="$(getent group "$DOWNLOADS_GID" | cut -d: -f1 || true)"
    if [[ -z "$group" ]]; then
        groupadd --system --gid "$DOWNLOADS_GID" "$DOWNLOADS_ACCOUNT" ||
            die "gid $DOWNLOADS_GID için grup açılamadı ($DOWNLOADS_ACCOUNT)"
        group="$DOWNLOADS_ACCOUNT"
        log INFO "gid $DOWNLOADS_GID için sistem grubu açıldı: $group (dosya paneli)"
    fi
    user="$(getent passwd "$DOWNLOADS_UID" | cut -d: -f1 || true)"
    if [[ -z "$user" ]]; then
        useradd --system --uid "$DOWNLOADS_UID" --gid "$DOWNLOADS_GID" --no-create-home \
            --home-dir /nonexistent --shell /usr/sbin/nologin "$DOWNLOADS_ACCOUNT" ||
            die "uid $DOWNLOADS_UID için sistem hesabı açılamadı ($DOWNLOADS_ACCOUNT)"
        user="$DOWNLOADS_ACCOUNT"
        log INFO "uid $DOWNLOADS_UID için girişsiz sistem hesabı açıldı: $user (dosya paneli)"
    fi
    atomic_write "$SBIN_DIR/master-files-panel" 0755 <"$V2_ROOT/files-panel/master-files-panel"
    [[ "${V2_LAST_ATOMIC_CHANGED:-0}" -eq 1 ]] && { changed=1; FILES_PANEL_SCRIPT_CHANGED=1; }
    atomic_write "$SBIN_DIR/master_archives.py" 0644 <"$V2_ROOT/files-panel/master_archives.py"
    [[ "${V2_LAST_ATOMIC_CHANGED:-0}" -eq 1 ]] && changed=1
    atomic_write "$SBIN_DIR/master_rar.py" 0644 <"$V2_ROOT/files-panel/master_rar.py"
    [[ "${V2_LAST_ATOMIC_CHANGED:-0}" -eq 1 ]] && changed=1
    python3 "$V2_ROOT/panel/master_permissions.py" --directory-mode 0700 \
        "$SERVER_ROOT/$FILES_ARCHIVE_DIR" "$DOWNLOADS_UID" "$DOWNLOADS_GID"
    # DD-144, DD-203: paketlerin yazdığı klasörler (bildirimlerden) köke göre; sayfa orada uyarır.
    protected="$(paket_korunan_klasorler)"
    install -d -m 0755 -o root -g root "$MODULES_DIR/dosya"
    render_template "$V2_ROOT/systemd/master-files-panel.service" "$MODULES_DIR/dosya/master-files-panel.service" 0644 \
        SBIN_DIR="$SBIN_DIR" \
        FILES_PANEL_PORT="$FILES_PANEL_PORT" \
        FILES_ARCHIVE_DIR="$FILES_ARCHIVE_DIR" \
        FILES_PANEL_TRASH="$FILES_PANEL_TRASH" \
        SHARE_DIR="$SHARE_DIR" \
        SERVER_ROOT="$SERVER_ROOT" \
        FILES_PANEL_USER="$user" \
        FILES_PANEL_GROUP="$group" \
        LOCAL_DOMAIN="$LOCAL_DOMAIN" \
        V2_VERSION="$V2_VERSION" \
        PROTECTED_DIRS="$protected" \
        DOWNLOADS_SUBDIR="$DOWNLOADS_SUBDIR" \
        PRIVATE_STATE_ROOT="$PRIVATE_STATE_ROOT"
    [[ "${V2_LAST_ATOMIC_CHANGED:-0}" -eq 1 ]] && changed=1
    # DD-222: aşama 4'ün döngüsünden sonra: işaret bir sonraki kurulum için, liste bu kurulum için.
    [[ "$changed" -eq 0 ]] || { mark_module_pending dosya; MODULES_CHANGED="$MODULES_CHANGED dosya"; }
}

# DD-235: Dosyalar'ın "Sistem (/)" görünümü. master-files-panel'in --sistem kipi root olarak, kök /;
# yalnız SYSTEM_FILES_SOCKET Unix soketinde (0660 root:CADDY_GROUP). Caddy onu yalnız Tailscale
# sitesinde /api/sistem/* için açar. Betik ya da unit değişince servis yeniden başlar.
ensure_system_files() {
    local changed="${1:-0}"
    [[ "$FILES_PANEL_SCRIPT_CHANGED" -eq 0 ]] || changed=1
    render_template "$V2_ROOT/systemd/master-sistem-dosya.service" "$UNIT_DIR/master-sistem-dosya.service" 0644 \
        SBIN_DIR="$SBIN_DIR" \
        SYSTEM_FILES_SOCKET="$SYSTEM_FILES_SOCKET" \
        SYSTEM_FILES_RUNTIME="$(basename -- "${SYSTEM_FILES_SOCKET%/*}")" \
        CADDY_GROUP="$CADDY_GROUP" \
        LOCAL_DOMAIN="$LOCAL_DOMAIN" \
        V2_VERSION="$V2_VERSION"
    [[ "${V2_LAST_ATOMIC_CHANGED:-0}" -eq 1 ]] && changed=1
    systemctl daemon-reload
    systemctl enable --quiet master-sistem-dosya.service
    if [[ "$changed" -eq 1 ]] || ! systemctl is-active --quiet master-sistem-dosya.service; then
        systemctl restart master-sistem-dosya.service
    else
        log INFO "Sistem görünümü arka ucu aynı; yeniden başlatılmadı"
    fi
}

stage_7() {
    log INFO "Aşama 7/7 — doğrulama"
    # Built-in capabilities keep the service registry IDs (DD-159/171).
    "$SBIN_DIR/master-modul" yerlesik "$MODULES_CHANGED"
    python3 "$SBIN_DIR/master_shares.py" publish
    systemctl enable --now master-share-network.timer
    # DD-152: Docker yok; kurulu modüller dosyaları değiştiyse master-modul ile yeniden uygulanır.
    reapply_modules
    "$SBIN_DIR/master-firewall" --check
    check_podman
    # DD-181: the timer sleeps while nothing is pending; it must stay enabled for boot and apply.
    systemctl is-enabled --quiet master-settings-guard.timer || die "Konsol ayar geri alma zamanlayıcısı etkin değil"
    python3 "$SBIN_DIR/master_settings.py" status >/dev/null || die "Konsol ayar durumu okunamadı"

    # Drop-in doğru yazılmış olsa bile /etc/sysctl.d'de sonradan sıralanan bir
    # dosya onu ezebilir; belirleyici olan ÇALIŞMA ANINDAKİ değer (DD-105).
    # ip_forward exit node'un varlık şartı: fail-closed.
    local fwd rmem
    fwd="$(sysctl -n net.ipv4.ip_forward 2>/dev/null || echo 0)"
    [[ "$fwd" == "1" ]] ||
        die "net.ipv4.ip_forward=$fwd (exit node için 1 olmalı; $SYSCTL_FORWARD_FILE başka bir /etc/sysctl.d dosyasınca eziliyor olabilir)"
    rmem="$(sysctl -n net.core.rmem_max 2>/dev/null || echo 0)"
    [[ "$rmem" =~ ^[0-9]+$ ]] || rmem=0
    if (( rmem < NET_BUF_FLOOR_BYTES )); then
        log WARN "net.core.rmem_max=$rmem taban değerin ($NET_BUF_FLOOR_BYTES) altında; $SYSCTL_NETBUF_FILE eziliyor olabilir"
    fi
    # DD-111: sonuç geri okunur. Bir optimizasyon, sözleşme maddesi değil —
    # uyumsuzluk uyarı üretir, kurulumu düşürmez.
    local cc
    cc="$(sysctl -n net.ipv4.tcp_congestion_control 2>/dev/null || echo bilinmiyor)"
    if [[ -f "$SYSCTL_TCP_FILE" && "$cc" != "$TCP_CONGESTION_CONTROL" ]]; then
        log WARN "tcp_congestion_control=$cc ($TCP_CONGESTION_CONTROL bekleniyordu; $SYSCTL_TCP_FILE eziliyor olabilir)"
    fi
    # DD-113: güncelleme politikası geri okunur (etkin apt-config + zamanlayıcı).
    # Bakım konusu, sözleşme maddesi değil — uyumsuzluk uyarı üretir.
    local periodic
    # awk boruyu sonuna kadar okur: erken `exit` apt-config'e SIGPIPE verir ve
    # pipefail altında 141 ile kurulumu düşürür (canlı testte görüldü).
    periodic="$(apt-config dump 2>/dev/null | awk -F'"' '/^APT::Periodic::Unattended-Upgrade /{v=$2} END{print v}')"
    if [[ "$periodic" != "1" ]] || ! command -v unattended-upgrade >/dev/null 2>&1 ||
        ! systemctl is-active --quiet apt-daily-upgrade.timer; then
        log WARN "otomatik güvenlik güncellemeleri etkin değil (APT::Periodic::Unattended-Upgrade=${periodic:-yok}; $APT_PERIODIC_FILE eziliyor olabilir)"
    fi
    # DD-184: Tailscale ve Caddy depoları etkin kalıpta mı (başka bir dosya ezmiş olabilir)?
    local patterns
    patterns="$(apt-config dump 2>/dev/null | awk '/^Unattended-Upgrade::Origins-Pattern/' || true)"
    [[ "$patterns" == *"$TAILSCALE_APT_ORIGIN"* && "$patterns" == *"$CADDY_APT_ORIGIN"* ]] ||
        log WARN "Tailscale/Caddy otomatik güncelleme kalıpları etkin yapılandırmada yok ($APT_UNATTENDED_POLICY_FILE)"

    local name resolver ans dig_out code line
    # shellcheck disable=SC2086
    for name in $SERVICE_NAMES; do
        if ! python3 "$SBIN_DIR/master_settings.py" dns-enabled "${name}.${LOCAL_DOMAIN}"; then
            log INFO "DNS: ${name}.${LOCAL_DOMAIN} Konsol tercihiyle kapalı"
            continue
        fi
        for resolver in 127.0.0.1 "$TAILSCALE_IPV4"; do
            ans="$(
                dig +short +time=2 +tries=1 "${name}.${LOCAL_DOMAIN}" @"$resolver" |
                    head -n1 || true
            )"
            [[ "$ans" == "$TAILSCALE_IPV4" ]] ||
                die "DNS: ${name}.${LOCAL_DOMAIN} @$resolver -> '${ans}' (beklenen $TAILSCALE_IPV4)"
        done
    done

    dig_out="$(
        dig +time=2 +tries=1 +noall +comments "not-in-${LOCAL_DOMAIN}.example" \
            @"$TAILSCALE_IPV4" 2>/dev/null || true
    )"
    if ! python3 "$SBIN_DIR/master_settings.py" dns-forward; then
        [[ "$dig_out" == *"status: REFUSED"* ]] ||
            die "DNS: alan dışı sorgu REFUSED değil (Tailscale DNS)"
    fi

    # DD-201: kurulu paketler kendi doğrulamasını yapar (paket_denetle); kurulu olmayan bir
    # paketin aracı ya da birim eki sunucuda bulunmamalı. Temel hiçbir uygulama ayrıntısı bilmez.
    local pkg
    for pkg in $(paket_katalog); do
        if [[ -n "$(module_state "$pkg")" ]]; then
            paket_denetle_calistir "$pkg"
        else
            paket_iz_yok "$pkg" ||
                die "$(paket_bildirim_oku "$pkg" PAKET_AD) kurulu değilken aracı ya da birim eki sunucuda kalmış"
        fi
    done

    # DD-194/DD-205: Konsol girişi. Giriş sayfasının dosyaları açıktır; geri kalan her panel isteği
    # (sayfa, Dosyalar, API) Caddy'nin forward_auth'u ile root arka uca sorulur. Tailscale sitesinde
    # başka bir Tailscale cihazı oturumsuz geçer (cihazı Tailscale doğrular) ve /giris.html Konsol'a
    # yönlenir; sunucunun kendisinden gelen istek reddedilir (DD-180). Caddy'nin yönlendirme
    # başlıkları olmadan (internet sitesinde olduğu gibi) oturumsuz API 401 alır, sayfa giriş
    # sayfasına yönlenir. Ayrıca X-Konsol başlığı olmayan API isteği (başka bir sitenin tarayıcıdan
    # attığı istek) ve yabancı Host (DNS rebinding) iki arka uçta da reddedilir. Panel VPN adresinde
    # dinlenmez. DD-154: eski adresler (wg., dosya., file.) yoktur.
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 \
        -H "Host: panel.${LOCAL_DOMAIN}" "http://${TAILSCALE_IPV4}/giris.js" || true)"
    [[ "$code" == "200" ]] || die "Konsol giriş sayfasının dosyası tailnet'ten açılmadı (HTTP $code)"
    local page_body probe tail_probe
    page_body="$(curl -s --max-time 5 -w '\n%{http_code}' -H "Host: panel.${LOCAL_DOMAIN}" \
        "http://${TAILSCALE_IPV4}/" 2>/dev/null || true)"
    [[ "${page_body##*$'\n'}" == "403" && "$page_body" == *"başka bir Tailscale cihazından"* ]] ||
        die "Konsol sayfası oturum denetiminden geçmeden açıldı (HTTP ${page_body##*$'\n'})"
    for probe in "/api/konsol/kaynaklar|401" "/|302"; do
        code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 --unix-socket "$PANEL_SOCKET" \
            -H "Host: panel.${LOCAL_DOMAIN}" -H "X-Forwarded-Uri: ${probe%%|*}" \
            "http://localhost/oturum-denetle" || true)"
        [[ "$code" == "${probe#*|}" ]] ||
            die "Konsol oturum denetimi ${probe%%|*} için HTTP $code döndü (beklenen ${probe#*|})"
    done
    # DD-205: başka bir Tailscale cihazı (Caddy'nin yazdığı X-Forwarded-For) oturumsuz geçer; giriş
    # sayfası ona Konsol'u gösterir. Deneme adresi sunucunun kendi tailnet adresinden türetilir
    # (son bölüm farklı, aynı 100.64.0.0/10 aralığında); sabit bir adres yazılmaz.
    tail_probe="${TAILSCALE_IPV4%.*}.$(( (${TAILSCALE_IPV4##*.} + 1) % 254 + 1 ))"
    for probe in "/api/konsol/kaynaklar|204" "/giris.html|302"; do
        code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 --unix-socket "$PANEL_SOCKET" \
            -H "Host: panel.${LOCAL_DOMAIN}" -H "X-Forwarded-For: $tail_probe" -H "X-Forwarded-Uri: ${probe%%|*}" \
            "http://localhost/oturum-denetle" || true)"
        [[ "$code" == "${probe#*|}" ]] ||
            die "Konsol Tailscale kapısı ${probe%%|*} için HTTP $code döndü (beklenen ${probe#*|})"
    done
    # DD-180: root arka ucu TCP'de değil, yalnız Unix soketinde; dosya arka ucu loopback'te.
    local gate gate_path gate_url gate_via=()
    for gate in "http://127.0.0.1:${FILES_PANEL_PORT}|/api/state" "unix:${PANEL_SOCKET}|/api/konsol/kaynaklar"; do
        gate_path="${gate#*|}"
        gate_url="${gate%%|*}"
        gate_via=()
        if [[ "$gate_url" == unix:* ]]; then
            gate_via=(--unix-socket "${gate_url#unix:}")
            gate_url="http://localhost"
        fi
        code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "${gate_via[@]}" \
            -H "Host: panel.${LOCAL_DOMAIN}" "${gate_url}${gate_path}" || true)"
        [[ "$code" == "403" ]] || die "Konsol ${gate_path}: X-Konsol başlığı olmadan HTTP $code (beklenen 403)"
        code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "${gate_via[@]}" -H 'X-Konsol: 1' \
            -H "Host: baska.ornek" "${gate_url}${gate_path}" || true)"
        [[ "$code" == "403" ]] || die "Konsol ${gate_path}: yabancı Host ile HTTP $code (beklenen 403)"
    done
    # DD-180: indirme hesabıyla çalışan bir program (bir paketin servisi, unrar) root arka uca ve
    # Caddy'nin yönetim arayüzüne ulaşamamalı. Soketin izni ve gerçek bir deneme sınanır.
    [[ "$(stat -c '%U:%G:%a' "$PANEL_SOCKET" 2>/dev/null)" == "root:${CADDY_GROUP}:660" ]] ||
        die "Konsol arka ucu soketi root:${CADDY_GROUP} 0660 değil: $PANEL_SOCKET"
    [[ "$(stat -c '%U:%a' "${CADDY_ADMIN_SOCKET%/*}" 2>/dev/null)" == "caddy:700" ]] ||
        die "Caddy yönetim soketinin klasörü yalnız Caddy'ye açık değil: ${CADDY_ADMIN_SOCKET%/*}"
    [[ -S "$CADDY_ADMIN_SOCKET" ]] || die "Caddy yönetim soketi yok: $CADDY_ADMIN_SOCKET"
    # DD-235: Sistem görünümü (root) da yalnız root ve Caddy'nin grubuna açık bir sokette; yalnız
    # Tailscale kanalından ve başka bir Tailscale cihazından gelen isteği kabul eder.
    [[ "$(stat -c '%U:%G:%a' "$SYSTEM_FILES_SOCKET" 2>/dev/null)" == "root:${CADDY_GROUP}:660" ]] ||
        die "Sistem görünümü soketi root:${CADDY_GROUP} 0660 değil: $SYSTEM_FILES_SOCKET"
    local kanal adres beklenen
    for probe in "tailscale|${tail_probe}|200" "internet|${tail_probe}|403" "tailscale|${TAILSCALE_IPV4}|403"; do
        IFS='|' read -r kanal adres beklenen <<<"$probe"
        code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 --unix-socket "$SYSTEM_FILES_SOCKET" \
            -H "Host: panel.${LOCAL_DOMAIN}" -H 'X-Konsol: 1' -H "X-Konsol-Kanal: $kanal" \
            -H "X-Forwarded-For: $adres" "http://localhost/api/sistem/state" || true)"
        [[ "$code" == "$beklenen" ]] ||
            die "Sistem görünümü $kanal kanalı ve $adres için HTTP $code döndü (beklenen $beklenen)"
    done
    local sock
    for sock in "$PANEL_SOCKET" "$SYSTEM_FILES_SOCKET" "$CADDY_ADMIN_SOCKET"; do
        code="$(setpriv --reuid="$DOWNLOADS_UID" --regid="$DOWNLOADS_GID" --clear-groups \
            curl -s -o /dev/null -w '%{http_code}' --max-time 3 --unix-socket "$sock" \
            -H "Host: panel.${LOCAL_DOMAIN}" -H 'X-Konsol: 1' "http://localhost/" 2>/dev/null || true)"
        [[ "$code" == "000" ]] || die "İndirme hesabı $sock soketine bağlanabildi (HTTP $code)"
    done
    # Caddy'nin varsayılan TCP yönetim portu (2019) kapalı; yeniden yükleme soketten çalışır.
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "http://127.0.0.1:2019/config/" || true)"
    [[ "$code" == "000" ]] || die "Caddy yönetim arayüzü TCP'de açık (HTTP $code)"
    systemctl reload caddy || die "Caddy yönetim soketi üzerinden yeniden yüklenemedi"
    # DD-180: Caddy'nin tailnet adresi sunucunun içinden de açıktır; oradan gelen istek (ör.
    # indirme hesabıyla çalışan bir program) root arka uçtan 403 almalı. Arka ucun kendi
    # denetimi soketten yapılır; 403'ün gövdesi isteğin Caddy'den arka uca ulaştığını da gösterir.
    local self_body
    self_body="$(setpriv --reuid="$DOWNLOADS_UID" --regid="$DOWNLOADS_GID" --clear-groups \
        curl -s --max-time 5 -w '\n%{http_code}' -H "Host: panel.${LOCAL_DOMAIN}" -H 'X-Konsol: 1' \
        "http://${TAILSCALE_IPV4}/api/konsol/kaynaklar" 2>/dev/null || true)"
    [[ "${self_body##*$'\n'}" == "403" && "$self_body" == *"başka bir Tailscale cihazından"* ]] ||
        die "Sunucunun içinden Caddy üzerinden root arka uca ulaşıldı (HTTP ${self_body##*$'\n'})"
    self_body="$(setpriv --reuid="$DOWNLOADS_UID" --regid="$DOWNLOADS_GID" --clear-groups \
        curl -s --max-time 5 -w '\n%{http_code}' -H "Host: panel.${LOCAL_DOMAIN}" -H 'X-Konsol: 1' \
        "http://${TAILSCALE_IPV4}/api/sistem/state" 2>/dev/null || true)"
    [[ "${self_body##*$'\n'}" == "403" && "$self_body" == *"başka bir Tailscale cihazından"* ]] ||
        die "Sunucunun içinden Caddy üzerinden Sistem görünümüne ulaşıldı (HTTP ${self_body##*$'\n'})"
    local panel_out
    panel_out="$(python3 "$SBIN_DIR/master-panel" check --socket "$PANEL_SOCKET" \
        --url "http://panel.${LOCAL_DOMAIN}/api/konsol/kaynaklar" --host "panel.${LOCAL_DOMAIN}" 2>&1)" ||
        die "Konsol arka ucu yanıt vermedi: $panel_out"
    log INFO "Konsol arka ucu açıldı: http://panel.${LOCAL_DOMAIN} ($panel_out)"
    # DD-159: built-in Files is required, writable and unprivileged.
    local files_out files_uid
    # DD-194: Caddy'den geçen yol oturum ister; arka ucun kendisi loopback'ten sınanır.
    files_out="$(python3 "$SBIN_DIR/master-files-panel" check \
        --url "http://127.0.0.1:${FILES_PANEL_PORT}/api/state" --host "panel.${LOCAL_DOMAIN}" 2>&1)" ||
        die "Konsol dosya arka ucu yanıt vermedi: $files_out"
    log INFO "Konsol dosya arka ucu açıldı: $files_out"
    files_uid="$(ps -o uid= -p "$(systemctl show -p MainPID --value master-files-panel.service)" 2>/dev/null | tr -d ' ')"
    [[ "$files_uid" == "$DOWNLOADS_UID" ]] ||
        die "Dosya paneli uid '${files_uid}' ile çalışıyor (beklenen $DOWNLOADS_UID; root olmamalı)"
    # DD-143: ağ varsa Konsol o ağın sunucu adresinde dinlememeli (ağ yoksa denetim atlanır).
    # WebDAV registry, unprivileged listener and addresses were verified by yerlesik.

    log INFO "Temel doğrulamalar geçti"
}

# Özet: yerleşik yetenekler ve mağaza paketleri (DD-197: ad ve bilgi paketten); kurulu olanın adresi.
summary_modules() {
    local id name info st ids
    ids="$(paket_katalog)"
    for id in dosya $ids paylasim; do
        case "$id" in
            dosya) name="Dosya yöneticisi"; info="$SERVER_ROOT" ;;
            paylasim) name="Paylaşım"; info="Dosyalar → Paylaşımlar: klasör başına adres, kullanıcı ve erişim izni" ;;
            *)
                name="$(paket_bildirim_oku "$id" PAKET_AD)"
                # Paketin kancası tek satır bilgi verir; alt kabukta, hiçbir şey çalıştırmadan.
                # shellcheck source=/dev/null
                info="$( [[ -f "$V2_ROOT/magaza/$id/kanca" ]] && ( source "$V2_ROOT/magaza/$id/kanca" 2>/dev/null;
                    declare -F paket_ozet >/dev/null 2>&1 && paket_ozet ) 2>/dev/null || true )"
                ;;
        esac
        case "$(module_state "$id")" in
            calisiyor) st="kurulu" ;;
            durduruldu) st="kurulu, durduruldu" ;;
            *) st="kurulu değil"; info="" ;;
        esac
        printf '  %s: %s%s\n' "$name" "$st" "${info:+ — $info}"
    done
}

# DD-196/201: kurulu paketin özet notu (paket_not), yalnız paket kuruluyken.
summary_notes() {
    local id note
    for id in $(paket_katalog); do
        [[ -n "$(module_state "$id")" && -f "$V2_ROOT/magaza/$id/kanca" ]] || continue
        # shellcheck source=/dev/null
        note="$( ( source "$V2_ROOT/magaza/$id/kanca" 2>/dev/null; declare -F paket_not >/dev/null 2>&1 && paket_not ) 2>/dev/null || true )"
        [[ -z "$note" ]] || printf '\n%s' "$note"
    done
}

print_summary() {
    log INFO "Kurulum tamam — v$V2_VERSION"
    cat <<EOF

WAN:          $WAN_INTERFACE $WAN_IPV4 ${WAN_IPV6:-"(IPv6 yok)"}
Tailscale:    $TAILSCALE_IPV4 ${TAILSCALE_IPV6:-"(IPv6 yok)"}
Domain:       $LOCAL_DOMAIN
Kullanıcı alanı: $SERVER_ROOT (indirmeler $DOWNLOADS_PATH, kütüphane $SERVER_ROOT/$MEDIA_SUBDIR)
State:        $STATE_FILE
Log:          $V2_LOG_FILE

Manuel Tailscale Admin:
  1) DNS → Nameservers → Custom: $TAILSCALE_IPV4
  2) Restrict to domain: $LOCAL_DOMAIN
  3) Exit node olarak bu makineyi onayla

Konsol: http://panel.${LOCAL_DOMAIN} (Dosyalar, App Store ve Ayarlar; Tailscale'den parolasız)
  İnternetten HTTPS isteğe bağlı: önce Ayarlar → Sistem → Konsol hesabı (kullanıcı adı + parola),
  sonra Ayarlar → Caddy → Panel (DNS A kaydı gerekir).
  Kaynak kullanımı sol menüde; sistem bilgisi ve günlük Ayarlar içinde.
Podman:       ${PODMAN_VERSION:-?} (konteyner ortamı; Konsol → Podman)
Yerleşik Dosyalar/WebDAV ve App Store uygulamaları ($(paket_katalog_adlar)):
$(summary_modules)$(summary_notes)
Tailscale IP: refresh-tailnet-config → Caddy
EOF
}

main() {
    log INFO "master-stack $V2_VERSION başlıyor"
    stage_0
    stage_1
    stage_2
    stage_3
    stage_4
    stage_5
    stage_6
    stage_7
    print_summary
}

if [[ "${V2_INHIBITED:-0}" != "1" ]]; then
    if ! command -v systemd-inhibit >/dev/null 2>&1 ||
       [[ ! -d /run/systemd/system ]]; then
        die "systemd-inhibit kullanılamıyor; kurulum başlatılmadı"
    fi
    self="$(readlink -f "${BASH_SOURCE[0]}" 2>/dev/null || true)"
    [[ -n "$self" && -f "$self" ]] || die "kurulum betiğinin yolu çözülemedi"
    exec systemd-inhibit \
        --what=shutdown:sleep \
        --who=master-stack-installer \
        --why="master-stack kurulum işlemi" \
        --mode=block \
        env V2_INHIBITED=1 bash "$self" "$@"
fi

main "$@"
