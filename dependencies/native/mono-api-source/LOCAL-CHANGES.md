# Local adaptation record

- Retain all 35 selected public API source files byte-identically, plus LICENSE
  and PATENTS from commit 0cbf0e290c31adb476f9de0fa44b1d8829affa40. No header body
  is patched. Public declarations are consumed at their original source paths.
- Adapt the first-party collector previously reviewed in the ignored Mono draft.
  `tf_mono_start` is removed. The collector never sets runtime directories,
  parses config, initializes Mono, opens an assembly from disk, invokes fixture
  initialization, loads a module or unloads a domain/runtime.
- Add fixed typed exports from the pinned public prototypes (api-prototypes.json).
  Existing HMODULE is held by a normal OS module reference, every resolved
  address must be direct executable MEM_IMAGE code inside that same image.
  Partial tables are not returned. A version family string is an additional
  compatibility check, not a substitute for exact controller-owned module hash.
- Pass a private synchronous C deadline/check callback through every lookup and
  before/after the bounded runtime-build-info query. Its allocated result must
  still be freed after a late return; it does not publish any callable capability.
- Register an already loaded assembly in the trusted first-party host's root
  domain, on its existing attached entry thread. Root domain ID0 remains valid.
  Callback-free assembly and no domain/runtime cleanup through target exit are
  host source guarantees, not boolean/JSON flags verified by this library.
- Keep original bounded method/signature/GenericParam checks, private generation
  tokens, strong GC handles, explicit main/attached-worker affinity, original
  request deadline and retirement retention. No new wire/Lua adapter is added.
- Move fresh-runtime setup solely into owned_fixture_bootstrap.c, compiled only for
  the explicit source-owned acceptance fixture. It refuses an existing root and
  is not an adapter/Engine/bootstrap-injection path. Runtime DLL/lib/assemblies
  must be locally supplied and are never copied into the source artifact.
- Original first-party bytes and unified collector patches remain beside this
  ignored draft. Old 44-per-architecture and54 combined runtime evidence belongs
  only to its original linked-fixture bytes; new adapted runtime proof is open.

- Revision2: original-deadline admission samples QPC last after owner/frequency
  queries; final binding rechecks after thread identity. Before-bind collector
  calls refuse rather than dereference an empty dynamic table. Independent
  fake-query buffers are allocated, freed once and checked for leaks/bad frees.
  Deterministic clock/identity shims and actual prebind C admission tests cover
  these boundaries; no real Mono runtime or target child is used.

- Revision3: reject execute-only header regions before PE memcpy. Executable
  exports still use the distinct callable-code protection rule. A real own
  fake-image page transition to PAGE_EXECUTE is refused without a query, and
  original page protection is restored in the test finally block.

- Repository adoption: retain the reviewed adapter/header bytes unchanged;
  add an exact source-export allowlist, dependency manifest entries, preserved
  license notice and four closure/notice regression tests. The selected-source
  README now describes the active source-only scope. No managed-runtime route
  or runtime binary is added. Older linked-fixture checks remain historical.
