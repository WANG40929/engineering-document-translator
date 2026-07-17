from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .cache import TranslationCache
from .config import AppConfig, ConfigStore
from .deepseek import DeepSeekTranslator
from .models import LANGUAGES, TranslationOptions
from .pipeline import SUPPORTED_EXTENSIONS, TranslationPipeline, collect_files, write_report
from .secret_store import SecretStore
from .text_utils import load_glossary


class TranslatorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("工程文档智能翻译器")
        self.geometry("1040x720")
        self.minsize(860, 600)
        self.config_store, self.secret_store = ConfigStore(), SecretStore()
        self.saved = self.config_store.load()
        self.events: queue.Queue = queue.Queue()
        self.running = False
        self._build()
        self.after(120, self._poll)

    def _build(self):
        style = ttk.Style(self)
        try: style.theme_use("vista")
        except tk.TclError: pass
        self.columnconfigure(0, weight=1); self.rowconfigure(2, weight=1)
        title = ttk.Frame(self, padding=(18, 14)); title.grid(row=0, column=0, sticky="ew")
        ttk.Label(title, text="工程文档智能翻译器", font=("Microsoft YaHei UI", 18, "bold")).pack(side="left")
        ttk.Label(title, text="仅翻译现有文字层 · 保留图纸、图片和版式", foreground="#506070").pack(side="left", padx=16)

        settings = ttk.LabelFrame(self, text="翻译设置", padding=12); settings.grid(row=1, column=0, padx=18, sticky="ew")
        for col in (1, 3, 5): settings.columnconfigure(col, weight=1)
        ttk.Label(settings, text="DeepSeek API Key").grid(row=0, column=0, sticky="w")
        self.key_var = tk.StringVar(value=self.secret_store.load())
        ttk.Entry(settings, textvariable=self.key_var, show="●").grid(row=0, column=1, columnspan=3, padx=6, sticky="ew")
        self.save_key = tk.BooleanVar(value=True); ttk.Checkbutton(settings, text="在本机加密保存", variable=self.save_key).grid(row=0, column=4, columnspan=2, sticky="w")
        ttk.Label(settings, text="源语言").grid(row=1, column=0, sticky="w", pady=(9, 0))
        self.source_var = tk.StringVar(value=self.saved.source_language)
        ttk.Combobox(settings, textvariable=self.source_var, values=list(LANGUAGES), state="readonly", width=10).grid(row=1, column=1, sticky="ew", padx=6, pady=(9, 0))
        ttk.Label(settings, text="目标语言").grid(row=1, column=2, sticky="w", pady=(9, 0))
        self.target_var = tk.StringVar(value=self.saved.target_language)
        ttk.Combobox(settings, textvariable=self.target_var, values=[k for k in LANGUAGES if k != "auto"], state="readonly", width=10).grid(row=1, column=3, sticky="ew", padx=6, pady=(9, 0))
        ttk.Label(settings, text="模型").grid(row=1, column=4, sticky="w", pady=(9, 0))
        self.model_var = tk.StringVar(value=self.saved.model)
        ttk.Entry(settings, textvariable=self.model_var).grid(row=1, column=5, sticky="ew", padx=6, pady=(9, 0))
        ttk.Label(settings, text="输出目录").grid(row=2, column=0, sticky="w", pady=(9, 0))
        self.output_var = tk.StringVar(value=self.saved.output_dir)
        ttk.Entry(settings, textvariable=self.output_var).grid(row=2, column=1, columnspan=4, sticky="ew", padx=6, pady=(9, 0))
        ttk.Button(settings, text="选择…", command=self._choose_output).grid(row=2, column=5, sticky="ew", padx=6, pady=(9, 0))
        ttk.Label(settings, text="术语表（CSV/TSV/XLSX）").grid(row=3, column=0, sticky="w", pady=(9, 0))
        self.glossary_var = tk.StringVar(value=self.saved.glossary_path)
        ttk.Entry(settings, textvariable=self.glossary_var).grid(row=3, column=1, columnspan=4, sticky="ew", padx=6, pady=(9, 0))
        ttk.Button(settings, text="选择…", command=self._choose_glossary).grid(row=3, column=5, sticky="ew", padx=6, pady=(9, 0))

        center = ttk.Frame(self, padding=(18, 12)); center.grid(row=2, column=0, sticky="nsew"); center.columnconfigure(0, weight=1); center.rowconfigure(1, weight=1)
        buttons = ttk.Frame(center); buttons.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(buttons, text="添加文件", command=self._add_files).pack(side="left")
        ttk.Button(buttons, text="添加文件夹", command=self._add_folder).pack(side="left", padx=6)
        ttk.Button(buttons, text="移除所选", command=self._remove).pack(side="left")
        ttk.Button(buttons, text="清空", command=lambda: self.files.delete(*self.files.get_children())).pack(side="left", padx=6)
        ttk.Label(buttons, text="支持 PDF、DOCX、DOC、XLSX/XLSM、CSV/TSV", foreground="#607080").pack(side="right")
        self.files = ttk.Treeview(center, columns=("type", "size", "path"), show="headings", selectmode="extended")
        self.files.heading("type", text="格式"); self.files.heading("size", text="大小"); self.files.heading("path", text="文件")
        self.files.column("type", width=70, anchor="center"); self.files.column("size", width=90, anchor="e"); self.files.column("path", width=700)
        self.files.grid(row=1, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(center, orient="vertical", command=self.files.yview); scroll.grid(row=1, column=1, sticky="ns"); self.files.configure(yscrollcommand=scroll.set)

        bottom = ttk.Frame(self, padding=(18, 0, 18, 16)); bottom.grid(row=3, column=0, sticky="ew"); bottom.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(bottom, maximum=100); self.progress.grid(row=0, column=0, sticky="ew")
        self.start_button = ttk.Button(bottom, text="开始翻译", command=self._start); self.start_button.grid(row=0, column=1, padx=(12, 0), ipadx=20)
        self.status_var = tk.StringVar(value="就绪"); ttk.Label(bottom, textvariable=self.status_var).grid(row=1, column=0, columnspan=2, sticky="w", pady=(7, 0))

    @staticmethod
    def _size(value):
        for unit in ("B", "KB", "MB", "GB"):
            if value < 1024 or unit == "GB": return f"{value:.1f} {unit}"
            value /= 1024

    def _insert_paths(self, paths):
        existing = {self.files.set(item, "path") for item in self.files.get_children()}
        for path in paths:
            path = Path(path).resolve()
            if str(path) not in existing and path.suffix.lower() in SUPPORTED_EXTENSIONS:
                self.files.insert("", "end", values=(path.suffix.upper()[1:], self._size(path.stat().st_size), str(path)))
                existing.add(str(path))

    def _add_files(self):
        self._insert_paths(filedialog.askopenfilenames(filetypes=[("支持的文档", "*.pdf *.docx *.doc *.xlsx *.xlsm *.csv *.tsv"), ("所有文件", "*.*")]))

    def _add_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            paths = collect_files(Path(folder)); self._insert_paths(paths); self.status_var.set(f"已从文件夹添加 {len(paths)} 个文件")

    def _remove(self):
        for item in self.files.selection(): self.files.delete(item)

    def _choose_output(self):
        value = filedialog.askdirectory()
        if value: self.output_var.set(value)

    def _choose_glossary(self):
        value = filedialog.askopenfilename(filetypes=[("术语表", "*.csv *.tsv *.txt *.xlsx"), ("所有文件", "*.*")])
        if value: self.glossary_var.set(value)

    def _start(self):
        if self.running: return
        paths = [Path(self.files.set(item, "path")) for item in self.files.get_children()]
        if not paths: messagebox.showwarning("没有文件", "请先添加需要翻译的文件。"); return
        if not self.key_var.get().strip(): messagebox.showwarning("缺少 API Key", "请输入 DeepSeek API Key。"); return
        output = Path(self.output_var.get()) if self.output_var.get().strip() else None
        glossary = Path(self.glossary_var.get()) if self.glossary_var.get().strip() else None
        config = AppConfig(self.model_var.get(), self.source_var.get(), self.target_var.get(), str(output or ""), str(glossary or ""))
        self.config_store.save(config)
        if self.save_key.get(): self.secret_store.save(self.key_var.get())
        options = TranslationOptions(self.source_var.get(), self.target_var.get(), self.model_var.get(), output_dir=output, glossary_path=glossary)
        self.running = True; self.start_button.configure(state="disabled"); self.progress["value"] = 0
        threading.Thread(target=self._worker, args=(paths, options), daemon=True).start()

    def _worker(self, paths, options):
        try:
            translator = DeepSeekTranslator(self.key_var.get(), options.model, options.source_language, options.target_language, load_glossary(options.glossary_path), TranslationCache(), options.request_timeout, options.batch_size)
            results = TranslationPipeline().run(paths, translator, options, lambda f, p, m: self.events.put(("progress", p, m)))
            report_dir = options.output_dir or paths[0].parent
            report = write_report(results, report_dir)
            self.events.put(("done", results, report))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def _poll(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "progress": self.progress["value"] = event[1] * 100; self.status_var.set(event[2])
                elif event[0] == "done":
                    self.running = False; self.start_button.configure(state="normal"); self.progress["value"] = 100
                    completed = sum(r.status == "completed" for r in event[1]); failed = sum(r.status == "failed" for r in event[1])
                    self.status_var.set(f"完成：成功 {completed}，失败 {failed}。报告：{event[2]}")
                    messagebox.showinfo("翻译完成", f"成功：{completed}\n失败：{failed}\n\n报告：{event[2]}")
                elif event[0] == "error":
                    self.running = False; self.start_button.configure(state="normal"); self.status_var.set("任务失败"); messagebox.showerror("错误", event[1])
        except queue.Empty: pass
        self.after(120, self._poll)


def main():
    TranslatorApp().mainloop()


if __name__ == "__main__": main()

