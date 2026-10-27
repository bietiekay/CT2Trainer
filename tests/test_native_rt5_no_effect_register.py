"""RT-5 item F: ratify the no-effect / out-of-scope register as an enforced contract.

Basis: ``documentation/rt5-api-inventory.md`` section 8 ("Scope decision
register", "No-effect / out-of-scope (documented)") as measured on the
lane base ``main`` @ ``b2f20a8`` (2026-10-26).  The register stays an index; the
code is the truth.  Every register family is pinned here with a test that
proves, for an independently authored synthetic fixture:

- the construct loads through the converter without error
  (``compile_table`` succeeds, both plan validators accept the plan),
- it is classified with its EXACT current reason string (byte-stable pin),
- it never influences record/plan state: differential compiles against the
  construct-free base show identical counts, entry states (supported
  flags, reasons, staged/provider/dependency metadata, activation flags),
  blocked-reason maps and warning lists apart from the pinned no-effect
  strings; no register construct appears in any entry block reason.

Families covered (register entry -> pinned code truth):

- CE UI family (inventory section 7.2 "Purely visual UI" minus
  ``messageDialog``, which is decision item E; 26 global APIs including
  the uppercase ``GetAddressList`` and the legacy timer helpers
  ``timer_onTimer``/``timer_setEnabled``/``timer_setInterval``) plus
  ``playSound``: runtime named refusal ``Unsupported CE Lua API: <name>``
  at the Lua host (``lua_host.py``); a table Lua that calls them loads
  and the static plan is byte-for-byte unaffected apart from the two
  generic table-Lua warnings.
- 18-object-method register entry (section 7.3): pinned per surface.  The
  WP-56 inert menu/form proxy accepts and discards
  hide/Hide/show/Show/getBitmap/setSize/SendToBack/draw/getCanvas/
  setBevelOuter/addElement/loadFromStream/LoadFromStream/Destroy with no
  target side effect; the typed proxies refuse the rest by name:
  addresslist (getMemoryRecord, disableAllWithoutExecute ->
  "Unsupported addresslist property: <name>"), memory scan
  (setOnlyOneResult, getOnlyResult -> "Unsupported memory scan property:
  <name>"), stringlist file access (loadFromFile, saveToFile ->
  "String list file access is outside this profile").  The structure
  methods (addToGlobalStructureList, removeFromGlobalStructureList,
  getElementByOffset, getReferencedStrings) have no host object in
  CT2Trainer: ``createStructure`` itself is one of the 26 named
  refusals, so they are unreachable.
- ``Forms`` (incl. Ascii85 ``CETrainer`` TTrainerForm, ``IconList``,
  ``UDF1``): "Embedded CE forms are present; check UI conflicts." +
  "Table-level sections not interpreted: Forms." +
  ``ignored_sections`` entry.
- ``Signature``/``SignedHash``/``PublicKey`` (integrity metadata):
  "Table-level sections not interpreted: PublicKey, Signature,
  SignedHash." (sorted).
- ``LastState`` incl. the ``RealAddress`` attribute (CE-side persistence;
  CT2Trainer keeps its own state model): silently ignored, zero warnings.
- ``ActivateSound``/``DeactivateSound`` hotkey children (decorative
  toggle sound): silently ignored by the hotkey parser.
- Embedded images + ``License.txt`` (``<Files>`` section with
  file-named children): "Table-level sections not interpreted: Files."
- ``Color``/``GroupHeader``/``Comments``/``DisassemblerComments``
  presentation: no warning; a plain ``GroupHeader`` pins as supported
  heading with reason "Navigation heading; CE group activation is not
  executed."
- Unreferenced ``Structures`` section (16 corpus tables, 0 referring
  records): "Table-level sections not interpreted: Structures." +
  ``ignored_sections`` entry.
- ``usemono()`` AA directive (newer-CE register entry; RT-4.5/O15): the
  record is blocked with the exact composite reason
  "usemono targets a Cheat Engine newer than 7.5; out of parity scope.
  Native assembly: Line 2: usemono targets a Cheat Engine newer than
  7.5; out of parity scope." (static bounded check + native assembly
  path name the identical refusal; the line number counts the
  LF-separated fixture script); every other record stays byte
  identical.

Word register wording normalized against the code (report-level):

- Section 7.2's heading reads "Purely visual UI (27)"; the list holds
  26 names after the ``messageDialog`` decision (item E) is carved out,
  matching section 8's "26 global APIs".
- Section 7.3's "18 object methods" lists 24 raw names (19
  casefold-unique); the per-surface pins above are the code truth.
- ``playSound`` / the legacy timer helpers / uppercase
  ``GetAddressList`` are named both inside the 26-global sweep and as
  separate register items; each is pinned once, in the sweep.

Excluded by lane contract: ``messageDialog`` (decision item E, parallel
lane) and the O22 ``createThread``/``threadWait`` gate pins (item G,
parallel lane).
"""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from ct2trainer.native.compiler import compile_table, validate_plan
from ct2trainer.native.converter import MISSING_LUA_API_PREFIX
from ct2trainer.native.engine import validate_plan as engine_validate_plan
from ct2trainer.native.lua_host import EngineLuaBroker, LuaHost, LuaHostError
from ct2trainer.table import read_table

