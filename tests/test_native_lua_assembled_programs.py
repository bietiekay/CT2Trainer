"""WP-51: plan-level admission of Lua-assembled Auto Assembler programs.

A record whose static AA envelope is empty or non-executable is still
plan-admissible when its record Lua provably carries an ``autoAssemble``
call with a statically provable, nonempty script body (exact admission,
never blanket):

- the proof report (schema ``ct2trainer-autoassemble-proof/v1``) records
  only each body's SHA-256 and byte count plus the bodies' static symbol
  and requirement sets; raw bodies never leave the plan;
- proven body symbols merge into the record's ``provides`` so the record
  acts as an ordinary static symbol provider (``requires`` stays
  consistent with the proven bodies);
- the runtime never assembles the inert outer envelope: the proven
  ``autoAssemble`` call itself owns the patch, the outer assembly token
  stays absent, and the declared symbol exports (gate at activation
  start) are proven by the body's own ``registersymbol``;
- the unprovable variants (no autoAssemble call, empty body, identifier
  not bound to a literal chain, body over the size bound, more than 128
  bodies) stay blocked with their exact named reasons;
- the proof field is strictly validated by both plan validators through
  the Lua program regeneration check: forged symbols, forged digests,
  stripped fields or stripped reports are rejected fail-closed;
- hybrid records (executable static envelope plus autoAssemble) and
  pure-Lua (shape C) records keep their existing profiles: the proof is
  additive there and absent when nothing is provable.

Self-contained synthetic records; no TableReferences input, no CE
inputs. The runtime half runs against the fake target memory with the
pinned autoAssemble enable/retire idiom.
"""
from copy import deepcopy
from hashlib import sha256
import tempfile
import unittest
import xml.sax.saxutils
from pathlib import Path
from types import SimpleNamespace

from test_native_engine import FakeMemory
from test_native_engine_code import Coordinator
from ct2trainer.native.compiler import (NativeCompileError, compile_table,
                                        validate_plan as compiler_validate_plan)
from ct2trainer.native.engine import (NativeRuntimeError, TrainerEngine,
                                      validate_plan)
from ct2trainer.native.lua_program import (AutoAssembleProofError,
                                           LuaProgramError,
                                           MAX_SOURCE_BYTES,
                                           _auto_assemble_proof, _Part,
                                           prepare_lua_program,
                                           validate_lua_program)


PROCESS = 'FixtureTarget.exe'

BODY = ('[ENABLE]\n'
        'alloc(code, 64)\n'
        'registersymbol(code)\n'
        'code:\n'
        '  db 90 E9\n'
        '[DISABLE]\n'
        'unregistersymbol(code)\n'
        'dealloc(code)\n')
BODY_BYTES = ('\n' + BODY).encode('utf-8')  # long-string content starts after [[

# Shape B: non-executable static envelope (label only) + provable
# autoAssemble in the enable Lua; the disable Lua retires the same source.
SHAPE_B = ('[ENABLE]\n'
           'label(inert)\n'
           '{$lua}\n'
           'script = [[\n' + BODY + ']]\n'
           'ok, receipt = autoAssemble(script)\n'
           '[DISABLE]\n'
           '{$lua}\n'
           'autoAssemble(script, false, receipt)\n')

# Shape C: no static envelope at all (pure Lua record), provable body.
SHAPE_C = ('{$lua}\n'
           '[ENABLE]\n'
           'script = [[\n' + BODY + ']]\n'
           'ok, receipt = autoAssemble(script)\n'
           '[DISABLE]\n'
           'autoAssemble(script, false, receipt)\n')


