#!/usr/bin/env python3
"""One disposable, labelled own Spring process against the new task-named schema."""
import json,subprocess,time,datetime,sys,re,hashlib
from manage import compose,RESULTS,clean_env,stop_owned_test,redact
from scope_guard import read_metadata
from indexing_migration import FRESH,MIGRATION,root_sql
NAME='dodream-phase3b-fresh-schema'

HARDENING_SCHEMA='dodream_portfolio_hardening_fresh'
CONTRACT_TABLES=('grading_attempts','grading_attempt_items','grading_attempt_results','index_resources','index_jobs','index_executions','quizzes','student_quiz_logs')
REQUIRED_UNIQUE={
    ('grading_attempts','attempt_id'),('grading_attempts','student_id,idempotency_key'),
    ('grading_attempt_items','attempt_id,quiz_id'),('grading_attempt_results','attempt_id,quiz_id'),
    ('student_quiz_logs','attempt_id,quiz_id'),('index_resources','resource_kind,resource_id'),
    ('index_jobs','job_id'),('index_jobs','resource_pk,source_revision,index_spec'),
    ('index_executions','job_pk,generation'),('index_executions','candidate_name'),
}
REQUIRED_FOREIGN={
    ('grading_attempt_items','fk_grading_item_attempt','attempt_id','grading_attempts','id'),
    ('grading_attempt_results','fk_grading_result_item','attempt_id,quiz_id','grading_attempt_items','attempt_id,quiz_id'),
    ('index_jobs','fk_index_job_resource','resource_pk','index_resources','id'),
    ('index_executions','fk_index_execution_job','job_pk','index_jobs','id'),
}
REQUIRED_CHECK={
    'ck_index_resource_kind':"resource_kind IN ('MATERIAL','PDF')",
    'ck_index_resource_ids':'resource_id>0 AND owner_id>0 AND source_revision>=0 AND request_seq>=0',
    'ck_index_job_snapshot':'snapshot_bytes>0 AND snapshot_bytes<=2097152 AND OCTET_LENGTH(snapshot_json)=snapshot_bytes AND JSON_VALID(snapshot_json)',
    'ck_index_job_generation':'execution_generation>=0 AND execution_generation<=3 AND delivery_attempts>=0 AND delivery_attempts<=5',
    'ck_index_execution_generation':'generation>=1 AND generation<=3',
}
REQUIRED_NONNULL={
    'grading_attempts':'id attempt_id student_id material_id idempotency_key request_fingerprint state execution_generation created_at',
    'grading_attempt_items':'attempt_id quiz_id quiz_version question_number title question_content correct_answer student_answer grading_version',
    'grading_attempt_results':'attempt_id quiz_id is_correct ai_feedback',
    'index_resources':'id resource_kind resource_id owner_id source_revision current_source_hash request_seq activation_count created_at updated_at',
    'index_jobs':'id job_id resource_pk source_revision source_hash snapshot_json snapshot_bytes index_spec request_seq state delivery_state delivery_attempts next_delivery_at execution_generation created_at updated_at',
    'index_executions':'id job_pk generation candidate_name claim_token lease_until state embedding_calls started_at',
    'quizzes':'version correct_answer', 'student_quiz_logs':'student_answer',
}


def normalize_check(value):
    # mysql batch output escapes literal quotes; metadata renders OCTET_LENGTH as its
    # byte-counting synonym LENGTH. CHAR_LENGTH must remain distinct.
    value=re.sub(r"\\+(?=')",'',value.lower())
    value=re.sub(r"_[a-z0-9]+(?=')",'',value)
    value=re.sub(r'\boctet_length\b','length',value)
    return re.sub(r'[\s`()]+','',value)


