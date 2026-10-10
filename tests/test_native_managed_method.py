"""Managed method label wiring (AP-05 stage 3): grammar, plan, engine.

Pinned corpus shapes (Yooka-Laylee, Disco Elysium): AA scripts patch IL2CPP
managed method heads addressed by injection labels, either the colon form
``Class:Method:`` or the dotted form ``Namespace.Class.Method:``.  The
compiler records each label verbatim in the program's
``managed_method_labels`` (never in ``requires``: labels have no
cross-record provider); the engine resolves them through the injected
``il2cpp_resolver`` at program install time and links the patch at the
resolver-proven live address.  This file proves the full chain against the
tested stage-2 registration host over own synthetic PE/metadata fixtures:
label -> resolver -> symbol overlay -> link -> byte-exact patch and restore.
"""
from pathlib import Path
import struct
import tempfile
import unittest

from test_native_engine import FakeMemory
from test_native_engine_code import Coordinator
from test_native_il2cpp_host import IDENTITY, default_base, make_host

from ct2trainer.native.aa_program import ProgramError, prepare_program, validate_program
from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import NativeRuntimeError, TrainerEngine
from ct2trainer.native.il2cpp_host import AliasSpec

COLON_SCRIPT = (
    "[ENABLE]\n"
    "assert(PlayerDropQuills:Activate,55)\n"
    "PlayerDropQuills:Activate:\n"
    "db c3\n"
    "[DISABLE]\n"
    "PlayerDropQuills:Activate:\n"
    "db 55\n"
)

DOTTED_SCRIPT = (
    "[ENABLE]\n"
    "Sunshine.Metric.SunshineRoller.RollOne:\n"
    "db B8 06 00 00 00 c3\n"
    "[DISABLE]\n"
    "Sunshine.Metric.SunshineRoller.RollOne:\n"
    "db 40 53 48 83 EC 20\n"
)

CT_BODY = '''<CheatTable CheatEngineTableVersion="45"><CheatEntries>
<CheatEntry><ID>700</ID><Description>"Colon managed method"</Description><VariableType>Auto Assembler Script</VariableType><AssemblerScript>[ENABLE]
assert(PlayerDropQuills:Activate,55)
PlayerDropQuills:Activate:
db c3
[DISABLE]
PlayerDropQuills:Activate:
db 55
</AssemblerScript></CheatEntry>
<CheatEntry><ID>701</ID><Description>"Dotted managed method"</Description><VariableType>Auto Assembler Script</VariableType><AssemblerScript>[ENABLE]
Sunshine.Metric.SunshineRoller.RollOne:
db B8 06 00 00 00 c3
[DISABLE]
Sunshine.Metric.SunshineRoller.RollOne:
db 40 53 48 83 EC 20
</AssemblerScript></CheatEntry>
</CheatEntries></CheatTable>'''


class ManagedMethodProgramTests(unittest.TestCase):
    """Compiler level: prepare_program records managed labels, nothing else."""

    def test_colon_label_is_recorded_and_requires_stays_clean(self):
        program = prepare_program(COLON_SCRIPT, "FixtureTarget.exe")
        self.assertEqual(
            program["managed_method_labels"], ["PlayerDropQuills:Activate"])
        self.assertEqual(program["requires"], [])
        validate_program(program)

    def test_dotted_label_is_recorded(self):
        program = prepare_program(DOTTED_SCRIPT, "FixtureTarget.exe")
        self.assertEqual(program["managed_method_labels"],
                         ["Sunshine.Metric.SunshineRoller.RollOne"])
        self.assertEqual(program["requires"], [])
        validate_program(program)

    def test_label_offset_keeps_the_single_label(self):
        script = COLON_SCRIPT.replace(
            "PlayerDropQuills:Activate:\n", "PlayerDropQuills:Activate+10:\n", 1)
        program = prepare_program(script, "FixtureTarget.exe")
        self.assertEqual(
            program["managed_method_labels"], ["PlayerDropQuills:Activate"])
        cursor = next(node for node in program["enable"] if node["op"] == "cursor")
        self.assertEqual(cursor["expression"], "PlayerDropQuills:Activate+10")

    def test_two_segment_dotted_name_stays_an_export(self):
        script = ("[ENABLE]\nFoo.Bar:\ndb c3\n[DISABLE]\nFoo.Bar:\ndb c3\n")
        program = prepare_program(script, "FixtureTarget.exe")
        self.assertEqual(program["managed_method_labels"], [])

    def test_plain_symbol_label_is_unaffected(self):
        script = ("[ENABLE]\nMyLabel:\ndb c3\n[DISABLE]\nMyLabel:\ndb c3\n")
        program = prepare_program(script, "FixtureTarget.exe")
        self.assertEqual(program["managed_method_labels"], [])
        self.assertEqual(program["requires"], ["MyLabel"])

    def test_triple_colon_form_is_refused(self):
        with self.assertRaises(ProgramError):
            prepare_program(
                "[ENABLE]\nA:B:C:\ndb c3\n[DISABLE]\nA:B:C:\ndb c3\n",
                "FixtureTarget.exe")

    def test_empty_colon_segment_is_refused(self):
        with self.assertRaises(ProgramError):
            prepare_program(
                "[ENABLE]\n:Activate:\ndb c3\n[DISABLE]\n:Activate:\ndb c3\n",
                "FixtureTarget.exe")

    def test_tampered_label_manifest_is_refused(self):
        program = prepare_program(COLON_SCRIPT, "FixtureTarget.exe")
        program["managed_method_labels"] = ["Forged:Label"]
        with self.assertRaises(ProgramError):
            validate_program(program)


