#!/usr/bin/env python3
"""Real localhost HTTP/DB verification. Stores statuses only, never tokens/bodies."""
import base64
import http.cookies
import json
import re
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from manage import ROOT, RESULTS, PROJECT, settings, compose_args, compose_base, clean_env
from scope_guard import MAIN, gate, port_available, read_metadata

ENV = settings()
BASE = {name: 'http://127.0.0.1:' + ENV[key] for name, key in
        [('be','BE_PORT'), ('ai','AI_PORT'), ('pdf','PDF_PORT'), ('web','WEB_PORT')]}
CHECKS = []
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs): return None
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

def req(service, path, token=None, body=None, headers=None, timeout=20):
    if not path.startswith('/') or path.startswith('//'):
        raise ValueError('Only explicit local paths allowed')
    h = {'Content-Type': 'application/json'}
    if token: h['Authorization'] = 'Bearer ' + token
    if headers: h.update(headers)
    # The new cookie auth contract needs a CSRF cookie/header even with expired AT.
    if body is not None and path.startswith('/api/auth/') and '/native/' not in path:
        csrf_req = urllib.request.Request(BASE[service] + '/api/auth/csrf')
        csrf_response = OPENER.open(csrf_req, timeout=timeout)
        csrf = json.loads(csrf_response.read())
        jar = http.cookies.SimpleCookie()
        for value in csrf_response.headers.get_all('Set-Cookie', []): jar.load(value)
        if jar:
            csrf_cookies = '; '.join(k + '=' + v.value for k, v in jar.items())
            h['Cookie'] = '; '.join(v for v in (h.get('Cookie', ''), csrf_cookies) if v)
        h[csrf['headerName']] = csrf['token']
    request = urllib.request.Request(BASE[service] + path, headers=h,
        data=None if body is None else json.dumps(body).encode())
    try: response = OPENER.open(request, timeout=timeout)
    except urllib.error.HTTPError as error: response = error
    raw = response.read()
    try: data = json.loads(raw)
    except (ValueError, UnicodeDecodeError): data = None
    return response.status, data, response.headers, raw

def check(name, passed, detail=''):
    row = {'name': name, 'status': 'PASS' if passed else 'FAIL', 'detail': detail}
    CHECKS.append(row)
    print(json.dumps(row, ensure_ascii=False))

def credentials(kind='teacher'):
    body = {'email': 'teacher@local.dodream.invalid', 'password': ENV['LOCAL_TEACHER_PASSWORD']}
    if kind == 'other-teacher': body['email'] = 'other-teacher@local.dodream.invalid'
    if kind == 'index-owner': body['email'] = 'authz-owner@local.dodream.invalid'
    if kind == 'student': body = {'deviceId': 'dodream-local-student', 'deviceSecret': ENV['LOCAL_STUDENT_SECRET']}
    if kind == 'index-shared': body = {'deviceId':'dodream-authz-shared','deviceSecret':ENV['LOCAL_STUDENT_SECRET']}
    routekind = 'student' if kind in ('student','index-shared') else 'teacher'
    code, data, headers, _ = req('be', '/api/auth/' + routekind + '/login', body=body)
    if code != 200 or not isinstance(data, dict) or not data.get('accessToken'):
        raise RuntimeError(kind + ' login failed with HTTP ' + str(code))
    cookie = http.cookies.SimpleCookie(); cookie.load(headers.get('Set-Cookie', ''))
    refresh = cookie['refresh'].value if 'refresh' in cookie else None
    return data['accessToken'], refresh

def payload(token):
    segment = token.split('.')[1]
    return json.loads(base64.urlsafe_b64decode(segment + '=' * (-len(segment) % 4)))

def material_ids(token):
    code, data, _, _ = req('be', '/api/documents/published', token)
    if code != 200 or not data.get('materials'): raise RuntimeError('No synthetic material')
    return [m for m in data['materials'] if m.get('title','').startswith('[AUTHZ 4] ')]

def embed(token, doc):
    code, data, _, _ = req('ai', '/rag/embeddings/create', token,
        {'document_id': str(doc), 's3_url': 'https://local-fixture.invalid/'+sql('SELECT f.jsons3key FROM materials m JOIN uploaded_files f ON f.id=m.uploaded_file_id WHERE m.id='+str(int(doc))+';')})
    if code != 202 or not data.get('task_id'): return False
    task = data['task_id']
    for _ in range(40):
        code, data, _, _ = req('ai', '/rag/embeddings/status/' + task, token)
        if code == 200 and data.get('status') == 'SUCCESS': return True
        if data.get('status') == 'FAILURE': return False
        time.sleep(0.5)
    return False

