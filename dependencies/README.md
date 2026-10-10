# Native build dependencies

All inputs stored here are recorded in `manifest.json` with size and
SHA-256. The native build (`scripts/Build-Native.ps1`) verifies the
inventory before use. No dependency is downloaded from the network during
the build.

| Storage | Version / origin / use |
| --- | --- |
| `python/python-3.12.14-windows-x64-portable.zip` | Local Python runtime with standard library, Tcl/Tk, ensurepip and license file; site-packages/bytecode caches excluded; private byte-pinned copy |
| `python/requirements-build.txt`, `python/wheels/` | PyInstaller 6.22.3 plus all pinned build dependencies; wheels archived via pip/PyPI |
| `native/nasm/` | NASM 3.02 (BSD-2-Clause): source + pinned Windows-x64 EXE |
| `native/iced-x86/` | iced-x86 1.21.0 (MIT): source + Windows ABI3 wheel |
| `native/lupa/` | Lupa 2.8 (MIT): source + Python-3.12 Windows wheel, incl. upstream Lua (MIT); Native explicitly selects `lupa.lua53` |
| `native/libcpp2il-static/` | Eight selected MIT LibCpp2IL C# originals, license and commit/file pins, plus the local Python adaptation note |
| `artifacts.json` | (currently empty – no large file parts needed) |

Every directory keeps its upstream origin and exact license. The native
build hashes exclusively the `python/` and `native/` inputs.

The user authorizes local forks, purpose-bound changes and library API
breaks for a maintainable independent trainer; upstream contributing is
optional. Keep unmodified upstream archives and version/hash pins, document
fork patches and build evidence alongside, and provide regression proofs
before a binary pin is changed.
