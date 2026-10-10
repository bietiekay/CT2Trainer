# Owned String fixture

This subtree is independently authored test material. It contains no CE input,
game table, injection, hook installation or executable callback. It is ignored
evidence. Its first-party source is promoted and included in the Native source-
export allowlist. Compiled target hashes and actual runtime evidence are recorded
separately; a fresh C build does not inherit another binary's runtime proof.

`Invoke-StringFixtureBuild.ps1 -OutputDirectory <fresh-path>` builds a source
snapshot and `NativeStringFixture.exe` in separate x64/x86 directories with
MSVC `/W4 /WX /Od /TC` and a nonincremental link. Failures and compiler command,
version and path logs remain in the fresh output. The successful `build-1`
snapshot is immutable evidence; rebuild into a different output directory.

## JSON-lines protocol

The first stdout line has schema `ct2trainer-owned-string-target/v1`.
It includes PID, pointer width, PE machine, executable name, main-image base and
`SizeOfImage` read from the child's own PE header. The child does not declare a
trusted creation identity; the controller must independently query identity and
bind the exact executable/source hash.

The `buffers` address map has `ascii`, `utf16` and `fixed`. Each exposes absolute
address and RVA, encoded-unit length, unit size, complete declared read span,
full guarded span, before/after addresses and RVAs, and eight guard bytes on
either side. The globals are distinct committed `PAGE_READWRITE` image data.
These guards are ordinary sentinel bytes, not Windows `PAGE_GUARD` pages.

| Buffer | Declared span | Initial bytes / visible text | Tail |
| --- | --- | --- | --- |
| `ascii` | 8 bytes | `old\0QRST`, visible `old` | Offset 4, four untouched declared-tail bytes |
| `utf16` | 16 UTF-16 units / 32 bytes | `OLD`, valid `D83D DE42` pair, aligned NUL | Offset 12, ten tail units; the first is deliberately invalid lone `DEAD` |
| `fixed` | 8 bytes, no terminator semantics | `FI\0XED!?`, embedded NUL is literal | `tail_offset == read_bytes`; every byte belongs to the fixed value |

`readonly` and `executable` describe separate owned private pages containing
eight observable bytes. Their actual protections are `PAGE_READONLY` (2) and
`PAGE_EXECUTE_READWRITE` (64). No executable page is called. Each also exposes a
module-relative pointer-slot RVA, allowing a controller to derive the target
address from `[(module base) + pointer_rva]` at the correct pointer width.
Both are intended negative String-write admission cases; this local fixture
verification establishes the protections, not runtime refusal behavior.

Accepted stdin lines are `status`, `mutate-prefix`, `mutate-tail` and `quit`.
LF and CRLF are accepted. Unknown input exits with a failure. Each status or
mutation returns one `ct2trainer-owned-string-status/v1` line with PID,
command sequence, hexadecimal full value and guard bytes, and actual queried
memory-region attributes. Output contains no decoded string assumptions.

`mutate-prefix` changes only the first byte/unit of each buffer to `M`.
`mutate-tail` toggles the low bit of the final byte/unit in each buffer. For
ASCII/UTF-16 this is the ignored declared tail. For `fixed` it is an owned
literal byte that a fixed-string freeze should restore. Guards and negative
pages are unaffected. There are no background target writers; after each
command the main thread waits for the next stdin line. `quit` releases both
owned private pages and exits normally.

## Independent local proof

Run `verify_string_fixture.py --build <build-path> --output <fresh-path>` using
the archived Windows Python. It launches exact hash-checked new children one
at a time with hidden windows, opens only VM_READ/QUERY_INFORMATION rights,
queries image identity and creation FILETIME, compares local/remote PE fields,
reads every full guarded buffer and private pointer slot, checks protections,
issues the explicit local mutation commands, and observes normal exits.
It never uses WriteProcessMemory, changes remote protection, or acquires a
debug-event proof. Its JSON/logs are retained even if a check fails.

`runtime-1/verification.json` records 29 successful checks per architecture.
This proves owned target layout/protocol/read observations only. The String
controller still needs source/identity binding, held-event publication,
precise literal-prefix write/undo and tail preservation, overlap and freeze
policy, refusal of read-only/executable/incomplete spans, and failure/late-guard
tests before source/frozen trainer acceptance can be claimed.

The module/RVA interpretation follows the public Microsoft
[PE format](https://learn.microsoft.com/en-us/windows/win32/debug/pe-format).
