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
| MT-6 | Per-table settings sidecar wiring | queued | Wire the existing `settings_model.py` (`.ct2trainer.json`: name drafts, value defaults, hotkeys) as a per-table master sidecar under the state home; restore on load, save on close. The on/off wish persistence itself already works via the engine state store (MT-4). |
| MT-7 | SteamOS / CheatDeck target route | queued (later) | Linux attach backend or the documented Proton-wrapped-trainer route; then run the Deck protocol (`tests/deck/compatibility-matrix.md`) with exact build hashes. Until then the Linux Master Trainer runs detection/index/UI only, and attach refusals stay fail-closed and named. |
| MT-8 | Frozen Master entry point | queued (later) | `tools/native_master.py` frozen to `CT2Trainer-Master.exe` with the `Master_Trainer.ico`, sharing the template/bundle machinery of the standalone trainer; add to `scripts/Build-Native.ps1` outputs. |

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
  dropped). A multi-root index is a possible MT-6-era extension.
- **Auto-load is silent by design** (user request: the unique match is
  loaded automatically). The picker only appears for the genuinely
  ambiguous case (several tables, one process).
