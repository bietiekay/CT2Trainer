# Local adaptation record

Source: SamboyCoding/Cpp2IL at b5ad444b82267cb1e4b88b8b373c008105bdea52 (MIT).
The exact originals are retained with file/commit/URL hashes and original license.
No upstream source code was executed or altered.

Local changes, 2026-10-01:

- Translate the relevant C# field order/read rules into explicit little-endian
  Python `struct` decoding for declared metadata version 29 only. Its image,
  type, method and parameter row strides are 40, 88, 32 and 12 bytes; section
  headers contain offset and byte-size, not the later version's count.
- Restrict the PE reader to matching I386/PE32 and AMD64/PE32+ file inputs.
  Replace permissive first-section/truncating mappings with full extent, width,
  overlap, raw-source and header checks. Do not port export, registration or
  binary-method-pointer resolvers.
- Remove global runtime/reflection state, code-generation module lookups,
  generic resolution, logging and mutable version/reader sessions. Each parser
  consumes one immutable snapshot and emits immutable static identities.
- Add finite file/row/name bounds, strict UTF-8, row ownership validation and
  explicit ambiguity refusal. Do not guess newer/older metadata layouts.
- Preserve raw `Il2CppType` indices and tokens. Omit signature-name inference
  and method pointers because v29 global metadata alone cannot prove them.
- Add entirely hand-authored inert byte fixtures and positive/malformed tests.
  No game or Unity metadata fixtures and no live runtime evidence are claimed.

Potential future integration must keep this adapter attribution and originals,
include its MIT notice in source/binary export, and add reviewed target-bound
live resolver/invocation contracts independently of these static identities.

Active source-only adoption, 2026-10-01:

- Native adapter bytes are unchanged from independent review.
- Rename/import the owned test/helper into the Native test namespace; update unittest patch targets only.
- Retain originals/license/pins; add explicit helper export and exact MIT notice copy.
- No engine, compiler, UI, runtime dependency, Unity binary or live pointer integration.
