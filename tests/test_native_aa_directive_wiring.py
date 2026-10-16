"""Wiring: createThread/threadWait, protect/unprotect and
getmodulehandle/getprocaddress are active in the AA pipeline.

- ``prepare_program`` parses the six directives into bounded nodes, reports
  them via capabilities and round-trips through ``validate_program``;
  out-of-grammar shapes are refused at parse time.
- ``preflight_program`` resolves addresses and executes side-effect nodes
  through the injected models only when ``execute_side_effects`` is true;
  read-only export nodes always execute. Missing models refuse visibly
  fail-closed before any effect.
- ``dry_link_program`` never spawns or protects, but still returns the
  read-only export observations.
- The engine gates activation on the injected backends (default: thread and
  protection refuse, export uses the linked memory as read-only backend),
  shares one model across preflight / enable link / inverse disable link and
  never invokes a factory for records without the capability.
"""
import tempfile
import unittest
from pathlib import Path

from aa_directives_fixture_data import (HeldExportBackend,
                                        ScriptedProtectionBackend,
                                        ScriptedThreadBackend, fixture_images)
from test_native_engine_code import Coordinator
from test_native_lua_activation import Memory
from ct2trainer.native.aa_directives import (PAGE_READWRITE,
                                               ProtectionDirectiveModel,
                                               TargetApiDirectiveModel,
                                               ThreadDirectiveModel)
from ct2trainer.native.aa_program import (ProgramError, dry_link_program,
                                           prepare_program, preflight_program)
from ct2trainer.native.compiler import compile_table
from ct2trainer.native.engine import NativeRuntimeError, TrainerEngine

PROCESS = "FixtureTarget.exe"

THREAD_SOURCE = """[ENABLE]
createThread(FixtureTarget.exe+0x10)
threadWait()
FixtureTarget.exe+0x20:
dd 1
[DISABLE]
FixtureTarget.exe+0x20:
dd 0"""

PROTECT_SOURCE = """[ENABLE]
protect(0x1000,0x1000,PAGE_READWRITE)
FixtureTarget.exe+0x20:
dd 1
[DISABLE]
unprotect(0x1000,0x1000,PAGE_READWRITE)
FixtureTarget.exe+0x20:
dd 0"""

PROTECT_ROUNDTRIP_SOURCE = """[ENABLE]
protect(0x1000,0x1000,PAGE_READWRITE)
unprotect(0x1000,0x1000,PAGE_READWRITE)
FixtureTarget.exe+0x20:
dd 1
[DISABLE]
FixtureTarget.exe+0x20:
dd 0"""

UNPROTECT_ONLY_SOURCE = """[ENABLE]
unprotect(0x1000,0x1000,PAGE_READWRITE)
FixtureTarget.exe+0x20:
dd 1
[DISABLE]
FixtureTarget.exe+0x20:
dd 0"""

EXPORT_MODULE_SOURCE = """[ENABLE]
getmodulehandle("fixturetarget.exe")
FixtureTarget.exe+0x20:
dd 1
[DISABLE]
FixtureTarget.exe+0x20:
dd 0"""

EXPORT_PROC_SOURCE = """[ENABLE]
getprocaddress("fixture","Alpha")
FixtureTarget.exe+0x20:
dd 1
[DISABLE]
FixtureTarget.exe+0x20:
dd 0"""

SIMPLE_SOURCE = """[ENABLE]
FixtureTarget.exe+0x20:
dd 1
[DISABLE]
FixtureTarget.exe+0x20:
dd 0"""


def _ct_path(root, source, name="owned.ct"):
    table = Path(root) / name
    table.write_text('<CheatTable CheatEngineTableVersion="45"><CheatEntries>'
                     '<CheatEntry><ID>1</ID><Description>Owned directive record</Description>'
                     '<VariableType>Auto Assembler Script</VariableType>'
                     '<AssemblerScript><![CDATA[' + source + ']]></AssemblerScript>'
                     '</CheatEntry></CheatEntries></CheatTable>',
                     encoding="utf-8")
    return table


