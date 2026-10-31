"""RT-5 item B: table-level <CheatCodes> code list as code_patch records.

Covers, for independently authored synthetic fixtures (no corpus files are
loaded; the fixtures mirror the corpus shapes — AddressString, ModuleName
plus ModuleNameOffset, absolute Address, GroupHeader rows, and
Before/Actual/After stored both as <Byte> child-element sequences and as
plain element text):

- table parsing: the frozen CodePatch list on Table, lowercase hex
  normalization, the text fallback of the byte-capture codec, and the
  fail-closed per-entry drops (non-hex captures, empty Actual, missing
  Description, missing address, header without a Description) with named
  warnings while the table still loads; the 4096-entry section bound;
  to_dict() exposure;
- compilation: address composition (AddressString verbatim / ModuleName
  plus normalized offset / absolute Address uppercased), the supported
  code_patch shape with synthetic IDs at 2**32 and up in table order,
  GroupHeader rows as supported headings with no activation effect, the
  CheatCodes warning no longer emitted, selection by synthetic ID, and
  the per-entry block for a symbol-carrying address;
- validation: both validate_plan gates (compiler and engine) accept the
  compiled shape and each rejects a forged or tampered code record
  (low ID, uppercase hex, empty actual, non-hex before, oversized
  capture, symbol-carrying or unparseable address, address/source
  mismatch, foreign metadata keys, shape deviation);
- engine: enable from pristine (byte-exact actual, applied, wish
  persisted), enable when the actual bytes are already live (adopted,
  zero writes in both directions), enable when the live bytes no longer
  match Before (named code-patch-target-changed refusal, zero writes,
  entry error, engine not blocked), disable restore byte-exact, disable
  never-applied no-op, disable with foreign bytes (named
  code-patch-restore-mismatch refusal, zero writes, engine blocked),
  the group-header no-effect toggle, saved-wish re-enable across
  re-attach, close-time restore, and the executable-page routing through
  the hook coordinator (plus the named coordinator refusal);
- UI rows: code records join the Switches/On/Saved views, render as
  switch rows with the "code" chip, and stay out of the Scripts view.
"""
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from copy import deepcopy
from pathlib import Path

from test_native_engine import FakeMemory
from test_native_engine_code import CodeMemory, Coordinator
from ct2trainer.native.compiler import (NativeCompileError, compile_table,
                                        validate_plan as validate_compiler_plan)
from ct2trainer.native.engine import (NativeRuntimeError, TrainerEngine,
                                      validate_plan as validate_engine_plan)
from ct2trainer.native.ui_rows import (ROW_SWITCH, STATE_ON, STATE_OFF,
                                       RowSnapshot, _switch_chip, build_rows)
from ct2trainer.table import read_table


PROCESS = "FixtureTarget.exe"
CODE_BASE = 2 ** 32
WIDTH = 640


def byte_el(pairs: list[str]) -> str:
    """One byte capture as the corpus's <Byte> child-element sequence."""
    return "".join(f"<Byte>{pair}</Byte>" for pair in pairs)


def code_entry(desc: str, module: str = "", offset: str = "", addrstr: str = "",
               address: str = "", before: str = "", actual: str = "",
               after: str = "", group_header: bool = False) -> str:
    header = ' GroupHeader="1"' if group_header else ""
    return (f"<CodeEntry{header}><Description>{desc}</Description>"
            f"<ModuleName>{module}</ModuleName>"
            f"<ModuleNameOffset>{offset}</ModuleNameOffset>"
            f"<AddressString>{addrstr}</AddressString>"
            f"<Address>{address}</Address>"
            f"<Before>{before}</Before><Actual>{actual}</Actual>"
            f"<After>{after}</After></CodeEntry>")


def value_record(entry_id: int, address: str = "1000") -> str:
    return (f"<CheatEntry><ID>{entry_id}</ID><Description>Value {entry_id}</Description>"
            f"<VariableType>4 Bytes</VariableType><Address>{address}</Address>"
            f"</CheatEntry>")


