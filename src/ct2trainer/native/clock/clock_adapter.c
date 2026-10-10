/* Independently authored local adapter. No hook installation or injection.
 * MIT: licenses/CT2Trainer-MIT.txt. */
#define TF_CLOCK_ADAPTER_BUILD
#include "clock_adapter.h"
#include <string.h>
#include <limits.h>

/* Stable undecorated names on x86 as well as x64. */
#if defined(_M_IX86)
#pragma comment(linker, "/EXPORT:TFClockInitialize=_TFClockInitialize@4")
#pragma comment(linker, "/EXPORT:TFClockGetInfo=_TFClockGetInfo@4")
#pragma comment(linker, "/EXPORT:TFClockSubmit=_TFClockSubmit@4")
#pragma comment(linker, "/EXPORT:TFClockTakeAcknowledgement=_TFClockTakeAcknowledgement@4")
#pragma comment(linker, "/EXPORT:TFClockCancel=_TFClockCancel@12")
#pragma comment(linker, "/EXPORT:TFClockGetFenceStatus=_TFClockGetFenceStatus@4")
#pragma comment(linker, "/EXPORT:TFClockReadRawCounter=_TFClockReadRawCounter@4")
#ifdef TF_CLOCK_ADAPTER_TESTING
#pragma comment(linker, "/EXPORT:TFClockFixtureInjectFault=_TFClockFixtureInjectFault@4")
#endif
#pragma comment(linker, "/EXPORT:TFQueryPerformanceCounter=_TFQueryPerformanceCounter@4")
#pragma comment(linker, "/EXPORT:TFGetTickCount=_TFGetTickCount@0")
#pragma comment(linker, "/EXPORT:TFGetTickCount64=_TFGetTickCount64@0")
#pragma comment(linker, "/EXPORT:TFtimeGetTime=_TFtimeGetTime@0")
#endif

enum { SLOT_EMPTY, SLOT_WRITING, SLOT_READY, SLOT_BUSY, SLOT_ACK, SLOT_READING_ACK };
static volatile LONG initialized;
static volatile LONG slot_state;
static volatile LONG adapter_fault;
static volatile LONG published_core_fault;
static volatile LONG platform_error;
static DWORD clock_error;
__declspec(align(8)) static volatile LONG64 owner_fence;
__declspec(align(8)) static volatile LONG64 retired_fence;
static SRWLOCK adapter_lock = SRWLOCK_INIT;
static DWORD tls_index = TLS_OUT_OF_INDEXES;
static tf_clock clock_state;
static tf_clock_originals originals;
static tf_clock_adapter_info adapter_info;
static tf_clock_command mailbox_command;
static tf_clock_acknowledgement mailbox_ack;
static uint64_t last_sequence;

static int ready(void)
{
    return InterlockedCompareExchange(&initialized, 2, 2) == 2;
}

static int sample_original(uint64_t *out, DWORD *error)
{
    LARGE_INTEGER value;
    DWORD saved_error = GetLastError();
    BOOL ok;
    SetLastError(ERROR_SUCCESS);
    ok = originals.qpc(&value);
    *error = GetLastError();
    SetLastError(saved_error);
    if (!ok) { if (*error == ERROR_SUCCESS) *error = ERROR_GEN_FAILURE; return 0; }
    if (value.QuadPart < 0) { *error = ERROR_INVALID_DATA; return 0; }
    *error = ERROR_SUCCESS;
    *out = (uint64_t)value.QuadPart;
    return 1;
}

static int raw_sample(void *ignored, uint64_t *out)
{
    (void)ignored;
    return sample_original(out, &clock_error);
}

static uint64_t fence_read(void)
{
    return (uint64_t)InterlockedCompareExchange64(&owner_fence, 0, 0);
}

static tf_clock_adapter_status fence_owner(uint64_t owner)
{
    unsigned int attempt;
    uint64_t previous;
    for (attempt = 0; attempt < 16; ++attempt) {
        previous = fence_read();
        if (previous >= owner) return TF_CLOCK_ADAPTER_OK;
        if ((uint64_t)InterlockedCompareExchange64(&owner_fence, (LONG64)owner, (LONG64)previous) == previous)
            return TF_CLOCK_ADAPTER_OK;
    }
    return TF_CLOCK_ADAPTER_BUSY;
}

