# Independent local clock core fixture

This fixture verifies independently authored integer clock math and local Windows
thread synchronization. It installs no hooks, loads no DLL, touches no other
process, and runs no game or table script. The original Windows clocks stay intact.

From the repository root, with installed archived MSVC/Windows SDK tools:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tests/windows/clock_fixture/Invoke-ClockFixture.ps1
$env:CT2TRAINER_CLOCK_FIXTURE='<fresh run>/x64/NativeClockFixture.exe'
python -m unittest discover -s tests -p test_native_clock.py -v
```

The script creates a fresh ignored `build/runs/native-clock-<ID>/`, preserves exact
source snapshots, compiler commands/logs, x64 and x86 PE hashes, fixture output and
`verification.json`. Optional Python checks compare 256 integer-conversion cases
with arbitrary-precision arithmetic. Repeat with the x86 EXE for its oracle check.

The C core accepts QPC ticks/frequency without floating point. Rates are integer
parts per million, from 0 to 16 inclusive. Fractional ticks survive repeated reads
and rate changes. One SRW lock serializes raw-QPC sampling, changes and snapshots.
Each millisecond clock keeps its capture QPC epoch, avoiding double-counting time
spent between initialization samples. A wrapper should bracket each capture with
original QPC calls and use their midpoint, reject an unreasonably delayed capture,
and report that bounded calibration uncertainty. GetTickCount32 derives the low
DWORD of GetTickCount64; multimedia time retains its independent captured phase.
QPC and tick64 are nondecreasing; DWORD outputs wrap. Sticky faults retain all last
valid outputs. A one-tick raw QPC ordering ambiguity clamps to the highest anchor;
larger regressions and arithmetic exhaustion stop clock advancement.

Nonzero, increasing owner tokens and a lease of at most 30 original-QPC seconds
control rates. Expiry is applied before reads and before every admitted control operation.
It advances at the old rate to the deadline, then at rate one to the current raw
sample. Late renewal cannot retroactively prolong an expired rate. Close restores
rate one with its accumulated offset. No API removes hooks or frees adapter state.

This is a **local** API: the callback must bypass future hooks and never reenter
the core. Future wrappers must preserve last-error behavior and use a TLS bypass;
they must release the core lock before touching a caller's QPC output pointer.
Debugger-held remote control must use an acknowledged generation-tagged command
mailbox consumed by a local caller; it must not wait for a lock held by a suspended
target thread. Keep future hooks, trampolines, adapter state and actual provider
modules pinned until target exit. Hook admission/relocation, remote control,
static/dynamic API interception, games and Wine/Proton are separate unverified work.

## Owned local adapter DLL

`clock_adapter.c/h` adds prefixed QPC/GetTickCount/GetTickCount64/timeGetTime
wrappers, original callbacks, TLS reentry bypass, preserved LastError on success, a bounded
command mailbox and acknowledgements. Initialization occurs outside loader lock;
system providers resolve through system module APIs and secure System32 loading.
QPC-bracketed captures use midpoint epochs; the entire calibration is bounded to
10 ms by default, configurable up to 100 ms, with at least one QPC tick of
representable uncertainty. The adapter reports its actual bracket windows. It
pins itself and its actual original provider modules until process exit.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tests/windows/clock_fixture/Invoke-ClockAdapterFixture.ps1
```

The script snapshots sources into a fresh ignored evidence run, builds x64 and
x86 DLLs and hosts with MSVC `/W4 /WX /O2 /MT`, and runs seven separate owned host
processes per architecture. Each host loads only its exact freshly built DLL.
Fake-clock, delayed-calibration and actual-Windows modes check acknowledgement
identity, busy/stale rejection, pause expiry, continuous close, nested original
callbacks, LastError, sticky faults and retention after ordinary FreeLibrary.
Additional modes check absolute pending/lease expiry, cancellation before and
during consumption, and 20,000 concurrent cancellation/status cycles with owner
generations beyond 32 bits. `-TestPlatformFault` builds a separate instrumented
fixture DLL with a test-only fault export and runs an eighth mode; the default
production DLL has no fault-injection export. Faulted submissions are rejected,
and a fault during a pending command produces an explicit snapshot-less fault ACK.
QPC FALSE returns a meaningful original or profile error through GetLastError;
successful QPC and the DWORD/64-bit clock getters preserve incoming LastError.
Four threads make 40,000 cycles across all four wrappers while 100 rate commands
are acknowledged. Exact slopes use original-QPC anchors carried in the ACKs.
PE imports/exports, compiler information, output, source and DLL hashes remain
beside `verification.json`. This remains source foundation, without deployment
into generated trainers or live hooks. The v2 interface closes the known
pending-intent, fault acknowledgement and QPC-error gaps of the earlier v1
design.

The v2 interface is same-bitness, with sizes and version fields checked explicitly.
`TFClockInitialize` fixes trusted originals and calibration once; `TFClockGetInfo`
reports frequency, calibration uncertainty and command/ack sizes. `TFClockSubmit`
uses one nonblocking slot and acquires no clock lock. Sequence numbers increase
for the DLL lifetime; owner generations follow the core's separate rule. Only a
future wrapper call consumes the command and publishes its exact transition ACK.
`TFClockTakeAcknowledgement` claims that immutable ACK before making the slot
available again. An accepted command without an ACK has not confirmed a change.
Commands carry absolute original-QPC not-after and lease deadlines obtained from
`TFClockReadRawCounter`. Pending intent is bounded to one real second and leases
to thirty seconds from submission. Consumption cannot start a fresh interval.
The core checks not-after again against its own locked sample, closing a delay
between the adapter's preliminary sample and actual control admission. An overdue
pending command gets an expiry ACK and cannot activate; existing leases expire
at their original deadline when the next admitted clock call samples raw QPC.

`TFClockCancel` advances a monotonic owner-generation fence with an explicitly
8-byte-aligned atomic protocol on x86/x64. It never acquires a clock lock. If it
wins the READY slot, it drains that command directly to a cancellation ACK with
`snapshot_valid=false`; this proves the pending command was not applied, rather
than proving an earlier active rate is off. Cancellation during BUSY consumption
is initially uncertain. A local wrapper closes any fenced live owner before
publishing its retirement generation. `TFClockGetFenceStatus` reads that monotonic
retirement proof without acquiring the clock lock. Retain owner/effect receipts
while the ACK or retirement status is uncertain; no cancellation response proves
that adapter/trampoline memory may be unloaded. Closed, cancelled and expired
pending owner generations cannot supply a fresh rate intent.

Future hook integration must supply verified original trampolines, their actual
module provider addresses, and target-lifetime retention of private trampoline
code. This adapter pins modules, but neither proves nor frees private machine code.
Remote mailbox publication, patch admission, instruction relocation and remote
module loading remain separate work; a debugger-held controller must never wait
for this local clock lock. No safe live unhook/unload or game/Proton claim follows
from the owned local DLL fixture.
