"""MT-32 (0.43): the Windows notification-tray seam (Shell_NotifyIconW).

A thin clean-room Win32 wrapper: a hidden callback window receives the
tray-icon messages (``NIF_MESSAGE``) and balloons are posted with
``NIM_MODIFY`` + ``NIF_INFO``.  Every failure is a named
:class:`TrayRefusal`, so the UI can leave the feature off fail-closed
instead of crashing.  On non-Windows platforms the feature is
unavailable (named reason); the attach path is unaffected - the tray
is a convenience, not a dependency.

The icon and its hidden window are created on the Tk main thread, and
the WndProc callback runs in that same thread, so the left-click
handler may touch Tk widgets directly.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import sys

from .tray_model import TRAY_TIP

# shellapi
NIM_ADD = 0x0000
NIM_MODIFY = 0x0001
NIM_DELETE = 0x0002
# NIF_* flags
NIF_MESSAGE = 0x0001
NIF_ICON = 0x0002
NIF_TIP = 0x0004
NIF_INFO = 0x0010
# winuser
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x020B
WS_OVERLAPPED = 0x00000000
IDC_ARROW = 32515
WM_USER = 0x0400
# This window's custom callback message for the tray icon.
_TRAY_MSG = WM_USER + 1

LRESULT = ctypes.c_ssize_t
# Pointer-sized message parameters (the wintypes WPARAM / LPARAM are
# 32-bit on this platform; Win64 messages are pointer-sized).
WPARAM = ctypes.c_size_t
LPARAM = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, WPARAM, LPARAM)


def _bind_prototypes(user32, kernel32) -> None:
    """Explicit 64-bit prototypes for every Win32 call (idempotent).

    Without them ctypes defaults to 32-bit handles / ints, which
    truncates the module handle (the process base commonly lives above
    4 GB) and the message parameters - clean-room hygiene, no CE input.
    """
    kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wt.HINSTANCE
    user32.LoadImageW.argtypes = [wt.HINSTANCE, wt.LPCWSTR, wt.UINT,
                                  ctypes.c_int, ctypes.c_int, wt.UINT]
    user32.LoadImageW.restype = wt.HICON
    user32.LoadCursorW.argtypes = [wt.HINSTANCE, ctypes.c_void_p]
    user32.LoadCursorW.restype = wt.HANDLE
    user32.RegisterClassExW.argtypes = [ctypes.POINTER(_WNDCLASSW)]
    user32.RegisterClassExW.restype = wt.ATOM
    user32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR,
                                       wt.DWORD, ctypes.c_int, ctypes.c_int,
                                       ctypes.c_int, ctypes.c_int, wt.HWND,
                                       wt.HMENU, wt.HINSTANCE, ctypes.c_void_p]
    user32.CreateWindowExW.restype = wt.HWND
    user32.UnregisterClassW.argtypes = [wt.LPCWSTR, wt.HINSTANCE]
    user32.UnregisterClassW.restype = wt.BOOL
    user32.DestroyWindow.argtypes = [wt.HWND]
    user32.DestroyWindow.restype = wt.BOOL
    user32.DestroyIcon.argtypes = [wt.HICON]
    user32.DestroyIcon.restype = wt.BOOL
    user32.Shell_NotifyIconW.argtypes = [wt.UINT,
                                        ctypes.POINTER(_NOTIFYICONDATAW)]
    user32.Shell_NotifyIconW.restype = wt.BOOL
    user32.CallWindowProcW.argtypes = [WNDPROC, wt.HWND, wt.UINT,
                                       WPARAM, LPARAM]
    user32.CallWindowProcW.restype = LRESULT

# One class name per TrayIcon instance (a second Master window in the
# same process must not collide with the first one's class).
_class_counter = 0


class TrayRefusal(Exception):
    """A tray failure with the stable named ``code`` and the
    displayable ``detail`` (the UI shows it; the feature stays off).

    Codes: ``tray-platform-unavailable`` (not Windows),
    ``tray-icon-missing`` (the icon file could not be loaded),
    ``tray-setup-failed`` (a Win32 call failed).
    """

    def __init__(self, code, detail):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def tray_available() -> bool:
    """The notification tray is a Windows-only feature
    (Shell_NotifyIconW); every other platform refuses with the named
    code ``tray-platform-unavailable``."""
    return sys.platform == "win32"


class _NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.UINT),
        ("hWnd", wt.HWND),
        ("uID", wt.UINT),
        ("uFlags", wt.UINT),
        ("uCallbackMessage", wt.UINT),
        ("hIcon", wt.HICON),
        ("szTip", wt.WCHAR * 128),
        ("dwState", wt.UINT),
        ("dwStateMask", wt.UINT),
        ("szInfo", wt.WCHAR * 256),
        ("uVersion", wt.UINT),
        ("szInfoTitle", wt.WCHAR * 64),
        ("dwFlags", wt.UINT),
    ]


class _WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.UINT),
        ("style", wt.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_long),
        ("cbWndExtra", ctypes.c_long),
        ("hInstance", wt.HINSTANCE),
        ("hIcon", wt.HICON),
        ("hCursor", wt.HANDLE),
        ("hbrBackground", wt.HBRUSH),
        ("lpszMenuName", wt.LPCWSTR),
        ("lpszClassName", wt.LPCWSTR),
    ]


class TrayIcon:
    """One hidden callback window plus the registered tray icon.

    ``icon_path`` is the multi-size ICO to show; ``on_left_click`` is
    called (on the Tk main thread) when the user clicks the icon.
    Raises :class:`TrayRefusal` on any failure - the icon is fully
    cleaned up before the refusal propagates.
    """

    def __init__(self, icon_path: str, on_left_click):
        if not tray_available():
            raise TrayRefusal(
                "tray-platform-unavailable",
                "the notification tray needs Windows "
                "(Shell_NotifyIconW)")
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        # Named missing-export guard (field precedent 0.23, the SC2
        # hotkey bridge T1): a stripped user32 without the
        # Shell_NotifyIconW export is a named refusal, not a crash.
        try:
            user32.Shell_NotifyIconW
        except AttributeError as exc:
            raise TrayRefusal(
                "tray-setup-failed",
                "the user32 build lacks the Shell_NotifyIconW export "
                "(%s)" % exc)
        _bind_prototypes(user32, kernel32)
        self._user32 = user32
        # The icon, loaded from the file (multi-size: 0x0 +
        # LR_LOADFROMFILE picks the best entry for the tray).
        self._hicon = user32.LoadImageW(0, icon_path, IMAGE_ICON, 0, 0,
                                        LR_LOADFROMFILE)
        if not self._hicon:
            raise TrayRefusal(
                "tray-icon-missing",
                "could not load the tray icon (%s, Win32 error %d)"
                % (icon_path, kernel32.GetLastError()))
        # The hidden callback window.
        global _class_counter
        _class_counter += 1
        cls_name = "CT2TrainerMasterTray%d" % _class_counter
        self._cls_name = cls_name
        wndproc = WNDPROC(self._wndproc)
        self._wndproc_ref = wndproc  # keep the callback alive
        wc = _WNDCLASSW()
        wc.cbSize = ctypes.sizeof(_WNDCLASSW)
        wc.style = 0
        wc.lpfnWndProc = wndproc
        wc.cbClsExtra = 0
        wc.cbWndExtra = 0
        wc.hInstance = kernel32.GetModuleHandleW(None)
        wc.hIcon = self._hicon
        wc.hCursor = user32.LoadCursorW(None, IDC_ARROW)
        wc.hbrBackground = None
        wc.lpszMenuName = None
        wc.lpszClassName = cls_name
        self._wc_ref = wc
        if not user32.RegisterClassExW(ctypes.byref(wc)):
            user32.DestroyIcon(self._hicon)
            self._hicon = None
            raise TrayRefusal(
                "tray-setup-failed",
                "RegisterClassExW failed (Win32 error %d)"
                % kernel32.GetLastError())
        hwnd = user32.CreateWindowExW(
            0, cls_name, "CT2Trainer Master Tray", WS_OVERLAPPED,
            0, 0, 0, 0, None, None, wc.hInstance, None)
        if not hwnd:
            user32.UnregisterClassW(cls_name, wc.hInstance)
            user32.DestroyIcon(self._hicon)
            self._hicon = None
            raise TrayRefusal(
                "tray-setup-failed",
                "CreateWindowExW failed (Win32 error %d)"
                % kernel32.GetLastError())
        self._hwnd = hwnd
        self._on_left_click = on_left_click
        self._removed = False
        data = self._data(NIF_MESSAGE | NIF_ICON | NIF_TIP)
        data.szTip = TRAY_TIP
        if not user32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(data)):
            self._teardown_window()
            raise TrayRefusal(
                "tray-setup-failed",
                "Shell_NotifyIconW(NIM_ADD) failed (Win32 error %d)"
                % kernel32.GetLastError())

    def _data(self, flags: int) -> _NOTIFYICONDATAW:
        data = _NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(_NOTIFYICONDATAW)
        data.hWnd = self._hwnd
        data.uID = 1
        data.uFlags = flags
        data.uCallbackMessage = _TRAY_MSG
        data.hIcon = self._hicon
        return data

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == _TRAY_MSG:
            if lparam in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                try:
                    self._on_left_click()
                except Exception:
                    pass
            # Every other tray-icon message (right click, hover, ...)
            # is swallowed - the Master's tray icon has no menu.
            return 0
        return self._user32.CallWindowProcW(None, hwnd, msg, wparam, lparam)

    def show_balloon(self, title: str, body: str) -> bool:
        """Post the balloon (NIM_MODIFY + NIF_INFO).  True when the
        call was accepted; a failure returns False (never fatal)."""
        if self._removed or not self._hicon:
            return False
        data = self._data(NIF_MESSAGE | NIF_ICON | NIF_TIP | NIF_INFO)
        data.szInfo = body[:255]
        data.szInfoTitle = title[:63]
        data.dwFlags = 0
        return bool(self._user32.Shell_NotifyIconW(
            NIM_MODIFY, ctypes.byref(data)))

    def remove(self) -> None:
        """Delete the icon, destroy the hidden window and free the
        icon handle (idempotent; never raises)."""
        if self._removed:
            return
        self._removed = True
        try:
            data = self._data(NIF_MESSAGE)
            self._user32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(data))
        except Exception:
            pass
        self._teardown_window()

    def _teardown_window(self) -> None:
        try:
            if self._hwnd:
                self._user32.DestroyWindow(self._hwnd)
                self._user32.UnregisterClassW(self._cls_name,
                                              self._wc_ref.hInstance)
                self._hwnd = None
        except Exception:
            pass
        try:
            if self._hicon:
                self._user32.DestroyIcon(self._hicon)
                self._hicon = None
        except Exception:
            pass
