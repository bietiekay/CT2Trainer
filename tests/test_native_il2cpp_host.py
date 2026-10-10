"""Synthetic-fixture tests for the IL2CPP registration host (AP-05 stage 2).

Fixtures are own inert PE/metadata bytes built on the shared
``native_il2cpp_static_fixtures`` generators (no Unity/game inputs, no
TableReferences): the host-specific builder lays out the three
registration tables and method bodies inside the single raw-backed
executable ``.own`` section, exactly mirroring the stage-1 live test
layout.  Covered: alias roundtrips, stale/base-changed/SHA-mismatch
refusals with the permanent stale latch, cross-table and cross-module
confusion refusals, 32/64-bit, relocated live bases, version limits and
deterministic re-runs.
"""
import struct
import unittest

from tests.native_il2cpp_static_fixtures import metadata_fixture, pe_fixture

from ct2trainer.native.il2cpp_host import (
    ALIAS_KINDS,
    AliasNotRegistered,
    AliasRegistrationRefused,
    AliasResolution,
    AliasSpec,
    Il2CppHostError,
    Il2CppRegistrationHost,
    ModuleRegistrationRefused,
    SCHEMA,
)
from ct2trainer.native.il2cpp_live import (
    BaseChangedRefused,
    BitnessMismatchRefused,
    MethodIdentityRefused,
    ModuleBinding,
    ModuleShaMismatchRefused,
    OutOfExtentRefused,
    POINTER_MODE_RVA,
    POINTER_MODE_VA,
    PointerTable,
    SignatureMismatchRefused,
    StaleBindingRefused,
    TableConfusionRefused,
)
from ct2trainer.native.il2cpp_static import FormatError, MetadataV29, WindowsPE

IDENTITY = ('Owned.dll', 'CT2TrainerOwned', 'Counter')


def default_base(bitness):
    return 0x180000000 if bitness == 64 else 0x400000


def table_rvas(bitness):
    if bitness == 64:
        return 0x1000, 0x1020, 0x1030
    return 0x1000, 0x1010, 0x1020


def code_targets(bitness):
    if bitness == 64:
        return (0x1040, 0x1048), 0x1050, 0x1060
    return (0x1030, 0x1034), 0x1040, 0x1050


def build_host_pe(bitness=64, *, live_base=None, pointer_mode=POINTER_MODE_VA,
                  method_table_rva=None, invoker_table_rva=None,
                  generic_table_rva=None, method_count=2, invoker_count=1,
                  generic_count=1, executable=True, write_slots=True,
                  raw_overrides=None):
    """Host PE fixture: executable .own with registration tables + bodies."""
    data = bytearray(pe_fixture(bitness))
    defaults = table_rvas(bitness)
    method_table_rva = defaults[0] if method_table_rva is None else method_table_rva
    invoker_table_rva = defaults[1] if invoker_table_rva is None else invoker_table_rva
    generic_table_rva = (defaults[2] if generic_table_rva is None
                         else generic_table_rva)
    base = default_base(bitness) if live_base is None else live_base
    fmt = '<Q' if bitness == 64 else '<I'
    pointer = 8 if bitness == 64 else 4
    method_targets, invoker_target, generic_target = code_targets(bitness)
    if executable:
        section_at = 0x98 + (240 if bitness == 64 else 224)
        struct.pack_into('<I', data, section_at + 36, 0x60000040)

    def put(table_rva, index, target, raw=None):
        value = (raw if raw is not None
                 else (base + target if pointer_mode == POINTER_MODE_VA
                       else target))
        struct.pack_into(fmt, data, 0x200 + (table_rva - 0x1000)
                         + index * pointer, value)

    if write_slots:
        for index in range(method_count):
            put(method_table_rva, index,
                method_targets[index % len(method_targets)])
        for index in range(invoker_count):
            put(invoker_table_rva, index, invoker_target)
        for index in range(generic_count):
            put(generic_table_rva, index, generic_target)
    if raw_overrides:
        table_by_name = {'method_pointers': method_table_rva,
                         'invokers': invoker_table_rva,
                         'generic_invokers': generic_table_rva}
        for (table, index), raw in raw_overrides.items():
            put(table_by_name[table], index, 0, raw=raw)
    return bytes(data)


