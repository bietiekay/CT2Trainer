/* Owned host for its exact freshly built clock adapter DLL. No hooks/injection. */
#include "clock_adapter.h"
#include <stdio.h>
#include <wchar.h>
#include <inttypes.h>
#include <string.h>

typedef struct adapter_api {
    tf_clock_adapter_status (WINAPI *initialize)(const tf_clock_adapter_options *);
    tf_clock_adapter_status (WINAPI *info)(tf_clock_adapter_info *);
    tf_clock_adapter_status (WINAPI *submit)(const tf_clock_command *);
    tf_clock_adapter_status (WINAPI *take)(tf_clock_acknowledgement *);
    tf_clock_adapter_status (WINAPI *cancel)(uint64_t, tf_clock_cancel_result *);
    tf_clock_adapter_status (WINAPI *fence)(tf_clock_fence_status *);
    tf_original_qpc raw;
    void (WINAPI *inject)(DWORD);
    tf_original_qpc qpc;
    tf_original_tick32 tick32;
    tf_original_tick64 tick64;
    tf_original_tick32 multimedia;
} adapter_api;
static adapter_api api;
static unsigned int checks;
static uint64_t sequence;
static tf_clock_adapter_info information;
#define CHECK(test) do { ++checks; if (!(test)) { \
    fprintf(stderr, "FAIL line %u: %s\n", (unsigned int)__LINE__, #test); return 0; \
} } while (0)
#define LOAD(member, name) do { FARPROC procedure = GetProcAddress(module, name); \
    ++checks; if (!procedure) { fprintf(stderr,"Missing export %s\n",name); return 2; } \
    memcpy(&api.member, &procedure, sizeof(procedure)); } while (0)

static uint64_t fake_now = UINT64_C(9007199254740999), fake_step;
static int fake_failed, fake_reentry;
static volatile LONG reentry_count;
static volatile LONG block_once;
static HANDLE blocked_event, release_event;
static BOOL WINAPI fake_qpc(LARGE_INTEGER *counter)
{
    if (InterlockedCompareExchange(&block_once, 0, 1) == 1) {
        SetEvent(blocked_event);
        if (WaitForSingleObject(release_event, 5000) != WAIT_OBJECT_0) { SetLastError(ERROR_TIMEOUT); return FALSE; }
    }
    if (fake_reentry) {
        /* While called by the core under its lock, the other wrappers must use
         * their private original callbacks without trying to acquire that lock. */
        if (api.tick32() != (DWORD)(fake_now/10000u + 10000u) ||
            api.tick64() != fake_now/10000u + 10000u ||
            api.multimedia() != (DWORD)(fake_now/10000u + 20000u)) return FALSE;
        InterlockedIncrement(&reentry_count);
    }
    fake_now += fake_step;
    counter->QuadPart = (LONGLONG)fake_now;
    SetLastError(fake_failed ? ERROR_READ_FAULT : 0x76543210u);
    return !fake_failed;
}
static BOOL WINAPI fake_frequency(LARGE_INTEGER *frequency)
{
    frequency->QuadPart = 10000000;
    SetLastError(0x76543210u);
    return TRUE;
}
static DWORD WINAPI fake_tick32(void) { SetLastError(0x76543210u); return (DWORD)(fake_now/10000u + 10000u); }
static ULONGLONG WINAPI fake_tick64(void) { SetLastError(0x76543210u); return fake_now/10000u + 10000u; }
static DWORD WINAPI fake_multimedia(void) { SetLastError(0x76543210u); return (DWORD)(fake_now/10000u + 20000u); }

static tf_clock_adapter_options fake_options(void)
{
    tf_clock_adapter_options options;
    ZeroMemory(&options, sizeof(options));
    options.size = sizeof(options);
    options.version = TF_CLOCK_ADAPTER_VERSION;
    options.maximum_calibration_microseconds = TF_CLOCK_CALIBRATION_US_DEFAULT;
    options.originals.qpc = fake_qpc;
    options.originals.frequency = fake_frequency;
    options.originals.tick32 = fake_tick32;
    options.originals.tick64 = fake_tick64;
    options.originals.multimedia32 = fake_multimedia;
    return options;
}

