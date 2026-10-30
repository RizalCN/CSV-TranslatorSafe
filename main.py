# -*- coding: utf-8 -*-
"""Toy Story 3 CSV Translator - Android/Kivy port retaining original features."""
from __future__ import annotations
import csv, io, json, re, threading, urllib.parse, urllib.request
from pathlib import Path
from collections import Counter
from kivy.app import App
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.properties import StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.checkbox import CheckBox
from kivy.utils import platform

try:
    from android_saf import pick_document, read_uri, write_uri
except Exception:
    pick_document = read_uri = write_uri = None

REQUIRED_COLUMNS = {"index", "file_offset_hex", "byte_length", "raw_hex", "translation"}
SOURCE_COLUMN_CANDIDATES = ("text_or_escaped_bytes", "source", "text", "original", "english")
GOOGLE_ENDPOINT = "https://translate.googleapis.com/translate_a/single"
PLACEHOLDER_RX = re.compile(r"\\r\\n|\\n|\\r|\\t|\\x[0-9A-Fa-f]{2}|\{[^{}]*\}|\[[^\[\]]*\]|<[^<>]*>|%\d*\$?[sdif]|\$[A-Za-z_][A-Za-z0-9_]*")

KV = r'''
<RootUI>:
    orientation: 'vertical'
    padding: '8dp'
    spacing: '5dp'
    ScrollView:
        do_scroll_x: False
        BoxLayout:
            orientation: 'vertical'
            size_hint_y: None
            height: self.minimum_height
            spacing: '6dp'
            Label:
                text: 'Toy Story 3 — CSV Translator'
                size_hint_y: None
                height: '36dp'
                font_size: '20sp'
                bold: True
            Label:
                text: root.status
                size_hint_y: None
                height: '48dp'
                text_size: self.width, None
                halign: 'left'
                valign: 'middle'
            BoxLayout:
                size_hint_y: None
                height: '44dp'
                spacing: '5dp'
                Button:
                    text: 'Buka CSV'
                    on_release: root.choose_csv()
                Button:
                    text: 'Simpan'
                    on_release: root.save_csv()
                Button:
                    text: 'Simpan sebagai'
                    on_release: root.save_as()
            TextInput:
                id: path_input
                size_hint_y: None
                height: '42dp'
                multiline: False
                hint_text: 'Path lokal (opsional)'
            BoxLayout:
                size_hint_y: None
                height: '42dp'
                spacing: '5dp'
                Button:
                    text: 'Muat path'
                    on_release: root.load_path()
                Button:
                    text: 'Simpan progres'
                    on_release: root.save_progress()
                Button:
                    text: 'Buka progres'
                    on_release: root.open_progress()
            BoxLayout:
                size_hint_y: None
                height: '42dp'
                spacing: '5dp'
                Label:
                    text: 'Dari'
                    size_hint_x: None
                    width: '35dp'
                Spinner:
                    id: source_lang
                    text: 'en'
                    values: ['en','auto','ja','zh-CN','ko','fr','de','es','ru']
                Label:
                    text: 'Ke'
                    size_hint_x: None
                    width: '25dp'
                Spinner:
                    id: target_lang
                    text: 'id'
                    values: ['id','en','ja','zh-CN','ko','fr','de','es','ru']
            BoxLayout:
                size_hint_y: None
                height: '42dp'
                spacing: '4dp'
                Label:
                    text: 'Encoding byte'
                    size_hint_x: None
                    width: '105dp'
                    font_size: '12sp'
                Spinner:
                    id: encoding
                    text: 'cp1252'
                    values: ['cp1252','latin-1','utf-8']
                CheckBox:
                    id: only_empty
                    active: True
                    size_hint_x: None
                    width: '35dp'
                Label:
                    text: 'Hanya translation kosong'
                    font_size: '12sp'
                    halign: 'left'
                    text_size: self.size
            BoxLayout:
                size_hint_y: None
                height: '44dp'
                spacing: '5dp'
                Button:
                    text: 'Terjemahkan semua kandidat'
                    on_release: root.translate_all()
                Button:
                    text: 'Terjemahkan entri'
                    on_release: root.translate_one()
            BoxLayout:
                size_hint_y: None
                height: '44dp'
                spacing: '5dp'
                Button:
                    text: 'Cari teks'
                    on_release: root.search_text()
                Button:
                    text: 'Deteksi encoding'
                    on_release: root.check_encoding()
                Button:
                    text: 'Cek placeholder'
                    on_release: root.check_placeholders()
                Button:
                    text: 'Kosongkan'
                    on_release: root.clear_current()
            BoxLayout:
                size_hint_y: None
                height: '42dp'
                spacing: '5dp'
                Button:
                    text: 'Sebelumnya'
                    on_release: root.move_row(-1)
                Label:
                    text: root.row_label
                Button:
                    text: 'Berikutnya'
                    on_release: root.move_row(1)
            Label:
                text: 'Teks sumber (escape seperti \\n tetap terlihat)'
                size_hint_y: None
                height: '24dp'
            TextInput:
                id: source_text
                readonly: True
                size_hint_y: None
                height: '170dp'
                multiline: True
                font_size: '14sp'
            Label:
                text: 'Translation'
                size_hint_y: None
                height: '24dp'
            TextInput:
                id: translation_text
                size_hint_y: None
                height: '170dp'
                multiline: True
                font_size: '14sp'
            BoxLayout:
                size_hint_y: None
                height: '44dp'
                spacing: '5dp'
                Button:
                    text: 'Terapkan edit'
                    on_release: root.apply_edit()
                Button:
                    text: 'Cek byte entri'
                    on_release: root.check_current_bytes()
            Label:
                text: root.byte_label
                size_hint_y: None
                height: '30dp'
                text_size: self.width, None
                halign: 'left'
            Label:
                text: 'Status: Google Translate memerlukan internet. Metadata CSV selain translation tidak diubah.'
                size_hint_y: None
                height: '38dp'
                font_size: '12sp'
                text_size: self.width, None
                halign: 'left'
'''

