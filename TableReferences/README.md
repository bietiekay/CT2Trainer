# Synthetic clean-room corpus (TableReferences)

This directory contains the 19 pinned case tables used by the corpus
denominator tool (`tools/corpus_denominator/`). All files are
independently authored, synthetic `.CT` tables; no third-party game table
content is part of this repository. They exercise the same 39 gap classes
that the pinned real corpus did, with neutral case file names.

## Case mapping

The case number is the pinned order used by
`tools/corpus_denominator/__main__.py` (`PINNED`). Each table carries
exactly one owned module token `ct2synthNN.exe`, assigned 1:1 to the
case number.

| Case file | Origin (documentation-level provenance only) | Module token | SHA-256 |
| --- | --- | --- | --- |
| `case-01.ct` | Trine 2 | `ct2synth01.exe` | `70888991c4e7c082c88285159b0dd2435d6b7343c46fb0d133877ca741f3a763` |
| `case-02.ct` | Fallout 4 | `ct2synth02.exe` | `a8193c18cc14e2861563b1d9b043c00b49c0dec94e6a33257e0848584092c0a3` |
| `case-03.ct` | Yooka-Laylee | `ct2synth03.exe` | `bc88a8f96c234564304186721c5448abdbf75731b2d47eeb26b4ba257e2973c7` |
| `case-04.ct` | Disco Elysium | `ct2synth04.exe` | `f200052a6de08a0cbd3a7ce323710cca0c23444163f5dc87ef861f1e4f4bccf7` |
| `case-05.ct` | Alien: Isolation | `ct2synth05.exe` | `68ca722ed125bbab73571a788012a1dba341b700d254df15c0131bd4096a9b05` |
| `case-06.ct` | Resident Evil 2 | `ct2synth06.exe` | `f2d48c3b28856f257afd8c728cd1f306a5f176dd826ac13c418f92776353daf1` |
| `case-07.ct` | Borderlands 3 | `ct2synth07.exe` | `5d47aa28e1beef64c59665f49ba9e023602f94a8717405b6819cc12bd9f74727` |
| `case-08.ct` | Clair Obscure: Expedition 33 | `ct2synth08.exe` | `f3f2bc5a4780199e66e34b140e89f556067ef4e811499633418585546e06f7d8` |
| `case-09.ct` | Silent Hill Townfall (Steam build) | `ct2synth09.exe` | `a7f9c7aeb65fca7fe549bb5d00cf6a5e76643f528cbe7a04957662fa145ffb` |
| `case-10.ct` | Senua's Saga: Hellblade 2 | `ct2synth10.exe` | `1aa44cd499c1ec7bc3e377933e7cccd482a33a1e485d8eccf90316ef820e6cad2` |
| `case-11.ct` | Red Dead Redemption 2 | `ct2synth11.exe` | `80ecb65161b341a68f1f228504577ea9b70b381023187201f791c6ffac99249d` |
| `case-12.ct` | Silent Hill Townfall (community "rml" build) | `ct2synth12.exe` | `69cd8349fa89fefd40e7e5e409605a74278532acfb71e37b1ebd7abe2cd83a47` |
| `case-13.ct` | Resident Evil 4 | `ct2synth13.exe` | `b6775e1611e2436e6a7fcf22a0586e18eae2c541d2143329e715179ce668e526` |
| `case-14.ct` | PRAGMATA (synthetic behaviour derivative, WP-14) | `ct2synth14.exe` | `e7df5b8adfc58b438464045e1c350d9f0be322c51e92f6761101c6168b43364f` |
| `case-15.ct` | Synthetic module & token shapes + offset-arithmetic derivative (WP-19/20/21/22/23 part 1: `$process` AOB scan, `@@:` globalalloc cursor, digit-leading module atom, `A:B`/`A::B` managed labels, folded pointer offsets incl. signed/annotated forms; bare token, symbol/dotted/empty-annotation offsets and the 33-offset chain stay blocked with the exact reasons) | `ct2synth15.exe` | `cdc1ad6ceacb559891c0f4a9cf4086187460dd061df5e03ad7cb82340b1cc44e` |
| `case-16.ct` | Synthetic linked-dropdown + separator-row derivative (WP-24/27/34: part 1 — shared read-only list with empty-value `:Basic:`/`:Advanced:` separator rows, linked records borrowing the choices with `link_target_id`, own list with one separator row; part 2 — linked byte-array (ByteLength=2) and bit-field records resolved against their own dropdown choices, wrong-length byte-array choice and dangling link target stay blocked with the exact named reasons; comma-decimal, `??` and out-of-range choices stay blocked per choice) | `ct2synth16.exe` | `cf7ef73a2c326edee6b6d87853f454996789add71e9cea7d7440347e41fcbb25` |
| `case-17.ct` | Synthetic addressless-demotion & hex bit-pattern derivative (WP-32/33/34: addressless value records demoted to non-actionable placeholder headings, hexadecimal Float/Double as raw IEEE-754 bit patterns; ShowAsHex string and undefined custom type stay blocked with the exact named reasons) | `ct2synth17.exe` | `893f961c5b36ad0c923bec3a3e138508086068a6cc970fc5f7fb6ff8487f0f49` |
| `case-19.ct` | Synthetic duplicate-ID robustness (Octopath/HellPie-style duplicate CheatEntry IDs; keep-first, dropped duplicates stay non-addressable, unique child of a dropped duplicate group survives re-parenting; WP-25) | `ct2synth19.exe` | `80690e8265e51cfe031ea02dbdd7bf2aeae898da034931f037044cbc930a3f7a` |
| `case-20.ct` | Synthetic Lua-directive & phase-marker derivative (WP-26: no-op `{$...}` directives, precise unknown-directive error, structural in-block `[ENABLE]`/`[DISABLE]` boundaries with shared preamble, redundant `{$asm}` no-op, contentless `[DISABLE]` one-shot, duplicate marker stays fail-closed) | `ct2synth20.exe` | `43f28580204c7fb3c18f5a28b4db2d73b112520bda26445db0a886f849a50b1c` |

Game names appear only as documentation-level provenance of the synthetic
shapes; the tables themselves contain no game code, assets or strings.

## Usage

The pinned case files are the inputs for the deterministic measurement
chain (see `documentation/native-verification.md`). Stage 2 and stage 3
refuse to write into the directory containing their inputs, so each uses a
scratch output directory; stage 3 consumes the committed
`gap_inventory/feature-coverage.json` so its provenance stays byte-stable:

```
python tools/corpus_denominator/__main__.py --corpus TableReferences --output gap_inventory --run-id repo-reproducible
python tools/corpus_denominator/feature_matrix.py --gap-report gap_inventory/gap-report.json --inventory gap_inventory/inventory.json --output <scratch2> --run-id repo-reproducible
copy <scratch2>/feature-coverage.json gap_inventory/feature-coverage.json
python tools/corpus_denominator/ap11_campaign.py manifest --gap-report gap_inventory/gap-report.json --inventory gap_inventory/inventory.json --feature-coverage gap_inventory/feature-coverage.json --corpus-root TableReferences --output <scratch3> --run-id repo-reproducible
copy <scratch3>/ap11-campaign.json gap_inventory/ap11-campaign.json
```

Byte-identical output requires the identical corpus bytes and run id; the
committed artifacts under `gap_inventory/` are the reference result.
