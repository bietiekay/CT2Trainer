"""Ignored N11 draft: source-bound literal RW globals and opaque consumer leases.

This is controller code, never a Lua API or a serialized pointer authority.  It
deliberately refuses readmem initializers and changed reinitialization.  Published
storage is retained until exact target exit; dealloc means consumer release.

The staged readmem profile (staged-readmem-rw/v1) extends the literal-only
profile with the two corpus-pinned shapes: readmem(target, size) under the
direct global ENABLE cursor (target_to_global, copied into the live allocation
at activation) and readmem(global, size) under a target DISABLE cursor
(global_to_target, copied back at deactivation).  Anything else that touches
a declared global (assert, reassemble, self-referencing readmem, offset or
multi-symbol readmem of a global, mixed initializer+staging) stays refused.
"""
from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import threading

from ct2trainer.native import aa_program as aa
from ct2trainer.native.aa import validate_symbol
from ct2trainer.native.address_expression import (AddressExpressionError, integer,
                                                  resolve_expression)
from ct2trainer.native.hooks import (HookManager, HookError, HookUncertain,
    MAX_HOOK_ALLOCATIONS, MAX_HOOK_BYTES)

SCHEMA = 'ct2trainer-global-aa/v1'
POOL_SCHEMA = 'ct2trainer-global-pool-draft/v1'
MAX_GLOBALS = 32
MAX_LEASES = 256
MAX_GLOBAL_BYTES = 65536
MAX_POOL_BYTES = 4 * 1024 * 1024  # reservation charged at least 64 KiB/member
MAX_POOL_JOURNAL_BYTES = 8 * 1024 * 1024
_AUTHORITY = object()


class GlobalError(aa.ProgramError, HookError):
    pass


class GlobalUncertain(HookUncertain):
    pass


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def _hash(value):
    return hashlib.sha256(value).hexdigest()


def _read_receipt(path):
    with path.open('rb') as stream:
        raw = stream.read(MAX_POOL_JOURNAL_BYTES + 1)
    if len(raw) > MAX_POOL_JOURNAL_BYTES:
        raise GlobalUncertain('The pool receipt exceeds its exact byte bound.')
    return raw


def has_global_alloc(source):
    return re.search(r'^\s*globalalloc\s*\(', aa._clean_source(source), re.I|re.M) is not None


