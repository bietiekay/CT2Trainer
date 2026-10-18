"""Pure layout contract for the native Touch UI.

Independent, testable form of the ``TrainerWindow`` layout rules from
``ct2trainer.native.ui`` (no Tk objects involved): initial window clamping,
filter-button column count, minimum window sizes, per-view card heights,
page size (at most 12 rows), the 56-px touch control minimum, the stacked
no-overlap window row model and hierarchical group navigation. Groups that
CE would expand are rendered as buttons the user "switches into"; the pure
functions here own the level stack, the breadcrumb labels and the view +
search + level entry filter. The numeric constants mirror the values used by
``ui.py`` so the pure contract stays aligned with the real frontend.
"""
from __future__ import annotations

from dataclasses import dataclass

MIN_WINDOW_WIDTH = 400
MIN_WINDOW_HEIGHT_WIDE = 610
MIN_WINDOW_HEIGHT_NARROW = 720
MAX_WINDOW_WIDTH = 1600
MAX_WINDOW_HEIGHT = 900
INITIAL_HEIGHT_FLOOR = 620
NARROW_THRESHOLD = 650  # window width < 650 -> two filter-button columns
WIDE_COLUMNS = 4
NARROW_COLUMNS = 2
MAX_PAGE_ROWS = 12
MIN_TOUCH_CONTROL = 56  # inputs and buttons are at least 56 logical pixels high
SEARCH_BAR_HEIGHT = 56
CARD_HEIGHT_SWITCH = 195
CARD_HEIGHT_VALUE = 270
BREADCRUMB_ROW_HEIGHT = 56  # interactive group-level row (back + level segments)

# Top-down window rows; cards occupies the remainder between the fixed rows
# before it and the navigation row after it (mirrors the TrainerWindow pack
# order: header, status, toolbar, search, cards, nav). Inside a group level
# the interactive breadcrumb row is inserted between "search" and "cards".
BEFORE_CARDS_ROWS = ("header", "status", "toolbar", "search")
AFTER_CARDS_ROWS = ("nav",)
ROW_HEIGHTS = {"header": 56, "status": 36, "toolbar": 56, "search": SEARCH_BAR_HEIGHT, "nav": 56}
ROW_HEIGHTS_IN_GROUP = dict(ROW_HEIGHTS, breadcrumb=BREADCRUMB_ROW_HEIGHT)
# Rows that carry inputs or buttons and therefore meet the 56-px touch minimum.
TOUCH_ROWS = frozenset({"header", "toolbar", "search", "nav", "breadcrumb"})
VIEWS = ("Switches", "On / Saved", "Values", "All")


def _before_cards(in_group: bool) -> tuple[str, ...]:
    """Fixed rows above the card list for the current navigation level.

    The interactive breadcrumb row sits directly above the cards, after the
    search field, and only while a group level is active.
    """
    if not in_group:
        return BEFORE_CARDS_ROWS
    return BEFORE_CARDS_ROWS + ("breadcrumb",)


def _row_heights(in_group: bool) -> dict:
    return ROW_HEIGHTS if not in_group else ROW_HEIGHTS_IN_GROUP


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


def initial_window_size(screen_width: int, screen_height: int) -> tuple[int, int]:
    """Initial trainer window size from the screen, clamped to the contract."""
    if screen_width <= 0 or screen_height <= 0:
        raise LayoutError("Screen dimensions must be positive")
    width = min(MAX_WINDOW_WIDTH, max(MIN_WINDOW_WIDTH, screen_width - 100))
    height = min(MAX_WINDOW_HEIGHT, max(INITIAL_HEIGHT_FLOOR, screen_height - 100))
    return width, height


def window_columns(width: int) -> int:
    """Filter-button grid: two columns below the narrow threshold, else four."""
    if width < 0:
        raise LayoutError("Width must be nonnegative")
    return NARROW_COLUMNS if width < NARROW_THRESHOLD else WIDE_COLUMNS


def min_window_size(width: int) -> tuple[int, int]:
    """Minimum allowed window size for the column mode of the given width."""
    if width < MIN_WINDOW_WIDTH:
        raise LayoutError("Width is below the hard minimum 400")
    return MIN_WINDOW_WIDTH, (MIN_WINDOW_HEIGHT_NARROW if width < NARROW_THRESHOLD else MIN_WINDOW_HEIGHT_WIDE)


