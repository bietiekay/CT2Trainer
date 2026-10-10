"""Synthetic-PE tests for the IL2CPP live resolver (AP-05 stage 1).

Fixtures are own inert PE/metadata bytes from
``native_il2cpp_static_fixtures`` plus a layout of the three registration
tables (method pointers, invokers, generic invokers) and method bodies
inside the single raw-backed executable section.  No Unity/game inputs.
"""
import struct
import unittest

from native_il2cpp_static_fixtures import metadata_fixture, pe_fixture
from ct2trainer.native.il2cpp_live import (
    BaseChangedRefused,
    BitnessMismatchRefused,
    Il2CppLiveError,
    Il2CppLiveResolver,
    MethodIdentityRefused,
    ModuleBinding,
    ModuleShaMismatchRefused,
    NonExecutableLocationRefused,
    OutOfExtentRefused,
    POINTER_MODE_RVA,
    POINTER_MODE_VA,
    PointerTable,
    SignatureMismatchRefused,
    StaleBindingRefused,
    TableConfusionRefused,
)
from ct2trainer.native.il2cpp_static import MetadataV29, WindowsPE

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


def build_live_pe(bitness=64, *, live_base=None, pointer_mode=POINTER_MODE_VA,
                  method_table_rva=None, invoker_table_rva=None,
                  generic_table_rva=None, method_count=2, invoker_count=1,
                  generic_count=1, executable=True, write_slots=True):
    """PE fixture with registration tables and method bodies in .own."""
    data = bytearray(pe_fixture(bitness))
    defaults = table_rvas(bitness)
    method_table_rva = method_table_rva if method_table_rva is not None else defaults[0]
    invoker_table_rva = invoker_table_rva if invoker_table_rva is not None else defaults[1]
    generic_table_rva = (generic_table_rva if generic_table_rva is not None
                         else defaults[2])
    base = default_base(bitness) if live_base is None else live_base
    fmt = '<Q' if bitness == 64 else '<I'
    pointer = 8 if bitness == 64 else 4
    method_targets, invoker_target, generic_target = code_targets(bitness)
    # The shared fixture marks .own READ|LINK_READ_ONLY only; the live
    # resolver requires an executable code section, so this builder adds
    # MEM_EXECUTE to .own by default, without touching the shared file.
    if executable:
        section_at = 0x98 + (240 if bitness == 64 else 224)
        struct.pack_into('<I', data, section_at + 36, 0x60000040)

    def put(table_rva, index, target):
        value = base + target if pointer_mode == POINTER_MODE_VA else target
        struct.pack_into(fmt, data, 0x200 + (table_rva - 0x1000) + index * pointer, value)

    if write_slots:
        for index in range(method_count):
            put(method_table_rva, index, method_targets[index])
        for index in range(invoker_count):
            put(invoker_table_rva, index, invoker_target)
        for index in range(generic_count):
            put(generic_table_rva, index, generic_target)

    return bytes(data)


def make_resolver(bitness=64, *, live_base=None, module_sha=None, generation=1,
                  pointer_mode=POINTER_MODE_VA, metadata_bytes=None,
                  pe_bytes=None, method_table_rva=None, invoker_table_rva=None,
                  generic_table_rva=None, method_count=2, invoker_count=1,
                  generic_count=1, executable=True):
    defaults = table_rvas(bitness)
    method_table_rva = method_table_rva if method_table_rva is not None else defaults[0]
    invoker_table_rva = invoker_table_rva if invoker_table_rva is not None else defaults[1]
    generic_table_rva = (generic_table_rva if generic_table_rva is not None
                         else defaults[2])
    if pe_bytes is None:
        pe_bytes = build_live_pe(
            bitness, live_base=live_base, pointer_mode=pointer_mode,
            method_table_rva=method_table_rva, invoker_table_rva=invoker_table_rva,
            generic_table_rva=generic_table_rva, method_count=method_count,
            invoker_count=invoker_count, generic_count=generic_count,
            executable=executable)
    base = default_base(bitness) if live_base is None else live_base
    pe = WindowsPE(pe_bytes)
    metadata = MetadataV29(
        metadata_bytes if metadata_bytes is not None else metadata_fixture())
    binding = ModuleBinding(base, module_sha or pe.sha256, generation, bitness)
    tables = {
        'method_pointers': PointerTable('method_pointers', method_table_rva,
                                        method_count, pointer_mode),
        'invokers': PointerTable('invokers', invoker_table_rva,
                                 invoker_count, pointer_mode),
        'generic_invokers': PointerTable('generic_invokers', generic_table_rva,
                                         generic_count, pointer_mode),
    }
    resolver = Il2CppLiveResolver(
        pe, metadata, binding,
        method_pointers=tables['method_pointers'],
        invokers=tables['invokers'],
        generic_invokers=tables['generic_invokers'])
    return resolver, tables