def smoke():
    for service, path in [('be','/actuator/health'), ('ai','/health'), ('pdf','/health'), ('web','/')]:
        code, _, _, _ = req(service, path)
        check(service + '_health', code == 200, 'HTTP ' + str(code))
    teacher, rt = credentials('index-owner')
    student, _ = credentials('index-shared')
    check('synthetic_teacher_login', True)
    check('synthetic_student_login', True)
    code, data, web_headers, _ = req('web', '/api/auth/teacher/login', body={
        'email':'authz-owner@local.dodream.invalid', 'password':ENV['LOCAL_TEACHER_PASSWORD']},
        headers={'Origin':BASE['web']})
    check('web_browser_origin_login', code == 200 and bool(data.get('accessToken')), 'HTTP '+str(code)+'; browser Origin through nginx')
    # A second login replaces this user's single session. Refresh its current RT,
    # not the first login's now-invalid RT (same-second tokens are now unique).
    web_cookies = http.cookies.SimpleCookie()
    for value in web_headers.get_all('Set-Cookie', []): web_cookies.load(value)
    if code == 200 and 'refresh' in web_cookies: rt = web_cookies['refresh'].value
    for service, path in [('be','/api/teacher/me'), ('ai','/users/users/me'), ('web','/api/teacher/me'), ('web','/ai/users/users/me')]:
        code, _, _, _ = req(service, path, teacher)
        check(service + '_authorized_api', code == 200, 'HTTP ' + str(code))
        for label, token in [('absent', None), ('invalid', 'not-a-valid-token')]:
            code, _, _, _ = req(service, path, token)
            check(service + '_' + label + '_token_denied', code in (401,403), 'HTTP ' + str(code))
    code, _, _, _ = req('be', '/api/auth/teacher/login', body={
        'email':'authz-owner@local.dodream.invalid', 'password':'deliberately-incorrect-local-password'})
    check('incorrect_password_denied', code in (401,403), 'HTTP ' + str(code))
    materials = material_ids(teacher)
    check('published_material_read', len(materials) >= 1, 'synthetic records present')
    code, shared, _, _ = req('be', '/api/materials/shared', student)
    check('shared_material_read', code == 200 and shared.get('totalCount',0) >= 1, 'HTTP ' + str(code))
    allowed={m['materialId'] for m in materials}
    doc = next(m['materialId'] for m in shared['materials'] if m['materialId'] in allowed)
    code, data, headers, _ = req('be', f'/api/materials/shared/{doc}/json', student)
    check('sample_content_read', code == 200 and bool(data), 'HTTP ' + str(code))
    check('celery_real_queue_local_embedding', embed(teacher, doc), 'real Redis/Celery; deterministic local provider')
    code, data, headers, _ = req('ai', '/rag/chat', student, {'document_id':str(doc), 'question':'로컬 합성 자료의 내용을 알려 주세요.'})
    check('rag_chat_persisted', code == 200 and bool(data.get('session_id')), 'HTTP ' + str(code) + '; local provider')
    if code == 200:
        (RESULTS / 'synthetic-session.json').write_text(json.dumps({'session_id': data['session_id'], 'document_id': str(doc), 'student_id':payload(student)['sub']}))
    check('ai_stub_explicit', headers.get('X-DO-DREAM-External-Provider') is not None or
          (isinstance(data, dict) and ('LOCAL' in str(data.get('answer','')).upper())), 'response marker checked')
    code, _, _, _ = req('be','/api/auth/teacher/refresh', body={}, headers={'Cookie':'refresh=' + rt})
    check('redis_refresh_rotation_flow', code == 200, 'HTTP ' + str(code) + '; cookie manually supplied for HTTP local test')