static void make_ack(tf_clock_acknowledgement *ack, const tf_clock_command *command,
                     uint32_t disposition, tf_clock_status status)
{
    ZeroMemory(ack, sizeof(*ack));
    ack->size = sizeof(*ack); ack->version = TF_CLOCK_ADAPTER_VERSION;
    ack->sequence = command->sequence; ack->owner = command->owner;
    ack->operation = command->operation; ack->disposition = disposition;
    ack->clock_status = status;
}

static int pin_address(uintptr_t address)
{
    HMODULE module;
    return GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_PIN,
                              (LPCWSTR)address, &module) != 0;
}

static int resolve_originals(tf_clock_originals *out, HMODULE *multimedia)
{
    HMODULE kernel = GetModuleHandleW(L"kernel32.dll");
    FARPROC procedure;
    if (!kernel) return 0;
    /* Function-pointer bytes are copied because their Windows representation is
     * identical, avoiding incompatible-prototype casts under /W4 /WX. */
    procedure = GetProcAddress(kernel, "QueryPerformanceCounter");
    memcpy(&out->qpc, &procedure, sizeof(procedure));
    procedure = GetProcAddress(kernel, "QueryPerformanceFrequency");
    memcpy(&out->frequency, &procedure, sizeof(procedure));
    procedure = GetProcAddress(kernel, "GetTickCount");
    memcpy(&out->tick32, &procedure, sizeof(procedure));
    procedure = GetProcAddress(kernel, "GetTickCount64");
    memcpy(&out->tick64, &procedure, sizeof(procedure));
    *multimedia = LoadLibraryExW(L"winmm.dll", NULL, LOAD_LIBRARY_SEARCH_SYSTEM32);
    if (!*multimedia) return 0;
    procedure = GetProcAddress(*multimedia, "timeGetTime");
    memcpy(&out->multimedia32, &procedure, sizeof(procedure));
    return out->qpc && out->frequency && out->tick32 && out->tick64 && out->multimedia32;
}

