/* Independently authored cooperative executable-hook fixture. */
#include <windows.h>
#include <stdint.h>
#include <stdio.h>

#ifndef _WIN64
#error This fixture requires x64 Windows.
#endif

#pragma section(".tfnhook", read, execute)
/* mov eax,ecx; add eax,1; nop; nop; ret -- a seven-byte hookable entry. */
__declspec(allocate(".tfnhook")) const unsigned char fixture_code[] = {
    0x8b,0xc1,0x83,0xc0,0x01,0x90,0x90,0xc3
};
typedef int (*TargetFunction)(int);
__declspec(dllexport) volatile LONG fixture_result = 0;
__declspec(dllexport) volatile LONG fixture_calls = 0;

int main(void) {
    char name[180];
    DWORD pid=GetCurrentProcessId();
    HANDLE request,ready,resume;
    sprintf_s(name,sizeof(name),"Local\\CT2Trainer-Hook-%lu-request",(unsigned long)pid);
    request=CreateEventA(NULL,TRUE,FALSE,name);
    sprintf_s(name,sizeof(name),"Local\\CT2Trainer-Hook-%lu-ready",(unsigned long)pid);
    ready=CreateEventA(NULL,TRUE,FALSE,name);
    sprintf_s(name,sizeof(name),"Local\\CT2Trainer-Hook-%lu-resume",(unsigned long)pid);
    resume=CreateEventA(NULL,FALSE,FALSE,name);
    if (!request || !ready || !resume) return 2;
    printf("{\"pid\":%lu,\"entry\":%llu,\"result\":%llu,\"calls\":%llu}\n",
        (unsigned long)pid,(unsigned long long)(uintptr_t)fixture_code,
        (unsigned long long)(uintptr_t)&fixture_result,
        (unsigned long long)(uintptr_t)&fixture_calls);
    fflush(stdout);
    for (;;) {
        if (WaitForSingleObject(request,0)==WAIT_OBJECT_0) {
            /* This single caller is outside the code before acknowledging. */
            SetEvent(ready);
            if (WaitForSingleObject(resume,INFINITE)!=WAIT_OBJECT_0) return 3;
            ResetEvent(ready);
        }
        fixture_result=((TargetFunction)(uintptr_t)fixture_code)(3);
        InterlockedIncrement(&fixture_calls);
        Sleep(10);
    }
}
