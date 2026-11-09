# CT2Trainer Master Trainer — UI flow (reviewable)

Status: 0.35 (2026-11-09). This document is the reviewable copy of the
in-app "UI flow" dialog (the `ui_flow_text()` function in
`master_ui.py`; keep both aligned when the flow changes). It describes
the complete user flow of the Master Trainer so it can be reviewed and
improved: every control, every mode transition, every keyboard shortcut
and every failure state. The waiting-mode logic itself lives in the
pure orchestrator; this document covers the user-facing wiring.

## The two modes, one window

The Master Trainer is one long-lived window. Two modes share one Tk
root:

- **Waiting mode** — the folder index: what tables exist, which bound
  processes run right now, and what the orchestrator will do about it.
- **Trainer mode** — the exact standalone-trainer row grid, running on
  the same root.

**Trainer-focus mode (0.29, MT-19):** entering the trainer collapses
the whole waiting view. The waiting view is a single container frame;
it is destroyed on trainer entry, so the table list and its chrome no
longer compete for window space with the trainer rows — the trainer
grid owns the full window. Going back rebuilds the waiting view from
scratch (filter, sort, view mode, status filter, pins and recents all
survive — they are window/app state, not widget state).

## 1) Waiting mode

### Header (left to right)

| Control | Action |
| --- | --- |
| Title | `CT2Trainer <version> — Master Trainer` (label only) |
| Filter entry | Live casefolded substring filter over table name AND any bound process name AND — with 0.35, MT-27 — the persisted note text and tags (a table matches when ANY of them matches); the meta line shows `filtered: N/M` while a query is active; persisted (schema 4) |
| `Status: all/ok/attention` | Cycles the live status filter (0.31, MT-23): all rows / only the loadable rows / only the rows the MT-9 gate would refuse right now (changed / missing / unreadable); persisted (schema 6) |
| `View: list/process` | Cycles the display mode: flat list vs. grouped by bound process name; persisted (schema 4) |
| `Sort: name/process/status` | Cycles the sort mode; persisted (schema 4) |
| Project link | Opens the repository page |
| `Load table` | Explicit load: a picker over the full index (works even while the bound process is not running yet — the engine then waits for it) |
| `Folders…` | The folder manager (0.34, MT-26): the indexed table folders in user order (the primary marked with a star); `Add folder…` / `Set primary` / `Remove` / `Close`; every action re-scans the indexed roots, saves the index, restarts the auto-rescan clock and refreshes the view; a failed change lands in the status line (fail-closed) |
| `Rescan` | Re-scans the indexed folders now (same as **F5**) |
| `UI flow` | Opens this flow document as a read-only in-app dialog (0.29, MT-20); a second click lifts the open window instead of duplicating it |
| `Close` | Closes the app (an active trainer session is closed cleanly first) |

### The lines

- **Folder line** — the primary folder; with several indexed folders
  (0.34, MT-26) the total folder count; a scan problem (e.g. a
  missing stored folder) is named inline.
- **Meta line** — table counts across the indexed folders, last scan
  time, state home location, the last loaded table, the attach mode,
  the recent list (`recent: a, b, c (N more)`), the active status
  filter (`status filter: X`, 0.31, MT-23) and the live attention
  count (`attention: N` — how many indexed tables the MT-9 gate would
  refuse right now; shown only when N > 0) and the live
  `analyzing N table(s)` figure (0.32, MT-24 — shown only while the
  background plan analysis has work), and — on non-Windows — the
  permanent MT-7 route hint (attach unavailable; the documented
  Proton-wrapped trainer route).
- **Running now** — which bound processes are visible in the latest
  snapshot, with PIDs.

### The table tree

One row per indexed table (in `process` view: one parent row per
casefolded bound process name, unbound tables last — group rows are
display-only):

