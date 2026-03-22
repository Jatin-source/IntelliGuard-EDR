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
try:
    import pystray
    from PIL import Image as PILImage, ImageDraw
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False
_project_root = str(Path(__file__).resolve().parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
from src.detector.ensemble import IntelliGuardEnsemble
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")
C = {
    "bg_deep":    "#080b0f",
    "bg_mid":     "#0e1117",
    "bg_card":    "#141820",
    "bg_hover":   "#1c2230",
    "border":     "#1e2535",
    "border2":    "#2a3548",
    "accent":     "#00d4ff",
    "accent2":    "#6c3fff",
    "green":      "#00e676",
    "amber":      "#ffc107",
    "red":        "#ff1744",
    "red_dim":    "#cc0033",
    "txt_pri":    "#dde3f0",
    "txt_sec":    "#55647a",
    "txt_mono":   "#4fc3f7",
    "safe_glow":  "#00e676",
    "danger_glow":"#ff1744",
}
_FONTS: dict = {}
def _f(key: str) -> ctk.CTkFont:
    if key not in _FONTS:
        _FONTS[key] = {
            "title":   lambda: ctk.CTkFont(family="Consolas", size=20, weight="bold"),
            "head":    lambda: ctk.CTkFont(family="Consolas", size=13, weight="bold"),
            "body":    lambda: ctk.CTkFont(family="Consolas", size=12),
            "mono":    lambda: ctk.CTkFont(family="Consolas", size=11),
            "huge":    lambda: ctk.CTkFont(family="Consolas", size=64, weight="bold"),
            "verdict": lambda: ctk.CTkFont(family="Consolas", size=22, weight="bold"),
            "label":   lambda: ctk.CTkFont(family="Consolas", size=10),
            "btn":     lambda: ctk.CTkFont(family="Consolas", size=12, weight="bold"),
            "score":   lambda: ctk.CTkFont(family="Consolas", size=16, weight="bold"),
        }[key]()
    return _FONTS[key]
class RadarCanvas(tk.Canvas):
    TRAIL_STEPS = 12   
    FPS_MS      = 80   
    def __init__(self, master, size=150, **kwargs):
        bg = kwargs.pop("bg", C["bg_mid"])
        super().__init__(master, width=size, height=size,
                         bg=bg, highlightthickness=0, **kwargs)
        self.size = size
        self.cx   = size // 2
        self.cy   = size // 2
        self.r    = size // 2 - 8
        self.angle = 0
        self._active = False
        self._after_id = None
        self._build_static()
        self._build_sweep()
    def _build_static(self):
        cx, cy, r = self.cx, self.cy, self.r
        for i in range(1, 4):
            ri = int(r * i / 3)
            self.create_oval(cx-ri, cy-ri, cx+ri, cy+ri,
                             outline=C["border2"], width=1, tags="static")
        self.create_line(cx, cy-r, cx, cy+r, fill=C["border2"], width=1, tags="static")
        self.create_line(cx-r, cy, cx+r, cy, fill=C["border2"], width=1, tags="static")
        self.create_oval(cx-3, cy-3, cx+3, cy+3,
                         fill=C["accent"], outline="", tags="dot")
    def _build_sweep(self):
        cx, cy = self.cx, self.cy
        self._trail_ids = []
        for _ in range(self.TRAIL_STEPS):
            lid = self.create_line(cx, cy, cx, cy, fill=C["border"], width=1)
            self._trail_ids.append(lid)
        self._arm_id = self.create_line(cx, cy, cx, cy,
                                        fill=C["accent"], width=2)
    @staticmethod
    def _blend(hex1, hex2, t):
        r1,g1,b1 = int(hex1[1:3],16),int(hex1[3:5],16),int(hex1[5:7],16)
        r2,g2,b2 = int(hex2[1:3],16),int(hex2[3:5],16),int(hex2[5:7],16)
        return f"#{int(r1+(r2-r1)*t):02x}{int(g1+(g2-g1)*t):02x}{int(b1+(b2-b1)*t):02x}"
    def start(self):
        self._active = True
        self._sweep()
    def stop(self):
        self._active = False
        if self._after_id:
            self.after_cancel(self._after_id)
            self._after_id = None
        cx, cy = self.cx, self.cy
        for lid in self._trail_ids:
            self.coords(lid, cx, cy, cx, cy)
        self.coords(self._arm_id, cx, cy, cx, cy)
    def _sweep(self):
        if not self._active:
            return
        cx, cy, r = self.cx, self.cy, self.r
        N = self.TRAIL_STEPS
        for i, lid in enumerate(self._trail_ids):
            a = math.radians(self.angle - (N - i) * 3)
            x = cx + r * math.cos(a)
            y = cy - r * math.sin(a)
            t = i / N
            self.coords(lid, cx, cy, x, y)
            self.itemconfig(lid, fill=self._blend(C["accent"], C["bg_mid"], 1 - t))
        arm_rad = math.radians(self.angle)
        ax = cx + r * math.cos(arm_rad)
        ay = cy - r * math.sin(arm_rad)
        self.coords(self._arm_id, cx, cy, ax, ay)
        self.tag_raise("dot")
        self.angle = (self.angle + 5) % 360
        self._after_id = self.after(self.FPS_MS, self._sweep)
class PulsingDot(tk.Canvas):
    def __init__(self, master, color=C["amber"], size=12, **kwargs):
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
        self._growing = not self._growing if self._scale >= 1.0 or self._scale <= 0.45 else self._growing
        self._scale += 0.1 if self._growing else -0.1
        self._scale = max(0.45, min(1.0, self._scale))
        half = self._size / 2
        r = half * self._scale
        self.delete("all")
        self.create_oval(half-r, half-r, half+r, half+r,
                         fill=self._color, outline="")
        self.after(150, self._pulse)   
class StatCard(ctk.CTkFrame):
    def __init__(self, master, label: str, value: str, accent: str, **kwargs):
        super().__init__(master, fg_color=C["bg_card"],
                         corner_radius=6, border_width=1,
                         border_color=C["border2"], **kwargs)
        ctk.CTkLabel(self, text=label, font=_f("label"),
                     text_color=C["txt_sec"]).pack(pady=(8, 0), padx=12)
        self.value_lbl = ctk.CTkLabel(
            self, text=value,
            font=ctk.CTkFont(family="Consolas", size=16, weight="bold"),
            text_color=accent)
        self.value_lbl.pack(pady=(2, 8))
    def update_value(self, value: str):
        self.value_lbl.configure(text=value)
class VoteRow(ctk.CTkFrame):
    def __init__(self, master, model_name: str, **kwargs):
        super().__init__(master, fg_color=C["bg_card"],
                         corner_radius=5, border_width=1,
                         border_color=C["border"], **kwargs)
        self.configure(height=34)
        self.name_lbl = ctk.CTkLabel(self, text=f"▸ {model_name}",
                                     font=_f("mono"), text_color=C["txt_sec"],
                                     width=150, anchor="w")
        self.name_lbl.pack(side="left", padx=(10, 0))
        self.verdict_lbl = ctk.CTkLabel(self, text="WAITING",
                                        font=_f("mono"), text_color=C["txt_sec"],
                                        width=80)
        self.verdict_lbl.pack(side="left", padx=6)
        self.bar = ctk.CTkProgressBar(self, width=160, height=5,
                                      fg_color=C["border"],
                                      progress_color=C["txt_sec"])
        self.bar.set(0)
        self.bar.pack(side="left", padx=6)
        self.conf_lbl = ctk.CTkLabel(self, text="--.--%",
                                     font=_f("label"), text_color=C["txt_sec"],
                                     width=55)
        self.conf_lbl.pack(side="left", padx=(4, 10))
        self.cov_lbl = ctk.CTkLabel(self, text="",
                                    font=_f("label"), text_color=C["txt_sec"],
                                    width=60)
        self.cov_lbl.pack(side="left", padx=(0, 8))
    def animate_result(self, is_malware: bool, confidence: float,
                       match_ratio: float = 1.0, delay_ms: int = 0):
        color = C["red"] if is_malware else C["green"]
        label = "MALWARE" if is_malware else "SAFE"
        cov   = f"cov:{match_ratio*100:.0f}%"
        def _start():
            self.verdict_lbl.configure(text=label, text_color=color)
            self.bar.configure(progress_color=color)
            self.conf_lbl.configure(text=f"{confidence*100:.1f}%", text_color=color)
            self.cov_lbl.configure(text=cov, text_color=C["txt_sec"])
            self._animate_bar(0, 18, confidence)   
        self.after(delay_ms, _start)
    def set_skipped(self, delay_ms: int = 0):
        def _start():
            self.verdict_lbl.configure(text="SKIPPED", text_color=C["amber"])
            self.conf_lbl.configure(text="N/A", text_color=C["amber"])
        self.after(delay_ms, _start)
    def set_trusted(self, delay_ms: int = 0):
        def _start():
            self.verdict_lbl.configure(text="TRUSTED", text_color=C["green"])
            self.bar.set(0)
            self.bar.configure(progress_color=C["green"])
            self.conf_lbl.configure(text="--", text_color=C["green"])
        self.after(delay_ms, _start)
    def _animate_bar(self, step, total, target):
        if step > total:
            return
        self.bar.set((target / total) * step)
        self.after(25, lambda: self._animate_bar(step + 1, total, target))
    def reset(self):
        self.verdict_lbl.configure(text="WAITING", text_color=C["txt_sec"])
        self.bar.set(0)
        self.bar.configure(progress_color=C["txt_sec"])
        self.conf_lbl.configure(text="--.--%", text_color=C["txt_sec"])
        self.cov_lbl.configure(text="")
_TEMP_EXT      = {'.crdownload', '.tmp', '.partial', '.downloading', '.part', '.download'}
_SCAN_EXT      = {'.exe', '.dll', '.sys', '.msi', '.scr', '.bat', '.cmd', '.com', '.pif',
                  '.vbs', '.ps1', '.jar', '.hta', '.wsf'}
class DownloadHandler(FileSystemEventHandler):
    def __init__(self, app):
        super().__init__()
        self.app     = app
        self._pending = set()
        self._lock    = threading.Lock()
    def on_created(self, event):
        if not event.is_directory:
            self._check(event.src_path)
    def on_moved(self, event):
        if not event.is_directory:
            self._check(event.dest_path)
    def _check(self, path: str):
        ext = os.path.splitext(path)[1].lower()
        if ext in _TEMP_EXT:
            return
        if ext in _SCAN_EXT:
            self._wait_and_queue(path)
    def _wait_and_queue(self, file_path: str):
        with self._lock:
            if file_path in self._pending:
                return
            self._pending.add(file_path)
        def _worker():
            try:
                prev_size = -1
                stable = 0
                for _ in range(120):        
                    try:
                        cur = os.path.getsize(file_path)
                    except OSError:
                        time.sleep(0.5)
                        continue
                    if cur == prev_size and cur > 0:
                        stable += 1
                        if stable >= 3:
                            break
                    else:
                        stable = 0
                    prev_size = cur
                    time.sleep(0.5)
                try:
                    with open(file_path, 'rb') as f:
                        f.read(1)
                except (OSError, PermissionError):
                    return
                self.app.queue_scan(file_path, auto=True)
            finally:
                with self._lock:
                    self._pending.discard(file_path)
        threading.Thread(target=_worker, daemon=True).start()
def _make_tray_icon():
    size = 64
    img  = PILImage.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.polygon([(32, 4), (58, 16), (58, 36), (32, 60), (6, 36), (6, 16)],
                 fill=(0, 212, 255, 220), outline=(0, 150, 200, 255))
    return img
class IntelliGuardApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("IntelliGuard  //  AI Threat Intelligence  //  v3.0")
        self.geometry("1180x720")
        self.resizable(False, False)
        self.configure(fg_color=C["bg_deep"])
        self.engine         = None
        self.is_scanning    = False
        self._scan_count    = 0
        self._threat_count  = 0
        self.scan_queue     = queue.Queue()
        self._tray          = None
        self._hidden        = False
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        threading.Thread(target=self._initialize_engine, daemon=True).start()
        threading.Thread(target=self._scan_worker, daemon=True).start()
        self._start_background_monitor()
        if TRAY_AVAILABLE:
            threading.Thread(target=self._start_tray, daemon=True).start()
    def _on_close(self):
        if TRAY_AVAILABLE and self._tray:
            self.withdraw()
            self._hidden = True
        else:
            self.destroy()
    def _start_tray(self):
        img  = _make_tray_icon()
        menu = pystray.Menu(
            pystray.MenuItem("Open IntelliGuard", self._restore_from_tray, default=True),
            pystray.MenuItem("Exit",              self._quit_app)
        )
        self._tray = pystray.Icon("IntelliGuard", img, "IntelliGuard Active", menu)
        self._tray.run()
    def _restore_from_tray(self, icon=None, item=None):
        self.after(0, self._do_restore)
    def _do_restore(self):
        self.deiconify()
        self.lift()
        self._hidden = False
    def _quit_app(self, icon=None, item=None):
        if self._tray:
            self._tray.stop()
        self.after(0, self.destroy)
    def _initialize_engine(self):
        self._log("[SYS]  Booting IntelliGuard Core Engine …")
        self.engine = IntelliGuardEnsemble()
        self._log("[SYS]  XGBoost Expert Ensemble loaded  (Kaggle · BODMAS · EMBER)")
        self._log("[SYS]  Score Calibration Layer          →  ACTIVE")
        self._log("[SYS]  Majority Vote Gate               →  ARMED")
        self._log("[SYS]  Late-Fusion Voting Module        →  ARMED")
        self._log("[SYS]  ─────────────────────────────────────────────")
        self._log("[RDY]  System online. Drop a target to begin.")
        self.after(0, lambda: self.dot.set_color(C["green"]))
        self.after(0, lambda: self.status_lbl.configure(
            text="ONLINE  ·  MONITORING", text_color=C["green"]))
        self.after(0, lambda: self.scan_btn.configure(state="normal"))
    def _build_ui(self):
        header = ctk.CTkFrame(self, fg_color=C["bg_card"],
                              corner_radius=0, height=54,
                              border_width=1, border_color=C["border2"])
        header.pack(fill="x", side="top")
        header.pack_propagate(False)
        ctk.CTkLabel(header, text="⬡ INTELLIGUARD",
                     font=_f("title"), text_color=C["accent"]).pack(
                     side="left", padx=20, pady=8)
        ctk.CTkLabel(header, text="AI THREAT INTELLIGENCE PLATFORM  v3.0",
                     font=_f("label"), text_color=C["txt_sec"]).pack(
                     side="left", pady=8)
        stats = ctk.CTkFrame(header, fg_color="transparent")
        stats.pack(side="right", padx=14, pady=6)
        self.card_scanned = StatCard(stats, "SCANNED", "0", C["accent"])
        self.card_scanned.pack(side="left", padx=5)
        self.card_threats = StatCard(stats, "THREATS", "0", C["red"])
        self.card_threats.pack(side="left", padx=5)
        self.card_engine  = StatCard(stats, "ENGINE", "XGB ×3", C["accent2"])
        self.card_engine.pack(side="left", padx=5)
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)
        sidebar = ctk.CTkFrame(body, width=220, fg_color=C["bg_card"],
                               corner_radius=0,
                               border_width=1, border_color=C["border2"])
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        ctk.CTkLabel(sidebar, text="CONTROL PANEL",
                     font=_f("label"), text_color=C["txt_sec"]).pack(
                     pady=(20, 3), padx=14, anchor="w")
        ctk.CTkFrame(sidebar, height=1, fg_color=C["accent"]).pack(
            fill="x", padx=14, pady=(0, 14))
        self.scan_btn = ctk.CTkButton(
            sidebar, text="▸  SELECT FILE",
            command=self.browse_file,
            height=42, font=_f("btn"),
            fg_color=C["accent"], hover_color="#00aacc",
            text_color=C["bg_deep"], corner_radius=6, state="disabled")
        self.scan_btn.pack(pady=(0, 8), padx=14, fill="x")
        self.clear_btn = ctk.CTkButton(
            sidebar, text="↺  CLEAR LOG",
            command=self._clear_console,
            height=34, font=_f("btn"),
            fg_color=C["bg_hover"], hover_color=C["border2"],
            text_color=C["txt_sec"], corner_radius=6,
            border_width=1, border_color=C["border2"])
        self.clear_btn.pack(pady=(0, 16), padx=14, fill="x")
        ctk.CTkLabel(sidebar, text="EXPERT MODELS",
                     font=_f("label"), text_color=C["txt_sec"]).pack(
                     pady=(0, 3), padx=14, anchor="w")
        ctk.CTkFrame(sidebar, height=1, fg_color=C["border2"]).pack(
            fill="x", padx=14, pady=(0, 10))
        for name, dataset in [("Expert α", "KAGGLE"),
                               ("Expert β", "BODMAS"),
                               ("Expert γ", "EMBER")]:
            row = ctk.CTkFrame(sidebar, fg_color=C["bg_mid"], corner_radius=5)
            row.pack(fill="x", padx=14, pady=2)
            ctk.CTkLabel(row, text=name, font=_f("mono"),
                         text_color=C["accent2"]).pack(side="left", padx=8, pady=5)
            ctk.CTkLabel(row, text=dataset, font=_f("label"),
                         text_color=C["txt_sec"]).pack(side="right", padx=8)
        ctk.CTkFrame(sidebar, height=1, fg_color=C["border2"]).pack(
            fill="x", padx=14, pady=(12, 8))
        ctk.CTkLabel(sidebar, text="ACTIVE PROTECTIONS",
                     font=_f("label"), text_color=C["txt_sec"]).pack(
                     padx=14, anchor="w")
        prot_box = ctk.CTkFrame(sidebar, fg_color=C["bg_mid"], corner_radius=5)
        prot_box.pack(fill="x", padx=14, pady=(4, 0))
        for prot in ["Majority Vote Gate", "Score Calibration", "Trusted Publishers",
                     "System Dir Bypass", "Download Monitor"]:
            ctk.CTkLabel(prot_box, text=f"  ✓  {prot}", font=_f("label"),
                         text_color=C["green"], anchor="w").pack(
                         fill="x", padx=4, pady=1)
        s_row = ctk.CTkFrame(sidebar, fg_color="transparent")
        s_row.pack(side="bottom", pady=16, padx=14, anchor="w")
        self.dot = PulsingDot(s_row, color=C["amber"])
        self.dot.pack(side="left", padx=(0, 6))
        self.status_lbl = ctk.CTkLabel(s_row, text="BOOTING …",
                                       font=_f("mono"), text_color=C["amber"])
        self.status_lbl.pack(side="left")
        main = ctk.CTkFrame(body, fg_color=C["bg_mid"], corner_radius=0)
        main.pack(side="right", fill="both", expand=True)
        top = ctk.CTkFrame(main, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=(16, 8))
        radar_card = ctk.CTkFrame(top, fg_color=C["bg_card"],
                                  corner_radius=8,
                                  border_width=1, border_color=C["border2"])
        radar_card.pack(side="left", padx=(0, 12))
        ctk.CTkLabel(radar_card, text="RADAR",
                     font=_f("label"), text_color=C["txt_sec"]).pack(pady=(8, 2))
        self.radar = RadarCanvas(radar_card, size=150, bg=C["bg_card"])
        self.radar.pack(padx=12, pady=(0, 10))
        verdict_card = ctk.CTkFrame(top, fg_color=C["bg_card"],
                                    corner_radius=8,
                                    border_width=1, border_color=C["border2"])
        verdict_card.pack(side="left", fill="both", expand=True)
        self.verdict_icon = ctk.CTkLabel(verdict_card, text="◈",
                                         font=_f("huge"),
                                         text_color=C["border2"])
        self.verdict_icon.pack(pady=(10, 0))
        self.verdict_lbl = ctk.CTkLabel(verdict_card,
                                        text="AWAITING TARGET",
                                        font=_f("verdict"),
                                        text_color=C["txt_sec"])
        self.verdict_lbl.pack()
        self.file_lbl = ctk.CTkLabel(verdict_card, text="No file selected",
                                     font=_f("label"), text_color=C["txt_sec"])
        self.file_lbl.pack(pady=(2, 0))
        self.reason_lbl = ctk.CTkLabel(verdict_card, text="",
                                       font=_f("label"), text_color=C["txt_sec"],
                                       wraplength=380)
        self.reason_lbl.pack(pady=(2, 0))
        self.score_lbl = ctk.CTkLabel(verdict_card, text="",
                                      font=_f("score"), text_color=C["txt_sec"])
        self.score_lbl.pack(pady=(2, 0))
        self.elapsed_lbl = ctk.CTkLabel(verdict_card, text="",
                                        font=_f("label"), text_color=C["txt_sec"])
        self.elapsed_lbl.pack(pady=(2, 8))
        votes_card = ctk.CTkFrame(main, fg_color=C["bg_card"],
                                  corner_radius=8,
                                  border_width=1, border_color=C["border2"])
        votes_card.pack(fill="x", padx=20, pady=(0, 8))
        ctk.CTkLabel(votes_card, text="ENSEMBLE VOTE BREAKDOWN",
                     font=_f("label"), text_color=C["txt_sec"]).pack(
                     pady=(8, 3), padx=14, anchor="w")
        ctk.CTkFrame(votes_card, height=1, fg_color=C["border2"]).pack(
            fill="x", padx=14, pady=(0, 6))
        self.vote_rows: dict[str, VoteRow] = {}
        for name in ["Expert α  (Kaggle)", "Expert β  (BODMAS)", "Expert γ  (EMBER)"]:
            vr = VoteRow(votes_card, model_name=name)
            vr.pack(fill="x", padx=14, pady=2)
            self.vote_rows[name] = vr
        ctk.CTkFrame(votes_card, height=0).pack(pady=3)
        t_header = ctk.CTkFrame(main, fg_color="transparent")
        t_header.pack(fill="x", padx=20, pady=(0, 3))
        ctk.CTkLabel(t_header, text="SYSTEM TERMINAL",
                     font=_f("label"), text_color=C["txt_sec"]).pack(side="left")
        self._cursor_vis = True
        self.cursor_lbl = ctk.CTkLabel(t_header, text="█",
                                       font=_f("mono"), text_color=C["accent"])
        self.cursor_lbl.pack(side="left", padx=4)
        self._blink_cursor()
        self.console = ctk.CTkTextbox(
            main, font=_f("mono"),
            fg_color=C["bg_deep"],
            text_color=C["txt_mono"],
            border_width=1, border_color=C["border2"],
            corner_radius=6,
            scrollbar_button_color=C["border2"],
            scrollbar_button_hover_color=C["bg_hover"],
            wrap="word"
        )
        self.console.pack(fill="both", expand=True, padx=20, pady=(0, 16))
        self.console.configure(state="disabled")
    def _blink_cursor(self):
        self._cursor_vis = not self._cursor_vis
        self.cursor_lbl.configure(text="█" if self._cursor_vis else " ")
        self.after(600, self._blink_cursor)
    def _log(self, text: str, delay_ms: int = 0):
        def _write():
            self.console.configure(state="normal")
            self.console.insert("end", "\n" + text)
            self.console.see("end")
            self.console.configure(state="disabled")
        self.after(delay_ms, _write)
    def _clear_console(self):
        self.console.configure(state="normal")
        self.console.delete("1.0", "end")
        self.console.configure(state="disabled")
    def _start_background_monitor(self):
        downloads = os.path.expanduser("~/Downloads")
        os.makedirs(downloads, exist_ok=True)
        self.observer = Observer()
        self.observer.schedule(DownloadHandler(self), downloads, recursive=False)
        self.observer.start()
        self.after(2500, lambda: self._log(
            f"[SYS]  🛡️  Download Monitor ACTIVE → {downloads}"))
        self.after(2500, lambda: self._log(
            "[SYS]  Watching: .exe .dll .sys .msi .scr .bat .cmd .com .pif .vbs .ps1 .jar"))
    def queue_scan(self, file_path: str, auto: bool = False):
        filename = os.path.basename(file_path)
        self.scan_queue.put(file_path)
        tag = "[AUTO]" if auto else "[MANUAL]"
        self._log(f"{tag}  Target queued: {filename}")
    def _scan_worker(self):
        while True:
            file_path = self.scan_queue.get()
            while self.is_scanning:
                time.sleep(0.3)
            self.is_scanning = True
            self._run_scan(file_path)
    def browse_file(self):
        fp = filedialog.askopenfilename(
            title="Select Binary to Analyse",
            filetypes=[("Executable", "*.exe"), ("DLL", "*.dll"),
                       ("All scannable", "*.exe *.dll *.sys *.msi *.bat *.cmd"),
                       ("All files", "*.*")]
        )
        if fp:
            self.queue_scan(fp)
    def _run_scan(self, file_path: str):
        filename = os.path.basename(file_path)
        try:
            fsize = os.path.getsize(file_path)
        except OSError:
            fsize = 0
        self.last_scanned_file = filename
        def _reset_ui():
            self.scan_btn.configure(state="disabled", text="⚙  ANALYSING …")
            self.verdict_icon.configure(text="◌", text_color=C["amber"])
            self.verdict_lbl.configure(text="SCANNING …", text_color=C["amber"])
            self.file_lbl.configure(text=filename, text_color=C["txt_sec"])
            self.reason_lbl.configure(text="")
            self.score_lbl.configure(text="")
            self.elapsed_lbl.configure(text="")
            for vr in self.vote_rows.values():
                vr.reset()
            self.radar.start()
            self.dot.set_color(C["amber"])
            self.status_lbl.configure(text="SCANNING", text_color=C["amber"])
        self.after(0, _reset_ui)
        self._log("")
        self._log(f"┌──── TARGET ────────────────────────────────────────")
        self._log(f"│  {filename[:52]}")
        self._log(f"│  Size: {fsize:,} bytes")
        self._log(f"└────────────────────────────────────────────────────")
        self._log("[*]  Extracting PE features …")
        t0      = time.time()
        result  = self.engine.scan_file(file_path)
        elapsed = time.time() - t0
        self.after(0, self.radar.stop)
        if result.get("status") == "error":
            self._log(f"[ERR] {result.get('message')}", delay_ms=100)
            self.after(200, lambda: self.verdict_icon.configure(
                text="⚠", text_color=C["amber"]))
            self.after(200, lambda: self.verdict_lbl.configure(
                text="ANALYSIS FAILED", text_color=C["amber"]))
            self.after(200, lambda: self.dot.set_color(C["amber"]))
            self.after(200, lambda: self.status_lbl.configure(
                text="ERROR", text_color=C["amber"]))
            self.after(800, lambda: self.scan_btn.configure(
                state="normal", text="▸  SELECT FILE"))
            self.after(800, lambda: setattr(self, "is_scanning", False))
            return
        votes   = result.get("votes", {})
        verdict = result.get("verdict", "UNKNOWN")
        trusted = result.get("trusted_publisher", False)
        fused   = result.get("fused_score", 0.0)
        reason  = result.get("verdict_reason", "")
        is_signed = result.get("is_signed", False)
        signer  = result.get("signer", "")
        if is_signed:
            self._log(f"[SIG]  🔏 Signed by: {signer[:60]}")
        else:
            self._log("[SIG]  ⚠️  No valid digital signature")
        if trusted:
            self._log(f"[TRU]  🛡️  Trusted Publisher — inference skipped")
        row_keys   = list(self.vote_rows.keys())
        vote_items = list(votes.items())
        total_delay = 200
        for idx, (model_key, data) in enumerate(vote_items):
            delay  = 250 + idx * 200
            vr_key = row_keys[idx] if idx < len(row_keys) else None
            status = data.get("status", "")
            if status == "TRUSTED":
                icon, label = "🛡️", "TRUSTED"
                self._log(f"  {icon}  [{model_key}] → {label}", delay_ms=delay)
                if vr_key:
                    self.vote_rows[vr_key].set_trusted(delay_ms=delay + 50)
            elif status == "SKIPPED":
                icon, label = "⏭️", "SKIPPED"
                cov = data.get("match_ratio", 0) * 100
                self._log(f"  {icon}  [{model_key}] → {label}  (coverage {cov:.0f}%)",
                          delay_ms=delay)
                if vr_key:
                    self.vote_rows[vr_key].set_skipped(delay_ms=delay + 50)
            else:
                conf = data.get("confidence", 0.0)
                is_mal = bool(data.get("malware", False))
                cov  = data.get("match_ratio", 1.0)
                icon = "🔴" if is_mal else "🟢"
                label= "MALWARE" if is_mal else "SAFE"
                self._log(
                    f"  {icon}  [{model_key}] → {label}  "
                    f"(conf={conf*100:.1f}%, cov={cov*100:.0f}%)",
                    delay_ms=delay
                )
                if vr_key:
                    self.vote_rows[vr_key].animate_result(
                        is_mal, conf, cov, delay_ms=delay + 80)
            total_delay = delay + 200
        self._log(f"[*]  Fused score: {fused:.4f}", delay_ms=total_delay)
        self._log(f"[*]  Reason: {reason}", delay_ms=total_delay + 50)
        self._log(f"[*]  Scan completed in {elapsed:.2f}s", delay_ms=total_delay + 100)
        settle = total_delay + 350
        self.after(settle, lambda: self.elapsed_lbl.configure(
            text=f"scan time: {elapsed:.2f}s"))
        score_color = C["red"] if verdict == "MALWARE" else C["green"]
        self.after(settle, lambda: self.score_lbl.configure(
            text=f"Score: {fused:.3f}", text_color=score_color))
        self.after(settle, lambda: self.reason_lbl.configure(
            text=reason, text_color=C["txt_sec"]))
        active_malware_count = sum(
            1 for v in votes.values()
            if v.get("status") == "VOTED" and v.get("malware") is True
        )
        active_safe_count = sum(
            1 for v in votes.values()
            if v.get("status") == "VOTED" and v.get("malware") is False
        )
        sig_override = (verdict == "SAFE" and active_malware_count > 0
                        and active_malware_count >= active_safe_count and is_signed)
        if verdict == "SAFE" and sig_override:
            self.after(settle + 100, self._show_safe_sig_override)
        elif verdict == "SAFE":
            self.after(settle + 100, self._show_safe)
        elif verdict == "MALWARE":
            self.after(settle + 100, self._show_malware)
        else:
            self.after(settle + 100, lambda: self.verdict_lbl.configure(
                text="UNKNOWN", text_color=C["amber"]))
        self._scan_count += 1
        if verdict == "MALWARE":
            self._threat_count += 1
        self.after(settle, lambda: self.card_scanned.update_value(str(self._scan_count)))
        self.after(settle, lambda: self.card_threats.update_value(str(self._threat_count)))
        final_settle = settle + 600
        self.after(final_settle, lambda: self.scan_btn.configure(
            state="normal", text="▸  SELECT FILE"))
        self.after(final_settle, lambda: self.dot.set_color(C["green"]))
        self.after(final_settle, lambda: self.status_lbl.configure(
            text="ONLINE  ·  MONITORING", text_color=C["green"]))
        self.after(final_settle, lambda: setattr(self, "is_scanning", False))
    def _show_safe(self):
        filename = getattr(self, "last_scanned_file", "File")
        self.verdict_icon.configure(text="✓", text_color=C["green"])
        self.verdict_lbl.configure(text="FILE IS SAFE", text_color=C["green"])
        self._log("════════════════════════════════════════════════════")
        self._log("  VERDICT  →  ✓  SAFE — no threat detected          ")
        self._log("════════════════════════════════════════════════════")
        try:
            notification.notify(title="IntelliGuard: SAFE",
                                 message=f"{filename} passed all checks.",
                                 timeout=3)
        except Exception:
            pass
    def _show_safe_sig_override(self):
        filename = getattr(self, "last_scanned_file", "File")
        self.verdict_icon.configure(text="⚠", text_color=C["amber"])
        self.verdict_lbl.configure(text="SAFE — SIG OVERRIDE", text_color=C["amber"])
        self._log("════════════════════════════════════════════════════")
        self._log("  VERDICT  →  ⚠  SAFE (Signature Override)          ")
        self._log("  Models flagged as suspicious BUT CA signature      ")
        self._log("  trust overrides — treat with caution.              ")
        self._log("  Consider verifying the publisher independently.    ")
        self._log("════════════════════════════════════════════════════")
        try:
            notification.notify(
                title="IntelliGuard: Caution",
                message=f"{filename}: Safe via signature — models were suspicious. Verify publisher.",
                timeout=5)
        except Exception:
            pass
    def _show_malware(self):
        filename = getattr(self, "last_scanned_file", "File")
        self.verdict_icon.configure(text="☠", text_color=C["red"])
        self.verdict_lbl.configure(text="THREAT DETECTED", text_color=C["red"])
        self._log("════════════════════════════════════════════════════")
        self._log("  VERDICT  →  ☠  MALWARE DETECTED                   ")
        self._log("  ⚠  DO NOT EXECUTE — QUARANTINE IMMEDIATELY         ")
        self._log("════════════════════════════════════════════════════")
        try:
            notification.notify(title="⚠ IntelliGuard: THREAT",
                                 message=f"Malware detected in {filename}!",
                                 timeout=6)
        except Exception:
            pass
if __name__ == "__main__":
    app = IntelliGuardApp()
    app.mainloop()
