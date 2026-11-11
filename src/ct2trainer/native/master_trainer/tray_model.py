"""MT-32 (0.43): pure tray decision layer for the Master Trainer.

The OS seam (``tray.py``) is a thin Windows wrapper; every decision
the UI makes around the notification tray - which events produce a
balloon, with which display text, and whether a pending minimize
diverts into the tray instead of the taskbar - lives here so it stays
testable without a Windows session or a live tray icon.

Events (the names the trainer attach/detach transition observer and
the trainer-start failure path report):

- ``attached``  - a trainer session confirmed its target attach
  (the engine memory handle went from nothing to a live target).
- ``detached``  - the target process exited, or the user detached on
  purpose (MT-12); the trainer session is still alive, effects are
  cleared.  The notification is informative; the user-initiated case
  is not distinguished - the balloon is harmless either way.
- ``attention`` - the trainer start failed with a named refusal; the
  ``detail`` argument carries the displayable reason.

Dedup rule (``TrayNotifier``): one balloon per distinct
(event, body) pair.  A repeated identical event - the engine
re-reports the same failure on consecutive ticks, or the same
attach/detach pair repeats - does not re-post; a changed detail
(another failure message, another table or process) does.
"""
from __future__ import annotations

TRAY_EVENT_ATTACHED = "attached"
TRAY_EVENT_DETACHED = "detached"
TRAY_EVENT_ATTENTION = "attention"
TRAY_EVENTS = (TRAY_EVENT_ATTACHED, TRAY_EVENT_DETACHED,
               TRAY_EVENT_ATTENTION)

# The tooltip under the tray icon (NOTIFYICONDATAW szTip, 127 chars).
TRAY_TIP = "CT2Trainer Master"

# Win32 balloon field limits (NOTIFYICONDATAW szInfoTitle = 63,
# szInfo = 255); the trims leave a one-character margin each.
_MAX_TITLE = 62
_MAX_BODY = 254


def tray_message(event, table=None, process=None, detail=None):
    """The displayable ``(title, body)`` balloon pair for one event.

    ``table`` and ``process`` are display names (table relative path /
    key and bound process name); either or both may be None when the
    context is unknown.  ``detail`` is the named refusal detail for
    the attention event.  Raises ValueError for an unknown event.
    """
    if event not in TRAY_EVENTS:
        raise ValueError("unknown tray event: " + repr(event))
    if event == TRAY_EVENT_ATTACHED:
        title = "Trainer attached"
        if table and process:
            body = table + " is attached to " + process + "."
        elif table:
            body = table + " is attached."
        elif process:
            body = "Attached to " + process + "."
        else:
            body = "A trainer session is attached."
    elif event == TRAY_EVENT_DETACHED:
        title = "Target detached"
        if table and process:
            body = process + " left; " + table + " is no longer " \
                "attached."
        elif table:
            body = table + " is no longer attached."
        else:
            body = "The target process is no longer attached."
    else:  # TRAY_EVENT_ATTENTION
        title = "Trainer needs attention"
        body = (detail or "The trainer needs your attention.").strip()
    return (title[:_MAX_TITLE], body[:_MAX_BODY])


def minimize_decision(tray_enabled, window_hidden):
    """Whether a pending minimize should divert into the tray.

    True iff the persisted tray feature is on AND the window is still
    visible - an already hidden window stays hidden (no re-waiting,
    no double withdraw).
    """
    return bool(tray_enabled) and not bool(window_hidden)


class TrayNotifier:
    """Dedup layer: notify only on a distinct (event, body) pair.

    One instance per Master window; the UI calls :meth:`observe` for
    every attach / detach / attention event it receives and posts a
    balloon only when the returned payload is not None.
    """

    def __init__(self):
        self._last = None

    def observe(self, event, table=None, process=None, detail=None):
        """Return the ``(title, body)`` balloon payload for one event,
        or None when the event duplicates the last posted one."""
        title, body = tray_message(event, table=table, process=process,
                                   detail=detail)
        key = (event, body)
        if key == self._last:
            return None
        self._last = key
        return (title, body)