def table_xml(body: str, codes: str = "") -> str:
    return ('<CheatTable CheatEngineTableVersion="45"><CheatEntries>' + body
            + "</CheatEntries>" + codes + "</CheatTable>")


# The full-shape fixture: three address forms, a group header and a plain
# value record.  Byte captures mix <Byte> child elements and element text.
FULL_CODES = ("<CheatCodes>"
              + code_entry("Code module offset", module=PROCESS, offset="0x40",
                           before=byte_el(["00"]), actual=byte_el(["AA"]),
                           after=byte_el(["BB"]))
              + code_entry("Code address string", addrstr="1050",
                           before="01", actual="02", after="")
              + code_entry("Code absolute", address="1060",
                           before="", actual=byte_el(["FF", "00"]),
                           after=byte_el(["00", "00"]))
              + code_entry("Code group header", group_header=True)
              + "</CheatCodes>")

FULL_BODY = value_record(0)


class CodeMemory(FakeMemory):
    """Data backend that reports one executable page (base+96..base+111)."""

    @property
    def identity(self):
        return self.pid, self.creation_time

    def is_executable(self, address, size):
        return self.base + 96 <= address < self.base + 112


def snapshot(applied=frozenset(), desired=frozenset()) -> RowSnapshot:
    return RowSnapshot(applied=applied, desired=desired)


