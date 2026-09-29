#!/usr/bin/env python3
"""Phase 3-A own-DB evidence: hashes only; existing rows never exported or rewritten."""
import hashlib,json,re,sys
from pathlib import Path
from verify import sql,docker_exec
from manage import RESULTS
BASELINE=RESULTS/'data-before.json'

def ident(name):
    if not re.fullmatch(r'[a-z][a-z0-9_]*',name):raise ValueError('Unexpected schema identifier')
    return '`'+name+'`'

def digest(table,columns,limit=None,key="id"):
    expression="CONCAT_WS('|',"+','.join("IFNULL(HEX("+ident(c)+"),'NULL')" for c in columns)+')'
    where='' if limit is None else ' WHERE '+ident(key)+'<='+str(int(limit))
    rows=sql('SELECT '+ident(key)+',SHA2('+expression+',256) FROM '+ident(table)+where+' ORDER BY '+ident(key)+';')
    return dict(line.split('\t',1) for line in rows.splitlines())

def before():
    if BASELINE.exists():raise RuntimeError('Original data baseline already exists; will not overwrite')
    tables={}
    for table in sql('SHOW TABLES;').splitlines():
        if table=='phase1_persistence_probe':continue
        cols=[line.split('\t')[0] for line in sql('SHOW COLUMNS FROM '+ident(table)+';').splitlines()]
        key={'conversation':'conversation_id','message':'message_id'}.get(table,'id')
        rows=digest(table,cols,key=key)
        tables[table]={'columns':cols,'key':key,'max_id':max(map(int,rows),default=0),'rows':rows}
    rag=json.loads(docker_exec('ai',['python','-c',"import sqlite3,json,hashlib; c=sqlite3.connect('/app/db_data/rag.db'); print(json.dumps({t:{str(r[0]):hashlib.sha256(json.dumps(r,default=str).encode()).hexdigest() for r in c.execute('SELECT * FROM '+t+' ORDER BY id')} for t in ('chat_sessions','chat_messages','embedding_tasks')}))"]))
    BASELINE.write_text(json.dumps({'tables':tables,'rag':rag},indent=2)+'\n')
    print(json.dumps({'baseline_tables':len(tables),'baseline_rows':sum(len(t['rows']) for t in tables.values()),'rag_rows':sum(map(len,rag.values()))}))

def after():
    original=json.loads(BASELINE.read_text());checks=[]
    for name,t in original['tables'].items():
        current=digest(name,t['columns'],t['max_id'],t['key'])
        changed=[rid for rid,h in t['rows'].items() if current.get(rid)!=h]
        checks.append({'table':name,'status':'PASS' if not changed else 'FAIL','original_rows':len(t['rows']),'changed_ids':changed})
    rag=json.loads(docker_exec('ai',['python','-c',"import sqlite3,json,hashlib; c=sqlite3.connect('/app/db_data/rag.db'); print(json.dumps({t:{str(r[0]):hashlib.sha256(json.dumps(r,default=str).encode()).hexdigest() for r in c.execute('SELECT * FROM '+t+' ORDER BY id')} for t in ('chat_sessions','chat_messages','embedding_tasks')}))"]))
    for t,rows in original['rag'].items():
        changed=[rid for rid,h in rows.items() if rag.get(t,{}).get(rid)!=h]
        checks.append({'table':'rag.'+t,'status':'PASS' if not changed else 'FAIL','original_rows':len(rows),'changed_ids':changed})
    result={'checks':checks,'status':'PASS' if all(c['status']=='PASS' for c in checks) else 'FAIL'}
    (RESULTS/'data-preservation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
    return result['status']!='PASS'

if __name__=='__main__':sys.exit(before() if sys.argv[1]=='before' else after())
