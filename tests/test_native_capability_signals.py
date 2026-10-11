"""WP-14 static review signals in capability.assess (staged provider, master
toggle, signed pointer offset) and the table parse fields that feed them."""

import tempfile
import unittest
from pathlib import Path

from ct2trainer.capability import assess
from ct2trainer.table import read_table


def _ct_xml(entries: str) -> str:
    return (
        '<CheatTable CheatEngineTableVersion="45">'
        + "<CheatEntries>" + entries + "</CheatEntries>"
        + "</CheatTable>"
    )


PROVIDER_SCRIPT = (
    '<CheatEntry><ID>1</ID><Description>"Provider"</Description>'
    '<VariableType>Auto Assembler Script</VariableType>'
    "<AssemblerScript>[ENABLE]\nalloc(cave,64)\ncave:\nregistersymbol(MySym)\n"
    "[DISABLE]\nunregistersymbol(MySym)\ndealloc(cave)</AssemblerScript>"
    "</CheatEntry>"
)

PLAIN_SCRIPT = (
    '<CheatEntry><ID>2</ID><Description>"Plain"</Description>'
    '<VariableType>Auto Assembler Script</VariableType>'
    "<AssemblerScript>[ENABLE]\ndb 90\n[DISABLE]\ndb 90</AssemblerScript>"
    "</CheatEntry>"
)

MASTER_SCRIPT = (
    '<CheatEntry><ID>3</ID><Description>"Master"</Description>'
    '<VariableType>Auto Assembler Script</VariableType>'
    '<Options moHideChildren="1"/>'
    "<AssemblerScript>[ENABLE]\n{$lua}\n"
    "getMemoryRecordByID(1).Active = true\n"
    "getMemoryRecordByID(2).Active = true\n"
    "{$asm}\n[DISABLE]\n{$lua}\n"
    "getMemoryRecordByID(1).Active = false\n"
    "getMemoryRecordByID(2).Active = false\n"
    "{$asm}</AssemblerScript>"
    "</CheatEntry>"
)

QUERY_ONLY_SCRIPT = (
    '<CheatEntry><ID>4</ID><Description>"Query"</Description>'
    '<VariableType>Auto Assembler Script</VariableType>'
    "<AssemblerScript>[ENABLE]\n{$lua}\n"
    "local r = getMemoryRecordByID(1)\n"
    "{$asm}\n[DISABLE]\n{$asm}</AssemblerScript>"
    "</CheatEntry>"
)

SIGNED_VALUE = (
    '<CheatEntry><ID>5</ID><Description>"Signed chain"</Description>'
    '<VariableType>4 Bytes</VariableType><Address>Target.exe+1000</Address>'
    "<Offsets><Offset>-0x10</Offset><Offset>28</Offset></Offsets>"
    "</CheatEntry>"
)

UNSIGNED_VALUE = (
    '<CheatEntry><ID>6</ID><Description>"Plain chain"</Description>'
    '<VariableType>4 Bytes</VariableType><Address>Target.exe+1000</Address>'
    "<Offsets><Offset>10</Offset><Offset>28</Offset></Offsets>"
    "</CheatEntry>"
)


def _entry(report: dict, record_id: int) -> dict:
    row = [r for r in report["entries"] if r["id"] == record_id]
    assert len(row) == 1, (record_id, report["entries"])
    return row[0]


class CapabilitySignalTests(unittest.TestCase):
    def _assess(self, entries: str) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "signals.ct"
            path.write_text(_ct_xml(entries), encoding="utf-8")
            return assess(read_table(path))

    def test_script_registering_symbols_is_a_staged_provider_signal(self):
        report = self._assess(PROVIDER_SCRIPT + PLAIN_SCRIPT)
        self.assertIn("script-registers-symbols", _entry(report, 1)["review_reasons"])
        self.assertNotIn("script-registers-symbols", _entry(report, 2)["review_reasons"])

    def test_embedded_master_toggle_lua_is_flagged(self):
        report = self._assess(MASTER_SCRIPT + QUERY_ONLY_SCRIPT)
        self.assertIn("embedded-record-activation-set", _entry(report, 3)["review_reasons"])
        self.assertNotIn(
            "embedded-record-activation-set", _entry(report, 4)["review_reasons"])

    def test_signed_pointer_offset_is_flagged_unsigned_is_not(self):
        report = self._assess(SIGNED_VALUE + UNSIGNED_VALUE)
        self.assertIn("signed-pointer-offset", _entry(report, 5)["review_reasons"])
        self.assertNotIn("signed-pointer-offset", _entry(report, 6)["review_reasons"])

    def test_table_parse_exposes_the_static_signals(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "signals.ct"
            path.write_text(_ct_xml(PROVIDER_SCRIPT + MASTER_SCRIPT + SIGNED_VALUE),
                            encoding="utf-8")
            by_id = {e.id: e for e in read_table(path).entries}
            self.assertTrue(by_id[1].registers_symbols)
            self.assertFalse(by_id[3].registers_symbols)
            self.assertTrue(by_id[3].activation_set_lua)
            self.assertFalse(by_id[5].activation_set_lua)
            self.assertFalse(by_id[5].registers_symbols)

    def test_report_stays_deterministic(self):
        a = self._assess(PROVIDER_SCRIPT + MASTER_SCRIPT + SIGNED_VALUE)
        b = self._assess(PROVIDER_SCRIPT + MASTER_SCRIPT + SIGNED_VALUE)
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
