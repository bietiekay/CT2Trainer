"""WP-28 per-program positional label scoping (CE label semantics),
refined two-stage resolution.

A bare positional label ("return:") is local to its own program at the
prepare level: it binds to the program's own patch position, is exposed
via ``positional_labels``, and does not enter the program's ``requires``.
The table compiler applies the second stage: a table-wide registered
symbol of the same name wins over the local label definition, so the
label is re-declared as an external requirement whenever another
supported record provides the symbol, and the consumer stages behind
that provider.  With no such provider, two records may freely share one
positional label name; declared ``label()`` locality is unchanged.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from xml.sax.saxutils import escape

from ct2trainer.native.aa_program import ProgramError, link_program, prepare_program
from ct2trainer.native.assembler import NasmAssembler
from ct2trainer.native.compiler import compile_table


def hook_script(anchor: str, cave: str, pattern: str, register_return: bool = False) -> str:
    """AOB injection with the classic cave + positional ``return:`` trampoline.

    When *register_return* is True the positional label is also exported
    via registersymbol (single-program link tests); otherwise it stays
    purely local (table-level isolation tests).
    """
    reg = f"registersymbol({anchor}, return)" if register_return else f"registersymbol({anchor})"
    unreg = f"unregistersymbol({anchor}, return)" if register_return else f"unregistersymbol({anchor})"
    return (
        "[ENABLE]\n"
        f"aobscanmodule({anchor},Target.exe,{pattern})\n"
        f"alloc({cave},100,{anchor})\n"
        f"{cave}:\n"
        "mov eax,1\n"
        "jmp return\n"
        f"{anchor}:\n"
        f"jmp {cave}\n"
        "return:\n"
        f"{reg}\n"
        "[DISABLE]\n"
        f"{anchor}:\n"
        f"db {pattern}\n"
        f"{unreg}\n"
        f"dealloc({cave})\n"
    )


# Table-level fixtures: positional label NOT registered (avoids provider
# ambiguity when two records share the name "return").
HOOK_A = hook_script("AnchorA", "caveA", "54 46")
HOOK_B = hook_script("AnchorB", "caveB", "57 47")

# Link-level fixtures: positional label IS registered so exports can be
# verified (single program, no cross-record collision).
HOOK_A_LINK = hook_script("AnchorA", "caveA", "54 46", register_return=True)
HOOK_B_LINK = hook_script("AnchorB", "caveB", "57 47", register_return=True)


def _table_path(*bodies: str, values: tuple[tuple[int, str], ...] = ()) -> Path:
    directory = Path(tempfile.mkdtemp(prefix="ct2trainer-label-scoping-"))
    entries = "".join(
        f'<CheatEntry><ID>{index}</ID><Description>R{index}</Description>'
        '<VariableType>Auto Assembler Script</VariableType>'
        f"<AssemblerScript>{escape(script)}</AssemblerScript></CheatEntry>"
        for index, script in enumerate(bodies, start=10)
    )
    entries += "".join(
        f'<CheatEntry><ID>{entry_id}</ID><Description>V{entry_id}</Description>'
        '<VariableType>4 Bytes</VariableType>'
        f"<Address>{address}</Address></CheatEntry>"
        for entry_id, address in values
    )
    path = directory / "sample.CT"
    path.write_text(
        '<CheatTable CheatEngineTableVersion="52"><CheatEntries>'
        + entries
        + "</CheatEntries></CheatTable>",
        encoding="utf-8",
    )
    return path


class ScopingMemory:
    def __init__(self, scan_address: int = 0x140001000):
        self.scan_address = scan_address
        self.data = {}
        self.scans = []

    def read(self, address, size):
        return bytes(self.data.get(address + index, 0) for index in range(size))

    def module(self, name):
        if name.casefold() != "target.exe":
            raise ValueError("Unknown module")
        return 0x140000000, 0x100000

    def scan_module(self, module, pattern):
        self.scans.append((module, pattern))
        return self.scan_address


class TableScopingTests(unittest.TestCase):
    def test_same_positional_label_name_in_two_records_is_isolated(self):
        """Two records may both use ``return:`` as a positional label without
        colliding; neither creates an external symbol requirement."""
        plan = compile_table(_table_path(HOOK_A, HOOK_B), "Target.exe")
        self.assertEqual(plan["counts"]["blocked"], 0,
                         [e.get("reason") for e in plan["entries"] if not e["supported"]])
        for entry in plan["entries"]:
            self.assertEqual(entry["kind"], "script", entry.get("reason"))
            self.assertTrue(entry["supported"], entry.get("reason"))
            self.assertEqual(entry["requires"], [])

    def test_cross_record_registered_symbol_wins_over_local_label(self):
        """WP-28 two-stage resolution: when another supported record
        registers the same symbol, the table compiler re-declares the
        consumer's own positional label as an external requirement and
        stages the consumer behind the provider (CE semantics: table-wide
        registered symbols win over local label definitions)."""
        owner = hook_script("AnchorA", "caveA", "54 46", register_return=True)
        consumer = hook_script("AnchorB", "caveB", "57 47", register_return=False)
        plan = compile_table(_table_path(owner, consumer), "Target.exe")
        entries = {entry["id"]: entry for entry in plan["entries"]}
        owner_entry = entries[10]
        consumer_entry = entries[11]
        self.assertTrue(owner_entry["supported"], owner_entry.get("reason"))
        self.assertEqual(owner_entry["provides"], ["AnchorA", "return"])
        self.assertEqual(owner_entry["requires"], [])
        self.assertTrue(consumer_entry["supported"], consumer_entry.get("reason"))
        # Re-declared as an external requirement by the table compiler,
        # while prepare_program itself kept the label local.
        self.assertEqual(consumer_entry["requires"], ["return"])
        self.assertEqual(consumer_entry["program"]["positional_labels"], ["return"])
        self.assertEqual(consumer_entry["program"]["requires"], ["return"])
        self.assertEqual(consumer_entry["dependency_ids"], [10])
        # Consumer stages behind its provider (staged-metadata rule).
        self.assertIn("staged", consumer_entry)
        self.assertEqual(consumer_entry["staged"]["provider_ids"], [10])

    def test_provider_cascade_resolves_value_at_scanned_symbol(self):
        """A value record referencing a registered scan symbol from a
        hook that also uses a positional return label resolves correctly."""
        plan = compile_table(_table_path(HOOK_A, values=((20, "AnchorA+4"),)), "Target.exe")
        self.assertEqual(plan["counts"]["blocked"], 0,
                         [e.get("reason") for e in plan["entries"] if not e["supported"]])
        value = plan["entries"][1]
        self.assertTrue(value["supported"], value.get("reason"))
        self.assertEqual(value["dependency_ids"], [10])
        self.assertNotIn("no unique supported provider", value.get("reason", ""))

    def test_declared_label_locality_unchanged_across_records(self):
        """Two records each declaring ``label(flag)`` stay isolated; the
        declared label does not leak across record boundaries."""
        script = (
            "[ENABLE]\n"
            "alloc(cave,100)\n"
            "label(flag)\n"
            "cave:\n"
            "mov eax,1\n"
            "flag:\n"
            "ret\n"
            "registersymbol(flag)\n"
            "[DISABLE]\n"
            "unregistersymbol(flag)\n"
            "dealloc(cave)\n"
        )
        # Use distinct cave names to avoid allocation-name collision.
        script_a = script.replace("cave", "caveA")
        script_b = script.replace("cave", "caveB").replace("flag", "flagB")
        plan = compile_table(_table_path(script_a, script_b), "Target.exe")
        self.assertEqual(plan["counts"]["blocked"], 0,
                         [e.get("reason") for e in plan["entries"] if not e["supported"]])
        for entry in plan["entries"]:
            self.assertEqual(entry["requires"], [], entry.get("reason"))


class LinkScopingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.assembler = NasmAssembler()
        except Exception as exc:
            raise unittest.SkipTest(str(exc))

    def _allocations(self, cave: str) -> dict:
        # Preflight rounds alloc size up to at least 256.
        return {cave: {"address": 0x140002000, "size": 256, "executable": True, "writable": False}}

    def test_each_program_binds_its_own_positional_label(self):
        for hook, cave, anchor, scan, expected_return in (
            (HOOK_A_LINK, "caveA", "AnchorA", 0x140001000, 0x140001005),
            (HOOK_B_LINK, "caveB", "AnchorB", 0x140001100, 0x140001105),
        ):
            with self.subTest(anchor=anchor):
                program = prepare_program(hook, "Target.exe")
                memory = ScopingMemory(scan_address=scan)
                linked = link_program(program, memory, allocations=self._allocations(cave),
                                      assembler=self.assembler)
                self.assertEqual(linked["exports"][anchor], scan)
                # ``return:`` sits right after the five-byte jmp cave at the
                # anchor: the export must track this program's own scan.
                self.assertEqual(linked["exports"]["return"], expected_return)

    def test_positional_label_before_any_cursor_is_refused_at_link(self):
        program = prepare_program("[ENABLE]\nret:\nmov eax,1\n2000:\ndb 90\n[DISABLE]\n2000:\ndb 00",
                                  "Target.exe")
        with self.assertRaisesRegex(ProgramError,
                                    "Positional label appears before any address cursor."):
            link_program(program, ScopingMemory(), assembler=self.assembler)

    def test_declared_label_stays_local_per_program(self):
        for suffix, cave, cave_address in (("a", "caveA", 0x140002000),
                                           ("b", "caveB", 0x140003000)):
            with self.subTest(suffix=suffix):
                source = (
                    f"[ENABLE]\nalloc({cave},100)\nlabel(flag)\n{cave}:\n"
                    "mov eax,1\nflag:\nret\nregistersymbol(flag)\n[DISABLE]\n"
                    f"unregistersymbol(flag)\ndealloc({cave})"
                )
                program = prepare_program(source, "Target.exe")
                linked = link_program(program, ScopingMemory(),
                                      allocations={cave: {"address": cave_address, "size": 256,
                                                          "executable": True, "writable": False}},
                                      assembler=self.assembler)
                self.assertEqual(linked["exports"]["flag"], cave_address + 5)


if __name__ == "__main__":
    unittest.main()
