/* Independent integer time scaling. MIT: licenses/CT2Trainer-MIT.txt. */
#include "clock_core.h"
#include <limits.h>
#include <string.h>

typedef struct tf_clock_progress {
    uint64_t raw_anchor, elapsed, owner, deadline;
    uint32_t fraction, rate;
} tf_clock_progress;

tf_clock_status tf_clock_ticks_to_ms(uint64_t ticks, uint64_t frequency,
                                    uint64_t *milliseconds)
{
    uint64_t whole, remainder, quotient = 0, residue = 0;
    unsigned int bit;
    if (!milliseconds || frequency == 0) return TF_CLOCK_BAD_INPUT;
    whole = ticks / frequency;
    remainder = ticks % frequency;
    if (whole > UINT64_MAX / 1000u) return TF_CLOCK_OVERFLOW;
    /* Divide remainder*1000 without forming that possibly overflowing
     * product. Ten binary digits suffice. residue always stays < frequency;
     * quotient stays <1000. The subtraction comparisons avoid double overflow. */
    for (bit = 512u; bit != 0; bit >>= 1) {
        quotient *= 2u;
        if (residue >= frequency - residue) {
            residue -= frequency - residue;
            ++quotient;
        } else residue *= 2u;
        if ((1000u & bit) != 0) {
            if (residue >= frequency - remainder) {
                residue -= frequency - remainder;
                ++quotient;
            } else residue += remainder;
        }
    }
    whole *= 1000u;
    if (quotient > UINT64_MAX - whole) return TF_CLOCK_OVERFLOW;
    *milliseconds = whole + quotient;
    return TF_CLOCK_OK;
}

static tf_clock_status materialize(const tf_clock *clock,
                                   const tf_clock_progress *next,
                                   tf_clock_snapshot *out)
{
    uint64_t ticks_epoch = clock->config.tick64_capture_qpc - clock->config.qpc_origin;
    uint64_t multimedia_epoch = clock->config.multimedia_capture_qpc - clock->config.qpc_origin;
    uint64_t tick_ms, multimedia_ms;
    tf_clock_status status;
    if (next->elapsed > (uint64_t)INT64_MAX - clock->config.qpc_origin ||
        next->elapsed < ticks_epoch || next->elapsed < multimedia_epoch)
        return TF_CLOCK_OVERFLOW;
    status = tf_clock_ticks_to_ms(next->elapsed - ticks_epoch,
                                 clock->config.frequency, &tick_ms);
    if (status != TF_CLOCK_OK) return status;
    status = tf_clock_ticks_to_ms(next->elapsed - multimedia_epoch,
                                 clock->config.frequency, &multimedia_ms);
    if (status != TF_CLOCK_OK) return status;
    if (tick_ms > UINT64_MAX - clock->config.tick64_origin)
        return TF_CLOCK_OVERFLOW;
    out->qpc = clock->config.qpc_origin + next->elapsed;
    out->tick64 = clock->config.tick64_origin + tick_ms;
    out->tick32 = (uint32_t)out->tick64;
    /* DWORD rollover is API behavior, rather than an arithmetic fault. */
    out->multimedia32 = clock->config.multimedia_origin + (uint32_t)multimedia_ms;
    out->raw_anchor = next->raw_anchor;
    out->owner = next->owner;
    out->lease_deadline = next->deadline;
    out->rate_ppm = next->rate;
    out->fault = TF_CLOCK_OK;
    return TF_CLOCK_OK;
}

static tf_clock_progress current_progress(const tf_clock *clock)
{
    tf_clock_progress result;
    result.raw_anchor = clock->raw_anchor;
    result.elapsed = clock->virtual_elapsed;
    result.owner = clock->owner;
    result.deadline = clock->lease_deadline;
    result.fraction = clock->fraction_ppm;
    result.rate = clock->rate_ppm;
    return result;
}

static tf_clock_status advance_segment(tf_clock_progress *next, uint64_t now)
{
    uint64_t delta = now - next->raw_anchor;
    uint64_t whole = delta / TF_CLOCK_RATE_ONE;
    uint64_t partial = (delta % TF_CLOCK_RATE_ONE) * next->rate + next->fraction;
    uint64_t addition;
    if (next->rate != 0 && whole > UINT64_MAX / next->rate)
        return TF_CLOCK_OVERFLOW;
    addition = whole * next->rate;
    if (partial / TF_CLOCK_RATE_ONE > UINT64_MAX - addition)
        return TF_CLOCK_OVERFLOW;
    addition += partial / TF_CLOCK_RATE_ONE;
    if (addition > UINT64_MAX - next->elapsed) return TF_CLOCK_OVERFLOW;
    next->elapsed += addition;
    next->fraction = (uint32_t)(partial % TF_CLOCK_RATE_ONE);
    next->raw_anchor = now;
    return TF_CLOCK_OK;
}

