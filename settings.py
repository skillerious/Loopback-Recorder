"""
Settings dialog for Loopback Recorder
— polished sidebar navigator in a card layout —
"""

from __future__ import annotations
import os, json
from pathlib import Path
from typing import Optional, Callable

import customtkinter as ctk
from PIL import Image
from tkinter import filedialog
import sounddevice as sd

ASSETS = Path(__file__).with_name("assets")

def icon(name: str, size: int = 28) -> Optional[ctk.CTkImage]:
    fp = ASSETS / name
    if not fp.exists():
        return None
    img = Image.open(fp).resize((size, size), Image.LANCZOS)
    return ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))


class Settings(ctk.CTkToplevel):
    def __init__(self, master, on_change: Callable[[], None], prefs: dict):
        super().__init__(master)
        self.on_change = on_change

        # prefs file in APPDATA / XDG_CONFIG_HOME
        if os.name == "nt":
            cfg = Path(os.getenv("APPDATA", "")) / "LoopbackRecorder"
        else:
            cfg = Path(os.getenv("XDG_CONFIG_HOME", "")) / "LoopbackRecorder"
        cfg.mkdir(parents=True, exist_ok=True)
        self.PREF_FILE = cfg / "prefs.json"

        # window setup
        self.withdraw()
        self.title("Settings")
        self.geometry("720x480")
        self.minsize(720, 480)
        self.transient(master)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._hide)
        self.configure(fg_color="#222222")
        self.after(0, self._center)

        # enumerate WASAPI input devices
        devs = [
            (i, d) for i, d in enumerate(sd.query_devices())
            if d["max_input_channels"] > 0
            and "wasapi" in sd.query_hostapis(d["hostapi"])["name"].lower()
        ]
        self._map = {
            f"{d['name']} ({d['max_input_channels']} ch)": i
            for i, d in devs
        } or {"<No Input>": 0}

        # detect MP3 support
        try:
            import pydub  # noqa
            HAVE_MP3 = True
        except ModuleNotFoundError:
            HAVE_MP3 = False
        fmts = ["wav", "flac"] + (["mp3"] if HAVE_MP3 else [])

        # Tk variables
        self.var_dev   = ctk.StringVar(value=prefs.get("dev", next(iter(self._map))))
        self.var_fmt   = ctk.StringVar(value=prefs.get("fmt", fmts[0]))
        self.var_dir   = ctk.StringVar(value=prefs.get("dir", str(Path.home())))
        self.var_base  = ctk.StringVar(value=prefs.get("base", "Recording"))
        self.var_split = ctk.StringVar(value=str(prefs.get("split", 0)))
        self.var_sdb   = ctk.StringVar(value=str(prefs.get("sdb", "")))
        self.var_slen  = ctk.StringVar(value=str(prefs.get("slen", 2.0)))
        self.var_gate  = ctk.BooleanVar(value=prefs.get("gate", False))
        self.var_gain  = ctk.StringVar(value=str(prefs.get("gain", 12.0)))

        # — card container —
        card = ctk.CTkFrame(
            self,
            fg_color="#2b2b2b",
            corner_radius=8,
            border_width=1,
            border_color="#333333"
        )
        card.pack(fill="both", expand=True, padx=20, pady=(20, 10))
        card.grid_columnconfigure(1, weight=1)
        card.grid_rowconfigure(0, weight=1)

        # — sidebar —
        sidebar = ctk.CTkFrame(card, width=140, fg_color="#1f1f1f", corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="ns", padx=(0, 8), pady=8)
        sidebar.grid_propagate(False)
        sidebar.grid_rowconfigure(4, weight=1)

        # active-tab indicator
        self._indicator = ctk.CTkFrame(sidebar, width=4, fg_color="#80DEEA")

        # sidebar buttons
        self._btns: dict[str, ctk.CTkButton] = {}
        for idx, (label, imgfile) in enumerate([
            ("Audio",     "audio.png"),
            ("File",      "folder1.png"),
            ("Recording", "record1.png"),
        ]):
            img = icon(imgfile)
            btn = ctk.CTkButton(
                master=sidebar,
                text=label,
                image=img,
                compound="left",
                anchor="w",
                width=120,
                height=32,
                fg_color="transparent",
                hover_color="#333333",
                text_color="#ddd",
                font=("Segoe UI", 12)
            )
            btn.configure(command=lambda l=label: self._select(l))
            btn.grid(row=idx, column=0, pady=6, padx=(12, 4), sticky="w")
            self._btns[label] = btn

        # — content panels —
        self._panels: dict[str, ctk.CTkFrame] = {}
        self._make_audio_panel(card, fmts)
        self._make_file_panel(card)
        self._make_recording_panel(card)

        # — footer —
        close = ctk.CTkButton(
            master=self,
            text="Close",
            width=120,
            fg_color="#80DEEA",
            hover_color="#6fdcee",
            text_color="#222222",
            command=self._hide
        )
        close.pack(pady=(0, 20))

        # auto-save on change
        for var in (
            self.var_dev, self.var_fmt, self.var_dir, self.var_base,
            self.var_split, self.var_sdb, self.var_slen, self.var_gain
        ):
            var.trace_add("write", lambda *a: self._changed())

        # show the first tab
        self._select("Audio")


    def _make_audio_panel(self, parent, fmts):
        p = ctk.CTkFrame(parent, fg_color="transparent")
        p.grid(row=0, column=1, sticky="nsew", padx=(8, 20), pady=20)
        p.columnconfigure(1, weight=1)
        self._panels["Audio"] = p

        ctk.CTkLabel(p, text="Input Device:", anchor="e") \
            .grid(row=0, column=0, padx=10, pady=12)
        ctk.CTkOptionMenu(
            master=p,
            variable=self.var_dev,
            values=list(self._map),
            width=320,
            command=lambda *_: self._changed()
        ).grid(row=0, column=1, sticky="w", padx=10, pady=12)

        ctk.CTkLabel(p, text="Format:", anchor="e") \
            .grid(row=1, column=0, padx=10, pady=12)
        ctk.CTkOptionMenu(
            master=p,
            variable=self.var_fmt,
            values=fmts,
            width=120,
            command=lambda *_: self._changed()
        ).grid(row=1, column=1, sticky="w", padx=10, pady=12)


    def _make_file_panel(self, parent):
        p = ctk.CTkFrame(parent, fg_color="transparent")
        p.grid(row=0, column=1, sticky="nsew", padx=(8, 20), pady=20)
        p.columnconfigure(1, weight=1)
        self._panels["File"] = p

        ctk.CTkLabel(p, text="Save Directory:", anchor="e") \
            .grid(row=0, column=0, padx=10, pady=12)
        ctk.CTkEntry(p, textvariable=self.var_dir, width=320) \
            .grid(row=0, column=1, sticky="w", padx=10, pady=12)
        ctk.CTkButton(
            master=p,
            image=icon("folder.png"),
            text="",
            width=30,
            command=lambda: self._browse(self.var_dir)
        ).grid(row=0, column=2, padx=10, pady=12)

        ctk.CTkLabel(p, text="Base Name:", anchor="e") \
            .grid(row=1, column=0, padx=10, pady=12)
        ctk.CTkEntry(p, textvariable=self.var_base, width=200) \
            .grid(row=1, column=1, columnspan=2, padx=10, pady=12, sticky="w")


    def _make_recording_panel(self, parent):
        p = ctk.CTkFrame(parent, fg_color="transparent")
        p.grid(row=0, column=1, sticky="nsew", padx=(8, 20), pady=20)
        p.columnconfigure(1, weight=1)
        self._panels["Recording"] = p

        specs = [
            ("Split (min):",    self.var_split),
            ("Silence dB:",     self.var_sdb),
            ("Silence Sec:",    self.var_slen),
            ("Post-gain (dB):", self.var_gain),
        ]
        for i, (lbl, var) in enumerate(specs):
            ctk.CTkLabel(p, text=lbl, anchor="e") \
                .grid(row=i, column=0, padx=10, pady=8, sticky="e")
            ctk.CTkEntry(p, textvariable=var, width=80) \
                .grid(row=i, column=1, padx=10, pady=8, sticky="w")

        # Noise gate checkbox
        ctk.CTkCheckBox(
            master=p,
            text="Enable Noise Gate",
            variable=self.var_gate,
            command=self._changed
        ).grid(row=4, column=1, padx=10, pady=(8,4), sticky="w")

        # Friendly help text, now in 11px
        ctk.CTkLabel(
            p,
            text=(
                "🔊 Desktop audio often records quieter than you hear. "
                "If your tracks sound low, bump the Post-gain above."
            ),
            font=("Segoe UI", 11),
            text_color="#BBB",
            wraplength=360,
            justify="left"
        ).grid(
            row=5,
            column=1,
            columnspan=2,
            padx=10,
            pady=(0,16),
            sticky="w"
        )



    def _select(self, section: str):
        # highlight button & slide indicator
        for name, btn in self._btns.items():
            is_active = (name == section)
            btn.configure(text_color=("#80DEEA" if is_active else "#ddd"))
            if is_active:
                h = btn.winfo_height()
                y = btn.winfo_y()
                self._indicator.configure(height=h)
                self._indicator.place(x=4, y=y)

        # show only the chosen panel
        for name, panel in self._panels.items():
            panel.grid_forget()
        self._panels[section].grid(row=0, column=1, sticky="nsew", padx=(8, 20), pady=20)


    def _browse(self, var: ctk.StringVar):
        d = filedialog.askdirectory(initialdir=var.get())
        if d:
            var.set(d)


    def _changed(self):
        try:
            self.PREF_FILE.write_text(json.dumps(self.dump(), indent=2))
        except Exception:
            pass
        self.on_change()


    def _hide(self):
        self.grab_release()
        self.withdraw()


    def toggle(self):
        if self.winfo_viewable():
            self._hide()
        else:
            self.update_idletasks()
            self.deiconify()
            self.grab_set()
            self.lift()
            self.focus_force()
            self.after(0, self._center)


    def _center(self):
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h   = self.winfo_width(), self.winfo_height()
        x, y   = (sw - w)//2, (sh - h)//2
        self.geometry(f"{w}x{h}+{x}+{y}")


    # ─── public getters & dump ─────────────────────────
    def dev_idx(self)   -> int:             return self._map.get(self.var_dev.get(), 0)
    def fmt(self)       -> str:             return self.var_fmt.get()
    def dir(self)       -> str:             return self.var_dir.get()
    def base(self)      -> str:             return self.var_base.get() or "Recording"
    def split_secs(self)-> Optional[int]:
        try:    m = int(self.var_split.get()); return (m*60 if m>0 else None)
        except: return None
    def sdb(self)       -> Optional[float]:
        try:    return float(self.var_sdb.get())
        except: return None
    def slen(self)      -> float:
        try:    return float(self.var_slen.get())
        except: return 2.0
    def gate(self)      -> bool:            return self.var_gate.get()
    def gain(self)      -> float:
        try:    return float(self.var_gain.get())
        except: return 12.0
    def dump(self)      -> dict:
        return {
            "dev":   self.var_dev.get(),
            "fmt":   self.var_fmt.get(),
            "dir":   self.var_dir.get(),
            "base":  self.var_base.get(),
            "split": int(self.var_split.get() or 0),
            "sdb":   self.var_sdb.get(),
            "slen":  self.var_slen.get(),
            "gate":  self.var_gate.get(),
            "gain":  self.gain(),
        }
