#!/usr/bin/env python3
"""One disposable, labelled own Spring process against the new task-named schema."""
import json,subprocess,time,datetime
from manage import compose,RESULTS,clean_env,stop_owned_test,redact
from scope_guard import read_metadata
from indexing_migration import FRESH,MIGRATION,root_sql
NAME='dodream-phase3b-fresh-schema'

def main():
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    # Only an already explicitly created task schema may be used.
    if not (RESULTS/'index-migration-fresh-created.json').exists():raise RuntimeError('Fresh schema preparation evidence missing')
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
        evidence={'status':'PASS' if success else 'FAIL','fresh_schema':FRESH,'healthy_after_migration_before_jpa':healthy,'tables':metadata.splitlines(),'unique_constraints':constraints,'rerun_constraint_stability':constraints==rerun,'schema_preserved':True}
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

if __name__=='__main__':raise SystemExit(main())
