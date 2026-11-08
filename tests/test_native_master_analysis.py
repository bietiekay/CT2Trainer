"""Master Trainer 0.32: per-table entry count + blocked count (MT-24).

Covers the pure ``table_analysis`` layer (the bounded plan-counts
extraction, the persisted ``table-analysis.json`` document with its
schema-1 discipline - unknown field is a named refusal, the
checksummed envelope, the LRU-bounded store, the column text
helpers, the details-window rows) and the background
``AnalysisWorker`` (success / failure / sha-mismatch entries,
dedupe by content sha, the queue bound, pause / resume, stop, the
bounded drain).  The worker tests use an injected fake plan
compiler and a fake app - no real table is compiled and no real
process is attached.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from ct2trainer.native.master_trainer import table_analysis
from ct2trainer.native.master_trainer.analysis_worker import (
    QUEUE_LIMIT, AnalysisWorker, active_workers)
from ct2trainer.native.master_trainer.table_analysis import (
    ANALYSIS_ENTRIES_LIMIT, BLOCKED_REASONS_LIMIT, ERROR_DETAIL_LIMIT,
    AnalysisRefusal, AnalysisStore, analysis_document_from_bytes,
    analysis_document_to_bytes, blocked_column_text,
    blocked_reasons_from_plan, counts_from_plan, details_analysis_lines,
    entries_column_text, evict_oldest, failed_analysis, load_analysis_document,
    ok_analysis, save_analysis_document)


def _plan(sha: str, entries) -> dict:
    return {"schema": 2, "table_sha256": sha, "entries": entries}


def _entries() -> list:
    return [
        {"id": 1, "supported": True, "kind": "value", "reason": ""},
        {"id": 2, "supported": True, "kind": "script", "reason": ""},
        {"id": 3, "supported": True, "kind": "heading", "reason": ""},
        {"id": 4, "supported": False, "kind": "value", "reason": "r-one"},
        {"id": 5, "supported": False, "kind": "script", "reason": "r-two"},
        {"id": 6, "supported": False, "kind": "value", "reason": "r-one"},
    ]


def _ok(sha: str) -> dict:
    return ok_analysis(counts_from_plan(_plan(sha, _entries())),
                       blocked_reasons_from_plan(_plan(sha, _entries())),
                       "2026-11-05T00:00:00Z")


class CountsFromPlanTests(unittest.TestCase):
    """MT-24 (0.32): the bounded entry counts of one plan."""

    def test_the_counts_match_the_entry_list(self):
        plan = _plan("a" * 64, _entries())
        self.assertEqual(counts_from_plan(plan),
                         {"total": 6, "supported": 3, "actionable": 2,
                          "blocked": 3, "headings": 1})

    def test_a_plan_without_entries_is_a_refusal(self):
        with self.assertRaises(AnalysisRefusal) as ctx:
            counts_from_plan({"schema": 2})
        self.assertIn("entries list", str(ctx.exception))

    def test_a_non_dict_entry_is_a_refusal(self):
        with self.assertRaises(AnalysisRefusal):
            counts_from_plan(_plan("a" * 64, [{"id": 1}, "nope"]))

    def test_a_missing_supported_flag_counts_as_blocked(self):
        plan = _plan("a" * 64, [{"id": 1, "kind": "value"}])
        self.assertEqual(counts_from_plan(plan)["blocked"], 1)
        self.assertEqual(counts_from_plan(plan)["supported"], 0)


class BlockedReasonsFromPlanTests(unittest.TestCase):
    """MT-24 (0.32): the top unsupported reasons of one plan."""

    def test_the_reasons_are_bounded_and_ordered(self):
        entries = []
        # nine distinct reasons: r-a twice, the rest once each.
        for i, name in enumerate(["r-a", "r-b", "r-c", "r-d", "r-e",
                                  "r-f", "r-g", "r-h", "r-i"]):
            entries.append({"id": i + 1, "supported": False,
                            "kind": "value", "reason": name})
            if name == "r-a":
                entries.append({"id": i + 100, "supported": False,
                                "kind": "value", "reason": name})
        reasons = blocked_reasons_from_plan(_plan("a" * 64, entries))
        self.assertEqual(len(reasons), BLOCKED_REASONS_LIMIT)
        self.assertEqual(reasons["r-a"], 2)
        # Highest counts first, ties by reason name.
        self.assertEqual(list(reasons), ["r-a", "r-b", "r-c", "r-d",
                                         "r-e", "r-f", "r-g", "r-h"])

    def test_nothing_blocked_is_empty(self):
        plan = _plan("a" * 64,
                     [{"id": 1, "supported": True, "kind": "value"}])
        self.assertEqual(blocked_reasons_from_plan(plan), {})

    def test_a_plan_without_entries_is_a_refusal(self):
        with self.assertRaises(AnalysisRefusal):
            blocked_reasons_from_plan({"schema": 2})

    def test_an_empty_reason_is_named(self):
        entries = [{"id": 1, "supported": False, "kind": "value"}]
        reasons = blocked_reasons_from_plan(_plan("a" * 64, entries))
        self.assertEqual(reasons, {"no-reason": 1})


class EntryBuilderTests(unittest.TestCase):
    """MT-24 (0.32): the persisted entry builders."""

    def test_the_ok_entry_shape(self):
        entry = ok_analysis({"total": 1, "supported": 1, "actionable": 1,
                             "blocked": 0, "headings": 0}, {}, "now-ts")
        self.assertEqual(set(entry), {"status", "counts",
                                      "blocked_reasons", "analyzed_at"})
        self.assertEqual(entry["status"], "ok")
        self.assertEqual(entry["analyzed_at"], "now-ts")

    def test_the_failed_entry_carries_the_named_error(self):
        entry = failed_analysis("ValueError: boom", "now-ts")
        self.assertEqual(set(entry), {"status", "error", "analyzed_at"})
        self.assertEqual(entry["status"], "failed")
        self.assertEqual(entry["error"], "ValueError: boom")

    def test_the_failed_error_is_truncated_to_the_bound(self):
        entry = failed_analysis("x" * (ERROR_DETAIL_LIMIT + 50), "now-ts")
        self.assertEqual(len(entry["error"]), ERROR_DETAIL_LIMIT)

    def test_the_failed_error_is_stripped(self):
        entry = failed_analysis("  boom  ", "now-ts")
        self.assertEqual(entry["error"], "boom")


class DocumentValidationTests(unittest.TestCase):
    """MT-24 (0.32): the schema-1 document discipline."""

    def _payload(self) -> dict:
        return {"schema": 1, "tables": {"a" * 64: _ok("a" * 64)}}

    def test_the_roundtrip_preserves_the_document(self):
        payload = self._payload()
        raw = analysis_document_to_bytes(payload)
        self.assertEqual(analysis_document_from_bytes(raw), payload)

    def test_the_roundtrip_bytes_are_canonical(self):
        payload = self._payload()
        self.assertEqual(analysis_document_to_bytes(payload),
                         analysis_document_to_bytes(payload))

    def test_the_checksum_mismatch_is_refused(self):
        payload = self._payload()
        raw = analysis_document_to_bytes(payload)
        document = json.loads(raw.decode("utf-8"))
        document["payload"]["tables"]["a" * 64]["analyzed_at"] = \
            "2026-11-05T01:00:00Z"
        with self.assertRaises(AnalysisRefusal) as ctx:
            analysis_document_from_bytes(
                json.dumps(document).encode("utf-8"))
        self.assertIn("checksum", str(ctx.exception))

    def test_not_json_is_refused(self):
        with self.assertRaises(AnalysisRefusal):
            analysis_document_from_bytes(b"not json at all")

    def test_the_missing_envelope_fields_are_refused(self):
        with self.assertRaises(AnalysisRefusal):
            analysis_document_from_bytes(
                json.dumps({"payload": self._payload()}).encode("utf-8"))

    def test_an_unknown_schema_is_refused(self):
        payload = self._payload()
        payload["schema"] = 2
        canonical = json.dumps(payload, sort_keys=True,
                               separators=(",", ":"),
                               ensure_ascii=True).encode("utf-8")
        raw = json.dumps({"payload": payload,
                          "sha256": hashlib.sha256(canonical).hexdigest()
                          }).encode("utf-8")
        with self.assertRaises(AnalysisRefusal) as ctx:
            analysis_document_from_bytes(raw)
        self.assertIn("schema", str(ctx.exception))

    def test_unknown_document_fields_are_refused(self):
        payload = self._payload()
        payload["extra"] = 1
        raw = analysis_document_to_bytes(self._payload())
        document = json.loads(raw.decode("utf-8"))
        document["payload"] = payload
        with self.assertRaises(AnalysisRefusal):
            analysis_document_from_bytes(
                json.dumps(document).encode("utf-8"))

    def test_an_unknown_entry_status_is_refused(self):
        payload = self._payload()
        payload["tables"]["a" * 64] = {"status": "weird",
                                       "analyzed_at":
                                       "2026-11-05T00:00:00Z"}
        raw = analysis_document_to_bytes(self._payload())
        document = json.loads(raw.decode("utf-8"))
        document["payload"] = payload
        with self.assertRaises(AnalysisRefusal):
            analysis_document_from_bytes(
                json.dumps(document).encode("utf-8"))

    def test_an_ok_entry_with_unknown_fields_is_refused(self):
        entry = _ok("a" * 64)
        entry["extra"] = 1
        payload = {"schema": 1, "tables": {"a" * 64: entry}}
        raw = analysis_document_to_bytes(self._payload())
        document = json.loads(raw.decode("utf-8"))
        document["payload"] = payload
        with self.assertRaises(AnalysisRefusal):
            analysis_document_from_bytes(
                json.dumps(document).encode("utf-8"))

    def test_a_failed_entry_must_carry_the_error(self):
        payload = {"schema": 1, "tables": {"a" * 64: {
            "status": "failed", "analyzed_at": "2026-11-05T00:00:00Z"}}}
        raw = analysis_document_to_bytes(self._payload())
        document = json.loads(raw.decode("utf-8"))
        document["payload"] = payload
        with self.assertRaises(AnalysisRefusal):
            analysis_document_from_bytes(
                json.dumps(document).encode("utf-8"))

    def test_an_invalid_timestamp_is_refused(self):
        payload = self._payload()
        payload["tables"]["a" * 64]["analyzed_at"] = "yesterday"
        raw = analysis_document_to_bytes(self._payload())
        document = json.loads(raw.decode("utf-8"))
        document["payload"] = payload
        with self.assertRaises(AnalysisRefusal):
            analysis_document_from_bytes(
                json.dumps(document).encode("utf-8"))

    def test_an_invalid_sha_key_is_refused(self):
        payload = {"schema": 1, "tables": {"nothex": _ok("a" * 64)}}
        raw = analysis_document_to_bytes(self._payload())
        document = json.loads(raw.decode("utf-8"))
        document["payload"] = payload
        with self.assertRaises(AnalysisRefusal):
            analysis_document_from_bytes(
                json.dumps(document).encode("utf-8"))

    def test_the_counts_keys_mismatch_is_refused(self):
        entry = _ok("a" * 64)
        del entry["counts"]["headings"]
        payload = {"schema": 1, "tables": {"a" * 64: entry}}
        raw = analysis_document_to_bytes(self._payload())
        document = json.loads(raw.decode("utf-8"))
        document["payload"] = payload
        with self.assertRaises(AnalysisRefusal):
            analysis_document_from_bytes(
                json.dumps(document).encode("utf-8"))

    def test_a_negative_count_is_refused(self):
        entry = _ok("a" * 64)
        entry["counts"]["blocked"] = -1
        payload = {"schema": 1, "tables": {"a" * 64: entry}}
        raw = analysis_document_to_bytes(self._payload())
        document = json.loads(raw.decode("utf-8"))
        document["payload"] = payload
        with self.assertRaises(AnalysisRefusal):
            analysis_document_from_bytes(
                json.dumps(document).encode("utf-8"))

    def test_blocked_reasons_over_the_limit_are_refused(self):
        entry = _ok("a" * 64)
        entry["blocked_reasons"] = {
            "r-%d" % i: 1 for i in range(BLOCKED_REASONS_LIMIT + 1)}
        payload = {"schema": 1, "tables": {"a" * 64: entry}}
        raw = analysis_document_to_bytes(self._payload())
        document = json.loads(raw.decode("utf-8"))
        document["payload"] = payload
        with self.assertRaises(AnalysisRefusal):
            analysis_document_from_bytes(
                json.dumps(document).encode("utf-8"))


class LoadSaveTests(unittest.TestCase):
    """MT-24 (0.32): the document I/O (absent / refused -> None)."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "table-analysis.json"

    def test_an_absent_file_loads_none(self):
        self.assertIsNone(load_analysis_document(self.path))

    def test_save_creates_the_directory(self):
        nested = Path(self.temporary.name) / "deep" / "er" \
            / "table-analysis.json"
        save_analysis_document(
            {"schema": 1, "tables": {"a" * 64: _ok("a" * 64)}}, nested)
        self.assertEqual(load_analysis_document(nested)["tables"]["a" * 64]
                         ["status"], "ok")

    def test_a_refused_document_loads_none(self):
        self.path.write_bytes(b"definitely not json")
        self.assertIsNone(load_analysis_document(self.path))

    def test_the_saved_file_is_the_checksummed_envelope(self):
        payload = {"schema": 1, "tables": {"a" * 64: _ok("a" * 64)}}
        save_analysis_document(payload, self.path)
        raw = self.path.read_bytes()
        self.assertTrue(raw.endswith(b"\n"))
        document = json.loads(raw.decode("utf-8"))
        self.assertEqual(set(document), {"payload", "sha256"})
        self.assertEqual(document["payload"], payload)


