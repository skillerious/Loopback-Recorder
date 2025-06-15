"""
Loopback Recorder • console-rail (full main.py • 2025-06-15)

Folder layout expected
----------------------
AudioLoopbackApp/
├─ main.py          ← this file
├─ settings.py      ← modal Settings dialog
├─ about.py         ← modal About dialog
├─ assets/
│   ├─ record.png
│   ├─ stop.png
│   ├─ settings.png
│   └─ folder.png
└─ logs/            ← created automatically
"""

from __future__ import annotations
import datetime as dt
import json
import logging
import math
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional, Tuple

import customtkinter as ctk
import matplotlib
import numpy as np
import sounddevice as sd
import soundfile as sf
import tkinter as tk
from PIL import Image
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from tkinter import ttk, messagebox

from mutagen.wave import WAVE
from mutagen.flac import FLAC
from mutagen.easyid3 import EasyID3

from settings import Settings, icon
from about import AboutDialog

# optional MP3 support
try:
    from pydub import AudioSegment  # type: ignore
except ModuleNotFoundError:
    AudioSegment = None

GIF_BG = "#242424"

# ── Logging setup ──────────────────────────────────────────────────
LOG_DIR = Path(__file__).with_name("logs")
LOG_DIR.mkdir(exist_ok=True)
log = logging.getLogger("looprec")
log.setLevel(logging.DEBUG)
fh = RotatingFileHandler(
    LOG_DIR / "loopback.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
)
fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s"))
log.addHandler(fh)
log.propagate = False
sys.excepthook = lambda t, v, b: (
    log.exception("Uncaught", exc_info=(t, v, b)),
    sys.__excepthook__(t, v, b),
)

# ── Helpers ────────────────────────────────────────────────────────
def open_in_explorer(path: Path) -> None:
    if os.name == "nt":
        subprocess.Popen(["explorer", "/select,", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path.parent)])


def human_bytes(b: int) -> str:
    return (
        f"{b/1_073_741_824:.1f} GB" if b >= 1_073_741_824 else f"{b/1_048_576:.1f} MB"
    )


# ── Recorder backend ───────────────────────────────────────────────
class Recorder:
    def __init__(
        self,
        dev: int,
        sr: int,
        ch: int,
        out: Path,
        base: str,
        fmt: str,
        split: Optional[int],
        sdb: Optional[float],
        slen: float,
        gate: bool,
    ):
        self.dev, self.sr, self.ch = dev, sr, ch
        self.out, self.base, self.fmt = out, base, fmt
        self.split, self.sdb, self.slen, self.gate = split, sdb, slen, gate
        self.audio_q = queue.Queue(maxsize=64)
        self.level_q = queue.Queue(maxsize=8)
        self._stop = threading.Event()
        self._writer = None
        self._stream = None
        self._file = None
        self._frames = 0
        self._silence = 0.0
        self._idx = 1
        self._ts = dt.datetime.now()
        self._tmp_wav = None
        self._mp3_target = None
        try:
            self._was = sd.WasapiSettings(loopback=True)
        except TypeError:
            self._was = sd.WasapiSettings()
            setattr(self._was, "loopback", True)

    def _stamp(self) -> str:
        return self._ts.strftime("%Y%m%d_%H%M%S")

    def _path(self) -> Path:
        return self.out / f"{self.base}_{self._stamp()}_{self._idx:03d}.{self.fmt}"

    def _open_file(self) -> None:
        if self.fmt in ("wav", "flac"):
            self._file = sf.SoundFile(
                self._path(),
                "w",
                self.sr,
                self.ch,
                subtype="PCM_16" if self.fmt == "wav" else None,
                format=self.fmt.upper(),
            )
        else:
            self._tmp_wav = Path(tempfile.mktemp(suffix=".wav"))
            self._mp3_target = self._path()
            self._file = sf.SoundFile(
                self._tmp_wav, "w", self.sr, self.ch, subtype="PCM_16"
            )

    def _close_file(self) -> None:
        if not self._file:
            return
        self._file.close()
        if self.fmt == "mp3" and AudioSegment:
            try:
                AudioSegment.from_wav(self._tmp_wav).export(
                    self._mp3_target, "mp3", bitrate="192k"
                )
                self._tmp_wav.unlink(missing_ok=True)
            except Exception as e:
                log.error("MP3 export failed: %s", e)

    def _rotate(self) -> None:
        self._close_file()
        self._idx += 1
        self._open_file()

    def start(self) -> None:
        self.out.mkdir(parents=True, exist_ok=True)
        self._open_file()
        self._stop.clear()
        self._writer = threading.Thread(target=self._writer_loop, daemon=True)
        self._writer.start()
        self._stream = sd.InputStream(
            device=self.dev,
            samplerate=self.sr,
            channels=self.ch,
            dtype="int16",
            callback=self._cb,
            blocksize=0,
            latency="low",
            extra_settings=self._was,
        )
        self._stream.start()

    def stop(self) -> None:
        self._stop.set()
        if self._stream:
            self._stream.stop()
            self._stream.close()
        if self._writer:
            self._writer.join()
        self._close_file()

    def is_running(self) -> bool:
        return bool(self._stream and self._stream.active)

    def _cb(self, indata, _frames, _time, status):
        if status:
            log.warning(status)
        self.audio_q.put(indata.copy())
        # compute rms/peak...
        if indata.ndim == 1 or indata.shape[1] == 1:
            pcm = indata.flatten()
            pk = np.max(np.abs(pcm)) / 32768
            rms = math.sqrt(np.mean(pcm.astype(np.float32) ** 2)) / 32768
            rms_db = -60 if rms == 0 else 20 * math.log10(rms)
            pk_db = -60 if pk == 0 else 20 * math.log10(pk)
            tup = (rms_db, pk_db, rms_db, pk_db, dt.datetime.now().timestamp())
        else:
            L, R = indata[:, 0], indata[:, 1]

            def dB(arr):
                p = np.max(np.abs(arr)) / 32768
                r = math.sqrt(np.mean(arr.astype(np.float32) ** 2)) / 32768
                return (
                    (-60 if r == 0 else 20 * math.log10(r)),
                    (-60 if p == 0 else 20 * math.log10(p)),
                )

            rmsL, pkL = dB(L)
            rmsR, pkR = dB(R)
            tup = (rmsL, pkL, rmsR, pkR, dt.datetime.now().timestamp())
        if not self.level_q.full():
            self.level_q.put(tup)

    def _writer_loop(self) -> None:
        split_frames = self.split * self.sr if self.split else None
        while not self._stop.is_set() or not self.audio_q.empty():
            try:
                buf = self.audio_q.get(timeout=0.1)
            except queue.Empty:
                continue
            pk = np.max(np.abs(buf)) / 32768
            dB = -60 if pk == 0 else 20 * math.log10(pk)
            if self.gate and self.sdb is not None and dB < self.sdb:
                buf[:] = 0
            if self.sdb is not None:
                self._silence = (
                    (self._silence + len(buf) / self.sr) if dB < self.sdb else 0
                )
                if self._silence >= self.slen:
                    self._rotate()
                    self._silence = 0
            self._frames += len(buf)
            if split_frames and self._frames >= split_frames:
                self._rotate()
            self._file.write(buf)