def decode_escaped_display(s):
    out=[]; i=0
    while i<len(s):
        if s[i] != '\\' or i+1>=len(s): out.append(s[i]); i+=1; continue
        c=s[i+1]
        if c=='\\': out.append('\\'); i+=2
        elif c=='n': out.append('\n'); i+=2
        elif c=='r': out.append('\r'); i+=2
        elif c=='t': out.append('\t'); i+=2
        elif c=='x' and i+3<len(s):
            try: out.append(chr(int(s[i+2:i+4],16))); i+=4
            except ValueError: out.extend(s[i:i+2]); i+=2
        else: out.extend(s[i:i+2]); i+=2
    return ''.join(out)

def encode_escaped_display(s):
    out=[]
    for ch in s:
        if ch=='\n': out.append('\\n')
        elif ch=='\r': out.append('\\r')
        elif ch=='\t': out.append('\\t')
        elif ord(ch)<32 or ord(ch)==127: out.append('\\x%02X'%ord(ch))
        else: out.append(ch)
    return ''.join(out)

def protect_tokens(text):
    tokens=[]
    def sub(m):
        marker='ZXQKEEP%04dQXZ'%len(tokens); tokens.append((marker,m.group(0))); return marker
    return PLACEHOLDER_RX.sub(sub,text or ''),tokens

