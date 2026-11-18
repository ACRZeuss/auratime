"""
SQLite storage engine for Ubuntu Screen Time on Windows.
Stores daily screen time, 24-hour hourly breakdown, per-application usage,
and user wellbeing settings with thread-safe access.
"""

from __future__ import annotations

from contextlib import closing
import csv
from datetime import date, datetime, timedelta
import math
from pathlib import Path
import sqlite3
import threading
from typing import Any


DEFAULT_SETTINGS: dict[str, str] = {
    "idle_threshold_seconds": "180",     # 3 minutes without mouse/keyboard -> Idle
    "daily_limit_enabled": "1",          # Daily screen time limit active
    "daily_limit_minutes": "480",        # 8 hours (480 min) default limit like GNOME Wellbeing
    "grayscale_on_limit": "0",           # Turn screen grayscale when limit reached
    "eye_break_enabled": "1",            # Eye break (20-20-20 / short break) reminders
    "eye_break_interval_minutes": "30",  # Every 30 minutes of continuous screen time
    "movement_break_enabled": "1",       # Movement / stretch break reminders
    "movement_break_interval_minutes": "60",  # Every 60 minutes of continuous screen time
    "theme": "dark",                     # Ubuntu Yaru Dark ("dark") or Light ("light")
}


class ScreenTimeDB:
    def __init__(self, db_path: Path | None = None) -> None:
        if db_path is None:
            base_dir = Path(__file__).resolve().parent / "data"
            base_dir.mkdir(parents=True, exist_ok=True)
            db_path = base_dir / "screentime.db"
        else:
            db_path.parent.mkdir(parents=True, exist_ok=True)

        self.db_path = db_path
        self._lock = threading.RLock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_schema(self) -> None:
        with self._lock, closing(self._connect()) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS daily_usage (
                    date TEXT PRIMARY KEY,
                    active_seconds INTEGER NOT NULL DEFAULT 0,
                    idle_seconds INTEGER NOT NULL DEFAULT 0,
                    locked_seconds INTEGER NOT NULL DEFAULT 0,
                    first_active TEXT,
                    last_active TEXT
                );

                CREATE TABLE IF NOT EXISTS hourly_usage (
                    date TEXT NOT NULL,
                    hour INTEGER NOT NULL,
                    active_seconds INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (date, hour)
                );

                CREATE TABLE IF NOT EXISTS app_usage (
                    date TEXT NOT NULL,
                    exe_name TEXT NOT NULL,
                    friendly_name TEXT NOT NULL,
                    active_seconds INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (date, exe_name)
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            for k, v in DEFAULT_SETTINGS.items():
                conn.execute(
                    "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                    (k, v),
                )
            conn.commit()

    def record_tick(
        self,
        dt: datetime,
        state: str,
        elapsed_seconds: int = 1,
        exe_name: str = "",
        friendly_name: str = "",
    ) -> None:
        """
        Record elapsed seconds for the given timestamp and state ('ACTIVE', 'IDLE', 'LOCKED').
        Caps hourly bucket at 3600 seconds and daily bucket at 86400 seconds.
        """
        if elapsed_seconds <= 0:
            return

        day_str = dt.strftime("%Y-%m-%d")
        time_str = dt.strftime("%H:%M:%S")
        hour = dt.hour

        with self._lock, closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO daily_usage (date, active_seconds, idle_seconds, locked_seconds, first_active, last_active)
                VALUES (?, 0, 0, 0, NULL, NULL)
                ON CONFLICT(date) DO NOTHING
                """,
                (day_str,),
            )

            if state == "ACTIVE":
                conn.execute(
                    """
                    UPDATE daily_usage
                    SET active_seconds = MIN(86400, active_seconds + ?),
                        first_active = COALESCE(first_active, ?),
                        last_active = ?
                    WHERE date = ?
                    """,
                    (elapsed_seconds, time_str, time_str, day_str),
                )
                conn.execute(
                    """
                    INSERT INTO hourly_usage (date, hour, active_seconds)
                    VALUES (?, ?, ?)
                    ON CONFLICT(date, hour) DO UPDATE SET
                        active_seconds = MIN(3600, active_seconds + excluded.active_seconds)
                    """,
                    (day_str, hour, elapsed_seconds),
                )
                if exe_name:
                    conn.execute(
                        """
                        INSERT INTO app_usage (date, exe_name, friendly_name, active_seconds)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(date, exe_name) DO UPDATE SET
                            active_seconds = active_seconds + excluded.active_seconds,
                            friendly_name = excluded.friendly_name
                        """,
                        (day_str, exe_name, friendly_name or exe_name, elapsed_seconds),
                    )
            elif state == "IDLE":
                conn.execute(
                    """
                    UPDATE daily_usage
                    SET idle_seconds = MIN(86400, idle_seconds + ?)
                    WHERE date = ?
                    """,
                    (elapsed_seconds, day_str),
                )
            elif state == "LOCKED":
                conn.execute(
                    """
                    UPDATE daily_usage
                    SET locked_seconds = MIN(86400, locked_seconds + ?)
                    WHERE date = ?
                    """,
                    (elapsed_seconds, day_str),
                )
            conn.commit()

    def get_day_summary(self, day_str: str, demo_mode: bool = False) -> dict[str, Any]:
        """Return active_seconds, idle_seconds, locked_seconds, first_active, last_active for a date."""
        if demo_mode:
            return self._generate_demo_day_summary(day_str)

        with self._lock, closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM daily_usage WHERE date = ?",
                (day_str,),
            ).fetchone()
            if not row:
                return {
                    "date": day_str,
                    "active_seconds": 0,
                    "idle_seconds": 0,
                    "locked_seconds": 0,
                    "first_active": None,
                    "last_active": None,
                }
            return dict(row)

    def get_week_usage(self, monday_date: date, demo_mode: bool = False) -> list[dict[str, Any]]:
        """
        Return 7 items (Monday..Sunday) for the week starting at monday_date.
        Each item has: date (YYYY-MM-DD), date_obj, weekday_idx (0..6), active_seconds, idle_seconds.
        """
        days = [monday_date + timedelta(days=i) for i in range(7)]
        if demo_mode:
            result = []
            for i, d in enumerate(days):
                ds = d.strftime("%Y-%m-%d")
                summary = self._generate_demo_day_summary(ds)
                result.append(
                    {
                        "date": ds,
                        "date_obj": d,
                        "weekday_idx": i,
                        "active_seconds": summary["active_seconds"],
                        "idle_seconds": summary["idle_seconds"],
                        "locked_seconds": summary["locked_seconds"],
                    }
                )
            return result

        start_str = days[0].strftime("%Y-%m-%d")
        end_str = days[-1].strftime("%Y-%m-%d")

        with self._lock, closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT date, active_seconds, idle_seconds, locked_seconds
                FROM daily_usage
                WHERE date BETWEEN ? AND ?
                """,
                (start_str, end_str),
            ).fetchall()
            by_date = {r["date"]: dict(r) for r in rows}

        result = []
        for i, d in enumerate(days):
            ds = d.strftime("%Y-%m-%d")
            info = by_date.get(ds, {})
            result.append(
                {
                    "date": ds,
                    "date_obj": d,
                    "weekday_idx": i,
                    "active_seconds": int(info.get("active_seconds", 0)),
                    "idle_seconds": int(info.get("idle_seconds", 0)),
                    "locked_seconds": int(info.get("locked_seconds", 0)),
                }
            )
        return result

    def get_hourly_usage(self, day_str: str, demo_mode: bool = False) -> list[int]:
        """Return list of 24 integers (active_seconds for each hour 0..23) on day_str."""
        if demo_mode:
            return self._generate_demo_hourly(day_str)

        hours = [0] * 24
        with self._lock, closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT hour, active_seconds FROM hourly_usage WHERE date = ?",
                (day_str,),
            ).fetchall()
            for r in rows:
                h = int(r["hour"])
                if 0 <= h < 24:
                    hours[h] = int(r["active_seconds"])
        return hours

    def get_app_usage(self, day_str: str, limit: int = 8, demo_mode: bool = False) -> list[dict[str, Any]]:
        """Return top applications used on day_str sorted by active_seconds descending."""
        if demo_mode:
            return self._generate_demo_apps(day_str)[:limit]

        with self._lock, closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT exe_name, friendly_name, active_seconds
                FROM app_usage
                WHERE date = ? AND active_seconds > 0
                ORDER BY active_seconds DESC
                LIMIT ?
                """,
                (day_str, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_all_settings(self) -> dict[str, str]:
        with self._lock, closing(self._connect()) as conn:
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
            res = dict(DEFAULT_SETTINGS)
            for r in rows:
                res[r["key"]] = r["value"]
            return res

    def get_setting(self, key: str, default: str = "") -> str:
        with self._lock, closing(self._connect()) as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            if row:
                return str(row["value"])
            return DEFAULT_SETTINGS.get(key, default)

    def set_setting(self, key: str, value: str | int | bool) -> None:
        if isinstance(value, bool):
            val_str = "1" if value else "0"
        else:
            val_str = str(value)
        with self._lock, closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, val_str),
            )
            conn.commit()

    def export_to_csv(self, output_path: Path) -> Path:
        """Export all daily usage and top app usage to a UTF-8 CSV file."""
        with self._lock, closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT date, active_seconds, idle_seconds, locked_seconds, first_active, last_active
                FROM daily_usage
                ORDER BY date DESC
                """
            ).fetchall()

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "Tarih",
                    "Aktif Süre (Saniye)",
                    "Aktif Süre (Saat:Dakika)",
                    "Boşta Süre (Saniye)",
                    "Kilitli Süre (Saniye)",
                    "İlk Etkinlik",
                    "Son Etkinlik",
                ]
            )
            for r in rows:
                act = int(r["active_seconds"])
                h, rem = divmod(act, 3600)
                m = rem // 60
                writer.writerow(
                    [
                        r["date"],
                        act,
                        f"{h:02d}:{m:02d}",
                        r["idle_seconds"],
                        r["locked_seconds"],
                        r["first_active"] or "-",
                        r["last_active"] or "-",
                    ]
                )
        return output_path

    def reset_today(self) -> None:
        """Clear today's counters if the user requests a reset."""
        today_str = date.today().strftime("%Y-%m-%d")
        with self._lock, closing(self._connect()) as conn:
            conn.execute("DELETE FROM daily_usage WHERE date = ?", (today_str,))
            conn.execute("DELETE FROM hourly_usage WHERE date = ?", (today_str,))
            conn.execute("DELETE FROM app_usage WHERE date = ?", (today_str,))
            conn.commit()

    # --- Non-Destructive Demo Preview Generators ---

    def _generate_demo_day_summary(self, day_str: str) -> dict[str, Any]:
        today = date.today()
        try:
            d = datetime.strptime(day_str, "%Y-%m-%d").date()
        except ValueError:
            d = today

        if d > today:
            return {
                "date": day_str,
                "active_seconds": 0,
                "idle_seconds": 0,
                "locked_seconds": 0,
                "first_active": None,
                "last_active": None,
            }

        hours = self._generate_demo_hourly(day_str)
        total_active = sum(hours)
        return {
            "date": day_str,
            "active_seconds": total_active,
            "idle_seconds": int(total_active * 0.18),
            "locked_seconds": int(total_active * 0.25),
            "first_active": "09:12:04" if total_active > 0 else None,
            "last_active": "22:45:19" if total_active > 0 else None,
        }

    def _generate_demo_hourly(self, day_str: str) -> list[int]:
        today = date.today()
        try:
            d = datetime.strptime(day_str, "%Y-%m-%d").date()
        except ValueError:
            d = today

        if d > today:
            return [0] * 24

        seed = d.toordinal()
        is_weekend = d.weekday() >= 5
        hours = [0] * 24
        max_hour = datetime.now().hour if d == today else 23

        for h in range(24):
            if h > max_hour:
                hours[h] = 0
                continue
            if 1 <= h <= 7:
                hours[h] = 0
                continue
            wave = math.sin((h - 8) * 0.45 + (seed % 7))
            if is_weekend:
                base = 1600 if 11 <= h <= 22 else 400
            else:
                base = 2400 if (9 <= h <= 12 or 14 <= h <= 18) else 1100
            val = int(max(0, min(3450, base + wave * 950 + ((seed * 37 + h * 101) % 500))))
            hours[h] = val
        return hours

    def _generate_demo_apps(self, day_str: str) -> list[dict[str, Any]]:
        total = self._generate_demo_day_summary(day_str)["active_seconds"]
        if total <= 0:
            return []
        shares = [
            ("code.exe", "Visual Studio Code", 0.36),
            ("firefox.exe", "Mozilla Firefox", 0.28),
            ("windowsterminal.exe", "Windows Terminal", 0.14),
            ("discord.exe", "Discord", 0.10),
            ("spotify.exe", "Spotify", 0.07),
            ("explorer.exe", "Windows Gezgini", 0.05),
        ]
        return [
            {
                "exe_name": exe,
                "friendly_name": name,
                "active_seconds": int(total * ratio),
            }
            for exe, name, ratio in shares
        ]
