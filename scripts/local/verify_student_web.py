#!/usr/bin/env python3
"""One fail-fast Chrome acceptance run; service faults use the existing scope gate."""
from datetime import datetime, timezone
import hashlib
import json
import os
import signal
import subprocess
import time
import uuid
from manage import ROOT, RESULTS, clean_env, compose, pause_chroma, record


def app_digest():
    digest=hashlib.sha256()
    for directory in ('fe-web/src','be/src','ai/app'):
        for path in sorted((ROOT/directory).rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts:
                digest.update(str(path.relative_to(ROOT)).encode()+b'\0'+path.read_bytes())
    digest.update((ROOT/'compose.local.yml').read_bytes())
    return digest.hexdigest()


def main():
    run_id=str(uuid.uuid4())
    directory=RESULTS.parent/'browser-ui'
    directory.mkdir(parents=True,exist_ok=True)
    plan=json.loads((RESULTS/'student-demo-plan.json').read_text())
    plan['runId']=run_id
    plan_path=directory/(run_id+'.student-plan.json')
    with plan_path.open('x') as stream:json.dump(plan,stream)
    env=clean_env();env['DODREAM_STUDENT_BROWSER_PLAN']=str(plan_path)
    env['DODREAM_DEMO_ENABLED']='true'
    os.environ['DODREAM_DEMO_ENABLED']='true'
    command=['node','tests/browser-student.mjs']
    started=datetime.now(timezone.utc).isoformat()
    before=app_digest();process=None;error=None;restores=set();handled=set()
    capture=RESULTS/('student-browser-child-'+run_id+'.log')
    try:
        with capture.open('x') as output:
            process=subprocess.Popen(command,cwd=ROOT/'fe-web',env=env,stdout=output,stderr=subprocess.STDOUT,
                                     text=True,start_new_session=True)
            deadline=time.monotonic()+1200
            while process.poll() is None:
                if time.monotonic()>deadline:raise TimeoutError('Acceptance deadline')
                for request_path in sorted(directory.glob(run_id+'.*.request.json')):
                    if request_path.name in handled:continue
                    if request_path.is_symlink():raise RuntimeError('Checkpoint symlink')
                    request=json.loads(request_path.read_text())
                    if request.get('runId')!=run_id:raise RuntimeError('Checkpoint identity')
                    event=request.get('event')
                    if event=='verify-evidence':
                        import verify
                        from verify_student_demo import source_evidence,grading_evidence
                        evidence=request.get('evidence',{})
                        sources=evidence.get('sourceEvidence',[]);submissions=evidence.get('logicalSubmissions',[])
                        if not 1<=len(sources)<=20 or not 1<=len(submissions)<=20:raise RuntimeError('Evidence bound')
                        source_checks=[source_evidence(source,verify) for source in sources]
                        grading_checks=grading_evidence(submissions,verify)
                        passed=all(r['bound'] and r['matched'] for r in source_checks) and all(r['passed'] for r in grading_checks)
                        (RESULTS/('student-storage-'+run_id+'-'+str(len(handled))+'.json')).write_text(json.dumps({
                            'status':'PASS' if passed else 'FAIL','sources':source_checks,'grading':grading_checks},indent=2)+'\n')
                        if not passed:raise RuntimeError('Actual storage evidence mismatch')
                        result=subprocess.CompletedProcess([],0)
                    elif event in ('dispatcher-stop','dispatcher-start','ai-stop','ai-start'):
                        service='index-dispatcher' if event.startswith('dispatcher') else 'ai'
                        stop=event.endswith('stop')
                        result=compose('student-ui-'+event,*(['stop',service] if stop else
                            ['up','-d','--no-deps','--wait','--wait-timeout','180',service]))
                        if stop:restores.add(service)
                        elif result.returncode==0:restores.discard(service)
                    elif event in ('chroma-pause','chroma-unpause'):
                        resume=event.endswith('unpause');result=pause_chroma(resume)
                        if resume and result.returncode==0:restores.discard('chroma')
                        else:restores.add('chroma')
                    else:raise RuntimeError('Unknown acceptance event')
                    if result.returncode:raise RuntimeError('Owned service operation')
                    target=request_path.with_name(request_path.name.replace('.request.json','.response.json'))
                    with target.open('x') as stream:json.dump({'runId':run_id,'event':event,'status':'PASS'},stream)
                    handled.add(request_path.name)
                time.sleep(.1)
        if process.returncode:raise RuntimeError('Browser acceptance failed')
        if before!=app_digest():raise RuntimeError('Application source changed during acceptance')
    except Exception as failure:
        error=type(failure).__name__
    finally:
        if process is not None and process.poll() is None:
            try:os.killpg(process.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            try:process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                try:os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                process.wait(timeout=5)
        for service in sorted(restores):
            result=pause_chroma(True) if service=='chroma' else compose('student-ui-restore-'+service,
                'up','-d','--no-deps','--wait','--wait-timeout','180',service)
            if result.returncode:error='ServiceRestoreFailed'
        code=1 if error or process is None else process.returncode
        record('student-browser-orchestration',command,subprocess.CompletedProcess(command,code,
            stdout=capture.read_text() if capture.exists() else ''),started)
        summary={'runId':run_id,'status':'FAIL' if code else 'PASS','exitCode':code,
                 'applicationSourceBefore':before,'applicationSourceAfter':app_digest(),
                 'errorType':error,'startedAt':started,'finishedAt':datetime.now(timezone.utc).isoformat()}
        for target in (RESULTS/('phase5-acceptance-'+run_id+'.json'),RESULTS/'phase5-acceptance.json'):
            target.write_text(json.dumps(summary,indent=2)+'\n')
        print(json.dumps(summary))
    return code


if __name__=='__main__':raise SystemExit(main())
