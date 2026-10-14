"""Receipt-bound actual HTTP PDF regression; imported by the isolated trial only.

No CLI, setup, automatic starts, imports of legacy settings, or import-time I/O.
Callers own the trial lifecycle. Records contain booleans and bounded metadata,
never response bodies, tokens, cookies, signing URLs or input document text.
"""
import base64
import hashlib
import http.cookies
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from isolated_trial import digest, exclusive_json, now, require

BODY = b'%PDF-1.4\n% DO-DREAM LOCAL SYNTHETIC FIXTURE\n%%EOF\n'
BODY_HASH = hashlib.sha256(BODY).hexdigest()
FILENAMES = {
    'normal': 'indexing-synthetic-c20cf22c-8758-4609-90f5-2466714127aa.pdf',
    'provider-failure': 'indexing-synthetic-22222222-2222-4222-8222-222222222222.pdf',
    'after-failure': 'indexing-synthetic-33333333-3333-4333-8333-333333333333.pdf',
}
BOOLEAN_FIELDS = {'transactionActive', 'synchronizationActive', 'dataSourceBound',
                  'requestEntityManagerPresent', 'physicalConnectionHeld',
                  'detachedEntityManagerPresent', 'detachedPhysicalConnectionHeld'}
EVENT_FIELDS = BOOLEAN_FIELDS | {'correlationId', 'stage', 'at'}
EXTERNAL_STAGES = {'OBJECT_WRITE_BEFORE', 'PARSE_BEFORE', 'STORAGE_BOUNDARY'}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs): return None


def _http(runtime, path, *, token=None, body=None, method=None, headers=None):
    require(path.startswith('/') and not path.startswith('//'), 'Only explicit trial HTTP paths allowed')
    origin = runtime.origins['main']
    require(re.fullmatch(r'http://127\.0\.0\.1:[2-6][0-9]{4}', origin), 'Explicit new loopback origin required')
    h = dict(headers or {})
    if token: h['Authorization'] = 'Bearer ' + token
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    request = urllib.request.Request(origin + path, data=body, method=method, headers=h)
    try: response = opener.open(request, timeout=55)
    except urllib.error.HTTPError as error: response = error
    raw = response.read(2 * 1024 * 1024 + 1)
    require(len(raw) <= 2 * 1024 * 1024, 'Bounded response exceeded')
    try: data = json.loads(raw)
    except (ValueError, UnicodeDecodeError): data = None
    return response.status, data, response.headers


def login(runtime, kind='owner'):
    settings = runtime.settings()
    status, csrf, csrf_headers = _http(runtime, '/api/auth/csrf')
    require(status == 200 and isinstance(csrf, dict), 'Synthetic login CSRF failed')
    jar = http.cookies.SimpleCookie()
    for value in csrf_headers.get_all('Set-Cookie', []): jar.load(value)
    student = kind == 'student'
    require(kind in ('owner', 'other', 'student'), 'Only named synthetic actors allowed')
    body = ({'deviceId': 'dodream-authz-shared', 'deviceSecret': settings['LOCAL_STUDENT_SECRET']} if student else
            {'email': 'authz-' + kind + '@local.dodream.invalid', 'password': settings['LOCAL_TEACHER_PASSWORD']})
    status, data, _ = _http(runtime, '/api/auth/' + ('student' if student else 'teacher') + '/login',
        body=json.dumps(body).encode(), headers={'Content-Type': 'application/json',
        'Cookie': '; '.join(key + '=' + value.value for key, value in jar.items()), csrf['headerName']: csrf['token']})
    require(status == 200 and isinstance(data, dict) and isinstance(data.get('accessToken'), str),
            'Synthetic actor login failed')
    token = data['accessToken']; segment = token.split('.')[1]
    user_id = int(json.loads(base64.urlsafe_b64decode(segment + '=' * (-len(segment) % 4)))['sub'])
    require(user_id > 0, 'Synthetic actor has invalid identifier')
    return token, user_id


def events(runtime):
    command = ['sh', '-c', 'for f in /app/local-data/indexing-controls/request-*.events.jsonl; do '
               '[ ! -f "$f" ] || head -c 65536 "$f"; done']
    output = runtime.compose('pdf-boundary-events', 'exec', '-T', 'be', *command).stdout
    require(len(output) <= 2 * 1024 * 1024, 'Observation evidence bound exceeded')
    result = []
    for line in output.splitlines():
        row = json.loads(line)
        require(set(row) == EVENT_FIELDS and all(type(row[key]) is bool for key in BOOLEAN_FIELDS),
                'Unexpected diagnostic event fields')
        require(str(uuid.UUID(row['correlationId'])) == row['correlationId'] and
                re.fullmatch(r'[A-Z_]{3,40}', row['stage']) and
                re.fullmatch(r'[0-9T:.Z+-]{20,40}', row['at']), 'Malformed diagnostic correlation metadata')
        result.append(row)
    return result