class CodePatchTableTests(unittest.TestCase):
    """The <CheatCodes> parse layer (fail-closed per entry)."""

    def write(self, xml: str, name: str = "code.CT") -> Path:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / name
        path.write_text(xml, encoding="utf-8")
        return path

    def test_code_entries_parse_all_forms(self):
        path = self.write(table_xml(FULL_BODY, FULL_CODES))
        table = read_table(path)
        self.assertEqual(len(table.code_entries), 4)
        first = table.code_entries[0]
        self.assertEqual(first.description, "Code module offset")
        self.assertFalse(first.group_header)
        self.assertEqual((first.module_name, first.module_name_offset),
                         (PROCESS, "0x40"))
        self.assertEqual((first.address_string, first.address), ("", ""))
        # <Byte> child sequences normalize to lowercase hex.
        self.assertEqual((first.before, first.actual, first.after),
                         ("00", "aa", "bb"))
        second = table.code_entries[1]
        self.assertEqual((second.module_name, second.module_name_offset),
                         ("", ""))
        self.assertEqual(second.address_string, "1050")
        # Element-text fallback keeps the value, lowercased, whitespace
        # dropped.
        self.assertEqual((second.before, second.actual, second.after),
                         ("01", "02", ""))
        third = table.code_entries[2]
        self.assertEqual(third.address, "1060")
        self.assertEqual((third.before, third.actual, third.after),
                         ("", "ff00", "0000"))
        fourth = table.code_entries[3]
        self.assertTrue(fourth.group_header)
        self.assertEqual(fourth.description, "Code group header")
        self.assertEqual((fourth.module_name, fourth.address_string,
                          fourth.address), ("", "", ""))
        self.assertEqual((fourth.before, fourth.actual, fourth.after),
                         ("", "", ""))

    def test_byte_codec_text_fallback_and_empty(self):
        from ct2trainer.table import _code_hex_bytes
        self.assertEqual(_code_hex_bytes(None), "")
        self.assertEqual(_code_hex_bytes(ET.fromstring("<Before></Before>")), "")
        self.assertEqual(_code_hex_bytes(
            ET.fromstring("<Before> AB cd </Before>")), "abcd")
        self.assertEqual(_code_hex_bytes(
            ET.fromstring("<Before><Byte>ab</Byte><Byte>Cd</Byte></Before>")),
            "abcd")

    def test_byte_codec_non_hex_is_refused(self):
        from ct2trainer.table import _code_hex_bytes
        self.assertIsNone(_code_hex_bytes(
            ET.fromstring("<Before>ZZ</Before>")))
        self.assertIsNone(_code_hex_bytes(
            ET.fromstring("<Before><Byte>GZ</Byte></Before>")))
        # Odd-length text is not a whole-byte hex sequence either.
        self.assertIsNone(_code_hex_bytes(
            ET.fromstring("<Before><Byte>A</Byte><Byte>BC</Byte></Before>")))

    def test_fail_closed_entries_drop_with_named_warnings(self):
        codes = "<CheatCodes>" \
            + code_entry("Bad before", addrstr="1010",
                         before=byte_el(["ZZ"]), actual=byte_el(["AA"])) \
            + code_entry("Empty actual", addrstr="1011", before="00", actual="") \
            + code_entry("", addrstr="1012", actual="AA") \
            + code_entry("No address", before="00", actual="AA") \
            + code_entry("", group_header=True) \
            + code_entry("Kept", addrstr="1020", before="00", actual="01") \
            + "</CheatCodes>"
        table = read_table(self.write(table_xml(FULL_BODY, codes)))
        self.assertEqual(len(table.code_entries), 1)
        self.assertEqual(table.code_entries[0].description, "Kept")
        joined = "\n".join(table.warnings)
        self.assertIn("entry 1 ('Bad before'): <Before>", joined)
        self.assertIn("entry 2 ('Empty actual'): empty <Actual>", joined)
        # A missing <Description> falls back to the positional entry name.
        self.assertIn("entry 3 ('CodeEntry 3'): missing <Description>", joined)
        self.assertIn("entry 4 ('No address'): no usable address", joined)
        self.assertIn("group header without a <Description>", joined)

    def test_oversized_codes_section_is_ignored_whole(self):
        many = "".join(code_entry(f"Code {i}", addrstr=f"10{i:02x}",
                                  actual="AA") for i in range(4097))
        table = read_table(self.write(table_xml(FULL_BODY,
                                                "<CheatCodes>" + many + "</CheatCodes>")))
        self.assertEqual(table.code_entries, ())
        self.assertTrue(any("exceeds 4096 entries" in warning
                            for warning in table.warnings))

    def test_absent_and_empty_sections_yield_no_entries(self):
        table = read_table(self.write(table_xml(FULL_BODY)))
        self.assertEqual(table.code_entries, ())
        self.assertFalse(table.warnings)
        table = read_table(self.write(table_xml(FULL_BODY, "<CheatCodes></CheatCodes>")))
        self.assertEqual(table.code_entries, ())
        self.assertFalse(table.warnings)

    def test_to_dict_exposes_code_entries(self):
        path = self.write(table_xml(FULL_BODY, FULL_CODES))
        document = read_table(path).to_dict()
        self.assertEqual(len(document["code_entries"]), 4)
        self.assertEqual(document["code_entries"][0]["description"],
                         "Code module offset")
        self.assertEqual(document["code_entries"][2]["actual"], "ff00")
        self.assertTrue(document["code_entries"][3]["group_header"])


