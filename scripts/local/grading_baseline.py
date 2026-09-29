#!/usr/bin/env python3
"""One-time phase 2-B behavior reproduction on new synthetic phase 3-A rows."""
import json
from verify import req,sql
from verify_authorization import login,TOKENS,request
from grading_fixtures import clone_material,clone_statement
from manage import RESULTS

def main():
    destination=RESULTS/'grading-before.json'
    if destination.exists():raise RuntimeError('Preserve original reproduction')
    login('owner');student_id=login('shared')
    source=int(sql("SELECT id FROM materials WHERE title='[AUTHZ LOCAL] second-shared';"))
    mid=clone_material(source,'[GRADING LOCAL] baseline')
    sql(clone_statement('quizzes',f'material_id={mid} AND question_number=1',{'question_number':'2','title':"'Baseline second question'"}))
    status,qs,_,_=req('be',f'/api/materials/{mid}/quizzes',TOKENS['owner'])
    if status!=200 or len(qs)!=2:raise RuntimeError('Dedicated two-question fixture unavailable')
    body={'answers':[{'quizId':q['id'],'answer':'얼음'} for q in qs]}
    count=lambda:int(sql(f'SELECT COUNT(*) FROM student_quiz_logs WHERE quiz_id IN (SELECT id FROM quizzes WHERE material_id={mid}) AND student_id={student_id};'))
    before=count();first=req('be',f'/api/materials/{mid}/quizzes/submit',TOKENS['shared'],body);after1=count()
    second=req('be',f'/api/materials/{mid}/quizzes/submit',TOKENS['shared'],body);after2=count()
    original=[q['correct_answer'] for q in first[1]]
    edits=[{k:v for k,v in q.items() if k!='id'} for q in qs]
    for q in edits:q['correct_answer']='변경된 합성 정답'
    edited=req('be',f'/api/materials/{mid}/quizzes',TOKENS['owner'],edits)
    history=req('be',f'/api/materials/{mid}/quizzes/history',TOKENS['shared'])
    changed=bool(history[1]) and all(q.get('correct_answer')=='변경된 합성 정답' for q in history[1])
    out={'source_commit':'eba04683a263b4a0fd327d428c1a4b3d693aee53','material_id':mid,'dedicated_rows_only':True,'checks':[
      {'name':'duplicate_retransmission','kind':'EXECUTED','status':'FAIL' if first[0]==second[0]==200 and after2-after1==2 else 'UNVERIFIED','http':[first[0],second[0]],'log_counts':[before,after1,after2]},
      {'name':'historical_answer_changes_with_live_quiz','kind':'EXECUTED','status':'FAIL' if edited[0]==history[0]==200 and changed else 'UNVERIFIED','original_answer_retained':not changed},
      {'name':'provider_wait_inside_transaction','kind':'STATIC_ONLY','status':'FAIL','evidence':'QuizService.gradeAndLog @Transactional encompasses WebClient.block; no runtime boundary probe in baseline'},
      {'name':'malformed_results','kind':'STATIC_ONLY','status':'FAIL','evidence':'BE count/ID check exists; primitive boolean coercion and AI per-question exception fallback to false remain'},
      {'name':'crash_recovery_state','kind':'STATIC_ONLY','status':'FAIL','evidence':'No durable attempt or dispatch/generation/deadline record; existing logs alone cannot identify unknown external result'}]}
    destination.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(out,ensure_ascii=False))
if __name__=='__main__':main()