try:
    import lupa.lua53  # noqa: F401
    _LUPA = True
except ImportError:
    _LUPA = False

PROCESS = "FixtureTarget.exe"

# The 26 no-effect CE UI globals (inventory section 7.2 minus messageDialog):
# purely visual UI, legacy timer helpers, uppercase GetAddressList, playSound.
CE_UI_GLOBALS = (
    "control_setVisible", "wincontrol_getControl", "getMemoryViewForm",
    "getStructureCount", "getStructure", "createButton", "createPanel",
    "createForm", "createFont", "createLabel", "component_getComponent",
    "createPicture", "createStructure", "enumStructureForms",
    "setMethodProperty", "menu_getItems", "createCheckBox",
    "createComponentClass", "createOpenDialog", "createStructureForm",
    "createImage", "GetAddressList", "timer_onTimer", "timer_setEnabled",
    "timer_setInterval", "playSound",
)
assert len(CE_UI_GLOBALS) == 26

# WP-56 inert menu/form proxy surface: the register's object methods that
# land on inert objects are accepted and discarded (no effect, no refusal).
INERT_MENU_METHODS = (
    "hide", "Hide", "show", "Show", "getBitmap", "setSize", "SendToBack",
    "draw", "getCanvas", "setBevelOuter", "addElement", "loadFromStream",
    "LoadFromStream", "Destroy",
)

# Register terms that must never appear in any entry block reason.
NO_EFFECT_TERMS = (
    "Structures", "Signature", "SignedHash", "PublicKey", "Forms", "Files",
    "LastState", "RealAddress", "ActivateSound", "DeactivateSound",
)

BASE_RECORD = """    <CheatEntry>
      <ID>0</ID>
      <Description>"baseline supported value"</Description>
      <VariableType>4 Bytes</VariableType>
      <Address>fixturetarget.exe+40</Address>
      <Value>0</Value>
    </CheatEntry>
"""


def _header(body: str, sections: str = "") -> str:
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<CheatTable CheatEngineTableVersion="45">\n'
            "  <CheatEntries>\n" + body + "\n  </CheatEntries>\n"
            + sections + "</CheatTable>\n")


BASE_CT = _header(BASE_RECORD)

STRUCTURES_SECTION = """  <Structures StructVersion="2">
    <Structure Name="sPlayer" AutoFill="0" AutoCreate="1" DefaultHex="0" AutoDestroy="0" DoNotSaveLocal="0" RLECompression="1" AutoCreateStructsize="4096">
      <Elements>
        <Element Offset="0" Vartype="Pointer" Bytesize="4" OffsetHex="00000000" DisplayMethod="Unsigned Integer"/>
        <Element Offset="8" Vartype="4 Bytes" Bytesize="4" OffsetHex="00000008" DisplayMethod="Unsigned Integer"/>
      </Elements>
    </Structure>
  </Structures>
"""

INTEGRITY_SECTIONS = """  <Signature>ABCD1234EF56</Signature>
  <SignedHash>7890ABCD</SignedHash>
  <PublicKey>0123456789ABCDEF</PublicKey>
"""

FORMS_CETRAINER_SECTION = """  <Forms>
    <CETrainer Class="TTrainerForm" Encoding="Ascii85">=Nz}!,cprTrP</CETrainer>
  </Forms>
"""

FORMS_ICONLIST_UDF_SECTION = """  <Forms>
    <IconList Encoding="Ascii85">abcDEF123</IconList>
    <UDF1 Encoding="Ascii85">xyzGHI456</UDF1>
  </Forms>
"""

FILES_SECTION = """  <Files>
    <OCTfooterlogo.png Encoding="Ascii85">Em^R!8[m-WQYgg</OCTfooterlogo.png>
    <License.txt>fixture license text</License.txt>
  </Files>
"""

PRESENTATION_RECORD = """    <CheatEntry>
      <ID>0</ID>
      <Description>"baseline supported value"</Description>
      <Color>0075EA</Color>
      <VariableType>4 Bytes</VariableType>
      <Address>fixturetarget.exe+40</Address>
      <LastState Value="0000000040000000" RealAddress="1A085C56D80"/>
      <Comments>presentation comment text</Comments>
      <DisassemblerComments>presentation disassembly comment</DisassemblerComments>
      <Value>0</Value>
    </CheatEntry>
"""

