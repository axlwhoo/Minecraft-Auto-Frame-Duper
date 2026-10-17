"""
Frame Duper with Graphical User Interface.

- Time between left clicks (seconds).
- "Hold right click" checkbox:
    * Checked   -> Right click is held down continuously.
    * Unchecked -> Performs a right click after each left click,
                   with the delay (in seconds) you enter. 0 = immediate.
- Hotbar (optional), changes slot at the start of each cycle:
    * Alternate slots: uses specified slots (e.g. 1,2 or 1,3,5).
    * Cycle hotbar: passes from 1 to 9 and loops back.
- Target window (optional): if selected, the program only sends
  clicks and keystrokes while that window is in focus. If switched,
  it automatically pauses and releases right click.
- Custom key to start/stop (default F6).

Target window support: Windows (native) and Linux/X11 (requires xdotool).

Requirements: pip install pynput
"""

import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

from pynput import keyboard
from pynput.mouse import Button, Controller

BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def resource_path(name):
    """Path to a file located alongside the .py script (logo, icon...)."""
    return os.path.join(BASE_DIR, name)

mouse = Controller()
kb = keyboard.Controller()

IS_WIN = sys.platform.startswith("win")
IS_LINUX = sys.platform.startswith("linux")

# ---------------------------------------------------------------------------
# Window Utilities
# ---------------------------------------------------------------------------
if IS_WIN:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [EnumWindowsProc, wintypes.LPARAM]

    def _win_title(hwnd):
        n = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value

    def _win_exe(hwnd):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = kernel32.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFORMATION
        if not handle:
            return ""
        try:
            size = wintypes.DWORD(520)
            buf = ctypes.create_unicode_buffer(size.value)
            if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                return buf.value.split("\\")[-1]
            return ""
        finally:
            kernel32.CloseHandle(handle)


def get_foreground():
    """Identifier of the active foreground window (or None if unavailable)."""
    if IS_WIN:
        return user32.GetForegroundWindow()
    if IS_LINUX:
        try:
            return subprocess.check_output(
                ["xdotool", "getactivewindow"], text=True, stderr=subprocess.DEVNULL
            ).strip()
        except Exception:
            return None
    return None


def list_windows():
    """Returns [(id, title, exe)] for visible windows."""
    result = []
    if IS_WIN:

        def callback(hwnd, lparam):
            if user32.IsWindowVisible(hwnd):
                title = _win_title(hwnd)
                if title:
                    result.append((hwnd, title, _win_exe(hwnd)))
            return True

        user32.EnumWindows(EnumWindowsProc(callback), 0)
        return result

    if IS_LINUX:
        try:
            ids = subprocess.check_output(
                ["xdotool", "search", "--onlyvisible", "--name", ""],
                text=True,
                stderr=subprocess.DEVNULL,
            ).split()
            for wid in ids:
                title = subprocess.check_output(
                    ["xdotool", "getwindowname", wid],
                    text=True,
                    stderr=subprocess.DEVNULL,
                ).strip()
                if title:
                    result.append((wid, title, ""))
            return result
        except Exception:
            raise RuntimeError("Could not list windows. Install xdotool (and use X11).")

    raise RuntimeError("Window selection is not supported on this OS.")


# ---------------------------------------------------------------------------
# General Utilities
# ---------------------------------------------------------------------------
def key_name(key):
    """Readable name for a pynput key."""
    if isinstance(key, keyboard.Key):
        return key.name.upper()
    char = getattr(key, "char", None)
    if char:
        return char.upper()
    return f"VK_{getattr(key, 'vk', '?')}"


def parse_seconds(text):
    value = float(text.replace(",", "."))
    if value < 0:
        raise ValueError
    return value


def parse_slots(text):
    """'1,2' / '1 3 5' -> [1, 2] / [1, 3, 5]. Valid slots: 1-9."""
    parts = text.replace(",", " ").split()
    slots = [int(p) for p in parts]
    if not slots or any(s < 1 or s > 9 for s in slots):
        raise ValueError
    return slots


def shorten(text, n=45):
    return text if len(text) <= n else text[: n - 1] + "…"


