"""Quiescence proof for the owned fixture's single cooperative caller only."""
import ctypes
from ctypes import wintypes
from contextlib import contextmanager
import hashlib
from pathlib import Path

from ct2trainer.native.hooks import QuiescenceProof


class OwnedFixtureCoordinator:
    def __init__(self, executable: Path, expected_sha256: str):
        self.executable=Path(executable).resolve()
        if self.executable.name!='NativeHookFixture.exe':
            raise ValueError('The coordinator is restricted to the owned fixture')
        if hashlib.sha256(self.executable.read_bytes()).hexdigest()!=expected_sha256:
            raise ValueError('Owned fixture hash mismatch')
        self.expected_sha256=expected_sha256

    @contextmanager
    def hold(self,memory,ranges):
        if Path(memory._image_path()).resolve()!=self.executable:
            raise ValueError('Target is not this byte-pinned owned fixture')
        if hashlib.sha256(self.executable.read_bytes()).hexdigest()!=self.expected_sha256:
            raise ValueError('Fixture executable changed')
        k=ctypes.WinDLL('kernel32',use_last_error=True)
        k.OpenEventW.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.LPCWSTR]
        k.OpenEventW.restype=wintypes.HANDLE
        for name in ('SetEvent','ResetEvent','CloseHandle'):
            getattr(k,name).argtypes=[wintypes.HANDLE]
            getattr(k,name).restype=wintypes.BOOL
        k.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
        k.WaitForSingleObject.restype=wintypes.DWORD
        handles=[]
        requested=False
        try:
            for suffix in ('request','ready','resume'):
                h=k.OpenEventW(0x100002,False,f'Local\\CT2Trainer-Hook-{memory.pid}-{suffix}')
                if not h: raise ctypes.WinError(ctypes.get_last_error())
                handles.append(h)
            request,ready,resume=handles
            if k.WaitForSingleObject(ready,0)==0:
                raise RuntimeError('Fixture is already held by another coordinator')
            if k.WaitForSingleObject(request,0)==0:
                raise RuntimeError('Another fixture safe-point request is pending')
            if not k.ResetEvent(resume): raise ctypes.WinError(ctypes.get_last_error())
            if not k.SetEvent(request): raise ctypes.WinError(ctypes.get_last_error())
            requested=True
            if k.WaitForSingleObject(ready,2000)!=0:
                raise RuntimeError('Fixture did not acknowledge a safe point')
            identity=memory.identity
            check=lambda: memory.is_alive() and memory.identity==identity and k.WaitForSingleObject(ready,0)==0
            yield QuiescenceProof(identity,tuple(ranges),'owned-fixture-cooperative-safe-point',check)
        finally:
            if requested:
                if not k.ResetEvent(handles[0]) or not k.SetEvent(handles[2]):
                    raise ctypes.WinError(ctypes.get_last_error())
            for h in handles: k.CloseHandle(h)
