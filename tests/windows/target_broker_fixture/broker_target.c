/* Independent owned target and fixed ABI contracts. MIT: Native license. */
#include "broker_abi.h"
#include <stdio.h>
#include <wchar.h>
#include <stdlib.h>
#include <string.h>

static __declspec(noinline) int32_t __cdecl owned_cdecl_add(int32_t a, int32_t b) { return a + b; }
static __declspec(noinline) int32_t __stdcall owned_stdcall_add(int32_t a, int32_t b) { return a + b; }
static __declspec(noinline) uint64_t __cdecl owned_wide(uint32_t high, uint32_t low) { return ((uint64_t)high << 32) | low; }
static __declspec(noinline) double __cdecl owned_mixed(int32_t a, double b, int32_t c, float d, int32_t e) {
    return (double)a + b + (double)c + (double)d + (double)e;
}
static volatile LONG g_main_value;
static __declspec(noinline) uint32_t __cdecl owned_main_boolean(uint32_t value, uint32_t main_tid) {
    if (GetCurrentThreadId() != main_tid) return ERROR_INVALID_THREAD_ID;
    InterlockedExchange(&g_main_value, (LONG)value); return 0;
}
static uint32_t __cdecl owned_dispatch(const tf_broker_frame *request, tf_broker_frame *reply,
                                      HANDLE release, HANDLE owner, uint32_t main_tid) {
    int32_t a, b, c, e, result; uint32_t high, low, boolean, error; uint64_t wide;
    double x, mixed; float y;
    /* Function-pointer calls keep real ABI entry and return paths in the fixture. */
    int32_t (__cdecl *volatile cdecl_fn)(int32_t, int32_t) = owned_cdecl_add;
    int32_t (__stdcall *volatile stdcall_fn)(int32_t, int32_t) = owned_stdcall_add;
    uint64_t (__cdecl *volatile wide_fn)(uint32_t, uint32_t) = owned_wide;
    double (__cdecl *volatile mixed_fn)(int32_t, double, int32_t, float, int32_t) = owned_mixed;
    HANDLE waits[2] = {release, owner};
    switch (request->operation) {
    case TF_OP_WAIT_ADD:
        if (WaitForMultipleObjects(2, waits, FALSE, INFINITE) != WAIT_OBJECT_0) return ERROR_CANCELLED;
        /* Fall through to the typed call only after the target-owned release. */
    case TF_OP_CDECL_ADD: case TF_OP_STDCALL_ADD:
        memcpy(&a, request->payload, 4); memcpy(&b, request->payload + 4, 4);
        result = request->operation == TF_OP_STDCALL_ADD ? stdcall_fn(a, b) : cdecl_fn(a, b);
        reply->result_kind = 1; reply->payload_size = 4; memcpy(reply->payload, &result, 4); return 0;
    case TF_OP_WIDE:
        memcpy(&high, request->payload, 4); memcpy(&low, request->payload + 4, 4); wide = wide_fn(high, low);
        reply->result_kind = 2; reply->payload_size = 8; memcpy(reply->payload, &wide, 8); return 0;
    case TF_OP_MIXED:
        memcpy(&a, request->payload, 4); memcpy(&x, request->payload + 4, 8);
        memcpy(&c, request->payload + 12, 4); memcpy(&y, request->payload + 16, 4); memcpy(&e, request->payload + 20, 4);
        mixed = mixed_fn(a, x, c, y, e); reply->result_kind = 3; reply->payload_size = 8;
        memcpy(reply->payload, &mixed, 8); return 0;
    case TF_OP_ECHO:
        reply->result_kind = 4; reply->payload_size = request->payload_size;
        memcpy(reply->payload, request->payload, request->payload_size); return 0;
    case TF_OP_MAIN_BOOL:
        memcpy(&boolean, request->payload, 4); error = owned_main_boolean(boolean, main_tid); if (error) return error;
        reply->result_kind = 5; reply->payload_size = 4; memcpy(reply->payload, &boolean, 4); return 0;
    default: return ERROR_INVALID_FUNCTION;
    }
}
static uint64_t owned_created(void) {
    FILETIME a, b, c, d; if (!GetProcessTimes(GetCurrentProcess(), &a, &b, &c, &d)) return 0;
    return ((uint64_t)a.dwHighDateTime << 32) | a.dwLowDateTime;
}
int wmain(int argc, wchar_t **argv) {
    HMODULE module; tf_broker_start_fn start; tf_broker_pump_fn pump; tf_broker_inspect_fn inspect;
    uint32_t owner, index; uint64_t created; tf_broker_stats stats;
    uint8_t nonce[16]; HANDLE input; DWORD available = 0, read = 0; char command[16]; wchar_t *end;
    if (argc != 5 || wcslen(argv[4]) != 32) return 2;
    owner = wcstoul(argv[2], &end, 10); if (*end || !owner) return 3;
    created = _wcstoui64(argv[3], &end, 10); if (*end || !created) return 3;
    for (index = 0; index < 16; ++index) {
        wchar_t part[3] = {argv[4][index * 2], argv[4][index * 2 + 1], 0};
        unsigned long value = wcstoul(part, &end, 16); if (*end || value > 255) return 3; nonce[index] = (uint8_t)value;
    }
    module = LoadLibraryExW(argv[1], NULL, LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_SYSTEM32);
    if (!module) return 4;
    start = (tf_broker_start_fn)(void *)GetProcAddress(module, "TFBrokerStart");
    pump = (tf_broker_pump_fn)(void *)GetProcAddress(module, "TFBrokerPumpMain");
    inspect = (tf_broker_inspect_fn)(void *)GetProcAddress(module, "TFBrokerInspect");
    if (!start || !pump || !inspect || !start(owner, created, nonce, owned_dispatch)) return 5;
    printf("{\"schema\":\"ct2trainer-owned-broker-target/v1\",\"pid\":%lu,\"created\":%llu,\"pointer_bits\":%u,\"main_thread_id\":%lu}\n",
        (unsigned long)GetCurrentProcessId(), (unsigned long long)owned_created(), (unsigned int)(sizeof(void *) * 8u), (unsigned long)GetCurrentThreadId());
    fflush(stdout); input = GetStdHandle(STD_INPUT_HANDLE);
    while (PeekNamedPipe(input, NULL, 0, NULL, &available, NULL)) {
        pump();
        if (available) {
            if (!ReadFile(input, command, sizeof(command), &read, NULL) || !read) break;
            if (memchr(command, 'q', read)) break;
        }
        Sleep(1);
    }
    /* Diagnostic grace lets owner-loss cancellation and worker return settle.
     * It never authorizes a new call and does not unload or free a request. */
    for (index = 0; index < 100; ++index) { pump(); Sleep(1); }
    if (!inspect(&stats)) return 6;
    printf("{\"schema\":\"ct2trainer-owned-broker-retention/v1\",\"requests\":%lu,\"worker_handles\":%lu,\"live_workers\":%lu,\"cancelled\":%lu,\"owner_alive\":%lu,\"calls\":%llu}\n",
        (unsigned long)stats.requests, (unsigned long)stats.worker_handles, (unsigned long)stats.live_workers,
        (unsigned long)stats.cancelled, (unsigned long)stats.owner_alive, (unsigned long long)stats.calls);
    fflush(stdout);
    /* DLL, all workers, events, buffers and ledger stay resident until process exit. */
    return 0;
}
