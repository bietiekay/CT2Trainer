"""Touch-first canvas renderer for the trainer row grid (WP-58).

Implements the compact row grid from ``documentation/trainer-ui-design.md``:
one 64 px switch row, one 72/120 px value row and 48 px group section
header per record, drawn on a single ``tk.Canvas`` instead of the old
per-record cards.  The pure row model (row kinds, states, truncation, hit
rectangles, page slicing) lives in ``ui_rows``; the window/chrome contract
(row heights, touch minimum, ``layout_violations``) lives in
``ui_layout``.  This module renders that model and forwards tap,
long-press, drag and key input to the unchanged engine contract.  The
row context menu (right-click or long-press) offers the combined row
details window (raw script + assessment + actions used, 0.18), the
script preview, a copy of the script text and the unchanged Info
dialog; the pure text builders live in ``ui_script_view``.

Deliberately unchanged by the redesign: the trainer tick sounds
(``trainer_sounds``: clean-room ~28 ms 8-bit ticks for a confirmed on /
off toggle plus an attach-success tick, Win32 winmm memory playback,
best-effort, never raises), the amber banner strings (hotkey
conflict, table-Lua bootstrap), the Info dialog content, the startup
recovery dialogs in ``run_trainer`` and the dark high-contrast palette
(constants extended for the row accents, not replaced).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk
from typing import Callable

from .engine import (TrainerEngine, NativeRuntimeError, StateError,
                     parse_value, format_value,
                     StaleStateRecoverable, StaleArtifactsRecoverable,
                     perform_stale_recovery,
                     LiveStateConflict, terminate_live_session)
from .about_ui import repo_link, trainer_title
from .architecture import plan_architecture
from .window_icon import window_icon_path
from .ui_layout import (NARROW_THRESHOLD, VIEWS, STAGED_PENDING, BANNER_HEIGHT,
                        CHROME_HEADER, CHROME_FILTER, CHROME_FILTER_GRID,
                        CHROME_PAGINATION, CHROME_SEARCH, CHROME_STATUS,
                        MIN_WINDOW_WIDTH,
                        address_provider_marker, activation_set_summary,
                        hotkey_binding_line, hotkey_conflict_banner,
                        initial_window_size, min_window_size, staged_card_state)
from .ui_rows import (ACCENT_BAR_WIDTH, ACCENT_ERROR, ACCENT_OFF, ACCENT_ON,
                      BADGE_FROZEN, GROUP_TOGGLE_H, GROUP_TOGGLE_W, INFO_CHIP,
                      LABEL_GAP_AFTER_PILL, PILL_GAP_AFTER_BAR, PILL_H, PILL_W,
                      ROW_HEIGHT_SECTION, SECTION_CHEVRON_W, SECTION_NAME_GAP,
                      STATE_BLOCKED, STATE_ON, STATE_STAGED, TEXT_DIM,
                      RowSnapshot, build_grid, build_rows, column_layout,
                      effective_columns, find_row, slice_pages,
                      try_again_available)
from .ui_script_view import entry_assessment, row_details, script_preview
from .trainer_sounds import play_sound


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
BANNER_BG = "#3a2f14"
BANNER_FG = "#ffd977"

# Trainer tick sounds (2026-11-01, clean-room): in the character of the
# original native trainer generator's built-in Activate/Deactivate
# ticks, a confirmed manual on/off toggle of an item plays the high /
# lower tick, and a confirmed (re-)attach plays the distinct
# attach-success tick.  Synthesis, caching and best-effort Win32 winmm
# memory playback live in ``trainer_sounds``; playback never raises.


# Touch input and transient-reaction timing (D6/D8 of the design doc).
DRAG_THRESHOLD_PX = 80   # B1-Motion drag distance that pages the row list
LONGPRESS_MS = 400       # press duration that opens the row context menu
PULSE_MS = 300           # row pulse after a successful toggle / value write
CONFIRM_MS = 2000        # transient "OK" chip duration
POLL_MS = 250            # engine poll cadence (unchanged)


class TrainerWindow:
    """Canvas renderer over the pure row model; forwards input to the engine."""

    def __init__(self, root: tk.Tk, engine: TrainerEngine,
                 master_back: Callable[[], None] | None = None,
                 detach_cb: Callable[[], None] | None = None,
                 columns: int = 1,
                 on_columns_changed: Callable[[int], None] | None = None):
        self.root, self.engine = root, engine
        # MT-4 (Master Trainer): optional "back to the Master wait mode"
        # callback.  None keeps the standalone trainer exactly as before
        # (no extra header button); the Master Trainer passes its handler.
        self.master_back = master_back
        # MT-12 (Master Trainer, 0.25): optional detach/attach handler.  The
        # Master passes its handler; None keeps the standalone trainer
        # header byte-identical.  The button reads "Detach" while the
        # engine is attached and "Attach" while detached (the poll tick
        # keeps the label in sync).
        self.detach_cb = detach_cb
        self.detach_btn: tk.Button | None = None
        # MT-21 (Master Trainer, 0.36): the trainer grid column count
        # (1 / 2 / 3) and the optional persistence callback.  The Master
        # passes both (persisted preference + the header cycle control);
        # the standalone trainer keeps the single-column layout and no
        # column control in its header.
        if type(columns) is not int or columns not in (1, 2, 3):
            raise ValueError("grid columns must be 1, 2 or 3 (got "
                             + repr(columns) + ")")
        self.columns = columns
        self.on_columns_changed = on_columns_changed
        self.columns_btn: tk.Button | None = None
        self.view = "Switches"
        self.page = 0
        self.drafts = {i: tk.StringVar(value=str(entry.get("value_default") or entry.get("default_value") or ""))
                       for i, entry in engine.entries.items() if entry["kind"] == "value"}
        # Row-grid interaction state (the pure model mirrors it per render).
        self.expanded_values: frozenset = frozenset()
        self.collapsed_sections: frozenset = frozenset()
        self._value_applied: set = set()      # ids written successfully this session
        self._pulsing: set = set()            # transient 300 ms pulse rows
        self._confirmed: set = set()          # transient 2 s "OK" chip rows
        self._value_texts: dict = {}          # id -> current display text
        self._rows: list = []
        self._pages: list = []
        # MT-21 (0.36): per-column row-grid state (a single column for
        # the standalone trainer): every column's full row list, the
        # column x offsets / widths of the last render, and the first
        # row y of each column's current page (the render offset).
        self._col_rows: list = []
        self._col_xs: list = []
        self._col_ws: list = []
        self._page_offsets: list = []
        self._embedded: list = []             # widgets embedded in the canvas
        self._drag_anchor: int | None = None
        self._longpress_job: int | None = None
        self._press_xy: tuple[int, int] | None = None  # last press, screen coords
        self._status_text = tk.StringVar(value=engine.status)
        self._search_text = tk.StringVar()
        self._page_text = tk.StringVar()
        root.title(trainer_title(engine.plan["title"]))
        width, height = initial_window_size(root.winfo_screenwidth(), root.winfo_screenheight())
        root.geometry(f"{width}x{height}")
        root.minsize(*min_window_size(width))
        root.option_add("*Font", ("Segoe UI", 12))
        root.configure(bg=BG)
        self._build_header()
        self._build_filters()
        self._build_status_and_banners()
        self._build_pagination()
        self.canvas = tk.Canvas(root, bg=BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind("<Prior>", lambda event: self.move_page(-1))
        root.bind("<Next>", lambda event: self.move_page(1))
        root.bind("<MouseWheel>", lambda event: self.move_page(-1 if event.delta > 0 else 1))
        root.bind("<Escape>", self.on_escape)
        root.bind("<Configure>", self.on_resize)
        self.canvas.bind("<Configure>", self.on_resize)
        self.canvas.bind("<Button-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Button-3>", self.on_context)
        self.render()
        self._update_banners()
        root.after(POLL_MS, self.poll)

    @staticmethod
    def _button(parent, label, action, **kwargs):
        style = {"bg": BG_BUTTON, "fg": FG, "activebackground": BG_BUTTON_ACTIVE,
                 "activeforeground": FG, "disabledforeground": FG_DIM,
                 "font": ("Segoe UI", 12), "height": 2, "pady": 4}
        style.update(kwargs)
        return tk.Button(parent, text=label, command=action, **style)

    # -- chrome rows (D7) ----------------------------------------------------

    def _build_header(self):
        self.header = tk.Frame(self.root, bg=BG_HEADER, height=CHROME_HEADER, padx=12)
        self.header.pack(fill="x")
        self.header.pack_propagate(False)
        tk.Label(self.header, text=self.engine.plan["title"], bg=BG_HEADER, fg=FG,
                 font=("Segoe UI", 13, "bold"), anchor="w").pack(side="left", fill="x", expand=True)
        self._button(self.header, "Close", self.close,
                     bg=BG_CLOSE, activebackground=BG_CLOSE_ACTIVE).pack(side="right")
        # MT-4 (Master Trainer): the extra "back to the Master" control only
        # exists when the Master passed its callback; the standalone trainer
        # header is byte-identical to before.
        if self.master_back is not None:
            self._button(self.header, "⬅ Master", self.master_back,
                         width=10).pack(side="right", padx=(0, 8))
        repo_link(self.header, bg=BG_HEADER, fg=FG).pack(side="right")
        self.conn_dot = tk.Label(self.header, text="●", bg=BG_HEADER, fg=FG_DIM,
                                 font=("Segoe UI", 11))
        self.conn_dot.pack(side="right", padx=(12, 2))
        self.conn_label = tk.Label(self.header, bg=BG_HEADER, fg=FG_DIM,
                                   font=("Segoe UI", 11))
        self.conn_label.pack(side="right")
        self._button(self.header, "Status / help", self.show_status,
                     width=12).pack(side="right")
        # Bounded re-arm (0.21): explicit re-attach action.  Detaches the
        # current target through the engine teardown and re-enters the
        # normal waiting attach cycle (fresh game process, fresh re-arm
        # budget) without restarting the trainer.
        self._button(self.header, "Re-attach", self.on_reattach,
                     width=10).pack(side="right")
        # MT-12 (Master Trainer, 0.25): explicit detach/attach control.
        # Present only when the Master passes its handler; the standalone
        # trainer header stays byte-identical.  The label mirrors the
        # attach state ("Detach" attached / "Attach" detached) and the
        # poll tick keeps it in sync.
        if self.detach_cb is not None:
            self.detach_btn = self._button(self.header, "Detach",
                                           self.detach_cb, width=10)
            self.detach_btn.pack(side="right")
        # MT-21 (Master Trainer, 0.36): the grid column count cycle
        # control ("Columns: 1/2/3").  Present only when the Master
        # passes its handler; the standalone trainer header stays
        # byte-identical.  The label mirrors the requested column count;
        # narrow windows render fewer columns than requested
        # (ui_rows.effective_columns).
        if self.on_columns_changed is not None:
            self.columns_btn = self._button(
                self.header, "Columns: " + str(self.columns),
                self._cycle_columns, width=11)
            self.columns_btn.pack(side="right")

    def _chip(self, parent, name):
        return self._button(parent, name, lambda: self.set_view(name),
                            width=9, height=2, font=("Segoe UI", 11))

    def _build_filters(self):
        # Wide mode: the six chips and the inline search share one 48 px row.
        self.filter_wide = tk.Frame(self.root, bg=BG, height=CHROME_FILTER, padx=8)
        self.filter_wide.pack(fill="x")
        self.filter_wide.pack_propagate(False)
        self._chips_wide = [self._chip(self.filter_wide, name) for name in VIEWS]
        for chip in self._chips_wide:
            chip.pack(side="left", padx=2)
        tk.Entry(self.filter_wide, textvariable=self._search_text,
                 font=("Segoe UI", 12), bg=BG_CARD, fg=FG, insertbackground=FG,
                 relief="solid", bd=1).pack(side="left", fill="x", expand=True,
                                            padx=(8, 0), ipady=8)
        # Narrow mode (< 650 px): 2x3 chip grid, search on its own row.
        self.filter_narrow = tk.Frame(self.root, bg=BG, height=CHROME_FILTER_GRID, padx=8)
        self.filter_narrow.pack(fill="x")
        self.filter_narrow.pack_propagate(False)
        self._chips_narrow = []
        for index, name in enumerate(VIEWS):
            chip = self._chip(self.filter_narrow, name)
            chip.grid(row=index // 2, column=index % 2, sticky="ew", padx=3, pady=2)
            self._chips_narrow.append(chip)
        self.filter_narrow.columnconfigure(0, weight=1)
        self.filter_narrow.columnconfigure(1, weight=1)
        self.search_row = tk.Frame(self.root, bg=BG, height=CHROME_SEARCH, padx=8)
        self.search_row.pack(fill="x")
        self.search_row.pack_propagate(False)
        tk.Label(self.search_row, text="Search", bg=BG, fg=FG_DIM).pack(side="left", padx=(0, 8))
        tk.Entry(self.search_row, textvariable=self._search_text,
                 font=("Segoe UI", 12), bg=BG_CARD, fg=FG, insertbackground=FG,
                 relief="solid", bd=1).pack(side="left", fill="both", expand=True)
        self._search_text.trace_add("write", self._search_changed)
        self._apply_filter_mode()

    def _apply_filter_mode(self):
        if self.root.winfo_width() >= NARROW_THRESHOLD:
            self.filter_wide.pack(fill="x", after=self.header)
            self.filter_narrow.pack_forget()
            self.search_row.pack_forget()
        else:
            self.filter_wide.pack_forget()
            self.filter_narrow.pack(fill="x", after=self.header)
            self.search_row.pack(fill="x", after=self.filter_narrow)

    def _build_status_and_banners(self):
        self.status_frame = tk.Frame(self.root, bg=BG, height=CHROME_STATUS, padx=12)
        self.status_frame.pack(fill="x")
        self.status_frame.pack_propagate(False)
        tk.Label(self.status_frame, textvariable=self._status_text, anchor="w",
                 justify="left", wraplength=900, bg=BG, fg=FG,
                 font=("Segoe UI", 11)).pack(side="left", fill="x", expand=True)
        # WP-41: table-Lua bootstrap banner (exact contract string, amber strip).
        self.table_lua_strip = tk.Frame(self.root, bg=BANNER_BG, height=BANNER_HEIGHT)
        self.table_lua_strip.pack(fill="x")
        self.table_lua_strip.pack_propagate(False)
        self.table_lua_banner = tk.Label(self.table_lua_strip, text="", anchor="w",
                                         justify="left", bg=BANNER_BG, fg=BANNER_FG,
                                         font=("Segoe UI", 11), padx=12)
        self.table_lua_banner.pack(fill="both")
        # WP-40: trainer-wide hotkey conflict banner (same string as before).
        self.hotkey_strip = tk.Frame(self.root, bg=BANNER_BG, height=BANNER_HEIGHT)
        self.hotkey_strip.pack(fill="x")
        self.hotkey_strip.pack_propagate(False)
        self.hotkey_banner = tk.Label(self.hotkey_strip, text="", anchor="w",
                                      justify="left", bg=BANNER_BG, fg=BANNER_FG,
                                      font=("Segoe UI", 11), padx=12)
        self.hotkey_banner.pack(fill="both")

    def _build_pagination(self):
        self.pagination = tk.Frame(self.root, bg=BG, height=CHROME_PAGINATION, padx=12)
        self.pagination.pack(fill="x")
        self.pagination.pack_propagate(False)
        tk.Label(self.pagination, textvariable=self._page_text, bg=BG, fg=FG_DIM,
                 font=("Segoe UI", 11)).pack(side="left")
        self._button(self.pagination, "Next ▶", lambda: self.move_page(1),
                     width=5).pack(side="right")
        self._button(self.pagination, "◀ Previous", lambda: self.move_page(-1),
                     width=5).pack(side="right", padx=(0, 4))
        self._button(self.pagination, "⤒", self.go_top,
                     width=3).pack(side="right", padx=(0, 4))

    # -- view / search / page controls ----------------------------------------

    def _search_changed(self, *_):
        self.page = 0
        self.render()

    def set_view(self, name):
        self.view = name
        self.page = 0
        self.render()

    def move_page(self, delta):
        if not self._pages:
            return
        self.page = min(len(self._pages) - 1, max(0, self.page + delta))
        self.render()

    def go_top(self):
        self.page = 0
        self.render()

    def _cycle_columns(self):
        """MT-21 (0.36): cycle the trainer grid 1 -> 2 -> 3 -> 1.

        The requested count is handed to the Master persistence
        callback (if any) and the view re-renders immediately.  A
        window too narrow for the request renders fewer columns
        (effective_columns) while the label keeps showing the
        requested mode.
        """
        next_columns = self.columns % 3 + 1
        self.columns = next_columns
        if self.columns_btn is not None:
            self.columns_btn.configure(text="Columns: " + str(next_columns))
        if self.on_columns_changed is not None:
            self.on_columns_changed(next_columns)
        self.render()

    # -- engine state snapshot for the pure row model -------------------------

    def _snapshot(self) -> RowSnapshot:
        parent_active = set()
        for entry in self.engine.entries.values():
            if entry.get("parent_activation") is not None:
                try:
                    if self.engine.parent_query(entry["id"])["active"]:
                        parent_active.add(entry["id"])
                except Exception:
                    # No parent policy yet (pre-attach / refused query): the
                    # section renders inactive; the engine is the authority.
                    pass
        return RowSnapshot(
            applied=frozenset(self.engine.applied),
            desired=frozenset(self.engine.desired),
            frozen=frozenset(self.engine.frozen),
            errors=dict(self.engine.entry_errors),
            value_applied=frozenset(self._value_applied),
            parent_active=frozenset(parent_active),
            pulsing=frozenset(self._pulsing),
            confirmed=frozenset(self._confirmed),
            disconnected=self.engine.memory is None,
            enable_failed=dict(self.engine.enable_failures),
            rearm={identifier: dict(state)
                   for identifier, state in self.engine.rearm.items()},
        )

    # -- rendering -------------------------------------------------------------

    def _mark_chips(self):
        for chips in (self._chips_wide, self._chips_narrow):
            for name, chip in zip(VIEWS, chips):
                if name == self.view:
                    chip.configure(bg=BG_BUTTON_ACTIVE, activebackground=BG_BUTTON,
                                   relief="sunken")
                else:
                    chip.configure(bg=BG_BUTTON, activebackground=BG_BUTTON_ACTIVE,
                                   relief="raised")

    def render(self):
        # MT-4 (Master Trainer): a pending pulse/confirm after-callback can
        # outlive the trainer view when the Master destroys the trainer
        # widgets and rebuilds the waiting view on the same root; a
        # destroyed canvas is skipped instead of raising out of mainloop.
        try:
            canvas_alive = self.canvas.winfo_exists()
        except tk.TclError:
            return
        if not canvas_alive:
            return
        for widget in self._embedded:
            widget.destroy()
        self._embedded = []
        self.canvas.delete("all")
        width = self.canvas.winfo_width()
        if width < 320:
            width = 320
        area = self.canvas.winfo_height()
        snapshot = self._snapshot()
        # MT-21 (0.36): the multi-column trainer grid.  ``self.columns``
        # is the persisted (requested) count; a narrow window renders
        # fewer columns than requested (effective_columns).  With one
        # column the whole pipeline is byte-stable against the
        # pre-0.36 single-column renderer.
        columns = effective_columns(width, self.columns)
        col_ws, col_xs = column_layout(width, columns)
        grid = build_grid(self.engine.entries, self.view,
                          self._search_text.get(), snapshot, width,
                          columns=columns,
                          expanded_values=self.expanded_values,
                          collapsed_sections=self.collapsed_sections,
                          values=self._value_texts)
        self._col_rows = grid
        self._col_ws = list(col_ws)
        self._col_xs = list(col_xs)
        # Per-column paging (the existing slice_pages floor rule); the
        # page count is the max across the columns - shorter columns
        # draw nothing on the later pages.
        col_pages = [slice_pages(col_rows, area) for col_rows in grid]
        n_pages = max((len(pages) for pages in col_pages), default=0)
        self._pages = [
            [col_pages[c][p] if p < len(col_pages[c]) else []
             for c in range(len(col_pages))]
            for p in range(n_pages)
        ]
        self._rows = [row for col_rows in grid for row in col_rows]
        self._mark_chips()
        if not self._rows:
            self._page_offsets = []
            self.page = 0
            self._page_text.set("Page 1 / 1")
            self.canvas.create_text(width / 2, 24,
                                    text="No entries match this view or search.",
                                    fill=FG_DIM, font=("Segoe UI", 12))
            return
        if self.page >= len(self._pages):
            self.page = len(self._pages) - 1
        self.page = max(0, self.page)
        visible = self._pages[self.page]
        self._page_offsets = [rows[0].y if rows else 0 for rows in visible]
        for col_rows, offset in zip(visible, self._page_offsets):
            for row in col_rows:
                self._draw_row(row, offset)
        self._page_text.set(f"Page {self.page + 1} / {len(self._pages)}")

    def _draw_row(self, row, offset):
        # MT-21 (0.36): right-anchored positions are derived from the
        # row's hit rectangle (the column x offset is baked in) instead
        # of the canvas width, so multi-column grids render correctly;
        # for the single column (x0 = 0, w = canvas width) this is
        # byte-identical to the pre-0.36 renderer.
        canvas = self.canvas
        x0, w = row.hit.x, row.hit.w
        canvas.create_rectangle(x0, row.y - offset, x0 + w, row.y + row.height - offset,
                                fill=row.tint, outline="")
        canvas.create_rectangle(x0, row.y - offset, x0 + ACCENT_BAR_WIDTH,
                                row.y + row.height - offset, fill=row.accent, outline="")
        if row.kind == "section":
            self._draw_section(row, offset)
        elif row.kind == "switch":
            self._draw_switch(row, offset)
        else:
            self._draw_value(row, offset)
        if row.chip:
            canvas.create_text(x0 + w - 44, row.y + row.height / 2 - offset,
                               anchor="e", text=row.chip, fill=TEXT_DIM,
                               font=("Segoe UI", 11))
        if row.error_dot:
            canvas.create_oval(x0 + w - 36, row.y + 16 - offset, x0 + w - 28,
                               row.y + 24 - offset, fill=ACCENT_ERROR, outline="")
        if row.info_hit is not None:
            self._draw_info_chip(row.info_hit.x, row.info_hit.y - offset)
        if row.confirmed:
            canvas.create_text(x0 + w - 10, row.y + 8 - offset, anchor="ne",
                               text="OK", fill=ACCENT_ON,
                               font=("Segoe UI", 11, "bold"))

    def _draw_info_chip(self, x, y):
        canvas = self.canvas
        canvas.create_oval(x, y, x + INFO_CHIP, y + INFO_CHIP, outline=TEXT_DIM)
        canvas.create_text(x + INFO_CHIP / 2, y + INFO_CHIP / 2, text="i",
                           fill=TEXT_DIM, font=("Segoe UI", 9, "bold"))

    def _draw_switch(self, row, offset):
        canvas = self.canvas
        if row.pill is not None:
            track = row.pill
            track_y = track.y - offset
            canvas.create_rectangle(track.x, track_y, track.x + PILL_W,
                                    track_y + PILL_H,
                                    fill=ACCENT_ON if row.pill_on else ACCENT_OFF,
                                    outline="")
            knob = PILL_H - 8
            knob_x = track.x + 4 if not row.pill_on else track.x + PILL_W - knob - 4
            canvas.create_oval(knob_x, track_y + 4, knob_x + knob, track_y + knob + 4,
                               fill=FG if row.pill_on else FG_DIM, outline="")
        label_x = row.hit.x + ACCENT_BAR_WIDTH + PILL_GAP_AFTER_BAR + PILL_W + LABEL_GAP_AFTER_PILL + row.indent
        canvas.create_text(label_x, row.y + 18 - offset, anchor="w", text=row.label,
                           fill=FG, font=("Segoe UI", 12))
        if row.sublabel:
            canvas.create_text(label_x, row.y + 38 - offset, anchor="w",
                               text=row.sublabel, fill=TEXT_DIM, font=("Segoe UI", 11))

    def _draw_value(self, row, offset):
        canvas = self.canvas
        label_x = row.hit.x + ACCENT_BAR_WIDTH + PILL_GAP_AFTER_BAR + row.indent
        canvas.create_text(label_x, row.y + 18 - offset, anchor="w", text=row.label,
                           fill=FG, font=("Segoe UI", 12))
        if row.sublabel:
            canvas.create_text(label_x, row.y + 40 - offset, anchor="w",
                               text=row.sublabel, fill=TEXT_DIM, font=("Segoe UI", 11))
        if row.expanded:
            self._draw_value_line(row, offset, expanded=True)
            self._draw_editor(row, offset)
        else:
            self._draw_value_line(row, offset, expanded=False)

    def _draw_value_line(self, row, offset, expanded: bool):
        canvas = self.canvas
        right = row.hit.x + row.hit.w
        canvas.create_text(right - 8, row.y + (18 if expanded else 22) - offset,
                           anchor="e", text=row.value_text,
                           fill=TEXT_DIM if expanded else FG, font=("Consolas", 12))
        if row.frozen_badge:
            badge_y = row.y + (12 if expanded else 34) - offset
            canvas.create_rectangle(right - 8 - 14, badge_y, right - 8 - 4,
                                    badge_y + 10, fill=BADGE_FROZEN, outline="")

    def _draw_editor(self, row, offset):
        canvas = self.canvas
        entry = self.engine.entries[row.entry_id]
        editor = row.editor
        disabled = row.state in (STATE_STAGED, STATE_BLOCKED) or self.engine.memory is None

        def rect(rect_):
            return (rect_.x, rect_.y - offset, rect_.w, rect_.h)

        x, y, w, h = rect(editor.input)
        dropdown = entry.get("dropdown") or {}
        choices = dropdown.get("choices", [])
        if choices:
            widget = ttk.Combobox(canvas, textvariable=self.drafts[row.entry_id],
                                  values=[choice["value"] for choice in choices],
                                  state="disabled" if disabled
                                  else ("readonly" if dropdown.get("read_only") else "normal"),
                                  font=("Segoe UI", 12))
        else:
            widget = tk.Entry(canvas, textvariable=self.drafts[row.entry_id],
                              font=("Consolas", 12), bg=BG, fg=FG,
                              insertbackground=FG, relief="solid", bd=1,
                              state="disabled" if disabled else "normal")
        canvas.create_window(x, y, window=widget, width=w, height=h, anchor="nw")
        self._embedded.append(widget)
        frozen = row.entry_id in self.engine.frozen
        for label, rect_, callback in (
                ("Apply", editor.apply, lambda: self._apply_value(row.entry_id)),
                ("Unfreeze" if frozen else "Freeze", editor.freeze,
                 lambda: self._value_freeze(row.entry_id)),
                ("+", editor.plus, lambda: self._step_value(row.entry_id, 1)),
                ("−", editor.minus, lambda: self._step_value(row.entry_id, -1)),
                ("Reset", editor.reset,
                 lambda: self._reset_value(row.entry_id)),
        ):
            if label in ("+", "−") and entry.get("value_profile", {}).get("kind") == "string":
                continue
            self._canvas_button(*rect(rect_), label, callback)

    def _canvas_button(self, x, y, w, h, text, callback):
        canvas = self.canvas
        rect = canvas.create_rectangle(x, y, x + w, y + h, fill=BG_BUTTON, outline="")
        label = canvas.create_text(x + w / 2, y + h / 2, text=text, fill=FG,
                                   font=("Segoe UI", 11))
        for item in (rect, label):
            canvas.bind_tag(item, "<Button-1>",
                            lambda event, callback=callback: self.action(callback))

    def _draw_section(self, row, offset):
        canvas = self.canvas
        chevron = row.chevron
        canvas.create_text(chevron.x + chevron.w / 2,
                           chevron.y + chevron.h / 2 - offset,
                           text="▾" if row.expanded else "▸", fill=TEXT_DIM,
                           font=("Segoe UI", 12))
        name_x = row.hit.x + 16 + row.indent + SECTION_CHEVRON_W + SECTION_NAME_GAP
        if row.sublabel:
            canvas.create_text(name_x, row.y + 16 - offset, anchor="w", text=row.label,
                               fill=FG, font=("Segoe UI", 13, "bold"))
            canvas.create_text(name_x, row.y + 34 - offset, anchor="w",
                               text=row.sublabel, fill=TEXT_DIM, font=("Segoe UI", 11))
        else:
            canvas.create_text(name_x, row.y + ROW_HEIGHT_SECTION / 2 - offset, anchor="w",
                               text=row.label, fill=FG, font=("Segoe UI", 13, "bold"))
        counter_x = row.hit.x + row.hit.w - 8 \
            - (GROUP_TOGGLE_W + 8 if row.group_toggle else 0)
        if row.counter:
            canvas.create_text(counter_x, row.y + ROW_HEIGHT_SECTION / 2 - offset,
                               anchor="e", text=row.counter, fill=TEXT_DIM,
                               font=("Segoe UI", 11))
        if row.group_toggle_hit is not None:
            rect = row.group_toggle_hit
            canvas.create_rectangle(rect.x, rect.y - offset,
                                    rect.x + GROUP_TOGGLE_W, rect.y + GROUP_TOGGLE_H - offset,
                                    fill=ACCENT_ON if row.state == STATE_ON else ACCENT_OFF,
                                    outline="")
            knob = 16
            knob_x = rect.x + (GROUP_TOGGLE_W - knob) / 2
            knob_y = rect.y - offset + (GROUP_TOGGLE_H - knob - 4 if row.state == STATE_ON else 4)
            canvas.create_oval(knob_x, knob_y, knob_x + knob, knob_y + knob,
                               fill=FG, outline="")

    # -- touch input (D8): tap, long-press, drag paging -------------------------

    def _column_at(self, x):
        """MT-21 (0.36): the grid column containing row-area x (or None)."""
        for c, cx in enumerate(self._col_xs):
            if cx <= x < cx + self._col_ws[c]:
                return c
        return None

    def _row_at(self, x, y):
        # MT-21 (0.36): pick the column by x, then the row by y inside
        # that column (each column has its own page offset).
        if not self._col_rows:
            return None
        column = self._column_at(x)
        if column is None or not self._col_rows[column]:
            return None
        return find_row(self._col_rows[column], y + self._page_offsets[column])

    def on_press(self, event):
        self._drag_anchor = event.y
        if hasattr(event, "x_root") and hasattr(event, "y_root"):
            self._press_xy = (event.x_root, event.y_root)
        row = self._row_at(event.x, event.y)
        if row is not None:
            self._longpress_job = self.root.after(
                LONGPRESS_MS, lambda: self._longpress(row.entry_id))
        else:
            self._longpress_job = None

    def on_drag(self, event):
        # Any motion cancels the pending long-press (the finger is moving).
        if self._longpress_job is not None:
            self.root.after_cancel(self._longpress_job)
            self._longpress_job = None
        if self._drag_anchor is None:
            self._drag_anchor = event.y
            return
        delta = event.y - self._drag_anchor
        if delta <= -DRAG_THRESHOLD_PX:
            self.move_page(1)
            self._drag_anchor = event.y
        elif delta >= DRAG_THRESHOLD_PX:
            self.move_page(-1)
            self._drag_anchor = event.y

    def _longpress(self, identifier):
        if self._longpress_job is None:
            return
        self._longpress_job = None
        entry = self.engine.entries.get(identifier)
        if entry is not None:
            self._show_context_menu(entry, self._press_xy)

    # -- row context menu (right-click / long-press) -----------------------------

    def on_context(self, event):
        row = self._row_at(event.x, event.y)
        if row is None:
            return
        entry = self.engine.entries.get(row.entry_id)
        if entry is None:
            return
        self._show_context_menu(entry, (event.x_root, event.y_root))

    def _context_menu_items(self, entry):
        """(label, command) pairs of the row context menu, pure enough to
        be unit-tested without a display.  The combined row-details window
        (0.18) leads the menu; the existing single-purpose items stay."""
        items = [("Row details", lambda: self.show_row_details(entry))]
        preview = script_preview(entry)
        if preview is not None:
            items.append(("Script preview",
                          lambda: self.show_script_preview(entry)))
            items.append(("Copy script text",
                          lambda p=preview: self._copy_script_text(p)))
        items.append(("What is happening here",
                      lambda: self.show_assessment(entry)))
        items.append(("Details", lambda: self.info(entry)))
        # Bounded re-arm (0.21): "Try again" is offered for script/code rows
        # whose last enable failed or that are pending a re-arm; the item is
        # disabled when neither condition holds.  It is a 3-tuple carrying
        # the menu state (2-tuples above stay unchanged).
        if entry.get("kind") in ("script", "code_patch"):
            rearm_snapshot = RowSnapshot(
                enable_failed=dict(self.engine.enable_failures),
                rearm={identifier: dict(state)
                       for identifier, state in self.engine.rearm.items()})
            available = try_again_available(rearm_snapshot, entry["id"])
            items.append(("Try again",
                          lambda: self._try_again(entry["id"]),
                          "normal" if available else "disabled"))
        return items

    def _try_again(self, identifier: int):
        # Route through action() so failures land in the status line
        # (touch-friendly, no modal).
        self.action(lambda: self.engine.try_again(identifier))

    def on_reattach(self):
        # Top-level re-attach: engine teardown + waiting poll cycle.
        self.action(lambda: self.engine.reattach())

    def _show_context_menu(self, entry, position):
        if position is None:
            return
        menu = tk.Menu(self.root, tearoff=0)
        for item in self._context_menu_items(entry):
            label, command = item[0], item[1]
            # Bounded re-arm (0.21): "Try again" carries an explicit menu
            # state; existing 2-tuples default to enabled.
            state = item[2] if len(item) > 2 else "normal"
            menu.add_command(label=label, command=command, state=state)
        try:
            menu.tk_popup(int(position[0]), int(position[1]))
        finally:
            menu.grab_release()

    def show_script_preview(self, entry):
        """Read-only dialog with the entry's executable source."""
        preview = script_preview(entry)
        if preview is None:
            return
        title, body = preview
        window = tk.Toplevel(self.root)
        window.title(title)
        window.configure(bg=BG)
        window.geometry("900x620")
        window.transient(self.root)
        text = scrolledtext.ScrolledText(window, font=("Consolas", 10),
                                         bg=BG_CARD, fg=FG, insertbackground=FG,
                                         wrap="none", padx=10, pady=10)
        text.insert("1.0", body)
        text.configure(state="disabled")
        text.pack(fill="both", expand=True)
        self._button(window, "Close", lambda: window.destroy()).pack(
            side="right", padx=10, pady=8)

    def show_assessment(self, entry):
        """Read-only dialog with the plain-language entry assessment."""
        window = tk.Toplevel(self.root)
        window.title(f"Entry assessment - {entry.get('label', '')}")
        window.configure(bg=BG)
        window.geometry("760x520")
        window.transient(self.root)
        text = scrolledtext.ScrolledText(window, font=("Consolas", 10),
                                         bg=BG_CARD, fg=FG, insertbackground=FG,
                                         wrap="word", padx=10, pady=10)
        text.insert("1.0", entry_assessment(entry, self.engine.entries,
                                            self.engine.applied,
                                            self.engine.entry_errors.get(entry["id"])))
        text.configure(state="disabled")
        text.pack(fill="both", expand=True)
        self._button(window, "Close", lambda: window.destroy()).pack(
            side="right", padx=10, pady=8)

    def show_row_details(self, entry):
        """Combined row-details window (0.18): one read-only Toplevel with
        the raw script source, the plain-language assessment (what it does
        / what is known) and the concrete actions the trainer performs for
        the entry.  Content comes from the pure ``row_details`` builder so
        the exact text is unit-tested in tests/test_native_ui_row_details.py.
        """
        details = row_details(entry, self.engine.entries,
                              self.engine.applied,
                              self.engine.entry_errors.get(entry["id"]))
        window = tk.Toplevel(self.root)
        window.title(details["title"])
        window.configure(bg=BG)
        window.geometry("900x700")
        window.transient(self.root)
        outer = tk.Frame(window, bg=BG)
        outer.pack(fill="both", expand=True)

        def section(label, text, mono=True, wrap="none", height=None):
            tk.Label(outer, text=label, bg=BG, fg=FG,
                     font=("Segoe UI", 12, "bold"), anchor="w").pack(
                fill="x", padx=10, pady=(8, 2))
            widget = scrolledtext.ScrolledText(
                outer, font=("Consolas", 10) if mono else ("Segoe UI", 11),
                bg=BG_CARD, fg=FG, insertbackground=FG,
                wrap=wrap, padx=10, pady=6, height=height)
            widget.insert("1.0", text)
            widget.configure(state="disabled")
            widget.pack(fill="both", expand=True)

        if details["script"] is not None:
            # The raw source keeps a fixed share of the window; the two
            # text sections below split the rest.
            section("Script (raw source)", details["script"]["body"],
                    mono=True, wrap="none", height=14)
        else:
            tk.Label(outer,
                     text="Script: no executable source "
                          "(record blocked; see the assessment below)",
                     bg=BG, fg=FG_DIM, font=("Segoe UI", 11),
                     anchor="w").pack(fill="x", padx=10, pady=(8, 2))
        section("What it does / what is known", details["assessment"],
                mono=False, wrap="word")
        section("Actions used",
                details["actions"] or "No direct memory action",
                mono=True, wrap="none")
        self._button(window, "Close", lambda: window.destroy()).pack(
            side="right", padx=10, pady=8)

    def _copy_script_text(self, preview):
        self.clipboard_clear()
        self.clipboard_append(preview[1])
        self._status_text.set("Script text copied to the clipboard.")

    def on_release(self, event):
        was_tap = self._longpress_job is not None
        if was_tap:
            self.root.after_cancel(self._longpress_job)
            self._longpress_job = None
        self._drag_anchor = None
        if was_tap:
            self._tap(event.x, event.y)

    def _tap(self, x, y):
        row = self._row_at(x, y)
        if row is None:
            return
        entry = self.engine.entries.get(row.entry_id)
        if entry is None:
            return
        if row.kind == "section":
            if row.group_toggle_hit is not None and row.group_toggle_hit.contains(x, y):
                self.action(lambda: self._toggle_group(row.entry_id))
            else:
                self._toggle_section(row.entry_id)
        elif row.kind == "switch":
            if row.info_hit is not None and row.info_hit.contains(x, y):
                self.info(entry)
            else:
                self.action(lambda i=row.entry_id: self._toggle(i))
        elif row.kind == "value":
            if row.editor is not None:
                self._tap_editor(row, x, y)
            elif row.info_hit is not None and row.info_hit.contains(x, y):
                self.info(entry)
            else:
                self._open_value_editor(row.entry_id)
        else:  # info row: no actions, only details
            self.info(entry)

    def _tap_editor(self, row, x, y):
        editor = row.editor
        identifier = row.entry_id
        if editor.apply.contains(x, y):
            self.action(lambda: self._apply_value(identifier))
        elif editor.freeze.contains(x, y):
            self.action(lambda: self._value_freeze(identifier))
        elif editor.plus.contains(x, y):
            self.action(lambda: self._step_value(identifier, 1))
        elif editor.minus.contains(x, y):
            self.action(lambda: self._step_value(identifier, -1))
        elif editor.reset.contains(x, y):
            self.action(lambda: self._reset_value(identifier))
        # Taps inside the embedded input widget never reach the canvas;
        # everything else on an expanded value row collapses the editor.
        elif editor.input.contains(x, y):
            return
        else:
            self._toggle_value_editor(identifier)

    # -- row actions -----------------------------------------------------------

    def _toggle(self, identifier):
        if self.engine.memory is None:
            # Pre-attach: the row tap manages the saved auto-on wish.
            if identifier in self.engine.desired:
                self.engine.clear_desired(identifier)
            else:
                self.engine.request_auto_on(identifier)
        else:
            self.engine.toggle(identifier)
            # 2026-11-01 (trainer sounds): a confirmed manual toggle plays the
            # native trainer generator's tick in the character of the original
            # (high on / lower off); a failed toggle stays silent.
            play_sound("on" if identifier in self.engine.applied else "off")
            self._flash(identifier)

    def _toggle_section(self, identifier):
        if identifier in self.collapsed_sections:
            self.collapsed_sections.discard(identifier)
        else:
            self.collapsed_sections.add(identifier)
        self.render()

    def _toggle_group(self, identifier):
        # Flagged group heading: runs the existing parent-activation cascade.
        self.engine.toggle(identifier)
        # 2026-11-01 (trainer sounds): the group toggle is a manual on/off
        # action too, so it plays the same native-trainer tick character.
        play_sound("on" if identifier in self.engine.applied else "off")

    def _toggle_value_editor(self, identifier):
        if identifier in self.expanded_values:
            self.expanded_values = self.expanded_values - {identifier}
        else:
            self.expanded_values = self.expanded_values | {identifier}
        self.render()

    def _open_value_editor(self, identifier):
        """Open (or close) the inline value editor with a staged guard.

        Field fix 2026-10-30 (South of Midnight, staged options): a
        staged-pending value refuses the editor client-side.  The engine
        would name the missing provider at read or write time, but the tap
        surfaces that refusal immediately instead of letting the user type
        into an editor that cannot apply.  Live or non-staged values open
        the editor exactly as before.
        """
        entry = self.engine.entries.get(identifier)
        if (entry is not None
                and staged_card_state(entry, self.engine.applied) == STAGED_PENDING):
            self.action(lambda: self.engine.read_value(identifier))
            return
        self._toggle_value_editor(identifier)

    def _apply_value(self, identifier):
        self.engine.set_value(identifier, self.drafts[identifier].get())
        self._value_applied.add(identifier)
        self._flash(identifier)

    def _value_freeze(self, identifier):
        self.engine.set_freeze(identifier, identifier not in self.engine.frozen)

    def _reset_value(self, identifier):
        entry = self.engine.entries[identifier]
        self.drafts[identifier].set(
            str(entry.get("value_default") or entry.get("default_value") or ""))

    def _step_value(self, identifier, direction):
        entry = self.engine.entries[identifier]
        variable = self.drafts[identifier]
        profile = entry.get("value_profile")
        if profile is not None and profile["kind"] in {"byte_array", "string"}:
            raise NativeRuntimeError("Edit this array as exact hex byte pairs")
        current = bytes(profile["size"]) if profile is not None else None
        literal = variable.get() or "0"
        raw = parse_value(entry, literal, current)
        displayed = format_value(entry, raw)
        if entry["variable_type"] in {"Float", "Double"}:
            candidate = str(float(displayed) + direction)
        elif profile is not None and profile["display"] == "binary":
            candidate = format(max(0, int(displayed, 2) + direction), "b")
        elif entry.get("show_as_hex"):
            candidate = format(max(0, int(displayed, 16) + direction), "X")
        else:
            candidate = str(int(displayed) + direction)
        parse_value(entry, candidate, current)
        variable.set(candidate)

    def _flash(self, identifier):
        first_pulse = identifier not in self._pulsing
        first_confirm = identifier not in self._confirmed
        self._pulsing.add(identifier)
        self._confirmed.add(identifier)
        if first_pulse:
            self.root.after(PULSE_MS, lambda i=identifier: self._end_reaction(i, True))
        if first_confirm:
            self.root.after(CONFIRM_MS, lambda i=identifier: self._end_reaction(i, False))
        self.render()

    def _end_reaction(self, identifier, pulse):
        (self._pulsing if pulse else self._confirmed).discard(identifier)
        self.render()

    def action(self, callback):
        """Run an engine action; expected failures stay inline (no modal).

        NativeRuntimeError: row error accent via engine.entry_errors plus the
        reason in the status line. Unexpected exceptions keep the old modal
        last resort and the debug-log entry.
        """
        error = None
        try:
            callback()
        except NativeRuntimeError as exc:
            error = str(exc)
        except Exception as exc:
            try:
                self.engine.debug_log.error("ui-action-failed", exc,
                                            trainer_id=self.engine.plan.get("trainer_id"))
            except Exception:
                pass
            messagebox.showerror("Trainer action failed", str(exc), parent=self.root)
        self._status_text.set(error if error is not None else self.engine.status)
        self.render()
        self._update_banners()

    # -- dialogs (content unchanged by the redesign) ----------------------------

    def show_status(self):
        messagebox.showinfo("Trainer status", self.engine.status + "\n\n" + self.engine.error +
            f"\n\nTarget: {self.engine.plan['process_name']} ({plan_architecture(self.engine.plan)['machine']})\nTable SHA-256: {self.engine.plan['table_sha256']}" +
            "\n\nCurrent means a byte patch confirmed by this trainer. Auto-on on next game launch means a saved switch." +
            "\nApply value changes memory; + / - / Reset edit the draft only. Freeze captures the current value for this session." +
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
        provider_marker = address_provider_marker(entry)
        provider_line = ("\n" + provider_marker) if provider_marker else ""
        set_summary = activation_set_summary(entry, self.engine.entries)
        set_line = ("\n" + set_summary + " (source: %s)"
                    % entry["activation_sets"].get("source", "unknown")) if set_summary else ""
        hotkeys = self.engine.hotkey_registered_keys(entry["id"])
        hotkey_line = ("\nHotkeys:\n" + "\n".join(
            hotkey_binding_line(text, registered) for text, registered in hotkeys)) if hotkeys else ""
        messagebox.showinfo("Entry information", f"{entry['label']}\nID: {entry['id']}\nPath: {path}\n" +
            f"Type: {entry.get('variable_type', entry['kind'])}\n" +
            (entry.get("reason") or "Supported by the bounded native engine") + staged_line + provider_line + set_line + hotkey_line + "\n" +
            self.engine.entry_errors.get(entry["id"], "") +
            "\nRequired symbols: " + ", ".join(entry.get("requires", [])), parent=self.root)

    # -- polling, banners, lifecycle --------------------------------------------

    def _signature(self):
        # The re-arm state and enable failures are part of the signature so
        # the row grid re-renders when an automatic re-arm attempt lands.
        rearm_state = tuple(sorted(
            (identifier, state.get("attempts"), state.get("exhausted"))
            for identifier, state in self.engine.rearm.items()))
        return (self.engine.connected, self.engine.blocked,
                tuple(sorted(self.engine.applied)), tuple(sorted(self.engine.desired)),
                tuple(sorted(self.engine.frozen)), tuple(sorted(self.engine.entry_errors)),
                self.engine.memory is None,
                tuple(sorted(self.engine.enable_failures)), rearm_state)

    def _update_banners(self):
        table_lua = self.engine.plan.get("table_lua")
        if (self.engine.memory is not None and table_lua is not None
                and table_lua.get("executed") is False):
            self.table_lua_banner.configure(
                text="Table Lua not executed on load — "
                     + str(table_lua.get("record_scripts_inactive", 0))
                     + " record scripts stay inactive")
            if not self.table_lua_strip.winfo_ismapped():
                self.table_lua_strip.pack(fill="x", after=self.status_frame)
        elif self.table_lua_strip.winfo_ismapped():
            self.table_lua_strip.pack_forget()
        banner = hotkey_conflict_banner(self.engine.hotkey_warnings)
        if banner:
            self.hotkey_banner.configure(text=banner)
            if not self.hotkey_strip.winfo_ismapped():
                self.hotkey_strip.pack(fill="x", after=self.status_frame)
        elif self.hotkey_strip.winfo_ismapped():
            self.hotkey_strip.pack_forget()
        connected = self.engine.memory is not None and self.engine.connected
        self.conn_dot.configure(fg=ON_BG if connected else OFF_BG)
        self.conn_label.configure(text=self.engine.plan["process_name"])

    def _refresh_value_texts(self):
        """Live-refresh the visible value rows between full re-renders."""
        if not self._pages or self.page >= len(self._pages):
            return
        changed = False
        # MT-21 (0.36): value rows live in per-column page slices.
        for col_rows in self._pages[self.page]:
            for row in col_rows:
                if row.kind != "value" or row.state == STATE_BLOCKED:
                    continue
                entry = self.engine.entries.get(row.entry_id)
                if entry is None:
                    continue
                staged_pending = staged_card_state(entry, self.engine.applied) == STAGED_PENDING
                try:
                    text = self.engine.read_value(row.entry_id)
                except Exception:
                    text = ("unavailable (provider inactive)"
                            if staged_pending else "unavailable")
                if self._value_texts.get(row.entry_id) != text:
                    self._value_texts[row.entry_id] = text
                    changed = True
        if changed:
            self.render()

    def poll(self):
        if self.engine.closed:
            return
        before = self._signature()
        was_attached = self.engine.memory is not None
        try:
            self.engine.poll()
        except Exception as exc:
            # Field case 2026-10-23 (Sinking City 2, 0.16.3): an exception
            # escaping this Tk after-callback propagates out of
            # mainloop() and kills the windowed trainer process without a
            # single debug-log event (stderr is unattached).  The tick is
            # fail-closed instead: the failure is logged, the engine is
            # blocked (writes refuse, the status line names the cause),
            # and the window keeps ticking so the state stays observable
            # and recoverable.
            try:
                self.engine.debug_log.error("poll-crashed", exc)
            except Exception:
                pass
            try:
                self.engine._block(exc)
            except Exception:
                pass
        # 2026-11-01 (trainer sounds): a confirmed (re-)attach - the engine
        # memory handle going from nothing to a live target - plays the
        # attach tick exactly once per transition; a failed attach attempt
        # leaves the handle None and stays silent.  Confirmed activation
        # toggles dispatched by OS hotkey (bridge drain) in this same tick
        # play the same on/off ticks a manual tap would (CE parity: the
        # generated trainer sounds on every toggle, not only UI taps).
        if (self.engine.memory is not None and not was_attached):
            play_sound("attach")
        # MT-12 (Master Trainer, 0.25): keep the Detach/Attach button label in
        # sync with the live attach state; standalone trainers have no such
        # button and skip this.
        if getattr(self, "detach_btn", None) is not None:
            label = "Detach" if self.engine.memory is not None else "Attach"
            if str(self.detach_btn.cget("text")) != label:
                self.detach_btn.configure(text=label)
        for toggle_id, on in self.engine.pop_hotkey_ui_toggles():
            play_sound("on" if on else "off")
        self._status_text.set(self.engine.status)
        self._update_banners()
        if before != self._signature():
            self.render()
        else:
            self._refresh_value_texts()
        self.root.after(POLL_MS, self.poll)

    def on_escape(self, _event):
        # Escape closes the expanded value editor; nothing else to pop.
        if self.expanded_values:
            self.expanded_values = frozenset()
            self.render()

    def on_resize(self, event):
        if event.widget is self.root:
            self._apply_filter_mode()
            self.root.minsize(*min_window_size(max(MIN_WINDOW_WIDTH, event.width)))
        elif event.widget is self.canvas:
            self.render()

    def close(self):
        clean = self.engine.close()
        if not clean:
            messagebox.showwarning("Cleanup needs attention", self.engine.status + "\n\nThe state and session journals were preserved. Restart the target before manual recovery.", parent=self.root)
        self.root.destroy()


def _log_startup_failure(plan, exc) -> None:
    """Keep the failed startup in the trainer debug log (best effort)."""
    try:
        from .debug_log import create_debug_log
        create_debug_log(plan).error("trainer-startup-failed", exc)
    except Exception:
        pass


def _log_force_event(plan, event: str, detail: str) -> None:
    """Keep the --force decision in the trainer debug log (best effort)."""
    try:
        from .debug_log import create_debug_log
        create_debug_log(plan).log(event, detail=detail)
    except Exception:
        pass


def _force_reclaim(plan) -> tuple[bool, str]:
    """The --force escape hatch for a held, unclassifiable state.

    Addresses exactly the directories the engine would have claimed
    (the documented default state home via ``default_state_dirs``) and
    hands them to ``state_force.force_reclaim``.
    """
    from .engine import default_state_dirs
    from .state_force import force_reclaim
    state_dir, shared_dir = default_state_dirs(plan)
    return force_reclaim(state_dir, shared_dir, plan)


def run_trainer(plan: dict | str | Path, force: bool = False) -> int:
    """Run from an embedded plan dictionary or a UTF-8 JSON plan file.

    ``force`` (0.38, the ``--force`` flag) skips the state-lock safety
    prompts: a recoverable stale state is archived without confirmation,
    and a leftover recovery fence (or any other unclassifiable held
    state) triggers the forced reclaim instead of the plain error
    dialog. The one boundary that stays: a proven-alive trainer session
    is still refused with its named reason, and a failed forced
    recovery still exits with the untouched state.
    """
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
        except StateError as exc:
            if not force:
                _log_startup_failure(plan, exc)
                messagebox.showerror("CT2Trainer cannot start", str(exc), parent=root)
                root.destroy()
                return 1
            # 0.38: the --force escape hatch for the documented SteamOS
            # dead end (leftover recovery fence / unclassifiable held
            # state lock): reclaim the blocking artifacts - a
            # proven-alive trainer-side owner still refuses - and
            # retry the startup.
            completed, detail = _force_reclaim(plan)
            if completed:
                _log_force_event(plan, "state-force-reclaimed", detail)
                continue
            _log_force_event(plan, "state-force-refused", detail)
            messagebox.showerror("CT2Trainer cannot start",
                                 "--force refusal: " + detail, parent=root)
            root.destroy()
            return 1
        except Exception as exc:
            _log_startup_failure(plan, exc)
            messagebox.showerror("CT2Trainer cannot start", str(exc), parent=root)
            root.destroy()
            return 1
        if stale is not None and force:
            # 0.38: no confirmation prompt - the stale state is archived
            # straight away (the documented --force contract: a
            # non-interactive forced start).
            ok, detail = perform_stale_recovery(stale)
            if not ok:
                _log_force_event(plan, "state-force-failed", detail)
                messagebox.showerror(
                    "CT2Trainer - forced recovery failed",
                    detail + "\n\nThe old state was left untouched at\n"
                    + str(stale.state_directory),
                    parent=root)
                root.destroy()
                return 1
            _log_force_event(plan, "state-force-recovered", detail)
            continue
        if stale is not None:
            if stale.live_target_takeover:
                stale_body = (
                    "The previous session of this trainer did not shut down cleanly and left a state lock behind.\n"
                    "The previous trainer process has been verified as terminated, but the game it "
                    "trained is still running.\n\n"
                    "Recovering archives the old state byte-for-byte to\n"
                    + str(stale.archive_directory) + "\n"
                    "and releases the lock. The trainer then attaches to the running game and "
                    "re-applies the saved toggles. Cheats the previous session already applied "
                    "stay in the game; toggles whose original scan pattern no longer matches "
                    "(because the game already carries that patch) will show a scan error "
                    "instead of re-applying.\n\n"
                    "Recover and attach to the running game?")
            else:
                stale_body = (
                    "The previous session of this trainer did not shut down cleanly and left a state lock behind.\n"
                    "The previous trainer process has been verified as terminated.\n\n"
                    "Recovering archives the old state byte-for-byte to\n"
                    + str(stale.archive_directory) + "\n"
                    "and releases the lock, so the trainer can start normally.\n\n"
                    "Recover and start?")
            prompt = messagebox.askyesno(
                "CT2Trainer - stale state",
                stale_body,
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
        if artifacts is not None and force:
            # 0.38: no confirmation prompt - the unfinished receipts are
            # archived straight away (the documented --force contract).
            ok, detail = perform_stale_recovery(artifacts)
            if not ok:
                _log_force_event(plan, "state-force-failed", detail)
                messagebox.showerror(
                    "CT2Trainer - forced recovery failed",
                    detail + "\n\nThe old state was left untouched at\n"
                    + str(artifacts.state_directory),
                    parent=root)
                root.destroy()
                return 1
            _log_force_event(plan, "state-force-recovered", detail)
            continue
        if artifacts is not None:
            fence_note = ""
            if (artifacts.state_directory / "recovery.lock").exists():
                fence_note = ("A recovery fence left by an interrupted recovery attempt is also part of "
                              "the stale artifacts; its owner process was verified as terminated as well.\n")
            if artifacts.live_target_takeover:
                process_note = (
                    "The recorded trainer processes have been verified as terminated, but the game "
                    "the previous session trained is still running. The trainer will attach to the "
                    "running game and re-apply the saved toggles; already applied patches stay in "
                    "the game, and toggles that no longer match their scan pattern will show a "
                    "scan error.\n")
            else:
                process_note = "The recorded target and trainer processes have been verified as terminated.\n"
            prompt = messagebox.askyesno(
                "CT2Trainer - previous session incomplete",
                ("The previous session of this trainer left unfinished receipts behind.\n"
                 + fence_note +
                 process_note +
                 "\n"
                 "Recovering archives the unfinished receipts byte-for-byte to\n"
                 + str(artifacts.archive_directory) + "\n"
                 "and releases them, so the trainer can start normally.\n\n"
                 + ("Recover and attach to the running game?" if artifacts.live_target_takeover
                    else "Recover and start?")),
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
        if live is not None and force:
            # 0.38: the one boundary that stays under --force - a
            # proven-alive second trainer session is never displaced
            # (named refusal, no termination prompt).
            refusal = ("Another trainer session (PID " + str(live.owner_pid)
                       + ") is proven alive; --force never displaces a live "
                       "trainer session. Close that session and start again.")
            _log_force_event(plan, "state-force-refused", refusal)
            messagebox.showerror("CT2Trainer cannot start",
                                 "--force refusal: " + refusal, parent=root)
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
    # Crash observability (field case 2026-10-23, Sinking City 2 0.16.3):
    # uncaught exceptions from the Tk event loop and native fatal signals
    # land in the trainer debug log instead of an unattached stderr.
    # Covers both entry points (frozen launcher and the source CLI run
    # command) because both arrive here with the final engine.
    try:
        engine.debug_log.arm_crash_reporting()
    except Exception:
        pass
    # WP-53 (GC-D7): OS hotkey capture bridge (Windows only): the hidden
    # message-only window starts with the trainer; the engine mirrors every
    # published binding into it and drains its queue on the 250 ms poll
    # tick.  Non-Windows platforms stay programmatic-only.  A failed
    # window start is named and visible; the trainer continues without
    # OS capture (dispatch stays programmatic).
    try:
        from .hotkey_bridge import HotkeyBridgeError, create_hotkey_bridge
        engine.hotkey_bridge = create_hotkey_bridge()
        engine.debug_log.log(
            "hotkey-bridge-started",
            hwnd=getattr(engine.hotkey_bridge, "_hwnd", 0),
        )
    except HotkeyBridgeError as exc:
        print("CT2Trainer: " + str(exc), file=sys.stderr)
        engine.debug_log.error("hotkey-bridge-failed", exc)
    TrainerWindow(root, engine)
    root.deiconify()
    root.mainloop()
    return 0 if not engine.blocked else 1
