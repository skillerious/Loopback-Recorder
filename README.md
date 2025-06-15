# Loopback Recorder

![Loopback Recorder Screenshot](https://i.imgur.com/d8omzbd.png)

A powerful, dark‐themed loopback audio recorder built with Python, CustomTkinter, SoundDevice, and SoundFile. Capture system audio (via Stereo Mix/WASAPI loopback), visualize levels in real time, and save recordings with metadata and automatic gain.

---

## Features

- **WASAPI Loopback Recording**  
  Capture your system audio (requires Stereo Mix / "What U Hear" on Windows or loopback-capable devices).

- **Real‑Time VU Meter & dB Chart**  
  - Dual‐channel VU meter showing RMS & peak levels.  
  - Live dB history chart with grid, axis labels, and subtle fill.

- **Flexible File Output**  
  - Save as WAV, FLAC, or MP3 (via pydub).  
  - Automatic splitting at set intervals or silence threshold.  
  - Post‑recording metadata editor (Title, Artist, Album).  
  - Automatic gain boost (+ configurable dB) after saving.

- **Custom File Browser Table**  
  - Dark‑themed, zebra‑striped rows with custom scrollbar.  
  - Context menu: Play, Rename (with metadata/edit dialog), Delete.  
  - Double‑click to open file in system explorer.

- **Settings Dialog**  
  - Modal, centered CTkToplevel with grouped sections: Audio, File, Recording.  
  - Persisted preferences in JSON under home directory.  
  - Options for device selection, format, save directory, naming, split/silence settings, noise gate, and gain increment.  
  - ![Settings Overview](https://i.imgur.com/R5eghU5.png)

- **About Dialog**  
  - Application info, version, author details, and dependencies.

- **Error Handling & Logging**  
  - Robust uncaught exception logging to rotating logs.  
  - Visual feedback for errors (e.g. “NO MP3” when pydub missing).

---

## Installation

### Prerequisites

- **Python 3.9+**  
- **Windows** (for WASAPI loopback)  
- **Dependencies**:  
  ```bash
  pip install customtkinter sounddevice soundfile numpy matplotlib mutagen pillow pydub
  ```

### Enable Stereo Mix

1. **Open Sound Settings**  
   ![Open Sound Settings](https://i.imgur.com/RlBYHBe.png)  
   - Right‑click the speaker icon in the taskbar → **Sound settings**.

2. **Advanced Sound Options**  
   ![Advanced Section](https://i.imgur.com/JaOM4oO.png)  
   - Scroll down to **Advanced sound options** → click **More sound settings**.

3. **Show Disabled Devices**  
   ![Show Disabled Devices](https://i.imgur.com/vqKN2PX.png)  
   - In the **Recording** tab, right‑click blank area → **Show Disabled Devices**.

4. **Enable Stereo Mix**  
   ![Enable Stereo Mix](https://i.imgur.com/4hcKWSo.png)  
   - Right‑click **Stereo Mix** → **Enable**.

5. **Confirm Enabled**  
   ![Stereo Mix Enabled](https://i.imgur.com/GyCyB7z.png)  
   - **Stereo Mix** should now appear as enabled.

6. **Select in App**  
   ![Select Stereo Mix in Settings](https://i.imgur.com/O8GuxrO.png)  
   - Launch Loopback Recorder → **Settings** → **Input Device** → choose “Stereo Mix”.

---

## Quick Start

1. **Run the App**  
   ```bash
   python main.py
   ```
2. **Start/Stop Recording**  
   - Click the large circular button or press **Spacebar**.  
   - Recording status and timer update in real time.

3. **Adjust Settings**  
   - Click ⚙️ in the header or press **Ctrl+S**.  
   - Configure device, format, save path, split interval, silence detection, noise gate, and gain.

4. **Manage Recordings**  
   - Browse the newest 20 files in the table.  
   - Right‑click a row to Play, Rename/Edit Metadata, or Delete.  
   - Double‑click to open the file location.

---

## Customization

- **Gain (dB)**: Adjustable in Settings; defaults to +12 dB post‑save.  
- **Split**: Enter minutes to automatically rotate files.  
- **Silence Detect**: Threshold dB and duration (sec) to auto‑split on silence.

---

## Troubleshooting

- **No Recording**:  
  - Check that **Stereo Mix** is enabled.  
  - Verify the selected input in Settings.

- **MP3 Not Available**:  
  - Ensure **pydub** and **ffmpeg** are installed.  
  - Or switch to WAV/FLAC.

- **High CPU Usage**:  
  - Reduce split frequency.  
  - Close other audio‑intensive apps.

- **Context Menu Blank**:  
  - Ensure `assets/` contains `play.png`, `rename.png`, `delete.png`.  
  - Restart the app to reload icons.

---

## Contributing

1. Fork the repo on GitHub.  
2. Create a feature branch.  
3. Submit a pull request.

---

## License

MIT © Robin Doak - 2025