def inspect_contract():
    if FRESH != HARDENING_SCHEMA:raise RuntimeError('Detailed replay is restricted to the hardening schema')
    tables=','.join("'"+table+"'" for table in CONTRACT_TABLES)
    condition="TABLE_SCHEMA='"+FRESH+"' AND TABLE_NAME IN ("+tables+")"
    return {
        'columns':root_sql("SELECT TABLE_NAME,COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,COALESCE(COLLATION_NAME,'-') FROM information_schema.COLUMNS WHERE "+condition+' ORDER BY TABLE_NAME,ORDINAL_POSITION;'),
        'unique':root_sql('SELECT TABLE_NAME,INDEX_NAME,GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) FROM information_schema.STATISTICS WHERE '+condition+' AND NON_UNIQUE=0 GROUP BY TABLE_NAME,INDEX_NAME ORDER BY TABLE_NAME,INDEX_NAME;'),
        'foreign':root_sql('SELECT TABLE_NAME,CONSTRAINT_NAME,GROUP_CONCAT(COLUMN_NAME ORDER BY ORDINAL_POSITION),REFERENCED_TABLE_NAME,GROUP_CONCAT(REFERENCED_COLUMN_NAME ORDER BY ORDINAL_POSITION) FROM information_schema.KEY_COLUMN_USAGE WHERE '+condition+' AND REFERENCED_TABLE_NAME IS NOT NULL GROUP BY TABLE_NAME,CONSTRAINT_NAME,REFERENCED_TABLE_NAME ORDER BY TABLE_NAME,CONSTRAINT_NAME;'),
        'checks':root_sql("SELECT t.TABLE_NAME,t.CONSTRAINT_NAME,t.ENFORCED,c.CHECK_CLAUSE FROM information_schema.TABLE_CONSTRAINTS t JOIN information_schema.CHECK_CONSTRAINTS c ON t.CONSTRAINT_SCHEMA=c.CONSTRAINT_SCHEMA AND t.CONSTRAINT_NAME=c.CONSTRAINT_NAME WHERE t.TABLE_SCHEMA='"+FRESH+"' AND t.TABLE_NAME IN ("+tables+") AND t.CONSTRAINT_TYPE='CHECK' ORDER BY t.TABLE_NAME,t.CONSTRAINT_NAME;"),
    }


def contract_failures(snapshot):
    unique={(row[0],row[2]) for line in snapshot['unique'].splitlines() if len(row:=line.split('\t'))==3}
    foreign={tuple(line.split('\t')) for line in snapshot['foreign'].splitlines()}
    checks={row[1]:(row[2],row[3]) for line in snapshot['checks'].splitlines() if len(row:=line.split('\t'))==4}
    columns={(row[0],row[1]):row[2:] for line in snapshot['columns'].splitlines() if len(row:=line.split('\t'))==5}
    failures=[]
    failures.extend('missing_unique:'+':'.join(value) for value in sorted(REQUIRED_UNIQUE-unique))
    failures.extend('missing_foreign:'+value[1] for value in sorted(REQUIRED_FOREIGN-foreign))
    for name,clause in REQUIRED_CHECK.items():
        actual=checks.get(name)
        if actual is None or actual[0]!='YES' or normalize_check(actual[1])!=normalize_check(clause):failures.append('invalid_check:'+name)
    for table,names in REQUIRED_NONNULL.items():
        for name in names.split():
            if columns.get((table,name),['',''])[1]!='NO':failures.append('missing_nonnull:'+table+'.'+name)
    for table,name in [('grading_attempts','attempt_id'),('grading_attempts','idempotency_key'),('grading_attempts','request_fingerprint'),('index_jobs','job_id'),('index_jobs','source_hash'),('index_jobs','index_spec'),('index_executions','candidate_name'),('index_executions','claim_token')]:
        if columns.get((table,name),['','',''])[2]!='ascii_bin':failures.append('invalid_collation:'+table+'.'+name)
    for table,name in [('grading_attempt_items','question_content'),('grading_attempt_items','correct_answer'),('grading_attempt_items','student_answer'),('quizzes','correct_answer'),('student_quiz_logs','student_answer')]:
        if columns.get((table,name),[''])[0]!='text':failures.append('invalid_text:'+table+'.'+name)
    for name in ('attempt_id','submitted_at','snapshot_correct_answer','snapshot_question_content','snapshot_quiz_version','grading_version'):
        if columns.get(('student_quiz_logs',name),['',''])[1]!='YES':failures.append('invalid_legacy_nullable:'+name)
    if columns.get(('index_jobs','snapshot_json'),['','',''])!=['longtext','NO','utf8mb4_bin']:failures.append('invalid_snapshot_json')
    return failures


def hardening_contract():
    if FRESH != HARDENING_SCHEMA:raise RuntimeError('Detailed replay is restricted to the hardening schema')
    created=json.loads((RESULTS/'index-migration-fresh-created.json').read_text())
    if created.get('schema')!=FRESH or created.get('status')!='PASS':raise RuntimeError('Hardening creation evidence missing')
    before=inspect_contract()
    failures=contract_failures(before)
    # Do not repair a surprising schema implicitly: pre-replay assertions must already pass.
    migrations=[MIGRATION.with_name('V003__grading_attempts.sql'),MIGRATION]
    after=None
    if not failures:
        root_sql('USE '+FRESH+';\n'+'\n'.join(path.read_text() for path in migrations))
        after=inspect_contract()
        failures=contract_failures(after)
    stable=after is not None and before==after
    result={'status':'PASS' if stable and not failures else 'FAIL','fresh_schema':FRESH,
        'application_start':'NOT_RUN_EXISTING_FRESH_SCHEMA_INSPECTION','replayed_migrations':[path.name for path in migrations] if after is not None else [],
        'migration_sha256':{path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in migrations},
        'required_unique':len(REQUIRED_UNIQUE),'required_foreign':len(REQUIRED_FOREIGN),'required_enforced_checks':len(REQUIRED_CHECK),
        'required_nonnull_columns':sum(len(names.split()) for names in REQUIRED_NONNULL.values()),
        'contract_failures':failures,'rerun_metadata_stable':stable,'before':before,'after':after,'schema_preserved':True}
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    for name in ('hardening-schema-contract.json','hardening-schema-contract-'+stamp+'.json'):
        (RESULTS/name).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({key:value for key,value in result.items() if key not in ('before','after')}))
    return 0 if result['status']=='PASS' else 1

