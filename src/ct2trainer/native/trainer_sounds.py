"""Clean-room tick sounds for the standalone trainer (2026-11-01).

Behavior reference (read-only, never copied): the Cheat Engine 7.5
native trainer generator plays two built-in tick sounds on cheat
toggle - ``Activate`` (``tick1.wav``) and ``Deactivate``
(``tick2.wav``, both registered as RCDATA resources in ``Sounds.RC``).
They are short (~28 ms), 8-bit unsigned mono, 11025 Hz, high-pitch
(~4.4 kHz activate / ~3.8 kHz deactivate) square-wave ticks with a
flat envelope, played through the Win32 winmm ``PlaySound`` API as
memory buffers (``SND_MEMORY | SND_ASYNC``).  The reference-corpus
tables carry no audio files of their own, so the original sound set
is exactly this built-in pair.

Clean-room: the ticks below are synthesized deterministically in code
in the same format and pitch character as the originals (integer
sample periods so the 11025 Hz grid lands on ~5.5 kHz on / ~3.7 kHz
off, the original on/off character); no CE asset bytes enter the
repository or the generated trainer.  The trainer adds one further
sound the CE generator does not have: a distinct attach-success
double tick (product request 2026-11-01: a sound for successful
attach plus the manual on/off toggle sounds).

Playback is best-effort: Windows-only, never raises into the UI, and
returns a stable named result string so callers can log or display
it.
"""
from __future__ import annotations

import struct
import sys

# Format character of the original native trainer generator ticks
# (tick1.wav / tick2.wav): 8-bit unsigned mono, 11025 Hz, ~28 ms.
TICK_RATE = 11025
# Integer sample periods on the 11025 Hz grid: period 2 -> 5512.5 Hz
# (high on tick), period 3 -> 3675 Hz (lower off tick; the original
# deactivate tick measures ~3.8 kHz).
_ON_FREQ = 5512.5
_OFF_FREQ = 3675.0
_ON_MS = 28
_OFF_MS = 28
# Attach success: a double tap (two short ticks, one silent gap) so it
# reads clearly as different from the single on/off ticks.
_ATTACH_FREQ = _OFF_FREQ
_ATTACH_TICK_MS = 20
_ATTACH_GAP_MS = 12

# Pre-synthesized sound buffers, kept in module scope for the whole
# process: SND_MEMORY requires the buffer to stay alive for the whole
# playback.
_SOUND_CACHE: dict[str, bytes] = {}


def tick_frames(freq: float, ms: int, rate: int = TICK_RATE,
                amp: int = 120) -> bytes:
    """One square-wave tick as raw 8-bit unsigned mono PCM bytes.

    Deterministic: same inputs always produce the same bytes.  A short
    fade-in/out (4 ms) keeps the click-free ends; the flat middle keeps
    the tick character of the original.
    """
    if freq <= 0 or ms <= 0 or rate <= 0:
        raise ValueError("freq, ms and rate must all be positive")
    n = max(1, int(rate * ms / 1000))
    fade = max(1, int(rate * 0.004))
    period = max(2, int(round(rate / freq)))
    half = max(1, period // 2)
    frames = bytearray()
    for i in range(n):
        if i + 1 >= fade and n - i >= fade:
            gain = 1.0
        else:
            gain = min((i + 1) / fade, (n - i) / fade)
        sample = amp if (i % period) < half else -amp
        frames.append(max(0, min(255, int(128 + sample * gain))))
    return bytes(frames)


def wav_from_frames(frames: bytes, rate: int = TICK_RATE) -> bytes:
    """Wrap raw 8-bit unsigned mono PCM frames in a RIFF/WAVE container."""
    header = (b"RIFF" + struct.pack("<I", 36 + len(frames)) + b"WAVEfmt "
              + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate, 1, 8)
              + b"data" + struct.pack("<I", len(frames)))
    return bytes(header + frames)


def tick_wav(freq: float, ms: int, rate: int = TICK_RATE,
             amp: int = 120) -> bytes:
    """One square-wave tick as 8-bit unsigned mono WAV bytes."""
    return wav_from_frames(tick_frames(freq, ms, rate, amp), rate)


def _attach_wav() -> bytes:
    """The attach-success double tick: two short ticks, one silent gap.

    Silence in 8-bit unsigned PCM is 128, not 0 - the gap is explicit
    128 bytes.
    """
    tick = tick_frames(_ATTACH_FREQ, _ATTACH_TICK_MS)
    gap = bytes([128]) * int(TICK_RATE * _ATTACH_GAP_MS / 1000)
    return wav_from_frames(tick + gap + tick)


def sound_bytes(kind: str) -> bytes:
    """WAV bytes for one trainer sound.

    ``attach`` is played on a confirmed attach to the target process;
    ``on`` / ``off`` on a confirmed manual toggle of an item.
    """
    if kind == "on":
        cached = _SOUND_CACHE.get(kind)
        if cached is None:
            cached = tick_wav(_ON_FREQ, _ON_MS)
            _SOUND_CACHE[kind] = cached
        return cached
    if kind == "off":
        cached = _SOUND_CACHE.get(kind)
        if cached is None:
            cached = tick_wav(_OFF_FREQ, _OFF_MS)
            _SOUND_CACHE[kind] = cached
        return cached
    if kind == "attach":
        cached = _SOUND_CACHE.get(kind)
        if cached is None:
            cached = _attach_wav()
            _SOUND_CACHE[kind] = cached
        return cached
    raise ValueError("Unknown trainer sound: " + repr(kind))


def clear_sound_cache() -> None:
    """Test seam: drop all cached buffers."""
    _SOUND_CACHE.clear()


def play_sound(kind: str) -> str:
    """Play one trainer sound best-effort; never raises.

    Returns a stable named result: ``played`` (Windows, winmm
    available), ``skipped: non-windows platform`` or
    ``refused: <reason>`` (unknown kind / audio unavailable).  The
    buffer is a module-level cache entry, so it stays alive for the
    whole asynchronous playback.
    """
    try:
        data = sound_bytes(kind)
    except ValueError as exc:
        return "refused: " + str(exc)
    if sys.platform != "win32":
        return "skipped: non-windows platform"
    try:
        import winsound
        winsound.PlaySound(data, winsound.SND_MEMORY | winsound.SND_ASYNC)
    except Exception:
        return "refused: audio unavailable"
    return "played"
