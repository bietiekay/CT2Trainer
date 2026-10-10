"""Read-only keyboard and XInput adapters, authored from public API contracts.

Sources: Microsoft's GetAsyncKeyState, XINPUT_STATE/XINPUT_GAMEPAD and
virtual-key documentation; CE's public getXBox360ControllerState field contract.
No CE implementation, input synthesis, driver or privilege adjustment is used.
GetAsyncKeyState's current-down bit is used; its unreliable recent-press bit is
ignored. A false keyboard result also covers desktops inaccessible to the API.
"""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
from typing import Any


class InputStateError(RuntimeError):
    """An invalid request or an unexpected read-only input API failure."""


ERROR_SUCCESS = 0
ERROR_DEVICE_NOT_CONNECTED = 1167
LOAD_LIBRARY_SEARCH_SYSTEM32 = 0x00000800

# Numeric values from Microsoft's public Winuser.h virtual-key table. Letter
# and digit names are convenience names for that table's ASCII-valued keys.
VIRTUAL_KEYS = {
    'VK_LBUTTON': 0x01, 'VK_RBUTTON': 0x02, 'VK_CANCEL': 0x03,
    'VK_MBUTTON': 0x04, 'VK_XBUTTON1': 0x05, 'VK_XBUTTON2': 0x06,
    'VK_BACK': 0x08, 'VK_TAB': 0x09, 'VK_CLEAR': 0x0C, 'VK_RETURN': 0x0D,
    'VK_SHIFT': 0x10, 'VK_CONTROL': 0x11, 'VK_MENU': 0x12,
    'VK_PAUSE': 0x13, 'VK_CAPITAL': 0x14, 'VK_ESCAPE': 0x1B,
    'VK_SPACE': 0x20, 'VK_PRIOR': 0x21, 'VK_NEXT': 0x22,
    'VK_END': 0x23, 'VK_HOME': 0x24, 'VK_LEFT': 0x25, 'VK_UP': 0x26,
    'VK_RIGHT': 0x27, 'VK_DOWN': 0x28, 'VK_SELECT': 0x29,
    'VK_PRINT': 0x2A, 'VK_EXECUTE': 0x2B, 'VK_SNAPSHOT': 0x2C,
    'VK_INSERT': 0x2D, 'VK_DELETE': 0x2E, 'VK_HELP': 0x2F,
    'VK_LWIN': 0x5B, 'VK_RWIN': 0x5C, 'VK_APPS': 0x5D,
    'VK_SLEEP': 0x5F, 'VK_MULTIPLY': 0x6A, 'VK_ADD': 0x6B,
    'VK_SEPARATOR': 0x6C, 'VK_SUBTRACT': 0x6D,
    'VK_DECIMAL': 0x6E, 'VK_DIVIDE': 0x6F,
    'VK_NUMLOCK': 0x90, 'VK_SCROLL': 0x91,
    'VK_LSHIFT': 0xA0, 'VK_RSHIFT': 0xA1,
    'VK_LCONTROL': 0xA2, 'VK_RCONTROL': 0xA3,
    'VK_LMENU': 0xA4, 'VK_RMENU': 0xA5,
    'VK_OEM_1': 0xBA, 'VK_OEM_PLUS': 0xBB, 'VK_OEM_COMMA': 0xBC,
    'VK_OEM_MINUS': 0xBD, 'VK_OEM_PERIOD': 0xBE, 'VK_OEM_2': 0xBF,
    'VK_OEM_3': 0xC0, 'VK_OEM_4': 0xDB, 'VK_OEM_5': 0xDC,
    'VK_OEM_6': 0xDD, 'VK_OEM_7': 0xDE, 'VK_OEM_8': 0xDF,
    'VK_OEM_102': 0xE2,
}
VIRTUAL_KEYS.update({f'VK_{character}': ord(character)
                     for character in '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'})
VIRTUAL_KEYS.update({f'VK_NUMPAD{index}': 0x60 + index for index in range(10)})
VIRTUAL_KEYS.update({f'VK_F{index}': 0x6F + index for index in range(1, 25)})

GAMEPAD_BUTTONS = {
    'GAMEPAD_DPAD_UP': 0x0001, 'GAMEPAD_DPAD_DOWN': 0x0002,
    'GAMEPAD_DPAD_LEFT': 0x0004, 'GAMEPAD_DPAD_RIGHT': 0x0008,
    'GAMEPAD_START': 0x0010, 'GAMEPAD_BACK': 0x0020,
    'GAMEPAD_LEFT_THUMB': 0x0040, 'GAMEPAD_RIGHT_THUMB': 0x0080,
    'GAMEPAD_LEFT_SHOULDER': 0x0100, 'GAMEPAD_RIGHT_SHOULDER': 0x0200,
    'GAMEPAD_A': 0x1000, 'GAMEPAD_B': 0x2000,
    'GAMEPAD_X': 0x4000, 'GAMEPAD_Y': 0x8000,
}


class XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [('wButtons', ctypes.c_uint16),
                ('bLeftTrigger', ctypes.c_uint8), ('bRightTrigger', ctypes.c_uint8),
                ('sThumbLX', ctypes.c_int16), ('sThumbLY', ctypes.c_int16),
                ('sThumbRX', ctypes.c_int16), ('sThumbRY', ctypes.c_int16)]


