# CT2Trainer Master Trainer — Concept

**Status:** MT-1..MT-5 merged into `main` with the 0.21 release (merge
`9a725a8`, 2026-10-31); MT-6..MT-9 (the full roadmap) with the 0.23
release (2026-11-01); MT-10..MT-12 (user control: explicit table
load, persisted attach mode + process picker, detach / user attach)
on `main` with the 0.25 release (2026-11-02); MT-13..MT-15
(waiting-view usability: search/filter/sort, keyboard flow, recent
tables + Size/Modified/Last-used columns) with the 0.26 release
(2026-11-03); MT-16..MT-17 (persisted waiting-view settings +
process-grouped view) with the 0.27 release (2026-11-03); MT-18
(pinned / favorite tables) with the 0.28 release (2026-11-03);
MT-19..MT-20 (trainer-focus mode: the waiting view collapses on
trainer entry; discoverability: the in-app UI-flow reference, the F5
re-scan, the initial table-list focus, retry-load in the status bar)
with the 0.29 release (2026-11-04); MT-22 (table details + live
load-gate preview) with the 0.30 release (2026-11-04); MT-23 (per-table
live status + color coding + status filter) with the 0.31 release
(2026-11-05); MT-24 (per-table entry count + blocked count, background
plan analysis) with the 0.32 release (2026-11-06); MT-25 (table
folder auto-rescan) with the 0.33 release (2026-11-08); MT-26 (multi-root
table index: several table folders in one Master window, the folder
manager, the absolute table key identity, the persisted folder list)
with the 0.34 release (2026-11-09); MT-27 (per-table notes / tags:
the Note column, the filter match surface, the "Edit note…" editor,
the details-window rows) with the 0.35 release (2026-11-09). Design and
implementation notes; the working plan is [ROADMAP.md](ROADMAP.md) and
the reviewable UI-flow document is [UI.md](UI.md).

## What it is

The Master Trainer is one long-lived trainer window instead of one trainer
per table. The user starts it once, points it at the table folder or
folders (MT-26, 0.34: several table folders can be indexed at once —
sub-folders of every root included) that hold their `.ct` tables, and then
works normally: when a game process starts that a table binds to, the
Master Trainer loads that table automatically, attaches, and switches
into the exact trainer UI of the standalone `trainer.exe`. Toggles the
user enables are persisted per-table and restored on the next load of the
same table. When the user returns to the Master (header button “⬅
Master”), the same window keeps waiting for the next matching process —
a “Forever-Master-Trainer”.

The Master Trainer adds **no new trainer functionality**: every table
feature, activation contract, fail-closed guard and state journal is the
already-tested CT2Trainer engine (`TrainerEngine` + `TrainerWindow`). The
Master Trainer is only the folder index, the process watch and the
auto-load/handoff loop around that existing engine.

## The two modes

### Waiting mode (default)

