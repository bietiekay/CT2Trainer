/* Independently authored, owned String fixture. No injected code or CE input.
 * Stdin commands perform deliberate local mutations; no background writer runs.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef struct GuardedBytes8 {
    BYTE before[8];
    BYTE value[8];
    BYTE after[8];
} GuardedBytes8;

typedef struct GuardedWide16 {
    BYTE before[8];
    WCHAR value[16];
    BYTE after[8];
} GuardedWide16;

typedef char byte_layout_check[(sizeof(GuardedBytes8) == 24 &&
    offsetof(GuardedBytes8, value) == 8 && offsetof(GuardedBytes8, after) == 16) ? 1 : -1];
typedef char wide_layout_check[(sizeof(GuardedWide16) == 48 &&
    sizeof(WCHAR) == 2 && offsetof(GuardedWide16, value) == 8 &&
    offsetof(GuardedWide16, after) == 40) ? 1 : -1];

static volatile GuardedBytes8 ascii_buffer;
static volatile GuardedWide16 utf16_buffer;
static volatile GuardedBytes8 fixed_buffer;
static volatile BYTE *readonly_region;
static volatile BYTE *executable_region;
static DWORD command_sequence;

static unsigned long long address(const volatile void *pointer) {
    return (unsigned long long)(uintptr_t)pointer;
}

static unsigned long long rva(const volatile void *pointer, HMODULE module) {
    return (unsigned long long)((uintptr_t)pointer - (uintptr_t)module);
}

static void hex_bytes(const volatile BYTE *bytes, size_t count) {
    size_t index;
    for (index = 0; index < count; ++index) printf("%02x", (unsigned int)bytes[index]);
}

static int region_json(const volatile void *pointer) {
    MEMORY_BASIC_INFORMATION info;
    if (VirtualQuery((LPCVOID)pointer, &info, sizeof(info)) != sizeof(info)) return 0;
    printf("{\"base\":%llu,\"bytes\":%llu,\"state\":%lu,\"protection\":%lu,\"type\":%lu}",
        address(info.BaseAddress), (unsigned long long)info.RegionSize,
        (unsigned long)info.State, (unsigned long)info.Protect, (unsigned long)info.Type);
    return 1;
}

static int guarded_status(const volatile BYTE *before, const volatile BYTE *value,
    size_t size, const volatile BYTE *after) {
    printf("{\"before\":\""); hex_bytes(before, 8);
    printf("\",\"value\":\""); hex_bytes(value, size);
    printf("\",\"after\":\""); hex_bytes(after, 8);
    printf("\",\"region\":");
    if (!region_json(value)) return 0;
    printf("}");
    return 1;
}

static int status(void) {
    printf("{\"schema\":\"ct2trainer-owned-string-status/v1\",\"pid\":%lu,\"sequence\":%lu,\"buffers\":{\"ascii\":",
        (unsigned long)GetCurrentProcessId(), (unsigned long)command_sequence);
    if (!guarded_status(ascii_buffer.before, ascii_buffer.value, 8, ascii_buffer.after)) return 0;
    printf(",\"utf16\":");
    if (!guarded_status(utf16_buffer.before, (const volatile BYTE *)utf16_buffer.value,
        32, utf16_buffer.after)) return 0;
    printf(",\"fixed\":");
    if (!guarded_status(fixed_buffer.before, fixed_buffer.value, 8, fixed_buffer.after)) return 0;
    printf("},\"readonly\":{\"value\":\""); hex_bytes(readonly_region, 8);
    printf("\",\"region\":"); if (!region_json(readonly_region)) return 0;
    printf("},\"executable\":{\"value\":\""); hex_bytes(executable_region, 8);
    printf("\",\"region\":"); if (!region_json(executable_region)) return 0;
    printf("}}\n");
    fflush(stdout);
    return 1;
}

static void buffer_metadata(const volatile BYTE *before, const volatile void *value,
    const volatile BYTE *after, HMODULE module, DWORD units, DWORD unit_bytes,
    int terminated, DWORD tail_offset) {
    printf("{\"address\":%llu,\"rva\":%llu,\"length\":%lu,\"unit_bytes\":%lu,"
        "\"read_bytes\":%lu,\"zero_terminate\":%s,\"full_address\":%llu,\"full_rva\":%llu,"
        "\"full_bytes\":%lu,\"before_address\":%llu,\"before_rva\":%llu,\"guard_bytes\":8,"
        "\"after_address\":%llu,\"after_rva\":%llu,\"tail_offset\":%lu}",
        address(value), rva(value, module), (unsigned long)units, (unsigned long)unit_bytes,
        (unsigned long)(units * unit_bytes), terminated ? "true" : "false",
        address(before), rva(before, module), (unsigned long)(units * unit_bytes + 16u),
        address(before), rva(before, module), address(after), rva(after, module),
        (unsigned long)tail_offset);
}

static int metadata(HMODULE module, DWORD image_size, DWORD page_size) {
#ifdef _WIN64
    const DWORD machine = IMAGE_FILE_MACHINE_AMD64;
#else
    const DWORD machine = IMAGE_FILE_MACHINE_I386;
#endif
    printf("{\"schema\":\"ct2trainer-owned-string-target/v1\",\"pid\":%lu,"
        "\"pointer_bits\":%lu,\"pe_machine\":%lu,\"process_name\":\"NativeStringFixture.exe\","
        "\"module_base\":%llu,\"module_bytes\":%lu,\"page_bytes\":%lu,\"buffers\":{\"ascii\":",
        (unsigned long)GetCurrentProcessId(), (unsigned long)(sizeof(void *) * 8u),
        (unsigned long)machine, address(module), (unsigned long)image_size, (unsigned long)page_size);
    buffer_metadata(ascii_buffer.before, ascii_buffer.value, ascii_buffer.after, module, 8, 1, 1, 4);
    printf(",\"utf16\":");
    buffer_metadata(utf16_buffer.before, utf16_buffer.value, utf16_buffer.after, module, 16, 2, 1, 12);
    printf(",\"fixed\":");
    /* Fixed strings own all bytes. tail_offset == read_bytes means no ignored tail. */
    buffer_metadata(fixed_buffer.before, fixed_buffer.value, fixed_buffer.after, module, 8, 1, 0, 8);
    printf("},\"readonly\":{\"address\":%llu,\"pointer_address\":%llu,\"pointer_rva\":%llu,"
        "\"read_bytes\":8,\"allocation_bytes\":%lu,\"expected_protection\":%lu},"
        "\"executable\":{\"address\":%llu,\"pointer_address\":%llu,\"pointer_rva\":%llu,"
        "\"read_bytes\":8,\"allocation_bytes\":%lu,\"expected_protection\":%lu}}\n",
        address(readonly_region), address(&readonly_region), rva(&readonly_region, module),
        (unsigned long)page_size, (unsigned long)PAGE_READONLY,
        address(executable_region), address(&executable_region), rva(&executable_region, module),
        (unsigned long)page_size, (unsigned long)PAGE_EXECUTE_READWRITE);
    fflush(stdout);
    return 1;
}

