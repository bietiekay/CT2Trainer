"""WP-53 (GC-D7): OS hotkey capture over a hidden message-only window.

On Windows the trainer owns a hidden message-only Win32 window (ctypes
``CreateWindowExW`` plus a private WNDPROC class) created at trainer
start.  Every unique registered combination goes through
``RegisterHotKey(hwnd, id, mods, vk)``; ``WM_HOTKEY`` maps the
registration ID back to the canonical
:class:`~ct2trainer.native.hotkey_model.HotKeySpec` and enqueues it on a
thread-safe queue.  The engine's steady poll tick drains the queue and
dispatches each combination through the tested WP-40 model gates (focus
gate, first-wins dedupe, tone policy, ``suppressed-*`` statuses).

``RegisterHotKey`` failures surface as the named
:class:`HotkeyRegistrationError` whose text the engine appends verbatim
to ``engine.hotkey_warnings``; the binding stays visible and the
programmatic dispatch path keeps working.  ``close()`` releases every
registration and destroys the window (trainer close, no OS leak).  On
user32 builds that lack the ``RegisterHotKeyW`` / ``UnregisterHotKeyW``
exports the registration path fails closed with the same named error
naming the missing export (non-blocking); the window lifecycle and the
programmatic dispatch path stay unaffected.

On non-Windows platforms the module is a no-op:
:func:`hotkey_bridge_available` is False and :func:`create_hotkey_bridge`
returns None, so non-Windows development and Deck runs keep working with
programmatic-only dispatch.  The real ``RegisterHotKey`` route stays
AP-11 evidence; tests drive the tested :class:`HotkeyBridge` through an
injected seam, never with a real window.
"""
from __future__ import annotations

import queue
import sys
import threading

from .hotkey_model import HotKeySpec, VK_KEY_NAMES


class HotkeyBridgeError(RuntimeError):
    """OS hotkey bridge contract violation (named, fail-closed)."""


class HotkeyRegistrationError(HotkeyBridgeError):
    """RegisterHotKey failed for one combination; the reason is named.

    The message text is the exact named reason the engine appends to
    ``hotkey_warnings``::

        OS hotkey registration failed for <key text>: <reason>.
    """

    def __init__(self, key_text: str, reason: str):
        super().__init__(f"OS hotkey registration failed for {key_text}: {reason}.")
        self.key_text = key_text
        self.reason = reason


MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

_MODIFIER_BITS = {
    "ctrl": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "meta": MOD_WIN,
}

_WIN32_E_ACCESS_DENIED = 5
_WIN32_E_INVALID_ARG = 87

# Name-to-VK reverse of the bounded hotkey_model tables.  Every spec main
# key comes from vk_to_spec, so this reverse map is total over specs; the
# load-time check keeps it fail-closed if the tables ever collide.
_VK_BY_NAME: dict[str, int] = {}
for _code, _name in VK_KEY_NAMES.items():
    if _name in _VK_BY_NAME and _VK_BY_NAME[_name] != _code:
        raise HotkeyBridgeError(
            f"VK name table collision for {_name!r}; the OS hotkey bridge "
            f"requires a name-to-VK bijection.")
    _VK_BY_NAME[_name] = _code


def hotkey_bridge_available() -> bool:
    """True on Windows only; elsewhere the bridge is a no-op."""
    return sys.platform == "win32"


def spec_to_os(spec: HotKeySpec) -> tuple[int, int]:
    """(RegisterHotKey mods, virtual key) for one canonical spec.

    Unmappable tokens are named, fail-closed :class:`HotkeyBridgeError`
    refusals (a spec main key outside the bounded VK table cannot be
    registered at all).
    """
    if not isinstance(spec, HotKeySpec):
        raise HotkeyBridgeError("OS hotkey registrations are canonical HotKeySpec values.")
    mods = 0
    for modifier in sorted(spec.modifiers):
        try:
            mods |= _MODIFIER_BITS[modifier]
        except KeyError:
            raise HotkeyBridgeError(
                f"Unknown hotkey modifier for the OS bridge: {modifier}") from None
    try:
        vk = _VK_BY_NAME[spec.key]
    except KeyError:
        raise HotkeyBridgeError(
            f"Hotkey main key has no virtual key for the OS bridge: {spec.key}") from None
    return mods, vk