static tf_clock_adapter_status initialize_impl(const tf_clock_adapter_options *options)
{
    uint32_t calibration_us = TF_CLOCK_CALIBRATION_US_DEFAULT;
    uint64_t limit, before, after, end;
    LARGE_INTEGER frequency;
    tf_clock_config config;
    tf_clock_adapter_info info;
    HMODULE multimedia = NULL;
    DWORD new_tls = TLS_OUT_OF_INDEXES;
    tf_clock_adapter_status status = TF_CLOCK_ADAPTER_PLATFORM_FAILED;
    tf_clock_originals selected;
    uintptr_t providers[5] = {0, 0, 0, 0, 0};
    int supplied = 0;
    ZeroMemory(&selected, sizeof(selected));
    if (options) {
        if (options->size != sizeof(*options) || options->version != TF_CLOCK_ADAPTER_VERSION ||
            options->reserved != 0 || options->maximum_calibration_microseconds == 0 ||
            options->maximum_calibration_microseconds > TF_CLOCK_CALIBRATION_US_MAX)
            return TF_CLOCK_ADAPTER_BAD_INPUT;
        calibration_us = options->maximum_calibration_microseconds;
        selected = options->originals;
        memcpy(providers, options->provider_addresses, sizeof(providers));
        supplied = selected.qpc || selected.frequency || selected.tick32 || selected.tick64 || selected.multimedia32;
        if (supplied && !(selected.qpc && selected.frequency && selected.tick32 && selected.tick64 && selected.multimedia32))
            return TF_CLOCK_ADAPTER_BAD_INPUT;
        if (!supplied && (providers[0] || providers[1] || providers[2] || providers[3] || providers[4]))
            return TF_CLOCK_ADAPTER_BAD_INPUT;
    }
    if (InterlockedCompareExchange(&initialized, 1, 0) != 0)
        return ready() ? TF_CLOCK_ADAPTER_ALREADY_INITIALIZED : TF_CLOCK_ADAPTER_BUSY;
    if (!supplied && !resolve_originals(&selected, &multimedia)) goto failed;
    originals = selected;
    if (!originals.frequency(&frequency) || frequency.QuadPart <= 0) goto failed;
    limit = ((uint64_t)frequency.QuadPart / 1000000u) * calibration_us +
            (((uint64_t)frequency.QuadPart % 1000000u) * calibration_us) / 1000000u;
    if (limit == 0) limit = 1; /* Minimum representable QPC uncertainty. */
    ZeroMemory(&config, sizeof(config));
    ZeroMemory(&info, sizeof(info));
    config.frequency = info.frequency = (uint64_t)frequency.QuadPart;
    if (!raw_sample(NULL, &config.qpc_origin) || !raw_sample(NULL, &before)) goto failed;
    config.tick64_origin = originals.tick64();
    if (!raw_sample(NULL, &after) || after < before) goto calibration_failed;
    info.tick_capture_window = after - before;
    config.tick64_capture_qpc = before + (after - before)/2;
    if (!raw_sample(NULL, &before)) goto failed;
    config.multimedia_origin = originals.multimedia32();
    if (!raw_sample(NULL, &after) || after < before) goto calibration_failed;
    info.multimedia_capture_window = after - before;
    config.multimedia_capture_qpc = before + (after - before)/2;
    if (!raw_sample(NULL, &end) || end < config.qpc_origin) goto calibration_failed;
    info.observed_calibration_ticks = end - config.qpc_origin;
    if (info.tick_capture_window > limit || info.multimedia_capture_window > limit ||
        info.observed_calibration_ticks > limit) goto calibration_failed;
    config.initial_raw_qpc = end;
    config.raw_counter = raw_sample;
    if (tf_clock_initialize(&clock_state, &config) != TF_CLOCK_OK) goto calibration_failed;
    new_tls = TlsAlloc();
    if (new_tls == TLS_OUT_OF_INDEXES) goto failed;
    /* Never unpin/remove these paths while the process lives. Partial pinning on
     * a platform failure is also retained; no unsafe compensation by unloading. */
    if (!pin_address(providers[0] ? providers[0] : (uintptr_t)originals.qpc) ||
        !pin_address(providers[1] ? providers[1] : (uintptr_t)originals.frequency) ||
        !pin_address(providers[2] ? providers[2] : (uintptr_t)originals.tick32) ||
        !pin_address(providers[3] ? providers[3] : (uintptr_t)originals.tick64) ||
        !pin_address(providers[4] ? providers[4] : (uintptr_t)originals.multimedia32) ||
        !pin_address((uintptr_t)&TFClockInitialize)) goto failed;
    info.size = sizeof(info);
    info.version = TF_CLOCK_ADAPTER_VERSION;
    info.maximum_calibration_ticks = limit;
    info.command_size = sizeof(tf_clock_command);
    info.acknowledgement_size = sizeof(tf_clock_acknowledgement);
    adapter_info = info;
    tls_index = new_tls;
    if (multimedia) FreeLibrary(multimedia); /* Provider is already permanently pinned. */
    InterlockedExchange(&initialized, 2);
    return TF_CLOCK_ADAPTER_OK;
calibration_failed:
    status = TF_CLOCK_ADAPTER_CALIBRATION_FAILED;
failed:
    if (new_tls != TLS_OUT_OF_INDEXES) TlsFree(new_tls);
    if (multimedia) FreeLibrary(multimedia);
    ZeroMemory(&originals, sizeof(originals));
    InterlockedExchange(&initialized, 0);
    return status;
}

tf_clock_adapter_status WINAPI TFClockInitialize(const tf_clock_adapter_options *options)
{
    DWORD saved_error = GetLastError();
    tf_clock_adapter_status status = initialize_impl(options);
    SetLastError(saved_error);
    return status;
}

tf_clock_adapter_status WINAPI TFClockGetInfo(tf_clock_adapter_info *info)
{
    DWORD saved_error = GetLastError();
    tf_clock_adapter_status status = TF_CLOCK_ADAPTER_OK;
    if (!info) status = TF_CLOCK_ADAPTER_BAD_INPUT;
    else if (!ready()) status = TF_CLOCK_ADAPTER_NOT_INITIALIZED;
    else *info = adapter_info; /* Immutable after release publication of initialized. */
    SetLastError(saved_error);
    return status;
}

