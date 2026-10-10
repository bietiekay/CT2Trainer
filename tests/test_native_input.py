"""Owned fake API cases plus a read-only Windows API availability smoke."""

import ctypes
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from ct2trainer.native.input_state import (
    ERROR_DEVICE_NOT_CONNECTED, GAMEPAD_BUTTONS, InputStateError,
    LOAD_LIBRARY_SEARCH_SYSTEM32, VIRTUAL_KEYS, Win32InputState,
    XINPUT_GAMEPAD, XINPUT_STATE, _WindowsInputAPI,
)


class FakeAPI:
    def __init__(self):
        self.keys = {}
        self.controllers = {}
        self.key_calls = []
        self.controller_calls = []

    def get_async_key_state(self, key):
        self.key_calls.append(key)
        return self.keys.get(key, 0)

    def get_controller_state(self, index):
        self.controller_calls.append(index)
        return self.controllers.get(index, (ERROR_DEVICE_NOT_CONNECTED, None))


class NativeInputTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeAPI()
        self.input = Win32InputState(self.api)

    def test_current_down_bit_ignores_recent_press_and_reserved_bits(self):
        for result, expected in [(0, False), (1, False), (0x7FFF, False),
                                 (0x8000, True), (-32768, True), (-1, True)]:
            self.api.keys[0x41] = result
            self.assertIs(self.input('isKeyPressed', (0x41,)), expected)
        self.assertEqual(self.api.key_calls, [0x41] * 6)

    def test_invalid_requests_do_not_poll_input(self):
        for key in (-1, 256, True, 1.0, 'A', None):
            with self.subTest(key=key), self.assertRaises(InputStateError):
                self.input('isKeyPressed', (key,))
        for index in (-1, 4, True, 1.0, '0'):
            with self.subTest(index=index), self.assertRaises(InputStateError):
                self.input('getXBox360ControllerState', (index,))
        for name, arguments in [('keyDown', (1,)), ('isKeyPressed', ()),
                                ('isKeyPressed', (1, 2)),
                                ('getXBox360ControllerState', (0, 1))]:
            with self.assertRaises(InputStateError):
                self.input(name, arguments)
        self.assertEqual(self.api.key_calls, [])
        self.assertEqual(self.api.controller_calls, [])

    def test_explicit_controller_preserves_all_raw_fields(self):
        state = XINPUT_STATE()
        state.dwPacketNumber = 0xFFFFFFFF
        state.Gamepad = XINPUT_GAMEPAD(0xA501, 0, 255, -32768, 32767, -123, 456)
        self.api.controllers[3] = (0, state)
        result = self.input('getXBox360ControllerState', (3,))
        self.assertEqual(self.api.controller_calls, [3])
        self.assertEqual({key: result[key] for key in
                          ('ControllerID', 'PacketNumber', 'LeftTrigger', 'RightTrigger',
                           'ThumbLeftX', 'ThumbLeftY', 'ThumbRightX', 'ThumbRightY')},
                         {'ControllerID': 3, 'PacketNumber': 0xFFFFFFFF,
                          'LeftTrigger': 0, 'RightTrigger': 255,
                          'ThumbLeftX': -32768, 'ThumbLeftY': 32767,
                          'ThumbRightX': -123, 'ThumbRightY': 456})
        for name, mask in GAMEPAD_BUTTONS.items():
            self.assertIs(result[name], bool(0xA501 & mask))
        self.assertEqual(set(result), set(GAMEPAD_BUTTONS) |
                         {'ControllerID', 'PacketNumber', 'LeftTrigger', 'RightTrigger',
                          'ThumbLeftX', 'ThumbLeftY', 'ThumbRightX', 'ThumbRightY'})

    def test_omitted_or_nil_controller_searches_first_connected_slot(self):
        self.api.controllers[2] = (0, XINPUT_STATE())
        self.api.controllers[3] = (0, XINPUT_STATE())
        self.assertEqual(self.input('getXBox360ControllerState', ())['ControllerID'], 2)
        self.assertEqual(self.api.controller_calls, [0, 1, 2])
        self.api.controller_calls.clear()
        self.assertEqual(self.input('getXBox360ControllerState', (None,))['ControllerID'], 2)
        self.assertEqual(self.api.controller_calls, [0, 1, 2])

    def test_disconnected_returns_nil_and_reconnect_is_seen_on_next_read(self):
        self.assertIsNone(self.input.controller_state())
        self.assertEqual(self.api.controller_calls, [0, 1, 2, 3])
        self.api.controllers[0] = (0, XINPUT_STATE())
        self.assertEqual(self.input.controller_state()['ControllerID'], 0)
        self.api.controllers.clear()
        self.assertIsNone(self.input.controller_state(0))

    def test_unexpected_controller_error_is_visible_not_disconnected(self):
        self.api.controllers[0] = (5, None)
        with self.assertRaisesRegex(InputStateError, 'status 5'):
            self.input.controller_state()
        self.assertEqual(self.api.controller_calls, [0])
        self.api.controllers[0] = (0, None)
        with self.assertRaises(InputStateError):
            self.input.controller_state(0)

    def test_native_struct_layout_and_documented_virtual_keys(self):
        self.assertEqual(ctypes.sizeof(XINPUT_GAMEPAD), 12)
        self.assertEqual(ctypes.sizeof(XINPUT_STATE), 16)
        self.assertEqual(XINPUT_STATE.Gamepad.offset, 4)
        self.assertEqual(VIRTUAL_KEYS['VK_A'], 0x41)
        self.assertEqual(VIRTUAL_KEYS['VK_0'], 0x30)
        self.assertEqual(VIRTUAL_KEYS['VK_F24'], 0x87)
        self.assertEqual(VIRTUAL_KEYS['VK_LCONTROL'], 0xA2)

    def test_secure_system_paths_and_documented_xinput_fallback(self):
        class Function:
            def __call__(self, *arguments): return 0
        class Library:
            GetAsyncKeyState = Function()
            XInputGetState = Function()
        calls = []
        def loader(path, *, winmode):
            calls.append((path, winmode))
            if Path(path).name == 'xinput1_4.dll':
                error = OSError('missing system XInput 1.4')
                error.winerror = 126
                raise error
            return Library()
        system = Path('C:/Windows/System32') if os.name == 'nt' else Path('/system32')
        with patch('ct2trainer.native.input_state._system_directory', return_value=system), \
                patch('ct2trainer.native.input_state.ctypes.WinDLL', loader, create=True):
            api = _WindowsInputAPI()
        self.assertEqual(calls, [(str(system / name), LOAD_LIBRARY_SEARCH_SYSTEM32)
                                 for name in ('user32.dll', 'xinput1_4.dll', 'xinput9_1_0.dll')])
        self.assertEqual(api.xinput_dll, str(system / 'xinput9_1_0.dll'))

    @unittest.skipUnless(os.name == 'nt', 'Win32 input smoke requires Windows')
    def test_actual_windows_read_only_api_smoke(self):
        native = Win32InputState()
        self.assertIsInstance(native.is_key_pressed(VIRTUAL_KEYS['VK_SHIFT']), bool)
        state = native.controller_state()
        self.assertTrue(state is None or isinstance(state, dict))
        if state is not None:
            self.assertIn(state['ControllerID'], range(4))
            self.assertIs(type(state['GAMEPAD_A']), bool)
        self.assertTrue(Path(native.api.xinput_dll).is_absolute()
                        if native.api.xinput_dll else True)


if __name__ == '__main__':
    unittest.main()