PLAIN_HEADING_CT = _header(BASE_RECORD + """    <CheatEntry>
      <ID>1</ID>
      <Description>"plain navigation heading"</Description>
      <GroupHeader>1</GroupHeader>
    </CheatEntry>
""")

HOTKEY_SOUND_RECORD = """    <CheatEntry>
      <ID>0</ID>
      <Description>"hotkey value with sounds"</Description>
      <VariableType>4 Bytes</VariableType>
      <Address>fixturetarget.exe+40</Address>
      <Hotkeys>
        <Hotkey>
          <Action>Activate</Action>
          <Keys>
            <Key>32</Key>
          </Keys>
          <ID>0</ID>
          <ActivateSound>Activate</ActivateSound>
          <DeactivateSound>Deactivate</DeactivateSound>
        </Hotkey>
      </Hotkeys>
      <Value>0</Value>
    </CheatEntry>
"""

HOTKEY_PLAIN_RECORD = """    <CheatEntry>
      <ID>0</ID>
      <Description>"hotkey value with sounds"</Description>
      <VariableType>4 Bytes</VariableType>
      <Address>fixturetarget.exe+40</Address>
      <Hotkeys>
        <Hotkey>
          <Action>Activate</Action>
          <Keys>
            <Key>32</Key>
          </Keys>
          <ID>0</ID>
        </Hotkey>
      </Hotkeys>
      <Value>0</Value>
    </CheatEntry>
"""

USEMONO_CT = _header("""    <CheatEntry>
      <ID>0</ID>
      <Description>"usemono script record"</Description>
      <VariableType>Auto Assembler Script</VariableType>
      <AssemblerScript>[ENABLE]
usemono()
[DISABLE]
</AssemblerScript>
    </CheatEntry>
""" + BASE_RECORD.replace("<ID>0</ID>", "<ID>1</ID>"), "")

# One table carrying a sample of every table-level register family
# (the launch-spec synthetic case).  Record ids are unique: the
# presentation value record is id 0, the plain heading id 1, the hotkey
# record id 2.
COMBINED_CT = _header(
    PRESENTATION_RECORD + """    <CheatEntry>
      <ID>1</ID>
      <Description>"plain navigation heading"</Description>
      <GroupHeader>1</GroupHeader>
    </CheatEntry>
""" + HOTKEY_SOUND_RECORD.replace("<ID>0</ID>", "<ID>2</ID>", 1),
    STRUCTURES_SECTION + INTEGRITY_SECTIONS + FORMS_CETRAINER_SECTION
    + FILES_SECTION)

# Control variant of the combined table: identical records, none of the
# register constructs.
COMBINED_CONTROL_CT = _header(
    BASE_RECORD + """    <CheatEntry>
      <ID>1</ID>
      <Description>"plain navigation heading"</Description>
      <GroupHeader>1</GroupHeader>
    </CheatEntry>
""" + HOTKEY_PLAIN_RECORD.replace("<ID>0</ID>", "<ID>2</ID>", 1))

COMBINED_EXTRA_WARNINGS = [
    "Embedded CE forms are present; check UI conflicts.",
    "Table-level sections not interpreted: Files, Forms, PublicKey, "
    "Signature, SignedHash, Structures.",
]

# Table Lua calling a spread of register APIs; every call is individually
# refused at activation time, the surrounding Lua keeps running.
TABLE_LUA_UI_CT = _header(BASE_RECORD, """  <LuaScript>local refs={}
for _,api in ipairs({getMemoryViewForm, control_setVisible, playSound, GetAddressList, timer_setInterval, createButton, getStructureCount, createStructure}) do
  local ok,err=pcall(function() return api() end)
  table.insert(refs, ok and "ok" or tostring(err))
end
print(table.concat(refs,"|"))</LuaScript>
""")

TABLE_LUA_EXPECTED_WARNINGS = [
    "Table Lua can run when Cheat Engine loads the table.",
    "Table Lua is not executed on load. Read-only helpers replay in each "
    "Lua activation; top-level writes, callbacks and unsupported APIs "
    "block activation.",
]


def _write(directory: Path, name: str, body: str) -> Path:
    path = directory / name
    path.write_text(body, encoding="utf-8")
    return path


def _compile(directory: Path, name: str, body: str) -> dict:
    plan = compile_table(_write(directory, name, body), PROCESS)
    validate_plan(plan)
    engine_validate_plan(plan)
    return plan


