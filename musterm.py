#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
==============================================================================
 MUSTERM v3.0 - Kali/Debian Terminal Music Player with Live Synced Lyrics
==============================================================================
"""

import sys
import os
import time
import json
import socket
import threading
import subprocess
import curses
import datetime
import math
import re
import urllib.request
import urllib.parse
from pathlib import Path

if os.environ.get("TERM") not in ["xterm-256color", "tmux-256color", "screen-256color"]:
    os.environ["TERM"] = "xterm-256color"

HOME_DIR = Path.home()
CONFIG_DIR = HOME_DIR / ".config" / "musterm"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

HIST_FILE = CONFIG_DIR / "history.log"
SOCKET_PATH = CONFIG_DIR / "mpv.sock"

RADIO_STATIONS = [
    {"name": "Lofi Girl Radio (24/7 Chill Beats)", "url": "https://play.streamaudio.de/lofi", "genre": "Lo-Fi / Chill"},
    {"name": "Synthwave / Chillwave Retro Stream", "url": "https://stream.synthwave.hu/live", "genre": "Synthwave"},
    {"name": "Nightwave Plaza (Vaporwave)", "url": "https://stream.nightwaveplaza.com/plaza.mp3", "genre": "Vaporwave"},
    {"name": "Cyberpunk Electro Radio", "url": "http://stream.zeno.fm/f3wvbbqmdg8uv", "genre": "Electro"},
    {"name": "Chillhop Cafe Instrumental", "url": "http://stream.zeno.fm/0r0xa792kwzuv", "genre": "Chillhop"},
    {"name": "Anime / J-Pop City Pop Radio", "url": "http://stream.zeno.fm/q9696k91638uv", "genre": "City Pop"},
]


def clean_song_name(raw_title):
    """Aggressively strip YouTube noise from a video title and extract artist/title."""
    t = raw_title
    t = re.sub(r'(?i)\(official\s*(music\s*)?video\)', '', t)
    t = re.sub(r'(?i)\[official\s*(music\s*)?video\]', '', t)
    t = re.sub(r'(?i)\(official\s*(audio|lyric|lyrics)\s*(video)?\)', '', t)
    t = re.sub(r'(?i)\[official\s*(audio|lyric|lyrics)\s*(video)?\]', '', t)
    t = re.sub(r'(?i)\((lyric|lyrics)\s*(video)?\)', '', t)
    t = re.sub(r'(?i)\[(lyric|lyrics)\s*(video)?\]', '', t)
    t = re.sub(r'(?i)\(lirik\s*(video)?\)', '', t)
    t = re.sub(r'(?i)\[lirik\s*(video)?\]', '', t)
    t = re.sub(r'(?i)\((mv|m/v|music video|audio|video|visualizer|animated|live|clip|cover|remix)\)', '', t)
    t = re.sub(r'(?i)\[(mv|m/v|music video|audio|video|visualizer|animated|live|clip|cover|remix)\]', '', t)
    t = re.sub(r'(?i)\b(hd|hq|4k|1080p|720p|full\s*hd)\b', '', t)
    t = re.sub(r'(?i)\b(?:ft|feat)\.?\s+[^(\[]*', '', t)  # remove "ft. Artist Name"
    t = re.sub(r'\|.*', '', t)                  # remove pipe and after
    t = re.sub(r'#\w+', '', t)                  # hashtags
    t = re.sub(r'\s{2,}', ' ', t).strip()

    artist = ''
    title = t
    if ' - ' in t:
        parts = t.split(' - ', 1)
        artist = parts[0].strip()
        title = parts[1].strip()
    elif ' ~ ' in t:
        parts = t.split(' ~ ', 1)
        artist = parts[0].strip()
        title = parts[1].strip()
    return artist, title


def parse_lrc(lrc_text):
    """Parse LRC synced lyrics into [(time_seconds, line_text)]."""
    parsed = []
    for line in lrc_text.strip().split("\n"):
        m = re.match(r"\[(\d+):(\d+(?:\.\d+)?)\]\s*(.*)", line)
        if m:
            mins, secs, txt = m.groups()
            t_sec = float(mins) * 60 + float(secs)
            if txt.strip():
                parsed.append((t_sec, txt.strip()))
    return parsed


def _lrclib_search(query):
    """Single LRCLIB API search attempt. Returns parsed lyrics or []."""
    if not query or not query.strip():
        return []
    url = f"https://lrclib.net/api/search?q={urllib.parse.quote(query.strip())}"
    req = urllib.request.Request(url, headers={"User-Agent": "MusTerm/3.0"})
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data and isinstance(data, list):
                for item in data:
                    if item.get("syncedLyrics"):
                        return parse_lrc(item["syncedLyrics"])
                for item in data:
                    if item.get("plainLyrics"):
                        lines = [l.strip() for l in item["plainLyrics"].split("\n") if l.strip()]
                        return [(i * 4.0, line) for i, line in enumerate(lines)]
    except Exception:
        pass
    return []


def fetch_lrclib_lyrics(title, uploader=""):
    """Multi-strategy lyrics fetch: tries several cleaned query variants."""
    artist_from_title, song_from_title = clean_song_name(title)

    queries = []
    if artist_from_title and song_from_title:
        queries.append(f"{artist_from_title} {song_from_title}")
        queries.append(f"{song_from_title} {artist_from_title}")

    if song_from_title:
        queries.append(song_from_title)

    cleaned_full = f"{artist_from_title} {song_from_title}".strip() if artist_from_title else song_from_title
    if cleaned_full and cleaned_full not in queries:
        queries.append(cleaned_full)

    if uploader and uploader not in ("YouTube", "NA", "Unknown", ""):
        up_clean = re.sub(r'(?i)(vevo|official|music|channel|records|entertainment|topic)\s*$', '', uploader).strip()
        if up_clean and song_from_title:
            q = f"{up_clean} {song_from_title}"
            if q not in queries:
                queries.append(q)

    if title and title not in queries:
        queries.append(title)

    for q in queries:
        result = _lrclib_search(q)
        if result:
            return result

    return []



class MPVController:
    """Manages MPV audio playback process & IPC JSON Socket communication."""
    def __init__(self, socket_path):
        self.socket_path = str(socket_path)
        self.process = None
        self.current_title = "No Track Playing"
        self.current_artist = ""
        self.is_playing = False
        self.is_paused = False
        self.is_loading = False
        self.duration = 0.0
        self.time_pos = 0.0
        self.volume = 100

    def start_mpv(self):
        self.stop()
        if os.path.exists(self.socket_path):
            try:
                os.remove(self.socket_path)
            except OSError:
                pass

        cmd = [
            "mpv",
            "--idle",
            f"--input-ipc-server={self.socket_path}",
            "--no-video",
            "--volume=100"
        ]
        self.process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.3)

    def send_cmd(self, command):
        if not os.path.exists(self.socket_path):
            return None
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(0.15)
            sock.connect(self.socket_path)
            payload = json.dumps({"command": command}) + "\n"
            sock.sendall(payload.encode("utf-8"))
            data = sock.recv(2048)
            sock.close()
            if data:
                res = json.loads(data.decode("utf-8"))
                return res.get("data")
        except Exception:
            return None
        return None

    def play_url(self, url, title="Loading...", artist="", app_ref=None):
        if not self.process or self.process.poll() is not None:
            self.start_mpv()

        self.current_title = title
        self.current_artist = artist
        self.is_playing = True
        self.is_paused = False
        self.is_loading = True
        self.time_pos = 0.0
        self.duration = 0.0

        if app_ref:
            app_ref.fetch_lyrics(title, artist)
            app_ref.current_tab = 3  # Auto-switch to lyrics tab

        def _play_thread():
            try:
                target_url = url
                if "youtube.com" in url or "youtu.be" in url or "ytsearch" in url:
                    cmd = ["yt-dlp", "--quiet", "--no-warnings", "-g", "-f", "ba/b", url]
                    res = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
                    if res.stdout and res.stdout.strip():
                        target_url = res.stdout.strip().split("\n")[0]

                self.send_cmd(["loadfile", target_url, "replace"])
            except Exception:
                self.send_cmd(["loadfile", url, "replace"])
            finally:
                self.is_loading = False

        threading.Thread(target=_play_thread, daemon=True).start()
        self.save_to_history(f"{title} - {artist}" if artist else title)

    def toggle_pause(self):
        if self.is_playing:
            self.send_cmd(["cycle", "pause"])
            self.is_paused = not self.is_paused

    def change_volume(self, delta):
        new_vol = max(0, min(100, self.volume + delta))
        self.send_cmd(["set_property", "volume", new_vol])
        self.volume = new_vol

    def seek(self, seconds):
        if self.is_playing:
            self.send_cmd(["seek", seconds, "relative"])

    def stop(self):
        if self.process:
            self.send_cmd(["quit"])
            try:
                self.process.wait(timeout=0.5)
            except Exception:
                self.process.kill()
            self.process = None
        self.is_playing = False
        self.is_paused = False
        self.current_title = "No Track Playing"

    def update_status(self):
        if not self.is_playing:
            return

        t_pos = self.send_cmd(["get_property", "time-pos"])
        if isinstance(t_pos, (int, float)):
            self.time_pos = float(t_pos)

        dur = self.send_cmd(["get_property", "duration"])
        if isinstance(dur, (int, float)):
            self.duration = float(dur)

        vol = self.send_cmd(["get_property", "volume"])
        if isinstance(vol, (int, float)):
            self.volume = int(vol)

        paused = self.send_cmd(["get_property", "pause"])
        if isinstance(paused, bool):
            self.is_paused = paused

    def save_to_history(self, entry):
        try:
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            with open(HIST_FILE, "a", encoding="utf-8") as f:
                f.write(f"{now_str} | {entry}\n")
        except Exception:
            pass



class MusTermApp:
    """Kali/Debian styled 256-color Curses TUI."""
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.mpv = MPVController(SOCKET_PATH)

        self.current_tab = 0
        self.search_query = ""
        self.search_cursor_pos = 0
        self.is_typing_search = False
        self.search_results = []
        self.search_loading = False
        self.search_status = ""
        self.last_search_query = ""
        self.selected_index = 0
        self.history_items = []
        self.running = True
        self.anim_tick = 0

        self.current_lyrics = []
        self.lyrics_loading = False
        self.lyrics_status = ""
        self.lyrics_title = ""
        self.lyrics_manual_scroll = 0

        self.setup_colors()
        self.load_history()

    def setup_colors(self):
        curses.start_color()
        curses.use_default_colors()
        curses.curs_set(0)
        self.stdscr.nodelay(True)


        curses.init_pair(1, 33, -1)    # Kali Electric Blue (Borders, primary text)
        curses.init_pair(2, 124, -1)   # Debian Crimson Red (Accents, titles)
        curses.init_pair(3, 75, -1)    # Steel Blue (Subtitles, secondary)
        curses.init_pair(4, 252, -1)   # Light Gray (Main text)
        curses.init_pair(5, 245, -1)   # Muted Gray (Inactive items)
        curses.init_pair(6, 196, -1)   # Bright Red (Errors & Warnings)
        curses.init_pair(7, 240, -1)   # Dim Gray (Dividers)
        curses.init_pair(8, 255, -1)   # Pure White (Bright emphasis)

        curses.init_pair(10, 255, 33)  # Active Tab (White on Kali Blue)
        curses.init_pair(11, 255, 25)  # Selector Row (White on Kali Navy)
        curses.init_pair(12, 255, 124) # Active Search Box (White on Debian Crimson)
        curses.init_pair(13, 255, 124) # Playing Badge (White on Debian Red)
        curses.init_pair(14, 232, 172) # Loading/Paused Badge (Black on Amber)
        curses.init_pair(15, 252, 236) # Idle Badge (Gray on Dark)
        curses.init_pair(16, 255, 124) # Active Lyric Line (White on Debian Red)

    def load_history(self):
        if HIST_FILE.exists():
            try:
                with open(HIST_FILE, "r", encoding="utf-8") as f:
                    lines = [l.strip() for l in f.readlines() if l.strip()]
                    self.history_items = list(reversed(lines[-30:]))
            except Exception:
                self.history_items = []

    def fetch_lyrics(self, title, artist=""):
        self.lyrics_loading = True
        self.current_lyrics = []
        self.lyrics_title = title
        self.lyrics_manual_scroll = 0
        self.lyrics_status = ""

        def _lyrics_thread():
            try:
                res = fetch_lrclib_lyrics(title, artist)
                self.current_lyrics = res
                if not res:
                    art, song = clean_song_name(title)
                    self.lyrics_status = f'No lyrics found for "{song}" by "{art}". Press r to retry.'
            except Exception as e:
                self.current_lyrics = []
                self.lyrics_status = f"Lyrics fetch error: {e}"
            finally:
                self.lyrics_loading = False

        threading.Thread(target=_lyrics_thread, daemon=True).start()

    def safe_addstr(self, win, y, x, string, attr=0):
        try:
            max_y, max_x = win.getmaxyx()
            if y < 0 or y >= max_y or x < 0 or x >= max_x:
                return
            avail_len = max_x - x
            if len(string) > avail_len:
                string = string[:avail_len]
            if not string:
                return
            if attr:
                win.addstr(y, x, string, attr)
            else:
                win.addstr(y, x, string)
        except curses.error:
            pass

    def perform_search(self, query):
        q = query.strip()
        if not q:
            return

        self.search_loading = True
        self.search_results = []
        self.last_search_query = q
        self.search_status = f'Searching for "{q}"...'

        def _search_thread():
            try:
                if q.startswith("http://") or q.startswith("https://"):
                    search_target = q
                else:
                    search_target = f"ytsearch10:{q}"

                cmd = [
                    "yt-dlp",
                    "--quiet",
                    "--no-warnings",
                    "--flat-playlist",
                    "--print",
                    "%(title)s||%(uploader)s||%(id)s||%(duration_string)s",
                    search_target
                ]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
                results = []
                if res.stdout:
                    for line in res.stdout.strip().split("\n"):
                        if "||" in line:
                            parts = line.split("||")
                            if len(parts) >= 3 and parts[2].strip():
                                t_title = parts[0] if parts[0] != "NA" else "Unknown Title"
                                t_uploader = parts[1] if parts[1] != "NA" else ""
                                t_id = parts[2].strip()
                                t_dur = parts[3] if len(parts) > 3 and parts[3] != "NA" else "--:--"
                                t_url = t_id if t_id.startswith("http") else f"https://www.youtube.com/watch?v={t_id}"

                                results.append({
                                    "title": t_title,
                                    "uploader": t_uploader,
                                    "id": t_id,
                                    "duration": t_dur,
                                    "url": t_url
                                })
                self.search_results = results
                self.selected_index = 0
                if not results:
                    self.search_status = f'No results for "{q}". Try a different query.'
                else:
                    self.search_status = ""
            except Exception as e:
                self.search_results = []
                self.search_status = f'Search failed: {str(e)}'
            finally:
                self.search_loading = False

        threading.Thread(target=_search_thread, daemon=True).start()


    def draw_box(self, win, y, x, h, w, title="", color=1):
        if h < 2 or w < 2:
            return
        c_blue = curses.color_pair(1)
        c_red = curses.color_pair(2)

        self.safe_addstr(win, y, x, "┌" + "─" * (w - 2) + "┐", c_blue)
        for i in range(1, h - 1):
            self.safe_addstr(win, y + i, x, "│", c_blue)
            self.safe_addstr(win, y + i, x + w - 1, "│", c_red)
        self.safe_addstr(win, y + h - 1, x, "└" + "─" * (w - 2) + "┘", c_red)

        if title:
            self.safe_addstr(win, y, x + 2, f" {title} ", c_red | curses.A_BOLD)

    def draw_header(self, max_y, max_x):
        logo_line1 = "█▀▄▀█ █  █ █▀▀ ▀█▀ █▀▀ █▀█ █▀▄▀█"
        logo_line2 = "█ ▀ █ █▄▄█ ▄██  █  ██▄ █▀▄ █ ▀ █"

        logo_x = max(1, max_x - len(logo_line1) - 2)

        self.safe_addstr(self.stdscr, 0, logo_x, logo_line1, curses.color_pair(1) | curses.A_BOLD)
        if logo_x >= 65:  # Only draw line 2 if screen is wide enough so it doesn't overlap tabs
            self.safe_addstr(self.stdscr, 1, logo_x, logo_line2, curses.color_pair(2) | curses.A_BOLD)

        tabs = [
            " 1:SEARCH ",
            " 2:RADIO ",
            " 3:HISTORY ",
            " 4:LYRICS ",
            " 5:VISUAL ",
            " 6:HELP ",
        ]

        start_x = 1
        for idx, tab in enumerate(tabs):
            if idx == self.current_tab:
                pair_idx = 10 if (idx % 2 == 0) else 12
                self.safe_addstr(self.stdscr, 1, start_x, tab, curses.color_pair(pair_idx) | curses.A_BOLD)
            else:
                pair_idx = 1 if (idx % 2 == 0) else 2
                self.safe_addstr(self.stdscr, 1, start_x, tab, curses.color_pair(pair_idx))
            start_x += len(tab) + 1

        self.safe_addstr(self.stdscr, 2, 0, "─" * max_x, curses.color_pair(7))

    def get_current_lyric_line(self):
        if not self.current_lyrics:
            return ""
        pos = self.mpv.time_pos
        active_line = ""
        for t_sec, text in self.current_lyrics:
            if pos >= t_sec:
                active_line = text
            else:
                break
        return active_line

    def draw_footer_player(self, max_y, max_x):
        footer_y = max_y - 5
        if footer_y < 4:
            return
        self.draw_box(self.stdscr, footer_y, 0, 5, max_x, "NOW PLAYING", 1)

        self.mpv.update_status()

        if getattr(self.mpv, 'is_loading', False):
            status_badge = " STREAMING... "
            status_pair = 14
        elif self.mpv.is_paused:
            status_badge = " || PAUSED "
            status_pair = 14
        elif self.mpv.is_playing:
            status_badge = " >> PLAYING "
            status_pair = 13
        else:
            status_badge = " -- IDLE "
            status_pair = 15

        art_clean, song_clean = clean_song_name(self.mpv.current_title)
        if art_clean and song_clean:
            track_info = f"{art_clean} - {song_clean}"
        else:
            track_info = self.mpv.current_title

        max_title_len = max(10, max_x - 35)
        if len(track_info) > max_title_len:
            track_info = track_info[:max_title_len - 3] + "..."

        self.safe_addstr(self.stdscr, footer_y + 1, 2, status_badge, curses.color_pair(status_pair) | curses.A_BOLD)
        badge_end = 2 + len(status_badge) + 1
        self.safe_addstr(self.stdscr, footer_y + 1, badge_end, track_info, curses.color_pair(8) | curses.A_BOLD)

        dur = self.mpv.duration
        pos = self.mpv.time_pos
        vol = self.mpv.volume

        pos_str = time.strftime("%M:%S", time.gmtime(pos))
        dur_str = time.strftime("%M:%S", time.gmtime(dur)) if dur > 0 else "LIVE"

        progress_w = max(10, max_x - 42)
        if dur > 0:
            pct = min(1.0, pos / dur)
            filled = int(pct * progress_w)
        else:
            filled = (self.anim_tick // 2) % progress_w

        filled_bar = "=" * max(0, filled)
        unfilled_bar = "-" * max(0, progress_w - filled - 1)

        self.safe_addstr(self.stdscr, footer_y + 2, 2, f" {pos_str} [", curses.color_pair(1))
        bar_x = 2 + len(pos_str) + 3
        self.safe_addstr(self.stdscr, footer_y + 2, bar_x, filled_bar, curses.color_pair(1) | curses.A_BOLD)
        self.safe_addstr(self.stdscr, footer_y + 2, bar_x + len(filled_bar), ">", curses.color_pair(2) | curses.A_BOLD)
        self.safe_addstr(self.stdscr, footer_y + 2, bar_x + len(filled_bar) + 1, unfilled_bar, curses.color_pair(7))
        self.safe_addstr(self.stdscr, footer_y + 2, bar_x + progress_w, f"] {dur_str} ", curses.color_pair(2))

        vol_str = f"vol:[{vol}%]"
        self.safe_addstr(self.stdscr, footer_y + 2, max(0, max_x - len(vol_str) - 3), vol_str, curses.color_pair(3))

        current_lyric = self.get_current_lyric_line()
        if current_lyric:
            lyric_disp = f'  "{current_lyric}"'
            if len(lyric_disp) > max_x - 6:
                lyric_disp = lyric_disp[:max_x - 9] + '..."'
            self.safe_addstr(self.stdscr, footer_y + 3, 2, lyric_disp, curses.color_pair(2) | curses.A_BOLD)
        else:
            hint_str = " [space:pause  +/-:vol  arrows:seek  l:lyrics  c:search  q:quit]"
            self.safe_addstr(self.stdscr, footer_y + 3, 2, hint_str, curses.color_pair(7))


    def draw_tab_search(self, max_y, max_x):
        box_h = 3
        box_color = 12 if self.is_typing_search else 1
        box_title = "SEARCH [EDIT MODE | Enter:search, Tab/Esc:exit]" if self.is_typing_search else "SEARCH [s/c:type query | 1-6:tabs | Down:results]"
        self.draw_box(self.stdscr, 3, 1, box_h, max_x - 2, box_title, box_color)

        prompt = " > "
        self.safe_addstr(self.stdscr, 4, 3, prompt, curses.color_pair(1) | curses.A_BOLD)
        self.safe_addstr(self.stdscr, 4, 3 + len(prompt), self.search_query, curses.color_pair(8) | curses.A_BOLD)

        if self.is_typing_search:
            try:
                self.stdscr.move(4, min(max_x - 2, 3 + len(prompt) + self.search_cursor_pos))
                curses.curs_set(1)
            except Exception:
                pass
        else:
            try:
                curses.curs_set(0)
            except Exception:
                pass

        res_y = 6
        res_h = max_y - res_y - 5
        if res_h < 2:
            return
        self.draw_box(self.stdscr, res_y, 1, res_h, max_x - 2, "RESULTS (Enter: play)", 3)

        if self.search_loading:
            spinner = ["|", "/", "-", "\\"][self.anim_tick % 4]
            self.safe_addstr(self.stdscr, res_y + 2, 4, f"{spinner} Searching for \"{self.last_search_query}\"...", curses.color_pair(3))
        elif not self.search_results:
            msg = self.search_status if self.search_status else "Type a song title and press Enter to search."
            msg_color = 6 if ("fail" in msg.lower() or "no result" in msg.lower()) else 5
            self.safe_addstr(self.stdscr, res_y + 2, 4, msg, curses.color_pair(msg_color))
        else:
            visible_count = res_h - 2
            for i in range(min(visible_count, len(self.search_results))):
                item = self.search_results[i]
                line_y = res_y + 1 + i

                art_c, song_c = clean_song_name(item['title'])
                if art_c and song_c:
                    disp_title = f"{art_c} - {song_c}"
                else:
                    disp_title = item['title']

                disp_line = f" {i + 1:2d}. {disp_title}  [{item['duration']}]"
                if len(disp_line) > max_x - 10:
                    disp_line = disp_line[:max_x - 13] + "..."

                if i == self.selected_index:
                    self.safe_addstr(self.stdscr, line_y, 3, " >> ", curses.color_pair(2) | curses.A_BOLD)
                    self.safe_addstr(self.stdscr, line_y, 7, disp_line, curses.color_pair(1) | curses.A_BOLD)
                else:
                    self.safe_addstr(self.stdscr, line_y, 3, f"    {disp_line}", curses.color_pair(4))

    def draw_tab_radios(self, max_y, max_x):
        res_y = 3
        res_h = max_y - res_y - 5
        if res_h < 2:
            return
        self.draw_box(self.stdscr, res_y, 1, res_h, max_x - 2, "RADIO STATIONS", 1)

        for i, st in enumerate(RADIO_STATIONS):
            line_y = res_y + 2 + (i * 2)
            if line_y >= res_y + res_h - 1:
                break

            disp_line = f"{st['name']}  --  [{st['genre']}]"
            if len(disp_line) > max_x - 10:
                disp_line = disp_line[:max_x - 13] + "..."

            if i == self.selected_index:
                self.safe_addstr(self.stdscr, line_y, 3, " >> ", curses.color_pair(2) | curses.A_BOLD)
                self.safe_addstr(self.stdscr, line_y, 7, disp_line, curses.color_pair(1) | curses.A_BOLD)
            else:
                self.safe_addstr(self.stdscr, line_y, 3, f"    {disp_line}", curses.color_pair(4))

    def clear_history(self):
        if HIST_FILE.exists():
            try:
                os.remove(HIST_FILE)
            except Exception:
                pass
        self.history_items = []
        self.selected_index = 0

    def draw_tab_history(self, max_y, max_x):
        res_y = 3
        res_h = max_y - res_y - 5
        if res_h < 2:
            return
        self.draw_box(self.stdscr, res_y, 1, res_h, max_x - 2, "PLAYBACK HISTORY [c: clear history]", 1)

        if not self.history_items:
            self.safe_addstr(self.stdscr, res_y + 2, 4, "No history yet.", curses.color_pair(5))
        else:
            visible_count = res_h - 2
            for i in range(min(visible_count, len(self.history_items))):
                line_y = res_y + 1 + i
                item = self.history_items[i]

                disp_line = f"{item}"
                if len(disp_line) > max_x - 10:
                    disp_line = disp_line[:max_x - 13] + "..."

                if i == self.selected_index:
                    self.safe_addstr(self.stdscr, line_y, 3, " >> ", curses.color_pair(2) | curses.A_BOLD)
                    self.safe_addstr(self.stdscr, line_y, 7, disp_line, curses.color_pair(1) | curses.A_BOLD)
                else:
                    self.safe_addstr(self.stdscr, line_y, 3, f"    {disp_line}", curses.color_pair(4))

    def draw_tab_lyrics(self, max_y, max_x):
        res_y = 3
        res_h = max_y - res_y - 5
        if res_h < 2:
            return

        art_c, song_c = clean_song_name(self.mpv.current_title)
        if art_c and song_c:
            title_str = f"LYRICS :: {art_c} - {song_c}"
        elif self.mpv.current_title != "No Track Playing":
            title_str = f"LYRICS :: {self.mpv.current_title}"
        else:
            title_str = "LYRICS"
        self.draw_box(self.stdscr, res_y, 1, res_h, max_x - 2, title_str, 1)

        if self.lyrics_loading:
            spinner = ["|", "/", "-", "\\"][self.anim_tick % 4]
            self.safe_addstr(self.stdscr, res_y + 2, 4, f"{spinner} Fetching lyrics...", curses.color_pair(3))
            return

        if not self.current_lyrics:
            if self.mpv.current_title == "No Track Playing":
                self.safe_addstr(self.stdscr, res_y + 2, 4, "Play a song to see lyrics here.", curses.color_pair(5))
            else:
                msg = self.lyrics_status if self.lyrics_status else "No lyrics found. Press r to retry."
                self.safe_addstr(self.stdscr, res_y + 2, 4, msg, curses.color_pair(5))
            return

        pos = self.mpv.time_pos
        active_idx = 0
        for idx, (t_sec, text) in enumerate(self.current_lyrics):
            if pos >= t_sec:
                active_idx = idx
            else:
                break

        visible_h = res_h - 2
        center_line = visible_h // 2
        start_idx = max(0, active_idx - center_line + self.lyrics_manual_scroll)

        for i in range(visible_h):
            l_idx = start_idx + i
            if l_idx < 0 or l_idx >= len(self.current_lyrics):
                continue

            t_sec, l_text = self.current_lyrics[l_idx]
            line_y = res_y + 1 + i

            time_fmt = time.strftime("%M:%S", time.gmtime(t_sec))
            disp_line = f" {time_fmt}  {l_text}"
            if len(disp_line) > max_x - 8:
                disp_line = disp_line[:max_x - 11] + "..."

            if l_idx == active_idx:
                row_str = f" >> {disp_line} ".ljust(max_x - 6)
                self.safe_addstr(self.stdscr, line_y, 3, row_str, curses.color_pair(16) | curses.A_BOLD)
            elif l_idx < active_idx:
                self.safe_addstr(self.stdscr, line_y, 4, f"   {disp_line}", curses.color_pair(7))
            else:
                self.safe_addstr(self.stdscr, line_y, 4, f"   {disp_line}", curses.color_pair(4))

    def draw_tab_visualizer(self, max_y, max_x):
        res_y = 3
        res_h = max_y - res_y - 5
        if res_h < 4 or max_x < 20:
            return

        is_active = self.mpv.is_playing and not self.mpv.is_paused
        t_pos = self.mpv.time_pos if is_active else 0.0

        title_str = f"AUDIO SPECTRUM :: ACTIVE [{time.strftime('%M:%S', time.gmtime(t_pos))}]" if is_active else "AUDIO SPECTRUM :: PAUSED"
        self.draw_box(self.stdscr, res_y, 1, res_h, max_x - 2, title_str, 1)

        max_bar_height = res_h - 3
        num_bars = min(60, max(4, (max_x - 6) // 2))
        bar_block_chars = [" ", "▂", "▃", "▄", "▅", "▆", "▇", "█"]

        base_y = res_y + res_h - 2

        for b in range(num_bars):
            bar_x = 3 + (b * 2)
            if bar_x + 1 >= max_x - 2:
                break

            if not is_active:
                self.safe_addstr(self.stdscr, base_y, bar_x, "  ", curses.color_pair(7))
                continue

            pos_factor = t_pos * 5.0
            if b < num_bars * 0.3:
                amp = (math.sin(pos_factor + b * 0.4) * 0.5 + 0.5) * (math.cos(t_pos * 2.5) * 0.3 + 0.7)
            elif b < num_bars * 0.7:
                amp = (math.sin(pos_factor * 1.5 + b * 0.3) * 0.5 + 0.5) * (math.sin(t_pos * 4.0) * 0.4 + 0.6)
            else:
                amp = (math.cos(pos_factor * 2.2 + b * 0.5) * 0.5 + 0.5) * (math.cos(t_pos * 8.0) * 0.4 + 0.6)

            amp = min(1.0, max(0.05, amp))
            col_height = int(amp * max_bar_height)

            for h_idx in range(col_height):
                draw_y = base_y - h_idx
                if draw_y <= res_y:
                    break

                pct = h_idx / max(1, max_bar_height)
                if pct > 0.65:
                    c_pair = 2  # Debian Red Peak
                elif pct > 0.35:
                    c_pair = 3  # Steel Blue Mid
                else:
                    c_pair = 1  # Kali Blue Base

                char_idx = min(len(bar_block_chars) - 1, int(amp * len(bar_block_chars)))
                ch = bar_block_chars[char_idx] if h_idx == col_height - 1 else "█"
                self.safe_addstr(self.stdscr, draw_y, bar_x, f"{ch}{ch}", curses.color_pair(c_pair) | curses.A_BOLD)

    def draw_tab_help(self, max_y, max_x):
        res_y = 3
        res_h = max_y - res_y - 5
        if res_h < 2:
            return
        self.draw_box(self.stdscr, res_y, 1, res_h, max_x - 2, "KEYBOARD SHORTCUTS", 1)

        help_lines = [
            ("1-6 / Tab", "Switch tabs"),
            ("l", "Jump to Lyrics tab"),
            ("r", "Re-fetch lyrics for current song"),
            ("c", "Clear search and type new query"),
            ("s or /", "Edit current search query"),
            ("Left/Right", "Move cursor in search"),
            ("Ctrl+U", "Clear search text"),
            ("Up/Down or k/j", "Navigate list / scroll lyrics"),
            ("Enter", "Submit search / play selected"),
            ("Space", "Toggle pause/resume"),
            ("+/-", "Volume up/down"),
            ("Left/Right", "Seek back/forward 10s"),
            ("q or Esc", "Quit"),
        ]

        for idx, (key, desc) in enumerate(help_lines):
            line_y = res_y + 2 + idx
            if line_y >= res_y + res_h - 1:
                break
            self.safe_addstr(self.stdscr, line_y, 4, key.ljust(18), curses.color_pair(1) | curses.A_BOLD)
            self.safe_addstr(self.stdscr, line_y, 23, desc, curses.color_pair(4))


    def handle_input(self, key):
        if key == -1:
            return

        if self.is_typing_search:
            if key in (10, 13, curses.KEY_ENTER):
                self.is_typing_search = False
                try: curses.curs_set(0)
                except Exception: pass
                if self.search_query.strip():
                    self.perform_search(self.search_query)
                return
            elif key == 9:  # Tab key exits edit mode & switches tabs!
                self.is_typing_search = False
                try: curses.curs_set(0)
                except Exception: pass
                self.current_tab = (self.current_tab + 1) % 6
                self.selected_index = 0
                return
            elif key in (27, curses.KEY_DOWN, curses.KEY_UP):
                self.is_typing_search = False
                try: curses.curs_set(0)
                except Exception: pass
                return
            elif key == curses.KEY_LEFT:
                self.search_cursor_pos = max(0, self.search_cursor_pos - 1)
                return
            elif key == curses.KEY_RIGHT:
                self.search_cursor_pos = min(len(self.search_query), self.search_cursor_pos + 1)
                return
            elif key in (curses.KEY_HOME, 1):
                self.search_cursor_pos = 0
                return
            elif key in (curses.KEY_END, 5):
                self.search_cursor_pos = len(self.search_query)
                return
            elif key == 21:  # Ctrl+U
                self.search_query = ""
                self.search_cursor_pos = 0
                return
            elif key in (curses.KEY_BACKSPACE, 127, 8):
                if self.search_cursor_pos > 0:
                    self.search_query = self.search_query[:self.search_cursor_pos - 1] + self.search_query[self.search_cursor_pos:]
                    self.search_cursor_pos -= 1
                return
            elif key == curses.KEY_DC:
                if self.search_cursor_pos < len(self.search_query):
                    self.search_query = self.search_query[:self.search_cursor_pos] + self.search_query[self.search_cursor_pos + 1:]
                return
            elif 32 <= key <= 126:
                ch = chr(key)
                self.search_query = self.search_query[:self.search_cursor_pos] + ch + self.search_query[self.search_cursor_pos:]
                self.search_cursor_pos += 1
                return
            return

        if key in (ord('q'), 27):
            self.running = False
            return
        elif key in (ord('1'), ord('2'), ord('3'), ord('4'), ord('5'), ord('6')):
            self.current_tab = key - ord('1')
            self.selected_index = 0
        elif key == 9:  # Tab
            self.current_tab = (self.current_tab + 1) % 6
            self.selected_index = 0
        elif key == ord(' '):
            self.mpv.toggle_pause()
        elif key in (ord('+'), ord('='), ord(']')):
            self.mpv.change_volume(5)
        elif key in (ord('-'), ord('[')):
            self.mpv.change_volume(-5)

        elif key in (ord('s'), ord('/')):
            self.current_tab = 0
            self.is_typing_search = True
            self.search_cursor_pos = len(self.search_query)
        elif key in (ord('c'), ord('C')):
            if self.current_tab == 2:
                self.clear_history()
            else:
                self.current_tab = 0
                self.search_query = ""
                self.search_cursor_pos = 0
                self.is_typing_search = True
        elif key in (ord('x'), ord('X')):
            if self.current_tab == 2:
                self.clear_history()
        elif key in (ord('r'), ord('R')):
            if self.mpv.current_title and self.mpv.current_title != "No Track Playing":
                self.fetch_lyrics(self.mpv.current_title, self.mpv.current_artist)

        elif key == curses.KEY_RIGHT:
            self.mpv.seek(10)
        elif key == curses.KEY_LEFT:
            self.mpv.seek(-10)

        elif key in (curses.KEY_DOWN, ord('j')):
            if self.current_tab == 3:
                self.lyrics_manual_scroll += 1
            else:
                max_len = 0
                if self.current_tab == 0: max_len = len(self.search_results)
                elif self.current_tab == 1: max_len = len(RADIO_STATIONS)
                elif self.current_tab == 2: max_len = len(self.history_items)
                if max_len > 0:
                    self.selected_index = (self.selected_index + 1) % max_len

        elif key in (curses.KEY_UP, ord('k')):
            if self.current_tab == 3:
                self.lyrics_manual_scroll -= 1
            else:
                max_len = 0
                if self.current_tab == 0: max_len = len(self.search_results)
                elif self.current_tab == 1: max_len = len(RADIO_STATIONS)
                elif self.current_tab == 2: max_len = len(self.history_items)
                if max_len > 0:
                    self.selected_index = (self.selected_index - 1) % max_len

        elif key in (10, 13, curses.KEY_ENTER):
            if self.current_tab == 0 and self.search_results:
                item = self.search_results[self.selected_index]
                self.mpv.play_url(item['url'], item['title'], item['uploader'], app_ref=self)
                self.load_history()
            elif self.current_tab == 1:
                if self.selected_index < len(RADIO_STATIONS):
                    st = RADIO_STATIONS[self.selected_index]
                    self.mpv.play_url(st['url'], st['name'], st['genre'], app_ref=self)
                    self.load_history()
            elif self.current_tab == 2 and self.history_items:
                h_item = self.history_items[self.selected_index]
                query = h_item.split("|")[-1].strip() if "|" in h_item else h_item
                self.mpv.play_url(f"ytsearch:{query}", query, app_ref=self)

        elif key == ord('l'):
            self.current_tab = 3

    def run(self):
        while self.running:
            self.anim_tick += 1
            self.stdscr.erase()

            max_y, max_x = self.stdscr.getmaxyx()
            if max_y < 12 or max_x < 40:
                self.safe_addstr(self.stdscr, 0, 0, "Terminal too small. Resize.", curses.color_pair(6))
                self.stdscr.refresh()
                time.sleep(0.2)
                continue

            self.draw_header(max_y, max_x)

            if self.current_tab == 0:
                self.draw_tab_search(max_y, max_x)
            elif self.current_tab == 1:
                self.draw_tab_radios(max_y, max_x)
            elif self.current_tab == 2:
                self.draw_tab_history(max_y, max_x)
            elif self.current_tab == 3:
                self.draw_tab_lyrics(max_y, max_x)
            elif self.current_tab == 4:
                self.draw_tab_visualizer(max_y, max_x)
            elif self.current_tab == 5:
                self.draw_tab_help(max_y, max_x)

            self.draw_footer_player(max_y, max_x)

            self.stdscr.refresh()

            try:
                key = self.stdscr.getch()
                self.handle_input(key)
            except Exception:
                pass

            time.sleep(0.05)

        self.mpv.stop()


def main(stdscr):
    app = MusTermApp(stdscr)
    app.run()

if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass
    sys.exit(0)
