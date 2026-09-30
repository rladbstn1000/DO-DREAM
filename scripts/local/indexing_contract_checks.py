"""Extra 3-B checks. Called by verify_indexing.Runner; never operates on old fixture rows.

Constraint failures and activation probes are rolled back. Publication checks use
fresh, explicitly tracked synthetic resources and retain prepared orphan objects.
Only aggregate counts, hashes and sanitized MySQL error numbers are recorded.
"""
import hashlib
import json
import re
import subprocess
import sys
import textwrap
import uuid


def _api(r):
    # Reuse the caller's CHECKS even when verify_indexing.py is __main__.
    return sys.modules[type(r).__module__]


def _ident(value):
    if not re.fullmatch(r'[a-z_][a-z0-9_]*', value):
        raise ValueError('Invalid SQL identifier')
    return '`' + value + '`'


def _literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def _columns(api, table):
    return [line.split('\t')[0] for line in api.sql('SHOW COLUMNS FROM ' + _ident(table) + ';').splitlines()]


def _require_fixture(r, fixture):
    api = _api(r)
    if fixture not in r.fixtures or not fixture['title'].startswith('[INDEXING LOCAL]'):
        raise ValueError('A new tracked indexing fixture is required')
    row = api.query("SELECT JSON_OBJECT('owner',m.teacher_id,'file',f.id,'name',f.original_file_name,'key',f.s3key) "
                    f"FROM materials m JOIN uploaded_files f ON f.id=m.uploaded_file_id WHERE m.id={int(fixture['id'])};")[0]
    if (row['owner'] != r.users['owner'] or row['file'] != fixture['file']
            or not row['name'].startswith('indexing-synthetic')
            or not re.fullmatch(r'local/synthetic/indexing-pdf/[0-9a-f-]{36}\.pdf', row['key'])):
        raise ValueError('Fixture must come from the dedicated binary PDF boundary')


def _digest(r, fixture):
    api = _api(r)
    mid, fid = int(fixture['id']), int(fixture['file'])
    resource = f"SELECT id FROM index_resources WHERE resource_kind='MATERIAL' AND resource_id={mid}"
    jobs = f'SELECT id FROM index_jobs WHERE resource_pk IN ({resource})'
    scopes = {
        'uploaded_files': f'id={fid}', 'materials': f'id={mid}',
        'quizzes': f'material_id={mid}', 'material_shares': f'material_id={mid}',
        'material_contents': f'material_id={mid}',
        'index_resources': f"resource_kind='MATERIAL' AND resource_id={mid}",
        'index_jobs': f'resource_pk IN ({resource})',
        'index_executions': f'job_pk IN ({jobs})',
    }
    result = {}
    for table, where in scopes.items():
        fields = ','.join(_literal(c) + ',' + _ident(c) for c in _columns(api, table))
        rows = api.sql('SELECT SHA2(CAST(JSON_OBJECT(' + fields + ') AS CHAR CHARACTER SET utf8mb4),256) FROM '
                       + _ident(table) + ' WHERE ' + where + ' ORDER BY id;').splitlines()
        result[table] = {'count': len(rows), 'hash': hashlib.sha256('\n'.join(rows).encode()).hexdigest()}
    return result


def _object_hashes(r, fixture):
    api = _api(r)
    rows = api.query("SELECT JSON_OBJECT('original',s3key,'json',jsons3key,'quiz',question_jsons3key) "
                     f"FROM uploaded_files WHERE id={int(fixture['file'])};")
    result = {}
    for label, key in rows[0].items():
        if key is None:
            continue
        if not re.fullmatch(r'local/synthetic/(?:indexing|indexing-pdf|authz)/[a-z0-9-]+\.(?:json|pdf)', key):
            raise ValueError('Only new local synthetic objects may be hashed')
        path = '/app/local-data/objects/' + hashlib.sha256(key.encode()).hexdigest() + ('.pdf' if key.endswith('.pdf') else '.json')
        digest = api.docker_exec('be', ['sha256sum', path]).split()[0]
        if not re.fullmatch(r'[0-9a-f]{64}', digest):
            raise ValueError('Unexpected object digest')
        result[label] = digest
    return result