class CodePatchCompileTests(unittest.TestCase):
    """Address composition, projection, selection and the section warning."""

    def compile(self, codes: str = FULL_CODES, selected_ids=None) -> dict:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / "code.CT"
        path.write_text(table_xml(FULL_BODY, codes), encoding="utf-8")
        return compile_table(str(path), PROCESS, selected_ids=selected_ids)

    def test_compile_projects_code_records(self):
        plan = self.compile()
        entries = plan["entries"]
        self.assertEqual(plan["counts"]["total"], 5)
        self.assertEqual(plan["counts"]["supported"], 5)
        by_kind = [entry for entry in entries if entry["kind"] == "code_patch"]
        self.assertEqual(len(by_kind), 3)
        # Synthetic IDs in table order, above the source-ID space.
        self.assertEqual([entry["id"] for entry in by_kind],
                         [CODE_BASE, CODE_BASE + 1, CODE_BASE + 2])
        module = by_kind[0]
        self.assertEqual(module["label"], "Code module offset")
        self.assertEqual(module["address"], "FixtureTarget.exe+40")
        self.assertEqual(module["source_address"], "FixtureTarget.exe+40")
        self.assertEqual((module["before"], module["actual"], module["after"]),
                         ("00", "aa", "bb"))
        self.assertTrue(module["supported"])
        self.assertTrue(module["selected"])
        self.assertIsNone(module["parent_id"])
        self.assertEqual(module["requires"], [])
        self.assertEqual(module["provides"], [])
        # The address-string form stays verbatim.
        self.assertEqual(by_kind[1]["address"], "1050")
        self.assertEqual(by_kind[1]["before"], "01")
        # The absolute form is uppercased raw hex.
        self.assertEqual(by_kind[2]["address"], "1060")
        self.assertEqual(by_kind[2]["actual"], "ff00")
        # The group header compiles to a supported heading without byte
        # captures and without any activation effect metadata.
        heading = [entry for entry in entries if entry["kind"] == "heading"][0]
        self.assertEqual(heading["id"], CODE_BASE + 3)
        self.assertEqual(heading["label"], "Code group header")
        self.assertTrue(heading["supported"])
        self.assertEqual(heading["reason"],
                         "Code-list section header; CE group activation is not executed.")
        self.assertNotIn("before", heading)
        self.assertNotIn("actual", heading)
        self.assertNotIn("after", heading)
        # The CheatCodes section is interpreted; the generic not-interpreted
        # warning no longer names it.
        self.assertFalse(any("CheatCodes" in warning
                             for warning in plan["warnings"]))
        validate_compiler_plan(plan)
        validate_engine_plan(plan)

    def test_compile_selection_by_synthetic_id(self):
        plan = self.compile(selected_ids=[0, CODE_BASE])
        entries = {entry["id"]: entry for entry in plan["entries"]}
        self.assertTrue(entries[0]["selected"])
        self.assertTrue(entries[CODE_BASE]["selected"])
        self.assertFalse(entries[CODE_BASE + 1]["selected"])
        self.assertFalse(entries[CODE_BASE + 3]["selected"])
        plan = self.compile(selected_ids=[CODE_BASE + 2])
        entries = {entry["id"]: entry for entry in plan["entries"]}
        self.assertTrue(entries[CODE_BASE + 2]["selected"])
        self.assertFalse(entries[0]["selected"])
        self.assertFalse(entries[CODE_BASE]["selected"])
        with self.assertRaisesRegex(NativeCompileError, "unknown"):
            self.compile(selected_ids=[CODE_BASE + 99])

    def test_compile_symbol_address_blocks_entry_only(self):
        codes = ("<CheatCodes>"
                 + code_entry("Symbol code", addrstr="SomeSymbol+10",
                              actual="AA")
                 + code_entry("Kept code", addrstr="1030", actual="AA")
                 + "</CheatCodes>")
        plan = self.compile(codes)
        blocked = [entry for entry in plan["entries"]
                   if entry["label"] == "Symbol code"]
        self.assertEqual(len(blocked), 1)
        blocked = blocked[0]
        self.assertFalse(blocked["supported"])
        self.assertEqual(blocked["kind"], "blocked")
        self.assertIn("static address expression", blocked["reason"])
        kept = [entry for entry in plan["entries"]
                if entry["label"] == "Kept code"][0]
        self.assertTrue(kept["supported"])
        self.assertEqual(kept["id"], CODE_BASE + 1)
        validate_compiler_plan(plan)
        validate_engine_plan(plan)


