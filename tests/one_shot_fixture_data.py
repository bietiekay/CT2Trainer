"""Synthetic fixture data for the one-shot ON/OFF save contract lane.

Self-contained (no TableReferences, no game inputs): one-shot-only
record sets, a mixed script/value set, a parent/child tree, and a
deterministic scripted backend double in the style of
``activation_fixture_data.py`` (import is allowed, copying is not
required).

Record sets
-----------

ONE_SHOT_RECORDS: four plain one-shot script records (1-4).

MIXED_RECORDS: two one-shot script records (10, 11) plus two value
records (12, 13) to pin freeze orthogonality.

PARENT_CHILD_RECORDS: a script record tree 20 -> 21 -> 22
(PARENT_CHILD_EDGES) to pin that the one-shot contract is per-record
and performs no parent/child propagation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ct2trainer.native.one_shot_contract import (
    OneShotContract,
    OneShotReceipt,
)

# ---------------------------------------------------------------------------
# Record sets
# ---------------------------------------------------------------------------

ONE_SHOT_RECORDS = [
    (1, 'script'),
    (2, 'script'),
    (3, 'script'),
    (4, 'script'),
]

MIXED_RECORDS = [
    (10, 'script'),
    (11, 'script'),
    (12, 'value'),
    (13, 'value'),
]

PARENT_CHILD_RECORDS = [
    (20, 'script'),
    (21, 'script'),
    (22, 'script'),
]

PARENT_CHILD_EDGES = {
    21: (20,),
    22: (21,),
}

CT_HASH = 'ab' * 32
PROCESS_NAME = 'fixturegame.exe'

DEFAULT_PROGRAMS = {
    1: b'one-shot:grant-1',
    2: b'one-shot:grant-2',
    3: b'one-shot:grant-3',
    4: b'one-shot:grant-4',
    10: b'one-shot:mixed-10',
    11: b'one-shot:mixed-11',
    20: b'one-shot:tree-20',
    21: b'one-shot:tree-21',
    22: b'one-shot:tree-22',
}


class OneShotOutcome(Enum):
    """Deterministic scripted behavior for one published attempt."""

    OK = 'ok'          # confirmed receipt returned immediately
    FAIL = 'fail'      # unconfirmed receipt returned immediately
    LATE = 'late'      # publish returns None; the receipt stays pending


DEFAULT_OUTCOME = OneShotOutcome.OK

#: Convenience script for the flaky case: the first attempt fails, the
#: next explicit attempt (a new ON action) is confirmed.
FLAKY = (OneShotOutcome.FAIL, OneShotOutcome.OK)


@dataclass
class OneShotBackendDouble:
    """Injectable target-side double with a deterministic outcome script.

    Each :meth:`publish` consumes the next scripted outcome (or
    DEFAULT_OUTCOME once the script is exhausted) and records the
    invocation, so tests can pin the exact publish sequence and count.
    """

    script: tuple = ()
    invocations: list = field(default_factory=list)
    pending: dict = field(default_factory=dict)
    _cursor: int = 0

    @property
    def remaining(self) -> int:
        return len(self.script) - self._cursor

    def arm(self, script: tuple) -> None:
        """Replace the outcome script for the next scenario and reset the
        cursor and pending receipts (previously consumed outcomes stay
        recorded in invocations)."""
        self.script = tuple(script)
        self._cursor = 0
        self.pending.clear()

    def publish(self, record_id: int, program: bytes) -> OneShotReceipt | None:
        if self._cursor < len(self.script):
            outcome = self.script[self._cursor]
        else:
            outcome = DEFAULT_OUTCOME
        self._cursor += 1
        self.invocations.append((record_id, bytes(program), outcome))
        if outcome is OneShotOutcome.OK:
            return OneShotReceipt(record_id, True)
        if outcome is OneShotOutcome.FAIL:
            return OneShotReceipt(record_id, False)
        if outcome is OneShotOutcome.LATE:
            self.pending[record_id] = OneShotReceipt(record_id, True)
            return None
        raise ValueError('Unscripted backend outcome: %r' % (outcome,))

    def pending_receipt(self, record_id: int) -> OneShotReceipt:
        """Pop the backend receipt pending for one LATE publish."""
        return self.pending.pop(record_id)


def make_contract(records=None, programs=None, ct_hash=CT_HASH,
                  process_name=PROCESS_NAME) -> OneShotContract:
    """Build a detached OneShotContract on the given record set."""
    if records is None:
        records = ONE_SHOT_RECORDS
    if programs is None:
        programs = DEFAULT_PROGRAMS
    return OneShotContract(records, ct_hash, process_name, programs=programs)


def attached_contract(records=None, programs=None, generation=1):
    """(OneShotContract, OneShotBackendDouble) attached at generation 1."""
    contract = make_contract(records, programs)
    contract.attach(generation)
    return contract, OneShotBackendDouble()

