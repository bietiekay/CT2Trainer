/* First-party fixed typed table derived from pinned MIT public prototypes. */
#ifndef TF_MONO_API_H
#define TF_MONO_API_H
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <mono/mini/jit.h>
#include <mono/metadata/assembly.h>
#include <mono/metadata/class.h>
#include <mono/metadata/loader.h>
#include <mono/metadata/threads.h>
#include <mono/metadata/object.h>
#include <mono/metadata/mono-config.h>
#include <mono/metadata/attrdefs.h>
#include <mono/metadata/mono-gc.h>
#include <mono/metadata/row-indexes.h>
typedef struct tf_mono_api {
 HMODULE module;
 uintptr_t image_begin,image_end;
 MonoImage * (__cdecl *tf_assembly_get_image)(MonoAssembly *assembly);
 MonoAssemblyName * (__cdecl *tf_assembly_get_name)(MonoAssembly *assembly);
 const char* (__cdecl *tf_assembly_name_get_name)(MonoAssemblyName *aname);
 MonoClass * (__cdecl *tf_class_from_name)(MonoImage *image, const char* name_space, const char *name);
 MonoMethod* (__cdecl *tf_class_get_methods)(MonoClass* klass, void **iter);
 const char* (__cdecl *tf_class_get_name)(MonoClass *klass);
 const char* (__cdecl *tf_class_get_namespace)(MonoClass *klass);
 uint32_t (__cdecl *tf_class_get_type_token)(MonoClass *klass);
 void* (__cdecl *tf_compile_method)(MonoMethod *method);
 MonoDomain * (__cdecl *tf_domain_get_by_id)(int32_t domainid);
 int32_t (__cdecl *tf_domain_get_id)(MonoDomain *domain);
 mono_bool (__cdecl *tf_domain_is_unloading)(MonoDomain *domain);
 void (__cdecl *tf_free)(void *);
 MonoObject* (__cdecl *tf_gchandle_get_target)(uint32_t gchandle);
 uint32_t (__cdecl *tf_gchandle_new)(MonoObject *obj, mono_bool pinned);
 MonoDomain* (__cdecl *tf_get_root_domain)(void);
 char* (__cdecl *tf_get_runtime_build_info)(void);
 const char* (__cdecl *tf_image_get_name)(MonoImage *image);
 const MonoTableInfo * (__cdecl *tf_image_get_table_info)(MonoImage *image, int table_id);
 int (__cdecl *tf_jit_info_get_code_size)(MonoJitInfo* ji);
 void* (__cdecl *tf_jit_info_get_code_start)(MonoJitInfo* ji);
 MonoMethod* (__cdecl *tf_jit_info_get_method)(MonoJitInfo* ji);
 MonoJitInfo * (__cdecl *tf_jit_info_table_find)(MonoDomain *domain, void* addr);
 uint32_t (__cdecl *tf_metadata_decode_row_col)(const MonoTableInfo *t, int idx, unsigned int col);
 MonoClass* (__cdecl *tf_method_get_class)(MonoMethod *method);
 const char* (__cdecl *tf_method_get_name)(MonoMethod *method);
 uint32_t (__cdecl *tf_method_get_token)(MonoMethod *method);
 MonoMethodSignature* (__cdecl *tf_method_signature)(MonoMethod *method);
 MonoClass* (__cdecl *tf_object_get_class)(MonoObject *obj);
 void* (__cdecl *tf_object_unbox)(MonoObject *obj);
 MonoObject* (__cdecl *tf_runtime_invoke)(MonoMethod *method, void *obj, void **params, MonoObject **exc);
 mono_bool (__cdecl *tf_signature_explicit_this)(MonoMethodSignature *sig);
 uint32_t (__cdecl *tf_signature_get_call_conv)(MonoMethodSignature *sig);
 uint32_t (__cdecl *tf_signature_get_param_count)(MonoMethodSignature *sig);
 MonoType* (__cdecl *tf_signature_get_params)(MonoMethodSignature *sig, void **iter);
 MonoType* (__cdecl *tf_signature_get_return_type)(MonoMethodSignature *sig);
 mono_bool (__cdecl *tf_signature_is_instance)(MonoMethodSignature *sig);
 int (__cdecl *tf_table_info_get_rows)(const MonoTableInfo *table);
 MonoThread * (__cdecl *tf_thread_attach)(MonoDomain *domain);
 void (__cdecl *tf_thread_detach)(MonoThread *thread);
 int (__cdecl *tf_type_get_type)(MonoType *type);
 mono_bool (__cdecl *tf_type_is_byref)(MonoType *type);
} tf_mono_api;
/* Existing current-process HMODULE only; no load/init/remote address input. */
/* Private synchronous C callback only; never Lua, wire or JSON authority. */
typedef int (__cdecl *tf_mono_api_checkpoint)(const void *context);
int tf_mono_api_select(HMODULE existing,tf_mono_api *out,
                       tf_mono_api_checkpoint check,const void *context);
/* Only discard an unpublished selection. Successful host bindings stay held
 * through process exit; module hold does not fence Mono runtime/domain cleanup. */
void tf_mono_api_discard(tf_mono_api *unpublished);
#endif