def make_host(bitness=64, *, module_name='GameAssembly.dll', live_base=None,
              module_sha=None, generation=1, pointer_mode=POINTER_MODE_VA,
              pe_bytes=None, metadata_bytes=None, method_count=2,
              invoker_count=1, generic_count=1, executable=True,
              method_table_rva=None, invoker_table_rva=None,
              generic_table_rva=None, write_slots=True, raw_overrides=None):
    if pe_bytes is None:
        pe_bytes = build_host_pe(
            bitness, live_base=live_base, pointer_mode=pointer_mode,
            method_table_rva=method_table_rva, invoker_table_rva=invoker_table_rva,
            generic_table_rva=generic_table_rva, method_count=method_count,
            invoker_count=invoker_count, generic_count=generic_count,
            executable=executable, write_slots=write_slots,
            raw_overrides=raw_overrides)
    if metadata_bytes is None:
        metadata_bytes = metadata_fixture()
    base = default_base(bitness) if live_base is None else live_base
    pe = WindowsPE(pe_bytes)
    metadata = MetadataV29(metadata_bytes)
    binding = ModuleBinding(base, module_sha if module_sha is not None
                            else pe.sha256, generation, bitness)
    defaults = table_rvas(bitness)
    tables = {
        'method_pointers': PointerTable(
            'method_pointers',
            defaults[0] if method_table_rva is None else method_table_rva,
            method_count, pointer_mode),
        'invokers': PointerTable(
            'invokers',
            defaults[1] if invoker_table_rva is None else invoker_table_rva,
            invoker_count, pointer_mode),
        'generic_invokers': PointerTable(
            'generic_invokers',
            defaults[2] if generic_table_rva is None else generic_table_rva,
            generic_count, pointer_mode),
    }
    host = Il2CppRegistrationHost(
        module_name, pe_bytes, metadata_bytes, binding,
        method_pointers=tables['method_pointers'],
        invokers=tables['invokers'],
        generic_invokers=tables['generic_invokers'])
    return host, tables


def register_standard_aliases(host):
    host.register_alias(AliasSpec(
        alias='status', kind='method', image=IDENTITY[0], namespace=IDENTITY[1],
        class_name=IDENTITY[2], name='GetCurrentStatus'))
    host.register_alias(AliasSpec(
        alias='setflag', kind='method', image=IDENTITY[0], namespace=IDENTITY[1],
        class_name=IDENTITY[2], name='SetFlag', parameter_type_indices=(102,)))
    host.register_alias(AliasSpec(alias='inv0', kind='invoker', slot_index=0))
    host.register_alias(
        AliasSpec(alias='gen0', kind='generic_invoker', slot_index=0))
    return host


