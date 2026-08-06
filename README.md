# 🎵 MusTerm - Terminal Music Player & Live Synced Lyrics TUI

**MusTerm** is an ultra-fast, lightweight, and modern terminal music player built with a custom-designed **256-Color TUI (Text User Interface)** featuring a **Live Synced Lyrics Engine (Karaoke Mode)** and dynamic audio spectrum visualizer.

Designed for **Termux (Android)**, **Linux (Debian, Arch, Ubuntu, Fedora, Alpine)**, **macOS**, and **WSL**.

---

> [!NOTE]
> MusTerm is designed as a standalone single-command application (`musterm`). It requires no python third-party library dependencies (pip-free) and runs out of the box using pure Python, `mpv`, and `yt-dlp`.

---

## 📽️ Video Review & Interactive Demonstration

![Video Demo Review](data/review.mp4)

---

## 📸 Interface Preview & Screenshots

````carousel
![Live Synced Lyrics Karaoke Mode](data/tab_lyrics.jpg)
<!-- slide -->
![Dynamic Audio Spectrum Visualizer](data/tab_visualizer.jpg)
<!-- slide -->
![24/7 Live Radio Streams](data/tab_radio.jpg)
<!-- slide -->
![Playback History Log](data/tab_history.jpg)
<!-- slide -->
![Keyboard Controls & Help Manual](data/tab_help.jpg)
````

---

## ✨ Features

- 🎤 **Live Synced Lyrics (Karaoke Mode)**: Auto-fetches synchronized LRC lyrics via the LRCLIB database. Displays the current active singing line in glowing Debian Red, auto-scrolls in sync with playback time, and shows live mini lyrics on any tab.
- 🎨 **Kali & Debian Hybrid Theme**: Custom-built ANSI 256-Color UI blending Kali Electric Blue borders with Debian Crimson Red accents.
- 🎛️ **Music-Synced Spectrum Visualizer**: Dynamic vertical audio equalizer bars pulsing to the exact tempo and frequency bands of playing audio.
- 📻 **24/7 Live Radio Streams**: Pre-loaded Lo-Fi Girl, Synthwave, Vaporwave, Cyberpunk Electro, and City Pop streams with instant 1-click playback.
- ⚡ **Ultra-Fast Stream Extraction**: Pre-resolves YouTube direct stream URLs via `yt-dlp` in background threads for instant (<1s) playback without player buffering stalls.
- 📜 **Playback History**: Automatic timestamped history log saved to `~/.config/musterm/history.log`.

---

## 🚀 Installation & Usage

### Launch Application
MusTerm is automatically linked to your system `$PREFIX/bin` (or `PATH`). You can type `musterm` from **any directory** in your terminal:
```bash
musterm
```

### Dependency Repair & PATH Check
To inspect or repair system dependencies (`python3`, `mpv`, `yt-dlp`) and system PATH setup:
```bash
musterm --check
```

---

> [!TIP]
> MusTerm auto-detects your system package manager (`pkg`, `apt`, `brew`, `pacman`, `dnf`, `apk`, `xbps`) and will install missing binaries automatically on first launch!

---

## ⌨️ Keyboard Shortcuts & Navigation

| Category | Key | Action |
| --- | --- | --- |
| **Navigation** | `1` - `6` or `Tab` | Switch Tabs (`Search`, `Radio`, `History`, `Lyrics`, `Visualizer`, `Help`) |
| **Lyrics** | `l` | Jump directly to Live Synced Lyrics tab |
| **Lyrics** | `r` | Re-fetch / Refresh lyrics for currently playing song |
| **Search** | `s` or `/` | Activate Live Search Input Box |
| **Search** | `c` | Clear search query & type new title |
| **Search Mode** | `Tab` / `Esc` / `↓` | Exit search edit mode & return to list navigation |
| **List Scroll** | `↑` / `↓` or `k` / `j` | Navigate tracks & scroll lyrics |
| **Playback** | `Enter` | Submit Search / Play selected item |
| **Playback** | `Space` | Toggle Pause / Resume |
| **Volume** | `+` / `-` | Increase / Decrease volume |
| **Seeking** | `←` / `→` | Seek backward / forward 10 seconds |
| **App** | `q` or `Esc` | Quit MusTerm TUI Application |

---

## 📁 File Structure

| File | Description |
| --- | --- |
| [musterm.py](musterm.py) | Full Curses TUI Engine, Audio Spectrum Visualizer, & Live Lyrics Fetcher |
| [musterm.sh](musterm.sh) | Universal Shell Launcher & Dependency Auto-Installer |
| [musterm](musterm) | Executable Launcher Symlink |
| [data/](data/) | Screenshots & Video Review Assets |

---

> [!IMPORTANT]
> To ensure seamless playback on Termux Android, ensure PulseAudio is active. MusTerm starts PulseAudio automatically on launch if installed.
