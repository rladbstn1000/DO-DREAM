#!/usr/bin/env python3
"""Isolated local Compose operations; never deletes data or emits secret values."""
import base64
import hashlib
import datetime
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
import scope_guard

ROOT = Path(__file__).resolve().parents[2]
LOCAL = ROOT / '.local'
RESULTS = Path(os.environ.get('DODREAM_RESULTS_DIR', str(LOCAL / 'phase4' / 'results')))
RESULTS.mkdir(parents=True, exist_ok=True)
PROJECT = 'dodream-phase1'
ENV_FILE = LOCAL / 'env'

def settings():
    if not ENV_FILE.exists():
        raise SystemExit('Run python3 scripts/local/manage.py init first.')
    values = {}
    for line in ENV_FILE.read_text().splitlines():
        if line and not line.startswith('#'):
            key, value = line.split('=', 1)
            values[key] = value
    return values

def clean_env():
    env = os.environ.copy()
    # Explicit file takes precedence over shell values and any pre-existing .env.
    for key in settings():
        env.pop(key, None)
    for key in list(env):
        if key.startswith('COMPOSE_'):
            env.pop(key)
    env['COMPOSE_DISABLE_ENV_FILE'] = 'true'
    return env

def redact(text):
    if ENV_FILE.exists():
        for key, value in settings().items():
            if any(word in key for word in ('PASSWORD', 'SECRET')) and value:
                text = text.replace(value, '[REDACTED]')
    text = re.sub(r'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', '[JWT REDACTED]', text)
    text = re.sub(r'(Using generated security password:)\s*\S+', r'\1 [REDACTED]', text)
    return text

def compose_base():
    return ['docker', 'compose', '--project-directory', str(ROOT), '--env-file', str(ENV_FILE),
            '-p', PROJECT, '-f', str(ROOT / 'compose.local.yml')]

def compose_args(*args):
    args=list(args)
    # Every one-off run is identifiable by labels as well as a unique task name.
    at=0
    while at<len(args) and args[at] in ('--profile','--progress'):at+=2
    if at<len(args) and args[at]=='run':
        at+=1
        if '--name' not in args:args[at:at]=['--name','dodream-phase3b-test-'+secrets.token_hex(6)]
        args[at:at]=['--label',scope_guard.RUN_LABEL]
    base=compose_base()
    operation,_=scope_guard.command_scope(args)
    if operation in scope_guard.MUTATIONS:
        scope_guard.gate(args,base,ROOT,clean_env(),RESULTS)
    return [*base,*args]

def stop_owned_test(name):
    # Revalidate local endpoint and full resource scope even on a timeout path.
    scope_guard.gate(['config','--quiet'],compose_base(),ROOT,clean_env(),RESULTS)
    rows=scope_guard.read_metadata(clean_env())
    row=next((r for r in rows if r['name']==name),None)
    scope_guard.require(row and row['project']==PROJECT and row['service'] in scope_guard.SERVICES
                        and row['task']=='phase3b' and name.startswith('dodream-phase3b-'),
                        'One-off cleanup target is not owned by this task')
    # Use the inspected immutable ID; never target an unverified name.
    return subprocess.run(['docker','stop','--time','5',row['id']],capture_output=True,text=True,
                          env=clean_env(),timeout=15)

def source_identity():
    head=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True).stdout.strip()
    names=subprocess.run(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=ROOT,capture_output=True).stdout.split(b'\0')
    digest=hashlib.sha256()
    for raw in sorted(set(names)):
        if not raw or raw.endswith(b'.DS_Store') or raw.rsplit(b'/',1)[-1]==b'.env':continue
        path=ROOT/os.fsdecode(raw)
        if path.is_file() and not path.is_symlink():digest.update(raw+b'\0'+hashlib.sha256(path.read_bytes()).digest())
    return {'head':head,'working_source_sha256':digest.hexdigest()}

def crash_owned(service):
    scope_guard.gate(['config','--quiet'],compose_base(),ROOT,clean_env(),RESULTS)
    row=next((r for r in scope_guard.read_metadata(clean_env()) if r['service']==service and r['project']==PROJECT and r['name']==PROJECT+'-'+service+'-1'),None)
    target=scope_guard.crash_target(row,service)
    return run('crash-'+service,['docker','kill','--signal','KILL',target])

