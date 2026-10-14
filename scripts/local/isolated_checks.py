"""Synthetic fixture and browser-suite functions for isolated_trial.TrialRuntime.

There is intentionally no CLI or independent resource executor here. The central
runtime owns every container operation and the creation/current-state receipts.
Importing this module performs no I/O and does not import legacy launchers.
"""
from datetime import datetime, timezone
import hashlib
import http.cookiejar
import json
import os
import signal
import subprocess
import urllib.error
import urllib.request
import uuid


TEACHERS = ('teacher@local.dodream.invalid', 'other-teacher@local.dodream.invalid',
            'authz-owner@local.dodream.invalid', 'authz-other@local.dodream.invalid',
            'authz-remote@local.dodream.invalid', 'demo-phase5-v1@local.dodream.invalid')
REPORTS = {'auth': 'browser-checks.json', 'authorization': 'browser-authorization-checks.json',
           'grading': 'browser-grading-checks.json', 'indexing': 'browser-indexing-checks.json',
           'student': 'student-browser.json', 'demo-disabled': 'student-disabled-ui.json',
           'hardening': 'browser-hardening-checks.json'}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def write_new(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def stamped(runtime, name, value):
    target = runtime.results / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + name + '.json')
    write_new(target, value)
    return target


def stage_notice(suite, status):
    print(json.dumps({'isolatedSuite': suite, 'status': status}), flush=True)


def suite_evidence(runtime, suite, report):
    """Keep fault probes and browser/API observations separate from policy tests."""
    explicit_faults = {
        'browser_403_preserves_session_without_refresh': 'ERROR_RESPONSE_INJECTION',
        'browser_refresh_failure_no_loop_and_login_guidance': 'ERROR_RESPONSE_INJECTION',
        'browser_late_401_no_second_refresh': 'ACTUAL_SERVER_WITH_DELIVERY_FAULT',
        'browser_logout_during_refresh_no_resurrection': 'ACTUAL_SERVER_WITH_DELIVERY_FAULT',
        'browser_late_cookie_cannot_revive_server_session': 'ACTUAL_SERVER_WITH_DELIVERY_FAULT',
        'browser_grading_api_response_loss_after_commit': 'ACTUAL_SERVER_WITH_DELIVERY_FAULT',
        'browser_grading_api_lost_response_replay': 'ACTUAL_SERVER_WITH_DELIVERY_FAULT',
    }
    categories = {}
    for row in report.get('checks', []):
        category = row.get('category') or explicit_faults.get(row['name'],
            'ACTUAL_BROWSER_API' if suite == 'grading' else 'ACTUAL_SERVER_AND_UI')
        categories.setdefault(category, []).append({'name': row['name'], 'status': row['status']})
    result = {'status': 'PASS', 'runId': runtime.run_id, 'suite': suite,
              'source': runtime.source_identity(), 'attemptId': runtime.attempt_id,
              'resultFile': str((runtime.results / REPORTS[suite]).relative_to(runtime.root)),
              'serverApi': 'REAL_SERVER_REQUESTS',
              'browserUi': 'NOT_RUN_GRADING_UI' if suite == 'grading' else 'ACTUAL_BROWSER_UI',
              'checksByEvidenceType': categories, 'policyTests': 'NOT_INCLUDED',
              'nativeDevice': 'NOT_RUN', 'realVoiceListening': 'NOT_RUN', 'voiceOver': 'NOT_RUN'}
    stamped(runtime, suite + '-completed', result)
    return result


def bind(runtime):
    """Import the existing helpers only after explicit new-runtime configuration."""
    require(os.environ.get('DODREAM_ISOLATED_MANIFEST') == str(runtime.manifest_path),
            'Central runtime must explicitly set the trial manifest before importing checks')
    import manage
    require(manage.ISOLATED is not None and manage.ISOLATED.run_id == runtime.run_id
            and manage.PROJECT == runtime.project and manage.RESULTS == runtime.results,
            'Existing helper import belongs to another environment')


