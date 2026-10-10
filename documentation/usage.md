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

## 5. Final acceptance

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
