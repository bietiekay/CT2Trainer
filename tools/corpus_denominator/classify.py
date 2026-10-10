#!/usr/bin/env python3
"""Static classification of CT tables/records for the AP-10 denominator.

Read-only, stdlib only. Mirrors the product's static CT model without
executing anything. Every assumption is marked; unknown stays unknown.
"""
import re
from collections import Counter
try:
    from .lib import (
        SIMPLE_VALUE_TYPES, ADVANCED_VALUE_TYPES, HEX_INTEGER_TYPES,
    )
    from .scan import scan_aa
except ImportError:
    from lib import (
        SIMPLE_VALUE_TYPES, ADVANCED_VALUE_TYPES, HEX_INTEGER_TYPES,
    )
    from scan import scan_aa

MODULE_RE = re.compile(r'"?([A-Za-z0-9_\-\.]+?\.(?:exe|dll))"?', re.I)
HEX_RE = re.compile(r"[0-9A-Fa-f]+")
SYMBOL_RE = re.compile(r'@?[A-Za-z_$][A-Za-z0-9_.$]*')
NULL_VALUES = {"", "0", "00", "0x0", "00000000", "0000000000000000",
               "00000000 00000000"}
RELATIVE_RE = re.compile(r"\+?[0-9A-Fa-f]+(?:\s*\*\s*[0-9A-Fa-f]+)?")
PLAIN_MODULE_RE = re.compile(
    r'"?[A-Za-z0-9_\-\.]+?\.(?:exe|dll)"?(?:\s*\+\s*[0-9A-Fa-f]+)?'
    r'(?:\s*\[[^\]]*\])?')


def _strip_label(raw):
    label = (raw or "").strip()
    if len(label) >= 2 and label[0] == label[-1] == '"':
        label = label[1:-1]
    return label


def _int_or_none(raw):
    try:
        return int((raw or "").strip())
    except (TypeError, ValueError):
        return None


def _offsets(entry):
    node = entry.find("Offsets")
    if node is None:
        return ()
    if (node.text or "").strip():
        return tuple(t.strip() for t in node.text.split(";"))
    return tuple((o.text or "").strip() for o in node.findall("Offset"))


def _all_zero_offsets(offsets):
    return all(o.lower() in ("0", "00", "0x0") for o in offsets)


def _options(entry):
    node = entry.find("Options")
    return tuple(k for k, v in node.attrib.items() if v == "1") \
        if node is not None else ()


def classify_address(raw, user_defined_symbols):
    """Return (kind, modules, symbols, note) for a value-record address."""
    a = (raw or "").strip()
    modules = [m.lower() for m in MODULE_RE.findall(a)]
    if a in NULL_VALUES:
        return "null", modules, [], "no base"
    core = a.strip('"')
    if HEX_RE.fullmatch(core) and len(core) > 0 and \
            re.fullmatch(r"[0-9A-Fa-f]+", core):
        return "fixed", modules, [], "fixed address, build-bound"
    if core.lower().startswith("$process"):
        return "process", modules, [], "process base"
    if re.search(r"\.(?:dll|exe)!", core, re.I):
        return "managed", modules, [core], "managed method reference"
    if RELATIVE_RE.fullmatch(core):
        return "relative", modules, [], "relative to parent base"
    if PLAIN_MODULE_RE.fullmatch(core):
        return "module", modules, [], "module bound"
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", core):
        kind = "symbol_ud" if core in user_defined_symbols else "symbol"
        return kind, modules, [core], "table symbol" if kind == "symbol_ud" \
            else "cross-record symbol"
    # strip hex offset fragments (+10D8, +4C8*4) before symbol extraction so
    # offset digits are not mistaken for cross-record symbols
    core_no_offsets = re.sub(r"\+\s*[0-9A-Fa-f]+(?:\s*\*\s*[0-9A-Fa-f]+)?", " ", core)
    symbols = [s for s in SYMBOL_RE.findall(core_no_offsets)
               if not re.search(r"\.(exe|dll)$", s, re.I)
               and not s.lower().startswith("$process")]
    if "[" in core or "(" in core or "*" in core or "+" in core:
        return "expression", modules, symbols, "pointer expression"
    return "unresolved", modules, symbols, "unrecognized address form"


