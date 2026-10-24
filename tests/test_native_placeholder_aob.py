"""WP-57 (GC-E20): placeholder-token AOB scans (``s<N>.<M>``).

A scan pattern may define bounded capture tokens: ``s<N>.<M>`` with index
1-9999 (no leading zeros) and M in {1, 2}. Each token matches any M bytes
and captures them at scan time.  Bare ``s<N>`` patch-side references are
substituted by the program-dialect linker only, from the scan-time
captures (db byte expansion and instruction operand integers, little
endian).  The classic data dialect, assertions, data literals, expression
positions, and the fixed-byte consumers (nth-AOB, luaCall AOB) keep their
exact pre-placeholder refusal text, and the region-symbol provider pin
stays untouched.  Captures are persisted in the hook journal so the
disable phase restores exact original bytes without rescanning.
"""
from __future__ import annotations

import json
import tempfile
import unittest
import xml.sax.saxutils
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ct2trainer.native import patterns
from ct2trainer.native.aa_luacall import LuaCallParseError, analyze_luacall_program
from ct2trainer.native.aa_program import (ProgramError, link_program,
                                          prepare_program, preflight_program,
                                          dry_link_program)
from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import TrainerEngine
from ct2trainer.native.nth_aob import (NthAOBError, definition_from_call,
                                       validate_definition)
from test_native_engine_code import CodeMemory, Coordinator

PROCESS = "FixtureTarget.exe"
SEED = bytes.fromhex("488B9F6002000031C0")
LOG_NAME = "ct2trainer-debug.log"

NOT_DEFINED = "Placeholder token s1 is not defined in the scan pattern."
DUPLICATE = "Placeholder token s1 is defined more than once in the pattern."
BYTE_COUNT = "Placeholder token byte count must be 1 or 2."
TOO_MANY = "More than 16 placeholder tokens in one pattern."
ASSERTION_REFUSAL = "Placeholder tokens are not supported in assertions or data literals."
NIBBLE_REFUSAL = "AOB pattern contains an invalid hexadecimal/wildcard nibble."


def table_xml(body: str) -> str:
    return ('<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
            + body + "</CheatEntries></CheatTable>")


def script_entry(entry_id: int, description: str, script: str) -> str:
    return (f'<CheatEntry><ID>{entry_id}</ID>'
            f'<Description>{description}</Description>'
            '<VariableType>Auto Assembler Script</VariableType>'
            f'<AssemblerScript>{xml.sax.saxutils.escape(script)}</AssemblerScript>'
            '</CheatEntry>')


class PlaceholderMemory(CodeMemory):
    """Module bytes plus one executable cave, with wildcard-aware scans.

    ``_query`` reports actual backend evidence: committed executable module
    bytes (PAGE_EXECUTE_READ) and, per allocation, the protection the hook
    layer requested through ``protect_allocation``.
    """

    def __init__(self, pid=123, creation_time=456, seeds=()):
        super().__init__(pid=pid, creation_time=creation_time)
        self.data = bytearray(2048)
        for offset, raw in seeds:
            self.data[offset:offset + len(raw)] = raw
        self.allocations = {}
        self.protection_map = {}
        self.protections = []

    def scan_module(self, name, pattern):
        self.module(name)
        tokens = patterns.expanded_pattern(pattern).split()
        for start in range(len(self.data) - len(tokens) + 1):
            window = self.data[start:start + len(tokens)]
            if all(tok == "??" or all(ch == "?" or ch == f"{byte:02X}"[i]
                                      for i, ch in enumerate(tok))
                   for tok, byte in zip(tokens, window)):
                return self.base + start
        raise OSError("The module byte pattern was not found in readable committed memory.")

    def allocate(self, size, near=None):
        address = self.base + 512
        self.allocations[address] = size
        return address

    def allocation_size(self, address):
        return self.allocations.get(address, 0)

    def protect_allocation(self, address, executable=True, writable=False):
        self.protections.append((address, executable, writable))
        self.protection_map[address] = (0x40 if writable else 0x20) if executable else 0x04

    def _query(self, address):
        size = self.allocations.get(address)
        if size is None:
            # Committed module bytes: executable page, never an RW literal.
            return SimpleNamespace(BaseAddress=self.base, AllocationBase=0,
                                   RegionSize=len(self.data), State=0x1000,
                                   Protect=0x40)
        return SimpleNamespace(BaseAddress=address, AllocationBase=address,
                               RegionSize=size, State=0x1000,
                               Protect=self.protection_map.get(address, 0x04))

    def release(self, address):
        self.allocations.pop(address, None)
        self.protection_map.pop(address, None)

    def is_executable(self, address, size):
        return super().is_executable(address, size) or any(
            base <= address and address + size <= base + length
            for base, length in self.allocations.items())


