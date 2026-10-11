"""Explain which CT features the first trainer UI can represent.

This is a static review report, not a claim that Cheat Engine can execute a
record or that a write has the intended effect in a running game.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from .table import (ADVANCED_VALUE_TYPES, SIMPLE_VALUE_TYPES,
                    LOCAL_CE_TABLE_VERSION, Entry,
                    Table, numeric_literal_safe, prototype_toggle_available,
                    prototype_value_editable)


KNOWN_VALUE_TYPES = SIMPLE_VALUE_TYPES | ADVANCED_VALUE_TYPES


def _ui_class(entry: Entry) -> str:
    if entry.kind == "heading":
        return "heading"
    if entry.kind == "group":
        return "toggle_group" if prototype_toggle_available(entry) else "review_group"
    if entry.kind == "script":
        if not prototype_toggle_available(entry) and entry.has_checkbox:
            return "review_script"
        return "toggle" if entry.has_checkbox else "advanced"
    if entry.kind != "value":
        return "unsupported"
    if entry.variable_type in ADVANCED_VALUE_TYPES:
        return "advanced_value"
    if entry.dropdown_link:
        return "linked_choice"
    if entry.dropdown_choices:
        return "choice"
    return "value"


def assess(table: Table) -> dict:
    """Return deterministic, machine-readable UI capability and review data."""
    by_label: dict[str, list[Entry]] = defaultdict(list)
    for entry in table.entries:
        by_label[entry.label.casefold()].append(entry)

    rows: list[dict] = []
    risk_counts: Counter[str] = Counter()
    ui_counts: Counter[str] = Counter()
    for entry in table.entries:
        ui_class = _ui_class(entry)
        ui_counts[ui_class] += 1
        risks: list[str] = []
        unavailable: list[str] = []
        source_id: int | None = None

        if entry.kind == "unsupported":
            risks.append("record-kind-unclassified")
            unavailable.append("generic-control")
        if not entry.has_checkbox and entry.kind in ("script", "value"):
            unavailable.append("direct-toggle-hidden-in-ce")
        if entry.is_group_header and entry.kind == "heading" and entry.has_checkbox:
            risks.append("group-checkbox-no-builtin-on-effect")
            unavailable.append("group-toggle-requires-runtime-review")
        if (entry.is_group_header and not prototype_toggle_available(entry)
                and ("moDeactivateChildrenAsWell" in entry.options
                     or "moBindActivation" in entry.options)):
            unavailable.append("group-deactivate-children-action")
        if (not entry.activation_safe and
                any(option in entry.options for option in
                    ("moActivateChildrenAsWell", "moBindActivation"))):
            risks.append("parent-activation-reaches-blocked-child")
            unavailable.append("parent-toggle")
        if (not entry.activation_safe and
                any(option in entry.options for option in
                    ("moDeactivateChildrenAsWell", "moBindActivation"))):
            risks.append("parent-deactivation-reaches-blocked-child")
            if "parent-toggle" not in unavailable:
                unavailable.append("parent-toggle")
        if entry.has_children and any(option in entry.options for option in
                                      ("moActivateChildrenAsWell", "moDeactivateChildrenAsWell",
                                       "moBindActivation")):
            risks.append("parent-propagation-confirmation-unverified")
            if "parent-toggle" not in unavailable:
                unavailable.append("parent-toggle")
        if entry.kind == "script":
            risks.append("assembler-runtime-unverified")
            if not entry.has_enable_section or not entry.has_disable_section:
                risks.append("assembler-toggle-sections-incomplete")
                unavailable.append("script-toggle-needs-enable-disable")
            if entry.has_assembler_lua:
                risks.append("assembler-contains-lua")
            if entry.async_script:
                risks.append("async-activation")
                risks.append("async-completion-api-not-available")
                unavailable.append("async-script-toggle")
            if entry.script_external_action:
                risks.append("script-dialog-or-external-action")
                unavailable.append("script-toggle-until-reviewed")
            if entry.registers_symbols:
                risks.append("script-registers-symbols")
            if entry.activation_set_lua:
                risks.append("embedded-record-activation-set")
        if entry.kind == "group" and entry.options:
            risks.append("group-option-semantics-unverified")
        if entry.kind == "value":
            risks.append("value-write-unverified")
            if not entry.address or not entry.address.strip():
                risks.append("value-has-no-own-address")
                unavailable.append("addressless-value-editor")
                unavailable.append("addressless-value-freeze")
            if entry.variable_type not in KNOWN_VALUE_TYPES:
                risks.append("value-type-unknown")
                unavailable.append("unknown-value-editor")
            if entry.variable_type in ADVANCED_VALUE_TYPES:
                risks.append("advanced-value-editor-unverified")
                unavailable.append("advanced-value-editor")
            if entry.variable_type == "Custom":
                if entry.custom_type_known:
                    risks.append("custom-type-statically-defined")
                else:
                    risks.append("custom-type-definition-runtime-required")
            if entry.has_children and "moRecursiveSetValue" in entry.options:
                risks.append("recursive-value-write-unverified")
                unavailable.append("recursive-value-editor")
                unavailable.append("recursive-value-freeze")
            if entry.dropdown_read_only and not any(
                    value != "*" for value, _ in entry.dropdown_choices):
                risks.append("readonly-dropdown-has-no-valid-choice")
                unavailable.append("readonly-dropdown-value")
            if entry.variable_type in SIMPLE_VALUE_TYPES and any(
                    value != "*" and not numeric_literal_safe(
                    value, entry.variable_type, entry.show_as_hex, entry.show_as_signed)
                   for value, _ in entry.dropdown_choices):
                risks.append("dropdown-has-nonliteral-value")
                unavailable.append("dropdown-value-until-reviewed")
            if entry.show_as_hex:
                risks.append("hex-input-semantics-require-ce-test")
                if entry.show_as_signed is None:
                    risks.append("signed-display-inherits-ce-setting")
                if entry.variable_type not in {"Byte", "2 Bytes", "4 Bytes", "8 Bytes"}:
                    risks.append("hex-noninteger-editor-unverified")
                    unavailable.append("hex-noninteger-editor")
            if entry.show_as_signed:
                risks.append("signed-input-semantics-require-ce-test")
            if entry.pointer_offsets:
                risks.append("pointer-chain-runtime-unverified")
                if any(offset.strip().startswith(("+", "-")) for offset in entry.pointer_offsets):
                    risks.append("signed-pointer-offset")
        if entry.dropdown_link:
            candidates = by_label[entry.dropdown_link.casefold()]
            with_choices = [candidate for candidate in candidates if candidate.dropdown_choices]
            if len(with_choices) == 1:
                source_id = with_choices[0].id
                risks.append("dropdown-link-source-candidate-unverified")
            elif len(with_choices) > 1:
                risks.append("dropdown-link-ambiguous")
            elif len(candidates) == 1:
                source_id = candidates[0].id
                risks.append("dropdown-link-target-has-no-list")
                if entry.dropdown_link_empty:
                    risks.append("dropdown-link-free-value-fallback-requires-game-test")
                else:
                    risks.append("dropdown-link-free-value-fallback-requires-ce-test")
            elif candidates:
                risks.append("dropdown-link-ambiguous")
            else:
                risks.append("dropdown-link-no-choice-source")
            if not entry.dropdown_link_empty:
                unavailable.append("linked-dropdown-control")
        if entry.hotkey_count:
            risks.append("hotkeys-present")
            unavailable.append("hotkey-control")
        if entry.kind == "heading" and entry.has_children:
            unavailable.append("collapsible-group-navigation")

        # Preserve a stable code order within each entry. Counts are sorted for
        # deterministic JSON regardless of traversal details in a new parser.
        for risk in risks:
            risk_counts[risk] += 1
        rows.append({
            "id": entry.id,
            "ui_class": ui_class,
            "prototype_action_available": (prototype_toggle_available(entry)
                                           or prototype_value_editable(entry)),
            "runtime_verified": False,
            "review_reasons": risks,
            "unavailable_actions": unavailable,
            "dropdown_source_candidate_id": source_id,
        })

    table_risks: list[str] = []
    if table.has_table_lua:
        table_risks.append("table-lua-executes-in-ce")
    if table.has_forms:
        table_risks.append("embedded-forms-may-conflict")
    if table.has_custom_types:
        if table.custom_types:
            table_risks.append("custom-types-statically-defined")
        else:
            table_risks.append("custom-types-require-ce-test")
    if table.has_custom_type_records:
        if all(entry.custom_type_known for entry in table.entries
               if entry.variable_type == "Custom"):
            table_risks.append("custom-type-records-statically-defined")
        else:
            table_risks.append("custom-type-records-require-ce-test")
    if table.table_version > LOCAL_CE_TABLE_VERSION:
        table_risks.append("table-version-newer-than-local-reference")
    return {
        "schema": "ct2trainer-capabilities/v1",
        "scope": "static-ui-assessment-runtime-unverified",
        "entry_count": len(rows),
        "ui_class_counts": dict(sorted(ui_counts.items())),
        "review_reason_counts": dict(sorted(risk_counts.items())),
        "table_review_reasons": table_risks,
        "entries": rows,
    }
