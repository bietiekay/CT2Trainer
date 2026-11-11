# CT2Trainer: where we stand

**Updated:** 2026-11-11. **0.43 released** (build
`native-20261111T184600Z-3bf9d8aa`, cut from `main` @ `0df2607`,
2026-11-11) - the Master Trainer minimize-to-tray +
window-geometry persistence (MT-32: the persisted "Minimize to tray"
toggle, master-state schema 9 -> 10 `tray_minimize`, the Win32 tray
icon behind a bounded, named fail-closed guard - a missing
`Shell_NotifyIconW` export or a refused `RegisterClassExW` (Win32 87)
is the named `tray-platform-unavailable` / `tray-icon-missing` /
`tray-setup-failed` refusal in the status line, never a crash and
never a dialog; restore on tray double-click; the tray balloon
reports the trainer's attach success / failure through the new
`ui.py` `attach_observer` - the standalone trainer header stays
byte-identical; MT-33: window size / position persisted in the same
master-state document (`window_geometry`), saved on the bounded
`<Configure>` cadence and on close, an invalid persisted geometry is
the named `window-geometry-invalid` refusal) + the TGC field fix
(transient target-memory reads no longer block the engine - Win32
299 joins the bounded snapshot transient retry set, the transient
set {299, 119, 1116, 24} is never treated as an observed change, a
real mismatch or a non-transient error blocks immediately, the
bounded verify-skip streak limit of 30 ticks names the condition
instead of looping); +85 tests (62 in
`tests/test_native_master_tray_geometry.py` + 17 in
`tests/test_native_tgc_field_fix.py` + 6 in the
`tests/test_native_architecture.py` /
`tests/test_native_master_state.py` updates); full main suite 5,011
OK / 36 expected skips; in-build suite 5,011 OK / 36 expected
skips, `ce_inputs: []`; catalog zero delta `blocked-catalog-043-tgc`
(117,809 total / 117,272 supported / 12,974 headings / 104,123
actionable / 537 blocked - zero newly blocked, zero unblocked, zero
reason changes); see the 0.43 section below.
Superseded 0.42 (build
`native-20261111T044023Z-04112d15`, cut from `main` @ `377f760`,
2026-11-11) - the CE 7.5 cleanup parity (a disable-phase cleanup
name that NO program owns is a silent no-op, matching CE
`unregistersymbol` / `dealloc` - read-only reference:
`autoassembler.pas` L2492-2525 appends to the deletion list without
an ownership check, L2625-2669 searches only this program's
allocation set; the name is dropped from the program node and
recorded in the new program field `unowned_cleanup_dropped` instead
of refusing the program, so the record stays supported; a name
live-registered by another supported record keeps the named WP-37
handover refusal - a plan-level re-check re-blocks a
first-pass-supported record when one of its dropped names is (a) a
WP-37 handover name or (b) in any other supported record's
entry-level `provides`, with the single-form reason "Program may not
unregister or deallocate the externally owned symbol X (owned by
record N).") + the bounded Windows API-export registry extension
(RT-4.2 R7: `sleep` / kernel32.dll, `showwindow` / user32.dll - the
corpus thread idioms (HorizonForbiddenWest `mov rcx,10 / call
Sleep`, APlagueTaleRequiem / Resonance console-open `call
ShowWindow`) now resolve with the exact `api_exports` marker +
link-time PE export resolution, named fail-closed refusal on an
absent export); +9 tests (new
`tests/test_native_aa_cleanup_parity.py`) + the deterministic MT-24
race guard; full main suite 4,926 OK / 35 expected skips; in-build
suite 4,926 OK / 35 expected skips, `ce_inputs: []`; catalog
remeasure `blocked-catalog-042-cleanup`: 117,809 total / 117,272
supported / 12,974 headings / 104,123 actionable / 537 blocked
(-268 vs 0.41, zero newly blocked, 268 unblocked: 26 `Sleep` + 2
`ShowWindow` + 24 direct cleanup-ownership rows + 216 provider
cascades); see the 0.42 section below.
Superseded 0.41 (build
`native-20261110T210856Z-5811040c`, cut from `main` @ `c724a7e`,
2026-11-10) - the AA typed-constant package (the CE
`StrToQWordEx` contract: the full typed family
`(int|float|double|dword|qword|word|byte)` as operand, data
literal and `define` value; the integer family parses
`0x`/`$` hex as an integer, decimal / exponent forms as a
float truncated toward zero, out-of-range as the named
refusal "Typed constant exceeds the {type} representation.";
the float / double family finite-only with the named
`Inf`/`-Inf`/`NaN` spellings; the deliberate dialect boundary
- typed constants parse pure digits DECIMAL, the unsized AA
dialect stays hex-by-default - 41 corpus rows byte-changing
CE-parity fixes incl. the Borderlands3 `cmp [flag],(byte)2`
byte-compare, the two decimal-form DS `(int)0.00` rows
assemble for the first time) + the digit-leading-label CE 7.5
parity fix (the `getPotentialLabels` contract: a `name:` line
is a positional label definition iff
`trystrtoint64('$'+name)` fails - the `_symbol_name_token()`
predicate at all eight cursor / symbol sites in
`aa_program.py`: digit-leading non-hex names are local
labels (`0CurrentWeight:` keeps the owned region for the
`resb 8` padding), all-hex names stay the classic
externally-provided symbol cursor, the `0x...` literal
tokens never enter the requirements, the link walk's
`key not in resolved` guard keeps the Octopath `8Path*`
scan symbols on the classic resolution path - closing the
second Death Stranding "Load Table" root, record 130605,
whose failure blocked the ~243-row "no unique supported
provider" cascade); +38 tests (new
`tests/test_native_aa_typed_constants.py` 23 + new
`tests/test_native_aa_digit_labels.py` 15 with the NASM byte
pins); full main suite 4,917 OK / 35 expected skips;
in-build suite 4,917 OK / 35 expected skips, `ce_inputs: []`;
catalog remeasure `blocked-catalog-041-digit-labels`: 117,809
total / 117,004 supported / 12,974 headings / 103,855
actionable / 805 blocked (-248 vs 0.40, zero newly blocked,
248 unblocked, zero reason changes); see the 0.41 section
below.
Superseded 0.40 (build
`native-20261110T093203Z-82c49872`, cut from `main` @ `e611e9e`,
2026-11-10) - the Master Trainer process identification in
picker + details (MT-31) + the bounded zero-transfer
transient-write retry in `memory.py` (MT-31: the optional
identification fields `path` / `creation_time` /
`pointer_size` on `ProcessSnapshotEntry`, all default `None`
- fail-closed, the row keeps the byte-stable name + PID form,
the `pid` / `name` decision fields are never touched; the
bounded per-candidate enrichment only at picker + details
open - Windows `OpenProcess(PROCESS_QUERY_INFORMATION)` +
`QueryFullProcessImageNameW` + `GetProcessTimes` +
`IsWow64Process2`, procfs `exe` link target + `stat` field
22 + `btime`; the picker rows and the table-details "Running
now" row render the proved facts, a refused fact never
renders); (the write-side symmetry of the 0.39
transient-read retry: a `WriteProcessMemory` call that
FAILED with the transient set {299, 119, 1116, 24} and
transferred NOTHING is retried in `memory._write_checked`
with the bounded exponential backoff - exactly 4 attempts,
backoff 0.05 -> 0.25 s; a partial transfer or any
non-transient code is never retried, the original error is
raised unchanged after the budget - completing the read /
write pair); +46 tests; full main suite 4,879 OK / 35
expected skips; in-build suite 4,879 OK / 35 expected
skips, `ce_inputs: []`; catalog zero delta
`blocked-catalog-040-process-id`; see the 0.40 section
below.
Superseded 0.39 (build
`native-20261110T051241Z-57bf7d47`, cut from `main` @ `17a22f7`,
2026-11-10) - the Master Trainer per-table auto-load
policy (MT-29) + state folder / debug log quick access
(MT-30) + the bounded transient-read retry in `memory.py`
(MT-29: the per-table auto-load policy - `table-autoload.json`
schema 1 under the state home, keyed by the table content
sha256 - the same identity as the MT-24/27/28 sidecars, so a
policy survives a rename and follows a content-identical
file to another root; only the non-default manual-only
policy persists, the absence of an entry is the documented
automatic default; a manual-only table is never auto-loaded
- no request, no picker, a stable named waiting detail -
and every explicit load path keeps working unchanged; the
orchestrator re-evaluates the policy on every tick; the row
context menu toggle + the MT-22 details row + the filter
matches the persisted policy text); (MT-30: the two
master-only waiting-view header buttons "State folder..."
and "Debug log..." - one click opens the persisted state
home or the current trainer debug log in the platform file
manager / default handler; the pure `state_access.py` layer
with named `StateAccessRefusal` codes, every refusal in the
status line - never a dialog, never a crash); (reliability:
the field-observed transient "ReadProcessMemory failed
(Win32 error 299)" is now retried in `memory._read_exact`
with the bounded exponential backoff - transient set
{299, 119, 1116, 24}, exactly 4 attempts, backoff 0.05 ->
0.25 s; a partial result is never retried, the original
error is raised unchanged after the budget - closing the
documented open issue of the 0.38 ledger); +73 tests; full
main suite 4,833 OK / 30 expected skips; in-build suite
4,833 OK / 30 expected skips, `ce_inputs: []`; catalog zero
delta `blocked-catalog-039-autoload`; see the 0.39 section
below.
Superseded 0.38 (build
`native-20261109T211151Z-03e89050`, cut from `main` @ `da1e68f`,
2026-11-09) - the --force forced start for the
documented SteamOS state-lock dead end (the user-requested `--force`
startup parameter skips the state-lock safety prompts: a recoverable
stale state (dead state-lock owner) or unfinished receipts are
archived through the tested `perform_stale_recovery` path without a
confirmation dialog; the fence dead end (the plain `StateError` "A
recovery transaction owns this state", incl. the "state.lock already
exists" probe fallback) triggers the new bounded forced reclaim in the
pure `state_force.py` layer (`force_reclaim`): every recorded
trainer-side owner is probed with the tested process probe (one
observation, one retry on a transient "unknown"); a proven-alive
trainer-side owner is still refused with its named reason - the one
hard data-safety boundary that stays even under `--force` (the
`LiveStateConflict` path now refuses without the termination prompt);
every other case (proven-dead or unprovable owner) quarantines the
blocking artifacts (state.lock, recovery.lock, session.json,
state.json.tmp, oneshot.json.tmp, hook receipts / global-pool, this
trainer's shared claims) into a timestamped
`forced-recovery/<UTC stamp>-<trainer id>/` archive next to the state
folder with a full evidence document (`ct2trainer-forced-reclaim/v1`);
the saved `state.json` (the user's saved wishes) is always preserved;
debug-log events `state-force-recovered` / `-reclaimed` /
`-refused` / `-failed`; on Steam / SteamOS: `--force` in the launch
options so the Proton-wrapped trainer starts without any dialog);
+27 tests; full main suite 4,760 OK / 30 expected skips; in-build
suite 4,760 OK / 30 expected skips, `ce_inputs: []`; catalog zero
delta `blocked-catalog-038-force`; see the 0.38 section below.
Superseded 0.37 (build
`native-20261109T154005Z-4ad8e339`, cut from `main` @ `27dbf0d`,
2026-11-09) - Master Trainer per-table
process binding persistence MT-28 (the explicit process choice is
remembered per table - `table-attach.json` schema 1 under the state
home, keyed by the table content sha256 - the same identity as the
MT-24 analysis and the MT-27 notes documents, so a remembered
choice survives a rename and follows a content-identical file to
another root; a live remembered choice outranks the documented
smallest-PID rule in auto mode; in ask mode the picker still opens
(the documented contract) with the remembered row preselected so
the one-click attach is the remembered target; a stale or foreign
PID falls back to the ordinary attach decision; every picker
origin persists the choice (auto-load, explicit load, table
choice, re-attach after a detach - the attach origin addresses the
loaded table through the sidecar sha); a table without a content
sha cannot carry a binding (the documented MT-27 identity rule);
the MT-22 table-details window shows the "Remembered process"
row; zero load-path effect - the MT-9 gate re-checks the table
independently at load time); +68 tests; full main suite 4,733 OK /
30 expected skips; in-build suite 4,733 OK / 30 expected skips,
`ce_inputs: []`; catalog zero delta
`blocked-catalog-037-attach`; see the 0.37 section below.
Superseded 0.36 (build
`native-20261109T114726Z-15c3d9ab`, cut from `main` @ `d071884`,
2026-11-09) - Master Trainer multi-column
trainer grid MT-21 (the trainer row grid can run in up to three
side-by-side columns - the requested column count (1 / 2 / 3,
default 1) persists in the master state (master-settings.json
schema 8 -> 9, `grid_columns`) and is handed to the trainer window
on table load; the trainer header gains the "Columns: N" cycle
button (master only - the standalone trainer header stays
byte-identical and always renders the single column); a narrow
window renders fewer columns than requested (two columns need 652
px, three need 984 px, a column never falls below the 320 px
floor); a section with its children never splits across columns;
the pure grid layer in `ui_rows.py` (`build_grid` /
`effective_columns` / `column_layout` / `row_units` / `flow_units`,
`columns == 1` byte-stable against `build_rows`); per-column
pagination and per-column hit-testing (x picks the column, y the
row inside that column); +55 tests; full main suite 4,665 OK / 30
expected skips; in-build suite 4,665 OK / 30 expected skips,
`ce_inputs: []`; catalog zero delta
`blocked-catalog-036-grid`; see the 0.36 section below.
Superseded 0.35 (build
`native-20261109T054146Z-c5f18494`, cut from `main` @ `65d8fbe`,
2026-11-09) - Master Trainer per-table
notes / tags MT-27 (the waiting view gains the Note column - the
persisted per-table organization metadata: the note text truncated
to one line plus the tags in brackets, empty while no note exists;
the row context menu offers "Edit note..." between load and pin -
the small Toplevel with the note (multi-line, bounded at 500
characters) and a comma-separated tag entry (bounded at 8 tags x
40 characters); a named refusal at save time is shown in the
dialog's own label - the dialog stays open, the persisted document
is untouched; a table without a content sha (unreadable / never
scanned) is refused in the status line; the notes persist in
`table-notes.json` schema 1, under the state home, keyed by the
table content sha256 - the same identity as the MT-24 analysis
document, so a note survives a rename and follows a
content-identical file across roots; LRU-bounded to 1024 entries;
no master-state schema bump - the MT-24 sidecar precedent; the
waiting-view filter also matches the note text and tags
(`note_lookup`, backward-compatible); the MT-22 details window
shows the note / tag rows; zero load-path effect - the MT-9 gate
re-checks the table independently at load time); +67 tests; full
main suite 4,610 OK / 30 expected skips; in-build suite 4,610 OK /
30 expected skips, `ce_inputs: []`; catalog zero delta
`blocked-catalog-035-notes`; see the 0.35 section below.
Superseded 0.34 (build
`native-20261109T024143Z-a5457911`, cut from `main` @ `dc00343`,
2026-11-09) - Master Trainer multi-root
table index MT-26 (the Master indexes several table folders at once -
every root keeps the same (size, mtime_ns) + sha256 short-circuit
reconcile contract; the merged surface distinguishes tables by the
absolute table key (index root + relative path), the relative path
stays the documented single-root identity; the "Folders..." header
button opens the folder manager (add / remove / set primary, the
primary marked with a star, every action re-scans the indexed
roots, saves the index and restarts the auto-rescan clock); the
waiting view gains the Folder column; the folder list persists in
master-state schema 7 -> 8, `table_folders`, primary first, cap 8;
the tables index document is schema 1 -> 2 - one checksum-bound
root block per indexed folder; `run_master` multi-root folder
resolution: an explicit folder argument wins as the primary root
with the stored folders indexed behind it (casefold-deduped), a
parameterless start keeps the stored list (a missing stored folder
stays visible as a scan problem), only a genuinely first start
shows the picker (cancel exits 0), an explicit missing folder is
the documented exit-2 refusal; zero load-path effect - the MT-9
gate re-checks the table under its index root independently at load
time); +44 tests; full main suite 4,543 OK / 30
expected skips; in-build suite 4,543 OK / 30 expected skips,
`ce_inputs: []`; catalog zero delta
`blocked-catalog-034-mt26`; see the 0.34 section below.
Superseded 0.33 (build
`native-20261108T200230Z-b0167049`, cut from `main` @ `6e71739`,
2026-11-08) - Master Trainer table folder auto-rescan MT-25 (the
waiting view re-runs the existing incremental scan every 30 s while
the persisted "Auto-rescan: on" status-bar toggle is on - added /
changed / removed tables show up without a manual F5; the same
(size, mtime_ns) + sha256 short-circuit contract as the manual
Rescan, one stat pass per interval, polling only (no OS
file-watcher), paused on trainer entry; the interval clock restarts
on a manual rescan, a folder change, and the waiting-view rebuild;
zero load-path effect - the MT-9 gate re-checks the table
independently at load time; master-state schema 6 -> 7,
`auto_rescan`, default on); +16 tests; full main suite 4,499 OK / 30
expected skips; in-build suite 4,499 OK / 30 expected skips,
`ce_inputs: []`; catalog zero delta
`blocked-catalog-033-auto-rescan`; see the 0.33 section below.
Superseded 0.32 (build
`native-20261108T100731Z-a1d311e5`, cut from `main` @ `bfcc3a3`,
2026-11-08) - Master Trainer per-table entry count +
blocked count via background plan analysis MT-24 (the
waiting-view Entries / Blocked columns - the actionable and blocked
record counts of the plan compile, computed in one background daemon
thread through the tested `compile_table` plan path, persisted in
`table-analysis.json` keyed by the table content sha256 with an
LRU cap; the meta line shows the live "analyzing N table(s)" figure;
the details window gains the analysis block; a named compile failure
shows the failed marker); +69 tests; full main suite 4,483 OK / 30
expected skips; in-build suite 4,483 OK / 30 expected skips,
`ce_inputs: []`; catalog zero delta
`blocked-catalog-032-analysis`; see the 0.32 section below.
Superseded 0.31 (build
`native-20261105T080853Z-2e7f50a5`, cut from `main` @ `2def12f`,
2026-11-05) - Master Trainer per-table live status +
color coding + status filter MT-23 (the waiting-view Status column
shows the table's state right now - one bounded stat per visible row
per render against the index entry: ok / running / changed / missing
/ unreadable; row color coding; the persisted "Status: all / ok /
attention" header cycle, master-state schema 5 -> 6, `view_status`;
the pure `table_status.py` decision layer); +28 tests; full main
suite 4,414 OK / 30 expected skips; catalog zero delta
`blocked-catalog-031-status`; see the 0.31 section below.
Superseded 0.30 (build `native-20261104T131114Z-11522f68`, cut from
`main` @ `2fbca94`, 2026-11-04) - Master Trainer table details +
live load-gate preview MT-22 (right-clicking a waiting-view row
offers "Table details" first - the read-only inspection window with
the indexed facts for the table plus the on-demand load-gate
re-check, the same pass MT-9 runs at load time; the pure
`table_details.py` row builder); +16 tests; full main suite 4,386 OK
/ 30 expected skips; catalog zero delta `blocked-catalog-030-details`;
see the 0.30 section below. Superseded 0.29 (build
`native-20261104T094808Z-50af0517`, cut from `main` @ `de3e4ff`,
2026-11-04) - Master Trainer UI/UX revamp MT-19/20 (MT-19
trainer-focus mode: the whole waiting view lives in one container
frame destroyed on trainer entry - the trainer row grid owns the
full window, rebuilt whole on the way back; MT-20 discoverability:
the read-only "UI flow" header button - the in-app copy of the
reviewable UI.md, F5 re-scan, initial table-list focus, "Retry
load" in the status bar); +13 tests; full main suite 4,370 OK / 30
expected skips; catalog zero delta
`blocked-catalog-029-trainer-focus`; see the 0.29 section below.
Superseded 0.28 (build `native-20261103T161621Z-ea8fde2f`, cut from
`main` @ `d7f4cf0`, 2026-11-03) - Master Trainer
pinned/favorite tables MT-18 (`master-settings.json` schema 4 → 5:
the pin set - relative paths, most recent pin first, cap 25 -
persisted and restored at start; the row context menu toggle,
pinned tables float to the top of the list view and to the top of
their process group, the pin marker in the detail column); +15
tests; full main suite 4,357 OK / 30 expected skips; catalog zero
delta `blocked-catalog-028-pin`; see the 0.28 section below.
Superseded 0.27 (build `native-20261103T145543Z-b29b3688`, cut from
`main` @ `8aa0815`, 2026-11-03) - Master Trainer waiting-view
settings persistence MT-16 (`master-settings.json` schema 3 → 4:
the filter query, sort mode and view mode restored at start and
persisted on every change) + the process-grouped waiting view MT-17
(group-by-bound-process tree, display-only group rows); +22 tests;
full main suite 4,342 OK / 30 expected skips; catalog zero delta
`blocked-catalog-027-view`; see the 0.27 section below.
Superseded 0.26 (build `native-20261103T112811Z-59a6b3d5`, cut from
`main` @ `c114ec2`, 2026-11-03) - Master Trainer waiting-view
usability MT-13/14/15 (user request 2026-11-02/03, online-
evaluated: search/filter/sort through the new pure
`table_filter.py` layer, keyboard load flow, rolling recent tables
in `master-settings.json` schema 3 + Size/Modified/Last-used
columns), plus the live-target takeover field fix (stale-lock
recovery attaches to the still-running game behind one
user-confirmed prompt when the owner is proven dead and only
target-side identities remain unproven); +61 tests; full main
suite 4,320 OK / 30 expected skips; catalog zero delta
`blocked-catalog-026-master-ui`; see the 0.26 section below.
Superseded 0.25 (build `native-20261103T062439Z-f4c16be9`, cut from
`main` @ `a861bfb`, 2026-11-03) - Master Trainer user control
MT-10/11/12 (user request 2026-11-02: explicit table load, process
picker + persisted attach mode, detach/user attach), plus the online
feature evaluation record in `master_trainer/ROADMAP.md`, the Tcl
test-harness hardening (`tests/native_tk_teardown.py`, test-only),
and the in-build reliability fix (state-home isolation in the
`run_master` cancel test + explicit Tk variable masters in
`master_ui.py`, first in-build run
`native-20261102T181843Z-ddfb63f0` exposed the dependence); +66
tests; full main suite 4,259 OK / 30 expected skips; catalog zero
delta `blocked-catalog-025-master-ui`; see the 0.25 section below.
Superseded 0.24 (build
`native-20261102T102029Z-fe358e35`, cut from `main` @ `a2777ed`,
2026-11-02; trainer tick sounds, user field request 2026-11-01;
branch `native-0.24-trainer-sounds`; see the 0.24 section below).
**Latest verified release:** 0.43, build
`native-20261111T184600Z-3bf9d8aa` (cut from `main` @ `0df2607`,
2026-11-11): the 0.43 Master Trainer minimize-to-tray +
window-geometry persistence (MT-32/MT-33) + TGC field fix release -
in-build suite 5,011 OK / 36 expected skips, `ce_inputs: []`,
`runtime_unverified` deliberately kept per gate; source ZIP
`CT2Trainer-0.43-source.zip` sha256
`c0011d10a5a60b78067b0cdd1a622a134088fee325ac4d544efd3ec8101438ca`
(14,617,762 bytes) - carries the MT-32/MT-33 tray + geometry
(`master_trainer/tray.py` + `master_trainer/window_geometry.py` +
`tests/test_native_master_tray_geometry.py`) and the TGC field fix
(`memory.py` + `engine.py` + `hooks.py` +
`tests/test_native_tgc_field_fix.py`) - and portable ZIP
`CT2Trainer-0.43-windows-portable.zip` sha256
`dc7a4062b56be99ea887a77ffd23e7c2c1ff38935e471d7f124ed4d775a022e9`
(49,849,139 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`4846d7568ef4eba091261b21e678c13ab5cecbbf3468a0a57ba30d84fc7e91a4`,
17,072,494 bytes) ships next to the converter). Superseded 0.42, build
`native-20261111T044023Z-04112d15` (cut from `main` @ `377f760`,
2026-11-11): the 0.42 CE 7.5 cleanup parity + API-export registry
extension release - in-build suite 4,926 OK / 35 expected skips,
`ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
source ZIP `CT2Trainer-0.42-source.zip` sha256
`f44d248303b302b8621e80efc7c6faff476d0f27887b729546bf42c639839415`
(14,589,013 bytes) - carries the CE 7.5 cleanup parity
(`aa_program.py` + `compiler.py` +
`tests/test_native_aa_cleanup_parity.py`) and the API-export
registry extension (`sleep` / `showwindow`) - and portable ZIP
`CT2Trainer-0.42-windows-portable.zip` sha256
`305832ddc03487542c9a889e150b96f45c1576fa5e56819276da54b9388a5c40`
(49,821,481 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`35389c7611715b494418b2c5bcdbd48e84f8d55a55f3deab556c4aa4d6aefd1c`,
17,051,026 bytes) ships next to the converter). Superseded 0.41, build
`native-20261110T210856Z-5811040c` (cut from `main` @ `c724a7e`,
2026-11-10): the 0.41 AA typed-constant package +
digit-leading-label CE 7.5 parity fix release - in-build
suite 4,917 OK / 35 expected skips, `ce_inputs: []`,
`runtime_unverified` deliberately kept per gate; source ZIP
`CT2Trainer-0.41-source.zip` sha256
`05ef6cabca08adcca8a084722581b7d553966e480e28274a4a72f4b31b9c1964`
(14,580,191 bytes) - carries the AA typed-constant package
(`aa_program.py` +
`tests/test_native_aa_typed_constants.py`) and the
digit-leading-label CE 7.5 parity fix
(`tests/test_native_aa_digit_labels.py`) - and portable ZIP
`CT2Trainer-0.41-windows-portable.zip` sha256
`533bee676d0ed5c487741cb4919af8f4370f2bee1c5c26181ed5f3f0c3753a77`
(49,814,303 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`ce07c42cf22c57eeeffa08be74ff562d3a7dcfca5f4c2d14121c784acd24c6f`,
17,049,435 bytes) ships next to the converter). Superseded 0.40,
build
`native-20261110T093203Z-82c49872` (cut from `main` @ `e611e9e`,
2026-11-10): the 0.40 Master Trainer process identification
in picker + details (MT-31) + the bounded zero-transfer
transient-write retry in `memory.py` release - in-build
suite 4,879 OK / 35 expected skips, `ce_inputs: []`,
`runtime_unverified` deliberately kept per gate; source ZIP
`CT2Trainer-0.40-source.zip` sha256
`46ad5dd9f9adc872e320dd4aec2362e007020ae879bba0cc8fe0621e44c34c40`
(14,569,029 bytes) - carries the MT-31 process
identification (`process_watch.py` enrichment layer +
`tests/test_native_master_ui_mt31.py`) and the bounded
transient-write retry
(`tests/test_native_memory_write_retry.py`)
and the reviewable `master_trainer/UI.md` - and portable ZIP
`CT2Trainer-0.40-windows-portable.zip` sha256
`5075586c7b0f3251749c8e3e60ec0db7fea251db39190b59b63273a4e9b10bd6`
(49,809,535 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`52f6da1cebfc44a0dc791d4b5758112342b5a1d42c9fc9656901a16d1a5eb03f`,
17,048,910 bytes) ships next to the converter). Superseded 0.39,
build
`native-20261110T051241Z-57bf7d47` (cut from `main` @ `17a22f7`,
2026-11-10): the 0.39 Master Trainer per-table auto-load
policy (MT-29) + state folder / debug log quick access
(MT-30) + the bounded transient-read retry in `memory.py`
release - in-build suite 4,833 OK / 30 expected skips,
`ce_inputs: []`, `runtime_unverified` deliberately kept per
gate; source ZIP `CT2Trainer-0.39-source.zip` sha256
`14163e7475477c177be339d06fd5ba7b9a7016667405669b084faed25035a923`
(14,549,960 bytes) - carries the MT-29 auto-load policy
(`table_autoload.py` pure layer + `table-autoload.json` schema 1,
`tests/test_native_master_autoload.py` +
`tests/test_native_master_ui_mt29.py`), the MT-30 state folder /
debug log quick access (`state_access.py` pure layer,
`tests/test_native_master_ui_mt30.py`) and the bounded
transient-read retry (`tests/test_native_memory_read_retry.py`)
and the reviewable `master_trainer/UI.md` - and portable ZIP
`CT2Trainer-0.39-windows-portable.zip` sha256
`7d5d7903f1be5df0eac0f1067d5c2ca596321a41ea37381e033e5deb175ec8b6`
(49,800,752 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`e0db5b2e2f41ec816089486ca57a2c0b1424523e7ee8450335053923ab629e47`,
17,042,819 bytes) ships next to the converter). Superseded 0.38,
build
`native-20261109T211151Z-03e89050` (cut from `main` @ `da1e68f`,
2026-11-09): the 0.38 --force forced start for the documented
SteamOS state-lock dead end release - in-build suite 4,760 OK /
30 expected skips, `ce_inputs: []`, `runtime_unverified`
deliberately kept per gate; source ZIP
`CT2Trainer-0.38-source.zip` sha256
`e2b466adc7abfb191bbd2b50f8304739a1e82cbf487099d4ecd6fd77cc3f3d0c`
(14,521,497 bytes) - carries the --force forced start
(`state_force.py` pure layer + the `force_reclaim` quarantine
archive, `tests/test_native_state_force.py` +
`tests/test_native_master_force.py` + the force-flow tests in
`tests/test_native_ui_recovery_flow.py`) and the reviewable
`master_trainer/UI.md` - and portable ZIP
`CT2Trainer-0.38-windows-portable.zip` sha256
`df5ccfa373c8f5deb6be85f36e75941a1c0b3a9f13afae23c03f1644f9290fc4`
(49,781,948 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`5d2cc5544eb6a29f1c3283f05e809e392d0038a1f59456c9d52f0356e519231d`,
17,026,316 bytes) ships next to the converter). Superseded 0.37,
build
`native-20261109T154005Z-4ad8e339` (cut from `main` @ `27dbf0d`,
2026-11-09): the 0.37 Master Trainer per-table process
binding persistence release (MT-28) - in-build suite 4,733 OK /
30 expected skips, `ce_inputs: []`, `runtime_unverified`
deliberately kept per gate; source ZIP
`CT2Trainer-0.37-source.zip` sha256
`a49bdd7d738de9551a1d971430ed9f7b0a212ec0d4a2afd8667e1f87ec61d301`
(14,506,715 bytes) - carries the MT-28 per-table process
binding persistence (`table_attach.py` pure layer +
`table-attach.json` schema 1,
`tests/test_native_master_attach.py` +
`tests/test_native_master_ui_mt28.py`) and the reviewable
`master_trainer/UI.md` - and portable ZIP
`CT2Trainer-0.37-windows-portable.zip` sha256
`5cdb23b24c0757cb047ddd72ae673614fc6bccee960747079849fe325785c3ce`
(49,762,223 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`c2a1a6948fa28248d36a6defa5a116867620261e55bdcfe1e144cd301060a9de`,
17,017,090 bytes) ships next to the converter). Superseded 0.36,
build `native-20261109T114726Z-15c3d9ab` (cut from `main` @
`d071884`, 2026-11-09): the 0.36 Master Trainer multi-column
trainer grid release (MT-21) - in-build suite 4,665 OK / 30 expected
skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per
gate; source ZIP `CT2Trainer-0.36-source.zip` sha256
`79464f02cd71492763656ca0ff3283a240c3579b9f52df3bcc18857dabb3d1be`
(14,490,858 bytes) - carries the MT-21 multi-column trainer grid
(`ui_rows.py` grid pure layer + `master_state.py` schema 9,
`tests/test_native_ui_grid.py` +
`tests/test_native_master_ui_mt21.py`) and the reviewable
`master_trainer/UI.md` - and portable ZIP
`CT2Trainer-0.36-windows-portable.zip` sha256
`089fc92b0c5758ba758fdc88bb92e11d8e3b3e36c28d04231f27b3eeaecceac0`
(49,751,886 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`07ebef319b55d686c4f76cdb6f07440a2b4934fc8943f9f72b402d62c4c49fe8`,
17,006,463 bytes) ships next to the converter). Superseded 0.35,
build `native-20261109T054146Z-c5f18494` (cut from `main` @
`65d8fbe`, 2026-11-09): the 0.35 Master Trainer per-table notes /
tags release (MT-27) - in-build suite 4,610 OK / 30 expected
skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per
gate; source ZIP `CT2Trainer-0.35-source.zip` sha256
`575ee8ad6f0864bd8ff39f3ae547bb629d5c128938cff792e9c4fb7362fbcdac`
(14,474,384 bytes) - carries the MT-27 per-table notes / tags
(`table_notes.py` pure layer + `table-notes.json` schema 1,
the Note column, the "Edit note..." editor,
`tests/test_native_master_notes.py`) and the reviewable
`master_trainer/UI.md` - and portable ZIP
`CT2Trainer-0.35-windows-portable.zip` sha256
`488d7453ca0433f843c1e46a2241142347aa2ee41390ed334d6068ed30e42d34`
(49,737,899 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`0c53908c267746cabd74e1ef091daa35d31eb94c4d0accc6401085d7e8c59ccc`,
16,999,124 bytes) ships next to the converter). Superseded 0.34,
build `native-20261109T024143Z-a5457911` (cut from `main` @
`dc00343`,
2026-11-09): the 0.34 Master Trainer multi-root table index
release (MT-26) - in-build suite 4,543 OK / 30 expected
skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per
gate; source ZIP `CT2Trainer-0.34-source.zip` sha256
`0d0a0849a90171f64eaf5b55ec06ec1d9117d02d5330895dcb4279e26f73b0f5`
(14,455,170 bytes) - carries the MT-26 multi-root table index
(`table_index.py` `RootIndexSet` + schema-2 index set,
`master_state.py` schema 8, `tests/test_native_master_ui_mt26.py`)
and the reviewable `master_trainer/UI.md` - and portable ZIP
`CT2Trainer-0.34-windows-portable.zip` sha256
`ade1ecc520ddbeaf6886e1b195fc6e2886a5f9cbeaa64b15f9ac5679420f5054`
(49,719,386 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`606ea2287eb9f787308d862c18209076ee42e4f7a4ae88fcb93bf8f22edcb6f6`,
16,983,514 bytes) ships next to the converter). Superseded 0.33,
build `native-20261108T200230Z-b0167049` (cut from `main` @
`6e71739`, 2026-11-08): the 0.33 Master Trainer table folder
auto-rescan release (MT-25) - in-build suite 4,499 OK / 30
expected skips, `ce_inputs: []`, `runtime_unverified` deliberately
kept per gate; source ZIP `CT2Trainer-0.33-source.zip` sha256
`4528d1d0f2ee269fb2ee7ec470d9e9711b3c284bffe6cf582f7dafa7431756f2`
(14,433,388 bytes) - carries the MT-25 auto-rescan
(`master_state.py` schema 7, the 30 s auto-rescan tick,
`tests/test_native_master_ui_mt25.py`) and the reviewable
`master_trainer/UI.md` - and portable ZIP
`CT2Trainer-0.33-windows-portable.zip` sha256
`5e0244791b6f31a2e2219d5c33541c978ca4c0d399c8e7a234cb0c16e8ccb3d7`
(49,703,149 bytes; the frozen `CT2Trainer-Master.exe` (sha256
`59961d511d3964b075c968a3c577117ffa235970d65976f66d7e34e0eae010a9`,
16,968,879 bytes) ships next to the converter). Superseded 0.32,
build `native-20261108T100731Z-a1d311e5` (cut from `main` @
`bfcc3a3`, 2026-11-08): the 0.32 Master Trainer per-table entry
count +
blocked count (background plan analysis) release (MT-24) - in-build
suite 4,483 OK / 30 expected skips,
`ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
source ZIP `CT2Trainer-0.32-source.zip` sha256
`f6cae57590d083e37308bc4a03b1046b8186617bdb0f98c88c9bc324404493d9`
(14,426,224 bytes), portable ZIP
`CT2Trainer-0.32-windows-portable.zip` sha256
`3a7980ba04f60f7cb93edce3cf5c723ba609ff55a00b1f866079101d3b7bc986`
(49,699,633 bytes), frozen `CT2Trainer-Master.exe` (sha256
`6dc34408c8e5ecec1c2215c45da27ea22cc5c5ce5a9629267778b172d44d3485`,
16,966,114 bytes) next to the converter. Superseded 0.31, build
`native-20261105T080853Z-2e7f50a5` (cut from `main` @ `2def12f`,
2026-11-05): the 0.31 Master Trainer per-table live status +
color coding + status filter release (MT-23) - in-build
suite 4,414 OK / 30 expected skips,
`ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
source ZIP `CT2Trainer-0.31-source.zip` sha256
`3bab9648208f6ed4cbafa919991cab19c7921597ac2075c5c8b964e17258c0f9`
(14,398,817 bytes), portable ZIP
`CT2Trainer-0.31-windows-portable.zip` sha256
`df5581ec5e8b0c0b99abdf35b914f08ec138b4470234b48c615304419a970839`
(49,679,202 bytes), frozen `CT2Trainer-Master.exe` (sha256
`811c0f85c143b632dd182646282ddb32c3293513a665eb62c8055f74f9c89dcb`)
next to the converter. Superseded 0.30, build
`native-20261104T131114Z-11522f68` (cut from `main` @ `2fbca94`,
2026-11-04): the 0.30 Master Trainer table details + live
load-gate preview release (MT-22) - in-build
suite 4,386 OK / 30 expected skips,
`ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
source ZIP `CT2Trainer-0.30-source.zip` sha256
`091b379c132e277c19f519705dcccc4c0817e8e7e614e5baf2f14bbe3fe414a3`
(14,387,690 bytes), portable ZIP
`CT2Trainer-0.30-windows-portable.zip` sha256
`f4476bb08e3e65e6db9cd35bfe7a72408a555b8525bd6a10f8b794f943083d54`
(49,669,933 bytes), frozen `CT2Trainer-Master.exe` (sha256
`9d0a525a78dfbfffb906261ad42e435c5414cb6cb0189dd78c73910063f67643`)
next to the converter. Superseded 0.29, build
`native-20261104T094808Z-50af0517` (cut from `main` @ `de3e4ff`,
2026-11-04): the 0.29 Master Trainer UI/UX revamp release
(MT-19 trainer-focus mode + MT-20 discoverability) - in-build
suite 4,370 OK / 30 expected skips,
`ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
source ZIP `CT2Trainer-0.29-source.zip` sha256
`2f5ce6e446f8d9885cd653580b5e194a2a0fc524eba7b5f684fe1f1a0e1da3d4`
(14,378,934 bytes), portable ZIP
`CT2Trainer-0.29-windows-portable.zip` sha256
`98c63c368bc2cccd68335e9db94a3b897abbbb815730c97912e3068805fad226`
(49,667,528 bytes), frozen `CT2Trainer-Master.exe` (sha256
`88e6ee99aa4c46973945e462ca956977e9942a1e8b30630aa2570107540f2de8`)
next to the converter. Superseded 0.28, build
`native-20261103T161621Z-ea8fde2f` (cut from `main` @ `d7f4cf0`,
2026-11-03): the 0.28 Master Trainer pinned/favorite tables release
(MT-18) - in-build suite 4,357 OK / 30 expected skips,
`ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
source ZIP `CT2Trainer-0.28-source.zip` sha256
`13f4b2222a83f9e4588d388b4120beaf8018a091a05364029ae2a950c0dabb1a`
(14,363,765 bytes), portable ZIP
`CT2Trainer-0.28-windows-portable.zip` sha256
`d656835a69ece75ff6adaa5ce766385327fb9ec08d89837ad772425dafe91ce3`
(49,658,473 bytes), frozen `CT2Trainer-Master.exe` (sha256
`c12dcea5bb8a609dae4df36f44827ab5269c9e1015cb723067ed98dc100bf99b`)
next to the converter. Superseded 0.27, build
`native-20261103T145543Z-b29b3688` (cut from `main` @ `8aa0815`,
2026-11-03): the 0.27 Master Trainer waiting-view settings release
(MT-16/17) - in-build suite
4,342 OK / 30 expected skips, `ce_inputs: []`,
`runtime_unverified` deliberately kept per gate; source ZIP
`CT2Trainer-0.27-source.zip` sha256
`264b42d6c42dac1bb434c1d0591e82ac0bec69e61e1a1c75047c6aa58126f40e`
(14,357,294 bytes), portable ZIP
`CT2Trainer-0.27-windows-portable.zip` sha256
`bfcf2abc885122dfa8653fcfd0046323e7112f59c0850958688e36e014ebc135`
(49,654,613 bytes), frozen `CT2Trainer-Master.exe` (sha256
`9762c8bdc2298c16bd82779f206d9a885a449261a6428187c3bd2155fc5bf1bc`)
next to the converter. Superseded 0.26, build
`native-20261103T112811Z-59a6b3d5` (cut from `main` @ `c114ec2`,
2026-11-03): the 0.26 Master Trainer waiting-view usability release
(MT-13/14/15 + live-target takeover field fix) - in-build suite
4,320 OK / 30 expected skips, `ce_inputs: []`,
`runtime_unverified` deliberately kept per gate; source ZIP
`CT2Trainer-0.26-source.zip` sha256
`3d62f80cdfb95d8439d4a2f2150002976795faad313fa75d47aeb4fb92bb49bd`
(14,348,462 bytes), portable ZIP
`CT2Trainer-0.26-windows-portable.zip` sha256
`49be1d286999ed175737edb073c5ab83533c40cccc7e636685a256a0b07004b3`
(49,653,968 bytes), frozen `CT2Trainer-Master.exe` (sha256
`895f937ed5c228c09b97edba28aa9dc4ad228abd58585f73080f40ab265bc031`)
next to the converter. Superseded 0.25, build
`native-20261103T062439Z-f4c16be9` (cut from `main` @ `a861bfb`,
2026-11-03): the 0.25 Master Trainer user-control release
(MT-10/11/12 + Tcl test-harness hardening + in-build reliability fix)
- in-build suite 4,259 OK / 30 expected skips, `ce_inputs: []`,
`runtime_unverified` deliberately kept per gate; source ZIP
`CT2Trainer-0.25-source.zip` sha256
`64f8c3082cff50687b1962234c17a82e2a2f0c19eb1112ece06a0a25132f35be`
(14,324,774 bytes), portable ZIP
`CT2Trainer-0.25-windows-portable.zip` sha256
`774266f7e2c9dc69f4d8cfc963309b9907442ec6b5343ff629b9e30c04049653`
(49,633,196 bytes), frozen `CT2Trainer-Master.exe` (sha256
`8736f73e762b57a8f337bf8fa04c2c16f8622c4d99e7dd7f2167b2c9999e3d8f`)
next to the converter. Superseded 0.24, build
`native-20261102T102029Z-fe358e35` (built from `main` at `a2777ed`,
2026-11-02): the 0.24 trainer tick sounds release (see the 0.24
section below) - in-build suite 4,193 OK / 30 expected skips,
`ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
source ZIP `CT2Trainer-0.24-source.zip` sha256
`dfdd8cfcca90a2789bf544d8f8de4e34941067feeb2b32ce8d550f98e5bc4eb6`
(14,298,696 bytes), portable ZIP
`CT2Trainer-0.24-windows-portable.zip` sha256
`12262cf16e906c3811ade0a8c582b7a1057c834a3110aff004dfd13b3067e7ab`
(49,618,009 bytes), frozen `CT2Trainer-Master.exe` (sha256
`5f3a66400c2c1775e6fc50ad6bbbc36aa8a6bcf8b58fe56507117dc33683494d`)
next to the converter. Superseded 0.23, build
`native-20261101T145310Z-a160bae4` (built from `main` at `6e3ec98`,
2026-11-01): the 0.23 Master Trainer roadmap release - MT-6/MT-7/
MT-8/MT-9 (frozen `CT2Trainer-Master.exe` now part of every build,
per-table settings sidecar, documented SteamOS/CheatDeck route,
load-time table compatibility & size gate with graceful named load
failures), waiting-view observability, ask-on-first-start
table-folder parameter, plus the same-day field fixes (placeholder
headings no longer create plan-level symbol dependencies; SC2
hotkey-bridge field fix from the 0.22.1 lane) - see the 0.23 section
below. In-build suite 4,176 OK / 30 expected skips, `ce_inputs: []`,
`runtime_unverified` deliberately kept per gate. Superseded 0.22,
build `native-20261101T075049Z-f32c112d` (built from `main` at
`2b24a1c`, 2026-11-01): the 0.22 FO4 field-fix cycle release -
bounded automatic re-arm of ScanMiss enable failures (30 s x 10
attempts, budget reset per (re-)attach, armed set survives target
exit) plus manual "Try again" / "Re-attach" actions (merge `a12a0b6`,
+17 tests; zero catalog delta `blocked-catalog-022-rearm`; the SC2
0.19 hotkey-bridge field findings are recorded in the section below -
the fix itself ships in 0.23 via the 0.22.1 lane). In-build suite
4,061 OK / 30 expected skips, `ce_inputs: []`,
`runtime_unverified` deliberately kept per gate.
Superseded 0.21, build
`native-20261031T211046Z-14707e12` (built from `main` at `9a725a8`,
2026-10-31): the 0.21 feature release - RT-5 complete (item B
CheatCodes code-patch plan path, merge `9ef4a74`, +26 tests, catalog
remeasure `blocked-catalog-020-rt5-be`: 117,634 -> 117,809 total,
116,581 -> 116,756 supported, 1,053 blocked, 60,161 staged, 0 load
errors, zero newly blocked; item E `messageDialog` safe logged no-op,
merge `b8bb4ee`, +22 tests, zero catalog delta
(`blocked-catalog-rt5e-iteme`)) plus the new Master Trainer (one
long-lived trainer window: incremental folder table index,
cross-platform process watch, unique-match auto-load / multi-table
picker, handoff into the exact standalone trainer UI, per-table on/off
persistence; MT-1..MT-5, 141 tests - see the Master Trainer section
below). In-build suite 4,044 OK / 30 expected skips, `ce_inputs: []`,
`runtime_unverified` deliberately kept per gate. Superseded 0.20.1,
build
`native-20261031T104114Z-d64ae4c2` (built from `main` at `080128c`,
2026-10-31): the 0.20.1 release-content re-cut of the 0.20 branding-icon
release - the 0.20 changelog suite line now states the verified in-build
suite (3,854 OK / 26 expected skips, fully green at the canonical build
path) and cites catalog remeasure `blocked-catalog-020-icons` (zero delta
vs `blocked-catalog-019-field`); no code or asset changes; in-build suite
3,854 OK / 26 expected skips, `ce_inputs: []`, `runtime_unverified`
deliberately kept per gate. Superseded 0.20, build
`native-20261030T184820Z-b9d6dc07` (built from `main` at `6298803`,
2026-10-30): the branding-icon release - the user-provided
`CT2Trainer_Generator` icon set for the CT2Trainer tool (embedded in the
frozen `CT2Trainer-Converter.exe` via PyInstaller `--icon`; converter
window via `window_icon_path("converter")`) and the `Standalone_Trainer`
icon set embedded in the `CT2Trainer-Template` stub so every generated
trainer .exe carries it (trainer window via `window_icon_path("trainer")`);
1024x1024 PNG masters committed as reference, multi-size ICOs (16-256 px,
32 bpp) rebuilt by the rewritten `tools/create_icons.py` (Pillow is
local-only, outside the offline wheels), `tests/test_native_icons.py` +4;
suite 3,854 OK / 26 expected skips, zero catalog delta vs
`blocked-catalog-019-field` (151/117,634/60,161/1,053/0 load errors),
`ce_inputs: []`, `runtime_unverified` deliberately kept per gate (the
first 0.20 cut, `native-20261030T183527Z-8f2cb20a`, was cut from the
wrong branch - duplicate 0.19 ZIPs without icons - and deleted before
recording). Superseded 0.19, build
`native-20261030T121918Z-c72dbb38` (built from `main` at `fbe626f`,
2026-10-30): the 0.19 field-fix cycle - hotkey-bridge Windows AV fix
(HWND_MESSAGE corrected to -3; explicit Win32 argtypes/restype on all
bridge prototypes; RegisterHotKeyW/UnregisterHotKeyW guarded for
stripped user32 builds; +1 real-seam regression test), value-read
observability (`read_value` logs `value-read-failed` per identifier
per cause, dedup, re-raise), the new `describe` CLI subcommand (raw
source + plain-language assessment + concrete trainer actions per
record, +13 tests), and full staged-options support for the South of
Midnight table (plan-level staging, engine gates and the two-level
parent cascade proven correct by new tests; UI gaps closed:
staged-pending value rows now refuse immediately in the status line
with the engine's named provider refusal, and `moAlwaysHideChildren`
passes through as the `hidden_children` plan marker with row-model
subtree suppression - the flagged parent row stays the interface);
+24 tests, suite 3,850 OK / 26 expected skips, zero catalog delta vs
`blocked-catalog-rt5d-main` (151/117,634/60,161/1,053/0 load errors),
`ce_inputs: []`, `runtime_unverified` deliberately kept per gate.
Superseded 0.18, build
`native-20261028T131208Z-55922918` (built from `main` at `70c5a61`,
2026-10-28): the trainer UI row-details window - right-click /
long-press on a row now offers "Row details" leading the context menu,
a single read-only window combining the raw script source (static Auto
Assembler / embedded Lua / global program / normalized operation list),
the plain-language assessment (what it does / what is known) and the
concrete actions the trainer performs for the entry (new pure builders
`entry_actions` / `row_details` / `lua_apis_used` in
`ui_script_view.py`, +22 tests in
`tests/test_native_ui_row_details.py`); in-build suite 3,767 OK / 25
expected skips, `ce_inputs: []`, `runtime_unverified` deliberately kept
per gate. Superseded: 0.17, build
`native-20261027T094839Z-ec6c6f55` (built from `main` at `ee41630`,
2026-10-27): the RT-4.2 runtime provider model (last RT-4 package;
catalog remeasure `blocked-catalog-rt42-main`: 1,351 -> 1,053
blocked, 298 rows unblocked, zero newly blocked, 28 reason-only
changes) on top of the 0.16.4 content, the RT-4.3
address-expression & identifier-dialect merge (2026-10-26,
merge `cd3217d`): O1 relative-address skip-fold + O9 runtime-base
staging, O3 pointer-offset expression slots, O10 identifier dialect,
O23 token-named quoted-atom refusal, O27/O4 Type:Member managed
labels, O13 directive-aware db/dw/dd/dq string bytes — catalog
remeasure `blocked-catalog-rt43-main`: 1,743 -> 1,351 blocked of
117,634, zero newly blocked rows; plus the RT-5 item G
createThread/threadWait gate decision (2026-10-26, merge `2de9c0e`):
option (2) recorded — capability gate stays, no thread backend ships
this milestone, byte-stable five-stage gate pins
`tests/test_native_rt5_thread_gate.py` +17, tests only, zero catalog
movement (`blocked-catalog-rt5g-main` zero delta); plus the RT-5 item F
no-effect register ratification (2026-10-26, merge `966fccd`,
tests-only: the inventory section-8 no-effect/out-of-scope register
pinned as a byte-stable contract,
`tests/test_native_rt5_no_effect_register.py` +22, zero catalog
movement, `blocked-catalog-rt5f-main` zero delta); plus the RT-5 item A
embedded `<Files>` extraction & Lua surface (2026-10-28, merge `479977c`):
new `src/ct2trainer/native/embedded_files.py` dual-branch codec (CE-alphabet
Ascii85 + 4-byte-LE size prefix; hex read-until-EOF for other/missing
`Encoding`), fail-closed table-load decode, `findTableFile`/`readStringLocal`/
stringstream/stringlist surface, +53 tests; zero catalog delta
(`blocked-catalog-rt5a-main`), full main suite 3,745 OK / 25 expected
skips; plus the RT-5 item C bounded process-info Lua API family
(2026-10-28, commit `0167825`): 11 CE 7.5 process-info APIs under the
clean-room single-target model (getProcessIDFromProcessName,
getProcessList, getAutoAttachList, getOpenedProcessID, getSettings,
integerToUserData, targetIs64Bit, enumModules, disassemble,
stringlist_add, getCEVersion pinned '7.5'), item-A-style allowlist
wiring, +23 tests; zero catalog delta (`blocked-catalog-rt5c-main`), full
main suite 3,790 OK / 25 expected skips; plus the RT-5 item C2 dynamic
addresslist records + custom AA directives (2026-10-29, merge
`dde9f04`): createMemoryRecord session journal (IDs >= 2**31, never
persisted, cleared on target exit), CE MemoryRecord runtime surface
(Description/Type/Address/Script/Parent/Child/Offset/OffsetText/Value
vtByte..vtDouble), journal + plan OnActivate/OnDeactivate callbacks,
getCEVersion number 7.5 (item-C string pin superseded), addresslist
getMemoryRecord/Count/MemoryRecord[i] lookups,
registerAutoAssemblerCommand custom AA directives (table scope, built-in
names refused), `tests/test_native_rt5_dynamic_records.py` +27; zero
catalog delta (`blocked-catalog-rt5c2-main`), full main suite 3,817 OK /
25 expected skips; plus the RT-5 item D onOpenProcess/onTableLoad
callback dispatch (2026-10-29, merge `9294bb8`): CE-sequence
table-scope dispatch after a clean table-Lua bootstrap (onOpenProcess
with the attached target PID, onTableLoad with the Lua literal false -
documented bounded deviation: no before-load phase), pcall-wrapped
dispatch chunks with literal argument injection, 'absent'/'ok'/
'error: <msg>' -> no event / table-callback / table-callback-error,
throwing-callback containment with plan byte-identity, idempotent per
confirmed attach with re-attach re-fire,
`tests/test_native_rt5_table_callbacks.py` +9; zero catalog delta
(`blocked-catalog-rt5d-main`), full main suite 3,826 OK / 25 expected
skips. RT-4 is complete; RT-5 items A, C, C2 and D are the
first implementation items landed. The 0.17 in-build suite:
3,692 OK / 25 expected skips, `ce_inputs: []`.
Superseded: 0.16.4, build
`native-20261024T003853Z-a8cf04fc` (built from `main` at `988ff8e`,
2026-10-24): the Sinking City 2 trainer-crash-observability field fix
(from the 0.16.3 field test: the windowed trainer process died
silently mid wish-restore with zero follow-up log events and the
restart was blocked by the correct state-lock refusal while the game
was alive; `arm_crash_reporting()` now sinks
excepthook/threading-hook/faulthandler evidence into the opt-in debug
log, `TrainerWindow.poll` fails closed instead of letting an exception
kill the windowed process, and the restore loop logs
`restore-entry-start` per wish; state-lock fail-closed behavior
unchanged) on top of the 0.16.3 content, the RT-4.4 value-semantics,
the RT-4.6 input-legacy and the RT-4.5 AA-directive merges (catalog
remeasure `blocked-catalog-rt45main`: 1,743 blocked of 117,634, zero
newly blocked rows). Superseded: 0.16.3, build
`native-20261023T065015Z-afbc3eba` (built from `main` at `6a5ba63`,
2026-10-23) - the Sinking City 2 activation field fix (two root
causes from the 0.16.2 field test: the recovery assessment still
rejected the WP-47/55 hook-journal `value_data_ranges` field on
every allocation entry, blocking startup behind a stale
`state.lock` on every attempt; and the module-snapshot retry
targeted the wrong Win32 code without backoff, so the transient
failure while the game was still loading DLLs was never retried -
now a bounded 8-attempt exponential-backoff retry on {1116, 24, 119}
with the architecture-aware fallback flag and the journal field
validated with the writer contract) on top of the 0.16.2 content;
user-tested, field finding: the 0.16.3 Sinking City 2 field test
found the silent mid-restore death above (ledger). Superseded:
0.16.2, build
`native-20261022T160328Z-0423fb21` (built from `main` at `68eeb00`,
2026-10-22) - the Sinking City 2 startup-block field fix (recovery
assessment accepts the WP-57 hook-journal `captured_placeholders`
field, which had blocked recovery behind a stale `state.lock`) plus
RT-4.1 symbol provider fidelity (keep-first duplicate-provider
policy, `label()` duplicate-name tolerance, wildcard-cleanup
scoping, catalog remeasure 2,698 -> 1,858 blocked of 117,624, zero
unexplained supported regressions); user-tested, field finding: the
0.16.2 Sinking City 2 field test found the activation failure above
(ledger). Superseded:
0.16.1, build
`native-20261021T161241Z-b0566a25` (built from `main` at `d1c61f2`,
2026-10-21) - Sinking City 2 table-load warnings made accurate + new
versioning rule (every build gets a new version number, bug fixes bump
the patch); user-tested, field finding: the 0.16.1 Sinking City 2
field test found the startup block above (ledger).

**0.21 Master Trainer (2026-10-31, released in build
`native-20261031T211046Z-14707e12` cut from `main` at `9a725a8`;
branch `native-0.20-master-trainer` merged into `main`):** one
long-lived trainer
window configured with a folder of `.ct` tables — incremental,
checksum-bound table index (folder + sub-folders; only the folder is
listed per reconcile, changed files re-read), cross-platform process
watch (Toolhelp32 on Windows, `/proc/<pid>/exe` on Linux/SteamOS),
auto-load of the unique matching table, table picker when several bind
one process, switch into the exact standalone `TrainerWindow` with a
`master_back` button, per-table on/off persistence via the existing
engine state store, pure UI-free orchestrator, `ct2trainer native
master` CLI and the user-provided `Master_Trainer` icon
(`window_icon_path("master")`). 141 new tests plus the three-kind icon
contract; four source bugs found and fixed during test-lane
development. In-build suite on the 0.21 build: 4,044 OK / 30 expected
skips, 0 failures (fully green at the canonical build path, incl.
the 3 path-dependent baseline-reproducibility tests); catalog
unchanged (zero Master Trainer effect; latest remeasure
`blocked-catalog-020-rt5-be`).

**0.22 field cycle (2026-11-01): FO4 re-arm + SC2 hotkey-bridge
findings (released in build `native-20261101T075049Z-f32c112d`).**
Field tests 2026-10-30/31: Fallout 4 (0.20, Steam Deck /
Proton) and The Sinking City 2 (0.19; Windows x2 + Deck x1); debug
logs kept local-only (clean-room rule).

- **FO4 (0.20, Deck, 2026-10-31 13:37-13:45 UTC, target pid 696):** 8
  auto-on wishes queued pre-attach, auto-attach OK, but 6 of 8 wish
  restores failed `ScanMiss` while the game was still loading (43 OK;
  1052 AOB first match OK then second ScanMiss); 15+ manual taps all
  ScanMiss; value-read failures on 8 identifiers while the engine
  loaded (expected - unresolved pointer chains; 0.19
  `value-read-failed` observability covers them). Shipped fix: bounded
  automatic re-arm (30 s x 10 attempts, armed by any ScanMiss enable
  failure, budget reset per (re-)attach, armed set survives target
  exit) + manual "Try again" row action + top-level "Re-attach"
  button; `tests/test_native_rearm.py` (+17). Catalog zero delta
  (`blocked-catalog-022-rearm`).
- **SC2 (0.19, 3 sessions) hotkey-bridge defects - NOT fixed in 0.22**
  (hotkey-bridge code unchanged; next field-fix cycle):
  (1) the missing-`RegisterHotKeyW` guard flag set in
  `hotkey_bridge.py:343-351` is never checked by `register_hotkey`
  (:404) / `unregister_hotkey` (:408) -> raw `AttributeError` instead
  of the named non-blocking `HotkeyRegistrationError`; (2) the error
  escapes toggle/poll and hard-blocks the whole engine - S1 entry 198
  shows `toggle-ok` **and** `toggle-failed` (the programmatic enable
  had succeeded), and S2's `poll-crashed` -> `engine-blocked` then
  refuses every toggle incl. `close()`; (3) deterministic close
  failure on every platform (S1/S2 Windows + S3 Deck): the bridge
  window is created on the main thread (`connect()`, :381) while the
  loop thread (:393, `GetMessageW(NULL)`) pumps its own empty queue,
  so `WM_BRIDGE_QUIT` is only deliverable on the main thread, but
  `destroy()` (:415) blocks that thread in `join(timeout=5.0)` ->
  guaranteed 5 s timeout ("hotkey bridge message loop did not stop
  within 5s") -> `DestroyWindow` never reached -> daemon loop thread
  AVs in `GetMessageW` during process teardown (3x) -> state lock
  survives the crash.
- **Other findings:** transient-read `PatchConflict` (Win32 299,
  `ReadProcessMemory failed`) ~1 h after attach (S1 22:19:19) - a
  transient read error must not become a receipt change; state-lock
  first-restart refusal ("not proven dead in both observations
  (absent)") although both dead PIDs were absent, second start
  recovered via `StaleStateRecoverable` (S2 12:31); wish persisted
  before `toggle-failed` (S1 entry 198) - violates the "only confirmed
  ON-switches are persisted" rule.
- **Open field verification:** no `WM_HOTKEY` dispatch observed in
  either log yet - next field test should press a bound hotkey and
  expect the `hotkey-*` events.

**0.24 content on main (2026-11-01, branch
`native-0.24-trainer-sounds`): trainer tick sounds (user field
request 2026-11-01).** The generated trainer now plays the tick
sounds of the original native trainer generator's character: a
distinct double tick on a confirmed (re-)attach to the game process,
and a high/low single tick on every confirmed on/off toggle of an
item (manual row switch, group heading toggle, and hotkey-dispatched
activation toggles - CE parity: the original generated trainer
sounds on every toggle, not only UI taps).  Behavior reference
(read-only, never copied): CE 7.5's native trainer generator ships
two built-in tick sounds (`Sounds.RC` registers `tick1.wav` /
`tick2.wav` as the `BUILDIN_ACTIVATE` / `BUILDIN_DEACTIVATE` RCDATA
resources; measured ~28 ms, 8-bit unsigned mono, 11025 Hz, ~4.4 kHz
activate / ~3.8 kHz deactivate, played through Win32 winmm
`PlaySound` with `SND_MEMORY | SND_ASYNC`).  The reference corpus
carries no table-embedded audio files, so that built-in pair is the
original sound set.  Clean-room: the ticks are synthesized
deterministically in code in the same format and pitch character; no
CE asset bytes are copied.

- **`trainer_sounds.py` (new):** deterministic synthesis of the three
  ticks as 8-bit unsigned mono 11025 Hz RIFF/WAVE bytes (on: 5512.5
  Hz / 28 ms; off: 3675 Hz / 28 ms; attach: double 3675 Hz tick with a
  silent gap); module-cached buffers (`SND_MEMORY` requires the
  buffer to stay alive for the playback); `play_sound(kind)` is
  best-effort - Win32 winmm `PlaySound` with `SND_MEMORY |
  SND_ASYNC`, a stable named result string
  (`played` / `skipped: non-windows platform` / `refused:
  <reason>`), and never raises into the UI.
- **`ui.py`:** the old 880/440 Hz sine `play_toggle_sound` helper is
  replaced by `trainer_sounds.play_sound` at every confirmed toggle
  site (row switch and group heading toggle now both sound) and on
  the attach-success transition detected in `TrainerWindow.poll()`
  (the engine memory handle going from nothing to a live target
  plays the attach tick exactly once per (re-)attach; failed attach
  attempts stay silent).
- **`engine.py`:** confirmed activation toggles dispatched through
  the hotkey path (OS bridge drain or programmatic
  `dispatch_hotkey`) surface as `(record_id, resulting-active)`
  pairs through `TrainerEngine.pop_hotkey_ui_toggles()` so the UI
  tick matches CE's on-every-toggle behavior; value-action hotkeys
  are not recorded.
- Tests: new `tests/test_native_trainer_sounds.py` +21 (synthesis
  shape/determinism/character, named playback refusals, hotkey-surface
  recording contract, real-Tk attach-transition / manual-toggle /
  group-toggle / hotkey-toggle wiring); `tests/test_native_ui_tone.py`
  (4 tests) superseded and removed with the old helper.  Full main
  suite 4,193 OK / 30 expected skips on `main` @ `60dbc21` (2026-11-02); catalog remeasure `blocked-catalog-024-sounds`: zero delta
  vs `blocked-catalog-023-field-fixes` (151/151 loaded, 117,809 total
  / 116,756 supported / 60,161 staged / 1,053 blocked / 0 load
  errors; per-table changes 0).
  Build `native-20261102T102029Z-fe358e35` (2026-11-02, cut from
  `main` @ `a2777ed`): in-build suite 4,193 OK / 30 expected skips,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
  source ZIP `CT2Trainer-0.24-source.zip` sha256
  `dfdd8cfcca90a2789bf544d8f8de4e34941067feeb2b32ce8d550f98e5bc4eb6`
  (14,298,696 bytes), portable ZIP
  `CT2Trainer-0.24-windows-portable.zip` sha256
  `12262cf16e906c3811ade0a8c582b7a1057c834a3110aff004dfd13b3067e7ab`
  (49,618,009 bytes), frozen `CT2Trainer-Master.exe` sha256
  `5f3a66400c2c1775e6fc50ad6bbbc36aa8a6bcf8b58fe56507117dc33683494d`
  (16,896,995 bytes) in the run folder, the payload inventory and
  the portable ZIP. Field test of the tick sounds on a live game
  is pending.

**0.43 released (build `native-20261111T184600Z-3bf9d8aa`, cut from `main` @
`0df2607`, 2026-11-11): the Master Trainer minimize-to-tray +
window-geometry persistence (MT-32/MT-33) + the TGC field fix.**
0.43 ships the two adopted candidates of the 0.43 online evaluation -
minimize-to-tray with attach / attention notifications and
window-geometry persistence - plus the TGC field fix from the
2026-11-11 Indiana Jones and the Great Circle field session.
- **MT-32 (minimize-to-tray):** the Master Trainer can minimize into
  the system tray and restore on tray double-click.
  `master_trainer/tray.py` drives the Win32 tray icon
  (`Shell_NotifyIconW` / `RegisterClassExW` / `DestroyIcon` bound
  through `_bind_prototypes` with pointer-sized WPARAM/LPARAM,
  64-bit clean) behind a bounded, named fail-closed guard: a Windows
  build without the `Shell_NotifyIconW` export (stripped user32, the
  Sinking City 2 0.22.1 hotkey-bridge precedent) is the named
  `tray-platform-unavailable` refusal, a refused `RegisterClassExW`
  (Win32 87) is `tray-setup-failed`, a missing icon is
  `tray-icon-missing` - every refusal lands in the status line, never
  a crash and never a dialog, and the toggle simply stays off. The
  persisted "Minimize to tray" preference (master-settings.json
  schema 9 -> 10, `tray_minimize`, default off) restores on start and
  persists on every change; the status-bar cycle button and the
  window `<Unmap>` binding drive it, and a persisted on preference
  minimizes into the tray at start. The tray balloon reports the
  trainer attach success / failure through the new `ui.py`
  `attach_observer` (default None; fail-safe `_fire_attach_observer`
  in `poll()`), so the standalone trainer header and behavior stay
  byte-identical.
- **MT-33 (window-geometry persistence):** the Master window size /
  position is remembered across restarts.
  `master_trainer/window_geometry.py` is the pure layer (parse /
  validate / clamp of the persisted rect); the geometry persists in
  the same master-state document (schema 10, `window_geometry`),
  saved on the bounded `<Configure>` cadence and on close
  (`_save_geometry` / `_save_final_geometry` with defensive winfo
  guards so a half-destroyed window never writes a bogus rect); an
  invalid persisted geometry is the named `window-geometry-invalid`
  refusal (the default geometry) rather than a crash.
- **TGC field fix:** the 2026-11-11 Indiana Jones and the Great
  Circle (0.41) field log (target TheGreatCircle.exe) exposed two
  transient-read dead ends that dead-ended the trainer until a
  manual restart: R1 the module snapshot failed with Win32 299
  (ERROR_INTERNAL_ERROR) immediately after the first attach while the
  game was still loading its DLLs - 299 was NOT in the snapshot
  transient retry set, so the engine got zero retries, became
  engine-blocked, and (fail-closed by design) refused a `close()`
  while the target still lived; R2 a transient 299 read during the
  periodic `_check_patches` (after the 0.39 read-retry budget) was
  wrapped as "An executable hook receipt changed" -> PatchConflict ->
  engine-blocked. A failed read is not an observed change. F1
  (`memory.py`): 299 joins the bounded snapshot transient retry (8
  attempts, 0.05 -> 1.0 s backoff); every `_windows_error` carries a
  machine-readable `win32_code` attribute; the public
  `TRANSIENT_MEMORY_ERRORS = {299, 119, 1116, 24}` set +
  `is_transient_memory_error(exc)` classify a read failure as
  "cannot verify right now" - never "bytes changed". F2
  (`engine.py`): a transient read in the periodic `_check_patches`
  now skips that verification tick instead of blocking - a bounded
  skip streak (`VERIFY_SKIP_STREAK_LIMIT = 30` consecutive ticks,
  reset on every verified tick and on every confirmed (re-)attach), a
  deduped `patch-verify-skipped` debug event (reported once per
  distinct cause, carrying skips/streak/limit/error), and a
  persistent streak is the named fail-closed refusal "Patch
  verification failed on transient read errors for 30 consecutive
  ticks (last: ...); the engine blocks to stay fail-closed." A real
  byte mismatch and a non-transient failure still block immediately
  (unchanged contract); the non-transient hook-read refusal is now
  the more specific "An executable hook receipt could not be
  verified: ..." (a genuine receipt mismatch keeps "An executable
  hook receipt changed: ..."). F2b (`hooks.py`): a transient guard
  read in `_check_allocation_guards` re-raises instead of calling
  `_fail_uncertain` (which would mark the manager uncertain - a
  permanent fail-closed state) - the engine tick-skip then handles it
  with the bounded streak. The `reattach()` / `close()` refusal
  semantics are deliberately unchanged (fail-closed stands).
- +85 tests (new `tests/test_native_master_tray_geometry.py` (62,
  incl. the correctly session-skipped Shell_NotifyIconW smoke test -
  this Windows build lacks the export, the same stripped-user32
  precedent as the SC2 hotkey bridge - plus the master UI / state
  updates), new `tests/test_native_tgc_field_fix.py` (17: the
  transient classification, the engine tick-skip / dedup / reset /
  persistent-block / real-mismatch / non-transient / re-attach-reset
  scenarios, and the F2b guard re-raise), 3 architecture snapshot
  tests adapted for the 299-retry contract + 1 new 299 retry test).
  Full main suite 5,011 OK / 36 expected skips (4,926 from the 0.42
  content + 85 new); catalog remeasure `blocked-catalog-043-tgc`:
  117,809 total / 117,272 supported / 12,974 headings / 104,123
  actionable / 537 blocked - zero delta vs
  `blocked-catalog-042-cleanup` (the 3-chunk record-level delta
  audit: 0 newly blocked, 0 unblocked, 0 reason changes, 0 tables
  added / removed; 0.43 touches no plan-compile path); feature
  matrix unchanged (42/42, 7,475/7,475 over
  `w4b4-case30-20261020081722Z`); AP-11 0/6,143. VERSION bumped to
  0.43 with the changelog entry in the same change (incl. the
  `__version__` package constant sync, guarded by
  `test_version_matches_root_version_file`). The 0.43 build
  `native-20261111T184600Z-3bf9d8aa` was cut from `main` @
  `0df2607` (2026-11-11): in-build suite 5,011 OK / 36 expected
  skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per
  gate; source ZIP `CT2Trainer-0.43-source.zip` sha256
  `c0011d10a5a60b78067b0cdd1a622a134088fee325ac4d544efd3ec8101438ca`
  (14,617,762 bytes) - carries the MT-32/MT-33 tray + geometry
  (`master_trainer/tray.py` + `master_trainer/window_geometry.py` +
  `master_state.py` schema 10 +
  `tests/test_native_master_tray_geometry.py`) and the TGC field
  fix (`memory.py` + `engine.py` + `hooks.py` +
  `tests/test_native_tgc_field_fix.py`) - and portable ZIP
  `CT2Trainer-0.43-windows-portable.zip` sha256
  `dc7a4062b56be99ea887a77ffd23e7c2c1ff38935e471d7f124ed4d775a022e9`
  (49,849,139 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `4846d7568ef4eba091261b21e678c13ab5cecbbf3468a0a57ba30d84fc7e91a4`,
  17,072,494 bytes, ships next to the converter).

**0.42 released (build `native-20261111T044023Z-04112d15`, cut from `main` @
`377f760`, 2026-11-11): the CE 7.5 cleanup parity + the API-export
registry extension.**
0.42 ships the two remaining bounded compatibility classes of the
805-row root-cause census - the second wave of the CE 7.5 parity
program.
- **The CE 7.5 cleanup parity:** a disable-phase cleanup name that
  NO program owns is a silent no-op in CE 7.5
  (`autoassembler.pas` L2492-2525 `unregistersymbol` appends it to
  the deletion list without an ownership check; L2625-2669
  `dealloc` searches only this program's allocation set, read-only
  reference). CT2Trainer now matches it: the name is dropped from
  the program node and recorded in the new program field
  `unowned_cleanup_dropped` (sorted, deduped, casefold) instead of
  refusing the program, and the record stays supported. A name
  live-registered by another supported record keeps the WP-37
  handover refusal - the owning record releases that symbol exactly
  once on its own deactivation, so a second release from a foreign
  program is a real cross-record hazard, not a CE no-op. Because
  the first-pass entry compile runs without the table-wide
  ownership context, the drop is only provisional there: a
  plan-level re-check (after the Wave B1 loop) re-blocks a
  first-pass-supported record when one of its dropped names is (a)
  a WP-37 handover name (record-Lua registerSymbol/unregisterSymbol
  pairs or allocation-only programs - the owner may be the record
  itself) or (b) in any other supported record's entry-level
  `provides` (luaCall AOB symbols, ordinary AA registrations) -
  with the named single-form reason "Program may not unregister or
  deallocate the externally owned symbol X (owned by record N)."
  (the "Static AA envelope: " prefix kept for envelope records).
- **The API-export registry extension:** the bounded Windows API
  export registry (RT-4.2 R7) gains `sleep` (kernel32.dll) and
  `showwindow` (user32.dll) - the corpus thread idioms
  (HorizonForbiddenWest records `mov rcx,10 / call Sleep`;
  APlagueTaleRequiem / Resonance console-open threads `call
  ShowWindow`) now resolve with the exact `api_exports` marker, the
  same contract as the existing user32 entries (requires ==
  [export], link-time resolution against the target's live PE
  export table, named fail-closed refusal on an absent export; a
  bare API name in a value address expression keeps the classic
  unsupported-provider refusal). The CE 7.5 tree has no
  GetProcAddress/kernel32 AA handling (it resolves via the symbol
  handler over target modules); the bounded registry + link-time
  resolution is the clean-room equivalent.
- +9 tests (new `tests/test_native_aa_cleanup_parity.py`: the
  program-level no-op shapes incl. sorted/dedup + wildcard/external
  scoping + the label-only re2 trigger; the plan-level handover
  re-block + the unowned cascade unblock (the re2 12997 root shape -
  the provider stays supported and the dependent `rootsym+8`
  resolves with dependency_ids [1]); the Sleep/ShowWindow markers;
  the value-expression boundary) and 4 modules updated
  (`test_native_assembler`, `test_native_luacall_symbol_only`,
  `test_native_rt42_runtime_provider`, `test_native_lua_symbol_
  handover` - the single named reason), plus the deterministic
  MT-24 race guard in `test_native_master_ui` (a queue-only stub
  analysis worker for the rescan pending-marker test - the daemon
  thread could finish the one-entry table's compile before the
  assertion, making the "..." marker racy). Full main suite 4,926
  OK / 35 expected skips (4,917 from the 0.41 content + 9 new);
  catalog remeasure `blocked-catalog-042-cleanup`: 117,809 total /
  117,272 supported / 12,974 headings / 104,123 actionable / 537
  blocked (-268 vs `blocked-catalog-041-digit-labels` - the 3-chunk
  delta audit vs the 0.41 chunks: zero newly blocked, 268 unblocked
  - 26 `Sleep` + 2 `ShowWindow` + 24 direct cleanup-ownership rows
  + 216 provider cascades: the HFW `pInventoryItemResource` /
  `pAttackInfo` / `PlayerCharacter` thread cascades, the DS2
  `KeyHandlerThread` dependents, the re2 `rootsym` cascade - 12
  still-blocked rows carry the more specific named handover reason:
  DS2 `KeyHandlerThread` x10 (record 87498) + x1 (record 87500),
  `pBase` x1 (record 1337263367)); feature matrix unchanged (42/42,
  7,475/7,475 over `w4b4-case30-20261020081722Z`); AP-11 0/6,143.
  VERSION bumped to 0.42 with the changelog entry in the same
  change (incl. the `__version__` package constant sync, guarded by
  `test_version_matches_root_version_file`). The 0.42 build
  `native-20261111T044023Z-04112d15` was cut from `main` @
  `377f760` (2026-11-11): in-build suite 4,926 OK / 35 expected
  skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per
  gate; source ZIP `CT2Trainer-0.42-source.zip` sha256
  `f44d248303b302b8621e80efc7c6faff476d0f27887b729546bf42c639839415`
  (14,589,013 bytes) - carries the CE 7.5 cleanup parity fix
  (`aa_program.py` + `compiler.py` +
  `tests/test_native_aa_cleanup_parity.py`) and the API-export
  registry extension - and portable ZIP
  `CT2Trainer-0.42-windows-portable.zip` sha256
  `305832ddc03487542c9a889e150b96f45c1576fa5e56819276da54b9388a5c40`
  (49,821,481 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `35389c7611715b494418b2c5bcdbd48e84f8d55a55f3deab556c4aa4d6aefd1c`,
  17,051,026 bytes, ships next to the converter).

**0.41 released (build `native-20261110T210856Z-5811040c`, cut from `main` @
`c724a7e`, 2026-11-10): the AA typed-constant package (the
CE `StrToQWordEx` contract) + the digit-leading-label CE 7.5
parity fix.**
0.41 ships the compatibility lane along the
reference-table-100 roadmap - the two remaining Death
Stranding "Load Table" roots (record 130605: root #1 the
`(int)0.00` decimal-cast operand, root #2 the
`0CurrentWeight:` digit-leading label line) whose failure
blocked the ~243-row "no unique supported provider" cascade.
- **The AA typed-constant package:** the full typed family
  `(int|float|double|dword|qword|word|byte)` as instruction
  operand, data literal and `define` value - the integer
  family follows the CE `StrToQWordEx` contract (read-only
  reference): a `0x`/`$`-prefixed or pure-hex literal parses
  as an integer, a decimal / exponent form parses as a float
  and truncates toward zero, and an out-of-range value is
  the named refusal "Typed constant exceeds the {type}
  representation." instead of a silent wrap; the float /
  double family stays finite-only with the named `Inf` /
  `-Inf` / `NaN` spellings, and a hex literal over a float /
  double type keeps the pre-existing cast no-op. The dialect
  boundary is deliberate: a typed constant parses pure
  digits DECIMAL (the CE contract), while the unsized AA
  dialect keeps its hex-by-default reading - 41 corpus rows
  now assemble with the CE-correct bytes (byte-changing
  parity fixes, every record stays supported, incl. the
  Borderlands3 `cmp [flag],(byte)2` byte-compare) and the
  two decimal-form DS `(int)0.00` rows assemble for the
  first time; the define flow needed no code change (corpus
  census: 164 `define(` calls, exactly 7 `(float)` idioms -
  the APlagueTale
  `define(movespeedmultiplierdefault,(float)0.64)` stays
  byte-stable as `0AD7233F`).
- **The digit-leading-label CE 7.5 parity fix:** the CE 7.5
  label-name contract (`autoassembler.pas`
  `getPotentialLabels` L707-730 + the main path L2843-2900,
  read-only reference) - a `name:` line is a positional
  label definition iff `trystrtoint64('$'+name)` fails -
  implemented as the `_symbol_name_token()` predicate (the
  `_LABEL_NAME` / `_HEX_NAME` / `_LITERAL_TOKEN` shapes) at
  all eight cursor / symbol sites in `aa_program.py`:
  letter-starting names are byte-stable against the pre-fix
  behavior (incl. letter-leading all-hex like `ABC`); a
  digit-leading name is a program-local label only while it
  is not fully hex-parseable and not a value literal (the
  `0x`/`$`-hex and `#N`-decimal spellings the typed-constant
  substitution emits into operand streams), so
  `0CurrentWeight:` keeps the owned allocation region for
  the following `resb 8` padding while `0078:` / `11105:`
  keep the classic externally-provided symbol cursor and the
  `0x...` literal tokens never enter the program's
  requirements; the link walk's `key not in resolved` guard
  keeps digit-leading SCAN symbols (the Octopath1
  `8PathBattleResult` / `8PathSteal` aobscanmodule pairs) on
  the classic resolution path (corpus census: 267 distinct
  digit-leading label names, 262 all-hex unchanged, 5
  non-hex: the DS trio + the Octopath pair, both
  regression-guarded).
- +38 tests (new `tests/test_native_aa_typed_constants.py`
  23 - the `_typed_bits` contract: the integer-family
  `StrToQWordEx` parse (0x/$ hex, decimal, exponent,
  truncation-toward-zero), the out-of-range named refusal,
  the finite-only float / double family, the named Inf /
  NaN spells, the cast no-op boundaries, the NASM byte pins
  incl. the DS root `mov [rax+000002BC],(int)0.00` ->
  `C780BC02000000000000`; new
  `tests/test_native_aa_digit_labels.py` 15 - the
  `_symbol_name_token` predicate, the prepare-level label
  binding, the all-hex symbol-cursor parity, the typed
  literals never entering the requirements, the NASM byte
  pins: the digit-vs-letter byte-stable blocks, the DS root
  idiom, the duplicate digit-label refusal with letter
  parity, the inlined Octopath aobscanmodule replica). Full
  main suite 4,917 OK / 35 expected skips (4,879 from the
  0.40 content + 38 new); catalog remeasure
  `blocked-catalog-041-digit-labels`: 117,809 total /
  117,004 supported / 12,974 headings / 103,855 actionable /
  805 blocked (-248 vs `blocked-catalog-040-process-id` -
  the 3-chunk delta audit vs the 0.40 chunks: zero newly
  blocked, 248 unblocked (the DS pair 122+121=243 rows, root
  record 130605 + the "no unique supported provider"
  cascade: PlayerStats, PlayerBattery, CurrentWeight, ...)
  plus 5 x `dq (double)Inf` records (AtomicHeart / HellPie /
  Oregon / Scorn / Callisto), zero reason changes); feature
  matrix unchanged (42/42, 7,475/7,475 over
  `w4b4-case30-20261020081722Z`); AP-11 0/6,143. VERSION
  bumped to 0.41 with the changelog entry in the same change
  (incl. the `__version__` package constant sync, guarded by
  `test_version_matches_root_version_file`). The 0.41 build
  `native-20261110T210856Z-5811040c` was cut from `main` @
  `c724a7e` (2026-11-10): in-build suite 4,917 OK / 35
  expected skips, `ce_inputs: []`, `runtime_unverified`
  deliberately kept per gate; source ZIP
  `CT2Trainer-0.41-source.zip` sha256
  `05ef6cabca08adcca8a084722581b7d553966e480e28274a4a72f4b31b9c1964`
  (14,580,191 bytes) - carries the AA
  typed-constant package (`aa_program.py` +
  `tests/test_native_aa_typed_constants.py`) and the
  digit-leading-label CE 7.5 parity fix
  (`tests/test_native_aa_digit_labels.py`) - and portable
  ZIP `CT2Trainer-0.41-windows-portable.zip` sha256
  `533bee676d0ed5c487741cb4919af8f4370f2bee1c5c26181ed5f3f0c3753a77`
  (49,814,303 bytes; the frozen
  `CT2Trainer-Master.exe` sha256
  `ce07c42cf22c57eeeffa08be74ff562d3a7dcfca5f4c2d14121c784acd24c6f`,
  17,049,435 bytes, ships next to the converter).
- The DeathStrandingDC Update31 pair (243 rows) is now fully
  supported - the last blocked cascade of the 0.40 catalog
  outside the documented createThread / cleanup-ownership /
  runtime-provider rows; Octopath stays at 0 blocked. The
  live-target runtime confirmation stays in the RT-6 / field
  lane (`runtime_unverified` kept per gate).

**0.40 released (build `native-20261110T093203Z-82c49872`, cut from
`main` @ `e611e9e`, 2026-11-10): the Master Trainer process
identification in picker + details (MT-31) + the bounded
zero-transfer transient-write retry in `memory.py`.**
0.40 ships the adopted 0.40 candidates from the online
evaluation (the Cheat Engine forum "Open Process By PID"
thread: the multi-instance indistinguishability problem -
several running instances of the same game name with no way
to tell them apart; the WeMod UI threads: the layout /
visibility / trainer-options requests remain covered by the
0.36 multi-column grid and the 0.37 per-table process
binding; the Game Cheats Manager front end: tags / search /
filters / last-used -> covered by MT-13/15/18/27,
auto-update / online catalog -> out of scope; the zhisync /
game.cheat online catalog -> out of scope; the game launch
integration -> still out of scope - no install-path data in
the read-only table model) plus the reliability lane that
completes the 0.39 read-side symmetry (the transient WRITE
failure now gets the same bounded retry the transient READ
failure got in 0.39 - the read / write pair is complete).
- **MT-31, the process identification in picker + details:**
  the use case's "choose which table runs against which
  process" direction - MT-10/11/28 persist the attach mode
  and the process binding, but the picker and the
  table-details "Running now" row could not TELL the
  candidates apart: several instances of the same game name
  render as identical name + PID rows, and the PID is the
  only discriminant. The `ProcessSnapshotEntry` gains the
  optional identification fields `path` (the full image
  path), `creation_time` (the process start, Unix epoch
  seconds) and `pointer_size` (4 / 8, the target bitness),
  all default `None` (refused / unavailable - fail-closed:
  the row keeps the byte-stable name + PID form, the `pid`
  / `name` decision fields are never touched). The snapshot
  listers stay cheap (name + PID only, the 30 s auto-rescan
  tick keeps its contract); the bounded per-candidate
  enrichment runs only where the user asks for it - the
  process picker rows and the table-details "Running now"
  row, never per poll tick: `enrich_candidates` applies the
  platform `default_process_enricher` (the injectable test
  seam) to each entry of the bounded candidate set, every
  per-entry failure fails closed (the entry stays
  unenriched, a non-entry result is refused as well). The
  Windows backend opens the process with
  `OpenProcess(PROCESS_QUERY_INFORMATION)` only - no other
  rights - and asks `QueryFullProcessImageNameW` /
  `GetProcessTimes` (FILETIME ticks -> Unix seconds via the
  11644473600 s epoch delta) / `IsWow64Process2` (I386 ->
  4, AMD64 -> 8, anything else unknown), the handle closed
  in a finally, a refused handle / query / missing export
  keeps the entry unenriched, no error propagates. The
  Linux/SteamOS backend takes the `/proc/<pid>/exe` link
  target (under Proton the compatibility-prefix path of the
  bound Windows EXE) and the `starttime` field 22 of
  `/proc/<pid>/stat` plus the system `btime` at
  `SC_CLK_TCK` (the bitness is not provable from `/proc`
  and stays `None`; any read failure keeps the entry
  unenriched). `process_picker.py`: `candidate_display_text`
  - name + PID always (byte-stable against the pre-0.40 row
  format while unenriched), the proved facts appended as
  "  -  " joined (path / "started YYYY-MM-DD HH:MM" via
  `format_creation_time` / "64-bit" / "32-bit"); a `None`
  fact never renders. `table_details.py`:
  `table_detail_lines(..., running_entries=None)` - the
  enriched "Running now" row (sorted by PID, "; "-joined)
  with the pre-0.40 PID-only form while `None`.
  `master_ui.py`: the picker enriches its bounded candidate
  set before rendering (the listbox widens 48 -> 76 to fit
  the facts on one row), the details window passes the
  enriched running entries; the waiting-view "Running now"
  line keeps its cheap name + PID form (never enriched).
  Zero load-path effect - the MT-9 gate re-checks the table
  independently at load time; the attach decision (the PID
  pin) is unaffected by the enrichment.
- **The bounded zero-transfer transient-write retry:** the
  write-side symmetry of the 0.39 transient-read retry - a
  `WriteProcessMemory` call that FAILED with the
  field-observed transient set {299, ERROR_MORE_DATA=119,
  ERROR_BAD_LENGTH=1116, ERROR_INVALID_ID=24} and
  transferred NOTHING is now retried in
  `memory._write_checked` with the bounded exponential
  backoff (exactly 4 attempts, backoff 0.05 -> 0.25 s, the
  sleep under the caller's lock, the snapshot-retry /
  read-retry precedent); a partial transfer (a call that
  moved any bytes, failed or not) or any non-transient code
  is NEVER retried and lands in the existing uncertain-write
  protocol unchanged (fail-closed - the "never silently
  retries a PARTIAL write" contract holds; after the budget
  the original error surfaces as before).
- +46 tests (`tests/test_native_master_ui_mt31.py` 12 - the
  master Tk wiring: the picker enrichment + row rendering,
  the details "Running now" row, the fail-closed refusal
  paths; `tests/test_native_memory_write_retry.py` 7 - the
  bounded retry: the {299, 119, 1116, 24} transient set, the
  4-attempt budget, the 0.05 -> 0.25 s backoff sequence, the
  zero-transfer precondition, the partial transfer never
  retried, the original error after the budget, the
  non-transient code never retried; the MT-31 additions in
  `tests/test_native_master_process_watch.py` +23 - the
  `ProcessSnapshotEntry` identification fields, the
  `enrich_candidates` bounded loop + fail-closed per-entry
  refusal, the Windows enricher (mocked Win32 seam), the
  procfs enricher (SYMLINKS_OK-guarded),
  `format_creation_time`;
  `tests/test_native_master_process_picker.py` +4 - the
  `candidate_display_text` byte-stable base + fact
  rendering, a refused fact never renders; baseline pinning
  in the MT-12 / MT-22 / MT-28 UI tests - the details-window
  and waiting-view assertions gain the new rows). Full main
  suite 4,879 OK / 35 expected skips (4,833 from the 0.39
  content + 46 new; the 5 SYMLINKS_OK-guarded procfs
  enrichment tests are expected skips where the symlink seam
  is unavailable, alongside the 4 pre-existing symlink
  tests); catalog zero delta `blocked-catalog-040-process-id`
  (the 3-chunk audit byte-identical vs
  `blocked-catalog-039-autoload`, 2026-11-10): 117,809 total
  / 116,756 supported / 60,161 staged / 103,607 actionable
  / 12,974 headings / 1,053 blocked - **zero delta** (zero
  newly blocked, zero reason changes); feature matrix
  unchanged (42/42, 7,475/7,475 over
  `w4b4-case30-20261020081722Z`); AP-11 0/6,143. VERSION
  bumped to 0.40 with the changelog entry in the same change
  (incl. the `__version__` package constant sync, guarded by
  `test_version_matches_root_version_file`). The 0.40 build
  `native-20261110T093203Z-82c49872` was cut from `main` @
  `e611e9e` (2026-11-10): in-build suite 4,879 OK / 35
  expected skips, `ce_inputs: []`, `runtime_unverified`
  deliberately kept per gate; source ZIP
  `CT2Trainer-0.40-source.zip` sha256
  `46ad5dd9f9adc872e320dd4aec2362e007020ae879bba0cc8fe0621e44c34c40`
  (14,569,029 bytes) - carries the MT-31 process
  identification (`process_watch.py` enrichment layer +
  `tests/test_native_master_ui_mt31.py`) and the bounded
  transient-write retry
  (`tests/test_native_memory_write_retry.py`) and the
  reviewable `master_trainer/UI.md` - and portable ZIP
  `CT2Trainer-0.40-windows-portable.zip` sha256
  `5075586c7b0f3251749c8e3e60ec0db7fea251db39190b59b63273a4e9b10bd6`
  (49,809,535 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `52f6da1cebfc44a0dc791d4b5758112342b5a1d42c9fc9656901a16d1a5eb03f`,
  17,048,910 bytes, ships next to the converter).
- The read / write transient pair is now complete: the
  0.39 half (the Win32 error 299 transient read failure,
  `memory._read_exact`) and this 0.40 half
  (`memory._write_checked`) both ship bounded retries, both
  fail closed on a partial transfer. The remaining
  reliability work stays in the RT-6 / field lane
  (live-target runtime confirmation, `runtime_unverified`
  kept per gate).

**0.39 released (build `native-20261110T051241Z-57bf7d47`, cut from
`main` @ `17a22f7`, 2026-11-10): the Master Trainer per-table
auto-load policy (MT-29) + state folder / debug log quick access
(MT-30) + the bounded transient-read retry in `memory.py`.**
0.39 ships the adopted 0.39 candidates from the online
evaluation (the WeMod community thread re-read: the layout /
visibility / trainer-options requests remain covered by the 0.36
multi-column grid and the 0.37 per-table process binding; the
code survey of Game-Trainer-Manager: pin-to-top -> MT-18 exists,
local search -> MT-13/14 exists, detailed logs / debug mode ->
the adopted MT-30 signal, Steam launch / online catalog / themes
/ bilingual -> out of scope for the private own-use model) plus
the reliability lane closing the documented open issue of the
0.38 ledger (the field-observed Win32 error 299 transient read
failure is now the object of the bounded retry instead of a
separate lane).
- **MT-29, the per-table auto-load policy:** the use case's
  "choose which table runs" direction - MT-10/11 persist the
  attach mode and the MT-28 process binding, but a table the
  user wants to load explicitly was still auto-loaded on every
  master start. `table-autoload.json` schema 1 under the state
  home, keyed by the table content sha256 - the same identity as
  the MT-24 analysis, MT-27 notes and MT-28 attach sidecars, so
  a policy survives a rename and follows a content-identical
  file to another root. Only the non-default policy persists -
  one `manual-only` entry per table; the absence of an entry is
  the documented automatic default (the MT-24 sidecar
  precedent). A manual-only table is never auto-loaded: no
  auto-load request and no picker - the waiting line shows the
  stable named detail "auto-load suppressed (all N bound
  table(s) for this process are manual-only; load one
  explicitly)" instead, and an open choice is dropped back to
  waiting. Every explicit load path (double-click / Enter,
  "Load this table", the "Load table" picker, `Recent:`) keeps
  working unchanged. The policy set is a zero-arg callable
  re-evaluated on every orchestrator tick (a policy change
  applies from the next tick); a table without a content sha
  cannot carry a policy (the documented MT-27 identity rule).
  The row context menu offers the toggle ("Auto-load: manual
  only" / "Auto-load: automatic" - the label names the action,
  the pin-toggle convention; immediate persist + status line;
  the disabled "Auto-load policy (no content sha)" item for a
  table without a content sha); the MT-22 table-details window
  gains the "Auto-load policy" row; the waiting-view filter
  matches the persisted policy text. Display-side only - the
  MT-9 gate re-checks the table independently at load time.
- **MT-30, state folder / debug log quick access:** the waiting
  view gains two master-only header buttons - "State folder..."
  and "Debug log..." (the standalone trainer header stays
  byte-identical, the MT-21 discipline) - opening the persisted
  state home (the master-state document, the table index, the
  per-table sidecars, and the `forced-recovery/` archives
  created by the 0.38 `--force` forced start) and the trainer
  debug log at its exact `debug_log.default_log_path()` in the
  platform file manager / default handler. The pure
  `state_access.py` layer carries the named
  `StateAccessRefusal` codes (`state-folder-bad` /
  `state-folder-missing` / `debug-log-bad` / `debug-log-missing`
  / `no-opener` / `bad-path` / `opener-failed`); every refusal
  lands in the status line - never a dialog, never a crash.
- **The bounded transient-read retry:** the field-observed
  transient "ReadProcessMemory failed (Win32 error 299)" (0.22
  / 0.30 / 0.31 field logs, Proton - no public Windows constant
  is named for 299, so it is documented as a field-observed
  transient code) is now retried in `memory._read_exact` with
  the bounded exponential backoff: the transient set {299,
  ERROR_MORE_DATA=119, ERROR_BAD_LENGTH=1116,
  ERROR_INVALID_ID=24} (the same codes the module-snapshot
  retry treats as transient), exactly 4 attempts, backoff
  0.05 -> 0.25 s (the sleep under the caller's lock, the
  snapshot-retry precedent); a partial result (a successful
  call that transferred fewer bytes) is NOT retried - an
  unexpected state, not a transient error code; after the
  budget the original error is raised unchanged (fail-closed,
  no silent success).
- +73 tests (`tests/test_native_master_autoload.py` 33 - the
  pure `table_autoload` layer: the schema-1 store contract, the
  content-sha keying, the manual-only-only persistence
  (absence = auto default), the rename survival, the
  no-content-sha refusal, the LRU bound;
  `tests/test_native_master_ui_mt29.py` 14 - the master Tk
  wiring: the orchestrator `manual_only` tick re-evaluation,
  the suppressed auto-load (no request, no picker, the stable
  named waiting detail), the open-choice drop-back, the
  explicit-load paths unaffected, the context menu toggle +
  persist + status line, the no-content-sha disabled item, the
  details row, the filter match;
  `tests/test_native_master_ui_mt30.py` 20 - the two header
  buttons: the state-home open, the debug-log open, every named
  `StateAccessRefusal` code in the status line, the master-only
  header (standalone byte-identical), the opener injection
  seam; `tests/test_native_memory_read_retry.py` 6 - the
  bounded retry: the {299, 119, 1116, 24} transient set, the
  4-attempt budget, the 0.05 -> 0.25 s backoff sequence, the
  partial result never retried, the original error after the
  budget, the non-transient code never retried); the 7 baseline
  updates (3 in `tests/test_native_master_notes.py`, 2 in
  `tests/test_native_master_ui_mt22.py`, 2 in
  `tests/test_native_master_ui_mt24.py` - the details-window
  and waiting-view assertions gain the new rows). Full main
  suite 4,833 OK / 30 expected skips (4,760 from the 0.38
  content + 73 new); catalog zero delta
  `blocked-catalog-039-autoload` (the 3-chunk audit
  byte-identical vs `blocked-catalog-038-force`, 2026-11-10):
  117,809 total / 116,756 supported / 60,161 staged /
  103,607 actionable / 12,974 headings / 1,053 blocked -
  **zero delta** (zero newly blocked, zero reason changes);
  feature matrix unchanged (42/42, 7,475/7,475 over
  `w4b4-case30-20261020081722Z`); AP-11 0/6,143. VERSION
  bumped to 0.39 with the changelog entry in the same change
  (incl. the `__version__` package constant sync, guarded by
  `test_version_matches_root_version_file`). The 0.39 build
  `native-20261110T051241Z-57bf7d47` was cut from `main` @
  `17a22f7` (2026-11-10): in-build suite 4,833 OK / 30
  expected skips, `ce_inputs: []`, `runtime_unverified`
  deliberately kept per gate; source ZIP
  `CT2Trainer-0.39-source.zip` sha256
  `14163e7475477c177be339d06fd5ba7b9a7016667405669b084faed25035a923`
  (14,549,960 bytes) - carries the MT-29 auto-load policy
  (`table_autoload.py` pure layer + `table-autoload.json`
  schema 1, `tests/test_native_master_autoload.py` +
  `tests/test_native_master_ui_mt29.py`), the MT-30 state
  folder / debug log quick access (`state_access.py` pure
  layer, `tests/test_native_master_ui_mt30.py`) and the
  bounded transient-read retry
  (`tests/test_native_memory_read_retry.py`) and the
  reviewable `master_trainer/UI.md` - and portable ZIP
  `CT2Trainer-0.39-windows-portable.zip` sha256
  `7d5d7903f1be5df0eac0f1067d5c2ca596321a41ea37381e033e5deb175ec8b6`
  (49,800,752 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `e0db5b2e2f41ec816089486ca57a2c0b1424523e7ee8450335053923ab629e47`,
  17,042,819 bytes, ships next to the converter).
- The documented open issue of the 0.38 ledger (the Win32
  error 299 transient read failure, `memory._read_exact` with
  no bounded retry) is now closed: the bounded retry ships in
  this release. The remaining reliability work stays in the
  RT-6 / field lane (live-target runtime confirmation,
  `runtime_unverified` kept per gate).
**0.38 released (build `native-20261109T211151Z-03e89050`, cut from
`main` @ `da1e68f`, 2026-11-09): the --force forced start for the
documented SteamOS state-lock dead end.**
0.38 ships the user-requested `--force` startup parameter (2026-11-09
field request) - the reliability fix for the recurring SteamOS
problem that the trainer does not start at all because of the state
lock. The dead end was documented by the user's Indiana Jones and
the Great Circle Proton field logs (the 0.22 / 0.30 / 0.31
`.ct2debug.log` files): an interrupted recovery transaction left
`recovery.lock` behind, the recovery-eligibility assessment stopped
classifying the state, and the conservative refusal "A recovery
transaction owns this state" fired on every start - on SteamOS the
user cannot easily delete the state folder, so the trainer stays
unusable for hours. The 0.31 log proves the engine's process probe
detects trainer PIDs correctly under Proton (the probe worked; the
dead end is an assessment-eligibility issue, not a broken probe).
Adopted: the `--force` forced start - skip the state-lock safety
prompts, auto-recover the provably stale, quarantine the
unclassifiable - with one hard data-safety boundary that stays even
under `--force`: a proven-alive trainer-side owner is never
displaced.
- **The `--force` forced start:** accepted by the frozen trainer EXE
  (`launcher.py`), the source CLI `run` + `master` commands
  (`__main__.py`) and the frozen `CT2Trainer-Master.exe`
  (`tools/native_master.py`); the master wiring is
  `run_master(..., force=)` -> `MasterApp.force` -> the `_start_load`
  loop (auto recovery without prompt, forced reclaim via
  `default_state_dirs(plan, app.state_dir_for(plan))`, live-conflict
  refusal, the `except StateError` clause before the generic
  `except Exception`; the status line + fail-closed loop guard
  unchanged). Semantics: (a) a recoverable stale state
  (`StaleStateRecoverable`, the state-lock owner proven dead) or
  unfinished receipts (`StaleArtifactsRecoverable`) is archived
  through the tested `perform_stale_recovery` path without the
  `askyesno` confirmation dialog; (b) the fence dead end - the plain
  `StateError` "A recovery transaction owns this state" (incl. the
  "state.lock already exists" probe fallback) - triggers the new
  bounded forced reclaim in the pure `state_force.py` layer
  (`force_reclaim`): every recorded trainer-side owner (the state
  lock, the recovery fence, the session record, the matching shared
  process claims under `_process_sessions`) is probed with the
  tested process probe (one observation, one retry on a transient
  "unknown"); a proven-alive trainer-side owner is still refused with
  its named reason - the one hard data-safety boundary that stays
  even under `--force` (the `LiveStateConflict` path now refuses
  without the termination prompt); every other case (proven-dead
  owner, unprovable owner: transient probe failure, legacy lock
  without a creation identity, unparseable document) quarantines the
  blocking artifacts (`state.lock`, `recovery.lock`, `session.json`,
  `state.json.tmp`, `oneshot.json.tmp`, the hook receipts /
  global-pool, this trainer's shared claims) into a timestamped
  `forced-recovery/<UTC stamp>-<trainer id>/` archive next to the
  state folder, with the evidence document `force-reclaim.json`
  (`ct2trainer-forced-reclaim/v1`: owner observations, moved files
  with size + sha256, the preserved `state.json`); the saved
  `state.json` (the user's saved wishes) is always preserved, so the
  saved toggles survive the forced reclaim; the engine default state
  directories are factored out as `default_state_dirs` (single fact
  shared by the engine claim and the reclaim path); debug-log events
  `state-force-recovered` / `state-force-reclaimed` /
  `state-force-refused` / `state-force-failed`. On Steam / SteamOS:
  `--force` in the game's launch options (Properties -> Launch
  Options) so the Proton-wrapped trainer starts without any dialog.
- +27 tests (`tests/test_native_state_force.py` 13 - the pure
  `force_reclaim` layer: the proven-alive state-lock owner refusal
  (state untouched), the dead-owners quarantine with the saved-state
  preservation, the dead fence owner reclaim, the own shared claim
  moved + the foreign claim kept, the live shared-claim owner
  refusal, the no-artifacts no-op, the unprovable-owner quarantine
  with evidence, the non-Windows no-probe refusal, the corrupt lock
  quarantine, the hooks / global-pool reclaim, the legacy lock
  quarantine, the moved-bytes-preserved-with-sha proof, the
  archive-collision refusal; `tests/test_native_master_force.py` 8 -
  the master Tk wiring: the forced stale-state / stale-artifacts
  auto recovery without prompt, the stale-recovery failure
  fail-closed start refusal, the fence dead-end reclaim + start, the
  reclaim refusal fail-closed, the live-conflict refusal without
  prompt, the custom state dir addressed by the reclaim, the
  non-force app still prompts; `tests/test_native_ui_recovery_flow.py`
  +6 `RunTrainerForceFlowTests` - the `run_trainer(force=)` branches:
  the forced stale-state / stale-artifacts auto recovery without
  prompt, the stale-recovery failure exit, the fence dead-end
  reclaim + start, the reclaim refusal exit, the live-conflict
  refusal without the termination prompt); full main suite 4,760 OK
  / 30 expected skips (4,733 from the 0.37 content + 27 new); catalog
  zero delta `blocked-catalog-038-force` (3-chunk deep-equal audit
  over the 151 reference tables, 2026-11-09): 151/151 loaded, 0 load
  errors, 117,809 total / 116,756 supported / 60,161 staged /
  103,607 actionable / 12,974 headings / 1,053 blocked - **zero
  delta** vs `blocked-catalog-037-attach` (per-table
  count/reason/sha changes: 0); feature matrix unchanged (42/42,
  7,475/7,475 over `w4b4-case30-20261020081722Z`); AP-11 0/6,143.
  VERSION bumped to 0.38 with the changelog entry in the same
  change. The 0.38 build `native-20261109T211151Z-03e89050` was
  cut from `main` @ `da1e68f` (2026-11-09): in-build suite 4,760
  OK / 30 expected skips, `ce_inputs: []`, `runtime_unverified`
  deliberately kept per gate; source ZIP
  `CT2Trainer-0.38-source.zip` sha256
  `e2b466adc7abfb191bbd2b50f8304739a1e82cbf487099d4ecd6fd77cc3f3d0c`
  (14,521,497 bytes) - carries the --force forced start
  (`state_force.py` pure layer + the `force_reclaim` quarantine
  archive, `tests/test_native_state_force.py` +
  `tests/test_native_master_force.py` + the force-flow tests in
  `tests/test_native_ui_recovery_flow.py`) and the reviewable
  `master_trainer/UI.md` - and portable ZIP
  `CT2Trainer-0.38-windows-portable.zip` sha256
  `df5ccfa373c8f5deb6be85f36e75941a1c0b3a9f13afae23c03f1644f9290fc4`
  (49,781,948 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `5d2cc5544eb6a29f1c3283f05e809e392d0038a1f59456c9d52f0356e519231d`,
  17,026,316 bytes, ships next to the converter).
- Documented open issue (not part of 0.38): the Win32 error 299
  transient read failure during a live `PatchConflict` receipt
  verification on Proton (`memory._read_exact` has no bounded
  retry) remains the upstream trigger of the stale state on Deck -
  `--force` recovers from it; the bounded retry stays a separate
  reliability lane.
**0.37 released (build `native-20261109T154005Z-4ad8e339`, cut from
`main` @ `27dbf0d`, 2026-11-09): Master Trainer per-table process
binding persistence (MT-28).**
The 0.37 feature was evaluated against the use case's core
requirement ("choose which table runs and which process it
attaches to - remember the configuration"): a re-read of the WeMod
community thread "UI customization"
(community.wemod.com/t/ui-customization/371434) - the thread's
layout / visibility requests remain covered by the 0.36
multi-column grid - plus a code audit of the Master Trainer attach
flow found the open functional gap: MT-11 persists the attach
*mode* (auto / ask), and the picker's chosen PID is "pinned for
the session" only (`master_ui.py` `_attach_pin`, honoured by the
injected memory factory until that process exits); a restart
loses the per-table process choice and the user must re-pick it.
Adopted: MT-28, the per-table process binding persistence.
Remaining candidates (updated): the game launch integration (needs
install-path data; out of scope for the read-only table model).
- **MT-28 per-table process binding persistence:** the user's
  explicit process choice (every picker origin: auto-load,
  explicit load, table choice, re-attach after a detach) is
  remembered per table against the table content sha256 (the same
  identity as the MT-24 analysis and the MT-27 notes documents, so
  a remembered choice survives a rename and follows a
  content-identical file to another root). The persisted document
  is `table-attach.json` (schema 1, under the state home; strict
  key-set / field validation of the master-state discipline - an
  unknown field is a named `AttachRefusal`, never a silent drop;
  checksummed canonical-JSON envelope; `ATTACH_ENTRIES_LIMIT` =
  1024 entries, `evict_oldest` by `updated_at`, ties by sha256 -
  deterministic; a refused document is treated as absent,
  documented, never a silent reset). The pure layer lives in
  `table_attach.py` (`binding_entry`, the document bytes / load /
  save, `evict_oldest`, `AttachStore`, `binding_target` - honour
  the stored PID only while it is one of the live candidates
  whose name still matches the bound process - case-insensitive,
  the same rule the picker and the memory factory use; a stale or
  foreign PID yields the documented fallback; `details_attach_lines`
  - the MT-22 details-window "Remembered process" row).
  `master_ui.py`: `MasterApp.attach_store`; the process picker
  gains `preselect_pid` (the remembered row is preselected - the
  picker still opens in `ask` mode, the documented contract);
  `_binding_candidate` (the persisted binding for a table's
  content sha, or None - a table without a content sha cannot
  carry a binding, the documented MT-27 identity rule); the
  binding is consulted in `_auto_load` (a live binding outranks
  the documented smallest-PID rule in `auto` mode; preselected in
  the picker in `ask` mode), `_load_selected_table`,
  `_picker_chosen` (the table-choice path) and
  `_detach_or_attach` (the `attach` origin addresses the loaded
  table through the sidecar sha); `_remember_attach_choice`
  persists the explicit choice before the picker state is torn
  down (a refused choice is not persisted, no status-line noise on
  the hot pick path). Zero load-path effect - the MT-9 gate
  re-checks the table independently at load time.
- +68 tests (`tests/test_native_master_attach.py` 53 - the pure
  `table_attach` layer: the schema-1 document round-trip, the
  strict key-set / field validation refusals, the checksummed
  envelope, the entry shape validation, `evict_oldest` order
  (`updated_at`, ties by sha256), `AttachStore` set / get / has /
  clear, refused documents treated as absent, `binding_target`
  (live + name match, stale, foreign), `details_attach_lines`;
  `tests/test_native_master_ui_mt28.py` 15 - the Tk wiring: the
  `MasterApp.attach_store` sidecar, the picker preselect in `ask`
  mode (with / without / stale binding), the persistence of the
  explicit choice from every origin (auto-load, explicit, choice,
  attach via the sidecar sha), the `auto`-mode honouring (live
  binding outranks the smallest-PID rule; stale / missing binding
  keeps the pre-0.37 behavior), the no-content-sha guard, the
  MT-22 details-window "Remembered process" row) + the baseline
  details-line assertion updates in
  `tests/test_native_master_ui_mt22.py` (2),
  `tests/test_native_master_notes.py` (2) and
  `tests/test_native_master_ui_mt24.py` (2); full main suite 4,733
  OK / 30 expected skips (4,665 from the 0.36 content + 68 new);
  catalog zero delta `blocked-catalog-037-attach` (3-chunk
  deep-equal audit over the 151 reference tables, 2026-11-09):
  151/151 loaded, 0 load errors, 117,809 total / 116,756 supported
  / 60,161 staged / 103,607 actionable / 12,974 headings / 1,053
  blocked - **zero delta** vs `blocked-catalog-036-grid` (per-table
  count/reason/sha changes: 0); feature matrix unchanged (42/42,
  7,475/7,475 over `w4b4-case30-20261020081722Z`); AP-11 0/6,143.
  VERSION bumped to 0.37 with the changelog entry in the same
  change. The 0.37 build `native-20261109T154005Z-4ad8e339` was
  cut from `main` @ `27dbf0d` (2026-11-09): in-build suite 4,733
  OK / 30 expected skips, `ce_inputs: []`, `runtime_unverified`
  deliberately kept per gate; source ZIP
  `CT2Trainer-0.37-source.zip` sha256
  `a49bdd7d738de9551a1d971430ed9f7b0a212ec0d4a2afd8667e1f87ec61d301`
  (14,506,715 bytes) - carries the MT-28 per-table process
  binding persistence (`table_attach.py` pure layer +
  `table-attach.json` schema 1,
  `tests/test_native_master_attach.py` +
  `tests/test_native_master_ui_mt28.py`) and the reviewable
  `master_trainer/UI.md` - and portable ZIP
  `CT2Trainer-0.37-windows-portable.zip` sha256
  `5cdb23b24c0757cb047ddd72ae673614fc6bccee960747079849fe325785c3ce`
  (49,762,223 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `c2a1a6948fa28248d36a6defa5a116867620261e55bdcfe1e144cd301060a9de`,
  17,017,090 bytes, ships next to the converter).

**0.36 released (build `native-20261109T114726Z-15c3d9ab`, cut from
`main` @ `d071884`, 2026-11-09): Master Trainer multi-column
trainer grid (MT-21).**
The 0.36 feature was evaluated against online trainer front-end
cheat-list layout patterns (WeMod's cheat list: the official WeMod
community thread "UI customization"
(community.wemod.com/t/ui-customization/371434, 2025-09-11)
records the staff-confirmed behavior - "The cheat list collapses
to a single column under a certain size so nothing is hidden.
There are also minimum width constraints to prevent it from ever
being hidden" - i.e. a multi-column cheat list with the clamped
single-column collapse and a per-column width floor, the exact
multi-screen / multi-monitor use case the thread is about; the
2025-09-22 follow-up in the same thread (trainer options
"highly compacted ... unreadable" on a portrait / narrow display)
corroborates the width-floor requirement; see the Master Trainer
ROADMAP "0.36 multi-column trainer grid" section). Adopted: MT-21,
the multi-column trainer grid. Remaining candidates (updated): the
game launch integration (needs install-path data; out of scope
for the read-only table model).
- **MT-21 multi-column trainer grid:** the trainer row grid can
  run in up to three side-by-side columns. The requested column
  count (1 / 2 / 3, default 1) persists in the master state
  (master-settings.json schema 8 -> 9, `grid_columns`; strict int
  validation in 1..3; a schema-8 document carrying the field is
  refused as an unknown field; schema-1..8 documents promote with
  the documented default 1) and is handed to the trainer window on
  table load. The trainer header gains the **"Columns: N"** cycle
  button (master only - the standalone trainer header stays
  byte-identical and always renders the single column): 1 -> 2 ->
  3 -> 1, immediate re-render, the requested count persisted
  through the callback on every change. The pure grid layer lives
  in `ui_rows.py`: `build_grid` (per-column row lists;
  `columns == 1` byte-stable against `build_rows`; otherwise the
  reference rows are emitted at the full width, split into
  top-level units (`row_units` - a section with its children never
  splits across columns), the width-independent unit heights flow
  shortest-column-first (`flow_units`, ties to the lower column
  index) and each column is re-emitted at its own width with the
  column x0 baked into every row rectangle (`column_layout`, equal
  widths, the leftover pixels to the leftmost columns));
  `effective_columns` clamps the requested count to what fits
  (two columns need 652 px, three need 984 px; a column never
  falls below the 320 px floor). The renderer carries per-column
  pagination and per-column hit-testing (x picks the column, y the
  row inside that column with its own page offset); the
  right-anchored positions derive from the baked `row.hit`
  rectangles. The standalone trainer is untouched beyond the new
  default-valued constructor arguments. Zero load-path effect -
  the MT-9 gate re-checks the table independently at load time.
- +55 tests (`tests/test_native_ui_grid.py` 37 - the pure grid
  layer: effective_columns thresholds, column_layout incl. the
  leftover distribution, row_units, flow_units determinism,
  build_grid byte-stability / section integrity / geometry /
  clamp / hidden-children; `tests/test_native_master_ui_mt21.py`
  14 - the app default / persistence / refusals / schema-8
  promotion, the handoff columns + callback, the handler
  persistence + refusal swallow, the columns kwarg validation,
  the header button wiring-only, the cycle label + notify, the
  2-column render + per-column hit test, the narrow clamp, the
  standalone 1-column invariant; the grid tests in
  `tests/test_native_master_state.py` 4) + the baseline handoff
  assertion updates in `tests/test_native_master_ui.py` (4); full
  main suite 4,665 OK / 30 expected skips (4,610 from the 0.35
  content + 55 new); catalog zero delta
  `blocked-catalog-036-grid` (3-chunk deep-equal audit over the
  151 reference tables, 2026-11-09): 151/151 loaded, 0 load
  errors, 117,809 total / 116,756 supported / 60,161 staged /
  103,607 actionable / 12,974 headings / 1,053 blocked - **zero
  delta** vs `blocked-catalog-035-notes` (per-table
  count/reason/sha changes: 0); feature matrix unchanged (42/42,
  7,475/7,475 over `w4b4-case30-20261020081722Z`); AP-11 0/6,143.
  VERSION bumped to 0.36 with the changelog entry in the same
  change. The 0.36 build `native-20261109T114726Z-15c3d9ab` was
  cut from `main` @ `d071884` (2026-11-09): in-build suite 4,665
  OK / 30 expected skips, `ce_inputs: []`, `runtime_unverified`
  deliberately kept per gate; source ZIP
  `CT2Trainer-0.36-source.zip` sha256
  `79464f02cd71492763656ca0ff3283a240c3579b9f52df3bcc18857dabb3d1be`
  (14,490,858 bytes) - carries the MT-21 multi-column trainer
  grid (`ui_rows.py` grid pure layer + `master_state.py` schema
  9, `tests/test_native_ui_grid.py` +
  `tests/test_native_master_ui_mt21.py`) and the reviewable
  `master_trainer/UI.md` - and portable ZIP
  `CT2Trainer-0.36-windows-portable.zip` sha256
  `089fc92b0c5758ba758fdc88bb92e11d8e3b3e36c28d04231f27b3eeaecceac0`
  (49,751,886 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `07ebef319b55d686c4f76cdb6f07440a2b4934fc8943f9f72b402d62c4c49fe8`,
  17,006,463 bytes, ships next to the converter).

**0.35 released (build `native-20261109T054146Z-c5f18494`, cut from
`main` @ `65d8fbe`, 2026-11-09): Master Trainer per-table notes /
tags (MT-27).**
The 0.35 feature was evaluated against online trainer / table
manager library-organization patterns (game-trainer-manager
(Karasukaigan): "downloading, importing, organizing, and
searching" with Pin to Top (already MT-18) and local real-time
fuzzy search (already MT-13); Fling-Trainer-Manager
(OscarZhang-735): local catalog with search across main + archive
catalogs; FLiNG: per-trainer metadata (option counts, game version,
last updated - already covered by the MT-24 Entries / Blocked
columns and the Size / Modified / Last-used columns); WeMod:
library organization patterns - see the Master Trainer ROADMAP
"0.35 per-table notes / tags" section). Adopted: MT-27, the
per-table notes / tags. Remaining candidates (evaluated, not yet
adopted): the MT-21 multi-column trainer grid; the game launch
integration (needs install-path data).
- **MT-27 per-table notes / tags:** the waiting view gains the
  **Note column** (last, width 160) - the persisted per-table
  organization metadata: the note text truncated to one line (an
  ellipsis marks a cut, `NOTE_COLUMN_MAX` = 60 characters) plus the
  tags in brackets (`note [tag-a, tag-b]`); note-only and tag-only
  entries both render; empty while no note exists. The row context
  menu offers **"Edit note..."** between "Load this table" and the
  pin toggle - a small Toplevel with the note (multi-line text,
  bounded at `NOTE_MAX_LEN` = 500 characters) and a
  comma-separated tag entry (bounded at `TAGS_LIMIT` = 8 tags x
  `TAG_MAX_LEN` = 40 characters, stripped, casefold-deduped
  first-spelling-wins); a named refusal at save time (note over the
  limit, a tag too long, too many tags) is shown in the dialog's
  own label - the dialog stays open, the persisted document is
  untouched; a table without a content sha (unreadable / never
  scanned) is refused in the status line, no dialog opens; single
  window, lift on second open, closed on trainer entry with the
  rest of the waiting view.
- **Persistence:** `table-notes.json` (schema 1, under the state
  home) - **keyed by the table content sha256** (the same identity
  as the MT-24 analysis document), so a note survives a rename
  within a root and follows a content-identical file to another
  root; one entry per noted table (`{"note", "tags",
  "updated_at"}`); strict key-set / field validation of the
  master-state discipline (an unknown field is a named refusal,
  never a silent drop); checksummed canonical-JSON envelope;
  `NOTES_ENTRIES_LIMIT` = 1024 entries, `evict_oldest` by
  `updated_at` (ties by sha256 - deterministic); a refused
  document is treated as absent (documented, never a silent
  reset). No master-state schema bump (the MT-24 sidecar
  precedent - the notes live in their own checksum-bound
  document).
- **Search + details:** the waiting-view filter now also matches
  the note text and every tag (the pure `filter_tables` gains the
  optional `note_lookup`, keyed by the table content sha; a table
  matches when ANY of them matches; `note_lookup=None` is the
  exact pre-0.35 behavior); the MT-22 table-details window gains
  the note / tag rows after the entry-analysis block (`none` while
  the table carries no organization metadata). No index
  mutation, no table-file access, zero load-path effect - the
  MT-9 gate re-checks the table independently at load time.
- +67 tests (`tests/test_native_master_notes.py`: the pure layer -
  `parse_tags` rules, the `note_entry` builder, the schema-1
  document discipline (unknown fields, checksum, schema, key,
  timestamp, entry-limit), `evict_oldest` determinism,
  `NotesStore` (set / clear / eviction / refused-document-as-
  absent), the column / details text helpers, the filter
  extension - plus the Tk wiring: the Note column (11 row
  values), the menu order (`Table details` / `Load this table` /
  `Edit note...` / `Pin to top`), the editor (prefill, save
  persistence + re-render, cancel, the over-limit note / over-
  long tag refusal inside the dialog, the no-content-sha and the
  missing-entry refusal in the status line, the second-open
  lift), the details-window note / tag rows); full main suite
  4,610 OK / 30 expected skips (4,543 from the 0.34 content + 67
  new); catalog remeasure `blocked-catalog-035-notes` (3-chunk
  deep-equal audit over the 151 reference tables, 2026-11-09):
  151/151 loaded, 0 load errors, 117,809 total / 116,756
  supported / 60,161 staged / 103,607 actionable / 12,974
  headings / 1,053 blocked - **zero delta** vs
  `blocked-catalog-034-mt26` (per-table count/reason/sha
  changes: 0); feature matrix unchanged (42/42, 7,475/7,475 over
  `w4b4-case30-20261020081722Z`); AP-11 0/6,143. VERSION bumped to
  0.35 with the changelog entry in the same change. The 0.35
  build `native-20261109T054146Z-c5f18494` was cut from `main` @
  `65d8fbe` (2026-11-09): in-build suite 4,610 OK / 30 expected
  skips, `ce_inputs: []`, `runtime_unverified` deliberately kept
  per gate; source ZIP `CT2Trainer-0.35-source.zip` sha256
  `575ee8ad6f0864bd8ff39f3ae547bb629d5c128938cff792e9c4fb7362fbcdac`
  (14,474,384 bytes) - carries the MT-27 per-table notes / tags
  (`table_notes.py` pure layer + `table-notes.json` schema 1,
  the Note column, the "Edit note..." editor,
  `tests/test_native_master_notes.py`) and the reviewable
  `master_trainer/UI.md` - and portable ZIP
  `CT2Trainer-0.35-windows-portable.zip` sha256
  `488d7453ca0433f843c1e46a2241142347aa2ee41390ed334d6068ed30e42d34`
  (49,737,899 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `0c53908c267746cabd74e1ef091daa35d31eb94c4d0accc6401085d7e8c59ccc`,
  16,999,124 bytes, ships next to the converter).

**0.34 released (build `native-20261109T024143Z-a5457911`, cut from
`main` @ `dc00343`, 2026-11-09): Master Trainer multi-root table
index (MT-26).**
The 0.34 feature was evaluated against online table / trainer
manager patterns (the Cheat Engine Table Manager (2026) feature
set, whose core capability is the multi-folder table index; the
trainer-manager import / organize / search / pin patterns -
game-trainer-manager (Karasukaigan), Cheat Happens Trainer Manager;
the WeMod "save your selections for next time" pattern - see the
Master Trainer ROADMAP "0.34 multi-root table index" section).
Adopted: MT-26, the multi-root table index. Remaining candidates
(evaluated, not yet adopted): per-table notes / tags (organize
metadata) - the documented 0.35 candidate; the MT-21 multi-column
trainer grid; the game launch integration (needs install-path
data).
- **MT-26 multi-root table index:** the Master Trainer indexes
  several table folders at once. Every root keeps the same
  incremental reconcile contract (the `(size, mtime_ns)` + sha256
  short-circuit per root; the MT-25 auto-rescan now covers every
  indexed folder), and the merged surface distinguishes tables by
  the **absolute table key** (index root + relative path, native
  separators; `table_key()`) - the relative path remains the
  documented single-root identity, and key lookups resolve
  casefolded with the documented relative-path fallback
  (`TableIndex.get_by_key` / `RootIndexSet.get_by_key`). The folder
  list persists in `master-settings.json` schema 7 -> 8
  (`table_folders`, primary first, capped at `TABLE_FOLDERS_LIMIT`
  = 8; strict non-empty unique casefolded strings; schema-7
  documents promote on load - the list is filled from the single
  stored last folder and the relative table references (last
  table, recents, pins) are re-anchored to absolute table keys
  under it, so pins / recents survive the upgrade; a schema-7
  document carrying the field is refused as an unknown field; a
  schema-8 document with a set last folder but an empty list
  self-heals to the single folder). The tables index document
  carries one checksum-bound root block per indexed folder (schema
  1 -> 2; `save_index_set` / `load_index_set`; schema-1
  single-root documents promote on load). The folder lifecycle is
  `MasterApp.add_folder` / `remove_folder` / `move_folder_front`
  (named `ValueError`s; `set_folder` keeps its replace-all
  contract), managed by the "Folders..." header button - the
  folder manager window (the indexed folders in user order, the
  primary marked with a star; "Add folder..." / "Set primary" /
  "Remove" / "Close"; every action re-scans the indexed roots,
  saves the index, restarts the auto-rescan clock and refreshes
  the view; a failed change lands in the status line, fail-closed).
  The waiting view gains the **Folder column** (the entry's index
  root), and the row key becomes the absolute key in a multi-root
  session - picker, details, pins, recents and the MT-24 analysis
  queue are all key-based. `run_master` multi-root folder
  resolution: an explicit folder argument wins as the primary root
  with the stored folders indexed behind it (casefold-deduped,
  each printed as an "Also indexing stored folder:" line); a
  parameterless start keeps the stored folder list as-is (a
  missing stored folder stays visible as a scan problem, fixed
  through the folder manager); only a genuinely first start / no
  stored folders shows the directory picker (a cancelled first
  start exits 0); every stored folder gone shows the picker (the
  pick is prepended as the new primary, a cancel keeps the missing
  list); an explicit missing folder is the documented exit-2
  refusal. Zero load-path effect - the MT-9 gate re-checks the
  table file under its index root independently at load time. Zero
  catalog effect (no table-parsing change).
- +44 tests (7 in `tests/test_native_master_state.py`: the
  schema-8 `table_folders` round-trip, the schema-7 document
  promotion (folder list from the stored last folder + the
  re-anchored relative table references), the
  schema-7-carries-the-field unknown-field refusal, the schema-8
  self-heal, and the cap / unique / non-empty named refusals; 37
  in `tests/test_native_master_ui_mt26.py` new: the `RootIndexSet`
  pure surface (roots / add / remove / move-front, the
  first-root-wins merged lookups, the key resolution with the
  relative-path fallback, the read-only merged entries, the
  `table_key` form), the multi-root `MasterApp` (the folder
  lifecycle + named refusals, the persisted folder list, the
  schema-2 index-set round trip, the per-root reconcile
  independence, the missing-root scan problem), the key-based load
  paths (`request_load` / `choose` across roots, the cross-root
  same-relative-path disambiguation), the folder manager window
  (primary marker, the add / set-primary / remove wiring, the
  auto-rescan clock restart), the Folder column + the row key, the
  table-load picker labels, the `run_master` multi-root folder
  resolution, the multi-root auto-rescan); full main suite 4,543
  OK / 30 expected skips (4,499 from the 0.33 content + 44 new);
  catalog remeasure `blocked-catalog-034-mt26` (3-chunk deep-equal
  audit over the 151 reference tables, 2026-11-09): 151/151
  loaded, 0 load errors, 117,809 total / 116,756 supported /
  60,161 staged / 103,607 actionable / 12,974 headings / 1,053
  blocked - **zero delta** vs `blocked-catalog-033-auto-rescan`
  (per-table count/reason/sha changes: 0); feature matrix
  unchanged (42/42, 7,475/7,475 over
  `w4b4-case30-20261020081722Z`); AP-11 0/6,143. VERSION bumped to
  0.34 with the changelog entry in the same change. The 0.34 build
  `native-20261109T024143Z-a5457911` was cut from `main` @
  `dc00343` (2026-11-09): in-build suite 4,543 OK / 30 expected
  skips, `ce_inputs: []`, `runtime_unverified` deliberately kept
  per gate; source ZIP `CT2Trainer-0.34-source.zip` sha256
  `0d0a0849a90171f64eaf5b55ec06ec1d9117d02d5330895dcb4279e26f73b0f5`
  (14,455,170 bytes) - carries the MT-26 multi-root table index
  (`table_index.py` `RootIndexSet` + schema-2 index set,
  `master_state.py` schema 8,
  `tests/test_native_master_ui_mt26.py`) and the reviewable
  `master_trainer/UI.md` - and portable ZIP
  `CT2Trainer-0.34-windows-portable.zip` sha256
  `ade1ecc520ddbeaf6886e1b195fc6e2886a5f9cbeaa64b15f9ac5679420f5054`
  (49,719,386 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `606ea2287eb9f787308d862c18209076ee42e4f7a4ae88fcb93bf8f22edcb6f6`,
  16,983,514 bytes, ships next to the converter).

**0.33 released (build `native-20261108T200230Z-b0167049`, cut from
`main` @ `6e71739`, 2026-11-08): Master Trainer table folder
auto-rescan (MT-25).**
The 0.33 feature was evaluated against online trainer front-end and
trainer-manager freshness patterns (WeMod automatic game detection -
the front end keeps the found-game / content pairing current;
game-trainer-manager (Karasukaigan) directory watching + auto-import
of matching files; Cheat Happens Trainer Manager library-freshness
lineage - see the Master Trainer ROADMAP "0.33 table folder
auto-rescan" section). Adopted: MT-25, the table folder auto-rescan.
Remaining candidates (evaluated, not yet adopted): per-table notes /
tags (organize metadata) vs. the multi-root index (several table
folders in one Master window) - the 0.34 candidate, decided at the
next release; the MT-21 multi-column trainer grid; the game launch
integration (needs install-path data).
- **MT-25 table folder auto-rescan:** the waiting view re-runs the
  existing incremental scan (the same `(size, mtime_ns)` + sha256
  short-circuit contract as the manual Rescan) on a bounded
  background interval (`AUTO_RESCAN_INTERVAL_SECONDS` = 30 s, one
  stat pass per interval) so added / changed / removed tables show up
  in the index and the view without a manual F5. No OS file-watcher
  API - polling only, cross-platform. The persisted on/off flag lives
  in the master state (`master-settings.json` schema 6 -> 7,
  `auto_rescan`, strict bool, documented default on; schema-6
  documents promote on load, a schema-6 document carrying the field
  is refused as an unknown field) and is toggled by the status-bar
  "Auto-rescan: on/off" button (next to the attach-mode toggle;
  re-persists on every change; a non-bool change raises the named
  `ValueError` and lands in the status line without a state change).
  The scan pauses on trainer entry (the poll tick early-returns,
  exactly like the MT-24 analysis worker) and while a picker is
  open; the interval clock restarts on a manual rescan, a folder
  change, and the waiting-view rebuild (trainer round-trip); the tick
  runs through `rescan()`, so added / changed tables are also
  re-queued for the MT-24 background analysis, and the tick carries
  no status-line flash (the waiting line keeps its cadence). Zero
  load-path effect - the MT-9 gate re-checks the table independently
  at load time. Zero catalog effect (no table-parsing change).
- +16 tests (4 in `tests/test_native_master_state.py`: the schema-7
  `auto_rescan` round-trip, the schema-6 document promotion, the
  schema-6-carries-the-field unknown-field refusal, the non-bool
  refusal; 12 in `tests/test_native_master_ui_mt25.py` new: the
  status-bar toggle (present + on/off text, flips the flag and
  persists it, a failed change lands in the status line without a
  state change), the interval clock (a poll after one interval
  re-runs the incremental reconcile so a newly added table shows up,
  without the "Rescanning…" flash; a disabled flag skips it; trainer
  mode skips it; a manual rescan restarts the clock so no immediate
  second pass)); full main suite 4,499 OK / 30 expected skips
  (4,483 from the 0.32 content + 16 new); catalog remeasure
  `blocked-catalog-033-auto-rescan` (3-chunk deep-equal audit over
  the 151 reference tables, 2026-11-08): 151/151 loaded, 0 load
  errors, 117,809 total / 116,756 supported / 60,161 staged /
  103,607 actionable / 12,974 headings / 1,053 blocked - **zero
  delta** vs `blocked-catalog-032-analysis` (per-table
  count/reason/sha changes: 0); feature matrix unchanged (42/42,
  7,475/7,475 over `w4b4-case30-20261020081722Z`); AP-11 0/6,143.
  VERSION bumped to 0.33 with the changelog entry in the same
  change. The 0.33 build `native-20261108T200230Z-b0167049` was
  cut from `main` @ `6e71739` (2026-11-08): in-build suite 4,499
  OK / 30 expected skips, `ce_inputs: []`, `runtime_unverified`
  deliberately kept per gate; source ZIP
  `CT2Trainer-0.33-source.zip` sha256
  `4528d1d0f2ee269fb2ee7ec470d9e9711b3c284bffe6cf582f7dafa7431756f2`
  (14,433,388 bytes) - carries the MT-25 auto-rescan
  (`master_state.py` schema 7, the 30 s auto-rescan tick,
  `tests/test_native_master_ui_mt25.py`) and the reviewable
  `master_trainer/UI.md` - and portable ZIP
  `CT2Trainer-0.33-windows-portable.zip` sha256
  `5e0244791b6f31a2e2219d5c33541c978ca4c0d399c8e7a234cb0c16e8ccb3d7`
  (49,703,149 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `59961d511d3964b075c968a3c577117ffa235970d65976f66d7e34e0eae010a9`,
  16,968,879 bytes, ships next to the converter).

**0.32 released (build `native-20261108T100731Z-a1d311e5`, cut from
`main` @ `bfcc3a3`, 2026-11-08): Master Trainer per-table entry
count + blocked count (background plan analysis, MT-24).**
The 0.32 feature was evaluated against online trainer front-end and
trainer-manager UX patterns (FLiNG per-trainer "N Options" /
option-count metadata - per-table entry counts surfaced in the list
tell the user what a table actually offers and what cannot run in it
before loading; game-trainer-manager (Karasukaigan)
organize/search workflows; Cheat Happens Trainer Manager v2
inspect-before-load lineage - see the Master Trainer ROADMAP "0.32
per-table entry count + blocked count (background plan analysis)"
section). Adopted: MT-24, the candidate deliberately deferred in
0.26/0.27/0.29/0.30/0.31 ("the entry-count / blocked-count columns
need background plan-analysis infrastructure"). Remaining candidate
(unchanged): the MT-21 multi-column trainer grid.
- **MT-24 per-table entry count + blocked count:** the waiting-view
  tree gains two columns between Detail and Size - **Entries**
  (actionable record count: the supported script / value records,
  i.e. the real cheat options) and **Blocked** (the blocked record
  count of the same analysis). The analysis runs in the background:
  one daemon thread (`master_trainer/analysis_worker.py`, queue limit
  64, dedupe by table content sha, only tables with a bound process
  name are queued) through the tested `compile_table` plan path - no
  Lua execution, no target attach, the same static proof the corpus
  audit uses. The columns show "..." while pending and "-" on a named
  compile failure, the counts once analyzed; a blocked count > 0
  appends the bounded "N blocked" note to the detail column after the
  pin marker. Results persist in `table-analysis.json` (schema 1,
  under the state home, keyed by table content sha256, LRU-bounded to
  1024 entries, top-8 blocked reasons per table, 200-char error
  detail) - a content change re-analyzes, an unchanged table reuses
  the cached entry; the pure decision layer is
  `master_trainer/table_analysis.py` (`counts_from_plan` /
  `blocked_reasons_from_plan` / `ok_analysis` / `failed_analysis` /
  `AnalysisStore` with strict key-set + checksum + timestamp + count
  validation, `AnalysisRefusal`). The worker is not auto-started: the
  waiting view owns the lifecycle (start / resume + queue at the end
  of the view build, pause on trainer entry after the attach gate,
  stop + clear on close); the meta line shows the live
  "analyzing N table(s)" figure while the queue has work; the MT-22
  table-details window gains the analysis block (`table_details.py`
  `analysis` kwarg): pending / "N entries (M blocked) of T records" +
  top blocked reasons / "failed: <reason>". Display-side observation
  only - it never blocks, alters, or delays the MT-9 load gate, which
  re-checks the table independently at load time. Zero catalog effect
  (no table-parsing change).
- +69 tests (57 in `tests/test_native_master_analysis.py` new: the
  pure counts / reasons builders, the ok / failed analysis builders,
  the store's strict validation (unknown fields, wrong sha, bad
  counts, checksum mismatch), LRU eviction by `analyzed_at` with sha
  tie-break, the refusal codes, and the `active_workers()` live-worker
  registry lifecycle; 12 in
  `tests/test_native_master_ui_mt24.py` new: the column wiring +
  pending / failed / pinned / group-row shaping, the queue discipline
  (unbound tables never queued, rescan re-queues on content change
  only), the details-window analysis rows, the trainer-entry pause,
  the close stop + reference clear, the window-created default worker
  with the real compile path); plus the cross-module test-isolation
  fix - the shared Tk test teardown now stops every live analysis
  worker (registry in `analysis_worker.py`) before releasing the
  root, so window tests no longer leak worker threads into later
  engine/timing modules; full main suite 4,483 OK / 30 expected
  skips (4,414 from the 0.31 content + 69 new); catalog remeasure
  `blocked-catalog-032-analysis` (3-chunk deep-equal audit over the
  151 reference tables, 2026-11-06): 151/151 loaded, 0 load errors,
  117,809 total / 116,756 supported / 60,161 staged / 103,607
  actionable / 12,974 headings / 1,053 blocked - **zero delta** vs
  `blocked-catalog-031-status` (per-table count/reason/sha changes:
  0); feature matrix unchanged (42/42, 7,475/7,475 over
  `w4b4-case30-20261020081722Z`); AP-11 0/6,143. VERSION bumped to
  0.32 with the changelog entry in the same change. The 0.32 build
  `native-20261108T100731Z-a1d311e5` was cut from `main` @
  `bfcc3a3` (2026-11-08): in-build suite 4,483 OK / 30 expected
  skips, `ce_inputs: []`, `runtime_unverified` deliberately kept
  per gate; source ZIP `CT2Trainer-0.32-source.zip` sha256
  `f6cae57590d083e37308bc4a03b1046b8186617bdb0f98c88c9bc324404493d9`
  (14,426,224 bytes) - carries the MT-24 Entries / Blocked columns,
  `table_analysis.py` + `analysis_worker.py` (incl. the
  `active_workers()` live-worker registry), the two MT-24 test
  files, the mt23 worker-guard test fix (`bfcc3a3`) and the
  reviewable `master_trainer/UI.md` - and portable ZIP
  `CT2Trainer-0.32-windows-portable.zip` sha256
  `3a7980ba04f60f7cb93edce3cf5c723ba609ff55a00b1f866079101d3b7bc986`
  (49,699,633 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `6dc34408c8e5ecec1c2215c45da27ea22cc5c5ce5a9629267778b172d44d3485`,
  16,966,114 bytes, ships next to the converter). The first build
  attempt `native-20261108T090044Z-5b70a3af` (preserved) failed the
  in-build suite in `test_native_master_ui_mt23` with PermissionError
  [WinError 32] on a fixture unlink while the MT-24 analysis worker
  still held the file open; test fix `bfcc3a3` stopped the worker in
  the affected window tests before fixture mutations, and the
  re-run full main suite is green.

**0.31 released (build `native-20261105T080853Z-2e7f50a5`, cut from
`main` @ `2def12f`, 2026-11-05): Master Trainer per-table live
status + color coding + status filter (MT-23).**
The 0.31 feature was evaluated against online trainer front-end and
trainer-manager UX patterns (FLiNG per-trainer "Game Version" /
"Last Updated" / option-count metadata - per-table freshness and
state facts surfaced in the list are a recognized pattern; Game
Cheats Manager (dyang886) "smart launcher" - drop tables +
trainers, detect the installed games, associate trainer to game,
auto-update: the detection + trainer-to-game association are already
covered by MT-2/MT-17, auto-update is out of scope per the
offline/hash-verified build policy, and the Python + Tkinter
implementation corroborates the Master's stack; game-trainer-manager
(Karasukaigan) download/import/organize/search around a trainer
list; CheatDeck (SheffeyG) Steam Deck launch options - the
documented MT-7 route). Adopted: MT-23, the candidate deliberately
deferred in 0.26/0.27/0.29/0.30 ("per-table status / color-coding").
Remaining candidates (unchanged): the MT-21 multi-column trainer
grid and the entry-count / blocked-count columns (they need
background plan-analysis infrastructure).
- **MT-23 per-table live status + color coding + status filter:**
  the waiting-view Status column shows the table's state RIGHT NOW,
  not only the cached state of the last scan - one bounded `stat`
  per visible row per render against the index entry: `ok` /
  `running` (a bound process is up, the table loadable) / `changed`
  (the file drifted since the last scan) / `missing` (the file is
  gone) / `unreadable` (the last scan could not read/parse it, the
  named detail surfaces); cheapest fact first, live facts outrank
  the cached scan state - the same order the MT-9 gate proves at
  load time. Rows are color coded (the default colors for ok /
  running, amber `#e5c07b` for changed, red `#ff7b72` for missing /
  unreadable - the two tree tags configured in the waiting view),
  and the persisted "Status: all / ok / attention" header cycle
  (between the view button and the filter entry) filters the list
  to the loadable rows or to the rows the gate would refuse right
  now. `master-settings.json` schema 5 -> 6: `view_status` (one of
  `VIEW_STATUS_FILTERS`, mirrored by
  `table_status.VIEW_STATUS_FILTERS`); schema-5 documents promote
  with `view_status=""`, a schema-5 document carrying the field is
  refused as an unknown field (the MT-11/15/16/18 discipline).
  `MasterApp.set_view_settings` gains the 4th parameter
  `status_filter` (validated + re-persisted; every existing change
  point passes the current mode through, so sort/view/filter
  changes never reset the status filter); `_visible_tables()`
  applies the status filter between the query filter and the pin
  float; the meta line gains the active `status filter: X` part and
  the live `attention: N` count (how many indexed tables the MT-9
  gate would refuse right now - shown only when N > 0). The pure
  decision layer is `master_trainer/table_status.py`
  (`row_file_status` / `row_status` / `row_tag` /
  `filter_rows_by_status`, `ATTENTION_STATUSES`,
  `VIEW_STATUS_FILTERS` - no OS access, no index mutation); the
  in-app `ui_flow_text()` and the reviewable `master_trainer/UI.md`
  document the new header control, the live Status column and the
  persistence row.
- +28 tests (4 schema-6 state in `tests/test_native_master_state.py`
  + 24 in `tests/test_native_master_ui_mt23.py` new: the pure layer
  - the live file state per fingerprint, the running-loses-to-
  attention contract, the tag per code, the filter reshaping per
  mode + the named refusal, the constant mirror against the state
  schema; the Tk wiring - the cycle / persist / restore, the other
  UI changes keeping the mode, the live changed / missing flags +
  tags, the ok / attention row shaping, the meta line); full main
  suite 4,414 OK / 30 expected skips (4,386 from the 0.30 content +
  28 new); catalog remeasure `blocked-catalog-031-status` (3-chunk
  deep-equal audit over the 151 reference tables, 2026-11-05):
  151/151 loaded, 0 load errors, 117,809 total / 116,756 supported
  / 60,161 staged / 103,607 actionable / 12,974 headings / 1,053
  blocked - **zero delta** vs `blocked-catalog-030-details`
  (per-table count/reason/sha changes: 0); feature matrix unchanged
  (42/42, 7,475/7,475 over `w4b4-case30-20261020081722Z`); AP-11
  0/6,143. VERSION bumped to 0.31 with the changelog entry in the
  same change. The 0.31 build
  `native-20261105T080853Z-2e7f50a5` was cut from `main` @
  `2def12f` (2026-11-05): in-build suite 4,414 OK / 30 expected
  skips, `ce_inputs: []`, `runtime_unverified` deliberately kept
  per gate; source ZIP `CT2Trainer-0.31-source.zip` sha256
  `3bab9648208f6ed4cbafa919991cab19c7921597ac2075c5c8b964e17258c0f9`
  (14,398,817 bytes), portable ZIP
  `CT2Trainer-0.31-windows-portable.zip` sha256
  `df5581ec5e8b0c0b99abdf35b914f08ec138b4470234b48c615304419a970839`
  (49,679,202 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `811c0f85c143b632dd182646282ddb32c3293513a665eb62c8055f74f9c89dcb`,
  16,948,380 bytes, ships next to the converter).

**0.30 released (build `native-20261104T131114Z-11522f68`, cut from
`main` @ `2fbca94`, 2026-11-04): Master Trainer table details + live
load-gate preview (MT-22).**
The 0.30 feature was evaluated against online trainer front-end and
trainer-manager UX patterns (FLiNG per-trainer version / "Last
Updated" metadata, game-trainer-manager organize/search workflows,
Game Cheats Manager .ct handling FAQ, Cheat Happens Trainer Manager
v2 portable + last-used pinning - see the Master Trainer ROADMAP
"0.30 table details + load-gate preview" section). Adopted: MT-22.
Deliberately deferred (documented): the MT-21 multi-column trainer
grid, the entry-count / blocked-count columns and the per-table
status / color-coding.
- **MT-22 table details + live load-gate preview:** right-clicking
  a waiting-view row offers "Table details" first - a read-only
  Toplevel (title "Table details - <rel>", transient, non-resizable,
  Close button) with the indexed facts for the table: path,
  folder, size, modified, bound processes, index status (ok /
  unreadable: <reason>), pin state, last used (the persisted UTC
  timestamp or "never"), running PIDs (deduped, sorted, "not
  running" when none), content sha256 (last scan - first 12 hex +
  "...") - plus the on-demand `gate_table_for_load` re-check: the
  same pass MT-9 runs at load time, so a refusal shows the stable
  named code + displayable detail (a stale / changed / unreadable
  table is explained at inspection time, not only at load time); a
  passing gate proves the file matches the last scan. One window (a
  second open lifts + focuses instead of duplicating); closed on
  trainer entry with the rest of the waiting view; no index entry
  leaves a named status line instead of a window. The row builder
  is pure in `master_trainer/table_details.py` (`format_size` /
  `format_mtime` / `gate_line` - "not checked" / "OK (loadable -
  the file matches the last scan)" / "<code>: <detail>" with named
  fallbacks; `table_detail_lines` - the 11 ordered (label, value)
  rows); the only I/O is the bounded gate re-check under the load
  limit. The in-app `ui_flow_text()` and the reviewable
  `master_trainer/UI.md` document the new row-menu entry
  (keyboard map + table-tree section).
- +16 tests (`tests/test_native_master_ui_mt22.py`); full main
  suite 4,386 OK / 30 expected skips (4,370 from the 0.29 content +
  16 new); catalog remeasure `blocked-catalog-030-details`
  (chunked 64x3 audit over the 151 reference tables, 2026-11-04):
  151/151 loaded, 0 load errors, 117,809 total / 116,756 supported
  / 60,161 staged / 103,607 actionable / 12,974 headings / 1,053
  blocked - **zero delta** vs `blocked-catalog-029-trainer-focus`
  (per-table count/reason/sha changes: 0); feature matrix unchanged
  (42/42, 7,475/7,475 over `w4b4-case30-20261020081722Z`); AP-11
  0/6,143. VERSION bumped to 0.30 with the changelog entry in the
  same change. The 0.30 build
  `native-20261104T131114Z-11522f68` was cut from `main` @
  `2fbca94` (2026-11-04): in-build suite 4,386 OK / 30 expected
  skips, `ce_inputs: []`, `runtime_unverified` deliberately kept
  per gate; source ZIP `CT2Trainer-0.30-source.zip` sha256
  `091b379c132e277c19f519705dcccc4c0817e8e7e614e5baf2f14bbe3fe414a3`
  (14,387,690 bytes), portable ZIP
  `CT2Trainer-0.30-windows-portable.zip` sha256
  `f4476bb08e3e65e6db9cd35bfe7a72408a555b8525bd6a10f8b794f943083d54`
  (49,669,933 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `9d0a525a78dfbfffb906261ad42e435c5414cb6cb0189dd78c73910063f67643`,
  16,940,058 bytes, ships next to the converter).

**0.29 released (build `native-20261104T094808Z-50af0517`, cut from
`main` @ `de3e4ff`, 2026-11-04): Master Trainer UI/UX revamp (MT-19
trainer-focus mode + MT-20 discoverability).** The user field request of 2026-11-04 (the
waiting table list must shrink/collapse so the trainer items get
maximum space once a process is identified and the trainer
attaches; generally more accessible UI; the UI flow documented so
it can be reviewed/improved) was evaluated against the local
shared-root trainer handoff plus the standing trainer-manager UI
evaluations (Trinity profiles, Cheat Happens AURORA accessibility,
keyboard-shortcut databases, WCAG/platform accessibility guidance -
see the Master Trainer ROADMAP "0.29 trainer-focus + discoverability"
section). Adopted: MT-19, MT-20. Deliberately deferred (documented
candidate MT-21, separate cycle): the multi-column trainer grid -
the single-column canvas grid is the validated touch-first design
(`ui_rows.py` pure row model + `ui_layout.py` + the 1-D hit-testing,
exhaustively tested and shared with the standalone trainer); a
column layout rewrites the pure row model, the pagination and the
2-D hit-testing and changes the standalone trainer as well.
- **MT-19 trainer-focus mode:** the whole waiting view now lives in
  one container frame (`MasterWindow._waiting_frame`,
  `fill=both expand=True` on the shared root) - the header, the
  folder/meta/running lines, the table-tree frame and the status
  bar are all its children. `_enter_trainer()` destroys the
  container immediately after the engine is up (before the
  `TrainerWindow` is built) and drops every waiting-view widget
  reference, so the trainer row grid owns the full window instead
  of sharing it with the table list, and the poll loop / handlers
  never touch a destroyed widget (the poll tick already
  early-returns in trainer mode). The trainer-constructor failure
  path rebuilds the waiting view before `_fail_trainer_start()` so
  the waiting loop and its loop guard stay consistent;
  `_back_to_master()` is unchanged (destroy-all + rebuild). The
  open UI-flow Toplevel is closed with the teardown. +6 UI tests in
  `tests/test_native_master_ui_mt19.py`.
- **MT-20 discoverability:** the module function `ui_flow_text()`
  (headless-testable) is the plain-language UI-flow document - the
  same content as the reviewable `master_trainer/UI.md` in the
  package (ships in the source ZIP through the existing `.md`
  allowlist); the new "UI flow" header button opens it in a
  read-only Toplevel (single window: a second click lifts +
  focuses the open window instead of duplicating; closed on
  trainer entry). F5 re-scans the folder from anywhere in the
  waiting view (root binding, guarded no-op in trainer mode like
  the existing "/" binding). The table tree takes the initial
  focus on build (`focus_set` at the end of
  `_build_waiting_view`), so arrow keys and Enter work immediately
  without a first click. The "Retry load" re-arm moves out of the
  root-level button below the status strip into the status bar
  next to the attach toggle and the Recent button. +7 UI tests in
  `tests/test_native_master_ui_mt19.py`.
- Full main suite 4,370 OK / 30 expected skips; catalog zero
  delta `blocked-catalog-029-trainer-focus` (151/151 loaded, 0
  load errors, 117,809 total / 116,756 supported / 1,053 blocked,
  zero delta vs `blocked-catalog-028-pin`); feature matrix
  unchanged (42/42, 7,475/7,475 over
  `w4b4-case30-20261020081722Z`); AP-11 0/6,143. VERSION bumped to
  0.29 with the changelog entry in the same change. The 0.29 build
  `native-20261104T094808Z-50af0517` was cut from `main` @ `de3e4ff`
  (2026-11-04): in-build suite 4,370 OK / 30 expected skips,
  `ce_inputs: []`, `runtime_unverified` deliberately kept
  per gate; source ZIP `CT2Trainer-0.29-source.zip` sha256
  `2f5ce6e446f8d9885cd653580b5e194a2a0fc524eba7b5f684fe1f1a0e1da3d4`
  (14,378,934 bytes), portable ZIP
  `CT2Trainer-0.29-windows-portable.zip` sha256
  `98c63c368bc2cccd68335e9db94a3b897abbbb815730c97912e3068805fad226`
  (49,667,528 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `88e6ee99aa4c46973945e462ca956977e9942a1e8b30630aa2570107540f2de8`,
  16,937,063 bytes, ships next to the converter).

**0.28 released (build `native-20261103T161621Z-ea8fde2f`, cut from
`main` @ `d7f4cf0`, 2026-11-03): Master Trainer
pinned/favorite tables (MT-18).** The 0.28 feature
set was evaluated against online table/list UX patterns (VGC Shelf
"sort, pin, archive"; see the Master Trainer ROADMAP "0.27
waiting-view settings + process groups" follow-up research and the
adopted candidate). Adopted: MT-18. Deliberately deferred
(documented): entry-count / blocked-count columns, per-table
status / color-coding.
- **MT-18 pinned / favorite tables:**
  `master-settings.json` schema 4 → 5: `pinned_tables` (relative
  table paths, most recent pin first, capped at
  `PINNED_TABLES_LIMIT` = 25, each a non-empty string within the
  table-path length bound). Schema-4 documents promote on load
  with `pinned_tables=[]`; a schema-4 document carrying the field
  is refused as an unknown field (foreign schema, never silently
  promoted - the same discipline as MT-11/15/16). The pure
  `table_filter.pin_tables` reshaping of the already-sorted-and-
  filtered row set (never adds or drops tables): pinned rows first
  in pin order (casefolded comparison), the remainder keeps the
  input order, pin paths not in the row set (filtered out or
  gone) ignored. The row context menu offers "Pin to top" /
  "Unpin" (`MasterApp.set_table_pinned` validates - named
  `ValueError`s for cap / already pinned / not pinned - and
  re-persists immediately); a pinned table floats to the top of
  the list view and to the top of its process group in the
  grouped view (the pin set is applied after filter + sort,
  before the MT-17 grouping); the pin marker lives in the detail
  column ("pinned" / "pinned - PID …"), the first column stays
  the bare relative path (the row identity the load paths key
  off); a named refusal lands in the status line without a state
  change or a crash. +15 tests (4 schema-5 state + 4 pure pin +
  7 MT-18 UI).
- Full main suite 4,357 OK / 30 expected skips; catalog zero
  delta `blocked-catalog-028-pin` (151/151 loaded, 0 load errors,
  117,809 total / 116,756 supported / 1,053 blocked, zero delta
  vs `blocked-catalog-027-view`); feature matrix unchanged
  (42/42, 7,475/7,475 over `w4b4-case30-20261020081722Z`);
  AP-11 0/6,143. VERSION bumped to 0.28 with the changelog entry
  in the same change. The 0.28 build
  `native-20261103T161621Z-ea8fde2f` was cut from `main` @ `d7f4cf0`
  (2026-11-03): in-build suite 4,357 OK / 30 expected skips,
  `ce_inputs: []`, `runtime_unverified` deliberately kept
  per gate; source ZIP `CT2Trainer-0.28-source.zip` sha256
  `13f4b2222a83f9e4588d388b4120beaf8018a091a05364029ae2a950c0dabb1a`
  (14,363,765 bytes), portable ZIP
  `CT2Trainer-0.28-windows-portable.zip` sha256
  `d656835a69ece75ff6adaa5ce766385327fb9ec08d89837ad772425dafe91ce3`
  (49,658,473 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `c12dcea5bb8a609dae4df36f44827ab5269c9e1015cb723067ed98dc100bf99b`,
  16,929,732 bytes, ships next to the converter).

**0.27 released (build `native-20261103T145543Z-b29b3688`, cut from
`main` @ `8aa0815`, 2026-11-03): Master Trainer waiting-view
settings persistence (MT-16) +
process-grouped waiting view (MT-17).** The 0.27 feature set was
evaluated against online table/list UX patterns (playR, Universal
Game Launcher, GamesList Manager, Game Cheats Manager) and
recorded in `master_trainer/ROADMAP.md` ("0.27 waiting-view
settings + process groups"). Adopted: MT-16/17 (both
deliberately deferred in 0.26). Deliberately deferred
(documented): entry-count / blocked-count columns, per-table
status / color-coding.
- **MT-16 persisted waiting-view settings:**
  `master-settings.json` schema 3 → 4: `view_filter` (the raw
  filter entry text, at most `VIEW_FILTER_MAX` = 200 characters,
  "" = no filter), `view_sort` (one of the table_filter sort
  modes) and `view_mode` ("list" flat rows / "process" grouped by
  bound process name). Schema-1/2/3 documents promote on load
  with the documented defaults ("" / "name" / "list"); a
  schema-3 document carrying a view_* field is refused as an
  unknown field (foreign schema, never silently promoted - the
  same discipline as MT-11/MT-15). The format-level constants
  live in `master_state` (the attach-mode pattern), pinned
  against the pure layer by a test.
  `MasterApp.set_view_settings(filter_query, sort_mode,
  view_mode)` validates (named `ValueError`s) and re-persists
  immediately; the window restores all three from the persisted
  document at construction; every UI change point re-persists
  (filter `<KeyRelease>`, sort cycle, view cycle, Esc clear).
  +4 state tests (`tests/test_native_master_state.py`) + 5 UI
  tests (`tests/test_native_master_ui_mt16.py`).
- **MT-17 process-grouped waiting view:** the pure
  `table_filter.group_tables_by_process` reshaping of the
  already-sorted-and-filtered row set (never adds or drops
  tables): one parent row per casefolded bound process name (a
  table bound to several names appears once under each of
  them), the tables without a bound name under "(no process
  binding)" last, within-group order = the caller's sort order.
  The "View: list/process" cycle button sits between the sort
  button and the filter entry (persisted through MT-16); the
  tree (`show="headings"`) renders the group label + "N
  table(s)" count in values[0] of the parent row (the text item
  is invisible with headings). Group rows are display-only -
  double-click, Enter and the row context menu are gated by
  `_is_table_row`, so a group row never loads; the children load
  through the ordinary MT-10 path. +8 pure tests
  (`tests/test_native_master_table_filter.py`) + 5 UI tests
  (`tests/test_native_master_ui_mt16.py`).
- Full main suite 4,342 OK / 30 expected skips; catalog zero
  delta `blocked-catalog-027-view` (151/151 loaded, 0 load
  errors, 117,809 total / 116,756 supported / 1,053 blocked,
  zero delta vs `blocked-catalog-026-master-ui`); feature matrix
  unchanged (42/42, 7,475/7,475 over
  `w4b4-case30-20261020081722Z`); AP-11 0/6,143. VERSION bumped
  to 0.27 with the changelog entry in the same change. The 0.27 build
  `native-20261103T145543Z-b29b3688` was cut from `main` @ `8aa0815`
  (2026-11-03): in-build suite 4,342 OK / 30 expected skips,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
  source ZIP `CT2Trainer-0.27-source.zip` sha256
  `264b42d6c42dac1bb434c1d0591e82ac0bec69e61e1a1c75047c6aa58126f40e`
  (14,357,294 bytes), portable ZIP
  `CT2Trainer-0.27-windows-portable.zip` sha256
  `bfcf2abc885122dfa8653fcfd0046323e7112f59c0850958688e36e014ebc135`
  (49,654,613 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `9762c8bdc2298c16bd82779f206d9a885a449261a6428187c3bd2155fc5bf1bc`,
  16,929,639 bytes, ships next to the converter).

**0.26 released (build `native-20261103T112811Z-59a6b3d5`, cut from
`main` @ `c114ec2`, 2026-11-03): Master Trainer waiting-view
usability MT-13/14/15 (user request 2026-11-02/03) + live-target
takeover field fix.** With ~151
indexed tables (143 distinct hashes) the waiting view needed real
navigation; the feature set was evaluated against online table/list
UX patterns and recorded in `master_trainer/ROADMAP.md` ("0.26
waiting-view usability"). Adopted: MT-13/14/15. Deliberately
deferred (documented): group-by-process tree, persisted filter/sort,
entry-count / blocked-count columns.
- **MT-13 search / filter / sort:** new pure decision layer
  `table_filter.py` (no OS / index / state access): `filter_tables`
  (empty/whitespace query = the identity, input order preserved;
  otherwise a casefolded substring over the table's relative path
  AND any bound process name — a table matches when ANY bound name
  matches) and `sort_tables` (modes name / process / status; the
  casefolded relative path is the universal tie-breaker; in
  process mode unbound tables sort last; unknown mode raises
  `ValueError`). The waiting view renders
  `filter_tables(sort_tables(index.tables(), mode), query)`; row
  identity stays the relative path; the load picker and the
  auto-load path keep the full index. Filter and sort are
  session-only: they survive the trainer round-trip but are never
  persisted. Header filter entry (live re-render; meta line shows
  `filtered: N/M`) + "Sort: name/process/status" cycle button.
  +21 tests (`test_native_master_table_filter.py` + filter/sort UI
  tests in `test_native_master_ui_mt13.py`).
- **MT-14 keyboard flow:** double-click, Return and KP_Enter load
  the selected row through the ordinary MT-10 explicit-load path
  (named refusals included, no new load logic); arrow keys are
  built into the Treeview; "/" focuses the filter from anywhere in
  the waiting view (a no-op in trainer mode); Esc on the filter
  clears it and returns focus to the table list. +3 tests.
- **MT-15 recent tables + metadata columns:**
  `master-settings.json` schema 2 → 3: `recent_tables`, most recent
  first, capped at ten, each item `{"path", "at"}` with the
  persisted UTC timestamp `YYYY-MM-DDTHH:MM:SSZ` (strict format);
  schema-1/2 documents promote on load with `recent_tables=()`,
  and a schema-2 document carrying the field is refused as an
  unknown field. `MasterApp.remember_recent_table` (prepend /
  dedup / cap / persist) is called at all three successful load
  points. The meta line shows `recent: a, b, c (N more)`, the
  status frame gains the "Recent: <path>" one-click load button,
  and the tree gains indexed Size (compact B/KB/MB), Modified
  (local `YYYY-MM-DD HH:MM`) and Last-used columns; the window
  grows to 1160x600 (minsize 900x420). +18 tests.
- **Live-target takeover field fix:** when a stale `state.lock`
  blocks the startup and the owner session is proven dead in both
  observations while only target-side identities remain unproven
  (no other refusal reasons), the recovery archives the state
  byte-for-byte and, behind one user-confirmed prompt, attaches to
  the still-running game; saved wishes are re-applied (code-patch
  adopt idempotent; AOB ScanMiss entries surface named scan errors
  + bounded re-arm). Unprovable or live owner, foreign artifact or
  any extra reason keeps the strict refusal. +19 tests
  (`test_native_live_target_takeover.py`).
- Regression fixes: `_meta_text()` re-gained its `state: <home>`
  line; `test_empty_state_roundtrip` expects the schema-3
  `recent_tables: []` payload; the stored-folder test persists
  through the current-schema state (old schemas are refused by
  `master_state_to_bytes` by design); the rescan test asserts the
  7-value row. Full main suite 4,320 OK / 30 expected skips;
  catalog zero delta `blocked-catalog-026-master-ui` (151/151
  loaded, 0 load errors, 117,809 total / 116,756 supported /
  1,053 blocked, zero delta vs `blocked-catalog-026-live-target`);
  feature matrix unchanged (42/42, 7,475/7,475 over
  `w4b4-case30-20261020081722Z`); AP-11 0/6,143. VERSION bumped to
  0.26 with the changelog entry in the same change. The 0.26 build
  `native-20261103T112811Z-59a6b3d5` was cut from `main` @ `c114ec2`
  (2026-11-03): in-build suite 4,320 OK / 30 expected skips,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate;
  source ZIP `CT2Trainer-0.26-source.zip` sha256
  `3d62f80cdfb95d8439d4a2f2150002976795faad313fa75d47aeb4fb92bb49bd`
  (14,348,462 bytes), portable ZIP
  `CT2Trainer-0.26-windows-portable.zip` sha256
  `49be1d286999ed175737edb073c5ab83533c40cccc7e636685a256a0b07004b3`
  (49,653,968 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `895f937ed5c228c09b97edba28aa9dc4ad228abd58585f73080f40ab265bc031`,
  16,925,677 bytes, ships next to the converter).

**0.25 content on main (2026-11-02, root-direct on `main`): Master
Trainer user control MT-10/11/12 (user request 2026-11-02).** The
Master Trainer now gives the user explicit control over which table
loads and which process attaches - and lets the user detach and
re-attach on demand. The feature set was evaluated against online
all-in-one trainer front ends (OpenForge (openforge-aio), the CE 7.5
process picker as a local read-only behavior reference,
LaunchForge/auto-update loaders); the evaluation is recorded in
`src/ct2trainer/native/master_trainer/ROADMAP.md` ("Online feature
evaluation (2026-11-02)"). Adopted: MT-10/11/12. Deliberately
deferred (documented): global per-feature hotkeys, auto-update
(offline/hash-verified build policy), and concurrent multi-table
sessions (documented single-session model).

- **MT-10 (explicit table load):** a "Load table" header button in
  the waiting view and a per-row "Load this table" context menu.
  The table loads even while the bound process is not running yet
  (the plan compiles statically; the engine waits for the process to
  start). The last explicitly loaded table persists in the state
  home (`master-settings.json` schema 2, `last_table`) and is visible
  in the metadata line. `orchestrator.request_load()` carries stable
  named refusals (`not-in-index` / `table-unreadable` /
  `no-process-binding` / `process-snapshot-failed`): a refused load
  shows a named dialog + status line and never crashes; an explicit
  load bypasses the auto-load loop guard, but a failed explicit load
  still records the ordinary (name, PID) suppression.
- **MT-11 (process selection + persisted attach mode):** new
  `process_picker.py` - a pure decision layer (`candidate_processes`,
  `attach_decision` -> attach-direct / pick / wait,
  `make_pinned_memory_factory` - the injected factory honors the
  session PID pin, self-clears the pin once that PID exits, and
  falls back to the ordinary smallest-PID name-based attach). Attach
  modes: "auto" (default, legacy behavior - no picker, smallest PID)
  and "ask" (the process picker, one row per running candidate
  name + PID, is shown for every attach, even a single candidate).
  The "Attach: auto/ask" toggle button persists the mode
  (`master-settings.json` schema 2; schema-1 documents promote on
  load with the documented defaults `last_table=null`,
  `attach_mode="auto"`). Cancel semantics per origin: an auto-load
  pick defers the exact (name, PID) pair (Retry load re-arms), a
  table choice defers exactly like "Not now", an explicit load
  returns to the waiting status, and an attach after detach stays
  paused.
- **MT-12 (detach / user attach):** engine `pause_attach()` /
  `resume_attach()` / `attach_paused` - while paused the poll attach
  branch is gated (status "Detached; waiting for user attach", no
  attach attempts, session state/journals/wishes untouched; debug
  events `attach-paused` / `attach-resumed`; pausing refused with a
  named error while closed/blocked/busy). The new "Detach"/"Attach"
  header button exists in Master mode only (the standalone trainer
  header stays byte-identical; `TrainerWindow` gains the optional
  `detach_cb`). On "Attach": "ask" mode with running candidates
  opens the process picker (origin "attach") and the chosen PID
  pins the session, then the hold resumes; "auto" mode simply
  resumes the ordinary wait. A target exit while attached is
  unaffected.
- **Tcl test-harness hardening (test-only change, no product code
  change):** new `tests/native_tk_teardown.py` with
  `force_root_release()` - deterministic Tk-root teardown on the
  creator thread (destroy + drop named test-side references + forced
  main-thread `gc.collect`) applied in all 7 UI test modules (17
  root creations: `test_native_master_ui.py`,
  `test_native_master_ui_mt12.py`,
  `test_native_sc2_crash_observability.py`,
  `test_native_staged_options_ui.py`, `test_native_trainer_sounds.py`,
  `test_native_ui_button.py`, `test_native_ui_row_details.py`). It
  removes the intermittent `Tcl_AsyncDelete: async handler deleted
  by the wrong thread` abort observed in the 0.25 full-suite
  non-verbose runs (2026-11-02). Mechanism (verified against the
  CPython 3.12 tkinter source + faulthandler dump): `Tk.destroy()`
  destroys the toplevel window and deletes the widgets' Tcl
  commands, but the underlying Tcl interpreter (the `_tkinter`
  Tkapp behind `root.tk`) is only released when the Python Tk
  object is deallocated; the root/interpreter reference cycle (the
  `after` poll callback and button commands hold bound methods
  inside the interpreter; the bound methods hold the window; the
  children/master bookkeeping holds the root) survives until the
  next cyclic GC, which runs on whatever thread allocates; when a
  worker thread's GC cycle finalizes the interpreter, Tcl aborts the
  process off the creator thread. The fault dump showed the fatal
  thread as a freshly started thread running the GC collector while
  the main test thread was mid NASM assembly in
  `test_native_record_hotkeys`. Evidence: two full-suite
  non-verbose runs aborted with the Tcl fatal (exit 1, no summary,
  ~71% position); the verbose full run completed green (Ran 4258,
  OK, skipped=30); a middle-set repro (`test_native_master_ui` +
  `test_native_master_ui_mt12` + `test_native_os_hotkeys` +
  `test_native_rearm` + `test_native_record_hotkeys`, x10) did not
  reproduce; a clean-tree (0.24 @ `aba8b65`) full run completed
  without the Tcl fatal.
- **In-build reliability fix:** the first 0.25 in-build suite run
  (`native-20261102T181843Z-ddfb63f0`, 2026-11-02; 4,259 ran, 1
  error, the rest green) exposed a state-home dependence: the
  `run_master` cancel test read the machine's real state home (the
  in-build suite runs without the LOCALAPPDATA isolation of local
  dev runs) and, on a field-tested box with a stored `last_folder`,
  took the stored-folder reuse path with the mocked `tk.Tk`. Fixed:
  the test now uses an isolated state home, a new deterministic test
  covers the stored-folder reuse path, and the waiting-view status
  variable plus the table-picker selection variable in `master_ui.py`
  carry an explicit master (the window root) instead of relying on
  the tkinter default-root lifecycle.
- **Evidence:** +66 tests (`tests/test_native_master_process_picker.py`
  16, `tests/test_native_master_explicit_load.py` 13,
  `tests/test_native_attach_pause.py` 5,
  `tests/test_native_master_ui_mt12.py` 24, +7 schema-2 tests in
  `tests/test_native_master_state.py`, +1 state-home isolation test
  in `tests/test_native_master_ui.py`); full main suite
  **4,259 OK / 30 expected skips** (2026-11-02); catalog remeasure
  `blocked-catalog-025-master-ui` (chunked 64x3 audit over the 151
  reference tables, 2026-11-02): 151/151 loaded, 0 load errors,
  117,809 total / 116,756 supported / 60,161 staged / 103,607
  actionable / 12,974 headings / 1,053 blocked - **zero delta** vs
  `blocked-catalog-024-sounds` (per-table count/reason/sha changes:
  0). Feature matrix unchanged (42/42, 7,475/7,475 over
  `w4b4-case30-20261020081722Z`); AP-11 0/6,143. VERSION 0.25 +
  CHANGELOG 0.25 entry in the same change (root-direct on `main`,
  versioning rule). The 0.25 build
  `native-20261103T062439Z-f4c16be9` (cut from `main` @ `a861bfb`,
  2026-11-03; in-build suite 4,259 OK / 30 expected skips,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate)
  is the latest verified release; superseded 0.24 (build
  `native-20261102T102029Z-fe358e35`).

**0.23 Master Trainer roadmap complete (2026-11-01, branch
`native-0.23-master-roadmap` @ `b2d0344` + load-gate branch
`native-0.23-load-gate` @ `98a9226`; `main` @ `6e3ec98`; released in
build `native-20261101T145310Z-a160bae4`):** the remaining roadmap
items MT-6/MT-7/MT-8/MT-9 landed (two lane subagents + root
integration + the load-gate cycle), together with the waiting-view
observability work and the ask-on-first-start table-folder
parameter. No new trainer functionality - the Master stays a wrapper
around the tested engine.

- **MT-8 (frozen Master entry point):** `tools/native_master.py`
  frozen to `CT2Trainer-Master.exe` with the user-provided
  `Master_Trainer.ico` (windowed; lazy `master_ui` import so
  `--help` and the named exit-2 refusals never require tkinter; CLI
  mirrors the `master` subcommand). `build()` freezes it after the
  converter (no `CT2BASE1` marker - templates are converter-only),
  runs the CE-content `inventory()` scan, adds it to
  `payload-inventory.json`, the `build.json` outputs and the
  portable ZIP next to the converter - **the Master Trainer is now
  part of every build** (`scripts/Build-Native.ps1` unchanged: its
  single `build()` call emits the new EXE + ZIP entry). +8 tests.
- **MT-6 (per-table settings sidecar):** `settings_sidecar.py`
  `MasterSettingsStore` keyed by the table content sha256 (never by
  path), layout `<state home>/settings/<sha>.ct2trainer.json`;
  `load_for` returns `(document, [])` / `(None, reasons)` - absent
  file is normal, `SettingsRejection` reasons pass through
  displayable (never a silent reset to defaults), structural
  `SettingsError` named; `save_for` derives the known-id set from
  the document and refuses an all-empty draft with the named
  `nothing to persist`; reuses the tested `SettingsModel` unchanged.
  UI wiring: restore on load (a refused stored document is shown
  with its named reasons; the session continues without it), save on
  close (back-to-Master and window close). The on/off wish
  persistence itself stays on the engine state store (MT-4). +17
  sidecar tests, +2 UI wiring tests.
- **MT-7 (SteamOS / CheatDeck target route, documented-route scope):**
  `steamdeck_route.py` `AttachRoute` + `attach_gate` /
  `require_engine_attach` / `route_text`; Windows -> attach
  available through the unchanged native engine path; Linux/other ->
  named `DeckAttachUnavailableError` carrying the documented route
  (Proton-wrapped standalone CT2Trainer Windows trainer EXE,
  CheatDeck-compatible; the Linux/SteamOS Master runs detection +
  table index + waiting UI only; the owned Linux attach backend
  remains a later work item). The gate runs before any engine
  creation (a refusal fails the load through the orchestrator's
  named loop guard); the waiting view shows the route hint
  permanently on non-Windows. Deliberately NOT a Linux attach
  backend - the real Deck protocol run with exact build hashes stays
  root/user field work (`tests/deck/compatibility-matrix.md`). +13
  route tests, +3 UI wiring tests.
- **Waiting-view observability:** the waiting view now shows a
  compact metadata line (table counts, bound process names, last
  scan time, the state home location) and a live "Running now" line
  (bound processes visible in the latest snapshot, with PIDs);
  table rows for a running process are marked `running (PID n)`;
  `TickOutcome.running` carries the live bound-process list from the
  orchestrator tick (stable name/PID order on every tick path). +6
  orchestrator tests, +5 UI tests.
- **Ask on first start for the table folder** (CT source directory
  parameter): an explicit folder argument (CLI or frozen EXE)
  always wins; without one, the last-used folder persisted in the
  state home (`master-settings.json`, new checksum-bound
  `master_state.py` module with named `MasterStateRefusal` and
  tolerant load) is reused when it still exists; only a genuinely
  first start (or a stale stored folder) shows the directory
  picker. +15 tests, +3 UI tests.
- **MT-9 (load-time table compatibility & size gate,
  `master_trainer/table_gate.py`):** before any compile, the load
  re-proves the table file against its index entry - missing / not a
  regular file / stat-or-read failure / empty / over the 32 MiB load
  limit (33,554,432 bytes) / changed since the last scan (named
  stale refusal; Rescan re-arms) / not loadable by the tested
  `read_table` parser (malformed XML, DTD/entity input, unparseable
  legacy binary) / changed during analysis. Every refusal is a
  stable named code + displayable detail, cheapest-first; the
  default plan compiler raises the named `TableLoadGateRefusal`, so
  a table load failure is graceful even when the target process was
  found: no crash, named dialog + status line, the fail-closed loop
  guard records the exact (name, PID) pair (no hot-retry), Rescan /
  Retry load re-arm, and the picker is not re-issued for a failed
  pair. +16 gate tests, +2 orchestrator, +4 UI.
- **Same-day field fixes in the 0.23 content** (merged to `main`
  after the MT-9 merge): placeholder headings no longer create
  plan-level symbol dependencies (`28c9b57`, +10 tests - the
  WP-32/WP-33 non-actionable placeholder display-address requires are
  display metadata, never runtime writes) and the Sinking City 2
  hotkey-bridge field fix (0.22.1 lane: T1 named missing-export
  guard, T2 engine containment of bridge faults as deduped named
  warnings, T3 loop-thread close protocol, T7 persistence ordering;
  merge `4e9b95b`, +11 tests) - the fix for the SC2 0.19
  hotkey-bridge findings deferred in the 0.22 field cycle.
- Suite: +115 tests (4,061 -> 4,176); catalog zero delta across all
  three 0.23 remeasures (`blocked-catalog-023-master-roadmap` @
  `b2d0344`, `blocked-catalog-023-load-gate` @ `98a9226`,
  `blocked-catalog-023-field-fixes` @ `4e9b95b`, all 2026-11-01:
  151/151 loaded, 0 compile errors, 117,809 total / 116,756
  supported / 60,161 staged / 1,053 blocked / 0 load errors;
  per-table count and reason changes: 0).
- **Build record:** 0.23 shipped as build
  `native-20261101T145310Z-a160bae4` (cut from `main` @ `6e3ec98`,
  2026-11-01, canonical path; in-build suite 4,176 OK / 30 expected
  skips, `ce_inputs: []`, `runtime_unverified` deliberately kept per
  gate; source ZIP `CT2Trainer-0.23-source.zip` sha256
  `3360cab031cb1334dda71bb02a511170a9a70d1f583b5a8721624f46e24da464`
  (14,291,040 bytes), portable ZIP
  `CT2Trainer-0.23-windows-portable.zip` sha256
  `eec023ba09e8fcb80608736896f0477f4a783034046e6ad67514e96ed0a2905b`
  (49,609,916 bytes); the frozen `CT2Trainer-Master.exe` (sha256
  `e5822f688c653242a9f64bd92e4ba92529d485b89c11607cf20d32e728ca3c20`,
  16,895,048 bytes) ships in the run folder, the payload inventory
  and the portable ZIP next to the converter; the source ZIP carries
  `table_gate.py` + `tests/test_native_master_table_gate.py` and the
  final 0.23 changelog entry).

This page is a short explanation of the
evidence in
[central tracking](plans/TRACKING.md) and the
[progress ledger](documentation/native-progress.md).

## The goal

Support the intended **trainer and cheat behavior** of all 151 local
reference-table paths (143 distinct file hashes), without copying Cheat
Engine code, binaries or original table content into CT2Trainer. CE editor
and visual UI features are outside scope unless a table uses them to
cause a game effect. The [roadmap](plans/reference-table-100-roadmap.md)
defines the work and completion gates.

## Achievement and remaining work

| Area | Achieved | Still needed |
| --- | --- | --- |
| Independently built product | The 0.23 source and Windows portable ZIPs passed the offline build (build `native-20261101T145310Z-a160bae4`) with **4,176 tests OK, 30 expected skips**, and `ce_inputs: []`; the MT-9 gate tests + the placeholder-heading / SC2 hotkey-bridge field-fix test files + the 0.23 changelog entry ship in the source ZIP; the `master_trainer` subpackage + user-provided `Master_Trainer` icons ship in the source ZIP, and the frozen `CT2Trainer-Master.exe` ships in the portable ZIP next to the converter; the 0.20/0.20.1 branding icons remain embedded in the frozen converter EXE and the generated-trainer template EXE (verified by PE icon-resource extraction against the committed ICOs). | Keep the clean-room build and release checks green after each change. |
| Master Trainer (released in 0.21; roadmap complete in the 0.23 release; user control MT-10/11/12 as 0.25 content on main) | Full MT-1..MT-12 feature set on `main` (branch `native-0.20-master-trainer` merged at `9a725a8`; branch `native-0.23-master-roadmap` merged at `b2d0344`; load-gate branch `native-0.23-load-gate` merged at `98a9226`): incremental table index (folder + sub-folders, sha256-bound JSON in the state home, foreign-schema/tamper refusal), cross-platform read-only process watch, pure orchestrator (unique-match auto-load, multi-table picker, fail-closed loop guard, live `running` tick feedback, no picker re-issue for a failed pair), waiting UI (metadata line, live "Running now" line, running/PID tree markers) + handoff into the exact standalone trainer with `master_back`, per-table on/off persistence via the engine state store, MT-6 per-table settings sidecar keyed by table content sha256 (restore-on-load / save-on-close, named refusals), MT-7 documented SteamOS/CheatDeck target route (named fail-closed non-Windows attach refusals; NOT a Linux attach backend), MT-8 frozen `CT2Trainer-Master.exe` in every build, MT-9 load-time table compatibility & size gate (stable named refusals, graceful named load failure even when the target process was found, no hot-retry, Rescan / Retry re-arm), ask-on-first-start table-folder parameter (`master-settings.json` in the state home; explicit folder argument wins), `master` CLI subcommand, `Master_Trainer` icon contract. 306 master-trainer tests; full main suite 4,176 OK / 30 expected skips; catalog zero delta `blocked-catalog-023-field-fixes` (all three 0.23 remeasures). 0.25 content on main (2026-11-02, root-direct): MT-10 explicit table load, MT-11 process picker + persisted attach mode, MT-12 detach / user attach (details in the 0.25 section above); online feature evaluation record in `master_trainer/ROADMAP.md` (MT-10/11/12 adopted; global hotkeys / auto-update / concurrent multi-table sessions deliberately deferred); Tcl test-harness hardening (test-only `tests/native_tk_teardown.py`); in-build reliability fix (state-home isolation in the `run_master` cancel test + explicit-master Tk variables in `master_ui.py`; first in-build run `native-20261102T181843Z-ddfb63f0` exposed the dependence). 372 master-trainer tests (306 + 66: 16 process picker + 13 explicit load + 5 attach pause + 24 master UI MT-12 + 7 schema-2 + 1 state-home isolation); full main suite 4,259 OK / 30 expected skips; catalog zero delta `blocked-catalog-025-master-ui` (vs `blocked-catalog-024-sounds`). | User field test of the 0.25 content (explicit table load / process picker / detach; the 0.25 build is pending cut - 0.24 remains the latest verified build); MT-7 owned Linux attach backend + the real Deck protocol run with exact build hashes (root/user field work). |
| Synthetic feature coverage | **42/42** declared feature classes and **7,475/7,475** action weight covered across **30 synthetic tables**. | This metric does not establish support for every original table or a real game effect. Add synthetic cases when a new behavior is found. |
| Original reference tables | All **151/151** table paths load after the RT-3 legacy-binary CT loader (2026-10-23). Local static catalog (0.21 RT-5 item B/E remeasure, run `blocked-catalog-020-rt5-be`, 2026-10-31, frozen manifest `gap_inventory/reference-manifest.json`; +175 supported vs `blocked-catalog-020-icons` - the 175 `CodeEntry` records of the 22 CheatCodes tables now `code_patch` plan rows, zero newly blocked, zero reason changes) classifies **116,756 supported**, including **60,161 staged**, out of **117,809 plan entries**. | **1,053 entries are blocked** (was 1,351 after RT-4.3, 1,743 after RT-4.5, 1,778 after RT-4.6, 1,807 after RT-4.4, 1,858 after RT-4.1/RT-3 and 2,698 before RT-4.1; RT-4.2 cleared the last 298 rows - R4 Lua-runtime symbol providers re-staged, R7 GetAsyncKeyState bare calls, keep-first scope fallback; zero newly blocked). The 0.19 field-fix cycle changed no catalog row (no corpus table uses `moAlwaysHideChildren`). RT-5 item B (0.21) added exactly 175 supported `code_patch` rows with no blocked or staged movement; item E is runtime-only (zero catalog delta). Staged entries still need their runtime conditions proved. |
| Observed game effects | Owned fixtures and selected runtime chains have tests. | The AP-11 campaign has **0 of 6,143** game effects confirmed. Original-table behavior must be checked against pinned game builds or explicitly equivalent owned targets. |
| Final platforms | The 0.9.0-rc2 portable converter and a generated trainer were user-tested without CE or Python; later fixture tests cover many runtime paths. The 0.16 re-cut was field-tested 2026-10-21 (new WP-58 UI confirmed good; one cheat = table/build mismatch, no fix; the state-lock orphan after a blocked close was fixed in code the same day, see the ledger). The Sinking City 2 table-load warnings were made accurate in 0.16.1 (2026-10-21): table-version reference 45 → 46 field-verified, `{$LUA}`/`ShellExecute` wording now states the supported native behavior — the table itself loaded fine (see the ledger). The 0.16.1 field test (2026-10-21, Sinking City 2) exposed a startup block behind a stale `state.lock`: WP-57 hook journals with `captured_placeholders` failed the recovery schema; fixed on `main` 2026-10-22 (0.16.2, built as `native-20261022T160328Z-0423fb21` — see the ledger). The 0.16.2 field test (2026-10-22, Sinking City 2) exposed the next activation failure: the startup brick from the still-missing journal field `value_data_ranges` plus a module-snapshot retry aimed at the wrong Win32 code (mislabeled 24 instead of 1116) without backoff while the game was still loading DLLs (field log: Win32 error 24 nine ms after attach); both root causes fixed on `main` 2026-10-23, shipped as 0.16.3 (see the ledger). The 0.18 field tests (2026-10-28/29, Sinking City 2 and South of Midnight) exposed two more issues: access violations in the real Win32 hotkey-bridge seam (the windowed trainer process crashed) and staged pointer-chain value reads failing silently (blank "unavailable" without a log trace); the South of Midnight table exposed the staged-options UI gaps (staged-pending value rows still opened the inline editor, `moAlwaysHideChildren` not implemented); both fixed in 0.19 (2026-10-30, see the ledger). | The 0.16 re-cut has no recorded full clean-machine acceptance. Clean Windows and real Steam Deck/Proton/touch acceptance remain open. `runtime_unverified` stays set. |

**The 42/42 result is real, but it measures the synthetic feature matrix.**
The 1,053 blocked entries (after the RT-4.2 remeasure, was 1,351 after
RT-4.3, 1,743 after RT-4.5, 1,778 after RT-4.6, 1,807 after RT-4.4,
1,858 after RT-4.1/RT-3 and 2,698 at the Wave-4 baseline), staged
runtime behavior, and absent game-effect evidence are why the overall
100% reference-table goal is still open.
"Supported" in the static catalog means plan admission, not confirmed
effect in a game.

**Measurement note:** the committed `gap-report.json` carries the
current structured totals (30 tables, 6,143 actions); the stale
15/27-table prose fields were repaired in the RT-1 rebaseline
(2026-10-21) at the tool source, with the committed artifacts
regenerated under the pinned run id
`w4b4-case30-20261020081722Z`.

## What happens next

1. **Full-corpus baseline (RT-1, done 2026-10-21):** 151 paths /
   143 hashes frozen in `gap_inventory/reference-manifest.json` with
   exact EXE bindings; the catalog re-run on the 0.16 source reproduces
   the 2026-10-20 counts exactly (2,698 / 117,624, 1 legacy-binary load
   error).
2. **Explain every remaining block (RT-2, done 2026-10-21):** all 2,698
   blocked rows traced to terminal causes - 1,931 cascade rows (963
   hidden in-table registrations, 110 Lua-runtime symbols, 91
   no-registration triage, 128 legacy built-ins, 12 API exports, 624
   duplicate-provider cascades, 3 wildcard-cleanup conflicts) and 767
   direct rows in 27 classes; per-class contracts, risks, expected
   deltas and the RT-4 package split (RT-4.1…RT-4.6, sums to
   2,698) are in the roadmap's RT-2 root-cause map (lane final
   report, 2026-10-21 21:14, authoritative record).
3. **Implement the missing behavior (RT-3 to RT-5; RT-3, RT-4.1,
   RT-4.2, RT-4.3, RT-4.4, RT-4.5 and RT-4.6 done):** RT-3
   legacy-binary CT loading
   landed 2026-10-23 (clean-room parser, `SuperMeatBoy.CT` 10/10
   supported, table load 151/151); RT-4.4 value semantics landed
   2026-10-23 (catalog remeasure `blocked-catalog-rt44`: 1,858 ->
   1,807 blocked, 51 value-semantics rows cleared, zero newly
   blocked); RT-4.6 input legacy & authoring gaps landed 2026-10-24
   (catalog remeasure `blocked-catalog-rt46`: 1,807 -> 1,778 blocked,
   29 rows cleared, zero newly blocked, 218 reason-only changes onto
   the actionable per-symbol report); RT-4.5 AA directive & script
   coverage landed 2026-10-24 (catalog remeasure
   `blocked-catalog-rt45main`: 1,778 -> 1,743 blocked, 35 rows
   cleared, zero newly blocked, 7 reason-only changes); RT-4.3 address
   expression & identifier dialect landed 2026-10-26 (catalog remeasure
   `blocked-catalog-rt43-main`: 1,743 -> 1,351 blocked, 392 rows
   cleared, zero newly blocked, 12 reason-only changes; dedicated
   dialect tests now at 38); RT-4.2 runtime provider model landed
   2026-10-27 (catalog remeasure `blocked-catalog-rt42-main`: 1,351 ->
   1,053 blocked, 298 rows cleared, zero newly blocked, 28
   reason-only changes). The RT-5 API/construct inventory is
   documented in `documentation/rt5-api-inventory.md`; RT-5 item G
   (createThread/threadWait gate decision, option 2 — gate stays, no
   thread backend this milestone) and RT-5 item F (no-effect register
   ratification, `tests/test_native_rt5_no_effect_register.py` +22)
   both landed 2026-10-26, tests-only, zero catalog movement. RT-5
   item A (embedded `<Files>` extraction), item C (bounded
   process-info Lua API family), item C2 (dynamic addresslist records +
   custom AA directives) and item D (onOpenProcess/onTableLoad
   callback dispatch) landed 2026-10-28/29 (merges `479977c`,
   `0167825`, `dde9f04`, `9294bb8`; zero catalog delta at each step).
   The 0.19 field-fix cycle (2026-10-30, merge `fbe626f`) added the
   hotkey-bridge AV fix, value-read observability, the `describe` CLI
   and full South of Midnight staged-options support on top.
   Remaining: none — RT-5 item B (CheatCodes code-patch plan path,
   merge `9ef4a74`) and item E (`messageDialog` safe logged no-op,
   merge `b8bb4ee`) landed 2026-10-31, closing RT-5 in full (all
   inventory items A, B, C, C2, D, E, F, G landed; catalog
   `blocked-catalog-020-rt5-be`: 1,053 blocked of 117,809).
4. **Trainer UI feature (user request, done 2026-10-24):** the
   `Scripts` filter view (every script record, blocked/unselected
   included with their reason; headings and values hidden) and the row
   context menu (right-click / long-press) with script preview (the
   executed Auto Assembler / Lua source), copy-script, plain-language
   entry assessment and the unchanged Info dialog — merged on branch
   `native-0.17-ui-script-inspector` (suite 3,587 OK / 25 expected
   skips; catalog remeasure `blocked-catalog-ui-scripts` zero delta).
   Ships in the 0.17 build cut after the remaining RT-4.x merges
   (user decision 2026-10-24).
5. **Verify original effects and platforms (RT-6):** record activation,
   values, freeze, re-attach, disable/undo and one-shot behavior where
   applicable. Run the Windows and Deck protocols with exact build
   hashes and setups.
6. **Release only with evidence (RT-7):** full suite, offline build,
   source/frozen parity, `ce_inputs: []`, and updated tracking and
   verification records.

The current capability map is in the
[CE trainer-behavior assessment](documentation/ce-feature-parity-assessment.md).
Completed AP/WP plans are in [the archive](plans/archive/README.md).

## How this page is maintained

This page summarizes evidence; [TRACKING.md](plans/TRACKING.md) owns the
active goals and detailed counts. Update this page **in the same change**
whenever a work package changes the full-corpus catalog, a synthetic case
or feature-matrix result changes, a game-effect or platform observation is
recorded, or a release/build status changes. State the observation date,
build or source revision, input/run identifier and denominator. Keep
synthetic coverage, original-table static coverage and observed effects
separate. If evidence is missing or a measurement is stale, say so; do
not silently carry a prior percentage forward.
