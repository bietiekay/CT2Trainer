"""Build and audit the allowlisted independent edition, without CE inputs."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]

try:
    VERSION = (ROOT / 'VERSION').read_text(encoding='utf-8').strip()
except FileNotFoundError:
    raise ValueError('VERSION file missing at repo root; it is the single version source for Native builds')
if not VERSION:
    raise ValueError('VERSION file is empty')
EXCLUDED = ("ct2trainer.build", "ct2trainer.ce_source", "ct2trainer.gui", "ct2trainer.package", "ct2trainer.standalone", "ct2trainer.version_adapter", "ct2trainer.winresource", "ct2trainer.publisher", "ct2trainer.__main__")

# Release-archive docs allowlist (0.9.0-rc2): the exact doc/metadata set that
# ships in the source ZIP next to the build-essential tree, and the set that
# refresh-source keeps current. Everything else in documentation/ and
# gap_inventory/ is dev material (ledgers, workflow rules, corpus scratch) and
# stays out of distributed releases. The three "documentation/*.md" core docs
# (build guide, usage guide, derivation doc) are required by the release
# contract and fail the build when absent.
RELEASE_DOC_FILES = (
    'CHANGELOG.md',
    'VERSION',
    'documentation/native-runtime.md',
    'documentation/native-verification.md',
    'documentation/build.md',
    'documentation/usage.md',
    'documentation/derivation.md',
    'tests/deck/compatibility-matrix.md',
    'tests/windows/fixture_target/README.md',
    'gap_inventory/feature-coverage.json',
)

MONO_SOURCE_INPUTS = (
    'dependencies/native/mono-api-source/api-prototypes.json',
    'dependencies/native/mono-api-source/LICENSE.txt',
    'dependencies/native/mono-api-source/LOCAL-CHANGES.md',
    'dependencies/native/mono-api-source/README.md',
    'dependencies/native/mono-api-source/upstream/LICENSE',
    'dependencies/native/mono-api-source/upstream/mono/cil/opcode.def',
    'dependencies/native/mono-api-source/upstream/mono/metadata/appdomain.h',
    'dependencies/native/mono-api-source/upstream/mono/metadata/assembly.h',
    'dependencies/native/mono-api-source/upstream/mono/metadata/attrdefs.h',
    'dependencies/native/mono-api-source/upstream/mono/metadata/blob.h',
    'dependencies/native/mono-api-source/upstream/mono/metadata/class.h',
    'dependencies/native/mono-api-source/upstream/mono/metadata/debug-helpers.h',
    'dependencies/native/mono-api-source/upstream/mono/metadata/debug-mono-symfile.h',
    'dependencies/native/mono-api-source/upstream/mono/metadata/environment.h',
    'dependencies/native/mono-api-source/upstream/mono/metadata/exception.h',
    'dependencies/native/mono-api-source/upstream/mono/metadata/image.h',
    'dependencies/native/mono-api-source/upstream/mono/metadata/loader.h',
    'dependencies/native/mono-api-source/upstream/mono/metadata/metadata.h',
    'dependencies/native/mono-api-source/upstream/mono/metadata/mono-config.h',
    'dependencies/native/mono-api-source/upstream/mono/metadata/mono-debug.h',
    'dependencies/native/mono-api-source/upstream/mono/metadata/mono-gc.h',
    'dependencies/native/mono-api-source/upstream/mono/metadata/object-forward.h',
    'dependencies/native/mono-api-source/upstream/mono/metadata/object.h',
    'dependencies/native/mono-api-source/upstream/mono/metadata/opcodes.h',
    'dependencies/native/mono-api-source/upstream/mono/metadata/profiler-events.h',
    'dependencies/native/mono-api-source/upstream/mono/metadata/profiler.h',
    'dependencies/native/mono-api-source/upstream/mono/metadata/reflection.h',
    'dependencies/native/mono-api-source/upstream/mono/metadata/row-indexes.h',
    'dependencies/native/mono-api-source/upstream/mono/metadata/sgen-bridge.h',
    'dependencies/native/mono-api-source/upstream/mono/metadata/threads.h',
    'dependencies/native/mono-api-source/upstream/mono/metadata/tokentype.h',
    'dependencies/native/mono-api-source/upstream/mono/metadata/verify.h',
    'dependencies/native/mono-api-source/upstream/mono/mini/jit.h',
    'dependencies/native/mono-api-source/upstream/mono/utils/mono-counters.h',
    'dependencies/native/mono-api-source/upstream/mono/utils/mono-dl-fallback.h',
    'dependencies/native/mono-api-source/upstream/mono/utils/mono-error.h',
    'dependencies/native/mono-api-source/upstream/mono/utils/mono-forward.h',
    'dependencies/native/mono-api-source/upstream/mono/utils/mono-jemalloc.h',
    'dependencies/native/mono-api-source/upstream/mono/utils/mono-logger.h',
    'dependencies/native/mono-api-source/upstream/mono/utils/mono-publib.h',
    'dependencies/native/mono-api-source/upstream/PATENTS.TXT',
    'dependencies/native/mono-api-source/upstream-pins.json',
    'src/ct2trainer/native/mono/mono_api.c',
    'src/ct2trainer/native/mono/mono_api.h',
    'src/ct2trainer/native/mono/mono_api_redirect.h',
    'src/ct2trainer/native/mono/mono_collector.c',
    'src/ct2trainer/native/mono/mono_collector.h',
    'tests/windows/mono_fixture/Build-FakeMonoExports.ps1',
    'tests/windows/mono_fixture/Build-MonoSources.ps1',
    'tests/windows/mono_fixture/Build-OwnedMonoFixture.ps1',
    'tests/windows/mono_fixture/fake_exports/admission_probe.c',
    'tests/windows/mono_fixture/fake_exports/complete.c',
    'tests/windows/mono_fixture/fake_exports/data.c',
    'tests/windows/mono_fixture/fake_exports/forwarded.c',
    'tests/windows/mono_fixture/fake_exports/forwarded.def',
    'tests/windows/mono_fixture/fake_exports/missing.c',
    'tests/windows/mono_fixture/fake_exports/oldversion.c',
    'tests/windows/mono_fixture/mono_fixture_host.c',
    'tests/windows/mono_fixture/owned_fixture_bootstrap.c',
    'tests/windows/mono_fixture/owned_fixture_bootstrap.h',
    'tests/windows/mono_fixture/OwnedManagedFixture.cs',
    'tests/windows/mono_fixture/README.md',
)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_files():
    """One explicit redistributable allowlist shared by build and docs refresh."""
    files = list((ROOT / 'src/ct2trainer/native').glob('*.py'))
    for native_component in ('clock','target_broker'):
        files += [p for p in (ROOT/'src/ct2trainer/native'/native_component).glob('*')
                  if p.is_file() and p.suffix in {'.c','.h','.py'}]
    files += [ROOT / 'src/ct2trainer' / n for n in ('__init__.py','table.py','local_processes.py','capability.py')]
    # Generated converter/trainer icons, see tools/create_icons.py.
    files += [ROOT / 'src/ct2trainer' / 'assets' / n for n in ('ct2trainer-converter.ico', 'ct2trainer-trainer.ico')]
    files += list((ROOT / 'tools').glob('native_*.py'))
    files += [ROOT / 'scripts/Build-Native.ps1', ROOT / 'tests/windows/native_probe.py']
    files += list((ROOT / 'tests').glob('test_native_*.py'))
    files += [ROOT / 'tests/native_il2cpp_static_fixtures.py']
    files += [ROOT / 'tests/windows/fixture_target' / n for n in ('fixture_target.c','fixture.ct','fixture_one_shot.ct')]
    for fixture in ('hook_fixture','debug_hook_fixture','clock_fixture','scan_fixture','target_broker_fixture','string_fixture'):
        files += [p for p in (ROOT/'tests/windows'/fixture).glob('*')
                  if p.suffix in {'.c','.h','.py','.ct','.ps1','.md'}]
    # Mono is a selected source-only API adaptation: never recursively admit
    # extra SDK/runtime files or arbitrary fixture .def inputs.
    files += [p for p in (ROOT/'dependencies/native').rglob('*')
              if p.is_file() and p.relative_to(ROOT/'dependencies/native').parts[0] != 'mono-api-source']
    mono_inputs = [ROOT / name for name in MONO_SOURCE_INPUTS]
    for path in mono_inputs:
        if not path.is_file():
            raise ValueError('Required selected Mono source input missing: '+path.relative_to(ROOT).as_posix())
    files += mono_inputs
    names=[p.relative_to(ROOT).as_posix() for p in files]
    if len(names)!=len(set(names)):raise ValueError('Duplicate Native source input')
    return sorted(files)


def verify_inputs():
    manifest = json.loads((ROOT / "dependencies/manifest.json").read_text(encoding="utf-8"))
    checked = []
    for entry in manifest["files"]:
        if entry["path"].startswith(("python/", "native/")):
            path = ROOT / "dependencies" / entry["path"]
            if path.stat().st_size != entry["bytes"] or digest(path) != entry["sha256"]:
                raise ValueError(f"Native build dependency mismatch: {entry['path']}")
            checked.append(entry["path"])
    print(f"Verified {len(checked)} Python and BSD/MIT native inputs; CE inputs are unused.")


def run_tests(output):
    """Keep native stdout/stderr and the exact tested input snapshot together."""
    output = Path(output).resolve()
    files = source_files()
    snapshot = {path.relative_to(ROOT).as_posix(): digest(path) for path in files}
    log = output / 'suite-tests.log'
    report_path = output / 'suite-tests.json'
    if log.exists() or report_path.exists():
        raise FileExistsError('Native suite evidence already exists in this run')
    with log.open('x', encoding='utf-8') as stream:
        result = subprocess.run([sys.executable, '-m', 'unittest', 'discover',
            '-s', 'tests', '-p', 'test_native_*.py', '-q'], cwd=ROOT,
            stdout=stream, stderr=subprocess.STDOUT)
    raw = log.read_text(encoding='utf-8')
    count = re.search(r'^Ran (\d+) tests? in ', raw, re.MULTILINE)
    skips = re.search(r'^OK \(skipped=(\d+)\)', raw, re.MULTILINE)
    unchanged = source_files() == files and all(
        digest(path) == snapshot[path.relative_to(ROOT).as_posix()] for path in files)
    report = {'schema': 'ct2trainer-suite/v1',
        'status': 'passed' if result.returncode == 0 and count and unchanged else 'failed',
        'exit_code': result.returncode, 'tests_run': int(count[1]) if count else None,
        'skipped': int(skips[1]) if skips else 0,
        'source_inputs_unchanged': unchanged, 'source_inputs': snapshot,
        'log_sha256': digest(log)}
    with report_path.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print(f"Native suite: {report['tests_run']} tests, {report['skipped']} skips; {log}")
    if report['status'] != 'passed':
        raise RuntimeError('Native tests failed or their source changed; preserve this run')


def inventory(executable):
    from PyInstaller.archive.readers import CArchiveReader
    archive = CArchiveReader(str(executable))
    names = sorted(archive.toc)
    modules = []
    for name in names:
        if name.endswith(".pyz"):
            modules.extend(archive.open_embedded_archive(name).toc)
    forbidden = [name for name in names + modules if any(
        token in name.casefold() for token in ("cheatengine", "trainerforge", "ce-bundle", "runtime.lua", "phase1_secure", "standalonephase", "lua53-64.dll", "ct2trainer.ce_source", "ct2trainer.runtime")) or name in EXCLUDED]
    if forbidden:
        raise ValueError(f"CE content reached Native binary: {forbidden}")
    independent_components={}
    for package in ('lupa','iced-x86'):
        for wheel in (ROOT/'dependencies/native'/package).glob('*.whl'):
            with zipfile.ZipFile(wheel) as source:
                for member in source.namelist():
                    if member.endswith('.pyd') and (package != 'lupa' or '/lua53.' in member):
                        independent_components[member.replace('/','\\')]=hashlib.sha256(source.read(member)).hexdigest()
    component_hashes={}
    for name in names:
        if name.replace('\\','/').endswith('native-tools/nasm.exe'):
            from ct2trainer.native.assembler import NASM_WIN64_SHA256
            if hashlib.sha256(archive.extract(name)).hexdigest() != NASM_WIN64_SHA256:
                raise ValueError('Embedded NASM does not match its independently sourced hash')
            component_hashes[name]=NASM_WIN64_SHA256
        normalized=name.replace('/','\\')
        if normalized in independent_components:
            expected=independent_components[normalized]
            if hashlib.sha256(archive.extract(name)).hexdigest()!=expected:
                raise ValueError('Embedded independent extension differs from its archived upstream wheel: '+name)
            component_hashes[name]=expected
    normalized_components={name.replace('/','\\') for name in component_hashes}
    required=set(independent_components)|{'native-tools\\nasm.exe'}
    if not required<=normalized_components:
        raise ValueError('Required independent components missing from frozen binary: '+str(sorted(required-normalized_components)))
    return {"file": Path(executable).name, "sha256": digest(executable), "archive_entries": names, "python_modules": sorted(modules), "ce_payload": False,
            'independent_native_components':component_hashes}


def restore_nasm(output):
    """Restore one pinned file, without trusting archive member paths."""
    from ct2trainer.native.assembler import NasmAssembler
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    nasm = output / 'nasm.exe'
    if nasm.exists():
        raise FileExistsError(nasm)
    with zipfile.ZipFile(ROOT/'dependencies/native/nasm/nasm-3.02-win64.zip') as source:
        binary = source.read('nasm-3.02/nasm.exe')
    from ct2trainer.native.assembler import NASM_WIN64_SHA256
    if hashlib.sha256(binary).hexdigest() != NASM_WIN64_SHA256:
        raise ValueError('Archived NASM binary hash mismatch')
    nasm.write_bytes(binary)
    NasmAssembler(nasm)
    return nasm


def _copy_mono_notice(notices):
    """Export one exact selected-API license; this supplies no Mono runtime."""
    original = ROOT / 'dependencies/native/mono-api-source/LICENSE.txt'
    retained = ROOT / 'licenses/MONO-API-SOURCE-LICENSE.txt'
    if original.read_bytes() != retained.read_bytes():
        raise ValueError('Retained Mono API license differs from its pinned original')
    shutil.copy2(retained, Path(notices) / retained.name)


def build(output):
    output = Path(output).resolve()
    files=source_files()
    snapshots={path.relative_to(ROOT).as_posix():digest(path) for path in files}
    notices = output / "notices"
    notices.mkdir()
    for name in ("CT2Trainer-MIT.txt", "Native-THIRD-PARTY.txt"):
        shutil.copy2(ROOT / "licenses" / name, notices / name)
    for package in ('nasm','lupa','iced-x86','libcpp2il-static'):
        shutil.copy2(ROOT/'dependencies/native'/package/'LICENSE.txt',notices/(package.upper()+'-LICENSE.txt'))
    _copy_mono_notice(notices)
    nasm=restore_nasm(output/'native-tools')
    runtime = Path(sys.base_prefix)
    shutil.copy2(runtime / "LICENSE.txt", notices / "PYTHON-LICENSE.txt")
    for package in ("tcl", "tk"):
        local = runtime / "tcl" / (package + "8.6") / "license.terms"
        if local.exists():
            shutil.copy2(local, notices / (package.upper() + "-LICENSE.txt"))
        else:
            # Standard portable Python can omit Tcl's text; checked-in official
            # 8.6 license is retained for that component without network access.
            shutil.copy2(ROOT / "licenses" / (package.upper() + "-LICENSE.txt"), notices / (package.upper() + "-LICENSE.txt"))
    def freeze(entry, name, extra=(), icon=None):
        command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed", "--name", name, "--paths", str(ROOT / "src"), "--distpath", str(output / "bin"), "--workpath", str(output / "pyinstaller" / name), "--specpath", str(output / "spec"), "--add-data", str(notices) + ";native-notices", "--add-data", str(ROOT / "src" / "ct2trainer" / "assets") + ";ct2trainer/assets",
           "--add-data", str(ROOT / "dependencies/native/mono-api-source/api-prototypes.json") + ";dependencies/native/mono-api-source"]
        if icon is not None:
            command += ["--icon", str(icon)]
        for excluded in EXCLUDED:
            command += ["--exclude-module", excluded]
        command += ['--hidden-import','lupa.lua53','--hidden-import','iced_x86',
                    '--hidden-import','ct2trainer.native.il2cpp_static_probe',
                    '--add-binary',str(nasm)+';native-tools']
        for module in ('lua51','lua52','lua54','lua55','luajit20','luajit21'):
            command += ['--exclude-module','lupa.'+module]
        command += list(extra) + [str(ROOT / "tools" / entry)]
        log = output / (name + ".log")
        with log.open("w", encoding="utf-8") as stream:
            subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, check=True)
        return output / "bin" / (name + ".exe")
    assets = ROOT / "src" / "ct2trainer" / "assets"
    template = freeze("native_trainer.py", "CT2Trainer-Template", icon=assets / "ct2trainer-trainer.ico")
    # Only archive-audited Native templates receive this marker. The converter
    # refuses arbitrary PE stubs, including foreign trainer executables.
    inventory(template)
    stub = template.read_bytes()
    template.write_bytes(stub + hashlib.sha256(stub).digest() + b"CT2BASE1")
    converter = freeze("native_converter.py", "CT2Trainer-Converter", ("--add-data", str(template) + ";native-template"), icon=assets / "ct2trainer-converter.ico")
    contents = [inventory(template), inventory(converter)]
    (output / "payload-inventory.json").write_text(json.dumps(contents, indent=2) + "\n", encoding="utf-8")
    if source_files()!=files or any(digest(path)!=snapshots[path.relative_to(ROOT).as_posix()] for path in files):
        raise ValueError('Native source changed during freezing; preserve this run and build a fresh stable snapshot')
    source_readme = f"""CT2Trainer {VERSION} development source