class BindingValidationTests(unittest.TestCase):
    def test_module_binding_field_validation(self):
        with self.assertRaises(Il2CppLiveError):
            ModuleBinding(-1, 'a' * 64, 1, 64)
        with self.assertRaises(Il2CppLiveError):
            ModuleBinding(0x1000, 'A' * 64, 1, 64)
        with self.assertRaises(Il2CppLiveError):
            ModuleBinding(0x1000, 'a' * 63, 1, 64)
        with self.assertRaises(Il2CppLiveError):
            ModuleBinding(0x1000, 'a' * 64, 0, 64)
        with self.assertRaises(Il2CppLiveError):
            ModuleBinding(0x1000, 'a' * 64, 1, 33)

    def test_pointer_table_field_validation(self):
        for fields in (('', 0x1000, 1, POINTER_MODE_VA),
                       ('t', -1, 1, POINTER_MODE_VA),
                       ('t', 0x1000, -1, POINTER_MODE_VA),
                       ('t', 0x1000, 1, 'far')):
            with self.assertRaises(Il2CppLiveError):
                PointerTable(*fields)

    def test_bitness_mismatch_between_pe_and_binding_refused(self):
        pe = WindowsPE(pe_fixture(32))
        metadata = MetadataV29(metadata_fixture())
        binding = ModuleBinding(default_base(64), pe.sha256, 1, 64)
        table = PointerTable('t', 0x1000, 2, POINTER_MODE_VA)
        with self.assertRaises(BitnessMismatchRefused):
            Il2CppLiveResolver(pe, metadata, binding, method_pointers=table,
                               invokers=table, generic_invokers=table)

    def test_module_sha_mismatch_at_construction_refused(self):
        with self.assertRaises(ModuleShaMismatchRefused):
            make_resolver(module_sha='b' * 64)

    def test_live_base_overflow_address_space_refused(self):
        for bitness in (32, 64):
            with self.subTest(bitness=bitness):
                pe_bytes = build_live_pe(bitness)
                overflow = (1 << bitness) - 0x1000
                with self.assertRaises(OutOfExtentRefused):
                    make_resolver(bitness=bitness, pe_bytes=pe_bytes,
                                  live_base=overflow)

    def test_table_overlap_at_construction_refused(self):
        with self.assertRaises(TableConfusionRefused):
            make_resolver(invoker_table_rva=0x1008)
        with self.assertRaises(TableConfusionRefused):
            make_resolver(generic_table_rva=0x1024)

    def test_zero_count_tables_construct(self):
        resolver, _ = make_resolver(invoker_count=0, generic_count=0)
        snapshot = resolver.snapshot()
        self.assertEqual(snapshot['tables']['invokers']['count'], 0)
        self.assertEqual(snapshot['tables']['generic_invokers']['extent_bytes'], 0)


class ObserveTests(unittest.TestCase):
    def test_matching_observation_accepted(self):
        resolver, _ = make_resolver()
        binding = resolver.snapshot()['binding']
        resolver.observe(live_base=binding['live_base'],
                         module_sha256=binding['module_sha256'],
                         generation=binding['generation'])

    def test_base_change_refused(self):
        resolver, _ = make_resolver()
        binding = resolver.snapshot()['binding']
        with self.assertRaises(BaseChangedRefused):
            resolver.observe(live_base=binding['live_base'] + 0x1000,
                             module_sha256=binding['module_sha256'],
                             generation=binding['generation'])

    def test_hash_change_refused(self):
        resolver, _ = make_resolver()
        binding = resolver.snapshot()['binding']
        with self.assertRaises(ModuleShaMismatchRefused):
            resolver.observe(live_base=binding['live_base'],
                             module_sha256='c' * 64,
                             generation=binding['generation'])

    def test_stale_generation_refused(self):
        resolver, _ = make_resolver()
        binding = resolver.snapshot()['binding']
        with self.assertRaises(StaleBindingRefused):
            resolver.observe(live_base=binding['live_base'],
                             module_sha256=binding['module_sha256'],
                             generation=binding['generation'] + 1)


