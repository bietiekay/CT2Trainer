/* First-party own fixture only. Never part of a live target adapter. MIT. */
#ifndef TF_OWNED_MONO_BOOTSTRAP_H
#define TF_OWNED_MONO_BOOTSTRAP_H
#include "mono_collector.h"
int tf_owned_bootstrap(const tf_mono_context *context,const char *runtime_root,const char *assembly_path);
#endif
