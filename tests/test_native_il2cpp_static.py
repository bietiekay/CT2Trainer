"""Static own-input positive/malformed identity and file-mapping checks."""
import struct
import unittest
from unittest.mock import patch
from ct2trainer.native.il2cpp_static import WindowsPE, MetadataV29, FormatError, METADATA_SECTIONS
from native_il2cpp_static_fixtures import pe_fixture, metadata_fixture, section_offset


class PEMappingTests(unittest.TestCase):
    def test_pe32_and_pe64_preferred_mapping_and_sha(self):
        for bitness in (32, 64):
            with self.subTest(bitness=bitness):
                pe = WindowsPE(pe_fixture(bitness))
                self.assertEqual(pe.bitness, bitness)
                self.assertEqual(pe.read_rva(0x1000, 6), b'OWNED!')
                self.assertEqual(pe.va_to_offset(pe.image_base + 0x1000, 6), 0x200)
                self.assertEqual(pe.read_rva(0, 2), b'MZ')
                self.assertEqual(len(pe.sha256), 64)

    def test_no_uint32_truncation_or_below_base_mapping(self):
        pe = WindowsPE(pe_fixture())
        for va in (pe.image_base - 1, pe.image_base + (1 << 32) + 0x1000, 1 << 64, True):
            with self.subTest(va=va), self.assertRaises(FormatError):
                pe.va_to_offset(va)

    def test_virtual_zero_fill_and_cross_section_bytes_are_not_file_bytes(self):
        pe = WindowsPE(pe_fixture())
        for rva, size in ((0x1200, 1), (0x11FF, 2), (0x12FF, 2), (0x1FFF, 2), (0x1000, 0)):
            with self.subTest(rva=rva, size=size), self.assertRaises(FormatError):
                pe.read_rva(rva, size)

    def test_truncated_dos_pe_optional_and_section_headers(self):
        for length in (0, 63, 130, 150, 0x188, 0x1AE, 0x201):
            with self.subTest(length=length), self.assertRaises(FormatError):
                WindowsPE(pe_fixture()[:length])

    def test_machine_magic_and_excessive_section_count_fail(self):
        for offset, fmt, value in ((0x84, '<H', 0xAA64), (0x98, '<H', 0x10B), (0x86, '<H', 97)):
            data = bytearray(pe_fixture())
            struct.pack_into(fmt, data, offset, value)
            with self.subTest(offset=offset), self.assertRaises(FormatError):
                WindowsPE(bytes(data))

    def test_virtual_and_raw_overlap_are_rejected_without_first_match_guess(self):
        for rva, raw in ((0x1000, 0x400), (0x2000, 0x200)):
            data = bytearray(pe_fixture())
            struct.pack_into('<H', data, 0x86, 2)
            struct.pack_into('<I', data, 0x98 + 56, 0x3000)
            struct.pack_into('<8sIIIIIIHHI', data, 0x188 + 40, b'.other', 0x200, rva, 0x200, raw, 0, 0, 0, 0, 0x40000040)
            with self.subTest(rva=rva, raw=raw), self.assertRaisesRegex(FormatError, 'Overlapping'):
                WindowsPE(bytes(data))

    def test_overflowing_raw_section_and_optional_directory_extent_fail(self):
        for offset, value in ((0x188 + 20, 0xFFFFFE00), (0x98 + 108, 17)):
            data = bytearray(pe_fixture())
            struct.pack_into('<I', data, offset, value)
            with self.subTest(offset=offset), self.assertRaises(FormatError):
                WindowsPE(bytes(data))