def os_key_text(spec: HotKeySpec) -> str:
    """Canonical '<modifiers>+<key>' text of a spec (hotkey_warnings input)."""
    if not isinstance(spec, HotKeySpec):
        raise HotkeyBridgeError("OS hotkey text needs a canonical HotKeySpec.")
    return "+".join(sorted(spec.modifiers) + [spec.key])


def classify_registration_error(code: int) -> str:
    """Named reason text for one RegisterHotKey GetLastError() value."""
    if type(code) is not int or code <= 0:
        raise HotkeyBridgeError("RegisterHotKey failure codes are positive integers.")
    if code == _WIN32_E_ACCESS_DENIED:
        return ("the combination is already registered by another "
                "process (E_ACCESS_DENIED)")
    if code == _WIN32_E_INVALID_ARG:
        return ("the key combination is invalid for RegisterHotKey "
                "(E_INVALID_PARAMETER)")
    return f"RegisterHotKey failed with Win32 error {code}"


class HotkeyBridge:
    """Registry of published OS hotkeys over one hidden message-only window.

    ``register(spec)`` maps one canonical combination to one OS
    registration and one internal ID (repeat registrations of the same
    combination are idempotent); ``WM_HOTKEY`` events come back on the
    message thread and are mapped through ``_on_hotkey`` to the spec on a
    thread-safe queue.  ``take_specs()`` drains the queue; ``unregister``
    releases one combination; ``close()`` releases everything, stops the
    message loop and destroys the window.  A key released from the OS
    just before a press may still deliver one late ``WM_HOTKEY`` for an
    already-removed ID; that event has no spec and is dropped by design
    (the engine-level binding is gone, so dispatch would report unbound
    anyway).

    The seam is the win32 call surface: the real hidden-window seam on
    Windows, an injected fake in tests.  Seam protocol -
    ``connect(handler) -> int`` (start the capture; return the window
    handle; ``handler(hotkey_id)`` is called on OS keypresses),
    ``register_hotkey(hotkey_id, mods, vk) -> bool``,
    ``unregister_hotkey(hotkey_id) -> bool``, ``last_error() -> int``
    (meaningful right after a failed register), ``destroy() -> None``
    (stop the loop and release the window).
    """

    def __init__(self, seam=None):
        if seam is None:
            if not hotkey_bridge_available():
                raise HotkeyBridgeError(
                    "OS hotkey bridge is Windows-only; other platforms "
                    "stay programmatic-only.")
            seam = _real_seam()
        self._seam = seam
        self._hwnd = seam.connect(self._on_hotkey)
        if not isinstance(self._hwnd, int) or self._hwnd <= 0:
            raise HotkeyBridgeError("Hotkey bridge window handle is invalid.")
        self._queue: "queue.Queue[HotKeySpec]" = queue.Queue()
        self._id_to_spec: dict[int, HotKeySpec] = {}
        self._spec_to_id: dict[HotKeySpec, int] = {}
        self._next_id = 1
        self._closed = False
        # Named teardown note from the seam (set on close when the quit
        # post finds an already-gone window); the engine logs it once.
        self.destroy_note = None

    # ------------------------------------------------------------- register
    def register(self, spec: HotKeySpec) -> int:
        """Register one combination (idempotent); returns the OS hotkey ID."""
        self._guard_open()
        mods, vk = spec_to_os(spec)
        if spec in self._spec_to_id:
            return self._spec_to_id[spec]
        hotkey_id = self._next_id
        self._next_id += 1
        if not self._seam.register_hotkey(hotkey_id, mods | MOD_NOREPEAT, vk):
            reason = classify_registration_error(self._seam.last_error())
            raise HotkeyRegistrationError(os_key_text(spec), reason)
        self._id_to_spec[hotkey_id] = spec
        self._spec_to_id[spec] = hotkey_id
        return hotkey_id

    def unregister(self, spec: HotKeySpec) -> bool:
        """Release one combination; True when a registration was removed."""
        if self._closed:
            return False
        if not isinstance(spec, HotKeySpec):
            raise HotkeyBridgeError("OS hotkey unregister needs a canonical HotKeySpec.")
        hotkey_id = self._spec_to_id.pop(spec, None)
        if hotkey_id is None:
            return False
        self._id_to_spec.pop(hotkey_id, None)
        # An already-released combination still counts as unregistered.
        self._seam.unregister_hotkey(hotkey_id)
        return True

    def is_registered(self, spec: HotKeySpec) -> bool:
        return spec in self._spec_to_id

    # -------------------------------------------------------------- capture
    def take_specs(self) -> tuple[HotKeySpec, ...]:
        """Drain every queued keypress (thread-safe, order-preserving)."""
        specs: list[HotKeySpec] = []
        while True:
            try:
                specs.append(self._queue.get_nowait())
            except queue.Empty:
                return tuple(specs)

    def _on_hotkey(self, hotkey_id: int) -> None:
        spec = self._id_to_spec.get(hotkey_id)
        if spec is None:
            # Late event for a just-released ID: no spec, nothing to
            # dispatch (documented race window, not a silent fallback).
            return
        self._queue.put(spec)

    # ----------------------------------------------------------------- close
    def close(self) -> None:
        """Release every registration, stop the loop and destroy the window.

        Idempotent; called by the engine close path so no OS registration
        or window outlives the trainer (no OS leak).
        """
        if self._closed:
            return
        for spec in list(self._spec_to_id):
            try:
                self._seam.unregister_hotkey(self._spec_to_id[spec])
            except HotkeyBridgeError:
                # Teardown containment (field case 2026-10-31, Sinking
                # City 2 0.19, T3): a missing OS export or a dead window
                # must not abort the close protocol before destroy();
                # the OS releases every registration with the window
                # and the process either way.
                continue
        self._spec_to_id.clear()
        self._id_to_spec.clear()
        self._seam.destroy()
        self.destroy_note = getattr(self._seam, "last_destroy_note", None)
        self._closed = True

    def _guard_open(self) -> None:
        if self._closed:
            raise HotkeyBridgeError("hotkey bridge is closed")


