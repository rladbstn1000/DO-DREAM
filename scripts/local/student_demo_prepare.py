#!/usr/bin/env python3
"""Prepare only the explicitly enabled, authored Phase 4 fixture through real domain APIs.

No Docker/SQL, provider calls, passwords, tokens or response bodies are printed.
The generated local teacher password is consumed only by the existing local HTTP helper.
"""
import argparse
import datetime
import json
import time
from pathlib import Path
from verify import ENV, req
from manage import ROOT, RESULTS

EMAIL = 'demo-phase5-v1@local.dodream.invalid'
VERSION = 'student-web-phase5-v1'


def prepare(wait_seconds=120):
    code, config, _, _ = req('be', '/api/auth/demo/config')
    if code != 200 or not isinstance(config, dict) or not config.get('enabled'):
        raise RuntimeError('Demo is disabled; enable the server local opt-in first')
    if config.get('fixtureVersion') != VERSION:
        raise RuntimeError('Unexpected demo fixture version')
    code, login, _, _ = req('be', '/api/auth/teacher/login', body={
        'email': EMAIL, 'password': ENV['LOCAL_TEACHER_PASSWORD']})
    if code != 200 or not isinstance(login, dict) or not login.get('accessToken'):
        raise RuntimeError('Dedicated demo teacher login failed')
    token = login['accessToken']
    code, _, _, _ = req('be', '/api/demo/prepare', token, {}, timeout=90)
    if code != 200:
        raise RuntimeError('Demo preparation failed with HTTP ' + str(code))
    code, first, _, _ = req('be', '/api/demo/preparation', token)
    if code != 200 or first.get('fixtureVersion') != VERSION:
        raise RuntimeError('Demo preparation metadata unavailable')
    code, _, _, _ = req('be', '/api/demo/prepare', token, {}, timeout=90)
    code2, repeat, _, _ = req('be', '/api/demo/preparation', token)
    if code != 200 or code2 != 200 or first.get('samples') != repeat.get('samples') or first.get('counts') != repeat.get('counts'):
        raise RuntimeError('Repeated fixture preparation changed its identities or logical counts')
    counts = first['counts']
    # Publication/version boundary checks may have added valid immutable jobs to
    # these new demo materials. Reopening a preserved demo must not delete that
    # history or mistake it for duplicate preparation. The replay comparison
    # above still requires this preparation itself to add exactly zero jobs.
    if (counts.get('files') != 2 or counts.get('materials') != 2
            or counts.get('quizzes') != 4 or counts.get('logicalJobs', 0) < 4):
        raise RuntimeError('Unexpected dedicated fixture counts')
    until = time.monotonic() + wait_seconds
    while True:
        code, config, _, _ = req('be', '/api/auth/demo/config')
        if code == 200 and config.get('ready'):
            break
        if time.monotonic() >= until:
            raise RuntimeError('Actual indexing is not ready; no activation state was fabricated')
        time.sleep(1)
    result = {'fixtureVersion': VERSION, 'status': 'PASS', 'sameVersionReplay': 'PASS',
              'counts': first['counts'], 'samples': first['samples'], 'readable': True}
    destination = RESULTS
    destination.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    (destination / ('demo-preparation-' + stamp + '.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2))
    statuses = {s['key']: s for s in config['samples']}
    plan = {'fixtureVersion': VERSION, 'teacherEmail': EMAIL, 'teacherUserId': first['teacherId'],
            'classroomId': first['classroomId'], 'samples': [
                {'key': s['key'], 'materialId': s['materialId'], 'uploadedFileId': s['fileId'],
                 'title': statuses[s['key']]['title'], 'source': statuses[s['key']]['source'],
                 'indexing': {'sourceRevision': statuses[s['key']]['sourceRevision'], 'readable': statuses[s['key']]['readable']}}
                for s in first['samples']]}
    (destination / 'student-demo-plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--wait-seconds', type=int, default=120)
    args = parser.parse_args()
    if not 0 <= args.wait_seconds <= 300:
        parser.error('wait must be 0..300 seconds')
    try:
        prepare(args.wait_seconds)
    except Exception as failure:
        # Deliberately print only our fixed message/class, never HTTP response text.
        print(json.dumps({'status': 'FAIL', 'reason': str(failure) if isinstance(failure, RuntimeError) else type(failure).__name__}))
        raise SystemExit(1)
