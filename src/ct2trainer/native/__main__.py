"""CE-free converter CLI for the independent Native edition."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys


def main(argv=None) -> int:
    cli = argparse.ArgumentParser(prog="ct2trainer", description="Compile CT data for the independent Win32 runtime")
    commands = cli.add_subparsers(dest="command", required=True)
    for command in ("inspect", "prepare", "build"):
        sub = commands.add_parser(command)
        sub.add_argument("table", type=Path)
        sub.add_argument("--process", required=False,
                         help="Exact target EXE; when omitted, a single distinct .exe name found in the CT fills the field (suggestion, never proof)")
        sub.add_argument("--title")
        sub.add_argument("--architecture", choices=("x86", "x64"), default="x64",
                         help="Fixed target architecture (default: x64); attach refuses a different target. Controller remains x64.")
        sub.add_argument("--include-id", type=int, action="append")
        sub.add_argument("--user-symbols", type=Path,
                         help="Optional user-symbol import file: JSON mapping of symbol "
                              "names to target addresses (decimal integers or 0x/$ hex "
                              "strings). Imported symbols cover requirements that no "
                              "record registers; they are seeded after the table-level "
                              "user-defined symbols, so an import overrides a table "
                              "definition of the same name. Record providers always win.")
        sub.add_argument("--debug-log", action="store_true",
                         help="Enable detailed runtime debug logging in the generated trainer "
                              "(plan flag debug_log; the trainer writes a *.ct2debug.log file next to the EXE)")
        if command != "inspect":
            sub.add_argument("--output", type=Path, required=True)
            sub.add_argument("--force", action="store_true")
        if command == "build":
            sub.add_argument("--template", type=Path)
    commands.add_parser("gui")
    il2cpp = commands.add_parser("il2cpp", help="Static IL2CPP PE/metadata analysis")
    il2cpp.add_argument("pe", type=Path, help="PE executable to analyze")
    il2cpp.add_argument("--metadata", type=Path, required=True,
                        help="IL2CPP metadata blob (global-metadata.dat)")
    il2cpp.add_argument("--output", type=Path, help="Write JSON report to this path")
    run = commands.add_parser("run")
    run.add_argument("plan", type=Path)
    for name in ('assess-recovery', 'recover'):
        recovery = commands.add_parser(name)
        recovery.add_argument('plan', type=Path)
        recovery.add_argument('--state-dir', type=Path, required=True)
        recovery.add_argument('--process-lock-dir', type=Path)
        if name == 'recover':
            recovery.add_argument('--archive-dir', type=Path, required=True)
    args = cli.parse_args(argv)
    try:
        if args.command in ("inspect", "prepare", "build"):
            from .process_detect import resolve_process
            args.process, process_source = resolve_process(args.process, args.table.read_bytes())
            if process_source == "ct-suggestion":
                print(f"note: target EXE '{args.process}' detected from the CT (suggestion, not proof)", file=sys.stderr)
        if args.command == "gui":
            from .converter import main as gui_main
            return gui_main()
        if args.command == "run":
            from .ui import run_trainer
            return run_trainer(json.loads(args.plan.read_text(encoding="utf-8"))) or 0
        if args.command == "il2cpp":
            from .il2cpp_static_probe import run_probe
            report = run_probe(args.pe, args.metadata, args.output)
            if args.output is not None:
                print(args.output)
            else:
                print(json.dumps(report, indent=2))
            return 0
        if args.command in {'assess-recovery', 'recover'}:
            from dataclasses import asdict
            from .engine import validate_plan
            from .recovery import assess_recovery
            plan = json.loads(args.plan.read_text(encoding='utf-8'))
            validate_plan(plan)
            assessment = assess_recovery(args.state_dir, args.process_lock_dir,
                                         expected_trainer_id=plan['trainer_id'],
                                         expected_table_sha256=plan['table_sha256'])
            if args.command == 'assess-recovery':
                print(json.dumps(asdict(assessment), indent=2, default=str))
                return 2 if assessment.status == 'blocked' else 0
            from .recovery_operation import recover_assessment
            result = recover_assessment(assessment, args.archive_dir,
                                         expected_trainer_id=plan['trainer_id'],
                                         expected_table_sha256=plan['table_sha256'])
            print(json.dumps(asdict(result), indent=2, default=str))
            return 0 if result.completed else 2 if result.status == 'refused' else 3
        from .compiler import compile_table, load_user_symbols
        user_symbols = (load_user_symbols(args.user_symbols)
                        if args.user_symbols is not None else None)
        plan = compile_table(args.table, args.process, title=args.title, selected_ids=args.include_id,
                             user_symbols=user_symbols,
                             architecture=args.architecture, debug_log=args.debug_log)
        if args.command == "inspect":
            print(json.dumps(plan, ensure_ascii=True, indent=2))
        elif args.command == "prepare":
            if args.output.exists() and not args.force:
                raise FileExistsError("Output exists; use --force.")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(plan, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
            print(args.output.resolve())
        else:
            from .bundle import build_trainer
            output, report = build_trainer(plan, args.output, args.template, force=args.force)
            print(output)
            print(report)
        return 0
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