def create_hotkey_bridge() -> HotkeyBridge | None:
    """Trainer-start entry: a running OS bridge on Windows, None elsewhere.

    Non-Windows platforms stay programmatic-only (dev machines, Steam
    Deck under Proton); the engine then keeps ``hotkey_bridge`` unset and
    its dispatch path is unchanged.
    """
    if not hotkey_bridge_available():
        return None
    return HotkeyBridge()


# ------------------------------------------------------------------ real seam
# Per-instance window class names: the class is registered on the loop
# thread and unregistered again in destroy(), so a later bridge instance
# in the same process (tests) starts from a clean class registration
# instead of reusing a class bound to a stale WNDPROC.
_CLASS_BASE = "CT2TrainerNativeHotkeyBridge"
_class_counter = 0


def _next_class_name() -> str:
    global _class_counter
    _class_counter += 1
    return "%s%04d" % (_CLASS_BASE, _class_counter)


def _real_seam():
    """Build the Windows-only hidden-window seam.

    The message-only window is created ON the dedicated daemon loop
    thread: ``WM_BRIDGE_QUIT`` is only deliverable when the thread that
    created the window pumps it, and the pump is that same thread, so
    the quit protocol works as designed (field case 2026-10-31,
    Sinking City 2 0.19: the window lived on the calling thread while
    the loop thread pumped its own queue, so the quit message was
    undeliverable, ``destroy()`` always hit the 5 s join timeout, the
    window was never destroyed and the daemon loop thread access-
    violated in ``GetMessageW`` during process teardown).

    ``connect()`` starts the loop thread, which registers the per-
    instance window class, creates the window, stores the handle and
    signals a completion event before entering the pump; ``connect()``
    waits for that event (bounded) and fails closed with the real
    Win32 error when class registration or window creation failed on
    the loop thread.  ``destroy()`` posts the private quit message
    (checked), the WNDPROC destroys the window from its own thread and
    quits the pump, the loop thread exits and the per-instance window
    class is released.  The thread is a daemon, so a process exit
    without close() cannot hang, and the OS releases the window and
    every hotkey with the process.
    """
    if sys.platform != "win32":
        raise HotkeyBridgeError(
            "OS hotkey bridge is Windows-only; other platforms "
            "stay programmatic-only.")
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    # HWND_MESSAGE = ((HWND)-3): a message-only window receives only
    # posted messages and is invisible to EnumWindows.  The previous
    # value c_void_p(-1) was HWND_BOTTOM (Z-order hint), which made the
    # window a regular top-level window and caused CreateWindowExW to
    # fail (error 1400) in the frozen environment.
    HWND_MESSAGE = ctypes.c_void_p(-3)
    WM_HOTKEY = 0x0312
    WM_BRIDGE_QUIT = 0x8001  # WM_APP + 1
    CS_HREDRAW = 0x0002
    CS_VREDRAW = 0x0001

    WNDPROC = ctypes.WINFUNCTYPE(
        ctypes.c_longlong, wintypes.HWND, wintypes.UINT,
        wintypes.WPARAM, wintypes.LPARAM)

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
            ("hBrBackground", wintypes.HBRUSH),
            ("lpszMenuName", wintypes.LPCWSTR),
            ("lpszClassName", wintypes.LPCWSTR),
            ("hIconSm", wintypes.HICON),
        ]

    # Declare Win32 prototypes up front so that 64-bit pointer sizes are
    # passed correctly.  Without explicit argtypes/restype, ctypes
    # defaults to c_int (32-bit) for both arguments and return values,
    # which truncates HINSTANCE/HWND on x64 and causes access
    # violations inside RegisterClassExW / CreateWindowExW / DefWindowProcW.
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
    user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
    user32.RegisterClassExW.restype = wintypes.ATOM
    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        wintypes.INT, wintypes.INT, wintypes.INT, wintypes.INT,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.DefWindowProcW.argtypes = [
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.DefWindowProcW.restype = wintypes.LPARAM
    user32.GetMessageW.argtypes = [
        ctypes.POINTER(wintypes.MSG), wintypes.HWND,
        wintypes.UINT, wintypes.UINT]
    user32.GetMessageW.restype = wintypes.BOOL
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.restype = wintypes.LPARAM
    user32.PostQuitMessage.argtypes = [ctypes.c_uint]
    user32.PostMessageW.argtypes = [
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.DestroyWindow.restype = wintypes.BOOL
    user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
    user32.UnregisterClassW.restype = wintypes.BOOL
    # RegisterHotKeyW / UnregisterHotKeyW may be absent in stripped or
    # minimal user32 builds (e.g. some embedded Python distributions);
    # guard so the seam can still be constructed for the window lifecycle
    # even when hotkey registration is unavailable.
    try:
        user32.RegisterHotKeyW.argtypes = [
            wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        user32.RegisterHotKeyW.restype = wintypes.BOOL
        user32.UnregisterHotKeyW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.UnregisterHotKeyW.restype = wintypes.BOOL
        _hotkey_api_available = True
    except AttributeError:
        _hotkey_api_available = False

    def _require_hotkey_export(export_name: str) -> None:
        # Field case 2026-10-31 (Sinking City 2 0.19, T1): a stripped
        # user32 build may lack the hotkey exports; the guard raises the
        # named, non-blocking registration error naming the missing
        # export instead of a raw AttributeError escaping the engine.
        if not _hotkey_api_available or not hasattr(user32, export_name):
            raise HotkeyRegistrationError(
                "the hotkey registry",
                f"the OS export {export_name} is missing from user32")

    state = {"handler": None, "hwnd": 0, "thread": None, "proc": None,
             "ready": None, "error": None, "class_name": None,
             "hinstance": None}

    class _WindowProc:
        """Private WNDPROC class; the instance is pinned on the state."""

        def __call__(self, hwnd, message, wparam, lparam):
            if message == WM_HOTKEY:
                state["handler"](int(wparam))
            elif message == WM_BRIDGE_QUIT:
                # Destroy the window from its own thread (legal: this
                # thread created it), then quit the pump; destroy() on
                # the calling thread only posts and joins, so the quit
                # protocol can no longer dead-lock on the 5 s join
                # timeout (field case 2026-10-31, Sinking City 2 0.19).
                user32.DestroyWindow(wintypes.HWND(hwnd))
                user32.PostQuitMessage(0)
                return 0
            return user32.DefWindowProcW(hwnd, message, wparam, lparam)

    class _RealHotkeySeam:
        def __init__(self):
            # Set by destroy() when the quit-post path finds the window is
            # already gone; the engine surfaces it as a named debug event.
            self.last_destroy_note = None

        def connect(self, handler) -> int:
            state["handler"] = handler
            state["proc"] = _WindowProc()
            state["ready"] = threading.Event()
            state["error"] = None
            state["hwnd"] = 0
            class_name = _next_class_name()
            state["class_name"] = class_name

            def loop():
                try:
                    hinstance = kernel32.GetModuleHandleW(None)
                    state["hinstance"] = hinstance
                    window_class = WNDCLASSEXW()
                    window_class.cbSize = ctypes.sizeof(WNDCLASSEXW)
                    window_class.style = CS_HREDRAW | CS_VREDRAW
                    window_class.lpfnWndProc = WNDPROC(state["proc"])
                    window_class.hInstance = hinstance
                    window_class.lpszClassName = class_name
                    atom = user32.RegisterClassExW(ctypes.byref(window_class))
                    if atom == 0:
                        state["error"] = (
                            "could not register the hotkey bridge window "
                            f"class: Win32 error {ctypes.get_last_error()}")
                        state["ready"].set()
                        return
                    hwnd = user32.CreateWindowExW(
                        0, class_name, "CT2Trainer Hotkey Bridge",
                        0, 0, 0, 0, 0, HWND_MESSAGE, None, hinstance, None)
                    if not hwnd:
                        state["error"] = (
                            "could not create the hidden hotkey window: "
                            f"Win32 error {ctypes.get_last_error()}")
                        state["ready"].set()
                        return
                    state["hwnd"] = int(hwnd)
                    state["ready"].set()
                    message = wintypes.MSG()
                    while True:
                        result = user32.GetMessageW(
                            ctypes.byref(message), None, 0, 0)
                        if result in (0, -1):
                            return
                        user32.DispatchMessageW(ctypes.byref(message))
                except Exception as exc:
                    # Unexpected loop-thread failure: surface a named
                    # error to the caller instead of a silent dead thread.
                    state["error"] = (
                        "hotkey bridge window thread failed: " + str(exc))
                    state["ready"].set()

            state["thread"] = threading.Thread(
                target=loop, name="ct2trainer-hotkey-bridge", daemon=True)
            state["thread"].start()
            if not state["ready"].wait(timeout=5.0):
                raise HotkeyBridgeError(
                    "hotkey bridge window did not start within 5s")
            if state["error"] is not None:
                raise HotkeyBridgeError(state["error"])
            if state["hwnd"] <= 0:
                raise HotkeyBridgeError("Hotkey bridge window handle is invalid.")
            return state["hwnd"]

        def register_hotkey(self, hotkey_id: int, mods: int, vk: int) -> bool:
            _require_hotkey_export("RegisterHotKeyW")
            return bool(user32.RegisterHotKeyW(
                wintypes.HWND(state["hwnd"]), hotkey_id, mods, vk))

        def unregister_hotkey(self, hotkey_id: int) -> bool:
            _require_hotkey_export("UnregisterHotKeyW")
            return bool(user32.UnregisterHotKeyW(wintypes.HWND(state["hwnd"]),
                                                 hotkey_id))

        def last_error(self) -> int:
            return ctypes.get_last_error()

        def destroy(self) -> None:
            hwnd = state["hwnd"]
            thread = state["thread"]
            note = None
            if hwnd:
                posted = bool(user32.PostMessageW(
                    wintypes.HWND(hwnd), WM_BRIDGE_QUIT, 0, 0))
                if not posted:
                    if thread is None or not thread.is_alive():
                        # The window is already gone (its loop thread is
                        # gone too): a clean state, reported as a named
                        # note for the engine's debug log instead of an
                        # error.
                        note = (
                            "hotkey bridge quit post failed "
                            f"(Win32 error {ctypes.get_last_error()}); the "
                            "loop thread was already gone, nothing to "
                            "destroy")
                    else:
                        raise HotkeyBridgeError(
                            "could not post the hotkey bridge quit "
                            f"message: Win32 error {ctypes.get_last_error()}")
            if thread is not None:
                thread.join(timeout=5.0)
                if thread.is_alive():
                    raise HotkeyBridgeError(
                        "hotkey bridge message loop did not stop within 5s")
            if hwnd or thread is not None:
                # The window was destroyed by its own WNDPROC; release
                # the per-instance class so a later bridge instance in
                # this process registers fresh.
                unregistered = bool(user32.UnregisterClassW(
                    wintypes.LPCWSTR(state["class_name"]),
                    state["hinstance"]))
                if not unregistered and note is None:
                    # Documented best-effort cleanup: the OS releases the
                    # class with the process; a failure here means a
                    # window of the class is still outstanding.
                    note = (
                        "hotkey bridge window class unregistration "
                        f"failed: Win32 error {ctypes.get_last_error()}")
                state["hwnd"] = 0
                state["thread"] = None
                state["class_name"] = None
                state["hinstance"] = None
            if note is not None:
                self.last_destroy_note = note

    return _RealHotkeySeam()
