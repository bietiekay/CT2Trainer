"""N-16: the corpus speed surface is wired through the tested Clock v2 model.

``speedhack_setSpeed`` / ``speedhack_getSpeed`` (pinned Alien Isolation and
re2 records) are routed by the engine's per-attach
:class:`~ct2trainer.native.clock_binding.ClockSpeedBinding` through the
tested core/gateway model. The real Windows clock route (AP-11) remains
open, so the production default binding is not-ready and refuses visibly
instead of inventing time.
"""
from pathlib import Path
import tempfile
import unittest
import xml.sax.saxutils

from test_native_engine_code import Coordinator
from test_native_lua_activation import Memory

from ct2trainer.native.clock_binding import (
    ClockBadMultiplier,
    ClockFault,
    ClockNotAttached,
    ClockRateOutOfRange,
    ClockSpeedBinding,
    ClockTerminated,
    default_speed_binding,
)
from ct2trainer.native.clock_engine import (
    COMMAND_SET_RATE,
    ClockBadInput,
    ClockCommand,
    ClockConfig,
    ClockCore,
    ClockGateway,
    FakeCounter,
    GatewayStatus,
    RATE_MAX_CORE,
    RATE_ONE,
)
from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import NativeRuntimeError, TrainerEngine
from ct2trainer.native.lua_host import EngineLuaBroker, LuaHostError

FREQ = 1000
PROCESS = "FixtureTarget.exe"

FAST_SCRIPT = ('[ENABLE]\n{$lua}\nspeedhack_setSpeed(2.0)\nreturn nil\n{$asm}\n'
               '[DISABLE]\n{$lua}\nspeedhack_setSpeed(1.0)\nreturn nil\n{$asm}')
SLOW_SCRIPT = ('[ENABLE]\n{$lua}\nif speedhack_getSpeed() ~= 0.4 then\n'
               '  speedhack_setSpeed(0.4)\nend\nreturn nil\n{$asm}\n'
               '[DISABLE]\n{$lua}\nspeedhack_setSpeed(1.0)\nreturn nil\n{$asm}')


def make_stack(rate_max_ppm=RATE_MAX_CORE):
    """One tested-model stack: (binding, core, scripted counter)."""
    counter = FakeCounter(now=2000)
    config = ClockConfig(
        frequency=FREQ,
        qpc_origin=1000,
        initial_raw_qpc=2000,
        tick64_origin=10000,
        tick64_capture_qpc=1500,
        multimedia_origin=20000,
        multimedia_capture_qpc=1700,
        raw_counter=counter,
    )
    core = ClockCore(config, rate_max_ppm=rate_max_ppm)
    return (ClockSpeedBinding(core, ClockGateway(core, counter)), core, counter)


def write_speed_table(root: Path) -> Path:
    """Corpus-shaped speed records as pure {$lua} scripts (no luacall)."""
    entries = []
    for row_id, label, script in (
            (0, 'Game   [Speed]   Fast', FAST_SCRIPT),
            (1, 'slow motion .4c (speedhack)', SLOW_SCRIPT)):
        entries.append(
            '    <CheatEntry>\n'
            '      <ID>' + str(row_id) + '</ID>\n'
            '      <Description>"' + xml.sax.saxutils.escape(label) + '"</Description>\n'
            '      <VariableType>Auto Assembler Script</VariableType>\n'
            '      <AssemblerScript>' + xml.sax.saxutils.escape(script)
            + '</AssemblerScript>\n'
            '    </CheatEntry>\n')
    path = root / 'speed_fixture.ct'
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<CheatTable CheatEngineTableVersion="45">\n'
        '  <CheatEntries>\n'
        + ''.join(entries)
        + '  </CheatEntries>\n'
        '</CheatTable>\n',
        encoding='utf-8')
    return path


