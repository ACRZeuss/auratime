"""
Core Screen Time & Wellbeing tracking engine for Windows (modeled on Ubuntu / GNOME Wellbeing).
Runs a 1-second background loop that:
- Detects ACTIVE vs IDLE vs LOCKED vs PAUSED states
- Filters out system sleep / hibernate jumps so sleep time is never counted as active time
- Logs daily, hourly, and per-application screen time into SQLite
- Tracks continuous active session duration for Eye & Movement Break reminders
- Enforces Daily Screen Time Limit notifications and optional Windows Grayscale filter
"""

from __future__ import annotations

from datetime import date, datetime
import threading
import time
from typing import Callable

from database import ScreenTimeDB
from win_api import (
    get_foreground_app,
    get_idle_seconds,
    is_workstation_locked,
    set_windows_grayscale,
)


def format_duration_tr(seconds: int, include_seconds: bool = False) -> str:
    """Format seconds into Ubuntu Turkish style, e.g. '4 sa 25 dk' or '38 dk'."""
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)

    if include_seconds:
        if hours > 0:
            return f"{hours} sa {minutes} dk {secs} sn"
        if minutes > 0:
            return f"{minutes} dk {secs} sn"
        return f"{secs} sn"

    if hours > 0 and minutes > 0:
        return f"{hours} sa {minutes} dk"
    if hours > 0:
        return f"{hours} sa"
    if minutes > 0:
        return f"{minutes} dk"
    return f"{secs} sn" if seconds > 0 else "0 dk"