class XINPUT_STATE(ctypes.Structure):
    _fields_ = [('dwPacketNumber', ctypes.c_uint32), ('Gamepad', XINPUT_GAMEPAD)]


def _system_directory() -> Path:
    """Ask Windows for its system directory; never trust PATH/SystemRoot."""
    if os.name != 'nt':
        raise InputStateError('Native input state requires Windows')
    kernel = ctypes.WinDLL('kernel32.dll', winmode=LOAD_LIBRARY_SEARCH_SYSTEM32)
    function = kernel.GetSystemDirectoryW
    function.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32]
    function.restype = ctypes.c_uint32
    buffer = ctypes.create_unicode_buffer(32768)
    length = function(buffer, len(buffer))
    if not 0 < length < len(buffer):
        raise InputStateError('Windows did not provide a bounded system directory')
    directory = Path(buffer.value)
    if not directory.is_absolute():
        raise InputStateError('Windows system directory is not absolute')
    return directory


class _WindowsInputAPI:
    """Only documented read functions from explicitly named system DLLs."""

    def __init__(self):
        system = _system_directory()
        self.user32 = ctypes.WinDLL(str(system / 'user32.dll'),
                                   winmode=LOAD_LIBRARY_SEARCH_SYSTEM32)
        self.user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        self.user32.GetAsyncKeyState.restype = ctypes.c_int16
        self.xinput = None
        self.xinput_dll = None
        for basename in ('xinput1_4.dll', 'xinput9_1_0.dll'):
            try:
                library = ctypes.WinDLL(str(system / basename),
                                        winmode=LOAD_LIBRARY_SEARCH_SYSTEM32)
            except OSError as exc:
                if getattr(exc, 'winerror', None) != 126:
                    raise InputStateError('Cannot load the Windows XInput API') from exc
                continue
            try:
                function = library.XInputGetState
            except AttributeError as exc:
                raise InputStateError('System XInput DLL lacks XInputGetState') from exc
            function.argtypes = [ctypes.c_uint32, ctypes.POINTER(XINPUT_STATE)]
            function.restype = ctypes.c_uint32
            self.xinput, self.xinput_dll = library, str(system / basename)
            break

    def get_async_key_state(self, key: int) -> int:
        return int(self.user32.GetAsyncKeyState(key))

    def get_controller_state(self, index: int) -> tuple[int, XINPUT_STATE | None]:
        if self.xinput is None:
            return ERROR_DEVICE_NOT_CONNECTED, None
        state = XINPUT_STATE()
        result = int(self.xinput.XInputGetState(index, ctypes.byref(state)))
        return result, state if result == ERROR_SUCCESS else None


class Win32InputState:
    """Primitive-only handler for the Lua broker's two read-only input APIs.

    Without an explicit controller index, the first connected slot among 0..3
    is returned. Disconnection/unavailable system XInput produces None, while
    unexpected native errors remain visible. Axis and trigger values are raw;
    no dead-zone, trigger-threshold or button remapping is applied.
    """

    def __init__(self, api: Any = None):
        self._api = api

    @property
    def api(self) -> Any:
        if self._api is None:
            self._api = _WindowsInputAPI()
        return self._api

    def is_key_pressed(self, key: int) -> bool:
        if type(key) is not int or not 0 <= key <= 255:
            raise InputStateError('isKeyPressed requires a virtual-key integer in 0..255')
        return bool(self.api.get_async_key_state(key) & 0x8000)

    def controller_state(self, index: int | None = None) -> dict | None:
        if index is not None and (type(index) is not int or not 0 <= index <= 3):
            raise InputStateError('Controller index must be an integer in 0..3 or nil')
        for selected in range(4) if index is None else (index,):
            result, state = self.api.get_controller_state(selected)
            if result == ERROR_DEVICE_NOT_CONNECTED:
                continue
            if result != ERROR_SUCCESS or not isinstance(state, XINPUT_STATE):
                raise InputStateError(f'XInputGetState failed with status {result}')
            pad = state.Gamepad
            values = {'ControllerID': selected, 'PacketNumber': int(state.dwPacketNumber),
                      'LeftTrigger': int(pad.bLeftTrigger), 'RightTrigger': int(pad.bRightTrigger),
                      'ThumbLeftX': int(pad.sThumbLX), 'ThumbLeftY': int(pad.sThumbLY),
                      'ThumbRightX': int(pad.sThumbRX), 'ThumbRightY': int(pad.sThumbRY)}
            values.update({name: bool(pad.wButtons & mask)
                           for name, mask in GAMEPAD_BUTTONS.items()})
            return values
        return None

    def __call__(self, name: str, arguments: tuple) -> bool | dict | None:
        if not isinstance(arguments, (tuple, list)):
            raise InputStateError('Input broker arguments must be a sequence')
        if name == 'isKeyPressed' and len(arguments) == 1:
            return self.is_key_pressed(arguments[0])
        if name == 'getXBox360ControllerState' and len(arguments) <= 1:
            return self.controller_state(arguments[0] if arguments else None)
        raise InputStateError('Unsupported input request or argument count: ' + str(name))
