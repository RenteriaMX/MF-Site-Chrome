#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bloc2footer_gui.py — GUI ligera (tkinter) sobre bloc2footer.py.

Flujo: eliges la carpeta del export de Blocs (la que tiene index.html),
clic en "Generar footer.html" y sale el artefacto listo para importar
(arrastrar a la dropzone del control panel de Site Chrome).

No instala nada: tkinter viene con Python. Reusa convert() del modulo
bloc2footer (misma carpeta), asi la logica de conversion vive en un solo lugar.

Uso:
    python3 tools/bloc2footer_gui.py
"""

import json
import os
import subprocess
import sys
import threading

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

# Importa convert() del script hermano (este archivo vive en tools/ junto a el).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bloc2footer import convert  # noqa: E402


def build_preview_html(payload, scope):
    """Mismo artefacto autonomo que genera bloc2footer.main() (--preview).

    Un solo .html que sirve para ver Y para importar: lleva los datos
    incrustados en <script id=sc-footer-data> (split limpio base_css/css).
    """
    scope_class = scope.lstrip('.')
    data_json = json.dumps(payload, ensure_ascii=False).replace('</', '<\\/')
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<script id="sc-footer-data" type="application/json">%s</script>'
        '<style>\n%s\n%s\n</style></head><body>'
        '<div class="%s">%s</div></body></html>'
        % (data_json, payload['base_css'], payload['css'], scope_class, payload['html'])
    )


def open_in_os(path):
    """Abre un archivo/carpeta con el manejador por defecto del SO."""
    try:
        if sys.platform == 'darwin':
            subprocess.run(['open', path], check=False)
        elif os.name == 'nt':
            os.startfile(path)  # noqa: B606  (solo Windows)
        else:
            subprocess.run(['xdg-open', path], check=False)
    except Exception as e:  # noqa: BLE001
        messagebox.showwarning('Abrir', 'No se pudo abrir:\n%s' % e)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Blocs -> footer.html (Site Chrome)')
        self.minsize(620, 460)

        self.export_dir = tk.StringVar()
        self.scope = tk.StringVar(value='.sc-footer-blocs')
        self.open_when_done = tk.BooleanVar(value=True)
        self.also_json = tk.BooleanVar(value=False)
        self.last_output = None

        pad = {'padx': 10, 'pady': 6}

        # --- Carpeta del export ---------------------------------------
        frm = ttk.LabelFrame(self, text='1) Carpeta del export de Blocs (la que tiene index.html)')
        frm.pack(fill='x', **pad)
        row = ttk.Frame(frm)
        row.pack(fill='x', padx=8, pady=8)
        ttk.Entry(row, textvariable=self.export_dir).pack(side='left', fill='x', expand=True)
        ttk.Button(row, text='Elegir...', command=self.pick_dir).pack(side='left', padx=(6, 0))

        # --- Opciones --------------------------------------------------
        opt = ttk.LabelFrame(self, text='2) Opciones')
        opt.pack(fill='x', **pad)
        r1 = ttk.Frame(opt)
        r1.pack(fill='x', padx=8, pady=(8, 2))
        ttk.Label(r1, text='Scope CSS:').pack(side='left')
        ttk.Entry(r1, textvariable=self.scope, width=24).pack(side='left', padx=(6, 0))
        r2 = ttk.Frame(opt)
        r2.pack(fill='x', padx=8, pady=(2, 8))
        ttk.Checkbutton(r2, text='Abrir footer.html al terminar', variable=self.open_when_done).pack(side='left')
        ttk.Checkbutton(r2, text='Generar tambien footer.json', variable=self.also_json).pack(side='left', padx=(16, 0))

        # --- Accion ----------------------------------------------------
        act = ttk.Frame(self)
        act.pack(fill='x', **pad)
        self.btn = ttk.Button(act, text='Generar footer.html', command=self.run)
        self.btn.pack(side='left')
        self.btn_open = ttk.Button(act, text='Abrir resultado', command=self.open_result, state='disabled')
        self.btn_open.pack(side='left', padx=(8, 0))

        # --- Log -------------------------------------------------------
        logf = ttk.LabelFrame(self, text='Resultado')
        logf.pack(fill='both', expand=True, **pad)
        self.log = scrolledtext.ScrolledText(logf, height=10, wrap='word', state='disabled')
        self.log.pack(fill='both', expand=True, padx=8, pady=8)

        self._log('Eligir la carpeta del export y pulsar "Generar footer.html".\n')

    # ------------------------------------------------------------------
    def _log(self, msg):
        self.log.configure(state='normal')
        self.log.insert('end', msg)
        self.log.see('end')
        self.log.configure(state='disabled')

    def pick_dir(self):
        start = self.export_dir.get() or os.getcwd()
        d = filedialog.askdirectory(title='Carpeta del export de Blocs', initialdir=start)
        if d:
            self.export_dir.set(d)
            ok = os.path.exists(os.path.join(d, 'index.html'))
            self._log(('[ok] index.html encontrado en %s\n' % d) if ok
                      else ('[!] OJO: no veo index.html en %s (¿es la carpeta correcta?)\n' % d))

    def run(self):
        d = self.export_dir.get().strip()
        if not d:
            messagebox.showwarning('Falta carpeta', 'Elegi primero la carpeta del export.')
            return
        if not os.path.exists(os.path.join(d, 'index.html')):
            if not messagebox.askyesno('Sin index.html',
                                       'No encuentro index.html en esa carpeta.\n¿Continuar de todos modos?'):
                return
        self.btn.configure(state='disabled', text='Generando...')
        self.btn_open.configure(state='disabled')
        # Conversion en hilo aparte para no congelar la UI.
        threading.Thread(target=self._work, args=(d, self.scope.get().strip() or '.sc-footer-blocs'),
                         daemon=True).start()

    def _work(self, export_dir, scope):
        try:
            result = convert(export_dir, scope, None)
            payload = {k: v for k, v in result.items() if not k.startswith('_')}
            out_html = os.path.join(export_dir, 'footer.html')
            with open(out_html, 'w', encoding='utf-8') as f:
                f.write(build_preview_html(payload, scope))
            wrote = [out_html]
            if self.also_json.get():
                out_json = os.path.join(export_dir, 'footer.json')
                with open(out_json, 'w', encoding='utf-8') as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
                wrote.append(out_json)
            self.after(0, self._done_ok, result, wrote, out_html)
        except SystemExit as e:  # convert() usa SystemExit para errores de entrada
            self.after(0, self._done_err, str(e))
        except Exception as e:  # noqa: BLE001
            self.after(0, self._done_err, '%s: %s' % (type(e).__name__, e))

    def _done_ok(self, result, wrote, out_html):
        self.last_output = out_html
        self._log('\n[OK] Conversion completa.\n')
        self._log('  html=%dB  base_css=%dB  css=%dB  clases_usadas=%d\n'
                  % (len(result['html']), len(result['base_css']),
                     len(result['css']), len(result['_used_classes'])))
        for w in wrote:
            self._log('  -> %s\n' % w)
        self._log('  Arrastra footer.html a la dropzone del control panel para importarlo.\n')
        self.btn.configure(state='normal', text='Generar footer.html')
        self.btn_open.configure(state='normal')
        if self.open_when_done.get():
            open_in_os(out_html)

    def _done_err(self, msg):
        self._log('\n[ERROR] %s\n' % msg)
        self.btn.configure(state='normal', text='Generar footer.html')
        messagebox.showerror('Error en la conversion', msg)

    def open_result(self):
        if self.last_output:
            open_in_os(self.last_output)


if __name__ == '__main__':
    App().mainloop()