def prepare_global_program(source, process_name=None, *, bitness=64):
    """Parse the original source, with no target read, allocation or execution."""
    if type(bitness) is not int or bitness not in (32, 64):
        raise GlobalError('Global profile requires explicit x86/x64 bitness.')
    clean = aa._clean_source(source)
    lines = clean.splitlines()
    globals_, phase = {}, None
    for index, raw in enumerate(lines):
        line = raw.strip()
        if line.upper() in ('[ENABLE]', '[DISABLE]'):
            phase = line[1:-1].casefold()
        match = re.fullmatch(r'globalalloc\s*\((.*)\)', line, re.I)
        if match:
            if phase != 'enable':
                raise GlobalError('Globals must be explicitly declared in ENABLE.')
            args = aa._args(match.group(1))
            if len(args) not in (2, 3):
                raise GlobalError('globalalloc requires name, size and optional near expression.')
            name = validate_symbol(args[0])
            try:
                size = integer(args[1])
            except AddressExpressionError as exc:
                raise GlobalError('Global declaration size is not a bounded integer: ' + str(exc)) from exc
            if name.casefold() in globals_ or len(globals_) == MAX_GLOBALS:
                raise GlobalError('Duplicate or excessive global declarations.')
            if not 1 <= size <= MAX_GLOBAL_BYTES:
                raise GlobalError('RW global size must be 1..65536 bytes.')
            globals_[name.casefold()] = {'name': name, 'size': size,
                'near': aa._expression(args[2]) if len(args) == 3 else None,
                'initializer': '', 'executable': False, 'writable': True,
                'declaration_line': index + 1, 'initializer_present': False}
    if not globals_:
        raise GlobalError('No global declaration exists in this source.')
    defines = {}
    for raw in lines:
        match = re.fullmatch(r'define\s*\((.*)\)', raw.strip(), re.I)
        if match:
            args = aa._args(match.group(1))
            if len(args) != 2 or len(defines) >= 128:
                raise GlobalError('A bounded source define closure is required.')
            name = validate_symbol(args[0]).casefold()
            if name in defines:
                raise GlobalError('Duplicate source definitions are outside the global profile.')
            defines[name] = args[1]
    reference_cache = {}
    reference_steps = 0
    def global_references(expression, stack=()):
        nonlocal reference_steps
        reference_steps += 1
        if reference_steps > 8192:
            raise GlobalError('Global cursor alias closure exceeds its aggregate work bound.')
        if len(stack) >= 64:
            raise GlobalError('Global cursor alias closure exceeds its depth bound.')
        try:
            names = [x.casefold() for x in aa.expression_symbols(expression)]
        except AddressExpressionError as exc:
            if expression.strip().startswith('@@'):
                raise GlobalError("The NASM current-address cursor '@@' is only supported as the '@@:' label line and cannot be used as an address expression.") from exc
            raise GlobalError('Global cursor expression is not a valid address expression: ' + str(exc)) from exc
        for name in names:
            if name in globals_:
                return True
            if name in stack:
                raise GlobalError('Cyclic cursor aliases are outside the shared profile.')
            if name in defines:
                if name not in reference_cache:
                    reference_cache[name] = global_references(defines[name], stack + (name,))
                if reference_cache[name]:
                    return True
        return False
    transformed, phase, cursor, cursor_expr = [], None, None, None
    initializer_seen = set()
    # Staged readmem candidates are collected per direction and validated as a
    # pair after the loop: the shared profile admits only the paired
    # ENABLE/DISABLE shape, so an unpaired readmem touching a global keeps the
    # established visible refusal.
    candidates_target, candidates_target2 = {}, {}
    for raw in lines:
        line = raw.strip()
        if not line:
            transformed.append(raw)
            continue
        if line.upper() in ('[ENABLE]', '[DISABLE]'):
            phase, cursor, cursor_expr = line[1:-1].casefold(), None, None
            transformed.append(line)
            continue
        if re.fullmatch(r'globalalloc\s*\(.*\)', line, re.I):
            continue
        match = re.fullmatch(r'(.+):', line)
        if match:
            expression = match.group(1).strip()
            if expression == '@@':
                # NASM current-address cursor: a positional marker, not a
                # named cursor. It changes no global-cursor context (data
                # lines after it still belong to the enclosing cursor) and
                # emits no plan operation. Inside a global initializer
                # region the marker is consumed with the data lines: its
                # position names a byte offset within the global buffer,
                # which lives in the pool allocation, not in the consumer
                # program. Outside that region the line passes through to
                # the consumer source, where the AA dialect owns the
                # anonymous-label (@f/@b) semantics.
                if cursor is None:
                    transformed.append(raw)
                continue
            cursor_expr = expression
            cursor = expression.casefold() if expression.casefold() in globals_ else None
            # Indirect global cursors cannot disguise executable/global writes.
            if global_references(expression) and cursor is None:
                raise GlobalError('Only a direct global cursor can initialize shared storage.')
            if cursor is not None:
                if phase != 'enable' or cursor in initializer_seen:
                    raise GlobalError('Global initialization requires one direct ENABLE cursor.')
                initializer_seen.add(cursor)
                globals_[cursor]['initializer_present'] = True
                continue
        node = aa._parse_line(line)
        if node['op'] == 'readmem':
            references_global = global_references(node['address'])
            if cursor is not None:
                # Staged ENABLE shape: readmem(target, size) under the direct
                # global cursor copies target bytes into the live global
                # allocation at activation time; the line is stripped from
                # the consumer source and re-derived deterministically.
                if phase != 'enable':
                    raise GlobalError('Staged global readmem under a global cursor requires the ENABLE section.')
                if references_global:
                    raise GlobalError('Staged global readmem cannot reference a declared global.')
                item = globals_[cursor]
                size = node['size']
                if not 1 <= size <= item['size']:
                    raise GlobalError('Staged readmem size exceeds the declared global allocation size.')
                if cursor in candidates_target:
                    raise GlobalError('At most one staged readmem may stage bytes into each global.')
                candidates_target[cursor] = {'op': 'readmem', 'direction': 'target_to_global',
                                             'global': item['name'], 'address': node['address'],
                                             'size': size, 'phase': 'enable'}
                continue
            if references_global:
                # Staged DISABLE shape: readmem(global, size) under a target
                # cursor copies the live global bytes back to the cursor
                # address at deactivation time.
                if phase != 'disable' or cursor_expr is None:
                    raise GlobalError('readmem of a declared global is staged only under a target DISABLE cursor.')
                symbols = aa.expression_symbols(node['address'])
                if (len(symbols) != 1 or symbols[0].casefold() not in globals_
                        or node['address'].strip().casefold() != symbols[0].casefold()):
                    raise GlobalError('Staged global readmem must name the declared global without offset or expression.')
                key = symbols[0].casefold()
                item = globals_[key]
                size = node['size']
                if not 1 <= size <= item['size']:
                    raise GlobalError('Staged readmem size exceeds the declared global allocation size.')
                if key in candidates_target2:
                    raise GlobalError('At most one staged readmem may restore bytes from each global.')
                candidates_target2[key] = {'op': 'readmem', 'direction': 'global_to_target',
                                           'global': item['name'], 'address': cursor_expr,
                                           'size': size, 'phase': 'disable'}
                continue
        if node['op'] in ('assert','reassemble') and global_references(node['address']):
            raise GlobalError('Read/assert/reassemble of a newly declared global requires a future staged source profile.')
        if node['op'] in ('dealloc', 'register', 'unregister'):
            if node['symbols'] == ['*']:
                raise GlobalError('Wildcard cleanup is outside the shared-global profile.')
            local = [x for x in node['symbols'] if x.casefold() not in globals_]
            shared = [x for x in node['symbols'] if x.casefold() in globals_]
            if shared and ((node['op'] == 'register' and phase != 'enable')
                           or (node['op'] == 'unregister' and phase != 'disable')):
                raise GlobalError('Implicit global registration/cleanup must match ENABLE/DISABLE.')
            if shared and node['op'] == 'dealloc' and phase != 'disable':
                raise GlobalError('Global dealloc is only a DISABLE lease-release declaration.')
            if local:
                command = {'register': 'registersymbol', 'unregister': 'unregistersymbol'}.get(node['op'], node['op'])
                transformed.append(command + '(' + ','.join(local) + ')')
            continue
        if node['op'] in ('alloc', 'define', 'label'):
            owned = [node['symbol']] if 'symbol' in node else node['symbols']
            if any(x.casefold() in globals_ for x in owned):
                raise GlobalError('A global cannot be redefined as local storage or a label.')
            if cursor is not None and node['op'] == 'label':
                raise GlobalError('Labels inside a global initializer are outside the direct literal profile.')
        if cursor is not None and node['op'] in ('data', 'instruction', 'nops', 'align', 'readmem', 'reassemble'):
            if cursor in candidates_target:
                raise GlobalError('A global cannot mix literal initializers with staged readmem.')
            if phase != 'enable' or not aa._literal_data(node):
                raise GlobalError('Only scalar/string db/dw/dd/dq initializers are supported; readmem/code globals remain blocked.')
            raw_bytes = aa._literal_bytes(node, None, None)
            item = globals_[cursor]
            if len(bytes.fromhex(item['initializer'])) + len(raw_bytes) > item['size']:
                raise GlobalError('Global initializer crosses its declared storage size.')
            item['initializer'] += raw_bytes.hex()
            continue
        transformed.append(raw)
    # Pairing and mixing validation for staged candidates: the shared profile
    # admits only the paired ENABLE-staging plus DISABLE-restoration shape per
    # global, and no literal initializer may coexist with staged readmem for
    # the same global. An unpaired readmem touching a global keeps the
    # established visible refusal.
    for item in globals_.values():
        if (item['name'].casefold() in candidates_target
                or item['name'].casefold() in candidates_target2) and item['initializer']:
            raise GlobalError('A global cannot mix literal initializers with staged readmem.')
    if set(candidates_target) != set(candidates_target2):
        unpaired = sorted(set(candidates_target) ^ set(candidates_target2))
        raise GlobalError('Staged readmem requires the paired ENABLE staging and DISABLE restoration shape; unpaired global readmem remains blocked: '
                          + ', '.join(globals_[key]['name'] for key in unpaired))
    staged_ops = list(candidates_target.values()) + list(candidates_target2.values())
    if any(x['initializer_present'] and not x['initializer'] and not any(
            op['global'].casefold() == x['name'].casefold()
            and op['direction'] == 'target_to_global' for op in staged_ops)
            for x in globals_.values()):
        raise GlobalError('An initializer cursor must contain bounded literal data or staged readmem.')
    if any(x['near'] and global_references(x['near']) for x in globals_.values()):
        raise GlobalError('A global near anchor cannot depend on global allocation aliases.')
    # Source-only diagnostic aliases. Runtime aliases are freshly regenerated
    # from an opaque live lease and never accepted from serialized plan fields.
    consumer_source = '\n'.join(transformed)
    diagnostic_source = _alias_source(consumer_source,
        {item['name']: 0x10000 + index * 0x10000 for index, item in enumerate(globals_.values())})
    program = aa.prepare_program(diagnostic_source, process_name, bitness=bitness)
    scans=[node for node in program['enable'] if node['op'] in {'scan','scan_process','scan_region'}]
    if len(scans)>64:
        raise GlobalError('The shared profile allows at most 64 original scan captures.')
    if any(node['op']=='scan_region' and (global_references(node['start']) or global_references(node['end'])) for node in scans):
        raise GlobalError('Original scan bounds cannot depend on newly allocated globals.')
    provided = list(program['provides']) + [x['name'] for x in globals_.values()]
    local = {x['symbol'].casefold() for phase in ('preamble','enable') for x in program[phase]
             if x['op'] in ('define','alloc','scan','scan_process','scan_region')}
    required = list(program['requires'])
    for item in globals_.values():
        for name in aa.expression_symbols(item['near'] or '0'):
            if name.casefold() in globals_:
                raise GlobalError('Global near expressions cannot depend on another global allocation.')
            if name.casefold() not in local and name.casefold() not in {x.casefold() for x in required}:
                required.append(name)
    profile = {'schema': SCHEMA, 'source': source,
               'source_sha256': _hash(source.encode('utf-8')), 'bitness': bitness,
               'process_name':process_name, 'provides':provided, 'requires':required,
               'globals': list(globals_.values()), 'consumer_source': consumer_source,
               'consumer_shape': {'provides': program['provides'], 'requires': program['requires'],
                                  'allocations': program['allocations'],
                                  'allocation_executable':program['allocation_executable'],
                                  # External literal cursors cannot prove RW ownership before
                                  # binding. Keep this first profile conservative: reserve no
                                  # globals unless a coordinator is available for any emission.
                                  'requires_coordinator': any(program['allocation_executable'].values()) or
                                      any(n['op'] in {'instruction','reassemble','data','nops','readmem','align'}
                                          for n in program['enable'])},
               'profile': ('staged-readmem-rw/v1' if staged_ops
                           else 'literal-rw-no-changed-reinitialization/v1')}
    # The staged plan is present only for staged sources; literal-only
    # profiles keep their exact pre-stage byte shape.
    if staged_ops:
        profile['staged_ops'] = staged_ops
    return profile