def _entry_states(plan: dict) -> list[dict]:
    """Per-entry state without the identity fields (id/label/path)."""
    return [
        {key: value for key, value in entry.items()
         if key not in ("id", "label", "path")}
        for entry in plan["entries"]
    ]


def _assert_plan_inert(testcase: unittest.TestCase, plan_with: dict,
                       plan_without: dict, extra_warnings: list[str] = (),
                       extra_ignored: list[str] = ()) -> None:
    """The construct adds no record/plan state beyond the pinned strings."""
    testcase.assertEqual(plan_with["counts"], plan_without["counts"])
    testcase.assertEqual(plan_with["blocked_reasons"],
                         plan_without["blocked_reasons"])
    testcase.assertEqual(len(plan_with["entries"]),
                         len(plan_without["entries"]))
    testcase.assertEqual(_entry_states(plan_with), _entry_states(plan_without))
    testcase.assertEqual(plan_with["warnings"],
                         list(extra_warnings) + list(plan_without["warnings"]))
    testcase.assertEqual(plan_with["ignored_sections"],
                         list(plan_without.get("ignored_sections", ()))
                         + sorted(extra_ignored))


def _assert_no_term_in_any_reason(plan: dict, terms: tuple[str, ...]) -> None:
    for entry in plan["entries"]:
        reason = entry.get("reason", "")
        for term in terms:
            assert term not in reason, \
                f"register term {term!r} leaked into entry {entry['id']} reason: {reason!r}"
    for reason in plan.get("blocked_reasons", {}):
        for term in terms:
            assert term not in reason, \
                f"register term {term!r} leaked into blocked reason: {reason!r}"


def _recording_memory():
    class _Mem:
        identity = (123, 456)
        pointer_size = 8
        pid = 4242
        process_handle = 0x11121314

        def __init__(self):
            self.ops = []

        def _range(self, address, size):
            self.ops.append(('range', address, size))

        def read(self, address, size):
            self.ops.append(('read', address, size))
            return b'\x00' * size

        def write(self, address, data):
            self.ops.append(('write', address, bytes(data)))
            return True

    return _Mem()


def _host() -> tuple:
    memory = _recording_memory()
    engine = SimpleNamespace(memory=memory, plan={'process_name': PROCESS},
                             symbols={}, _guard=lambda: None)
    return memory, EngineLuaBroker(engine, input_handler=object())


# ---------------------------------------------------------------------------
# Table-level no-effect constructs (converter/plan level)
# ---------------------------------------------------------------------------

class StructuresNoEffectTests(unittest.TestCase):
    """Unreferenced <Structures> section: warning only, plan untouched."""

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.directory = Path(self._temp.name)

    def test_structures_section_warns_and_is_inert(self):
        base = _compile(self.directory, "base.ct", BASE_CT)
        plan = _compile(self.directory, "structures.ct",
                        _header(BASE_RECORD, STRUCTURES_SECTION))
        # Exact pinned warning (byte-stable) and ignored-section census.
        self.assertEqual(plan["warnings"],
                         ["Table-level sections not interpreted: Structures."])
        self.assertEqual(plan["ignored_sections"], ["Structures"])
        # No plan state beyond the pinned warning: counts, entry states,
        # blocked-reason map and ignored sections apart from "Structures".
        _assert_plan_inert(self, plan, base,
                           extra_warnings=["Table-level sections not interpreted: Structures."],
                           extra_ignored=["Structures"])
        _assert_no_term_in_any_reason(plan, ("Structures", "sPlayer"))
        entry = plan["entries"][0]
        self.assertTrue(entry["supported"])
        self.assertEqual(entry["reason"], "")
        self.assertIsNone(entry.get("staged"))
        self.assertEqual(entry["dependency_ids"], [])
        self.assertEqual(entry["provides"], [])
        self.assertEqual(plan["counts"]["blocked"], 0)


class IntegrityMetadataNoEffectTests(unittest.TestCase):
    """Signature/SignedHash/PublicKey: author integrity metadata, no role."""

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.directory = Path(self._temp.name)

    def test_integrity_sections_warn_sorted_and_are_inert(self):
        base = _compile(self.directory, "base.ct", BASE_CT)
        plan = _compile(self.directory, "integrity.ct",
                        _header(BASE_RECORD, INTEGRITY_SECTIONS))
        self.assertEqual(plan["warnings"],
                         ["Table-level sections not interpreted: "
                          "PublicKey, Signature, SignedHash."])
        self.assertEqual(plan["ignored_sections"],
                         ["PublicKey", "Signature", "SignedHash"])
        _assert_plan_inert(self, plan, base,
                           extra_warnings=["Table-level sections not interpreted: "
                                           "PublicKey, Signature, SignedHash."],
                           extra_ignored=["PublicKey", "Signature", "SignedHash"])
        _assert_no_term_in_any_reason(plan, ("Signature", "SignedHash", "PublicKey"))
        self.assertTrue(plan["entries"][0]["supported"])
        self.assertEqual(plan["entries"][0]["reason"], "")
        self.assertEqual(plan["counts"]["blocked"], 0)


