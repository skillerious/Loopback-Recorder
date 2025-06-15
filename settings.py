"""
Settings dialog for Loopback Recorder
=====================================

• Modal CTkToplevel centered on screen.
• Grouped sections using CTkFrame with bold headers.
• Auto-saves on any change via on_change callback.
• Persists prefs (including Post-gain) in %APPDATA%/LoopbackRecorder/prefs.json.
"""

from __future__ import annotations
import os
import json
from pathlib import Path
from typing import Optional, Callable

import customtkinter as ctk
from PIL import Image
from tkinter import filedialog, ttk
import sounddevice as sd

# ── asset helper ────────────────────────────────────────────────────
ASSETS = Path(__file__).with_name("assets")

def icon(name: str, size: int = 20) -> Optional[ctk.CTkImage]:
    fp = ASSETS / name
    if not fp.exists():
        return None
    img = Image.open(fp).resize((size, size), Image.LANCZOS)
    return ctk.CTkImage(light_image=img, dark_image=img)


class Settings(ctk.CTkToplevel):
    """Modal, centered Settings dialog with grouped sections and Post-gain control."""

    def __init__(self, master, on_change: Callable[[], None], prefs: dict):
        super().__init__(master)
        self.on_change = on_change

        # ── prefs file in APPDATA (or ~/.config) ───────────────────────
        if os.name == "nt":
            appdir = Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming")) / "LoopbackRecorder"
        else:
            appdir = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")) / "LoopbackRecorder"
        appdir.mkdir(parents=True, exist_ok=True)
        self.PREF_FILE = appdir / "prefs.json"

        # ── start hidden until toggle() ────────────────────────────────
        self.withdraw()
        self.title("Settings")
        self.resizable(False, False)
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self._hide)

        # ── schedule center after geometry settles ────────────────────
        self.after(0, self._center)

        # ── Force window size to fit all controls ────────────────────
        self.geometry("600x560")
        self.minsize(600, 560)

        # ── enumerate WASAPI input devices ────────────────────────────
        devs = [
            (i, d) for i, d in enumerate(sd.query_devices())
            if d["max_input_channels"] > 0
            and "wasapi" in sd.query_hostapis(d["hostapi"])["name"].lower()
        ]
        self._map = {
            f"{d['name']} ({d['max_input_channels']} ch)": i
            for i, d in devs
        } or {"<No Input>": 0}

        # ── detect pydub support for MP3 ─────────────────────────────
        try:
            import pydub  # noqa
            HAVE_PYDUB = True
        except ModuleNotFoundError:
            HAVE_PYDUB = False

        self.fmts = ["wav", "flac"] + (["mp3"] if HAVE_PYDUB else [])

        # ── load incoming prefs or defaults ──────────────────────────
        self.var_dev   = ctk.StringVar(value=prefs.get("dev", next(iter(self._map))))
        self.var_fmt   = ctk.StringVar(value=prefs.get("fmt", self.fmts[0]))
        self.var_dir   = ctk.StringVar(value=prefs.get("dir", str(Path.home())))
        self.var_base  = ctk.StringVar(value=prefs.get("base", "Recording"))
        self.var_split = ctk.StringVar(value=str(prefs.get("split", 0)))
        self.var_sdb   = ctk.StringVar(value=str(prefs.get("sdb", "")))
        self.var_slen  = ctk.StringVar(value=str(prefs.get("slen", 2.0)))
        self.var_gate  = ctk.BooleanVar(value=prefs.get("gate", False))
        self.var_gain  = ctk.StringVar(value=str(prefs.get("gain", 12.0)))  # new Post-gain

        # ── Build grouped sections ────────────────────────────────────

        # Audio section
        ctk.CTkLabel(self, text="Audio", font=("Segoe UI", 12, "bold")).pack(
            anchor="w", padx=20, pady=(20, 4))
        audio_fr = ctk.CTkFrame(self, fg_color="transparent",
                                border_width=1, border_color="#333")
        audio_fr.pack(fill="x", padx=20, pady=(0,10))
        audio_fr.columnconfigure(1, weight=1)

        ctk.CTkLabel(audio_fr, text="Input Device:").grid(
            row=0, column=0, sticky="e", padx=10, pady=6)
        ctk.CTkOptionMenu(
            audio_fr, variable=self.var_dev, values=list(self._map),
            width=350, command=lambda *_: self._changed()
        ).grid(row=0, column=1, padx=10, pady=6)

        ctk.CTkLabel(audio_fr, text="Format:").grid(
            row=1, column=0, sticky="e", padx=10, pady=6)
        ctk.CTkOptionMenu(
            audio_fr, variable=self.var_fmt, values=self.fmts,
            width=120, command=lambda *_: self._changed()
        ).grid(row=1, column=1, padx=10, pady=6)

        # File section
        ctk.CTkLabel(self, text="File", font=("Segoe UI", 12, "bold")).pack(
            anchor="w", padx=20, pady=(10,4))
        file_fr = ctk.CTkFrame(self, fg_color="transparent",
                               border_width=1, border_color="#333")
        file_fr.pack(fill="x", padx=20, pady=(0,10))
        file_fr.columnconfigure(1, weight=1)

        ctk.CTkLabel(file_fr, text="Save Directory:").grid(
            row=0, column=0, sticky="e", padx=10, pady=6)
        ctk.CTkEntry(file_fr, textvariable=self.var_dir, width=350).grid(
            row=0, column=1, sticky="w", padx=10, pady=6)
        ctk.CTkButton(
            file_fr, image=icon("folder.png"), text="",
            width=30, command=lambda: self._browse(self.var_dir)
        ).grid(row=0, column=2, padx=10, pady=6)

        ctk.CTkLabel(file_fr, text="Base Name:").grid(
            row=1, column=0, sticky="e", padx=10, pady=6)
        ctk.CTkEntry(
            file_fr, textvariable=self.var_base, width=200
        ).grid(row=1, column=1, columnspan=2, sticky="w", padx=10, pady=6)

        # Recording section
        ctk.CTkLabel(self, text="Recording", font=("Segoe UI", 12, "bold")).pack(
            anchor="w", padx=20, pady=(10,4))
        rec_fr = ctk.CTkFrame(self, fg_color="transparent",
                              border_width=1, border_color="#333")
        rec_fr.pack(fill="x", padx=20, pady=(0,10))
        rec_fr.columnconfigure(1, weight=1)

        ctk.CTkLabel(rec_fr, text="Split (min):").grid(
            row=0, column=0, sticky="e", padx=10, pady=6)
        ctk.CTkEntry(
            rec_fr, textvariable=self.var_split, width=80
        ).grid(row=0, column=1, sticky="w", padx=10, pady=6)

        ctk.CTkLabel(rec_fr, text="Silence dB:").grid(
            row=1, column=0, sticky="e", padx=10, pady=6)
        ctk.CTkEntry(
            rec_fr, textvariable=self.var_sdb, width=80
        ).grid(row=1, column=1, sticky="w", padx=10, pady=6)

        ctk.CTkLabel(rec_fr, text="Silence Sec:").grid(
            row=2, column=0, sticky="e", padx=10, pady=6)
        ctk.CTkEntry(
            rec_fr, textvariable=self.var_slen, width=80
        ).grid(row=2, column=1, sticky="w", padx=10, pady=6)

        ctk.CTkCheckBox(
            rec_fr, text="Enable Noise Gate",
            variable=self.var_gate, command=self._changed
        ).grid(row=3, column=1, sticky="w", padx=10, pady=(6,12))

        # New Post-gain control
        ctk.CTkLabel(rec_fr, text="Post-gain (dB):").grid(
            row=4, column=0, sticky="e", padx=10, pady=6)
        ctk.CTkEntry(
            rec_fr, textvariable=self.var_gain, width=80
        ).grid(row=4, column=1, sticky="w", padx=10, pady=6)

        # Separator + Close
        sep = ttk.Separator(self, orient="horizontal")
        sep.pack(fill="x", padx=20, pady=(10,10))
        ctk.CTkButton(self, text="Close", width=80, command=self._hide).pack(pady=(0,20))

        # trace any change → auto-save
        for v in (
            self.var_dev, self.var_fmt, self.var_dir,
            self.var_base, self.var_split, self.var_sdb,
            self.var_slen, self.var_gate, self.var_gain
        ):
            v.trace_add("write", lambda *a: self._changed())

    # ── internal handlers ───────────────────────────────────────────
    def _browse(self, var: ctk.StringVar):
        path = filedialog.askdirectory(initialdir=var.get())
        if path:
            var.set(path)

    def _changed(self):
        # write out the entire prefs file immediately
        try:
            out = self.dump()
            self.PREF_FILE.write_text(json.dumps(out, indent=2))
        except Exception:
            pass
        self.on_change()

    def _hide(self):
        self.grab_release()
        self.withdraw()

    def toggle(self):
        """Show or hide the modal dialog."""
        if self.winfo_viewable():
            self._hide()
        else:
            self.deiconify()
            self.grab_set()
            self.lift()
            self.focus_force()
            self.after(0, self._center)

    def _center(self):
        """Center window on screen."""
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = self.winfo_width(), self.winfo_height()
        x, y = (sw - w)//2, (sh - h)//2
        self.geometry(f"{w}x{h}+{x}+{y}")

    # ── public getters for main app ─────────────────────────────────
    def dev_idx(self) -> int:
        return self._map.get(self.var_dev.get(), 0)

    def fmt(self) -> str:
        return self.var_fmt.get()

    def dir(self) -> str:
        return self.var_dir.get()

    def base(self) -> str:
        return self.var_base.get() or "Recording"

    def split_secs(self) -> Optional[int]:
        try:
            m = int(self.var_split.get())
            return m * 60 if m > 0 else None
        except ValueError:
            return None

    def sdb(self) -> Optional[float]:
        try:
            return float(self.var_sdb.get())
        except ValueError:
            return None

    def slen(self) -> float:
        try:
            return float(self.var_slen.get())
        except ValueError:
            return 2.0

    def gate(self) -> bool:
        return self.var_gate.get()

    def gain(self) -> float:
        """Post-gain in dB for pydub.apply_gain()."""
        try:
            return float(self.var_gain.get())
        except ValueError:
            return 12.0

    def dump(self) -> dict:
        """Return all settings as a serializable dict."""
        return {
            "dev":   self.var_dev.get(),
            "fmt":   self.var_fmt.get(),
            "dir":   self.var_dir.get(),
            "base":  self.var_base.get(),
            "split": int(self.var_split.get() or 0),
            "sdb":   self.var_sdb.get(),
            "slen":  self.var_slen.get(),
            "gate":  self.var_gate.get(),
            "gain":  float(self.var_gain.get() or 12.0),
        }
