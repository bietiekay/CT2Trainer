"""Pure builder for the MT-22 waiting-view "Table details" window.

The details window is read-only: it renders the indexed facts for one
table (relative path, folder, size, modified, bound processes, index
status, pin state, last-used timestamp, running PIDs, content sha)
plus the on-demand load-gate re-check - the same
``table_gate.gate_table_for_load`` pass MT-9 runs at load time - so
the user can inspect a table and see its current loadability (named
refusal code + displayable detail) before loading it.  MT-24 (0.32)
adds the entry-analysis block (the persisted background plan-analysis
entry for the table's content sha: the entry count, the blocked
count, the top blocked reasons, or the named failure) below the
load-gate row.

The builder is pure: every fact is an argument (the gate result is
computed by the UI layer and passed in), so this module is
headless-testable and touches no I/O itself.  Platform independent.
"""
from __future__ import annotations


def format_size(size: int) -> str:
    """Compact human-readable byte size (the Size column style)."""
    if size < 1024:
        return str(size) + " B"
    if size < 1024 * 1024:
        return str(int(size / 1024)) + " KB"
    return f"{size / (1024 * 1024):.1f} MB"


def format_mtime(mtime_ns: int) -> str:
    """Local 'YYYY-MM-DD HH:MM' (the Modified column style)."""
    from datetime import datetime
    return datetime.fromtimestamp(mtime_ns / 1e9).strftime(
        "%Y-%m-%d %H:%M")


def gate_line(gate) -> str:
    """The load-gate line of the details window.

    ``gate`` is a ``table_gate.TableGateResult`` (or ``None`` = not
    checked).  A passing gate proves the file matches the last scan;
    a refusal shows the stable machine code plus the displayable
    detail - the same two-part contract MT-9 uses at load time, so
    the window never re-invents the wording.
    """
    if gate is None:
        return "not checked"
    if gate.ok:
        return "OK (loadable - the file matches the last scan)"
    return (gate.code or "?") + ": " + (gate.detail or "no detail")


def table_detail_lines(entry, *, root: str, pinned: bool,
                       last_used: str | None,
                       running_pids,
                       gate,
                       analysis=None,
                       notes=None,
                                              attach=None,
                       autoload=None) -> list:
    """Ordered ``(label, value)`` rows for the read-only details
    window of one indexed table.

    ``entry`` is the ``table_index.TableEntry``; ``root`` is the
    indexed folder; ``last_used`` is the stored UTC timestamp from
    the rolling recent list (or None when the table was never loaded
    in a remembered session); ``running_pids`` are the PIDs of the
    bound processes currently visible in the process watch; ``gate``
    is the on-demand gate result (see :func:`gate_line`);
    ``analysis`` (MT-24, 0.32) is the persisted background
    plan-analysis entry for the table's content sha from
    ``table_analysis.AnalysisStore`` (or None while pending) - it
    adds the entry-analysis rows below the load-gate row;
    ``notes`` (MT-27, 0.35) is the persisted notes/tags entry for
    the same content sha from ``table_notes.NotesStore`` (or None
    when the table carries no organization metadata) - it adds the
    note / tag rows below the entry-analysis block;
    ``attach`` (MT-28, 0.37) is the persisted per-table process
    binding for the same content sha from
    ``table_attach.AttachStore`` (or None while the table carries no
    remembered choice) - it adds the "Remembered process" row below
    the note / tag block;
    ``autoload`` (MT-29, 0.39) is the persisted per-table auto-load
    policy entry for the same content sha from
    ``table_autoload.AutoLoadStore`` (or None while the table carries
    the documented default) - it adds the "Auto-load policy" row
    below the remembered-process block.
    """
    names = ", ".join(entry.process_names) or "(none found)"
    if entry.status == "ok":
        status = "ok"
    else:
        status = "unreadable: " + (entry.detail or "no detail")
    pids = sorted(set(running_pids))
    if pids:
        running = "PID " + ", ".join(str(p) for p in pids)
    else:
        running = "not running"
    lines = [
        ("Table", entry.relative_path),
        ("Folder", root),
        ("Size", format_size(entry.size)),
        ("Modified", format_mtime(entry.mtime_ns)),
        ("Bound process(es)", names),
        ("Index status", status),
        ("Pinned", "yes" if pinned else "no"),
        ("Last used", last_used or "never"),
        ("Running now", running),
        ("Content sha256 (last scan)", entry.sha256[:12] + "..."),
        ("Load gate (live re-check)", gate_line(gate)),
    ]
    # MT-24 (0.32): the entry-analysis block (the persisted
    # background plan-analysis entry for the table's content sha,
    # or None while pending).
    from .table_analysis import details_analysis_lines
    lines.extend(details_analysis_lines(analysis))
    # MT-27 (0.35): the per-table organization metadata (note + tags,
    # keyed by the same content sha).
    from .table_notes import details_note_lines
    lines.extend(details_note_lines(notes))
    # MT-28 (0.37): the per-table remembered process choice (keyed by
    # the same content sha).
    from .table_attach import details_attach_lines
    lines.extend(details_attach_lines(attach))
    # MT-29 (0.39): the per-table auto-load policy (keyed by the same
    # content sha; None = the documented default "automatic").
    from .table_autoload import details_autoload_lines
    lines.extend(details_autoload_lines(autoload))
    return lines
