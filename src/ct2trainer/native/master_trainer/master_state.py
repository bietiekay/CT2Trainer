"""Master Trainer state document (last-used folder, preferences).

The state home holds one small document, ``master-settings.json``, next to
the tables index.  Schema 2 (0.25) carries:

- ``last_folder``  - the last-used table folder ("ask on first start");
- ``last_table``   - the last explicitly loaded table (MT-10), relative
  path within the table folder;
- ``attach_mode``  - "auto" (never asks; the documented smallest-PID rule)
  or "ask" (the user always picks the target process, MT-11).

Schema 1 documents (last_folder only) are promoted on load: the missing
fields take their documented defaults (last_table=None, attach_mode
"auto"), so existing state homes keep working unchanged.

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

MASTER_STATE_SCHEMA = 2
MASTER_STATE_SCHEMA_LEGACY = 1
MASTER_STATE_FILENAME = "master-settings.json"
MAX_MASTER_STATE_BYTES = 1024 * 1024
ATTACH_MODE_AUTO = "auto"
ATTACH_MODE_ASK = "ask"
ATTACH_MODES = (ATTACH_MODE_AUTO, ATTACH_MODE_ASK)
_MAX_FOLDER = 4096
_MAX_TABLE_PATH = 4096


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

    Only schema-2 documents may be written; schema 1 is load-only (promoted
    on load, see the module docstring).
    """

    schema: int
    last_folder: str | None
    last_table: str | None = None
    attach_mode: str = ATTACH_MODE_AUTO


def empty_master_state() -> MasterState:
    return MasterState(schema=MASTER_STATE_SCHEMA, last_folder=None,
                       last_table=None, attach_mode=ATTACH_MODE_AUTO)


def _validate_state_dict(payload: dict) -> MasterState:
    reasons: list[str] = []
    schema = payload.get("schema")
    if type(schema) is not int or schema not in (
            MASTER_STATE_SCHEMA, MASTER_STATE_SCHEMA_LEGACY):
        reasons.append(f"master-state schema {schema!r} is not supported "
                       f"(expected {MASTER_STATE_SCHEMA}, "
                       f"legacy {MASTER_STATE_SCHEMA_LEGACY} is promoted on load)")
    allowed = {"schema", "last_folder"}
    if schema == MASTER_STATE_SCHEMA:
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
    if reasons:
        raise MasterStateRefusal(reasons)
    # Promote legacy (schema 1) documents to the current schema with the
    # documented defaults; the stored document itself stays untouched.
    if schema == MASTER_STATE_SCHEMA_LEGACY:
        return MasterState(schema=MASTER_STATE_SCHEMA, last_folder=last,
                           last_table=None, attach_mode=ATTACH_MODE_AUTO)
    return MasterState(schema=MASTER_STATE_SCHEMA, last_folder=last,
                       last_table=last_table, attach_mode=attach_mode)


def master_state_to_bytes(state: MasterState) -> bytes:
    """Canonical, deterministic JSON bytes for one master-state document.

    Only the current schema is writable; legacy documents cannot be
    re-persisted as-is (they are promoted in memory on load).
    """
    if not isinstance(state, MasterState):
        raise MasterStateRefusal(["state must be a MasterState document"])
    if state.schema != MASTER_STATE_SCHEMA:
        raise MasterStateRefusal([f"cannot persist an unsupported "
                                  f"master-state schema {state.schema!r}"])
    _validate_state_dict({"schema": state.schema, "last_folder": state.last_folder,
                          "last_table": state.last_table,
                          "attach_mode": state.attach_mode})
    payload = {"schema": state.schema, "last_folder": state.last_folder,
               "last_table": state.last_table, "attach_mode": state.attach_mode}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                           allow_nan=False, ensure_ascii=True).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    return json.dumps({"payload": payload, "sha256": digest},
                      sort_keys=True, separators=(",", ":"),
                      allow_nan=False, ensure_ascii=True).encode("utf-8") + b"\n"


def master_state_from_bytes(raw: bytes) -> MasterState:
    """Strict, checksum-bound load of one master-state document.

    Schema-1 documents are accepted and promoted to schema 2 (see module
    docstring); every other foreign schema, malformed shape or tampered
    checksum raises the named :class:`MasterStateRefusal`.
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
