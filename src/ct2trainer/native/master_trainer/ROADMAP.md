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

## Merge & release plan

1. This feature lands on `main` behind the branch
   `native-0.20-master-trainer` (normal merge + push, never force),
   with the in-build suite green and zero catalog delta (the feature
   touches no table parsing).
2. The next build is **0.20** (feature release, minor bump per the
   versioning rule); VERSION + `__init__.__version__` + CHANGELOG entry
   are part of this change.
3. The feature is user-testable immediately from source:
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
