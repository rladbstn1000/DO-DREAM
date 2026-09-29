#!/usr/bin/env python3
"""Real localhost HTTP/DB verification. Stores statuses only, never tokens/bodies."""
import base64
import http.cookies
import json
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from manage import ROOT, RESULTS, settings, compose_args, clean_env
from scope_guard import port_available

ENV = settings()
BASE = {name: 'http://127.0.0.1:' + ENV[key] for name, key in
        [('be','BE_PORT'), ('ai','AI_PORT'), ('pdf','PDF_PORT'), ('web','WEB_PORT')]}
CHECKS = []
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs): return None
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

def req(service, path, token=None, body=None, headers=None):
    if not path.startswith('/') or path.startswith('//'):
        raise ValueError('Only explicit local paths allowed')
    h = {'Content-Type': 'application/json'}
    if token: h['Authorization'] = 'Bearer ' + token
    if headers: h.update(headers)
    # The new cookie auth contract needs a CSRF cookie/header even with expired AT.
    if body is not None and path.startswith('/api/auth/') and '/native/' not in path:
        csrf_req = urllib.request.Request(BASE[service] + '/api/auth/csrf')
        csrf_response = OPENER.open(csrf_req, timeout=20)
        csrf = json.loads(csrf_response.read())
        jar = http.cookies.SimpleCookie()
        for value in csrf_response.headers.get_all('Set-Cookie', []): jar.load(value)
        if jar:
            csrf_cookies = '; '.join(k + '=' + v.value for k, v in jar.items())
            h['Cookie'] = '; '.join(v for v in (h.get('Cookie', ''), csrf_cookies) if v)
        h[csrf['headerName']] = csrf['token']
    request = urllib.request.Request(BASE[service] + path, headers=h,
        data=None if body is None else json.dumps(body).encode())
    try: response = OPENER.open(request, timeout=20)
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
    if kind == 'student': body = {'deviceId': 'dodream-local-student', 'deviceSecret': ENV['LOCAL_STUDENT_SECRET']}
    routekind = 'student' if kind == 'student' else 'teacher'
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
    return data['materials']

def embed(token, doc):
    code, data, _, _ = req('ai', '/rag/embeddings/create', token,
        {'document_id': str(doc), 's3_url': 'https://local-fixture.invalid/sample.json'})
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
    teacher, rt = credentials()
    student, _ = credentials('student')
    check('synthetic_teacher_login', True)
    check('synthetic_student_login', True)
    code, data, web_headers, _ = req('web', '/api/auth/teacher/login', body={
        'email':'teacher@local.dodream.invalid', 'password':ENV['LOCAL_TEACHER_PASSWORD']},
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
        'email':'teacher@local.dodream.invalid', 'password':'deliberately-incorrect-local-password'})
    check('incorrect_password_denied', code in (401,403), 'HTTP ' + str(code))
    materials = material_ids(teacher)
    check('published_material_read', len(materials) >= 1, 'synthetic records present')
    code, shared, _, _ = req('be', '/api/materials/shared', student)
    check('shared_material_read', code == 200 and shared.get('totalCount',0) >= 1, 'HTTP ' + str(code))
    doc = shared['materials'][0]['materialId']
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
    teacher, rt = credentials(); student, _ = credentials('student')
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
    materials = material_ids(teacher); doc = materials[0]['materialId']; file_id = materials[0]['uploadedFileId']
    code, quizzes, _, _ = req('be',f'/api/materials/{doc}/quizzes',student)
    leaks = isinstance(quizzes,list) and any('correct_answer' in q for q in quizzes)
    check('student_quiz_must_exclude_correct_answer', code==200 and not leaks, 'HTTP '+str(code)+'; correct_answer present='+str(leaks))
    code, _, _, _ = req('be',f'/api/files/{file_id}/download-url')
    check('anonymous_file_url_must_be_denied', code in (401,403), 'HTTP '+str(code)+'; local signing boundary')
    # Known synthetic document, never an external URL. This is an intentionally unshared fixture.
    code, data, _, _ = req('be','/api/materials/shared',student)
    shared_ids = {m['materialId'] for m in data['materials']}
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
    return docker_exec('mysql',['sh','-c','MYSQL_PWD="$MYSQL_PASSWORD" mysql -N -B -u"$MYSQL_USER" "$MYSQL_DATABASE"'],statement)

def persistence():
    marker=secrets.token_hex(16)
    sql('CREATE TABLE IF NOT EXISTS phase1_persistence_probe (id INT PRIMARY KEY, marker VARCHAR(64) NOT NULL);\nINSERT INTO phase1_persistence_probe VALUES (1,"'+marker+'") ON DUPLICATE KEY UPDATE marker=VALUES(marker);')
    docker_exec('redis',['redis-cli','SET','phase1:persistence',marker])
    before=sql('SELECT COUNT(*) FROM users; SELECT COUNT(*) FROM materials;')
    saved=json.loads((RESULTS/'synthetic-session.json').read_text()) if (RESULTS/'synthetic-session.json').exists() else None
    result=subprocess.run(compose_args('stop'),capture_output=True,text=True,env=clean_env())
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
    result=subprocess.run(compose_args('up','-d','--wait','--wait-timeout','240'),capture_output=True,text=True,env=clean_env())
    check('compose_restart',result.returncode==0,'exit '+str(result.returncode))
    if result.returncode: return
    check('mysql_new_marker_persisted',sql('SELECT marker FROM phase1_persistence_probe WHERE id=1;')==marker,'probe is not seeded by application')
    check('mysql_domain_counts_preserved',sql('SELECT COUNT(*) FROM users; SELECT COUNT(*) FROM materials;')==before,'synthetic user/material counts match')
    check('redis_new_marker_persisted',docker_exec('redis',['redis-cli','GET','phase1:persistence'])==marker,'probe is not seeded by application')
    teacher,_=credentials()
    if saved:
        code,data,_,_=req('ai','/rag/chat/sessions?student_id='+str(saved['student_id']),teacher)
        check('rag_sqlite_session_persisted',code==200 and any(s['id']==saved['session_id'] for s in data),'same session ID after restart')
        student,_=credentials('student')
        code,_,_,_=req('ai','/rag/chat',student,{'document_id':saved['document_id'],'session_id':saved['session_id'],'question':'재시작 후 합성 자료 확인'})
        check('local_embedding_provider_persisted',code==200,'HTTP '+str(code)+' without enqueue after restart')
    else:
        for name in ('rag_sqlite_session_persisted','local_embedding_provider_persisted'):
            CHECKS.append({'name':name,'status':'BLOCKED','detail':'run smoke to create synthetic session first'})

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