class HostConstructionTests(unittest.TestCase):
    def test_construction_snapshot_identity(self):
        host, _tables = make_host()
        snapshot = host.snapshot()
        self.assertEqual(snapshot['schema'], SCHEMA)
        self.assertEqual(snapshot['schema'], 'ct2trainer-il2cpp-host/v1')
        self.assertEqual(snapshot['module']['name'], 'GameAssembly.dll')
        self.assertEqual(snapshot['module']['bitness'], 64)
        self.assertEqual(snapshot['module']['live_base'], default_base(64))
        self.assertEqual(snapshot['metadata']['version'], 29)
        self.assertEqual(snapshot['metadata']['sha256'], host.metadata.sha256)
        self.assertEqual(snapshot['pe']['sha256'], host.pe.sha256)
        self.assertEqual(snapshot['module']['module_sha256'],
                         host.binding.module_sha256)
        self.assertEqual(snapshot['pe']['sha256'],
                         host.binding.module_sha256)
        self.assertEqual(snapshot['counts'],
                         {'modules': 1, 'aliases': 0, 'proofs': 0})
        self.assertFalse(snapshot['observations']['stale'])
        self.assertEqual(snapshot['observations']['count'], 0)

    def test_foreign_metadata_version_refused(self):
        metadata = bytearray(metadata_fixture())
        struct.pack_into('<i', metadata, 4, 30)
        with self.assertRaises(FormatError):
            make_host(metadata_bytes=bytes(metadata))

    def test_foreign_metadata_magic_refused(self):
        metadata = bytearray(metadata_fixture())
        struct.pack_into('<I', metadata, 0, 0x12345678)
        with self.assertRaises(FormatError):
            make_host(metadata_bytes=bytes(metadata))

    def test_foreign_pe_machine_refused(self):
        pe_bytes = bytearray(build_host_pe())
        struct.pack_into('<H', pe_bytes, 0x84, 0x01C0)
        with self.assertRaises(FormatError):
            make_host(pe_bytes=bytes(pe_bytes))

    def test_bitness_mismatch_refused(self):
        pe_bytes = build_host_pe(32)
        with self.assertRaises(BitnessMismatchRefused):
            Il2CppRegistrationHost(
                'GameAssembly.dll', pe_bytes, metadata_fixture(),
                ModuleBinding(default_base(32), WindowsPE(pe_bytes).sha256, 1, 64),
                method_pointers=PointerTable(
                    'method_pointers', 0x1000, 2, POINTER_MODE_VA),
                invokers=PointerTable('invokers', 0x1010, 1, POINTER_MODE_VA),
                generic_invokers=PointerTable(
                    'generic_invokers', 0x1020, 1, POINTER_MODE_VA))

    def test_module_sha_mismatch_refused(self):
        with self.assertRaises(ModuleShaMismatchRefused):
            make_host(module_sha='f' * 64)

    def test_invalid_module_name_refused(self):
        with self.assertRaises(ModuleRegistrationRefused):
            make_host(module_name='')

    def test_live_base_overflow_refused(self):
        for bitness in (32, 64):
            with self.subTest(bitness=bitness):
                pe_bytes = build_host_pe(bitness)
                overflow = (1 << bitness) - 0x1000
                with self.assertRaises(OutOfExtentRefused):
                    Il2CppRegistrationHost(
                        'GameAssembly.dll', pe_bytes, metadata_fixture(),
                        ModuleBinding(overflow, WindowsPE(pe_bytes).sha256,
                                      1, bitness),
                        method_pointers=PointerTable(
                            'method_pointers', 0x1000, 2, POINTER_MODE_VA),
                        invokers=PointerTable('invokers', 0x1010, 1,
                                              POINTER_MODE_VA),
                        generic_invokers=PointerTable(
                            'generic_invokers', 0x1020, 1,
                            POINTER_MODE_VA))

    def test_invalid_alias_kind_refused(self):
        with self.assertRaises(AliasRegistrationRefused):
            AliasSpec(alias='bad', kind='script')


class AliasRegistrationTests(unittest.TestCase):
    def test_register_method_alias_appears_in_snapshot(self):
        host, _tables = make_host()
        register_standard_aliases(host)
        snapshot = host.snapshot()
        self.assertEqual(host.alias_names,
                         ('status', 'setflag', 'inv0', 'gen0'))
        self.assertEqual(snapshot['aliases']['status']['kind'], 'method')
        self.assertEqual(snapshot['aliases']['status']['table'],
                         'method_pointers')
        self.assertIsNone(snapshot['aliases']['status']['slot_index'])
        self.assertEqual(snapshot['aliases']['status']['name'],
                         'GetCurrentStatus')
        self.assertEqual(snapshot['aliases']['inv0']['slot_index'], 0)
        self.assertEqual(snapshot['aliases']['inv0']['table'], 'invokers')
        self.assertEqual(snapshot['counts']['aliases'], 4)

    def test_duplicate_alias_refused(self):
        host, _tables = make_host()
        host.register_alias(AliasSpec(
            alias='status', kind='method', image=IDENTITY[0],
            namespace=IDENTITY[1], class_name=IDENTITY[2],
            name='GetCurrentStatus'))
        with self.assertRaises(AliasRegistrationRefused):
            host.register_alias(AliasSpec(
                alias='status', kind='method', image=IDENTITY[0],
                namespace=IDENTITY[1], class_name=IDENTITY[2],
                name='SetFlag', parameter_type_indices=(102,)))

    def test_empty_alias_name_refused(self):
        with self.assertRaises(AliasRegistrationRefused):
            AliasSpec(alias='', kind='method', image='A', namespace='B',
                      class_name='C', name='D')

    def test_alias_control_character_refused(self):
        with self.assertRaises(AliasRegistrationRefused):
            AliasSpec(alias='bad\x00name', kind='method', image='A',
                      namespace='B', class_name='C', name='D')

    def test_alias_name_too_long_refused(self):
        with self.assertRaises(AliasRegistrationRefused):
            AliasSpec(alias='a' * 129, kind='method', image='A',
                      namespace='B', class_name='C', name='D')

    def test_method_alias_missing_identity_refused(self):
        with self.assertRaises(AliasRegistrationRefused):
            AliasSpec(alias='x', kind='method', namespace='B', class_name='C',
                      name='D')

    def test_method_alias_with_slot_refused(self):
        with self.assertRaises(AliasRegistrationRefused):
            AliasSpec(alias='x', kind='method', image='A', namespace='B',
                      class_name='C', name='D', slot_index=0)

    def test_invoker_alias_slot_out_of_range_refused(self):
        host, _tables = make_host()
        with self.assertRaises(AliasRegistrationRefused):
            host.register_alias(AliasSpec(alias='bad', kind='invoker',
                                          slot_index=5))

    def test_invoker_alias_with_method_identity_refused(self):
        with self.assertRaises(AliasRegistrationRefused):
            AliasSpec(alias='x', kind='invoker', slot_index=0, image='A')
        with self.assertRaises(AliasRegistrationRefused):
            AliasSpec(alias='x', kind='generic_invoker', slot_index=0,
                      expected_static=True)

    def test_invalid_spec_fields_refused(self):
        with self.assertRaises(AliasRegistrationRefused):
            AliasSpec(alias='x', kind='method', image='A', namespace='B',
                      class_name='C', name='D',
                      parameter_type_indices='102')
        with self.assertRaises(AliasRegistrationRefused):
            AliasSpec(alias='x', kind='invoker', slot_index=-2)
        with self.assertRaises(AliasRegistrationRefused):
            AliasSpec(alias='x', kind='invoker', slot_index=1.5)


