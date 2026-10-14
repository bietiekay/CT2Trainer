"""Focused fixture-driven tests for the value-link models (AP-10 lane).

Drives ``src/ct2trainer/native/value_links.py`` against the synthetic
record tables of ``tests/value_links_fixture_data.py`` (no
TableReferences, no CE inputs).  Pinned scenarios:

RecursiveSetValue (moRecursiveSetValue):
    closure completeness and deterministic order (deepest first, ties by
    id, target last), byte-exact write plans for Byte/Float/byte-array
    children, SHA stability across instances and calls, tamper-sensitive
    element/plan digests, the skipped protocol (script/heading/blocked,
    unselected, unsupported; subtrees still collected), cycle refusal with
    named path (two-node and self-parent), the depth > 64 refusal and the
    depth == 64 boundary acceptance, no-profile / no-flag / inactive /
    unknown target refusals, bit-field snapshot handling, malformed table
    refusals, and the deep-copy input contract.

DropDownListLink (cross-record):
    read-only inspection (target name, choices, current index,
    non-mutation), resolve/apply roundtrip over every index, byte-exact
    apply plans written to the TARGET record through its value profile,
    index-bound refusals, the binding index-semantics decision (stored
    value is the index, not the choice literal), case-fold name identity
    including ambiguous case-fold twins, missing/self/chained link
    refusals, group-header / non-numeric / script target refusals,
    empty or unusable dropdown refusals, activatability (inspect reports,
    resolve/apply refuse), hex and float target encodings, and malformed
    table refusals.
"""

import copy
import json
import struct
import unittest
from hashlib import sha256

from ct2trainer.native.value_links import (
    MAX_RECURSIVE_DEPTH,
    SCHEMA_DROPDOWN_INSPECTION,
    SCHEMA_DROPDOWN_PLAN,
    SCHEMA_RECURSIVE_PLAN,
    DropdownIndexError,
    DropdownLinkActivatableError,
    DropdownLinkCycleError,
    DropdownLinkEmptyRefused,
    DropdownLinkError,
    DropdownLinkModel,
    DropdownLinkTableError,
    DropdownLinkTargetError,
    DropdownLinkTypeRefused,
    DropdownLinkValueParseError,
    RecursiveCycleError,
    RecursiveDepthError,
    RecursiveNoValueProfileError,
    RecursiveSetValueModel,
    RecursiveSnapshotRequiredError,
    RecursiveTableError,
    RecursiveTargetError,
    RecursiveValueParseError,
)

try:
    from value_links_fixture_data import (
        DROPDOWN_AMBIGUOUS_TABLE,
        DROPDOWN_BAD_CHOICE_TABLE,
        DROPDOWN_CHAIN_TABLE,
        DROPDOWN_EMPTY_TABLE,
        DROPDOWN_FLOAT_TARGET_TABLE,
        DROPDOWN_GROUP_TARGET_TABLE,
        DROPDOWN_HEX_FLOAT_TABLE,
        DROPDOWN_HEX_TARGET_TABLE,
        DROPDOWN_INACTIVE_TABLE,
        DROPDOWN_INDEX_SEMANTICS_TABLE,
        DROPDOWN_LINK_NOT_VALUE_TABLE,
        DROPDOWN_MISSING_TABLE,
        DROPDOWN_NO_LINK_NAME_TABLE,
        DROPDOWN_NON_NUMERIC_TABLE,
        DROPDOWN_READONLY_TABLE,
        DROPDOWN_SCRIPT_TARGET_TABLE,
        DROPDOWN_SELF_LINK_TABLE,
        DROPDOWN_VALID_TABLE,
        RECURSIVE_BITFIELD_TABLE,
        RECURSIVE_CYCLE_TABLE,
        RECURSIVE_DEEP_OK_TABLE,
        RECURSIVE_DEEP_REJECT_TABLE,
        RECURSIVE_INACTIVE_TABLE,
        RECURSIVE_MIXED_TABLE,
        RECURSIVE_NO_FLAG_TABLE,
        RECURSIVE_NO_PROFILE_TABLE,
        RECURSIVE_SELF_PARENT_TABLE,
        RECURSIVE_TORSO_TABLE,
        build_deep_chain,
        value_record,
    )
except ModuleNotFoundError:  # invoked as tests.test_native_value_links
    from tests.value_links_fixture_data import (
        DROPDOWN_AMBIGUOUS_TABLE,
        DROPDOWN_BAD_CHOICE_TABLE,
        DROPDOWN_CHAIN_TABLE,
        DROPDOWN_EMPTY_TABLE,
        DROPDOWN_FLOAT_TARGET_TABLE,
        DROPDOWN_GROUP_TARGET_TABLE,
        DROPDOWN_HEX_FLOAT_TABLE,
        DROPDOWN_HEX_TARGET_TABLE,
        DROPDOWN_INACTIVE_TABLE,
        DROPDOWN_INDEX_SEMANTICS_TABLE,
        DROPDOWN_LINK_NOT_VALUE_TABLE,
        DROPDOWN_MISSING_TABLE,
        DROPDOWN_NO_LINK_NAME_TABLE,
        DROPDOWN_NON_NUMERIC_TABLE,
        DROPDOWN_READONLY_TABLE,
        DROPDOWN_SCRIPT_TARGET_TABLE,
        DROPDOWN_SELF_LINK_TABLE,
        DROPDOWN_VALID_TABLE,
        RECURSIVE_BITFIELD_TABLE,
        RECURSIVE_CYCLE_TABLE,
        RECURSIVE_DEEP_OK_TABLE,
        RECURSIVE_DEEP_REJECT_TABLE,
        RECURSIVE_INACTIVE_TABLE,
        RECURSIVE_MIXED_TABLE,
        RECURSIVE_NO_FLAG_TABLE,
        RECURSIVE_NO_PROFILE_TABLE,
        RECURSIVE_SELF_PARENT_TABLE,
        RECURSIVE_TORSO_TABLE,
        build_deep_chain,
        value_record,
    )


