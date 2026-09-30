#!/usr/bin/env python3
"""Phase 4 actual HTTP/SQL checks, not browser UI E2E.

Only two new opaque visitor contexts are allocated. Domain writes use the real
demo/chat/grading APIs; sample source, shares, indexes and existing rows are not
edited. Docker exec is read-only and goes through the existing scope gate.
Tokens, cookies, visitor secrets, raw bodies and exception text are never logged.
"""
import argparse
import copy
import concurrent.futures
import http.cookiejar
import http.cookies
import json
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone


class CheckFailure(RuntimeError):
    pass


def positive_id(value):
    if type(value) is not int or not 0 < value <= 9223372036854775807:
        raise ValueError('Invalid synthetic object identifier')
    return value


def uuid_value(value):
    if not isinstance(value,str) or str(uuid.UUID(value))!=value:
        raise ValueError('Invalid synthetic UUID')
    return value


def no_answers(value):
    forbidden={'answer','correct_answer','correctanswer','rubric','teacher_notes','grading_criteria','explanation'}
    if isinstance(value,dict):return all(str(k).lower() not in forbidden and no_answers(v) for k,v in value.items())
    if isinstance(value,list):return all(no_answers(v) for v in value)
    return True


def cookie_contract(headers,name,path):
    cookies=http.cookies.SimpleCookie()
    for value in headers.get_all('Set-Cookie',[]):cookies.load(value)
    item=cookies.get(name)
    return bool(item and item['httponly'] and item['path']==path and item['samesite'].lower()=='lax'
        and not item['secure'] and int(item['max-age'])>0)


def source_contract(source,document,revision,source_hash):
    fields={'document_id','source_revision','source_hash','chunk_position','content_hash','material_title','excerpt'}
    return (isinstance(source,dict) and set(source)==fields and source['document_id']==str(document)
        and type(source['source_revision']) is int and source['source_revision']==revision
        and source['source_hash']==source_hash and isinstance(source['source_hash'],str)
        and re.fullmatch(r'[a-f0-9]{64}',source['source_hash']) is not None
        and type(source['chunk_position']) is int and 0<=source['chunk_position']<500
        and isinstance(source['content_hash'],str) and re.fullmatch(r'[a-f0-9]{64}',source['content_hash']) is not None
        and isinstance(source['material_title'],str) and isinstance(source['excerpt'],str)
        and 0<len(source['excerpt'])<=300)


def source_evidence(source,api):
    """Read-only probe reusable by actual browser acceptance; never returns text."""
    document=positive_id(int(source['document_id']))
    if not source_contract(source,document,source['source_revision'],source['source_hash']):
        raise ValueError('Invalid public source reference')
    code="""import hashlib,json
from app.common.db_session import SessionLocal
from app.indexing.models import IndexResource,IndexExecution,IndexJob
from app.indexing.chroma import fetch
s=json.loads(SOURCE_JSON)
with SessionLocal() as db:
    r=db.query(IndexResource).filter_by(resource_kind='MATERIAL',resource_id=int(s['document_id'])).one()
    e=db.get(IndexExecution,r.active_execution_id);j=db.get(IndexJob,e.job_pk)
    bound=(r.source_revision==s['source_revision']==j.source_revision and r.current_source_hash==s['source_hash']==j.source_hash and e.state=='ACTIVE' and j.state=='SUCCEEDED' and j.resource_pk==r.id)
    candidate=e.candidate_name
c=fetch(candidate)
d=c.get(where={'$and':[{'position':s['chunk_position']},{'source_hash':s['source_hash']}]},include=['documents','metadatas'])
matched=len(d['ids'])==1 and d['documents'][0][:300]==s['excerpt'] and hashlib.sha256(d['documents'][0].encode()).hexdigest()==s['content_hash'] and d['metadatas'][0]['content_hash']==s['content_hash']
print(json.dumps({'bound':bound,'matched':matched,'count':len(d['ids'])}))
""".replace('SOURCE_JSON',repr(json.dumps(source,ensure_ascii=False)))
    return json.loads(api.docker_exec('ai',['python','-c',code]))