class AliasResolutionTests(unittest.TestCase):
    def test_method_alias_roundtrip_status(self):
        host, _tables = make_host()
        register_standard_aliases(host)
        base = default_base(64)
        proof = host.resolve_alias('status')
        self.assertEqual(proof.va, base + 0x1040)
        self.assertEqual(proof.kind, 'method')
        self.assertEqual(proof.table, 'method_pointers')
        self.assertEqual(proof.slot_index, 0)
        self.assertEqual(proof.section, '.own')
        self.assertEqual(proof.live_base, base)
        self.assertEqual(proof.module_sha256, host.binding.module_sha256)
        self.assertEqual(proof.metadata_sha256, host.metadata.sha256)
        self.assertEqual(proof.generation, 1)
        self.assertEqual(proof.pointer_mode, POINTER_MODE_VA)
        self.assertEqual(proof.method_token, 0x06000001)
        self.assertEqual(proof.image, 'Owned.dll')
        self.assertEqual(proof.namespace, 'CT2TrainerOwned')
        self.assertEqual(proof.class_name, 'Counter')
        self.assertEqual(proof.method_name, 'GetCurrentStatus')
        self.assertTrue(proof.is_static)
        self.assertEqual(proof.parameter_count, 0)
        payload = proof.to_dict()
        self.assertEqual(payload['name'], 'GetCurrentStatus')
        self.assertEqual(payload['image'], 'Owned.dll')

    def test_method_alias_roundtrip_setflag(self):
        host, _tables = make_host()
        register_standard_aliases(host)
        base = default_base(64)
        proof = host.resolve_alias('setflag')
        self.assertEqual(proof.va, base + 0x1048)
        self.assertEqual(proof.slot_index, 1)
        self.assertEqual(proof.method_token, 0x06000002)
        self.assertTrue(proof.is_static)
        self.assertEqual(proof.parameter_count, 1)

    def test_invoker_alias_roundtrip(self):
        host, _tables = make_host()
        register_standard_aliases(host)
        proof = host.resolve_alias('inv0')
        self.assertEqual(proof.va, default_base(64) + 0x1050)
        self.assertEqual(proof.table, 'invokers')
        self.assertEqual(proof.slot_index, 0)
        self.assertIsNone(proof.method_token)
        self.assertNotIn('image', proof.to_dict())

    def test_generic_invoker_alias_roundtrip(self):
        host, _tables = make_host()
        register_standard_aliases(host)
        proof = host.resolve_alias('gen0')
        self.assertEqual(proof.va, default_base(64) + 0x1060)
        self.assertEqual(proof.table, 'generic_invokers')
        self.assertEqual(proof.kind, 'generic_invoker')

    def test_unknown_alias_refused(self):
        host, _tables = make_host()
        register_standard_aliases(host)
        with self.assertRaises(AliasNotRegistered):
            host.resolve_alias('missing')

    def test_ambiguous_identity_refused(self):
        host, _tables = make_host(metadata_bytes=metadata_fixture(overload=True),
                                  method_count=3)
        register_standard_aliases(host)
        with self.assertRaises(MethodIdentityRefused):
            host.resolve_alias('status')

    def test_signature_model_mismatch_refused(self):
        host, _tables = make_host()
        host.register_alias(AliasSpec(
            alias='wrongstatic', kind='method', image=IDENTITY[0],
            namespace=IDENTITY[1], class_name=IDENTITY[2], name='SetFlag',
            parameter_type_indices=(102,), expected_static=False))
        with self.assertRaises(SignatureMismatchRefused):
            host.resolve_alias('wrongstatic')
        host.register_alias(AliasSpec(
            alias='wrongcount', kind='method', image=IDENTITY[0],
            namespace=IDENTITY[1], class_name=IDENTITY[2], name='SetFlag',
            parameter_type_indices=(102,), expected_parameter_count=3))
        with self.assertRaises(SignatureMismatchRefused):
            host.resolve_alias('wrongcount')

    def test_method_index_beyond_table_count_refused(self):
        host, _tables = make_host(method_count=1)
        register_standard_aliases(host)
        with self.assertRaises(OutOfExtentRefused):
            host.resolve_alias('setflag')

    def test_cross_table_target_refused(self):
        # Method slot 0 points into the invoker table extent.
        pe_bytes = build_host_pe(
            raw_overrides={('method_pointers', 0): default_base(64) + 0x1020})
        host, _tables = make_host(pe_bytes=pe_bytes)
        register_standard_aliases(host)
        with self.assertRaises(TableConfusionRefused):
            host.resolve_alias('status')

    def test_target_outside_image_refused(self):
        pe_bytes = build_host_pe(
            raw_overrides={('method_pointers', 0): 0x70000000000})
        host, _tables = make_host(pe_bytes=pe_bytes)
        register_standard_aliases(host)
        with self.assertRaises(OutOfExtentRefused):
            host.resolve_alias('status')

    def test_rva_mode_roundtrip(self):
        host, _tables = make_host(pointer_mode=POINTER_MODE_RVA)
        register_standard_aliases(host)
        proof = host.resolve_alias('status')
        self.assertEqual(proof.va, default_base(64) + 0x1040)
        self.assertEqual(proof.pointer_mode, POINTER_MODE_RVA)

    def test_proof_carries_binding_identity(self):
        host, _tables = make_host(generation=7)
        register_standard_aliases(host)
        proof = host.resolve_alias('status')
        self.assertEqual(proof.generation, 7)
        self.assertEqual(proof.live_base, host.binding.live_base)
        self.assertEqual(proof.module_sha256, host.pe.sha256)
        self.assertEqual(proof.metadata_sha256, host.metadata.sha256)
        snapshot = host.snapshot()
        self.assertEqual(len(snapshot['proofs']), 1)
        self.assertEqual(snapshot['proofs'][0]['va'], proof.va)


