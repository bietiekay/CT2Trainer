"""Source-only Mono adapter checks. Fake DLLs have no managed runtime/code."""
import ctypes,hashlib,io,json,os,re,struct,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PINS=json.loads((ROOT/'dependencies/native/mono-api-source/upstream-pins.json').read_text())
EXPORTS=json.loads((ROOT/'dependencies/native/mono-api-source/api-prototypes.json').read_text())['required_exports']
BUILD=Path(os.environ.get('CT2TRAINER_MONO_SOURCE_BUILD','missing-mono-source-build'))
FAKE=Path(os.environ.get('CT2TRAINER_MONO_FAKE_BUILD','missing-mono-fake-build'))
_BUILDS_AVAILABLE=(sys.platform=='win32' and (BUILD/'x64/CT2TrainerMonoExisting.dll').is_file() and (BUILD/'x86/CT2TrainerMonoExisting.dll').is_file() and all((FAKE/(n+'.dll')).is_file() for n in ('complete','missing','oldversion','forwarded','data','admission_probe')))
CHECK=ctypes.CFUNCTYPE(ctypes.c_int,ctypes.c_void_p)
class Api(ctypes.Structure):
 _fields_=[('module',ctypes.c_void_p),('image_begin',ctypes.c_size_t),('image_end',ctypes.c_size_t)]+[(p['field'],ctypes.c_void_p) for p in EXPORTS]
class Context(ctypes.Structure):
 _fields_=[('owner',ctypes.c_void_p)]+[(p,ctypes.c_uint64) for p in ('owner_created','target_created','deadline_qpc','qpc_frequency','request_id')]+[('target_pid',ctypes.c_uint32)]
if _BUILDS_AVAILABLE:
 ADAPTER=ctypes.CDLL(str(BUILD/'x64/CT2TrainerMonoExisting.dll'))
 ADAPTER.tf_mono_api_select.argtypes=(ctypes.c_void_p,ctypes.POINTER(Api),CHECK,ctypes.c_void_p)
 ADAPTER.tf_mono_api_select.restype=ctypes.c_int
 ADAPTER.tf_mono_api_discard.argtypes=(ctypes.POINTER(Api),)
 ADAPTER.tf_mono_bind_existing.argtypes=(ctypes.POINTER(Context),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p)
 ADAPTER.tf_mono_bind_existing.restype=ctypes.c_int
 ADAPTER.tf_mono_get_jit.argtypes=(ctypes.POINTER(Context),ctypes.c_uint64,ctypes.c_void_p)
 ADAPTER.tf_mono_get_jit.restype=ctypes.c_int
 PROBE=ctypes.CDLL(str(FAKE/'admission_probe.dll'))
 LIBS={name:ctypes.CDLL(str(FAKE/(name+'.dll'))) for name in ('complete','missing','oldversion','forwarded','data')}
 for lib in LIBS.values():
  lib.test_version_calls.restype=ctypes.c_uint;lib.test_free_calls.restype=ctypes.c_uint
  lib.test_live_buffers.restype=ctypes.c_uint;lib.test_bad_frees.restype=ctypes.c_uint
else:
 ADAPTER=None;LIBS={}

def imports(path):
 b=path.read_bytes();pe=struct.unpack_from('<I',b,60)[0];machine,count=struct.unpack_from('<HH',b,pe+4)
 optional_bytes=struct.unpack_from('<H',b,pe+20)[0];opt=pe+24;magic=struct.unpack_from('<H',b,opt)[0]
 directories=opt+(112 if magic==0x20b else 96);rva,size=struct.unpack_from('<II',b,directories+8)
 sections=[]
 for i in range(count):
  at=opt+optional_bytes+i*40;vsize,va,rawsize,raw=struct.unpack_from('<IIII',b,at+8);sections.append((va,rawsize,raw))
 def off(address):
  match=[raw+address-va for va,rawsize,raw in sections if va<=address<va+rawsize]
  assert len(match)==1 and 0<=match[0]<len(b);return match[0]
 result=[]
 if rva:
  for i in range(1024):
   d=struct.unpack_from('<IIIII',b,off(rva+i*20))
   if not any(d):break
   start=off(d[3]);end=b.find(b'\0',start,start+260);assert end>start
   result.append(b[start:end].decode('ascii'))
  else:raise AssertionError('Unbounded PE import table')
 return machine,result

