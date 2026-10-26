"""RT-5 item G: createThread / threadWait capability gate (O22) - decision
pins.

Root-owned decision for this milestone: option (2) - keep the capability
gate; no thread backend ships in the staged runtime.  A bounded
owned-thread backend (owned-thread lifecycle, debug-event ownership,
cancellation, exact teardown in the disable path, journal receipt)
requires a root design review before it can land; the design sketch is
recorded in the lane report and the next-work roadmap, not in this
repository.

This file pins the EXACT current fail-closed refusal behavior so the
future decision starts from a byte-stable baseline:

- tokenizer stage (small grammar ``aa.compile_script`` /
  ``compile_one_shot``): ``Unsupported AA directive: createthread.`` /
  ``Unsupported AA directive: threadwait.`` - fires before any plan is
  built.
- plan stage (``aa_program.prepare_program``): a thread-only ENABLE
  section (no data/instruction/nops/readmem/reassemble node) hits the
  staged-runtime gate with the exact message; no partial plan is
  returned.
- converter stage (``compiler.compile_table``): the record stays blocked
  with the byte-stable composite reason (Witcher3 id 192 "Call Function"
  shape: ``createthread(get_item_name)`` over an empty [DISABLE]); no
  program/plan is emitted, requires/provides stay empty.
- assembly stage (``preflight_program`` / ``dry_link_program``): a
  thread-capable plan refuses with the exact injected-backend message
  before any effect and with zero backend calls.
- activation stage (``TrainerEngine.toggle`` on the default trainer, no
  ``thread_backend_factory``): the exact ``NativeRuntimeError``, no
  allocation, no symbol registration, no memory writes, entry not
  applied.
- positive control: an injected deterministic backend lifts exactly the
  missing binding - the same staged program round-trips byte-exact with
  one spawn.

Catalog census (launch base ``blocked-catalog-rt43-main``, 2026-10-26,
main @ 0a471a2): exactly 2 O22 rows, both Witcher3
(``...4.02HF1_G25v2.CT`` / ``...4.03_G25v2.CT``, id 192, path
``Archived (Ignore) / Retrieve Item Name (Its updated to not crash but I
made a better one) / Call Function``) with the composite reason above.
AA usage census over the 151-path local reference corpus: 77
first-word usages across 18 tables (26 createThread AA lines in 8
tables + 51 createThread Lua lines in 11 tables; zero threadWait
first-word lines).  Zero catalog movement: this lane is tests only.
"""
import re
import tempfile
import unittest
from pathlib import Path

from aa_directives_fixture_data import ScriptedThreadBackend
from test_native_engine_code import Coordinator
from test_native_lua_activation import Memory
from ct2trainer.native.aa import AAError, compile_one_shot, compile_script
from ct2trainer.native.aa_directives import ThreadDirectiveModel
from ct2trainer.native.aa_program import (ProgramError, dry_link_program,
                                          prepare_program, preflight_program)
from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import NativeRuntimeError, TrainerEngine

PROCESS = "FixtureTarget.exe"

# Byte-stable refusal strings (the decision-record baseline).
SMALL_CT = "Unsupported AA directive: createthread."
SMALL_TW = "Unsupported AA directive: threadwait."
GATE = ("createThread()/threadWait() are gated in the native staged "
        "runtime: no thread backend is part of the shipped trainer profile.")
COMPOSITE_CT = "Unsupported AA directive: createthread. Native assembly: " + GATE
COMPOSITE_TW = "Unsupported AA directive: threadwait. Native assembly: " + GATE
PREFLIGHT_CT = ("createThread requires an injected thread backend; record "
                "activation was refused before any effect.")
PREFLIGHT_TW = ("threadWait requires an injected thread backend; record "
                "activation was refused before any effect.")
ORDER = ("threadWait appears before any createThread in the selected "
         "phase.")
ENGINE_GATE = ("This record uses createThread()/threadWait(), but the "
              "thread binding was not provided for this trainer. The "
              "record was not activated. No target memory was allocated "
              "or changed.")
PARSE_CT_ARGS = "createThread requires one address expression."
PARSE_TW_ARGS = "threadWait takes no arguments."

# Mirrors the Witcher3 id 192 "Call Function" record verbatim: a
# thread-only ENABLE over an empty [DISABLE].
WITCHER3_SOURCE = "[ENABLE]\ncreatethread(get_item_name)\n[DISABLE]"
THREADWAIT_ONLY_SOURCE = "[ENABLE]\nthreadWait()\n[DISABLE]"

# Thread capability plus executable data: compiles (staged) and reaches
# the engine-level gate at activation.
THREAD_WITH_DATA_SOURCE = """[ENABLE]
createThread(FixtureTarget.exe+0x10)
threadWait()
FixtureTarget.exe+0x20:
dd 1
[DISABLE]
FixtureTarget.exe+0x20:
dd 0"""


