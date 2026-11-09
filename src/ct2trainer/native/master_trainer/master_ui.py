"""Master Trainer UI: waiting mode, table picker, and trainer handoff.

One long-lived window.  Two modes share it:

- Waiting mode: shows the configured folder, the incremental table index
  (table, bound process names, status), and a live status line.  A poll
  tick asks the orchestrator for a decision; a unique table-for-process
  match auto-loads (the documented default), a multi-table match opens
  the picker, nothing matches and the line keeps ticking.
- Trainer mode: the exact ``TrainerWindow`` row grid of the standalone
  trainer, running on the same Tk root.  The header gains one extra
  button ("⬅ Master") that closes the engine cleanly and rebuilds the
  waiting view, so the same process can keep watching the folder;
  0.25 adds the "Detach" header button (MT-12) that detaches the live
  target and re-attaches to a user-chosen process in "ask" mode.

0.25 user control (MT-10/11/12): the waiting view gains the "Load
table" header button and the row context menu (explicit table load,
including while the bound process is not running yet), the persisted
attach-mode toggle (auto/ask) and the process picker for
multi-instance targets; the session pins the chosen PID through the
injected memory factory.

0.26 waiting-view usability (MT-13/14/15): the table list carries a
live filter (casefolded substring over table name AND bound process
name, pure layer in ``table_filter.py``) plus a name/process/status
sort cycle (session-only; the load picker and the auto-load path
keep the full index), the keyboard flow (double-click / Enter load
the selected row through the MT-10 explicit path; "/" focuses the
filter; Esc clears it; arrow keys are built in), and the rolling
recent list (master-state schema 3, most recent first, capped at ten,
feeds the meta line, the "Recent:" one-click load button and the
Last-used column; the indexed Size / Modified columns join the
tree).

0.29 trainer-focus + discoverability (MT-19/20): entering the trainer
collapses the whole waiting view (one container frame holds every
waiting widget; it is destroyed on trainer entry and rebuilt on the
way back) so the trainer row grid owns the full window instead of
sharing it with the table list; the waiting view gains the read-only
"UI flow" header button (the in-app copy of the UI.md flow document),
an F5 re-scan shortcut, the initial table-list focus (arrow keys and
Enter work immediately), and the "Retry load" re-arm moves into the
status bar next to the other waiting controls.

0.30 table details + load-gate preview (MT-22): right-clicking a
waiting-view row offers "Table details" first - the read-only
Toplevel with the indexed facts for that table (path, folder, size,
modified, bound processes, index status, pin, last used, running
PIDs, content sha) plus the on-demand load-gate re-check (the same
gate_table_for_load pass MT-9 runs at load time, named refusal code +
displayable detail) so the user can inspect a table before loading
it; the row builder is pure in ``table_details.py``.

0.31 per-table live status + color coding + status filter
(MT-23): the waiting-view Status column shows the table's state
RIGHT NOW, not only the cached state of the last scan - one bounded
stat per visible row per render (the folder content may have drifted
in between) against the index entry: ok / running / changed /
missing / unreadable, cheapest fact first, live facts outranking the
cached scan state (the same order the MT-9 load gate proves at load
time); the rows are color coded (the default colors for ok /
running, an amber warning for changed, an error red for missing /
unreadable), and the persisted "Status: all / ok / attention"
header cycle filters the list to the loadable rows or to the rows
the gate would refuse right now (master-state schema 6,
view_status); the pure decision layer is ``table_status.py``.

0.32 per-table entry count + blocked count (MT-24): the waiting
view gains the Entries / Blocked columns - the per-table entry
counts of the plan compile (the actionable script / value records,
i.e. the real cheat options, and the blocked records), computed in
the background by one daemon thread (``analysis_worker.py``)
through the tested ``compile_table`` plan path (no Lua execution,
no target attach; a failed compile is a named, persisted failure -
the columns show the failed marker, the details window shows the
reason and the top blocked reasons).  The persisted
``table-analysis.json`` document (schema 1, under the state home,
keyed by the table content sha256, bounded entries / reasons) with
its pure decision layer is ``table_analysis.py``; the worker
pauses on trainer entry, resumes + re-queues with the waiting
view, and the meta line shows "analyzing N table(s)".

0.33 table folder auto-rescan (MT-25): the waiting view re-runs
the existing incremental scan (the same ``(size, mtime_ns)`` + sha256
short-circuit contract as the manual Rescan) on a bounded
background interval (``AUTO_RESCAN_INTERVAL_SECONDS`` = 30 s) so
added / changed / removed tables show up without a manual F5.
The persisted on/off flag lives in the master state (schema 7,
``auto_rescan``, default true) and is toggled by the status-bar
"Auto-rescan: on/off" button.  The scan is one stat pass per
interval (no OS file-watcher, cross-platform), pauses on trainer
entry exactly like the MT-24 analysis worker, is restarted by a
manual rescan or a folder change, and has zero effect on the load
path (the MT-9 gate re-checks the table independently at load
time).

0.35 per-table notes / tags (MT-27): the waiting view gains a
Note column (note text truncated, tags in brackets) fed by the
persisted ``table-notes.json`` document (schema 1, under the state
home, keyed by the table content sha256 - the same identity as the
MT-24 analysis document).  The row context menu offers "Edit
note..." between load and pin: a small Toplevel with the note
(multi-line, bounded by ``NOTE_MAX_LEN``) and a comma-separated
tag entry (bounded by ``TAGS_LIMIT`` / ``TAG_MAX_LEN``); a named
refusal at save time (note over the limit, a tag too long, too
many tags) is shown in the dialog's own label while the persisted
document stays untouched; a table without a content sha (unreadable
/ never scanned) is refused in the status line.  The waiting-view
filter also matches the note text and tags, and the MT-22 details
window shows the note / tag rows.  No load-path effect.

0.36 multi-column trainer grid (MT-21): the trainer row grid can
run in up to three side-by-side columns.  The requested column
count (1 / 2 / 3, default 1) persists in the master state (schema 9,
``grid_columns``) and is handed to the trainer window on table
load; the trainer header gains the "Columns: N" cycle button
(master only - the standalone trainer header stays byte-identical
and always renders the single column).  The pure grid layer lives
in ``ui_rows`` (``build_grid`` / ``effective_columns`` /
``column_layout`` / ``row_units`` / ``flow_units``): a narrow window
renders fewer columns than requested (a column never falls below
the 320 px floor), sections are never split across columns, and the
one-column path is byte-stable against the pre-0.36 renderer.

All waiting-mode logic lives in the pure orchestrator; this module is
Tk wiring plus the picker Toplevel.
"""
from __future__ import annotations

import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ... import __version__
from ..ui import (BG, BG_HEADER, BG_CARD, FG, FG_DIM, POLL_MS,
                  TrainerWindow, trainer_title)
from ..engine import (TrainerEngine, StaleStateRecoverable,
                      StaleArtifactsRecoverable, LiveStateConflict,
                      perform_stale_recovery)
from ..window_icon import window_icon_path
from ..about_ui import repo_link
from .orchestrator import (MasterOrchestrator, STATE_ACTIVE,
                           STATE_CHOOSING, TickOutcome,
                           ExplicitLoadRefusal)
from .master_state import (MASTER_STATE_SCHEMA, MASTER_STATE_FILENAME,
                           ATTACH_MODE_ASK, ATTACH_MODE_AUTO,
                           GRID_COLUMN_MODES, PINNED_TABLES_LIMIT,
                           RECENT_TABLES_LIMIT, VIEW_FILTER_MAX,
                           VIEW_STATUS_FILTERS, MasterState,
                           load_master_state, save_master_state)
from .table_filter import (SORT_MODES, VIEW_MODES, UNBOUND_PROCESS_LABEL,
                           filter_tables, group_tables_by_process,
                           pin_tables, sort_tables)
from .table_status import (ATTENTION_STATUSES, filter_rows_by_status,
                           row_file_status, row_status, row_tag)
from .process_picker import (DECISION_PICK, attach_decision,
                             candidate_processes,
                             make_pinned_memory_factory)
from .process_watch import names_match
from .settings_sidecar import MasterSettingsStore
from .table_analysis import (AnalysisStore, blocked_column_text,
                             entries_column_text)
from .table_notes import (NotesRefusal, NotesStore, TAGS_LIMIT,
                          TAG_MAX_LEN, note_column_text, parse_tags,
                          sha256_key_ok)
from .analysis_worker import AnalysisWorker
from .steamdeck_route import (attach_gate, require_engine_attach,
                              DeckAttachUnavailableError)

WAIT_POLL_MS = 1000
# MT-25 (0.33): the table-folder auto-rescan interval.  One bounded
# incremental reconcile (the same (size, mtime_ns) + sha256 short-circuit
# contract as the manual Rescan) per interval while the waiting view is
# open and auto-rescan is enabled.  Deliberately conservative: the scan
# is a single stat pass over the folder, so 30 s keeps the overhead
# negligible while still surfacing added / changed / removed tables
# quickly.  No OS file-watcher API - polling only, cross-platform.
AUTO_RESCAN_INTERVAL_SECONDS = 30


def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def master_title() -> str:
    return "CT2Trainer " + __version__ + " — Master Trainer"


def ui_flow_text() -> str:
    """MT-20 (0.29): the read-only in-app UI-flow reference.

    The same plain-language flow document as the reviewable UI.md next
    to this module, so the user can read, review and improve the flow
    from inside the app (the "UI flow" header button opens it).  Keep
    this text aligned with UI.md: a change to the flow updates both."""
    return (
        "CT2Trainer Master Trainer - UI flow\n"
        "====================================\n\n"
        "One long-lived window with two modes.  Waiting mode shows the "
        "table index; trainer mode runs the exact standalone-trainer row "
        "grid.  They share one Tk root: entering the trainer collapses "
        "the whole waiting view (the table list no longer competes for "
        "window space), and going back rebuilds it.\n\n"
        "1) WAITING MODE\n"
        "   Header, left to right: title; filter box (casefolded "
        "substring over table name AND bound process name); Status "
        "cycle (all / ok / attention - the live loadability filter, "
        "persisted); View cycle (list <-> process groups); Sort cycle "
        "(name / process / status); the project link; Load table; "
        "Folders... (the folder manager: add / remove / set primary "
        "among the indexed table folders - several folders can be "
        "indexed at once, primary first); Rescan; UI flow (this "
        "window); Close.\n"
        "   Below the header: the folder line (the primary folder, "
        "the total folder count with several indexed, and any scan "
        "problem), the meta line (table counts across the indexed "
        "folders, the live attention count, the "
        "live 'analyzing N table(s)' figure while the background plan "
        "analysis has work, state home, and the attach route on "
        "non-Windows), and the live "
        "'Running now' line (which bound processes are visible right "
        "now, with PIDs).\n"
        "   The table tree, one row per table: Table (relative path), "
        "Folder (the indexed folder the table came from), Process "
        "name(s), Status (live right now: "
        "ok / running / changed / missing / unreadable - the same "
        "facts the load gate proves at load time; changed is an "
        "amber warning, missing / unreadable are red), Detail (PID, "
        "'pinned' marker, the 'N blocked' note, or the attention / "
        "unreadable reason), Entries (the actionable entries of the "
        "background plan analysis - the supported script / value "
        "records, i.e. the real cheat options; '…' while analyzing, "
        "'–' on a named failure), Blocked (the blocked records of "
        "the same analysis), Size, Modified, Last used, Note (the "
        "persisted per-table organization metadata - the note text "
        "truncated to one line plus the tags in brackets; empty while "
        "no note exists).  In 'process' view the tables group under "
        "their bound process name (unbound last); group rows are "
        "display-only.\n"
        "   Status bar, left to right: the status line (waiting for "
        "which process, last error); Attach mode toggle (auto/ask, "
        "persisted); Auto-rescan toggle (on/off, persisted - while "
        "on the folder is re-scanned every 30 s so added / changed "
        "/ removed tables show up without a manual F5; paused while "
        "a trainer is attached, restarted by a manual rescan or "
        "folder change); Retry load (re-arm auto-load after a "
        "deferred choice); Recent: <table> (one-click re-load, only "
        "when a recent table exists).\n"
        "   Keyboard: '/' focuses the filter; Esc clears it and returns "
        "focus to the list; F5 re-scans the indexed folders; arrow keys "
        "navigate "
        "the list (it takes the initial focus); Enter or double-click "
        "loads the selected row; right-click a row for the context menu "
        "(table details - the read-only inspection window with the "
        "live load-gate preview, the entry analysis and the note / "
        "tag rows, load, edit note - the small dialog for the "
        "per-table note and the comma-separated tags, saved with the "
        "table's content hash, pin to top / unpin).\n"
        "   Auto-load: the poll tick asks the orchestrator.  A unique "
        "table-for-process match loads by itself (the documented "
        "default).  A multi-table match opens the picker.  Nothing "
        "matches and the line keeps ticking.\n"
        "   Auto-rescan: while the toggle is on, the tick re-runs the "
        "incremental scan of every indexed folder every 30 s (one stat "
        "pass per folder - added / changed / removed tables show up "
        "automatically); a manual rescan (F5), a folder add / remove / "
        "set-primary, or the waiting-view rebuild restarts the "
        "interval.  Paused while a trainer is attached.\n\n"
        "2) LOADING A TABLE\n"
        "   Any of these starts a load through the same path (named "
        "refusals included, never a crash): the auto-load above; the "
        "Load table header button; right-click / Enter / double-click a "
        "row; the Recent button.  The explicit paths also work while "
        "the bound process is not running yet - the engine then waits "
        "for it.\n"
        "   Attach mode: 'auto' attaches to the documented smallest-PID "
        "process; 'ask' opens the process picker first (even for a "
        "single running candidate).  The choice is persisted and "
        "applies to the next load.  When several instances of the "
        "bound process run, the picker lists them and the chosen PID is "
        "pinned for the session (falling back to the name-based attach "
        "once that PID exits).\n"
        "   Startup recovery: if a previous session left a stale state "
        "lock or unfinished receipts, the trainer offers to recover "
        "(archive the old state byte-for-byte) - decline and the load "
        "fails with the state preserved; accept and it archives and "
        "starts.  If a live session conflict is detected (another "
        "trainer still owns the state), the load is refused and the "
        "other trainer must be closed first.\n\n"
        "3) TRAINER MODE\n"
        "   The exact standalone-trainer row grid, now owning the full "
        "window (the waiting list is hidden).  Rows: switch rows (tap "
        "toggles), value rows (tap the value to expand the inline "
        "editor), group section headers (chevron + counter + group "
        "toggle where one exists), and dim info rows (blocked or "
        "unselected records).  The header gains 'Detach' (detach the "
        "live target and re-attach to a user-chosen process), "
        "'Columns: N' (the trainer grid column count cycle "
        "1 -> 2 -> 3 -> 1, persisted; a narrow window renders fewer "
        "columns than requested, and sections never split across "
        "columns) and '< Master' (below).\n\n"
        "4) BACK TO MASTER\n"
        "   The '< Master' button closes the engine cleanly and "
        "rebuilds the waiting view, so the same process keeps watching "
        "the folder.  The per-table settings sidecar is saved on the "
        "way out.  An unclean close keeps the state journals and shows "
        "the cleanup warning.\n"
        "   Detach: keeps the trainer window open, releases the live "
        "target, and - in 'ask' mode - re-attaches to a user-chosen "
        "process.\n\n"
        "5) WHAT IS REMEMBERED (persisted)\n"
        "   Waiting-view settings (filter, sort, view mode, status "
        "filter), the trainer grid column count (the trainer 'Columns: "
        "N' setting), the pinned "
        "/favorite tables, the rolling recent list, the attach mode, "
        "the table folders (the indexed folder list, primary first), "
        "the per-table plan-analysis results "
        "(keyed by the table content hash, LRU-bounded), the "
        "per-table notes / tags (keyed by the table content hash, "
        "LRU-bounded) and the per-table settings sidecar (keyed by "
        "the table content hash, never the path) all survive "
        "restarts under the state home.  "
        "Only confirmed ON toggles are persisted "
        "as saved wishes; a failed enable stays visibly inactive.\n\n"
        "6) FAILURE STATES\n"
        "   Every refusal is named and lands in the status line (plus a "
        "dialog where the context needs it) - never a crash.  An "
        "unrecoverable startup leaves the state folder preserved for "
        "manual recovery.  'Retry load' re-arms a deferred auto-load.  "
        "A table whose background plan analysis fails is shown with the "
        "failed marker and the named reason (in the row and in the "
        "details window) - display-side only, the load gate re-checks "
        "the table independently at load time.\n"
    )


