# Trainer UI/UX Design — Compact Touch-First Row Grid (WP-58)

Status: **designed and implemented in 0.16** (WP-58, integrated into
Wave 4; design dated 2026-10-19, field-fix re-cut
`native-20261020T150115Z-c426fb92`). The shipped UI startup crash fix is
recorded in [`plans/TRACKING.md`](../plans/TRACKING.md). Windows and real
Steam Deck/Proton acceptance remain open, so this design does not change
`runtime_unverified`. The reference-table work is tracked in the
[reference-table roadmap](../plans/reference-table-100-roadmap.md).

Supersedes the current card-based layout in `src/ct2trainer/native/ui.py` /
`ui_layout.py` for the trainer window. Engine contract, plan format, release
build path and dark palette are unchanged.

## 1. Background and goals

User decision 2026-10-19: the switches and selections in the generated
trainer take too much vertical space. The UI is redesigned for the actual
use case:

- **Touchscreen-first** — final acceptance is on a real Steam Deck under
  Proton with touch operation (`tests/deck/compatibility-matrix.md`); the
  UI must be operable with a finger without hover, right-click or precise
  small targets.
- **Many options, fast toggling** — tables with dozens to hundreds of
  toggles; the default view should show as many actionable rows as fit, and
  flipping a switch must be a single tap on a large target.
- **Short names / state at a glance** — one-line labels, immediate visible
  reaction (state color, feedback flash, value display) after every action.

Constraints: the headless engine contract (`toggle` / `set_value` /
`read_value` / `poll`, `applied` / `desired` / `entry_errors` / `frozen` /
`hotkey_warnings` / `table_lua` / `status`) is unchanged — this is a UI-layer
redesign. Tests stay headless (pure row model + mocked window). No new
dependencies; PyInstaller release path unchanged.

## 2. Current state (what is being replaced)

Evidence: `src/ct2trainer/native/ui.py` (684 lines) + `ui_layout.py`
(pure contract), surveyed 2026-10-19.

- One `tk.Frame` **card per record**, vertically stacked, paginated:
  `CARD_HEIGHT_SWITCH = 195`, `CARD_HEIGHT_VALUE = 270` (`ui_layout.py:29-30`)
  → ~4–5 rows per page in a 900 px window.
- Card content: bold 16 px wrapped title label (max 85 chars, 2+ lines),
  Info button, full-width `tk.Button` toggle showing the state
  ("ON" green `#1fbf4a` / "OFF" red `#e5484d`), separate "Current: …" status
  label, staged/pending line.
- Value card: `ttk.Combobox`/`tk.Entry` (`width=10`, Segoe UI 16) + **Apply**
  + **Freeze/Unfreeze** + **▲/▼/Reset** draft row → 270 px per value record.
- Chrome rows at 56 px each (header / toolbar / search / nav / breadcrumb)
  + 36 px status; group drill-down navigation with breadcrumbs replaces the
  list; paging only via PageUp/PageDown/MouseWheel — **no touch drag**, no
  DPI awareness anywhere in `src/`.
- State feedback: re-render on state change or 250 ms poll tick; audio tones
  880/440 Hz; error → modal messagebox; hotkey-conflict and table-Lua banners
  (amber) under the status row.

## 3. New layout (design decisions)

### D1 — Row model (replaces cards)

One compact row per record, one line each:

| Row type | Height | Content |
| --- | ---: | --- |
| Switch row | **64 px** | accent bar + pill toggle + 1-line label + status chip |
| Value row | **72 px** | accent bar + 1-line label + current value + freeze badge (editor expands inline, see D4) |
| Group section header | **48 px** | chevron + group name + "n/N on" counter + (group toggle for flagged groups) |

Page size = floor(cards-area height / row height), mixed content computed per
page from the row model → **≥ 10 switch rows per page** at the 900 px
reference window (vs. ~4 today, ≥ 2.5× density). Row heights keep the touch
minimum: interactive rows ≥ 56 px; chips/buttons ≥ 48 px.

### D2 — Rendering: canvas virtual list + pure row model

- New **pure module `src/ct2trainer/native/ui_rows.py`** (no Tk import):
  computes the row model from plan entries + an engine-state snapshot —
  row type, truncated label, state, accent color, sub-label, editor
  expansion, group section collapse state, hit-area rectangles, page slicing.
  Everything unit-testable headless; deterministic (sorted, casefolded
  where names are involved).
- `ui.py` becomes a **thin canvas renderer** (`tk.Canvas`, full-card area):
  only visible rows drawn; full redraw on state change; row rectangles, text
  items (1-line labels with `-ellipsis`), pill toggle shapes, accent bars,
  status chips. `pack`/`Frame` cards disappear.
- The pure contract in `ui_layout.py` is updated in place (row heights,
  chrome heights, page math, `layout_violations()`); its Tk-free purity and
  doc-contract with `ui.py` stay.

### D3 — Switch row