static tf_clock_command command_for(uint64_t owner, uint32_t operation, uint32_t rate, uint64_t lease)
{
    tf_clock_command command;
    LARGE_INTEGER now;
    if (!api.raw(&now)) { fprintf(stderr,"Raw counter unavailable\n"); ExitProcess(2); }
    ZeroMemory(&command, sizeof(command));
    command.size = sizeof(command);
    command.version = TF_CLOCK_ADAPTER_VERSION;
    command.sequence = ++sequence;
    command.owner = owner;
    command.operation = operation;
    command.rate_ppm = rate;
    command.not_after_qpc = (uint64_t)now.QuadPart + (lease && lease < information.frequency/2 ? lease : information.frequency/2);
    command.lease_deadline_qpc = operation == TF_CLOCK_COMMAND_CLOSE ? 0 : (uint64_t)now.QuadPart + lease;
    return command;
}

static int apply(tf_clock_command command, tf_clock_acknowledgement *ack)
{
    LARGE_INTEGER sample;
    unsigned int attempt;
    CHECK(api.submit(&command) == TF_CLOCK_ADAPTER_OK);
    for (attempt = 0; attempt < 1000; ++attempt) {
        CHECK(api.qpc(&sample));
        if (api.take(ack) == TF_CLOCK_ADAPTER_OK) break;
        Sleep(0);
    }
    CHECK(attempt < 1000);
    CHECK(ack->size == sizeof(*ack) && ack->version == TF_CLOCK_ADAPTER_VERSION);
    CHECK(ack->sequence == command.sequence && ack->owner == command.owner && ack->operation == command.operation);
    return 1;
}

