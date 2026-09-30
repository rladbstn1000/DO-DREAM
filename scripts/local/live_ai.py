#!/usr/bin/env python3
"""Explicit sequential live session; templates/preflight make zero provider requests.

Approval is supplied by the human. This tool never creates an authorized manifest.
Only the AI service gets the two fixed read-only files. No live broker consumer.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import uuid
import manage
import scope_guard

ROOT = manage.ROOT
sys.path.insert(0, str(ROOT))
LIVE = ROOT / '.local/phase5/live'
MANIFEST = LIVE / 'manifest.json'
SESSION = LIVE / 'session.json'
KEY_FILE = Path.home() / '.config/dodream/provider-live.env'
LEDGER = '/app/db_data/live_ai/budget.sqlite3'
SPEC = 'openai-text-embedding-3-small-1536-l2-content-v1'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(value, code):
    if not value:
        raise RuntimeError(code)


def contract_digest():
    digestor=hashlib.sha256()
    paths=set()
    for directory in ('ai/app','ai/tests','be/src','fe-web/src','fe-web/tests','scripts/local','scripts/evaluation'):
        paths.update((ROOT/directory).rglob('*'))
    paths.update(ROOT/name for name in ('compose.local.yml','compose.live.yml','ai/Dockerfile.local','ai/requirements.local.lock.txt','be/Dockerfile.local','fe-web/Dockerfile.local','fe-web/package-lock.json'))
    for path in sorted(paths):
        if path.is_file() and not path.is_symlink() and '__pycache__' not in path.parts and path.name!='.DS_Store':
            digestor.update(str(path.relative_to(ROOT)).encode()+b'\0'+path.read_bytes())
    return digestor.hexdigest()


def provider_contract():
    sys.path.insert(0, str(ROOT/'ai'))
    from app.providers.contract import load_manifest
    return load_manifest


def template():
    LIVE.mkdir(parents=True, exist_ok=True)
    data = {'schema_version':1, 'run_id':str(uuid.uuid4()), 'authorized':False,
        'approval_reference':'', 'expires_at':'2000-01-01T00:00:00Z',
        'models':{'embedding':'text-embedding-3-small','answer':'gpt-4.1-mini-2025-04-14','grading':'gpt-4.1-mini-2025-04-14'},
        'limits':{'max_requests':0,'max_cost_usd':'0','max_input_bytes':16384,'max_output_tokens':1024},
        'dataset_sha256':'', 'isolation':{'verified':False,'evidence_sha256':''},
        'allowed_roles':['api','worker','cli'], 'materials':[]}
    for path, content in ((LIVE/'manifest.template.json',json.dumps(data,indent=2)+'\n'),
                          (LIVE/'provider-live.env.example','# Copy to ~/.config/dodream/provider-live.env with mode 0600, then edit locally.\nOPENAI_API_KEY=\n')):
        if not path.exists():
            with path.open('x') as stream:
                os.chmod(path,0o600);stream.write(content)
    return {'status':'NOT_RUN','authorized':False,'provider_requests':0,'templates':str(LIVE),'existing_files_preserved':True}


def metadata_only_key():
    require(KEY_FILE.is_file() and not KEY_FILE.is_symlink() and KEY_FILE.resolve()==KEY_FILE, 'DEDICATED_KEY_FILE_REQUIRED')
    info=KEY_FILE.stat()
    require(stat.S_IMODE(info.st_mode)==0o600 and info.st_uid==os.getuid(),'DEDICATED_KEY_PERMISSIONS_REQUIRED')
    return {'exists':True,'mode':'0600','contents_read':False}


def preflight():
    require(os.environ.get('LIVE_API_AUTHORIZED')=='true','LIVE_NOT_AUTHORIZED')
    require(MANIFEST.is_file() and not MANIFEST.is_symlink(),'LIVE_MANIFEST_REQUIRED')
    manifest=provider_contract()(MANIFEST)
    metadata_only_key()
    # The immutable authored dataset and preparation receipt bind approval to
    # newly allocated records; a human-entered old material ID cannot bypass it.
    frozen=ROOT/'scripts/evaluation/phase5_data/freeze.json'
    freeze=json.loads(frozen.read_text())
    from scripts.evaluation.phase5 import load, validate, freeze as verify_freeze
    validate(load())
    require(verify_freeze()['dataset_sha256']==freeze['dataset_sha256'],'FROZEN_DATASET_MISMATCH')
    require(manifest.data['dataset_sha256']==freeze['dataset_sha256'],'FROZEN_DATASET_MISMATCH')
    prepared=json.loads((manage.RESULTS/'phase5-prepared.json').read_text())
    require(prepared.get('status')=='PASS' and prepared.get('dataset_sha256')==freeze['dataset_sha256'],'NEW_MATERIAL_PREPARATION_REQUIRED')
    actual={m['material_id']:m for m in prepared['materials']}
    for approved in manifest.data['materials']:
        found=actual.get(approved['material_id'])
        require(found is not None and all(found.get(k)==approved[k] for k in ('source_revision','source_hash','spec'))
            and set(approved['user_ids'])<=set(found['user_ids']), 'ONLY_NEW_APPROVED_SYNTHETIC_RECORDS')
    evidence=manage.RESULTS/'live-offline-contract.json'
    require(evidence.is_file() and digest(evidence)==manifest.data['isolation']['evidence_sha256'],'OFFLINE_EVIDENCE_REQUIRED')
    report=json.loads(evidence.read_text())
    from verify_student_web import app_digest
    require(report.get('status')=='PASS' and report.get('application_source_sha256')==app_digest() and report.get('contract_source_sha256')==contract_digest(),'OFFLINE_EVIDENCE_STALE')
    require(manifest.data['isolation']['verified'] is True,'ISOLATION_REQUIRED')
    return manifest


def owned():
    scope_guard.gate(['config','--quiet'],manage.compose_base(),ROOT,manage.clean_env(),manage.RESULTS)
    return {r['service']:r for r in scope_guard.read_metadata(manage.clean_env()) if r['project']==manage.PROJECT}


def require_tested_images(rows):
    """Bind the running app and the AI tag to the images in offline evidence."""
    report=json.loads((manage.RESULTS/'live-offline-contract.json').read_text())
    expected=report.get('validated_image_ids',{})
    for service in ('ai','be','web'):
        require(service in rows and isinstance(expected.get(service),str)
            and expected[service].startswith('sha256:'),'TESTED_IMAGE_EVIDENCE_REQUIRED')
        actual=scope_guard._read(['docker','inspect','--format','{{.Image}}',rows[service]['id']],manage.clean_env()).strip()
        require(actual==expected[service],'RUNNING_IMAGE_NOT_TESTED')
    # Compose up resolves the tag again; a tested old container is insufficient.
    image=scope_guard._read(['docker','image','inspect','--format','{{.Id}}',rows['ai']['image_tag']],manage.clean_env()).strip()
    require(image==expected['ai'],'LIVE_IMAGE_TAG_NOT_TESTED')


def execute(name, arguments, live=False):
    base=manage.compose_base()
    if live:
        base += ['-f',str(ROOT/'compose.live.yml')]
        os.environ['DODREAM_LIVE_KEY_CONFIG']=str(KEY_FILE)
    scope_guard.gate(arguments,base,ROOT,manage.clean_env(),manage.RESULTS)
    result=manage.run(name,[*base,*arguments])
    require(result.returncode==0,'OWNED_SERVICE_OPERATION_FAILED')
    return result


def save_session(data):
    LIVE.mkdir(parents=True,exist_ok=True)
    data['updated_at']=datetime.now(timezone.utc).isoformat()
    temporary=LIVE/'session.next.json'
    with temporary.open('w') as stream:json.dump(data,stream,indent=2)
    os.replace(temporary,SESSION)


def open_session():
    manifest=preflight()
    if SESSION.exists():
        require(json.loads(SESSION.read_text()).get('state')=='CLOSED','LIVE_SESSION_ALREADY_OPEN')
    rows=owned()
    require(all(rows.get(s,{}).get('state')=='running' for s in ('be','ai','mysql','redis','chroma','web')),'PREPARED_LOCAL_APP_REQUIRED')
    require(not any(m['type']=='bind' for m in rows['ai']['mounts']),'LOCAL_AI_REQUIRED_BEFORE_OPEN')
    require_tested_images(rows)
    require(os.environ.get('DODREAM_RAG_VARIANT','A') in ('A','B'),'RAG_VARIANT_INVALID')
    data={'run_id':manifest.run_id,'manifest_sha256':manifest.digest,'state':'OPENING',
          'before':{s:{'id':rows[s]['id'],'state':rows[s]['state']} for s in ('ai','worker','index-dispatcher','web')}}
    save_session(data)
    try:
        execute('live-stop-local-consumers',['stop','worker','index-dispatcher','ai'])
        rows=owned()
        require(all(rows[s]['state']=='exited' for s in ('worker','index-dispatcher','ai')),'LOCAL_CONSUMERS_NOT_STOPPED')
        execute('live-ai-open',['up','-d','--no-deps','--wait','--wait-timeout','180','ai'],live=True)
        require_tested_images(owned())
        initialize="from app.providers.contract import load_manifest; from app.providers.budget import BudgetLedger; BudgetLedger.initialize('/app/db_data/live_ai/budget.sqlite3',load_manifest('/run/dodream-live/manifest.json')); print('Durable budget initialized; no provider request')"
        execute('live-budget-initialize',['exec','-T','ai','python','-c',initialize],live=True)
        execute('live-web-dns-refresh',['restart','web'])
        data['live_ai_id']=owned()['ai']['id']
        data['state']='OPEN';save_session(data)
    except Exception:
        data['state']='RECOVERY_REQUIRED';save_session(data)
        # Never silently leave the key-holding service callable after setup error.
        try:execute('live-open-failure-close',['stop','ai'])
        except Exception:pass
        raise
    return {'status':'OPEN','provider_requests_during_open':0,'run_id':manifest.run_id,'live_broker_consumers':0}


def close_session():
    require(SESSION.is_file(),'LIVE_SESSION_NOT_FOUND')
    data=json.loads(SESSION.read_text())
    if data['state']=='CLOSED':return {'status':'CLOSED','already_closed':True}
    rows=owned()
    # Closing requires no still-valid approval/key: revocation must remain possible.
    execute('live-ai-close',['stop','ai'])
    data['state']='LIVE_STOPPED_RESTORING';save_session(data)
    for service in ('worker','index-dispatcher'):
        require(rows[service]['id']==data['before'][service]['id'],'LOCAL_CONSUMER_ID_CHANGED')
    execute('local-ai-keyless-restore',['up','-d','--no-deps','--wait','--wait-timeout','180','ai'])
    rows=owned()
    require(not any(m['type']=='bind' for m in rows['ai']['mounts']) and set(rows['ai']['networks'])=={manage.PROJECT+'_default'},'KEYLESS_RESTORE_UNVERIFIED')
    for service in ('worker','index-dispatcher'):
        if data['before'][service]['state']=='running':execute('local-restore-'+service,['start',service])
    if data['before']['ai']['state']!='running':execute('local-ai-original-stop',['stop','ai'])
    if data['before']['web']['state']=='running':execute('local-web-dns-refresh',['restart','web'])
    data['state']='CLOSED';save_session(data)
    return {'status':'CLOSED','key_mounts_removed':True,'live_broker_consumers':0}


def run_job(job_id):
    manifest=preflight()
    require(str(uuid.UUID(job_id))==job_id,'CANONICAL_JOB_ID_REQUIRED')
    state=json.loads(SESSION.read_text())
    require(state['state']=='OPEN' and state['manifest_sha256']==manifest.digest,'MATCHING_OPEN_SESSION_REQUIRED')
    rows=owned()
    require(rows.get('ai',{}).get('id')==state.get('live_ai_id')
        and rows['ai']['state']=='running','LIVE_AI_ID_CHANGED')
    require(all(rows[s]['state']=='exited' for s in ('worker','index-dispatcher')),'LOCAL_CONSUMERS_MUST_STAY_STOPPED')
    execute('live-one-approved-job',['exec','-T','ai','python','-m','app.indexing.live_worker',job_id],live=True)
    return {'status':'CHECK_JOB_RESULT','job_id':job_id}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['template','preflight','open','close','job'])
    parser.add_argument('job_id',nargs='?')
    args=parser.parse_args()
    try:
        if args.command=='template':result=template()
        elif args.command=='preflight':result={'status':'READY','provider_requests':0,'run_id':preflight().run_id}
        elif args.command=='open':result=open_session()
        elif args.command=='close':result=close_session()
        else:require(args.job_id is not None,'JOB_ID_REQUIRED');result=run_job(args.job_id)
        print(json.dumps(result));return 0
    except Exception as error:
        # Only fixed safe codes; never expose provider bodies, credentials or config.
        code=str(error) if isinstance(error,RuntimeError) and str(error).replace('_','').isalnum() else type(error).__name__
        print(json.dumps({'status':'BLOCKED','reason':code,'provider_requests_started_by_this_command':0 if args.command in ('template','preflight') else 'not_asserted'}))
        return 2

if __name__=='__main__':raise SystemExit(main())
