"""Hotkey and rebind model over the protected toggle controller path.

The model mirrors the CT hotkey contract: global hotkeys are registered only
through the same protected toggle path the Touch UI uses (the controller
gate), never by a direct memory write. Every binding is owned by an explicit
session owner; the registration list is the only authority for what may be
dispatched, unbound, or cleaned up.

Dispatch rules:
- Collision: one key combination may be bound to at most one record; a second
  registration is rejected with the conflicting record, visible and durable.
- Focus: a hotkey only fires while the target process is focused.
- Text editor guard: while a text field has focus, no hotkey is triggered.
- Blocked controller (e.g. uncertain session): dispatch is suppressed and
  reported, never retried silently.
- Cancellation: a pending registration can be cancelled before publication;
  publication re-checks the collision and drops itself on conflict.
- Cleanup: closing an owner removes exactly that owner's bindings and
  pending entries; foreign owners keep theirs.
- Sound policy: a success tone is reported only after a confirmed toggle whose
  state was saved. pending / failed / unknown outcomes are silent.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json


class HotkeyModelError(RuntimeError):
    """Invalid hotkey request or a binding contract violation."""


class HotkeyCollisionError(HotkeyModelError):
    """A key combination is already bound to another record."""

    def __init__(self, existing_record_id: int, requested_record_id: int):
        super().__init__(
            f"Hotkey already bound to record {existing_record_id}; "
            f"cannot bind record {requested_record_id} to the same combination")
        self.existing_record_id = existing_record_id
        self.requested_record_id = requested_record_id


class ToggleOutcomeStatus(str, Enum):
    CONFIRMED = "confirmed"
    PENDING = "pending"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ToggleOutcome:
    """Result of the protected toggle call; only confirmed+saved may sound."""

    status: ToggleOutcomeStatus
    saved: bool
    detail: str = ""

    @property
    def tone_allowed(self) -> bool:
        return self.status is ToggleOutcomeStatus.CONFIRMED and self.saved


MODIFIER_NAMES = frozenset({"ctrl", "alt", "shift", "meta"})
NAMED_KEYS = frozenset({
    "UP", "DOWN", "LEFT", "RIGHT", "SPACE", "TAB", "ENTER", "ESC", "DELETE",
    "INSERT", "HOME", "END", "PGUP", "PGDN", "PRINTSCREEN",
})


def canonical_key(token: str) -> str:
    if not isinstance(token, str) or not token:
        raise HotkeyModelError("A hotkey needs a nonempty key token.")
    key = token.upper()
    if key.lower() in MODIFIER_NAMES:
        raise HotkeyModelError("A modifier cannot be the main key: " + token)
    if len(key) == 1 and (key.isalpha() or key.isdigit()):
        return key
    if key.startswith("F") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        return key
    if key in NAMED_KEYS or len(key) <= 16:
        return key
    raise HotkeyModelError("Unsupported hotkey key token: " + token)


@dataclass(frozen=True)
class HotKeySpec:
    """One key combination; modifiers are a canonical order-independent set."""

    key: str
    modifiers: frozenset = frozenset()

    def __post_init__(self):
        key = canonical_key(self.key)
        if key != self.key:
            object.__setattr__(self, "key", key)
        if not isinstance(self.modifiers, frozenset):
            raise HotkeyModelError("Modifiers must be a frozenset of modifier names.")
        unknown = self.modifiers - MODIFIER_NAMES
        if unknown:
            raise HotkeyModelError("Unknown modifier names: " + ", ".join(sorted(unknown)))

    @classmethod
    def parse(cls, text: str) -> "HotKeySpec":
        """Parse 'Ctrl+Alt+F1' style text into a canonical spec."""
        if not isinstance(text, str) or not text.strip():
            raise HotkeyModelError("Hotkey text is empty.")
        tokens = [token.strip() for token in text.split("+")]
        if any(not token for token in tokens):
            raise HotkeyModelError("Hotkey text has empty parts: " + text)
        modifiers = set()
        key_token = None
        for token in tokens:
            lowered = token.lower()
            if lowered in MODIFIER_NAMES:
                modifiers.add(lowered)
            else:
                if key_token is not None:
                    raise HotkeyModelError("More than one main key: " + text)
                key_token = token
        if key_token is None:
            raise HotkeyModelError("Hotkey text has no main key: " + text)
        if len(modifiers) > 4:
            raise HotkeyModelError("Too many modifiers: " + text)
        return cls(key=canonical_key(key_token), modifiers=frozenset(modifiers))

    def as_list(self) -> list[str]:
        return sorted(self.modifiers) + [self.key]

    def to_json(self) -> str:
        return json.dumps({"key": self.key, "modifiers": sorted(self.modifiers)},
                          sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class HotkeyBinding:
    """One published registration with its owner binding."""

    owner: str
    record_id: int
    spec: HotKeySpec


class HotkeyController:
    """Owner-bound registration list plus protected dispatch.

    ``gate`` is the same protected controller path the Touch toggle uses
    (it must expose ``toggle(identifier) -> ToggleOutcome`` and a ``blocked``
    flag). The controller never touches memory itself.
    """

    def __init__(self, gate, *, focus_provider, text_focus_provider, tone_recorder=None):
        if gate is None or not hasattr(gate, "toggle"):
            raise HotkeyModelError("Hotkeys require the protected toggle gate.")
        if focus_provider is None or text_focus_provider is None:
            raise HotkeyModelError("Focus and text-focus providers are required.")
        self._gate = gate
        self._focus_provider = focus_provider
        self._text_focus_provider = text_focus_provider
        self._tone_recorder = tone_recorder
        self._published: list[HotkeyBinding] = []
        self._pending: list[HotkeyBinding] = []

    # ------------------------------------------------------------------ bind
    def register(self, owner: str, record_id: int, spec: HotKeySpec, *, commit: bool = True) -> HotkeyBinding:
        self._validate_owner(owner)
        if type(record_id) is not int or record_id <= 0:
            raise HotkeyModelError("Record ids are positive integers.")
        self._check_owner_binding(owner, record_id, include_pending=True)
        candidate = HotkeyBinding(owner, record_id, spec)
        if commit:
            self._check_collision(candidate, pending=False)
            self._published.append(candidate)
            return candidate
        self._pending.append(candidate)
        return candidate

    def cancel_pending(self, owner: str, record_id: int) -> bool:
        """Remove a pending registration before publication; True when removed."""
        self._validate_owner(owner)
        before = len(self._pending)
        self._pending = [item for item in self._pending
                         if not (item.owner == owner and item.record_id == record_id)]
        return len(self._pending) != before

    def commit_pending(self, owner: str, record_id: int) -> HotkeyBinding:
        """Publish a pending registration with a fresh collision re-check."""
        self._validate_owner(owner)
        candidate = self._find_pending(owner, record_id)
        if candidate is None:
            raise HotkeyModelError("No pending hotkey registration for record "
                                    + str(record_id) + " under that owner.")
        self._pending.remove(candidate)
        self._check_owner_binding(candidate.owner, candidate.record_id, include_pending=True)
        self._check_collision(candidate, pending=True)
        self._published.append(candidate)
        return candidate

    def unregister(self, owner: str, record_id: int) -> bool:
        """Owner-bound removal of a published binding; True when removed."""
        self._validate_owner(owner)
        before = len(self._published)
        self._published = [item for item in self._published
                           if not (item.owner == owner and item.record_id == record_id)]
        return len(self._published) != before

    def close(self, owner: str) -> tuple[int, int]:
        """Cleanup: remove exactly this owner's published and pending entries."""
        self._validate_owner(owner)
        published = sum(1 for item in self._published if item.owner == owner)
        pending = sum(1 for item in self._pending if item.owner == owner)
        self._published = [item for item in self._published if item.owner != owner]
        self._pending = [item for item in self._pending if item.owner != owner]
        return published, pending

    # ----------------------------------------------------------------- read
    def registrations(self) -> tuple[HotkeyBinding, ...]:
        return tuple(self._published)

    def pending(self) -> tuple[HotkeyBinding, ...]:
        return tuple(self._pending)

    def owner_of(self, record_id: int) -> str | None:
        for item in self._published:
            if item.record_id == record_id:
                return item.owner
        return None

    def binding_for(self, record_id: int) -> HotkeyBinding | None:
        for item in self._published:
            if item.record_id == record_id:
                return item
        return None

    # -------------------------------------------------------------- dispatch
    def dispatch(self, spec: HotKeySpec) -> "DispatchResult":
        """Dispatch one key combination through the protected toggle path."""
        binding = None
        for item in self._published:
            if item.spec == spec:
                binding = item
                break
        if binding is None:
            return DispatchResult(None, "unbound", None, False)
        if not self._focus_provider():
            return DispatchResult(binding.record_id, "suppressed-unfocused", None, False)
        if self._text_focus_provider():
            return DispatchResult(binding.record_id, "suppressed-text-focus", None, False)
        if getattr(self._gate, "blocked", False):
            return DispatchResult(binding.record_id, "suppressed-blocked", None, False)
        outcome = self._gate.toggle(binding.record_id)
        if not isinstance(outcome, ToggleOutcome):
            raise HotkeyModelError("The toggle gate must return a ToggleOutcome.")
        tone = outcome.tone_allowed
        if tone and self._tone_recorder is not None:
            self._tone_recorder(binding.record_id, outcome.status.value)
        return DispatchResult(binding.record_id, "triggered", outcome, tone)

    # ----------------------------------------------------------------- guard
    def _validate_owner(self, owner: str) -> None:
        if not isinstance(owner, str) or not owner or len(owner) > 256:
            raise HotkeyModelError("Hotkey owners are bounded nonempty strings.")

    def _check_owner_binding(self, owner: str, record_id: int, *, include_pending: bool) -> None:
        for item in self._published:
            if item.record_id == record_id:
                raise HotkeyModelError(
                    f"Record {record_id} already has a hotkey binding under owner "
                    f"{item.owner}; rebind through that owner")
        if include_pending:
            for item in self._pending:
                if item.record_id == record_id:
                    raise HotkeyModelError(
                        f"Record {record_id} has a pending hotkey registration under "
                        f"owner {item.owner}")

    def _find_pending(self, owner: str, record_id: int) -> HotkeyBinding | None:
        for item in self._pending:
            if item.owner == owner and item.record_id == record_id:
                return item
        return None

    def _check_collision(self, candidate: HotkeyBinding, *, pending: bool) -> None:
        for item in self._published:
            if item.spec == candidate.spec and item.record_id != candidate.record_id:
                raise HotkeyCollisionError(item.record_id, candidate.record_id)
        if pending:
            for item in self._pending:
                if item is not candidate and item.spec == candidate.spec \
                        and item.record_id != candidate.record_id:
                    raise HotkeyCollisionError(item.record_id, candidate.record_id)


@dataclass(frozen=True)
class DispatchResult:
    record_id: int | None
    status: str  # triggered | unbound | suppressed-unfocused | suppressed-text-focus | suppressed-blocked
    outcome: ToggleOutcome | None
    tone_played: bool
