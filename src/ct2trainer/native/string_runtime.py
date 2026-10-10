"""Held literal String writes preserving all bytes beyond the exact intent.

Canonical CT metadata describes an input/read bound. It does not authorize
clearing that bound. Each mutation owns only its literal prefix and terminator,
or the exact fixed-length literal, with fresh pointer, region and target proof.
"""
from .engine import NativeRuntimeError, PatchConflict, RetryableAction, StateError, _Patch
from .hooks import QuiescenceProof, HookError, HookUncertain, _rw_inventory
from .value_types import (parse_profile_value, format_profile_value,
                         profile_value_matches, validate_value_profile)

MAX_ITEMS=128
MAX_BATCH_BYTES=1024*1024


def _hold(engine):
    hold=getattr(engine.hook_coordinator,'hold_data',None)
    if not callable(hold):
        raise NativeRuntimeError('String operations require a verified data-only coordinator')
    return hold


def _profile(engine,identifier):
    entry=engine._entry(identifier,'value')
    profile=entry.get('value_profile')
    validate_value_profile(profile)
    if profile['kind']!='string' or not profile['actionable']:
        raise NativeRuntimeError('String operation requires a canonical actionable String record')
    return entry,profile


def admit_freeze(engine,identifier):
    """Refuse enrollment before it can make the next freeze tick impossible."""
    _profile(engine,identifier)
    identifiers={other for other in engine.frozen
                 if engine.entries[other].get('value_profile',{}).get('kind')=='string'}
    identifiers.add(identifier)
    if len(identifiers)>MAX_ITEMS:
        raise NativeRuntimeError('String freeze enrollment exceeds its record-count bound')
    read_bytes=sum(_profile(engine,other)[1]['size'] for other in identifiers)
    if read_bytes>MAX_BATCH_BYTES:
        raise NativeRuntimeError('String freeze enrollment exceeds its byte bound')


def _refusal(engine,error,mutation_attempted):
    if isinstance(error,HookUncertain):
        engine._block(StateError('String data coordinator cleanup is uncertain: '+str(error)))
        raise NativeRuntimeError(str(error)) from error
    if isinstance(error,HookError):
        if mutation_attempted:
            engine._block(StateError('String data-write proof became uncertain: '+str(error)))
            raise NativeRuntimeError(str(error)) from error
        raise RetryableAction(str(error)) from error
    raise error


def snapshot_freeze(engine,identifier,address):
    """Freeze a freshly held canonical prefix; a full unterminated read refuses."""
    entry,profile=_profile(engine,identifier)
    ranges=((address,profile['size']),)
    hold=_hold(engine)
    regions=_rw_inventory(engine.memory,*ranges[0])
    try:
        with hold(engine.memory,ranges) as proof:
            if not isinstance(proof,QuiescenceProof):
                raise NativeRuntimeError('String coordinator did not return a target-bound data proof')
            proof.verify(engine.memory,ranges)
            engine._guard()
            engine._check_patches()
            if engine._value_address(entry)!=address:
                raise PatchConflict('String pointer changed under the held freeze event')
            if _rw_inventory(engine.memory,*ranges[0])!=regions:
                raise HookError('String writable region changed under held freeze')
            current=engine.memory.read(address,profile['size'])
            raw=parse_profile_value(profile,format_profile_value(profile,current))
            engine._check_value_ownership(identifier,address,len(raw))
            proof.verify(engine.memory,ranges)
            engine._guard()
            return raw
    except Exception as error:
        _refusal(engine,error,False)


def write_strings(engine,items):
    """Publish precise prefixes under one held target event and shared undo ledger."""
    if not isinstance(items,(list,tuple)) or not 1<=len(items)<=MAX_ITEMS:
        raise NativeRuntimeError('String transaction exceeds its record-count bound')
    hold=_hold(engine)
    prepared=[]
    read_bytes=write_bytes=0
    identifiers=set()
    for identifier,address,desired in items:
        entry,profile=_profile(engine,identifier)
        if identifier in identifiers:
            raise NativeRuntimeError('String transaction repeats a record')
        identifiers.add(identifier)
        # This reconstructs the complete literal; LiteralWrite/JSON is no permit.
        profile_value_matches(profile,desired,bytes(profile['size']))
        read_bytes+=profile['size'];write_bytes+=len(desired)
        if max(read_bytes,write_bytes)>MAX_BATCH_BYTES:
            raise NativeRuntimeError('String transaction exceeds its byte bound')
        if any(address < old_address+len(old_desired) and old_address < address+len(desired)
               for _,old_address,old_desired,_,_ in prepared):
            raise NativeRuntimeError('String transaction contains overlapping literal spans')
        regions=_rw_inventory(engine.memory,address,len(desired))
        prepared.append((identifier,address,desired,entry,regions))
    ranges=tuple((address,len(desired)) for _,address,desired,_,_ in prepared)
    mutation_attempted=False
    transaction_finished=False
    try:
        with hold(engine.memory,ranges) as proof:
            if not isinstance(proof,QuiescenceProof):
                raise NativeRuntimeError('String coordinator did not return a target-bound data proof')
            proof.verify(engine.memory,ranges)
            def exact_guard():
                for identifier,address,desired,entry,regions in prepared:
                    if engine._value_address(entry)!=address:
                        raise PatchConflict('String pointer changed under the held write event')
                    if _rw_inventory(engine.memory,address,len(desired))!=regions:
                        raise HookError('String writable region changed during publication or restoration')
                    engine._check_value_ownership(identifier,address,len(desired))
            engine._guard()
            engine._check_patches()
            exact_guard()
            patches=[]
            for _,address,desired,entry,_ in prepared:
                # A complete bounded snapshot is required. Its old encoding need
                # not be valid: an explicitly valid literal may repair it, with
                # an exact raw inverse if publication fails.
                engine.memory.read(address,entry['value_profile']['size'])
                original=engine.memory.read(address,len(desired))
                if original!=desired:patches.append(_Patch(address,original,desired))
            proof.verify(engine.memory,ranges)
            mutation_attempted=bool(patches)
            engine._write_transaction(patches,proof=proof,transaction_guard=exact_guard)
            transaction_finished=True
            proof.verify(engine.memory,ranges)
            exact_guard()
            for _,address,desired,_,_ in prepared:
                if engine.memory.read(address,len(desired))!=desired:
                    raise PatchConflict('String literal prefix changed before confirmation')
        # Cleanup/resume belongs to the charged operation. It may be slow even
        # though all held writes and readbacks completed successfully.
        from .lua_work_budget import broker_checkpoint
        broker_checkpoint()
    except Exception as error:
        if transaction_finished and mutation_attempted:
            engine._block(StateError('Post-publication String confirmation is uncertain: '+str(error)))
            raise NativeRuntimeError(str(error)) from error
        _refusal(engine,error,mutation_attempted)
