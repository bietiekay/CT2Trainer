/* Independently authored x64 fourteen-byte far-jump publication target. */
#include <windows.h>
#include <stdint.h>
#include <stdio.h>

#ifndef _WIN64
#error This fixture requires the x64 far-jump instruction profile.
#endif
#pragma section(".tfndebug", read, execute)
/* mov eax,ecx; add eax,1; nine nops; ret -- exactly fourteen displaced bytes. */
__declspec(allocate(".tfndebug")) const unsigned char fixture_code[] = {
    0x8b,0xc1,0x83,0xc0,0x01,0x90,0x90,0x90,0x90,0x90,0x90,0x90,0x90,0x90,0xc3
};
typedef int (__stdcall *TargetFunction)(int);
volatile LONG fixture_result = 0;
volatile LONG fixture_calls = 0;
volatile LONG fixture_bad = 0;
volatile LONG fixture_churn = 0;
volatile LONG fixture_stop = 0;

DWORD WINAPI caller(LPVOID context) {
    LONG remaining = (LONG)(intptr_t)context;
    do {
        LONG value = ((TargetFunction)(uintptr_t)fixture_code)(3);
        InterlockedExchange(&fixture_result, value);
        if (value != 4 && value != 103) InterlockedIncrement(&fixture_bad);
        InterlockedIncrement(&fixture_calls);
        Sleep(1);
    } while (!fixture_stop && (remaining < 0 || --remaining > 0));
    return 0;
}

DWORD WINAPI churn(LPVOID context) {
    (void)context;
    while (!fixture_stop) {
        HANDLE transient = CreateThread(NULL, 0, caller, (LPVOID)(intptr_t)20, 0, NULL);
        if (!transient) return 3;
        if (WaitForSingleObject(transient, INFINITE) != WAIT_OBJECT_0) return 4;
        CloseHandle(transient);
        InterlockedIncrement(&fixture_churn);
    }
    return 0;
}

int main(void) {
    HANDLE handles[5];
    int index;
    for (index = 0; index < 4; ++index)
        handles[index] = CreateThread(NULL, 0, caller, (LPVOID)(intptr_t)-1, 0, NULL);
    handles[4] = CreateThread(NULL, 0, churn, NULL, 0, NULL);
    for (index = 0; index < 5; ++index) if (!handles[index]) return 2;
    printf("{\"pid\":%lu,\"entry\":%llu,\"entry_size\":14,\"pointer_size\":8,"
           "\"result\":%llu,\"calls\":%llu,\"bad\":%llu,\"churn\":%llu,\"stop\":%llu}\n",
        (unsigned long)GetCurrentProcessId(), (unsigned long long)(uintptr_t)fixture_code,
        (unsigned long long)(uintptr_t)&fixture_result, (unsigned long long)(uintptr_t)&fixture_calls,
        (unsigned long long)(uintptr_t)&fixture_bad, (unsigned long long)(uintptr_t)&fixture_churn,
        (unsigned long long)(uintptr_t)&fixture_stop);
    fflush(stdout);
    while (!fixture_stop) Sleep(10);
    WaitForMultipleObjects(5, handles, TRUE, INFINITE);
    for (index = 0; index < 5; ++index) CloseHandle(handles[index]);
    return fixture_bad ? 5 : 0;
}