class CodePatchValidatorTests(unittest.TestCase):
    """Both plan validators re-derive the code_patch shape from a plan."""

    def plan(self) -> dict:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / "code.CT"
        path.write_text(table_xml(FULL_BODY, FULL_CODES), encoding="utf-8")
        return compile_table(str(path), PROCESS)

    def code_entry(self, plan: dict) -> dict:
        return next(entry for entry in plan["entries"]
                    if entry["kind"] == "code_patch")

    def test_validators_accept_the_compiled_shape(self):
        plan = self.plan()
        validate_compiler_plan(plan)
        validate_engine_plan(plan)

    def test_validators_reject_forged_entries(self):
        cases = [
            ("low synthetic ID",
             lambda entry: entry.update(id=5),
             "synthetic"),
            ("uppercase actual hex",
             lambda entry: entry.update(actual="AA"),
             "lowercase whole-byte hex strings"),
            ("empty actual",
             lambda entry: entry.update(actual=""),
             "nonempty"),
            ("non-hex before",
             lambda entry: entry.update(before="zz"),
             "lowercase whole-byte hex strings"),
            ("oversized capture",
             lambda entry: entry.update(actual="ab" * 65537),
             "byte captures"),
            ("symbol-carrying address",
             lambda entry: entry.update(address="SomeSym+10",
                                        source_address="SomeSym+10"),
             "static"),
            ("unparseable address",
             lambda entry: entry.update(address="10+",
                                        source_address="10+"),
             "valid static address expression"),
            ("address/source mismatch",
             lambda entry: entry.update(source_address="1000"),
             "re-derive"),
            ("foreign executable metadata",
             lambda entry: entry.update(enable=[]),
             "no executable metadata"),
            ("shape deviation (parent)",
             lambda entry: entry.update(parent_id=0),
             "canonical form"),
        ]
        for name, mutation, phrase in cases:
            with self.subTest(name=name):
                plan = self.plan()
                entry = self.code_entry(plan)
                mutation(entry)
                with self.assertRaisesRegex(NativeCompileError, phrase):
                    validate_compiler_plan(plan)
                with self.assertRaisesRegex(NativeRuntimeError, phrase):
                    validate_engine_plan(plan)


