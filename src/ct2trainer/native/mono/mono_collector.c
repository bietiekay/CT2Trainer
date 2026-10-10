/* Independently authored, bounded public-API Mono adapter draft. MIT.
 * This host owns one root domain and one source-pinned assembly until process
 * exit. Real game domain/unload observers and arbitrary signatures are excluded.
 * Native controller/source identity is supplied by the owned typed broker.
 */
#include "mono_collector.h"
#include "mono_api_redirect.h"
#include <string.h>
#include <stdio.h>
#define TF_SLOTS 64u
#define TF_OK 0
#define TF_BAD_SELECTOR 1
#define TF_NO_METHOD 2
#define TF_AMBIGUOUS 3
#define TF_STALE 4
#define TF_AFFINITY 5
#define TF_EXCEPTION 6
#define TF_QUOTA 7
#define TF_BAD_REFERENCE 8
#define TF_RUNTIME 9
#define TF_MAIN_ONLY 10
#define TF_EXPIRED 10
#define TF_UTF16_LIMIT 256u
static MonoDomain *g_domain;
static MonoAssembly *g_assembly;
static MonoImage *g_image;
static DWORD g_main;
static uint64_t g_main_created;
static uint32_t g_generation=1,g_methods_count,g_refs_count;
static volatile LONG g_attach_count,g_detach_count;
static int g_retired;
static SRWLOCK g_lock=SRWLOCK_INIT;
typedef struct tf_method { MonoMethod *method; uint32_t generation,instance,return_type,param_count; int main_only; } tf_method;
typedef struct tf_reference { uint32_t handle,generation; } tf_reference;
static tf_method g_methods[TF_SLOTS];
static tf_reference g_refs[TF_SLOTS];
static uint64_t tf_process_created(HANDLE process) {
 FILETIME a,b,c,d;
 if (!GetProcessTimes(process,&a,&b,&c,&d)) return 0;
 return ((uint64_t)a.dwHighDateTime<<32)|a.dwLowDateTime;
}
static int tf_admitted(const tf_mono_context *context) {
 LARGE_INTEGER now,frequency;
 return context&&context->owner&&context->request_id&&context->owner_created&&context->target_created&&context->target_pid==GetCurrentProcessId()&&
  context->target_created==tf_process_created(GetCurrentProcess())&&context->owner_created==tf_process_created(context->owner)&&
  WaitForSingleObject(context->owner,0)==WAIT_TIMEOUT&&
  QueryPerformanceFrequency(&frequency)&&frequency.QuadPart>0&&(uint64_t)frequency.QuadPart==context->qpc_frequency&&
  QueryPerformanceCounter(&now)&&now.QuadPart>0&&
  (uint64_t)now.QuadPart<context->deadline_qpc&&context->qpc_frequency<=UINT64_MAX/30u&&
  context->deadline_qpc-(uint64_t)now.QuadPart<=context->qpc_frequency*30u;
}
static int tf_api_check(const void *context) {return tf_admitted((const tf_mono_context *)context);}
static int tf_open_generic(const tf_mono_context *context,MonoMethod *method) {
 const MonoTableInfo *table=mono_image_get_table_info(g_image,MONO_TABLE_GENERICPARAM);
 int rows,index;uint32_t method_row=mono_method_get_token(method)&0x00ffffffu;
 uint32_t class_row=mono_class_get_type_token(mono_method_get_class(method))&0x00ffffffu;
 if (!table) return TF_RUNTIME;
 rows=mono_table_info_get_rows(table);if (rows<0||rows>4096) return TF_QUOTA;
 for (index=0;index<rows;++index) {
  uint32_t owner;if (!tf_admitted(context)) return TF_EXPIRED;
  owner=mono_metadata_decode_row_col(table,index,MONO_GENERICPARAM_OWNER);
  /* ECMA335 TypeOrMethodDef: low tag0 TypeDef,1 MethodDef; rest row. */
  if (((owner&1u)&&(owner>>1)==method_row)||(!(owner&1u)&&(owner>>1)==class_row)) return TF_BAD_SELECTOR;
 }
 return TF_OK;
}
static uint64_t tf_thread_created(void) {
 FILETIME a,b,c,d;
 if (!GetThreadTimes(GetCurrentThread(),&a,&b,&c,&d)) return 0;
 return ((uint64_t)a.dwHighDateTime<<32)|a.dwLowDateTime;
}
static int tf_text(const char text[64]) {
 uint32_t i;
 for (i=0;i<64;++i) {
  unsigned char c=(unsigned char)text[i];
  if (!c) { for (++i;i<64;++i) if (text[i]) return 0;return 1; }
  if (!(c>='a'&&c<='z')&&!(c>='A'&&c<='Z')&&!(c>='0'&&c<='9')&&c!='_'&&c!='.') return 0;
 }
 return 0;
}
static int tf_copy_name(char out[64],const char *name) {
 size_t length;
 if (!name) return 0;
 length=strnlen(name,64);if (length>=64) return 0;
 ZeroMemory(out,64);memcpy(out,name,length);return 1;
}
static MonoThread *tf_attach(void) {
 MonoThread *thread;
 /* An admitted context is not an initialized dynamic API table. Startup
  * failure or a call before bind must not dereference a null export. */
 if (!g_domain||!g_api.tf_thread_attach) return NULL;
 if (GetCurrentThreadId()==g_main) return NULL;
 thread=mono_thread_attach(g_domain);
 if (thread) InterlockedIncrement(&g_attach_count);
 return thread;
}
static void tf_detach(MonoThread *thread) {
 if (thread) { mono_thread_detach(thread);InterlockedIncrement(&g_detach_count); }
}
static int tf_live(void) {
 return !g_retired&&g_domain&&g_assembly&&g_image&&mono_domain_get_by_id(mono_domain_get_id(g_domain))==g_domain&&
        !mono_domain_is_unloading(g_domain)&&mono_assembly_get_image(g_assembly)==g_image;
}
static tf_method *tf_method_from_token(uint64_t token) {
 uint32_t generation=(uint32_t)(token>>32),index=(uint32_t)token;
 if (!index||index>g_methods_count||generation!=g_generation||g_methods[index-1].generation!=generation) return NULL;
 return &g_methods[index-1];
}
static MonoObject *tf_object_from_reference(uint64_t reference) {
 uint32_t generation=(uint32_t)(reference>>32),index=(uint32_t)reference;
 if (!index||index>g_refs_count||generation!=g_generation||g_refs[index-1].generation!=generation) return NULL;
 return mono_gchandle_get_target(g_refs[index-1].handle);
}
static int tf_keep_reference(MonoObject *object,uint64_t *reference) {
 uint32_t handle;
 if (!object||g_refs_count>=TF_SLOTS) return TF_QUOTA;
 /* This small owned profile pins at most64 bounded fixture objects/exceptions.
  * Arbitrary object graphs and unrestricted reference-return methods are excluded. */
 handle=mono_gchandle_new(object,1);if (!handle) return TF_RUNTIME;
 g_refs[g_refs_count].handle=handle;g_refs[g_refs_count].generation=g_generation;
 ++g_refs_count;*reference=((uint64_t)g_generation<<32)|g_refs_count;return TF_OK;
}
/* Trusted first-party host entry only: caller owns a callback-free root domain,
 * already-loaded source-bound assembly, and no-runtime-cleanup lifetime through
 * target exit. C pointers below are never accepted from wire/Lua/JSON. */
