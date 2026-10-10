"""Frozen trainer entry point; no conversion modules or CE runtime imports."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def _record_string_plan_load_failure(report, error):
    """Keep failed gate admission without replacing previous evidence."""
    report = Path(report).resolve()
    report.parent.mkdir(parents=True, exist_ok=True)
    frozen = bool(getattr(sys, 'frozen', False))
    evidence = {'schema': 'ct2trainer-owned-string-plan-load/v1',
                'status': 'failed', 'error_stage': 'plan-load', 'error': repr(error),
                'ce_implementation_inputs': [], 'target_spawned': False,
                'target_writes': False, 'target_write_actions_started': False,
                'frozen_runtime': frozen, 'source_runtime': not frozen,
                'game_runtime_verified': False, 'checks': []}
    with report.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(evidence, indent=2) + '\n')


def main(argv=None) -> int:
    from .bundle import read_embedded_plan
    from .engine import validate_plan
    cli = argparse.ArgumentParser(description="Independent CT2Trainer runtime")
    cli.add_argument("--plan", type=Path, help="Source runtime: declarative trainer JSON")
    cli.add_argument("--smoke", action="store_true", help="Check plan without a window or process writes")
    cli.add_argument("--smoke-output", type=Path, help="Write static smoke result as JSON")
    cli.add_argument("--fixture-target", type=Path, help="Integration gate: owned FixtureTarget.exe only")
    cli.add_argument("--fixture-report", type=Path, help="Integration gate evidence file")
    cli.add_argument('--hook-fixture-target',type=Path,help='Owned executable-hook fixture gate')
    cli.add_argument('--hook-fixture-report',type=Path,help='Executable-hook gate evidence file')
    cli.add_argument('--lua-fixture-target', type=Path, help='Owned Lua record fixture gate')
    cli.add_argument('--lua-fixture-report', type=Path, help='Lua record gate evidence file')
    cli.add_argument('--x86-fixture-target', type=Path, help='Pinned owned WOW64 fixture gate')
    cli.add_argument('--x86-fixture-report', type=Path, help='Owned WOW64 gate evidence file')
    cli.add_argument('--scan-fixture-target', type=Path, help='Pinned owned process/nth scan fixture gate')
    cli.add_argument('--scan-fixture-report', type=Path, help='Owned scan gate evidence file')
    cli.add_argument('--string-fixture-target', type=Path, help='Pinned owned String fixture gate')
    cli.add_argument('--string-fixture-report', type=Path, help='Owned String gate evidence file')
    cli.add_argument('--il2cpp-static-pe', type=Path, help='Static IL2CPP PE analysis target (owned fixture)')
    cli.add_argument('--il2cpp-static-metadata', type=Path, help='Static IL2CPP metadata file')
    cli.add_argument('--il2cpp-static-report', type=Path, help='Static IL2CPP gate evidence file')
    args = cli.parse_args(argv)
    pairs = (('fixture_target','fixture_report'),
             ('hook_fixture_target','hook_fixture_report'), ('lua_fixture_target','lua_fixture_report'),
             ('x86_fixture_target','x86_fixture_report'), ('scan_fixture_target','scan_fixture_report'),
             ('string_fixture_target','string_fixture_report'),
             ('il2cpp_static_pe','il2cpp_static_report'))
    owned_mode_requested = any(getattr(args, name) is not None for pair in pairs for name in pair)
    try:
        for target_name, report_name in pairs:
            if bool(getattr(args, target_name)) != bool(getattr(args, report_name)):
                raise ValueError('--' + target_name.replace('_','-') + ' and --' + report_name.replace('_','-') + ' are required together')
        modes = [bool(getattr(args, target)) for target, _ in pairs] + [bool(args.smoke or args.smoke_output)]
        if sum(modes) > 1:
            raise ValueError('Choose only one smoke or owned fixture gate')
        if args.il2cpp_static_pe:
            if args.il2cpp_static_metadata is None or args.il2cpp_static_report is None:
                raise ValueError('--il2cpp-static-pe requires --il2cpp-static-metadata and --il2cpp-static-report')
            from .il2cpp_static_probe import run_probe
            run_probe(args.il2cpp_static_pe, args.il2cpp_static_metadata,
                      args.il2cpp_static_report)
            return 0
        try:
            plan = json.loads(args.plan.read_text(encoding="utf-8")) if args.plan else read_embedded_plan(sys.executable)
        except (OSError, ValueError, RuntimeError) as exc:
            if args.string_fixture_target:
                _record_string_plan_load_failure(args.string_fixture_report, exc)
            raise
        if args.string_fixture_target:
            from .string_probe import run_probe
            run_probe(plan, args.string_fixture_target, args.string_fixture_report)
            return 0
        if args.lua_fixture_report is not None and args.lua_fixture_target is None:
            raise ValueError('--lua-fixture-report requires --lua-fixture-target')
        if args.x86_fixture_report is not None and args.x86_fixture_target is None:
            raise ValueError('--x86-fixture-report requires --x86-fixture-target')
        if args.scan_fixture_report is not None and args.scan_fixture_target is None:
            raise ValueError('--scan-fixture-report requires --scan-fixture-target')
        if args.scan_fixture_target:
            if args.scan_fixture_report is None:
                raise ValueError('--scan-fixture-target requires --scan-fixture-report')
            from .scan_probe import run_probe
            run_probe(plan, args.scan_fixture_target, args.scan_fixture_report)
            return 0
        if args.x86_fixture_target:
            if args.x86_fixture_report is None:
                raise ValueError('--x86-fixture-target requires --x86-fixture-report')
            from .x86_probe import run_probe
            run_probe(plan, args.x86_fixture_target, args.x86_fixture_report)
            return 0
        if args.lua_fixture_target:
            if args.lua_fixture_report is None:
                raise ValueError('--lua-fixture-target requires --lua-fixture-report')
            from .lua_record_probe import run_probe
            run_probe(plan, args.lua_fixture_target, args.lua_fixture_report)
            return 0
        validate_plan(plan)
        from .architecture import plan_architecture
        architecture = plan_architecture(plan)
        if args.hook_fixture_target:
            if args.hook_fixture_report is None:
                raise ValueError('--hook-fixture-target requires --hook-fixture-report')
            from .hook_probe import run_probe
            run_probe(plan,args.hook_fixture_target,args.hook_fixture_report)
            return 0
        if args.fixture_target:
            if args.fixture_report is None:
                raise ValueError("--fixture-target requires --fixture-report")
            from .fixture_probe import run_probe
            run_probe(plan, args.fixture_target, args.fixture_report)
            return 0
        if args.smoke or args.smoke_output:
            result = {"engine": plan["engine"], "trainer_id": plan["trainer_id"],
                      "entries": len(plan["entries"]), "ce_payload": False,
                      "target_architecture": architecture, "controller_architecture": "x64",
                      "status": "plan-validated-no-process-access"}
            if args.smoke_output:
                args.smoke_output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            if sys.stdout is not None:
                print(json.dumps(result))
            return 0
        from .ui import run_trainer
        return run_trainer(plan) or 0
    except (OSError, ValueError, RuntimeError, AssertionError) as exc:
        if args.smoke or args.smoke_output or owned_mode_requested:
            if sys.stderr is not None:
                print(str(exc), file=sys.stderr)
        else:
            from tkinter import messagebox
            messagebox.showerror("CT2Trainer", str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
