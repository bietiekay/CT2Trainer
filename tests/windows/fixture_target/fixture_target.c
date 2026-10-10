/* Owned, harmless memory target for the Windows trainer test gate.
 * The 16-byte marker is followed by three aligned 32-bit fields. Keep the
 * marker and field order in sync with fixture.ct if this layout changes.
 */
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

#ifdef _WIN32
#  ifndef _WIN64
#    error Build FixtureTarget.exe with a Windows x64 compiler.
#  endif
#  include <windows.h>
#  define FIXTURE_EXPORT __declspec(dllexport)
static void wait_one_second(void) { Sleep(1000); }
static unsigned long process_id(void) { return (unsigned long)GetCurrentProcessId(); }
#else
/* Allows a local logic smoke test; it does not validate Windows or CE. */
#  include <unistd.h>
#  define FIXTURE_EXPORT
static void wait_one_second(void) { sleep(1); }
static unsigned long process_id(void) { return (unsigned long)getpid(); }
#endif

typedef struct FixtureState {
    unsigned char marker[16];
    volatile uint32_t test_value;
    volatile uint32_t pause_ticks;
    volatile uint32_t ticks;
} FixtureState;

typedef char fixture_value_offset_is_16[(offsetof(FixtureState, test_value) == 16) ? 1 : -1];
typedef char fixture_pause_offset_is_20[(offsetof(FixtureState, pause_ticks) == 20) ? 1 : -1];
typedef char fixture_ticks_offset_is_24[(offsetof(FixtureState, ticks) == 24) ? 1 : -1];
typedef char fixture_state_size_is_28[(sizeof(FixtureState) == 28) ? 1 : -1];

/* ASCII marker: CT2T-FIX-2026-01. It belongs only to this process image. */
FIXTURE_EXPORT FixtureState fixture_state = {
    {0x43, 0x54, 0x32, 0x54, 0x2d, 0x46, 0x49, 0x58,
     0x2d, 0x32, 0x30, 0x32, 0x36, 0x2d, 0x30, 0x31},
    1234u,
    0u,
    0u
};

static void print_state(void)
{
    printf("PID=%lu value=%lu pause=%lu ticks=%lu\n",
           process_id(),
           (unsigned long)fixture_state.test_value,
           (unsigned long)fixture_state.pause_ticks,
           (unsigned long)fixture_state.ticks);
    fflush(stdout);
}

int main(void)
{
    puts("FixtureTarget: Ctrl+C to stop; restart for a fresh PID and data state.");
    print_state();
    for (;;) {
        wait_one_second();
        if (fixture_state.pause_ticks == 0u) {
            fixture_state.ticks += 1u;
        }
        print_state();
    }
}
