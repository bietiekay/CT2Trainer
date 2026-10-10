"""Wiring: disassemble is active in the AA pipeline (aa_debugger_api).

- ``prepare_program`` parses ``disassemble(addr, count)`` into a bounded
  node, reports it via capabilities, and round-trips through
  ``validate_program``; out-of-grammar shapes are refused at parse time.
- ``preflight_program`` executes the bounded read-only inspection through
  the injected DisassemblerPort (default: the owned iced-x86 backend) and
  returns it as an observation; without a port the record is refused
  visibly fail-closed before any effect.
- The engine gates activation on the port: the default iced route
  activates end-to-end (enable/disable round trip), an injected refusal
  fails closed before any allocation or write, and a record without
  disassemble capability never touches the factory.
"""
import tempfile
import unittest
from pathlib import Path

from test_native_engine_code import Coordinator
from test_native_lua_activation import Memory
from ct2trainer.native.aa_directives import DisassemblerError
from ct2trainer.native.aa_program import (ProgramError, dry_link_program,
                                           prepare_program, preflight_program,
                                           validate_program)
from ct2trainer.native.iced_disassembler import IcedDisassemblerPort
from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import NativeRuntimeError, TrainerEngine

PROCESS = "FixtureTarget.exe"
SOURCE = """[ENABLE]
disassemble(FixtureTarget.exe+0x10,3)
FixtureTarget.exe+0x20:
dd 1
[DISABLE]
FixtureTarget.exe+0x20:
dd 0"""
SIMPLE_SOURCE = """[ENABLE]
1040:
dd 1
[DISABLE]
1040:
dd 0"""


def _ct_path(root, source, name="owned.ct"):
    table = Path(root) / name
    table.write_text('<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
                     '<CheatEntry><ID>1</ID><Description>Owned disassemble</Description>'
                     '<VariableType>Auto Assembler Script</VariableType>'
                     '<AssemblerScript><![CDATA[' + source + ']]></AssemblerScript>'
                     '</CheatEntry></CheatEntries></CheatTable>',
                     encoding="utf-8")
    return table


class DisassembleParseTests(unittest.TestCase):
    def test_parse_embeds_bounded_node_and_capability(self):
        program = prepare_program(SOURCE, PROCESS, bitness=64)
        nodes = [node for node in program["enable"] if node["op"] == "disassemble"]
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0]["count"], 3)
        self.assertEqual(nodes[0]["address"], "FixtureTarget.exe+0x10")
        self.assertIn("disassemble", program["capabilities"])
        validate_program(program)

    def test_parse_refuses_wrong_argument_count(self):
        for source in (SOURCE.replace(",3)", ")"),
                       SOURCE.replace(",3)", ",3,4)")):
            with self.subTest(source=source), \
                    self.assertRaisesRegex(ProgramError,
                                           "address expression and an instruction count"):
                prepare_program(source, PROCESS, bitness=64)

    def test_parse_refuses_out_of_range_count(self):
        for count in ("0", "4097"):
            with self.subTest(count=count), \
                    self.assertRaisesRegex(ProgramError, "4096"):
                prepare_program(SOURCE.replace(",3)", "," + count + ")"),
                                PROCESS, bitness=64)

    def test_enable_without_executable_patch_stays_refused(self):
        source = """[ENABLE]
disassemble(FixtureTarget.exe+0x10,3)
[DISABLE]
1050:
db 0"""
        with self.assertRaisesRegex(ProgramError, "no executable patch or data"):
            prepare_program(source, PROCESS, bitness=64)