Use Windows x64 Python 3.12. No CE implementation or binaries are included.
Owned C targets and CT fixtures are included; no external trainer code or
third-party game tables are included. User CT rights are separate.

Install build packages with python -m pip install -r requirements-native.txt.
The pinned runtime wheels can also be installed offline from dependencies/native:
python -m pip install --no-index --find-links dependencies/native/lupa --find-links dependencies/native/iced-x86 lupa==2.8 iced-x86==1.21.0

From PowerShell:
$env:PYTHONPATH='src'
python tools/native_build.py restore-nasm --output .tools/native-tools
$env:CT2TRAINER_NASM=(Resolve-Path .tools/native-tools/nasm.exe).Path
python -m unittest discover -s tests -p 'test_native_*.py' -q
python -m ct2trainer.native inspect tests/windows/fixture_target/fixture.ct --process FixtureTarget.exe
python -m ct2trainer.native prepare tests/windows/fixture_target/fixture.ct --process FixtureTarget.exe --output fixture.json
python -m ct2trainer.native run fixture.json
python tools/native_build.py build --output a-new-empty-folder

The game-corpus test skips when TableReferences is absent. The full-checkout
scripts/Build-Native.ps1 additionally needs Python/PyInstaller archives and the
global dependency manifest, which are excluded from this source ZIP.

