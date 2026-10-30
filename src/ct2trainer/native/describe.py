"""Pure helpers for describing what each plan entry does.

Extracted from the trainer UI so the same "what does this record do"
information is available in the CLI (``ct2trainer native describe``),
the converter inspector, and any other consumer without pulling in Tk.
"""
from __future__ import annotations

from .ui_script_view import row_details


def describe_entries(plan: dict, include_ids: set[int] | None = None) -> list[dict]:
    """Return row-details dicts for entries of a compiled plan.

    Parameters
    ----------
    plan:
        A validated plan dict as produced by ``compile_table``.
    include_ids:
        Optional set of entry IDs to include.  When ``None`` every
        entry in the plan is described.

    Returns a list of dicts with keys ``id``, ``title``, ``script``,
    ``assessment`` and ``actions`` (same shape as the trainer UI's
    row-details window content).
    """
    entries: dict[int, dict] = {e["id"]: e for e in plan["entries"]}
    if include_ids is not None:
        unknown = include_ids - set(entries)
        if unknown:
            raise ValueError(
                f"Unknown entry id(s): {sorted(unknown)}")
        ids = sorted(include_ids)
    else:
        ids = sorted(entries)
    results = []
    for eid in ids:
        entry = entries[eid]
        details = row_details(entry, entries)
        results.append({"id": eid, "label": entry.get("label", ""),
                        **details})
    return results


def render_describe(results: list[dict]) -> str:
    """Render :func:`describe_entries` output as plain, human-readable text.

    Each record becomes a labelled section with its id, the raw script
    source (when the entry carries an executable one), the plain-language
    assessment, and the concrete actions the trainer performs.  This is the
    same content the trainer's row-details window shows, so a user can
    inspect "what a record does" from the command line without launching
    the GUI.
    """
    if not results:
        return "(no entries)"
    lines: list[str] = []
    for r in results:
        # Prefer the plain record label for the CLI header; the window-
        # style ``title`` (``Row details – … (id N)``) is the GUI text.
        label = r.get("label") or r.get("title", "")
        lines.append(f"=== [{r['id']}] {label} ===")
        script = r.get("script")
        if script:
            lines.append("  Script:")
            if script.get("title"):
                lines.append(f"    {script['title']}")
            for ln in script.get("body", "").splitlines():
                lines.append(f"    {ln}")
        else:
            lines.append("  Script: (none)")
        assessment = r.get("assessment", "")
        if assessment:
            lines.append("  Assessment:")
            for ln in assessment.splitlines():
                lines.append(f"    {ln}")
        else:
            lines.append("  Assessment: (none)")
        actions = r.get("actions", "")
        if actions:
            lines.append("  Actions:")
            for ln in actions.splitlines():
                lines.append(f"    {ln}")
        else:
            lines.append("  Actions: (none)")
        lines.append("")
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)