class ProveRvaTests(unittest.TestCase):
    def test_prove_rva_maps_backed_executable_bytes(self):
        resolver, _ = make_resolver()
        va, section = resolver.prove_rva(0x1040, 2)
        self.assertEqual(va, default_base(64) + 0x1040)
        self.assertEqual(section, '.own')

    def test_prove_rva_zero_fill_refused(self):
        resolver, _ = make_resolver()
        with self.assertRaises(OutOfExtentRefused):
            resolver.prove_rva(0x1200)

    def test_prove_rva_outside_image_refused(self):
        resolver, _ = make_resolver()
        with self.assertRaises(OutOfExtentRefused):
            resolver.prove_rva(0x2000)

    def test_prove_rva_in_header_refused(self):
        resolver, _ = make_resolver()
        with self.assertRaises(OutOfExtentRefused):
            resolver.prove_rva(0x100)

    def test_prove_rva_non_executable_section_refused(self):
        # .own keeps the shared fixture characteristics (READ, no EXECUTE).
        resolver, _ = make_resolver(executable=False)
        with self.assertRaises(NonExecutableLocationRefused):
            resolver.prove_rva(0x1040)

    def test_method_pointer_into_non_executable_section_refused(self):
        # Method bodies point into .own, which is not executable here.
        pe_bytes = build_live_pe(executable=False)
        resolver, _ = make_resolver(pe_bytes=pe_bytes)
        with self.assertRaises(NonExecutableLocationRefused):
            resolver.resolve_method(*IDENTITY, 'GetCurrentStatus')


class TablePointerTests(unittest.TestCase):
    def test_read_table_slot_decodes_both_modes(self):
        for mode in (POINTER_MODE_VA, POINTER_MODE_RVA):
            with self.subTest(mode=mode):
                resolver, tables = make_resolver(pointer_mode=mode)
                value, slot_rva = resolver.read_table_slot(
                    tables['method_pointers'], 0)
                self.assertEqual(slot_rva, 0x1000)
                expected = (default_base(64) + 0x1040 if mode == POINTER_MODE_VA
                            else 0x1040)
                self.assertEqual(value, expected)

    def test_read_table_slot_out_of_count_refused(self):
        resolver, tables = make_resolver()
        for index in (2, -1, 1.5):
            with self.subTest(index=index), self.assertRaises(OutOfExtentRefused):
                resolver.read_table_slot(tables['method_pointers'], index)

    def test_read_table_slot_without_source_bytes_refused(self):
        pe_bytes = build_live_pe(method_count=0, invoker_count=0,
                                 generic_count=0, write_slots=False)
        resolver, tables = make_resolver(
            pe_bytes=pe_bytes, method_count=1, invoker_count=1, generic_count=1,
            method_table_rva=0x1200, invoker_table_rva=0x1210,
            generic_table_rva=0x1220)
        with self.assertRaises(OutOfExtentRefused):
            resolver.read_table_slot(tables['method_pointers'], 0)

    def test_resolve_into_other_table_refused(self):
        base = default_base(64)
        for target in (0x1020, 0x1030):
            with self.subTest(target=target):
                pe_bytes = bytearray(build_live_pe())
                struct.pack_into('<Q', pe_bytes, 0x200, base + target)
                resolver, tables = make_resolver(pe_bytes=bytes(pe_bytes))
                with self.assertRaises(TableConfusionRefused):
                    resolver.resolve_table_pointer(tables['method_pointers'], 0)

    def test_va_pointer_outside_live_image_refused(self):
        pe_bytes = bytearray(build_live_pe())
        struct.pack_into('<Q', pe_bytes, 0x200, 0x70000000000)
        resolver, tables = make_resolver(pe_bytes=bytes(pe_bytes))
        with self.assertRaises(OutOfExtentRefused):
            resolver.resolve_table_pointer(tables['method_pointers'], 0)

    def test_va_pointer_below_live_base_refused(self):
        pe_bytes = bytearray(build_live_pe())
        struct.pack_into('<Q', pe_bytes, 0x200, 0x100)
        resolver, tables = make_resolver(pe_bytes=bytes(pe_bytes))
        with self.assertRaises(OutOfExtentRefused):
            resolver.resolve_table_pointer(tables['method_pointers'], 0)

    def test_relocated_live_base_shifts_va(self):
        live_base = default_base(64) + 0x20000
        pe_bytes = build_live_pe(live_base=live_base)
        resolver, tables = make_resolver(live_base=live_base, pe_bytes=pe_bytes)
        va, _section = resolver.resolve_table_pointer(tables['method_pointers'], 0)
        self.assertEqual(va, live_base + 0x1040)

    def test_32bit_pointer_width(self):
        resolver, tables = make_resolver(bitness=32)
        value, slot_rva = resolver.read_table_slot(tables['method_pointers'], 1)
        self.assertEqual(slot_rva, 0x1004)
        self.assertEqual(value, default_base(32) + 0x1034)
        va, _section = resolver.resolve_table_pointer(tables['method_pointers'], 1)
        self.assertEqual(va, default_base(32) + 0x1034)