def security():
    teacher, rt = credentials('index-owner'); student, _ = credentials('index-shared')
    # Positive controls prove object-policy failures are not masked by invalid token contracts.
    for who, token in [('teacher', teacher), ('student', student)]:
        for svc, route in [('be', '/api/teacher/me' if who == 'teacher' else '/api/materials/shared'), ('ai', '/users/users/me')]:
            code, _, _, _ = req(svc, route, token)
            check('positive_control_' + who + '_' + svc, code == 200, 'HTTP ' + str(code))
            if code != 200: raise RuntimeError('Positive authentication control failed')
    for service, path in [('be','/api/teacher/me'), ('ai','/users/users/me')]:
        code, _, _, _ = req(service, path, rt)
        check(service + '_refresh_must_not_authenticate_as_access', code in (401,403), 'HTTP ' + str(code))
    claim = payload(teacher)
    check('access_token_kind_claim', any(claim.get(k) == 'access' for k in ('token_use','type','typ')), 'access token needs a verifiable kind')
    ttl = claim['exp'] - claim['iat']
    CHECKS.append({'name':'actual_access_token_lifetime','status':'PASS' if ttl == 900 else 'FAIL','detail':str(ttl)+' seconds observed; phase2a policy=900'})
    materials = material_ids(teacher)
    # Owner library ordering is not a sharing contract. Select the student's
    # actual shared fixture so this remains a positive 200/no-answer assertion.
    code, shared_data, _, _ = req('be','/api/materials/shared',student)
    if code != 200: raise RuntimeError('Shared fixture prerequisite unavailable')
    shared_ids = {m['materialId'] for m in shared_data['materials']}
    shared = next((m for m in materials if m['materialId'] in shared_ids), None)
    if shared is None: raise RuntimeError('Shared fixture prerequisite unavailable')
    doc = shared['materialId']; file_id = shared['uploadedFileId']
    code, quizzes, _, _ = req('be',f'/api/materials/{doc}/quizzes',student)
    leaks = isinstance(quizzes,list) and any('correct_answer' in q for q in quizzes)
    check('student_quiz_must_exclude_correct_answer', code==200 and not leaks, 'HTTP '+str(code)+'; correct_answer present='+str(leaks))
    code, _, _, _ = req('be',f'/api/files/{file_id}/download-url')
    check('anonymous_file_url_must_be_denied', code in (401,403), 'HTTP '+str(code)+'; local signing boundary')
    # Known synthetic document, never an external URL. This is an intentionally unshared fixture.
    private = next((m for m in materials if m['materialId'] not in shared_ids), None)
    if private:
        private_doc = private['materialId']
        code, _, _, _ = req('be',f'/api/files/{private["uploadedFileId"]}/download-url',student)
        check('unshared_file_url_must_be_denied', code in (401,403,404), 'HTTP '+str(code))
        if embed(teacher, private_doc):
            code, _, _, _ = req('ai','/rag/chat',student,{'document_id':str(private_doc),'question':'합성 비공유 자료 권한 점검'})
            check('rag_unshared_document_must_be_denied', code in (401,403,404), 'HTTP '+str(code)+'; local provider')
        else:
            CHECKS.append({'name':'rag_unshared_document_must_be_denied','status':'BLOCKED','detail':'embedding prerequisite failed'})
        if (RESULTS/'synthetic-session.json').exists():
            sid=json.loads((RESULTS/'synthetic-session.json').read_text())['session_id']
            code, _, _, _ = req('ai','/rag/chat',student,{'document_id':str(private_doc),'session_id':sid,'question':'합성 세션 자료 불일치 점검'})
            check('rag_session_document_mismatch_must_be_denied',code in (400,403,404,409),'HTTP '+str(code)+'; local provider')
        else:
            CHECKS.append({'name':'rag_session_document_mismatch_must_be_denied','status':'BLOCKED','detail':'run smoke to create synthetic session first'})
    else: CHECKS.append({'name':'unshared_document_checks','status':'NOT_RUN','detail':'second fixture unavailable'})
    try:
        other,_=credentials('other-teacher')
        for svc, route in [('be','/api/teacher/me'),('ai','/users/users/me')]:
            status,_,_,_=req(svc,route,other)
            check('positive_control_other_teacher_'+svc,status==200,'HTTP '+str(status))
            if status!=200: raise RuntimeError('Other teacher positive control failed')
        sid=payload(student)['sub']
        code,data,_,_=req('ai','/rag/chat/sessions?student_id='+str(sid),other)
        check('unrelated_teacher_history_must_be_denied',code in (401,403,404),'HTTP '+str(code)+'; rows='+str(len(data) if isinstance(data,list) else 0))
    except RuntimeError: CHECKS.append({'name':'unrelated_teacher_history','status':'NOT_RUN','detail':'second teacher unavailable'})

