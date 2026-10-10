"""Private bounded work accounting; never a serialized or script API.

This draft separates Lua/transport work from trusted synchronous broker work.
It does not asynchronously interrupt Python or Win32 I/O. Blocking primitives
must consume remaining_seconds() and cooperate at publication/checkpoints.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import math
import threading


class WorkBudgetError(RuntimeError):
    pass


@dataclass(frozen=True)
class WorkLimits:
    lua_seconds: float
    instructions: int
    broker_call_seconds: float = 15.0
    broker_seconds: float = 30.0
    broker_calls: int = 4096
    wall_seconds: float = 30.25

    def __post_init__(self):
        for value in (self.lua_seconds, self.broker_call_seconds,
                      self.broker_seconds, self.wall_seconds):
            if type(value) not in (float, int) or not math.isfinite(value) or not 0.001 <= value <= 120:
                raise ValueError('Work deadline must be finite and within 1ms..120s')
        if type(self.instructions) is not int or not 1000 <= self.instructions <= 10_000_000:
            raise ValueError('Invalid finite Lua instruction allowance')
        if type(self.broker_calls) is not int or not 1 <= self.broker_calls <= 65536:
            raise ValueError('Invalid finite Lua broker dispatch allowance')


@dataclass
class _Frame:
    limits: WorkLimits
    guard: object
    started: float
    lua: float
    broker: float
    instructions: int
    calls: int


class _WorkBudget:
    def __init__(self, clock):
        self.clock = clock
        self.started = self.last = self._now()
        self.lua = self.broker = 0.0
        self.instructions = self.calls = 0
        self.mode = 'lua'
        self.frames = []
        self.dispatches = []
        self.violation = None

    def _now(self):
        value = self.clock()
        if type(value) not in (float, int) or not math.isfinite(value):
            raise WorkBudgetError('Work budget clock is not finite')
        return float(value)

    def _advance(self):
        now = self._now()
        if now < self.last:
            self._fail('Work budget monotonic clock moved backwards')
        elapsed = now - self.last
        if self.mode == 'lua':
            self.lua += elapsed
        else:
            self.broker += elapsed
        self.last = now
        return now

    def _fail(self, message):
        if self.violation is None:
            self.violation = message
        raise WorkBudgetError(self.violation)

    def check(self, *, instructions=0, _trusted_guards=True):
        now = self._advance()
        self.instructions += instructions
        if self.violation is not None:
            raise WorkBudgetError(self.violation)
        if _trusted_guards:
            for frame in self.frames:
                frame.guard()
                # Trusted identity/journal guards may block on filesystem or OS
                # reads. Charge their elapsed work before admitting a mutation.
                now = self._advance()
        for frame in self.frames:
            limits = frame.limits
            if self.instructions - frame.instructions > limits.instructions or self.lua - frame.lua >= limits.lua_seconds:
                self._fail('Lua execution budget exceeded')
            if self.calls - frame.calls > limits.broker_calls:
                self._fail('Lua broker call budget exceeded')
            if self.broker - frame.broker >= limits.broker_seconds:
                self._fail('Lua cumulative broker deadline exceeded')
            if now - frame.started >= limits.wall_seconds:
                self._fail('Lua overall wall deadline exceeded')
        if any(now >= deadline for deadline in self.dispatches):
            self._fail('Lua broker call deadline exceeded')

    @contextmanager
    def frame(self, limits, guard, *, mode='lua'):
        if mode not in {'lua', 'broker'}:
            raise WorkBudgetError('Invalid private work accounting mode')
        self.check()
        prior_mode = self.mode
        frame = _Frame(limits, guard, self.last, self.lua, self.broker, self.instructions, self.calls)
        self.frames.append(frame)
        self.mode = mode
        try:
            self.check()
            yield self
            self.check()
        finally:
            self._advance()
            self.mode = prior_mode
            assert self.frames[-1] is frame
            self.frames.pop()

    @contextmanager
    def dispatch(self):
        self.check()
        self.calls += 1
        self.check()
        deadline = min(self.last + frame.limits.broker_call_seconds for frame in self.frames)
        prior_mode = self.mode
        self.dispatches.append(deadline)
        self.mode = 'broker'
        primary = None
        try:
            self.check()
            yield self
        except Exception as exc:
            primary = exc
            raise
        finally:
            try:
                # Charge even a failed/cancelled call. An ordinary broker error
                # cannot hide an expired deadline and restart the next call.
                try:
                    self.check()
                except Exception as boundary:
                    if primary is not None:
                        raise WorkBudgetError(str(primary) + '; broker boundary: ' + str(boundary)) from primary
                    raise
            finally:
                self.mode = prior_mode
                assert self.dispatches[-1] == deadline
                self.dispatches.pop()

    @contextmanager
    def controller(self):
        """Account source adapters/direct linking inside one outer operation.

        Nested Lua work_slice frames still switch to charged Lua mode. This
        controller context does not grant a fresh dispatch count or deadline.
        """
        self.check()
        prior_mode = self.mode
        self.mode = 'broker'
        try:
            yield self
            self.check()
        finally:
            self._advance()
            self.mode = prior_mode

    def remaining(self):
        self.check()
        now = self.last
        values = [deadline - now for deadline in self.dispatches]
        for frame in self.frames:
            values.extend((frame.limits.wall_seconds - (now - frame.started),
                           frame.limits.broker_seconds - (self.broker - frame.broker)))
        if not values:
            raise WorkBudgetError('No active bounded broker dispatch')
        return min(values)


_context = threading.local()


@contextmanager
def work_slice(limits, guard, clock):
    """Nested states share counters; their tighter local limits still apply."""
    from .restoration_budget import in_restoration
    if getattr(_context, 'cleanup', False) or in_restoration():
        raise WorkBudgetError('Lua callbacks are refused during controller cleanup')
    budget = getattr(_context, 'budget', None)
    owns = budget is None
    if owns:
        budget = _WorkBudget(clock)
        _context.budget = budget
    try:
        from .restoration_budget import restoration_operation
        with restoration_operation(clock):
            with budget.frame(limits, guard):
                yield budget
    finally:
        if owns:
            _context.budget = None


@contextmanager
def controller_cleanup(guard, clock, *, timeout=30.0):
    """Join one shared, controller-only restoration ledger after cancellation."""
    from .restoration_budget import restoration_region
    old_cleanup=getattr(_context,'cleanup',False)
    _context.cleanup=True
    try:
        with restoration_region(guard,clock,timeout=timeout):
            yield
    finally:
        _context.cleanup=old_cleanup


def broker_checkpoint():
    """Cooperative trusted work checks cancellation, identity and all deadlines."""
    from .restoration_budget import in_restoration, checkpoint
    if not in_restoration():
        budget = getattr(_context, 'budget', None)
        if budget is not None:
            budget.check()
    checkpoint()


def remaining_seconds(default):
    """Cap existing bounded primitive waits; never extend their own maximum."""
    if type(default) not in (float, int) or not math.isfinite(default) or default <= 0:
        raise ValueError('A finite positive primitive timeout is required')
    budget = getattr(_context, 'budget', None)
    from .restoration_budget import in_restoration, remaining
    value=float(default)
    if not in_restoration() and budget is not None and budget.mode == 'broker':
        value=min(value,budget.remaining())
    return remaining(value)


def _mutation_checkpoint():
    """Last Python-only kernel admission after full trusted guards returned.

    Charge the returned work and every sticky/root deadline without repeating
    I/O guards. Full broker_checkpoint plus exact target/byte/lease/protection
    work is mandatory immediately before this call; no script sees this API.
    """
    from .restoration_budget import in_restoration, checkpoint
    if not in_restoration():
        budget = getattr(_context, 'budget', None)
        if budget is not None:
            budget.check(_trusted_guards=False)
    checkpoint(full=False)