def _json_object_count(api):
    raw = api.docker_exec('be', ['sh', '-c', "find /app/local-data/objects -maxdepth 1 -type f -name '*.json' | wc -l"])
    return int(raw)


def _reject(api, name, statements, expected):
    # A failed mysql batch closes the connection and rolls the transaction back.
    result = subprocess.run(api.compose_args('exec', '-T', 'mysql', 'sh', '-c',
        'MYSQL_PWD="$MYSQL_PASSWORD" mysql --default-character-set=utf8mb4 -N -B -u"$MYSQL_USER" "$MYSQL_DATABASE"'),
        input='START TRANSACTION;\n' + statements + '\nROLLBACK;\n',
        capture_output=True, text=True, env=api.clean_env(), timeout=25)
    found = re.search(r'ERROR (\d+)', result.stderr)
    code = int(found.group(1)) if found else None
    api.check(name, result.returncode != 0 and code == expected, {'mysqlError': code, 'expected': expected})


def _clone_job(api, job_pk, changes):
    columns = [c for c in _columns(api, 'index_jobs') if c != 'id']
    return ('INSERT INTO index_jobs (' + ','.join(map(_ident, columns)) + ') SELECT '
            + ','.join(changes.get(c, _ident(c)) for c in columns)
            + f' FROM index_jobs WHERE id={int(job_pk)};')