def _default_state_home() -> str:
    import os
    from pathlib import Path
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_STATE_HOME")
    if base:
        return str(Path(base) / "CT2Trainer" / "native" / "master-trainer")
    return str(Path.home() / ".local" / "state" / "CT2Trainer" / "native" / "master-trainer")


def _dedupe_folders(folders: list[str]) -> list[str]:
    """MT-26 (0.34): unique resolved folder list, casefold-deduped,
    order preserved (the first occurrence wins)."""
    out: list[str] = []
    seen: set[str] = set()
    for folder in folders:
        if not folder:
            continue
        key = folder.casefold()
        if key not in seen:
            seen.add(key)
            out.append(folder)
    return out


class MasterApp:
    """Owns the table folders + multi-root index + orchestrator for one
    Master window (MT-26, 0.34)."""

    def __init__(self, folder, *, state_home: str | None = None,
                 debug_log: bool = False, poll_ms: int = WAIT_POLL_MS,
                 lister=None, plan_compiler=None, state_dir_factory=None,
                 folders=None):
        from pathlib import Path
        from .table_index import RootIndexSet, load_index_set, reconcile
        from .process_watch import default_process_lister
        # MT-26 (0.34): the Master indexes several table folders at once.
        # ``folder`` is the primary (first) root; ``folders`` are the extra
        # roots, appended in order.  Every root keeps the same incremental
        # reconcile contract (one stored per-root index, (size, mtime_ns) +
        # sha256 short-circuit); the merged RootIndexSet orders them in user
        # order (first = primary) and exposes one merged surface.
        primary = str(Path(folder).expanduser().resolve())
        extra = [str(Path(f).expanduser().resolve()) for f in (folders or [])]
        self.folders: list[str] = _dedupe_folders([primary] + extra)
        self.folder = self.folders[0] if self.folders else ""
        self.state_home = str(Path(state_home or _default_state_home()))
        self.debug_log = debug_log
        self.poll_ms = poll_ms
        self.closed = False
        self.last_scan_at: str | None = None
        index_path = Path(self.state_home) / "tables-index.json"
        try:
            stored_set = load_index_set(index_path)
        except Exception:
            stored_set = RootIndexSet()
        stored_by_root = {ix.root.casefold(): ix for ix in stored_set.indexes}
        indexes: list = []
        changes: list = []
        errors: dict[str, str] = {}
        for root in self.folders:
            prior = stored_by_root.get(root.casefold())
            result = reconcile(root, prior)
            indexes.append(result.index)
            changes.extend(result.changes)
            if result.scan_error:
                errors[root] = result.scan_error
        self.index = RootIndexSet(indexes)
        self.last_changes = tuple(changes)
        self.scan_errors = errors
        self.scan_error = errors.get(self.folder) if self.folder else None
        self.last_scan_at = _utc_now()
        # MT-10/11 (0.25): stored preferences (last explicitly loaded
        # table, attach mode) from the master-state document; an absent
        # or refused document means the documented defaults.
        state = load_master_state(Path(self.state_home)
                                  / MASTER_STATE_FILENAME)
        self.last_table = state.last_table if state is not None else None
        self.attach_mode = (state.attach_mode if state is not None
                            else ATTACH_MODE_AUTO)
        # MT-15 (0.26): the rolling recently loaded tables (most recent
        # first; empty on a fresh or refused state home).
        self.recent_tables = (tuple(state.recent_tables) if state is not None
                              else ())
        # MT-16 (0.27): the persisted waiting-view settings (schema 4):
        # the filter query, the sort mode and the display mode.  A fresh
        # or refused state home takes the documented defaults ("" /
        # "name" / "list").
        self.view_filter = (state.view_filter if state is not None else "")
        self.view_sort = (state.view_sort if state is not None
                          else SORT_MODES[0])
        self.view_mode = (state.view_mode if state is not None
                          else VIEW_MODES[0])
        # MT-18 (0.28): the persisted waiting-view pin set (schema 5):
        # relative table paths, most recent pin first; a fresh or
        # refused state home takes the documented default (no pins).
        self.pinned_tables = (tuple(state.pinned_tables) if state is not None
                              else ())
        # MT-23 (0.31): the persisted waiting-view status-filter mode
        # (schema 6): "" (all) / "ok" (the loadable rows) / "attention"
        # (the rows the MT-9 load gate would refuse right now); a fresh
        # or refused state home takes the documented default "".
        self.view_status = (state.view_status if state is not None else "")
        # MT-25 (0.33): the persisted table-folder auto-rescan flag
        # (schema 7); a fresh or refused state home takes the
        # documented default True.
        self.auto_rescan = (state.auto_rescan if state is not None else True)
        # MT-21 (0.36): the persisted trainer grid column count
        # (schema 9); a fresh or refused state home takes the
        # documented default 1 (the single-column layout).
        self.grid_columns = (state.grid_columns if state is not None else 1)
        # MT-24 (0.32): the background plan-analysis cache under the
        # state home (table-analysis.json, schema 1, keyed by the
        # table content sha256).  The analysis worker is NOT started
        # here - the window starts it with the waiting view
        # (deterministic tests); until then the Entries / Blocked
        # columns show the pending marker.
        self.analysis_store = AnalysisStore(self.state_home)
        self.analysis_worker = None
        # MT-27 (0.35): the per-table notes/tags sidecar under the
        # state home (table-notes.json, schema 1, keyed by the table
        # content sha256 - the same identity as the analysis
        # document, so a note follows a content-identical file across
        # roots and renames).  An absent or refused document means
        # the documented empty state (no notes).
        self.notes_store = NotesStore(self.state_home)
        self.lister = lister if lister is not None else default_process_lister()
        self.plan_compiler = plan_compiler
        self.state_dir_factory = state_dir_factory
        if plan_compiler is None:
            from ..compiler import compile_table
            from .table_gate import TableLoadGateRefusal, gate_table_for_load
            app = self

            def plan_compiler(entry, process_name):
                # MT-9 load gate: re-prove the table file (compatibility +
                # size + drift vs the index entry) at the moment the load
                # is requested.  A refusal raises the named refusal, so
                # the orchestrator's fail-closed loop guard records the
                # exact (name, PID) pair: no crash and no hot-retry even
                # when the target process was found (visible in the
                # status line + error dialog; Rescan/Retry load re-arm).
                # MT-26 (0.34): the table file lives under the entry's
                # index root (multi-root), falling back to the primary
                # folder for root-less entries.
                base = (getattr(entry, "root", "")
                        or (app.folders[0] if app.folders else ""))
                path = Path(base) / entry.relative_path
                result = gate_table_for_load(path, entry)
                if not result.ok:
                    raise TableLoadGateRefusal(result.code, result.detail)
                return compile_table(path, process_name, architecture="x64",
                                     debug_log=debug_log)
            self.plan_compiler = plan_compiler
        self.orchestrator = MasterOrchestrator(self.index, self.lister,
                                               self.plan_compiler)

    def index_path(self):
        from pathlib import Path
        return Path(self.state_home) / "tables-index.json"

    def state_path(self):
        """The master-state document (last-used folder) in the state home."""
        from pathlib import Path
        return Path(self.state_home) / MASTER_STATE_FILENAME

    def persist_state(self) -> None:
        """Remember the current table folders plus the MT-10/11/15/16/18
        preferences (last explicit table, attach mode, rolling recent
        tables, waiting-view filter/sort/display mode, pin set) for the
        next start (best effort, like the index persistence).  MT-26
        (0.34): ``table_folders`` carries the indexed folders in user
        order (primary first); ``last_folder`` mirrors the primary."""
        try:
            save_master_state(MasterState(
                MASTER_STATE_SCHEMA,
                self.folders[0] if self.folders else None,
                last_table=self.last_table,
                attach_mode=self.attach_mode,
                recent_tables=tuple(self.recent_tables),
                view_filter=self.view_filter,
                view_sort=self.view_sort,
                view_mode=self.view_mode,
                pinned_tables=tuple(self.pinned_tables),
                view_status=self.view_status,
                auto_rescan=self.auto_rescan,
                table_folders=tuple(self.folders),
                grid_columns=self.grid_columns),
                self.state_path())
        except Exception:
            pass

    def set_attach_mode(self, mode: str) -> None:
        """Switch the persisted attach mode (MT-11) and re-persist it."""
        if mode not in (ATTACH_MODE_AUTO, ATTACH_MODE_ASK):
            raise ValueError("attach mode must be 'auto' or 'ask'")
        self.attach_mode = mode
        self.persist_state()

    def set_auto_rescan(self, enabled: bool) -> None:
        """MT-25 (0.33): switch the persisted table-folder auto-rescan
        flag and re-persist it."""
        if type(enabled) is not bool:
            raise ValueError("auto-rescan flag must be a boolean")
        self.auto_rescan = enabled
        self.persist_state()

    def set_grid_columns(self, columns: int) -> None:
        """MT-21 (0.36): persist the trainer grid column count
        (schema 9) and re-persist it.

        ``columns`` must be one of ``GRID_COLUMN_MODES`` (1, 2 or 3);
        a window too narrow for the request renders fewer columns than
        requested (``ui_rows.effective_columns``).  Invalid values
        raise the named ValueError, so the UI never persists what it
        would not render.
        """
        if type(columns) is not int or columns not in GRID_COLUMN_MODES:
            raise ValueError("grid columns must be 1, 2 or 3 (got "
                             + repr(columns) + ")")
        self.grid_columns = columns
        self.persist_state()

    def set_view_settings(self, filter_query: str | None, sort_mode: str,
                          view_mode: str, status_filter: str = "") -> None:
        """MT-16 (0.27) + MT-23 (0.31): persist the waiting-view settings
        (schema 4, + the status-filter mode, schema 6).

        ``filter_query`` is the raw filter entry text ("" means no
        filter); ``sort_mode`` / ``view_mode`` must be one of the
        documented modes; ``status_filter`` is one of
        ``VIEW_STATUS_FILTERS`` ("" = all, "ok" = the loadable rows,
        "attention" = the rows the MT-9 load gate would refuse right
        now).  Invalid values raise the named ValueError, so the UI
        never persists what it would not render.
        """
        if sort_mode not in SORT_MODES:
            raise ValueError("unknown view sort mode: " + repr(sort_mode)
                             + " (expected one of "
                             + ", ".join(SORT_MODES) + ")")
        if view_mode not in VIEW_MODES:
            raise ValueError("unknown view mode: " + repr(view_mode)
                             + " (expected one of " + ", ".join(VIEW_MODES)
                             + ")")
        if status_filter not in VIEW_STATUS_FILTERS:
            raise ValueError("unknown status filter mode: "
                             + repr(status_filter)
                             + " (expected one of "
                             + ", ".join(repr(m) for m in VIEW_STATUS_FILTERS)
                             + ")")
        text = filter_query if filter_query is not None else ""
        if not isinstance(text, str):
            raise ValueError("filter query must be a string")
        if len(text) > VIEW_FILTER_MAX:
            raise ValueError("filter query exceeds "
                             + str(VIEW_FILTER_MAX) + " characters")
        self.view_filter = text
        self.view_sort = sort_mode
        self.view_mode = view_mode
        self.view_status = status_filter
        self.persist_state()

    def set_table_pinned(self, table_key: str, pinned: bool) -> None:
        """MT-18 (0.28): pin/unpin one waiting-view table (schema 5)
        and re-persist the pin set.

        A pinned table floats to the top of the waiting view (list
        view) and to the top of its process group (process view); the
        pin order is the persistence order, most recent pin first.
        Invalid state raises the named ValueError, so the UI never
        persists what it would not render.
        """
        if not isinstance(table_key, str) or not table_key:
            raise ValueError("table path must be a non-empty string")
        current = {p.casefold() for p in self.pinned_tables}
        if pinned:
            if table_key.casefold() in current:
                raise ValueError("table is already pinned")
            if len(self.pinned_tables) >= PINNED_TABLES_LIMIT:
                raise ValueError("pinned tables limit reached ("
                                 + str(PINNED_TABLES_LIMIT) + ")")
            self.pinned_tables = (table_key,) + tuple(
                p for p in self.pinned_tables
                if p.casefold() != table_key.casefold())
        else:
            if table_key.casefold() not in current:
                raise ValueError("table is not pinned")
            self.pinned_tables = tuple(
                p for p in self.pinned_tables
                if p.casefold() != table_key.casefold())
        self.persist_state()

    def is_table_pinned(self, table_key: str) -> bool:
        """MT-18 (0.28): True when this relative path is in the
        persisted pin set (casefolded comparison, so the row identity
        and the stored pins compare the same on every platform)."""
        return table_key.casefold() in {
            p.casefold() for p in self.pinned_tables}

    def remember_last_table(self, table_key: str | None) -> None:
        """Remember the last explicitly loaded table (MT-10) and
        re-persist the master-state document."""
        self.last_table = table_key
        self.persist_state()

    def remember_recent_table(self, table_key: str) -> None:
        """Record a successful table load in the rolling recent list
        (MT-15): most recent first, deduplicated by relative path,
        capped at ``RECENT_TABLES_LIMIT``, re-persisted immediately."""
        if not isinstance(table_key, str) or not table_key:
            return
        at = _utc_now()
        remaining = [item for item in self.recent_tables
                     if item[0] != table_key]
        self.recent_tables = ((table_key, at),) \
            + tuple(remaining)[:RECENT_TABLES_LIMIT - 1]
        self.persist_state()

    def rescan(self) -> None:
        # MT-26 (0.34): reconcile EVERY indexed root (the same
        # incremental (size, mtime_ns) + sha256 short-circuit per root);
        # the merged set keeps the user order (primary first).
        from .table_index import RootIndexSet, reconcile
        indexes: list = []
        changes: list = []
        errors: dict[str, str] = {}
        for root in self.folders:
            prior = self.index.index_for_root(root)
            result = reconcile(root, prior)
            indexes.append(result.index)
            changes.extend(result.changes)
            if result.scan_error:
                errors[root] = result.scan_error
        self.index = RootIndexSet(indexes)
        self.last_changes = tuple(changes)
        self.scan_errors = errors
        self.scan_error = errors.get(self.folder) if self.folder else None
        self.last_scan_at = _utc_now()
        # Folder content changed: the orchestrator's cached names are read
        # live from self.index each tick, so nothing else to refresh.
        self.orchestrator.index = self.index
        self.orchestrator.retry()
        # MT-24 (0.32): re-queue the background plan analysis - a
        # changed table content has a new sha (its old document entry
        # no longer matches), added tables have none.
        self._queue_analysis()

    # -- MT-26 (0.34) folder lifecycle ------------------------------------------

    def _set_folders(self, folders: list[str]) -> None:
        """Keep self.folder in sync with the ordered folder list."""
        self.folders = _dedupe_folders(folders)
        self.folder = self.folders[0] if self.folders else ""

    def add_folder(self, folder) -> bool:
        """MT-26 (0.34): index one more table folder (appended, not the
        primary).  A missing / non-directory folder raises the named
        ValueError; a folder already indexed (casefolded) is a no-op.
        Returns True when the folder was added, False when it was
        already indexed.
        """
        from pathlib import Path
        resolved = str(Path(folder).expanduser().resolve())
        if not Path(resolved).is_dir():
            raise ValueError("folder is missing or not a directory: "
                             + resolved)
        if any(f.casefold() == resolved.casefold() for f in self.folders):
            return False
        self._set_folders(self.folders + [resolved])
        return True

    def remove_folder(self, folder) -> None:
        """MT-26 (0.34): stop indexing one table folder.  Removing a
        folder that is not indexed raises the named ValueError; the
        list may become empty (the Master then has no indexed tables).
        """
        from pathlib import Path
        resolved = str(Path(folder).expanduser().resolve())
        if not any(f.casefold() == resolved.casefold() for f in self.folders):
            raise ValueError("folder is not indexed: " + resolved)
        remaining = [f for f in self.folders
                     if f.casefold() != resolved.casefold()]
        self._set_folders(remaining)

    def move_folder_front(self, folder) -> None:
        """MT-26 (0.34): make one indexed folder the primary (front).
        Moving a folder that is not indexed raises the named ValueError.
        """
        from pathlib import Path
        resolved = str(Path(folder).expanduser().resolve())
        target = resolved.casefold()
        if not any(f.casefold() == target for f in self.folders):
            raise ValueError("folder is not indexed: " + resolved)
        moved = [f for f in self.folders if f.casefold() == target]
        rest = [f for f in self.folders if f.casefold() != target]
        self._set_folders(moved + rest)

    def entry_key(self, entry) -> str:
        """MT-26 (0.34): the UI / storage identity key of one table.

        Single-root session: the relative path (the documented picker
        and display identity, and what the legacy single-root state
        stored).  Multi-root session: the absolute table key (root
        joined with the relative path), so a table is unambiguous
        across roots.
        """
        from .table_index import table_key
        if len(self.folders) <= 1:
            return entry.relative_path
        return table_key(entry)

    def _queue_analysis(self) -> int:
        """MT-24 (0.32): enqueue the unanalyzed bound tables.

        Every indexed table with at least one bound process name and
        no persisted analysis entry yet (the content sha is the key)
        is queued for the background plan compile - an unbound table
        has nothing to compile against, so its columns keep the
        pending marker.  Returns the number of newly queued tables
        (0 when no worker is running yet - the window starts the
        worker at the waiting-view build).
        """
        from .table_index import table_key
        worker = self.analysis_worker
        if worker is None:
            return 0
        known = self.analysis_store.document()["tables"]
        queued = 0
        for entry in self.index.tables():
            if not entry.process_names or entry.sha256 in known:
                continue
            if worker.enqueue(table_key(entry), entry.sha256,
                              entry.process_names[0]):
                queued += 1
        return queued

    def set_folder(self, folder) -> None:
        # MT-26 (0.34): replace-all semantics - the given folder becomes
        # the only indexed root (the documented contract the existing
        # single-root callers rely on).
        from pathlib import Path
        from .table_index import RootIndexSet, TableIndex, reconcile
        resolved = str(Path(folder).expanduser().resolve())
        self._set_folders([resolved])
        result = reconcile(resolved, TableIndex(resolved, {}))
        self.index = RootIndexSet([result.index])
        self.last_changes = result.changes
        self.scan_errors = {}
        self.scan_error = result.scan_error
        self.last_scan_at = _utc_now()
        self.orchestrator.index = self.index
        self.orchestrator.retry()
        try:
            self.save_index()
        except Exception:
            pass
        self.persist_state()

    def save_index(self) -> None:
        # MT-26 (0.34): persist the whole multi-root set (schema 2); a
        # single-root set is one root block in the array.
        from .table_index import save_index_set
        try:
            save_index_set(self.index, self.index_path())
        except Exception:
            pass

    def state_dir_for(self, plan) -> str | None:
        if self.state_dir_factory is not None:
            return self.state_dir_factory(plan)
        return None

    @property
    def settings_store(self) -> MasterSettingsStore:
        """The per-table settings sidecar store under the state home (MT-6)."""
        return MasterSettingsStore(self.state_home)


