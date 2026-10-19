"""Indirection bound raised from 2 to 6 pointer dereferences (WP-45, GC-E10).

The strict split (`split_expression` / `validate_expression`) now admits
authored address chains up to six nested ``[]`` dereferences; the reference
corpus reaches 4-5 dereferences (Borderlands3 max 6).  Depth 7 stays
fail-closed with the named depth-limit refusal.  The runtime resolver
(``parse_expression`` / ``resolve_expression``) keeps its own parametric
bound (default 32) untouched, so admitted deep chains resolve at runtime.
"""
from __future__ import annotations

import re
import struct
import tempfile
import unittest
from pathlib import Path

from test_native_engine_code import Coordinator
from test_native_lua_activation import Memory

from ct2trainer.native.address_expression import (AddressExpressionError,
                                                  parse_expression)
from ct2trainer.native.aa import AAError, split_expression, validate_expression
from ct2trainer.native.compiler import (compile_table, validate_plan)
from ct2trainer.native.engine import (NativeRuntimeError, TrainerEngine,
                                      validate_plan as validate_engine_plan)

PROCESS = "FixtureTarget.exe"
DEPTH_REFUSAL = ("Address expression exceeds the bounded indirection depth "
                 "(6 pointer dereferences): ")


def depth_seven_refusal_regex() -> str:
    """Regex-escaped depth-7 refusal including the quoted expression."""
    return re.escape(DEPTH_REFUSAL + "'[[[[[[[sym]]]]]]]'")


def deref_depths(expression: str) -> list[str]:
    return ["[" * depth + "sym" + "]" * depth for depth in range(1, 8)]


class SplitDepthTests(unittest.TestCase):
    def test_depths_one_through_six_are_admitted(self):
        for depth in range(1, 7):
            with self.subTest(depth=depth):
                base, offset = split_expression(deref_depths("sym")[depth - 1])
                self.assertEqual(base, "[" * depth + "sym" + "]" * depth)
                self.assertEqual(offset, 0)

    def test_depth_seven_is_refused_with_the_named_depth_limit(self):
        with self.assertRaisesRegex(AAError, depth_seven_refusal_regex()):
            split_expression(deref_depths("sym")[6])

    def test_depth_eight_and_mixed_casts_stay_refused(self):
        with self.assertRaisesRegex(AAError, re.escape(DEPTH_REFUSAL)):
            split_expression("[[[[[[[[sym]]]]]]]")
        with self.assertRaisesRegex(AAError, re.escape(DEPTH_REFUSAL)):
            split_expression("((DWORD)[[[[[[[sym]]]]]]]+2")

    def test_displacement_tail_after_deep_chain_stays_admitted(self):
        # Bounded (non-flat) chains are admitted verbatim with a zero
        # displacement; the tail stays part of the profile expression.
        base, offset = split_expression("[[[[[[sym]]]]]]+10")
        self.assertEqual((base, offset), ("[[[[[[sym]]]]]]+10", 0))
        base, offset = split_expression("[[[sym]]]+10")
        self.assertEqual((base, offset), ("[[[sym]]]+10", 0))


class ValidateExpressionDepthTests(unittest.TestCase):
    def test_validate_expression_admits_six_and_refuses_seven(self):
        self.assertEqual(validate_expression("[[sym]]"), "[[sym]]")
        self.assertEqual(validate_expression("[[[sym]]]"), "[[[sym]]]")
        self.assertEqual(validate_expression("[[[[[[sym]]]]]]"), "[[[[[[sym]]]]]]")
        self.assertEqual(validate_expression("[[[sym]]]+4"), "[[[sym]]]+4")
        with self.assertRaisesRegex(AAError, depth_seven_refusal_regex()):
            validate_expression("[[[[[[[sym]]]]]]]")


class ResolverBoundUnchangedTests(unittest.TestCase):
    """The runtime resolver keeps its own parametric bound (default 32)."""

    def test_default_resolver_bound_admits_depth_seven(self):
        # Depth 7 parses fine for the runtime resolver (default max_deref=32);
        # only the strict split bound is the authored-depth gate.
        node = parse_expression("[[[[[[[sym]]]]]]]")
        self.assertEqual(node["kind"], "deref")
        self.assertEqual(node["value"]["kind"], "deref")

    def test_parametric_bound_remains_parametric(self):
        with self.assertRaisesRegex(
                AddressExpressionError,
                "Address expressions allow at most 2 pointer dereferences."):
            parse_expression("[[a]][b]", max_deref=2)
        self.assertEqual(parse_expression("[[a]]", max_deref=2)["kind"], "deref")