def _rows(runtime, statement):
    result = runtime.sql(statement)
    return [json.loads(line) for line in result.splitlines()] if result else []


def snapshot(runtime, filename):
    require(filename in FILENAMES.values(), 'Only fixed new synthetic PDF cases allowed')
    counts = _rows(runtime, "SELECT JSON_OBJECT('files',(SELECT COUNT(*) FROM uploaded_files),"
        "'jobs',(SELECT COUNT(*) FROM index_jobs),'resources',(SELECT COUNT(*) FROM index_resources),"
        "'executions',(SELECT COUNT(*) FROM index_executions));")[0]
    files = _rows(runtime, "SELECT JSON_OBJECT('id',id,'ownerId',uploader_id,'bytes',file_size,"
        "'objectKeyHash',SHA2(s3key,256),'hasParsedObject',jsons3key IS NOT NULL,'status',ocr_status) "
        "FROM uploaded_files WHERE original_file_name='" + filename + "' ORDER BY id;")
    require(len(files) <= 1, 'Repeated synthetic case would exceed the fixture bound; preserve existing evidence')
    objects = []
    for row in files:
        sha = row['objectKeyHash']
        require(isinstance(sha, str) and re.fullmatch(r'[a-f0-9]{64}', sha), 'Invalid synthetic object-key digest')
        path = '/app/local-data/objects/' + sha + '.pdf'
        probe = runtime.compose('pdf-boundary-object-metadata', 'exec', '-T', 'be', 'sh', '-c',
            'if [ -f "$1" ]; then wc -c < "$1"; sha256sum "$1" | cut -d" " -f1; else printf missing; fi', 'sh', path).stdout.strip()
        parts = probe.splitlines()
        objects.append({'fileId': row['id'], 'exists': probe != 'missing',
            'bytes': int(parts[0]) if probe != 'missing' else None,
            'sha256': parts[1] if probe != 'missing' else None})
    return {'counts': counts, 'files': files, 'objects': objects}


def _safe_response(status, data):
    result = {'http': status}
    if isinstance(data, dict):
        code = data.get('code')
        if isinstance(code, str) and re.fullmatch(r'[A-Z][A-Z0-9_]{0,80}', code): result['code'] = code
        if isinstance(data.get('pdfId'), int): result['fileId'] = data['pdfId']
        indexing = data.get('indexing')
        if isinstance(indexing, dict):
            job = indexing.get('jobId') or indexing.get('job_id')
            if isinstance(job, str) and str(uuid.UUID(job)) == job: result['jobId'] = job
    return result


def _record(runtime, label, value):
    require(re.fullmatch(r'[a-z0-9-]+', label), 'Invalid PDF evidence label')
    path = runtime.results / ('pdf-boundary-' + label + '.json')
    exclusive_json(path, value)
    return str(path)