def _ct_path(root, source, entry_id, description):
    table = Path(root) / "owned.ct"
    table.write_text('<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
                     f'<CheatEntry><ID>{entry_id}</ID>'
                     f'<Description>{description}</Description>'
                     '<VariableType>Auto Assembler Script</VariableType>'
                     '<AssemblerScript><![CDATA[' + source +
                     ']]></AssemblerScript></CheatEntry>'
                     '</CheatEntries></CheatTable>', encoding="utf-8")
    return table


class SmallGrammarGateTests(unittest.TestCase):
    """Tokenizer stage: the small grammar refuses both directives before
    any plan exists."""

    def test_small_grammar_createthread_refusal_is_byte_exact(self):
        with self.assertRaises(AAError) as ctx:
            compile_script(WITCHER3_SOURCE)
        self.assertEqual(str(ctx.exception), SMALL_CT)

    def test_small_grammar_threadwait_refusal_is_byte_exact(self):
        with self.assertRaises(AAError) as ctx:
            compile_script(THREADWAIT_ONLY_SOURCE)
        self.assertEqual(str(ctx.exception), SMALL_TW)

    def test_one_shot_grammar_refusal_is_byte_exact(self):
        with self.assertRaises(AAError) as ctx:
            compile_one_shot(WITCHER3_SOURCE)
        self.assertEqual(str(ctx.exception), SMALL_CT)
        with self.assertRaises(AAError) as ctx:
            compile_one_shot(THREADWAIT_ONLY_SOURCE)
        self.assertEqual(str(ctx.exception), SMALL_TW)


class PlanGateTests(unittest.TestCase):
    """Plan stage: the staged-runtime gate for thread-only ENABLE
    sections."""

    def test_plan_gate_createthread_only_enable_is_byte_exact(self):
        with self.assertRaises(ProgramError) as ctx:
            prepare_program(WITCHER3_SOURCE, PROCESS, bitness=64)
        self.assertEqual(str(ctx.exception), GATE)

    def test_plan_gate_threadwait_only_enable_is_byte_exact(self):
        with self.assertRaises(ProgramError) as ctx:
            prepare_program(THREADWAIT_ONLY_SOURCE, PROCESS, bitness=64)
        self.assertEqual(str(ctx.exception), GATE)

    def test_plan_gate_does_not_fire_when_executable_data_is_present(self):
        program = prepare_program(THREAD_WITH_DATA_SOURCE, PROCESS, bitness=64)
        self.assertEqual(
            [node["op"] for node in program["enable"]],
            ["createthread", "threadwait", "cursor", "data"])
        self.assertIn("createthread", program["capabilities"])
        self.assertIn("threadwait", program["capabilities"])
        self.assertFalse(program["one_shot"])

    def test_parser_argument_refusals_are_byte_exact(self):
        # parse-time rejections carry a stable "Line N: " prefix; the message
        # body after the prefix is what is byte-stable.
        base = "\nFixtureTarget.exe+0x20:\ndd 1\n[DISABLE]\n" \
               "FixtureTarget.exe+0x20:\ndd 0"
        cases = [
            ("[ENABLE]\ncreateThread()" + base, PARSE_CT_ARGS),
            ("[ENABLE]\ncreateThread(a,b)" + base, PARSE_CT_ARGS),
            ("[ENABLE]\nthreadWait(1)" + base, PARSE_TW_ARGS),
        ]
        for source, message in cases:
            with self.subTest(source=source.splitlines()[1]), \
                    self.assertRaisesRegex(
                        ProgramError,
                        r"^Line \d+: " + re.escape(message) + r"$"):
                prepare_program(source, PROCESS, bitness=64)


