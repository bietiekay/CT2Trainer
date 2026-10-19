"""Pure layout contract for the native Touch UI (row grid, WP-58).

Independent, testable form of the ``TrainerWindow`` layout rules from
``ct2trainer.native.ui`` (no Tk objects involved): initial window clamping,
filter-chip columns, minimum window sizes, the compact chrome row stack
(48 px header / 48 px filter row / 32 px status / 28 px amber banner
strips / 48 px pagination), the row-area floor (56 px), the row heights
(64 px switch / 72 px value / 120 px expanded value / 48 px section) and
the per-view page math.  The pure functions here own the no-overlap window
row model, the 48-px touch minimum for interactive rows and the
``layout_violations()`` report.  The numeric constants mirror the values
used by ``ui.py`` so the pure contract stays aligned with the real
frontend; the per-record row model (row kinds, states, truncation, hit
areas, section counters, page slicing) lives in ``ui_rows.py``.
"""
from __future__ import annotations

from dataclasses import dataclass

MIN_WINDOW_WIDTH = 400
MIN_WINDOW_HEIGHT_WIDE = 610
MIN_WINDOW_HEIGHT_NARROW = 720
MAX_WINDOW_WIDTH = 1600
MAX_WINDOW_HEIGHT = 900
INITIAL_HEIGHT_FLOOR = 620
NARROW_THRESHOLD = 650  # window width < 650 -> 2x3 chip grid + own search row
FILTER_CHIP_COLUMNS_WIDE = 5
FILTER_CHIP_COLUMNS_NARROW = 2
MAX_PAGE_ROWS = 12
TOUCH_MINIMUM = 48  # interactive targets are at least 48 logical pixels
MIN_ROW_AREA = 56  # the row area must hold at least this much height

# Row heights (D1): switch / value / expanded value / group section header.
ROW_HEIGHT_SWITCH = 64
ROW_HEIGHT_VALUE = 72
ROW_HEIGHT_VALUE_EXPANDED = 120
ROW_HEIGHT_SECTION = 48
ROW_INDENT_STEP = 12  # per nesting level, with a 1 px left rule

# Compact chrome rows (D7).
CHROME_HEADER = 48
CHROME_FILTER = 48  # wide mode: chips + inline search in one row
CHROME_FILTER_GRID = 96  # narrow mode: 2x3 chip grid (2 rows x 48)
CHROME_SEARCH = 48  # narrow mode: dedicated search row
CHROME_STATUS = 32
CHROME_PAGINATION = 48
BANNER_HEIGHT = 28  # hotkey-conflict / table-Lua amber strips

# Touch control geometry (D7/D8).
FILTER_CHIP_SIZE = (80, 48)
GROUP_TOGGLE_SIZE = (32, 40)
PAGINATION_BUTTON_SIZE = (56, 48)
INFO_CHIP_SIZE = 16
PILL_SIZE = (40, 24)

VIEWS = ("Switches", "On", "Saved", "Values", "All")
# Smallest row each view can produce; used for the fast page-size estimate
# and the "fits at least one row" layout check.  Mixed content is paginated
# exactly by the row model's ``slice_pages`` in ``ui_rows``.
_VIEW_ROW_HEIGHT = {
    "Switches": ROW_HEIGHT_SWITCH,
    "On": ROW_HEIGHT_SWITCH,
    "Saved": ROW_HEIGHT_SWITCH,
    "Values": ROW_HEIGHT_VALUE,
    "All": ROW_HEIGHT_SECTION,
}
# Chrome rows that carry inputs or buttons and therefore meet the 48-px
# touch minimum; the status row and banner strips are display-only.
_INTERACTIVE_CHROME = frozenset({"header", "filter", "chips", "search", "pagination"})


class LayoutError(ValueError):
    """Invalid layout request (unknown view, negative size, ...)."""


@dataclass(frozen=True)
class WindowRow:
    name: str
    top: int
    height: int

    @property
    def bottom(self) -> int:
        return self.top + self.height


