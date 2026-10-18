#!/usr/bin/env python3
"""
Dosya Düzenleyici - İndirilen dosyaları türlerine göre otomatik olarak klasörlere taşır.

Kullanım:
    dosya_duzenleyici.py              # Sürekli izle (servis modu)
    dosya_duzenleyici.py --once       # Mevcut dosyaları bir kez düzenle ve çık
    dosya_duzenleyici.py --dry-run    # Ne yapılacağını göster, taşıma yapma
    dosya_duzenleyici.py --config YOL # Farklı bir ayar dosyası kullan

Harici bağımlılık yoktur; yalnızca Python 3 standart kütüphanesi kullanılır.
"""

import argparse
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

VARSAYILAN_AYAR = Path.home() / ".config" / "dosya-duzenleyici" / "config.json"
LOG_DOSYASI = Path.home() / ".local" / "state" / "dosya-duzenleyici" / "dosya-duzenleyici.log"

# Tarayıcıların indirme sırasında kullandığı geçici uzantılar
GECICI_UZANTILAR = {
    ".crdownload",  # Chrome / Chromium / Brave / Edge
    ".part",        # Firefox
    ".partial",     # eski Firefox / bazı indiriciler
    ".download",    # Safari / bazı tarayıcılar
    ".opdownload",  # Opera
    ".tmp",
    ".temp",
    ".!qb",         # qBittorrent
    ".aria2",
}

log = logging.getLogger("dosya-duzenleyici")
_calisiyor = True


def _dur(signum, frame):
    global _calisiyor
    log.info("Durdurma sinyali alındı (%s), çıkılıyor...", signum)
    _calisiyor = False


def genislet(yol: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(yol)))


def xdg_indirme_klasoru() -> Path:
    try:
        cikti = subprocess.run(["xdg-user-dir", "DOWNLOAD"], capture_output=True, text=True, timeout=5)
        yol = cikti.stdout.strip()
        if yol:
            return Path(yol)
    except Exception:
        pass
    return Path.home() / "Downloads"


class Ayarlar:
    def __init__(self, yol: Path):
        self.yol = yol
        with open(yol, encoding="utf-8") as f:
            veri = json.load(f)

        izlenen = veri.get("izlenen_klasorler") or ["$XDG_DOWNLOAD"]
        self.izlenen_klasorler = []
        for k in izlenen:
            p = xdg_indirme_klasoru() if k == "$XDG_DOWNLOAD" else genislet(k)
            self.izlenen_klasorler.append(p)

        self.tarama_araligi = float(veri.get("tarama_araligi_saniye", 3))
        self.bekleme_suresi = float(veri.get("sabit_kalma_suresi_saniye", 5))
        self.mevcutlari_duzenle = bool(veri.get("baslangicta_mevcut_dosyalari_duzenle", False))
        self.bildirim = bool(veri.get("masaustu_bildirimi", True))
        self.gizli_dosyalari_atla = bool(veri.get("gizli_dosyalari_atla", True))

        diger = veri.get("eslesmeyen_dosyalar_klasoru")
        self.diger_klasor = genislet(diger) if diger else None

        # uzantı -> hedef klasör eşlemesi
        self.uzanti_haritasi: dict[str, Path] = {}
        for kural in veri.get("kurallar", []):
            hedef = genislet(kural["hedef"])
            for uz in kural.get("uzantilar", []):
                uz = uz.lower().strip()
                if not uz.startswith("."):
                    uz = "." + uz
                self.uzanti_haritasi[uz] = hedef

    def hedef_bul(self, dosya: Path) -> Path | None:
        ad = dosya.name.lower()
        # Çok parçalı uzantılar için en uzun eşleşmeyi dene (.tar.gz gibi)
        en_iyi = None
        for uz, hedef in self.uzanti_haritasi.items():
            if ad.endswith(uz) and (en_iyi is None or len(uz) > len(en_iyi[0])):
                en_iyi = (uz, hedef)
        if en_iyi:
            return en_iyi[1]
        return self.diger_klasor


def gecici_mi(dosya: Path) -> bool:
    ad = dosya.name.lower()
    if any(ad.endswith(u) for u in GECICI_UZANTILAR):
        return True
    # Firefox indirme sırasında asıl dosyanın yanında "dosya.part" tutar
    for u in (".part", ".crdownload"):
        if dosya.with_name(dosya.name + u).exists():
            return True
    return False


def benzersiz_yol(hedef: Path) -> Path:
    if not hedef.exists():
        return hedef
    kok, uz = hedef.stem, hedef.suffix
    # .tar.gz gibi uzantıları koru
    if kok.lower().endswith(".tar"):
        kok, uz = kok[:-4], ".tar" + uz
    i = 1
    while True:
        aday = hedef.with_name(f"{kok} ({i}){uz}")
        if not aday.exists():
            return aday
        i += 1


