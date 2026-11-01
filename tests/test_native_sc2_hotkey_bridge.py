"""SC2 hotkey-bridge field fix (0.22.1): T1/T2/T3/T7 regressions.

Field case 2026-10-31 (Sinking City 2 on 0.19, 3 sessions):
  T1 - a stripped user32 build lacks RegisterHotKeyW/UnregisterHotKeyW;
       the real seam called the exports unconditionally, so a raw
       AttributeError escaped where the module promises the named,
       non-blocking HotkeyRegistrationError.
  T2 - that error escaped _hotkey_sync through the toggle path (a
       confirmed enable reported toggle-failed with its wish already
       persisted) and the poll path (poll-crashed -> engine-blocked ->
       every toggle and close() refused).  A hotkey-registry/bridge
       failure is now a named per-entry warning, never an engine fault.
  T3 - the message-only window lived on the calling thread while the
       loop thread pumped its own queue, so the quit message was
       undeliverable, destroy() always hit the 5 s join timeout, the
       window was never destroyed and the daemon loop thread
       access-violated in GetMessageW during process teardown.  The
       window is now created on the loop thread; the WNDPROC destroys
       it from its own thread and quits the pump; destroy() posts the
       quit message (checked) and joins.
  T7 - the state-save that persisted the wish preceded toggle-failed.
       The toggle transaction now runs the hotkey mirror before
       toggle-ok, so a confirmed enable is the only path that persists
       the wish and a failed enable persists nothing.

Coverage:
  1. missing-export guard (T1): the real seam raises the exact named
     HotkeyRegistrationError - never a raw AttributeError.
  2. real-seam close protocol (T3): connect + destroy roundtrip
     completes within the join timeout with no error; destroy is
     idempotent-safe; register + unregister + destroy ordering; a
     second bridge instance in the same process starts clean.
  3. engine (T2/T7): toggle where hotkey registration raises the named
     error after a successful programmatic enable (entry stays enabled,
     no toggle-failed, per-entry warning, pinned event ordering);
     failed enable persists no wish; poll where the hotkey drain
     fails (no engine-blocked, deduped warning); re-attach where the
     hotkey sync fails (engine stays usable); close() with pending
     hotkey warnings and with a failing bridge teardown proceeds.

The real Win32 seam is exercised on Windows only; the engine scenarios
run everywhere through the injected bridge contract (no real window,
no real OS hotkey - the real RegisterHotKey route stays AP-11
evidence).
"""
from __future__ import annotations

import sys
import struct
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from test_native_engine import FakeMemory
from test_native_engine_code import Coordinator
from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import NativeRuntimeError, TrainerEngine
from ct2trainer.native.hotkey_bridge import (HotkeyBridge,
                                             HotkeyBridgeError,
                                             HotkeyRegistrationError,
                                             _real_seam)
from ct2trainer.native.hotkey_model import HotKeySpec

LOG_NAME = "ct2trainer-debug.log"

ALT_PRINT = HotKeySpec.parse("alt+PRINT")
CTRL_ALT_F12 = HotKeySpec.parse("ctrl+alt+F12")


class Sc2Memory(FakeMemory):
    """FakeMemory with the hook-journal identity surface the Coordinator
    receipt journal requires (the base fake predates it)."""

    def __init__(self, pid=123, creation_time=456):
        super().__init__(pid=pid, creation_time=creation_time)
        # The entry patch site is anchor+0x16 (the AA dialect reads the
        # trailing offset as hex: 0x1000 base + 0x16 = 0x1016, data offset
        # 22).  It must hold a complete valid one-byte instruction: the
        # hook layer displaces the original bytes only when they decode as
        # a full instruction stream (the zero filler byte there decodes
        # invalid in the pinned iced-x86 build).  0x56 (PUSH RSI) is the
        # byte the fixture's DISABLE script restores.
        self.data[22] = 0x56

    @property
    def identity(self):
        return self.pid, self.creation_time

    def is_executable(self, address, size):
        return False

    def restart(self):
        """Simulate a fresh target process after the target ended.

        The previous session's writes vanish with the old process: the
        memory image is re-seeded with the unpatched layout (anchor
        header plus the planted 0x56 at the patch site, data offset 22)
        and the process is alive again.  This mirrors the real
        re-attach contract: a new process image carries the original
        bytes, so the captured-original invariant of the disable script
        holds again.
        """
        self.data[:] = bytes(256)
        self.data[:16] = b"CT2T-FIX-2026-01"
        self.data[16:20] = struct.pack("<I", 1234)
        self.data[22] = 0x56
        self.alive = True
        self.closed = False