class PlaceholderPatternTests(unittest.TestCase):
    """patterns.py: token grammar, bounds, canonical form, capture mapping."""

    def test_definition_normalizes_to_single_canonical_span(self):
        self.assertEqual(patterns.normalize_pattern("48 8b 9f s1.2 00 00 31 c0"),
                         "48 8B 9F S1.2 00 00 31 C0")
        self.assertEqual(patterns.pattern_byte_length("48 8B 9F s1.2 00 00 31 C0"), 9)
        self.assertEqual(patterns.expanded_pattern("48 8B 9F S1.2 00 00 31 C0"),
                         "48 8B 9F ?? ?? 00 00 31 C0")
        self.assertEqual(patterns.placeholder_spans("48 8B 9F S1.2 00 00 31 C0"),
                         {"s1": (3, 2)})
        self.assertTrue(patterns.pattern_matches("48 8B 9F S1.2 00 00 31 C0", SEED))
        self.assertFalse(patterns.pattern_matches("48 8B 9F S1.2 00 00 32 C0", SEED))
        # Idempotent canonical form.
        self.assertEqual(patterns.normalize_pattern("48 8B 9F S1.2 00 00 31 C0"),
                         "48 8B 9F S1.2 00 00 31 C0")

    def test_bare_reference_in_a_scan_pattern_is_refused(self):
        for pattern in ("s1", "48 8B s1 00", "S1 48"):
            with self.assertRaises(ValueError) as ctx:
                patterns.normalize_pattern(pattern)
            self.assertIn(NOT_DEFINED, str(ctx.exception))

    def test_duplicate_name_in_one_pattern_is_refused(self):
        with self.assertRaises(ValueError) as ctx:
            patterns.normalize_pattern("48 s1.2 s1.2 00")
        self.assertEqual(str(ctx.exception), DUPLICATE)

    def test_byte_count_out_of_range_is_refused(self):
        for pattern in ("s1.3", "s1.0", "s2.12"):
            with self.assertRaises(ValueError) as ctx:
                patterns.normalize_pattern(pattern)
            self.assertEqual(str(ctx.exception), BYTE_COUNT)

    def test_more_than_sixteen_tokens_in_one_pattern_is_refused(self):
        seventeen = "48 " + " ".join(f"s{n}.1" for n in range(1, 18))
        with self.assertRaises(ValueError) as ctx:
            patterns.normalize_pattern(seventeen)
        self.assertEqual(str(ctx.exception), TOO_MANY)
        sixteen = "48 " + " ".join(f"s{n}.1" for n in range(1, 17))
        self.assertEqual(patterns.pattern_byte_length(sixteen), 17)

    def test_invalid_indices_keep_the_nibble_refusal(self):
        for pattern in ("s0.2", "s01.2", "s12345.1"):
            with self.assertRaises(ValueError) as ctx:
                patterns.normalize_pattern(pattern)
            self.assertEqual(str(ctx.exception), NIBBLE_REFUSAL)

    def test_token_spans_and_counts_are_derived_from_the_definition(self):
        spans = patterns.placeholder_spans("s1.1 48 s2.2 00")
        self.assertEqual(spans, {"s1": (0, 1), "s2": (2, 2)})
        self.assertEqual(patterns.pattern_byte_length("s1.1 48 s2.2 00"), 5)

    def test_symbol_shape_detection(self):
        shaped = {"s1", "S1", "s9999", "s1.2", "S1.1", "s1234", "s1.123"}
        plain = {"s0", "s01", "s10000", "s12345", "s1x", "xs1", "s", "s1.2.3"}
        for name in shaped:
            self.assertTrue(patterns.symbol_is_placeholder_shaped(name), name)
        for name in plain:
            self.assertFalse(patterns.symbol_is_placeholder_shaped(name), name)
        self.assertFalse(patterns.symbol_is_placeholder_shaped(None))
        self.assertFalse(patterns.symbol_is_placeholder_shaped(1))