static void commit(tf_clock *clock, const tf_clock_progress *next,
                   const tf_clock_snapshot *snapshot)
{
    clock->raw_anchor = next->raw_anchor;
    clock->virtual_elapsed = next->elapsed;
    clock->owner = next->owner;
    clock->lease_deadline = next->deadline;
    clock->fraction_ppm = next->fraction;
    clock->rate_ppm = next->rate;
    clock->last = *snapshot;
}

static tf_clock_status fail(tf_clock *clock, tf_clock_status status)
{
    clock->fault = status;
    clock->last.fault = status;
    return status;
}

/* Must hold lock. Stages everything so a failing interval cannot partially
 * change any published clock. A sticky fault preserves the final valid output. */
static tf_clock_status update(tf_clock *clock)
{
    uint64_t now;
    tf_clock_progress next;
    tf_clock_snapshot snapshot;
    tf_clock_status status;
    if (clock->fault != TF_CLOCK_OK) return clock->fault;
    if (!clock->config.raw_counter(clock->config.raw_context, &now))
        return fail(clock, TF_CLOCK_RAW_SAMPLE_FAILED);
    if (now > (uint64_t)INT64_MAX) return fail(clock, TF_CLOCK_OVERFLOW);
    if (now < clock->raw_anchor) {
        /* Microsoft's QPC cross-thread ordering has one-tick ambiguity. Keep
         * the highest anchor: rewinding it would count the following tick twice. */
        if (clock->raw_anchor - now == 1u) now = clock->raw_anchor;
        else return fail(clock, TF_CLOCK_REGRESSION);
    }
    next = current_progress(clock);
    if (next.owner != 0 && now >= next.deadline) {
        status = advance_segment(&next, next.deadline);
        if (status != TF_CLOCK_OK) return fail(clock, status);
        next.rate = TF_CLOCK_RATE_ONE;
        next.owner = 0;
        next.deadline = 0;
    }
    status = advance_segment(&next, now);
    if (status == TF_CLOCK_OK) status = materialize(clock, &next, &snapshot);
    if (status != TF_CLOCK_OK) return fail(clock, status);
    commit(clock, &next, &snapshot);
    return TF_CLOCK_OK;
}

tf_clock_status tf_clock_initialize(tf_clock *clock,
                                    const tf_clock_config *config)
{
    tf_clock_progress initial;
    tf_clock_snapshot snapshot;
    tf_clock_status status;
    if (!clock || !config || !config->raw_counter || config->frequency == 0 ||
        config->frequency > (uint64_t)INT64_MAX ||
        config->qpc_origin > config->initial_raw_qpc ||
        config->initial_raw_qpc > (uint64_t)INT64_MAX ||
        config->tick64_capture_qpc < config->qpc_origin ||
        config->tick64_capture_qpc > config->initial_raw_qpc ||
        config->multimedia_capture_qpc < config->qpc_origin ||
        config->multimedia_capture_qpc > config->initial_raw_qpc)
        return TF_CLOCK_BAD_INPUT;
    memset(clock, 0, sizeof(*clock));
    InitializeSRWLock(&clock->lock);
    clock->config = *config;
    initial.raw_anchor = config->initial_raw_qpc;
    initial.elapsed = config->initial_raw_qpc - config->qpc_origin;
    initial.owner = initial.deadline = 0;
    initial.fraction = 0;
    initial.rate = TF_CLOCK_RATE_ONE;
    status = materialize(clock, &initial, &snapshot);
    if (status != TF_CLOCK_OK) return status;
    commit(clock, &initial, &snapshot);
    return TF_CLOCK_OK;
}

tf_clock_status tf_clock_read(tf_clock *clock, tf_clock_snapshot *snapshot)
{
    tf_clock_status status;
    tf_clock_snapshot result;
    if (!clock || !snapshot) return TF_CLOCK_BAD_INPUT;
    AcquireSRWLockExclusive(&clock->lock);
    status = update(clock);
    result = clock->last;
    ReleaseSRWLockExclusive(&clock->lock);
    *snapshot = result;
    return status;
}

