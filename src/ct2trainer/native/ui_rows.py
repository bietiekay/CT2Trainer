"""Pure row model for the compact touch-first trainer row grid (WP-58).

No Tk import: this module turns plan entries plus an engine-state snapshot
into a deterministic, headless-testable list of drawable rows — one compact
row per record instead of the old card-per-record layout:

* switch rows: 64 px (accent bar + pill toggle + 1-line label + status chip),
  the whole row is the tap target;
* value rows: 72 px collapsed, 120 px with the inline editor expanded
  (accent bar + 1-line label + right-aligned live value + frozen badge),
  tapping the value area expands the editor, neighbours shift down and the
  pages are recomputed;
* group section header rows: 48 px (chevron + name + "n/N on" counter + a
  32x40 group toggle pill only for headings with a ``parent_activation``
  flag; plain moHideChildren groups show chevron + counter only; children
  are indented 12 px with a 1 px left rule and nest as sections; default
  state is expanded);
* info rows: 48 px dim rows for blocked records, unselected records
  (visible in the All view) and placeholder headings without children,
  carrying the exact reason as a one-line sublabel.

Everything is deterministic (same width input -> same truncated output,
plan-order row list) so the pure contract is byte-verifiable in tests.
``ui.py`` is a thin ``tk.Canvas`` renderer over this model; the window,
chrome and page constants live in ``ui_layout.py``.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .ui_layout import (ROW_HEIGHT_SECTION, ROW_HEIGHT_SWITCH,
                        ROW_HEIGHT_VALUE, ROW_HEIGHT_VALUE_EXPANDED,
                        ROW_INDENT_STEP, STAGED_PENDING, VIEWS,
                        address_provider_marker, staged_card_state,
                        staged_provider_labels)

ROW_SWITCH = "switch"
ROW_VALUE = "value"
ROW_SECTION = "section"
ROW_INFO = "info"  # dim 48 px row: blocked records, placeholder headings,
                   # unselected rows (D6 "blocked / unselected")

# D6 state names.
STATE_OFF = "off"
STATE_ON = "on"
STATE_ERROR = "error"
STATE_STAGED = "staged"
STATE_BLOCKED = "blocked"

# D6/D10 accent + tint palette (module constants, shared by the renderer).
ACCENT_OFF = "#39415a"
ACCENT_ON = "#1fbf4a"
ACCENT_ERROR = "#e5484d"
ACCENT_STAGED = "#d9a53a"
BADGE_FROZEN = "#4d90e5"
TINT_DEFAULT = "#1a2130"  # same value as ui.BG_CARD
TINT_ACTIVE = "#223044"   # slightly lighter card (ON / error)
TINT_BLOCKED = "#141a24"  # dim row background
TINT_PULSE = "#2c3d58"    # transient 300 ms reaction tint
TEXT_DIM = "#c3ccda"      # same value as ui.FG_DIM

STATE_ACCENT = {
    STATE_OFF: ACCENT_OFF,
    STATE_ON: ACCENT_ON,
    STATE_ERROR: ACCENT_ERROR,
    STATE_STAGED: ACCENT_STAGED,
    STATE_BLOCKED: ACCENT_OFF,
}
STATE_TINT = {
    STATE_OFF: TINT_DEFAULT,
    STATE_ON: TINT_ACTIVE,
    STATE_ERROR: TINT_ACTIVE,
    STATE_STAGED: TINT_DEFAULT,
    STATE_BLOCKED: TINT_BLOCKED,
}

# Row content geometry (logical pixels, row area width = ``width``).
ACCENT_BAR_WIDTH = 4
RIGHT_MARGIN = 8
PILL_GAP_AFTER_BAR = 12
PILL_W, PILL_H = 40, 24
LABEL_GAP_AFTER_PILL = 12
INFO_CHIP = 16
VALUE_AREA_W = 240
SECTION_CHEVRON_W = 16
SECTION_NAME_GAP = 8
GROUP_TOGGLE_W, GROUP_TOGGLE_H = 32, 40
EDITOR_LINE_PAD = 4
BTN_GAP = 8
BTN_APPLY_W, BTN_FREEZE_W = 56, 56
BTN_STEP_W, BTN_RESET_W = 48, 48
ROW_HEIGHT_INFO = 48

_ELLIPSIS = "…"
_NARROW_CHARS = set("iIljft1.,:;!|()[]")


class RowModelError(ValueError):
    """Refused row-model request (bad view, width, snapshot shape, ...)."""


def _check_width(width: int) -> None:
    if type(width) is not int or width < 320:
        raise RowModelError(
            "Row area width must be an integer of at least 320 px "
            "(the expanded value editor needs the space).")


def _char_weight(char: str) -> float:
    """Deterministic per-character width weight for the label font.

    A bounded approximation of Segoe UI 12 glyph advance (not pixel
    perfect; the contract is that the same input always yields the same
    truncation, which the fixed table guarantees).
    """
    if char == " ":
        return 0.30
    if char in _NARROW_CHARS:
        return 0.35
    if char.isdigit():
        return 0.55
    if char.isupper():
        return 0.68
    if char.islower():
        return 0.52
    return 0.60


def text_width(text: str, size: int = 12) -> int:
    """Deterministic pixel width of ``text`` in a font of ``size`` pt.

    The weight table is scaled linearly by the font size, so the same
    (text, size) pair always produces the same width.
    """
    if not isinstance(text, str):
        raise RowModelError("text width needs a string")
    if type(size) is not int or size < 1:
        raise RowModelError("font size must be a positive integer")
    return int(round(sum(_char_weight(char) for char in text) * size))


def truncate_label(text: str, max_width: int, size: int = 12) -> str:
    """One-line label, ellipsized to ``max_width`` (deterministic).

    Whitespace runs (including newlines) collapse to single spaces.  The
    result is the longest prefix whose width plus the ellipsis fits; if
    even the ellipsis alone does not fit the result is the empty string
    (the Info dialog always carries the full label).
    """
    if not isinstance(text, str):
        raise RowModelError("label must be a string")
    if type(max_width) is not int or max_width < 0:
        raise RowModelError("label width must be a nonnegative integer")
    normalized = " ".join(text.split())
    if text_width(normalized, size) <= max_width:
        return normalized
    budget = max_width - text_width(_ELLIPSIS, size)
    if budget <= 0:
        return ""
    prefix = ""
    for char in normalized:
        if text_width(prefix + char, size) > budget:
            break
        prefix += char
    return prefix.rstrip() + _ELLIPSIS


@dataclass(frozen=True)
class RowRect:
    """Axis-aligned hit/test rectangle in row-area coordinates.

    ``y`` is measured from the top of the row area (the same coordinate
    space as ``Row.y``); the renderer subtracts the first row's y of the
    visible page before drawing.
    """
    x: int
    y: int
    w: int
    h: int

    def contains(self, px: int, py: int) -> bool:
        if type(px) is not int or type(py) is not int:
            raise RowModelError("hit tests use integer coordinates")
        return self.x <= px < self.x + self.w and self.y <= py < self.y + self.h


@dataclass(frozen=True)
class EditorRects:
    """Hit rectangles of the expanded value row's inline editor (D4)."""
    input: RowRect
    apply: RowRect
    freeze: RowRect
    plus: RowRect
    minus: RowRect
    reset: RowRect