class ClockSpeedBindingTests(unittest.TestCase):
    def setUp(self):
        self.binding, self.core, self.counter = make_stack()

    def test_fresh_binding_reports_normal_time_without_owner(self):
        self.assertFalse(self.binding.active)
        self.assertEqual(self.binding.get_speed(), 1.0)
        self.assertEqual(self.core.owner, 0)

    def test_set_speed_applies_rate_lease_and_acked_roundtrip(self):
        self.assertIsNone(self.binding.set_speed(2.5))
        self.assertEqual(self.core.rate_ppm, 2500000)
        self.assertEqual(self.core.owner, 1)
        self.assertEqual(self.core.lease_deadline, 2000 + FREQ * 30)
        self.assertEqual(self.binding.gateway.last_sequence, 1)
        self.assertEqual(self.binding.get_speed(), 2.5)
        self.assertTrue(self.binding.active)

    def test_zero_rate_freezes_the_scaled_clock(self):
        self.binding.set_speed(2.0)
        self.binding.set_speed(0.0)
        self.assertEqual(self.core.rate_ppm, 0)
        self.counter.now = 12000
        self.assertEqual(self.binding.get_speed(), 0.0)

    def test_fractional_multipliers_map_to_ppm(self):
        for speed, ppm in ((0.25, 250000), (0.5, 500000),
                           (1.25, 1250000), (2.0, 2000000)):
            self.binding.set_speed(speed)
            self.assertEqual(self.core.rate_ppm, ppm)

    def test_invalid_multipliers_refuse_without_state_change(self):
        before = (self.core.rate_ppm, self.core.owner,
                  self.binding.gateway.last_sequence)
        for value in ('2.5', True, -1.0, -1, float('nan'), float('inf'),
                      None, [2.0]):
            with self.assertRaises(ClockBadMultiplier):
                self.binding.set_speed(value)
        after = (self.core.rate_ppm, self.core.owner,
                 self.binding.gateway.last_sequence)
        self.assertEqual(before, after)

    def test_out_of_profile_rate_refuses_visibly_without_clamping(self):
        for value in (16.001, 17.0, 20.0, 2 * RATE_ONE):
            with self.assertRaises(ClockRateOutOfRange):
                self.binding.set_speed(value)
        self.assertEqual(self.core.rate_ppm, RATE_ONE)
        self.assertEqual(self.core.owner, 0)

    def test_wider_profile_admits_x20(self):
        binding, core, _ = make_stack(rate_max_ppm=20 * RATE_ONE)
        binding.set_speed(20.0)
        self.assertEqual(core.rate_ppm, 20 * RATE_ONE)
        self.assertEqual(binding.get_speed(), 20.0)

    def test_tick_renews_a_held_lease_and_keeps_the_rate(self):
        self.binding.set_speed(2.0)
        self.assertEqual(self.core.lease_deadline, 2000 + FREQ * 30)
        self.counter.now = 25000
        self.binding.tick()
        self.assertEqual(self.core.lease_deadline, 25000 + FREQ * 30)
        self.assertEqual(self.core.rate_ppm, 2 * RATE_ONE)
        self.assertEqual(self.core.owner, 1)

    def test_tick_is_inert_without_a_held_lease(self):
        before = (self.core.lease_deadline, self.binding.gateway.last_sequence)
        self.counter.now = 4000
        self.binding.tick()
        self.assertEqual(before, (self.core.lease_deadline,
                                  self.binding.gateway.last_sequence))

    def test_finish_retires_owner_refuses_later_calls_and_is_idempotent(self):
        self.binding.set_speed(2.0)
        self.binding.finish()
        self.assertTrue(self.binding.terminated)
        self.assertEqual(self.core.owner, 0)
        self.assertEqual(self.core.rate_ppm, RATE_ONE)
        with self.assertRaises(ClockTerminated):
            self.binding.set_speed(2.0)
        with self.assertRaises(ClockTerminated):
            self.binding.get_speed()
        self.binding.finish()
        self.assertTrue(self.binding.terminated)

    def test_finish_cancels_in_flight_intent_and_fences_the_owner(self):
        pending = ClockCommand(
            sequence=1, owner=1, operation=COMMAND_SET_RATE,
            rate_ppm=2 * RATE_ONE,
            not_after_qpc=2000 + FREQ,
            lease_deadline_qpc=2000 + FREQ * 30)
        self.assertEqual(self.binding.gateway.submit(pending), GatewayStatus.OK)
        self.assertEqual(self.binding.gateway.slot, 'READY')
        self.binding.finish()
        self.assertEqual(self.binding.gateway.slot, 'EMPTY')
        self.assertEqual(self.binding.gateway.owner_fence, 1)
        self.assertEqual(self.core.owner, 0)
        self.assertEqual(self.core.rate_ppm, RATE_ONE)
        resubmit = ClockCommand(
            sequence=2, owner=1, operation=COMMAND_SET_RATE,
            rate_ppm=2 * RATE_ONE,
            not_after_qpc=2000 + FREQ,
            lease_deadline_qpc=2000 + FREQ * 30)
        self.assertEqual(self.binding.gateway.submit(resubmit),
                         GatewayStatus.FENCED_OWNER)

    def test_default_binding_faults_visibly_until_the_clock_route_exists(self):
        binding = default_speed_binding()
        with self.assertRaises(ClockFault):
            binding.set_speed(2.0)
        with self.assertRaises(ClockFault):
            binding.get_speed()
        binding.tick()
        self.assertFalse(binding.terminated)
        binding.finish()
        self.assertTrue(binding.terminated)
        with self.assertRaises(ClockTerminated):
            binding.get_speed()

    def test_construction_requires_the_tested_model_and_positive_owner(self):
        _, core, _ = make_stack()
        with self.assertRaises(ClockBadInput):
            ClockSpeedBinding(core, object())
        gateway = ClockGateway(core, FakeCounter(now=2000))
        with self.assertRaises(ClockBadInput):
            ClockSpeedBinding(object(), gateway)
        with self.assertRaises(ClockBadInput):
            ClockSpeedBinding(core, gateway, owner=0)


class EngineSpeedWiringTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.table = write_speed_table(root)
        self.memory = Memory()
        self.stacks = []
        self.engine = TrainerEngine(
            compile_table(self.table, PROCESS),
            state_dir=root / 'state',
            process_lock_dir=root / 'shared',
            memory_factory=lambda name: self.memory,
            hook_coordinator=Coordinator(),
            clock_factory=self._fresh_stack)
        self.engine.poll()
        self.assertTrue(self.engine.connected)

    def _fresh_stack(self, name: str):
        stack = make_stack()
        self.stacks.append(stack)
        return stack[0]

    def tearDown(self):
        if not self.engine.closed:
            self.memory.alive = False
            self.engine.poll()
            self.engine.close()
        self.directory.cleanup()

    def test_session_and_broker_refuse_visibly_before_attach(self):
        engine = TrainerEngine(
            compile_table(self.table, PROCESS),
            state_dir=Path(self.directory.name) / 'second',
            process_lock_dir=Path(self.directory.name) / 'second_shared',
            memory_factory=lambda name: Memory(),
            hook_coordinator=Coordinator(),
            clock_factory=self._fresh_stack)
        self.assertIsNone(engine.clock)
        with self.assertRaisesRegex(NativeRuntimeError, 'not connected'):
            engine.open_lua_session()
        self.assertTrue(engine.close())

    def test_broker_refuses_when_the_engine_loses_its_binding(self):
        clock = self.engine.clock
        self.engine.clock = None
        try:
            with self.assertRaises(ClockNotAttached):
                EngineLuaBroker(self.engine).call(
                    'speedhack_getSpeed', (), generation=0, syntaxcheck=False)
            with self.assertRaises(ClockNotAttached):
                EngineLuaBroker(self.engine).call(
                    'speedhack_setSpeed', (2.0,), generation=0, syntaxcheck=False)
        finally:
            self.engine.clock = clock

    def test_lua_session_reads_normal_time_before_any_toggle(self):
        host = self.engine.open_lua_session()
        self.assertEqual(host.execute('return speedhack_getSpeed()'), 1.0)

    def test_toggle_runs_the_corpus_speed_programs_and_restores_time(self):
        self.assertTrue(self.engine.toggle(0, True))
        core = self.stacks[-1][1]
        self.assertEqual(core.rate_ppm, 2 * RATE_ONE)
        self.assertEqual(core.owner, 1)
        host = self.engine.lua_activations[0].host
        self.assertEqual(host.execute('return speedhack_getSpeed()'), 2.0)
        self.assertFalse(self.engine.toggle(0, False))
        self.assertEqual(core.rate_ppm, RATE_ONE)
        session = self.engine.open_lua_session()
        self.assertEqual(session.execute('return speedhack_getSpeed()'), 1.0)

    def test_slow_motion_record_reads_before_writing(self):
        self.assertTrue(self.engine.toggle(1, True))
        core = self.stacks[-1][1]
        self.assertEqual(core.rate_ppm, 400000)
        self.assertEqual(core.owner, 1)
        self.assertFalse(self.engine.toggle(1, False))
        self.assertEqual(core.rate_ppm, RATE_ONE)

    def test_close_retires_the_binding_and_refuses_later_speed(self):
        self.assertTrue(self.engine.toggle(0, True))
        host = self.engine.lua_activations[0].host
        binding = self.engine.clock
        core = self.stacks[-1][1]
        self.assertTrue(self.engine.close())
        self.assertIsNone(self.engine.clock)
        self.assertTrue(binding.terminated)
        self.assertEqual(core.owner, 0)
        self.assertEqual(core.rate_ppm, RATE_ONE)
        with self.assertRaises(ClockTerminated):
            binding.get_speed()
        with self.assertRaisesRegex(LuaHostError, 'cancelled'):
            host.execute('return speedhack_getSpeed()')

    def test_target_exit_retires_the_binding_and_reattach_starts_fresh(self):
        self.assertTrue(self.engine.toggle(0, True))
        self.assertFalse(self.engine.toggle(0, False))
        first = self.stacks[-1]
        self.memory.alive = False
        status = self.engine.poll()
        self.assertIn('Target ended', status)
        self.assertIsNone(self.engine.clock)
        self.assertTrue(first[0].terminated)
        self.assertEqual(first[1].owner, 0)
        self.assertEqual(first[1].rate_ppm, RATE_ONE)
        self.memory.alive = True
        self.engine.poll()
        self.assertEqual(len(self.stacks), 2)
        second = self.stacks[-1]
        self.assertIs(self.engine.clock, second[0])
        self.assertFalse(second[0].terminated)
        self.assertEqual(second[1].rate_ppm, RATE_ONE)

    def test_poll_keeps_the_speed_lease_alive(self):
        self.assertTrue(self.engine.toggle(0, True))
        stack = self.stacks[-1]
        core, counter = stack[1], stack[2]
        self.assertEqual(core.lease_deadline, 2000 + FREQ * 30)
        counter.now = 25000
        self.engine.poll()
        self.assertEqual(core.lease_deadline, 25000 + FREQ * 30)
        self.assertEqual(core.rate_ppm, 2 * RATE_ONE)

    def test_host_refusals_have_no_target_effect(self):
        host = self.engine.open_lua_session()
        binding, core, _ = self.stacks[-1]
        gateway = binding.gateway
        count = len(self.memory.writes)
        state = (core.rate_ppm, core.owner, core.lease_deadline,
                 gateway.last_sequence)
        for source, needle in (
                ('return speedhack_setSpeed("2.0")', 'numeric'),
                ('return speedhack_setSpeed(-1)', 'not be negative'),
                ('return speedhack_setSpeed(true)', 'numeric'),
                ('return speedhack_setSpeed(20)', 'profile'),
                ('return speedhack_getSpeed(1)', 'takes no arguments')):
            with self.assertRaisesRegex(LuaHostError, needle):
                host.execute(source)
        self.assertEqual(len(self.memory.writes), count)
        self.assertEqual((core.rate_ppm, core.owner, core.lease_deadline,
                          gateway.last_sequence), state)

    def test_platform_fault_stays_visible_and_poll_stays_unblocked(self):
        self.assertTrue(self.engine.toggle(0, True))
        host = self.engine.open_lua_session()
        core, counter = self.stacks[-1][1], self.stacks[-1][2]
        self.assertEqual(core.rate_ppm, 2 * RATE_ONE)
        counter.fail = True
        with self.assertRaisesRegex(LuaHostError, 'failed with status|sticky fault'):
            host.execute('return speedhack_getSpeed()')
        with self.assertRaises(ClockFault):
            self.engine.clock.set_speed(2.0)
        self.engine.poll()
        self.assertFalse(self.engine.blocked)
