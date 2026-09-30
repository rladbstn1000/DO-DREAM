#!/usr/bin/env python3
"""Real local Spring→MySQL→Redis/Celery→Chroma verification; new synthetic data only."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from manage import RESULTS, ROOT, compose, compose_args, clean_env, crash_owned, pause_chroma, source_identity
from verify import ENV, BASE, req, payload, sql, docker_exec, NoRedirect
from grading_fixtures import clone_material, clone_statement, literal
from verify_grading import http

sys.modules.setdefault('verify_indexing',sys.modules[__name__])

STAMP=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8]
CHECKS=[]
SCENARIOS=('happy','publication','failure_preservation','corruption','source_versions','duplicates','restarts','delivery','late_worker','authorization','storage_failure','transport_timeout','schema','initial_pdf','bounded_recovery','browser')

def check(name, passed, detail=None):
    row={'name':name,'status':'PASS' if passed else 'FAIL','detail':detail}
    CHECKS.append(row)
    with (RESULTS/('indexing-progress-'+STAMP+'.jsonl')).open('a') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
    print(json.dumps(row,ensure_ascii=False),flush=True)
    if not passed:raise AssertionError(name)

def query(statement):
    value=sql(statement)
    return [json.loads(line) for line in value.splitlines()] if value else []

def wait(predicate, seconds=45, label='condition'):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        result=predicate()
        if result:return result
        time.sleep(.35)
    raise TimeoutError(label)

class Runner:
    def __init__(self):
        self.tokens={};self.users={};self.last_login=0;self.jobs=[];self.fixtures=[];self.processes=[];self.evidence=[]
        self.pool=ThreadPoolExecutor(max_workers=8)
        self.fixture_source=json.loads((RESULTS/'index-fixture-ids.json').read_text())['authorization']['editable']
    def initialize(self):
        for who in ('owner','shared','other','unshared'):
            teacher=who in ('owner','other')
            body={'email':'authz-'+who+'@local.dodream.invalid','password':ENV['LOCAL_TEACHER_PASSWORD']} if teacher else {'deviceId':'dodream-authz-'+who,'deviceSecret':ENV['LOCAL_STUDENT_SECRET']}
            # Health endpoints do not exercise Spring's reconnected Redis client.
            # After this suite's real broker outage, wait only for transient
            # dependency responses; authentication denials still fail immediately.
            deadline=time.monotonic()+25;statuses=[]
            while True:
                code,data,_,_=req('be','/api/auth/'+('teacher' if teacher else 'student')+'/login',body=body,timeout=5)
                statuses.append(code)
                if code not in (502,503,504) or time.monotonic()>=deadline:break
                time.sleep(.5)
            check('index_login_'+who,code==200 and isinstance(data,dict) and bool(data.get('accessToken')),{'http':code,'readinessStatuses':statuses})
            self.tokens[who]=data['accessToken'];self.users[who]=int(payload(data['accessToken'])['sub'])
        self.last_login=time.monotonic()
        actual=json.loads(docker_exec('ai',['python','-c',"import json,chromadb;from app.indexing.chroma import client;from app.celery_config import celery_app;print(json.dumps({'client':chromadb.__version__,'heartbeat':client().heartbeat()>0,'server':client().get_version(),'eager':bool(celery_app.conf.task_always_eager),'queue':celery_app.conf.task_default_queue}))"]))
        check('real_chroma_and_non_eager_celery',actual['client']==actual['server']=='0.6.3' and actual['heartbeat'] and not actual['eager'],actual)
    def service(self, operation, *names):
        # Compose `start` traverses depends_on and would repair the dependency
        # outage under test. This branch starts only the selected existing service.
        args=(('up','-d','--wait','--wait-timeout','180',*names) if operation=='up'
              else ('up','-d','--no-deps',*names) if operation=='start' else (operation,*names))
        result=compose('index-'+operation+'-'+'-'.join(names),*args)
        if result.returncode:raise RuntimeError('Owned service operation failed')
    def upload(self):
        request=urllib.request.Request(BASE['be']+'/api/pdf/upload-and-parse?filename=indexing-synthetic-'+str(uuid.uuid4())+'.pdf',headers={'Authorization':'Bearer '+self.tokens['owner'],'Content-Type':'application/pdf'},data=b'%PDF-1.4\n% DO-DREAM LOCAL SYNTHETIC FIXTURE\n%%EOF\n')
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
        try:response=opener.open(request,timeout=55)
        except urllib.error.HTTPError as error:response=error
        data=json.loads(response.read());check('actual_binary_pdf_initial_accept',response.status==200 and bool(data.get('indexing')),{'http':response.status})
        state=data['indexing'];job=state.get('jobId') or state.get('job_id');self.jobs.append(job)
        fid=data.get('uploadedFileId') or data.get('pdfId')
        check('initial_pdf_file_identifier',isinstance(fid,int) and fid>0)
        return fid,job
    def fixture(self,name,title=None):
        title=title or '[INDEXING LOCAL] '+name+' '+STAMP+' '+uuid.uuid4().hex[:6]
        fid,initial=self.upload()
        statements=[clone_statement('materials',f'id={self.fixture_source}',{'title':literal(title),'uploaded_file_id':str(fid)}),'SET @new_material=LAST_INSERT_ID();']
        for table in ('material_contents','quizzes','material_shares'):
            statements.append(clone_statement(table,f'material_id={self.fixture_source}',{'material_id':'@new_material'}))
        statements.append('SELECT @new_material;')
        mid=int(sql('START TRANSACTION;\n'+'\n'.join(statements)+'\nCOMMIT;').splitlines()[-1])
        row={'id':mid,'file':fid,'title':title,'initialJob':initial};self.fixtures.append(row);return row
    def body(self,fixture,version='v1'):
        content='[INDEX LOCAL] '+version+' '+('물은 수소와 산소로 이루어져 있습니다. 안전한 합성 학습 본문입니다. '*70)
        return {'materialTitle':fixture['title'],'labelColor':'BLUE','editedJson':{'chapters':[{'id':'synthetic-content','title':'합성 학습','type':'content','content':content},{'id':'synthetic-quiz','title':'교사 전용','type':'quiz','content':'INDEX_SECRET_ANSWER_CANARY','correct_answer':'INDEX_SECRET_ANSWER_CANARY'}]},'quizzes':[]}
    def publish(self,fixture,version='v1',body=None):
        status,data,_=http('be',f"/api/documents/{fixture['file']}/publish",self.tokens['owner'],body or self.body(fixture,version))
        check('publish_accepted_'+str(fixture['id']),status==200 and isinstance(data,dict) and isinstance(data.get('indexing'),dict),{'http':status})
        result=data['indexing'];job=result.get('jobId') or result.get('job_id')
        check('publish_returns_durable_job',bool(job) and 'state' in result)
        if job not in self.jobs:self.jobs.append(job)
        return job,result
    def request(self,fixture,spec='local-hash8-content-v2'):
        code,data,_=http('be',f"/api/documents/{fixture['id']}/indexing",self.tokens['owner'],{'indexSpec':spec})
        check('reindex_accepted',code in (200,202) and isinstance(data,dict),{'http':code})
        job=data.get('jobId') or data.get('job_id')
        check('reindex_durable_id',bool(job))
        if job not in self.jobs:self.jobs.append(job)
        return job,data
    def status(self,job,who='owner'):
        code,data,_=http('be','/api/indexing/jobs/'+job,self.tokens[who])
        if code!=200:raise RuntimeError('Index status HTTP '+str(code))
        return data
    def done(self,job,state='SUCCEEDED',seconds=50):
        data=wait(lambda:(s if (s:=self.status(job))['state'] in ('SUCCEEDED','FAILED','REVOKED','SUPERSEDED') else None),seconds,'job '+job)
        check('job_terminal_'+state,data['state']==state,{'jobId':job,'state':data['state'],'generation':data.get('executionGeneration',data.get('generation')),'failureCode':data.get('failureCode')})
        return data
    def controls(self,job,**values):
        uuid.UUID(job)
        code="from pathlib import Path;import json;p=Path('/app/db_data/indexing-controls');p.mkdir(exist_ok=True);(p/"+repr(job+'.json')+").write_text("+repr(json.dumps(values))+")"
        docker_exec('ai',['python','-c',code])
    def release(self,job,gate):
        uuid.UUID(job)
        if gate not in ('before_write','after_partial','before_activation','after_activation','after_send'):raise ValueError('gate')
        docker_exec('ai',['python','-c',"from pathlib import Path;Path("+repr('/app/db_data/indexing-controls/'+job+'.'+gate+'.release')+").touch()"])
    def events(self,job):
        uuid.UUID(job)
        return json.loads(docker_exec('ai',['python','-c',"from pathlib import Path;import json;p=Path("+repr('/app/db_data/indexing-controls/'+job+'.events.jsonl')+");print(json.dumps([json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []))"]))
    def gate(self,job,name,seconds=30,generation=1):
        events=wait(lambda:[e for e in self.events(job) if e['event']==name and e.get('generation')==generation],seconds,'gate '+name)
        check('observed_'+name,True,{'jobId':job,'generation':generation,'observed_time':events[-1]['time']});return events[-1]
    def ledger(self,job):
        uuid.UUID(job)
        return query("SELECT JSON_OBJECT('jobId',j.job_id,'state',j.state,'deliveryState',j.delivery_state,'deliveries',j.delivery_attempts,'generation',j.execution_generation,'sourceRevision',j.source_revision,'sourceHash',j.source_hash,'snapshotHash',SHA2(j.snapshot_json,256),'safeSnapshot',LOCATE('INDEX_SECRET_ANSWER_CANARY',j.snapshot_json)=0,'resourceKind',r.resource_kind,'resource',r.resource_id,'latestJob',r.latest_job_id,'jobPk',j.id,'activeExecution',r.active_execution_id,'activations',r.activation_count) FROM index_jobs j JOIN index_resources r ON r.id=j.resource_pk WHERE j.job_id='"+job+"';")[0]
    def executions(self,job):
        return query("SELECT JSON_OBJECT('id',e.id,'generation',e.generation,'candidate',e.candidate_name,'state',e.state,'expectedChunks',e.expected_chunks,'actualChunks',e.actual_chunks,'digest',e.content_digest,'embeddingCalls',e.embedding_calls,'failureCode',e.failure_code) FROM index_executions e JOIN index_jobs j ON j.id=e.job_pk WHERE j.job_id='"+str(uuid.UUID(job))+"' ORDER BY e.generation;")
    def digest(self,candidate):
        if not candidate.startswith('idx_') or not all(c.isalnum() or c=='_' for c in candidate):raise ValueError('candidate')
        code="import json,hashlib;from app.indexing.chroma import fetch;c=fetch("+repr(candidate)+");d=c.get(include=['documents','metadatas','embeddings']);v=d['embeddings'];rows=sorted([[i,d['documents'][p],d['metadatas'][p],[float(x) for x in v[p]]] for p,i in enumerate(d['ids'])]);print(json.dumps({'count':c.count(),'digest':hashlib.sha256(json.dumps(rows,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()}))"
        return json.loads(docker_exec('ai',['python','-c',code]))
    def chat(self,fixture,code=200,who='shared',session=None):
        body={'document_id':str(fixture['id']),'question':'합성 본문 내용을 알려 주세요.'}
        if session:body['session_id']=session
        actual,data,_=http('ai','/rag/chat',self.tokens[who],body)
        check('rag_http_'+str(code),actual==code,{'actual':actual,'resource':fixture['id']})
        if actual==200:check('rag_no_teacher_answer',bool(data.get('answer')) and 'INDEX_SECRET_ANSWER_CANARY' not in json.dumps(data))
        return data
    def retry(self,job,generation):
        code,data,_=http('be','/api/indexing/jobs/'+job+'/retry',self.tokens['owner'],{'expectedGeneration':generation})
        check('bounded_explicit_retry',code in (200,202),{'http':code,'generation':generation});return data
    def duplicate_send(self,job,count=2):
        code="from app.celery_config import celery_app;[celery_app.send_task('dodream.indexing.process',kwargs={'job_id':"+repr(str(uuid.UUID(job)))+"},queue='indexing-v3',retry=False,ignore_result=True) for _ in range("+str(int(count))+")]"
        docker_exec('ai',['python','-c',code])
    def healthy(self,name):
        fixture=self.fixture(name);job,_=self.publish(fixture);self.done(job);return fixture,job
    def happy(self):
        self.service('stop','index-dispatcher')
        fixture=self.fixture('happy');job,data=self.publish(fixture)
        check('commit_before_delivery_is_queued',data['state']=='QUEUED' and not data['readable'])
        same,_=self.publish(fixture);check('duplicate_publish_same_logical_job',same==job)
        row=self.ledger(job);check('snapshot_hash_and_answer_filter',row['sourceHash']==row['snapshotHash'] and row['safeSnapshot'])
        self.service('up','index-dispatcher');self.done(job)
        row=self.ledger(job);executions=self.executions(job)
        check('one_activation_and_execution',row['activations']==1 and len(executions)==1 and executions[0]['state']=='ACTIVE')
        data=self.digest(executions[0]['candidate']);check('validated_real_chunks',data['count']==executions[0]['expectedChunks'] and data['count']>1)
        self.chat(fixture);self.evidence.append({'scenario':'happy','ledger':row,'executions':executions,'physical':data});self.happy_fixture=fixture;self.happy_job=job
    def failure_preservation(self):
        fixture,first=self.healthy('preserve');old=self.executions(first)[0];before=self.digest(old['candidate']);pointer=self.ledger(first)['activeExecution']
        self.service('stop','index-dispatcher');job,_=self.request(fixture);self.controls(job,fault='partial_failure');self.service('up','index-dispatcher')
        state=self.done(job,'FAILED');check('failed_reindex_still_readable',state['readable'] and not state['activeCurrent'])
        check('previous_pointer_and_chunks_preserved',self.ledger(job)['activeExecution']==pointer and self.digest(old['candidate'])==before)
        failed=self.executions(job)[0];physical=self.digest(failed['candidate']);check('failed_candidate_is_partial_isolated',0<physical['count']<failed['expectedChunks'] and failed['candidate']!=old['candidate'])
        self.chat(fixture);self.controls(job);self.retry(job,1);self.done(job)
        check('recovery_uses_new_candidate',len(self.executions(job))==2 and self.executions(job)[0]['candidate']!=self.executions(job)[1]['candidate'])
        check('recovery_old_index_unchanged',self.digest(old['candidate'])==before)
        self.evidence.append({'scenario':'partial_failure_recovery','before':before,'after':self.digest(old['candidate']),'ledger':self.ledger(job),'executions':self.executions(job)})
    def corruption(self):
        for fault in ('hash_mismatch','bad_dimension','bad_vector','missing_chunk','foreign_metadata','extra_chunk','bad_stored_vector','bad_document','activation_rollback','storage_timeout'):
            fixture,first=self.healthy(fault);old=self.executions(first)[0];before=self.digest(old['candidate']);pointer=self.ledger(first)['activeExecution']
            self.service('stop','index-dispatcher');job,_=self.request(fixture);self.controls(job,fault=fault);self.service('up','index-dispatcher');state=self.done(job,'FAILED')
            check('corruption_rejected_'+fault,state['readable'] and self.ledger(job)['activeExecution']==pointer and self.digest(old['candidate'])==before)
            self.chat(fixture);self.evidence.append({'scenario':fault,'ledger':self.ledger(job),'executions':self.executions(job),'preserved':before})
    def source_versions(self):
        fixture,first=self.healthy('source-version');session=self.chat(fixture)['session_id'];original=self.ledger(first)
        self.service('stop','index-dispatcher');second,state=self.publish(fixture,'new-v2')
        check('changed_source_blocks_old_active',not state['readable'] and state['sourceRevision']>original['sourceRevision']);self.chat(fixture,409)
        check('old_snapshot_immutable',self.ledger(first)['snapshotHash']==original['snapshotHash'])
        self.controls(second,fault='embedding_failure');self.service('up','index-dispatcher');self.done(second,'FAILED');self.chat(fixture,409)
        self.controls(second);self.retry(second,1);self.done(second);self.chat(fixture,409,session=session);self.chat(fixture)
        self.evidence.append({'scenario':'source_and_session_versions','old':original,'current':self.ledger(second)})
    def duplicates(self):
        self.service('stop','index-dispatcher');fixture=self.fixture('duplicates');job,_=self.publish(fixture)
        with ThreadPoolExecutor(max_workers=2) as pool:
            ids=list(pool.map(lambda _:self.request(fixture,'local-hash8-content-v1')[0],range(2)))
        check('independent_http_dedup',ids==[job,job])
        self.controls(job,gate='after_partial');self.service('up','index-dispatcher');self.gate(job,'after_partial')
        self.duplicate_send(job,3);self.release(job,'after_partial');self.done(job)
        wait(lambda:len([e for e in self.events(job) if e['event']=='worker_received'])>=4,25,'duplicate receipts')
        row=self.ledger(job);runs=self.executions(job)
        check('duplicate_delivery_one_execution_activation',len(runs)==1 and row['activations']==1)
        events=self.events(job);self.evidence.append({'scenario':'duplicate_delivery','logicalJobs':1,'workerReceipts':sum(e['event']=='worker_received' for e in events),'ledger':row,'executions':runs})
    def spring_control(self,fixture,mode):
        path='/app/local-data/indexing-controls/file-'+str(fixture['file'])+'.json'
        data=json.dumps({'mode':mode})
        docker_exec('be',['sh','-c','mkdir -p /app/local-data/indexing-controls; printf %s "$1" > "$2"','sh',data,path])
    def spring_events(self,fixture):
        path='/app/local-data/indexing-controls/file-'+str(fixture['file'])+'.events.jsonl'
        raw=docker_exec('be',['sh','-c','if test -f "$1"; then cat "$1"; fi','sh',path])
        return [json.loads(line) for line in raw.splitlines()]
    def restarts(self):
        self.service('stop','index-dispatcher');fixture=self.fixture('publish-crash');self.spring_control(fixture,'after_commit')
        future=self.pool.submit(http,'be',f"/api/documents/{fixture['file']}/publish",self.tokens['owner'],self.body(fixture))
        wait(lambda:any(e['event']=='after_commit' for e in self.spring_events(fixture)),25,'publish commit gate')
        jobs=query(f"SELECT JSON_OBJECT('jobId',j.job_id,'deliveries',j.delivery_attempts,'state',j.state) FROM index_jobs j JOIN index_resources r ON r.id=j.resource_pk WHERE r.resource_kind='MATERIAL' AND r.resource_id={fixture['id']};")
        check('published_job_committed_before_delivery',len(jobs)==1 and jobs[0]['deliveries']==0 and jobs[0]['state']=='QUEUED')
        job=jobs[0]['jobId'];self.jobs.append(job);check('spring_sigkill_after_observed_commit',crash_owned('be').returncode==0)
        try:future.result(timeout=5)
        except Exception:pass
        self.service('up','be');self.service('up','index-dispatcher');self.done(job);self.chat(fixture)
        self.evidence.append({'scenario':'publish_commit_before_delivery_crash','ledger':self.ledger(job)})
        for gate in ('after_partial','before_activation','after_activation'):
            fixture,first=self.healthy('crash-'+gate);old=self.executions(first)[0];before=self.digest(old['candidate'])
            self.service('stop','index-dispatcher');job,_=self.request(fixture);self.controls(job,gate=gate);self.service('up','index-dispatcher');self.gate(job,gate)
            pointer=self.ledger(job)['activeExecution'];check('worker_sigkill_'+gate,crash_owned('worker').returncode==0)
            self.service('up','worker')
            if gate=='after_activation':
                self.duplicate_send(job,2);self.done(job);check('post_commit_ack_loss_no_reactivation',self.ledger(job)['activeExecution']==pointer and self.ledger(job)['activations']==2 and len(self.executions(job))==1)
            else:
                self.done(job,'FAILED',seconds=45);self.controls(job);self.retry(job,1);self.done(job)
            check('crash_keeps_previous_physical_index_'+gate,self.digest(old['candidate'])==before);self.chat(fixture)
            self.evidence.append({'scenario':'actual_worker_sigkill_'+gate,'ledger':self.ledger(job),'executions':self.executions(job),'oldIndex':before})
    def delivery(self):
        self.service('stop','index-dispatcher');fixture=self.fixture('rollback');before=sql(f"SELECT SHA2(CONCAT_WS('|',title,uploaded_file_id),256) FROM materials WHERE id={fixture['id']};")
        self.spring_control(fixture,'rollback');code,_,_=http('be',f"/api/documents/{fixture['file']}/publish",self.tokens['owner'],self.body(fixture))
        count=int(sql(f"SELECT COUNT(*) FROM index_resources WHERE resource_kind='MATERIAL' AND resource_id={fixture['id']};"))
        check('publish_and_job_real_transaction_rollback',code==503 and count==0 and before==sql(f"SELECT SHA2(CONCAT_WS('|',title,uploaded_file_id),256) FROM materials WHERE id={fixture['id']};"))
        self.spring_control(fixture,'none');job,_=self.publish(fixture);self.service('stop','redis')
        try:
            self.service('start','index-dispatcher')
            wait(lambda:any(e['event']=='delivery_unconfirmed' for e in self.events(job)),25,'broker failure result')
            check('dispatcher_stopped_after_observed_broker_failure',crash_owned('index-dispatcher').returncode==0)
            row=self.ledger(job)
            check('broker_down_job_remains_durable',row['state']=='QUEUED' and row['generation']==0 and 1<=row['deliveries']<5,row)
        finally:
            self.service('up','redis');self.service('up','worker','index-dispatcher')
        self.done(job)
        self.evidence.append({'scenario':'broker_failure_recovery','ledger':self.ledger(job),'executions':self.executions(job)})
        self.service('stop','index-dispatcher','worker');fixture=self.fixture('send-crash');job,_=self.publish(fixture);self.controls(job,gate='after_send',generation=0)
        self.service('up','index-dispatcher');self.gate(job,'after_send',generation=0);check('dispatcher_sigkill_after_send',crash_owned('index-dispatcher').returncode==0)
        check('sent_before_record_has_unconfirmed_lease',self.ledger(job)['deliveryState']=='CLAIMED')
        queue_script="import base64,json;from redis import Redis;from app.config import CELERY_BROKER_URL;r=Redis.from_url(CELERY_BROKER_URL);bodies=[json.loads(base64.b64decode(json.loads(x)['body'])) for x in r.lrange('indexing-v3',0,-1)];found=[b for b in bodies if b[1].get('job_id')=="+repr(job)+"];print(json.dumps({'messages':len(found),'idsOnly':bool(found) and all(b[0]==[] and set(b[1])=={'job_id'} for b in found)}))"
        envelope=json.loads(docker_exec('ai',['python','-c',queue_script]));check('real_redis_envelope_contains_job_id_only',envelope['idsOnly'],envelope)
        self.controls(job);self.service('up','index-dispatcher');wait(lambda:self.ledger(job)['deliveries']>=2,45,'durable redelivery');self.service('up','worker');self.done(job)
        check('ambiguous_send_redelivery_one_activation',self.ledger(job)['activations']==1 and len(self.executions(job))==1)
        self.evidence.append({'scenario':'send_before_record_crash','ledger':self.ledger(job),'executions':self.executions(job)})
    def late_worker(self):
        from indexing_concurrency import late_worker
        late_worker(self)
    def bounded_recovery(self):
        from indexing_contract_checks import bounded_recovery
        bounded_recovery(self)
    def authorization(self):
        fixture,job=self.healthy('authority')
        for who in ('other','shared','unshared'):
            code,_,_=http('be','/api/indexing/jobs/'+job,self.tokens[who]);check('job_status_denied_'+who,code==(404 if who=='other' else 403))
            code,_,_=http('be','/api/indexing/jobs/'+job+'/retry',self.tokens[who],{'expectedGeneration':1});check('job_retry_denied_'+who,code==(404 if who=='other' else 403))
        self.chat(fixture,404,who='unshared')
        self.service('stop','index-dispatcher');pending,_=self.request(fixture);self.controls(pending,gate='before_activation');self.service('up','index-dispatcher');self.gate(pending,'before_activation')
        sql(f"UPDATE materials SET deleted_at=UTC_TIMESTAMP(6) WHERE id={fixture['id']} AND title={literal(fixture['title'])};")
        self.release(pending,'before_activation');wait(lambda:self.ledger(pending)['state']=='REVOKED',20,'revoked activation')
        check('deleted_resource_activation_refused',self.ledger(pending)['activations']==1);self.chat(fixture,404)
        sql(f"UPDATE materials SET deleted_at=NULL WHERE id={fixture['id']} AND title={literal(fixture['title'])};")
        self.chat(fixture)
        code,_,_=http('be',f"/api/materials/{fixture['id']}/shares/{self.users['shared']}",self.tokens['owner'],method='DELETE');check('new_fixture_share_revoked',code==204);self.chat(fixture,404)
        owned,active=self.healthy('owner-loss')
        self.service('stop','index-dispatcher');pending,_=self.request(owned);self.controls(pending,gate='before_activation');self.service('up','index-dispatcher');self.gate(pending,'before_activation')
        sql(f"UPDATE materials SET teacher_id={self.users['other']} WHERE id={owned['id']} AND teacher_id={self.users['owner']};")
        try:
            self.release(pending,'before_activation');wait(lambda:self.ledger(pending)['state']=='REVOKED',20,'owner loss')
            check('changed_owner_refuses_activation',self.ledger(pending)['activations']==1)
            self.chat(owned,404,who='owner');self.chat(owned,404,who='other')
        finally:sql(f"UPDATE materials SET teacher_id={self.users['owner']} WHERE id={owned['id']} AND teacher_id={self.users['other']};")
        self.chat(owned)
        before_invalid=self.ledger(pending)
        code,_,_=http('be',f"/api/documents/{owned['id']}/indexing",self.tokens['owner'],{'indexSpec':'local-hash8-content-v1','owner':self.users['other']})
        check('new_index_api_rejects_client_owner',code==400,{'http':code})
        check('invalid_owner_does_not_change_index_ledger',self.ledger(pending)==before_invalid)
        code,_,_=http('ai','/rag/chat',self.tokens['shared'],{'document_id':str(owned['id']),'question':'허용되지 않는 컬렉션 지정','collection':'arbitrary'})
        check('rag_rejects_client_collection',code==422)
    def storage_failure(self):
        fixture,first=self.healthy('chroma-unavailable');old=self.executions(first)[0];before=self.digest(old['candidate']);pointer=self.ledger(first)['activeExecution']
        self.service('stop','index-dispatcher');job,_=self.request(fixture);self.service('stop','chroma');self.service('start','index-dispatcher');self.done(job,'FAILED');self.chat(fixture,503)
        check('chroma_error_preserves_pointer',self.ledger(job)['activeExecution']==pointer)
        self.service('up','chroma');check('chroma_restart_old_chunks_preserved',self.digest(old['candidate'])==before);self.chat(fixture)
        self.retry(job,1);self.done(job);self.evidence.append({'scenario':'actual_chroma_unavailable_restart','ledger':self.ledger(job),'executions':self.executions(job),'preserved':before})
    def transport_timeout(self):
        fixture,first=self.healthy('http-timeout');old=self.executions(first)[0];before=self.digest(old['candidate']);pointer=self.ledger(first)['activeExecution']
        self.service('stop','index-dispatcher');job,_=self.request(fixture)
        check('actual_chroma_server_paused',pause_chroma().returncode==0)
        try:
            self.service('start','index-dispatcher');self.done(job,'FAILED')
            started=time.monotonic();self.chat(fixture,503);elapsed=time.monotonic()-started
            check('actual_http_read_timeout_bounded',4<=elapsed<12,{'elapsedSeconds':round(elapsed,2)})
            check('timeout_pointer_unchanged',self.ledger(job)['activeExecution']==pointer)
        finally:check('actual_chroma_server_resumed',pause_chroma(True).returncode==0)
        check('timeout_physical_content_preserved',self.digest(old['candidate'])==before);self.chat(fixture)
        self.retry(job,1);self.done(job)
        self.evidence.append({'scenario':'actual_paused_server_http_timeout','ledger':self.ledger(job),'executions':self.executions(job),'preserved':before})
    def publication(self):
        from indexing_contract_checks import publication
        publication(self)
    def schema(self):
        from indexing_contract_checks import schema
        schema(self)
    def initial_pdf(self):
        fid,job=self.upload();self.done(job)
        check('initial_pdf_has_distinct_resource_kind',sql("SELECT r.resource_kind FROM index_resources r JOIN index_jobs j ON j.resource_pk=r.id WHERE j.job_id='"+job+"';")=='PDF')
        for who,expected in (('owner',200),('shared',403)):
            code,_,_=http('ai','/rag/chat',self.tokens[who],{'document_id':'pdf_'+str(fid),'question':'합성 초기본 확인'})
            check('initial_pdf_teacher_only_'+who,code==expected,{'http':code})
    def browser(self):
        from indexing_browser_checks import browser
        browser(self)
    def report(self,completed):
        alljobs=[]
        for job in self.jobs:
            try:
                events=self.events(job);alljobs.append({'ledger':self.ledger(job),'executions':self.executions(job),'workerReceipts':sum(e['event']=='worker_received' for e in events),'brokerSendReturns':sum(e['event']=='broker_send_returned' for e in events)})
            except Exception:pass
        result={'run':STAMP,'source':source_identity(),'completed':completed,'checks':CHECKS,'counts':{s:sum(c['status']==s for c in CHECKS) for s in ('PASS','FAIL','BLOCKED','NOT_RUN')},'evidence':self.evidence,'jobs':alljobs,'fixtures':self.fixtures}
        (RESULTS/('indexing-checks-'+STAMP+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        (RESULTS/'indexing-checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(result['counts']),flush=True)

def main():
    runner=Runner();completed=[];selected=tuple(sys.argv[1:] or SCENARIOS);interrupted=False
    try:
        runner.initialize()
        for name in selected:
            if name not in SCENARIOS:raise ValueError('Unknown scenario')
            if time.monotonic()-runner.last_login>300:
                runner.initialize()
            getattr(runner,name)();completed.append(name)
    except KeyboardInterrupt:
        interrupted=True
        print('Own indexing verifier interrupted; partial evidence retained',flush=True)
    except Exception as error:
        import traceback
        print('failure_locations:',json.dumps([{'file':Path(f.filename).name,'line':f.lineno,'function':f.name} for f in traceback.extract_tb(error.__traceback__)]),flush=True)
        CHECKS.append({'name':'indexing_execution','status':'BLOCKED' if isinstance(error,(TimeoutError,urllib.error.URLError,subprocess.TimeoutExpired)) else 'FAIL','detail':type(error).__name__})
        print('indexing stopped:',type(error).__name__,flush=True)
    finally:
        for name in selected:
            if name not in completed:
                CHECKS.append({'name':name+'_not_completed','status':'NOT_RUN','detail':'Scenario not completed; see preceding failure or interruption'})
        runner.report(completed);runner.pool.shutdown(wait=False,cancel_futures=True)
    if interrupted:return 130
    return 1 if any(c['status'] in ('FAIL','BLOCKED') for c in CHECKS) else 0

if __name__=='__main__':sys.exit(main())
