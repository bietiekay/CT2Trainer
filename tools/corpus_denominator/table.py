#!/usr/bin/env python3
"""Table-level parsing and classification helpers (read-only, stdlib only)."""
import re
import xml.etree.ElementTree as ET
from collections import Counter
try:
    from .classify import classify_record
except ImportError:
    from classify import classify_record

MAIN_INIT_RE = re.compile(r"\b(?:main|init|initialise|initialize|setup|start|load)\b", re.I)


def user_defined_symbol_names(root):
    """Names declared in the table's own UserdefinedSymbols section."""
    names = set()
    section = root.find("UserdefinedSymbols")
    if section is None:
        return names
    for child in section.iter():
        for attr in ("Name", "name"):
            value = child.attrib.get(attr)
            if value:
                names.add(value)
    return names


def table_flags(root):
    """Static table-level feature flags, no execution."""
    lua = root.find("LuaScript")
    flags = {
        "table_lua": lua is not None and bool((lua.text or "").strip()),
        "forms": root.find("Forms") is not None,
        "forms_count": len(root.find("Forms")) if root.find("Forms") is not None else 0,
        "cheat_codes": root.find("CheatCodes") is not None,
        "structures": root.find("Structures") is not None,
        "embedded_files": root.find("Files") is not None,
        "custom_types_section": root.find("CustomTypes") is not None,
        "user_defined_symbols": len(user_defined_symbol_names(root)),
    }
    return flags


def _entry_id(entry):
    try:
        return int((entry.findtext("ID") or "").strip())
    except ValueError:
        return None


def _label_of(entry):
    label = (entry.findtext("Description") or "").strip()
    if len(label) >= 2 and label[0] == label[-1] == '"':
        label = label[1:-1]
    return label


def iter_entries(root):
    """Yield (entry, depth, labels) for EVERY CheatEntry in document order.

    Mirrors the product's single visit() traversal (src/ct2trainer/table.py):
    each entry's nested CheatEntries are visited regardless of group status, so
    records nested under group headers are not lost. GroupHeader uses the
    product's exact "1" comparison.
    """
    def visit(entry, depth, labels):
        label = _label_of(entry)
        yield entry, depth, tuple(labels) + (label,)
        for child in entry.findall("./CheatEntries/CheatEntry"):
            yield from visit(child, depth + 1, tuple(labels) + (label,))

    for entry in root.findall("./CheatEntries/CheatEntry"):
        yield from visit(entry, 0, ())


def iter_records(root):
    """Yield (entry, depth, labels, group_labels) for every non-group CheatEntry.

    labels = full ancestor chain incl. the record's own label;
    group_labels = only the group-header ancestors (CE breadcrumb).
    """
    def visit(entry, depth, labels, group_labels):
        is_group = entry.findtext("GroupHeader") == "1"
        label = _label_of(entry)
        if not is_group:
            yield entry, depth, tuple(labels) + (label,), tuple(group_labels)
        next_labels = tuple(labels) + (label,)
        next_groups = group_labels + (label,) if is_group else group_labels
        for child in entry.findall("./CheatEntries/CheatEntry"):
            yield from visit(child, depth + 1, next_labels, next_groups)

    for entry in root.findall("./CheatEntries/CheatEntry"):
        yield from visit(entry, 0, (), ())


def iter_groups(root):
    """Yield (entry, depth, labels, children, descendant records) for groups."""
    def collect(nodes, out):
        for node in nodes:
            if node.findtext("GroupHeader") == "1":
                collect(node.findall("./CheatEntries/CheatEntry"), out)
            else:
                out.append(node)

    for entry, depth, labels in iter_entries(root):
        if entry.findtext("GroupHeader") != "1":
            continue
        descendants = []
        collect(entry.findall("./CheatEntries/CheatEntry"), descendants)
        yield entry, depth, labels, entry.findall("./CheatEntries/CheatEntry"), descendants


def _child_has_own_effect(child):
    vt = (child.findtext("VariableType") or "").strip()
    if vt == "Auto Assembler Script":
        return True
    if vt and (child.findtext("Address") or "").strip():
        return True
    script = child.find("AssemblerScript")
    return script is not None and bool((script.text or "").strip())


