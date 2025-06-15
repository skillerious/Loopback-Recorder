from __future__ import annotations

import webbrowser
import customtkinter as ctk
from PIL import Image
from settings import icon as _icon  # we’ll still use your helper to find the file

# color palette
BG        = "#232323"
CARD_BG   = "#2c2c2c"
ACCENT    = "#80DEEA"
TEXT_MAIN = "#E0E0E0"
TEXT_SUB  = "#A0A0A0"
DIVIDER   = "#3a3a3a"
BULLET    = "#FF7043"
BTN_TEXT  = "#222222"

class AboutDialog(ctk.CTkToplevel):
    """
    Polished About dialog for Loopback Recorder.
    """
    def __init__(self, master):
        super().__init__(master)

        # setup
        self.withdraw()
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self.withdraw)
        self.title("About Loopback Recorder")
        self.resizable(False, False)
        self.configure(fg_color=BG)

        # fixed window size
        win_w, win_h = 620, 580
        self.geometry(f"{win_w}x{win_h}")
        self.minsize(win_w, win_h)

        # — Card container —
        card_w, card_h = int(win_w * 0.9), int(win_h * 0.9)
        card = ctk.CTkFrame(
            self,
            fg_color=CARD_BG,
            corner_radius=12,
            border_width=1,
            border_color=DIVIDER,
            width=card_w,
            height=card_h
        )
        card.place(relx=0.5, rely=0.5, anchor="center")

        # — Floating header —
        hdr_w, hdr_h = 300, 120
        hdr = ctk.CTkFrame(
            card,
            fg_color=BG,
            corner_radius=8,
            border_width=1,
            border_color=DIVIDER,
            width=hdr_w,
            height=hdr_h
        )
        hdr.place(relx=0.5, y=16, anchor="n")

        # header icon + title
        # load original PNG and force 96×96
        fp = _icon.__globals__['ASSETS'] / "record.png"
        pil = Image.open(fp).resize((96, 96), Image.LANCZOS)
        app_icon = ctk.CTkImage(light_image=pil, dark_image=pil, size=(96, 96))
        ctk.CTkLabel(hdr, image=app_icon, text="").place(x=16, rely=0.5, anchor="w")

        ctk.CTkLabel(
            hdr,
            text="Loopback\nRecorder",
            justify="left",
            font=("Segoe UI", 18, "bold"),
            text_color=ACCENT
        ).place(x=128, rely=0.5, anchor="w")

        # — Body —
        body_h = int(card_h * 0.6)
        body = ctk.CTkFrame(
            card,
            fg_color="transparent",
            width=int(card_w * 0.9),
            height=body_h
        )
        body.place(relx=0.5, rely=0.27, anchor="n")

        # version
        ctk.CTkLabel(
            body,
            text="Version 1.0.0 (2025-06-15)",
            font=("Segoe UI", 10),
            text_color=TEXT_SUB
        ).pack(pady=(4, 12))

        # description
        desc = (
            "Loopback Recorder is an open-source desktop application that "
            "captures exactly what you hear. From quick audio grabs to long-form "
            "loop-back sessions, it’s designed for simplicity and power."
        )
        ctk.CTkLabel(
            body,
            text=desc,
            font=("Segoe UI", 11),
            wraplength=int(card_w * 0.8),
            justify="left",
            text_color=TEXT_MAIN
        ).pack(pady=(0, 16))

        # divider
        ctk.CTkFrame(body, fg_color=DIVIDER, height=1).pack(
            fill="x", padx=24, pady=8
        )

        # feature bullets
        features = [
            "Loop-back capture of any system audio",
            "Export to WAV • FLAC • MP3 with metadata",
            "Silence detection & automatic splitting",
            "Real-time VU meter & dB chart",
            "Optional post-gain boost via pydub"
        ]
        for feat in features:
            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x", padx=40, pady=4)
            ctk.CTkLabel(
                row,
                text="●",
                font=("Segoe UI", 12),
                text_color=BULLET
            ).pack(side="left")
            ctk.CTkLabel(
                row,
                text=feat,
                font=("Segoe UI", 11),
                text_color=TEXT_MAIN,
                wraplength=int(card_w * 0.7),
                justify="left"
            ).pack(side="left", padx=8)

        # GitHub link (above Close)
        link = ctk.CTkLabel(
            card,
            text="🔗 View on GitHub",
            font=("Segoe UI", 11, "underline"),
            text_color=ACCENT,
            cursor="hand2"
        )
        link.place(relx=0.5, rely=0.90, anchor="s")
        link.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/skillerious"))
        link.bind("<Return>",  lambda e: webbrowser.open("https://github.com/skillerious"))

        # — Close button at very bottom —
        close_btn = ctk.CTkButton(
            card,
            text="Close",
            width=120,
            height=36,
            fg_color=ACCENT,
            hover_color="#6fb8d6",
            text_color=BTN_TEXT,
            command=self.withdraw
        )
        close_btn.place(relx=0.5, rely=0.97, anchor="s")

        # ESC key also closes
        self.bind("<Escape>", lambda e: self.withdraw())

    def toggle(self):
        """Show or hide without white flash."""
        if self.winfo_viewable():
            self.withdraw()
        else:
            self.update_idletasks()
            self._center(self.master)
            self.deiconify()
            self.lift()
            self.focus_force()

    def _center(self, master):
        """Center this dialog over its master."""
        self.update_idletasks()
        mx, my = master.winfo_rootx(), master.winfo_rooty()
        mw, mh = master.winfo_width(), master.winfo_height()
        w, h = self.winfo_width(), self.winfo_height()
        x = mx + (mw - w)//2
        y = my + (mh - h)//2
        self.geometry(f"{w}x{h}+{x}+{y}")