# Entry 1 anchors on the fixture memory header (present at module
# offset 0: "CT2T-FIX-2026-01") and patches anchor+0x16 (hex offset per
# the AA dialect, 0x1016 absolute; original byte 0x56 planted by
# Sc2Memory, outside the anchor pattern so a re-scan after a target
# restart still matches).  Entry 2 anchors on a pattern that is never
# present, so its enable fails with the named zero-match scan refusal.
SC2_CT = '''<CheatTable CheatEngineTableVersion="45"><CheatEntries>
<CheatEntry><ID>1</ID><Description>"hotkey ok entry"</Description>
<VariableType>Auto Assembler Script</VariableType><AssemblerScript>[ENABLE]
aobscanmodule(HkOk,FixtureTarget.exe,43 54 32 54 2D 46 49 58 2D 32 30 32 36 2D 30 31)
registersymbol(HkOk)
HkOk+16:
 db 90

[DISABLE]
HkOk+16:
 db 56
unregistersymbol(HkOk)</AssemblerScript>
<Hotkeys><Hotkey Active="1"><Keys><Key>18</Key><Key>45</Key></Keys><Action>Toggle Activation</Action></Hotkey></Hotkeys>
</CheatEntry>
<CheatEntry><ID>2</ID><Description>"hotkey fail entry"</Description>
<VariableType>Auto Assembler Script</VariableType><AssemblerScript>[ENABLE]
aobscanmodule(HkFail,FixtureTarget.exe,DE AD BE EF)
registersymbol(HkFail)
HkFail+1:
 db 90

[DISABLE]
HkFail+1:
 db AD
unregistersymbol(HkFail)</AssemblerScript>
</CheatEntry>
</CheatEntries></CheatTable>'''


class _StrippedUser32:
    """A user32 stand-in with the hotkey exports removed (T1 guard).

    Delegates everything to the real DLL; the stripped names raise
    AttributeError exactly like a stripped / minimal user32 build does
    on the real export lookup.
    """

    def __init__(self, real, strip=()):
        object.__setattr__(self, "_real", real)
        object.__setattr__(self, "_strip", frozenset(strip))

    def __getattr__(self, name):
        if name in self._strip:
            raise AttributeError(f"function '{name}' not found")
        return getattr(self._real, name)


class FaultyBridge:
    """Engine-side duck type driving the named bridge-error containment
    paths (register / unregister / drain / close faults)."""

    def __init__(self, register_error=None, unregister_error=None,
                 drain_error=None, close_error=None):
        self.register_error = register_error
        self.unregister_error = unregister_error
        self.drain_error = drain_error
        self.close_error = close_error
        self.registered = set()
        self.close_calls = 0

    def register(self, spec):
        if self.register_error is not None:
            raise self.register_error
        self.registered.add(spec)
        return len(self.registered)

    def unregister(self, spec):
        if self.unregister_error is not None:
            raise self.unregister_error
        self.registered.discard(spec)
        return True

    def take_specs(self):
        if self.drain_error is not None:
            raise self.drain_error
        return ()

    def close(self):
        self.close_calls += 1
        if self.close_error is not None:
            raise self.close_error
        self.registered.clear()


@unittest.skipUnless(sys.platform == "win32",
                    "the real user32 hotkey seam is Windows-only")