class DirectiveParseTests(unittest.TestCase):
    def test_parse_creates_nodes_and_capabilities(self):
        thread = prepare_program(THREAD_SOURCE, PROCESS, bitness=64)
        self.assertEqual(
            [node["op"] for node in thread["enable"]],
            ["createthread", "threadwait", "cursor", "data"])
        self.assertEqual(thread["enable"][0]["address"], "FixtureTarget.exe+0x10")
        self.assertIn("createthread", thread["capabilities"])
        self.assertIn("threadwait", thread["capabilities"])

        protect = prepare_program(PROTECT_SOURCE, PROCESS, bitness=64)
        self.assertEqual(protect["enable"][0]["op"], "protect")
        self.assertEqual(protect["disable"][0]["op"], "unprotect")
        self.assertEqual(protect["enable"][0]["address"], "0x1000")
        self.assertEqual(protect["enable"][0]["size"], 0x1000)
        self.assertEqual(protect["enable"][0]["page"], PAGE_READWRITE)
        self.assertIn("protect", protect["capabilities"])
        self.assertIn("unprotect", protect["capabilities"])

        export = prepare_program(EXPORT_PROC_SOURCE, PROCESS, bitness=64)
        self.assertEqual(export["enable"][0],
                         {"op": "getprocaddress", "module": "fixture",
                          "export": "Alpha"})
        self.assertIn("getprocaddress", export["capabilities"])
        module = prepare_program(EXPORT_MODULE_SOURCE, PROCESS, bitness=64)
        self.assertEqual(module["enable"][0],
                         {"op": "getmodulehandle", "module": "fixturetarget.exe"})
        self.assertIn("getmodulehandle", module["capabilities"])
        # Round-trip through validate_program (strict JSON equality).
        prepare_program(PROTECT_SOURCE, PROCESS, bitness=64)

    def test_parse_refuses_wrong_argument_counts(self):
        cases = [
            ("[ENABLE]\ncreateThread()\nFixtureTarget.exe+0x20:\ndd 1\n[DISABLE]\nFixtureTarget.exe+0x20:\ndd 0",
             "createThread requires one address expression"),
            ("[ENABLE]\ncreateThread(a,b)\nFixtureTarget.exe+0x20:\ndd 1\n[DISABLE]\nFixtureTarget.exe+0x20:\ndd 0",
             "createThread requires one address expression"),
            ("[ENABLE]\nthreadWait(1)\nFixtureTarget.exe+0x20:\ndd 1\n[DISABLE]\nFixtureTarget.exe+0x20:\ndd 0",
             "threadWait takes no arguments"),
            ("[ENABLE]\nprotect(0x1000,0x1000)\nFixtureTarget.exe+0x20:\ndd 1\n[DISABLE]\nFixtureTarget.exe+0x20:\ndd 0",
             "protect requires an address expression, a byte size and a page constant"),
            ("[ENABLE]\nunprotect(0x1000,0x1000,PAGE_READWRITE,1)\nFixtureTarget.exe+0x20:\ndd 1\n[DISABLE]\nFixtureTarget.exe+0x20:\ndd 0",
             "unprotect requires an address expression, a byte size and a page constant"),
            ("[ENABLE]\ngetmodulehandle(\"fixturetarget.exe\",\"x\")\nFixtureTarget.exe+0x20:\ndd 1\n[DISABLE]\nFixtureTarget.exe+0x20:\ndd 0",
             "getmodulehandle requires one quoted module name"),
            ("[ENABLE]\ngetprocaddress(\"fixture\")\nFixtureTarget.exe+0x20:\ndd 1\n[DISABLE]\nFixtureTarget.exe+0x20:\ndd 0",
             "getprocaddress requires a quoted module name and a quoted export name"),
        ]
        for source, message in cases:
            with self.subTest(source=source.splitlines()[1]), \
                    self.assertRaisesRegex(ProgramError, message):
                prepare_program(source, PROCESS, bitness=64)

    def test_parse_refuses_bad_protect_arguments(self):
        base = ("[ENABLE]\nprotect(0x1000,0x1000,%s)"
                "\nFixtureTarget.exe+0x20:\ndd 1\n[DISABLE]\nFixtureTarget.exe+0x20:\ndd 0")
        with self.assertRaisesRegex(ProgramError, "page must be a PAGE_\\* name or integer constant"):
            prepare_program(base % "PAGE_BOGUS", PROCESS, bitness=64)
        for size in ("0", "0x2000000"):
            source = ("[ENABLE]\nprotect(0x1000,%s,PAGE_READWRITE)"
                      "\nFixtureTarget.exe+0x20:\ndd 1\n[DISABLE]\nFixtureTarget.exe+0x20:\ndd 0") % size
            with self.subTest(size=size), \
                    self.assertRaisesRegex(ProgramError, "protect size must contain 1"):
                prepare_program(source, PROCESS, bitness=64)

    def test_parse_accepts_page_integer_constant(self):
        source = ("[ENABLE]\nprotect(0x1000,0x1000,0x04)"
                  "\nFixtureTarget.exe+0x20:\ndd 1\n[DISABLE]\nFixtureTarget.exe+0x20:\ndd 0")
        node = prepare_program(source, PROCESS, bitness=64)["enable"][0]
        self.assertEqual(node["page"], PAGE_READWRITE)

    def test_parse_refuses_unquoted_module_or_export_name(self):
        cases = [
            ("getmodulehandle(fixturetarget.exe)", "exact quoted module name"),
            ('getmodulehandle("")', "exact quoted module name"),
            ("getprocaddress(fixture,Alpha)", "exact quoted module name"),
            ('getprocaddress("fixture",Alpha)', "exact quoted export name"),
        ]
        for directive, message in cases:
            source = ("[ENABLE]\n" + directive +
                      "\nFixtureTarget.exe+0x20:\ndd 1\n[DISABLE]\nFixtureTarget.exe+0x20:\ndd 0")
            with self.subTest(directive=directive), \
                    self.assertRaisesRegex(ProgramError, message):
                prepare_program(source, PROCESS, bitness=64)

    def test_parse_still_requires_executable_patch_or_data(self):
        # WP-36: a thread-only ENABLE now hits the named staged-runtime
        # gate (no thread backend in the shipped trainer profile) instead
        # of the generic empty-enable message.
        thread_only = "[ENABLE]\nthreadWait()\n[DISABLE]\nFixtureTarget.exe+0x20:\ndd 0"
        with self.assertRaisesRegex(ProgramError, "gated in the native staged runtime"):
            prepare_program(thread_only, PROCESS, bitness=64)
        # A genuinely empty ENABLE section keeps the generic message.
        empty = "[ENABLE]\n[DISABLE]\nFixtureTarget.exe+0x20:\ndd 0"
        with self.assertRaisesRegex(ProgramError, "no executable patch or data"):
            prepare_program(empty, PROCESS, bitness=64)


