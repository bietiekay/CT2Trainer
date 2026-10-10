/* First-party fake exports for C boundary tests; not Mono or a runtime. */
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
static unsigned version_calls,free_calls,bad_frees;
static void *query_buffer;
__declspec(dllexport) unsigned test_version_calls(void){return version_calls;}
__declspec(dllexport) unsigned test_free_calls(void){return free_calls;}
__declspec(dllexport) unsigned test_live_buffers(void){return query_buffer!=NULL;}
__declspec(dllexport) unsigned test_bad_frees(void){return bad_frees;}
__declspec(dllexport) void test_reset(void){version_calls=free_calls=bad_frees=0;}
__declspec(dllexport) void *mono_assembly_get_image(void){return 0;}
__declspec(dllexport) void *mono_assembly_get_name(void){return 0;}
__declspec(dllexport) void *mono_assembly_name_get_name(void){return 0;}
__declspec(dllexport) void *mono_class_from_name(void){return 0;}
__declspec(dllexport) void *mono_class_get_methods(void){return 0;}
__declspec(dllexport) void *mono_class_get_name(void){return 0;}
__declspec(dllexport) void *mono_class_get_namespace(void){return 0;}
__declspec(dllexport) void *mono_class_get_type_token(void){return 0;}
__declspec(dllexport) void *mono_compile_method(void){return 0;}
__declspec(dllexport) void *mono_domain_get_by_id(void){return 0;}
__declspec(dllexport) void *mono_domain_get_id(void){return 0;}
__declspec(dllexport) void *mono_domain_is_unloading(void){return 0;}
__declspec(dllexport) void mono_free(void *pointer){
 if(pointer&&pointer==query_buffer){query_buffer=NULL;++free_calls;free(pointer);}
 else{++bad_frees;}
}
__declspec(dllexport) void *mono_gchandle_get_target(void){return 0;}
__declspec(dllexport) void *mono_gchandle_new(void){return 0;}
__declspec(dllexport) void *mono_get_root_domain(void){return 0;}
__declspec(dllexport) char *mono_get_runtime_build_info(void){
 const char version[]="5.0.0 unsupported";
 if(query_buffer){++bad_frees;return NULL;}
 query_buffer=malloc(sizeof(version));if(!query_buffer)return NULL;
 memcpy(query_buffer,version,sizeof(version));++version_calls;return (char *)query_buffer;
}
__declspec(dllexport) void *mono_image_get_name(void){return 0;}
__declspec(dllexport) void *mono_image_get_table_info(void){return 0;}
__declspec(dllexport) void *mono_jit_info_get_code_size(void){return 0;}
__declspec(dllexport) void *mono_jit_info_get_code_start(void){return 0;}
__declspec(dllexport) void *mono_jit_info_get_method(void){return 0;}
__declspec(dllexport) void *mono_jit_info_table_find(void){return 0;}
__declspec(dllexport) void *mono_metadata_decode_row_col(void){return 0;}
__declspec(dllexport) void *mono_method_get_class(void){return 0;}
__declspec(dllexport) void *mono_method_get_name(void){return 0;}
__declspec(dllexport) void *mono_method_get_token(void){return 0;}
__declspec(dllexport) void *mono_method_signature(void){return 0;}
__declspec(dllexport) void *mono_object_get_class(void){return 0;}
__declspec(dllexport) void *mono_object_unbox(void){return 0;}
__declspec(dllexport) void *mono_runtime_invoke(void){return 0;}
__declspec(dllexport) void *mono_signature_explicit_this(void){return 0;}
__declspec(dllexport) void *mono_signature_get_call_conv(void){return 0;}
__declspec(dllexport) void *mono_signature_get_param_count(void){return 0;}
__declspec(dllexport) void *mono_signature_get_params(void){return 0;}
__declspec(dllexport) void *mono_signature_get_return_type(void){return 0;}
__declspec(dllexport) void *mono_signature_is_instance(void){return 0;}
__declspec(dllexport) void *mono_table_info_get_rows(void){return 0;}
__declspec(dllexport) void *mono_thread_attach(void){return 0;}
__declspec(dllexport) void *mono_thread_detach(void){return 0;}
__declspec(dllexport) void *mono_type_get_type(void){return 0;}
__declspec(dllexport) void *mono_type_is_byref(void){return 0;}
