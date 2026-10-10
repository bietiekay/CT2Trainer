"""Tone synthesis and playback guards for the trainer UI toggle sounds."""
from __future__ import annotations

import struct
import unittest
from unittest import mock

import winsound

from ct2trainer.native import ui
from ct2trainer.native.ui import _TONE_CACHE, _tone_wav, play_toggle_sound


class ToneTests(unittest.TestCase):
    def test_tone_wav_is_a_valid_pcm_header_with_exact_frame_count(self):
        rate = 22050
        raw = _tone_wav(880.0, 120, rate=rate)
        self.assertEqual(raw[:4], b"RIFF")
        self.assertEqual(raw[8:12], b"WAVE")
        self.assertEqual(raw[12:16], b"fmt ")
        self.assertEqual(struct.unpack("<I", raw[16:20])[0], 16)
        self.assertEqual(struct.unpack("<HHIIHH", raw[20:36]), (1, 1, rate, rate * 2, 2, 16))
        self.assertEqual(raw[36:40], b"data")
        frames = 2 * int(rate * 120 / 1000)
        self.assertEqual(struct.unpack("<I", raw[40:44])[0], frames)
        self.assertEqual(len(raw) - 44, frames)
        self.assertEqual(struct.unpack("<I", raw[4:8])[0], 36 + frames)

    def test_tone_starts_and_ends_silent(self):
        raw = _tone_wav(440.0, 120, rate=22050)
        first = struct.unpack("<h", raw[44:46])[0]
        last = struct.unpack("<h", raw[-2:])[0]
        self.assertEqual(first, 0)  # sin(0) at sample 0
        self.assertLess(abs(last), 100)  # 20 ms fade-out tail, click-free

    def test_play_caches_both_tones_and_uses_memory_async_flags(self):
        _TONE_CACHE.clear()
        with mock.patch.object(winsound, "PlaySound") as play:
            play_toggle_sound(on=True)
            play_toggle_sound(on=False)
            play_toggle_sound(on=True)
        self.assertEqual(set(_TONE_CACHE), {"on", "off"})
        self.assertEqual(play.call_count, 3)
        args, _kwargs = play.call_args_list[0]
        buffer, flags = args[0], args[1]
        self.assertIsInstance(buffer, bytes)
        self.assertEqual(buffer[:4], b"RIFF")
        self.assertEqual(flags, winsound.SND_MEMORY | winsound.SND_ASYNC)

    def test_play_never_raises_without_audio(self):
        _TONE_CACHE.clear()
        with mock.patch("builtins.__import__", side_effect=ModuleError()):
            play_toggle_sound(on=True)


class ModuleError(ImportError):
    pass
