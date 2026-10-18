"""Independent desktop CT converter. Never loads the CE adapter or bundle.

WP-39: the inspection window renders the structured per-table result
({supported, blocked, top_reasons, warnings}) derived from the compiled
plan, plan warnings, and expandable per-record blocked reasons. The four
hard failure classes (G4a-G4d) render as named per-file diagnostics; the
messagebox stays reserved for unexpected errors.
"""
from __future__ import annotations
import json
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ..table import MAX_ENTRIES, TableError
from .about_ui import converter_title, repo_link
from .compiler import NativeCompileError, compile_table
from .bundle import build_trainer
from .process_detect import find_candidates
from .window_icon import window_icon_path

# Runtime host refusal taxonomy for CE Lua APIs outside the declared
# read-only profile boundary (lua_host).  The inspection result groups
# block reasons carrying this exact prefix by the named API, so the whole
# profile boundary reads as one decision in the window.
MISSING_LUA_API_PREFIX = "Unsupported CE Lua API: "


class InspectionError(ValueError):
    """A plan shape the structured inspection result cannot derive from."""


def missing_lua_api(reason: str) -> str | None:
    """Name the CE Lua API a block reason refuses, or None for other reasons.

    Reuses the existing runtime refusal taxonomy verbatim; no new strings
    are introduced for the profile-boundary grouping.
    """
    if not isinstance(reason, str) or not reason.startswith(MISSING_LUA_API_PREFIX):
        return None
    api = reason[len(MISSING_LUA_API_PREFIX):].strip()
    return api if api else None


def table_inspection(plan: dict) -> dict:
    """Structured per-table inspection result derived from a compiled plan.

    GUI-side derivation (WP-39): no plan metadata is added, so both plan
    validators stay untouched; the result is a pure deterministic function
    of the plan's own entries and warnings and therefore byte-verifiable
    against the plan.

    Shape:
      supported:   int, count of supported entries
      blocked:     int, count of blocked entries
      top_reasons: list of {"key", "reason", "api", "count", "records"},
                   one group per top block reason, ordered by casefolded
                   key; missing-Lua-API refusals group by the named API
      warnings:    the plan warnings, verbatim and in plan order
    """
    if not isinstance(plan, dict):
        raise InspectionError("Inspection input must be a plan dict.")
    entries = plan.get("entries")
    if (not isinstance(entries, list) or not entries or len(entries) > MAX_ENTRIES):
        raise InspectionError("Inspection plan entries must be a bounded nonempty list.")
    warnings = plan.get("warnings")
    if not isinstance(warnings, list) or not all(isinstance(item, str) for item in warnings):
        raise InspectionError("Inspection plan warnings must be a list of text.")
    supported = 0
    groups: dict[str, dict] = {}
    seen: set[int] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise InspectionError("Inspection plan entry must be an object.")
        record_id = entry.get("id")
        if type(record_id) is not int or record_id < 0 or record_id in seen:
            raise InspectionError("Inspection plan record IDs must be unique nonnegative integers.")
        seen.add(record_id)
        if type(entry.get("supported")) is not bool:
            raise InspectionError("Inspection plan entries need a boolean supported flag.")
        if not isinstance(entry.get("reason"), str):
            raise InspectionError("Inspection plan entries need a text reason.")
        if entry["supported"]:
            supported += 1
            continue
        api = missing_lua_api(entry["reason"])
        key = api if api is not None else entry["reason"]
        group = groups.setdefault(key, {"api": api, "reasons": set(), "records": []})
        group["reasons"].add(entry["reason"])
        group["records"].append(record_id)
    top_reasons = [
        {"key": key,
         "reason": sorted(group["reasons"], key=str.casefold)[0],
         "api": group["api"],
         "count": len(group["records"]),
         "records": sorted(group["records"])}
        for key, group in sorted(groups.items(), key=lambda item: item[0].casefold())
    ]
    return {"supported": supported, "blocked": len(entries) - supported,
            "top_reasons": top_reasons, "warnings": list(warnings)}