def docker_exec(service, command, stdin=None):
    result = subprocess.run(compose_args('exec','-T',service,*command),input=stdin, capture_output=True,text=True,env=clean_env())
    if result.returncode: raise RuntimeError(service+' exec exit '+str(result.returncode))
    return result.stdout.strip()

def sql(statement):
    return docker_exec('mysql',['sh','-c','MYSQL_PWD="$MYSQL_PASSWORD" mysql --default-character-set=utf8mb4 -N -B -u"$MYSQL_USER" "$MYSQL_DATABASE"'],statement)

def persistence_pointer(doc):
    """Read only the current resource and its bound active execution, not content."""
    if not re.fullmatch(r'[1-9][0-9]*', str(doc)): raise ValueError('Invalid document ID')
    raw=sql("SELECT JSON_OBJECT('documentId',r.resource_id,'sourceRevision',r.source_revision,"
        "'sourceHash',r.current_source_hash,'activeExecution',r.active_execution_id,"
        "'candidate',e.candidate_name,'activeRevision',j.source_revision,'activeHash',j.source_hash,"
        "'activeJob',j.job_id,'indexSpec',j.index_spec,'executionState',e.state,'jobState',j.state) "
        "FROM index_resources r JOIN index_executions e ON e.id=r.active_execution_id "
        "JOIN index_jobs j ON j.id=e.job_pk AND j.resource_pk=r.id "
        "WHERE r.resource_kind='MATERIAL' AND r.resource_id="+str(doc)+';')
    return json.loads(raw) if raw else None

def persistence_readable(pointer):
    return bool(pointer and pointer['executionState']=='ACTIVE' and pointer['jobState']=='SUCCEEDED'
        and pointer['sourceRevision']==pointer['activeRevision'] and pointer['sourceHash']==pointer['activeHash'])

def persistence_digest(candidate):
    if not re.fullmatch(r'idx_[a-z0-9_]+',candidate): raise ValueError('Invalid candidate')
    code="import json,hashlib;from app.indexing.chroma import fetch;c=fetch("+repr(candidate)+");d=c.get(include=['documents','metadatas','embeddings']);v=d['embeddings'];rows=sorted([[i,d['documents'][p],d['metadatas'][p],[float(x) for x in v[p]]] for p,i in enumerate(d['ids'])]);print(json.dumps({'count':c.count(),'digest':hashlib.sha256(json.dumps(rows,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()}))"
    return json.loads(docker_exec('ai',['python','-c',code]))

def persistence_binding(session):
    session=str(uuid.UUID(session))
    code="import sqlite3,json;db=sqlite3.connect('file:/app/db_data/rag.db?mode=ro',uri=True);db.row_factory=sqlite3.Row;row=db.execute('SELECT s.id,s.user_id,s.document_id,i.source_revision,i.source_hash,(SELECT COUNT(*) FROM chat_messages m WHERE m.session_id=s.id) AS message_count FROM chat_sessions s JOIN chat_session_indexes i ON i.session_id=s.id WHERE s.id=?',("+repr(session)+",)).fetchone();print(json.dumps(dict(row) if row else None));db.close()"
    return json.loads(docker_exec('ai',['python','-c',code]))

def persistence_containers():
    """Validate ownership before selecting the nine existing primary containers."""
    gate(['config','--quiet'],compose_base(),ROOT,clean_env(),RESULTS)
    inventory=read_metadata(clean_env())
    rows={}
    for service in MAIN:
        found=[r for r in inventory if r['name']==PROJECT+'-'+service+'-1'
            and r['project']==PROJECT and r['service']==service]
        if len(found)!=1: raise RuntimeError('Owned primary container unavailable')
        rows[service]=found[0]['id']
    return persistence_inspect(rows)