int tf_mono_bind_existing(const tf_mono_context *context,HMODULE module,
                          void *owned_root,void *owned_assembly) {
 tf_mono_api selected;MonoDomain *root;MonoAssembly *assembly=(MonoAssembly *)owned_assembly;
 MonoImage *image;int status=TF_RUNTIME;
 if (!tf_admitted(context)||!module||!owned_root||!assembly) return TF_EXPIRED;
 AcquireSRWLockExclusive(&g_lock);
 if (g_domain||g_retired) goto end;
 if (!tf_mono_api_select(module,&selected,tf_api_check,context)) {
  if (!tf_admitted(context)) status=TF_EXPIRED;goto end;
 }
 /* API selection queries current-process module/code only, never loads Mono. */
 if (!tf_admitted(context)) {tf_mono_api_discard(&selected);status=TF_EXPIRED;goto end;}
 root=selected.tf_get_root_domain();
 if (!root||root!=(MonoDomain *)owned_root||selected.tf_domain_is_unloading(root)||
     selected.tf_domain_get_by_id(selected.tf_domain_get_id(root))!=root) {
  tf_mono_api_discard(&selected);goto end;
 }
 /* Domain ID0 is a valid root. Calling into Mono requires this source-owned
  * entry thread to have been attached by its existing host initialization. */
 image=selected.tf_assembly_get_image(assembly);
 if (!image||!tf_admitted(context)) {tf_mono_api_discard(&selected);goto end;}
 g_main=GetCurrentThreadId();g_main_created=tf_thread_created();
 if (!g_main_created) {tf_mono_api_discard(&selected);goto end;}
 if (!tf_admitted(context)) {tf_mono_api_discard(&selected);status=TF_EXPIRED;goto end;}
 g_api=selected;g_domain=root;g_assembly=assembly;g_image=image;status=TF_OK;
end:
 ReleaseSRWLockExclusive(&g_lock);return status;
}
int tf_mono_find(const tf_mono_context *context,const tf_mono_selector *selector,uint64_t *token) {
 MonoThread *thread;MonoClass *klass;MonoMethod *method,*found=NULL;void *iter=NULL;uint32_t scanned=0,matches=0,index;
 const char *assembly_name;int status=TF_NO_METHOD;
 if (!tf_admitted(context)) return TF_EXPIRED;
 if (!selector||!token||selector->generation!=g_generation||selector->instance>1||selector->parameter_count>1||
     (selector->return_type!=MONO_TYPE_VOID&&selector->return_type!=MONO_TYPE_BOOLEAN&&selector->return_type!=MONO_TYPE_I4&&
      selector->return_type!=MONO_TYPE_CLASS&&selector->return_type!=MONO_TYPE_OBJECT)||
     (selector->parameter_count&&selector->parameter_types[0]!=MONO_TYPE_BOOLEAN&&selector->parameter_types[0]!=MONO_TYPE_I4)||
     !tf_text(selector->assembly)||!tf_text(selector->image)||!tf_text(selector->name_space)||!tf_text(selector->class_name)||!tf_text(selector->method)) return TF_BAD_SELECTOR;
 for (index=selector->parameter_count;index<4;++index) if (selector->parameter_types[index]) return TF_BAD_SELECTOR;
 thread=tf_attach();if (GetCurrentThreadId()!=g_main&&!thread) return TF_RUNTIME;
 AcquireSRWLockExclusive(&g_lock);
 if (!tf_live()) { status=TF_STALE;goto end; }
 assembly_name=mono_assembly_name_get_name(mono_assembly_get_name(g_assembly));
 if (strcmp(selector->assembly,assembly_name)||strcmp(selector->image,mono_image_get_name(g_image))) { status=TF_BAD_SELECTOR;goto end; }
 klass=mono_class_from_name(g_image,selector->name_space,selector->class_name);if (!klass) goto end;
 while ((method=mono_class_get_methods(klass,&iter))!=NULL) {
  MonoMethodSignature *signature;void *param_iter=NULL;MonoType *param;uint32_t count=0;int same=1;
  if (!tf_admitted(context)) { status=TF_EXPIRED;goto end; }
  if (++scanned>4096) { status=TF_QUOTA;goto end; }
  if (strcmp(mono_method_get_name(method),selector->method)) continue;
  signature=mono_method_signature(method);if (!signature) continue;
  if (mono_signature_get_call_conv(signature)!=MONO_CALL_DEFAULT||mono_signature_explicit_this(signature)||
      mono_type_is_byref(mono_signature_get_return_type(signature))) continue;
  if ((uint32_t)mono_signature_is_instance(signature)!=selector->instance||mono_signature_get_param_count(signature)!=selector->parameter_count||
      (uint32_t)mono_type_get_type(mono_signature_get_return_type(signature))!=selector->return_type) continue;
  while ((param=mono_signature_get_params(signature,&param_iter))!=NULL) {
   if (mono_type_is_byref(param)||count>=selector->parameter_count||(uint32_t)mono_type_get_type(param)!=selector->parameter_types[count]) { same=0;break; }
   ++count;
  }
  if (same&&count==selector->parameter_count) { found=method;++matches; }
 }
 if (!tf_admitted(context)) { status=TF_EXPIRED;goto end; }
 if (!matches) goto end;if (matches!=1) { status=TF_AMBIGUOUS;goto end; }
 status=tf_open_generic(context,found);if (status!=TF_OK) goto end;
 for (index=0;index<g_methods_count;++index) if (g_methods[index].method==found&&g_methods[index].generation==g_generation) break;
 if (index==g_methods_count) {
  tf_method *slot;if (g_methods_count>=TF_SLOTS) { status=TF_QUOTA;goto end; }
  slot=&g_methods[g_methods_count++];slot->method=found;slot->generation=g_generation;slot->instance=selector->instance;
  slot->return_type=selector->return_type;slot->param_count=selector->parameter_count;
  /* Affinity comes from this owned source profile, never from a request flag. */
  slot->main_only=!strcmp(selector->name_space,"CT2TrainerOwned")&&!strcmp(selector->class_name,"Application")&&
                  !strcmp(selector->method,"set_runInBackground");
 }
 *token=((uint64_t)g_generation<<32)|(index+1u);status=TF_OK;
end:
 ReleaseSRWLockExclusive(&g_lock);tf_detach(thread);return status;
}
int tf_mono_get_jit(const tf_mono_context *context,uint64_t token,tf_mono_jit *result) {
 MonoThread *thread;tf_method *method;void *address;MonoJitInfo *info;int size,status=TF_STALE;
 if (!tf_admitted(context)) return TF_EXPIRED;
 if (!result) return TF_BAD_SELECTOR;
 thread=tf_attach();if (GetCurrentThreadId()!=g_main&&!thread) return TF_RUNTIME;
 AcquireSRWLockExclusive(&g_lock);
 method=tf_method_from_token(token);if (!tf_live()||!method) goto end;
 if (!tf_admitted(context)) { status=TF_EXPIRED;goto end; }
 address=mono_compile_method(method->method);if (!address) { status=TF_RUNTIME;goto end; }
 /* Compilation can have happened after admission. An expired return never
  * grants a live hook range and compiled code remains retained until exit. */
 if (!tf_admitted(context)) { status=TF_EXPIRED;goto end; }
 info=mono_jit_info_table_find(g_domain,address);if (!info||mono_jit_info_get_method(info)!=method->method) { status=TF_RUNTIME;goto end; }
 size=mono_jit_info_get_code_size(info);if (size<=0||size>1024*1024) { status=TF_QUOTA;goto end; }
 ZeroMemory(result,sizeof(*result));result->token=token;result->address=(uint64_t)(uintptr_t)mono_jit_info_get_code_start(info);
 result->size=(uint32_t)size;result->domain_id=(uint32_t)mono_domain_get_id(g_domain);
 memcpy(result->first_bytes,(void *)(uintptr_t)result->address,size<32?(size_t)size:32u);status=TF_OK;
end:
 ReleaseSRWLockExclusive(&g_lock);tf_detach(thread);return status;
}
int tf_mono_invoke(const tf_mono_context *context,uint64_t token,uint64_t receiver,int has_boolean,uint32_t boolean,
                   int32_t *scalar,uint64_t *reference,tf_mono_exception *exception_result) {
 MonoThread *thread;tf_method *method;MonoObject *receiver_object=NULL,*result,*exception=NULL;void *arguments[1];
 mono_bool bool_argument=(mono_bool)boolean;int status=TF_STALE;
 if (!tf_admitted(context)) return TF_EXPIRED;
 if (!scalar||!reference||!exception_result||boolean>1||has_boolean<0||has_boolean>1) return TF_BAD_SELECTOR;
 *scalar=0;*reference=0;ZeroMemory(exception_result,sizeof(*exception_result));
 thread=tf_attach();if (GetCurrentThreadId()!=g_main&&!thread) return TF_RUNTIME;
 AcquireSRWLockExclusive(&g_lock);
 method=tf_method_from_token(token);if (!tf_live()||!method) goto end;
 if (method->main_only&&(GetCurrentThreadId()!=g_main||tf_thread_created()!=g_main_created)) { status=TF_AFFINITY;goto end; }
 if (method->param_count!=(uint32_t)has_boolean) { status=TF_BAD_SELECTOR;goto end; }
 if (has_boolean) {
  void *iter=NULL;MonoType *parameter=mono_signature_get_params(mono_method_signature(method->method),&iter);
  if (!parameter||mono_type_get_type(parameter)!=MONO_TYPE_BOOLEAN) { status=TF_BAD_SELECTOR;goto end; }
 }
 if (method->instance) { receiver_object=tf_object_from_reference(receiver);if (!receiver_object) { status=TF_BAD_REFERENCE;goto end; }
  if (mono_object_get_class(receiver_object)!=mono_method_get_class(method->method)) { status=TF_BAD_REFERENCE;goto end; }
 } else if (receiver) { status=TF_BAD_REFERENCE;goto end; }
 arguments[0]=&bool_argument;
 if (!tf_admitted(context)) { status=TF_EXPIRED;goto end; }
 result=mono_runtime_invoke(method->method,receiver_object,has_boolean?arguments:NULL,&exception);
 if (exception) {
  MonoClass *klass=mono_object_get_class(exception);status=tf_keep_reference(exception,&exception_result->reference);
  if (status!=TF_OK) goto end;
  if (!tf_copy_name(exception_result->name_space,mono_class_get_namespace(klass))||!tf_copy_name(exception_result->class_name,mono_class_get_name(klass))) { status=TF_QUOTA;goto end; }
  status=TF_EXCEPTION;goto end;
 }
 switch (method->return_type) {
 case MONO_TYPE_VOID: status=TF_OK;break;
 case MONO_TYPE_I4:
  if (!result) { status=TF_RUNTIME;break; }
  memcpy(scalar,mono_object_unbox(result),4);status=TF_OK;break;
 case MONO_TYPE_BOOLEAN:
  if (!result) { status=TF_RUNTIME;break; }
  *scalar=*(uint8_t *)mono_object_unbox(result);status=TF_OK;break;
 case MONO_TYPE_CLASS: case MONO_TYPE_OBJECT:
  status=tf_keep_reference(result,reference);break;
 default:status=TF_BAD_SELECTOR;break;
 }
end:
 ReleaseSRWLockExclusive(&g_lock);tf_detach(thread);return status;
}
int tf_mono_reference_type(const tf_mono_context *context,uint64_t reference,char name_space[64],char name[64]) {
 MonoThread *thread;MonoObject *object;MonoClass *klass;int status=TF_BAD_REFERENCE;
 if (!tf_admitted(context)) return TF_EXPIRED;
 thread=tf_attach();if (GetCurrentThreadId()!=g_main&&!thread) return TF_RUNTIME;
 AcquireSRWLockExclusive(&g_lock);
 object=tf_live()?tf_object_from_reference(reference):NULL;
 if (object) { klass=mono_object_get_class(object);status=(tf_copy_name(name_space,mono_class_get_namespace(klass))&&tf_copy_name(name,mono_class_get_name(klass)))?TF_OK:TF_QUOTA; }
 ReleaseSRWLockExclusive(&g_lock);tf_detach(thread);return status;
}
void tf_mono_retire(void) { AcquireSRWLockExclusive(&g_lock);g_retired=1;++g_generation;ReleaseSRWLockExclusive(&g_lock); }
uint32_t tf_mono_generation(void) { return g_generation; }
uint32_t tf_mono_attach_count(void) { return (uint32_t)g_attach_count; }
uint32_t tf_mono_detach_count(void) { return (uint32_t)g_detach_count; }

