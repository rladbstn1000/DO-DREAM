#!/usr/bin/env python3
"""Apply the versioned additive migration only through the fixed local MySQL service."""
import json,re,sys
from manage import ROOT,RESULTS,compose
from verify import sql,docker_exec
MIGRATION=ROOT/'be/src/main/resources/db/migration/V003__grading_attempts.sql'
FRESH='dodream_phase3a_fresh_v2'

def inspect():
    return {
      'columns':sql("SELECT TABLE_NAME,COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,COALESCE(COLLATION_NAME,'') FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND (TABLE_NAME LIKE 'grading_attempt%' OR (TABLE_NAME='quizzes' AND COLUMN_NAME='version') OR (TABLE_NAME='student_quiz_logs' AND COLUMN_NAME IN ('attempt_id','submitted_at','snapshot_correct_answer','snapshot_question_content','snapshot_quiz_version','grading_version'))) ORDER BY TABLE_NAME,ORDINAL_POSITION;"),
      'indexes':sql("SELECT TABLE_NAME,INDEX_NAME,NON_UNIQUE,GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND (TABLE_NAME LIKE 'grading_attempt%' OR (TABLE_NAME='student_quiz_logs' AND INDEX_NAME='uq_quiz_log_attempt')) GROUP BY TABLE_NAME,INDEX_NAME,NON_UNIQUE ORDER BY TABLE_NAME,INDEX_NAME;")}

def forward():
    before=inspect();sql(MIGRATION.read_text());first=inspect();sql(MIGRATION.read_text());second=inspect()
    valid='uq_grading_student_key\t0\tstudent_id,idempotency_key' in second['indexes'] and 'idempotency_key\tchar(36)\tNO\tascii_bin' in second['columns']
    result={'status':'PASS' if first==second and valid else 'FAIL','rerun_unchanged':first==second,'actual_constraints':valid,'before':before,'after':second}
    (RESULTS/'migration-forward.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ('before','after')}))
    if result['status']!='PASS':raise RuntimeError('Schema validation failed')

def root_sql(statement):
    return docker_exec('mysql',['sh','-c','MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql --default-character-set=utf8mb4 -N -B -uroot'],statement)

def fresh_prepare():
    # New, task-named schema only. Never drop or reset an existing schema.
    exists=root_sql("SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='"+FRESH+"';")
    if exists!='0':raise RuntimeError('Fresh schema already exists; preserve it and inspect prior run')
    root_sql('CREATE DATABASE '+FRESH+' CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci; GRANT ALL ON '+FRESH+".* TO 'dodream'@'%';")
    root_sql('USE '+FRESH+';\n'+MIGRATION.read_text())
    (RESULTS/'migration-fresh-created.json').write_text(json.dumps({'schema':FRESH,'status':'PASS','migration_before_jpa':True})+'\n')
    print('New dedicated local schema created; migration applied before first JPA startup')

if __name__=='__main__':{'forward':forward,'fresh-prepare':fresh_prepare}[sys.argv[1]]()
