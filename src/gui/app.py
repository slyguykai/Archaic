"""
Tkinter GUI for Archaic

Provides URL input, output directory selection, Start/Stop controls,
progress updates, and an Advanced panel for concurrency and toggles.
"""

import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from src.core.controller import ArchaicController, RunConfig
from src.core.cdx_client import CDXClient


class ArchaicApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Archaic – Archival Web Scraper")
        self.geometry("720x520")

        self._worker = None
        self._queue = queue.Queue()
        self._controller = None

        self._build_ui()
        self._load_settings()
        self._poll_queue()

    def _build_ui(self):
        frm = ttk.Frame(self, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)

        # URL
        ttk.Label(frm, text="Target URL path").grid(row=0, column=0, sticky="w")
        self.url_var = tk.StringVar()
        self.url_entry = ttk.Entry(frm, textvariable=self.url_var, width=70)
        self.url_entry.grid(row=1, column=0, columnspan=3, sticky="ew", pady=4)

        # Output dir
        ttk.Label(frm, text="Output directory").grid(row=2, column=0, sticky="w")
        self.out_var = tk.StringVar(value="output")
        out_entry = ttk.Entry(frm, textvariable=self.out_var, width=60)
        out_entry.grid(row=3, column=0, columnspan=2, sticky="ew", pady=4)
        ttk.Button(frm, text="Browse", command=self._choose_output).grid(row=3, column=2, sticky="e")

        # Options
        self.offline_var = tk.BooleanVar(value=True)
        self.singlefile_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(frm, text="Offline assets", variable=self.offline_var).grid(row=4, column=0, sticky="w")
        ttk.Checkbutton(frm, text="Single-file HTML", variable=self.singlefile_var).grid(row=4, column=1, sticky="w")
        self.skip_completed_var = tk.BooleanVar(value=True)
        self.only_failed_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(frm, text="Skip completed (resume)", variable=self.skip_completed_var).grid(row=4, column=2, sticky="w")
        ttk.Checkbutton(frm, text="Reprocess failed only", variable=self.only_failed_var).grid(row=4, column=3, sticky="w")

        # Advanced
        sep = ttk.Separator(frm)
        sep.grid(row=5, column=0, columnspan=3, sticky="ew", pady=6)
        adv_label = ttk.Label(frm, text="Advanced", font=("", 10, "bold"))
        adv_label.grid(row=6, column=0, sticky="w")
        ttk.Label(frm, text="Concurrency").grid(row=7, column=0, sticky="w")
        self.conc_var = tk.IntVar(value=1)
        self.conc_cb = ttk.Combobox(frm, values=[1, 2], textvariable=self.conc_var, width=5, state="readonly")
        self.conc_cb.grid(row=7, column=1, sticky="w")
        ttk.Label(frm, text="Delay (s)").grid(row=7, column=2, sticky="e")
        self.delay_var = tk.DoubleVar(value=1.5)
        delay_entry = ttk.Entry(frm, textvariable=self.delay_var, width=6)
        delay_entry.grid(row=7, column=2, sticky="w", padx=(68,0))
        ttk.Label(frm, text="Max pages").grid(row=7, column=3, sticky="e")
        self.maxpages_var = tk.IntVar(value=0)
        maxpages_entry = ttk.Entry(frm, textvariable=self.maxpages_var, width=8)
        maxpages_entry.grid(row=7, column=3, sticky="w", padx=(80,0))

        # Controls
        ctrl_frame = ttk.Frame(frm)
        ctrl_frame.grid(row=8, column=0, columnspan=3, sticky="ew", pady=8)
        self.preview_btn = ttk.Button(ctrl_frame, text="Preview", command=self._preview)
        self.start_btn = ttk.Button(ctrl_frame, text="Start", command=self._start)
        self.stop_btn = ttk.Button(ctrl_frame, text="Stop", command=self._stop, state=tk.DISABLED)
        self.open_output_btn = ttk.Button(ctrl_frame, text="Open Output", command=self._open_output)
        self.view_log_btn = ttk.Button(ctrl_frame, text="View Log", command=self._view_log)
        self.open_index_btn = ttk.Button(ctrl_frame, text="Open Index", command=self._open_index)
        self.preview_btn.pack(side=tk.LEFT)
        self.start_btn.pack(side=tk.LEFT, padx=8)
        self.stop_btn.pack(side=tk.LEFT, padx=8)
        self.open_output_btn.pack(side=tk.LEFT, padx=8)
        self.view_log_btn.pack(side=tk.LEFT)
        self.open_index_btn.pack(side=tk.LEFT, padx=8)

        # Progress
        self.progress = ttk.Progressbar(frm, mode='indeterminate')
        self.progress.grid(row=9, column=0, columnspan=3, sticky="ew", pady=4)
        self.status_var = tk.StringVar(value="Idle")
        counters_frame = ttk.Frame(frm)
        counters_frame.grid(row=10, column=0, columnspan=3, sticky="ew")
        ttk.Label(counters_frame, textvariable=self.status_var).pack(side=tk.LEFT)
        self.discovered_var = tk.IntVar(value=0)
        self.completed_var = tk.IntVar(value=0)
        self.failed_var = tk.IntVar(value=0)
        ttk.Label(counters_frame, text="   Discovered:").pack(side=tk.LEFT)
        ttk.Label(counters_frame, textvariable=self.discovered_var).pack(side=tk.LEFT)
        ttk.Label(counters_frame, text="   Completed:").pack(side=tk.LEFT)
        ttk.Label(counters_frame, textvariable=self.completed_var).pack(side=tk.LEFT)
        ttk.Label(counters_frame, text="   Failed:").pack(side=tk.LEFT)
        ttk.Label(counters_frame, textvariable=self.failed_var).pack(side=tk.LEFT)

        # URL status list
        self.tree = ttk.Treeview(frm, columns=("status", "url"), show='headings', height=8)
        self.tree.heading("status", text="Status")
        self.tree.heading("url", text="URL")
        self.tree.column("status", width=100)
        self.tree.grid(row=11, column=0, columnspan=3, sticky="nsew", pady=6)

        # Log box
        self.log = tk.Text(frm, height=8)
        self.log.grid(row=12, column=0, columnspan=3, sticky="nsew", pady=6)
        frm.rowconfigure(11, weight=1)
        frm.columnconfigure(0, weight=1)

    def _choose_output(self):
        path = filedialog.askdirectory(initialdir=self.out_var.get() or ".")
        if path:
            self.out_var.set(path)

    def _start(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showerror("Validation", "Please enter a target URL path")
            return
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.progress.start(80)
        cfg = RunConfig(
            base_url=url,
            output_dir=self.out_var.get().strip() or "output",
            delay_secs=max(0.1, float(self.delay_var.get() or 1.5)),
            offline_assets=bool(self.offline_var.get()),
            single_file_html=bool(self.singlefile_var.get()),
            skip_completed=bool(self.skip_completed_var.get()),
            only_failed=bool(self.only_failed_var.get()),
            max_pages=int(self.maxpages_var.get() or 0),
            asset_cache=True,
        )
        # Attach concurrency dynamically
        setattr(cfg, 'concurrency', int(self.conc_var.get() or 1))
        self._controller = ArchaicController(cfg)

        def run_worker():
            try:
                stats = self._controller.run(progress=lambda s: self._queue.put(("progress", s)))
                self._queue.put(("done", stats))
            except Exception as e:
                self._queue.put(("error", str(e)))

        self._worker = threading.Thread(target=run_worker, daemon=True)
        self._worker.start()
        self._log("Started")
        self._save_settings()

    def _stop(self):
        if self._controller:
            self._controller.stop()
        self._log("Stop requested")

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "progress":
                    if isinstance(payload, dict):
                        self._handle_structured_progress(payload)
                    else:
                        self.status_var.set(str(payload))
                        self._log(payload)
                elif kind == "preview":
                    self.progress.stop()
                    self._show_preview_window(payload)
                elif kind == "done":
                    self.progress.stop()
                    self.start_btn.config(state=tk.NORMAL)
                    self.stop_btn.config(state=tk.DISABLED)
                    self.status_var.set("Completed")
                    self._log(f"Completed: {payload}")
                elif kind == "error":
                    self.progress.stop()
                    self.start_btn.config(state=tk.NORMAL)
                    self.stop_btn.config(state=tk.DISABLED)
                    self.status_var.set("Error")
                    self._log(f"Error: {payload}")
        except queue.Empty:
            pass
        self.after(150, self._poll_queue)

    def _log(self, msg: str):
        self.log.insert(tk.END, f"{msg}\n")
        self.log.see(tk.END)

    def _handle_structured_progress(self, data: dict):
        t = data.get('type')
        if t == 'discovery':
            total = int(data.get('total', 0))
            self.discovered_var.set(total)
            self.status_var.set(f"Discovered {total} pages")
            self._log(self.status_var.get())
        elif t == 'discovery_cap':
            proc = int(data.get('processing', 0))
            self.status_var.set(f"Processing first {proc} pages (capped)")
            self._log(self.status_var.get())
        elif t == 'url':
            idx = data.get('index', '')
            stage = data.get('stage', '')
            url = data.get('url', '')
            if stage == 'completed':
                self.completed_var.set(self.completed_var.get() + 1)
                status = 'Completed'
            elif stage == 'failed':
                self.failed_var.set(self.failed_var.get() + 1)
                reason = data.get('reason', '')
                status = f"Failed ({reason})" if reason else 'Failed'
            else:
                status = stage.capitalize() if stage else 'Working'
            # Insert/update row (simple append for now)
            self.tree.insert('', tk.END, values=(status, url))
            self.status_var.set(f"[{idx}] {status} – {url}")
            self._log(self.status_var.get())
        elif t == 'counters':
            stats = data.get('stats', {})
            # These counters align approximately; discovered already set earlier
            self.completed_var.set(int(stats.get('pdf', self.completed_var.get())))
            self.failed_var.set(int(stats.get('failed', self.failed_var.get())))

    def _show_preview_window(self, pages: list):
        win = tk.Toplevel(self)
        win.title("Discovery Preview")
        win.geometry("700x400")
        total = len(pages)
        ttk.Label(win, text=f"Discovered {total} pages").pack(anchor='w', padx=10, pady=6)
        frame = ttk.Frame(win)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=6)
        listbox = tk.Listbox(frame)
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=listbox.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        listbox.configure(yscrollcommand=sb.set)
        # Show first 200 entries
        for rec in pages[:200]:
            listbox.insert(tk.END, rec.get('url', ''))
        ttk.Label(win, text="Use 'Max pages' in Advanced to limit processing.").pack(anchor='w', padx=10)
        ttk.Button(win, text="Close", command=win.destroy).pack(pady=8)

    # Utilities
    def _open_output(self):
        import os, subprocess, sys
        path = self.out_var.get().strip() or 'output'
        path = os.path.abspath(path)
        try:
            if sys.platform.startswith('darwin'):
                subprocess.Popen(['open', path])
            elif os.name == 'nt':
                os.startfile(path)
            else:
                subprocess.Popen(['xdg-open', path])
        except Exception as e:
            messagebox.showerror("Open Output", str(e))

    def _view_log(self):
        import os, subprocess, sys
        path = os.path.abspath('logs')
        try:
            if sys.platform.startswith('darwin'):
                subprocess.Popen(['open', path])
            elif os.name == 'nt':
                os.startfile(path)
            else:
                subprocess.Popen(['xdg-open', path])
        except Exception as e:
            messagebox.showerror("View Log", str(e))

    def _open_index(self):
        import os, subprocess, sys
        base = self.out_var.get().strip() or 'output'
        index_path = os.path.abspath(os.path.join(base, 'index.html'))
        try:
            if sys.platform.startswith('darwin'):
                subprocess.Popen(['open', index_path])
            elif os.name == 'nt':
                os.startfile(index_path)
            else:
                subprocess.Popen(['xdg-open', index_path])
        except Exception as e:
            messagebox.showerror("Open Index", str(e))

    def _preview(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showerror("Validation", "Please enter a target URL path")
            return
        self.status_var.set("Discovering...")
        self.progress.start(80)
        def worker():
            try:
                cdx = CDXClient()
                pages = cdx.discover_urls(url)
                self._queue.put(("progress", {"type": "discovery", "total": len(pages)}))
                self._queue.put(("preview", pages))
            except Exception as e:
                self._queue.put(("error", str(e)))
        threading.Thread(target=worker, daemon=True).start()

    # Settings persistence
    def _settings_path(self):
        import os
        return os.path.join(os.path.abspath('.'), '.archaic_gui.json')

    def _load_settings(self):
        import json, os
        path = self._settings_path()
        if not os.path.exists(path):
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.url_var.set(data.get('base_url', ''))
            self.out_var.set(data.get('output_dir', 'output'))
            self.offline_var.set(bool(data.get('offline_assets', True)))
            self.singlefile_var.set(bool(data.get('single_file_html', False)))
            self.conc_var.set(int(data.get('concurrency', 1)))
            self.delay_var.set(float(data.get('delay_secs', 1.5)))
            self.maxpages_var.set(int(data.get('max_pages', 0)))
            self.skip_completed_var.set(bool(data.get('skip_completed', True)))
            self.only_failed_var.set(bool(data.get('only_failed', False)))
        except Exception:
            pass

    def _save_settings(self):
        import json
        data = {
            'base_url': self.url_var.get().strip(),
            'output_dir': self.out_var.get().strip() or 'output',
            'offline_assets': bool(self.offline_var.get()),
            'single_file_html': bool(self.singlefile_var.get()),
            'concurrency': int(self.conc_var.get() or 1),
            'delay_secs': float(self.delay_var.get() or 1.5),
            'max_pages': int(self.maxpages_var.get() or 0),
            'skip_completed': bool(self.skip_completed_var.get()),
            'only_failed': bool(self.only_failed_var.get()),
        }
        try:
            with open(self._settings_path(), 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


def main():
    app = ArchaicApp()
    app.mainloop()


if __name__ == "__main__":
    main()
