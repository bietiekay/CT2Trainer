"""Independent grammar/compatibility and fail-closed compiler checks."""

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

from ct2trainer.native.aa import AAError, compile_script, expression_symbols, validate_expression
from ct2trainer.native.compiler import NativeCompileError, compile_table, validate_plan
from ct2trainer.native.engine import NativeRuntimeError, validate_plan as validate_runtime_plan
from ct2trainer.table import TableError, read_table


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/windows/fixture_target/fixture.ct"


def script_record(entry_id, script, label="Option", attributes=""):
    import xml.sax.saxutils
    return (f'<CheatEntry><ID>{entry_id}</ID><Description>{label}</Description>'
            '<VariableType>Auto Assembler Script</VariableType>'
            f'<AssemblerScript {attributes}>{xml.sax.saxutils.escape(script)}</AssemblerScript></CheatEntry>')


def value_record(entry_id, address="1000", extra="", value_type="4 Bytes"):
    return (f'<CheatEntry><ID>{entry_id}</ID><Description>Value {entry_id}</Description>'
            f'<VariableType>{value_type}</VariableType><Address>{address}</Address>{extra}</CheatEntry>')


def patch_script(enable="01", disable="00", address="Target.exe+10"):
    return f"[ENABLE]\nassert({address},{disable})\n{address}:\ndb {enable}\n[DISABLE]\nassert({address},{enable})\n{address}:\ndb {disable}"


class NativeCompilerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.table_path = Path(self.directory.name) / "sample.CT"

    def compile(self, body, selected_ids=None, sections=""):
        self.table_path.write_text('<CheatTable CheatEngineTableVersion="52"><CheatEntries>'
                                   + body + '</CheatEntries>' + sections + '</CheatTable>', encoding="utf-8")
        return compile_table(self.table_path, "Target.exe", selected_ids=selected_ids)

    def test_fixture_all_four_entries_compiled_with_actual_dependencies(self):
        before = FIXTURE.read_bytes()
        plan = compile_table(FIXTURE, "FixtureTarget.exe")
        self.assertEqual(plan["counts"], {"total": 4, "supported": 4, "actionable": 4, "blocked": 0, "headings": 0})
        anchor, pause, value, ticks = plan["entries"]
        self.assertEqual(anchor["provides"], ["FixtureAnchor"])
        self.assertEqual(pause["requires"], ["FixtureAnchor"])
        self.assertEqual(value["dependency_ids"], [0])
        self.assertEqual(ticks["dependency_ids"], [0])
        self.assertEqual(pause["enable"][-1], {"op": "write", "address": "FixtureAnchor+14", "bytes": "01000000"})
        self.assertEqual(plan["table_sha256"], sha256(before).hexdigest())
        self.assertEqual(FIXTURE.read_bytes(), before)

    def test_selecting_value_automatically_includes_symbol_provider(self):
        plan = compile_table(FIXTURE, "FixtureTarget.exe", selected_ids=[2])
        self.assertEqual(plan["selected_ids"], [0, 2])
        self.assertEqual(len(plan["entries"]), 4)
        self.assertEqual([entry["id"] for entry in plan["entries"] if entry["selected"]], [0, 2])

    def test_all_reference_rows_retained_including_blocked_records(self):
        corpus = ROOT / "TableReferences"
        if not corpus.exists():
            self.skipTest("The synthetic clean-room corpus is intentionally excluded from the Native source distribution.")
        paths = sorted(corpus.glob("*.ct"))
        self.assertEqual(len(paths), 18, "The repository compatibility corpus must retain all 18 case tables.")
        for path in paths:
            with self.subTest(path=path.name):
                plan = compile_table(path, "Target.exe")
                source = read_table(path)
                self.assertEqual([entry["id"] for entry in plan["entries"]], [entry.id for entry in source.entries])
                for entry in plan["entries"]:
                    if not entry["supported"]:
                        self.assertTrue(entry["reason"])
                        self.assertNotIn("enable", entry)
                        self.assertNotIn("disable", entry)

    def test_missing_provider_blocks_value_and_script_visibly(self):
        plan = self.compile(value_record(1, "Missing+10") + script_record(2, patch_script(address="Missing+20")))
        self.assertEqual(plan["counts"]["blocked"], 2)
        self.assertTrue(all("Required symbol" in entry["reason"] for entry in plan["entries"]))

    def test_ambiguous_providers_and_consumer_blocked(self):
        locator = "[ENABLE]\naobscanmodule(Anchor,Target.exe,54 46)\nregistersymbol(Anchor)\n[DISABLE]\nunregistersymbol(Anchor)"
        plan = self.compile(script_record(0, locator) + script_record(1, locator) + value_record(2, "Anchor+4"))
        self.assertEqual(plan["counts"]["blocked"], 3)
        self.assertIn("ambiguous", plan["entries"][0]["reason"])

    def test_provider_dependency_cycle_blocks_both_records(self):
        left = "[ENABLE]\ndefine(LeftSymbol,RightSymbol+10)\nregistersymbol(LeftSymbol)\n[DISABLE]\nunregistersymbol(LeftSymbol)"
        right = left.replace("LeftSymbol", "Temp").replace("RightSymbol", "LeftSymbol").replace("Temp", "RightSymbol")
        plan = self.compile(script_record(0, left) + script_record(1, right))
        self.assertEqual(plan["counts"]["blocked"], 2)
        self.assertTrue(all("cycle" in entry["reason"] for entry in plan["entries"]))

    def test_unsupported_script_never_returns_partial_operations(self):
        # WP-29: an allocation-only ENABLE is now a supported init profile, so
        # the genuinely empty ENABLE is the canonical unsupported-script case.
        plan = self.compile(script_record(1, "[ENABLE]\n[DISABLE]\n"))
        self.assertEqual(plan["entries"][0]["kind"], "blocked")
        self.assertIn("no executable patch or data", plan["entries"][0]["reason"])
        self.assertNotIn("enable", plan["entries"][0])

    def test_table_lua_is_not_executed_or_used_as_symbol_provider(self):
        plan = self.compile(value_record(0, "CreatedByLua"), sections='<LuaScript>raise_error_if_executed()</LuaScript>')
        self.assertFalse(plan["entries"][0]["supported"])
        self.assertEqual(plan['lua_bootstrap']['source'], 'raise_error_if_executed()')
        self.assertTrue(any("not executed" in warning for warning in plan["warnings"]))

    def test_owned_lua_profile_is_prepared_without_execution_or_assembly(self):
        source = "[ENABLE]\n{$lua}\nerror('conversion must not execute this')\n{$asm}\n" + patch_script().split("[ENABLE]\n", 1)[1]
        with patch("ct2trainer.native.lua_host.LuaHost.execute", side_effect=AssertionError("Lua executed")), \
                patch("ct2trainer.native.assembler.NasmAssembler.assemble", side_effect=AssertionError("assembler executed")):
            entry = self.compile(script_record(0, source))["entries"][0]
            validate_plan(self.compile(script_record(0, source)))
        self.assertTrue(entry["supported"], entry["reason"])
        self.assertNotIn("program", entry)
        self.assertEqual(entry["enable"], [])
        self.assertEqual(entry["disable"], [])
        self.assertEqual(entry["lua_program"]["source"], source)
        self.assertEqual(entry["lua_program"]["source_sha256"], sha256(source.encode()).hexdigest())
        self.assertIsNotNone(entry["lua_program"]["static_program"])

    def test_lua_registered_symbol_is_a_static_provider(self):
        # WP-14: a Lua record that proves via static literals that it
        # registers a symbol on enable and unregisters it on disable
        # claims that symbol (the PRAGMATA registration pattern).
        source = "[ENABLE]\n{$lua}\nregisterSymbol('DynamicOnly',0x1000)\n{$asm}\n[DISABLE]\n{$lua}\nunregisterSymbol('DynamicOnly')\n{$asm}"
        plan = self.compile(script_record(0, source) + value_record(1, "DynamicOnly"))
        entry, consumer = plan["entries"]
        self.assertTrue(entry["supported"], entry["reason"])
        self.assertIsNone(entry["lua_program"]["static_program"])
        self.assertEqual(entry["provides"], ["DynamicOnly"])
        self.assertEqual(entry["requires"], [])
        self.assertTrue(consumer["supported"], consumer["reason"])
        self.assertEqual(consumer["dependency_ids"], [0])
        self.assertEqual(consumer["staged"],
                         {"provider_ids": [0], "provider_labels": [entry["label"]]})

    def test_lua_registration_without_unregister_is_not_a_static_provider(self):
        source = "[ENABLE]\n{$lua}\nregisterSymbol('NoRelease',0x1000)\n{$asm}\n[DISABLE]\n{$lua}\n{$asm}"
        plan = self.compile(script_record(0, source) + value_record(1, "NoRelease"))
        entry, consumer = plan["entries"]
        self.assertTrue(entry["supported"], entry["reason"])
        self.assertEqual(entry["provides"], [])
        self.assertFalse(consumer["supported"])
        self.assertIn("NoRelease", consumer["reason"])

    def test_lua_static_dependencies_preserve_selected_provider_closure(self):
        locator = "[ENABLE]\naobscanmodule(Anchor,Target.exe,54 46)\nregistersymbol(Anchor)\n[DISABLE]\nunregistersymbol(Anchor)"
        source = "[ENABLE]\n{$lua}\nerror('not during conversion')\n{$asm}\nalloc(data,100,Anchor)\ndata:\ndq 0\nregistersymbol(data)\n[DISABLE]\nunregistersymbol(data)\ndealloc(data)"
        plan = self.compile(script_record(0, locator) + script_record(1, source) + value_record(2, "data+8"), selected_ids=[2])
        self.assertEqual(plan["selected_ids"], [0, 1, 2])
        self.assertTrue(all(entry["supported"] for entry in plan["entries"]))
        self.assertEqual(plan["entries"][1]["requires"], ["Anchor"])
        self.assertEqual(plan["entries"][1]["provides"], ["data"])
        self.assertEqual(plan["entries"][1]["dependency_ids"], [0])
        self.assertEqual(plan["entries"][2]["dependency_ids"], [1])
        validate_runtime_plan(plan)

    def test_missing_lua_static_provider_removes_all_activation_profiles(self):
        source = "[ENABLE]\n{$lua}\nreturn nil\n{$asm}\nalloc(data,100,Missing)\ndata:\ndq 0\nregistersymbol(data)\n[DISABLE]\nunregistersymbol(data)\ndealloc(data)"
        entry = self.compile(script_record(0, source))["entries"][0]
        self.assertFalse(entry["supported"])
        self.assertIn("Missing", entry["reason"])
        for field in ("program", "lua_program", "enable", "disable"):
            self.assertNotIn(field, entry)
        self.assertEqual(entry["provides"], [])

    def test_async_lua_record_is_accepted_with_async_marker(self):
        source = "[ENABLE]\n{$lua}\nreturn nil\n{$asm}\n[DISABLE]"
        entry = self.compile(script_record(0, source, attributes='Async="1"'))["entries"][0]
        self.assertTrue(entry["supported"], entry["reason"])
        self.assertTrue(entry["async"])
        self.assertIn("lua_program", entry)
        self.assertIn("Async activation", entry["reason"])

    def test_sync_lua_record_has_no_async_marker(self):
        source = "[ENABLE]\n{$lua}\nreturn nil\n{$asm}\n[DISABLE]"
        entry = self.compile(script_record(0, source))["entries"][0]
        self.assertTrue(entry["supported"], entry["reason"])
        self.assertNotIn("async", entry)

    def test_unsupported_lua_static_envelope_and_malformed_chunks_stay_visible(self):
        sources = (
            "[ENABLE]\n{$lua}\nreturn nil\n{$asm}\ncreatethread(Target.exe)\n[DISABLE]",
            "[ENABLE]\n{$lua}\nlocal text = [[unterminated\n{$asm}\n[DISABLE]",
            "[ENABLE]\n{$lua} return nil\n[DISABLE]",
        )
        for source in sources:
            with self.subTest(source=source):
                entry = self.compile(script_record(0, source))["entries"][0]
                self.assertFalse(entry["supported"])
                self.assertTrue(entry["reason"])
                for field in ("program", "lua_program", "enable", "disable"):
                    self.assertNotIn(field, entry)

    def test_inert_lua_markers_in_comments_do_not_select_lua_execution_profile(self):
        comments = "/*\n{$lua}\n*/\n// {$lua}\n"
        with patch("ct2trainer.native.compiler.prepare_lua_program", side_effect=AssertionError("inert marker routed to Lua")):
            entry = self.compile(script_record(0, comments + patch_script()))["entries"][0]
        self.assertTrue(entry["supported"], entry["reason"])
        self.assertNotIn("lua_program", entry)

    def test_single_line_lua_call_routes_to_owned_profile_without_running_source(self):
        source = "[ENABLE]\nLuaCall(error('must not run during conversion'))\n" + patch_script().split("[ENABLE]\n", 1)[1]
        with patch("ct2trainer.native.lua_host.LuaHost.execute", side_effect=AssertionError("conversion executed Lua")):
            plan = self.compile(script_record(0, source))
        entry = plan["entries"][0]
        self.assertTrue(entry["supported"], entry["reason"])
        self.assertEqual(entry["lua_program"]["source"], source)
        self.assertNotIn("LuaCall", entry["lua_program"]["static_source"])
        validate_plan(plan)
        validate_runtime_plan(plan)

    def test_lua_call_cannot_publish_partial_profile_from_an_injected_command(self):
        source = "[ENABLE]\nluaCall(return nil) Target.exe: db 01\n[DISABLE]"
        entry = self.compile(script_record(0, source))["entries"][0]
        self.assertFalse(entry["supported"])
        self.assertIn("own AA command line", entry["reason"])
        self.assertNotIn("lua_program", entry)
        self.assertNotIn("enable", entry)

    def test_serialized_lua_profile_cannot_change_source_or_activation_metadata(self):
        source = "[ENABLE]\n{$lua}\nreturn nil\n{$asm}\n" + patch_script().split("[ENABLE]\n", 1)[1]
        plan = self.compile(script_record(0, source))
        validate_plan(plan)
        validate_runtime_plan(plan)
        mutations = (
            lambda entry: entry["lua_program"].update(source=source.replace("nil", "'db 02'")),
            lambda entry: entry["lua_program"].update(source_sha256="0" * 64),
            lambda entry: entry["lua_program"].update(process_name="Other.exe"),
            lambda entry: entry.update(requires=["Missing"]),
            lambda entry: entry.update(provides=["Forged"]),
            lambda entry: entry.update(program=entry["lua_program"]["static_program"]),
            lambda entry: entry.update(enable=[{"op": "write", "address": "1000", "bytes": "01"}]),
            lambda entry: entry.update(disable=None),
            lambda entry: entry.pop("enable"),
            lambda entry: entry.update(enable={}),
            lambda entry: entry.update(kind="value"),
            lambda entry: entry.update(kind="blocked", supported=False),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index):
                invalid = deepcopy(plan)
                mutate(invalid["entries"][0])
                with self.assertRaises(NativeCompileError):
                    validate_plan(invalid)
                with self.assertRaises(NativeRuntimeError):
                    validate_runtime_plan(invalid)

    def test_parent_recursive_write_carries_deterministic_closure_metadata(self):
        # The legacy fail-closed block was replaced: moRecursiveSetValue
        # parents compile like ordinary value records and carry their
        # deepest-first write closure as byte-verifiable plan metadata.
        body = '<CheatEntry><ID>0</ID><Description>Parent</Description><VariableType>4 Bytes</VariableType><Address>1000</Address><Options moRecursiveSetValue="1"/><CheatEntries>' + value_record(1) + '</CheatEntries></CheatEntry>'
        plan = self.compile(body)
        self.assertTrue(plan["entries"][0]["supported"])
        self.assertEqual(plan["entries"][0]["recursive_value"], {"write_ids": [1, 0]})
        self.assertTrue(plan["entries"][1]["supported"])
        self.assertNotIn("recursive_value", plan["entries"][1])

    def test_heading_has_no_executable_group_action(self):
        body = '<CheatEntry><ID>0</ID><Description>Parent</Description><GroupHeader>1</GroupHeader><Options moActivateChildrenAsWell="1"/><CheatEntries>' + value_record(1) + '</CheatEntries></CheatEntry>'
        plan = self.compile(body, selected_ids=[1])
        self.assertEqual(plan["entries"][0]["kind"], "heading")
        self.assertNotIn("enable", plan["entries"][0])
        self.assertEqual(plan["selected_ids"], [0, 1])

    def test_pointer_offsets_are_hex_and_preserve_xml_order(self):
        plan = self.compile(value_record(1, extra='<Offsets><Offset>10</Offset><Offset>-8</Offset></Offsets>'))
        self.assertEqual(plan["entries"][0]["pointer_offsets"], [16, -8])

    def test_signed_pointer_offset_literals_are_accepted(self):
        plan = self.compile(value_record(1, extra='<Offsets><Offset>+28</Offset><Offset>-0x10</Offset><Offset>+0x28</Offset></Offsets>'))
        self.assertEqual(plan["entries"][0]["pointer_offsets"], [0x28, -16, 0x28])

    def test_malformed_pointer_offset_literals_stay_rejected(self):
        for text in ("++10", "+", "0x", "", "10-", "x1", "1 0"):
            with self.subTest(offset=text):
                plan = self.compile(value_record(1, extra=f'<Offsets><Offset>{text}</Offset></Offsets>'))
                entry = plan["entries"][0]
                self.assertFalse(entry["supported"], entry["reason"])
                self.assertIn("Pointer offset must be a hexadecimal integer literal.", entry["reason"])

    def test_pointer_offset_constant_folding_accepts_corpus_forms(self):
        # WP-21: constant hexadecimal arithmetic in pointer-chase slots is
        # folded to one int64 offset.  Precedence is the usual one ('*'
        # before '+'/'-'); a leading sign binds to the first term; balanced
        # non-nested parenthesized annotations are stripped before eval.
        cases = (
            ("13A8+118", 0x13A8 + 0x118),
            # The plan case table on this base quotes "1594+8+118 -> 0x164C";
            # the exact arithmetic is 0x1594 + 8 + 0x118 = 5812 = 0x16B4
            # (flagged in the lane report; the plan document itself is
            # intentionally untouched by this lane).
            ("1594+8+118", 0x1594 + 8 + 0x118),
            ("A0+4*4", 0xA0 + 4 * 4),
            ("433c+10c*4", 0x433C + 0x10C * 4),
            ("30+30+30+30", 0x30 * 4),
            ("0x10+0x2", 0x12),
            ("20 (Offset of the name pointer)", 0x20),
            ("-13A8+118", -0x13A8 + 0x118),
            ("+10", 0x10),
        )
        for text, expected in cases:
            with self.subTest(offset=text):
                plan = self.compile(value_record(1, extra=f'<Offsets><Offset>{text}</Offset></Offsets>'))
                entry = plan["entries"][0]
                self.assertTrue(entry["supported"], entry["reason"])
                self.assertEqual(entry["pointer_offsets"], [expected])
                validate_plan(plan)
                validate_runtime_plan(plan)

    def test_pointer_offset_malformed_forms_stay_rejected_with_the_literal_reason(self):
        for text in ("base+10", "GameEngine.GameInstance", "20 ()", "20 (unclosed",
                     "(dword)[sym+B8]*4", "[sym+3]++14", "(10)(20)"):
            with self.subTest(offset=text):
                plan = self.compile(value_record(1, extra=f'<Offsets><Offset>{text}</Offset></Offsets>'))
                entry = plan["entries"][0]
                self.assertFalse(entry["supported"], "expected rejection: " + entry["reason"])
                self.assertEqual(entry["reason"], "Pointer offset must be a hexadecimal integer literal.")

    def test_pointer_offset_overflow_and_chain_limit_stay_rejected(self):
        overflow = self.compile(value_record(1, extra='<Offsets><Offset>FFFFFFFFFFFFFFFFFFF+1</Offset></Offsets>'))
        self.assertFalse(overflow["entries"][0]["supported"])
        self.assertEqual(overflow["entries"][0]["reason"], "Pointer offset exceeds signed 64 bits.")
        offsets = "".join("<Offset>10</Offset>" for _ in range(33))
        plan = self.compile(value_record(1, extra=f"<Offsets>{offsets}</Offsets>"))
        self.assertFalse(plan["entries"][0]["supported"])
        self.assertEqual(plan["entries"][0]["reason"], "Pointer chains are limited to 32 offsets.")

    def test_process_aob_scan_module_passes_both_plan_validators(self):
        # WP-19: the $process token names the main module of the attached
        # process; the runtime maps it to the plan's process_name, so the
        # module-basename grammar must not apply to it in either validator.
        script = ("[ENABLE]\naobscanmodule(scan_sym, $process, 89 48 08)\n"
                  "scan_sym:\nassert(scan_sym, 89 48 08)\ndb 90\n"
                  "[DISABLE]\nscan_sym:\nassert(scan_sym, 90)\ndb 89\n")
        plan = self.compile(script_record(0, script))
        entry = plan["entries"][0]
        self.assertTrue(entry["supported"], entry["reason"])
        self.assertEqual(entry["enable"][0],
                         {"op": "scan", "symbol": "scan_sym",
                          "module": "$process", "pattern": "89 48 08"})
        validate_plan(plan)
        validate_runtime_plan(plan)

    def test_forged_scan_modules_are_rejected_by_both_plan_validators(self):
        script = ("[ENABLE]\naobscanmodule(scan_sym, $process, 89 48 08)\n"
                  "scan_sym:\nassert(scan_sym, 89 48 08)\ndb 90\n"
                  "[DISABLE]\nscan_sym:\nassert(scan_sym, 90)\ndb 89\n")
        plan = self.compile(script_record(0, script))
        for module in ('C:\\x\\y.exe', "$PROCESS", "owned.exe+10"):
            with self.subTest(module=module):
                forged = deepcopy(plan)
                for entry in forged["entries"]:
                    for phase in ("enable", "disable"):
                        for op in entry.get(phase, ()):
                            if op.get("op") == "scan":
                                op["module"] = module
                with self.assertRaises(NativeCompileError):
                    validate_plan(deepcopy(forged))
                with self.assertRaises(NativeRuntimeError):
                    validate_runtime_plan(deepcopy(forged))

    def test_table_reader_warnings_are_forwarded_into_the_plan(self):
        # WP-25 follow-up (a): table-reader warnings are forwarded into the
        # plan, followed by the compile-level warnings in document order.
        plan = self.compile(value_record(0, "CreatedByLua"),
                            sections='<LuaScript>local x = 1</LuaScript>')
        self.assertIn("Table Lua can run when Cheat Engine loads the table.", plan["warnings"])
        self.assertIn("Table Lua is not executed on load. Read-only helpers replay in each Lua activation; top-level writes, callbacks and unsupported APIs block activation.", plan["warnings"])
        # The compile helper pins CheatEngineTableVersion 52, which is newer
        # than the local CE reference (45), so the reader's version warning
        # must be forwarded as well.
        self.assertIn("Table version 52 is newer than the local CE reference (45); CE loading is unverified.", plan["warnings"])

    def test_entry_node_maps_resolve_duplicate_ids_keep_first(self):
        # WP-25 follow-up (b): duplicate IDs resolve keep-first, so the body
        # of the kept (first) record is the one that gets compiled.
        root = ET.fromstring(
            "<CheatEntries>"
            '<CheatEntry><ID>7</ID><Description>First</Description>'
            '<VariableType>Auto Assembler Script</VariableType>'
            '<AssemblerScript>FIRST</AssemblerScript></CheatEntry>'
            '<CheatEntry><ID>7</ID><Description>Duplicate</Description>'
            '<VariableType>Auto Assembler Script</VariableType>'
            '<AssemblerScript>SECOND</AssemblerScript></CheatEntry>'
            '<CheatEntry><ID>9</ID><Description>Unique</Description>'
            '<VariableType>Auto Assembler Script</VariableType>'
            '<AssemblerScript>UNIQUE</AssemblerScript></CheatEntry>'
            "</CheatEntries>")
        from ct2trainer.native.compiler import _entry_node_maps
        nodes, scripts = _entry_node_maps(root)
        self.assertEqual(set(nodes), {7, 9})
        self.assertEqual(nodes[7].findtext("Description"), "First")
        self.assertEqual(scripts[7], "FIRST")
        self.assertEqual(scripts[9], "UNIQUE")

    def test_staged_marker_derives_from_supported_symbol_providers(self):
        plan = compile_table(FIXTURE, "FixtureTarget.exe")
        anchor, pause, value, ticks = plan["entries"]
        self.assertNotIn("staged", anchor)
        for entry in (pause, value, ticks):
            self.assertEqual(entry.get("staged"),
                             {"provider_ids": [0],
                              "provider_labels": ["Locate fixture data (enable first)"]})

    def test_advanced_types_malformed_pointer_blocked_hex_float_supported(self):
        # WP-33: the ShowAsHex Float record is now a supported raw bit-pattern
        # value; only the custom type and the malformed pointer offset stay
        # blocked.
        body = value_record(0, value_type="Custom") + value_record(1, extra='<Offsets><Offset>print(1)</Offset></Offsets>') + value_record(2, value_type="Float", extra='<ShowAsHex>1</ShowAsHex>')
        plan = self.compile(body)
        self.assertEqual(plan["counts"]["blocked"], 2)
        hex_float = plan["entries"][2]
        self.assertTrue(hex_float["supported"], hex_float["reason"])
        self.assertEqual(hex_float["kind"], "value")
        self.assertTrue(hex_float["show_as_hex"])
        validate_plan(plan)
        validate_runtime_plan(plan)

    def test_custom_type_reasons_cite_the_ap_08_7_write_gate(self):
        # WP-34 (FLAG-2 follow-up 3): the custom-type block reasons cite the
        # write gate's current AP id (AP-08.7).
        custom_types = ('<CustomTypes><CustomType name="KnownType">4</CustomType>'
                        '</CustomTypes>')
        known = self.compile(
            value_record(0, value_type="Custom",
                         extra='<CustomType>KnownType</CustomType>'),
            sections=custom_types)["entries"][0]
        self.assertFalse(known["supported"])
        self.assertEqual(known["reason"],
            "Custom value type 'KnownType' is statically defined; the native "
            "converter write gate is not implemented yet (AP-08.7).")
        unknown = self.compile(
            value_record(0, value_type="Custom",
                         extra='<CustomType>GhostType</CustomType>'),
            sections=custom_types)["entries"][0]
        self.assertFalse(unknown["supported"])
        self.assertEqual(unknown["reason"],
            "Custom value type 'GhostType' has no static definition; blocked "
            "until a converter/write gate exists (AP-08.7).")

    def test_empty_and_expression_readonly_dropdown_blocked(self):
        body = value_record(0, extra='<DropDownList ReadOnly="1">*:None</DropDownList>') + value_record(1, extra='<DropDownList ReadOnly="1">1+2:Expression</DropDownList>')
        self.assertEqual(self.compile(body)["counts"]["blocked"], 2)

    def test_safe_dropdown_choices_preserve_value_and_description(self):
        plan = self.compile(value_record(0, extra='<DropDownList ReadOnly="1">*:Placeholder\n1:One\n2:Two</DropDownList>'))
        self.assertEqual(plan["entries"][0]["dropdown"], {"read_only": True, "choices": [{"value": "1", "description": "One"}, {"value": "2", "description": "Two"}]})

    def test_native_dropdown_range_and_signed_defaults(self):
        body = value_record(0, value_type="Byte", extra='<DropDownList>256:Overflow</DropDownList>') + value_record(1, extra='<DropDownList>-1:Negative without signed</DropDownList>') + value_record(2, extra='<ShowAsSigned>1</ShowAsSigned><DropDownList>-1:Signed</DropDownList>') + value_record(3, extra='<ShowAsSigned>1</ShowAsSigned><ShowAsHex>1</ShowAsHex><DropDownList>-1:Negative hex</DropDownList>')
        plan = self.compile(body)
        self.assertEqual([entry["supported"] for entry in plan["entries"]], [False, False, True, False])
        self.assertEqual(plan["numeric_policy"]["hexadecimal"], "unsigned-bit-pattern")

    def test_byte_arrays_and_binary_fields_compile_explicit_value_profiles(self):
        body = (value_record(0, value_type="Array of byte", extra='<ByteLength>3</ByteLength><ShowAsHex>1</ShowAsHex><ShowAsSigned>1</ShowAsSigned>')
                + value_record(1, value_type="Binary", extra='<BitStart>7</BitStart><BitLength>64</BitLength><ShowAsBinary>1</ShowAsBinary>'))
        plan = self.compile(body)
        array, binary = plan["entries"]
        self.assertEqual(plan["counts"]["actionable"], 2)
        self.assertEqual([entry["kind"] for entry in plan["entries"]], ["value", "value"])
        self.assertEqual(array["value_profile"]["size"], 3)
        self.assertEqual(array["value_profile"]["display"], "hex_bytes")
        self.assertTrue(array["value_profile"]["properties"]["ShowAsSigned"])
        self.assertFalse(array["value_profile"]["signed"])
        self.assertEqual(binary["value_profile"]["size"], 9)
        self.assertEqual(binary["value_profile"]["properties"]["BitStart"], 7)
        self.assertEqual(binary["value_profile"]["display"], "binary")
        validate_plan(plan)

    def test_zero_array_is_navigation_and_retains_pointer_ancestry_for_children(self):
        provider = '[ENABLE]\ndefine(Anchor,Target.exe)\nregistersymbol(Anchor)\n[DISABLE]\nunregistersymbol(Anchor)'
        parent = value_record(1, "Anchor", value_type="Array of byte",
                              extra='<ByteLength>0</ByteLength><Offsets><Offset>10</Offset><Offset>0</Offset></Offsets>')
        parent = parent.removesuffix('</CheatEntry>') + '<CheatEntries>' + value_record(2, "+4") + '</CheatEntries></CheatEntry>'
        plan = self.compile(script_record(0, provider) + parent, selected_ids=[2])
        _, heading, child = plan["entries"]
        self.assertEqual(plan["selected_ids"], [0, 1, 2])
        self.assertEqual(heading["kind"], "heading")
        self.assertEqual(heading["source_kind"], "value")
        self.assertTrue(heading["supported"])
        self.assertEqual(heading["value_profile"]["size"], 0)
        self.assertFalse(heading["value_profile"]["actionable"])
        self.assertEqual(heading["source_address"], "Anchor")
        self.assertEqual(heading["pointer_offsets"], [16, 0])
        self.assertEqual(heading["requires"], ["Anchor"])
        self.assertEqual(heading["dependency_ids"], [])
        self.assertEqual(heading["dropdown"], {"choices": [], "read_only": False})
        self.assertEqual(child["address"], "([[Anchor]]+10)+4")
        self.assertEqual(child["address_profile"], "expression/v1")
        self.assertEqual(child["dependency_ids"], [0])
        self.assertEqual(plan["counts"], {"total": 3, "supported": 3, "actionable": 2, "blocked": 0, "headings": 1})

    def test_addressless_zero_array_navigates_without_an_invented_range(self):
        plan = self.compile(value_record(0, "", value_type="Array of byte", extra='<ByteLength>0</ByteLength>'))
        entry = plan["entries"][0]
        self.assertEqual(entry["kind"], "heading")
        self.assertTrue(entry["supported"])
        self.assertEqual(entry["address"], "")
        self.assertEqual(entry["value_profile"]["size"], 0)
        self.assertEqual(entry["pointer_offsets"], [])
        invalid = deepcopy(plan)
        invalid["entries"][0]["pointer_offsets"] = [0]
        with self.assertRaises(NativeCompileError):
            validate_plan(invalid)

    def test_value_profile_bounds_missing_properties_and_recursive_write_metadata(self):
        invalid = (
            ("Array of byte", ""),
            ("Array of byte", '<ByteLength>65537</ByteLength>'),
            ("Array of byte", '<ByteLength>-1</ByteLength>'),
            ("Binary", '<BitStart>8</BitStart><BitLength>1</BitLength>'),
            ("Binary", '<BitStart>0</BitStart><BitLength>0</BitLength>'),
            ("Binary", '<BitStart>0</BitStart><BitLength>1</BitLength><ShowAsBinary>2</ShowAsBinary>'),
            ("Binary", '<BitStart>0</BitStart><BitLength>1</BitLength><ShowAsBinary>1</ShowAsBinary><ShowAsHex>1</ShowAsHex>'),
        )
        for variable_type, properties in invalid:
            with self.subTest(variable_type=variable_type, properties=properties):
                entry = self.compile(value_record(0, value_type=variable_type, extra=properties))["entries"][0]
                self.assertFalse(entry["supported"])
                self.assertNotIn("value_profile", entry)
        # A moRecursiveSetValue flag on a non-actionable zero-length
        # placeholder stays a navigation heading without closure metadata;
        # the executable recursive path is no longer blocked at compile time.
        parent = value_record(0, value_type="Array of byte", extra='<ByteLength>0</ByteLength><Options moRecursiveSetValue="1"/>')
        parent = parent.removesuffix('</CheatEntry>') + '<CheatEntries>' + value_record(1, "+4") + '</CheatEntries></CheatEntry>'
        entry = self.compile(parent)["entries"][0]
        self.assertTrue(entry["supported"])
        self.assertEqual(entry["kind"], "heading")
        self.assertNotIn("recursive_value", entry)

    def test_profile_literal_dropdowns_keep_exact_source_text_and_display_mode(self):
        body = (value_record(0, value_type="Array of byte", extra='<ByteLength>2</ByteLength><DropDownList ReadOnly="1">*:Placeholder\n0a fF:Bytes</DropDownList>')
                + value_record(1, value_type="Binary", extra='<BitStart>2</BitStart><BitLength>3</BitLength><ShowAsBinary>1</ShowAsBinary><DropDownList>101:Five</DropDownList>')
                + value_record(2, value_type="Binary", extra='<BitStart>0</BitStart><BitLength>3</BitLength><ShowAsSigned>1</ShowAsSigned><DropDownList>-1:Negative</DropDownList>'))
        plan = self.compile(body)
        self.assertTrue(all(entry["supported"] for entry in plan["entries"]))
        self.assertEqual(plan["entries"][0]["dropdown"], {"choices": [{"value": "0a fF", "description": "Bytes"}], "read_only": True})
        self.assertEqual(plan["entries"][1]["dropdown"]["choices"][0]["value"], "101")
        self.assertEqual(plan["entries"][2]["dropdown"]["choices"][0]["value"], "-1")

    def test_profiles_refuse_linked_expression_wildcard_and_numeric_array_dropdowns(self):
        # WP-27: linked dropdowns work for profile value records; the last
        # case now refuses only because the borrowed choice (5) is outside
        # the linked bit field's range (WP-34 per-choice refusal).
        cases = (
            ("Array of byte", '<ByteLength>2</ByteLength><DropDownList>12:Number</DropDownList>'),
            ("Array of byte", '<ByteLength>2</ByteLength><DropDownList>01 ??:Wildcard</DropDownList>'),
            ("Array of byte", '<ByteLength>2</ByteLength><DropDownList>01 02+1:Expression</DropDownList>'),
            ("Array of byte", '<ByteLength>2</ByteLength><DropDownList ReadOnly="1">*:Placeholder</DropDownList>'),
            ("Binary", '<BitStart>0</BitStart><BitLength>2</BitLength><DropDownList>1+1:Expression</DropDownList>'),
            ("Binary", '<BitStart>0</BitStart><BitLength>2</BitLength><DropDownListLink>Value 1</DropDownListLink>'),
        )
        for variable_type, properties in cases:
            with self.subTest(variable_type=variable_type, properties=properties):
                entry = self.compile(value_record(0, value_type=variable_type, extra=properties) + value_record(1, extra='<DropDownList>5:Big</DropDownList>'))["entries"][0]
                self.assertFalse(entry["supported"])
                self.assertNotIn("value_profile", entry)

    def test_cross_record_dropdown_link_borrows_choices_and_records_target(self):
        body = (value_record(1, extra='<DropDownList>0:Off\n1:On\n2:Both</DropDownList>')
                + value_record(2, extra='<DropDownListLink>Value 1</DropDownListLink>'))
        plan = self.compile(body)
        self.assertTrue(all(entry["supported"] for entry in plan["entries"]))
        self.assertEqual(plan["entries"][1]["dropdown"],
                         {"choices": [{"value": "0", "description": "Off"},
                                      {"value": "1", "description": "On"},
                                      {"value": "2", "description": "Both"}],
                          "read_only": False, "link_target_id": 1})
        self.assertNotIn("link_target_id", plan["entries"][0]["dropdown"])
        validate_plan(plan)
        validate_runtime_plan(plan)

    def test_cross_record_dropdown_link_to_choiceless_group_is_explicit(self):
        # Pinned corpus shape (rml): the link target is a group header without
        # choices. The link stays explicit in the plan, choices remain empty,
        # and the record compiles as a free value record at its own address.
        body = ('<CheatEntry><ID>0</ID><Description>Achievement Related</Description>'
                '<GroupHeader>1</GroupHeader><Address>2000</Address><CheatEntries>'
                + value_record(1, address="+1", value_type="Byte",
                               extra='<DropDownListLink>Achievement Related</DropDownListLink>')
                + '</CheatEntries></CheatEntry>')
        plan = self.compile(body)
        entry = plan["entries"][1]
        self.assertTrue(entry["supported"])
        self.assertEqual(entry["dropdown"], {"choices": [], "read_only": False, "link_target_id": 0})
        self.assertEqual(entry["source_address"], "+1")
        self.assertEqual(entry["address"], "(2000)+1")
        validate_plan(plan)
        validate_runtime_plan(plan)

    def test_cross_record_dropdown_link_refuses_missing_ambiguous_and_chained_targets(self):
        missing = self.compile(value_record(0, extra='<DropDownListLink>Missing Target</DropDownListLink>'))["entries"][0]
        # WP-34 (FLAG-2 follow-up 1a): missing and ambiguous targets are
        # diagnosed with separate, exact messages.
        self.assertFalse(missing["supported"])
        self.assertEqual(missing["reason"],
                         "Dropdown link target is missing: 'Missing Target' matches no record label.")
        ambiguous = ('<CheatEntry><ID>0</ID><Description>Twin</Description><VariableType>4 Bytes</VariableType>'
                     '<Address>1000</Address><DropDownList>1:One</DropDownList></CheatEntry>'
                     + '<CheatEntry><ID>1</ID><Description>twin</Description><VariableType>4 Bytes</VariableType>'
                       '<Address>1001</Address><DropDownList>2:Two</DropDownList></CheatEntry>'
                     + value_record(2, extra='<DropDownListLink>TWIN</DropDownListLink>'))
        plan = self.compile(ambiguous)
        self.assertTrue(all(entry["supported"] for entry in plan["entries"][:2]))
        self.assertFalse(plan["entries"][2]["supported"])
        self.assertEqual(plan["entries"][2]["reason"],
                         "Dropdown link target is ambiguous: 'TWIN' matches 2 record labels.")
        chained = (value_record(0, extra='<DropDownList>1:One</DropDownList>')
                   + value_record(1, extra='<DropDownListLink>Value 0</DropDownListLink>')
                   + value_record(2, extra='<DropDownListLink>Value 1</DropDownListLink>'))
        plan = self.compile(chained)
        self.assertTrue(plan["entries"][1]["supported"])
        self.assertFalse(plan["entries"][2]["supported"])
        self.assertIn("Chained", plan["entries"][2]["reason"])

    def test_dropdown_link_metadata_rejects_forged_targets_in_serialized_plans(self):
        plan = self.compile(value_record(0, extra='<DropDownList>1:One</DropDownList>')
                            + value_record(1, extra='<DropDownListLink>Value 0</DropDownListLink>'))
        mutations = (
            lambda entry: entry["dropdown"].update(link_target_id=99),
            lambda entry: entry["dropdown"].update(link_target_id=1),
            lambda entry: entry["dropdown"].update(link_target_id=True),
        )
        for mutation in mutations:
            invalid = deepcopy(plan)
            mutation(invalid["entries"][1])
            with self.assertRaises(NativeCompileError):
                validate_plan(invalid)
            with self.assertRaises(NativeRuntimeError):
                validate_runtime_plan(invalid)

    def test_serialized_value_profiles_reject_forged_metadata_address_and_kind(self):
        plan = self.compile(value_record(0, value_type="Binary", extra='<BitStart>2</BitStart><BitLength>3</BitLength>'))
        mutations = (
            lambda entry: entry["value_profile"].update(size=4),
            lambda entry: entry["value_profile"].update(kind="byte_array"),
            lambda entry: entry["value_profile"].update(extra="ignored"),
            lambda entry: entry["value_profile"]["properties"].update(BitLength="3"),
            lambda entry: entry["value_profile"]["properties"].update(ShowAsHex=True),
            lambda entry: entry.update(show_as_hex=True),
            lambda entry: entry.update(show_as_signed=True),
            lambda entry: entry.update(variable_type="Byte"),
            lambda entry: entry.update(kind="heading"),
            lambda entry: entry.update(kind="blocked", supported=False),
            lambda entry: entry.update(kind="script", enable=[], disable=[]),
            lambda entry: entry.update(requires=["Hidden"]),
            lambda entry: entry.update(address="Hidden+4"),
            lambda entry: entry.update(enable=[]),
            lambda entry: entry.pop("value_profile"),
            lambda entry: entry.pop("source_address"),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index):
                invalid = deepcopy(plan)
                mutate(invalid["entries"][0])
                with self.assertRaises(NativeCompileError):
                    validate_plan(invalid)
        numeric = self.compile(value_record(0))
        numeric["entries"][0]["value_profile"] = plan["entries"][0]["value_profile"]
        with self.assertRaises(NativeCompileError):
            validate_plan(numeric)

    def test_zero_profile_heading_is_canonically_validated_without_actions(self):
        plan = self.compile(value_record(0, value_type="Array of byte", extra='<ByteLength>0</ByteLength>'))
        mutations = (
            lambda entry: entry.update(kind="value"),
            lambda entry: entry["value_profile"].update(size=1),
            lambda entry: entry.update(address="Hidden+4"),
            lambda entry: entry.update(requires=["Hidden"]),
            lambda entry: entry.update(enable=[]),
            lambda entry: entry.update(disable=[]),
            lambda entry: entry.update(dependency_ids=[0]),
            lambda entry: entry.update(dropdown={"choices": [{"value": "01", "description": "Byte"}], "read_only": False}),
            lambda entry: entry.update(reason="writable"),
            lambda entry: entry.pop("value_profile"),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index):
                invalid = deepcopy(plan)
                mutate(invalid["entries"][0])
                with self.assertRaises(NativeCompileError):
                    validate_plan(invalid)

    def test_missing_symbol_provider_removes_partial_profile(self):
        entry = self.compile(value_record(0, "Missing", value_type="Array of byte", extra='<ByteLength>1</ByteLength>'))["entries"][0]
        self.assertFalse(entry["supported"])
        self.assertIn("Required symbol", entry["reason"])
        self.assertNotIn("value_profile", entry)

    def test_dependency_depth_is_bounded_without_python_recursion(self):
        body = []
        for identifier in range(90):
            target = f"Symbol{identifier + 1}" if identifier < 89 else "Target.exe"
            script = f"[ENABLE]\ndefine(Symbol{identifier},{target})\nregistersymbol(Symbol{identifier})\n[DISABLE]\nunregistersymbol(Symbol{identifier})"
            body.append(script_record(identifier, script))
        plan = self.compile("".join(body))
        self.assertEqual(len(plan["entries"]), 90)
        self.assertFalse(plan["entries"][0]["supported"])
        self.assertTrue(any("64 levels" in entry["reason"] for entry in plan["entries"]))

    def test_dtd_is_rejected_by_shared_bounded_reader(self):
        self.table_path.write_text('<!DOCTYPE CheatTable [<!ENTITY x "x">]><CheatTable CheatEngineTableVersion="45"/>', encoding="utf-8")
        with self.assertRaises(TableError):
            compile_table(self.table_path, "Target.exe")

    def test_source_changed_between_metadata_and_script_extraction(self):
        self.compile(value_record(0))
        table = read_table(self.table_path)
        self.table_path.write_text('<CheatTable CheatEngineTableVersion="45"/>', encoding="utf-8")
        with patch("ct2trainer.native.compiler.read_table", return_value=table), self.assertRaisesRegex(NativeCompileError, "changed"):
            compile_table(self.table_path, "Target.exe")

    def test_process_and_selection_validation(self):
        for process in ("C:\\Target.exe", "../Target.exe", "Target", "Target.exe\n", "Target?.exe"):
            with self.subTest(process=process), self.assertRaises(NativeCompileError):
                compile_table(FIXTURE, process)
        with self.assertRaises(NativeCompileError):
            compile_table(FIXTURE, "Target.exe", selected_ids=[999])

    def test_serialized_plan_rejects_unknown_operation_and_unguarded_patch(self):
        plan = compile_table(FIXTURE, "FixtureTarget.exe")
        unknown = deepcopy(plan)
        unknown["entries"][1]["enable"].append({"op": "exec", "command": "bad"})
        with self.assertRaises(NativeCompileError):
            validate_plan(unknown)
        unguarded = deepcopy(plan)
        unguarded["entries"][1]["enable"].pop(0)
        with self.assertRaises(NativeCompileError):
            validate_plan(unguarded)

    def test_serialized_symbol_metadata_and_selection_cannot_hide_dependencies(self):
        plan = compile_table(FIXTURE, "FixtureTarget.exe")
        for mutate in (lambda value: value["entries"][1].update(requires=[]),
                       lambda value: value["entries"][0].update(provides=[]),
                       lambda value: value["entries"][2].update(selected=False)):
            invalid = deepcopy(plan)
            mutate(invalid)
            with self.assertRaises(NativeCompileError):
                validate_plan(invalid)

    def test_empty_table_cannot_generate_a_runtime_that_rejects_it(self):
        with self.assertRaises(NativeCompileError):
            self.compile("")

    def test_identity_depends_on_table_process_and_selection(self):
        full = compile_table(FIXTURE, "FixtureTarget.exe")
        self.assertEqual(full["trainer_id"], compile_table(FIXTURE, "fixturetarget.EXE")["trainer_id"])
        self.assertNotEqual(full["trainer_id"], compile_table(FIXTURE, "Other.exe")["trainer_id"])
        self.assertNotEqual(full["trainer_id"], compile_table(FIXTURE, "FixtureTarget.exe", selected_ids=[0])["trainer_id"])


