"""Activation-owned Lua mutations and AA receipts, independent of CE code."""
from __future__ import annotations
from .restoration_budget import restoration_entry

import hashlib
import json
import os
import re
import uuid

from .lua_work_budget import controller_cleanup, broker_checkpoint

from .aa import validate_symbol
from .engine import NativeRuntimeError, PatchConflict, StateError, _Patch
from .lua_bootstrap import table_lua_bootstrap_gate
from .lua_host import EngineLuaBroker, LuaHost, LuaHostError


def finalized_receipt(receipt, plan):
    """Strictly admit only terminal, bound Lua receipts on controller restart."""
    if (not isinstance(receipt, dict) or receipt.get('schema') != 'ct2trainer-lua-activation/v1'
            or receipt.get('engine') != 'ct2trainer-lua'
            or receipt.get('trainer_id') != plan['trainer_id']
            or receipt.get('table_sha256') != plan['table_sha256']
            or receipt.get('state') not in {'abandoned', 'target-exited'}
            or type(receipt.get('owner')) is not int
            or not any(entry['id'] == receipt['owner'] and entry['kind'] == 'script' for entry in plan['entries'])
            or receipt.get('symbols') != {} or receipt.get('assemblies') != {}
            or receipt.get('pending') is not None):
        return False
    target, data = receipt.get('target'), receipt.get('data')
    if (not isinstance(target, list) or len(target) != 2 or any(type(value) is not int or value <= 0 for value in target)
            or not isinstance(data, list) or len(data) > 1024):
        return False
    if 'nth_aob_results' in receipt:
        from .nth_aob import NthAOBError, validate_result, MAX_DEFINITIONS
        results = receipt['nth_aob_results']
        if type(results) is not list or not 1 <= len(results) <= MAX_DEFINITIONS:
            return False
        owner = next(entry for entry in plan['entries'] if entry['id'] == receipt['owner'])
        definitions = owner.get('lua_program', {}).get('dynamic_definitions', [])
        seen = set()
        try:
            for result in results:
                validate_result(result)
                key = result['definition']['symbol'].casefold()
                if result['target'] != target or result['definition'] not in definitions or key in seen:
                    return False
                seen.add(key)
        except NthAOBError:
            return False
    total = 0
    for item in data:
        if (not isinstance(item, dict) or set(item) != {'address', 'original', 'current'}
                or type(item['address']) is not int or not 0 < item['address'] <= 0x7FFFFFFFFFFF
                or not all(isinstance(item[key], str) and re.fullmatch(r'(?:[0-9a-fA-F]{2}){1,65536}', item[key])
                           for key in ('original', 'current'))
                or len(item['original']) != len(item['current'])
                or receipt['state'] == 'abandoned' and item['original'] != item['current']):
            return False
        total += len(item['original']) // 2
    return total <= 1024 * 1024


