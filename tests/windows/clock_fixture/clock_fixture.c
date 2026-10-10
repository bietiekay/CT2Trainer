/* Owned local verification. No hooks, DLL loading, target writes or CE code. */
#include "clock_core.h"
#include <mmsystem.h>
#include <stdio.h>
#include <stdlib.h>
#include <inttypes.h>

static unsigned int checks;
#define CHECK(test) do { ++checks; if (!(test)) { \
    fprintf(stderr, "FAIL line %u: %s\n", (unsigned int)__LINE__, #test); return 0; \
} } while (0)

typedef struct fake_counter { uint64_t now; int failed; } fake_counter;
static int fake_sample(void *context, uint64_t *out)
{
    fake_counter *source = (fake_counter *)context;
    if (source->failed) return 0;
    *out = source->now;
    return 1;
}

static tf_clock_config config_for(fake_counter *source, uint64_t frequency)
{
    tf_clock_config config;
    ZeroMemory(&config, sizeof(config));
    config.frequency = frequency;
    config.qpc_origin = config.initial_raw_qpc = source->now;
    config.tick64_origin = 10000;
    config.multimedia_origin = 20000;
    config.tick64_capture_qpc = config.multimedia_capture_qpc = source->now;
    config.raw_counter = fake_sample;
    config.raw_context = source;
    return config;
}

static int rate_and_epoch_tests(void)
{
    fake_counter source = {1000, 0};
    tf_clock clock;
    tf_clock_config config = config_for(&source, 1000);
    tf_clock_snapshot snapshot;
    uint64_t expected;
    unsigned int i;
    const uint32_t rates[] = {0, 200000, 500000, 1000000, 2000000, 16000000};
    config.tick64_capture_qpc = 1500;
    config.multimedia_capture_qpc = 1700;
    config.initial_raw_qpc = source.now = 2000;
    CHECK(tf_clock_initialize(&clock, &config) == TF_CLOCK_OK);
    CHECK(tf_clock_read(&clock, &snapshot) == TF_CLOCK_OK);
    CHECK(snapshot.qpc == 2000 && snapshot.tick64 == 10500 && snapshot.multimedia32 == 20300);
    source.now = 3000;
    CHECK(tf_clock_read(&clock, &snapshot) == TF_CLOCK_OK);
    CHECK(snapshot.qpc == 3000 && snapshot.tick64 == 11500 && snapshot.multimedia32 == 21300);
    for (i = 0; i < sizeof(rates)/sizeof(rates[0]); ++i) {
        source.now = UINT64_C(9007199254740999);
        config = config_for(&source, 10000000);
        CHECK(tf_clock_initialize(&clock, &config) == TF_CLOCK_OK);
        CHECK(tf_clock_set_rate(&clock, 1, rates[i], 100000000, &snapshot) == TF_CLOCK_OK);
        source.now += 1000000;
        CHECK(tf_clock_read(&clock, &snapshot) == TF_CLOCK_OK);
        expected = config.qpc_origin + rates[i];
        CHECK(snapshot.qpc == expected);
        CHECK(tf_clock_close(&clock, 1, &snapshot) == TF_CLOCK_OK);
        CHECK(snapshot.qpc == expected && snapshot.rate_ppm == TF_CLOCK_RATE_ONE);
        source.now += 111;
        CHECK(tf_clock_read(&clock, &snapshot) == TF_CLOCK_OK);
        CHECK(snapshot.qpc == expected + 111);
        CHECK(tf_clock_set_rate(&clock, 1, rates[i], 1000, &snapshot) == TF_CLOCK_STALE_OWNER);
        CHECK(tf_clock_set_rate(&clock, 2, rates[i], 1000, &snapshot) == TF_CLOCK_OK);
    }
    /* Small samples must accumulate, rather than truncate every interval. */
    source.now = 1;
    config = config_for(&source, 10000000);
    CHECK(tf_clock_initialize(&clock, &config) == TF_CLOCK_OK);
    CHECK(tf_clock_set_rate(&clock, 1, 200000, 300000000, &snapshot) == TF_CLOCK_OK);
    for (i = 0; i < 1000000; ++i) {
        ++source.now;
        if (tf_clock_read(&clock, &snapshot) != TF_CLOCK_OK) CHECK(0);
    }
    CHECK(snapshot.qpc == 200001);
    CHECK(tf_clock_set_rate(&clock, 1, 500000, 1000, &snapshot) == TF_CLOCK_OK);
    ++source.now;
    CHECK(tf_clock_read(&clock, &snapshot) == TF_CLOCK_OK && snapshot.qpc == 200001);
    CHECK(tf_clock_set_rate(&clock, 1, 1000000, 1000, &snapshot) == TF_CLOCK_OK);
    ++source.now;
    CHECK(tf_clock_read(&clock, &snapshot) == TF_CLOCK_OK && snapshot.qpc == 200002);
    CHECK(clock.fraction_ppm == 500000);
    /* A long interval remains representable even though delta*rate overflows
     * uint64 before division. The core must not use that direct product. */
    source.now = 0;
    config = config_for(&source, UINT64_C(100000000000000000));
    CHECK(tf_clock_initialize(&clock, &config) == TF_CLOCK_OK);
    CHECK(tf_clock_set_rate(&clock, 1, 2000000, UINT64_C(3000000000000000000), &snapshot) == TF_CLOCK_OK);
    source.now = UINT64_C(2000000000000000000);
    CHECK(tf_clock_read(&clock, &snapshot) == TF_CLOCK_OK);
    CHECK(snapshot.qpc == UINT64_C(4000000000000000000));
    CHECK(snapshot.tick64 == 50000);
    return 1;
}