class NativeAATests(unittest.TestCase):
    def test_direct_patch_has_symmetric_guarded_operations(self):
        plan = compile_script(patch_script())
        self.assertEqual(plan["requires"], [])
        self.assertEqual(plan["enable"], [{"op": "assert", "address": "Target.exe+10", "bytes": "00"}, {"op": "write", "address": "Target.exe+10", "bytes": "01"}])

    def test_integer_data_width_hex_decimal_and_negative_semantics(self):
        script = "[ENABLE]\nassert(Target.exe,00 00 00 00 00 00 00 00 00 00 00 00 00 00 00)\nTarget.exe:\ndb 10\ndw 1234\ndd #10\ndq -1\n[DISABLE]\nassert(Target.exe,10 34 12 0A 00 00 00 FF FF FF FF FF FF FF FF)\nTarget.exe:\ndb 00\ndw 0\ndd 0\ndq 0"
        plan = compile_script(script)
        self.assertEqual([op["bytes"] for op in plan["enable"] if op["op"] == "write"], ["10", "3412", "0a000000", "ffffffffffffffff"])
        self.assertEqual([op["address"] for op in plan["enable"] if op["op"] == "write"], ["Target.exe", "Target.exe+1", "Target.exe+3", "Target.exe+7"])

    def test_comments_and_case_insensitive_sections(self):
        script = "{two\nline comment}\n" + patch_script().replace("[ENABLE]", "[ enable ] // note").replace("db 01", "DB 01 // patch")
        self.assertEqual(len(compile_script(script)["enable"]), 2)

    def test_named_data_label_alias_inherits_address_for_disable(self):
        script = "label(PatchAddress)\n[ENABLE]\nassert(Target.exe+10,00)\nTarget.exe+10:\nPatchAddress:\ndb 01\n[DISABLE]\nassert(PatchAddress,01)\nPatchAddress:\ndb 00"
        plan = compile_script(script)
        self.assertEqual(plan["enable"][1], {"op": "define", "symbol": "PatchAddress", "expression": "Target.exe+10"})
        self.assertEqual(plan["enable"][-1]["address"], "PatchAddress")
        self.assertEqual(plan["requires"], [])

    def test_noop_script_and_unbalanced_module_quote_are_rejected(self):
        for script in ("[ENABLE]\n[DISABLE]", '[ENABLE]\naobscanmodule(Anchor,"Target.exe,54 46)\nregistersymbol(Anchor)\n[DISABLE]\nunregistersymbol(Anchor)'):
            with self.subTest(script=script), self.assertRaises(AAError):
                compile_script(script)

    def test_unsupported_lua_machine_code_thread_and_alloc(self):
        for line in ("{$LUA}", "mov eax,1", "createthread(Target.exe)", "alloc(Anchor,100)", "include(file.asm)", "{$C}"):
            with self.subTest(line=line), self.assertRaises(AAError):
                compile_script("[ENABLE]\n" + line + "\n[DISABLE]\n")

    def test_missing_assert_and_wrong_disable_restore_rejected(self):
        for script in ("[ENABLE]\nTarget.exe:\ndb 01\n[DISABLE]\nTarget.exe:\ndb 00", patch_script().replace("db 00", "db 02")):
            with self.subTest(script=script), self.assertRaises(AAError):
                compile_script(script)

    def test_symbol_registration_requires_unregister(self):
        with self.assertRaisesRegex(AAError, "unregistered"):
            compile_script("[ENABLE]\ndefine(Anchor,Target.exe)\nregistersymbol(Anchor)\n[DISABLE]\n")

    def test_expression_is_bounded_and_never_evaluated(self):
        self.assertEqual(validate_expression('"Game-Win64-Shipping.exe" + 10 - 8'), '"Game-Win64-Shipping.exe"+8')
        self.assertEqual(expression_symbols("Anchor+10"), ["Anchor"])
        self.assertEqual(expression_symbols("Game.exe+10"), [])
        self.assertEqual(expression_symbols("1234"), [])
        for expression in ("[Anchor]+4", "lua('x')", "Target.exe*2", "C:\\Target.exe+4", "Anchor+10000000000000000"):
            with self.subTest(expression=expression), self.assertRaises(AAError):
                validate_expression(expression)

    def test_scan_wildcards_are_preserved_and_all_wildcards_rejected(self):
        plan = compile_script("[ENABLE]\naobscanmodule(Anchor,Target.exe,54 ?? 4? ?F)\nregistersymbol(Anchor)\n[DISABLE]\nunregistersymbol(Anchor)")
        self.assertEqual(plan["enable"][0]["pattern"], "54 ?? 4? ?F")
        with self.assertRaises(AAError):
            compile_script("[ENABLE]\naobscanmodule(Anchor,Target.exe,?? ??)\n[DISABLE]\n")

    def test_duplicate_sections_integer_overflow_wildcard_assert_rejected(self):
        for script in (patch_script() + "\n[DISABLE]", patch_script().replace("db 01", "db 100"), patch_script().replace("assert(Target.exe+10,00)", "assert(Target.exe+10,??)")):
            with self.subTest(script=script), self.assertRaises(AAError):
                compile_script(script)


if __name__ == "__main__":
    unittest.main()