def _alias_source(source, aliases):
    return '\n'.join('define(' + name + ',0x' + format(address, 'X') + ')'
                     for name, address in aliases.items()) + '\n' + source


class _CapturedMemory:
    """Private controller view: original scans are checked, never searched again."""
    def __init__(self,capture):self._capture=capture
    def __getattr__(self,name):return getattr(self._capture.memory,name)
    def scan_process(self,pattern):return self._capture._scan('scan_process',(pattern,))
    def scan_module(self,module,pattern):return self._capture._scan('scan',(module,pattern))
    def scan_region(self,start,end,pattern):return self._capture._scan('scan_region',(start,end,pattern))


class GlobalScanCapture:
    """Source-bound opaque capture spanning alias binding and global allocation.

    All searches run once before allocation. A freshly regenerated consumer may
    issue its own source-hash receipt only through this exact live object, which
    rechecks the original address, wildcard bytes, identity and controller fence.
    No JSON scan/address/hash field can reconstruct a capture.
    """
    def __init__(self,authority,profile,memory,guard):
        if authority is not _AUTHORITY:raise GlobalError('Original scan captures are controller-only.')
        self.profile=_canonical(validate_global_program(profile))
        self.memory,self.guard=memory,guard
        self.identity,self.width=tuple(memory.identity),memory.pointer_size
        self.records=[];self.capturing=True;self.view=_CapturedMemory(self)

    @classmethod
    def prepare(cls,profile,memory,symbols,guard):
        from .lua_work_budget import broker_checkpoint
        capture=cls(_AUTHORITY,profile,memory,guard)
        capture.recheck()
        diagnostic=aa.prepare_program(_alias_source(profile['consumer_source'],{x['name']:0x10000+i*0x10000
                                      for i,x in enumerate(profile['globals'])}),profile['process_name'],bitness=profile['bitness'])
        broker_checkpoint()
        resolved=aa.preflight_program(diagnostic,capture.view,symbols)
        capture.capturing=False
        capture.recheck()
        return capture,resolved

    def _scan(self,op,args):
        from .lua_work_budget import broker_checkpoint
        broker_checkpoint();self.recheck()
        if self.capturing:
            method={'scan':'scan_module','scan_process':'scan_process','scan_region':'scan_region'}[op]
            address=getattr(self.memory,method)(*args)
            size=len(args[-1].split());raw=self.memory.read(address,size)
            from .patterns import pattern_matches
            if len(self.records)>=64 or sum(len(x['bytes']) for x in self.records)+size>262144:
                raise GlobalError('Original shared scan captures exceed their count/byte bound.')
            if type(address) is not int or not 0<address<(1<<(self.width*8)) or not pattern_matches(args[-1],raw):
                raise GlobalError('Original shared scan returned invalid target bytes/address.')
            row={'op':op,'args':args,'address':address,'bytes':raw}
            if op=='scan':
                row['module_extent']=tuple(self.memory.module(args[0]))
                base,length=row['module_extent']
                if not base<=address<address+size<=base+length:
                    raise GlobalError('Original module scan lies outside its held image extent.')
            self.records.append(row)
        else:
            matches=[x for x in self.records if x['op']==op and x['args']==args]
            if not matches or any((x['address'],x['bytes'])!=(matches[0]['address'],matches[0]['bytes']) for x in matches):
                raise GlobalError('Consumer scan differs from its exact original source capture.')
            address=matches[0]['address']
        self.recheck();broker_checkpoint()
        return address

    def bind(self,profile,program):
        if self.capturing or _canonical(validate_global_program(profile))!=self.profile:
            raise GlobalError('Original shared source capture has not completed or changed.')
        aa.validate_program(program)
        if (program['process_name'],program['bitness'])!=(profile['process_name'],profile['bitness']):
            raise GlobalError('Consumer context differs from the original scan source.')
        prefix=program['source'].splitlines()[:len(profile['globals'])]
        aliases={}
        for line,item in zip(prefix,profile['globals']):
            node=aa._parse_line(line)
            if node['op']!='define' or node['symbol']!=item['name']:
                raise GlobalError('Consumer aliases differ from the original global declarations.')
            aliases[node['symbol']]=integer(node['expression'])
        if (len(aliases)!=len(profile['globals']) or any(not 0<address<(1<<profile['bitness']) for address in aliases.values())
                or program['source']!=_alias_source(profile['consumer_source'],aliases)):
            raise GlobalError('Consumer differs from the exact original body and literal alias binding.')
        self.recheck()
        return self.view

    def recheck(self):
        from .lua_work_budget import broker_checkpoint
        broker_checkpoint()
        if (tuple(self.memory.identity)!=self.identity or self.memory.pointer_size!=self.width
                or self.memory.is_alive() is not True or self.guard() is not True):
            raise GlobalError('Original scan target/controller proof changed.')
        for row in self.records:
            if row['op']=='scan' and tuple(self.memory.module(row['args'][0]))!=row['module_extent']:
                raise GlobalError('Original module scan image extent changed.')
            if self.memory.read(row['address'],len(row['bytes']))!=row['bytes']:
                raise GlobalError('Original shared scan bytes changed; rebinding is forbidden.')
        broker_checkpoint()
        return True