class DisassemblePreflightTests(unittest.TestCase):
    def setUp(self):
        self.memory = Memory()
        # nop, nop, ret at 0x1010
        self.memory.data[0x10:0x13] = b"\x90\x90\xc3"
        self.program = prepare_program(SOURCE, PROCESS, bitness=64)
        self.port = IcedDisassemblerPort(self.memory.read)

    def test_preflight_runs_iced_inspection_and_returns_observation(self):
        result = preflight_program(self.program, self.memory, {},
                                   disassembler=self.port)
        obs = result["observations"]
        self.assertEqual(len(obs), 1)
        self.assertEqual(obs[0]["address"], 0x1010)
        self.assertEqual(obs[0]["count"], 3)
        self.assertEqual([item["mnemonic"] for item in obs[0]["output"]],
                         ["nop", "nop", "ret"])
        self.assertEqual([item["address"] for item in obs[0]["output"]],
                         [0x1010, 0x1011, 0x1012])

    def test_preflight_without_port_refuses_visibly(self):
        with self.assertRaisesRegex(ProgramError, "DisassemblerPort"):
            preflight_program(self.program, self.memory, {})

    def test_dry_link_returns_same_observations(self):
        dry = dry_link_program(self.program, self.memory, {},
                               disassembler=self.port)
        self.assertTrue(dry["dry_run"])
        self.assertFalse(dry["publishable"])
        self.assertEqual(dry["observations"][0]["output"],
                         preflight_program(self.program, self.memory, {},
                                           disassembler=self.port)
                         ["observations"][0]["output"])

    def test_preflight_with_failing_port_raises_named_error(self):
        class FailingPort(IcedDisassemblerPort):
            def disassemble(self, address, count, bitness):
                raise DisassemblerError("invalid instruction at 0x1010; "
                                        "disassemble refused",
                                        address=address, count=count)
        with self.assertRaisesRegex(DisassemblerError, "invalid instruction"):
            preflight_program(self.program, self.memory, {},
                              disassembler=FailingPort(self.memory.read))


class DisassembleEngineWiringTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.memory = Memory()
        self.memory.data[0x10:0x13] = b"\x90\x90\xc3"
        self.engine = None

    def tearDown(self):
        if self.engine is not None and not self.engine.closed:
            self.engine.close()

    def make_engine(self, source=SOURCE, name="owned.ct", **kwargs):
        plan = compile_table(_ct_path(self.root, source, name), PROCESS)
        self.assertTrue(plan["entries"][0]["supported"],
                        plan["entries"][0]["reason"])
        self.engine = TrainerEngine(
            plan, state_dir=self.root / "state",
            process_lock_dir=self.root / "shared",
            memory_factory=lambda name: self.memory,
            hook_coordinator=Coordinator(), **kwargs)
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)
        return self.engine

    def test_default_iced_route_activates_and_round_trips(self):
        engine = self.make_engine()
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.memory.read(0x1020, 4), b"\x01\x00\x00\x00")
        self.assertIn(1, engine.applied)
        self.assertFalse(engine.toggle(1, False))
        self.assertEqual(self.memory.read(0x1020, 4), b"\x00\x00\x00\x00")
        self.assertNotIn(1, engine.applied)

    def test_injected_factory_refusal_fails_closed_before_any_effect(self):
        engine = self.make_engine(disassembler_factory=lambda memory: None)
        writes_before = len(self.memory.writes)
        with self.assertRaisesRegex(NativeRuntimeError,
                                    "disassembler binding was not provided"):
            engine.toggle(1, True)
        self.assertEqual(len(self.memory.writes), writes_before)
        self.assertNotIn(1, engine.applied)

    def test_failing_port_refuses_with_named_reason(self):
        def failing_factory(memory):
            class FailingPort(IcedDisassemblerPort):
                def disassemble(self, address, count, bitness):
                    raise DisassemblerError("invalid instruction at 0x1010; "
                                            "disassemble refused",
                                            address=address, count=count)
            return FailingPort(memory.read)
        engine = self.make_engine(disassembler_factory=failing_factory)
        with self.assertRaisesRegex(NativeRuntimeError, "invalid instruction"):
            engine.toggle(1, True)
        self.assertFalse(self.memory.writes)

    def test_factory_not_invoked_without_disassemble_capability(self):
        calls = []
        engine = self.make_engine(SIMPLE_SOURCE, name="simple.ct",
                                  disassembler_factory=lambda memory:
                                  calls.append(1))
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.memory.read(0x1040, 4), b"\x01\x00\x00\x00")
        self.assertEqual(calls, [])
        self.assertFalse(engine.toggle(1, False))
        self.assertEqual(self.memory.read(0x1040, 4), b"\x00\x00\x00\x00")


if __name__ == "__main__":
    unittest.main()
