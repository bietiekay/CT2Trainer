# Owned process and nth scan fixture

This independently authored C target provides one 32-byte pattern in a private
RW allocation and three 16-byte patterns in its main image. `add-first` adds an
earlier module occurrence while a trainer is active: disable must use its captured
address. All patterns are initialized by the target itself. There is no injection,
game dependency or CE implementation input.

`Invoke-ScanFixtureBuild.ps1` creates fresh x64/x86 builds with source snapshots,
compiler logs, PE architecture and output hashes. A successful build alone does
not prove scan, trainer publication or game compatibility. Runtime evidence must
also check exact target identity, independent readback, complete matches, unchanged
context/sentinels, disable, saved reattach and actual frozen output.

The child accepts only `status`, `add-first` and `quit` on standard input; it
prints bounded JSON metadata/results on standard output. Close input exits normally.
