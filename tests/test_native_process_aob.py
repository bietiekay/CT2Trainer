"""Owned scan data, source IR and publication ordering; no game execution."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from ct2trainer.native.aa import normalize_pattern as aa_pattern
from ct2trainer.native.aa_program import (ProgramError, dry_link_program, link_program,
                                           prepare_program, preflight_program, validate_program)
from ct2trainer.native.compiler import compile_table
from ct2trainer.native.lua_program import prepare_lua_program, validate_lua_program
from ct2trainer.native.aob_scan import AOBScanError, capture_scan, recheck_result, validate_result
from ct2trainer.native.engine import NativeRuntimeError, TrainerEngine
from ct2trainer.native.memory import MEM_COMMIT, MEM_FREE, PAGE_GUARD, ProcessMemoryError, _compile_pattern
from ct2trainer.native.patterns import normalize_pattern, pattern_matches
from ct2trainer.native.lua_work_budget import WorkLimits, WorkBudgetError, work_slice
from test_native_scan import _scan_memory
from test_native_hooks import _Memory, _LiteralCoordinator


SOURCE = '''[ENABLE]
aobscan(anchor,B80100000090??)
anchor:
 mov eax,#2
registersymbol(anchor)
[DISABLE]
anchor:
 mov eax,#1
unregistersymbol(anchor)
'''


class PatternTests(unittest.TestCase):
    def test_published_compact_whole_byte_and_nibble_wildcard_examples(self):
        cases = {'0F28': '0F 28', '4C 89 64 24 * 0F28 C8': '4C 89 64 24 ?? 0F 28 C8',
                 '005x8xxxxxE0': '00 5? 8? ?? ?? E0',
                 '005*8*****E0': '00 5? 8? ?? ?? E0',
                 '00 ? * x X ** xx ?? A* *f': '00 ?? ?? ?? ?? ?? ?? ?? A? ?F',
                 'e0000000': 'E0 00 00 00', '0x0F': '0? 0F', ' A?\t?f ': 'A? ?F'}
        for source, canonical in cases.items():
            with self.subTest(source=source):
                self.assertEqual(normalize_pattern(source), canonical)
                self.assertEqual(aa_pattern(source), canonical)
                matcher, size = _compile_pattern(source)
                raw = bytes(int(token.replace('?', '0'), 16) for token in canonical.split())
                self.assertEqual(size, len(raw))
                self.assertIsNotNone(matcher.match(raw))
                self.assertTrue(pattern_matches(canonical, raw))

    def test_each_nibble_mask_matches_the_expected_byte_domain(self):
        for high in range(16):
            pattern = f'{high:X}*'
            matches = [byte for byte in range(256) if _compile_pattern(pattern)[0].match(bytes([byte]))]
            self.assertEqual(matches, list(range(high * 16, high * 16 + 16)))
        for low in range(16):
            pattern = f'x{low:X}'
            matches = [byte for byte in range(256) if _compile_pattern(pattern)[0].match(bytes([byte]))]
            self.assertEqual(matches, list(range(low, 256, 16)))

    def test_invalid_odd_or_all_wildcard_patterns_refuse_before_scan(self):
        for value in ('', '*', 'x x', '???', '**??', 'F', 'F F', '0F2', '0F,28',
                      '0F|28', '[]', 'AA' * 4097, 'AA ' * 4097):
            with self.subTest(value=value[:30]), self.assertRaises(ValueError):
                normalize_pattern(value)


class ProcessScanTests(unittest.TestCase):
    def test_process_match_outside_module_is_not_module_alias(self):
        memory, _, _ = _scan_memory([(0x1000, b'xx', 0x04, MEM_COMMIT),
                                     (0x1002, b'xABC', 0x04, MEM_COMMIT)])
        memory.module = Mock(return_value=(0x1000, 2))
        self.assertEqual(memory.scan_process('414243'), 0x1003)
        with self.assertRaisesRegex(ProcessMemoryError, 'not found'):
            memory.scan_module('owned.exe', '414243')
        with self.assertRaisesRegex(ProcessMemoryError, 'not found'):
            memory.scan_region(0x1000, 0x1002, '414243')
        self.assertEqual(memory.scan_region(0x1002, 0x1006, '41 42 43'), 0x1003)

    def test_compact_nibble_pattern_bridges_chunks_but_no_ineligible_gap(self):
        memory, _, _ = _scan_memory([(0x1000, b'x\xA1', 0x04, MEM_COMMIT),
                                     (0x1002, b'\x2Fy', 0x20, MEM_COMMIT)])
        with patch('ct2trainer.native.memory.SCAN_CHUNK_SIZE', 1):
            self.assertEqual(memory.scan_process('A*xF'), 0x1001)
        for state, protection in ((MEM_FREE, 0x04), (MEM_COMMIT, 0x04 | PAGE_GUARD),
                                  (MEM_COMMIT, 0x01)):
            memory, _, _ = _scan_memory([(0x1000, b'A', 0x04, MEM_COMMIT),
                                         (0x1001, b'B', protection, state),
                                         (0x1002, b'C', 0x04, MEM_COMMIT)])
            with self.subTest(state=state, protection=protection), self.assertRaisesRegex(ProcessMemoryError, 'not found'):
                memory.scan_process('414243')
            self.assertNotIn((0x1001, 1), memory.read_calls)

    def test_multi_match_returns_lowest_address_and_quotas_still_refuse(self):
        # WP-55 (CE 7.5 parity): a multi-match process scan selects the
        # lowest address; the full match evidence is recorded in the
        # diagnostics.  The quotas below still refuse before any address.
        memory, _, _ = _scan_memory([(0x1000, b'ABxxAB', 0x04, MEM_COMMIT)])
        self.assertEqual(memory.scan_process('4142'), 0x1000)
        self.assertEqual(memory.last_scan_diagnostics,
                         {'match_count': 2, 'match_addresses': [0x1000, 0x1004]})
        memory, _, _ = _scan_memory([(0x1000, b'ABxxABxxAB', 0x04, MEM_COMMIT)])
        with patch('ct2trainer.native.memory.MAX_SCAN_RESULTS', 2):
            with self.assertRaisesRegex(ProcessMemoryError, 'result bound'):
                memory.scan_process('4142')
        # The initial match does not permit a successful truncated search.
        for name, value, message in (('MAX_PROCESS_SCAN_BYTES', 4, 'byte-read'),
                                     ('MAX_PROCESS_SCAN_REGIONS', 2, 'region/time'),
                                     ('MAX_SCAN_CANDIDATES', 1, 'candidate/time')):
            memory, _, _ = _scan_memory([(0x1000, b'ABxx', 0x04, MEM_COMMIT),
                                         (0x1004, b'ABxx', 0x04, MEM_COMMIT)])
            with self.subTest(name=name), patch('ct2trainer.native.memory.' + name, value):
                with self.assertRaisesRegex(ProcessMemoryError, message):
                    memory.scan_process('4142')
        memory, _, _ = _scan_memory([(0x1000, b'AB', 0x04, MEM_COMMIT)])
        with patch('ct2trainer.native.memory.time.monotonic', side_effect=[0, 31]):
            with self.assertRaisesRegex(ProcessMemoryError, 'time bound'):
                memory.scan_process('4142')

    def test_cancellation_after_match_and_target_change_never_return_address(self):
        memory, _, _ = _scan_memory([(0x1000, b'AB', 0x04, MEM_COMMIT)])
        calls = []
        def checkpoint():
            calls.append(1)
            if memory.read_calls:
                raise RuntimeError('owned generation cancelled')
        with self.assertRaisesRegex(RuntimeError, 'generation cancelled'):
            memory.scan_process('4142', checkpoint=checkpoint)
        self.assertTrue(memory.read_calls)
        self.assertGreater(len(calls), 2)
        memory, _, _ = _scan_memory([(0x1000, b'AB', 0x04, MEM_COMMIT)])
        raw_read = memory._read_exact
        def changed(address, size):
            raw = raw_read(address, size)
            memory._creation_time += 1
            return raw
        memory._read_exact = changed
        with self.assertRaises(ProcessMemoryError):
            memory.scan_process('4142')

    def test_bad_checkpoint_bounds_and_nonprogress_inventory_are_refused(self):
        memory, _, _ = _scan_memory([(0x1000, b'AB', 0x04, MEM_COMMIT)])
        with self.assertRaises(ValueError):
            memory.scan_process('4142', checkpoint=True)
        for start, end in ((0, 10), (True, 10), (0x1000, 0x1000), (0x1000, 0x200000000)):
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                memory.scan_region(start, end, '4142')
        self.assertEqual(memory.read_calls, [])
        memory._query = lambda address: SimpleNamespace(BaseAddress=address, RegionSize=0)
        with self.assertRaisesRegex(ProcessMemoryError, 'progress'):
            memory.scan_process('4142')


def _owned_memory():
    memory = _Memory()
    memory.data[0x1000] = bytes.fromhex('b8 01 00 00 00 90 ab')
    memory.scan_process = Mock(return_value=0x1000)
    memory.module = Mock(side_effect=AssertionError('Process scans cannot become module scans'))
    return memory


class SourceCaptureTests(unittest.TestCase):
    def test_process_module_and_region_ir_are_distinct_and_source_derived(self):
        program = prepare_program(SOURCE, 'owned.exe', bitness=32)
        self.assertEqual(program['enable'][0], {'op': 'scan_process', 'symbol': 'anchor', 'pattern': 'B8 01 00 00 00 90 ??'})
        self.assertEqual(program['requires'], [])
        self.assertEqual(program['provides'], ['anchor'])
        for directive, expected in (('aobscanmodule(anchor,owned.exe,B80100000090??)', 'scan'),
                                    ('aobscanregion(anchor,1000,1100,B80100000090??)', 'scan_region')):
            other = prepare_program(SOURCE.replace('aobscan(anchor,B80100000090??)', directive), 'owned.exe')
            self.assertEqual(other['enable'][0]['op'], expected)
        for change in (lambda p: p['enable'][0].update(op='scan'),
                       lambda p: p['enable'][0].update(pattern='B8 02 00 00 00 90 ??'),
                       lambda p: p.update(source_sha256='0' * 64)):
            forged = deepcopy(program); change(forged)
            with self.assertRaises(ProgramError):
                validate_program(forged)
        for source in (SOURCE.replace('[DISABLE]', '[DISABLE]\naobscan(other,0102)'),
                       SOURCE.replace('aobscan(anchor,B80100000090??)', '\n'.join(f'aobscan(anchor{i},0102)' for i in range(17)))):
            with self.assertRaises(ProgramError):
                prepare_program(source)

    def test_wrong_source_width_and_malformed_receipt_inputs_refuse_before_scan(self):
        program = prepare_program(SOURCE, 'owned.exe', bitness=32)
        memory = _owned_memory()
        with self.assertRaisesRegex(ProgramError, 'bitness'):
            preflight_program(program, memory)
        with self.assertRaisesRegex(AOBScanError, 'source hash'):
            capture_scan(program['enable'][0], 'not-a-hash', memory)
        memory.scan_process.assert_not_called()
        memory.pointer_size = 4
        result = preflight_program(program, memory)['scan_results']
        for supplied in ([], result + result, tuple(result)):
            with self.subTest(type=type(supplied)), self.assertRaises(ProgramError):
                preflight_program(program, memory, scan_results=supplied)

    def test_linking_reuses_capture_and_disable_never_scans(self):
        program = prepare_program(SOURCE, 'owned.exe')
        memory = _owned_memory()
        preflight = preflight_program(program, memory)
        result = link_program(program, memory, scan_results=preflight['scan_results'])
        self.assertEqual(result['exports']['anchor'], 0x1000)
        self.assertEqual(memory.scan_process.call_count, 1)
        link_program(program, memory, result['symbols'], phase='disable')
        self.assertEqual(memory.scan_process.call_count, 1)
        diagnostic = dry_link_program(program, memory)
        self.assertFalse(diagnostic['publishable'])
        self.assertEqual(memory.scan_process.call_count, 2)
        memory.module.assert_not_called()

    def test_captured_receipts_reject_changed_source_context_target_or_width(self):
        program = prepare_program(SOURCE, 'owned.exe')
        memory = _owned_memory()
        receipt = capture_scan(program['enable'][0], program['source_sha256'], memory)
        for changes in ({'source_sha256': '0' * 64}, {'pointer_size': True}, {'address': 0x1000000000000},
                        {'target': [1, True]}, {'bytes': 'b80200000090ab'}):
            forged = deepcopy(receipt); forged.update(changes)
            with self.subTest(changes=changes), self.assertRaises(AOBScanError):
                validate_result(forged, program['source_sha256'], program['enable'][0])
        memory.data[0x1000] = bytes.fromhex('b8 01 00 00 00 90 ac')
        self.assertTrue(pattern_matches(receipt['node']['pattern'], memory.data[0x1000]))
        with self.assertRaisesRegex(AOBScanError, 'bytes changed'):
            recheck_result(receipt, memory)
        memory.data[0x1000] = bytes.fromhex(receipt['bytes'])
        memory.identity = (123, 789)
        with self.assertRaisesRegex(AOBScanError, 'identity'):
            recheck_result(receipt, memory)
        memory.identity = (123, 456); memory.pointer_size = 4
        with self.assertRaisesRegex(AOBScanError, 'architecture'):
            recheck_result(receipt, memory)

    def engine(self, memory, coordinator, directory):
        engine = TrainerEngine.__new__(TrainerEngine)
        engine.memory, engine.hook_coordinator = memory, coordinator
        engine.symbols, engine.applied, engine.frozen, engine.lua_activations = {}, {}, {}, {}
        engine.hooks = {}; engine.store = SimpleNamespace(directory=Path(directory))
        engine.plan = {'trainer_id': 'a' * 16}
        engine._hook_lifetime_count = engine._hook_lifetime_bytes = 0
        engine.blocked = False
        return engine

    def test_publication_checks_captured_wildcard_context_under_held_event(self):
        memory, coordinator = _owned_memory(), _LiteralCoordinator()
        coordinator.before_hold = lambda: memory.data.update({0x1000: bytes.fromhex('b8 01 00 00 00 90 ac')})
        with tempfile.TemporaryDirectory() as directory:
            engine = self.engine(memory, coordinator, directory)
            with self.assertRaisesRegex(NativeRuntimeError, 'bytes changed'):
                engine._install_program(prepare_program(SOURCE, 'owned.exe'), 1)
        self.assertEqual(memory.writes, [])
        self.assertEqual(memory.data[0x1000][:5], bytes.fromhex('b8 01 00 00 00'))

    def test_existing_publication_guard_composes_and_scan_address_is_not_rediscovered(self):
        memory, coordinator = _owned_memory(), _LiteralCoordinator()
        observations = []
        with tempfile.TemporaryDirectory() as directory:
            engine = self.engine(memory, coordinator, directory)
            manager, result, live = engine._install_program(prepare_program(SOURCE, 'owned.exe'), 1,
                publication_guard=lambda: observations.append(coordinator.held))
            self.assertEqual(observations, [True])
            self.assertEqual(memory.scan_process.call_count, 1)
            self.assertEqual(memory.data[0x1000][:5], bytes.fromhex('b8 02 00 00 00'))
            manager.disable()
            self.assertEqual(memory.data[0x1000][:5], bytes.fromhex('b8 01 00 00 00'))
            self.assertEqual(memory.scan_process.call_count, 1)

    def test_allocator_introducing_second_full_pattern_does_not_move_captured_address(self):
        memory, coordinator = _owned_memory(), _LiteralCoordinator()
        original = memory.data[0x1000]
        def matches():
            return sorted(base + index for base, raw in memory.data.items()
                          for index in range(len(raw) - len(original) + 1)
                          if raw[index:index + len(original)] == original)
        def scan(pattern):
            found = matches()
            if len(found) != 1:
                raise ProcessMemoryError('Owned allocation made full-process pattern ambiguous')
            return found[0]
        memory.scan_process.side_effect = scan
        allocate = memory.allocate
        observations = []
        def duplicate(size, near=None):
            address = allocate(size, near)
            memory.data[address] = original + memory.data[address][len(original):]
            observations.append(matches())
            return address
        memory.allocate = duplicate
        source = SOURCE.replace('anchor:\n mov eax,#2',
            'alloc(cave,100)\ncave:\n db 01 02\nanchor:\n mov eax,#2')
        source = source.replace('unregistersymbol(anchor)', 'unregistersymbol(anchor)\ndealloc(cave)')
        with tempfile.TemporaryDirectory() as directory:
            engine = self.engine(memory, coordinator, directory)
            manager, result, live = engine._install_program(prepare_program(source, 'owned.exe'), 1)
            self.assertEqual(observations, [[0x1000, 0x10000]])
            self.assertEqual(memory.scan_process.call_count, 1)
            self.assertEqual(result['exports']['anchor'], 0x1000)
            self.assertEqual(live[0]['address'], 0x1000)
            manager.disable()
            self.assertEqual(memory.scan_process.call_count, 1)
            self.assertEqual(memory.data[0x1000][:5], bytes.fromhex('b8 01 00 00 00'))



class _Clock:
    def __init__(self): self.value = 100.0
    def __call__(self): return self.value
    def advance(self, seconds): self.value += seconds


class ProcessBudgetTests(unittest.TestCase):
    def setUp(self):
        self.clock = _Clock()
        self.limits = WorkLimits(0.25, 1_000_000, 0.5, 2, 10, 3)

    def test_process_backend_refuses_success_after_late_read(self):
        memory, _, _ = _scan_memory([(0x1000, b'ABC', 0x04, MEM_COMMIT)])
        read = memory.read
        def late_read(*args):
            raw = read(*args)
            self.clock.advance(0.6)
            return raw
        memory.read = late_read
        with self.assertRaisesRegex(WorkBudgetError, 'broker call deadline'):
            with work_slice(self.limits, lambda: None, self.clock) as budget:
                with budget.dispatch(): memory.scan_process('414243')

    def test_capture_refuses_late_backend_before_selected_byte_read(self):
        memory = _owned_memory()
        def late_scan(*args):
            self.clock.advance(0.6)
            return 0x1000
        memory.scan_process.side_effect = late_scan
        memory.read = Mock(wraps=memory.read)
        program = prepare_program(SOURCE, 'owned.exe')
        with self.assertRaisesRegex(WorkBudgetError, 'broker call deadline'):
            with work_slice(self.limits, lambda: None, self.clock) as budget:
                with budget.dispatch(): capture_scan(program['enable'][0], program['source_sha256'], memory)
        memory.read.assert_not_called()

    def test_expired_allocation_cannot_rescan_or_publish_captured_entry(self):
        memory, coordinator = _owned_memory(), _LiteralCoordinator()
        original, allocate = memory.data[0x1000], memory.allocate
        def late_duplicate(size, near=None):
            address = allocate(size, near)
            memory.data[address] = original + memory.data[address][len(original):]
            self.clock.advance(0.6)
            return address
        memory.allocate = late_duplicate
        source = SOURCE.replace('anchor:\n mov eax,#2',
            'alloc(cave,100)\ncave:\n db 01 02\nanchor:\n mov eax,#2')
        source = source.replace('unregistersymbol(anchor)', 'unregistersymbol(anchor)\ndealloc(cave)')
        with tempfile.TemporaryDirectory() as directory:
            engine = SourceCaptureTests().engine(memory, coordinator, directory)
            with self.assertRaisesRegex((WorkBudgetError, NativeRuntimeError), 'broker call deadline'):
                with work_slice(self.limits, lambda: None, self.clock) as budget:
                    with budget.dispatch(): engine._install_program(prepare_program(source, 'owned.exe'), 1)
        self.assertEqual(memory.scan_process.call_count, 1)
        self.assertFalse(any(address == 0x1000 for address, _ in memory.writes))
        self.assertEqual(memory.data[0x1000], original)

    def test_expired_composed_scan_guard_cannot_publish_under_held_proof(self):
        memory, coordinator = _owned_memory(), _LiteralCoordinator()
        held = []
        def slow_guard():
            held.append(coordinator.held)
            self.clock.advance(0.6)
        with tempfile.TemporaryDirectory() as directory:
            engine = SourceCaptureTests().engine(memory, coordinator, directory)
            with self.assertRaisesRegex((WorkBudgetError, NativeRuntimeError), 'broker call deadline'):
                with work_slice(self.limits, lambda: None, self.clock) as budget:
                    with budget.dispatch(): engine._install_program(prepare_program(SOURCE, 'owned.exe'), 1, publication_guard=slow_guard)
        self.assertEqual(held, [True])
        self.assertFalse(coordinator.held)
        self.assertEqual(memory.scan_process.call_count, 1)
        self.assertEqual(memory.writes, [])


class ScanPolicyTests(unittest.TestCase):
    """WP-36(a): scan-only programs are staged; the 16-scan bound holds."""

    def test_scan_only_program_is_staged(self):
        source = ("[ENABLE]\n"
                  "aobscan(sym,B80100000090??)\n"
                  "registersymbol(sym)\n"
                  "[DISABLE]\n"
                  "unregistersymbol(sym)\n")
        program = prepare_program(source, "owned.exe")
        self.assertEqual(program["enable"][0]["op"], "scan_process")
        self.assertEqual(program["requires"], [])
        self.assertEqual(program["provides"], ["sym"])
        validate_program(program)
        # Scan-only programs carry no NASM patch content, so the dry link has
        # nothing to assemble; the preflight scan capture is the meaningful
        # check at this level (runtime activation is AP-11 territory).
        preflight = preflight_program(program, _owned_memory())
        self.assertEqual(len(preflight["scan_results"]), 1)

    def test_scan_only_program_needs_no_executable_patch(self):
        # Regression: before WP-36 the generic refusal hit scan-only providers.
        source = ("[ENABLE]\n"
                  "aobscanregion(sym,1000,1100,0102)\n"
                  "registersymbol(sym)\n"
                  "[DISABLE]\n"
                  "unregistersymbol(sym)\n")
        program = prepare_program(source, "owned.exe")
        self.assertEqual(program["enable"][0]["op"], "scan_region")
        validate_program(program)

    def test_seventeen_process_scans_exceed_the_bound(self):
        lines = ["[ENABLE]"]
        lines.extend(f"aobscan(sym{i:02d},0102)" for i in range(17))
        lines += ["sym00:", "mov eax,#2", "[DISABLE]", "sym00:", "mov eax,#1"]
        with self.assertRaisesRegex(ProgramError, "16 complete process-scan bound"):
            prepare_program("\n".join(lines) + "\n", "owned.exe")

    def test_sixteen_process_scans_stay_within_the_bound(self):
        lines = ["[ENABLE]"]
        lines.extend(f"aobscan(sym{i:02d},0102)" for i in range(16))
        lines += ["sym00:", "mov eax,#2", "[DISABLE]", "sym00:", "mov eax,#1"]
        program = prepare_program("\n".join(lines) + "\n", "owned.exe")
        self.assertEqual(sum(node["op"] == "scan_process" for node in program["enable"]), 16)


class ThreadGateTests(unittest.TestCase):
    """WP-36(b): createThread/threadWait get a named staged-runtime gate."""

    def test_thread_only_enable_hits_named_gate_at_prepare(self):
        with self.assertRaisesRegex(ProgramError, "gated in the native staged runtime"):
            prepare_program("[ENABLE]\ncreatethread(1000)\n[DISABLE]\n", "owned.exe")

    def test_threadwait_only_enable_hits_named_gate_at_prepare(self):
        with self.assertRaisesRegex(ProgramError, "gated in the native staged runtime"):
            prepare_program("[ENABLE]\nthreadwait()\n[DISABLE]\n", "owned.exe")

    def test_createthread_with_patch_is_gated_in_preflight(self):
        program = prepare_program(
            "[ENABLE]\n1000:\ndb 01\ncreatethread(1000)\n[DISABLE]\n1000:\ndb 00\n",
            "owned.exe")
        with self.assertRaisesRegex(ProgramError, "injected thread backend"):
            preflight_program(program, _owned_memory())


class GlobalAllocTests(unittest.TestCase):
    """WP-36(c): globalalloc in the program dialect (lua+asm records).

    Per-program RW allocation that is registered into the shared symbol
    space (CE 7.5: SetUserdefinedSymbolAllocSize), so other records may
    require it; forced RW data capabilities; 2-arg and 3-arg (near) forms.
    """

    GLOBAL_SCRIPT = (
        "[ENABLE]\n"
        "aobscan(anchor,B80100000090??)\n"
        "registersymbol(anchor)\n"
        "globalalloc(pAnchor,8)\n"
        "globalalloc(pNear,4,anchor)\n"
        "globalalloc(nCrash,4)\n"
        "alloc(newmem,$100,anchor)\n"
        "label(code)\n"
        "label(return)\n"
        "nCrash:\n"
        "dd (int)0\n"
        "newmem:\n"
        "  push r15\n"
        "  mov r15,pAnchor\n"
        "  mov [r15],rax\n"
        "  pop r15\n"
        "code:\n"
        "  mov eax,#2\n"
        "  jmp return\n"
        "return:\n"
        "  mov [anchor],eax\n"
        "anchor:\n"
        "  jmp newmem\n"
        "[DISABLE]\n"
        "anchor:\n"
        "  db B8 01 00 00 00\n"
        "unregistersymbol(anchor)\n"
        "dealloc(newmem)\n")

    def test_globalalloc_plan_carries_forced_rw_and_provides(self):
        program = prepare_program(self.GLOBAL_SCRIPT, "owned.exe")
        self.assertEqual(program["allocations"], ["pAnchor", "pNear", "nCrash", "newmem"])
        self.assertEqual(program["provides"], ["anchor", "nCrash", "pAnchor", "pNear"])
        for symbol in ("pAnchor", "pNear", "nCrash"):
            self.assertFalse(program["allocation_executable"][symbol])
            self.assertTrue(program["allocation_writable"][symbol])
        validate_program(program)

    def test_globalalloc_preflight_requests_forced_rw(self):
        program = prepare_program(self.GLOBAL_SCRIPT, "owned.exe")
        memory = _owned_memory()
        preflight = preflight_program(program, memory)
        requests = {request["name"].casefold(): request
                    for request in preflight["allocation_requests"]}
        self.assertEqual(requests["panchor"]["executable"], False)
        self.assertEqual(requests["panchor"]["writable"], True)
        self.assertEqual(requests["pnear"]["near"], 0x1000)
        self.assertTrue(requests["newmem"]["executable"])
        memory.scan_process.assert_called_once()

    def test_globalalloc_dry_links_end_to_end(self):
        program = prepare_program(self.GLOBAL_SCRIPT, "owned.exe")
        result = dry_link_program(program, _owned_memory())
        self.assertFalse(result["publishable"])
        synthetic = result["synthetic_allocations"]
        self.assertEqual(len(synthetic), 4)
        self.assertFalse(synthetic["panchor"]["executable"])
        self.assertTrue(synthetic["panchor"]["writable"])

    def test_lua_plus_asm_record_with_globalalloc_compiles(self):
        # Resonance shape: single top-level [ENABLE]/[DISABLE] with
        # {$lua}/{asm} mode switches inside; the Lua registers/releases the
        # global symbol (provider proof), the static AA body carries the
        # per-program globalalloc (option B: stays in the program dialect,
        # forced RW allocation).
        source = (
            "[ENABLE]\n"
            "{$lua}\n"
            'if not getAddressSafe("pCheatFlags") then registerSymbol("pCheatFlags", allocateMemory(8)) end\n'
            "{$asm}\n"
            "aobscan(synSkill,B8 01 00 00 90)\n"
            "registersymbol(synSkill)\n"
            "alloc(newmem,$100,synSkill)\n"
            "globalalloc(pSkill,8)\n"
            "label(code)\n"
            "label(return)\n"
            "newmem:\n"
            "  push r15\n"
            "  mov r15,pSkill\n"
            "  pop r15\n"
            "code:\n"
            "  mov eax,#2\n"
            "  jmp return\n"
            "synSkill:\n"
            "  jmp newmem\n"
            "[DISABLE]\n"
            "{$lua}\n"
            'unregisterSymbol("pCheatFlags")\n'
            "{$asm}\n"
            "synSkill:\n"
            "  db B8 01 00 00 00\n"
            "unregistersymbol(synSkill)\n"
            "dealloc(newmem)\n")
        program = prepare_lua_program(source, "owned.exe")
        static = program["static_program"]
        self.assertIsNotNone(static)
        self.assertEqual(static["provides"], ["pSkill", "synSkill"])
        self.assertEqual(static["requires"], [])
        self.assertEqual(program["requires"], [])
        self.assertIn("pCheatFlags", program["provides"])
        self.assertFalse(program["one_shot"])
        validate_lua_program(program)

    def test_globalalloc_requires_forced_arguments(self):
        for bad in ("globalalloc()", "globalalloc(pA)", "globalalloc(pA,0)",
                    "globalalloc(pA,8,1000,extra)"):
            with self.subTest(bad=bad):
                with self.assertRaises(ProgramError):
                    prepare_program("[ENABLE]\n" + bad + "\n"
                                    "1000:\ndb 01\n[DISABLE]\n1000:\ndb 00\n", "owned.exe")

    def test_compiled_ct_record_with_lua_and_globalalloc_is_supported(self):
        # Compiler level: a Resonance-shaped record (Lua register/unregister
        # provider + static {$asm} body with a per-program globalalloc)
        # compiles to a supported record with the merged provides list.
        ct_body = '''<CheatTable CheatEngineTableVersion="45"><CheatEntries>
<CheatEntry><ID>970</ID><Description>"ResonanceShaped"</Description><VariableType>Auto Assembler Script</VariableType><AssemblerScript>
[ENABLE]
{$lua}
if not getAddressSafe("pCheatFlags") then registerSymbol("pCheatFlags", allocateMemory(8)) end
{$asm}
aobscan(synSkill,B8 01 00 00 90)
registersymbol(synSkill)
alloc(newmem,$100,synSkill)
globalalloc(pSkill,8)
label(code)
label(return)
newmem:
  push r15
  mov r15,pSkill
  pop r15
code:
  mov eax,#2
  jmp return
synSkill:
  jmp newmem
[DISABLE]
{$lua}
unregisterSymbol("pCheatFlags")
{$asm}
synSkill:
  db B8 01 00 00 00
unregistersymbol(synSkill)
dealloc(newmem)
</AssemblerScript></CheatEntry>
</CheatEntries></CheatTable>'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "owned.ct"
            path.write_text(ct_body, encoding="utf-8")
            plan = compile_table(path, "ct2synth01.exe")
        entry = next(e for e in plan["entries"] if e["id"] == 970)
        self.assertTrue(entry["supported"], entry["reason"])
        self.assertIsNotNone(entry.get("lua_program"))
        static = entry["lua_program"]["static_program"]
        self.assertIsNotNone(static)
        self.assertIn("pCheatFlags", entry["provides"])
        self.assertIn("pSkill", entry["provides"])
        self.assertEqual(entry["requires"], [])


if __name__ == '__main__':
    unittest.main()