def _check_view(view: str) -> None:
    if view not in VIEWS:
        raise LayoutError(f"Unknown view {view!r}; expected one of {VIEWS}")


def _chrome_rows(width: int, banner_count: int) -> list:
    """Top-down fixed chrome rows for one width and banner count.

    Wide windows keep the five filter chips plus the inline search in one
    48 px row; narrow windows fall back to a 2x3 chip grid and give the
    search field its own 48 px row.  Banner strips stack directly under
    the status row, above the row area.
    """
    rows = [("header", CHROME_HEADER)]
    if width < NARROW_THRESHOLD:
        rows.append(("chips", CHROME_FILTER_GRID))
        rows.append(("search", CHROME_SEARCH))
    else:
        rows.append(("filter", CHROME_FILTER))
    rows.append(("status", CHROME_STATUS))
    rows.extend((f"banner{i}", BANNER_HEIGHT) for i in range(banner_count))
    rows.append(("pagination", CHROME_PAGINATION))
    return rows


def initial_window_size(screen_width: int, screen_height: int) -> tuple[int, int]:
    """Initial trainer window size from the screen, clamped to the contract."""
    if screen_width <= 0 or screen_height <= 0:
        raise LayoutError("Screen dimensions must be positive")
    width = min(MAX_WINDOW_WIDTH, max(MIN_WINDOW_WIDTH, screen_width - 100))
    height = min(MAX_WINDOW_HEIGHT, max(INITIAL_HEIGHT_FLOOR, screen_height - 100))
    return width, height


def window_columns(width: int) -> int:
    """Filter-chip columns: five in one row when wide, a 2x3 grid when narrow."""
    if width < 0:
        raise LayoutError("Width must be nonnegative")
    return (FILTER_CHIP_COLUMNS_NARROW if width < NARROW_THRESHOLD
            else FILTER_CHIP_COLUMNS_WIDE)


def min_window_size(width: int) -> tuple[int, int]:
    """Minimum allowed window size for the column mode of the given width."""
    if width < MIN_WINDOW_WIDTH:
        raise LayoutError("Width is below the hard minimum 400")
    return MIN_WINDOW_WIDTH, (MIN_WINDOW_HEIGHT_NARROW if width < NARROW_THRESHOLD else MIN_WINDOW_HEIGHT_WIDE)


def rows_area_height(window_height: int, width: int, banner_count: int = 0) -> int:
    """Height left for the row list after all fixed chrome rows.

    ``banner_count`` accounts for the 28 px amber banner strips that may
    sit between the status row and the row area (hotkey conflicts,
    table-Lua bootstrap failures).
    """
    if window_height < 0 or width < 0:
        raise LayoutError("Window dimensions must be nonnegative")
    if type(banner_count) is not int or banner_count < 0:
        raise LayoutError("Banner count must be a nonnegative integer")
    return window_height - sum(height for _, height in _chrome_rows(width, banner_count))


def window_rows(window_height: int, width: int, banner_count: int = 0) -> list:
    """Stacked, non-overlapping window rows; the row area takes the remainder.

    The row area ("rows") is the flexible row between the fixed chrome rows
    and the pagination row; it may be negative for a below-minimum window,
    in which case ``layout_violations`` reports it.
    """
    if window_height < 0 or width < 0:
        raise LayoutError("Window dimensions must be nonnegative")
    if type(banner_count) is not int or banner_count < 0:
        raise LayoutError("Banner count must be a nonnegative integer")
    rows: list[WindowRow] = []
    top = 0
    for name, height in _chrome_rows(width, banner_count):
        rows.append(WindowRow(name, top, height))
        top += height
    rows.append(WindowRow("rows", top, window_height - top))
    return rows