static int valid_lease(const tf_clock *clock, uint64_t ticks)
{
    uint64_t maximum = clock->config.frequency > UINT64_MAX / TF_CLOCK_LEASE_SECONDS_MAX
        ? UINT64_MAX : clock->config.frequency * TF_CLOCK_LEASE_SECONDS_MAX;
    return ticks != 0 && ticks <= maximum;
}

static tf_clock_status control(tf_clock *clock, uint64_t owner,
                               uint32_t rate, uint64_t lease_ticks,
                               int operation, uint64_t not_after, tf_clock_snapshot *snapshot)
{
    tf_clock_status status;
    tf_clock_progress next;
    tf_clock_snapshot changed;
    tf_clock_snapshot result;
    if (!clock || !snapshot || owner == 0 ||
        (operation >= 3 && (not_after == 0 || not_after > lease_ticks)) ||
        (operation != 2 && (lease_ticks == 0 || rate > TF_CLOCK_RATE_MAX ||
         (operation < 3 && !valid_lease(clock, lease_ticks)))))
        return TF_CLOCK_BAD_INPUT;
    AcquireSRWLockExclusive(&clock->lock);
    /* Expiry is applied before renew/change/close as well as before reads. */
    status = update(clock);
    if (status == TF_CLOCK_OK) {
        if (clock->owner != 0 && clock->owner != owner) status = TF_CLOCK_OWNER_CONFLICT;
        else if ((clock->owner == 0 && ((operation != 0 && operation != 3) || owner <= clock->last_owner)))
            status = TF_CLOCK_STALE_OWNER;
        else if (operation >= 3 && (lease_ticks <= clock->raw_anchor || lease_ticks > (uint64_t)INT64_MAX ||
                 clock->raw_anchor >= not_after || !valid_lease(clock, lease_ticks - clock->raw_anchor)))
            status = TF_CLOCK_BAD_INPUT;
        else if (operation < 2 && lease_ticks > (uint64_t)INT64_MAX - clock->raw_anchor)
            status = TF_CLOCK_BAD_INPUT;
        else {
            next = current_progress(clock);
            if (operation == 2) {
                next.owner = next.deadline = 0;
                next.rate = TF_CLOCK_RATE_ONE;
            } else {
                next.owner = owner;
                next.deadline = operation >= 3 ? lease_ticks : next.raw_anchor + lease_ticks;
                if (operation == 0 || operation == 3) next.rate = rate;
            }
            status = materialize(clock, &next, &changed);
            if (status == TF_CLOCK_OK) {
                commit(clock, &next, &changed);
                if (owner > clock->last_owner) clock->last_owner = owner;
            }
        }
    }
    result = clock->last;
    ReleaseSRWLockExclusive(&clock->lock);
    *snapshot = result;
    return status;
}

tf_clock_status tf_clock_set_rate(tf_clock *clock, uint64_t owner,
                                 uint32_t rate_ppm, uint64_t lease_ticks,
                                 tf_clock_snapshot *snapshot)
{
    return control(clock, owner, rate_ppm, lease_ticks, 0, 0, snapshot);
}

tf_clock_status tf_clock_renew(tf_clock *clock, uint64_t owner,
                              uint64_t lease_ticks, tf_clock_snapshot *snapshot)
{
    return control(clock, owner, TF_CLOCK_RATE_ONE, lease_ticks, 1, 0, snapshot);
}

tf_clock_status tf_clock_close(tf_clock *clock, uint64_t owner,
                              tf_clock_snapshot *snapshot)
{
    return control(clock, owner, 0, 0, 2, 0, snapshot);
}

tf_clock_status tf_clock_set_rate_until(tf_clock *clock, uint64_t owner,
                                       uint32_t rate_ppm, uint64_t not_after, uint64_t deadline,
                                       tf_clock_snapshot *snapshot)
{
    return control(clock, owner, rate_ppm, deadline, 3, not_after, snapshot);
}

tf_clock_status tf_clock_renew_until(tf_clock *clock, uint64_t owner,
                                    uint64_t not_after, uint64_t deadline,
                                    tf_clock_snapshot *snapshot)
{
    return control(clock, owner, TF_CLOCK_RATE_ONE, deadline, 4, not_after, snapshot);
}