NASM 3.02 (BSD) and iced-x86 1.21.0 (MIT) supply encoding/relocation. Lupa 2.8
and upstream Lua 5.3 (MIT) supply the language. Pinned source and native runtime
archives are under dependencies/native; preserve the notices under licenses/.
Local forks and library API changes are authorized; contributing upstream is
optional. Retain upstream source pins, license notices and local patch evidence.

Process/module/range AA scans and compact wildcard patterns are separate bounded
operations. Source-reconstructed literal patches in external private RW memory
use opaque live data permits and held publication; disable restores captured bytes.
Lua execution and trusted controller transactions have separate shared budgets.
Restoration operations share one nonrenewable controller budget. Bounded ASCII/
UTF-16LE String writes and Freeze retain exact remote prefixes and do not replay
values. Source-bound literal RW globals use live opaque consumer leases; published
storage remains until exact target exit, with live-close/restart quarantine.
Single printable ASCII instruction literals are encoded without API resolution.
Selected MIT LibCpp2IL sources support static PE/Metadata-v29 inspection only.
The preloaded owned typed target broker and its C fixtures are source foundations;
they do not implement game injection, managed lookup or saved toggle actions.

Executable hooks use Windows debug-event coordination. Physical IP quiescence
has fixture evidence; saved-context/CFG correctness and game compatibility remain
open. Private read-only table helpers and owned Lua records are implemented;
broad async/table forms and remote clock adapters remain in development.
Read documentation/native-runtime.md and native-verification.md for current
gates. Build, usage and derivation notes: documentation/build.md,
documentation/usage.md, documentation/derivation.md. Proton/Steam Deck
protocol: tests/deck/compatibility-matrix.md. Feature matrix:
gap_inventory/feature-coverage.json. Release notes: CHANGELOG.md.
"""
    source_zip = output / f"CT2Trainer-{VERSION}-source.zip"
    with zipfile.ZipFile(source_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(ROOT).as_posix())
        for path in notices.iterdir():
            archive.write(path, "licenses/" + path.name)
        # Release docs: exactly the allowlisted set (RELEASE_DOC_FILES).
        # Dev ledgers, plans and corpus scratch are not part of the
        # release; the single changelog is the only one shipped.
        for name in RELEASE_DOC_FILES:
            path = ROOT / name
            if not path.is_file():
                raise ValueError('Required release doc missing: ' + name)
            archive.write(path, name)
        gitattributes = ROOT / '.gitattributes'
        if gitattributes.is_file():
            archive.write(gitattributes, '.gitattributes')
        archive.writestr("README.md", source_readme)
        archive.write(ROOT / "LICENSE.md", "LICENSE.md")
        requirements = ROOT / "dependencies/python/requirements-build.txt"
        if not requirements.exists():
            requirements = ROOT / "requirements-native.txt"
        archive.writestr("requirements-native.txt", requirements.read_text(encoding="utf-8")+'\nlupa==2.8\niced-x86==1.21.0\n')
        archive.writestr("pyproject.toml", '[build-system]\nrequires = ["setuptools>=68"]\nbuild-backend = "setuptools.build_meta"\n\n[project]\nname = "ct2trainer"\nversion = "'+VERSION+'"\ndescription = "Independent CT converter and Win32 trainer"\nrequires-python = ">=3.12"\ndependencies = ["lupa==2.8", "iced-x86==1.21.0"]\nlicense = {file = "licenses/CT2Trainer-MIT.txt"}\n\n[project.scripts]\nct2trainer = "ct2trainer.native.__main__:main"\n\n[tool.setuptools.packages.find]\nwhere = ["src"]\n')
    portable_zip = output / f"CT2Trainer-{VERSION}-windows-portable.zip"
    with zipfile.ZipFile(portable_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(converter, converter.name)
        for path in notices.iterdir():
            archive.write(path, "licenses/" + path.name)
        archive.write(ROOT / "LICENSE.md", "LICENSE.md")
        archive.write(ROOT / "CHANGELOG.md", "CHANGELOG.md")
        archive.write(output / "payload-inventory.json", "payload-inventory.json")
        archive.writestr("README.md", f"CT2Trainer {VERSION} development build\n\nRun CT2Trainer-Converter.exe. Open a CT, enter the exact target EXE basename, include records and build a trainer EXE. Python and CE do not need to be installed.\nNative assembler/linking, owned Lua53 record activation, private table helpers, exact arrays, coordinated bitfields, bounded ASCII/UTF-16LE Strings and Freeze, bounded process/module/range AA scans, source-bound literal RW data patches and shared RW globals are implemented. Executable hooks use Windows debug-event coordination and source-proven provider literal spans. Published globals remain allocated until target exit; closing a live controller quarantines that session. Single printable ASCII instruction literals are supported; target API resolution remains separate. Static IL2CPP file analysis does not provide a live managed resolver. Broad async/table forms, managed lookup/target invocation and remote speed control remain in development. Explicit recovery is currently available through the source CLI.\nOwned x64/WOW64 fixture validation is separate from games, other PCs, touch and Proton/Steam Deck.\nKeep licenses/ with redistributions. The same notices are embedded in generated trainers. User CT rights are separate.\n")
    report = {"schema": "ct2trainer-repository-build/v1", "version": VERSION, "python": sys.version, "pyinstaller": __import__("PyInstaller").__version__, "ce_inputs": [], "runtime_unverified": True,
              "source_inputs": [{"path": p.relative_to(ROOT).as_posix(), "sha256": digest(p)} for p in files],
              "outputs": [{"file": p.name, "sha256": digest(p), "bytes": p.stat().st_size} for p in (template, converter, source_zip, portable_zip)]}
    (output / "build.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(portable_zip)
    print(source_zip)


def refresh_source(output):
    """Refresh verification prose only; changed implementation needs a fresh build."""
    output = Path(output).resolve()
    archive_path = output / f"CT2Trainer-{VERSION}-source.zip"
    temporary = output / "native-source-refresh.tmp"
    if temporary.exists():
        raise FileExistsError(temporary)
    with zipfile.ZipFile(archive_path) as source:
        names = set(source.namelist())
        if len(names) != len(source.namelist()):
            raise ValueError("Duplicate source archive entry")
        for path in source_files():
            name=path.relative_to(ROOT).as_posix()
            if name not in names or source.read(name)!=path.read_bytes():
                raise ValueError('Native implementation changed since freezing; a fresh build is required: '+name)
    with zipfile.ZipFile(archive_path) as source, zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as target:
        for name in source.namelist():
            path = ROOT / name
            if name in RELEASE_DOC_FILES and path.is_file():
                target.write(path, name)
            else:
                target.writestr(name, source.read(name))
        for name in RELEASE_DOC_FILES:
            if name not in names and (ROOT / name).is_file():
                target.write(ROOT / name, name)
    with zipfile.ZipFile(temporary) as check:
        if check.testzip() is not None:
            raise ValueError("Refreshed source ZIP verification failed")
    temporary.replace(archive_path)
    report_path = output / "build.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    for item in report["outputs"]:
        if item["file"] == archive_path.name:
            item.update(sha256=digest(archive_path), bytes=archive_path.stat().st_size)
    report["source_export_docs_refreshed_after_verification"] = True
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(archive_path)


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("command", choices=("verify-inputs", "restore-nasm", "run-tests", "build", "refresh-source"))
    cli.add_argument("--output", type=Path)
    args = cli.parse_args()
    if args.command == "verify-inputs":
        verify_inputs()
    else:
        if args.output is None:
            cli.error("build requires --output")
        args.output.mkdir(parents=True, exist_ok=True)
        if args.command == "restore-nasm":
            print(restore_nasm(args.output))
        elif args.command == "run-tests":
            run_tests(args.output)
        elif args.command == "refresh-source":
            refresh_source(args.output)
        else:
            build(args.output)