def classify_record(entry, user_defined_symbols):
    """Classify one non-group CheatEntry. Returns a dict."""
    entry_id = _int_or_none(entry.findtext("ID"))
    name = _strip_label(entry.findtext("Description")) or f"Entry {entry_id}"
    vt = (entry.findtext("VariableType") or "").strip()
    options = _options(entry)
    offsets = _offsets(entry)
    script_el = entry.find("AssemblerScript")
    script = (script_el.text or "") if script_el is not None else ""
    async_attr = script_el is not None and script_el.attrib.get("Async") == "1"
    async_opt = "moAsyncRecord" in options
    lua_el = entry.find("LuaScript")
    lua = (lua_el.text or "").strip() if lua_el is not None else ""
    custom = (entry.findtext("CustomType") or "").strip()
    address = (entry.findtext("Address") or "").strip()
    dropdown_link = (entry.findtext("DropDownListLink") or "").strip()
    dropdown = entry.find("DropDownList")
    hotkeys = len(entry.findall("./Hotkeys/Hotkey"))

    record = {
        "id": entry_id,
        "name": name,
        "variable_type": vt or None,
        "options": list(options),
        "offsets": list(offsets),
        "has_hotkeys": hotkeys > 0,
        "dropdown": bool(dropdown or dropdown_link),
    }

    # --- type determination -------------------------------------------------
    if vt == "Auto Assembler Script" or (not vt and script):
        kind = "aa_script"
    elif vt in SIMPLE_VALUE_TYPES or vt in ADVANCED_VALUE_TYPES:
        kind = "value"
    elif vt == "String" or vt.startswith("String"):
        kind = "string"
    elif vt == "Custom" or custom:
        kind = "custom"
    elif lua:
        kind = "script_lua"
    else:
        kind = "unknown"

    record["type"] = kind
    gaps = []
    providers = []
    status = "unknown"
    category = "unknown"

    if kind == "aa_script":
        scan = scan_aa(script)
        record["async"] = async_attr or async_opt
        if scan["unknown"]:
            record["aa_unknown_tokens"] = sorted(scan["unknown"])
        if scan["method_labels"]:
            record["aa_method_labels"] = scan["method_labels"]
        providers.append("aa_grammar")
        for d, n in sorted(scan["directives"].items()):
            prov = {
                "aobscan": "aob_scan_process", "aobscanmodule": "aob_scan_module",
                "aobscanchunk": "aob_scan_region", "aobscanregion": "aob_scan_region",
                "alloc": "cave_alloc", "globalalloc": "aa_globalalloc",
                "readmem": "aa_readmem", "reassemble": "aa_reassemble",
                "registersymbol": "aa_symbol_registration",
                "unregistersymbol": "aa_symbol_registration",
            }.get(d)
            if prov and prov not in providers:
                providers.append(prov)
        if scan["had_lua"]:
            gaps.append("lua_host_profile")
        for g in sorted(scan["lua_gaps"]):
            if g not in gaps:
                gaps.append(g)
        for g in sorted(scan["locked"]):
            if g not in gaps:
                gaps.append(g)
        if scan["has_conditional"]:
            gaps.append("aa_conditional_block")
        if scan["method_labels"] and any(
                scan["directives"].get(d, 0) for d in ("db", "dw", "dd", "dq")):
            gaps.append("managed_method_resolution")
        if scan["unknown"]:
            gaps.append("aa_directive_unverified")
        if not scan["has_enable"] or not scan["has_disable"]:
            gaps.append("aa_sections_incomplete")
            record["semantics"] = "AA script without complete ENABLE/DISABLE sections"
        elif scan["empty_disable"]:
            category = "one_shot"
            gaps.append("one_shot_save_contract")
            record["semantics"] = "One-shot action: empty/missing DISABLE section, no OFF contract"
        else:
            category = "persistent_script"
            n_aob = sum(scan["directives"].get(d, 0) for d in
                        ("aobscan", "aobscanmodule", "aobscanchunk", "aobscanregion"))
            parts = [f"AA patch with {n_aob} AOB scan(s)"] if n_aob else \
                    ["AA patch (static address/label)"]
            if scan["modules"]:
                parts.append("target " + ",".join(sorted(set(m for m in scan["modules"]))))
            if scan["had_lua"]:
                parts.append("with embedded Lua")
            if scan["method_labels"]:
                parts.append("injection at managed method label(s)")
            if async_attr or async_opt:
                parts.append("async")
            record["semantics"] = "; ".join(parts) + " (syntax assumption)"
        if async_attr or async_opt:
            gaps.append("async_lifecycle")
        if lua:
            gaps.append("lua_record_body")
            record["type"] = "aa_script+lua"
        if "aa_sections_incomplete" in gaps or "aa_directive_unverified" in gaps:
            status = "unknown"
        elif gaps:
            status = "locked"
        else:
            status = "statically_assumed"
        record["lifetime"] = "one_shot_without_off_contract" if category == "one_shot" \
            else "held_until_disable_or_target_exit"
    elif kind == "value":
        kind_addr, modules, symbols, note = classify_address(
            address, user_defined_symbols)
        record["address_kind"] = kind_addr
        record["address_note"] = note
        if kind_addr == "null":
            category = "navigation"
            record["semantics"] = "Null-array placeholder without its own effect"
            record["lifetime"] = "none_navigation_placeholder"
        else:
            providers.append("typed_value_readwrite")
            if offsets and not _all_zero_offsets(offsets):
                providers.append("pointer_chain")
            if kind_addr == "fixed":
                providers.append("direct_address")
                status = "statically_assumed"
            elif kind_addr in ("process", "module", "relative", "expression"):
                if kind_addr == "process":
                    providers.append("process_base")
                elif kind_addr == "module":
                    providers.append("module_binding")
                elif kind_addr == "expression":
                    providers.append("pointer_expression")
                if symbols:
                    gaps.append("cross_record_symbol")
                status = "locked" if gaps else "statically_assumed"
            elif kind_addr == "managed":
                gaps.append("managed_method_resolution")
                status = "locked"
            elif kind_addr == "symbol_ud":
                providers.append("user_defined_symbol")
                status = "statically_assumed"
            elif kind_addr == "symbol":
                gaps.append("cross_record_symbol")
                status = "locked"
            elif kind_addr == "empty":
                gaps.append("value_address_empty")
                status = "unknown"
            else:
                gaps.append("address_form_unrecognized")
                status = "unknown"
            category = "value_freeze"
            record["lifetime"] = "read_write_freezable_value"
            shape = f"{vt} value"
            if modules:
                shape += " in " + modules[0]
            if offsets and not _all_zero_offsets(offsets):
                shape += f" with {len(offsets)} pointer offsets"
            if note:
                shape += f" ({note})"
            if kind_addr == "expression" and symbols:
                shape += "; requires symbols " + ",".join(sorted(set(symbols)))[:60]
            record["semantics"] = shape
        if vt in ADVANCED_VALUE_TYPES:
            providers.append("array_value")
        if dropdown_link:
            gaps.append("dropdown_link")
        if "moRecursiveSetValue" in options:
            gaps.append("recursive_parent_value")
        if "moActivateChildrenAsWell" in options or "moBindActivation" in options:
            gaps.append("parent_activation")
        if status == "statically_assumed" and gaps:
            status = "locked"
    elif kind == "string":
        length = _int_or_none(entry.findtext("Length"))
        unicode_flag = (entry.findtext("Unicode") or "0").strip() == "1"
        codepage = _int_or_none(entry.findtext("CodePage")) or 0
        record["string"] = {"length": length, "unicode": unicode_flag,
                            "codepage": codepage}
        kind_addr, modules, symbols, note = classify_address(
            address, user_defined_symbols)
        record["address_kind"] = kind_addr
        if kind_addr == "null":
            category = "navigation"
            record["semantics"] = "String placeholder without base address"
            record["lifetime"] = "none_navigation_placeholder"
        else:
            providers.append("string_codec_bounded")
            enc = "UTF-16LE" if unicode_flag else "ASCII"
            record["semantics"] = (f"String ({enc}, length {length if length is not None else '?'})"
                                   + (f" an {modules[0]}" if modules else "")
                                   + (f" ({note})" if note else ""))
            if codepage and codepage != 0:
                gaps.append("string_codepage")
            if symbols:
                gaps.append("cross_record_symbol")
            if kind_addr == "managed":
                gaps.append("managed_method_resolution")
                status = "locked"
            elif kind_addr == "symbol":
                gaps.append("cross_record_symbol")
                status = "locked"
            elif kind_addr == "empty" or kind_addr == "unresolved":
                status = "unknown"
                gaps.append("value_address_empty" if kind_addr == "empty"
                            else "address_form_unrecognized")
            else:
                status = "statically_assumed"
            category = "string_write"
            record["lifetime"] = "terminator_bounded_write_freezable"
        if status not in ("locked", "unknown"):
            status = "locked" if gaps else "statically_assumed"
    elif kind == "custom":
        category = "custom_value"
        providers.append("custom_type_codec")
        gaps.append("custom_type")
        status = "locked"
        record["semantics"] = f"Custom type value ({custom or 'Custom'})"
        record["lifetime"] = "custom_type_readwrite"
    elif kind == "script_lua":
        category = "script_lua"
        providers.append("lua53_host")
        providers.append("ce_lua_api_subset")
        gaps.append("lua_record")
        status = "locked"
        record["semantics"] = "Lua record (no AA); host API coverage undetermined"
        record["lifetime"] = "script_enable_disable"
    else:
        if address:
            category = "configuration"
            record["semantics"] = f"Record without VariableType, address {address[:40]}"
        else:
            record["semantics"] = "Unclassifiable (no type, no script, no address)"
        status = "unknown"
        record["lifetime"] = "unknown"
        gaps.append("record_unclassifiable")

    # --- lua body on any record ---------------------------------------------
    if lua and kind != "script_lua" and kind != "aa_script":
        gaps.append("lua_record_body")
    record["status"] = status
    record["category"] = category
    record["gaps"] = sorted(set(gaps))
    record["providers"] = providers
    return record
