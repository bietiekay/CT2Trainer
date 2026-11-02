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

## Merge & release plan (historical + current)

1. MT-1..MT-5 shipped on `main` with the 0.21 release (2026-10-31);
   MT-6..MT-9 with the 0.23 release (2026-11-01); MT-10..MT-12 with the
   0.25 feature release (2026-11-02) — normal merge + push, never
   force, in-build suite green and zero catalog delta (the feature
   touches no table parsing).
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