static int lease_and_fault_tests(void)
{
    fake_counter source = {1000, 0};
    tf_clock clock;
    tf_clock_config config = config_for(&source, 1000);
    tf_clock_snapshot snapshot;
    CHECK(tf_clock_initialize(&clock, &config) == TF_CLOCK_OK);
    CHECK(tf_clock_set_rate(&clock, 10, TF_CLOCK_RATE_MAX + 1u, 100, &snapshot) == TF_CLOCK_BAD_INPUT);
    CHECK(tf_clock_set_rate(&clock, 10, TF_CLOCK_RATE_ONE, 0, &snapshot) == TF_CLOCK_BAD_INPUT);
    CHECK(tf_clock_set_rate(&clock, 10, TF_CLOCK_RATE_ONE, 30001, &snapshot) == TF_CLOCK_BAD_INPUT);
    CHECK(tf_clock_set_rate(&clock, 10, 2000000, 100, &snapshot) == TF_CLOCK_OK);
    source.now += 25;
    CHECK(tf_clock_renew(&clock, 10, 75, &snapshot) == TF_CLOCK_OK);
    CHECK(snapshot.qpc == 1050 && snapshot.rate_ppm == 2000000 && snapshot.lease_deadline == 1100);
    CHECK(tf_clock_set_rate(&clock, 11, 2000000, 100, &snapshot) == TF_CLOCK_OWNER_CONFLICT);
    source.now = 1300;
    CHECK(tf_clock_renew(&clock, 10, 100, &snapshot) == TF_CLOCK_STALE_OWNER);
    CHECK(snapshot.qpc == 1400 && snapshot.owner == 0 && snapshot.rate_ppm == TF_CLOCK_RATE_ONE);
    CHECK(tf_clock_set_rate(&clock, 10, 2000000, 100, &snapshot) == TF_CLOCK_STALE_OWNER);
    CHECK(tf_clock_set_rate(&clock, 11, 0, 100, &snapshot) == TF_CLOCK_OK);
    source.now = 1600;
    CHECK(tf_clock_close(&clock, 11, &snapshot) == TF_CLOCK_STALE_OWNER);
    CHECK(snapshot.qpc == 1600 && snapshot.owner == 0);
    source.now = 1599;
    CHECK(tf_clock_read(&clock, &snapshot) == TF_CLOCK_OK && snapshot.qpc == 1600 && snapshot.raw_anchor == 1600);
    source.now = 1601;
    CHECK(tf_clock_read(&clock, &snapshot) == TF_CLOCK_OK && snapshot.qpc == 1601);
    source.now = 1599;
    CHECK(tf_clock_read(&clock, &snapshot) == TF_CLOCK_REGRESSION && snapshot.qpc == 1601);
    source.now = 2000;
    CHECK(tf_clock_read(&clock, &snapshot) == TF_CLOCK_REGRESSION && snapshot.qpc == 1601);
    source.now = 10;
    config = config_for(&source, 1000);
    config.tick64_origin = UINT32_MAX - 1u;
    config.multimedia_origin = UINT32_MAX - 1u;
    CHECK(tf_clock_initialize(&clock, &config) == TF_CLOCK_OK);
    source.now += 3;
    CHECK(tf_clock_read(&clock, &snapshot) == TF_CLOCK_OK);
    CHECK(snapshot.tick64 == UINT64_C(4294967297) && snapshot.tick32 == 1 && snapshot.multimedia32 == 1);
    source.failed = 1;
    CHECK(tf_clock_read(&clock, &snapshot) == TF_CLOCK_RAW_SAMPLE_FAILED);
    source.failed = 0;
    source.now += 100;
    CHECK(tf_clock_read(&clock, &snapshot) == TF_CLOCK_RAW_SAMPLE_FAILED && snapshot.tick32 == 1);
    source.now = (uint64_t)INT64_MAX - 5;
    config = config_for(&source, 1000000);
    CHECK(tf_clock_initialize(&clock, &config) == TF_CLOCK_OK);
    CHECK(tf_clock_set_rate(&clock, 1, 2000000, 5, &snapshot) == TF_CLOCK_OK);
    source.now += 4;
    CHECK(tf_clock_read(&clock, &snapshot) == TF_CLOCK_OVERFLOW && snapshot.qpc == config.qpc_origin);
    source.now = 1;
    config = config_for(&source, 1000);
    config.tick64_origin = UINT64_MAX - 1;
    CHECK(tf_clock_initialize(&clock, &config) == TF_CLOCK_OK);
    source.now += 2;
    CHECK(tf_clock_read(&clock, &snapshot) == TF_CLOCK_OVERFLOW && snapshot.tick64 == UINT64_MAX - 1);
    config.frequency = 0;
    CHECK(tf_clock_initialize(&clock, &config) == TF_CLOCK_BAD_INPUT);
    return 1;
}