@dataclass(frozen=True)
class RowSnapshot:
    """Engine-state snapshot the row model renders (D6, no Tk).

    ``applied``/``desired``/``frozen`` are the engine's live sets (keys),
    ``errors`` the per-record last-action refusals, ``value_applied`` the
    ids whose value was written successfully in this session (a value row
    is "on" then, and keeps the badge while frozen), ``parent_active``
    the flagged group headings whose cascade the engine reports active
    (``engine.parent_query``), ``pulsing``/``confirmed`` the transient
    reaction sets (300 ms pulse, 2 s "OK" chip) and ``disconnected`` the
    pre-attach state (switch rows then carry the auto-on wish).
    """
    applied: frozenset = field(default_factory=frozenset)
    desired: frozenset = field(default_factory=frozenset)
    frozen: frozenset = field(default_factory=frozenset)
    errors: dict = field(default_factory=dict)
    value_applied: frozenset = field(default_factory=frozenset)
    parent_active: frozenset = field(default_factory=frozenset)
    pulsing: frozenset = field(default_factory=frozenset)
    confirmed: frozenset = field(default_factory=frozenset)
    disconnected: bool = False

    def __post_init__(self) -> None:
        for name in ("applied", "desired", "frozen", "value_applied",
                     "parent_active", "pulsing", "confirmed"):
            value = getattr(self, name)
            if type(value) is not frozenset or not all(type(v) is int for v in value):
                raise RowModelError(
                    f"snapshot field {name!r} must be a frozenset of entry ids")
        if not isinstance(self.errors, dict) or not all(
                type(k) is int and isinstance(v, str) for k, v in self.errors.items()):
            raise RowModelError("snapshot errors must map entry ids to text")
        if type(self.disconnected) is not bool:
            raise RowModelError("snapshot disconnected must be a boolean")


