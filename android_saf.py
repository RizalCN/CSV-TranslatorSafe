# -*- coding: utf-8 -*-
"""Android Storage Access Framework helpers for Kivy/python-for-Android."""

REQUEST_CODE = 8421
_pending_callback = None


def _on_activity_result(request_code, result_code, intent):
    global _pending_callback

    if request_code != REQUEST_CODE:
        return

    callback = _pending_callback
    _pending_callback = None

    try:
        from android import activity

        try:
            activity.unbind(on_activity_result=_on_activity_result)
        except Exception:
            pass

        if callback is None:
            return

        # RESULT_OK Android = -1
        if result_code != -1 or intent is None:
            callback(None, None, "Pemilihan file dibatalkan.")
            return

        uri = intent.getData()
        if uri is None:
            callback(None, None, "Android tidak mengembalikan URI file.")
            return

        filename = "selected_file.csv"

        try:
            from jnius import autoclass

            PythonActivity = autoclass(
                "org.kivy.android.PythonActivity"
            )
            activity_obj = PythonActivity.mActivity
            resolver = activity_obj.getContentResolver()

            OpenableColumns = autoclass(
                "android.provider.OpenableColumns"
            )

            cursor = resolver.query(
                uri,
                None,
                None,
                None,
                None
            )

            if cursor is not None:
                try:
                    if cursor.moveToFirst():
                        column_name = OpenableColumns.DISPLAY_NAME
                        index = cursor.getColumnIndex(column_name)

                        if index >= 0:
                            result = cursor.getString(index)
                            if result:
                                filename = str(result)
                finally:
                    cursor.close()

        except Exception:
            # Tetap lanjut jika nama file tidak dapat dibaca.
            pass

        callback(uri, filename, None)

    except Exception as exc:
        if callback:
            callback(
                None,
                None,
                "Gagal membaca hasil pemilihan file: %s" % exc
            )


def pick_document(callback, mime="*/*"):
    """Buka pemilih file Android dan kembalikan URI file terpilih."""
    global _pending_callback

    try:
        from android import activity
        from jnius import autoclass

        Intent = autoclass("android.content.Intent")
        PythonActivity = autoclass(
            "org.kivy.android.PythonActivity"
        )

        activity_obj = PythonActivity.mActivity

        intent = Intent(Intent.ACTION_OPEN_DOCUMENT)
        intent.addCategory(Intent.CATEGORY_OPENABLE)
        intent.setType(mime or "*/*")

        # Izinkan aplikasi membaca dan menulis file yang dipilih.
        flags = (
            Intent.FLAG_GRANT_READ_URI_PERMISSION
            | Intent.FLAG_GRANT_WRITE_URI_PERMISSION
        )
        intent.addFlags(flags)

        # Daftarkan callback sebelum membuka pemilih file.
        _pending_callback = callback
        activity.bind(on_activity_result=_on_activity_result)

        # PERBAIKAN UTAMA:
        # startActivityForResult dipanggil pada objek Activity,
        # bukan pada modul android.activity.
        activity_obj.startActivityForResult(
            intent,
            REQUEST_CODE
        )

    except Exception as exc:
        _pending_callback = None

        try:
            from android import activity
            activity.unbind(on_activity_result=_on_activity_result)
        except Exception:
            pass

        callback(
            None,
            None,
            "Tidak dapat membuka pemilih file Android: %s" % exc
        )


def read_uri(uri):
    """Baca isi file melalui URI Android."""
    from jnius import autoclass

    PythonActivity = autoclass(
        "org.kivy.android.PythonActivity"
    )
    activity_obj = PythonActivity.mActivity
    resolver = activity_obj.getContentResolver()

    stream = resolver.openInputStream(uri)

    if stream is None:
        raise IOError(
            "Android tidak dapat membuka file yang dipilih."
        )

    output = bytearray()

    try:
        while True:
            value = stream.read()

            if value == -1:
                break

            output.append(value & 255)

    finally:
        stream.close()

    return bytes(output)


def write_uri(uri, data):
    """Simpan data kembali ke file yang dipilih melalui URI Android."""
    from jnius import autoclass

    PythonActivity = autoclass(
        "org.kivy.android.PythonActivity"
    )
    activity_obj = PythonActivity.mActivity
    resolver = activity_obj.getContentResolver()

    stream = resolver.openOutputStream(uri, "wt")

    if stream is None:
        raise IOError(
            "Android tidak dapat menyimpan ke lokasi yang dipilih."
        )

    try:
        for value in data:
            stream.write(int(value))

        stream.flush()

    finally:
        stream.close()