# ---------------------------------------------------------------------------
# Visual Style: Flat window with rounded corners, cards, and smooth buttons
# ---------------------------------------------------------------------------
from tkinter import font as tkfont

FONT = "Segoe UI"
PANEL = "#f7f7f9"      # Main panel
CARD = "#ffffff"       # Cards
BORDER = "#e6e6ec"     # Subtle card border
FIELD = "#efeff3"      # Fields & secondary buttons
FIELD_OFF = "#f5f5f8"  # Disabled fields
TEXT = "#1c1c21"
MUTED = "#8d8d98"
ACCENT = "#7c6af7"
DARK = "#18181b"
RED = "#e5484d"
GREEN = "#2fa36b"
ORANGE = "#f5a524"
FS = 9                 # Base font size
BAR_H = 36             # Title bar height
CUSTOM_BAR = IS_WIN    # Custom bar (without native title bar) on Windows only
KEY = "#010203"         # Transparent key color for rounded corners


def round_rect(canvas, x1, y1, x2, y2, r, **kw):
    """Rounded rectangle drawn as a smoothed polygon."""
    pts = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return canvas.create_polygon(pts, smooth=True, **kw)


class Card(tk.Canvas):
    """White card with rounded corners, subtle border, and a small header."""

    def __init__(self, parent, title, bg=PANEL, pad=12, radius=14):
        super().__init__(parent, bg=bg, highlightthickness=0, bd=0, width=10, height=10)
        self._card_pad = pad
        self._corner = radius
        self.inner = tk.Frame(self, bg=CARD)
        tk.Label(
            self.inner, text=title.upper(), font=(FONT, 8), fg=MUTED, bg=CARD
        ).pack(anchor="w")
        self.body = tk.Frame(self.inner, bg=CARD)
        self.body.pack(anchor="w", fill="x", pady=(8, 0))
        self._card_win = self.create_window(pad, pad, window=self.inner, anchor="nw")
        self.bind("<Configure>", self._on_configure)
        self.inner.bind("<Configure>", lambda e: self.fit(update=False))

    def fit(self, update=True):
        if update:
            self.update_idletasks()
        w = self.inner.winfo_reqwidth() + 2 * self._card_pad
        h = self.inner.winfo_reqheight() + 2 * self._card_pad
        if int(self.cget("width")) != w or int(self.cget("height")) != h:
            tk.Canvas.configure(self, width=w, height=h)

    def _on_configure(self, event):
        self.itemconfigure(self._card_win, width=max(1, event.width - 2 * self._card_pad))
        self.delete("shape")
        round_rect(
            self, 1, 1, event.width - 1, event.height - 1, self._corner,
            fill=CARD, outline=BORDER, tags="shape",
        )
        self.tag_lower("shape")