class EvictOldestTests(unittest.TestCase):
    """MT-24 (0.32): the LRU-by-analyzed_at bound."""

    def test_the_oldest_entry_is_dropped(self):
        tables = {
            "a" * 64: _ok("a" * 64),
            "b" * 64: _ok("b" * 64),
            "c" * 64: _ok("c" * 64),
        }
        tables["b" * 64]["analyzed_at"] = "2026-11-05T01:00:00Z"
        tables["c" * 64]["analyzed_at"] = "2026-11-05T02:00:00Z"
        evict_oldest(tables, limit=2)
        self.assertEqual(set(tables), {"b" * 64, "c" * 64})

    def test_ties_break_by_the_sha256_key(self):
        tables = {
            "a" * 64: _ok("a" * 64),
            "b" * 64: _ok("b" * 64),
        }
        evict_oldest(tables, limit=1)
        self.assertEqual(set(tables), {"b" * 64})

    def test_the_mapping_is_mutated_in_place(self):
        tables = {"a" * 64: _ok("a" * 64)}
        self.assertIs(evict_oldest(tables, limit=5), tables)


class AnalysisStoreTests(unittest.TestCase):
    """MT-24 (0.32): the persistent per-sha analysis cache."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.store = AnalysisStore(self.temporary.name)

    def test_a_fresh_store_is_empty(self):
        self.assertEqual(self.store.document(),
                         {"schema": 1, "tables": {}})
        self.assertIsNone(self.store.get("a" * 64))
        self.assertFalse(self.store.has("a" * 64))

    def test_update_persists_the_entry(self):
        self.store.update("a" * 64, _ok("a" * 64))
        self.assertEqual(self.store.get("a" * 64)["status"], "ok")
        # A re-loaded store sees the same entry.
        again = AnalysisStore(self.temporary.name)
        self.assertEqual(again.get("a" * 64), self.store.get("a" * 64))

    def test_update_refuses_a_malformed_key(self):
        with self.assertRaises(AnalysisRefusal):
            self.store.update("nothex", _ok("a" * 64))

    def test_update_refuses_a_malformed_entry(self):
        with self.assertRaises(AnalysisRefusal):
            self.store.update("a" * 64, {"status": "weird"})

    def test_update_evicts_over_the_default_limit(self):
        # Fill the document to the bound, then one more update evicts
        # the oldest entry.
        tables = {"%064x" % i: _ok("%064x" % i)
                  for i in range(ANALYSIS_ENTRIES_LIMIT)}
        # Several entries share the oldest timestamp; the tie breaks by
        # the sha256 key, so the "0"*64 entry is the one evicted.
        for i, key in enumerate(tables):
            tables[key]["analyzed_at"] = \
                "2026-10-%02dT00:00:00Z" % ((i % 28) + 1)
        save_analysis_document({"schema": 1, "tables": tables},
                               self.store.path)
        new_key = "f" * 64
        self.store.update(new_key, _ok(new_key))
        document = self.store.document()
        self.assertEqual(len(document["tables"]), ANALYSIS_ENTRIES_LIMIT)
        self.assertIn(new_key, document["tables"])
        self.assertNotIn("0" * 64, document["tables"])

    def test_clear_resets_the_document(self):
        self.store.update("a" * 64, _ok("a" * 64))
        self.store.clear()
        self.assertEqual(self.store.document()["tables"], {})
        self.assertTrue(self.store.path.is_file())

    def test_a_refused_document_is_treated_as_absent(self):
        self.store.update("a" * 64, _ok("a" * 64))
        self.store.path.write_bytes(b"corrupted")
        self.assertEqual(self.store.document(),
                         {"schema": 1, "tables": {}})
        self.assertIsNone(self.store.get("a" * 64))


class ColumnTextTests(unittest.TestCase):
    """MT-24 (0.32): the waiting-view column text per entry."""

    def test_the_pending_marker(self):
        self.assertEqual(entries_column_text(None), "…")
        self.assertEqual(blocked_column_text(None), "…")

    def test_the_failed_marker(self):
        failed = failed_analysis("ValueError: boom", "2026-11-05T00:00:00Z")
        self.assertEqual(entries_column_text(failed), "–")
        self.assertEqual(blocked_column_text(failed), "–")

    def test_the_ok_counts(self):
        entry = _ok("a" * 64)
        self.assertEqual(entries_column_text(entry), "2")
        self.assertEqual(blocked_column_text(entry), "3")


class DetailsAnalysisLinesTests(unittest.TestCase):
    """MT-24 (0.32): the details-window analysis rows."""

    def test_the_pending_entry(self):
        self.assertEqual(details_analysis_lines(None),
                         [("Entry analysis",
                           "not analyzed yet (the background analysis "
                           "is pending)")])

    def test_the_failed_entry_shows_the_named_error(self):
        failed = failed_analysis("ValueError: boom", "2026-11-05T00:00:00Z")
        self.assertEqual(details_analysis_lines(failed),
                         [("Entry analysis", "failed: ValueError: boom")])

    def test_the_ok_entry_without_blocked_records(self):
        entry = ok_analysis({"total": 4, "supported": 4, "actionable": 3,
                             "blocked": 0, "headings": 1}, {},
                            "2026-11-05T00:00:00Z")
        lines = details_analysis_lines(entry)
        self.assertEqual(lines,
                         [("Entry analysis", "3 entries of 4 records")])

    def test_the_ok_entry_adds_the_top_blocked_reasons(self):
        lines = details_analysis_lines(_ok("a" * 64))
        self.assertEqual(lines, [
            ("Entry analysis", "2 entries (3 blocked) of 6 records"),
            ("Top blocked reasons", "r-one × 2, r-two × 1"),
        ])


# ---------------------------------------------------------------------
# the background worker
# ---------------------------------------------------------------------

class _FakeApp:
    def __init__(self, state_home: str):
        self.folder = state_home
        self.analysis_store = AnalysisStore(state_home)
        self.analysis_worker = None


def _wait_results(worker: AnalysisWorker, count: int, timeout: float = 5.0):
    got = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        got.extend(worker.drain_results())
        if len(got) >= count:
            return got
        time.sleep(0.01)
    return got


class AnalysisWorkerTests(unittest.TestCase):
    """MT-24 (0.32): one daemon thread, bounded queue, named results."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.app = _FakeApp(self.temporary.name)
        self.shas = {}

    def _worker(self, compiler):
        worker = AnalysisWorker(self.app, compiler=compiler)
        self.addCleanup(worker.stop)
        return worker

    def test_success_writes_the_ok_entry_and_drains(self):
        def compiler(relative_path, process_name):
            return _plan("a" * 64, _entries())
        worker = self._worker(compiler)
        worker.start()
        self.assertTrue(worker.enqueue("a.ct", "a" * 64, "GameA.exe"))
        got = _wait_results(worker, 1)
        self.assertEqual(got, ["a" * 64])
        entry = self.app.analysis_store.get("a" * 64)
        self.assertEqual(entry["status"], "ok")
        self.assertEqual(entry["counts"],
                         {"total": 6, "supported": 3, "actionable": 2,
                          "blocked": 3, "headings": 1})
        self.assertEqual(entry["blocked_reasons"],
                         {"r-one": 2, "r-two": 1})

    def test_a_compile_failure_is_a_named_failed_entry(self):
        def compiler(relative_path, process_name):
            raise ValueError("boom")
        worker = self._worker(compiler)
        worker.start()
        worker.enqueue("a.ct", "a" * 64, "GameA.exe")
        _wait_results(worker, 1)
        entry = self.app.analysis_store.get("a" * 64)
        self.assertEqual(entry["status"], "failed")
        self.assertEqual(entry["error"], "ValueError: boom")

    def test_a_sha_mismatch_is_a_failed_entry(self):
        def compiler(relative_path, process_name):
            return _plan("b" * 64, _entries())
        worker = self._worker(compiler)
        worker.start()
        worker.enqueue("a.ct", "a" * 64, "GameA.exe")
        _wait_results(worker, 1)
        entry = self.app.analysis_store.get("a" * 64)
        self.assertEqual(entry["status"], "failed")
        self.assertEqual(entry["error"], "table-changed-during-analysis")

    def test_dedupe_by_content_sha(self):
        def compiler(relative_path, process_name):
            time.sleep(0.05)
            return _plan("a" * 64, [])
        worker = self._worker(compiler)
        worker.start()
        self.assertTrue(worker.enqueue("a.ct", "a" * 64, "GameA.exe"))
        self.assertFalse(worker.enqueue("b.ct", "a" * 64, "GameB.exe"))
        got = _wait_results(worker, 1)
        self.assertEqual(got, ["a" * 64])
        self.assertEqual(worker.pending_count(), 0)

    def test_the_queue_is_bounded(self):
        gate = threading.Event()

        def compiler(relative_path, process_name):
            gate.wait(timeout=10)
            return _plan(self.shas[relative_path], [])
        for i in range(QUEUE_LIMIT + 1):
            rel = "t-%03d.ct" % i
            self.shas[rel] = "c%063d" % i
        worker = self._worker(compiler)
        for i in range(QUEUE_LIMIT):
            self.assertTrue(worker.enqueue("t-%03d.ct" % i,
                                           "c%063d" % i, "GameA.exe"))
        # The (QUEUE_LIMIT + 1)-th item is a named drop.
        self.assertFalse(worker.enqueue("t-%03d.ct" % QUEUE_LIMIT,
                                        "c%063d" % QUEUE_LIMIT,
                                        "GameA.exe"))
        self.assertEqual(worker.pending_count(), QUEUE_LIMIT)
        worker.start()
        gate.set()
        got = _wait_results(worker, QUEUE_LIMIT, timeout=20.0)
        self.assertEqual(len(got), QUEUE_LIMIT)
        self.assertEqual(worker.pending_count(), 0)
        self.assertEqual(len(self.app.analysis_store.document()["tables"]),
                         QUEUE_LIMIT)
        # The dropped table was never analyzed.
        self.assertIsNone(self.app.analysis_store.get(
            "c%063d" % QUEUE_LIMIT))

    def test_pause_holds_the_queue_and_resume_processes_it(self):
        def compiler(relative_path, process_name):
            return _plan(self.shas[relative_path], [])
        worker = self._worker(compiler)
        worker.pause()
        worker.start()
        self.assertTrue(worker.enqueue("a.ct", "a" * 64, "GameA.exe"))
        self.assertTrue(worker.enqueue("b.ct", "b" * 64, "GameB.exe"))
        # While paused: nothing runs.
        time.sleep(0.1)
        self.assertIsNone(self.app.analysis_store.get("a" * 64))
        self.assertIsNone(self.app.analysis_store.get("b" * 64))
        self.assertEqual(worker.pending_count(), 2)
        worker.resume()
        got = _wait_results(worker, 2)
        self.assertEqual(sorted(got), ["a" * 64, "b" * 64])
        self.assertFalse(worker.paused)

    def test_stop_terminates_the_thread_and_refuses_new_items(self):
        gate = threading.Event()

        def compiler(relative_path, process_name):
            gate.wait(timeout=10)
            return _plan("a" * 64, [])
        worker = self._worker(compiler)
        worker.start()
        worker.enqueue("a.ct", "a" * 64, "GameA.exe")
        # The in-flight compile finishes (the stop joins it).
        gate.set()
        _wait_results(worker, 1)
        worker.stop()
        self.assertFalse(worker._thread.is_alive())
        # A re-queued item is refused, not lost: the table stays
        # pending for the next waiting-view build.
        self.assertFalse(worker.enqueue("b.ct", "b" * 64, "GameB.exe"))

    def test_pending_count_counts_queued_and_in_flight(self):
        gate = threading.Event()

        def compiler(relative_path, process_name):
            gate.wait(timeout=10)
            return _plan("a" * 64, [])
        worker = self._worker(compiler)
        worker.start()
        worker.enqueue("a.ct", "a" * 64, "GameA.exe")
        deadline = time.monotonic() + 5.0
        while worker.pending_count() != 1 and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(worker.pending_count(), 1)
        gate.set()
        _wait_results(worker, 1)
        self.assertEqual(worker.pending_count(), 0)

    def test_active_workers_tracks_the_lifecycle(self):
        # MT-24 (0.32): the live-worker set reflects the worker while its
        # thread runs - the process-wide teardown (tests/native_tk_teardown
        # force_root_release) stops every live worker in one bounded pass,
        # so a window test that never calls close() leaks no worker.
        def compiler(relative_path, process_name):
            return _plan("a" * 64, [])
        worker = self._worker(compiler)
        self.assertNotIn(worker, active_workers())
        worker.start()
        deadline = time.monotonic() + 5.0
        while worker not in active_workers() \
                and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertIn(worker, active_workers())
        # An idempotent restart does not double-register.
        worker.start()
        self.assertEqual([w for w in active_workers() if w is worker],
                         [worker])
        worker.stop()
        self.assertFalse(worker._thread.is_alive())
        self.assertNotIn(worker, active_workers())


if __name__ == "__main__":
    unittest.main()
