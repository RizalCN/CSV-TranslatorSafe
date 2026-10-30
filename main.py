
# -*- coding: utf-8 -*-
"""Toy Story 3 CSV Translator - Android/Kivy."""

import csv
import io
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
from kivy.utils import platform

try:
    from android_saf import pick_document, read_uri, write_uri
except Exception:
    pick_document = None
    read_uri = None
    write_uri = None


GOOGLE_ENDPOINT = "https://translate.googleapis.com/translate_a/single"

REQUIRED_COLUMNS = {
    "index",
    "file_offset_hex",
    "byte_length",
    "raw_hex",
    "translation",
}

SOURCE_COLUMN_CANDIDATES = (
    "text_or_escaped_bytes",
    "source",
    "text",
    "original",
    "english",
)

PLACEHOLDER_RX = re.compile(
    r"\\r\\n|\\n|\\r|\\t|\\x[0-9A-Fa-f]{2}|"
    r"\{[^{}]*\}|\[[^\[\]]*\]|<[^<>]*>|"
    r"%\d*\$?[sdif]|\$\{[^{}]*\}|"
    r"\$[A-Za-z_][A-Za-z0-9_]*"
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
        height: "48dp"
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
        text: "Path file lokal (opsional)"
        size_hint_y: None
        height: "20dp"
        font_size: "12sp"

    TextInput:
        id: path_input
        size_hint_y: None
        height: "42dp"
        multiline: False
        hint_text: "Pilih CSV menggunakan tombol di atas"

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
        text: "Pilih entri menggunakan Sebelumnya/Berikutnya."
        size_hint_y: None
        height: "30dp"
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
    """Lindungi placeholder supaya tidak ikut diterjemahkan."""
    tokens = []

    def replace(match):
        marker = "ZXQKEEP{:04d}QXZ".format(len(tokens))
        tokens.append((marker, match.group(0)))
        return marker

    return PLACEHOLDER_RX.sub(replace, text or ""), tokens


def google_translate(text, source_lang="en", target_lang="id", timeout=30):
    if not (text or "").strip():
        return text or ""

    protected, tokens = protect_tokens(text)

    params = urllib.parse.urlencode({
        "client": "gtx",
        "sl": source_lang,
        "tl": target_lang,
        "dt": "t",
        "q": protected,
    })

    request = urllib.request.Request(
        GOOGLE_ENDPOINT + "?" + params,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        },
    )

    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))

    translated = "".join(
        part[0]
        for part in payload[0]
        if part and part[0]
    )

    for marker, original in tokens:
        if marker not in translated:
            raise ValueError(
                "Placeholder tidak ditemukan setelah terjemahan: "
                + original
            )
        translated = translated.replace(marker, original)

    return translated


def placeholders(text):
    return PLACEHOLDER_RX.findall(text or "")


def source_column(headers):
    for name in SOURCE_COLUMN_CANDIDATES:
        if name in headers:
            return name
    return None


def decode_csv(raw):
    """Dekode CSV tanpa langsung mengganti karakter yang gagal."""
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue

    raise ValueError("Encoding CSV tidak dikenali.")


