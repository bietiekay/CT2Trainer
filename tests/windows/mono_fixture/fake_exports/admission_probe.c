/* First-party deterministic clocks/private API stubs; no Mono runtime. */
#include "mono_api.h"
#include "mono_collector.h"
static LONGLONG test_now,test_frequency_work,test_thread_work;
static unsigned test_discard_count;
static unsigned char test_root,test_assembly,test_image;
static BOOL WINAPI test_qpf(LARGE_INTEGER *out) {out->QuadPart=1000;test_now+=test_frequency_work;return TRUE;}
static BOOL WINAPI test_qpc(LARGE_INTEGER *out) {out->QuadPart=test_now;return TRUE;}
static BOOL WINAPI test_thread_times(HANDLE thread,LPFILETIME a,LPFILETIME b,LPFILETIME c,LPFILETIME d) {
 BOOL result=GetThreadTimes(thread,a,b,c,d);test_now+=test_thread_work;return result;
}
static MonoDomain *test_get_root(void) {return (MonoDomain *)&test_root;}
static mono_bool test_unloading(MonoDomain *root) {(void)root;return 0;}
static int32_t test_domain_id(MonoDomain *root) {(void)root;return 0;}
static MonoDomain *test_domain_by_id(int32_t id) {(void)id;return (MonoDomain *)&test_root;}
static MonoImage *test_get_image(MonoAssembly *assembly) {(void)assembly;return (MonoImage *)&test_image;}
static int test_select(HMODULE module,tf_mono_api *out,tf_mono_api_checkpoint check,const void *context) {
 if (!check(context)) return 0;
 ZeroMemory(out,sizeof(*out));out->module=module;out->tf_get_root_domain=test_get_root;
 out->tf_domain_is_unloading=test_unloading;out->tf_domain_get_id=test_domain_id;
 out->tf_domain_get_by_id=test_domain_by_id;out->tf_assembly_get_image=test_get_image;return 1;
}
static void test_discard(tf_mono_api *out) {++test_discard_count;ZeroMemory(out,sizeof(*out));}
#define QueryPerformanceFrequency test_qpf
#define QueryPerformanceCounter test_qpc
#define GetThreadTimes test_thread_times
#define tf_mono_api_select test_select
#define tf_mono_api_discard test_discard
#include "mono_collector.c"
static tf_mono_context test_context(void) {
 tf_mono_context context;ZeroMemory(&context,sizeof(context));context.owner=GetCurrentProcess();
 context.owner_created=tf_process_created(context.owner);context.target_created=context.owner_created;
 context.target_pid=GetCurrentProcessId();context.qpc_frequency=1000;context.request_id=1;context.deadline_qpc=2000;
 return context;
}
__declspec(dllexport) int tf_test_late_frequency(void) {
 tf_mono_context context=test_context();test_now=1000;test_frequency_work=1000;
 return tf_admitted(&context);
}
__declspec(dllexport) int tf_test_late_bind(void) {
 tf_mono_context context=test_context();test_now=1000;test_frequency_work=0;test_thread_work=1000;
 test_discard_count=0;g_domain=NULL;g_assembly=NULL;g_image=NULL;g_main=0;g_retired=0;ZeroMemory(&g_api,sizeof(g_api));
 return tf_mono_bind_existing(&context,(HMODULE)(uintptr_t)1,&test_root,&test_assembly);
}
__declspec(dllexport) unsigned tf_test_bound(void) {return g_domain!=NULL;}
__declspec(dllexport) unsigned tf_test_discards(void) {return test_discard_count;}
