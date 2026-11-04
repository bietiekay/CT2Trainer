# CT2Trainer Master Trainer — UI flow (reviewable)

Status: 0.29 (2026-11-04). This document is the reviewable copy of the
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
scratch (filter, sort, view mode, pins and recents all survive — they
are window/app state, not widget state).

## 1) Waiting mode

### Header (left to right)

| Control | Action |
| --- | --- |
| Title | `CT2Trainer <version> — Master Trainer` (label only) |
| Filter entry | Live casefolded substring filter over table name AND any bound process name; the meta line shows `filtered: N/M` while a query is active; persisted (schema 4) |
| `View: list/process` | Cycles the display mode: flat list vs. grouped by bound process name; persisted (schema 4) |
| `Sort: name/process/status` | Cycles the sort mode; persisted (schema 4) |
| Project link | Opens the repository page |
| `Load table` | Explicit load: a picker over the full index (works even while the bound process is not running yet — the engine then waits for it) |
| `Change folder…` | Directory picker; switches the indexed root (the previous root's index is dropped) |
| `Rescan` | Re-scans the folder now (same as **F5**) |
| `UI flow` | Opens this flow document as a read-only in-app dialog (0.29, MT-20); a second click lifts the open window instead of duplicating it |
| `Close` | Closes the app (an active trainer session is closed cleanly first) |

### The lines

- **Folder line** — the configured folder; a scan problem is named
  inline.
- **Meta line** — table counts, last scan time, state home location,
  the last loaded table, the attach mode, the recent list (`recent:
  a, b, c (N more)`), and — on non-Windows — the permanent MT-7 route
  hint (attach unavailable; the documented Proton-wrapped trainer
  route).
- **Running now** — which bound processes are visible in the latest
  snapshot, with PIDs.

### The table tree

One row per indexed table (in `process` view: one parent row per
casefolded bound process name, unbound tables last — group rows are
display-only):

| Column | Content |
| --- | --- |
| Table | The relative path — the row identity every load path keys off |
| Process name(s) | The bound process names, or `(none found)` |
| Status | `ok` / `running` (a bound process is up) / `unreadable` |
| Detail | The running PID(s), the `pinned` marker (0.28, MT-18), or the unreadable reason |
| Size | Indexed file size (compact B/KB/MB) |
| Modified | Local `YYYY-MM-DD HH:MM` |
| Last used | The persisted UTC timestamp from the recent list |

The tree takes the **initial focus** on build (0.29, MT-20), so arrow
keys and Enter work immediately without a first click.

### Status bar

Left to right: the live status line (waiting for which process, the
last error / tick detail) · `Attach: auto/ask` (the persisted attach
mode) · **`Retry load`** (the re-arm; moved into the status bar in
0.29 — it used to be a separate button below the status strip, easy to
miss) · `Recent: <path>` (one-click re-load of the most recent table,
only when a recent table exists).

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
  hot-retry; Rescan / Retry load re-arm.

## 2) Loading a table

All load paths run through the same explicit/auto pipeline (named
refusals included — never a crash):

1. **Auto-load** — the poll tick (unique match).
2. **`Load table` header button** — the picker over the full index.
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
`Detach` (release the live target; in `ask` mode the process picker
offers the re-attach target) and `⬅ Master` (the return below).

## 4) Back to Master / Detach

- **`⬅ Master`** — closes the engine cleanly and rebuilds the waiting
  view; the same process keeps watching the folder. The per-table
  settings sidecar is saved on the way out. An unclean close keeps the
  state journals and shows the cleanup warning.
- **`Detach`** — keeps the trainer window open, releases the live
  target (session state, journals and wishes untouched), and re-
  attaches to a user-chosen process (ask mode) or resumes the
  ordinary wait (auto mode).

## 5) What is remembered (persisted, under the state home)

| Item | Where |
| --- | --- |
| Table folder (ask on first start) | `master-settings.json` |
| Attach mode (auto/ask) | `master-settings.json` (schema 2+) |
| Last explicit table | `master-settings.json` (schema 2+) |
| Recent tables (≤ 10, UTC) | `master-settings.json` (schema 3+) |
| Waiting-view settings (filter / sort / view) | `master-settings.json` (schema 4+) |
| Pinned tables (≤ 25) | `master-settings.json` (schema 5+) |
| Per-table settings sidecar | `settings/<table-sha256>.ct2trainer.json` (keyed by content hash, never the path) |
| Enabled toggles (per table) | the engine state store; only confirmed ON toggles persist |
| Table index | `tables-index.json` (checksum-bound) |

A failed enable attempt stays visibly inactive and is never repeated
as a saved wish on the next attach.

## 6) Keyboard map

| Key | Waiting mode | Trainer mode |
| --- | --- | --- |
| `/` | Focus the filter entry (from anywhere) | — (the trainer UI owns the keys) |
| `Esc` | (in the filter) clear the query, focus returns to the list | — |
| `F5` | Re-scan the folder (0.29) | — |
| `↑/↓/←/→`, `PgUp/PgDn` | Navigate the table list (initial focus on build, 0.29) | Grid navigation (trainer UI) |
| `Enter` / `KP_Enter` | Load the selected row (explicit path, named refusals included) | — |
| Double-click | Load the clicked row | Value-row expansion (trainer UI) |
| Right-click | Row context menu: `Load this table`, `Pin to top` / `Unpin` | Row context menu (trainer UI) |

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