class PlaceholderCaptureValidationTests(unittest.TestCase):
    """validate_placeholder_captures: the fail-closed capture mapping."""

    def test_none_and_empty_map_to_empty(self):
        self.assertEqual(patterns.validate_placeholder_captures(None), {})
        self.assertEqual(patterns.validate_placeholder_captures({}), {})

    def test_valid_mapping_is_canonicalized(self):
        self.assertEqual(patterns.validate_placeholder_captures({"S1": "6002", "s2": "31"}),
                         {"s1": "6002", "s2": "31"})

    def test_non_mapping_is_refused(self):
        for value in ("s1", ["s1"], 1):
            with self.assertRaises(ValueError) as ctx:
                patterns.validate_placeholder_captures(value)
            self.assertEqual(str(ctx.exception),
                             "Placeholder captures must be a bounded mapping of token name to hex bytes.")

    def test_more_than_sixteen_captures_is_refused(self):
        captures = {f"s{n}": "6002" for n in range(1, 18)}
        with self.assertRaises(ValueError) as ctx:
            patterns.validate_placeholder_captures(captures)
        self.assertEqual(str(ctx.exception), "More than 16 placeholder captures supplied.")

    def test_invalid_names_are_refused(self):
        for name in ("s0", "s01", "s10000", "anchor", "", 1):
            with self.assertRaises(ValueError) as ctx:
                patterns.validate_placeholder_captures({name: "60"})
            self.assertIn("Invalid placeholder capture name", str(ctx.exception))

    def test_case_ambiguous_names_are_refused(self):
        with self.assertRaises(ValueError) as ctx:
            patterns.validate_placeholder_captures({"S1": "6002", "s1": "6002"})
        self.assertEqual(str(ctx.exception),
                         "Placeholder captures define s1 more than once with different case.")

    def test_wrong_byte_counts_are_refused(self):
        for value in ("", "6", "600", "60020", "G002", "60 02", 96):
            with self.assertRaises(ValueError) as ctx:
                patterns.validate_placeholder_captures({"s1": value})
            self.assertEqual(str(ctx.exception),
                             "Placeholder capture s1 must be 1 or 2 hex bytes.")


