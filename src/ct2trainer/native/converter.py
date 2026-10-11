"""Independent desktop CT converter. Never loads the CE adapter or bundle."""
from __future__ import annotations
import json
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .about_ui import converter_title, repo_link
from .compiler import compile_table
from .bundle import build_trainer
from .process_detect import find_candidates
from .window_icon import window_icon_path


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
    model = {"plan": None, "selected": set()}
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

    def inspect():
        try:
            plan = compile_table(Path(table_path.get()), process.get(), title=title.get(),
                                 architecture=architecture.get())
            model["plan"] = plan
            model["selected"] = {e["id"] for e in plan["entries"] if e["supported"]}
            render()
            supported = len(model["selected"])
            staged = sum(1 for e in plan["entries"] if e["supported"] and e.get("staged") is not None)
            blocked = sum(1 for e in plan["entries"] if not e["supported"])
            status.set(f"Target {architecture.get()}: {supported} supported ({staged} staged, {blocked} blocked) records. Blocked records retain their reasons; Lua is never executed.")
        except (ValueError, OSError, RuntimeError) as exc:
            model["plan"] = None
            messagebox.showerror("CT inspection", str(exc), parent=root)

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
        for e in model["plan"]["entries"]:
            tree.insert("", "end", iid=str(e["id"]), text=e["path"], values=(
                "Yes" if e["id"] in model["selected"] else "", e["id"], e["kind"],
                entry_capability(e), entry_details(e)))

    def select_record(event=None):
        if model["plan"] is None:
            return
        for row in tree.selection():
            record_id = int(row)
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
                             architecture=architecture.get())

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
            messagebox.showerror("Trainer build", str(exc), parent=root)

    def export():
        try:
            plan = selected_plan()
            output = filedialog.asksaveasfilename(parent=root, defaultextension=".json", filetypes=[("Native trainer plan", "*.json")])
            if output:
                Path(output).write_text(json.dumps(plan, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
                status.set(f"Saved {output}")
        except (ValueError, OSError, RuntimeError) as exc:
            messagebox.showerror("Plan export", str(exc), parent=root)

    def architecture_changed(event=None):
        model["plan"] = None
        model["selected"] = set()
        tree.delete(*tree.get_children())
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