def schema(r):
    api = _api(r)
    r.service('stop', 'index-dispatcher')
    fixture = r.fixture('contract-schema')
    _require_fixture(r, fixture)
    job, _ = r.publish(fixture)
    before = _digest(r, fixture)
    row = r.ledger(job)
    try:
        expected = {
            'index_resources': {'resource_kind,resource_id'},
            'index_jobs': {'job_id', 'resource_pk,source_revision,index_spec'},
            'index_executions': {'job_pk,generation', 'candidate_name'},
        }
        for table, required in expected.items():
            indexes = api.query("SELECT JSON_OBJECT('columns',GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX),"
                                "'unique',MAX(NON_UNIQUE)=0) FROM information_schema.STATISTICS "
                                f"WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME={_literal(table)} GROUP BY INDEX_NAME;")
            actual = {x['columns'] for x in indexes if x['unique']}
            api.check('actual_unique_' + table, required.issubset(actual))
        required = {'job_id', 'resource_pk', 'source_revision', 'source_hash', 'snapshot_json', 'snapshot_bytes', 'index_spec'}
        columns = api.query("SELECT JSON_OBJECT('name',COLUMN_NAME,'required',IS_NULLABLE='NO','collation',COLLATION_NAME) "
                            "FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='index_jobs';")
        api.check('actual_mysql_job_required_columns', required.issubset({x['name'] for x in columns if x['required']}))
        api.check('actual_mysql_identity_case_sensitive', all(x['collation'] == 'ascii_bin' for x in columns
                                                             if x['name'] in {'job_id', 'source_hash', 'index_spec'}))
        pk = int(row['jobPk'])
        _reject(api, 'mysql_rejects_duplicate_logical_job', _clone_job(api, pk, {'job_id': _literal(str(uuid.uuid4()))}), 1062)
        _reject(api, 'mysql_rejects_duplicate_public_job', _clone_job(api, pk, {'index_spec': _literal('constraint-' + uuid.uuid4().hex)}), 1062)
        base = {'job_id': _literal(str(uuid.uuid4())), 'index_spec': _literal('constraint-' + uuid.uuid4().hex)}
        _reject(api, 'mysql_rejects_null_snapshot', _clone_job(api, pk, {**base, 'snapshot_json': 'NULL'}), 1048)
        _reject(api, 'mysql_rejects_false_snapshot_byte_count', _clone_job(api, pk, {**base, 'snapshot_bytes': 'snapshot_bytes+1'}), 3819)
        _reject(api, 'mysql_rejects_unbounded_generation', _clone_job(api, pk, {**base, 'execution_generation': '4'}), 3819)
        _reject(api, 'mysql_rejects_unbounded_delivery', _clone_job(api, pk, {**base, 'delivery_attempts': '6'}), 3819)
        _reject(api, 'mysql_rejects_missing_resource_fk', _clone_job(api, pk, {**base, 'resource_pk': '9223372036854775807'}), 1452)
        # Run the production activation function against actual MySQL, with every
        # transient state contained in an outer rollback-only transaction. This
        # probes its DB fence, not the separate real-Chroma validation scenario.
        probe = textwrap.dedent('''
            import json, uuid
            from contextlib import contextmanager
            from datetime import timedelta
            from unittest.mock import patch
            from app.indexing import store
            from app.indexing.models import IndexJob, IndexResource, IndexExecution
            result={}
            db=store.SessionLocal()
            class RollbackOnly:
                @contextmanager
                def begin(self):
                    yield db
            try:
                db.begin()
                job=db.query(IndexJob).filter(IndexJob.job_id==JOB_ID).with_for_update().one()
                resource=db.query(IndexResource).filter(IndexResource.id==job.resource_pk).with_for_update().one()
                original_pointer=resource.active_execution_id
                original_count=resource.activation_count
                job.state='PROCESSING';job.execution_generation=1
                execution=IndexExecution(job_pk=job.id,generation=1,candidate_name='idx_schema_'+uuid.uuid4().hex,
                    claim_token=str(uuid.uuid4()),lease_until=store.now(db)+timedelta(seconds=30),state='VALIDATED',
                    expected_chunks=1,actual_chunks=1,content_digest='a'*64,embedding_calls=0,started_at=store.now(db))
                db.add(execution);db.flush()
                ctx={'job_id':job.job_id,'execution_id':execution.id,'token':execution.claim_token,'generation':1,
                    'candidate':execution.candidate_name,'source_json':job.snapshot_json,'source_hash':job.source_hash,
                    'source_bytes':job.snapshot_bytes,'source_revision':job.source_revision,'spec':job.index_spec,
                    'resource_kind':resource.resource_kind,'resource_id':resource.resource_id}
                def rejected(context):
                    try: store.activate(context)
                    except ValueError: return True
                    return False
                with patch.object(store,'SessionLocal',RollbackOnly()):
                    result['wrong_generation']=rejected({**ctx,'generation':2})
                    result['wrong_capability']=rejected({**ctx,'token':str(uuid.uuid4())})
                    execution.lease_until=store.now(db)-timedelta(seconds=1);db.flush()
                    result['expired_lease']=rejected(ctx)
                    execution.lease_until=store.now(db)+timedelta(seconds=30);execution.state='BUILDING';db.flush()
                    result['unvalidated_candidate']=rejected(ctx)
                    execution.state='VALIDATED';db.flush()
                    with db.begin_nested() as savepoint:
                        resource.request_seq+=1;resource.latest_job_id=None;db.flush()
                        result['superseded_request']=store.activate(ctx) is False
                        db.flush()
                        result['superseded_keeps_pointer']=resource.active_execution_id==original_pointer
                        savepoint.rollback()
                    db.expire_all()
                    result['valid_activation']=store.activate(ctx) is True
                    db.flush()
                    result['one_pointer_update']=resource.active_execution_id==execution.id and resource.activation_count==original_count+1
                    result['duplicate_completion_rejected']=rejected(ctx)
                    store.fail_execution(ctx,'SYNTHETIC_LATE_FAILURE');db.flush()
                    result['late_failure_preserves_success']=job.state=='SUCCEEDED' and execution.state=='ACTIVE' and resource.activation_count==original_count+1
            finally:
                db.rollback();db.close()
            print(json.dumps(result))
        ''').replace('JOB_ID', repr(str(uuid.UUID(job))))
        result = json.loads(api.docker_exec('ai', ['python', '-c', probe]))
        for name, passed in result.items():
            api.check('production_activation_mysql_' + name, passed is True)
        api.check('schema_probes_rolled_back_all_new_fixture_rows', _digest(r, fixture) == before)
        r.evidence.append({'scenario': 'schema_and_activation_contract', 'checks': result, 'before': before, 'after': _digest(r, fixture)})
    finally:
        r.service('up', 'index-dispatcher')
    r.done(job)