def main():
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    # Only an already explicitly created task schema may be used.
    if not (RESULTS/'index-migration-fresh-created.json').exists():raise RuntimeError('Fresh schema preparation evidence missing')
    if json.loads((RESULTS/'index-migration-fresh-created.json').read_text()).get('schema')!=FRESH:
        raise RuntimeError('Fresh schema evidence does not match the selected schema')
    result=compose('index-migration-fresh-start','run','--rm','--no-deps','-d','--name',NAME,'-e','MYSQL_DATABASE='+FRESH,'be')
    if result.returncode:return result.returncode
    healthy=False;identity=None;log_process=None
    previous=RESULTS/'index-migration-fresh.json'
    if previous.exists():
        (RESULTS/('index-migration-fresh-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.json')).write_bytes(previous.read_bytes())
    try:
        until=time.monotonic()+120
        while time.monotonic()<until:
            row=next((r for r in read_metadata(clean_env()) if r['name']==NAME),None)
            if row is None:break
            if row['project']!='dodream-phase1' or row['service']!='be' or row['task']!='phase3b':raise RuntimeError('Fresh process ownership failed')
            identity=row['id']
            if log_process is None:
                log_process=subprocess.Popen(['docker','logs','--follow',identity],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,env=clean_env())
            state=subprocess.run(['docker','inspect','--format','{{.State.Health.Status}}',identity],capture_output=True,text=True,env=clean_env())
            if state.returncode==0 and state.stdout.strip()=='healthy':healthy=True;break
            if row['state'] in ('exited','dead'):break
            time.sleep(2)
        metadata=root_sql("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA='"+FRESH+"' ORDER BY TABLE_NAME;")
        constraints=root_sql("SELECT TABLE_NAME,INDEX_NAME,GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA='"+FRESH+"' AND NON_UNIQUE=0 AND INDEX_NAME IN ('uq_index_resource','uq_index_job_source_spec','uq_index_execution_generation','uq_index_candidate') GROUP BY TABLE_NAME,INDEX_NAME;")
        root_sql('USE '+FRESH+';\n'+MIGRATION.read_text())
        rerun=root_sql("SELECT TABLE_NAME,INDEX_NAME,GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA='"+FRESH+"' AND NON_UNIQUE=0 AND INDEX_NAME IN ('uq_index_resource','uq_index_job_source_spec','uq_index_execution_generation','uq_index_candidate') GROUP BY TABLE_NAME,INDEX_NAME;")
        success=healthy and all(t in metadata.splitlines() for t in ('index_resources','index_jobs','index_executions','grading_attempts','grading_attempt_items','grading_attempt_results','student_quiz_logs','quizzes')) and 'resource_kind,resource_id' in constraints and 'resource_pk,source_revision,index_spec' in constraints and 'job_pk,generation' in constraints and constraints==rerun
        evidence={'status':'PASS' if success else 'FAIL','fresh_schema':FRESH,'healthy_after_migration_and_jpa':healthy,'tables':metadata.splitlines(),'unique_constraints':constraints,'rerun_constraint_stability':constraints==rerun,'schema_preserved':True}
        (RESULTS/'index-migration-fresh.json').write_text(json.dumps(evidence,indent=2)+'\n');print(json.dumps(evidence))
        return 0 if success else 1
    finally:
        if identity and any(r['name']==NAME for r in read_metadata(clean_env())):
            stopped=stop_owned_test(NAME)
            if stopped.returncode:raise RuntimeError('Own fresh process could not be stopped')
        if log_process is not None:
            logged,_=log_process.communicate(timeout=15)
            sanitized=redact(logged)
            (RESULTS/('index-migration-fresh-sanitized-'+stamp+'.log')).write_text(sanitized)
            (RESULTS/'index-migration-fresh-sanitized.log').write_text(sanitized)

if __name__=='__main__':
    if sys.argv[1:]==['--hardening-inspect']:
        FRESH=HARDENING_SCHEMA
        raise SystemExit(hardening_contract())
    if sys.argv[1:]==['--hardening']:
        FRESH='dodream_portfolio_hardening_fresh'
        NAME='dodream-phase3b-hardening-fresh'
    elif sys.argv[1:]:
        raise SystemExit('Use no argument, --hardening or --hardening-inspect')
    raise SystemExit(main())
