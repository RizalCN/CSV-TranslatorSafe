
# -*- coding: utf-8 -*-
"""Android Storage Access Framework untuk Kivy."""

REQUEST_CODE = 8421
_pending_callback = None


def _unbind_callback():
    try:
        from android import activity
        activity.unbind(on_activity_result=_on_activity_result)
    except Exception:
        pass


def _on_activity_result(request_code, result_code, intent):
    global _pending_callback

    if request_code != REQUEST_CODE:
        return

    callback = _pending_callback
    _pending_callback = None
    _unbind_callback()

    if callback is None:
        return

    try:
        # Android Activity.RESULT_OK bernilai -1.
        if result_code != -1 or intent is None:
            callback(None, None, "Pemilihan file dibatalkan.")
            return

        uri = intent.getData()
        if uri is None:
            callback(None, None, "Android tidak mengembalikan URI file.")
            return

        name = "translation.csv"

        try:
            from jnius import autoclass

            PythonActivity = autoclass(
                "org.kivy.android.PythonActivity"
            )
            resolver = PythonActivity.mActivity.getContentResolver()
            cursor = resolver.query(uri, None, None, None, None)

            if cursor is not None:
                try:
                    if cursor.moveToFirst():
                        index = cursor.getColumnIndex("_display_name")
                        if index >= 0:
                            value = cursor.getString(index)
                            if value:
                                name = str(value)
                finally:
                    cursor.close()
        except Exception:
            pass

        callback(uri, name, None)

    except Exception as exc:
        callback(
            None,
            None,
            "Gagal memproses file pilihan: {}".format(exc)
        )


def pick_document(callback, mime="*/*"):
    """Buka pemilih dokumen Android."""
    global _pending_callback

    try:
        from android import activity
        from jnius import autoclass

        Intent = autoclass("android.content.Intent")
        PythonActivity = autoclass(
            "org.kivy.android.PythonActivity"
        )

        intent = Intent(Intent.ACTION_OPEN_DOCUMENT)
        intent.addCategory(Intent.CATEGORY_OPENABLE)
        intent.setType(mime or "*/*")

        # Minta izin baca dan tulis jika penyedia dokumen mendukungnya.
        flags = (
            Intent.FLAG_GRANT_READ_URI_PERMISSION
            | Intent.FLAG_GRANT_WRITE_URI_PERMISSION
        )
        intent.addFlags(flags)

        _unbind_callback()
        _pending_callback = callback
        activity.bind(on_activity_result=_on_activity_result)

        PythonActivity.mActivity.startActivityForResult(
            intent, REQUEST_CODE
        )

    except Exception as exc:
        _pending_callback = None
        _unbind_callback()

        callback(
            None,
            None,
            "Tidak dapat membuka pemilih file Android: {}".format(exc)
        )


def read_uri(uri):
    """Baca file yang dipilih menggunakan ContentResolver."""
    from jnius import autoclass

    PythonActivity = autoclass(
        "org.kivy.android.PythonActivity"
    )
    resolver = PythonActivity.mActivity.getContentResolver()
    stream = resolver.openInputStream(uri)

    if stream is None:
        raise IOError("Android tidak dapat membuka file tersebut.")

    output = bytearray()

    try:
        while True:
            value = stream.read()
            if value == -1:
                break
            output.append(value & 0xFF)
    finally:
        stream.close()

    return bytes(output)


def write_uri(uri, data):
    """Tulis data kembali ke dokumen yang dipilih."""
    from jnius import autoclass

    PythonActivity = autoclass(
        "org.kivy.android.PythonActivity"
    )
    resolver = PythonActivity.mActivity.getContentResolver()

    # Mode wt membuka file untuk ditulis dan memotong isi lama.
    stream = resolver.openOutputStream(uri, "wt")

    if stream is None:
        raise IOError("Android tidak dapat menulis ke file tersebut.")

    try:
        for value in data:
            stream.write(int(value))
        stream.flush()
    finally:
        stream.close()