static void initialize_buffers(void) {
    DWORD index;
    for (index = 0; index < 8; ++index) {
        ascii_buffer.before[index] = (BYTE)(0xa0u + index);
        ascii_buffer.after[index] = (BYTE)(0xa8u + index);
        utf16_buffer.before[index] = (BYTE)(0xb0u + index);
        utf16_buffer.after[index] = (BYTE)(0xb8u + index);
        fixed_buffer.before[index] = (BYTE)(0xc0u + index);
        fixed_buffer.after[index] = (BYTE)(0xc8u + index);
    }
    ascii_buffer.value[0] = 'o'; ascii_buffer.value[1] = 'l'; ascii_buffer.value[2] = 'd';
    ascii_buffer.value[3] = 0;
    for (index = 4; index < 8; ++index) ascii_buffer.value[index] = (BYTE)('Q' + index - 4);
    utf16_buffer.value[0] = 'O'; utf16_buffer.value[1] = 'L'; utf16_buffer.value[2] = 'D';
    utf16_buffer.value[3] = 0xd83d; utf16_buffer.value[4] = 0xde42; utf16_buffer.value[5] = 0;
    for (index = 6; index < 16; ++index) utf16_buffer.value[index] = (WCHAR)(0x3310u + index);
    /* Deliberately invalid surrogate after NUL verifies visible-prefix decoding. */
    utf16_buffer.value[6] = 0xdead;
    fixed_buffer.value[0] = 'F'; fixed_buffer.value[1] = 'I'; fixed_buffer.value[2] = 0;
    fixed_buffer.value[3] = 'X'; fixed_buffer.value[4] = 'E'; fixed_buffer.value[5] = 'D';
    fixed_buffer.value[6] = '!'; fixed_buffer.value[7] = '?';
}