class AutoAssemblePlanTests(unittest.TestCase):
    """Plan-level admission, proof report content and named refusals."""

    def test_shape_b_admitted_with_proof_and_body_symbols(self):
        program = prepare_lua_program(SHAPE_B, PROCESS, 64)
        self.assertIsNone(program['static_program'])
        self.assertEqual(program['requires'], [])
        self.assertFalse(program['one_shot'])
        proof = program['auto_assemble']
        self.assertEqual(proof['schema'], 'ct2trainer-autoassemble-proof/v1')
        self.assertEqual(len(proof['calls']), 1)
        self.assertEqual(proof['calls'][0]['body_sha256'],
                         sha256(BODY_BYTES).hexdigest())
        self.assertEqual(proof['calls'][0]['body_bytes'], len(BODY_BYTES))
        self.assertEqual(proof['body_symbols'], ['code'])
        self.assertEqual(proof['body_requires'], [])
        # Proven body symbols merge into the record's provides.
        self.assertEqual(program['provides'], ['code'])
        validate_lua_program(program)

    def test_shape_b_without_autoassemble_keeps_original_refusal(self):
        source = ('[ENABLE]\n'
                  'label(inert)\n'
                  '{$lua}\n'
                  'local x = 1\n'
                  '[DISABLE]\n'
                  '{$lua}\n'
                  'x = nil\n')
        with self.assertRaises(LuaProgramError) as caught:
            prepare_lua_program(source, PROCESS, 64)
        self.assertEqual(str(caught.exception),
                         'Static AA envelope: Enable section has no executable '
                         'patch or data.')

    def test_shape_b_unprovable_body_stays_blocked_with_named_reason(self):
        # Identifier never bound to a literal chain.
        source = ('[ENABLE]\n'
                  'label(inert)\n'
                  '{$lua}\n'
                  'local ok, receipt = autoAssemble(mystery)\n'
                  '[DISABLE]\n'
                  '{$lua}\n'
                  'autoAssemble(nil, false, receipt)\n')
        with self.assertRaises(AutoAssembleProofError) as caught:
            prepare_lua_program(source, PROCESS, 64)
        self.assertEqual(str(caught.exception),
                         'Auto-assembled program body is not statically provable.')
        # Identifier bound through a non-literal chain member.
        source = ('[ENABLE]\n'
                  'label(inert)\n'
                  '{$lua}\n'
                  "local body = 'a' .. readInteger(getLocalBase())\n"
                  'local ok, receipt = autoAssemble(body)\n'
                  '[DISABLE]\n'
                  '{$lua}\n'
                  'autoAssemble(nil, false, receipt)\n')
        with self.assertRaises(AutoAssembleProofError) as caught:
            prepare_lua_program(source, PROCESS, 64)
        self.assertEqual(str(caught.exception),
                         'Auto-assembled program body is not statically provable.')

    def test_shape_b_empty_body_is_refused_with_named_reason(self):
        source = ('[ENABLE]\n'
                  'label(inert)\n'
                  '{$lua}\n'
                  "local ok, receipt = autoAssemble('')\n"
                  '[DISABLE]\n'
                  '{$lua}\n'
                  "autoAssemble('', false, receipt)\n")
        with self.assertRaises(AutoAssembleProofError) as caught:
            prepare_lua_program(source, PROCESS, 64)
        self.assertEqual(str(caught.exception),
                         'Auto-assembled program body is empty.')

    def test_shape_b_provable_first_argument_forms(self):
        expected = '[ENABLE]\ndb 90 E9\n[DISABLE]\ndb 00'
        cases = {
            'double-quoted literal': (
                'local ok, receipt = autoAssemble('
                '"[ENABLE]\\ndb 90 E9\\n[DISABLE]\\ndb 00")\n',
                expected),
            'single-quoted literal': (
                "local ok, receipt = autoAssemble("
                "'[ENABLE]\\ndb 90 E9\\n[DISABLE]\\ndb 00')\n",
                expected),
            # Level 2 long string so the body keeps its leading [ bracket.
            'long string': (
                'local ok, receipt = autoAssemble('
                '[==[[ENABLE]\ndb 90 E9\n[DISABLE]\ndb 00]==])\n',
                expected),
            'concatenated literal chain through an identifier': (
                "local body = '[ENABLE]\\n' .. 'db 90 E9' .. '\\n[DISABLE]\\n' "
                ".. 'db 00'\n"
                'local ok, receipt = autoAssemble(body)\n',
                expected),
        }
        for name, (lua, body) in cases.items():
            with self.subTest(form=name):
                source = ('[ENABLE]\n'
                          'label(inert)\n'
                          '{$lua}\n' + lua +
                          '[DISABLE]\n'
                          '{$lua}\n'
                          'autoAssemble(nil, false, receipt)\n')
                program = prepare_lua_program(source, PROCESS, 64)
                self.assertIsNone(program['static_program'])
                proof = program['auto_assemble']
                self.assertEqual(len(proof['calls']), 1)
                self.assertEqual(proof['calls'][0]['body_sha256'],
                                 sha256(body.encode('utf-8')).hexdigest())
                # The bodies carry no registersymbol, so no symbol merges.
                self.assertEqual(proof['body_symbols'], [])
                self.assertEqual(program['provides'], [])

    def test_shape_b_retire_call_is_ignored_and_keeps_original_refusal(self):
        source = ('[ENABLE]\n'
                  'label(inert)\n'
                  '{$lua}\n'
                  'autoAssemble(nil, nil)\n'
                  '[DISABLE]\n'
                  '{$lua}\n'
                  'return nil\n')
        with self.assertRaises(LuaProgramError) as caught:
            prepare_lua_program(source, PROCESS, 64)
        self.assertEqual(str(caught.exception),
                         'Static AA envelope: Enable section has no executable '
                         'patch or data.')

    def test_proof_body_count_bound_is_enforced(self):
        # 129 distinct single-line bodies exceed the 128 proof body bound.
        lines = "\n".join("autoAssemble('x%d')" % i for i in range(129))
        source = '[ENABLE]\nlabel(inert)\n{$lua}\n' + lines + '\n[DISABLE]\n{$lua}\n'
        with self.assertRaises(AutoAssembleProofError) as caught:
            prepare_lua_program(source, PROCESS, 64)
        self.assertEqual(str(caught.exception),
                         'Auto-assembled program call count exceeds its bound.')

    def test_proof_body_size_bound_is_enforced(self):
        # A quoted body above the source byte bound is refused before any
        # symbols are derived (defense in depth: the record source itself is
        # bounded, so this trips only when a chunk is assembled by the
        # scanner).
        parts = [_Part('lua', 'enable', "autoAssemble('"
                    + 'x' * (MAX_SOURCE_BYTES + 1) + "')")]
        with self.assertRaises(AutoAssembleProofError) as caught:
            _auto_assemble_proof(parts, PROCESS, 64)
        self.assertEqual(str(caught.exception),
                         'Auto-assembled program body exceeds its size bound.')

    def test_shape_c_provable_attaches_proof(self):
        program = prepare_lua_program(SHAPE_C, PROCESS, 64)
        self.assertIsNone(program['static_program'])
        self.assertIsNotNone(program['auto_assemble'])
        self.assertEqual(program['auto_assemble']['body_symbols'], ['code'])
        self.assertEqual(program['provides'], ['code'])
        validate_lua_program(program)

    def test_shape_c_unprovable_leaves_profile_untouched(self):
        program = prepare_lua_program(
            '{$lua}\n'
            '[ENABLE]\n'
            'local ok, receipt = autoAssemble(buildBody())\n'
            '[DISABLE]\n'
            'autoAssemble(nil, nil, receipt)\n', PROCESS, 64)
        self.assertIsNone(program['static_program'])
        self.assertNotIn('auto_assemble', program)
        self.assertEqual(program['provides'], [])
        self.assertEqual(program['requires'], [])
        validate_lua_program(program)

    def test_hybrid_keeps_static_program_without_proof_field(self):
        program = prepare_lua_program(
            '[ENABLE]\n'
            'assert(1040,00)\n'
            '1040:\n'
            'db 90 E9\n'
            '{$lua}\n'
            'local ok, receipt = autoAssemble('
            '[=[ENABLE]\ndb 90\n[DISABLE]\ndb 00\n]=])\n'
            '[DISABLE]\n'
            '1040:\n'
            'db 00\n'
            '{$lua}\n'
            'autoAssemble(nil, false, receipt)\n', PROCESS, 64)
        self.assertIsNotNone(program['static_program'])
        self.assertNotIn('auto_assemble', program)
        validate_lua_program(program)

    def test_forged_proof_metadata_is_rejected_by_regeneration(self):
        program = prepare_lua_program(SHAPE_B, PROCESS, 64)
        for tamper in (
            lambda p: p['auto_assemble']['body_symbols'].append('forged'),
            lambda p: p['auto_assemble']['calls'][0].__setitem__(
                'body_sha256', '0' * 64),
            lambda p: p['auto_assemble'].pop('calls'),
            lambda p: p.pop('auto_assemble'),
            lambda p: p['provides'].append('forged'),
        ):
            with self.subTest():
                forged = deepcopy(program)
                tamper(forged)
                with self.assertRaises(LuaProgramError):
                    validate_lua_program(forged)


