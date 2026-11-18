"""
Ubuntu Screen Time (GNOME Wellbeing / Ekran Süresi) for Windows.
Main entry point coordinating the background screen time tracker,
SQLite persistence, native Win32 System Tray icon, and GNOME-style desktop UI.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tkinter as tk

from database import ScreenTimeDB
from tracker import ScreenTimeTracker
from tray import SystemTrayIcon, signal_existing_instance
from ui import UbuntuScreenTimeWindow
from win_api import (
    enable_dpi_awareness,
    ensure_app_icon,
    get_bundle_dir,
    get_user_data_dir,
)


def run_app(start_minimized: bool = False) -> int:
    enable_dpi_awareness()

    # Single-instance check: if already running in system tray, bring existing window to front
    if signal_existing_instance():
        return 0

    bundle_dir = get_bundle_dir()
    data_dir = get_user_data_dir()
    icon_path = ensure_app_icon(bundle_dir / "assets" / "auratime.ico")
    db = ScreenTimeDB(data_dir / "screentime.db")

    root = tk.Tk()
    tray_holder: list[SystemTrayIcon] = []
    window_holder: list[UbuntuScreenTimeWindow] = []

    def on_notify(title: str, message: str, warning: bool = False) -> None:
        if tray_holder:
            tray_holder[0].show_notification(title, message, warning=warning)

    def on_break_due(break_type: str, duration_sec: int) -> None:
        if window_holder:
            window_holder[0].trigger_break_overlay(break_type, duration_sec)

    tracker = ScreenTimeTracker(
        db=db,
        on_notify=on_notify,
        on_break_due=on_break_due,
    )

    def quit_application() -> None:
        tracker.stop()
        if tray_holder:
            tray_holder[0].stop()
        root.after(0, root.destroy)

    win = UbuntuScreenTimeWindow(
        root=root,
        db=db,
        tracker=tracker,
        icon_path=icon_path,
        on_quit_app=quit_application,
        start_minimized=start_minimized,
    )
    window_holder.append(win)

    tray = SystemTrayIcon(
        icon_path=icon_path,
        on_open=win.show_window,
        on_toggle_pause=lambda: (tracker.toggle_pause(), root.after(0, win.refresh_live_metrics)),
        on_take_break=lambda: win.trigger_break_overlay("eye", 20),
        on_exit=quit_application,
        get_status_label=tracker.get_status_summary_text,
        is_paused_fn=tracker.is_paused,
    )
    tray_holder.append(tray)

    tray.start()
    tracker.start()

    # Record initial active second immediately so the user sees instant activity on launch
    tracker._process_tick(1)
    win.refresh_all()

    def update_tray_tooltip_loop() -> None:
        if root.winfo_exists():
            tray.update_tooltip(f"AuraTime — {tracker.get_status_summary_text()}")
            root.after(5000, update_tray_tooltip_loop)

    root.after(2000, update_tray_tooltip_loop)

    try:
        root.mainloop()
    finally:
        tracker.stop()
        tray.stop()

    return 0


def run_self_test() -> int:
    """Verify Win32 API calls, SQLite DB operations, icon generation, and tracker ticks."""
    from datetime import date, datetime
    import tempfile
    from win_api import get_foreground_app, get_idle_seconds, is_workstation_locked

    print("[1/4] Testing Win32 API integration...")
    idle_s = get_idle_seconds()
    locked = is_workstation_locked()
    exe, friendly, title = get_foreground_app()
    print(f"      Idle: {idle_s:.2f}s | Locked: {locked} | Foreground: {friendly} ({exe})")

    print("[2/4] Testing AuraTime logo & multi-size icon generator...")
    base_dir = Path(__file__).resolve().parent
    ico = ensure_app_icon(base_dir / "assets" / "auratime.ico")
    assert ico.exists() and ico.stat().st_size > 5000, "ICO file generation failed"
    print(f"      Generated icon: {ico} ({ico.stat().st_size} bytes)")

    print("[3/4] Testing SQLite database & ScreenTimeTracker...")
    with tempfile.TemporaryDirectory() as tmp:
        test_db = ScreenTimeDB(Path(tmp) / "test_screentime.db")
        tracker = ScreenTimeTracker(db=test_db)
        now = datetime.now()
        test_db.record_tick(now, "ACTIVE", elapsed_seconds=125, exe_name="code.exe", friendly_name="Visual Studio Code")
        test_db.record_tick(now, "IDLE", elapsed_seconds=30)

        today_str = date.today().strftime("%Y-%m-%d")
        summary = test_db.get_day_summary(today_str)
        assert summary["active_seconds"] == 125, f"Expected 125, got {summary['active_seconds']}"
        assert summary["idle_seconds"] == 30, f"Expected 30, got {summary['idle_seconds']}"

        hourly = test_db.get_hourly_usage(today_str)
        assert hourly[now.hour] == 125

        apps = test_db.get_app_usage(today_str)
        assert len(apps) == 1 and apps[0]["exe_name"] == "code.exe"

        demo_week = test_db.get_week_usage(date.today(), demo_mode=True)
        assert len(demo_week) == 7
        print("      SQLite daily, hourly, app, and demo queries verified.")

    print("[4/4] All self-tests passed!")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="AuraTime — Dijital Denge & Ekran Süresi (Windows)"
    )
    parser.add_argument(
        "--minimized",
        action="store_true",
        help="Start minimized in the Windows System Tray",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run automated self-test and exit",
    )
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()
    return run_app(start_minimized=args.minimized)


if __name__ == "__main__":
    sys.exit(main())
