/* First-party Windows typed export selection. MIT. No Mono import/loader/init. */
#include "mono_api.h"
#include <string.h>
static int tf_readable(uintptr_t address,size_t bytes,uintptr_t allocation) {
 MEMORY_BASIC_INFORMATION region;uintptr_t begin,end;DWORD protection;
 if (!address||!bytes||address>UINTPTR_MAX-bytes||
     !VirtualQuery((const void *)address,&region,sizeof(region))) return 0;
 begin=(uintptr_t)region.BaseAddress;
 if ((uintptr_t)region.AllocationBase!=allocation||region.State!=MEM_COMMIT||region.Type!=MEM_IMAGE||
     (region.Protect&(PAGE_GUARD|PAGE_NOACCESS))||begin>address||begin>UINTPTR_MAX-region.RegionSize) return 0;
 protection=region.Protect&0xffu;
 if (protection!=PAGE_READONLY&&protection!=PAGE_READWRITE&&protection!=PAGE_WRITECOPY&&
     protection!=PAGE_EXECUTE_READ&&protection!=PAGE_EXECUTE_READWRITE&&protection!=PAGE_EXECUTE_WRITECOPY) return 0;
 end=begin+region.RegionSize;return address+bytes<=end;
}
static int tf_image(HMODULE module,uintptr_t *begin,uintptr_t *end) {
 uintptr_t base=(uintptr_t)module,pe,optional;IMAGE_DOS_HEADER dos;IMAGE_FILE_HEADER coff;
 IMAGE_OPTIONAL_HEADER header;DWORD signature;
 if (!tf_readable(base,sizeof(dos),base)) return 0;
 memcpy(&dos,(const void *)base,sizeof(dos));
 if (dos.e_magic!=IMAGE_DOS_SIGNATURE||dos.e_lfanew<64||dos.e_lfanew>1024*1024||
     (dos.e_lfanew&3)||base>UINTPTR_MAX-(uintptr_t)dos.e_lfanew) return 0;
 pe=base+(uintptr_t)dos.e_lfanew;
 if (!tf_readable(pe,sizeof(signature)+sizeof(coff),base)) return 0;
 memcpy(&signature,(const void *)pe,sizeof(signature));
 memcpy(&coff,(const void *)(pe+sizeof(signature)),sizeof(coff));
 if (signature!=IMAGE_NT_SIGNATURE||coff.NumberOfSections==0||coff.NumberOfSections>96||
     coff.SizeOfOptionalHeader<sizeof(header)||coff.SizeOfOptionalHeader>4096) return 0;
#ifdef _WIN64
 if (coff.Machine!=IMAGE_FILE_MACHINE_AMD64) return 0;
#else
 if (coff.Machine!=IMAGE_FILE_MACHINE_I386) return 0;
#endif
 optional=pe+sizeof(signature)+sizeof(coff);
 if (!tf_readable(optional,sizeof(header),base)) return 0;
 memcpy(&header,(const void *)optional,sizeof(header));
#ifdef _WIN64
 if (header.Magic!=IMAGE_NT_OPTIONAL_HDR64_MAGIC) return 0;
#else
 if (header.Magic!=IMAGE_NT_OPTIONAL_HDR32_MAGIC) return 0;
#endif
 if (!header.SizeOfImage||header.SizeOfImage>1024u*1024u*1024u||header.SizeOfHeaders>header.SizeOfImage||
     (uint64_t)dos.e_lfanew+sizeof(signature)+sizeof(coff)+coff.SizeOfOptionalHeader>header.SizeOfHeaders||
     base>UINTPTR_MAX-header.SizeOfImage) return 0;
 *begin=base;*end=base+header.SizeOfImage;return 1;
}
static int tf_export(HMODULE module,const char *name,uintptr_t begin,uintptr_t end,FARPROC *out) {
 FARPROC address=GetProcAddress(module,name);MEMORY_BASIC_INFORMATION region;HMODULE actual;
 uintptr_t at=(uintptr_t)address;DWORD protection;
 if (!address||at<begin||at>=end||!VirtualQuery((const void *)at,&region,sizeof(region))||
     region.State!=MEM_COMMIT||region.Type!=MEM_IMAGE||(uintptr_t)region.AllocationBase!=begin||
     (region.Protect&(PAGE_GUARD|PAGE_NOACCESS))||
     !GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
       (LPCWSTR)at,&actual)||actual!=module) return 0;
 protection=region.Protect&0xffu;
 if (protection!=PAGE_EXECUTE&&protection!=PAGE_EXECUTE_READ&&
     protection!=PAGE_EXECUTE_READWRITE&&protection!=PAGE_EXECUTE_WRITECOPY) return 0;
 *out=address;return 1;
}
int tf_mono_api_select(HMODULE existing,tf_mono_api *out,
                       tf_mono_api_checkpoint check,const void *context) {
 HMODULE held=NULL;tf_mono_api next;FARPROC address;char *version;size_t length;
 if (!out) return 0;
 ZeroMemory(out,sizeof(*out));ZeroMemory(&next,sizeof(next));
 /* Hold only an already loaded exact address. This is not LoadLibrary and
  * no caller-supplied module filename/search path is used. */
 if (!check||!check(context)||!existing||!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS,(LPCWSTR)existing,&held)) return 0;
 if (!check(context)||held!=existing||!tf_image(held,&next.image_begin,&next.image_end)) goto fail;
 next.module=held;
 /* Every export is a direct executable address inside that same held image;
  * forwarded functions and data exports never become callable table entries. */
 if (!check(context)||!tf_export(held,"mono_assembly_get_image",next.image_begin,next.image_end,&address)) goto fail;
 memcpy(&next.tf_assembly_get_image,&address,sizeof(next.tf_assembly_get_image));
 if (!check(context)||!tf_export(held,"mono_assembly_get_name",next.image_begin,next.image_end,&address)) goto fail;
 memcpy(&next.tf_assembly_get_name,&address,sizeof(next.tf_assembly_get_name));
 if (!check(context)||!tf_export(held,"mono_assembly_name_get_name",next.image_begin,next.image_end,&address)) goto fail;
 memcpy(&next.tf_assembly_name_get_name,&address,sizeof(next.tf_assembly_name_get_name));
 if (!check(context)||!tf_export(held,"mono_class_from_name",next.image_begin,next.image_end,&address)) goto fail;
 memcpy(&next.tf_class_from_name,&address,sizeof(next.tf_class_from_name));
 if (!check(context)||!tf_export(held,"mono_class_get_methods",next.image_begin,next.image_end,&address)) goto fail;
 memcpy(&next.tf_class_get_methods,&address,sizeof(next.tf_class_get_methods));
 if (!check(context)||!tf_export(held,"mono_class_get_name",next.image_begin,next.image_end,&address)) goto fail;
 memcpy(&next.tf_class_get_name,&address,sizeof(next.tf_class_get_name));
 if (!check(context)||!tf_export(held,"mono_class_get_namespace",next.image_begin,next.image_end,&address)) goto fail;
 memcpy(&next.tf_class_get_namespace,&address,sizeof(next.tf_class_get_namespace));
 if (!check(context)||!tf_export(held,"mono_class_get_type_token",next.image_begin,next.image_end,&address)) goto fail;
 memcpy(&next.tf_class_get_type_token,&address,sizeof(next.tf_class_get_type_token));
 if (!check(context)||!tf_export(held,"mono_compile_method",next.image_begin,next.image_end,&address)) goto fail;
 memcpy(&next.tf_compile_method,&address,sizeof(next.tf_compile_method));
 if (!check(context)||!tf_export(held,"mono_domain_get_by_id",next.image_begin,next.image_end,&address)) goto fail;
 memcpy(&next.tf_domain_get_by_id,&address,sizeof(next.tf_domain_get_by_id));
 if (!check(context)||!tf_export(held,"mono_domain_get_id",next.image_begin,next.image_end,&address)) goto fail;
 memcpy(&next.tf_domain_get_id,&address,sizeof(next.tf_domain_get_id));
 if (!check(context)||!tf_export(held,"mono_domain_is_unloading",next.image_begin,next.image_end,&address)) goto fail;
 memcpy(&next.tf_domain_is_unloading,&address,sizeof(next.tf_domain_is_unloading));
 if (!check(context)||!tf_export(held,"mono_free",next.image_begin,next.image_end,&address)) goto fail;
 memcpy(&next.tf_free,&address,sizeof(next.tf_free));
 if (!check(context)||!tf_export(held,"mono_gchandle_get_target",next.image_begin,next.image_end,&address)) goto fail;
 memcpy(&next.tf_gchandle_get_target,&address,sizeof(next.tf_gchandle_get_target));
 if (!check(context)||!tf_export(held,"mono_gchandle_new",next.image_begin,next.image_end,&address)) goto fail;
 memcpy(&next.tf_gchandle_new,&address,sizeof(next.tf_gchandle_new));
 if (!check(context)||!tf_export(held,"mono_get_root_domain",next.image_begin,next.image_end,&address)) goto fail;
 memcpy(&next.tf_get_root_domain,&address,sizeof(next.tf_get_root_domain));
 if (!check(context)||!tf_export(held,"mono_get_runtime_build_info",next.image_begin,next.image_end,&address)) goto fail;
 memcpy(&next.tf_get_runtime_build_info,&address,sizeof(next.tf_get_runtime_build_info));
 if (!check(context)||!tf_export(held,"mono_image_get_name",next.image_begin,next.image_end,&address)) goto fail;
 memcpy(&next.tf_image_get_name,&address,sizeof(next.tf_image_get_name));
 if (!check(context)||!tf_export(held,"mono_image_get_table_info",next.image_begin,next.image_end,&address)) goto fail;
 memcpy(&next.tf_image_get_table_info,&address,sizeof(next.tf_image_get_table_info));
 if (!check(context)||!tf_export(held,"mono_jit_info_get_code_size",next.image_begin,next.image_end,&address)) goto fail;
 memcpy(&next.tf_jit_info_get_code_size,&address,sizeof(next.tf_jit_info_get_code_size));
 if (!check(context)||!tf_export(held,"mono_jit_info_get_code_start",next.image_begin,next.image_end,&address)) goto fail;
 memcpy(&next.tf_jit_info_get_code_start,&address,sizeof(next.tf_jit_info_get_code_start));
 if (!check(context)||!tf_export(held,"mono_jit_info_get_method",next.image_begin,next.image_end,&address)) goto fail;
 memcpy(&next.tf_jit_info_get_method,&address,sizeof(next.tf_jit_info_get_method));
 if (!check(context)||!tf_export(held,"mono_jit_info_table_find",next.image_begin,next.image_end,&address)) goto fail;
 memcpy(&next.tf_jit_info_table_find,&address,sizeof(next.tf_jit_info_table_find));
 if (!check(context)||!tf_export(held,"mono_metadata_decode_row_col",next.image_begin,next.image_end,&address)) goto fail;
 memcpy(&next.tf_metadata_decode_row_col,&address,sizeof(next.tf_metadata_decode_row_col));
 if (!check(context)||!tf_export(held,"mono_method_get_class",next.image_begin,next.image_end,&address)) goto fail;
 memcpy(&next.tf_method_get_class,&address,sizeof(next.tf_method_get_class));
 if (!check(context)||!tf_export(held,"mono_method_get_name",next.image_begin,next.image_end,&address)) goto fail;
 memcpy(&next.tf_method_get_name,&address,sizeof(next.tf_method_get_name));
 if (!check(context)||!tf_export(held,"mono_method_get_token",next.image_begin,next.image_end,&address)) goto fail;
 memcpy(&next.tf_method_get_token,&address,sizeof(next.tf_method_get_token));
 if (!check(context)||!tf_export(held,"mono_method_signature",next.image_begin,next.image_end,&address)) goto fail;
 memcpy(&next.tf_method_signature,&address,sizeof(next.tf_method_signature));
 if (!check(context)||!tf_export(held,"mono_object_get_class",next.image_begin,next.image_end,&address)) goto fail;
 memcpy(&next.tf_object_get_class,&address,sizeof(next.tf_object_get_class));
 if (!check(context)||!tf_export(held,"mono_object_unbox",next.image_begin,next.image_end,&address)) goto fail;
 memcpy(&next.tf_object_unbox,&address,sizeof(next.tf_object_unbox));
 if (!check(context)||!tf_export(held,"mono_runtime_invoke",next.image_begin,next.image_end,&address)) goto fail;
 memcpy(&next.tf_runtime_invoke,&address,sizeof(next.tf_runtime_invoke));
 if (!check(context)||!tf_export(held,"mono_signature_explicit_this",next.image_begin,next.image_end,&address)) goto fail;
 memcpy(&next.tf_signature_explicit_this,&address,sizeof(next.tf_signature_explicit_this));
 if (!check(context)||!tf_export(held,"mono_signature_get_call_conv",next.image_begin,next.image_end,&address)) goto fail;
 memcpy(&next.tf_signature_get_call_conv,&address,sizeof(next.tf_signature_get_call_conv));
 if (!check(context)||!tf_export(held,"mono_signature_get_param_count",next.image_begin,next.image_end,&address)) goto fail;
 memcpy(&next.tf_signature_get_param_count,&address,sizeof(next.tf_signature_get_param_count));
 if (!check(context)||!tf_export(held,"mono_signature_get_params",next.image_begin,next.image_end,&address)) goto fail;
 memcpy(&next.tf_signature_get_params,&address,sizeof(next.tf_signature_get_params));
 if (!check(context)||!tf_export(held,"mono_signature_get_return_type",next.image_begin,next.image_end,&address)) goto fail;
 memcpy(&next.tf_signature_get_return_type,&address,sizeof(next.tf_signature_get_return_type));
 if (!check(context)||!tf_export(held,"mono_signature_is_instance",next.image_begin,next.image_end,&address)) goto fail;
 memcpy(&next.tf_signature_is_instance,&address,sizeof(next.tf_signature_is_instance));
 if (!check(context)||!tf_export(held,"mono_table_info_get_rows",next.image_begin,next.image_end,&address)) goto fail;
 memcpy(&next.tf_table_info_get_rows,&address,sizeof(next.tf_table_info_get_rows));
 if (!check(context)||!tf_export(held,"mono_thread_attach",next.image_begin,next.image_end,&address)) goto fail;
 memcpy(&next.tf_thread_attach,&address,sizeof(next.tf_thread_attach));
 if (!check(context)||!tf_export(held,"mono_thread_detach",next.image_begin,next.image_end,&address)) goto fail;
 memcpy(&next.tf_thread_detach,&address,sizeof(next.tf_thread_detach));
 if (!check(context)||!tf_export(held,"mono_type_get_type",next.image_begin,next.image_end,&address)) goto fail;
 memcpy(&next.tf_type_get_type,&address,sizeof(next.tf_type_get_type));
 if (!check(context)||!tf_export(held,"mono_type_is_byref",next.image_begin,next.image_end,&address)) goto fail;
 memcpy(&next.tf_type_is_byref,&address,sizeof(next.tf_type_is_byref));
 if (!check(context)) goto fail;
 version=next.tf_get_runtime_build_info();if (!version) goto fail;
 if (!check(context)) {next.tf_free(version);goto fail;}
 length=strnlen(version,128);
 /* Version text is an ABI family check only. The trusted caller still must
  * bind exact approved image/source/target hash, not trust this string alone. */
 if (length>=128||length<7||strncmp(version,"6.12.0 ",7)!=0) {
  next.tf_free(version);goto fail;
 }
 next.tf_free(version);
 if (!check(context)) goto fail;
 *out=next;return 1;
fail:
 FreeLibrary(held);return 0;
}
void tf_mono_api_discard(tf_mono_api *unpublished) {
 HMODULE owned;
 if (!unpublished) return;
 owned=unpublished->module;ZeroMemory(unpublished,sizeof(*unpublished));
 if (owned) FreeLibrary(owned);
}
