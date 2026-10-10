/* First-party typed Mono collector draft. MIT. Public Mono API only. */
#ifndef TF_MONO_COLLECTOR_H
#define TF_MONO_COLLECTOR_H
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
/* Native-only context, constructed from a verified broker request. Never on
 * the wire and never accepted from Lua/JSON; borrowed owner handle remains
 * held by the broker for process lifetime. The original QPC deadline is kept. */
typedef struct tf_mono_context {
 HANDLE owner;
 uint64_t owner_created,target_created,deadline_qpc,qpc_frequency,request_id;
 uint32_t target_pid;
} tf_mono_context;
#pragma pack(push,1)
typedef struct tf_mono_selector {
 uint32_t generation, instance, return_type, parameter_count, parameter_types[4];
 char assembly[64], image[64], name_space[64], class_name[64], method[64];
} tf_mono_selector;
typedef struct tf_mono_jit {
 uint64_t token,address;
 uint32_t size,domain_id;
 uint8_t first_bytes[32];
} tf_mono_jit;
typedef struct tf_mono_exception {
 uint64_t reference;
 char name_space[64],class_name[64];
} tf_mono_exception;
#pragma pack(pop)
/* Private source-host registration, not a wire capability or runtime loader. */
int tf_mono_bind_existing(const tf_mono_context *context,HMODULE module,
                          void *owned_root,void *owned_assembly);
int tf_mono_find(const tf_mono_context *context,const tf_mono_selector *selector,uint64_t *token);
int tf_mono_get_jit(const tf_mono_context *context,uint64_t token,tf_mono_jit *result);
int tf_mono_invoke(const tf_mono_context *context,uint64_t token,uint64_t receiver,int has_boolean,uint32_t boolean,
                   int32_t *scalar,uint64_t *reference,tf_mono_exception *exception);
int tf_mono_reference_type(const tf_mono_context *context,uint64_t reference,char name_space[64],char name[64]);
int tf_mono_identity(char assembly[64],char image[64],uint32_t *domain_id);
int tf_mono_runtime(char version[128],wchar_t module_path[2048]);
void tf_mono_retire(void);
uint32_t tf_mono_generation(void);
uint32_t tf_mono_attach_count(void);
uint32_t tf_mono_detach_count(void);
#endif