class LuaActivation:
    """One active record's callbacks, symbols, exact data undo and hook receipts.

    The journal precedes every data mutation. Executable changes use the same
    HookManager path as declarative records. A crash keeps both receipt types;
    automatic crash recovery is deliberately not inferred from successful undo.
    """

    def __init__(self, engine, identifier: int):
        self.engine, self.identifier = engine, identifier
        self.identity = engine.memory.identity
        self.state = 'open'
        self.data: dict[tuple[int, int], dict] = {}
        self.symbols: dict[str, int] = {}
        self.assemblies: dict[str, dict] = {}
        self.pending = None
        self.record_program = None
        self.record_assembly_token = None
        self.nth_aob_results = []
        self.expected_journal = None
        self.path = engine.store.directory / 'hooks' / ('lua-' + uuid.uuid4().hex + '.json')
        self.broker = EngineLuaBroker(engine, mutation_handler=self.mutate, assembler_handler=self.assemble)
        self.broker.syntaxcheck_assembler = True
        self.host = LuaHost(self.broker, owner_record_id=identifier, memory_pool=engine.lua_memory_pool)
        self._save(initial=True)

    def _document(self):
        document = {'schema': 'ct2trainer-lua-activation/v1', 'engine': 'ct2trainer-lua',
                'trainer_id': self.engine.plan['trainer_id'], 'table_sha256': self.engine.plan['table_sha256'],
                'state': self.state,
                'target': list(self.identity), 'owner': self.identifier,
                'data': list(self.data.values()), 'symbols': self.symbols,
                'assemblies': {token: {'source_sha256': item['hash'],
                    'journal': str(item['manager'].path)} for token, item in self.assemblies.items()},
                'pending': self.pending}
        if self.nth_aob_results:
            document['nth_aob_results'] = self.nth_aob_results
        return document

    def _save(self, *, initial=False):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(self._document(), sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        if len(raw) > 8 * 1024 * 1024:
            raise StateError('Lua activation receipt exceeds its bound')
        if initial:
            with self.path.open('xb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        else:
            self._journal_guard()
            temporary = self.path.with_name(self.path.name + '.' + uuid.uuid4().hex + '.tmp')
            with temporary.open('xb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            self._journal_guard()
            os.replace(temporary, self.path)
        self.expected_journal = raw
        self._journal_guard()

    def _journal_guard(self):
        if self.path.is_symlink() or self.path.read_bytes() != self.expected_journal:
            raise StateError('Lua activation receipt changed externally')

    def _guard(self):
        self.engine._guard()
        if self.engine.memory.identity != self.identity or self.state not in {'open', 'data-write-intent', 'closing'}:
            raise LuaHostError('Lua activation is retired or belongs to another target')
        self._journal_guard()

    def check(self):
        self._guard()
        if self.state != 'open':
            raise StateError('A Lua activation mutation has not been finalized')
        for item in self.data.values():
            raw = bytes.fromhex(item['current'])
            if self.engine.memory.read(item['address'], len(raw)) != raw:
                raise PatchConflict('Lua-owned bytes changed externally; undo is refused')
        for name, value in self.symbols.items():
            if self.engine.symbols.get(name) != value:
                raise PatchConflict('Lua-owned symbol changed externally')
        for manager in self.managers():
            manager.check_entries()

    def managers(self):
        return [item['manager'] for item in self.assemblies.values()]

    def overlaps(self, address, size):
        ranges = [(item['address'], len(bytes.fromhex(item['current']))) for item in self.data.values()]
        ranges += [(item['address'], len(bytes.fromhex(item['bytes'])))
                   for manager in self.managers() for item in manager.entries]
        return any(address < start + length and start < address + size for start, length in ranges)

    def _fail(self, exc):
        self.state = 'uncertain'
        self.engine._block(StateError('Lua activation mutation is uncertain: ' + str(exc)))
        self.broker.invalidate()
        self.host.cancel()

    def mutate(self, operation, arguments):
        self.check()
        if operation == 'write':
            address, raw = arguments
            if type(address) is not int or type(raw) is not bytes or not 0 < len(raw) <= 65536:
                raise LuaHostError('Invalid bounded Lua memory mutation')
            self.engine.memory._range(address, len(raw))
            if self.engine._is_executable(address, len(raw)):
                raise LuaHostError('Executable Lua writes require autoAssemble with an owned receipt')
            key = address, len(raw)
            if key not in self.data and self.overlaps(address, len(raw)):
                raise LuaHostError('Lua write overlaps a different owned mutation')
            for patches in self.engine.applied.values():
                if any(address < p.address + len(p.changed) and p.address < address + len(raw) for p in patches):
                    raise LuaHostError('Lua write overlaps an active record patch')
            if any(address < start + len(data) and start < address + len(raw)
                   for start, data in self.engine.frozen.values()):
                raise LuaHostError('Lua write overlaps a frozen value')
            if any(scope is not self and scope.overlaps(address, len(raw))
                   for scope in self.engine.lua_activations.values()):
                raise LuaHostError('Lua write overlaps another activation')
            if key not in self.data:
                if len(self.data) >= 1024 or sum(k[1] for k in self.data) + len(raw) > 1024 * 1024:
                    raise LuaHostError('Lua activation memory-undo budget exceeded')
                original = self.engine.memory.read(address, len(raw))
                self.data[key] = {'address': address, 'original': original.hex(), 'current': original.hex()}
            item = self.data[key]
            before = bytes.fromhex(item['current'])
            self.pending = {'address': address, 'before': before.hex(), 'after': raw.hex()}
            self.state = 'data-write-intent'
            try:
                self._save()
                broker_checkpoint()
                self.engine._write_transaction([_Patch(address, before, raw)],
                                               before_write=broker_checkpoint)
                item['current'] = raw.hex()
                self.pending, self.state = None, 'open'
                self._save()
            except Exception as exc:
                # A confirmed rollback may leave the previous scope usable.
                if not self.engine.blocked and self.engine.memory.read(address, len(before)) == before:
                    self.pending, self.state = None, 'open'
                    try:
                        self._save()
                    except Exception as journal_error:
                        self._fail(journal_error)
                else:
                    self._fail(exc)
                raise LuaHostError(str(exc)) from exc
            return True
        if operation == 'registerSymbol':
            if len(arguments) not in {2, 3} or len(arguments) == 3 and type(arguments[2]) is not bool:
                raise LuaHostError('Invalid symbol registration arguments')
            name, address = arguments[:2]
            validate_symbol(name)
            if type(address) is not int:
                raise LuaHostError('Symbol address must be an integer')
            self.engine.memory._range(address, 1)
            key = name.casefold()
            if key in self.engine.symbols or len(self.symbols) >= 4096:
                raise LuaHostError('Symbol is already owned or the activation limit is reached')
            self.symbols[key] = address
            try:
                self._save()
            except Exception as exc:
                del self.symbols[key]
                self._fail(exc)
                raise LuaHostError(str(exc)) from exc
            self.engine.symbols[key] = address
            return True
        if operation == 'unregisterSymbol':
            if len(arguments) != 1 or not isinstance(arguments[0], str):
                raise LuaHostError('Invalid symbol removal arguments')
            key = arguments[0].casefold()
            if key not in self.symbols:
                raise LuaHostError('Symbol does not belong to this Lua activation')
            if any(key in {name.casefold() for name in item['exports']} for item in self.assemblies.values()):
                raise LuaHostError('Active assembler exports require their owned disable receipt')
            if self.engine._symbol_consumers({key}):
                raise LuaHostError('Disable symbol consumers before unregistering their provider')
            address = self.symbols[key]
            del self.symbols[key]
            try:
                self._save()
            except Exception as exc:
                self.symbols[key] = address
                self._fail(exc)
                raise LuaHostError(str(exc)) from exc
            del self.engine.symbols[key]
            return True
        raise LuaHostError('Unsupported owned mutation: ' + str(operation))

    @restoration_entry
    def assemble(self, source, disable_info=None, *, syntaxcheck=False):
        with self.host.controller_work() as budget:
            with budget.dispatch():
                return self._assemble_body(source, disable_info, syntaxcheck=syntaxcheck)

    def _assemble_body(self, source, disable_info=None, *, syntaxcheck=False):
        self.check()
        from .aa_program import prepare_program, dry_link_program
        if not isinstance(source, str) or len(source.encode()) > 1024 * 1024:
            raise LuaHostError('Invalid bounded assembler source')
        digest = hashlib.sha256(source.encode()).hexdigest()
        if syntaxcheck:
            if disable_info is not None:
                raise LuaHostError('Syntax checking cannot retire an assembler receipt')
            program = prepare_program(source, self.engine.plan['process_name'], bitness=self.engine.memory.pointer_size * 8)
            ordinary, executable = self.engine._owned_provider_data()
            caps = set(program.get("capabilities", ()))
            disassembler = self.engine._disassembler_for(self.engine.memory) if "disassemble" in caps else None
            thread_model = self.engine._thread_model_for(self.engine.memory) if {"createthread", "threadwait"} & caps else None
            protection_model = self.engine._protection_model_for(self.engine.memory) if {"protect", "unprotect"} & caps else None
            export_model = self.engine._export_model_for(self.engine.memory) if {"getmodulehandle", "getprocaddress"} & caps else None
            dry_link_program(program, self.engine.memory, self.engine.symbols,
                             owned_data_ranges=ordinary,
                             owned_executable_data_ranges=executable,
                             disassembler=disassembler,
                             thread_model=thread_model,
                             protection_model=protection_model,
                             export_model=export_model)
            return {'ok': True, 'disableInfo': None}
        if disable_info is not None:
            if not isinstance(disable_info, dict) or set(disable_info) != {'token'}:
                raise LuaHostError('Invalid assembler disable receipt')
            token = disable_info['token']
            item = self.assemblies.get(token) if isinstance(token, str) else None
            if item is None or item['hash'] != digest:
                raise LuaHostError('Assembler receipt is foreign, stale or source-mismatched')
            self._retire(token)
            return {'ok': True, 'disableInfo': None}
        if len(self.assemblies) >= 128:
            raise LuaHostError('Lua activation assembler-receipt limit exceeded')
        program = prepare_program(source, self.engine.plan['process_name'], bitness=self.engine.memory.pointer_size * 8)
        if len(self.symbols) + len(program['provides']) > 4096:
            raise LuaHostError('Lua activation symbol limit exceeded')
        publication_guard = None
        if self.nth_aob_results and self.record_assembly_token is None:
            # This controller callback runs inside HookManager's held proof,
            # after assembly/staging, before any live entry is written. Once
            # the main AA owns its patched sites, normal receipt checks govern
            # later child assembly rather than rescanning the original bytes.
            results = tuple(self.nth_aob_results)
            def publication_guard():
                from .nth_aob import recheck_result
                self._guard()
                for result in results:
                    recheck_result(result, self.engine.memory)
        manager, linked, _ = self.engine._install_program(program, 'lua:' + str(self.identifier),
                                                          publication_guard=publication_guard)
        token = uuid.uuid4().hex
        self.assemblies[token] = {'hash': digest, 'manager': manager, 'exports': linked['exports'],
                                  'requires': program['requires'], 'program': program, 'linked': linked}
        for name, address in linked['exports'].items():
            self.symbols[name.casefold()] = address
            self.engine.symbols[name.casefold()] = address
        try:
            self._save()
        except Exception as exc:
            self._fail(exc)
            raise LuaHostError(str(exc)) from exc
        return {'ok': True, 'disableInfo': {'token': token}}

    @staticmethod
    def _aa_sections(source):
        from .aa_program import _clean_source
        clean = _clean_source(source)
        markers = list(re.finditer(r'^\s*\[(ENABLE|DISABLE)\]\s*$', clean, re.I | re.M))
        if len(markers) != 2 or [item.group(1).lower() for item in markers] != ['enable', 'disable']:
            raise LuaHostError('Expanded Lua AA requires one ordered ENABLE/DISABLE pair')
        return clean[:markers[0].start()], clean[markers[0].end():markers[1].start()], clean[markers[1].end():]

    def _nth_helper_provenance(self, program):
        contract = program.get('nth_aob_helper')
        if contract is not None:
            from .nth_aob import prepare_helper_contract
            bootstrap = self.engine.plan.get('lua_bootstrap')
            if bootstrap is None or prepare_helper_contract(bootstrap) != contract:
                raise LuaHostError('Nth-AOB table helper provenance differs from this trainer bootstrap')

    def _resolve_nth(self, definition, syntaxcheck):
        if syntaxcheck:
            raise LuaHostError('A live activation cannot publish syntax-check scan symbols')
        from .nth_aob import scan_nth
        self.check()
        key = definition['symbol'].casefold()
        if key in self.engine.symbols or len(self.symbols) >= 4096:
            raise LuaHostError('Nth-AOB symbol is already owned or the activation limit is reached')
        result = scan_nth(definition, self.engine.memory, expected_identity=self.identity)
        self.check()
        if key in self.engine.symbols:
            raise LuaHostError('Nth-AOB symbol ownership changed during scan')
        self.nth_aob_results.append(result)
        self.symbols[key] = result['address']
        try:
            # Durable source/target/selection evidence precedes publication of
            # this owned namespace entry. Scanning itself never writes memory.
            self._save()
        except Exception as exc:
            self._fail(exc)
            raise LuaHostError(str(exc)) from exc
        self.engine.symbols[key] = result['address']

    def check_program(self, program):
        with self.host.controller_work() as budget:
            return self._check_program_body(program)

    def _check_program_body(self, program):
        """Run disposable Lua and actual NASM linking with a private scan map.

        Diagnostic allocation addresses are synthetic. No scope symbol,
        journal, target byte, protection or allocation is changed.
        """
        from .lua_program import validate_lua_program, phase_expansion
        from .nth_aob import scan_nth, recheck_result
        from .aa_program import prepare_program, dry_link_program
        validate_lua_program(program)
        self.check()
        self._nth_helper_provenance(program)
        if program['bitness'] != self.engine.memory.pointer_size * 8:
            raise LuaHostError('Lua AA profile bitness differs from the attached target')
        overlay, results = dict(self.engine.symbols), []
        def resolve(definition, _checking):
            key = definition['symbol'].casefold()
            if key in overlay:
                raise LuaHostError('Nth-AOB syntax-check symbol collides with an owned symbol')
            result = scan_nth(definition, self.engine.memory, expected_identity=self.identity)
            results.append(result)
            overlay[key] = result['address']
        def expand(checker):
            original_broker = checker.broker
            from .address_expression import resolve_expression
            class ReadOverlayBroker:
                # The original disposable broker still authorizes every call.
                # Only address arguments use this private source-derived map.
                @property
                def generation(self):
                    return original_broker.generation
                def call(_self, name, arguments, *, generation, syntaxcheck):
                    if name in {'getAddress', 'readInteger', 'readSmallInteger', 'readQword',
                                'readFloat', 'readDouble', 'readPointer', 'readString', 'readBytes'} and arguments:
                        values = list(arguments)
                        if type(values[0]) is str:
                            values[0] = resolve_expression(values[0], self.engine.memory, overlay,
                                process_name=self.engine.plan['process_name'], pointer_size=self.engine.memory.pointer_size)
                        arguments = tuple(values)
                    return original_broker.call(name, arguments, generation=generation, syntaxcheck=syntaxcheck)
            checker.broker = ReadOverlayBroker()
            bootstrap = self.engine.plan.get('lua_bootstrap')
            if bootstrap is not None and not checker.helper_sources:
                # WP-41: a refused or failed table bootstrap blocks dependent
                # record scripts with the named reason; non-dependent records
                # skip the replay instead of failing on the unrun table source.
                decision, reason = table_lua_bootstrap_gate(
                    bootstrap['source'], program['source'],
                    self.engine.plan.get('table_lua'))
                if decision == 'block':
                    raise LuaHostError(reason)
                if decision == 'replay':
                    checker.install_helpers(bootstrap['source'])
            return phase_expansion(checker, program, 'enable', nth_resolver=resolve)
        expanded = self.host._disposable_check(expand)
        self.check()
        for result in results:
            recheck_result(result, self.engine.memory)
        preamble, enable, disable = self._aa_sections(expanded)
        if preamble.strip() or enable.strip() or disable.strip():
            aa = prepare_program(expanded, self.engine.plan['process_name'], bitness=program['bitness'])
            ordinary, executable = self.engine._owned_provider_data()
            caps = set(aa.get("capabilities", ()))
            disassembler = self.engine._disassembler_for(self.engine.memory) if "disassemble" in caps else None
            thread_model = self.engine._thread_model_for(self.engine.memory) if {"createthread", "threadwait"} & caps else None
            protection_model = self.engine._protection_model_for(self.engine.memory) if {"protect", "unprotect"} & caps else None
            export_model = self.engine._export_model_for(self.engine.memory) if {"getmodulehandle", "getprocaddress"} & caps else None
            diagnostic = dry_link_program(aa, self.engine.memory, overlay,
                owned_data_ranges=ordinary, owned_executable_data_ranges=executable,
                disassembler=disassembler, thread_model=thread_model,
                protection_model=protection_model, export_model=export_model)
        else:
            diagnostic = {'dry_run': True, 'publishable': False, 'enable': None, 'disable': None}
        self.check()
        return {'schema': 'ct2trainer-lua-program-dry-link/v1', 'dry_run': True,
                'publishable': False, 'nth_aob_results': results, 'assembler': diagnostic}

    @restoration_entry
    def start_program(self, program):
        with self.host.controller_work() as budget:
            return self._start_program_body(program)

    def _start_program_body(self, program):
        """Run selected Lua, then publish its AA under the same undo scope.

        Callbacks are only pulsed by the controller after this method confirms.
        A failure remains owned and can be compensated by close().
        """
        from .lua_program import validate_lua_program, phase_expansion
        validate_lua_program(program)
        if program['bitness'] != self.engine.memory.pointer_size * 8:
            raise LuaHostError('Lua AA profile bitness differs from the attached target')
        self.record_program = program
        self._nth_helper_provenance(program)
        if program.get('dynamic_definitions'):
            self.check_program(program)
        bootstrap = self.engine.plan.get('lua_bootstrap')
        if bootstrap is not None:
            # WP-41: replay the table source only when the bootstrap executed
            # cleanly (or the plan predates the bootstrap metadata); a refused
            # or failed bootstrap blocks dependent record scripts with the
            # named reason and skips the replay for non-dependent ones.
            decision, reason = table_lua_bootstrap_gate(
                bootstrap['source'], program['source'],
                self.engine.plan.get('table_lua'))
            if decision == 'block':
                raise LuaHostError(reason)
            if decision == 'replay':
                self.host.install_helpers(bootstrap['source'])
        expanded = phase_expansion(self.host, program, 'enable', nth_resolver=self._resolve_nth)
        from .nth_aob import recheck_result
        for result in self.nth_aob_results:
            recheck_result(result, self.engine.memory)
        preamble, enable, disable = self._aa_sections(expanded)
        if preamble.strip() or enable.strip() or disable.strip():
            outcome = self.assemble(expanded)
            self.record_assembly_token = outcome['disableInfo']['token']
        if any(name.casefold() not in self.symbols for name in program['provides']):
            raise LuaHostError('Lua activation did not confirm its declared symbol exports')
        self.check()

    @restoration_entry
    def stop_program(self):
        with self.host.controller_work() as budget:
            return self._stop_program_body()

    def _stop_program_body(self):
        """Execute DISABLE Lua and prove its AA still describes exact undo.

        The owned HookManager performs restoration from captured bytes. A new
        Lua return cannot replace that receipt with arbitrary disable writes.
        """
        if self.record_program is None:
            return
        from .lua_program import phase_expansion
        from .aa_program import prepare_program, link_program
        from .nth_aob import recheck_result
        for result in self.nth_aob_results:
            recheck_result(result, self.engine.memory, before_publication=False)
        expanded = phase_expansion(self.host, self.record_program, 'disable')
        preamble, enable, disable = self._aa_sections(expanded)
        if self.record_assembly_token is None:
            if preamble.strip() or enable.strip() or disable.strip():
                raise LuaHostError('Disable cannot introduce AA for a Lua-only activation')
            self.check()
            return
        item = self.assemblies.get(self.record_assembly_token)
        if item is None:
            raise LuaHostError('The activation main assembler receipt is missing')
        original = item['program']
        captured_preamble, captured_enable, _ = self._aa_sections(original['source'])
        replacement = prepare_program(preamble + '\n[ENABLE]\n' + captured_enable +
                                      '\n[DISABLE]\n' + disable,
                                      self.engine.plan['process_name'], bitness=original['bitness'])
        if replacement['preamble'] != original['preamble'] or replacement['enable'] != original['enable']:
            raise LuaHostError('Disable Lua changed the captured AA preamble or enable program')
        ordinary, executable = self.engine._owned_provider_data()
        symbols = dict(self.engine.symbols)
        symbols.update(item['linked']['symbols'])
        inverse = link_program(replacement, self.engine.memory, symbols,
                               item['manager'].allocation_map(), phase='disable',
                               owned_data_ranges=ordinary, owned_executable_data_ranges=executable)
        restored = sorted((row['address'], row['bytes'].lower()) for row in inverse['blocks']
                          if not row['is_allocation'])
        expected = sorted((row['address'], row['original'].lower()) for row in item['manager'].entries)
        if restored != expected:
            raise LuaHostError('Disable Lua AA must restore exactly the captured original entry bytes')
        self.check()

    def _retire(self, token):
        item = self.assemblies[token]
        for name, address in item['exports'].items():
            if self.engine.symbols.get(name.casefold()) != address:
                raise PatchConflict('Assembler export ownership changed before disable')
        provided = {name.casefold() for name in item['exports']}
        if (self.engine._symbol_consumers(provided, exclude_token=(self.identifier, token))
                or self.engine._provider_consumers(item['manager'], exclude_token=(self.identifier, token))):
            raise LuaHostError('Disable dependent records/Lua receipts before their assembler provider')
        try:
            item['manager'].disable()
            self.engine.retired_hooks.append(item['manager'])
            for name, address in item['exports'].items():
                key = name.casefold()
                if key in self.symbols:
                    if self.engine.symbols.get(key) != address:
                        raise PatchConflict('Assembler export ownership changed')
                    del self.symbols[key]
                    del self.engine.symbols[key]
            del self.assemblies[token]
            self._save()
        except Exception as exc:
            self._fail(exc)
            raise LuaHostError(str(exc)) from exc

    def _cleanup_guard(self):
        self.engine._guard()
        if self.engine.memory.identity != self.identity or self.state not in {'open', 'closing', 'abandoned'}:
            raise LuaHostError('Controller cleanup target or lifecycle changed')
        self._journal_guard()

    @restoration_entry
    def close(self):
        self.check()
        if self.engine._symbol_consumers(self.symbols, exclude_scope=self.identifier, exclude_entry=self.identifier):
            raise LuaHostError('Disable dependent Lua activations before their provider')
        self.broker.invalidate()
        self.host.cancel()
        try:
            with controller_cleanup(self._cleanup_guard, self.host._clock):
                for token in reversed(list(self.assemblies)):
                    broker_checkpoint()
                    self._retire(token)
                self.state = 'closing'
                self._save()
                patches = [_Patch(item['address'], bytes.fromhex(item['current']), bytes.fromhex(item['original']))
                           for item in reversed(list(self.data.values()))]
                broker_checkpoint()
                self.engine._write_transaction(patches, before_write=broker_checkpoint)
                for item in self.data.values():
                    item['current'] = item['original']
                for name in self.symbols:
                    del self.engine.symbols[name]
                self.symbols.clear()
                self.state = 'abandoned'  # Exact data undo complete; hook receipts remain separate.
                self._save()
        except Exception as exc:
            self._fail(exc)
            raise LuaHostError(str(exc)) from exc

    def finish_after_exit(self):
        self.broker.invalidate()
        self.host.cancel()
        if self.engine.memory.identity != self.identity or self.engine.memory.is_alive():
            raise StateError('Lua receipt can only finalize after the exact target exits')
        for manager in self.managers():
            manager.finish_after_exit()
        self.assemblies.clear()
        self.symbols.clear()
        self.pending = None
        self.state = 'target-exited'
        self._save()
