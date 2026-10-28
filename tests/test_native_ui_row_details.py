"""Pure contract tests for the combined row-details window (0.18).

Covers the new ``ui_script_view`` builders added for the trainer row
context menu (right-click / long-press): ``entry_actions`` (which concrete
actions the trainer performs for an entry, plan metadata only) and
``row_details`` (the combined window content: raw script + assessment +
actions used), plus the CE-Lua API extraction ``lua_apis_used``.  Also pins
the context-menu wiring in ``ui.TrainerWindow``: the new "Row details"
item leads the menu and ``show_row_details`` builds the read-only
Toplevel with the builder content.
"""
from __future__ import annotations

import types
import unittest

try:
    import tkinter as tk
    from tkinter import scrolledtext
except ImportError:  # pragma: no cover - environment without Tcl/Tk
    tk = None
    scrolledtext = None

from ct2trainer.native.ui import TrainerWindow
from ct2trainer.native.ui_script_view import (
    entry_actions,
    entry_assessment,
    lua_apis_used,
    row_details,
    script_backing,
    script_preview,
)


def _program_entry():
    return {
        "id": 121,
        "label": "Syn01 Item 121",
        "path": "SynT Group 001 / Syn01 Item 121",
        "kind": "script",
        "supported": True,
        "selected": True,
        "reason": "",
        "requires": ["base_ptr"],
        "provides": ["synAOB0121"],
        "dependency_ids": [7],
        "one_shot": False,
        "source_hotkey_count": 1,
        "runtime_verified": True,
        "enable": [],
        "disable": [],
        "program": {
            "bitness": 64,
            "source": "[ENABLE]\nalloc(synCave0121,64)\n[DISABLE]\ndealloc(synCave0121)",
            "enable": [
                {"op": "scan", "symbol": "base", "module": "$process",
                 "pattern": "48 8B 05 01 02 03 04"},
                {"op": "register", "symbol": "synAOB0121"},
            ],
            "disable": [{"op": "unregister", "symbol": "synAOB0121"}],
            "capabilities": ["aobscan", "register", "unregister"],
        },
    }


def _operations_entry():
    return {
        "id": 56, "label": "Ops Entry", "kind": "script",
        "supported": True, "selected": True, "one_shot": True,
        "enable": [
            {"op": "scan", "symbol": "base", "module": "$process",
             "pattern": "48 8B 05 01 02 03 04"},
            {"op": "define", "symbol": "addr", "expression": "base+10"},
            {"op": "write", "address": "addr", "bytes": "C3"},
        ],
        "disable": [{"op": "unregister", "symbol": "base"}],
    }


def _lua_entry():
    source = (
        "[ENABLE]\n"
        "lua()\n"
        "local addr = getAddressSafe('Game.exe', 1234)\n"
        "WriteInteger(addr, 42)\n"
        "local sl = createStringList()\n"
        "sl.add('x')\n"
        "string.match('abc', 'b')\n"
        "autoAssemble('[ENABLE]\\nrevert"
        "end_lua\n"
        "[DISABLE]\n"
        "lua()\n"
        "unregisterSymbol('base')\n"
        "end_lua"
    )
    return {
        "id": 9, "label": "Lua Cheat", "kind": "script",
        "supported": True, "selected": True,
        "lua_program": {
            "bitness": 64,
            "source": source,
            "static_program": {
                "enable": [{"op": "register", "symbol": "base"}],
                "disable": [{"op": "unregister", "symbol": "base"}],
            },
        },
    }


def _value_entry():
    return {
        "id": 3, "label": "Health", "kind": "value",
        "supported": True, "selected": True,
        "variable_type": "4 Bytes", "show_as_hex": True,
        "address": "Game.exe+1234",
    }


class LuaApisUsedTests(unittest.TestCase):
    def test_extracts_canonical_names_casefold_sorted(self):
        source = ("readInteger(a)\nWriteInteger(a, 1)\ngetAddressSafe(m, o)\n"
                  "registerSymbol('s')\nunknownLocal(x)\n")
        self.assertEqual(
            lua_apis_used(source),
            ["getAddressSafe", "readInteger", "registerSymbol",
             "writeInteger"])

    def test_first_letter_case_variants_are_matched(self):
        # CE registers first-letter case-flipped variants; extraction is
        # case-insensitive but reports the canonical spelling.
        self.assertEqual(lua_apis_used("READFLOAT(x)"), ["readFloat"])
        self.assertEqual(lua_apis_used("AutoAssemble('x')"), ["autoAssemble"])

    def test_method_calls_and_stdlib_do_not_match(self):
        source = "sl.add('a')\nstring.match('b', 'c')\nprint('d')\ntostring(1)\n"
        self.assertEqual(lua_apis_used(source), [])

    def test_empty_source(self):
        self.assertEqual(lua_apis_used(""), [])
        self.assertEqual(lua_apis_used(None), [])

    def test_duplicates_are_collapsed(self):
        self.assertEqual(
            lua_apis_used("writeInteger(a, 1)\nwriteInteger(b, 2)\n"),
            ["writeInteger"])


