#!/bin/bash
# Konsol'a ulaşılamadığında sunucuyu denetler ve onarır (DD-239). Repo kökünde çift tıklanır; sunucudaki
# master-onar'ı SSH ile çalıştırır, Konsol'un Ayarlar → Sistem → Sağlık → "Denetle ve onar" düğmesiyle aynı
# işi yapar ve her adımı terminale yazar. kurulum/kurulum.env'den yalnız SSH_HOST okunur; Mac'te hiçbir
# şey saklanmaz. Finder bu dosyayı macOS /bin/bash 3.2 ile çalıştırır.
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "$0")" && pwd)"
INPUT_FILE="$ROOT/kurulum/kurulum.env"
DEFAULTS_FILE="$ROOT/Data/config/defaults.env"

pause_exit() {
    echo
    read -r -p "Pencereyi kapatmak için Enter..." || true
    exit "${1:-0}"
}

fail() {
    printf 'HATA: %s\n' "$*" >&2
    pause_exit 1
}

[[ -f "$DEFAULTS_FILE" ]] || fail "Data/ bulunamadı; betiği repo kökünden çalıştırın."
[[ -f "$INPUT_FILE" ]] || fail "girdi dosyası yok: $INPUT_FILE"
HOST="$(awk 'index($0, "SSH_HOST=") == 1 {print substr($0, 10); exit}' "$INPUT_FILE")"
[[ "$HOST" =~ ^[A-Za-z0-9._@-]+$ ]] || fail "kurulum.env içinde SSH_HOST boş ya da geçersiz"
SBIN_DIR="$(awk -F= '$1 == "SBIN_DIR" {v = substr($0, 10); gsub(/^"|"$/, "", v); print v; exit}' "$DEFAULTS_FILE")"
[[ "$SBIN_DIR" =~ ^/[A-Za-z0-9/._-]+$ ]] || fail "defaults.env içinde SBIN_DIR okunamadı"

printf '\n--- %s · denetle ve onar ---\n' "$HOST"
echo "1) Denetle ve onar (bozuk servisleri yeniden başlatır, güvenlik duvarını yeniden kurar)"
echo "2) Yalnız denetle (hiçbir şeyi değiştirmez)"
echo "3) Çık"
read -r -p "Seçim [1]: " choice || true
case "${choice:-1}" in
    1) mode="" ;;
    2) mode="--denetle" ;;
    *) exit 0 ;;
esac

# Sunucuda root değilse sudo sorar (-t: parola istemi bu pencerede görünür).
tool="$(printf '%q' "$SBIN_DIR/master-onar")"
remote="if [ \"\$(id -u)\" -eq 0 ]; then exec $tool $mode; else exec sudo $tool $mode; fi"
rc=0
ssh -t -o ConnectTimeout=20 -o ServerAliveInterval=15 -o ServerAliveCountMax=3 "$HOST" "$remote" || rc=$?
case "$rc" in
    0) echo; echo "Tamam: sorun yok ya da onarıldı." ;;
    1) echo; echo "Bazı adımlar onarılamadı; yukarıdaki satırlara bakın." ;;
    3) echo; echo "Sunucuda başka bir onarım sürüyor; biraz sonra yeniden deneyin." ;;
    255) echo; echo "SSH bağlantısı kurulamadı ($HOST)." ;;
esac
pause_exit "$rc"