# ── RecordButton ────────────────────────────────────────────────────
class RecordButton(ctk.CTkCanvas):
    WIDTH, HEIGHT = 68, 68
    IDLE_TO_REC = (15, 32)
    REC_TO_IDLE = (48, 64)
    FRAME_DELAY = 40

    def __init__(self, master, command, frames_dir=None, **kw):
        super().__init__(
            master,
            width=self.WIDTH,
            height=self.HEIGHT,
            highlightthickness=0,
            bg=GIF_BG,
            **kw,
        )
        self.command, self.state = command, "idle"
        self._anim_job = None
        base = Path(frames_dir or Path(__file__).parent / "frames")
        files = sorted(base.glob("*.gif"), key=lambda p: int(p.stem))
        self._frames = [tk.PhotoImage(file=str(p)) for p in files]
        idle_frame = self.REC_TO_IDLE[1]
        self._img_id = self.create_image(
            self.WIDTH // 2,
            self.HEIGHT // 2,
            image=self._frames[idle_frame],
            anchor="center",
        )
        self.tag_bind("all", "<Button-1>", lambda e: self.command())

    def _cancel_anim(self):
        if self._anim_job:
            self.after_cancel(self._anim_job)
            self._anim_job = None

    def _play_sequence(self, start, end, on_complete=None):
        idx = start

        def step():
            nonlocal idx
            if idx > end:
                if on_complete:
                    on_complete()
                return
            self.itemconfig(self._img_id, image=self._frames[idx])
            idx += 1
            self._anim_job = self.after(self.FRAME_DELAY, step)

        self._cancel_anim()
        step()

    def set_recording(self):
        if self.state == "rec":
            return
        self.state = "rec"
        self._play_sequence(
            *self.IDLE_TO_REC,
            on_complete=lambda: self.itemconfig(
                self._img_id, image=self._frames[self.IDLE_TO_REC[1]]
            ),
        )

    def set_idle(self):
        self.state = "idle"
        self._play_sequence(
            *self.REC_TO_IDLE,
            on_complete=lambda: self.itemconfig(
                self._img_id, image=self._frames[self.REC_TO_IDLE[1]]
            ),
        )

