"""Real broker/independent-worker races for verify_indexing.Runner.

Only the guarded parent runner invokes these scenarios. No direct task function,
fabricated clock, lease UPDATE, or replacement server is used here.
"""
from contextlib import contextmanager
import math
import json
import sys
import textwrap
import uuid

from manage import compose, stop_owned_test


def _api(r):
    # The runner normally executes as __main__; importing it again would lose checks.
    module = sys.modules[type(r).__module__]
    return module.check, module.query, module.wait


def _identity(event):
    return (event.get('hostname'), event.get('pid'))


def _events(r, job, name, generation=None):
    return [e for e in r.events(job) if e['event'] == name
            and (generation is None or e.get('generation') == generation)]


def database_identity_refresh(r):
    """Two real MySQL connections prove a locked resource replaces cached hints."""
    check, _, _ = _api(r)
    r.service('stop', 'index-dispatcher')
    fixture = r.fixture('locked-identity-refresh')
    job, _ = r.publish(fixture)
    args = {'job': str(uuid.UUID(job)), 'material': int(fixture['id']),
            'owner': int(r.users['owner']), 'title': fixture['title']}
    code = 'args=' + repr(args) + '\n' + textwrap.dedent('''
        import json
        from sqlalchemy import event, text
        from app.indexing import store
        from app.indexing.models import IndexJob, IndexResource
        from app.indexing.source import normalize_source
        from app.common.models import Material, UploadedFile
        from app.local_providers import load_fixture_json, FIXTURE_BASE
        connections=[]
        def opened(session, transaction, connection):
            if connection.dialect.name != 'mysql':
                raise RuntimeError('Actual MySQL is required')
            connections.append(int(connection.execute(text('SELECT CONNECTION_ID()')).scalar_one()))
        event.listen(store.SessionLocal,'after_begin',opened)
        try:
            with store.SessionLocal() as first:
                old=first.query(IndexJob).filter(IndexJob.job_id==args['job']).one()
                resource=first.get(IndexResource,old.resource_pk)
                material=first.get(Material,args['material'])
                if (resource.resource_kind!='MATERIAL' or resource.resource_id!=args['material']
                    or resource.owner_id!=args['owner'] or resource.latest_job_id!=old.id
                    or old.state!='QUEUED' or resource.active_execution_id is not None
                    or material.title!=args['title'] or '[INDEX' not in material.title
                    or '[INDEX LOCAL]' not in old.snapshot_json):
                    raise RuntimeError('Probe is restricted to its newly created synthetic resource')
                file=first.get(UploadedFile,material.uploaded_file_id)
                key=file.json_s3_key
                source=load_fixture_json(FIXTURE_BASE+key)
                raw,digest,_=normalize_source(source,'MATERIAL')
                if raw!=old.snapshot_json or digest!=old.source_hash:
                    raise RuntimeError('Immutable object and accepted snapshot must agree')
                before=(resource.latest_job_id,resource.source_revision,resource.current_source_hash,resource.request_seq)
                new=store.accept_source(args['owner'],str(args['material']),key,source,'local-hash8-content-v2')
                stale_before=(resource.latest_job_id,resource.source_revision,resource.current_source_hash,resource.request_seq)==before
                locked,old_locked=store._job_locked(first,args['job'])
                after=(locked.latest_job_id,locked.source_revision,locked.current_source_hash,locked.request_seq)
                proof={'job':args['job'],'newJob':new['job_id'],'connectionIds':connections,
                    'staleBeforeLock':stale_before,'sameEntityRefreshed':locked is resource,
                    'oldNoLongerLatest':not store._is_latest(locked,old_locked),
                    'latestChanged':after[0]!=before[0],'sourceUnchanged':after[1:3]==before[1:3],
                    'requestSequenceAdvanced':after[3]==before[3]+1,'newJobDifferent':new['job_id']!=args['job']}
            print(json.dumps(proof))
        finally:
            event.remove(store.SessionLocal,'after_begin',opened)
    ''')
    module = sys.modules[type(r).__module__]
    proof = json.loads(module.docker_exec('ai', ['python', '-c', code]))
    new_job = str(uuid.UUID(proof['newJob']))
    if new_job not in r.jobs:
        r.jobs.append(new_job)
    check('actual_mysql_independent_connections_refresh_locked_resource',
          len(proof['connectionIds']) == 2 and len(set(proof['connectionIds'])) == 2
          and all(proof[field] for field in ('staleBeforeLock','sameEntityRefreshed',
                    'oldNoLongerLatest','latestChanged','sourceUnchanged',
                    'requestSequenceAdvanced','newJobDifferent')), proof)
    r.service('up', 'index-dispatcher')
    r.done(job, 'SUPERSEDED')
    r.done(new_job)
    r.evidence.append({'scenario': 'actual_mysql_cached_identity_refresh', 'proof': proof,
                       'superseded': r.ledger(job), 'current': r.ledger(new_job)})