class FormsNoEffectTests(unittest.TestCase):
    """Embedded CE forms (CETrainer/IconList/UDF1): out of scope, warned."""

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.directory = Path(self._temp.name)

    def _assert_forms_plan(self, body, name):
        base = _compile(self.directory, "base.ct", BASE_CT)
        plan = _compile(self.directory, name, _header(BASE_RECORD, body))
        # Both pinned warnings, in plan order: table-level forms warning
        # first (read_table), then the omitted-section census warning.
        self.assertEqual(plan["warnings"], [
            "Embedded CE forms are present; check UI conflicts.",
            "Table-level sections not interpreted: Forms.",
        ])
        self.assertEqual(plan["ignored_sections"], ["Forms"])
        _assert_plan_inert(
            self, plan, base,
            extra_warnings=["Embedded CE forms are present; check UI conflicts.",
                            "Table-level sections not interpreted: Forms."],
            extra_ignored=["Forms"])
        _assert_no_term_in_any_reason(plan, ("Forms",))
        self.assertTrue(plan["entries"][0]["supported"])
        self.assertEqual(plan["entries"][0]["reason"], "")
        self.assertEqual(plan["counts"]["blocked"], 0)
        # The table reader flags the section itself.
        table = read_table(_write(self.directory, name + ".read.ct",
                                  _header(BASE_RECORD, body)))
        self.assertTrue(table.has_forms)

    def test_forms_cetrainer_ascii85_ttrainerform_warns_and_is_inert(self):
        self._assert_forms_plan(FORMS_CETRAINER_SECTION, "forms_cetrainer.ct")

    def test_forms_iconlist_and_udf1_warn_and_are_inert(self):
        self._assert_forms_plan(FORMS_ICONLIST_UDF_SECTION, "forms_iconlist.ct")


class EmbeddedFilesNoEffectTests(unittest.TestCase):
    """Embedded images + License.txt (<Files> section): warning only."""

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.directory = Path(self._temp.name)

    def test_embedded_files_section_warns_and_is_inert(self):
        base = _compile(self.directory, "base.ct", BASE_CT)
        plan = _compile(self.directory, "files.ct",
                        _header(BASE_RECORD, FILES_SECTION))
        self.assertEqual(plan["warnings"],
                         ["Table-level sections not interpreted: Files."])
        self.assertEqual(plan["ignored_sections"], ["Files"])
        _assert_plan_inert(self, plan, base,
                           extra_warnings=["Table-level sections not interpreted: Files."],
                           extra_ignored=["Files"])
        _assert_no_term_in_any_reason(plan, ("Files", "License"))
        self.assertTrue(plan["entries"][0]["supported"])
        self.assertEqual(plan["entries"][0]["reason"], "")
        self.assertEqual(plan["counts"]["blocked"], 0)


class PresentationAttributesNoEffectTests(unittest.TestCase):
    """Color/Comments/DisassemblerComments/LastState/RealAddress: silent."""

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.directory = Path(self._temp.name)

    def test_presentation_elements_are_silent_and_inert(self):
        base = _compile(self.directory, "base.ct", BASE_CT)
        plan = _compile(self.directory, "presentation.ct",
                        _header(PRESENTATION_RECORD))
        # No warning at all: presentation elements are read nowhere.
        self.assertEqual(plan["warnings"], [])
        self.assertEqual(plan["ignored_sections"], [])
        _assert_plan_inert(self, plan, base)
        _assert_no_term_in_any_reason(plan, NO_EFFECT_TERMS)
        entry = plan["entries"][0]
        self.assertTrue(entry["supported"])
        self.assertEqual(entry["reason"], "")
        self.assertEqual(entry["source_address"], "fixturetarget.exe+40")

    def test_plain_group_header_pins_the_heading_reason(self):
        plan = _compile(self.directory, "heading.ct", PLAIN_HEADING_CT)
        self.assertEqual(plan["warnings"], [])
        heading = plan["entries"][1]
        self.assertEqual(heading["kind"], "heading")
        self.assertTrue(heading["supported"])
        self.assertEqual(
            heading["reason"],
            "Navigation heading; CE group activation is not executed.")
        self.assertIsNone(heading.get("parent_activation"))
        self.assertEqual(plan["counts"],
                         {"total": 2, "supported": 2, "actionable": 1,
                          "blocked": 0, "headings": 1})
        self.assertEqual(plan["blocked_reasons"], {})


