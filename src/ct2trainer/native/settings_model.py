"""Settings sidecar model for the native trainer (analog of .ct2trainer.json).

The document binds record selection, visible-name drafts, start-ON requests
and value-default drafts to the exact CT SHA-256 of the table it was created
from. Loading is only valid for the byte-identical table; any other table is
a visible rejection, never a silent reset to defaults.

Drafts stay drafts: the model never writes target memory. Applying a
value default is a separate explicit write through the caller's engine
callback; only a confirmed write is recorded as applied.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from pathlib import Path

SETTINGS_SCHEMA = 1
SETTINGS_FILENAME = ".ct2trainer.json"
_MAX_TEXT = 512
_HEX64 = re.compile(r"[0-9a-f]{64}")


class SettingsError(ValueError):
    """Structural or contract problem with a settings document."""


class SettingsRejection(SettingsError):
    """A settings document that was refused for the current table/records.

    ``reasons`` is the visible, displayable list; callers must show it and
    must not fall back to silent defaults.
    """

    def __init__(self, reasons: list[str]):
        super().__init__("; ".join(reasons))
        self.reasons = tuple(reasons)


@dataclass(frozen=True)
class SettingsDocument:
    schema: int
    table_sha256: str
    trainer_id: str | None
    process_name: str | None
    selected: tuple[int, ...]
    names: dict[int, str]
    start_on: tuple[int, ...]
    value_defaults: dict[int, str]
    hotkeys: dict[int, list[str]]

    def selected_set(self) -> set[int]:
        return set(self.selected)

    def name_for(self, record_id: int) -> str | None:
        return self.names.get(record_id)

    def start_on_set(self) -> set[int]:
        return set(self.start_on)

    def value_default_for(self, record_id: int) -> str | None:
        return self.value_defaults.get(record_id)


def sha256_hex(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _strict_document(raw: bytes) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise SettingsError("Duplicate JSON keys are not settings evidence")
            result[key] = value
        return result

    try:
        value = json.loads(raw, object_pairs_hook=pairs,
                           parse_constant=lambda item: (_ for _ in ()).throw(SettingsError("nonfinite JSON value")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise SettingsError("Settings document is not valid JSON") from exc
    if not isinstance(value, dict):
        raise SettingsError("Settings document must be a JSON object")
    return value


def _validate_id_set(ids, *, name: str, known: set[int], ordered: bool,
                     reasons: list[str]) -> tuple[int, ...]:
    if not isinstance(ids, list) or any(type(item) is not int for item in ids):
        reasons.append(f"{name} must be a list of integer record ids")
        return ()
    if len(set(ids)) != len(ids):
        reasons.append(f"{name} contains duplicate record ids")
        return ()
    if ordered and ids != sorted(ids):
        reasons.append(f"{name} must be sorted ascending")
        return ()
    unknown = [item for item in ids if item not in known]
    if unknown:
        reasons.append(f"{name} references unknown record ids: {unknown}")
        return ()
    return tuple(ids)


def create_default(table_sha256: str, *, trainer_id: str | None = None,
                   process_name: str | None = None) -> SettingsDocument:
    """Empty draft document bound to the given table hash."""
    if not _HEX64.fullmatch(table_sha256):
        raise SettingsError("table_sha256 must be a 64-char lowercase hex sha256")
    return SettingsDocument(
        schema=SETTINGS_SCHEMA, table_sha256=table_sha256, trainer_id=trainer_id,
        process_name=process_name, selected=(), names={}, start_on=(),
        value_defaults={}, hotkeys={})


def document_to_json(document: SettingsDocument) -> bytes:
    """Canonical, deterministic JSON bytes for one document."""
    raw = json.dumps({
        "schema": document.schema,
        "table_sha256": document.table_sha256,
        "trainer_id": document.trainer_id,
        "process_name": document.process_name,
        "selected": list(document.selected),
        "names": {str(key): value for key, value in sorted(document.names.items())},
        "start_on": list(document.start_on),
        "value_defaults": {str(key): value for key, value in sorted(document.value_defaults.items())},
        "hotkeys": {str(key): value for key, value in sorted(document.hotkeys.items())},
    }, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return raw.encode("utf-8")


class SettingsModel:
    """Load/save guard for the sidecar; drafts never touch target memory."""

    def __init__(self, table_sha256: str, known_record_ids, *,
                 trainer_id: str | None = None, process_name: str | None = None,
                 switch_ids=None):
        if not _HEX64.fullmatch(table_sha256):
            raise SettingsError("table_sha256 must be a 64-char lowercase hex sha256")
        known = set()
        for item in known_record_ids:
            if type(item) is not int or item < 0:
                raise SettingsError("known_record_ids must be integers")
            known.add(item)
        if not known:
            raise SettingsError("known_record_ids must not be empty")
        self.table_sha256 = table_sha256
        self.known_record_ids = frozenset(known)
        self.trainer_id = trainer_id
        self.process_name = process_name
        self.switch_ids = frozenset(switch_ids) if switch_ids is not None else None

    # ------------------------------------------------------------------ save
    def save(self, document: SettingsDocument, path: str | Path) -> None:
        """Write the canonical document; the path must carry the settings name."""
        name = Path(path).name
        if name != SETTINGS_FILENAME and not name.endswith(SETTINGS_FILENAME):
            raise SettingsError(f"Settings sidecar must be named {SETTINGS_FILENAME}")
        if not isinstance(document, SettingsDocument):
            raise SettingsError("save requires a SettingsDocument")
        if document.schema != SETTINGS_SCHEMA:
            raise SettingsError("Cannot save an unsupported settings schema")
        if document.table_sha256 != self.table_sha256:
            raise SettingsError("Settings document belongs to a different table")
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(document_to_json(document))

    # ------------------------------------------------------------------ load
    def load(self, path: str | Path) -> SettingsDocument:
        """Load only for the byte-identical table; otherwise a visible rejection.

        Raises ``SettingsRejection`` with a displayable reason list when the
        document cannot be used; callers must show the reasons and must not
        silently reset to defaults.
        """
        reasons: list[str] = []
        raw = Path(path).read_bytes()
        try:
            document = _strict_document(raw)
        except SettingsError as exc:
            raise SettingsRejection([str(exc)]) from exc

        schema = document.get("schema")
        if type(schema) is not int or schema != SETTINGS_SCHEMA:
            reasons.append(f"Schema version {schema!r} is not supported (expected {SETTINGS_SCHEMA})")

        table = document.get("table_sha256")
        if not isinstance(table, str) or not _HEX64.fullmatch(table):
            reasons.append("table_sha256 is missing or malformed")
        elif table != self.table_sha256:
            reasons.append(
                f"Settings belong to a different table (document {table[:12]}…, "
                f"current {self.table_sha256[:12]}…); refusing to load")

        trainer = document.get("trainer_id")
        if trainer is not None and (not isinstance(trainer, str) or not re.fullmatch(r"[0-9a-f]{16}", trainer)):
            reasons.append("trainer_id is malformed")
        elif trainer is not None and self.trainer_id is not None and trainer != self.trainer_id:
            reasons.append("trainer_id differs from the current trainer")

        process = document.get("process_name")
        if process is not None and (not isinstance(process, str) or not process or len(process) > 255):
            reasons.append("process_name is malformed")
        elif process is not None and self.process_name is not None and process != self.process_name:
            reasons.append("process_name differs from the current target")

        selected = _validate_id_set(document.get("selected"), name="selected",
                                    known=self.known_record_ids, ordered=True, reasons=reasons)
        start_on = _validate_id_set(document.get("start_on"), name="start_on",
                                    known=self.known_record_ids, ordered=True, reasons=reasons)
        if self.switch_ids is not None and start_on:
            not_switch = [item for item in start_on if item not in self.switch_ids]
            if not_switch:
                reasons.append(f"start_on references non-switch records: {not_switch}")

        names_raw = document.get("names")
        names: dict[int, str] = {}
        if names_raw is None:
            names = {}
        elif isinstance(names_raw, dict):
            for key, value in names_raw.items():
                if not isinstance(key, str) or not key.lstrip("-").isdigit():
                    reasons.append(f"names key {key!r} is not an integer record id")
                    continue
                if not isinstance(value, str) or not value or len(value) > _MAX_TEXT:
                    reasons.append(f"name for record {key} is malformed or too long")
                    continue
                record = int(key)
                if record not in self.known_record_ids:
                    reasons.append(f"names references unknown record id {record}")
                    continue
                names[record] = value
        else:
            reasons.append("names must be an object mapping record ids to strings")

        defaults_raw = document.get("value_defaults")
        defaults: dict[int, str] = {}
        if defaults_raw is None:
            defaults = {}
        elif isinstance(defaults_raw, dict):
            for key, value in defaults_raw.items():
                if not isinstance(key, str) or not key.lstrip("-").isdigit():
                    reasons.append(f"value_defaults key {key!r} is not an integer record id")
                    continue
                if not isinstance(value, str) or len(value) > _MAX_TEXT:
                    reasons.append(f"value_default for record {key} is malformed or too long")
                    continue
                record = int(key)
                if record not in self.known_record_ids:
                    reasons.append(f"value_defaults references unknown record id {record}")
                    continue
                defaults[record] = value
        else:
            reasons.append("value_defaults must be an object mapping record ids to strings")

        hotkeys_raw = document.get("hotkeys")
        hotkeys: dict[int, list[str]] = {}
        if hotkeys_raw is None:
            hotkeys = {}
        elif isinstance(hotkeys_raw, dict):
            for key, value in hotkeys_raw.items():
                if not isinstance(key, str) or not key.lstrip("-").isdigit():
                    reasons.append(f"hotkeys key {key!r} is not an integer record id")
                    continue
                if not isinstance(value, list) or not value or len(value) > 5:
                    reasons.append(f"hotkey for record {key} must be 1..5 tokens")
                    continue
                if not all(isinstance(token, str) and token and len(token) <= 16 for token in value):
                    reasons.append(f"hotkey tokens for record {key} are malformed")
                    continue
                record = int(key)
                if record not in self.known_record_ids:
                    reasons.append(f"hotkeys references unknown record id {record}")
                    continue
                hotkeys[record] = list(value)
        else:
            reasons.append("hotkeys must be an object mapping record ids to token lists")

        if reasons:
            raise SettingsRejection(reasons)

        return SettingsDocument(
            schema=SETTINGS_SCHEMA, table_sha256=table, trainer_id=trainer,
            process_name=process, selected=selected, names=names, start_on=start_on,
            value_defaults=defaults, hotkeys=hotkeys)

    # ------------------------------------------------------------------ apply
    def apply_value_default(self, document: SettingsDocument, record_id: int, *,
                            write) -> bool:
        """Apply one value-default draft through the caller's write callback.

        ``write(record_id, text)`` must return True only after the memory
        write is confirmed. The document itself is never mutated: a confirmed
        apply is recorded by the caller, not by a reset of the draft.
        """
        if not isinstance(document, SettingsDocument):
            raise SettingsError("apply_value_default requires a SettingsDocument")
        if document.table_sha256 != self.table_sha256:
            raise SettingsRejection([
                "Value apply refused: settings belong to a different table"])
        if type(record_id) is not int or record_id not in self.known_record_ids:
            raise SettingsError(f"Unknown record id for value apply: {record_id!r}")
        text = document.value_default_for(record_id)
        if text is None:
            raise SettingsError(f"Record {record_id} has no value default")
        if write is None or not callable(write):
            raise SettingsError("apply_value_default requires a write callback")
        result = write(record_id, text)
        return bool(result)
