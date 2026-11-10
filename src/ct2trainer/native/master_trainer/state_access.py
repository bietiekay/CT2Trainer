"""Pure state-access + opener layer for the Master Trainer (MT-30).

MT-30 (0.39): the waiting view gains two header buttons -
"State folder…" and "Debug log…" - that open the persisted state
home (``master-settings.json``, ``tables-index.json``, the
per-table sidecars, and the ``forced-recovery/`` archives created by
the 0.38 ``--force`` forced start) and the trainer debug log (the
frozen trainer writes ``<exe stem>.ct2debug.log`` next to the EXE
when the converter option "Debug logging" is enabled; the source
runtime writes ``ct2trainer-debug.log`` in the working directory -
the exact path is ``debug_log.default_log_path()``).

The module is the pure decision + opener layer:

- ``resolve_state_folder(state_home)`` / ``resolve_debug_log(path)``
  validate the target and raise the named
  :class:`StateAccessRefusal` when it cannot be opened (missing
  folder / missing log file - the status line names the cause,
  never a crash);
- ``choose_opener()`` selects the platform opener (``os.startfile``
  on Windows - the default shell; ``xdg-open`` on Linux / SteamOS
  through a fire-and-forget subprocess, no shell) and is the only
  place that touches an OS service;
- ``open_path(target, opener=None)`` hands the resolved path to the
  (injectable) opener and converts an opener failure into the named
  refusal.

No window, no Tk in this module - the UI layer renders the named
refusal into the status line.  Headless-testable: the opener is
injectable, the platform selection is a documented decision.
"""
from __future__ import annotations

import os
import sys
from typing import Callable


class StateAccessRefusal(ValueError):
    """A named MT-30 refusal.

    ``code`` is the stable machine-readable reason; ``detail`` is
    displayable in the status line.
    """

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


# ---------------------------------------------------------------------
# path resolution (named refusals, no opener yet)
# ---------------------------------------------------------------------

def resolve_state_folder(state_home) -> str:
    """The state home to open in the file manager.

    The folder must exist (the state home is created by the first
    persisted document - a genuinely fresh start has nothing to
    show yet) and must be a directory.  A missing or wrong-kind
    path is the named refusal (the status line says so, no crash).
    """
    if not isinstance(state_home, (str, os.PathLike)) or not state_home:
        raise StateAccessRefusal("state-folder-bad",
                                 "no state folder path given")
    path = os.fsdecode(os.path.abspath(state_home))
    if not os.path.isdir(path):
        raise StateAccessRefusal(
            "state-folder-missing",
            "the state folder does not exist yet (nothing has been "
            "persisted): " + path)
    return path


def resolve_debug_log(log_path) -> str:
    """The trainer debug log to open.

    The file must exist (debug logging is a converter option - an
    un-enabled build writes no log at all, and a fresh install has
    written none yet).  A missing or wrong-kind path is the named
    refusal (the status line says so, no crash).
    """
    if not isinstance(log_path, (str, os.PathLike)) or not log_path:
        raise StateAccessRefusal("debug-log-bad",
                                 "no debug log path given")
    path = os.fsdecode(os.path.abspath(log_path))
    if not os.path.isfile(path):
        raise StateAccessRefusal(
            "debug-log-missing",
            "the debug log does not exist (debug logging may be "
            "disabled, or no trainer session has written it "
            "yet): " + path)
    return path


# ---------------------------------------------------------------------
# opener selection (the only OS-service boundary)
# ---------------------------------------------------------------------

def choose_opener() -> Callable[[str], None]:
    """The platform path-opener.

    Windows: ``os.startfile`` (the default shell opens the file
    manager / the default text handler).  Linux / SteamOS:
    ``xdg-open`` (the desktop handler, started as a detached
    subprocess - no shell, no wait), so the waiting view stays
    responsive.  A missing opener is the named refusal
    ``no-opener`` (documented - e.g. a headless SteamOS session
    without a desktop environment; the status line names the
    cause, no crash).
    """
    if sys.platform == "win32":
        return os.startfile  # type: ignore[attr-defined]
    import shutil
    xdg = shutil.which("xdg-open")
    if xdg is None:
        raise StateAccessRefusal(
            "no-opener",
            "no desktop opener is available on this platform "
            "(xdg-open was not found)")

    def opener(path: str) -> None:
        import subprocess
        subprocess.Popen([xdg, path], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)

    return opener


def open_path(target: str, *,
             opener: Callable[[str], None] | None = None) -> None:
    """Open one resolved path with the (injectable) platform opener.

    ``opener`` is the test seam (a callable taking the path); the
    default is :func:`choose_opener`, evaluated at call time so a
    test can patch it.  A non-string / empty target is the named
    refusal ``bad-path``; an opener failure (a refused start) is
    the named refusal ``opener-failed`` - never a crash.
    """
    if not isinstance(target, str) or not target:
        raise StateAccessRefusal("bad-path", "no path to open")
    if opener is None:
        opener = choose_opener()
    try:
        opener(target)
    except StateAccessRefusal:
        raise
    except Exception as exc:
        raise StateAccessRefusal(
            "opener-failed",
            "the opener failed: " + exc.__class__.__name__
            + ": " + str(exc)) from exc
