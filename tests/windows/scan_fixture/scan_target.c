/* Independently owned scan target. It receives no code or DLL injection.
 * Three module patterns and one private allocation are initialized at runtime.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static volatile BYTE nth_regions[4][32];
static volatile BYTE *private_region;

__declspec(noinline) static BYTE nth_byte(DWORD index) {
    if (index < 4) return (BYTE)(index == 0 ? 17 : 0);
    return (BYTE)(((index * 29u + 83u) ^ 0xd6u) & 255u);
}

__declspec(noinline) static BYTE private_byte(DWORD index) {
    if (index < 4) return (BYTE)((0x11223344u >> (index * 8u)) & 255u);
    return (BYTE)(((index * 47u + 19u) ^ 0xb7u) & 255u);
}

static void set_nth(DWORD slot) {
    DWORD index;
    for (index = 0; index < 16; ++index) nth_regions[slot][index] = nth_byte(index);
}

static DWORD read_value(const volatile BYTE *data) {
    return (DWORD)data[0] | ((DWORD)data[1] << 8u) |
        ((DWORD)data[2] << 16u) | ((DWORD)data[3] << 24u);
}

static void status(void) {
    printf("{\"pid\":%lu,\"private_value\":%lu,\"nth_values\":[%lu,%lu,%lu,%lu]}\n",
        (unsigned long)GetCurrentProcessId(), (unsigned long)read_value(private_region + 16),
        (unsigned long)read_value(nth_regions[0]), (unsigned long)read_value(nth_regions[1]),
        (unsigned long)read_value(nth_regions[2]), (unsigned long)read_value(nth_regions[3]));
    fflush(stdout);
}

int main(void) {
    DWORD slot, index;
    char command[64];
    private_region = (volatile BYTE *)VirtualAlloc(NULL, 4096,
        MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
    if (private_region == NULL) return 2;
    for (index = 0; index < 64; ++index) private_region[index] = 0xabu;
    for (index = 0; index < 32; ++index) private_region[16 + index] = private_byte(index);
    for (slot = 0; slot < 4; ++slot) {
        for (index = 16; index < 32; ++index) nth_regions[slot][index] = (BYTE)(0xe0u + slot);
        if (slot != 0) set_nth(slot);
    }
    printf("{\"schema\":\"ct2trainer-owned-scan-target/v1\",\"pid\":%lu,"
        "\"pointer_bits\":%lu,\"private\":%llu,\"nth\":[%llu,%llu,%llu,%llu]}\n",
        (unsigned long)GetCurrentProcessId(), (unsigned long)(sizeof(void *) * 8u),
        (unsigned long long)(uintptr_t)(private_region + 16),
        (unsigned long long)(uintptr_t)nth_regions[0], (unsigned long long)(uintptr_t)nth_regions[1],
        (unsigned long long)(uintptr_t)nth_regions[2], (unsigned long long)(uintptr_t)nth_regions[3]);
    fflush(stdout);
    while (fgets(command, sizeof(command), stdin) != NULL) {
        if (strcmp(command, "status\n") == 0) status();
        else if (strcmp(command, "add-first\n") == 0) {
            set_nth(0);
            status();
        } else if (strcmp(command, "quit\n") == 0) {
            if (!VirtualFree((void *)private_region, 0, MEM_RELEASE)) return 3;
            return 0;
        } else return 4;
    }
    if (!VirtualFree((void *)private_region, 0, MEM_RELEASE)) return 5;
    return 0;
}
