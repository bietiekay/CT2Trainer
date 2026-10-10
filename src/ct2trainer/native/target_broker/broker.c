/* Independent Native broker. MIT: licenses/CT2Trainer-MIT.txt.
 * No CE source, remote loader, arbitrary function pointer or executable allocation.
 * Every request buffer, event and worker handle is retained until process exit.
 * No unload API exists: an attached host must keep this DLL loaded until exit. */
#define TF_BROKER_BUILD
#include "broker_abi.h"
#include <sddl.h>
#include <stdio.h>
#include <string.h>
#include <math.h>
#include <float.h>

typedef struct tf_slot {
    tf_broker_frame request, result;
    volatile LONG state; /* Naturally aligned private target CAS, outside packed ABI. */
    HANDLE thread, start_gate, release;
    LONG main_returned;
} tf_slot;
static SRWLOCK g_lock = SRWLOCK_INIT;
static tf_slot g_slots[TF_BROKER_MAX_REQUESTS];
static uint32_t g_count, g_main_tid, g_tls = TLS_OUT_OF_INDEXES;
static uint64_t g_calls, g_owner_created, g_target_created, g_frequency, g_main_created;
static uint32_t g_owner_pid, g_target_pid;
static uint8_t g_nonce[16];
static HANDLE g_owner, g_server;
static tf_broker_dispatch_fn g_dispatch;
static WCHAR g_pipe[128];
static PSECURITY_DESCRIPTOR g_security;
static volatile LONG g_initialized;
/* Unknown async storage is process-lifetime heap memory, never stack memory. */
typedef struct tf_io_storage { OVERLAPPED overlap; uint8_t bytes[sizeof(tf_broker_frame)]; } tf_io_storage;
static tf_io_storage *g_retained_io;
static HANDLE g_retained_pipe;
static volatile LONG g_io_uncertain;

