/* Owned actual-Mono acceptance; never loads OriginalLua/AA or a game. MIT. */
#include "mono_collector.h"
#include "owned_fixture_bootstrap.h"
#include <stdio.h>
#include <string.h>
static uint32_t g_checks,g_failed;
static void check(const char *name,int success) { ++g_checks;if (!success) ++g_failed;printf("{\"name\":\"%s\",\"passed\":%s}\n",name,success?"true":"false");fflush(stdout); }
static char g_assembly[64],g_image[64];
static tf_mono_context g_context;
static tf_mono_selector selector(const char *klass,const char *name,uint32_t instance,uint32_t type,uint32_t parameter) {
 tf_mono_selector s;ZeroMemory(&s,sizeof(s));s.generation=tf_mono_generation();s.instance=instance;s.return_type=type;
 s.parameter_count=parameter?1u:0u;s.parameter_types[0]=parameter;
 strcpy_s(s.assembly,64,g_assembly);strcpy_s(s.image,64,g_image);strcpy_s(s.name_space,64,"CT2TrainerOwned");
 strcpy_s(s.class_name,64,klass);strcpy_s(s.method,64,name);return s;
}
typedef struct worker_job { tf_mono_context context;uint64_t token,receiver;int boolean;int status;int32_t scalar;uint64_t reference;tf_mono_exception exception; } worker_job;
static DWORD WINAPI invoke_worker(void *opaque) {
 worker_job *job=(worker_job *)opaque;
 job->status=tf_mono_invoke(&job->context,job->token,job->receiver,job->boolean,(uint32_t)job->boolean,&job->scalar,&job->reference,&job->exception);return 0;
}
static int run_worker(worker_job *job) {
 HANDLE thread;job->context=g_context;thread=CreateThread(NULL,0,invoke_worker,job,0,NULL);if (!thread) return 0;
 if (WaitForSingleObject(thread,3000)!=WAIT_OBJECT_0) {
  /* Own fixture only: an unknown worker must not outlive its stack job.
   * Process exit retains every worker/code/reference until exact target exit.
   * A game adapter never gets this process-exit action. */
  check("worker-completion-uncertain",0);fflush(stdout);ExitProcess(9);
 }
 CloseHandle(thread);return 1;
}
static int invoke(uint64_t token,uint64_t receiver,int has_bool,uint32_t value,int32_t *scalar,uint64_t *ref,tf_mono_exception *ex) {
 return tf_mono_invoke(&g_context,token,receiver,has_bool,value,scalar,ref,ex);
}
int main(int argc,char **argv) {
 tf_mono_selector s;uint64_t setter=0,getter=0,int_add=0,bool_add=0,creator=0,instance_get=0,thrower=0,count=0,collect=0,ref=0,temp_ref=0;
 tf_mono_exception ex;int32_t scalar=0;tf_mono_jit jit;worker_job job;uint32_t domain=0;char ns[64],name[64];
 ZeroMemory(&jit,sizeof(jit));
 if (argc!=3) return 2;
 {FILETIME a,b,c,d;LARGE_INTEGER now,frequency;
  if (!GetProcessTimes(GetCurrentProcess(),&a,&b,&c,&d)||!QueryPerformanceCounter(&now)||!QueryPerformanceFrequency(&frequency)) return 2;
  g_context.owner=GetCurrentProcess();g_context.owner_created=((uint64_t)a.dwHighDateTime<<32)|a.dwLowDateTime;
  g_context.target_created=g_context.owner_created;g_context.target_pid=GetCurrentProcessId();
  g_context.qpc_frequency=(uint64_t)frequency.QuadPart;g_context.deadline_qpc=(uint64_t)now.QuadPart+20u*g_context.qpc_frequency;g_context.request_id=1;
 }
 check("actual-mono-root-and-owned-assembly",tf_owned_bootstrap(&g_context,argv[1],argv[2])==0);
 if (g_failed) return 3;
 {char version[128],utf8[4096];wchar_t module[2048];uint32_t i;
  check("actual-Mono-loaded-DLL-identity",tf_mono_runtime(version,module)==0);
  if (!WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,module,-1,utf8,sizeof(utf8),NULL,NULL)) return 8;
  printf("{\"runtime_build\":\"%s\",\"module_path_utf8_hex\":\"",version);
  for(i=0;utf8[i];++i)printf("%02x",(unsigned char)utf8[i]);printf("\"}\n");
 }
 /* Mono's root domain legitimately has ID0. Identity is bound by the held
  * domain pointer + mono_domain_get_by_id, not an assumed positive ID. */
 check("exact-assembly-image-domain",tf_mono_identity(g_assembly,g_image,&domain)==0&&!strcmp(g_assembly,"OwnedManagedFixture")&&!strcmp(g_image,"OwnedManagedFixture"));
 printf("{\"assembly\":\"%s\",\"image\":\"%s\",\"domain_id\":%lu,\"pointer_bits\":%u}\n",g_assembly,g_image,(unsigned long)domain,(unsigned int)(sizeof(void*)*8));
 s=selector("Application","set_runInBackground",0,1,2);check("find-static-void-Boolean",tf_mono_find(&g_context,&s,&setter)==0&&setter!=0);
 s=selector("Application","GetCurrentStatus",0,8,0);check("find-static-I4-noarg",tf_mono_find(&g_context,&s,&getter)==0&&getter!=setter);
 check("read-initial17",invoke(getter,0,0,0,&scalar,&temp_ref,&ex)==0&&scalar==17);
 check("JIT-public-info-owned-method",tf_mono_get_jit(&g_context,getter,&jit)==0&&jit.token==getter&&jit.address&&jit.size&&jit.size<=1048576&&jit.domain_id==domain);
 printf("{\"jit_address\":%llu,\"jit_size\":%lu,\"first_bytes\":\"",(unsigned long long)jit.address,(unsigned long)jit.size);
 {uint32_t i;for(i=0;i<(jit.size<32?jit.size:32);++i) printf("%02x",jit.first_bytes[i]);}printf("\"}\n");
 s=selector("Application","Add",0,8,8);check("exact-int-overload",tf_mono_find(&g_context,&s,&int_add)==0);
 s=selector("Application","Add",0,8,2);check("exact-bool-overload",tf_mono_find(&g_context,&s,&bool_add)==0&&bool_add!=int_add);
 check("bool-overload-not-first-name",invoke(bool_add,0,1,1,&scalar,&temp_ref,&ex)==0&&scalar==101);
 s=selector("Application","Ambiguous",0,1,0);check("ambiguous-generic-overloads-refused",tf_mono_find(&g_context,&s,&temp_ref)==3);
 s=selector("Application","SingleGeneric",0,1,0);check("open-single-generic-refused",tf_mono_find(&g_context,&s,&temp_ref)==1);
 s=selector("Application","RefBoolean",0,1,2);check("byref-Boolean-refused",tf_mono_find(&g_context,&s,&temp_ref)==2);
 s=selector("Application","Varargs",0,1,0);check("varargs-refused",tf_mono_find(&g_context,&s,&temp_ref)==2);
 s=selector("Application","GetCurrentStatus",0,8,0);strcpy_s(s.assembly,64,"ForeignAssembly");check("foreign-assembly-refused",tf_mono_find(&g_context,&s,&temp_ref)==1);
 s=selector("Application","GetCurrentStatus",0,8,0);strcpy_s(s.image,64,"ForeignImage");check("foreign-image-refused",tf_mono_find(&g_context,&s,&temp_ref)==1);
 s=selector("Application","GetCurrentStatus",0,8,0);memset(s.method,'x',64);check("unterminated-selector-refused",tf_mono_find(&g_context,&s,&temp_ref)==1);
 check("main-static-Boolean-call",invoke(setter,0,1,1,&scalar,&temp_ref,&ex)==0);
 ZeroMemory(&job,sizeof(job));job.token=getter;check("worker-attached-read19",run_worker(&job)&&job.status==0&&job.scalar==19);
 ZeroMemory(&job,sizeof(job));job.token=setter;job.boolean=1;check("worker-main-affinity-refused",run_worker(&job)&&job.status==5);
 s=selector("Application","CallCount",0,8,0);check("find-call-count",tf_mono_find(&g_context,&s,&count)==0);
 check("affinity-refusal-had-no-call",invoke(count,0,0,0,&scalar,&temp_ref,&ex)==0&&scalar==1);
 s=selector("Application","CreateCounter",0,18,0);check("find-owned-reference-factory",tf_mono_find(&g_context,&s,&creator)==0);
 check("create-pinned-reference",invoke(creator,0,0,0,&scalar,&ref,&ex)==0&&ref!=0);
 s=selector("Counter","GetCurrentStatus",1,8,0);check("find-instance-method",tf_mono_find(&g_context,&s,&instance_get)==0);
 ZeroMemory(&job,sizeof(job));job.token=instance_get;job.receiver=ref;check("typed-owned-receiver41",run_worker(&job)&&job.status==0&&job.scalar==41);
 check("unknown-receiver-refused",invoke(instance_get,((uint64_t)99<<32)|1,0,0,&scalar,&temp_ref,&ex)==8);
 s=selector("Application","Collect",0,1,0);check("find-owned-GC-vector",tf_mono_find(&g_context,&s,&collect)==0);
 check("owned-GC-call",invoke(collect,0,0,0,&scalar,&temp_ref,&ex)==0);
 check("pinned-reference-survives-GC",tf_mono_reference_type(&g_context,ref,ns,name)==0&&!strcmp(ns,"CT2TrainerOwned")&&!strcmp(name,"Counter"));
 s=selector("Application","ThrowAfterIncrement",0,1,0);check("find-owned-exception-call",tf_mono_find(&g_context,&s,&thrower)==0);
 check("typed-exception-reference",invoke(thrower,0,0,0,&scalar,&temp_ref,&ex)==6&&ex.reference&&!strcmp(ex.name_space,"System")&&!strcmp(ex.class_name,"InvalidOperationException"));
 check("exception-partial-effect-once",invoke(count,0,0,0,&scalar,&temp_ref,&ex)==0&&scalar==2);
 check("main-inverse-is-separate-one-shot",invoke(setter,0,1,0,&scalar,&temp_ref,&ex)==0);
 check("read-final17",invoke(getter,0,0,0,&scalar,&temp_ref,&ex)==0&&scalar==17);
 check("worker-attach-detach-balanced",tf_mono_attach_count()==3&&tf_mono_detach_count()==3);
 {tf_mono_context expired=g_context;uint64_t denied=0;expired.deadline_qpc=1;
  s=selector("Application","GetCurrentStatus",0,8,0);
  check("expired-lookup-before-Mono-refused",tf_mono_find(&expired,&s,&denied)==10&&!denied);
  check("expired-invocation-before-Mono-refused",tf_mono_invoke(&expired,setter,0,1,1,&scalar,&temp_ref,&ex)==10);
  check("expired-JIT-address-not-exposed",tf_mono_get_jit(&expired,getter,&jit)==10);
  check("expired-context-had-no-managed-call",invoke(count,0,0,0,&scalar,&temp_ref,&ex)==0&&scalar==3);
  expired=g_context;expired.owner_created=0;
  check("unknown-owner-creation-refused",tf_mono_find(&expired,&s,&denied)==10);
  expired=g_context;expired.deadline_qpc=UINT64_MAX;
  check("far-future-admission-refused",tf_mono_find(&expired,&s,&denied)==10);
 }
 tf_mono_retire();check("stale-domain-token-refused",invoke(getter,0,0,0,&scalar,&temp_ref,&ex)==4);
 check("generation-advanced-no-unload",tf_mono_generation()==2);
 printf("{\"schema\":\"ct2trainer-owned-mono-collector/v1\",\"checks\":%lu,\"failed\":%lu,\"attach\":%lu,\"detach\":%lu,\"retained_until_process_exit\":true,\"mono_runtime\":true,\"clr_fixture\":false}\n",(unsigned long)g_checks,(unsigned long)g_failed,(unsigned long)tf_mono_attach_count(),(unsigned long)tf_mono_detach_count());
 return g_failed?4:0;
}