class DirectivePreflightTests(unittest.TestCase):
    def setUp(self):
        self.memory = Memory()
        self.thread_backend = ScriptedThreadBackend()
        self.thread_model = ThreadDirectiveModel(self.thread_backend)
        self.protection_backend = ScriptedProtectionBackend()
        self.protection_model = ProtectionDirectiveModel(self.protection_backend)
        self.export_backend = HeldExportBackend(fixture_images(64))
        self.export_model = TargetApiDirectiveModel(self.export_backend)

    def test_preflight_thread_spawn_and_wait_are_observed_once(self):
        program = prepare_program(THREAD_SOURCE, PROCESS, bitness=64)
        result = preflight_program(program, self.memory, {},
                                   thread_model=self.thread_model)
        observations = result["observations"]
        self.assertEqual(observations[0],
                         {"op": "create_thread", "thread": 1, "address": 0x1010})
        self.assertEqual(observations[1]["op"], "thread_wait")
        self.assertEqual(observations[1]["thread"], 1)
        self.assertEqual(observations[1]["exited"], True)
        self.assertEqual(observations[1]["exit_code"], 0)
        self.assertEqual(self.thread_backend.calls,
                         [("spawn", 1), ("poll", 1)])
        self.assertEqual(self.thread_model.threads()[0].entry_address, 0x1010)

    def test_preflight_thread_wait_before_create_is_refused(self):
        source = ("[ENABLE]\nthreadWait()\nFixtureTarget.exe+0x20:\ndd 1"
                  "\n[DISABLE]\nFixtureTarget.exe+0x20:\ndd 0")
        program = prepare_program(source, PROCESS, bitness=64)
        with self.assertRaisesRegex(ProgramError, "before any createThread"):
            preflight_program(program, self.memory, {},
                              thread_model=self.thread_model)
        self.assertEqual(self.thread_backend.calls, [])

    def test_preflight_thread_without_model_refuses_visibly(self):
        program = prepare_program(THREAD_SOURCE, PROCESS, bitness=64)
        with self.assertRaisesRegex(ProgramError, "thread backend"):
            preflight_program(program, self.memory, {})
        self.assertEqual(self.thread_backend.calls, [])

    def test_preflight_thread_side_effects_gated_by_flag(self):
        program = prepare_program(THREAD_SOURCE, PROCESS, bitness=64)
        result = preflight_program(program, self.memory, {},
                                   thread_model=self.thread_model,
                                   execute_side_effects=False)
        self.assertEqual(result["observations"], [])
        self.assertEqual(self.thread_backend.calls, [])
        self.assertEqual(self.thread_model.operations, [])

    def test_preflight_protection_applies_and_releases_once(self):
        program = prepare_program(PROTECT_ROUNDTRIP_SOURCE, PROCESS, bitness=64)
        result = preflight_program(program, self.memory, {},
                                   protection_model=self.protection_model)
        protect = result["observations"][0]
        unprotect = result["observations"][1]
        self.assertEqual(protect, {"op": "protect", "address": 0x1000,
                                   "size": 0x1000, "page": PAGE_READWRITE})
        self.assertEqual(unprotect["op"], "unprotect")
        self.assertTrue(unprotect["reverted"])
        self.assertEqual(self.protection_backend.applies,
                         [(0x1000, 0x1000, PAGE_READWRITE)])
        self.assertEqual(self.protection_backend.releases, [(0x1000, 0x1000)])
        self.assertEqual(self.protection_model.owned_regions, ())

    def test_preflight_unprotect_without_prior_protect_warns(self):
        program = prepare_program(UNPROTECT_ONLY_SOURCE, PROCESS, bitness=64)
        result = preflight_program(program, self.memory, {},
                                   protection_model=self.protection_model)
        unprotect = result["observations"][0]
        self.assertFalse(unprotect["reverted"])
        self.assertTrue(self.protection_model.warnings)
        self.assertEqual(self.protection_backend.applies, [])
        self.assertEqual(self.protection_backend.releases, [])

    def test_preflight_protection_without_model_refuses_visibly(self):
        program = prepare_program(PROTECT_SOURCE, PROCESS, bitness=64)
        with self.assertRaisesRegex(ProgramError, "protection backend"):
            preflight_program(program, self.memory, {})
        self.assertEqual(self.protection_backend.applies, [])

    def test_preflight_protection_alignment_error_is_visible(self):
        source = ("[ENABLE]\nprotect(0x1234,0x1000,PAGE_READWRITE)"
                  "\nFixtureTarget.exe+0x20:\ndd 1\n[DISABLE]\nFixtureTarget.exe+0x20:\ndd 0")
        program = prepare_program(source, PROCESS, bitness=64)
        with self.assertRaisesRegex(Exception, "page-aligned"):
            preflight_program(program, self.memory, {},
                              protection_model=self.protection_model)

    def test_preflight_export_observations_are_read_only(self):
        program = prepare_program(EXPORT_PROC_SOURCE, PROCESS, bitness=64)
        result = preflight_program(program, self.memory, {},
                                   export_model=self.export_model)
        observation = result["observations"][0]
        self.assertEqual(observation["op"], "getprocaddress")
        self.assertEqual(observation["module"], "fixture.dll")
        self.assertEqual(observation["export"], "Alpha")
        self.assertEqual(observation["base"], 0x710000)
        self.assertEqual(observation["address"], 0x711100)
        self.assertEqual(observation["rva"], 0x1100)
        self.assertFalse(observation["forwarded"])
        self.assertTrue(self.export_backend.reads)

    def test_preflight_export_module_handle_observation(self):
        source = ('[ENABLE]\ngetmodulehandle("fixture")'
                  "\nFixtureTarget.exe+0x20:\ndd 1\n[DISABLE]\nFixtureTarget.exe+0x20:\ndd 0")
        program = prepare_program(source, PROCESS, bitness=64)
        result = preflight_program(program, self.memory, {},
                                   export_model=self.export_model)
        self.assertEqual(result["observations"][0]["op"], "getmodulehandle")
        self.assertEqual(result["observations"][0]["module"], "fixture.dll")
        self.assertEqual(result["observations"][0]["base"], 0x710000)

    def test_preflight_export_dedup_on_rerun(self):
        program = prepare_program(EXPORT_PROC_SOURCE, PROCESS, bitness=64)
        for _ in range(3):
            preflight_program(program, self.memory, {},
                              export_model=self.export_model)
        self.assertEqual(len(self.export_model.operations), 1)
        self.assertEqual(len(self.export_model.report()["operations"]), 1)

    def test_preflight_export_without_model_refuses_visibly(self):
        program = prepare_program(EXPORT_MODULE_SOURCE, PROCESS, bitness=64)
        with self.assertRaisesRegex(ProgramError, "export backend"):
            preflight_program(program, self.memory, {})

    def test_preflight_export_still_observed_without_side_effects_flag(self):
        source = ('[ENABLE]\ngetmodulehandle("fixture")'
                  "\nFixtureTarget.exe+0x20:\ndd 1\n[DISABLE]\nFixtureTarget.exe+0x20:\ndd 0")
        program = prepare_program(source, PROCESS, bitness=64)
        result = preflight_program(program, self.memory, {},
                                   export_model=self.export_model,
                                   execute_side_effects=False)
        self.assertEqual(result["observations"][0]["op"], "getmodulehandle")