static tf_clock_adapter_status submit_impl(const tf_clock_command *command)
{
    tf_clock_command copied;
    uint64_t maximum, now;
    LARGE_INTEGER counter;
    if (!command) return TF_CLOCK_ADAPTER_BAD_INPUT;
    if (!ready()) return TF_CLOCK_ADAPTER_NOT_INITIALIZED;
    if (InterlockedCompareExchange(&adapter_fault, 0, 0) || InterlockedCompareExchange(&published_core_fault, 0, 0))
        return TF_CLOCK_ADAPTER_CLOCK_FAULT;
    copied = *command;
    maximum = adapter_info.frequency > UINT64_MAX / TF_CLOCK_LEASE_SECONDS_MAX
        ? UINT64_MAX : adapter_info.frequency * TF_CLOCK_LEASE_SECONDS_MAX;
    if (copied.size != sizeof(copied) || copied.version != TF_CLOCK_ADAPTER_VERSION ||
        copied.sequence == 0 || copied.owner == 0 || copied.owner > (uint64_t)INT64_MAX || copied.operation < TF_CLOCK_COMMAND_SET_RATE ||
        copied.operation > TF_CLOCK_COMMAND_CLOSE ||
        (copied.operation == TF_CLOCK_COMMAND_SET_RATE && copied.rate_ppm > TF_CLOCK_RATE_MAX) ||
        (copied.operation != TF_CLOCK_COMMAND_SET_RATE && copied.rate_ppm != 0) ||
        copied.not_after_qpc > (uint64_t)INT64_MAX || copied.lease_deadline_qpc > (uint64_t)INT64_MAX ||
        (copied.operation == TF_CLOCK_COMMAND_CLOSE && copied.lease_deadline_qpc != 0) ||
        (copied.operation != TF_CLOCK_COMMAND_CLOSE && copied.lease_deadline_qpc < copied.not_after_qpc))
        return TF_CLOCK_ADAPTER_BAD_INPUT;
    if (copied.owner <= fence_read() && copied.operation != TF_CLOCK_COMMAND_CLOSE) return TF_CLOCK_ADAPTER_FENCED_OWNER;
    if (!TFClockReadRawCounter(&counter)) return TF_CLOCK_ADAPTER_CLOCK_FAULT;
    now = (uint64_t)counter.QuadPart;
    if (copied.not_after_qpc <= now) return TF_CLOCK_ADAPTER_EXPIRED;
    if (copied.not_after_qpc - now > adapter_info.frequency * TF_CLOCK_PENDING_SECONDS_MAX ||
        (copied.operation != TF_CLOCK_COMMAND_CLOSE && (copied.lease_deadline_qpc <= now || copied.lease_deadline_qpc - now > maximum)))
        return TF_CLOCK_ADAPTER_BAD_INPUT;
    if (InterlockedCompareExchange(&slot_state, SLOT_WRITING, SLOT_EMPTY) != SLOT_EMPTY)
        return TF_CLOCK_ADAPTER_BUSY;
    if (copied.sequence <= last_sequence) {
        InterlockedExchange(&slot_state, SLOT_EMPTY);
        return TF_CLOCK_ADAPTER_STALE_SEQUENCE;
    }
    mailbox_command = copied;
    last_sequence = copied.sequence;
    if (copied.operation == TF_CLOCK_COMMAND_CLOSE) (void)fence_owner(copied.owner);
    if (copied.owner <= fence_read() && copied.operation != TF_CLOCK_COMMAND_CLOSE) {
        make_ack(&mailbox_ack, &copied, TF_CLOCK_ACK_CANCELLED_PENDING, TF_CLOCK_STALE_OWNER);
        InterlockedExchange(&slot_state, SLOT_ACK);
        return TF_CLOCK_ADAPTER_OK;
    }
    /* Interlocked release/acquire publication prevents torn 64-bit x86 data;
     * fields have one writer and cannot change before the consumer takes them. */
    InterlockedExchange(&slot_state, SLOT_READY);
    return TF_CLOCK_ADAPTER_OK;
}

tf_clock_adapter_status WINAPI TFClockCancel(uint64_t owner, tf_clock_cancel_result *result)
{
    DWORD saved_error = GetLastError();
    tf_clock_adapter_status status;
    tf_clock_cancel_result copied;
    if (!result || owner == 0 || owner > (uint64_t)INT64_MAX) status = TF_CLOCK_ADAPTER_BAD_INPUT;
    else if (!ready()) status = TF_CLOCK_ADAPTER_NOT_INITIALIZED;
    else {
        ZeroMemory(&copied, sizeof(copied)); copied.size = sizeof(copied); copied.version = TF_CLOCK_ADAPTER_VERSION;
        status = fence_owner(owner);
        copied.fenced_through_owner = fence_read();
        if (status == TF_CLOCK_ADAPTER_OK && InterlockedCompareExchange(&slot_state, SLOT_BUSY, SLOT_READY) == SLOT_READY) {
            if (mailbox_command.owner <= copied.fenced_through_owner) {
                make_ack(&mailbox_ack, &mailbox_command, TF_CLOCK_ACK_CANCELLED_PENDING, TF_CLOCK_STALE_OWNER);
                copied.drained_sequence = mailbox_command.sequence;
                InterlockedExchange(&slot_state, SLOT_ACK);
            } else InterlockedExchange(&slot_state, SLOT_READY);
        }
        *result = copied;
    }
    SetLastError(saved_error);
    return status;
}

