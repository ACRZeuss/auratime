"""
Native Windows System Tray (Shell_NotifyIconW) controller using pure ctypes.
Zero third-party dependencies required.
Supports:
- Custom Ubuntu Screen Time icon (.ico) in the Windows system tray
- Dynamic live tooltip showing today's screen time & status
- Left-click / Double-click to restore the main GNOME Wellbeing window
- Right-click native Windows context menu (Open, Today's Summary, Pause/Resume, Exit)
- Native Windows Balloon / Toast notifications (Daily limit & Break reminders)
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import Path
import threading
from typing import Callable

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
shell32 = ctypes.windll.shell32

# Pointer-sized types for 64-bit Windows safety
LRESULT = ctypes.c_ssize_t
WPARAM = ctypes.c_size_t
LPARAM = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, WPARAM, LPARAM)

# Window messages & constants
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_COMMAND = 0x0111
WM_USER = 0x0400
WM_TRAYICON = WM_USER + 20
WM_SHOW_EXISTING = WM_USER + 21

WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_CONTEXTMENU = 0x007B

NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002

NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_INFO = 0x00000010

NIIF_INFO = 0x00000001
NIIF_WARNING = 0x00000002

IMAGE_ICON = 1
LR_LOADFROMFILE = 0x00000010
LR_DEFAULTSIZE = 0x00000040

MF_STRING = 0x00000000
MF_SEPARATOR = 0x00000800
MF_GRAYED = 0x00000001
TPM_LEFTALIGN = 0x0000
TPM_BOTTOMALIGN = 0x0020
TPM_RIGHTBUTTON = 0x0002

IDM_OPEN = 1001
IDM_STATUS = 1002
IDM_TOGGLE_PAUSE = 1003
IDM_TRIGGER_BREAK = 1004
IDM_EXIT = 1005


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uTimeoutOrVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", GUID),
        ("hBalloonIcon", wintypes.HICON),
    ]


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", wintypes.HICON),
    ]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", WPARAM),
        ("lParam", LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    ]


user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, WPARAM, LPARAM]
user32.DefWindowProcW.restype = LRESULT

user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
user32.RegisterClassExW.restype = wintypes.ATOM

user32.CreateWindowExW.argtypes = [
    wintypes.DWORD,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    wintypes.HMENU,
    wintypes.HINSTANCE,
    wintypes.LPVOID,
]
user32.CreateWindowExW.restype = wintypes.HWND

user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.DestroyWindow.restype = wintypes.BOOL

user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.PostQuitMessage.restype = None

user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = wintypes.BOOL

user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
user32.TranslateMessage.restype = wintypes.BOOL

user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
user32.DispatchMessageW.restype = LRESULT

user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, WPARAM, LPARAM]
user32.PostMessageW.restype = wintypes.BOOL

user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowW.restype = wintypes.HWND

user32.LoadImageW.argtypes = [
    wintypes.HINSTANCE,
    wintypes.LPCWSTR,
    wintypes.UINT,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
]
user32.LoadImageW.restype = wintypes.HANDLE

user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
user32.LoadIconW.restype = wintypes.HICON

user32.CreatePopupMenu.argtypes = []
user32.CreatePopupMenu.restype = wintypes.HMENU

user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
user32.AppendMenuW.restype = wintypes.BOOL

user32.TrackPopupMenu.argtypes = [
    wintypes.HMENU,
    wintypes.UINT,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    wintypes.LPVOID,
]
user32.TrackPopupMenu.restype = wintypes.BOOL

user32.DestroyMenu.argtypes = [wintypes.HMENU]
user32.DestroyMenu.restype = wintypes.BOOL

user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.GetCursorPos.restype = wintypes.BOOL

user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL

shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
shell32.Shell_NotifyIconW.restype = wintypes.BOOL

kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE


TRAY_WINDOW_CLASS = "AuraTimeTrayWndClass"
TRAY_WINDOW_TITLE = "AuraTimeHiddenWindow"


def signal_existing_instance() -> bool:
    """
    If another instance of AuraTime is already running, send it WM_SHOW_EXISTING
    so it pops up its window, and return True.
    """
    for cls_name, title in (
        (TRAY_WINDOW_CLASS, TRAY_WINDOW_TITLE),
        ("UbuntuScreenTimeTrayWndClass", "UbuntuScreenTimeHiddenWindow"),
    ):
        hwnd = user32.FindWindowW(cls_name, title)
        if hwnd:
            user32.PostMessageW(hwnd, WM_SHOW_EXISTING, 0, 0)
            return True
    return False


class SystemTrayIcon:
    def __init__(
        self,
        icon_path: Path,
        on_open: Callable[[], None],
        on_toggle_pause: Callable[[], None],
        on_take_break: Callable[[], None],
        on_exit: Callable[[], None],
        get_status_label: Callable[[], str],
        is_paused_fn: Callable[[], bool],
    ) -> None:
        self.icon_path = icon_path
        self.on_open = on_open
        self.on_toggle_pause = on_toggle_pause
        self.on_take_break = on_take_break
        self.on_exit = on_exit
        self.get_status_label = get_status_label
        self.is_paused_fn = is_paused_fn

        self._hwnd: int | None = None
        self._hicon: int | None = None
        self._nid = NOTIFYICONDATAW()
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._wndproc_ref = WNDPROC(self._wnd_proc)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run_loop, name="Win32TrayThread", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=3.0)

    def stop(self) -> None:
        if self._hwnd:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid))
            user32.PostMessageW(self._hwnd, WM_CLOSE, 0, 0)
            self._hwnd = None

    def update_tooltip(self, tip: str) -> None:
        if not self._hwnd:
            return
        self._nid.uFlags = NIF_TIP
        self._nid.szTip = tip[:127]
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self._nid))

    def show_notification(self, title: str, message: str, warning: bool = False) -> None:
        """Display a native Windows system tray toast/balloon notification."""
        if not self._hwnd:
            return
        self._nid.uFlags = NIF_INFO | NIF_TIP
        self._nid.szInfoTitle = title[:63]
        self._nid.szInfo = message[:255]
        self._nid.dwInfoFlags = NIIF_WARNING if warning else NIIF_INFO
        self._nid.uTimeoutOrVersion = 5000
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self._nid))

    def _run_loop(self) -> None:
        hinst = kernel32.GetModuleHandleW(None)

        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = self._wndproc_ref
        wc.hInstance = hinst
        wc.lpszClassName = TRAY_WINDOW_CLASS
        user32.RegisterClassExW(ctypes.byref(wc))

        hwnd = user32.CreateWindowExW(
            0,
            TRAY_WINDOW_CLASS,
            TRAY_WINDOW_TITLE,
            0,
            0,
            0,
            0,
            0,
            None,
            None,
            hinst,
            None,
        )
        self._hwnd = hwnd

        hicon = None
        if self.icon_path.exists():
            hicon = user32.LoadImageW(
                None,
                str(self.icon_path),
                IMAGE_ICON,
                32,
                32,
                LR_LOADFROMFILE,
            )
            if not hicon:
                hicon = user32.LoadImageW(
                    None,
                    str(self.icon_path),
                    IMAGE_ICON,
                    0,
                    0,
                    LR_LOADFROMFILE | LR_DEFAULTSIZE,
                )
        if not hicon:
            # IDI_APPLICATION = 32512
            hicon = user32.LoadIconW(None, ctypes.cast(32512, wintypes.LPCWSTR))
        self._hicon = hicon

        ctypes.memset(ctypes.byref(self._nid), 0, ctypes.sizeof(NOTIFYICONDATAW))
        self._nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        self._nid.hWnd = hwnd
        self._nid.uID = 1
        self._nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        self._nid.uCallbackMessage = WM_TRAYICON
        self._nid.hIcon = hicon
        self._nid.szTip = "AuraTime — Dijital Denge & Ekran Süresi"

        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self._nid))
        self._ready.set()

        msg = MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _show_context_menu(self, hwnd: int) -> None:
        hmenu = user32.CreatePopupMenu()
        if not hmenu:
            return
        try:
            status_text = f"⏱  AuraTime · {self.get_status_label()}"
            paused = self.is_paused_fn()
            pause_label = "▶  Takibi Devam Ettir" if paused else "⏸  Takibi Duraklat"

            user32.AppendMenuW(hmenu, MF_STRING | MF_GRAYED, IDM_STATUS, status_text)
            user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
            user32.AppendMenuW(hmenu, MF_STRING, IDM_OPEN, "📊  AuraTime Panelini Aç")
            user32.AppendMenuW(hmenu, MF_STRING, IDM_TOGGLE_PAUSE, pause_label)
            user32.AppendMenuW(hmenu, MF_STRING, IDM_TRIGGER_BREAK, "☕  Şimdi Göz Molası Ver (20 sn)")
            user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
            user32.AppendMenuW(hmenu, MF_STRING, IDM_EXIT, "✖  AuraTime'dan Çık")

            pt = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            user32.SetForegroundWindow(hwnd)
            user32.TrackPopupMenu(
                hmenu,
                TPM_LEFTALIGN | TPM_BOTTOMALIGN | TPM_RIGHTBUTTON,
                pt.x,
                pt.y,
                0,
                hwnd,
                None,
            )
            user32.PostMessageW(hwnd, 0, 0, 0)
        finally:
            user32.DestroyMenu(hmenu)

    def _wnd_proc(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        if msg == WM_TRAYICON:
            event = lparam & 0xFFFF
            if event in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                self.on_open()
                return 0
            if event in (WM_RBUTTONUP, WM_CONTEXTMENU):
                self._show_context_menu(hwnd)
                return 0
        elif msg == WM_SHOW_EXISTING:
            self.on_open()
            return 0
        elif msg == WM_COMMAND:
            cmd_id = wparam & 0xFFFF
            if cmd_id == IDM_OPEN:
                self.on_open()
            elif cmd_id == IDM_TOGGLE_PAUSE:
                self.on_toggle_pause()
            elif cmd_id == IDM_TRIGGER_BREAK:
                self.on_take_break()
            elif cmd_id == IDM_EXIT:
                self.on_exit()
            return 0
        elif msg == WM_CLOSE:
            user32.DestroyWindow(hwnd)
            return 0
        elif msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0

        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
