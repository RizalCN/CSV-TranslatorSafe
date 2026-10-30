# -*- coding: utf-8 -*-
"""Small Android Storage Access Framework helpers for Kivy/python-for-android."""
import os
from pathlib import Path

REQUEST_CODE = 8421
_pending_callback = None
_bound = False

def _on_activity_result(request_code, result_code, intent):
    global _pending_callback
    if request_code != REQUEST_CODE:
        return
    cb, _pending_callback = _pending_callback, None
    try:
        from android import activity
        try:
            activity.unbind(on_activity_result=_on_activity_result)
        except Exception:
            pass
        if cb is None:
            return
        if result_code != -1 or intent is None:
            cb(None, None, "Pemilihan file dibatalkan.")
            return
        uri = intent.getData()
        if uri is None:
            cb(None, None, "Android tidak mengembalikan URI file.")
            return
        name = None
        try:
            from jnius import autoclass
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            activity_obj = PythonActivity.mActivity
            resolver = activity_obj.getContentResolver()
            cursor = resolver.query(uri, None, None, None, None)
            if cursor is not None:
                try:
                    if cursor.moveToFirst():
                        idx = cursor.getColumnIndex('_display_name')
                        if idx >= 0:
                            name = cursor.getString(idx)
                finally:
                    cursor.close()
        except Exception:
            pass
        cb(uri, name or 'selected_file', None)
    except Exception as exc:
        if cb:
            cb(None, None, 'Gagal membaca pilihan file: %s' % exc)

def pick_document(callback, mime='*/*'):
    """Open Android's native Files picker. callback(uri, display_name, error)."""
    global _pending_callback
    try:
        from android import activity
        from jnius import autoclass
        Intent = autoclass('android.content.Intent')
        intent = Intent(Intent.ACTION_OPEN_DOCUMENT)
        intent.addCategory(Intent.CATEGORY_OPENABLE)
        intent.setType(mime or '*/*')
        _pending_callback = callback
        activity.bind(on_activity_result=_on_activity_result)
        activity.startActivityForResult(intent, REQUEST_CODE)
    except Exception as exc:
        _pending_callback = None
        callback(None, None, 'Tidak dapat membuka pemilih file Android: %s' % exc)

def read_uri(uri):
    from jnius import autoclass
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    stream = PythonActivity.mActivity.getContentResolver().openInputStream(uri)
    if stream is None:
        raise IOError('Android tidak dapat membuka file yang dipilih.')
    out = bytearray()
    try:
        while True:
            value = stream.read()
            if value == -1:
                break
            out.append(value & 255)
    finally:
        stream.close()
    return bytes(out)

def write_uri(uri, data):
    from jnius import autoclass
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    stream = PythonActivity.mActivity.getContentResolver().openOutputStream(uri, 'wt')
    if stream is None:
        raise IOError('Android tidak dapat menyimpan ke lokasi yang dipilih.')
    try:
        for value in data:
            stream.write(int(value))
        stream.flush()
    finally:
        stream.close()