class ObserveTests(unittest.TestCase):
    def test_matching_observation_accepted(self):
        host, _tables = make_host()
        module = host.snapshot()['module']
        host.observe(live_base=module['live_base'],
                     module_sha256=module['module_sha256'],
                     generation=module['generation'])
        host.observe(live_base=module['live_base'],
                     module_sha256=module['module_sha256'],
                     generation=module['generation'])
        self.assertFalse(host.is_stale)
        self.assertEqual(host.snapshot()['observations']['count'], 2)

    def test_base_change_refused(self):
        host, _tables = make_host()
        register_standard_aliases(host)
        module = host.snapshot()['module']
        with self.assertRaises(BaseChangedRefused):
            host.observe(live_base=module['live_base'] + 0x1000,
                         module_sha256=module['module_sha256'],
                         generation=module['generation'])

    def test_sha_change_refused(self):
        host, _tables = make_host()
        module = host.snapshot()['module']
        with self.assertRaises(ModuleShaMismatchRefused):
            host.observe(live_base=module['live_base'],
                         module_sha256='c' * 64,
                         generation=module['generation'])

    def test_generation_change_refused(self):
        host, _tables = make_host()
        module = host.snapshot()['module']
        with self.assertRaises(StaleBindingRefused):
            host.observe(live_base=module['live_base'],
                         module_sha256=module['module_sha256'],
                         generation=module['generation'] + 1)

    def test_stale_host_refuses_resolution(self):
        host, _tables = make_host()
        register_standard_aliases(host)
        module = host.snapshot()['module']
        with self.assertRaises(BaseChangedRefused):
            host.observe(live_base=module['live_base'] + 0x40,
                         module_sha256=module['module_sha256'],
                         generation=module['generation'])
        self.assertTrue(host.is_stale)
        with self.assertRaises(BaseChangedRefused):
            host.resolve_alias('status')
        self.assertTrue(host.snapshot()['observations']['stale'])

    def test_stale_latch_is_permanent(self):
        host, _tables = make_host()
        module = host.snapshot()['module']
        with self.assertRaises(BaseChangedRefused):
            host.observe(live_base=module['live_base'] + 0x40,
                         module_sha256=module['module_sha256'],
                         generation=module['generation'])
        # Even a matching observation cannot resurrect the stale host.
        with self.assertRaises(BaseChangedRefused):
            host.observe(live_base=module['live_base'],
                         module_sha256=module['module_sha256'],
                         generation=module['generation'])


