"""Load-time compatibility and size gate for one table file.

Applied at the moment the Master Trainer requests a table load for a
matched running process (auto-load or picker load), before the plan
compile.  The gate re-proves the file against the index entry from the
last scan, because the folder content may have changed in between:

- the path still exists and is a regular file (the file may have been
  deleted or replaced after the scan);
- the content is non-empty and within the tool's load limit
  (``MAX_TABLE_BYTES`` — the same bound the table parser and the plan
  compiler enforce);
- the content hash still matches the index entry (a file that drifted
  since the last scan is a named stale refusal: a Rescan refreshes the
  index and re-arms the load; this also keeps the MT-6 settings-sidecar
  keying — the table content sha256 — consistent with what the trainer
  actually loads);
- the content is a trainer table this tool can load at all (XML CT or
  legacy binary CT, through the tested ``read_table`` parser — malformed
  XML, DTD/entity input and unparseable legacy binaries are all named
  refusals).

Every refusal is named and displayable: a stable machine-readable code
plus a human detail.  The gate never raises for table-content problems;
it returns the refusal in the result.  The UI layer raises
``TableLoadGateRefusal`` from the plan compiler, so the orchestrator's
fail-closed loop guard records the exact (process name, PID) pair and
the next tick does not hot-retry — the failure stays visible in the
status line even though the target process was found.

Pure standard library plus the main-branch table library (deferred
imports, the same pattern as :mod:`.table_index`); platform
independent.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

# Stable refusal codes (machine-readable; the detail stays displayable).
CODE_FILE_MISSING = "table-file-missing"
CODE_NOT_A_FILE = "table-not-a-file"
CODE_READ_FAILED = "table-read-failed"
CODE_EMPTY = "table-empty"
CODE_TOO_LARGE = "table-too-large"
CODE_CHANGED_SINCE_LAST_SCAN = "table-changed-since-last-scan"
CODE_NOT_LOADABLE = "table-not-loadable"
CODE_CHANGED_DURING_ANALYSIS = "table-changed-during-analysis"


class TableLoadGateRefusal(ValueError):
    """A named, displayable load-gate refusal.

    Raised from the Master Trainer's default plan compiler so the
    orchestrator's load failure handling (named error + fail-closed
    loop guard) applies unchanged.  ``code`` is the stable machine
    token; the string of the exception is the human detail.
    """

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class TableGateResult:
    """Outcome of one load-time gate pass over a table file.

    ``ok`` with ``size``/``sha256`` proves the file is loadable for the
    recorded entry; a refusal carries the stable ``code`` and the
    displayable ``detail`` (``size`` is reported whenever it was
    established before the refusal).
    """

    ok: bool
    size: int | None = None
    sha256: str | None = None
    code: str | None = None
    detail: str | None = None


def _refuse(code: str, detail: str, size: int | None = None) -> TableGateResult:
    return TableGateResult(False, size=size, code=code, detail=detail)


def gate_table_for_load(path: str | Path, entry) -> TableGateResult:
    """Re-prove one table file at load time against its index entry.

    ``entry`` is the :class:`.table_index.TableEntry` the index holds
    for this path (its ``sha256`` is the content hash of the last
    scan).  The checks run cheapest-first and stop at the first
    refusal; a passing gate means the file is present, within the
    load limit, unchanged since the last scan and parseable by the
    tested table parser — the same preconditions the plan compiler
    needs.
    """
    p = Path(path)
    if not p.exists():
        return _refuse(CODE_FILE_MISSING,
                       "table file is missing (deleted after the last "
                       "scan): " + str(p))
    if not p.is_file():
        return _refuse(CODE_NOT_A_FILE,
                       "table path is not a regular file: " + str(p))
    try:
        size = p.stat().st_size
    except OSError as exc:
        return _refuse(CODE_READ_FAILED,
                       "table stat failed: " + exc.__class__.__name__
                       + ": " + str(exc))
    if size == 0:
        return _refuse(CODE_EMPTY,
                       "table file is empty (0 bytes): " + str(p),
                       size=0)
    from ...table import MAX_TABLE_BYTES
    if size > MAX_TABLE_BYTES:
        return _refuse(CODE_TOO_LARGE,
                       "table exceeds the " + str(MAX_TABLE_BYTES)
                       + "-byte load limit (size " + str(size)
                       + " bytes): " + str(p),
                       size=size)
    try:
        data = p.read_bytes()
    except OSError as exc:
        return _refuse(CODE_READ_FAILED,
                       "table read failed: " + exc.__class__.__name__
                       + ": " + str(exc),
                       size=size)
    sha = hashlib.sha256(data).hexdigest()
    if sha != entry.sha256:
        return _refuse(CODE_CHANGED_SINCE_LAST_SCAN,
                       "table changed since the last scan (Rescan "
                       "refreshes the index and re-arms the load)",
                       size=size)
    from ...table import TableError, read_table
    try:
        table = read_table(p)
    except (TableError, OSError, ValueError) as exc:
        return _refuse(CODE_NOT_LOADABLE,
                       "table is not loadable: "
                       + exc.__class__.__name__ + ": " + str(exc),
                       size=size)
    if table.source_sha256 != sha:
        return _refuse(CODE_CHANGED_DURING_ANALYSIS,
                       "table changed while it was being analyzed "
                       "(Rescan refreshes the index)",
                       size=size)
    return TableGateResult(True, size=size, sha256=sha)