static int fake_tests(void)
{
    tf_clock_adapter_options options = fake_options();
    tf_clock_acknowledgement ack;
    tf_clock_command command, blocked;
    LARGE_INTEGER counter;
    uint64_t initial, paused, before;
    DWORD tick32, multimedia;
    ULONGLONG tick64;
    CHECK(!api.qpc(&counter));
    SetLastError(0xabcdef12u);
    CHECK(api.initialize(&options) == TF_CLOCK_ADAPTER_OK && GetLastError() == 0xabcdef12u);
    CHECK(api.initialize(NULL) == TF_CLOCK_ADAPTER_ALREADY_INITIALIZED);
    CHECK(api.info(&information) == TF_CLOCK_ADAPTER_OK);
    CHECK(information.frequency == 10000000 && information.observed_calibration_ticks == 0);
    CHECK(information.command_size == sizeof(command) && information.acknowledgement_size == sizeof(ack));
    fake_reentry = 1;
    SetLastError(0xabcdef12u);
    CHECK(api.qpc(&counter) && GetLastError() == 0xabcdef12u);
    initial = (uint64_t)counter.QuadPart;
    CHECK(initial == fake_now && initial > UINT64_C(9007199254740992));
    command = command_for(1, TF_CLOCK_COMMAND_SET_RATE, 2000000, information.frequency*10);
    CHECK(api.submit(&command) == TF_CLOCK_ADAPTER_OK && GetLastError() == 0xabcdef12u);
    CHECK(api.take(&ack) == TF_CLOCK_ADAPTER_BUSY);
    blocked = command_for(1, TF_CLOCK_COMMAND_RENEW, 0, information.frequency);
    CHECK(api.submit(&blocked) == TF_CLOCK_ADAPTER_BUSY);
    CHECK(api.qpc(&counter));
    CHECK(api.submit(&blocked) == TF_CLOCK_ADAPTER_BUSY); /* ACK remains immutable. */
    CHECK(api.take(&ack) == TF_CLOCK_ADAPTER_OK && ack.clock_status == TF_CLOCK_OK);
    CHECK(ack.sequence == command.sequence && ack.snapshot.rate_ppm == 2000000 && ack.snapshot.qpc == initial);
    CHECK(api.submit(&command) == TF_CLOCK_ADAPTER_STALE_SEQUENCE);
    fake_now += information.frequency;
    CHECK(api.qpc(&counter) && (uint64_t)counter.QuadPart == initial + information.frequency*2);
    SetLastError(0xabcdef12u);
    tick64 = api.tick64(); CHECK(GetLastError() == 0xabcdef12u);
    tick32 = api.tick32(); CHECK(GetLastError() == 0xabcdef12u);
    multimedia = api.multimedia(); CHECK(GetLastError() == 0xabcdef12u);
    CHECK(tick32 == (DWORD)tick64);
    CHECK(tick64 == initial/10000u + 12000u && multimedia == (DWORD)(initial/10000u + 22000u));
    CHECK(apply(command_for(1, TF_CLOCK_COMMAND_SET_RATE, 0, information.frequency/10), &ack));
    paused = ack.snapshot.qpc;
    fake_now += information.frequency/20;
    CHECK(api.qpc(&counter) && (uint64_t)counter.QuadPart == paused);
    CHECK(api.tick64() == tick64 && api.tick32() == tick32 && api.multimedia() == multimedia);
    fake_now += information.frequency*3/20;
    CHECK(api.qpc(&counter) && (uint64_t)counter.QuadPart == paused + information.frequency/10);
    CHECK(apply(command_for(1, TF_CLOCK_COMMAND_RENEW, 0, information.frequency), &ack));
    CHECK(ack.clock_status == TF_CLOCK_STALE_OWNER && ack.snapshot.owner == 0 && ack.snapshot.rate_ppm == TF_CLOCK_RATE_ONE);
    CHECK(apply(command_for(2, TF_CLOCK_COMMAND_SET_RATE, TF_CLOCK_RATE_MAX, information.frequency), &ack));
    CHECK(ack.clock_status == TF_CLOCK_OK);
    before = ack.snapshot.qpc;
    fake_now += information.frequency/100;
    CHECK(api.qpc(&counter) && (uint64_t)counter.QuadPart == before + information.frequency*16/100);
    CHECK(apply(command_for(2, TF_CLOCK_COMMAND_CLOSE, 0, 0), &ack));
    CHECK(ack.clock_status == TF_CLOCK_OK && ack.snapshot.rate_ppm == TF_CLOCK_RATE_ONE);
    before = ack.snapshot.qpc;
    fake_now += information.frequency/100;
    CHECK(api.qpc(&counter) && (uint64_t)counter.QuadPart == before + information.frequency/100);
    command = command_for(2, TF_CLOCK_COMMAND_SET_RATE, 2000000, information.frequency);
    CHECK(api.submit(&command) == TF_CLOCK_ADAPTER_FENCED_OWNER);
    CHECK(apply(command_for(3, TF_CLOCK_COMMAND_SET_RATE, TF_CLOCK_RATE_ONE, information.frequency), &ack));
    CHECK(ack.clock_status == TF_CLOCK_OK && reentry_count > 10);
    command = command_for(3, TF_CLOCK_COMMAND_SET_RATE, TF_CLOCK_RATE_MAX + 1, information.frequency);
    CHECK(api.submit(&command) == TF_CLOCK_ADAPTER_BAD_INPUT);
    tick64 = api.tick64(); tick32 = api.tick32(); multimedia = api.multimedia();
    CHECK(api.qpc(&counter)); before = (uint64_t)counter.QuadPart;
    fake_failed = 1;
    fake_now += information.frequency;
    CHECK(!api.qpc(&counter) && (uint64_t)counter.QuadPart == before && GetLastError() == ERROR_READ_FAULT);
    CHECK(api.tick64() == tick64 && api.tick32() == tick32 && api.multimedia() == multimedia);
    fake_failed = 0;
    CHECK(!api.qpc(&counter) && (uint64_t)counter.QuadPart == before && GetLastError() == ERROR_READ_FAULT);
    command = command_for(4, TF_CLOCK_COMMAND_SET_RATE, TF_CLOCK_RATE_ONE, information.frequency);
    CHECK(api.submit(&command) == TF_CLOCK_ADAPTER_CLOCK_FAULT);
    return 1;
}