@dataclass(frozen=True)
class Row:
    """One drawable row of the row grid (all geometry in row-area px).

    ``kind`` is switch / value / section.  ``y`` is the cumulative offset
    from the top of the row area over the whole (unpaged) row list; the
    renderer offsets rows of the visible page by the first row's y.
    Sections carry ``chevron``/``counter``/``group_toggle`` (flagged
    headings only); value rows carry ``value_text``/``frozen_badge`` and,
    while the editor is expanded, ``editor`` rectangles.  ``hit`` always
    covers the whole row; the optional sub-rects are the finer tap targets
    (info chip, group toggle, value area, editor controls).
    """
    kind: str
    entry_id: int
    y: int
    height: int
    indent: int
    state: str
    accent: str
    tint: str
    label: str
    hit: RowRect
    sublabel: str = ""
    chip: str = ""
    value_text: str = ""
    counter: str = ""
    pill: "RowRect | None" = None
    pill_on: bool = False
    chevron: "RowRect | None" = None
    frozen_badge: bool = False
    error_dot: bool = False
    pulsing: bool = False
    confirmed: bool = False
    expanded: bool = False
    group: bool = False
    group_toggle: bool = False
    info_hit: "RowRect | None" = None
    group_toggle_hit: "RowRect | None" = None
    value_area_hit: "RowRect | None" = None
    editor: "EditorRects | None" = None


def filter_entries(entries: dict, view: str, needle: str,
                   applied, desired) -> list:
    """Candidate entries for one view + search, in plan order.

    Views: ``Switches`` (selected supported scripts), ``On`` (those among
    them the engine has applied), ``Saved`` (those carrying a saved wish),
    ``Values`` (selected supported value records), ``Scripts`` (every
    script record — blocked or unselected ones included, headings and
    values hidden; the row model still renders the group sections around
    them) and ``All`` (every record, blocked ones included with their
    reason).  A non-empty search is a table-wide escape hatch over
    label/id/ancestor path (casefolded); the view filter still applies to
    the candidates.
    """
    if view not in VIEWS:
        raise RowModelError(f"Unknown view {view!r}; expected one of {VIEWS}")
    if not isinstance(entries, dict):
        raise RowModelError("entries must be the plan entry dict")
    if not isinstance(needle, str):
        raise RowModelError("search needle must be a string")
    needle_cf = needle.casefold() if needle else ""
    result = []
    for entry in entries.values():
        if not isinstance(entry, dict) or "id" not in entry:
            raise RowModelError("plan entries need an id field")
        if not entry["selected"] and view not in ("All", "Scripts"):
            continue
        if view == "Switches" and not (entry["supported"] and entry["kind"] == "script"):
            continue
        if view == "Scripts" and entry["kind"] != "script":
            continue
        if view == "On" and not (entry["supported"] and entry["kind"] == "script"
                                 and entry["id"] in applied):
            continue
        if view == "Saved" and not (entry["supported"] and entry["kind"] == "script"
                                    and entry["id"] in desired):
            continue
        if view == "Values" and not (entry["supported"] and entry["kind"] == "value"):
            continue
        if needle_cf:
            haystack = f"{entry['label']} {entry['id']} {entry.get('path', '')}".casefold()
            if needle_cf not in haystack:
                continue
        result.append(entry)
    return result