class ConverterGateTests(unittest.TestCase):
    """Converter stage: the blocked row carries the byte-stable composite
    reason and emits no partial program/plan."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def _entry(self, source, entry_id, description):
        path = _ct_path(self.root, source, entry_id, description)
        plan = compile_table(path, PROCESS)
        self.assertEqual(len(plan["entries"]), 1)
        return plan["entries"][0]

    def test_witcher3_shape_row_is_blocked_with_exact_composite_reason(self):
        entry = self._entry(WITCHER3_SOURCE, 192, "Call Function")
        self.assertFalse(entry["supported"])
        self.assertEqual(entry["reason"], COMPOSITE_CT)
        self.assertEqual(entry["path"], "Call Function")

    def test_threadwait_shape_row_is_blocked_with_exact_composite_reason(self):
        entry = self._entry(THREADWAIT_ONLY_SOURCE, 193, "Wait Only")
        self.assertFalse(entry["supported"])
        self.assertEqual(entry["reason"], COMPOSITE_TW)

    def test_blocked_row_emits_no_partial_plan(self):
        for source in (WITCHER3_SOURCE, THREADWAIT_ONLY_SOURCE):
            with self.subTest(source=source.splitlines()[1]):
                entry = self._entry(source, 194, "No Partial Plan")
                self.assertFalse(entry["supported"])
                self.assertNotIn("program", entry)
                self.assertNotIn("enable", entry)
                self.assertNotIn("disable", entry)
                self.assertEqual(entry["requires"], [])
                self.assertEqual(entry["provides"], [])
                self.assertEqual(entry["dependency_ids"], [])

    def test_thread_plus_data_stages_instead_of_blocking(self):
        entry = self._entry(THREAD_WITH_DATA_SOURCE, 195, "Thread plus data")
        self.assertTrue(entry["supported"], entry["reason"])
        self.assertEqual(entry["reason"],
                         "Native assembly; activation requires a "
                         "verified target safe point.")
        self.assertIn("program", entry)


class AssemblyGateTests(unittest.TestCase):
    """Assembly stage: preflight / dry-link refuse the missing backend
    before any effect."""

    def setUp(self):
        self.memory = Memory()
        self.program_ct = prepare_program(
            THREAD_WITH_DATA_SOURCE, PROCESS, bitness=64)
        self.program_tw = prepare_program(
            "[ENABLE]\nthreadWait()\nFixtureTarget.exe+0x20:\ndd 1"
            "\n[DISABLE]\nFixtureTarget.exe+0x20:\ndd 0",
            PROCESS, bitness=64)

    def test_preflight_createthread_without_backend_is_byte_exact(self):
        with self.assertRaises(ProgramError) as ctx:
            preflight_program(self.program_ct, self.memory, {})
        self.assertEqual(str(ctx.exception), PREFLIGHT_CT)

    def test_preflight_threadwait_without_backend_is_byte_exact(self):
        with self.assertRaises(ProgramError) as ctx:
            preflight_program(self.program_tw, self.memory, {})
        self.assertEqual(str(ctx.exception), PREFLIGHT_TW)

    def test_dry_link_without_backend_is_byte_exact(self):
        with self.assertRaises(ProgramError) as ctx:
            dry_link_program(self.program_ct, self.memory, {})
        self.assertEqual(str(ctx.exception), PREFLIGHT_CT)
        with self.assertRaises(ProgramError) as ctx:
            dry_link_program(self.program_tw, self.memory, {})
        self.assertEqual(str(ctx.exception), PREFLIGHT_TW)

    def test_threadwait_before_createthread_with_backend_is_byte_exact(self):
        backend = ScriptedThreadBackend()
        model = ThreadDirectiveModel(backend)
        with self.assertRaises(ProgramError) as ctx:
            preflight_program(self.program_tw, self.memory, {},
                              thread_model=model)
        self.assertEqual(str(ctx.exception), ORDER)
        self.assertEqual(backend.calls, [])


class EngineGateTests(unittest.TestCase):
    """Activation stage: the default trainer refuses the thread binding
    before any allocation, symbol registration or memory write."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.memory = Memory()
        self.engine = None

    def tearDown(self):
        if self.engine is not None and not self.engine.closed:
            self.engine.close()

    def make_engine(self, **kwargs):
        path = _ct_path(self.root, THREAD_WITH_DATA_SOURCE, 1,
                        "Thread plus data")
        plan = compile_table(path, PROCESS)
        entry = plan["entries"][0]
        self.assertTrue(entry["supported"], entry["reason"])
        self.engine = TrainerEngine(
            plan, state_dir=self.root / "state",
            process_lock_dir=self.root / "shared",
            memory_factory=lambda name: self.memory,
            hook_coordinator=Coordinator(), **kwargs)
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)
        return self.engine

    def test_default_engine_thread_gate_is_byte_exact_with_no_side_effects(self):
        engine = self.make_engine()
        symbols_before = dict(engine.symbols)
        data_before = bytes(self.memory.data)
        with self.assertRaises(NativeRuntimeError) as ctx:
            engine.toggle(1, True)
        self.assertEqual(str(ctx.exception), ENGINE_GATE)
        # No memory write, no allocation side effect, no symbol
        # registration, entry not applied.
        self.assertEqual(self.memory.writes, [])
        self.assertEqual(bytes(self.memory.data), data_before)
        self.assertEqual(dict(engine.symbols), symbols_before)
        self.assertNotIn(1, engine.applied)

    def test_injected_backend_lifts_only_the_missing_binding(self):
        # Positive control: with a deterministic backend injected, the
        # same staged program activates and round-trips byte-exact, so
        # the gate is exactly the missing binding.
        backend = ScriptedThreadBackend()
        engine = self.make_engine(
            thread_backend_factory=lambda memory:
            ThreadDirectiveModel(backend))
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.memory.read(0x1020, 4), b"\x01\x00\x00\x00")
        self.assertEqual([call for call in backend.calls
                          if call[0] == "spawn"], [("spawn", 1)])
        self.assertFalse(engine.toggle(1, False))
        self.assertEqual(self.memory.read(0x1020, 4), b"\x00\x00\x00\x00")


if __name__ == "__main__":
    unittest.main()