static int calibration_tests(void)
{
    tf_clock_adapter_options options = fake_options();
    LARGE_INTEGER counter;
    fake_step = 100000;
    SetLastError(0xabcdef12u);
    CHECK(api.initialize(&options) == TF_CLOCK_ADAPTER_CALIBRATION_FAILED);
    CHECK(GetLastError() == 0xabcdef12u);
    CHECK(api.info(&information) == TF_CLOCK_ADAPTER_NOT_INITIALIZED && !api.qpc(&counter));
    fake_step = 0;
    options.reserved = 1;
    CHECK(api.initialize(&options) == TF_CLOCK_ADAPTER_BAD_INPUT);
    options.reserved = 0;
    CHECK(api.initialize(&options) == TF_CLOCK_ADAPTER_OK);
    CHECK(api.info(&information) == TF_CLOCK_ADAPTER_OK);
    CHECK(information.maximum_calibration_ticks == 100000 && information.observed_calibration_ticks == 0);
    CHECK(api.qpc(&counter));
    return 1;
}

static int deadline_tests(void)
{
    tf_clock_adapter_options options = fake_options();
    tf_clock_command command;
    tf_clock_acknowledgement ack;
    LARGE_INTEGER sample;
    uint64_t origin, expected;
    CHECK(api.initialize(&options) == TF_CLOCK_ADAPTER_OK);
    CHECK(api.info(&information) == TF_CLOCK_ADAPTER_OK);
    CHECK(api.qpc(&sample)); origin = (uint64_t)sample.QuadPart;
    command = command_for(1, TF_CLOCK_COMMAND_SET_RATE, TF_CLOCK_RATE_MAX, information.frequency);
    command.not_after_qpc = fake_now + information.frequency/10;
    CHECK(api.submit(&command) == TF_CLOCK_ADAPTER_OK);
    fake_now += information.frequency/5;
    CHECK(api.qpc(&sample) && (uint64_t)sample.QuadPart == origin + information.frequency/5);
    CHECK(api.take(&ack) == TF_CLOCK_ADAPTER_OK && ack.disposition == TF_CLOCK_ACK_EXPIRED && !ack.snapshot_valid);
    command = command_for(1, TF_CLOCK_COMMAND_SET_RATE, TF_CLOCK_RATE_MAX, information.frequency);
    CHECK(api.submit(&command) == TF_CLOCK_ADAPTER_FENCED_OWNER);
    command = command_for(2, TF_CLOCK_COMMAND_SET_RATE, 2000000, information.frequency);
    CHECK(api.submit(&command) == TF_CLOCK_ADAPTER_OK);
    fake_now += information.frequency/4;
    CHECK(api.qpc(&sample));
    CHECK(api.take(&ack) == TF_CLOCK_ADAPTER_OK && ack.snapshot_valid && ack.clock_status == TF_CLOCK_OK);
    CHECK(ack.snapshot.lease_deadline == command.lease_deadline_qpc);
    expected = ack.snapshot.qpc + (command.lease_deadline_qpc - ack.snapshot.raw_anchor)*2 + information.frequency/10;
    fake_now = command.lease_deadline_qpc + information.frequency/10;
    CHECK(api.qpc(&sample) && (uint64_t)sample.QuadPart == expected);
    /* Cross not-after between consume's preliminary sample and the core's own
     * locked sample. It must still refuse the transition at that second sample. */
    command = command_for(3, TF_CLOCK_COMMAND_SET_RATE, TF_CLOCK_RATE_MAX, information.frequency);
    command.not_after_qpc = fake_now + 100;
    CHECK(api.submit(&command) == TF_CLOCK_ADAPTER_OK);
    fake_step = 60;
    CHECK(api.qpc(&sample));
    fake_step = 0;
    CHECK(api.take(&ack) == TF_CLOCK_ADAPTER_OK && ack.disposition == TF_CLOCK_ACK_EXPIRED);
    CHECK(ack.snapshot_valid && ack.snapshot.owner == 0 && ack.snapshot.rate_ppm == TF_CLOCK_RATE_ONE);
    return 1;
}