static int real_sample(void *ignored, uint64_t *out)
{
    LARGE_INTEGER value;
    (void)ignored;
    if (!QueryPerformanceCounter(&value) || value.QuadPart < 0) return 0;
    *out = (uint64_t)value.QuadPart;
    return 1;
}

static int initialize_real(tf_clock *clock, uint64_t *frequency)
{
    LARGE_INTEGER value;
    uint64_t before, after;
    tf_clock_config config;
    ZeroMemory(&config, sizeof(config));
    CHECK(QueryPerformanceFrequency(&value) && value.QuadPart > 0);
    config.frequency = *frequency = (uint64_t)value.QuadPart;
    CHECK(real_sample(NULL, &config.qpc_origin));
    CHECK(real_sample(NULL, &before));
    config.tick64_origin = GetTickCount64();
    CHECK(real_sample(NULL, &after));
    config.tick64_capture_qpc = before + (after - before)/2;
    CHECK(real_sample(NULL, &before));
    config.multimedia_origin = timeGetTime();
    CHECK(real_sample(NULL, &after));
    config.multimedia_capture_qpc = before + (after - before)/2;
    CHECK(real_sample(NULL, &config.initial_raw_qpc));
    config.raw_counter = real_sample;
    CHECK(tf_clock_initialize(clock, &config) == TF_CLOCK_OK);
    return 1;
}

typedef struct thread_context { tf_clock *clock; volatile LONG failures; } thread_context;
static DWORD WINAPI reader_thread(void *parameter)
{
    thread_context *context = (thread_context *)parameter;
    tf_clock_snapshot snapshot;
    uint64_t previous_qpc = 0, previous_tick = 0;
    unsigned int i;
    for (i = 0; i < 20000; ++i) {
        if (tf_clock_read(context->clock, &snapshot) != TF_CLOCK_OK ||
            snapshot.qpc < previous_qpc || snapshot.tick64 < previous_tick ||
            snapshot.tick32 != (uint32_t)snapshot.tick64)
            InterlockedIncrement(&context->failures);
        previous_qpc = snapshot.qpc;
        previous_tick = snapshot.tick64;
    }
    return 0;
}

