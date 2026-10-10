# Synthetic clean-room corpus (TableReferences)

This directory contains the 13 pinned case tables used by the corpus
denominator tool (`tools/corpus_denominator/`). All files are
independently authored, synthetic `.CT` tables; no third-party game table
content is part of this repository. They exercise the same 36 gap classes
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

Game names appear only as documentation-level provenance of the synthetic
shapes; the tables themselves contain no game code, assets or strings.

## Usage

The pinned case files are the inputs for the deterministic measurement
chain (see `documentation/native-verification.md`):

```
python tools/corpus_denominator/__main__.py --corpus TableReferences --output gap_inventory --run-id repo-reproducible
python tools/corpus_denominator/feature_matrix.py --output gap_inventory --run-id repo-reproducible
python tools/corpus_denominator/ap11_campaign.py manifest --output gap_inventory --run-id repo-reproducible
```

Byte-identical output requires the identical corpus bytes and run id; the
committed artifacts under `gap_inventory/` are the reference result.