static int cancellation_tests(void)
{
    tf_clock_adapter_options options = fake_options();
    tf_clock_command command;
    tf_clock_acknowledgement ack;
    tf_clock_cancel_result cancelled;
    tf_clock_fence_status fence;
    LARGE_INTEGER sample;
    CHECK(api.initialize(&options) == TF_CLOCK_ADAPTER_OK);
    CHECK(api.info(&information) == TF_CLOCK_ADAPTER_OK);
    CHECK(apply(command_for(1, TF_CLOCK_COMMAND_SET_RATE, 2000000, information.frequency), &ack));
    command = command_for(1, TF_CLOCK_COMMAND_RENEW, 0, information.frequency);
    CHECK(api.submit(&command) == TF_CLOCK_ADAPTER_OK);
    CHECK(api.cancel(1, &cancelled) == TF_CLOCK_ADAPTER_OK && cancelled.drained_sequence == command.sequence);
    CHECK(api.take(&ack) == TF_CLOCK_ADAPTER_OK && ack.disposition == TF_CLOCK_ACK_CANCELLED_PENDING && !ack.snapshot_valid);
    CHECK(api.fence(&fence) == TF_CLOCK_ADAPTER_OK && fence.fenced_through_owner == 1 && fence.retired_through_owner == 0);
    CHECK(api.qpc(&sample));
    CHECK(api.fence(&fence) == TF_CLOCK_ADAPTER_OK && fence.retired_through_owner == 1);
    command = command_for(1, TF_CLOCK_COMMAND_SET_RATE, TF_CLOCK_RATE_MAX, information.frequency);
    CHECK(api.submit(&command) == TF_CLOCK_ADAPTER_FENCED_OWNER);
    CHECK(apply(command_for(2, TF_CLOCK_COMMAND_SET_RATE, TF_CLOCK_RATE_ONE, information.frequency), &ack));
    CHECK(ack.snapshot_valid && ack.clock_status == TF_CLOCK_OK && ack.snapshot.owner == 2);
    CHECK(api.cancel(1, &cancelled) == TF_CLOCK_ADAPTER_OK && cancelled.fenced_through_owner == 1);
    CHECK(api.qpc(&sample));
    return 1;
}

static DWORD WINAPI single_reader(void *unused)
{
    LARGE_INTEGER value;
    (void)unused;
    return api.qpc(&value) ? 0 : 1;
}

static int busy_cancellation_tests(void)
{
    tf_clock_adapter_options options = fake_options();
    tf_clock_command command;
    tf_clock_acknowledgement ack;
    tf_clock_cancel_result cancelled;
    tf_clock_fence_status fence;
    HANDLE worker;
    DWORD worker_exit;
    LARGE_INTEGER before, after, frequency;
    CHECK(api.initialize(&options) == TF_CLOCK_ADAPTER_OK);
    CHECK(api.info(&information) == TF_CLOCK_ADAPTER_OK);
    blocked_event = CreateEventW(NULL, TRUE, FALSE, NULL); release_event = CreateEventW(NULL, TRUE, FALSE, NULL);
    CHECK(blocked_event && release_event);
    command = command_for(1, TF_CLOCK_COMMAND_SET_RATE, TF_CLOCK_RATE_MAX, information.frequency);
    CHECK(api.submit(&command) == TF_CLOCK_ADAPTER_OK);
    InterlockedExchange(&block_once, 1);
    worker = CreateThread(NULL, 0, single_reader, NULL, 0, NULL); CHECK(worker != NULL);
    CHECK(WaitForSingleObject(blocked_event, 2000) == WAIT_OBJECT_0);
    CHECK(QueryPerformanceCounter(&before) && QueryPerformanceFrequency(&frequency));
    CHECK(api.cancel(1, &cancelled) == TF_CLOCK_ADAPTER_OK && cancelled.drained_sequence == 0);
    CHECK(QueryPerformanceCounter(&after) && after.QuadPart-before.QuadPart < frequency.QuadPart/10);
    CHECK(api.fence(&fence) == TF_CLOCK_ADAPTER_OK && fence.fenced_through_owner == 1 && fence.retired_through_owner == 0);
    CHECK(SetEvent(release_event));
    CHECK(WaitForSingleObject(worker, 2000) == WAIT_OBJECT_0 && GetExitCodeThread(worker,&worker_exit) && worker_exit == 0);
    CHECK(api.take(&ack) == TF_CLOCK_ADAPTER_OK && ack.disposition == TF_CLOCK_ACK_CANCELLED_AFTER_CONSUMPTION);
    CHECK(ack.snapshot_valid && ack.snapshot.owner == 0 && ack.snapshot.rate_ppm == TF_CLOCK_RATE_ONE);
    CHECK(api.fence(&fence) == TF_CLOCK_ADAPTER_OK && fence.retired_through_owner == 1);
    CHECK(CloseHandle(worker) && CloseHandle(blocked_event) && CloseHandle(release_event));
    return 1;
}

