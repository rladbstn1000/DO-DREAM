#!/usr/bin/env python3
"""Real local HTTP + SQL object authorization regression; outputs statuses only."""
import json
import sys
import time
import uuid
import urllib.error
import urllib.request
from verify import req, check, CHECKS, ENV, BASE, OPENER, payload, sql, docker_exec
from manage import RESULTS

TOKENS={}

def request(service,path,who=None,body=None,method=None):
    token=TOKENS.get(who) if who else None
    if method is None:
        headers={'Idempotency-Key':str(uuid.uuid4())} if path.endswith('/quizzes/submit') else None
        return req(service,path,token,body,headers)
    headers={'Content-Type':'application/json'}
    if token:headers['Authorization']='Bearer '+token
    r=urllib.request.Request(BASE[service]+path,headers=headers,method=method,
        data=json.dumps(body).encode() if body is not None else None)
    try:response=OPENER.open(r,timeout=20)
    except urllib.error.HTTPError as error:response=error
    raw=response.read()
    try:data=json.loads(raw)
    except (ValueError,UnicodeDecodeError):data=None
    return response.status,data,response.headers,raw

def expect(name,service,path,who,status,body=None,method=None):
    code,data,_,_=request(service,path,who,body,method)
    check(name,code==status,f'HTTP {code}; expected {status}')
    return data if code==status else None

def login(who):
    teacher=who in ('owner','other','remote')
    body={'email':f'authz-{who}@local.dodream.invalid','password':ENV['LOCAL_TEACHER_PASSWORD']} if teacher else {
        'deviceId':'dodream-authz-'+who.removesuffix('-student'),'deviceSecret':ENV['LOCAL_STUDENT_SECRET']}
    code,data,_,_=req('be','/api/auth/'+('teacher' if teacher else 'student')+'/login',body=body)
    if code!=200 or not data.get('accessToken'):raise RuntimeError('Synthetic login failed')
    TOKENS[who]=data['accessToken'];check('authz_login_'+who,True)
    return int(payload(data['accessToken'])['sub'])

def no_answers(value):
    denied={'answer','correct_answer','correctanswer','rubric','teacher_notes','grading_criteria','explanation'}
    if isinstance(value,dict):return all(str(k).lower() not in denied and no_answers(v) for k,v in value.items())
    if isinstance(value,list):return all(no_answers(v) for v in value)
    return True

def db_counts():
    # Content/credentials never leave the service; these are only row totals.
    mysql=sql('CHECKSUM TABLE material_shares,student_quiz_logs,quizzes,materials,uploaded_files,bookmarks,grading_attempts,grading_attempt_items,grading_attempt_results; SELECT COUNT(*) FROM material_shares; SELECT COUNT(*) FROM student_quiz_logs; SELECT COUNT(*) FROM quizzes; SELECT COUNT(*) FROM materials; SELECT COUNT(*) FROM uploaded_files;')
    rag=docker_exec('ai',['python','-c',"import sqlite3,json; c=sqlite3.connect('/app/db_data/rag.db'); import hashlib; from pathlib import Path; rows=[c.execute('SELECT * FROM '+t+' ORDER BY id').fetchall() for t in ('chat_sessions','chat_messages','embedding_tasks')]; objects=[(p.name,hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(Path('/app/be-local-data/objects').glob('*.json'))]; print(hashlib.sha256(json.dumps([rows,objects],default=str).encode()).hexdigest())"])
    return mysql,rag

def embed(who,doc,url,initial=False):
    route='/rag/embeddings/create-initial' if initial else '/rag/embeddings/create'
    body={'pdf_id':doc,'s3_url':url} if initial else {'document_id':str(doc),'s3_url':url}
    data=expect('embedding_owner_enqueue_'+str(doc),'ai',route,who,202,body)
    if not data:return None
    task=data['task_id']
    for _ in range(80):
        code,state,_,_=request('ai','/rag/embeddings/status/'+task,who)
        if code!=200 or state.get('status') in ('SUCCESS','FAILURE'):break
        time.sleep(.5)
    check('embedding_owner_completes_'+str(doc),code==200 and state.get('status')=='SUCCESS','real Redis/Celery + local provider')
    return task