def reproduction(runtime, expected_status):
    """Exactly one normal HTTP upload; same filename/body before and after fix."""
    require(expected_status in (200, 503), 'Only original failure or fixed success is expected')
    label = 'reproduction-' + str(expected_status)
    require(not (runtime.results / ('pdf-boundary-' + label + '.json')).exists(), 'Original request evidence already exists')
    receipt = runtime._receipt()
    token, owner = login(runtime)
    before = snapshot(runtime, FILENAMES['normal'])
    require(not before['files'], 'The fixed normal case already exists; no duplicate upload')
    observed_before = events(runtime)
    started = now()
    status, data, _ = _http(runtime, '/api/pdf/upload-and-parse?filename=' + FILENAMES['normal'], token=token,
        body=BODY, headers={'Content-Type': 'application/pdf'})
    response = _safe_response(status, data)
    after = snapshot(runtime, FILENAMES['normal'])
    existing = {row['correlationId'] for row in observed_before}
    observed = [row for row in events(runtime) if row['correlationId'] not in existing]
    evidence = {'schema': 1, 'runId': runtime.run_id, 'startedAt': started, 'finishedAt': now(),
        'method': 'POST', 'path': '/api/pdf/upload-and-parse', 'filename': FILENAMES['normal'],
        'inputSha256': BODY_HASH, 'inputBytes': len(BODY), 'expectedStatus': expected_status,
        'response': response, 'before': before, 'after': after, 'events': observed,
        'source': runtime.source_identity(), 'provenanceDigest': digest(receipt)}
    failures = []
    if status != expected_status: failures.append('expected_http_status')
    if len({row['correlationId'] for row in observed}) != 1: failures.append('one_observed_request')
    if not observed or observed[-1]['stage'] != 'REQUEST_END': failures.append('observation_scope_cleanup')
    if expected_status == 503:
        if response.get('code') != 'INDEXING_TRANSACTION_BOUNDARY': failures.append('original_boundary_failure')
        if before != after: failures.append('failure_before_object_or_row_change')
    else:
        checks = [row for row in observed if row['stage'] in EXTERNAL_STAGES]
        if not checks or any(row[key] for row in checks for key in
                            ('transactionActive', 'dataSourceBound', 'physicalConnectionHeld', 'detachedPhysicalConnectionHeld')):
            failures.append('external_boundary_holds_transaction_or_connection')
        if after['counts']['files'] != before['counts']['files'] + 1 or after['counts']['jobs'] != before['counts']['jobs'] + 1:
            failures.append('one_file_and_initial_job')
        if len(after['files']) != 1 or after['files'][0]['ownerId'] != owner or not after['files'][0]['hasParsedObject']:
            failures.append('synthetic_owner_and_parsed_metadata')
        if not response.get('jobId') or not response.get('fileId'): failures.append('durable_initial_accept')
        if len(after['objects']) != 1 or after['objects'][0]['sha256'] != BODY_HASH or after['objects'][0]['bytes'] != len(BODY):
            failures.append('original_object_correspondence')
    evidence['status'] = 'PASS' if not failures else 'FAIL'; evidence['failedChecks'] = failures
    path = _record(runtime, label, evidence)
    require(not failures, 'PDF boundary reproduction failed; preserved bounded evidence: ' + path)
    return evidence


def _new_events(runtime, previous):
    ids = {row['correlationId'] for row in previous}
    return [row for row in events(runtime) if row['correlationId'] not in ids]


def verify_denials(runtime, accepted):
    """Real authorization/input requests; no storage is created by these cases."""
    require(accepted['status'] == 'PASS' and accepted['response']['http'] == 200,
            'The actual fixed upload must pass before denial cases')
    path = runtime.results / 'pdf-boundary-denials.json'
    require(not path.exists(), 'Denial evidence already exists')
    token, _ = login(runtime)
    student, _ = login(runtime, 'student')
    other, _ = login(runtime, 'other')
    file_id = accepted['response']['fileId']
    before = snapshot(runtime, FILENAMES['normal']); previous = events(runtime)
    cases = []
    upload_path = '/api/pdf/upload-and-parse?filename=' + FILENAMES['normal']
    specifications = (
        ('no-token', upload_path, None, BODY, 401),
        ('student-role', upload_path, student, BODY, 403),
        ('foreign-file-hidden', '/api/pdf/' + str(file_id) + '/json', other, None, 404),
        ('invalid-filename', '/api/pdf/upload-and-parse?filename=invalid.txt', token, BODY, 400),
        ('invalid-body', upload_path, token, b'NOT A PDF', 400),
        ('size-limit', upload_path, token, b'%PDF-' + b'X' * (10 * 1024 * 1024 - 4), 413),
    )
    for label, request_path, actor, content, expected in specifications:
        status, data, _ = _http(runtime, request_path, token=actor, body=content,
                               headers={'Content-Type': 'application/pdf'} if content is not None else {})
        row = {'case': label, 'method': 'POST' if content is not None else 'GET',
               'expected': expected, 'response': _safe_response(status, data),
               'status': 'PASS' if status == expected else 'FAIL'}
        cases.append(row)
        if status != expected: break
    after = snapshot(runtime, FILENAMES['normal'])
    observed = _new_events(runtime, previous)
    unchanged = before == after
    evidence = {'runId': runtime.run_id, 'source': runtime.source_identity(), 'cases': cases,
        'before': before, 'after': after, 'events': observed, 'noStorageChanges': unchanged,
        'status': 'PASS' if unchanged and len(cases) == len(specifications)
                  and all(row['status'] == 'PASS' for row in cases) else 'FAIL'}
    _record(runtime, 'denials', evidence)
    require(evidence['status'] == 'PASS', 'PDF authorization/input denial regression failed')
    return evidence


