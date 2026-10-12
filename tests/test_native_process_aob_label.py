"""WP-18: $process AOB module token and trailing @F anonymous-label fallback.

Covers the two root causes that blocked the PRAGMATA reference records
(shapes only, no table content): aobscanmodule with the $process module
token in the bounded, program and engine paths, and a forward anonymous
reference (@F) with no explicit @@ after it falling back to the next
positioned named label of the phase.
"""

from __future__ import annotations

import unittest
from unittest.mock import Mock

from iced_x86 import Decoder, Mnemonic

from ct2trainer.native.aa import AAError, compile_script
from ct2trainer.native.aa_program import (
    ProgramError,
    link_program,
    prepare_program,
    preflight_program,
    validate_program,
)
from ct2trainer.native.assembler import AssemblyError, NasmAssembler
from ct2trainer.native.engine import TrainerEngine


MODULE_START = 0x140000000
MODULE_SIZE = 0x100000
SCAN_ADDRESS = 0x140001000
SCAN_PATTERN = "48 8B 48 08"

# Program-path fixture: aobscanmodule with the $process token, backup of the
# scanned bytes via readmem, restore from the backup on disable.
PROCESS_AOB_PROGRAM = (
    "[ENABLE]\n"
    "aobscanmodule(scan_ref, $process, 48 8B 48 08)\n"
    "alloc(backup, 4, scan_ref)\n"
    "backup:\n"
    "readmem(scan_ref, 4)\n"
    "[DISABLE]\n"
    "scan_ref:\n"
    "readmem(backup, 4)\n"
    "unregistersymbol(*)\n"
    "dealloc(*)\n"
)

# Bounded (data-only) fixture for compile_script with the $process token.
PROCESS_AOB_BOUNDED = (
    "[ENABLE]\n"
    "aobscanmodule(L, $process, 89 48 08)\n"
    "L:\n"
    "assert(L, 89 48 08)\n"
    "db 90\n"
    "[DISABLE]\n"
    "L:\n"
    "assert(L, 90)\n"
    "db 89\n"
)

# Synthetic cascade mirroring the PRAGMATA reference shape: chained
# cmp / jne short @F / @@: blocks whose last check ends with a trailing
# @F and no following @@ — the next positioned named label is code:.
SOURCE_TRAILING_ATF = (
    "[ENABLE]\n"
    "aobscanmodule(scan_pt, $process, 48 8B 48 08)\n"
    "alloc(newmem, 256, scan_pt)\n"
    "alloc(backup, 4, scan_pt)\n"
    "label(code, return)\n"
    "label(stash_a, stash_b)\n"
    "backup:\n"
    "readmem(scan_pt, 4)\n"
    "newmem:\n"
    " cmp [rax], #42\n"
    " jne short @F\n"
    " mov [stash_a], rax\n"
    " jmp code\n"
    "@@:\n"
    " cmp [rax], #43\n"
    " jne short @F\n"
    " mov [stash_b], rax\n"
    " jmp code\n"
    "@@:\n"
    " cmp [rax], #44\n"
    " jne short @F\n"
    " mov [stash_a], rax\n"
    "code:\n"
    " reassemble(scan_pt)\n"
    " jmp return\n"
    "stash_a:\n"
    "dq 0\n"
    "stash_b:\n"
    "dq 0\n"
    "return:\n"
    "registersymbol(stash_a, stash_b)\n"
    "[DISABLE]\n"
    "scan_pt:\n"
    "readmem(backup, 4)\n"
    "unregistersymbol(stash_a, stash_b)\n"
    "dealloc(*)\n"
)


class _ProcessMemory:
    """Fake process memory: one owned main module with a seeded pattern."""

    def __init__(self):
        self.data = {}
        self.scan_module_calls = []
        self.module_calls = []

    def seed(self, address, raw: bytes):
        self.data.update({address + offset: byte for offset, byte in enumerate(raw)})

    def read(self, address, size):
        return bytes(self.data.get(address + offset, 0) for offset in range(size))

    def module(self, name):
        self.module_calls.append(name)
        if name.casefold() != "owned.exe":
            raise ValueError("Unknown owned module: " + name)
        return MODULE_START, MODULE_SIZE

    def scan_module(self, module, pattern):
        self.scan_module_calls.append((module, pattern))
        if module == "$process":
            raise AssertionError("scan_module called with the literal $process token")
        start, _ = self.module(module)
        needle = bytes.fromhex(pattern.replace(" ", ""))
        image = bytes(self.data.get(start + offset, 0) for offset in range(MODULE_SIZE))
        matches = [
            start + index
            for index in range(len(image) - len(needle) + 1)
            if image[index:index + len(needle)] == needle
        ]
        if len(matches) != 1:
            raise ValueError("Pattern does not match uniquely in the module.")
        return matches[0]