int tf_mono_identity(char assembly[64],char image[64],uint32_t *domain_id) {
 if (GetCurrentThreadId()!=g_main||!tf_live()) return TF_STALE;
 if (!tf_copy_name(assembly,mono_assembly_name_get_name(mono_assembly_get_name(g_assembly)))||!tf_copy_name(image,mono_image_get_name(g_image))) return TF_QUOTA;
 *domain_id=(uint32_t)mono_domain_get_id(g_domain);return TF_OK;
}
int tf_mono_runtime(char version[128],wchar_t module_path[2048]) {
 char *build;HMODULE selected,module;FARPROC actual;size_t length;DWORD path_length;
 if (GetCurrentThreadId()!=g_main||!tf_live()) return TF_STALE;
 /* The import library can expose a controller-owned IAT thunk address.
  * Resolve the actual export inside this target's loaded Mono image first. */
 selected=g_api.module;if(!selected) return TF_RUNTIME;
 memcpy(&actual,&g_api.tf_runtime_invoke,sizeof(actual));if(!actual) return TF_RUNTIME;
 if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
     (LPCWSTR)(uintptr_t)(void *)actual,&module)||module!=selected) return TF_RUNTIME;
 path_length=GetModuleFileNameW(module,module_path,2048);if (!path_length||path_length>=2048) return TF_QUOTA;
 build=mono_get_runtime_build_info();if (!build) return TF_RUNTIME;
 length=strnlen(build,128);if(length>=128) {mono_free(build);return TF_QUOTA;}
 ZeroMemory(version,128);memcpy(version,build,length);mono_free(build);return TF_OK;
}