def google_translate(text, source_lang='en', target_lang='id', timeout=25):
    if not (text or '').strip(): return text or ''
    protected,tokens=protect_tokens(text)
    params=urllib.parse.urlencode({'client':'gtx','sl':source_lang,'tl':target_lang,'dt':'t','q':protected})
    req=urllib.request.Request(GOOGLE_ENDPOINT+'?'+params,headers={'User-Agent':'Mozilla/5.0','Accept':'application/json,text/plain,*/*'})
    with urllib.request.urlopen(req,timeout=timeout) as response: payload=json.loads(response.read().decode('utf-8'))
    translated=''.join(part[0] for part in payload[0] if part and part[0])
    missing=[m for m,_ in tokens if m not in translated]
    if missing: raise ValueError('Google Translate mengubah/menghilangkan placeholder; baris dilewati agar kode aman.')
    for marker,original in tokens: translated=translated.replace(marker,original)
    return translated

def source_column(headers): return next((c for c in SOURCE_COLUMN_CANDIDATES if c in headers),None)
def byte_len(text, encoding):
    try: return len(text.encode(encoding,errors='strict'))
    except (UnicodeEncodeError,LookupError): return None

def detect_source_encoding(row):
    try: raw=bytes.fromhex(row.get('raw_hex','') or '')
    except ValueError: return 'RAW_HEX_INVALID',[]
    decoded=decode_escaped_display(row.get('text_or_escaped_bytes','') or '')
    matches=[]
    for enc in ('utf-8','cp1252','latin-1'):
        try:
            if decoded.encode(enc,errors='strict')==raw: matches.append(enc)
        except (UnicodeEncodeError,LookupError): pass
    if len(matches)==1: return matches[0],matches
    if len(matches)>1: return 'ASCII/AMBIGUOUS',matches
    return 'MISMATCH',matches