| Column | Content |
| --- | --- |
| Table | The relative path (the row label; in a multi-root session the absolute table key — index root + relative path — is the row identity every load path keys off, 0.34, MT-26) |
| Folder | The indexed folder the table came from (0.34, MT-26) |
| Process name(s) | The bound process names, or `(none found)` |
| Status | Live right now (0.31, MT-23): `ok` / `running` (a bound process is up) / `changed` (the file drifted since the last scan — amber row) / `missing` (the file is gone — red row) / `unreadable` (red row); one bounded stat per visible row per render |
| Detail | The running PID(s), the `pinned` marker (0.28, MT-18), the bounded `N blocked` note when the background analysis found blocked records (0.32, MT-24 — appended after the pin marker), or the attention / unreadable reason |
| Entries | Actionable record count (supported script / value records — the real cheat options) from the background plan analysis (0.32, MT-24): `…` while pending, `–` on a named compile failure, the number once analyzed |
| Blocked | Blocked record count from the same analysis (0.32, MT-24): `…` pending, `–` failed, the number once analyzed |
| Size | Indexed file size (compact B/KB/MB) |
| Modified | Local `YYYY-MM-DD HH:MM` |
| Last used | The persisted UTC timestamp from the recent list |
| Note | The persisted per-table organization metadata (0.35, MT-27): the note text truncated to one line (an ellipsis marks a cut) plus the tags in brackets (`note [tag-a, tag-b]`); empty while no note exists |

The tree takes the **initial focus** on build (0.29, MT-20), so arrow
keys and Enter work immediately without a first click.

**Row context menu (right-click):** `Table details` (0.30, MT-22)
leads the menu — a read-only Toplevel with the indexed facts for the
row (table path, folder, size, modified, bound processes, index
status, pin state, last used, running PIDs, content sha) plus the
**on-demand load-gate re-check** — the same `gate_table_for_load`
pass MT-9 runs at load time, named refusal code + displayable
detail — so a table can be inspected and its current loadability
checked before loading it. It also shows the background plan-analysis
result for the table (0.32, MT-24): `pending` while the analysis is
still queued/running, `N entries (M blocked) of T records` + the top
blocked reasons (up to 8, `reason × count`) once analyzed, or
`failed: <reason>` for a named compile refusal — and the per-table
note / tag rows (0.35, MT-27; `none` while the table carries no
organization metadata). Then `Load this
table` (the explicit load path), `Edit note…` (0.35, MT-27 — the
per-table note / tag editor: a small Toplevel with the note (multi-line,
bounded at 500 characters) and a comma-separated tag entry (bounded at
8 tags × 40 characters); the note and tags persist against the
table's *content sha256*, so they survive a rename or a move between
indexed roots while the content is unchanged; a named refusal at save
time is shown in the dialog's own label — the dialog stays open, the
persisted document stays untouched; a table without a content sha is
refused in the status line), and the `Pin to top` / `Unpin`
toggle (0.28, MT-18).
Group rows (process view) are display-only: no context menu.

### Status bar

Left to right: the live status line (waiting for which process, the
last error / tick detail) · `Attach: auto/ask` (the persisted attach
mode) · **`Auto-rescan: on/off`** (the persisted auto-rescan toggle,
0.33; 0.34: it covers every indexed folder — while on, the tick
re-runs the incremental scan of every indexed folder every 30 s so
added / changed / removed tables show up without a manual F5; paused
while a trainer is attached; a manual rescan, a folder add / remove /
set-primary, or the waiting-view rebuild restarts the 30 s clock) · **`Retry load`** (the re-arm; moved
into the status bar in 0.29 — it used to be a separate button below
the status strip, easy to miss) · `Recent: <path>` (one-click
re-load of the most recent table, only when a recent table exists).

### What the poll tick does (visible behavior)

Every second the pure orchestrator decides:

- no bound process running → stays waiting, the line says so;
- exactly one table binds the running process → **auto-loads** that
  table without prompting (the documented default);