def card_height(view: str) -> int:
    _check_view(view)
    return CARD_HEIGHT_VALUE if view in {"Values", "All"} else CARD_HEIGHT_SWITCH


def cards_area_height(window_height: int, in_group: bool = False) -> int:
    """Height left for the card list after all fixed rows.

    Inside a group level the interactive breadcrumb row (56 px) sits between
    the search field and the cards, so the cards area shrinks by exactly
    ``BREADCRUMB_ROW_HEIGHT``. The root-level row model is unchanged.
    """
    if window_height < 0:
        raise LayoutError("Window height must be nonnegative")
    heights = _row_heights(in_group)
    return window_height - sum(heights.values())


def window_rows(window_height: int, in_group: bool = False) -> list[WindowRow]:
    """Stacked, non-overlapping window rows; cards take the remainder before nav.

    ``in_group`` inserts the interactive breadcrumb row between "search" and
    "cards"; the root-level model (``in_group=False``) is byte-identical to
    the original contract.
    """
    if window_height < 0:
        raise LayoutError("Window height must be nonnegative")
    heights = _row_heights(in_group)
    rows: list[WindowRow] = []
    top = 0
    for name in _before_cards(in_group):
        height = heights[name]
        rows.append(WindowRow(name, top, height))
        top += height
    after_total = sum(ROW_HEIGHTS[name] for name in AFTER_CARDS_ROWS)
    cards = WindowRow("cards", top, window_height - top - after_total)
    rows.append(cards)
    top += cards.height
    for name in AFTER_CARDS_ROWS:
        height = ROW_HEIGHTS[name]
        rows.append(WindowRow(name, top, height))
        top += height
    return rows


