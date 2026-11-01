"""Per-table settings sidecar store for the Master Trainer (MT-6).

Wires the existing, already-tested
:mod:`ct2trainer.native.settings_model` (the ``.ct2trainer.json``
sidecar: visible-name drafts, value defaults, start-ON requests, hotkeys)
into the Master Trainer as a **per-table** sidecar under the state home.

Keying discipline (the point of the package): the sidecar is keyed by the
table's **content sha256** — the table's identity — and never by its path.
Tables move between folders all the time; the hash does not. The same table
therefore always restores the same sidecar regardless of where it sits on
disk, and two different tables can never collide on one file.

Layout (MT-5 discipline: the index and every sidecar live under the state
home only, never inside the table folder)::

    <state home>/settings/<table_sha256>.ct2trainer.json

The file name ends with ``.ct2trainer.json`` so the existing
``SettingsModel.save`` contract (which requires exactly that name) accepts
it unchanged.

All load/save semantics are delegated to the tested
:class:`~ct2trainer.native.settings_model.SettingsModel`; this module adds
only the per-table path management, the strict sha boundary, and the
``(document, reasons)`` tuple contract the Master UI consumes on restore and
on close.

The on/off wish persistence itself is NOT part of this package: it already
works through the engine state store keyed by trainer id (MT-4). This
module does not touch the engine or that store.

Pure standard library; no Tk, no engine, no platform-specific system APIs,
no network.
"""
from __future__ import annotations

import re
from pathlib import Path

from ..settings_model import (
    SettingsDocument,
    SettingsError,
    SettingsModel,
    SettingsRejection,
)

# Same 64-char lowercase-hex discipline as settings_model._HEX64. Defined
# locally (house style: each module keeps its own boundary constant) so the
# store's boundary is self-contained and auditable in one place.
_HEX64 = re.compile(r"[0-9a-f]{64}")

_SIDECAR_DIR = "settings"


class MasterSettingsRefusal(SettingsError):
    """Named, store-level structural refusal.

    Raised for problems that are the *store's* boundary rather than a
    document-level rejection: a malformed table sha256, a non-
    :class:`SettingsDocument` input, or a document with nothing to persist.
    It is a :class:`SettingsError` subclass (and therefore a
    ``ValueError``), so callers may catch either the specific named error
    or the family. Document-level refusals keep the
    :class:`SettingsRejection` contract with its displayable reason list.
    """


class MasterSettingsStore:
    """One store per state home; per-table sidecars keyed by table sha256."""

    def __init__(self, state_home: str | Path):
        """Bind the store to one state-home directory (created lazily on save)."""
        self.state_home = Path(state_home)

    # ------------------------------------------------------------- boundary
    def _require_sha(self, table_sha256: str) -> str:
        if not isinstance(table_sha256, str) or not _HEX64.fullmatch(table_sha256):
            raise MasterSettingsRefusal(
                "table_sha256 must be a 64-char lowercase hex sha256, "
                f"got {table_sha256!r}")
        return table_sha256

    @staticmethod
    def _known_ids_from_document(document: SettingsDocument) -> set[int]:
        """The union of every record id the document actually references.

        ``selected`` + ``start_on`` + the keys of ``names`` /
        ``value_defaults`` / ``hotkeys``. This is the minimal known-record
        set needed to round-trip the document through ``SettingsModel``.
        """
        ids: set[int] = set()
        ids.update(document.selected)
        ids.update(document.start_on)
        ids.update(document.names.keys())
        ids.update(document.value_defaults.keys())
        ids.update(document.hotkeys.keys())
        return ids

    # ---------------------------------------------------------------- paths
    def sidecar_path(self, table_sha256: str) -> Path:
        """``<state home>/settings/<table_sha256>.ct2trainer.json``.

        Pure path construction — no directories are created here. The path
        is built only from the validated hex sha plus the fixed relative
        layout, so path traversal is impossible. Raises
        :class:`MasterSettingsRefusal` for a non-conforming sha.
        """
        sha = self._require_sha(table_sha256)
        return self.state_home / _SIDECAR_DIR / f"{sha}.ct2trainer.json"

    def has_table(self, table_sha256: str) -> bool:
        """True when a sidecar file currently exists for this table hash."""
        return self.sidecar_path(table_sha256).is_file()

    # ----------------------------------------------------------------- load
    def load_for(self, table_sha256: str, known_record_ids, *,
                 switch_ids=None, process_name=None
                 ) -> tuple[SettingsDocument | None, list[str]]:
        """Load the sidecar for one table for display.

        Returns ``(document, [])`` on success. Returns ``(None, reasons)``
        for every non-success case:

        - malformed table sha256 -> ``(None, [named reason])``;
        - no sidecar file present -> ``(None, [])`` (nothing to restore is
          normal and not an error);
        - a stored document the ``SettingsModel`` refuses -> ``(None,
          reasons)`` where ``reasons`` is the :class:`SettingsRejection`
          displayable list (including the "different table" refusal);
        - any other structural :class:`SettingsError` (e.g. empty/
          malformed ``known_record_ids``) -> ``(None, [named reason])``.

        Callers must show the reasons and must NOT silently fall back to
        defaults (the ``SettingsModel.load`` contract).
        """
        try:
            path = self.sidecar_path(table_sha256)
        except MasterSettingsRefusal as exc:
            return None, [str(exc)]
        if not path.is_file():
            return None, []
        try:
            model = SettingsModel(table_sha256, known_record_ids,
                                  switch_ids=switch_ids,
                                  process_name=process_name)
        except SettingsError as exc:
            return None, [str(exc)]
        try:
            document = model.load(path)
        except SettingsRejection as exc:
            return None, list(exc.reasons)
        except SettingsError as exc:
            return None, [str(exc)]
        return document, []

    # ----------------------------------------------------------------- save
    def save_for(self, document: SettingsDocument, table_sha256: str) -> Path:
        """Persist ``document`` to the table's sidecar; returns the path.

        The known record ids are derived from the document's own id sets
        (``selected`` + ``start_on`` + the keys of ``names`` /
        ``value_defaults`` / ``hotkeys``). An all-empty draft has nothing
        to persist and is refused, not silently written as a default file.

        Raises :class:`MasterSettingsRefusal` for store-boundary problems
        (malformed sha, non-document input, nothing to persist) and the
        underlying :class:`SettingsError` for document-level contract
        violations (e.g. the document belongs to a different table).
        """
        sha = self._require_sha(table_sha256)
        if not isinstance(document, SettingsDocument):
            raise MasterSettingsRefusal("save_for requires a SettingsDocument")
        known = self._known_ids_from_document(document)
        if not known:
            raise MasterSettingsRefusal(
                "nothing to persist: the document references no record ids")
        model = SettingsModel(sha, sorted(known))
        path = self.sidecar_path(sha)
        model.save(document, path)
        return path
