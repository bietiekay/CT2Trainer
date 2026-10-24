"""Pure contract tests for the trainer row context-menu builders.

Covers ``ui_script_view``: script backing detection, the script preview
(raw Auto Assembler / embedded Lua / global program source, or the
rendered operation list) and the plain-language entry assessment used by
the row context menu (right-click / long-press).
"""
from __future__ import annotations

import unittest


from ct2trainer.native.ui_script_view import (
    entry_assessment,
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
                {"op": "alloc"},
                {"op": "scan_process"},
                {"op": "register"},
                {"op": "instruction"},
            ],
            "disable": [{"op": "dealloc"}, {"op": "unregister"}],
            "capabilities": ["alloc", "aobscan", "register", "instruction",
                             "dealloc", "unregister"],
        },
    }


def _entries_with_relations():
    entries = {121: _program_entry()}
    entries[7] = {"id": 7, "label": "Dep 7", "kind": "script",
                  "supported": True, "selected": True}
    entries[2] = {"id": 2, "label": "Consumer", "kind": "script",
                  "supported": True, "selected": True,
                  "requires": ["synaob0121"]}
    return entries


class ScriptBackingTests(unittest.TestCase):
    def test_program_backing(self):
        self.assertEqual(script_backing(_program_entry()), "program")

    def test_lua_backing(self):
        entry = {"id": 1, "kind": "script",
                 "lua_program": {"source": "registerSymbol('a')"}}
        self.assertEqual(script_backing(entry), "lua_program")

    def test_global_program_backing(self):
        entry = {"id": 1, "kind": "script",
                 "global_program": {"source": "[GLOBAL]\nglobalalloc(g,16)"}}
        self.assertEqual(script_backing(entry), "global_program")

    def test_operations_backing(self):
        entry = {"id": 1, "kind": "script",
                 "enable": [{"op": "scan", "symbol": "s", "module": "$process",
                             "pattern": "48 8B"}],
                 "disable": []}
        self.assertEqual(script_backing(entry), "operations")

    def test_value_entry_has_no_backing(self):
        entry = {"id": 1, "kind": "value", "supported": True}
        self.assertIsNone(script_backing(entry))

    def test_blocked_script_has_no_backing(self):
        entry = {"id": 1, "kind": "script", "supported": False,
                 "reason": "Native assembly: Line 3: ..."}
        self.assertIsNone(script_backing(entry))

    def test_non_dict_is_none(self):
        self.assertIsNone(script_backing(None))
        self.assertIsNone(script_backing({"kind": "script"}))


class ScriptPreviewTests(unittest.TestCase):
    def test_program_preview_returns_raw_source(self):
        title, body = script_preview(_program_entry())
        self.assertEqual(
            title,
            "Script preview - Syn01 Item 121 (id 121) - Auto Assembler 64-bit")
        self.assertEqual(
            body,
            "[ENABLE]\nalloc(synCave0121,64)\n[DISABLE]\ndealloc(synCave0121)")

    def test_lua_preview_returns_raw_source(self):
        source = "[ENABLE]\nlua()\nregisterSymbol('a')\nend_lua\n[DISABLE]"
        entry = {"id": 9, "label": "Lua Cheat", "kind": "script",
                 "lua_program": {"source": source}}
        title, body = script_preview(entry)
        self.assertEqual(title,
                         "Script preview - Lua Cheat (id 9) - embedded Lua")
        self.assertEqual(body, source)

    def test_global_program_preview_returns_raw_source(self):
        source = "[GLOBAL]\nglobalalloc(g,16)"
        entry = {"id": 4, "label": "Global Alloc", "kind": "script",
                 "global_program": {"source": source, "globals": [{"name": "g"}]}}
        title, body = script_preview(entry)
        self.assertEqual(title,
                         "Script preview - Global Alloc (id 4) - global program")
        self.assertEqual(body, source)

    def test_operations_preview_renders_phases(self):
        entry = {
            "id": 56, "label": "Ops Entry", "kind": "script",
            "one_shot": True,
            "enable": [
                {"op": "scan", "symbol": "base", "module": "$process",
                 "pattern": "48 8B 05 01 02 03 04"},
                {"op": "define", "symbol": "addr", "expression": "base+10"},
                {"op": "write", "address": "addr", "bytes": "C3"},
                {"op": "register", "symbol": "base"},
            ],
            "disable": [{"op": "unregister", "symbol": "base"}],
        }
        title, body = script_preview(entry)
        self.assertEqual(title,
                         "Script preview - Ops Entry (id 56) - operation list")
        self.assertEqual(
            body,
            "[ENABLE]\n"
            "aobscan base module=$process pattern=48 8B 05 01 02 03 04\n"
            "define addr = base+10\n"
            "write addr = C3\n"
            "registersymbol base\n"
            "\n"
            "[DISABLE]\n"
            "unregistersymbol base")

    def test_one_shot_program_title_is_marked(self):
        entry = _program_entry()
        entry["one_shot"] = True
        entry["program"]["one_shot"] = True
        title, _ = script_preview(entry)
        self.assertTrue(title.endswith("-bit (one-shot)"), title)

    def test_preview_is_none_without_executable_source(self):
        entry = {"id": 1, "label": "Blocked", "kind": "script",
                 "supported": False, "reason": "boom", "enable": [],
                 "disable": []}
        self.assertIsNone(script_preview(entry))