static int real_and_thread_tests(void)
{
    tf_clock clock;
    tf_clock_snapshot first, last;
    uint64_t frequency, real_before, real_after, virtual_delta, real_delta;
    HANDLE threads[4];
    thread_context context;
    unsigned int i;
    const uint32_t rates[] = {200000, 500000, 2000000};
    CHECK(initialize_real(&clock, &frequency));
    context.clock = &clock;
    context.failures = 0;
    CHECK(tf_clock_set_rate(&clock, 1, TF_CLOCK_RATE_ONE, frequency * 30, &first) == TF_CLOCK_OK);
    for (i = 0; i < 4; ++i) {
        threads[i] = CreateThread(NULL, 0, reader_thread, &context, 0, NULL);
        CHECK(threads[i] != NULL);
    }
    for (i = 0; i < 1000; ++i)
        CHECK(tf_clock_set_rate(&clock, 1, (i%5)*400000, frequency*30, &last) == TF_CLOCK_OK);
    CHECK(WaitForMultipleObjects(4, threads, TRUE, 15000) == WAIT_OBJECT_0);
    for (i = 0; i < 4; ++i) CHECK(CloseHandle(threads[i]));
    CHECK(context.failures == 0);
    for (i = 0; i < sizeof(rates)/sizeof(rates[0]); ++i) {
        CHECK(tf_clock_set_rate(&clock, 1, rates[i], frequency*30, &first) == TF_CLOCK_OK);
        real_before = first.raw_anchor;
        Sleep(30);
        CHECK(tf_clock_read(&clock, &last) == TF_CLOCK_OK);
        real_after = last.raw_anchor;
        virtual_delta = last.qpc - first.qpc;
        real_delta = real_after - real_before;
        /* These slopes use exact raw samples, not Sleep's requested duration. */
        CHECK(real_delta > 0);
        CHECK(virtual_delta >= (real_delta*rates[i])/TF_CLOCK_RATE_ONE &&
              virtual_delta <= (real_delta*rates[i])/TF_CLOCK_RATE_ONE + 1);
    }
    CHECK(tf_clock_close(&clock, 1, &first) == TF_CLOCK_OK);
    CHECK(first.rate_ppm == TF_CLOCK_RATE_ONE && first.owner == 0);
    Sleep(10);
    CHECK(tf_clock_read(&clock, &last) == TF_CLOCK_OK);
    CHECK(last.qpc - first.qpc == last.raw_anchor - first.raw_anchor);
    CHECK(tf_clock_set_rate(&clock, 2, 0, frequency/100, &first) == TF_CLOCK_OK);
    Sleep(30);
    CHECK(tf_clock_read(&clock, &last) == TF_CLOCK_OK);
    CHECK(last.owner == 0 && last.rate_ppm == TF_CLOCK_RATE_ONE && last.qpc > first.qpc);
    return 1;
}

static uint64_t next_random(uint64_t *value)
{
    *value = *value * UINT64_C(6364136223846793005) + UINT64_C(1442695040888963407);
    return *value;
}

int main(void)
{
    unsigned int i;
    uint64_t random = 17, ticks, frequency, result;
    tf_clock_status status;
    if (!rate_and_epoch_tests() || !lease_and_fault_tests() || !real_and_thread_tests()) return 1;
    printf("{\"schema\":\"ct2trainer-clock-fixture/v1\",\"checks\":%u,\"pointer_bits\":%u,\"vectors\":[",
           checks, (unsigned int)(sizeof(void*) * 8));
    for (i = 0; i < 256; ++i) {
        ticks = next_random(&random);
        frequency = (i%4 == 0) ? (next_random(&random)%1000 + 1) : (next_random(&random) | 1);
        result = UINT64_MAX;
        status = tf_clock_ticks_to_ms(ticks, frequency, &result);
        printf("%s{\"ticks\":\"%" PRIu64 "\",\"frequency\":\"%" PRIu64 "\",\"milliseconds\":\"%" PRIu64 "\",\"status\":%u}",
               i ? "," : "", ticks, frequency, result, (unsigned int)status);
    }
    puts("]}");
    return 0;
}