class CrossModuleTests(unittest.TestCase):
    def _secondary_pe(self):
        return build_host_pe(64)

    def test_register_secondary_module(self):
        host, _tables = make_host()
        pe2 = self._secondary_pe()
        binding2 = ModuleBinding(0x190000000, WindowsPE(pe2).sha256, 2, 64)
        host.register_module('StubNative.dll', binding2, pe2)
        snapshot = host.snapshot()
        self.assertEqual(snapshot['counts']['modules'], 2)
        entry = snapshot['modules']['StubNative.dll']
        self.assertEqual(entry['live_base'], 0x190000000)
        self.assertEqual(entry['image_size'], 0x2000)
        self.assertEqual(entry['module_sha256'], WindowsPE(pe2).sha256)

    def test_duplicate_module_name_refused(self):
        host, _tables = make_host()
        pe2 = self._secondary_pe()
        with self.assertRaises(ModuleRegistrationRefused):
            host.register_module('GameAssembly.dll',
                                 ModuleBinding(0x190000000,
                                               WindowsPE(pe2).sha256, 2, 64),
                                 pe2)
        with self.assertRaises(ModuleRegistrationRefused):
            host.register_module('', ModuleBinding(0x190000000,
                                                   WindowsPE(pe2).sha256, 2, 64),
                                pe2)

    def test_secondary_module_bitness_mismatch_refused(self):
        host, _tables = make_host()
        pe32 = build_host_pe(32)
        with self.assertRaises(BitnessMismatchRefused):
            host.register_module('X86Stub.dll',
                                 ModuleBinding(default_base(32),
                                               WindowsPE(pe32).sha256, 2, 32),
                                 pe32)

    def test_secondary_module_sha_mismatch_refused(self):
        host, _tables = make_host()
        pe2 = self._secondary_pe()
        with self.assertRaises(ModuleShaMismatchRefused):
            host.register_module('StubNative.dll',
                                 ModuleBinding(0x190000000, 'f' * 64, 2, 64),
                                 pe2)

    def test_alias_target_inside_secondary_module_refused(self):
        host, _tables = make_host()
        register_standard_aliases(host)
        pe2 = self._secondary_pe()
        # Extent [0x180001000, 0x180003000) contains method-0 target
        # 0x180001040 (confused/stale pointer scenario).
        binding2 = ModuleBinding(0x180001000, WindowsPE(pe2).sha256, 2, 64)
        host.register_module('ConfusedStub.dll', binding2, pe2)
        with self.assertRaises(TableConfusionRefused):
            host.resolve_alias('status')

    def test_alias_targeting_other_module_refused(self):
        host, _tables = make_host()
        spec = AliasSpec(
            alias='foreign', kind='method', image=IDENTITY[0],
            namespace=IDENTITY[1], class_name=IDENTITY[2],
            name='GetCurrentStatus', module='OtherModule.dll')
        with self.assertRaises(TableConfusionRefused):
            host.register_alias(spec)
        # Unregistered module names are refused just as explicitly.
        spec2 = AliasSpec(
            alias='foreign2', kind='method', image=IDENTITY[0],
            namespace=IDENTITY[1], class_name=IDENTITY[2],
            name='GetCurrentStatus', module='Unknown.dll')
        with self.assertRaises(TableConfusionRefused):
            host.register_alias(spec2)