def publication(r):
    api = _api(r)
    r.service('stop', 'index-dispatcher')
    fixture = None
    try:
        fixture = r.fixture('contract-publication')
        _require_fixture(r, fixture)
        body = r.body(fixture, 'canonical 한글 😀\tline\nquote"')
        rows = api.query("SELECT JSON_OBJECT('question_number',question_number,'question_type',question_type,'title',title,"
                         "'content',content,'correct_answer',correct_answer,'chapter_reference',chapter_reference) "
                         f"FROM quizzes WHERE material_id={int(fixture['id'])} ORDER BY question_number;")
        if not rows:
            raise ValueError('The publication fixture needs cloned synthetic quizzes')
        for row in rows:
            row['content'] = '[INDEX LOCAL] atomic quiz change'
            row['correct_answer'] = 'INDEX_SECRET_ANSWER_CANARY_CHANGED'
        body['quizzes'] = rows
        before, objects = _digest(r, fixture), _object_hashes(r, fixture)
        for mode in ('fail_after_object', 'rollback'):
            count = _json_object_count(api)
            r.spring_control(fixture, mode)
            code, _, _ = api.http('be', f"/api/documents/{fixture['file']}/publish", r.tokens['owner'], body)
            api.check('publication_' + mode + '_explicit_503', code == 503, {'http': code})
            api.check('publication_' + mode + '_all_db_rows_unchanged', _digest(r, fixture) == before)
            api.check('publication_' + mode + '_referenced_object_bytes_unchanged', _object_hashes(r, fixture) == objects)
            api.check('publication_' + mode + '_prepared_orphan_retained', _json_object_count(api) > count)
        r.spring_control(fixture, 'none')
        job, state = r.publish(fixture, body=body)
        api.check('publication_and_job_commit_together', state['state'] == 'QUEUED')
        snapshot = r.ledger(job)
        probe = textwrap.dedent('''
            import hashlib,json,os
            from pathlib import Path
            from sqlalchemy import text
            from app.common.db_session import SessionLocal
            from app.indexing.source import normalize_source
            with SessionLocal() as db:
                row=db.execute(text("SELECT j.snapshot_json,j.source_hash,j.snapshot_bytes,f.jsons3key FROM index_jobs j JOIN index_resources r ON r.id=j.resource_pk JOIN materials m ON m.id=r.resource_id JOIN uploaded_files f ON f.id=m.uploaded_file_id WHERE j.job_id=:job AND r.resource_kind='MATERIAL'"),{'job':JOB_ID}).mappings().one()
                saved=dict(row)
            path=Path(os.environ['LOCAL_OBJECT_STORAGE_DIR'])/(hashlib.sha256(saved['jsons3key'].encode()).hexdigest()+'.json')
            if path.is_symlink():raise ValueError('Symlink refused')
            raw=path.read_bytes()
            if len(raw)>2097152:raise ValueError('Bounded source required')
            original=json.loads(raw)
            canonical,digest,size=normalize_source(original,'MATERIAL')
            print(json.dumps({'sameBytes':canonical==saved['snapshot_json'],'sameHash':digest==saved['source_hash'],
                'sameSize':size==saved['snapshot_bytes'],'dbHash':hashlib.sha256(saved['snapshot_json'].encode()).hexdigest()==digest,
                'noTeacherAnswer':'INDEX_SECRET_ANSWER_CANARY' not in canonical,'snapshotBytes':size}))
        ''').replace('JOB_ID', repr(str(uuid.UUID(job))))
        canonical = json.loads(api.docker_exec('ai', ['python', '-c', probe]))
        api.check('java_python_canonical_snapshot_bytes_and_hash', all(canonical[k] is True for k in ('sameBytes','sameHash','sameSize','dbHash','noTeacherAnswer')),
                  {'snapshotBytes': canonical['snapshotBytes']})
        changed = _digest(r, fixture)
        api.check('successful_publication_changes_new_fixture_quizzes_and_reference',
                  changed['quizzes'] != before['quizzes'] and changed['uploaded_files'] != before['uploaded_files'])
        r.evidence.append({'scenario':'publication_object_and_database_atomicity','before':before,'committed':changed,
                           'originalObjectHashes':objects,'ledger':snapshot,'canonical':canonical})
    finally:
        if fixture is not None:
            r.spring_control(fixture, 'none')
        r.service('up', 'index-dispatcher')
    r.done(job)


