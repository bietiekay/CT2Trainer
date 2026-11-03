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

All waiting-mode logic lives in the pure orchestrator; this module is
Tk wiring plus the picker Toplevel.
"""
from __future__ import annotations

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
                           PINNED_TABLES_LIMIT, RECENT_TABLES_LIMIT,
                           VIEW_FILTER_MAX, MasterState,
                           load_master_state, save_master_state)
from .table_filter import (SORT_MODES, VIEW_MODES, UNBOUND_PROCESS_LABEL,
                           filter_tables, group_tables_by_process,
                           pin_tables, sort_tables)
from .process_picker import (DECISION_PICK, attach_decision,
                             candidate_processes,
                             make_pinned_memory_factory)
from .process_watch import names_match
from .settings_sidecar import MasterSettingsStore
from .steamdeck_route import (attach_gate, require_engine_attach,
                              DeckAttachUnavailableError)

WAIT_POLL_MS = 1000


def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def master_title() -> str:
    return "CT2Trainer " + __version__ + " — Master Trainer"


def _default_state_home() -> str:
    import os
    from pathlib import Path
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_STATE_HOME")
    if base:
        return str(Path(base) / "CT2Trainer" / "native" / "master-trainer")
    return str(Path.home() / ".local" / "state" / "CT2Trainer" / "native" / "master-trainer")


class MasterApp:
    """Owns folder + index + orchestrator for one Master window."""

    def __init__(self, folder, *, state_home: str | None = None,
                 debug_log: bool = False, poll_ms: int = WAIT_POLL_MS,
                 lister=None, plan_compiler=None, state_dir_factory=None):
        from pathlib import Path
        from .table_index import TableIndex, load_index, reconcile
        from .process_watch import default_process_lister
        self.folder = str(Path(folder).expanduser().resolve())
        self.state_home = str(Path(state_home or _default_state_home()))
        self.debug_log = debug_log
        self.poll_ms = poll_ms
        self.closed = False
        self.last_scan_at: str | None = None
        index_path = Path(self.state_home) / "tables-index.json"
        try:
            stored = load_index(index_path)
        except Exception:
            stored = None
        result = reconcile(self.folder, stored)
        self.index = result.index
        self.last_changes = result.changes
        self.scan_error = result.scan_error
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
        self.lister = lister if lister is not None else default_process_lister()
        self.plan_compiler = plan_compiler
        self.state_dir_factory = state_dir_factory
        if plan_compiler is None:
            from ..compiler import compile_table
            from .table_gate import TableLoadGateRefusal, gate_table_for_load
            folder = self.folder

            def plan_compiler(entry, process_name):
                # MT-9 load gate: re-prove the table file (compatibility +
                # size + drift vs the index entry) at the moment the load
                # is requested.  A refusal raises the named refusal, so
                # the orchestrator's fail-closed loop guard records the
                # exact (name, PID) pair: no crash and no hot-retry even
                # when the target process was found (visible in the
                # status line + error dialog; Rescan/Retry load re-arm).
                path = Path(folder) / entry.relative_path
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
        """Remember the current table folder plus the MT-10/11/15/16/18
        preferences (last explicit table, attach mode, rolling recent
        tables, waiting-view filter/sort/display mode, pin set) for the
        next start (best effort, like the index persistence)."""
        try:
            save_master_state(MasterState(
                MASTER_STATE_SCHEMA, self.folder,
                last_table=self.last_table,
                attach_mode=self.attach_mode,
                recent_tables=tuple(self.recent_tables),
                view_filter=self.view_filter,
                view_sort=self.view_sort,
                view_mode=self.view_mode,
                pinned_tables=tuple(self.pinned_tables)),
                self.state_path())
        except Exception:
            pass

    def set_attach_mode(self, mode: str) -> None:
        """Switch the persisted attach mode (MT-11) and re-persist it."""
        if mode not in (ATTACH_MODE_AUTO, ATTACH_MODE_ASK):
            raise ValueError("attach mode must be 'auto' or 'ask'")
        self.attach_mode = mode
        self.persist_state()

    def set_view_settings(self, filter_query: str | None, sort_mode: str,
                          view_mode: str) -> None:
        """MT-16 (0.27): persist the waiting-view settings (schema 4).

        ``filter_query`` is the raw filter entry text ("" means no
        filter); ``sort_mode`` / ``view_mode`` must be one of the
        documented modes.  Invalid values raise the named ValueError,
        so the UI never persists what it would not render.
        """
        if sort_mode not in SORT_MODES:
            raise ValueError("unknown view sort mode: " + repr(sort_mode)
                             + " (expected one of "
                             + ", ".join(SORT_MODES) + ")")
        if view_mode not in VIEW_MODES:
            raise ValueError("unknown view mode: " + repr(view_mode)
                             + " (expected one of " + ", ".join(VIEW_MODES)
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
        self.persist_state()

    def set_table_pinned(self, relative_path: str, pinned: bool) -> None:
        """MT-18 (0.28): pin/unpin one waiting-view table (schema 5)
        and re-persist the pin set.

        A pinned table floats to the top of the waiting view (list
        view) and to the top of its process group (process view); the
        pin order is the persistence order, most recent pin first.
        Invalid state raises the named ValueError, so the UI never
        persists what it would not render.
        """
        if not isinstance(relative_path, str) or not relative_path:
            raise ValueError("table path must be a non-empty string")
        current = {p.casefold() for p in self.pinned_tables}
        if pinned:
            if relative_path.casefold() in current:
                raise ValueError("table is already pinned")
            if len(self.pinned_tables) >= PINNED_TABLES_LIMIT:
                raise ValueError("pinned tables limit reached ("
                                 + str(PINNED_TABLES_LIMIT) + ")")
            self.pinned_tables = (relative_path,) + tuple(
                p for p in self.pinned_tables
                if p.casefold() != relative_path.casefold())
        else:
            if relative_path.casefold() not in current:
                raise ValueError("table is not pinned")
            self.pinned_tables = tuple(
                p for p in self.pinned_tables
                if p.casefold() != relative_path.casefold())
        self.persist_state()

    def is_table_pinned(self, relative_path: str) -> bool:
        """MT-18 (0.28): True when this relative path is in the
        persisted pin set (casefolded comparison, so the row identity
        and the stored pins compare the same on every platform)."""
        return relative_path.casefold() in {
            p.casefold() for p in self.pinned_tables}

    def remember_last_table(self, relative_path: str | None) -> None:
        """Remember the last explicitly loaded table (MT-10) and
        re-persist the master-state document."""
        self.last_table = relative_path
        self.persist_state()

    def remember_recent_table(self, relative_path: str) -> None:
        """Record a successful table load in the rolling recent list
        (MT-15): most recent first, deduplicated by relative path,
        capped at ``RECENT_TABLES_LIMIT``, re-persisted immediately."""
        if not isinstance(relative_path, str) or not relative_path:
            return
        at = _utc_now()
        remaining = [item for item in self.recent_tables
                     if item[0] != relative_path]
        self.recent_tables = ((relative_path, at),) \
            + tuple(remaining)[:RECENT_TABLES_LIMIT - 1]
        self.persist_state()

    def rescan(self) -> None:
        from .table_index import reconcile
        result = reconcile(self.folder, self.index)
        self.index = result.index
        self.last_changes = result.changes
        self.scan_error = result.scan_error
        self.last_scan_at = _utc_now()
        # Folder content changed: the orchestrator's cached names are read
        # live from self.index each tick, so nothing else to refresh.
        self.orchestrator.index = self.index
        self.orchestrator.retry()

    def set_folder(self, folder) -> None:
        from pathlib import Path
        from .table_index import TableIndex, reconcile, save_index
        self.folder = str(Path(folder).expanduser().resolve())
        result = reconcile(self.folder, TableIndex(self.folder, {}))
        self.index = result.index
        self.last_changes = result.changes
        self.scan_error = result.scan_error
        self.last_scan_at = _utc_now()
        self.orchestrator.index = self.index
        self.orchestrator.retry()
        try:
            save_index(self.index, self.index_path())
        except Exception:
            pass
        self.persist_state()

    def save_index(self) -> None:
        from .table_index import save_index
        try:
            save_index(self.index, self.index_path())
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
        self._table_frame = None
        self._folder_label = None
        self._meta_label = None
        self._running_label = None
        self._status_var = None
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
        header = tk.Frame(self.root, bg=BG_HEADER, height=44, padx=12)
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
        button(header, "Rescan", self._rescan).pack(side="right", padx=(0, 8))
        button(header, "Change folder…", self._change_folder).pack(side="right", padx=(0, 8))
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
        self._folder_label = tk.Label(self.root, text=self._folder_text(),
                                      bg=BG, fg=FG_DIM, font=("Segoe UI", 11),
                                      anchor="w", padx=12)
        self._folder_label.pack(fill="x")
        self._meta_label = tk.Label(self.root, text=self._meta_text(),
                                    bg=BG, fg=FG_DIM, font=("Segoe UI", 9),
                                    anchor="w", padx=12)
        self._meta_label.pack(fill="x")
        self._running_label = tk.Label(self.root,
                                       text=self._running_text(self._running),
                                       bg=BG, fg=FG, font=("Segoe UI", 10),
                                       anchor="w", padx=12)
        self._running_label.pack(fill="x")

        frame = ttk.Frame(self.root, padding=8)
        frame.pack(fill="both", expand=True)
        # MT-15 (0.26): the waiting-view tree carries the indexed size /
        # modified columns plus the Last-used feed of the recent list.
        cols = ("table", "processes", "status", "detail",
                "size", "modified", "last_used")
        self._table_tree = ttk.Treeview(frame, columns=cols, show="headings",
                                        height=16)
        for name, text, width in (("table", "Table", 220),
                                  ("processes", "Process name(s)", 170),
                                  ("status", "Status", 70),
                                  ("detail", "Detail", 170),
                                  ("size", "Size", 80),
                                  ("modified", "Modified", 130),
                                  ("last_used", "Last used", 150)):
            self._table_tree.heading(name, text=text)
            self._table_tree.column(name, width=width, anchor="w")
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
        status = tk.Frame(self.root, bg=BG, height=40, padx=12)
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
        button(self.root, "Retry load", self._retry, width=12).pack(
            anchor="e", padx=12)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._render_tables()

    def _folder_text(self) -> str:
        error = self.app.scan_error
        text = "Folder: " + self.app.folder
        if error:
            text += "  (scan problem: " + error + ")"
        return text

    def _meta_text(self) -> str:
        """One compact line: table counts, bound process names, last scan
        time and the state home (where the index + per-table state live)."""
        app = self.app
        entries = app.index.tables()
        unreadable = sum(1 for e in entries if e.status != "ok")
        if unreadable:
            count = f"{len(entries)} tables ({len(entries) - unreadable} ok, " \
                    f"{unreadable} unreadable)"
        else:
            count = f"{len(entries)} table(s) indexed"
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
        if self._view_mode != "process":
            for entry in rows:
                self._insert_table_row("", entry, pids_by_key, recent_at)
            return
        for label, group in group_tables_by_process(rows):
            parent = tree.insert("", "end", open=True, values=(
                label, str(len(group)) + " table(s)",
                "", "", "", "", ""))
            for entry in group:
                self._insert_table_row(parent, entry, pids_by_key,
                                       recent_at)

    def _insert_table_row(self, parent: str, entry, pids_by_key: dict,
                          recent_at: dict) -> None:
        """One waiting-view table row (flat list or group child)."""
        names = ", ".join(entry.process_names) or "(none found)"
        if entry.status == "ok":
            pids = sorted(set(p for n in entry.process_names
                              for p in pids_by_key.get(n.casefold(), ())))
            if pids:
                status = "running"
                detail = "PID " + ", ".join(str(p) for p in pids)
            else:
                status, detail = "ok", ""
        else:
            status = "unreadable"
            detail = entry.detail or ""
        # MT-18 (0.28): the pin marker lives in the detail column -
        # the first column (the relative path) stays the bare row
        # identity the load paths key off.
        if self.app.is_table_pinned(entry.relative_path):
            detail = "pinned" + (" - " + detail if detail else "")
        self._table_tree.insert(parent, "end", values=(
            entry.relative_path, names, status, detail,
            self._format_size(entry.size),
            self._format_mtime(entry.mtime_ns),
            recent_at.get(entry.relative_path, "")))

    def _visible_tables(self) -> list:
        """MT-13/18 (0.26/0.28): the waiting-view row set - the full
        index, sorted per the current mode, filtered per the current
        query, then the persisted pin set floated to the top (MT-18;
        pinned rows not in the filtered set are ignored).  Row
        identity stays the relative path; the load picker and the
        auto-load path keep using the full index."""
        entries = sort_tables(self.app.index.tables(), self._sort_mode)
        return pin_tables(filter_tables(entries, self._filter_query),
                          self.app.pinned_tables)

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
                                   self._view_mode)
        self._render_tables()

    def _cycle_view(self):
        """MT-17 (0.27): list -> process -> list (the choice is
        persisted with the waiting-view settings, MT-16)."""
        order = list(VIEW_MODES)
        self._view_mode = order[(order.index(self._view_mode) + 1)
                                % len(order)]
        self._view_btn.configure(text="View: " + self._view_mode)
        self.app.set_view_settings(self._filter_query, self._sort_mode,
                                   self._view_mode)
        self._render_tables()

    def _on_filter_edit(self, _event):
        """MT-13 (0.26): live filter - re-render plus the meta line
        counter ('filtered: N/M') while a query is active.  The query
        is persisted with the other waiting-view settings (MT-16)."""
        self._filter_query = self._filter_entry.get()
        self.app.set_view_settings(self._filter_query, self._sort_mode,
                                   self._view_mode)
        self._render_tables()
        if self._meta_label is not None:
            self._meta_label.configure(text=self._meta_text())

    def _on_filter_escape(self, _event):
        """MT-14 (0.26): Esc clears the filter and returns focus to
        the table list."""
        self._filter_entry.delete(0, "end")
        self._filter_query = ""
        self.app.set_view_settings(self._filter_query, self._sort_mode,
                                   self._view_mode)
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

    def _is_table_row(self, item: str) -> bool:
        """MT-17 (0.27): True for loadable table rows - group children
        in the process view and every row in the flat list.  Group rows
        themselves are display-only (no load)."""
        if self._table_tree.parent(item):
            return True
        return self._view_mode != "process"

    def _table_selected_rel(self):
        item = self._table_tree.focus()
        if not item:
            selected = self._table_tree.selection()
            if not selected:
                return None
            item = selected[0]
        if not self._is_table_row(item):
            return None
        values = self._table_tree.item(item, "values")
        return values[0] if values else None

    def _table_double_click(self, event):
        """MT-14 (0.26): double-click loads the clicked row through
        the MT-10 explicit-load path (named refusals included)."""
        item = self._table_tree.identify_row(event.y)
        if not item or not self._is_table_row(item):
            return
        values = self._table_tree.item(item, "values")
        if values:
            self._load_selected_table(values[0])

    def _table_return(self, _event):
        """MT-14 (0.26): Enter loads the selected/focused row."""
        rel = self._table_selected_rel()
        if rel:
            self._load_selected_table(rel)

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
        self._set_status("Rescanning…")
        self.app.rescan()
        self.app.save_index()
        self._meta_label.configure(text=self._meta_text())
        self._render_tables()
        self._set_status(self._waiting_status_line())

    def _change_folder(self):
        folder = filedialog.askdirectory(
            parent=self.root, title="Choose the folder with your tables")
        if not folder:
            return
        self.app.set_folder(folder)
        self.app.save_index()
        self._folder_label.configure(text=self._folder_text())
        self._meta_label.configure(text=self._meta_text())
        self._set_running(self._running)
        self._render_tables()
        self._set_status(self._waiting_status_line())

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
        try:
            self.trainer_window = TrainerWindow(
                self.root, engine, master_back=self._back_to_master,
                detach_cb=self._detach_or_attach)
        except Exception as exc:
            # The engine is up but the trainer view could not be built:
            # close the engine again and fail the load so the waiting
            # loop (and its loop guard) stay consistent.
            self.engine = None
            try:
                engine.close()
            except Exception:
                pass
            self.trainer_window = None
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

    def _load_selected_table(self, rel):
        """Explicit user table load (MT-10): resolve the table against
        the live snapshot, apply the attach decision, then load.  Named
        refusals land in the status line + dialog, never a crash."""
        try:
            request = self.app.orchestrator.request_load(rel)
        except ExplicitLoadRefusal as exc:
            self._set_status("Explicit load refused: " + exc.detail)
            messagebox.showerror("Table load refused",
                                 rel + "\n\n" + exc.detail,
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
        listbox = tk.Listbox(top, exportselection=False, width=56,
                             height=12, font=("Segoe UI", 10))
        for entry in entries:
            listbox.insert("end", entry.relative_path)
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
        self._close_table_load_picker()
        if not sel:
            return
        self._load_selected_table(
            self._table_load_entries[sel[0]].relative_path)

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
        rel = values[0]
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Load this table",
                         command=lambda: self._load_selected_table(rel))
        if self.app.is_table_pinned(rel):
            menu.add_command(label="Unpin",
                             command=lambda: self._toggle_table_pin(rel,
                                                                    False))
        else:
            menu.add_command(label="Pin to top",
                             command=lambda: self._toggle_table_pin(rel,
                                                                    True))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.destroy()

    def _toggle_table_pin(self, rel: str, pinned: bool):
        """MT-18 (0.28): the row-menu pin toggle - re-renders on
        success, surfaces the named refusal in the status line on
        failure (no crash, no state change)."""
        try:
            self.app.set_table_pinned(rel, pinned)
        except ValueError as exc:
            self._set_status(str(exc))
            return
        self._render_tables()
        self._set_status(("Pinned " if pinned else "Unpinned ") + rel)

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

    Folder resolution (ask on first start): an explicit ``folder`` argument
    always wins; without one, the last-used folder stored in the state home
    is reused when it still exists; only a genuinely first start (or a
    stale stored folder) shows the directory picker.
    """
    from pathlib import Path
    home = state_home or _default_state_home()
    if folder is None:
        stored = load_master_state(Path(home) / MASTER_STATE_FILENAME)
        last = stored.last_folder if stored is not None else None
        if last is not None and Path(last).is_dir():
            folder = Path(last)
            print("Using folder from last session: " + str(folder),
                  flush=True)
        else:
            bootstrap = tk.Tk()
            bootstrap.withdraw()
            folder = filedialog.askdirectory(
                parent=bootstrap, title="Choose the folder with your tables")
            bootstrap.destroy()
            if not folder:
                print("No folder chosen; nothing to do.", flush=True)
                return 0
    folder = Path(folder)
    if not folder.is_dir():
        print("Error: folder not found: " + str(folder), flush=True)
        return 2
    app = MasterApp(folder, state_home=home, debug_log=debug_log,
                    poll_ms=poll_ms)
    try:
        app.save_index()
        app.persist_state()
    except Exception:
        pass
    root = tk.Tk()
    window = MasterWindow(root, app)
    root.mainloop()
    return 0