class HotkeySoundNoEffectTests(unittest.TestCase):
    """ActivateSound/DeactivateSound hotkey children: parser ignores them."""

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.directory = Path(self._temp.name)

    def test_activate_deactivate_sound_children_are_ignored(self):
        plain = _compile(self.directory, "hotkey_plain.ct",
                         _header(HOTKEY_PLAIN_RECORD))
        plan = _compile(self.directory, "hotkey_sound.ct",
                        _header(HOTKEY_SOUND_RECORD))
        # The sound children change nothing: identical entry states (hotkey
        # keys/action parsed the same way), identical warning (the per-case
        # hotkey note), identical counts and blocked-reason map.
        _assert_plan_inert(self, plan, plain)
        _assert_no_term_in_any_reason(plan, ("ActivateSound", "DeactivateSound"))
        hotkeys = plan["entries"][0]["hotkeys"]
        self.assertEqual(hotkeys, [
            {"action": "Activate", "active": True, "description": "",
             "keys": [32], "value": ""}])
        self.assertEqual(plan["entries"][0]["source_hotkey_count"], 1)


class CombinedRatificationTableTests(unittest.TestCase):
    """One table carrying a sample of every table-level register family."""

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.directory = Path(self._temp.name)

    def test_combined_table_pins_the_full_register_warning_set(self):
        plan = _compile(self.directory, "combined.ct", COMBINED_CT)
        # Byte-stable full warning list: forms warning (table reader),
        # single omitted-section census line (sorted names), then the
        # per-case hotkey note in record order.
        self.assertEqual(plan["warnings"], [
            "Embedded CE forms are present; check UI conflicts.",
            "Table-level sections not interpreted: Files, Forms, PublicKey, "
            "Signature, SignedHash, Structures.",
            "Record 2 ('hotkey value with sounds'): hotkey SPACE (Activate) "
            "not registered: record has no activation action.",
        ])
        self.assertEqual(plan["ignored_sections"],
                         ["Files", "Forms", "PublicKey", "Signature",
                          "SignedHash", "Structures"])
        self.assertEqual(plan["counts"],
                         {"total": 3, "supported": 3, "actionable": 2,
                          "blocked": 0, "headings": 1})
        self.assertEqual(plan["blocked_reasons"], {})
        by_id = {entry["id"]: entry for entry in plan["entries"]}
        self.assertTrue(by_id[0]["supported"])
        self.assertEqual(by_id[0]["reason"], "")
        self.assertEqual(by_id[1]["kind"], "heading")
        self.assertEqual(by_id[1]["reason"],
                         "Navigation heading; CE group activation is not executed.")
        self.assertEqual(by_id[2]["hotkeys"], [
            {"action": "Activate", "active": True, "description": "",
             "keys": [32], "value": ""}])

    def test_combined_table_plan_state_is_independent_of_the_registers(self):
        control = _compile(self.directory, "combined_control.ct",
                           COMBINED_CONTROL_CT)
        plan = _compile(self.directory, "combined.ct", COMBINED_CT)
        # Same records, no register construct in any reason: apart from the
        # two pinned register warnings the plans are state-identical.
        _assert_plan_inert(self, plan, control,
                           extra_warnings=list(COMBINED_EXTRA_WARNINGS),
                           extra_ignored=["Files", "Forms", "PublicKey",
                                          "Signature", "SignedHash",
                                          "Structures"])
        _assert_no_term_in_any_reason(plan, NO_EFFECT_TERMS)