def page_size_for_cards(cards_height: int, view: str) -> int:
    """Visible rows per page: at least one, at most MAX_PAGE_ROWS."""
    _check_view(view)
    if cards_height < 0:
        raise LayoutError("Cards height must be nonnegative")
    return max(1, min(MAX_PAGE_ROWS, cards_height // card_height(view)))


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
                      in_group: bool = False) -> list[str]:
    """All contract violations of one window size, empty when the layout fits.

    Checks: hard minimums, the 56-px touch minimum on interactive rows, at
    least one full card row, and that no two rows overlap or leave the window.
    With ``in_group=True`` the breadcrumb row participates in every check.
    """
    _check_view(view)
    if window_width < 0 or window_height < 0:
        raise LayoutError("Window dimensions must be nonnegative")
    violations: list[str] = []
    min_width, min_height = (MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT_NARROW) \
        if window_width < NARROW_THRESHOLD else (MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT_WIDE)
    if window_width < min_width:
        violations.append(f"window width {window_width} below minimum {min_width}")
    if window_height < min_height:
        violations.append(f"window height {window_height} below minimum {min_height} for {window_columns(window_width)}-column mode")
    rows = window_rows(window_height, in_group=in_group)
    for row in rows:
        if row.name in TOUCH_ROWS and row.height < MIN_TOUCH_CONTROL:
            violations.append(f"row {row.name} is {row.height}px below the {MIN_TOUCH_CONTROL}px touch minimum")
        if row.bottom > window_height:
            violations.append(f"row {row.name} extends beyond the window ({row.bottom} > {window_height})")
    for left in range(len(rows)):
        for right in range(left + 1, len(rows)):
            a, b = rows[left], rows[right]
            if a.top < b.bottom and b.top < a.bottom:
                violations.append(f"rows {a.name} and {b.name} overlap")
    cards = next(row for row in rows if row.name == "cards")
    if cards.height < card_height(view):
        violations.append(f"cards area ({cards.height}px) fits fewer than one {view} row ({card_height(view)}px)")
    return violations


def page_count(count: int, view: str, window_height: int) -> int:
    """Total page count for one window size and view, clamped navigation target."""
    size = page_size_for_cards(cards_area_height(window_height), view)
    return max(1, (count + size - 1) // size)


# ---------------------------------------------------------------------------
# Staged card state (WP-14, C5)
#
# A supported value record whose symbols are uniquely provided by other
# supported entries carries ``staged`` plan metadata.  While any provider is
# not live the record is *pending*: reads/writes/freeze are refused by the
# engine (a state, not a fault) and the card shows the provider names and
# waits.  Once every provider id is applied the card unlocks automatically
# (the poll loop re-renders on applied-set changes).  Master-toggle records
# (``activation_sets``) are script cards with a set-shaped button.
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
    ordinary script card.  Returns the contract phrase when the heading
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
# Hierarchical group navigation (pure, Tk-free)
#
# A real CE group is a plan entry with kind "heading" that has at least one
# plan entry with matching parent_id. Placeholder value headings (kind
# "heading" derived from unsupported value records) have no children and stay
# ordinary info cards. The window keeps a stack of group ids, root -> current
# level; every navigation resets the page.
# ---------------------------------------------------------------------------


class GroupNavigationError(ValueError):
    """Refused group navigation (not a navigable group, exit at root, bad stack)."""


def root_entries(entries: dict) -> list:
    """Top-level plan entries in plan (dict) order."""
    return [entry for entry in entries.values() if entry["parent_id"] is None]


def level_entries(entries: dict, group_stack: list) -> list:
    """Direct children of the current level, in plan order.

    An empty stack is the root level.
    """
    if not group_stack:
        return root_entries(entries)
    current = group_stack[-1]
    return [entry for entry in entries.values() if entry["parent_id"] == current]


def is_navigable_group(entry: dict, entries: dict) -> bool:
    """A selected heading with at least one plan child is a drillable group."""
    return (entry["kind"] == "heading" and entry["selected"]
            and any(other["parent_id"] == entry["id"] for other in entries.values()))


def enter_group(group_stack: list, entry: dict, entries: dict) -> list:
    """Return the stack with the entry id appended, or refuse visibly."""
    if not is_navigable_group(entry, entries):
        raise GroupNavigationError(f"Not a navigable group: {entry['label']!r}")
    return list(group_stack) + [entry["id"]]


def exit_group(group_stack: list) -> list:
    """Return the stack without its last level, or refuse at the root."""
    if not group_stack:
        raise GroupNavigationError("Already at the root level")
    return list(group_stack)[:-1]


def breadcrumb_labels(entries: dict, group_stack: list) -> list[str]:
    """["Root"] plus the label of every group in the stack, root -> current.

    Refuses ids that are not navigable groups (defensive; the window only
    builds stacks through enter_group/exit_group).
    """
    by_id = {entry["id"]: entry for entry in entries.values()}
    labels = ["Root"]
    for identifier in group_stack:
        entry = by_id.get(identifier)
        if entry is None or not is_navigable_group(entry, entries):
            raise GroupNavigationError(f"Invalid group in breadcrumb stack: {identifier!r}")
        labels.append(entry["label"])
    return labels


def filtered_entries(entries: dict, view: str, needle: str, applied, desired,
                     group_stack: list) -> list:
    """Plan entries visible under one view/search/level combination, plan order.

    An empty needle applies the group level first and then the view filter, so
    a level shows only its direct children. A non-empty needle keeps the search
    a table-wide escape hatch: every entry is a candidate (the ancestor ``path``
    string stays in the match haystack), while the view filter still applies.
    Navigable groups bypass the view's kind filter in the level listing, so
    they stay visible in every view and the user can drill down from any level.
    Search results keep ordinary matching: a group is listed only when it
    matches the needle itself. ``applied``/``desired`` are any key/membership
    containers of entry ids.
    """
    _check_view(view)
    needle = needle.casefold() if needle else ""
    pool = entries.values() if needle else level_entries(entries, group_stack)
    result = []
    for entry in pool:
        identifier = entry["id"]
        supported = entry["supported"]
        if not entry["selected"] and view != "All":
            continue
        # Navigable groups stay visible in every view of the current level so
        # the user can drill down from any filter level.
        if not needle and is_navigable_group(entry, entries):
            result.append(entry)
            continue
        if view == "Switches" and not (supported and entry["kind"] == "script"):
            continue
        if view == "On / Saved" and not (supported and entry["kind"] == "script"
                                         and (identifier in applied or identifier in desired)):
            continue
        if view == "Values" and not (supported and entry["kind"] == "value"):
            continue
        if needle and needle not in f"{entry['label']} {identifier} {entry.get('path', '')}".casefold():
            continue
        result.append(entry)
    return result