class BitnessAndRelocationTests(unittest.TestCase):
    def test_32bit_roundtrip(self):
        host, _tables = make_host(bitness=32)
        register_standard_aliases(host)
        base = default_base(32)
        status = host.resolve_alias('status')
        self.assertEqual(status.va, base + 0x1030)
        self.assertEqual(status.pointer_mode, POINTER_MODE_VA)
        setflag = host.resolve_alias('setflag')
        self.assertEqual(setflag.va, base + 0x1034)
        inv0 = host.resolve_alias('inv0')
        self.assertEqual(inv0.va, base + 0x1040)
        gen0 = host.resolve_alias('gen0')
        self.assertEqual(gen0.va, base + 0x1050)
        snapshot = host.snapshot()
        self.assertEqual(snapshot['module']['bitness'], 32)
        self.assertEqual(snapshot['pe']['image_size'], 0x2000)

    def test_32bit_table_extent_bytes(self):
        host, _tables = make_host(bitness=32)
        snapshot = host.snapshot()
        self.assertEqual(snapshot['tables']['method_pointers']['extent_bytes'], 8)
        self.assertEqual(snapshot['tables']['invokers']['extent_bytes'], 4)
        self.assertEqual(snapshot['tables']['generic_invokers']['extent_bytes'], 4)
        host64, _tables64 = make_host(bitness=64)
        snapshot64 = host64.snapshot()
        self.assertEqual(snapshot64['tables']['method_pointers']['extent_bytes'], 16)
        self.assertEqual(snapshot64['tables']['invokers']['extent_bytes'], 8)

    def test_relocated_base_shifts_alias_va(self):
        live_base = default_base(64) + 0x20000
        host, _tables = make_host(live_base=live_base)
        register_standard_aliases(host)
        proof = host.resolve_alias('status')
        self.assertEqual(proof.va, live_base + 0x1040)
        self.assertEqual(proof.live_base, live_base)
        snapshot = host.snapshot()
        self.assertEqual(snapshot['module']['live_base'], live_base)

    def test_relocated_base_rva_mode_shifts_alias_va(self):
        live_base = default_base(64) + 0x30000
        host, _tables = make_host(live_base=live_base, pointer_mode=POINTER_MODE_RVA)
        register_standard_aliases(host)
        proof = host.resolve_alias('setflag')
        self.assertEqual(proof.va, live_base + 0x1048)


class DeterminismTests(unittest.TestCase):
    def _build_host(self, pe_bytes, metadata_bytes):
        host, _tables = make_host(pe_bytes=pe_bytes, metadata_bytes=metadata_bytes)
        register_standard_aliases(host)
        module = host.snapshot()['module']
        host.observe(live_base=module['live_base'],
                     module_sha256=module['module_sha256'],
                     generation=module['generation'])
        host.resolve_alias('setflag')
        host.resolve_alias('status')
        host.resolve_alias('gen0')
        return host

    def test_identical_inputs_identical_snapshots(self):
        pe_bytes = build_host_pe()
        metadata_bytes = metadata_fixture()
        a = self._build_host(pe_bytes, metadata_bytes)
        b = self._build_host(pe_bytes, metadata_bytes)
        self.assertEqual(a.snapshot(), b.snapshot())

    def test_repeated_resolution_stable(self):
        host, _tables = make_host()
        register_standard_aliases(host)
        first = host.resolve_alias('status')
        second = host.resolve_alias('status')
        third = host.resolve_alias('status')
        self.assertEqual(first, second)
        self.assertEqual(first.va, third.va)
        self.assertEqual(first.to_dict(), third.to_dict())
        snapshot = host.snapshot()
        self.assertEqual(len(snapshot['proofs']), 3)
        self.assertEqual(snapshot['proofs'][0], snapshot['proofs'][2])
        self.assertEqual(host.snapshot(), snapshot)

    def test_snapshot_stable_across_calls(self):
        host, _tables = make_host()
        register_standard_aliases(host)
        host.resolve_alias('inv0')
        self.assertEqual(host.snapshot(), host.snapshot())

    def test_proof_order_follows_resolution_order(self):
        host, _tables = make_host()
        register_standard_aliases(host)
        host.resolve_alias('setflag')
        host.resolve_alias('status')
        host.resolve_alias('gen0')
        snapshot = host.snapshot()
        self.assertEqual(
            [proof['alias'] for proof in snapshot['proofs']],
            ['setflag', 'status', 'gen0'])


if __name__ == '__main__':
    unittest.main()