def write_table(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    table = root / "depth.ct"
    table.write_text(
        '<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
        '<CheatEntry><ID>0</ID><Description>"base"</Description>'
        '<VariableType>Auto Assembler Script</VariableType><AssemblerScript>[ENABLE]'
        '\ndefine(sym,1010)'
        '\nregistersymbol(sym)'
        '\n[DISABLE]'
        '\nunregistersymbol(sym)'
        '</AssemblerScript></CheatEntry>'
        '<CheatEntry><ID>1</ID><Description>"d3"</Description><VariableType>4 Bytes</VariableType><Address>[[[sym]]]</Address></CheatEntry>'
        '<CheatEntry><ID>2</ID><Description>"d4"</Description><VariableType>4 Bytes</VariableType><Address>[[[[sym]]]]</Address></CheatEntry>'
        '<CheatEntry><ID>3</ID><Description>"d5"</Description><VariableType>4 Bytes</VariableType><Address>[[[[[sym]]]]]</Address></CheatEntry>'
        '<CheatEntry><ID>4</ID><Description>"d6"</Description><VariableType>4 Bytes</VariableType><Address>[[[[[[sym]]]]]]</Address></CheatEntry>'
        '<CheatEntry><ID>5</ID><Description>"d7"</Description><VariableType>4 Bytes</VariableType><Address>[[[[[[[sym]]]]]]]</Address></CheatEntry>'
        '</CheatEntries></CheatTable>',
        encoding="utf-8")
    return table


class DepthPlanTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.table = write_table(self.root)
        self.plan = compile_table(self.table, PROCESS)
        self.by_id = {entry["id"]: entry for entry in self.plan["entries"]}

    def test_depth_three_to_six_take_the_expression_profile(self):
        for record_id, depth in ((1, 3), (2, 4), (3, 5), (4, 6)):
            with self.subTest(depth=depth):
                row = self.by_id[record_id]
                self.assertTrue(row["supported"], row["reason"])
                self.assertEqual(row["address_profile"], "expression/v1")
                self.assertEqual(row["address"], "[" * depth + "sym" + "]" * depth)
                self.assertEqual(row["pointer_offsets"], [])
                self.assertEqual(row["requires"], ["sym"])
                self.assertEqual(row["dependency_ids"], [0])
        blocked = self.by_id[5]
        self.assertFalse(blocked["supported"])
        self.assertEqual(blocked["reason"],
                         DEPTH_REFUSAL + "'[[[[[[[sym]]]]]]]'.")
        validate_plan(self.plan)
        validate_engine_plan(self.plan)


class _DerefMemory(Memory):
    """Fixture memory plus nested ``[]`` dereference resolution.

    The bounded expression profile resolves through the ordinary
    ``resolve`` entry point; the double extends the flat
    base/displacement dialect with pointer dereferences that follow the
    fixture memory contents.
    """

    def resolve(self, expression, symbols=None):
        expr = expression.strip()
        depth = 0
        while expr.startswith("[") and expr.endswith("]"):
            depth += 1
            expr = expr[1:-1]
        address = super().resolve(expr, symbols)
        for _ in range(depth):
            address = int.from_bytes(self.read(address, self.pointer_size),
                                     "little")
        return address


class DepthEngineTests(unittest.TestCase):
    """Runtime resolution of a depth-4 chain through live memory."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.table = write_table(self.root)
        self.memory = _DerefMemory()
        # sym -> 0x1010; chain 0x1010 -> 0x1020 -> 0x1030 -> 0x1040 -> 0x1050
        # (the 4 derefs of [[[[sym]]]] land on the value address 0x1050).
        self.memory.data[0x1010 - 0x1000:0x1018 - 0x1000] = struct.pack("<Q", 0x1020)
        self.memory.data[0x1020 - 0x1000:0x1028 - 0x1000] = struct.pack("<Q", 0x1030)
        self.memory.data[0x1030 - 0x1000:0x1038 - 0x1000] = struct.pack("<Q", 0x1040)
        self.memory.data[0x1040 - 0x1000:0x1048 - 0x1000] = struct.pack("<Q", 0x1050)
        self.memory.data[0x1050 - 0x1000:0x1054 - 0x1000] = struct.pack("<I", 0x1234)
        self.engine = TrainerEngine(compile_table(self.table, PROCESS),
                                    state_dir=self.root / "state",
                                    process_lock_dir=self.root / "shared",
                                    memory_factory=lambda name: self.memory,
                                    hook_coordinator=Coordinator())
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)

    def tearDown(self):
        if getattr(self, "engine", None) is None:
            return
        self.memory.alive = False
        self.engine.poll()
        self.engine.close()

    def test_depth_four_chain_resolves_at_runtime(self):
        engine = self.engine
        self.assertTrue(engine.toggle(0, True))
        self.assertEqual(engine.symbols["sym"], 0x1010)
        # 0x1234 at 0x1050, displayed decimal for a plain 4 Bytes value.
        self.assertEqual(engine.read_value(2), "4660")
        engine.toggle(0, False)
        self.assertNotIn("sym", engine.symbols)

    def test_blocked_depth_seven_record_is_inert_at_runtime(self):
        engine = self.engine
        self.assertTrue(engine.toggle(0, True))
        with self.assertRaisesRegex(NativeRuntimeError, re.escape(DEPTH_REFUSAL)):
            engine.read_value(5)
        with self.assertRaisesRegex(NativeRuntimeError, re.escape(DEPTH_REFUSAL)):
            engine.set_value(5, "1")
        self.assertEqual(len(self.memory.writes), 0)
        engine.toggle(0, False)


if __name__ == "__main__":
    unittest.main()
