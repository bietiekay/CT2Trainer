# Synthetic clean-room corpus (TableReferences)

This directory contains the 27 pinned case tables used by the corpus
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
| `case-15.ct` | Synthetic module & token shapes + offset-arithmetic derivative (WP-19/20/21/22/23 part 1: `$process` AOB scan — record 13 registers `synProcScan` (registersymbol/unregistersymbol) as the cross-record provider for the part-2 cast records — `@@:` globalalloc cursor, digit-leading module atom, `A:B`/`A::B` managed labels, folded pointer offsets incl. signed/annotated forms; part 2 with WP-30: 21 records — cast indirection depth 1–2 supported via the bounded expression profile, depth 3 stays blocked with the named depth-limit reason, module-prefixed 3-segment managed labels with/without offset supported; bare token, symbol/dotted/empty-annotation offsets and the 33-offset chain stay blocked with the exact reasons) | `ct2synth15.exe` | `5bc013eb2a8215fecae039b4d514968a3ac8d75b22e236786e4a7f7a52cf881b` |
| `case-16.ct` | Synthetic linked-dropdown + separator-row derivative (WP-24/27/34: part 1 — shared read-only list with empty-value `:Basic:`/`:Advanced:` separator rows, linked records borrowing the choices with `link_target_id`, own list with one separator row; part 2 — linked byte-array (ByteLength=2) and bit-field records resolved against their own dropdown choices, wrong-length byte-array choice and dangling link target stay blocked with the exact named reasons; comma-decimal, `??` and out-of-range choices stay blocked per choice) | `ct2synth16.exe` | `cf7ef73a2c326edee6b6d87853f454996789add71e9cea7d7440347e41fcbb25` |
| `case-17.ct` | Synthetic addressless-demotion & hex bit-pattern derivative (WP-32/33/34: addressless value records demoted to non-actionable placeholder headings, hexadecimal Float/Double as raw IEEE-754 bit patterns; ShowAsHex string and undefined custom type stay blocked with the exact named reasons) | `ct2synth17.exe` | `893f961c5b36ad0c923bec3a3e138508086068a6cc970fc5f7fb6ff8487f0f49` |
| `case-18.ct` | Synthetic AA label & directive pack (WP-28/29/31/35/36: positional `return:` hooks over two AOB scans with a value consumer on the registered scan symbol, alloc-only init provider + pointer consumer, 2-arg `dealloc`, multi-token `registersymbol`, `registerlabel`, `fullAccess` no-op, `/* */` block comment in the data dialect, operand-less `dq` reservation, process-wide `aobscan` + `aobscanregion`, `createthread`/`threadwait` gate, 3-arg `$process` `globalalloc` + consumer; the globalalloc DISABLE reinitialization record and the label-inside-global-initializer record stay blocked with the exact W2-C named keep-block reasons) | `ct2synth18.exe` | `e3405ebcf7fa566a101ad424c5318348c89e5e020636d8f2533d125c89f7e2f6` |
| `case-19.ct` | Synthetic duplicate-ID robustness (Octopath/HellPie-style duplicate CheatEntry IDs; keep-first, dropped duplicates stay non-addressable, unique child of a dropped duplicate group survives re-parenting; WP-25) | `ct2synth19.exe` | `80690e8265e51cfe031ea02dbdd7bf2aeae898da034931f037044cbc930a3f7a` |
| `case-20.ct` | Synthetic Lua-directive & phase-marker derivative (WP-26: no-op `{$...}` directives, precise unknown-directive error, structural in-block `[ENABLE]`/`[DISABLE]` boundaries with shared preamble, redundant `{$asm}` no-op, contentless `[DISABLE]` one-shot, duplicate marker stays fail-closed) | `ct2synth20.exe` | `43f28580204c7fb3c18f5a28b4db2d73b112520bda26445db0a886f849a50b1c` |
| `case-21.ct` | Synthetic runtime dynamic address provider (WP-38 / GC-B6: Lua provider registers exactly one symbol on enable and unregisters it on disable; the nearest heading carries the `address_provider` binding; three relative children `+10`/`+14`/`+18` adopt the runtime-resolved base as `expression/v1` values; the static module-relative sibling pins the module token) | `ct2synth21.exe` | `1f4ee77ea9b1e3d06ace85551fdbfd7e9662895485e5ea43dbd18559d3c5acbf` |
| `case-22.ct` | Synthetic table-Lua bootstrap (WP-41, phase 1: read-only table LuaScript with the main body defining top-level globals `synthBase22` (read from `0x1008`) and the helper function `synthStep22`, plus the named script tab `SynthTab22` adding the constant global `synthLimit22` in document order; two record scripts reference the table globals and count as inactive at plan time, one record script is independent of the table source, one static module-relative value sibling) | `ct2synth22.exe` | `0f90e1bf8699469113b85fd812a4eb317d884eee905456e2c7afd37b4f0ce528` |
| `case-23.ct` | Synthetic record-hotkey derivative (WP-40: F1 (VK 112) activation hotkey on the alloc-only anchor script, F2 (VK 113) value operation on the child 4-byte row, first-wins F1 conflict pair on the second script record) | `ct2synth23.exe` | `e3568de1225e5d84d8b468b0daaad64153c70c034a550754eb022caaa001dab3` |
| `case-24.ct` | Synthetic Lua-owned symbol handover (WP-37: record 1 registers `SynthHandBase24` from record Lua, record 2 is an allocation-only provider of `synthHandAlloc24`; value records 3/4 and AA patch record 5 consume the symbols and depend on their owners; records 6/7 duplicate the `SynthHandDup24` provider so record 7 is blocked by the named keep-first reason and the contested symbol stays out of the external-ownership map; record 8 attempts a foreign `unregistersymbol` of `SynthHandBase24` and is blocked by the named foreign-release refusal) | `ct2synth24.exe` | `dcca38baf1ac4b08fc2a33f986083c071f815befd5ac868b1ea70cf9f6ea5ae6` |
| `case-26.ct` | Synthetic Requiem-style AA grammar & table-symbol pack (WP-43/44: single-quoted `db` string data literal and single-quoted instruction operand byte-identical to the double-quoted twin; multi-token `registersymbol`; `unregistersymbol(*)` + `dealloc(*)`; 3-arg `globalalloc` with `$process` over a pointer-chain label definition with consumer value rows; pre-`[ENABLE]` `define` + `registersymbol` demoted to a supported module-patch record; one comments-only script demoted to an inert heading with the exact WP-44 reason) | `ct2synth26.exe` | `034b1d89e1da45dd05818b55bbbe8bb0db8e920cb6171aaa6304df3cd9a2fb5d` |
| `case-27.ct` | Synthetic Innocence-style provider/UDS pack (WP-45/46 part 1: table-level `UserdefinedSymbols` — UDS-only-provided base consumed by a value record and a symbol provided by BOTH a UDS entry and a script record where the record provider wins (no UDS residual); alternative provider pair for one symbol (selection-aware keep-first dedupe: the default compile keeps provider 40, provider 41 blocked by the exact named duplicate reason, consumer binds to the kept provider); `#` decimal/signed `<Offset>` slots per the CE `ConvertHexStrToRealStr` convention; dangling `DropDownListLink` demoted to an empty plain dropdown with the exact named plan warning; 5-deref address chain under the raised indirection bound (2 -> 6)) | `ct2synth27.exe` | `2695fb5735c61f817358bf94ce1c893f30efd7342f9e8d44de979e1e5e3f0bb7` |
| `case-31.ct` | Synthetic Sinking City 2 field-shape pack (WP-55/56: multi-match AOB provider + consumer — first/lowest-address match semantics at runtime with multi-match-only debug diagnostics, single-match log lines keep the 0.14 shape; record-Lua CE-global stubs — `OpenProcess` identity no-op + `ShellExecute` safe no-op + inert `getMainForm`/`createMenuItem`/`addCompactMenu` menu surface in both CE first-letter spellings; empty self-closing `UserdefinedSymbols` tag (no warning, no uninterpreted section); pointer value child with hex `<Offset>` slots) | `ct2synth31.exe` | `1ab46a835ba1c8b016ff05e85aaab9678ed6f25c4bf7d96fe7ba38632435fcb0` |

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