def _logical_count(r, fixture):
    return int(_api(r).sql("SELECT COUNT(*) FROM index_jobs j JOIN index_resources r ON r.id=j.resource_pk "
                           f"WHERE r.resource_kind='MATERIAL' AND r.resource_id={int(fixture['id'])};"))


def bounded_recovery(r):
    """Reach the real execution/delivery ceilings without changing DB clocks or leases."""
    api = _api(r)
    r.service('stop', 'index-dispatcher')
    fixture = r.fixture('bounded-execution')
    _require_fixture(r, fixture)
    job, accepted = r.publish(fixture)
    original = r.ledger(job)
    api.check('first_index_has_no_readable_active', accepted['state'] == 'QUEUED'
              and not accepted['readable'] and not accepted['activeCurrent']
              and original['activeExecution'] is None and original['activations'] == 0)
    executions = []
    try:
        r.controls(job, fault='embedding_failure', generation=1)
        r.service('up', 'index-dispatcher')
        for generation in (1, 2, 3):
            if generation > 1:
                # Install this generation's provider-boundary fault before queuing it.
                r.controls(job, fault='embedding_failure', generation=generation)
                r.retry(job, generation - 1)
            failed = r.done(job, 'FAILED')
            row, runs = r.ledger(job), r.executions(job)
            api.check('bounded_execution_generation_' + str(generation),
                      row['generation'] == generation and len(runs) == generation
                      and runs[-1]['state'] == 'FAILED' and runs[-1]['failureCode'] == 'EMBEDDING_FAILURE',
                      {'generation': row['generation'], 'executions': len(runs), 'deliveries': row['deliveries']})
            api.check('first_index_failure_not_readable_' + str(generation),
                      not failed['readable'] and not failed['activeCurrent']
                      and row['activeExecution'] is None and row['activations'] == 0)
            api.check('bounded_execution_keeps_one_immutable_source_' + str(generation),
                      _logical_count(r, fixture) == 1 and row['sourceHash'] == original['sourceHash']
                      and row['snapshotHash'] == original['snapshotHash'])
            executions = runs
        code, data, _ = api.http('be', '/api/indexing/jobs/' + job + '/retry', r.tokens['owner'],
                                  {'expectedGeneration': 3})
        api.check('fourth_execution_retry_is_409', code == 409 and isinstance(data,dict) and data.get('code') == 'INDEXING_RETRY_LIMIT', {'http': code})
        same, _ = r.request(fixture, 'local-hash8-content-v1')
        final = r.ledger(job)
        api.check('execution_budget_cannot_reset_by_duplicate_request', same == job
                  and final['generation'] == 3 and final['state'] == 'FAILED'
                  and final['activations'] == 0 and _logical_count(r, fixture) == 1)
        api.check('three_failures_have_three_distinct_candidates',
                  len({execution['candidate'] for execution in executions}) == 3)
        r.evidence.append({'scenario': 'actual_execution_budget_exhaustion', 'original': original,
                           'final': final, 'executions': executions, 'logicalJobs': 1})
    finally:
        r.controls(job)
        r.service('up', 'index-dispatcher')

    # Finish this resource's unrelated initial-PDF job while Redis is still up.
    # Only the new MATERIAL job below participates in the broker outage proof.
    fixture = r.fixture('bounded-delivery')
    _require_fixture(r, fixture)
    r.done(fixture['initialJob'])
    r.service('stop', 'index-dispatcher')
    job, accepted = r.publish(fixture)
    original = r.ledger(job)
    api.check('broker_budget_starts_undelivered', original['generation'] == 0
              and original['deliveries'] == 0 and not accepted['readable'])
    seen = set()
    exhausted = None
    try:
        r.service('stop', 'worker', 'redis')
        # start intentionally skips a healthy-Redis dependency gate: the tested
        # dispatcher must encounter the real unavailable broker itself.
        r.service('start', 'index-dispatcher')

        def terminal():
            row = r.ledger(job)  # Actual MySQL only; no fabricated time/lease updates.
            attempts = row['deliveries']
            if attempts not in seen:
                seen.add(attempts)
                api.check('observed_broker_delivery_attempt_' + str(attempts), 0 <= attempts <= 5,
                          {'deliveries': attempts, 'state': row['state']})
            if row['state'] == 'FAILED':
                return row
            return None

        exhausted = api.wait(terminal, 100, 'real broker delivery budget')
        api.check('fifth_broker_failure_is_terminal', exhausted['deliveries'] == 5
                  and exhausted['generation'] == 0 and exhausted['activations'] == 0
                  and exhausted['activeExecution'] is None
                  and api.sql("SELECT failure_code FROM index_jobs WHERE job_id=" + _literal(job) + ';') == 'DELIVERY_LIMIT')
        def last_delivery_event():
            rows = r.events(job)
            return rows if sum(e['event'] == 'delivery_unconfirmed' for e in rows) >= 5 else None
        events = api.wait(last_delivery_event, 5, 'last failed delivery event')
        api.check('five_actual_broker_send_attempts_no_send_success',
                  sum(e['event'] == 'delivery_attempted' for e in events) == 5
                  and sum(e['event'] == 'delivery_unconfirmed' for e in events) == 5
                  and not any(e['event'] == 'broker_send_returned' for e in events))
        api.check('broker_exhaustion_never_started_worker', r.executions(job) == [])
        api.check('broker_exhaustion_preserves_immutable_single_job', _logical_count(r, fixture) == 1
                  and exhausted['sourceHash'] == original['sourceHash']
                  and exhausted['snapshotHash'] == original['snapshotHash'])
    finally:
        # Always restore this task's real broker/worker/dispatcher, including when
        # an assertion or dependency timeout interrupts the scenario.
        r.service('stop', 'index-dispatcher')
        r.service('up', 'redis')
        r.service('up', 'worker', 'index-dispatcher')

    # Redis PING and Spring /health alone do not prove the application's Redis
    # connection has recovered. Require an actual bounded synthetic login before
    # checking post-outage APIs and before the next browser scenario.
    r.initialize()
    code, data, _ = api.http('be', '/api/indexing/jobs/' + job + '/retry', r.tokens['owner'],
                              {'expectedGeneration': 0})
    api.check('delivery_budget_manual_retry_is_409', code == 409 and isinstance(data,dict) and data.get('code') == 'INDEXING_RETRY_LIMIT', {'http': code})
    same, _ = r.request(fixture, 'local-hash8-content-v1')
    final = r.ledger(job)
    state = r.status(job)
    api.check('restored_broker_does_not_reset_exhausted_budget', same == job and final['state'] == 'FAILED'
              and final['deliveries'] == 5 and final['generation'] == 0 and final['activations'] == 0
              and _logical_count(r, fixture) == 1 and not state['readable'] and not state['retryable'])
    r.evidence.append({'scenario': 'actual_broker_delivery_budget_exhaustion', 'original': original,
                       'exhausted': exhausted, 'restored': final, 'executions': [], 'logicalJobs': 1})