static int platform_tests(void)
{
    tf_clock_adapter_options options = fake_options();
    tf_clock_command command;
    tf_clock_acknowledgement ack;
    LARGE_INTEGER sample;
    CHECK(api.initialize(&options) == TF_CLOCK_ADAPTER_OK);
    CHECK(api.info(&information) == TF_CLOCK_ADAPTER_OK);
    command = command_for(1, TF_CLOCK_COMMAND_SET_RATE, TF_CLOCK_RATE_MAX, information.frequency);
    CHECK(api.submit(&command) == TF_CLOCK_ADAPTER_OK);
    api.inject(ERROR_NO_SYSTEM_RESOURCES);
    CHECK(!api.qpc(&sample) && GetLastError() == ERROR_NO_SYSTEM_RESOURCES);
    CHECK(api.take(&ack) == TF_CLOCK_ADAPTER_OK && ack.disposition == TF_CLOCK_ACK_PLATFORM_FAULT && !ack.snapshot_valid);
    command = command_for(2, TF_CLOCK_COMMAND_SET_RATE, TF_CLOCK_RATE_ONE, information.frequency);
    CHECK(api.submit(&command) == TF_CLOCK_ADAPTER_CLOCK_FAULT);
    CHECK(!api.qpc(NULL) && GetLastError() == ERROR_INVALID_PARAMETER);
    return 1;
}

static volatile LONG thread_failures;
static DWORD WINAPI reader(void *unused)
{
    LARGE_INTEGER counter;
    uint64_t previous_qpc = 0, previous_tick = 0, tick;
    DWORD previous32 = 0, previous_media = 0, tick32, media;
    unsigned int i;
    (void)unused;
    for (i = 0; i < 10000; ++i) {
        SetLastError(0xabcdef12u);
        if (!api.qpc(&counter) || GetLastError() != 0xabcdef12u || (uint64_t)counter.QuadPart < previous_qpc)
            InterlockedIncrement(&thread_failures);
        tick = api.tick64();
        if (GetLastError() != 0xabcdef12u || tick < previous_tick) InterlockedIncrement(&thread_failures);
        tick32 = api.tick32(); media = api.multimedia();
        if (GetLastError() != 0xabcdef12u || (i != 0 && ((DWORD)(tick32-previous32) > 0x7fffffffu ||
            (DWORD)(media-previous_media) > 0x7fffffffu))) InterlockedIncrement(&thread_failures);
        previous_qpc = (uint64_t)counter.QuadPart; previous_tick = tick;
        previous32 = tick32; previous_media = media;
    }
    return 0;
}