# ── SaveDialog ─────────────────────────────────────────────────────
class SaveDialog(ctk.CTkToplevel):
    """Modal dialog to rename/tag the just-recorded file."""

    def __init__(self, master, src: Path, duration: int):
        super().__init__(master)
        self.title("Save recording")
        self.transient(master)             # stay on top of master
        self.grab_set()                    # make modal
        self.resizable(False, False)       # fixed size

        self.res = None                    # will hold the result dict
        self.columnconfigure(1, weight=1)

        # --- file info ---
        folder, ext = src.parent, src.suffix.lstrip(".")
        ctk.CTkLabel(self, text="Folder:").grid(row=0, column=0, sticky="e", padx=10, pady=6)
        ctk.CTkLabel(self, text=str(folder), anchor="w")\
            .grid(row=0, column=1, columnspan=2, sticky="w", padx=6)

        # --- file name entry ---
        self.var_file = ctk.StringVar(value=src.name)
        ctk.CTkLabel(self, text="File name:")\
            .grid(row=1, column=0, sticky="e", padx=10, pady=6)
        ctk.CTkEntry(self, textvariable=self.var_file)\
            .grid(row=1, column=1, columnspan=2, sticky="ew", padx=6, pady=6)

        # --- metadata fields ---
        self.var_title  = ctk.StringVar()
        self.var_artist = ctk.StringVar()
        self.var_album  = ctk.StringVar()
        for i, (label, var) in enumerate(
            (("Title", self.var_title),
             ("Artist", self.var_artist),
             ("Album", self.var_album)),
            start=2,
        ):
            ctk.CTkLabel(self, text=f"{label}:")\
                .grid(row=i, column=0, sticky="e", padx=10, pady=4)
            ctk.CTkEntry(self, textvariable=var)\
                .grid(row=i, column=1, columnspan=2, sticky="ew", padx=6, pady=4)

        # --- file summary (duration, size, format) ---
        dur_text = f"{duration//60}:{duration%60:02d}"
        size_text = human_bytes(src.stat().st_size)
        ctk.CTkLabel(
            self,
            text=f"Length: {dur_text}   Size: {size_text}   Format: {ext.upper()}",
            anchor="w"
        ).grid(row=5, column=0, columnspan=3, sticky="w", padx=10, pady=(8, 12))

        # --- Save button ---
        ctk.CTkButton(
            self,
            text="Save",
            fg_color="#1f7b4d",
            command=self._on_ok
        ).grid(row=6, column=0, columnspan=3, pady=(0,12), ipadx=20)

        # remember for later
        self._folder, self._ext = folder, ext

        # now that everything’s laid out, size & center
        self.update_idletasks()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        mx = master.winfo_rootx()
        my = master.winfo_rooty()
        mw = master.winfo_width()
        mh = master.winfo_height()
        x = mx + (mw - w)//2
        y = my + (mh - h)//2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _on_ok(self):
        name = self.var_file.get().strip()
        if not name.endswith(f".{self._ext}"):
            name += f".{self._ext}"
        self.res = {
            "path":  self._folder / name,
            "title":  self.var_title.get().strip(),
            "artist": self.var_artist.get().strip(),
            "album":  self.var_album.get().strip(),
        }
        self.destroy()