@contextmanager
def _second_worker(r):
    check, _, _ = _api(r)
    name = 'dodream-phase3b-index-worker-' + uuid.uuid4().hex[:10]
    result = compose('index-independent-worker-start', 'run', '--rm', '--no-deps', '-d',
                     '--name', name, 'worker', 'celery', '-A', 'app.celery_config.celery_app',
                     'worker', '--loglevel=warning', '--concurrency=1', '--pool=solo',
                     '--queues=indexing-v3', '--hostname=indexing-secondary@%h')
    check('independent_worker_started', result.returncode == 0, {'name': name})
    try:
        yield name
    finally:
        # This helper inspects project/service/task labels, then stops that immutable
        # container ID only. --rm removes this newly created one-off container.
        result = stop_owned_test(name)
        check('independent_worker_stopped', result.returncode == 0, {'name': name})


def late_generation(r):
    """Generation 1 writes late, after generation 2 has actually become active."""
    check, query, wait = _api(r)
    r.service('stop', 'index-dispatcher')
    fixture = r.fixture('late-generation')
    job, _ = r.publish(fixture)
    r.controls(job, gate='before_write', generation=1)
    r.service('up', 'index-dispatcher')
    held = r.gate(job, 'before_write')
    old = r.executions(job)[0]
    before = r.digest(old['candidate'])
    check('late_candidate_exists_before_first_write', before['count'] == 0)
    try:
        with _second_worker(r) as secondary:
            # While main is paused, an independently running consumer receives
            # duplicate queue messages and competes for the same MySQL claim.
            r.duplicate_send(job, 2)
            ignored = wait(lambda: [e for e in _events(r, job, 'duplicate_or_terminal_ignored')
                                   if _identity(e) != _identity(held)], 20,
                           'second worker duplicate claim refusal')[-1]
            claims = _events(r, job, 'execution_claimed', 1)
            check('two_worker_processes_same_job_single_claim',
                  bool(held.get('hostname')) and type(held.get('pid')) is int
                  and bool(ignored.get('hostname')) and type(ignored.get('pid')) is int
                  and _identity(held) != _identity(ignored) and len(claims) == 1,
                  {'claimant': _identity(held), 'duplicateConsumer': _identity(ignored)})

            # The real DB clock and the normal status/dispatcher recovery path
            # expire the 30-second lease. The test does not edit deadline columns.
            r.done(job, 'FAILED', seconds=45)
            expired = query("SELECT JSON_OBJECT('expired',e.lease_until<=UTC_TIMESTAMP(6),"
                            "'state',e.state,'leaseUntil',CAST(e.lease_until AS CHAR),"
                            "'observedAt',CAST(UTC_TIMESTAMP(6) AS CHAR)) FROM index_executions e "
                            "JOIN index_jobs j ON j.id=e.job_pk WHERE j.job_id='" + job +
                            "' AND e.generation=1;")[0]
            check('actual_database_lease_expired_without_clock_injection',
                  bool(expired['expired']) and expired['state'] == 'EXPIRED', expired)
            r.retry(job, 1)
            r.done(job)
            runs = r.executions(job)
            check('retry_claims_distinct_generation_candidate',
                  len(runs) == 2 and runs[0]['generation'] == 1 and runs[1]['generation'] == 2
                  and runs[0]['candidate'] != runs[1]['candidate'] and runs[1]['state'] == 'ACTIVE')
            new = runs[1]
            active_before = r.digest(new['candidate'])
            # Releasing old main permits a physical write to its own collection.
            r.release(job, 'before_write')
            writes = wait(lambda: _events(r, job, 'batch_written', 1), 20,
                          'old worker physical late write')
            events = r.events(job)
            activated = [e for e in events if e['event'] == 'activation_committed' and e.get('generation') == 2]
            check('independent_new_worker_activated_before_old_physical_write',
                  len(activated) == 1 and _identity(activated[0]) == _identity(ignored)
                  and writes[0]['time'] > activated[0]['time'])
            old_after = r.digest(old['candidate'])
            row = r.ledger(job)
            check('late_write_is_physical_but_cannot_replace_current_active',
                  0 < old_after['count'] < old['expectedChunks']
                  and row['state'] == 'SUCCEEDED' and row['generation'] == 2
                  and row['activeExecution'] == new['id'] and row['activations'] == 1
                  and r.digest(new['candidate']) == active_before)
            check('expired_generation_never_commits_activation',
                  not any(e['event'] == 'activation_committed' and e.get('generation') == 1 for e in events))
            r.chat(fixture)
            r.evidence.append({'scenario': 'independent_workers_late_generation', 'secondary': secondary,
                               'lease': expired, 'oldBefore': before, 'oldAfter': old_after,
                               'activeBeforeLateWrite': active_before, 'ledger': row,
                               'executions': r.executions(job), 'events': events})
    finally:
        r.release(job, 'before_write')