class MetadataIdentityTests(unittest.TestCase):
    def test_exact_image_class_method_parameter_identity_preserves_raw_indices(self):
        metadata = MetadataV29(metadata_fixture())
        method = metadata.find_method('Owned.dll', 'CT2TrainerOwned', 'Counter', 'SetFlag', parameter_type_indices=(102,))
        self.assertEqual((method.return_type_index, method.parameters[0].type_index), (101, 102))
        self.assertEqual(method.parameters[0].name, 'value')
        self.assertEqual(method.token, 0x06000002)
        self.assertTrue(method.is_static)
        self.assertEqual(method.metadata_sha256, metadata.sha256)
        self.assertFalse(hasattr(method, 'pointer'))

    def test_overload_requires_exact_raw_signature_and_duplicate_signature_stays_ambiguous(self):
        metadata = MetadataV29(metadata_fixture(overload=True))
        with self.assertRaisesRegex(FormatError, 'ambiguous'):
            metadata.find_method('Owned.dll', 'CT2TrainerOwned', 'Counter', 'GetCurrentStatus')
        method = metadata.find_method('Owned.dll', 'CT2TrainerOwned', 'Counter', 'GetCurrentStatus', parameter_type_indices=())
        self.assertEqual(method.token, 0x06000001)
        duplicate = MetadataV29(metadata_fixture(duplicate_signature=True))
        with self.assertRaisesRegex(FormatError, 'ambiguous'):
            duplicate.find_method('Owned.dll', 'CT2TrainerOwned', 'Counter', 'GetCurrentStatus', parameter_type_indices=())

    def test_wrong_image_namespace_class_name_and_return_index_never_fall_back(self):
        metadata = MetadataV29(metadata_fixture())
        for identity in (('owned.dll', 'CT2TrainerOwned', 'Counter', 'GetCurrentStatus'),
                         ('Owned.dll', '', 'Counter', 'GetCurrentStatus'),
                         ('Owned.dll', 'CT2TrainerOwned', 'Other', 'GetCurrentStatus'),
                         ('Owned.dll', 'CT2TrainerOwned', 'Counter', 'Getcurrentstatus')):
            with self.subTest(identity=identity), self.assertRaises(FormatError):
                metadata.find_method(*identity)
        with self.assertRaises(FormatError):
            metadata.find_method('Owned.dll', 'CT2TrainerOwned', 'Counter', 'GetCurrentStatus', return_type_index=999)

    def test_only_explicit_version29_and_correct_magic_are_admitted(self):
        for offset, value in ((0, 0), (4, 24), (4, 27), (4, 31), (4, 38)):
            data = bytearray(metadata_fixture())
            struct.pack_into('<I', data, offset, value)
            with self.subTest(value=value), self.assertRaises(FormatError):
                MetadataV29(bytes(data))

    def test_negative_oversized_and_overlapping_header_sections_fail(self):
        original = metadata_fixture()
        for name, extent in (('images', (-1, 40)), ('methods', (0x7FFFFFF0, 32)),
                             ('images', section_offset(original, 'typeDefinitions')), ('images', (8, 40))):
            data = bytearray(original)
            struct.pack_into('<ii', data, 8 + METADATA_SECTIONS.index(name) * 8, *extent)
            with self.subTest(name=name, extent=extent), self.assertRaises(FormatError):
                MetadataV29(bytes(data))

    def test_wrong_stride_and_aggregate_work_limit_fail(self):
        data = bytearray(metadata_fixture())
        at = 8 + METADATA_SECTIONS.index('methods') * 8
        offset, size = struct.unpack_from('<ii', data, at)
        struct.pack_into('<ii', data, at, offset, size - 1)
        with self.assertRaisesRegex(FormatError, 'layout'):
            MetadataV29(bytes(data))
        with patch('ct2trainer.native.il2cpp_static.MAX_ROWS', 2), self.assertRaisesRegex(FormatError, 'Aggregate'):
            MetadataV29(metadata_fixture())

    def test_bad_string_index_utf8_and_unterminated_name_are_rejected(self):
        original = metadata_fixture()
        image_at, _ = section_offset(original, 'images')
        data = bytearray(original)
        struct.pack_into('<i', data, image_at, 0x7FFFFFFF)
        with self.assertRaises(FormatError):
            MetadataV29(bytes(data))
        strings_at, size = section_offset(original, 'string')
        for replacement in (b'\xff', b'X'):
            data = bytearray(original)
            data[strings_at + 1] = replacement[0]
            if replacement == b'X':
                data[strings_at:strings_at + size] = b'X' * size
            with self.subTest(replacement=replacement), self.assertRaises(FormatError):
                MetadataV29(bytes(data))

    def test_orphan_or_foreign_method_and_parameter_ranges_fail(self):
        original = metadata_fixture()
        methods_at, _ = section_offset(original, 'methods')
        type_at, _ = section_offset(original, 'typeDefinitions')
        for offset, fmt, value in ((methods_at + 4, '<i', 1), (type_at + 64, '<H', 1),
                                   (methods_at + 32 + 12, '<i', 99), (methods_at + 32 + 30, '<H', 0)):
            data = bytearray(original)
            struct.pack_into(fmt, data, offset, value)
            with self.subTest(offset=offset), self.assertRaises(FormatError):
                MetadataV29(bytes(data))

    def test_duplicate_image_type_ownership_and_raw_parameter_inputs_fail(self):
        original = metadata_fixture()
        image_at, image_size = section_offset(original, 'images')
        data = bytearray(original)
        data.extend(original[image_at:image_at + image_size])
        struct.pack_into('<i', data, 8 + METADATA_SECTIONS.index('images') * 8 + 4, image_size * 2)
        with self.assertRaisesRegex(FormatError, 'multiple images'):
            MetadataV29(bytes(data))
        metadata = MetadataV29(original)
        for indices in ([102], (True,), (-1,)):
            with self.subTest(indices=indices), self.assertRaises(ValueError):
                metadata.find_method('Owned.dll', 'CT2TrainerOwned', 'Counter', 'SetFlag', parameter_type_indices=indices)

    def test_decoded_name_aggregate_bound_and_repeated_reference_cache(self):
        with patch('ct2trainer.native.il2cpp_static.MAX_DECODED_NAME_BYTES', 8), self.assertRaisesRegex(FormatError, 'byte bound'):
            MetadataV29(metadata_fixture())
        metadata = MetadataV29(metadata_fixture(overload=True))
        before = metadata._decoded_name_bytes
        for _ in range(100):
            metadata.find_method('Owned.dll', 'CT2TrainerOwned', 'Counter', 'GetCurrentStatus', parameter_type_indices=())
        self.assertEqual(before, metadata._decoded_name_bytes)

    def test_immutable_file_inputs_and_unknown_negative_type_ids_fail(self):
        with self.assertRaises(FormatError):
            MetadataV29(bytearray(metadata_fixture()))
        with self.assertRaises(FormatError):
            WindowsPE(bytearray(pe_fixture()))
        data = bytearray(metadata_fixture())
        parameters_at, _ = section_offset(data, 'parameters')
        struct.pack_into('<i', data, parameters_at + 8, -1)
        with self.assertRaisesRegex(FormatError, 'type index'):
            MetadataV29(bytes(data))


if __name__ == '__main__':
    unittest.main()