class MethodResolutionTests(unittest.TestCase):
    def test_happy_path_resolves_both_metadata_methods(self):
        resolver, _tables = make_resolver()
        base = default_base(64)
        first = resolver.resolve_method(*IDENTITY, 'GetCurrentStatus')
        second = resolver.resolve_method(*IDENTITY, 'SetFlag',
                                         parameter_type_indices=(102,))
        self.assertEqual(first.va, base + 0x1040)
        self.assertEqual(first.method.token, 0x06000001)
        self.assertTrue(first.is_static)
        self.assertEqual(first.section, '.own')
        self.assertEqual(first.pointer_mode, POINTER_MODE_VA)
        self.assertEqual(first.slot_rva, 0x1000)
        self.assertEqual(first.metadata_sha256,
                         resolver.snapshot()['metadata_sha256'])
        self.assertEqual(first.generation, 1)
        self.assertEqual(second.va, base + 0x1048)
        self.assertEqual(second.method.token, 0x06000002)
        self.assertEqual(len(second.method.parameters), 1)
        self.assertEqual(second.slot_rva, 0x1008)

    def test_overload_requires_exact_raw_signature(self):
        resolver, _ = make_resolver(metadata_bytes=metadata_fixture(overload=True))
        with self.assertRaises(MethodIdentityRefused):
            resolver.resolve_method(*IDENTITY, 'GetCurrentStatus')
        resolved = resolver.resolve_method(*IDENTITY, 'GetCurrentStatus',
                                           parameter_type_indices=())
        self.assertEqual(resolved.method.token, 0x06000001)

    def test_missing_or_wrong_identity_refused(self):
        resolver, _ = make_resolver()
        for identity in (('owned.dll', 'CT2TrainerOwned', 'Counter',
                          'GetCurrentStatus'),
                         ('Owned.dll', '', 'Counter', 'GetCurrentStatus'),
                         ('Owned.dll', 'CT2TrainerOwned', 'Other',
                          'GetCurrentStatus'),
                         ('Owned.dll', 'CT2TrainerOwned', 'Counter',
                          'Getcurrentstatus')):
            with self.subTest(identity=identity):
                with self.assertRaises(MethodIdentityRefused):
                    resolver.resolve_method(*identity)

    def test_signature_model_mismatch_refused(self):
        resolver, _ = make_resolver()
        with self.assertRaises(SignatureMismatchRefused):
            resolver.resolve_method(*IDENTITY, 'SetFlag',
                                    parameter_type_indices=(102,),
                                    expected_static=False)
        with self.assertRaises(SignatureMismatchRefused):
            resolver.resolve_method(*IDENTITY, 'SetFlag',
                                    parameter_type_indices=(102,),
                                    expected_parameter_count=3)
        ok = resolver.resolve_method(*IDENTITY, 'SetFlag',
                                     parameter_type_indices=(102,),
                                     expected_static=True,
                                     expected_parameter_count=1)
        self.assertEqual(ok.method.token, 0x06000002)

    def test_method_index_beyond_table_count_refused(self):
        pe_bytes = build_live_pe(method_count=1)
        resolver, _ = make_resolver(pe_bytes=pe_bytes, method_count=1)
        resolver.resolve_method(*IDENTITY, 'GetCurrentStatus')
        with self.assertRaises(OutOfExtentRefused):
            resolver.resolve_method(*IDENTITY, 'SetFlag',
                                    parameter_type_indices=(102,))

    def test_snapshot_proofs_and_determinism(self):
        resolver, _ = make_resolver()
        resolver.resolve_method(*IDENTITY, 'GetCurrentStatus')
        resolver.resolve_method(*IDENTITY, 'SetFlag',
                                parameter_type_indices=(102,))
        first = resolver.snapshot()
        second = resolver.snapshot()
        self.assertEqual(first, second)
        self.assertEqual(first['schema'], 'ct2trainer-il2cpp-live/v1')
        self.assertEqual(first['binding']['live_base'], default_base(64))
        self.assertEqual(first['pe']['image_size'], 0x2000)
        self.assertEqual(first['tables']['method_pointers']['extent_bytes'], 16)
        self.assertEqual(len(first['proofs']), 2)
        self.assertEqual(first['proofs'][0]['name'], 'GetCurrentStatus')
        self.assertEqual(first['proofs'][1]['va'], default_base(64) + 0x1048)
        self.assertEqual(first['counts']['proofs'], 2)


if __name__ == '__main__':
    unittest.main()
