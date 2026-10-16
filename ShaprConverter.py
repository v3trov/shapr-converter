from pathlib import Path
import argparse
import json
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from shapr_core import FORMATS, convert


def main():
    parser = argparse.ArgumentParser(description='Автономный SHAPR Converter')
    parser.add_argument('source', nargs='?')
    parser.add_argument('-o', '--output')
    parser.add_argument('-f', '--format', choices=FORMATS, default='stl')
    parser.add_argument('--solids-only', action='store_true')
    parser.add_argument('--tolerance', type=float, default=0.02)
    args = parser.parse_args()
    if args.source and args.output:
        try:
            result = convert(args.source, args.output, args.format, args.tolerance, args.solids_only, lambda s: print(s, flush=True))
            print(json.dumps(result, ensure_ascii=False))
        except Exception as exc:
            print(str(exc), file=sys.stderr); return 1
        return 0
    root = tk.Tk(); root.title('SHAPR Converter'); root.geometry('790x560'); root.minsize(720, 500)
    root.configure(bg='#f4f5f7')
    style = ttk.Style(); style.theme_use('clam')
    style.configure('TFrame', background='#f4f5f7'); style.configure('TLabel', background='#f4f5f7', font=('Segoe UI', 10))
    style.configure('TButton', font=('Segoe UI', 10), padding=8)
    frame = ttk.Frame(root, padding=22); frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='SHAPR → STL, OBJ, 3MF, GLB, PLY, STEP', font=('Segoe UI', 17, 'bold')).pack(anchor='w')
    ttk.Label(frame, text='Работает локально. Shapr3D, Python и интернет для запуска не нужны.').pack(anchor='w', pady=(6, 18))
    source = tk.StringVar(value=args.source or ''); target = tk.StringVar()
    fmt = tk.StringVar(value='stl'); solids = tk.BooleanVar(value=False); tol = tk.StringVar(value='0.02')
    def choose_source():
        value = filedialog.askopenfilename(title='Выберите проект Shapr3D', initialdir='F:/Проекты Shapr3d' if Path('F:/Проекты Shapr3d').exists() else None, filetypes=[('Shapr3D', '*.shapr')])
        if value:
            source.set(value)
            target.set(str(Path(value).with_name(Path(value).stem+'_converted.'+fmt.get())))
    def choose_target():
        value = filedialog.asksaveasfilename(title='Сохранить результат', defaultextension='.'+fmt.get(), filetypes=[(fmt.get().upper(), '*.'+fmt.get())], initialfile=Path(target.get()).name if target.get() else 'model.'+fmt.get())
        if value:target.set(value)
    def row(label, variable, command):
        ttk.Label(frame, text=label).pack(anchor='w')
        r = ttk.Frame(frame); r.pack(fill='x', pady=(5, 12))
        ttk.Entry(r, textvariable=variable).pack(side='left', fill='x', expand=True)
        ttk.Button(r, text='Выбрать…', command=command).pack(side='left', padx=(8, 0))
    row('Исходный файл', source, choose_source); row('Результат (существующие файлы не заменяются)', target, choose_target)
    r = ttk.Frame(frame); r.pack(fill='x', pady=4)
    ttk.Label(r, text='Формат').pack(side='left')
    box = ttk.Combobox(r, textvariable=fmt, values=FORMATS, state='readonly', width=8); box.pack(side='left', padx=(8, 22))
    def update_suffix(event=None):
        if target.get():target.set(str(Path(target.get()).with_suffix('.'+fmt.get())))
    box.bind('<<ComboboxSelected>>', update_suffix)
    ttk.Label(r, text='Отклонение сетки, мм').pack(side='left')
    ttk.Entry(r, textvariable=tol, width=8).pack(side='left', padx=8)
    ttk.Checkbutton(frame, text='Только точные тела — исключить импортированные сетки', variable=solids).pack(anchor='w', pady=(12, 6))
    ttk.Label(frame, text='Экспортируются сохранённые активные тела, включая скрытые.\nИстория, эскизы, чертежи и цвета не переносятся.', foreground='#555b65').pack(anchor='w')
    status = tk.StringVar(value='Выберите файл и формат.'); events = queue.Queue(); busy = False
    def start():
        nonlocal busy
        if busy:return
        try:
            if not source.get() or not target.get():raise ValueError('Выберите исходный файл и результат.')
            tolerance = float(tol.get().replace(',', '.'))
            params = (source.get(), target.get(), fmt.get(), tolerance, solids.get())
        except Exception as exc:messagebox.showerror('Проверьте параметры', str(exc)); return
        busy = True; button.configure(state='disabled'); progress.start(12)
        def worker():
            try:
                result = convert(*params, progress=lambda s: events.put(('status', s)))
                events.put(('done', result))
            except Exception as exc:events.put(('error', str(exc)))
        threading.Thread(target=worker, daemon=True).start()
    button = ttk.Button(frame, text='Конвертировать', command=start); button.pack(anchor='w', pady=(18, 8))
    progress = ttk.Progressbar(frame, mode='indeterminate'); progress.pack(fill='x')
    ttk.Label(frame, textvariable=status, wraplength=720).pack(anchor='w', pady=8)
    def poll():
        nonlocal busy
        while not events.empty():
            kind, value = events.get()
            if kind=='status':status.set(value)
            else:
                busy=False;button.configure(state='normal');progress.stop()
                if kind=='done':
                    status.set(f'Готово. Тел: {len(value["parts"])}. Треугольников: {value["triangles"]:,}.')
                    messagebox.showinfo('Готово', 'Файл сохранён:\n'+target.get()+'\n\nРядом находится отчёт .json.')
                else:status.set('Преобразование не завершено.');messagebox.showerror('Не удалось преобразовать проект', value)
        root.after(150, poll)
    def close():
        if busy:
            messagebox.showinfo('Идёт преобразование', 'Дождитесь завершения преобразования.'); return
        root.destroy()
    root.protocol('WM_DELETE_WINDOW', close); poll(); root.mainloop(); return 0


if __name__ == '__main__':
    raise SystemExit(main())