def _upload_case(runtime, label, token):
    filename = FILENAMES[label]
    before = snapshot(runtime, filename)
    require(not before['files'], 'Synthetic case already exists; no duplicate retry')
    previous = events(runtime)
    status, data, _ = _http(runtime, '/api/pdf/upload-and-parse?filename=' + filename,
        token=token, body=BODY, headers={'Content-Type': 'application/pdf'})
    after = snapshot(runtime, filename)
    return {'response': _safe_response(status, data), 'before': before, 'after': after,
            'events': _new_events(runtime, previous), 'inputSha256': BODY_HASH, 'inputBytes': len(BODY)}


def verify_provider_failure(runtime):
    """One new provider failure and one later valid request; preserve partial rows."""
    require(not (runtime.results / 'pdf-boundary-provider-failure.json').exists(), 'Provider failure evidence already exists')
    token, owner = login(runtime)
    runtime.compose('pdf-boundary-consumers-stop', 'stop', 'worker', 'index-dispatcher')
    stopped = False
    try:
        runtime.compose('pdf-boundary-provider-stop', 'stop', 'ai'); stopped = True
        failed = _upload_case(runtime, 'provider-failure', token)
    finally:
        if stopped: runtime.compose('pdf-boundary-provider-restore', 'start', 'ai')
    failures = []
    if failed['response']['http'] != 500: failures.append('provider_failure_http_500')
    if failed['response'].get('code') == 'INDEXING_TRANSACTION_BOUNDARY': failures.append('boundary_failure_returned')
    if failed['after']['counts']['files'] != failed['before']['counts']['files'] + 1:
        failures.append('provider_failure_preserved_one_file_row')
    if failed['after']['counts']['jobs'] != failed['before']['counts']['jobs']:
        failures.append('provider_failure_did_not_enqueue')
    if len(failed['after']['files']) != 1 or failed['after']['files'][0]['hasParsedObject']:
        failures.append('provider_failure_preserved_unparsed_metadata')
    if len(failed['after']['objects']) != 1 or failed['after']['objects'][0]['sha256'] != BODY_HASH:
        failures.append('provider_failure_preserved_original_object')
    boundary_events = [row for row in failed['events'] if row['stage'] in EXTERNAL_STAGES]
    if not any(row['stage'] == 'PARSE_BEFORE' for row in boundary_events) or any(row[key] for row in boundary_events
            for key in ('transactionActive', 'dataSourceBound', 'physicalConnectionHeld', 'detachedPhysicalConnectionHeld')):
        failures.append('provider_failure_external_boundary')
    failed.update(status='PASS' if not failures else 'FAIL', failedChecks=failures,
                  runId=runtime.run_id, source=runtime.source_identity(),
                  wholeUploadAtomic=False, scope='Original object and file row remain; no parsed object or initial job')
    _record(runtime, 'provider-failure', failed)
    require(not failures, 'Provider exception regression failed; partial evidence preserved')
    later = _upload_case(runtime, 'after-failure', token)
    failures = []
    if later['response']['http'] != 200 or not later['response'].get('jobId'): failures.append('subsequent_http_success')
    if later['after']['counts']['files'] != later['before']['counts']['files'] + 1 or \
            later['after']['counts']['jobs'] != later['before']['counts']['jobs'] + 1:
        failures.append('subsequent_single_file_and_job')
    if len(later['after']['files']) != 1 or later['after']['files'][0]['ownerId'] != owner:
        failures.append('subsequent_owner')
    if len(later['after']['objects']) != 1 or later['after']['objects'][0]['sha256'] != BODY_HASH:
        failures.append('subsequent_original_object')
    boundaries = [row for row in later['events'] if row['stage'] in EXTERNAL_STAGES]
    if not boundaries or any(row[key] for row in boundaries for key in
            ('transactionActive', 'dataSourceBound', 'physicalConnectionHeld', 'detachedPhysicalConnectionHeld')):
        failures.append('subsequent_clean_external_boundary')
    later.update(status='PASS' if not failures else 'FAIL', failedChecks=failures,
                 runId=runtime.run_id, source=runtime.source_identity(),
                 sameServerThreadClaim='NOT_ASSERTED; HTTP event fields deliberately omit thread identity')
    _record(runtime, 'after-failure', later)
    require(not failures, 'Subsequent actual PDF request failed; preserved previous exception evidence')
    return failed, later


