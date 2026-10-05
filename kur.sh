#!/usr/bin/env bash
# Master Stack — sunucuda tek satırla kurulum (DD-228).
#
#   curl -fsSL https://raw.githubusercontent.com/drs0me1/myserver/main/kur.sh | sudo bash
#
# Kodu GitHub'dan (varsayılan main; başka bir sürüm için: sudo KUR_REF=<commit|etiket> bash)
# indirir, /root/debian-server-installer'a atomik yerleştirir ve install.sh'ı terminalden
# başlatır. Sorular, Tailscale giriş bağlantısı ve onay terminalde kalır.
# Konsol'daki "Güncelle" düğmesi (DD-233) bu betiği master-guncelle ile çağırır: KUR_REF bir
# commit, KUR_GUNCELLE o commit'teki V2_VERSION'dır; kurulum terminalsiz güncelleme kipinde çalışır.
# Bütün gövde main() içindedir: yarıda kesilen bir indirme yarım betik çalıştırmaz.
set -Eeuo pipefail

main() {
    local repo="drs0me1/myserver"
    local ref="${KUR_REF:-main}"
    # KUR_URL yalnız testler içindir (yerel arşiv); kurulumda boş kalır.
    local url="${KUR_URL:-https://codeload.github.com/$repo/tar.gz/$ref}"
    local root="${KUR_ROOT:-/root/debian-server-installer}"
    local update="${KUR_GUNCELLE:-}"
    # Kurulumun çalışma dosyaları; dokümanlar ve testler sunucuya gitmez.
    local items="install.sh common.sh config templates scripts systemd panel files-panel console magaza"

    printf '\n=== Master Stack — kurulum ===\n'
    [[ "$(id -u)" -eq 0 ]] || {
        echo "HATA: root gerekli. Şöyle çalıştırın: curl -fsSL <bağlantı> | sudo bash" >&2
        exit 1
    }
    [[ "$ref" =~ ^[A-Za-z0-9._/-]+$ ]] || { echo "HATA: geçersiz KUR_REF: $ref" >&2; exit 1; }
    local tool
    for tool in curl tar sha256sum; do
        command -v "$tool" >/dev/null 2>&1 || { echo "HATA: $tool yok (apt install -y $tool)" >&2; exit 1; }
    done
    if [[ -n "$update" ]]; then
        [[ "$ref" =~ ^[0-9a-f]{40}$ ]] || { echo "HATA: güncelleme bir commit'e sabitlenmeli: $ref" >&2; exit 1; }
        [[ "$update" =~ ^[0-9]{4}\.[0-9]{2}\.[0-9]{2}-v2-[0-9]+$ ]] || { echo "HATA: geçersiz sürüm: $update" >&2; exit 1; }
    else
        [[ -r /dev/tty ]] || { echo "HATA: etkileşimli terminal gerekli (ssh -t ile bağlanın)" >&2; exit 1; }
    fi

    local tmp
    tmp="$(mktemp -d /tmp/master-stack-kur.XXXXXX)"
    # shellcheck disable=SC2064 # tmp şimdi sabitlenir
    trap "rm -rf -- '$tmp'" EXIT

    echo "==> İndiriliyor: $repo ($ref)"
    curl -fsSL --proto '=https,file' --retry 3 --max-time 300 -o "$tmp/kod.tgz" "$url" ||
        { echo "HATA: indirilemedi: $url" >&2; exit 1; }
    printf 'SHA256: %s\n' "$(sha256sum "$tmp/kod.tgz" | awk '{print $1}')"

    mkdir "$tmp/acik"
    tar -C "$tmp/acik" --no-same-owner --exclude='__pycache__' --exclude='*.pyc' -xzf "$tmp/kod.tgz"
    local src
    src="$(find "$tmp/acik" -mindepth 3 -maxdepth 3 -path '*/Data/install.sh' -print -quit)"
    [[ -n "$src" ]] || { echo "HATA: arşivde Data/install.sh yok" >&2; exit 1; }
    src="${src%/install.sh}"

    local incoming="$root.incoming.$$" previous="$root.previous.$$" item
    rm -rf -- "$incoming" "$previous"
    mkdir -m 0700 "$incoming"
    for item in $items; do
        [[ -e "$src/$item" ]] || { rm -rf -- "$incoming"; echo "HATA: arşivde Data/$item yok" >&2; exit 1; }
        cp -R -- "$src/$item" "$incoming/"
    done
    chmod 0755 "$incoming/install.sh" "$incoming/scripts/"*
    bash -n "$incoming/install.sh" || { rm -rf -- "$incoming"; echo "HATA: install.sh sözdizimi bozuk" >&2; exit 1; }
    local version
    version="$(grep -m1 -E '^V2_VERSION=' "$incoming/install.sh")" ||
        { rm -rf -- "$incoming"; echo "HATA: install.sh sürüm satırı yok" >&2; exit 1; }
    # Güncelleme, Konsol'da onaylanan sürümden başkasını kurmaz.
    [[ -z "$update" || "$version" == "V2_VERSION=\"$update\"" ]] ||
        { rm -rf -- "$incoming"; echo "HATA: indirilen sürüm ($version) onaylanan $update değil" >&2; exit 1; }

    # Atomik yer değiştirme: yarıda kalırsa önceki kopya geri gelir.
    [[ ! -e "$root" ]] || mv -- "$root" "$previous"
    if ! mv -- "$incoming" "$root"; then
        [[ ! -e "$previous" ]] || mv -- "$previous" "$root"
        rm -rf -- "$incoming"
        echo "HATA: $root yerleştirilemedi" >&2
        exit 1
    fi
    rm -rf -- "$previous"
    echo "==> Yerleştirildi → $root ($version)"

    if [[ -n "$update" ]]; then
        printf '\n==> Güncelleme başlıyor (%s). Sistem önce güncellenir.\n' "$update"
        rm -rf -- "$tmp"
        trap - EXIT
        V2_GUNCELLEME=1 exec bash "$root/install.sh" </dev/null
    fi
    printf '\n==> Kurulum başlıyor. Sistem önce güncellenir.\n'
    printf '    Özeti kontrol edip onaya E yazın. Tailscale URL gelirse tarayıcıda onaylayın.\n'
    printf '    Uygulamalar kurulumdan sonra Konsol → App Store'"'"'dan kurulur.\n\n'
    rm -rf -- "$tmp"
    trap - EXIT
    exec bash "$root/install.sh" </dev/tty
}

main "$@"
