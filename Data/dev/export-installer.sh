#!/usr/bin/env bash
# Kurulum çalışma dosyalarını gömülü tek bir macOS .command dosyasına paketler.
# Her export: Data/app/<V2_VERSION>.command + repo kökünde güncel sürümün kopyası
# (çift tıklanan dosya). İkisinde de yalnız güncel sürüm durur; eskiler Git geçmişinde (DD-154).
set -Eeuo pipefail

DEV_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# Kurulum ağacı Data/ altında; çift tıklanan dosyalar repo kökünde.
REPO_ROOT="$(cd -- "$DEV_DIR/.." && pwd)"
TOP_DIR="$(cd -- "$REPO_ROOT/.." && pwd)"
APP_DIR="$REPO_ROOT/app"
MARKER="__MASTER_STACK_ARCHIVE__"

V2_VERSION="$(awk -F= '/^V2_VERSION=/{gsub(/"/,"",$2); print $2; exit}' "$REPO_ROOT/install.sh")"
[[ -n "$V2_VERSION" ]] || { echo "HATA: V2_VERSION okunamadı" >&2; exit 1; }
# DD-119: girdinin sunucudaki yeri tek kaynaktan (defaults.env) gelir.
INPUT_DIR="$(awk -F= '/^INPUT_DIR=/{gsub(/"/,"",$2); print $2; exit}' "$REPO_ROOT/config/defaults.env")"
[[ "$INPUT_DIR" =~ ^/run/[A-Za-z0-9._/-]+$ ]] || { echo "HATA: INPUT_DIR /run altında değil: $INPUT_DIR" >&2; exit 1; }

OUT_NAME="${V2_VERSION}.command"
COPY_DESKTOP=0
OUT_PATH=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --desktop) COPY_DESKTOP=1; shift ;;
        -o|--output) OUT_PATH="$2"; shift 2 ;;
        -h|--help)
            cat <<EOF
Kullanım: $(basename "$0") [--desktop] [-o PATH]

  (varsayılan) Data/app/${V2_VERSION}.command — sürüm adıyla kaydet,
                repo köküne güncel kopya (kökteki önceki sürüm kaldırılır)
  --desktop     aynı dosyayı ~/Desktop (veya ~/Masaüstü) altına da kopyala
  -o PATH       çıktı yolunu elle seç
EOF
            exit 0
            ;;
        *) echo "HATA: bilinmeyen argüman: $1" >&2; exit 1 ;;
    esac
done

[[ -n "$OUT_PATH" ]] || OUT_PATH="$APP_DIR/$OUT_NAME"

file_sha256() {
    local f="$1"
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$f" | awk '{print $1}'
    else
        shasum -a 256 "$f" | awk '{print $1}'
    fi
}

tmpdir="$(mktemp -d "${TMPDIR:-/tmp}/dsi-portable.XXXXXX")"
cleanup() { rm -rf "$tmpdir"; }
trap cleanup EXIT

tgz="$tmpdir/installer.tgz"
stage="$tmpdir/src"
mkdir -p "$stage/installer"
echo "==> Paketleniyor: kurulum çalışma dosyaları ($V2_VERSION) [deterministik]"
# Sabit mtime + gzip -n → aynı kaynak = aynı ARCHIVE_SHA256.
# TZ=UTC + 2000-01-01: doğu TZ'de 1970-01-01 local Unix epoch öncesi olur
# (mtime 0 → Debian tar "implausibly old"). --no-xattrs/--no-mac-metadata:
# Apple provenance pax başlıkları Debian'da LIBARCHIVE uyarısı üretmesin.
rsync -a \
    --exclude='._*' \
    --exclude='.DS_Store' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    "$REPO_ROOT/install.sh" \
    "$REPO_ROOT/common.sh" \
    "$REPO_ROOT/config" \
    "$REPO_ROOT/templates" \
    "$REPO_ROOT/scripts" \
    "$REPO_ROOT/systemd" \
    "$REPO_ROOT/panel" \
    "$REPO_ROOT/files-panel" \
    "$REPO_ROOT/console" \
    "$REPO_ROOT/magaza" \
    "$stage/installer/"
xattr -cr "$stage" 2>/dev/null || true
TZ=UTC find "$stage" -exec touch -t 200001010000 {} +
(
    cd -- "$stage" || exit 1
    COPYFILE_DISABLE=1 tar \
        --format=ustar \
        --no-xattrs \
        --no-mac-metadata \
        --uid 0 --gid 0 \
        --uname root --gname root \
        -cf - installer | gzip -n >"$tgz"
)

ARCHIVE_SHA256="$(file_sha256 "$tgz")"
[[ "$ARCHIVE_SHA256" =~ ^[0-9a-f]{64}$ ]] || {
    echo "HATA: arşiv sha256 üretilemedi" >&2
    exit 1
}