def verify_activation(runtime, accepted_cases):
    """Run only receipted new consumers; inspect these two new PDF jobs and Chroma."""
    require(len(accepted_cases) == 2 and all(case['response']['http'] == 200 for case in accepted_cases),
            'Exactly two successful synthetic HTTP cases required')
    token, owner = login(runtime)
    runtime.compose('pdf-boundary-chroma-start', 'start', 'chroma')
    runtime.verify_pending_work()
    runtime.compose('pdf-boundary-consumers-start', 'start', 'worker', 'index-dispatcher')
    results = []
    try:
        for case in accepted_cases:
            job = str(uuid.UUID(case['response']['jobId'])); file_id = int(case['response']['fileId'])
            deadline = time.monotonic() + 60
            while True:
                status, state, _ = _http(runtime, '/api/indexing/jobs/' + job, token=token)
                require(status == 200 and isinstance(state, dict), 'Initial job status unavailable')
                if state.get('state') in ('SUCCEEDED', 'FAILED', 'REVOKED', 'SUPERSEDED'): break
                require(time.monotonic() < deadline, 'Initial PDF job did not finish within the bounded interval')
                time.sleep(.5)
            ledger = _rows(runtime, "SELECT JSON_OBJECT('jobId',j.job_id,'state',j.state,'generation',j.execution_generation,"
                "'sourceRevision',j.source_revision,'resourceRevision',r.source_revision,'sourceHash',j.source_hash,"
                "'snapshotHash',SHA2(j.snapshot_json,256),'resourceHash',r.current_source_hash,'ownerId',r.owner_id,"
                "'fileOwner',f.uploader_id,'fileId',f.id,'resourceKind',r.resource_kind,'activeExecution',r.active_execution_id,"
                "'executionId',e.id,'executionGeneration',e.generation,'executionState',e.state,'candidate',e.candidate_name,"
                "'expectedChunks',e.expected_chunks,'actualChunks',e.actual_chunks,'activations',r.activation_count) "
                "FROM index_jobs j JOIN index_resources r ON r.id=j.resource_pk JOIN uploaded_files f ON f.id=r.resource_id "
                "LEFT JOIN index_executions e ON e.id=r.active_execution_id WHERE r.resource_kind='PDF' AND j.job_id='" + job + "';")
            require(len(ledger) == 1, 'Initial PDF ledger row mismatch')
            row = ledger[0]
            candidate = row['candidate']
            require(isinstance(candidate, str) and re.fullmatch(r'idx_[a-zA-Z0-9_]+', candidate), 'Invalid active candidate')
            code = "import json;from app.indexing.chroma import fetch;c=fetch(" + repr(candidate) + ");d=c.get(include=['embeddings']);" \
                "v=[float(x) for x in d['embeddings'][0]];q=c.query(query_embeddings=[v],n_results=1,include=['distances']);" \
                "print(json.dumps({'count':c.count(),'queryCount':len(q['ids'][0]),'matchedKnownId':q['ids'][0][0] in d['ids']}))"
            physical = json.loads(runtime.compose('pdf-boundary-chroma-query', 'exec', '-T', 'ai', 'python', '-c', code).stdout)
            passed = state['state'] == row['state'] == 'SUCCEEDED' and row['ownerId'] == row['fileOwner'] == owner \
                and row['fileId'] == file_id and row['resourceKind'] == 'PDF' and row['generation'] == row['executionGeneration'] == 1 \
                and row['sourceRevision'] == row['resourceRevision'] == 1 and row['activations'] == 1 \
                and row['sourceHash'] == row['snapshotHash'] == row['resourceHash'] \
                and row['activeExecution'] == row['executionId'] and row['executionState'] == 'ACTIVE' \
                and physical['count'] == row['expectedChunks'] == row['actualChunks'] and physical['count'] > 0 \
                and physical['queryCount'] == 1 and physical['matchedKnownId']
            results.append({'ledger': row, 'physicalChroma': physical, 'status': 'PASS' if passed else 'FAIL'})
            if not passed: break
    finally:
        runtime.compose('pdf-boundary-consumers-stop', 'stop', 'index-dispatcher', 'worker')
        _record(runtime, 'activation', {'runId': runtime.run_id, 'source': runtime.source_identity(), 'cases': results,
            'status': 'PASS' if len(results) == 2 and all(row['status'] == 'PASS' for row in results) else 'FAIL'})
    require(len(results) == 2 and all(row['status'] == 'PASS' for row in results), 'Initial PDF activation regression failed')
    return results


def run(runtime, expected_status):
    """Caller must first pass this attempt's auth gate and start required MAIN services."""
    accepted = reproduction(runtime, expected_status)
    if expected_status == 503: return {'reproduction': accepted}
    denials = verify_denials(runtime, accepted)
    failed, later = verify_provider_failure(runtime)
    activation = verify_activation(runtime, [accepted, later])
    return {'reproduction': accepted, 'denials': denials, 'providerFailure': failed,
            'afterFailure': later, 'activation': activation}
