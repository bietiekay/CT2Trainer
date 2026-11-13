"""Trainer tick sounds (2026-11-01, user field request).

The generated trainer plays short tick sounds in the character of the
original native trainer generator's built-in Activate/Deactivate
sounds (behavior reference, read-only, never copied: CE 7.5
``Sounds.RC`` registers ``tick1.wav`` / ``tick2.wav`` as the
``BUILDIN_ACTIVATE`` / ``BUILDIN_DEACTIVATE`` RCDATA resources -
~28 ms, 8-bit unsigned mono, 11025 Hz, high-pitch square-wave ticks,
played through Win32 winmm ``PlaySound`` with
``SND_MEMORY | SND_ASYNC``; the reference corpus carries no audio
files of its own, so that built-in pair is the original sound set).

Clean-room: the ticks are synthesized deterministically in
``trainer_sounds`` (no CE asset bytes).  The trainer additionally
plays a distinct attach-success double tick (a sound the CE
generator does not have) on a confirmed (re-)attach.

Covered:
- synthesis: valid 8-bit mono WAV, exact frame counts, deterministic
  and cached, distinct per kind, pitch ordering, click-free fades,
  the attach double-tick shape, named refusals;
- playback: winmm.PlaySoundW memory+async flags against the persistent
  cached buffer, named refusals (unavailable winmm / Win32 code on a
  failed call), never raises, non-Windows skip, live winmm smoke;
- engine surface: confirmed hotkey activation toggles are recorded
  and popped (value-action hotkeys are not);
- UI wiring (real Tk window): the attach transition plays the attach
  tick exactly once, a failed attach attempt stays silent, manual row
  and group toggles play the on/off tick, and a hotkey-dispatched
  toggle plays its tick on the next poll tick (CE parity: the
  generated trainer sounds on every toggle, not only UI taps).
"""
from __future__ import annotations

import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from unittest.mock import patch

from ct2trainer.native import trainer_sounds
from native_tk_teardown import force_root_release
from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import TrainerEngine
from ct2trainer.native.hotkey_model import (HotkeyBinding, HotKeySpec,
                                            ToggleOutcomeStatus)
from test_native_engine import FakeMemory
from test_native_engine_code import Coordinator
from test_native_lua_activation import Memory
from test_native_record_hotkeys import CT_BODY

try:
    import tkinter as tk
    from ct2trainer.native import ui
    from ct2trainer.native.ui import TrainerWindow
except ImportError:  # pragma: no cover - environment without Tcl/Tk
    tk = None
    ui = None
    TrainerWindow = None

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "windows" / "fixture_target" / "fixture.ct"
PROCESS = "FixtureTarget.exe"

RATE = trainer_sounds.TICK_RATE


def _data(raw: bytes) -> bytes:
    return raw[44:]


def _crossings(data: bytes) -> int:
    return sum(1 for i in range(1, len(data))
               if (data[i - 1] < 128) != (data[i] < 128))