def run():
    ids={who:login(who) for who in ('owner','other','remote','shared','unshared','class','other-student','remote-student')}
    rows=sql("SELECT m.id,m.title,m.uploaded_file_id,f.jsons3key FROM materials m JOIN uploaded_files f ON f.id=m.uploaded_file_id WHERE m.title LIKE '[AUTHZ 3A] %' AND m.deleted_at IS NULL;")
    docs={}
    for line in rows.splitlines():
        mid,title,fid,key=line.split('\t');docs[title.replace('[AUTHZ 3A] ','')]={'id':int(mid),'file':int(fid),'url':'https://local-fixture.invalid/'+key}
    required={'editable','second-shared','class-shared','private','draft','other-owned','remote-owned'}
    if not required<=docs.keys():raise RuntimeError('Synthetic authorization fixtures missing')
    m=docs['editable'];mid=m['id'];fid=m['file'];second=docs['second-shared'];private=docs['private']
    profile=sql(f"SELECT id,classroom_id FROM student_profiles WHERE user_id={ids['shared']};").split('\t')
    spid,cid=map(int,profile)
    teacher_profile=int(sql(f"SELECT id FROM teacher_profiles WHERE user_id={ids['owner']};"))
    check('user_profile_ids_are_distinct',spid!=ids['shared'] and teacher_profile!=ids['owner'])
    for who in ids:
        expect('valid_at_be_'+who,'be','/api/teacher/me' if who in ('owner','other','remote') else '/api/materials/shared',who,200)
        expect('valid_at_ai_'+who,'ai','/users/users/me',who,200)
    for who in ('owner','other','remote'):
        data=expect('published_list_owner_only_'+who,'be','/api/documents/published',who,200)
        allowed={int(v) for v in sql(f"SELECT id FROM materials WHERE teacher_id={ids[who]} AND deleted_at IS NULL;").splitlines()}
        check('published_list_membership_'+who,bool(data) and {r['materialId'] for r in data['materials']}==allowed)
    teacher_quizzes=expect('teacher_quiz_answers_retained','be',f'/api/materials/{mid}/quizzes','owner',200)
    check('teacher_quiz_has_answer',bool(teacher_quizzes) and 'correct_answer' in teacher_quizzes[0])
    quizzes=expect('shared_student_quiz_positive','be',f'/api/materials/{mid}/quizzes','shared',200)
    check('student_quiz_allowlist',bool(quizzes) and all(set(q)<= {'id','question_number','question_type','title','content','chapter_reference','version'} for q in quizzes) and no_answers(quizzes))
    content=expect('shared_student_json_positive','be',f'/api/materials/shared/{mid}/json','shared',200)
    check('student_json_nested_answer_exclusion',bool(content) and no_answers(content) and 'AUTHZ_TEACHER_ONLY' not in json.dumps(content))
    expect('owner_raw_json_positive','be',f'/api/pdf/{fid}/json','owner',200)
    expect('owner_download_positive','be',f'/api/files/{fid}/download-url','owner',200)
    expect('class_share_positive','be',f"/api/materials/{docs['class-shared']['id']}/quizzes",'class',200)
    expect('class_share_ai_positive_identity','ai','/users/users/me','class',200)
    for d in (m,second,docs['class-shared']):embed('owner',d['id'],d['url'])
    initial_task=embed('owner',fid,m['url'],True)
    embed('owner',private['file'],private['url'],True)
    expect('private_initial_owner_positive','ai','/rag/chat','owner',200,{'document_id':'pdf_'+str(private['file']),'question':'initial positive'})
    session=expect('shared_rag_positive','ai','/rag/chat','shared',200,{'document_id':str(mid),'question':'본문을 설명해 주세요.'})
    sid=session['session_id'] if session else 'missing'
    expect('second_shared_rag_positive','ai','/rag/chat','shared',200,{'document_id':str(second['id']),'question':'내용 확인'})
    expect('class_share_rag_positive','ai','/rag/chat','class',200,{'document_id':str(docs['class-shared']['id']),'question':'내용 확인'})
    expect('owner_initial_rag_positive','ai','/rag/chat','owner',200,{'document_id':'pdf_'+str(fid),'question':'초기본 확인'})
    own_history=expect('assigned_owner_history_positive','ai',f"/rag/chat/sessions?student_id={ids['shared']}",'owner',200)
    check('assigned_owner_history_contains_session',isinstance(own_history,list) and any(s['id']==sid for s in own_history))
    expect('self_history_detail_positive','ai',f"/rag/chat/sessions/{sid}/messages?student_id={ids['shared']}",'shared',200)
    # The teacher's existing library includes their own drafts, which is permitted.
    expect('owner_concept_processing_positive','ai','/document/process-concept-check','owner',200,{'uploaded_file_id':fid,'concept_checks':[{'contents':'synthetic permitted text'}]})
    for who in ('owner','shared'):
        expect('progress_positive_'+who,'be',f"/api/progress/students/{ids['shared']}/materials/{mid}",who,200)
        expect('stats_positive_'+who,'be',f"/api/stats/student/{ids['shared']}/materials",who,200)
    title_id=content['chapters'][0]['id']
    current=expect('bookmark_list_positive','be',f'/api/bookmarks/material/{mid}','shared',200)
    # Dedicated AUTHZ fixture: retain any pre-existing bookmark membership.
    original_bookmarked=title_id in current.get('bookmarkedTitleIds',[])
    if not original_bookmarked:expect('bookmark_create_positive','be','/api/bookmarks/toggle','shared',200,{'materialId':mid,'titleId':title_id})
    try:
        bookmarks=expect('bookmark_read_positive','be','/api/bookmarks','shared',200)
        check('bookmark_answer_exclusion',isinstance(bookmarks,list) and any(b['materialId']==mid for b in bookmarks) and 'AUTHZ_TEACHER_ONLY' not in json.dumps(bookmarks) and no_answers(bookmarks))
    finally:
        if not original_bookmarked:expect('bookmark_restore_membership','be','/api/bookmarks/toggle','shared',200,{'materialId':mid,'titleId':title_id})
    before=db_counts()
    for route,body in (('/document/parse-pdf-from-cloudfront',{'uploaded_file_id':fid,'cloudfront_url':'https://local-fixture.invalid/sample.pdf'}),('/document/process-concept-check',{'uploaded_file_id':fid,'concept_checks':[{'contents':'synthetic permitted text'}]})):
        expect('anonymous_'+route,'ai',route,None,401,body)
    for route in (f'/api/files/{fid}/download-url',f'/api/pdf/{fid}/json',f'/api/materials/{mid}/quizzes'):
        expect('anonymous_'+route,'be',route,None,401)
    for who in ('other','remote'):
        expect(who+'_direct_parser','ai','/document/parse-pdf-from-cloudfront',who,404,{'uploaded_file_id':fid,'cloudfront_url':'https://local-fixture.invalid/sample.pdf'})
        expect(who+'_direct_concept','ai','/document/process-concept-check',who,404,{'uploaded_file_id':fid,'concept_checks':[{'contents':'synthetic permitted text'}]})
        expect(who+'_student_progress','be',f"/api/progress/students/{ids['shared']}/materials/{mid}",who,404)
        expect(who+'_student_stats','be',f"/api/stats/student/{ids['shared']}/materials",who,404)
        for suffix in ('json','json-url','concept-check','temp-data','extract-text'):
            expect(who+'_file_'+suffix,'be',f'/api/pdf/{fid}/{suffix}',who,404)
        expect(who+'_download','be',f'/api/files/{fid}/download-url',who,404)
        expect(who+'_quiz_read','be',f'/api/materials/{mid}/quizzes',who,404)
        expect(who+'_quiz_save','be',f'/api/materials/{mid}/quizzes',who,404,[])
        expect(who+'_publish','be',f'/api/documents/{fid}/publish',who,404,{'materialTitle':'unauthorized','editedJson':{}})
        expect(who+'_temp_save','be',f'/api/pdf/{fid}/temp-save',who,404,{'materialTitle':'unauthorized','editedJson':{}})
        expect(who+'_label','be','/api/documents/label',who,404,{'materialId':mid,'label':'RED'},'PATCH')
        expect(who+'_delete','be',f'/api/documents/{mid}',who,404,method='DELETE')
        expect(who+'_embed','ai','/rag/embeddings/create',who,404,{'document_id':str(mid),'s3_url':m['url']})
        expect(who+'_initial_embed','ai','/rag/embeddings/create-initial',who,404,{'pdf_id':fid,'s3_url':m['url']})
        expect(who+'_generate','ai','/rag/quiz/generate',who,404,{'document_id':str(mid),'num_questions':5})
        expect(who+'_history_list','ai',f"/rag/chat/sessions?student_id={ids['shared']}",who,404)
        expect(who+'_history_detail','ai',f"/rag/chat/sessions/{sid}/messages?student_id={ids['shared']}",who,404)
        if initial_task:expect(who+'_task_status','ai','/rag/embeddings/status/'+initial_task,who,404)
    for who in ('unshared','class','other-student','remote-student'):
        expect(who+'_quiz_denied','be',f'/api/materials/{mid}/quizzes',who,404)
        expect(who+'_json_denied','be',f'/api/materials/shared/{mid}/json',who,404)
        expect(who+'_rag_denied','ai','/rag/chat',who,404,{'document_id':str(mid),'question':'denied'})
    for suffix in ('json','json-url','concept-check','temp-data','extract-text'):
        expect('student_editor_'+suffix,'be',f'/api/pdf/{fid}/{suffix}','shared',403)
    expect('student_signed_raw_url','be',f'/api/files/{fid}/download-url','shared',403)
    expect('student_direct_parser','ai','/document/parse-pdf-from-cloudfront','shared',403,{'uploaded_file_id':fid,'cloudfront_url':'https://local-fixture.invalid/sample.pdf'})
    expect('student_direct_concept','ai','/document/process-concept-check','shared',403,{'uploaded_file_id':fid,'concept_checks':[{'contents':'synthetic permitted text'}]})
    expect('unshared_bookmark_write','be','/api/bookmarks/toggle','unshared',404,{'materialId':mid,'titleId':title_id})
    expect('unshared_bookmark_read','be',f'/api/bookmarks/material/{mid}','unshared',404)
    expect('student_upload_url','be','/api/files/presigned-url','shared',403,{'fileName':'test.pdf','contentType':'application/pdf'})
    expect('student_quiz_save','be',f'/api/materials/{mid}/quizzes','shared',403,[])
    expect('student_generate','ai','/rag/quiz/generate','shared',403,{'document_id':str(mid),'num_questions':5})
    expect('student_initial','ai','/rag/chat','shared',403,{'document_id':'pdf_'+str(fid),'question':'denied'})
    for key in ('private','draft'):
        expect(key+'_student_read','be',f"/api/materials/{docs[key]['id']}/quizzes",'shared',404)
        expect(key+'_student_rag','ai','/rag/chat','shared',404,{'document_id':str(docs[key]['id']),'question':'denied'})
    for bad in ('0','01','+1','1/../2',str(mid)+'_suffix','pdf_01'):
        expect('canonical_id_'+bad,'ai','/rag/chat','owner',400,{'document_id':bad,'question':'denied'})
    expect('session_cross_document_both_shared','ai','/rag/chat','shared',409,{'document_id':str(second['id']),'session_id':sid,'question':'denied'})
    expect('session_cross_user','ai','/rag/chat','owner',404,{'document_id':str(mid),'session_id':sid,'question':'denied'})
    expect('cross_student_history','ai',f"/rag/chat/sessions/{sid}/messages?student_id={ids['shared']}",'class',404)
    expect('object_url_mismatch','ai','/rag/embeddings/create','owner',400,{'document_id':str(mid),'s3_url':second['url']})
    expect('initial_url_mismatch','ai','/rag/embeddings/create-initial','owner',400,{'pdf_id':fid,'s3_url':second['url']})
    expect('mixed_share_targets','be','/api/materials/share','owner',404,{'materialId':private['id'],'shares':{str(cid):{'type':'INDIVIDUAL','studentIds':[ids['shared'],ids['other-student']]}}})
    qid=quizzes[0]['id']
    q2_record=expect('second_quiz_positive','be',f"/api/materials/{second['id']}/quizzes",'shared',200)[0]
    q2=q2_record['id']
    expect('quiz_cross_material_be','be',f'/api/materials/{mid}/quizzes/submit','shared',400,{'answers':[{'quizId':q2,'version':q2_record['version'],'answer':'얼음'}]})
    expect('quiz_unshared_submit','be',f'/api/materials/{mid}/quizzes/submit','unshared',404,{'answers':[{'quizId':qid,'version':quizzes[0]['version'],'answer':'얼음'}]})
    expect('quiz_cross_material_ai','ai','/rag/quiz/grade-batch','shared',422,{'material_id':mid,'student_answers':[{'question_id':q2,'student_answer':'얼음'}]})
    expect('quiz_client_authority_fields','ai','/rag/quiz/grade-batch','shared',422,{'material_id':mid,'student_answers':[{'question_id':qid,'student_answer':'얼음'}],'questions':[{'correct_answer':'forged'}],'studentId':ids['other-student'],'score':100})
    check('denial_group_no_mysql_or_rag_rows_changed',db_counts()==before,'real MySQL checksums/counts, SQLite row digest, synthetic object file digests; provider call counts verified separately in unit tests')
    submitted=expect('submit_server_quiz_positive','be',f"/api/materials/{second['id']}/quizzes/submit",'shared',200,{
        'answers':[{'quizId':q2,'version':q2_record['version'],'answer':'얼음','correct_answer':'forged','score':100}],
        'studentId':ids['other-student'],'score':100,'correct_answer':'forged'})
    check('submit_feedback_uses_server_answer',bool(submitted) and all(r.get('correct_answer')=='얼음' for r in submitted))
    owned_log=sql(f"SELECT COUNT(*) FROM student_quiz_logs WHERE quiz_id={int(q2)} AND student_id={ids['shared']}; SELECT COUNT(*) FROM student_quiz_logs WHERE quiz_id={int(q2)} AND student_id={ids['other-student']};").splitlines()
    check('submit_ignores_forged_record_owner',int(owned_log[0])>=1 and int(owned_log[1])==0)
    # Revoke only this dedicated synthetic share and restore through the normal API.
    restore={'materialId':mid,'shares':{str(cid):{'type':'INDIVIDUAL','studentIds':[ids['shared']]}}}
    try:
        expect('owner_revoke_share','be',f"/api/materials/{mid}/shares/{ids['shared']}",'owner',204,method='DELETE')
        for label,svc,path,who,body in (
            ('quiz','be',f'/api/materials/{mid}/quizzes','shared',None),
            ('json','be',f'/api/materials/shared/{mid}/json','shared',None),
            ('rag','ai','/rag/chat','shared',{'document_id':str(mid),'session_id':sid,'question':'denied'}),
            ('history_detail','ai',f"/rag/chat/sessions/{sid}/messages?student_id={ids['shared']}",'owner',None)):
            expect('share_revoked_'+label,svc,path,who,404,body)
        listing=expect('share_revoked_history_list','ai',f"/rag/chat/sessions?student_id={ids['shared']}",'owner',200)
        check('share_revoked_history_filtered',isinstance(listing,list) and not any(s['id']==sid for s in listing))
        listing=expect('share_revoked_material_list','be','/api/materials/shared','shared',200)
        check('share_revoked_material_filtered',bool(listing) and not any(s['materialId']==mid for s in listing['materials']))
    finally:expect('share_restored','be','/api/materials/share','owner',200,restore)
    try:
        sql(f'UPDATE student_profiles SET classroom_id=NULL WHERE id={spid} AND user_id={ids["shared"]} AND classroom_id={cid};')
        expect('current_assignment_revoked_be','be',f'/api/materials/{mid}/quizzes','shared',404)
        expect('current_assignment_revoked_ai','ai','/rag/chat','shared',404,{'document_id':str(mid),'session_id':sid,'question':'denied'})
        expect('current_assignment_revoked_teacher_history','ai',f"/rag/chat/sessions?student_id={ids['shared']}",'owner',404)
    finally:sql(f'UPDATE student_profiles SET classroom_id={cid} WHERE id={spid} AND user_id={ids["shared"]} AND classroom_id IS NULL;')
    try:
        sql(f"UPDATE materials SET deleted_at=NOW() WHERE id={private['id']} AND teacher_id={ids['owner']} AND deleted_at IS NULL;")
        expect('softdeleted_file_be','be',f"/api/pdf/{private['file']}/json",'owner',404)
        expect('softdeleted_initial_ai','ai','/rag/chat','owner',404,{'document_id':'pdf_'+str(private['file']),'question':'denied'})
        expect('softdeleted_enqueue_ai','ai','/rag/embeddings/create-initial','owner',404,{'pdf_id':private['file'],'s3_url':private['url']})
    finally:sql(f"UPDATE materials SET deleted_at=NULL WHERE id={private['id']} AND teacher_id={ids['owner']};")
    expect('softdeleted_restore_positive','ai','/rag/chat','owner',200,{'document_id':'pdf_'+str(private['file']),'question':'restored'})
    expect('assignment_restored_be','be',f'/api/materials/{mid}/quizzes','shared',200)
    expect('assignment_restored_ai','ai','/rag/chat','shared',200,{'document_id':str(mid),'session_id':sid,'question':'복구 확인'})

if __name__=='__main__':
    try:run()
    except Exception as error:
        CHECKS.append({'name':'authorization_execution','status':'BLOCKED','detail':type(error).__name__})
        print('authorization BLOCKED',type(error).__name__)
    output={'mode':'authorization','checks':CHECKS,'total':len(CHECKS),'counts':{s:sum(c['status']==s for c in CHECKS) for s in ('PASS','FAIL','BLOCKED','NOT_RUN')}}
    (RESULTS/'authorization-checks.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(output['counts']))
    sys.exit(1 if any(c['status'] in ('FAIL','BLOCKED') for c in CHECKS) else 0)
