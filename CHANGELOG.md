# CT2Trainer Changelog

Single maintained changelog for CT2Trainer releases.

## 0.47 (2026-11-14)

Optional code signing for the frozen and generated trainer
executables (Smart App Control handling, the field block observed
2026-11-14 on the 0.46 trainer): Smart App Control (Windows Security)
refuses unsigned binaries by their binary hash, offers no per-app
"allow" option, and on Windows 11 turning it off is a one-way switch
- the durable fix is an Authenticode signature from a code-signing
certificate issued by a trusted public CA (OV or EV; a self-signed
certificate does not clear Smart App Control). The new pure layer
`src/ct2trainer/native/code_signing.py` wires that optional step
everywhere an EXE is produced, configured through environment
variables only (never persisted): `CT2TRAINER_SIGN_PFX` (the PFX
certificate store file), `CT2TRAINER_SIGN_PFX_PASSWORD`, optional
`CT2TRAINER_SIGNTOOL` (explicit signtool.exe, default discovery under
the Windows SDK bin roots, highest version wins) and
`CT2TRAINER_SIGN_TIMESTAMP_URL` (default
`http://timestamp.digicert.com`). `tools/native_build.py` signs
`CT2Trainer-Converter.exe` and `CT2Trainer-Master.exe` after freezing
(the template stub is deliberately NOT signed: it is never run
directly, and a certificate table after its `CT2BASE1` trailer would
break the converter's template check) and reports the per-EXE signing
facts in `build.json` under `code_signing`; `bundle.build_trainer`
signs every generated trainer before publication (the `sign` keyword
is the injectable test seam, defaulting to the environment-driven
`sign_if_configured`), and the trainer `.build.json` gains the
`signed` flag. Signing is signtool `sign /v /f <pfx> [/p <pwd>] /fd
SHA256 [/tr <url> /td SHA256] <path>` (bounded 300 s timeout, stdout
captured), and after a reported success the certificate table of the
PE is re-proven by the pure `certificate_table` security-directory
walk (WIN_CERTIFICATE revision 0x0200, certificate type 0x0001,
declared length equal to the security directory size) - so a signed
file is never shipped unproven. Fail-closed named refusals:
`sign-not-win32`, `sign-signtool-unavailable`,
`sign-certificate-missing`, `sign-failed`,
`sign-verification-failed` - a configured signing that fails refuses
the build / the trainer generation, it never ships an unsigned
binary. `bundle.read_embedded_plan` no longer assumes the footer at
the end of the file: a bounded backwards `CT2NATV1` magic scan (tail
window 1 MiB, the documented certificate-tail bound) where every
candidate is proved against the plan checksum, so the plan survives
the certificate table that signtool appends after the footer; a magic
occurrence inside the tail that does not verify is skipped, never
accepted, and a tail beyond the window is the named refusal. Without
`CT2TRAINER_SIGN_PFX` nothing is signed and every produced byte is
identical to the unsigned flow. +37 tests (new
`tests/test_native_code_signing.py` 32: config resolution, named
refusals, SDK discovery, argv construction, the signtool seam over
injected runners, the synthetic-PE certificate-table walk,
sign-and-verify fail-closed; `tests/test_native_bundle.py` +5:
certificate-tail roundtrip, fake-magic-in-tail, bounded-scan refusal,
signing wiring + report flag). The user guide gains section 8
"Windows Security (Smart App Control)" (the two documented options:
code-sign with a trusted-CA certificate, or the one-way
SAC-off switch; trainers generated before a certificate was
installed must be regenerated) and the build guide the optional
code-signing section; the portable ZIP README carries the same user
notes. Catalog delta none - the change touches no table-parsing path.

- Build: 0.47 released as run
  `native-20261114T011046Z-ee5cecee` (cut from `main` @
  `6e1940e`, 2026-11-14): in-build suite 5,108 OK / 36
  expected skips, 0 failures - fully green at the canonical
  build path, `ce_inputs: []`, `runtime_unverified`
  deliberately kept per gate. The build ran unsigned by
  default (no certificate on this machine; `code_signing`
  report: converter / master signed false, reason
  not-configured) - the signed path activates with a
  user-supplied trusted-CA PFX. Source ZIP
  `CT2Trainer-0.47-source.zip` sha256
  `436a330aeceb70a51c2fc5585085a133b25ea6f05aedcdfa25353aa9042d436d`
  (14,675,788 bytes) - carries the code-signing package
  (`code_signing.py` +
  `tests/test_native_code_signing.py` + the bundle
  footer-scan) and the SAC user docs (`usage.md` section 8,
  `build.md` section 3) - and portable ZIP
  `CT2Trainer-0.47-windows-portable.zip` sha256
  `146ee9cd99a12865779ba1daff9e66fa0855be20a7a847d0bd47a513e74bc3a5`
  (49,879,105 bytes; the frozen `CT2Trainer-Master.exe`
  (sha256 `a770f9689a5744a49aa26ec911437f0fcd09a05631e85edcfea92061b6658453`,
  17,066,832 bytes) ships next to the converter).

## 0.46 (2026-11-13)

AA extended-register `l` alias + `dqword` size-keyword parity
(compatibility lane against the 221-row post-0.44 census): the nine
direct "Required symbol" rows of the CE register / size spellings
the clean-room token sets did not admit - seven `rXl` low-dword
register spellings (DS2 `r13l`, HellPie / RAGE2 / Sinking City
`r15l`, SOTTR `r8l` + `r11l`, YakuzaLikeADragon `r9l`) and two
`dqword` 128-bit operand-size spellings (Fallout4, SOTTR) - were
blocked because CE `TSingleLineAssembler.getreg` (Assemblerunit.pas)
accepts the `l` 32-bit alias R8L..R15L and CE `dqword` is the
128-bit operand size, while the pinned NASM 3.02 assembles neither
spelling.  Recognition - `r8l`..`r15l` join the register set and
`dqword` the size-keyword set - drops the tokens out of every
program's symbol requires; the NASM source generation normalizes
the CE spellings to the NASM spellings they map to (`rXl` ->
`rXd`, `dqword` -> `oword`, the same 128-bit size CE's `xmmword`
already maps to) via the new bounded `_CE_TO_NASM_SPELLING` table.
Byte correctness is proven through the pinned NASM: `mov r13l, eax`
assembles byte-identically to `mov r13d, eax` (`41 89 C5`, the
REX.B low-dword encoding) and `movdqu dqword [rsp], xmm0` to
`movdqu oword [rsp], xmm0` (`F3 0F 7F 04 24`).  +9 tests in
`tests/test_native_aa_register_aliases.py` (recognition,
normalization, symbol-requirement and byte-identity).  Full main
suite 5,071 OK / 36 expected skips.  Catalog remeasure
`blocked-catalog-046-regsize`: 117,809 total / 117,599 supported /
12,974 headings / 104,450 actionable / 210 blocked (net -11 vs
`blocked-catalog-lane-b`: exactly 11 rows unblocked - the 9 direct
register / size rows plus 2 provider cascades, Fallout4 record
1057 (`fZoomIntevalMultiplier`) and SOTTR record 15385
(`dMinHealth`), whose symbol providers are the two now-supported
dqword records; zero newly blocked, zero reason changes, the other
147 tables byte-identical).

- Build: 0.46 released as run
  `native-20261113T185658Z-e543af1a` (cut from `main` @
  `b348184`, 2026-11-13): in-build suite 5,071 OK / 36
  expected skips, 0 failures - fully green at the canonical
  build path, `ce_inputs: []`, `runtime_unverified`
  deliberately kept per gate. Source ZIP
  `CT2Trainer-0.46-source.zip` sha256
  `c49323d56d8feab0652f676d86a739fb6204cff6ddeed8e4b326e43020ee4d62`
  (14,661,247 bytes) - carries the AA extended-register /
  size-keyword parity lane (`aa_program.py` +
  `tests/test_native_aa_register_aliases.py`) - and portable
  ZIP `CT2Trainer-0.46-windows-portable.zip` sha256
  `1b130db71508e42b98c4127ebcec766bc79cd65aabdd563ed59d4b058bfc9fe9`
  (49,857,331 bytes; the frozen `CT2Trainer-Master.exe`
  (sha256 `18306034231d6632ba15f4f23f62e611dd2c9b73e14db634d99f6cdccb7e8857`,
  17,069,499 bytes) ships next to the converter).

## 0.45 (2026-11-13)

Per-session hotkey management (MT-34) + the trainer-tick-sound field
fix. (MT-34, the WeMod QoL from the 0.43 candidate list, adopted as
the 0.45 candidate): the trainer header gains one control, "Hotkeys:
on/off", in every trainer (standalone + Master - no header
byte-identity test exists; the label mirrors the state and the poll
tick keeps it in sync).  Off releases every published hotkey binding
for the session: the engine's `_hotkey_sync` reconciles the model
controller to an empty live set and releases the OS bridge mirror,
and nothing new is published while off; on re-publishes the
table-declared hotkeys of the live records in activation order - the
table's defaults, since no per-record override surface exists.  The
plan-level bindings are never mutated, the state is session-scoped
and never persisted (a fresh engine starts on), the ordinary toggle /
dispatch paths stay fully functional while off, and the row hotkey
display shows the live registration state; the switch logs a
`hotkeys-session-switched` debug event.  +10 tests in
`tests/test_native_hotkey_session_switch.py` (engine + real-Tk UI).
(Sound field fix, 2026-11-13): the stdlib winsound `PlaySound`
wrapper raises
`RuntimeError("Cannot play asynchronously from memory")` for
`SND_MEMORY | SND_ASYNC`, so every on / off / attach tick silently
failed in the field (swallowed by the never-raises guard, returned
"refused: audio unavailable").  Playback now goes through
`winmm.PlaySoundW` directly via ctypes (the house attribute-access
binding pattern, see `hotkey_bridge`) against one persistent
per-kind buffer, with named refusals ("refused: winmm unavailable"
/ "refused: PlaySoundW failed (Win32 <code>)"); the reworked
`tests/test_native_trainer_sounds.py` PlaybackTests mock the binding
seam, not the OS call (+3 tests, incl. a live winmm smoke that
accepts "played" or a named refusal and never raises). Full main
suite 5,062 OK / 36 expected skips. Catalog unchanged at 117,809
total / 117,588 supported / 221 blocked (MT-34 and the sound fix
touch no table-parsing path; the MT-9 gate re-checks each table
independently at load time).

- Build: 0.45 released as run
  `native-20261113T144426Z-572d5b30` (cut from `main` @ `58d6c8f`,
  2026-11-13): in-build suite 5,062 OK / 36 expected skips, 0
  failures - fully green at the canonical build path,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate.
  Source ZIP `CT2Trainer-0.45-source.zip` sha256
  `3bdd783359623d273de15e90f4f0acc524d3ecbda64f925c3cf59de9d4e27416`
  (14,657,388 bytes) - carries MT-34 (`engine.py` +
  `ui.py` + `tests/test_native_hotkey_session_switch.py`) and the
  trainer-tick-sound field fix (`trainer_sounds.py` +
  `tests/test_native_trainer_sounds.py`) - and portable ZIP
  `CT2Trainer-0.45-windows-portable.zip` sha256
  `58bac73098b219e3049668b55877e8a3e4fd758e6e1917b058da128e416eb4e2`
  (49,854,120 bytes; the frozen `CT2Trainer-Master.exe` (sha256
  `f882add64b2fc0f9d66cb88ed2142684e71736de326b28f72ddb007186aa2d05`,
  17,069,125 bytes) ships next to the converter).

## 0.44 (2026-11-13)

The deferred compatibility-lane cycle against the 537-blocked
post-0.43 census - the three lead cases, all closed on `main`.
(Lane C, roadmap class d, test-only; merged as `7d92482`): the
80 `BaseAddress` rows of the five UE5 script-template tables
(16 per table) are blocked by design until the user imports the
symbol, and the documented `<UserdefinedSymbols>` import path is
proven end-to-end - with the entry the same rows are fully
supported (not staged; static UDS address,
`requires=['BaseAddress']`), byte-exact through the engine,
while the as-is rows keep the exact named class-d block (the
block message names the remedy); catalog zero delta
`blocked-catalog-lane-c`. (Lane A; merged as `ff6e8d6`): the
182 rows of the two dynamic Lua symbol registration shapes -
the Witcher3 returned-define shape (the ENABLE Lua returns a
`define(<ident>, <expr>)` string spliced into the AA section
per the CE contract, so the record's own envelope may reference
the defined symbol: the adopted idents leave `requires`,
recorded in the deterministic `lua_define_symbols` plan
marker, expression position only - a bare `name:` label keeps
the program-owned contract) and the GoW literal name-list
shape (the bounded derivation of the constant-string column
registered through the exact `X[i][k]` indexed call argument;
the same register-and-release rule as the WP-14 extraction;
>64 names stay unproven) - plus the runtime hosting of the
registration path (`AOBScanModuleUnique`, `stringToByteTable`,
`getUpdateTimer`, `createDisassembler`, `getNameFromAddress`,
the bounded in-memory `createTableFile` stream, the inert
`GetLuaEngine` show/hide / Component surface). (Lane B; merged
as `285fb8a`): the 134 rows of the Octopath2 relative-address
census - the staging walk now folds relative ancestors into
the chain whether or not they carry pointer offsets, and the
record's own pointer offsets no longer block staging; while
every level is a plain-hex relative literal with no pointer
offsets anywhere the byte-stable flat signed-hex total is kept
(the RT-4.3 O9/O1 form, unchanged), otherwise the chain folds
through the deterministic synthetic symbol
`__ct2_rtbase_<anchor_id>` (plan metadata, never a dependency;
the engine injects the anchor heading's live base per
activation call, a registered symbol under the placeholder name
is the named fail-closed collision; intermediate headings are
never staged, and addressless headings with pointer offsets
keep the byte-for-byte ambiguous-base refusal). Catalog
remeasure `blocked-catalog-lane-b`: 117,809 total / 117,588
supported / 12,974 headings / 104,439 actionable / 221 blocked
(net -316 vs `blocked-catalog-043-tgc`: 182 + 134 unblocked,
zero newly blocked, zero reason changes; exactly the 4 lane
tables changed, the other 147 byte-identical). Full main suite
5,049 OK / 36 expected skips. The remaining 221 blocked rows
are the documented design / gate residuals (80 `BaseAddress`
by design until the documented user import, 79 required
symbols not defined in their table, 23 no-unique-supported-
provider, 11 KeyHandlerThread WP-37 external ownership, 6 RE2
AP-08.7 custom value types, 5 trailing-token, 4 usemono > 7.5
out of parity scope, 2 + 2 relative-ancestor refusals kept by
design, 2 createthread / threadWait RT-5G, 1 pBase Cronos, 6
single-row named AA-syntax / DISABLE re-init refusals); AP-11
stays open by definition (0/6,143).

- Build: 0.44 released as run
  `native-20261112T233337Z-1dc678c6` (cut from `main` @ `ab11893`,
  2026-11-13): in-build suite 5,049 OK / 36 expected skips, 0
  failures - fully green at the canonical build path,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate.
  Source ZIP `CT2Trainer-0.44-source.zip` sha256
  `026886a700282a56c40568f30d2a4ebc57d6390a59cd59c42fd3f7f5dc8d49ff`
  (14,648,668 bytes) - carries the deferred compatibility-lane
  cycle (Lane C `tests/test_native_baseaddress_import.py`, Lane A
  `lua_program.py` + `lua_symbol_providers.py` +
  `tests/test_native_lua_define_providers.py` +
  `tests/test_native_lua_name_list_providers.py`, Lane B
  `compiler.py` + `engine.py` +
  `tests/test_native_staged_pointer_chain.py`) - and portable ZIP
  `CT2Trainer-0.44-windows-portable.zip` sha256
  `656bf7106fd86a5a21532cf476b91f82cfafe2287ef5bf3d3ba41b6d2d9d6f36`
  (49,885,729 bytes; the frozen `CT2Trainer-Master.exe` (sha256
  `02e4731ef30ce320f71594f37cb176402be64849a90656c785d474dbc50d6112`,
  17,084,284 bytes) ships next to the converter).

## 0.43 (2026-11-11)

