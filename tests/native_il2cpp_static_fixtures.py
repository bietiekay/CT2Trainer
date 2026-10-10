"""Hand-authored inert PE/v29 metadata fixture generator, no Unity/game inputs."""
import struct
from ct2trainer.native.il2cpp_static import METADATA_SECTIONS, HEADER_SIZE


def pe_fixture(bitness=64):
    data = bytearray(0x600)
    data[:2] = b'MZ'
    struct.pack_into('<I', data, 60, 0x80)
    data[0x80:0x84] = b'PE\0\0'
    machine, magic, optional_size = (0x8664, 0x20B, 240) if bitness == 64 else (0x14C, 0x10B, 224)
    struct.pack_into('<HHIIIHH', data, 0x84, machine, 1, 0, 0, 0, optional_size, 0x2002)
    optional = 0x98
    struct.pack_into('<H', data, optional, magic)
    if bitness == 64:
        struct.pack_into('<Q', data, optional + 24, 0x180000000)
        struct.pack_into('<I', data, optional + 108, 16)
    else:
        struct.pack_into('<I', data, optional + 28, 0x400000)
        struct.pack_into('<I', data, optional + 92, 16)
    struct.pack_into('<II', data, optional + 32, 0x1000, 0x200)
    struct.pack_into('<II', data, optional + 56, 0x2000, 0x200)
    struct.pack_into('<8sIIIIIIHHI', data, optional + optional_size, b'.own', 0x300, 0x1000,
                     0x200, 0x200, 0, 0, 0, 0, 0x40000040)
    data[0x200:0x206] = b'OWNED!'
    return bytes(data)


def metadata_fixture(overload=False, duplicate_signature=False):
    names = ['', 'Owned.dll', 'CT2TrainerOwned', 'Counter', 'GetCurrentStatus', 'value', 'SetFlag']
    strings = bytearray()
    indices = {}
    for name in names:
        indices[name] = len(strings)
        strings.extend(name.encode('utf-8') + b'\0')
    methods = [(indices['GetCurrentStatus'], 0, 100, -1, -1, 0x06000001, 0x10, 0, 0xFFFF, 0),
               (indices['SetFlag'], 0, 101, 0, -1, 0x06000002, 0x10, 0, 0xFFFF, 1)]
    parameters = [(indices['value'], 0x08000001, 102)]
    if overload:
        methods.append((indices['GetCurrentStatus'], 0, 100, 1, -1, 0x06000003, 0x10, 0, 0xFFFF, 1))
        parameters.append((indices['value'], 0x08000002, 102))
    if duplicate_signature:
        methods.append((indices['GetCurrentStatus'], 0, 100, -1, -1, 0x06000004, 0x10, 0, 0xFFFF, 0))
    type_row = (indices['Counter'], indices['CT2TrainerOwned'], 0, -1, -1, -1, -1, 0,
                -1, 0, -1, -1, -1, -1, -1, -1, len(methods), 0, 0, 0, 0, 0, 0, 0, 0, 0x02000001)
    image_row = (indices['Owned.dll'], 0, 0, 1, -1, 0, -1, 1, -1, 0)
    chunks = {'string': bytes(strings),
              'methods': b''.join(struct.pack('<5iI4H', *row) for row in methods),
              'parameters': b''.join(struct.pack('<iIi', *row) for row in parameters),
              'typeDefinitions': struct.pack('<7iI8i8HII', *type_row),
              'images': struct.pack('<iiiIiIiIiI', *image_row)}
    data = bytearray(HEADER_SIZE)
    struct.pack_into('<Ii', data, 0, 0xFAB11BAF, 29)
    for index, name in enumerate(METADATA_SECTIONS):
        if name in chunks:
            offset = len(data)
            data.extend(chunks[name])
            struct.pack_into('<ii', data, 8 + index * 8, offset, len(chunks[name]))
    return bytes(data)


def section_offset(data, name):
    return struct.unpack_from('<ii', data, 8 + METADATA_SECTIONS.index(name) * 8)
