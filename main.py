# -*- coding: utf-8 -*-
"""Android/Kivy port of Toy Story 3 CSV Translator."""
import csv
import json
import re
import threading
import urllib.parse
import urllib.request
from pathlib import Path

from kivy.app import App
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.properties import StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.utils import platform

GOOGLE_ENDPOINT = "https://translate.googleapis.com/translate_a/single"
REQUIRED_COLUMNS = {"index", "file_offset_hex", "byte_length", "raw_hex", "translation"}
SOURCE_COLUMN_CANDIDATES = ("text_or_escaped_bytes", "source", "text", "original", "english")
PLACEHOLDER_RX = re.compile(
    r"\\r\\n|\\n|\\r|\\t|\\x[0-9A-Fa-f]{2}|"
    r"\{[^{}]*\}|\[[^\[\]]*\]|<[^<>]*>|"
    r"%\d*\$?[sdif]|\{\w+\}|\$[A-Za-z_][A-Za-z0-9_]*"
)

KV = r"""
<RootUI>:
    orientation: "vertical"
    padding: "10dp"
    spacing: "7dp"
    Label:
        text: "Toy Story 3 — CSV Translator"
        size_hint_y: None
        height: "38dp"
        font_size: "20sp"
        bold: True
    Label:
        text: root.status
        size_hint_y: None
        height: "42dp"
        text_size: self.width, None
        halign: "left"
        valign: "middle"
    BoxLayout:
        size_hint_y: None
        height: "42dp"
        spacing: "6dp"
        Button:
            text: "Pilih CSV"
            on_release: root.choose_csv()
        Button:
            text: "Simpan CSV"
            on_release: root.save_csv()
    Label:
        text: "Path file (jika pemilih file tidak tersedia)"
        size_hint_y: None
        height: "20dp"
        font_size: "12sp"
    TextInput:
        id: path_input
        size_hint_y: None
        height: "42dp"
        multiline: False
        hint_text: "/storage/emulated/0/Download/file.csv"
    BoxLayout:
        size_hint_y: None
        height: "42dp"
        spacing: "6dp"
        Button:
            text: "Muat dari path"
            on_release: root.load_path()
        Button:
            text: "Terjemahkan semua"
            on_release: root.translate_all()
    BoxLayout:
        size_hint_y: None
        height: "42dp"
        spacing: "6dp"
        Label:
            text: "Dari"
            size_hint_x: None
            width: "35dp"
        Spinner:
            id: source_lang
            text: "en"
            values: ["auto", "en", "ja", "zh-CN", "ko", "fr", "de", "es", "ru"]
        Label:
            text: "Ke"
            size_hint_x: None
            width: "25dp"
        Spinner:
            id: target_lang
            text: "id"
            values: ["id", "en", "ja", "zh-CN", "ko", "fr", "de", "es", "ru"]
    Label:
        text: "Pilih entri dengan tombol Sebelumnya/Berikutnya. Edit kolom translation di bawah."
        size_hint_y: None
        height: "38dp"
        text_size: self.width, None
        halign: "left"
    BoxLayout:
        size_hint_y: None
        height: "42dp"
        spacing: "6dp"
        Button:
            text: "Sebelumnya"
            on_release: root.move_row(-1)
        Label:
            text: root.row_label
        Button:
            text: "Berikutnya"
            on_release: root.move_row(1)
    Label:
        text: "Teks sumber"
        size_hint_y: None
        height: "24dp"
    TextInput:
        id: source_text
        readonly: True
        size_hint_y: 0.34
        multiline: True
        font_size: "14sp"
    Label:
        text: "Terjemahan"
        size_hint_y: None
        height: "24dp"
    TextInput:
        id: translation_text
        size_hint_y: 0.34
        multiline: True
        font_size: "14sp"
    BoxLayout:
        size_hint_y: None
        height: "44dp"
        spacing: "6dp"
        Button:
            text: "Simpan edit entri"
            on_release: root.apply_edit()
        Button:
            text: "Terjemahkan entri"
            on_release: root.translate_one()
        Button:
            text: "Cek placeholder"
            on_release: root.check_placeholders()
"""