- several tables bind the running process → a picker offers all of
  them; "Not now" defers the decision for that exact (name, PID) pair
  until the process exits, and **Retry load** re-arms it;
- a load failure is named in the status line + an error dialog; the
  failed (name, PID) pair is remembered so the loop does not
  hot-retry; Rescan / Retry load re-arm;
- while **Auto-rescan** is on (0.33, the persisted status-bar
  toggle; 0.34: it covers every indexed folder), the tick
  additionally re-runs the incremental scan of every indexed folder
  every 30 s — one stat pass per folder with the manual Rescan's
  `(size, mtime_ns)` + sha256 short-circuit — so added / changed /
  removed tables show up in the list without a manual F5; the pass
  has no status-line flash, it pauses while a trainer is attached,
  and a manual rescan (F5), a folder add / remove / set-primary, or
  the waiting-view rebuild restarts the 30 s clock.

## 2) Loading a table

All load paths run through the same explicit/auto pipeline (named
refusals included — never a crash):

1. **Auto-load** — the poll tick (unique match).
2. **`Load table` header button** — the picker over the full index
   (0.34, MT-26: the list rows are the table keys — the absolute path
   in a multi-root session, the relative path in a single-root one).
3. **Row** — right-click "Load this table", Enter, or double-click.
4. **`Recent: <path>`** — the one-click re-load.

### Attach decision (persisted, MT-11)

- **auto** (default) — no picker ever; several instances attach to the
  smallest PID.
- **ask** — the process picker is shown for every attach, even for a
  single running candidate; the chosen PID pins the session (it
  self-clears once that PID exits, then the ordinary name-based attach
  applies).

### Startup recovery (named, fail-closed)

- **Stale state lock** / **unfinished receipts** — a previous session
  left state behind and its trainer process is verified terminated:
  the trainer offers to recover (archive the old state
  byte-for-byte). Decline → the load fails, the state is preserved.
  Accept → archive and start. If the game it trained is still running,
  the prompt names that (recovery attaches to the live game; already
  applied patches stay, saved toggles re-apply, stale scans show a
  scan error).
- **Live session conflict** — another trainer still owns this table's
  state: the load is refused; close the other trainer first.
- **Non-convergence** — four recovery attempts without a clean start:
  the state folder is preserved for manual recovery.

### Platform gate (MT-7)

On Windows the attach runs through the unchanged native engine path.
On any other platform the gate is fail-closed: the load is refused
with the documented SteamOS/CheatDeck route (the Proton-wrapped
standalone CT2Trainer Windows trainer EXE). The waiting view carries
the route hint permanently.

## 3) Trainer mode

The exact standalone-trainer row grid, now owning the full window
(the waiting list is hidden — MT-19). Row kinds:

- **switch rows** — tap toggles (the whole row is the tap target);
- **value rows** — tap the value area to expand the inline editor;
- **group section headers** — chevron + "n/N on" counter; a group
  toggle pill only where a `parent_activation` exists;
- **info rows** — dim rows for blocked / unselected records.

Header: the standalone trainer header plus, in Master mode only,
`Columns: N` (0.36, MT-21 - cycles the trainer row grid
1 -> 2 -> 3 -> 1; the requested count persists; a narrow window
renders fewer columns than requested, and a section with its
children never splits across columns), `Detach` (release the live
target; in `ask` mode the process picker offers the re-attach
target) and `⬅ Master` (the return below).

## 4) Back to Master / Detach

- **`⬅ Master`** — closes the engine cleanly and rebuilds the waiting
  view; the same process keeps watching the indexed folders. The
  per-table settings sidecar is saved on the way out. An unclean close keeps the
  state journals and shows the cleanup warning.
- **`Detach`** — keeps the trainer window open, releases the live
  target (session state, journals and wishes untouched), and re-
  attaches to a user-chosen process (ask mode) or resumes the
  ordinary wait (auto mode).

## 5) What is remembered (persisted, under the state home)

