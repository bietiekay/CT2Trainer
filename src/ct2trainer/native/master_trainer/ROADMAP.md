# CT2Trainer Master Trainer — Roadmap & Working Plan

Work packages for the Master Trainer feature (user request 2026-10-30:
one always-running trainer window, folder-scanned table index, automatic
table load on process appearance, per-table toggle persistence, platform
independent for Windows + SteamOS/CheatDeck). All packages reuse the
main-branch libraries; none adds trainer functionality.

## Package states

| ID | Package | State | Exit evidence |
| --- | --- | --- | --- |
| MT-1 | Table folder index (incremental) | done (2026-10-30) | `table_index.py`: deterministic recursive scan, `(size, mtime_ns)` skip contract, sha256 short-circuit, unreadable entries visible with named error, checksum-bound JSON persistence with root/schema/tamper refusal; `tests/test_native_master_index.py`. |
| MT-2 | Cross-platform process watch | done (2026-10-30) | `process_watch.py`: `WindowsProcessLister` (Toolhelp32, read-only), `ProcfsProcessLister` (`/proc/<pid>/exe`, `proc_root` injectable), platform-selected `default_process_lister()` fail-closed, pure deterministic `match_targets`/`names_match`; `tests/test_native_master_process_watch.py`. |
| MT-3 | Orchestrator state machine | done (2026-10-30) | `orchestrator.py`: waiting → choosing → loading → active → waiting; unique-match auto-load, multi-table picker contract, deterministic first-key/lowest-PID rule, fail-closed loop guard (failed + deferred (name, PID) pairs, PID-gone re-arm, explicit retry), snapshot-failure named and non-fatal; `tests/test_native_master_orchestrator.py`. |
| MT-4 | Waiting UI + table picker + trainer handoff | done (2026-10-30) | `master_ui.py`: one Tk root, waiting view (folder, index Treeview, status line, Rescan / Change folder / Retry load), modal picker with per-table rows + “Not now” deferral, handoff into the unchanged `TrainerWindow` (identical row grid) with the new optional “⬅ Master” header button (default-off, byte-identical standalone behavior), clean engine close on return and on window close; stale-state / artifacts / live-conflict startup recovery mirrored from `run_trainer`; `tests/test_native_master_ui.py`. |
| MT-5 | CLI + state-home wiring + icon | done (2026-10-30) | `ct2trainer native master [FOLDER] [--state-dir] [--debug-log] [--poll-ms]`; index persisted under the state home (`tables-index.json`), never inside the table folder; `window_icon_path("master")` for the user-provided `Master_Trainer.ico`; build allowlist updated (`Master_Trainer.ico/.png`, the `master_trainer` subpackage). |
| MT-6 | Per-table settings sidecar wiring | done (2026-11-01) | `settings_sidecar.py`: `MasterSettingsStore` keyed by the table content sha256 (never by path), layout `<state home>/settings/<sha>.ct2trainer.json`; `load_for` returns `(document, [])` / `(None, reasons)` — absent file is normal, `SettingsRejection` reasons pass through displayable, structural `SettingsError` named; `save_for` derives the known-id set from the document and refuses an all-empty draft with the named `nothing to persist`; reuses the tested `SettingsModel` unchanged. UI wiring: restore on load with a visible named refusal (session continues without it), save on close (back-to-Master and window close). The on/off wish persistence itself stays on the engine state store (MT-4). +17 sidecar tests, +6 UI wiring tests. |
| MT-7 | SteamOS / CheatDeck target route | done (2026-11-01, documented-route scope) | `steamdeck_route.py`: `AttachRoute` + `attach_gate` / `require_engine_attach` / `route_text`; Windows -> attach available through the unchanged native engine path; Linux/other -> named `DeckAttachUnavailableError` carrying the documented route (Proton-wrapped standalone CT2Trainer Windows trainer EXE, CheatDeck-compatible; the Linux/SteamOS Master runs detection + table index + waiting UI only; the owned Linux attach backend remains a later work item). UI wiring: the gate runs before any engine creation (a refusal fails the load through the orchestrator's named loop guard); the waiting view shows the route hint permanently on non-Windows. The real Deck protocol run (`tests/deck/compatibility-matrix.md`) with exact build hashes stays root/user field work. +13 route tests, +3 UI wiring tests. |
| MT-8 | Frozen Master entry point | done (2026-11-01) | `tools/native_master.py` frozen to `CT2Trainer-Master.exe` with the user-provided `Master_Trainer.ico` (windowed; lazy `master_ui` import so `--help` and the named exit-2 refusals need no tkinter; CLI mirrors the `master` subcommand). `build()` freezes it after the converter (no `CT2BASE1` marker — templates are converter-only), runs the CE-content `inventory()` scan, adds it to `payload-inventory.json`, the `build.json` outputs and the portable ZIP next to the converter; `source_files()` already admits `tools/native_*.py` by glob; `scripts/Build-Native.ps1` needs no change (its single `build()` call emits the new EXE and ZIP entry). +8 tests; the real PyInstaller freeze is verified at the 0.23 build cut. |
| MT-9 | Load-time table compatibility & size gate | done (2026-11-01) | `table_gate.py`: re-proves one table file against its index entry at the moment the load is requested (auto-load or picker) — missing file / not-a-regular-file / stat-or-read failure / empty / exceeds the 32 MiB load limit (33,554,432 bytes, the bound the parser and the compiler enforce) / changed since the last scan (stale index) / not loadable by the tested `read_table` parser (malformed XML, DTD/entity input, unparseable legacy binary) / changed during analysis — each a stable named code + a displayable detail, cheapest-first, no parser call for a stat-level refusal. The default plan compiler raises the named `TableLoadGateRefusal`, so a load failure is handled gracefully even when the target process was found: no crash, named dialog + status line, the orchestrator's fail-closed loop guard records the exact (name, PID) pair (no hot-retry), Rescan / Retry load re-arm; the stale-scan refusal also keeps the MT-6 sidecar keying (table content sha256) consistent with what the trainer loads. New `tests/test_native_master_table_gate.py` (12), orchestrator gate-refusal loop-guard tests (2), UI wiring tests (4). |
| MT-10 | Explicit table load (user choice) | done (2026-11-02) | “Load table” header button in the waiting view + per-row context menu (“Load this table”): the user chooses which table loads, even while the bound process is not running yet (the plan compiles statically, the engine waits for the process to start). `orchestrator.request_load(relative_path)` resolves one indexed table against the live snapshot into `ExplicitLoadRequest(table, plan_process, candidates, process)`; running bound candidate → the smallest-PID process wins and the plan compiles against that snapshot name; nothing running → the first bound name in casefold order plus a synthetic zero-PID entry. Named `ExplicitLoadRefusal` codes: `not-in-index` / `table-unreadable` / `no-process-binding` / `process-snapshot-failed` — a refused load lands in the status line + a named dialog, never a crash. Unlike the auto-load tick the path bypasses the fail-closed loop guard (the user asked for this table); a later `load()` failure still records the ordinary (name, PID) suppression. The last explicit table persists in the state home (schema 2, `last_table`) and is visible in the meta line. +13 orchestrator tests (`tests/test_native_master_explicit_load.py`), +5 UI flow tests in `tests/test_native_master_ui_mt12.py`. |
| MT-11 | Process selection + persisted attach mode | done (2026-11-02) | `process_picker.py` (pure decision layer): `candidate_processes` (deterministic name-then-PID order over the snapshot), `attach_decision(candidates, mode)` → `attach-direct` / `pick` / `wait`, and `make_pinned_memory_factory(lister, pin)` — the injected factory honors the session pin `{"pid": int\|None}`, self-clears the pin once that PID exits, falls back to the ordinary `ProcessMemory(name)` open (single instance) or the documented smallest-PID multi-instance rule, and re-raises the named refusal when nothing runs. The attach-mode constants live in `master_state` (single source of truth): `auto` (default, legacy behavior — no picker ever; several instances attach to the smallest PID) and `ask` (the process picker is shown for every attach, even a single running candidate). `master-settings.json` schema 2 persists `attach_mode` + `last_table` (schema-1 documents promote on load with the documented defaults `last_table=None`, `attach_mode="auto"`; only schema 2 is writable). UI: the “Attach: auto/ask” toggle button in the status frame persists the choice on toggle; the meta line shows the last loaded table + the mode; auto-load and explicit load both route through `attach_decision`; the picker lists one row per candidate (name + PID); the chosen PID pins the session through the injected memory factory. Cancel semantics per origin: `auto-load` defers the exact (name, PID) pair (Retry load re-arms), `choice` defers the open table choice exactly like “Not now”, `explicit` returns to the waiting status, `attach` stays paused. +16 decision/factory tests (`tests/test_native_master_process_picker.py`), +7 schema-2 tests in `tests/test_native_master_state.py`, +4 UI picker-flow tests in `tests/test_native_master_ui_mt12.py`. |
| MT-12 | Detach / user attach | done (2026-11-02) | Engine hold: `pause_attach()` / `resume_attach()` + the `attach_paused` property; while paused the poll attach branch is gated (status “Detached; waiting for user attach”, no attach attempts; session state, journals and wishes untouched), debug events `attach-paused` / `attach-resumed`, `reattach()` status stays pause-aware, and pausing is refused with a named error while the engine is closed / blocked / busy. UI: the new “Detach” / “Attach” header button exists in Master mode only (the standalone trainer header stays byte-identical; `TrainerWindow` gains the optional `detach_cb` and the poll tick keeps the label in sync). `_detach_or_attach()`: attached → `pause_attach()` + `reattach()`; detached-by-user + `ask` mode + running candidates → the process picker (origin `attach`) → pin the chosen PID + `resume_attach()`; `auto` mode or no candidates → `resume_attach()`; detached-by-target-exit → no-op (the ordinary wait already runs). +5 engine tests (`tests/test_native_attach_pause.py`), +8 UI routing tests in `tests/test_native_master_ui_mt12.py`. |
| MT-13 | Waiting-view search / filter / sort | done (2026-11-03) | `table_filter.py` (pure decision layer, no OS / index / state access): `filter_tables` (empty/whitespace query = the identity, input order preserved; otherwise a casefolded substring over the table's relative path AND any bound process name — a table matches when ANY bound name matches) and `sort_tables` (modes `name` / `process` / `status`; the casefolded relative path is the universal tie-breaker; in `process` mode tables without a bound name sort after the named ones; an unknown mode raises `ValueError` — named refusal, never a silent fallback). The waiting view renders `filter_tables(sort_tables(index.tables(), mode), query)` through `_visible_tables()`; row identity stays the relative path, and the load picker and the auto-load path keep the full index (separate decision surfaces). The filter/sort state is restored from the persisted master-state document at construction and re-persisted on every change (MT-16, schema 4); it also survives the trainer round-trip (the waiting view is rebuilt from it). UI: a header filter entry (live re-render on `<KeyRelease>`; while a query is active the meta line carries `filtered: N/M`) and a “Sort: name/process/status” cycle button. Delivered in 0.27: the group-by-process tree (MT-17) and the persisted filter/sort (MT-16). +17 pure tests (`tests/test_native_master_table_filter.py`), +4 UI filter/sort tests in `tests/test_native_master_ui_mt13.py`. |
| MT-14 | Keyboard flow in the waiting view | done (2026-11-03) | Double-click, Return and KP_Enter load the selected/focused row through the ordinary MT-10 explicit-load path (`_load_selected_table` — named refusals included, no new load logic); arrow keys are built into the Treeview. Root `<KeyPress>/` focuses the filter entry from anywhere in the waiting view (a no-op in trainer mode, where the keys belong to the trainer UI — the handler checks the engine); Esc on the filter entry clears the query and returns focus to the table list. +3 keyboard tests in `tests/test_native_master_ui_mt13.py` (Return loads / is a no-op without a selection, double-click through the real `identify_row` bbox, the “/” focus contract via a `focus_set` spy — Tk focus allocation on an unmapped window is environment-dependent). |
| MT-15 | Recent tables + Size / Modified / Last-used columns | done (2026-11-03) | `master-settings.json` schema 2 → 3: `recent_tables`, most recent first, capped at `RECENT_TABLES_LIMIT` (10), each item `{"path", "at"}` with the persisted UTC timestamp `YYYY-MM-DDTHH:MM:SSZ` (strict format, length-bound); schema-2 and schema-1 documents promote on load with `recent_tables=()`, and a schema-2 document carrying the field is refused as an unknown field (foreign schema, never silently promoted). `MasterApp.remember_recent_table` prepends, dedupes by relative path, caps and re-persists immediately; it is called at all three successful load points (the explicit `_start_load` path, the process-picker `choice` origin, the table-picker `choice`). Waiting view: the meta line shows `recent: a, b, c (N more)` (first 3), the status frame gains the “Recent: <path>” one-click load button (MT-10 path, width 28), and the tree gains the indexed Size (compact B/KB/MB), Modified (local `YYYY-MM-DD HH:MM`) and Last-used (the stored UTC timestamp) columns — the window grows to 1160x600 / minsize 900x420. +13 tests (`tests/test_native_master_recent.py`: schema-3 round trip, schema-1/2 promotions, the named refusals, the cap, the app behavior) + 5 UI tests in `tests/test_native_master_ui_mt13.py`. |
| MT-16 | Persisted waiting-view settings | done (2026-11-03) | `master-settings.json` schema 3 → 4: `view_filter` (the raw filter entry text, at most `VIEW_FILTER_MAX` = 200 characters, "" = no filter), `view_sort` (one of `VIEW_SORT_MODES` — mirrors `table_filter.SORT_MODES`) and `view_mode` (one of `VIEW_MODES`: "list" flat rows / "process" grouped by bound process name). Schema-1/2/3 documents promote on load with the documented defaults ("" / "name" / "list"); a schema-3 document carrying a view_* field is refused as an unknown field (foreign schema, never silently promoted — the same discipline as MT-11/MT-15). The format-level constants live in `master_state` (the attach-mode pattern); a test pins the mirror against the pure layer. `MasterApp.set_view_settings(filter_query, sort_mode, view_mode)` validates (named `ValueError`s) and re-persists immediately; the window restores all three from the app at construction, and every UI change point calls it (filter `<KeyRelease>`, sort cycle, view cycle, Esc clear). +4 state tests (`tests/test_native_master_state.py`), +5 UI tests in `tests/test_native_master_ui_mt16.py`. |
| MT-17 | Process-grouped waiting view | done (2026-11-03) | `table_filter.group_tables_by_process` (pure reshaping of the already-sorted-and-filtered row set — never adds or drops tables): one parent row per casefolded bound process name (a table with several bound names appears once under EACH of them), the tables without a bound name under `UNBOUND_PROCESS_LABEL` ("(no process binding)") last; within a group the caller's sort order is preserved; group labels are casefolded, i.e. the same identity the running-PID markers key on. UI: a "View: list/process" cycle button between the sort button and the filter entry (persisted through MT-16); the tree (`show="headings"`) renders the group label + "N table(s)" count into `values[0]` of the parent row (the `text` item is invisible), the children through `_insert_table_row`; group rows are display-only — `_is_table_row` gates the double-click, the Enter/`_table_selected_rel` and the row context menu, so a group row never loads. +8 pure tests (`tests/test_native_master_table_filter.py`), +5 UI tests in `tests/test_native_master_ui_mt16.py`. |
| MT-18 | Pinned / favorite tables | done (2026-11-03) | `master-settings.json` schema 4 → 5: `pinned_tables` (relative table paths, most recent pin first, capped at `PINNED_TABLES_LIMIT` = 25, each a non-empty string within the table-path length bound). Schema-4 documents promote on load with `pinned_tables=[]`; a schema-4 document carrying the field is refused as an unknown field (same discipline as MT-11/15/16). The pure `table_filter.pin_tables` reshaping of the already-sorted-and-filtered row set (never adds or drops tables): pinned rows first in pin order, casefolded comparison, the remainder keeps the input order, pin paths not in the row set (filtered out or gone) ignored. UI: the row context menu offers "Pin to top" / "Unpin" (`_toggle_table_pin` → `MasterApp.set_table_pinned`, named `ValueError`s for cap / already pinned / not pinned, immediate persist); a pinned table floats to the top of the list view and to the top of its process group in the grouped view (the pin set is applied after filter + sort, before the MT-17 grouping); the pin marker lives in the detail column ("pinned" / "pinned - PID …"), the first column stays the bare relative path (the row identity the load paths key off). +4 state tests (`tests/test_native_master_state.py`), +4 pure tests (`tests/test_native_master_table_filter.py`), +7 UI tests in `tests/test_native_master_ui_mt18.py`. |
| MT-19 | Trainer-focus mode (waiting view collapses on attach) | done (2026-11-04) | `master_ui.py`: the whole waiting view now lives in one container frame (`MasterWindow._waiting_frame`, `fill=both expand=True` on the shared root) — the header (title, filter, sort/view cycles, repo link, Load table / Change folder / Rescan / UI flow / Close), the folder / meta / running lines, the table-tree frame and the status bar are all its children. `_enter_trainer()` destroys the container immediately after the engine is up (before the `TrainerWindow` is built) and drops every waiting-view widget reference, so the trainer row grid owns the full window instead of sharing it with the table list, and the poll loop / handlers never touch a destroyed widget (the poll tick already early-returns in trainer mode). The trainer-constructor failure path rebuilds the waiting view before `_fail_trainer_start()` so the waiting loop and its loop guard stay consistent; `_back_to_master()` is unchanged (destroy-all + rebuild). The open UI-flow Toplevel is closed with the teardown. +6 UI tests in `tests/test_native_master_ui_mt19.py` (container parenting, the collapse through the patched handoff, the constructor-failure rebuild, the back-to-master fresh frame, one real-`TrainerWindow` case). |
| MT-20 | Discoverability: in-app UI-flow reference + keyboard map | done (2026-11-04) | `master_ui.py`: the module function `ui_flow_text()` (headless-testable) is the plain-language UI-flow document — the same content as the reviewable `UI.md` in the package (ships in the source ZIP through the existing `.md` allowlist); the new "UI flow" header button opens it in a read-only Toplevel (single window: a second click lifts + focuses the open window instead of duplicating; the window is transient to the root and closed on trainer entry). **F5** re-scans the folder from anywhere in the waiting view (root binding, guarded no-op in trainer mode exactly like the existing "/" binding). The table tree takes the **initial focus** on build (`focus_set` at the end of `_build_waiting_view`), so arrow keys and Enter work immediately without a first click. The "Retry load" re-arm moves out of the root-level button below the status strip into the status bar next to the attach toggle and the Recent button. +7 UI tests in `tests/test_native_master_ui_mt19.py` (document content, the read-only Toplevel + lift-on-second-click, the trainer-entry close, the F5 contract in both modes, the initial-focus spy, the retry-bar placement). |
| MT-22 | Table details + live load-gate preview (waiting view) | done (2026-11-04) | `table_details.py` (new pure builder - the ordered (label, value) rows of the read-only details window: Table / Folder / Size / Modified / Bound process(es) / Index status / Pinned / Last used / Running now / Content sha256 (last scan, first 12 hex + "...") / Load gate (live re-check); `format_size` / `format_mtime` / `gate_line` formatters with named fallbacks). `master_ui.py`: the row context menu offers **"Table details"** first - one read-only Toplevel with the indexed facts for the row plus the on-demand `gate_table_for_load` re-check (the same pass MT-9 runs at load time; refusal = stable named code + displayable detail), so a table can be inspected and its current loadability checked before loading it; single window (a second open lifts + focuses instead of duplicating), transient, non-resizable, closed on trainer entry with the rest of the waiting view; the only I/O is the bounded gate re-check under the load limit. +16 tests (pure builder coverage + the Tk wiring: menu order through a recording `tk.Menu` subclass, window rows incl. the live gate line, lift on second open, trainer-entry close, named refusal display - all in `tests/test_native_master_ui_mt22.py`). |
| MT-23 | Per-table live status + color coding + status filter (waiting view) | done (2026-11-04) | `table_status.py` (new pure decision layer - no OS access, no index mutation, no orchestrator or state access): `row_file_status(entry, fingerprint)` derives the live file state of one indexed table from the index entry (last-scan `(size, mtime_ns)` + cached status/detail) and the current on-disk fingerprint - `missing` (file gone / stat fails) / `changed` (fingerprint drift) / `unreadable` (the last scan could not read/parse it, the named detail surfaces) / `ok`; cheapest fact first, live facts outrank the cached scan state - the same order the MT-9 gate proves at load time. `row_status` adds the process state: a running bound process shows `running` only for a loadable file (a live process cannot make a changed / missing / unreadable table loadable). `row_tag` maps code → tree color tag ("" default for ok / running, "attention-warn" for changed, "attention-error" for missing / unreadable; unknown codes fall back to the default). `filter_rows_by_status` reshapes the ordered row set per the persisted mode - "" (all, the identity), "ok" (the loadable rows), "attention" (the rows the gate would refuse right now); input order preserved, an unknown mode raises the named `ValueError`. `master_state.py`: `master-settings.json` schema 5 → 6 - `view_status` (one of `VIEW_STATUS_FILTERS`, mirrored by `table_status.VIEW_STATUS_FILTERS`); schema-5 documents promote with `view_status=""`, a schema-5 document carrying the field is refused as an unknown field (the MT-11/15/16/18 discipline). `master_ui.py`: one bounded `stat` per visible row per render (`_live_fingerprint` / `_row_status`) feeds the live Status column (ok / running / changed / missing / unreadable) + the row color coding (the two tree tags configured in `_build_waiting_view`: amber `#e5c07b` for changed, red `#ff7b72` for missing / unreadable); the persisted "Status: all/ok/attention" header cycle button (between the view button and the filter entry; `MasterApp.set_view_settings` gains the 4th parameter `status_filter` - validated + re-persisted, and every existing change point passes the current mode through); `_visible_tables()` applies the status filter between the query filter and the pin float; the meta line gains the active `status filter: X` part and the live `attention: N` count (how many indexed tables the MT-9 gate would refuse right now). Zero new load-path behavior, zero catalog effect. +4 state tests (`tests/test_native_master_state.py`: schema-6 round trip, schema-5 promotion, the unknown-field refusal, the named value refusals), +24 tests in `tests/test_native_master_ui_mt23.py` (the pure layer + the Tk wiring: cycle / persist / restore, the other UI changes keeping the mode, the live changed / missing flags + tags, the ok / attention row shaping, the running-loses-to-attention contract, the meta line). |

| MT-24 | Per-table entry count + blocked count (background plan analysis) | done (2026-11-06) | `table_analysis.py` (new pure decision layer - no OS / index / state access): `counts_from_plan` (actionable = the supported script / value records of the compiled plan, i.e. the real cheat options; blocked = the blocked record count of the same analysis) + `blocked_reasons_from_plan` (top-8 stable named reasons with counts), `ok_analysis` / `failed_analysis` (bounded failure detail, 200 chars, the named `AnalysisRefusal`), `AnalysisStore` (`table-analysis.json`, schema 1, under the state home; keyed by the table content sha256, strict document validation - root / schema / key-set / checksum / timestamp / count - LRU-bounded to 1024 entries; a content change re-analyzes, an unchanged table reuses the cached entry). `analysis_worker.py` (one background daemon thread; queue bounded to 64, dedupe by content sha, only tables with a bound process name are queued; compiles through the tested `compile_table` plan path - no Lua execution, no target attach, no engine - the same static proof the corpus audit uses; a named compile failure is persisted as the failed entry). `master_ui.py`: the waiting view gains two columns between Detail and Size - Entries / Blocked (pending "…", failed "–", the counts once analyzed; a blocked count > 0 appends "N blocked" to the detail column after the pin marker); the meta line shows the live "analyzing N table(s)" figure while the queue has work; the worker lifecycle is owned by the waiting view (start + queue at the view build, pause on trainer entry after the attach gate, stop + clear on close) - display-side only, never blocks / alters / delays the MT-9 load gate, which re-checks the table independently at load time. `table_details.py`: the MT-22 details window gains the analysis block (entry count / blocked count / top blocked reasons / the failure detail). +69 tests (the pure-layer coverage in `tests/test_native_master_analysis.py` - incl. the `active_workers()` live-worker registry lifecycle - + the UI coverage in `tests/test_native_master_ui_mt24.py`; assertion updates in the existing master-UI test files for the two new columns; plus the cross-module test-isolation fix - the shared Tk test teardown stops every live plan-analysis worker, so window tests no longer leak worker threads into the later engine/timing modules). Catalog zero delta `blocked-catalog-032-analysis`. |

## Online feature evaluation (2026-11-02)

Web research (2026-11-02) evaluated all-in-one trainer front ends and
trainer tooling for features that fit the Master Trainer use case
(“detach the trainer, choose which table runs against which process,
remember the configuration”):

- **OpenForge (openforge-aio)** — multi-game all-in-one trainer: code
  patches auto-revert on detach, sub-100 ms re-attach, per-feature
  global hotkeys with conflict detection, an explicit Attach button,
  offline / no telemetry, table-folder drop.
- **Cheat Engine 7.5** (local read-only behavior reference): the process
  selection is a list of running processes (name + PID) with
  double-click attach; nothing about the choice is persisted.
- **LaunchForge / auto-update loaders** — noted, out of scope (the
  local-only, offline, hash-verified build policy).

Adopted in this cycle: the explicit table load (MT-10), the persisted
attach mode + process picker with the session PID pin (MT-11) and the
detach / user attach (MT-12). Deliberately deferred: global per-feature
hotkeys (the engine already supports per-record hotkeys; a global OS
registration surface goes beyond the documented single-target,
local-only model), auto-update (contradicts the offline, hash-verified
build policy) and concurrent multi-table sessions (the documented model
is one active session at a time — return to the Master, then re-load).

### 0.26 waiting-view usability (evaluated 2026-11-02/03)

With ~151 indexed tables (143 distinct hashes) the waiting view needs
real navigation. The 0.26 evaluation (web research over table/list
UX patterns + the local 0.25 baseline, record kept with the change)
adopted: waiting-view search / filter / sort (MT-13), the keyboard
load flow (MT-14) and the rolling recent list with the Size /
Modified / Last-used columns (MT-15). Deliberately deferred:
group-by-process tree (the flat list + the process sort covers the
finding task without a second hierarchy), persisted filter/sort (view
state stays session-only) and entry-count / blocked-count columns
(catalog numbers belong to the local tooling, not the waiting view).

### 0.27 waiting-view settings + process groups (evaluated 2026-11-03)

Follow-up online evaluation (recorded with the change): playR
("ratings, lists, statuses, filters, sorting and statistics —
organise a collection of several hundred games"), Universal Game
Launcher ("powerful filters and bookmarks"), GamesList Manager
("sortable columns, color-coded status, search") and the Game Cheats
Manager (one-stop Fling trainer launcher), plus the standing user
requirement (the waiting view is configurable and "merkt sich das
einmal eingestellte" — it remembers what was set once). Both items
deliberately deferred in 0.26 are adopted: the persisted
waiting-view settings (MT-16) and the process-grouped view (MT-17).
Deliberately deferred (documented): entry-count / blocked-count
columns (the catalog numbers belong to the local tooling, not the
waiting view) and per-table status / color-coding (the indexed Status
column plus the running-PID markers already carry the state; a status
taxonomy would be a feature in its own right).

Follow-up research (2026-11-03): Cheat Happens Trainer Manager (a
"Last Used Trainer" pinned above the list - the MT-15 recent list
already covers this), GameTrainerLauncher (a sortable local trainer
library with status feedback - covered by the MT-13/15/17 feature
set), GamesList Manager ("sortable columns, color-coded status" -
corroborates the deferred status / color-coding item) and VGC Shelf
("sort, pin, archive" - pinning as a first-class feature). Adopted
for 0.28: pinned/favorite tables (MT-18) - the persisted pin set
plus pinning to the top of the waiting view. Remaining candidates
(evaluated, not yet adopted): entry-count / blocked-count columns
and per-table status / color-coding (already deferred in
0.26/0.27).

### 0.29 trainer-focus + discoverability (evaluated 2026-11-04)

User field request (2026-11-04): when a process is identified and the
trainer attaches, the waiting table list must shrink/collapse so the
trainer items get maximum space; the UI should be generally more
accessible; and the UI flow should be documented for review. The
0.29 evaluation (local code audit of the shared-root trainer handoff
plus web research over trainer-manager UI patterns - Trinity
("hotkeys, profiles, an in-game overlay" - saved per-game
configurations, corroborated by the standing user requirement "merkt
sich das einmal eingestellte", already covered by MT-6/11/15/16/18),
Cheat Happens AURORA ("easily accessible for the games you are
currently playing" - discoverability), the keyboard-shortcut
databases (a documented shortcut map is a recognized app-UX
baseline), and the WCAG / platform accessibility guidance (descriptive
labels, keyboard operability, no reliance on a single input path))
adopts: the trainer-focus mode (MT-19 - the root cause is that the
waiting-view widgets are packed directly on the shared root and are
never destroyed on trainer entry; the single container frame fixes
the space sharing) and the discoverability set (MT-20 - the in-app
"UI flow" reference dialog, the F5 re-scan, the initial table-list
focus, and the Retry-load re-arm moved into the status bar). The
reviewable full-flow document ships as `master_trainer/UI.md`
(in-package, in the source ZIP) mirroring the in-app dialog.
Deliberately deferred (documented candidate MT-21, separate cycle):
the multi-column trainer grid - the single-column canvas grid is the
validated touch-first design (`ui_rows.py` pure row model +
`ui_layout.py` + the 1-D hit-testing, exhaustively tested and shared
with the standalone trainer); a column layout rewrites the pure row
model, the pagination and the 2-D hit-testing and changes the
standalone trainer as well. Remaining candidates (unchanged):
entry-count / blocked-count columns and per-table status /
color-coding.

### 0.30 table details + load-gate preview (evaluated 2026-11-04)

The 0.30 evaluation (web research over trainer front-end and
trainer-manager UX patterns - FLiNG's per-trainer version /
"Last Updated" metadata (per-table freshness facts surfaced in the
list are a recognized pattern), game-trainer-manager
(Karasukaigan) (organize / search / import workflows around a
trainer table list), Game Cheats Manager's .ct handling FAQ (what a
table is, how it binds to a process - inspection before use),
Cheat Happens Trainer Manager v2 (portable front end, last-used /
pinned table ordering - corroborated by the MT-15/18 recents +
pins)) adopts: the read-only table details window with the live
load-gate preview (MT-22). Rationale: before loading a table the
user can now see every indexed fact for it (path, folder, size,
modified, bound processes, index status, pin, last used, running
PIDs, content sha) and its **current loadability** - the same
`gate_table_for_load` pass MT-9 runs at load time, with the same
named refusal code + displayable detail - so a stale / changed /
unreadable table is explained at inspection time, not only at load
time (reliability + reviewability; zero new behavior in the load
path itself, zero catalog effect). The row builder is pure in
`table_details.py` (headless-testable), consistent with the 0.18
row-details window, the `describe` CLI subcommand and the MT-20
discoverability lineage. Deliberately deferred (unchanged
candidates): the MT-21 multi-column trainer grid, and the
entry-count / blocked-count columns + per-table status /
color-coding.

### 0.31 per-table live status + color coding + status filter
(evaluated 2026-11-04)

The 0.31 evaluation (web research over trainer front-end and
trainer-manager UX patterns - FLiNG's per-trainer "Game Version" /
"Last Updated" / option-count metadata (per-table freshness and state
facts surfaced in the list are a recognized pattern), Game Cheats
Manager (dyang886) (the "smart launcher": drop tables + trainers,
detect the installed games, associate trainer ↔ game, auto-update -
the detection + the trainer↔game association are already covered by
MT-2 / MT-17; the auto-update is out of scope by the offline,
hash-verified build policy; the Python + Tkinter implementation
corroborates the Master's stack), game-trainer-manager (Karasukaigan)
(download / import / organize / search around a trainer list),
CheatDeck (SheffeyG) (Steam Deck launch options - the documented
MT-7 route)) adopts: the per-table live status + color coding +
status filter (MT-23) - the candidate deliberately deferred in
0.26/0.27/0.29/0.30 ("per-table status / color-coding"). Rationale:
the indexed Status column carried the cached state of the last scan;
the folder content may have drifted in between (a table edited,
replaced or deleted), and the MT-9 gate would refuse such a table
with a named code at load time - MT-23 surfaces that at a glance
(one bounded `stat` per visible row per render, cheapest fact first,
live facts outranking the cached scan state - the same order the
gate proves), with row color coding (amber for changed, red for
missing / unreadable) and the persisted "Status: all / ok /
attention" filter. Remaining candidates (unchanged): the MT-21
multi-column trainer grid and the entry-count / blocked-count
columns (they need background plan-analysis infrastructure).

### 0.32 per-table entry count + blocked count (background plan
analysis) (evaluated 2026-11-05)

The 0.32 evaluation (web research over trainer front-end and
trainer-manager UX patterns - FLiNG's per-trainer "N Options" /
option-count metadata (per-table entry counts surfaced in the list
are a recognized pattern - the list tells the user what a table
actually offers, and what cannot run in it, before loading),
game-trainer-manager (Karasukaigan) (organize / search / import
workflows around a trainer table list), Cheat Happens Trainer
Manager v2 (portable front end, the inspect-before-load lineage of
MT-22)) adopts: the per-table entry count + blocked count columns
(MT-24) - the candidate deliberately deferred in 0.26/0.27/0.29/
0.30/0.31 ("the entry-count / blocked-count columns ... need
background plan-analysis infrastructure"). Rationale: the waiting
view now shows, per table, what it will actually run (the
actionable script / value records - the real cheat options) and
what it cannot (the blocked records), computed in the background by
one daemon thread through the tested `compile_table` plan path (no
Lua execution, no target attach - the same proof the corpus audit
uses). A failed compile is a named, persisted failure (the columns
show the failed marker, the details window shows the reason and
the top blocked reasons); the persisted `table-analysis.json`
document (schema 1, under the state home, keyed by the table
content sha256, LRU-bounded entries + reasons) with its pure
decision layer lives in `table_analysis.py`; the worker
(`analysis_worker.py`) pauses on trainer entry, resumes +
re-queues with the waiting view, and the meta line shows
"analyzing N table(s)". Zero catalog effect (no table-parsing
change), no new load-path behavior. Remaining candidates
(unchanged): the MT-21 multi-column trainer grid.

### 0.33 candidate: table folder auto-rescan (evaluated 2026-11-06)

The 0.33 evaluation (web research over trainer front-end and
trainer-manager patterns - WeMod (automatic game detection: the
front end scans the machine and pairs the found games with the
available content; the "Play/Playing" button state reflects the
running game; "save your mod selections for next time without
enabling them every time"; in-game overlay + smartphone remote
app), game-trainer-manager (Karasukaigan) (a .exe/.zip trainer
library: import, organize, search, pin, delete, one-click launch;
watches a download directory and auto-imports matching files),
Cheat Happens Trainer Manager (the central library that keeps the
trainer collection organized and up to date), FLiNG Downloader
(search a game, review the trainer's options - offline research
only)) maps onto the Master Trainer use case as follows:

- Automatic game detection / content pairing: already covered by
  MT-1/MT-2/MT-3 (the folder-scanned table index + the
  cross-platform process watch + the unique-match auto-load).
- "Save your selections for next time": already covered by the
  MT-5/MT-6 on/off persistence + the per-table settings sidecar.
- Pin / search / organize: already covered by
  MT-13/MT-15/MT-17/MT-18.
- Delete / import / download: out of scope (the tables are strict
  read-only inputs; the tooling never deletes or modifies user
  files; no download surface under the offline, hash-verified
  build policy).
- Launch the game from the front end (the WeMod Play button; the
  CE-forum "run the game's EXE from the trainer" pattern):
  deferred - the index binds process names, not install paths;
  without path data a launch integration cannot be proven
  fail-closed.
- In-game overlay / smartphone remote / telemetry: out of scope
  (local-only, offline, single-window model).
- Watch the watched folder for new / changed content and pick it
  up automatically: **the adopted 0.33 candidate** - the table
  folder auto-rescan (MT-25): the waiting view re-runs the
  existing incremental scan (the same `(size, mtime_ns)` + sha256
  short-circuit contract as the manual Rescan) on a bounded
  background interval, so added / changed / removed tables show
  up in the index and the view without a manual F5; the setting
  persists in the master state (default on, bounded interval,
  the same schema-promotion discipline), paused on trainer entry
  exactly like the MT-24 analysis worker; no OS file-watcher API
  - polling only, cross-platform, one stat pass per interval,
  zero effect on the load path (the MT-9 gate re-checks the
  table independently at load time).

Adopted for 0.33: the table folder auto-rescan (MT-25). Remaining
candidates (evaluated, not yet adopted): the MT-21 multi-column
trainer grid, per-table notes / tags (organize metadata - low
value for the private 151-table corpus), the game launch
integration (needs install-path data), the multi-root index
(open design decision).

## Merge & release plan (historical + current)

1. MT-1..MT-5 shipped on `main` with the 0.21 release (2026-10-31);
   MT-6..MT-9 with the 0.23 release (2026-11-01); MT-10..MT-12 with the
   0.25 feature release (2026-11-02); MT-13..MT-15 with the 0.26
   release (2026-11-03) — normal merge + push, never
   force, in-build suite green and zero catalog delta (the features
    touch no table parsing); MT-16..MT-17 shipped with the 0.27
    release (2026-11-03).
2. The feature is user-testable immediately from source:
   `python -m ct2trainer.native master <folder>` (PYTHONPATH=src).

## Open design decisions (recorded, no code change)

- **Default architecture x64** for auto-compiled plans (the converter
  default). A 32-bit game yields the engine's named architecture
  refusal; x86 auto-detection is a possible follow-up.
- **One state home per user**, one index document: switching folders
  rebuilds the index for the new root (the previous root's index is
  dropped). A multi-root index is a possible extension.
- **Auto-load is silent by design** (user request: the unique match is
  loaded automatically). The picker only appears for the genuinely
  ambiguous case (several tables, one process).
- **Ask on first start for the table folder** (recorded 2026-11-01,
  implemented): the last-used folder persists in the state home
  (`master-settings.json`, checksum-bound like the tables index); a
  parameterless start reuses it when it still exists, and only a
  genuinely first start (or a stale stored folder) shows the directory
  picker. An explicit folder argument always wins and becomes the new
  persisted folder.
- **MT-7 scope decision** (recorded 2026-11-01, implemented): the
  SteamOS/CheatDeck target route ships as the *documented-route surface*
  (`steamdeck_route.py`: named fail-closed refusal + the Proton-wrapped
  standalone CT2Trainer Windows trainer EXE route text + waiting-view
  hint). The owned Linux attach backend is deliberately NOT part of this
  milestone; until it exists the Linux Master runs
  detection/index/UI only and attach refusals stay fail-closed and
  named. The Deck protocol run with exact build hashes is root/user
  field work (`tests/deck/compatibility-matrix.md`).