def protect_tokens(text):
    tokens = []
    def sub(match):
        marker = "ZXQKEEP%04dQXZ" % len(tokens)
        tokens.append((marker, match.group(0)))
        return marker
    return PLACEHOLDER_RX.sub(sub, text or ""), tokens

def google_translate(text, source_lang="en", target_lang="id", timeout=25):
    if not (text or "").strip():
        return text or ""
    protected, tokens = protect_tokens(text)
    params = urllib.parse.urlencode({
        "client": "gtx", "sl": source_lang, "tl": target_lang, "dt": "t", "q": protected
    })
    req = urllib.request.Request(
        GOOGLE_ENDPOINT + "?" + params,
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    translated = "".join(part[0] for part in payload[0] if part and part[0])
    for marker, original in tokens:
        if marker not in translated:
            raise ValueError("Placeholder hilang saat diterjemahkan: " + original)
        translated = translated.replace(marker, original)
    return translated

def placeholders(text):
    return PLACEHOLDER_RX.findall(text or "")

def source_column(headers):
    for name in SOURCE_COLUMN_CANDIDATES:
        if name in headers:
            return name
    return None

class RootUI(BoxLayout):
    status = StringProperty("Belum ada CSV. Pilih file CSV untuk mulai.")
    row_label = StringProperty("0 / 0")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.headers = []
        self.rows = []
        self.encoding = "utf-8-sig"
        self.current = 0
        self.file_path = ""

    def info(self, message, title="Info"):
        content = BoxLayout(orientation="vertical", padding=10, spacing=10)
        content.add_widget(Label(text=message))
        close = Button(text="OK", size_hint_y=None, height="44dp")
        popup = Popup(title=title, content=content, size_hint=(.9, .5))
        close.bind(on_release=popup.dismiss)
        content.add_widget(close)
        popup.open()

    def choose_csv(self):
        try:
            from plyer import filechooser
            filechooser.open_file(on_selection=self._picked_file, filters=[("CSV files", "*.csv")])
        except Exception as exc:
            self.info("Pemilih file tidak tersedia. Isi path file di kotak path lalu tekan Muat dari path.\n\n" + str(exc))

    def _picked_file(self, selection):
        if selection:
            self.file_path = selection[0]
            self.ids.path_input.text = self.file_path
            self.load_path()

    def load_path(self):
        path = self.ids.path_input.text.strip()
        if not path:
            self.info("Masukkan path file CSV.")
            return
        try:
            raw = Path(path).read_bytes()
            # Try common encodings without silently replacing characters.
            for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
                try:
                    text = raw.decode(enc)
                    self.encoding = enc
                    break
                except UnicodeDecodeError:
                    continue
            else:
                raise ValueError("Encoding file tidak dikenali.")
            import io
            reader = csv.DictReader(io.StringIO(text, newline=""))
            if not reader.fieldnames:
                raise ValueError("CSV tidak memiliki header.")
            self.headers = list(reader.fieldnames)
            missing = REQUIRED_COLUMNS - set(self.headers)
            if missing:
                raise ValueError("Kolom wajib tidak ditemukan: " + ", ".join(sorted(missing)))
            self.rows = list(reader)
            self.file_path = path
            self.current = 0
            self.status = "Berhasil memuat %d entri • encoding %s" % (len(self.rows), self.encoding)
            self.show_row()
        except Exception as exc:
            self.info("Gagal membuka CSV:\n" + str(exc), "Error")

    def save_csv(self):
        if not self.headers:
            self.info("Muat CSV terlebih dahulu.")
            return
        self.apply_edit(show_message=False)
        path = self.ids.path_input.text.strip() or self.file_path
        if not path:
            self.info("Path file belum diisi.")
            return
        try:
            import io
            output = io.StringIO(newline="")
            writer = csv.DictWriter(output, fieldnames=self.headers, extrasaction="ignore", lineterminator="\n")
            writer.writeheader()
            for row in self.rows:
                writer.writerow({h: row.get(h, "") for h in self.headers})
            Path(path).write_bytes(output.getvalue().encode(self.encoding))
            self.file_path = path
            self.status = "CSV tersimpan: " + path
            self.info("CSV berhasil disimpan.")
        except Exception as exc:
            self.info("Gagal menyimpan CSV:\n" + str(exc), "Error")

    def show_row(self):
        if not self.rows:
            self.row_label = "0 / 0"
            self.ids.source_text.text = ""
            self.ids.translation_text.text = ""
            return
        self.current = max(0, min(self.current, len(self.rows)-1))
        row = self.rows[self.current]
        src_col = source_column(self.headers)
        self.ids.source_text.text = (row.get(src_col, "") if src_col else "(Kolom sumber tidak ditemukan)")
        self.ids.translation_text.text = row.get("translation", "") or ""
        self.row_label = "%d / %d (index %s)" % (self.current+1, len(self.rows), row.get("index", "?"))

    def apply_edit(self, show_message=True):
        if not self.rows:
            return
        self.rows[self.current]["translation"] = self.ids.translation_text.text
        if show_message:
            self.status = "Edit entri %d diterapkan. Simpan CSV untuk menulis ke file." % (self.current+1)

    def move_row(self, amount):
        if not self.rows:
            return
        self.apply_edit(show_message=False)
        self.current = max(0, min(len(self.rows)-1, self.current+amount))
        self.show_row()

    def check_placeholders(self):
        if not self.rows:
            self.info("Muat CSV terlebih dahulu.")
            return
        self.apply_edit(show_message=False)
        src_col = source_column(self.headers)
        if not src_col:
            self.info("Kolom sumber tidak ditemukan.")
            return
        src = placeholders(self.rows[self.current].get(src_col, ""))
        dst = placeholders(self.rows[self.current].get("translation", ""))
        missing = list(dst)
        lost = []
        for token in src:
            if token in missing:
                missing.remove(token)
            else:
                lost.append(token)
        msg = "Placeholder sumber: %s\nHilang dari terjemahan: %s\nTambahan di terjemahan: %s" % (
            src, lost, missing)
        self.info(msg, "Pemeriksaan placeholder")

    def translate_one(self):
        if not self.rows:
            self.info("Muat CSV terlebih dahulu.")
            return
        self.apply_edit(show_message=False)
        src_col = source_column(self.headers)
        if not src_col:
            self.info("Kolom sumber tidak ditemukan.")
            return
        src = self.rows[self.current].get(src_col, "")
        sl, tl = self.ids.source_lang.text, self.ids.target_lang.text
        self.status = "Menerjemahkan entri %d..." % (self.current+1)
        threading.Thread(target=self._translate_worker, args=([self.current], src_col, sl, tl), daemon=True).start()

    def translate_all(self):
        if not self.rows:
            self.info("Muat CSV terlebih dahulu.")
            return
        self.apply_edit(show_message=False)
        src_col = source_column(self.headers)
        if not src_col:
            self.info("Kolom sumber tidak ditemukan.")
            return
        sl, tl = self.ids.source_lang.text, self.ids.target_lang.text
        self.status = "Memulai terjemahan..."
        threading.Thread(target=self._translate_worker, args=(list(range(len(self.rows))), src_col, sl, tl), daemon=True).start()

    def _translate_worker(self, indices, src_col, sl, tl):
        done = 0
        errors = []
        for i in indices:
            src = self.rows[i].get(src_col, "") or ""
            if not src.strip():
                done += 1
                continue
            try:
                result = google_translate(src, sl, tl)
                self.rows[i]["translation"] = result
            except Exception as exc:
                errors.append("Baris %d: %s" % (i+1, str(exc)))
            done += 1
            Clock.schedule_once(lambda dt, n=done, total=len(indices): self._progress(n, total), 0)
        Clock.schedule_once(lambda dt: self._finished(done, len(indices), errors), 0)

    def _progress(self, done, total):
        self.status = "Menerjemahkan: %d/%d" % (done, total)

    def _finished(self, done, total, errors):
        self.show_row()
        self.status = "Selesai: %d/%d diproses; %d error. Simpan CSV." % (done, total, len(errors))
        if errors:
            self.info("\n".join(errors[:12]), "Sebagian terjemahan gagal")
        else:
            self.info("Terjemahan selesai. Tekan Simpan CSV agar perubahan tersimpan.")

class CSVTranslatorApp(App):
    def build(self):
        self.title = "Toy Story 3 CSV Translator"
        Builder.load_string(KV)
        return RootUI()

if __name__ == "__main__":
    CSVTranslatorApp().run()