def _record_state(entry: dict, row_kind: str, snapshot: RowSnapshot) -> str:
    if not (entry["selected"] and entry["supported"]):
        return STATE_BLOCKED
    if entry["id"] in snapshot.errors:
        return STATE_ERROR
    if staged_card_state(entry, snapshot.applied) == STAGED_PENDING:
        return STATE_STAGED
    if row_kind == ROW_VALUE:
        # A value row is "on" while its value was written successfully in
        # this session; freezing it keeps the badge (D6), not the accent.
        return STATE_ON if entry["id"] in snapshot.value_applied else STATE_OFF
    return STATE_ON if entry["id"] in snapshot.applied else STATE_OFF


def _switch_chip(entry: dict) -> str:
    if entry.get("one_shot"):
        return "one-shot"
    if entry.get("activation_sets") is not None:
        return "master"
    return ""


def _value_chip(entry: dict) -> str:
    return entry.get("variable_type") or "value"


def _switch_sublabel(entry: dict, state: str, snapshot: RowSnapshot) -> str:
    if state == STATE_BLOCKED:
        return entry.get("reason") or "Not included in this trainer"
    if state == STATE_STAGED:
        providers = ", ".join(staged_provider_labels(entry)) or "unknown provider"
        return "unlocks when active: " + providers
    if state == STATE_OFF and snapshot.disconnected and entry["id"] in snapshot.desired:
        return "auto-on for next game launch"
    return ""


def _section_counter(entries: dict, children_of: dict, heading_id: int,
                     applied) -> str:
    """'n/N on' over the subtree's selected supported script records.

    Falls back to a plain record count for subtrees without switches;
    empty when the subtree holds no record rows at all.
    """
    on = total = records = 0
    stack = [heading_id]
    seen = set()
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        for child in children_of.get(current, ()):
            entry = entries[child]
            if entry["kind"] == "heading":
                stack.append(child)
                continue
            if entry["kind"] == "script" and entry["selected"] and entry["supported"]:
                total += 1
                if child in applied:
                    on += 1
            else:
                records += 1
    if total:
        return f"{on}/{total} on"
    if records == 1:
        return "1 record"
    if records:
        return f"{records} records"
    return ""


