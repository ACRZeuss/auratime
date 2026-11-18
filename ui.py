"""
Ubuntu (GNOME 47/48 Wellbeing / Ekran Süresi) Desktop UI for Windows.
Built with Tkinter + custom vector Canvas components styled in Ubuntu Yaru / Libadwaita theme.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Any, Callable
import winsound

from database import ScreenTimeDB
from tracker import ScreenTimeTracker, format_duration_tr
from win_api import (
    is_startup_enabled,
    is_windows_grayscale_active,
    set_dark_titlebar,
    set_startup_enabled,
    set_windows_grayscale,
)


THEMES: dict[str, dict[str, str]] = {
    "dark": {
        "bg": "#1E1E1E",
        "header_bg": "#252525",
        "card_bg": "#2D2D2D",
        "card_alt": "#343434",
        "card_hover": "#3A3A3A",
        "border": "#3E3E3E",
        "text": "#F5F5F5",
        "text_sec": "#ADADAD",
        "text_muted": "#7C7C7C",
        "accent": "#E95420",        # Ubuntu Orange
        "accent_hover": "#F46837",
        "blue": "#3584E4",          # GNOME Blue
        "green": "#2EC27E",         # GNOME Emerald Green
        "amber": "#F5C211",         # GNOME Warning Amber
        "red": "#E01B24",           # GNOME Danger Red
        "bar_normal": "#E95420",
        "bar_unselected": "#9E4728",
        "bar_over": "#E01B24",
        "bar_hourly": "#3584E4",
        "bar_track": "#383838",
        "grid_line": "#3B3B3B",
        "tooltip_bg": "#151515",
    },
    "light": {
        "bg": "#F6F5F4",
        "header_bg": "#EBEAE8",
        "card_bg": "#FFFFFF",
        "card_alt": "#F8F8F7",
        "card_hover": "#EFEFED",
        "border": "#DEDDDA",
        "text": "#241F31",
        "text_sec": "#5E5C64",
        "text_muted": "#9A9996",
        "accent": "#E95420",
        "accent_hover": "#D34615",
        "blue": "#1C71D8",
        "green": "#26A269",
        "amber": "#E5A50A",
        "red": "#C01C28",
        "bar_normal": "#E95420",
        "bar_unselected": "#F2A58A",
        "bar_over": "#C01C28",
        "bar_hourly": "#1C71D8",
        "bar_track": "#EAEAE8",
        "grid_line": "#E5E4E2",
        "tooltip_bg": "#241F31",
    },
}

TR_WEEKDAYS_SHORT = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
TR_WEEKDAYS_LONG = [
    "Pazartesi",
    "Salı",
    "Çarşamba",
    "Perşembe",
    "Cuma",
    "Cumartesi",
    "Pazar",
]
TR_MONTHS_SHORT = [
    "",
    "Oca",
    "Şub",
    "Mar",
    "Nis",
    "May",
    "Haz",
    "Tem",
    "Ağu",
    "Eyl",
    "Eki",
    "Kas",
    "Ara",
]
TR_MONTHS_LONG = [
    "",
    "Ocak",
    "Şubat",
    "Mart",
    "Nisan",
    "Mayıs",
    "Haziran",
    "Temmuz",
    "Ağustos",
    "Eylül",
    "Ekim",
    "Kasım",
    "Aralık",
]


def format_date_tr_long(d: date) -> str:
    today = date.today()
    wd = TR_WEEKDAYS_LONG[d.weekday()]
    month = TR_MONTHS_LONG[d.month]
    if d == today:
        return f"Bugün, {d.day} {month} {wd}"
    if d == today - timedelta(days=1):
        return f"Dün, {d.day} {month} {wd}"
    return f"{d.day} {month} {d.year}, {wd}"


def format_week_range_tr(monday: date) -> str:
    sunday = monday + timedelta(days=6)
    today_monday = date.today() - timedelta(days=date.today().weekday())
    prefix = "Bu Hafta · " if monday == today_monday else ""
    if monday.month == sunday.month:
        return f"{prefix}{monday.day} – {sunday.day} {TR_MONTHS_LONG[sunday.month]} {sunday.year}"
    return (
        f"{prefix}{monday.day} {TR_MONTHS_SHORT[monday.month]} – "
        f"{sunday.day} {TR_MONTHS_SHORT[sunday.month]} {sunday.year}"
    )


def draw_rounded_rect(
    canvas: tk.Canvas,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    r: float = 8,
    **kwargs: Any,
) -> int:
    """Draw a smooth rounded rectangle on a Tkinter Canvas."""
    r = max(0.0, min(r, abs(x2 - x1) / 2.0, abs(y2 - y1) / 2.0))
    if r < 1.5:
        return canvas.create_rectangle(x1, y1, x2, y2, **kwargs)
    points = [
        x1 + r, y1,
        x2 - r, y1,
        x2, y1,
        x2, y1 + r,
        x2, y2 - r,
        x2, y2,
        x2 - r, y2,
        x1 + r, y2,
        x1, y2,
        x1, y2 - r,
        x1, y1 + r,
        x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


class GnomeSwitch(tk.Canvas):
    """Libadwaita / Ubuntu Yaru pill switch widget."""

    def __init__(
        self,
        parent: tk.Widget,
        initial: bool = False,
        on_toggle: Callable[[bool], None] | None = None,
        theme: dict[str, str] | None = None,
    ) -> None:
        self.theme = theme or THEMES["dark"]
        super().__init__(
            parent,
            width=46,
            height=24,
            bg=parent.cget("bg"),
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self._value = bool(initial)
        self._on_toggle = on_toggle
        self.bind("<Button-1>", self._handle_click)
        self._render()

    @property
    def value(self) -> bool:
        return self._value

    def set_value(self, val: bool, notify: bool = False) -> None:
        self._value = bool(val)
        self._render()
        if notify and self._on_toggle:
            self._on_toggle(self._value)

    def update_theme(self, theme: dict[str, str], bg_color: str) -> None:
        self.theme = theme
        self.configure(bg=bg_color)
        self._render()

    def _handle_click(self, _event: tk.Event) -> None:
        self._value = not self._value
        self._render()
        if self._on_toggle:
            self._on_toggle(self._value)

    def _render(self) -> None:
        self.delete("all")
        track_color = self.theme["accent"] if self._value else self.theme["bar_track"]
        border_color = self.theme["accent"] if self._value else self.theme["border"]
        draw_rounded_rect(
            self,
            2,
            2,
            44,
            22,
            r=10,
            fill=track_color,
            outline=border_color,
        )
        knob_x = 24 if self._value else 4
        self.create_oval(
            knob_x,
            4,
            knob_x + 16,
            20,
            fill="#FFFFFF",
            outline="",
        )


class BreakOverlayWindow:
    """
    Ubuntu GNOME Wellbeing floating break countdown modal/banner.
    Appears top-center when an Eye Break (20s) or Movement Break (120s) starts.
    """

    def __init__(
        self,
        root: tk.Tk,
        theme_getter: Callable[[], dict[str, str]],
        on_finished: Callable[[], None],
    ) -> None:
        self.root = root
        self.theme_getter = theme_getter
        self.on_finished = on_finished
        self.win: tk.Toplevel | None = None
        self._remaining = 0
        self._total = 1
        self._after_id: str | None = None

    def show(self, break_type: str = "eye", duration_sec: int = 20) -> None:
        self.close()
        theme = self.theme_getter()
        self._total = max(5, duration_sec)
        self._remaining = self._total

        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=theme["accent"])
        self.win = win

        w, h = 460, 165
        sw = win.winfo_screenwidth()
        x = (sw - w) // 2
        y = 36
        win.geometry(f"{w}x{h}+{x}+{y}")

        inner = tk.Frame(win, bg=theme["card_bg"], padx=20, pady=14)
        inner.pack(fill="both", expand=True, padx=2, pady=2)

        is_eye = break_type == "eye"
        title_str = (
            "AuraTime · Göz Dinlendirme Molası (20-20-20)"
            if is_eye
            else "AuraTime · Hareket ve Esneme Molası"
        )
        desc_str = (
            "Gözlerinizi ekrandan ayırıp ~6 metre uzağa odaklanın."
            if is_eye
            else "Ayağa kalkın, omuzlarınızı dinlendirin ve kısa bir yürüyüş yapın."
        )

        top_row = tk.Frame(inner, bg=theme["card_bg"])
        top_row.pack(fill="x")

        tk.Label(
            top_row,
            text=title_str,
            font=("Segoe UI", 12, "bold"),
            fg=theme["text"],
            bg=theme["card_bg"],
        ).pack(side="left")

        self.lbl_timer = tk.Label(
            top_row,
            text=f"{self._remaining} sn",
            font=("Segoe UI", 14, "bold"),
            fg=theme["accent"],
            bg=theme["card_bg"],
        )
        self.lbl_timer.pack(side="right")

        tk.Label(
            inner,
            text=desc_str,
            font=("Segoe UI", 9),
            fg=theme["text_sec"],
            bg=theme["card_bg"],
            anchor="w",
        ).pack(fill="x", pady=(6, 10))

        self.prog_canvas = tk.Canvas(
            inner,
            height=8,
            bg=theme["card_bg"],
            highlightthickness=0,
            bd=0,
        )
        self.prog_canvas.pack(fill="x", pady=(0, 12))

        btn_row = tk.Frame(inner, bg=theme["card_bg"])
        btn_row.pack(fill="x")

        btn_skip = tk.Button(
            btn_row,
            text="Molayı Atla",
            font=("Segoe UI", 9, "bold"),
            fg=theme["text"],
            bg=theme["card_alt"],
            activebackground=theme["card_hover"],
            activeforeground=theme["text"],
            bd=0,
            padx=14,
            pady=5,
            cursor="hand2",
            command=self._skip,
        )
        btn_skip.pack(side="right")

        self._tick()

    def _tick(self) -> None:
        if not self.win or not self.win.winfo_exists():
            return
        theme = self.theme_getter()
        mins, secs = divmod(self._remaining, 60)
        t_str = f"{mins}:{secs:02d}" if mins > 0 else f"{secs} sn"
        self.lbl_timer.configure(text=t_str)

        self.prog_canvas.delete("all")
        cw = max(100, self.prog_canvas.winfo_width() or 416)
        draw_rounded_rect(self.prog_canvas, 0, 0, cw, 8, r=4, fill=theme["bar_track"], outline="")
        ratio = max(0.0, min(1.0, (self._total - self._remaining) / float(self._total)))
        fill_w = int(cw * ratio)
        if fill_w > 4:
            draw_rounded_rect(
                self.prog_canvas, 0, 0, fill_w, 8, r=4, fill=theme["green"], outline=""
            )

        if self._remaining <= 0:
            try:
                winsound.MessageBeep(winsound.MB_OK)
            except Exception:
                pass
            self.on_finished()
            self.close()
            return

        self._remaining -= 1
        self._after_id = self.root.after(1000, self._tick)

    def _skip(self) -> None:
        self.on_finished()
        self.close()

    def close(self) -> None:
        if self._after_id:
            try:
                self.root.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        if self.win and self.win.winfo_exists():
            self.win.destroy()
        self.win = None


class UbuntuScreenTimeWindow:
    """
    Main desktop window modeled after Ubuntu 24.10 / 25.04 GNOME Settings -> Wellbeing (Ekran Süresi).
    """

    def __init__(
        self,
        root: tk.Tk,
        db: ScreenTimeDB,
        tracker: ScreenTimeTracker,
        icon_path: Path,
        on_quit_app: Callable[[], None],
        start_minimized: bool = False,
    ) -> None:
        self.root = root
        self.db = db
        self.tracker = tracker
        self.icon_path = icon_path
        self.on_quit_app = on_quit_app

        # Current UI state
        self.theme_name = self.db.get_setting("theme", "dark")
        if self.theme_name not in THEMES:
            self.theme_name = "dark"
        self.theme = THEMES[self.theme_name]

        self.demo_mode = False
        self.selected_date: date = date.today()
        self.current_week_monday: date = self.selected_date - timedelta(
            days=self.selected_date.weekday()
        )
        self._week_bar_hitboxes: list[tuple[float, float, float, float, date, int]] = []
        self._hourly_bar_hitboxes: list[tuple[float, float, float, float, int, int]] = []
        self._hovered_week_idx: int | None = None
        self._hovered_hour_idx: int | None = None

        self.break_overlay = BreakOverlayWindow(
            self.root,
            theme_getter=lambda: self.theme,
            on_finished=self.tracker.reset_break_timers,
        )

        self._configure_root_window()
        self._build_layout()
        self.refresh_all()

        if start_minimized:
            self.hide_to_tray()

        # Schedule periodic 1-second UI refresh
        self._schedule_live_tick()

    def _configure_root_window(self) -> None:
        self.root.title("AuraTime — Dijital Denge & Ekran Süresi")
        self.root.geometry("920x820")
        self.root.minsize(780, 660)
        self.root.configure(bg=self.theme["bg"])

        assets_dir = self.icon_path.parent
        self._logo_photo_256: tk.PhotoImage | None = None
        self._logo_photo_64: tk.PhotoImage | None = None
        self._logo_photo_36: tk.PhotoImage | None = None

        try:
            p256 = assets_dir / "auratime_256.png"
            p64 = assets_dir / "auratime_64.png"
            p36 = assets_dir / "auratime_36.png"
            if p256.exists():
                self._logo_photo_256 = tk.PhotoImage(file=str(p256))
            if p64.exists():
                self._logo_photo_64 = tk.PhotoImage(file=str(p64))
            if p36.exists():
                self._logo_photo_36 = tk.PhotoImage(file=str(p36))
            if self._logo_photo_256 and self._logo_photo_64:
                self.root.iconphoto(True, self._logo_photo_256, self._logo_photo_64)
        except Exception:
            pass

        if self.icon_path.exists():
            try:
                self.root.iconbitmap(default=str(self.icon_path))
            except Exception:
                pass

        # Close button minimizes to System Tray so tracking continues seamlessly
        self.root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)

        # Apply Windows 10/11 dark titlebar
        self.root.update_idletasks()
        try:
            hwnd = int(self.root.wm_frame(), 16)
            set_dark_titlebar(hwnd, dark=(self.theme_name == "dark"))
        except Exception:
            pass

    def show_window(self) -> None:
        """Restore and bring window to front from the system tray."""
        self.root.after(0, self._do_show_window)

    def _do_show_window(self) -> None:
        self.root.deiconify()
        self.root.state("normal")
        self.root.lift()
        self.root.focus_force()
        self.refresh_all()

    def hide_to_tray(self) -> None:
        """Minimize window to the Windows System Tray."""
        self.root.withdraw()

    def trigger_break_overlay(self, break_type: str = "eye", duration_sec: int = 20) -> None:
        self.root.after(0, lambda: self.break_overlay.show(break_type, duration_sec))

    def _toggle_theme(self) -> None:
        self.theme_name = "light" if self.theme_name == "dark" else "dark"
        self.theme = THEMES[self.theme_name]
        self.db.set_setting("theme", self.theme_name)
        try:
            hwnd = int(self.root.wm_frame(), 16)
            set_dark_titlebar(hwnd, dark=(self.theme_name == "dark"))
        except Exception:
            pass
        self._rebuild_ui()

    def _toggle_demo_mode(self) -> None:
        self.demo_mode = not self.demo_mode
        self.refresh_all()

    def _rebuild_ui(self) -> None:
        for child in self.root.winfo_children():
            if isinstance(child, tk.Toplevel):
                continue
            child.destroy()
        self.root.configure(bg=self.theme["bg"])
        self._build_layout()
        self.refresh_all()

    def _build_layout(self) -> None:
        t = self.theme

        # --- Top GNOME Adwaita HeaderBar ---
        header = tk.Frame(self.root, bg=t["header_bg"], height=56, padx=18, pady=10)
        header.pack(fill="x", side="top")

        # Left: AuraTime SDF Logo + Brand Title + Subtitle + Live status chip
        left_hdr = tk.Frame(header, bg=t["header_bg"])
        left_hdr.pack(side="left")

        if self._logo_photo_36 is not None:
            tk.Label(
                left_hdr,
                image=self._logo_photo_36,
                bg=t["header_bg"],
                bd=0,
            ).pack(side="left", padx=(0, 12))
        else:
            logo_cv = tk.Canvas(
                left_hdr, width=32, height=32, bg=t["header_bg"], highlightthickness=0, bd=0
            )
            logo_cv.pack(side="left", padx=(0, 10))
            logo_cv.create_oval(2, 2, 30, 30, fill=t["accent"], outline="")

        brand_col = tk.Frame(left_hdr, bg=t["header_bg"])
        brand_col.pack(side="left")

        tk.Label(
            brand_col,
            text="AuraTime",
            font=("Segoe UI", 13, "bold"),
            fg=t["text"],
            bg=t["header_bg"],
            anchor="w",
        ).pack(anchor="w")

        tk.Label(
            brand_col,
            text="Dijital Denge ve Ekran Süresi",
            font=("Segoe UI", 8),
            fg=t["text_sec"],
            bg=t["header_bg"],
            anchor="w",
        ).pack(anchor="w")

        self.lbl_status_chip = tk.Label(
            left_hdr,
            text="● Aktif Takip",
            font=("Segoe UI", 9, "bold"),
            fg=t["green"],
            bg=t["card_bg"],
            padx=10,
            pady=4,
        )
        self.lbl_status_chip.pack(side="left", padx=(16, 0))

        # Right: Action buttons (Demo preview, Pause/Resume, Theme toggle, Minimize to Tray)
        right_hdr = tk.Frame(header, bg=t["header_bg"])
        right_hdr.pack(side="right")

        self.btn_demo = tk.Button(
            right_hdr,
            text="✨ Örnek Veri: Kapalı",
            font=("Segoe UI", 9),
            fg=t["text_sec"],
            bg=t["card_bg"],
            activebackground=t["card_hover"],
            activeforeground=t["text"],
            bd=0,
            padx=10,
            pady=5,
            cursor="hand2",
            command=self._toggle_demo_mode,
        )
        self.btn_demo.pack(side="left", padx=(0, 8))

        self.btn_pause = tk.Button(
            right_hdr,
            text="⏸ Duraklat",
            font=("Segoe UI", 9),
            fg=t["text"],
            bg=t["card_bg"],
            activebackground=t["card_hover"],
            activeforeground=t["text"],
            bd=0,
            padx=10,
            pady=5,
            cursor="hand2",
            command=self._on_click_pause,
        )
        self.btn_pause.pack(side="left", padx=(0, 8))

        theme_label = "☀ Açık Tema" if self.theme_name == "dark" else "🌙 Koyu Tema"
        tk.Button(
            right_hdr,
            text=theme_label,
            font=("Segoe UI", 9),
            fg=t["text"],
            bg=t["card_bg"],
            activebackground=t["card_hover"],
            activeforeground=t["text"],
            bd=0,
            padx=10,
            pady=5,
            cursor="hand2",
            command=self._toggle_theme,
        ).pack(side="left", padx=(0, 8))

        tk.Button(
            right_hdr,
            text="⬇ Tepsiye Küçült",
            font=("Segoe UI", 9),
            fg="#FFFFFF",
            bg=t["accent"],
            activebackground=t["accent_hover"],
            activeforeground="#FFFFFF",
            bd=0,
            padx=11,
            pady=5,
            cursor="hand2",
            command=self.hide_to_tray,
        ).pack(side="left")

        # --- Thin header separator ---
        tk.Frame(self.root, bg=t["border"], height=1).pack(fill="x", side="top")

        # --- Scrollable Main Content Container (GNOME Centered Clamp) ---
        outer = tk.Frame(self.root, bg=t["bg"])
        outer.pack(fill="both", expand=True)

        self.scroll_canvas = tk.Canvas(
            outer, bg=t["bg"], highlightthickness=0, bd=0
        )
        scrollbar = tk.Scrollbar(
            outer, orient="vertical", command=self.scroll_canvas.yview
        )
        self.scroll_canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        self.scroll_canvas.pack(side="left", fill="both", expand=True)

        self.content_frame = tk.Frame(self.scroll_canvas, bg=t["bg"], padx=28, pady=18)
        self._content_win_id = self.scroll_canvas.create_window(
            (0, 0), window=self.content_frame, anchor="nw"
        )

        self.content_frame.bind("<Configure>", self._on_content_configure)
        self.scroll_canvas.bind("<Configure>", self._on_canvas_configure)
        self.scroll_canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        # Build the 4 GNOME Wellbeing Sections inside content_frame
        self._build_chart_card()
        self._build_apps_card()
        self._build_limits_and_breaks_card()
        self._build_system_card()

    def _on_content_configure(self, _event: tk.Event) -> None:
        self.scroll_canvas.configure(scrollregion=self.scroll_canvas.bbox("all"))

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self.scroll_canvas.itemconfig(self._content_win_id, width=event.width)
        self._draw_weekly_chart()
        self._draw_hourly_chart()

    def _on_mousewheel(self, event: tk.Event) -> None:
        try:
            self.scroll_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass

    # =========================================================================
    # SECTION 1: Ubuntu / GNOME Screen Time Hero & Weekly + Hourly Bar Charts
    # =========================================================================
    def _build_chart_card(self) -> None:
        t = self.theme

        card = tk.Frame(
            self.content_frame,
            bg=t["card_bg"],
            highlightbackground=t["border"],
            highlightthickness=1,
            padx=22,
            pady=18,
        )
        card.pack(fill="x", pady=(0, 16))

        # Top row: Selected date & Big Screen Time Duration (left) + Week navigation (right)
        top_row = tk.Frame(card, bg=t["card_bg"])
        top_row.pack(fill="x")

        hero_left = tk.Frame(top_row, bg=t["card_bg"])
        hero_left.pack(side="left", anchor="nw")

        self.lbl_selected_date = tk.Label(
            hero_left,
            text="Bugün",
            font=("Segoe UI", 10, "bold"),
            fg=t["accent"],
            bg=t["card_bg"],
            anchor="w",
        )
        self.lbl_selected_date.pack(anchor="w")

        self.lbl_hero_duration = tk.Label(
            hero_left,
            text="0 dk",
            font=("Segoe UI", 28, "bold"),
            fg=t["text"],
            bg=t["card_bg"],
            anchor="w",
        )
        self.lbl_hero_duration.pack(anchor="w", pady=(2, 2))

        self.lbl_hero_comparison = tk.Label(
            hero_left,
            text="Haftalık Ortalama: 0 dk",
            font=("Segoe UI", 9),
            fg=t["text_sec"],
            bg=t["card_bg"],
            anchor="w",
        )
        self.lbl_hero_comparison.pack(anchor="w")

        # Right side: Week navigation & mini metric pills
        hero_right = tk.Frame(top_row, bg=t["card_bg"])
        hero_right.pack(side="right", anchor="ne")

        nav_row = tk.Frame(hero_right, bg=t["card_bg"])
        nav_row.pack(anchor="e")

        tk.Button(
            nav_row,
            text="◀",
            font=("Segoe UI", 9, "bold"),
            fg=t["text"],
            bg=t["card_alt"],
            activebackground=t["card_hover"],
            activeforeground=t["text"],
            bd=0,
            padx=10,
            pady=4,
            cursor="hand2",
            command=self._prev_week,
        ).pack(side="left", padx=(0, 6))

        self.lbl_week_range = tk.Label(
            nav_row,
            text="",
            font=("Segoe UI", 9, "bold"),
            fg=t["text"],
            bg=t["card_alt"],
            padx=12,
            pady=5,
        )
        self.lbl_week_range.pack(side="left", padx=(0, 6))

        self.btn_next_week = tk.Button(
            nav_row,
            text="▶",
            font=("Segoe UI", 9, "bold"),
            fg=t["text"],
            bg=t["card_alt"],
            activebackground=t["card_hover"],
            activeforeground=t["text"],
            bd=0,
            padx=10,
            pady=4,
            cursor="hand2",
            command=self._next_week,
        )
        self.btn_next_week.pack(side="left", padx=(0, 6))

        self.btn_today = tk.Button(
            nav_row,
            text="Bugün",
            font=("Segoe UI", 9),
            fg=t["accent"],
            bg=t["card_alt"],
            activebackground=t["card_hover"],
            activeforeground=t["accent"],
            bd=0,
            padx=10,
            pady=4,
            cursor="hand2",
            command=self._go_to_today,
        )
        self.btn_today.pack(side="left")

        # Sub-metrics row (First Active, Idle Time, Continuous Session, Limit Remaining)
        metrics_row = tk.Frame(card, bg=t["card_alt"], padx=14, pady=9)
        metrics_row.pack(fill="x", pady=(14, 14))

        self.lbl_metric_first = tk.Label(
            metrics_row,
            text="İlk Etkinlik: --:--",
            font=("Segoe UI", 9),
            fg=t["text_sec"],
            bg=t["card_alt"],
        )
        self.lbl_metric_first.pack(side="left", padx=(0, 18))

        self.lbl_metric_idle = tk.Label(
            metrics_row,
            text="Boşta (Hariç Tutulan): 0 dk",
            font=("Segoe UI", 9),
            fg=t["text_sec"],
            bg=t["card_alt"],
        )
        self.lbl_metric_idle.pack(side="left", padx=(0, 18))

        self.lbl_metric_session = tk.Label(
            metrics_row,
            text="Aralıksız Oturum: 0 dk",
            font=("Segoe UI", 9),
            fg=t["text_sec"],
            bg=t["card_alt"],
        )
        self.lbl_metric_session.pack(side="left", padx=(0, 18))

        self.lbl_metric_limit_status = tk.Label(
            metrics_row,
            text="Günlük Sınır: 8 sa",
            font=("Segoe UI", 9, "bold"),
            fg=t["green"],
            bg=t["card_alt"],
        )
        self.lbl_metric_limit_status.pack(side="right")

        # --- Weekly 7-Day Bar Chart (Monday .. Sunday) ---
        lbl_w_hdr = tk.Frame(card, bg=t["card_bg"])
        lbl_w_hdr.pack(fill="x", pady=(0, 4))
        tk.Label(
            lbl_w_hdr,
            text="HAFTALIK EKRAN SÜRESİ (GÜN SEÇMEK İÇİN SÜTUNA TIKLAYIN)",
            font=("Segoe UI", 8, "bold"),
            fg=t["text_muted"],
            bg=t["card_bg"],
        ).pack(side="left")

        self.weekly_canvas = tk.Canvas(
            card,
            height=195,
            bg=t["card_bg"],
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.weekly_canvas.pack(fill="x", pady=(2, 12))
        self.weekly_canvas.bind("<Button-1>", self._on_weekly_chart_click)
        self.weekly_canvas.bind("<Motion>", self._on_weekly_chart_hover)
        self.weekly_canvas.bind("<Leave>", self._on_weekly_chart_leave)

        tk.Frame(card, bg=t["border"], height=1).pack(fill="x", pady=(4, 12))

        # --- 24-Hour Hourly Breakdown Bar Chart (00:00 .. 23:00) ---
        lbl_h_hdr = tk.Frame(card, bg=t["card_bg"])
        lbl_h_hdr.pack(fill="x", pady=(0, 4))

        self.lbl_hourly_title = tk.Label(
            lbl_h_hdr,
            text="SAATLİK DAĞILIM (00:00 – 23:00)",
            font=("Segoe UI", 8, "bold"),
            fg=t["text_muted"],
            bg=t["card_bg"],
        )
        self.lbl_hourly_title.pack(side="left")

        self.lbl_hourly_hover = tk.Label(
            lbl_h_hdr,
            text="",
            font=("Segoe UI", 8, "bold"),
            fg=t["blue"],
            bg=t["card_bg"],
        )
        self.lbl_hourly_hover.pack(side="right")

        self.hourly_canvas = tk.Canvas(
            card,
            height=115,
            bg=t["card_bg"],
            highlightthickness=0,
            bd=0,
        )
        self.hourly_canvas.pack(fill="x")
        self.hourly_canvas.bind("<Motion>", self._on_hourly_chart_hover)
        self.hourly_canvas.bind("<Leave>", self._on_hourly_chart_leave)

    # =========================================================================
    # SECTION 2: Per-Application Screen Time Breakdown for Selected Day
    # =========================================================================
    def _build_apps_card(self) -> None:
        t = self.theme

        hdr = tk.Frame(self.content_frame, bg=t["bg"])
        hdr.pack(fill="x", pady=(2, 6))
        tk.Label(
            hdr,
            text="Uygulama Kullanımı",
            font=("Segoe UI", 11, "bold"),
            fg=t["text"],
            bg=t["bg"],
        ).pack(side="left")

        self.lbl_apps_subtitle = tk.Label(
            hdr,
            text="Seçili gündeki aktif pencere dağılımı",
            font=("Segoe UI", 9),
            fg=t["text_sec"],
            bg=t["bg"],
        )
        self.lbl_apps_subtitle.pack(side="right")

        self.apps_card = tk.Frame(
            self.content_frame,
            bg=t["card_bg"],
            highlightbackground=t["border"],
            highlightthickness=1,
            padx=18,
            pady=14,
        )
        self.apps_card.pack(fill="x", pady=(0, 16))

    # =========================================================================
    # SECTION 3: Ubuntu Wellbeing — Ekran Süresi Sınırı & Mola Hatırlatıcıları
    # =========================================================================
    def _build_limits_and_breaks_card(self) -> None:
        t = self.theme
        settings = self.db.get_all_settings()

        hdr = tk.Frame(self.content_frame, bg=t["bg"])
        hdr.pack(fill="x", pady=(2, 6))
        tk.Label(
            hdr,
            text="Ekran Süresi Sınırları ve Mola Hatırlatıcıları",
            font=("Segoe UI", 11, "bold"),
            fg=t["text"],
            bg=t["bg"],
        ).pack(side="left")

        card = tk.Frame(
            self.content_frame,
            bg=t["card_bg"],
            highlightbackground=t["border"],
            highlightthickness=1,
        )
        card.pack(fill="x", pady=(0, 16))

        # --- Row 1: Günlük Ekran Süresi Sınırı (Daily Screen Time Limit) ---
        row1 = tk.Frame(card, bg=t["card_bg"], padx=18, pady=13)
        row1.pack(fill="x")

        r1_text = tk.Frame(row1, bg=t["card_bg"])
        r1_text.pack(side="left", fill="x", expand=True)
        tk.Label(
            r1_text,
            text="Günlük Ekran Süresi Sınırı",
            font=("Segoe UI", 10, "bold"),
            fg=t["text"],
            bg=t["card_bg"],
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            r1_text,
            text="Günlük hedef süreye ulaşıldığında bildirim gönderir ve grafikte sınır çizgisini gösterir",
            font=("Segoe UI", 8),
            fg=t["text_sec"],
            bg=t["card_bg"],
            anchor="w",
        ).pack(anchor="w")

        r1_ctrl = tk.Frame(row1, bg=t["card_bg"])
        r1_ctrl.pack(side="right")

        tk.Button(
            r1_ctrl,
            text="−",
            font=("Segoe UI", 10, "bold"),
            fg=t["text"],
            bg=t["card_alt"],
            activebackground=t["card_hover"],
            bd=0,
            width=3,
            pady=2,
            cursor="hand2",
            command=lambda: self._adjust_daily_limit(-30),
        ).pack(side="left", padx=(0, 6))

        limit_mins = int(settings.get("daily_limit_minutes", "480"))
        self.lbl_limit_val = tk.Label(
            r1_ctrl,
            text=format_duration_tr(limit_mins * 60),
            font=("Segoe UI", 10, "bold"),
            fg=t["accent"],
            bg=t["card_alt"],
            width=10,
            pady=4,
        )
        self.lbl_limit_val.pack(side="left", padx=(0, 6))

        tk.Button(
            r1_ctrl,
            text="+",
            font=("Segoe UI", 10, "bold"),
            fg=t["text"],
            bg=t["card_alt"],
            activebackground=t["card_hover"],
            bd=0,
            width=3,
            pady=2,
            cursor="hand2",
            command=lambda: self._adjust_daily_limit(30),
        ).pack(side="left", padx=(0, 14))

        self.sw_daily_limit = GnomeSwitch(
            r1_ctrl,
            initial=(settings.get("daily_limit_enabled", "1") == "1"),
            on_toggle=self._on_toggle_daily_limit,
            theme=t,
        )
        self.sw_daily_limit.pack(side="left")

        tk.Frame(card, bg=t["border"], height=1).pack(fill="x")

        # --- Row 2: Süre Dolduğunda Ekranı Siyah-Beyaz Yap (Ubuntu Grayscale Mode) ---
        row2 = tk.Frame(card, bg=t["card_bg"], padx=18, pady=13)
        row2.pack(fill="x")

        r2_text = tk.Frame(row2, bg=t["card_bg"])
        r2_text.pack(side="left", fill="x", expand=True)
        tk.Label(
            r2_text,
            text="Sınır Aşıldığında Ekranı Gri Tonlamalı (Siyah-Beyaz) Yap",
            font=("Segoe UI", 10, "bold"),
            fg=t["text"],
            bg=t["card_bg"],
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            r2_text,
            text="Ubuntu Wellbeing gibi günlük süre dolduğunda Windows Renk Filtresi ile ekranı siyah-beyaz yapar",
            font=("Segoe UI", 8),
            fg=t["text_sec"],
            bg=t["card_bg"],
            anchor="w",
        ).pack(anchor="w")

        r2_ctrl = tk.Frame(row2, bg=t["card_bg"])
        r2_ctrl.pack(side="right")

        tk.Button(
            r2_ctrl,
            text="Şimdi Test Et",
            font=("Segoe UI", 8),
            fg=t["text_sec"],
            bg=t["card_alt"],
            activebackground=t["card_hover"],
            bd=0,
            padx=9,
            pady=4,
            cursor="hand2",
            command=self._test_grayscale_toggle,
        ).pack(side="left", padx=(0, 12))

        self.sw_grayscale = GnomeSwitch(
            r2_ctrl,
            initial=(settings.get("grayscale_on_limit", "0") == "1"),
            on_toggle=self._on_toggle_grayscale_setting,
            theme=t,
        )
        self.sw_grayscale.pack(side="left")

        tk.Frame(card, bg=t["border"], height=1).pack(fill="x")

        # --- Row 3: Göz Dinlendirme Molası (Eye Break 20-20-20) ---
        row3 = tk.Frame(card, bg=t["card_bg"], padx=18, pady=13)
        row3.pack(fill="x")

        r3_text = tk.Frame(row3, bg=t["card_bg"])
        r3_text.pack(side="left", fill="x", expand=True)
        tk.Label(
            r3_text,
            text="Göz Dinlendirme Molaları (20-20-20 Kuralı)",
            font=("Segoe UI", 10, "bold"),
            fg=t["text"],
            bg=t["card_bg"],
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            r3_text,
            text="Belirlenen aralıksız kullanım süresinde bir 20 saniyelik göz dinlendirme sayacı açar",
            font=("Segoe UI", 8),
            fg=t["text_sec"],
            bg=t["card_bg"],
            anchor="w",
        ).pack(anchor="w")

        r3_ctrl = tk.Frame(row3, bg=t["card_bg"])
        r3_ctrl.pack(side="right")

        tk.Button(
            r3_ctrl,
            text="Şimdi Mola Ver",
            font=("Segoe UI", 8),
            fg=t["text_sec"],
            bg=t["card_alt"],
            activebackground=t["card_hover"],
            bd=0,
            padx=9,
            pady=4,
            cursor="hand2",
            command=lambda: self.trigger_break_overlay("eye", 20),
        ).pack(side="left", padx=(0, 10))

        eye_min = int(settings.get("eye_break_interval_minutes", "30"))
        self.btn_eye_interval = tk.Button(
            r3_ctrl,
            text=f"Her {eye_min} dk",
            font=("Segoe UI", 9, "bold"),
            fg=t["blue"],
            bg=t["card_alt"],
            activebackground=t["card_hover"],
            bd=0,
            padx=10,
            pady=4,
            cursor="hand2",
            command=self._cycle_eye_interval,
        )
        self.btn_eye_interval.pack(side="left", padx=(0, 12))

        self.sw_eye_break = GnomeSwitch(
            r3_ctrl,
            initial=(settings.get("eye_break_enabled", "1") == "1"),
            on_toggle=self._on_toggle_eye_break,
            theme=t,
        )
        self.sw_eye_break.pack(side="left")

        tk.Frame(card, bg=t["border"], height=1).pack(fill="x")

        # --- Row 4: Hareket Molası (Movement Break) ---
        row4 = tk.Frame(card, bg=t["card_bg"], padx=18, pady=13)
        row4.pack(fill="x")

        r4_text = tk.Frame(row4, bg=t["card_bg"])
        r4_text.pack(side="left", fill="x", expand=True)
        tk.Label(
            r4_text,
            text="Hareket ve Esneme Molaları",
            font=("Segoe UI", 10, "bold"),
            fg=t["text"],
            bg=t["card_bg"],
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            r4_text,
            text="Uzun süreli aralıksız oturumlarda kısa yürüyüş ve esneme molası hatırlatır",
            font=("Segoe UI", 8),
            fg=t["text_sec"],
            bg=t["card_bg"],
            anchor="w",
        ).pack(anchor="w")

        r4_ctrl = tk.Frame(row4, bg=t["card_bg"])
        r4_ctrl.pack(side="right")

        move_min = int(settings.get("movement_break_interval_minutes", "60"))
        self.btn_move_interval = tk.Button(
            r4_ctrl,
            text=f"Her {move_min} dk",
            font=("Segoe UI", 9, "bold"),
            fg=t["blue"],
            bg=t["card_alt"],
            activebackground=t["card_hover"],
            bd=0,
            padx=10,
            pady=4,
            cursor="hand2",
            command=self._cycle_move_interval,
        )
        self.btn_move_interval.pack(side="left", padx=(0, 12))

        self.sw_move_break = GnomeSwitch(
            r4_ctrl,
            initial=(settings.get("movement_break_enabled", "1") == "1"),
            on_toggle=self._on_toggle_move_break,
            theme=t,
        )
        self.sw_move_break.pack(side="left")

    # =========================================================================
    # SECTION 4: System Settings (Idle Threshold, Windows Startup, Data Export)
    # =========================================================================
    def _build_system_card(self) -> None:
        t = self.theme
        settings = self.db.get_all_settings()

        hdr = tk.Frame(self.content_frame, bg=t["bg"])
        hdr.pack(fill="x", pady=(2, 6))
        tk.Label(
            hdr,
            text="Takip Hassasiyeti ve Sistem Ayarları",
            font=("Segoe UI", 11, "bold"),
            fg=t["text"],
            bg=t["bg"],
        ).pack(side="left")

        card = tk.Frame(
            self.content_frame,
            bg=t["card_bg"],
            highlightbackground=t["border"],
            highlightthickness=1,
        )
        card.pack(fill="x", pady=(0, 20))

        # --- Row 1: Boşta Kalma Süresi Eşiği (Idle Threshold) ---
        row1 = tk.Frame(card, bg=t["card_bg"], padx=18, pady=13)
        row1.pack(fill="x")

        r1_text = tk.Frame(row1, bg=t["card_bg"])
        r1_text.pack(side="left", fill="x", expand=True)
        tk.Label(
            r1_text,
            text="Boşta Kalma Algılama Süresi (Idle Eşiği)",
            font=("Segoe UI", 10, "bold"),
            fg=t["text"],
            bg=t["card_bg"],
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            r1_text,
            text="Fare veya klavye bu süre boyunca kullanılmazsa süre sayımı otomatik duraklatılır",
            font=("Segoe UI", 8),
            fg=t["text_sec"],
            bg=t["card_bg"],
            anchor="w",
        ).pack(anchor="w")

        idle_sec = int(settings.get("idle_threshold_seconds", "180"))
        self.btn_idle_threshold = tk.Button(
            row1,
            text=f"{idle_sec // 60} Dakika",
            font=("Segoe UI", 9, "bold"),
            fg=t["accent"],
            bg=t["card_alt"],
            activebackground=t["card_hover"],
            bd=0,
            padx=12,
            pady=5,
            cursor="hand2",
            command=self._cycle_idle_threshold,
        )
        self.btn_idle_threshold.pack(side="right")

        tk.Frame(card, bg=t["border"], height=1).pack(fill="x")

        # --- Row 2: Windows Başlangıcında Otomatik Çalıştır ---
        row2 = tk.Frame(card, bg=t["card_bg"], padx=18, pady=13)
        row2.pack(fill="x")

        r2_text = tk.Frame(row2, bg=t["card_bg"])
        r2_text.pack(side="left", fill="x", expand=True)
        tk.Label(
            r2_text,
            text="Windows Açılışında Arka Planda Başlat",
            font=("Segoe UI", 10, "bold"),
            fg=t["text"],
            bg=t["card_bg"],
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            r2_text,
            text="Bilgisayar açıldığında sistem tepsisinde (saatin yanında) otomatik olarak takibe başlar",
            font=("Segoe UI", 8),
            fg=t["text_sec"],
            bg=t["card_bg"],
            anchor="w",
        ).pack(anchor="w")

        self.sw_startup = GnomeSwitch(
            row2,
            initial=is_startup_enabled(),
            on_toggle=self._on_toggle_startup,
            theme=t,
        )
        self.sw_startup.pack(side="right")

        tk.Frame(card, bg=t["border"], height=1).pack(fill="x")

        # --- Row 3: Verileri Dışa Aktar (CSV) / Bugünü Sıfırla / Çıkış ---
        row3 = tk.Frame(card, bg=t["card_bg"], padx=18, pady=13)
        row3.pack(fill="x")

        tk.Label(
            row3,
            text="Ekran Süresi Geçmişi ve Veri Yönetimi",
            font=("Segoe UI", 10, "bold"),
            fg=t["text"],
            bg=t["card_bg"],
        ).pack(side="left")

        btn_box = tk.Frame(row3, bg=t["card_bg"])
        btn_box.pack(side="right")

        tk.Button(
            btn_box,
            text="📥 CSV Olarak Dışa Aktar",
            font=("Segoe UI", 9),
            fg=t["text"],
            bg=t["card_alt"],
            activebackground=t["card_hover"],
            bd=0,
            padx=12,
            pady=5,
            cursor="hand2",
            command=self._export_csv_dialog,
        ).pack(side="left", padx=(0, 8))

        tk.Button(
            btn_box,
            text="🔄 Bugünü Sıfırla",
            font=("Segoe UI", 9),
            fg=t["text_sec"],
            bg=t["card_alt"],
            activebackground=t["card_hover"],
            bd=0,
            padx=12,
            pady=5,
            cursor="hand2",
            command=self._reset_today_confirm,
        ).pack(side="left", padx=(0, 8))

        tk.Button(
            btn_box,
            text="✖ Uygulamadan Tamamen Çık",
            font=("Segoe UI", 9, "bold"),
            fg="#FFFFFF",
            bg=t["red"],
            activebackground="#B0151C",
            bd=0,
            padx=12,
            pady=5,
            cursor="hand2",
            command=self.on_quit_app,
        ).pack(side="left")

    # =========================================================================
    # Data Refresh & Chart Rendering
    # =========================================================================
    def _schedule_live_tick(self) -> None:
        if self.root.winfo_exists():
            if self.root.state() != "withdrawn":
                self.refresh_live_metrics()
            self.root.after(1000, self._schedule_live_tick)

    def refresh_live_metrics(self) -> None:
        """Fast 1-second update of live status badge and today's counter when viewing today."""
        t = self.theme
        st = self.tracker.current_state
        if st == "ACTIVE":
            app = self.tracker.current_app_name
            suffix = f" · {app}" if app else ""
            self.lbl_status_chip.configure(
                text=f"● Aktif Takip{suffix[:28]}", fg=t["green"]
            )
            self.btn_pause.configure(text="⏸ Duraklat")
        elif st == "IDLE":
            idle_s = int(self.tracker.current_idle_seconds)
            self.lbl_status_chip.configure(
                text=f"○ Boşta ({format_duration_tr(idle_s)} hareketsiz)", fg=t["amber"]
            )
            self.btn_pause.configure(text="⏸ Duraklat")
        elif st == "LOCKED":
            self.lbl_status_chip.configure(text="🔒 Ekran Kilitli", fg=t["amber"])
            self.btn_pause.configure(text="⏸ Duraklat")
        else:
            self.lbl_status_chip.configure(text="⏸ Takip Duraklatıldı", fg=t["red"])
            self.btn_pause.configure(text="▶ Devam Ettir")

        # If currently inspecting Today, keep numbers & chart updated every 5 seconds (and hero text every 1s)
        if self.selected_date == date.today():
            self._update_selected_day_header()
            if datetime.now().second % 5 == 0:
                self._draw_weekly_chart()
                self._draw_hourly_chart()
                self._populate_apps_list()

    def refresh_all(self) -> None:
        t = self.theme
        if self.demo_mode:
            self.btn_demo.configure(
                text="✨ Örnek Veri: Açık", fg="#FFFFFF", bg=t["blue"]
            )
        else:
            self.btn_demo.configure(
                text="✨ Örnek Veri: Kapalı", fg=t["text_sec"], bg=t["card_bg"]
            )

        self.lbl_week_range.configure(text=format_week_range_tr(self.current_week_monday))
        self._update_selected_day_header()
        self._draw_weekly_chart()
        self._draw_hourly_chart()
        self._populate_apps_list()

    def _update_selected_day_header(self) -> None:
        t = self.theme
        sel_str = self.selected_date.strftime("%Y-%m-%d")
        day_summary = self.db.get_day_summary(sel_str, demo_mode=self.demo_mode)
        active_sec = int(day_summary.get("active_seconds", 0))
        idle_sec = int(day_summary.get("idle_seconds", 0))
        first_act = day_summary.get("first_active") or "--:--"

        self.lbl_selected_date.configure(text=format_date_tr_long(self.selected_date))
        self.lbl_hero_duration.configure(
            text=format_duration_tr(active_sec, include_seconds=(active_sec < 60))
        )

        # Compute weekly average (across non-future days in the selected week)
        week_data = self.db.get_week_usage(self.current_week_monday, demo_mode=self.demo_mode)
        today = date.today()
        valid_days = [
            d["active_seconds"]
            for d in week_data
            if d["date_obj"] <= today and d["active_seconds"] > 0
        ]
        avg_sec = int(sum(valid_days) / len(valid_days)) if valid_days else active_sec

        # Compare with previous day
        prev_str = (self.selected_date - timedelta(days=1)).strftime("%Y-%m-%d")
        prev_sec = int(
            self.db.get_day_summary(prev_str, demo_mode=self.demo_mode).get("active_seconds", 0)
        )
        if prev_sec > 0:
            diff = active_sec - prev_sec
            if abs(diff) < 300:
                cmp_str = "Önceki günle neredeyse aynı"
            elif diff > 0:
                cmp_str = f"Önceki güne göre {format_duration_tr(diff)} daha fazla"
            else:
                cmp_str = f"Önceki güne göre {format_duration_tr(abs(diff))} daha az"
        else:
            cmp_str = "Önceki gün kaydı yok"

        self.lbl_hero_comparison.configure(
            text=f"Haftalık Ortalama: {format_duration_tr(avg_sec)}   ·   {cmp_str}"
        )

        # Metrics bar
        self.lbl_metric_first.configure(text=f"İlk Etkinlik: {first_act[:5]}")
        self.lbl_metric_idle.configure(
            text=f"Boşta (Sayılmayan): {format_duration_tr(idle_sec)}"
        )
        self.lbl_metric_session.configure(
            text=f"Aralıksız Oturum: {format_duration_tr(self.tracker.continuous_active_seconds)}"
        )

        limit_enabled = self.db.get_setting("daily_limit_enabled", "1") == "1"
        limit_mins = int(self.db.get_setting("daily_limit_minutes", "480"))
        limit_sec = limit_mins * 60
        if not limit_enabled:
            self.lbl_metric_limit_status.configure(
                text="Günlük Sınır: Kapalı", fg=t["text_muted"]
            )
        elif active_sec >= limit_sec:
            over = active_sec - limit_sec
            self.lbl_metric_limit_status.configure(
                text=f"⚠ Sınır {format_duration_tr(over)} Aşıldı ({format_duration_tr(limit_sec)})",
                fg=t["red"],
            )
        else:
            rem = limit_sec - active_sec
            self.lbl_metric_limit_status.configure(
                text=f"✓ Sınıra {format_duration_tr(rem)} Kaldı (Hedef: {format_duration_tr(limit_sec)})",
                fg=t["green"],
            )

    def _draw_weekly_chart(self) -> None:
        cv = self.weekly_canvas
        cv.delete("all")
        t = self.theme

        w = max(560, cv.winfo_width())
        h = 195
        pad_left = 42
        pad_right = 58
        pad_top = 18
        pad_bottom = 38
        plot_w = w - pad_left - pad_right
        plot_h = h - pad_top - pad_bottom

        week_data = self.db.get_week_usage(self.current_week_monday, demo_mode=self.demo_mode)
        limit_enabled = self.db.get_setting("daily_limit_enabled", "1") == "1"
        limit_sec = int(self.db.get_setting("daily_limit_minutes", "480")) * 60

        max_val = max([d["active_seconds"] for d in week_data] + [3600 * 4])
        if limit_enabled:
            max_val = max(max_val, int(limit_sec * 1.15))

        # Round max_val up to nearest even hour (at least 4 hours)
        max_hours = max(4, int((max_val / 3600.0) + 1.99) // 2 * 2)
        y_max_sec = max_hours * 3600

        # Draw horizontal grid lines (0, 25%, 50%, 75%, 100%)
        steps = 4
        for i in range(steps + 1):
            frac = i / float(steps)
            y = pad_top + plot_h * (1.0 - frac)
            hrs = int(round(max_hours * frac))
            cv.create_line(
                pad_left, y, w - pad_right, y, fill=t["grid_line"], width=1
            )
            cv.create_text(
                pad_left - 8,
                y,
                text=f"{hrs} sa",
                font=("Segoe UI", 8),
                fill=t["text_muted"],
                anchor="e",
            )

        # Draw Daily Screen Time Limit dashed line (Ubuntu Wellbeing signature element)
        if limit_enabled and 0 < limit_sec <= y_max_sec:
            ly = pad_top + plot_h * (1.0 - (limit_sec / float(y_max_sec)))
            cv.create_line(
                pad_left,
                ly,
                w - pad_right,
                ly,
                fill=t["green"],
                width=1.5,
                dash=(5, 4),
            )
            cv.create_text(
                w - pad_right + 6,
                ly,
                text=f"Sınır\n{limit_sec // 3600} sa",
                font=("Segoe UI", 8, "bold"),
                fill=t["green"],
                anchor="w",
            )

        # Draw 7 vertical day bars
        col_w = plot_w / 7.0
        bar_w = min(46.0, col_w * 0.52)
        self._week_bar_hitboxes.clear()
        today = date.today()

        for i, item in enumerate(week_data):
            d_obj: date = item["date_obj"]
            act_sec: int = item["active_seconds"]
            cx = pad_left + col_w * (i + 0.5)
            bx1 = cx - bar_w / 2.0
            bx2 = cx + bar_w / 2.0
            base_y = pad_top + plot_h

            # Background track bar
            draw_rounded_rect(
                cv,
                bx1,
                pad_top,
                bx2,
                base_y,
                r=6,
                fill=t["bar_track"],
                outline="",
            )

            is_selected = d_obj == self.selected_date
            is_hovered = i == self._hovered_week_idx

            if act_sec > 0:
                ratio = min(1.0, act_sec / float(y_max_sec))
                bh = max(6.0, plot_h * ratio)
                by1 = base_y - bh

                if limit_enabled and act_sec > limit_sec:
                    bar_color = t["bar_over"]
                elif is_selected or is_hovered:
                    bar_color = t["bar_normal"]
                else:
                    bar_color = t["bar_unselected"]

                draw_rounded_rect(
                    cv,
                    bx1,
                    by1,
                    bx2,
                    base_y,
                    r=6,
                    fill=bar_color,
                    outline=t["text"] if is_selected else "",
                    width=1.5 if is_selected else 0,
                )

                # Value label on top of bar
                if act_sec >= 60:
                    cv.create_text(
                        cx,
                        max(8, by1 - 9),
                        text=format_duration_tr(act_sec),
                        font=("Segoe UI", 8, "bold" if is_selected else "normal"),
                        fill=t["text"] if is_selected else t["text_sec"],
                    )

            # Day label below bar (highlighted pill if selected)
            day_label = TR_WEEKDAYS_SHORT[i]
            date_sub = f"{d_obj.day} {TR_MONTHS_SHORT[d_obj.month]}"
            if is_selected:
                draw_rounded_rect(
                    cv,
                    cx - 26,
                    base_y + 5,
                    cx + 26,
                    base_y + 33,
                    r=7,
                    fill=t["accent"],
                    outline="",
                )
                cv.create_text(
                    cx,
                    base_y + 13,
                    text=day_label,
                    font=("Segoe UI", 8, "bold"),
                    fill="#FFFFFF",
                )
                cv.create_text(
                    cx,
                    base_y + 25,
                    text=date_sub,
                    font=("Segoe UI", 7),
                    fill="#FFE5DC",
                )
            else:
                lbl_color = t["accent"] if d_obj == today else t["text_sec"]
                cv.create_text(
                    cx,
                    base_y + 13,
                    text=day_label,
                    font=("Segoe UI", 8, "bold" if d_obj == today else "normal"),
                    fill=lbl_color,
                )
                cv.create_text(
                    cx,
                    base_y + 25,
                    text=date_sub,
                    font=("Segoe UI", 7),
                    fill=t["text_muted"],
                )

            self._week_bar_hitboxes.append((cx - col_w / 2, pad_top, cx + col_w / 2, h, d_obj, i))

    def _draw_hourly_chart(self) -> None:
        cv = self.hourly_canvas
        cv.delete("all")
        t = self.theme

        sel_str = self.selected_date.strftime("%Y-%m-%d")
        self.lbl_hourly_title.configure(
            text=f"SAATLİK DAĞILIM ({format_date_tr_long(self.selected_date).upper()})"
        )

        hours_data = self.db.get_hourly_usage(sel_str, demo_mode=self.demo_mode)

        w = max(560, cv.winfo_width())
        h = 115
        pad_left = 42
        pad_right = 58
        pad_top = 12
        pad_bottom = 24
        plot_w = w - pad_left - pad_right
        plot_h = h - pad_top - pad_bottom

        # Horizontal reference lines for 60 dk and 30 dk
        for mins, frac in ((60, 1.0), (30, 0.5), (0, 0.0)):
            y = pad_top + plot_h * (1.0 - frac)
            cv.create_line(pad_left, y, w - pad_right, y, fill=t["grid_line"], width=1)
            cv.create_text(
                pad_left - 8,
                y,
                text=f"{mins} dk",
                font=("Segoe UI", 7),
                fill=t["text_muted"],
                anchor="e",
            )

        col_w = plot_w / 24.0
        bar_w = max(6.0, min(18.0, col_w * 0.64))
        self._hourly_bar_hitboxes.clear()

        for hr, sec in enumerate(hours_data):
            cx = pad_left + col_w * (hr + 0.5)
            bx1 = cx - bar_w / 2.0
            bx2 = cx + bar_w / 2.0
            base_y = pad_top + plot_h

            draw_rounded_rect(
                cv, bx1, pad_top, bx2, base_y, r=3, fill=t["bar_track"], outline=""
            )

            if sec > 0:
                ratio = min(1.0, sec / 3600.0)
                bh = max(3.0, plot_h * ratio)
                by1 = base_y - bh
                is_hov = hr == self._hovered_hour_idx
                color = t["accent"] if is_hov else t["bar_hourly"]
                draw_rounded_rect(cv, bx1, by1, bx2, base_y, r=3, fill=color, outline="")

            if hr % 3 == 0:
                cv.create_text(
                    cx,
                    base_y + 11,
                    text=f"{hr:02d}:00",
                    font=("Segoe UI", 7),
                    fill=t["text_muted"],
                )

            self._hourly_bar_hitboxes.append((cx - col_w / 2, pad_top, cx + col_w / 2, h, hr, sec))

    def _populate_apps_list(self) -> None:
        t = self.theme
        for child in self.apps_card.winfo_children():
            child.destroy()

        sel_str = self.selected_date.strftime("%Y-%m-%d")
        apps = self.db.get_app_usage(sel_str, limit=6, demo_mode=self.demo_mode)
        total_day_sec = max(
            1,
            int(
                self.db.get_day_summary(sel_str, demo_mode=self.demo_mode).get(
                    "active_seconds", 0
                )
            ),
        )

        if not apps:
            tk.Label(
                self.apps_card,
                text="Seçili gün için henüz uygulama kullanım verisi kaydedilmedi.",
                font=("Segoe UI", 9),
                fg=t["text_muted"],
                bg=t["card_bg"],
                pady=8,
            ).pack()
            return

        palette = [t["accent"], t["blue"], t["green"], t["amber"], "#9141AC", "#E66100"]

        for idx, app in enumerate(apps):
            name = app["friendly_name"]
            exe = app["exe_name"]
            sec = int(app["active_seconds"])
            pct = min(100, int(round((sec / float(total_day_sec)) * 100)))
            bar_color = palette[idx % len(palette)]

            row = tk.Frame(self.apps_card, bg=t["card_bg"], pady=5)
            row.pack(fill="x")

            top = tk.Frame(row, bg=t["card_bg"])
            top.pack(fill="x")

            tk.Label(
                top,
                text=f"{name}",
                font=("Segoe UI", 9, "bold"),
                fg=t["text"],
                bg=t["card_bg"],
            ).pack(side="left")

            tk.Label(
                top,
                text=f"({exe})",
                font=("Segoe UI", 8),
                fg=t["text_muted"],
                bg=t["card_bg"],
            ).pack(side="left", padx=(6, 0))

            tk.Label(
                top,
                text=f"{format_duration_tr(sec, include_seconds=(sec < 60))}  ·  %{pct}",
                font=("Segoe UI", 9, "bold"),
                fg=t["text_sec"],
                bg=t["card_bg"],
            ).pack(side="right")

            bar_cv = tk.Canvas(
                row, height=7, bg=t["card_bg"], highlightthickness=0, bd=0
            )
            bar_cv.pack(fill="x", pady=(3, 0))
            bar_cv.update_idletasks()
            w = max(300, self.apps_card.winfo_width() - 40)
            draw_rounded_rect(bar_cv, 0, 0, w, 7, r=3, fill=t["bar_track"], outline="")
            fill_w = max(6, int(w * min(1.0, sec / float(total_day_sec))))
            draw_rounded_rect(bar_cv, 0, 0, fill_w, 7, r=3, fill=bar_color, outline="")

    # =========================================================================
    # User Interaction Handlers
    # =========================================================================
    def _on_weekly_chart_click(self, event: tk.Event) -> None:
        for x1, _y1, x2, _y2, d_obj, _idx in self._week_bar_hitboxes:
            if x1 <= event.x <= x2:
                self.selected_date = d_obj
                self.refresh_all()
                break

    def _on_weekly_chart_hover(self, event: tk.Event) -> None:
        hovered = None
        for x1, _y1, x2, _y2, _d_obj, idx in self._week_bar_hitboxes:
            if x1 <= event.x <= x2:
                hovered = idx
                break
        if hovered != self._hovered_week_idx:
            self._hovered_week_idx = hovered
            self._draw_weekly_chart()

    def _on_weekly_chart_leave(self, _event: tk.Event) -> None:
        if self._hovered_week_idx is not None:
            self._hovered_week_idx = None
            self._draw_weekly_chart()

    def _on_hourly_chart_hover(self, event: tk.Event) -> None:
        hovered = None
        hovered_sec = 0
        for x1, _y1, x2, _y2, hr, sec in self._hourly_bar_hitboxes:
            if x1 <= event.x <= x2:
                hovered = hr
                hovered_sec = sec
                break
        if hovered != self._hovered_hour_idx:
            self._hovered_hour_idx = hovered
            if hovered is not None:
                self.lbl_hourly_hover.configure(
                    text=f"{hovered:02d}:00 – {hovered:02d}:59  →  {format_duration_tr(hovered_sec, include_seconds=(0 < hovered_sec < 60))}"
                )
            else:
                self.lbl_hourly_hover.configure(text="")
            self._draw_hourly_chart()

    def _on_hourly_chart_leave(self, _event: tk.Event) -> None:
        self._hovered_hour_idx = None
        self.lbl_hourly_hover.configure(text="")
        self._draw_hourly_chart()

    def _prev_week(self) -> None:
        self.current_week_monday -= timedelta(days=7)
        self.selected_date = self.current_week_monday
        self.refresh_all()

    def _next_week(self) -> None:
        today_monday = date.today() - timedelta(days=date.today().weekday())
        if self.current_week_monday < today_monday:
            self.current_week_monday += timedelta(days=7)
            self.selected_date = min(date.today(), self.current_week_monday)
            self.refresh_all()

    def _go_to_today(self) -> None:
        self.selected_date = date.today()
        self.current_week_monday = self.selected_date - timedelta(
            days=self.selected_date.weekday()
        )
        self.refresh_all()

    def _on_click_pause(self) -> None:
        self.tracker.toggle_pause()
        self.refresh_live_metrics()

    def _adjust_daily_limit(self, delta_minutes: int) -> None:
        cur = int(self.db.get_setting("daily_limit_minutes", "480"))
        new_val = max(30, min(16 * 60, cur + delta_minutes))
        self.db.set_setting("daily_limit_minutes", new_val)
        self.tracker.reload_settings()
        self.lbl_limit_val.configure(text=format_duration_tr(new_val * 60))
        self.refresh_all()

    def _on_toggle_daily_limit(self, enabled: bool) -> None:
        self.db.set_setting("daily_limit_enabled", enabled)
        self.tracker.reload_settings()
        self.refresh_all()

    def _on_toggle_grayscale_setting(self, enabled: bool) -> None:
        self.db.set_setting("grayscale_on_limit", enabled)
        self.tracker.reload_settings()
        if not enabled and is_windows_grayscale_active():
            set_windows_grayscale(False)

    def _test_grayscale_toggle(self) -> None:
        currently_gray = is_windows_grayscale_active()
        set_windows_grayscale(not currently_gray)

    def _on_toggle_eye_break(self, enabled: bool) -> None:
        self.db.set_setting("eye_break_enabled", enabled)
        self.tracker.reload_settings()

    def _cycle_eye_interval(self) -> None:
        options = [15, 20, 30, 45, 60]
        cur = int(self.db.get_setting("eye_break_interval_minutes", "30"))
        idx = (options.index(cur) + 1) % len(options) if cur in options else 2
        new_val = options[idx]
        self.db.set_setting("eye_break_interval_minutes", new_val)
        self.tracker.reload_settings()
        self.btn_eye_interval.configure(text=f"Her {new_val} dk")

    def _on_toggle_move_break(self, enabled: bool) -> None:
        self.db.set_setting("movement_break_enabled", enabled)
        self.tracker.reload_settings()

    def _cycle_move_interval(self) -> None:
        options = [30, 45, 60, 90, 120]
        cur = int(self.db.get_setting("movement_break_interval_minutes", "60"))
        idx = (options.index(cur) + 1) % len(options) if cur in options else 2
        new_val = options[idx]
        self.db.set_setting("movement_break_interval_minutes", new_val)
        self.tracker.reload_settings()
        self.btn_move_interval.configure(text=f"Her {new_val} dk")

    def _cycle_idle_threshold(self) -> None:
        options_sec = [60, 180, 300, 600, 900]
        cur = int(self.db.get_setting("idle_threshold_seconds", "180"))
        idx = (options_sec.index(cur) + 1) % len(options_sec) if cur in options_sec else 1
        new_sec = options_sec[idx]
        self.db.set_setting("idle_threshold_seconds", new_sec)
        self.tracker.reload_settings()
        self.btn_idle_threshold.configure(text=f"{new_sec // 60} Dakika")

    def _on_toggle_startup(self, enabled: bool) -> None:
        ok = set_startup_enabled(enabled)
        if not ok:
            self.sw_startup.set_value(not enabled, notify=False)

    def _export_csv_dialog(self) -> None:
        default_name = f"ubuntu_ekran_suresi_{date.today().strftime('%Y-%m-%d')}.csv"
        target = filedialog.asksaveasfilename(
            parent=self.root,
            title="Ekran Süresi Verilerini CSV Olarak Kaydet",
            defaultextension=".csv",
            initialfile=default_name,
            filetypes=[("CSV Dosyası", "*.csv"), ("Tüm Dosyalar", "*.*")],
        )
        if target:
            out = self.db.export_to_csv(Path(target))
            messagebox.showinfo(
                "Dışa Aktarma Tamamlandı",
                f"Ekran süresi geçmişiniz başarıyla kaydedildi:\n{out}",
                parent=self.root,
            )

    def _reset_today_confirm(self) -> None:
        ans = messagebox.askyesno(
            "Bugünkü Veriyi Sıfırla",
            "Bugüne ait ekran süresi ve uygulama kullanım kayıtlarını sıfırlamak istediğinize emin misiniz?",
            parent=self.root,
        )
        if ans:
            self.db.reset_today()
            self.tracker.reset_break_timers()
            self.refresh_all()
