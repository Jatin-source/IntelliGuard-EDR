"""
IntelliGuard — AI Threat Intelligence Platform
Upgraded UI/UX: Enterprise Cyberpunk Edition
Place this file at:  malSight/main.py
Run with:           python main.py  (from inside malSight/)
"""

import os
import sys
import time
import math
import queue
import threading
import tkinter as tk
from tkinter import filedialog
from pathlib import Path
import customtkinter as ctk
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from plyer import notification

# ── Ensure project root is on sys.path ─────────────────────────────────────
_project_root = str(Path(__file__).resolve().parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.detector.ensemble import IntelliGuardEnsemble

# ── Theme ───────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

# ── Palette (single source of truth) ────────────────────────────────────────
C = {
    "bg_deep":    "#0d0d12",   # deepest background
    "bg_mid":     "#13131a",   # panels
    "bg_card":    "#1a1a24",   # cards / sidebar
    "bg_hover":   "#22222e",   # hover state
    "border":     "#2a2a3a",   # subtle borders
    "accent":     "#00e5ff",   # cyan accent
    "accent2":    "#7b2fff",   # purple accent
    "green":      "#00ff88",   # safe / ok
    "amber":      "#ffb300",   # warning / booting
    "red":        "#ff3b5c",   # danger / malware
    "txt_pri":    "#e8e8f0",   # primary text
    "txt_sec":    "#6b6b8a",   # secondary / muted
    "txt_mono":   "#00e5ff",   # terminal text
}

# ── Fonts (lazy — created on first access, always after Tk root exists) ─────
_FONTS: dict = {}

def _f(key: str) -> ctk.CTkFont:
    """Return a cached CTkFont. Safe to call any time after CTk() is created."""
    if key not in _FONTS:
        _FONTS[key] = {
            "title":   lambda: ctk.CTkFont(family="Consolas", size=22, weight="bold"),
            "head":    lambda: ctk.CTkFont(family="Consolas", size=14, weight="bold"),
            "body":    lambda: ctk.CTkFont(family="Consolas", size=12),
            "mono":    lambda: ctk.CTkFont(family="Consolas", size=12),
            "huge":    lambda: ctk.CTkFont(family="Consolas", size=72, weight="bold"),
            "verdict": lambda: ctk.CTkFont(family="Consolas", size=24, weight="bold"),
            "label":   lambda: ctk.CTkFont(family="Consolas", size=11),
            "btn":     lambda: ctk.CTkFont(family="Consolas", size=13, weight="bold"),
        }[key]()
    return _FONTS[key]


# ════════════════════════════════════════════════════════════════════════════
#  ANIMATED CANVAS WIDGETS
# ════════════════════════════════════════════════════════════════════════════

class RadarCanvas(tk.Canvas):
    """A rotating radar sweep animation rendered on a tk.Canvas."""

    def __init__(self, master, size=160, **kwargs):

        # allow external bg override but avoid duplicate argument
        bg_color = kwargs.pop("bg", C["bg_mid"])

        super().__init__(
            master,
            width=size,
            height=size,
            bg=bg_color,
            highlightthickness=0,
            **kwargs
        )

        self.size   = size
        self.cx     = size // 2
        self.cy     = size // 2
        self.r      = (size // 2) - 10
        self.angle  = 0
        self._active = False
        self._draw_idle()

    # ── static idle state ──────────────────────────────────────────────────
    def _draw_idle(self):
        self.delete("all")
        # Concentric rings
        for i in range(1, 4):
            ratio = i / 3
            r = int(self.r * ratio)
            self.create_oval(
                self.cx - r, self.cy - r,
                self.cx + r, self.cy + r,
                outline=C["border"], width=1
            )
        # Cross-hairs
        self.create_line(self.cx, self.cy - self.r,
                         self.cx, self.cy + self.r,
                         fill=C["border"], width=1)
        self.create_line(self.cx - self.r, self.cy,
                         self.cx + self.r, self.cy,
                         fill=C["border"], width=1)
        # Centre dot
        self.create_oval(self.cx-3, self.cy-3, self.cx+3, self.cy+3,
                         fill=C["accent"], outline="")

    # ── animated sweep ─────────────────────────────────────────────────────
    def start(self):
        self._active = True
        self._sweep()

    def stop(self):
        self._active = False
        self._draw_idle()

    def _sweep(self):
        if not self._active:
            return
        self.delete("all")
        # Rings
        for i in range(1, 4):
            ratio = i / 3
            r = int(self.r * ratio)
            self.create_oval(
                self.cx - r, self.cy - r,
                self.cx + r, self.cy + r,
                outline=C["border"], width=1
            )
        # Cross-hairs
        self.create_line(self.cx, self.cy - self.r,
                         self.cx, self.cy + self.r,
                         fill=C["border"], width=1)
        self.create_line(self.cx - self.r, self.cy,
                         self.cx + self.r, self.cy,
                         fill=C["border"], width=1)

        # Sweep gradient (arc segments trailing behind the arm)
        TRAIL = 60
        for i in range(TRAIL, 0, -1):
            alpha = int(180 * (i / TRAIL))          # simulate opacity via colour
            trail_angle = self.angle - i
            rad = math.radians(trail_angle)
            x_end = self.cx + self.r * math.cos(rad)
            y_end = self.cy - self.r * math.sin(rad)
            # Use a slightly transparent-looking colour by blending toward bg
            self.create_line(
                self.cx, self.cy, x_end, y_end,
                fill=self._blend(C["accent"], C["bg_mid"], i / TRAIL),
                width=1
            )

        # Leading sweep arm
        rad = math.radians(self.angle)
        x_end = self.cx + self.r * math.cos(rad)
        y_end = self.cy - self.r * math.sin(rad)
        self.create_line(self.cx, self.cy, x_end, y_end,
                         fill=C["accent"], width=2)

        # Centre dot
        self.create_oval(self.cx-3, self.cy-3, self.cx+3, self.cy+3,
                         fill=C["accent"], outline="")

        self.angle = (self.angle + 3) % 360
        self.after(30, self._sweep)   # ~33 fps, smooth & cheap

    @staticmethod
    def _blend(hex1: str, hex2: str, t: float) -> str:
        """Linearly blend two hex colours. t=0 → hex1, t=1 → hex2."""
        r1, g1, b1 = int(hex1[1:3],16), int(hex1[3:5],16), int(hex1[5:7],16)
        r2, g2, b2 = int(hex2[1:3],16), int(hex2[3:5],16), int(hex2[5:7],16)
        r = int(r1 + (r2-r1)*t)
        g = int(g1 + (g2-g1)*t)
        b = int(b1 + (b2-b1)*t)
        return f"#{r:02x}{g:02x}{b:02x}"


class PulsingDot(tk.Canvas):
    """Tiny pulsing status indicator (like a heart-beat LED)."""

    def __init__(self, master, color=C["amber"], size=14, **kwargs):
        super().__init__(master, width=size, height=size,
                         bg=C["bg_card"], highlightthickness=0, **kwargs)
        self._color  = color
        self._size   = size
        self._scale  = 1.0
        self._growing = False
        self._pulse()

    def set_color(self, color: str):
        self._color = color

    def _pulse(self):
        # Oscillate between 0.4 and 1.0 scale
        if self._growing:
            self._scale = min(1.0, self._scale + 0.06)
            if self._scale >= 1.0:
                self._growing = False
        else:
            self._scale = max(0.4, self._scale - 0.06)
            if self._scale <= 0.4:
                self._growing = True

        self.delete("all")
        half = self._size / 2
        r    = half * self._scale
        self.create_oval(half-r, half-r, half+r, half+r,
                         fill=self._color, outline="")
        self.after(60, self._pulse)


# ════════════════════════════════════════════════════════════════════════════
#  STAT CARD (small metric tiles in the header bar)
# ════════════════════════════════════════════════════════════════════════════

class StatCard(ctk.CTkFrame):
    def __init__(self, master, label: str, value: str, accent: str, **kwargs):
        super().__init__(master,
                         fg_color=C["bg_card"],
                         corner_radius=8,
                         border_width=1,
                         border_color=C["border"],
                         **kwargs)
        ctk.CTkLabel(self, text=label,
                     font=_f("label"),
                     text_color=C["txt_sec"]).pack(pady=(10, 0))
        self.value_lbl = ctk.CTkLabel(self, text=value,
                                      font=ctk.CTkFont(family="Consolas", size=18, weight="bold"),
                                      text_color=accent)
        self.value_lbl.pack(pady=(2, 10))

    def update_value(self, value: str):
        self.value_lbl.configure(text=value)


# ════════════════════════════════════════════════════════════════════════════
#  VOTE INDICATOR ROW
# ════════════════════════════════════════════════════════════════════════════

class VoteRow(ctk.CTkFrame):
    def __init__(self, master, model_name: str, **kwargs):
        super().__init__(master,
                         fg_color=C["bg_card"],
                         corner_radius=6,
                         border_width=1,
                         border_color=C["border"],
                         **kwargs)
        self.configure(height=36)

        self.name_lbl = ctk.CTkLabel(self, text=f"► {model_name}",
                                     font=_f("mono"),
                                     text_color=C["txt_sec"],
                                     width=160, anchor="w")
        self.name_lbl.pack(side="left", padx=(12, 0))

        self.verdict_lbl = ctk.CTkLabel(self, text="PENDING",
                                        font=_f("mono"),
                                        text_color=C["txt_sec"],
                                        width=90)
        self.verdict_lbl.pack(side="left", padx=8)

        self.bar = ctk.CTkProgressBar(self, width=180, height=6,
                                      fg_color=C["border"],
                                      progress_color=C["txt_sec"])
        self.bar.set(0)
        self.bar.pack(side="left", padx=8)

        self.conf_lbl = ctk.CTkLabel(self, text="--.--%",
                                     font=_f("label"),
                                     text_color=C["txt_sec"],
                                     width=60)
        self.conf_lbl.pack(side="left", padx=(4, 12))

    def animate_result(self, is_malware: bool, confidence: float, delay_ms: int = 0):
        """Animate the bar and label after `delay_ms` ms."""
        color  = C["red"] if is_malware else C["green"]
        label  = "MALWARE" if is_malware else "SAFE"

        def _run():
            self.verdict_lbl.configure(text=label, text_color=color)
            self.bar.configure(progress_color=color)
            self.conf_lbl.configure(text=f"{confidence*100:.1f}%", text_color=color)
            # Animate bar from 0 → confidence
            steps = 20
            for i in range(1, steps + 1):
                val = (confidence / steps) * i
                self.bar.set(val)
                time.sleep(0.02)

        def _after():
            threading.Thread(target=_run, daemon=True).start()

        self.after(delay_ms, _after)

    def reset(self):
        self.verdict_lbl.configure(text="PENDING", text_color=C["txt_sec"])
        self.bar.set(0)
        self.bar.configure(progress_color=C["txt_sec"])
        self.conf_lbl.configure(text="--.--% ", text_color=C["txt_sec"])


class DownloadHandler(FileSystemEventHandler):
    def __init__(self, app):
        super().__init__()
        self.app = app

    def on_created(self, event):
        if not event.is_directory:
            ext = os.path.splitext(event.src_path)[1].lower()
            if ext in ['.exe', '.dll', '.sys', '.msi']:
                self.app.queue_scan(event.src_path)

# ════════════════════════════════════════════════════════════════════════════
#  MAIN APPLICATION
# ════════════════════════════════════════════════════════════════════════════

class IntelliGuardApp(ctk.CTk):

    def __init__(self):
        super().__init__()   # ← root window now exists; _f() calls are now safe

        self.title("IntelliGuard  //  AI Threat Intelligence Platform  //  v2.0")
        self.geometry("1180x720")
        self.resizable(False, False)
        self.configure(fg_color=C["bg_deep"])

        self.engine      = None
        self.is_scanning = False
        self._scan_count = 0
        self._threat_count = 0
        self.scan_queue = queue.Queue()

        self._build_ui()

        # Boot AI in background so UI is snappy
        threading.Thread(target=self._initialize_engine, daemon=True).start()
        threading.Thread(target=self._scan_worker, daemon=True).start()
        self._start_background_monitor()

    # ────────────────────────────────────────────────────────────────────────
    #  ENGINE INIT
    # ────────────────────────────────────────────────────────────────────────
    def _initialize_engine(self):
        self._log("[SYS]  Booting IntelliGuard Core Engine …")
        self.engine = IntelliGuardEnsemble()
        self._log("[SYS]  XGBoost Expert Ensemble loaded  (Kaggle · BODMAS · EMBER)")
        self._log("[SYS]  Cryptographic Heuristic Layer  →  ACTIVE")
        self._log("[SYS]  Late-Fusion Voting Module       →  ARMED")
        self._log("[SYS]  ─────────────────────────────────────────")
        self._log("[RDY]  System online. Drop a target to begin.")

        # Update status dot & label safely on main thread
        self.after(0, lambda: self.dot.set_color(C["green"]))
        self.after(0, lambda: self.status_lbl.configure(
            text="ONLINE", text_color=C["green"]))
        self.after(0, lambda: self.scan_btn.configure(state="normal"))

    # ────────────────────────────────────────────────────────────────────────
    #  UI CONSTRUCTION
    # ────────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        # ── TOP HEADER BAR ─────────────────────────────────────────────────
        header = ctk.CTkFrame(self, fg_color=C["bg_card"],
                              corner_radius=0, height=58,
                              border_width=1, border_color=C["border"])
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        # Logo
        ctk.CTkLabel(header, text="⬡ INTELLIGUARD",
                     font=_f("title"),
                     text_color=C["accent"]).pack(side="left", padx=24, pady=10)

        ctk.CTkLabel(header, text="AI THREAT INTELLIGENCE PLATFORM",
                     font=_f("label"),
                     text_color=C["txt_sec"]).pack(side="left", pady=10)

        # Right-side stat cards
        stats_frame = ctk.CTkFrame(header, fg_color="transparent")
        stats_frame.pack(side="right", padx=16, pady=8)

        self.card_scanned = StatCard(stats_frame, "FILES SCANNED", "0",
                                     C["accent"])
        self.card_scanned.pack(side="left", padx=6)

        self.card_threats = StatCard(stats_frame, "THREATS FOUND", "0",
                                     C["red"])
        self.card_threats.pack(side="left", padx=6)

        self.card_model = StatCard(stats_frame, "ENGINE", "XGBoost ×3",
                                   C["accent2"])
        self.card_model.pack(side="left", padx=6)

        # ── BODY (sidebar + main) ───────────────────────────────────────────
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=0, pady=0)

        # ── LEFT SIDEBAR ────────────────────────────────────────────────────
        sidebar = ctk.CTkFrame(body, width=230, fg_color=C["bg_card"],
                               corner_radius=0,
                               border_width=1, border_color=C["border"])
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        ctk.CTkLabel(sidebar, text="CONTROL PANEL",
                     font=_f("label"), text_color=C["txt_sec"]).pack(
                     pady=(24, 4), padx=16, anchor="w")

        # Thin accent line
        ctk.CTkFrame(sidebar, height=1, fg_color=C["accent"]).pack(
            fill="x", padx=16, pady=(0, 18))

        self.scan_btn = ctk.CTkButton(
            sidebar,
            text="▸  SELECT TARGET FILE",
            command=self.browse_file,
            height=44,
            font=_f("btn"),
            fg_color=C["accent"],
            hover_color="#00b8cc",
            text_color=C["bg_deep"],
            corner_radius=6,
            state="disabled"
        )
        self.scan_btn.pack(pady=(0, 10), padx=16, fill="x")

        self.clear_btn = ctk.CTkButton(
            sidebar,
            text="↺  CLEAR TERMINAL",
            command=self._clear_console,
            height=36,
            font=_f("btn"),
            fg_color=C["bg_hover"],
            hover_color=C["border"],
            text_color=C["txt_sec"],
            corner_radius=6,
            border_width=1,
            border_color=C["border"]
        )
        self.clear_btn.pack(pady=(0, 20), padx=16, fill="x")

        # ── Separator ──────────────────────────────────────────────────────
        ctk.CTkLabel(sidebar, text="EXPERT MODELS",
                     font=_f("label"), text_color=C["txt_sec"]).pack(
                     pady=(0, 4), padx=16, anchor="w")
        ctk.CTkFrame(sidebar, height=1, fg_color=C["border"]).pack(
            fill="x", padx=16, pady=(0, 12))

        # Model tags
        for name, dataset in [("Expert α", "KAGGLE"), ("Expert β", "BODMAS"), ("Expert γ", "EMBER")]:
            row = ctk.CTkFrame(sidebar, fg_color=C["bg_mid"], corner_radius=6)
            row.pack(fill="x", padx=16, pady=3)
            ctk.CTkLabel(row, text=name, font=_f("mono"),
                         text_color=C["accent2"]).pack(side="left", padx=10, pady=6)
            ctk.CTkLabel(row, text=dataset, font=_f("label"),
                         text_color=C["txt_sec"]).pack(side="right", padx=10)

        # ── Status dot at bottom ────────────────────────────────────────────
        status_row = ctk.CTkFrame(sidebar, fg_color="transparent")
        status_row.pack(side="bottom", pady=20, padx=16, anchor="w")

        self.dot = PulsingDot(status_row, color=C["amber"])
        self.dot.pack(side="left", padx=(0, 8))

        self.status_lbl = ctk.CTkLabel(status_row, text="BOOTING …",
                                       font=_f("mono"),
                                       text_color=C["amber"])
        self.status_lbl.pack(side="left")

        # ── RIGHT MAIN AREA ─────────────────────────────────────────────────
        main = ctk.CTkFrame(body, fg_color=C["bg_mid"], corner_radius=0)
        main.pack(side="right", fill="both", expand=True)

        # ── TOP HALF: Radar + Verdict ────────────────────────────────────────
        top_panel = ctk.CTkFrame(main, fg_color="transparent")
        top_panel.pack(fill="x", padx=24, pady=(20, 10))

        # --- Radar widget ---
        radar_frame = ctk.CTkFrame(top_panel, fg_color=C["bg_card"],
                                   corner_radius=10,
                                   border_width=1, border_color=C["border"])
        radar_frame.pack(side="left", padx=(0, 16))

        ctk.CTkLabel(radar_frame, text="SCAN RADAR",
                     font=_f("label"), text_color=C["txt_sec"]).pack(
                     pady=(10, 4))
        self.radar = RadarCanvas(radar_frame, size=160, bg=C["bg_card"])
        self.radar.pack(padx=16, pady=(0, 12))

        # --- Verdict panel ---
        verdict_frame = ctk.CTkFrame(top_panel, fg_color=C["bg_card"],
                                     corner_radius=10,
                                     border_width=1, border_color=C["border"])
        verdict_frame.pack(side="left", fill="both", expand=True)

        self.verdict_icon = ctk.CTkLabel(verdict_frame, text="◈",
                                         font=_f("huge"),
                                         text_color=C["border"])
        self.verdict_icon.pack(pady=(12, 0))

        self.verdict_lbl = ctk.CTkLabel(verdict_frame,
                                        text="AWAITING TARGET",
                                        font=_f("verdict"),
                                        text_color=C["txt_sec"])
        self.verdict_lbl.pack(pady=(0, 4))

        self.file_lbl = ctk.CTkLabel(verdict_frame, text="No file selected",
                                     font=_f("label"), text_color=C["txt_sec"])
        self.file_lbl.pack(pady=(0, 10))

        self.elapsed_lbl = ctk.CTkLabel(verdict_frame, text="",
                                        font=_f("label"), text_color=C["txt_sec"])
        self.elapsed_lbl.pack()

        # --- Vote rows panel ---
        votes_outer = ctk.CTkFrame(main, fg_color=C["bg_card"],
                                   corner_radius=10,
                                   border_width=1, border_color=C["border"])
        votes_outer.pack(fill="x", padx=24, pady=(0, 10))

        ctk.CTkLabel(votes_outer, text="ENSEMBLE VOTE BREAKDOWN",
                     font=_f("label"), text_color=C["txt_sec"]).pack(
                     pady=(10, 4), padx=16, anchor="w")
        ctk.CTkFrame(votes_outer, height=1, fg_color=C["border"]).pack(
            fill="x", padx=16, pady=(0, 8))

        self.vote_rows: dict[str, VoteRow] = {}
        for name in ["Expert α  (Kaggle)", "Expert β  (BODMAS)", "Expert γ  (EMBER)"]:
            vr = VoteRow(votes_outer, model_name=name)
            vr.pack(fill="x", padx=16, pady=3)
            self.vote_rows[name] = vr
        ctk.CTkFrame(votes_outer, height=0).pack(pady=4)   # bottom padding

        # ── TERMINAL ────────────────────────────────────────────────────────
        term_header = ctk.CTkFrame(main, fg_color="transparent")
        term_header.pack(fill="x", padx=24, pady=(0, 4))

        ctk.CTkLabel(term_header, text="SYSTEM TERMINAL",
                     font=_f("label"), text_color=C["txt_sec"]).pack(side="left")

        # Blinking cursor label (cosmetic)
        self._cursor_visible = True
        self.cursor_lbl = ctk.CTkLabel(term_header, text="█",
                                       font=_f("mono"), text_color=C["accent"])
        self.cursor_lbl.pack(side="left", padx=4)
        self._blink_cursor()

        self.console = ctk.CTkTextbox(
            main,
            font=_f("mono"),
            fg_color=C["bg_deep"],
            text_color=C["txt_mono"],
            border_width=1,
            border_color=C["border"],
            corner_radius=8,
            scrollbar_button_color=C["border"],
            scrollbar_button_hover_color=C["bg_hover"],
            wrap="word"
        )
        self.console.pack(fill="both", expand=True, padx=24, pady=(0, 18))
        self.console.configure(state="disabled")

    # ────────────────────────────────────────────────────────────────────────
    #  CURSOR BLINK  (purely cosmetic)
    # ────────────────────────────────────────────────────────────────────────
    def _blink_cursor(self):
        self._cursor_visible = not self._cursor_visible
        self.cursor_lbl.configure(
            text="█" if self._cursor_visible else " ")
        self.after(530, self._blink_cursor)

    # ────────────────────────────────────────────────────────────────────────
    #  LOGGING  (thread-safe via after())
    # ────────────────────────────────────────────────────────────────────────
    def _log(self, text: str, typewriter: bool = False, delay_ms: int = 0):
        """Append text to the terminal. Safe to call from any thread."""
        def _plain():
            self.console.configure(state="normal")
            self.console.insert("end", "\n" + text)
            self.console.see("end")
            self.console.configure(state="disabled")
        self.after(delay_ms, _plain)

    def _clear_console(self):
        self.console.configure(state="normal")
        self.console.delete("1.0", "end")
        self.console.configure(state="disabled")

    # ────────────────────────────────────────────────────────────────────────
    #  FILE BROWSE + SCAN
    # ────────────────────────────────────────────────────────────────────────
    def _start_background_monitor(self):
        downloads_path = os.path.expanduser("~/Downloads")
        if not os.path.exists(downloads_path):
            try:
                os.makedirs(downloads_path)
            except Exception:
                pass

        if os.path.exists(downloads_path):
            self.observer = Observer()
            handler = DownloadHandler(self)
            self.observer.schedule(handler, downloads_path, recursive=False)
            self.observer.start()
            self.after(2000, lambda: self._log(f"[SYS]  Real-time protection activated on {downloads_path}"))

    def queue_scan(self, file_path):
        self.scan_queue.put(file_path)
        filename = os.path.basename(file_path)
        self._log(f"[*] Target queued for analysis: {filename}")

    def _scan_worker(self):
        while True:
            file_path = self.scan_queue.get()
            while self.is_scanning:
                time.sleep(1)
            
            self.is_scanning = True
            self._run_scan(file_path)

    def browse_file(self):
        fp = filedialog.askopenfilename(
            title="Select Binary to Analyse",
            filetypes=[("Executable", "*.exe"), ("DLL", "*.dll"), ("All files", "*.*")]
        )
        if fp:
            self.queue_scan(fp)

    def _run_scan(self, file_path: str):
        filename = os.path.basename(file_path)
        fsize    = os.path.getsize(file_path)
        self.last_scanned_file = filename

        # ── Reset UI ──────────────────────────────────────────────────────
        self.after(0, lambda: self.scan_btn.configure(
            state="disabled", text="⚙  ANALYSING …"))
        self.after(0, lambda: self.verdict_icon.configure(
            text="◌", text_color=C["amber"]))
        self.after(0, lambda: self.verdict_lbl.configure(
            text="EXTRACTING FEATURES …", text_color=C["amber"]))
        self.after(0, lambda: self.file_lbl.configure(
            text=filename, text_color=C["txt_sec"]))
        self.after(0, lambda: self.elapsed_lbl.configure(text=""))
        self.after(0, lambda: [vr.reset() for vr in self.vote_rows.values()])
        self.after(0, self.radar.start)
        self.after(0, lambda: self.dot.set_color(C["amber"]))
        self.after(0, lambda: self.status_lbl.configure(
            text="SCANNING", text_color=C["amber"]))

        # ── Log header ────────────────────────────────────────────────────
        self._log("", delay_ms=0)
        self._log("┌─────────────────────────────────────────────────┐")
        self._log(f"│  TARGET   : {filename[:44]:<44} │")
        self._log(f"│  SIZE     : {fsize:,} bytes{'':<36} │")
        self._log("│  ENGINE   : XGBoost Ensemble (Kaggle·BODMAS·EMBER) │")
        self._log("└─────────────────────────────────────────────────┘")
        self._log("[*] Parsing PE headers …", delay_ms=50)
        self._log("[*] Running Cryptographic Heuristic Layer …", delay_ms=100)

        # ── Call backend ──────────────────────────────────────────────────
        t0     = time.time()
        result = self.engine.scan_file(file_path)
        elapsed = time.time() - t0

        self.after(0, self.radar.stop)

        # ── Process result ────────────────────────────────────────────────
        if result.get("status") == "error":
            self._log(f"[ERR] {result.get('message')}", typewriter=True, delay_ms=200)
            self.after(300, lambda: self.verdict_icon.configure(
                text="⚠", text_color=C["amber"]))
            self.after(300, lambda: self.verdict_lbl.configure(
                text="ANALYSIS FAILED", text_color=C["amber"]))
            self.after(300, lambda: self.dot.set_color(C["amber"]))
            self.after(300, lambda: self.status_lbl.configure(
                text="ERROR", text_color=C["amber"]))
        else:
            votes   = result.get("votes", {})
            verdict = result.get("verdict")

            # Map backend keys → our VoteRow names (order must match)
            row_keys = list(self.vote_rows.keys())
            vote_items = list(votes.items())

            for idx, (model_key, data) in enumerate(vote_items):
                delay  = 400 + idx * 250        # faster stagger reveal
                vr_key = row_keys[idx] if idx < len(row_keys) else None

                # Log line
                if data.get("status") == "SKIPPED":
                    status = "SKIPPED"
                    conf_str = "--.--%"
                    icon = "⏭️"
                    is_malware = False
                    conf_float = 0.0
                else:
                    status = "MALWARE" if data["malware"] else "SAFE"
                    conf_float = data["confidence"]
                    conf_str = f'{conf_float * 100:.2f}%'
                    icon = '🔴' if data["malware"] else '🟢'
                    is_malware = bool(data["malware"])
                    
                line   = f"  {icon} [{model_key}] → {status}  ({conf_str})"
                self._log(line, delay_ms=delay)

                # Animate vote row
                if vr_key:
                    if data.get("status") != "SKIPPED":
                        self.vote_rows[vr_key].animate_result(
                            is_malware, conf_float,
                            delay_ms=delay + 100
                        )

            total_delay = 400 + len(vote_items) * 250 + 200
            self._log(f"[*]  Scan completed in {elapsed:.2f}s.", delay_ms=total_delay)
            self.after(total_delay, lambda: self.elapsed_lbl.configure(
                text=f"Scan time: {elapsed:.2f} s"))

            if verdict == "SAFE":
                self.after(total_delay + 400, self._show_safe)
            else:
                self.after(total_delay + 400, self._show_malware)

            # Update counters
            self._scan_count += 1
            if verdict != "SAFE":
                self._threat_count += 1
            self.after(total_delay, lambda: self.card_scanned.update_value(
                str(self._scan_count)))
            self.after(total_delay, lambda: self.card_threats.update_value(
                str(self._threat_count)))

        # ── Re-enable button after all animations settle ───────────────────
        settle = total_delay + 800
        self.after(settle, lambda: self.scan_btn.configure(
            state="normal", text="▸  SELECT TARGET FILE"))
        self.after(settle, lambda: self.dot.set_color(C["green"]))
        self.after(settle, lambda: self.status_lbl.configure(
            text="ONLINE", text_color=C["green"]))
        self.after(settle, lambda: setattr(self, "is_scanning", False))

    # ────────────────────────────────────────────────────────────────────────
    #  VERDICT STATES
    # ────────────────────────────────────────────────────────────────────────
    def _show_safe(self):
        filename = getattr(self, 'last_scanned_file', 'File')
        self.verdict_icon.configure(text="✓", text_color=C["green"])
        self.verdict_lbl.configure(text="FILE IS SECURE", text_color=C["green"])
        self._log("═══════════════════════════════════════════════════")
        self._log("  LATE-FUSION VERDICT →  ✓  SAFE                  ")
        self._log("═══════════════════════════════════════════════════")
        try:
            notification.notify(title="IntelliGuard: Safe", message=f"{filename} is secure.", timeout=3)
        except Exception:
            pass

    def _show_malware(self):
        filename = getattr(self, 'last_scanned_file', 'File')
        self.verdict_icon.configure(text="☠", text_color=C["red"])
        self.verdict_lbl.configure(text="THREAT DETECTED", text_color=C["red"])
        self._log("═══════════════════════════════════════════════════")
        self._log("  LATE-FUSION VERDICT →  ☠  MALWARE DETECTED       ")
        self._log("  ⚠  IMMEDIATE QUARANTINE RECOMMENDED               ")
        self._log("═══════════════════════════════════════════════════")
        try:
            notification.notify(title="IntelliGuard: THREAT DETECTED", message=f"Malware found in {filename}!", timeout=5)
        except Exception:
            pass


# ════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = IntelliGuardApp()
    app.mainloop()