def persistence_inspect(ids):
    if set(ids)!=set(MAIN) or any(not re.fullmatch(r'[0-9a-f]{64}',v) for v in ids.values()):
        raise ValueError('Invalid immutable container IDs')
    # Never inspect Env, commands or application logs.
    fmt='{{json .Id}}\t{{json .Image}}\t{{json .State.Status}}\t{{if index .State "Health"}}{{json .State.Health.Status}}{{else}}null{{end}}'
    result=subprocess.run(['docker','inspect','--format',fmt,*ids.values()],capture_output=True,
        text=True,env=clean_env(),timeout=20)
    if result.returncode: raise RuntimeError('Container metadata unavailable')
    observed={}
    for line in result.stdout.splitlines():
        identity,image,state,health=[json.loads(v) for v in line.split('\t')]
        observed[identity]={'id':identity,'image':image,'state':state,'health':health}
    if set(observed)!=set(ids.values()): raise RuntimeError('Container inventory changed')
    return {service:observed[identity] for service,identity in ids.items()}

def persistence_identity(rows):
    return {s:{k:r[k] for k in ('id','image')} for s,r in rows.items()}

def persistence_wait_ready(before):
    deadline=time.monotonic()+240
    ids={s:r['id'] for s,r in before.items()}
    while time.monotonic()<deadline:
        rows=persistence_inspect(ids)
        if persistence_identity(rows)!=persistence_identity(before): return False,rows
        if all(r['state']=='running' and r['health'] in (None,'healthy') for r in rows.values()):
            try:
                if all(req(s,p,timeout=2)[0]==200 for s,p in
                    [('be','/actuator/health'),('ai','/health'),('pdf','/health'),('web','/')]):
                    return True,rows
            except (OSError,TimeoutError): pass
        time.sleep(2)
    return False,rows

