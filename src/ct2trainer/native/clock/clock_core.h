/* Independently authored CT2Trainer clock core. MIT: see
 * licenses/CT2Trainer-MIT.txt. No hook installation or DLL loading. */
#ifndef CT2TRAINER_CLOCK_CORE_H
#define CT2TRAINER_CLOCK_CORE_H

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define TF_CLOCK_RATE_ONE 1000000u
#define TF_CLOCK_RATE_MAX 16000000u
#define TF_CLOCK_LEASE_SECONDS_MAX 30u

typedef enum tf_clock_status {
    TF_CLOCK_OK = 0,
    TF_CLOCK_BAD_INPUT = 1,
    TF_CLOCK_RAW_SAMPLE_FAILED = 2,
    TF_CLOCK_REGRESSION = 3,
    TF_CLOCK_OVERFLOW = 4,
    TF_CLOCK_STALE_OWNER = 5,
    TF_CLOCK_OWNER_CONFLICT = 6
} tf_clock_status;

/* This trusted callback must use the original QPC path, must not enter this
 * clock, and must not acquire a lock which depends on this clock's lock. */
typedef int (*tf_clock_raw_counter)(void *context, uint64_t *counter);

typedef struct tf_clock_config {
    uint64_t frequency;
    uint64_t qpc_origin;
    uint64_t initial_raw_qpc;
    uint64_t tick64_origin;
    uint64_t tick64_capture_qpc;
    uint32_t multimedia_origin;
    uint64_t multimedia_capture_qpc;
    tf_clock_raw_counter raw_counter;
    void *raw_context;
} tf_clock_config;

typedef struct tf_clock_snapshot {
    uint64_t qpc;
    uint64_t tick64;
    uint32_t tick32;
    uint32_t multimedia32;
    uint64_t raw_anchor;
    uint64_t owner;
    uint64_t lease_deadline;
    uint32_t rate_ppm;
    tf_clock_status fault;
} tf_clock_snapshot;

/* Storage is public solely to permit stack/static allocation without a heap.
 * After initialize, callers must use the functions below; never edit fields,
 * copy an initialized clock, or reinitialize it while callers exist. */
typedef struct tf_clock {
    SRWLOCK lock;
    tf_clock_config config;
    uint64_t raw_anchor;
    uint64_t virtual_elapsed;
    uint64_t owner;
    uint64_t last_owner;
    uint64_t lease_deadline;
    uint32_t fraction_ppm;
    uint32_t rate_ppm;
    tf_clock_status fault;
    tf_clock_snapshot last;
} tf_clock;

/* No floating point and no intermediate wrap, including on x86. */
tf_clock_status tf_clock_ticks_to_ms(uint64_t ticks, uint64_t frequency,
                                    uint64_t *milliseconds);
tf_clock_status tf_clock_initialize(tf_clock *clock,
                                    const tf_clock_config *config);
tf_clock_status tf_clock_read(tf_clock *clock, tf_clock_snapshot *snapshot);
/* A strictly increasing nonzero owner token claims an unowned clock. Reuse of
 * an expired/closed token is refused. One live owner may change/renew its rate.
 * lease_ticks is original QPC time, positive, at most 30 real seconds. */
tf_clock_status tf_clock_set_rate(tf_clock *clock, uint64_t owner,
                                 uint32_t rate_ppm, uint64_t lease_ticks,
                                 tf_clock_snapshot *snapshot);
tf_clock_status tf_clock_renew(tf_clock *clock, uint64_t owner,
                              uint64_t lease_ticks,
                              tf_clock_snapshot *snapshot);
/* Absolute original-QPC deadlines never start a new consumption-relative
 * lease. The deadline must be future and at most 30 seconds from this call's
 * own raw sample. The relative APIs above remain unchanged. */
tf_clock_status tf_clock_set_rate_until(tf_clock *clock, uint64_t owner,
                                       uint32_t rate_ppm, uint64_t not_after,
                                       uint64_t deadline,
                                       tf_clock_snapshot *snapshot);
tf_clock_status tf_clock_renew_until(tf_clock *clock, uint64_t owner,
                                    uint64_t not_after, uint64_t deadline,
                                    tf_clock_snapshot *snapshot);
/* Close advances time and restores rate one while keeping accumulated offset.
 * No hook/trampoline/module retirement is performed by this core. */
tf_clock_status tf_clock_close(tf_clock *clock, uint64_t owner,
                              tf_clock_snapshot *snapshot);

#ifdef __cplusplus
}
#endif
#endif
