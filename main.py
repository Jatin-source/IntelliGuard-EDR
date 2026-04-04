import os
import sys
import time
import math
import queue
import random
import threading
import tkinter as tk
from tkinter import filedialog
from pathlib import Path
import customtkinter as ctk
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from plyer import notification

# PIL for logo/image support
from PIL import Image as PILImage, ImageDraw

# Tray Support
try:
    import pystray
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False

# Live Execution Monitor Support
try:
    import psutil  # type: ignore[import]
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

_project_root = str(Path(__file__).resolve().parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
from src.detector.ensemble import IntelliGuardEnsemble

# ── Appearance ──────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

# ── Industry Security Color Palette ─────────────────────────────────────
C = {
    "bg_deep":       "#040810",
    "bg_mid":        "#0a0f1a",
    "bg_card":       "#0f1520",
    "bg_hover":      "#162030",
    "border":        "#1a2438",
    "border2":       "#243350",
    "accent":        "#00a8e8",
    "accent_dim":    "#007bb5",
    "accent2":       "#6c63ff",
    "accent2_dim":   "#524acc",
    "green":         "#00c853",
    "green_dim":     "#00893a",
    "amber":         "#ffa726",
    "red":           "#ef5350",
    "red_dim":       "#c62828",
    "txt_pri":       "#dce4f0",
    "txt_sec":       "#556b8a",
    "txt_mono":      "#4db8d9",
    "safe_bg":       "#071a10",
    "danger_bg":     "#1a0a0a",
    "warn_bg":       "#1a1508",
    "safe_glow":     "#00c853",
    "danger_glow":   "#ef5350",
    "header_line":   "#00a8e8",
    "shield_bg":     "#0c1a2e",
}

# ── Font Factory ────────────────────────────────────────────────────────
_FONTS: dict = {}
_UI_FAMILY = "Segoe UI"
_MONO_FAMILY = "Consolas"

def _f(key: str) -> ctk.CTkFont:
    if key not in _FONTS:
        _FONTS[key] = {
            "title":     lambda: ctk.CTkFont(family=_UI_FAMILY, size=24, weight="bold"),
            "head":      lambda: ctk.CTkFont(family=_UI_FAMILY, size=15, weight="bold"),
            "body":      lambda: ctk.CTkFont(family=_UI_FAMILY, size=13),
            "mono":      lambda: ctk.CTkFont(family=_MONO_FAMILY, size=13),
            "mono_sm":   lambda: ctk.CTkFont(family=_MONO_FAMILY, size=12),
            "huge":      lambda: ctk.CTkFont(family=_UI_FAMILY, size=64, weight="bold"),
            "verdict":   lambda: ctk.CTkFont(family=_UI_FAMILY, size=30, weight="bold"),
            "label":     lambda: ctk.CTkFont(family=_UI_FAMILY, size=11),
            "label_sm":  lambda: ctk.CTkFont(family=_UI_FAMILY, size=10),
            "label_xs":  lambda: ctk.CTkFont(family=_UI_FAMILY, size=9, slant="italic"),
            "btn":       lambda: ctk.CTkFont(family=_UI_FAMILY, size=14, weight="bold"),
            "score":     lambda: ctk.CTkFont(family=_MONO_FAMILY, size=19, weight="bold"),
            "pill":      lambda: ctk.CTkFont(family=_UI_FAMILY, size=10, weight="bold"),
            "section":   lambda: ctk.CTkFont(family=_UI_FAMILY, size=11, weight="bold"),
        }[key]()
    return _FONTS[key]

# ═══════════════════════════════════════════════════════════════════════
#  CUSTOM WIDGETS
# ═══════════════════════════════════════════════════════════════════════

class GradientLine(tk.Canvas):
    def __init__(self, master, height=2, color_left="#00bfff", color_right="#7c5cff", **kw):
        bg = kw.pop("bg", C["bg_card"])
        super().__init__(master, height=height, bg=bg, highlightthickness=0, **kw)
        self._c1, self._c2 = color_left, color_right
        self.bind("<Configure>", self._draw)

    def _draw(self, event=None):
        self.delete("all")
        w = self.winfo_width()
        if w < 2: return
        steps = min(w, 120)
        seg_w = max(w / steps, 1)
        r1, g1, b1 = int(self._c1[1:3], 16), int(self._c1[3:5], 16), int(self._c1[5:7], 16)
        r2, g2, b2 = int(self._c2[1:3], 16), int(self._c2[3:5], 16), int(self._c2[5:7], 16)
        for i in range(steps):
            t = i / steps
            r, g, b = int(r1 + (r2 - r1) * t), int(g1 + (g2 - g1) * t), int(b1 + (b2 - b1) * t)
            self.create_rectangle(int(i * seg_w), 0, int((i + 1) * seg_w), self.winfo_height(), 
                                  fill=f"#{r:02x}{g:02x}{b:02x}", outline="")

class RadarCanvas(tk.Canvas):
    TRAIL_STEPS, FPS_MS = 14, 70
    def __init__(self, master, size=170, **kwargs):
        bg = kwargs.pop("bg", C["bg_card"])
        super().__init__(master, width=size, height=size, bg=bg, highlightthickness=0, **kwargs)
        self.cx = self.cy = size // 2
        self.r = size // 2 - 10
        self.angle = 0
        self._active, self._after_id, self._pings = False, None, []
        self._build_static()
        self._build_sweep()

    def _build_static(self):
        cx, cy, r = self.cx, self.cy, self.r
        for i in range(3):
            ri = r + 3 - i
            self.create_oval(cx - ri, cy - ri, cx + ri, cy + ri, outline=["#0d1a22", "#0a1520", "#081018"][i], width=1)
        for i in range(1, 4):
            ri = int(r * i / 3)
            self.create_oval(cx - ri, cy - ri, cx + ri, cy + ri, outline=C["border2"], dash=(2, 4))
        self.create_line(cx, cy - r, cx, cy + r, fill=C["border"], dash=(3, 5))
        self.create_line(cx - r, cy, cx + r, cy, fill=C["border"], dash=(3, 5))
        self.create_oval(cx - 4, cy - 4, cx + 4, cy + 4, fill=C["accent"], outline=C["accent_dim"], tags="dot")

    def _build_sweep(self):
        cx, cy = self.cx, self.cy
        self._trail_ids = [self.create_line(cx, cy, cx, cy, fill=C["border"]) for _ in range(self.TRAIL_STEPS)]
        self._arm_id = self.create_line(cx, cy, cx, cy, fill=C["accent"], width=2)

    @staticmethod
    def _blend(hex1, hex2, t):
        r1, g1, b1 = int(hex1[1:3], 16), int(hex1[3:5], 16), int(hex1[5:7], 16)
        r2, g2, b2 = int(hex2[1:3], 16), int(hex2[3:5], 16), int(hex2[5:7], 16)
        return f"#{int(r1+(r2-r1)*t):02x}{int(g1+(g2-g1)*t):02x}{int(b1+(b2-b1)*t):02x}"

    def start(self):
        self._active = True
        self._sweep()

    def stop(self):
        self._active = False
        if self._after_id: self.after_cancel(self._after_id)
        cx, cy = self.cx, self.cy
        for lid in self._trail_ids: self.coords(lid, cx, cy, cx, cy)
        self.coords(self._arm_id, cx, cy, cx, cy)
        for pid in self._pings: self.delete(pid)
        self._pings.clear()

    def _sweep(self):
        if not self._active: return
        cx, cy, r, N = self.cx, self.cy, self.r, self.TRAIL_STEPS
        for i, lid in enumerate(self._trail_ids):
            a = math.radians(self.angle - (N - i) * 3)
            self.coords(lid, cx, cy, cx + r * math.cos(a), cy - r * math.sin(a))
            self.itemconfig(lid, fill=self._blend(C["accent"], C["bg_card"], 1 - i / N))
        arm_rad = math.radians(self.angle)
        self.coords(self._arm_id, cx, cy, cx + r * math.cos(arm_rad), cy - r * math.sin(arm_rad))
        self.tag_raise("dot")
        if random.random() < 0.08: self._add_ping()
        self.angle = (self.angle + 4) % 360
        self._after_id = self.after(self.FPS_MS, self._sweep)

    def _add_ping(self):
        cx, cy, r = self.cx, self.cy, self.r
        dist, ang = random.uniform(0.15, 0.85) * r, random.uniform(0, 2 * math.pi)
        px, py = cx + dist * math.cos(ang), cy - dist * math.sin(ang)
        pid = self.create_oval(px - 3, py - 3, px + 3, py + 3, fill=C["accent"], outline="")
        self._pings.append(pid)
        self.after(800, lambda: self._remove_ping(pid))

    def _remove_ping(self, pid):
        try:
            self.delete(pid)
            if pid in self._pings: self._pings.remove(pid)
        except tk.TclError: pass

class PulsingDot(tk.Canvas):
    def __init__(self, master, color=C["amber"], size=14, **kwargs):
        bg = kwargs.pop("bg", C["bg_card"])
        super().__init__(master, width=size, height=size, bg=bg, highlightthickness=0, **kwargs)
        self._color, self._size, self._scale, self._growing = color, size, 1.0, False
        self._pulse()

    def set_color(self, color: str): self._color = color

    def _pulse(self):
        if self._scale >= 1.0: self._growing = False
        elif self._scale <= 0.4: self._growing = True
        self._scale = max(0.4, min(1.0, self._scale + (0.08 if self._growing else -0.08)))
        half, r = self._size / 2, (self._size / 2) * self._scale
        self.delete("all")
        self.create_oval(half - r - 2, half - r - 2, half + r + 2, half + r + 2, outline=self._color)
        self.create_oval(half - r, half - r, half + r, half + r, fill=self._color, outline="")
        self.after(120, self._pulse)

class StatCard(ctk.CTkFrame):
    def __init__(self, master, label: str, value: str, accent: str, click_callback=None, **kwargs):
        super().__init__(master, fg_color=C["bg_card"], corner_radius=8, border_width=1, border_color=C["border2"], **kwargs)
        self._accent = accent
        self._click_cb = click_callback
        self.configure(cursor="hand2")
        inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.pack(padx=16, pady=(8, 6))
        ctk.CTkLabel(inner, text=label, font=_f("label_sm"), text_color=C["txt_sec"]).pack()
        self.value_lbl = ctk.CTkLabel(inner, text=value, font=ctk.CTkFont(family=_MONO_FAMILY, size=18, weight="bold"), text_color=accent)
        self.value_lbl.pack(pady=(2, 0))
        self._bar = ctk.CTkFrame(self, height=2, fg_color="transparent", corner_radius=1)
        self._bar.pack(fill="x", padx=10, pady=(0, 5))
        
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        for child in self.winfo_children():
            child.bind("<Enter>", self._on_enter)
            child.bind("<Leave>", self._on_leave)
            child.bind("<Button-1>", self._on_click)

    def _on_enter(self, e=None):
        self.configure(border_color=self._accent)
        self._bar.configure(fg_color=self._accent)

    def _on_leave(self, e=None):
        self.configure(border_color=C["border2"])
        self._bar.configure(fg_color="transparent")

    def _on_click(self, e=None):
        if self._click_cb: self._click_cb()

    def update_value(self, value: str):
        try:
            target, current = int(value), int(self.value_lbl.cget("text")) if self.value_lbl.cget("text").isdigit() else 0
            if current < target:
                self._count_up(current, target, 0)
                return
        except (ValueError, AttributeError): pass
        self.value_lbl.configure(text=value)

    def _count_up(self, current, target, step):
        if current >= target:
            self.value_lbl.configure(text=str(target))
            return
        self.value_lbl.configure(text=str(current + 1))
        self.after(max(30, 150 - step * 20), lambda: self._count_up(current + 1, target, step + 1))

class VoteRow(ctk.CTkFrame):
    def __init__(self, master, model_name: str, dot_color: str = C["accent2"], **kwargs):
        # Increased height to accommodate the explanation layer
        super().__init__(master, fg_color=C["bg_mid"], corner_radius=8, border_width=1, border_color=C["border"], height=58, **kwargs)
        self.pack_propagate(False) # Keep fixed height
        
        # TOP FRAME (Progress bar, stats)
        self.top_frame = ctk.CTkFrame(self, fg_color="transparent", height=28)
        self.top_frame.pack(fill="x", padx=0, pady=(6, 0))
        
        self._dot_canvas = tk.Canvas(self.top_frame, width=10, height=10, bg=C["bg_mid"], highlightthickness=0)
        self._dot_canvas.pack(side="left", padx=(12, 0), pady=0)
        self._dot_canvas.create_oval(1, 1, 9, 9, fill=dot_color, outline="", tags="dot")
        self._dot_color = dot_color

        self.name_lbl = ctk.CTkLabel(self.top_frame, text=model_name, font=_f("mono_sm"), text_color=C["txt_sec"], width=155, anchor="w")
        self.name_lbl.pack(side="left", padx=(6, 0))

        self.verdict_lbl = ctk.CTkLabel(self.top_frame, text="WAITING", font=_f("mono_sm"), text_color=C["txt_sec"], width=80)
        self.verdict_lbl.pack(side="left", padx=6)

        self.bar = ctk.CTkProgressBar(self.top_frame, width=170, height=8, fg_color=C["border"], progress_color=C["txt_sec"], corner_radius=4)
        self.bar.set(0)
        self.bar.pack(side="left", padx=6)

        self.conf_lbl = ctk.CTkLabel(self.top_frame, text="--.--%", font=ctk.CTkFont(family=_MONO_FAMILY, size=11), text_color=C["txt_sec"], width=58, anchor="e")
        self.conf_lbl.pack(side="left", padx=(4, 6))

        self.cov_lbl = ctk.CTkLabel(self.top_frame, text="", font=_f("label_sm"), text_color=C["txt_sec"], width=58, anchor="e")
        self.cov_lbl.pack(side="left", padx=(0, 10))

        # BOTTOM FRAME (Explainability Logic)
        self.reason_lbl = ctk.CTkLabel(self, text="↳ Waiting for scan...", font=_f("label_xs"), text_color=C["txt_sec"], anchor="w")
        self.reason_lbl.pack(fill="x", padx=(32, 12), pady=(0, 4))

    def animate_result(self, is_malware: bool, confidence: float, match_ratio: float = 1.0, reason_text: str = "", delay_ms: int = 0):
        color, label = (C["red"], "MALWARE") if is_malware else (C["green"], "SAFE")
        def _start():
            self.verdict_lbl.configure(text=label, text_color=color)
            self.bar.configure(progress_color=color)
            self.conf_lbl.configure(text=f"{confidence * 100:.1f}%", text_color=color)
            self.cov_lbl.configure(text=f"cov:{match_ratio * 100:.0f}%", text_color=C["txt_sec"])
            self.reason_lbl.configure(text=reason_text, text_color=C["txt_pri"]) # Highlight reason
            self._dot_canvas.delete("dot")
            self._dot_canvas.create_oval(1, 1, 9, 9, fill=color, outline="", tags="dot")
            self._animate_bar(0, 20, confidence)
        self.after(delay_ms, _start)

    def set_state(self, state: str, color: str, reason_text: str = "", delay_ms: int = 0):
        def _start():
            self.verdict_lbl.configure(text=state, text_color=color)
            self.conf_lbl.configure(text="--", text_color=color)
            self.reason_lbl.configure(text=reason_text, text_color=C["txt_sec"])
            self._dot_canvas.delete("dot")
            self._dot_canvas.create_oval(1, 1, 9, 9, fill=color, outline="", tags="dot")
            if state == "TRUSTED":
                self.bar.set(0)
                self.bar.configure(progress_color=color)
        self.after(delay_ms, _start)

    def _animate_bar(self, step, total, target):
        if step <= total:
            self.bar.set((target / total) * step)
            self.after(22, lambda: self._animate_bar(step + 1, total, target))

    def reset(self):
        self.verdict_lbl.configure(text="WAITING", text_color=C["txt_sec"])
        self.bar.set(0)
        self.bar.configure(progress_color=C["txt_sec"])
        self.conf_lbl.configure(text="--.--%", text_color=C["txt_sec"])
        self.cov_lbl.configure(text="")
        self.reason_lbl.configure(text="↳ Waiting for scan...", text_color=C["txt_sec"])
        self._dot_canvas.delete("dot")
        self._dot_canvas.create_oval(1, 1, 9, 9, fill=self._dot_color, outline="", tags="dot")

# ═══════════════════════════════════════════════════════════════════════
#  DOWNLOAD MONITOR
# ═══════════════════════════════════════════════════════════════════════

_TEMP_EXT = {'.crdownload', '.tmp', '.partial', '.downloading', '.part', '.download'}
_SCAN_EXT = {'.exe', '.dll', '.sys', '.msi', '.scr', '.bat', '.cmd', '.com', '.pif', '.vbs', '.ps1', '.jar', '.hta', '.wsf'}

class DownloadHandler(FileSystemEventHandler):
    def __init__(self, app):
        super().__init__()
        self.app, self._pending, self._lock = app, set(), threading.Lock()

    def on_created(self, event):
        if not event.is_directory: self._check(event.src_path)
    def on_moved(self, event):
        if not event.is_directory: self._check(event.dest_path)

    def _check(self, path: str):
        ext = os.path.splitext(path)[1].lower()
        if ext not in _TEMP_EXT and ext in _SCAN_EXT:
            self._wait_and_queue(path)

    def _wait_and_queue(self, file_path: str):
        with self._lock:
            if file_path in self._pending: return
            self._pending.add(file_path)

        def _worker():
            try:
                prev_size: int = -1
                stable: int = 0
                for _ in range(120):
                    try: cur = os.path.getsize(file_path)
                    except OSError: 
                        time.sleep(0.5)
                        continue
                    if cur == prev_size and cur > 0:
                        stable += 1 
                        if stable >= 3: break
                    else: stable = 0
                    prev_size = cur
                    time.sleep(0.5)
                try:
                    with open(file_path, 'rb') as f: f.read(1)
                except (OSError, PermissionError): return
                self.app.queue_scan(file_path, auto=True)
            finally:
                with self._lock: self._pending.discard(file_path)
        threading.Thread(target=_worker, daemon=True).start()

# ═══════════════════════════════════════════════════════════════════════
#  SYSTEM TRAY
# ═══════════════════════════════════════════════════════════════════════

def _make_tray_icon():
    img = PILImage.new("RGBA", (64, 64), (0, 0, 0, 0))
    ImageDraw.Draw(img).polygon([(32, 4), (58, 16), (58, 36), (32, 60), (6, 36), (6, 16)], fill=(0, 191, 255, 220), outline=(0, 136, 187, 255))
    return img

# ═══════════════════════════════════════════════════════════════════════
#  MAIN APPLICATION
# ═══════════════════════════════════════════════════════════════════════

class IntelliGuardApp(ctk.CTk):
    # Path to logo assets
    _LOGO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
    _LOGO_PNG = os.path.join(_LOGO_DIR, "logo.png")
    _LOGO_ICO = os.path.join(_LOGO_DIR, "logo.ico")

    def __init__(self):
        super().__init__()
        # On Windows, set the AppUserModelID so the taskbar groups this app separately from python.exe
        if os.name == 'nt':
            try:
                import ctypes
                myappid = 'intelliguard.threat.intelligence.3.0'
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
            except Exception:
                pass

        self.title("IntelliGuard  ·  AI Threat Intelligence  ·  v3.0")
        self.resizable(True, True)
        self.configure(fg_color=C["bg_deep"])

        # Taskbar / title-bar icon (wm_iconphoto works reliably for taskbar)
        if os.path.isfile(self._LOGO_PNG):
            from PIL import ImageTk
            _icon_img = PILImage.open(self._LOGO_PNG).convert("RGBA")
            self._taskbar_icon = ImageTk.PhotoImage(_icon_img.resize((64, 64), PILImage.LANCZOS))
            self._taskbar_icon_lg = ImageTk.PhotoImage(_icon_img.resize((256, 256), PILImage.LANCZOS))
            self.wm_iconphoto(True, self._taskbar_icon_lg, self._taskbar_icon)

        self.engine, self.is_scanning, self._scan_count, self._threat_count = None, False, 0, 0
        self.scan_queue, self._tray, self._hidden, self._scan_anim_id = queue.Queue(), None, False, None

        # Build UI while window is default size (not yet shown to user)
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Now maximize — use attributes to prevent any small-window flash
        self.geometry("1280x780")  # fallback restore size
        self.state("zoomed")

        threading.Thread(target=self._initialize_engine, daemon=True).start()
        threading.Thread(target=self._scan_worker, daemon=True).start()
        
        self._start_background_monitor()
        self._start_execution_monitor()
        
        if TRAY_AVAILABLE: threading.Thread(target=self._start_tray, daemon=True).start()

    # ── Window / Tray ───────────────────────────────────────────────────
    def _on_close(self):
        if TRAY_AVAILABLE and self._tray:
            self.withdraw()
            self._hidden = True
        else: self.destroy()

    def _start_tray(self):
        # Use actual logo for tray if available
        if os.path.isfile(self._LOGO_PNG):
            tray_img = PILImage.open(self._LOGO_PNG).convert("RGBA").resize((64, 64), PILImage.LANCZOS)
        else:
            tray_img = _make_tray_icon()
        menu = pystray.Menu(pystray.MenuItem("Open IntelliGuard", self._restore_from_tray, default=True), pystray.MenuItem("Exit", self._quit_app))
        self._tray = pystray.Icon("IntelliGuard", tray_img, "IntelliGuard Active", menu)
        self._tray.run()

    def _restore_from_tray(self, icon=None, item=None): self.after(0, self._do_restore)
    def _do_restore(self): self.deiconify(); self.lift(); self._hidden = False
    def _quit_app(self, icon=None, item=None): 
        if self._tray: self._tray.stop()
        self.after(0, self.destroy)

    # ── Engine Init ─────────────────────────────────────────────────────
    def _initialize_engine(self):
        self._log("[SYS]  Booting IntelliGuard Core Engine …")
        self.engine = IntelliGuardEnsemble()
        self._log("[SYS]  Quad-Core AI Ensemble loaded (Kaggle · BODMAS · EMBER · Quo Vadis)")
        self._log("[SYS]  Dynamic Behavioral Proxy            →  ACTIVE")
        self._log("[SYS]  Late-Fusion Voting Module           →  ARMED")
        self._log("[SYS]  ─────────────────────────────────────────────")
        self._log("[RDY]  System online. Drop a target to begin.")
        self.after(0, lambda: self.dot.set_color(C["green"]))
        self.after(0, lambda: self.status_lbl.configure(text="ONLINE  ·  MONITORING", text_color=C["green"]))
        self.after(0, lambda: self.scan_btn.configure(state="normal"))
        self.after(0, self._start_btn_pulse)

    # ── Build UI ────────────────────────────────────────────────────────
    def _build_ui(self):
        # HEADER — no fixed height, auto-expands to fit stat cards
        header_wrap = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        header_wrap.pack(fill="x", side="top")
        header = ctk.CTkFrame(header_wrap, fg_color=C["bg_card"], corner_radius=0, border_width=0)
        header.pack(fill="x")

        brand_frame = ctk.CTkFrame(header, fg_color="transparent")
        brand_frame.pack(side="left", padx=(20, 0), pady=10)
        # App logo from image file
        if os.path.isfile(self._LOGO_PNG):
            _logo_pil = PILImage.open(self._LOGO_PNG).convert("RGBA")
            self._logo_img = ctk.CTkImage(light_image=_logo_pil, dark_image=_logo_pil, size=(36, 36))
            ctk.CTkLabel(brand_frame, image=self._logo_img, text="").pack(side="left", padx=(0, 8))
        else:
            ctk.CTkLabel(brand_frame, text="🛡", font=ctk.CTkFont(size=22), text_color=C["accent"]).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(brand_frame, text="INTELLIGUARD", font=_f("title"), text_color=C["accent"]).pack(side="left")

        pill = ctk.CTkFrame(brand_frame, fg_color=C["shield_bg"], corner_radius=8, border_width=1, border_color=C["accent_dim"], width=42, height=20)
        pill.pack(side="left", padx=(8, 0), pady=2)
        pill.pack_propagate(False)
        ctk.CTkLabel(pill, text="v3.0", font=_f("pill"), text_color=C["accent"]).pack(expand=True)

        ctk.CTkFrame(header, width=1, height=32, fg_color=C["border2"], corner_radius=0).pack(side="left", padx=(12, 12))
        subtitle_frame = ctk.CTkFrame(header, fg_color="transparent")
        subtitle_frame.pack(side="left", pady=10)
        ctk.CTkLabel(subtitle_frame, text="QUAD-CORE AI THREAT PLATFORM", font=_f("label"), text_color=C["txt_sec"]).pack(anchor="w")
        ctk.CTkLabel(subtitle_frame, text="Enterprise Security Suite", font=_f("label_sm"), text_color=C["border2"]).pack(anchor="w")

        stats = ctk.CTkFrame(header, fg_color="transparent")
        stats.pack(side="right", padx=20, pady=8)
        self.card_scanned = StatCard(stats, "SCANNED", "0", C["accent"], click_callback=self._show_scan_details)
        self.card_scanned.pack(side="left", padx=5)
        self.card_threats = StatCard(stats, "THREATS", "0", C["red"], click_callback=self._show_threat_details)
        self.card_threats.pack(side="left", padx=5)
        self.card_engine  = StatCard(stats, "ENGINE", "XGB ×4", C["accent2"], click_callback=self._show_engine_details)
        self.card_engine.pack(side="left", padx=5)

        GradientLine(header_wrap, height=2, color_left=C["accent"], color_right=C["accent2"], bg=C["bg_deep"]).pack(fill="x")

        # BODY
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)

        # SIDEBAR
        sidebar = ctk.CTkFrame(body, width=270, fg_color=C["bg_card"], corner_radius=0, border_width=0)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        ctk.CTkFrame(body, width=1, fg_color=C["border2"], corner_radius=0).pack(side="left", fill="y")

        self._sidebar_section(sidebar, "CONTROL PANEL", C["accent"], top_pad=18)
        self.scan_btn = ctk.CTkButton(sidebar, text="▸  SELECT FILE", command=self.browse_file, height=48, font=_f("btn"),
                                      fg_color=C["accent"], hover_color=C["accent_dim"], text_color=C["bg_deep"], corner_radius=10, state="disabled")
        self.scan_btn.pack(pady=(0, 8), padx=18, fill="x")
        self.clear_btn = ctk.CTkButton(sidebar, text="↺  CLEAR LOG", command=self._clear_console, height=38, font=_f("btn"),
                                       fg_color=C["bg_hover"], hover_color=C["border2"], text_color=C["txt_sec"], corner_radius=10, border_width=1, border_color=C["border2"])
        self.clear_btn.pack(pady=(0, 18), padx=18, fill="x")

        self._sidebar_section(sidebar, "EXPERT MODELS", C["accent2"])
        expert_data = [("Expert α", "KAGGLE",  C["accent"]), ("Expert β", "BODMAS",  C["accent2"]),
                       ("Expert γ", "EMBER",   C["green"]), ("Expert δ", "QUO VADIS", C["red"])]
        self._expert_rows = []
        for name, dataset, dot_c in expert_data:
            row = ctk.CTkFrame(sidebar, fg_color=C["bg_mid"], corner_radius=8, border_width=1, border_color=C["bg_mid"], cursor="hand2")
            row.pack(fill="x", padx=18, pady=2)
            dot_cv = tk.Canvas(row, width=10, height=10, bg=C["bg_mid"], highlightthickness=0)
            dot_cv.pack(side="left", padx=(12, 0), pady=8)
            dot_cv.create_oval(1, 1, 9, 9, fill=dot_c, outline="")
            ctk.CTkLabel(row, text=name, font=_f("mono_sm"), text_color=C["txt_pri"]).pack(side="left", padx=(6, 0), pady=6)
            ds_pill = ctk.CTkFrame(row, fg_color=C["bg_card"], corner_radius=6, border_width=1, border_color=C["border2"])
            ds_pill.pack(side="right", padx=10, pady=4)
            ctk.CTkLabel(ds_pill, text=dataset, font=_f("label_sm"), text_color=C["txt_sec"]).pack(padx=8, pady=2)
            _dc = dot_c
            row.bind("<Enter>", lambda e, r=row, c=_dc: r.configure(border_color=c))
            row.bind("<Leave>", lambda e, r=row: r.configure(border_color=C["bg_mid"]))
            row.bind("<Button-1>", lambda e, n=name, d=dataset: self._show_expert_info(n, d))
            self._expert_rows.append(row)

        self._sidebar_section(sidebar, "ACTIVE PROTECTIONS", C["green"], top_pad=14)
        prot_box = ctk.CTkFrame(sidebar, fg_color=C["bg_mid"], corner_radius=8)
        prot_box.pack(fill="x", padx=18, pady=(0, 0))
        for prot in ["Majority Vote Gate", "Trusted Publishers", "System Dir Bypass", "Download Monitor", "Live Process Watcher"]:
            pr = ctk.CTkFrame(prot_box, fg_color="transparent")
            pr.pack(fill="x", padx=10, pady=2)
            dot_cv = tk.Canvas(pr, width=8, height=8, bg=C["bg_mid"], highlightthickness=0)
            dot_cv.pack(side="left", padx=(2, 0), pady=5)
            dot_cv.create_oval(0, 0, 6, 6, fill=C["green_dim"], outline="")
            ctk.CTkLabel(pr, text=prot, font=_f("label"), text_color=C["green_dim"], anchor="w").pack(side="left", padx=(6, 0))

        s_row = ctk.CTkFrame(sidebar, fg_color="transparent")
        s_row.pack(side="bottom", pady=18, padx=16, anchor="w")
        self.dot = PulsingDot(s_row, color=C["amber"], bg=C["bg_card"])
        self.dot.pack(side="left", padx=(0, 8))
        status_text_frame = ctk.CTkFrame(s_row, fg_color="transparent")
        status_text_frame.pack(side="left")
        ctk.CTkLabel(status_text_frame, text="System ▸", font=_f("label_sm"), text_color=C["txt_sec"]).pack(anchor="w")
        self.status_lbl = ctk.CTkLabel(status_text_frame, text="BOOTING …", font=_f("mono_sm"), text_color=C["amber"])
        self.status_lbl.pack(anchor="w")

        # MAIN PANEL
        main = ctk.CTkFrame(body, fg_color=C["bg_mid"], corner_radius=0)
        main.pack(side="right", fill="both", expand=True)

        top = ctk.CTkFrame(main, fg_color="transparent")
        top.pack(fill="x", padx=24, pady=(14, 8))

        radar_card = ctk.CTkFrame(top, fg_color=C["bg_card"], corner_radius=10, border_width=1, border_color=C["border2"])
        radar_card.pack(side="left", padx=(0, 12))
        ctk.CTkLabel(radar_card, text="THREAT RADAR", font=_f("label_sm"), text_color=C["txt_sec"]).pack(pady=(10, 2))
        self.radar = RadarCanvas(radar_card, size=190, bg=C["bg_card"])
        self.radar.pack(padx=12, pady=(0, 10))

        self.verdict_card = ctk.CTkFrame(top, fg_color=C["bg_card"], corner_radius=10, border_width=1, border_color=C["border2"])
        self.verdict_card.pack(side="left", fill="both", expand=True)
        self.verdict_icon = ctk.CTkLabel(self.verdict_card, text="◈", font=_f("huge"), text_color=C["border2"])
        self.verdict_icon.pack(pady=(12, 0))
        self.verdict_lbl = ctk.CTkLabel(self.verdict_card, text="AWAITING TARGET", font=_f("verdict"), text_color=C["txt_sec"])
        self.verdict_lbl.pack()
        self.file_lbl = ctk.CTkLabel(self.verdict_card, text="No file selected", font=_f("label"), text_color=C["txt_sec"])
        self.file_lbl.pack(pady=(3, 0))
        self.reason_lbl = ctk.CTkLabel(self.verdict_card, text="", font=_f("label"), text_color=C["txt_sec"], wraplength=560)
        self.reason_lbl.pack(pady=(2, 0))
        self.score_lbl = ctk.CTkLabel(self.verdict_card, text="", font=_f("score"), text_color=C["txt_sec"])
        self.score_lbl.pack(pady=(3, 0))
        self.elapsed_lbl = ctk.CTkLabel(self.verdict_card, text="", font=_f("label_sm"), text_color=C["txt_sec"])
        self.elapsed_lbl.pack(pady=(2, 8))

        # Ensemble Votes (With Explainability Heights)
        votes_card = ctk.CTkFrame(main, fg_color=C["bg_card"], corner_radius=10, border_width=1, border_color=C["border2"])
        votes_card.pack(fill="x", padx=24, pady=(0, 8))
        votes_header = ctk.CTkFrame(votes_card, fg_color="transparent")
        votes_header.pack(fill="x", padx=14, pady=(8, 0))
        ctk.CTkLabel(votes_header, text="QUAD-CORE ENSEMBLE BREAKDOWN", font=_f("section"), text_color=C["txt_sec"]).pack(side="left")
        GradientLine(votes_card, height=1, color_left=C["accent"], color_right=C["accent2"], bg=C["bg_card"]).pack(fill="x", padx=14, pady=(3, 6))

        self.vote_rows: dict[str, VoteRow] = {}
        vote_configs = [
            ("Kaggle",    "Expert α  (Kaggle)",    C["accent"]),
            ("BODMAS",    "Expert β  (BODMAS)",    C["accent2"]),
            ("EMBER",     "Expert γ  (EMBER)",     C["green"]),
            ("Quo_Vadis", "Expert δ  (Quo Vadis)", C["red"])
        ]
        for dict_key, display_name, dot_c in vote_configs:
            vr = VoteRow(votes_card, model_name=display_name, dot_color=dot_c)
            vr.pack(fill="x", padx=14, pady=2)
            self.vote_rows[dict_key] = vr
        ctk.CTkFrame(votes_card, height=0).pack(pady=4)

        # Terminal
        t_header = ctk.CTkFrame(main, fg_color="transparent")
        t_header.pack(fill="x", padx=24, pady=(0, 3))
        ctk.CTkLabel(t_header, text="SYSTEM TERMINAL", font=_f("section"), text_color=C["txt_sec"]).pack(side="left")
        self._cursor_vis = True
        self.cursor_lbl = ctk.CTkLabel(t_header, text="█", font=_f("mono_sm"), text_color=C["accent"])
        self.cursor_lbl.pack(side="left", padx=4)
        self._blink_cursor()
        ctk.CTkLabel(t_header, text="IntelliGuard $", font=_f("label_sm"), text_color=C["border2"]).pack(side="right")

        self.console = ctk.CTkTextbox(main, font=_f("mono"), fg_color=C["bg_deep"], text_color=C["txt_mono"],
                                      border_width=1, border_color=C["border2"], corner_radius=8,
                                      scrollbar_button_color=C["border2"], scrollbar_button_hover_color=C["bg_hover"], wrap="word")
        self.console.pack(fill="both", expand=True, padx=24, pady=(0, 16))
        self.console.configure(state="disabled")

    def _sidebar_section(self, parent, title: str, accent_color: str, top_pad: int = 10):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", padx=16, pady=(top_pad, 6))
        ctk.CTkFrame(frame, width=3, height=12, fg_color=accent_color, corner_radius=2).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(frame, text=title, font=_f("section"), text_color=C["txt_sec"]).pack(side="left")

    def _blink_cursor(self):
        self._cursor_vis = not self._cursor_vis
        self.cursor_lbl.configure(text="█" if self._cursor_vis else " ")
        self.after(550, self._blink_cursor)

    def _start_btn_pulse(self):
        self._btn_pulse_step = 0
        self._btn_pulse()

    def _btn_pulse(self):
        if self.is_scanning:
            self.scan_btn.configure(border_width=0, border_color=C["accent"])
            return
        step = self._btn_pulse_step % 40
        t = abs(step - 20) / 20.0 
        glow_color = f"#{int(0x00):02x}{int(0x88 + (0xbf - 0x88) * t):02x}{int(0xbb + (0xff - 0xbb) * t):02x}"
        self.scan_btn.configure(border_width=2, border_color=glow_color)
        self._btn_pulse_step += 1
        self._scan_anim_id = self.after(80, self._btn_pulse)

    def _start_scan_anim(self):
        self._scan_dots = 0
        self._animate_scan_text()

    def _animate_scan_text(self):
        if not self.is_scanning: return
        self.scan_btn.configure(text=f"⚙  ANALYSING {'.' * (self._scan_dots % 4)}")
        self._scan_dots += 1
        self.after(400, self._animate_scan_text)

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

    # ── Background File Monitors ─────────────────────────────────────────
    def _start_background_monitor(self):
        downloads = r"D:\Downloads"
        os.makedirs(downloads, exist_ok=True)
        self.observer = Observer()
        self.observer.schedule(DownloadHandler(self), downloads, recursive=False)
        self.observer.start()
        self.after(2500, lambda: self._log(f"[SYS]  🛡️  Download Drop Monitor ACTIVE → {downloads}"))

    # ── Live Execution Monitor ─────────────────────────────────────
    def _start_execution_monitor(self):
        if not PSUTIL_AVAILABLE:
            self.after(3000, lambda: self._log("[SYS]  ⚠️ psutil not installed. Live Process Tracker disabled. (pip install psutil)"))
            return

        self._known_pids = set()
        downloads_path = os.path.normcase(r"D:\Downloads")

        def _watch():
            while True:
                try:
                    for proc in psutil.process_iter(['pid', 'name', 'exe']):
                        pid, exe = proc.info['pid'], proc.info['exe']
                        
                        if pid in self._known_pids or not exe:
                            continue
                            
                        if os.path.normcase(exe).startswith(downloads_path):
                            self._known_pids.add(pid)
                            name = proc.info['name']
                            self._log(f"[WARN] ⚠️ EXECUTION DETECTED: {name} is running from Downloads!")
                            
                            try:
                                notification.notify(
                                    title="IntelliGuard Active Tracking",
                                    message=f"Process executed from Downloads:\n{name}",
                                    timeout=5
                                )
                            except Exception: pass
                except Exception:
                    pass
                time.sleep(2.0) 

        threading.Thread(target=_watch, daemon=True).start()
        self.after(2800, lambda: self._log("[SYS]  👁️  Live Process Execution Tracker ACTIVE"))

    # ── AI Logic Mapping ────────────────────────────────────────────────
    def _get_expert_reason(self, model: str, is_mal: bool, conf: float) -> str:
        """Translates numerical confidence into human-readable heuristic explanations."""
        if not is_mal:
            if model == "Kaggle": return "↳ Standard PE structure and normal file entropy."
            if model == "BODMAS": return "↳ Import Address Table (IAT) appears benign."
            if model == "EMBER": return "↳ Clean byte distribution and safe structural markers."
            if model == "Quo_Vadis": return "↳ No destructive API calls or injection signatures found."
        else:
            sev = "Critical" if conf > 0.9 else ("High" if conf > 0.7 else "Suspicious")
            if model == "Kaggle": return f"↳ {sev}: Anomalous PE sections or high entropy (packed/obfuscated)."
            if model == "BODMAS": return f"↳ {sev}: Matches static signatures of known dropper/loader families."
            if model == "EMBER": return f"↳ {sev}: Suspicious byte histograms and anomalous string allocations."
            if model == "Quo_Vadis": return f"↳ {sev}: Detected code injection APIs or active evasion tactics."
        return "↳ Analysis complete."

    # ── Scan Queue ──────────────────────────────────────────────────────
    def queue_scan(self, file_path: str, auto: bool = False):
        self.scan_queue.put(file_path)
        self._log(f"{'[AUTO]' if auto else '[MANUAL]'}  Target queued: {os.path.basename(file_path)}")

    def _scan_worker(self):
        while True:
            file_path = self.scan_queue.get()
            while self.is_scanning: time.sleep(0.3)
            self.is_scanning = True
            self._run_scan(file_path)

    def browse_file(self):
        fp = filedialog.askopenfilename(title="Select Binary to Analyse", filetypes=[("Executable", "*.exe"), ("DLL", "*.dll"), ("All scannable", "*.exe *.dll *.sys *.msi *.bat *.cmd"), ("All files", "*.*")])
        if fp: self.queue_scan(fp)

    # ── Run Scan ────────────────────────────────────────────────────────
    def _run_scan(self, file_path: str):
        filename = os.path.basename(file_path)
        try: fsize = os.path.getsize(file_path)
        except OSError: fsize = 0
        self.last_scanned_file = filename

        def _reset_ui():
            self.scan_btn.configure(state="disabled")
            self._start_scan_anim()
            self.verdict_icon.configure(text="◌", text_color=C["amber"])
            self.verdict_lbl.configure(text="SCANNING …", text_color=C["amber"])
            self.verdict_card.configure(fg_color=C["bg_card"])
            self.file_lbl.configure(text=filename, text_color=C["txt_pri"])
            self.reason_lbl.configure(text="")
            self.score_lbl.configure(text="")
            self.elapsed_lbl.configure(text="")
            for vr in self.vote_rows.values(): vr.reset()
            self.radar.start()
            self.dot.set_color(C["amber"])
            self.status_lbl.configure(text="SCANNING", text_color=C["amber"])
        self.after(0, _reset_ui)

        self._log(f"\n┌──── TARGET ────────────────────────────────────────")
        self._log(f"│  {filename[:52]}\n│  Size: {fsize:,} bytes")
        self._log(f"└────────────────────────────────────────────────────")
        self._log("[*]  Extracting deep PE & behavior features …")

        t0 = time.time()
        result = self.engine.scan_file(file_path)
        elapsed = time.time() - t0

        self.after(0, self.radar.stop)

        if result.get("status") == "error":
            self._log(f"[ERR] {result.get('message')}", delay_ms=100)
            self.after(200, lambda: self.verdict_icon.configure(text="⚠", text_color=C["amber"]))
            self.after(200, lambda: self.verdict_lbl.configure(text="ANALYSIS FAILED", text_color=C["amber"]))
            self.after(200, lambda: self.verdict_card.configure(fg_color=C["warn_bg"]))
            self.after(200, lambda: self.dot.set_color(C["amber"]))
            self.after(200, lambda: self.status_lbl.configure(text="ERROR", text_color=C["amber"]))
            self.after(800, lambda: self.scan_btn.configure(state="normal", text="▸  SELECT FILE"))
            self.after(800, lambda: setattr(self, "is_scanning", False))
            self.after(850, self._start_btn_pulse)
            return

        votes, verdict = result.get("votes", {}), result.get("verdict", "UNKNOWN")
        fused, reason = result.get("fused_score", 0.0), result.get("verdict_reason", "")
        is_signed, signer = result.get("is_signed", False), result.get("signer", "")

        if is_signed: self._log(f"[SIG]  🔏 Signed by: {signer[:60]}")
        else: self._log("[SIG]  ⚠️  No valid digital signature")
        if result.get("trusted_publisher", False): self._log(f"[TRU]  🛡️  Trusted Publisher — inference skipped")

        total_delay = 200
        for idx, (model_key, data) in enumerate(votes.items()):
            delay = 250 + idx * 220
            vr = self.vote_rows.get(model_key) 
            status = data.get("status", "")

            if status == "TRUSTED":
                self._log(f"  🛡️  [{model_key}] → TRUSTED", delay_ms=delay)
                if vr: vr.set_state("TRUSTED", C["green"], "↳ Inference bypassed due to Trusted Publisher certificate.", delay_ms=delay + 50)
            elif status == "SKIPPED":
                cov = data.get("match_ratio", 0) * 100
                self._log(f"  ⏭️  [{model_key}] → SKIPPED  (coverage {cov:.0f}%)", delay_ms=delay)
                if vr: vr.set_state("SKIPPED", C["amber"], "↳ Skipped: Insufficient feature overlap with model.", delay_ms=delay + 50)
            else:
                conf, is_mal, cov = data.get("confidence", 0.0), bool(data.get("malware", False)), data.get("match_ratio", 1.0)
                icon, label = ("🔴", "MALWARE") if is_mal else ("🟢", "SAFE")
                self._log(f"  {icon}  [{model_key}] → {label}  (conf={conf * 100:.1f}%, cov={cov * 100:.0f}%)", delay_ms=delay)
                
                # Fetch dynamically generated logic explanation
                logic_reason = self._get_expert_reason(model_key, is_mal, conf)
                if vr: vr.animate_result(is_mal, conf, cov, reason_text=logic_reason, delay_ms=delay + 80)
            total_delay = delay + 200

        self._log(f"[*]  Fused score: {fused:.4f}\n[*]  Reason: {reason}\n[*]  Scan completed in {elapsed:.2f}s", delay_ms=total_delay)

        settle = total_delay + 350
        self.after(settle, lambda: self.elapsed_lbl.configure(text=f"scan time: {elapsed:.2f}s"))
        self.after(settle, lambda: self.score_lbl.configure(text=f"Score: {fused:.3f}", text_color=C["red"] if verdict == "MALWARE" else C["green"]))
        self.after(settle, lambda: self.reason_lbl.configure(text=reason, text_color=C["txt_sec"]))

        active_mal, active_safe = sum(1 for v in votes.values() if v.get("status") == "VOTED" and v.get("malware")), sum(1 for v in votes.values() if v.get("status") == "VOTED" and not v.get("malware"))
        sig_override = (verdict == "SAFE" and active_mal > 0 and active_mal >= active_safe and is_signed)

        if verdict == "SAFE" and sig_override: self.after(settle + 100, self._show_safe_sig_override)
        elif verdict == "SAFE": self.after(settle + 100, self._show_safe)
        elif verdict == "MALWARE": self.after(settle + 100, self._show_malware)
        else: self.after(settle + 100, lambda: self.verdict_lbl.configure(text="UNKNOWN", text_color=C["amber"]))

        self._scan_count += 1
        if verdict == "MALWARE": self._threat_count += 1
        self.after(settle, lambda: self.card_scanned.update_value(str(self._scan_count)))
        self.after(settle, lambda: self.card_threats.update_value(str(self._threat_count)))

        final_settle = settle + 600
        self.after(final_settle, lambda: self.scan_btn.configure(state="normal", text="▸  SELECT FILE"))
        self.after(final_settle, lambda: self.dot.set_color(C["green"]))
        self.after(final_settle, lambda: self.status_lbl.configure(text="ONLINE  ·  MONITORING", text_color=C["green"]))
        self.after(final_settle, lambda: setattr(self, "is_scanning", False))
        self.after(final_settle + 50, self._start_btn_pulse)

    # ── Verdict Displays ────────────────────────────────────────────────
    def _show_safe(self):
        self.verdict_icon.configure(text="✓", text_color=C["green"])
        self.verdict_lbl.configure(text="FILE IS SAFE", text_color=C["green"])
        self.verdict_card.configure(fg_color=C["safe_bg"])
        self._log("════════════════════════════════════════════════════\n  VERDICT  →  ✓  SAFE — no threat detected\n════════════════════════════════════════════════════")
        try: notification.notify(title="IntelliGuard: SAFE", message=f"{getattr(self, 'last_scanned_file', 'File')} passed checks.", timeout=3)
        except Exception: pass

    def _show_safe_sig_override(self):
        self.verdict_icon.configure(text="⚠", text_color=C["amber"])
        self.verdict_lbl.configure(text="SAFE — SIG OVERRIDE", text_color=C["amber"])
        self.verdict_card.configure(fg_color=C["warn_bg"])
        self._log("════════════════════════════════════════════════════\n  VERDICT  →  ⚠  SAFE (Signature Override)\n  Models flagged suspicious BUT CA signature \n  trust overrides. Treat with caution.\n════════════════════════════════════════════════════")
        try: notification.notify(title="IntelliGuard: Caution", message=f"{getattr(self, 'last_scanned_file', 'File')}: Safe via signature — models suspicious.", timeout=5)
        except Exception: pass

    def _show_malware(self):
        self.verdict_icon.configure(text="☠", text_color=C["red"])
        self.verdict_lbl.configure(text="THREAT DETECTED", text_color=C["red"])
        self.verdict_card.configure(fg_color=C["danger_bg"])
        self._log("════════════════════════════════════════════════════\n  VERDICT  →  ☠  MALWARE DETECTED\n  ⚠  DO NOT EXECUTE — QUARANTINE IMMEDIATELY\n════════════════════════════════════════════════════")
        try: notification.notify(title="⚠ IntelliGuard: THREAT", message=f"Malware detected in {getattr(self, 'last_scanned_file', 'File')}!", timeout=6)
        except Exception: pass

    # ── Popup Dialog Helpers ────────────────────────────────────────────
    def _create_popup(self, title: str, width: int = 480, height: int = 400) -> ctk.CTkToplevel:
        popup = ctk.CTkToplevel(self)
        popup.title(title)
        popup.geometry(f"{width}x{height}")
        popup.configure(fg_color=C["bg_deep"])
        popup.transient(self)
        popup.grab_set()
        popup.resizable(False, False)
        popup.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - width) // 2
        y = self.winfo_y() + (self.winfo_height() - height) // 2
        popup.geometry(f"+{x}+{y}")
        return popup

    def _show_scan_details(self):
        popup = self._create_popup("Scan Summary", 500, 340)
        GradientLine(popup, height=3, color_left=C["accent"], color_right=C["accent2"], bg=C["bg_deep"]).pack(fill="x")
        ctk.CTkLabel(popup, text="SCAN STATISTICS", font=_f("head"), text_color=C["accent"]).pack(pady=(18, 8))
        card = ctk.CTkFrame(popup, fg_color=C["bg_card"], corner_radius=10, border_width=1, border_color=C["border2"])
        card.pack(fill="x", padx=24, pady=6)
        stats = [
            ("Total Files Scanned", str(self._scan_count), C["accent"]),
            ("Threats Found", str(self._threat_count), C["red"]),
            ("Files Cleared", str(self._scan_count - self._threat_count), C["green"]),
            ("Detection Rate", f"{(self._threat_count / max(1, self._scan_count)) * 100:.1f}%", C["amber"]),
        ]
        for label, value, color in stats:
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=6)
            ctk.CTkLabel(row, text=label, font=_f("body"), text_color=C["txt_sec"]).pack(side="left")
            ctk.CTkLabel(row, text=value, font=ctk.CTkFont(family=_MONO_FAMILY, size=14, weight="bold"), text_color=color).pack(side="right")
        ctk.CTkButton(popup, text="Close", command=popup.destroy, fg_color=C["bg_hover"], hover_color=C["border2"],
                      text_color=C["txt_pri"], corner_radius=8, height=36, width=120).pack(pady=18)

    def _show_threat_details(self):
        popup = self._create_popup("Threat Report", 500, 320)
        GradientLine(popup, height=3, color_left=C["red"], color_right=C["red_dim"], bg=C["bg_deep"]).pack(fill="x")
        ctk.CTkLabel(popup, text="THREAT OVERVIEW", font=_f("head"), text_color=C["red"]).pack(pady=(18, 8))
        card = ctk.CTkFrame(popup, fg_color=C["bg_card"], corner_radius=10, border_width=1, border_color=C["border2"])
        card.pack(fill="x", padx=24, pady=6)
        info = [
            ("Total Threats Detected", str(self._threat_count), C["red"]),
            ("Active Protections", "5 / 5", C["green"]),
            ("Threat Level", "LOW" if self._threat_count == 0 else ("MODERATE" if self._threat_count < 3 else "HIGH"),
             C["green"] if self._threat_count == 0 else (C["amber"] if self._threat_count < 3 else C["red"])),
        ]
        for label, value, color in info:
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=6)
            ctk.CTkLabel(row, text=label, font=_f("body"), text_color=C["txt_sec"]).pack(side="left")
            ctk.CTkLabel(row, text=value, font=ctk.CTkFont(family=_MONO_FAMILY, size=14, weight="bold"), text_color=color).pack(side="right")
        ctk.CTkButton(popup, text="Close", command=popup.destroy, fg_color=C["bg_hover"], hover_color=C["border2"],
                      text_color=C["txt_pri"], corner_radius=8, height=36, width=120).pack(pady=18)

    def _show_engine_details(self):
        popup = self._create_popup("Engine Details", 520, 420)
        GradientLine(popup, height=3, color_left=C["accent2"], color_right=C["accent"], bg=C["bg_deep"]).pack(fill="x")
        ctk.CTkLabel(popup, text="ENGINE CONFIGURATION", font=_f("head"), text_color=C["accent2"]).pack(pady=(18, 8))
        engines = [
            ("Expert α — Kaggle", "XGBoost", "PE Header features", C["accent"]),
            ("Expert β — BODMAS", "XGBoost", "PE + Behavioral features", C["accent2"]),
            ("Expert γ — EMBER", "XGBoost", "EMBER feature set", C["green"]),
            ("Expert δ — Quo Vadis", "XGBoost", "Dynamic emulation features", C["red"]),
        ]
        for name, algo, desc, color in engines:
            card = ctk.CTkFrame(popup, fg_color=C["bg_card"], corner_radius=8, border_width=1, border_color=C["border2"])
            card.pack(fill="x", padx=24, pady=4)
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=6)
            dot_cv = tk.Canvas(row, width=8, height=8, bg=C["bg_card"], highlightthickness=0)
            dot_cv.pack(side="left", padx=(0, 8))
            dot_cv.create_oval(0, 0, 8, 8, fill=color, outline="")
            ctk.CTkLabel(row, text=name, font=_f("mono_sm"), text_color=C["txt_pri"]).pack(side="left")
            ctk.CTkLabel(row, text=algo, font=_f("label_sm"), text_color=color).pack(side="right")
            ctk.CTkLabel(card, text=desc, font=_f("label"), text_color=C["txt_sec"]).pack(padx=28, pady=(0, 6), anchor="w")
        info_frame = ctk.CTkFrame(popup, fg_color=C["bg_card"], corner_radius=8, border_width=1, border_color=C["border2"])
        info_frame.pack(fill="x", padx=24, pady=8)
        ctk.CTkLabel(info_frame, text="Fusion Method:  Late-Fusion Majority Voting", font=_f("label"), text_color=C["txt_sec"]).pack(padx=12, pady=6)
        ctk.CTkButton(popup, text="Close", command=popup.destroy, fg_color=C["bg_hover"], hover_color=C["border2"],
                      text_color=C["txt_pri"], corner_radius=8, height=36, width=120).pack(pady=10)

    def _show_expert_info(self, name: str, dataset: str):
        descriptions = {
            "KAGGLE": "Trained on Kaggle malware dataset with PE header structural features.\nSpecializes in detecting packed and obfuscated binaries.",
            "BODMAS": "Blue Hexagon's BODMAS dataset with PE + behavioral features.\nExcels at detecting dropper and loader type malware.",
            "EMBER": "Endgame Malware BEnchmark for Research dataset.\nBroad-spectrum detection with EMBER's standardized feature extraction.",
            "QUO VADIS": "Quo Vadis dynamic emulation dataset.\nCaptures runtime behavioral patterns from sandboxed execution.",
        }
        popup = self._create_popup(f"{name} — {dataset}", 460, 260)
        GradientLine(popup, height=3, color_left=C["accent"], color_right=C["accent2"], bg=C["bg_deep"]).pack(fill="x")
        ctk.CTkLabel(popup, text=f"{name}  ·  {dataset}", font=_f("head"), text_color=C["accent"]).pack(pady=(18, 8))
        card = ctk.CTkFrame(popup, fg_color=C["bg_card"], corner_radius=10, border_width=1, border_color=C["border2"])
        card.pack(fill="x", padx=24, pady=6)
        desc = descriptions.get(dataset, "Expert model trained for malware classification.")
        ctk.CTkLabel(card, text=desc, font=_f("body"), text_color=C["txt_sec"], wraplength=380, justify="left").pack(padx=16, pady=12)
        ctk.CTkButton(popup, text="Close", command=popup.destroy, fg_color=C["bg_hover"], hover_color=C["border2"],
                      text_color=C["txt_pri"], corner_radius=8, height=36, width=120).pack(pady=14)

if __name__ == "__main__":
    app = IntelliGuardApp()
    app.mainloop()