class NoEffectEngineRuntimeTests(unittest.TestCase):
    """Positive end-to-end: constructs present, the effect path still works."""

    def setUp(self):
        from test_native_engine_code import Coordinator
        from test_native_lua_activation import Memory
        self.directory = Path(tempfile.mkdtemp(prefix="ct2-rt5f-"))
        self.addCleanup(shutil.rmtree, self.directory, ignore_errors=True)
        self.table = self.directory / "combined.ct"
        self.table.write_text(COMBINED_CT, encoding="utf-8")
        self.memory = Memory()
        self.coordinator = Coordinator()
        self.engine = None

    def test_combined_table_attaches_and_writes_byte_exact(self):
        from ct2trainer.native.engine import TrainerEngine
        self.engine = TrainerEngine(
            compile_table(self.table, PROCESS),
            state_dir=self.directory / "state",
            process_lock_dir=self.directory / "shared",
            memory_factory=lambda name: self.memory,
            hook_coordinator=self.coordinator)
        self.engine.poll()
        # No record blocked by any register construct: the plan attached
        # cleanly and the effect path is live.
        self.assertFalse(self.engine.blocked, self.engine.error)
        # The supported baseline value record (id 0, fixturetarget.exe+40)
        # still writes its own 4 bytes exactly despite every no-effect
        # construct being present in the table.
        self.assertEqual(self.engine.set_value(0, "255"), "255")
        self.assertEqual(self.memory.read(0x1040, 4), b"\xff\x00\x00\x00")
        self.assertEqual(self.engine.read_value(0), "255")
        self.assertEqual(len(self.memory.writes), 1)
        address, data = self.memory.writes[0]
        self.assertEqual(address, 0x1040)
        self.assertEqual(data, b"\xff\x00\x00\x00")
        # Frozen restore roundtrip on the same record: tamper, poll, restore.
        self.assertTrue(self.engine.set_freeze(0, True))
        self.memory.data[0x40] = 0x01
        self.engine.poll()
        self.assertFalse(self.engine.blocked, self.engine.error)
        self.assertEqual(self.memory.read(0x1040, 4), b"\xff\x00\x00\x00")

    def tearDown(self):
        if self.engine is not None:
            self.memory.alive = False
            self.engine.poll()
            self.engine.close()


# ---------------------------------------------------------------------------
# Runtime named refusals (host level)
# ---------------------------------------------------------------------------

class CeUiGlobalRefusalTests(unittest.TestCase):
    """The 26 CE UI globals keep the exact named refusal (refusal stays)."""

    def setUp(self):
        if not _LUPA:
            self.skipTest("pinned MIT Lupa Lua53 dependency is not installed")
        self.memory, broker = _host()
        self.host = LuaHost(broker)

    def tearDown(self):
        self.host.cancel()

    def test_all_26_ce_ui_globals_keep_the_exact_named_refusal(self):
        for name in CE_UI_GLOBALS:
            with self.subTest(api=name):
                with self.assertRaises(LuaHostError) as ctx:
                    self.host.execute("return " + name + "()")
                self.assertEqual(str(ctx.exception),
                                 "Unsupported CE Lua API: " + name)
        # No target/engine side effect from any of the refused calls.
        self.assertEqual(self.memory.ops, [])

    def test_hosted_lower_case_getAddressList_contrasts_with_uppercase(self):
        # CE 7.5 registers both casings (first-character case-flipped
        # lua_register wrapper, LuaHandler.pas:213-228); the host
        # registers only lowercase, so the uppercase call stays a
        # named refusal.
        self.assertIsNotNone(self.host.execute("return getAddressList()"))
        with self.assertRaises(LuaHostError) as ctx:
            self.host.execute("return GetAddressList()")
        self.assertEqual(str(ctx.exception),
                         "Unsupported CE Lua API: GetAddressList")
        self.assertEqual(self.memory.ops, [])

    def test_missing_lua_api_prefix_constant_is_byte_stable(self):
        self.assertEqual(MISSING_LUA_API_PREFIX, "Unsupported CE Lua API: ")


class TableLuaPlanUnaffectedTests(unittest.TestCase):
    """Table Lua calling register APIs loads; the static plan is untouched."""

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.directory = Path(self._temp.name)

    def test_table_lua_calling_register_apis_leaves_the_static_plan_untouched(self):
        base = _compile(self.directory, "base.ct", BASE_CT)
        plan = _compile(self.directory, "table_lua_ui.ct", TABLE_LUA_UI_CT)
        # Refusals happen at activation time, not at compile time: the plan
        # differs from the construct-free base only by the two generic
        # table-Lua warnings; every entry stays supported.
        _assert_plan_inert(self, plan, base,
                           extra_warnings=list(TABLE_LUA_EXPECTED_WARNINGS))
        for entry in plan["entries"]:
            self.assertTrue(entry["supported"])
            self.assertEqual(entry["reason"], "")
        for name in CE_UI_GLOBALS:
            _assert_no_term_in_any_reason(plan, (name,))

    def test_table_lua_bootstrap_continues_across_the_exact_refusals(self):
        if not _LUPA:
            self.skipTest("pinned MIT Lupa Lua53 dependency is not installed")
        memory, broker = _host()
        host = LuaHost(broker)
        try:
            # Every register API is refused with its exact byte-stable
            # string (level-0 error: no Lua position prefix).  The refusal
            # is the bootstrap's nil-call detection, so the refused call
            # aborts that activation; the Lua state written before the
            # refusal and the host itself keep working.
            for name in ("getMemoryViewForm", "control_setVisible",
                         "playSound", "GetAddressList", "timer_setInterval",
                         "createButton", "getStructureCount",
                         "createStructure"):
                with self.subTest(api=name):
                    with self.assertRaises(LuaHostError) as ctx:
                        host.execute(
                            "rt5f_marker = '" + name + "'\n"
                            "return " + name + "()")
                    self.assertEqual(str(ctx.exception),
                                     "Unsupported CE Lua API: " + name)
            # The host continues across the refusals: the pre-refusal
            # global survives and follow-up activations run normally.
            self.assertEqual(host.execute("return rt5f_marker"),
                             "createStructure")
            self.assertEqual(host.execute("return 40 + 2"), 42)
            # No target side effect from any of the refused calls.
            self.assertEqual(memory.ops, [])
        finally:
            host.cancel()