class EntryActionsTests(unittest.TestCase):
    def test_operations_backing_renders_phases(self):
        self.assertEqual(entry_actions(_operations_entry()),
                         "[ENABLE]\n"
                         "aobscan base module=$process pattern=48 8B 05 01 02 03 04\n"
                         "define addr = base+10\n"
                         "write addr = C3\n"
                         "\n"
                         "[DISABLE]\n"
                         "unregistersymbol base")

    def test_program_backing_renders_operations_and_capabilities(self):
        self.assertEqual(entry_actions(_program_entry()),
                         "[ENABLE]\n"
                         "aobscan base module=$process pattern=48 8B 05 01 02 03 04\n"
                         "registersymbol synAOB0121\n"
                         "\n"
                         "[DISABLE]\n"
                         "unregistersymbol synAOB0121\n"
                         "Capabilities: aobscan, register, unregister")

    def test_lua_backing_lists_static_ops_and_lua_apis(self):
        text = entry_actions(_lua_entry())
        self.assertTrue(text.startswith("[ENABLE]\nregistersymbol base"), text)
        self.assertTrue("\n[DISABLE]\nunregistersymbol base\n" in text, text)
        self.assertIn("Lua APIs used: autoAssemble, createStringList, "
                      "getAddressSafe, unregisterSymbol, writeInteger",
                      text)

    def test_global_program_backing_counts_allocations(self):
        entry = {"id": 4, "label": "Global Alloc", "kind": "script",
                 "supported": True,
                 "global_program": {"source": "[GLOBAL]\nglobalalloc(g,16)",
                                    "globals": [{"name": "g"}]}}
        self.assertEqual(entry_actions(entry),
                         "Global allocation program: 1 global allocation(s)")

    def test_value_entry_with_address_and_hex(self):
        self.assertEqual(entry_actions(_value_entry()),
                         "Write 4 Bytes to Game.exe+1234 on Apply\n"
                         "Display: hex")

    def test_value_entry_without_address(self):
        entry = _value_entry()
        entry["address"] = None
        entry["show_as_hex"] = False
        self.assertEqual(entry_actions(entry),
                         "Write 4 Bytes on Apply")

    def test_heading_with_parent_activation(self):
        entry = {"id": 9000000, "label": "Group", "kind": "heading",
                 "supported": True, "parent_activation": {"ids": [1, 2]}}
        self.assertEqual(
            entry_actions(entry),
            "Group toggle: runs the parent-activation cascade on toggle")

    def test_plain_heading_has_no_action(self):
        entry = {"id": 1, "label": "Section", "kind": "heading",
                 "supported": True}
        self.assertEqual(entry_actions(entry), "")

    def test_blocked_script_has_no_action(self):
        entry = {"id": 2, "label": "Blocked One", "kind": "script",
                 "supported": False, "reason": "boom"}
        self.assertEqual(entry_actions(entry), "")


class RowDetailsTests(unittest.TestCase):
    def test_program_entry_full_content(self):
        entry = _program_entry()
        entries = {121: entry}
        details = row_details(entry, entries, applied=frozenset({121}))
        self.assertEqual(
            details["title"], "Row details - Syn01 Item 121 (id 121)")
        self.assertEqual(details["script"]["title"],
                         "Script preview - Syn01 Item 121 (id 121) - "
                         "Auto Assembler 64-bit")
        self.assertEqual(details["script"]["body"],
                         "[ENABLE]\nalloc(synCave0121,64)\n[DISABLE]\n"
                         "dealloc(synCave0121)")
        self.assertEqual(details["assessment"],
                         entry_assessment(entry, entries,
                                          applied=frozenset({121})))
        self.assertEqual(details["actions"], entry_actions(entry))

    def test_blocked_entry_has_no_script_and_no_actions(self):
        entry = {"id": 3, "label": "Blocked One", "kind": "script",
                 "supported": False, "selected": True,
                 "reason": "Native assembly: Line 3: unknown symbol."}
        details = row_details(entry, {3: entry})
        self.assertEqual(details["title"],
                         "Row details - Blocked One (id 3)")
        self.assertIsNone(details["script"])
        self.assertEqual(details["actions"], "")
        self.assertIn("Status: blocked (converter refused this record)",
                      details["assessment"])
        self.assertIn("Reason: Native assembly: Line 3: unknown symbol.",
                      details["assessment"])

    def test_value_entry_script_is_none(self):
        entry = _value_entry()
        details = row_details(entry, {3: entry})
        self.assertIsNone(details["script"])
        self.assertEqual(details["actions"],
                         "Write 4 Bytes to Game.exe+1234 on Apply\n"
                         "Display: hex")

    def test_error_is_forwarded_to_assessment(self):
        entry = _value_entry()
        details = row_details(entry, {3: entry},
                              error="Write failed: access denied")
        self.assertIn("Last error: Write failed: access denied",
                      details["assessment"])