def build_rows(entries: dict, view: str, search: str, snapshot: RowSnapshot,
               width: int, *, expanded_values=frozenset(),
               collapsed_sections=frozenset(), values: dict | None = None) -> list:
    """The full, unpaged row list for one view/search/state combination.

    Plan order is the row order; group headings with children render as
    48 px section header rows (default expanded; a heading in
    ``collapsed_sections`` hides its direct subtree), actionable scripts
    and values render as switch/value rows, and everything else (blocked
    or unselected records, placeholder headings without children) renders
    as a dim 48 px info row with the exact reason as sublabel.  Value ids
    in ``expanded_values`` render at the 120 px editor height with their
    inline editor rectangles; ``values`` maps value ids to their current
    display text (the renderer feeds it from ``engine.read_value``).
    """
    _check_width(width)
    if not isinstance(expanded_values, frozenset):
        raise RowModelError("expanded_values must be a frozenset of ids")
    if not isinstance(collapsed_sections, frozenset):
        raise RowModelError("collapsed_sections must be a frozenset of ids")
    if values is None:
        values = {}
    if not isinstance(values, dict):
        raise RowModelError("values must map entry ids to display text")

    visible = {entry["id"] for entry in
               filter_entries(entries, view, search, snapshot.applied, snapshot.desired)}
    children_of: dict = {}
    for entry in entries.values():
        if not isinstance(entry, dict):
            raise RowModelError("plan entries must be dicts")
        children_of.setdefault(entry.get("parent_id"), []).append(entry["id"])
    # CE display parity (field fix 2026-10-30, South of Midnight): entries
    # flagged moAlwaysHideChildren never render as rows; their whole subtree
    # is suppressed in every view. Presentation only - the engine keeps
    # activating them through the parent cascade.
    hidden: set = set()
    for entry in entries.values():
        if entry.get("hidden_children") is True:
            subtree = _subtree_ids(children_of, entry["id"])
            subtree.discard(entry["id"])
            hidden.update(subtree)
    if hidden:
        visible -= hidden

    rows: list[Row] = []
    y = 0

    def emit_section(entry: dict, indent: int, expanded: bool):
        nonlocal y
        has_toggle = entry.get("parent_activation") is not None
        on = entry["id"] in snapshot.parent_active
        counter_right = width - GROUP_TOGGLE_W - RIGHT_MARGIN - SECTION_NAME_GAP \
            if has_toggle else width - RIGHT_MARGIN
        # The section name starts after the 4 px accent bar + 12 px gap
        # (16 + indent), the 16 px chevron and an 8 px gap, i.e. at
        # 40 + indent; the sublabel repeats that origin one line down.
        name_x = 16 + indent + SECTION_CHEVRON_W + SECTION_NAME_GAP
        name_max = counter_right - name_x
        sublabel_max = counter_right - name_x
        row = Row(
            kind=ROW_SECTION, entry_id=entry["id"], y=y, height=ROW_HEIGHT_SECTION,
            indent=indent,
            state=STATE_ON if on else STATE_OFF,
            accent=ACCENT_ON if on else ACCENT_OFF, tint=TINT_DEFAULT,
            label=truncate_label(entry["label"], max(0, name_max), size=13),
            sublabel=truncate_label(address_provider_marker(entry),
                                    max(0, sublabel_max), size=11),
            counter=_section_counter(entries, children_of, entry["id"], snapshot.applied),
            expanded=expanded, group=True, group_toggle=has_toggle,
            chevron=RowRect(16 + indent, y + 14, SECTION_CHEVRON_W, 20),
            group_toggle_hit=(RowRect(width - RIGHT_MARGIN - GROUP_TOGGLE_W,
                                      y + 4, GROUP_TOGGLE_W, GROUP_TOGGLE_H)
                              if has_toggle else None),
            hit=RowRect(0, y, width, ROW_HEIGHT_SECTION),
        )
        rows.append(row)
        y += ROW_HEIGHT_SECTION

    def emit_record(entry: dict, indent: int):
        nonlocal y
        identifier = entry["id"]
        state = _record_state(entry, ROW_VALUE if entry["kind"] == "value" else ROW_SWITCH,
                              snapshot)
        pulsing = identifier in snapshot.pulsing
        confirmed = identifier in snapshot.confirmed
        tint = TINT_PULSE if pulsing else STATE_TINT[state]
        if entry["kind"] == "value":
            height = ROW_HEIGHT_VALUE_EXPANDED if identifier in expanded_values else ROW_HEIGHT_VALUE
            # Label: from x=16+indent (accent bar + gap) to the value area
            # (W-240) with a 12 px gap.
            label_x = ACCENT_BAR_WIDTH + PILL_GAP_AFTER_BAR + indent
            label_max = (width - VALUE_AREA_W) - 12 - label_x
            value_rect = RowRect(width - RIGHT_MARGIN - VALUE_AREA_W, y, VALUE_AREA_W, height)
            info = RowRect(width - RIGHT_MARGIN - INFO_CHIP, y + 28, INFO_CHIP, INFO_CHIP)
            editor = None
            if identifier in expanded_values:
                # line 2 of the expanded row: input + Apply + Freeze + + - + Reset
                reset_x = width - RIGHT_MARGIN - BTN_RESET_W
                minus_x = reset_x - BTN_GAP - BTN_STEP_W
                plus_x = minus_x - BTN_GAP - BTN_STEP_W
                freeze_x = plus_x - BTN_GAP - BTN_FREEZE_W
                apply_x = freeze_x - BTN_GAP - BTN_APPLY_W
                input_x = RIGHT_MARGIN + indent
                editor = EditorRects(
                    input=RowRect(input_x, y + ROW_HEIGHT_VALUE + EDITOR_LINE_PAD,
                                  apply_x - BTN_GAP - input_x,
                                  ROW_HEIGHT_VALUE_EXPANDED - ROW_HEIGHT_VALUE - 2 * EDITOR_LINE_PAD),
                    apply=RowRect(apply_x, y + ROW_HEIGHT_VALUE + EDITOR_LINE_PAD,
                                  BTN_APPLY_W,
                                  ROW_HEIGHT_VALUE_EXPANDED - ROW_HEIGHT_VALUE - 2 * EDITOR_LINE_PAD),
                    freeze=RowRect(freeze_x, y + ROW_HEIGHT_VALUE + EDITOR_LINE_PAD,
                                   BTN_FREEZE_W,
                                   ROW_HEIGHT_VALUE_EXPANDED - ROW_HEIGHT_VALUE - 2 * EDITOR_LINE_PAD),
                    plus=RowRect(plus_x, y + ROW_HEIGHT_VALUE + EDITOR_LINE_PAD,
                                 BTN_STEP_W,
                                 ROW_HEIGHT_VALUE_EXPANDED - ROW_HEIGHT_VALUE - 2 * EDITOR_LINE_PAD),
                    minus=RowRect(minus_x, y + ROW_HEIGHT_VALUE + EDITOR_LINE_PAD,
                                  BTN_STEP_W,
                                  ROW_HEIGHT_VALUE_EXPANDED - ROW_HEIGHT_VALUE - 2 * EDITOR_LINE_PAD),
                    reset=RowRect(reset_x, y + ROW_HEIGHT_VALUE + EDITOR_LINE_PAD,
                                  BTN_RESET_W,
                                  ROW_HEIGHT_VALUE_EXPANDED - ROW_HEIGHT_VALUE - 2 * EDITOR_LINE_PAD),
                )
            rows.append(Row(
                kind=ROW_VALUE, entry_id=identifier, y=y, height=height, indent=indent,
                state=state, accent=STATE_ACCENT[state], tint=tint,
                label=truncate_label(entry["label"], max(0, label_max), size=12),
                sublabel=truncate_label(_switch_sublabel(entry, state, snapshot),
                                        max(0, label_max), size=11) if state in (STATE_BLOCKED, STATE_STAGED) else "",
                chip=_value_chip(entry) if state != STATE_BLOCKED else "",
                value_text=str(values.get(identifier, "")),
                frozen_badge=identifier in snapshot.frozen and state != STATE_BLOCKED,
                error_dot=state == STATE_ERROR,
                pulsing=pulsing, confirmed=confirmed,
                expanded=identifier in expanded_values,
                value_area_hit=value_rect,
                info_hit=info,
                editor=editor,
                hit=RowRect(0, y, width, height),
            ))
            y += height
            return
        # switch row
        pill = RowRect(ACCENT_BAR_WIDTH + PILL_GAP_AFTER_BAR + indent, y + 20, PILL_W, PILL_H)
        # Label: from pill end (56+i) + 12 px gap to the status-chip right edge
        # (W-44); right-side zones: chip text, error dot (W-36..W-28),
        # info chip (W-24..W-8).
        label_max = (width - 44) - 12 - (ACCENT_BAR_WIDTH + PILL_GAP_AFTER_BAR + PILL_W + LABEL_GAP_AFTER_PILL + indent)
        rows.append(Row(
            kind=ROW_SWITCH, entry_id=identifier, y=y, height=ROW_HEIGHT_SWITCH,
            indent=indent, state=state, accent=STATE_ACCENT[state], tint=tint,
            label=truncate_label(entry["label"], max(0, label_max), size=12),
            sublabel=truncate_label(_switch_sublabel(entry, state, snapshot),
                                    max(0, label_max), size=11),
            chip=_switch_chip(entry) if state != STATE_BLOCKED else "",
            pill=pill,
            pill_on=identifier in snapshot.applied,
            error_dot=state == STATE_ERROR,
            pulsing=pulsing, confirmed=confirmed,
            info_hit=RowRect(width - RIGHT_MARGIN - INFO_CHIP, y + 24, INFO_CHIP, INFO_CHIP),
            hit=RowRect(0, y, width, ROW_HEIGHT_SWITCH),
        ))
        y += ROW_HEIGHT_SWITCH

    def emit_info(entry: dict, indent: int):
        nonlocal y
        identifier = entry["id"]
        # Label: from x=16+i to 8 px left of the info chip (W-24..W-8).
        label_max = (width - INFO_CHIP - RIGHT_MARGIN - 8) - 12 - (ACCENT_BAR_WIDTH + PILL_GAP_AFTER_BAR + indent)
        rows.append(Row(
            kind=ROW_INFO, entry_id=identifier, y=y, height=ROW_HEIGHT_INFO,
            indent=indent, state=STATE_BLOCKED, accent=ACCENT_OFF, tint=TINT_BLOCKED,
            label=truncate_label(entry["label"], max(0, label_max), size=12),
            sublabel=truncate_label(entry.get("reason") or "Not included in this trainer",
                                    max(0, label_max), size=11),
            info_hit=RowRect(width - RIGHT_MARGIN - INFO_CHIP, y + 16, INFO_CHIP, INFO_CHIP),
            hit=RowRect(0, y, width, ROW_HEIGHT_INFO),
        ))
        y += ROW_HEIGHT_INFO

    def render_level(parent_id, depth):
        indent = depth * ROW_INDENT_STEP
        for entry in entries.values():
            if entry.get("parent_id") != parent_id:
                continue
            identifier = entry["id"]
            if entry["kind"] == "heading" and children_of.get(identifier):
                subtree_visible = any(
                    descendant in visible
                    for descendant in _subtree_ids(children_of, identifier))
                if identifier not in visible and not subtree_visible:
                    continue
                emit_section(entry, indent, expanded=identifier not in collapsed_sections)
                if identifier not in collapsed_sections:
                    render_level(identifier, depth + 1)
            else:
                if identifier not in visible:
                    continue
                actionable = (entry["kind"] in ("script", "value")
                              and entry["selected"] and entry["supported"])
                if actionable:
                    emit_record(entry, indent)
                else:
                    emit_info(entry, indent)

    render_level(None, 0)
    return rows


