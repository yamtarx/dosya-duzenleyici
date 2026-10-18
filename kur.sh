#!/usr/bin/env bash
# Dosya Düzenleyici kurulum betiği (Linux Mint / systemd kullanıcı servisi + grafik arayüz)
set -euo pipefail

DIZIN="$(cd "$(dirname "$0")" && pwd)"
PAYLASIM="$HOME/.local/share/dosya-duzenleyici"
BIN_DIZIN="$HOME/.local/bin"
AYAR_DIZIN="$HOME/.config/dosya-duzenleyici"
SERVIS_DIZIN="$HOME/.config/systemd/user"
SERVIS="$SERVIS_DIZIN/dosya-duzenleyici.service"
MENU="$HOME/.local/share/applications/dosya-duzenleyici.desktop"

mkdir -p "$PAYLASIM" "$BIN_DIZIN" "$AYAR_DIZIN" "$SERVIS_DIZIN" "$(dirname "$MENU")"

install -m 755 "$DIZIN/dosya_duzenleyici.py" "$PAYLASIM/dosya_duzenleyici.py"
install -m 755 "$DIZIN/dosya_duzenleyici_gui.py" "$PAYLASIM/dosya_duzenleyici_gui.py"
install -m 644 "$DIZIN/config.json" "$PAYLASIM/config.json"
ln -sf "$PAYLASIM/dosya_duzenleyici.py" "$BIN_DIZIN/dosya-duzenleyici"
ln -sf "$PAYLASIM/dosya_duzenleyici_gui.py" "$BIN_DIZIN/dosya-duzenleyici-gui"
echo "✓ Program kuruldu: $PAYLASIM"

if [ -f "$AYAR_DIZIN/config.json" ]; then
    echo "• Mevcut ayar dosyası korundu: $AYAR_DIZIN/config.json"
else
    cp "$DIZIN/config.json" "$AYAR_DIZIN/config.json"
    echo "✓ Ayar dosyası oluşturuldu: $AYAR_DIZIN/config.json"
fi

cat > "$SERVIS" <<EOF
[Unit]
Description=Dosya Düzenleyici - indirilen dosyaları türlerine göre taşır
After=graphical-session.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 $PAYLASIM/dosya_duzenleyici.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF

cat > "$MENU" <<EOF
[Desktop Entry]
Type=Application
Name=Dosya Düzenleyici
Comment=İndirilen dosyaları türlerine göre klasörlere yönlendir
Exec=/usr/bin/python3 $PAYLASIM/dosya_duzenleyici_gui.py
Icon=folder-download
Terminal=false
Categories=Utility;FileTools;
Keywords=indirme;download;düzenle;organize;klasör;
EOF
update-desktop-database "$(dirname "$MENU")" 2>/dev/null || true
echo "✓ Uygulama menüsüne eklendi: Dosya Düzenleyici"

systemctl --user daemon-reload
if systemctl --user is-enabled --quiet dosya-duzenleyici.service 2>/dev/null; then
    systemctl --user restart dosya-duzenleyici.service
    echo "✓ Arka plan servisi güncellendi ve yeniden başlatıldı."
else
    echo "• Arka plan servisi hazır. Grafik arayüzdeki anahtarla açabilirsiniz."
fi