def reverse_source_completion(r):
    """A newer source finishes on worker 2 while worker 1 holds a validated old source."""
    check, _, wait = _api(r)
    r.service('stop', 'index-dispatcher')
    fixture = r.fixture('reverse-source')
    old_job, _ = r.publish(fixture, 'old-source')
    r.controls(old_job, gate='before_activation')
    r.service('up', 'index-dispatcher')
    held = r.gate(old_job, 'before_activation')
    try:
        with _second_worker(r) as secondary:
            new_job, _ = r.publish(fixture, 'new-source')
            check('new_source_has_distinct_durable_job', new_job != old_job)
            r.done(new_job)
            # Its first immutable candidate name is deterministic. Read it directly
            # before releasing old work, saving an extra Docker scope scan while
            # the old job still has its real 30-second execution lease.
            candidate = 'idx_' + uuid.UUID(new_job).hex + '_g1'
            before = r.digest(candidate)
            r.release(old_job, 'before_activation')
            finished = wait(lambda: [e for e in r.events(old_job)
                                    if e['event'] in ('execution_failed','activation_rejected')
                                    and e.get('generation') == 1], 20,
                            'old worker resumed and rejected activation')[-1]
            check('old_worker_really_finished_after_activation_gate',
                  _identity(finished) == _identity(held) and finished['time'] > held['time'],
                  {'event': finished['event'], 'worker': _identity(finished)})
            r.done(old_job, 'SUPERSEDED')
            current = r.executions(new_job)[0]
            row = r.ledger(new_job)
            events = r.events(new_job)
            committed = [e for e in events if e['event'] == 'activation_committed']
            check('new_source_completed_on_independent_worker',
                  len(committed) == 1 and _identity(committed[0]) != _identity(held))
            check('older_source_cannot_replace_latest_pointer_or_physical_chunks',
                  current['candidate'] == candidate
                  and row['state'] == 'SUCCEEDED' and row['latestJob'] == row['jobPk']
                  and row['activeExecution'] == current['id'] and row['activations'] == 1
                  and r.digest(current['candidate']) == before)
            check('superseded_job_keeps_immutable_original_snapshot',
                  r.ledger(old_job)['sourceHash'] != row['sourceHash']
                  and r.ledger(old_job)['sourceHash'] == r.ledger(old_job)['snapshotHash'])
            r.chat(fixture)
            r.evidence.append({'scenario': 'independent_workers_reverse_source_completion',
                               'secondary': secondary, 'old': r.ledger(old_job), 'current': row,
                               'activePhysical': before, 'oldExecutions': r.executions(old_job),
                               'currentExecutions': r.executions(new_job), 'currentEvents': events})
    finally:
        r.release(old_job, 'before_activation')


def duplicate_batch(r):
    """Repeated actual Chroma upserts retain one row per deterministic chunk ID."""
    check, _, _ = _api(r)
    r.service('stop', 'index-dispatcher')
    fixture = r.fixture('duplicate-batch')
    job, _ = r.publish(fixture)
    r.controls(job, fault='duplicate_batch')
    r.service('up', 'index-dispatcher')
    r.done(job)
    execution = r.executions(job)[0]
    actual = r.digest(execution['candidate'])
    count = execution['expectedChunks']
    expected_calls = math.ceil(count / min(32, max(1, count // 2)))
    check('duplicate_physical_batch_upserts_preserve_exact_count_and_digest',
          actual['count'] == count == execution['actualChunks'] and actual['digest'] == execution['digest'])
    check('duplicate_physical_upserts_do_not_repeat_embedding_calls',
          execution['embeddingCalls'] == expected_calls,
          {'chunks': count, 'expectedEmbeddingCalls': expected_calls,
           'actualEmbeddingCalls': execution['embeddingCalls']})
    writes = _events(r, job, 'batch_written', 1)
    check('actual_completed_upsert_calls_are_twice_embedding_batches',
          len(writes) == expected_calls and all(e.get('upserts') == 2 for e in writes)
          and sum(e['chunks'] for e in writes) == count)
    r.evidence.append({'scenario': 'duplicate_batch_upsert', 'ledger': r.ledger(job),
                       'execution': execution, 'physical': actual})


def activation_rollback(r):
    """Optional focused rerun; the parent corruption scenario also exercises this fault."""
    check, _, _ = _api(r)
    fixture, initial = r.healthy('atomic-activation-rollback')
    original = r.executions(initial)[0]
    physical = r.digest(original['candidate'])
    prior = r.ledger(initial)
    r.service('stop', 'index-dispatcher')
    job, _ = r.request(fixture)
    r.controls(job, fault='activation_rollback')
    r.service('up', 'index-dispatcher')
    r.done(job, 'FAILED')
    row = r.ledger(job)
    execution = r.executions(job)[0]
    check('actual_activation_transaction_rollback_preserves_all_success_fields',
          row['activeExecution'] == prior['activeExecution'] and row['activations'] == prior['activations']
          and row['state'] == 'FAILED' and execution['state'] != 'ACTIVE'
          and r.digest(original['candidate']) == physical
          and not _events(r, job, 'activation_committed'))
    r.evidence.append({'scenario': 'activation_transaction_rollback', 'before': prior,
                       'after': row, 'execution': execution, 'preserved': physical})


def late_worker(r):
    database_identity_refresh(r)
    late_generation(r)
    reverse_source_completion(r)
    duplicate_batch(r)
