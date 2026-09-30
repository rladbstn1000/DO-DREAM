#!/usr/bin/env python3
"""New phase-4 synthetic regression fixture rows only; original records and objects remain intact."""
import json
from grading_fixtures import clone_material, literal
from verify import sql
from manage import RESULTS

def create():
    result={'authorization':{},'grading':{}}
    for row in sql("SELECT id,title FROM materials WHERE title LIKE '[AUTHZ LOCAL] %' AND deleted_at IS NULL;").splitlines():
        source,title=row.split('\t');suffix=title.removeprefix('[AUTHZ LOCAL] ')
        result['authorization'][suffix]=clone_material(int(source),'[AUTHZ 4] '+suffix,'phase4')
    for suffix in ('',' second'):
        source=sql("SELECT id FROM materials WHERE title="+literal('[GRADING LOCAL] phase3a'+suffix)+" AND deleted_at IS NULL;")
        if not source:raise RuntimeError('Known synthetic grading source missing')
        result['grading'][suffix.strip() or 'primary']=clone_material(int(source),'[GRADING LOCAL] phase4'+suffix,'phase4')
    (RESULTS/'index-fixture-ids.json').write_text(json.dumps(result,indent=2)+'\n')
    (RESULTS/'authorization-fixtures.json').write_text(json.dumps(result['authorization'],indent=2)+'\n')
    print(json.dumps(result))

if __name__=='__main__':create()
