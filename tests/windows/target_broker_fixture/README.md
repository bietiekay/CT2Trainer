# Owned typed target broker

These independently authored sources use the Native MIT license. No CE source,
binary, collector protocol or original table script participates in this build.
The Windows DLL is loaded explicitly by our own host before requests are enabled;
there is no remote injection or arbitrary address execution mode.

Build both architectures in a fresh evidence directory:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tests/windows/target_broker_fixture/Invoke-TargetBrokerBuild.ps1
$env:PYTHONPATH='src'
.tools/native-build-env/Scripts/python.exe tests/windows/target_broker_fixture/probe.py --build-report <run>/verification.json --output-directory <fresh-run>/live-probe
```

The wire ABI is version 1, little endian, 664 bytes: a 152-byte packed scalar
header and a counted 512-byte payload. A local named pipe uses an explicit
creator-user DACL, rejects remote clients, and verifies the OS client PID against
a held PID/creation-time owner. The controller verifies the server PID and its
held target identity. A fresh 128-bit nonce and fixed generation bind each session.
Each session retains at most 64 immutable requests, payloads, events and worker
handles until target exit. IDs increase exactly once and cannot be submitted again.

Fixed compiled C calls verify x86 cdecl/stdcall, signed integers, a full 64-bit
return, a five-position integer/double/integer/float/integer signature, counted
UTF-16 including embedded zeroes, and an explicitly main-thread-only Boolean.
The host registers its dispatcher in trusted C; the mailbox cannot specify a
function pointer. These contracts motivate, but do not implement, the namespace/
class/method lookup and static Boolean invocation in Yooka IDs 95/97 or Disco
ID 216. No Mono or IL2CPP runtime has been built or called by this fixture.

The target alone performs aligned private CAS transitions from PREPARED to
RUNNING or CANCELLED_BEFORE_START. It checks the held owner and an absolute QPC
admission deadline before dispatch. The controller calibrates a conservative QPC
offset with a bounded same-host handshake and preserves the original caller's
absolute deadline. This proof uses the owned fixture's unhooked QPC; a future
speed/clock adapter needs an explicitly bound raw clock before game admission.
Worker completion requires the retained exact thread handle
to signal; main completion means the captured PID/TID/creation-time host thread
returned. TLS markers and both forms of completion are explicit evidence.

Immutable, hash-chained controller receipts record intent before launch and
dispatch. A lost acknowledgement consumes its ID and blocks new submissions.
A running timeout does not stop a thread or free its call buffers; a later result
does not clear uncertainty. Explicit target-owned cancellation plus completion is
required to establish that a prepared call did not run. Failed or incomplete
overlapped I/O retains its exact event, buffer, OVERLAPPED and pipe; the C server
stops dispatching. No unbounded buffer lifetime depends on a stack frame. The
owned host emits a terminal ledger/handle retention snapshot and exits through
its own input channel. No target thread is forcibly terminated.

The acceptance probe includes owner process death, foreign identities, duplicate
requests, lost acknowledgements, late completion, deadline refusal, main affinity,
and buffer/handle retention. Python fault tests exercise failed waits/incomplete
I/O and every post-launch setup gate. Future game integration remains separate:
explicit scope/state coordination, runtime/module binding, ABI descriptors beyond
these fixed signatures, managed attach/exception/reference handling, main-thread
scheduling, domain/unload fencing, and honest one-shot UI semantics. Invocations
must never be saved as reversible ON toggles or automatically replayed.

The fixture uses MSVC's compiled ABI rather than libffi because these signatures
are fixed. Mono's MIT runtime APIs, MIT LibCpp2IL metadata parsing and MIT-style
libffi remain researched candidates; none is required or redistributed here.
Primary public contracts: [named pipe access](https://learn.microsoft.com/windows/win32/ipc/named-pipe-security-and-access-rights),
[client identity](https://learn.microsoft.com/windows/win32/api/winbase/nf-winbase-getnamedpipeclientprocessid),
[QPC](https://learn.microsoft.com/windows/win32/sysinfo/acquiring-high-resolution-time-stamps),
[x64 ABI](https://learn.microsoft.com/cpp/build/x64-calling-convention),
[overlapped completion](https://learn.microsoft.com/windows/win32/api/ioapiset/nf-ioapiset-getoverlappedresult).
