/* First-party own fixture setup. Explicitly excluded from trainer/runtime DLL. */
#include "owned_fixture_bootstrap.h"
#include <mono/mini/jit.h>
#include <mono/metadata/assembly.h>
#include <mono/metadata/class.h>
#include <mono/metadata/mono-config.h>
#include <stdio.h>
int tf_owned_bootstrap(const tf_mono_context *context,const char *runtime_root,const char *assembly_path) {
 char lib[1024],etc[1024];HMODULE module;MonoDomain *domain;MonoAssembly *assembly;
 MonoClass *klass;MonoMethod *initialize;MonoObject *exception=NULL;
 /* Own fresh native host only. A pre-existing runtime is refused rather than
  * initialized for a second time; already-running hosts use collector bind. */
 if (!runtime_root||!assembly_path||mono_get_root_domain()) return 9;
 if (sprintf_s(lib,sizeof(lib),"%s/lib",runtime_root)<0||sprintf_s(etc,sizeof(etc),"%s/etc",runtime_root)<0) return 9;
 mono_set_dirs(lib,etc);mono_config_parse(NULL);
 domain=mono_jit_init_version("CT2TrainerOwnedMono","v4.0.30319");if (!domain) return 9;
 assembly=mono_domain_assembly_open(domain,assembly_path);if (!assembly) return 9;
 klass=mono_class_from_name(mono_assembly_get_image(assembly),"CT2TrainerOwned","Application");if (!klass) return 9;
 initialize=mono_class_get_method_from_name(klass,"Initialize",0);if (!initialize) return 9;
 mono_runtime_invoke(initialize,NULL,NULL,&exception);if (exception) return 6;
 module=GetModuleHandleW(L"mono-2.0-sgen.dll");if (!module) return 9;
 return tf_mono_bind_existing(context,module,domain,assembly);
}