class ProcessTokenProgramTests(unittest.TestCase):
    def test_prepare_accepts_process_token(self):
        program = prepare_program(PROCESS_AOB_PROGRAM, "owned.exe")
        self.assertEqual(
            program["enable"][0],
            {"op": "scan", "symbol": "scan_ref", "module": "$process", "pattern": SCAN_PATTERN},
        )
        validate_program(program)

    def test_quoted_module_name_still_compiles(self):
        program = prepare_program(PROCESS_AOB_PROGRAM.replace("$process", '"owned.exe"'), "owned.exe")
        self.assertEqual(program["enable"][0]["module"], "owned.exe")
        validate_program(program)

    def test_path_like_module_still_refused(self):
        with self.assertRaisesRegex(AAError, "module basenames"):
            prepare_program(PROCESS_AOB_PROGRAM.replace("$process", '"C:\\x\\y"'))

    def test_bounded_path_accepts_process_token(self):
        result = compile_script(PROCESS_AOB_BOUNDED)
        scan = next(op for op in result["enable"] if op["op"] == "scan")
        self.assertEqual(scan["module"], "$process")
        self.assertEqual(scan["symbol"], "L")
        self.assertEqual(scan["pattern"], "89 48 08")

    def test_preflight_maps_token_to_process_name(self):
        memory = _ProcessMemory()
        memory.seed(SCAN_ADDRESS, bytes.fromhex(SCAN_PATTERN))
        program = prepare_program(PROCESS_AOB_PROGRAM, "owned.exe")
        result = preflight_program(program, memory)
        self.assertEqual(result["symbols"]["scan_ref"], SCAN_ADDRESS)
        self.assertTrue(0 <= SCAN_ADDRESS - MODULE_START < MODULE_SIZE)
        self.assertEqual([call[0] for call in memory.scan_module_calls], ["owned.exe"])
        self.assertEqual(memory.module_calls, ["owned.exe"])


class ProcessTokenEngineTests(unittest.TestCase):
    def _engine(self, memory):
        engine = TrainerEngine.__new__(TrainerEngine)
        engine.memory = memory
        engine.symbols = {}
        engine.local_symbols = {}
        engine.plan = {"trainer_id": "a" * 16, "process_name": "owned.exe"}
        return engine

    def test_operations_maps_process_token(self):
        memory = Mock()
        memory.scan_module.return_value = 0x140001000
        engine = self._engine(memory)
        entry = {"id": 1, "enable": [
            {"op": "scan", "symbol": "L", "module": "$process", "pattern": SCAN_PATTERN},
        ]}
        symbols, registered, patches = engine._operations(entry, "enable")
        memory.scan_module.assert_called_once_with("owned.exe", SCAN_PATTERN)
        self.assertEqual(symbols, {"l": 0x140001000})
        self.assertEqual(registered, set())
        self.assertEqual(patches, [])

    def test_operations_keeps_plain_module_names(self):
        memory = Mock()
        memory.scan_module.return_value = 0x140001000
        engine = self._engine(memory)
        entry = {"id": 2, "enable": [
            {"op": "scan", "symbol": "L", "module": "other.exe", "pattern": "48 8B"},
        ]}
        symbols, _, _ = engine._operations(entry, "enable")
        memory.scan_module.assert_called_once_with("other.exe", "48 8B")
        self.assertEqual(symbols, {"l": 0x140001000})

    def test_async_enable_writes_maps_process_token(self):
        memory = Mock()
        memory.scan_module.return_value = 0x140001000
        memory.resolve.return_value = 0x140002000
        engine = self._engine(memory)
        entry = {"id": 3, "enable": [
            {"op": "scan", "symbol": "L", "module": "$process", "pattern": "48 8B"},
            {"op": "write", "address": "L", "bytes": "90"},
        ]}
        writes = engine._async_enable_writes(entry)
        memory.scan_module.assert_called_once_with("owned.exe", "48 8B")
        self.assertEqual(writes, [(0x140002000, b"\x90")])


