# CT2Trainer: Named Table-Lua Tabs (WP-16, L5-19)

**Status:** Implemented (2026-10-11) on branch `wp16-tablua` @ `38a830d`
(commits `3a81af0`, `38a830d`) — Baseline: `main` @ `af7f099` (0.10, suite
2671 OK / 25 expected skips)

Closes **L5-19** from the CE7.5 comparison: the table-Lua section can hold
several **named script tabs** in addition to the main body, combined at
load time. Today the product *detects* any descendant text of
`<LuaScript>` (`table.py:457`, `itertext()`) but the compiler only prepares
the **direct section text** (`compiler.py:397`,
`root.findtext('LuaScript')`) — so named tabs in real-world tables are
silently dropped. The pinned corpus has no such tab, so there is no corpus
impact today; this closes a real load-path gap for real tables.

## 1. Current state (verified 2026-10-11)

- `table.py:456-457`: `lua = root.find("LuaScript")`;
  `has_table_lua = lua is not None and bool("".join(lua.itertext()).strip())`
  — detection already counts named-tab child text (correct).
- `compiler.py:395-397`: `if table.has_table_lua:` →
  `prepare_lua_bootstrap(root.findtext('LuaScript') or '')` — direct text
  only; child-element (tab) text is dropped.
- `lua_bootstrap.py`: `prepare_lua_bootstrap(source: str)` parses one source
  string into the bootstrap profile; `validate_lua_bootstrap` re-derives
  and tamper-refuses it at trainer load. The bootstrap profile already
  travels as plan data (no new plan fields needed).
- Runtime replay of read-only helpers per Lua activation already works for
  whatever the bootstrap profile contains — no engine change expected.
- Pinned corpus: every `TableReferences/*.ct` table-Lua section (where
  present) is a single direct body with **zero** child elements under
  `<LuaScript>` — lane must verify by grep before changing behaviour.

## 2. Contract (clean-room, derived from the public format contract)

- The table-Lua source is the concatenation, in this order, of:
  1. the `<LuaScript>` **direct text** (main body),
  2. then, in **document order**, the full text
     (`"".join(el.itertext())`) of every **direct child element** of
     `<LuaScript>` (each one a named tab).
- Empty/whitespace-only parts are skipped; parts are joined with a single
  newline separator.
- The combined source must be valid Lua; if preparation fails, the same
  named fail-closed compile error applies as today (no new error class).
- `has_table_lua` semantics in `table.py` are unchanged (already
  descendant-text based).
- No changes to the plan schema, validators, bundle, converter UI, or the
  `gap_inventory/` artifacts.

## 3. Scope decisions (root, 2026-10-11)

1. Gather is a compiler concern: implement it as a small helper in
   `src/ct2trainer/native/compiler.py` used at the single preparation site
   (`compiler.py:397`). `table.py` is unchanged unless verification shows
   the detection needs a fix (it does not).
2. No attempt to interpret tab names for ordering or gating; document
   order only (CE combines tabs at load time; the product keeps the
   profile closed and deterministic).
3. The "Table Lua is not executed on load..." warning (compiler.py:706-707)
   stays as-is; if named tabs are present, the existing warning covers it.
4. Zero corpus impact: no `gap_inventory/*` changes, feature matrix and
   AP-11 manifest unchanged.

## 4. Lane ownership

- Branch `wp16-tablua` cut from `native-l5-19`; worktree
  `C:\Users\xboxl\AppData\Local\Temp\opencode\wp16-tablua`.
- Touchable: `src/ct2trainer/native/compiler.py`,
  `tests/test_native_table_lua_tabs.py` (new).
- Root-owned (do NOT modify; report needed updates in the final report):
  everything else, including `plans/*`, `documentation/*`,
  `gap_inventory/*`, `CHANGELOG.md`, `AGENTS.md`, `TableReferences/*`,
  and **`src/ct2trainer/native/engine.py`** (owned concurrently by the
  WP-15 lane — if the gather turns out to require an engine/runtime change,
  STOP and report instead of touching it).
- No new third-party dependencies; no pushes; no commit to `main`.

## 5. Acceptance

- New `tests/test_native_table_lua_tabs.py` (synthetic tables, no corpus):
  - main-body-only table → bootstrap source **byte-identical** to today's
    `findtext` behaviour (regression guard);
  - main body + one named tab → combined source in document order, tab
    helper functions present in the prepared profile;
  - tabs only (empty main body) → bootstrap from tabs only;
  - whitespace-only tab parts are skipped;
  - a record Lua activation can use a helper defined in a named tab
    (end-to-end replay, reusing the existing table-Lua replay fixtures);
  - a syntactically invalid tab → named compile error, fail-closed, no
    partial plan.
- Full suite green at the canonical path; in the worktree only the three
  known provenance byte-identity tests may fail (see §6).
- `git diff --stat` against the branch base shows **no** `gap_inventory/*`
  changes and no `TableReferences/*` changes.

## 6. Known worktree caveat

In any non-canonical worktree, exactly three tests fail because the
committed artifacts embed the canonical absolute paths:
`test_committed_manifest_is_byte_reproducible`
(`tests/test_native_repro_chain.py`),
`test_02_feature_matrix_reproduces_feature_coverage`
(`tests/test_native_feature_matrix.py`),
`test_03_ap11_reproduces_campaign_manifest`
(`tests/test_native_ap11_campaign.py`). Verified 2026-10-11 in a scratch
worktree (43/46 OK, exactly those three fail). Do **not** try to "fix"
them in the lane; root re-runs the full suite at the canonical path at
integration.

## 7. Log

| Date | Change / next checkpoint | Evidence / open work |
| --- | --- | --- |
| 11.10.2026 | WP-16 plan; L5-19 gap confirmed (detection vs preparation mismatch at `table.py:457` / `compiler.py:397`) | baseline `main` @ `af7f099` (0.10) |
| 11.10.2026 | WP-16 implemented: `_table_lua_source(root)` gather in `compiler.py` (single call-site swap), 8 new tests in `tests/test_native_table_lua_tabs.py`; pinned corpus verified free of `LuaScript` child elements; zero `gap_inventory/` impact | lane `wp16-tablua` @ `38a830d` (commits `3a81af0`, `38a830d`); canonical-path suite 2679 OK / 25 skips |
