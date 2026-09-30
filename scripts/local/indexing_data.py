#!/usr/bin/env python3
"""Current own-data evidence, hashes only; never rewrites an original row or baseline."""
import collections
import datetime
import json
import re
import sys
from manage import RESULTS
from verify import sql, docker_exec

BASELINE = RESULTS / 'data-before.json'

def ident(value):
    if not re.fullmatch(r'[a-z][a-z0-9_]*', value):
        raise ValueError('Unexpected schema identifier')
    return '`' + value + '`'

def mysql_rows(table, columns):
    expression = "CONCAT_WS('|'," + ','.join("IFNULL(HEX(" + ident(c) + "),'NULL')" for c in columns) + ')'
    return dict(collections.Counter(sql('SELECT SHA2(' + expression + ',256) FROM ' + ident(table) + ';').splitlines()))

SQLITE = r'''
import collections,hashlib,json,pathlib,sqlite3
root=pathlib.Path('/app/db_data'); out={}
for p in sorted(root.rglob('*')):
    if not p.is_file() or p.is_symlink() or p.suffix not in ('.db','.sqlite3'): continue
    c=sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True)
    tables={}
    for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        if not t.replace('_','').isalnum(): raise ValueError('Unexpected table')
        cols=[r[1] for r in c.execute('PRAGMA table_info("'+t+'")')]
        rows=collections.Counter(hashlib.sha256(json.dumps(r,default=str,ensure_ascii=False,separators=(',',':')).encode()).hexdigest() for r in c.execute('SELECT '+','.join('"'+x+'"' for x in cols)+' FROM "'+t+'"'))
        tables[t]={'columns':cols,'rows':dict(rows)}
    c.close();out[str(p.relative_to(root))]=tables
print(json.dumps(out))
'''

FILES = r'''
import hashlib,json,pathlib
root=pathlib.Path('/app/be-local-data/objects')
print(json.dumps({str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file() and not p.is_symlink()}))
'''

def current():
    tables = {}
    for table in sql('SHOW TABLES;').splitlines():
        columns = [r.split('\t')[0] for r in sql('SHOW COLUMNS FROM ' + ident(table) + ';').splitlines()]
        tables[table] = {'columns': columns, 'rows': mysql_rows(table, columns)}
    return {'observed_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'tables': tables, 'sqlite': json.loads(docker_exec('ai', ['python', '-c', SQLITE])),
            'objects': json.loads(docker_exec('ai', ['python', '-c', FILES]))}

def before():
    if BASELINE.exists():
        raise RuntimeError('Baseline exists; never overwrite it')
    data = current()
    BASELINE.write_text(json.dumps(data, indent=2) + '\n')
    print(json.dumps({'mysql_tables': len(data['tables']), 'mysql_rows': sum(sum(t['rows'].values()) for t in data['tables'].values()),
                      'sqlite_rows': sum(sum(t['rows'].values()) for f in data['sqlite'].values() for t in f.values()), 'objects': len(data['objects'])}))

def after():
    original = json.loads(BASELINE.read_text()); checks = []
    def compare(name, old, new):
        missing = sum(max(0, count-new.get(digest, 0)) for digest, count in old.items())
        checks.append({'name': name, 'original_rows': sum(old.values()), 'missing_or_changed': missing, 'status': 'FAIL' if missing else 'PASS'})
    for name, table in original['tables'].items():
        compare('mysql.'+name, table['rows'], mysql_rows(name, table['columns']))
    # Existing SQLite schemas are additive only; select original columns even after migrations.
    spec = json.dumps({p: {t: d['columns'] for t,d in tables.items()} for p,tables in original['sqlite'].items()})
    script = "import collections,hashlib,json,pathlib,sqlite3\nspec=json.loads("+repr(spec)+")\nout={}\nfor p,tables in spec.items():\n c=sqlite3.connect('file:/app/db_data/'+p+'?mode=ro',uri=True);out[p]={}\n for t,cols in tables.items():\n  out[p][t]=dict(collections.Counter(hashlib.sha256(json.dumps(r,default=str,ensure_ascii=False,separators=(',',':')).encode()).hexdigest() for r in c.execute('SELECT '+','.join(chr(34)+x+chr(34) for x in cols)+' FROM '+chr(34)+t+chr(34))))\n c.close()\nprint(json.dumps(out))"
    actual = json.loads(docker_exec('ai', ['python','-c',script]))
    for path,tables in original['sqlite'].items():
        for name,table in tables.items(): compare(path+'.'+name,table['rows'],actual[path][name])
    files = json.loads(docker_exec('ai', ['python','-c',FILES]))
    changed = [name for name,digest in original['objects'].items() if files.get(name) != digest]
    checks.append({'name':'original_objects','original_files':len(original['objects']),'changed_files':changed,'status':'FAIL' if changed else 'PASS'})
    result = {'status':'PASS' if all(c['status']=='PASS' for c in checks) else 'FAIL','checks':checks}
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    (RESULTS/('data-preservation-'+stamp+'.json')).write_text(json.dumps(result,indent=2)+'\n')
    (RESULTS/'data-preservation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result));return result['status']!='PASS'

if __name__ == '__main__': sys.exit(before() if sys.argv[1]=='before' else after())
