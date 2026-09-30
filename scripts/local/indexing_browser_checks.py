"""Actual teacher UI orchestration, invoked only by the guarded root Runner.

The browser edits three new synthetic fixtures and writes metadata checkpoints.
All service operations remain on the root runner's reviewed scope path.
"""
from datetime import datetime, timezone
import json
import os
import signal
import subprocess
import sys
import time
import uuid

from manage import ROOT, RESULTS, clean_env, record


def browser(r):
    check = sys.modules[type(r).__module__].check
    publish, _ = r.healthy('ui-ready')
    try:
        r.service('stop', 'index-dispatcher')
        first = r.fixture('ui-first-failure')
        first_job, _ = r.publish(first)
        r.controls(first_job, fault='embedding_failure')
        r.service('up', 'index-dispatcher')
        first_state = r.done(first_job, 'FAILED')
        check('index_ui_first_failure_is_unreadable', first_state['readable'] is False and first_state['retryable'] is True)
        r.controls(first_job)
        reindex, _ = r.healthy('ui-reindex-failure')
        r.service('stop', 'index-dispatcher')
        reindex_job, _ = r.request(reindex)
        r.controls(reindex_job, fault='partial_failure')
        r.service('up', 'index-dispatcher')
        reindex_state = r.done(reindex_job, 'FAILED')
        check('index_ui_reindex_failure_retains_readability', reindex_state['readable'] is True
              and reindex_state['activeCurrent'] is False and reindex_state['retryable'] is True)
        r.controls(reindex_job)
    except Exception:
        r.service('up', 'index-dispatcher')
        raise

    run_id = str(uuid.uuid4())
    directory = RESULTS.parent / 'browser-ui'
    directory.mkdir(parents=True, exist_ok=True)
    plan = {'runId': run_id, 'publishTitle': publish['title'], 'firstFailureTitle': first['title'],
            'reindexFailureTitle': reindex['title']}
    plan_path = directory / (run_id + '.plan.json')
    with plan_path.open('x') as stream:
        json.dump(plan, stream, ensure_ascii=False)
        stream.write('\n')
    command = ['npm', 'run', 'test:browser-indexing']
    env = clean_env()
    env['DODREAM_INDEX_BROWSER_PLAN'] = str(plan_path)
    # This helper always uses the reviewed local default target.
    env.pop('DODREAM_INDEX_BROWSER_ORIGIN', None)
    process = None
    published = None
    complete = None
    error = None
    cleanup_errors = []
    started = datetime.now(timezone.utc).isoformat()
    capture = RESULTS / ('browser-indexing-child-' + run_id + '.log')

    def checkpoint(event, seconds):
        target = directory / (run_id + '.' + event + '.json')
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if target.exists():
                if target.is_symlink():
                    raise RuntimeError('Unexpected UI checkpoint symlink')
                value = json.loads(target.read_text())
                if value.get('runId') != run_id or value.get('event') != event:
                    raise RuntimeError('UI checkpoint identity mismatch')
                return value
            if process.poll() is not None:
                raise RuntimeError('Browser child ended before ' + event)
            time.sleep(.05)
        raise TimeoutError('Browser checkpoint deadline: ' + event)

    try:
        r.service('stop', 'index-dispatcher')
        with capture.open('x') as output:
            process = subprocess.Popen(command, cwd=ROOT / 'fe-web', env=env,
                                       stdout=output, stderr=subprocess.STDOUT, text=True,
                                       start_new_session=True)
            published = checkpoint('published', 60)
            job = published.get('jobId')
            check('index_ui_published_checkpoint_is_real_queued_job',
                  isinstance(job, str) and str(uuid.UUID(job)) == job
                  and published.get('materialId') == publish['id'] and published.get('state') == 'QUEUED')
            if job not in r.jobs:
                r.jobs.append(job)
            r.controls(job, gate='after_partial', generation=1)
            r.service('up', 'index-dispatcher')
            processing = checkpoint('processing', 40)
            check('index_ui_processing_checkpoint_matches_publication',
                  processing.get('jobId') == job and processing.get('materialId') == publish['id']
                  and processing.get('sourceRevision') == published.get('sourceRevision')
                  and processing.get('state') == 'PROCESSING')
            r.release(job, 'after_partial')
            complete = checkpoint('complete', 120)
            process.wait(timeout=10)
    except Exception as failure:
        error = failure
    finally:
        if process is not None and process.poll() is None:
            # This new session contains only our npm/Node child. Node handles TERM
            # by closing its own isolated Playwright browser before reporting failure.
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=5)
                cleanup_errors.append('Browser child required forced termination')
        if published and isinstance(published.get('jobId'), str):
            try:
                if str(uuid.UUID(published['jobId'])) == published['jobId']:
                    r.release(published['jobId'], 'after_partial')
            except Exception:
                cleanup_errors.append('Own UI gate release failed')
        try:
            r.service('up', 'index-dispatcher')
        except Exception:
            cleanup_errors.append('Own dispatcher restore failed')
        output = capture.read_text() if capture.exists() else ''
        exit_code = process.returncode if process is not None else 1
        if error is not None or cleanup_errors:
            exit_code = exit_code or 1
        record('browser-indexing-orchestration', command,
               subprocess.CompletedProcess(command, exit_code, stdout=output), started)
    if error is not None:
        check('index_ui_orchestration_completed', False, {'errorType': type(error).__name__, 'cleanupErrors': cleanup_errors})
    check('index_ui_owned_child_and_dispatcher_restored', not cleanup_errors, cleanup_errors)
    report = json.loads((RESULTS / 'browser-indexing-checks.json').read_text())
    counts = report.get('counts', {})
    check('actual_chrome_indexing_ui_14_checks', process.returncode == 0 and complete.get('exitCode') == 0
          and counts == {'PASS': 14, 'FAIL': 0, 'BLOCKED': 0} and complete.get('counts') == counts
          and len(report.get('checks', [])) == 14
          and all(row.get('status') == 'PASS' for row in report['checks'])
          and report.get('activation', {}).get('jobId') == published['jobId'], counts)
    r.evidence.append({'scenario': 'actual_teacher_indexing_ui', 'runId': run_id,
                       'published': published, 'counts': counts, 'browser': report.get('browser'),
                       'activation': report.get('activation'), 'recoveries': report.get('recoveries'),
                       'plan': str(plan_path.relative_to(ROOT))})