| Item | Where |
| --- | --- |
| Table folders (the indexed folder list, primary first, capped at 8; ask on first start; 0.34, MT-26) | `master-settings.json` (schema 8+) |
| Trainer grid column count (1 / 2 / 3, default 1; the header "Columns: N" cycle; 0.36, MT-21) | `master-settings.json` (schema 9) |
| Attach mode (auto/ask) | `master-settings.json` (schema 2+) |
| Last explicit table | `master-settings.json` (schema 2+) |
| Recent tables (≤ 10, UTC) | `master-settings.json` (schema 3+) |
| Waiting-view settings (filter / sort / view) | `master-settings.json` (schema 4+) |
| Pinned tables (≤ 25) | `master-settings.json` (schema 5+) |
| Status filter (all / ok / attention) | `master-settings.json` (schema 6+, 0.31 MT-23) |
| Per-table settings sidecar | `settings/<table-sha256>.ct2trainer.json` (keyed by content hash, never the path) |
| Per-table plan analysis (0.32, MT-24) | `table-analysis.json` (schema 1; keyed by table content sha256, LRU-bounded to 1024 entries — a content change re-analyzes, an unchanged table reuses the cached counts) |
| Per-table notes / tags (0.35, MT-27) | `table-notes.json` (schema 1; keyed by table content sha256, LRU-bounded to 1024 entries — a note follows the content identity across renames and roots) |
| Enabled toggles (per table) | the engine state store; only confirmed ON toggles persist |
| Table index (0.34: one checksum-bound root block per indexed folder) | `tables-index.json` (schema 2, checksum-bound) |

A failed enable attempt stays visibly inactive and is never repeated
as a saved wish on the next attach.

## 6) Keyboard map

| Key | Waiting mode | Trainer mode |
| --- | --- | --- |
| `/` | Focus the filter entry (from anywhere) | — (the trainer UI owns the keys) |
| `Esc` | (in the filter) clear the query, focus returns to the list | — |
| `F5` | Re-scan the indexed folders (0.29; 0.34: every indexed folder) | — |
| `↑/↓/←/→`, `PgUp/PgDn` | Navigate the table list (initial focus on build, 0.29) | Grid navigation (trainer UI) |
| `Enter` / `KP_Enter` | Load the selected row (explicit path, named refusals included) | — |
| Double-click | Load the clicked row | Value-row expansion (trainer UI) |
| Right-click | Row context menu: `Table details` (0.30), `Load this table`, `Edit note…` (0.35), `Pin to top` / `Unpin` | Row context menu (trainer UI) |

## 7) Failure states

Every refusal is **named** and lands in the status line (plus a dialog
where the context needs it) — never a crash.

- **Load refused** (MT-10): `not-in-index` / `table-unreadable` /
  `no-process-binding` / `process-snapshot-failed`.
- **Load-time gate** (MT-9): missing file, not a regular file, read
  failure, empty, over the 32 MiB limit, changed since the last scan
  (stale index), not loadable by the tested parser, changed during
  analysis — each a stable named code + displayable detail.
- **Attach refused** (MT-11/MT-7): no candidate process, a snapshot
  failure, or the non-Windows platform gate (the documented route).
- **Startup recovery** (see §2): declined prompt, live conflict, or
  non-convergence — the state is preserved for manual recovery.
- **Trainer view failure** (0.29): if the engine is up but the trainer
  view cannot be built, the engine is closed again, the waiting view
  is restored, and the load fails with the named error — the waiting
  loop and its loop guard stay consistent.
- **Analysis failure** (0.32, MT-24): a table whose plan compile raises
  is recorded as a named, persisted failure (`failed: <ExcType>:
  <message>`, bounded to 200 chars) — the row's Entries / Blocked
  columns show the failed marker and the table is excluded from the
  queue until its content changes. This is a display-side observation
  only: it never blocks, alters, or delays the MT-9 load gate, which
  re-checks the table independently at load time.
