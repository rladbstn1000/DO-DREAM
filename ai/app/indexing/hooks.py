"""Bounded file-only local faults for explicitly marked new synthetic snapshots."""
import json
import os
from pathlib import Path
import socket
import time
from app.config import APP_ENV, LOCAL_EXTERNAL_STUBS, LOCAL_PROVIDER_DATA_DIR, AI_MODE
from app.indexing.store import identity

GATES = frozenset(('after_partial','before_activation','after_activation','after_send','before_write'))
FAULTS = frozenset(('embedding_failure','missing_chunk','foreign_metadata','bad_dimension',
    'bad_vector','hash_mismatch','storage_timeout','partial_failure','extra_chunk','duplicate_batch','bad_stored_vector','bad_document','activation_rollback'))


def directory():
    return Path(LOCAL_PROVIDER_DATA_DIR).parent / 'indexing-controls'


def control(ctx):
    identity(ctx['job_id'])
    source = ctx.get('source_json', ctx.get('snapshot_json',''))
    if not (AI_MODE == 'LOCAL_FAKE' and LOCAL_EXTERNAL_STUBS and APP_ENV in ('local','test') and '[INDEX LOCAL]' in source):
        return {}
    path = directory() / (ctx['job_id']+'.json')
    if not path.exists():
        return {}
    if path.is_symlink() or path.stat().st_size > 1024:
        raise ValueError('INVALID_INDEX_CONTROL')
    value = json.loads(path.read_text())
    if not isinstance(value,dict) or set(value)-{'gate','fault','generation'}:
        raise ValueError('INVALID_INDEX_CONTROL')
    if value.get('gate') not in GATES | {None} or value.get('fault') not in FAULTS | {None}:
        raise ValueError('INVALID_INDEX_CONTROL')
    generation = value.get('generation',1)
    if type(generation) is not int or not 0 <= generation <= 3:
        raise ValueError('INVALID_INDEX_CONTROL')
    if ctx.get('generation',0) != generation and value.get('gate') != 'after_send':
        return {}
    return value


def event(ctx, name, **counts):
    source = ctx.get('source_json',ctx.get('snapshot_json',''))
    if not (AI_MODE == 'LOCAL_FAKE' and LOCAL_EXTERNAL_STUBS and APP_ENV in ('local','test') and '[INDEX LOCAL]' in source):
        return
    path = directory()
    path.mkdir(parents=True,exist_ok=True)
    row = {'event':name,'job_id':ctx['job_id'],'generation':ctx.get('generation',0),'time':time.time(),
           'pid':os.getpid(),'hostname':socket.gethostname()}
    if ctx.get('candidate'):
        row['candidate'] = ctx['candidate']
    row.update({key:value for key,value in counts.items() if type(value) in (int,bool)})
    with (path/(ctx['job_id']+'.events.jsonl')).open('a') as stream:
        stream.write(json.dumps(row,separators=(',',':'))+'\n')


def gate(ctx, name):
    event(ctx,name)
    if control(ctx).get('gate') != name:
        return
    release = directory()/(ctx['job_id']+'.'+name+'.release')
    deadline = time.monotonic()+(75 if name == 'before_write' else 45)
    while not release.is_file():
        if time.monotonic() >= deadline:
            raise TimeoutError('LOCAL_INDEX_GATE_TIMEOUT')
        time.sleep(.05)
