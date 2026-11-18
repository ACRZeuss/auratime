"""
Windows API (Win32) integration via ctypes for Ubuntu Screen Time on Windows.
Provides:
- User input idle detection (GetLastInputInfo)
- Workstation lock / screensaver detection (OpenInputDesktop & process check)
- Active foreground window & application detection
- Windows 10/11 dark titlebar & DPI awareness
- Windows Startup (HKCU\\...\\Run) registry integration
- Windows Color Filter (Grayscale / Siyah-Beyaz) toggle for Screen Time Limit
- Icon generator (.ico file & Win32 HICON)
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import struct
import sys
import winreg

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
gdi32 = ctypes.windll.gdi32
shell32 = ctypes.windll.shell32

try:
    dwmapi = ctypes.windll.dwmapi
except Exception:
    dwmapi = None

try:
    shcore = ctypes.windll.shcore
except Exception:
    shcore = None


# --- Win32 Structures & Constants ---

class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("dwTime", wintypes.DWORD),
    ]


user32.GetLastInputInfo.argtypes = [ctypes.POINTER(LASTINPUTINFO)]
user32.GetLastInputInfo.restype = wintypes.BOOL

kernel32.GetTickCount.argtypes = []
kernel32.GetTickCount.restype = wintypes.DWORD

kernel32.GetTickCount64.argtypes = []
kernel32.GetTickCount64.restype = ctypes.c_ulonglong

user32.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
user32.OpenInputDesktop.restype = wintypes.HANDLE

user32.CloseDesktop.argtypes = [wintypes.HANDLE]
user32.CloseDesktop.restype = wintypes.BOOL

user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = wintypes.HWND

user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD

user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int

user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE

kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL

kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL

DESKTOP_SWITCHDESKTOP = 0x0100

FRIENDLY_APP_NAMES: dict[str, str] = {
    "explorer.exe": "Windows Gezgini",
    "code.exe": "Visual Studio Code",
    "firefox.exe": "Mozilla Firefox",
    "chrome.exe": "Google Chrome",
    "msedge.exe": "Microsoft Edge",
    "brave.exe": "Brave Browser",
    "opera.exe": "Opera",
    "windowsterminal.exe": "Windows Terminal",
    "powershell.exe": "PowerShell",
    "pwsh.exe": "PowerShell",
    "cmd.exe": "Komut İstemi",
    "notepad.exe": "Not Defteri",
    "spotify.exe": "Spotify",
    "discord.exe": "Discord",
    "slack.exe": "Slack",
    "telegram.exe": "Telegram",
    "whatsapp.exe": "WhatsApp",
    "vlc.exe": "VLC Media Player",
    "winword.exe": "Microsoft Word",
    "excel.exe": "Microsoft Excel",
    "powerpnt.exe": "Microsoft PowerPoint",
    "outlook.exe": "Microsoft Outlook",
    "teams.exe": "Microsoft Teams",
    "ms-teams.exe": "Microsoft Teams",
    "devenv.exe": "Visual Studio",
    "pycharm64.exe": "PyCharm",
    "idea64.exe": "IntelliJ IDEA",
    "taskmgr.exe": "Görev Yöneticisi",
    "systemsettings.exe": "Windows Ayarları",
    "applicationframehost.exe": "Windows Uygulaması",
    "python.exe": "Python",
    "pythonw.exe": "Python",
}

LOCK_PROCESSES = {"lockapp.exe", "logonui.exe"}


def enable_dpi_awareness() -> None:
    """Enable per-monitor DPI awareness and set Windows AppUserModelID for taskbar icon."""
    try:
        shell32.SetCurrentProcessExplicitAppUserModelID("AuraTime.DigitalWellbeing.1")
    except Exception:
        pass
    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass
    try:
        if shcore is not None:
            shcore.SetProcessDpiAwareness(2)
            return
    except Exception:
        pass
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass


def set_dark_titlebar(hwnd: int, dark: bool = True) -> None:
    """Apply Windows 10/11 dark mode attribute to a top-level window titlebar."""
    if not dwmapi or not hwnd:
        return
    try:
        value = ctypes.c_int(1 if dark else 0)
        # DWMWA_USE_IMMERSIVE_DARK_MODE = 20 (Windows 10 20H1+ & Windows 11)
        dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            ctypes.c_int(20),
            ctypes.byref(value),
            ctypes.sizeof(value),
        )
    except Exception:
        pass


def get_idle_seconds() -> float:
    """Return seconds elapsed since last keyboard or mouse input."""
    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if not user32.GetLastInputInfo(ctypes.byref(lii)):
        return 0.0
    now_tick = kernel32.GetTickCount()
    # Handle 32-bit unsigned wraparound
    elapsed_ms = (now_tick - lii.dwTime) & 0xFFFFFFFF
    return max(0.0, elapsed_ms / 1000.0)


def get_foreground_app() -> tuple[str, str, str]:
    """
    Return (exe_name_lower, friendly_name, window_title) of the active foreground window.
    Falls back to ("explorer.exe", "Windows Masaüstü", "Masaüstü") if focus is on the desktop/shell.
    """
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ("explorer.exe", "Windows Masaüstü", "Masaüstü")

    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return ("explorer.exe", "Windows Masaüstü", "Masaüstü")

    exe_name = ""
    hproc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if hproc:
        try:
            buf_len = wintypes.DWORD(1024)
            buf = ctypes.create_unicode_buffer(1024)
            if kernel32.QueryFullProcessImageNameW(hproc, 0, buf, ctypes.byref(buf_len)):
                full_path = buf.value
                exe_name = os.path.basename(full_path)
        finally:
            kernel32.CloseHandle(hproc)

    title = ""
    length = user32.GetWindowTextLengthW(hwnd)
    if length > 0:
        tbuf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, tbuf, length + 1)
        title = tbuf.value.strip()

    exe_lower = exe_name.lower()
    if not exe_lower:
        return ("", "", title)

    if exe_lower in FRIENDLY_APP_NAMES:
        friendly = FRIENDLY_APP_NAMES[exe_lower]
        if exe_lower == "applicationframehost.exe" and title:
            friendly = title.split(" - ")[-1][:40]
    else:
        stem = os.path.splitext(exe_name)[0]
        friendly = stem.replace("_", " ").replace("-", " ").title()

    return (exe_lower, friendly, title)


def is_workstation_locked() -> bool:
    """
    Detect if Windows workstation is locked or on the secure desktop (Ctrl+Alt+Del / Win+L).
    """
    # Check 1: Foreground process is LockApp.exe or LogonUI.exe
    exe_lower, _, _ = get_foreground_app()
    if exe_lower in LOCK_PROCESSES:
        return True

    # Check 2: OpenInputDesktop succeeds only when interactive user desktop is active
    hdesk = user32.OpenInputDesktop(0, False, DESKTOP_SWITCHDESKTOP)
    if not hdesk:
        return True
    user32.CloseDesktop(hdesk)
    return False


# --- App Paths & Frozen (.exe) Support ---

def is_frozen() -> bool:
    """Return True when running as a PyInstaller compiled .exe."""
    return bool(getattr(sys, "frozen", False))


def get_bundle_dir() -> Path:
    """Return directory containing bundled read-only assets (supports PyInstaller _MEIPASS)."""
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def get_user_data_dir() -> Path:
    """
    Return persistent directory for SQLite database and generated assets.
    When running as a standalone .exe, uses %LOCALAPPDATA%\\AuraTime so the .exe remains portable
    and never litters the folder where it is placed.
    """
    if is_frozen():
        local_app_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else (Path.home() / "AppData" / "Local")
        data_dir = base / "AuraTime"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir
    data_dir = Path(__file__).resolve().parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


# --- Windows Startup Registry Integration ---

STARTUP_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_APP_NAME = "AuraTime"


def get_startup_command() -> str:
    """Build the command string used to launch AuraTime silently at Windows login."""
    if is_frozen():
        exe_path = Path(sys.executable).resolve()
        return f'"{exe_path}" --minimized'
    main_script = Path(__file__).resolve().parent / "main.py"
    py_exe = Path(sys.executable)
    pythonw = py_exe.with_name("pythonw.exe")
    launcher = pythonw if pythonw.exists() else py_exe
    return f'"{launcher}" "{main_script}" --minimized'


def is_startup_enabled() -> bool:
    """Check if AuraTime is registered in HKCU Run."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REG_PATH, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, STARTUP_APP_NAME)
            return bool(val)
    except FileNotFoundError:
        return False
    except OSError:
        return False


