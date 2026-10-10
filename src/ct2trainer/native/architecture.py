"""Explicit target architecture policy; the controller remains Windows x64.

New plans bind a selected target profile. Schema 1 is legacy x64, never an
architecture-neutral request. A target handle can confirm or refuse a plan,
but cannot change its assembly mode or saved-state identity.
"""
from __future__ import annotations


class ArchitectureError(ValueError):
    """Unknown, inconsistent, or unconfirmed target architecture."""


def prepare_architecture(machine: str) -> dict:
    if type(machine) is not str or machine not in {'x86', 'x64'}:
        raise ArchitectureError('Target architecture must be explicitly x86 or x64.')
    bits = 32 if machine == 'x86' else 64
    return {'schema': 'ct2trainer-target-architecture/v1', 'machine': machine,
            'bitness': bits, 'pointer_size': bits // 8}


def plan_architecture(plan: dict) -> dict:
    if not isinstance(plan, dict) or type(plan.get('schema')) is not int:
        raise ArchitectureError('A native plan schema is required.')
    if plan['schema'] == 1:
        if 'target_architecture' in plan:
            raise ArchitectureError('Legacy schema 1 cannot override its x64 target architecture.')
        return prepare_architecture('x64')
    if plan['schema'] != 2:
        raise ArchitectureError('Unsupported native architecture plan schema.')
    profile = plan.get('target_architecture')
    if (not isinstance(profile, dict) or set(profile) != {'schema', 'machine', 'bitness', 'pointer_size'}
            or type(profile.get('bitness')) is not int or type(profile.get('pointer_size')) is not int):
        raise ArchitectureError('An exact canonical target architecture profile is required.')
    canonical = prepare_architecture(profile.get('machine'))
    if profile != canonical:
        raise ArchitectureError('Target architecture metadata is inconsistent.')
    return canonical


def require_target_architecture(plan: dict, memory) -> dict:
    """Read the held backend's confirmed pointer width; never probe by filename.

    ProcessMemory obtains this from the exact live handle, with PID/creation-time
    checks. Other backends must supply the same contract. No scan, allocation,
    write, session claim, source rewriting or target selection is performed here.
    """
    profile = plan_architecture(plan)
    observed = getattr(memory, 'pointer_size', None)
    if type(observed) is not int or observed not in {4, 8}:
        raise ArchitectureError('Held target architecture is unavailable or unsupported.')
    if observed != profile['pointer_size']:
        actual = 'x86' if observed == 4 else 'x64'
        raise ArchitectureError('Target architecture mismatch: plan requires ' + profile['machine']
                                + ', held process is ' + actual + '. Recompile explicitly for that target.')
    return profile