class PlaceholderProgramRefusalTests(unittest.TestCase):
    """prepare_program: every named refusal at every position, no writes."""

    def _refusal(self, source, expected):
        with self.assertRaises(ProgramError) as ctx:
            prepare_program(source, PROCESS)
        self.assertIn(expected, str(ctx.exception))

    def test_bare_ref_in_a_scan_pattern_is_refused_at_parse_time(self):
        self._refusal("[ENABLE]\n"
                      "aobscanmodule(Anchor, FixtureTarget.exe, 48 8B s1 00)\n"
                      "[DISABLE]\n", NOT_DEFINED)

    def test_cross_scan_duplicate_name_is_refused(self):
        self._refusal("[ENABLE]\n"
                      "aobscanmodule(AnchorOne, FixtureTarget.exe, 48 8B 9F s1.2 00 00)\n"
                      "aobscanmodule(AnchorTwo, FixtureTarget.exe, 48 8B 9F s1.2 00 00)\n"
                      "[DISABLE]\n", DUPLICATE)

    def test_assert_pattern_tokens_are_refused(self):
        self._refusal("[ENABLE]\n"
                      "aobscanmodule(Anchor, FixtureTarget.exe, 48 8B 9F s1.2 00 00)\n"
                      "assert(Anchor, 48 s1.2 00 00)\n"
                      "[DISABLE]\n", ASSERTION_REFUSAL)

    def test_definition_form_in_data_is_refused(self):
        self._refusal("[ENABLE]\n"
                      "aobscanmodule(Anchor, FixtureTarget.exe, 48 8B 9F s1.2 00 00)\n"
                      "Anchor:\n"
                      "db 48 s1.2\n"
                      "[DISABLE]\n", ASSERTION_REFUSAL)

    def test_bare_ref_in_wide_data_directives_is_refused(self):
        for directive in ("dw", "dd", "dq"):
            self._refusal("[ENABLE]\n"
                          "aobscanmodule(Anchor, FixtureTarget.exe, 48 8B 9F s1.2 00 00)\n"
                          "Anchor:\n"
                          f"{directive} s1\n"
                          "[DISABLE]\n", ASSERTION_REFUSAL)

    def test_definition_form_in_instruction_operands_is_refused(self):
        self._refusal("[ENABLE]\n"
                      "aobscanmodule(Anchor, FixtureTarget.exe, 48 8B 9F s1.2 00 00)\n"
                      "alloc(Cave, 256)\n"
                      "Cave:\n"
                      " mov rbx, [rdi+s1.2]\n"
                      "[DISABLE]\n"
                      "dealloc(Cave)\n", ASSERTION_REFUSAL)

    def test_expression_positions_are_refused(self):
        self._refusal("[ENABLE]\n"
                      "aobscanmodule(Anchor, FixtureTarget.exe, 48 8B 9F s1.2 00 00)\n"
                      "define(Out, s1+2)\n"
                      "[DISABLE]\n", ASSERTION_REFUSAL)
        self._refusal("[ENABLE]\n"
                      "aobscanmodule(Anchor, FixtureTarget.exe, 48 8B 9F s1.2 00 00)\n"
                      "aobscanregion(Region, s1, s1+100, 48 8B)\n"
                      "[DISABLE]\n", ASSERTION_REFUSAL)

    def test_undefined_bare_ref_in_db_is_refused(self):
        self._refusal("[ENABLE]\n"
                      "aobscanmodule(Anchor, FixtureTarget.exe, 48 8B 9F s2.1 00 00)\n"
                      "Anchor:\n"
                      "db s1\n"
                      "[DISABLE]\n", NOT_DEFINED)

    def test_undefined_bare_ref_in_instruction_operands_is_refused(self):
        self._refusal("[ENABLE]\n"
                      "aobscanmodule(Anchor, FixtureTarget.exe, 48 8B 9F s2.1 00 00)\n"
                      "alloc(Cave, 256)\n"
                      "Cave:\n"
                      " mov rbx, [rdi+s1]\n"
                      "[DISABLE]\n"
                      "dealloc(Cave)\n", NOT_DEFINED)

    def test_quoted_s1_literal_and_uppercase_definition_are_admitted(self):
        program = prepare_program("[ENABLE]\n"
                                  "aobscanmodule(Anchor, FixtureTarget.exe, 48 8B 9F S1.2 00 00)\n"
                                  "registersymbol(Anchor)\n"
                                  "Anchor:\n"
                                  'db "s1"\n'
                                  " db 90\n"
                                  "[DISABLE]\n"
                                  "Anchor:\n"
                                  'db "s1"\n'
                                  " db 48\n"
                                  "unregistersymbol(Anchor)\n", PROCESS)
        # The quoted literal is inert; only the defined token is captured.
        self.assertEqual(program["requires"], [])
        self.assertEqual(patterns.placeholder_spans(program["enable"][0]["pattern"]),
                         {"s1": (3, 2)})

    def test_scan_region_argument_count_still_refused(self):
        self._refusal("[ENABLE]\n"
                      'aobscanregion(Region, "48 8B")\n'
                      "[DISABLE]\n", "aobscanregion requires 4 arguments.")

    def test_capture_conflict_is_refused_at_preflight(self):
        program = prepare_program("[ENABLE]\n"
                                  "aobscanmodule(Anchor, FixtureTarget.exe, "
                                  "48 8B 9F s1.2 00 00 31 C0)\n"
                                  "Anchor:\n"
                                  " db 90\n"
                                  "[DISABLE]\n"
                                  "Anchor:\n"
                                  " db 48\n", PROCESS)

        class Memory:
            pointer_size = 8

            def module(self, name):
                return 0x10000, 2048

            def read(self, address, size):
                return SEED

            def scan_module(self, name, pattern):
                return 0x10000 + 100

        with self.assertRaises(ProgramError) as ctx:
            preflight_program(program, Memory(), captured_placeholders={"s1": "FFFF"})
        self.assertEqual(str(ctx.exception),
                         "Captured placeholder bytes changed while linking the patch.")

    def test_invalid_capture_mapping_is_refused_at_preflight(self):
        program = prepare_program("[ENABLE]\n"
                                  "aobscanmodule(Anchor, FixtureTarget.exe, "
                                  "48 8B 9F s1.2 00 00)\n"
                                  "Anchor:\n"
                                  " db 90\n"
                                  "[DISABLE]\n"
                                  "Anchor:\n"
                                  " db 48\n", PROCESS)

        class Memory:
            pointer_size = 8

        with self.assertRaises(ProgramError) as ctx:
            preflight_program(program, Memory(), captured_placeholders="not-a-mapping")
        self.assertIn("Placeholder captures must be a bounded mapping of token name to hex bytes.",
                      str(ctx.exception))