def bildir(baslik: str, mesaj: str):
    try:
        subprocess.Popen(
            ["notify-send", "-a", "Dosya Düzenleyici", "-i", "folder-download", baslik, mesaj],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        pass


class Duzenleyici:
    def __init__(self, ayarlar: Ayarlar, dry_run: bool = False):
        self.ayarlar = ayarlar
        self.dry_run = dry_run
        # dosya yolu -> (boyut, mtime, ilk_görülme_zamanı_bu_durumda)
        self.izlenen: dict[Path, tuple[int, float, float]] = {}
        self.yok_sayilan: set[Path] = set()  # hiçbir kurala uymayan dosyalar
        self.baslangic: set[Path] = set()    # servis başlarken zaten var olan dosyalar

    def adaylar(self):
        for klasor in self.ayarlar.izlenen_klasorler:
            if not klasor.is_dir():
                continue
            try:
                for giris in os.scandir(klasor):
                    if not giris.is_file(follow_symlinks=False):
                        continue
                    if self.ayarlar.gizli_dosyalari_atla and giris.name.startswith("."):
                        continue
                    yield Path(giris.path)
            except OSError as e:
                log.warning("Klasör okunamadı %s: %s", klasor, e)

    def tasi(self, dosya: Path) -> bool:
        hedef_klasor = self.ayarlar.hedef_bul(dosya)
        if hedef_klasor is None:
            return False
        if hedef_klasor.resolve() == dosya.parent.resolve():
            return False
        hedef = benzersiz_yol(hedef_klasor / dosya.name)
        if self.dry_run:
            log.info("[DENEME] %s -> %s", dosya, hedef)
            return True
        try:
            hedef_klasor.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dosya), str(hedef))
            log.info("Taşındı: %s -> %s", dosya.name, hedef)
            if self.ayarlar.bildirim:
                bildir("Dosya taşındı", f"{dosya.name}\n→ {hedef_klasor}")
            return True
        except Exception as e:
            log.error("Taşınamadı %s: %s", dosya, e)
            return False

    def bir_kez(self):
        """Mevcut tüm dosyaları (indirmesi bitmiş olanları) hemen düzenler."""
        sayac = 0
        for dosya in self.adaylar():
            if gecici_mi(dosya):
                continue
            if self.tasi(dosya):
                sayac += 1
        log.info("Toplam %d dosya işlendi.", sayac)

    def tara(self):
        simdi = time.monotonic()
        gorulen = set()
        for dosya in self.adaylar():
            gorulen.add(dosya)
            if dosya in self.yok_sayilan or dosya in self.baslangic or gecici_mi(dosya):
                continue
            try:
                st = dosya.stat()
            except FileNotFoundError:
                continue
            onceki = self.izlenen.get(dosya)
            if onceki is None or onceki[0] != st.st_size or onceki[1] != st.st_mtime:
                # Yeni dosya ya da hâlâ değişiyor: sayacı sıfırla
                self.izlenen[dosya] = (st.st_size, st.st_mtime, simdi)
                continue
            if simdi - onceki[2] >= self.ayarlar.bekleme_suresi:
                self.izlenen.pop(dosya, None)
                if not self.tasi(dosya):
                    self.yok_sayilan.add(dosya)  # eşleşmeyen dosyaları tekrar deneme
        # Kaybolan dosyaları listelerden temizle
        for d in list(self.izlenen):
            if d not in gorulen:
                del self.izlenen[d]
        self.yok_sayilan &= gorulen
        self.baslangic &= gorulen

    def calistir(self):
        log.info("İzlenen klasörler: %s", ", ".join(map(str, self.ayarlar.izlenen_klasorler)))
        if self.ayarlar.mevcutlari_duzenle:
            self.bir_kez()
        else:
            # Başlangıçta var olan dosyalara dokunma
            self.baslangic = set(self.adaylar())
        ayar_mtime = self.ayarlar.yol.stat().st_mtime
        while _calisiyor:
            try:
                self.tara()
                # Ayar dosyası değiştiyse yeniden yükle
                yeni = self.ayarlar.yol.stat().st_mtime
                if yeni != ayar_mtime:
                    ayar_mtime = yeni
                    try:
                        self.ayarlar = Ayarlar(self.ayarlar.yol)
                        self.yok_sayilan.clear()  # yeni kurallarla tekrar dene
                        log.info("Ayarlar yeniden yüklendi.")
                    except Exception as e:
                        log.error("Ayar dosyası hatalı, eski ayarlar kullanılıyor: %s", e)
            except Exception as e:
                log.exception("Beklenmeyen hata: %s", e)
            time.sleep(self.ayarlar.tarama_araligi)


def main():
    p = argparse.ArgumentParser(description="İndirilen dosyaları türlerine göre otomatik düzenler.")
    p.add_argument("--config", type=Path, default=VARSAYILAN_AYAR, help="Ayar dosyası yolu")
    p.add_argument("--once", action="store_true", help="Mevcut dosyaları bir kez düzenle ve çık")
    p.add_argument("--dry-run", action="store_true", help="Taşıma yapmadan ne yapılacağını göster")
    args = p.parse_args()

    log_yolu = Path(os.environ.get("DOSYA_DUZENLEYICI_LOG", LOG_DOSYASI))
    handlers = [logging.StreamHandler(sys.stdout)]
    try:
        log_yolu.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_yolu, encoding="utf-8"))
    except OSError as e:
        print(f"Uyarı: log dosyası açılamadı ({e}), yalnızca ekrana yazılacak.", file=sys.stderr)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers,
    )

    if not args.config.exists():
        log.error("Ayar dosyası bulunamadı: %s", args.config)
        sys.exit(1)

    signal.signal(signal.SIGTERM, _dur)
    signal.signal(signal.SIGINT, _dur)

    duzenleyici = Duzenleyici(Ayarlar(args.config), dry_run=args.dry_run)
    if args.once or args.dry_run:
        duzenleyici.bir_kez()
    else:
        duzenleyici.calistir()


if __name__ == "__main__":
    main()
