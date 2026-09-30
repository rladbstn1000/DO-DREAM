#!/usr/bin/env python3
"""Reuse the existing row/object baseline, adding read-only Chroma content hashes."""
import datetime
import json
import sys
from manage import RESULTS
from verify import docker_exec
import indexing_data

PHYSICAL = RESULTS / 'chroma-before.json'
PROBE = r"""
import hashlib,json
from app.indexing.chroma import client
c=client();result={}
for offset in range(0,10000,100):
 names=c.list_collections(limit=100,offset=offset)
 if not names:break
 for name in names:
  collection=c.get_collection(name=str(name),embedding_function=None)
  count=collection.count()
  if count>4096:raise RuntimeError('Original collection exceeds reviewed read bound')
  data=collection.get(include=['documents','metadatas','embeddings'])
  rows=sorted([[identity,data['documents'][n],data['metadatas'][n],[float(v) for v in data['embeddings'][n]]] for n,identity in enumerate(data['ids'])])
  digest=hashlib.sha256(json.dumps(rows,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
  result[str(name)]={'id':str(collection.id),'count':count,'sha256':digest}
else:raise RuntimeError('Collection inventory exceeds reviewed bound')
print(json.dumps(result))
"""

def physical():
    return json.loads(docker_exec('ai',['python','-c',PROBE]))

def main(mode):
    if mode=='before':
        if indexing_data.BASELINE.exists() or PHYSICAL.exists():
            raise RuntimeError('Original baselines already exist; never overwrite')
        data=indexing_data.current()
        collections=physical()
        # Collect everything before creating either immutable baseline.
        with indexing_data.BASELINE.open('x') as f:json.dump(data,f,indent=2)
        with PHYSICAL.open('x') as f:json.dump(collections,f,indent=2)
        summary={'mysql_tables':len(data['tables']),'mysql_rows':sum(sum(t['rows'].values()) for t in data['tables'].values()),
                 'sqlite_rows':sum(sum(t['rows'].values()) for tables in data['sqlite'].values() for t in tables.values()),
                 'objects':len(data['objects']),'collections':len(collections),'chunks':sum(v['count'] for v in collections.values())}
        print(json.dumps(summary));return 0
    if mode!='after':raise ValueError('Use before or after')
    rows_failed=indexing_data.after()
    old=json.loads(PHYSICAL.read_text());now=physical()
    changed=[name for name,entry in old.items() if now.get(name)!=entry]
    report={'status':'FAIL' if changed else 'PASS','original_collections':len(old),
            'original_chunks':sum(v['count'] for v in old.values()),'changed_or_missing':changed,
            'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    for path in (RESULTS/('chroma-preservation-'+stamp+'.json'),RESULTS/'chroma-preservation.json'):
        path.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report));return int(rows_failed or bool(changed))

if __name__=='__main__':raise SystemExit(main(sys.argv[1]))
