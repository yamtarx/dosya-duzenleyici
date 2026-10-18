#!/usr/bin/env bash
# Dosya Düzenleyici kaldırma betiği (ayar dosyası ve taşınmış dosyalar silinmez)
set -uo pipefail
systemctl --user disable --now dosya-duzenleyici.service 2>/dev/null
rm -f "$HOME/.config/systemd/user/dosya-duzenleyici.service" \
      "$HOME/.local/bin/dosya-duzenleyici" "$HOME/.local/bin/dosya-duzenleyici-gui" \
      "$HOME/.local/share/applications/dosya-duzenleyici.desktop"
rm -rf "$HOME/.local/share/dosya-duzenleyici"
systemctl --user daemon-reload
echo "✓ Kaldırıldı. Ayarlar burada duruyor: ~/.config/dosya-duzenleyici/"