static int real_tests(void)
{
    HANDLE threads[4];
    tf_clock_acknowledgement first, last;
    uint64_t real_delta, virtual_delta;
    LARGE_INTEGER counter;
    unsigned int i;
    const uint32_t rates[] = {200000, 500000, 2000000};
    CHECK(api.initialize(NULL) == TF_CLOCK_ADAPTER_OK);
    CHECK(api.info(&information) == TF_CLOCK_ADAPTER_OK);
    CHECK(information.observed_calibration_ticks <= information.maximum_calibration_ticks);
    CHECK(apply(command_for(1, TF_CLOCK_COMMAND_SET_RATE, TF_CLOCK_RATE_ONE, information.frequency*30), &first));
    for (i = 0; i < 4; ++i) { threads[i] = CreateThread(NULL, 0, reader, NULL, 0, NULL); CHECK(threads[i] != NULL); }
    for (i = 0; i < 100; ++i) {
        CHECK(apply(command_for(1, TF_CLOCK_COMMAND_SET_RATE, (i%5)*400000, information.frequency*30), &last));
        CHECK(last.clock_status == TF_CLOCK_OK);
    }
    CHECK(WaitForMultipleObjects(4, threads, TRUE, 15000) == WAIT_OBJECT_0);
    for (i = 0; i < 4; ++i) CHECK(CloseHandle(threads[i]));
    CHECK(thread_failures == 0);
    for (i = 0; i < sizeof(rates)/sizeof(rates[0]); ++i) {
        CHECK(apply(command_for(1, TF_CLOCK_COMMAND_SET_RATE, rates[i], information.frequency*30), &first));
        Sleep(20);
        CHECK(apply(command_for(1, TF_CLOCK_COMMAND_RENEW, 0, information.frequency*30), &last));
        real_delta = last.snapshot.raw_anchor - first.snapshot.raw_anchor;
        virtual_delta = last.snapshot.qpc - first.snapshot.qpc;
        CHECK(real_delta > 0 && virtual_delta >= real_delta*rates[i]/TF_CLOCK_RATE_ONE &&
              virtual_delta <= real_delta*rates[i]/TF_CLOCK_RATE_ONE + 1);
    }
    CHECK(apply(command_for(1, TF_CLOCK_COMMAND_SET_RATE, 0, information.frequency/100), &first));
    Sleep(30);
    CHECK(api.qpc(&counter) && (uint64_t)counter.QuadPart > first.snapshot.qpc);
    CHECK(apply(command_for(1, TF_CLOCK_COMMAND_RENEW, 0, information.frequency), &last));
    CHECK(last.clock_status == TF_CLOCK_STALE_OWNER && last.snapshot.rate_ppm == TF_CLOCK_RATE_ONE && last.snapshot.owner == 0);
    CHECK(apply(command_for(2, TF_CLOCK_COMMAND_SET_RATE, 2000000, information.frequency), &first));
    CHECK(apply(command_for(2, TF_CLOCK_COMMAND_CLOSE, 0, 0), &last));
    real_delta = last.snapshot.raw_anchor - first.snapshot.raw_anchor;
    virtual_delta = last.snapshot.qpc - first.snapshot.qpc;
    CHECK(virtual_delta >= real_delta*2 && virtual_delta <= real_delta*2+1);
    CHECK(apply(command_for(3, TF_CLOCK_COMMAND_SET_RATE, TF_CLOCK_RATE_ONE, information.frequency), &first));
    Sleep(10);
    CHECK(apply(command_for(3, TF_CLOCK_COMMAND_RENEW, 0, information.frequency), &last));
    CHECK(last.snapshot.qpc-first.snapshot.qpc == last.snapshot.raw_anchor-first.snapshot.raw_anchor);
    return 1;
}

static DWORD WINAPI fence_worker(void *parameter)
{
    uint64_t base = ((uint64_t)(uintptr_t)parameter * 2u + 1u) << 32;
    tf_clock_cancel_result cancelled;
    tf_clock_fence_status status;
    tf_clock_adapter_status result;
    LARGE_INTEGER sample;
    unsigned int i;
    for (i = 1; i <= 5000; ++i) {
        result = api.cancel(base+i, &cancelled);
        if ((result != TF_CLOCK_ADAPTER_OK && result != TF_CLOCK_ADAPTER_BUSY) || !api.qpc(&sample) ||
            api.fence(&status) != TF_CLOCK_ADAPTER_OK || status.retired_through_owner > status.fenced_through_owner)
            InterlockedIncrement(&thread_failures);
    }
    return 0;
}

