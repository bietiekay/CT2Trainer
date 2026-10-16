"""Touch-sized Tk frontend for the independent declarative trainer engine."""
from __future__ import annotations

import json
import math
from pathlib import Path
import struct
import tkinter as tk
from tkinter import messagebox, ttk

from .engine import (TrainerEngine, NativeRuntimeError, parse_value, format_value,
                     StaleStateRecoverable, StaleArtifactsRecoverable,
                     perform_stale_recovery,
                     LiveStateConflict, terminate_live_session)
from .about_ui import repo_link, trainer_title
from .architecture import plan_architecture
from .window_icon import window_icon_path
from .ui_layout import (
    BREADCRUMB_ROW_HEIGHT,
    MIN_WINDOW_HEIGHT_WIDE,
    activation_set_summary,
    breadcrumb_labels,
    cards_area_height,
    enter_group,
    exit_group,
    filtered_entries,
    is_navigable_group,
    level_entries,
    page_size_for_cards,
    staged_card_state,
    staged_provider_labels,
    STAGED_PENDING,
)


# High-contrast dark palette: dark background, bright text.
BG = "#10141c"
BG_HEADER = "#181f2b"
BG_CARD = "#1a2130"
BG_BUTTON = "#2a3547"
BG_BUTTON_ACTIVE = "#3a4a63"
BG_CLOSE = "#5c2b33"
BG_CLOSE_ACTIVE = "#7c3a45"
FG = "#f2f5fa"
FG_DIM = "#c3ccda"
ON_BG, ON_FG = "#1fbf4a", "#07130a"
OFF_BG, OFF_FG = "#e5484d", "#ffffff"

# Pre-synthesized toggle tones, kept in module scope for the whole process:
# winsound SND_MEMORY + SND_ASYNC requires the buffer to stay alive for the
# whole playback.
_TONE_CACHE: dict[str, bytes] = {}


def _tone_wav(freq: float, ms: int = 120, rate: int = 22050) -> bytes:
    """Short sine tone with a 20 ms fade-in/out as 16-bit mono WAV bytes."""
    n = int(rate * ms / 1000)
    fade = max(1, int(rate * 0.02))
    amp = 12000
    frames = bytearray()
    for i in range(n):
        gain = 1.0 if (i + 1 >= fade and n - i >= fade) else min((i + 1) / fade, (n - i) / fade)
        frames += struct.pack("<h", int(amp * gain * math.sin(2 * math.pi * freq * i / rate)))
    header = (b"RIFF" + struct.pack("<I", 36 + len(frames)) + b"WAVEfmt "
              + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
              + b"data" + struct.pack("<I", len(frames)))
    return bytes(header + frames)


def play_toggle_sound(on: bool) -> None:
    """Confirmed manual toggle: ON plays the higher tone, OFF the lower one."""
    key = "on" if on else "off"
    if key not in _TONE_CACHE:
        _TONE_CACHE[key] = _tone_wav(880.0 if on else 440.0)
    try:
        import winsound
        winsound.PlaySound(_TONE_CACHE[key], winsound.SND_MEMORY | winsound.SND_ASYNC)
    except Exception:
        pass