tf_clock_adapter_status WINAPI TFClockGetFenceStatus(tf_clock_fence_status *status)
{
    DWORD saved_error = GetLastError();
    tf_clock_adapter_status result = TF_CLOCK_ADAPTER_OK;
    if (!status) result = TF_CLOCK_ADAPTER_BAD_INPUT;
    else if (!ready()) result = TF_CLOCK_ADAPTER_NOT_INITIALIZED;
    else {
        status->size = sizeof(*status); status->version = TF_CLOCK_ADAPTER_VERSION;
        /* Read retirement first: both counters only increase, and publication
         * always has retired<=fenced. Reversed loads could mix old fence with
         * newer retirement under concurrent wrappers/cancellation. */
        status->retired_through_owner = (uint64_t)InterlockedCompareExchange64(&retired_fence, 0, 0);
        status->fenced_through_owner = fence_read();
    }
    SetLastError(saved_error); return result;
}

BOOL WINAPI TFClockReadRawCounter(LARGE_INTEGER *counter)
{
    DWORD saved_error = GetLastError(), error = ERROR_SUCCESS;
    uint64_t value;
    int entered = 0, ok;
    if (!counter) { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
    if (!ready()) { SetLastError(ERROR_NOT_READY); return FALSE; }
    if (!TlsGetValue(tls_index)) {
        if (!TlsSetValue(tls_index, (LPVOID)(uintptr_t)1)) { SetLastError(ERROR_GEN_FAILURE); return FALSE; }
        entered = 1;
    }
    ok = sample_original(&value, &error);
    if (entered && !TlsSetValue(tls_index, NULL)) { ok = 0; error = ERROR_GEN_FAILURE; }
    if (ok) counter->QuadPart = (LONGLONG)value;
    SetLastError(ok ? saved_error : error);
    return ok;
}

#ifdef TF_CLOCK_ADAPTER_TESTING
void WINAPI TFClockFixtureInjectFault(DWORD error)
{
    InterlockedExchange(&platform_error, (LONG)(error ? error : ERROR_GEN_FAILURE));
    InterlockedExchange(&adapter_fault, TF_CLOCK_ADAPTER_PLATFORM_FAILED);
}
#endif

tf_clock_adapter_status WINAPI TFClockSubmit(const tf_clock_command *command)
{
    DWORD saved_error = GetLastError();
    tf_clock_adapter_status status = submit_impl(command);
    SetLastError(saved_error);
    return status;
}

tf_clock_adapter_status WINAPI TFClockTakeAcknowledgement(tf_clock_acknowledgement *acknowledgement)
{
    DWORD saved_error = GetLastError();
    tf_clock_adapter_status status = TF_CLOCK_ADAPTER_OK;
    tf_clock_acknowledgement copied;
    if (!acknowledgement) status = TF_CLOCK_ADAPTER_BAD_INPUT;
    else if (!ready()) status = TF_CLOCK_ADAPTER_NOT_INITIALIZED;
    else if (InterlockedCompareExchange(&slot_state, SLOT_READING_ACK, SLOT_ACK) != SLOT_ACK)
        status = TF_CLOCK_ADAPTER_BUSY;
    else {
        copied = mailbox_ack;
        InterlockedExchange(&slot_state, SLOT_EMPTY);
        *acknowledgement = copied; /* No synchronization held across caller write. */
    }
    SetLastError(saved_error);
    return status;
}

/* Called only under adapter_lock with reentry bypass established. A command's
 * acknowledgement records the exact applied transition, rather than a later
 * snapshot. Every core operation first expires overdue leases. */
static void retire_fenced_owner(void)
{
    uint64_t fence = fence_read();
    tf_clock_snapshot snapshot;
    tf_clock_status status = TF_CLOCK_OK;
    if (clock_state.owner && clock_state.owner <= fence)
        status = tf_clock_close(&clock_state, clock_state.owner, &snapshot);
    if (clock_state.fault == TF_CLOCK_OK && (status == TF_CLOCK_OK || status == TF_CLOCK_STALE_OWNER))
        InterlockedExchange64(&retired_fence, (LONG64)fence);
}

static void consume_command(void)
{
    tf_clock_command command;
    tf_clock_acknowledgement acknowledgement;
    uint64_t now;
    if (InterlockedCompareExchange(&slot_state, SLOT_BUSY, SLOT_READY) != SLOT_READY) return;
    command = mailbox_command;
    make_ack(&acknowledgement, &command, TF_CLOCK_ACK_TRANSITION, TF_CLOCK_OK);
    if (InterlockedCompareExchange(&adapter_fault, 0, 0)) {
        make_ack(&acknowledgement, &command, TF_CLOCK_ACK_PLATFORM_FAULT, TF_CLOCK_RAW_SAMPLE_FAILED);
        goto publish;
    }
    if (acknowledgement.disposition == TF_CLOCK_ACK_TRANSITION && command.owner <= fence_read() && command.operation != TF_CLOCK_COMMAND_CLOSE) {
        make_ack(&acknowledgement, &command, TF_CLOCK_ACK_CANCELLED_PENDING, TF_CLOCK_STALE_OWNER); goto publish;
    }
    if (!raw_sample(NULL, &now)) {
        make_ack(&acknowledgement, &command, TF_CLOCK_ACK_PLATFORM_FAULT, TF_CLOCK_RAW_SAMPLE_FAILED); goto publish;
    }
    if (now >= command.not_after_qpc || (command.operation != TF_CLOCK_COMMAND_CLOSE && now >= command.lease_deadline_qpc)) {
        (void)fence_owner(command.owner);
        make_ack(&acknowledgement, &command, TF_CLOCK_ACK_EXPIRED, TF_CLOCK_STALE_OWNER); goto publish;
    }
    acknowledgement.snapshot = clock_state.last;
    if (command.operation == TF_CLOCK_COMMAND_SET_RATE)
        acknowledgement.clock_status = tf_clock_set_rate_until(&clock_state, command.owner,
            command.rate_ppm, command.not_after_qpc, command.lease_deadline_qpc, &acknowledgement.snapshot);
    else if (command.operation == TF_CLOCK_COMMAND_RENEW)
        acknowledgement.clock_status = tf_clock_renew_until(&clock_state, command.owner,
            command.not_after_qpc, command.lease_deadline_qpc, &acknowledgement.snapshot);
    else acknowledgement.clock_status = tf_clock_close(&clock_state, command.owner, &acknowledgement.snapshot);
    if (command.operation != TF_CLOCK_COMMAND_CLOSE && acknowledgement.clock_status == TF_CLOCK_BAD_INPUT &&
        clock_state.raw_anchor >= command.not_after_qpc) {
        (void)fence_owner(command.owner);
        acknowledgement.disposition = TF_CLOCK_ACK_EXPIRED;
    }
    retire_fenced_owner();
    if (acknowledgement.disposition == TF_CLOCK_ACK_TRANSITION && command.owner <= fence_read() && command.operation != TF_CLOCK_COMMAND_CLOSE) {
        acknowledgement.disposition = TF_CLOCK_ACK_CANCELLED_AFTER_CONSUMPTION;
        acknowledgement.snapshot = clock_state.last;
    }
    acknowledgement.snapshot_valid = 1;
publish:
    mailbox_ack = acknowledgement;
    InterlockedExchange(&slot_state, SLOT_ACK);
}

static tf_clock_adapter_status snapshot_for_wrapper(tf_clock_snapshot *snapshot)
{
    tf_clock_status status = TF_CLOCK_OK;
    int tls_ok;
    if (!ready()) return TF_CLOCK_ADAPTER_NOT_INITIALIZED;
    if (TlsGetValue(tls_index) != NULL) return TF_CLOCK_ADAPTER_REENTRY;
    tls_ok = TlsSetValue(tls_index, (LPVOID)(uintptr_t)1) != 0;
    if (!tls_ok) InterlockedExchange(&adapter_fault, TF_CLOCK_ADAPTER_PLATFORM_FAILED);
    AcquireSRWLockExclusive(&adapter_lock);
    if (InterlockedCompareExchange(&adapter_fault, 0, 0) != 0) {
        consume_command(); *snapshot = clock_state.last;
    }
    else {
        consume_command();
        retire_fenced_owner();
        status = tf_clock_read(&clock_state, snapshot);
        retire_fenced_owner();
        *snapshot = clock_state.last;
        if (clock_state.fault != TF_CLOCK_OK) InterlockedExchange(&published_core_fault, clock_state.fault);
    }
    ReleaseSRWLockExclusive(&adapter_lock);
    if (tls_ok && !TlsSetValue(tls_index, NULL))
        InterlockedExchange(&adapter_fault, TF_CLOCK_ADAPTER_PLATFORM_FAILED);
    return status == TF_CLOCK_OK && InterlockedCompareExchange(&adapter_fault, 0, 0) == 0
        ? TF_CLOCK_ADAPTER_OK : TF_CLOCK_ADAPTER_CLOCK_FAULT;
}

BOOL WINAPI TFQueryPerformanceCounter(LARGE_INTEGER *counter)
{
    DWORD saved_error = GetLastError();
    tf_clock_snapshot snapshot;
    tf_clock_adapter_status status;
    BOOL result = FALSE;
    DWORD error = ERROR_INVALID_PARAMETER;
    if (counter) {
        status = snapshot_for_wrapper(&snapshot);
        if (status == TF_CLOCK_ADAPTER_REENTRY) {
            SetLastError(ERROR_SUCCESS); result = originals.qpc(counter); error = GetLastError();
            if (!result && !error) error = ERROR_GEN_FAILURE;
        }
        else if (status == TF_CLOCK_ADAPTER_OK || status == TF_CLOCK_ADAPTER_CLOCK_FAULT) {
            counter->QuadPart = (LONGLONG)snapshot.qpc; /* Both locks already released. */
            result = status == TF_CLOCK_ADAPTER_OK;
            if (!result) {
                if (InterlockedCompareExchange(&adapter_fault, 0, 0)) {
                    error = (DWORD)InterlockedCompareExchange(&platform_error, 0, 0);
                    if (!error) error = ERROR_GEN_FAILURE;
                } else error = snapshot.fault == TF_CLOCK_RAW_SAMPLE_FAILED ? clock_error :
                    snapshot.fault == TF_CLOCK_OVERFLOW ? ERROR_ARITHMETIC_OVERFLOW : ERROR_INVALID_DATA;
            }
        }
        else error = ERROR_NOT_READY;
    }
    SetLastError(result ? saved_error : error);
    return result;
}

DWORD WINAPI TFGetTickCount(void)
{
    DWORD saved_error = GetLastError(), result = 0;
    tf_clock_snapshot snapshot;
    tf_clock_adapter_status status = snapshot_for_wrapper(&snapshot);
    if (status == TF_CLOCK_ADAPTER_REENTRY) result = originals.tick32();
    else if (status == TF_CLOCK_ADAPTER_OK || status == TF_CLOCK_ADAPTER_CLOCK_FAULT) result = snapshot.tick32;
    SetLastError(saved_error);
    return result;
}

ULONGLONG WINAPI TFGetTickCount64(void)
{
    DWORD saved_error = GetLastError();
    ULONGLONG result = 0;
    tf_clock_snapshot snapshot;
    tf_clock_adapter_status status = snapshot_for_wrapper(&snapshot);
    if (status == TF_CLOCK_ADAPTER_REENTRY) result = originals.tick64();
    else if (status == TF_CLOCK_ADAPTER_OK || status == TF_CLOCK_ADAPTER_CLOCK_FAULT) result = snapshot.tick64;
    SetLastError(saved_error);
    return result;
}

DWORD WINAPI TFtimeGetTime(void)
{
    DWORD saved_error = GetLastError(), result = 0;
    tf_clock_snapshot snapshot;
    tf_clock_adapter_status status = snapshot_for_wrapper(&snapshot);
    if (status == TF_CLOCK_ADAPTER_REENTRY) result = originals.multimedia32();
    else if (status == TF_CLOCK_ADAPTER_OK || status == TF_CLOCK_ADAPTER_CLOCK_FAULT) result = snapshot.multimedia32;
    SetLastError(saved_error);
    return result;
}

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID reserved)
{
    (void)instance;
    (void)reason;
    (void)reserved;
    /* No initialization under loader lock. Keep notifications available for
     * the static CRT used by the owned local x86/x64 build. */
    return TRUE;
}