class RootUI(BoxLayout):
    status = StringProperty(
        "Belum ada CSV. Tekan Pilih CSV untuk memulai."
    )
    row_label = StringProperty("0 / 0")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.headers = []
        self.rows = []
        self.encoding = "utf-8-sig"
        self.current = 0
        self.file_path = ""
        self._source_uri = None
        self._translating = False

    def info(self, message, title="Info"):
        def show_popup(_dt):
            content = BoxLayout(
                orientation="vertical",
                padding=10,
                spacing=10,
            )
            label = Label(
                text=str(message),
                halign="left",
                valign="middle",
            )
            label.bind(
                size=lambda obj, size: setattr(
                    obj, "text_size", (size[0], None)
                )
            )
            content.add_widget(label)

            close = Button(
                text="OK",
                size_hint_y=None,
                height="44dp",
            )
            popup = Popup(
                title=title,
                content=content,
                size_hint=(0.92, 0.65),
            )
            close.bind(on_release=popup.dismiss)
            content.add_widget(close)
            popup.open()

        Clock.schedule_once(show_popup, 0)

    def choose_csv(self):
        if platform == "android":
            if pick_document is None or read_uri is None:
                self.info(
                    "Modul Android SAF tidak tersedia.\n"
                    "Pastikan android_saf.py ikut dimasukkan "
                    "ke dalam APK.",
                    "Kesalahan",
                )
                return

            self.status = "Pilih file CSV dari pemilih dokumen Android."

            def picked(uri, name, error):
                # Jadwalkan operasi UI ke thread Kivy.
                Clock.schedule_once(
                    lambda _dt: self._handle_picked_file(
                        uri, name, error
                    ),
                    0,
                )

            pick_document(picked, "*/*")
            return

        try:
            from plyer import filechooser

            filechooser.open_file(
                on_selection=self._picked_file,
                filters=[("CSV files", "*.csv")],
            )
        except Exception as exc:
            self.info(
                "Pemilih file tidak tersedia.\n\n{}".format(exc),
                "Kesalahan",
            )

    def _handle_picked_file(self, uri, name, error):
        if error:
            self.status = "Pemilihan file gagal."
            self.info(error, "Pemilih file")
            return

        try:
            raw = read_uri(uri)

            safe_name = Path(
                str(name or "translation.csv")
            ).name

            if not safe_name.lower().endswith(".csv"):
                safe_name += ".csv"

            local_dir = Path(
                App.get_running_app().user_data_dir
            )
            local_dir.mkdir(parents=True, exist_ok=True)

            local_path = local_dir / safe_name
            local_path.write_bytes(raw)

            self._source_uri = uri
            self.file_path = str(local_path)
            self.ids.path_input.text = self.file_path

            self._load_csv_bytes(raw, self.file_path)

        except Exception as exc:
            self.status = "Gagal memuat CSV."
            self.info(
                "Gagal membaca file yang dipilih:\n{}".format(exc),
                "Kesalahan",
            )

    def _picked_file(self, selection):
        if not selection:
            return

        self._source_uri = None
        self.file_path = selection[0]
        self.ids.path_input.text = self.file_path
        self.load_path()

    def load_path(self):
        path = self.ids.path_input.text.strip()

        if not path:
            self.info("Pilih CSV atau masukkan path file lokal.")
            return

        try:
            raw = Path(path).read_bytes()
            self._source_uri = None
            self._load_csv_bytes(raw, path)

        except Exception as exc:
            self.info(
                "Gagal membuka CSV:\n{}\n\n"
                "Di Android, gunakan tombol Pilih CSV untuk "
                "file di Download atau penyimpanan bersama."
                .format(exc),
                "Kesalahan",
            )

    def _load_csv_bytes(self, raw, path):
        text, encoding = decode_csv(raw)

        reader = csv.DictReader(io.StringIO(text, newline=""))

        if not reader.fieldnames:
            raise ValueError("CSV tidak memiliki header.")

        headers = list(reader.fieldnames)

        missing = REQUIRED_COLUMNS - set(headers)
        if missing:
            raise ValueError(
                "Kolom wajib tidak ditemukan: "
                + ", ".join(sorted(missing))
            )

        rows = list(reader)

        self.headers = headers
        self.rows = rows
        self.encoding = encoding
        self.file_path = str(path)
        self.current = 0

        self.status = (
            "Berhasil memuat {} entri | encoding {}"
            .format(len(rows), encoding)
        )
        self.show_row()

    def save_csv(self):
        if not self.headers:
            self.info("Muat CSV terlebih dahulu.")
            return

        self.apply_edit(show_message=False)

        path = self.file_path or self.ids.path_input.text.strip()

        if not path:
            self.info("Path file belum tersedia.")
            return

        try:
            output = io.StringIO(newline="")

            writer = csv.DictWriter(
                output,
                fieldnames=self.headers,
                extrasaction="ignore",
                lineterminator="\n",
            )
            writer.writeheader()

            for row in self.rows:
                writer.writerow({
                    header: row.get(header, "")
                    for header in self.headers
                })

            data = output.getvalue().encode(self.encoding)

            # Simpan salinan lokal terlebih dahulu.
            Path(path).write_bytes(data)

            # Jika file berasal dari pemilih Android, tulis juga
            # kembali ke dokumen aslinya.
            if (
                platform == "android"
                and self._source_uri is not None
                and write_uri is not None
            ):
                write_uri(self._source_uri, data)

            self.status = "CSV berhasil disimpan."
            self.info(
                "CSV berhasil disimpan ke file yang dipilih."
                if self._source_uri is not None
                else "CSV berhasil disimpan:\n{}".format(path)
            )

        except Exception as exc:
            self.info(
                "Gagal menyimpan CSV:\n{}".format(exc),
                "Kesalahan",
            )

    def show_row(self):
        if not self.rows:
            self.row_label = "0 / 0"
            self.ids.source_text.text = ""
            self.ids.translation_text.text = ""
            return

        self.current = max(
            0,
            min(self.current, len(self.rows) - 1),
        )

        row = self.rows[self.current]
        src_col = source_column(self.headers)

        if src_col:
            self.ids.source_text.text = row.get(src_col, "") or ""
        else:
            self.ids.source_text.text = (
                "(Kolom sumber tidak ditemukan)"
            )

        self.ids.translation_text.text = (
            row.get("translation", "") or ""
        )

        self.row_label = "{}/{} (index {})".format(
            self.current + 1,
            len(self.rows),
            row.get("index", "?"),
        )

    def apply_edit(self, show_message=True):
        if not self.rows:
            return

        self.rows[self.current]["translation"] = (
            self.ids.translation_text.text
        )

        if show_message:
            self.status = (
                "Edit entri {} diterapkan. "
                "Tekan Simpan CSV untuk menyimpan."
                .format(self.current + 1)
            )

    def move_row(self, amount):
        if not self.rows:
            return

        self.apply_edit(show_message=False)

        self.current = max(
            0,
            min(len(self.rows) - 1, self.current + amount),
        )
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

        src = placeholders(
            self.rows[self.current].get(src_col, "")
        )
        dst = placeholders(
            self.rows[self.current].get("translation", "")
        )

        remaining = list(dst)
        missing = []

        for token in src:
            if token in remaining:
                remaining.remove(token)
            else:
                missing.append(token)

        message = (
            "Placeholder sumber:\n{}\n\n"
            "Hilang dari terjemahan:\n{}\n\n"
            "Tambahan di terjemahan:\n{}"
        ).format(src, missing, remaining)

        self.info(message, "Pemeriksaan placeholder")

    def translate_one(self):
        if not self.rows:
            self.info("Muat CSV terlebih dahulu.")
            return

        if self._translating:
            self.info("Terjemahan sedang berjalan.")
            return

        self.apply_edit(show_message=False)

        src_col = source_column(self.headers)
        if not src_col:
            self.info("Kolom sumber tidak ditemukan.")
            return

        self._start_translation(
            [self.current],
            src_col,
            self.ids.source_lang.text,
            self.ids.target_lang.text,
        )

    def translate_all(self):
        if not self.rows:
            self.info("Muat CSV terlebih dahulu.")
            return

        if self._translating:
            self.info("Terjemahan sedang berjalan.")
            return

        self.apply_edit(show_message=False)

        src_col = source_column(self.headers)
        if not src_col:
            self.info("Kolom sumber tidak ditemukan.")
            return

        self._start_translation(
            list(range(len(self.rows))),
            src_col,
            self.ids.source_lang.text,
            self.ids.target_lang.text,
        )

    def _start_translation(self, indices, src_col, sl, tl):
        self._translating = True
        self.status = "Memulai terjemahan..."

        thread = threading.Thread(
            target=self._translate_worker,
            args=(indices, src_col, sl, tl),
            daemon=True,
        )
        thread.start()

    def _translate_worker(self, indices, src_col, sl, tl):
        done = 0
        errors = []
        total = len(indices)

        for index in indices:
            src = self.rows[index].get(src_col, "") or ""

            if src.strip():
                try:
                    result = google_translate(src, sl, tl)
                    self.rows[index]["translation"] = result
                except Exception as exc:
                    errors.append(
                        "Baris {}: {}".format(index + 1, exc)
                    )

            done += 1

            Clock.schedule_once(
                lambda dt, n=done, t=total:
                    self._progress(n, t),
                0,
            )

        Clock.schedule_once(
            lambda dt: self._finished(done, total, errors),
            0,
        )

    def _progress(self, done, total):
        self.status = "Menerjemahkan: {}/{}".format(done, total)

    def _finished(self, done, total, errors):
        self._translating = False
        self.show_row()

        self.status = (
            "Selesai: {}/{} diproses; {} error. "
            "Simpan CSV untuk menyimpan perubahan."
        ).format(done, total, len(errors))

        if errors:
            self.info(
                "\n".join(errors[:12]),
                "Sebagian terjemahan gagal",
            )
        else:
            self.info(
                "Terjemahan selesai. Tekan Simpan CSV "
                "agar perubahan tersimpan."
            )


class CSVTranslatorApp(App):
    def build(self):
        self.title = "Toy Story 3 CSV Translator"
        Builder.load_string(KV)
        return RootUI()


if __name__ == "__main__":
    CSVTranslatorApp().run()