def plan_elements(plan):
    return [(element["record_id"], element["bytes_hex"]) for element in plan["writes"]]


class RecursiveModelTests(unittest.TestCase):
    # -- closure and order -------------------------------------------------

    def test_closure_order_deepest_first_then_id(self):
        model = RecursiveSetValueModel(RECURSIVE_MIXED_TABLE)
        plan = model.plan_writes(100, "1")
        # Depth 2 first (105, 108 by id), then depth 1 (101, 102), target last.
        self.assertEqual(
            [entry["record_id"] for entry in plan["writes"]],
            [105, 108, 101, 102, 100],
        )
        depths = [entry["depth"] for entry in plan["writes"]]
        self.assertEqual(depths, [2, 2, 1, 1, 0])
        self.assertEqual(plan["writes"][-1]["record_id"], 100)

    def test_closure_is_complete_for_mixed_child_types(self):
        model = RecursiveSetValueModel(RECURSIVE_MIXED_TABLE)
        plan = model.plan_writes(100, "1")
        written = {entry["record_id"] for entry in plan["writes"]}
        self.assertEqual(written, {100, 101, 102, 105, 108})
        # 105 lives under heading 104: headings are skipped but do not prune.
        skipped_ids = {entry["record_id"] for entry in plan["skipped"]}
        self.assertEqual(skipped_ids, {103, 104, 106, 107, 110})

    # -- byte-exact plans ---------------------------------------------------

    def test_byte_exact_plans_byte_and_float(self):
        model = RecursiveSetValueModel(RECURSIVE_MIXED_TABLE)
        plan = model.plan_writes(100, "1")
        elements = {entry["record_id"]: entry for entry in plan["writes"]}
        self.assertEqual(elements[100]["bytes_hex"], struct.pack("<f", 1.0).hex().upper())
        self.assertEqual(elements[101]["bytes_hex"], struct.pack("<f", 1.0).hex().upper())
        self.assertEqual(elements[102]["bytes_hex"], "01")
        self.assertEqual(elements[102]["size"], 1)
        self.assertEqual(elements[102]["variable_type"], "Byte")
        self.assertEqual(elements[100]["variable_type"], "Float")

    def test_byte_array_profile_target_and_children_bytes(self):
        model = RecursiveSetValueModel(RECURSIVE_TORSO_TABLE)
        plan = model.plan_writes(200, "01 00")
        elements = {entry["record_id"]: entry for entry in plan["writes"]}
        for record_id in (200, 201, 202):
            self.assertEqual(elements[record_id]["bytes_hex"], "0100")
            self.assertEqual(elements[record_id]["size"], 2)
            self.assertEqual(elements[record_id]["variable_type"], "Array of byte")

    def test_signed_type_uses_twos_complement(self):
        table = {
            3000: value_record("signed root", variable_type="2 Bytes",
                               show_as_signed=True, address="sroot",
                               recursive=True),
            3001: value_record("signed kid", parent_id=3000, variable_type="2 Bytes",
                               show_as_signed=True, address="skid"),
        }
        plan = RecursiveSetValueModel(table).plan_writes(3000, "-2")
        expected = struct.pack("<h", -2).hex().upper()
        self.assertEqual(plan_elements(plan), [(3001, expected), (3000, expected)])

    # -- SHA stability -------------------------------------------------------

    def test_plan_sha_stable_across_instances_and_calls(self):
        first = RecursiveSetValueModel(RECURSIVE_MIXED_TABLE).plan_writes(100, "1")
        again = RecursiveSetValueModel(RECURSIVE_MIXED_TABLE).plan_writes(100, "1")
        self.assertEqual(first, again)
        self.assertEqual(first["plan_sha256"], again["plan_sha256"])
        same_model = RecursiveSetValueModel(RECURSIVE_MIXED_TABLE)
        self.assertEqual(same_model.plan_writes(100, "1")["plan_sha256"],
                         first["plan_sha256"])

    def test_plan_sha_changes_with_value_text(self):
        model = RecursiveSetValueModel(RECURSIVE_MIXED_TABLE)
        a = model.plan_writes(100, "1")
        b = model.plan_writes(100, "2")
        self.assertNotEqual(a["plan_sha256"], b["plan_sha256"])
        self.assertNotEqual(plan_elements(a), plan_elements(b))

    def test_plan_element_sha_tamper_detection(self):
        model = RecursiveSetValueModel(RECURSIVE_MIXED_TABLE)
        plan = model.plan_writes(100, "1")
        for element in plan["writes"]:
            payload = {key: value for key, value in element.items() if key != "sha256"}
            digest = sha256(json.dumps(payload, sort_keys=True,
                                      separators=(",", ":")).encode("utf-8")).hexdigest()
            self.assertEqual(digest, element["sha256"])
            payload["bytes_hex"] = "FF"
            forged = sha256(json.dumps(payload, sort_keys=True,
                                      separators=(",", ":")).encode("utf-8")).hexdigest()
            self.assertNotEqual(forged, element["sha256"])

    def test_plan_counts_and_schema(self):
        plan = RecursiveSetValueModel(RECURSIVE_MIXED_TABLE).plan_writes(100, "1")
        self.assertEqual(plan["schema"], SCHEMA_RECURSIVE_PLAN)
        self.assertEqual(plan["target_id"], 100)
        self.assertEqual(plan["value_text"], "1")
        self.assertEqual(plan["write_count"], 5)
        self.assertEqual(plan["skipped_count"], 5)
        self.assertEqual(len(plan["writes"]), 5)
        self.assertEqual(len(plan["skipped"]), 5)

    # -- skipped protocol -----------------------------------------------------

    def test_skipped_non_value_children_logged_with_reason(self):
        plan = RecursiveSetValueModel(RECURSIVE_MIXED_TABLE).plan_writes(100, "1")
        skipped = {entry["record_id"]: entry for entry in plan["skipped"]}
        self.assertEqual(skipped[103]["kind"], "script")
        self.assertIn("kind=script", skipped[103]["reason"])
        self.assertEqual(skipped[104]["kind"], "heading")
        self.assertIn("kind=heading", skipped[104]["reason"])
        self.assertEqual(skipped[110]["kind"], "blocked")
        self.assertIn("kind=blocked", skipped[110]["reason"])
        self.assertEqual(skipped[103]["label"], "script kid")
        self.assertEqual(skipped[104]["depth"], 1)
        written = {entry["record_id"] for entry in plan["writes"]}
        for record_id in (103, 104, 110):
            self.assertNotIn(record_id, written)

    def test_skipped_unselected_and_unsupported_never_written(self):
        plan = RecursiveSetValueModel(RECURSIVE_MIXED_TABLE).plan_writes(100, "1")
        skipped = {entry["record_id"]: entry for entry in plan["skipped"]}
        self.assertIn("unsupported", skipped[106]["reason"])
        self.assertIn("unselected", skipped[107]["reason"])
        written = {entry["record_id"] for entry in plan["writes"]}
        self.assertNotIn(106, written)
        self.assertNotIn(107, written)

    def test_unselected_intermediate_still_collects_descendants(self):
        plan = RecursiveSetValueModel(RECURSIVE_MIXED_TABLE).plan_writes(100, "1")
        written = {entry["record_id"] for entry in plan["writes"]}
        # 108 is the value child of unselected 107 and is still written.
        self.assertIn(108, written)
        element = next(entry for entry in plan["writes"] if entry["record_id"] == 108)
        self.assertEqual(element["depth"], 2)
        self.assertEqual(element["bytes_hex"], "01")

    # -- refusals -------------------------------------------------------------

    def test_cycle_rejected_with_named_path(self):
        model = RecursiveSetValueModel(RECURSIVE_CYCLE_TABLE)
        with self.assertRaises(RecursiveCycleError) as caught:
            model.plan_writes(300, "1")
        self.assertEqual(caught.exception.path, (300, 301, 300))
        self.assertIn("alpha", str(caught.exception))
        self.assertIn("beta", str(caught.exception))

    def test_self_parent_cycle_rejected(self):
        model = RecursiveSetValueModel(RECURSIVE_SELF_PARENT_TABLE)
        with self.assertRaises(RecursiveCycleError) as caught:
            model.plan_writes(400, "1")
        self.assertEqual(caught.exception.path, (400, 400))

    def test_depth_over_64_rejected(self):
        model = RecursiveSetValueModel(RECURSIVE_DEEP_REJECT_TABLE)
        with self.assertRaises(RecursiveDepthError) as caught:
            model.plan_writes(500, "1")
        self.assertEqual(caught.exception.__class__.__name__, "RecursiveDepthError")
        self.assertIn("chain65", str(caught.exception))

    def test_depth_exactly_64_accepted(self):
        model = RecursiveSetValueModel(RECURSIVE_DEEP_OK_TABLE)
        plan = model.plan_writes(600, "1")
        self.assertEqual(plan["write_count"], MAX_RECURSIVE_DEPTH + 1)
        self.assertEqual(plan["skipped_count"], 0)
        deepest = max(entry["depth"] for entry in plan["writes"])
        self.assertEqual(deepest, MAX_RECURSIVE_DEPTH)
        deepest_entries = [entry for entry in plan["writes"]
                           if entry["depth"] == MAX_RECURSIVE_DEPTH]
        self.assertEqual(deepest_entries[0]["record_id"], 664)

    def test_target_without_value_profile_rejected(self):
        model = RecursiveSetValueModel(RECURSIVE_NO_PROFILE_TABLE)
        for target_id, label in ((700, "no type"), (701, "custom")):
            with self.subTest(target_id=target_id), \
                    self.assertRaises(RecursiveNoValueProfileError) as caught:
                model.plan_writes(target_id, "1")
            self.assertIn(str(target_id), str(caught.exception))
            self.assertIn(label, str(caught.exception))

    def test_target_without_recursive_flag_rejected(self):
        model = RecursiveSetValueModel(RECURSIVE_NO_FLAG_TABLE)
        with self.assertRaises(RecursiveTargetError) as caught:
            model.plan_writes(800, "1")
        self.assertIn("moRecursiveSetValue", str(caught.exception))
        self.assertIn("plain", str(caught.exception))

    def test_target_not_selected_or_unsupported_rejected(self):
        model = RecursiveSetValueModel(RECURSIVE_INACTIVE_TABLE)
        with self.assertRaises(RecursiveTargetError) as caught:
            model.plan_writes(900, "1")
        self.assertIn("not selected", str(caught.exception))
        with self.assertRaises(RecursiveTargetError) as caught:
            model.plan_writes(901, "1")
        self.assertIn("unsupported", str(caught.exception))

    def test_target_unknown_or_not_a_value_rejected(self):
        model = RecursiveSetValueModel(RECURSIVE_MIXED_TABLE)
        with self.assertRaises(RecursiveTargetError):
            model.plan_writes(9999, "1")
        with self.assertRaises(RecursiveTargetError) as caught:
            model.plan_writes(104, "1")  # heading
        self.assertIn("not a value record", str(caught.exception))
        with self.assertRaises(RecursiveTargetError):
            model.plan_writes("100", "1")  # non-int id

    def test_value_parse_error_names_record(self):
        model = RecursiveSetValueModel(RECURSIVE_MIXED_TABLE)
        # Elements are built deepest first, so the first invalid literal is
        # reported on the deepest record that cannot parse it.
        with self.assertRaises(RecursiveValueParseError) as caught:
            model.plan_writes(100, "abc")
        self.assertIn("105", str(caught.exception))
        self.assertIn("deep float", str(caught.exception))
        with self.assertRaises(RecursiveValueParseError):
            model.plan_writes(100, "256")  # out of Byte range for 108
        with self.assertRaises(RecursiveValueParseError) as caught:
            model.plan_writes(100, None)
        self.assertIn("must be text", str(caught.exception))

    def test_hex_float_recursive_write_is_a_raw_bit_pattern(self):
        # WP-33: a ShowAsHex Float target is a raw IEEE-754 bit-pattern
        # record; the exact-width hex literal is encoded little-endian.
        table = {
            3100: value_record("hex float", variable_type="Float",
                               show_as_hex=True, address="hf", recursive=True),
        }
        plan = RecursiveSetValueModel(table).plan_writes(3100, "3F800000")
        self.assertEqual(plan_elements(plan), [(3100, "0000803F")])
        # The 0x prefix is accepted and encodes identically.
        again = RecursiveSetValueModel(table).plan_writes(3100, "0x3F800000")
        self.assertEqual(plan_elements(again), [(3100, "0000803F")])
        # Wrong-width and decimal literals refuse with the record named.
        for literal in ("3F8000", "3F8000000", "1.0"):
            with self.subTest(literal=literal), \
                    self.assertRaises(RecursiveValueParseError) as caught:
                RecursiveSetValueModel(table).plan_writes(3100, literal)
            self.assertIn("3100", str(caught.exception))
            self.assertIn("hexadecimal digits", str(caught.exception))

    def test_bitfield_requires_snapshot(self):
        model = RecursiveSetValueModel(RECURSIVE_BITFIELD_TABLE)
        with self.assertRaises(RecursiveSnapshotRequiredError) as caught:
            model.plan_writes(1000, "5")
        self.assertIn("flags", str(caught.exception))
        self.assertIn("snapshot", str(caught.exception).lower())

    def test_bitfield_snapshot_preserves_unowned_bits(self):
        model = RecursiveSetValueModel(RECURSIVE_BITFIELD_TABLE)
        plan = model.plan_writes(1001, "5")
        element = plan["writes"][0]
        self.assertEqual(element["bytes_hex"], "05")
        # bits 4..7 of the snapshot (0x0F) are unowned and must survive.
        self.assertEqual(int(element["bytes_hex"], 16) & 0xF0, 0)

    def test_table_normalization_rejections(self):
        bad_tables = {
            "not a mapping": "torso",
            "empty": {},
            "negative id": {-5: value_record("a")},
            "string id": {"5": value_record("a")},
            "unknown kind": {1: value_record("a", kind="alien")},
            "bad selected": {1: value_record("a", selected="yes")},
            "bad supported": {1: value_record("a", supported="yes")},
            "unknown parent": {1: value_record("a", parent_id=99)},
            "bad recursive": {1: value_record("a", recursive="yes")},
        }
        for name, table in bad_tables.items():
            with self.subTest(name=name), self.assertRaises(RecursiveTableError):
                RecursiveSetValueModel(table)

    def test_profile_metadata_mismatch_rejected(self):
        from ct2trainer.native.value_types import prepare_value_profile
        profile = prepare_value_profile("Array of byte",
                                        {"ByteLength": 3, "ShowAsHex": True})
        flag_mismatch = value_record("flag mismatch", variable_type="Array of byte",
                                     show_as_hex=False, show_as_signed=False,
                                     address="mm", value_profile=profile)
        size_mismatch = value_record("size mismatch", variable_type="Array of byte",
                                     show_as_hex=True, show_as_signed=False,
                                     address="sm", size=2, value_profile=profile)
        for name, record in (("flag mismatch", flag_mismatch),
                             ("size mismatch", size_mismatch)):
            with self.subTest(name=name):
                table = {3200: record}
                with self.assertRaises(RecursiveTableError):
                    RecursiveSetValueModel(table)

    # -- deep-copy contract ----------------------------------------------------

    def test_input_table_not_mutated(self):
        original = copy.deepcopy(RECURSIVE_MIXED_TABLE)
        model = RecursiveSetValueModel(RECURSIVE_MIXED_TABLE)
        model.plan_writes(100, "1")
        model.plan_writes(100, "2")
        self.assertEqual(RECURSIVE_MIXED_TABLE, original)
        # The model must hold its own copy, not the caller's objects.
        self.assertIsNot(model._records[100], RECURSIVE_MIXED_TABLE[100])

    def test_input_table_not_mutated_dropdown(self):
        original = copy.deepcopy(DROPDOWN_VALID_TABLE)
        model = DropdownLinkModel(DROPDOWN_VALID_TABLE)
        model.inspect(1101, "2")
        model.apply(1101, 2)
        self.assertEqual(DROPDOWN_VALID_TABLE, original)
        self.assertIsNot(model._records[1101], DROPDOWN_VALID_TABLE[1101])