class MonoSourceAdapterTests(unittest.TestCase):
 def setUp(self):
  for lib in LIBS.values():lib.test_reset()
 def tearDown(self):
  for name,lib in LIBS.items():
   self.assertEqual(lib.test_live_buffers(),0,name+' leaked query buffer')
   self.assertEqual(lib.test_bad_frees(),0,name+' invalid/double query free')
 def select(self,name,check=lambda opaque:1):
  out=Api();fn=CHECK(check);ok=ADAPTER.tf_mono_api_select(LIBS[name]._handle,ctypes.byref(out),fn,None)
  return ok,out
 def test_exact35_API_sources_and_license_patents_match_commit_blobs(self):
  self.assertEqual(PINS['headers_count'],35);self.assertEqual(len(PINS['files']),37)
  for e in PINS['files']:
   raw=(ROOT/'dependencies/native/mono-api-source/upstream'/e['path']).read_bytes()
   self.assertEqual(len(raw),e['bytes']);self.assertEqual(hashlib.sha256(raw).hexdigest(),e['sha256'])
   self.assertEqual(hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest(),e['git_blob'])
   self.assertEqual(e['commit'],'0cbf0e290c31adb476f9de0fa44b1d8829affa40')
 def test_fixed_API_table_derives_every_decl_from_selected_originals(self):
  headers='\n'.join((ROOT/'dependencies/native/mono-api-source/upstream'/e['path']).read_text() for e in PINS['files'] if e['path'] not in ('LICENSE','PATENTS.TXT'))
  headers=re.sub(r'/\*.*?\*/','',headers,flags=re.S);headers=re.sub(r'//[^\n]*','',headers)
  self.assertEqual(len(EXPORTS),42)
  for e in EXPORTS:
   match=re.search(r'\bMONO_API\s+([^;{}]*?\b'+re.escape(e['export'])+r'\s*\([^;{}]*\)\s*)\s*;',headers,re.S)
   self.assertIsNotNone(match);self.assertEqual(' '.join(match.group(1).replace('MONO_RT_EXTERNAL_ONLY','').split()),e['prototype'])
 @unittest.skipUnless(_BUILDS_AVAILABLE,'Explicit source/fake DLL build gate required; no Mono runtime is loaded')
 def test_x86_and_x64_compile_without_vendor_Mono_imports(self):
  for arch,machine in (('x86',0x14c),('x64',0x8664)):
   actual,names=imports(BUILD/arch/'CT2TrainerMonoExisting.dll')
   self.assertEqual(actual,machine);self.assertTrue(names);self.assertFalse(any('mono' in n.lower() for n in names),names)
 @unittest.skipUnless(_BUILDS_AVAILABLE,'Explicit source/fake DLL build gate required; no Mono runtime is loaded')
 def test_complete_fake_exports_bind_only_direct_code_in_held_image(self):
  ok,out=self.select('complete');self.assertEqual(ok,1)
  self.assertEqual(out.module,LIBS['complete']._handle);self.assertLess(out.image_begin,out.image_end)
  for e in EXPORTS:self.assertLessEqual(out.image_begin,getattr(out,e['field']));self.assertLess(getattr(out,e['field']),out.image_end)
  self.assertEqual(LIBS['complete'].test_version_calls(),1);self.assertEqual(LIBS['complete'].test_free_calls(),1)
  ADAPTER.tf_mono_api_discard(ctypes.byref(out));self.assertEqual(bytes(out),b'\0'*ctypes.sizeof(out))
 @unittest.skipUnless(_BUILDS_AVAILABLE,'Explicit source/fake DLL build gate required; no Mono runtime is loaded')
 def test_missing_export_leaves_no_partial_table_or_runtime_query(self):
  ok,out=self.select('missing');self.assertEqual(ok,0);self.assertEqual(bytes(out),b'\0'*ctypes.sizeof(out));self.assertEqual(LIBS['missing'].test_version_calls(),0)
 @unittest.skipUnless(_BUILDS_AVAILABLE,'Explicit source/fake DLL build gate required; no Mono runtime is loaded')
 def test_forwarded_function_is_not_admitted_from_another_module(self):
  ok,out=self.select('forwarded');self.assertEqual(ok,0);self.assertEqual(bytes(out),b'\0'*ctypes.sizeof(out));self.assertEqual(LIBS['forwarded'].test_version_calls(),0)
 @unittest.skipUnless(_BUILDS_AVAILABLE,'Explicit source/fake DLL build gate required; no Mono runtime is loaded')
 def test_data_export_is_not_callable_even_when_name_matches(self):
  ok,out=self.select('data');self.assertEqual(ok,0);self.assertEqual(bytes(out),b'\0'*ctypes.sizeof(out));self.assertEqual(LIBS['data'].test_version_calls(),0)

 @unittest.skipUnless(_BUILDS_AVAILABLE,'Explicit source/fake DLL build gate required; no Mono runtime is loaded')
 def test_execute_only_own_fake_header_page_is_refused_before_read(self):
  kernel=ctypes.WinDLL('kernel32',use_last_error=True)
  kernel.VirtualProtect.argtypes=(ctypes.c_void_p,ctypes.c_size_t,ctypes.c_uint32,ctypes.POINTER(ctypes.c_uint32))
  kernel.VirtualProtect.restype=ctypes.c_int
  old=ctypes.c_uint32();restored=ctypes.c_uint32()
  base=LIBS['complete']._handle
  self.assertTrue(kernel.VirtualProtect(base,4096,0x10,ctypes.byref(old)))
  try:
   ok,out=self.select('complete');self.assertEqual(ok,0);self.assertEqual(bytes(out),b'\0'*ctypes.sizeof(out))
   self.assertEqual(LIBS['complete'].test_version_calls(),0)
  finally:
   self.assertTrue(kernel.VirtualProtect(base,4096,old.value,ctypes.byref(restored)))
  self.assertEqual(restored.value,0x10)
 @unittest.skipUnless(_BUILDS_AVAILABLE,'Explicit source/fake DLL build gate required; no Mono runtime is loaded')
 def test_unsupported_version_frees_query_result_without_binding(self):
  ok,out=self.select('oldversion');self.assertEqual(ok,0);self.assertEqual(bytes(out),b'\0'*ctypes.sizeof(out));self.assertEqual(LIBS['oldversion'].test_version_calls(),1);self.assertEqual(LIBS['oldversion'].test_free_calls(),1)
 @unittest.skipUnless(_BUILDS_AVAILABLE,'Explicit source/fake DLL build gate required; no Mono runtime is loaded')
 def test_nonmodule_or_interior_module_address_is_refused(self):
  check=CHECK(lambda opaque:1)
  for address in (None,1,LIBS['complete']._handle+16):
   out=Api();self.assertEqual(ADAPTER.tf_mono_api_select(address,ctypes.byref(out),check,None),0);self.assertEqual(bytes(out),b'\0'*ctypes.sizeof(out))
  self.assertEqual(LIBS['complete'].test_version_calls(),0)
 @unittest.skipUnless(_BUILDS_AVAILABLE,'Explicit source/fake DLL build gate required; no Mono runtime is loaded')
 def test_no_checkpoint_cannot_admit_any_table(self):
  out=Api();self.assertEqual(ADAPTER.tf_mono_api_select(LIBS['complete']._handle,ctypes.byref(out),CHECK(),None),0);self.assertEqual(LIBS['complete'].test_version_calls(),0)
 @unittest.skipUnless(_BUILDS_AVAILABLE,'Explicit source/fake DLL build gate required; no Mono runtime is loaded')
 def test_expiry_during_export_resolution_stops_before_runtime_query(self):
  calls=[]
  def check(opaque):calls.append(1);return len(calls)<5
  ok,out=self.select('complete',check);self.assertEqual(ok,0);self.assertEqual(len(calls),5);self.assertEqual(LIBS['complete'].test_version_calls(),0);self.assertEqual(bytes(out),b'\0'*ctypes.sizeof(out))
 @unittest.skipUnless(_BUILDS_AVAILABLE,'Explicit source/fake DLL build gate required; no Mono runtime is loaded')
 def test_late_query_return_frees_owned_result_and_never_publishes_table(self):
  calls=[]
  def check(opaque):calls.append(1);return LIBS['complete'].test_version_calls()==0
  ok,out=self.select('complete',check);self.assertEqual(ok,0);self.assertEqual(LIBS['complete'].test_version_calls(),1);self.assertEqual(LIBS['complete'].test_free_calls(),1);self.assertEqual(bytes(out),b'\0'*ctypes.sizeof(out))
 @unittest.skipUnless(_BUILDS_AVAILABLE,'Explicit source/fake DLL build gate required; no Mono runtime is loaded')
 def test_late_query_cleanup_return_still_cannot_publish_table(self):
  def check(opaque):return LIBS['complete'].test_free_calls()==0
  ok,out=self.select('complete',check);self.assertEqual(ok,0);self.assertEqual(LIBS['complete'].test_version_calls(),1);self.assertEqual(LIBS['complete'].test_free_calls(),1);self.assertEqual(bytes(out),b'\0'*ctypes.sizeof(out))
 @unittest.skipUnless(_BUILDS_AVAILABLE,'Explicit source/fake DLL build gate required; no Mono runtime is loaded')
 def test_invalid_owner_context_is_denied_before_any_fake_runtime_api(self):
  ctx=Context();code=ADAPTER.tf_mono_bind_existing(ctypes.byref(ctx),LIBS['complete']._handle,1,1)
  self.assertEqual(code,10);self.assertEqual(LIBS['complete'].test_version_calls(),0)

 @unittest.skipUnless(_BUILDS_AVAILABLE,'Explicit source/fake DLL build gate required; no Mono runtime is loaded')
 def test_final_counter_observes_late_frequency_guard_return(self):
  self.assertEqual(PROBE.tf_test_late_frequency(),0)

 @unittest.skipUnless(_BUILDS_AVAILABLE,'Explicit source/fake DLL build gate required; no Mono runtime is loaded')
 def test_late_thread_identity_return_cannot_publish_existing_bind(self):
  self.assertEqual(PROBE.tf_test_late_bind(),10)
  self.assertEqual(PROBE.tf_test_bound(),0);self.assertEqual(PROBE.tf_test_discards(),1)

 @unittest.skipUnless(_BUILDS_AVAILABLE,'Explicit source/fake DLL build gate required; no Mono runtime is loaded')
 def test_admitted_jit_request_before_bind_refuses_without_null_call(self):
  kernel=ctypes.WinDLL('kernel32',use_last_error=True)
  kernel.GetCurrentProcess.restype=ctypes.c_void_p
  kernel.GetProcessTimes.argtypes=(ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p)
  kernel.QueryPerformanceFrequency.argtypes=(ctypes.POINTER(ctypes.c_int64),)
  kernel.QueryPerformanceCounter.argtypes=(ctypes.POINTER(ctypes.c_int64),)
  times=[ctypes.c_uint64() for _ in range(4)]
  owner=kernel.GetCurrentProcess()
  self.assertTrue(kernel.GetProcessTimes(owner,*[ctypes.byref(t) for t in times]))
  frequency=ctypes.c_int64();now=ctypes.c_int64()
  self.assertTrue(kernel.QueryPerformanceFrequency(ctypes.byref(frequency)))
  self.assertTrue(kernel.QueryPerformanceCounter(ctypes.byref(now)))
  context=Context(owner,times[0].value,times[0].value,now.value+frequency.value*30,frequency.value,1,kernel.GetCurrentProcessId())
  result=(ctypes.c_ubyte*56)()
  self.assertEqual(ADAPTER.tf_mono_get_jit(ctypes.byref(context),1,result),9)
  for lib in LIBS.values():self.assertEqual(lib.test_version_calls(),0)

