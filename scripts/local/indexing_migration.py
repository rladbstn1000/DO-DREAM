#!/usr/bin/env python3
"""Additive 3-B migration, inspected on the owned current and fresh test schemas."""
import json
import sys
from manage import ROOT, RESULTS
from verify import sql
from grading_migration import root_sql

MIGRATION=ROOT/'be/src/main/resources/db/migration/V004__indexing_ledger.sql'
FRESH='dodream_phase3b_fresh'

def inspect():
    return {'columns':sql("SELECT TABLE_NAME,COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,COALESCE(COLLATION_NAME,'') FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN ('index_resources','index_jobs','index_executions') ORDER BY TABLE_NAME,ORDINAL_POSITION;"),
            'indexes':sql("SELECT TABLE_NAME,INDEX_NAME,NON_UNIQUE,GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN ('index_resources','index_jobs','index_executions') GROUP BY TABLE_NAME,INDEX_NAME,NON_UNIQUE ORDER BY TABLE_NAME,INDEX_NAME;")}

def forward():
    before=inspect();sql(MIGRATION.read_text());first=inspect();sql(MIGRATION.read_text());second=inspect()
    valid=all(term in second['indexes'] for term in ('uq_index_resource\t0\tresource_kind,resource_id','uq_index_job_source_spec\t0\tresource_pk,source_revision,index_spec','uq_index_execution_generation\t0\tjob_pk,generation','uq_index_candidate\t0\tcandidate_name'))
    valid=valid and 'snapshot_json\tlongtext\tNO\tutf8mb4_bin' in second['columns']
    result={'status':'PASS' if first==second and valid else 'FAIL','rerun_unchanged':first==second,'required_columns_unique':valid,'before':before,'after':second}
    (RESULTS/'index-migration-forward.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('before','after')}))
    if result['status']!='PASS':raise RuntimeError('Index schema validation failed')

def fresh_prepare():
    if root_sql("SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='"+FRESH+"';")!='0':
        raise RuntimeError('Fresh schema already exists; do not reset it')
    root_sql('CREATE DATABASE '+FRESH+' CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci; GRANT ALL ON '+FRESH+".* TO 'dodream'@'%';")
    grading=ROOT/'be/src/main/resources/db/migration/V003__grading_attempts.sql'
    root_sql('USE '+FRESH+';\n'+grading.read_text()+'\n'+MIGRATION.read_text())
    (RESULTS/'index-migration-fresh-created.json').write_text(json.dumps({'schema':FRESH,'migration_before_jpa':True,'status':'PASS'})+'\n')
    print('Dedicated fresh schema created; no existing schema replaced')

if __name__=='__main__':
    if sys.argv[1]=='fresh-prepare-hardening':
        FRESH='dodream_portfolio_hardening_fresh'
        fresh_prepare()
    else:
        {'forward':forward,'fresh-prepare':fresh_prepare}[sys.argv[1]]()