def page_size_for_rows(area_height: int, view: str) -> int:
    """Fast per-view page-size estimate (at least one, at most MAX_PAGE_ROWS).

    Uses the smallest row height the view can produce; the renderer paginates
    mixed content exactly through ``ui_rows.slice_pages`` and treats this
    estimate only as a navigation clamp.
    """
    _check_view(view)
    if area_height < 0:
        raise LayoutError("Row area height must be nonnegative")
    return max(1, min(MAX_PAGE_ROWS, area_height // _VIEW_ROW_HEIGHT[view]))


def next_page(page: int, delta: int, count: int, page_size: int) -> int:
    """Clamped page navigation, mirroring TrainerWindow.move_page."""
    if page_size < 1:
        raise LayoutError("Page size must be at least 1")
    maximum = max(0, (count - 1) // page_size)
    return min(maximum, max(0, page + delta))


def filter_change(page: int, drafts: dict) -> tuple[int, dict]:
    """A view/search change resets the page but preserves every value draft."""
    return 0, drafts


def layout_violations(window_width: int, window_height: int, view: str,
                      banner_count: int = 0) -> list[str]:
    """All contract violations of one window size, empty when the layout fits.

    Checks: the hard window minimums, the 48-px touch minimum on interactive
    chrome rows, the 56-px row-area floor, at least one full row of the
    active view fitting the row area, and that no two rows overlap or leave
    the window.
    """
    _check_view(view)
    if window_width < 0 or window_height < 0:
        raise LayoutError("Window dimensions must be nonnegative")
    if type(banner_count) is not int or banner_count < 0:
        raise LayoutError("Banner count must be a nonnegative integer")
    violations: list[str] = []
    if window_width < MIN_WINDOW_WIDTH:
        violations.append(f"window width {window_width} below minimum {MIN_WINDOW_WIDTH}")
    min_height = (MIN_WINDOW_HEIGHT_NARROW if window_width < NARROW_THRESHOLD
                  else MIN_WINDOW_HEIGHT_WIDE)
    if window_height < min_height:
        violations.append(f"window height {window_height} below minimum {min_height} for {window_columns(window_width)}-column mode")
    rows = window_rows(window_height, window_width, banner_count)
    for row in rows:
        if row.name in _INTERACTIVE_CHROME and row.height < TOUCH_MINIMUM:
            violations.append(f"row {row.name} is {row.height}px below the {TOUCH_MINIMUM}px touch minimum")
        if row.bottom > window_height:
            violations.append(f"row {row.name} extends beyond the window ({row.bottom} > {window_height})")
    for left in range(len(rows)):
        for right in range(left + 1, len(rows)):
            a, b = rows[left], rows[right]
            if a.top < b.bottom and b.top < a.bottom:
                violations.append(f"rows {a.name} and {b.name} overlap")
    area = next(row for row in rows if row.name == "rows")
    if area.height < MIN_ROW_AREA:
        violations.append(f"row area ({area.height}px) below the {MIN_ROW_AREA}px minimum")
    if area.height < _VIEW_ROW_HEIGHT[view]:
        violations.append(f"row area ({area.height}px) fits fewer than one {view} row ({_VIEW_ROW_HEIGHT[view]}px)")
    return violations


# ---------------------------------------------------------------------------
# Staged record state (WP-14, C5)
#
# A supported value record whose symbols are uniquely provided by other
# supported entries carries ``staged`` plan metadata.  While any provider is
# not live the record is *pending*: reads/writes/freeze are refused by the
# engine (a state, not a fault) and the row shows the provider names and
# waits.  Once every provider id is applied the row unlocks automatically
# (the poll loop re-renders on applied-set changes).  Master-toggle records
# (``activation_sets``) are script rows with a set-shaped chip.
# ---------------------------------------------------------------------------

STAGED_NONE = "none"
STAGED_PENDING = "pending"
STAGED_LIVE = "live"


def staged_card_state(entry, applied) -> str:
    """'none' | 'pending' | 'live' for one plan entry against applied ids.

    ``applied`` is any key/membership container of live entry ids.  An entry
    without staged metadata is always ``none``; a staged entry is pending
    until every provider id is applied (an empty provider list is vacuously
    live).
    """
    staged = entry.get("staged")
    if not staged:
        return STAGED_NONE
    for provider_id in staged.get("provider_ids", ()):
        if provider_id not in applied:
            return STAGED_PENDING
    return STAGED_LIVE


def staged_provider_labels(entry) -> list:
    """Provider labels carried by the entry's staged metadata, in order."""
    staged = entry.get("staged") or {}
    return list(staged.get("provider_labels", ()))


def address_provider_marker(entry) -> str:
    """Trainer-UI marker for a heading whose relative children inherit a
    runtime-computed base (WP-38 dynamic address provider).

    Consumes only the additive ``address_provider`` plan field, so the UI
    carries no parallel metadata; the provider record itself keeps its
    ordinary switch row.  Returns the contract phrase when the heading
    carries the field, ``''`` otherwise.
    """
    marker = entry.get("address_provider")
    if isinstance(marker, dict):
        return "Address provided at runtime"
    return ""


def activation_set_record_ids(entry) -> tuple:
    """(enable_ids, disable_ids) of a master-toggle activation set, or ([], [])."""
    sets = entry.get("activation_sets") or {}
    return (list(sets.get("enable", ())), list(sets.get("disable", ())))


def activation_set_summary(entry, entries, limit: int = 8) -> str:
    """Compact one-line summary of the records a master toggle covers.

    Returns '' when the entry carries no activation set.  Record ids are
    rendered with their plan labels (unknown ids fall back to the bare id)
    and the list is truncated to ``limit`` names per direction.
    """
    enable, disable = activation_set_record_ids(entry)
    if not enable and not disable:
        return ""
    by_id = {entry_["id"]: entry_ for entry_ in entries.values()}

    def _names(ids):
        names = [(by_id.get(i) or {}).get("label") or str(i) for i in ids]
        if len(names) > limit:
            return ", ".join(names[:limit]) + " (+%d more)" % (len(names) - limit)
        return ", ".join(names)

    parts = []
    if enable:
        parts.append("apply: " + _names(enable))
    if disable:
        parts.append("clear: " + _names(disable))
    return "Master toggle - " + "; ".join(parts)


# ---------------------------------------------------------------------------
# Record hotkey display (WP-40, pure, Tk-free)
#
# The plan entry's "hotkeys" list carries every original source binding
# (byte-verified by both plan validators); the engine publishes the live
# subset with the first-wins conflict policy.  These render the per-record
# binding lines (original binding + active state) and the trainer-wide
# warning banner from plain state.
# ---------------------------------------------------------------------------


def hotkey_binding_line(key_text: str, registered: bool) -> str:
    """One original-binding line: 'F1 (active)' or 'F2 (not registered)'.

    ``key_text`` is the canonical human form of the source key
    combination; ``registered`` reflects the engine's first-wins
    publication state for the record that declared the binding.
    """
    if not isinstance(key_text, str) or not key_text:
        raise LayoutError("Hotkey binding line needs a nonempty key text.")
    if type(registered) is not bool:
        raise LayoutError("Hotkey binding line needs a boolean registration state.")
    return f"{key_text} (active)" if registered else f"{key_text} (not registered)"


def hotkey_conflict_banner(warnings, limit: int = 3) -> str:
    """Trainer-wide banner text for hotkey registration warnings.

    ``warnings`` is the engine's deduplicated, monotonic warning list;
    at most ``limit`` warnings render verbatim, the remainder collapse
    into a bounded counter so the banner stays one readable line on
    large tables.  Empty string when there is nothing to warn.
    """
    if not isinstance(limit, int) or limit < 1:
        raise LayoutError("Hotkey banner limit must be a positive integer.")
    if warnings is None:
        warnings = []
    if not isinstance(warnings, (list, tuple)):
        raise LayoutError("Hotkey banner needs a warning list.")
    if not all(isinstance(item, str) for item in warnings):
        raise LayoutError("Hotkey banner warnings must be text.")
    if not warnings:
        return ""
    shown = list(warnings[:limit])
    text = "Hotkeys: " + " | ".join(shown)
    if len(warnings) > limit:
        text += f" | {len(warnings) - limit} more"
    return text