class EntryAssessmentTests(unittest.TestCase):
    def test_supported_program_entry_assessment(self):
        text = entry_assessment(_program_entry(), _entries_with_relations())
        self.assertEqual(text, (
            "Syn01 Item 121 (id 121)\n"
            "SynT Group 001 / Syn01 Item 121\n"
            "\n"
            "Status: supported\n"
            "Program: static Auto Assembler (64-bit)\n"
            "Enable phase: 4 operation(s)\n"
            "Disable phase: 2 operation(s)\n"
            "Capabilities: alloc, aobscan, register, instruction, dealloc, "
            "unregister\n"
            "Provides: synAOB0121\n"
            "Requires: base_ptr\n"
            "Depends on: Dep 7\n"
            "Required by: Consumer\n"
            "Source hotkeys: 1\n"
            "Runtime verified: yes"))

    def test_staged_pending_names_providers(self):
        entry = _program_entry()
        entry["staged"] = {"provider_ids": [7],
                           "provider_labels": ["Provider Seven"]}
        text = entry_assessment(entry, _entries_with_relations())
        self.assertIn("Status: staged (pending - providers not active yet)",
                      text)
        self.assertIn("Staged: unlocks when active: Provider Seven", text)

    def test_staged_gate_satisfied_when_providers_applied(self):
        entry = _program_entry()
        entry["staged"] = {"provider_ids": [7],
                           "provider_labels": ["Provider Seven"]}
        text = entry_assessment(entry, _entries_with_relations(),
                                applied=frozenset({7}))
        self.assertIn("Status: staged (gate satisfied - providers active)",
                      text)

    def test_blocked_entry_carries_reason_and_no_program(self):
        entry = {"id": 3, "label": "Blocked One", "kind": "script",
                 "supported": False, "selected": True,
                 "reason": "Native assembly: Line 3: unknown symbol."}
        text = entry_assessment(entry, {3: entry})
        self.assertEqual(text, (
            "Blocked One (id 3)\n"
            "\n"
            "Status: blocked (converter refused this record)\n"
            "Reason: Native assembly: Line 3: unknown symbol.\n"
            "Program: none (record blocked; no executable source)\n"
            "Runtime verified: no"))

    def test_unselected_entry_is_reported(self):
        entry = _program_entry()
        entry["selected"] = False
        text = entry_assessment(entry, {121: entry})
        self.assertIn("Status: not selected (excluded from the trainer build)",
                      text)

    def test_last_error_line(self):
        text = entry_assessment(_program_entry(), _entries_with_relations(),
                                error="Write failed: access denied")
        lines = text.splitlines()
        self.assertEqual(lines[3], "Status: supported")
        self.assertEqual(lines[4], "Last error: Write failed: access denied")

    def test_value_entry_assessment(self):
        entry = {"id": 3, "label": "Health", "kind": "value",
                 "supported": True, "selected": True,
                 "variable_type": "4 Bytes", "show_as_hex": True,
                 "address": "Game.exe+1234"}
        text = entry_assessment(entry, {3: entry})
        self.assertEqual(text, (
            "Health (id 3)\n"
            "\n"
            "Status: supported\n"
            "Type: 4 Bytes\n"
            "Address: Game.exe+1234\n"
            "Display: hex"))

    def test_heading_assessment(self):
        entry = {"id": 9000000, "label": "Group", "kind": "heading",
                 "supported": True, "selected": True,
                 "parent_activation": {"ids": [1, 2]}}
        text = entry_assessment(entry, {9000000: entry})
        self.assertIn("Kind: group heading (no direct memory action)", text)
        self.assertIn("Group toggle: runs the parent-activation cascade on "
                      "toggle", text)

    def test_operation_entry_assessment_counts_phases(self):
        entry = {"id": 56, "label": "Ops", "kind": "script",
                 "supported": True, "selected": True, "one_shot": True,
                 "enable": [{"op": "write", "address": "a", "bytes": "C3"}],
                 "disable": []}
        text = entry_assessment(entry, {56: entry})
        self.assertIn("Program: operation list (1 enable / 0 disable "
                      "operation(s))", text)
        self.assertIn("One-shot: runs once on activation; no disable phase",
                      text)

    def test_activation_set_summary_is_included(self):
        entry = _program_entry()
        entry["activation_sets"] = {"enable": [2], "disable": [],
                                    "source": "lua-static-extract"}
        entries = _entries_with_relations()
        entries[2]["provides"] = []
        text = entry_assessment(entry, entries)
        self.assertIn("Activation set: Master toggle - apply: Consumer "
                      "(source: lua-static-extract)", text)


if __name__ == "__main__":
    unittest.main()