class RoundedButton(tk.Canvas):
    """Rounded button. kind: 'primary' (dark), 'secondary' (gray), or 'light' (white with border).
    icon: None, 'min', 'pin', or 'close' (drawn toolbar icons)."""

    def __init__(self, parent, text="", command=None, kind="secondary",
                 width=None, height=34, radius=12, bg=PANEL, icon=None):
        font = tkfont.Font(
            family=FONT, size=FS, weight="bold" if kind == "primary" else "normal"
        )
        if width is None:
            width = max(80, font.measure(text) + 32)
        super().__init__(
            parent, width=width, height=height, bg=bg, highlightthickness=0, bd=0
        )
        self._btn_font = font
        self._btn_text = text
        self._btn_cmd = command
        self._btn_kind = kind
        self._btn_icon = icon
        self._btn_active = False
        self._btn_state = "normal"
        self._btn_hover = False
        self._corner = radius
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<ButtonRelease-1>", self._release)
        self._draw()

    def _colors(self):
        """(fill, text/icon color, outline)"""
        hover = self._btn_hover
        if self._btn_kind == "primary":
            if self._btn_state == "disabled":
                return "#b9b9c2", "#ffffff", "#b9b9c2"
            fill = "#33333a" if hover else DARK
            return fill, "#ffffff", fill
        if self._btn_kind == "light":
            fill = "#f3f3f7" if hover else "#ffffff"
            return fill, (ACCENT if self._btn_active else TEXT), BORDER
        if self._btn_state == "disabled":
            return FIELD_OFF, "#b4b4be", FIELD_OFF
        fill = "#e4e4ea" if hover else FIELD
        return fill, TEXT, fill

    def _draw(self):
        self.delete("all")
        w = self.winfo_width()
        if w <= 1:
            w = int(self.cget("width"))
        h = int(self.cget("height"))
        fill, fg, outline = self._colors()
        round_rect(self, 1, 1, w - 1, h - 1, self._corner, fill=fill, outline=outline)
        if self._btn_icon:
            self._draw_icon(w / 2, h / 2, fill, fg)
        else:
            self.create_text(w / 2, h / 2, text=self._btn_text, fill=fg, font=self._btn_font)

    def _draw_icon(self, cx, cy, fill, fg):
        if self._btn_icon == "min":
            self.create_line(cx - 5, cy, cx + 5, cy, fill=fg, width=1, capstyle="round")
        elif self._btn_icon == "close":
            self.create_line(cx - 5, cy - 5, cx + 5, cy + 5, fill=fg, width=1, capstyle="round")
            self.create_line(cx - 5, cy + 5, cx + 5, cy - 5, fill=fg, width=1, capstyle="round")
        elif self._btn_icon == "pin":  # Two overlapping squares
            self.create_rectangle(cx - 3, cy - 6, cx + 6, cy + 3, outline=fg, width=1)
            self.create_rectangle(cx - 6, cy - 3, cx + 3, cy + 6, outline=fg, fill=fill, width=1)

    def _enter(self, _):
        self._btn_hover = True
        self._draw()

    def _leave(self, _):
        self._btn_hover = False
        self._draw()

    def _release(self, event):
        inside = 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height()
        if self._btn_state == "normal" and inside and self._btn_cmd:
            self._btn_cmd()

    def configure(self, cnf=None, **kw):
        if "text" in kw:
            self._btn_text = kw.pop("text")
        if "command" in kw:
            self._btn_cmd = kw.pop("command")
        if "active" in kw:
            self._btn_active = kw.pop("active")
        if "state" in kw:
            self._btn_state = kw.pop("state")
            kw["cursor"] = "hand2" if self._btn_state == "normal" else "arrow"
        if kw:
            tk.Canvas.configure(self, **kw)
        self._draw()

    config = configure


