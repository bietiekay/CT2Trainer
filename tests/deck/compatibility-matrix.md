# Steam Deck / Proton: Compatibility Matrix and D0/D1 Run Sheet

**Status:** October 10, 2026 (re-issued for the independent edition). **All test cases and gates: OPEN; no Proton, Linux, or Steam Deck run has been performed.** This document is a protocol for later measurements, not a compatibility promise. Read the own [fixture manual](../windows/fixture_target/README.md) first. A green Windows run, a started window, or a visible process name does not yet prove access to the game process under Proton.

## 1. Goal, Sources, and Boundaries

The goal is a self-contained CT2Trainer Windows trainer EXE that **in the Proton context of the running game** unambiguously finds the correct Windows process, really attaches, reads and writes a controlled value, toggles a cheat reversibly, re-activates saved switches after a successful re-attach, and stays operable by touch on a real Steam Deck. No Python or other runtime needs to be installed; the EXE must be self-sufficient. **D0** isolates process visibility and memory effect first under Steam/Proton on a Linux desktop or directly on the Deck. **D1** measures the same core functions on the **real Steam Deck**, separated into desktop and gaming mode. Decide the later everyday launcher only after the manual D0 evidence.

The test hypothesis is a start in the **same Wine prefix and in the running per-game Steam runtime**. Valve describes one prefix per game under the respective Steam library `steamapps/compatdata/<appid>/pfx/`; the path can differ for an additional library or an external drive. The Proton debugging guide describes how to open a shell in the running per-app runtime with `WINEPREFIX` set and start an additional Windows program inside it with `wine`. That is a **hypothesis for the test setup**, not evidence for Win32 process visibility, trainer attach, or write rights. A trainer started separately as a Steam title can receive a different prefix and is therefore no equivalent positive test. Sources: [Valve Proton FAQ: prefix per game](https://github.com/ValveSoftware/Proton/wiki/Proton-FAQ), [Valve: shell in the Steam runtime and starting another Windows program](https://github.com/ValveSoftware/Proton/blob/proton_11.0/docs/DEBUGGING-LINUX.md), [Valve: Deck compatibility criteria](https://partner.steamgames.com/doc/steamhardware/compat). The version of the actually used Proton tool must be recorded separately; the linked guide is the documentation of the `proton_11.0` branch and not automatically the version in use.

The first effect measurement uses the own [`../windows/fixture_target/fixture.ct`](../windows/fixture_target/fixture.ct) and an x64 `FixtureTarget.exe` started under Proton. Afterwards, the **product acceptance on a game process** needs an explicitly selected, locally running single-player title with a verified CT and an exactly documented game version. Neither the fixture nor an arbitrary table import replaces this game evidence. No online/anti-cheat/kernel/DBVM scenario in this matrix. CT tables can contain Lua and Auto Assembler scripts; check their content and provenance before a third-party test. Private own use and rights/trust boundary: see `licenses/` and `documentation/native-runtime.md`.

### Status rule

Every row starts as **OPEN**. After a real run, assign exactly one status with evidence: **PASSED**, **FAILED**, or **OPEN** (not run, not reproducible, or insufficient evidence). "Partial" only as observation text, never as an overall gate. On errors, name the first demonstrably failing stage; later stages stay OPEN. No project upgrade from a single Proton or desktop-mode run.

## 2. Matrix of the combinations actually to be checked

For **each** variant, copy a separate run sheet from section 3. A change of Proton, Steam runtime, CT, game build, trainer EXE, Deck system state, or start path creates a new row. A change of prefix or Steam library is also a new run, not just a repetition.

| Run ID | Device / mode | Target | Start path / prefix | Purpose | Status / evidence |
| --- | --- | --- | --- | --- | --- |
| D0-F | Linux desktop, Steam/Proton; alternatively Deck desktop with explicit D0 marking | Own fixture | Runtime shell of the running fixture, same `WINEPREFIX` | Isolate trainer/Wine process visibility and controlled read/write/AA effect | **OPEN** / `____` |
| D0-G | Linux desktop or Deck desktop | Suitable local single-player game | Runtime shell of the running game, same prefix | Transfer to a real game process and a verified CT | **OPEN** / `____` |
| D1-Desktop-F | Real Deck, desktop mode | Own fixture | Documented same-prefix/runtime start | Fixture effect, re-attach, state and touch | **OPEN** / `____` |
| D1-Desktop-G | Real Deck, desktop mode | Suitable local single-player game | Documented same-prefix/runtime start | Real game process and touch | **OPEN** / `____` |
| D1-Gaming-F | Real Deck, gaming mode | Own fixture | Reproducible game-context start; protocolize the launch method | Focus/touch/keyboard plus technical fixture effect | **OPEN** / `____` |
| D1-Gaming-G | Real Deck, gaming mode | Suitable local single-player game | Reproducible game-context start | Complete product evidence on the game process | **OPEN** / `____` |
| N-Prefix | Same device as a positive baseline run | Same target | Trainer in a **separate** Steam prefix | Control case for process visibility; a success or failure is a finding, not an assumption | **OPEN** / `____` |

Neither D0-F alone nor a started trainer EXE alone is sufficient. D0-G may stay open until a suitable title is selected and verified. **D1 as product gate stays open** as long as desktop or gaming mode on the real game process or the touch measurement is missing. A gaming run may not be derived from the desktop result.

## 3. Run sheet: identity and reproducible environment

For each run, fill in these fields **before** any effect measurement. Note paths as actual absolute paths including the library drive; do not assume `~/.steam` or a fixed internal SSD. Compare the SHA-256 of the EXE and CT before/after transfer. The build report flag `runtime_unverified: true` is a structure check, not D0 evidence.

| Field | Observed value / evidence |
| --- | --- |
| Run ID, date/time with timezone, tester, evidence folder | `____` |
| Device/mode: Linux desktop or Deck model; desktop/gaming; SteamOS/Linux kernel version; display resolution, scaling | `____` |
| Steam client version; Steam runtime name and observed version; Proton tool/version and path/hash | `____` |
| Game name, **Steam AppID or actually used compatdata ID** (for a non-Steam fixture note the kind of ID), Steam library and library drive | `____` |
| Exact target EXE basename, game/fixture version, target EXE SHA-256, process architecture; for a game: CT clearance for this version | `____` |
| Used CT SHA-256, CT version, generated CT SHA-256, `trainer_id`, generator revision | `____` |
| Trainer EXE SHA-256, PE architecture, `.build.json` SHA-256 | `____` |
| Full prefix path, `WINEPREFIX` from the running runtime, wine/Proton invocation, runtime shell command and trainer start command | `____` |
| Linux PID and Windows PID visible in the Wine context for target and trainer; start time/identity in addition to the PID | `____` |
| State file and `.session` marker in the prefix: Linux/Windows path, hash/bytes before/after transitions; note target PID and `owner=<trainer PID>` separately | `____` |
| Initial state: clean prefix/snapshot or existing prefix; existing trainer, Python, or source artifacts; game already started? | `____` |
| Deviations from the Windows reference run; logs/photos/videos used, with file names and hashes | `____` |

For the fixture, the PID printed in the console and the triple `value`, `pause`, `ticks` are the independent effect evidence. The target value starts at `1234`; a controlled write must show `4321`. The pause switch must produce `pause=1` and at least three unchanged `ticks` outputs; after disable `pause=0` and rising `ticks` again. Offsets, record IDs, and AA order are in the [fixture manual](../windows/fixture_target/README.md). For a real game, **before the run** a harmless, measurable value and a reversible, verified cheat with its own observation source must be defined; a UI label alone is not sufficient.

### Documented same-prefix/runtime start: hypothesis, no fixed launcher implementation

1. In Steam, pin down the actually used Proton tool for **the target**. For diagnostics, the launch option documented by Valve `PROTON_LOG=1 STEAM_COMPAT_LAUNCHER_SERVICE=proton %command%` can be used. Back up the original options beforehand and undo the temporary intervention after the test. For a non-Steam fixture, determine the actual compatdata ID and its prefix; do not invent an AppID.
2. Start the target from Steam and let it run. Distinguish the actual target EXE and its Linux/Wine PID from launcher or helper processes. Capture the actual `steam-<ID>.log` and the `steam-runtime-launch-client` command printed there for the **running** per-app runtime. The Valve guide shows the way; take the bus name, path, runtime, and command from **this run** instead of hardcoding example values.
3. Open the runtime shell with the documented command. Check `WINEPREFIX`, the runtime environment, the `wine` path, the running Windows processes, and the target PID. Compare the prefix path against `steamapps/compatdata/<ID>/pfx/` of the actually used Steam library. A missing variable or a different prefix is a test setup error; do not make a positive attach statement in this state.
4. **Only then** start the standalone trainer EXE from this shell with the wine/Proton path available there; record the full invocation, exit code, outputs, and any self-unpacked temporary files. It is not yet known which exact command is reliable for the pinned environment. For a deviating start path, create a new matrix run. The EXE must work without separately installed Python/CT/manifest files; self-unpacked temporary files are allowed and must be documented.
5. Verify reproducibility: terminate target and trainer normally, start again through the same documented path. A technical shell proof is only the foundation for a later, gaming-mode-reachable start integration. Protocolize the game context, focus switching, and closing without a persistent terminal separately.

**Start setup gate: OPEN** — Actual start commands/logs: `____`; prefix/runtime equality: `____`; target and trainer process identity: `____`; result/evidence: `____`.

## 4. D0: technical Proton measurement

Apply the following steps to D0-F and then to D0-G. Verify the fixture CT first directly on Windows with the converter-built trainer, and afterwards repeat the identical flow under Proton. Do not derive Windows effect from the macOS unit tests. Secure state/markers as a starting point and start exactly **one** target EXE first, unless the test explicitly checks multiple hits. The Valve runtime shell requires a running target: for D0-01, terminate the target only **after** opening the runtime shell and starting the trainer, then restart it within the same still-living game context. If Steam also terminates the runtime at target end, hold D0-01 as **OPEN** for this start path and check a reproducible alternative flow separately; do not report a waiting status from another prefix as same-prefix evidence.

| Step | Expected evidence / concrete observation | Status / evidence |
| --- | --- | --- |
| D0-01 Target missing, trainer keeps running | After the initial target start needed for the shell, terminate the target while runtime/trainer persist: the UI waits, shows neither a wrong PID nor supposedly active cheats; document the later return of the target for D0-02. | **OPEN** / `____` |
| D0-02 Process visibility | After the target starts, the trainer lists exactly the right EXE basename and the right **Wine PID**; protocolize Linux PID and Wine PID separately. The launcher must not be selected by mistake. | **OPEN** / `____` |
| D0-03 Attach | Show success only after a real trainer handle/attach; capture error text/error code on failure. A successful enumeration does not count as attach. | **OPEN** / `____` |
| D0-04 Read | Fixture: resolve locator ID 0 and read ID 2 as `1234`, ID 3 as live `ticks`. Game: read a predefined harmless comparison value. | **OPEN** / `____` |
| D0-05 Write | Fixture: set ID 2 to `4321`, compare the trainer readback and the next target console line. Game: change a controlled, harmless value with external observation. | **OPEN** / `____` |
| D0-06 Reversible cheat | Fixture: enable ID 1 via the locator (`pause=1`, at least three identical `ticks`), disable (`pause=0`, then rising `ticks`). Game: evidence the verified effect **and** the rollback. | **OPEN** / `____` |
| D0-07 Module/AA/pointers | Fixture: actually check `aobscanmodule`, `registersymbol`, and the AA `assert`. For a real game CT, only tick off the constructs present there separately; do not infer pointers/hotkeys/v52 from the fixture. | **OPEN** / `____` |
| D0-08 Game restart | With confirmed desired IDs 0/1, terminate the target, let the trainer run, and start a new target. Evidence the new session/identity, the one-time reactivation, and the real target effect after the re-attach. Do not count a same PID alone as a new session. | **OPEN** / `____` |
| D0-09 Trainer restart/state | Terminate the trainer normally and start it again; check the state path **inside the right prefix**, the saved confirmed switches, markers, and the reapply against the target effect. Values like `4321` are not persisted in the prototype. | **OPEN** / `____` |
| D0-10 Resources and cleanup | The trainer should create a private directory under Windows LocalAppData in the right Wine prefix per start and unpack there. Capture actual write/execute rights, trainer child processes, memory/CPU behavior, normal closing, and leftover files/processes. A single self-contained EXE is the shipping form; a missing bundled runtime component is not compatible. | **OPEN** / `____` |
| D0-11 Markers and race | Start two trainers against one target PID with the same fixture and the same prefix. At most one complete `CREATE_NEW` claim with target/owner PID, no trainer write/reapply by the loser, and no removal of the foreign marker after confirmed target death. An AA call counter/hook is required for "exactly once"; without it, leave this part open. Legacy/partial markers block. Check a Unicode prefix/`%APPDATA%` path separately: a wide `CreateFileW` and a subsequent trainer state reopen can differ; on a failed reopen, the empty marker must block. | **OPEN** / `____` |

**D0-F gate: OPEN** — target/trainer hashes, prefix/runtime, trainer invocation, and independent fixture effect evidence: `____`. **D0-G gate: OPEN** — additional game build/CT/effect evidence: `____`. A missing suitable game test stays marked OPEN as D0-G.

## 5. D1: real Steam Deck, capture the modes separately

Create two independent passes of the core points D0-02 through D0-09 for **desktop** and **gaming**. The D0-F/G effect on a Linux desktop does not count for D1. Keep the same trainer/Proton/game version where possible; record every deviation in the run sheet. Measure touch and focus exclusively on the real Deck, never derived from screenshots or mouse operation.

| Checkpoint | Desktop mode: observation/status | Gaming mode: observation/status |
| --- | --- | --- |
| Common start of game/fixture and trainer, same prefix/runtime, target stays launchable | `____` / **OPEN** | `____` / **OPEN** |
| Correct process, real trainer attach, read/write, and reversible cheat; target effect evidenced separately | `____` / **OPEN** | `____` / **OPEN** |
| Reach the trainer from the game and return to the game; focus, window position, overlay/task switching, no permanently covered controls | `____` / **OPEN** | `____` / **OPEN** |
| Touch (WP-58 row grid): flat switch default view, `On`/`Saved`/`Values`/`All` chips, tap every visible whole switch row (row is the toggle target), tap a value area to expand the inline editor, Apply/Freeze/±/Reset in the expanded row, collapse via Escape or re-tap, `Info` via the 16 px "i" chip or a 400 ms long-press, section chevron collapse/expand, group toggle pill, `Status / help`, page change via 80 px drag, wheel, PageUp/PageDown and the ◀ ▶ ⤒ buttons, and the **last entry** with a finger; no hover/right-click requirement | `____` / **OPEN** | `____` / **OPEN** |
| Literal search by name/ID/full parent path on a controlled nested CT with German upper/lower case variants (Ä/ä, Ö/ö, Ü/ü, ẞ/ß); the visible context shows at most the last two ancestors, zero hits show "No entries match this view or search."; switching view/page leaves no stale controls active | `____` / **OPEN** | `____` / **OPEN** |
| Compare the actual `Current` against the saved `Auto-on on next game launch` and the next button action; document a safe restore error with `Current: OFF` separately | `____` / **OPEN** | `____` / **OPEN** |
| `On` and `Saved` (separate chips since WP-58): own empty message per view, saved and only freshly verified active safe switch, quick refresh after process/marker/state change; on an unclear check show only the saved wish (sublabel "auto-on for next game launch" on the switch row) with unverified current state and no write clearance. The preview has no such runtime view. | `____` / **OPEN** | `____` / **OPEN** |
| `All`: read the async/external script/value lock reason in the row; check short texts as well as full `Status / help`/`Info` `showMessage` dialogs with a finger, capture closing/focus and text wrapping | `____` / **OPEN** | `____` / **OPEN** |
| Enter a numeric value with the on-screen keyboard, keep focus, field not covered; close the keyboard and read the value back | `____` / **OPEN** | `____` / **OPEN** |
| Capture the actual logical/physical resolution, DPI/scaling, long labels and status at narrow window width, horizontal window edge, 1–12 rows/last page, 720 × 640 value control spacing, hit areas/mistouches by photo/video | `____` / **OPEN** | `____` / **OPEN** |
| On the pre-verified `case-06.ct` (origin: Resident Evil 2): measure opening, search, page change, and quick refresh on the real Deck; do not activate locked scripts | `____` / **OPEN** | `____` / **OPEN** |
| Restart the target: desired switches active after verified re-attach; restart the trainer: state in the prefix and effect still correct | `____` / **OPEN** | `____` / **OPEN** |
| Close the trainer normally, the game stays operable; new common start without manual reinstallation/source artifacts | `____` / **OPEN** | `____` / **OPEN** |
| Optional controller/Steam Input: report the focus order and the back path as passed only if really checked | `____` / **OPEN** | `____` / **OPEN** |

The current source layout is the compact touch-first row grid (WP-58): window width/height is computed from the screen API and clamped (400×610 wide, 400×720 narrow), one row per record — 64 px switch rows, 72 px value rows (120 px while the inline editor is expanded), 48 px group section headers — plus compact chrome (48 px header, 48 px filter row with the five chips Switches/On/Saved/Values/All and inline search, 32 px status line, 28 px amber banners, 48 px pagination; below 650 px window width the chips fall to a 2×3 grid with a dedicated 48 px search row). At the 1600 × 900 reference window the row area is 724 px high and fits 11 switch rows per page (≥ 10 required). The 720 × 640 value layout is only overlap-free in the mock. **This is no physical touch proof.** The inactive `preview.html` predates the row grid and has only `Switches`/`Values`/`All` with five cards per page; the native `On` and `Saved` views need process/state data. With the four-entry fixture, parent-path search, drag paging, and large-table performance are not checkable; add larger, pre-verified CTs as own UI runs for that. Document touch target size on the real display, DPI/scaling, long labels, text overflow, `showMessage` wrapping, adjacent controls, mistouch count, focus, and on-screen keyboard coverage. Gaming mode additionally needs a reproducible start path **reachable from the gaming overlay**; the debug shell alone does not evidence this usage path.

**D1-Desktop-F/G: OPEN** — device/display data, baseline effect, touch/state and evidence: `____`.

**D1-Gaming-F/G: OPEN** — launch/focus path, baseline effect, touch/state and evidence: `____`.

## 6. Negative and edge cases

Run every case against a documented positive initial state, preferably with prefix/state backup. An intentionally wrong prefix or a missing permission is a **diagnostic case** and may not replace the positive matrix. Restrict uncertain interventions to an own fixture process.

| Case | Expected boundary and measurement | Status / evidence |
| --- | --- | --- |
| Trainer separate as Steam title / other `WINEPREFIX` | Evidence the prefix difference and observe the trainer process list/attach; no "must be invisible" conclusion without measurement. The positive same-prefix run stays separate. | **OPEN** / `____` |
| Target missing or wrong EXE basename | Waiting/error visible, no wrong PID and no write. | **OPEN** / `____` |
| Two same-named fixture processes in the target prefix | Ambiguity visible, no automatic re-attach and no write to an arbitrarily chosen PID. | **OPEN** / `____` |
| Game launcher and real game EXE differ | Bind the exact game process; the launcher must not count as target. Capture the actual EXE/PID switch at start. | **OPEN** / `____` |
| Target ends between find and attach; fast restart/PID reuse | No false success; check the session with more than the PID and evidence the effect on the new target. Without a reproducible timing setup, leave open. | **OPEN** / `____` |
| Process visible, attach/access denied | Capture process visibility, attach, read, and write **separately**; no success message from enumeration alone. No blanket permission bypass. | **OPEN** / `____` |
| Locator missing/ambiguous, AA `assert` fails, invalid value | No silent activation or wrong write message; capture the trainer error, `MemoryRecord.Active`, and external target values. | **OPEN** / `____` |
| Target process restart with saved ON; trainer crash with active patch | Separate wish, actually active state, and `.session` lock; evidence crash marker behavior as in the Windows crash-marker case. | **OPEN** / `____` |
| Two trainers in the same prefix or legacy/partial markers | Repeat the two-trainer race check in the Proton context: complete target/owner marker, only one claim, no trainer write or foreign marker cleanup by the loser; legacy and incomplete markers block. Measure the Unicode prefix path and trainer state reopen separately. A `CREATE_NEW` probe and race hook on Windows provide no Proton evidence. | **OPEN** / `____` |
| Trainer handle lost with the **same living target PID** | Only with a securely identified fixture handle: check the write block/re-attach. Without a suitable hook, leave OPEN. | **OPEN** / `____` |
| Async enable or restore still pending, trainer window closed or deadline reached | Keep the marker in the right prefix, no second AA activation, observe target effect and late trainer completion separately. The current trainer does not expose an async-completion read; the corresponding Windows solution must also be evidenced under Proton. | **OPEN** / `____` |
| Corrupted state file or non-writable prefix | No activation from unknown IDs. A valid backup after a corrupted primary is shown only as a **locked recovery candidate**; no older ON is silently reapplied. Check backup/error message, state path, and hash after securing. Marker read/remove errors and externally changed state bytes separately. Do not change foreign game files. | **OPEN** / `____` |
| Trainer EXE on a read-only drive; temp path separate | The trainer should use its own private LocalAppData directory per start; observe start, extraction, and cleanup. On a non-writable/non-executable LocalAppData path, report a clear start error without a false attach. Two simultaneous starts only in a secured prefix/fixture run: no double patch application or silent state corruption. | **OPEN** / `____` |
| Source CT with record hotkeys, generated CT without these blocks | Press the former hotkeys in a controlled fixture copy: no direct `Active`/`Value` path bypassing the trainer UI; compare the manifest and the trainer hotkey behavior against the Windows reference run. Table-Lua/AA-own dynamic hotkeys reviewed separately. | **OPEN** / `____` |
| Gaming focus loss, on-screen keyboard covers the value field, touch on the last row impossible | Film the visible control error and the resolution/scaling; do not report the function as passed even if it works on desktop. | **OPEN** / `____` |

**Error classification for every failure:** (1) start/package/trainer unpacking, (2) wrong prefix or runtime, (3) process visibility/EXE identity, (4) attach/permissions, (5) read/module/pointer, (6) write/AA/table logic, (7) session/state logic, (8) UI/focus/touch, (9) still unclear. Give the first failing stage, the raw message, reproducible steps, build/prefix hashes, and the difference from the Windows reference run. Only then deploy a minimal owned test trainer for root-cause isolation; do not derive an alternative architecture from an unresolved error.

## 7. Evidence and gate decision

Create a local evidence directory per matrix run containing: the filled run sheet, the exact start commands/launch options, Steam/Proton logs, an environment excerpt (`WINEPREFIX`, relevant Steam/runtime variables), the hash list, target/trainer PIDs and start times, trainer status and error messages, time-correlated fixture console lines or game observations, state/marker hashes, and photos/videos for desktop and gaming. Check logs for personal or game data before forwarding. A screenshot of "connected" without an actual read/write/cheat evidence is not sufficient.

| Claim | Required evidence | Current status |
| --- | --- | --- |
| Same-prefix start under Proton reproducible | Run ID, real AppID/compatdata value, prefix, runtime shell, two starts, and process identities | **OPEN** |
| D0-F technical trainer/fixture effect | D0-01 through D0-10, target console evidence, reversible effect, and state/restart | **OPEN** |
| D0-G real game process | Suitable offline game, verified CT/game version, attach, external read/write/cheat evidence | **OPEN** |
| D1-Desktop on real Deck | D0 core steps plus real touch/focus/state measurement in desktop mode | **OPEN** |
| D1-Gaming on real Deck | Own gaming start path, D0 core steps plus real touch/focus/state measurement in gaming mode | **OPEN** |
| "Steam Deck supported" | D1-Desktop **and** D1-Gaming passed on the real game process, no open mandatory points | **OPEN** |

**Conclusion for run ID `____`:** PASSED / FAILED / OPEN: `____`; first deviation and reproducible steps: `____`; affected requirements/gates: `____`; build and prefix identity: `____`; evidence directory: `____`; next tightest test/fix: `____`. Only after an actual measurement update versions, hashes, setup, and result in the project documentation.
