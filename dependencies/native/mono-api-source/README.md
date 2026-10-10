# Selected Mono public API source foundation

This directory contains 35 exact public SDK source files (including `opcode.def`),
plus the upstream LICENSE and PATENTS text from mono/mono commit
`0cbf0e290c31adb476f9de0fa44b1d8829affa40`, tag `mono-6.12.0.206`.
Original paths, Git blob SHA-1, sizes, SHA-256 and URLs are in upstream-pins.json.
No vendor DLL, MSI, import library, mscorlib, configuration, installer or runtime
implementation source is selected. `mono/mini/jit.h` is included at its original
source path rather than renaming it to the installed SDK's `mono/jit/jit.h`.

The selected public API declarations are covered by Mono's MIT scope; their
original notices remain intact. The exact project-root LICENSE retains its
broader mixed-license disclosures. Retaining that file does not import the
unselected GPL/BSD/MS-PL/runtime implementation components or claim the whole
repository/SDK/MSI is MIT. PATENTS.TXT is preserved without rewriting its scope.
The emitted C function-pointer prototypes are a local typed adaptation of these
pinned declarations; no Mono implementation body is copied.

Runtime DLL source/build closure is deliberately absent. If a future product
bundles Mono, it must prove that complete independently built runtime/class
library closure separately. The intended target supplies an already loaded,
explicitly admitted Mono. Native currently retains these public declarations
and its own adapter as a source-only foundation; there is no Engine, Lua or
Frozen managed-runtime route. Source/fake-export checks do not confirm real
Mono calls or game compatibility.