class RoundedEntry(tk.Canvas):
    """Text field with smooth gray background and rounded corners."""

    def __init__(self, parent, textvariable, width=90, height=28, radius=10, bg=PANEL):
        super().__init__(
            parent, width=width, height=height, bg=bg, highlightthickness=0, bd=0
        )
        self._ent_w, self._ent_h, self._ent_r = width, height, radius
        self.entry = tk.Entry(
            self, textvariable=textvariable, relief="flat", bd=0,
            highlightthickness=0, font=(FONT, FS), bg=FIELD, fg=TEXT,
            insertbackground=TEXT, disabledbackground=FIELD_OFF,
            disabledforeground=MUTED,
        )
        self.create_window(12, height // 2, window=self.entry, anchor="w", width=width - 24)
        self._shape(FIELD)

    def _shape(self, fill):
        self.delete("shape")
        round_rect(
            self, 1, 1, self._ent_w - 1, self._ent_h - 1, self._ent_r,
            fill=fill, outline=fill, tags="shape",
        )
        self.tag_lower("shape")

    def configure(self, cnf=None, **kw):
        if "state" in kw:
            state = kw.pop("state")
            self.entry.config(state=state)
            self._shape(FIELD if state == "normal" else FIELD_OFF)
        if kw:
            tk.Canvas.configure(self, **kw)

    config = configure


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
APP_TITLE = "Frame Duper"
LOGO_FILE = "logo.png"    # Title bar logo
ICON_FILE = "icon.ico"   # Window / taskbar icon (Windows)
LOGO_SIZE = 20            # Logo size in pixels
PICKER_TITLE = "Select Window"


class FrameDuper:
    def __init__(self, root):
        self.root = root
        root.title(APP_TITLE)
        root.resizable(False, False)
        if CUSTOM_BAR:
            root.overrideredirect(True)  # Remove native title bar; use custom one
        self._drag = None
        self._was_min = False
        self._pinned = False
        self._set_app_icon(root)

        self.running = False
        self.paused = False
        self.thread = None
        self.stop_event = threading.Event()

        # Shared thread values (avoid reading widgets from background thread)
        self.delay = 1.0
        self.right_delay = 0.0
        self.hold_right = False
        self.right_down = False
        self.slots = []  # Empty = hotbar disabled
        self.target = None  # (id, title, exe) or None = any window

        # Start/Stop hotkey
        self.hotkey = keyboard.Key.f6
        self.capturing = False

        # ttk styles for checkbuttons / radiobuttons (purple accent)
        style = ttk.Style(root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        for prefix, color in (("Panel", PANEL), ("Card", CARD)):
            for kind in ("TCheckbutton", "TRadiobutton"):
                name = f"{prefix}.{kind}"
                style.configure(
                    name, background=color, foreground=TEXT, font=(FONT, FS),
                    focuscolor=color, indicatorbackground="#ffffff",
                    indicatorforeground="#ffffff", bordercolor="#cfcfd8",
                )
                style.map(
                    name,
                    background=[("active", color)],
                    foreground=[("disabled", MUTED)],
                    indicatorbackground=[("disabled", "#ececf0"), ("selected", ACCENT)],
                    indicatorforeground=[("selected", "#ffffff")],
                )

        # Gradient background + rounded panel (drawn in _finish_layout)
        self.bgc = tk.Canvas(root, highlightthickness=0, bd=0)
        self.bgc.pack(fill="both", expand=True)
        content = tk.Frame(self.bgc, bg=PANEL)
        self._content = content

        # Two columns: left = clicks / key / start, right = hotbar & target window
        left = tk.Frame(content, bg=PANEL)
        left.grid(row=0, column=0, sticky="nsew")
        right = tk.Frame(content, bg=PANEL)
        right.grid(row=0, column=1, sticky="nsew", padx=(18, 0))
        left.columnconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        def label(parent, text, bg=PANEL):
            return tk.Label(parent, text=text, bg=bg, fg=TEXT, font=(FONT, FS))

        # ================= Left Column =================
        # Left click delay
        label(left, "Time between left clicks (sec):").grid(
            row=0, column=0, sticky="w", pady=(5, 0)
        )
        self.delay_var = tk.StringVar(value="0.1")
        self.delay_entry = RoundedEntry(left, self.delay_var, width=76)
        self.delay_entry.grid(row=0, column=1, sticky="e", padx=(10, 0), pady=(5, 0))

        # Hold right click checkbox
        self.hold_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            left,
            text="Hold right click",
            variable=self.hold_var,
            command=self.update_hold,
            style="Panel.TCheckbutton",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(12, 8))

        # Right click delay (only if NOT held down)
        label(left, "Right click delay (sec):").grid(
            row=2, column=0, sticky="w"
        )
        self.right_delay_var = tk.StringVar(value="0")
        self.right_delay_entry = RoundedEntry(left, self.right_delay_var, width=76)
        self.right_delay_entry.grid(row=2, column=1, sticky="e", padx=(10, 0))

        # Custom key
        label(left, "Start/Stop key:").grid(
            row=3, column=0, sticky="w", pady=(20, 0)
        )
        self.key_button = RoundedButton(
            left, key_name(self.hotkey), self.start_capture, width=112, height=28
        )
        self.key_button.grid(row=3, column=1, sticky="e", padx=(10, 0), pady=(20, 0))

        # Start/Stop button
        self.button = RoundedButton(
            left, "Start", self.toggle, kind="primary", width=200, height=36, radius=12
        )
        self.button.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(14, 0))

        self.status = tk.Label(
            left, text="Stopped", fg=RED, bg=PANEL, font=(FONT, FS)
        )
        self.status.grid(row=5, column=0, columnspan=2, pady=(14, 0))

        # ================= Right Column =================
        # ---- Hotbar ----
        self.hotbar_card = Card(right, "Hotbar")
        self.hotbar_card.grid(row=0, column=0, sticky="ew")
        hb = self.hotbar_card.body

        self.hotbar_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            hb,
            text="Change slot each cycle",
            variable=self.hotbar_var,
            command=self.refresh_ui,
            style="Card.TCheckbutton",
        ).grid(row=0, column=0, columnspan=2, sticky="w")

        self.mode_var = tk.StringVar(value="alternate")
        self.rb_alt = ttk.Radiobutton(
            hb,
            text="Alternate slots:",
            variable=self.mode_var,
            value="alternate",
            command=self.refresh_ui,
            style="Card.TRadiobutton",
        )
        self.rb_alt.grid(row=1, column=0, sticky="w", pady=(8, 0))

        self.slots_var = tk.StringVar(value="1,2")
        self.slots_entry = RoundedEntry(hb, self.slots_var, width=88, bg=CARD)
        self.slots_entry.grid(row=1, column=1, padx=(10, 0), pady=(8, 0))

        self.rb_all = ttk.Radiobutton(
            hb,
            text="Cycle hotbar 1 → 9 in loop",
            variable=self.mode_var,
            value="cycle",
            command=self.refresh_ui,
            style="Card.TRadiobutton",
        )
        self.rb_all.grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

        # ---- Target Window ----
        self.target_card = Card(right, "Target Program")
        self.target_card.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        tb = self.target_card.body
        tb.columnconfigure(0, weight=1)

        self.target_label = tk.Label(
            tb, bg=CARD, fg=TEXT, font=(FONT, FS), anchor="w", justify="left", width=34
        )
        self.target_label.grid(row=0, column=0, columnspan=2, sticky="w")

        self.pick_button = RoundedButton(
            tb, "Select window...", self.open_picker, width=170, height=28, bg=CARD
        )
        self.pick_button.grid(row=1, column=0, sticky="ew", pady=(10, 0))

        self.clear_button = RoundedButton(
            tb, "Remove", self.clear_target, width=70, height=28, bg=CARD
        )
        self.clear_button.grid(row=1, column=1, padx=(8, 0), pady=(10, 0))

        self.refresh_ui()
        self._finish_layout()

        # Global keyboard listener
        self.listener = keyboard.Listener(on_press=self.on_key)
        self.listener.start()

        self.poll()
        root.protocol("WM_DELETE_WINDOW", self.close)

    def _load_logo(self, size):
        """Loads logo.png at 'size' px. With Pillow accepts any size; without Pillow, PNG/GIF."""
        path = resource_path(LOGO_FILE)
        try:
            try:
                from PIL import Image, ImageTk
                img = Image.open(path).convert("RGBA").resize((size, size), Image.LANCZOS)
                return ImageTk.PhotoImage(img)
            except ImportError:
                img = tk.PhotoImage(file=path)
                return img.subsample(max(1, img.width() // size))
        except Exception:
            return None

    def _set_app_icon(self, root):
        """Window and taskbar icon."""
        try:
            if IS_WIN:
                root.iconbitmap(resource_path(ICON_FILE))
            else:
                self._icon_img = tk.PhotoImage(file=resource_path(LOGO_FILE))
                root.iconphoto(True, self._icon_img)
        except Exception:
            pass

    def _finish_layout(self):
        """Flat window with rounded corners, top title bar, and content."""
        for card in (self.hotbar_card, self.target_card):
            card.fit()
        self.root.update_idletasks()
        content = self._content
        pad = 24
        cw, ch = content.winfo_reqwidth(), content.winfo_reqheight()
        W = cw + 2 * pad
        H = BAR_H + ch + pad - 4
        c = self.bgc
        c.config(bg=KEY if CUSTOM_BAR else PANEL, width=W, height=H)
        if CUSTOM_BAR:
            # Color KEY becomes transparent: gives rounded window corners
            self.root.configure(bg=KEY)
            self.root.attributes("-transparentcolor", KEY)

        # Window body
        round_rect(c, 1, 1, W - 1, H - 1, 18, fill=PANEL, outline=BORDER)

        # White title pill with logo and app title
        title_font = tkfont.Font(family=FONT, size=FS)
        tw = title_font.measure(APP_TITLE)
        ph = 24
        px, py = 12, (BAR_H - ph) // 2 + 1
        lx, ly = px + 4, py + 3
        self._logo_img = self._load_logo(LOGO_SIZE)  # Keep reference or image disappears
        if self._logo_img:
            c.create_image(lx, ly, image=self._logo_img, anchor="nw")
        else:
            # Default logo if logo.png is missing
            round_rect(c, lx, ly, lx + 18, ly + 18, 6, fill=ACCENT, outline=ACCENT)
            cursor = [0, 0, 0, 13, 3.5, 10, 6, 15.5, 8.5, 14.5, 6, 9.5, 10.5, 9.5]
            pts = [(lx + 5 if i % 2 == 0 else ly + 3) + v * 0.75 for i, v in enumerate(cursor)]
            c.create_polygon(pts, fill="#ffffff", outline="#ffffff")
        c.create_text(
            lx + LOGO_SIZE + 6, py + ph / 2, text=APP_TITLE, anchor="w", font=title_font, fill=TEXT
        )

        # Window buttons (minimize, pin, close)
        if CUSTOM_BAR:
            by = BAR_H // 2 + 1
            close_btn = RoundedButton(
                c, "", self.close, kind="primary", icon="close",
                width=40, height=24, radius=8, bg=PANEL,
            )
            self.pin_btn = RoundedButton(
                c, "", self.toggle_pin, kind="light", icon="pin",
                width=32, height=24, radius=8, bg=PANEL,
            )
            min_btn = RoundedButton(
                c, "", self.minimize, kind="light", icon="min",
                width=32, height=24, radius=8, bg=PANEL,
            )
            c.create_window(W - 14, by, window=close_btn, anchor="e")
            c.create_window(W - 14 - 40 - 6, by, window=self.pin_btn, anchor="e")
            c.create_window(W - 14 - 40 - 6 - 32 - 6, by, window=min_btn, anchor="e")

        # Content
        c.create_window(W // 2, BAR_H + ch // 2 + 2, window=content, anchor="center")

        # Move window by dragging the title bar
        c.bind("<ButtonPress-1>", self._drag_start)
        c.bind("<B1-Motion>", self._drag_move)
        self.root.bind("<Map>", self._on_map)

        # Center on screen
        x = (self.root.winfo_screenwidth() - W) // 2
        y = (self.root.winfo_screenheight() - H) // 3
        self.root.geometry(f"{W}x{H}+{x}+{y}")
        if CUSTOM_BAR:
            self.root.after(60, self._fix_taskbar)

    # ---------- Title bar: drag / minimize / pin ----------
    def _drag_start(self, event):
        if event.y <= BAR_H:
            self._drag = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())
        else:
            self._drag = None

    def _drag_move(self, event):
        if self._drag:
            self.root.geometry(f"+{event.x_root - self._drag[0]}+{event.y_root - self._drag[1]}")

    def _fix_taskbar(self):
        """Without native window frame, Windows hides the taskbar icon; restore it."""
        try:
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
            style = (style & ~0x00000080) | 0x00040000  # Remove TOOLWINDOW, add APPWINDOW
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, style)
            self.root.withdraw()
            self.root.after(10, self.root.deiconify)
        except Exception:
            pass

    def minimize(self):
        """Minimizes window using parent HWND on Windows."""
        if IS_WIN:
            try:
                # Retrieve top-level HWND (TkTopLevel)
                hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
                # 6 = SW_MINIMIZE (minimizes window to taskbar)
                ctypes.windll.user32.ShowWindow(hwnd, 6)
                return
            except Exception:
                pass
        
        self.root.iconify()

    def _on_map(self, event):
        pass

    def toggle_pin(self):
        """Keep window always on top."""
        self._pinned = not self._pinned
        self.root.attributes("-topmost", self._pinned)
        self.pin_btn.config(active=self._pinned)

    # ---------- UI ----------
    def refresh_ui(self):
        """Updates widget states based on current state."""
        idle = not self.running
        self.delay_entry.config(state="normal" if idle else "disabled")

        right_ok = idle and not self.hold_var.get()
        self.right_delay_entry.config(state="normal" if right_ok else "disabled")

        hb = self.hotbar_var.get()
        self.rb_alt.config(state="normal" if (idle and hb) else "disabled")
        self.rb_all.config(state="normal" if (idle and hb) else "disabled")
        slots_ok = idle and hb and self.mode_var.get() == "alternate"
        self.slots_entry.config(state="normal" if slots_ok else "disabled")

        # Target window
        if self.target:
            _, title, exe = self.target
            text = f"{exe + ' — ' if exe else ''}{title}"
            self.target_label.config(text=shorten(text, 34), fg=TEXT)
        else:
            self.target_label.config(text="None (any window)", fg=MUTED)
        self.pick_button.config(state="normal" if idle else "disabled")
        self.clear_button.config(
            state="normal" if (idle and self.target) else "disabled"
        )

        name = key_name(self.hotkey)
        self.button.config(text=f"{'Stop' if self.running else 'Start'} ({name})")
        self.key_button.config(text="Press key..." if self.capturing else name)

    def poll(self):
        """Updates status label (running / paused)."""
        if self.running:
            if self.paused:
                self.status.config(
                    text="Paused: target window not active",
                    foreground=ORANGE,
                )
            else:
                self.status.config(text="Running...", foreground=GREEN)
        self.root.after(200, self.poll)

    def update_hold(self):
        self.hold_right = self.hold_var.get()
        # If changed while running, release right click when unchecked
        if self.running and not self.hold_right:
            self.release_right()
        self.refresh_ui()

    def start_capture(self):
        self.capturing = True
        self.refresh_ui()

    # ---------- Window Picker ----------
    def open_picker(self):
        top = tk.Toplevel(self.root)
        top.title(PICKER_TITLE)
        top.configure(bg=PANEL, padx=16, pady=14)
        top.resizable(False, False)
        top.transient(self.root)
        top.grab_set()

        tk.Label(
            top, text="Select the window where the program should run:",
            bg=PANEL, fg=TEXT, font=(FONT, FS),
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))

        list_frame = tk.Frame(top, bg=BORDER, padx=1, pady=1)
        list_frame.grid(row=1, column=0, columnspan=3, sticky="nsew")
        listbox = tk.Listbox(
            list_frame, width=75, height=15, exportselection=False, relief="flat",
            bd=0, highlightthickness=0, bg=CARD, fg=TEXT, font=(FONT, FS),
            selectbackground=ACCENT, selectforeground="#ffffff", activestyle="none",
        )
        listbox.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=listbox.yview)
        scroll.pack(side="right", fill="y")
        listbox.config(yscrollcommand=scroll.set)

        items = []

        def load():
            listbox.delete(0, tk.END)
            items.clear()
            try:
                windows = list_windows()
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=top)
                return
            for wid, title, exe in sorted(windows, key=lambda w: (w[2].lower(), w[1].lower())):
                if title in (APP_TITLE, PICKER_TITLE):
                    continue
                items.append((wid, title, exe))
                listbox.insert(tk.END, f"[{exe or '?'}]  {title}")

        def accept(event=None):
            sel = listbox.curselection()
            if not sel:
                return
            self.target = items[sel[0]]
            self.refresh_ui()
            top.destroy()

        listbox.bind("<Double-Button-1>", accept)
        top.columnconfigure(1, weight=1)
        RoundedButton(top, "Refresh", load, width=110).grid(
            row=2, column=0, pady=(12, 0), sticky="w"
        )
        RoundedButton(top, "Select", accept, kind="primary", width=120).grid(
            row=2, column=1, pady=(12, 0), sticky="e"
        )
        RoundedButton(top, "Cancel", top.destroy, width=100).grid(
            row=2, column=2, padx=(8, 0), pady=(12, 0), sticky="e"
        )
        load()

    def clear_target(self):
        self.target = None
        self.refresh_ui()

    def active(self):
        """True if no target window is set or if target window is in focus."""
        target = self.target
        return target is None or get_foreground() == target[0]

    # ---------- Hotkey ----------
    def on_key(self, key):
        if self.capturing:
            self.hotkey = key
            self.capturing = False
            self.root.after(0, self.refresh_ui)
            return
        if key == self.hotkey:
            self.root.after(0, self.toggle_from_hotkey)

    def toggle_from_hotkey(self):
        # Always allow stopping; only allow starting if target window is active
        if not self.running and not self.active():
            return
        self.toggle()

    def toggle(self):
        if self.running:
            self.stop()
        else:
            self.start()

    def start(self):
        try:
            delay = parse_seconds(self.delay_var.get())
        except ValueError:
            messagebox.showerror("Error", "Invalid left click delay (e.g. 0.5)")
            return

        hold = self.hold_var.get()
        try:
            right_delay = parse_seconds(self.right_delay_var.get())
        except ValueError:
            if hold:
                right_delay = 0.0
            else:
                messagebox.showerror("Error", "Invalid right click delay (e.g. 0.1)")
                return

        # Hotbar
        slots = []
        if self.hotbar_var.get():
            if self.mode_var.get() == "cycle":
                slots = list(range(1, 10))
            else:
                try:
                    slots = parse_slots(self.slots_var.get())
                except ValueError:
                    messagebox.showerror(
                        "Error", "Invalid slots. Use numbers from 1 to 9 (e.g. 1,2 or 1,3,5)"
                    )
                    return

            # Avoid hotkey overlapping with hotbar slot numbers
            hot_char = getattr(self.hotkey, "char", None)
            if hot_char and hot_char.isdigit() and int(hot_char) in slots:
                messagebox.showerror(
                    "Error",
                    f"Start/Stop key ({hot_char}) conflicts with a hotbar slot. "
                    "Choose another key.",
                )
                return

        self.delay = delay
        self.right_delay = right_delay
        self.hold_right = hold
        self.slots = slots
        self.paused = False
        self.running = True
        self.stop_event.clear()
        self.status.config(text="Running...", foreground=GREEN)
        self.refresh_ui()

        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        self.paused = False
        self.stop_event.set()
        self.status.config(text="Stopped", foreground=RED)
        self.refresh_ui()

    # ---------- Click Logic ----------
    def release_right(self):
        if self.right_down:
            mouse.release(Button.right)
            self.right_down = False

    def wait(self, seconds):
        """Interruptible wait. Releases right click if window loses focus.
        Returns True if stop was requested."""
        end = time.monotonic() + seconds
        while True:
            remaining = end - time.monotonic()
            if remaining <= 0:
                return self.stop_event.is_set()
            if self.stop_event.wait(min(0.05, remaining)):
                return True
            if self.right_down and not self.active():
                self.release_right()

    def loop(self):
        self.right_down = False
        slot_index = 0
        try:
            while not self.stop_event.is_set():
                # Target window not active -> pause
                if not self.active():
                    self.paused = True
                    self.release_right()
                    self.stop_event.wait(0.1)
                    continue
                self.paused = False

                # Change hotbar slot (at start of cycle)
                if self.slots:
                    kb.tap(str(self.slots[slot_index]))
                    slot_index = (slot_index + 1) % len(self.slots)

                # Left click
                mouse.click(Button.left)

                if self.hold_right:
                    if not self.right_down:
                        mouse.press(Button.right)
                        self.right_down = True
                else:
                    self.release_right()
                    # Right click delay (0 = immediate)
                    if self.right_delay > 0 and self.wait(self.right_delay):
                        break
                    if self.active():
                        mouse.click(Button.right)

                # Wait for next cycle
                if self.wait(self.delay):
                    break
        finally:
            mouse.release(Button.right)
            self.right_down = False

    def close(self):
        self.stop_event.set()
        mouse.release(Button.right)
        self.listener.stop()
        self.root.destroy()


if __name__ == "__main__":
    if IS_WIN:
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("FrameDuper.App")
        except Exception:
            pass
    root = tk.Tk()
    FrameDuper(root)
    root.mainloop()