if __name__=='__main__':
 unittest.main()


class MonoSourceAdoptionClosureTests(unittest.TestCase):
 def build_module(self):
  import importlib.util
  spec=importlib.util.spec_from_file_location('mono_adoption_native_build',ROOT/'tools/native_build.py')
  module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  return module
 def expected(self):
  dependencies={('dependencies/native/mono-api-source/upstream/'+e['path']) for e in PINS['files']}
  dependencies.update('dependencies/native/mono-api-source/'+n for n in ('api-prototypes.json','LICENSE.txt','LOCAL-CHANGES.md','README.md','upstream-pins.json'))
  component={'src/ct2trainer/native/mono/'+n for n in ('mono_api.c','mono_api.h','mono_api_redirect.h','mono_collector.c','mono_collector.h')}
  fixture={'tests/windows/mono_fixture/'+n for n in ('Build-FakeMonoExports.ps1','Build-MonoSources.ps1','Build-OwnedMonoFixture.ps1','mono_fixture_host.c','owned_fixture_bootstrap.c','owned_fixture_bootstrap.h','OwnedManagedFixture.cs','README.md')}
  fixture.update('tests/windows/mono_fixture/fake_exports/'+n for n in ('admission_probe.c','complete.c','data.c','forwarded.c','forwarded.def','missing.c','oldversion.c'))
  return dependencies|component|fixture
 def temporary_tree(self):
  import tempfile
  temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
  root=Path(temporary.name)
  for name in self.expected():
   target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/name).read_bytes())
  return root
 def test_source_allowlist_exact64_closure_without_duplicate_license(self):
  build=self.build_module();names=[p.relative_to(ROOT).as_posix() for p in build.source_files()]
  selected={n for n in names if n.startswith(('dependencies/native/mono-api-source/','src/ct2trainer/native/mono/','tests/windows/mono_fixture/'))}
  self.assertEqual(selected,self.expected());self.assertEqual(len(selected),62)
  self.assertEqual(names.count('tests/test_native_mono_sources.py'),1)
  self.assertNotIn('licenses/MONO-API-SOURCE-LICENSE.txt',names)
  self.assertEqual(len(selected)+1+1,64)
  original=(ROOT/'dependencies/native/mono-api-source/LICENSE.txt').read_bytes()
  self.assertEqual((ROOT/'licenses/MONO-API-SOURCE-LICENSE.txt').read_bytes(),original)
 def test_unlisted_runtime_def_sdk_and_fixture_helpers_are_not_exported(self):
  build=self.build_module();root=self.temporary_tree();build.ROOT=root
  unwanted=('dependencies/native/mono-api-source/mono.dll','dependencies/native/mono-api-source/runtime.lib','dependencies/native/mono-api-source/extra.def','dependencies/native/mono-api-source/upstream/unselected.h','src/ct2trainer/native/mono/unselected.c','src/ct2trainer/native/mono/other.py','tests/windows/mono_fixture/fake_exports/other.def','tests/windows/mono_fixture/unselected.c','tests/windows/mono_fixture/extra.py','tests/windows/mono_fixture/MonoFixture.exe')
  for name in unwanted:
   p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'unselected source/runtime fixture')
  names={p.relative_to(root).as_posix() for p in build.source_files()}
  self.assertTrue(self.expected()<=names)
  self.assertTrue(set(unwanted).isdisjoint(names))
 def test_missing_named_forwarder_opcode_and_component_refuse_partial_export(self):
  build=self.build_module()
  for name in ('tests/windows/mono_fixture/fake_exports/forwarded.def','dependencies/native/mono-api-source/upstream/mono/cil/opcode.def','src/ct2trainer/native/mono/mono_api_redirect.h'):
   with self.subTest(name=name):
    root=self.temporary_tree();build.ROOT=root;(root/name).unlink()
    with self.assertRaisesRegex(ValueError,'Required selected Mono source input missing'):
     build.source_files()
 def test_exact_notice_is_copied_once_and_mismatch_refuses_before_output(self):
  import tempfile
  build=self.build_module()
  with tempfile.TemporaryDirectory() as temporary:
   output=Path(temporary);build._copy_mono_notice(output)
   self.assertEqual([p.name for p in output.iterdir()],['MONO-API-SOURCE-LICENSE.txt'])
   self.assertEqual((output/'MONO-API-SOURCE-LICENSE.txt').read_bytes(),(ROOT/'dependencies/native/mono-api-source/LICENSE.txt').read_bytes())
  root=self.temporary_tree();build.ROOT=root
  retained=root/'licenses/MONO-API-SOURCE-LICENSE.txt';retained.parent.mkdir();retained.write_bytes(b'changed license')
  out=root/'notices';out.mkdir()
  with self.assertRaisesRegex(ValueError,'differs from its pinned original'):
   build._copy_mono_notice(out)
  self.assertEqual(list(out.iterdir()),[])

