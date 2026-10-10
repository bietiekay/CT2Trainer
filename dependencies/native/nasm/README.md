# NASM 3.02 (BSD-2-Clause)

These unmodified inputs come from the official NASM release server and the
official `nasm-3.02` source tag. The normal build uses archived files offline.
`manifest.json` records exact SHA-256 hashes; the adapter additionally verifies
the executable hash before every invocation. Hashes establish these archived
bytes, not an upstream signing claim.

- Windows x64 archive: https://www.nasm.us/pub/nasm/releasebuilds/3.02/win64/nasm-3.02-win64.zip
- Source archive: https://www.nasm.us/pub/nasm/releasebuilds/3.02/nasm-3.02.tar.xz
- License: https://github.com/netwide-assembler/nasm/blob/nasm-3.02/LICENSE
- Flat binary and multisection documentation: https://www.nasm.us/doc/nasm09.html

Restore into `.tools/native/nasm-3.02/` by extracting the Windows ZIP. It contains
`nasm-3.02/nasm.exe`. `CT2TRAINER_NASM` may select that pinned executable in a
different directory. A distributable frozen program can carry it at
`native-tools/nasm.exe`; it must also carry the copyright, BSD conditions and
disclaimer from `LICENSE.txt` in its notices. The source archive remains an
independent redistributable dependency; none of these inputs contains CE code.

CT2Trainer emits compact physical sections with `vstart` values equal to the
actual allocated target addresses. Empty virtual sections give imported symbols
address relocation types for RIP-relative operands. A generated footer describes
each block and label, so no arbitrary user NASM file, include or macro is needed.
The assembler runs locally with a time limit and never accesses target memory.

The upstream license permits source and binary redistribution when its notices
are retained. Build or redistribution of user-supplied tables has separate input
rights; these archives grant no rights to those tables.
