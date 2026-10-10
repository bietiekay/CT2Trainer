"""Settings sidecar model: hash binding, strict validation, visible rejection."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from ct2trainer.native.settings_model import (
    SETTINGS_FILENAME,
    SETTINGS_SCHEMA,
    SettingsDocument,
    SettingsModel,
    SettingsRejection,
    SettingsError,
    create_default,
    document_to_json,
    sha256_hex,
)


TABLE_A = b"fixture-ct-bytes-a"
TABLE_B = b"fixture-ct-bytes-b"
SHA_A = sha256_hex(TABLE_A)
SHA_B = sha256_hex(TABLE_B)
KNOWN_IDS = (1, 2, 3)
SWITCH_IDS = (1, 2)


class _Fixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="native-settings-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / SETTINGS_FILENAME
        self.model = SettingsModel(SHA_A, KNOWN_IDS, trainer_id="a" * 16,
                                   process_name="Fixture.exe", switch_ids=SWITCH_IDS)
        self.other = SettingsModel(SHA_B, KNOWN_IDS, trainer_id="a" * 16,
                                   process_name="Fixture.exe", switch_ids=SWITCH_IDS)

    def _document(self, **overrides):
        document = create_default(SHA_A, trainer_id="a" * 16, process_name="Fixture.exe")
        values = {
            "schema": SETTINGS_SCHEMA,
            "table_sha256": SHA_A,
            "trainer_id": "a" * 16,
            "process_name": "Fixture.exe",
            "selected": (1, 2),
            "names": {1: "Visible name"},
            "start_on": (1,),
            "value_defaults": {2: "12.5"},
            "hotkeys": {1: ["ctrl", "F1"]},
        }
        values.update(overrides)
        return SettingsDocument(**values)


class SettingsValidationTests(_Fixture, unittest.TestCase):
    def test_round_trip_preserves_every_field(self):
        document = self._document()
        self.model.save(document, self.path)
        loaded = self.model.load(self.path)
        self.assertEqual(loaded, document)
        self.assertEqual(loaded.selected_set(), {1, 2})
        self.assertEqual(loaded.name_for(1), "Visible name")
        self.assertEqual(loaded.start_on_set(), {1})
        self.assertEqual(loaded.value_default_for(2), "12.5")
        self.assertIsNone(loaded.name_for(3))
        self.assertIsNone(loaded.value_default_for(1))

    def test_loading_a_foreign_table_is_a_visible_rejection(self):
        document = self._document()
        self.model.save(document, self.path)
        with self.assertRaises(SettingsRejection) as ctx:
            self.other.load(self.path)
        self.assertTrue(any("different table" in reason for reason in ctx.exception.reasons))
        self.assertFalse(any("reset" in reason for reason in ctx.exception.reasons))

    def test_schema_version_mismatch_is_rejected(self):
        self.model.save(self._document(), self.path)
        for schema in (0, 2, "1", None):
            with self.subTest(schema=schema):
                self._rewrite(schema)
                with self.assertRaises(SettingsRejection) as ctx:
                    self.model.load(self.path)
                self.assertTrue(any("Schema version" in reason for reason in ctx.exception.reasons))

    def _rewrite(self, schema):
        raw = json.loads(self.path.read_bytes())
        raw["schema"] = schema
        self.path.write_bytes(json.dumps(raw, sort_keys=True, separators=(",", ":")).encode())

    def test_unknown_record_ids_are_rejected(self):
        self.model.save(self._document(), self.path)
        self._merge(selected=(1, 99))
        with self.assertRaises(SettingsRejection) as ctx:
            self.model.load(self.path)
        self.assertTrue(any("selected" in reason and "99" in reason for reason in ctx.exception.reasons))
        self._merge(selected=(1, 2), start_on=(99,))
        with self.assertRaises(SettingsRejection) as ctx:
            self.model.load(self.path)
        self.assertTrue(any("start_on" in reason for reason in ctx.exception.reasons))

    def _merge(self, **fields):
        raw = json.loads(self.path.read_bytes())
        raw.update(fields)
        self.path.write_bytes(json.dumps(raw, sort_keys=True, separators=(",", ":")).encode())

    def test_duplicate_and_unsorted_ids_are_rejected(self):
        self.model.save(self._document(), self.path)
        self._merge(selected=[1, 1])
        with self.assertRaises(SettingsRejection) as ctx:
            self.model.load(self.path)
        self.assertTrue(any("duplicate" in reason for reason in ctx.exception.reasons))
        self._merge(selected=[2, 1])
        with self.assertRaises(SettingsRejection) as ctx:
            self.model.load(self.path)
        self.assertTrue(any("sorted" in reason for reason in ctx.exception.reasons))

    def test_start_on_must_reference_switch_records(self):
        self.model.save(self._document(), self.path)
        self._merge(start_on=(3,))  # record 3 is not a switch
        with self.assertRaises(SettingsRejection) as ctx:
            self.model.load(self.path)
        self.assertTrue(any("non-switch" in reason for reason in ctx.exception.reasons))

    def test_trainer_and_process_binding_is_checked(self):
        self.model.save(self._document(), self.path)
        self._merge(trainer_id="f" * 16)
        with self.assertRaises(SettingsRejection) as ctx:
            self.model.load(self.path)
        self.assertTrue(any("trainer_id" in reason for reason in ctx.exception.reasons))
        self._merge(trainer_id="a" * 16, process_name="Other.exe")
        with self.assertRaises(SettingsRejection) as ctx:
            self.model.load(self.path)
        self.assertTrue(any("process_name" in reason for reason in ctx.exception.reasons))

    def test_corrupt_and_ambiguous_json_is_rejected(self):
        self.path.write_bytes(b"{not-json")
        with self.assertRaises(SettingsRejection):
            self.model.load(self.path)
        self.path.write_bytes(b'[1, 2]')
        with self.assertRaises(SettingsRejection):
            self.model.load(self.path)
        duplicate = ('{"schema":1,"schema":1,"table_sha256":"%s"}' % SHA_A).encode()
        self.path.write_bytes(duplicate)
        with self.assertRaises(SettingsRejection):
            self.model.load(self.path)

    def test_malformed_text_fields_are_rejected(self):
        self.model.save(self._document(), self.path)
        self._merge(names={"1": "x" * 513})
        with self.assertRaises(SettingsRejection) as ctx:
            self.model.load(self.path)
        self.assertTrue(any("too long" in reason for reason in ctx.exception.reasons))
        self._merge(names={"42": "unknown"})
        with self.assertRaises(SettingsRejection) as ctx:
            self.model.load(self.path)
        self.assertTrue(any("unknown record" in reason for reason in ctx.exception.reasons))
        self._merge(names={"1": "ok"}, value_defaults={"2": "x" * 513})
        with self.assertRaises(SettingsRejection) as ctx:
            self.model.load(self.path)
        self.assertTrue(any("value_default" in reason for reason in ctx.exception.reasons))

    def test_hotkey_tokens_are_bounded_and_bound_to_known_ids(self):
        self.model.save(self._document(), self.path)
        self._merge(hotkeys={"1": ["ctrl", "alt", "shift", "meta", "F1", "extra"]})
        with self.assertRaises(SettingsRejection) as ctx:
            self.model.load(self.path)
        self.assertTrue(any("1..5" in reason for reason in ctx.exception.reasons))
        self._merge(hotkeys={"99": ["F1"]})
        with self.assertRaises(SettingsRejection) as ctx:
            self.model.load(self.path)
        self.assertTrue(any("unknown record" in reason for reason in ctx.exception.reasons))

    def test_multiple_problems_are_all_reported(self):
        self.model.save(self._document(), self.path)
        self._merge(selected=(7,), names={"8": "n"}, hotkeys={"9": ["F2"]})
        with self.assertRaises(SettingsRejection) as ctx:
            self.model.load(self.path)
        self.assertGreaterEqual(len(ctx.exception.reasons), 3)


class SettingsSaveTests(_Fixture, unittest.TestCase):
    def test_save_requires_the_settings_filename(self):
        with self.assertRaises(SettingsError):
            self.model.save(self._document(), Path(self.temp.name) / "settings.json")
        self.assertFalse((Path(self.temp.name) / "settings.json").exists())

    def test_save_refuses_a_document_bound_to_another_table(self):
        foreign = create_default(SHA_B)
        foreign = SettingsDocument(schema=foreign.schema, table_sha256=foreign.table_sha256,
                                   trainer_id=None, process_name=None, selected=(),
                                   names={}, start_on=(), value_defaults={}, hotkeys={})
        with self.assertRaises(SettingsError):
            self.model.save(foreign, self.path)
        self.assertFalse(self.path.exists())

    def test_default_document_is_a_draft_without_selections(self):
        document = create_default(SHA_A)
        self.assertEqual(document.selected, ())
        self.assertEqual(document.names, {})
        self.assertEqual(document.start_on, ())
        self.assertEqual(document.value_defaults, {})
        self.assertEqual(document.hotkeys, {})

    def test_serialized_bytes_are_canonical_and_deterministic(self):
        document = self._document()
        first = document_to_json(document)
        second = document_to_json(document)
        self.assertEqual(first, second)
        parsed = json.loads(first)
        self.assertEqual(list(parsed.keys()), sorted(parsed.keys()))
        self.model.save(document, self.path)
        self.assertEqual(self.path.read_bytes(), first)


class SettingsApplyTests(_Fixture, unittest.TestCase):
    def test_apply_uses_a_separate_explicit_write_and_keeps_the_draft(self):
        document = self._document()
        calls = []
        confirmed = self.model.apply_value_default(document, 2, write=lambda rid, text: calls.append((rid, text)) or True)
        self.assertTrue(confirmed)
        self.assertEqual(calls, [(2, "12.5")])
        self.assertEqual(document.value_default_for(2), "12.5", "the draft is not consumed by applying")

    def test_unconfirmed_write_is_not_reported_applied(self):
        document = self._document()
        self.assertFalse(self.model.apply_value_default(document, 2, write=lambda rid, text: False))

    def test_apply_refuses_missing_defaults_unknown_ids_and_foreign_tables(self):
        document = self._document()
        with self.assertRaises(SettingsError):
            self.model.apply_value_default(document, 1, write=lambda rid, text: True)
        with self.assertRaises(SettingsError):
            self.model.apply_value_default(document, 99, write=lambda rid, text: True)
        with self.assertRaises(SettingsRejection):
            self.other.apply_value_default(document, 2, write=lambda rid, text: True)
        with self.assertRaises(SettingsError):
            self.model.apply_value_default(document, 2, write=None)


if __name__ == "__main__":
    unittest.main()