class TickSynthesisTests(unittest.TestCase):
    def test_tick_wav_is_valid_8bit_mono_pcm(self):
        raw = trainer_sounds.tick_wav(5512.5, 28)
        self.assertEqual(raw[:4], b"RIFF")
        self.assertEqual(raw[8:12], b"WAVE")
        self.assertEqual(raw[12:16], b"fmt ")
        self.assertEqual(struct.unpack("<HHIIHH", raw[20:36]),
                         (1, 1, RATE, RATE, 1, 8))
        self.assertEqual(raw[36:40], b"data")
        frames = int(RATE * 28 / 1000)
        self.assertEqual(struct.unpack("<I", raw[40:44])[0], frames)
        self.assertEqual(len(raw) - 44, frames)
        self.assertEqual(struct.unpack("<I", raw[4:8])[0], 36 + frames)

    def test_sounds_are_deterministic_and_cached(self):
        trainer_sounds.clear_sound_cache()
        first = trainer_sounds.sound_bytes("on")
        second = trainer_sounds.sound_bytes("on")
        self.assertIs(first, second)  # module cache keeps the buffer alive
        trainer_sounds.clear_sound_cache()
        third = trainer_sounds.sound_bytes("on")
        self.assertEqual(first, third)  # deterministic regeneration
        self.assertIsNot(first, third)

    def test_the_three_sounds_are_distinct(self):
        trainer_sounds.clear_sound_cache()
        on = trainer_sounds.sound_bytes("on")
        off = trainer_sounds.sound_bytes("off")
        attach = trainer_sounds.sound_bytes("attach")
        self.assertNotEqual(on, off)
        self.assertNotEqual(on, attach)
        self.assertNotEqual(off, attach)

    def test_on_tick_has_higher_pitch_than_off_tick(self):
        on = _data(trainer_sounds.sound_bytes("on"))
        off = _data(trainer_sounds.sound_bytes("off"))
        self.assertGreater(_crossings(on), _crossings(off))

    def test_ticks_start_and_end_near_silence(self):
        for kind in ("on", "off"):
            data = _data(trainer_sounds.sound_bytes(kind))
            self.assertLess(abs(data[0] - 128), 10)
            self.assertLess(abs(data[-1] - 128), 10)

    def test_attach_is_a_double_tick_with_silent_gap(self):
        tick = int(RATE * trainer_sounds._ATTACH_TICK_MS / 1000)
        gap = int(RATE * trainer_sounds._ATTACH_GAP_MS / 1000)
        data = _data(trainer_sounds.sound_bytes("attach"))
        self.assertEqual(len(data), 2 * tick + gap)
        middle = data[tick:tick + gap]
        self.assertTrue(all(b == 128 for b in middle))
        # the gap is interior, not at either end
        self.assertGreater(_crossings(data[:tick]), 0)
        self.assertGreater(_crossings(data[-tick:]), 0)

    def test_unknown_kind_is_refused_and_named(self):
        with self.assertRaises(ValueError):
            trainer_sounds.sound_bytes("bogus")
        self.assertEqual(
            trainer_sounds.play_sound("bogus"),
            "refused: Unknown trainer sound: 'bogus'")

    def test_tick_frames_reject_nonpositive_params(self):
        for bad in ((0.0, 28), (4400.0, -1), (4400.0, 28, 0)):
            with self.assertRaises(ValueError):
                trainer_sounds.tick_frames(*bad)


@unittest.skipUnless(sys.platform == "win32",
                     "winmm playback is Windows-only")
class PlaybackTests(unittest.TestCase):
    """The winmm.PlaySoundW seam (2026-11-13 field fix).

    The stdlib winsound wrapper refuses SND_MEMORY | SND_ASYNC outright
    (RuntimeError), so playback goes through the directly bound winmm
    export against one persistent ctypes buffer per kind.  These tests
    mock the binding, not the OS call.
    """

    def setUp(self):
        self._saved_fn = trainer_sounds._PLAY_SOUND_W
        self._saved_lib = trainer_sounds._WINMM_LIB
        trainer_sounds._PLAY_SOUND_W = None
        trainer_sounds._WINMM_LIB = None
        trainer_sounds.clear_sound_cache()

    def tearDown(self):
        trainer_sounds._PLAY_SOUND_W = self._saved_fn
        trainer_sounds._WINMM_LIB = self._saved_lib
        trainer_sounds.clear_sound_cache()

    def test_play_returns_played_and_uses_memory_async_flags(self):
        calls = []

        def fake_play(buffer, hmodule, flags):
            calls.append((buffer, hmodule, flags))
            return True

        with mock.patch.object(trainer_sounds, "_bind_play_sound_w",
                               return_value=fake_play):
            self.assertEqual(trainer_sounds.play_sound("on"), "played")
        self.assertEqual(len(calls), 1)
        buffer, hmodule, flags = calls[0]
        self.assertIsNone(hmodule)
        self.assertEqual(flags,
                         trainer_sounds.SND_MEMORY | trainer_sounds.SND_ASYNC)
        self.assertEqual(flags, 5)  # 0x4 | 0x1
        data = trainer_sounds._SOUND_CACHE["on"]
        self.assertEqual(data[:4], b"RIFF")
        self.assertEqual(bytes(buffer)[: len(data)], data)

    def test_play_uses_the_persistent_buffer_across_calls(self):
        buffers = []

        def fake_play(buffer, hmodule, flags):
            buffers.append(buffer)
            return True

        with mock.patch.object(trainer_sounds, "_bind_play_sound_w",
                               return_value=fake_play):
            trainer_sounds.play_sound("attach")
            trainer_sounds.play_sound("attach")
        self.assertEqual(len(buffers), 2)
        self.assertIs(buffers[0], buffers[1])

    def test_play_failure_never_raises(self):
        def fake_play(buffer, hmodule, flags):
            raise OSError("no audio device")

        with mock.patch.object(trainer_sounds, "_bind_play_sound_w",
                               return_value=fake_play):
            self.assertEqual(trainer_sounds.play_sound("off"),
                             "refused: audio unavailable")

    def test_failed_call_is_named_with_the_win32_error(self):
        with mock.patch.object(trainer_sounds, "_bind_play_sound_w",
                               return_value=lambda b, h, f: False), \
                mock.patch("ctypes.get_last_error", return_value=87):
            self.assertEqual(
                trainer_sounds.play_sound("on"),
                "refused: PlaySoundW failed (Win32 87)")

    def test_unavailable_winmm_is_a_named_refusal(self):
        with mock.patch.object(trainer_sounds, "_bind_play_sound_w",
                               return_value=None):
            self.assertEqual(trainer_sounds.play_sound("on"),
                             "refused: winmm unavailable")

    def test_play_skips_on_non_windows(self):
        with mock.patch.object(trainer_sounds.sys, "platform", "linux"):
            self.assertEqual(trainer_sounds.play_sound("on"),
                             "skipped: non-windows platform")

    def test_unknown_kind_is_refused_without_playback(self):
        buffers = []
        with mock.patch.object(
                trainer_sounds, "_bind_play_sound_w",
                return_value=lambda b, h, f: buffers.append(b) or True):
            self.assertEqual(
                trainer_sounds.play_sound("nope"),
                "refused: Unknown trainer sound: 'nope'")
        self.assertEqual(buffers, [])

    def test_real_winmm_playback_never_raises(self):
        # Live smoke on the actual export: the result is either
        # "played" or a named refusal (audio-device state of the test
        # host); it must never raise.  The pre-fix stdlib path raised
        # RuntimeError("Cannot play asynchronously from memory") here.
        result = trainer_sounds.play_sound("on")
        self.assertTrue(result == "played" or result.startswith("refused: "),
                        result)