class ScreenTimeTracker:
    def __init__(
        self,
        db: ScreenTimeDB,
        on_notify: Callable[[str, str, bool], None] | None = None,
        on_break_due: Callable[[str, int], None] | None = None,
    ) -> None:
        self.db = db
        self.on_notify = on_notify
        self.on_break_due = on_break_due

        self._running = False
        self._paused = False
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()

        # Live runtime metrics
        self.current_state: str = "ACTIVE"  # ACTIVE, IDLE, LOCKED, PAUSED
        self.current_idle_seconds: float = 0.0
        self.current_app_exe: str = ""
        self.current_app_name: str = ""
        self.current_window_title: str = ""

        # Continuous session & break counters
        self.continuous_active_seconds: int = 0
        self._eye_break_counter: int = 0
        self._movement_break_counter: int = 0
        self._consecutive_non_active_seconds: int = 0

        # Daily limit notification state (keyed by YYYY-MM-DD)
        self._warned_15m_date: str = ""
        self._limit_reached_date: str = ""

        # Cached settings (refreshed periodically or on settings update)
        self.settings: dict[str, str] = self.db.get_all_settings()

    def reload_settings(self) -> None:
        with self._lock:
            old_limit = self.settings.get("daily_limit_minutes")
            self.settings = self.db.get_all_settings()
            if self.settings.get("daily_limit_minutes") != old_limit:
                # Allow re-triggering limit alert if user changed the daily limit
                self._limit_reached_date = ""
                self._warned_15m_date = ""

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="ScreenTimeTrackerThread", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def is_paused(self) -> bool:
        return self._paused

    def set_paused(self, paused: bool) -> None:
        with self._lock:
            self._paused = paused
            if paused:
                self.current_state = "PAUSED"

    def toggle_pause(self) -> bool:
        with self._lock:
            self._paused = not self._paused
            if self._paused:
                self.current_state = "PAUSED"
            return self._paused

    def reset_break_timers(self) -> None:
        """Reset continuous break counters after the user completes or dismisses a break."""
        with self._lock:
            self.continuous_active_seconds = 0
            self._eye_break_counter = 0
            self._movement_break_counter = 0

    def get_today_active_seconds(self, demo_mode: bool = False) -> int:
        today_str = date.today().strftime("%Y-%m-%d")
        summary = self.db.get_day_summary(today_str, demo_mode=demo_mode)
        return int(summary.get("active_seconds", 0))

    def get_status_summary_text(self) -> str:
        active_sec = self.get_today_active_seconds()
        dur_str = format_duration_tr(active_sec)
        state_map = {
            "ACTIVE": "Aktif",
            "IDLE": "Boşta",
            "LOCKED": "Kilitli",
            "PAUSED": "Duraklatıldı",
        }
        st = state_map.get(self.current_state, "Aktif")
        return f"Bugün: {dur_str} ({st})"

    def _loop(self) -> None:
        last_monotonic = time.monotonic()
        tick_count = 0

        while self._running:
            time.sleep(1.0)
            now_mono = time.monotonic()
            raw_elapsed = now_mono - last_monotonic
            last_monotonic = now_mono

            # If raw_elapsed > 5s, the PC likely woke from sleep/hibernation or heavy freeze.
            # Never credit sleep time as active screen time.
            elapsed = 1 if raw_elapsed > 5.0 else max(1, int(round(raw_elapsed)))

            tick_count += 1
            if tick_count % 10 == 0:
                self.reload_settings()

            self._process_tick(elapsed)

    def _process_tick(self, elapsed: int) -> None:
        now_dt = datetime.now()
        today_str = now_dt.strftime("%Y-%m-%d")

        with self._lock:
            if self._paused:
                self.current_state = "PAUSED"
                return

            idle_threshold = max(30, int(self.settings.get("idle_threshold_seconds", "180")))
            idle_sec = get_idle_seconds()
            self.current_idle_seconds = idle_sec

            if is_workstation_locked():
                state = "LOCKED"
                exe_name, friendly_name, title = "", "", ""
            elif idle_sec >= idle_threshold:
                state = "IDLE"
                exe_name, friendly_name, title = "", "", ""
            else:
                state = "ACTIVE"
                exe_name, friendly_name, title = get_foreground_app()

            self.current_state = state
            self.current_app_exe = exe_name
            self.current_app_name = friendly_name
            self.current_window_title = title

        # Save to SQLite
        self.db.record_tick(
            dt=now_dt,
            state=state,
            elapsed_seconds=elapsed,
            exe_name=exe_name,
            friendly_name=friendly_name,
        )

        # Update continuous active session & break timers
        if state == "ACTIVE":
            self._consecutive_non_active_seconds = 0
            self.continuous_active_seconds += elapsed
            self._eye_break_counter += elapsed
            self._movement_break_counter += elapsed
            self._check_breaks()
            self._check_daily_limit(today_str)
        else:
            self._consecutive_non_active_seconds += elapsed
            # Natural break of 3+ minutes resets continuous active session timers
            if self._consecutive_non_active_seconds >= 180:
                self.continuous_active_seconds = 0
                self._eye_break_counter = 0
                self._movement_break_counter = 0

    def _check_breaks(self) -> None:
        eye_enabled = self.settings.get("eye_break_enabled", "1") == "1"
        eye_interval_min = max(5, int(self.settings.get("eye_break_interval_minutes", "30")))

        move_enabled = self.settings.get("movement_break_enabled", "1") == "1"
        move_interval_min = max(10, int(self.settings.get("movement_break_interval_minutes", "60")))

        # Check Movement Break first if due
        if move_enabled and self._movement_break_counter >= move_interval_min * 60:
            self._movement_break_counter = 0
            self._eye_break_counter = 0
            if self.on_notify:
                self.on_notify(
                    "AuraTime · Hareket Molası Zamanı",
                    f"{move_interval_min} dakikadır aralıksız ekran başındasınız. Kısa bir yürüyüş veya esneme molası verin.",
                    False,
                )
            if self.on_break_due:
                self.on_break_due("movement", 120)
            return

        # Check Eye Break (20-20-20 rule)
        if eye_enabled and self._eye_break_counter >= eye_interval_min * 60:
            self._eye_break_counter = 0
            if self.on_notify:
                self.on_notify(
                    "AuraTime · Göz Dinlendirme Molası (20-20-20)",
                    f"{eye_interval_min} dakikadır ekran başındasınız. 20 saniye boyunca 6 metre uzağa odaklanarak gözlerinizi dinlendirin.",
                    False,
                )
            if self.on_break_due:
                self.on_break_due("eye", 20)

    def _check_daily_limit(self, today_str: str) -> None:
        limit_enabled = self.settings.get("daily_limit_enabled", "1") == "1"
        if not limit_enabled:
            return

        limit_minutes = max(15, int(self.settings.get("daily_limit_minutes", "480")))
        limit_seconds = limit_minutes * 60
        active_seconds = self.get_today_active_seconds(demo_mode=False)

        # 15-minute warning before reaching limit
        remaining = limit_seconds - active_seconds
        if 0 < remaining <= 900 and self._warned_15m_date != today_str and limit_minutes > 30:
            self._warned_15m_date = today_str
            if self.on_notify:
                self.on_notify(
                    "AuraTime · Ekran Süresi Sınırı Yaklaşıyor",
                    f"Günlük {format_duration_tr(limit_seconds)} ekran süresi sınırınıza 15 dakika kaldı.",
                    False,
                )

        # Limit reached
        if active_seconds >= limit_seconds and self._limit_reached_date != today_str:
            self._limit_reached_date = today_str
            grayscale = self.settings.get("grayscale_on_limit", "0") == "1"
            if grayscale:
                set_windows_grayscale(True)

            if self.on_notify:
                extra = " Ekran gri tonlamaya geçirildi." if grayscale else ""
                self.on_notify(
                    "AuraTime · Günlük Ekran Süresi Sınırı Doldu",
                    f"Bugünkü {format_duration_tr(limit_seconds)} ekran süresi sınırınıza ulaştınız.{extra}",
                    True,
                )
