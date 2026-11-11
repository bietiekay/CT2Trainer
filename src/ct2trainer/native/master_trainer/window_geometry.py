"""MT-33 (0.43): pure window-geometry decision layer for the Master
Trainer.

The persisted geometry is the ``window_geometry`` field of the
master-state document (schema 10): null (nothing stored yet) or an
object with exactly the four keys ``x``, ``y``, ``w``, ``h`` - strict
integers, the window's position and outer size in screen pixels.

The restore pass clamps the stored geometry into the primary screen
bounds, so a dead monitor layout or a stale stored value can never
hide the window off-screen: at least ``VISIBLE_MARGIN`` pixels of the
window must stay visible on every axis, and the size is clamped to
[minimum, screen size].  A malformed stored document raises the named
:class:`GeometryRefusal` and the caller falls back to the default
window size (displaying the reason in the status line).
"""
from __future__ import annotations

# The documented default window (byte-identical to the pre-0.43
# behavior: "1160x600" without an explicit position).
DEFAULT_WIDTH = 1160
DEFAULT_HEIGHT = 600
# A restored window never shrinks below this.
GEOMETRY_MIN_WIDTH = 320
GEOMETRY_MIN_HEIGHT = 240
# At least this many pixels of the window must stay visible on every
# axis after the clamp (a window parked entirely off-screen is
# brought back with its edge on the screen).
VISIBLE_MARGIN = 64
# Documented bound for every stored geometry value (multi-monitor
# positions can be negative; nothing sane lives beyond +/- 16384 px).
GEOMETRY_BOUNDS = 16384

GEOMETRY_KEYS = ("x", "y", "w", "h")


class GeometryRefusal(ValueError):
    """A stored window geometry that cannot be applied.

    ``reason`` is the stable named code; ``detail`` the displayable
    detail (the UI shows it and keeps the default window size).
    """

    def __init__(self, reason, detail):
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


def default_geometry_spec() -> str:
    """The documented default Tk geometry spec: 1160x600, no explicit
    position (the window manager places it)."""
    return "%dx%d" % (DEFAULT_WIDTH, DEFAULT_HEIGHT)


def capture_geometry(root) -> dict | None:
    """One window's current geometry as the persistable document
    (strict integers).

    None when the widget is torn down, uninitialised, or degenerate
    (a non-positive size) - the caller simply keeps the previous value
    then.
    """
    try:
        x = int(root.winfo_x())
        y = int(root.winfo_y())
        w = int(root.winfo_width())
        h = int(root.winfo_height())
    except Exception:
        return None
    if w <= 0 or h <= 0:
        return None
    return {"x": x, "y": y, "w": w, "h": h}


def geometry_spec(geometry: dict) -> str:
    """The Tk geometry string for one captured geometry document."""
    return "%dx%d+%d+%d" % (geometry["w"], geometry["h"],
                            geometry["x"], geometry["y"])


def validate_geometry(geometry) -> None:
    """Validate one stored geometry value.

    None means "nothing stored" (valid).  Anything else must be an
    object with exactly the four strict-integer keys; sizes are
    non-negative and every value stays within the documented bounds.
    Raises the named :class:`GeometryRefusal`.
    """
    if geometry is None:
        return
    if type(geometry) is not dict or set(geometry) != set(GEOMETRY_KEYS):
        raise GeometryRefusal(
            "window-geometry-invalid",
            "the stored window geometry must be null or an object with "
            "exactly the keys x, y, w, h")
    for key in GEOMETRY_KEYS:
        if type(geometry[key]) is not int:
            raise GeometryRefusal(
                "window-geometry-invalid",
                "the stored window geometry value %r must be a strict "
                "integer" % key)
    if geometry["w"] < 0 or geometry["h"] < 0:
        raise GeometryRefusal(
            "window-geometry-invalid",
            "the stored window geometry sizes must be non-negative")
    for key in GEOMETRY_KEYS:
        if not -GEOMETRY_BOUNDS <= geometry[key] <= GEOMETRY_BOUNDS:
            raise GeometryRefusal(
                "window-geometry-invalid",
                "the stored window geometry value %r is out of bounds "
                "(+/- %d)" % (key, GEOMETRY_BOUNDS))


def restore_geometry(geometry, screen_w: int, screen_h: int) -> str:
    """Resolve one stored geometry (or None) to the Tk geometry spec to
    apply on the given screen.

    None (nothing stored) keeps the documented default 1160x600.  A
    stored document is validated (named refusal on malformed) and then
    clamped into the screen: the size never leaves the screen and
    never drops below the documented minimum, and the window keeps at
    least ``VISIBLE_MARGIN`` pixels visible on every axis - a dead
    monitor layout can therefore not hide the window.
    """
    validate_geometry(geometry)
    if geometry is None:
        return default_geometry_spec()
    # size: clamp to the screen, but never below the minimum (a screen
    # smaller than the minimum takes the screen size - degenerate, but
    # the window stays usable).
    w = max(min(geometry["w"], screen_w), min(GEOMETRY_MIN_WIDTH, screen_w))
    h = max(min(geometry["h"], screen_h), min(GEOMETRY_MIN_HEIGHT, screen_h))
    # position: keep VISIBLE_MARGIN of the window on the screen.
    x = max(min(geometry["x"], screen_w - VISIBLE_MARGIN),
            -(w - VISIBLE_MARGIN))
    y = max(min(geometry["y"], screen_h - VISIBLE_MARGIN),
            -(h - VISIBLE_MARGIN))
    return "%dx%d+%d+%d" % (w, h, x, y)