class MissingExportGuardTests(unittest.TestCase):
    """T1: a stripped user32 build raises the named error, never a raw
    AttributeError."""

    def _seam_with_stripped(self, strip):
        # Patch ctypes.WinDLL so the seam receives a user32 twin without
        # the hotkey exports, regardless of whether the local build
        # actually has them (the field bug occurred on exactly such
        # stripped builds).
        import ctypes
        real_user32 = ctypes.WinDLL("user32", use_last_error=True)
        real_windll = ctypes.WinDLL

        def fake_windll(name, use_last_error=False):
            if name == "user32":
                return _StrippedUser32(
                    real_windll(name, use_last_error=use_last_error),
                    strip=strip)
            return real_windll(name, use_last_error=use_last_error)

        with patch.object(ctypes, "WinDLL", fake_windll):
            return _real_seam()

    def test_register_hotkey_missing_export_raises_named_error(self):
        seam = self._seam_with_stripped(("RegisterHotKeyW",
                                         "UnregisterHotKeyW"))
        with self.assertRaises(HotkeyRegistrationError) as caught:
            seam.register_hotkey(1, 0x0001, 45)
        self.assertIs(type(caught.exception), HotkeyRegistrationError)
        self.assertNotIsInstance(caught.exception, AttributeError)
        self.assertIn("RegisterHotKeyW", str(caught.exception))
        self.assertIn("missing from user32", str(caught.exception))

    def test_unregister_hotkey_missing_export_raises_named_error(self):
        seam = self._seam_with_stripped(("UnregisterHotKeyW",))
        with self.assertRaises(HotkeyRegistrationError) as caught:
            seam.unregister_hotkey(1)
        self.assertIs(type(caught.exception), HotkeyRegistrationError)
        self.assertNotIsInstance(caught.exception, AttributeError)
        self.assertIn("UnregisterHotKeyW", str(caught.exception))
        self.assertIn("missing from user32", str(caught.exception))


@unittest.skipUnless(sys.platform == "win32",
                    "the real OS hotkey seam is Windows-only")
class RealSeamCloseProtocolTests(unittest.TestCase):
    """T3: the window now lives on the loop thread, so the quit protocol
    completes and the deterministic 5 s close timeout is gone."""

    def test_connect_destroy_roundtrip_completes_within_join_timeout(self):
        seam = _real_seam()
        hwnd = seam.connect(lambda hotkey_id: None)
        self.assertIsInstance(hwnd, int)
        self.assertGreater(hwnd, 0)
        started = time.monotonic()
        seam.destroy()  # must not raise (pre-fix: guaranteed 5 s timeout)
        elapsed = time.monotonic() - started
        # The pre-fix destroy always ran the full 5 s join timeout; the
        # fixed protocol completes in a fraction of a second.
        self.assertLess(elapsed, 4.0)
        # destroy is idempotent-safe: a second call is a clean no-op.
        seam.destroy()

    def test_register_unregister_destroy_ordering(self):
        seam = _real_seam()
        bridge = HotkeyBridge(seam=seam)
        try:
            registered = False
            try:
                bridge.register(CTRL_ALT_F12)
                registered = True
            except HotkeyRegistrationError:
                # Another process may own the combination in this
                # environment; the regression is the lifecycle protocol,
                # not a busy key.
                self.assertTrue(bridge.is_registered(CTRL_ALT_F12)
                                or not registered)
            if registered:
                self.assertTrue(bridge.is_registered(CTRL_ALT_F12))
                self.assertTrue(bridge.unregister(CTRL_ALT_F12))
                self.assertFalse(bridge.is_registered(CTRL_ALT_F12))
            started = time.monotonic()
            bridge.close()
            self.assertLess(time.monotonic() - started, 4.0)
            self.assertTrue(bridge._closed)
            # Idempotent close: the second call does not raise.
            bridge.close()
        finally:
            if not bridge._closed:
                bridge.close()

    def test_second_bridge_instance_starts_clean(self):
        # Per-instance window class names: a later bridge in the same
        # process registers a fresh class instead of reusing one bound
        # to a stale WNDPROC.
        first = _real_seam()
        first_hwnd = first.connect(lambda hotkey_id: None)
        second = _real_seam()
        second_hwnd = second.connect(lambda hotkey_id: None)
        self.assertGreater(first_hwnd, 0)
        self.assertGreater(second_hwnd, 0)
        self.assertNotEqual(first_hwnd, second_hwnd)
        second.destroy()
        first.destroy()