def rows(runtime, statement):
    return [json.loads(line) for line in runtime.sql(statement).splitlines() if line]


def fixture(runtime, suite, **fields):
    value = {**fields, **runtime.fixture_binding(suite)}
    write_new(runtime.fixtures / (suite + '.json'), value)
    return value


def initial_ownership(runtime):
    """Initial store proofs remain bound to the immutable first creation."""
    receipt = json.loads((runtime.root / 'creation.json').read_text())['provenance']
    require(receipt['runId'] == runtime.run_id and receipt['project'] == runtime.project,
            'Original creation receipt belongs to another trial')
    canonical = json.dumps(receipt, sort_keys=True, separators=(',', ':')).encode()
    return {'runId': runtime.run_id, 'project': runtime.project,
            'provenanceDigest': hashlib.sha256(canonical).hexdigest()}


def register_pending_fixtures(runtime):
    """Bind only the product's newly seeded teacher IDs, never historical IDs."""
    found = rows(runtime, "SELECT JSON_OBJECT('id',user_id,'email',email) FROM password_credentials ORDER BY user_id;")
    require(len(found) == len(TEACHERS) and {row['email'] for row in found} == set(TEACHERS),
            'Unexpected teacher credentials in the new synthetic database')
    require(all(isinstance(row['id'], int) and row['id'] > 0 for row in found), 'Invalid synthetic owner ID')
    value = {'runId': runtime.run_id, 'project': runtime.project, 'syntheticOnly': True,
             'teachers': found, 'provenanceDigest': initial_ownership(runtime)['provenanceDigest']}
    target = runtime.root / 'fixtures' / 'owners.json'
    if target.exists():
        require(json.loads(target.read_text()) == value, 'Synthetic seed owner receipt changed')
    else:
        write_new(target, value)
    return value


QUEUE_PROBE = '''import base64,json,redis
r=redis.Redis(host='redis',port=6379,db=1,decode_responses=True)
keys=r.keys('*');invalid=[];jobs=[]
if len(keys)>2000:raise RuntimeError('Queue metadata bound')
def task(raw):
    try:
        v=json.loads(raw);body=json.loads(base64.b64decode(v['body']))
        job=body[1]['job_id']
        if v.get('headers',{}).get('task')!='dodream.indexing.process' or body[0] or set(body[1])!={'job_id'}:
            invalid.append('unknown-task');return
        jobs.append(job)
    except Exception:invalid.append('invalid-task')
for key in keys:
    if key=='indexing-v3' or key.startswith('indexing-v3'+chr(6)+chr(22)):
        if r.type(key)!='list' or r.llen(key)>2000:invalid.append('queue-type-or-bound');continue
        for raw in r.lrange(key,0,2000):task(raw)
    elif key=='unacked':
        if r.type(key)!='hash' or r.hlen(key)>2000:invalid.append('unacked-type-or-bound');continue
        for raw in r.hvals(key):
            try:task(json.dumps(json.loads(raw)[0]))
            except Exception:invalid.append('invalid-unacked')
    elif key=='unacked_index':
        if r.type(key)!='zset':invalid.append('unacked-index-type')
    elif key=='unacked_mutex':
        if r.type(key)!='string' or not 0<=r.ttl(key)<=300:invalid.append('unacked-lock-type-or-ttl')
    elif key.startswith('_kombu.binding.'):
        if r.type(key)!='set':invalid.append('binding-type')
    else:invalid.append('unknown-broker-key')
print(json.dumps({'jobs':jobs,'invalid':invalid,'keyCount':len(keys)}))
'''


