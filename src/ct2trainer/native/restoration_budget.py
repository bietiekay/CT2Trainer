"""Draft controller-only, shared cooperative receipt restoration allowance.

No target capability is created here. Existing identity, journal, byte,
protection and held-event guards remain mandatory at every mutation. A deadline
can stop returned synchronous work; it cannot interrupt a Win32 call or fsync.
"""
from __future__ import annotations

from contextlib import contextmanager
from functools import wraps
import math
import threading
import time

from .lua_work_budget import WorkBudgetError

DEFAULT_SECONDS=30.0
DEFAULT_MUTATIONS=65536
DEFAULT_BYTES=128*1024*1024
_context=threading.local()


class RestorationBudgetError(WorkBudgetError):
    pass


def _seconds(value):
    if type(value) not in (int,float) or not math.isfinite(value) or not .001<=value<=120:
        raise ValueError('Restoration ceiling must be finite within 1ms..120s')
    return float(value)


class _Ledger:
    def __init__(self,clock,timeout,mutations,byte_limit):
        if not callable(clock):raise ValueError('Restoration clock must be controller-owned')
        if type(mutations) is not int or not 1<=mutations<=65536:
            raise ValueError('Invalid restoration mutation limit')
        if type(byte_limit) is not int or not 1<=byte_limit<=128*1024*1024:
            raise ValueError('Invalid restoration byte limit')
        self.clock,self.timeout=clock,_seconds(timeout)
        self.max_mutations,self.max_bytes=mutations,byte_limit
        self.last=None;self.started=None;self.deadline=None;self.violation=None
        self.mutations=self.bytes=0
        self.guards=[];self.emergency_depth=0;self.checking=False

    def now(self):
        value=self.clock()
        if type(value) not in (int,float) or not math.isfinite(value):
            self.fail('Restoration clock is not finite')
        value=float(value)
        if self.last is not None and value<self.last:
            self.fail('Restoration clock moved backwards')
        self.last=value
        return value

    def fail(self,reason):
        if self.violation is None:self.violation=reason
        raise RestorationBudgetError(self.violation)

    def begin(self):
        if self.deadline is None:
            self.started=self.now()
            self.deadline=self.started+self.timeout
        self.check(full=False)

    def check(self,*,full=True):
        if self.violation is not None:raise RestorationBudgetError(self.violation)
        if self.deadline is None:return
        if self.now()>=self.deadline:self.fail('Shared restoration deadline exceeded; retain uncertain receipts')
        if full and not self.checking:
            self.checking=True
            try:
                for guard in tuple(self.guards):
                    guard()
                    self.check(full=False)
            finally:self.checking=False

    def reserve(self,size):
        self.check(full=False)
        if type(size) is not int or size<=0:raise ValueError('Invalid restoration mutation size')
        if self.mutations>=self.max_mutations:self.fail('Shared restoration mutation count exceeded')
        if size>self.max_bytes-self.bytes:self.fail('Shared restoration byte allowance exceeded')
        self.mutations+=1;self.bytes+=size


def _clock_for(owner=None):
    from . import lua_work_budget
    work=getattr(lua_work_budget._context,'budget',None)
    if work is not None:return work.clock
    if owner is not None:
        clock=getattr(owner,'_clock',None)
        if callable(clock):return clock
        host=getattr(owner,'host',None)
        clock=getattr(host,'_clock',None)
        if callable(clock):return clock
        for scope in getattr(owner,'lua_activations',{}).values():
            clock=getattr(scope.host,'_clock',None)
            if callable(clock):return clock
    return time.monotonic


@contextmanager
def restoration_operation(clock=None,*,timeout=None,max_mutations=None,max_bytes=None):
    """One outer action; nested actions reuse its lazy, unextendable ledger."""
    previous=getattr(_context,'ledger',None)
    if previous is not None:
        # A child can tighten explicit limits but never restart or extend time.
        if timeout is not None:
            previous.timeout=min(previous.timeout,_seconds(timeout))
            if previous.deadline is not None:
                previous.deadline=min(previous.deadline,previous.started+previous.timeout)
        if max_mutations is not None:
            if type(max_mutations) is not int or not 1<=max_mutations<=65536:raise ValueError('Invalid child mutation bound')
            previous.max_mutations=min(previous.max_mutations,max_mutations)
        if max_bytes is not None:
            if type(max_bytes) is not int or not 1<=max_bytes<=DEFAULT_BYTES:raise ValueError('Invalid child byte bound')
            previous.max_bytes=min(previous.max_bytes,max_bytes)
        yield previous
        return
    ledger=_Ledger(clock or _clock_for(),DEFAULT_SECONDS if timeout is None else timeout,
                   DEFAULT_MUTATIONS if max_mutations is None else max_mutations,
                   DEFAULT_BYTES if max_bytes is None else max_bytes)
    _context.ledger=ledger
    try:yield ledger
    finally:_context.ledger=None


def restoration_entry(function):
    """Private root wrapper spanning normal work and its later compensation."""
    @wraps(function)
    def run(owner,*args,**kwargs):
        with restoration_operation(_clock_for(owner)):
            return function(owner,*args,**kwargs)
    return run


@contextmanager
def restoration_region(guard,clock=None,*,emergency=True,timeout=None):
    """Receipt-only Python region, joining the parent operation's allowance."""
    if not callable(guard) or type(emergency) is not bool:raise ValueError('Invalid controller restoration region')
    with restoration_operation(clock,timeout=timeout) as ledger:
        ledger.begin()
        ledger.guards.append(guard)
        if emergency:ledger.emergency_depth+=1
        try:
            ledger.check()
            yield ledger
            ledger.check()
        finally:
            if emergency:ledger.emergency_depth-=1
            if ledger.guards[-1] is not guard:raise RestorationBudgetError('Restoration guard stack changed')
            ledger.guards.pop()


def in_restoration():
    ledger=getattr(_context,'ledger',None)
    return ledger is not None and ledger.emergency_depth>0


def checkpoint(*,full=True):
    ledger=getattr(_context,'ledger',None)
    if ledger is not None:ledger.check(full=full)


def mutation_admission(size,*,rollback=False):
    ledger=getattr(_context,'ledger',None)
    if rollback and (ledger is None or not ledger.emergency_depth):
        raise RestorationBudgetError('Emergency rollback requires a controller restoration region')
    if ledger is not None:
        ledger.check(full=False)
        if ledger.guards:ledger.reserve(size)


def remaining(default):
    ledger=getattr(_context,'ledger',None)
    if ledger is None or ledger.deadline is None:return default
    ledger.check()
    return min(default,ledger.deadline-ledger.last)