class MasterWindow:
    def __init__(self, root, app: MasterApp):
        self.root = root
        self.app = app
        self.engine = None
        self.trainer_window = None
        self._picker = None
        self._picker_selection = None
        # MT-10/11/12 (0.25): explicit-load pickers, the process picker,
        # the pending choice-table (ask mode) and the session PID pin
        # ({"pid": None} = no pin, ordinary name-based attach).
        self._table_load_picker = None
        self._table_load_listbox = None
        self._table_load_entries = ()
        self._proc_picker = None
        self._proc_picker_listbox = None
        self._proc_picker_candidates = ()
        self._proc_picker_entry = None
        self._proc_picker_origin = None
        self._choice_table_rel = None
        self._attach_pin = {"pid": None}
        self._attach_mode_btn = None
        # MT-25 (0.33): the persisted auto-rescan toggle button + the
        # interval clock (time.monotonic); a fresh waiting view arms the
        # clock so the first auto pass is one interval after the view
        # builds (the initial reconcile already happened in
        # MasterApp.__init__).
        self._auto_rescan_btn = None
        self._last_auto_rescan = time.monotonic()
        self._table_frame = None
        # MT-19 (0.29): the single container that owns every
        # waiting-view widget.  It is torn down when the trainer takes
        # over the shared root, so the trainer row grid owns the full
        # window instead of sharing it with the table list.
        self._waiting_frame = None
        self._folder_label = None
        self._meta_label = None
        self._running_label = None
        self._status_var = None
        self._retry_btn = None
        self._filter_entry = None
        self._sort_btn = None
        self._view_btn = None
        self._status_btn = None
        # MT-20 (0.29): the read-only in-app UI-flow Toplevel (at most
        # one at a time).
        self._ui_flow_win = None
        # MT-22 (0.30): the read-only table-details Toplevel (at most
        # one at a time).
        self._details_win = None
        # MT-27 (0.35): the per-table note / tag editor Toplevel (at
        # most one at a time).
        self._note_editor_win = None
        # Live bound-process feedback of the latest waiting tick.
        self._running: tuple = ()
        self._running_keys: frozenset = frozenset()
        # MT-13/14/15 (0.26) + MT-16/17 (0.27): the waiting-view
        # filter/sort/display state.  Restored from the persisted
        # master-state document (schema 4) at construction; every
        # change is re-persisted through app.set_view_settings.
        self._filter_query = app.view_filter
        self._sort_mode = app.view_sort
        self._view_mode = app.view_mode
        # MT-23 (0.31): the persisted status-filter mode (schema 6);
        # restored like the other view settings and re-persisted on
        # every change through app.set_view_settings.
        self._status_filter = app.view_status
        try:
            icon = window_icon_path("master")
            if icon.is_file():
                root.iconbitmap(str(icon))
        except tk.TclError:
            pass
        self._build_waiting_view()
        root.after(app.poll_ms, self._poll)

    # ------------------------------------------------------------------
    # waiting view
    # ------------------------------------------------------------------

    def _build_waiting_view(self):
        self.root.title(master_title())
        # MT-15 (0.26): the tree gained the Size / Modified / Last-used
        # columns, so the waiting view starts wider.
        self.root.geometry("1160x600")
        self.root.minsize(900, 420)
        # MT-19 (0.29): every waiting-view widget lives in this single
        # container.  Entering the trainer destroys the container, so
        # the table list and its chrome stop competing for window
        # space with the trainer row grid (the trainer then owns the
        # full root); the waiting view is rebuilt whole on the way
        # back.
        self._waiting_frame = tk.Frame(self.root, bg=BG)
        self._waiting_frame.pack(fill="both", expand=True)
        header = tk.Frame(self._waiting_frame, bg=BG_HEADER, height=44,
                          padx=12)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text=master_title(), bg=BG_HEADER, fg=FG,
                 font=("Segoe UI", 13, "bold"), anchor="w").pack(
            side="left", fill="x", expand=True)

        def button(parent, label, action, **kw):
            style = {"bg": "#2a3547", "fg": FG, "activebackground": "#3a4a63",
                     "activeforeground": FG, "font": ("Segoe UI", 12),
                     "height": 2, "pady": 4}
            style.update(kw)
            return tk.Button(parent, text=label, command=action, **style)

        button(header, "Close", self.close).pack(side="right")
        # MT-20 (0.29): the read-only in-app UI-flow reference (the
        # same content as the reviewable UI.md next to this module).
        button(header, "UI flow", self._open_ui_flow).pack(
            side="right", padx=(0, 8))
        button(header, "Rescan", self._rescan).pack(side="right", padx=(0, 8))
        # MT-26 (0.34): the folder manager (several indexed table
        # folders; add / remove / set primary) replaces the single
        # "Change folder" picker.
        button(header, "Folders…", self._open_folder_manager).pack(
            side="right", padx=(0, 8))
        # MT-10 (0.25): explicit table load (loads even while the bound
        # process is not running; the engine then waits for it).
        button(header, "Load table", self._open_table_load_picker).pack(
            side="right", padx=(0, 8))
        repo_link(header, bg=BG_HEADER, fg=FG).pack(side="right", padx=(0, 16))
        # MT-13 (0.26): the waiting-view filter + sort cycle.  Packed
        # after the repo link, i.e. left of it in the header row.  The
        # filter/sort/view values are restored from the persisted
        # master-state document (schema 4, MT-16) and re-persisted on
        # every change.
        self._sort_btn = tk.Button(header, text="Sort: " + self._sort_mode,
                                   command=self._cycle_sort,
                                   bg="#2a3547", fg=FG,
                                   activebackground="#3a4a63",
                                   activeforeground=FG,
                                   font=("Segoe UI", 11),
                                   relief="raised", padx=8, pady=2)
        self._sort_btn.pack(side="right", padx=(0, 8))
        # MT-17 (0.27): the waiting-view display mode cycle (flat list
        # vs grouped by bound process name), between the sort button
        # and the filter entry; persisted like the other view settings
        # (MT-16).
        self._view_btn = tk.Button(header,
                                   text="View: " + self._view_mode,
                                   command=self._cycle_view,
                                   bg="#2a3547", fg=FG,
                                   activebackground="#3a4a63",
                                   activeforeground=FG,
                                   font=("Segoe UI", 11),
                                   relief="raised", padx=8, pady=2)
        self._view_btn.pack(side="right", padx=(0, 8))
        # MT-23 (0.31): the waiting-view status-filter cycle (all /
        # ok / attention), between the view button and the filter
        # entry; persisted like the other view settings (MT-16,
        # schema 6).  "" shows as "all".
        self._status_btn = tk.Button(header,
                                     text="Status: "
                                     + (self._status_filter or "all"),
                                     command=self._cycle_status_filter,
                                     bg="#2a3547", fg=FG,
                                     activebackground="#3a4a63",
                                     activeforeground=FG,
                                     font=("Segoe UI", 11),
                                     relief="raised", padx=8, pady=2)
        self._status_btn.pack(side="right", padx=(0, 8))
        self._filter_entry = tk.Entry(header, width=30,
                                      font=("Segoe UI", 11),
                                      bg="#10151f", fg=FG,
                                      insertbackground=FG, relief="flat")
        self._filter_entry.pack(side="right", padx=(0, 4))
        # Restore the session query (survives the trainer round-trip).
        self._filter_entry.insert(0, self._filter_query)
        self._filter_entry.bind("<KeyRelease>", self._on_filter_edit)
        self._filter_entry.bind("<Escape>", self._on_filter_escape)
        # MT-14 (0.26): "/" focuses the filter from anywhere in the
        # waiting view (a no-op in trainer mode, where keys belong to
        # the trainer UI).
        self.root.bind("<KeyPress>/", self._on_slash)
        # MT-20 (0.29): F5 re-scans the folder from anywhere in the
        # waiting view (a no-op in trainer mode, where the keys belong
        # to the trainer UI).
        self.root.bind("<F5>", self._on_f5)
        self._folder_label = tk.Label(self._waiting_frame,
                                      text=self._folder_text(),
                                      bg=BG, fg=FG_DIM, font=("Segoe UI", 11),
                                      anchor="w", padx=12)
        self._folder_label.pack(fill="x")
        self._meta_label = tk.Label(self._waiting_frame,
                                    text=self._meta_text(),
                                    bg=BG, fg=FG_DIM, font=("Segoe UI", 9),
                                    anchor="w", padx=12)
        self._meta_label.pack(fill="x")
        self._running_label = tk.Label(self._waiting_frame,
                                       text=self._running_text(self._running),
                                       bg=BG, fg=FG, font=("Segoe UI", 10),
                                       anchor="w", padx=12)
        self._running_label.pack(fill="x")

        frame = ttk.Frame(self._waiting_frame, padding=8)
        frame.pack(fill="both", expand=True)
        # MT-15 (0.26): the waiting-view tree carries the indexed size /
        # modified columns plus the Last-used feed of the recent list.
        # MT-24 (0.32): the Entries / Blocked columns carry the
        # background plan-analysis counts (pending "…" until the
        # analysis finishes, the failed marker "–" on a named
        # refusal, the counts otherwise).
        # MT-26 (0.34): the Folder column (after Table) shows the root
        # each table was indexed under - the single primary folder in a
        # single-root session, the per-table root in a multi-root one.
        # MT-27 (0.35): the Note column (last) shows the persisted
        # per-table organization metadata (note text truncated, tags
        # in brackets) - "" while no note exists.
        cols = ("table", "folder", "processes", "status", "detail",
                "entries", "blocked",
                "size", "modified", "last_used", "note")
        self._table_tree = ttk.Treeview(frame, columns=cols, show="headings",
                                        height=16)
        for name, text, width in (("table", "Table", 220),
                                  ("folder", "Folder", 160),
                                  ("processes", "Process name(s)", 170),
                                  ("status", "Status", 70),
                                  ("detail", "Detail", 170),
                                  ("entries", "Entries", 70),
                                  ("blocked", "Blocked", 70),
                                  ("size", "Size", 80),
                                  ("modified", "Modified", 130),
                                  ("last_used", "Last used", 150),
                                  ("note", "Note", 160)):
            self._table_tree.heading(name, text=text)
            self._table_tree.column(name, width=width, anchor="w")
        # MT-23 (0.31): the live status color coding - the default
        # colors for ok / running rows, an amber warning for a table
        # that changed since the last scan, and an error red for a
        # missing / unreadable one (the MT-9 gate would refuse it).
        self._table_tree.tag_configure("attention-warn",
                                       foreground="#e5c07b")
        self._table_tree.tag_configure("attention-error",
                                       foreground="#ff7b72")
        scroll = ttk.Scrollbar(frame, orient="vertical",
                               command=self._table_tree.yview)
        self._table_tree.configure(yscrollcommand=scroll.set)
        self._table_tree.pack(side="left", fill="both", expand=True)
        # MT-10 (0.25): right-click a row to load that table explicitly.
        self._table_tree.bind("<Button-3>", self._table_context_menu)
        # MT-14 (0.26): double-click or Enter loads the selected row
        # through the ordinary explicit-load path (named refusals
        # included; no new load logic).  Arrow keys are built in.
        self._table_tree.bind("<Double-1>", self._table_double_click)
        self._table_tree.bind("<Return>", self._table_return)
        self._table_tree.bind("<KP_Enter>", self._table_return)
        scroll.pack(side="right", fill="y")

        self._status_var = tk.StringVar(self.root, value="Scanning…")
        status = tk.Frame(self._waiting_frame, bg=BG, height=40, padx=12)
        status.pack(fill="x")
        status.pack_propagate(False)
        tk.Label(status, textvariable=self._status_var, anchor="w",
                 justify="left", wraplength=900, bg=BG, fg=FG,
                 font=("Segoe UI", 11)).pack(side="left", fill="x", expand=True)
        # MT-11 (0.25): the persisted attach-mode toggle (auto/ask).
        self._attach_mode_btn = button(status, "Attach: "
                                       + self.app.attach_mode,
                                       self._toggle_attach_mode, width=14)
        self._attach_mode_btn.pack(side="right")
        # MT-25 (0.33): the persisted auto-rescan toggle.  Packed after
        # the attach button so it sits directly to its left.  While on,
        # the waiting view re-runs the incremental scan every
        # AUTO_RESCAN_INTERVAL_SECONDS (paused while a trainer is
        # attached; a manual rescan or folder change restarts the
        # interval clock).
        self._auto_rescan_btn = button(status, "Auto-rescan: "
                                        + ("on" if self.app.auto_rescan
                                           else "off"),
                                        self._toggle_auto_rescan,
                                        width=16)
        self._auto_rescan_btn.pack(side="right", padx=(0, 8))
        # MT-20 (0.29): the retry-load re-arm moves into the status bar
        # next to the other waiting controls (it used to be a separate
        # root-level button below the status strip, easy to miss).
        self._retry_btn = button(status, "Retry load", self._retry, width=12)
        self._retry_btn.pack(side="right", padx=(0, 8))
        # MT-15 (0.26): one-click re-load of the most recent table
        # (built per waiting-view build; the list only changes while a
        # trainer session runs, i.e. while this view is not visible).
        if self.app.recent_tables:
            self._recent_btn = button(status, "Recent: "
                                      + self.app.recent_tables[0][0],
                                      self._load_recent_table, width=28)
            self._recent_btn.pack(side="right", padx=(0, 8))
        else:
            self._recent_btn = None
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._render_tables()
        # MT-20 (0.29): the table list takes the initial focus, so the
        # arrow keys and Enter work immediately without a first click.
        self._table_tree.focus_set()
        # MT-24 (0.32): the background plan analysis starts with the
        # waiting view (deterministic: the window, not the app, owns
        # the worker lifecycle) and resumes after a trainer
        # round-trip, re-queueing the unanalyzed bound tables.
        app = self.app
        if app.analysis_worker is None:
            app.analysis_worker = AnalysisWorker(app)
            app.analysis_worker.start()
        app.analysis_worker.resume()
        app._queue_analysis()
        # The meta line was built before the queue pass; refresh it so
        # the "analyzing N table(s)" figure is visible at a glance.
        if self._meta_label is not None:
            self._meta_label.configure(text=self._meta_text())

    def _teardown_waiting_view(self):
        """MT-19 (0.29): remove the waiting view from the shared root.

        Called on trainer entry, once the engine is up: the single
        container is destroyed (which takes every waiting-view
        widget - header, folder/meta/running lines, the table tree,
        the status bar - with it) and the widget references are
        dropped, so the poll loop and the handlers never touch a
        destroyed widget.  ``_back_to_master`` rebuilds the waiting
        view from scratch."""
        if self._ui_flow_win is not None:
            try:
                if self._ui_flow_win.winfo_exists():
                    self._ui_flow_win.destroy()
            except tk.TclError:
                pass
            self._ui_flow_win = None
        if self._details_win is not None:
            try:
                if self._details_win.winfo_exists():
                    self._details_win.destroy()
            except tk.TclError:
                pass
            self._details_win = None
        if self._note_editor_win is not None:
            try:
                if self._note_editor_win.winfo_exists():
                    self._note_editor_win.destroy()
            except tk.TclError:
                pass
            self._note_editor_win = None
        if self._waiting_frame is not None:
            self._waiting_frame.destroy()
            self._waiting_frame = None
        self._table_tree = None
        self._folder_label = None
        self._meta_label = None
        self._running_label = None
        self._status_var = None
        self._attach_mode_btn = None
        self._retry_btn = None
        self._recent_btn = None
        self._filter_entry = None
        self._sort_btn = None
        self._view_btn = None
        self._status_btn = None

    def _open_ui_flow(self):
        """MT-20 (0.29): the read-only in-app UI-flow reference.

        One Toplevel shows the full waiting/trainer flow (the same
        content as the reviewable UI.md next to this module) so the
        user can read, review and improve the flow without leaving the
        app.  A second click lifts the open window instead of opening
        a duplicate."""
        if self._ui_flow_win is not None:
            try:
                if self._ui_flow_win.winfo_exists():
                    self._ui_flow_win.lift()
                    self._ui_flow_win.focus_set()
                    return
            except tk.TclError:
                pass
            self._ui_flow_win = None
        win = tk.Toplevel(self.root)
        self._ui_flow_win = win
        win.title("CT2Trainer Master Trainer — UI flow")
        win.configure(bg=BG, padx=16, pady=16)
        win.transient(self.root)
        tk.Label(win, text="UI flow (read-only reference)",
                 bg=BG, fg=FG, font=("Segoe UI", 13, "bold"),
                 anchor="w").pack(fill="x")
        paned = tk.Frame(win, bg=BG)
        paned.pack(fill="both", expand=True, pady=(8, 8))
        box = tk.Text(paned, wrap="word", bg=BG, fg=FG,
                      font=("Segoe UI", 11), relief="flat",
                      highlightthickness=0, padx=10, pady=10)
        box.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(paned, orient="vertical", command=box.yview)
        box.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        box.insert("1.0", ui_flow_text())
        box.configure(state="disabled")
        tk.Button(win, text="Close", command=win.destroy,
                  bg="#2a3547", fg=FG, activebackground="#3a4a63",
                  activeforeground=FG, font=("Segoe UI", 12),
                  height=2, padx=12, pady=4).pack(anchor="e")

    def _folder_text(self) -> str:
        # MT-26 (0.34): the primary folder first; with several indexed
        # folders the total count is shown, and every root-level scan
        # problem is surfaced (one per failing root).
        folders = self.app.folders
        text = "Folder: " + (folders[0] if folders else "(none)")
        if len(folders) > 1:
            text += "  (" + str(len(folders)) + " folders total)"
        errors = self.app.scan_errors
        if errors:
            detail = "; ".join(
                err for _root, err in sorted(errors.items(),
                                             key=lambda item: item[0].casefold()))
            text += "  (scan problem: " + detail + ")"
        return text

    def _meta_text(self) -> str:
        """One compact line: table counts, bound process names, last scan
        time and the state home (where the index + per-table state live)."""
        app = self.app
        entries = app.index.tables()
        unreadable = sum(1 for e in entries if e.status != "ok")
        # MT-26 (0.34): with several indexed folders the count names the
        # folder span; a single folder keeps the documented line.
        folder_note = (" across " + str(len(app.folders)) + " folder(s)"
                       if len(app.folders) > 1 else "")
        if unreadable:
            count = (f"{len(entries)} tables "
                     f"({len(entries) - unreadable} ok, "
                     f"{unreadable} unreadable)"
                     + folder_note)
        else:
            count = f"{len(entries)} table(s) indexed" + folder_note
        names = app.index.process_names()
        bound = "bound: " + (", ".join(names) if names else "(none yet)")
        parts = [count, bound]
        # MT-10/11 (0.25): the stored preferences are visible at a glance.
        if app.last_table:
            parts.append("last loaded: " + app.last_table)
        # MT-15 (0.26): the rolling recent list (most recent first; the
        # full list feeds the Last-used column).
        if app.recent_tables:
            recent = ", ".join(path for path, _at in app.recent_tables[:3])
            more = len(app.recent_tables) - 3
            if more > 0:
                recent += f" ({more} more)"
            parts.append("recent: " + recent)
        parts.append("attach mode: " + app.attach_mode)
        if app.last_scan_at:
            parts.append("scanned " + app.last_scan_at)
        # MT-13 (0.26): the active filter is visible in the meta line;
        # the load picker always lists the full index, the tree only.
        if self._filter_query.strip():
            shown = len(self._visible_tables())
            parts.append(f"filtered: {shown}/{len(entries)}")
        # MT-23 (0.31): the active status filter (when not "all") and
        # the live attention count (how many indexed tables the MT-9
        # gate would refuse right now - changed / missing / unreadable,
        # one bounded stat per row per render).
        if self._status_filter:
            parts.append("status filter: " + self._status_filter)
        attention = sum(1 for e in entries
                        if self._row_status(e)[0] in ATTENTION_STATUSES)
        if attention:
            parts.append("attention: " + str(attention))
        # MT-24 (0.32): the background plan analysis is visible at a
        # glance (how many tables are queued / in flight right now).
        worker = app.analysis_worker
        if worker is not None:
            pending = worker.pending_count()
            if pending:
                parts.append("analyzing " + str(pending) + " table(s)")
        parts.append("state: " + app.state_home)
        # MT-7: on non-Windows the attach gate is fail-closed; the
        # documented SteamOS/CheatDeck route stays visible in the waiting
        # view, not only at the (refused) load attempt.
        route = attach_gate()
        if not route.attach_available:
            parts.append(route.detail)
        return "   |   ".join(parts)

    def _running_text(self, running) -> str:
        """Live feedback: which bound processes are visible right now."""
        if not running:
            return "Running now: (none of the bound processes)"
        by_name: dict[str, list[int]] = {}
        for entry in running:
            by_name.setdefault(entry.name.casefold(), []).append(entry.pid)
            by_name.setdefault(entry.name.casefold(), []).append(entry.name)
        parts = []
        for key in sorted(by_name):
            values = by_name[key]
            pids = sorted(v for v in values if isinstance(v, int))
            name = next(v for v in values if isinstance(v, str))
            parts.append(name + " (PID " + ", ".join(str(p) for p in pids) + ")")
        return "Running now: " + "; ".join(parts)

    def _set_running(self, running) -> None:
        """Refresh the running line; re-render the table rows only when the
        set of visible (name, PID) pairs changed."""
        self._running = tuple(running)
        if self._running_label is not None:
            self._running_label.configure(text=self._running_text(self._running))
        keys = frozenset((e.name.casefold(), e.pid) for e in self._running)
        if keys != self._running_keys:
            self._running_keys = keys
            self._render_tables()

    def _render_tables(self):
        tree = self._table_tree
        tree.delete(*tree.get_children())
        pids_by_key: dict[str, list[int]] = {}
        for entry in self._running:
            pids_by_key.setdefault(entry.name.casefold(), []).append(entry.pid)
        # MT-15 (0.26): the Last-used column is fed by the recent list
        # (the stored UTC timestamp, most recent first).
        recent_at = {path: at for path, at in self.app.recent_tables}
        # MT-17 (0.27): the process-grouped view reshapes the very same
        # row set (filter + sort applied first) into one parent row per
        # casefolded bound process name; the unbound tables collect
        # under UNBOUND_PROCESS_LABEL last.  The tree renders with
        # show="headings", so the group label lives in values[0], not
        # in the invisible text item.
        rows = list(self._visible_tables())
        # MT-24 (0.32): the background plan-analysis entries for the
        # visible rows (one document load per render; the pending
        # rows keep the "…" marker until the worker finishes them).
        analysis_by_sha = self.app.analysis_store.document()["tables"]
        # MT-27 (0.35): the per-table notes/tags entries for the
        # visible rows (one document load per render; rows without a
        # note entry show an empty Note cell).
        notes_by_sha = self.app.notes_store.document()["tables"]
        # MT-23 (0.31): one bounded stat per visible row per render -
        # the live (code, detail) pairs feed the Status column, the
        # row color tag and the attention detail.  A file that drifted
        # since the last scan surfaces here with the same facts the
        # MT-9 gate proves at load time.
        statuses = {entry.relative_path: self._row_status(entry)
                    for entry in rows}
        if self._view_mode != "process":
            for entry in rows:
                self._insert_table_row("", entry, pids_by_key, recent_at,
                                       statuses[entry.relative_path],
                                       analysis_by_sha, notes_by_sha)
            return
        for label, group in group_tables_by_process(rows):
            # MT-24 (0.32) + MT-26 (0.34) + MT-27 (0.35): the
            # display-only group row carries the empty Folder value
            # plus the (empty) Entries / Blocked / Note values of the
            # new columns.
            parent = tree.insert("", "end", open=True, values=(
                label, "", str(len(group)) + " table(s)",
                "", "", "", "", "", "", "", ""))
            for entry in group:
                self._insert_table_row(parent, entry, pids_by_key,
                                       recent_at,
                                       statuses[entry.relative_path],
                                       analysis_by_sha, notes_by_sha)

    def _insert_table_row(self, parent: str, entry, pids_by_key: dict,
                          recent_at: dict, status: tuple,
                          analysis_by_sha: dict,
                          notes_by_sha: dict) -> None:
        """One waiting-view table row (flat list or group child).

        MT-23 (0.31): ``status`` is the live ``(code, detail)`` pair
        from ``_row_status`` - the Status column shows the code (ok /
        running / changed / missing / unreadable), the tree tag
        carries the color coding (default for ok / running, amber for
        changed, red for missing / unreadable), and the attention
        detail is displayable (the same facts the MT-9 gate refuses
        with at load time).

        MT-24 (0.32): ``analysis_by_sha`` maps the table content sha
        to its persisted background plan-analysis entry (or the row
        stays pending) - the Entries / Blocked columns show the
        counts ("…" pending, "–" failed) and a blocked count > 0
        adds the "N blocked" note to the detail column (the parts
        join with " - ", the pin marker keeps its place)."""
        code, file_detail = status
        names = ", ".join(entry.process_names) or "(none found)"
        # MT-24 (0.32): the persisted analysis entry for this table's
        # content sha (None = pending, the "…" marker).
        analysis = analysis_by_sha.get(entry.sha256)
        # MT-27 (0.35): the persisted notes/tags entry for this
        # table's content sha (None = no note yet, the empty cell).
        note_entry = notes_by_sha.get(entry.sha256)
        if code == "running":
            pids = sorted(set(p for n in entry.process_names
                              for p in pids_by_key.get(n.casefold(), ())))
            detail = "PID " + ", ".join(str(p) for p in pids)
        elif code == "ok":
            detail = ""
        else:
            detail = file_detail
        # MT-18 (0.28) + MT-26 (0.34): the pin marker lives in the
        # detail column; the row identity is the table key (relative in
        # a single-root session, absolute in a multi-root one), checked
        # against the persisted pin set.
        if self.app.is_table_pinned(self.app.entry_key(entry)):
            detail = "pinned" + (" - " + detail if detail else "")
        # MT-24 (0.32): a table with blocked records gets the bounded
        # "N blocked" note in the detail column (after the pin
        # marker; the counts themselves live in the columns).
        if analysis is not None and analysis.get("status") == "ok" \
                and analysis["counts"]["blocked"]:
            note = str(analysis["counts"]["blocked"]) + " blocked"
            detail = (detail + " - " + note if detail else note)
        # MT-26 (0.34): the Folder column shows the index root; the
        # Last-used lookup and the row identity use the table key.
        key = self.app.entry_key(entry)
        # MT-27 (0.35): the Note column shows the persisted note
        # (truncated) plus the tags; "" while no note exists.
        note_text = note_column_text(note_entry)
        self._table_tree.insert(parent, "end", values=(
            entry.relative_path, entry.root, names, code, detail,
            entries_column_text(analysis),
            blocked_column_text(analysis),
            self._format_size(entry.size),
            self._format_mtime(entry.mtime_ns),
            recent_at.get(key, ""),
            note_text),
            tags=(row_tag(code),))

    def _live_fingerprint(self, entry):
        """MT-23 (0.31): one bounded ``stat`` of the table file: the
        live ``(size, mtime_ns)`` pair, or ``None`` when the file no
        longer exists or cannot be stat'ed (the 'missing' fact)."""
        from pathlib import Path
        # MT-26 (0.34): the table file lives under the entry's index
        # root (multi-root), falling back to the primary folder for
        # root-less entries.
        base = (getattr(entry, "root", "")
                or (self.app.folders[0] if self.app.folders else ""))
        path = Path(base) / entry.relative_path
        try:
            st = path.stat()
        except OSError:
            return None
        return (st.st_size, st.st_mtime_ns)

    def _row_status(self, entry):
        """MT-23 (0.31): the live ``(code, detail)`` pair for one row -
        the bounded stat plus the bound-process state of the latest
        tick; the pure ``table_status`` layer decides (cheapest fact
        first, live facts outrank the cached scan state - the same
        order the MT-9 gate proves at load time)."""
        fingerprint = self._live_fingerprint(entry)
        code, detail = row_file_status(entry, fingerprint)
        running = any(n.casefold() in
                      {e.name.casefold() for e in self._running}
                      for n in entry.process_names)
        return row_status(entry, fingerprint, running), detail

    def _visible_tables(self) -> list:
        """MT-13/18/23/27 (0.26/0.28/0.31/0.35): the waiting-view row
        set - the full index, sorted per the current mode, filtered per
        the current query (MT-27: the note text and tags of the
        persisted notes document join the match surface, keyed by the
        table content sha), then the persisted status filter (MT-23;
        one bounded stat per remaining row per render), then the
        persisted pin set floated to the top (MT-18; pinned rows not
        in the filtered set are ignored).  Row identity stays the
        relative path; the load picker and the auto-load path keep
        using the full index."""
        entries = sort_tables(self.app.index.tables(), self._sort_mode)
        # MT-27 (0.35): the filter also matches the persisted note
        # text and tags (one document load per render; a table without
        # a note entry simply has no note-side match surface).
        notes_by_sha = self.app.notes_store.document()["tables"]
        filtered = filter_tables(entries, self._filter_query,
                                 note_lookup=notes_by_sha)
        if self._status_filter:
            codes = [self._row_status(entry)[0] for entry in filtered]
            filtered = filter_rows_by_status(filtered, codes,
                                             self._status_filter)
        return pin_tables(filtered, self.app.pinned_tables)

    @staticmethod
    def _format_size(size: int) -> str:
        """Compact human-readable byte size for the Size column."""
        if size < 1024:
            return str(size) + " B"
        if size < 1024 * 1024:
            return str(int(size / 1024)) + " KB"
        return f"{size / (1024 * 1024):.1f} MB"

    @staticmethod
    def _format_mtime(mtime_ns: int) -> str:
        """Local 'YYYY-MM-DD HH:MM' for the Modified column."""
        from datetime import datetime
        return datetime.fromtimestamp(mtime_ns / 1e9).strftime(
            "%Y-%m-%d %H:%M")

    def _cycle_sort(self):
        """MT-13 (0.26): name -> process -> status -> name (the choice
        is persisted with the waiting-view settings, MT-16)."""
        order = list(SORT_MODES)
        self._sort_mode = order[(order.index(self._sort_mode) + 1)
                                % len(order)]
        self._sort_btn.configure(text="Sort: " + self._sort_mode)
        self.app.set_view_settings(self._filter_query, self._sort_mode,
                                   self._view_mode, self._status_filter)
        self._render_tables()

    def _cycle_view(self):
        """MT-17 (0.27): list -> process -> list (the choice is
        persisted with the waiting-view settings, MT-16)."""
        order = list(VIEW_MODES)
        self._view_mode = order[(order.index(self._view_mode) + 1)
                                % len(order)]
        self._view_btn.configure(text="View: " + self._view_mode)
        self.app.set_view_settings(self._filter_query, self._sort_mode,
                                   self._view_mode, self._status_filter)
        self._render_tables()

    def _cycle_status_filter(self):
        """MT-23 (0.31): "" (all) -> ok -> attention -> "" (the choice
        is persisted with the waiting-view settings, schema 6)."""
        order = list(VIEW_STATUS_FILTERS)
        self._status_filter = order[(order.index(self._status_filter) + 1)
                                    % len(order)]
        if self._status_btn is not None:
            self._status_btn.configure(text="Status: "
                                        + (self._status_filter or "all"))
        self.app.set_view_settings(self._filter_query, self._sort_mode,
                                   self._view_mode, self._status_filter)
        self._render_tables()
        if self._meta_label is not None:
            self._meta_label.configure(text=self._meta_text())

    def _on_filter_edit(self, _event):
        """MT-13 (0.26): live filter - re-render plus the meta line
        counter ('filtered: N/M') while a query is active.  The query
        is persisted with the other waiting-view settings (MT-16)."""
        self._filter_query = self._filter_entry.get()
        self.app.set_view_settings(self._filter_query, self._sort_mode,
                                   self._view_mode, self._status_filter)
        self._render_tables()
        if self._meta_label is not None:
            self._meta_label.configure(text=self._meta_text())

    def _on_filter_escape(self, _event):
        """MT-14 (0.26): Esc clears the filter and returns focus to
        the table list."""
        self._filter_entry.delete(0, "end")
        self._filter_query = ""
        self.app.set_view_settings(self._filter_query, self._sort_mode,
                                   self._view_mode, self._status_filter)
        self._render_tables()
        if self._meta_label is not None:
            self._meta_label.configure(text=self._meta_text())
        self._table_tree.focus_set()

    def _on_slash(self, _event):
        """MT-14 (0.26): '/' focuses the filter from anywhere in the
        waiting view; a no-op in trainer mode (the trainer UI owns
        the keys)."""
        if self.engine is not None:
            return
        self._filter_entry.focus_set()

    def _on_f5(self, _event):
        """MT-20 (0.29): F5 re-scans the folder (the documented
        refresh shortcut); a no-op in trainer mode (the trainer UI
        owns the keys)."""
        if self.engine is not None:
            return
        self._rescan()

    def _is_table_row(self, item: str) -> bool:
        """MT-17 (0.27): True for loadable table rows - group children
        in the process view and every row in the flat list.  Group rows
        themselves are display-only (no load)."""
        if self._table_tree.parent(item):
            return True
        return self._view_mode != "process"

    def _row_key(self, values) -> str | None:
        """MT-26 (0.34): the table key of one tree row from its values
        (values[0] = table name/relative path, values[1] = folder/root).
        Single-root: the relative path; multi-root: the absolute table
        key (so a table is unambiguous across roots)."""
        if not values or not values[0]:
            return None
        rel = values[0]
        if len(self.app.folders) <= 1:
            return rel
        folder = values[1] if len(values) > 1 else ""
        if not folder:
            return rel
        from pathlib import Path
        return str(Path(folder) / rel)

    def _table_selected_key(self):
        item = self._table_tree.focus()
        if not item:
            selected = self._table_tree.selection()
            if not selected:
                return None
            item = selected[0]
        if not self._is_table_row(item):
            return None
        values = self._table_tree.item(item, "values")
        return self._row_key(values)

    def _table_double_click(self, event):
        """MT-14 (0.26): double-click loads the clicked row through
        the MT-10 explicit-load path (named refusals included)."""
        item = self._table_tree.identify_row(event.y)
        if not item or not self._is_table_row(item):
            return
        values = self._table_tree.item(item, "values")
        if values:
            self._load_selected_table(self._row_key(values))

    def _table_return(self, _event):
        """MT-14 (0.26): Enter loads the selected/focused row."""
        key = self._table_selected_key()
        if key:
            self._load_selected_table(key)

    def _load_recent_table(self):
        """MT-15 (0.26): load the most recent table through the MT-10
        explicit-load path (named refusals included)."""
        if not self.app.recent_tables:
            return
        self._load_selected_table(self.app.recent_tables[0][0])

    def _set_status(self, text: str) -> None:
        if self._status_var is not None:
            self._status_var.set(text)

    def _rescan(self):
        # MT-25 (0.33): a manual rescan restarts the auto-rescan
        # interval clock, so the next automatic pass is a full interval
        # away (no immediate double scan).
        self._last_auto_rescan = time.monotonic()
        self._set_status("Rescanning…")
        self.app.rescan()
        self.app.save_index()
        self._meta_label.configure(text=self._meta_text())
        self._render_tables()
        self._set_status(self._waiting_status_line())

    def _auto_rescan_tick(self):
        """MT-25 (0.33): one interval re-scan - the same incremental
        reconcile as the manual rescan (the (size, mtime_ns) + sha256
        short-circuit) without the status-line flash (the line would
        flap every interval).  rescan() also re-queues the MT-24
        analysis for added or changed tables."""
        self.app.rescan()
        self.app.save_index()
        self._meta_label.configure(text=self._meta_text())
        self._render_tables()

    def _change_folder(self):
        folder = filedialog.askdirectory(
            parent=self.root, title="Choose the folder with your tables")
        if not folder:
            return
        # MT-25 (0.33): der gewechselte Ordner wird neu gescannt; der
        # Auto-Rescan-Zyklus startet damit ebenfalls neu.
        self._last_auto_rescan = time.monotonic()
        self.app.set_folder(folder)
        self.app.save_index()
        self._folder_label.configure(text=self._folder_text())
        self._meta_label.configure(text=self._meta_text())
        self._set_running(self._running)
        self._render_tables()
        self._set_status(self._waiting_status_line())

    # -- MT-26 (0.34) folder manager --------------------------------------------

    def _refresh_folder_view(self) -> None:
        """Rebuild the folder label + meta line + table rows after a
        folder-list change, and restart the auto-rescan clock.  Every
        indexed root is re-scanned first (the same incremental,
        short-circuited reconcile per root), so an added / removed /
        reordered folder shows up in the index immediately."""
        self._last_auto_rescan = time.monotonic()
        self.app.rescan()
        self.app.save_index()
        self._folder_label.configure(text=self._folder_text())
        self._meta_label.configure(text=self._meta_text())
        self._set_running(self._running)
        self._render_tables()
        self._set_status(self._waiting_status_line())

    def _open_folder_manager(self):
        """MT-26 (0.34): manage the indexed table folders - the listbox
        shows every root in user order (the primary first, marked with
        a star), and the buttons add a folder, set one primary, or
        remove one.  Every action re-scans the affected root, saves the
        index, restarts the auto-rescan clock and refreshes the view.
        A failed change lands in the status line (fail-closed)."""
        top = tk.Toplevel(self.root)
        top.title("Table folders")
        top.resizable(False, False)
        top.transient(self.root)
        tk.Label(top, text="Indexed table folders (primary first):",
                 anchor="w", padx=14,
                 font=("Segoe UI", 11)).pack(fill="x", pady=(12, 4))
        listbox = tk.Listbox(top, exportselection=False, width=52,
                             height=8, font=("Segoe UI", 10))
        folders = list(self.app.folders)
        for pos, folder in enumerate(folders):
            marker = "★ " if pos == 0 else "   "
            listbox.insert("end", marker + folder)
        listbox.pack(padx=14, pady=4)
        if folders:
            listbox.selection_set(0)

        def selected_folder() -> str | None:
            sel = listbox.curselection()
            if not sel:
                return None
            return folders[sel[0]]

        def do_add():
            folder = filedialog.askdirectory(
                parent=top, title="Choose a table folder to index")
            if not folder:
                return
            try:
                self.app.add_folder(folder)
            except ValueError as exc:
                self._set_status("Folder add failed: " + str(exc))
                return
            self._refresh_folder_view()
            self._open_folder_manager()

        def do_set_primary():
            folder = selected_folder()
            if not folder:
                return
            try:
                self.app.move_folder_front(folder)
            except ValueError as exc:
                self._set_status("Folder primary failed: " + str(exc))
                return
            self._refresh_folder_view()
            self._open_folder_manager()

        def do_remove():
            folder = selected_folder()
            if not folder:
                return
            try:
                self.app.remove_folder(folder)
            except ValueError as exc:
                self._set_status("Folder remove failed: " + str(exc))
                return
            self._refresh_folder_view()
            self._open_folder_manager()

        buttons = tk.Frame(top, padx=14)
        buttons.pack(fill="x", pady=(4, 12))
        for label, action in (("Add folder…", do_add),
                              ("Set primary", do_set_primary),
                              ("Remove", do_remove),
                              ("Close", top.destroy)):
            tk.Button(buttons, text=label, command=action,
                      font=("Segoe UI", 11), width=11,
                      bg="#2a3547", fg=FG,
                      activebackground="#3a4a63",
                      activeforeground=FG).pack(side="left", padx=(0, 6))

    def _retry(self):
        self.app.orchestrator.retry()
        self._set_status("Retry armed; resuming auto-load.")

    def _waiting_status_line(self) -> str:
        orch = self.app.orchestrator
        names = orch.bound_process_names
        base = ("Waiting for one of: " + (", ".join(names) if names
                 else "(no table binds a process name yet)"))
        if orch.last_error:
            return base + "  |  last: " + orch.last_error
        if orch.last_tick_detail:
            return base + "  |  " + orch.last_tick_detail
        return base

    # ------------------------------------------------------------------
    # polling / decisions
    # ------------------------------------------------------------------

    def _poll(self):
        if self.app.closed or self.engine is not None:
            # Trainer mode (or shutdown): the trainer window runs its own
            # poll loop, so the waiting-mode tick must not double-fire.
            return
        if self._proc_picker is not None \
                or self._table_load_picker is not None:
            # MT-10/11 (0.25): a user picker is open - the orchestrator
            # must not decide (auto-load) while the user is choosing, but
            # the loop keeps its cadence.
            self.root.after(self.app.poll_ms, self._poll)
            return
        # MT-25 (0.33): the table-folder auto-rescan - one incremental
        # reconcile per AUTO_RESCAN_INTERVAL_SECONDS while the waiting
        # view is open and auto-rescan is enabled.  Trainer mode (early
        # return above) and open pickers never reach this point, so the
        # scan pauses on trainer entry exactly like the MT-24 worker.
        if self.app.auto_rescan:
            now = time.monotonic()
            if now - self._last_auto_rescan >= AUTO_RESCAN_INTERVAL_SECONDS:
                self._last_auto_rescan = now
                self._auto_rescan_tick()
        try:
            outcome = self.app.orchestrator.tick()
            self._set_running(outcome.running)
            self._set_status(self._waiting_status_line())
            if outcome.request is not None and outcome.request_process is not None:
                self._auto_load(outcome.request, outcome.request_process)
            elif outcome.choice is not None and self._picker is None:
                self._open_picker(outcome.choice)
        except Exception as exc:
            # Fail-closed tick: name the problem, keep the loop alive.
            self._set_status("Waiting tick failed: " + exc.__class__.__name__
                             + ": " + str(exc))
        # MT-24 (0.32): finished background analyses re-render the
        # waiting view (the store already carries the facts; the
        # worker wrote them from its own thread - the drain only
        # triggers the render, plus the meta line's "analyzing N").
        worker = self.app.analysis_worker
        if worker is not None and self._table_tree is not None \
                and worker.drain_results():
            self._render_tables()
            if self._meta_label is not None:
                self._meta_label.configure(text=self._meta_text())
        if not self.app.closed and self.engine is None:
            self.root.after(self.app.poll_ms, self._poll)

    def _start_load(self, entry, process, explicit=False):
        # MT-11 (0.25): pin the chosen process for this session; the
        # injected memory factory honors it and falls back to the
        # ordinary name-based attach once that PID exits.
        self._attach_pin = {"pid": process.pid if process.pid else None}
        self._set_status("Loading " + entry.relative_path + " for " +
                         process.name + " (PID " + str(process.pid) + ")…")
        if explicit:
            # MT-10: remember the explicitly loaded table.
            self.app.remember_last_table(entry.relative_path)
        outcome = self.app.orchestrator.load(entry, process)
        if not outcome.ok:
            self._set_status("Load failed: " + outcome.error)
            messagebox.showerror("Table load failed",
                                 entry.relative_path + "\n\n" + outcome.error,
                                 parent=self.root)
            self._set_status(self._waiting_status_line())
            return
        # MT-15 (0.26): every successful load (auto or explicit) feeds
        # the rolling recent list (persisted under the state home).
        self.app.remember_recent_table(entry.relative_path)
        self._enter_trainer(outcome.plan, entry)

    def _enter_trainer(self, plan, entry):
        # MT-7: the attach gate is fail-closed and named. On Windows this
        # returns immediately (the unchanged native engine path); on any
        # other platform the load is refused with the documented
        # SteamOS/CheatDeck route before any engine work happens.
        try:
            require_engine_attach()
        except DeckAttachUnavailableError as exc:
            messagebox.showerror("Attach not available on this platform",
                                 str(exc), parent=self.root)
            self._fail_trainer_start(str(exc))
            return False
        # MT-24 (0.32): the background plan analysis pauses while a
        # trainer session runs (the window owns the CPU then); the
        # waiting-view rebuild resumes + re-queues.
        if self.app.analysis_worker is not None:
            self.app.analysis_worker.pause()
        # MT-6: restore the per-table settings sidecar (keyed by the table
        # content sha, never by path) for this session. A stored document
        # the settings model refuses is shown with its named reasons; the
        # session continues without it (no silent reset to defaults).
        self._sidecar_document = None
        self._sidecar_sha = entry.sha256 if entry is not None else None
        if entry is not None:
            known_ids = [e["id"] for e in (plan.get("entries") or [])
                         if isinstance(e, dict) and type(e.get("id")) is int]
            document, reasons = self.app.settings_store.load_for(
                entry.sha256, known_ids, process_name=plan.get("process_name"))
            if reasons:
                messagebox.showwarning(
                    "Table settings not restored",
                    "The stored per-table settings for "
                    + entry.relative_path + " were refused:\n\n"
                    + "\n".join("- " + reason for reason in reasons)
                    + "\n\nThe session starts without them.",
                    parent=self.root)
            else:
                self._sidecar_document = document
        attempt = 0
        while True:
            attempt += 1
            if attempt > 4:
                self._set_status("Startup recovery did not converge; the "
                                 "state folder was preserved for manual "
                                 "recovery.")
                messagebox.showerror("Trainer cannot start",
                                     "Startup recovery did not converge "
                                     "within four attempts.", parent=self.root)
                # Fail-closed like every other startup failure: record the
                # failure for the exact (name, PID) pair and return the
                # orchestrator to the waiting state, or the next tick would
                # refuse (the state machine only ticks while waiting) and
                # the waiting loop would stay stuck on the error text.
                self._fail_trainer_start(
                    "startup recovery did not converge within four attempts")
                return False
            try:
                engine = TrainerEngine(plan,
                                       state_dir=self.app.state_dir_for(plan),
                                       memory_factory=self._memory_factory())
                break
            except StaleStateRecoverable as exc:
                if not self._confirm_recovery("stale state", exc):
                    self._fail_trainer_start(str(exc))
                    return False
                continue
            except StaleArtifactsRecoverable as exc:
                if not self._confirm_recovery("unfinished receipts", exc):
                    self._fail_trainer_start(str(exc))
                    return False
                continue
            except LiveStateConflict as exc:
                messagebox.showerror(
                    "Live session conflict",
                    "Another trainer session (PID " + str(exc.owner_pid) +
                    ") still uses this table's state.\nClose the other "
                    "trainer and try again.", parent=self.root)
                self._fail_trainer_start(str(exc))
                return False
            except Exception as exc:
                messagebox.showerror("Trainer cannot start",
                                     str(exc), parent=self.root)
                self._fail_trainer_start(str(exc))
                return False
        self.engine = engine
        # MT-19 (0.29): the engine is up - collapse the waiting view so
        # the trainer row grid owns the full window (the waiting list no
        # longer competes for space next to the trainer rows).  The
        # waiting view is rebuilt whole on the way back.
        self._teardown_waiting_view()
        try:
            # MT-21 (0.36): the trainer grid column count (persisted
            # preference) is handed to the trainer window, and the
            # header cycle control persists it back through the app.
            self.trainer_window = TrainerWindow(
                self.root, engine, master_back=self._back_to_master,
                detach_cb=self._detach_or_attach,
                columns=self.app.grid_columns,
                on_columns_changed=self._set_trainer_grid_columns)
        except Exception as exc:
            # The engine is up but the trainer view could not be built:
            # close the engine again, restore the waiting view (torn
            # down for trainer entry) and fail the load so the waiting
            # loop (and its loop guard) stay consistent.
            self.engine = None
            try:
                engine.close()
            except Exception:
                pass
            self.trainer_window = None
            self._build_waiting_view()
            messagebox.showerror("Trainer cannot start", str(exc),
                                 parent=self.root)
            self._fail_trainer_start(str(exc))
            return
        self.app.orchestrator.mark_active()
        return True

    def _confirm_recovery(self, kind: str, exc) -> bool:
        live_target = bool(getattr(exc, "live_target_takeover", False))
        if kind == "stale state":
            if live_target:
                body = (
                    "A previous session of this table left a state lock; the "
                    "previous trainer process is verified terminated, but the "
                    "game it trained is still running.\n\n"
                    "Recover (archive the old state byte-for-byte) and attach "
                    "to the running game? Already applied patches stay in the "
                    "game; saved toggles are re-applied and toggles that no "
                    "longer match their scan pattern will show a scan error.")
            else:
                body = (
                    "A previous session of this table left a state lock; the "
                    "previous trainer process is verified terminated.\n\n"
                    "Recover (archive the old state byte-for-byte) and start?")
            prompt = messagebox.askyesno("Trainer state", body,
                                         parent=self.root)
            if prompt:
                ok, detail = perform_stale_recovery(exc)
                if not ok:
                    messagebox.showerror("Recovery failed", detail,
                                         parent=self.root)
                    return False
        else:
            if live_target:
                body = (
                    "A previous session left unfinished receipts; the recorded "
                    "trainer processes are verified terminated, but the game "
                    "the previous session trained is still running.\n\n"
                    "Recover (archive the old receipts byte-for-byte) and "
                    "attach to the running game?")
            else:
                body = (
                    "A previous session left unfinished receipts; the recorded "
                    "processes are verified terminated.\n\nRecover and start?")
            prompt = messagebox.askyesno("Trainer state", body,
                                         parent=self.root)
            if prompt:
                ok, detail = perform_stale_recovery(exc)
                if not ok:
                    messagebox.showerror("Recovery failed", detail,
                                         parent=self.root)
                    return False
        # A declined prompt fails the load (the standalone trainer exits
        # with the untouched state preserved); returning True here would
        # re-prompt on every loop iteration until the 4-attempt guard
        # tripped.
        return prompt

    def _fail_trainer_start(self, error: str):
        self.app.orchestrator.fail_load(error)
        self._set_status("Trainer start failed: " + error)

    # ------------------------------------------------------------------
    # explicit table load (MT-10) / attach mode (MT-11) / detach (MT-12)
    # ------------------------------------------------------------------

    def _auto_load(self, request, process):
        """Auto-load path with the MT-11 attach decision applied: in
        'ask' mode the user picks the target process first (even for a
        single running candidate); 'auto' attaches directly to the
        documented smallest-PID process."""
        candidates = candidate_processes(self._running,
                                         request.process_names)
        decision, _ = attach_decision(candidates, self.app.attach_mode)
        if decision == DECISION_PICK:
            self._open_process_picker(request, candidates,
                                      origin="auto-load")
            return
        self._start_load(request, process)

    def _memory_factory(self):
        """The MT-11 memory factory for the current session: it honors
        the session's pinned PID (the user's process choice) and falls
        back to the ordinary name-based attach once that process exits."""
        return make_pinned_memory_factory(self.app.lister,
                                          self._attach_pin)

    def _load_selected_table(self, table_key):
        """Explicit user table load (MT-10, table key): resolve the
        table against the live snapshot, apply the attach decision,
        then load.  Named refusals land in the status line + dialog,
        never a crash.  MT-26 (0.34): the table is addressed by its
        key (relative in a single-root session, absolute in a
        multi-root one)."""
        if not table_key:
            return
        try:
            request = self.app.orchestrator.request_load(table_key)
        except ExplicitLoadRefusal as exc:
            self._set_status("Explicit load refused: " + exc.detail)
            messagebox.showerror("Table load refused",
                                 table_key + "\n\n" + exc.detail,
                                 parent=self.root)
            return
        decision, _ = attach_decision(request.candidates,
                                      self.app.attach_mode)
        if decision == DECISION_PICK:
            self._open_process_picker(request.table, request.candidates,
                                      origin="explicit")
            return
        self._start_load(request.table, request.process, explicit=True)

    def _open_table_load_picker(self):
        """The MT-10 table picker: every readable indexed table, pick
        one to load now (the load runs even if the bound process does
        not run yet; the engine then waits for it)."""
        entries = [e for e in self.app.index.tables() if e.status == "ok"]
        if not entries:
            messagebox.showwarning(
                "No loadable table",
                "No readable table is indexed yet; point the Master at a "
                "folder with .ct tables first.", parent=self.root)
            return
        top = tk.Toplevel(self.root)
        top.title("Load table")
        top.resizable(False, False)
        top.transient(self.root)
        tk.Label(top, text="Choose the table to load now:",
                 anchor="w", padx=14, font=("Segoe UI", 11)
                 ).pack(fill="x", pady=(12, 4))
        # MT-26 (0.34): the picker label is the table key (the relative
        # path in a single-root session, the absolute path in a
        # multi-root one - so a table is unambiguous across roots).
        listbox = tk.Listbox(top, exportselection=False, width=56,
                             height=12, font=("Segoe UI", 10))
        for entry in entries:
            listbox.insert("end", self.app.entry_key(entry))
        listbox.pack(padx=14, pady=4)
        listbox.selection_set(0)
        buttons = tk.Frame(top, padx=14)
        buttons.pack(fill="x", pady=(4, 12))
        tk.Button(buttons, text="Load",
                  command=self._table_load_picker_load,
                  font=("Segoe UI", 12), width=10,
                  bg="#2a3547", fg=FG).pack(side="left")
        tk.Button(buttons, text="Cancel",
                  command=self._close_table_load_picker,
                  font=("Segoe UI", 12), width=10,
                  bg="#2a3547", fg=FG).pack(side="left", padx=(8, 0))
        self._table_load_picker = top
        self._table_load_listbox = listbox
        self._table_load_entries = tuple(entries)
        top.protocol("WM_DELETE_WINDOW", self._close_table_load_picker)
        try:
            top.grab_set()
        except tk.TclError:
            pass
        top.update_idletasks()

    def _table_load_picker_load(self):
        if self._table_load_picker is None:
            return
        sel = self._table_load_listbox.curselection()
        if not sel:
            self._close_table_load_picker()
            return
        # MT-26 (0.34): resolve the chosen entry BEFORE closing the
        # picker (closing clears the entry tuple).
        entry = self._table_load_entries[sel[0]]
        self._close_table_load_picker()
        self._load_selected_table(self.app.entry_key(entry))

    def _close_table_load_picker(self):
        if self._table_load_picker is not None:
            self._table_load_picker.destroy()
        self._table_load_picker = None
        self._table_load_listbox = None
        self._table_load_entries = ()

    def _table_context_menu(self, event):
        """The MT-10/18 row menu: right-click a table row to load it
        or pin/unpin it (group rows are display-only, MT-17)."""
        item = self._table_tree.identify_row(event.y)
        if not item or not self._is_table_row(item):
            return
        values = self._table_tree.item(item, "values")
        if not values:
            return
        # MT-26 (0.34): the row menu acts on the table key (relative in
        # a single-root session, absolute in a multi-root one).
        key = self._row_key(values)
        menu = tk.Menu(self.root, tearoff=0)
        # MT-22 (0.30) + MT-27 (0.35): the read-only details lead the
        # row menu (the inspection window with the live load-gate
        # preview), then the explicit load, then the per-table
        # note / tag editor, then the pin toggle.
        menu.add_command(label="Table details",
                         command=lambda: self._open_table_details(key))
        menu.add_command(label="Load this table",
                         command=lambda: self._load_selected_table(key))
        menu.add_command(label="Edit note\u2026",
                         command=lambda: self._open_note_editor(key))
        if self.app.is_table_pinned(key):
            menu.add_command(label="Unpin",
                             command=lambda: self._toggle_table_pin(key,
                                                                    False))
        else:
            menu.add_command(label="Pin to top",
                             command=lambda: self._toggle_table_pin(key,
                                                                    True))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.destroy()

    def _toggle_table_pin(self, table_key: str, pinned: bool):
        """MT-18 (0.28) + MT-26 (0.34): the row-menu pin toggle (table
        key) - re-renders on success, surfaces the named refusal in the
        status line on failure (no crash, no state change)."""
        try:
            self.app.set_table_pinned(table_key, pinned)
        except ValueError as exc:
            self._set_status(str(exc))
            return
        self._render_tables()
        self._set_status(("Pinned " if pinned else "Unpinned ") + table_key)

    def _open_note_editor(self, table_key: str):
        """MT-27 (0.35): the per-table note / tag editor Toplevel.

        Addressed by the table key (relative in a single-root session,
        absolute in a multi-root one).  The note and the tags persist
        against the table's *content* sha256 (the same identity as the
        MT-24 analysis and the MT-22 content-sha row), so they survive a
        rename or a move between indexed roots while the content is
        unchanged.  A table whose index entry has no content sha
        (unreadable / never scanned) cannot carry a note: the named
        refusal lands in the status line, no dialog opens, no state
        changes.

        The dialog is a small Toplevel: the note as a multi-line Text
        (bounded by NOTE_MAX_LEN), the tags as one comma-separated
        Entry (bounded by the TAGS_LIMIT / TAG_MAX_LEN rules), a Save
        button and a Cancel button.  A named refusal at save time
        (note over the limit, a tag too long, too many tags) is shown
        in the dialog's own status label - the dialog stays open, the
        persisted document is untouched.  A successful save re-renders
        the waiting view (the Note column updates) and reports to the
        status line.  A second open lifts the window instead of
        duplicating it; the window closes on trainer entry with the
        rest of the waiting view.
        """
        if self._note_editor_win is not None:
            try:
                if self._note_editor_win.winfo_exists():
                    self._note_editor_win.lift()
                    self._note_editor_win.focus_set()
                    return
            except tk.TclError:
                pass
            self._note_editor_win = None
        entry = self.app.index.get_by_key(table_key)
        if entry is None:
            self._set_status("No index entry for " + table_key)
            return
        if not sha256_key_ok(entry.sha256):
            self._set_status(
                "Note: no content sha for " + table_key
                + " (the table is unreadable or unscanned - a note "
                "follows the content identity, so there is none to "
                "edit)")
            return
        stored = self.app.notes_store.get(entry.sha256) or {}
        existing_note = stored.get("note") or ""
        existing_tags = ", ".join(stored.get("tags") or ())
        win = tk.Toplevel(self.root)
        self._note_editor_win = win
        win.title("Edit note - " + table_key)
        win.configure(bg=BG, padx=16, pady=16)
        win.transient(self.root)
        win.resizable(True, False)
        win.protocol("WM_DELETE_WINDOW", self._note_editor_cancel)
        tk.Label(win, text="Note for this table (saved with its content "
                           "sha256)",
                 bg=BG, fg=FG, font=("Segoe UI", 12, "bold"),
                 anchor="w").pack(fill="x")
        note_box = tk.Text(win, width=72, height=6, bg="#10151f", fg=FG,
                           insertbackground=FG, relief="flat",
                           font=("Segoe UI", 11), wrap="word")
        note_box.insert("1.0", existing_note)
        note_box.pack(fill="x", pady=(8, 4))
        tk.Label(win, text="Tags (comma separated; max "
                           + str(TAGS_LIMIT) + " tags, "
                           + str(TAG_MAX_LEN) + " characters each)",
                 bg=BG, fg=FG_DIM, font=("Segoe UI", 10),
                 anchor="w").pack(fill="x")
        tag_entry = tk.Entry(win, width=74, bg="#10151f", fg=FG,
                             insertbackground=FG, relief="flat",
                             font=("Segoe UI", 11))
        tag_entry.insert(0, existing_tags)
        tag_entry.pack(fill="x", pady=(0, 4))
        error_var = tk.StringVar(win)
        error_label = tk.Label(win, textvariable=error_var, bg=BG,
                               fg="#ff7b72", font=("Segoe UI", 10),
                               anchor="w", justify="left")
        error_label.pack(fill="x")

        def save():
            note_text = note_box.get("1.0", "end").rstrip("\n")
            try:
                tags = parse_tags(tag_entry.get())
                self.app.notes_store.set_note(entry.sha256, note_text,
                                              tags)
            except NotesRefusal as exc:
                error_var.set(str(exc))
                return
            win.destroy()
            self._note_editor_win = None
            self._render_tables()
            self._set_status("Note saved for " + table_key)

        def cancel():
            win.destroy()
            self._note_editor_win = None
            self._set_status("Note edit cancelled for " + table_key)

        tk.Button(win, text="Save", command=save, bg="#2a3547", fg=FG,
                  activebackground="#3a4a63", activeforeground=FG,
                  font=("Segoe UI", 12), padx=12, pady=2).pack(
            side="right", pady=(8, 0))
        tk.Button(win, text="Cancel", command=cancel, bg="#2a3547",
                  fg=FG, activebackground="#3a4a63",
                  activeforeground=FG, font=("Segoe UI", 12), padx=12,
                  pady=2).pack(side="right", pady=(8, 0), padx=(0, 8))

    def _note_editor_cancel(self):
        """MT-27 (0.35): the window X handler of the note editor
        (same documented path as the Cancel button)."""
        if self._note_editor_win is None:
            return
        try:
            if not self._note_editor_win.winfo_exists():
                self._note_editor_win = None
                return
        except tk.TclError:
            self._note_editor_win = None
            return
        win = self._note_editor_win
        win.destroy()
        self._note_editor_win = None

    def _open_table_details(self, table_key: str):
        """MT-22 (0.30) + MT-26 (0.34): the read-only table details
        window (addressed by the table key - relative in a single-root
        session, absolute in a multi-root one).

        One Toplevel shows the indexed facts for the table (path,
        folder, size, modified, bound processes, index status, pin
        state, last used, running PIDs, content sha) plus the
        on-demand load-gate re-check - the same
        ``gate_table_for_load`` pass MT-9 runs at load time, named
        refusal code + displayable detail - so the user can inspect a
        table before loading it.  A second open lifts the window
        instead of duplicating it; the window closes on trainer entry
        with the rest of the waiting view.  The row builder is pure in
        ``table_details.py`` (the only I/O is the bounded gate
        re-check, which reads the file under the load limit)."""
        if self._details_win is not None:
            try:
                if self._details_win.winfo_exists():
                    self._details_win.lift()
                    self._details_win.focus_set()
                    return
            except tk.TclError:
                pass
            self._details_win = None
        entry = self.app.index.get_by_key(table_key)
        if entry is None:
            self._set_status("No index entry for " + table_key)
            return
        from pathlib import Path
        from .table_details import table_detail_lines
        from .table_gate import gate_table_for_load
        # MT-26 (0.34): the table file lives under the entry's index
        # root (multi-root), falling back to the primary folder.
        base = (getattr(entry, "root", "")
                or (self.app.folders[0] if self.app.folders else ""))
        gate = gate_table_for_load(str(Path(base) / entry.relative_path),
                                   entry)
        pids = [e.pid for e in self._running
                for n in entry.process_names
                if e.name.casefold() == n.casefold()]
        last_used = dict(self.app.recent_tables).get(table_key)
        # MT-24 (0.32): the details window shows the persisted
        # background plan-analysis entry for the table's content sha
        # (None while pending - the row says so).
        analysis = self.app.analysis_store.get(entry.sha256)
        lines = table_detail_lines(entry, root=base,
                                   pinned=self.app.is_table_pinned(table_key),
                                   last_used=last_used,
                                   running_pids=pids, gate=gate,
                                   analysis=analysis,
                                   notes=self.app.notes_store.get(entry.sha256))
        win = tk.Toplevel(self.root)
        self._details_win = win
        win.title("Table details - " + table_key)
        win.configure(bg=BG, padx=16, pady=16)
        win.transient(self.root)
        win.resizable(False, False)
        tk.Label(win, text="Table details (read-only)", bg=BG, fg=FG,
                 font=("Segoe UI", 13, "bold"),
                 anchor="w").pack(fill="x")
        body = tk.Frame(win, bg=BG)
        body.pack(fill="x", pady=(8, 8))
        for label, value in lines:
            tk.Label(body, text=label, bg=BG, fg=FG_DIM, anchor="w",
                     justify="left", font=("Segoe UI", 11, "bold"),
                     width=22).pack(side="left", anchor="n", pady=2)
            tk.Label(body, text=value, bg=BG, fg=FG, anchor="w",
                     justify="left", font=("Segoe UI", 11),
                     wraplength=520).pack(side="left", fill="x",
                                          expand=True, padx=(12, 0),
                                          pady=2)
        tk.Button(win, text="Close", command=win.destroy,
                  bg="#2a3547", fg=FG, activebackground="#3a4a63",
                  activeforeground=FG, font=("Segoe UI", 12)
                  ).pack(fill="x", pady=(4, 0))

    def _open_process_picker(self, entry, candidates, origin):
        """The MT-11 process picker: one row per running candidate
        (name + PID), an Attach button and Cancel.

        ``origin`` names the pending action the choice resumes:
        ``auto-load`` (the auto-load request), ``explicit`` (the MT-10
        table load), ``choice`` (a table from the open table picker) or
        ``attach`` (the MT-12 attach after a detach).
        """
        top = tk.Toplevel(self.root)
        if origin == "attach":
            top.title("Which process to attach?")
        else:
            top.title("Which process for " + entry.relative_path + "?")
        top.resizable(False, False)
        top.transient(self.root)
        tk.Label(top, text="Select the running process to attach to:",
                 anchor="w", padx=14, font=("Segoe UI", 11)
                 ).pack(fill="x", pady=(12, 4))
        listbox = tk.Listbox(top, exportselection=False, width=48,
                             height=8, font=("Segoe UI", 10))
        for cand in candidates:
            listbox.insert("end", cand.name + "  (PID " + str(cand.pid) + ")")
        listbox.pack(padx=14, pady=4)
        if candidates:
            listbox.selection_set(0)
        buttons = tk.Frame(top, padx=14)
        buttons.pack(fill="x", pady=(4, 12))
        tk.Button(buttons, text="Attach",
                  command=self._proc_picker_attach,
                  font=("Segoe UI", 12), width=10,
                  bg="#2a3547", fg=FG).pack(side="left")
        tk.Button(buttons, text="Cancel",
                  command=self._proc_picker_cancel,
                  font=("Segoe UI", 12), width=10,
                  bg="#2a3547", fg=FG).pack(side="left", padx=(8, 0))
        self._proc_picker = top
        self._proc_picker_listbox = listbox
        self._proc_picker_candidates = tuple(candidates)
        self._proc_picker_entry = entry
        self._proc_picker_origin = origin
        top.protocol("WM_DELETE_WINDOW", self._proc_picker_cancel)
        try:
            top.grab_set()
        except tk.TclError:
            pass
        top.update_idletasks()

    def _proc_picker_attach(self):
        if self._proc_picker is None:
            return
        sel = self._proc_picker_listbox.curselection()
        if not sel:
            self._set_status("No process selected.")
            return
        self._proc_picker_chosen(sel[0])

    def _proc_picker_chosen(self, index):
        """Route the user's process choice to the pending action."""
        origin = self._proc_picker_origin
        entry = self._proc_picker_entry
        chosen = self._proc_picker_candidates[index]
        self._close_proc_picker()
        self._attach_pin = {"pid": chosen.pid}
        if origin == "attach":
            # MT-12: resume the held attach to the chosen PID.
            try:
                self.engine.resume_attach()
            except Exception as exc:
                messagebox.showerror("Attach failed", str(exc),
                                     parent=self.root)
            return
        if origin == "choice":
            outcome = self.app.orchestrator.choose(self._choice_table_rel)
            rel = self._choice_table_rel
            self._choice_table_rel = None
            if not outcome.ok:
                self._set_status("Load failed: " + (outcome.error or ""))
                messagebox.showerror("Table load failed",
                                     (outcome.error or "unknown error"),
                                     parent=self.root)
                self._set_status(self._waiting_status_line())
                return
            # MT-15 (0.26): successful load feeds the rolling recent
            # list (same rule as the _start_load path).
            self.app.remember_recent_table(rel)
            self._enter_trainer(outcome.plan, entry)
            return
        self._start_load(entry, chosen,
                         explicit=(origin == "explicit"))

    def _proc_picker_cancel(self):
        if self._proc_picker is None:
            return
        origin = self._proc_picker_origin
        candidates = self._proc_picker_candidates
        self._close_proc_picker()
        if origin == "attach":
            # Stay detached; the engine holds the attach until the user
            # chooses again (the status line shows the hold).
            return
        if origin == "choice":
            # The table choice stays deferred exactly like "Not now".
            orch = self.app.orchestrator
            if orch.state == STATE_CHOOSING and orch.choice is not None:
                for e in orch.choice.snapshot_entries:
                    orch.suppress(orch.choice.process_key, e.pid)
                orch.cancel_choice()
            self._set_status("Table choice deferred; not asking again while "
                             "this exact process runs. Use Retry load to "
                             "re-arm.")
            return
        if origin == "auto-load":
            # Declined the pick: do not re-ask while these exact
            # processes run (Retry load re-arms, as always).
            orch = self.app.orchestrator
            for e in candidates:
                orch.suppress(e.name.casefold(), e.pid)
            self._set_status("Process choice deferred; not auto-loading "
                             "while these exact processes run. Use Retry "
                             "load to re-arm.")
            return
        # Explicit load: the user asked and declined the pick; nothing
        # auto-retries, just return to the waiting status.
        self._set_status(self._waiting_status_line())

    def _close_proc_picker(self):
        if self._proc_picker is not None:
            self._proc_picker.destroy()
        self._proc_picker = None
        self._proc_picker_listbox = None
        self._proc_picker_candidates = ()
        self._proc_picker_entry = None
        self._proc_picker_origin = None

    def _toggle_attach_mode(self):
        """Flip the persisted attach mode (MT-11) and refresh the button."""
        mode = (ATTACH_MODE_ASK if self.app.attach_mode == ATTACH_MODE_AUTO
                else ATTACH_MODE_AUTO)
        try:
            self.app.set_attach_mode(mode)
        except Exception as exc:
            self._set_status("Attach mode change failed: " + str(exc))
            return
        if self._attach_mode_btn is not None:
            self._attach_mode_btn.configure(text="Attach: " + mode)
        if self._meta_label is not None:
            self._meta_label.configure(text=self._meta_text())
        self._set_status("Attach mode: " + mode +
                         (" - the process picker is shown for every "
                          "attach" if mode == ATTACH_MODE_ASK
                          else " - auto-attach, smallest PID when "
                               "several instances run"))

    def _toggle_auto_rescan(self):
        """MT-25 (0.33): flip the persisted auto-rescan flag and refresh
        the button."""
        enabled = not self.app.auto_rescan
        try:
            self.app.set_auto_rescan(enabled)
        except Exception as exc:
            self._set_status("Auto-rescan change failed: " + str(exc))
            return
        if self._auto_rescan_btn is not None:
            self._auto_rescan_btn.configure(text="Auto-rescan: "
                                              + ("on" if enabled else "off"))
        self._set_status("Auto-rescan: " + ("on" if enabled else "off")
                         + " (every "
                         + str(AUTO_RESCAN_INTERVAL_SECONDS) + " s)")

    def _set_trainer_grid_columns(self, columns: int) -> None:
        """MT-21 (0.36): the trainer header's "Columns: N" cycle changed
        the grid column count; persist it through the app (named
        refusal for a bogus value, which the window can only produce
        by construction)."""
        try:
            self.app.set_grid_columns(columns)
        except ValueError:
            pass

    def _detach_or_attach(self):
        """The MT-12 header action: detach the live target, or (while
        detached by the user) attach - in 'ask' mode via the process
        picker, in 'auto' mode by resuming the ordinary wait."""
        engine = self.engine
        if engine is None:
            return
        if engine.memory is not None:
            try:
                engine.pause_attach()
            except Exception as exc:
                messagebox.showerror("Detach failed", str(exc),
                                     parent=self.root)
                return
            try:
                engine.reattach()
            except Exception as exc:
                messagebox.showerror("Detach failed", str(exc),
                                     parent=self.root)
            return
        if not engine.attach_paused:
            # Detached by the target exit, not by the user: the ordinary
            # wait already runs, there is nothing to resume.
            return
        if self.app.attach_mode == ATTACH_MODE_ASK:
            plan_name = engine.plan["process_name"]
            try:
                snapshot = self.app.lister.list_processes()
            except Exception as exc:
                self._set_status("Process snapshot failed: "
                                 + exc.__class__.__name__ + ": " + str(exc))
                return
            candidates = tuple(sorted(
                (e for e in snapshot if names_match(e.name, plan_name)),
                key=lambda e: e.pid))
            if candidates:
                self._open_process_picker(None, candidates,
                                          origin="attach")
                return
        try:
            engine.resume_attach()
        except Exception as exc:
            messagebox.showerror("Attach failed", str(exc),
                                 parent=self.root)

    # ------------------------------------------------------------------
    # table picker
    # ------------------------------------------------------------------

    def _open_picker(self, choice):
        top = tk.Toplevel(self.root)
        top.title("Which table for " + choice.process_name + "?")
        top.resizable(False, False)
        top.transient(self.root)
        selection = tk.StringVar(top)
        tk.Label(top, text=choice.process_name + " is running (PID "
                 + str(choice.snapshot_entries[0].pid) + ") and "
                 + str(len(choice.tables)) + " indexed tables bind to it:",
                 anchor="w", padx=14,
                 font=("Segoe UI", 11)).pack(fill="x", pady=(12, 4))
        for entry in choice.tables:
            tk.Radiobutton(top, text=entry.relative_path,
                           value=entry.relative_path, variable=selection,
                           anchor="w", padx=14, font=("Segoe UI", 11)
                           ).pack(fill="x")
        buttons = tk.Frame(top, padx=14)
        buttons.pack(fill="x", pady=(4, 12))
        tk.Button(buttons, text="Load",
                  command=lambda: self._picker_chosen(selection.get()),
                  font=("Segoe UI", 12), width=10,
                  bg="#2a3547", fg=FG).pack(side="left")
        tk.Button(buttons, text="Not now", command=self._picker_cancel,
                  font=("Segoe UI", 12), width=10,
                  bg="#2a3547", fg=FG).pack(side="left", padx=(8, 0))
        self._picker = top
        self._picker_selection = selection
        top.protocol("WM_DELETE_WINDOW", self._picker_cancel)
        try:
            top.grab_set()
        except tk.TclError:
            pass
        top.update_idletasks()

    def _picker_chosen(self, rel: str | None):
        if self._picker is None:
            return
        picker = self._picker
        self._picker = None
        selection = self._picker_selection
        self._picker_selection = None
        picker.destroy()
        orch = self.app.orchestrator
        if rel is None or not selection.get():
            if orch.state == STATE_CHOOSING:
                for e in orch.choice.snapshot_entries:
                    orch.suppress(orch.choice.process_key, e.pid)
                orch.cancel_choice()
            self._set_status("Table choice deferred; not asking again while "
                             "this exact process runs. Use Retry load to "
                             "re-arm.")
            return
        # MT-11 (0.25): in 'ask' mode the target process must be picked
        # before the load; the choice stays open until that is resolved.
        if (self.app.attach_mode == ATTACH_MODE_ASK
                and orch.state == STATE_CHOOSING and orch.choice is not None
                and orch.choice.snapshot_entries):
            self._choice_table_rel = rel
            entry = next(t for t in orch.choice.tables
                         if t.relative_path == rel)
            self._open_process_picker(
                entry, tuple(orch.choice.snapshot_entries), origin="choice")
            return
        outcome = orch.choose(rel)
        if not outcome.ok:
            self._set_status("Load failed: " + (outcome.error or ""))
            messagebox.showerror("Table load failed",
                                 (outcome.error or "unknown error"),
                                 parent=self.root)
            self._set_status(self._waiting_status_line())
            return
        # MT-15 (0.26): successful load feeds the rolling recent list
        # (same rule as the _start_load path).
        self.app.remember_recent_table(rel)
        entry = next(t for t in self.app.orchestrator.choice.tables
                     if t.relative_path == rel) if self.app.orchestrator.choice \
            else None
        # Auto mode: the documented smallest-PID rule; pin it so the
        # session cannot drift to another instance mid-flight.
        if self.app.orchestrator.choice is not None:
            self._attach_pin = {"pid": min(
                e.pid for e in self.app.orchestrator.choice.snapshot_entries)}
        else:
            self._attach_pin = {"pid": None}
        self._enter_trainer(outcome.plan, entry)

    def _picker_cancel(self):
        if self._picker is None:
            return
        picker = self._picker
        self._picker = None
        self._picker_selection = None
        picker.destroy()
        orch = self.app.orchestrator
        if orch.state == STATE_CHOOSING and orch.choice is not None:
            for e in orch.choice.snapshot_entries:
                orch.suppress(orch.choice.process_key, e.pid)
            orch.cancel_choice()
        self._set_status("Table choice deferred; not asking again while "
                         "this exact process runs. Use Retry load to re-arm.")

    # ------------------------------------------------------------------
    # mode switching / lifecycle
    # ------------------------------------------------------------------

    def _back_to_master(self):
        if self.engine is None:
            return
        self._persist_sidecar()
        clean = self.engine.close()
        self.engine = None
        self.trainer_window = None
        if not clean:
            messagebox.showwarning(
                "Cleanup needs attention",
                "The trainer state and session journals were preserved; "
                "restart the target before manual recovery.",
                parent=self.root)
        self.app.orchestrator.deactivate()
        # MT-25 (0.33): die neu gebaute Waiting-View armiert den
        # Auto-Rescan-Zyklus frisch (erste Passage nach einem vollen
        # Intervall; der Initial-Rescan lief schon beim Fensterbau).
        self._last_auto_rescan = time.monotonic()
        # The MT-10/11 pickers are children of the root that is rebuilt
        # below; close them explicitly before the teardown.
        self._close_proc_picker()
        self._close_table_load_picker()
        for binding in ("<Prior>", "<Next>", "<MouseWheel>", "<Escape>",
                        "<Configure>"):
            self.root.unbind(binding)
        for child in self.root.winfo_children():
            child.destroy()
        self._build_waiting_view()
        self._set_status("Back to Master wait mode.")
        self.root.after(self.app.poll_ms, self._poll)

    def close(self):
        # MT-24 (0.32): stop the background plan analysis first
        # (bounded join; the thread is a daemon anyway, so a stuck
        # compile can never block the process exit).
        if self.app.analysis_worker is not None:
            self.app.analysis_worker.stop()
            self.app.analysis_worker = None
        if self.engine is not None:
            self._persist_sidecar()
            clean = self.engine.close()
            self.engine = None
            if not clean:
                messagebox.showwarning(
                    "Cleanup needs attention",
                    "The trainer state and session journals were preserved; "
                    "restart the target before manual recovery.",
                    parent=self.root)
        if self._picker is not None:
            self._picker.destroy()
            self._picker = None
        self._close_proc_picker()
        self._close_table_load_picker()
        self.app.closed = True
        self.root.destroy()

    def _persist_sidecar(self):
        """MT-6 save-on-close: persist the session's restored settings
        document back to the table's sidecar (best effort; a named refusal,
        e.g. 'nothing to persist', never breaks the session lifecycle)."""
        document = getattr(self, "_sidecar_document", None)
        sha = getattr(self, "_sidecar_sha", None)
        if document is None or sha is None:
            return
        try:
            self.app.settings_store.save_for(document, sha)
        except Exception:
            pass


