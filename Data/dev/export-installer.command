#!/usr/bin/env bash
# Çift tık: kurulumu taşınabilir app olarak export et → Data/app/<sürüm>.command,
# repo kökünde güncel kopya + Masaüstü
set -Eeuo pipefail

cd -- "$(dirname -- "$0")"
./export-installer.sh --desktop

V2_VERSION="$(awk -F= '/^V2_VERSION=/{gsub(/"/,"",$2); print $2; exit}' ../install.sh)"
APP_FILE="../app/${V2_VERSION}.command"

cat <<EOF

Export tamam.

  • Arşiv:    $APP_FILE
  • Kök:      ../../${V2_VERSION}.command
  • Masaüstü: ~/{Desktop|Masaüstü}/${V2_VERSION}.command

EOF

read -r -p "Şimdi kurulumu başlat? [E/h]: " ans || true
ans="${ans:-E}"
if [[ "$ans" =~ ^[EeYy]$ ]]; then
    exec "$APP_FILE"
fi
read -r -p "Pencereyi kapatmak için Enter..."