b64="$tmpdir/installer.b64"
base64 <"$tgz" | tr -d '\n' >"$b64"
fold -w 76 "$b64" >"$b64.folded"
mv "$b64.folded" "$b64"

mkdir -p "$(dirname -- "$OUT_PATH")"
# Duvar saati .command hash'ini kirletmesin; sürüm kimliği yeterli.
built_at="reproducible/${V2_VERSION}"

{
    cat <<'HEADER_END'
#!/usr/bin/env bash
# Master Stack — taşınabilir tek dosya kurulum (macOS .command)
# Kurulum girdileri yanındaki kurulum/kurulum.env'den gelir (DD-119;
# şablon: Data/config/kurulum.env.example).
# Yeniden üretmek: dev/export-installer.sh
set -Eeuo pipefail

HEADER_END
    cat <<EOF
PORTABLE_INSTALLER_VERSION="$V2_VERSION"
PORTABLE_BUILT_AT="$built_at"
PORTABLE_ARCHIVE_SHA256="$ARCHIVE_SHA256"
ARCHIVE_MARKER="$MARKER"
REMOTE_INPUT_DIR="$INPUT_DIR"
EOF
    cat <<'BODY_END'

REMOTE_TGZ="/tmp/debian-server-installer.tgz"
REMOTE_ROOT="/root/debian-server-installer"

pause_exit() {
    local rc="${1:-0}"
    echo
    read -r -p "Pencereyi kapatmak için Enter..." || true
    exit "$rc"
}

file_sha256() {
    local f="$1"
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$f" | awk '{print $1}'
    else
        shasum -a 256 "$f" | awk '{print $1}'
    fi
}

here="$(cd -- "$(dirname -- "$0")" && pwd)"
self="$here/$(basename -- "$0")"
[[ -f "$self" ]] || { echo "HATA: betik yolu bulunamadı: $self" >&2; pause_exit 1; }

# macOS mktemp X'leri yalnız şablonun sonundaysa değiştirir: "dsi-embed.XXXXXX.tgz"
# birebir o adla açılır ve yarıda kalan bir çalıştırmadan sonra bütün çalıştırmalar
# "File exists" ile düşer. Arşiv her seferinde yeni, özel bir dizinde durur.
tgz_dir="$(mktemp -d "${TMPDIR:-/tmp}/dsi-embed.XXXXXX")"
tgz="$tgz_dir/installer.tgz"
remote_input_sent=0
# Kurulum girdileri okur okumaz siler; bu yalnız yarıda kalan bir oturumdan
# artakalanı temizler.
cleanup_local() {
    rm -rf -- "$tgz_dir"
    if [[ "$remote_input_sent" -eq 1 ]]; then
        ssh "${ssh_base[@]}" "$HOST" \
            "rm -rf '$REMOTE_INPUT_DIR' '$REMOTE_INPUT_DIR.incoming'" >/dev/null 2>&1 || true
    fi
}
trap cleanup_local EXIT

printf '\n=== Master Stack — taşınabilir kurulum ===\n'
printf 'Sürüm:  %s\n' "$PORTABLE_INSTALLER_VERSION"
printf 'Üretim: %s\n' "$PORTABLE_BUILT_AT"
printf 'SHA256: %s\n\n' "$PORTABLE_ARCHIVE_SHA256"

# DD-119: bütün girdiler .command'ın yanındaki kurulum/kurulum.env'de. Burada
# yalnız varlığı, izni ve SSH_HOST okunur; alan doğrulaması
# sunucuda kurulumun kendisindedir. DD-143: sunucuya yalnız bu dosya gider —
# VPN ağları ve cihazları sunucuda Konsol ile (paketin aracıyla) kurulur, Mac'ten
# hiçbir anahtar ya da profil taşınmaz.
INPUT_LOCAL_DIR="$here/kurulum"
INPUT_FILE_LOCAL="$INPUT_LOCAL_DIR/kurulum.env"
if [[ ! -f "$INPUT_FILE_LOCAL" ]]; then
    echo "HATA: girdi dosyası yok: $INPUT_FILE_LOCAL" >&2
    echo "  Şablon: Data/config/kurulum.env.example — kurulum/kurulum.env olarak kopyalayıp doldurun," >&2
    echo "  ardından: chmod 600 kurulum/kurulum.env" >&2
    pause_exit 1
fi
input_mode="$(stat -f %Lp "$INPUT_FILE_LOCAL")"
if [[ "$input_mode" != 600 && "$input_mode" != 400 ]]; then
    echo "HATA: $INPUT_FILE_LOCAL izinleri $input_mode; özel kurulum girdisi 600 olmalı:" >&2
    echo "  chmod 600 \"$INPUT_FILE_LOCAL\"" >&2
    pause_exit 1
fi
HOST="$(awk 'index($0, "SSH_HOST=") == 1 {print substr($0, 10); exit}' "$INPUT_FILE_LOCAL")"
if [[ ! "$HOST" =~ ^[A-Za-z0-9._@-]+$ ]]; then
    echo "HATA: kurulum.env içinde SSH_HOST boş ya da geçersiz (ör. SSH_HOST=nrm)" >&2
    pause_exit 1
fi
echo "Sunucu:  $HOST (kurulum/kurulum.env)"

# DD-143: sunucuya yalnız girdi dosyası gider.
send_files="kurulum.env"
for rel in $send_files; do
    mode="$(stat -f %Lp "$INPUT_LOCAL_DIR/$rel")"
    if [[ "$mode" != 600 && "$mode" != 400 ]]; then
        echo "HATA: kurulum/$rel izinleri $mode; özel kurulum girdisi 600 olmalı:" >&2
        echo "  chmod 600 \"$INPUT_LOCAL_DIR/$rel\"" >&2
        pause_exit 1
    fi
done
echo "==> Gömülü arşiv açılıyor"
marker_line="$(grep -n "^${ARCHIVE_MARKER}$" "$self" | head -n1 | cut -d: -f1 || true)"
[[ -n "$marker_line" ]] || { echo "HATA: gömülü arşiv işareti yok" >&2; pause_exit 1; }
if ! tail -n +"$((marker_line + 1))" "$self" | base64 -D -o "$tgz" 2>/dev/null; then
    tail -n +"$((marker_line + 1))" "$self" | base64 --decode >"$tgz"
fi
[[ -s "$tgz" ]] || { echo "HATA: arşiv boş veya bozuk" >&2; pause_exit 1; }

got_sha="$(file_sha256 "$tgz")"
[[ "$got_sha" == "$PORTABLE_ARCHIVE_SHA256" ]] || {
    echo "HATA: arşiv sha256 uyuşmuyor" >&2
    echo "  beklenen: $PORTABLE_ARCHIVE_SHA256" >&2
    echo "  bulunan:  $got_sha" >&2
    pause_exit 1
}
echo "==> SHA256 doğrulandı"

ssh_base=(-o ClearAllForwardings=yes -o BatchMode=yes -o ConnectTimeout=20)

echo "==> SSH kontrol: $HOST"
ssh "${ssh_base[@]}" "$HOST" 'printf "OK user=%s host=%s\n" "$(id -un)" "$(hostname)"'

echo "==> Kopyalanıyor → ${HOST}:${REMOTE_TGZ}"
scp "${ssh_base[@]}" "$tgz" "${HOST}:${REMOTE_TGZ}"

echo "==> Sunucuda açılıyor (atomik + sha256)"
ssh "${ssh_base[@]}" "$HOST" bash -s <<EOF
set -Eeuo pipefail
expect='$PORTABLE_ARCHIVE_SHA256'
remote_tgz='$REMOTE_TGZ'
remote_root='$REMOTE_ROOT'
got="\$(sha256sum "\$remote_tgz" | awk '{print \$1}')"
[[ "\$got" == "\$expect" ]] || {
    echo "HATA: uzak arşiv sha256 uyuşmuyor (\$got)" >&2
    exit 1
}
staging="\$(mktemp -d /tmp/dsi-extract.XXXXXX)"
incoming="\${remote_root}.incoming.\$\$"
previous="\${remote_root}.previous.\$\$"
cleanup_staging() {
    rm -rf "\$staging" "\$incoming"
    if [[ ! -e "\$remote_root" && -e "\$previous" ]]; then
        mv "\$previous" "\$remote_root"
    fi
}
trap cleanup_staging EXIT
tar -C "\$staging" -xzf "\$remote_tgz"
[[ -f "\$staging/installer/install.sh" ]] || {
    echo "HATA: arşivde install.sh yok" >&2
    exit 1
}
rm -rf "\$incoming" "\$previous"
mv "\$staging/installer" "\$incoming"
if [[ -e "\$remote_root" ]]; then
    mv "\$remote_root" "\$previous"
fi
if ! mv "\$incoming" "\$remote_root"; then
    [[ ! -e "\$previous" ]] || mv "\$previous" "\$remote_root"
    exit 1
fi
rm -rf "\$previous"
trap - EXIT
rmdir "\$staging" 2>/dev/null || rm -rf "\$staging"
find "\$remote_root" -name '._*' -delete
find "\$remote_root" -name '.DS_Store' -delete
chmod 0755 "\$remote_root/install.sh"
chmod 0755 "\$remote_root/scripts/"*
bash -n "\$remote_root/install.sh"
grep -E '^V2_VERSION=' "\$remote_root/install.sh"
echo "SYNC_OK → \$remote_root"
EOF

# /run tmpfs değilse girdi diske inerdi: gönderilmez. Yalnız kurulum.env gider.
echo "==> Girdi gönderiliyor → ${HOST}:${REMOTE_INPUT_DIR} (tmpfs)"
remote_input_sent=1
# shellcheck disable=SC2086 # send_files: süzülmüş, boşluksuz göreli yollar
COPYFILE_DISABLE=1 tar -C "$INPUT_LOCAL_DIR" --no-xattrs --no-mac-metadata -cf - $send_files |
    ssh "${ssh_base[@]}" "$HOST" "set -e; umask 077; install -d -m 0700 '${REMOTE_INPUT_DIR%/*}'; \
fs=\$(stat -f -c %T '${REMOTE_INPUT_DIR%/*}'); \
[ \"\$fs\" = tmpfs ] || { echo \"HATA: ${REMOTE_INPUT_DIR%/*} tmpfs değil (\$fs); girdiler gönderilmedi\" >&2; exit 1; }; \
rm -rf '$REMOTE_INPUT_DIR' '$REMOTE_INPUT_DIR.incoming'; mkdir -m 0700 '$REMOTE_INPUT_DIR.incoming'; \
tar -C '$REMOTE_INPUT_DIR.incoming' --no-same-owner -xf -; mv '$REMOTE_INPUT_DIR.incoming' '$REMOTE_INPUT_DIR'"

printf '\n==> Kurulum başlıyor: %s\n' "$HOST"
printf '    Özeti kontrol edip onaya E yazın. Tailscale URL gelirse tarayıcıda onaylayın.\n'
printf '    Uygulamalar kurulumdan sonra Konsol → App Store'"'"'dan kurulur.\n\n'

set +e
ssh \
    -o ClearAllForwardings=yes \
    -o ConnectTimeout=20 \
    -t \
    "$HOST" \
    "bash '$REMOTE_ROOT/install.sh'"
rc=$?
set -e


echo
if [[ "$rc" -eq 0 ]]; then
    echo "Kurulum oturumu bitti (exit 0)."
else
    echo "Kurulum oturumu bitti (exit $rc)." >&2
fi
pause_exit "$rc"

BODY_END
    printf '%s\n' "$MARKER"
    cat "$b64"
    printf '\n'
} >"$OUT_PATH"