class TrailingAtFRefusalTests(unittest.TestCase):
    def test_forward_ref_without_any_target_still_refused(self):
        source = "[ENABLE]\nalloc(cave,100)\ncave:\njmp @f\nret\n[DISABLE]\ndealloc(*)"
        with self.assertRaisesRegex(ProgramError, "no target"):
            prepare_program(source)

    def test_backward_ref_without_preceding_atat_still_refused(self):
        source = "[ENABLE]\nalloc(cave,100)\ncave:\njmp @b\nret\n[DISABLE]\ndealloc(*)"
        with self.assertRaisesRegex(ProgramError, "no target"):
            prepare_program(source)


class TrailingAtFRealNasmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.assembler = NasmAssembler()
        except AssemblyError as exc:
            raise unittest.SkipTest(str(exc))

    def test_trailing_atf_targets_code_label_end_to_end(self):
        memory = _ProcessMemory()
        memory.seed(SCAN_ADDRESS, bytes.fromhex(SCAN_PATTERN))
        program = prepare_program(SOURCE_TRAILING_ATF, "owned.exe")
        preflight = preflight_program(program, memory)
        self.assertEqual(preflight["symbols"]["scan_pt"], SCAN_ADDRESS)
        self.assertEqual([call[0] for call in memory.scan_module_calls], ["owned.exe"])
        sizes = {request["name"]: request["size"] for request in preflight["allocation_requests"]}
        result = link_program(
            program,
            memory,
            allocations={
                "newmem": {"address": 0x140002000, "size": sizes["newmem"], "executable": True},
                "backup": {"address": 0x140003000, "size": sizes["backup"]},
            },
            assembler=self.assembler,
        )
        self.assertEqual(sorted(result["exports"]), ["stash_a", "stash_b"])
        block = next(block for block in result["blocks"] if block["address"] == 0x140002000)
        instructions = list(Decoder(64, bytes.fromhex(block["bytes"]), ip=0x140002000))
        jne_targets = [ins.near_branch_target for ins in instructions if ins.mnemonic == Mnemonic.JNE]
        self.assertEqual(len(jne_targets), 3)
        # Each block is cmp(3) + jne short(2) + mov(7) + jmp short(2) = 0xE bytes,
        # so the explicit @@ cursors sit at +0xE and +0x1C.
        self.assertEqual(jne_targets[0], 0x140002000 + 0x0E)
        self.assertEqual(jne_targets[1], 0x140002000 + 0x1C)
        # ...the trailing one falls back to the positioned code: label.
        self.assertEqual(jne_targets[2], result["symbols"]["code"])
        self.assertNotEqual(jne_targets[2], jne_targets[1])

    def test_explicit_atat_wins_over_named_label_fallback(self):
        source = (
            "[ENABLE]\n"
            "alloc(cave, 100)\n"
            "label(target)\n"
            "cave:\n"
            "jmp @F\n"
            "@@:\n"
            "nop\n"
            "target:\n"
            "ret\n"
            "[DISABLE]\n"
            "dealloc(*)\n"
        )
        memory = _ProcessMemory()
        result = link_program(
            prepare_program(source),
            memory,
            allocations={"cave": {"address": 0x140002000, "size": 256, "executable": True}},
            assembler=self.assembler,
        )
        block = result["blocks"][0]
        self.assertEqual(block["address"], 0x140002000)
        instructions = list(Decoder(64, bytes.fromhex(block["bytes"]), ip=0x140002000))
        self.assertEqual(instructions[0].mnemonic, Mnemonic.JMP)
        # The branch lands on the @@ cursor (offset 2, after the 2-byte short jmp),
        # not on target: (offset 3).
        self.assertEqual(instructions[0].near_branch_target, 0x140002002)
        self.assertNotEqual(instructions[0].near_branch_target, result["symbols"]["target"])


if __name__ == "__main__":
    unittest.main()
