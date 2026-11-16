/* Independently owned, deterministic code-patch target.
 * No injected code, no CE input, no background writer.
 *
 * Layout contract (shared with the pinned code-patch CTs and the probe):
 *   - The 16-byte module marker "CT2T-CPP-2026-01" occurs exactly once.
 *   - data_a holds the 8-byte baseline "DATA_A01" (44 41 54 41 5F 41 30 31);
 *     its tail four bytes (offset +4, baseline "_A01" 5F 41 30 31) are the
 *     overlap block the refusal-target record addresses.
 *   - data_b holds the 4-byte baseline "DATB" (44 41 54 42).
 *   - codepatch_probe() returns the fixed constant 0x5A5B5C5D. MSVC /Od
 *     emits it as B8 5D 5C 5B 5A C3 (x64) or
 *     55 8B EC B8 5D 5C 5B 5A 5D C3 (x86, extra frame pointer setup); the
 *     CTs patch the entry so it returns 0x46474849 instead, and the target's
 *     own protocol loop executes the patched entry on every "probe" reply.
 *   - The "setdata A|B <hex>" protocol commands let the owned gate modify a
 *     data block from the target itself (simulating an external writer);
 *     every command replies with the status line, and the bytes are
 *     re-proven by the gate's independent process-memory reader.
 *   - The build script verifies that the marker, both data baselines and
 *     the probe prologue each occur exactly once in each produced EXE and
 *     reports the byte-pinned SHA-256.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static const unsigned char marker[16] = {
    0x43, 0x54, 0x32, 0x54, 0x2d, 0x43, 0x50, 0x50,
    0x2d, 0x32, 0x30, 0x32, 0x36, 0x2d, 0x30, 0x31
};

/* Baseline "DATA_A01". Hex initializer form so the raw byte pattern occurs
 * only in the data section, never in a string literal pool. */
static unsigned char data_a[8] = {
    0x44, 0x41, 0x54, 0x41, 0x5f, 0x41, 0x30, 0x31
};

/* Baseline "DATB". */
static unsigned char data_b[4] = {
    0x44, 0x41, 0x54, 0x42
};

static int hex_equal(const char *hex, const unsigned char *bytes, size_t count)
{
    size_t index;
    for (index = 0; index < count; index++) {
        char hi = hex[index * 2], lo = hex[index * 2 + 1];
        int d1, d2;
        d1 = hi >= '0' && hi <= '9' ? hi - '0' : hi >= 'A' && hi <= 'F' ? hi - 'A' + 10 : -1;
        d2 = lo >= '0' && lo <= '9' ? lo - '0' : lo >= 'A' && lo <= 'F' ? lo - 'A' + 10 : -1;
        if (d1 < 0 || d1 > 15 || d2 < 0 || d2 > 15) return 0;
        if (bytes[index] != (unsigned char)((d1 << 4) | d2)) return 0;
    }
    return 1;
}

static int sentinels_valid(void)
{
    /* Uppercase hex form keeps the unique raw byte patterns from occurring
     * a second time in the image. */
    return hex_equal("435432542D4350502D323032362D3031", marker, 16)
        && hex_equal("444154415F413031", data_a, 8)
        && hex_equal("44415442", data_b, 4);
}

/* The probe entry must be exactly: mov eax, 0x5A5B5C5Dh ; ret */
uint32_t codepatch_probe(void)
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
    printf("{\"schema\":\"ct2trainer-owned-codepatch-target/v1\",\"pid\":%lu,"
           "\"pointer_bits\":%lu,\"pe_machine\":%lu,"
           "\"process_name\":\"NativeCodePatchFixture.exe\","
           "\"module_base\":%llu,\"module_bytes\":%lu,\"page_bytes\":%lu,"
           "\"marker_rva\":%llu,\"marker_bytes\":\"435432542d4350502d323032362d3031\","
           "\"data_a_rva\":%llu,\"data_a_bytes\":\"444154415f413031\","
           "\"data_b_rva\":%llu,\"data_b_bytes\":\"44415442\","
           "\"overlap_rva\":%llu,\"overlap_bytes\":\"5f413031\","
           "\"probe_rva\":%llu,\"probe_bytes\":\"%s\","
           "\"original_value\":%lu}\n",
         (unsigned long)GetCurrentProcessId(), bits, (unsigned long)machine,
         address(module), (unsigned long)image_size, (unsigned long)page_size,
         rva(marker, module),
         rva(data_a, module),
         rva(data_b, module),
         rva(&data_a[4], module),
         rva((const void *)codepatch_probe, module), probe_bytes,
         (unsigned long)codepatch_probe());
    fflush(stdout);
    return 1;
}

static int probe_status(DWORD sequence)
{
    printf("{\"schema\":\"ct2trainer-owned-codepatch-status/v1\",\"pid\":%lu,"
           "\"sequence\":%lu,\"probe_value\":%lu}\n",
         (unsigned long)GetCurrentProcessId(), (unsigned long)sequence,
         (unsigned long)codepatch_probe());
    fflush(stdout);
    return 1;
}

/* "setdata A <hex16>" / "setdata B <hex8>": modify one owned data block
 * from inside the target (the gate's external-writer simulation). Exactly
 * the documented byte length must be provided, terminated by the line
 * ending; anything else is a protocol failure. */
static int setdata(const char *command)
{
    unsigned char *block;
    const char *hex;
    size_t count;
    size_t index;
    size_t length;
    if (strncmp(command, "setdata A ", 10) == 0) {
        block = data_a;
        count = 8;
    } else if (strncmp(command, "setdata B ", 10) == 0) {
        block = data_b;
        count = 4;
    } else {
        return 0;
    }
    hex = command + 10;
    length = strlen(hex);
    if (length != count * 2 + 1 || hex[length - 1] != '\n') return 0;
    if (length == count * 2 + 2 && hex[length - 2] != '\r') return 0;
    for (index = 0; index < count; index++) {
        char hi = hex[index * 2], lo = hex[index * 2 + 1];
        int d1 = hi >= '0' && hi <= '9' ? hi - '0' : hi >= 'A' && hi <= 'F' ? hi - 'A' + 10 : hi >= 'a' && hi <= 'f' ? hi - 'a' + 10 : -1;
        int d2 = lo >= '0' && lo <= '9' ? lo - '0' : lo >= 'A' && lo <= 'F' ? lo - 'A' + 10 : lo >= 'a' && lo <= 'f' ? lo - 'a' + 10 : -1;
        if (d1 < 0 || d1 > 15 || d2 < 0 || d2 > 15) return 0;
        block[index] = (unsigned char)((d1 << 4) | d2);
    }
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
    if (!sentinels_valid()) return 6;
    SYSTEM_INFO system_info;
    GetSystemInfo(&system_info);
    if (!metadata(module, nt->OptionalHeader.SizeOfImage, system_info.dwPageSize))
        return 5;
    while (fgets(command, sizeof(command), stdin) != NULL) {
        if (strcmp(command, "quit\n") == 0 || strcmp(command, "quit\r\n") == 0) {
            break;
        } else if (strcmp(command, "probe\n") == 0 || strcmp(command, "probe\r\n") == 0) {
            if (!probe_status(++sequence)) { exit_code = 7; break; }
        } else if (strncmp(command, "setdata ", 8) == 0) {
            if (!setdata(command)) { exit_code = 7; break; }
            if (!probe_status(++sequence)) { exit_code = 7; break; }
        } else {
            exit_code = 7; break;
        }
    }
    return exit_code;
}