class HotkeyUiToggleSurfaceTests(unittest.TestCase):
    """The engine surfaces confirmed hotkey activation toggles to the UI."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        ct = root / "hotkeys.ct"
        ct.write_text(CT_BODY, encoding="utf-8")
        self.plan = compile_table(ct, "FixtureTarget.exe")
        self.memory = Memory()
        self.engine = TrainerEngine(
            self.plan, state_dir=root / "state",
            process_lock_dir=root / "shared",
            memory_factory=lambda name: self.memory,
            hook_coordinator=Coordinator())
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)

    def tearDown(self):
        if not self.engine.closed:
            self.memory.alive = False
            self.engine.poll()
            self.engine.close()
        self.directory.cleanup()

    def test_confirmed_hotkey_activation_toggle_is_recorded_and_popped(self):
        self.assertTrue(self.engine.toggle(1, True))
        result = self.engine.dispatch_hotkey(HotKeySpec.parse("F1"))
        self.assertEqual(result.status, "triggered")
        self.assertEqual(result.outcome.status, ToggleOutcomeStatus.CONFIRMED)
        self.assertTrue(result.tone_played)
        self.assertEqual(self.engine.pop_hotkey_ui_toggles(), [(1, False)])
        # the pop drains the list; a second pop sees nothing
        self.assertEqual(self.engine.pop_hotkey_ui_toggles(), [])

    def test_hotkey_dispatch_records_the_resulting_active_state(self):
        # record 1 starts inactive: a direct binding-handler dispatch
        # toggles it ON and records the resulting active state
        self.assertFalse(1 in self.engine.applied)
        outcome = self.engine._hotkey_dispatch(
            HotkeyBinding("trainer", 1, HotKeySpec.parse("F1")))
        self.assertIs(outcome.status, ToggleOutcomeStatus.CONFIRMED)
        self.assertEqual(self.engine.pop_hotkey_ui_toggles(), [(1, True)])
        # the activation published the F1 binding: the public dispatch
        # now routes through it and records the toggle back to off
        self.assertEqual(
            self.engine.dispatch_hotkey(HotKeySpec.parse("F1")).status,
            "triggered")
        self.assertEqual(self.engine.pop_hotkey_ui_toggles(), [(1, False)])
        # deactivated: the binding is gone, dispatch is unbound, nothing records
        self.assertEqual(
            self.engine.dispatch_hotkey(HotKeySpec.parse("F1")).status,
            "unbound")
        self.assertEqual(self.engine.pop_hotkey_ui_toggles(), [])

    def test_value_action_hotkey_is_not_recorded(self):
        self.assertTrue(self.engine.toggle(1, True))  # provider live
        result = self.engine.dispatch_hotkey(HotKeySpec.parse("F2"))
        self.assertEqual(result.status, "triggered")
        self.assertEqual(self.engine.pop_hotkey_ui_toggles(), [])


@unittest.skipIf(tk is None or TrainerWindow is None,
                 "tkinter required for the real trainer window")
class TrainerWindowSoundTests(unittest.TestCase):
    """The window plays the ticks at the right moments (play_sound mocked)."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.shared = self.directory / "shared"
        self.cwd_dir = self.directory / "cwd"
        self.cwd_dir.mkdir()
        self.memory = FakeMemory()
        self.engine = None
        self.root = None

    def tearDown(self):
        if self.root is not None:
            force_root_release([self.root], ((self, "root"),))
        if self.engine is not None and not self.engine.closed:
            try:
                self.engine.close()
            except Exception:
                pass

    def _start(self, plan: dict) -> TrainerEngine:
        with patch("pathlib.Path.cwd", return_value=self.cwd_dir):
            self.engine = TrainerEngine(plan, self.directory,
                                        lambda _n: self.memory, self.shared)
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)
        return self.engine

    def _window(self) -> TrainerWindow:
        self.root = tk.Tk()
        self.root.withdraw()
        return TrainerWindow(self.root, self.engine)

    def _toggleable_id(self) -> int:
        for entry in self.engine.plan["entries"]:
            if (entry["supported"] and entry.get("selected", True)
                    and entry["kind"] == "script" and not entry.get("staged")):
                return entry["id"]
        self.fail("fixture plan has no toggleable script entry")

    def test_attach_transition_plays_attach_tick_once(self):
        plan = compile_table(FIXTURE, PROCESS)
        self._start(plan)
        window = self._window()
        memory = self.engine.memory
        self.engine.memory = None  # pretend the target exited
        def fake_poll():
            self.engine.memory = memory
            return f"Connected to {PROCESS} (PID {memory.pid})"
        self.engine.poll = fake_poll
        with mock.patch.object(ui, "play_sound") as play:
            window.poll()
        play.assert_called_once_with("attach")
        # steady state: no repeat
        with mock.patch.object(ui, "play_sound") as play2:
            window.poll()
        play2.assert_not_called()

    def test_failed_attach_attempt_plays_nothing(self):
        plan = compile_table(FIXTURE, PROCESS)
        self._start(plan)
        window = self._window()
        self.engine.memory = None
        self.engine.poll = lambda: "Waiting / hook into game unavailable: not running"
        with mock.patch.object(ui, "play_sound") as play:
            window.poll()
        play.assert_not_called()

    def test_manual_toggle_plays_on_then_off_tick(self):
        plan = compile_table(FIXTURE, PROCESS)
        self._start(plan)
        window = self._window()
        ident = self._toggleable_id()
        with mock.patch.object(ui, "play_sound") as play:
            window._toggle(ident)
        play.assert_called_once_with("on")
        self.assertIn(ident, self.engine.applied)
        with mock.patch.object(ui, "play_sound") as play:
            window._toggle(ident)
        play.assert_called_once_with("off")
        self.assertNotIn(ident, self.engine.applied)

    def test_group_toggle_plays_the_tick_for_the_resulting_state(self):
        plan = compile_table(FIXTURE, PROCESS)
        self._start(plan)
        window = self._window()
        ident = self._toggleable_id()
        with mock.patch.object(ui, "play_sound") as play:
            window._toggle_group(ident)
        expected = "on" if ident in self.engine.applied else "off"
        play.assert_called_once_with(expected)

    def test_hotkey_dispatched_toggle_plays_its_tick_on_next_poll(self):
        # The hotkey fixture needs the hooking Memory (identity) like the
        # record-hotkey tests, so the engine is built here, not via _start.
        ct = self.directory / "hotkeys.ct"
        ct.write_text(CT_BODY, encoding="utf-8")
        plan = compile_table(ct, PROCESS)
        memory = Memory()
        self.memory = memory
        with patch("pathlib.Path.cwd", return_value=self.cwd_dir):
            self.engine = TrainerEngine(plan, state_dir=self.directory / "state",
                                        process_lock_dir=self.shared,
                                        memory_factory=lambda _n: memory,
                                        hook_coordinator=Coordinator())
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)
        window = self._window()
        self.assertTrue(self.engine.toggle(1, True))
        self.engine.dispatch_hotkey(HotKeySpec.parse("F1"))  # toggles off
        with mock.patch.object(ui, "play_sound") as play:
            window.poll()
        play.assert_called_once_with("off")


if __name__ == "__main__":
    unittest.main()