def _window_stub(root, entry):
    """TrainerWindow without __init__ (house test style, see
    test_native_ui_button.py): enough state for the context-menu helpers."""
    window = TrainerWindow.__new__(TrainerWindow)
    window.root = root
    window.engine = types.SimpleNamespace(
        entries={entry["id"]: entry}, applied=frozenset(), entry_errors={})
    window._status_text = tk.StringVar(value="")
    return window


def _scrolled_texts(parent):
    """ScrolledText widgets in creation order.

    In this Python build ``scrolledtext.ScrolledText`` is a Text subclass
    that installs itself inside its own wrapper Frame, so the direct
    children of the section frame are Labels + wrapper Frames; the
    ScrolledText widgets live one level down (inside each wrapper Frame,
    next to its Scrollbar).
    """
    found = []
    for child in parent.winfo_children():
        for grandchild in child.winfo_children():
            if isinstance(grandchild, scrolledtext.ScrolledText):
                found.append(grandchild)
    return found


@unittest.skipUnless(tk is not None, 'tkinter required for real widget construction')
class RowDetailsWiringTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()

    def tearDown(self):
        self.root.destroy()

    def test_menu_items_lead_with_row_details(self):
        window = _window_stub(self.root, _program_entry())
        labels = [label for label, _ in
                  window._context_menu_items(_program_entry())]
        self.assertEqual(labels, ["Row details", "Script preview",
                                  "Copy script text",
                                  "What is happening here", "Details"])

    def test_menu_items_without_script_skip_preview_and_copy(self):
        window = _window_stub(self.root, _value_entry())
        labels = [label for label, _ in
                  window._context_menu_items(_value_entry())]
        self.assertEqual(labels, ["Row details", "What is happening here",
                                  "Details"])

    def test_show_row_details_builds_toplevel_with_builder_content(self):
        entry = _lua_entry()
        window = _window_stub(self.root, entry)
        window.show_row_details(entry)
        toplevels = [child for child in self.root.winfo_children()
                     if isinstance(child, tk.Toplevel)]
        self.assertEqual(len(toplevels), 1)
        toplevel = toplevels[0]
        self.assertEqual(toplevel.title(), "Row details - Lua Cheat (id 9)")
        # Script section carries the raw source, actions section the
        # extracted CE APIs.  Note: this Python's ScrolledText is a Text
        # subclass that installs itself inside its own wrapper Frame, so
        # the direct children of ``outer`` are Labels + wrapper Frames and
        # the ScrolledText widgets live one level down.
        widgets = toplevel.winfo_children()
        outer = [w for w in widgets if type(w).__name__ == "Frame"][0]
        labels = [w.cget("text") for w in outer.winfo_children()
                  if isinstance(w, tk.Label)]
        self.assertEqual(labels, ["Script (raw source)",
                                  "What it does / what is known",
                                  "Actions used"])
        texts = _scrolled_texts(outer)
        self.assertEqual(len(texts), 3)
        self.assertIn("getAddressSafe", texts[0].get("1.0", "end"))
        self.assertIn("Status: supported", texts[1].get("1.0", "end"))
        self.assertIn("Lua APIs used:", texts[2].get("1.0", "end"))
        toplevel.destroy()

    def test_show_row_details_without_script_uses_placeholder(self):
        entry = _value_entry()
        window = _window_stub(self.root, entry)
        window.show_row_details(entry)
        toplevel = [child for child in self.root.winfo_children()
                    if isinstance(child, tk.Toplevel)][0]
        outer = [w for w in toplevel.winfo_children()
                 if isinstance(w, tk.Frame)][0]
        labels = [w.cget("text") for w in outer.winfo_children()
                  if isinstance(w, tk.Label)]
        self.assertTrue(any("no executable source" in str(label)
                            for label in labels), labels)
        texts = _scrolled_texts(outer)
        self.assertEqual(len(texts), 2)
        self.assertIn("Status: supported", texts[0].get("1.0", "end"))
        self.assertIn("Write 4 Bytes to Game.exe+1234 on Apply",
                      texts[1].get("1.0", "end"))
        toplevel.destroy()


if __name__ == "__main__":
    unittest.main()
