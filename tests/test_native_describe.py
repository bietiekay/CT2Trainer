"""Tests for the describe CLI subcommand and value-read-failed observability.

Covers:
- describe_entries / render_describe pure functions
- CLI dispatch of the 'describe' subcommand (text + JSON output)
- value-read-failed debug log event on read errors
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ct2trainer.native.compiler import compile_table
from ct2trainer.native.describe import describe_entries, render_describe
from ct2trainer.native.engine import NativeRuntimeError, TrainerEngine
from test_native_engine import FakeMemory

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "windows" / "fixture_target" / "fixture.ct"


class DescribeEntriesTests(unittest.TestCase):
    def setUp(self):
        self.plan = compile_table(FIXTURE, "FixtureTarget.exe")

    def test_all_entries_described(self):
        results = describe_entries(self.plan)
        # The fixture has 4 entries (ids 0, 1, 2, 3).
        self.assertEqual(len(results), 4)
        ids = [r["id"] for r in results]
        self.assertEqual(ids, [0, 1, 2, 3])

    def test_single_entry_filter(self):
        results = describe_entries(self.plan, include_ids={2})
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], 2)
        self.assertIn("Test value", results[0]["title"])

    def test_unknown_id_raises(self):
        with self.assertRaisesRegex(ValueError, "Unknown entry id"):
            describe_entries(self.plan, include_ids={9999})

    def test_result_shape(self):
        results = describe_entries(self.plan, include_ids={0})
        r = results[0]
        self.assertIn("id", r)
        self.assertIn("title", r)
        self.assertIn("script", r)
        self.assertIn("assessment", r)
        self.assertIn("actions", r)
        # Entry 0 is an AA script, so it should have a script
        self.assertIsNotNone(r["script"])
        self.assertIn("body", r["script"])
        self.assertIn("title", r["script"])

    def test_value_entry_has_no_script(self):
        results = describe_entries(self.plan, include_ids={2})
        r = results[0]
        # Entry 2 is a plain value, no executable script
        self.assertIsNone(r["script"])


class RenderDescribeTests(unittest.TestCase):
    def test_empty_list(self):
        self.assertEqual(render_describe([]), "(no entries)")

    def test_renders_all_sections(self):
        results = [
            {
                "id": 1,
                "title": "Test entry",
                "script": {"title": "AA Program", "body": "dd 1"},
                "assessment": "This entry writes a patch.",
                "actions": "Patch 1 byte at 0x1000",
            }
        ]
        text = render_describe(results)
        self.assertIn("=== [1] Test entry ===", text)
        self.assertIn("Script:", text)
        self.assertIn("AA Program", text)
        self.assertIn("dd 1", text)
        self.assertIn("Assessment:", text)
        self.assertIn("This entry writes a patch.", text)
        self.assertIn("Actions:", text)
        self.assertIn("Patch 1 byte at 0x1000", text)

    def test_no_script_renders_placeholder(self):
        results = [
            {
                "id": 5,
                "title": "Value entry",
                "script": None,
                "assessment": "A value record.",
                "actions": "",
            }
        ]
        text = render_describe(results)
        self.assertIn("Script: (none)", text)
        self.assertIn("Actions: (none)", text)


class DescribeCLITests(unittest.TestCase):
    """Test the 'describe' subcommand dispatch in __main__.main()."""

    def test_describe_text_output(self):
        from ct2trainer.native.__main__ import main
        import io
        from contextlib import redirect_stdout

        with tempfile.TemporaryDirectory() as tmp:
            ct_path = Path(tmp) / "test.ct"
            ct_path.write_bytes(FIXTURE.read_bytes())
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = main(["describe", str(ct_path), "--process", "FixtureTarget.exe"])
            self.assertEqual(rc, 0)
            output = buf.getvalue()
            self.assertIn("=== [0]", output)
            self.assertIn("Assessment:", output)

    def test_describe_json_output(self):
        from ct2trainer.native.__main__ import main
        import io
        from contextlib import redirect_stdout

        with tempfile.TemporaryDirectory() as tmp:
            ct_path = Path(tmp) / "test.ct"
            ct_path.write_bytes(FIXTURE.read_bytes())
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = main(["describe", str(ct_path), "--process",
                           "FixtureTarget.exe", "--json"])
            self.assertEqual(rc, 0)
            data = json.loads(buf.getvalue())
            self.assertIsInstance(data, list)
            self.assertEqual(len(data), 4)
            self.assertEqual(data[0]["id"], 0)

    def test_describe_single_id(self):
        from ct2trainer.native.__main__ import main
        import io
        from contextlib import redirect_stdout

        with tempfile.TemporaryDirectory() as tmp:
            ct_path = Path(tmp) / "test.ct"
            ct_path.write_bytes(FIXTURE.read_bytes())
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = main(["describe", str(ct_path), "--process",
                           "FixtureTarget.exe", "--id", "2"])
            self.assertEqual(rc, 0)
            output = buf.getvalue()
            self.assertIn("=== [2]", output)
            self.assertNotIn("=== [0]", output)


class ValueReadFailedLogTests(unittest.TestCase):
    """Verify that read_value failures emit a value-read-failed debug event."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.cwd_dir = self.directory / "cwd"
        self.cwd_dir.mkdir()
        self.memory = FakeMemory()
        self.engine = None

    def tearDown(self):
        if self.engine is not None and not self.engine.closed:
            self.engine.close()
        self.temp.cleanup()

    def _start(self, attach=True):
        plan = compile_table(FIXTURE, "FixtureTarget.exe", debug_log=True)
        with patch("pathlib.Path.cwd", return_value=self.cwd_dir):
            self.engine = TrainerEngine(
                plan, self.directory,
                lambda _n: self.memory,
                self.directory / "shared")
        if attach:
            self.engine.poll()
        return self.engine

    def test_value_read_failure_is_logged(self):
        engine = self._start()
        # Entry 2 is a staged value; reading without activating the provider
        # should fail and log the event.
        with self.assertRaises(NativeRuntimeError):
            engine.read_value(2)
        # A second identical failure must not duplicate the log line.
        with self.assertRaises(NativeRuntimeError):
            engine.read_value(2)
        # Give the log a moment to flush
        engine.close()
        log_file = self.cwd_dir / "ct2trainer-debug.log"
        self.assertTrue(log_file.exists())
        lines = [json.loads(l) for l in log_file.read_text(
            encoding="utf-8").splitlines() if l.strip()]
        events = [e["event"] for e in lines]
        failed = [e for e in lines if e["event"] == "value-read-failed"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["identifier"], 2)
        self.assertIn("Test value", failed[0]["label"])
        self.assertIn("requires active provider", failed[0]["error"])
        self.assertIn("Traceback", failed[0]["traceback"])

    def test_value_read_failure_rearms_after_recovery(self):
        engine = self._start()
        # Provider entry 0 not active -> first failure logged.
        with self.assertRaises(NativeRuntimeError):
            engine.read_value(2)
        # Activate the provider, read succeeds, failure entry clears.
        engine.toggle(0, True)
        self.assertEqual(engine.read_value(2), "1234")
        # Break the provider again: the failure must be logged anew.
        engine.toggle(0, False)
        with self.assertRaises(NativeRuntimeError):
            engine.read_value(2)
        engine.close()
        log_file = self.cwd_dir / "ct2trainer-debug.log"
        lines = [json.loads(l) for l in log_file.read_text(
            encoding="utf-8").splitlines() if l.strip()]
        failed = [e for e in lines if e["event"] == "value-read-failed"]
        self.assertEqual(len(failed), 2)


if __name__ == "__main__":
    unittest.main()