# ── VUMeter ─────────────────────────────────────────────────────────
class VUMeter(ctk.CTkCanvas):
    DB_MIN, DB_MAX = -60, 0
    NUM_W, T_MAJ, T_MIN = 24, 20, 12
    PAD_X, PAD_Y = 10, 8
    BAR_W, GAP = 28, 10
    PEAK_HOLD = 2.0
    WIDTH = PAD_X * 2 + NUM_W * 2 + T_MAJ * 2 + BAR_W * 2 + GAP

    def __init__(self, master, **kw):
        super().__init__(
            master, width=self.WIDTH, bg="#202020", highlightthickness=0, **kw
        )
        x = self.PAD_X
        self.x_numL = x + self.NUM_W
        self.x_tickL = self.x_numL + 2
        self.x_barL0 = self.x_tickL + self.T_MAJ
        self.x_barL1 = self.x_barL0 + self.BAR_W
        self.x_barR0 = self.x_barL1 + self.GAP
        self.x_barR1 = self.x_barR0 + self.BAR_W
        self.x_tickR = self.x_barR1
        self.x_numR = self.x_tickR + self.T_MAJ + 2
        self._bars_ready = False
        self._peakL = self._peakR = self.DB_MIN
        self._last_update = 0
        self.bind("<Configure>", self._on_resize)

    def _y(self, db: float) -> int:
        h = self.winfo_height()
        span = h - 2 * self.PAD_Y
        db = max(min(db, self.DB_MAX), self.DB_MIN)
        return int(
            h - self.PAD_Y - (db - self.DB_MIN) / (self.DB_MAX - self.DB_MIN) * span
        )

    def _draw_ticks(self):
        self.delete("tick")
        for db in range(self.DB_MIN, self.DB_MAX + 1):
            y = self._y(db)
            major = db % 6 == 0
            ln = self.T_MAJ if major else self.T_MIN
            self.create_line(
                self.x_tickL, y, self.x_tickL + ln, y, fill="#444", tags="tick"
            )
            self.create_line(
                self.x_tickR + self.T_MAJ - ln,
                y,
                self.x_tickR + self.T_MAJ,
                y,
                fill="#444",
                tags="tick",
            )
            if major:
                col = "#fff" if db == 0 else "#888"
                self.create_text(
                    self.x_numL - 2,
                    y,
                    text=f"{db}",
                    anchor="e",
                    fill=col,
                    font=("Segoe UI", 8),
                    tags="tick",
                )
                self.create_text(
                    self.x_numR + 2,
                    y,
                    text=f"{db}",
                    anchor="w",
                    fill=col,
                    font=("Segoe UI", 8),
                    tags="tick",
                )

    def _make_bars(self):
        h = self.winfo_height()
        self.l_rms = self.create_rectangle(
            self.x_barL0,
            h - self.PAD_Y,
            self.x_barL1,
            h - self.PAD_Y,
            fill="#00e676",
            width=0,
        )
        self.r_rms = self.create_rectangle(
            self.x_barR0,
            h - self.PAD_Y,
            self.x_barR1,
            h - self.PAD_Y,
            fill="#00e676",
            width=0,
        )
        self.l_peak = self.create_rectangle(
            self.x_barL0 + 6,
            h - self.PAD_Y,
            self.x_barL1 - 6,
            h - self.PAD_Y,
            fill="#d50000",
            width=0,
        )
        self.r_peak = self.create_rectangle(
            self.x_barR0 + 6,
            h - self.PAD_Y,
            self.x_barR1 - 6,
            h - self.PAD_Y,
            fill="#d50000",
            width=0,
        )
        self.l_hold = self.create_line(
            self.x_barL0,
            h - self.PAD_Y,
            self.x_barL1,
            h - self.PAD_Y,
            fill="white",
            width=2,
        )
        self.r_hold = self.create_line(
            self.x_barR0,
            h - self.PAD_Y,
            self.x_barR1,
            h - self.PAD_Y,
            fill="white",
            width=2,
        )
        self._bars_ready = True

    def _on_resize(self, _=None) -> None:
        self._draw_ticks()
        if not self._bars_ready:
            self._make_bars()
            return
        h = self.winfo_height()
        # only reposition bars if coords() returned a valid 4-tuple
        for item in (self.l_rms, self.r_rms, self.l_peak, self.r_peak):
            coords = self.coords(item)
            if not coords or len(coords) != 4:
                continue
            x0, _, x1, _ = coords
            self.coords(item, x0, h - self.PAD_Y, x1, h - self.PAD_Y)

        for line in (self.l_hold, self.r_hold):
            coords = self.coords(line)
            if not coords or len(coords) != 4:
                continue
            x0, _, x1, _ = coords
            self.coords(line, x0, h - self.PAD_Y, x1, h - self.PAD_Y)


    def update(self, rmsL, pkL, rmsR, pkR, now):
        if not self._bars_ready:
            return
        h = self.winfo_height()
        c = lambda db: "#d50000" if db > -6 else "#00e676"
        self.coords(
            self.l_rms, self.x_barL0, self._y(rmsL), self.x_barL1, h - self.PAD_Y
        )
        self.itemconfig(self.l_rms, fill=c(rmsL))
        ypk = self._y(pkL)
        self.coords(self.l_peak, self.x_barL0 + 6, ypk, self.x_barL1 - 6, ypk + 2)
        self.coords(
            self.r_rms, self.x_barR0, self._y(rmsR), self.x_barR1, h - self.PAD_Y
        )
        self.itemconfig(self.r_rms, fill=c(rmsR))
        ypk2 = self._y(pkR)
        self.coords(self.r_peak, self.x_barR0 + 6, ypk2, self.x_barR1 - 6, ypk2 + 2)
        self._peak_hold("L", pkL, now)
        self._peak_hold("R", pkR, now)

    def _peak_hold(self, ch, pk, now):
        attr = "_peakL" if ch == "L" else "_peakR"
        line = self.l_hold if ch == "L" else self.r_hold
        hold = getattr(self, attr)
        if pk > hold or now - self._last_update > self.PEAK_HOLD:
            setattr(self, attr, pk)
            self._last_update = now
        y = self._y(getattr(self, attr))
        self.coords(
            line,
            self.x_barL0 if ch == "L" else self.x_barR0,
            y,
            self.x_barL1 if ch == "L" else self.x_barR1,
            y,
        )