class RootUI(BoxLayout):
    status=StringProperty('Belum ada CSV. Pilih file CSV untuk mulai.')
    row_label=StringProperty('0 / 0')
    byte_label=StringProperty('Status byte: -')
    def __init__(self,**kwargs):
        super().__init__(**kwargs); self.headers=[]; self.rows=[]; self.encoding_name='utf-8-sig'; self.current=0; self.file_path=''; self._source_uri=None; self.source_col=None; self.translating=False; self._last_errors=[]
    def info(self,message,title='Info'):
        box=BoxLayout(orientation='vertical',padding=10,spacing=10); lab=TextInput(text=str(message),readonly=True,multiline=True); box.add_widget(lab)
        btn=Button(text='OK',size_hint_y=None,height='44dp'); pop=Popup(title=title,content=box,size_hint=(.92,.72)); btn.bind(on_release=pop.dismiss); box.add_widget(btn); pop.open()
    def choose_csv(self):
        if platform=='android' and pick_document:
            self.status='Pilih CSV… file besar mungkin perlu waktu untuk dimuat.'
            def picked(uri,name,error): Clock.schedule_once(lambda dt:self._picked_uri(uri,name,error),0)
            pick_document(picked,'text/*'); return
        try:
            from plyer import filechooser
            filechooser.open_file(on_selection=self._picked_file,filters=[('CSV','*.csv')])
        except Exception as e: self.info('Pemilih file tidak tersedia. '+str(e))
    def _picked_uri(self,uri,name,error):
        if error: self.info(error,'Pemilih file'); return
        try:
            self.status='Membaca CSV…'
            raw=read_uri(uri); safe=Path(str(name or 'translation.csv')).name or 'translation.csv'
            local=Path(App.get_running_app().user_data_dir)/safe; local.write_bytes(raw)
            self._source_uri=uri; self.file_path=str(local); self.ids.path_input.text=self.file_path
            self._load_bytes(raw,self.file_path)
        except Exception as e: self.info('Gagal membaca CSV:\n'+str(e),'Error')
    def _picked_file(self,selection):
        if selection: self.file_path=selection[0]; self.ids.path_input.text=self.file_path; self.load_path()
    def load_path(self):
        path=self.ids.path_input.text.strip()
        if not path: self.info('Masukkan path file atau tekan Buka CSV.'); return
        try: self.status='Membaca CSV…'; self._load_bytes(Path(path).read_bytes(),path)
        except Exception as e: self.info('Gagal membuka CSV:\n'+str(e),'Error')
    def _load_bytes(self,raw,path):
        text=None; chosen=None
        for enc in ('utf-8-sig','utf-8','cp1252','latin-1'):
            try: text=raw.decode(enc); chosen=enc; break
            except UnicodeDecodeError: continue
        if text is None: raise ValueError('Encoding file tidak dikenali.')
        reader=csv.DictReader(io.StringIO(text,newline=''))
        if not reader.fieldnames: raise ValueError('CSV tidak memiliki header.')
        headers=list(reader.fieldnames); missing=REQUIRED_COLUMNS-set(headers)
        if missing: raise ValueError('Kolom wajib hilang: '+', '.join(sorted(missing)))
        src=source_column(headers)
        if not src: raise ValueError('Kolom teks sumber tidak ditemukan.')
        rows=[dict(r) for r in reader]
        self.headers,self.rows,self.source_col,self.encoding_name=headers,rows,src,chosen
        self.file_path=path; self.current=0; self.ids.encoding.text=chosen if chosen in ('cp1252','latin-1','utf-8') else 'utf-8'
        self.status='CSV dimuat: %s baris | sumber: %s | encoding: %s'%(format(len(rows),','),src,chosen)
        self.show_row()
    def _csv_bytes(self):
        out=io.StringIO(newline=''); writer=csv.DictWriter(out,fieldnames=self.headers,extrasaction='ignore',lineterminator='\n'); writer.writeheader()
        for row in self.rows: writer.writerow({h:row.get(h,'') for h in self.headers})
        enc=self.encoding_name
        if enc=='utf-8-sig': return out.getvalue().encode('utf-8-sig')
        try: return out.getvalue().encode(enc)
        except UnicodeEncodeError: raise ValueError('Ada karakter yang tidak dapat disimpan sebagai '+enc+'. Pilih UTF-8 untuk output yang aman.')
    def save_csv(self):
        if not self.rows: self.info('Muat CSV terlebih dahulu.'); return
        self.apply_edit(False)
        try:
            data=self._csv_bytes()
            if platform=='android' and self._source_uri and write_uri:
                write_uri(self._source_uri,data)
                # keep private copy in sync too
                Path(self.file_path).write_bytes(data)
                self.status='CSV berhasil disimpan ke dokumen Android.'
            else:
                path=self.ids.path_input.text.strip() or self.file_path
                if not path: self.info('Gunakan Simpan sebagai.'); return
                Path(path).write_bytes(data); self.file_path=path; self.status='Disimpan: '+path
            self.info('CSV berhasil disimpan.','Simpan')
        except Exception as e: self.info('Gagal menyimpan:\n'+str(e),'Error')
    def save_as(self):
        if not self.rows: self.info('Muat CSV terlebih dahulu.'); return
        # Android SAF document creation is not available in all picker implementations; use current document URI safely.
        if platform=='android':
            self.info('Di Android, gunakan Buka CSV lalu Simpan untuk menulis ke dokumen yang dipilih. Untuk membuat salinan, pilih lokasi file melalui aplikasi pengelola berkas dan gunakan Muat path jika izin tersedia.'); return
        try:
            from plyer import filechooser
            filechooser.save_file(on_selection=self._save_as_selected, filters=[('CSV','*.csv')])
        except Exception as e: self.info('Simpan sebagai tidak tersedia: '+str(e))
    def _save_as_selected(self,selection):
        if selection:
            path=selection[0]; self.ids.path_input.text=path; self.file_path=path; self._source_uri=None; self.save_csv()
    def save_progress(self):
        if not self.rows: self.info('Muat CSV terlebih dahulu.'); return
        try:
            path=Path(App.get_running_app().user_data_dir)/'toy_story3_progress.csv'
            path.write_bytes(self._csv_bytes()); self.status='Progres tersimpan di penyimpanan aplikasi.'; self.info('Progres disimpan. Gunakan Buka progres untuk melanjutkan.')
        except Exception as e: self.info('Gagal menyimpan progres: '+str(e))
    def open_progress(self):
        path=Path(App.get_running_app().user_data_dir)/'toy_story3_progress.csv'
        if not path.exists(): self.info('Belum ada file progres tersimpan.'); return
        try: self._source_uri=None; self.ids.path_input.text=str(path); self._load_bytes(path.read_bytes(),str(path)); self.status='Progres dimuat: %d baris'%len(self.rows)
        except Exception as e: self.info('Gagal membuka progres: '+str(e))
    def show_row(self):
        if not self.rows:
            self.row_label='0 / 0'; self.ids.source_text.text=''; self.ids.translation_text.text=''; self.byte_label='Status byte: -'; return
        self.current=max(0,min(self.current,len(self.rows)-1)); row=self.rows[self.current]
        self.ids.source_text.text=row.get(self.source_col,'') or ''; self.ids.translation_text.text=row.get('translation','') or ''
        self.row_label='%s / %s (index %s)'%(format(self.current+1,','),format(len(self.rows),','),row.get('index','?'))
        self.byte_label='Status byte: '+self._status_bytes(row)
    def apply_edit(self,show_message=True):
        if not self.rows: return
        self.rows[self.current]['translation']=self.ids.translation_text.text
        self.byte_label='Status byte: '+self._status_bytes(self.rows[self.current])
        if show_message: self.status='Edit diterapkan pada entri %d. Simpan untuk menulis ke CSV.'%(self.current+1)
    def move_row(self,amount):
        if not self.rows:return
        self.apply_edit(False); self.current=max(0,min(len(self.rows)-1,self.current+amount)); self.show_row()
    def _status_bytes(self,row):
        value=row.get('translation','') or ''
        if not value:return 'KOSONG'
        try: expected=int(row.get('byte_length',''))
        except Exception:return 'METADATA?'
        enc=self.ids.encoding.text if 'encoding' in self.ids else 'cp1252'
        actual=byte_len(decode_escaped_display(value),enc)
        if actual is None:return 'ENCODING!'
        return '%d/%d %s'%(actual,expected,'OK' if actual==expected else 'BERBEDA')
    def check_current_bytes(self):
        if not self.rows: self.info('Muat CSV terlebih dahulu.'); return
        self.apply_edit(False); row=self.rows[self.current]
        self.info('Index: %s\nEncoding cek: %s\nStatus: %s\nCatatan: byte_length adalah metadata asli; fitur ini hanya memeriksa, tidak mengubahnya.'%(row.get('index','?'),self.ids.encoding.text,self._status_bytes(row)),'Pemeriksaan byte')
    def check_encoding(self):
        if not self.rows:self.info('Muat CSV terlebih dahulu.'); return
        result=Counter(); examples=[]
        for i,row in enumerate(self.rows):
            enc,matches=detect_source_encoding(row); result[enc]+=1
            if enc not in ('ASCII/AMBIGUOUS',) and len(examples)<12: examples.append('Baris %d / index %s: %s'%(i+1,row.get('index','?'),enc))
        self.info('Hasil deteksi dari raw_hex dibanding teks sumber:\n'+'\n'.join('%s: %d'%(k,v) for k,v in result.most_common())+'\n\nContoh:\n'+'\n'.join(examples),'Deteksi encoding')
    def check_placeholders(self):
        if not self.rows:self.info('Muat CSV terlebih dahulu.'); return
        self.apply_edit(False); row=self.rows[self.current]; src=PLACEHOLDER_RX.findall(row.get(self.source_col,'') or ''); dst=PLACEHOLDER_RX.findall(row.get('translation','') or '')
        remaining=list(dst); lost=[]
        for token in src:
            if token in remaining: remaining.remove(token)
            else: lost.append(token)
        self.info('Placeholder sumber: %s\nHilang dari terjemahan: %s\nTambahan di terjemahan: %s'%(src,lost,remaining),'Pemeriksaan placeholder')
    def clear_current(self):
        if not self.rows:return
        self.apply_edit(False); self.rows[self.current]['translation']=''; self.show_row(); self.status='Translation entri dikosongkan.'
    def search_text(self):
        if not self.rows:self.info('Muat CSV terlebih dahulu.'); return
        box=BoxLayout(orientation='vertical',padding=10,spacing=8); inp=TextInput(hint_text='Cari pada teks sumber dan translation',multiline=False,size_hint_y=None,height='44dp'); box.add_widget(inp)
        btn=Button(text='Cari berikutnya',size_hint_y=None,height='44dp'); pop=Popup(title='Cari teks',content=box,size_hint=(.9,.35)); box.add_widget(btn)
        def go(*_):
            q=inp.text.casefold()
            if not q:return
            for step in range(1,len(self.rows)+1):
                i=(self.current+step)%len(self.rows); row=self.rows[i]
                if q in ((row.get(self.source_col,'') or '')+' '+(row.get('translation','') or '')).casefold():
                    self.apply_edit(False); self.current=i; self.show_row(); self.status='Ditemukan pada baris %d'%(i+1); pop.dismiss(); return
            self.info('Teks tidak ditemukan.','Cari teks')
        btn.bind(on_release=go); pop.open()
    def translate_one(self):
        if not self.rows:self.info('Muat CSV terlebih dahulu.'); return
        self.apply_edit(False); self._start_translation([self.current])
    def translate_all(self):
        if not self.rows:self.info('Muat CSV terlebih dahulu.'); return
        self.apply_edit(False)
        indices=list(range(len(self.rows)))
        if self.ids.only_empty.active: indices=[i for i in indices if not (self.rows[i].get('translation','') or '').strip()]
        if not indices:self.info('Tidak ada translation kosong yang perlu diterjemahkan.'); return
        self._start_translation(indices)
    def _start_translation(self,indices):
        if self.translating:self.info('Terjemahan sedang berjalan.'); return
        self.translating=True; self._last_errors=[]; self.status='Memulai terjemahan untuk %d baris…'%len(indices)
        threading.Thread(target=self._translate_worker,args=(indices,self.source_col,self.ids.source_lang.text,self.ids.target_lang.text),daemon=True).start()
    def _translate_worker(self,indices,src_col,sl,tl):
        errors=[]; done=0; total=len(indices)
        for i in indices:
            src=self.rows[i].get(src_col,'') or ''
            if src.strip():
                try: self.rows[i]['translation']=google_translate(src,sl,tl)
                except Exception as exc: errors.append('Baris %d (index %s): %s'%(i+1,self.rows[i].get('index','?'),exc))
            done+=1
            if done%3==0 or done==total: Clock.schedule_once(lambda dt,n=done,t=total:self._progress(n,t),0)
        Clock.schedule_once(lambda dt:self._finished(done,total,errors),0)
    def _progress(self,done,total): self.status='Menerjemahkan: %s/%s'%(format(done,','),format(total,','))
    def _finished(self,done,total,errors):
        self.translating=False; self._last_errors=errors; self.show_row(); self.status='Selesai: %d/%d diproses; %d error. Simpan CSV/progres.'%(done,total,len(errors))
        if errors:self.info('\n'.join(errors[:20])+ ('\n… masih ada error lain.' if len(errors)>20 else ''),'Laporan terjemahan')
        else:self.info('Terjemahan selesai. Periksa status byte dan simpan CSV.','Selesai')

class CSVTranslatorApp(App):
    def build(self):
        self.title='Toy Story 3 CSV Translator'; Builder.load_string(KV); return RootUI()
if __name__=='__main__': CSVTranslatorApp().run()