Master Trainer minimize-to-tray + window-geometry persistence
(MT-32/MT-33) + the TGC field fix (transient target-memory reads no
longer block the engine). (MT-32) Minimize-to-tray: the Master
Trainer can minimize into the system tray and restore on tray
double-click - `master_trainer/tray.py` drives the Win32 tray icon
(`Shell_NotifyIconW` / `RegisterClassExW` bound through
`_bind_prototypes` with pointer-sized WPARAM/LPARAM) behind a bounded,
named fail-closed guard: a Windows build without the
`Shell_NotifyIconW` export (stripped user32, the Sinking City 2 0.22.1
precedent) or a refused `RegisterClassExW` (Win32 87) is the named
`tray-platform-unavailable` / `tray-icon-missing` / `tray-setup-failed`
refusal in the status line - never a crash and never a dialog; the
persisted "Minimize to tray" toggle (master-state schema 9 -> 10,
`tray_minimize`) restores on start and persists on change, and the
tray balloon reports the trainer's attach success / failure through
the new `ui.py` `attach_observer` (fail-safe `_fire_attach_observer`,
standalone trainer unchanged). (MT-33) Window-geometry persistence:
the Master window's size / position is remembered across restarts -
`master_trainer/window_geometry.py` pure layer, persisted in the same
master-state document (schema 10, `window_geometry`), saved on the
bounded `<Configure>` cadence and on close (`_save_geometry` /
`_save_final_geometry` with defensive winfo guards so a half-destroyed
window never writes a bogus rect), and an invalid persisted geometry
is the named `window-geometry-invalid` refusal (the default geometry)
rather than a crash. (TGC field fix) the 2026-11-11 Indiana Jones and
the Great Circle (0.41) field log exposed two transient-read dead
ends: R1 the module snapshot failed with Win32 299
(ERROR_INTERNAL_ERROR) immediately after the first attach while the
game was still loading its DLLs - 299 was not in the snapshot
transient retry set, so the engine blocked with no retry and the
stuck engine refused a close while the target lived; R2 a transient
299 read during the periodic `_check_patches` was wrapped as "An
executable hook receipt changed" -> `PatchConflict` -> engine
blocked.  A failed read is not an observed change.  Fixes: F1
(memory.py) 299 joins the bounded snapshot transient retry (8
attempts, 0.05 -> 1.0 s backoff), every `_windows_error` carries a
machine-readable `win32_code`, and the public
`TRANSIENT_MEMORY_ERRORS` / `is_transient_memory_error()` classify a
read failure as "cannot verify right now" (never "bytes changed");
F2 (engine.py) a transient read in the periodic `_check_patches` now
skips that verification tick instead of blocking - a bounded skip
streak (`VERIFY_SKIP_STREAK_LIMIT = 30` consecutive ticks), a deduped
`patch-verify-skipped` debug event (reported once per distinct cause,
reset on a verified tick and on every confirmed (re-)attach), and a
persistent streak is the named fail-closed refusal "Patch
verification failed on transient read errors for 30 consecutive ticks
(last: ...); the engine blocks to stay fail-closed."; a real byte
mismatch and a non-transient failure still block immediately (the
non-transient hook-read refusal is now the more specific "An
executable hook receipt could not be verified: ..."); F2b (hooks.py)
a transient guard read in `_check_allocation_guards` re-raises instead
of marking the manager uncertain (which would be a permanent
fail-closed state). +85 tests (new
`tests/test_native_master_tray_geometry.py` 62 incl. the correctly
session-skipped `Shell_NotifyIconW` smoke test, the master
UI / state updates, new `tests/test_native_tgc_field_fix.py` 17, 3
architecture snapshot tests adapted for the 299-retry contract + 1 new
299 retry test); full main suite 5,011 OK / 36 expected skips; catalog
remeasure `blocked-catalog-043-tgc`: 117,809 total / 117,272
supported / 12,974 headings / 104,123 actionable / 537 blocked - zero
delta vs `blocked-catalog-042-cleanup` (3-chunk record-level delta
audit: 0 newly blocked, 0 unblocked, 0 reason changes, 0 tables
added / removed).

- Build: 0.43 released as run
  `native-20261111T184600Z-3bf9d8aa` (cut from `main` @ `0df2607`,
  2026-11-11): in-build suite 5,011 OK / 36 expected skips, 0
  failures - fully green at the canonical build path,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate.
  Source ZIP `CT2Trainer-0.43-source.zip` sha256
  `c0011d10a5a60b78067b0cdd1a622a134088fee325ac4d544efd3ec8101438ca`
  (14,617,762 bytes) - carries the MT-32/MT-33 tray + geometry
  (`master_trainer/tray.py` + `master_trainer/window_geometry.py` +
  `tests/test_native_master_tray_geometry.py`) and the TGC field fix
  (`memory.py` + `engine.py` + `hooks.py` +
  `tests/test_native_tgc_field_fix.py`) - and portable ZIP
  `CT2Trainer-0.43-windows-portable.zip` sha256
  `dc7a4062b56be99ea887a77ffd23e7c2c1ff38935e471d7f124ed4d775a022e9`
  (49,849,139 bytes; the frozen `CT2Trainer-Master.exe` (sha256
  `4846d7568ef4eba091261b21e678c13ab5cecbbf3468a0a57ba30d84fc7e91a4`,
  17,072,494 bytes) ships next to the converter).

## 0.42 (2026-11-11)

CE 7.5 cleanup parity + the API-export registry extension — the two
remaining bounded compatibility classes of the 805-row root-cause
census. (B) Cleanup parity: a disable-phase cleanup name that NO
program owns is a silent no-op in CE 7.5 (`autoassembler.pas`
L2492-2525 `unregistersymbol` appends it to the deletion list without
an ownership check; L2625-2669 `dealloc` searches only this program's
allocation set, read-only reference) — CT2Trainer now matches it: the
name is dropped from the program node and recorded in the new program
field `unowned_cleanup_dropped` (sorted, deduped, casefold) instead of
refusing the program, and the record stays supported. A name
live-registered by another supported record keeps the WP-37 handover
refusal — the owning record releases that symbol exactly once on its
own deactivation, so a second release from a foreign program is a
real cross-record hazard, not a CE no-op. Because the first-pass entry
compile runs without the table-wide ownership context, the drop is
only provisional there: a plan-level re-check (compiler, after the
Wave B1 loop) re-blocks a first-pass-supported record when one of its
dropped names is (a) a WP-37 handover name (record-Lua
registerSymbol/unregisterSymbol pairs or allocation-only programs —
the owner may be the record itself, whose record-Lua registration is
invisible to its static program) or (b) in any other supported
record's entry-level `provides` (luaCall AOB symbols, ordinary AA
registrations) — with the named single-form reason "Program may not
unregister or deallocate the externally owned symbol X (owned by
record N)." (the "Static AA envelope: " prefix kept for envelope
records); the old Wave B1 doubled-composite reasons no longer occur.
(C) API-export registry: the bounded Windows API export registry
(RT-4.2 R7) gains `sleep` (kernel32.dll) and `showwindow`
(user32.dll) — the corpus thread idioms (HorizonForbiddenWest
records `mov rcx,10 / call Sleep`; APlagueTaleRequiem / Resonance
console-open threads `call ShowWindow`) now resolve with the exact
`api_exports` marker, the same contract as the existing user32
entries (requires == [export], link-time resolution against the
target's live PE export table, named fail-closed refusal on an absent
export; a bare API name in a value address expression keeps the
classic unsupported-provider refusal). +9 tests (new
`tests/test_native_aa_cleanup_parity.py`: the program-level no-op
shapes incl. sorted/dedup + wildcard/external scoping + the label-only
re2 trigger; the plan-level handover re-block + the unowned cascade
unblock (the re2 12997 root shape — the provider stays supported and
the dependent `rootsym+8` resolves with dependency_ids [1]); the
Sleep/ShowWindow markers; the value-expression boundary) and 4
modules updated (`test_native_assembler`,
`test_native_luacall_symbol_only`,
`test_native_rt42_runtime_provider`,
`test_native_lua_symbol_handover` — the single named reason), plus
the deterministic MT-24 race guard in `test_native_master_ui` (a
queue-only stub analysis worker for the rescan pending-marker test —
the daemon thread could finish the one-entry table's compile before
the assertion, making the "…" marker racy). Full main suite 4,926
OK / 35 expected skips; catalog remeasure
`blocked-catalog-042-cleanup`: 117,809 total / 117,272 supported /
12,974 headings / 104,123 actionable / 537 blocked (-268 vs
`blocked-catalog-041-digit-labels`; the 3-chunk delta audit vs the
0.41 chunks: zero newly blocked, 268 unblocked — 26 `Sleep` + 2
`ShowWindow` + 24 direct cleanup-ownership rows + 216 provider
cascades: the HFW `pInventoryItemResource` / `pAttackInfo` /
`PlayerCharacter` thread cascades, the DS2 `KeyHandlerThread`
dependents, the re2 `rootsym` cascade — 12 still-blocked rows carry
the more specific named handover reason: DS2 `KeyHandlerThread` x10
(record 87498) + x1 (record 87500), `pBase` x1 (record 1337263367)).

- Build: 0.42 released as run
  `native-20261111T044023Z-04112d15` (cut from `main` @ `377f760`,
  2026-11-11): in-build suite 4,926 OK / 35 expected skips, 0
  failures — fully green at the canonical build path,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate.
  Source ZIP `CT2Trainer-0.42-source.zip` sha256
  `f44d248303b302b8621e80efc7c6faff476d0f27887b729546bf42c639839415`
  (14,589,013 bytes) - carries the CE 7.5 cleanup parity fix
  (`aa_program.py` + `compiler.py` + `tests/test_native_aa_cleanup_parity.py`)
  and the API-export registry extension (`sleep` / `showwindow`) - and
  portable ZIP `CT2Trainer-0.42-windows-portable.zip` sha256
  `305832ddc03487542c9a889e150b96f45c1576fa5e56819276da54b9388a5c40`
  (49,821,481 bytes; the frozen `CT2Trainer-Master.exe` (sha256
  `35389c7611715b494418b2c5bcdbd48e84f8d55a55f3deab556c4aa4d6aefd1c`,
  17,051,026 bytes) ships next to the converter).

## 0.41 (2026-11-10)

