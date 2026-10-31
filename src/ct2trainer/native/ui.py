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

Deliberately unchanged by the redesign: the audio tones
(``play_toggle_sound``, 880/440 Hz), the amber banner strings (hotkey
conflict, table-Lua bootstrap), the Info dialog content, the startup
recovery dialogs in ``run_trainer`` and the dark high-contrast palette
(constants extended for the row accents, not replaced).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
import struct
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk
from typing import Callable

from .engine import (TrainerEngine, NativeRuntimeError, parse_value, format_value,
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
                      RowSnapshot, build_rows, find_row, slice_pages)
from .ui_script_view import entry_assessment, row_details, script_preview


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


# Touch input and transient-reaction timing (D6/D8 of the design doc).
DRAG_THRESHOLD_PX = 80   # B1-Motion drag distance that pages the row list
LONGPRESS_MS = 400       # press duration that opens the row context menu
PULSE_MS = 300           # row pulse after a successful toggle / value write
CONFIRM_MS = 2000        # transient "OK" chip duration
POLL_MS = 250            # engine poll cadence (unchanged)


class TrainerWindow:
    """Canvas renderer over the pure row model; forwards input to the engine."""

    def __init__(self, root: tk.Tk, engine: TrainerEngine,
                 master_back: Callable[[], None] | None = None):
        self.root, self.engine = root, engine
        # MT-4 (Master Trainer): optional "back to the Master wait mode"
        # callback.  None keeps the standalone trainer exactly as before
        # (no extra header button); the Master Trainer passes its handler.
        self.master_back = master_back
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
        self._page_offset = 0
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
        rows = build_rows(self.engine.entries, self.view, self._search_text.get(),
                          snapshot, width,
                          expanded_values=self.expanded_values,
                          collapsed_sections=self.collapsed_sections,
                          values=self._value_texts)
        pages = slice_pages(rows, area)
        self._rows, self._pages = rows, pages
        self._mark_chips()
        if not rows:
            self._page_offset = 0
            self.page = 0
            self._page_text.set("Page 1 / 1")
            self.canvas.create_text(width / 2, 24,
                                    text="No entries match this view or search.",
                                    fill=FG_DIM, font=("Segoe UI", 12))
            return
        if self.page >= len(pages):
            self.page = len(pages) - 1
        self.page = max(0, self.page)
        visible = pages[self.page]
        self._page_offset = visible[0].y
        for row in visible:
            self._draw_row(row, width, self._page_offset)
        self._page_text.set(f"Page {self.page + 1} / {len(pages)}")

    def _draw_row(self, row, width, offset):
        canvas = self.canvas
        canvas.create_rectangle(0, row.y - offset, width, row.y + row.height - offset,
                                fill=row.tint, outline="")
        canvas.create_rectangle(0, row.y - offset, ACCENT_BAR_WIDTH,
                                row.y + row.height - offset, fill=row.accent, outline="")
        if row.kind == "section":
            self._draw_section(row, offset)
        elif row.kind == "switch":
            self._draw_switch(row, offset)
        else:
            self._draw_value(row, offset)
        if row.chip:
            canvas.create_text(width - 44, row.y + row.height / 2 - offset,
                               anchor="e", text=row.chip, fill=TEXT_DIM,
                               font=("Segoe UI", 11))
        if row.error_dot:
            canvas.create_oval(width - 36, row.y + 16 - offset, width - 28,
                               row.y + 24 - offset, fill=ACCENT_ERROR, outline="")
        if row.info_hit is not None:
            self._draw_info_chip(row.info_hit.x, row.info_hit.y - offset)
        if row.confirmed:
            canvas.create_text(width - 10, row.y + 8 - offset, anchor="ne",
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
        label_x = ACCENT_BAR_WIDTH + PILL_GAP_AFTER_BAR + PILL_W + LABEL_GAP_AFTER_PILL + row.indent
        canvas.create_text(label_x, row.y + 18 - offset, anchor="w", text=row.label,
                           fill=FG, font=("Segoe UI", 12))
        if row.sublabel:
            canvas.create_text(label_x, row.y + 38 - offset, anchor="w",
                               text=row.sublabel, fill=TEXT_DIM, font=("Segoe UI", 11))

    def _draw_value(self, row, offset):
        canvas = self.canvas
        label_x = ACCENT_BAR_WIDTH + PILL_GAP_AFTER_BAR + row.indent
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
        width = self.canvas.winfo_width() or self.root.winfo_width()
        canvas.create_text(width - 8, row.y + (18 if expanded else 22) - offset,
                           anchor="e", text=row.value_text,
                           fill=TEXT_DIM if expanded else FG, font=("Consolas", 12))
        if row.frozen_badge:
            badge_y = row.y + (12 if expanded else 34) - offset
            canvas.create_rectangle(width - 8 - 14, badge_y, width - 8 - 4,
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
        name_x = 16 + row.indent + SECTION_CHEVRON_W + SECTION_NAME_GAP
        if row.sublabel:
            canvas.create_text(name_x, row.y + 16 - offset, anchor="w", text=row.label,
                               fill=FG, font=("Segoe UI", 13, "bold"))
            canvas.create_text(name_x, row.y + 34 - offset, anchor="w",
                               text=row.sublabel, fill=TEXT_DIM, font=("Segoe UI", 11))
        else:
            canvas.create_text(name_x, row.y + ROW_HEIGHT_SECTION / 2 - offset, anchor="w",
                               text=row.label, fill=FG, font=("Segoe UI", 13, "bold"))
        width = self.canvas.winfo_width() or self.root.winfo_width()
        counter_x = width - 8 - (GROUP_TOGGLE_W + 8 if row.group_toggle else 0)
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

    def _row_at(self, x, y):
        if not self._rows:
            return None
        return find_row(self._rows, y + self._page_offset)

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
        return items

    def _show_context_menu(self, entry, position):
        if position is None:
            return
        menu = tk.Menu(self.root, tearoff=0)
        for label, command in self._context_menu_items(entry):
            menu.add_command(label=label, command=command)
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
            play_toggle_sound(on=identifier in self.engine.applied)
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
        return (self.engine.connected, self.engine.blocked,
                tuple(sorted(self.engine.applied)), tuple(sorted(self.engine.desired)),
                tuple(sorted(self.engine.frozen)), tuple(sorted(self.engine.entry_errors)),
                self.engine.memory is None)

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
        for row in self._pages[self.page]:
            if row.kind != "value" or row.state == STATE_BLOCKED:
                continue
            entry = self.engine.entries.get(row.entry_id)
            if entry is None:
                continue
            staged_pending = staged_card_state(entry, self.engine.applied) == STAGED_PENDING
            try:
                text = self.engine.read_value(row.entry_id)
            except Exception:
                text = "unavailable (provider inactive)" if staged_pending else "unavailable"
            if self._value_texts.get(row.entry_id) != text:
                self._value_texts[row.entry_id] = text
                changed = True
        if changed:
            self.render()

    def poll(self):
        if self.engine.closed:
            return
        before = self._signature()
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
