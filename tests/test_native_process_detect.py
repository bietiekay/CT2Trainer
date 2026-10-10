"""CT-derived target EXE detection and CLI auto-fill."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from ct2trainer.native import process_detect as pd
from ct2trainer.native.__main__ import main

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "windows" / "fixture_target" / "fixture.ct"


class FindCandidatesTests(unittest.TestCase):
    def test_empty_ct_has_no_candidates(self):
        self.assertEqual(pd.find_candidates(b"<CheatTable><CheatEntries/></CheatTable>"), [])

    def test_single_candidate(self):
        self.assertEqual(pd.find_candidates(b"aobscanmodule(x,Game.exe,48 8B)"), ["Game.exe"])

    def test_multiple_distinct_candidates_keep_first_seen_order(self):
        self.assertEqual(pd.find_candidates(b"A.exe then B.exe"), ["A.exe", "B.exe"])

    def test_case_insensitive_dedup_keeps_first_spelling(self):
        self.assertEqual(pd.find_candidates(b"A.exe later A.EXE"), ["A.exe"])

    def test_word_boundary_rejects_longer_words(self):
        self.assertEqual(pd.find_candidates(b"notgame.exemb mygame.exemalware"), [])

    def test_dotted_and_pathed_names(self):
        self.assertEqual(pd.find_candidates(b"my.game.v2.exe"), ["my.game.v2.exe"])
        self.assertEqual(pd.find_candidates(b"C:\\Games\\game.exe"), ["game.exe"])

    def test_token_at_eol_and_after_space(self):
        self.assertEqual(pd.find_candidates(b"game.exe"), ["game.exe"])
        self.assertEqual(pd.find_candidates(b"game.exe\ndb 1"), ["game.exe"])


class SuggestTests(unittest.TestCase):
    def test_none_without_candidate(self):
        self.assertIsNone(pd.suggest_process_name(b"<CheatTable/>"))

    def test_single_candidate_is_suggested(self):
        self.assertEqual(pd.suggest_process_name(b"x Game.exe y"), "Game.exe")

    def test_ambiguous_stays_none(self):
        self.assertIsNone(pd.suggest_process_name(b"A.exe B.exe"))


class ResolveTests(unittest.TestCase):
    def test_explicit_always_wins(self):
        self.assertEqual(pd.resolve_process("Mine.exe", b"A.exe B.exe"), ("Mine.exe", "explicit"))

    def test_missing_explicit_fills_single_candidate(self):
        self.assertEqual(pd.resolve_process(None, b"A.exe"), ("A.exe", "ct-suggestion"))
        self.assertEqual(pd.resolve_process("", b" A.exe "), ("A.exe", "ct-suggestion"))

    def test_multiple_candidates_rejected_with_names(self):
        with self.assertRaisesRegex(ValueError, "multiple distinct EXE names.*A.exe.*B.exe"):
            pd.resolve_process(None, b"A.exe B.exe")

    def test_no_candidate_rejected(self):
        with self.assertRaisesRegex(ValueError, "no .exe name"):
            pd.resolve_process(None, b"<CheatTable/>")


class CliTests(unittest.TestCase):
    def _run(self, argv):
        io_out, io_err = io.StringIO(), io.StringIO()
        with redirect_stdout(io_out), redirect_stderr(io_err):
            rc = main(argv)
        return rc, io_out.getvalue(), io_err.getvalue()

    def test_inspect_autofills_single_candidate_from_fixture_ct(self):
        rc, out, err = self._run(["inspect", str(FIXTURE)])
        self.assertEqual(rc, 0)
        plan = json.loads(out)
        self.assertEqual(plan["process_name"], "FixtureTarget.exe")
        self.assertIn("detected from the CT", err)

    def test_explicit_process_overrides_suggestion(self):
        rc, out, err = self._run(["inspect", str(FIXTURE), "--process", "Other.exe"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["process_name"], "Other.exe")
        self.assertNotIn("detected from the CT", err)

    def test_prepare_autofill_writes_plan(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "plan.json"
            rc, out, _ = self._run(["prepare", str(FIXTURE), "--output", str(output)])
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["process_name"], "FixtureTarget.exe")

    def _write_ct(self, body: bytes) -> str:
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        path = Path(td.name) / "sample.CT"
        path.write_bytes(body)
        return str(path)

    def test_multiple_candidates_error_lists_names(self):
        path = self._write_ct(b"<CheatTable CheatEngineTableVersion=\"45\">A.exe B.exe</CheatTable>")
        rc, _, err = self._run(["inspect", path])
        self.assertEqual(rc, 2)
        self.assertIn("multiple distinct EXE names", err)
        self.assertIn("A.exe", err)
        self.assertIn("B.exe", err)

    def test_no_candidate_error(self):
        path = self._write_ct(b"<CheatTable CheatEngineTableVersion=\"45\"/>")
        rc, _, err = self._run(["inspect", path])
        self.assertEqual(rc, 2)
        self.assertIn("no .exe name", err)


if __name__ == "__main__":
    unittest.main()
