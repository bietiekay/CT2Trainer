"""Master Trainer state document (last-used folder, preferences).

The state home holds one small document, ``master-settings.json``, next to
the tables index.  Schema 4 (0.27) carries:

- ``last_folder``  - the last-used table folder ("ask on first start");
- ``last_table``   - the last explicitly loaded table (MT-10), relative
  path within the table folder;
- ``attach_mode``  - "auto" (never asks; the documented smallest-PID rule)
  or "ask" (the user always picks the target process, MT-11);
- ``recent_tables``- the rolling recently loaded tables (MT-15): most
  recent first, capped at ``RECENT_TABLES_LIMIT``, each item the relative
  path plus the UTC load timestamp (``YYYY-MM-DDTHH:MM:SSZ``);
- ``view_filter``  - the persisted waiting-view filter query (MT-16):
  the MT-13 filter entry text ("" means no filter), at most
  ``VIEW_FILTER_MAX`` characters;
- ``view_sort``    - the persisted waiting-view sort mode (MT-16): one of
  :data:`VIEW_SORT_MODES` (mirrors ``table_filter.SORT_MODES``);
- ``view_mode``    - the persisted waiting-view display mode (MT-16 /
  MT-17): one of :data:`VIEW_MODES` ("list" flat rows, "process"
  grouped by bound process name).

Schema 3 (0.26) documents carry the first five fields; schema 2 (0.25)
documents the first three; schema 1 documents (last_folder only) are
schema-2 ancestors.  All are promoted on load: the missing fields take
their documented defaults (last_table=None, attach_mode "auto",
recent_tables=[], view_filter "", view_sort "name", view_mode "list"),
so existing state homes keep working unchanged.  A schema-3 document
carrying a view_* field is refused as an unknown field (foreign schema,
never silently promoted).

Persistence discipline mirrors the table index (``table_index.py``):
canonical JSON payload with a sha256 checksum envelope, strict size bound,
refused foreign schemas, malformed documents and tampered checksums
instead of guessing.  A refused document is treated by the caller as "no
stored state" (a fresh first start), never as a silent reset.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

MASTER_STATE_SCHEMA = 4
MASTER_STATE_SCHEMA_PREVIOUS = 3
MASTER_STATE_SCHEMA_PREVIOUS2 = 2
MASTER_STATE_SCHEMA_LEGACY = 1
MASTER_STATE_FILENAME = "master-settings.json"
MAX_MASTER_STATE_BYTES = 1024 * 1024
ATTACH_MODE_AUTO = "auto"
ATTACH_MODE_ASK = "ask"
ATTACH_MODES = (ATTACH_MODE_AUTO, ATTACH_MODE_ASK)
RECENT_TABLES_LIMIT = 10
# MT-16 (0.27): format-level constants for the persisted waiting-view
# settings.  They mirror ``table_filter.SORT_MODES`` / ``VIEW_MODES``
# (the attach-mode pattern) and must stay in sync with them.
VIEW_SORT_MODES = ("name", "process", "status")
VIEW_MODES = ("list", "process")
VIEW_FILTER_MAX = 200
_MAX_FOLDER = 4096
_MAX_TABLE_PATH = 4096
_MAX_RECENT_TIMESTAMP = 20


def _utc_timestamp_ok(value) -> bool:
    """True for the persisted UTC load timestamp format."""
    if not isinstance(value, str) or len(value) > _MAX_RECENT_TIMESTAMP:
        return False
    if len(value) != 20 or value.endswith("Z") is False:
        return False
    import re
    return re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value) is not None


class MasterStateRefusal(ValueError):
    """A stored master-state document that is refused.

    ``reasons`` is the displayable refusal list; callers surface it and fall
    back to a fresh first start (picker), never a silent guess.
    """

    def __init__(self, reasons: list[str]):
        super().__init__("; ".join(reasons))
        self.reasons = tuple(reasons)


@dataclass(frozen=True)
class MasterState:
    """One master-state document (schema-bound).

    Only schema-4 documents may be written; schemas 1-3 are load-only
    (promoted on load, see the module docstring).
    """

    schema: int
    last_folder: str | None
    last_table: str | None = None
    attach_mode: str = ATTACH_MODE_AUTO
    recent_tables: tuple[tuple[str, str], ...] = ()
    view_filter: str = ""
    view_sort: str = VIEW_SORT_MODES[0]
    view_mode: str = VIEW_MODES[0]


def empty_master_state() -> MasterState:
    return MasterState(schema=MASTER_STATE_SCHEMA, last_folder=None,
                       last_table=None, attach_mode=ATTACH_MODE_AUTO,
                       recent_tables=())


def _validate_state_dict(payload: dict) -> MasterState:
    reasons: list[str] = []
    schema = payload.get("schema")
    if type(schema) is not int or schema not in (
            MASTER_STATE_SCHEMA, MASTER_STATE_SCHEMA_PREVIOUS,
            MASTER_STATE_SCHEMA_PREVIOUS2, MASTER_STATE_SCHEMA_LEGACY):
        reasons.append(f"master-state schema {schema!r} is not supported "
                       f"(expected {MASTER_STATE_SCHEMA}, legacy "
                       f"{MASTER_STATE_SCHEMA_PREVIOUS} / "
                       f"{MASTER_STATE_SCHEMA_PREVIOUS2} / "
                       f"{MASTER_STATE_SCHEMA_LEGACY} are promoted on load)")
    allowed = {"schema", "last_folder"}
    if schema == MASTER_STATE_SCHEMA:
        allowed |= {"last_table", "attach_mode", "recent_tables",
                    "view_filter", "view_sort", "view_mode"}
    elif schema == MASTER_STATE_SCHEMA_PREVIOUS:
        allowed |= {"last_table", "attach_mode", "recent_tables"}
    elif schema == MASTER_STATE_SCHEMA_PREVIOUS2:
        allowed |= {"last_table", "attach_mode"}
    unknown = sorted(set(payload) - allowed)
    if unknown:
        reasons.append("master-state payload carries unknown fields: "
                       + ", ".join(unknown))
    last = payload.get("last_folder", None)
    if last is not None:
        if not isinstance(last, str) or not last:
            reasons.append("last_folder must be a non-empty string or null")
        elif len(last) > _MAX_FOLDER:
            reasons.append("last_folder exceeds its length bound")
    last_table = payload.get("last_table")
    if last_table is not None:
        if type(last_table) is not str or not last_table:
            reasons.append("last_table must be a non-empty string or null")
        elif len(last_table) > _MAX_TABLE_PATH:
            reasons.append("last_table exceeds its length bound")
    attach_mode = payload.get("attach_mode", ATTACH_MODE_AUTO)
    if attach_mode not in ATTACH_MODES:
        reasons.append("attach_mode must be one of "
                       + ", ".join(f"'{m}'" for m in ATTACH_MODES)
                       + f" (got {attach_mode!r})")
    recent_raw = payload.get("recent_tables")
    recent: list[tuple[str, str]] = []
    if recent_raw is not None:
        if not isinstance(recent_raw, list):
            reasons.append("recent_tables must be a list of "
                           "{\"path\", \"at\"} objects or absent")
        else:
            if len(recent_raw) > RECENT_TABLES_LIMIT:
                reasons.append("recent_tables exceeds its limit of "
                               + str(RECENT_TABLES_LIMIT) + " entries")
            for item in recent_raw:
                if (not isinstance(item, dict)
                        or set(item) != {"path", "at"}
                        or not isinstance(item.get("path"), str)
                        or not item.get("path")
                        or len(item.get("path", "")) > _MAX_TABLE_PATH
                        or not _utc_timestamp_ok(item.get("at"))):
                    reasons.append("recent_tables carries a malformed "
                                   "entry (need {\"path\": non-empty string, "
                                   "\"at\": UTC timestamp YYYY-MM-DDTHH:MM:SSZ})")
                    break
            if not reasons:
                recent = [(item["path"], item["at"]) for item in recent_raw]
    view_filter = payload.get("view_filter", "")
    if not isinstance(view_filter, str) or len(view_filter) > VIEW_FILTER_MAX:
        reasons.append("view_filter must be a string of at most "
                       + str(VIEW_FILTER_MAX) + " characters")
    view_sort = payload.get("view_sort", VIEW_SORT_MODES[0])
    if view_sort not in VIEW_SORT_MODES:
        reasons.append("view_sort must be one of "
                       + ", ".join(f"'{m}'" for m in VIEW_SORT_MODES)
                       + f" (got {view_sort!r})")
    view_mode = payload.get("view_mode", VIEW_MODES[0])
    if view_mode not in VIEW_MODES:
        reasons.append("view_mode must be one of "
                       + ", ".join(f"'{m}'" for m in VIEW_MODES)
                       + f" (got {view_mode!r})")
    if reasons:
        raise MasterStateRefusal(reasons)
    # Promote older documents (schema 3 / 2 / 1) to the current schema
    # with the documented defaults; the stored document itself stays
    # untouched.  (The per-schema field sets were validated above, so the
    # values are well-formed; the view_* defaults cover schema 3 and
    # older documents, schema 1 only ever carried last_folder.)
    if schema == MASTER_STATE_SCHEMA_LEGACY:
        last_table = None
        attach_mode = ATTACH_MODE_AUTO
    return MasterState(schema=MASTER_STATE_SCHEMA, last_folder=last,
                       last_table=last_table, attach_mode=attach_mode,
                       recent_tables=tuple(recent),
                       view_filter=view_filter, view_sort=view_sort,
                       view_mode=view_mode)


def master_state_to_bytes(state: MasterState) -> bytes:
    """Canonical, deterministic JSON bytes for one master-state document.

    Only the current schema is writable; older documents cannot be
    re-persisted as-is (they are promoted in memory on load).
    """
    if not isinstance(state, MasterState):
        raise MasterStateRefusal(["state must be a MasterState document"])
    if state.schema != MASTER_STATE_SCHEMA:
        raise MasterStateRefusal([f"cannot persist an unsupported "
                                  f"master-state schema {state.schema!r}"])
    _validate_state_dict({"schema": state.schema, "last_folder": state.last_folder,
                          "last_table": state.last_table,
                          "attach_mode": state.attach_mode,
                          "recent_tables": [
                              {"path": path, "at": at}
                              for path, at in state.recent_tables],
                          "view_filter": state.view_filter,
                          "view_sort": state.view_sort,
                          "view_mode": state.view_mode})
    payload = {"schema": state.schema, "last_folder": state.last_folder,
               "last_table": state.last_table, "attach_mode": state.attach_mode,
               "recent_tables": [
                   {"path": path, "at": at}
                   for path, at in state.recent_tables],
               "view_filter": state.view_filter,
               "view_sort": state.view_sort,
               "view_mode": state.view_mode}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                           allow_nan=False, ensure_ascii=True).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    return json.dumps({"payload": payload, "sha256": digest},
                      sort_keys=True, separators=(",", ":"),
                      allow_nan=False, ensure_ascii=True).encode("utf-8") + b"\n"


def master_state_from_bytes(raw: bytes) -> MasterState:
    """Strict, checksum-bound load of one master-state document.

    Schema-1 / 2 / 3 documents are accepted and promoted to the
    current schema (see module docstring); every other foreign
    schema, malformed shape or tampered checksum raises the named
    :class:`MasterStateRefusal`.
    """
    if len(raw) > MAX_MASTER_STATE_BYTES:
        raise MasterStateRefusal(["master-state file exceeds its size limit"])
    try:
        document = json.loads(raw)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise MasterStateRefusal(["master-state document is not valid JSON"]) \
            from exc
    if not isinstance(document, dict) or set(document) != {"payload", "sha256"}:
        raise MasterStateRefusal(["master-state document shape is invalid"])
    payload = document["payload"]
    if not isinstance(payload, dict):
        raise MasterStateRefusal(["master-state payload is not an object"])
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                           allow_nan=False, ensure_ascii=True).encode("utf-8")
    if hashlib.sha256(canonical).hexdigest() != document.get("sha256"):
        raise MasterStateRefusal(["master-state checksum does not match"])
    return _validate_state_dict(payload)


def load_master_state(path: str | Path) -> MasterState | None:
    """Load the stored master state; absent file -> None, refusal -> None.

    Refusals are returned as None by the caller-visible contract only when
    the caller asks for tolerance; :func:`master_state_from_bytes` itself
    raises the named :class:`MasterStateRefusal`.
    """
    path = Path(path)
    if not path.is_file():
        return None
    try:
        return master_state_from_bytes(path.read_bytes())
    except MasterStateRefusal:
        return None


def save_master_state(state: MasterState, path: str | Path) -> None:
    """Persist one document; the state home directory is created if needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(master_state_to_bytes(state))