class PlaceholderLinkSubstitutionTests(unittest.TestCase):
    """link_program: capture substitution beats coincidental symbol names."""

    def test_capture_beats_a_symbol_of_the_same_name(self):
        program = prepare_program("[ENABLE]\n"
                                  "aobscanmodule(PatchAnchor, FixtureTarget.exe, "
                                  "48 8B 9F s1.2 00 00 31 C0)\n"
                                  "registersymbol(PatchAnchor)\n"
                                  "alloc(MyCode, 256)\n"
                                  "MyCode:\n"
                                  " mov rbx, [rdi+s1]\n"
                                  " xor eax, eax\n"
                                  " jmp PatchAnchor+9\n"
                                  "PatchAnchor:\n"
                                  " db 48 8B 9F s1 00 00\n"
                                  " db B0 01\n"
                                  "[DISABLE]\n"
                                  "PatchAnchor:\n"
                                  " db 48 8B 9F s1 00 00\n"
                                  " db 31 C0\n"
                                  "unregistersymbol(PatchAnchor)\n"
                                  "dealloc(MyCode)\n", PROCESS)
        memory = PlaceholderMemory(seeds=[(100, SEED)])
        allocations = {"MyCode": {"address": memory.base + 512, "size": 598,
                                  "executable": True, "writable": False}}
        # An external symbol named s1 (another record's register) must not
        # shadow the scan-captured value in the instruction operand.
        linked = link_program(program, memory, {"s1": 0x400000}, allocations)
        cave = [block for block in linked["blocks"] if block["is_allocation"]][0]
        # Captured displacement 0x260 little-endian: 60 02 00 00.
        self.assertTrue(cave["bytes"].startswith("488B9F60020000"), cave["bytes"])
        self.assertNotIn("00004000", cave["bytes"], cave["bytes"])
        self.assertEqual(linked["captured_placeholders"], {"s1": "6002"})
        # The disable phase resolves s1 from the captures alone (no rescan).
        disabled = link_program(program, memory, linked["symbols"], allocations,
                                phase="disable",
                                captured_placeholders=linked["captured_placeholders"])
        live = [block for block in disabled["blocks"] if not block["is_allocation"]][0]
        self.assertEqual(live["bytes"], live["original"])


class FixedByteConsumerTests(unittest.TestCase):
    """nth-AOB and luaCall AOB keep the byte-identical nibble refusal."""

    def test_nth_aob_placeholder_keeps_the_nibble_refusal(self):
        with self.assertRaises(NthAOBError) as ctx:
            definition_from_call('ct2trainerNthAOB("nthAnchor","FixtureTarget.exe",'
                                 '"48 8B s1.2 00 00",1)', 1)
        self.assertEqual(str(ctx.exception), NIBBLE_REFUSAL)
        with self.assertRaises(NthAOBError) as ctx:
            validate_definition({"op": "nth_aobscan", "symbol": "NthAnchor",
                                 "module": "FixtureTarget.exe",
                                 "pattern": "48 8B S1.2 00 00",
                                 "occurrence": 1, "part_index": 1,
                                 "helper": "ct2trainerNthAOB"})
        self.assertEqual(str(ctx.exception), NIBBLE_REFUSAL)
        with self.assertRaises(NthAOBError) as ctx:
            definition_from_call('ct2trainerNthAOB("nthAnchor","FixtureTarget.exe",'
                                 '"48 8B s1 00 00",1)', 1)
        self.assertEqual(str(ctx.exception), NIBBLE_REFUSAL)

    def test_luacall_aob_placeholder_keeps_the_nibble_refusal(self):
        source = ('[ENABLE]\n'
                  'luaCall(lua_aobscan("AnchorSym","FixtureTarget.exe","48 8B s1.2 00 00"))\n'
                  'AnchorSym:\n'
                  'db 01\n')
        with self.assertRaises(LuaCallParseError) as ctx:
            analyze_luacall_program(source)
        self.assertIn(NIBBLE_REFUSAL, str(ctx.exception))