chmod 0755 "$OUT_PATH"
xattr -d com.apple.quarantine "$OUT_PATH" 2>/dev/null || true

bytes="$(wc -c <"$OUT_PATH" | tr -d ' ')"
echo "==> Yazıldı: $OUT_PATH ($bytes bayt)"
echo "==> SHA256 (gömülü arşiv): $ARCHIVE_SHA256"

# Repo kökünde ve Data/app/'ta yalnız güncel sürüm durur; önceki sürümler kalkar (Git
# geçmişinde kalırlar, DD-154).
if [[ "$(cd -- "$(dirname -- "$OUT_PATH")" && pwd)" == "$(cd -- "$APP_DIR" && pwd)" ]]; then
    for old in "$TOP_DIR"/20[0-9][0-9].[0-9][0-9].[0-9][0-9]-v2-*.command \
        "$APP_DIR"/20[0-9][0-9].[0-9][0-9].[0-9][0-9]-v2-*.command; do
        if [[ -f "$old" && "$(basename -- "$old")" != "$OUT_NAME" ]]; then rm -f -- "$old"; fi
    done
    cp -f "$OUT_PATH" "$TOP_DIR/$OUT_NAME"
    chmod 0755 "$TOP_DIR/$OUT_NAME"
    xattr -d com.apple.quarantine "$TOP_DIR/$OUT_NAME" 2>/dev/null || true
    echo "==> kök: $TOP_DIR/$OUT_NAME"
fi

if [[ "$COPY_DESKTOP" -eq 1 ]]; then
    desk="${HOME}/Desktop"
    [[ -d "$desk" ]] || desk="${HOME}/Masaüstü"
    if [[ -d "$desk" ]]; then
        cp -f "$OUT_PATH" "$desk/$OUT_NAME"
        chmod 0755 "$desk/$OUT_NAME"
        xattr -d com.apple.quarantine "$desk/$OUT_NAME" 2>/dev/null || true
        echo "==> Masaüstü: $desk/$OUT_NAME"
    else
        echo "UYARI: Masaüstü klasörü bulunamadı; yalnız $OUT_PATH yazıldı" >&2
    fi
fi
