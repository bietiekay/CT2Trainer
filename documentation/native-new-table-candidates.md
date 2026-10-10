# New CT test cases for CT2Trainer — 30.09.2026

Status 2026-10-10: historical corpus-selection document. The candidates
below informed the 0.9 feature work; the live pinned corpus is now the
synthetic clean-room set in `TableReferences/` (case-01 … case-13, see
`TableReferences/README.md`).

The recursive inventory covers **162 CT paths** with **147 distinct
SHA-256 hashes**. 160 files can be parsed by the bounded own CT parser;
of those, 145 are distinct hashes. Subtracting the seven existing pinned
tables leaves **138 distinct newly readable tables**. Copies of the same
bytes do not count as additional compatibility cases.

The selection served the extension of the independent implementation on
`main`. The review read XML, script text and
native-compiler results. It executed no table Lua or AA and attached to no
game. Even a statically assumed record can fail on a missing runtime API,
a resolver, or an upstream dependency.

## Small, targeted candidates

| Candidate | Scope | Gap evidenced and relevant IDs | Use |
| --- | --- | --- | --- |
| Yooka-Laylee (case-03) | 35 records | Mono: collector, method search, JIT addresses and call; IDs 1, 95, 97, 108 | First method search in an own managed fixture; evidence the call separately |
| Disco Elysium, 2024-06-24 (case-04) | 29 | IL2CPP method alias `Sunshine.Metric.SunshineRoller.RollOne`; IDs 182, 216, 224 | Alias resolution with a plain `GameAssembly.dll` AOB as comparison; currently wrongly assumed to be a PE export |
| Rage (no pinned case) | 16 | Explicit x86 profile through compiler, plan and trainer; IDs 6, 40, 62 | Own PE32 fixture; check architecture before allocation and writes |
| Trine 2 (case-01) | 115 | Process-wide AA `aobscan`, `globalalloc` and x86; IDs 121, 61, 63, 65 | Develop scan bounds, multiple hits and jointly owned allocations separately |
| Fallout 4 (case-02) | 154 | Compact AOB tokens such as `0F28`, `*`, `globalalloc`, `readmem` and relocation; IDs 1095, 1096 | Small syntax cases and exact original-byte/buffer ownership |
| Alien Isolation (case-05) | 9 | `speedhack_setSpeed(2.5/0.5)`; IDs 46, 47 | Clear runtime test for the still-missing clock broker; the records already pass syntax checks |
| Expedition 33 V5 (case-08) | 16 | Typed `executeCodeEx` calls, string/buffer passing and dynamic records; IDs 1337320550, 1337320545 | Own harmless target call with confirmed completion, then bounded dynamic value rows |

A particularly small additional Mono case is **My Friend Pedro** with eight
records. Its exact process name is not in the table; a placeholder from the
static review is not an evidenced game process.

## Larger feature and load tests

**Resonance_v1.1_Released.CT** (90 records) contains form/file resources,
process-related metadata, extensive table Lua and target calls. That tests
table initialization and display beyond single cheat records.
**RiftApart.CT** (25 records, ten embedded files) is another asset probe.
For this first version, bounded declarative metadata and own UI models are
sensible; elided script effects must stay visible.

**Witcher 3 4.03** is a precise target-thread case: record 192 really calls
AA `createthread(get_item_name)`, provider 186 supplies the routine. A
controller-Lua worker does not fulfill this contract. Required are a
target ABI, thread/result evidence, timeout, and allocation lifetime. A
confirmed thread start still does not evidence a successful game call or a
reversible effect.

**Borderlands3-V10.CT** (6,353 records) combines a large async reflection
editor, relocation helpers, symbol callbacks and dynamic structures.
**Atomic Heart**, **Metaphor** and **Persona 3 Reload** are further large
load tests. They are useful after the small feature cases; their many
values and navigation rows must not artificially inflate the
compatibility rate.

**RS.CT / Radiant Silvergun** has only three module-relative numeric
values. That is a good already-covered control case for a simple value
trainer, but it provides no new missing API and no observed game effect.

## Original implementation steps and current progress

Historical (0.5 era): the order below came from the first review. Lua EOF
and the explicit architecture binding were implemented in the verified 0.5
code; the owned frozen x86 trainer passed six checks. A dedicated frozen
EOF CT case and the game acceptances remained open. The following points
3–5 were further extension; the full status is in
[native-progress.md](native-progress.md).

1. Support Lua sections that end at the phase end without a closing
   `{$asm}`, with a clear ENABLE/DISABLE grammar. Several new tables use
   this convention. The script assumption replaces no missing host APIs.
2. Pass x86 through as an explicit, plan-bound architecture and compare
   it at attach time with the actually held target.
3. Add process-wide scans, shared allocation owners, and activation
   dependencies. Existing module/region scans remain separate operations.
4. Develop Mono/IL2CPP name resolution, the clock broker, and confirmed
   target calls on own fixtures; then check the original game tables
   specifically.
5. Use table UI/assets and the large async/reflection tables as later
   gates.

This order followed different missing functions, not the number of
statically assumed records. Current status (2026-10-10): the 100%
feature-matrix goal (without AP-11) is reached and closed; the AP-11
real-game campaign remains the separate end goal (see
[native-ap11-campaign.md](native-ap11-campaign.md)).

## Input errors and reproducible evidence

- `Octopath Traveler/Octopath_Traveler-Win64-Shipping.CT` is rejected
  because of the duplicate record ID **1150**. Automatic ID repair would
  change possible script references and is not implemented yet.
- `Super Meat Boy/SuperMeatBoy.CT` cannot be read as XML yet (error at
  line 1, column 0); an alternative/protected format has not been
  determined. The file was left unchanged.

The detailed inventory reports referenced above were generated during the
original development cycle and are not part of this repository or of
distributed releases. The reproducible, committed evidence for the corpus
is the deterministic measurement chain under `gap_inventory/` (see
[native-verification.md](native-verification.md) §Reproduction); the
original game tables are not part of the redistributable source or binary
export — their provenance and rights remain a separate input.