def run_master(folder=None, *, state_home: str | None = None,
               debug_log: bool = False, poll_ms: int = WAIT_POLL_MS) -> int:
    """Create the Tk root, build the Master window, run mainloop.

    Folder resolution (ask on first start; MT-26 multi-root): an explicit
    ``folder`` argument always wins as the primary root (the stored
    folders are indexed behind it); without one, the stored table folders
    are kept as-is (a missing stored folder stays visible as a scan
    problem, and "Folders…" fixes the list); only a genuinely first start
    (or no stored folders at all) shows the directory picker, and a
    cancelled first-start picker exits with 0.
    """
    from pathlib import Path
    home = state_home or _default_state_home()
    stored = load_master_state(Path(home) / MASTER_STATE_FILENAME)
    if folder is not None:
        folder = Path(folder)
        if not folder.is_dir():
            print("Error: folder not found: " + str(folder), flush=True)
            return 2
        # MT-26: the explicit folder is the primary; the stored folders
        # are indexed behind it (deduped, order kept).
        folders = [str(folder)]
        seen = {f.casefold() for f in folders}
        for saved in (stored.table_folders if stored is not None else ()):
            if saved and saved.casefold() not in seen:
                seen.add(saved.casefold())
                folders.append(saved)
        print("Using folder: " + folders[0], flush=True)
        for extra in folders[1:]:
            print("Also indexing stored folder: " + extra, flush=True)
    else:
        # MT-26: the stored folder list is kept (missing folders are
        # visible as scan problems); an empty list falls back to the
        # single stored last folder (pre-0.34 documents carry only that).
        folders = [f for f in
                   (stored.table_folders if stored is not None else ())
                   if f]
        if not folders and stored is not None and stored.last_folder:
            folders = [stored.last_folder]
        existing = [f for f in folders if Path(f).is_dir()]
        if existing:
            print("Using folder from last session: " + folders[0],
                  flush=True)
            for extra in folders[1:]:
                state = " (missing - scan problem)" \
                    if not Path(extra).is_dir() else ""
                print("Also indexing stored folder: " + extra + state,
                      flush=True)
        elif folders:
            # Every stored folder is gone: ask; the pick becomes the
            # primary (the stored list stays behind, missing folders
            # visible as scan problems); cancel keeps the stored list.
            bootstrap = tk.Tk()
            bootstrap.withdraw()
            picked = filedialog.askdirectory(
                parent=bootstrap, title="Choose the folder with your tables")
            bootstrap.destroy()
            if picked:
                folders = [picked] + folders
                print("Using folder: " + picked, flush=True)
            else:
                print("Stored folders are missing; keeping them "
                      "(visible as scan problems). Use 'Folders...' "
                      "to fix the list.", flush=True)
        else:
            bootstrap = tk.Tk()
            bootstrap.withdraw()
            picked = filedialog.askdirectory(
                parent=bootstrap, title="Choose the folder with your tables")
            bootstrap.destroy()
            if not picked:
                print("No folder chosen; nothing to do.", flush=True)
                return 0
            folders = [picked]
    app = MasterApp(folders[0], state_home=home, debug_log=debug_log,
                    poll_ms=poll_ms, folders=folders[1:])
    try:
        app.save_index()
        app.persist_state()
    except Exception:
        pass
    root = tk.Tk()
    window = MasterWindow(root, app)
    root.mainloop()
    return 0