def verify_pending_work(runtime):
    """Validate new ledger ownership and actual queued task IDs before consumers."""
    target = runtime.root / 'fixtures' / 'owners.json'
    require(target.is_file() and not target.is_symlink(), 'Fresh synthetic owner receipt required')
    owners = json.loads(target.read_text())
    require(owners['runId'] == runtime.run_id and owners['project'] == runtime.project
            and owners['provenanceDigest'] == initial_ownership(runtime)['provenanceDigest'],
            'Synthetic owner receipt does not match the new resources')
    allowed = {row['id'] for row in owners['teachers']}
    # The actual Java schema uses materials.teacher_id, uploaded_files.uploader_id,
    # password_credentials.user_id; the two resource kinds are MATERIAL and PDF.
    jobs = rows(runtime, """SELECT JSON_OBJECT('jobId',j.job_id,'state',j.state,
      'resourceKind',r.resource_kind,'resourceId',r.resource_id,'ownerId',r.owner_id,
      'actualOwner',CASE WHEN r.resource_kind='MATERIAL' THEN m.teacher_id ELSE f.uploader_id END,
      'title',m.title,'fileName',f.original_file_name,'snapshotValid',
       JSON_VALID(j.snapshot_json) AND OCTET_LENGTH(j.snapshot_json)=j.snapshot_bytes
       AND SHA2(j.snapshot_json,256)=j.source_hash)
      FROM index_jobs j JOIN index_resources r ON r.id=j.resource_pk
      LEFT JOIN materials m ON r.resource_kind='MATERIAL' AND m.id=r.resource_id
      LEFT JOIN uploaded_files f ON (r.resource_kind='PDF' AND f.id=r.resource_id)
       OR (r.resource_kind='MATERIAL' AND f.id=m.uploaded_file_id)
      ORDER BY j.id LIMIT 2001;""")
    require(len(jobs) <= 2000, 'Synthetic ledger bound exceeded')
    for job in jobs:
        require(str(uuid.UUID(job['jobId'])) == job['jobId'], 'Invalid fresh job ID')
        require(job['resourceKind'] in ('MATERIAL', 'PDF') and job['ownerId'] in allowed
                and job['actualOwner'] == job['ownerId'] and bool(job['snapshotValid']),
                'Queued job does not match a newly seeded synthetic owner and immutable snapshot')
        if job['resourceKind'] == 'MATERIAL':
            title = job['title'] or ''
            require(title.startswith(('[AUTHZ ', '[GRADING LOCAL] ', '[INDEXING LOCAL] ', '[LOCAL '))
                    or title in ('물의 여행', '생활 속 분리배출'), 'Unknown synthetic material in indexing ledger')
        else:
            filename = job['fileName'] or ''
            require(filename.startswith(('indexing-synthetic-', 'demo-', 'authz-', 'grading-synthetic')),
                    'Unknown synthetic PDF fixture in indexing ledger')
    probe = runtime._operation('exec', ['ai'], payload=['python', '-c', QUEUE_PROBE])
    queue = json.loads(probe.stdout)
    require(not queue['invalid'] and set(queue['jobs']) <= {job['jobId'] for job in jobs},
            'Broker contains a task outside this trial fixture ledger')
    proof = {'status': 'PASS', 'runId': runtime.run_id, 'project': runtime.project,
             'jobCount': len(jobs), 'queuedMessageCount': len(queue['jobs']),
             'pendingJobs': [{key: job[key] for key in ('jobId', 'resourceKind', 'resourceId', 'ownerId')}
                             for job in jobs if job['state'] in ('QUEUED', 'PROCESSING')],
             'physicalStores': 'CREATION_RECEIPT_BOUND'}
    stamped(runtime, 'consumer-preflight', proof)
    return proof


def browser_report(runtime, suite):
    path = runtime.results / REPORTS[suite]
    require(path.is_file() and not path.is_symlink(), 'Current browser result is missing')
    report = json.loads(path.read_text())
    if 'checks' in report:
        require(report['checks'] and all(row.get('status') == 'PASS' for row in report['checks']),
                'Actual browser checks did not all pass')
    else:
        require(report.get('status') == 'PASS', 'Actual browser suite failed')
    require(all(report.get(key, 0) == 0 for key in ('externalRequestsBlocked', 'externalRequests', 'external', 'blockedExternal')),
            'Browser observed forbidden external requests')
    if 'origin' in report:
        require(report['origin'] == runtime.fixture_binding(suite)['origin'], 'Browser used another origin')
    return report