class DirectiveDryLinkTests(unittest.TestCase):
    def test_dry_link_never_spawns_but_reports_export_observations(self):
        memory = Memory()
        thread_backend = ScriptedThreadBackend()
        thread_model = ThreadDirectiveModel(thread_backend)
        protection_backend = ScriptedProtectionBackend()
        protection_model = ProtectionDirectiveModel(protection_backend)
        export_model = TargetApiDirectiveModel(HeldExportBackend(fixture_images(64)))

        program = prepare_program(THREAD_SOURCE, PROCESS, bitness=64)
        dry = dry_link_program(program, memory, {},
                               thread_model=thread_model,
                               protection_model=protection_model,
                               export_model=export_model)
        self.assertTrue(dry["dry_run"])
        self.assertFalse(dry["publishable"])
        self.assertEqual(thread_backend.calls, [])
        self.assertEqual(protection_backend.applies, [])

        export = prepare_program(EXPORT_PROC_SOURCE, PROCESS, bitness=64)
        dry_export = dry_link_program(export, memory, {},
                                      export_model=export_model)
        self.assertEqual(dry_export["observations"][0]["op"], "getprocaddress")
        self.assertEqual(dry_export["observations"][0]["address"], 0x711100)

    def test_dry_link_refuses_missing_model_visibly(self):
        memory = Memory()
        program = prepare_program(PROTECT_SOURCE, PROCESS, bitness=64)
        with self.assertRaisesRegex(ProgramError, "protection backend"):
            dry_link_program(program, memory, {})


class DirectiveEngineWiringTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.memory = Memory()
        self.engine = None

    def tearDown(self):
        if self.engine is not None and not self.engine.closed:
            self.engine.close()

    def make_engine(self, source=SIMPLE_SOURCE, name="owned.ct", **kwargs):
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

    def test_default_thread_binding_refuses_before_any_effect(self):
        engine = self.make_engine(THREAD_SOURCE)
        with self.assertRaisesRegex(NativeRuntimeError,
                                    "thread binding was not provided"):
            engine.toggle(1, True)
        self.assertEqual(self.memory.writes, [])
        self.assertNotIn(1, engine.applied)

    def test_injected_thread_backend_round_trips_without_double_spawn(self):
        backend = ScriptedThreadBackend()
        engine = self.make_engine(
            THREAD_SOURCE,
            thread_backend_factory=lambda memory: ThreadDirectiveModel(backend))
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.memory.read(0x1020, 4), b"\x01\x00\x00\x00")
        self.assertEqual(
            [call for call in backend.calls if call[0] == "spawn"],
            [("spawn", 1)])
        self.assertFalse(engine.toggle(1, False))
        self.assertEqual(self.memory.read(0x1020, 4), b"\x00\x00\x00\x00")

    def test_default_protection_binding_refuses_before_any_effect(self):
        engine = self.make_engine(PROTECT_SOURCE)
        with self.assertRaisesRegex(NativeRuntimeError,
                                    "protection binding was not provided"):
            engine.toggle(1, True)
        self.assertEqual(self.memory.writes, [])
        self.assertNotIn(1, engine.applied)

    def test_injected_protection_backend_round_trips(self):
        backend = ScriptedProtectionBackend()
        engine = self.make_engine(
            PROTECT_SOURCE,
            protection_backend_factory=lambda memory:
            ProtectionDirectiveModel(backend))
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(backend.applies, [(0x1000, 0x1000, PAGE_READWRITE)])
        self.assertEqual(self.memory.read(0x1020, 4), b"\x01\x00\x00\x00")
        self.assertFalse(engine.toggle(1, False))
        self.assertEqual(backend.releases, [(0x1000, 0x1000)])
        self.assertEqual(self.memory.read(0x1020, 4), b"\x00\x00\x00\x00")

    def test_export_default_route_uses_linked_memory(self):
        engine = self.make_engine(EXPORT_MODULE_SOURCE)
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.memory.read(0x1020, 4), b"\x01\x00\x00\x00")
        self.assertFalse(engine.toggle(1, False))
        self.assertEqual(self.memory.read(0x1020, 4), b"\x00\x00\x00\x00")

    def test_injected_export_backend_round_trips(self):
        backend = HeldExportBackend(fixture_images(64))
        engine = self.make_engine(
            EXPORT_PROC_SOURCE,
            export_backend_factory=lambda memory:
            TargetApiDirectiveModel(backend))
        self.assertTrue(engine.toggle(1, True))
        self.assertEqual(self.memory.read(0x1020, 4), b"\x01\x00\x00\x00")
        self.assertFalse(engine.toggle(1, False))
        self.assertEqual(self.memory.read(0x1020, 4), b"\x00\x00\x00\x00")

    def test_export_factory_refusal_fails_closed_before_any_effect(self):
        engine = self.make_engine(EXPORT_MODULE_SOURCE,
                                  export_backend_factory=lambda memory: None)
        with self.assertRaisesRegex(NativeRuntimeError,
                                    "export binding was not provided"):
            engine.toggle(1, True)
        self.assertEqual(self.memory.writes, [])
        self.assertNotIn(1, engine.applied)

    def test_factories_not_invoked_without_capability(self):
        thread_calls, protection_calls, export_calls = [], [], []
        engine = self.make_engine(
            SIMPLE_SOURCE,
            thread_backend_factory=lambda memory: thread_calls.append(1),
            protection_backend_factory=lambda memory: protection_calls.append(1),
            export_backend_factory=lambda memory: export_calls.append(1))
        self.assertTrue(engine.toggle(1, True))
        self.assertFalse(engine.toggle(1, False))
        self.assertEqual((thread_calls, protection_calls, export_calls),
                         ([], [], []))


if __name__ == "__main__":
    unittest.main()
