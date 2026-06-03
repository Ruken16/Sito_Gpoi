from __future__ import annotations

import queue
import threading
import tkinter as tk
from datetime import date
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable

from .core import COMMON_METHODS, RANGE_METHODS, fetch_info, fetch_method, friendly_error, json_text, load_config, package_version, save_env_file


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("ClasseViva Probe GUI")
        self.geometry("1300x850")
        self.minsize(1100, 700)

        self.result_queue: queue.Queue[tuple[str, str, str]] = queue.Queue()
        self.is_busy = False
        self.method_buttons: list[ttk.Button] = []
        self.tabs: dict[str, tk.Text] = {}
        self.tab_order: list[str] = []

        cfg = load_config()
        self.username_var = tk.StringVar(value=cfg.username or "")
        self.password_var = tk.StringVar(value=cfg.password or "")
        today = date.today().isoformat()
        self.day_var = tk.StringVar(value=today)
        self.start_var = tk.StringVar(value=f"{date.today().year}-09-01")
        self.end_var = tk.StringVar(value=today)
        self.status_var = tk.StringVar(value=f"Pronto · Classeviva.py {package_version()}")

        self._build_ui()
        self.after(150, self._poll_queue)

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self, padding=12)
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        for i in range(6):
            header.columnconfigure(i, weight=1 if i in (1, 3) else 0)

        ttk.Label(header, text="Username").grid(row=0, column=0, sticky="w")
        ttk.Entry(header, textvariable=self.username_var, width=24).grid(row=0, column=1, sticky="ew", padx=(6, 12))
        ttk.Label(header, text="Password").grid(row=0, column=2, sticky="w")
        ttk.Entry(header, textvariable=self.password_var, show="*", width=24).grid(row=0, column=3, sticky="ew", padx=(6, 12))
        ttk.Button(header, text="Salva .env", command=self.save_credentials).grid(row=0, column=4, padx=(0, 8))
        ttk.Button(header, text="Test login", command=lambda: self.run_info()).grid(row=0, column=5)

        sidebar = ttk.Frame(self, padding=(12, 0, 8, 12))
        sidebar.grid(row=1, column=0, sticky="ns")

        main = ttk.Frame(self, padding=(8, 0, 12, 12))
        main.grid(row=1, column=1, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(1, weight=1)

        quick = ttk.LabelFrame(sidebar, text="Caricamento rapido", padding=10)
        quick.grid(row=0, column=0, sticky="ew")
        ttk.Button(quick, text="Carica tutto", command=self.load_everything).grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(quick, text="Info", command=self.run_info).grid(row=1, column=0, sticky="ew", pady=2)
        ttk.Button(quick, text="Esporta tab corrente", command=self.export_current_tab).grid(row=2, column=0, sticky="ew", pady=2)

        common = ttk.LabelFrame(sidebar, text="Endpoint standard", padding=10)
        common.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        row = 0
        for tab_name, (label, method_name) in COMMON_METHODS.items():
            if tab_name == "info":
                continue
            btn = ttk.Button(common, text=label, command=lambda tn=tab_name, mn=method_name: self.run_method(tn, mn))
            btn.grid(row=row, column=0, sticky="ew", pady=2)
            self.method_buttons.append(btn)
            row += 1

        dated = ttk.LabelFrame(sidebar, text="Per giorno / intervallo", padding=10)
        dated.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        ttk.Label(dated, text="Giorno (YYYY-MM-DD)").grid(row=0, column=0, sticky="w")
        ttk.Entry(dated, textvariable=self.day_var, width=18).grid(row=1, column=0, sticky="ew", pady=(0, 6))
        btn = ttk.Button(dated, text="Lezioni del giorno", command=self.run_lessons_day)
        btn.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        self.method_buttons.append(btn)

        ttk.Label(dated, text="Da").grid(row=3, column=0, sticky="w")
        ttk.Entry(dated, textvariable=self.start_var, width=18).grid(row=4, column=0, sticky="ew")
        ttk.Label(dated, text="A").grid(row=5, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(dated, textvariable=self.end_var, width=18).grid(row=6, column=0, sticky="ew")

        for i, (tab_name, (label, method_name)) in enumerate(RANGE_METHODS.items(), start=7):
            btn = ttk.Button(dated, text=label, command=lambda tn=tab_name, mn=method_name: self.run_range_method(tn, mn))
            btn.grid(row=i, column=0, sticky="ew", pady=2)
            self.method_buttons.append(btn)

        help_box = ttk.LabelFrame(sidebar, text="Note", padding=10)
        help_box.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        ttk.Label(
            help_box,
            justify="left",
            wraplength=240,
            text=(
                "• I dati vengono mostrati in JSON grezzo.\n"
                "• I metodi 'lezioni' possono fallire per alcuni account con 'invalid student-id'.\n"
                "• Salva le credenziali nel file .env per non reinserirle ogni volta."
            ),
        ).grid(row=0, column=0, sticky="w")

        topbar = ttk.Frame(main)
        topbar.grid(row=0, column=0, sticky="ew")
        ttk.Label(topbar, textvariable=self.status_var).grid(row=0, column=0, sticky="w")

        self.notebook = ttk.Notebook(main)
        self.notebook.grid(row=1, column=0, sticky="nsew", pady=(8, 0))

        self._ensure_tab("home", "Benvenuto")
        self._set_tab_text(
            "home",
            "Benvenuto",
            (
                "ClasseViva Probe GUI\n\n"
                "1. Inserisci username e password oppure caricali da .env\n"
                "2. Premi 'Test login'\n"
                "3. Usa 'Carica tutto' o i pulsanti laterali per vedere i dati\n\n"
                "L'output è lasciato in JSON così puoi capire subito se un endpoint risponde oppure no."
            ),
        )

    def _set_busy(self, busy: bool) -> None:
        self.is_busy = busy
        state = "disabled" if busy else "normal"
        for button in self.method_buttons:
            button.configure(state=state)

    def _build_cfg(self):
        return load_config(username=self.username_var.get().strip(), password=self.password_var.get().strip())

    def save_credentials(self) -> None:
        try:
            path = save_env_file(self.username_var.get().strip(), self.password_var.get().strip())
            self.status_var.set(f"Credenziali salvate in {path}")
            messagebox.showinfo("Salvato", f"Credenziali salvate in {path}")
        except Exception as exc:
            messagebox.showerror("Errore", str(exc))

    def _ensure_tab(self, key: str, title: str) -> None:
        if key in self.tabs:
            return
        frame = ttk.Frame(self.notebook)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        text = tk.Text(frame, wrap="none", font=("Consolas", 10))
        yscroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        xscroll = ttk.Scrollbar(frame, orient="horizontal", command=text.xview)
        text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        text.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        self.notebook.add(frame, text=title)
        self.tabs[key] = text
        self.tab_order.append(key)

    def _set_tab_text(self, key: str, title: str, content: str) -> None:
        self._ensure_tab(key, title)
        text = self.tabs[key]
        text.delete("1.0", "end")
        text.insert("1.0", content)
        index = self.tab_order.index(key)
        self.notebook.tab(index, text=title)
        self.notebook.select(index)

    def _run_background(self, label: str, task: Callable[[], Any], tab_key: str) -> None:
        if self.is_busy:
            messagebox.showwarning("Attendere", "C'è già una richiesta in corso.")
            return

        self._set_busy(True)
        self.status_var.set(f"Caricamento: {label}...")

        def worker() -> None:
            try:
                result = task()
                self.result_queue.put((tab_key, label, json_text(result)))
            except Exception as exc:
                self.result_queue.put((tab_key, label, json_text(friendly_error(exc))))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_queue(self) -> None:
        try:
            while True:
                key, label, content = self.result_queue.get_nowait()
                self._set_tab_text(key, label, content)
                self.status_var.set(f"Completato: {label}")
                self._set_busy(False)
        except queue.Empty:
            pass
        self.after(150, self._poll_queue)

    def run_info(self) -> None:
        cfg = self._build_cfg()
        self._run_background("Informazioni utente e sessione", lambda: __import__("asyncio").run(fetch_info(cfg)), "info")

    def run_method(self, tab_key: str, method_name: str) -> None:
        cfg = self._build_cfg()
        label = COMMON_METHODS[tab_key][0]
        self._run_background(label, lambda: __import__("asyncio").run(fetch_method(cfg, method_name)), tab_key)

    def run_lessons_day(self) -> None:
        cfg = self._build_cfg()
        day = self.day_var.get().strip()
        self._run_background(
            f"Lezioni del giorno ({day})",
            lambda: __import__("asyncio").run(fetch_method(cfg, "lezioni_giorno", day)),
            "lezioni_giorno",
        )

    def run_range_method(self, tab_key: str, method_name: str) -> None:
        cfg = self._build_cfg()
        start = self.start_var.get().strip()
        end = self.end_var.get().strip()
        label = RANGE_METHODS[tab_key][0] + f" ({start} → {end})"
        self._run_background(label, lambda: __import__("asyncio").run(fetch_method(cfg, method_name, start, end)), tab_key)

    def load_everything(self) -> None:
        cfg = self._build_cfg()
        day = self.day_var.get().strip()
        start = self.start_var.get().strip()
        end = self.end_var.get().strip()

        def task() -> dict[str, Any]:
            import asyncio

            async def inner() -> dict[str, Any]:
                bundle: dict[str, Any] = {}
                bundle["info"] = await fetch_info(cfg)
                for key, (_, method_name) in COMMON_METHODS.items():
                    if key == "info":
                        continue
                    try:
                        bundle[key] = await fetch_method(cfg, method_name)
                    except Exception as exc:
                        bundle[key] = friendly_error(exc)
                try:
                    bundle["lezioni_giorno"] = await fetch_method(cfg, "lezioni_giorno", day)
                except Exception as exc:
                    bundle["lezioni_giorno"] = friendly_error(exc)
                for key, (_, method_name) in RANGE_METHODS.items():
                    try:
                        bundle[key] = await fetch_method(cfg, method_name, start, end)
                    except Exception as exc:
                        bundle[key] = friendly_error(exc)
                return bundle

            return asyncio.run(inner())

        self._run_background("Carica tutto", task, "all_data")

    def export_current_tab(self) -> None:
        current = self.notebook.index(self.notebook.select())
        if current >= len(self.tab_order):
            return
        key = self.tab_order[current]
        text = self.tabs[key].get("1.0", "end").strip()
        if not text:
            messagebox.showwarning("Vuoto", "La tab corrente non contiene dati da esportare.")
            return
        path = filedialog.asksaveasfilename(
            title="Esporta JSON",
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("Text", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        self.status_var.set(f"Esportato: {path}")
        messagebox.showinfo("Esportato", f"File salvato in:\n{path}")


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
