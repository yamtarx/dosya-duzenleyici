# Dosya Düzenleyici

İndirme klasörünü izler ve indirmesi biten dosyaları uzantılarına göre belirlediğiniz klasörlere taşır.
Yalnızca Python 3 kullanır, ek paket gerekmez.

## Kurulum
```bash
bash kur.sh
```
Kurulumdan sonra uygulama menüsünde **Dosya Düzenleyici** görünür (veya terminalde `dosya-duzenleyici-gui`).

## Grafik arayüz
- **Anahtar (sağ üst):** Otomatik düzenlemeyi açar/kapatır. Açıkken pencereyi kapatsanız da arka planda
  çalışmaya ve oturum açılışında otomatik başlamaya devam eder.
- **İzlenen klasörler:** Tarayıcının indirdiği klasör(ler).
- **Yönlendirme kuralları:** Her satıra bir ad, uzantılar (virgülle) ve hedef klasör girin. "Kaydet ve uygula"ya basın.
- **Mevcut dosyaları şimdi düzenle:** Klasörde zaten bulunan dosyaları önizleme gösterip taşır.
- **Son etkinlikler:** Hangi dosyanın nereye taşındığını gösterir.

Arka planda çalışan servis `systemd --user` ile yönetilir; ayarlar
`~/.config/dosya-duzenleyici/config.json` dosyasında tutulur.

## Ayarlar (`~/.config/dosya-duzenleyici/config.json`)
| Anahtar | Açıklama |
|---|---|
| `izlenen_klasorler` | İzlenecek klasörler. `$XDG_DOWNLOAD` sistemdeki İndirilenler klasörü anlamına gelir. |
| `kurallar` | `hedef` klasör + `uzantilar` listesi. `tar.gz` gibi çok parçalı uzantılar desteklenir. |
| `eslesmeyen_dosyalar_klasoru` | Hiçbir kurala uymayan dosyalar buraya gider; `null` ise yerinde kalır. |
| `sabit_kalma_suresi_saniye` | Dosya bu süre boyunca değişmezse indirmesi bitmiş sayılır. |
| `baslangicta_mevcut_dosyalari_duzenle` | `true` ise servis başlarken klasördeki eski dosyaları da taşır. |
| `masaustu_bildirimi` | Taşınan her dosya için bildirim gösterir. |

Ayar dosyası kaydedildiğinde otomatik olarak yeniden yüklenir; servisi yeniden başlatmanız gerekmez.

## Faydalı komutlar
```bash
dosya-duzenleyici --dry-run            # Mevcut dosyalarla ne yapılacağını göster (taşımaz)
dosya-duzenleyici --once               # Mevcut dosyaları bir kez düzenle
systemctl --user status dosya-duzenleyici
journalctl --user -u dosya-duzenleyici -f
tail -f ~/.local/state/dosya-duzenleyici/dosya-duzenleyici.log
bash kaldir.sh                         # Kaldır
```

## Notlar
- `.crdownload`, `.part`, `.opdownload` gibi yarım indirmeler beklenir, bitmeden taşınmaz.
- Hedefte aynı isimde dosya varsa üzerine yazılmaz; `dosya (1).png` şeklinde yeniden adlandırılır.
- Alt klasörlere dokunulmaz, yalnızca izlenen klasörün kendisindeki dosyalar işlenir.