# ── Live dB Chart ──────────────────────────────────────────────────
class DBChart(ctk.CTkFrame):
    def __init__(self, master, length: int = 200, **kw):
        super().__init__(master, **kw)

        # buffer is twice as long → slower scroll
        self.data = deque([-60.0] * length, maxlen=length)

        # create a dark-themed Matplotlib figure
        self.fig = Figure(figsize=(2, 1), dpi=100, facecolor=GIF_BG)
        self.ax = self.fig.add_subplot(111, facecolor=GIF_BG)

        # set view limits for a dB scale
        self.ax.set_xlim(0, length)
        self.ax.set_ylim(-60, 0)

        # show only y-axis labels
        # choose ticks every 10 dB
        self.ax.set_yticks([-60, -50, -40, -30, -20, -10, 0])
        self.ax.tick_params(
            axis="y",
            colors="#888",      # tick label color
            labelsize=8,
            left=True,
            right=False,
            length=4,
        )
        # hide x-axis ticks
        self.ax.tick_params(axis="x", which="both", length=0, labelbottom=False)

        # draw a subtle grid
        self.ax.grid(
            True,
            axis="y",
            color="#444",
            linestyle="--",
            linewidth=0.5,
            alpha=0.7
        )

        # line + soft fill
        (self.line,) = self.ax.plot([], [], lw=2, color="#80DEEA")
        # we will update the fill in update()

        # embed in CTk
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    def update(self, new_db: float):
        # clamp & append
        self.data.append(max(-60.0, min(0.0, new_db)))
        y = list(self.data)
        x = list(range(len(y)))

        # update line
        self.line.set_data(x, y)

        # clear and redraw fill
        # remove old collections
        for coll in list(self.ax.collections):
            coll.remove()
        self.ax.fill_between(x, y, -60, color="#80DEEA", alpha=0.2)

        # redraw
        self.canvas.draw_idle()


# ── Context Menu ───────────────────────────────────────────────────
class ContextMenu(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.withdraw()
        self.overrideredirect(True)
        self.transient(master)
        self.configure(fg_color="#2b2b2b")
        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.pack(fill="both", expand=True)
        self.bind("<FocusOut>", lambda e: self.withdraw())
        self.container.bind("<FocusOut>", lambda e: self.withdraw())
        self._items = []

    def add_command(self, label, icon, cmd):
        self._items.append(("cmd", label, icon, cmd))

    def add_separator(self):
        self._items.append(("sep",))

    def build(self):
        for w in self.container.winfo_children():
            w.destroy()
        for i in self._items:
            if i[0] == "sep":
                sep = ctk.CTkFrame(self.container, fg_color="#444", height=1)
                sep.pack(fill="x", padx=8, pady=4)
            else:
                _, lab, ic, cmd = i
                btn = ctk.CTkButton(
                    self.container,
                    text=lab,
                    image=ic,
                    compound="left",
                    fg_color="transparent",
                    hover_color="#333",
                    text_color="#ddd",
                    anchor="w",
                    corner_radius=0,
                    height=24,
                    command=lambda c=cmd: (self.withdraw(), c()),
                )
                btn.pack(fill="x", padx=4, pady=2)

    def show(self, x, y):
        self.build()
        self.geometry(f"+{x}+{y}")
        self.deiconify()
        self.focus_force()


# ── RecordingTable ─────────────────────────────────────────────────
class RecordingTable(ctk.CTkFrame):
    COLS = ("FILE", "WHEN", "LENGTH", "SIZE")
    ROW_COLORS = ("#1a1a1a", "#272727")

    def __init__(self, master, folder: Path, **kw):
        super().__init__(
            master,
            fg_color="transparent",
            corner_radius=6,
            border_width=1,
            border_color="#333",
            **kw,
        )
        self.folder = folder
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "CTk.Treeview",
            background=self.ROW_COLORS[0],
            fieldbackground=self.ROW_COLORS[0],
            foreground="#ddd",
            rowheight=24,
            font=("Segoe UI", 10),
            bordercolor="#333",
            borderwidth=0,
        )
        style.map("CTk.Treeview", background=[("selected", "#333")])
        style.configure(
            "CTk.Treeview.Heading",
            background="#2b2b2b",
            foreground="#eee",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            bordercolor="#333",
        )
        style.map("CTk.Treeview.Heading", background=[("active", "#2b2b2b")])
        cont = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        cont.pack(fill="both", expand=True, padx=4, pady=4)
        cont.grid_rowconfigure(0, weight=1)
        cont.grid_columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            cont,
            columns=self.COLS,
            show="headings",
            style="CTk.Treeview",
            selectmode="browse",
        )
        for c in self.COLS:
            a = "w" if c != "SIZE" else "e"
            self.tree.heading(c, text=c, anchor=a)
            self.tree.column(c, anchor=a, stretch=True)
        vsb = ctk.CTkScrollbar(cont, orientation="vertical", command=self.tree.yview)
        vsb.grid(row=0, column=1, sticky="ns", padx=(0, 4))
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ads = Path(__file__).with_name("assets")
        self._icons = {}
        for n in ("play", "rename", "delete"):
            im = Image.open(ads / f"{n}.png").resize((20, 20), Image.LANCZOS)
            self._icons[n] = ctk.CTkImage(light_image=im, dark_image=im)
        self.menu = ContextMenu(self)
        self.menu.add_command("Play", self._icons["play"], self._play_selected)
        self.menu.add_command("Rename", self._icons["rename"], self._rename_selected)
        self.menu.add_separator()
        self.menu.add_command("Delete", self._icons["delete"], self._delete_selected)
        self.refresh()
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<Button-3>", self._show_context_menu)

    def _on_double_click(self, _):
        p = self._get_selected_path()
        p and open_in_explorer(p)

    def _show_context_menu(self, e):
        row = self.tree.identify_row(e.y)
        if not row:
            return
        self.tree.focus(row)
        self.tree.selection_set(row)
        self.menu.show(e.x_root, e.y_root)

    def _get_selected_path(self) -> Optional[Path]:
        it = self.tree.focus()
        if not it:
            return None
        fn = self.tree.item(it, "values")[0]
        return self.folder / fn

    def _play_selected(self):
        p = self._get_selected_path()
        if not p or not p.exists():
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(p))
            elif sys.platform == "darwin":
                subprocess.call(["open", str(p)])
            else:
                subprocess.call(["xdg-open", str(p)])
        except:
            pass

    def _rename_selected(self):
        p = self._get_selected_path()
        if not p or not p.exists():
            return
        dur = 0
        try:
            dur = int(len(sf.SoundFile(p)) / sf.SoundFile(p).samplerate)
        except:
            pass
        dlg = SaveDialog(self.master, p, dur)
        dlg.wait_window()
        if dlg.res:
            new = dlg.res["path"]
            try:
                os.replace(str(p), str(new))
                self.folder = new.parent
                self.refresh()
            except:
                pass

    def _delete_selected(self):
        p = self._get_selected_path()
        if not p or not p.exists():
            return
        if messagebox.askyesno("Delete", f"Delete {p.name}?"):
            try:
                os.remove(p)
                self.refresh()
            except:
                pass

    def refresh(self):
        for r in self.tree.get_children():
            self.tree.delete(r)
        files = sorted(
            self.folder.glob("*.*"), key=lambda p: p.stat().st_mtime, reverse=True
        )[:20]
        for i, p in enumerate(files):
            st = p.stat()
            when = dt.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
            try:
                f = sf.SoundFile(p)
                sec = int(len(f) / f.samplerate)
                dur = f"{sec//60}:{sec%60:02d}"
            except:
                dur = "--:--"
            size = human_bytes(st.st_size)
            tag = "even" if i % 2 == 0 else "odd"
            self.tree.insert("", "end", values=(p.name, when, dur, size), tags=(tag,))
        self.tree.tag_configure("even", background=self.ROW_COLORS[0])
        self.tree.tag_configure("odd", background=self.ROW_COLORS[1])


