"""Repeatable static CT admission audit; never execute Lua or target writes."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from ct2trainer.native.compiler import compile_table


def audit(specification):
    if (type(specification) is not list or not 1 <= len(specification) <= 64
            or any(type(item) is not dict or set(item) != {'table', 'process'} for item in specification)):
        raise ValueError('Audit specification requires 1..64 table/process objects')
    reports=[]
    from ct2trainer.native.lua_host import LuaHost
    with patch.object(LuaHost,'execute',side_effect=AssertionError('Static audit attempted Lua execution')):
        for item in specification:
            path=Path(item['table']).resolve()
            before=hashlib.sha256(path.read_bytes()).hexdigest()
            plan=compile_table(path,item['process'])
            entries=plan['entries']
            reasons=Counter(entry['reason'] for entry in entries if not entry['supported'])
            after=hashlib.sha256(path.read_bytes()).hexdigest()
            if before != after or before != plan['table_sha256']:
                raise ValueError('CT changed during audit: '+str(path))
            reports.append({'file':path.name,'sha256':before,'process':item['process'],
                            'counts':plan['counts'],
                            'admitted_profiles':dict(Counter('lua' if 'lua_program' in row else
                                'assembly' if 'program' in row else
                                row.get('value_profile',{}).get('kind',row['kind'])
                                for row in entries if row['supported'] and row['kind'] != 'heading')),
                            'blocked_reasons':dict(reasons),
                            'blocked_records':[{'id':row['id'],'label':row['label'],'reason':row['reason']}
                                               for row in entries if not row['supported']],
                            'lua_bootstrap':plan.get('lua_bootstrap',{}).get('source_sha256'),
                            'runtime_verified':False})
    totals=Counter()
    for report in reports:totals.update(report['counts'])
    return {'schema':'ct2trainer-static-corpus-audit/v1','lua_executed':False,'remote_writes':False,
            'runtime_verified':False,'totals':dict(totals),'tables':reports}


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--spec',type=Path,required=True)
    cli.add_argument('--output',type=Path,required=True)
    args=cli.parse_args()
    result=audit(json.loads(args.spec.read_text(encoding='utf-8')))
    with args.output.open('x',encoding='utf-8') as stream:
        json.dump(result,stream,indent=2,ensure_ascii=True)
        stream.write('\n')
    print(json.dumps(result['totals'],sort_keys=True))


if __name__=='__main__':main()