Layout (left → right): 4 px accent bar (state color, D6) · pill toggle
(40×24 px, 12 px from the accent bar; OFF = dark track `#39415a` + light
knob, ON = green track `#1fbf4a` + white knob; knob position = state) ·
label, one line, Segoe UI 12, ellipsized to the remaining width ·
right-aligned status chip (11 px, `FG_DIM`): for scripts the one-shot marker
or dependency hint, for values the type.

**The entire row is the tap target for toggling** (not just the pill) —
largest practical hit area. The pill is state display, not a separate
control. **Info** = 16×16 "i" chip at the right edge (tap) **or long-press
(400 ms) anywhere on the row** → existing Info dialog (full label, reason,
hotkey, current value — content unchanged).

### D4 — Value row

Collapsed: accent bar · label (1 line) · current value right-aligned
(Consolas 12, live from the 250 ms poll as today) · freeze badge (small
lock square in `#4d90e5` when frozen, else nothing).

**Tap on the value area → inline editor expands** that row to a two-line
editor block (72 → 120 px, neighbors shift down, page recomputed):
line 1 = `ttk.Combobox`/`tk.Entry` (Segoe UI 12, draft `StringVar` as today);
line 2 = **Apply** (≥ 56 px touch) + **Freeze/Unfreeze** + steppers **+/−**
(step from the plan as today) + **Reset**. Draft editing never touches
memory (same as today); Apply → `engine.set_value`; on failure the row gets
the error accent (D6) and the status line shows the reason (no modal
messagebox for expected failures — the existing `action()` error path stays
as the last resort for unexpected exceptions).

### D5 — Group sections (replaces breadcrumb drill-down)

- Every group heading renders as a **section header row**: chevron
  (▸ collapsed / ▾ expanded) + group name (Segoe UI 12 bold, dim) + counter
  "n/N on" + right edge: for headings with `parent_activation` (flagged
  groups) a compact **group toggle** (pill, 32×40 px) that runs the existing
  parent-activation cascade via `engine.toggle(heading_id)`; plain
  `moHideChildren` groups show chevron + counter only (CE parity: no cascade
  flag → no child propagation; see WP-53 hotkey semantics).
- Children render indented 12 px with a 1 px left rule, inline in the same
  flat page. Default state: expanded.
- **Breadcrumb navigation and the "Open group" card are removed**; the
  flat-with-sections view is the only record list view. Deep nesting works
  by nested section headers (same flat page, no drill-down).
- This replaces the `ui_layout.py` row-stack/breadcrumb model —
  `tests/test_native_ui_group_nav.py` is rewritten as the section/collapse
  contract (see §5).

### D6 — State feedback ("Reaktionsdarstellung")

Per-row state is carried by the accent bar + row tint + badge:

| State | Accent | Row tint | Notes |
| --- | --- | --- | --- |
| OFF (active-able, not on) | `#39415a` (neutral) | `BG_CARD` | default |
| ON | `#1fbf4a` (green) | slightly lighter card | pill green |
| Error (last action failed) | `#e5484d` (red) | slightly lighter | red dot at right edge; reason in status line + Info |
| Staged / pending (provider not live) | `#d9a53a` (amber) | `BG_CARD` | sub-label "unlocks when active: …" as today |
| Frozen (value) | value row accent by ON/OFF; badge `#4d90e5` lock | — | |
| Blocked / unselected | dim row, `FG_DIM` text | — | exact `reason` as 1-line sub-label (11 px) |

**Transient reaction:** after every successful toggle / value write the row
pulses (row background to the lighter tint for 300 ms, driven by
`after()`) and a transient "✓" chip shows at the row's right edge for 2 s —
immediate, glanceable feedback. Audio tones (880/440 Hz) and the status line
stay as today. No per-row label text changes beyond the transient chip.

### D7 — Compact chrome

| Row | Height | Content |
| --- | ---: | --- |
| Header | 48 px | trainer title (left, 13 px) · connection dot + target process name (right) |
| Filter/search | 48 px | chips **Switches / On / Saved / Values / All** (≥ 80×48 px each; same row as an inline search field when wide; below 650 px window width the chips fall to a 2×3 grid and search gets its own 48 px row) |
| Status | 32 px | `engine.status` (as today) |
| Banners | 28 px each | hotkey-conflict banner (WP-40) + table-Lua banner (WP-41) — compact amber strips, same strings, stacked |
| Pagination | 48 px | "Page x/y" · ◀ ▶ (56×48 px touch buttons) · ⤒ (top) |

Total fixed chrome ≈ 200 px (vs. ~320 px today) → larger row area at the
same window size; window clamping rules (screen-derived, min 400×610 /
400×720 narrow) stay.

### D8 — Touch input

- Tap: `Button-1` on the canvas → hit-test against row rectangles (row
  model provides the geometry); row = toggle, value area = editor expand,
  chips = their actions.
