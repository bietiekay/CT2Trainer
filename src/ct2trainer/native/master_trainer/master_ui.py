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
  waiting view, so the same process can keep watching the folder.

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
                           STATE_CHOOSING, TickOutcome)
from .master_state import (MASTER_STATE_SCHEMA, MASTER_STATE_FILENAME,
                           MasterState, load_master_state, save_master_state)
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

    def persist_folder(self) -> None:
        """Remember the current table folder for the next parameterless
        start (best effort, like the index persistence)."""
        try:
            save_master_state(MasterState(MASTER_STATE_SCHEMA, self.folder),
                              self.state_path())
        except Exception:
            pass

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
        self.persist_folder()

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
        self._table_frame = None
        self._folder_label = None
        self._meta_label = None
        self._running_label = None
        self._status_var = None
        # Live bound-process feedback of the latest waiting tick.
        self._running: tuple = ()
        self._running_keys: frozenset = frozenset()
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
        self.root.geometry("980x600")
        self.root.minsize(680, 420)
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
        repo_link(header, bg=BG_HEADER, fg=FG).pack(side="right", padx=(0, 16))
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
        cols = ("table", "processes", "status", "detail")
        self._table_tree = ttk.Treeview(frame, columns=cols, show="headings",
                                        height=16)
        for name, text, width in (("table", "Table", 300),
                                  ("processes", "Process name(s)", 260),
                                  ("status", "Status", 90),
                                  ("detail", "Detail", 260)):
            self._table_tree.heading(name, text=text)
            self._table_tree.column(name, width=width, anchor="w")
        scroll = ttk.Scrollbar(frame, orient="vertical",
                               command=self._table_tree.yview)
        self._table_tree.configure(yscrollcommand=scroll.set)
        self._table_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self._status_var = tk.StringVar(value="Scanning…")
        status = tk.Frame(self.root, bg=BG, height=40, padx=12)
        status.pack(fill="x")
        status.pack_propagate(False)
        tk.Label(status, textvariable=self._status_var, anchor="w",
                 justify="left", wraplength=900, bg=BG, fg=FG,
                 font=("Segoe UI", 11)).pack(side="left", fill="x", expand=True)
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
        if app.last_scan_at:
            parts.append("scanned " + app.last_scan_at)
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
        for entry in self.app.index.tables():
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
            tree.insert("", "end", values=(entry.relative_path, names,
                                           status, detail))

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
        try:
            outcome = self.app.orchestrator.tick()
            self._set_running(outcome.running)
            self._set_status(self._waiting_status_line())
            if outcome.request is not None and outcome.request_process is not None:
                self._start_load(outcome.request, outcome.request_process)
            elif outcome.choice is not None and self._picker is None:
                self._open_picker(outcome.choice)
        except Exception as exc:
            # Fail-closed tick: name the problem, keep the loop alive.
            self._set_status("Waiting tick failed: " + exc.__class__.__name__
                             + ": " + str(exc))
        if not self.app.closed and self.engine is None:
            self.root.after(self.app.poll_ms, self._poll)

    def _start_load(self, entry, process):
        self._set_status("Loading " + entry.relative_path + " for " +
                         process.name + " (PID " + str(process.pid) + ")…")
        outcome = self.app.orchestrator.load(entry, process)
        if not outcome.ok:
            self._set_status("Load failed: " + outcome.error)
            messagebox.showerror("Table load failed",
                                 entry.relative_path + "\n\n" + outcome.error,
                                 parent=self.root)
            self._set_status(self._waiting_status_line())
            return
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
            return
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
                return
            try:
                engine = TrainerEngine(plan,
                                       state_dir=self.app.state_dir_for(plan))
                break
            except StaleStateRecoverable as exc:
                if not self._confirm_recovery("stale state", exc):
                    self._fail_trainer_start(str(exc))
                    return
                continue
            except StaleArtifactsRecoverable as exc:
                if not self._confirm_recovery("unfinished receipts", exc):
                    self._fail_trainer_start(str(exc))
                    return
                continue
            except LiveStateConflict as exc:
                messagebox.showerror(
                    "Live session conflict",
                    "Another trainer session (PID " + str(exc.owner_pid) +
                    ") still uses this table's state.\nClose the other "
                    "trainer and try again.", parent=self.root)
                self._fail_trainer_start(str(exc))
                return
            except Exception as exc:
                messagebox.showerror("Trainer cannot start",
                                     str(exc), parent=self.root)
                self._fail_trainer_start(str(exc))
                return
        self.engine = engine
        try:
            self.trainer_window = TrainerWindow(self.root, engine,
                                                master_back=self._back_to_master)
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

    def _confirm_recovery(self, kind: str, exc) -> bool:
        if kind == "stale state":
            prompt = messagebox.askyesno(
                "Trainer state",
                ("A previous session of this table left a state lock; the "
                 "previous trainer process is verified terminated.\n\n"
                 "Recover (archive the old state byte-for-byte) and start?"),
                parent=self.root)
            if prompt:
                ok, detail = perform_stale_recovery(exc)
                if not ok:
                    messagebox.showerror("Recovery failed", detail,
                                         parent=self.root)
                    return False
        else:
            prompt = messagebox.askyesno(
                "Trainer state",
                ("A previous session left unfinished receipts; the recorded "
                 "processes are verified terminated.\n\nRecover and start?"),
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
    # table picker
    # ------------------------------------------------------------------

    def _open_picker(self, choice):
        top = tk.Toplevel(self.root)
        top.title("Which table for " + choice.process_name + "?")
        top.resizable(False, False)
        top.transient(self.root)
        selection = tk.StringVar()
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
        outcome = orch.choose(rel)
        if not outcome.ok:
            self._set_status("Load failed: " + (outcome.error or ""))
            messagebox.showerror("Table load failed",
                                 (outcome.error or "unknown error"),
                                 parent=self.root)
            self._set_status(self._waiting_status_line())
            return
        entry = next(t for t in self.app.orchestrator.choice.tables
                     if t.relative_path == rel) if self.app.orchestrator.choice \
            else None
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
        app.persist_folder()
    except Exception:
        pass
    root = tk.Tk()
    window = MasterWindow(root, app)
    root.mainloop()
    return 0