static int fence_concurrency_tests(void)
{
    tf_clock_adapter_options options = fake_options();
    tf_clock_fence_status status;
    HANDLE workers[4];
    unsigned int i;
    CHECK(api.initialize(&options) == TF_CLOCK_ADAPTER_OK);
    CHECK(api.info(&information) == TF_CLOCK_ADAPTER_OK);
    for (i = 0; i < 4; ++i) { workers[i] = CreateThread(NULL,0,fence_worker,(LPVOID)(uintptr_t)i,0,NULL); CHECK(workers[i] != NULL); }
    CHECK(WaitForMultipleObjects(4,workers,TRUE,15000) == WAIT_OBJECT_0);
    for (i = 0; i < 4; ++i) CHECK(CloseHandle(workers[i]));
    CHECK(thread_failures == 0);
    CHECK(api.fence(&status) == TF_CLOCK_ADAPTER_OK && status.fenced_through_owner == (UINT64_C(7)<<32)+5000);
    CHECK(status.retired_through_owner == status.fenced_through_owner);
    return 1;
}

int wmain(int argc, wchar_t **argv)
{
    HMODULE module, retained;
    wchar_t full_path[32768];
    const wchar_t *basename;
    LARGE_INTEGER counter;
    int ok;
    if (argc != 3) return 2;
    if (GetFullPathNameW(argv[1], 32768, full_path, NULL) == 0 || wcscmp(argv[1], full_path) != 0) return 2;
    basename = wcsrchr(full_path, L'\\');
    if (!basename || wcscmp(basename+1, L"NativeClockAdapter.dll")) return 2;
    module = LoadLibraryExW(full_path, NULL, LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_SYSTEM32);
    if (!module) { fprintf(stderr, "Owned DLL load failed: %lu\n", GetLastError()); return 2; }
    LOAD(initialize, "TFClockInitialize"); LOAD(info, "TFClockGetInfo");
    LOAD(submit, "TFClockSubmit"); LOAD(take, "TFClockTakeAcknowledgement");
    LOAD(cancel, "TFClockCancel"); LOAD(fence, "TFClockGetFenceStatus"); LOAD(raw, "TFClockReadRawCounter");
    LOAD(qpc, "TFQueryPerformanceCounter"); LOAD(tick32, "TFGetTickCount");
    LOAD(tick64, "TFGetTickCount64"); LOAD(multimedia, "TFtimeGetTime");
    if (!wcscmp(argv[2], L"platform")) { LOAD(inject,"TFClockFixtureInjectFault"); }
    ok = !wcscmp(argv[2], L"real") ? real_tests() : !wcscmp(argv[2], L"fake") ? fake_tests() :
         !wcscmp(argv[2], L"calibration") ? calibration_tests() : !wcscmp(argv[2], L"deadline") ? deadline_tests() :
         !wcscmp(argv[2], L"cancel") ? cancellation_tests() : !wcscmp(argv[2], L"cancel_busy") ? busy_cancellation_tests() :
         !wcscmp(argv[2], L"platform") ? platform_tests() : !wcscmp(argv[2], L"fence_concurrency") ? fence_concurrency_tests() : 0;
    if (!ok) return 1;
    /* Ordinary FreeLibrary must not unmap a successfully initialized adapter. */
    if (!FreeLibrary(module) || !GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
        (LPCWSTR)(uintptr_t)api.qpc, &retained) || retained != module) return 1;
    if (wcscmp(argv[2], L"fake") && wcscmp(argv[2], L"platform") && !api.qpc(&counter)) return 1;
    printf("{\"schema\":\"ct2trainer-clock-adapter-fixture/v2\",\"mode\":\"%ls\",\"checks\":%u,\"pointer_bits\":%u,\"frequency\":\"%" PRIu64 "\",\"calibration_ticks\":\"%" PRIu64 "\",\"reentry_calls\":%ld,\"retained_after_free\":true}\n",
        argv[2], checks, (unsigned int)(sizeof(void*)*8), information.frequency, information.observed_calibration_ticks, reentry_count);
    return 0;
}
