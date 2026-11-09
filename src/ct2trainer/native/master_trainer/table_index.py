"""Incremental table index for the Master Trainer folder.

The index maps every ``.ct`` table under one root folder (recursively) to
its process-name candidates, so the Master Trainer can answer "which
tables bind to process X" from the index without re-reading unchanged
tables.  This module is pure standard library and platform independent.

Incremental contract:

- A directory listing (``os.walk``) is the only filesystem work on an
  unchanged tree; unchanged entries are kept from the stored index.
- An entry is refreshed only when its ``(size, st_mtime_ns)`` pair
  changed.  A content-identical refresh (same sha256) keeps the derived
  process names and only moves the fingerprint fields.
- A removed path drops its entry; a new path gets a full read.
- A file that cannot be read or parsed is kept as a visible
  ``unreadable`` entry with a named error; it never fails the scan and
  never binds a process name.
- Only the exact ``.ct`` extension (case-insensitive) is admitted;
  anything else in the tree is ignored.

The persistence document is canonical JSON with a sha256 checksum over
the canonical payload (same discipline as the trainer state store);
load refuses foreign roots, foreign schemas and tampered checksums
instead of guessing.

MT-26 (0.34): the Master Trainer can index several table folders at
once.  Each root still owns one :class:`TableIndex` (the incremental
contract above is unchanged per root); a :class:`RootIndexSet` orders
the per-root indexes in user order and exposes one merged surface over
them.  Every :class:`TableEntry` additionally carries the root it was
indexed under, so a table is identifiable across roots by its absolute
path key (:func:`table_key`).  The per-root single document stays
schema 1 (the schema-1 load/save functions are kept for per-root use
and for promotion); the merged document is schema 2 (an ordered array
of ``{root, entries}`` blocks that preserves the user's folder order).
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path

INDEX_SCHEMA = 1
INDEX_SET_SCHEMA = 2
INDEX_FILENAME = "tables-index.json"
MAX_INDEX_BYTES = 32 * 1024 * 1024
_MAX_TEXT = 512

CT_SUFFIXES = {".ct"}


class TableIndexError(ValueError):
    """Structural or contract problem with a table-index document."""


class TableIndexRefusal(TableIndexError):
    """A stored index that is refused for the current root.

    Carries the displayable refusal reasons; callers must surface them
    and may fall back to a full rebuild (documented, never silent).
    """

    def __init__(self, reasons: list[str]):
        super().__init__("; ".join(reasons))
        self.reasons = tuple(reasons)


@dataclass(frozen=True)
class TableEntry:
    """One indexed table under the root folder."""

    relative_path: str          # '/'-separated, portable
    size: int
    mtime_ns: int
    sha256: str
    process_names: tuple[str, ...]   # original spelling, first-seen, deduped
    status: str               # 'ok' | 'unreadable'
    detail: str | None        # named error for unreadable entries
    # MT-26 (0.34): the resolved index root this entry was found under
    # ("" for legacy / root-less entries - single-root documents and
    # test fixtures keep working unchanged; the table key then falls
    # back to the relative path).
    root: str = ""


def table_key(entry: "TableEntry") -> str:
    """MT-26 (0.34): the global identity key of one indexed table.

    When the entry carries its index root, the key is the absolute path
    (root joined with the relative path, native separators); otherwise
    the relative path is used as-is (legacy single-root documents,
    root-less fixtures and duck-typed test stand-ins).  All comparisons
    on the key are casefolded by the callers; the key itself is never
    modified.
    """
    root = getattr(entry, "root", "") or ""
    if not root:
        return entry.relative_path
    return str(Path(root) / entry.relative_path)


@dataclass(frozen=True)
class IndexChange:
    """One reconciliation decision for a path (test and UI evidence)."""

    kind: str                 # 'added' | 'changed' | 'unchanged' | 'removed'
    relative_path: str
    detail: str | None = None


@dataclass(frozen=True)
class ReconcileResult:
    """Outcome of one reconcile pass over the root folder."""

    index: "TableIndex"
    changes: tuple[IndexChange, ...]
    scan_error: str | None = None


class TableIndex:
    """The in-memory index for one root folder."""

    def __init__(self, root: str, entries: dict[str, TableEntry]):
        self.root = root
        self.entries = entries

    # -- lookups -------------------------------------------------------------

    def get(self, relative_path: str) -> TableEntry | None:
        return self.entries.get(relative_path)

    def tables(self) -> list[TableEntry]:
        return sorted(self.entries.values(),
                      key=lambda e: (e.relative_path.casefold(), e.relative_path))

    def process_names(self) -> list[str]:
        """Distinct bound process names, original spelling, stable order."""
        seen: dict[str, str] = {}
        for entry in self.entries.values():
            for name in entry.process_names:
                seen.setdefault(name.casefold(), name)
        return [seen[key] for key in sorted(seen)]

    def process_name_set(self) -> set[str]:
        names = set()
        for entry in self.entries.values():
            names.update(name.casefold() for name in entry.process_names)
        return names

    def entries_for_process(self, name: str) -> list[TableEntry]:
        """All ok-status entries that bind to the process name.

        Uses the same ordinal comparison as the process finder for the
        common ASCII case; non-ASCII uses casefold on every platform
        (the attach authority re-proves identity later either way).
        """
        key = name.casefold()
        hits = [entry for entry in self.entries.values()
                if entry.status == "ok"
                and key in set(n.casefold() for n in entry.process_names)]
        return sorted(hits, key=lambda e: (e.relative_path.casefold(), e.relative_path))

    def get_by_key(self, key: str) -> TableEntry | None:
        """MT-26 (0.34): resolve one entry by its table key.

        The key is matched casefolded; within one root the absolute key
        is unique, so at most one entry ever matches.  Entries without a
        stored root use their relative path as the key.  A relative-path
        lookup is accepted as a documented fallback (single-root callers
        that pass the relative path while the entries carry their index
        root).
        """
        if not key:
            return None
        target = key.casefold()
        for entry in self.entries.values():
            if table_key(entry).casefold() == target:
                return entry
        for entry in self.entries.values():
            if entry.relative_path.casefold() == target:
                return entry
        return None


class RootIndexSet:
    """MT-26 (0.34): the ordered set of per-root table indexes.

    The Master Trainer indexes several table folders at once; the set
    keeps one :class:`TableIndex` per root in user order (the first
    root is the primary folder) and exposes one merged surface over all
    roots: ``tables()`` / ``process_names()`` / ``process_name_set()`` /
    ``entries_for_process()`` / ``get()`` / ``get_by_key()``.  Entries
    from different roots may share the same relative path; the merged
    surface distinguishes them by the absolute table key
    (:func:`table_key`).  The per-root incremental reconcile contract
    (``reconcile``) is unchanged - the set only orders and merges.
    """

    def __init__(self, indexes: list[TableIndex] | None = None):
        self._indexes: list[TableIndex] = list(indexes or [])

    # -- root lifecycle --------------------------------------------------------

    def roots(self) -> list[str]:
        """The index roots in user order (first = primary)."""
        return [index.root for index in self._indexes]

    def index_for_root(self, root: str) -> TableIndex | None:
        """The per-root index for one root (casefolded match) or None."""
        target = root.casefold()
        for index in self._indexes:
            if index.root.casefold() == target:
                return index
        return None

    def add_root(self, index: TableIndex) -> bool:
        """Append one per-root index; True when it was added.

        Adding a root that already exists (casefolded) is a no-op.
        """
        if self.index_for_root(index.root) is not None:
            return False
        self._indexes.append(index)
        return True

    def remove_root(self, root: str) -> bool:
        """Remove one root; True when it was present (empty set allowed)."""
        target = root.casefold()
        for pos, index in enumerate(self._indexes):
            if index.root.casefold() == target:
                del self._indexes[pos]
                return True
        return False

    def move_front(self, root: str) -> bool:
        """Move one root to the front (primary); True when found."""
        target = root.casefold()
        for pos, index in enumerate(self._indexes):
            if index.root.casefold() == target:
                self._indexes.insert(0, self._indexes.pop(pos))
                return True
        return False

    @property
    def indexes(self) -> list[TableIndex]:
        """A copy of the ordered per-root indexes."""
        return list(self._indexes)

    # -- merged surface ----------------------------------------------------------

    def tables(self) -> list[TableEntry]:
        """Every entry, root order first, per-root path order inside."""
        entries: list[TableEntry] = []
        for index in self._indexes:
            entries.extend(index.tables())
        return entries

    def process_names(self) -> list[str]:
        """Distinct bound process names over all roots, stable order."""
        seen: dict[str, str] = {}
        for index in self._indexes:
            for name in index.process_names():
                seen.setdefault(name.casefold(), name)
        return [seen[key] for key in sorted(seen)]

    def process_name_set(self) -> set[str]:
        names: set[str] = set()
        for index in self._indexes:
            names |= index.process_name_set()
        return names

    def entries_for_process(self, name: str) -> list[TableEntry]:
        """All ok-status entries over all roots that bind to the name."""
        hits: list[TableEntry] = []
        for index in self._indexes:
            hits.extend(index.entries_for_process(name))
        return hits

    def get(self, relative_path: str) -> TableEntry | None:
        """First entry with the relative path in root order (or None)."""
        for index in self._indexes:
            entry = index.get(relative_path)
            if entry is not None:
                return entry
        return None

    def get_by_key(self, key: str) -> TableEntry | None:
        """Resolve one entry by its absolute table key (or None)."""
        for index in self._indexes:
            entry = index.get_by_key(key)
            if entry is not None:
                return entry
        return None

    # -- compatibility surface ---------------------------------------------------
    # The merged document is addressed by table key everywhere; the two
    # attributes below keep the single-root surface of TableIndex working
    # (relative-path entries dict + the root string) so existing callers
    # and tests stay unchanged.  In a multi-root set the entries dict is
    # merged by relative path, first root in user order wins a collision
    # (the global identity stays the absolute table key).

    @property
    def root(self) -> str:
        """The primary (first) index root; "" for an empty set."""
        return self._indexes[0].root if self._indexes else ""

    @property
    def entries(self) -> dict[str, TableEntry]:
        """Merged relative-path -> entry dict (first root wins)."""
        merged: dict[str, TableEntry] = {}
        for index in self._indexes:
            for relative, entry in index.entries.items():
                merged.setdefault(relative, entry)
        return merged


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _fingerprint(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns


def iter_ct_files(root: Path) -> list[Path]:
    """Every ``.ct`` file under root, deterministic order."""
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort(key=lambda d: d.casefold())
        for name in sorted(filenames, key=lambda n: n.casefold()):
            path = Path(dirpath) / name
            if Path(name).suffix.lower() in CT_SUFFIXES:
                found.append(path)
    return found


def _derive_names(data: bytes) -> tuple[str, ...]:
    """Process-name candidates from raw table bytes (main-branch library).

    The CT heuristic names every distinct EXE token it can find in the
    source; the Master Trainer binds a table to all of its candidates
    (a single running process is the compile-time authority, so a
    multi-name table simply loads against the one that is running).
    """
    from ..process_detect import find_candidates
    return tuple(find_candidates(data))


def _read_and_hash(path: Path) -> tuple[str, bytes | None, str, str | None]:
    """Read-only fast path of one table: (sha256, raw bytes, status, detail).

    Only files whose (size, mtime_ns) fingerprint changed reach this step.
    The content hash is computed here; process-name derivation happens in
    :func:`_parse_names` and is skipped entirely when the stored content
    hash still matches (identical bytes cannot yield different names).
    """
    from ...table import MAX_TABLE_BYTES
    try:
        data = path.read_bytes()
    except OSError as exc:
        return "", None, "unreadable", f"read failed: {exc}"
    if not data:
        return hashlib.sha256(data).hexdigest(), None, "unreadable", "empty file"
    if len(data) > MAX_TABLE_BYTES:
        return hashlib.sha256(data).hexdigest(), None, "unreadable", \
            f"table exceeds the {MAX_TABLE_BYTES}-byte limit"
    return hashlib.sha256(data).hexdigest(), data, "ok", None


def _parse_names(path: Path, data: bytes, sha: str) -> tuple[tuple[str, ...], str, str | None]:
    """Derive the bound process names from one freshly read table.

    Reuses the tested table parser so legacy-binary CTs contribute their
    converted document (module name, AOB module tokens) exactly like
    XML tables; raw bytes are the fallback for parseable-but-conversion
    sources.  A parse refusal is a named unreadable entry, not a scan
    failure.
    """
    from ...table import TableError, read_table
    try:
        table = read_table(path)
    except (TableError, OSError, ValueError) as exc:
        return (), "unreadable", f"parse failed: {exc.__class__.__name__}: {exc}"
    if table.source_sha256 != sha:
        return (), "unreadable", "table changed during analysis"
    source = table.converted_xml if table.converted_xml is not None else data
    return _derive_names(source), "ok", None


def reconcile(root: str | Path, index: TableIndex | None,
              ) -> ReconcileResult:
    """Incrementally reconcile the stored index with the root folder.

    The folder is always listed; only changed/added/unreadable tables are
    re-read.  ``scan_error`` names a root-level failure (missing or
    unreadable root); per-file failures stay visible as unreadable
    entries.
    """
    root_path = Path(root).expanduser().resolve()
    if not root_path.is_dir():
        keep = index if (index is not None and index.root == str(root_path)) \
            else TableIndex(str(root_path), {})
        return ReconcileResult(keep, (),
                               scan_error=f"root folder is missing or not a directory: {root_path}")
    prior_root = str(root_path)
    if index is None or index.root != prior_root:
        # Foreign or absent index: start from an empty entry set while
        # still using the stored document for nothing (a full rebuild).
        index = TableIndex(prior_root, {})
    prior = index.entries
    changes: list[IndexChange] = []
    entries: dict[str, TableEntry] = {}
    live_paths = set()
    for path in iter_ct_files(root_path):
        rel = _relative(root_path, path)
        live_paths.add(rel)
        try:
            size, mtime_ns = _fingerprint(path)
        except OSError as exc:
            old = prior.get(rel)
            if old is not None:
                entries[rel] = old
                changes.append(IndexChange("unchanged", rel))
            continue
        old = prior.get(rel)
        if old is not None and old.size == size and old.mtime_ns == mtime_ns:
            entries[rel] = old
            changes.append(IndexChange("unchanged", rel))
            continue
        sha, data, status, detail = _read_and_hash(path)
        kind = "added" if old is None else "changed"
        if status != "ok":
            if (old is not None and old.sha256 == sha
                    and old.status == status and old.detail == detail):
                # Identical unreadable content: fingerprint-only change.
                entries[rel] = old
                changes.append(IndexChange("unchanged", rel))
                continue
            entry = TableEntry(rel, size, mtime_ns, sha, (), status, detail,
                               root=prior_root)
            entries[rel] = entry
            changes.append(IndexChange(kind, rel, detail))
            continue
        if old is not None and old.sha256 == sha:
            # Content unchanged (only the fingerprint moved): the content
            # hash is the authority, so identical bytes keep the derived
            # names; no re-parse, no name re-derivation.
            entries[rel] = TableEntry(rel, size, mtime_ns, sha,
                                      old.process_names, "ok", None,
                                      root=prior_root)
            changes.append(IndexChange("unchanged", rel))
            continue
        names, status, detail = _parse_names(path, data, sha)
        entry = TableEntry(rel, size, mtime_ns, sha, names, status,
                           detail if status != "ok" else None,
                           root=prior_root)
        entries[rel] = entry
        changes.append(IndexChange(kind, rel,
                                   detail if status != "ok" else None))
    for rel in sorted(prior, key=str.casefold):
        if rel not in live_paths:
            changes.append(IndexChange("removed", rel))
    return ReconcileResult(TableIndex(prior_root, entries), tuple(changes))


# -- persistence -------------------------------------------------------------

def _canonical_payload(index: TableIndex) -> dict:
    return {
        "schema": INDEX_SCHEMA,
        "root": index.root,
        "entries": {
            relative: {
                "size": entry.size,
                "mtime_ns": entry.mtime_ns,
                "sha256": entry.sha256,
                "process_names": list(entry.process_names),
                "status": entry.status,
                "detail": entry.detail,
            }
            for relative, entry in sorted(index.entries.items(),
                                          key=lambda item: item[0].casefold())
        },
    }


def index_to_bytes(index: TableIndex) -> bytes:
    payload = _canonical_payload(index)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                           allow_nan=False, ensure_ascii=True).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    return json.dumps({"payload": payload, "sha256": digest},
                      sort_keys=True, separators=(",", ":"),
                      allow_nan=False, ensure_ascii=True).encode("utf-8") + b"\n"


def _strict_object(raw: bytes) -> dict:
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise TableIndexRefusal(["index document is not valid JSON"]) from exc
    if not isinstance(value, dict) or set(value) != {"payload", "sha256"}:
        raise TableIndexRefusal(["index document shape is invalid"])
    return value


def index_from_bytes(raw: bytes) -> TableIndex:
    document = _strict_object(raw)
    payload = document["payload"]
    if not isinstance(payload, dict):
        raise TableIndexRefusal(["index payload is not an object"])
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                           allow_nan=False, ensure_ascii=True).encode("utf-8")
    if hashlib.sha256(canonical).hexdigest() != document.get("sha256"):
        raise TableIndexRefusal(["index checksum does not match"])
    schema = payload.get("schema")
    if type(schema) is not int or schema != INDEX_SCHEMA:
        raise TableIndexRefusal([f"index schema {schema!r} is not supported "
                                 f"(expected {INDEX_SCHEMA})"])
    root = payload.get("root")
    if not isinstance(root, str) or not root:
        raise TableIndexRefusal(["index root is missing"])
    raw_entries = payload.get("entries")
    if not isinstance(raw_entries, dict):
        raise TableIndexRefusal(["index entries are invalid"])
    entries: dict[str, TableEntry] = {}
    for relative, item in raw_entries.items():
        if not isinstance(relative, str) or not relative or not isinstance(item, dict):
            raise TableIndexRefusal([f"index entry {relative!r} is malformed"])
        size = item.get("size")
        mtime_ns = item.get("mtime_ns")
        sha = item.get("sha256")
        status = item.get("status")
        detail = item.get("detail")
        names_raw = item.get("process_names")
        if type(size) is not int or size < 0 or type(mtime_ns) is not int or mtime_ns < 0:
            raise TableIndexRefusal([f"entry {relative!r} fingerprint is malformed"])
        if not isinstance(sha, str) or len(sha) != 64:
            raise TableIndexRefusal([f"entry {relative!r} sha256 is malformed"])
        if status not in ("ok", "unreadable"):
            raise TableIndexRefusal([f"entry {relative!r} status is unknown"])
        if detail is not None and (not isinstance(detail, str) or len(detail) > _MAX_TEXT):
            raise TableIndexRefusal([f"entry {relative!r} detail is malformed"])
        if not isinstance(names_raw, list):
            raise TableIndexRefusal([f"entry {relative!r} process names are malformed"])
        names: list[str] = []
        seen: set[str] = set()
        for name in names_raw:
            if not isinstance(name, str) or not name or len(name) > 255:
                raise TableIndexRefusal([f"entry {relative!r} carries a bad process name"])
            key = name.casefold()
            if key not in seen:
                seen.add(key)
                names.append(name)
        entries[relative] = TableEntry(relative, size, mtime_ns, sha,
                                       tuple(names), status, detail,
                                       root=root)
    return TableIndex(root, entries)


def load_index(path: str | Path) -> TableIndex:
    """Load a stored index; size-bounded, strict, checksum-bound."""
    raw = Path(path).read_bytes()
    if len(raw) > MAX_INDEX_BYTES:
        raise TableIndexRefusal(["index file exceeds its size limit"])
    return index_from_bytes(raw)


def save_index(index: TableIndex, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(index_to_bytes(index))


# -- MT-26 (0.34) multi-root set persistence ----------------------------------

def _canonical_set_payload(index_set: "RootIndexSet") -> dict:
    """Schema-2 payload: the per-root blocks in user order (array)."""
    roots = []
    for index in index_set.indexes:
        blocks = [
            {
                "root": index.root,
                "entries": {
                    relative: {
                        "size": entry.size,
                        "mtime_ns": entry.mtime_ns,
                        "sha256": entry.sha256,
                        "process_names": list(entry.process_names),
                        "status": entry.status,
                        "detail": entry.detail,
                    }
                    for relative, entry in sorted(
                        index.entries.items(),
                        key=lambda item: item[0].casefold())
                },
            }
        ]
        roots.extend(blocks)
    return {"schema": INDEX_SET_SCHEMA, "roots": roots}


def index_set_to_bytes(index_set: "RootIndexSet") -> bytes:
    payload = _canonical_set_payload(index_set)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                           allow_nan=False, ensure_ascii=True).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    return json.dumps({"payload": payload, "sha256": digest},
                      sort_keys=True, separators=(",", ":"),
                      allow_nan=False, ensure_ascii=True).encode("utf-8") \
        + b"\n"


def _entry_from_item(relative: str, item: dict, root: str) -> TableEntry:
    """Strict entry decode shared by the schema-1 and schema-2 loaders."""
    size = item.get("size")
    mtime_ns = item.get("mtime_ns")
    sha = item.get("sha256")
    status = item.get("status")
    detail = item.get("detail")
    names_raw = item.get("process_names")
    if type(size) is not int or size < 0 or type(mtime_ns) is not int or mtime_ns < 0:
        raise TableIndexRefusal([f"entry {relative!r} fingerprint is malformed"])
    if not isinstance(sha, str) or len(sha) != 64:
        raise TableIndexRefusal([f"entry {relative!r} sha256 is malformed"])
    if status not in ("ok", "unreadable"):
        raise TableIndexRefusal([f"entry {relative!r} status is unknown"])
    if detail is not None and (not isinstance(detail, str) or len(detail) > _MAX_TEXT):
        raise TableIndexRefusal([f"entry {relative!r} detail is malformed"])
    if not isinstance(names_raw, list):
        raise TableIndexRefusal([f"entry {relative!r} process names are malformed"])
    names: list[str] = []
    seen: set[str] = set()
    for name in names_raw:
        if not isinstance(name, str) or not name or len(name) > 255:
            raise TableIndexRefusal([f"entry {relative!r} carries a bad process name"])
        key = name.casefold()
        if key not in seen:
            seen.add(key)
            names.append(name)
    return TableEntry(relative, size, mtime_ns, sha, tuple(names), status,
                      detail, root=root)


def index_set_from_bytes(raw: bytes) -> "RootIndexSet":
    """Strict, checksum-bound load of the schema-2 multi-root document.

    A schema-1 single-root document is promoted to a one-root set (the
    documented upgrade path); a foreign schema, malformed shape, a
    tampered checksum or an invalid root / entry is refused with a named
    reason.
    """
    document = _strict_object(raw)
    payload = document["payload"]
    if not isinstance(payload, dict):
        raise TableIndexRefusal(["index payload is not an object"])
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                           allow_nan=False, ensure_ascii=True).encode("utf-8")
    if hashlib.sha256(canonical).hexdigest() != document.get("sha256"):
        raise TableIndexRefusal(["index checksum does not match"])
    schema = payload.get("schema")
    if type(schema) is not int:
        raise TableIndexRefusal(["index schema is not an integer"])

    if schema == INDEX_SET_SCHEMA:
        raw_roots = payload.get("roots")
        if not isinstance(raw_roots, list):
            raise TableIndexRefusal(["index set roots are invalid"])
        indexes: list[TableIndex] = []
        seen_roots: set[str] = set()
        for block in raw_roots:
            if not isinstance(block, dict) \
                    or set(block) != {"root", "entries"}:
                raise TableIndexRefusal(
                    ["index set root block is malformed"])
            root = block.get("root")
            if not isinstance(root, str) or not root:
                raise TableIndexRefusal(["index set root is missing"])
            key = root.casefold()
            if key in seen_roots:
                raise TableIndexRefusal(
                    ["index set carries a duplicate root"])
            seen_roots.add(key)
            raw_entries = block.get("entries")
            if not isinstance(raw_entries, dict):
                raise TableIndexRefusal(
                    [f"root {root!r} entries are invalid"])
            entries: dict[str, TableEntry] = {}
            for relative, item in raw_entries.items():
                if not isinstance(relative, str) or not relative \
                        or not isinstance(item, dict):
                    raise TableIndexRefusal(
                        [f"index entry {relative!r} is malformed"])
                entries[relative] = _entry_from_item(relative, item, root)
            indexes.append(TableIndex(root, entries))
        return RootIndexSet(indexes)

    if schema == INDEX_SCHEMA:
        root = payload.get("root")
        if not isinstance(root, str) or not root:
            raise TableIndexRefusal(["index root is missing"])
        raw_entries = payload.get("entries")
        if not isinstance(raw_entries, dict):
            raise TableIndexRefusal(["index entries are invalid"])
        entries: dict[str, TableEntry] = {}
        for relative, item in raw_entries.items():
            if not isinstance(relative, str) or not relative \
                    or not isinstance(item, dict):
                raise TableIndexRefusal(
                    [f"index entry {relative!r} is malformed"])
            entries[relative] = _entry_from_item(relative, item, root)
        return RootIndexSet([TableIndex(root, entries)])

    raise TableIndexRefusal([f"index schema {schema!r} is not supported "
                             f"(expected {INDEX_SET_SCHEMA}, legacy "
                             f"{INDEX_SCHEMA} is promoted)"])


def load_index_set(path: str | Path) -> "RootIndexSet":
    """Load the stored multi-root set; size-bounded, strict."""
    raw = Path(path).read_bytes()
    if len(raw) > MAX_INDEX_BYTES:
        raise TableIndexRefusal(["index file exceeds its size limit"])
    return index_set_from_bytes(raw)


def save_index_set(index_set: "RootIndexSet", path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(index_set_to_bytes(index_set))