static uint64_t tf_filetime(FILETIME value) { return ((uint64_t)value.dwHighDateTime << 32) | value.dwLowDateTime; }
static uint64_t tf_now(void) { LARGE_INTEGER value; if (!QueryPerformanceCounter(&value) || value.QuadPart < 0) return 0; return (uint64_t)value.QuadPart; }
static uint64_t tf_process_created(HANDLE handle) {
    FILETIME a, b, c, d;
    if (!GetProcessTimes(handle, &a, &b, &c, &d)) return 0;
    return tf_filetime(a);
}
static uint64_t tf_thread_created(HANDLE handle) {
    FILETIME a, b, c, d;
    if (!GetThreadTimes(handle, &a, &b, &c, &d)) return 0;
    return tf_filetime(a);
}
static int tf_owner_alive(void) { return g_owner && WaitForSingleObject(g_owner, 0) == WAIT_TIMEOUT && tf_process_created(g_owner) == g_owner_created; }
static int tf_admitted(const tf_broker_frame *request) {
    uint64_t now = tf_now();
    return tf_owner_alive() && now && now < request->deadline_qpc && request->qpc_frequency == g_frequency;
}
static void tf_response(const tf_broker_frame *request, tf_broker_frame *reply, uint32_t status, uint32_t error) {
    *reply = *request;
    reply->status = status; reply->error = error;
    reply->thread_id = 0; reply->thread_created = 0;
    reply->main_thread_id = g_main_tid; reply->pointer_bits = (uint32_t)(sizeof(void *) * 8u);
    reply->qpc_frequency = g_frequency; reply->clock_sample = tf_now(); reply->call_count = g_calls;
    reply->payload_size = 0; reply->result_kind = 0; reply->tls_marker = 0;
    ZeroMemory(reply->payload, sizeof(reply->payload));
}
static int tf_valid_payload(const tf_broker_frame *frame) {
    uint32_t expected = 0, index;
    int64_t sum; int32_t a, b; double d; float f; uint32_t boolean;
    if (frame->payload_size > TF_BROKER_PAYLOAD || frame->flags & ~TF_BROKER_HOLD) return 0;
    for (index = frame->payload_size; index < TF_BROKER_PAYLOAD; ++index) if (frame->payload[index]) return 0;
    switch (frame->operation) {
    case TF_OP_CDECL_ADD: case TF_OP_STDCALL_ADD: case TF_OP_WAIT_ADD:
        expected = 8; memcpy(&a, frame->payload, 4); memcpy(&b, frame->payload + 4, 4);
        sum = (int64_t)a + b; if (sum < INT32_MIN || sum > INT32_MAX) return 0; break;
    case TF_OP_WIDE: expected = 8; break;
    case TF_OP_MIXED:
        expected = 24; memcpy(&d, frame->payload + 4, 8); memcpy(&f, frame->payload + 16, 4);
        if (!_finite(d) || !_finite((double)f) || fabs(d) > 1e20 || fabs((double)f) > 1e20) return 0; break;
    case TF_OP_ECHO: return !(frame->payload_size & 1u);
    case TF_OP_MAIN_BOOL: case TF_OP_WRONG_AFFINITY:
        expected = 4; memcpy(&boolean, frame->payload, 4); if (boolean > 1u) return 0; break;
    default: return 0;
    }
    return frame->payload_size == expected;
}
static void tf_finish(tf_slot *slot, uint32_t status, uint32_t error, tf_broker_frame *result, int main) {
    AcquireSRWLockExclusive(&g_lock);
    result->status = status; result->error = error; result->call_count = g_calls;
    result->clock_sample = tf_now(); result->flags |= TF_BROKER_TLS_CLEARED;
    slot->result = *result;
    slot->main_returned = main;
    InterlockedExchange(&slot->state, (LONG)status);
    ReleaseSRWLockExclusive(&g_lock);
}
static void tf_execute(tf_slot *slot, int main) {
    tf_broker_frame result;
    uint32_t error;
    AcquireSRWLockShared(&g_lock);
    tf_response(&slot->request, &result, TF_RUNNING, 0);
    ReleaseSRWLockShared(&g_lock);
    result.thread_id = GetCurrentThreadId(); result.thread_created = tf_thread_created(GetCurrentThread());
    if (!tf_admitted(&slot->request)) {
        if (InterlockedCompareExchange(&slot->state, TF_CANCELLED, TF_PREPARED) == TF_PREPARED)
            tf_finish(slot, TF_CANCELLED, ERROR_TIMEOUT, &result, main);
        else if (slot->state == TF_CANCELLED) tf_finish(slot, TF_CANCELLED, ERROR_CANCELLED, &result, main);
        return;
    }
    if (InterlockedCompareExchange(&slot->state, TF_RUNNING, TF_PREPARED) != TF_PREPARED) {
        if (slot->state == TF_CANCELLED) tf_finish(slot, TF_CANCELLED, ERROR_CANCELLED, &result, main);
        return;
    }
    /* A second admission check closes a delayed transition before dispatch. */
    if (!tf_admitted(&slot->request)) { tf_finish(slot, TF_REFUSED, ERROR_TIMEOUT, &result, main); return; }
    if (!TlsSetValue(g_tls, (void *)(uintptr_t)slot->request.request_id)) {
        tf_finish(slot, TF_REFUSED, GetLastError(), &result, main); return;
    }
    result.tls_marker = (uint64_t)(uintptr_t)TlsGetValue(g_tls);
    if (slot->request.operation == TF_OP_WRONG_AFFINITY ||
        (slot->request.operation == TF_OP_MAIN_BOOL && GetCurrentThreadId() != g_main_tid)) {
        TlsSetValue(g_tls, NULL); tf_finish(slot, TF_REFUSED, ERROR_INVALID_THREAD_ID, &result, main); return;
    }
    AcquireSRWLockExclusive(&g_lock); ++g_calls; ReleaseSRWLockExclusive(&g_lock);
    error = g_dispatch(&slot->request, &result, slot->release, g_owner, g_main_tid);
    if (!TlsSetValue(g_tls, NULL)) { tf_finish(slot, TF_UNKNOWN, GetLastError(), &result, main); return; }
    tf_finish(slot, error ? TF_REFUSED : TF_DONE, error, &result, main);
}
static DWORD WINAPI tf_worker(void *opaque) {
    tf_slot *slot = (tf_slot *)opaque;
    HANDLE waits[2] = {slot->start_gate, g_owner};
    while (slot->state == TF_PREPARED && tf_admitted(&slot->request)) {
        DWORD observed = WaitForMultipleObjects(2, waits, FALSE, 10);
        if (observed == WAIT_OBJECT_0) break;
        if (observed != WAIT_TIMEOUT) break;
    }
    tf_execute(slot, 0);
    return 0;
}
static tf_slot *tf_find(uint64_t id) {
    uint32_t index;
    for (index = 0; index < g_count; ++index) if (g_slots[index].request.request_id == id) return &g_slots[index];
    return NULL;
}
static void tf_observe(tf_slot *slot, const tf_broker_frame *request, tf_broker_frame *reply) {
    LONG status = slot->state;
    *reply = slot->result;
    reply->command = request->command;
    reply->clock_sample = tf_now(); reply->call_count = g_calls;
    reply->status = (uint32_t)status;
    if (status == TF_DONE || status == TF_CANCELLED || status == TF_REFUSED || status == TF_UNKNOWN) {
        if (slot->thread && WaitForSingleObject(slot->thread, 0) == WAIT_OBJECT_0) reply->flags |= TF_BROKER_WORKER_COMPLETE;
        else if (slot->main_returned) reply->flags |= TF_BROKER_MAIN_COMPLETE;
        else reply->status = TF_RUNNING;
    }
}
static void tf_handle(const tf_broker_frame *request, tf_broker_frame *reply) {
    tf_slot *slot; uint32_t index; uint64_t now;
    AcquireSRWLockExclusive(&g_lock);
    tf_response(request, reply, TF_REFUSED, ERROR_INVALID_DATA);
    if (memcmp(request->magic, "TFB1", 4) || request->version != TF_BROKER_VERSION || request->size != sizeof(*request) ||
        request->status || request->generation != 1 || request->owner_pid != g_owner_pid ||
        request->owner_created != g_owner_created || request->target_pid != g_target_pid ||
        request->target_created != g_target_created || memcmp(request->nonce, g_nonce, 16) || !tf_owner_alive()) goto leave;
    if (request->command == TF_CMD_HELLO && !request->request_id && !request->payload_size) {
        reply->status = TF_READY; reply->error = 0; goto leave;
    }
    if (request->qpc_frequency != g_frequency) goto leave;
    slot = tf_find(request->request_id);
    if (request->command == TF_CMD_SUBMIT) {
        now = tf_now();
        if (slot || g_count >= TF_BROKER_MAX_REQUESTS || request->request_id != (uint64_t)g_count + 1 ||
            !tf_valid_payload(request) || !now || request->deadline_qpc <= now ||
            request->deadline_qpc - now > g_frequency * 30u) goto leave;
        for (index = 0; index < g_count; ++index) {
            LONG state = g_slots[index].state;
            if (state == TF_PREPARED || state == TF_RUNNING || state == TF_UNKNOWN ||
                (g_slots[index].thread && WaitForSingleObject(g_slots[index].thread, 0) != WAIT_OBJECT_0)) goto leave;
        }
        slot = &g_slots[g_count]; slot->request = *request;
        tf_response(request, &slot->result, TF_PREPARED, 0);
        slot->start_gate = CreateEventW(NULL, TRUE, !(request->flags & TF_BROKER_HOLD), NULL);
        slot->release = CreateEventW(NULL, TRUE, FALSE, NULL);
        if (!slot->start_gate || !slot->release) { reply->error = GetLastError(); goto leave; }
        InterlockedExchange(&slot->state, TF_PREPARED); ++g_count;
        if (request->operation != TF_OP_MAIN_BOOL) {
            slot->thread = CreateThread(NULL, 0, tf_worker, slot, 0, NULL);
            if (!slot->thread) { InterlockedExchange(&slot->state, TF_UNKNOWN); reply->status = TF_UNKNOWN; reply->error = GetLastError(); goto leave; }
        }
        tf_observe(slot, request, reply); goto leave;
    }
    if (!slot || request->payload_size || request->operation != slot->request.operation || request->flags ||
        request->deadline_qpc != slot->request.deadline_qpc) goto leave;
    if (request->command == TF_CMD_CANCEL) {
        InterlockedCompareExchange(&slot->state, TF_CANCELLED, TF_PREPARED);
        SetEvent(slot->start_gate);
    } else if (request->command == TF_CMD_RELEASE) {
        SetEvent(slot->start_gate); SetEvent(slot->release);
    } else if (request->command != TF_CMD_QUERY) goto leave;
    tf_observe(slot, request, reply);
leave:
    ReleaseSRWLockExclusive(&g_lock);
}
static int tf_io(HANDLE pipe, int write, void *buffer, DWORD size) {
    tf_io_storage *storage; DWORD done = 0, error, wait;
    BOOL okay, pending = FALSE;
    if (size > sizeof(tf_broker_frame) || g_io_uncertain) return 0;
    storage = (tf_io_storage *)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, sizeof(*storage)); if (!storage) return 0;
    storage->overlap.hEvent = CreateEventW(NULL, TRUE, FALSE, NULL);
    if (!storage->overlap.hEvent) { HeapFree(GetProcessHeap(), 0, storage); return 0; }
    if (write) memcpy(storage->bytes, buffer, size);
    okay = write ? WriteFile(pipe, storage->bytes, size, &done, &storage->overlap) : ReadFile(pipe, storage->bytes, size, &done, &storage->overlap);
    if (!okay) {
        error = GetLastError();
        if (error == ERROR_IO_PENDING) {
            pending = TRUE; wait = WaitForSingleObject(storage->overlap.hEvent, 1000);
            if (wait != WAIT_OBJECT_0) { CancelIoEx(pipe, &storage->overlap); wait = WaitForSingleObject(storage->overlap.hEvent, 1000); }
            if (wait == WAIT_OBJECT_0) {
                okay = GetOverlappedResult(pipe, &storage->overlap, &done, FALSE);
                error = okay ? 0 : GetLastError();
                if (error != ERROR_IO_INCOMPLETE && error != ERROR_IO_PENDING && error != ERROR_INVALID_HANDLE) pending = FALSE;
            }
        }
    }
    if (pending) {
        /* Server stops permanently; no unload or retry can free this object. */
        g_retained_io = storage; g_retained_pipe = pipe; InterlockedExchange(&g_io_uncertain, 1); return 0;
    }
    if (okay && done == size && !write) memcpy(buffer, storage->bytes, size);
    CloseHandle(storage->overlap.hEvent); HeapFree(GetProcessHeap(), 0, storage);
    return okay && done == size;
}
static DWORD WINAPI tf_server(void *unused) {
    HANDLE pipe; SECURITY_ATTRIBUTES attributes; tf_io_storage *connection; DWORD pid, ignored, wait, error;
    tf_broker_frame request, reply; BOOL connected; (void)unused;
    attributes.nLength = sizeof(attributes); attributes.lpSecurityDescriptor = g_security; attributes.bInheritHandle = FALSE;
    pipe = CreateNamedPipeW(g_pipe, PIPE_ACCESS_DUPLEX | FILE_FLAG_OVERLAPPED | FILE_FLAG_FIRST_PIPE_INSTANCE,
        PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT | PIPE_REJECT_REMOTE_CLIENTS,
        1, sizeof(reply), sizeof(request), 0, &attributes);
    if (pipe == INVALID_HANDLE_VALUE) return GetLastError();
    while (tf_owner_alive() && !g_io_uncertain) {
        connection = (tf_io_storage *)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, sizeof(*connection)); if (!connection) break;
        connection->overlap.hEvent = CreateEventW(NULL, TRUE, FALSE, NULL);
        if (!connection->overlap.hEvent) { HeapFree(GetProcessHeap(), 0, connection); break; }
        connected = ConnectNamedPipe(pipe, &connection->overlap);
        if (!connected && GetLastError() == ERROR_PIPE_CONNECTED) connected = TRUE;
        else if (!connected && GetLastError() == ERROR_IO_PENDING) {
            do { wait = WaitForSingleObject(connection->overlap.hEvent, 100); } while (tf_owner_alive() && wait == WAIT_TIMEOUT);
            if (wait != WAIT_OBJECT_0) { CancelIoEx(pipe, &connection->overlap); wait = WaitForSingleObject(connection->overlap.hEvent, 1000); }
            error = ERROR_IO_INCOMPLETE;
            if (wait == WAIT_OBJECT_0) {
                connected = GetOverlappedResult(pipe, &connection->overlap, &ignored, FALSE);
                error = connected ? 0 : GetLastError();
            }
            if (error == ERROR_IO_INCOMPLETE || error == ERROR_IO_PENDING || error == ERROR_INVALID_HANDLE) {
                g_retained_io = connection; g_retained_pipe = pipe; InterlockedExchange(&g_io_uncertain, 1); break;
            }
        }
        CloseHandle(connection->overlap.hEvent); HeapFree(GetProcessHeap(), 0, connection);
        if (!connected) break;
        if (GetNamedPipeClientProcessId(pipe, &pid) && pid == g_owner_pid && tf_owner_alive() &&
            tf_io(pipe, 0, &request, sizeof(request))) {
            tf_handle(&request, &reply);
            if (tf_io(pipe, 1, &reply, sizeof(reply))) {
                /* Disconnect discards unread pipe bytes. Keep this connection
                 * alive until client close (after its read) or a bounded drain.
                 * A dropped ACK never waits on unbounded FlushFileBuffers. */
                tf_io(pipe, 0, &request, sizeof(request));
            }
        }
        if (!g_io_uncertain) DisconnectNamedPipe(pipe);
    }
    /* Owner loss permits cancellation before start only. Running code is never terminated. */
    AcquireSRWLockExclusive(&g_lock);
    for (pid = 0; pid < g_count; ++pid) {
        InterlockedCompareExchange(&g_slots[pid].state, TF_CANCELLED, TF_PREPARED);
        SetEvent(g_slots[pid].start_gate);
    }
    ReleaseSRWLockExclusive(&g_lock);
    if (!g_io_uncertain) CloseHandle(pipe);
    return 0;
}
static int tf_make_security(void) {
    HANDLE token = NULL; DWORD size = 0; TOKEN_USER *user = NULL; LPWSTR sid = NULL; WCHAR sddl[256]; int okay = 0;
    if (!OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &token)) return 0;
    GetTokenInformation(token, TokenUser, NULL, 0, &size);
    if (!size || size > 65536) goto done;
    user = (TOKEN_USER *)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, size); if (!user) goto done;
    if (!GetTokenInformation(token, TokenUser, user, size, &size) || !ConvertSidToStringSidW(user->User.Sid, &sid)) goto done;
    if (swprintf_s(sddl, 256, L"D:P(A;;GA;;;%s)", sid) < 0) goto done;
    okay = ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, SDDL_REVISION_1, &g_security, NULL) != FALSE;
