# Selected MIT LibCpp2IL static adaptation

The Native module `src/ct2trainer/native/il2cpp_static.py` is a stdlib-only
Python adaptation of selected LibCpp2IL PE and metadata layout/read rules.
Upstream: SamboyCoding/Cpp2IL at b5ad444b82267cb1e4b88b8b373c008105bdea52.
Copyright (c) 2020 Sam Byass; the exact MIT text is retained in LICENSE.txt.

Original C# bytes remain under upstream/, with URLs/sizes/SHA256s in
upstream-pins.json and the pinned upstream Git tree in upstream-tree.json.
LOCAL-CHANGES.md records the local adaptation and source-only adoption. No
upstream C# code is executed, compiled or required by the Native build.

The adapter reads bounded matching I386/PE32 and AMD64/PE32+ file snapshots and
explicit metadata version 29. Interpreted image/type/method/parameter strides
are 40/88/32/12 bytes. Other metadata section bodies are extent-checked only.
Exact static names/raw signature indices must disambiguate overloads. Raw
Il2CppType indices, tokens and preferred-image VAs are metadata/file coordinates,
not target-bound calling or pointer authority.

The owned tests use hand-authored inert byte fixtures, not Unity outputs. An
actual owned Unity-produced v29 fixture, binary registrations, live image
lifetime/method mapping and controlled invocation are separate unresolved gates.
There is no engine/Lua/Mono integration, game input or CE implementation here.
