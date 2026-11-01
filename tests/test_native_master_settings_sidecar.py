"""Master Trainer per-table settings sidecar (MT-6): the store contract.

Covers: the state-home sidecar layout (``<state home>/settings/
<table_sha256>.ct2trainer.json``), the save/load roundtrip with
byte-stable canonical bytes, the absent-file ``(None, [])`` contract,
foreign-table documents (the ``SettingsRejection`` path with a
displayable "different table" reason, no silent defaults), malformed-sha
refusals at every boundary, path containment (no file may appear outside
the state home), and the all-empty "nothing to persist" refusal. The
on/off wish persistence (engine state store, MT-4) is out of scope and
untouched here.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ct2trainer.native.settings_model import (
    SETTINGS_SCHEMA,
    SettingsDocument,
    SettingsError,
    create_default,
    document_to_json,
)
from ct2trainer.native.master_trainer.settings_sidecar import (
    MasterSettingsRefusal,
    MasterSettingsStore,
)

SHA_A = "a" * 64
SHA_B = "b" * 64


def full_document(sha=SHA_A, trainer_id="0123456789abcdef",
                  process_name="GameA.exe"):
    return SettingsDocument(
        schema=SETTINGS_SCHEMA, table_sha256=sha, trainer_id=trainer_id,
        process_name=process_name, selected=(2, 5, 9),
        names={2: "HP (draft)", 9: "SP"}, start_on=(5,),
        value_defaults={9: "100"}, hotkeys={2: ["F1"], 9: ["ctrl", "K"]})


class MasterSettingsSidecarTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.state_home = self.root / "statehome"
        self.state_home.mkdir()
        self.store = MasterSettingsStore(self.state_home)

    def tearDown(self):
        self._tmp.cleanup()

    # ------------------------------------------------- roundtrip (positive)

    def test_save_load_roundtrip_returns_identical_document(self):
        doc = full_document()
        path = self.store.save_for(doc, SHA_A)
        self.assertEqual(path, self.store.sidecar_path(SHA_A))
        loaded, reasons = self.store.load_for(SHA_A, [1, 2, 5, 9])
        self.assertEqual(reasons, [])
        self.assertEqual(loaded, doc)

    def test_on_disk_bytes_equal_canonical_document_bytes(self):
        doc = full_document()
        path = self.store.save_for(doc, SHA_A)
        self.assertEqual(path.read_bytes(), document_to_json(doc))
        self.store.save_for(doc, SHA_A)  # byte-stable across re-saves
        self.assertEqual(path.read_bytes(), document_to_json(doc))

    def test_known_ids_derive_from_all_document_fields(self):
        # The ids live only in the mapping fields, not selected/start_on.
        doc = SettingsDocument(
            schema=SETTINGS_SCHEMA, table_sha256=SHA_A, trainer_id=None,
            process_name=None, selected=(), names={7: "x"}, start_on=(),
            value_defaults={11: "3"}, hotkeys={13: ["F2"]})
        self.store.save_for(doc, SHA_A)
        loaded, reasons = self.store.load_for(SHA_A, [7, 11, 13])
        self.assertEqual(reasons, [])
        self.assertEqual(loaded, doc)

    def test_start_on_respects_switch_ids(self):
        doc = full_document()  # start_on=(5,)
        self.store.save_for(doc, SHA_A)
        loaded, reasons = self.store.load_for(SHA_A, [2, 5, 9],
                                              switch_ids=[2, 9])
        self.assertIsNone(loaded)
        self.assertTrue(any("non-switch" in r for r in reasons))
        loaded, reasons = self.store.load_for(SHA_A, [2, 5, 9],
                                              switch_ids=[2, 5, 9])
        self.assertEqual(reasons, [])
        self.assertEqual(loaded, doc)

    def test_process_name_mismatch_is_refused(self):
        self.store.save_for(full_document(process_name="GameA.exe"), SHA_A)
        loaded, reasons = self.store.load_for(SHA_A, [2, 5, 9],
                                              process_name="Other.exe")
        self.assertIsNone(loaded)
        self.assertTrue(any("process_name differs" in r for r in reasons))

    # ------------------------------------------------------------- absent

    def test_absent_sidecar_returns_none_and_no_reasons(self):
        self.assertFalse(self.store.has_table(SHA_A))
        loaded, reasons = self.store.load_for(SHA_A, [1])
        self.assertIsNone(loaded)
        self.assertEqual(reasons, [])

    def test_has_table_true_after_save(self):
        self.store.save_for(full_document(), SHA_A)
        self.assertTrue(self.store.has_table(SHA_A))
        self.assertFalse(self.store.has_table(SHA_B))

    # ------------------------------------------------------ foreign table

    def test_foreign_table_document_refused_with_displayable_reason(self):
        foreign = full_document(sha=SHA_B)
        path = self.store.sidecar_path(SHA_A)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(document_to_json(foreign))
        loaded, reasons = self.store.load_for(SHA_A, [2, 5, 9])
        self.assertIsNone(loaded)
        self.assertTrue(reasons)
        self.assertIn("different table", " ".join(reasons))
        for reason in reasons:
            self.assertIsInstance(reason, str)
            self.assertTrue(reason)

    # ------------------------------------------------------- malformed sha

    def test_malformed_sha_load_returns_named_reason(self):
        for bad in ("", "xyz", "A" * 64, "a" * 63, "a" * 65, "g" * 64):
            with self.subTest(bad=bad):
                loaded, reasons = self.store.load_for(bad, [1])
                self.assertIsNone(loaded)
                self.assertEqual(len(reasons), 1)
                self.assertIn("64-char lowercase hex", reasons[0])

    def test_malformed_sha_boundary_raises_named_refusal(self):
        for bad in ("nothex", "Z" * 64, "a" * 63, 1234):
            with self.subTest(bad=bad):
                with self.assertRaises(MasterSettingsRefusal):
                    self.store.sidecar_path(bad)
                with self.assertRaises(MasterSettingsRefusal):
                    self.store.has_table(bad)
                with self.assertRaises(MasterSettingsRefusal):
                    self.store.save_for(full_document(), bad)

    def test_refusal_is_settings_error_family(self):
        self.assertTrue(issubclass(MasterSettingsRefusal, SettingsError))
        self.assertTrue(issubclass(MasterSettingsRefusal, ValueError))

    # ---------------------------------------------------- path containment

    def test_sidecar_path_always_under_state_home(self):
        for sha in (SHA_A, "0" * 64, "f" * 64):
            path = self.store.sidecar_path(sha)
            self.assertEqual(path.parent, self.state_home / "settings")
            self.assertEqual(path.name, f"{sha}.ct2trainer.json")

    def test_settings_directory_created_on_save(self):
        self.assertFalse((self.state_home / "settings").exists())
        self.store.save_for(full_document(), SHA_A)
        self.assertTrue((self.state_home / "settings").is_dir())
        self.assertTrue(self.store.sidecar_path(SHA_A).is_file())

    def test_no_file_appears_outside_state_home(self):
        self.store.save_for(full_document(), SHA_A)
        for path in self.root.rglob("*"):
            self.assertTrue(path.is_dir() or self.state_home in path.parents,
                            str(path))

    # --------------------------------------------------------- save refusals

    def test_all_empty_document_save_refused_nothing_to_persist(self):
        empty = create_default(SHA_A)
        with self.assertRaises(MasterSettingsRefusal) as cm:
            self.store.save_for(empty, SHA_A)
        self.assertIn("nothing to persist", str(cm.exception))
        self.assertFalse(self.store.has_table(SHA_A))

    def test_save_document_of_other_table_refused(self):
        doc = full_document(sha=SHA_B)
        with self.assertRaises(SettingsError):
            self.store.save_for(doc, SHA_A)
        self.assertFalse(self.store.has_table(SHA_A))

    def test_save_requires_settings_document(self):
        with self.assertRaises(MasterSettingsRefusal):
            self.store.save_for("not a document", SHA_A)
