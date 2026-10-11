# CT2Trainer: Version in Window Titles + Repository Link (WP-17)

## 1. Current state (verified 2026-10-11)

- Converter window title: `CT2Trainer — independent CT converter`
  (`src/ct2trainer/native/converter.py:16`).
- Trainer window title: `<plan title> — CT2Trainer`
  (`src/ct2trainer/native/ui.py:97`, `TrainerWindow.__init__`).
- Neither window shows the build version or the repository link.
- `src/ct2trainer/__init__.py` carries a stale
  `__version__ = "0.9.0-rc2"`; the root `VERSION` file says `0.10`.
  Nothing today keeps the constant in sync with the single version source
  (`tools/native_build.py` line 16: `VERSION` read from the root file).
- The frozen trainer entry point (`src/ct2trainer/native/launcher.py`) ends
  in `from .ui import run_trainer; return run_trainer(plan)`, so a change in
  `TrainerWindow` covers both source-mode and frozen trainers.
- `source_files()` in `tools/native_build.py` already allows
  `src/ct2trainer/__init__.py` and every `src/ct2trainer/native/*.py`; no
  release allowlist change is needed for this feature.
- No existing test pins the window title strings, `__version__`, or a
  repository URL (checked 2026-10-11).

## 2. Requirement (user, 2026-10-11)

1. The version number must appear in the converter window title **and** in
   the produced trainer window, so it can be seen with which version a
   trainer was created.
2. Every copy (converter window and trainer window) must contain the link
   to the GitHub repository: `https://github.com/bietiekay/CT2Trainer`.

## 3. Design decisions (root, 2026-10-11)

1. **Single version source stays the root `VERSION` file.** The runtime
   constant `ct2trainer.__version__` in `src/ct2trainer/__init__.py` is set
   to the current version (`0.10`) and a new fail-closed build check
   `verify_version_sync(version_file=..., init_file=...)` in
   `tools/native_build.py` (called from `build()`, before freeze) raises
   `ValueError` when the constant is missing or differs from the `VERSION`
   file. The function takes injectable paths so it is unit-testable.
2. **No plan schema change.** The trainer displays its own build version;
   converter and trainer ship as one build (the portable ZIP contains both
   EXEs from the same `VERSION`), so the trainer's displayed version is
   exactly the version that created its plan. Plan payload, validators,
   frozen-parity gate and `validate_plan` stay untouched.
3. **Exact title strings:**
   - Converter: `CT2Trainer {v} — independent CT converter`
   - Trainer: `{plan title} — CT2Trainer {v}`
   (em-dash `—` as in the current strings; files are UTF-8.)
4. **Repository link.** Package-root constant
   `REPO_URL = "https://github.com/bietiekay/CT2Trainer"` in
   `src/ct2trainer/__init__.py`. A small shared helper module
   `src/ct2trainer/native/about_ui.py` provides:
   - `converter_title() -> str` and `trainer_title(plan_title) -> str`
     (pure string functions, importable without Tk);
   - `repo_link(parent, **label_options) -> tk.Label` — a label whose text
     is `REPO_URL`, `cursor="hand2"`, with `<Button-1>` bound to
     `webbrowser.open(REPO_URL)` (stdlib only).
   Placement:
   - converter: `bottom` frame, packed `side="right"`;
   - trainer: `header` frame, packed `side="right"` **after** the Close
     button so it sits to the left of Close.
5. **Styling** follows each window's existing conventions (converter:
   ttk; trainer: tk with the module's `BG`/`FG` palette — link label uses
   `FG` on `BG_HEADER` in the header).

## 4. Lane ownership

Files the lane owns (exactly):

- `src/ct2trainer/__init__.py` — set `__version__ = "0.10"`, add
  `REPO_URL`.
- `src/ct2trainer/native/about_ui.py` — new helper module (titles + link
  widget).
- `src/ct2trainer/native/converter.py` — title via helper; repo link in the
  bottom frame.
- `src/ct2trainer/native/ui.py` — title via helper; repo link in the header
  frame.
- `tools/native_build.py` — `verify_version_sync()` + call from `build()`.
- `tests/test_native_version_display.py` — new dedicated test file.

Zero changes to: plan schema/validators, `compiler.py`, `engine.py`,
`bundle.py`, `gap_inventory/*`, `TableReferences/`, `plans/*`,
`documentation/*`, any existing test file.

## 5. Acceptance

- `tests/test_native_version_display.py` covers at minimum:
  1. `ct2trainer.__version__` equals the root `VERSION` file content
     (stripped).
  2. `REPO_URL` is exactly `https://github.com/bietiekay/CT2Trainer`.
  3. `converter_title()` == `"CT2Trainer " + __version__ +
     " — independent CT converter"`.
  4. `trainer_title("Demo")` == `"Demo — CT2Trainer " + __version__`.
  5. `repo_link(...)` with `tk.Label` patched: the created label carries
     `text == REPO_URL`, `cursor == "hand2"`; invoking the bound
     `<Button-1>` handler calls `webbrowser.open(REPO_URL)` (`webbrowser`
     patched; assert called once with the URL).
  6. `verify_version_sync()`: matching pair passes; drifted version and
     missing constant each raise `ValueError` (injectable temp paths).
- Focused suite green; full suite green at the lane base (2688 OK / 25
  skips) plus the new tests, zero failures — except the three known
  worktree provenance failures when run off-canonical (see §6).
- `verify_version_sync()` passes on the working tree as committed.
- Integration (root agent): canonical-path full suite, suite-baseline
  updates in `documentation/native-verification.md` and
  `documentation/native-progress.md`, WP-17 row in
  `plans/native-implementation-continuation.md` §5, worktree/branch
  cleanup, push.

## 6. Known worktree caveat

Off-canonical worktrees fail exactly three provenance byte-identity tests
(`test_committed_manifest_is_byte_reproducible`,
`test_02_feature_matrix_reproduces_feature_coverage`,
`test_03_ap11_reproduces_campaign_manifest`) because they embed the
worktree path. They are NOT to be "fixed" in the lane; root re-runs the
full suite at the canonical path at integration.

## 7. Log

| Date | Change / next checkpoint | Evidence / open work |
| --- | --- | --- |
| 11.10.2026 | WP-17 plan | base `main` @ `42464d1` (0.10, after WP-15 merge `d3316aa`) |
