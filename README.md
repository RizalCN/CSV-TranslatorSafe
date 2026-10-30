# Toy Story 3 CSV Translator — Android

Versi ini memakai konfigurasi build GitHub Actions dan pengaturan Android/NDK yang sama seperti proyek Safe Translator yang berhasil dibuild, dengan identitas paket CSV Translator dan izin INTERNET untuk terjemahan online.

## Build
1. Unggah **isi folder ini** ke root repository GitHub CSV Translator.
2. Buka Actions → Build Toy Story 3 CSV Translator APK → Run workflow.
3. Setelah workflow berhasil, unduh artifact `ToyStory3-CSV-Translator-APK`.

## Catatan
- Ini adalah source project, bukan APK yang sudah dikompilasi.
- Workflow build belum dijalankan ulang; keberhasilan perlu dikonfirmasi melalui GitHub Actions.
- CSV Translator memakai Kivy dan tidak membutuhkan `plyer` untuk build; jika pemilih file tidak tersedia, antarmuka menyediakan kolom path sebagai alternatif.