def run_browser(runtime, suite):
    runtime.assert_ready_for_browser(suite)
    require(not (runtime.results / REPORTS[suite]).exists(), 'Browser evidence already exists; preserve it and review a new attempt')
    command = ['node', 'tests/browser-' + suite + '.mjs']
    started = datetime.now(timezone.utc).isoformat()
    process = subprocess.Popen(command, cwd=runtime.repo / 'fe-web', env=runtime.clean_env(),
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
    output = ''; code = 1
    try:
        output, _ = process.communicate(timeout=900)
        code = process.returncode
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                output, _ = process.communicate(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                output, _ = process.communicate(timeout=5)
        runtime.record('browser-' + suite, command, subprocess.CompletedProcess(command, code, stdout=output), started)
    require(code == 0, 'Actual ' + suite + ' browser failed; subsequent suites stopped')
    return browser_report(runtime, suite)


def request(origin, pathname, *, opener=None, body=None, headers=None):
    require(origin.startswith('http://127.0.0.1:') and pathname.startswith('/') and not pathname.startswith('//'),
            'Explicit isolated loopback HTTP target required')
    opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    req = urllib.request.Request(origin + pathname, headers={'Content-Type': 'application/json', **(headers or {})},
                                 data=None if body is None else json.dumps(body).encode())
    try:
        response = opener.open(req, timeout=15)
    except urllib.error.HTTPError as failure:
        response = failure
    raw = response.read()
    return response.status, json.loads(raw) if raw else None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def run_auth(runtime):
    stage_notice('auth', 'STARTING')
    runtime.set_stage('auth', 'data')
    require(not (runtime.results / 'isolated-auth-gate.json').exists(), 'Auth gate already attempted')
    require(not (runtime.results / REPORTS['auth']).exists(),
            'Prior actual auth browser evidence exists; preserve it and review a separate browser attempt')
    if runtime.attempt_id is None:
        require(not set(runtime._started()) & {'worker', 'index-dispatcher'},
                'Auth preparation cannot resume after a consumer has started')
    else:
        # Follow-up uses the same new data stores, never pretends they are empty.
        runtime.compose('auth-consumers-stop', 'stop', 'index-dispatcher', 'worker')
    ownership = initial_ownership(runtime)
    runtime.compose('new-data-start', 'start', 'mysql', 'redis')
    empty_path = runtime.root / 'results' / 'auth-empty-stores.json'
    require(runtime.attempt_id is None or empty_path.is_file(), 'Follow-up requires the original empty-store proof')
    if empty_path.exists():
        prior = json.loads(empty_path.read_text())
        require(prior == {**ownership, 'status': 'PASS', 'applicationTables': 0, 'redisDatabase0': 0, 'redisDatabase1': 0},
                'Initial empty-store proof does not match this run')
    else:
        require(runtime.sql('SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE();') == '0',
                'New application schema is not empty')
        for database in ('0', '1'):
            result = runtime._operation('exec', ['redis'], payload=['redis-cli', '-n', database, 'DBSIZE'])
            require(result.stdout.strip() == '0', 'New Redis database contains preexisting records')
        write_new(empty_path, {**ownership, 'status': 'PASS', 'applicationTables': 0, 'redisDatabase0': 0, 'redisDatabase1': 0})
    migrations = {filename: (runtime.repo / 'be/src/main/resources/db/migration' / filename).read_text()
                  for filename in ('V003__grading_attempts.sql', 'V004__indexing_ledger.sql')}
    migration_proof = {**ownership, 'status': 'PASS', 'sha256': {
        name: hashlib.sha256(source.encode()).hexdigest() for name, source in migrations.items()}}
    migration_path = runtime.root / 'results' / 'auth-migrations.json'
    require(runtime.attempt_id is None or migration_path.is_file(), 'Follow-up requires the original migration proof')
    if migration_path.exists():
        require(json.loads(migration_path.read_text()) == migration_proof, 'Migration source or creation proof changed')
    else:
        require('be' not in runtime._started(), 'Primary app started without completed migration proof')
        tables = set(runtime.sql('SELECT table_name FROM information_schema.tables WHERE table_schema=DATABASE();').splitlines())
        require(tables <= {'grading_attempts', 'grading_attempt_items', 'grading_attempt_results',
                           'index_resources', 'index_jobs', 'index_executions'},
                'Unexpected tables during additive migration preparation')
        for source in migrations.values():
            runtime.sql(source)
        write_new(migration_path, migration_proof)
    runtime.set_stage('auth', 'browser')
    runtime.compose('new-primary-seed', 'start', 'be')
    require(runtime.sql("SELECT COUNT(*) FROM password_credentials WHERE email IN ('teacher@local.dodream.invalid','other-teacher@local.dodream.invalid');") == '2',
            'Primary Spring synthetic seed incomplete')
    register_pending_fixtures(runtime)
    if runtime.attempt_id is None:
        require(runtime.sql('SELECT COUNT(*) FROM index_jobs;') == '0', 'Auth seed unexpectedly contains indexing work')
    runtime.compose('new-auth-dependencies', 'start', 'ai', 'be-auth-short')
    if runtime.attempt_id is None:
        sqlite = runtime._operation('exec', ['ai'], payload=['python', '-c',
            "import json,sqlite3; c=sqlite3.connect('file:/app/db_data/rag.db?mode=ro',uri=True); "
            "print(json.dumps({t:c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] "
            "for t in ('chat_sessions','chat_messages','embedding_tasks')}))"])
        require(all(value == 0 for value in json.loads(sqlite.stdout).values()), 'New RAG SQLite contains preexisting records')
    runtime.compose('new-auth-web', 'start', 'web-auth-test')
    origin = runtime.origins['short']
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
                                        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    code, csrf = request(origin, '/api/auth/csrf', opener=opener)
    require(code == 200, 'New auth CSRF endpoint unavailable')
    code, login = request(origin, '/api/auth/teacher/login', opener=opener,
                          headers={csrf['headerName']: csrf['token']},
                          body={'email': TEACHERS[0], 'password': runtime.settings()['LOCAL_TEACHER_PASSWORD']})
    require(code == 200 and login.get('accessToken'), 'New synthetic login failed')
    code, _ = request(origin, '/api/teacher/me', headers={'Authorization': 'Bearer ' + login['accessToken']})
    require(code == 200, 'New protected API did not accept the synthetic session')
    fixture(runtime, 'auth', teacherEmail=TEACHERS[0])
    report = run_browser(runtime, 'auth')
    result = {'status': 'PASS', 'runId': runtime.run_id, 'origin': origin,
              'newEmptyDatabaseAndRedis': 'INITIAL_PROOF_REUSED' if runtime.attempt_id else 'PASS',
              'migrationsBeforeSpring': 'INITIAL_PROOF_REUSED' if runtime.attempt_id else 'PASS',
              'attemptId': runtime.attempt_id, 'source': runtime.source_identity(),
              'newLoginAndProtectedApi': 'PASS', 'browserCounts': report.get('counts'),
              'consumersStarted': False, 'nativeDeviceExecution': 'NOT_RUN'}
    require(runtime.inventory()['frozen'] == runtime.preparation['before']['frozen'], 'Frozen resource metadata changed')
    write_new(runtime.results / 'isolated-auth-gate.json', result)
    write_new(runtime.attempt_root / 'auth-pass.json', {'status': 'PASS', 'runId': runtime.run_id,
                                              'currentProvenanceDigest': runtime.fixture_binding('auth')['provenanceDigest'],
                                              'attemptId': runtime.attempt_id, 'source': runtime.source_identity(),
                                              'evidence': str((runtime.results / 'isolated-auth-gate.json').relative_to(runtime.root))})
    suite_evidence(runtime, 'auth', report)
    stage_notice('auth', 'PASS')
    return result


def fresh_phase5_fixtures(runtime):
    bind(runtime)
    target = runtime.results / 'index-fixture-ids.json'
    if target.exists():
        return json.loads(target.read_text())
    if runtime.attempt_id is None:
        from indexing_fixtures import create
        create()
        result = json.loads(target.read_text())
    else:
        # Reuse exactly the initial trial's authored seed clones. The browser
        # restores its edits/shares; attempts add no second set of these 9 rows.
        source = runtime.root / 'results' / 'index-fixture-ids.json'
        require(source.is_file() and not source.is_symlink(), 'Initial synthetic fixture receipt required')
        result = json.loads(source.read_text())
        expected = {}
        require(set(result) == {'authorization', 'grading'}
                and set(result['authorization']) == {'editable', 'second-shared', 'class-shared', 'private', 'draft', 'other-owned', 'remote-owned'}
                and set(result['grading']) == {'primary', 'second'}, 'Unexpected initial fixture keys')
        for suffix, identifier in result['authorization'].items():
            expected[identifier] = '[AUTHZ 5] ' + suffix
        for suffix, identifier in result['grading'].items():
            expected[identifier] = '[GRADING LOCAL] phase5' + (' second' if suffix == 'second' else '')
        require(len(expected) == 9 and all(type(identifier) is int and identifier > 0 for identifier in expected),
                'Initial fixture IDs are invalid or duplicated')
        actual = rows(runtime, "SELECT JSON_OBJECT('id',id,'title',title) FROM materials WHERE deleted_at IS NULL AND id IN ("
                      + ','.join(str(identifier) for identifier in sorted(expected)) + ');')
        require(len(actual) == 9 and {row['id']: row['title'] for row in actual} == expected,
                'Initial fixture identities do not match preserved synthetic rows')
        write_new(target, result)
        write_new(runtime.results / 'authorization-fixtures.json', result['authorization'])
        stamped(runtime, 'seed-reuse', {'runId': runtime.run_id, 'attemptId': runtime.attempt_id,
                'source': str(source.relative_to(runtime.root)), 'verifiedRows': len(actual), 'addedRows': 0})
    require(len(result['authorization']) == 7 and len(result['grading']) == 2, 'New phase5 fixture identities incomplete')
    return result


def start_main(runtime, suite):
    runtime.set_stage(suite, 'browser')
    runtime.compose('new-main-dependencies', 'start', 'python-service')
    runtime.compose('new-main-web', 'start', 'web')
    if suite in ('authorization', 'indexing', 'student', 'hardening'):
        # The first Chroma start is checked before any consumer can write to it.
        initial_empty = runtime.root / 'results' / 'new-chroma-empty.json'
        first = not initial_empty.exists()
        require(runtime.attempt_id is None or not first, 'Follow-up requires initial Chroma empty proof')
        if not first:
            require(json.loads(initial_empty.read_text()) == {'status': 'PASS', 'runId': runtime.run_id, 'collections': 0},
                    'Initial Chroma proof does not match this trial')
        runtime.compose('new-chroma', 'start', 'chroma')
        if first:
            result = runtime._operation('exec', ['ai'], payload=['python', '-c',
                "import json;from app.indexing.chroma import client;print(json.dumps({'collections':len(client().list_collections(limit=1))}))"])
            require(json.loads(result.stdout)['collections'] == 0, 'New Chroma is not empty')
            write_new(initial_empty, {'status': 'PASS', 'runId': runtime.run_id, 'collections': 0})


def run_suite(runtime, suite):
    require(suite in ('authorization', 'grading', 'indexing', 'student', 'demo-disabled', 'hardening'), 'Unknown remaining suite')
    prerequisite = json.loads((runtime.results / 'isolated-auth-gate.json').read_text())
    require(prerequisite['status'] == 'PASS' and prerequisite['runId'] == runtime.run_id, 'Current auth gate has not passed')
    bind(runtime)
    runtime.set_stage(suite, 'browser')
    if suite == 'demo-disabled':
        runtime.compose('new-short-student-web-stop', 'stop', 'web-student-short')
        runtime.compose('new-disabled-web-start', 'start', 'web-auth-test')
        fixture(runtime, suite)
        return run_browser(runtime, suite)
    start_main(runtime, suite)
    if suite in ('authorization', 'grading', 'indexing'):
        fresh_phase5_fixtures(runtime)
        fields = {'ownerEmail': 'authz-owner@local.dodream.invalid'}
        if suite in ('authorization', 'grading'):
            fields.update(studentDeviceId='dodream-authz-shared',
                          lessonTitle='[AUTHZ 5] editable' if suite == 'authorization' else '[GRADING LOCAL] phase5')
        if suite == 'authorization':
            fields['otherEmail'] = 'authz-other@local.dodream.invalid'
        fixture(runtime, suite, **fields)
        if suite in ('authorization', 'indexing'):
            runtime.compose('new-consumers', 'start', 'worker', 'index-dispatcher')
        try:
            if suite != 'indexing':
                return run_browser(runtime, suite)
            import verify_indexing
            runner = verify_indexing.Runner()
            completed = []
            try:
                runner.initialize(); runner.browser(); completed.append('browser')
                return browser_report(runtime, suite)
            finally:
                runner.report(completed)
                runner.pool.shutdown(wait=False, cancel_futures=True)
        finally:
            if suite in ('authorization', 'indexing'):
                runtime.compose('new-consumers-stop', 'stop', 'index-dispatcher', 'worker')
    # Prepare the authored catalog through its normal API, validating newly
    # enqueued jobs before the runtime permits either new consumer to start.
    from student_demo_prepare import prepare
    def start_consumers(metadata):
        require(metadata.get('fixtureVersion') == 'student-web-phase5-v1', 'Unreviewed synthetic catalog')
        runtime.verify_pending_work()
        runtime.compose('new-catalog-consumers', 'start', 'worker', 'index-dispatcher')
    runtime.compose('new-consumers-before-prepare-stop', 'stop', 'index-dispatcher', 'worker')
    if suite == 'hardening':
        runtime.set_stage('student', 'browser')  # Explicit authored catalog preparation needs the consumer scope.
    try:
        prepare(after_enqueue=start_consumers, write_plan=suite == 'student')
        if suite == 'student':
            fixture(runtime, suite, teacherEmail='demo-phase5-v1@local.dodream.invalid')
            runtime.compose('new-disabled-web-stop', 'stop', 'web-auth-test')
            runtime.compose('new-student-short', 'start', 'be-student-short', 'web-student-short')
            import verify_student_web
            require(verify_student_web.main() == 0, 'Actual student browser orchestration failed')
            return browser_report(runtime, suite)
    finally:
        runtime.compose('new-catalog-consumers-stop', 'stop', 'index-dispatcher', 'worker')
    runtime.set_stage('hardening', 'browser')
    other = runtime.sql("SELECT user_id FROM device_credentials WHERE device_id='dodream-authz-unshared';")
    require(other.isdecimal() and int(other) > 0, 'Fresh unauthorized student ID unavailable')
    fixture(runtime, suite, teacherEmail='demo-phase5-v1@local.dodream.invalid', unauthorizedStudentId=int(other))
    return run_browser(runtime, suite)


def run_remaining(runtime):
    results = {}
    order = ('authorization', 'grading', 'indexing', 'student', 'demo-disabled', 'hardening')
    for index, suite in enumerate(order):
        stage_notice(suite, 'STARTING')
        try:
            results[suite] = run_suite(runtime, suite)
            suite_evidence(runtime, suite, results[suite])
        except BaseException as error:
            stage_notice(suite, 'STOPPED')
            blocked = isinstance(error, (TimeoutError, subprocess.TimeoutExpired, urllib.error.URLError, KeyboardInterrupt)) or type(error).__name__ == 'PolicyError'
            stamped(runtime, suite + '-stopped', {'status': 'BLOCKED' if blocked else 'FAIL', 'runId': runtime.run_id,
                    'suite': suite, 'errorType': type(error).__name__,
                    'remaining': {name: 'NOT_RUN' for name in order[index + 1:]}})
            raise
        stage_notice(suite, 'PASS')
    return results
