/* Independently authored local clock adapter ABI, v2. Scoped MIT license. */
#ifndef CT2TRAINER_CLOCK_ADAPTER_H
#define CT2TRAINER_CLOCK_ADAPTER_H
#include "clock_core.h"

#ifdef TF_CLOCK_ADAPTER_BUILD
#define TF_CLOCK_EXPORT __declspec(dllexport)
#else
#define TF_CLOCK_EXPORT
#endif

#ifdef __cplusplus
extern "C" {
#endif

#define TF_CLOCK_ADAPTER_VERSION 2u
#define TF_CLOCK_PENDING_SECONDS_MAX 1u
#define TF_CLOCK_CALIBRATION_US_DEFAULT 10000u
#define TF_CLOCK_CALIBRATION_US_MAX 100000u

typedef enum tf_clock_adapter_status {
    TF_CLOCK_ADAPTER_OK = 0,
    TF_CLOCK_ADAPTER_NOT_INITIALIZED = 1,
    TF_CLOCK_ADAPTER_BAD_INPUT = 2,
    TF_CLOCK_ADAPTER_BUSY = 3,
    TF_CLOCK_ADAPTER_STALE_SEQUENCE = 4,
    TF_CLOCK_ADAPTER_CALIBRATION_FAILED = 5,
    TF_CLOCK_ADAPTER_PLATFORM_FAILED = 6,
    TF_CLOCK_ADAPTER_REENTRY = 7,
    TF_CLOCK_ADAPTER_ALREADY_INITIALIZED = 8,
    TF_CLOCK_ADAPTER_CLOCK_FAULT = 9,
    TF_CLOCK_ADAPTER_FENCED_OWNER = 10,
    TF_CLOCK_ADAPTER_EXPIRED = 11
} tf_clock_adapter_status;

typedef BOOL (WINAPI *tf_original_qpc)(LARGE_INTEGER *);
typedef BOOL (WINAPI *tf_original_frequency)(LARGE_INTEGER *);
typedef DWORD (WINAPI *tf_original_tick32)(void);
typedef ULONGLONG (WINAPI *tf_original_tick64)(void);

typedef struct tf_clock_originals {
    tf_original_qpc qpc;
    tf_original_frequency frequency;
    tf_original_tick32 tick32;
    tf_original_tick64 tick64;
    tf_original_tick32 multimedia32;
} tf_clock_originals;

typedef struct tf_clock_adapter_options {
    uint32_t size, version;
    uint32_t maximum_calibration_microseconds, reserved;
    /* All NULL selects system exports. Otherwise all five are required.
     * Trusted original paths must bypass any future detours and remain alive.
     * These are host callbacks, never Lua- or table-supplied function pointers. */
    tf_clock_originals originals;
    /* Optional module-backed actual provider addresses in the same order as
     * originals. Zero means use that callback address. A future relocation
     * backend may supply private trampoline callbacks and actual export
     * providers separately; it must retain those trampolines until process exit
     * and prove their provenance before initialization. This adapter pins the
     * provider modules but neither owns nor validates private machine code. */
    uintptr_t provider_addresses[5];
} tf_clock_adapter_options;

typedef enum tf_clock_command_operation {
    TF_CLOCK_COMMAND_SET_RATE = 1,
    TF_CLOCK_COMMAND_RENEW = 2,
    TF_CLOCK_COMMAND_CLOSE = 3
} tf_clock_command_operation;

/* Default Windows ABI alignment. Same-bitness only; no packed pointer ABI. */
typedef struct tf_clock_command {
    uint32_t size, version;
    uint64_t sequence, owner;
    uint32_t operation, rate_ppm;
    /* Both are absolute original QPC, never scaled. Pending admission is at
     * most one real second; SET/RENEW lease is at most thirty real seconds from
     * submission. A consumed command cannot restart either interval. CLOSE has
     * lease_deadline_qpc=0. Obtain original time with TFClockReadRawCounter. */
    uint64_t not_after_qpc, lease_deadline_qpc;
} tf_clock_command;

typedef enum tf_clock_ack_disposition {
    TF_CLOCK_ACK_TRANSITION = 0,
    TF_CLOCK_ACK_EXPIRED = 1,
    TF_CLOCK_ACK_CANCELLED_PENDING = 2,
    TF_CLOCK_ACK_CANCELLED_AFTER_CONSUMPTION = 3,
    TF_CLOCK_ACK_PLATFORM_FAULT = 4
} tf_clock_ack_disposition;

typedef struct tf_clock_acknowledgement {
    uint32_t size, version;
    uint64_t sequence, owner;
    uint32_t operation;
    tf_clock_status clock_status;
    uint32_t disposition, snapshot_valid;
    tf_clock_snapshot snapshot;
} tf_clock_acknowledgement;

typedef struct tf_clock_fence_status {
    uint32_t size, version;
    uint64_t fenced_through_owner, retired_through_owner;
} tf_clock_fence_status;

typedef struct tf_clock_cancel_result {
    uint32_t size, version;
    uint64_t fenced_through_owner, drained_sequence;
    /* A nonzero drained_sequence proves a READY command was cancelled before
     * consumption. Neither this response nor a snapshot-less cancellation ACK
     * proves that an already applied rate has ceased. Poll FenceStatus for the
     * locally published retirement generation and retain ownership on doubt. */
} tf_clock_cancel_result;

typedef struct tf_clock_adapter_info {
    uint32_t size, version;
    uint64_t frequency;
    uint64_t maximum_calibration_ticks, observed_calibration_ticks;
    uint64_t tick_capture_window, multimedia_capture_window;
    uint32_t command_size, acknowledgement_size;
} tf_clock_adapter_info;

/* Initialize once outside loader lock. On failure it may be retried. Successful
 * initialization permanently pins this adapter and its actual original provider
 * modules until process exit. There is intentionally no unload/teardown API. */
TF_CLOCK_EXPORT tf_clock_adapter_status WINAPI TFClockInitialize(const tf_clock_adapter_options *options);
TF_CLOCK_EXPORT tf_clock_adapter_status WINAPI TFClockGetInfo(tf_clock_adapter_info *info);
/* One outstanding command. Submit is bounded/nonblocking and acquires no clock
 * lock. Nonzero sequence numbers increase for the DLL lifetime; owner generations
 * follow the core's separate monotonic rule. A future wrapper call applies a
 * command and publishes one immutable ACK, consumed by TakeAcknowledgement.
 * Accepted submission alone never confirms that a rate change took effect. */
TF_CLOCK_EXPORT tf_clock_adapter_status WINAPI TFClockSubmit(const tf_clock_command *command);
TF_CLOCK_EXPORT tf_clock_adapter_status WINAPI TFClockTakeAcknowledgement(tf_clock_acknowledgement *acknowledgement);
TF_CLOCK_EXPORT tf_clock_adapter_status WINAPI TFClockCancel(uint64_t owner, tf_clock_cancel_result *result);
/* Nonblocking atomic metadata. Retirement is published only by a local wrapper
 * after it has stopped any live fenced owner. It is not a module-unload proof. */
TF_CLOCK_EXPORT tf_clock_adapter_status WINAPI TFClockGetFenceStatus(tf_clock_fence_status *status);
TF_CLOCK_EXPORT BOOL WINAPI TFClockReadRawCounter(LARGE_INTEGER *counter);
#ifdef TF_CLOCK_ADAPTER_TESTING
/* Owned fixture builds only, never an admitted production control. */
TF_CLOCK_EXPORT void WINAPI TFClockFixtureInjectFault(DWORD error);
#endif
TF_CLOCK_EXPORT BOOL WINAPI TFQueryPerformanceCounter(LARGE_INTEGER *counter);
TF_CLOCK_EXPORT DWORD WINAPI TFGetTickCount(void);
TF_CLOCK_EXPORT ULONGLONG WINAPI TFGetTickCount64(void);
TF_CLOCK_EXPORT DWORD WINAPI TFtimeGetTime(void);

#ifdef __cplusplus
}
#endif
#endif
