from __future__ import annotations

import customtkinter as ctk
import webbrowser
from settings import icon

class AboutDialog(ctk.CTkToplevel):
    """
    Non-blocking About dialog for Loopback Recorder.
    """
    def __init__(self, master):
        super().__init__(master)
        self.title("About Loopback Recorder")
        self.resizable(False, False)
        # keep on top of master but do not grab
        self.transient(master)
        self.withdraw()
        self.protocol("WM_DELETE_WINDOW", self.withdraw)

        # Main container
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(padx=20, pady=20)

        # App icon
        app_icon = icon("record.png", 64)
        if app_icon:
            ctk.CTkLabel(container, image=app_icon, text="").pack()

        # Title and version
        ctk.CTkLabel(
            container,
            text="Loopback Recorder",
            font=("Segoe UI", 18, "bold")
        ).pack(pady=(10, 5))
        ctk.CTkLabel(
            container,
            text="Version 1.0.0 (2025-06-15)",
            font=("Segoe UI", 12)
        ).pack()

        # Author/Copyright
        ctk.CTkLabel(
            container,
            text="© 2025 Robin Doak",
            font=("Segoe UI", 12)
        ).pack(pady=(0, 10))

        # Description
        description = (
            "An open-source desktop application for capturing system audio.\n"
            "Features: loopback recording, WAV/FLAC/MP3 export, metadata tagging,\n"
            "silence detection, split recordings, and real-time monitoring."
        )
        ctk.CTkLabel(
            container,
            text=description,
            font=("Segoe UI", 10),
            justify="center"
        ).pack(pady=(0, 10))

        # GitHub link
        link = ctk.CTkLabel(
            container,
            text="GitHub: github.com/skillerious",
            font=("Segoe UI", 10, "underline"),
            text_color="#80DEEA",
            cursor="hand2"
        )
        link.pack()
        link.bind(
            "<Button-1>",
            lambda e: webbrowser.open("https://github.com/skillerious")
        )

        # Close button
        ctk.CTkButton(
            container,
            text="Close",
            width=80,
            command=self.withdraw
        ).pack(pady=(15, 0))

        # Center over parent initially
        self._center(master)

    def _center(self, master):
        """Center this window over the given master."""
        self.update_idletasks()
        x = master.winfo_rootx() + master.winfo_width() // 2 - self.winfo_width() // 2
        y = master.winfo_rooty() + master.winfo_height() // 2 - self.winfo_height() // 2
        self.geometry(f"+{x}+{y}")

    def toggle(self):
        """Show or hide the dialog without blocking the main app."""
        if self.winfo_viewable():
            self.withdraw()
        else:
            self.deiconify()
            self._center(self.master)
            self.focus_force()
