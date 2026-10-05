#!/usr/bin/env bash
# Ortak yardımcılar — kısa ve tekrar kullanılanlar.
# Docker / Tailscale / firewall bilmez. Production: Bash 5.x
# (Debian 13 / Ubuntu 24.04 / Ubuntu 26.04).

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    printf 'HATA: %s source edilmek içindir.\n' "${BASH_SOURCE[0]}" >&2
    exit 1
fi

V2_LOG_FILE="${V2_LOG_FILE:-}"
V2_LAST_ATOMIC_CHANGED="${V2_LAST_ATOMIC_CHANGED:-0}"

log() {
    local level="$1"
    shift
    local line
    line="[$(date '+%H:%M:%S')] $*"
    case "$level" in
        WARN | HATA) printf '%s\n' "$line" >&2 ;;
        *) printf '%s\n' "$line" ;;
    esac
    if [[ -n "$V2_LOG_FILE" ]]; then
        printf '%s\n' "$line" >>"$V2_LOG_FILE" 2>/dev/null || true
    fi
}

die() {
    log HATA "${1:-bilinmeyen hata}"
    exit "${2:-1}"
}

require_root() {
    [[ "$(id -u)" == "0" ]] || die "bu betik root olarak çalıştırılmalıdır"
}

# Desteklenen sürümler (DD-102): Debian 13 (trixie), Ubuntu 24.04 LTS
# (noble), Ubuntu 26.04 LTS (resolute). ID+codename+major üçlüsü birlikte
# doğrulanır; OS_ID/OS_CODENAME apt depo satırlarını türetir — dağıtım
# kimliğinin tek kaynağı os-release'tir, depo suite'i ayrıca yazılmaz.
# OS_VERSION_ID/OS_ARCH yalnız state.env kaydı ve sürüm değişimi tespiti
# içindir; kapı kararını değiştirmez (DD-104).
require_supported_os() {
    local f="${V2_OS_RELEASE_PATH:-/etc/os-release}"
    [[ -r "$f" ]] || die "işletim sistemi okunamıyor: $f"
    local id="" codename="" version_id="" line=""
    while IFS= read -r line || [[ -n "$line" ]]; do
        case "$line" in
            ID=*) id="${line#ID=}"; id="${id%\"}"; id="${id#\"}" ;;
            VERSION_CODENAME=*)
                codename="${line#VERSION_CODENAME=}"
                codename="${codename%\"}"
                codename="${codename#\"}"
                ;;
            VERSION_ID=*)
                version_id="${line#VERSION_ID=}"
                version_id="${version_id%\"}"
                version_id="${version_id#\"}"
                ;;
        esac
    done <"$f"
    local expected=""
    case "$id/$codename" in
        debian/trixie) expected=13 ;;
        ubuntu/noble) expected=24 ;;
        ubuntu/resolute) expected=26 ;;
        *)
            die "desteklenmeyen dağıtım: ID=${id:-yok} codename=${codename:-yok} (Debian 13 trixie / Ubuntu 24.04 noble / Ubuntu 26.04 resolute)"
            ;;
    esac
    [[ "${version_id%%.*}" == "$expected" ]] ||
        die "sürüm codename ile uyuşmuyor: $codename için VERSION_ID=${version_id:-yok} (beklenen ${expected}.*)"
    # dpkg yoksa (iş istasyonu testleri) uname'e düş; değer yalnız kayıt için.
    local arch=""
    arch="$(dpkg --print-architecture 2>/dev/null || uname -m 2>/dev/null || true)"
    # shellcheck disable=SC2034 # install.sh apt depo satırlarında ve state.env'de tüketir
    OS_ID="$id" OS_CODENAME="$codename" OS_VERSION_ID="$version_id" \
        OS_ARCH="${arch:-bilinmiyor}"
}

acquire_lock() {
    local lock_file="${1:?}" wait_seconds="${2:-5}"
    [[ "$lock_file" == /* && "$lock_file" != / && "$lock_file" != */ ]] ||
        die "kilit yolu mutlak bir dosya olmalıdır"
    command -v flock >/dev/null || die "flock gerekli (util-linux)"
    mkdir -p -- "${lock_file%/*}"
    exec {V2_LOCK_FD}>"$lock_file"
    flock -w "$wait_seconds" "$V2_LOCK_FD" ||
        die "kilit alınamadı (${wait_seconds}s): $lock_file"
    # Child module operations reuse this exact open file description, not a bypass flag.
    export V2_LOCK_FD
}

