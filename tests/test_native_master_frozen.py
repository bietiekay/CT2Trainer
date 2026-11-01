"""MT-8 frozen Master Trainer entry point (tools/native_master.py).

The frozen CT2Trainer-Master.exe shares the template/bundle machinery of
the standalone trainer but is a plain entry wrapper: it parses its own
CLI surface, refuses invalid inputs fail-closed and by name before any
UI import, and hands the parsed arguments to run_master. The real
PyInstaller freeze is verified at build time (root work); these tests pin
the entry module itself - allowlist membership, loadability, the help
contract, the exit-code-2 refusals and the lazy-import structure that
guarantees tkinter is never required for --help or a missing folder.
"""
from __future__ import annotations
import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "tools" / "native_master.py"

BUILD_SPEC = importlib.util.spec_from_file_location(
    "owned_native_build_mt8", ROOT / "tools" / "native_build.py")
BUILD = importlib.util.module_from_spec(BUILD_SPEC)
BUILD_SPEC.loader.exec_module(BUILD)


def _load_entry():
    """Load the frozen entry module from its path (spec_from_file_location)."""
    spec = importlib.util.spec_from_file_location("owned_native_master_mt8", ENTRY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MasterFrozenEntryTests(unittest.TestCase):
    """tools/native_master.py is the release-admitted frozen Master entry."""

    def test_entry_file_exists(self):
        self.assertTrue(ENTRY.is_file(), "tools/native_master.py must exist")
        self.assertGreater(ENTRY.stat().st_size, 0)

    def test_entry_admitted_by_source_allowlist(self):
        names = [p.relative_to(BUILD.ROOT).as_posix() for p in BUILD.source_files()]
        self.assertIn("tools/native_master.py", names,
                      "the frozen entry must ship in the source ZIP allowlist")
        self.assertIn("tests/test_native_master_frozen.py", names,
                      "this dedicated test file must ship via the tests glob")

    def test_entry_module_loads_and_exposes_main(self):
        module = _load_entry()
        self.assertTrue(callable(getattr(module, "main", None)),
                        "main(argv=None) -> int must be the entry point")
        # Lazy-import structure: the master UI (and with it tkinter) is
        # imported inside main(), never at module level.
        self.assertNotIn("tkinter", vars(module))
        self.assertNotIn("master_ui", vars(module))
        self.assertNotIn("run_master", vars(module))

    def test_frozen_entry_tail_is_pinned(self):
        tail = ENTRY.read_text(encoding="utf-8").splitlines()[-2:]
        self.assertEqual(tail, ['if __name__ == "__main__":',
                                "    raise SystemExit(main())"])

    def test_help_exits_zero_and_pins_cli_surface(self):
        module = _load_entry()
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            with self.assertRaises(SystemExit) as caught:
                module.main(["--help"])
        self.assertEqual(caught.exception.code, 0,
                         "argparse --help must exit 0")
        out = buffer.getvalue()
        self.assertTrue(out.startswith("usage: CT2Trainer-Master"), out[:200])
        for token in ("folder", "--state-dir", "--debug-log", "--poll-ms"):
            self.assertIn(token, out)

    def test_missing_folder_refusal_returns_2_without_tkinter(self):
        module = _load_entry()
        had_tkinter = "tkinter" in sys.modules
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "no-such-folder"
            buffer = io.StringIO()
            with contextlib.redirect_stderr(buffer):
                code = module.main([str(missing)])
        self.assertEqual(code, 2, "folder-not-found must be the named exit 2")
        self.assertIn("folder not found", buffer.getvalue())
        if not had_tkinter:
            # The refusal path never imports the master UI, so a clean
            # interpreter must show no tkinter side effect.
            self.assertNotIn("tkinter", sys.modules)

    def test_file_given_as_folder_is_refused(self):
        module = _load_entry()
        with tempfile.TemporaryDirectory() as tmp:
            table = Path(tmp) / "table.ct"
            table.write_bytes(b"<CheatEngineTable/>")
            buffer = io.StringIO()
            with contextlib.redirect_stderr(buffer):
                code = module.main([str(table)])
        self.assertEqual(code, 2)
        self.assertIn("folder not found", buffer.getvalue())

    def test_poll_ms_below_one_is_refused_before_the_ui(self):
        module = _load_entry()
        with tempfile.TemporaryDirectory() as tmp:
            for value in ("0", "-5"):
                buffer = io.StringIO()
                with contextlib.redirect_stderr(buffer):
                    code = module.main(["--poll-ms", value, tmp])
                self.assertEqual(code, 2, "--poll-ms " + value)
                self.assertIn("--poll-ms", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
