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
it.  The actual playback uses ``winmm.PlaySoundW`` directly (ctypes)
with a persistent in-memory buffer: the stdlib ``winsound`` wrapper
refuses ``SND_MEMORY | SND_ASYNC`` outright (RuntimeError), which made
every tick silently fail in the field (2026-11-13 fix).
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
# Win32 winmm flags: play from an in-memory WAV buffer, asynchronously.
SND_ASYNC = 0x1
SND_MEMORY = 0x4

# Pre-synthesized sound buffers, kept in module scope for the whole
# process: SND_MEMORY requires the buffer to stay alive for the whole
# playback.
_SOUND_CACHE: dict[str, bytes] = {}

# winmm binding + stable in-memory playback buffers (2026-11-13 field
# fix).  The stdlib ``winsound.PlaySound`` wrapper REFUSES
# ``SND_ASYNC`` from memory ("Cannot play asynchronously from memory",
# RuntimeError) because it cannot guarantee a temporary buffer's
# lifetime; the CE 7.5 reference instead plays its built-in ticks
# asynchronously from fixed memory.  We mirror that: bind
# ``winmm.PlaySoundW`` directly and hand it a pointer to one persistent
# ctypes buffer per kind, kept here for the whole process so it stays
# valid for the whole asynchronous playback.  On the old winsound path
# every play_sound() call raised, was swallowed by the "never raises"
# guard and returned "refused: audio unavailable" - i.e. no tick ever
# played, neither on manual toggles nor on attach.
_WINMM_LIB = None
_PLAY_SOUND_W = None  # lazily bound PlaySoundW (None while unbound)
_BUFFER_CACHE: dict[str, object] = {}  # kind -> persistent ctypes buffer


def _bind_play_sound_w():
    """Lazily bind ``winmm.PlaySoundW``; returns None when unavailable.

    The house Win32 pattern (see ``hotkey_bridge``): attribute access on
    the loaded DLL with explicit argtypes/restype, guarded so a stripped
    or missing winmm build is a named refusal, never a crash.
    ``PlaySoundW`` returns BOOL; with ``SND_MEMORY`` the first parameter
    is a pointer to the WAV bytes (RIFF header first) and ``hModule`` is
    NULL.  The DLL is loaded with ``use_last_error`` so a failed call
    can be named with its Win32 error code.
    """
    global _WINMM_LIB, _PLAY_SOUND_W
    if _PLAY_SOUND_W is not None:
        return _PLAY_SOUND_W
    try:
        import ctypes
        import ctypes.wintypes
        lib = ctypes.WinDLL("winmm", use_last_error=True)
        fn = lib.PlaySoundW
        fn.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                       ctypes.wintypes.DWORD]
        fn.restype = ctypes.wintypes.BOOL
    except Exception:
        _WINMM_LIB = None
        _PLAY_SOUND_W = None
        return None
    _WINMM_LIB = lib
    _PLAY_SOUND_W = fn
    return fn


def _sound_buffer(kind: str, data: bytes):
    """The persistent in-memory buffer for one sound kind.

    ``create_string_buffer`` copies the WAV bytes into a ctypes array
    we own; caching it keeps the pointer stable across asynchronous
    playbacks (SND_MEMORY requires the buffer to outlive the call).
    """
    import ctypes
    buffer = _BUFFER_CACHE.get(kind)
    if buffer is None:
        buffer = ctypes.create_string_buffer(data)
        _BUFFER_CACHE[kind] = buffer
    return buffer


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
    """Test seam: drop all cached buffers (WAV bytes + the persistent
    winmm memory buffers)."""
    _SOUND_CACHE.clear()
    _BUFFER_CACHE.clear()


def play_sound(kind: str) -> str:
    """Play one trainer sound best-effort; never raises.

    Returns a stable named result: ``played`` (Windows, winmm
    available), ``skipped: non-windows platform`` or
    ``refused: <reason>`` (unknown kind / audio unavailable).  The
    buffer is a module-level cache entry, so it stays alive for the
    whole asynchronous playback.

    2026-11-13 field fix: the stdlib ``winsound.PlaySound`` wrapper
    raises ``RuntimeError("Cannot play asynchronously from memory")``
    for ``SND_MEMORY | SND_ASYNC``, so every play call silently failed
    (swallowed by the never-raises guard) and no tick ever reached the
    user.  Playback now goes through ``winmm.PlaySoundW`` directly via
    ctypes against the persistent cached buffer (see module docstring
    and the CE 7.5 reference behavior: RCDATA ticks played
    asynchronously from memory).
    """
    try:
        data = sound_bytes(kind)
    except ValueError as exc:
        return "refused: " + str(exc)
    if sys.platform != "win32":
        return "skipped: non-windows platform"
    play = _bind_play_sound_w()
    if play is None:
        return "refused: winmm unavailable"
    buffer = _sound_buffer(kind, data)
    try:
        ok = play(buffer, None, SND_MEMORY | SND_ASYNC)
    except Exception:
        return "refused: audio unavailable"
    if not ok:
        import ctypes
        code = ctypes.get_last_error()
        return "refused: PlaySoundW failed (Win32 %d)" % code
    return "played"