def grading_evidence(submissions,api):
    """Verify each frozen logical key, including all result/log rows for its attempt.

    Only validated integer/UUID values enter SQL. A different logical submission
    by the same student is not a duplicate of this one and is counted separately.
    """
    if not isinstance(submissions,list) or not 1<=len(submissions)<=100:
        raise ValueError('Invalid submission evidence list')
    rows=[]
    for item in submissions:
        user=positive_id(item['userId']);material=positive_id(item['materialId'])
        key=uuid_value(item['key']);attempt=uuid_value(item['attemptId'])
        count=positive_id(item['questionCount'])
        if count>50:raise ValueError('Invalid question count')
        predicate=f"student_id={user} AND idempotency_key='{key}'"
        raw=api.sql("SELECT COUNT(*) FROM grading_attempts WHERE "+predicate+";"
            "SELECT COUNT(*) FROM grading_attempts WHERE "+predicate+
            f" AND material_id={material} AND attempt_id='{attempt}' AND state='SUCCEEDED';"
            "SELECT COUNT(*) FROM grading_attempt_results r JOIN grading_attempts a ON a.id=r.attempt_id WHERE a."+predicate.replace(' AND ',' AND a.')+";"
            "SELECT COUNT(*) FROM student_quiz_logs l JOIN grading_attempts a ON a.id=l.attempt_id WHERE a."+predicate.replace(' AND ',' AND a.')+";"
            "SELECT COUNT(DISTINCT r.quiz_id) FROM grading_attempt_results r JOIN grading_attempts a ON a.id=r.attempt_id WHERE a."+predicate.replace(' AND ',' AND a.')+";"
            "SELECT COUNT(DISTINCT l.quiz_id) FROM student_quiz_logs l JOIN grading_attempts a ON a.id=l.attempt_id WHERE a."+predicate.replace(' AND ',' AND a.')+";")
        observed=list(map(int,raw.splitlines()))
        rows.append({'userId':user,'materialId':material,'attemptId':attempt,
            'passed':observed==[1,1,count,count,count,count],
            'attempts':observed[0],'boundSuccessfulAttempts':observed[1],
            'results':observed[2],'logs':observed[3],
            'uniqueResultQuestions':observed[4],'uniqueLogQuestions':observed[5],
            'expectedQuestions':count})
    return rows


class Client:
    def __init__(self,bases,no_redirect):
        self.bases=bases
        self.jar=http.cookiejar.CookieJar()
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),no_redirect(),
            urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf=None
        self.token=None
        self.user=None

    def call(self,path,body=None,token=None,headers=None,service='be'):
        if service not in ('be','ai') or not path.startswith('/') or path.startswith('//'):
            raise ValueError('Only reviewed local service paths allowed')
        h={'Content-Type':'application/json',**(headers or {})}
        if token:h['Authorization']='Bearer '+token
        request=urllib.request.Request(self.bases[service]+path,headers=h,
            data=None if body is None else json.dumps(body).encode())
        try:response=self.opener.open(request,timeout=20)
        except urllib.error.HTTPError as error:response=error
        with response:
            raw=response.read(2*1024*1024+1)
            if len(raw)>2*1024*1024:raise ValueError('Response limit exceeded')
            try:data=json.loads(raw)
            except (ValueError,UnicodeDecodeError):data=None
            return response.status,data,response.headers

    def cookie(self,name):
        return next((cookie.value for cookie in self.jar if cookie.name==name),None)

    def auth(self,path,body=None,token=None):
        if not self.csrf:raise ValueError('CSRF prerequisite missing')
        return self.call(path,{} if body is None else body,token,
            {self.csrf['headerName']:self.csrf['token']})