def _subtree_ids(children_of: dict, heading_id: int) -> set:
    result = set()
    stack = [heading_id]
    while stack:
        current = stack.pop()
        if current in result:
            continue
        result.add(current)
        stack.extend(children_of.get(current, ()))
    return result


def slice_pages(rows: list, area_height: int) -> list:
    """Page the row list into the visible area (mixed content, floor rule).

    A page accumulates rows while they fit; the first row that no longer
    fits starts the next page (a row taller than the whole area still gets
    its own page so oversized rows stay reachable).  With a non-positive
    area every row lands on its own page, which the pre-layout render uses
    as its one-row fallback.
    """
    if not isinstance(rows, list):
        raise RowModelError("rows must be a list")
    if type(area_height) is not int or area_height < 0:
        raise RowModelError("area height must be a nonnegative integer")
    pages: list[list] = []
    current: list = []
    used = 0
    for row in rows:
        if current and used + row.height > area_height:
            pages.append(current)
            current = []
            used = 0
        current.append(row)
        used += row.height
    if current:
        pages.append(current)
    return pages


def find_row(rows: list, y: int) -> "Row | None":
    """The row whose vertical span contains row-area coordinate ``y``."""
    if type(y) is not int:
        raise RowModelError("row coordinate must be an integer")
    for row in rows:
        if row.y <= y < row.y + row.height:
            return row
    return None


def page_of_entry(pages: list, entry_id: int) -> "int | None":
    """Index of the page containing a row for ``entry_id`` (or None)."""
    if type(entry_id) is not int:
        raise RowModelError("entry id must be an integer")
    for index, page in enumerate(pages):
        if any(row.entry_id == entry_id for row in page):
            return index
    return None