class ManagedMemory(FakeMemory):
    """Spans the IL2CPP binding base; the two host-proven method heads
    (offsets 0x1040 / 0x1048) hold executable original prologues."""

    def __init__(self):
        super().__init__()
        self.base = default_base(64)
        self.data = bytearray(0x1400)
        self.data[:16] = b"CT2T-FIX-2026-01"
        self.data[16:20] = struct.pack("<I", 1234)
        self.data[0x1040] = 0x55  # original prologue byte (colon record)
        self.data[0x1048:0x104E] = bytes.fromhex("40534883EC20")

    @property
    def identity(self):
        return self.pid, self.creation_time

    def is_executable(self, address, size):
        return (self.base + 0x1040 <= address
                and address + size <= self.base + 0x104E)


def _make_host():
    host, _tables = make_host()
    host.register_alias(AliasSpec(
        alias="PlayerDropQuills:Activate", kind="method",
        image=IDENTITY[0], namespace=IDENTITY[1], class_name=IDENTITY[2],
        name="GetCurrentStatus"))
    host.register_alias(AliasSpec(
        alias="Sunshine.Metric.SunshineRoller.RollOne", kind="method",
        image=IDENTITY[0], namespace=IDENTITY[1], class_name=IDENTITY[2],
        name="SetFlag", parameter_type_indices=(102,)))
    return host


class ManagedMethodEngineTests(unittest.TestCase):
    """Engine level: resolver -> symbol overlay -> link -> byte-exact patch."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.table = self.root / "managed.ct"
        self.table.write_text(CT_BODY, encoding="utf-8")
        self.memory = ManagedMemory()
        self.host = _make_host()
        self.engine = TrainerEngine(
            compile_table(self.table, "FixtureTarget.exe"),
            state_dir=self.root / "state",
            process_lock_dir=self.root / "shared",
            memory_factory=lambda name: self.memory,
            hook_coordinator=Coordinator(),
            il2cpp_resolver=lambda label: self.host.resolve_alias(label).va)
        self.engine.poll()

    def tearDown(self):
        self.engine.close()

    def test_plan_carries_managed_method_labels_and_clean_requires(self):
        by_id = {entry["id"]: entry for entry in self.engine.plan["entries"]}
        self.assertEqual(by_id[700]["program"]["managed_method_labels"],
                         ["PlayerDropQuills:Activate"])
        self.assertEqual(by_id[701]["program"]["managed_method_labels"],
                         ["Sunshine.Metric.SunshineRoller.RollOne"])
        for entry in by_id.values():
            self.assertEqual(entry["program"]["requires"], [])
            self.assertEqual(entry["requires"], [])

    def test_colon_label_enable_disable_roundtrip(self):
        base = default_base(64)
        self.assertTrue(self.engine.toggle(700, True))
        self.assertEqual(self.memory.read(base + 0x1040, 1), b"\xc3")
        self.assertFalse(self.engine.toggle(700, False))
        self.assertEqual(self.memory.read(base + 0x1040, 1), b"\x55")

    def test_dotted_label_enable_disable_roundtrip(self):
        base = default_base(64)
        self.assertTrue(self.engine.toggle(701, True))
        self.assertEqual(self.memory.read(base + 0x1048, 6),
                         bytes.fromhex("b806000000c3"))
        self.assertFalse(self.engine.toggle(701, False))
        self.assertEqual(self.memory.read(base + 0x1048, 6),
                         bytes.fromhex("40534883ec20"))

    def test_writes_land_at_host_proven_addresses(self):
        self.assertTrue(self.engine.toggle(700, True))
        self.assertTrue(self.engine.toggle(701, True))
        addresses = {address for address, _ in self.memory.writes}
        for label in ("PlayerDropQuills:Activate",
                      "Sunshine.Metric.SunshineRoller.RollOne"):
            self.assertIn(self.host.resolve_alias(label).va, addresses)

    def test_missing_resolver_fails_closed_before_any_write(self):
        memory = ManagedMemory()
        engine = TrainerEngine(
            compile_table(self.table, "FixtureTarget.exe"),
            state_dir=self.root / "state-nor",
            process_lock_dir=self.root / "shared-nor",
            memory_factory=lambda name: memory,
            hook_coordinator=Coordinator())
        engine.poll()
        try:
            with self.assertRaisesRegex(NativeRuntimeError, "IL2CPP resolver"):
                engine.toggle(700, True)
        finally:
            engine.close()
        self.assertFalse(memory.writes)

    def test_resolver_failure_blocks_entry_without_writes(self):
        def failing_resolver(label):
            raise NativeRuntimeError("IL2CPP binding unavailable")

        memory = ManagedMemory()
        engine = TrainerEngine(
            compile_table(self.table, "FixtureTarget.exe"),
            state_dir=self.root / "state-fail",
            process_lock_dir=self.root / "shared-fail",
            memory_factory=lambda name: memory,
            hook_coordinator=Coordinator(),
            il2cpp_resolver=failing_resolver)
        engine.poll()
        try:
            with self.assertRaises(NativeRuntimeError):
                engine.toggle(700, True)
        finally:
            engine.close()
        self.assertFalse(memory.writes)

    def test_resolver_non_integer_address_is_rejected(self):
        memory = ManagedMemory()
        engine = TrainerEngine(
            compile_table(self.table, "FixtureTarget.exe"),
            state_dir=self.root / "state-bad",
            process_lock_dir=self.root / "shared-bad",
            memory_factory=lambda name: memory,
            hook_coordinator=Coordinator(),
            il2cpp_resolver=lambda label: "0x1040")
        engine.poll()
        try:
            with self.assertRaisesRegex(NativeRuntimeError, "invalid address"):
                engine.toggle(700, True)
        finally:
            engine.close()
        self.assertFalse(memory.writes)


if __name__ == "__main__":
    unittest.main()