AA typed-constant package + the digit-leading-label CE 7.5 parity fix
— the two remaining Death Stranding "Load Table" roots (record 130605:
root #1 the `(int)0.00` decimal-cast operand, root #2 the
`0CurrentWeight:` digit-leading label line) whose failure blocked the
~243-row "no unique supported provider" cascade. Typed constants: the
full typed family `(int|float|double|dword|qword|word|byte)` as
instruction operand, data literal and `define` value — the integer
family follows the CE `StrToQWordEx` contract (read-only reference):
a `0x`/`$`-prefixed or pure-hex literal parses as an integer, a
decimal / exponent form parses as a float and truncates toward zero,
and an out-of-range value is the named refusal "Typed constant
exceeds the {type} representation." instead of a silent wrap; the
float/double family stays finite-only with the named `Inf`/`-Inf` /
`NaN` spellings, and a hex literal over a float/double type keeps the
pre-existing cast no-op. The dialect boundary is deliberate: a typed
constant parses pure digits DECIMAL (the CE contract), while the
unsized AA dialect keeps its hex-by-default reading — 41 corpus rows
now assemble with the CE-correct bytes (byte-changing parity fixes,
every record stays supported, incl. the Borderlands3
`cmp [flag],(byte)2` byte-compare) and the two decimal-form DS
`(int)0.00` rows assemble for the first time; the define flow needed
no code change (corpus census: 164 `define(` calls, exactly 7
`(float)` idioms — the APlagueTale
`define(movespeedmultiplierdefault,(float)0.64)` stays byte-stable as
`0AD7233F`). Digit-leading labels: the CE 7.5 label-name contract
(`autoassembler.pas` `getPotentialLabels` L707-730 + the main path
L2843-2900, read-only reference) — a `name:` line is a positional
label definition iff `trystrtoint64('$'+name)` fails — implemented as
the `_symbol_name_token()` predicate (the `_LABEL_NAME` / `_HEX_NAME`
/ `_LITERAL_TOKEN` shapes) at all eight cursor / symbol sites in
`aa_program.py`: letter-starting names are byte-stable against the
pre-fix behavior (incl. letter-leading all-hex like `ABC`); a
digit-leading name is a program-local label only while it is not
fully hex-parseable and not a value literal (the `0x`/`$`-hex and
`#N`-decimal spellings the typed-constant substitution emits into
operand streams), so `0CurrentWeight:` keeps the owned allocation
region for the following `resb 8` padding while `0078:` / `11105:`
keep the classic externally-provided symbol cursor and the `0x...`
literal tokens never enter the program's requirements; the link
walk's `key not in resolved` guard keeps digit-leading SCAN symbols
(the Octopath1 `8PathBattleResult` / `8PathSteal` aobscanmodule
pairs) on the classic resolution path (corpus census: 267 distinct
digit-leading label names, 262 all-hex unchanged, 5 non-hex: the DS
trio + the Octopath pair, both regression-guarded). +38 tests (new
`tests/test_native_aa_typed_constants.py` 23 + new
`tests/test_native_aa_digit_labels.py` 15 with the NASM byte pins:
the digit-vs-letter byte-stable blocks, the DS root idiom
`C780BC02000000000000` + 24 reservation zero bytes, the duplicate
digit-label refusal with letter parity, the inlined Octopath
aobscanmodule replica); full main suite 4,917 OK / 35 expected skips;
catalog remeasure `blocked-catalog-041-digit-labels`: 117,809 total /
117,004 supported / 12,974 headings / 103,855 actionable / 805
blocked (-248 vs `blocked-catalog-040-process-id` — the 3-chunk delta
audit vs the 0.40 chunks: zero newly blocked, 248 unblocked (the DS
pair 122+121=243 rows, root record 130605 + the "no unique supported
provider" cascade: PlayerStats, PlayerBattery, CurrentWeight, ...)
plus 5 x `dq (double)Inf` records (AtomicHeart / HellPie / Oregon /
Scorn / Callisto), zero reason changes).

- Build: 0.41 released as run
  `native-20261110T210856Z-5811040c` (cut from `main` @ `c724a7e`,
  2026-11-10): in-build suite 4,917 OK / 35 expected skips, 0
  failures — fully green at the canonical build path,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate.
  Source ZIP `CT2Trainer-0.41-source.zip` sha256
  `05ef6cabca08adcca8a084722581b7d553966e480e28274a4a72f4b31b9c1964`
  (14,580,191 bytes) - carries the AA typed-constant package
  (`aa_program.py` + `tests/test_native_aa_typed_constants.py`)
  and the digit-leading-label CE 7.5 parity fix
  (`tests/test_native_aa_digit_labels.py`) - and portable ZIP
  `CT2Trainer-0.41-windows-portable.zip` sha256
  `533bee676d0ed5c487741cb4919af8f4370f2bee1c5c26181ed5f3f0c3753a77`
  (49,814,303 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `ce07c42cf22c57eeeffa08be74ff562d3a7dcfca5f4c2d14121c784acd24c6f`,
  17,049,435 bytes, ships next to the converter).

## 0.40 (2026-11-10)

Master Trainer process identification in picker + details (MT-31) +
the bounded zero-transfer transient-write retry in `memory.py` — the
adopted 0.40 candidates from the online evaluation (the Cheat Engine
forum "Open Process By PID" thread: the multi-instance
indistinguishability problem — several running instances of the same
game name with no way to tell them apart; the WeMod UI threads: the
layout / visibility / trainer-options requests remain covered by the
0.36 multi-column grid and the 0.37 per-table process binding; the
Game Cheats Manager front end: tags / search / filters / last-used →
covered by MT-13/15/18/27, auto-update / online catalog → out of
scope; the zhisync / game.cheat online catalog → out of scope; the
game launch integration → still out of scope — no install-path data
in the read-only table model), and the reliability lane that
completes the 0.39 read-side symmetry. MT-31: the use case's "choose
which table runs against which process" only works reliably when the
user can TELL the candidates apart — the `ProcessSnapshotEntry` gains
the optional identification fields `path` (the full image path),
`creation_time` (the process start, Unix epoch seconds) and
`pointer_size` (4 / 8, the target bitness), all default `None`
(refused / unavailable — fail-closed: the display falls back to
name + PID, the `pid` / `name` decision fields are never touched);
the snapshot listers stay cheap (name + PID only, the 30 s
auto-rescan tick keeps its contract). The bounded per-candidate
enrichment runs only where the user asks for it — the process
picker rows and the table-details "Running now" row, never per poll
tick: `enrich_candidates` applies the platform
`default_process_enricher` to each entry of the bounded candidate
set, every per-entry failure fails closed (the entry stays
unenriched, a non-entry result is refused as well); the Windows
backend opens the process with `PROCESS_QUERY_INFORMATION` only
(no other rights) and asks `QueryFullProcessImageNameW` /
`GetProcessTimes` (FILETIME ticks → Unix seconds) /
`IsWow64Process2` (I386 → 32-bit, AMD64 → 64-bit, anything else
unknown) with the handle closed in a finally; the Linux/SteamOS
backend takes the `/proc/<pid>/exe` link target (under Proton the
compatibility-prefix path of the bound Windows EXE) and the
`starttime` field of `/proc/<pid>/stat` plus the system `btime` (the
bitness is not provable from `/proc` and stays hidden there); the
picker rows render through `candidate_display_text` — name + PID
always (byte-stable against the pre-0.40 row format while
unenriched), the proved facts appended (path / "started YYYY-MM-DD
HH:MM" / "64-bit" / "32-bit"), a refused fact never renders; the
table-details "Running now" row renders each running bound candidate
with its identification facts (the bare name + PID row while
refused); the waiting-view "Running now" line keeps its cheap name +
PID form (never enriched). Zero load-path effect — the MT-9 gate
re-checks the table independently at load time; the attach decision
(the PID pin) is unaffected by the enrichment. Reliability lane:
the write-side symmetry of the 0.39 transient-read retry — a
`WriteProcessMemory` call that FAILED with the field-observed
transient set {299, ERROR_MORE_DATA=119, ERROR_BAD_LENGTH=1116,
ERROR_INVALID_ID=24} and transferred NOTHING is retried in
`memory._write_checked` with the bounded exponential backoff
(exactly 4 attempts, backoff 0.05 → 0.25 s, the sleep under the
caller's lock, the snapshot-retry / read-retry precedent); a partial
transfer (a call that moved any bytes, failed or not) or any
non-transient code is NEVER retried and lands in the existing
uncertain-write protocol unchanged (fail-closed — the "never
silently retries a PARTIAL write" contract holds; after the budget
the original error surfaces as before). +46 tests (new
`tests/test_native_master_ui_mt31.py` 12 +
`tests/test_native_memory_write_retry.py` 7 + the MT-31 additions in
`tests/test_native_master_process_watch.py` +23 and
`tests/test_native_master_process_picker.py` +4; baseline pinning in
the MT-12/MT-22/MT-28 UI tests); full main suite 4,879 OK / 35
expected skips; catalog zero delta (the audit chunks
byte-identical vs `blocked-catalog-039-autoload`: 117,809 total /
116,756 supported / 60,161 staged / 1,053 blocked, zero newly
blocked; run `blocked-catalog-040-process-id`).
- Build: 0.40 released as run
  `native-20261110T093203Z-82c49872` (cut from `main` @ `e611e9e`,
  2026-11-10): in-build suite 4,879 OK / 35 expected skips, 0
  failures — fully green at the canonical build path,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate.
  Source ZIP `CT2Trainer-0.40-source.zip` sha256
  `46ad5dd9f9adc872e320dd4aec2362e007020ae879bba0cc8fe0621e44c34c40`
  (14,569,029 bytes); portable ZIP
  `CT2Trainer-0.40-windows-portable.zip` sha256
  `5075586c7b0f3251749c8e3e60ec0db7fea251db39190b59b63273a4e9b10bd6`
  (49,809,535 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `52f6da1cebfc44a0dc791d4b5758112342b5a1d42c9fc9656901a16d1a5eb03f`,
  17,048,910 bytes, ships next to the converter).

## 0.39 (2026-11-10)

Master Trainer per-table auto-load policy (MT-29) + state folder /
debug log quick access (MT-30) + the bounded transient-read retry in
`memory.py` — the adopted 0.39 candidates from the online evaluation
(the WeMod community thread re-read: the layout / visibility /
trainer-options requests remain covered by the 0.36 multi-column
grid and the 0.37 per-table process binding; plus the code survey of
Game-Trainer-Manager (github.com/Karasukaigan/game-trainer-manager):
pin-to-top → MT-18 exists, local search → MT-13/14 exists, detailed
logs / debug mode → the adopted MT-30 signal, Steam launch / online
catalog / themes / bilingual → out of scope for the private own-use
model), and the reliability lane closing the documented open issue
of the 0.38 ledger. MT-29: the use case's "choose which table runs"
direction — the per-table auto-load policy (`table-autoload.json`
schema 1, under the state home, keyed by the table content sha256,
the same identity as the MT-24/27/28 sidecars, so a policy survives
a rename and follows a content-identical file to another root); only
the non-default policy persists — one `manual-only` entry per table,
the absence of an entry is the documented automatic default; a
manual-only table is never auto-loaded (no auto-load request and no
picker — the waiting line shows the stable named detail "auto-load
suppressed (all N bound table(s) for this process are manual-only;
load one explicitly)" instead, and an open choice is dropped back to
waiting), while every explicit load path (double-click / Enter,
"Load this table", the "Load table" picker, `Recent:`) keeps
working unchanged; the policy set is a zero-arg callable
re-evaluated on every orchestrator tick (a policy change applies
from the next tick); the row context menu offers the toggle
("Auto-load: manual only" / "Auto-load: automatic" — the label
names the action, the pin-toggle convention; immediate persist +
status line; the disabled "Auto-load policy (no content sha)" item
for a table without a content sha), the MT-22 table-details window
gains the "Auto-load policy" row, and the waiting-view filter
matches the persisted policy text. MT-30: the waiting view gains
two header buttons — "State folder…" and "Debug log…" (master-only,
the standalone trainer header stays byte-identical) — opening the
persisted state home (the master-state document, the table index,
the per-table sidecars, and the `forced-recovery/` archives created
by the 0.38 `--force` forced start) and the trainer debug log at its
exact `debug_log.default_log_path()` in the platform file manager /
default handler (the pure `state_access.py` layer: the named
`StateAccessRefusal` codes `state-folder-bad` / `state-folder-
missing` / `debug-log-bad` / `debug-log-missing` / `no-opener` /
`bad-path` / `opener-failed`; every refusal lands in the status
line — never a dialog, never a crash). Reliability lane: the field-
observed transient "ReadProcessMemory failed (Win32 error 299)"
(0.22 / 0.30 / 0.31 field logs, Proton — no public Windows constant
is named for 299, so it is documented as a field-observed transient
code) is now retried in `memory._read_exact` with the bounded
exponential backoff — the transient set {299, ERROR_MORE_DATA=119,
ERROR_BAD_LENGTH=1116, ERROR_INVALID_ID=24} (the same codes the
module-snapshot retry treats as transient), exactly 4 attempts,
backoff 0.05 → 0.25 s (the sleep under the caller's lock, the
snapshot-retry precedent); a partial result (a successful call that
transferred fewer bytes) is NOT retried — an unexpected state, not
a transient error code; after the budget the original error is
raised unchanged (fail-closed, no silent success). +73 tests (new
`tests/test_native_master_autoload.py` 33 +
`tests/test_native_master_ui_mt29.py` 14 +
`tests/test_native_master_ui_mt30.py` 20 +
`tests/test_native_memory_read_retry.py` 6); full main suite 4,833
OK / 30 expected skips; catalog zero delta (the audit chunks
byte-identical vs `blocked-catalog-038-force`: 117,809 total /
116,756 supported / 60,161 staged / 1,053 blocked, zero newly
blocked).
- Build: 0.39 released as run
  `native-20261110T051241Z-57bf7d47` (cut from `main` @ `17a22f7`,
  2026-11-10): in-build suite 4,833 OK / 30 expected skips, 0
  failures — fully green at the canonical build path,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate.
  Source ZIP `CT2Trainer-0.39-source.zip` sha256
  `14163e7475477c177be339d06fd5ba7b9a7016667405669b084faed25035a923`
  (14,549,960 bytes); portable ZIP
  `CT2Trainer-0.39-windows-portable.zip` sha256
  `7d5d7903f1be5df0eac0f1067d5c2ca596321a41ea37381e033e5deb175ec8b6`
  (49,800,752 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `e0db5b2e2f41ec816089486ca57a2c0b1424523e7ee8450335053923ab629e47`,
  17,042,819 bytes, ships next to the converter).

## 0.38 (2026-11-09)

The `--force` startup parameter for the documented SteamOS state-lock
dead end (user request 2026-11-09; diagnosis logs from the 0.22/0.30/
0.31 Indiana Jones and the Great Circle field runs on Proton: an
interrupted recovery transaction left `recovery.lock` behind, the
recovery-eligibility assessment stopped classifying the state, and the
conservative refusal "A recovery transaction owns this state" fired on
every start for hours - with no easy way to delete the state folder on
SteamOS). `--force` is accepted by the frozen trainer EXE
(`launcher.py`), the source CLI `run` and `master` commands
(`__main__.py`) and the frozen `CT2Trainer-Master.exe`
(`tools/native_master.py`); it skips the state-lock safety prompts - a
recoverable stale state (dead state-lock owner) or unfinished receipts
are archived through the tested `perform_stale_recovery` path without a
confirmation dialog, and a leftover recovery fence / any other
unclassifiable held state (the plain `StateError` dead end, including
the "state.lock already exists" probe fallback) triggers the new
bounded forced reclaim in the pure `state_force.py` layer
(`force_reclaim`): every recorded trainer-side owner (state lock,
recovery fence, session record, matching shared process claims under
`_process_sessions`) is probed with the tested process probe (one
observation, one retry on a transient "unknown"); a **proven-alive**
trainer-side owner is still refused with its named reason - the one
hard data-safety boundary that stays even under `--force` (the
`LiveStateConflict` path now refuses without the termination prompt);
every other case (proven-dead owner, unprovable owner: transient probe
failure, legacy lock without creation identity, unparseable document)
quarantines the blocking artifacts (state.lock, recovery.lock,
session.json, state.json.tmp, oneshot.json.tmp, hook receipts /
global-pool, this trainer's shared claims) into a timestamped
`forced-recovery/<UTC stamp>-<trainer id>/` archive next to the state
folder with a full evidence document (`ct2trainer-forced-reclaim/v1`:
owner observations, moved files with size + sha256); the saved
`state.json` (the user's saved wishes) is always preserved, so the
saved toggles survive the forced reclaim; the engine default state
directories factored out as `default_state_dirs` (single fact shared by
the engine claim and the reclaim path); debug-log events
`state-force-recovered` / `-reclaimed` / `-refused` / `-failed`; master
wiring: `run_master(..., force=)` → `MasterApp.force` → the `_start_load`
loop (status line `Forced … complete` / `--force refusal: …`, the
fail-closed loop guard unchanged); on Steam set it in the game's launch
options (Properties → Launch Options: `--force`) so the Proton-wrapped
trainer starts without any dialog. +27 tests (new
`tests/test_native_state_force.py` 13 + force-flow classes in
`tests/test_native_ui_recovery_flow.py` 6 + `tests/test_native_master_force.py`
8); full main suite 4,760 OK / 30 expected skips; catalog zero delta
(all three audit chunks byte-identical vs `blocked-catalog-037-attach`:
117,809 total / 116,756 supported / 60,161 staged / 1,053 blocked, zero
newly blocked). Documented open issue (not part of 0.38): the Win32
error 299 transient read failure during a live `PatchConflict` receipt
verification on Proton (`memory._read_exact` has no bounded retry)
remains the upstream trigger of the stale state on Deck - see the
0.38 ledger section in `documentation/native-progress.md`.
- Build: 0.38 released as run
  `native-20261109T211151Z-03e89050` (cut from `main` @ `da1e68f`,
  2026-11-09): in-build suite 4,760 OK / 30 expected skips, 0
  failures — fully green at the canonical build path,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate.
  Source ZIP `CT2Trainer-0.38-source.zip` sha256
  `e2b466adc7abfb191bbd2b50f8304739a1e82cbf487099d4ecd6fd77cc3f3d0c`
  (14,521,497 bytes); portable ZIP
  `CT2Trainer-0.38-windows-portable.zip` sha256
  `df5ccfa373c8f5deb6be85f36e75941a1c0b3a9f13afae23c03f1644f9290fc4`
  (49,781,948 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `5d2cc5544eb6a29f1c3283f05e809e392d0038a1f59456c9d52f0356e519231d`,
  17,026,316 bytes, ships next to the converter).

## 0.37 (2026-11-09)

Master Trainer per-table process binding persistence (MT-28) — the
adopted 0.37 candidate from the online evaluation (the WeMod
community thread "UI customization" re-read,
community.wemod.com/t/ui-customization/371434 — the thread's layout /
visibility requests remain covered by the 0.36 multi-column grid —
plus the code audit of the Master Trainer attach flow that found the
gap: MT-11 persists the attach mode, and the picker's chosen PID is
"pinned for the session" only, so a restart loses the per-table
process choice). MT-28: the explicit process choice is remembered per
table (`table-attach.json` schema 1, under the state home, keyed by
the table content sha256 — the same identity as the MT-24 analysis
and the MT-27 notes documents, so a remembered choice survives a
rename and follows a content-identical file to another root; strict
key-set / field validation, checksummed envelope, LRU-bounded to
1024 entries, refused documents treated as absent); a live
remembered choice outranks the documented smallest-PID rule in
`auto` mode; in `ask` mode the picker still opens (the documented
contract) with the remembered row preselected so the one-click
attach is the remembered target; a stale or foreign PID (the process
exited, or the PID was recycled by another process) falls back to
the ordinary attach decision; every picker origin persists the
choice (auto-load, explicit load, table choice, re-attach after a
detach — the `attach` origin addresses the loaded table through the
sidecar sha); a table without a content sha cannot carry a binding
(the documented MT-27 identity rule); the MT-22 table-details window
shows the "Remembered process" row; zero load-path effect — the MT-9
gate re-checks the table independently at load time. The pure layer
lives in `table_attach.py` (`binding_entry`, the document bytes /
load / save, `evict_oldest`, `AttachStore`, `binding_target`,
`details_attach_lines`); `master_ui.py` carries the wiring
(`MasterApp.attach_store`, the picker `preselect_pid`,
`_binding_candidate`, `_remember_attach_choice`);
`table_details.py` renders the row. +68 tests
(`tests/test_native_master_attach.py` 53,
`tests/test_native_master_ui_mt28.py` 15) + the baseline
details-line assertion updates in `tests/test_native_master_ui_mt22.py`
(2), `tests/test_native_master_notes.py` (2) and
`tests/test_native_master_ui_mt24.py` (2). Full main suite 4,733 OK /
30 expected skips (4,665 from the 0.36 content + 68 new); catalog
zero delta `blocked-catalog-037-attach` (3-chunk deep-equal audit over
the 151 reference tables, 2026-11-09: 151/151 loaded, 0 load errors,
117,809 total / 116,756 supported / 60,161 staged / 103,607
actionable / 12,974 headings / 1,053 blocked — zero delta vs
`blocked-catalog-036-grid`).
- Build: 0.37 released as run
  `native-20261109T154005Z-4ad8e339` (cut from `main` @ `27dbf0d`,
  2026-11-09): in-build suite 4,733 OK / 30 expected skips, 0
  failures — fully green at the canonical build path,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate.
  Source ZIP `CT2Trainer-0.37-source.zip` sha256
  `a49bdd7d738de9551a1d971430ed9f7b0a212ec0d4a2afd8667e1f87ec61d301`
  (14,506,715 bytes); portable ZIP
  `CT2Trainer-0.37-windows-portable.zip` sha256
  `5cdb23b24c0757cb047ddd72ae673614fc6bccee960747079849fe325785c3ce`
  (49,762,223 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `c2a1a6948fa28248d36a6defa5a116867620261e55bdcfe1e144cd301060a9de`,
  17,017,090 bytes, ships next to the converter).

## 0.36 (2026-11-09)

Master Trainer multi-column trainer grid (MT-21) — the adopted
0.36 candidate from the online evaluation (WeMod's cheat list
multi-column layout with the staff-confirmed collapse behavior —
the official WeMod community thread "UI customization",
community.wemod.com/t/ui-customization/371434, 2025-09-11: "The
cheat list collapses to a single column under a certain size so
nothing is hidden. There are also minimum width constraints to
prevent it from ever being hidden" — see the Master Trainer
ROADMAP "0.36 multi-column trainer grid" section):

- **MT-21 multi-column trainer grid**: the trainer row grid can
  now run in up to three side-by-side columns. The requested
  column count (1 / 2 / 3, default 1) persists in the master
  state (`master-settings.json` schema 8 -> 9, `grid_columns`;
  strict int validation, a schema-8 document carrying the field is
  refused as an unknown field) and is handed to the trainer window
  on table load. The trainer header gains the **"Columns: N"**
  cycle button (master only — the standalone trainer header stays
  byte-identical and always renders the single column): 1 -> 2 ->
  3 -> 1, immediate re-render, persisted on every change. The
  pure grid layer lives in `ui_rows.py`: `build_grid` (per-column
  row lists; `columns == 1` byte-stable against `build_rows`;
  otherwise the reference rows are emitted at the full width,
  split into top-level units (`row_units` — a section with its
  children never splits across columns), the width-independent
  unit heights flow shortest-column-first (`flow_units`, ties to
  the lower column index) and each column is re-emitted at its own
  width with the column `x0` baked into every row rectangle
  (`column_layout`, equal widths, the leftover pixels to the
  leftmost columns)); `effective_columns` clamps the requested
  count to what fits (two columns need 652 px, three need 984 px;
  a column never falls below the 320 px floor). Renderer:
  per-column pagination, per-column hit-testing (x picks the
  column, y the row inside that column with its own page offset),
  the right-anchored positions derived from the baked `row.hit`
  rectangles. The standalone trainer is untouched beyond the new
  default-valued constructor arguments. +55 tests
  (`tests/test_native_ui_grid.py` 37,
  `tests/test_native_master_ui_mt21.py` 14, the grid tests in
  `tests/test_native_master_state.py` 4) + the baseline handoff
  assertion updates in `tests/test_native_master_ui.py`. Full main
  suite 4,665 OK / 30 expected skips (4,610 from the 0.35 content
  + 55 new); catalog zero delta `blocked-catalog-036-grid`
  (3-chunk deep-equal audit over the 151 reference tables,
  2026-11-09: 151/151 loaded, 0 load errors, 117,809 total /
  116,756 supported / 60,161 staged / 103,607 actionable /
  12,974 headings / 1,053 blocked — zero delta vs
  `blocked-catalog-035-notes`).
- Build: 0.36 released as run
  `native-20261109T114726Z-15c3d9ab` (cut from `main` @ `d071884`,
  2026-11-09): in-build suite 4,665 OK / 30 expected skips, 0
  failures — fully green at the canonical build path,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate.
  Source ZIP `CT2Trainer-0.36-source.zip` sha256
  `79464f02cd71492763656ca0ff3283a240c3579b9f52df3bcc18857dabb3d1be`
  (14,490,858 bytes); portable ZIP
  `CT2Trainer-0.36-windows-portable.zip` sha256
  `089fc92b0c5758ba758fdc88bb92e11d8e3b3e36c28d04231f27b3eeaecceac0`
  (49,751,886 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `07ebef319b55d686c4f76cdb6f07440a2b4934fc8943f9f72b402d62c4c49fe8`,
  17,006,463 bytes, ships next to the converter).

## 0.35 (2026-11-09)

Master Trainer per-table notes / tags (MT-27) — the adopted 0.35
candidate from the online evaluation (the trainer / table manager
library-organization patterns — game-trainer-manager
(Karasukaigan): organizing + local search + Pin to Top;
Fling-Trainer-Manager: local catalog with search; FLiNG:
per-trainer metadata; WeMod: library organization — see the Master
Trainer ROADMAP "0.35 per-table notes / tags" section):

- **MT-27 per-table notes / tags**: the waiting view gains a **Note**
  column (last, width 160) — the persisted per-table organization
  metadata: the note text truncated to one line (an ellipsis marks a
  cut, `NOTE_COLUMN_MAX` = 60 characters) plus the tags in brackets
  (`note [tag-a, tag-b]`); note-only and tag-only entries both
  render; empty while no note exists. The row context menu offers
  **"Edit note…"** between "Load this table" and the pin toggle —
  a small Toplevel with the note (multi-line text, bounded at
  `NOTE_MAX_LEN` = 500 characters) and a comma-separated tag entry
  (bounded at `TAGS_LIMIT` = 8 tags × `TAG_MAX_LEN` = 40 characters,
  stripped, casefold-deduped first-spelling-wins); a named refusal
  at save time (note over the limit, a tag too long, too many tags)
  is shown in the dialog's own label — the dialog stays open, the
  persisted document is untouched; a table without a content sha
  (unreadable / never scanned) is refused in the status line, no
  dialog opens; single window, lift on second open, closed on
  trainer entry with the rest of the waiting view.
- **Persistence**: `table-notes.json` (schema 1, under the state
  home) — **keyed by the table content sha256** (the same identity
  as the MT-24 analysis document), so a note survives a rename
  within a root and follows a content-identical file to another
  root; one entry per noted table (`{"note", "tags",
  "updated_at"}`); strict key-set / field validation of the
  master-state discipline (an unknown field is a named refusal,
  never a silent drop); checksummed canonical-JSON envelope;
  `NOTES_ENTRIES_LIMIT` = 1024 entries, `evict_oldest` by
  `updated_at` (ties by sha256 — deterministic); a refused
  document is treated as absent (documented, never a silent
  reset). No master-state schema bump (the MT-24 sidecar
  precedent — the notes live in their own checksum-bound
  document).
- **Search**: the waiting-view filter now also matches the note
  text and every tag — the pure `filter_tables` gains the optional
  `note_lookup` (table content sha256 -> entry); a table matches
  when ANY of them matches; `note_lookup=None` is the exact
  pre-0.35 behavior (backward-compatible).
- **Details**: the MT-22 table-details window gains the note / tag
  rows after the entry-analysis block (`none` while the table
  carries no organization metadata).
- The pure layer is `table_notes.py` (`parse_tags`, `note_entry`,
  the document bytes / load / save, `evict_oldest`, `NotesStore`,
  `note_column_text`, `details_note_lines`, the named
  `NotesRefusal` with `.reasons`); no index mutation, no
  table-file access, no load-path effect (the MT-9 gate
  re-checks the table independently at load time). +67 tests
  (`tests/test_native_master_notes.py`: the pure layer + the Tk
  wiring incl. the menu order `Table details` / `Load this table` /
  `Edit note…` / `Pin to top`); full main suite 4,610 OK / 30
  expected skips; catalog zero delta `blocked-catalog-035-notes`
  (3-chunk deep-equal audit over the 151 reference tables,
  2026-11-09: 151/151 loaded, 0 load errors, 117,809 total /
  116,756 supported / 60,161 staged / 103,607 actionable /
  12,974 headings / 1,053 blocked — zero delta vs
  `blocked-catalog-034-mt26`).
- Build: 0.35 released as run
  `native-20261109T054146Z-c5f18494` (cut from `main` @ `65d8fbe`,
  2026-11-09): in-build suite 4,610 OK / 30 expected skips, 0
  failures — fully green at the canonical build path,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate.
  Source ZIP `CT2Trainer-0.35-source.zip` sha256
  `575ee8ad6f0864bd8ff39f3ae547bb629d5c128938cff792e9c4fb7362fbcdac`
  (14,474,384 bytes); portable ZIP
  `CT2Trainer-0.35-windows-portable.zip` sha256
  `488d7453ca0433f843c1e46a2241142347aa2ee41390ed334d6068ed30e42d34`
  (49,737,899 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `0c53908c267746cabd74e1ef091daa35d31eb94c4d0accc6401085d7e8c59ccc`,
  16,999,124 bytes, ships next to the converter).

## 0.34 (2026-11-09)

Master Trainer multi-root table index (MT-26) — the adopted 0.34
candidate from the online evaluation (the Cheat Engine Table Manager
(2026) feature set, whose core capability is the multi-folder table
index; the trainer-manager import / organize / search / pin patterns
— game-trainer-manager (Karasukaigan), Cheat Happens Trainer Manager;
the WeMod "save your selections for next time" pattern — see the
Master Trainer ROADMAP "0.34 multi-root table index" section):

- **MT-26 multi-root table index**: the Master Trainer indexes
  several table folders at once. Every root keeps the same
  incremental reconcile contract (the `(size, mtime_ns)` + sha256
  short-circuit per root; the MT-25 auto-rescan now covers every
  indexed folder), and the merged surface distinguishes tables by
  the **absolute table key** (index root + relative path, native
  separators; `table_key()`) — the relative path remains the
  documented single-root identity, and key lookups resolve
  casefolded with the documented relative-path fallback
  (`TableIndex.get_by_key` / `RootIndexSet.get_by_key`). The folder
  list persists in `master-settings.json` schema 7 -> 8
  (`table_folders`, primary first, capped at `TABLE_FOLDERS_LIMIT` =
  8; strict non-empty unique casefolded strings; schema-7 documents
  promote on load — the list is filled from the single stored last
  folder and the relative table references (last table, recents,
  pins) are re-anchored to absolute table keys under it, so pins /
  recents survive the upgrade; a schema-7 document carrying the
  field is refused as an unknown field; a schema-8 document with a
  set last folder but an empty list self-heals to the single
  folder). The tables index document carries one checksum-bound
  root block per indexed folder (schema 1 -> 2; `save_index_set` /
  `load_index_set`; schema-1 single-root documents promote on
  load). The folder lifecycle is `MasterApp.add_folder` /
  `remove_folder` / `move_folder_front` (named `ValueError`s;
  `set_folder` keeps its replace-all contract), managed by the
  "Folders…" header button — the folder manager window (the
  indexed folders in user order, the primary marked with a star;
  "Add folder…" / "Set primary" / "Remove" / "Close"; every action
  re-scans the indexed roots, saves the index, restarts the
  auto-rescan clock and refreshes the view; a failed change lands
  in the status line, fail-closed). The waiting view gains the
  **Folder column** (the entry's index root), and the row key
  becomes the absolute key in a multi-root session — picker,
  details, pins, recents and the MT-24 analysis queue are all
  key-based. `run_master` multi-root folder resolution: an
  explicit folder argument wins as the primary root with the
  stored folders indexed behind it (casefold-deduped, each
  printed as an "Also indexing stored folder:" line); a
  parameterless start keeps the stored folder list as-is (a
  missing stored folder stays visible as a scan problem, fixed
  through the folder manager); only a genuinely first start / no
  stored folders shows the directory picker (a cancelled first
  start exits 0); every stored folder gone shows the picker (the
  pick is prepended as the new primary, a cancel keeps the missing
  list); an explicit missing folder is the documented exit-2
  refusal. Zero load-path effect — the MT-9 gate re-checks the
  table file under its index root independently at load time.
  +37 new tests (`tests/test_native_master_ui_mt26.py`) + 7 new
  schema-8 state tests (`tests/test_native_master_state.py`) + the
  baseline test updates (folder column, key-based identity,
  per-root entry injection); full main suite 4,543 OK / 30 expected
  skips; catalog zero delta `blocked-catalog-034-mt26` (3-chunk
  deep-equal audit over the 151 reference tables, 2026-11-09:
  151/151 loaded, 0 load errors, 117,809 total / 116,756 supported
  / 60,161 staged / 103,607 actionable / 12,974 headings / 1,053
  blocked — zero delta vs `blocked-catalog-033-auto-rescan`). Docs
  in the same change: `master_trainer/ROADMAP.md` (0.34 section +
  the 0.35 candidate note — per-table notes / tags), `CONCEPT.md`,
  `UI.md` (+ the multi-root lines in `ui_flow_text()`).
- Build: 0.34 released as run
  `native-20261109T024143Z-a5457911` (cut from `main` @ `dc00343`,
  2026-11-09): in-build suite 4,543 OK / 30 expected skips, 0
  failures — fully green at the canonical build path,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate.
  Source ZIP `CT2Trainer-0.34-source.zip` sha256
  `0d0a0849a90171f64eaf5b55ec06ec1d9117d02d5330895dcb4279e26f73b0f5`
  (14,455,170 bytes); portable ZIP
  `CT2Trainer-0.34-windows-portable.zip` sha256
  `ade1ecc520ddbeaf6886e1b195fc6e2886a5f9cbeaa64b15f9ac5679420f5054`
  (49,719,386 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `606ea2287eb9f787308d862c18209076ee42e4f7a4ae88fcb93bf8f22edcb6f6`,
  16,983,514 bytes, ships next to the converter).

## 0.33 (2026-11-08)

Master Trainer table folder auto-rescan (MT-25) — the adopted 0.33
candidate from the online evaluation (WeMod automatic game detection,
game-trainer-manager (Karasukaigan) directory watching + auto-import,
Cheat Happens Trainer Manager library-freshness lineage — see the
Master Trainer ROADMAP "0.33 table folder auto-rescan" section):

- **MT-25 table folder auto-rescan**: while the persisted
  "Auto-rescan: on/off" status-bar toggle is on, the waiting view
  re-runs the existing incremental scan every 30 s (one stat pass per
  interval; the same `(size, mtime_ns)` + sha256 short-circuit
  contract as the manual Rescan), so added / changed / removed tables
  show up in the index and the view without a manual F5. No OS
  file-watcher API — polling only, cross-platform. The toggle sits
  next to the attach-mode toggle, re-persists on every change, and
  raises the named `ValueError` for non-boolean values.
  `master-settings.json` schema 6 -> 7 (`auto_rescan`, strict bool,
  documented default on); schema-6 documents promote on load, a
  schema-6 document carrying the field is refused as an unknown
  field. The 30 s interval clock restarts on a manual rescan, a
  folder change, and the waiting-view rebuild (trainer round-trip);
  the scan pauses while a trainer is attached (the tick early-
  returns), exactly like the MT-24 analysis worker. The tick runs
  through `rescan()`, so added / changed tables are also re-queued
  for the MT-24 background analysis, and the tick carries no
  status-line flash. Zero load-path effect (the MT-9 gate re-checks
  the table independently at load time). +16 tests (4 state tests in
  `tests/test_native_master_state.py`, 12 UI tests in
  `tests/test_native_master_ui_mt25.py`).
  Docs in the same change: `master_trainer/ROADMAP.md` (0.33
  section + the 0.34 candidate note), `CONCEPT.md`, `UI.md` (+ the
  auto-rescan line in `ui_flow_text()`).
- Build: 0.33 released as run
  `native-20261108T200230Z-b0167049` (cut from `main` @ `6e71739`,
  2026-11-08): in-build suite 4,499 OK / 30 expected skips, 0
  failures — fully green at the canonical build path,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate.
  Source ZIP `CT2Trainer-0.33-source.zip` sha256
  `4528d1d0f2ee269fb2ee7ec470d9e9711b3c284bffe6cf582f7dafa7431756f2`
  (14,433,388 bytes); portable ZIP
  `CT2Trainer-0.33-windows-portable.zip` sha256
  `5e0244791b6f31a2e2219d5c33541c978ca4c0d399c8e7a234cb0c16e8ccb3d7`
  (49,703,149 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `59961d511d3964b075c968a3c577117ffa235970d65976f66d7e34e0eae010a9`,
  16,968,879 bytes, ships next to the converter).

## 0.32 (2026-11-06)

Master Trainer per-table entry count + blocked count via background plan
analysis (MT-24) — the adopted 0.32 candidate from the online
evaluation (FLiNG per-trainer "N Options" / option-count metadata —
per-table entry counts surfaced in the list are a recognized pattern,
game-trainer-manager (Karasukaigan) organize/search workflows, Cheat
Happens Trainer Manager v2 inspect-before-load lineage — see the
Master Trainer ROADMAP "0.32 per-table entry count + blocked count"
section). The entry-count / blocked-count columns were the candidate
deliberately deferred in 0.26/0.27/0.29/0.30/0.31 ("they need
background plan-analysis infrastructure"); this release ships that
infrastructure:

- **MT-24 per-table entry count + blocked count (background plan
  analysis)**: the waiting-view tree gains two columns between Detail
  and Size — **Entries** (the actionable record count of the plan
  compile: supported script / value records, i.e. the real cheat
  options) and **Blocked** (the blocked record count of the same
  analysis). The analysis runs in the background: one daemon thread
  (`analysis_worker.py`, queue limit 64, dedupe by table content sha,
  only tables with ≥1 bound process name are queued) through the
  tested `compile_table` plan path — no Lua execution, no target
  attach, the same static proof the corpus audit uses. The columns
  show `…` while pending and `–` on a named compile failure, the
  counts once analyzed; a blocked count > 0 appends the bounded
  "N blocked" note to the detail column after the pin marker. Results
  persist in `table-analysis.json` (schema 1, under the state home,
  keyed by table content sha256, LRU-bounded to 1024 entries, top-8
  blocked reasons per table, 200-char error detail) — a content
  change re-analyzes, an unchanged table reuses the cached entry; the
  pure decision layer is `master_trainer/table_analysis.py`
  (`counts_from_plan` / `blocked_reasons_from_plan` / `ok_analysis` /
  `failed_analysis` / `AnalysisStore` with strict key-set + checksum +
  timestamp + count validation, `AnalysisRefusal`). The worker is not
  auto-started: the waiting view owns the lifecycle (start / resume +
  queue at the end of the view build, pause on trainer entry after the
  attach gate, stop + clear on close); the meta line shows the live
  `analyzing N table(s)` figure while the queue has work. The MT-22
  table-details window gains the analysis block (`table_details.py`
  `analysis` kwarg): pending / `N entries (M blocked) of T records` +
  top blocked reasons / `failed: <reason>`. Display-side observation
  only — it never blocks, alters, or delays the MT-9 load gate, which
  re-checks the table independently at load time. Zero catalog effect
  (no table-parsing change).
- +69 tests (57 in `tests/test_native_master_analysis.py` new: the
  pure counts / reasons builders, the ok / failed analysis builders,
  the store's strict validation (unknown fields, wrong sha, bad
  counts, checksum mismatch), LRU eviction by `analyzed_at` with sha
  tie-break, the refusal codes, and the `active_workers()` live-worker
  registry lifecycle; 12 in `tests/test_native_master_ui_mt24.py`
  new: the column wiring + pending / failed / pinned / group-row
  shaping, the queue discipline (unbound tables never queued, rescan
  re-queue on content change only), the details-window analysis rows,
  the trainer-entry pause, the close stop + reference clear, the
  window-created default worker with the real compile path); plus the
  cross-module test-isolation fix (the shared Tk test teardown now
  stops every live plan-analysis worker, so window tests no longer
  leak worker threads into the later engine/timing modules); full
  main suite 4,483 OK / 30 expected skips (4,414 from the 0.31
  content + 69 new MT-24 tests); catalog zero delta
  `blocked-catalog-032-analysis` (3-chunk deep-equal audit over the
  151 reference tables, 2026-11-06): 151/151 loaded, 0 load errors,
  117,809 total / 116,756 supported / 60,161 staged / 103,607
  actionable / 12,974 headings / 1,053 blocked — **zero delta** vs
  `blocked-catalog-031-status` (per-table count/reason/sha changes: 0).
  Docs in the same change: `master_trainer/ROADMAP.md` (0.32
  section), `CONCEPT.md`, `UI.md` (+ `ui_flow_text()`).
- Build: 0.32 released as run
  `native-20261108T100731Z-a1d311e5` (cut from `main` @ `bfcc3a3`,
  2026-11-08): in-build suite 4,483 OK / 30 expected skips, 0
  failures — fully green at the canonical build path,
  `ce_inputs: []`, `runtime_unverified` deliberately kept per gate.
  Source ZIP `CT2Trainer-0.32-source.zip` sha256
  `f6cae57590d083e37308bc4a03b1046b8186617bdb0f98c88c9bc324404493d9`
  (14,426,224 bytes); portable ZIP
  `CT2Trainer-0.32-windows-portable.zip` sha256
  `3a7980ba04f60f7cb93edce3cf5c723ba609ff55a00b1f866079101d3b7bc986`
  (49,699,633 bytes; the frozen `CT2Trainer-Master.exe` sha256
  `6dc34408c8e5ecec1c2215c45da27ea22cc5c5ce5a9629267778b172d44d3485`,
  16,966,114 bytes, ships next to the converter). The first build
  attempt (`native-20261108T090044Z-5b70a3af`, preserved) failed the
  in-build suite in `test_native_master_ui_mt23` — the MT-24
  background worker still held a fixture table file open when the
  test unlinked it (Windows refuses the delete while a reader holds
  the file, WinError 32); the affected mt23 window tests now stop
  the worker via the shared guard before fixture mutations (test-only
  fix, no product code change), and the re-run full main suite on
  the final tree is green (4,483 OK / 30 expected skips).

## 0.31 (2026-11-05)

Master Trainer per-table live status + color coding + status filter
(MT-23) — the adopted 0.31 candidate from the online evaluation
(FLiNG per-trainer "Game Version" / "Last Updated" / option-count
metadata, Game Cheats Manager (dyang886) smart launcher,
game-trainer-manager (Karasukaigan) organize/search workflows,
CheatDeck (SheffeyG) Steam Deck launch options — see the Master
Trainer ROADMAP "0.31 per-table live status + color coding + status
filter" section):

- **MT-23 per-table live status + color coding + status filter**:
  the waiting-view Status column shows the table's state right now,
  not only the cached state of the last scan — one bounded `stat`
  per visible row per render against the index entry: `ok` /
  `running` (a bound process is up, the table loadable) /
  `changed` (the file drifted since the last scan) / `missing`
  (the file is gone) / `unreadable` (the last scan could not
  read/parse it, the named detail surfaces) — cheapest fact first,
  live facts outrank the cached scan state, the same order the MT-9
  gate proves at load time. Rows are color coded (the default
  colors for ok / running, amber #e5c07b for changed, red #ff7b72
  for missing / unreadable), and the persisted "Status: all / ok /
  attention" header cycle (between the view button and the filter
  entry) filters the list to the loadable rows or to the rows the
  gate would refuse right now. `master-settings.json` schema 5 -> 6
  (`view_status`): schema-5 documents promote, a schema-5 document
  carrying the field is refused as an unknown field.
  `set_view_settings` gains the 4th parameter `status_filter`
  (validated + re-persisted; every existing change point passes the
  current mode through, so sort/view/filter changes never reset the
  status filter); the status filter applies between the query
  filter and the pin float; the meta line gains the active
  `status filter: X` part + the live `attention: N` count (shown
  only when N > 0). The pure decision layer is
  `master_trainer/table_status.py` (`row_file_status` / `row_status`
  / `row_tag` / `filter_rows_by_status`, `ATTENTION_STATUSES`,
  `VIEW_STATUS_FILTERS`); the in-app `ui_flow_text()` and the
  reviewable `master_trainer/UI.md` document the new header control,
  the live Status column and the persistence row.
- Deliberately deferred (documented, unchanged candidates): the
  MT-21 multi-column trainer grid, and the entry-count /
  blocked-count columns (they need background plan-analysis
  infrastructure).
- Test totals: +28 over 0.30 (4 schema-6 state in
  `tests/test_native_master_state.py` + the new
  `tests/test_native_master_ui_mt23.py` — the pure layer: the live
  file state per fingerprint, the running-loses-to-attention
  contract, the tag per code, the filter reshaping per mode + the
  named refusal, the constant mirror against the state schema; the
  Tk wiring: the cycle / persist / restore, the other UI changes
  keeping the mode, the live changed / missing flags + tags, the ok
  / attention row shaping, the meta line); full main suite 4,414 OK
  / 30 expected skips; catalog remeasure
  `blocked-catalog-031-status`: zero delta (151/151 loaded, 0 load
  errors, 117,809 total / 116,756 supported / 1,053 blocked).

## 0.30 (2026-11-04)

Master Trainer table details + live load-gate preview (MT-22) — the
adopted 0.30 candidate from the online evaluation (FLiNG per-trainer
version / "Last Updated" metadata, game-trainer-manager
organize/search workflows, Game Cheats Manager .ct handling FAQ,
Cheat Happens Trainer Manager v2 portable + last-used pinning — see
the Master Trainer ROADMAP "0.30 table details + load-gate preview"
section):

- **MT-22 table details + live load-gate preview**: right-clicking a
  waiting-view row offers "Table details" first — a read-only window
  with the indexed facts for the table (path, folder, size,
  modified, bound processes, index status, pin state, last used,
  running PIDs, content sha — first 12 hex + "...") plus the
  on-demand load-gate re-check: the same `gate_table_for_load` pass
  MT-9 runs at load time, named refusal code + displayable detail —
  so a stale / changed / unreadable table is explained at
  inspection time, not only at load time. One window (a second open
  lifts + focuses instead of duplicating), transient, non-resizable,
  closed on trainer entry with the rest of the waiting view; no
  index entry leaves a named status line instead of a window. The
  row builder is pure in `master_trainer/table_details.py`
  (`format_size` / `format_mtime` / `gate_line` /
  `table_detail_lines`, named fallbacks) — the only I/O is the
  bounded gate re-check under the load limit. The in-app
  `ui_flow_text()` and the reviewable `master_trainer/UI.md`
  document the new row-menu entry.
- Deliberately deferred (documented, unchanged candidates): the
  MT-21 multi-column trainer grid, and the entry-count /
  blocked-count columns + per-table status / color-coding.
- Test totals: +16 over 0.29 (the new
  `tests/test_native_master_ui_mt22.py`: the pure builder — all
  facts in order, the unreadable entry + named fallbacks, the
  no-bound-processes label, the deduped/sorted PIDs, the size /
  mtime / gate-line formatters with boundaries; the Tk wiring — the
  menu order through a recording `tk.Menu` subclass, the details
  command opening the window for the row, the indexed facts incl.
  the live "OK (loadable...)" gate line, lift on second open,
  trainer-entry close, the named refusal display, the last-used
  timestamp); full main suite 4,386 OK / 30 expected skips; catalog
  remeasure `blocked-catalog-030-details`: zero delta (151/151
  loaded, 0 load errors, 117,809 total / 116,756 supported / 1,053
  blocked).

## 0.29 (2026-11-04)

Master Trainer UI/UX revamp: trainer-focus mode (MT-19) +
discoverability (MT-20) — the user field request of 2026-11-04 (when
a process is identified and the trainer attaches, the waiting table
list must shrink/collapse so the trainer items get maximum space;
make the UI generally more accessible; document the UI flow so it can
be reviewed/improved — see the Master Trainer ROADMAP "0.29
trainer-focus + discoverability" section):

- **MT-19 trainer-focus mode**: the whole waiting view now lives in
  one container frame that is destroyed on trainer entry — the table
  list and its chrome (header, folder/meta/running lines, status bar)
  no longer share the window with the trainer rows; the trainer row
  grid owns the full window. "⬅ Master" rebuilds the waiting view
  from scratch (filter, sort, view mode, pins and recents are window/
  app state and survive the round trip). If the engine is up but the
  trainer view cannot be built, the engine is closed again, the
  waiting view is restored and the load fails with the named error —
  the waiting loop and its loop guard stay consistent.
- **MT-20 discoverability**: the read-only "UI flow" header button
  (the in-app copy of the reviewable `master_trainer/UI.md` flow
  document — one Toplevel, a second click lifts the open window, the
  window closes on trainer entry); **F5** re-scans the folder from
  anywhere in the waiting view (a no-op in trainer mode, like the
  existing "/" binding); the table list takes the initial focus
  (arrow keys and Enter work immediately without a first click); the
  "Retry load" re-arm moves out of the root-level button below the
  status strip into the status bar next to the attach toggle and the
  Recent button.
- **Reviewable UI-flow document**: `master_trainer/UI.md` — the full
  flow (waiting-mode controls, tree columns, status bar, poll-tick
  behavior, every load path, the attach decision, the startup
  recovery dialogs, the platform gate, trainer-mode rows, back /
  detach, what is persisted, the keyboard map, the failure states)
  ships in the source ZIP with the package docs.
- Deliberately deferred (documented candidate MT-21, separate
  cycle): the multi-column trainer grid — the single-column canvas
  grid is the validated touch-first design (`ui_rows.py` pure row
  model + `ui_layout.py` + the 1-D hit-testing, exhaustively tested
  and shared with the standalone trainer); a column layout rewrites
  the pure row model, the pagination and the 2-D hit-testing and
  changes the standalone trainer as well.
- Test totals: +13 over 0.28 (the new
  `tests/test_native_master_ui_mt19.py`: container parenting, the
  collapse through the patched handoff, the constructor-failure
  rebuild, the back-to-master fresh frame, one real-`TrainerWindow`
  case, the flow-document content, the read-only Toplevel +
  lift-on-second-click, the trainer-entry close, the F5 contract in
  both modes, the initial-focus spy, the retry-bar placement); full
  main suite 4,370 OK / 30 expected skips; catalog remeasure
  `blocked-catalog-029-trainer-focus`: zero delta (151/151 loaded,
  0 load errors, 117,809 total / 116,756 supported / 1,053
  blocked).

## 0.28 (2026-11-03)

Master Trainer pinned/favorite tables (MT-18) - the first
candidate documented in the 0.27 follow-up online evaluation is
adopted (VGC Shelf "sort, pin, archive": pinning as a first-class
feature - see the Master Trainer ROADMAP "0.27 waiting-view
settings + process groups" section):

- **MT-18 pinned / favorite tables**: `master-settings.json`
  schema 4 → 5 - the pin set (`pinned_tables`, relative table
  paths, most recent pin first, capped at 25) is part of the
  persisted state document: restored at start, re-persisted on
  every toggle. The row context menu offers "Pin to top" /
  "Unpin"; a pinned table floats to the top of the waiting view
  (list view) and to the top of its process group (process view),
  and carries a "pinned" marker in the detail column - the first
  column stays the bare relative path, the row identity the load
  paths key off. Schema-4 documents promote on load; a schema-4
  document carrying the field is refused as an unknown field
  (foreign schema, never silently promoted - the same discipline
  as the attach mode, the recent list and the view settings).
  Named refusals (pin cap, already pinned, not pinned) land in
  the status line without a state change or a crash.
- Deliberately deferred (documented): entry-count / blocked-count
  columns and per-table status / color-coding (remaining
  candidates, evaluated in the ROADMAP).
- Test totals: +15 over 0.27 (4 schema-5 state tests, 4 pure pin
  tests, 7 MT-18 UI tests); full main suite 4,357 OK / 30
  expected skips; catalog remeasure `blocked-catalog-028-pin`:
  zero delta (151/151 loaded, 0 load errors, 117,809 total /
  116,756 supported / 1,053 blocked).

## 0.27 (2026-11-03)

Master Trainer waiting-view settings persistence (MT-16) +
process-grouped waiting view (MT-17) - both items deliberately
deferred in 0.26 are adopted (follow-up online evaluation: playR,
Universal Game Launcher, GamesList Manager, Game Cheats Manager -
see the Master Trainer ROADMAP "0.27 waiting-view settings +
process groups" section):

- **MT-16 persisted waiting-view settings**: `master-settings.json`
  schema 3 → 4 - the waiting-view filter query, sort mode and view
  mode are now part of the persisted state document. The filter
  entry text ("" = no filter, at most 200 characters), the sort
  mode (name / process / status) and the display mode (list /
  process) are restored at start and re-persisted on every change
  (filter typing, sort cycle, view cycle, Esc clear).
  Schema-1/2/3 documents promote on load with the documented
  defaults; a schema-3 document carrying a view_* field is refused
  as an unknown field (foreign schema, never silently promoted -
  the same discipline as the attach mode and the recent list).
- **MT-17 process-grouped waiting view**: a "View: list/process"
  cycle button switches the waiting view between the flat row list
  and a tree grouped by bound process name: one group per
  casefolded process name (a table bound to several names appears
  once under each of them), the tables without a bound name under
  "(no process binding)" last, within-group order = the current
  sort order (filter + sort applied first). Group rows are
  display-only and never load; the tables under a group load
  through the ordinary explicit-load path.
- Deliberately deferred (documented): entry-count / blocked-count
  columns (the catalog numbers belong to the local tooling) and
  per-table status / color-coding.
- Test totals: +22 over 0.26 (4 schema-4 state tests, 8 pure
  process-grouping tests, 10 MT-16/17 UI tests); full main suite
  4,342 OK / 30 expected skips; catalog remeasure
  `blocked-catalog-027-view`: zero delta (151/151 loaded, 0 load
  errors, 117,809 total / 116,756 supported / 1,053 blocked).

## 0.26 (2026-11-03)

Master Trainer waiting-view usability (MT-13 / MT-14 / MT-15) - with
~151 indexed tables the waiting view gets real navigation (user
request 2026-11-02/03; the feature set was evaluated against online
table/list UX patterns - see the Master Trainer ROADMAP "0.26
waiting-view usability" section) - plus the live-target takeover
field fix:

- **MT-13 search / filter / sort**: the new pure `table_filter.py`
  decision layer: a live filter (casefolded substring over the
  table name AND any bound process name; empty query = the full
  list, input order preserved) and a name / process / status sort
  cycle. Row identity stays the table's relative path; the load
  picker and the auto-load path keep the full index. Filter and
  sort are session only: they survive the trainer round-trip but
  are never persisted. While a query is active the metadata line
  shows `filtered: N/M`.
- **MT-14 keyboard flow**: double-click, Enter or numeric-pad Enter
  loads the selected row through the ordinary explicit-load path;
  "/" focuses the filter from anywhere in the waiting view (a
  no-op in trainer mode, where the keys belong to the trainer UI);
  Esc on the filter clears it and returns focus to the table list.
- **MT-15 recent tables + Size / Modified / Last-used columns**:
  every successful load records the table in the rolling recent
  list (`master-settings.json` schema 3 - most recent first,
  deduplicated, capped at ten, UTC timestamps; older schema
  documents promote on load). The list feeds the metadata line
  (`recent: a, b, c (N more)`), the one-click "Recent: <path>"
  load button and the tree's Last-used column; the indexed Size
  (compact B/KB/MB) and Modified (local time) join the tree, and
  the window grows to 1160x600 (minsize 900x420).
- **Live-target takeover field fix**: when a stale `state.lock`
  blocks the startup and the previous session's owner is proven
  dead in both observations while only target-side identities
  remain unproven, the recovery now - behind one user-confirmed
  prompt ("Recover and attach to the running game?") - archives
  the state byte-for-byte and attaches to the still-running game
  instead of dead-ending on a manual state-folder delete; saved
  wishes are re-applied (code-patch entries adopt idempotently,
  AOB entries whose scan pattern no longer matches surface named
  scan errors with the bounded re-arm). Unprovable or live owners,
  foreign artifacts or any extra refusal reason keep the strict
  refusal.
- Test totals: +61 over 0.25 (17 pure filter/sort tests, 13
  recent/state tests, 12 MT-13/14/15 UI tests, 19 live-target
  takeover tests); full main suite 4,320 OK / 30 expected skips;
  catalog remeasure `blocked-catalog-026-master-ui`: zero delta
  (151/151 loaded, 0 load errors, 117,809 total / 116,756
  supported / 1,053 blocked).

## 0.25 (2026-11-02)

Master Trainer user control (MT-10 / MT-11 / MT-12) — the trainer can be
detached, and the user chooses which table runs against which process,
with the configuration remembered (user request 2026-11-02; the feature
set was evaluated against online all-in-one trainers and the CE 7.5
process picker — see the Master Trainer ROADMAP “Online feature
evaluation” section):

- **MT-10 explicit table load**: the “Load table” waiting-view header
  button + the per-row right-click menu (“Load this table”); the table
  loads even while the bound process is not running yet (the engine
  waits for it); the last explicitly loaded table persists in the state
  home (`master-settings.json` schema 2) and is shown in the metadata
  line. The orchestrator's `request_load()` carries stable named
  refusals (`not-in-index` / `table-unreadable` /
  `no-process-binding` / `process-snapshot-failed`) — a refused load
  shows a named dialog + status line, never a crash; an explicit load
  bypasses the auto-load loop guard, but a failed explicit load still
  records the ordinary (name, PID) suppression.
- **MT-11 process selection + persisted attach mode**: the
  “Attach: auto/ask” toggle button (persisted). “auto” (default, legacy
  behavior): smallest-PID direct attach, no picker. “ask”: the process
  picker (name + PID rows) is shown for every attach, even a single
  running candidate. The chosen PID pins the session through the
  injected memory factory; the pin self-clears when that process exits
  and the session falls back to the ordinary name-based attach
  (smallest PID). Cancel semantics per origin (an auto-load pick defers
  the exact process pair, a table choice defers exactly like “Not
  now”, an attach stays paused).
- **MT-12 detach / user attach**: the new “Detach” header button in
  Master mode only (the standalone trainer header stays
  byte-identical). Detaching holds the engine's attach branch (no auto
  re-attach; session state, journals and wishes untouched; status
  “Detached; waiting for user attach”; debug events
  `attach-paused` / `attach-resumed`). The button turns into “Attach”:
  in “ask” mode the process picker offers the running candidates and
  the chosen PID is pinned on resume; in “auto” mode the ordinary wait
  simply resumes. A target exit while attached is unaffected (the
  engine keeps waiting as before).
- `master-settings.json` schema 2 (`last_table`, `attach_mode`):
  schema-1 documents promote on load with the documented defaults
  (`last_table=null`, `attach_mode="auto"`); only schema 2 is writable.
- Tests: +66 (`tests/test_native_master_process_picker.py` 16,
  `tests/test_native_master_explicit_load.py` 13,
  `tests/test_native_master_ui_mt12.py` 24,
  `tests/test_native_attach_pause.py` 5, +7 schema-2 tests in
  `tests/test_native_master_state.py`, +1 state-home isolation test in
  `tests/test_native_master_ui.py`). Full main suite 4,259 OK / 30
  expected skips (2026-11-02), zero catalog delta vs
  `blocked-catalog-024-sounds` (run `blocked-catalog-025-master-ui`:
  151/151 loaded, 117,809 total / 116,756 supported / 60,161 staged /
  1,053 blocked / 0 load errors).
- In-build reliability fix (exposed by the first 0.25 in-build suite
  run `native-20261102T181843Z-ddfb63f0`, 2026-11-02: 4,259 ran,
  1 error, the rest green): the `run_master` cancel test read the
  machine's real state home (the in-build suite runs without the
  LOCALAPPDATA isolation local dev runs use) and, on a field-tested
  box with a stored `last_folder`, took the stored-folder reuse path
  with the mocked `tk.Tk` and failed at the waiting-view status
  variable. The test now uses an isolated state home, a new
  deterministic test covers the stored-folder reuse path, and the
  waiting-view status variable plus the table-picker selection
  variable in `master_ui.py` now carry an explicit master (the window
  root) instead of relying on the tkinter default-root lifecycle.

## 0.24 (2026-11-01)

Trainer tick sounds (user field request 2026-11-01): the generated
trainer now plays the short tick sounds of the original native
trainer generator's character - a distinct double tick on a confirmed
attach to the game process, and a high / low single tick on a manual
on/off toggle of an item (row switch, group heading, or hotkey-
dispatched activation toggle, i.e. every confirmed toggle path, CE
parity).

- New `src/ct2trainer/native/trainer_sounds.py`: deterministic
  clean-room synthesis of the three ticks as 8-bit unsigned mono
  11025 Hz RIFF/WAVE bytes (on ~5.5 kHz 28 ms, off ~3.7 kHz 28 ms,
  attach = double 3.7 kHz tick with a silent gap; the format and
  pitch character follow the CE 7.5 native trainer generator's built-in
  `tick1.wav` / `tick2.wav` Activate/Deactivate pair, measured
  read-only - no CE asset bytes are copied).  `play_sound(kind)` is
  best-effort: Win32 `winmm` `PlaySound` with `SND_MEMORY | SND_ASYNC`,
  a stable named result string (`played` /
  `skipped: non-windows platform` / `refused: <reason>`), never raises
  into the UI; buffers are cached at module scope because
  `SND_MEMORY` requires the buffer to stay alive for the playback.
- `ui.py`: the old 880/440 Hz sine `play_toggle_sound` helper is
  replaced by `trainer_sounds.play_sound` at every confirmed toggle
  site (row switch + group heading toggle now both sound) and on the
  attach success transition detected in `TrainerWindow.poll()` (the
  engine memory handle going from nothing to a live target plays the
  attach tick exactly once per (re-)attach; failed attach attempts
  stay silent).
- `engine.py`: confirmed activation toggles dispatched through the
  hotkey path (OS bridge drain or programmatic `dispatch_hotkey`)
  surface as `(record_id, resulting-active)` pairs through
  `TrainerEngine.pop_hotkey_ui_toggles()` so the UI tick matches CE's
  on-every-toggle behavior; value-action hotkeys are not recorded.
- Tests: new `tests/test_native_trainer_sounds.py` +21 (synthesis
  shape/determinism/character, named playback refusals, hotkey-surface
  recording contract, real-Tk attach-transition / manual-toggle /
  group-toggle / hotkey-toggle wiring); `tests/test_native_ui_tone.py`
  (4 tests) superseded and removed with the old helper.  Full main
  suite 4,193 OK / 30 expected skips on `main` @ `60dbc21` (2026-11-02), zero catalog delta vs `blocked-catalog-023-field-fixes`
  (151/151 loaded, 117,809 total / 116,756 supported / 60,161 staged /
  1,053 blocked / 0 load errors; run `blocked-catalog-024-sounds`).

## 0.23 (2026-11-01)

Master Trainer roadmap complete (MT-6 / MT-7 / MT-8 / MT-9) - the full
feature set of the all-in-one "Forever Master Trainer" front end,
plus the waiting-view observability work and the ask-on-first-start
table-folder parameter (branch `native-0.23-master-roadmap`; lane
`lane-mt8-frozen-entry` merge `deed3c5`, lane `lane-mt67-sidecar-deck`
merge `cee58b7`, root integration `b2d0344`, MT-9 load-gate branch
`native-0.23-load-gate` merge `98a9226`; `main` @ `98a9226`):

- **MT-8 frozen Master entry point**: `tools/native_master.py`
  frozen to `CT2Trainer-Master.exe` with the user-provided
  `Master_Trainer.ico` (windowed; lazy `master_ui` import so
  `--help` and the named exit-2 refusals never require tkinter or a
  display; CLI mirrors the `master` subcommand: optional folder
  positional, `--state-dir`, `--debug-log`, `--poll-ms`). `build()`
  freezes it after the converter (no `CT2BASE1` marker - templates
  are converter-only), runs the CE-content `inventory()` scan, adds
  it to `payload-inventory.json`, the `build.json` outputs and the
  portable ZIP next to the converter - the Master Trainer is now
  part of every build. `scripts/Build-Native.ps1` unchanged (its
  single `build()` call emits the new EXE + ZIP entry). +8 tests.
- **MT-6 per-table settings sidecar**: `settings_sidecar.py`
  `MasterSettingsStore` keyed by the table content sha256 (never by
  path), layout `<state home>/settings/<sha>.ct2trainer.json`;
  `load_for` returns `(document, [])` / `(None, reasons)` - absent
  file is normal, `SettingsRejection` reasons pass through
  displayable (never a silent reset to defaults), structural
  `SettingsError` named; `save_for` derives the known-id set from
  the document and refuses an all-empty draft with the named
  `nothing to persist`; reuses the tested `SettingsModel` unchanged.
  UI wiring: restore on load (a refused stored document is shown
  with its named reasons and the session continues without it),
  save on close (back-to-Master and window close). The on/off wish
  persistence itself stays on the engine state store (MT-4). +17
  sidecar tests, +2 UI wiring tests.
- **MT-7 SteamOS / CheatDeck target route (documented-route scope)**:
  `steamdeck_route.py` `AttachRoute` + `attach_gate` /
  `require_engine_attach` / `route_text`; Windows -> attach
  available through the unchanged native engine path; Linux/other ->
  named `DeckAttachUnavailableError` carrying the documented route
  (Proton-wrapped standalone CT2Trainer Windows trainer EXE,
  CheatDeck-compatible; the Linux/SteamOS Master Trainer runs
  detection + table index + waiting UI only; the owned Linux attach
  backend remains a later work item). The gate runs before any
  engine creation (a refusal fails the load through the
  orchestrator's named loop guard); the waiting view shows the
  route hint permanently on non-Windows. Deliberately NOT a Linux
  attach backend - the real Deck protocol run with exact build
  hashes stays root/user field work
  (`tests/deck/compatibility-matrix.md`). +13 route tests, +3 UI
  wiring tests.
- **Waiting-view observability**: the waiting view now shows a
  compact metadata line (table counts, bound process names, last
  scan time, the state home location) and a live "Running now" line
  (bound processes visible in the latest snapshot, with PIDs);
  table rows for a running process are marked `running (PID n)`;
  `TickOutcome.running` carries the live bound-process list from
  the orchestrator tick (stable name/PID order on every tick path).
  +6 orchestrator tests, +5 UI tests.
- **Ask on first start for the table folder** (CT source directory
  parameter): an explicit folder argument (CLI or frozen EXE)
  always wins; without one, the last-used folder persisted in the
  state home (`master-settings.json`, new checksum-bound
  `master_state.py` module with named `MasterStateRefusal` and
  tolerant load) is reused when it still exists; only a genuinely
  first start (or a stale stored folder) shows the directory
  picker. +15 tests, +3 UI tests.
- **MT-9 load-time table compatibility & size gate**: `table_gate.py`
  `gate_table_for_load` re-proves one table file against its index
  entry at the moment the load is requested (auto-load or picker):
  missing file / not a regular file / stat-or-read failure / empty /
  exceeds the 32 MiB load limit (33,554,432 bytes - the bound the
  table parser and the plan compiler enforce) / changed since the
  last scan (a named stale refusal: Rescan refreshes the index and
  re-arms; also keeps the MT-6 sidecar keying - the table content
  sha256 - consistent with what the trainer loads) / not loadable by
  the tested `read_table` parser (malformed XML, DTD/entity input,
  unparseable legacy binary - the `LegacyCTError` named error passes
  through displayable) / changed during analysis. Cheapest-first
  ordering (no parser call for a stat-level refusal); every refusal a
  stable named code + displayable detail. The default plan compiler
  raises the named `TableLoadGateRefusal`, so a table load failure is
  handled gracefully even when the target process was found: no
  crash, named error dialog + status line, the orchestrator's
  fail-closed loop guard records the exact (name, PID) pair (no
  hot-retry), Rescan / Retry load re-arm, and the picker is not
  re-issued for a failed pair (named suppression until an explicit
  retry). +22 tests (16 gate, 2 orchestrator, 4 UI).
- **Also in the 0.23 content (same-day field fixes merged to
  `main` after the MT-9 merge)**: placeholder headings no longer
  create plan-level symbol dependencies (`28c9b57`, +10 tests - the
  WP-32/WP-33 non-actionable placeholder display-address requires are
  display metadata, never runtime writes, so neither the validate-plan
  symbol walk nor the engine dependency walk treats them as
  dependencies) and the Sinking City 2 hotkey-bridge field fix
  (0.22.1 lane: T1 named missing-export guard, T2 engine containment
  of bridge faults as deduped named warnings, T3 loop-thread close
  protocol, T7 persistence ordering; merge `4e9b95b`, +11 tests).
- No new trainer functionality: the Master stays a wrapper around
  the tested engine. +115 tests in total (4,061 -> 4,176); catalog
  zero delta (`blocked-catalog-023-master-roadmap` at `b2d0344`,
  `blocked-catalog-023-load-gate` at `98a9226` and
  `blocked-catalog-023-field-fixes` at `4e9b95b`, all 2026-11-01:
  151/151 loaded, 0 compile errors, 117,809 total / 116,756
  supported / 60,161 staged / 1,053 blocked / 0 load errors - zero
  delta vs `blocked-catalog-022-rearm`, per-table count and reason
  changes: 0).

## 0.22 (2026-11-01)

FO4 field-fix cycle - bounded automatic re-arm of scan-missed enables,
plus explicit "Try again" and "Re-attach" actions (branch
`native-0.21-fo4-rearm`, merged `main` @ `a12a0b6`; commit `5704fd2`,
5 files, +1,005/-62). Driven by the Fallout 4 0.20 field test
(2026-10-31, Steam Deck / Proton): 6 of 8 auto-on wish restores failed
`ScanMiss` while the game was still loading and stayed off; manual
taps kept missing the same way.

- **Bounded automatic re-arm**: any enable that fails with `ScanMiss`
  (manual toggle, wish restore, at any depth) is armed; the engine
  re-runs the full enable path every 30 s (`REARM_INTERVAL_SECONDS`)
  up to 10 attempts (`REARM_MAX_ATTEMPTS`) while attached. The budget
  resets on every confirmed (re-)attach; the armed set and
  `enable_failures` survive a target exit within one trainer session;
  exhaustion stops automatic retries; value-read failures and all
  other named refusals are never armed (plain-failed contract
  unchanged).
- **Manual "Try again"** row action (context menu, disabled when the
  last attempt succeeded): immediate full-enable retry that resets the
  re-arm budget after exhaustion.
- **Top-level "Re-attach" header button**: detaches the live target
  through the normal engine teardown (`_detach_current_target`,
  extracted from the target-exited poll branch) and re-enters the
  waiting attach cycle - fresh game process, fresh re-arm budget;
  named refusals while closed/blocked/busy.
- JSONL events: `rearm-scheduled`, `rearm-attempt {attempt,max,result}`,
  `rearm-succeeded`, `rearm-exhausted {attempts}`;
  `reattach-requested`, `reattach-done {pid}`, `reattach-failed
  {reason}` (deduped per request across the five unattached
  attach-failure points), `reattach-detached`.
- `tests/test_native_rearm.py` (+17: 10 engine + 7 UI/pure);
  `RowSnapshot` gains validated `enable_failed`/`rearm` fields and the
  row sublabel shows "re-arming n/10 (last: ScanMiss)" / "enable
  failed: <reason> - Try again".

Field findings recorded, not fixed here (tracked for the next
field-fix cycle): The Sinking City 2 0.19 log (3 sessions: Windows x2 +
Deck x1) shows an unguarded `RegisterHotKeyW` missing-export path (raw
`AttributeError` where the module docstring promises the named
non-blocking `HotkeyRegistrationError`), hotkey failures
hard-blocking the engine incl. `close()`, and a deterministic
close-timeout + access violation in the bridge message loop (window
created on the main thread, loop thread pumps its own empty queue,
`WM_BRIDGE_QUIT` undeliverable while `destroy()` blocks the main
thread in `join(5s)`); plus a transient-read `PatchConflict` (Win32
299) ~1 h after attach and a state-lock first-restart refusal. The
hotkey-bridge code is unchanged in 0.22. Full main suite 4,061 OK /
30 expected skips (canonical path, 2026-11-01; 4,044 from the 0.21
build + 17 re-arm tests); in-build suite on the 0.22 build (run
`native-20261101T075049Z-f32c112d`, cut from `main` @ `2b24a1c`,
2026-11-01): 4,061 OK / 30 expected skips, 0 failures - fully green
at the canonical build path. Catalog: zero delta
(`blocked-catalog-022-rearm`:
151/151 loaded, 0 compile errors, 117,809 total / 116,756 supported /
60,161 staged / 1,053 blocked / 0 load errors).

## 0.21 (2026-10-31)

RT-5 complete + Master Trainer — the final two implementation items of the RT-5
inventory (every item A, B, C, C2, D, E, F, G now landed) plus the new
all-in-one "Forever Master Trainer" front end (one long-lived trainer
window that indexes a folder of `.ct` tables (sub-folders included) and
auto-loads the matching table when a bound game process appears, handoff
into the exact standalone trainer UI, and per-table on/off persistence on
top of the existing engine state store):

- RT-5 item B — table-level `<CheatCodes>` code list as `code_patch`
  plan records (lane `native-0.20-rt5-b`, merge `9ef4a74`):
  fail-closed per-entry table parse (whole-byte hex byte-capture codec
  with `<Byte>` child and text fallback, 4096-entry section bound,
  per-entry named drop warnings; `GroupHeader` rows become supported
  heading records — the corpus carries zero of them); compiler
  `code_patch` projection with synthetic plan IDs at 2**32+ (above the
  RT-5 C2 dynamic-record journal range 2**31+1..2**31+4096 — documented
  deviation from the task's 2**31 base), CE code-list address forms
  (`AddressString` verbatim / `ModuleName` + normalized offset /
  absolute hex) with a compile-time static symbol-free expression gate
  that blocks only the offending entry, `CheatCodes` added to the
  interpreted-section whitelist (the load-time warning is gone), both
  plan validators re-deriving the canonical shape with forged-entry
  refusals; engine toggle lifecycle with named refusals
  (`code-patch-already-active`, `code-patch-target-changed`,
  `code-patch-restore-mismatch` + engine block), executable pages
  routed through the verified coordinator hook journal, data pages
  through the ordinary byte transaction, standard enabled-wish
  persistence with re-attach re-enable and close-time restore (disable
  restores the bytes captured at enable time — documented superset of
  CE); UI switch rows with the `code` chip in Switches/On/Saved.
  `tests/test_native_rt5_code_patch.py` +26. Catalog remeasure on main
  (run `blocked-catalog-020-rt5-be`): 117,634 -> 117,809 total,
  116,581 -> 116,756 supported (+175 — the full 22-table `CodeEntry`
  census, zero GroupHeader rows), 1,053 blocked and 60,161 staged
  unchanged, 0 load errors, zero newly blocked, zero reason changes.
- RT-5 item E — `messageDialog` decision (branch
  `native-0.20-rt5-be`, merge `b8bb4ee`): hosted as a safe logged
  no-op returning 0 (mbOK, truthy in Lua) with the CE 7.5 argument
  shapes (message / title+message / dialogtype / buttons) and nil
  argument tolerance (corpus table Lua passes undefined button
  constants as nil); debug-log event `message-dialog` (title + message
  truncated, argument count); both spellings admitted in record scope
  and table scope (`TABLE_LUA_READ_ONLY_NAMES`, 47 corpus table-Lua
  call sites). `tests/test_native_rt5_message_dialog.py` +22 plus pin
  updates. Zero catalog delta (run `blocked-catalog-rt5e-iteme`) —
  runtime host behavior, static catalog unaffected.
- New closing analysis `documentation/ce-vs-ct2trainer-analysis.md`
  (CE 7.5 behavior vs the CT2Trainer implementation, measured end
  state vs the 100% goal, the 17-row bounded-deviation register, the
  RT-6/RT-7 verification path; file:line-verified CE 7.5 citations).

- New `ct2trainer.native.master_trainer` package (`CONCEPT.md` +
  `ROADMAP.md` in-package):
  - `table_index.py` — incremental folder index: only a directory
    listing is done per reconcile; an entry is re-read only when its
    `(size, mtime_ns)` fingerprint changed; a content-identical
    (sha256-equal) refresh keeps the derived process names without
    re-parsing; removed paths drop; unreadable tables stay visible with
    a named error and bind no process. Canonical JSON persistence with a
    sha256 checksum (foreign schema/root and tampered checksums are
    refused); the index lives in the state home, never in the table
    folder.
  - `process_watch.py` — read-only process snapshots: Toolhelp32 on
    Windows, `/proc/<pid>/exe` on Linux/SteamOS (Proton-compatible);
    pure, deterministic matcher (ordinal case-insensitive for ASCII,
    casefold otherwise).
  - `orchestrator.py` — waiting → choosing → loading → active state
    machine: unique-match auto-load, multi-table picker contract,
    deterministic first-casefold-name / lowest-PID rule, fail-closed
    loop guard (failed and deferred exact (name, PID) pairs; PID-gone
    re-arm; explicit retry), open-choice stability.
  - `master_ui.py` — waiting view (folder, index Treeview, status line,
    Rescan / Change folder / Retry load), modal table picker with
    "Not now" deferral, and the trainer handoff with the same
    startup-recovery flow as the standalone trainer.
- `TrainerWindow` gained an optional `master_back` callback: one extra
  "⬅ Master" header button that closes the engine cleanly and returns
  to the waiting view in the same window; `None` keeps the standalone
  trainer byte-identical.
- New `ct2trainer native master [FOLDER]` CLI subcommand
  (`--state-dir`, `--debug-log`, `--poll-ms`); directory picker when
  the folder argument is omitted.
- Build allowlist: the `master_trainer` subpackage (code + in-package
  docs) and the user-provided `Master_Trainer.ico` / `Master_Trainer.png`
  ship in the source ZIP; `window_icon_path("master")` resolves the
  master window icon.
- Source fixes (found during test-lane development):
  - `process_watch.py`: `from ..local_processes` → `from
    ...local_processes` (the module lives at `ct2trainer.local_processes`,
    not `ct2trainer.native.local_processes`; the Windows backend raised
    `ModuleNotFoundError` on first tick).
  - `master_ui.py` `_open_picker`: `pady=(12, 4)` / `pady=(4, 12)` moved
    from Tk widget options to `.pack()` (tuple padding is only valid as a
    pack/grid option, not a widget constructor argument; the picker
    crashed with `TclError: bad screen distance` every time it opened).
  - `master_ui.py` `_confirm_recovery`: a declined recovery prompt
    (user says "No") now fails the load instead of returning `True`
    (which re-prompted up to 4 times then stranded the orchestrator in
    `STATE_LOADING`; the standalone trainer exits on decline).
  - `master_ui.py` `_enter_trainer`: the non-convergence path
    (`attempt > 4`) now calls `_fail_trainer_start` so the orchestrator
    returns to `STATE_WAITING` and the loop guard arms, instead of
    leaving the state machine stuck.
  - `master_ui.py` `set_folder`: added `TableIndex` to the local import
    (was missing, causing `NameError` on every "Change folder" click).
- Tests: `tests/test_native_master_index.py` (18),
  `tests/test_native_master_process_watch.py` (35),
  `tests/test_native_master_orchestrator.py` (42),
  `tests/test_native_master_ui.py` (46). 141 master-trainer tests total.

Queued (roadmap MT-6/7/8): the `settings_model.py` sidecar wiring, the
SteamOS/CheatDeck attach route, and the frozen
`CT2Trainer-Master.exe` entry point.

Suite: 3,902 OK / 26 expected skips on `main` after the RT-5 B/E merges
(canonical checkout, CT2TRAINER_NASM); full dev suite on the merged
branch `native-0.20-master-trainer`: 4,011 OK / 30 expected skips (4,044
ran; the only 3 failures are the known worktree path-dependent
baseline-reproducibility tests, which pass at the canonical build path);
in-build suite on the 0.21 build (run
`native-20261031T211046Z-14707e12`, cut from `main` @ `9a725a8`,
2026-10-31): 4,044 OK / 30 expected skips, 0 failures - fully green at
the canonical build path. One additional fix landed with this cycle:
`tests/test_native_icons.py` now pins the `Master_Trainer` icon contract
and the three-kind `window_icon_path` resolution (the pre-MT-5
unknown-kind refusal test used `"master"` as its probe value, which
became a valid kind). Catalog: latest remeasure
`blocked-catalog-020-rt5-be` (117,809 total, 116,756 supported incl. the
+175 code-patch rows, 1,053 blocked, 60,161 staged, 0 load errors); the
Master Trainer feature itself has zero catalog effect (no plan-builder
code touched).

## 0.20.1 (2026-10-30)

Release-content correction - re-cut of the 0.20 branding-icon build:

- The 0.20 changelog suite line now states the verified in-build
  suite (3,854 OK / 26 expected skips, fully green at the canonical
  path) instead of the worktree dev-suite observation, and cites
  the catalog remeasure `blocked-catalog-020-icons` (zero delta vs
  `blocked-catalog-019-field`).
- No code or asset changes: the re-cut reproduces the 0.20 content
  with the corrected release changelog.

## 0.20 (2026-10-30)

New branding icons (user-provided artwork, 1024x1024 masters):

- The CT2Trainer tool icon (the "Generator" artwork) now ships as
  `src/ct2trainer/assets/ct2trainer-converter.ico` (plus its 1024x1024
  reference PNG). It is embedded in the frozen `CT2Trainer-Converter.exe`
  via PyInstaller and set on the converter window at runtime
  (`window_icon_path("converter")`).
- The standalone trainer icon now ships as
  `src/ct2trainer/assets/ct2trainer-trainer.ico` (plus its 1024x1024
  reference PNG). It is embedded in the `CT2Trainer-Template` stub, so
  every trainer .exe the converter generates carries it, and set on the
  trainer window at runtime (`window_icon_path("trainer")`).
- `tools/create_icons.py` no longer draws the old placeholder artwork: it
  now rebuilds the multi-size ICO files (16-256 px, 32 bpp) from the
  committed PNG masters, so a rebuild can never silently replace the
  shipped icons.
- New `tests/test_native_icons.py` (+4 tests) pins the committed icon
  contract: both ICOs carry the full 16/24/32/48/64/128/256 px 32-bpp set
  with intact image blobs, both PNG masters are 1024x1024, and
  `window_icon_path("converter"|"trainer")` resolves to the committed
  assets (unknown kinds are refused).

Suite: 3,854 OK / 26 expected skips in the in-build run
`native-20261030T184820Z-b9d6dc07` cut from the canonical path
(the 3 path-dependent baseline-reproducibility tests pass there,
their committed baselines embedding the canonical repo path).
Catalog: remeasure `blocked-catalog-020-icons` (2026-10-30: 151
tables, 117,634 entries, 60,161 staged, 1,053 blocked, 0 load
errors) is zero-delta vs `blocked-catalog-019-field`. Asset-only
change: no trainer behavior change.

## 0.19 (2026-10-30)

Field-fix release after the 0.18 field tests (Sinking City 2, South of
Midnight) plus full staged-options support for the South of Midnight
table:

- Hotkey-bridge Windows crash fix (0.18 field report: the trainer
  process crashed with access violations inside the real Win32
  hotkey-bridge seam): the bridge window now uses the correct
  `HWND_MESSAGE` value `-3` (previously `c_void_p(-1)`, i.e.
  `HWND_BOTTOM`, which made `CreateWindowExW` fail with Win32 error
  1400 in the frozen environment); all Win32 prototypes now declare
  explicit `argtypes`/`restype` up front (previously undeclared calls
  defaulted to 32-bit `c_int` arguments/return values, truncating
  64-bit `HINSTANCE`/`HWND` pointers and causing AVs in
  `RegisterClassExW` / `CreateWindowExW` / `DefWindowProcW`);
  `RegisterHotKeyW` / `UnregisterHotKeyW` are guarded behind an
  availability flag so stripped or minimal user32 builds (e.g. some
  embedded Python distributions) can still construct the window
  lifecycle without hotkey registration. `run_trainer` now logs
  `hotkey-bridge-started` (with the bridge HWND) and
  `hotkey-bridge-failed` debug events. Regression test
  `tests/test_native_os_hotkeys.py` +1 (real-seam connect / register /
  close lifecycle, Windows-only; reaching the asserts is the
  regression signal since an AV would kill the runner).
- Value-read observability (Sinking City 2 field finding: staged
  pointer-chain value reads failed silently and surfaced only as a
  blank "unavailable" with no trace): `TrainerEngine.read_value` now
  records every failure as a `value-read-failed` debug-log event
  carrying the exception, deduplicated per identifier per distinct
  cause (the UI tick retries every visible value row on every poll, so
  a persistently failing read must not flood the log), then re-raises
  so callers still surface the refusal as "unavailable". The log entry
  names the record label, so a broken pointer chain (e.g. a pointer
  whose base symbol has no live value yet) is diagnosable from
  `ct2trainer-debug.log` without target access.
- New `describe` CLI subcommand: `ct2trainer native describe <table>`
  prints, per record, the raw script source, the plain-language
  assessment and the concrete actions the trainer performs for the
  entry (reusing the 0.18 row-details builders from `ui_script_view`,
  so CLI and UI stay in sync); flags `--process` (suggestion from the
  CT when omitted), `--id <recordId>` (single record) and `--json`
  (machine-readable output). `tests/test_native_describe.py` +13
  tests.
- Staged-options support (South of Midnight field report: "the staged
  options are not correctly supported; no staging happens - the options
  should become selectable only after the prerequisites are active"):
  the plan-level staging, the engine gates (`_require_staged_live` on
  value read / write / freeze) and the two-level parent cascade
  (flagged master -> nested child provider -> staged values) were
  proven correct by the new cascade test; the real gaps were in the
  UI: (a) a staged-pending value row still opened the inline editor on
  tap, letting the user type into an editor that could never apply -
  now `TrainerWindow._open_value_editor` routes the tap through
  `engine.read_value` so the engine's named staged refusal ("Staged
  record 'X' requires active provider 'Y'") lands in the status line
  immediately and the editor never expands; live or non-staged values
  open the editor exactly as before; (b) `moAlwaysHideChildren` was
  not implemented anywhere - the compiler now emits the optional
  `hidden_children` plan marker for records carrying that option with
  children, and the row model suppresses the flagged entry's whole
  subtree (but not the flagged parent row itself) in every view,
  presentation-only, engine-side cascade untouched. No corpus table
  uses the flag, so the canonical plans stay byte-stable.
  `tests/test_native_staged_cascade.py` +2 (SOM-shaped two-level
  cascade: pending refusals -> master ON cascades to the child
  provider -> both values read/write -> master OFF re-pends both) and
  `tests/test_native_staged_options_ui.py` +8 (row-model suppression
  with a no-flag control case plus the South-of-Midnight shape, and
  the staged-pending tap guard: pending refuses + names the provider,
  live and non-staged open the editor without touching the engine).

Suite: 3,850 OK / 26 expected skips. Catalog: unchanged vs
`blocked-catalog-rt5d-main` (151 tables, 117,634 entries, 60,161
staged, 1,053 blocked, 0 load errors).

## 0.18 (2026-10-28)

- Trainer UI row-details window: right-click / long-press on a row now
  offers "Row details" (leads the context menu) - a single read-only
  window combining the raw script source (static Auto Assembler /
  embedded Lua / global program / normalized operation list), the
  plain-language assessment (what it does / what is known) and the
  concrete actions the trainer performs for the entry (enable/disable
  operations, capabilities, CE Lua API calls in embedded-Lua sources,
  memory writes for value rows, group-activation cascade for flagged
  group headings).  New pure builders `entry_actions` / `row_details` /
  `lua_apis_used` in `ui_script_view.py` (display-only CE-API
  vocabulary, no runtime dependency); context-menu wiring refactored to
  a unit-testable `_context_menu_items` in `ui.py`; the existing
  script-preview / assessment / details items are unchanged.
  `tests/test_native_ui_row_details.py` +22 tests.

## 0.17 (2026-10-27)

- RT-4.2 runtime provider model (last RT-4 package, ~1,085-row scope):
  R3 keep-first duplicate-provider scope fallback (a blocked kept
  provider no longer strands its dependents; the first
  still-supported candidate in the keep-first scope resolves the
  symbol; single-candidate and shared-global-compatible branches keep
  their classic refusals), R4 mixed-dialect release evidence (AA
  `unregistersymbol(` release proof from `{$asm}` [DISABLE] parts per
  the CE 7.5 split-on-commas/whitespace contract, `*` wildcard and
  scalar trailing args excluded; Lua `unregisterSymbol` stays
  strict-pair per the gettop==1 handler), R7 bounded API-export
  registry (bare `call GetAsyncKeyState` / `FindWindowA` supported with
  the exact `api_exports` plan marker, forged-marker refusals in both
  plan validators, link-time resolution against the target's live
  export table with a fail-closed refusal before any write).
  Catalog: 1,351 -> 1,053 blocked (net -298: R4 Lua runtime symbol
  providers 286 rows now staged - DS2 118, HorizonForbiddenWest 82 per
  copy, ForgottonAnne dMoveValueMultiplier 2, Witcher3 bIsLevel 1 per
  copy; R7 GetAsyncKeyState 12 rows supported - ForgottonAnne 7,
  trine2 3, Witcher3 1 per copy; R3 catalog-neutral; 5 previously
  supported-plain rows re-staged through the now-supported runtime
  providers; zero newly blocked; 28 rows reason-changed, all still
  blocked and explained). Dedicated
  `tests/test_native_rt42_runtime_provider.py` (21 tests) plus the R7
  pin migration in `tests/test_native_undefined_provider_report.py`.
- RT-4.3 address expression & identifier dialect: O1 relative-address
  skip-fold over addressless script/value ancestors, O9 runtime-base
  marker staging on group headings, O3 pointer-offset expression slots
  (hex-arithmetic fold, expression slots resolved against the live
  symbol table at activation), O10 identifier dialect (digit-leading
  and dot-bearing names per the CE `label()` contract), O23
  quoted-atom module-basename refusal, O27/O4 Type:Member managed
  labels through the injected IL2CPP resolver, O13 directive-aware
  db/dw/dd/dq string bytes. Catalog: 1,743 -> 1,351 blocked (net
  -392, zero newly blocked, 12 rows reason-changed and still
  explained); dedicated
  `tests/test_native_address_expression_dialect.py` with 38 tests
  after the dedicated dialect-test follow-up.
- RT-4.5 AA directive & script coverage: named usemono() parity-scope
  refusal (O15), CE dealloc name-list semantics (O12), managed-label
  regex bounded to a {1,2} colon tail (O18), global DISABLE reset
  regions and pure-global records (O19/O21), symbol-only luaCall
  envelopes (O20), per-record symbol-handover refusals (O5). Catalog:
  1,778 -> 1,743 blocked (net -35, zero newly blocked).
- RT-4.6 input legacy & authoring gaps: actionable per-symbol
  "not registered anywhere in this table" report with raw-source
  registration survey (R5/R6 closure), x87 `st`/`st(N)` FPU-operand
  fold, optional user-symbol import. Catalog: 1,807 -> 1,778 blocked
  (net -29; 218 rows reason-changed onto the actionable per-symbol
  report, all still blocked).
- NASM 3.02 FSTP encoding audit (RT-4.6 follow-up): the "FSTP table
  defect" was a misdiagnosis - no defect in the pinned NASM 3.02 (per
  the Intel SDM table FSTP ST(i) = DD D8+i; probe artifacts came from
  snippets missing the bits directive); docs corrected in place, +3
  regression pins (byte-exact FSTP/FST forms plus a full-pipeline
  fstp st(0) roundtrip).
- Trainer UI (user feature 2026-10-24): new "Scripts" filter chip
  (every kind==script record, blocked/unselected shown dimmed with the
  exact reason) and the row context menu - script preview, copy
  script text, "What is happening here" plan-based assessment,
  details; pure text builders in ui_script_view.py, plan format and
  engine contract unchanged, +25 tests.
- RT-5 item G createThread/threadWait gate decision: option (2)
  recorded - the capability gate stays, no thread backend ships this
  milestone (a bounded owned-thread backend awaits the root design
  review); byte-stable five-stage fail-closed pins in
  `tests/test_native_rt5_thread_gate.py` (+17); census re-derived:
  exactly 2 O22 rows (Witcher3 4.02HF1_G25v2 + 4.03_G25v2, id 192) and
  77 first-word createThread usages across 18 tables (26 AA lines / 8
  tables gate-governed; 51 Lua lines / 11 tables are the separate
  lua_host cooperative-worker family).
- RT-5 item F no-effect register ratification: the rt5-api-inventory
  no-effect register is pinned as an enforced byte-stable contract in
  `tests/test_native_rt5_no_effect_register.py` (+22 tests / 12
  classes: 26 CE UI globals with exact named refusals, section-7.3
  object-method register per surface, table-level
  Structures/Signature/PublicKey/Forms/Files byte-exact warnings +
  sorted plan-inert ignored_sections, Lua lifecycle no-ops); tests
  only, zero catalog movement.
- Reference-table catalog state at the 0.17 cut: run
  `blocked-catalog-rt42-main` (2026-10-27) over the 151-path/143-hash
  frozen manifest: 151/151 load, 117,634 total, 116,581 supported
  (60,161 staged), 1,053 blocked, zero load errors; residual blocked
  rows are deliberate gates (thread capability, bounded API-export
  registry, cleanup-ownership) plus table-side symbols registered only
  by the tables' own runtime Lua (globals outside the clean-room
  provider set, user labels, bare targets beyond the registry).
  First minor release of the reference-table 100% program; full local
  suite on main after the final merge: 3,692 OK / 25 expected skips.

## 0.16.4 (2026-10-24)

- Sinking City 2 trainer-crash observability field fix (0.16.3 field
  test 2026-10-23: the trainer process died silently mid wish-restore
  - last logged event the TALENTPTR aobscan at 18:49:31, zero
  follow-up events - and the restart on PC2 was blocked by the correct
  fail-closed state-lock refusal while the game was still running):
  the TALENTPTR restore itself is not deterministically broken (it
  worked on PC1 and on PC2's second attempt after a game restart), and
  every Python-level failure path logs an event - so the silent death
  is a hard exit (native crash or external kill). The defect is the
  missing crash observability: a windowed build has unattached stderr,
  no excepthook, no faulthandler, and an unguarded Tk poll callback.
  - `debug_log.py` gains `TrainerDebugLog.arm_crash_reporting()`:
    process-wide one-time `sys.excepthook` wrapper writing a
    `trainer-crashed` JSON event (error + full traceback + pid) and
    delegating to the previous hook, `threading.excepthook` wrapper
    writing `trainer-thread-crashed` (with the thread name), and
    `faulthandler` on a dedicated append handle so native fatal
    signals (access violation, stack overflow, abort) dump every
    thread's Python stacks into the same log file. The crash handle is
    independent of `close()`, so evidence is written even after the
    engine tore the session log down. Arming emits no log event of its
    own; a re-arm (the startup retry loop may create several engines
    before the session engine is final) closes the previous handle.
  - `run_trainer` arms crash reporting once the final engine exists -
    both entry points covered (frozen launcher, source CLI run
    command).
  - `TrainerWindow.poll` wraps `engine.poll()` fail-closed: an
    escaping exception is logged as `poll-crashed`, the engine is
    blocked (writes refuse, the status line names the cause), and the
    250 ms tick keeps scheduling instead of the exception propagating
    out of the Tk after-callback and killing the windowed process.
  - The restore loop logs `restore-entry-start` (identifier + label)
    before each record's dependencies/enable, so a hard process exit
    mid-restore leaves the last in-progress entry identifiable in the
    debug log.
  - State-lock behavior is unchanged: the blocked restart while the
    target was alive remained the correct fail-closed refusal; this
    build only adds the evidence that was missing.
  - Regression tests: `tests/test_native_sc2_crash_observability.py`
    (new, 8 tests: excepthook/threading-hook/faulthandler arming,
    evidence surviving session close, one-time hook installation,
    disabled no-op, the poll guard blocking and keeping the window
    alive, restore-entry-start ordering).
  - Full local dev suite on the 0.16.4 branch: 3,479 OK / 25 expected
    skips. This build also ships the RT-4.4 value-semantics content
    merged into main (catalog remeasure `blocked-catalog-rt44`:
    1,858 -> 1,807 blocked of 117,634, zero newly blocked rows).

## 0.16.3 (2026-10-23)

- Sinking City 2 activation failure field fix (0.16.2 field test
  2026-10-22, "the trainer did not activate at all"): two independent
  defects compounded.
  - Recovery brick: every 0.16-series hook journal carries the
    WP-47/55 `value_data_ranges` field on each allocation entry
    (persisted since `ee07b60`, shipped in 0.16), but the recovery
    assessment's journal schema (`recovery.py::_hook()`) rejected it
    as an unknown field — the 0.16.2 fix had added only the sibling
    `captured_placeholders` field. Every allocation-bearing journal
    failed with "Recovery record contains missing or unknown schema
    fields" and blocked recovery behind the stale `state.lock`, so the
    trainer refused to start on every attempt. `value_data_ranges` is
    now an optional allocation-entry field validated with the
    writer-side contract (at most 4096 exact `{address, size}` spans,
    inside the allocation's `[address, address + actual_size]` bounds,
    no duplicate span); malformed inventories keep named refusals.
  - Module-snapshot retry: the first entry scan failed nine
    milliseconds after attach with `CreateToolhelp32Snapshot
    architecture modules failed (Win32 error 24)` while the game was
    still loading DLLs — the documented transient form of
    module-snapshot creation (Microsoft: "may fail with
    ERROR_BAD_LENGTH or another error code … try calling the function
    again"). `memory.py` mislabeled `ERROR_BAD_LENGTH` as 24 (the real
    code is 1116; 24 is `ERROR_INVALID_ID`) and retried only that
    mislabeled code in a tight 3-attempt loop without backoff, so the
    transient failure was never retried usefully. The constants are
    now correct, `_take_module_snapshot` retries a bounded 8 attempts
    with exponential backoff (0.05 s doubling, 1.0 s cap, ~3.5 s
    worst case) on the transient set {1116, 24, 119}, and
    non-transient errors still fail fast. The architecture-only retry
    flag is now architecture-aware (0x08 for a 64-bit target, 0x10 for
    a 32-bit/WOW64 target, which lists its modules only under
    `TH32CS_SNAPMODULE32`), and the final dual-failure message carries
    both failure codes.
  - Regression tests: `tests/test_native_architecture.py` (+4:
    transient 24 retries with backoff until success; 1116 retries;
    persistent transient exhausts 2×8 attempts with the named
    dual-flag message; x86 target falls back to the 0x10 flag) and
    `tests/test_native_recovery.py` (+2: writer-shape allocation
    journal with in-bounds `value_data_ranges` stays eligible; six
    malformed shapes stay blocked).
  - Field workaround while on 0.16.2: with the game closed and the
    previous trainer process verified terminated, delete the state
    folder (`%LOCALAPPDATA%\CT2Trainer\native\<trainer_id>`) to start
    fresh; activate only after the game has finished loading.

## 0.16.2 (2026-10-22)

- Sinking City 2 startup block field fix: a trainer left behind by a
  prior session (crash, kill, or orphaned lock after a blocked close)
  could not start whenever any hook journal in `state/hooks/` carried
  `captured_placeholders` (WP-57, shipped in 0.16) — the recovery
  assessment rejected the field as an unknown schema field, and the
  refusal repeated on every startup attempt. The field is now an
  optional journal field validated with the writer-side contract
  (`patterns.validate_placeholder_captures`: at most 16 captures,
  `s<N>` names, 1-2 hex bytes per value); malformed captures still
  block with the named refusal "Hook journal placeholder captures are
  invalid". Regression tests: `tests/test_native_recovery.py` (+2).
  Field workaround until this build: with the game closed and the
  previous trainer process verified terminated, delete the state folder
  (`%LOCALAPPDATA%\CT2Trainer\native\<trainer_id>`).
- RT-4.1 symbol provider fidelity (reference-corpus closure cycle):
  duplicate provider entries are no longer blocked wholesale — the
  first registration wins, the duplicate registration is shadowed, and
  every non-duplicate registration in the same entry still takes
  effect (CE `dupIgnore` alignment; documented safe narrowing vs CE's
  last-wins runtime registration); repeated names inside one `label()`
  list are now tolerated (CE's duplicate-declaration check is disabled;
  multiple `name:` definitions and undefined names stay refused); the
  wildcard-cleanup static guard is removed (the wildcard sweep is
  scoped at runtime to the program's own phase-owned symbols). Full
  suite: 3,415 OK / 25 expected skips. Original-table catalog remeasure:
  2,698 -> 1,858 blocked of 117,624 plan entries (842 unblocked, 2
  explained Cyberpunk shared-global regressions per the pinned
  contract, zero unexplained supported regressions).

## 0.16.1 (2026-10-21)

- Sinking City 2 field fix — the table-load warnings are now accurate
  instead of reading like failures (the table loaded and worked; the
  three warning lines were stale or confusing review notes):
  - The local CE table-version reference moved 45 → 46. CE 7.5 (the
    behavior reference) writes 45; 46 is issued by newer CE builds and
    is field-verified (The Sinking City 2 table) to load and compile
    unchanged, so v46 tables no longer warn. Genuinely newer versions
    still warn.
  - The `{$LUA}` warning now states the supported behavior: the
    embedded Lua runs in the trainer's built-in Lua runtime when the
    record activates.
  - The external-action warning is split per API: `ShellExecute` is
    documented as the safe no-op the native trainer performs (WP-56),
    while `messageDialog` — which the native Lua runtime does not
    implement — keeps a real review flag naming the activation
    failure.
- RT-1 measurement content: the shipped `feature-coverage.json` now
  carries the repaired table-count prose (stale 15/27-table fields
  fixed at the tool source, artifacts regenerated under pinned run id
  `w4b4-case30-20261020081722Z`).
- Versioning rule (user decision 2026-10-21): every build gets a new
  version number; bug-fix builds bump the patch (0.16 → 0.16.1 →
  0.16.2), feature releases bump the minor (0.16 → 0.17).

## 0.16 (2026-10-20)

- Wave 4 reference-corpus closure features (all W4 lanes integrated in
  the `native-0.16` cycle, merged into `main`; corpus cases 26…31
  pinned, gate:1 → 30 tables):
  - AA / table grammar (WP-43/44/45/46): single-quoted string data
    literals (both dialects, shared literal path); pre-`[ENABLE]`
    `registerSymbol` + inert comments-only scripts demoted to
    supported no-action; selection-aware provider dedupe, decimal and
    signed `<Offset>` values, missing dropdown-link demotion,
    indirection bound 2 → 6; `<UserdefinedSymbols>` interpretation
    (table-level static symbols, hex-only fail-closed, script
    providers keep winning) + empty-section warning suppression; Lua
    literal `registerSymbol` provides extraction + one-shot provider
    handover (release-on-detach at owner-scope retirement).
  - Symbol cycles and dynamic providers (WP-48/49/50): self-provision
    exclusion in the compiler dependency pass (a record's own
    registration satisfies its own reference; true cross-record
    cycles stay fail-closed with the exact reason); dynamic
    script-parent address providers (record-Lua `AddressList`
    providers with the `address_provider {provider_id, symbol: null}`
    marker, bounded static extraction, engine `dynamic_addresses`
    state); `luaCall(lua_aobscan(…))` / Lua-internal static symbol
    provision.
  - Engine / runtime (WP-47/51/52/55/56): allocation-only engine
    enable (no game write, symbol-only publish); Lua-assembled AA
    program admission at plan level (provable `autoAssemble` call);
    Lua broker scan/utility surface (`memscan.Result`/`OnlyOneResult`,
    `firstScan` nil rounding, found-list `getCount()`/`getAddress(i)`,
    `createStringlist`); AOB multi-match → first (lowest-address)
    match semantics per the CE `aobscan` family + match count/offsets
    in the debug log; record-Lua CE-global stubs (`OpenProcess` no-op
    success, `syntaxcheck` false, `ShellExecute` safe stub, no-op
    menu surface, named refusal for remaining missing globals).
  - Hotkeys and table-Lua phase 2 (WP-53/54): Windows OS hotkey
    capture bridge (message-only window, `RegisterHotKey`/`WM_HOTKEY`
    → queue, named refusal + programmatic-only fallback) +
    group-heading hotkeys (plain `moHideChildren` headings toggle
    their own applied state without child propagation, flagged groups
    cascade via the parent-activation path); persistent table-scope
    `createTimer` (record replay scheduler-free via inert stubs),
    table-scoped `registerSymbol` via `TableSymbolOwner` into plan
    field `table_lua_symbols` (supported record providers always
    win), consumer resolution through table symbols without
    `dependency_ids`, inverted teardown (table scope retires last,
    symbols released exactly once), UDS reseed on every confirmed
    attach.
  - Placeholder-token AOB (WP-57): `s1`/`s1.2` 2-byte tokens treated
    as wildcard displacements with the matched bytes captured at link
    time and persisted for the `[DISABLE]` restore; external region
    symbols get a named fail-closed reason.
  - Trainer UI (WP-58): compact touch-first row grid (canvas list,
    64/72 px rows, pill toggle + full-row tap, group sections
    replacing breadcrumb drill-down, inline value editor, state
    accent + transient reaction feedback); plan output byte-stable.
- Pinned corpus: cases 26/27/31 (W4 B1–B3) and 28/29/30 (W4 B4) pinned
  as the 25th–30th tables; chain `w4b4-case30-20261020081722Z`: 30
  tables, 6145 records, 6143 expected actions, feature matrix 42/42
  in-scope, weights 7475/7475.
- Reference corpus (local-only assessment, not shipped): catalog
  re-run post W4 B4 2,698 / 117,624 blocked (−934 vs post B1–B3).
- Post-release field fixes (2026-10-20 re-cut, from user testing of the
  first 0.16 build):
  - WP-58 UI startup crash: `TrainerWindow._button` hard-coded
    `font=`/`height=`/`pady=` on top of the `**style` spread, so the
    filter-chip call (height+font overrides) raised
    `TypeError: tkinter.Button() got multiple values for keyword
    argument 'height'` — every generated trainer crashed at startup.
    The defaults now live in the style dict so caller kwargs override
    them; a second latent WP-58 regression (pagination buttons passing
    the tuple `padx=(0, 4)` as a widget option, TclError "bad screen
    distance") moved the padding to `.pack()`. Regression test with
    real tkinter widget construction for every call-site signature:
    `tests/test_native_ui_button.py`.
  - Sinking City 2 field case (the "1 Activate me! Attach game's
    process" step and the multi-step pointer activation): the
    `OpenProcess` attach call runs as the WP-56 identity no-op; the
    chain (one-shot attach record → multi-match AOB pointer provider
    with `registersymbol` → staged pointer value record) now has
    end-to-end runtime proof on owned fake memory with the real Lua
    host — first-match scan resolution, symbol registration, byte-exact
    patch restore, the named staged gate, hex pointer-offset chase, and
    the named refusal for a process-name mismatch:
    `tests/test_native_sc2_attach_chain.py`. Field note: if a record
    fails at runtime with "pattern not found", the table's AOB pattern
    is missing from the installed game build (table/build mismatch —
    fail-closed by design, cf. the 2026-10-18 Sinking City 2 analysis).
  - State-lock self-repair and reliable restart (2026-10-21, user
    testing of the 0.16 re-cut, Sinking City 2): a target exit racing a
    hook-receipt read (Win32 299) blocked the engine; `close()` then
    refused permanently on the block flag and orphaned `state.lock`
    (the atexit net could not release it while a process session
    remained), so the trainer could not be restarted ("state.lock
    already exists"). Fixes in `src/ct2trainer/native/engine.py`:
    (1) `close()` now completes the exit cleanup when blocked but the
    target is gone — saved wishes survive in `state.json`; a
    still-alive target keeps the fail-closed refusal; (2) the atexit
    net releases the session and the lock when the target is provably
    gone; (3) the stale-lock startup probe retries a transient
    "unknown" owner observation once and, when the owner is proven dead
    but the full assessment is not eligible (most commonly: the
    previous session's target is still running), surfaces the concrete
    assessment reasons in an actionable refusal instead of the generic
    "delete that folder" line. Regression tests:
    `tests/test_native_stale_lock_selfheal.py` (7 tests) plus the
    updated never-attached-variant close assertion in
    `tests/test_native_engine.py`. Field note: the one non-working
    cheat in the field log (Inf Items, record id 15) is a table/build
    mismatch — the AOB pattern is absent from the installed build
    (ScanMiss logged twice), fail-closed by design, no code fix.

## 0.15 (2026-10-18)

- Prefix-cut byte-patch validation (field fix from the 0.14-ext2 Great
  Circle debug log, `d15268a`): the Stealth Mode and No Reload (2nd hook)
  entries use the classic byte-patch technique `db 90 E9` over a 6-byte
  conditional jump (je/jae rel32), reusing the original displacement to
  form `nop; jmp rel32`. Stage-time validation only accepted entry
  patches whose recorded original bytes AND whose patch bytes each decode
  as complete instruction sequences, so both halves of the legitimate
  prefix patch were rejected ("Entry patch cuts or contains an invalid
  instruction.") and the entries silently failed on attach.
  - `aa_program.link_program` now proves a prefix cut against the live
    target at link time: the recorded original must fail the
    complete-sequence check, the first original instruction boundary at
    or past the patch length must resolve inside a live window, and the
    patched prefix plus the original tail up to that boundary must decode
    as complete, valid instructions with no call/interrupt hazards.
    Passing blocks carry a `prefix_cut: true` flag.
  - `hooks._normalize` keeps the historical strict complete-instruction
    contract for every block; only blocks flagged `prefix_cut` at link
    time get the live re-verification (window read, head-byte match
    against the recorded original, boundary resolution, post-patch
    decode, control-flow safety) and fail closed on unreadable targets.
- Wave 3 reference-corpus closure features (trainer/converter):
  - Per-record hotkeys: source `<Hotkey>` bindings compile into plan
    metadata, register first-wins in the engine with deduplicated
    warnings, dispatch value operations on value records, and show
    original-binding cards plus a table-wide conflict banner in the UI.
  - Trainer-creator per-table inspection: structured supported/blocked
    results with named per-record reasons and named per-file
    diagnostics in the conversion GUI.
  - Runtime dynamic address providers: a Lua provider registers exactly
    one symbol on enable; relative children resolve the runtime base per
    activation; static module-relative siblings keep the module binding.
  - Read-only table-Lua bootstrap: the table LuaScript top level executes
    exactly once per attach through a read-only broker; refused or failed
    bootstraps surface a named banner and dependent record scripts stay
    visibly inactive.
  - Lua-owned symbol handover: record-Lua registerSymbol pairs and
    allocation-only programs publish symbols in the per-table
    `external_owned_providers` map; consumers carry explicit
    dependencies on their owning record, and the engine enforces the
    teardown order (owner deactivation only after consumers, exactly-once
    symbol release).
- Pinned reference corpus: 24 tables, 6,100 expected AP-11 actions
  (7,426/7,426 action-weighted feature coverage).
- Release build 0.15: run `native-20261018T055505Z-39f20180` cut from
  `main` @ `ed0b97b` via `scripts/Build-Native.ps1` (2026-10-18); in-build
  suite 3057 OK / 25 regular skips, `ce_inputs: []`,
  `runtime_unverified` deliberately kept per gate; source ZIP
  `CT2Trainer-0.15-source.zip` sha256
  `5d5a85f63f0b0948b05e06bfba8f40fa91e7bf75e5d981da22b33a3a5f522581`,
  portable ZIP `CT2Trainer-0.15-windows-portable.zip` sha256
  `cfcc8e06f65d0b3c6ec1ef4671f2be520c45c1c6c85572f1dbe6e69d15ea8414`.
  Both ZIPs ship the elaborated release READMEs and this changelog.

## 0.14 (2026-10-17)

- Per-wish restore isolation: a scan miss in one saved record no longer
  blocks the whole trainer (field finding from the 0.13 debug log: a stale
  AOB pattern in one record fell into the restore loop's catch-all
  exception path and blocked the engine, making every other saved toggle
  unusable until the process restart):
  - New `ScanMiss(ProcessMemoryError)` in `memory.py` for definite
    scan-result failures (pattern not found, ambiguous match, module
    changed while scanning, module-inventory or scan-quota bounds);
    process-level errors (identity change, inventory progress anomalies,
    read/write failures) stay plain `ProcessMemoryError` and still
    fail-close.
  - The engine's saved-wish restore loop now isolates each wish: a
    `ScanMiss` or `NativeRuntimeError` from one record fails that record
    only (logged as `restore-failed` with identifier and label, recorded
    in `entry_errors`) and the remaining saved wishes keep restoring;
    the engine stays connected and usable. A `StateError`/`PatchConflict`
    that already blocked the engine stops the loop; `RetryableAction`
    keeps the outer "waiting for a safe data-write point" handling.
- Debug logging now covers program (AA script) preflight scans, which
  previously bypassed the byte-patch `_operations` scan events:
  - `preflight_program()` accepts an optional `on_scan` callback; every
    `scan` / `scan_process` / `scan_region` op reports its symbol,
    module, pattern and resolved address, or the exception on failure.
  - `_install_program` logs `scan` / `scan-failed` events with
    `entry_id`, symbol, module, pattern, address and (while logging is
    enabled) module base / size / RVA; failures carry the full
    traceback. Byte-patch scan events in `_operations` now include
    `entry_id` as well.
- New tests: 2 restore-isolation tests in `tests/test_native_engine.py`
  (stale anchor fails only the affected wishes; an independent later wish
  still restores), 2 `on_scan` callback tests in
  `tests/test_native_aa_directive_wiring.py`, and a `ScanMiss`
  classification test in `tests/test_native_memory.py`.
- Release build 0.14: run `native-20261017T115850Z-1ebb48b7` cut from
  `main` @ `fca6b06` via `scripts/Build-Native.ps1` (2026-10-17); in-build
  suite 2932 OK / 25 regular skips, `ce_inputs: []`,
  `runtime_unverified` deliberately kept per gate; source ZIP
  `CT2Trainer-0.14-source.zip` sha256
  `a5b075cf6535c5eef3807da7b7b9429dda08a3cf9f9dba6fdafb879e0dfce0a9`,
  portable ZIP `CT2Trainer-0.14-windows-portable.zip` sha256
  `e57fe9b9fb56ef7a97f81a98f04455976c4b5e9ebddee655b24cbb64e7ed3103`.
  Both ZIPs ship the elaborated release READMEs and this changelog.

## 0.13 (2026-10-16)

- Optional runtime debug logging for generated trainers (user-requested
  feature for diagnosing red/disabled toggles on real tables):
  - New converter option **Debug logging** — checkbox in the converter
    GUI, `--debug-log` flag on the source CLI `inspect`/`prepare`/`build`.
    It sets the plan flag `debug_log: true` (default plans are
    byte-identical to before; the plan identity / trainer ID is
    unaffected, so state directories stay shared).
  - When enabled, the generated Trainer.exe appends one JSON line per
    runtime event to `<TrainerName>.ct2debug.log` next to the EXE (source
    runtime: `ct2trainer-debug.log` in the working directory): plan
    identity header, engine init + saved wishes, attach attempts and
    refusals (process not found, architecture mismatch, session claim,
    call broker), confirmed attach (PID, target EXE path, pointer width,
    creation time), target exit, every AOB scan (symbol, module, pattern,
    module base, size, RVA; failures with full traceback), definitions,
    symbol register/unregister, byte asserts (expected vs. actual bytes on
    failure), planned and written patches (address, original, new bytes;
    refusals, write failures, rollback failures), toggle / value-write /
    freeze attempts with success and failure outcomes, wish replay on
    attach, state saves, auto-on requests, engine blocking, and
    clean/unclean close. Errors carry exception type, message and full
    traceback.
  - Attach-stage failures are logged once per distinct cause so the
    repeating 250 ms poll loop cannot flood the log; the signature clears
    on a confirmed attach, so a recurring cause is reported again.
  - Logging is best-effort and never changes trainer behavior; disabled
    plans (the default) write no file at all.
  - New module `src/ct2trainer/native/debug_log.py`; instrumentation in
    `engine.py` (init, poll/attach, `_operations`, `_write_transaction`,
    `_save`, `toggle`, `set_value`, `set_freeze`, `request_auto_on`,
    `clear_desired`, `_block`, `close`), `ui.py` (action failures,
    startup failures), `launcher.py` (startup failures); `memory.py`
    exposes the bound target's `image_path`.
  - New tests: `tests/test_native_debug_log.py` (15 tests: plan flag
    default/opt-in/typo validation + trainer-ID stability, log writer
    JSON-line format / error traceback capture / disabled no-op / close
    semantics, engine integration for attach failure incl. repeated-
    failure dedupe, scan failure, assert failure, state-save failure,
    full toggle/value/close cycle, and no-file-when-disabled).
- Module-snapshot robustness fix (surfaced in the field by the new debug
  logging): the target module inventory used by every AOB scan and by
  target-architecture re-verification now retries with the native-only
  TH32CS_SNAPMODULE flag when the combined native/WOW64 snapshot fails
  (observed in the field: Win32 error 299,
  ERROR_INVALID_STARTING_ADDRESS, on some Windows builds); if both
  attempts fail, the named error reports both attempts and the first
  Win32 code. Two new tests in `tests/test_native_architecture.py` pin
  the fallback and the double-failure error.
- Release build 0.13: run `native-20261016T190005Z-b3139b30` cut from
  `main` @ `d57e62c` via `scripts/Build-Native.ps1` (2026-10-16);
  in-build suite 2927 OK / 25 regular skips, `ce_inputs: []`,
  `runtime_unverified` deliberately kept per gate. Artifacts:
  `CT2Trainer-0.13-source.zip` (sha256
  `23b57307819e4262d8ca894ac16c86d595df9945c1afec25750f66bb9e0c9124`),
  `CT2Trainer-0.13-windows-portable.zip` (sha256
  `d7f64efbae975f477e5bb011796d64276f32ef4300d4a0986961e95ae63aca78`);
  superseded 0.13 run `native-20261016T181516Z-b8ae88de` (pre
  module-snapshot fallback, cut from `main` @ `7184547`).
  both ZIPs ship the elaborated release READMEs (the portable user
  guide now documents the debug-logging option) and this changelog.
  The build carries the released 0.12 content (Wave 2 corpus closure)
  unchanged; 0.13 adds the debug-logging option and the module-snapshot
  fallback only.

## 0.12 (2026-10-16)

- Wave 2 of the reference-corpus closure cycle on `native-0.12`
  (all ten work packages merged; full local suite 2910 OK / 25 expected
  skips, 0 failures):
  - W2-A (WP-27/32/33/34, lane `w2-a` @ `a49a1db`, merge `aa6371b`):
    - WP-27 profile-aware linked dropdowns: every choice validated
      against the record's own value type at compile time (per-choice
      named refusals: byte-array hex-byte width, bit-field range,
      integer type width); missing vs. ambiguous link targets split;
      engine validator delegates to the compiler refusal so both layers
      agree; reference dropdown family 1,215 → 0.
    - WP-32 addressless value-record demotion to supported
      non-actionable placeholder headings (`Addressless value record is
      a non-actionable table placeholder.`); relative-address children
      stay blocked; demoted placeholders excluded from the
      parent-activation cascade.
    - WP-33 IEEE-754 bit-pattern editing for hex Float/Double (exactly
      8/16 hex digits, optional `0x` prefix, little-endian raw bytes,
      `struct` round-trip proof shared by parse/format/dropdown/
      value-link layers); fixed-width policy shared across
      engine/compiler.
    - WP-34 diagnostics: `Dropdown link target is missing or
      ambiguous` split into per-name missing/ambiguous refusals;
      comma-decimal Float/Double choice normalization (FLAG-2
      follow-up); per-choice width-precision refusal names the
      offending choice; AP-08.3/08.7 citations aligned.
  - W2-C (WP-30/36, lane commit `e5c039e`, merge `32e0cdd`):
    - WP-30 bounded address-expression profile: typed casts are no-ops
      for symbol extraction, nested indirection up to depth 2, `@`
      forms accepted; the `requires == address symbols` match gate kept;
      malformed forms refused with named depth-limit reasons.
    - WP-36 `aobscan`/`aobscanregion` staged under the existing scan
      budget; `createThread()/threadWait()` keep the named fail-closed
      capability gate; 3-arg `globalalloc(sym,size,$process)` accepted
      in the global-init profile with shared symbol registration.
  - W2-B (WP-28/29/31/35, lane commit `d4d062d`, merge `2f68f80`):
    - WP-28 two-stage per-program label scoping: a program's own bare
      positional labels (`return:`, `endp:`) are local at the prepare
      level (`positional_labels`); the table compiler re-declares them
      as external requirements whenever another supported record
      provides the same symbol (registered symbols win over local label
      definitions); bare labels without a provider or an address anchor
      refused (`Positional label appears before any address cursor.`).
      P3Reload `return:` family unblocked; reference catalog P3Reload
      blocked 3,006 → 331.
    - WP-29 `alloc` in the data dialect + allocation-only
      initialization profile (no game write; `dealloc`/
      `unregistersymbol` on disable; no dead-allocation publication);
      one-shot programs stay refused (`Enable section has no
      executable patch or data.`).
    - WP-31 data-dialect grammar: 2-arg `dealloc`, multi-token
      `registersymbol` pre-pass, `registerlabel`, bounded no-op
      `fullaccess(addr,size)`, `/* */` comments, line-attached error
      messages; comment-only scripts classified `inert/documented`.
    - WP-35 operand-less `dq`/`resb` reservation spans as
      program-owned allocations (must be written before publish, no
      cross-program access); outside owned regions refused
      (`Uninitialized reservation (dq/resb) requires a program-owned
      allocation.`).
- Corpus: 20 pinned tables (was 19): case-16 part 2 refined and
  case-17 pinned as the 19th table (W2-A); case-15 part 2 refined and
  re-pinned — 21 records, cast/indirection records, chain
  `w2c-case15p2b-20261015144326Z` (W2-C); case-18 pinned as the 20th
  table — `ct2synth18.exe`, 18 records, IDs 10–27: 16 supported,
  IDs 26/27 deliberately kept blocked with named reasons (W2-B).
  gate:1 now covers all 20 pinned tables.
- Feature matrix stays 42/42 in-scope (100% feature-weighted,
  7408/7408 action-weighted over run `w2b-case18-20261016142912Z`);
  AP-11 campaign: 0/6,080 confirmed (separate end goal, excluded from
  the 100% feature metric).
- Reference catalog re-run (151 local-only tables, 143 distinct
  hashes): 110,047 supported (54,234 staged), 7,577 of 117,624 blocked
  (was 9,962 after W2-A); 1 whole-table compile error (SuperMeatBoy
  legacy binary).
- Release build 0.12: run `native-20261016T163910Z-d047f2d2` cut from
  `main` @ `ba1d3e4` via `scripts/Build-Native.ps1` (2026-10-16);
  in-build suite 2910 OK / 25 regular skips, `ce_inputs: []`,
  `runtime_unverified` deliberately kept per gate. Artifacts:
  `CT2Trainer-0.12-source.zip` (sha256
  `f5a5468da6e49ee5d4812dce3edea71e87e4bb9736ce4bf3486dfc0c66e70165`,
  12,811,693 bytes) and
  `CT2Trainer-0.12-windows-portable.zip` (sha256
  `7bd582e33f2978c641bb36a22ad8fc5f21bc9b695bb16930bed19720eaa81619`,
  28,313,477 bytes); EXEs: `CT2Trainer-Template.exe` (sha256
  `14c0d86726404087299a2e7e924cb3d960562671f7d9e2e174d8706992343edc`,
  14,516,772 bytes), `CT2Trainer-Converter.exe` (sha256
  `1ebbf708631fea59618c7d0c18e5de229a699e09678595977033bc7ac40307f5`,
  28,569,255 bytes). Both ZIPs ship the elaborated release READMEs
  (source: product overview + build guide; portable: full user guide)
  and this changelog (0.12 + retro 0.11 entries).

## 0.11 (2026-10-12)

- WP-15 (L2-37): fully-permitted executable bit-field writes routed
  through the engine (merge `d3316aa`; suite 2688).
- WP-16 (L5-19): named table-Lua tabs gathered into the table-Lua
  bootstrap source — main-body-only byte identity, document-order
  joining, fail-closed invalid-tab activation (merge `38a830d`;
  suite 2679).
- WP-17: build version in the converter and trainer window titles plus
  a clickable GitHub repository link in both windows; fail-closed
  `verify_version_sync` fails the build on VERSION/`__version__` drift
  (merge `557b2ac`; suite 2698).
- WP-18: `$process` AOB module token for `aobscanmodule` at both engine
  scan dispatch sites; trailing `@F` without explicit `@@` falls back
  to the next positioned named label (explicit `@@` still wins);
  PRAGMATA reference table 595/595 supported, 0 blocked (merge
  `9a76eb8`; suite 2710).
- Release build 0.11: run `native-20261012T092729Z-2d8aaf12` cut from
  `main` @ `9a76eb8` via `scripts/Build-Native.ps1` (2026-10-12);
  in-build suite 2710 OK / 25 regular skips, `ce_inputs: []`,
  `runtime_unverified` deliberately kept per gate. Artifacts:
  `CT2Trainer-0.11-source.zip` (sha256
  `168c14a452595588a6483140f1d43bec818d0f0d0e9eb72167453a80624469db`)
  and `CT2Trainer-0.11-windows-portable.zip` (sha256
  `8a2d6ac6f8b802714fe7578de54cea432506a41f8bf91d597a03fa086b04f196`).
  Superseded 0.11 run: `native-20261011T182033Z-f3317337` (pre-WP-18,
  in-build suite 2698/25).

## 0.10 (in cycle, 2026-10-11)

- WP-14 "Staged Capabilities" (PRAGMATA-class tables):
  - Signed pointer offsets: `<Offsets>` literals accept an explicit sign
    (`+28` = `0x28`, `+0x130`, `-0x10`); malformed forms
    (`++10`, `+`, `0x`, empty, trailing junk) stay rejected fail-closed.
  - Script-parent activation cascades: the tested flag-class contract
    (AP-07) extends from group headings to script records with children
    (`required_dependency` / `direct_activation` / `collective_off`);
    `moBindActivation` on any non-heading parent stays a visible named
    block; value parents with flags stay fail-closed (documented inert
    scope).
  - Staged runtime gating: records whose address needs a symbol provided
    by another supported record carry `staged` metadata; the engine gates
    read/write/freeze on provider liveness (named, fail-closed error while
    the provider is inactive; UI shows a pending state and auto-unlocks);
    provider OFF releases freeze on frozen staged children first, then
    deactivates the provider.
  - Record-ID activation sets: the converter statically extracts
    enable/disable ID sets from embedded `{$lua}` blocks
    (`getMemoryRecordByID(<int>)` + `Active = true|false`, uniform
    direction per section); such records route through the engine's
    dependency-ordered set application instead of executing the
    CE-coupled Lua. Plan validators re-derive `staged`/`activation_sets`
    and refuse tampered metadata.
  - Trainer/converter UI states: staged pending card, master-toggle card
    for activation sets, converter `Staged` capability column and
    `N supported (M staged, K blocked)` status line.
- Corpus: 14th pinned table `TableReferences/case-14.ct` (PRAGMATA
  behaviour derivative, `ct2synth14.exe`, 57 records: master toggle with
  record-ID activation set, script parents with all three flag classes,
  nested script provider/consumer, signed pointer offsets on record and
  heading, one-shot guarded write).
- Denominator: 14 pinned tables, 6011 expected actions (was 5967), three
  new gap labels (`signed_pointer_offset`, `script_parent_activation`,
  `record_activation_set`), 39 gap classes, 42 in-scope features
  (39 + 3 gates) all covered: 100% feature-weighted, 7361/7361
  action-weighted (was 7332/7332); all `gap_inventory/` artifacts
  regenerated byte-reproducible (run
  `wp14-staged-20261011T093320Z`, consistency `all_ok`).
- Old-13 plan stability: per-table plan diff rc2 → WP-14 shows
  12/13 byte-identical; the only delta is case-06 entry 17258 (async
  Lua/AA record) flipping blocked → supported — the Lua
  symbol-provider extraction resolves a table-owned symbol the old
  envelope check rejected (table totals: supported 38 → 39, blocked
  293 → 292).
- Classifier fidelity: `assert` added to the supported AA directive list
  (product-supported guard directive); ENABLE-only scripts with a
  guarded write classify as `one_shot` (mirroring the product's
  `compile_one_shot` contract) instead of `unknown`.
- PRAGMATA.CT reference measurement (reference input only, never in the
  repo): 595 records → 586 supported (416 staged / 170 non-staged),
  9 blocked (2 records with a strict `"$process"` address plus an
  anonymous assembly label; 7 `i_base_*` children without a unique
  supported provider — each individually justified).
- Release build 0.10: run `native-20261011T121914Z-bfc5fc11` cut from
  `main` @ `64b1e63` via `scripts/Build-Native.ps1` (2026-10-11);
  in-build suite 2671 OK / 25 regular skips, `ce_inputs: []`,
  `runtime_unverified` deliberately kept per gate, source inputs
  unchanged. Artifacts: `CT2Trainer-0.10-source.zip` (sha256
  `93f1f353abaf399287ebf27b90dcb794793658cd6663a6fc68d25998e5f2eb83`,
  12,729,937 bytes) and `CT2Trainer-0.10-windows-portable.zip` (sha256
  `833441069b078d352a556d650ccb7ddbbc8604aacc6e752adfd869d8b11f36f1`,
  28,231,325 bytes); EXEs: `CT2Trainer-Template.exe` (sha256
  `1ae0d2163bac4271711f7a7e826346cd1513ce3b231563b9f64ddc0526f93c14`,
  14,475,270 bytes), `CT2Trainer-Converter.exe` (sha256
  `a8e3005ed6bc7c18092ac0fcd28e42495c0573e87abe4fb3e5f0f79c9094eb89`,
  28,490,774 bytes).

## 0.9.0-rc2 (2026-10-10)

- Clean-room synthetic CT corpus: `TableReferences/` is replaced by a
  synthetic clean-room corpus of the 13 pinned tables as neutral case
  files (`case-01.ct` through `case-13.ct`); own code only, no
  third-party copyrighted material in the corpus or the distributed
  releases. Affected tests are re-pinned to the synthetic corpus.
- CT2Trainer naming: the Native edition is officially CT2Trainer. Fresh
  builds produce `CT2Trainer-<version>-source.zip` and
  `CT2Trainer-<version>-windows-portable.zip`; the binary plan footer
  magic is `CT2NATV1` and the template stub marker `CT2BASE1` (both
  8 bytes). The one-shot marker magic `TFSH0001` is kept as a stable
  format constant.
- 0.9 feature set: 5967-action denominator baseline; 39/39 in-scope
  features covered (100% feature-weighted, 7332/7332 action-weighted).
  The 100% feature-matrix goal (excluding AP-11) is reached. AP-11
  (5967 expected actions, 0 confirmed so far) remains a separate end
  goal and is excluded from the 100% feature metric.
- Gates 1-3 closed with tested evidence (their action weights remain
  0; they are completeness/proof features, not record actions):
  - gate:1 per-table completeness for all 13 pinned tables
    (Forms, Lua lifecycle, Custom Types, Assets) is demonstrated by
    `tests/test_native_table_completeness.py` (every source record
    preserved, each table-level construct handled or surfaced
    fail-closed, plus a synthetic embedded-Files case).
  - gate:2 Source-to-Frozen parity of the 0.9 feature set is
    demonstrated by `tests/test_native_source_frozen_parity.py`
    (real corpus plans round-trip through build_trainer /
    read_embedded_plan byte-identical); the binary CLI/GUI adapter
    for the static IL2CPP parser is new: the frozen launcher exposes
    `--il2cpp-static-pe/--il2cpp-static-metadata/--il2cpp-static-report`
    and the source CLI exposes `ct2trainer native il2cpp`, both
    producing a bounded read-only report
    (`tests/test_native_il2cpp_static_probe.py`).
  - gate:3 end-to-end reproducibility chain across all features with
    exact commands and pinned inputs is demonstrated by
    `tests/test_native_repro_chain.py` (denominator -> feature matrix
    -> AP-11 manifest reproduced byte-for-byte for a fixed run-id).
- Portable frozen-build fix: `api-prototypes.json` is now bundled into
  the EXE and, in frozen mode, resolved against the bundle root
  (`sys._MEIPASS`), so trainer generation in the portable ZIP no longer
  fails on a missing `dependencies/native/mono-api-source/` path;
  `tests/test_native_mono_runtime.py` (`PinnedTablePathTests`) covers
  path resolution in both source and frozen mode.
- Fresh, fully offline build
  `native-20261010T172336Z-ffe35eb0` via `scripts/Build-Native.ps1`:
  in-build suite 2617 OK / 25 regular skips; `ce_inputs` empty;
  `api-prototypes.json` present in both EXE payload inventories;
  `runtime_unverified` deliberately kept per gate. The portable ZIP of
  this release was user-tested (converter run plus generated trainer on
  a machine without CE or Python).
- Release artifacts for this entry:
  `CT2Trainer-0.9.0-rc2-source.zip`,
  `CT2Trainer-0.9.0-rc2-windows-portable.zip` with the output hashes
  recorded in the build report.
- Release-archive hygiene: the source ZIP contains exactly the
  build-essential tree plus the build/usage/derivation docs, the
  runtime and verification docs, the Proton/Steam Deck compatibility
  matrix, the feature-matrix artifact, and this single changelog.
  Dev ledgers, plans and corpus scratch stay out of distributed
  releases; the build allowlist in `tools/native_build.py` is the
  single source of truth, verified by the in-build CE-content scan.
- 0.9.0-rc1 remains an earlier release; it is not superseded by this
  entry.

## 0.9.0-rc1 (2026-10-08)

- First release under the CT2Trainer name, built fully offline
  (`native-20261008T093705Z-61c2257d` via `scripts/Build-Native.ps1`):
  in-build suite 2595 OK / 25 regular skips, `ce_inputs` empty,
  `runtime_unverified` deliberately kept per gate.
- Release artifacts for this entry:
  `CT2Trainer-0.9.0-rc1-source.zip`,
  `CT2Trainer-0.9.0-rc1-windows-portable.zip` with the output hashes
  recorded in the build report.
- Binary plan footer magic `CT2NATV1` and template stub marker
  `CT2BASE1` introduced; the owned fixture corpus was re-pinned after
  the marker/schema change.