# retry LABEL ATTEMPTS TIMEOUT -- cmd args...
# Bash fonksiyonları timeout ile doğrudan exec edilemez (kod 127); bu durumda
# export -f + bash -c ile sarılır.
retry() {
    local label="$1" attempts="$2" budget="$3"
    shift 3
    [[ "${1:-}" == "--" ]] || die "retry: '--' ayırıcısı gerekli"
    shift
    local n=1 status=0
    local -a cmd=("$@")
    while [[ "$n" -le "$attempts" ]]; do
        status=0
        # --foreground: tmux/non-TTY altında apt'in SIGTSTP ile T durumunda
        # kalmasını önler (aksi halde paket kurulumu donar).
        if declare -F -- "${cmd[0]}" >/dev/null 2>&1; then
            export -f "${cmd[0]}"
            # shellcheck disable=SC2016 # $0/$@ child bash'te genişlesin; burada değil
            timeout --foreground "$budget" bash -c '"$0" "$@"' "${cmd[@]}" || status=$?
        else
            timeout --foreground "$budget" "${cmd[@]}" || status=$?
        fi
        [[ "$status" -eq 0 ]] && return 0
        log WARN "$label: deneme $n/$attempts başarısız (kod $status)"
        n=$((n + 1))
        [[ "$n" -le "$attempts" ]] && sleep 2
    done
    die "$label: $attempts deneme başarısız (son kod $status)"
}

# atomic_write DEST MODE < stdin
# Sets V2_LAST_ATOMIC_CHANGED to 1 if the file was replaced, 0 if content matched.
atomic_write() {
    local dest="${1:?}" mode="${2:-0644}"
    [[ "$dest" == /* && "$dest" != / ]] || die "atomic_write: mutlak hedef gerekli"
    [[ ! -L "$dest" ]] || die "atomic_write: symlink hedef reddedildi: $dest"
    local dir="${dest%/*}"
    [[ -d "$dir" ]] || die "atomic_write: dizin yok: $dir"
    local tmp
    tmp="$(mktemp "$dir/.installer-XXXXXX")"
    # No RETURN trap (DD-193): Bash traps are global, so one set here replaced the
    # caller's own cleanup trap and kept firing afterwards. Clean up explicitly.
    if ! cat >"$tmp" || ! chmod "$mode" "$tmp"; then
        rm -f -- "$tmp"
        return 1
    fi
    if [[ -f "$dest" ]] && cmp -s "$tmp" "$dest"; then
        rm -f -- "$tmp"
        chmod "$mode" "$dest" 2>/dev/null || true
        V2_LAST_ATOMIC_CHANGED=0
        return 0
    fi
    if ! mv -f "$tmp" "$dest"; then
        rm -f -- "$tmp"
        return 1
    fi
    V2_LAST_ATOMIC_CHANGED=1
}

# render_template SRC DEST MODE KEY=VALUE...
# Yer tutucu: __KEY__
render_template() {
    local src="${1:?}" dest="${2:?}" mode="${3:?}"
    shift 3
    [[ -f "$src" ]] || die "şablon yok: $src"
    local content key value restore_patsub=0
    # Bash 5.2's replacement & means the matched token; Bash 3.2 has no option.
    # Keep template values literal without changing the caller's shell setting.
    if shopt -q patsub_replacement 2>/dev/null; then
        restore_patsub=1
        shopt -u patsub_replacement
    fi
    # $(...) sondaki newline'ları siler; şablonun fmt/EOF newline'ını koru.
    content="$(cat -- "$src"; printf x)"
    content="${content%x}"
    for pair in "$@"; do
        key="${pair%%=*}"
        value="${pair#*=}"
        [[ "$key" =~ ^[A-Z][A-Z0-9_]*$ ]] || die "geçersiz şablon anahtarı: $key"
        content="${content//__${key}__/$value}"
    done
    if [[ "$restore_patsub" == 1 ]]; then shopt -s patsub_replacement; fi
    if [[ "$content" =~ __[A-Z][A-Z0-9_]*__ ]]; then
        die "şablonda doldurulmamış yer tutucu kaldı: $src"
    fi
    # Stream straight into atomic_write: the old /tmp copy relied on a RETURN trap
    # that atomic_write's own trap replaced, leaking one file per call on Bash 5.
    atomic_write "$dest" "$mode" < <(printf '%s' "$content")
}