done:
    if (sid) LocalFree(sid); if (user) HeapFree(GetProcessHeap(), 0, user); if (token) CloseHandle(token);
    return okay;
}
int __cdecl TFBrokerStart(uint32_t owner, uint64_t created, const uint8_t nonce[16], tf_broker_dispatch_fn dispatch) {
    LARGE_INTEGER frequency; WCHAR hex[33]; uint32_t index;
    if (!owner || !created || !nonce || !dispatch || InterlockedCompareExchange(&g_initialized, 1, 0)) return 0;
    if (!QueryPerformanceFrequency(&frequency) || frequency.QuadPart <= 0 || frequency.QuadPart > INT64_MAX / 30) return 0;
    g_owner = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, FALSE, owner);
    if (!g_owner || tf_process_created(g_owner) != created || WaitForSingleObject(g_owner, 0) != WAIT_TIMEOUT) return 0;
    g_owner_pid = owner; g_owner_created = created; g_target_pid = GetCurrentProcessId();
    g_target_created = tf_process_created(GetCurrentProcess()); g_main_tid = GetCurrentThreadId();
    g_main_created = tf_thread_created(GetCurrentThread()); g_frequency = (uint64_t)frequency.QuadPart;
    if (!g_target_created || !g_main_created || !tf_make_security()) return 0;
    memcpy(g_nonce, nonce, 16); g_dispatch = dispatch; g_tls = TlsAlloc(); if (g_tls == TLS_OUT_OF_INDEXES) return 0;
    for (index = 0; index < 16; ++index) swprintf_s(hex + index * 2, 33 - index * 2, L"%02x", nonce[index]);
    if (swprintf_s(g_pipe, 128, L"\\\\.\\pipe\\CT2TrainerOwnedBroker-%lu-%s", (unsigned long)g_target_pid, hex) < 0) return 0;
    g_server = CreateThread(NULL, 0, tf_server, NULL, 0, NULL);
    return g_server != NULL;
}
void __cdecl TFBrokerPumpMain(void) {
    tf_slot *slot = NULL; uint32_t index;
    if (GetCurrentThreadId() != g_main_tid || tf_thread_created(GetCurrentThread()) != g_main_created) return;
    AcquireSRWLockShared(&g_lock);
    for (index = 0; index < g_count; ++index) {
        if (g_slots[index].request.operation == TF_OP_MAIN_BOOL &&
            (g_slots[index].state == TF_PREPARED || g_slots[index].state == TF_CANCELLED) && !g_slots[index].main_returned &&
            (WaitForSingleObject(g_slots[index].start_gate, 0) == WAIT_OBJECT_0 || !tf_admitted(&g_slots[index].request))) {
            slot = &g_slots[index]; break;
        }
    }
    ReleaseSRWLockShared(&g_lock);
    if (slot) tf_execute(slot, 1);
}
int __cdecl TFBrokerInspect(tf_broker_stats *stats) {
    uint32_t index;
    if (!stats || GetCurrentThreadId() != g_main_tid || tf_thread_created(GetCurrentThread()) != g_main_created) return 0;
    ZeroMemory(stats, sizeof(*stats)); stats->version = 1; stats->size = sizeof(*stats);
    AcquireSRWLockShared(&g_lock);
    stats->requests = g_count; stats->calls = g_calls; stats->owner_alive = (uint32_t)tf_owner_alive();
    stats->pointer_bits = (uint32_t)(sizeof(void *) * 8u);
    for (index = 0; index < g_count; ++index) {
        if (g_slots[index].state == TF_CANCELLED) ++stats->cancelled;
        if (g_slots[index].thread) {
            ++stats->worker_handles;
            if (WaitForSingleObject(g_slots[index].thread, 0) != WAIT_OBJECT_0) ++stats->live_workers;
        }
    }
    ReleaseSRWLockShared(&g_lock);
    return 1;
}
BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID reserved) {
    (void)instance; (void)reason; (void)reserved; return TRUE;
}
