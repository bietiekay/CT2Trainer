# CT2Trainer usage guide

Status: October 10, 2026.

This guide describes the product behavior of CT2Trainer, the independent
CT converter and Windows trainer, for private own use. It is
self-contained: no development ledgers are referenced.

## 1. Required inputs

CT2Trainer requires exactly two inputs:

1. a **`.CT` table file** (a Cheat Engine table in its XML format), and
2. the **exact game process EXE name** (basename) the trainer must attach
   to.

You produce a trainer either with the portable converter
(`CT2Trainer-Converter.exe` from the portable ZIP — no Python or CE
installation is needed; open the CT, enter the exact target EXE basename,
select the records and build a trainer EXE) or with the source CLI:

```bat
python -m ct2trainer.native inspect <table>.CT
python -m ct2trainer.native prepare <table>.CT --process <target>.exe --output build\fixture
python -m ct2trainer.native build <table>.CT --process <target>.exe --output build\out --architecture x64
```

`prepare` only produces a JSON plan; a plan or its hash grants no target
write permission. The trainer re-proves the target identity (PID/creation
time, remote PE, architecture, ownership, current bytes/regions) before
any mutation.

## 2. Saved toggles (state contract)

- **Saved enabled toggles are automatically re-enabled after a successful
  re-attach** (target restart or trainer restart, on a freshly verified
  target identity).
- **Only confirmed ON-switches are persisted.** A switch is saved only
  after its enable was independently confirmed.
- **A failed enable attempt stays visibly inactive** and is **not repeated
  as a saved wish** on the next attach. Irreversible one-time calls never
  receive a faked OFF/save/reapply contract.

## 3. Table loading semantics

- Original-table Lua and Auto Assembler code **may execute when a table is
  loaded** by the trainer runtime (owned Lua records, returned-AA
  activation, table bootstrap code).
- The **local inspector does not execute it**: `inspect` is a static,
  read-only analysis of the table structure.

## 4. Stale-session recovery (source CLI)

If a previous session left a stale state lock, the source CLI offers
explicit recovery (assessment performs no mutation; recovery archives and
releases held stale file objects only after proving the owner and all
recorded target identities dead):

```powershell
python -m ct2trainer.native assess-recovery plan.json --state-dir <state> --process-lock-dir <shared>
python -m ct2trainer.native recover plan.json --state-dir <state> --process-lock-dir <shared> --archive-dir <fresh-evidence>
```

A new trainer must still attach to a freshly verified target before
applying saved switches.

## 5. Debug logging (optional)

The converter offers an optional **debug logging** option (checkbox in the
converter GUI, `--debug-log` flag in the source CLI). When enabled, the
generated trainer writes an append-only log file with one JSON line per
runtime event:

- **Location:** next to the trainer EXE, named
  `<TrainerName>.ct2debug.log` (source runtime:
  `ct2trainer-debug.log` in the working directory).
- **Contents:** plan identity at startup (trainer ID, process, state
  directory, saved wishes), every attach attempt and refusal (process not
  found, architecture mismatch, state conflicts, call broker), confirmed
  attaches (PID, EXE path, pointer width), every AOB scan (symbol, module,
  pattern, module base, RVA, result), definitions, symbol registrations,
  byte assertions (with expected vs. actual bytes on failure), every patch
  write (address, original and new bytes, read-back verification), all
  toggle/value/freeze attempts, wish replay on attach, state saves, and
  clean or unclean shutdown.
- **Errors** are logged with exception type, message and full traceback.

Logging is best-effort: a failed log write never changes trainer behavior,
and without the option no log file is created at all. The option does not
change plan identity (trainer ID) or state directories, so a log-enabled
trainer stays compatible with state created by a standard trainer.

## 6. Final acceptance

Final acceptance is **separate on Windows and on a real Steam Deck under
Proton with touch operation**; fixture tests and a green build do not
replace either measurement. After new Windows or Deck tests, **record the
observed build (versions, hashes, test setup, and result) in the
documentation before raising the status.**

Test protocols:

- [Proton / Steam Deck protocol](../tests/deck/compatibility-matrix.md) —
  the D0/D1 run sheets, prefix/runtime identity, process effect and touch
  measurement under Proton.
- [Own Windows test target](../tests/windows/fixture_target/README.md) —
  the self-owned `FixtureTarget.exe` console process and `fixture.ct` used
  for the Windows function gates.