def file_diagnostic(exc: BaseException) -> str | None:
    """Named per-file diagnostic for one hard CT failure class (G4a-G4d).

    The four known classes map to stable names rendered in the inspection
    window:
      TableError (any)                    -> Malformed or unreadable CT table
      process-name refusal                -> Bad target binding
      unsupported plan schema refusal     -> Unsupported plan schema
      every other compile refusal         -> Compile failure
    Any other exception returns None, which keeps the messagebox reserved
    for unexpected errors.
    """
    if isinstance(exc, TableError):
        return "Malformed or unreadable CT table"
    if isinstance(exc, NativeCompileError):
        message = str(exc)
        if message == "Process name must be an exact .exe basename without a path.":
            return "Bad target binding"
        if message == "Unsupported native plan schema or engine.":
            return "Unsupported plan schema"
        return "Compile failure"
    return None


def main() -> int:
    root = tk.Tk()
    root.title(converter_title())
    root.geometry("1080x780")
    root.minsize(650, 610)
    try:
        icon = window_icon_path("converter")
        if icon.is_file():
            root.iconbitmap(str(icon))
    except tk.TclError:
        pass
    style = ttk.Style(root)
    style.configure("Native.TButton", padding=(12, 16), font=("Segoe UI", 12))
    style.configure("Treeview", rowheight=32)
    table_path = tk.StringVar()
    process = tk.StringVar(value="game.exe")
    title = tk.StringVar(value="CT2Trainer")
    architecture = tk.StringVar(value="x64")
    status = tk.StringVar(value="Open a CT to inspect the supported independent-runtime subset.")
    model = {"plan": None, "selected": set(),
             "inspection": None, "file_diagnosis": None}
    top = ttk.Frame(root, padding=12)
    top.pack(fill="x")
    ttk.Label(top, text="CT file").grid(row=0, column=0, sticky="w")
    ttk.Entry(top, textvariable=table_path).grid(row=0, column=1, sticky="ew", padx=8)
    ttk.Label(top, text="Exact process EXE").grid(row=1, column=0, sticky="w", pady=8)
    ttk.Entry(top, textvariable=process).grid(row=1, column=1, sticky="ew", padx=8)
    ttk.Label(top, text="Trainer title").grid(row=2, column=0, sticky="w")
    ttk.Entry(top, textvariable=title).grid(row=2, column=1, sticky="ew", padx=8)
    ttk.Label(top, text="Target architecture").grid(row=3, column=0, sticky="w", pady=8)
    architecture_choice = ttk.Combobox(top, textvariable=architecture, values=("x86", "x64"), state="readonly")
    architecture_choice.grid(row=3, column=1, sticky="ew", padx=8)
    debug_log = tk.BooleanVar(value=False)
    ttk.Checkbutton(top, text="Debug logging (trainer writes a detailed .ct2debug.log next to the EXE)",
                    variable=debug_log).grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))
    top.columnconfigure(1, weight=1)
    tree_frame = ttk.Frame(root, padding=(12, 0))
    tree_frame.pack(fill="both", expand=True)
    tree = ttk.Treeview(tree_frame, columns=("include", "id", "type", "support", "reason"), show="tree headings")
    tree.heading("#0", text="Record / context")
    tree.column("#0", width=360, minwidth=150)
    for name, heading, width in (("include", "Include", 65), ("id", "ID", 80), ("type", "Type", 80), ("support", "Capability", 100), ("reason", "Details", 340)):
        tree.heading(name, text=heading)
        tree.column(name, width=width, minwidth=55)
    scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")
    tree.pack(fill="both", expand=True)
    # WP-39: plan warnings (table Lua, forms, hotkeys, omitted sections,
    # duplicate IDs, ...) and file-level diagnostics render here instead of
    # in a bare popup.
    warnings_frame = ttk.LabelFrame(tree_frame, text="Plan warnings", padding=(4, 2))
    warnings_frame.pack(fill="x", pady=(6, 0))
    warnings_text = tk.Text(warnings_frame, height=3, wrap="word", state="disabled")
    warnings_text.pack(fill="x")

    def inspect():
        try:
            plan = compile_table(Path(table_path.get()), process.get(), title=title.get(),
                                 architecture=architecture.get(), debug_log=debug_log.get())
        except (ValueError, OSError, RuntimeError) as exc:
            # WP-39: the four hard failure classes (malformed/unreadable CT,
            # bad target binding, unsupported plan schema, compile failure)
            # render as named file-level diagnostics in the window below;
            # the messagebox stays reserved for unexpected errors.
            model["plan"] = None
            model["inspection"] = None
            model["file_diagnosis"] = file_diagnostic(exc)
            render()
            if model["file_diagnosis"] is None:
                messagebox.showerror("CT inspection", str(exc), parent=root)
                status.set("CT inspection failed with an unexpected error.")
            else:
                status.set(model["file_diagnosis"] + ": " + str(exc))
            return
        model["plan"] = plan
        model["inspection"] = table_inspection(plan)
        model["file_diagnosis"] = None
        model["selected"] = {e["id"] for e in plan["entries"] if e["supported"]}
        render()
        supported = len(model["selected"])
        staged = sum(1 for e in plan["entries"] if e["supported"] and e.get("staged") is not None)
        inspection = model["inspection"]
        status.set(f"Target {architecture.get()}: {supported} supported ({staged} staged, {inspection['blocked']} blocked) records. Blocked records retain their reasons; Lua is never executed.")
        if inspection["top_reasons"]:
            status.set(status.get() + " Top blocked: " + "; ".join(
                f"{group['key']} x{group['count']}" for group in inspection["top_reasons"]))
        if inspection["warnings"]:
            status.set(status.get() + f" {len(inspection['warnings'])} plan warning(s) in the list below.")

    def open_ct():
        selected = filedialog.askopenfilename(parent=root, filetypes=[("Cheat tables", "*.CT *.ct")])
        if selected:
            table_path.set(selected)
            try:
                data = Path(selected).read_bytes()
            except OSError:
                data = b""
            candidates = find_candidates(data)
            if len(candidates) == 1:
                # A CT often spells out the module filename; a single distinct
                # EXE fills the field as a suggestion, never as proof.
                process.set(candidates[0])
            inspect()
            if len(candidates) > 1:
                status.set("CT names several EXEs; choose the exact target: " + ", ".join(candidates))
            elif not candidates:
                status.set("No EXE name found in the CT; enter the exact target EXE manually.")

    def entry_capability(e):
        if not e["supported"]:
            return "Blocked"
        if e.get("staged") is not None:
            return "Staged"
        return "Supported"

    def entry_details(e):
        if not e["supported"]:
            return e.get("reason", "")
        details = [e.get("reason", "")]
        staged = e.get("staged")
        if staged is not None:
            details.append("Unlocks after: " + ", ".join(staged.get("provider_labels", ())))
        sets = e.get("activation_sets")
        if sets is not None:
            details.append("Master toggle: %d records" % len(sets.get("enable", ())))
        return "; ".join(part for part in details if part)

    def render():
        tree.delete(*tree.get_children())
        plan = model["plan"]
        warnings_text.config(state="normal")
        warnings_text.delete("1.0", "end")
        if plan is None:
            # WP-39: file-level diagnostic for a failed inspection; the
            # window explains the named failure instead of a bare popup.
            if model["file_diagnosis"] is not None:
                warnings_text.insert("1.0", "File-level diagnostic: " + model["file_diagnosis"] + "\n")
            warnings_text.config(state="disabled")
            return
        inspection = model["inspection"]
        for e in plan["entries"]:
            tree.insert("", "end", iid=str(e["id"]), text=e["path"], values=(
                "Yes" if e["id"] in model["selected"] else "", e["id"], e["kind"],
                entry_capability(e), entry_details(e)))
        # WP-39: per-table top reasons, each expandable to its blocked
        # records with their exact named reasons.  Missing-Lua-API blocks
        # group by the named API (the profile boundary is one decision).
        by_id = {e["id"]: e for e in plan["entries"]}
        for group in inspection["top_reasons"]:
            heading = group["key"]
            if group["api"] is not None:
                heading = "Missing Lua API: " + heading
            heading += f" ({group['count']} blocked record" + ("" if group["count"] == 1 else "s") + ")"
            row = tree.insert("", "end", text=heading, values=(
                "", "", "reason group", str(group["count"]), group["reason"]), open=True)
            for record_id in group["records"]:
                record = by_id[record_id]
                tree.insert(row, "end", text=record["path"], values=(
                    "", record["id"], record["kind"], "Blocked", record["reason"]))
        for warning in inspection["warnings"]:
            warnings_text.insert("end", warning + "\n")
        warnings_text.config(state="disabled")

    def select_record(event=None):
        if model["plan"] is None:
            return
        for row in tree.selection():
            try:
                record_id = int(row)
            except ValueError:
                continue  # reason-group rows are display-only
            if record_id in model["selected"]:
                model["selected"].remove(record_id)
            else:
                model["selected"].add(record_id)
        render()

    def selected_plan():
        if model["plan"] is None:
            raise ValueError("Open and inspect a CT first.")
        if not model["selected"]:
            raise ValueError("Include at least one record.")
        return compile_table(Path(table_path.get()), process.get(), title=title.get(), selected_ids=model["selected"],
                             architecture=architecture.get(), debug_log=debug_log.get())

    def report_failure(exc, operation):
        # WP-39: the four hard failure classes are named per-file
        # diagnostics on the status line; the messagebox stays reserved
        # for unexpected errors.
        diagnosis = file_diagnostic(exc)
        if diagnosis is None:
            messagebox.showerror(operation, str(exc), parent=root)
            status.set(operation + " failed with an unexpected error.")
        else:
            status.set(operation + " — " + diagnosis + ": " + str(exc))

    def build():
        try:
            plan = selected_plan()
            output = filedialog.asksaveasfilename(parent=root, defaultextension=".exe", filetypes=[("Windows trainer", "*.exe")])
            if not output:
                return
            # Tk save dialog has already obtained overwrite consent.
            executable, report = build_trainer(plan, output, force=True)
            status.set(f"Built {executable.name}; report: {report.name}")
            messagebox.showinfo("Independent trainer built", f"{executable}\n\nSupported capabilities are checked byte patches and typed values. See the report for included records.\n\nWindows game and Proton compatibility require testing.", parent=root)
        except (ValueError, OSError, RuntimeError) as exc:
            report_failure(exc, "Trainer build")

    def export():
        try:
            plan = selected_plan()
            output = filedialog.asksaveasfilename(parent=root, defaultextension=".json", filetypes=[("Native trainer plan", "*.json")])
            if output:
                Path(output).write_text(json.dumps(plan, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
                status.set(f"Saved {output}")
        except (ValueError, OSError, RuntimeError) as exc:
            report_failure(exc, "Plan export")

    def architecture_changed(event=None):
        model["plan"] = None
        model["inspection"] = None
        model["file_diagnosis"] = None
        model["selected"] = set()
        render()
        status.set("Target architecture changed. Inspect again before selecting or building.")

    architecture_choice.bind("<<ComboboxSelected>>", architecture_changed)
    ttk.Button(top, text="Open CT…", command=open_ct, style="Native.TButton").grid(row=0, column=2, rowspan=2)
    ttk.Button(top, text="Inspect again", command=inspect).grid(row=2, column=2)
    tree.bind("<Double-1>", select_record)
    bottom = ttk.Frame(root, padding=12)
    bottom.pack(fill="x")
    for text, callback in (("Include / remove selection", select_record), ("Save source plan…", export), ("Build trainer EXE…", build)):
        ttk.Button(bottom, text=text, command=callback, style="Native.TButton").pack(side="left", padx=(0, 8))
    repo_link(bottom).pack(side="right")
    ttk.Label(root, textvariable=status, wraplength=950, padding=12).pack(fill="x")
    root.mainloop()
    return 0