- Finger drag: `B1-Motion` on the list area with an 80 px drag threshold
  changes the page (same paging as MouseWheel); no free scroll in v1.
- MouseWheel / PageUp / PageDown / Escape bindings stay.
- No hover or right-click path anywhere in the new layout (Deck protocol
  requirement). All interactive targets ≥ 48 px.

### D9 — Short names

Labels render one line, ellipsized to the available width (canvas text
`-ellipsis`). The full label, exact reason and hotkey are always in the Info
dialog (long-press or "i" chip). No abbreviation engine — truncation only,
deterministic and byte-verifiable in the pure row model (same width input →
same truncated output in tests).

### D10 — Visuals

Keep the existing dark high-contrast palette constants in `ui.py`
(`BG`, `BG_CARD`, `ON_BG`, `OFF_BG`, `BANNER_*`, …); new constants only for
the row accent colors (D6) and the pill. Fonts: Segoe UI 12 (labels), 11
(sub-labels/chips), 13 bold (group headers), Consolas 12 (values). No light
mode, no theme file, no settings — the palette stays a set of module
constants.

## 4. Explicitly out of scope

- Engine semantics and plan format: **zero** `engine.py` changes in this
  lane; plans stay byte-identical (UI-only change).
- Startup recovery flows (`run_trainer` dialogs) — unchanged.
- Info dialog content — unchanged (may be restyled to the row palette).
- Converter GUI (`converter.py`) — separate window, untouched.
- DPI awareness (zero today, zero in this redesign — stays a documented open
  Deck item), Proton audio tones (untested as today), light mode,
  multi-window, free-scroll.

## 5. Change surface and tests

| File | Change |
| --- | --- |
| `src/ct2trainer/native/ui_rows.py` | **new** — pure row model (no Tk): row types/heights, label truncation, state→accent mapping, filter application, group section/collapse model, value-editor expansion, hit-area geometry, page slicing |
| `src/ct2trainer/native/ui.py` | canvas list renderer; tap/long-press/drag bindings; pulse via `after()`; inline value editor; compact chrome rows; banners as strips |
| `src/ct2trainer/native/ui_layout.py` | new constants (64/72/48 rows, 48/48/32/48 chrome, chip sizes), page math, `layout_violations()` for the row model; purity contract unchanged |
| `tests/test_native_ui_layout.py` | constants + page math updated to the row grid (e.g. "400×800 shows ≥ 2 value rows", 56 px touch minimum on interactive rows, chrome stacking without overlap) |
| `tests/test_native_ui_group_sections.py` | **replaces** `test_native_ui_group_nav.py` — section header model, collapse/expand, counter, flagged-group toggle vs plain group, nested sections |
| `tests/test_native_ui_rows.py` | **new** — pure row model: truncation (deterministic), state→accent mapping per D6 table, filter behavior (Switches/On/Saved/Values/All), value-editor expand/collapse, hit-area geometry, mixed-page slicing |
| `tests/test_native_ui_tone.py` | unchanged (audio contract untouched) |
| `tests/test_native_ui_recovery_flow.py` | unchanged (mocked window) |
| `tests/test_native_record_hotkeys.py`, `tests/test_native_dynamic_address_provider.py` | unchanged as long as banner/marker strings keep their exact text (design keeps them) |
| `tests/deck/compatibility-matrix.md` | layout description (line ~105) updated to the row grid; D1 run-sheet row stays, touch checklist adapts (tap rows, drag paging, editor expand) |
| `tools/native_build.py` | embedded README wording ("one switch card per record" → compact row grid) |
| `documentation/usage.md`, `documentation/native-runtime.md` | UI description paragraphs |
| `CHANGELOG.md` | at release, by root |

## 6. Acceptance

1. Full suite green (baseline + new/updated tests, zero failures).
2. Density: at the 1600×900 reference window, switch rows per page ≥ 2.5×
   the old layout (≥ 10 rows vs. ~4) — pinned in `test_native_ui_layout.py`.
3. Plan byte-identity: the converter output for all 27 pinned corpus tables
   is unchanged (UI-only lane; verified by root at integration).
4. All engine state fields render with unchanged semantics; no modal dialog
   for expected action failures (row accent + status line instead);
   `messagebox` only for unexpected exceptions and the startup recovery
   flows.
5. Headless testability: no test instantiates a real canvas; `ui_rows.py` is
   pure; `ui.py` stays covered by the existing mocked patterns.
6. Deck D1 acceptance remains OPEN until the hardware run; the matrix is
   updated to describe the new layout so the D1 sheet tests the row grid.

## 7. Open items (root decisions)

- Scroll: page-based drag chosen for v1; free-scroll (row-precise) is a
  possible follow-up, not required.
- Long-press = Info **and** "i" chip (both) — if field tests show the chip
  is sufficient, the long-press can be dropped later.
- DPI awareness remains a separate, explicitly open item (see
  `tests/deck/compatibility-matrix.md`).