class CodePatchRuntimeTests(unittest.TestCase):
    """The engine enable/disable lifecycle for code-list records."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.memories = []
        self.engines = []

    def tearDown(self):
        for memory in self.memories:
            if not memory.closed:
                memory.alive = False
        for engine in self.engines:
            if not engine.closed:
                engine.poll()
                engine.close()

    def attach(self, *, codes: str = FULL_CODES, memory: FakeMemory | None = None,
               coordinator="debug-event", state: str = "state",
               shared: str = "shared") -> tuple[TrainerEngine, FakeMemory]:
        path = self.root / "rt5b.CT"
        path.write_text(table_xml(FULL_BODY, codes), encoding="utf-8")
        plan = compile_table(str(path), PROCESS)
        if memory is None:
            memory = FakeMemory()
        memory.data[0x40] = 0x00
        memory.data[0x50] = 0x01
        memory.data[0x60] = 0x11
        memory.data[0x61] = 0x22
        self.memories.append(memory)
        engine = TrainerEngine(plan, state_dir=self.root / state,
                               process_lock_dir=self.root / shared,
                               memory_factory=lambda name: memory,
                               hook_coordinator=coordinator)
        self.engines.append(engine)
        engine.poll()
        self.assertTrue(engine.connected, engine.status)
        return engine, memory

    def code_id(self, engine: TrainerEngine, index: int = 0) -> int:
        return [entry for entry in engine.plan["entries"]
                if entry["kind"] == "code_patch"][index]["id"]

    def test_enable_pristine_applies_actual_and_saves_wish(self):
        engine, memory = self.attach()
        code_id = self.code_id(engine)
        self.assertTrue(engine.toggle(code_id, True))
        self.assertEqual(memory.read(0x1040, 1), b"\xaa")
        self.assertIn(code_id, engine.applied)
        self.assertIn(code_id, engine.desired)
        state = json.loads((self.root / "state" / "state.json")
                           .read_text(encoding="utf-8"))
        self.assertEqual(state["payload"]["desired"], [code_id])

    def test_enable_already_active_adopts_without_writing(self):
        engine, memory = self.attach()
        memory.data[0x40] = 0xAA  # the actual bytes are already live
        code_id = self.code_id(engine)
        self.assertTrue(engine.toggle(code_id, True))
        self.assertIn(code_id, engine.applied)
        self.assertEqual(memory.writes, [])
        self.assertFalse(engine.toggle(code_id, False))
        self.assertNotIn(code_id, engine.applied)
        self.assertEqual(memory.writes, [])

    def test_enable_target_changed_refuses_named(self):
        engine, memory = self.attach()
        memory.data[0x40] = 0x77  # no longer matches the table's Before
        code_id = self.code_id(engine)
        with self.assertRaisesRegex(NativeRuntimeError,
                                    "code-patch-target-changed"):
            engine.toggle(code_id, True)
        self.assertNotIn(code_id, engine.applied)
        self.assertNotIn(code_id, engine.desired)
        self.assertEqual(memory.writes, [])
        self.assertIn(code_id, engine.entry_errors)
        self.assertFalse(engine.blocked)

    def test_disable_restores_captured_original_byte_exact(self):
        engine, memory = self.attach()
        code_id = self.code_id(engine)
        self.assertTrue(engine.toggle(code_id, True))
        self.assertFalse(engine.toggle(code_id, False))
        self.assertEqual(memory.read(0x1040, 1), b"\x00")
        self.assertEqual(memory.writes, [(0x1040, b"\xaa"), (0x1040, b"\x00")])
        self.assertNotIn(code_id, engine.applied)
        self.assertNotIn(code_id, engine.desired)

    def test_disable_never_applied_is_no_op(self):
        engine, memory = self.attach()
        code_id = self.code_id(engine)
        self.assertFalse(engine.toggle(code_id, False))
        self.assertNotIn(code_id, engine.applied)
        self.assertEqual(memory.writes, [])

    def test_disable_foreign_bytes_refuses_and_blocks(self):
        engine, memory = self.attach()
        code_id = self.code_id(engine)
        self.assertTrue(engine.toggle(code_id, True))
        memory.data[0x40] = 0x77  # external clobber between enable and disable
        with self.assertRaisesRegex(NativeRuntimeError,
                                    "code-patch-restore-mismatch"):
            engine.toggle(code_id, False)
        self.assertEqual(memory.read(0x1040, 1), b"\x77")
        self.assertEqual(memory.writes, [(0x1040, b"\xaa")])
        self.assertTrue(engine.blocked)

    def test_group_header_toggle_has_no_effect(self):
        engine, memory = self.attach()
        heading = next(entry for entry in engine.plan["entries"]
                       if entry["kind"] == "heading")
        self.assertTrue(engine.toggle(heading["id"], True))
        self.assertIn(heading["id"], engine.applied)
        self.assertEqual(memory.writes, [])
        self.assertFalse(engine.toggle(heading["id"], False))
        self.assertNotIn(heading["id"], engine.applied)
        self.assertEqual(memory.writes, [])

    def test_saved_wish_reenables_after_reattach(self):
        engine, memory = self.attach(state="state", shared="shared")
        code_id = self.code_id(engine)
        self.assertTrue(engine.toggle(code_id, True))
        self.assertTrue(engine.close())
        # close() restored the target; the saved wish survives in state.json.
        self.assertEqual(memory.read(0x1040, 1), b"\x00")
        state = json.loads((self.root / "state" / "state.json")
                           .read_text(encoding="utf-8"))
        self.assertEqual(state["payload"]["desired"], [code_id])
        second, memory2 = self.attach(state="state", shared="shared")
        self.assertIn(code_id, second.applied)
        self.assertEqual(memory2.read(0x1040, 1), b"\xaa")

    def test_executable_code_routes_through_hook_coordinator(self):
        # The executable hook validator displaces only complete
        # instruction sequences, so the fixture site holds six bytes on
        # both sides: the original decodes as MOV EDX, ECX + four NOPs,
        # and the patch as MOV EAX, 0x65 + NOP.
        codes = ("<CheatCodes>"
                 + code_entry("Exec code", module=PROCESS, offset="60",
                              before=byte_el(["8B", "C1"]),
                              actual=byte_el(["B8", "65", "00", "00", "00", "90"]))
                 + "</CheatCodes>")

        def seed(memory) -> None:
            # The attach-time seed touches offsets 0x40..0x61, so the
            # pattern at offset 96 is (re)written after attach returns.
            memory.data[96:102] = bytes.fromhex("8bc190909090")

        # Without the verified coordinator the executable routing is
        # refused before any write.
        denied_memory = CodeMemory()
        denied, denied_mem = self.attach(codes=codes, memory=denied_memory,
                                         coordinator=None, state="denied",
                                         shared="denied-shared")
        seed(denied_mem)
        code_id = self.code_id(denied)
        with self.assertRaisesRegex(NativeRuntimeError, "coordinator"):
            denied.toggle(code_id, True)
        self.assertEqual(denied_mem.writes, [])
        self.assertNotIn(code_id, denied.applied)
        self.assertTrue(denied.close())
        # With the coordinator the same record routes through the hook
        # journal: publish under one coordinator hold, restore under a
        # second.
        memory = CodeMemory()
        coordinator = Coordinator()
        engine, mem = self.attach(codes=codes, memory=memory,
                                  coordinator=coordinator,
                                  state="allowed", shared="allowed-shared")
        seed(mem)
        code_id = self.code_id(engine)
        self.assertTrue(engine.toggle(code_id, True))
        self.assertEqual(mem.read(mem.base + 96, 6), bytes.fromhex("b86500000090"))
        self.assertEqual(len(coordinator.holds), 1)
        self.assertEqual(engine.hooks[code_id].receipt()["state"], "enabled")
        self.assertIn(code_id, engine.applied)
        self.assertFalse(engine.toggle(code_id, False))
        self.assertEqual(mem.read(mem.base + 96, 6), bytes.fromhex("8bc190909090"))
        self.assertEqual(len(coordinator.holds), 2)
        self.assertNotIn(code_id, engine.applied)


class CodePatchUiRowTests(unittest.TestCase):
    """Code-list records render as switch rows in the row model."""

    def plan(self) -> dict:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / "code.CT"
        path.write_text(table_xml(FULL_BODY, FULL_CODES), encoding="utf-8")
        return compile_table(str(path), PROCESS)

    def entries(self) -> dict:
        plan = self.plan()
        return {entry["id"]: entry for entry in plan["entries"]}

    def code_ids(self, entries: dict) -> list[int]:
        return [entry_id for entry_id, entry in entries.items()
                if entry["kind"] == "code_patch"]

    def rows_for(self, view: str, **snapshot_kwargs) -> list:
        entries = self.entries()
        rows = build_rows(entries, view, "", snapshot(**snapshot_kwargs), WIDTH)
        return {row.entry_id: row for row in rows}

    def test_switches_view_includes_code_rows(self):
        entries = self.entries()
        rows = self.rows_for("Switches")
        code_ids = self.code_ids(entries)
        self.assertEqual(sorted(rows), sorted(code_ids))
        for row in rows.values():
            self.assertEqual(row.kind, ROW_SWITCH)
            self.assertEqual(row.chip, "code")
            self.assertEqual(row.state, STATE_OFF)
            self.assertFalse(row.pill_on)
        # The plain value record stays out of the Switches view.
        self.assertNotIn(0, rows)

    def test_on_view_shows_applied_code_rows(self):
        entries = self.entries()
        rows = self.rows_for("On", applied=frozenset({self.code_ids(entries)[1]}))
        self.assertEqual(len(rows), 1)
        row = next(iter(rows.values()))
        self.assertEqual(row.state, STATE_ON)
        self.assertTrue(row.pill_on)

    def test_saved_view_shows_desired_code_rows(self):
        entries = self.entries()
        rows = self.rows_for("Saved",
                             desired=frozenset({self.code_ids(entries)[2]}))
        self.assertEqual(len(rows), 1)
        self.assertEqual(next(iter(rows.values())).state, STATE_OFF)

    def test_scripts_view_excludes_code_rows(self):
        self.assertEqual(self.rows_for("Scripts"), {})

    def test_switch_chip_is_code(self):
        entries = self.entries()
        code = next(entry for entry in entries.values()
                    if entry["kind"] == "code_patch")
        self.assertEqual(_switch_chip(code), "code")
        self.assertEqual(_switch_chip({"kind": "script"}), "")


if __name__ == "__main__":
    unittest.main()