static int release_regions(void) {
    int ok = 1;
    if (readonly_region != NULL && !VirtualFree((void *)readonly_region, 0, MEM_RELEASE)) ok = 0;
    if (executable_region != NULL && !VirtualFree((void *)executable_region, 0, MEM_RELEASE)) ok = 0;
    readonly_region = NULL; executable_region = NULL;
    return ok;
}

int main(void) {
    HMODULE module = GetModuleHandleW(NULL);
    const IMAGE_DOS_HEADER *dos;
    const IMAGE_NT_HEADERS *nt;
    SYSTEM_INFO system_info;
    DWORD old_protection, index;
    char command[64];
    int exit_code = 0;
    if (module == NULL) return 2;
    dos = (const IMAGE_DOS_HEADER *)module;
    if (dos->e_magic != IMAGE_DOS_SIGNATURE || dos->e_lfanew <= 0) return 3;
    nt = (const IMAGE_NT_HEADERS *)((const BYTE *)module + dos->e_lfanew);
    if (nt->Signature != IMAGE_NT_SIGNATURE || nt->OptionalHeader.SizeOfImage == 0) return 4;
    GetSystemInfo(&system_info);
    readonly_region = (volatile BYTE *)VirtualAlloc(NULL, system_info.dwPageSize,
        MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
    executable_region = (volatile BYTE *)VirtualAlloc(NULL, system_info.dwPageSize,
        MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
    if (readonly_region == NULL || executable_region == NULL) { release_regions(); return 5; }
    for (index = 0; index < 8; ++index) {
        readonly_region[index] = (BYTE)('R' + index);
        executable_region[index] = (BYTE)('E' + index);
    }
    if (!VirtualProtect((void *)readonly_region, system_info.dwPageSize, PAGE_READONLY, &old_protection) ||
        !VirtualProtect((void *)executable_region, system_info.dwPageSize, PAGE_EXECUTE_READWRITE, &old_protection)) {
        release_regions(); return 6;
    }
    initialize_buffers();
    metadata(module, nt->OptionalHeader.SizeOfImage, system_info.dwPageSize);
    while (fgets(command, sizeof(command), stdin) != NULL) {
        if (strcmp(command, "quit\n") == 0 || strcmp(command, "quit\r\n") == 0) break;
        if (strcmp(command, "mutate-prefix\n") == 0 || strcmp(command, "mutate-prefix\r\n") == 0) {
            ascii_buffer.value[0] = 'M'; utf16_buffer.value[0] = 'M'; fixed_buffer.value[0] = 'M';
            ++command_sequence;
        } else if (strcmp(command, "mutate-tail\n") == 0 || strcmp(command, "mutate-tail\r\n") == 0) {
            ascii_buffer.value[7] ^= 1u; utf16_buffer.value[15] ^= 1u; fixed_buffer.value[7] ^= 1u;
            ++command_sequence;
        } else if (strcmp(command, "status\n") != 0 && strcmp(command, "status\r\n") != 0) {
            exit_code = 7; break;
        }
        if (!status()) { exit_code = 8; break; }
    }
    if (!release_regions() && exit_code == 0) exit_code = 9;
    return exit_code;
}