class Runner:
    def __init__(self,disabled=False):
        # Reuse only the established localhost targets, generated local settings,
        # NoRedirect and scoped SQL/exec helpers. Pure helper tests do not import it.
        import verify
        from manage import RESULTS
        self.api=verify
        self.results=RESULTS
        self.disabled=disabled
        self.stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8]
        self.checks=[]
        self.contexts=[Client(verify.BASE,verify.NoRedirect) for _ in range(2 if not disabled else 1)]
        self.started=datetime.now(timezone.utc).isoformat()
        self.observations={}

    def check(self,name,passed,detail=None):
        row={'name':name,'status':'PASS' if passed else 'FAIL','detail':detail or {}}
        self.checks.append(row)
        print(json.dumps(row,ensure_ascii=False),flush=True)
        with (self.results/('student-demo-progress-'+self.stamp+'.jsonl')).open('a') as stream:
            stream.write(json.dumps(row,ensure_ascii=False)+'\n')
        if not passed:raise CheckFailure(name)

    def expect(self,name,response,status):
        code,data,headers=response
        self.check(name,code==status,{'http':code,'expected':status})
        return data,headers

    def csrf(self,client,label):
        data,_=self.expect(label+'_csrf',client.call('/api/auth/csrf'),200)
        self.check(label+'_csrf_shape',isinstance(data,dict) and isinstance(data.get('token'),str)
            and data.get('headerName')=='X-XSRF-TOKEN')
        client.csrf=data

    def counts(self):
        # Totals only; no visitor hash, credential or content leaves MySQL.
        tables=('users','student_profiles','materials','quizzes','material_shares','index_jobs')
        raw=self.api.sql(';'.join('SELECT COUNT(*) FROM '+table for table in tables)+';')
        counts=dict(zip(tables,map(int,raw.splitlines())))
        present=self.api.sql("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='local_demo_visitors';")
        counts['visitors']=int(self.api.sql('SELECT COUNT(*) FROM local_demo_visitors;')) if int(present) else 0
        return counts

    def identity(self,client,label):
        data,_=self.expect(label+'_spring_identity',client.call('/api/session/me',token=client.token),200)
        self.check(label+'_student_identity',isinstance(data,dict) and set(data)=={'userId','name','role','demo'}
            and data.get('role')=='STUDENT' and data.get('demo') is True and type(data.get('userId')) is int)
        identity=positive_id(data['userId'])
        ai,_=self.expect(label+'_ai_identity',client.call('/users/users/me',token=client.token,service='ai'),200)
        claims=self.api.payload(client.token)
        self.check(label+'_shared_real_jwt_identity',ai.get('id')==identity and ai.get('role')=='STUDENT'
            and claims.get('sub')==str(identity) and claims.get('role')=='STUDENT' and claims.get('token_use')=='access')
        client.user=identity
        return identity

    def bootstrap(self,client,label):
        self.csrf(client,label)
        for route in ('bootstrap','start'):
            self.expect(label+'_'+route+'_no_csrf',client.call('/api/auth/demo/'+route,body={}),403)
        for body in ({'userId':1},{'role':'TEACHER'},{'schoolId':1}):
            self.expect(label+'_forged_'+next(iter(body)),client.auth('/api/auth/demo/start',body),400)
        self.expect(label+'_start_needs_bootstrap',client.auth('/api/auth/demo/start'),400)
        data,headers=self.expect(label+'_bootstrap',client.auth('/api/auth/demo/bootstrap'),200)
        self.check(label+'_opaque_bootstrap_cookie',data=={'ready':True}
            and cookie_contract(headers,'dodream_demo_visitor','/api/auth/demo'))
        visitor=client.cookie('dodream_demo_visitor')
        self.check(label+'_visitor_shape',isinstance(visitor,str) and re.fullmatch(r'[a-f0-9]{64}',visitor) is not None)
        self.expect(label+'_bootstrap_replay',client.auth('/api/auth/demo/bootstrap'),200)
        self.check(label+'_same_opaque_visitor',client.cookie('dodream_demo_visitor')==visitor)

    def start(self,client,label):
        data,headers=self.expect(label+'_start',client.auth('/api/auth/demo/start'),200)
        self.started_session(client,label,data,headers)

    def started_session(self,client,label,data,headers):
        self.check(label+'_access_only_body',isinstance(data,dict) and set(data)=={'accessToken'}
            and isinstance(data['accessToken'],str) and bool(data['accessToken'])
            and cookie_contract(headers,'refresh','/api/auth'))
        client.token=data['accessToken']
        self.identity(client,label)

    def concurrent_start(self,client,label):
        # Two cookie clients for ONE opaque visitor, released together. A losing
        # request must not create another account or invalidate the winning JWT.
        twin=Client(client.bases,self.api.NoRedirect)
        for cookie in client.jar:twin.jar.set_cookie(copy.copy(cookie))
        twin.csrf=dict(client.csrf)
        ready=threading.Barrier(2)
        def attempt(candidate):
            ready.wait(timeout=5)
            return candidate,candidate.auth('/api/auth/demo/start')
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            pending=[pool.submit(attempt,candidate) for candidate in (client,twin)]
            completed=[future.result(timeout=25) for future in pending]
        self.check(label+'_concurrent_start_one_winner',sorted(response[0] for _,response in completed)==[200,409])
        winner,response=next((candidate,response) for candidate,response in completed if response[0]==200)
        loser=next(response for _,response in completed if response[0]==409)
        self.check(label+'_concurrent_start_lease',isinstance(loser[1],dict) and loser[1].get('code')=='DEMO_START_IN_PROGRESS')
        # CookieJar is shared with the original opener, so copy accepted cookies
        # into it rather than replacing the jar object behind that opener.
        if winner is not client:
            client.jar.clear()
            for cookie in winner.jar:client.jar.set_cookie(copy.copy(cookie))
        self.started_session(client,label,response[1],response[2])

    def modes(self,client):
        mode,_=self.expect('server_mode',client.call('/rag/mode',token=client.token,service='ai'),200)
        self.check('server_explicit_local_mode',mode=={'environment':'local','answer_provider':'local_stub',
            'embedding_provider':'local_hash8','grading_provider':'local_stub'})
        return mode

    def chat(self,client,material,mode,label):
        data,_=self.expect(label+'_rag_chat',client.call('/rag/chat',token=client.token,service='ai',
            body={'document_id':str(material),'question':'이 자료의 학습 내용을 알려 주세요.'}),200)
        self.check(label+'_answer_source_shape',isinstance(data,dict) and isinstance(data.get('answer'),str)
            and bool(data['answer']) and isinstance(data.get('sources'),list) and len(data['sources'])==1
            and data.get('document_id')==str(material) and data.get('mode')==mode)
        uuid_value(data['session_id']);positive_id(data['message_id'])
        source=data['sources'][0]
        self.check(label+'_bound_source',source_contract(source,material,data['source_revision'],data['source_hash'])
            and data['answer'].endswith(source['excerpt']))
        path=f"/rag/chat/sessions/{data['session_id']}/messages/{data['message_id']}/sources/0?student_id={client.user}"
        actual,_=self.expect(label+'_source_lookup',client.call(path,token=client.token,service='ai'),200)
        self.check(label+'_same_version_lookup',actual==source)
        history,_=self.expect(label+'_history',client.call(
            f"/rag/chat/sessions/{data['session_id']}/messages?student_id={client.user}",token=client.token,service='ai'),200)
        saved=[message for message in history['messages'] if message['id']==data['message_id']]
        self.check(label+'_history_recovery',len(saved)==1 and saved[0]['content']==data['answer']
            and saved[0]['sources']==data['sources'] and saved[0]['mode']==mode)
        return data

    def actual_source(self,source):
        observed=source_evidence(source,self.api)
        self.check('actual_mysql_and_chroma_source_correspondence',observed=={'bound':True,'matched':True,'count':1},observed)

    def submit(self,client,material,quizzes,key,label):
        answers=[{'quizId':positive_id(q['id']),'version':q['version'],'answer':'합성 체험 검증 답안'} for q in quizzes]
        body={'answers':answers}
        response=client.call(f'/api/materials/{material}/quizzes/submit',body=body,token=client.token,headers={'Idempotency-Key':key})
        data,headers=self.expect(label+'_quiz_submission',response,200)
        attempt=uuid_value(headers.get('X-Grading-Attempt-Id'))
        self.check(label+'_confirmed_snapshot_result',headers.get('X-Grading-State')=='SUCCEEDED' and isinstance(data,list)
            and len(data)==len(answers) and {r.get('question_id') for r in data}=={q['quizId'] for q in answers}
            and all(r.get('attemptId')==attempt and r.get('snapshotAvailable') is True and type(r.get('is_correct')) is bool
                and isinstance(r.get('correct_answer'),str) and isinstance(r.get('ai_feedback'),str)
                and r.get('student_answer')=='합성 체험 검증 답안' for r in data))
        replay,headers=self.expect(label+'_same_key_replay',client.call(f'/api/materials/{material}/quizzes/submit',
            body=body,token=client.token,headers={'Idempotency-Key':key}),200)
        self.check(label+'_same_attempt_and_result',headers.get('X-Grading-Attempt-Id')==attempt and replay==data)
        queried,_=self.expect(label+'_attempt_status',client.call(f'/api/materials/{material}/quiz-attempts/{attempt}',token=client.token),200)
        self.check(label+'_status_matches_result',queried==data)
        history,_=self.expect(label+'_quiz_history',client.call(f'/api/materials/{material}/quizzes/history',token=client.token),200)
        self.check(label+'_history_matches_snapshot',isinstance(history,list) and len(history)==len(answers)
            and all(r.get('attemptId')==attempt and r.get('snapshotAvailable') is True for r in history))
        return attempt

    def disabled_run(self):
        client=self.contexts[0];before=self.counts()
        data,_=self.expect('disabled_configuration',client.call('/api/auth/demo/config'),200)
        self.check('disabled_server_flag',data.get('enabled') is False and data.get('mode')=='UNAVAILABLE'
            and data.get('ready') is False and data.get('samples')==[])
        self.csrf(client,'disabled')
        for route in ('bootstrap','start'):
            self.expect('disabled_'+route,client.auth('/api/auth/demo/'+route),404)
        self.check('disabled_no_cookies_or_accounts',client.cookie('dodream_demo_visitor') is None
            and client.cookie('refresh') is None and self.counts()==before)

    def run(self):
        if self.disabled:return self.disabled_run()
        self.expect('actual_spring_health',self.api.req('be','/actuator/health')[:3],200)
        a,b=self.contexts
        config,_=self.expect('demo_configuration',a.call('/api/auth/demo/config'),200)
        self.check('prepared_demo_samples',config.get('enabled') is True and config.get('ready') is True
            and config.get('mode')=='LOCAL_DETERMINISTIC' and len(config.get('samples',[]))==2
            and all(s.get('readable') is True and type(s.get('materialId')) is int
                and isinstance(s.get('source'),str) and bool(s['source']) for s in config['samples']))
        self.check('bounded_server_visitor_limit',type(config.get('visitorLimit')) is int
            and 1<=config['visitorLimit']<=1000)
        version=config.get('fixtureVersion')
        if not isinstance(version,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,40}',version):
            raise ValueError('Invalid fixture version')
        catalog_count=int(self.api.sql("SELECT visitor_count FROM local_demo_catalogs WHERE version='"+version+"';"))
        actual_count=int(self.api.sql("SELECT COUNT(*) FROM local_demo_visitors WHERE fixture_version='"+version+"';"))
        self.check('visitor_quota_counter_consistent',catalog_count==actual_count and catalog_count+2<=config['visitorLimit'],
            {'allocatedBefore':actual_count,'limit':config['visitorLimit'],'requiredNewVisitors':2})
        sample_ids={positive_id(s['materialId']) for s in config['samples']}
        before=self.counts()
        self.bootstrap(a,'visitor_a');self.bootstrap(b,'visitor_b')
        self.check('bootstrap_does_not_create_users',self.counts()==before)
        self.check('independent_visitor_secrets',a.cookie('dodream_demo_visitor')!=b.cookie('dodream_demo_visitor'))
        self.concurrent_start(a,'visitor_a');self.start(b,'visitor_b')
        self.check('independent_student_ids',a.user!=b.user)
        after=self.counts()
        self.check('exactly_two_new_visitors',all(after[k]==before[k]+2 for k in ('users','student_profiles','visitors'))
            and after['material_shares']==before['material_shares']+2*len(sample_ids)
            and all(after[k]==before[k] for k in ('materials','quizzes','index_jobs')))
        self.check('visitor_quota_counter_incremented_once',int(self.api.sql(
            "SELECT visitor_count FROM local_demo_catalogs WHERE version='"+version+"';"))==catalog_count+2)
        original_rt=a.cookie('refresh')
        for route in ('start','bootstrap'):
            self.expect('existing_session_'+route+'_not_replaced',a.auth('/api/auth/demo/'+route,token=a.token),409)
        self.check('duplicate_start_keeps_identity_and_cookie',a.cookie('refresh')==original_rt and self.counts()==after)
        self.identity(a,'visitor_a_after_rejected_start')
        for label,client in [('visitor_a',a),('visitor_b',b)]:
            self.expect(label+'_teacher_route_denied',client.call('/api/documents/published',token=client.token),403)
            self.expect(label+'_teacher_preparation_denied',client.call('/api/demo/prepare',body={},token=client.token),403)
            shared,_=self.expect(label+'_shared_materials',client.call('/api/materials/shared',token=client.token),200)
            self.check(label+'_only_demo_materials',{row['materialId'] for row in shared['materials']}==sample_ids
                and all(row.get('indexing',{}).get('readable') is True for row in shared['materials']))
            for material in sorted(sample_ids):
                content,_=self.expect(label+'_safe_student_content_'+str(material),client.call(f'/api/materials/shared/{material}/json',token=client.token),200)
                self.check(label+'_no_teacher_answers_'+str(material),isinstance(content,dict)
                    and bool(content.get('chapters')) and no_answers(content))
        material=min(sample_ids)
        private_id=self.api.sql('SELECT id FROM materials WHERE id NOT IN ('+
            ','.join(str(identity) for identity in sorted(sample_ids))+') ORDER BY id LIMIT 1;')
        self.check('unshared_material_prerequisite',bool(private_id))
        private=positive_id(int(private_id))
        for label,client in [('visitor_a',a),('visitor_b',b)]:
            self.expect(label+'_unshared_content_denied',client.call(f'/api/materials/shared/{private}/json',token=client.token),404)
            self.expect(label+'_unshared_quiz_denied',client.call(f'/api/materials/{private}/quizzes',token=client.token),404)
            self.expect(label+'_unshared_chat_denied',client.call('/rag/chat',token=client.token,service='ai',
                body={'document_id':str(private),'question':'공유되지 않은 자료 접근 검사'}),404)
        quizzes,_=self.expect('public_versioned_questions',a.call(f'/api/materials/{material}/quizzes',token=a.token),200)
        self.check('questions_do_not_expose_answers',isinstance(quizzes,list) and 0<len(quizzes)<=50 and no_answers(quizzes)
            and all(type(q.get('version')) is int and q['version']>=0 for q in quizzes))
        mode=self.modes(a)
        chat_a=self.chat(a,material,mode,'visitor_a');chat_b=self.chat(b,material,mode,'visitor_b')
        self.actual_source(chat_a['sources'][0])
        for caller,owner,chat,label in [(a,b,chat_b,'a_to_b'),(b,a,chat_a,'b_to_a')]:
            self.expect('cross_session_'+label,caller.call('/rag/chat',token=caller.token,service='ai',body={
                'document_id':str(material),'session_id':chat['session_id'],'question':'다른 방문자 세션 접근 검사'}),404)
            self.expect('cross_history_'+label,caller.call(f"/rag/chat/sessions/{chat['session_id']}/messages?student_id={owner.user}",token=caller.token,service='ai'),404)
            self.expect('cross_source_'+label,caller.call(f"/rag/chat/sessions/{chat['session_id']}/messages/{chat['message_id']}/sources/0?student_id={caller.user}",token=caller.token,service='ai'),404)
            sessions,_=self.expect('self_session_list_'+label,caller.call(f'/rag/chat/sessions?student_id={caller.user}',token=caller.token,service='ai'),200)
            self.check('session_list_isolated_'+label,len(sessions)==1 and sessions[0]['id']!=chat['session_id'])
        key=str(uuid.uuid4())
        attempt_a=self.submit(a,material,quizzes,key,'visitor_a')
        attempt_b=self.submit(b,material,quizzes,key,'visitor_b')
        self.check('same_key_is_scoped_to_student',attempt_a!=attempt_b)
        for caller,attempt,label in [(a,attempt_b,'a_to_b'),(b,attempt_a,'b_to_a')]:
            self.expect('cross_attempt_'+label,caller.call(f'/api/materials/{material}/quiz-attempts/{attempt}',token=caller.token),404)
        submissions=[{'userId':client.user,'materialId':material,'key':key,'attemptId':attempt,'questionCount':len(quizzes)}
            for client,attempt in ((a,attempt_a),(b,attempt_b))]
        counts=grading_evidence(submissions,self.api)
        self.check('real_database_no_duplicate_grading',all(row['passed'] for row in counts),{'submissions':counts})
        self.observations={'studentIds':[a.user,b.user],'materialIds':sorted(sample_ids),
            'logicalSubmissions':submissions,'grading':counts,
            'source':{k:v for k,v in chat_a['sources'][0].items() if k not in ('excerpt','material_title')}}
        for service,path in [('be','/api/session/me'),('ai','/users/users/me')]:
            self.expect('refresh_not_access_'+service,a.call(path,token=original_rt,service=service),401)
        self.expect('student_refresh_requires_csrf',a.call('/api/auth/student/refresh',body={}),403)
        renewed,headers=self.expect('student_cookie_refresh',a.auth('/api/auth/student/refresh'),200)
        self.check('refresh_rotated_without_body_rt',isinstance(renewed,dict) and set(renewed)=={'accessToken'}
            and a.cookie('refresh')!=original_rt and cookie_contract(headers,'refresh','/api/auth'))
        a.token=renewed['accessToken'];self.identity(a,'visitor_a_refreshed')
        self.expect('student_logout_requires_csrf',a.call('/api/auth/student/logout',body={}),403)
        self.expect('student_cookie_logout',a.auth('/api/auth/student/logout'),200)
        self.check('logout_removes_refresh_cookie',a.cookie('refresh') is None)
        self.expect('logged_out_refresh_denied',a.auth('/api/auth/student/refresh'),401)
        # Explicit logout then same opaque visitor: user/material/index creation
        # must not repeat. The server's fixed 3-second duplicate-start lease is
        # normally long expired by now; one bounded wait avoids a timing guess.
        time.sleep(3.1)
        original_user=a.user;self.start(a,'visitor_a_explicit_restart')
        self.check('visitor_restart_reuses_identity_and_rows',a.user==original_user and self.counts()==after)
        for label,client in [('visitor_a',a),('visitor_b',b)]:
            self.expect(label+'_final_logout',client.auth('/api/auth/student/logout'),200)

    def cleanup(self):
        """Release only sessions allocated in this run, including partial failures."""
        for index,client in enumerate(self.contexts):
            if not client.cookie('refresh'):continue
            try:
                status,_,_=client.auth('/api/auth/student/logout')
                passed=status==200 and client.cookie('refresh') is None
                detail={'http':status}
            except Exception as error:
                passed=False;detail={'error_type':type(error).__name__}
            self.checks.append({'name':'cleanup_visitor_'+str(index+1),
                'status':'PASS' if passed else 'FAIL','detail':detail})
        return not any(row['status']=='FAIL' and row['name'].startswith('cleanup_') for row in self.checks)

    def finish(self,exit_code):
        output={'kind':'ACTUAL_HTTP_SQL_API_NOT_UI_E2E','mode':'disabled' if self.disabled else 'enabled',
            'origins':{key:self.api.BASE[key] for key in ('be','ai')},'observations':self.observations,
            'started_at':self.started,'finished_at':datetime.now(timezone.utc).isoformat(),
            'checks':self.checks,'counts':{state:sum(row['status']==state for row in self.checks)
                for state in ('PASS','FAIL','BLOCKED')},'exit_code':exit_code,
            'limits':'Two fresh visitor identities maximum; existing sample source/index/relationships untouched. Capacity exhaustion is a separate Spring unit check, not exercised by allocating 100 visitors. No provider faults or browser UI claims.'}
        encoded=json.dumps(output,ensure_ascii=False,indent=2)+'\n'
        (self.results/('student-demo-checks-'+self.stamp+'.json')).write_text(encoded)
        (self.results/('student-demo-'+('disabled' if self.disabled else 'enabled')+'-latest.json')).write_text(encoded)
        print(json.dumps({'exit_code':exit_code,'counts':output['counts']}))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disabled',action='store_true',help='Assert server-disabled endpoints without allocating a visitor')
    args=parser.parse_args()
    runner=Runner(args.disabled);exit_code=0
    try:runner.run()
    except CheckFailure:exit_code=1
    except Exception as error:
        from scope_guard import ScopeError
        state='BLOCKED' if isinstance(error,(ScopeError,urllib.error.URLError,TimeoutError,ConnectionError,subprocess.TimeoutExpired)) else 'FAIL'
        runner.checks.append({'name':'student_demo_execution','status':state,'detail':{'error_type':type(error).__name__}})
        exit_code=1
    finally:
        if not runner.cleanup():exit_code=1
        runner.finish(exit_code)
    return exit_code


if __name__=='__main__':sys.exit(main())