def persistence():
    # Other regressions may legitimately publish a new source after smoke. Bind a
    # fresh real session immediately before stopping; never relax RAG_SOURCE_CHANGED.
    teacher,_=credentials('index-owner'); student,_=credentials('index-shared')
    allowed={m['materialId'] for m in material_ids(teacher)}
    code,shared,_,_=req('be','/api/materials/shared',student)
    check('persistence_shared_fixture_prerequisite',code==200 and isinstance(shared,dict),'HTTP '+str(code))
    if code!=200 or not isinstance(shared,dict):return
    pointer=None
    for material in shared.get('materials',[]):
        if material['materialId'] in allowed:
            candidate=persistence_pointer(material['materialId'])
            if persistence_readable(candidate):pointer=candidate;break
    check('persistence_current_index_prerequisite',pointer is not None,'current source equals active source; no enqueue')
    if pointer is None:return
    doc=str(pointer['documentId'])
    code,data,_,_=req('ai','/rag/chat',student,{'document_id':doc,'question':'재시작 전 영속성 검사용 새 대화입니다.'})
    valid=code==200 and isinstance(data,dict) and bool(data.get('session_id'))
    check('persistence_fresh_session_created',valid,'HTTP '+str(code))
    if not valid:return
    saved={'session_id':str(uuid.UUID(data['session_id'])),'document_id':doc,'student_id':payload(student)['sub']}
    binding=persistence_binding(saved['session_id'])
    stable=bool(binding and str(binding['user_id'])==str(saved['student_id']) and binding['document_id']==doc
        and binding['source_revision']==pointer['sourceRevision'] and binding['source_hash']==pointer['sourceHash']
        and binding['message_count']>=2 and persistence_pointer(doc)==pointer)
    check('persistence_fresh_session_bound_to_current_source',stable)
    if not stable:return
    physical=persistence_digest(pointer['candidate'])
    check('persistence_active_candidate_nonempty',physical['count']>0)
    if physical['count']<=0:return
    containers=persistence_containers()
    ready=all(r['state']=='running' and r['health'] in (None,'healthy') for r in containers.values())
    check('persistence_existing_containers_ready',ready)
    if not ready:return
    evidence={'session':saved,'before':{'pointer':pointer,'binding':binding,'physical':physical,'containers':containers}}
    evidence_path=RESULTS/('persistence-session-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'-'+secrets.token_hex(4)+'.json')
    def save_evidence():
        text=json.dumps(evidence,ensure_ascii=False,indent=2)+'\n'
        evidence_path.write_text(text);(RESULTS/'persistence-session.json').write_text(text)
    save_evidence()
    marker=secrets.token_hex(16)
    sql('CREATE TABLE IF NOT EXISTS phase1_persistence_probe (id INT PRIMARY KEY, marker VARCHAR(64) NOT NULL);\nINSERT INTO phase1_persistence_probe VALUES (400000000,"'+marker+'") ON DUPLICATE KEY UPDATE marker=VALUES(marker);')
    docker_exec('redis',['redis-cli','SET','phase4:persistence',marker])
    before=sql('SELECT COUNT(*) FROM users; SELECT COUNT(*) FROM materials;')
    result=subprocess.run(compose_args('stop',*MAIN),capture_output=True,text=True,env=clean_env(),timeout=120)
    check('compose_stop',result.returncode==0,'exit '+str(result.returncode))
    if result.returncode:return
    # Give this project's just-stopped port forwarders a bounded release window.
    # An actual remaining listener is still a failure; never terminate it.
    deadline=time.monotonic()+5
    ports=[int(ENV[k]) for k in ('WEB_PORT','BE_PORT','AI_PORT','PDF_PORT')]
    while not all(port_available(p) for p in ports) and time.monotonic()<deadline:time.sleep(.25)
    released=all(port_available(p) for p in ports)
    check('loopback_ports_released_after_stop',released,'bounded read-only check; no process termination')
    if not released:return
    # start preserves the existing immutable containers; up could reconcile a
    # changed build tag and accidentally test newly-created runtime images.
    result=subprocess.run(compose_args('start',*MAIN),capture_output=True,text=True,env=clean_env(),timeout=120)
    check('compose_restart',result.returncode==0,'exit '+str(result.returncode))
    if result.returncode: return
    healthy,after_containers=persistence_wait_ready(containers)
    evidence['after']={'containers':after_containers};save_evidence()
    check('persistence_bounded_restart_readiness',healthy,'240-second health window')
    after_containers=persistence_containers()
    evidence['after']['containers']=after_containers;save_evidence()
    same=persistence_identity(after_containers)==persistence_identity(containers)
    check('persistence_same_container_ids_and_images',same,'all nine primary containers')
    if not healthy or not same:return
    check('mysql_new_marker_persisted',sql('SELECT marker FROM phase1_persistence_probe WHERE id=400000000;')==marker,'probe is not seeded by application')
    check('mysql_domain_counts_preserved',sql('SELECT COUNT(*) FROM users; SELECT COUNT(*) FROM materials;')==before,'synthetic user/material counts match')
    check('redis_new_marker_persisted',docker_exec('redis',['redis-cli','GET','phase4:persistence'])==marker,'probe is not seeded by application')
    teacher,_=credentials('index-owner')
    code,data,_,_=req('ai','/rag/chat/sessions?student_id='+str(saved['student_id']),teacher)
    check('rag_sqlite_session_persisted',code==200 and isinstance(data,list) and any(s['id']==saved['session_id'] for s in data),'same fresh session ID after restart')
    after_binding=persistence_binding(saved['session_id']);after_pointer=persistence_pointer(doc)
    after_physical=persistence_digest(pointer['candidate'])
    evidence['after'].update({'binding':after_binding,'pointer':after_pointer,'physical':after_physical});save_evidence()
    check('persistence_session_binding_and_messages_preserved',after_binding==binding)
    check('persistence_active_pointer_and_source_preserved',after_pointer==pointer)
    check('persistence_chroma_candidate_digest_preserved',after_physical==physical,'same collection/count/content/metadata/vectors')
    student,_=credentials('index-shared')
    code,data,_,_=req('ai','/rag/chat',student,{'document_id':doc,'session_id':saved['session_id'],'question':'재시작 후 합성 자료 확인'})
    check('local_embedding_provider_persisted',code==200 and isinstance(data,dict) and data.get('session_id')==saved['session_id'],
        'HTTP '+str(code)+'; same source/session, without enqueue before or after restart')

if __name__=='__main__':
    mode=sys.argv[1]
    try: {'smoke':smoke,'security':security,'persistence':persistence}[mode]()
    except Exception as error:
        # Never print HTTP bodies, tokens, or exception strings containing credentials.
        CHECKS.append({'name':mode+'_execution','status':'BLOCKED','detail':type(error).__name__})
        print(mode,'BLOCKED',type(error).__name__)
    output={'mode':mode,'checks':CHECKS,'total':len(CHECKS),
            'counts':{s:sum(c['status']==s for c in CHECKS) for s in ('PASS','FAIL','BLOCKED','NOT_RUN')}}
    (RESULTS/(mode+'-checks.json')).write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(output['counts']))
    sys.exit(1 if any(c['status'] in ('FAIL','BLOCKED') for c in CHECKS) else 0)
