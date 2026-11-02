"""Master state document (MT: ask on first start; 0.25 preferences).

Covers the ``master_state`` persistence module end-to-end: canonical
byte-stable serialization, strict checksum-bound load, every fail-closed
refusal (malformed JSON, invalid shape, tampered checksum, foreign schema,
unknown fields, out-of-bounds last_folder, size limit), tolerant
``load_master_state`` (absent / refused -> None), and
``save_master_state`` directory creation.  Schema 2 (0.25) carries the
MT-10/11 preferences (last_table, attach_mode); schema-1 documents are
promoted on load with the documented defaults.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from ct2trainer.native.master_trainer.master_state import (
    ATTACH_MODE_ASK,
    ATTACH_MODE_AUTO,
    MASTER_STATE_FILENAME,
    MASTER_STATE_SCHEMA,
    MAX_MASTER_STATE_BYTES,
    MasterState,
    MasterStateRefusal,
    empty_master_state,
    load_master_state,
    master_state_from_bytes,
    master_state_to_bytes,
    save_master_state,
)


def _state(last_folder=None):
    return MasterState(schema=MASTER_STATE_SCHEMA, last_folder=last_folder)


class MasterStateSerializeTests(unittest.TestCase):
    def test_empty_state_roundtrip(self):
        raw = master_state_to_bytes(empty_master_state())
        document = json.loads(raw)
        self.assertEqual(set(document), {"payload", "sha256"})
        self.assertEqual(document["payload"],
                         {"schema": MASTER_STATE_SCHEMA, "last_folder": None,
                          "last_table": None,
                          "attach_mode": ATTACH_MODE_AUTO})
        canonical = json.dumps(document["payload"], sort_keys=True,
                               separators=(",", ":"), allow_nan=False,
                               ensure_ascii=True).encode("utf-8")
        self.assertEqual(hashlib.sha256(canonical).hexdigest(),
                         document["sha256"])
        self.assertEqual(master_state_from_bytes(raw), empty_master_state())

    def test_state_with_folder_roundtrip(self):
        folder = "C:\\tables"
        raw = master_state_to_bytes(_state(folder))
        self.assertEqual(master_state_from_bytes(raw), _state(folder))
        # The document is byte-stable: same input, same bytes.
        self.assertEqual(master_state_to_bytes(_state(folder)), raw)
        # Canonical trailing newline (same discipline as the tables index).
        self.assertTrue(raw.endswith(b"\n"))

    # -- schema 2 (0.25) preferences -------------------------------------------

    @staticmethod
    def _document(payload):
        """One checksum-bound document envelope around a raw payload."""
        canonical = json.dumps(payload, sort_keys=True,
                               separators=(",", ":"), allow_nan=False,
                               ensure_ascii=True).encode("utf-8")
        return (json.dumps({"payload": payload,
                            "sha256": hashlib.sha256(canonical).hexdigest()})
                .encode("utf-8"))

    def test_state_with_preferences_roundtrip(self):
        state = MasterState(MASTER_STATE_SCHEMA, "C:\\tables",
                            last_table="sub\\gamea.ct",
                            attach_mode=ATTACH_MODE_ASK)
        raw = master_state_to_bytes(state)
        self.assertEqual(master_state_from_bytes(raw), state)

    def test_legacy_schema1_document_promotes_on_load(self):
        payload = {"schema": 1, "last_folder": "C:\\tables"}
        state = master_state_from_bytes(self._document(payload))
        self.assertEqual(state, MasterState(
            MASTER_STATE_SCHEMA, "C:\\tables", last_table=None,
            attach_mode=ATTACH_MODE_AUTO))

    def test_to_bytes_refuses_legacy_schema(self):
        with self.assertRaises(MasterStateRefusal) as ctx:
            master_state_to_bytes(MasterState(schema=1, last_folder=None))
        self.assertIn("schema", str(ctx.exception))

    def test_from_bytes_refuses_bad_attach_mode(self):
        payload = {"schema": MASTER_STATE_SCHEMA, "last_folder": None,
                   "last_table": None, "attach_mode": "sometimes"}
        with self.assertRaises(MasterStateRefusal) as ctx:
            master_state_from_bytes(self._document(payload))
        self.assertIn("attach_mode", str(ctx.exception))

    def test_from_bytes_refuses_malformed_last_table(self):
        for bad in (123, "", ["a.ct"], {"t": 1}):
            payload = {"schema": MASTER_STATE_SCHEMA, "last_folder": None,
                       "last_table": bad, "attach_mode": ATTACH_MODE_AUTO}
            with self.assertRaises(MasterStateRefusal) as ctx:
                master_state_from_bytes(self._document(payload))
            self.assertIn("last_table", str(ctx.exception))

    def test_from_bytes_refuses_oversized_last_table(self):
        payload = {"schema": MASTER_STATE_SCHEMA, "last_folder": None,
                   "last_table": "x" * 5000,
                   "attach_mode": ATTACH_MODE_AUTO}
        with self.assertRaises(MasterStateRefusal) as ctx:
            master_state_from_bytes(self._document(payload))
        self.assertIn("last_table", str(ctx.exception))

    def test_from_bytes_refuses_schema1_with_schema2_fields(self):
        payload = {"schema": 1, "last_folder": None, "last_table": "a.ct"}
        with self.assertRaises(MasterStateRefusal) as ctx:
            master_state_from_bytes(self._document(payload))
        self.assertIn("unknown fields", str(ctx.exception))

    def test_to_bytes_refuses_non_state_document(self):
        with self.assertRaises(MasterStateRefusal):
            master_state_to_bytes({"schema": 1, "last_folder": None})

    def test_to_bytes_refuses_foreign_schema(self):
        with self.assertRaises(MasterStateRefusal) as ctx:
            master_state_to_bytes(MasterState(schema=99, last_folder=None))
        self.assertIn("schema", str(ctx.exception))

    def test_to_bytes_refuses_out_of_bounds_folder(self):
        with self.assertRaises(MasterStateRefusal):
            master_state_to_bytes(_state("x" * 5000))

    def test_from_bytes_refuses_malformed_json(self):
        with self.assertRaises(MasterStateRefusal) as ctx:
            master_state_from_bytes(b"not json at all")
        self.assertIn("not valid JSON", str(ctx.exception))

    def test_from_bytes_refuses_invalid_shape(self):
        with self.assertRaises(MasterStateRefusal):
            master_state_from_bytes(b'{"payload": {}}')
        with self.assertRaises(MasterStateRefusal):
            master_state_from_bytes(b'{"payload": {}, "sha256": "x", "extra": 1}')
        with self.assertRaises(MasterStateRefusal):
            master_state_from_bytes(b'{"sha256": "x"}')

    def test_from_bytes_refuses_tampered_checksum(self):
        raw = json.loads(master_state_to_bytes(_state("C:\\t")))
        raw["payload"]["last_folder"] = "C:\\other"
        with self.assertRaises(MasterStateRefusal) as ctx:
            master_state_from_bytes(json.dumps(raw, sort_keys=True)
                                    .encode("utf-8"))
        self.assertIn("checksum does not match", str(ctx.exception))

    def test_from_bytes_refuses_foreign_schema(self):
        payload = {"schema": MASTER_STATE_SCHEMA + 1, "last_folder": None}
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                               allow_nan=False,
                               ensure_ascii=True).encode("utf-8")
        document = {"payload": payload,
                    "sha256": hashlib.sha256(canonical).hexdigest()}
        with self.assertRaises(MasterStateRefusal) as ctx:
            master_state_from_bytes(json.dumps(document).encode("utf-8"))
        self.assertIn("schema", str(ctx.exception))

    def test_from_bytes_refuses_unknown_fields(self):
        payload = {"schema": MASTER_STATE_SCHEMA, "last_folder": None,
                   "surprise": True}
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                               allow_nan=False,
                               ensure_ascii=True).encode("utf-8")
        document = {"payload": payload,
                    "sha256": hashlib.sha256(canonical).hexdigest()}
        with self.assertRaises(MasterStateRefusal) as ctx:
            master_state_from_bytes(json.dumps(document).encode("utf-8"))
        self.assertIn("unknown fields", str(ctx.exception))
        self.assertEqual(ctx.exception.reasons[0].count("surprise"), 1)

    def test_from_bytes_refuses_malformed_last_folder(self):
        for bad in (123, "", ["C:\\t"], {"p": 1}):
            payload = {"schema": MASTER_STATE_SCHEMA, "last_folder": bad}
            canonical = json.dumps(payload, sort_keys=True,
                                   separators=(",", ":"), allow_nan=False,
                                   ensure_ascii=True).encode("utf-8")
            document = {"payload": payload,
                        "sha256": hashlib.sha256(canonical).hexdigest()}
            with self.assertRaises(MasterStateRefusal) as ctx:
                master_state_from_bytes(json.dumps(document).encode("utf-8"))
            self.assertIn("last_folder", str(ctx.exception))

    def test_from_bytes_refuses_oversized_document(self):
        with self.assertRaises(MasterStateRefusal) as ctx:
            master_state_from_bytes(b"x" * (MAX_MASTER_STATE_BYTES + 1))
        self.assertIn("size limit", str(ctx.exception))


class MasterStateFileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(self._rmtree)

    def _rmtree(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_save_creates_parent_and_roundtrips(self):
        path = self.tmp / "nested" / "home" / MASTER_STATE_FILENAME
        save_master_state(_state("C:\\tables"), path)
        self.assertTrue(path.is_file())
        self.assertEqual(load_master_state(path), _state("C:\\tables"))

    def test_load_absent_file_is_none(self):
        self.assertIsNone(load_master_state(self.tmp / "missing"
                                             / MASTER_STATE_FILENAME))

    def test_load_refused_file_is_none(self):
        path = self.tmp / MASTER_STATE_FILENAME
        path.write_bytes(b"corrupted")
        self.assertIsNone(load_master_state(path))
        # The corrupted document stays on disk untouched (never a silent
        # reset; the caller falls back to a fresh first start).
        self.assertEqual(path.read_bytes(), b"corrupted")


if __name__ == "__main__":
    unittest.main()