- Shows the indexed table folders (the primary first, MT-26: the
  folder count and a scan-problem mark when a stored folder is
  missing), a compact metadata line (table counts across the indexed
  folders, bound process names, last scan time, the state home
  location), a live “Running now” line (which bound processes are
  visible in the latest process snapshot, with PIDs), the table index
  (one row per `.ct` table: table name, the **Folder** column (the
  entry's index root), bound process name(s), status, detail, entries
  / blocked counts, indexed size, modified time, last used — rows for
  a running process are marked `running` with its PID(s)) and a live
  status line.
  On non-Windows the metadata line also carries the permanent MT-7 route
  hint (attach unavailable; the documented Proton-wrapped trainer route).
- 0.26 (MT-13/14/15) waiting-view usability: the table list carries a
  live filter (casefolded substring over the table name AND any bound
  process name; the meta line shows `filtered: N/M` while a query is
  active) and a name/process/status sort cycle; the settings persist in the
  master-state document (schema 4, MT-16) and are restored at
  start; the load picker and the auto-load path keep the full
  index. Double-click
  or Enter loads the selected row through the explicit-load path; “/”
  focuses the filter from anywhere in the waiting view, Esc clears it.
  The rolling recent list (master-state schema 3: most recent first,
  capped at ten, UTC timestamps) feeds the meta line, the “Recent:
  <path>” one-click load button and the tree's Last-used column.
- 0.27 (MT-16/17): the waiting-view settings (filter / sort / view
  mode) persist in the master-state document (schema 4) and the tree
  can display the process-grouped view (one parent row per bound
  process name, unbound last; group rows display-only).
- 0.28 (MT-18): the row context menu offers “Pin to top” / “Unpin” —
  the persisted pin set (schema 5) floats the pinned tables to the top
  of the list and of their process group, with the pin marker in the
  detail column.
- 0.29 (MT-19/20): the whole waiting view lives in one container that
  **collapses on trainer entry** — the table list and its chrome no
  longer share the window with the trainer rows (the trainer grid owns
  the full window; the waiting view is rebuilt whole on the way back,
  filter / sort / view / pins / recents included). The header gains
  the read-only **“UI flow”** button (the in-app copy of the
  reviewable [UI.md](UI.md) flow document); **F5** re-scans the
  indexed folders from anywhere in the waiting view; the table
  list takes the
  **initial focus** (arrow keys and Enter work immediately without a
  first click); the “Retry load” re-arm moves into the status bar
  next to the attach toggle and the Recent button.
- 0.30 (MT-22): right-clicking a row offers **“Table details”**
  first — a read-only window with the indexed facts for the table
  (path, folder, size, modified, bound processes, index status, pin,
  last used, running PIDs, content sha) plus the on-demand load-gate
  re-check — the same gate the load path runs (MT-9), named refusal
  code + detail — so a table's current loadability is checked at
  inspection time, not only at load time.
- 0.31 (MT-23): the Status column shows the table's state **right
  now**, not only the cached state of the last scan — one bounded
  `stat` per visible row per render against the index entry: `ok` /
  `running` / `changed` / `missing` / `unreadable` (cheapest fact
  first, live facts outrank the cached scan state — the same order
  the MT-9 gate proves at load time). Rows are color coded (the
  default colors for ok / running, amber for changed, red for
  missing / unreadable), and the persisted **“Status: all / ok /
  attention”** header cycle (schema 6, `view_status`) filters the
  list to the loadable rows or to the rows the gate would refuse
  right now; the meta line carries the live `attention: N` count.
- 0.32 (MT-24): the tree gains the **Entries** / **Blocked**
  columns — the per-table entry counts of the plan compile,
  computed in the background by one daemon thread
  (`analysis_worker.py`) through the tested `compile_table` plan
  path (no Lua execution, no target attach): Entries is the
  actionable count (the supported script / value records — the
  real cheat options), Blocked the blocked-record count. The
  columns show "…" while the analysis is pending and "–" on a
  named compile failure (the details window shows the reason); a
  blocked count > 0 adds the bounded "N blocked" note to the
  detail column (after the pin marker). The results persist in
  `table-analysis.json` (schema 1, under the state home, keyed by
  the table content sha256, LRU-bounded — `table_analysis.py`),
  so a table is re-analyzed only after a content change; only
  tables with a bound process name are analyzed; the worker
  pauses on trainer entry, resumes + re-queues with the waiting
  view, and the meta line shows "analyzing N table(s)".
- 0.33 (MT-25): the **table folder auto-rescan** — while the
  persisted **"Auto-rescan: on"** status-bar toggle is on, the poll
  tick re-runs the incremental scan every 30 s (one stat pass; the
  same `(size, mtime_ns)` + sha256 short-circuit as the manual
  Rescan), so added / changed / removed tables show up in the list
  without a manual F5. The flag persists in `master-settings.json`
  (schema 7, `auto_rescan`, default on); the scan pauses while a
  trainer is attached, is restarted by a manual rescan or a folder
  change, and has zero effect on the load path (the MT-9 gate
  re-checks the table independently at load time).
- 0.34 (MT-26): the **multi-root table index** — the Master indexes
  several table folders at once. The "Folders…" header button opens
  the folder manager (the indexed folders, primary first, the primary
  marked with a star; "Add folder…" / "Set primary" / "Remove" /
  "Close"; every action re-scans the indexed roots, saves the index,
  restarts the auto-rescan clock and refreshes the view). The tree
  gains the **Folder** column (the entry's index root), and the table
  identity in a multi-root session is the **absolute table key**
  (index root + relative path) — picker, details, pins, recents and
  the MT-24 analysis queue are all key-based, so a table is
  unambiguous across roots (the relative path remains the documented
  single-root identity). The folder list persists in
  `master-settings.json` (schema 7 -> 8, `table_folders`, primary
  first, capped at 8) and the tables index document carries one
  checksum-bound root block per indexed folder (schema 1 -> 2); a
  missing stored folder stays visible as a scan problem (fixed
  through the folder manager). Zero load-path effect — the MT-9 gate
  re-checks the table file under its index root independently at load
  time; the auto-rescan and the analysis cover every indexed root.
- 0.35 (MT-27): **per-table notes / tags** — the waiting view gains a
  **Note** column (the persisted note text truncated to one line plus
  the tags in brackets; empty while no note exists). The note and the
  tags are free-form organization metadata, edited from the row
  context menu ("Edit note…" between load and pin) in a small
  Toplevel (the note as a multi-line text bounded at 500 characters,
  the tags as one comma-separated entry bounded at 8 tags × 40
  characters; a named refusal at save time is shown in the dialog's
  own label — the dialog stays open, the persisted document is
  untouched). They persist in `table-notes.json` (schema 1, under the
  state home, **keyed by the table content sha256** — the same
  identity as the MT-24 analysis document, so a note survives a
  rename within a root and follows a content-identical file to
  another root; LRU-bounded to 1024 entries), not in the
  master-state document (no schema bump — the MT-24 sidecar
  precedent). The waiting-view filter also matches the note text and
  every tag (the `note_lookup` extension of the pure
  `filter_tables`; the pre-0.35 behavior is unchanged when no lookup
  is passed), and the MT-22 details window shows the note / tag rows
  (`none` while the table carries no organization metadata). A table
  without a content sha (unreadable / never scanned) cannot carry a
  note: the named refusal lands in the status line, no dialog opens.
  Zero load-path effect — the MT-9 gate re-checks the table
  independently at load time.
- The table folders are taken from the CLI parameter, or from the
  persisted folder list in the state home (`master-settings.json`);
  only a genuinely first start (or no stored folders at all) shows the
  directory picker — “ask on first start”. An explicit folder argument
  wins as the new primary root (the stored folders are indexed behind
  it).
- A 1 s poll tick asks the pure orchestrator for a decision:
  - no bound process running → stays waiting, the line says so;
  - exactly one table binds the running process → **auto-loads** that
    table (the documented default) without prompting;
  - several tables bind the running process → a picker offers all of
    them; “Not now” defers the decision for that exact process
    (name + PID) until it exits, and “Retry load” re-arms it;
  - a load failure (compile refusal, engine start refusal) is named in
    the status line and an error dialog; the failed (name, PID) pair is
    remembered so the loop does not hot-retry while the same process
    lives;
  - before any compile, the load-time gate re-proves the table file
    against its index entry: compatibility (a table this tool can
    actually load — malformed XML, DTD/entity input and unparseable
    legacy binaries are named refusals) and size (non-empty, within the
    32 MiB load limit), plus a drift check — a file that changed since
    the last scan is a named stale refusal (Rescan refreshes the index
    and re-arms). A refused load is visible even though the target
    process was found: no crash, named dialog + status line, no
    hot-retry.

### Trainer mode

The orchestrator hands the compiled plan to `TrainerWindow` on the same
Tk root — the identical row grid, filters, status line, hotkeys, saved
wishes and state journal of the standalone trainer. The visible
differences from the standalone trainer are two extra header buttons:
“⬅ Master”, which:

1. closes the engine cleanly (`engine.close()`; the state and session
   journals are preserved on an unclean close, exactly as the standalone
   trainer does),
2. destroys the trainer widgets,
3. rebuilds the waiting view in the same window and resumes polling;

and — 0.25 (MT-12) — the “Detach” / “Attach” button, which holds the
live target (no auto re-attach; see User control below) and re-attaches
to a user-chosen process in “ask” mode.

— 0.29 (MT-19) — and the trainer-focus mode: on trainer entry the
whole waiting view (header, table list, status bar) is destroyed with
its single container frame, so the trainer rows get the full window
instead of sharing it with the table list. “⬅ Master” rebuilds the
waiting view from scratch (the waiting-view state — filter, sort,
view mode, pins, recents — lives on the window/app and survives the
round trip). If the trainer view cannot be built after the engine is
up, the engine is closed again and the waiting view is restored before
the load fails (the waiting loop and its loop guard stay consistent).

Closing the window (X) in either mode closes the whole app: in trainer
mode it first runs the engine close, so no state is orphaned.

## Folder index (the scan optimization)

Index file: `<state home>/tables-index.json` (state home =
`%LOCALAPPDATA%\CT2Trainer\native\master-trainer` on Windows,
`$XDG_STATE_HOME/CT2Trainer/native/master-trainer` on Linux). The index
lives **outside the table folder** so the user's table directory is never
written to.

MT-26 (0.34): the document is the ordered **set** of per-root indexes
(schema 2) — one checksum-bound root block per indexed table folder,
in user order (the first root is the primary). A table is identified
globally by its **table key**: the absolute path (index root joined
with the relative path, native separators) in a multi-root session,
the relative path in a single-root one (the documented legacy
identity). The merged surface resolves keys casefolded with the
documented relative-path fallback; entries from different roots may
share a relative path (the merged relative-path dict is first-root-
wins and only the compatibility surface — the key is the identity).
Schema-1 single-root documents promote on load. Adding / reordering
roots keeps the stored per-root indexes; removing a root drops its
block; `set_folder` (replace-all) rebuilds the document for the single
new root.

Per table the entry stores: relative path, size, `st_mtime_ns`,
`sha256`, bound process names, and a status (`ok` / `unreadable` with a
named error) — plus the index root it was found under. Reconcile rules (the same
contract per root):

1. Only the folder is listed (`os.walk`, deterministic order); that is the
   only filesystem work on an unchanged tree.
2. An entry whose `(size, mtime_ns)` pair is unchanged is kept as-is —
   the table file is **not re-read**.
3. A changed/new entry is read once; its sha256 is computed. If the
   content hash matches the previous entry, only the fingerprint moves
   (no re-derivation of process names); otherwise the bound process
   names are re-derived from the table source.
4. A removed path drops its entry.
5. Files that fail to read or parse stay visible as `unreadable` rows
   with the named error; they never fail the whole scan and never bind a
   process name.

The bound process names are the distinct EXE tokens the main-branch
`process_detect.find_candidates` heuristic finds in the table source
(legacy-binary CTs are first converted by the tested `read_table` path,
so their module name and AOB module tokens count exactly like XML
tables). A table may bind several names (all are candidates); the
compile-time process name is the one that is actually running, so a
multi-name table simply loads against the live match. A table with no
findable EXE token is listed but never auto-loads (it is visible in the
index row); such tables remain usable through the standalone converter.

The stored document is canonical JSON with a sha256 checksum (same
discipline as the trainer state store): a foreign schema, a different
root path, or a tampered checksum is refused with named reasons instead
of silently falling back.

## Process watch (platform independent)

A small backend abstraction (`process_watch.py`) supplies the read-only
process snapshot; both backends observe only image basenames and PIDs —
no handle rights, no write/terminate paths:

- **Windows:** the Toolhelp32 snapshot (the same read-only contract as
  `ct2trainer.local_processes`).
- **Linux / SteamOS:** the `/proc/<pid>/exe` magic link; the basename is
  the image name. Under Proton the link resolves into the compatibility
  prefix, so the basename is the Windows game EXE name the table binds
  to. Processes whose `exe` link cannot be read are skipped rather than
  matched on a truncated `comm` (a 15-char truncation could produce
  false process-name matches).

Matching is a pure, deterministic function: ordinal case-insensitive for
ASCII names (consistent with the main-branch process finder), casefold
otherwise. The match is only a **load candidate** — the trainer engine
re-proves the exact target identity (PID, creation time, PE header,
architecture, ownership, current bytes) at attach time, so a false
positive can never attach to the wrong process.

Determinism rules (documented, stable across ticks): when several bound
processes run, the first casefold-sorted process name wins; when several
PIDs match one name, the smallest PID wins.

## Per-table configuration persistence

The “items on/off” persistence is the engine's existing state store:
each compiled plan gets a stable `trainer_id` (hash of table sha256 +
process name + selection + architecture), and the state directory
`<state home>/CT2Trainer/native/<trainer_id>/state.json` carries the
confirmed ON-switch wishes, exactly like the standalone trainer. Same
table + same process + same architecture therefore always restores the
same configuration, whether loaded by the standalone trainer or by the
Master Trainer. Only confirmed ON-switches persist; a failed enable
stays visibly inactive and is never re-applied (unchanged engine
contract).

The richer sidecar model (`settings_model.py`, `.ct2trainer.json`:
visible-name drafts, value defaults, hotkeys) is wired in as a per-table
master sidecar (MT-6, done 2026-11-01): `settings_sidecar.py` keys the
sidecar by the table's **content sha256** (never by path) under the state
home at `<state home>/settings/<table_sha256>.ct2trainer.json`. On load
the Master restores the document for the table it is about to open and
shows the named refusal reasons when the stored document is refused
(different table, unknown record ids, ...); on session end (back-to-
Master and window close) the restored document is saved back. A stored
document that cannot be used never silently resets to defaults — the
refusal is visible, and the session continues without it. Applying value
defaults stays a separate explicit engine write (unchanged
`settings_model` contract).

## User control (0.25: MT-10 / MT-11 / MT-12)

User request 2026-11-02 (evaluated against online all-in-one trainers
and the CE 7.5 process picker — the evaluation record is in
ROADMAP.md, “Online feature evaluation”): detach the trainer, choose
which table runs against which process, and remember the
configuration.

- **MT-10 explicit table load.** The “Load table” header button and the
  per-row context menu (“Load this table”) load the table the user
  picked, even while the bound process is not running yet (the plan
  compiles statically; the engine waits for the process to start).
  Named refusals (`not-in-index` / `table-unreadable` /
  `no-process-binding` / `process-snapshot-failed`) land in the status
  line + a named dialog — never a crash. An explicit load bypasses the
  auto-load loop guard (the user asked for this table), but a failed
  load still records the ordinary (name, PID) suppression for the
  auto-load loop. The last explicitly loaded table persists in the
  state home (`master-settings.json`, schema 2) and is visible in the
  metadata line.
- **MT-11 process selection + persisted attach mode.** “auto”
  (default, legacy behavior): no picker ever, the documented
  smallest-PID rule. “ask”: the process picker (one row per running
  candidate, name + PID) is shown for every attach — even a single
  candidate. The “Attach: auto/ask” toggle button persists the mode
  (schema 2; schema-1 documents promote on load with the documented
  defaults). The chosen PID pins the session through the injected
  memory factory; the pin self-clears once that process exits and the
  session falls back to the ordinary name-based attach (smallest PID).
  Cancel semantics depend on the origin: an auto-load pick defers the
  exact (name, PID) pair (Retry load re-arms), a table choice defers
  exactly like “Not now”, an explicit load returns to the waiting
  status, and an attach after a detach stays paused.
- **MT-12 detach / user attach.** The “Detach” header button (Master
  mode only; the standalone trainer header stays byte-identical) holds
  the engine's attach branch: no auto re-attach, session state,
  journals and wishes untouched, the status line says
  “Detached; waiting for user attach”. The button turns into
  “Attach”: in “ask” mode the process picker offers the running
  candidates and the chosen PID is pinned on resume; in “auto” mode
  the ordinary wait simply resumes. A target exit while attached is
  unaffected — the engine keeps waiting as before.

## Waiting-view usability (0.26: MT-13 / MT-14 / MT-15)

With ~151 indexed tables (143 distinct hashes) the waiting view needed
real navigation (evaluation record: ROADMAP.md, “0.26 waiting-view
usability”):

- **MT-13 search / filter / sort.** A header filter entry (live;
  casefolded substring over the table's relative path AND any bound
  process name — a table matches when ANY bound name matches; empty or
  whitespace query = the full list, input order preserved) and a
  “Sort: name/process/status” cycle button. The decision layer is the
  pure `table_filter.py`; the waiting view renders
  `filter_tables(sort_tables(index.tables(), mode), query)`. Row
  identity stays the relative path; the load picker and the auto-load
  path keep using the full index (separate decision surfaces). Both
  values are persisted in the master-state
  document (schema 4, MT-16) and restored at start; they also
  survive the trainer round-trip. Deliberately out (0.26):
  entry-count / blocked-count columns; the group-by-process tree
  (MT-17) and the persisted filter/sort (MT-16) shipped in 0.27.
- **MT-14 keyboard flow.** Double-click, Return and KP_Enter load the
  selected row through the MT-10 explicit-load path (named refusals
  included, no new load logic); arrow keys are built into the Treeview.
  “/” focuses the filter from anywhere in the waiting view (a no-op in
  trainer mode, where the keys belong to the trainer UI); Esc on the
  filter clears it and returns focus to the table list.
- **MT-15 recent tables + metadata columns.** Every successful load
  (auto or explicit; all three load points) records the table in the
  rolling recent list — most recent first, deduplicated by relative
  path, capped at ten, each item the relative path plus the persisted
  UTC timestamp. The list lives in `master-settings.json` (schema 3;
  schema 1 / 2 documents promote on load with `recent_tables=()`, and a
  schema-2 document carrying the field is refused as an unknown field).
  It feeds the meta line (`recent: a, b, c (N more)`), the “Recent:
  <path>” one-click load button in the status frame and the tree's
  Last-used column; the indexed Size (compact B/KB/MB) and Modified
  (local time) join the tree, and the window grows to 1160x600
  (minsize 900x420).
- **MT-16 persisted waiting-view settings (0.27).** The filter
  query, the sort mode and the view mode persist in
  `master-settings.json` (schema 3 → 4: `view_filter` at most
  200 characters, "" = no filter; `view_sort`; `view_mode`).
  Schema-1/2/3 documents promote on load with the documented
  defaults ("" / "name" / "list"); a schema-3 document carrying
  a view_* field is refused as an unknown field. The window
  restores all three at construction; every change (filter
  typing, sort cycle, view cycle, Esc clear) re-persists
  immediately through `MasterApp.set_view_settings` (named
  refusals for unknown modes / an over-long filter).
- **MT-17 process-grouped view (0.27).** The "View: list/process"
  cycle button switches between the flat row list and the
  grouped tree: one parent row per casefolded bound process
  name (a table bound to several names appears once under each
  of them), the tables without a bound name under
  "(no process binding)" last, within-group order = the
  current sort order (filter + sort applied first; the pure
  reshaping is `table_filter.group_tables_by_process`, which
  never adds or drops tables). The parent row carries the group
  label + "N table(s)" count (the tree uses show="headings",
  so the label is values[0]); group rows are display-only —
  double-click, Enter and the row context menu are gated by
  `_is_table_row`, so a group row never loads; the children
  load through the ordinary MT-10 path.
- **MT-18 pinned / favorite tables (0.28).** With ~151 indexed
  tables the ones the user touches daily deserve a permanent place
  at the top: the row context menu offers "Pin to top" / "Unpin",
  the pin set persists in `master-settings.json` (schema 4 → 5:
  `pinned_tables`, relative paths, most recent pin first, capped at
  `PINNED_TABLES_LIMIT` = 25; schema-4 documents promote on load
  with `pinned_tables=[]`, a schema-4 document carrying the field
  is refused as an unknown field). The pure `table_filter.pin_tables`
  reshapes the already-sorted-and-filtered row set (never adds or
  drops tables: pinned rows first in pin order, casefolded
  comparison, the remainder keeps the input order; pin paths not in
  the row set — filtered out or gone — are ignored). A pinned table
  floats to the top of the list view and to the top of its process
  group in the grouped view; the marker lives in the detail column
  ("pinned" / "pinned - PID …"), the first column stays the bare
  relative path (the row identity the load paths key off). Named
  refusals (cap, already pinned, not pinned) land in the status
  line without a state change or a crash.

## CLI

```
ct2trainer native master [FOLDER] [--state-dir DIR] [--debug-log] [--poll-ms N]
```

- `FOLDER` optional; when omitted the stored folder list
  (`master-settings.json` schema 8, `table_folders`) is kept as-is —
  a missing stored folder stays visible as a scan problem (fixed
  through the "Folders…" folder manager), and only a genuinely first
  start (no stored folders at all) shows the directory picker. An
  explicit folder wins as the new primary root; the stored folders are
  indexed behind it (casefold-deduped, each printed as an "Also
  indexing stored folder:" line). A cancelled first start exits 0;
  every stored folder gone shows the picker (the pick is prepended as
  the new primary, a cancel keeps the missing list). An explicit
  missing folder is the documented exit-2 refusal.
- `--state-dir` overrides the state home (tests, portable installs).
- `--debug-log` propagates into the compiled plans, so the trainer
  writes the usual `.ct2debug.log` next to the running trainer.

The frozen entry point `CT2Trainer-Master.exe` (MT-8, part of every
build's portable ZIP) exposes the same surface:
`CT2Trainer-Master.exe [FOLDER] [--state-dir DIR] [--debug-log]
[--poll-ms N]`; a missing/non-directory folder and a non-positive
`--poll-ms` are named exit-2 refusals before any window is created.

## Platform strategy

- The index, matcher, orchestrator and the waiting UI are pure Python +
  Tk and run unchanged on Windows and SteamOS.
- The memory-attach backend is currently Windows-only (as in the rest of
  CT2Trainer). The SteamOS/CheatDeck target route is the documented-route
  surface implemented in MT-7 (done 2026-11-01, `steamdeck_route.py`):
  on a Steam Deck / SteamOS the supported route is the Proton-wrapped
  standalone CT2Trainer Windows trainer EXE (CheatDeck-compatible); the
  Linux/SteamOS Master Trainer runs detection + table index + waiting UI
  only, and every engine-attach attempt is refused fail-closed with the
  named `DeckAttachUnavailableError` (visible in the waiting view and at
  the load attempt). The owned Linux attach backend remains a later work
  item, and the Deck protocol run with exact build hashes
  (`tests/deck/compatibility-matrix.md`) is root/user field work.

## Icon

The Master window and the frozen `CT2Trainer-Master.exe` use the
user-provided `Master_Trainer.ico` / `Master_Trainer.png` (kept in
`src/ct2trainer/assets/`, shipped in the build allowlist; the icon is
passed to the MT-8 PyInstaller freeze).

## Explicit non-goals

- No new CE features or new trainer behavior: the Master is a wrapper
  around the tested engine, not a second trainer implementation.
- No writing into the table folder (index and state live in the state
  home).
- No cross-machine index sync, no hot-reload of a loaded table while
  its trainer session is active (return to the Master, then re-load).
- No global per-feature hotkeys, no auto-update, no concurrent
  multi-table sessions (recorded with the online feature evaluation in
  ROADMAP.md: the engine already supports per-record hotkeys, the
  build policy is offline/hash-verified, and the documented model is
  one active session at a time).