class DropdownLinkTests(unittest.TestCase):
    # -- inspection ------------------------------------------------------------

    def test_inspect_valid_link_reports_target_and_choices(self):
        model = DropdownLinkModel(DROPDOWN_VALID_TABLE)
        result = model.inspect(1101)
        self.assertEqual(result["schema"], SCHEMA_DROPDOWN_INSPECTION)
        self.assertEqual(result["link_record_id"], 1101)
        self.assertEqual(result["link_name"], "Achievement Related")
        self.assertEqual(result["target_record_id"], 1100)
        self.assertEqual(result["target_record_label"], "Achievement Related")
        self.assertEqual(result["target_variable_type"], "Byte")
        self.assertEqual(len(result["choices"]), 4)
        self.assertEqual(result["choices"][0],
                         {"index": 0, "value": "0", "description": "Kill By Bottle"})
        self.assertEqual(result["choices"][3]["description"], "Kill By Melee")
        self.assertFalse(result["read_only"])
        self.assertTrue(result["activatable"])
        self.assertEqual(result["problems"], [])
        self.assertIsNone(result["current_index"])
        self.assertIsNone(result["current_choice"])

    def test_inspect_current_value_resolves_index(self):
        model = DropdownLinkModel(DROPDOWN_VALID_TABLE)
        result = model.inspect(1101, "2")
        self.assertEqual(result["current_index"], 2)
        self.assertEqual(result["current_choice"], "Kill By Bomb")
        self.assertIsNone(result["current_error"])

    def test_inspect_current_value_out_of_range_reports_error(self):
        model = DropdownLinkModel(DROPDOWN_VALID_TABLE)
        result = model.inspect(1101, "9")
        self.assertIsNone(result["current_index"])
        self.assertIsNone(result["current_choice"])
        self.assertIn("outside the choice range 0..3", result["current_error"])

    def test_inspect_current_value_unparseable_reports_error(self):
        model = DropdownLinkModel(DROPDOWN_VALID_TABLE)
        result = model.inspect(1101, "xyz")
        self.assertIsNone(result["current_index"])
        self.assertIsNotNone(result["current_error"])
        result2 = model.inspect(1101, 5)
        self.assertIn("must be text", result2["current_error"])

    def test_inspect_is_read_only(self):
        original = copy.deepcopy(DROPDOWN_VALID_TABLE)
        model = DropdownLinkModel(DROPDOWN_VALID_TABLE)
        self.assertEqual(model.inspect(1101, "1"), model.inspect(1101, "1"))
        self.assertEqual(DROPDOWN_VALID_TABLE, original)
        target = model._records[1100]
        self.assertEqual(DROPDOWN_VALID_TABLE[1100], original[1100])
        self.assertIsNot(target, DROPDOWN_VALID_TABLE[1100])

    def test_inspect_reports_non_activatable_without_refusing(self):
        model = DropdownLinkModel(DROPDOWN_INACTIVE_TABLE)
        result = model.inspect(2101, "1")
        self.assertFalse(result["activatable"])
        self.assertEqual(len(result["problems"]), 1)
        self.assertIn("Linker Unselected", result["problems"][0])
        self.assertIn("not selected", result["problems"][0])
        self.assertEqual(result["current_index"], 1)

    def test_read_only_target_flag_surfaced(self):
        result = DropdownLinkModel(DROPDOWN_READONLY_TABLE).inspect(2601)
        self.assertTrue(result["read_only"])
        self.assertTrue(result["activatable"])

    # -- resolve / apply --------------------------------------------------------

    def test_resolve_returns_index_description_raw(self):
        model = DropdownLinkModel(DROPDOWN_VALID_TABLE)
        index, description, raw = model.resolve(1101, "3")
        self.assertEqual(index, 3)
        self.assertEqual(description, "Kill By Melee")
        self.assertEqual(raw, b"\x03")

    def test_resolve_apply_roundtrip_all_indices(self):
        model = DropdownLinkModel(DROPDOWN_VALID_TABLE)
        for index in range(4):
            plan = model.apply(1101, index)
            raw = plan["writes"][0]["bytes_hex"]
            value_text = plan["writes"][0]["value_text"]
            resolved_index, description, resolved_raw = model.resolve(1101, value_text)
            self.assertEqual(resolved_index, index)
            self.assertEqual(description, plan["choice_description"])
            self.assertEqual(bytes.fromhex(raw), resolved_raw)
            self.assertEqual(plan["target_record_id"], 1100)

    def test_apply_plan_writes_target_record_with_index_bytes(self):
        model = DropdownLinkModel(DROPDOWN_VALID_TABLE)
        plan = model.apply(1101, 2)
        self.assertEqual(plan["schema"], SCHEMA_DROPDOWN_PLAN)
        self.assertEqual(plan["index"], 2)
        self.assertEqual(plan["choice_description"], "Kill By Bomb")
        self.assertEqual(len(plan["writes"]), 1)
        element = plan["writes"][0]
        # The write goes to the TARGET record, not the link record.
        self.assertEqual(element["record_id"], 1100)
        self.assertEqual(element["label"], "Achievement Related")
        self.assertEqual(element["address"], "[pStatistics]+A10")
        self.assertEqual(element["bytes_hex"], "02")
        self.assertEqual(element["size"], 1)
        self.assertEqual(element["depth"], 0)
        self.assertEqual(element["value_text"], "2")

    def test_apply_plan_sha_stable_and_tamper_sensitive(self):
        model = DropdownLinkModel(DROPDOWN_VALID_TABLE)
        plan = model.apply(1101, 2)
        again = DropdownLinkModel(DROPDOWN_VALID_TABLE).apply(1101, 2)
        self.assertEqual(plan["plan_sha256"], again["plan_sha256"])
        payload = {key: value for key, value in plan.items() if key != "plan_sha256"}
        digest = sha256(json.dumps(payload, sort_keys=True,
                                  separators=(",", ":")).encode("utf-8")).hexdigest()
        self.assertEqual(digest, plan["plan_sha256"])
        payload["index"] = 3
        self.assertNotEqual(
            sha256(json.dumps(payload, sort_keys=True,
                              separators=(",", ":")).encode("utf-8")).hexdigest(),
            plan["plan_sha256"])

    def test_apply_index_out_of_range_rejected(self):
        model = DropdownLinkModel(DROPDOWN_VALID_TABLE)
        with self.assertRaises(DropdownIndexError) as caught:
            model.apply(1101, 4)
        self.assertEqual(caught.exception.index, 4)
        self.assertEqual(caught.exception.choice_count, 4)
        with self.assertRaises(DropdownIndexError) as caught:
            model.apply(1101, -1)
        self.assertEqual(caught.exception.index, -1)

    def test_apply_non_integer_index_rejected(self):
        model = DropdownLinkModel(DROPDOWN_VALID_TABLE)
        for bad in ("2", 2.0, None, [2], True):
            with self.subTest(bad=bad), self.assertRaises(DropdownIndexError) as caught:
                model.apply(1101, bad)
            self.assertIsNone(caught.exception.index)
            self.assertEqual(caught.exception.choice_count, 4)

    def test_resolve_out_of_range_rejected_with_context(self):
        model = DropdownLinkModel(DROPDOWN_VALID_TABLE)
        with self.assertRaises(DropdownIndexError) as caught:
            model.resolve(1101, "4")
        self.assertEqual(caught.exception.index, 4)
        self.assertEqual(caught.exception.choice_count, 4)
        self.assertIn("1100", str(caught.exception))
        self.assertIn("Achievement Related", str(caught.exception))

    def test_resolve_unparseable_value_rejected(self):
        model = DropdownLinkModel(DROPDOWN_VALID_TABLE)
        with self.assertRaises(DropdownLinkValueParseError) as caught:
            model.resolve(1101, "xyz")
        self.assertIn("Achievement Related", str(caught.exception))
        with self.assertRaises(DropdownLinkValueParseError):
            model.resolve(1101, 3)

    def test_index_semantics_not_choice_literal(self):
        # Binding model decision: the stored value is the index, so the plan
        # writes 1 (not the choice literal "20") for index 1.
        model = DropdownLinkModel(DROPDOWN_INDEX_SEMANTICS_TABLE)
        plan = model.apply(2301, 1)
        self.assertEqual(plan["writes"][0]["bytes_hex"],
                         struct.pack("<I", 1).hex().upper())
        index, description, raw = model.resolve(2301, "1")
        self.assertEqual((index, description), (1, "High"))
        with self.assertRaises(DropdownIndexError) as caught:
            model.resolve(2301, "20")  # the literal is not a valid index
        self.assertEqual(caught.exception.index, 20)

    def test_hex_target_index_encoding(self):
        model = DropdownLinkModel(DROPDOWN_HEX_TARGET_TABLE)
        plan = model.apply(2201, 2)
        element = plan["writes"][0]
        self.assertEqual(element["bytes_hex"], "0200")
        self.assertEqual(element["value_text"], "2")
        index, description, raw = model.resolve(2201, "1")
        self.assertEqual((index, description), (1, "One"))
        self.assertEqual(raw, b"\x01\x00")

    def test_float_target_index_and_parse(self):
        model = DropdownLinkModel(DROPDOWN_FLOAT_TARGET_TABLE)
        plan = model.apply(2701, 1)
        self.assertEqual(plan["writes"][0]["bytes_hex"],
                         struct.pack("<f", 1.0).hex().upper())
        index, description, raw = model.resolve(2701, "1")
        self.assertEqual((index, description), (1, "Two"))
        with self.assertRaises(DropdownIndexError):
            model.resolve(2701, "2")  # only two choices: indices 0..1
        with self.assertRaises(DropdownLinkValueParseError):
            model.resolve(2701, "1.5")  # not a whole index

    # -- structural refusals ----------------------------------------------------

    def test_missing_target_rejected(self):
        model = DropdownLinkModel(DROPDOWN_MISSING_TABLE)
        with self.assertRaises(DropdownLinkTargetError) as caught:
            model.inspect(1300)
        self.assertEqual(caught.exception.link_name, "Nowhere")
        self.assertEqual(caught.exception.candidates, ())
        self.assertIn("1300", str(caught.exception))

    def test_ambiguous_casefold_target_rejected_with_candidates(self):
        model = DropdownLinkModel(DROPDOWN_AMBIGUOUS_TABLE)
        with self.assertRaises(DropdownLinkTargetError) as caught:
            model.inspect(1202)
        self.assertEqual(caught.exception.candidates, (1200, 1201))
        self.assertIn("ambiguous", str(caught.exception))

    def test_casefold_name_identity_resolves(self):
        model = DropdownLinkModel(DROPDOWN_VALID_TABLE)
        result = model.inspect(1103, "1")  # link name is all lowercase
        self.assertEqual(result["target_record_id"], 1100)
        self.assertEqual(result["current_index"], 1)

    def test_self_link_cycle_rejected(self):
        model = DropdownLinkModel(DROPDOWN_SELF_LINK_TABLE)
        with self.assertRaises(DropdownLinkCycleError) as caught:
            model.inspect(1400)
        self.assertEqual(caught.exception.path, (1400,))
        self.assertIn("itself", str(caught.exception))

    def test_chained_link_cycle_rejected_with_path(self):
        model = DropdownLinkModel(DROPDOWN_CHAIN_TABLE)
        with self.assertRaises(DropdownLinkCycleError) as caught:
            model.resolve(1500, "0")
        self.assertEqual(caught.exception.path[:2], (1500, 1501))
        self.assertIn("chained", str(caught.exception))
        # The reverse direction refuses as well.
        with self.assertRaises(DropdownLinkCycleError):
            model.resolve(1501, "0")

    def test_group_header_target_rejected(self):
        # Pinned corpus shape: the link names a group header.
        model = DropdownLinkModel(DROPDOWN_GROUP_TARGET_TABLE)
        with self.assertRaises(DropdownLinkTypeRefused) as caught:
            model.inspect(1601)
        self.assertIn("1600", str(caught.exception))
        self.assertIn("kind=heading", str(caught.exception))

    def test_non_numeric_target_rejected(self):
        model = DropdownLinkModel(DROPDOWN_NON_NUMERIC_TABLE)
        with self.assertRaises(DropdownLinkTypeRefused) as caught:
            model.inspect(1701)
        self.assertIn("1700", str(caught.exception))
        self.assertIn("not a numeric", str(caught.exception))

    def test_script_target_rejected(self):
        model = DropdownLinkModel(DROPDOWN_SCRIPT_TARGET_TABLE)
        with self.assertRaises(DropdownLinkTypeRefused) as caught:
            model.inspect(1801)
        self.assertIn("1800", str(caught.exception))
        self.assertIn("kind=script", str(caught.exception))

    def test_link_record_not_value_rejected(self):
        model = DropdownLinkModel(DROPDOWN_LINK_NOT_VALUE_TABLE)
        with self.assertRaises(DropdownLinkTypeRefused) as caught:
            model.inspect(2400)
        self.assertIn("2400", str(caught.exception))
        self.assertIn("kind=script", str(caught.exception))

    def test_no_link_name_rejected(self):
        model = DropdownLinkModel(DROPDOWN_NO_LINK_NAME_TABLE)
        with self.assertRaises(DropdownLinkTargetError) as caught:
            model.inspect(2500)
        self.assertIsNone(caught.exception.link_name)
        self.assertEqual(caught.exception.candidates, ())

    def test_empty_dropdown_rejected(self):
        model = DropdownLinkModel(DROPDOWN_EMPTY_TABLE)
        with self.assertRaises(DropdownLinkEmptyRefused) as caught:
            model.inspect(1901)
        self.assertIn("1900", str(caught.exception))
        with self.assertRaises(DropdownLinkEmptyRefused):
            model.inspect(1903)  # only the "*" placeholder

    def test_unusable_choice_literal_rejected(self):
        model = DropdownLinkModel(DROPDOWN_BAD_CHOICE_TABLE)
        with self.assertRaises(DropdownLinkEmptyRefused) as caught:
            model.inspect(2001)
        self.assertIn("xyz", str(caught.exception))

    def test_hex_float_target_inspect_resolve_apply(self):
        # WP-33: a ShowAsHex Float target is a raw bit-pattern record; the
        # link pair is fully usable with fixed-width choice literals.
        model = DropdownLinkModel(DROPDOWN_HEX_FLOAT_TABLE)
        result = model.inspect(2801, "40000000")
        self.assertEqual(result["target_record_id"], 2800)
        self.assertEqual(result["target_variable_type"], "Float")
        self.assertEqual(len(result["choices"]), 3)
        self.assertEqual(result["choices"][1]["value"], "3F800000")
        self.assertTrue(result["activatable"])
        # The stored value is the index, rendered as its float bit pattern.
        self.assertEqual(result["current_index"], 2)
        self.assertEqual(result["current_choice"], "two")
        index, description, raw = model.resolve(2801, "40000000")
        self.assertEqual((index, description), (2, "two"))
        self.assertEqual(raw, b"\x00\x00\x00\x40")
        plan = model.apply(2801, 1)
        element = plan["writes"][0]
        self.assertEqual(element["record_id"], 2800)
        self.assertEqual(element["bytes_hex"], "0000803F")
        self.assertEqual(element["value_text"], "3F800000")
        self.assertEqual(plan["choice_description"], "one")
        # A short hex literal is not a valid bit-pattern choice.
        with self.assertRaises(DropdownLinkValueParseError):
            model.resolve(2801, "3F8000")

    def test_hex_float_target_unusable_choice_rejected(self):
        table = {
            2900: value_record("Bad Hex Float", address="bh", variable_type="Float",
                               show_as_hex=True,
                               dropdown_choices=[("3F8000", "short")]),
            2901: value_record("Linker", address="bl",
                               dropdown_link="Bad Hex Float"),
        }
        with self.assertRaises(DropdownLinkEmptyRefused) as caught:
            DropdownLinkModel(table).inspect(2901)
        self.assertIn("'3F8000'", str(caught.exception))
        self.assertIn("hexadecimal digits", str(caught.exception))

    def test_unknown_link_record_refused(self):
        model = DropdownLinkModel(DROPDOWN_VALID_TABLE)
        with self.assertRaises(DropdownLinkError):
            model.inspect(9999)
        with self.assertRaises(DropdownLinkError):
            model.apply("1101", 0)

    # -- activatability -----------------------------------------------------------

    def test_inactive_link_refused_by_resolve_and_apply(self):
        model = DropdownLinkModel(DROPDOWN_INACTIVE_TABLE)
        with self.assertRaises(DropdownLinkActivatableError) as caught:
            model.resolve(2101, "0")
        self.assertEqual(len(caught.exception.problems), 1)
        self.assertIn("not selected", caught.exception.problems[0])
        with self.assertRaises(DropdownLinkActivatableError) as caught:
            model.apply(2101, 0)
        self.assertEqual(len(caught.exception.problems), 1)
        with self.assertRaises(DropdownLinkActivatableError) as caught:
            model.apply(2103, 0)
        self.assertIn("unsupported", caught.exception.problems[0])
        # inspect stays read-only informative
        result = model.inspect(2103)
        self.assertFalse(result["activatable"])
        self.assertEqual(len(result["problems"]), 1)

    def test_inactive_target_refused(self):
        model = DropdownLinkModel(DROPDOWN_INACTIVE_TABLE)
        with self.assertRaises(DropdownLinkActivatableError) as caught:
            model.resolve(2103, "0")
        self.assertIn("Target B", caught.exception.problems[0])
        self.assertIn("unsupported", caught.exception.problems[0])

    # -- table normalization -------------------------------------------------------

    def test_dropdown_table_normalization_rejections(self):
        bad_tables = {
            "not a mapping": 42,
            "empty": {},
            "unknown kind": {1: value_record("a", kind="alien")},
            "bad parent": {1: value_record("a", parent_id=77)},
            "bad choices": {1: value_record("a", dropdown_choices=[("x",)], )},
            "bad link name": {1: value_record("a", dropdown_link="   ")},
            "bad read only": {1: value_record("a", dropdown_read_only="yes")},
            "bad current bytes": {1: value_record("a", current_bytes=[1])},
            "bad id": {"1": value_record("a")},
        }
        for name, table in bad_tables.items():
            with self.subTest(name=name), self.assertRaises(DropdownLinkTableError):
                DropdownLinkModel(table)

    def test_profile_record_must_match_display_flags(self):
        from ct2trainer.native.value_types import prepare_value_profile
        table = {
            3300: value_record("mismatch", variable_type="Array of byte",
                               show_as_hex=False, show_as_signed=None,
                               address="mm",
                               value_profile=prepare_value_profile(
                                   "Array of byte",
                                   {"ByteLength": 1, "ShowAsHex": True})),
        }
        with self.assertRaises(DropdownLinkTableError):
            DropdownLinkModel(table)


if __name__ == "__main__":
    unittest.main()
