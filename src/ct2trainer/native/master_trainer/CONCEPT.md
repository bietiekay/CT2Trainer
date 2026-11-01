# CT2Trainer Master Trainer — Concept

**Status:** MT-1..MT-5 merged into `main` with the 0.21 release (merge
`9a725a8`, 2026-10-31); MT-6..MT-8 (the full roadmap) implemented on
branch `native-0.23-master-roadmap` (2026-11-01) together with the
waiting-view observability work and the ask-on-first-start folder
persistence. Design and implementation notes; the working plan is
[ROADMAP.md](ROADMAP.md).

## What it is

The Master Trainer is one long-lived trainer window instead of one trainer
per table. The user starts it once, points it at the folder that holds
their `.ct` tables (sub-folders included), and then works normally: when a
game process starts that a table binds to, the Master Trainer loads that
table automatically, attaches, and switches into the exact trainer UI of
the standalone `trainer.exe`. Toggles the user enables are persisted
per-table and restored on the next load of the same table. When the user
returns to the Master (header button “⬅ Master”), the same window keeps
waiting for the next matching process — a “Forever-Master-Trainer”.

The Master Trainer adds **no new trainer functionality**: every table
feature, activation contract, fail-closed guard and state journal is the
already-tested CT2Trainer engine (`TrainerEngine` + `TrainerWindow`). The
Master Trainer is only the folder index, the process watch and the
auto-load/handoff loop around that existing engine.

## The two modes

### Waiting mode (default)

- Shows the configured folder, a compact metadata line (table counts,
  bound process names, last scan time, the state home location), a live
  “Running now” line (which bound processes are visible in the latest
  process snapshot, with PIDs), the table index (one row per `.ct` table:
  relative path, bound process name(s), status — rows for a running
  process are marked `running` with its PID(s)) and a live status line.
  On non-Windows the metadata line also carries the permanent MT-7 route
  hint (attach unavailable; the documented Proton-wrapped trainer route).
- The table folder is taken from a CLI parameter, or from the
  last-used folder persisted in the state home (`master-settings.json`);
  only a genuinely first start (or a stale stored folder) shows the
  directory picker — “ask on first start”.
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
wishes and state journal of the standalone trainer. The only visible
difference is one extra header button, “⬅ Master”, which:

1. closes the engine cleanly (`engine.close()`; the state and session
   journals are preserved on an unclean close, exactly as the standalone
   trainer does),
2. destroys the trainer widgets,
3. rebuilds the waiting view in the same window and resumes polling.

Closing the window (X) in either mode closes the whole app: in trainer
mode it first runs the engine close, so no state is orphaned.

## Folder index (the scan optimization)

Index file: `<state home>/tables-index.json` (state home =
`%LOCALAPPDATA%\CT2Trainer\native\master-trainer` on Windows,
`$XDG_STATE_HOME/CT2Trainer/native/master-trainer` on Linux). The index
lives **outside the table folder** so the user's table directory is never
written to.

Per table the entry stores: relative path, size, `st_mtime_ns`,
`sha256`, bound process names, and a status (`ok` / `unreadable` with a
named error). Reconcile rules:

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

## CLI

```
ct2trainer native master [FOLDER] [--state-dir DIR] [--debug-log] [--poll-ms N]
```

- `FOLDER` optional; when omitted the last-used folder stored in the
  state home is reused when it still exists, and only a genuinely first
  start (or a stale stored folder) shows the directory picker. An
  explicit folder always wins and becomes the new persisted folder.
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
- No cross-machine index sync, no multi-root index, no hot-reload of a
  loaded table while its trainer session is active (return to the
  Master, then re-load).