class Sc2HotkeyEngineTests(unittest.TestCase):
    """T2/T7: bridge faults are named per-entry warnings, never engine
    faults; the wish persists only for a confirmed enable."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.cwd = self.root / "cwd"
        self.cwd.mkdir()
        table = self.root / "sc2_hotkey.ct"
        table.write_text(SC2_CT, encoding="utf-8")
        self.plan = compile_table(table, "FixtureTarget.exe", debug_log=True)
        self.memory = Sc2Memory()
        self.engine = None

    def tearDown(self):
        if self.engine is not None and not self.engine.closed:
            self.memory.alive = False
            self.engine.poll()
            self.engine.close()

    def start(self):
        with patch("pathlib.Path.cwd", return_value=self.cwd):
            self.engine = TrainerEngine(
                self.plan, state_dir=self.root / "state",
                process_lock_dir=self.root / "shared",
                memory_factory=lambda name: self.memory,
                hook_coordinator=Coordinator())
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)
        return self.engine

    def events(self):
        log = self.cwd / LOG_NAME
        if not log.exists():
            return []
        import json
        return [json.loads(line) for line in
                log.read_text(encoding="utf-8").splitlines() if line.strip()]

    def event(self, name, identifier=None):
        return [e for e in self.events() if e["event"] == name
                and (identifier is None or e.get("identifier") == identifier)]

    def test_toggle_registration_failure_is_warning_not_failure(self):
        # T2 + T7 regression: the hotkey registration raises the named
        # error after a successful programmatic enable; the entry stays
        # enabled, there is no toggle-failed, and the pinned event
        # ordering is state-save -> toggle-ok with no toggle-failed after
        # it (the field sequence state-save -> toggle-failed is gone).
        engine = self.start()
        bridge = FaultyBridge(register_error=HotkeyRegistrationError(
            "alt+PRINT",
            "the combination is already registered by another "
            "process (E_ACCESS_DENIED)"))
        engine.hotkey_bridge = bridge
        self.assertTrue(engine.toggle(1, True))
        self.assertIn(1, engine.applied)
        self.assertEqual(self.memory.read(0x1016, 1), b"\x90")
        self.assertIn(1, engine.desired)
        self.assertFalse(engine.blocked)
        self.assertEqual(
            engine.hotkey_warnings,
            ["OS hotkey registration failed for alt+PRINT: the combination "
             "is already registered by another process (E_ACCESS_DENIED)."])
        # Exactly one named debug event for the fault.
        faults = self.event("hotkey-bridge-failed")
        self.assertEqual(len(faults), 1)
        self.assertEqual(faults[0].get("where"), "register")
        # Pinned event ordering: state-save (the confirmed enable's wish)
        # precedes toggle-ok, and no toggle-failed follows it.
        ordered = [e["event"] for e in self.events()]
        ok_indexes = [i for i, name in enumerate(ordered)
                      if name == "toggle-ok"
                      and (self.events()[i].get("identifier") == 1)]
        save_indexes = [i for i, name in enumerate(ordered)
                        if name == "state-save"]
        failed_indexes = [i for i, name in enumerate(ordered)
                          if name == "toggle-failed"]
        self.assertTrue(ok_indexes)
        self.assertTrue(save_indexes)
        self.assertEqual(failed_indexes, [])
        self.assertGreater(max(ok_indexes), max(save_indexes))
        # The binding stays published for the programmatic dispatch
        # path despite the OS registration failure.
        self.assertEqual(engine.hotkey_controller.find(ALT_PRINT).record_id, 1)
        result = engine.dispatch_hotkey(ALT_PRINT)
        self.assertEqual(result.status, "triggered")
        self.assertEqual(result.record_id, 1)
        self.assertNotIn(1, engine.applied)
        self.assertEqual(self.memory.read(0x1016, 1), b"\x56")
        self.assertEqual(engine.desired, set())
        self.assertFalse(engine.blocked)
        self.assertEqual(len(engine.hotkey_warnings), 1)

    def test_failed_enable_persists_no_wish(self):
        # T7 invariant from the other side: a genuinely failed enable
        # reports toggle-failed and persists nothing (the failed attempt
        # stays visibly inactive and is not repeated as a saved wish).
        engine = self.start()
        with self.assertRaises(NativeRuntimeError):
            engine.toggle(2, True)
        self.assertNotIn(2, engine.applied)
        self.assertNotIn(2, engine.desired)
        self.assertFalse(engine.blocked)
        self.assertEqual(len(self.event("toggle-failed", 2)), 1)
        self.assertEqual(self.event("toggle-ok", 2), [])
        self.assertEqual(self.event("state-save"), [])
        self.assertFalse(self.memory.writes)

    def test_poll_drain_failure_dedupes_and_keeps_engine_alive(self):
        # T2 poll path: a named fault from the hotkey drain is a
        # deduplicated per-entry warning, never a poll-crashed /
        # engine-blocked fault; the poll continues.
        engine = self.start()
        bridge = FaultyBridge()
        engine.hotkey_bridge = bridge
        self.assertTrue(engine.toggle(1, True))
        self.assertIn(1, engine.applied)

        def faulting_source():
            raise HotkeyBridgeError(
                "the OS hotkey bridge queue is unavailable")

        engine.hotkey_spec_source = faulting_source
        engine.poll()
        self.assertFalse(engine.blocked)
        self.assertTrue(engine.connected, engine.status)
        self.assertIn(1, engine.applied)
        self.assertEqual(
            engine.hotkey_warnings,
            ["the OS hotkey bridge queue is unavailable"])
        # Repeat: the warning and the debug event are deduped (exactly
        # one per distinct message, no traceback spam on repeats).
        engine.poll()
        engine.poll()
        self.assertEqual(len(engine.hotkey_warnings), 1)
        faults = self.event("hotkey-bridge-failed")
        self.assertEqual(len(faults), 1)
        self.assertEqual(faults[0].get("where"), "drain")
        self.assertFalse(engine.blocked)
        # The programmatic dispatch path keeps working.
        self.assertFalse(engine.toggle(1, False))
        self.assertNotIn(1, engine.applied)

    def test_reattach_hotkey_sync_failure_keeps_engine_usable(self):
        # T2 attach path (the field S2 shape): the restore-time hotkey
        # sync faults with a named bridge error; the engine must not
        # block, the restored effect stands, and later toggles work.
        engine = self.start()
        self.assertTrue(engine.toggle(1, True))
        engine.hotkey_bridge = FaultyBridge(register_error=HotkeyBridgeError(
            "hotkey bridge window thread failed: simulated loop-thread "
            "fault"))
        # Confirmed target exit: the detach releases the OS spec.
        self.memory.alive = False
        engine.poll()
        self.assertIsNone(engine.memory)
        # Re-attach: a fresh target process with the unpatched memory
        # image; the saved wish restores and the hotkey sync faults -
        # contained as a per-entry warning.
        self.memory.restart()
        engine.poll()
        self.assertTrue(engine.connected, engine.status)
        self.assertFalse(engine.blocked)
        self.assertIn(1, engine.applied)
        self.assertIn(1, engine.desired)
        self.assertEqual(
            engine.hotkey_warnings,
            ["hotkey bridge window thread failed: simulated loop-thread "
             "fault"])
        faults = self.event("hotkey-bridge-failed")
        self.assertEqual(len(faults), 1)
        self.assertEqual(faults[0].get("where"), "register")
        # The engine stays fully usable after the fault.
        self.assertFalse(engine.toggle(1, False))
        self.assertNotIn(1, engine.applied)
        self.assertFalse(engine.blocked)

    def test_close_proceeds_with_pending_hotkey_warnings(self):
        # T2 close: pending hotkey warnings never refuse the close.
        engine = self.start()
        engine.hotkey_bridge = FaultyBridge(register_error=HotkeyRegistrationError(
            "alt+PRINT",
            "the combination is already registered by another "
            "process (E_ACCESS_DENIED)"))
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(len(engine.hotkey_warnings), 1)
        self.assertTrue(engine.close())
        self.assertTrue(engine.closed)

    def test_close_proceeds_when_bridge_teardown_fails(self):
        # T2 close (the field S2 close-refusal shape): a bridge teardown
        # failure (quit post / join timeout) is a named warning, not a
        # close fault; close() completes and the trainer state is
        # released.
        engine = self.start()
        bridge = FaultyBridge(close_error=HotkeyBridgeError(
            "hotkey bridge message loop did not stop within 5s"))
        engine.hotkey_bridge = bridge
        self.assertTrue(engine.toggle(1, True))
        self.assertIn(ALT_PRINT, bridge.registered)
        self.assertTrue(engine.close())
        self.assertTrue(engine.closed)
        self.assertEqual(bridge.close_calls, 1)
        self.assertIsNone(engine.hotkey_bridge)
        self.assertEqual(
            engine.hotkey_warnings,
            ["hotkey bridge message loop did not stop within 5s"])
        faults = self.event("hotkey-bridge-failed")
        self.assertEqual(len(faults), 1)
        self.assertEqual(faults[0].get("where"), "close")
        self.assertFalse(engine.blocked)


if __name__ == "__main__":
    unittest.main()