def validate_global_program(profile):
    if not isinstance(profile, dict):
        raise GlobalError('Global source profile must be an object.')
    rebuilt = prepare_global_program(profile.get('source'), profile.get('process_name'), bitness=profile.get('bitness'))
    if _canonical(profile) != _canonical(rebuilt):
        raise GlobalError('Global profile differs from its exact original source.')
    return rebuilt


class GlobalLease:
    """Opaque controller-issued authority; its JSON diagnostic is not reusable."""
    def __init__(self, authority, pool, profile, record_id, activation):
        if authority is not _AUTHORITY:
            raise GlobalError('Only the live pool can issue a consumer lease.')
        self._pool, self._profile = pool, profile
        self.record_id, self.activation = record_id, activation
        self.nonce = secrets.token_hex(16)
        self.state, self._manager, self._binding, self._manager_path = 'prepared', None, None, None


class GlobalPool:
    """Fresh target/table/owner-bound pool. Existing journals block reopening.

    The engine must claim its shared target lock before constructing this pool.
    controller_guard rechecks that lock on every operation. No persisted address
    or lease can be imported to reconstruct this live object.
    """
    def __init__(self, memory, directory, *, trainer_id, table_sha256, controller_guard,
                 external_symbols=lambda: {}):
        if (not re.fullmatch('[0-9a-f]{16}', trainer_id or '')
                or not re.fullmatch('[0-9a-f]{64}', table_sha256 or '')
                or not callable(controller_guard) or not callable(external_symbols)):
            raise GlobalError('The pool requires a canonical owner/table and live controller guard.')
        if memory.pointer_size not in (4, 8) or not memory.is_alive():
            raise GlobalError('An exact live x86/x64 target is required.')
        if controller_guard() is not True:
            raise GlobalError('The shared target/controller lock is not held.')
        self.memory, self.identity = memory, tuple(memory.identity)
        self.path = Path(directory).resolve() / 'global-pool.json'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Never reopen or overwrite a crash receipt; recovery must prove death.
        self._bytes = b''
        with self.path.open('xb') as stream:
            stream.write(b'')
            stream.flush()
            os.fsync(stream.fileno())
        self.trainer_id, self.table_sha256 = trainer_id, table_sha256
        self.controller_guard, self.external_symbols = controller_guard, external_symbols
        self.nonce, self.state = secrets.token_hex(16), 'live'
        self.members, self.leases, self.pending = {}, {}, []
        self.thread_id = threading.get_ident()
        self._save()

    def _snapshot(self):
        return {'schema': POOL_SCHEMA, 'trainer_id': self.trainer_id,
                'table_sha256': self.table_sha256, 'target': list(self.identity),
                'pool_nonce': self.nonce, 'state': self.state,
                'pending': [{k: v for k, v in item.items() if k != 'manager'} for item in self.pending],
                'members': [{k: v for k, v in item.items() if k != 'manager'}
                            for item in self.members.values()],
                'consumers': [{'nonce': lease.nonce, 'record_id': lease.record_id,
                              'activation': lease.activation, 'source_sha256': lease._profile['source_sha256'],
                              'globals': [x['name'] for x in lease._profile['globals']], 'state': lease.state,
                              'consumer_journal': str(lease._manager.path) if lease._manager else lease._manager_path}
                             for lease in self.leases.values()]}

    def _save(self):
        if self._bytes is not None and _read_receipt(self.path) != self._bytes:
            raise GlobalUncertain('The exact pool journal changed; ownership is uncertain.')
        raw = _canonical(self._snapshot()) + b'\n'
        if len(raw) > MAX_POOL_JOURNAL_BYTES:
            raise GlobalUncertain('The bounded pool journal capacity is exhausted.')
        temporary = self.path.with_name(self.path.name + '.' + secrets.token_hex(16) + '.tmp')
        # Mirrors the first-party hook journal's checked temp/replace protocol.
        # StateStore must retain its exact lock/fence through every operation;
        # this is one file only and never claims multi-file atomicity.
        with temporary.open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if _read_receipt(temporary) != raw or _read_receipt(self.path) != self._bytes:
            raise GlobalUncertain('Pool journal replacement is uncertain; preserve every file.')
        os.replace(temporary, self.path)
        self._bytes = raw
        if _read_receipt(self.path) != raw:
            raise GlobalUncertain('The pool journal did not round-trip exactly.')

    def _uncertain(self, exc):
        self.state = 'uncertain'
        try:
            self._save()
        except Exception:
            pass  # preserve originals/receipts; never clean up ambiguous pages
        return GlobalUncertain(str(exc))

    def _guard(self):
        if threading.get_ident() != self.thread_id:
            raise GlobalError('The first global profile is serialized on its owning controller thread.')
        if self.state != 'live':
            raise GlobalUncertain('This pool is retired or uncertain.')
        try:
            if _read_receipt(self.path) != self._bytes:
                raise GlobalError('The pool journal changed externally.')
            if (tuple(self.memory.identity) != self.identity or not self.memory.is_alive()
                    or self.controller_guard() is not True):
                raise GlobalError('The exact target/controller ownership proof changed.')
            for item in self.members.values():
                manager = item['manager']
                if manager.state != 'enabled':
                    raise GlobalError('A global allocation is not durably published.')
                manager.check_entries()
                manager._verify_allocation_protection(item['address'], item['actual_size'], executable=False, writable=True)
            for lease in self.leases.values():
                if lease._manager is not None and lease.state == 'enabled':
                    if lease._manager.state == 'retired':
                        lease._manager.receipt()  # normal disable precedes explicit lease release
                    else:
                        lease._manager.check_entries()
                elif lease._manager is not None and lease.state == 'released' and lease._manager.path.exists():
                    lease._manager.receipt()
            foreign = {str(name).casefold() for name in self.external_symbols()}
            if foreign.intersection(self.members):
                raise GlobalError('An external symbol collides with a pool-owned global.')
        except Exception as exc:
            raise self._uncertain(exc) from exc

    def _lease(self, lease, *, states=('prepared', 'enabled')):
        self._guard()
        if (not isinstance(lease, GlobalLease) or lease._pool is not self
                or self.leases.get(lease.nonce) is not lease or lease.state not in states):
            raise GlobalError('The exact live consumer lease is required.')
        validate_global_program(lease._profile)
        return lease

    def _admit_target_budget(self, requests):
        allocations = [(x['actual_size']) for x in self.members.values()]
        for lease in self.leases.values():
            if lease._manager is not None:
                allocations.extend(x['actual_size'] for x in lease._manager.allocations.values()
                                   if x['address'] is not None and x['state'] != 'released-unpublished')
        reserved = lambda size: ((size + 65535) // 65536) * 65536
        if (len(allocations) + len(requests) > MAX_HOOK_ALLOCATIONS
                or sum(reserved(x) for x in allocations) + sum(reserved(x['size']) for x in requests) > MAX_HOOK_BYTES):
            raise GlobalError('Combined global and retained consumer target-lifetime allocation budget is exhausted.')

    def acquire(self, profile, *, record_id, activation, symbols=None):
        profile = validate_global_program(profile)
        self._guard()
        if profile['bitness'] != self.memory.pointer_size * 8:
            raise GlobalError('Source/target architecture differs before global allocation.')
        if (type(record_id) is not int or not 0 <= record_id <= 0x7FFFFFFF
                or not isinstance(activation, str) or not re.fullmatch('[A-Za-z0-9_-]{1,64}', activation)):
            raise GlobalError('A bounded selected record and unique activation identifier are required.')
        if any(x.activation == activation and x.state in ('prepared', 'enabled') for x in self.leases.values()):
            raise GlobalError('The activation already owns a live global lease.')
        foreign = {str(name).casefold() for name in self.external_symbols()}
        resolved = []
        for request in profile['globals']:
            name = request['name'].casefold()
            if name in foreign:
                raise GlobalError('A global name collides with an external provider.')
            if request['near']:
                # WP-36: the near anchor may be a module token ($process or a
                # basename); module resolution needs the target's exact
                # process name and pointer width, mirroring the engine's
                # staged-copy range resolution.
                near = resolve_expression(request['near'], self.memory, symbols or {},
                                          process_name=profile['process_name'],
                                          pointer_size=profile['bitness'] // 8)
            else:
                near = None
            if near is not None and not 0 <= near < (1 << profile['bitness']):
                raise GlobalError('The near anchor exceeds the target address width.')
            existing = self.members.get(name)
            if existing:
                if (existing['size'], existing['near'], existing['executable'], existing['writable']) != (request['size'], near, False, True):
                    raise GlobalError('An existing global cannot be resized, relocated or reprotected.')
                active = [x for x in self.leases.values() if x.state in ('prepared', 'enabled')
                          and any(r['name'].casefold() == name for r in x._profile['globals'])]
                if request['initializer_present']:
                    if active:
                        raise GlobalError('A global initializer cannot run while another consumer owns the storage.')
                    raw = bytes.fromhex(request['initializer'])
                    if raw and self.memory.read(existing['address'], len(raw)) != raw:
                        raise GlobalError('Changed global reinitialization requires a future verified data-commit profile.')
            resolved.append((name, request, near))
        new = [x for x in resolved if x[0] not in self.members]
        if len(self.leases) == MAX_LEASES:
            raise GlobalError('The bounded target-lifetime consumer journal is full.')
        if len(self.members) + len(new) > MAX_GLOBALS or sum(max(65536, x['actual_size']) for x in self.members.values()) + len(new) * 65536 > MAX_POOL_BYTES:
            raise GlobalError('The target-lifetime global allocation budget is exhausted.')
        self._admit_target_budget([x[1] for x in new])
        lease = GlobalLease(_AUTHORITY, self, profile, record_id, activation)
        self.leases[lease.nonce] = lease
        try:
            self._save()  # bind source/consumer before the first allocation intent
            for name, request, near in new:
                journal = self.path.parent / ('global-' + name + '-' + secrets.token_hex(8) + '.json')
                intent = {'name': request['name'], 'size': request['size'], 'near': near,
                          'journal': str(journal), 'state': 'allocation-intent', 'source_sha256': profile['source_sha256']}
                self.pending.append(intent)
                self._save()
                manager = HookManager(self.memory, journal, owner_id=self.trainer_id,
                                      publication_guard=self._guard)
                intent['manager'] = manager
                address = manager.allocate(request['name'], request['size'], near, executable=False, writable=True)
                actual = self.memory.allocation_size(address)
                raw = bytes.fromhex(request['initializer'])
                if raw:
                    block = {'address': address, 'bytes': raw.hex(), 'original': bytes(len(raw)).hex(),
                             'is_allocation': True, 'executable': False, 'requires_coordinator': False}
                    manager.stage([block])
                    manager.publish()  # no live entry; allocation is exposed only after this receipt
                else:
                    # Staged-readmem globals own no literal initializer bytes;
                    # publish the held allocation alone so the guarded staged
                    # copies can write into it later.
                    manager.commit()
                self.members[name] = {'name': request['name'], 'size': request['size'], 'near': near,
                    'executable': False, 'writable': True, 'address': address, 'actual_size': actual,
                    'initializer': request['initializer'], 'source_sha256': profile['source_sha256'],
                    'journal': str(journal), 'manager': manager}
                self.pending.remove(intent)
                self._save()
            self._guard()
            return lease
        except Exception as exc:
            lease.state = 'uncertain'
            # Allocation/reachable receipt ambiguity always retains storage;
            # never free based on a failed high-level acquisition alone.
            raise self._uncertain(exc) from exc

    def binding(self, lease):
        lease = self._lease(lease, states=('prepared',))
        aliases = {r['name']: self.members[r['name'].casefold()]['address'] for r in lease._profile['globals']}
        program = aa.prepare_program(_alias_source(lease._profile['consumer_source'], aliases),
                                     lease._profile['process_name'], bitness=lease._profile['bitness'])
        lease._binding = _canonical(program)
        return program

    def make_consumer(self, lease, journal_path, *, coordinator=None, owned_data_ranges=(),
                      owned_executable_data_ranges=(),publication_guard=None):
        lease = self._lease(lease, states=('prepared',))
        if lease._manager is not None:
            raise GlobalError('A lease can own exactly one consumer transaction.')
        if lease._binding is None:
            raise GlobalError('Bind the exact consumer source before reserving its target budget.')
        program = json.loads(lease._binding)
        self._admit_target_budget([x for x in program['enable'] if x['op'] == 'alloc'])
        lease._manager_path = str(Path(journal_path).resolve())
        try:
            self._save()  # retain exact consumer journal intent before constructor effects
            def guard():
                self.verify_publication(lease)
                if publication_guard is not None: publication_guard()
            manager = HookManager(self.memory, journal_path, coordinator, owner_id=self.trainer_id,
                                  owned_data_ranges=tuple((self.members[r['name'].casefold()]['address'], r['size'])
                                                          for r in lease._profile['globals']) + tuple(owned_data_ranges),
                                  owned_executable_data_ranges=owned_executable_data_ranges,
                                  publication_guard=guard)
            lease._manager = manager
            self._save()
            return manager
        except Exception as exc:
            raise self._uncertain(exc) from exc

    def verify_publication(self, lease):
        self._lease(lease, states=('prepared',))
        if lease._binding is None:
            raise GlobalError('The original source must be bound before consumer publication.')
        for request in lease._profile['globals']:
            raw = bytes.fromhex(request['initializer'])
            if raw and self.memory.read(self.members[request['name'].casefold()]['address'], len(raw)) != raw:
                raise GlobalError('The source initializer changed before held consumer publication.')
        manager = lease._manager
        if manager is None:
            raise GlobalError('A consumer must own its exact staged transaction.')
        for entry in manager.entries:
            start, size = entry['address'], len(bytes.fromhex(entry['bytes']))
            if any(start < item['address'] + item['actual_size'] and item['address'] < start + size
                   for item in self.members.values()):
                raise GlobalError('Ordinary consumer entries cannot rewrite pool globals or allocation padding.')
            for other in self.leases.values():
                if other is lease or other.state not in ('prepared', 'enabled') or other._manager is None or other._manager.state == 'retired':
                    continue
                if any(start < existing['address'] + len(bytes.fromhex(existing['bytes']))
                       and existing['address'] < start + size for existing in other._manager.entries):
                    raise GlobalError('Independent global consumers cannot overlap live entry ownership.')
        # The root engine must link exactly binding(lease); the opaque lease is
        # controller-only and guards ownership, not arbitrary Python callers.
        return True

    def confirm_enabled(self, lease, program):
        self._lease(lease, states=('prepared',))
        aa.validate_program(program)
        if _canonical(program) != lease._binding:
            raise GlobalError('A consumer cannot confirm a different source/address binding.')
        manager = lease._manager
        if manager is None or manager.state != 'enabled':
            raise GlobalError('The exact consumer transaction has not published.')
        manager.check_entries()
        lease.state = 'enabled'
        self._save()

    def release(self, lease):
        self._lease(lease)
        manager = lease._manager
        if manager is not None:
            if not (manager.state == 'abandoned' and not manager.path.exists()
                    and not manager.uncertain and not manager.exports
                    and all(x['state'] == 'released-unpublished' for x in manager.allocations.values())
                    and not any(x['state'] in ('installed', 'restored') for x in manager.entries)):
                manager.receipt()
            if manager.state not in ('retired', 'abandoned'):
                raise GlobalError('Consumer entries must be restored before releasing a global lease.')
        elif lease.state != 'prepared':
            raise GlobalError('An enabled consumer lacks its exact transaction receipt.')
        lease.state = 'released'
        self._save()  # no free: retired code may still retain the global pointer

    def staged_read(self, lease, global_name, size, offset=0):
        """Staged DISABLE staging: read live bytes from a held global allocation.

        Runs under the exact pool/lease guard: target identity, liveness,
        controller lock, member manager state and allocation protection are
        rechecked before the read.
        """
        lease = self._lease(lease, states=('prepared', 'enabled'))
        member = self.members.get(global_name.casefold())
        if member is None:
            raise GlobalError('Staged global read has no live pool member.')
        if (type(offset) is not int or offset < 0 or type(size) is not int
                or not 1 <= size or offset + size > member['size']):
            raise GlobalError('Staged global read crosses its declared allocation size.')
        raw = self.memory.read(member['address'] + offset, size)
        if len(raw) != size:
            raise GlobalError('Staged global read returned incomplete bytes.')
        return raw

    def staged_write(self, lease, global_name, data, offset=0):
        """Staged ENABLE staging: copy target bytes into a held global allocation.

        The same guarded write-and-readback contract as the acquire-time
        initializer write; any drift or failure marks the pool uncertain and
        preserves every receipt (fail-closed).
        """
        lease = self._lease(lease, states=('prepared', 'enabled'))
        member = self.members.get(global_name.casefold())
        if member is None:
            raise GlobalError('Staged global write has no live pool member.')
        if not isinstance(data, (bytes, bytearray)) or not data:
            raise GlobalError('Staged global write requires non-empty bytes.')
        data = bytes(data)
        if type(offset) is not int or offset < 0 or offset + len(data) > member['size']:
            raise GlobalError('Staged global write crosses its declared allocation size.')
        address = member['address'] + offset
        try:
            original = self.memory.read(address, len(data))
            if self.memory.read(address, len(data)) != original:
                raise GlobalError('Staged global storage changed immediately before the write.')
            self.memory.write(address, data)
            if self.memory.read(address, len(data)) != data:
                raise GlobalError('Staged global write did not verify.')
        except Exception as exc:
            raise self._uncertain(exc) from exc

    def diagnostic(self):
        self._guard()
        return json.loads(_canonical(self._snapshot()))

    def symbols(self):
        self._guard()
        return {item['name'].casefold():self.members[item['name'].casefold()]['address']
                for lease in self.leases.values() if lease.state == 'enabled'
                for item in lease._profile['globals']}

    def active_data_ranges(self):
        names=set(self.symbols())
        return tuple((item['address'],item['size']) for name,item in self.members.items() if name in names)

    def finish_unexposed(self):
        """Release only an exact empty claim; no allocation or consumer exists."""
        self._guard()
        if self.members or self.pending or self.leases:
            raise GlobalError('An exposed or pending global pool cannot close while its target lives.')
        self.state='unexposed-closed'
        self._save()
        if (_read_receipt(self.path)!=self._bytes or tuple(self.memory.identity)!=self.identity
                or self.memory.is_alive() is not True or self.controller_guard() is not True):
            raise GlobalUncertain('The exact unexposed claim proof changed before release.')
        self.path.unlink()

    def finish_after_exit(self, *, remove_journal=False):
        if _read_receipt(self.path) != self._bytes or tuple(self.memory.identity) != self.identity or self.memory.is_alive():
            raise GlobalError('Exact target death and original receipts are required.')
        if self.controller_guard() is not True:
            raise GlobalError('The controller lock must remain held during target-exit retirement.')
        for item in self.members.values():
            item['manager'].finish_after_exit()
        self.state = 'target-exited'
        for lease in self.leases.values():
            lease.state = 'target-exited'
        self._save()  # retain compact evidence; never remotely free or revive JSON
        if remove_journal:
            if _read_receipt(self.path)!=self._bytes or tuple(self.memory.identity)!=self.identity or self.memory.is_alive():
                raise GlobalUncertain('Global terminal receipt/target death changed before exact release.')
            self.path.unlink()


def shared_global_names(entry):
    profile=entry.get('global_program')
    return {x['name'].casefold() for x in profile['globals']} if isinstance(profile,dict) else set()


def shared_provider_compatible(candidates, symbol):
    definitions=[]
    for entry in candidates:
        if symbol not in shared_global_names(entry): return False
        definitions.extend((x['size'],x['near'],x['executable'],x['writable'])
                           for x in entry['global_program']['globals'] if x['name'].casefold()==symbol)
    return bool(definitions) and all(x==definitions[0] for x in definitions)
