# Owned Mono source fixture

This source-only fixture initializes its own supplied Mono once, loads only its
own IL and then registers that already-loaded root/assembly with the collector.
It is separate from the adapter, which never initializes/loads/unloads Mono.
No vendor runtime binary or original game code is included. Root domain ID0 is
valid; the source intentionally has no runtime/domain cleanup through exit and
no managed callback reentry. Windows/MSVC and local Mono inputs are prerequisites.

Build-MonoSources.ps1 builds the adapter without Mono import dependencies.
Build-FakeMonoExports.ps1 builds stateless first-party fake exports for native
boundary tests. Build-OwnedMonoFixture.ps1 compiles the owned acceptance host
against explicitly supplied local Mono; it starts no target and copies no DLLs.
Every runtime/target run is a separate explicitly owned gate. The original44/arch
and54 combined checks refer to the prior linked-fixture source, not this adaptation.