class PlaceholderEngineTests(unittest.TestCase):
    """Program dialect: link substitution, journal persistence, re-enable."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="ct2-wp57-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.cwd = self.root / "cwd"
        self.cwd.mkdir()
        self.memory = PlaceholderMemory(seeds=[(100, SEED)])
        self.engine = None

    def tearDown(self):
        if self.engine is not None and not self.engine.closed:
            self.engine.close()

    def _start(self, script, state="state", shared="shared"):
        table = self.root / "table.ct"
        table.write_text(table_xml(script_entry(1, "placeholder", script)),
                         encoding="utf-8")
        plan = compile_table(str(table), PROCESS, debug_log=True)
        self.assertTrue(plan["entries"][0]["supported"], plan["entries"][0].get("reason"))
        with patch("pathlib.Path.cwd", return_value=self.cwd):
            self.engine = TrainerEngine(plan, state_dir=self.root / state,
                                        process_lock_dir=self.root / shared,
                                        memory_factory=lambda name: self.memory,
                                        hook_coordinator=Coordinator())
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)
        return plan

    def test_enable_disable_journal_roundtrip_with_captures(self):
        script = ("[ENABLE]\n"
                  "aobscanmodule(PatchAnchor, FixtureTarget.exe, 48 8B 9F s1.2 00 00 31 C0)\n"
                  "registersymbol(PatchAnchor)\n"
                  "alloc(MyCode, 256)\n"
                  "MyCode:\n"
                  " mov rbx, [rdi+s1]\n"
                  " xor eax, eax\n"
                  " jmp PatchAnchor+9\n"
                  "PatchAnchor:\n"
                  " db 48 8B 9F s1 00 00\n"
                  " db B0 01\n"
                  "[DISABLE]\n"
                  "PatchAnchor:\n"
                  " db 48 8B 9F s1 00 00\n"
                  " db 31 C0\n"
                  "unregistersymbol(PatchAnchor)\n"
                  "dealloc(MyCode)\n")
        self._start(script)
        base = self.memory.base
        original = bytes(self.memory.data)
        self.engine.toggle(1, True)
        # Live patch: captured displacement inline + new tail byte.
        self.assertEqual(self.memory.read(base + 100, 9),
                         bytes.fromhex("488B9F60020000B001"))
        # Cave assembled the captured bytes as a little-endian displacement.
        cave = self.memory.read(base + 512, 19)
        self.assertEqual(cave[:7], bytes.fromhex("488B9F60020000"))
        self.assertEqual(self.memory.read(base + 519, 2), bytes.fromhex("31C0"))
        self.assertEqual(self.engine.placeholder_captures, {1: {"s1": "6002"}})
        # The journal persists the captures while enabled.
        journals = list((self.root / "state" / "hooks").glob("*.json"))
        self.assertEqual(len(journals), 1)
        document = json.loads(journals[0].read_text(encoding="utf-8"))
        self.assertEqual(document["captured_placeholders"], {"s1": "6002"})
        self.assertEqual(document["state"], "enabled")
        # The debug log carries the scan-time captures.
        events = [json.loads(line) for line in
                  (self.cwd / LOG_NAME).read_text(encoding="utf-8").splitlines()
                  if line.strip()]
        scans = [event for event in events if event["event"] == "scan"]
        self.assertEqual(len(scans), 1)
        self.assertEqual(scans[0]["symbol"], "PatchAnchor")
        self.assertEqual(scans[0]["captured_placeholders"], {"s1": "6002"})
        # Disable restores the live entry byte-exact from the captures
        # (no rescan); the published cave is retained until target exit.
        self.engine.toggle(1, False)
        self.assertEqual(self.memory.read(base + 100, 9), SEED)
        self.assertEqual(self.memory.read(base + 512, 14),
                         bytes.fromhex("488B9F6002000031C0E95FFEFFFF"))
        self.assertNotIn(1, self.engine.placeholder_captures)
        self.assertNotIn("patchanchor", self.engine.symbols)
        # The retired journal keeps the captures for recovery provenance.
        document = json.loads(journals[0].read_text(encoding="utf-8"))
        self.assertEqual(document["captured_placeholders"], {"s1": "6002"})
        self.assertEqual(document["state"], "retired")
        # Re-enable works against the same target and recaptures.
        self.engine.toggle(1, True)
        self.assertEqual(self.memory.read(base + 100, 9),
                         bytes.fromhex("488B9F60020000B001"))
        self.assertEqual(self.engine.placeholder_captures, {1: {"s1": "6002"}})
        self.engine.toggle(1, False)

    def test_multi_token_capture_in_cave_and_disable(self):
        script = ("[ENABLE]\n"
                  "aobscanmodule(PatchAnchor, FixtureTarget.exe, 48 8B 9F s1.2 00 00 s2.1 C0)\n"
                  "registersymbol(PatchAnchor)\n"
                  "alloc(MyCode, 256)\n"
                  "MyCode:\n"
                  " mov rbx, [rdi+s1]\n"
                  " add al, s2\n"
                  " jmp PatchAnchor+9\n"
                  "PatchAnchor:\n"
                  " db 48 8B 9F s1 00 00\n"
                  " db B0 01\n"
                  "[DISABLE]\n"
                  "PatchAnchor:\n"
                  " db 48 8B 9F s1 00 00\n"
                  " db s2 C0\n"
                  "unregistersymbol(PatchAnchor)\n"
                  "dealloc(MyCode)\n")
        plan = self._start(script)
        base = self.memory.base
        self.engine.toggle(1, True)
        self.assertEqual(self.engine.placeholder_captures,
                         {1: {"s1": "6002", "s2": "31"}})
        cave = self.memory.read(base + 512, 20)
        self.assertEqual(cave[:7], bytes.fromhex("488B9F60020000"))
        self.assertEqual(cave[7:9], bytes.fromhex("0431"))
        journals = list((self.root / "state" / "hooks").glob("*.json"))
        document = json.loads(journals[0].read_text(encoding="utf-8"))
        self.assertEqual(document["captured_placeholders"], {"s1": "6002", "s2": "31"})
        self.engine.toggle(1, False)
        # Live entry restored from the captures; cave retained until exit.
        self.assertEqual(self.memory.read(base + 100, 9), SEED)
        self.assertEqual(self.memory.read(base + 512, 14),
                         bytes.fromhex("488B9F600200000431E95FFEFFFF"))
        self.assertEqual(plan["entries"][0]["requires"], [])

    def test_region_symbol_pin_keeps_the_provider_refusal(self):
        table = self.root / "region.ct"
        table.write_text(table_xml(script_entry(1, "region", "[ENABLE]\n"
                                     "aobscanregion(RegionSym, RapidFireSearchBegin, "
                                     "RapidFireSearchBegin+1000, 48 8B 9F 60 02 00 00)\n"
                                     "registersymbol(RegionSym)\n"
                                     "RegionSym:\n"
                                     " db 90\n"
                                     "[DISABLE]\n"
                                     "RegionSym:\n"
                                     " db 48\n"
                                     "unregistersymbol(RegionSym)\n")),
                         encoding="utf-8")
        plan = compile_table(str(table), PROCESS)
        entry = plan["entries"][0]
        self.assertFalse(entry["supported"])
        # RT-4.6: RapidFireSearchBegin is not registered anywhere in the
        # table source (it is the aobscanregion range argument, not a
        # registration), so the refusal is the actionable per-symbol report.
        reason = (
            "Required symbol 'RapidFireSearchBegin' is not registered "
            "anywhere in this table (referenced by 'region'): no record "
            "defines it and it is not a user-defined symbol. Import it as a "
            "user symbol with its target address, or add a record that "
            "registers it (registersymbol/registerSymbol/label/aobscan)."
        )
        self.assertEqual(entry["reason"], reason)
        self.assertIn(reason, plan["blocked_reasons"])
        # The placeholder machinery added no new refusal path for this case.
        self.assertNotIn("placeholder", entry["reason"].casefold())

    def test_dry_link_carries_captures_in_both_phases(self):
        program = prepare_program("[ENABLE]\n"
                                  "aobscanmodule(PatchAnchor, FixtureTarget.exe, "
                                  "48 8B 9F s1.2 00 00 31 C0)\n"
                                  "registersymbol(PatchAnchor)\n"
                                  "PatchAnchor:\n"
                                  " db 48 8B 9F s1 00 00\n"
                                  " db B0 01\n"
                                  "[DISABLE]\n"
                                  "PatchAnchor:\n"
                                  " db 48 8B 9F s1 00 00\n"
                                  " db 31 C0\n"
                                  "unregistersymbol(PatchAnchor)\n", PROCESS)
        diagnostic = dry_link_program(program, PlaceholderMemory(seeds=[(100, SEED)]))
        self.assertEqual(diagnostic["enable"]["captured_placeholders"], {"s1": "6002"})
        self.assertEqual(diagnostic["disable"]["captured_placeholders"], {"s1": "6002"})


class PlaceholderClassicTests(unittest.TestCase):
    """Classic dialect: scans log captures; the patch side stays hex-only."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="ct2-wp57c-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.cwd = self.root / "cwd"
        self.cwd.mkdir()
        self.memory = PlaceholderMemory(seeds=[(100, SEED), (200, bytes.fromhex("DEADBEEF"))])
        self.engine = None

    def tearDown(self):
        if self.engine is not None and not self.engine.closed:
            self.engine.close()

    def _start(self, *entries):
        table = self.root / "table.ct"
        table.write_text(table_xml("".join(entries)), encoding="utf-8")
        plan = compile_table(str(table), PROCESS, debug_log=True)
        for entry in plan["entries"]:
            self.assertTrue(entry["supported"], entry.get("reason"))
            self.assertNotIn("program", entry)
        with patch("pathlib.Path.cwd", return_value=self.cwd):
            self.engine = TrainerEngine(plan, state_dir=self.root / "state",
                                        process_lock_dir=self.root / "shared",
                                        memory_factory=lambda name: self.memory,
                                        hook_coordinator=Coordinator())
        self.engine.poll()
        self.assertTrue(self.engine.connected, self.engine.status)

    def test_classic_placeholder_scan_logs_captures_with_hex_only_patch(self):
        self._start(script_entry(
            1, "classic s1", "[ENABLE]\n"
            "aobscanmodule(PatchAnchor, FixtureTarget.exe, 48 8B 9F s1.2 00 00 31 C0)\n"
            "registersymbol(PatchAnchor)\n"
            "assert(PatchAnchor+7, 31 C0)\n"
            "PatchAnchor+7:\n"
            " db B0 01\n"
            "[DISABLE]\n"
            "assert(PatchAnchor+7, B0 01)\n"
            "PatchAnchor+7:\n"
            " db 31 C0\n"
            "unregistersymbol(PatchAnchor)\n"))
        base = self.memory.base
        self.engine.toggle(1, True)
        self.assertEqual(self.memory.read(base + 107, 2), bytes.fromhex("B001"))
        # The classic path carries no substitution: captures are scan-log
        # evidence only, never engine-side capture state.
        self.assertEqual(self.engine.placeholder_captures, {})
        events = [json.loads(line) for line in
                  (self.cwd / LOG_NAME).read_text(encoding="utf-8").splitlines()
                  if line.strip()]
        scans = [event for event in events if event["event"] == "scan"]
        self.assertEqual(len(scans), 1)
        self.assertEqual(scans[0]["captured_placeholders"], {"s1": "6002"})
        self.engine.toggle(1, False)
        self.assertEqual(self.memory.read(base + 107, 2), bytes.fromhex("31C0"))
        self.assertNotIn(1, self.engine.placeholder_captures)

    def test_classic_plain_scan_log_keeps_the_pre_placeholder_shape(self):
        self._start(script_entry(
            1, "classic plain", "[ENABLE]\n"
            "aobscanmodule(PlainAnchor, FixtureTarget.exe, DE AD BE EF)\n"
            "registersymbol(PlainAnchor)\n"
            "assert(PlainAnchor, DE)\n"
            "PlainAnchor:\n"
            " db 90\n"
            "[DISABLE]\n"
            "assert(PlainAnchor, 90)\n"
            "PlainAnchor:\n"
            " db DE\n"
            "unregistersymbol(PlainAnchor)\n"))
        base = self.memory.base
        self.engine.toggle(1, True)
        self.assertEqual(self.memory.read(base + 200, 1), bytes.fromhex("90"))
        events = [json.loads(line) for line in
                  (self.cwd / LOG_NAME).read_text(encoding="utf-8").splitlines()
                  if line.strip()]
        scans = [event for event in events if event["event"] == "scan"]
        self.assertEqual(len(scans), 1)
        self.assertNotIn("captured_placeholders", scans[0])
        self.assertNotIn("match_count", scans[0])
        self.assertNotIn("match_offsets", scans[0])
        self.assertNotIn(1, self.engine.placeholder_captures)
        self.engine.toggle(1, False)

    def test_classic_db_s1_falls_back_to_the_program_dialect(self):
        # The classic data path refuses s1, but the program dialect accepts
        # the bare reference, so the record stays supported as a program.
        table = self.root / "table.ct"
        table.write_text(table_xml(script_entry(
            1, "classic db s1", "[ENABLE]\n"
            "aobscanmodule(PatchAnchor, FixtureTarget.exe, 48 8B 9F s1.2 00 00 31 C0)\n"
            "registersymbol(PatchAnchor)\n"
            "alloc(MyCode, 256)\n"
            "PatchAnchor:\n"
            " db 48 8B 9F s1 00 00\n"
            " db B0 01\n"
            "[DISABLE]\n"
            "PatchAnchor:\n"
            " db 48 8B 9F s1 00 00\n"
            " db 31 C0\n"
            "unregistersymbol(PatchAnchor)\n"
            "dealloc(MyCode)\n")),
            encoding="utf-8")
        plan = compile_table(str(table), PROCESS)
        entry = plan["entries"][0]
        self.assertTrue(entry["supported"], entry.get("reason"))
        self.assertIn("program", entry)
        self.assertEqual(entry["requires"], [])

    def test_classic_wide_data_placeholder_is_blocked_by_both_dialects(self):
        table = self.root / "table.ct"
        table.write_text(table_xml(script_entry(
            1, "classic dw s1", "[ENABLE]\n"
            "aobscanmodule(PatchAnchor, FixtureTarget.exe, 48 8B 9F s1.2 00 00 31 C0)\n"
            "registersymbol(PatchAnchor)\n"
            "assert(PatchAnchor+7, 31 C0)\n"
            "PatchAnchor+7:\n"
            " dw s1\n"
            "[DISABLE]\n"
            "assert(PatchAnchor+7, B0 01)\n"
            "PatchAnchor+7:\n"
            " db 31 C0\n"
            "unregistersymbol(PatchAnchor)\n")),
            encoding="utf-8")
        plan = compile_table(str(table), PROCESS)
        entry = plan["entries"][0]
        self.assertFalse(entry["supported"])
        self.assertIn(ASSERTION_REFUSAL, entry["reason"])


if __name__ == "__main__":
    unittest.main()
