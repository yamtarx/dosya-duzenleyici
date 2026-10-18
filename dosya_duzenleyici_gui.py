#!/usr/bin/env python3
"""
Dosya Düzenleyici - Grafik arayüz (GTK3)

Kuralları (dosya türü -> hedef klasör) görsel olarak düzenler, ayarları kaydeder
ve arka planda çalışan otomatik düzenleme servisini açıp kapatır.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

UYGULAMA_ADI = "Dosya Düzenleyici"
SERVIS = "dosya-duzenleyici.service"
AYAR_DOSYASI = Path.home() / ".config" / "dosya-duzenleyici" / "config.json"
LOG_DOSYASI = Path.home() / ".local" / "state" / "dosya-duzenleyici" / "dosya-duzenleyici.log"
BURASI = Path(__file__).resolve().parent
VARSAYILAN_AYAR = BURASI / "config.json"
MOTOR_ADAYLARI = [Path.home() / ".local" / "bin" / "dosya-duzenleyici", BURASI / "dosya_duzenleyici.py"]
EV = str(Path.home())


def kisalt(yol: str) -> str:
    """'/home/kullanici/Resimler' -> '~/Resimler'"""
    yol = os.path.expanduser(yol)
    if yol == EV:
        return "~"
    if yol.startswith(EV + os.sep):
        return "~" + yol[len(EV):]
    return yol


def genislet(yol: str) -> str:
    return os.path.expanduser(yol)


def xdg_indirme() -> str:
    try:
        r = subprocess.run(["xdg-user-dir", "DOWNLOAD"], capture_output=True, text=True, timeout=3)
        if r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    return str(Path.home() / "Downloads")


def systemctl(*args) -> subprocess.CompletedProcess:
    return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True)


def servis_aktif_mi() -> bool:
    return systemctl("is-active", SERVIS).stdout.strip() == "active"


def servis_kurulu_mu() -> bool:
    return (Path.home() / ".config" / "systemd" / "user" / SERVIS).exists()


# --------------------------------------------------------------------------- #
#  Yardımcı bileşen: klasör seçme düğmesi
# --------------------------------------------------------------------------- #
class KlasorSecici(Gtk.Button):
    """Seçili klasörü gösteren, tıklanınca klasör seçme penceresi açan düğme.
    (Gtk.FileChooserButton henüz var olmayan klasörleri gösteremediği için özel bileşen.)"""

    def __init__(self, yol: str = "", baslik: str = "Klasör seçin"):
        super().__init__()
        self.baslik = baslik
        kutu = Gtk.Box(spacing=6)
        kutu.pack_start(Gtk.Image.new_from_icon_name("folder", Gtk.IconSize.BUTTON), False, False, 0)
        self.etiket = Gtk.Label(xalign=0)
        self.etiket.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self.etiket.set_width_chars(22)
        kutu.pack_start(self.etiket, True, True, 0)
        self.add(kutu)
        self.set_yol(yol)
        self.connect("clicked", self._tiklandi)
        self.degisti_cb = None

    def set_yol(self, yol: str):
        self.yol = kisalt(yol) if yol else ""
        self.etiket.set_text(self.yol or "(seçilmedi)")
        self.set_tooltip_text(genislet(self.yol) if self.yol else "Klasör seçilmedi")

    def _tiklandi(self, _btn):
        dlg = Gtk.FileChooserDialog(
            title=self.baslik, parent=self.get_toplevel(), action=Gtk.FileChooserAction.SELECT_FOLDER
        )
        dlg.add_buttons("İptal", Gtk.ResponseType.CANCEL, "Seç", Gtk.ResponseType.OK)
        dlg.set_create_folders(True)
        # Var olan en yakın üst klasörden başla
        p = Path(genislet(self.yol)) if self.yol else Path.home()
        while not p.exists() and p != p.parent:
            p = p.parent
        dlg.set_current_folder(str(p))
        if dlg.run() == Gtk.ResponseType.OK:
            self.set_yol(dlg.get_filename())
            if self.degisti_cb:
                self.degisti_cb()
        dlg.destroy()


# --------------------------------------------------------------------------- #
#  Kural satırı
# --------------------------------------------------------------------------- #
class KuralSatiri(Gtk.ListBoxRow):
    def __init__(self, pencere, ad="", uzantilar=None, hedef=""):
        super().__init__()
        self.pencere = pencere
        self.set_activatable(False)
        self.set_selectable(False)

        izgara = Gtk.Grid(column_spacing=8, margin=6)
        self.add(izgara)

        self.ad = Gtk.Entry(text=ad, placeholder_text="Örn: Resimler", width_chars=14)
        self.uzantilar = Gtk.Entry(
            text=", ".join(uzantilar or []), placeholder_text="jpg, png, gif ...", hexpand=True
        )
        self.uzantilar.set_tooltip_text("Uzantıları virgülle ayırın. Nokta yazmanız gerekmez.\nÖrn: pdf, docx, tar.gz")
        self.hedef = KlasorSecici(hedef, "Bu türdeki dosyalar hangi klasöre gitsin?")
        sil = Gtk.Button.new_from_icon_name("user-trash-symbolic", Gtk.IconSize.BUTTON)
        sil.set_tooltip_text("Bu kuralı sil")
        sil.set_relief(Gtk.ReliefStyle.NONE)
        sil.connect("clicked", lambda *_: pencere.kural_sil(self))

        izgara.attach(self.ad, 0, 0, 1, 1)
        izgara.attach(self.uzantilar, 1, 0, 1, 1)
        izgara.attach(Gtk.Label(label="→"), 2, 0, 1, 1)
        izgara.attach(self.hedef, 3, 0, 1, 1)
        izgara.attach(sil, 4, 0, 1, 1)

        for w in (self.ad, self.uzantilar):
            w.connect("changed", lambda *_: pencere.degisiklik_var())
        self.hedef.degisti_cb = pencere.degisiklik_var

    def uzanti_listesi(self):
        parcalar = self.uzantilar.get_text().replace(";", ",").replace(" ", ",").split(",")
        return [p.strip().lstrip(".").lower() for p in parcalar if p.strip().lstrip(".")]

    def veri(self):
        return {"ad": self.ad.get_text().strip(), "hedef": self.hedef.yol, "uzantilar": self.uzanti_listesi()}


# --------------------------------------------------------------------------- #
#  Ana pencere
# --------------------------------------------------------------------------- #
class AnaPencere(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title=UYGULAMA_ADI)
        self.set_default_size(900, 680)
        self.set_icon_name("folder-download")
        self._degisti = False
        self._yukleniyor = True
        self._log_mtime = 0

        # Başlık çubuğu
        hb = Gtk.HeaderBar(show_close_button=True, title=UYGULAMA_ADI,
                           subtitle="İndirilen dosyaları türlerine göre klasörlere yönlendirir")
        self.set_titlebar(hb)
        self.kaydet_btn = Gtk.Button(label="Kaydet ve uygula")
        self.kaydet_btn.get_style_context().add_class("suggested-action")
        self.kaydet_btn.connect("clicked", lambda *_: self.kaydet())
        hb.pack_end(self.kaydet_btn)

        ana = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin=14)
        kaydirma = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        kaydirma.add(ana)
        self.add(kaydirma)

        # --- Durum / açma-kapama ---
        durum_cerceve = Gtk.Frame()
        durum = Gtk.Box(spacing=12, margin=12)
        durum_cerceve.add(durum)
        self.durum_ikon = Gtk.Image()
        durum.pack_start(self.durum_ikon, False, False, 0)
        metinler = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.durum_baslik = Gtk.Label(xalign=0)
        self.durum_alt = Gtk.Label(xalign=0)
        self.durum_alt.get_style_context().add_class("dim-label")
        metinler.pack_start(self.durum_baslik, False, False, 0)
        metinler.pack_start(self.durum_alt, False, False, 0)
        durum.pack_start(metinler, True, True, 0)
        self.anahtar = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.anahtar_id = self.anahtar.connect("state-set", self.anahtar_degisti)
        durum.pack_end(self.anahtar, False, False, 0)
        ana.pack_start(durum_cerceve, False, False, 0)

        # --- İzlenen klasörler ---
        ana.pack_start(self._baslik("İzlenen klasörler",
                                    "Tarayıcınızın dosyaları indirdiği klasör(ler)"), False, False, 0)
        self.izlenen_liste = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        cer = Gtk.Frame()
        cer.add(self.izlenen_liste)
        ana.pack_start(cer, False, False, 0)
        btn = Gtk.Button(label="Klasör ekle", halign=Gtk.Align.START,
                         image=Gtk.Image.new_from_icon_name("list-add-symbolic", Gtk.IconSize.BUTTON),
                         always_show_image=True)
        btn.connect("clicked", lambda *_: self.izlenen_ekle_dialog())
        ana.pack_start(btn, False, False, 0)

        # --- Kurallar ---
        ana.pack_start(self._baslik("Yönlendirme kuralları",
                                    "Her dosya türü için hedef klasörü seçin"), False, False, 0)
        basliklar = Gtk.Grid(column_spacing=8, margin_start=8)
        for i, (m, gen) in enumerate([("Ad", 14), ("Uzantılar", 0), ("", 0), ("Hedef klasör", 24)]):
            lb = Gtk.Label(label=m, xalign=0, hexpand=(i == 1))
            lb.set_width_chars(gen)
            lb.get_style_context().add_class("dim-label")
            basliklar.attach(lb, i, 0, 1, 1)
        ana.pack_start(basliklar, False, False, 0)
        self.kural_liste = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        cer = Gtk.Frame()
        cer.add(self.kural_liste)
        ana.pack_start(cer, False, False, 0)
        satir = Gtk.Box(spacing=8)
        btn = Gtk.Button(label="Kural ekle",
                         image=Gtk.Image.new_from_icon_name("list-add-symbolic", Gtk.IconSize.BUTTON),
                         always_show_image=True)
        btn.connect("clicked", lambda *_: self.kural_ekle(odakla=True))
        satir.pack_start(btn, False, False, 0)
        btn = Gtk.Button(label="Varsayılan kurallara dön")
        btn.connect("clicked", lambda *_: self.varsayilana_don())
        satir.pack_end(btn, False, False, 0)
        ana.pack_start(satir, False, False, 0)

        # --- Seçenekler ---
        ana.pack_start(self._baslik("Seçenekler"), False, False, 0)
        sec = Gtk.Grid(column_spacing=12, row_spacing=8)
        self.diger_cb = Gtk.CheckButton(label="Hiçbir kurala uymayan dosyaları şu klasöre taşı:")
        self.diger_klasor = KlasorSecici("", "Eşleşmeyen dosyalar için klasör")
        self.diger_klasor.degisti_cb = self.degisiklik_var
        self.diger_cb.connect("toggled", lambda *_: (self.diger_klasor.set_sensitive(self.diger_cb.get_active()),
                                                     self.degisiklik_var()))
        sec.attach(self.diger_cb, 0, 0, 1, 1)
        sec.attach(self.diger_klasor, 1, 0, 1, 1)
        self.bildirim_cb = Gtk.CheckButton(label="Her taşınan dosya için masaüstü bildirimi göster")
        self.bildirim_cb.connect("toggled", lambda *_: self.degisiklik_var())
        sec.attach(self.bildirim_cb, 0, 1, 2, 1)
        sec.attach(Gtk.Label(label="İndirme bitti sayılması için bekleme süresi (sn):", xalign=0), 0, 2, 1, 1)
        self.bekleme = Gtk.SpinButton.new_with_range(1, 120, 1)
        self.bekleme.connect("value-changed", lambda *_: self.degisiklik_var())
        sec.attach(self.bekleme, 1, 2, 1, 1)
        ana.pack_start(sec, False, False, 0)

        simdi_btn = Gtk.Button(label="Klasördeki mevcut dosyaları şimdi düzenle",
                               halign=Gtk.Align.START,
                               image=Gtk.Image.new_from_icon_name("edit-clear-all-symbolic", Gtk.IconSize.BUTTON),
                               always_show_image=True)
        simdi_btn.set_tooltip_text("Normalde yalnızca yeni indirilen dosyalar taşınır. "
                                   "Bu düğme izlenen klasörde zaten bulunan dosyaları da kurallara göre taşır.")
        simdi_btn.connect("clicked", lambda *_: self.simdi_duzenle())
        ana.pack_start(simdi_btn, False, False, 0)

        # --- Etkinlik günlüğü ---
        ana.pack_start(self._baslik("Son etkinlikler"), False, False, 0)
        self.log_view = Gtk.TextView(editable=False, cursor_visible=False, monospace=True,
                                     wrap_mode=Gtk.WrapMode.WORD_CHAR)
        lk = Gtk.ScrolledWindow(min_content_height=150)
        lk.add(self.log_view)
        cer = Gtk.Frame()
        cer.add(lk)
        ana.pack_start(cer, True, True, 0)

        self.connect("delete-event", self.kapaniyor)
        self.yukle()
        self.durum_guncelle()
        self.log_guncelle()
        GLib.timeout_add_seconds(2, self._periyodik)

    # ---------------- yardımcılar ----------------
    def _baslik(self, metin, alt=None):
        kutu = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin_top=6)
        lb = Gtk.Label(xalign=0)
        lb.set_markup(f"<b>{GLib.markup_escape_text(metin)}</b>")
        kutu.pack_start(lb, False, False, 0)
        if alt:
            a = Gtk.Label(label=alt, xalign=0)
            a.get_style_context().add_class("dim-label")
            kutu.pack_start(a, False, False, 0)
        return kutu

    def mesaj(self, tur, baslik, metin="", butonlar=Gtk.ButtonsType.OK):
        d = Gtk.MessageDialog(transient_for=self, modal=True, message_type=tur, buttons=butonlar, text=baslik)
        if metin:
            d.format_secondary_text(metin)
        r = d.run()
        d.destroy()
        return r

    def degisiklik_var(self):
        if self._yukleniyor:
            return
        self._degisti = True
        self.kaydet_btn.set_label("Kaydet ve uygula *")

    # ---------------- izlenen klasörler ----------------
    def izlenen_ekle(self, yol):
        row = Gtk.ListBoxRow(activatable=False, selectable=False)
        kutu = Gtk.Box(spacing=8, margin=6)
        kutu.pack_start(Gtk.Image.new_from_icon_name("folder-download", Gtk.IconSize.BUTTON), False, False, 0)
        lb = Gtk.Label(label=kisalt(yol), xalign=0)
        kutu.pack_start(lb, True, True, 0)
        sil = Gtk.Button.new_from_icon_name("user-trash-symbolic", Gtk.IconSize.BUTTON)
        sil.set_relief(Gtk.ReliefStyle.NONE)
        sil.set_tooltip_text("İzlemeyi bırak")
        sil.connect("clicked", lambda *_: (self.izlenen_liste.remove(row), self.degisiklik_var()))
        kutu.pack_end(sil, False, False, 0)
        row.add(kutu)
        row.yol = kisalt(yol)
        self.izlenen_liste.add(row)
        row.show_all()

    def izlenen_ekle_dialog(self):
        dlg = Gtk.FileChooserDialog(title="İzlenecek klasörü seçin", parent=self,
                                    action=Gtk.FileChooserAction.SELECT_FOLDER)
        dlg.add_buttons("İptal", Gtk.ResponseType.CANCEL, "Ekle", Gtk.ResponseType.OK)
        dlg.set_current_folder(xdg_indirme())
        if dlg.run() == Gtk.ResponseType.OK:
            yol = dlg.get_filename()
            if kisalt(yol) not in [r.yol for r in self.izlenen_liste.get_children()]:
                self.izlenen_ekle(yol)
                self.degisiklik_var()
        dlg.destroy()

    # ---------------- kurallar ----------------
    def kural_ekle(self, ad="", uzantilar=None, hedef="", odakla=False):
        row = KuralSatiri(self, ad, uzantilar, hedef)
        self.kural_liste.add(row)
        row.show_all()
        if odakla:
            row.ad.grab_focus()
            self.degisiklik_var()

    def kural_sil(self, row):
        self.kural_liste.remove(row)
        self.degisiklik_var()

    def varsayilana_don(self):
        if self.mesaj(Gtk.MessageType.QUESTION, "Varsayılan kurallara dönülsün mü?",
                      "Mevcut kurallarınız silinecek.", Gtk.ButtonsType.YES_NO) != Gtk.ResponseType.YES:
            return
        try:
            veri = json.loads(VARSAYILAN_AYAR.read_text(encoding="utf-8"))
        except Exception as e:
            self.mesaj(Gtk.MessageType.ERROR, "Varsayılan ayarlar okunamadı", str(e))
            return
        for r in self.kural_liste.get_children():
            self.kural_liste.remove(r)
        for k in veri.get("kurallar", []):
            self.kural_ekle(k.get("ad", ""), k.get("uzantilar", []), k.get("hedef", ""))
        self.degisiklik_var()

    # ---------------- yükle / kaydet ----------------
    def yukle(self):
        self._yukleniyor = True
        kaynak = AYAR_DOSYASI if AYAR_DOSYASI.exists() else VARSAYILAN_AYAR
        try:
            self.veri = json.loads(kaynak.read_text(encoding="utf-8"))
        except Exception as e:
            self.mesaj(Gtk.MessageType.ERROR, "Ayar dosyası okunamadı", f"{kaynak}\n{e}")
            self.veri = {}

        for k in self.veri.get("izlenen_klasorler", ["$XDG_DOWNLOAD"]):
            self.izlenen_ekle(xdg_indirme() if k == "$XDG_DOWNLOAD" else genislet(k))
        for k in self.veri.get("kurallar", []):
            ad = k.get("ad") or (Path(genislet(k.get("hedef", ""))).name or "")
            self.kural_ekle(ad, k.get("uzantilar", []), k.get("hedef", ""))

        diger = self.veri.get("eslesmeyen_dosyalar_klasoru")
        self.diger_cb.set_active(bool(diger))
        self.diger_klasor.set_yol(diger or "~/İndirilenler/Diğer")
        self.diger_klasor.set_sensitive(bool(diger))
        self.bildirim_cb.set_active(self.veri.get("masaustu_bildirimi", True))
        self.bekleme.set_value(self.veri.get("sabit_kalma_suresi_saniye", 5))
        self._yukleniyor = False

    def topla(self):
        """Arayüzdeki değerleri doğrular ve ayar sözlüğü döndürür. Hata varsa None."""
        izlenen = [r.yol for r in self.izlenen_liste.get_children()]
        if not izlenen:
            self.mesaj(Gtk.MessageType.WARNING, "En az bir izlenen klasör eklemelisiniz.")
            return None

        kurallar, gorulen = [], {}
        for i, r in enumerate(self.kural_liste.get_children(), 1):
            k = r.veri()
            ad = k["ad"] or f"{i}. kural"
            if not k["uzantilar"] and not k["hedef"]:
                continue  # tamamen boş satırı yok say
            if not k["uzantilar"]:
                self.mesaj(Gtk.MessageType.WARNING, f"“{ad}” kuralında uzantı yok.")
                return None
            if not k["hedef"]:
                self.mesaj(Gtk.MessageType.WARNING, f"“{ad}” kuralı için hedef klasör seçilmedi.")
                return None
            for uz in k["uzantilar"]:
                if uz in gorulen:
                    self.mesaj(Gtk.MessageType.WARNING, f"“.{uz}” uzantısı iki kuralda birden var.",
                               f"“{gorulen[uz]}” ve “{ad}” kurallarından birinden kaldırın.")
                    return None
                gorulen[uz] = ad
            k["ad"] = ad
            kurallar.append(k)

        # Hedef klasör izlenen klasörün kendisi olmamalı
        izlenen_tam = {os.path.realpath(genislet(p)) for p in izlenen}
        for k in kurallar:
            if os.path.realpath(genislet(k["hedef"])) in izlenen_tam:
                self.mesaj(Gtk.MessageType.WARNING, f"“{k['ad']}” kuralının hedefi izlenen klasörün kendisi.",
                           "Lütfen farklı bir klasör veya bir alt klasör seçin.")
                return None

        veri = dict(self.veri)
        veri["izlenen_klasorler"] = ["$XDG_DOWNLOAD" if genislet(p) == xdg_indirme() else p for p in izlenen]
        veri["kurallar"] = kurallar
        veri["eslesmeyen_dosyalar_klasoru"] = self.diger_klasor.yol if self.diger_cb.get_active() else None
        veri["masaustu_bildirimi"] = self.bildirim_cb.get_active()
        veri["sabit_kalma_suresi_saniye"] = int(self.bekleme.get_value())
        veri.setdefault("tarama_araligi_saniye", 3)
        veri.setdefault("gizli_dosyalari_atla", True)
        veri.setdefault("baslangicta_mevcut_dosyalari_duzenle", False)
        return veri

    def kaydet(self, sessiz=False) -> bool:
        veri = self.topla()
        if veri is None:
            return False
        try:
            AYAR_DOSYASI.parent.mkdir(parents=True, exist_ok=True)
            gecici = AYAR_DOSYASI.with_suffix(".json.tmp")
            gecici.write_text(json.dumps(veri, ensure_ascii=False, indent=2), encoding="utf-8")
            gecici.replace(AYAR_DOSYASI)  # atomik yazım: servis yarım dosya okumaz
        except Exception as e:
            self.mesaj(Gtk.MessageType.ERROR, "Ayarlar kaydedilemedi", str(e))
            return False
        self.veri = veri
        self._degisti = False
        self.kaydet_btn.set_label("Kaydet ve uygula")
        # Servis ayar dosyasını kendisi algılar; çalışmıyorsa kullanıcıya hatırlat
        if not sessiz and not servis_aktif_mi():
            if self.mesaj(Gtk.MessageType.QUESTION, "Ayarlar kaydedildi.",
                          "Otomatik düzenleme şu anda kapalı. Şimdi açılsın mı?",
                          Gtk.ButtonsType.YES_NO) == Gtk.ResponseType.YES:
                self.anahtar.set_active(True)
        return True

    # ---------------- servis kontrolü ----------------
    def anahtar_degisti(self, _sw, acik):
        if acik:
            if self._degisti and not self.kaydet(sessiz=True):
                return True  # kaydedilemediyse anahtarı değiştirme
            if not servis_kurulu_mu():
                self.mesaj(Gtk.MessageType.ERROR, "Arka plan servisi kurulu değil",
                           "Lütfen önce kur.sh betiğini çalıştırın.")
                return True
            r = systemctl("enable", "--now", SERVIS)
        else:
            r = systemctl("disable", "--now", SERVIS)
        if r.returncode != 0:
            self.mesaj(Gtk.MessageType.ERROR, "Servis durumu değiştirilemedi", r.stderr.strip())
        GLib.timeout_add(600, lambda: (self.durum_guncelle(), False)[1])
        return True  # durumu durum_guncelle() belirleyecek

    def durum_guncelle(self):
        aktif = servis_aktif_mi()
        self.anahtar.handler_block(self.anahtar_id)
        self.anahtar.set_state(aktif)
        self.anahtar.set_active(aktif)
        self.anahtar.handler_unblock(self.anahtar_id)
        if aktif:
            self.durum_ikon.set_from_icon_name("emblem-ok-symbolic", Gtk.IconSize.DIALOG)
            self.durum_baslik.set_markup("<big><b>Otomatik düzenleme AÇIK</b></big>")
            self.durum_alt.set_text("Yeni indirilen dosyalar kurallara göre taşınıyor. "
                                    "Bu pencereyi kapatsanız da çalışmaya devam eder.")
        else:
            self.durum_ikon.set_from_icon_name("media-playback-pause-symbolic", Gtk.IconSize.DIALOG)
            self.durum_baslik.set_markup("<big><b>Otomatik düzenleme KAPALI</b></big>")
            self.durum_alt.set_text("Açmak için sağdaki anahtarı kullanın.")

    def simdi_duzenle(self):
        if self._degisti and not self.kaydet(sessiz=True):
            return
        motor = next((p for p in MOTOR_ADAYLARI if p.exists()), None)
        if motor is None:
            self.mesaj(Gtk.MessageType.ERROR, "Düzenleme programı bulunamadı.")
            return
        onizleme = subprocess.run([sys.executable, str(motor), "--dry-run"], capture_output=True, text=True)
        satirlar = [s.split("[DENEME] ", 1)[1] for s in onizleme.stdout.splitlines() if "[DENEME]" in s]
        if not satirlar:
            self.mesaj(Gtk.MessageType.INFO, "Taşınacak dosya yok.",
                       "İzlenen klasörlerde kurallara uyan dosya bulunamadı.")
            return
        ozet = "\n".join(kisalt(s.split(" -> ")[0]).rsplit("/", 1)[-1] + "  →  " + kisalt(s.split(" -> ")[1])
                         for s in satirlar[:15])
        if len(satirlar) > 15:
            ozet += f"\n... ve {len(satirlar) - 15} dosya daha"
        if self.mesaj(Gtk.MessageType.QUESTION, f"{len(satirlar)} dosya taşınacak. Devam edilsin mi?",
                      ozet, Gtk.ButtonsType.YES_NO) != Gtk.ResponseType.YES:
            return
        r = subprocess.run([sys.executable, str(motor), "--once"], capture_output=True, text=True)
        self.log_guncelle(zorla=True)
        if r.returncode != 0:
            self.mesaj(Gtk.MessageType.ERROR, "Düzenleme sırasında hata oluştu", r.stderr[-800:])

    # ---------------- günlük ----------------
    def log_guncelle(self, zorla=False):
        try:
            mt = LOG_DOSYASI.stat().st_mtime
        except FileNotFoundError:
            self.log_view.get_buffer().set_text("Henüz etkinlik yok.")
            return
        if mt == self._log_mtime and not zorla:
            return
        self._log_mtime = mt
        with open(LOG_DOSYASI, encoding="utf-8", errors="replace") as f:
            satirlar = f.readlines()[-200:]
        # En yeni üstte, sadece tarih-saat ve mesaj
        temiz = []
        for s in reversed(satirlar):
            s = s.rstrip()
            if "[INFO] " in s or "[ERROR] " in s or "[WARNING] " in s:
                zaman = s[:19]
                mesaj = s.split("] ", 1)[1] if "] " in s else s
                temiz.append(f"{zaman}  {mesaj.replace(EV, '~')}")
        self.log_view.get_buffer().set_text("\n".join(temiz) or "Henüz etkinlik yok.")

    def _periyodik(self):
        self.durum_guncelle()
        self.log_guncelle()
        return True

    def kapaniyor(self, *_):
        if not self._degisti:
            return False
        d = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.QUESTION,
                              text="Kaydedilmemiş değişiklikler var.")
        d.format_secondary_text("Çıkmadan önce kaydetmek ister misiniz?")
        d.add_buttons("Kaydetmeden çık", Gtk.ResponseType.NO, "İptal", Gtk.ResponseType.CANCEL,
                      "Kaydet", Gtk.ResponseType.YES)
        r = d.run()
        d.destroy()
        if r == Gtk.ResponseType.YES:
            return not self.kaydet()
        return r != Gtk.ResponseType.NO


class Uygulama(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="tr.ymx.DosyaDuzenleyici")

    def do_activate(self):
        pencere = self.get_active_window() or AnaPencere(self)
        pencere.show_all()
        pencere.present()


if __name__ == "__main__":
    sys.exit(Uygulama().run(sys.argv))
