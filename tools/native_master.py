"""Frozen entry point for CT2Trainer-Master.exe (the Master Trainer).

Tiny wrapper around ``ct2trainer.native.master_trainer.master_ui.run_master``
so PyInstaller can freeze a dedicated, always-on Master Trainer EXE (MT-8).
The master UI is imported lazily inside ``main()`` after argument parsing,
so ``--help`` and the fail-closed folder/poll refusals never require
tkinter or a display.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys


def main(argv=None) -> int:
    cli = argparse.ArgumentParser(
        prog="CT2Trainer-Master",
        description="Master Trainer: index a table folder and auto-load the "
                    "matching table when its bound process appears")
    cli.add_argument("folder", nargs="?", type=Path, default=None,
                     help="Folder holding .ct tables (sub-folders "
                          "included); when omitted a directory picker is shown")
    cli.add_argument("--state-dir", type=Path, default=None,
                     help="Override the Master state home (the tables "
                          "index + per-table trainer state live there, "
                          "never in the table folder)")
    cli.add_argument("--debug-log", action="store_true",
                     help="Enable detailed runtime debug logging in the "
                          "generated trainer (plan flag debug_log; the "
                          "trainer writes a *.ct2debug.log file next to "
                          "the EXE)")
    cli.add_argument("--poll-ms", type=int, default=None,
                     help="Waiting-mode poll interval in milliseconds "
                          "(default: 1000)")
    cli.add_argument("--force", action="store_true",
                     help="Forced trainer start (0.38): recover stale state "
                          "without a confirmation prompt and reclaim a "
                          "leftover recovery fence; a proven-alive trainer "
                          "session is still refused")
    args = cli.parse_args(argv)
    # Fail-closed, named, before any UI import: a missing folder must
    # never pull in tkinter or create a window. run_master re-checks the
    # same condition for the picker/relaunch paths.
    if args.folder is not None and not args.folder.is_dir():
        print("Error: folder not found: " + str(args.folder), file=sys.stderr)
        return 2
    if args.poll_ms is not None and args.poll_ms < 1:
        print("Error: --poll-ms must be a positive integer (got %d)"
              % args.poll_ms, file=sys.stderr)
        return 2
    from ct2trainer.native.master_trainer.master_ui import WAIT_POLL_MS, run_master
    return run_master(
        args.folder,
        state_home=str(args.state_dir) if args.state_dir is not None else None,
        debug_log=args.debug_log,
        poll_ms=args.poll_ms if args.poll_ms is not None else WAIT_POLL_MS,
        force=args.force) or 0


if __name__ == "__main__":
    raise SystemExit(main())
