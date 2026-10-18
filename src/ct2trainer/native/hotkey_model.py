"""Hotkey and rebind model over the protected toggle controller path.

The model mirrors the CT hotkey contract: global hotkeys are registered only
through the same protected toggle path the Touch UI uses (the controller
gate), never by a direct memory write. Every binding is owned by an explicit
session owner; the registration list is the only authority for what may be
dispatched, unbound, or cleaned up.

Dispatch rules:
- Collision: one key combination may be bound to at most one record; a second
  strict ``register`` call is rejected with the conflicting record, visible
  and durable.  The engine-level ``register_first_wins`` path implements the
  trainer policy instead: the first published binding keeps the combination
  and a later claimant simply gets no binding (the caller reports the named
  conflict warning; the losing record stays fully functional).
- One record may hold several published bindings (a source record can carry
  multiple hotkeys, e.g. one toggle key and one value-operation key); the
  single-binding restriction only applies across different owners.
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
- VK mapping: ``vk_to_spec`` normalizes the decimal Windows virtual-key codes
  stored in source table ``<Key>`` elements into the canonical named spec
  (modifiers plus exactly one main key); unmappable codes fail closed with a
  named ``HotkeyModelError``.
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
# Source action texts that map to the record's activation toggle (CE contract:
# the three toggle variants all flip active state; Allow Increase/Decrease
# only differ in CE's activation sound choice).
ACTIVATION_HOTKEY_ACTIONS = frozenset({
    "Toggle Activation", "Toggle Activation Allow Increase",
    "Toggle Activation Allow Decrease", "Activate", "Deactivate"})
# Source action texts that map to a value-row operation on the record.
VALUE_HOTKEY_ACTIONS = frozenset({"Set Value", "Increase Value", "Decrease Value"})


def format_hotkey_keys(keys) -> str:
    """Human-readable form of a source key combination ('Ctrl+Alt+F1').

    Modifier names render in canonical order, then the main key; unmappable
    virtual-key codes render as ``VK<n>``; an empty list renders ``(none)``.
    """
    if not isinstance(keys, (list, tuple)) or not keys:
        return "(none)"
    modifiers = set()
    main: list[str] = []
    for vk in keys:
        if type(vk) is not int or not 0 < vk <= 255:
            main.append(f"VK{vk!r}")
            continue
        if vk in VK_MODIFIER_NAMES:
            modifiers.add(VK_MODIFIER_NAMES[vk])
        elif vk in VK_KEY_NAMES:
            main.append(VK_KEY_NAMES[vk])
        else:
            main.append(f"VK{vk}")
    if not modifiers and not main:
        return "(none)"
    return "+".join(sorted(modifiers) + main)
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


# Windows virtual-key names used by source table <Key> elements.  The mapping
# is bounded and clean-room: modifier-class codes fold into the four canonical
# modifiers, everything else is a main key.  Codes outside these tables are
# not representable and fail closed in vk_to_spec().
VK_MODIFIER_NAMES = {
    17: "ctrl", 162: "ctrl", 163: "ctrl",
    2: "meta", 91: "meta", 92: "meta",
    16: "shift", 160: "shift", 161: "shift",
    18: "alt", 164: "alt", 165: "alt",
}
VK_KEY_NAMES = {
    8: "BACK", 9: "TAB", 13: "ENTER", 20: "CAPSLOCK", 27: "ESC",
    32: "SPACE", 33: "PGUP", 34: "PGDN", 35: "END", 36: "HOME",
    37: "LEFT", 38: "UP", 39: "RIGHT", 40: "DOWN",
    45: "PRINT", 46: "EXECUTE", 47: "PRINTSCREEN",
    93: "APPS", 124: "NUMLOCK", 125: "SCROLL",
    106: "NUMMULTIPLY", 107: "NUMADD", 109: "NUMSUBTRACT",
    110: "NUMDECIMAL", 111: "NUMDIVIDE",
    186: "OEM1", 187: "OEM2", 188: "OEM3", 189: "OEM4",
    190: "OEM5", 191: "OEM6", 192: "OEM7",
    220: "LBRACKET", 221: "RBRACKET", 222: "BACKSLASH",
}
for _digit in range(10):
    VK_KEY_NAMES[48 + _digit] = str(_digit)
    VK_KEY_NAMES[96 + _digit] = "NUMPAD" + str(_digit)
for _letter in range(26):
    VK_KEY_NAMES[65 + _letter] = chr(ord("A") + _letter)
for _function in range(1, 25):
    VK_KEY_NAMES[111 + _function] = "F" + str(_function)


def vk_to_spec(vks) -> "HotKeySpec":
    """Canonical spec for one source key combination (decimal VK codes).

    Accepts at most five unique positive codes up to 255; modifier-class
    codes fold into the canonical modifier set and exactly one main key must
    remain.  Unmappable codes, missing main keys and multi-main-key
    combinations are named, fail-closed ``HotkeyModelError`` refusals.
    """
    if not isinstance(vks, (list, tuple)) or not vks or len(vks) > 5:
        raise HotkeyModelError("A hotkey needs 1..5 key tokens.")
    seen: set[int] = set()
    for vk in vks:
        if type(vk) is not int or not 0 < vk <= 255:
            raise HotkeyModelError("Hotkey key tokens are positive integers up to 255.")
        if vk in seen:
            raise HotkeyModelError("Duplicate hotkey key token: VK " + str(vk))
        seen.add(vk)
    modifiers: set[str] = set()
    main_keys: list[str] = []
    for vk in sorted(seen):
        if vk in VK_MODIFIER_NAMES:
            modifiers.add(VK_MODIFIER_NAMES[vk])
        elif vk in VK_KEY_NAMES:
            main_keys.append(VK_KEY_NAMES[vk])
        else:
            raise HotkeyModelError("Unsupported hotkey key VK " + str(vk))
    if not main_keys:
        raise HotkeyModelError("Hotkey key combination has no main key.")
    if len(main_keys) > 1:
        raise HotkeyModelError(
            "Hotkey key combination has more than one main key: "
            + ", ".join(main_keys))
    return HotKeySpec(key=main_keys[0], modifiers=frozenset(modifiers))


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

    def __init__(self, gate, *, focus_provider, text_focus_provider, tone_recorder=None,
                 binding_handler=None):
        if gate is None or not hasattr(gate, "toggle"):
            raise HotkeyModelError("Hotkeys require the protected toggle gate.")
        if focus_provider is None or text_focus_provider is None:
            raise HotkeyModelError("Focus and text-focus providers are required.")
        self._gate = gate
        self._focus_provider = focus_provider
        self._text_focus_provider = text_focus_provider
        self._tone_recorder = tone_recorder
        # WP-40: optional binding-aware dispatch hook.  When set, dispatch
        # hands the full binding (owner, record, spec) to the handler so the
        # engine can route the pressed combination to the record hotkey that
        # declared it (one record may hold several different actions); the
        # gate stays the protected fallback path.
        self._binding_handler = binding_handler
        self._published: list[HotkeyBinding] = []
        self._pending: list[HotkeyBinding] = []

    # ------------------------------------------------------------------ bind
    def register(self, owner: str, record_id: int, spec: HotKeySpec, *, commit: bool = True) -> HotkeyBinding:
        self._validate_owner(owner)
        if type(record_id) is not int or record_id <= 0:
            raise HotkeyModelError("Record ids are positive integers.")
        self._check_owner_binding(owner, record_id, spec, include_pending=True)
        candidate = HotkeyBinding(owner, record_id, spec)
        if commit:
            self._check_collision(candidate, pending=False)
            self._published.append(candidate)
            return candidate
        self._pending.append(candidate)
        return candidate

    def register_first_wins(self, owner: str, record_id: int, spec: HotKeySpec) -> tuple[bool, "HotkeyBinding | None"]:
        """Engine conflict policy: the first published binding for a
        combination wins.

        Returns ``(True, None)`` when the binding was registered.  Returns
        ``(False, winner)`` when another already-published binding owns the
        combination: the caller is expected to surface the named conflict
        warning and register nothing for the losing record (which stays fully
        functional).  A record re-registering a combination it already holds
        is a no-op success (``(True, existing)``) so reactivation is
        idempotent.
        """
        self._validate_owner(owner)
        if type(record_id) is not int or record_id <= 0:
            raise HotkeyModelError("Record ids are positive integers.")
        self._check_owner_binding(owner, record_id, spec, include_pending=True)
        winner = self.find(spec)
        if winner is not None and winner.record_id != record_id:
            return False, winner
        candidate = HotkeyBinding(owner, record_id, spec)
        if winner is None:
            self._published.append(candidate)
        return True, winner

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
        self._check_owner_binding(candidate.owner, candidate.record_id, candidate.spec, include_pending=True)
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

    def find(self, spec: HotKeySpec) -> HotkeyBinding | None:
        """First published binding for the exact key combination, or None.

        Read-only lookup used by the engine first-wins policy and by the UI
        to show which record currently owns a claimed combination.
        """
        for item in self._published:
            if item.spec == spec:
                return item
        return None

    # -------------------------------------------------------------- dispatch
    def dispatch(self, spec: HotKeySpec) -> "DispatchResult":
        """Dispatch one key combination through the protected toggle path."""
        binding = self.find(spec)
        if binding is None:
            return DispatchResult(None, "unbound", None, False)
        if not self._focus_provider():
            return DispatchResult(binding.record_id, "suppressed-unfocused", None, False)
        if self._text_focus_provider():
            return DispatchResult(binding.record_id, "suppressed-text-focus", None, False)
        if getattr(self._gate, "blocked", False):
            return DispatchResult(binding.record_id, "suppressed-blocked", None, False)
        if self._binding_handler is not None:
            outcome = self._binding_handler(binding)
        else:
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

    def _check_owner_binding(self, owner: str, record_id: int, spec: HotKeySpec,
                             *, include_pending: bool) -> None:
        # A record may hold several bindings for its own owner (multiple
        # source hotkeys); only a foreign owner holding the record is a
        # contract violation, as is a pending duplicate for the same
        # record + combination.
        for item in self._published:
            if item.record_id == record_id and item.owner != owner:
                raise HotkeyModelError(
                    f"Record {record_id} already has a hotkey binding under owner "
                    f"{item.owner}; rebind through that owner")
        if include_pending:
            for item in self._pending:
                if item.record_id == record_id and item.spec == spec:
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