MAX_TOGGLE_DEPTH = 64


def group_toggle(entry, descendants):
    """Mirror the product's static group ON-effect rule.

    A group checkbox is an expected collective action only when the group
    itself opts into CE child-activation (moActivateChildrenAsWell /
    moBindActivation) and that activation reaches a record with an own
    effect; otherwise it is a plain heading (navigation). Mirrors
    _group_has_builtin_on_effect from src/ct2trainer/table.py.
    """
    def on_effect(element, depth):
        if depth > MAX_TOGGLE_DEPTH:
            return False
        options = element.find("Options")
        activates = options is not None and any(
            options.attrib.get(name) == "1" for name in
            ("moActivateChildrenAsWell", "moBindActivation"))
        if not activates:
            return False
        for child in element.findall("./CheatEntries/CheatEntry"):
            if child.findtext("GroupHeader") == "1":
                if on_effect(child, depth + 1):
                    return True
            elif _child_has_own_effect(child):
                return True
        return False

    has_checkbox = entry.attrib.get("NoCheckbox") != "1"
    effect = on_effect(entry, 0)
    return {"has_checkbox": bool(has_checkbox), "on_effect": bool(effect),
            "action": bool(has_checkbox and effect)}


def main_initialization(records, table_lua):
    """Conservative heuristic for the table's main initialization.

    Table-level Lua dominates; otherwise the first depth-0 script record with
    a main-like name, else the first depth-0 script record.
    """
    if table_lua:
        return {"source": "table_lua", "status": "locked",
                "gaps": ["table_lua_lifecycle"],
                "note": "Table Lua loads on import (statistical, without execution)"}
    scripts = [r for r in records
               if r["type"] in ("aa_script", "aa_script+lua", "script_lua")]
    top_level = [r for r in scripts if r["depth"] == 0]
    pool = top_level or scripts
    if not pool:
        return None
    named = next((r for r in pool if MAIN_INIT_RE.search(r["name"] or "")), None)
    chosen = named or pool[0]
    if named:
        note = "named main script"
    elif top_level:
        note = "first depth-0 script record"
    else:
        note = "no top-level script; first script record (document order)"
    return {"source": "record", "id": chosen["id"], "name": chosen["name"],
            "type": chosen["type"], "status": chosen["status"],
            "gaps": chosen["gaps"], "note": note}


def architecture_hints(basename, modules, scans):
    """Static architecture hints from file name, module refs and instruction
    width. Hints only: they are not an attach proof."""
    signals = []
    x86 = x64 = 0
    name = (basename or "").lower()
    for token, arch in (("32bit", "x86"), ("win32", "x86"), ("x86", "x86"),
                        ("64bit", "x64"), ("win64", "x64"), ("x64", "x64")):
        if token in name:
            signals.append(f"filename:{token}")
            if arch == "x86":
                x86 += 1
            else:
                x64 += 1
    for module in modules:
        low = module.lower()
        if "gameassembly.dll" in low:
            signals.append("module:gameassembly")
            x64 += 1
        elif any(token in low for token in ("win64", "64bit")):
            signals.append(f"module:{module}")
            x64 += 1
        elif any(token in low for token in ("32bit", "win32", "x86")):
            signals.append(f"module:{module}")
            x86 += 1
    instr64 = sum(scan.get("instr64_lines", 0) for scan in scans)
    instr32 = sum(scan.get("instr32_lines", 0) for scan in scans)
    if instr64:
        signals.append(f"instr64:{instr64} lines")
        x64 += 1
    # instr32_lines is reported for transparency but intentionally not used
    # as a signal: 32-bit registers and dword operands are valid in x64 code.
    if instr32:
        signals.append(f"instr32:{instr32} lines (not an architecture signal)")
    if x86 and not x64:
        value = "x86"
    elif x64 and not x86:
        value = "x64"
    elif x86 and x64:
        value = "mixed"
    else:
        value = "unknown"
    return {"value": value, "signals": signals}
