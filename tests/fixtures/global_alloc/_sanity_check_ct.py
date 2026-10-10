"""One-shot sanity check for the global_alloc fixture CTs (lane-local, not a test)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'src'))
from ct2trainer.native.compiler import compile_table

for arch, ct in (('x64', 'global_alloc_x64.ct'), ('x86', 'global_alloc_x86.ct')):
    path = Path(__file__).resolve().parent / ct
    plan = compile_table(path, 'NativeGlobalFixture.exe', architecture=arch)
    print('==', arch, ct)
    for e in plan['entries']:
        print('  id', e['id'], 'kind', e['kind'], 'supported', e['supported'],
              'reason', e['reason'][:60], 'provides', e.get('provides'),
              'requires', e.get('requires'), 'deps', e.get('dependency_ids'))
    e1 = plan['entries'][0]
    gp = e1.get('global_program', {})
    print('  globals', [(g['name'], g['size'], g['near'], g['initializer'], g['initializer_present']) for g in gp.get('globals', [])])
    print('  consumer_shape', gp.get('consumer_shape'))
    print('  requires', gp.get('requires'), 'provides', gp.get('provides'))
    import hashlib, json
    def canonical(v):
        return json.dumps(v, sort_keys=True, separators=(',', ':'),
                          ensure_ascii=False, allow_nan=False).encode('utf-8')
    print('  plan_fingerprint', hashlib.sha256(canonical({k: v for k, v in plan.items()
                                                            if k not in {'title', 'source_name'}})).hexdigest())
    print('  ct_sha256', hashlib.sha256(path.read_bytes()).hexdigest())
    print('  plan_sha256_full', hashlib.sha256(canonical(plan)).hexdigest())