def set_startup_enabled(enabled: bool) -> bool:
    """Enable or disable automatic launch on Windows login."""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, STARTUP_REG_PATH, 0, winreg.KEY_SET_VALUE
        ) as key:
            # Clean up legacy key name if present
            try:
                winreg.DeleteValue(key, "UbuntuScreenTime")
            except FileNotFoundError:
                pass
            if enabled:
                winreg.SetValueEx(key, STARTUP_APP_NAME, 0, winreg.REG_SZ, get_startup_command())
            else:
                try:
                    winreg.DeleteValue(key, STARTUP_APP_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False


# --- Windows Grayscale Filter (Ubuntu Screen Limit Greyscale feature) ---

COLOR_FILTER_REG_PATH = r"Software\Microsoft\ColorFiltering"


def is_windows_grayscale_active() -> bool:
    """Check if Windows built-in grayscale color filter is active."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, COLOR_FILTER_REG_PATH, 0, winreg.KEY_READ) as key:
            active, _ = winreg.QueryValueEx(key, "Active")
            filter_type, _ = winreg.QueryValueEx(key, "FilterType")
            return bool(active == 1 and filter_type == 0)
    except OSError:
        return False


def set_windows_grayscale(enable: bool) -> bool:
    """
    Toggle Windows Grayscale Color Filter (matching Ubuntu Wellbeing's grayscale screen limit).
    Configures HKCU\\Software\\Microsoft\\ColorFiltering and triggers the system hotkey or hotkey enable.
    """
    try:
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, COLOR_FILTER_REG_PATH, 0, winreg.KEY_SET_VALUE | winreg.KEY_READ
        ) as key:
            try:
                cur_active, _ = winreg.QueryValueEx(key, "Active")
            except FileNotFoundError:
                cur_active = 0

            # FilterType 0 = Grayscale
            winreg.SetValueEx(key, "FilterType", 0, winreg.REG_DWORD, 0)
            winreg.SetValueEx(key, "HotkeyEnabled", 0, winreg.REG_DWORD, 1)

            want_active = 1 if enable else 0
            if cur_active != want_active:
                # Send Win + Ctrl + C keyboard shortcut to immediately apply Windows Color Filter
                VK_LWIN = 0x5B
                VK_CONTROL = 0x11
                VK_C = 0x43
                KEYEVENTF_KEYUP = 0x0002
                user32.keybd_event(VK_LWIN, 0, 0, 0)
                user32.keybd_event(VK_CONTROL, 0, 0, 0)
                user32.keybd_event(VK_C, 0, 0, 0)
                user32.keybd_event(VK_C, 0, KEYEVENTF_KEYUP, 0)
                user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
                user32.keybd_event(VK_LWIN, 0, KEYEVENTF_KEYUP, 0)
        return True
    except Exception:
        return False


# --- AuraTime Brand Logo & Multi-Resolution Icon (.ico & .png) ---

def ensure_app_icon(icon_path: Path | None = None) -> Path:
    """
    Ensure AuraTime multi-resolution .ico and PNG brand assets exist and return the .ico path.
    """
    from logo import ensure_brand_assets

    assets_dir = (
        icon_path.parent
        if icon_path is not None
        else (Path(__file__).resolve().parent / "assets")
    )
    assets = ensure_brand_assets(assets_dir)
    return assets["ico"]
