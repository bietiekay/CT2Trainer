/* Independently owned, deterministic Global-allocation target.
 * No injected code, no CE input, no background writer.
 *
 * Layout contract (shared with the pinned global CT and the probe):
 *   - global_state.marker holds the unique 16-byte module anchor
 *     "CT2T-GLB-2026-01"; the CT locates it with aobscanmodule.
 *   - global_probe() returns the fixed constant 0x5A5B5C5D. MSVC /Od emits
 *     it as B8 5D 5C 5B 5A C3 (x64) or 55 8B EC B8 5D 5C 5B 5A 5D C3 (x86,
 *     extra frame pointer setup); the CTs patch the first five bytes of the
 *     entry with a jump stub into a trainer-owned cave that reads the
 *     shared RW global and returns it.
 *   - The build script verifies that both patterns occur exactly once
 *     in each produced EXE and reports the byte-pinned SHA-256.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef struct GlobalState {
    unsigned char marker[16];
} GlobalState;

/* ASCII marker: CT2T-GLB-2026-01. It belongs only to this process image.
 * The byte content is verified at process start; only the size is a valid
 * C constant expression for a compile-time assertion. */
static const GlobalState global_state = {
    {0x43, 0x54, 0x32, 0x54, 0x2d, 0x47, 0x4c, 0x42,
     0x2d, 0x32, 0x30, 0x32, 0x36, 0x2d, 0x30, 0x31}
};

typedef char global_state_is_16[(sizeof(global_state) == 16) ? 1 : -1];

static int marker_valid(void)
{
    /* Hex form keeps the unique raw 16-byte marker from occurring a second
     * time in the image. */
    static const char hex[33] = "435432542D474C422D323032362D3031";
    unsigned index;
    int d1, d2;
    for (index = 0; index < 16u; index++) {
        char hi = hex[index * 2], lo = hex[index * 2 + 1];
        d1 = hi >= '0' && hi <= '9' ? hi - '0' : hi >= 'A' && hi <= 'F' ? hi - 'A' + 10 : -1;
        d2 = lo >= '0' && lo <= '9' ? lo - '0' : lo >= 'A' && lo <= 'F' ? lo - 'A' + 10 : -1;
        if (d1 < 0 || d1 > 15 || d2 < 0 || d2 > 15) return 0;
        if (global_state.marker[index] != (unsigned char)((d1 << 4) | d2)) return 0;
    }
    return 1;
}

/* The probe entry must be exactly: mov eax, 0x5A5B5C5Dh ; ret */
uint32_t global_probe(void)
{
    return 0x5A5B5C5Du;
}

static unsigned long long address(const void *pointer)
{
    return (unsigned long long)(uintptr_t)pointer;
}

static unsigned long long rva(const void *pointer, HMODULE module)
{
    return (unsigned long long)((uintptr_t)pointer - (uintptr_t)module);
}

static int metadata(HMODULE module, DWORD image_size, DWORD page_size)
{
#ifdef _WIN64
    const DWORD machine = IMAGE_FILE_MACHINE_AMD64;
    const unsigned long bits = 64u;
    const char *probe_bytes = "b85d5c5b5ac3";
#else
    const DWORD machine = IMAGE_FILE_MACHINE_I386;
    const unsigned long bits = 32u;
    const char *probe_bytes = "558becb85d5c5b5a5dc3";
#endif
    printf("{\"schema\":\"ct2trainer-owned-global-target/v1\",\"pid\":%lu,"
           "\"pointer_bits\":%lu,\"pe_machine\":%lu,"
           "\"process_name\":\"NativeGlobalFixture.exe\","
           "\"module_base\":%llu,\"module_bytes\":%lu,\"page_bytes\":%lu,"
           "\"marker_rva\":%llu,\"marker_bytes\":\"435432542d474c422d323032362d3031\","
           "\"probe_rva\":%llu,\"probe_bytes\":\"%s\","
           "\"original_value\":%lu}\n",
        (unsigned long)GetCurrentProcessId(), bits, (unsigned long)machine,
        address(module), (unsigned long)image_size, (unsigned long)page_size,
        rva(global_state.marker, module),
        rva((const void *)global_probe, module), probe_bytes,
        (unsigned long)global_probe());
    fflush(stdout);
    return 1;
}

static int probe_status(DWORD sequence)
{
    printf("{\"schema\":\"ct2trainer-owned-global-status/v1\",\"pid\":%lu,"
           "\"sequence\":%lu,\"probe_value\":%lu}\n",
        (unsigned long)GetCurrentProcessId(), (unsigned long)sequence,
        (unsigned long)global_probe());
    fflush(stdout);
    return 1;
}

int main(void)
{
    HMODULE module = GetModuleHandleW(NULL);
    const IMAGE_DOS_HEADER *dos;
    const IMAGE_NT_HEADERS *nt;
    DWORD sequence = 0;
    char command[64];
    int exit_code = 0;
    if (module == NULL) return 2;
    dos = (const IMAGE_DOS_HEADER *)module;
    if (dos->e_magic != IMAGE_DOS_SIGNATURE || dos->e_lfanew <= 0) return 3;
    nt = (const IMAGE_NT_HEADERS *)((const BYTE *)module + dos->e_lfanew);
    if (nt->Signature != IMAGE_NT_SIGNATURE || nt->OptionalHeader.SizeOfImage == 0) return 4;
    if (!marker_valid()) return 6;
    SYSTEM_INFO system_info;
    GetSystemInfo(&system_info);
    if (!metadata(module, nt->OptionalHeader.SizeOfImage, system_info.dwPageSize))
        return 5;
    while (fgets(command, sizeof(command), stdin) != NULL) {
        if (strcmp(command, "quit\n") == 0 || strcmp(command, "quit\r\n") == 0) {
            break;
        } else if (strcmp(command, "probe\n") == 0 || strcmp(command, "probe\r\n") == 0) {
            if (!probe_status(++sequence)) { exit_code = 7; break; }
        } else {
            exit_code = 7; break;
        }
    }
    return exit_code;
}