class ObjectMethodRefusalTests(unittest.TestCase):
    """The register's object methods, pinned per surface (section 7.3)."""

    def setUp(self):
        if not _LUPA:
            self.skipTest("pinned MIT Lupa Lua53 dependency is not installed")
        self.memory, broker = _host()
        self.host = LuaHost(broker)

    def tearDown(self):
        self.host.cancel()

    def test_inert_menu_surface_methods_are_accepted_and_discarded(self):
        # WP-56 inert proxy: these register methods run to completion
        # against the inert object and are discarded - no target effect.
        for method in INERT_MENU_METHODS:
            with self.subTest(method=method):
                self.assertTrue(self.host.execute(
                    "local obj=getMainForm()\n"
                    "local r=obj:" + method + "()\n"
                    "return r ~= nil"))
        self.assertEqual(self.memory.ops, [])

    def test_addresslist_ui_methods_are_named_refusals(self):
        for method in ("getMemoryRecord", "disableAllWithoutExecute"):
            with self.subTest(method=method):
                with self.assertRaisesRegex(
                        LuaHostError,
                        "Unsupported addresslist property: " + method):
                    self.host.execute(
                        "local l=getAddressList()\n"
                        "local r=l:" + method + "(1)")
        self.assertEqual(self.memory.ops, [])

    def test_memory_scan_ui_methods_are_named_refusals(self):
        for method in ("setOnlyOneResult", "getOnlyResult"):
            with self.subTest(method=method):
                with self.assertRaisesRegex(
                        LuaHostError,
                        "Unsupported memory scan property: " + method):
                    self.host.execute(
                        "local m=createMemScan()\n"
                        "m:" + method + "(true)")
        self.assertEqual(self.memory.ops, [])

    def test_stringlist_file_access_is_outside_the_profile(self):
        for method in ("loadFromFile", "saveToFile"):
            with self.subTest(method=method):
                with self.assertRaisesRegex(
                        LuaHostError,
                        "String list file access is outside this profile"):
                    self.host.execute(
                        "local s=createStringList()\n"
                        "s:" + method + '("fixture.txt")')
        self.assertEqual(self.memory.ops, [])

    def test_structure_host_objects_are_unreachable(self):
        # The structure methods (addToGlobalStructureList,
        # removeFromGlobalStructureList, getElementByOffset,
        # getReferencedStrings) need a TStructure host object; the
        # constructor is itself one of the 26 named refusals, so the
        # methods can never be reached in the CT2Trainer host.
        with self.assertRaises(LuaHostError) as ctx:
            self.host.execute("return createStructure()")
        self.assertEqual(str(ctx.exception),
                         "Unsupported CE Lua API: createStructure")
        self.assertEqual(self.memory.ops, [])


class UsemonoRefusalTests(unittest.TestCase):
    """usemono(): the newer-CE register entry; named AA refusal, record only."""

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.directory = Path(self._temp.name)

    def test_usemono_record_is_blocked_with_the_exact_composite_reason(self):
        base = _compile(self.directory, "base.ct", BASE_CT)
        plan = _compile(self.directory, "usemono.ct", USEMONO_CT)
        entry = plan["entries"][0]
        self.assertFalse(entry["supported"])
        self.assertEqual(
            entry["reason"],
            "usemono targets a Cheat Engine newer than 7.5; out of parity "
            "scope. Native assembly: Line 2: usemono targets a Cheat Engine "
            "newer than 7.5; out of parity scope.")
        self.assertEqual(set(plan["blocked_reasons"]), {entry["reason"]})
        self.assertEqual(plan["counts"],
                         {"total": 2, "supported": 1, "actionable": 1,
                          "blocked": 1, "headings": 0})
        # Every other record stays byte-identical to the construct-free
        # plan: the construct influences no other record/plan state.
        self.assertEqual(_entry_states(plan)[1], _entry_states(base)[0])
        self.assertEqual(plan["entries"][1]["supported"], True)
        self.assertEqual(plan["entries"][1]["reason"], "")


if __name__ == "__main__":
    unittest.main()
