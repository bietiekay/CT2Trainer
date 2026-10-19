"""Selection-aware symbol provider dedupe (WP-45, GC-E4).

Corpus semantics (synthetic fixture, no original table content): when
several records register the same symbol with incompatible definitions the
keep-first dedupe now respects the user's selection.  With at least one
provider selected, the selected providers form the dedupe scope, so an
explicit selection can activate the alternative variant instead of the
document-first one.  With no provider selected the table-wide scope applies
(the default compile selects every record, so default plans stay
byte-stable).  Unselected duplicates stay supported: the engine activates
selected-and-supported records only, so the kept provider cannot shadow
them at runtime.  The dependency loop resolves against selected supported
providers and falls back to the full supported set when none is selected,
so the selection closure still pulls in an initially unselected sole
provider.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from test_native_engine_code import Coordinator
from test_native_lua_activation import Memory

from ct2trainer.native.compiler import compile_table, validate_plan
from ct2trainer.native.engine import TrainerEngine, validate_plan as validate_engine_plan

PROCESS = "FixtureTarget.exe"
DUPLICATE_REASON = ("Symbol provider duplicate: sharedsym (kept provider {kept}); "
                    "a later registration would shadow the kept one at runtime.")


def provider_script(symbol: str, value: str = "3E8") -> str:
    # Hex literals: the engine resolves define values hex-first.  3E8/1000/
    # 1004 are the decimal values 1000/4096/4100.
    return (f"[ENABLE]\ndefine({symbol},{value})\nregistersymbol({symbol})\n"
            f"[DISABLE]\nunregistersymbol({symbol})")


def write_table(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    table = root / "dedupe.ct"
    table.write_text(
        '<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
        '<CheatEntry><ID>1</ID><Description>"Provider A"'
        f'</Description><VariableType>Auto Assembler Script</VariableType>'
        f'<AssemblerScript>{provider_script("sharedsym", "1000")}</AssemblerScript></CheatEntry>'
        '<CheatEntry><ID>2</ID><Description>"Provider B"'
        f'</Description><VariableType>Auto Assembler Script</VariableType>'
        f'<AssemblerScript>{provider_script("sharedsym", "1000")}</AssemblerScript></CheatEntry>'
        '<CheatEntry><ID>4</ID><Description>"Provider C"'
        f'</Description><VariableType>Auto Assembler Script</VariableType>'
        f'<AssemblerScript>{provider_script("sharedsym", "1004")}</AssemblerScript></CheatEntry>'
        '<CheatEntry><ID>3</ID><Description>"Consumer"</Description>'
        '<VariableType>4 Bytes</VariableType><Address>sharedsym+4</Address>'
        '<Value>0</Value></CheatEntry>'
        '</CheatEntries></CheatTable>',
        encoding="utf-8")
    return table


class ProviderSelectionDedupePlanTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.table = write_table(self.root)

    def compile(self, selected_ids=None):
        return compile_table(self.table, PROCESS, selected_ids=selected_ids)

    def by_id(self, plan):
        return {entry["id"]: entry for entry in plan["entries"]}

    def test_default_compile_keeps_the_document_first_provider(self):
        plan = self.compile()
        by = self.by_id(plan)
        self.assertTrue(by[1]["supported"], by[1]["reason"])
        self.assertFalse(by[2]["supported"])
        self.assertEqual(by[2]["reason"], DUPLICATE_REASON.format(kept=1))
        self.assertFalse(by[4]["supported"])
        self.assertEqual(by[4]["reason"], DUPLICATE_REASON.format(kept=1))
        self.assertTrue(by[3]["supported"], by[3]["reason"])
        self.assertEqual(by[3]["dependency_ids"], [1])
        self.assertEqual(plan["selected_ids"], [1, 2, 3, 4])
        validate_plan(plan)
        validate_engine_plan(plan)

    def test_selected_alternative_provider_wins_over_the_kept_one(self):
        plan = self.compile(selected_ids=[2])
        by = self.by_id(plan)
        # The unselected duplicate stays supported (the engine activates
        # selected-and-supported records only, so it cannot shadow the kept
        # provider at runtime).
        self.assertTrue(by[1]["supported"], by[1]["reason"])
        self.assertFalse(by[1]["selected"])
        self.assertTrue(by[2]["supported"], by[2]["reason"])
        self.assertTrue(by[2]["selected"])
        self.assertTrue(by[4]["supported"], by[4]["reason"])
        self.assertFalse(by[4]["selected"])
        # The consumer resolves against the selected provider.
        self.assertTrue(by[3]["supported"], by[3]["reason"])
        self.assertEqual(by[3]["dependency_ids"], [2])
        self.assertEqual(plan["selected_ids"], [2])
        validate_plan(plan)
        validate_engine_plan(plan)

    def test_both_selected_providers_keep_document_order_within_the_scope(self):
        plan = self.compile(selected_ids=[1, 2])
        by = self.by_id(plan)
        self.assertTrue(by[1]["supported"], by[1]["reason"])
        self.assertFalse(by[2]["supported"])
        self.assertEqual(by[2]["reason"], DUPLICATE_REASON.format(kept=1))
        self.assertTrue(by[3]["supported"], by[3]["reason"])
        self.assertEqual(by[3]["dependency_ids"], [1])

    def test_selected_later_provider_pair_keeps_the_first_selected(self):
        plan = self.compile(selected_ids=[2, 4])
        by = self.by_id(plan)
        # The scope is the selected provider set in document order, so the
        # selected keep-first is provider 2; provider 4 is the duplicate.
        self.assertTrue(by[1]["supported"], by[1]["reason"])
        self.assertTrue(by[2]["supported"], by[2]["reason"])
        self.assertFalse(by[4]["supported"])
        self.assertEqual(by[4]["reason"], DUPLICATE_REASON.format(kept=2))
        self.assertEqual(by[3]["dependency_ids"], [2])

    def test_consumer_only_selection_pulls_the_kept_provider_into_the_closure(self):
        plan = self.compile(selected_ids=[3])
        by = self.by_id(plan)
        self.assertTrue(by[1]["supported"], by[1]["reason"])
        self.assertFalse(by[2]["supported"])
        self.assertFalse(by[4]["supported"])
        self.assertEqual(by[3]["dependency_ids"], [1])
        # No provider is selected, so the dependency loop falls back to the
        # full supported set; the selection closure then activates the kept
        # provider for the consumer.
        self.assertEqual(plan["selected_ids"], [1, 3])
        validate_plan(plan)
        validate_engine_plan(plan)

    def test_unknown_selection_ids_stay_a_named_refusal(self):
        with self.assertRaises(Exception) as ctx:
            self.compile(selected_ids=[99])
        self.assertIn("Selection contains unknown or noninteger CT record IDs.",
                      str(ctx.exception))


class ProviderSelectionDedupeEngineTests(unittest.TestCase):
    """Engine level: only selected-and-supported providers activate."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.table = write_table(self.root)
        self.memory = Memory()
        # The consumer (3) must be selected too: the engine activates
        # selected-and-supported records only, so an unselected consumer has
        # no value action at runtime.
        self.engine = TrainerEngine(
            compile_table(self.table, PROCESS, selected_ids=[2, 3]),
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

    def test_unselected_duplicate_provider_stays_inert_at_runtime(self):
        engine = self.engine
        # Only the selected provider 2 may activate; the supported but
        # unselected providers 1 and 4 never register the symbol.
        self.assertNotIn(1, engine.desired)
        self.assertNotIn(4, engine.desired)
        self.assertTrue(engine.toggle(2, True))
        self.assertIn(2, engine.desired)
        self.assertEqual(engine.symbols["sharedsym"], 4096)
        self.assertNotIn(1, engine.desired)
        self.assertNotIn(4, engine.desired)
        # The consumer resolves through the selected provider's symbol:
        # 4096 + 4 = 0x1004.
        self.assertEqual(engine.set_value(3, "7"), "7")
        self.assertEqual(self.memory.read(0x1004, 4), b"\x07\x00\x00\x00")
        engine.toggle(2, False)
        self.assertNotIn("sharedsym", engine.symbols)
        self.assertNotIn(2, engine.desired)


if __name__ == "__main__":
    unittest.main()