def pause_chroma(resume=False):
    scope_guard.gate(['config','--quiet'],compose_base(),ROOT,clean_env(),RESULTS)
    row=next((r for r in scope_guard.read_metadata(clean_env()) if r['service']=='chroma' and r['project']==PROJECT),None)
    target=scope_guard.chroma_pause_target(row,resume)
    action='unpause' if resume else 'pause'
    return run('chroma-'+action,['docker',action,target])

def record(name, command, result, started):
    RESULTS.mkdir(parents=True, exist_ok=True)
    entry = {'command': command, 'exit_code': result.returncode,
             'status': 'PASS' if result.returncode == 0 else 'FAIL',
             'started_at': started, 'finished_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    entry['source'] = source_identity()
    if shutil.which('docker'):
        ids=subprocess.run(['docker','ps','-a','--filter','label=com.docker.compose.project='+PROJECT,'--format','{{.ID}}'],capture_output=True,text=True,env=clean_env())
        if ids.returncode==0 and ids.stdout.strip():
            images=subprocess.run(['docker','inspect','--format','{{index .Config.Labels "com.docker.compose.service"}}\t{{.Image}}',*ids.stdout.split()],capture_output=True,text=True,env=clean_env())
            if images.returncode==0:entry['observed_container_image_ids']=sorted(set(images.stdout.splitlines()))
    with (RESULTS / 'commands.jsonl').open('a') as history:
        history.write(json.dumps(entry) + '\n')
    stamp = started.replace(':','').replace('.','')
    (RESULTS / (name + '-' + stamp + '.log')).write_text(redact(result.stdout or ''))
    (RESULTS / (name + '-' + stamp + '.json')).write_text(json.dumps(entry, indent=2) + '\n')
    (RESULTS / (name + '.json')).write_text(json.dumps(entry, indent=2) + '\n')
    (RESULTS / (name + '.log')).write_text(redact(result.stdout or ''))
    print(json.dumps(entry, ensure_ascii=False))
    print('sanitized_output:', RESULTS / (name + '.log'))

def run(name, args):
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    result = subprocess.run(args, cwd=ROOT, env=clean_env(), stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    record(name, args, result, started)
    if result.returncode:
        print(redact(result.stdout[-5000:]))
    return result

def compose(name, *args):
    return run(name, compose_args(*args))

def unit_tests():
    # The real-DB indexing suite creates new synthetic ledger rows and requires
    # the dispatcher to remain stopped while it asserts transaction state.
    def dispatcher():
        scope_guard.gate(['config','--quiet'],compose_base(),ROOT,clean_env(),RESULTS)
        rows=[r for r in scope_guard.read_metadata(clean_env())
              if r['project']==PROJECT and r['service']=='index-dispatcher']
        scope_guard.require(len(rows)<=1 and all(r['name']==PROJECT+'-index-dispatcher-1' for r in rows),
                            'Unit-test dispatcher target is ambiguous')
        return rows[0] if rows else None

    before=dispatcher()
    scope_guard.require(before is None or before['state'] in ('running','exited','created'),
                        'Unit-test dispatcher has an unsupported initial state')
    restore=before is not None and before['state']=='running'
    try:
        if restore:
            stopped=compose('unit-dispatcher-stop','stop','index-dispatcher')
            if stopped.returncode:
                return stopped.returncode
            current=dispatcher()
            scope_guard.require(current and current['id']==before['id'] and current['state']=='exited',
                                'Unit-test dispatcher did not stop with the same verified identity')
        results = [compose('be-tests', '--profile', 'test', 'run', '--rm', '--no-deps', 'be-test'),
                   compose('ai-tests', 'exec', '-T', 'ai', 'python', '-m', 'unittest', 'discover', '-s', 'tests', '-v'),
                   compose('pdf-tests', 'exec', '-T', 'python-service', 'python', '-m', 'unittest', 'discover', '-s', 'tests', '-v')]
        return int(any(r.returncode for r in results))
    finally:
        if restore:
            current=dispatcher()
            scope_guard.require(current and current['id']==before['id'] and current['state'] in ('running','exited'),
                                'Unit-test dispatcher identity/state changed; restoration blocked')
            # Compose start may also start dependencies. Restore only the exact
            # container whose ownership, identity and prior state were verified.
            resumed=run('unit-dispatcher-restore',['docker','start',before['id']])
            scope_guard.require(resumed.returncode==0,'Unit-test dispatcher restoration failed')
            current=dispatcher()
            scope_guard.require(current and current['id']==before['id'] and current['state']=='running',
                                'Unit-test dispatcher running state was not restored')

def init():
    LOCAL.mkdir(exist_ok=True, mode=0o700)
    RESULTS.mkdir(exist_ok=True)
    if ENV_FILE.exists():
        print('Existing .local/env preserved. No secrets changed.')
        return
    values = {'COMPOSE_PROJECT_NAME': PROJECT, 'BE_PORT': '18082', 'AI_PORT': '18000',
              'PDF_PORT': '18001', 'WEB_PORT': '15173', 'MYSQL_DATABASE': 'dodream_local',
              'MYSQL_USER': 'dodream', 'MYSQL_PASSWORD': secrets.token_hex(24),
              'MYSQL_ROOT_PASSWORD': secrets.token_hex(24),
              'JWT_SECRET_BASE64': base64.b64encode(secrets.token_bytes(32)).decode(),
              'LOCAL_TEACHER_PASSWORD': secrets.token_urlsafe(24),
              'LOCAL_STUDENT_SECRET': secrets.token_urlsafe(24)}
    with ENV_FILE.open('x') as f:
        os.chmod(ENV_FILE, 0o600)
        f.write('\n'.join(f'{key}={value}' for key, value in values.items()) + '\n')
    print('Created ignored .local/env (0600); generated secrets are not printed.')

def check():
    status = 0
    for name, args in [('java', ['java', '-version']), ('node', ['node', '--version']),
                       ('npm', ['npm', '--version']), ('python', [sys.executable, '--version']),
                       ('docker', ['docker', '--version']), ('compose', ['docker', 'compose', 'version'])]:
        if not shutil.which(args[0]):
            print(name, 'BLOCKED: unavailable'); status = 1; continue
        result = run('check-' + name, args)
        print(name, redact(result.stdout.strip()))
        status |= result.returncode
    current = subprocess.run(['docker', 'ps', '--filter', 'label=com.docker.compose.project=' + PROJECT,
                              '--format', '{{.Ports}}'], capture_output=True, text=True)
    for key in ('BE_PORT', 'AI_PORT', 'PDF_PORT', 'WEB_PORT'):
        port = int(settings()[key])
        with socket.socket() as sock:
            try:
                sock.bind(('127.0.0.1', port))
                print(key, port, 'AVAILABLE')
            except OSError:
                owned = f':{port}->' in current.stdout
                print(key, port, 'IN_USE_BY_PROJECT' if owned else 'CONFLICT: change .local/env; never kill another process')
                if not owned: status = 1
    return status

def snapshot(name):
    items = {}
    commands = {
        'containers': ['docker', 'ps', '-a', '--format', '{{.ID}}\t{{.Names}}\t{{.State}}\t{{.Ports}}'],
        'volumes': ['docker', 'volume', 'ls', '--format', '{{.Name}}'],
        'networks': ['docker', 'network', 'ls', '--format', '{{.Name}}'],
    }
    for key, args in commands.items():
        result = subprocess.run(args, capture_output=True, text=True)
        if result.returncode: raise SystemExit(redact(result.stderr))
        items[key] = result.stdout.splitlines()
    # New snapshots classify ownership by exact Compose labels, not a name prefix.
    items['container_metadata']=scope_guard.read_metadata(clean_env())
    target = RESULTS / (name + '.json')
    if target.exists() and name == 'resources-before':
        print('Existing first snapshot preserved:', target); return
    target.write_text(json.dumps(items, indent=2) + '\n')
    print('resource inventory saved:', target)

def main():
    os.chdir(ROOT)
    command = sys.argv[1] if len(sys.argv) > 1 else 'help'
    if command == 'init': init(); return 0
    if command == 'help':
        print('init | check | config | scope | scope-test | build | up | demo-up | demo-prepare | demo-api | student-web | auth-test-up | test | auth | authorization | grading | grading-migrate | indexing | indexing-migrate | startup | smoke | security | persistence | status | stop | restart | isolation | resources-before | resources-after')
        return 0
    settings()
    if command == 'scope-test':return run('scope-unit',[sys.executable,'-m','unittest','discover','-s','scripts/local/tests','-v']).returncode
    if command == 'scope':
        scope_guard.gate(['config','--quiet'],compose_base(),ROOT,clean_env(),RESULTS)
        print('Current target metadata validated.');return 0
    if command == 'check': return check()
    if command == 'isolation': return run('isolation', [sys.executable, str(ROOT / 'scripts/local/check_resources.py')]).returncode
    if command.startswith('resources-') and command in ('resources-before', 'resources-after'):
        snapshot(command); return 0
    if command == 'config': return compose('compose-config', 'config', '--quiet').returncode
    if command == 'build': return compose('compose-build', '--profile', 'test', '--progress', 'plain', 'build').returncode
    if command == 'up':
        snapshot('resources-before')
        return compose('compose-up', 'up', '-d', '--wait', '--wait-timeout', '240').returncode
    if command == 'demo-up':
        # Opt-in is deliberate and server-side; never infer it from browser flags.
        os.environ['DODREAM_DEMO_ENABLED']='true'
        snapshot('resources-before')
        return compose('demo-up','up','-d','--wait','--wait-timeout','240').returncode
    if command in ('demo-prepare','demo-api','student-web'):
        script={'demo-prepare':'student_demo_prepare.py','demo-api':'verify_student_demo.py',
                'student-web':'verify_student_web.py'}[command]
        return run(command,[sys.executable,str(ROOT/'scripts/local'/script),*sys.argv[2:]]).returncode
    if command == 'auth-test-up':
        return compose('auth-test-up', '--profile', 'auth-test', 'up', '-d', '--wait', '--wait-timeout', '240', 'be-auth-short', 'web-auth-test').returncode
    if command == 'status':
        result = compose('compose-status', 'ps', '--all'); print(redact(result.stdout)); return result.returncode
    if command == 'stop': return compose('compose-stop', '--profile', 'auth-test', 'stop').returncode
    if command == 'restart': return compose('compose-restart', 'restart').returncode
    if command == 'indexing-migrate': return run('index-migration-forward',[sys.executable,str(ROOT/'scripts/local/indexing_migration.py'),'forward']).returncode
    if command == 'indexing': return run('indexing',[sys.executable,str(ROOT/'scripts/local/verify_indexing.py'),*sys.argv[2:]]).returncode
    if command == 'test':
        return unit_tests()
    if command == 'auth':
        return run('auth-regression', [sys.executable, str(ROOT / 'scripts/local/verify_auth.py')]).returncode
    if command == 'grading':
        return run('grading', [sys.executable, str(ROOT / 'scripts/local/verify_grading.py')]).returncode
    if command == 'grading-migrate':
        return run('grading-migrate', [sys.executable, str(ROOT / 'scripts/local/grading_migration.py'), 'forward']).returncode
    if command == 'authorization':
        return run('authorization', [sys.executable, str(ROOT / 'scripts/local/verify_authorization.py')]).returncode
    if command == 'startup':
        return run('startup-key-regression', [sys.executable, str(ROOT / 'scripts/local/verify_startup.py')]).returncode
    if command in ('smoke', 'security', 'persistence'):
        return run(command, [sys.executable, str(ROOT / 'scripts/local/verify.py'), command]).returncode
    raise SystemExit('Unknown command. Use help.')

if __name__ == '__main__':
    try:sys.exit(main())
    except scope_guard.ScopeError as error:
        print('BLOCKED:',str(error));sys.exit(2)