class TrainerWindow:
    def __init__(self, root: tk.Tk, engine: TrainerEngine):
        self.root, self.engine = root, engine
        self.view = "Switches"
        self.page = 0
        self.page_size = 4
        # Hierarchical group navigation: group ids from the root down to the
        # currently shown level (pure contract in ui_layout). Empty = root.
        self.group_stack: list[int] = []
        self.drafts = {i: tk.StringVar(value=str(entry.get("value_default") or entry.get("default_value") or ""))
                       for i, entry in engine.entries.items() if entry["kind"] == "value"}
        self.current_labels: dict[int, tk.Label] = {}
        self.action_widgets: list[tk.Widget] = []
        self.status_text = tk.StringVar(value=engine.status)
        self.search_text = tk.StringVar()
        self.page_text = tk.StringVar()
        root.title(trainer_title(engine.plan["title"]))
        width = min(1600, max(400, root.winfo_screenwidth() - 100))
        height = min(900, max(620, root.winfo_screenheight() - 100))
        root.geometry(f"{width}x{height}")
        root.minsize(400, 610)
        root.option_add("*Font", ("Segoe UI", 12))
        root.configure(bg=BG)
        header = tk.Frame(root, bg=BG_HEADER, padx=12, pady=8)
        header.pack(fill="x")
        tk.Label(header, text=engine.plan["title"], bg=BG_HEADER, fg=FG, font=("Segoe UI", 20, "bold"), anchor="w").pack(side="left", fill="x", expand=True)
        self._button(header, "Close", self.close, width=8, bg=BG_CLOSE, activebackground=BG_CLOSE_ACTIVE, fg=FG).pack(side="right")
        repo_link(header, bg=BG_HEADER, fg=FG).pack(side="right")
        status = tk.Frame(root, bg=BG, padx=12)
        status.pack(fill="x")
        tk.Label(status, textvariable=self.status_text, anchor="w", justify="left", wraplength=900, bg=BG, fg=FG).pack(side="left", fill="x", expand=True)
        self._button(status, "Status / help", self.show_status, width=12).pack(side="right")
        toolbar = tk.Frame(root, bg=BG, padx=12)
        toolbar.pack(fill="x")
        self.toolbar = toolbar
        self.filter_buttons = []
        for column, name in enumerate(("Switches", "On / Saved", "Values", "All")):
            button = self._button(toolbar, name, lambda name=name: self.set_view(name))
            button.grid(row=column // 2, column=column % 2, sticky="nsew", padx=3, pady=3)
            self.filter_buttons.append(button)
        toolbar.columnconfigure((0, 1), weight=1)
        self.search_frame = tk.Frame(root, height=56, padx=12, pady=4, bg=BG)
        self.search_frame.pack(fill="x")
        self.search_frame.pack_propagate(False)
        tk.Label(self.search_frame, text="Search", bg=BG, fg=FG_DIM).pack(side="left", padx=(0, 8))
        tk.Entry(self.search_frame, textvariable=self.search_text, font=("Segoe UI", 16), bg=BG_CARD, fg=FG, insertbackground=FG, relief="solid", bd=1).pack(side="left", fill="both", expand=True)
        self.search_text.trace_add("write", lambda *_: self.changed_filter())
        # Interactive group-level row (back + breadcrumb segments); the pure
        # contract counts its 56 px between the search field and the cards.
        # Packed only while inside a group level.
        self.breadcrumb = tk.Frame(root, height=BREADCRUMB_ROW_HEIGHT, padx=12, pady=4, bg=BG)
        self.breadcrumb.pack(fill="x", after=self.search_frame)
        self.breadcrumb.pack_propagate(False)
        self.breadcrumb.pack_forget()
        self.cards = tk.Frame(root, bg=BG, padx=12)
        self.cards.pack(fill="both", expand=True)
        self.cards.bind("<Configure>", self.resized)
        nav = tk.Frame(root, bg=BG, padx=12, pady=6)
        nav.pack(fill="x")
        self._button(nav, "◀ Previous", lambda: self.move_page(-1), width=12).pack(side="left")
        tk.Label(nav, textvariable=self.page_text, bg=BG, fg=FG_DIM).pack(side="left", expand=True)
        self._button(nav, "Next ▶", lambda: self.move_page(1), width=12).pack(side="right")
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind("<Prior>", lambda _: self.move_page(-1))
        root.bind("<Next>", lambda _: self.move_page(1))
        root.bind("<MouseWheel>", lambda event: self.move_page(-1 if event.delta > 0 else 1))
        root.bind("<Escape>", self.on_escape)
        root.bind("<Configure>", self.resized)
        self.render()
        root.after(100, self.poll)

    @staticmethod
    def _button(parent, label, action, **kwargs):
        style = {"bg": BG_BUTTON, "fg": FG, "activebackground": BG_BUTTON_ACTIVE,
                 "activeforeground": FG, "disabledforeground": FG_DIM}
        style.update(kwargs)
        return tk.Button(parent, text=label, command=action, font=("Segoe UI", 13), height=2, pady=5, **style)

    def show_status(self):
        messagebox.showinfo("Trainer status", self.engine.status + "\n\n" + self.engine.error +
            f"\n\nTarget: {self.engine.plan['process_name']} ({plan_architecture(self.engine.plan)['machine']})\nTable SHA-256: {self.engine.plan['table_sha256']}" +
            "\n\nCurrent means a byte patch confirmed by this trainer. Auto-on on next game launch means a saved switch." +
            "\nApply value changes memory; ▲ / ▼ / Reset edit the draft only. Freeze captures the current value for this session." +
            "\nDependencies are enabled before the requested entry. Disable their consumers first." +
            "\nAn uncertain or crashed session blocks writes and keeps its journal. Preserve the state files; restart the target before manual recovery." +
            f"\n\nState folder: {self.engine.store.directory}", parent=self.root)

    def info(self, entry):
        path = entry.get("path", [])
        if isinstance(path, list):
            path = " / ".join(map(str, path))
        staged = entry.get("staged")
        staged_line = (("\nStaged: unlocks when active: " + ", ".join(staged.get("provider_labels", ())))
                       if staged else "")
        set_summary = activation_set_summary(entry, self.engine.entries)
        set_line = ("\n" + set_summary + " (source: %s)"
                    % entry["activation_sets"].get("source", "unknown")) if set_summary else ""
        messagebox.showinfo("Entry information", f"{entry['label']}\nID: {entry['id']}\nPath: {path}\n" +
            f"Type: {entry.get('variable_type', entry['kind'])}\n" +
            (entry.get("reason") or "Supported by the bounded native engine") + staged_line + set_line + "\n" +
            self.engine.entry_errors.get(entry["id"], "") +
            "\nRequired symbols: " + ", ".join(entry.get("requires", [])), parent=self.root)

    def filtered(self):
        """Thin wrapper over the pure view/search/level filter.

        Search is a table-wide escape hatch: a non-empty needle matches every
        entry (the ancestor path stays in the haystack), so a group child is
        reachable from any level. With an empty needle the current group level
        is applied first and only its direct children are candidates.
        """
        return filtered_entries(self.engine.entries, self.view, self.search_text.get(),
                                self.engine.applied, self.engine.desired, self.group_stack)

    def changed_filter(self):
        self.page = 0
        self.render()

    def set_view(self, name):
        self.view = name
        self.changed_filter()

    def move_page(self, delta):
        maximum = max(0, (len(self.filtered()) - 1) // self.page_size)
        self.page = min(maximum, max(0, self.page + delta))
        self.render()

    # Group navigation (pure contract in ui_layout; refusals surface through
    # the standard action error box). Every navigation resets the page.
    def open_group(self, entry):
        self.group_stack = enter_group(self.group_stack, entry, self.engine.entries)
        self.changed_filter()

    def exit_level(self):
        self.group_stack = exit_group(self.group_stack)
        self.changed_filter()

    def go_to_level(self, index):
        self.group_stack = list(self.group_stack[:index])
        self.changed_filter()

    def on_escape(self, _event):
        # Escape exits one level; at the root level it is a no-op.
        if self.group_stack:
            self.action(self.exit_level)

    def resized(self, event):
        if event.widget is self.root:
            columns = 2 if event.width < 650 else 4
            for index, button in enumerate(self.filter_buttons):
                button.grid_configure(row=index // columns, column=index % columns)
            for column in range(4):
                self.toolbar.columnconfigure(column, weight=1 if column < columns else 0)
            self.root.minsize(400, 720 if columns == 2 else 610)
        elif event.widget is self.cards:
            size = page_size_for_cards(self._cards_area_height(), self.view)
            if size != self.page_size:
                self.page_size = size
                self.render()

    def _cards_area_height(self):
        """Card area height per the pure layout contract.

        Inside a group level the breadcrumb row consumes its 56 px between
        the search field and the cards. Before the first map the toplevel
        reports 1 px; that pre-layout render then falls back to one row, as
        the original card-height computation did.
        """
        height = self.root.winfo_height()
        if height < MIN_WINDOW_HEIGHT_WIDE:
            return 0
        return cards_area_height(height, in_group=bool(self.group_stack))

    def action(self, callback):
        try:
            callback()
        except Exception as exc:
            self.engine.debug_log.error("ui-action-failed", exc,
                                        trainer_id=self.engine.plan.get("trainer_id"))
            messagebox.showerror("Trainer action failed", str(exc), parent=self.root)
        self.status_text.set(self.engine.status)
        self.render()

    def step(self, entry, direction):
        variable = self.drafts[entry["id"]]
        try:
            profile = entry.get('value_profile')
            if profile is not None and profile['kind'] in {'byte_array','string'}:
                raise NativeRuntimeError('Edit this array as exact hex byte pairs')
            current = bytes(profile['size']) if profile is not None else None
            literal = variable.get() or "0"
            raw = parse_value(entry, literal, current)
            displayed = format_value(entry, raw)
            if entry["variable_type"] in {"Float", "Double"}:
                candidate = str(float(displayed) + direction)
            elif profile is not None and profile['display'] == 'binary':
                candidate = format(max(0, int(displayed, 2) + direction), 'b')
            elif entry.get("show_as_hex"):
                candidate = format(max(0, int(displayed, 16) + direction), "X")
            else:
                candidate = str(int(displayed) + direction)
            parse_value(entry, candidate, current)
            variable.set(candidate)
        except NativeRuntimeError as exc:
            messagebox.showinfo("Value draft", str(exc), parent=self.root)

    def _toggle_with_sound(self, identifier):
        """Toggle a switch and play the appropriate tone on success."""
        was_active = identifier in self.engine.applied
        self.engine.toggle(identifier)
        now_active = identifier in self.engine.applied
        play_toggle_sound(on=now_active)

    def _render_breadcrumb(self):
        """Group-level row between the search field and the cards.

        Shown only while a group level is active: a "Back" button exits one
        level, and one segment per breadcrumb label (Root, then each group)
        jumps to that level. Refusals surface through the standard action
        error box.
        """
        for widget in self.breadcrumb.winfo_children():
            widget.destroy()
        if not self.group_stack:
            self.breadcrumb.pack_forget()
            return
        self.breadcrumb.pack(fill="x", after=self.search_frame)
        self._button(self.breadcrumb, "Back", lambda: self.action(self.exit_level), width=8).pack(side="left")
        labels = breadcrumb_labels(self.engine.entries, self.group_stack)
        for index, label in enumerate(labels):
            self._button(self.breadcrumb, label,
                         lambda i=index: self.action(lambda i=i: self.go_to_level(i)),
                         width=8).pack(side="left", padx=(4, 0))

    def render(self):
        self.page_size = page_size_for_cards(self._cards_area_height(), self.view)
        self._render_breadcrumb()
        for widget in self.cards.winfo_children():
            widget.destroy()
        self.current_labels.clear()
        self.action_widgets.clear()
        entries = self.filtered()
        maximum = max(0, (len(entries) - 1) // self.page_size)
        self.page = min(self.page, maximum)
        if self.group_stack:
            group_label = breadcrumb_labels(self.engine.entries, self.group_stack)[-1]
            self.page_text.set(f"{self.view} · {group_label} · {self.page + 1} / {maximum + 1} · {len(entries)} entries")
        else:
            self.page_text.set(f"{self.view} · {self.page + 1} / {maximum + 1} · {len(entries)} entries")
        selected = entries[self.page * self.page_size:(self.page + 1) * self.page_size]
        if not selected:
            tk.Label(self.cards, text="No entries match this view or search.", bg=BG, fg=FG_DIM, pady=30).pack(fill="x")
        for entry in selected:
            identifier = entry["id"]
            card = tk.Frame(self.cards, bg=BG_CARD, relief="solid", bd=1, padx=8, pady=5)
            card.pack(fill="x", pady=4)
            title_row = tk.Frame(card, bg=BG_CARD)
            title_row.pack(fill="x")
            full_label = entry["label"].replace("\n", " ")
            visible_label = full_label[:85] + ("…" if len(full_label) > 85 else "")
            title = tk.Label(title_row, text=visible_label, anchor="w", justify="left", wraplength=max(240, self.root.winfo_width() - 165), bg=BG_CARD, fg=FG, font=("Segoe UI", 16, "bold"))
            title.pack(side="left", fill="x", expand=True)
            self._button(title_row, "Info", lambda e=entry: self.info(e), width=5).pack(side="right")
            if entry["kind"] == "heading" and is_navigable_group(entry, self.engine.entries):
                # Navigable CE group: a button switches into the level.
                # Refusals (pure contract) surface through the action error box.
                children = len(level_entries(self.engine.entries, [identifier]))
                self._button(card, "Open group",
                             lambda e=entry: self.action(lambda e=e: self.open_group(e))
                             ).pack(fill="x", pady=(4, 0))
                tk.Label(card, text=f"{children} entries", anchor="w", bg=BG_CARD, fg=FG_DIM).pack(fill="x")
                continue
            if not entry["selected"] or not entry["supported"] or entry["kind"] in {"heading", "blocked"}:
                reason = "Not included in this trainer" if not entry["selected"] else entry.get("reason") or "Navigation heading"
                visible_reason = reason[:140] + ("… (Info)" if len(reason) > 140 else "")
                tk.Label(card, text=visible_reason, anchor="w", justify="left", bg=BG_CARD, fg=FG_DIM, wraplength=max(280, self.root.winfo_width() - 60)).pack(fill="x")
                continue
            if entry["kind"] == "script":
                active = identifier in self.engine.applied
                master = entry.get("activation_sets") is not None
                current = ("Unknown" if self.engine.blocked else ("ON" if active else "OFF")) if self.engine.memory else "Disconnected"
                if master and self.engine.memory is not None:
                    current = "Set applied" if active else "Set not applied"
                tk.Label(card, text=f"Current: {current}   Next game launch: {'ON' if identifier in self.engine.desired else 'OFF'}", anchor="w", bg=BG_CARD, fg=FG_DIM).pack(fill="x")
                set_summary = activation_set_summary(entry, self.engine.entries)
                if set_summary:
                    tk.Label(card, text=set_summary, anchor="w", justify="left", bg=BG_CARD, fg=FG_DIM,
                             wraplength=max(280, self.root.winfo_width() - 60)).pack(fill="x")
                if self.engine.memory is None:
                    if identifier in self.engine.desired:
                        button = self._button(card, "Cancel auto-on on next game launch", lambda i=identifier: self.action(lambda: self.engine.clear_desired(i)))
                    else:
                        button = self._button(card, "Auto-on on next game launch", lambda i=identifier: self.action(lambda: self.engine.request_auto_on(i)))
                    if self.engine.blocked:
                        button.configure(state="disabled")
                else:
                    if master:
                        label = "Clear set" if active else "Apply set"
                    else:
                        label = "ON" if active else "OFF"
                    bg_color = ON_BG if active else OFF_BG
                    fg_color = ON_FG if active else OFF_FG
                    button = self._button(card, label, lambda i=identifier: self.action(lambda i=i: self._toggle_with_sound(i)),
                                          bg=bg_color, fg=fg_color,
                                          activebackground=BG_BUTTON_ACTIVE, activeforeground=FG)
                    if not self.engine.connected:
                        button.configure(state="disabled")
                button.pack(fill="x")
            else:
                staged_pending = staged_card_state(entry, self.engine.applied) == STAGED_PENDING
                if staged_pending:
                    providers = ", ".join(staged_provider_labels(entry))
                    tk.Label(card, text="Pending - unlocks when active: " + (providers or "unknown provider"),
                             anchor="w", justify="left", bg=BG_CARD, fg=FG_DIM,
                             wraplength=max(280, self.root.winfo_width() - 60)).pack(fill="x")
                current = tk.Label(card, text="Current: unavailable" + (" - provider inactive" if staged_pending else ""),
                                   anchor="w", bg=BG_CARD, fg=FG_DIM)
                current.pack(fill="x")
                self.current_labels[identifier] = current
                row = tk.Frame(card, bg=BG_CARD)
                row.pack(fill="x")
                dropdown = entry.get("dropdown") or {}
                choices = dropdown.get("choices", [])
                if choices:
                    editor = ttk.Combobox(row, textvariable=self.drafts[identifier], values=[choice["value"] for choice in choices],
                                          state="readonly" if dropdown.get("read_only") else "normal", font=("Segoe UI", 16), width=10)
                else:
                    editor = tk.Entry(row, textvariable=self.drafts[identifier], font=("Segoe UI", 16), width=10,
                                      bg=BG, fg=FG, insertbackground=FG)
                editor.pack(side="left", fill="both", expand=True, padx=(0, 4))
                button = self._button(row, "Apply", lambda i=identifier: self.action(lambda: self.engine.set_value(i, self.drafts[i].get())), width=6)
                button.pack(side="left")
                frozen = identifier in self.engine.frozen
                freeze = self._button(row, "Unfreeze" if frozen else "Freeze", lambda i=identifier, f=frozen: self.action(lambda: self.engine.set_freeze(i, not f)), width=7)
                freeze.pack(side="left", padx=(4, 0))
                if staged_pending or not self.engine.connected:
                    button.configure(state="disabled")
                    freeze.configure(state="disabled")
                draft_row = tk.Frame(card, bg=BG_CARD)
                draft_row.pack(fill="x", pady=(4, 0))
                for label, callback in (("▲", lambda e=entry: self.step(e, 1)), ("▼", lambda e=entry: self.step(e, -1)),
                                        ("Reset", lambda i=identifier, e=entry: self.drafts[i].set(str(e.get("value_default") or e.get("default_value") or "")))):
                    if label in {'▲','▼'} and entry.get('value_profile',{}).get('kind')=='string':continue
                    draft_button = self._button(draft_row, label, callback)
                    if staged_pending:
                        draft_button.configure(state="disabled")
                    draft_button.pack(side="left", fill="x", expand=True)

    def poll(self):
        if self.engine.closed:
            return
        before = (self.engine.connected, self.engine.blocked, tuple(self.engine.applied), tuple(self.engine.desired))
        self.engine.poll()
        self.status_text.set(self.engine.status)
        after = (self.engine.connected, self.engine.blocked, tuple(self.engine.applied), tuple(self.engine.desired))
        if before != after:
            self.render()
        for identifier, label in self.current_labels.items():
            try:
                value = self.engine.read_value(identifier)
                label.configure(text=f"Current: {value}   {'FROZEN' if identifier in self.engine.frozen else ''}")
            except Exception:
                entry = self.engine.entries.get(identifier) or {}
                if entry.get("staged") and staged_card_state(entry, self.engine.applied) == STAGED_PENDING:
                    label.configure(text="Current: unavailable — provider inactive")
                else:
                    label.configure(text="Current: unavailable — enable required symbols first")
        self.root.after(250, self.poll)

    def close(self):
        clean = self.engine.close()
        if not clean:
            messagebox.showwarning("Cleanup needs attention", self.engine.status + "\n\nThe state and session journals were preserved. Restart the target before manual recovery.", parent=self.root)
        self.root.destroy()


def run_trainer(plan: dict | str | Path) -> int:
    """Run from an embedded plan dictionary or a UTF-8 JSON plan file."""
    if not isinstance(plan, dict):
        plan = json.loads(Path(plan).read_text(encoding="utf-8"))
    root = tk.Tk()
    root.withdraw()
    try:
        icon = window_icon_path("trainer")
        if icon.is_file():
            root.iconbitmap(str(icon))
    except tk.TclError:
        pass
    engine: TrainerEngine | None = None
    stale: StaleStateRecoverable | None = None
    artifacts: StaleArtifactsRecoverable | None = None
    live: LiveStateConflict | None = None
    attempt = 0
    while engine is None:
        attempt += 1
        if attempt > 4:
            messagebox.showerror("CT2Trainer cannot start",
                                 "Startup recovery did not converge within four attempts. "
                                 "Delete the state folder to start fresh.",
                                 parent=root)
            root.destroy()
            return 1
        stale = artifacts = live = None
        try:
            engine = TrainerEngine(plan)
        except StaleStateRecoverable as exc:
            stale = exc
        except StaleArtifactsRecoverable as exc:
            artifacts = exc
        except LiveStateConflict as exc:
            live = exc
        except Exception as exc:
            try:
                from .debug_log import create_debug_log
                create_debug_log(plan).error("trainer-startup-failed", exc)
            except Exception:
                pass
            messagebox.showerror("CT2Trainer cannot start", str(exc), parent=root)
            root.destroy()
            return 1
        if stale is not None:
            prompt = messagebox.askyesno(
                "CT2Trainer - stale state",
                ("The previous session of this trainer did not shut down cleanly and left a state lock behind.\n"
                 "The previous trainer process has been verified as terminated.\n\n"
                 "Recovering archives the old state byte-for-byte to\n"
                 + str(stale.archive_directory) + "\n"
                 "and releases the lock, so the trainer can start normally.\n\n"
                 "Recover and start?"),
                parent=root)
            if prompt:
                ok, detail = perform_stale_recovery(stale)
                if not ok:
                    messagebox.showerror(
                        "CT2Trainer - recovery failed",
                        (detail + "\n\nThe old state was left untouched at\n" + str(stale.state_directory) +
                         "\nDelete that folder to start fresh."),
                        parent=root)
                    root.destroy()
                    return 1
                messagebox.showinfo("CT2Trainer - stale state recovered",
                                    detail + "\n\nArchives are stored in " + str(stale.archive_directory),
                                    parent=root)
            else:
                messagebox.showinfo(
                    "CT2Trainer - stale state",
                    ("The old state was left untouched at\n" + str(stale.state_directory) +
                     "\nDelete that folder if you want to start fresh."),
                    parent=root)
                root.destroy()
                return 1
        if artifacts is not None:
            fence_note = ""
            if (artifacts.state_directory / "recovery.lock").exists():
                fence_note = ("A recovery fence left by an interrupted recovery attempt is also part of "
                              "the stale artifacts; its owner process was verified as terminated as well.\n")
            prompt = messagebox.askyesno(
                "CT2Trainer - previous session incomplete",
                ("The previous session of this trainer left unfinished receipts behind.\n"
                 + fence_note +
                 "The recorded target and trainer processes have been verified as terminated.\n\n"
                 "Recovering archives the unfinished receipts byte-for-byte to\n"
                 + str(artifacts.archive_directory) + "\n"
                 "and releases them, so the trainer can start normally.\n\n"
                 "Recover and start?"),
                parent=root)
            if prompt:
                ok, detail = perform_stale_recovery(artifacts)
                if not ok:
                    messagebox.showerror(
                        "CT2Trainer - recovery failed",
                        (detail + "\n\nThe old state was left untouched at\n" + str(artifacts.state_directory) +
                         "\nDelete that folder to start fresh."),
                        parent=root)
                    root.destroy()
                    return 1
                messagebox.showinfo("CT2Trainer - receipts recovered",
                                    detail + "\n\nArchives are stored in " + str(artifacts.archive_directory),
                                    parent=root)
            else:
                messagebox.showinfo(
                    "CT2Trainer - receipts left untouched",
                    ("The unfinished receipts were left untouched at\n" + str(artifacts.state_directory) +
                     "\nDelete that folder if you want to start fresh."),
                    parent=root)
                root.destroy()
                return 1
        if live is not None:
            if live.owner_created is None:
                messagebox.showinfo(
                    "CT2Trainer - live session conflict",
                    ("Another trainer session (PID " + str(live.owner_pid) + ") still uses this state, "
                     "but its exact creation identity is unknown.\n"
                     "Close the other trainer manually and start this one again."),
                    parent=root)
                root.destroy()
                return 1
            prompt = messagebox.askyesno(
                "CT2Trainer - live session conflict",
                ("Another trainer session (PID " + str(live.owner_pid) + ") still uses this state.\n"
                 "It has been verified as the exact recorded owner process.\n\n"
                 "Terminate that session and take over? Its unsaved work is lost; "
                 "the state files are preserved."),
                parent=root)
            if prompt:
                ok, detail = terminate_live_session(live.owner_pid, live.owner_created)
                if not ok:
                    messagebox.showerror(
                        "CT2Trainer - takeover failed",
                        detail + "\n\nClose the other trainer manually and start again.",
                        parent=root)
                    root.destroy()
                    return 1
                messagebox.showinfo("CT2Trainer - session terminated",
                                    detail + "\n\nThe state was left untouched; the next start "
                                    "offers the verified stale-state recovery.",
                                    parent=root)
            else:
                messagebox.showinfo(
                    "CT2Trainer - live session left running",
                    "The live session was left running. Close it manually and start this trainer again.",
                    parent=root)
                root.destroy()
                return 1
    TrainerWindow(root, engine)
    root.deiconify()
    root.mainloop()
    return 0 if not engine.blocked else 1