class AutoAssemblePlanValidatorTests(unittest.TestCase):
    """Both plan validators reject forged or stripped proof fields."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.ct = self.root / 'shape-b.ct'
        self.ct.write_text(
            '<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
            '<CheatEntry><ID>1</ID><Description>"Assembled"</Description>'
            '<VariableType>Auto Assembler Script</VariableType>'
            '<AssemblerScript>%s</AssemblerScript></CheatEntry>'
            '</CheatEntries></CheatTable>' % xml.sax.saxutils.escape(SHAPE_B),
            encoding='utf-8')
        self.plan = compile_table(self.ct, PROCESS)

    def _entry(self):
        return next(entry for entry in self.plan['entries'] if entry['id'] == 1)

    def test_canonical_plan_validates_and_carries_the_proof(self):
        entry = self._entry()
        self.assertTrue(entry['supported'])
        self.assertIn('auto_assemble', entry['lua_program'])
        self.assertEqual(entry['provides'], ['code'])
        compiler_validate_plan(self.plan)
        validate_plan(self.plan)

    def test_forged_or_stripped_proof_is_rejected_by_both_validators(self):
        for tamper in (
            lambda e: e['lua_program']['auto_assemble']['body_symbols'].append(
                'forged'),
            lambda e: e['lua_program'].pop('auto_assemble'),
            lambda e: e['provides'].append('forged'),
        ):
            with self.subTest():
                forged = deepcopy(self.plan)
                tamper(self._entry_from(forged))
                with self.assertRaises(NativeCompileError):
                    compiler_validate_plan(forged)
                with self.assertRaises(NativeRuntimeError):
                    validate_plan(forged)

    @staticmethod
    def _entry_from(plan):
        return next(entry for entry in plan['entries'] if entry['id'] == 1)


class CaveMemory(FakeMemory):
    """Fake target with one flat data page; allocations land in the cave."""

    def __init__(self, cave=0x10000, cave_size=0x1000):
        super().__init__()
        self.cave, self.cave_size = cave, cave_size
        extended = bytearray(cave_size + cave - self.base)
        extended[:len(self.data)] = self.data
        self.data = extended
        self.allocations = {}
        self.allocation_protections = {}
        self.releases = []
        self._next = cave

    @property
    def identity(self):
        return self.pid, self.creation_time

    def _range(self, address, size):
        if not self.base <= address or address + size > self.base + len(self.data):
            raise ValueError('Outside owned fixture memory')

    def is_executable(self, address, size):
        return False

    def allocate(self, size, near=None):
        base = self._next
        self._next += (size + 7) & ~7
        self.allocations[base] = size
        return base

    def allocation_size(self, address):
        return self.allocations[address]

    def protect_allocation(self, address, executable=True, writable=False):
        self.allocation_protections[address] = \
            (0x40 if writable else 0x20) if executable else 0x04

    def _query(self, address):
        for base, size in self.allocations.items():
            if base <= address < base + size:
                return SimpleNamespace(BaseAddress=base, AllocationBase=base,
                                       RegionSize=size, State=0x1000,
                                       Protect=self.allocation_protections.get(base, 0x04))
        raise ValueError('unmapped allocation range')

    def release(self, address):
        self.releases.append(address)


class AutoAssembleRuntimeTests(unittest.TestCase):
    """Runtime: the proven body assembles; the inert envelope never does."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.memory = CaveMemory()
        self.engine = None

    def tearDown(self):
        if self.engine is not None and not self.engine.closed:
            self.memory.alive = False
            self.engine.poll()
            self.engine.close()

    def _engine(self, script):
        ct = self.root / 'table.ct'
        ct.write_text(
            '<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
            '<CheatEntry><ID>1</ID><Description>"Assembled"</Description>'
            '<VariableType>Auto Assembler Script</VariableType>'
            '<AssemblerScript>%s</AssemblerScript></CheatEntry>'
            '</CheatEntries></CheatTable>' % xml.sax.saxutils.escape(script),
            encoding='utf-8')
        plan = compile_table(ct, PROCESS)
        self.engine = TrainerEngine(plan, state_dir=self.root / 'state',
                                    process_lock_dir=self.root / 'shared',
                                    memory_factory=lambda name: self.memory,
                                    hook_coordinator=Coordinator())
        self.engine.poll()
        return self.engine

    def test_shape_b_enable_patches_via_body_and_disable_retires_receipt(self):
        engine = self._engine(SHAPE_B)
        self.assertTrue(engine.toggle(1, True))
        scope = engine.lua_activations[1]
        # The inert outer envelope was never assembled.
        self.assertIsNone(scope.record_assembly_token)
        # The body assembled once and owns the export (gate proven).
        self.assertEqual(len(scope.assemblies), 1)
        self.assertIn('code', engine.symbols)
        self.assertEqual(self.memory.read(engine.symbols['code'], 2),
                         b'\x90\xe9')
        self.assertFalse(engine.toggle(1, False))
        # The disable Lua retired the body receipt and the export is gone.
        self.assertEqual(len(scope.assemblies), 0)
        self.assertNotIn('code', engine.symbols)
        self.assertNotIn(1, engine.applied)
        self.assertNotIn(1, engine.desired)
        self.assertFalse(engine.blocked)

    def test_shape_c_pure_lua_record_round_trips(self):
        engine = self._engine(SHAPE_C)
        self.assertTrue(engine.toggle(1, True))
        scope = engine.lua_activations[1]
        self.assertIsNone(scope.record_assembly_token)
        self.assertIn('code', engine.symbols)
        self.assertEqual(self.memory.read(engine.symbols['code'], 2),
                         b'\x90\xe9')
        self.assertFalse(engine.toggle(1, False))
        self.assertEqual(len(scope.assemblies), 0)
        self.assertNotIn('code', engine.symbols)
        self.assertFalse(engine.blocked)


if __name__ == '__main__':
    unittest.main()