# ── Main App ────────────────────────────────────────────────────────
class App(ctk.CTk):
    PREF = Path.home() / ".looprec.json"

    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        self.title("Loopback Recorder")
        w, h = 1040, 660
        self.geometry(f"{w}x{h}")
        self.minsize(920, 560)
        self.configure(fg_color=GIF_BG)
        self.after_idle(lambda: self._center_window(w, h))
        self.prefs = self._load_prefs()
        self.settings = Settings(self, self._save_prefs, self.prefs)
        self.about = AboutDialog(self)
        self.rec = None
        self.started = None
        self._build_ui()
        self.after(40, self._tick)
        self.bind("<space>", lambda e: self._toggle())
        self.bind("<Control-s>", lambda e: self.settings.toggle())
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _center_window(self, w, h):
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x, y = (sw - w) // 2, (sh - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _info_label(self, master, text="–", header=False, row=0, pady=(2, 2)):
        fg = "#EEEEEE" if header else "#BBBBBB"
        font = ("Segoe UI", 13, "bold") if header else ("Segoe UI", 12)
        lab = ctk.CTkLabel(master, text=text, anchor="w", font=font, text_color=fg)
        lab.grid(row=row, column=0, sticky="w", columnspan=2, padx=10, pady=pady)
        return lab

    def _info_row(self, master, key, var, row):
        kc, vc = "#BBBBBB", "#80DEEA"
        ctk.CTkLabel(
            master, text=key, anchor="w", font=("Segoe UI", 12), text_color=kc
        ).grid(row=row, column=0, sticky="w", padx=(10, 4), pady=(2, 2))
        ctk.CTkLabel(
            master,
            textvariable=var,
            anchor="w",
            font=("Segoe UI", 12, "bold"),
            text_color=vc,
        ).grid(row=row, column=1, sticky="w", padx=(0, 10), pady=(2, 2))

    def _build_ui(self):
        # top‐level container
        root = ctk.CTkFrame(self, fg_color=GIF_BG, corner_radius=0)
        root.pack(fill="both", expand=True)
        root.grid_columnconfigure(1, weight=1)
        root.grid_rowconfigure(0, weight=1)

        # left rail (VU meter)
        rail = ctk.CTkFrame(root, fg_color="#181818", width=140, corner_radius=0)
        rail.grid(row=0, column=0, sticky="nsew")
        rail.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(
            rail, text="LEVEL", text_color="#888", font=("Segoe UI", 12, "bold")
        ).grid(row=0, column=0, pady=(16, 6))
        self.vu = VUMeter(rail)
        self.vu.grid(row=1, column=0, sticky="nsew")

        # right panel
        right = ctk.CTkFrame(root, fg_color=GIF_BG, corner_radius=0)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(2, weight=0)
        right.grid_rowconfigure(3, weight=1)
        right.grid_columnconfigure(0, weight=1)
        right.grid_columnconfigure(1, weight=1)

        # header
        hdr = ctk.CTkFrame(right, fg_color="#1c1c1c", height=46, corner_radius=0)
        hdr.grid(row=0, column=0, columnspan=2, sticky="ew")
        hdr.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(hdr, text="Loopback Recorder", font=("Segoe UI", 15, "bold")).grid(
            row=0, column=0, padx=14
        )
        self.lab_device = ctk.CTkLabel(hdr, text="", anchor="e")
        self.lab_device.grid(row=0, column=1, sticky="e", padx=6)
        ctk.CTkButton(
            hdr,
            image=icon("settings.png", 20),
            text="",
            fg_color="transparent",
            hover_color="#333",
            width=30,
            command=lambda: self.settings.toggle(),
        ).grid(row=0, column=2, padx=(8, 4))
        ctk.CTkButton(
            hdr,
            image=icon("about.png", 20),
            text="",
            fg_color="transparent",
            hover_color="#333",
            width=30,
            command=lambda: self.about.toggle(),
        ).grid(row=0, column=3, padx=(0, 8))

        # status bar
        status = ctk.CTkFrame(right, fg_color=GIF_BG)
        status.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(28, 8))
        status.grid_columnconfigure(0, weight=0)
        status.grid_columnconfigure(1, weight=1)
        status.grid_columnconfigure(2, weight=0)
        self.var_stat = ctk.StringVar(value="IDLE")
        self.lbl_stat = ctk.CTkLabel(
            status,
            textvariable=self.var_stat,
            font=("Segoe UI", 16, "bold"),
            text_color="#bbb",
        )
        self.lbl_stat.grid(row=0, column=0, sticky="w")
        self.var_time = ctk.StringVar(value="00:00:00:00")
        ctk.CTkLabel(status, textvariable=self.var_time, font=("Consolas", 28)).grid(
            row=0, column=1
        )
        self.btn = RecordButton(status, command=self._toggle)
        self.btn.grid(row=0, column=2, padx=(0, 4))

        # Session Info + dB Chart
        info = ctk.CTkFrame(right, corner_radius=6)
        info.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self._info_label(info, "Session Info", header=True, row=0, pady=(14, 6))
        self.var_sr = tk.StringVar(value="–")
        self.var_ch = tk.StringVar(value="–")
        self.var_fmt = tk.StringVar(value="–")
        self.var_split = tk.StringVar(value="–")
        self.var_sil = tk.StringVar(value="–")
        self.var_space = tk.StringVar(value="–")
        self._info_row(info, "Samplerate:", self.var_sr, row=1)
        self._info_row(info, "Channels:", self.var_ch, row=2)
        self._info_row(info, "Format:", self.var_fmt, row=3)
        self._info_row(info, "Split every:", self.var_split, row=4)
        self._info_row(info, "Silence detect:", self.var_sil, row=5)
        self._info_row(info, "Free disk:", self.var_space, row=6)

        self.db_chart = DBChart(right, fg_color=GIF_BG, corner_radius=6)
        self.db_chart.grid(row=2, column=1, sticky="nsew", padx=(0, 12), pady=(0, 12))

        # recordings table
        self.table = RecordingTable(right, folder=Path(self.settings.dir()))
        self.table.grid(
            row=3, column=0, columnspan=2, sticky="nsew", padx=12, pady=(0, 12)
        )

        self._update_info()

    def _toggle(self):
        if self.rec and self.rec.is_running():
            self._stop()
        else:
            self._start()

    def _start(self):
        if self.settings.fmt() == "mp3" and AudioSegment is None:
            self.lbl_stat.configure(text_color="#ff9c00")
            self.var_stat.set("NO MP3")
            return
        dev_idx = self.settings.dev_idx()
        d = sd.query_devices(dev_idx, "input")
        sr = int(d["default_samplerate"])
        ch = d["max_input_channels"]
        try:
            self.rec = Recorder(
                dev_idx,
                sr,
                ch,
                Path(self.settings.dir()),
                self.settings.base(),
                self.settings.fmt(),
                self.settings.split_secs(),
                self.settings.sdb(),
                self.settings.slen(),
                self.settings.gate(),
            )
            self.rec.start()
        except Exception as e:
            log.exception(e)
            self.lbl_stat.configure(text_color="#ff4c4d")
            self.var_stat.set("ERROR")
            return
        self.started = dt.datetime.now()
        self.var_stat.set("REC")
        self.lbl_stat.configure(text_color="#d32f2f")
        self.btn.set_recording()
        self._update_info()

    def _stop(self):
        if not self.rec:
            return

        # stop recording
        self.rec.stop()
        self.btn.set_idle()

        # find the just‐written file
        pattern = f"{self.rec.base}_{self.rec._stamp()}_*.{self.rec.fmt}"
        files = list(self.rec.out.glob(pattern))

        if len(files) == 1:
            orig = files[0]
            duration = int((dt.datetime.now() - self.rec._ts).total_seconds())

            # show save dialog
            dlg = SaveDialog(self, orig, duration)
            dlg.wait_window()

            if dlg.res:
                new_path = dlg.res["path"]
                os.replace(str(orig), str(new_path))

                # write metadata tags
                tags = {
                    "title":  dlg.res["title"] or new_path.stem,
                    "artist": dlg.res["artist"],
                    "album":  dlg.res["album"],
                }
                ext = new_path.suffix.lower().lstrip(".")
                try:
                    if ext == "flac":
                        audio = FLAC(str(new_path))
                        audio.update(tags)
                        audio.save()
                    elif ext == "wav":
                        audio = WAVE(str(new_path))
                        audio["INAM"] = tags["title"]
                        audio["IART"] = tags["artist"]
                        audio["IPRD"] = tags["album"]
                        audio.save()
                    elif ext == "mp3":
                        audio = EasyID3(str(new_path))
                        audio.update(tags)
                        audio.save()
                except Exception as e:
                    log.warning("Metadata failed: %s", e)

                # apply boost via pydub if available
                if AudioSegment:
                    try:
                        seg = AudioSegment.from_file(str(new_path))
                        boosted = seg.apply_gain(+20.0)  # use your desired gain here
                        boosted.export(str(new_path), format=ext)
                    except Exception as e:
                        log.warning("Post-gain export failed: %s", e)

        # reset state & UI
        self.rec = None
        self.started = None
        self.table.refresh()
        self.var_stat.set("IDLE")
        self.lbl_stat.configure(text_color="#bbb")
        self.var_time.set("00:00:00:00")
        self.vu.update(-60, -60, -60, -60, dt.datetime.now().timestamp())
        self._update_info()


    def _tick(self):
        if self.rec and self.rec.is_running():
            try:
                while True:
                    rmsL, pkL, rmsR, pkR, ts = self.rec.level_q.get_nowait()
                    self.vu.update(rmsL, pkL, rmsR, pkR, ts)
                    self.db_chart.update(max(pkL, pkR))
            except queue.Empty:
                pass
            if self.started:
                total = (dt.datetime.now() - self.started).total_seconds()
                h = int(total // 3600)
                m = int((total % 3600) // 60)
                s = int(total % 60)
                cs = int((total - int(total)) * 100)
                self.var_time.set(f"{h:02d}:{m:02d}:{s:02d}:{cs:02d}")
        if (
            not hasattr(self, "_last_space")
            or (dt.datetime.now() - self._last_space).seconds >= 1
        ):
            free = shutil.disk_usage(self.settings.dir()).free
            self.var_space.set(human_bytes(free))
            self._last_space = dt.datetime.now()
        self.after(40, self._tick)

    def _update_info(self):
        dev_name = next(
            name
            for name, idx in self.settings._map.items()
            if idx == self.settings.dev_idx()
        )
        self.lab_device.configure(text=f"  {dev_name}")
        if self.rec and self.rec.is_running():
            self.var_sr.set(f"{self.rec.sr} Hz")
            self.var_ch.set(f"{self.rec.ch}")
            self.var_fmt.set(self.rec.fmt.upper())
        else:
            self.var_sr.set("–")
            self.var_ch.set("–")
            self.var_fmt.set(self.settings.fmt().upper())
        sp = self.settings.split_secs()
        self.var_split.set(f"{sp//60} min" if sp else "off")
        if self.settings.sdb() is not None:
            self.var_sil.set(
                f"< {self.settings.sdb():.0f} dB / {self.settings.slen():.1f}s"
            )
        else:
            self.var_sil.set("off")
        free = shutil.disk_usage(self.settings.dir()).free
        self.var_space.set(human_bytes(free))

    def _save_prefs(self):
        self.PREF.write_text(json.dumps(self.settings.dump(), indent=2))
        self.table.folder = Path(self.settings.dir())
        self.table.refresh()
        self._update_info()

    def _load_prefs(self):
        try:
            return json.loads(self.PREF.read_text())
        except:
            return {}

    def _on_close(self):
        self.btn.set_idle()
        if self.rec and self.rec.is_running():
            self.rec.stop()
        self.destroy()


if __name__ == "__main__":
    try:
        App().mainloop()
    except KeyboardInterrupt:
        pass
