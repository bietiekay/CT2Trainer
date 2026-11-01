"""Master Trainer state document (last-used table folder).

The state home holds one small document, ``master-settings.json``, next to
the tables index.  It carries the last-used table folder so that a
parameterless start ("ask on first start") only asks once: the first start
shows the directory picker, every later start reuses the stored folder
unless it no longer exists.

Persistence discipline mirrors the table index (``table_index.py``):
canonical JSON payload with a sha256 checksum envelope, strict size bound,
refused foreign schemas, malformed documents and tampered checksums instead
of guessing.  A refused document is treated by the caller as "no stored
state" (a fresh picker), never as a silent reset.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

MASTER_STATE_SCHEMA = 1
MASTER_STATE_FILENAME = "master-settings.json"
MAX_MASTER_STATE_BYTES = 1024 * 1024
_MAX_FOLDER = 4096


class MasterStateRefusal(ValueError):
    """A stored master-state document that is refused.

    ``reasons`` is the displayable refusal list; callers surface it and fall
    back to a fresh first-start (picker), never a silent guess.
    """

    def __init__(self, reasons: list[str]):
        super().__init__("; ".join(reasons))
        self.reasons = tuple(reasons)


@dataclass(frozen=True)
class MasterState:
    """One master-state document (schema-bound)."""

    schema: int
    last_folder: str | None


def empty_master_state() -> MasterState:
    return MasterState(schema=MASTER_STATE_SCHEMA, last_folder=None)


def _validate_state_dict(payload: dict) -> MasterState:
    reasons: list[str] = []
    schema = payload.get("schema")
    if type(schema) is not int or schema != MASTER_STATE_SCHEMA:
        reasons.append(f"master-state schema {schema!r} is not supported "
                       f"(expected {MASTER_STATE_SCHEMA})")
    allowed = {"schema", "last_folder"}
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
    if reasons:
        raise MasterStateRefusal(reasons)
    return MasterState(schema=MASTER_STATE_SCHEMA, last_folder=last)


def master_state_to_bytes(state: MasterState) -> bytes:
    """Canonical, deterministic JSON bytes for one master-state document."""
    if not isinstance(state, MasterState):
        raise MasterStateRefusal(["state must be a MasterState document"])
    if state.schema != MASTER_STATE_SCHEMA:
        raise MasterStateRefusal([f"cannot persist an unsupported "
                                  f"master-state schema {state.schema!r}"])
    _validate_state_dict({"schema": state.schema,
                          "last_folder": state.last_folder})
    payload = {"schema": state.schema, "last_folder": state.last_folder}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                           allow_nan=False, ensure_ascii=True).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    return json.dumps({"payload": payload, "sha256": digest},
                      sort_keys=True, separators=(",", ":"),
                      allow_nan=False, ensure_ascii=True).encode("utf-8") + b"\n"


def master_state_from_bytes(raw: bytes) -> MasterState:
    """Strict, checksum-bound load of one master-state document."""
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
