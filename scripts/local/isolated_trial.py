#!/usr/bin/env python3
"""Finite-scope planner and explicit, receipt-bound isolated trial execution.

The manifest is the sole trial-specific configuration. Compose is generated data,
not another maintained configuration. Planning is NOT permission to execute.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import sys
import os
import base64
import secrets
import shutil
import socket
import subprocess
import time
import uuid
import signal
from datetime import datetime, timezone
from urllib.parse import urlsplit


class PolicyError(ValueError):
    pass


class ExecutionDisabled(RuntimeError):
    pass


MAIN = ('mysql', 'redis', 'be', 'ai', 'python-service', 'web')
SHORT = ('mysql', 'redis', 'be', 'ai', 'be-auth-short', 'web-auth-test')
CONSUMERS = ('worker', 'index-dispatcher')
SUITES = {
    'auth': SHORT,
    'demo-disabled': SHORT,
    'grading': MAIN,
    'hardening': MAIN + ('chroma',),
    'authorization': MAIN + ('chroma',) + CONSUMERS,
    'indexing': MAIN + ('chroma',) + CONSUMERS,
    'student': MAIN + ('chroma',) + CONSUMERS + ('be-auth-short', 'web-auth-test'),
}
PRESTART = [
    'Separate user authorization for actual new-environment execution.',
    'Read-only target metadata must prove all planned containers, volumes and networks absent; no adoption.',
    'Fresh-inventory validation is first-creation only; later phases need a creation receipt and exact owned-state validation (not yet implemented).',
    'Confirm loopback ports free without terminating other processes.',
    'Generate fresh credentials only inside this trial; never read/copy old .env or .local/env. Use URL-safe MySQL passwords.',
    'Build reviewed images or prove immutable image/source correspondence and absence of embedded secrets.',
    'Adapt migration/fixture/orchestration launchers: current manage.py and imports remain FROZEN.',
    'Apply V003/V004 to the new database before Spring; wait for primary Spring synthetic seed before short Spring.',
    'Prepare only authored synthetic seed in new stores; discover new IDs and issue trial-bound suite receipts/plans.',
    'Hardening needs a newly indexed catalog preparation phase, then consumers stopped for the browser phase.',
    'Wire actual per-operation execution to this policy plus fresh metadata; config approval is not start approval.',
]


def require(condition, message):
    if not condition:
        raise PolicyError(message)


def lexical_path(path):
    """Reject symlinks, including ancestors, without reading target contents."""
    p = Path(path).absolute()
    require('..' not in p.parts, 'Parent traversal is forbidden')
    for item in (p, *p.parents):
        require(not item.is_symlink(), 'Symlink paths are forbidden')
        require(not item.is_file() or item.stat().st_nlink == 1, 'Hard-linked trial inputs are forbidden')
    return p


def validate_manifest(manifest, repo, config_path):
    require(isinstance(manifest, dict), 'Explicit manifest object required')
    require(config_path is not None and Path(config_path).is_absolute(), 'Explicit absolute config path required')
    repo = lexical_path(repo)
    config = lexical_path(config_path)
    require(config.is_absolute() and config == repo / 'scripts/local/isolated-trial.json',
            'An explicit reviewed trial manifest is required; no env fallback')
    require(set(manifest) == {'schema', 'id', 'project', 'root', 'credentials', 'origins'},
            'Missing or unknown manifest settings')
    require(manifest['schema'] == 1, 'Unknown manifest schema')
    trial_id = manifest['id']
    require(isinstance(trial_id, str) and re.fullmatch(r'evidence-portability-\d{8}', trial_id), 'Unknown trial id')
    require(manifest['project'] == 'dodream-evidence-' + trial_id[-8:], 'Unknown trial project')
    require(manifest['root'] == '.local/isolated/' + trial_id, 'Existing or unknown trial root')
    require(manifest['credentials'] == 'credentials.env', 'Existing or missing credentials setting')
    root = lexical_path(repo / manifest['root'])
    for suffix in ('credentials.env', 'compose.json', 'nginx.auth-test.conf', 'results', 'fixtures', 'browser-ui'):
        lexical_path(root / suffix)
    require(isinstance(manifest['origins'], dict) and set(manifest['origins']) == {'main', 'short'}, 'Both explicit origins are required')
    ports = []
    for origin in manifest['origins'].values():
        require(isinstance(origin, str), 'Invalid origin')
        parsed = urlsplit(origin)
        try:
            port = parsed.port
        except ValueError as error:
            raise PolicyError('Invalid loopback port') from error
        require(parsed.scheme == 'http' and parsed.hostname == '127.0.0.1' and port is not None
                and 20000 <= port <= 60000 and origin == f'http://127.0.0.1:{port}',
                'Only explicit new loopback origins are allowed')
        ports.append(port)
    require(len(set(ports)) == 2, 'Origins must use different ports')
    return root


def load_manifest(config_path, repo):
    require(config_path is not None and Path(config_path).is_absolute(), 'Explicit absolute --manifest required')
    config = lexical_path(config_path)
    require(config == Path(repo).absolute() / 'scripts/local/isolated-trial.json', 'Unreviewed config path')
    # Never reads credentials or imports a launcher with import-time side effects.
    with config.open() as stream:
        manifest = json.load(stream)
    validate_manifest(manifest, repo, config)
    return manifest


def required_services(suite, phase):
    require(suite in SUITES, 'Unknown suite')
    require(phase in ('data', 'browser'), 'Unknown phase')
    services = SUITES[suite]
    return list(services if phase == 'browser' else tuple(s for s in services if s in ('mysql', 'redis', 'chroma')))


def credential(name):
    return '${ISOLATED_' + name + ':?fresh trial credentials required}'


def candidate_compose(manifest, repo, suite, phase='browser'):
    """Render a minimal service subset using existing images/Dockerfiles and fixed local contracts."""
    require(suite in SUITES, 'Unknown suite')
    project = manifest['project']
    root = Path(repo) / manifest['root']
    database = project.replace('-', '_')
    be_env = {
        'SPRING_PROFILES_ACTIVE': 'local', 'MYSQL_HOST': 'mysql', 'MYSQL_PORT': '3306',
        'MYSQL_DATABASE': database, 'MYSQL_USER': 'synthetic_trial', 'MYSQL_PASSWORD': credential('MYSQL_PASSWORD'),
        'REDIS_HOST': 'redis', 'REDIS_PORT': '6379', 'JWT_SECRET': credential('JWT_SECRET_BASE64'),
        'JWT_ISSUER': 'dodream', 'JWT_AUDIENCE': 'dodream-api', 'JWT_CLOCK_SKEW_SECONDS': '5',
        'AI_BASE_URL': 'http://ai:8000', 'LOCAL_TEACHER_PASSWORD': credential('TEACHER_PASSWORD'),
        'LOCAL_STUDENT_SECRET': credential('STUDENT_SECRET'), 'LOCAL_DATA_DIR': '/app/local-data',
        'LOCAL_DEMO_ENABLED': 'true' if suite in ('student', 'hardening') else 'false',
        'LOCAL_PHASE5_ENABLED': 'false', 'LOCAL_DEMO_MAX_VISITORS': '100',
    }
    ai_env = {
        'APP_ENV': 'local', 'LOCAL_EXTERNAL_STUBS': 'true', 'DODREAM_AI_MODE': 'LOCAL_FAKE',
        'LIVE_API_AUTHORIZED': 'false',
        'DATABASE_URL': 'mysql+pymysql://synthetic_trial:' + credential('MYSQL_PASSWORD') + '@mysql:3306/' + database,
        'JWT_SECRET_BASE64': credential('JWT_SECRET_BASE64'), 'JWT_ISSUER': 'dodream',
        'JWT_AUDIENCE': 'dodream-api', 'JWT_CLOCK_SKEW_SECONDS': '5',
        'CELERY_BROKER_URL': 'redis://redis:6379/1', 'RAG_DATABASE_URL': 'sqlite:////app/db_data/rag.db',
        'LOCAL_PROVIDER_DATA_DIR': '/app/db_data/local_provider',
        'LOCAL_OBJECT_STORAGE_DIR': '/app/be-local-data/objects', 'CHROMA_HOST': 'chroma',
        'CHROMA_PORT': '8000', 'INDEXING_QUEUE': 'indexing-v3',
    }

    def mount(source, target, read_only=False):
        return dict(type='volume', source=source, target=target, read_only=read_only)

    def service(image, *, environment=None, volumes=(), depends=(), health=None, memory='512m'):
        result = {'image': image, 'networks': ['default'], 'cpus': 1.0, 'mem_limit': memory}
        if environment is not None:
            result['environment'] = environment
        if volumes:
            result['volumes'] = list(volumes)
        if depends:
            result['depends_on'] = {s: {'condition': 'service_healthy'} for s in depends}
        if health:
            result['healthcheck'] = {'test': health, 'interval': '5s', 'timeout': '5s', 'start_period': '30s', 'retries': 20}
        return result

    ai_mounts = [mount('ai-data', '/app/db_data'), mount('be-data', '/app/be-local-data', True)]
    be_health = ['CMD-SHELL', 'curl -fsS http://127.0.0.1:8080/actuator/health >/dev/null']
    ai_health = ['CMD', 'python', '-c', 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=3)']
    services = {
        'mysql': service('mysql:8.4', environment={'MYSQL_DATABASE': database, 'MYSQL_USER': 'synthetic_trial',
            'MYSQL_PASSWORD': credential('MYSQL_PASSWORD'), 'MYSQL_ROOT_PASSWORD': credential('MYSQL_ROOT_PASSWORD')},
            volumes=[mount('mysql-data', '/var/lib/mysql')], memory='768m',
            health=['CMD-SHELL', 'MYSQL_PWD="$$MYSQL_PASSWORD" mysql -h127.0.0.1 -u"$$MYSQL_USER" "$$MYSQL_DATABASE" -e "SELECT 1" >/dev/null']),
        'redis': service('redis:7.4-alpine', volumes=[mount('redis-data', '/data')], health=['CMD', 'redis-cli', 'ping']),
        'be': service(project + '-be:reviewed', environment=be_env, volumes=[mount('be-data', '/app/local-data')],
            depends=['mysql', 'redis'], health=be_health, memory='1024m'),
        'ai': service(project + '-ai:reviewed', environment=ai_env, volumes=ai_mounts, depends=['be', 'redis'], health=ai_health, memory='1536m'),
        'python-service': service(project + '-python-service:reviewed', environment={'APP_ENV': 'local',
            'LOCAL_EXTERNAL_STUBS': 'true', 'ENVIRONMENT': 'local', 'DEBUG': 'false'}, health=ai_health, memory='768m'),
        'chroma': service(project + '-chroma:reviewed', environment={'IS_PERSISTENT': 'true',
            'PERSIST_DIRECTORY': '/chroma/chroma', 'ANONYMIZED_TELEMETRY': 'false', 'ALLOW_RESET': 'false',
            'CHROMA_SEGMENT_CACHE_POLICY': 'LRU', 'CHROMA_MEMORY_LIMIT_BYTES': '8388608'},
            volumes=[mount('chroma-data', '/chroma/chroma')], memory='768m',
            health=['CMD', 'python', '-c', 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8000/api/v1/heartbeat", timeout=3)']),
        'worker': service(project + '-ai:reviewed', environment=ai_env, volumes=ai_mounts, depends=['ai'], memory='1024m'),
        'index-dispatcher': service(project + '-ai:reviewed', environment=ai_env, volumes=ai_mounts, depends=['ai', 'redis', 'chroma'], memory='256m'),
        'be-auth-short': service(project + '-be:reviewed', environment={**be_env, 'JWT_ACCESS_EXP_SECONDS': '2',
            'LOCAL_DEMO_ENABLED': 'true' if suite == 'student' else 'false'},
            volumes=[mount('be-data', '/app/local-data')], depends=['mysql', 'redis', 'be'], health=be_health, memory='1024m'),
        'web': service(project + '-web:reviewed', depends=['be', 'ai', 'python-service'], memory='128m'),
        'web-auth-test': service(project + '-web:reviewed', depends=['be-auth-short', 'ai'], memory='128m'),
    }
    services['redis']['command'] = ['redis-server', '--appendonly', 'yes', '--appendfsync', 'everysec']
    services['worker']['command'] = ['celery', '-A', 'app.celery_config.celery_app', 'worker', '--loglevel=warning',
        '--concurrency=1', '--pool=solo', '--queues=indexing-v3', '--hostname=indexing-trial@%h']
    services['index-dispatcher']['command'] = ['python', '-m', 'app.indexing.dispatcher']
    for web, origin in [('web', 'main'), ('web-auth-test', 'short')]:
        services[web]['networks'] = ['default', 'gateway']
        services[web]['ports'] = [f'127.0.0.1:{urlsplit(manifest["origins"][origin]).port}:80']
    # This sole bind is a future copy of a reviewed, non-secret nginx source, inside the new trial root.
    services['web-auth-test']['volumes'] = [{'type': 'bind', 'source': str(root / 'nginx.auth-test.conf'),
        'target': '/etc/nginx/conf.d/default.conf', 'read_only': True, 'bind': {'create_host_path': False}}]
    chosen = required_services(suite, phase)
    selected = {key: copy.deepcopy(services[key]) for key in chosen}
    volumes = {item['source']: {} for val in selected.values() for item in val.get('volumes', []) if item['type'] == 'volume'}
    networks = {'default': {'internal': True}}
    if any('gateway' in val['networks'] for val in selected.values()):
        networks['gateway'] = {}
    return {'name': project, 'services': selected, 'networks': networks, 'volumes': volumes}


def validate_compose(compose, manifest, repo, suite, phase):
    expected = candidate_compose(manifest, repo, suite, phase)
    require(set(compose) == set(expected), 'Unknown Compose sections')
    for value in compose.get('volumes', {}).values():
        require(value == {}, 'Named/external/existing volume override forbidden')
    require(compose == expected,
            'Unreviewed service/endpoint/mount/network/image configuration; exact trial configuration required')


def command_for(manifest, repo, suite, phase, operation, services):
    require(operation in ('config', 'up'), 'Only config or up can be planned; direct start/restart is forbidden')
    expected = required_services(suite, phase)
    require(services is not None and list(services) == expected,
            'Explicit exact suite/phase services required; no implicit/background/unknown targets')
    root = Path(repo) / manifest['root']
    prefix = ['docker', 'compose', '--project-directory', str(root), '--env-file', str(root / manifest['credentials']),
              '-p', manifest['project'], '-f', str(root / 'compose.json')]
    if operation == 'config':
        return prefix + ['config', '--format', 'json']
    return prefix + ['up', '-d', '--no-deps', '--wait', '--wait-timeout', '180'] + expected


def validate_invocation(manifest, repo, config_path, suite, phase, operation, services, argv, compose, environment=None):
    validate_manifest(manifest, repo, config_path)
    require(isinstance(argv, list) and all(isinstance(x, str) for x in argv), 'argv must be a literal argument list')
    require(argv[:2] != ['docker', 'start'], 'Direct container-ID start is forbidden; config grants no start permission')
    require(environment is None or environment == {},
            'Inherited process environment is forbidden; future runner must use a reviewed hermetic environment')
    require(argv == command_for(manifest, repo, suite, phase, operation, services),
            'Actual command differs from approved operation, project, config, root or services')
    validate_compose(compose, manifest, repo, suite, phase)
    return {'status': 'PASS', 'scope': 'OFFLINE_PLAN_ONLY', 'operation': operation, 'services': list(services),
            'executionAuthorized': False, 'resourceFreshness': 'NOT_CHECKED', 'integration': 'NOT_RUN'}


def validate_fresh_inventory(plan, metadata):
    """Check supplied non-secret metadata; does not query Docker or grant execution."""
    require(isinstance(metadata, dict) and set(metadata) == {'containers', 'volumes', 'networks'}, 'Complete metadata required')
    require(all(isinstance(metadata[k], list) for k in metadata), 'Invalid metadata lists')
    project = plan['project']
    volumes, networks = set(plan['effectiveVolumes'].values()), set(plan['effectiveNetworks'].values())
    require(all(isinstance(x, str) for x in metadata['volumes'] + metadata['networks']), 'Only metadata names accepted')
    require(not volumes.intersection(metadata['volumes']), 'Trial volume already exists; never adopt it')
    require(not networks.intersection(metadata['networks']), 'Trial network already exists; never adopt it')
    for row in metadata['containers']:
        require(isinstance(row, dict) and set(row) == {'id', 'name', 'project', 'volumes', 'networks'}, 'Only bounded container metadata accepted')
        require(all(isinstance(row[k], str) for k in ('id', 'name', 'project')) and
                all(isinstance(row[k], list) and all(isinstance(x, str) for x in row[k]) for k in ('volumes', 'networks')),
                'Invalid container metadata')
        require(row['project'] != project and not row['name'].startswith(project + '-'), 'Trial container already exists; no reuse')
        require(not volumes.intersection(row['volumes']) and not networks.intersection(row['networks']), 'Existing container references trial storage/network')
    return {'status': 'PASS', 'scope': 'SUPPLIED_METADATA_ONLY', 'executionAuthorized': False}


def execute_invocation(*args, executor=None, **kwargs):
    """Intentionally unavailable in this preparatory release, even after a plan PASS."""
    raise ExecutionDisabled('Actual execution is disabled; config/plan PASS cannot authorize start')


def build_plan(manifest, repo, config_path, suite, phase, operation, services):
    root = validate_manifest(manifest, repo, config_path)
    compose = candidate_compose(manifest, repo, suite, phase)
    argv = command_for(manifest, repo, suite, phase, operation, services)
    validation = validate_invocation(manifest, repo, config_path, suite, phase, operation, services, argv, compose)
    origin = manifest['origins']['short' if suite in ('auth', 'demo-disabled') else 'main']
    source_paths = ['compose.local.yml', 'scripts/local/nginx.auth-test.conf', 'fe-web/nginx.local.conf',
                    'be/Dockerfile.local', 'ai/Dockerfile.local', 'fe-web/Dockerfile.local',
                    'python-service/Dockerfile.local', 'scripts/local/chroma/Dockerfile.local']
    controls = {p: hashlib.sha256((Path(repo) / p).read_bytes()).hexdigest() for p in source_paths}
    return {'trialId': manifest['id'], 'project': manifest['project'], 'suite': suite, 'phase': phase,
            'manifest': str(config_path), 'root': str(root), 'origin': origin, 'shortOrigin': manifest['origins']['short'],
            'status': 'PREPARED_OFFLINE_ONLY', 'validation': validation, 'argv': argv, 'compose': compose,
            'effectiveVolumes': {v: manifest['project'] + '_' + v for v in compose['volumes']},
            'effectiveNetworks': {v: manifest['project'] + '_' + v for v in compose['networks']},
            'browserEnvironment': {'DODREAM_ISOLATED_MANIFEST': str(config_path)},
            'processEnvironment': 'Empty environment required by policy; no ambient COMPOSE/DOCKER/credential overrides.',
            'paths': {k: str(root / v) for k, v in {'credentials': manifest['credentials'], 'results': 'results',
                      'fixtures': 'fixtures', 'plans': 'browser-ui', 'compose': 'compose.json'}.items()},
            'fixtures': 'Authored synthetic seed only; obtain IDs from new stores, never old plans or rows.',
            'credentials': 'NOT_GENERATED; ISOLATED_* interpolation names only, never valid credentials. Future file also binds DODREAM_TRIAL_ID and DODREAM_TRIAL_RUN_ID to fresh suite receipts.',
            'queue': {'name': 'indexing-v3', 'isolation': 'New MySQL outbox + Redis volume/network; queue name alone is insufficient.'},
            'sourceControlHashes': controls, 'images': 'NOT_VERIFIED: reviewed tags are planned targets, not proof of image contents.',
            'prestartConditions': PRESTART, 'newEnvironmentStarted': False}


RUN_LABEL = 'io.dodream.trial.run-id'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def exclusive_json(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')


def execution_compose(manifest, repo, run_id, image_ids):
    """Fixed definitions: no recreation/configuration swap when suites change."""
    result = candidate_compose(manifest, repo, 'student')
    services = result['services']
    # Student's 2-second demo endpoint is a separately created service. Both
    # short web containers use 25174 sequentially, never simultaneously.
    student_be = services.pop('be-auth-short')
    student_web = services.pop('web-auth-test')
    student_web['depends_on'] = {'be-student-short': {'condition': 'service_healthy'}, 'ai': {'condition': 'service_healthy'}}
    student_web['volumes'][0]['source'] = str(Path(repo) / manifest['root'] / 'nginx.student-short.conf')
    services['be-student-short'] = student_be
    services['web-student-short'] = student_web
    auth = candidate_compose(manifest, repo, 'auth')['services']
    services['be-auth-short'] = auth['be-auth-short']
    services['web-auth-test'] = auth['web-auth-test']
    for name, service in services.items():
        component = ('be' if name.startswith('be-') else 'web' if name.startswith('web-') else
                     'ai' if name in CONSUMERS else name)
        require(component in image_ids and re.fullmatch(r'sha256:[a-f0-9]{64}', image_ids[component]), 'Verified immutable image required')
        service['image'] = image_ids[component]
        service['labels'] = {RUN_LABEL: run_id}
    for spec in result['volumes'].values():
        spec.update({'driver': 'local', 'labels': {RUN_LABEL: run_id}})
    for spec in result['networks'].values():
        spec.update({'driver': 'bridge', 'labels': {RUN_LABEL: run_id}})
    return result


class TrialRuntime:
    """The only real executor. Every container mutation revalidates provenance."""
    def __init__(self, repo, manifest_path, *, preparing=False, attempt=None):
        self.repo = Path(repo).absolute()
        self.manifest_path = Path(manifest_path).absolute()
        self.manifest = load_manifest(str(self.manifest_path), self.repo)
        self.root = validate_manifest(self.manifest, self.repo, self.manifest_path)
        self.project = self.manifest['project']
        self.origins = self.manifest['origins']
        self.attempt_id = attempt if attempt is not None else os.environ.get('DODREAM_ISOLATED_ATTEMPT')
        require(self.attempt_id is None or (isinstance(self.attempt_id, str) and
                re.fullmatch(r'[a-z][a-z0-9-]{0,47}', self.attempt_id)), 'Explicit safe attempt identifier required')
        self.attempt_root = lexical_path(self.root / 'attempts' / self.attempt_id) if self.attempt_id else self.root
        self.results = self.attempt_root / 'results'
        self.fixtures = self.attempt_root / 'fixtures'
        self.plans = self.attempt_root / 'browser-ui'
        self.credentials_path = self.root / self.manifest['credentials']
        self.docker = shutil.which('docker')
        require(self.docker is not None, 'Docker CLI unavailable')
        self.preparation = None
        if not preparing:
            self.preparation = json.loads(lexical_path(self.root / 'preparation.json').read_text())
            require(self.preparation['manifestDigest'] == digest(self.manifest), 'Manifest changed after preparation')
            self.run_id = self.preparation['runId']
            self.host = self.preparation['dockerHost']
            require(self.host.startswith('unix:///') and not any(x in self.host for x in ('\n', '..')), 'Local Docker endpoint required')
            require(hashlib.sha256(lexical_path(self.credentials_path).read_bytes()).hexdigest() ==
                    self.preparation['credentialHash'], 'New credential receipt mismatch')

    def clean_env(self):
        # No ambient API keys, proxies, Docker credentials, Compose overrides or browser profile.
        result = {'PATH': '/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin',
                'HOME': str(self.root / 'home'), 'TMPDIR': str(self.root / 'tmp'),
                'COMPOSE_DISABLE_ENV_FILE': 'true', 'DODREAM_ISOLATED_MANIFEST': str(self.manifest_path),
                'PYTHONDONTWRITEBYTECODE': '1', 'LANG': 'en_US.UTF-8'}
        if getattr(self, 'attempt_id', None): result['DODREAM_ISOLATED_ATTEMPT'] = self.attempt_id
        return result

    def _prefix(self):
        return [self.docker, '--host', self.host, '--config', str(self.root / 'docker-client')]

    def configure_client(self):
        # The fresh HOME deliberately excludes the user's Docker configuration.
        # Load only Docker Desktop's installed plugin directory, never copy that config.
        directory=Path('/Applications/Docker.app/Contents/Resources/cli-plugins')
        require((directory/'docker-compose').is_file(),'Reviewed Docker Desktop Compose plugin unavailable')
        path=lexical_path(self.root/'docker-client/config.json')
        previous=json.loads(path.read_text())
        wanted={'auths':{},'cliPluginsExtraDirs':[str(directory)]}
        require(previous in ({'auths':{}},wanted),'Unexpected isolated Docker client configuration')
        if previous!=wanted:
            exclusive_json(self.results/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')+'-docker-client-config.json'),
                           {'beforeDigest':digest(previous),'afterDigest':digest(wanted),'pluginDirectory':str(directory),'ambientConfigCopied':False})
            path.write_text(json.dumps(wanted)+'\n')

    def _raw(self, args, *, stdin=None, timeout=60):
        return subprocess.run([*self._prefix(), *args], input=stdin, capture_output=True,
                              text=True, env=self.clean_env(), cwd=self.repo, timeout=timeout)

    def _json(self, args):
        result = self._raw(args)
        require(result.returncode == 0, 'Docker metadata read failed: ' + ' '.join(args[:2]))
        return json.loads(result.stdout)

    def _credentials(self):
        data=lexical_path(self.credentials_path).read_bytes()
        require(hashlib.sha256(data).hexdigest()==self.preparation['credentialHash'],'New credential receipt mismatch')
        values = dict(line.split('=', 1) for line in data.decode().splitlines() if line)
        require(set(values)=={'DODREAM_TRIAL_ID','DODREAM_TRIAL_RUN_ID','ISOLATED_MYSQL_PASSWORD','ISOLATED_MYSQL_ROOT_PASSWORD',
                              'ISOLATED_JWT_SECRET_BASE64','ISOLATED_TEACHER_PASSWORD','ISOLATED_STUDENT_SECRET'},'Unknown trial credential keys')
        require(values.get('DODREAM_TRIAL_ID') == self.manifest['id'] and
                values.get('DODREAM_TRIAL_RUN_ID') == self.run_id, 'Credential ownership mismatch')
        return values

    def settings(self):
        values = self._credentials()
        return {'MYSQL_DATABASE': self.project.replace('-', '_'), 'MYSQL_USER': 'synthetic_trial',
                'MYSQL_PASSWORD': values['ISOLATED_MYSQL_PASSWORD'], 'MYSQL_ROOT_PASSWORD': values['ISOLATED_MYSQL_ROOT_PASSWORD'],
                'JWT_SECRET_BASE64': values['ISOLATED_JWT_SECRET_BASE64'],
                'LOCAL_TEACHER_PASSWORD': values['ISOLATED_TEACHER_PASSWORD'], 'LOCAL_STUDENT_SECRET': values['ISOLATED_STUDENT_SECRET'],
                'WEB_PORT': str(urlsplit(self.origins['main']).port)}

    def redact(self, text):
        if self.credentials_path.exists() and self.preparation:
            for key, value in self._credentials().items():
                if key.startswith('ISOLATED_'):
                    text = text.replace(value, '[REDACTED]')
        text = re.sub(r'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', '[JWT REDACTED]', text)
        return re.sub(r'(Using generated security password:)\s*\S+', r'\1 [REDACTED]', text)

    def record(self, name, args, result, started):
        require(re.fullmatch(r'[a-zA-Z0-9_.-]+', name), 'Invalid evidence name')
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
        row = {'name': name, 'argv': self.redact(json.dumps(args)), 'exitCode': result.returncode,
               'startedAt': started, 'finishedAt': now(), 'runId': self.run_id}
        exclusive_json(self.results / f'{stamp}-{name}.json', row)
        with (self.results / f'{stamp}-{name}.log').open('x') as stream:
            stream.write(self.redact((result.stdout or '') + (getattr(result, 'stderr', '') or '')))
        return row

    def inventory(self):
        fmt = '{{.ID}}\t{{.Names}}\t{{.State}}\t{{.Label "com.docker.compose.project"}}'
        result = self._raw(['ps', '-a', '--no-trunc', '--format', fmt])
        require(result.returncode == 0, 'Container inventory unavailable')
        rows = [dict(zip(('id', 'name', 'state', 'project'), line.split('\t'))) for line in result.stdout.splitlines()]
        volumes = self._raw(['volume', 'ls', '--format', '{{.Name}}'])
        networks = self._raw(['network', 'ls', '--format', '{{.Name}}'])
        require(volumes.returncode == networks.returncode == 0, 'Storage inventory unavailable')
        old_ids = [r['id'] for r in rows if r['project'] == 'dodream-phase1']
        old = []
        if old_ids:
            fmt = '{{json .Id}}\t{{json .State.Status}}\t{{json .State.StartedAt}}\t{{json .State.FinishedAt}}'
            res = self._raw(['inspect', '--format', fmt, *old_ids])
            require(res.returncode == 0, 'Frozen container state unavailable')
            old = [dict(zip(('id', 'state', 'startedAt', 'finishedAt'), map(json.loads, row.split('\t')))) for row in res.stdout.splitlines()]
        return {'containers': [r['id'] for r in rows], 'volumes': volumes.stdout.splitlines(),
                'networks': networks.stdout.splitlines(), 'rows': rows, 'frozen': sorted(old, key=lambda x:x['id'])}

    def prepare(self):
        require(not self.root.exists(), 'Trial root already exists; refuse adoption or overwrite')
        env = {'PATH': '/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin'}
        context = subprocess.run([self.docker, 'context', 'inspect', '--format', '{{json .Endpoints.docker.Host}}'],
                                 capture_output=True, text=True, env=env, timeout=15)
        require(context.returncode == 0, 'Docker context unavailable')
        self.host = json.loads(context.stdout)
        require(self.host.startswith('unix:///') and '..' not in self.host, 'Only local Docker is allowed')
        # Nonexistent --config path is okay for metadata; no ambient credential config is used.
        before = self.inventory()
        require(all(r['state'] == 'exited' for r in before['frozen']), 'Historical environment is not frozen')
        require(not any(r['project'] == self.project or r['name'].startswith(self.project + '-') for r in before['rows']), 'Unreceipted trial container already exists')
        require(not any(n.startswith(self.project + '_') for n in before['volumes'] + before['networks']), 'Unreceipted trial storage/network exists')
        capacity=self._raw(['info','--format','{{json .NCPU}}\t{{json .MemTotal}}'])
        require(capacity.returncode==0,'Docker resource capacity unavailable')
        cpus,memory=map(json.loads,capacity.stdout.strip().split('\t'))
        require(cpus>=4 and memory>=9*1024**3, 'Insufficient trial capacity; do not free existing resources')
        require(not any(r['state']=='running' for r in before['rows']), 'Concurrent resource usage requires separate capacity review')
        for origin in self.origins.values():
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', urlsplit(origin).port))
        self.run_id = str(uuid.uuid4())
        self.root.mkdir(mode=0o700,parents=True, exist_ok=False)
        for directory in ('results', 'fixtures', 'browser-ui', 'home', 'tmp', 'docker-client'):
            (self.root / directory).mkdir()
        exclusive_json(self.root / 'docker-client/config.json', {'auths': {}})
        values = {'DODREAM_TRIAL_ID': self.manifest['id'], 'DODREAM_TRIAL_RUN_ID': self.run_id,
                  'ISOLATED_MYSQL_PASSWORD': secrets.token_hex(24), 'ISOLATED_MYSQL_ROOT_PASSWORD': secrets.token_hex(24),
                  'ISOLATED_JWT_SECRET_BASE64': base64.b64encode(secrets.token_bytes(48)).decode(),
                  'ISOLATED_TEACHER_PASSWORD': secrets.token_hex(24), 'ISOLATED_STUDENT_SECRET': secrets.token_hex(24)}
        fd = os.open(self.credentials_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write(''.join(f'{k}={v}\n' for k,v in values.items()))
        source = (self.repo / 'scripts/local/nginx.auth-test.conf').read_text()
        for name, content in [('nginx.auth-test.conf', source), ('nginx.student-short.conf', source.replace('be-auth-short', 'be-student-short'))]:
            with (self.root / name).open('x') as stream: stream.write(content)
        self.preparation = {'runId': self.run_id, 'project': self.project, 'createdAt': now(),
            'manifestDigest': digest(self.manifest), 'dockerHost': self.host, 'before': before,
            'capacity':{'cpus':cpus,'memoryBytes':memory,'preexistingRunning':0},
            'credentialHash': hashlib.sha256(self.credentials_path.read_bytes()).hexdigest(),
            'configHashes': {name: hashlib.sha256((self.root/name).read_bytes()).hexdigest() for name in ('nginx.auth-test.conf','nginx.student-short.conf')}}
        exclusive_json(self.root / 'preparation.json', self.preparation)
        return {'runId': self.run_id, 'status': 'PREPARED', 'credentials': 'NEW_0600_NOT_PRINTED', 'containersCreated': False}

    def build_images(self):
        from isolated_images import materialize_context
        self.configure_client()
        require(not (self.root / 'images.json').exists(), 'Image receipt exists; no rebuild/adoption')
        files = [p for p in subprocess.check_output(['git', 'ls-files', '-z'], cwd=self.repo).decode().split('\0') if p]
        records = {}
        for component in ('be', 'ai', 'python-service', 'web', 'chroma'):
            context = materialize_context(self.repo, self.root, component, files)
            tag = f'{self.project}-{component}:run-{self.run_id[:8]}'
            require(self._raw(['image', 'inspect', tag]).returncode != 0, 'Build tag exists; refuse overwrite')
            argv = ['build', '--network', 'default', '--pull=false', '-f', str(self.root/'contexts'/component/'Dockerfile.local'),
                    '--label', RUN_LABEL+'='+self.run_id,
                    *[item for key,value in context['labels'].items() for item in ('--label',key+'='+value)],
                    '-t', tag, str(self.root/'contexts'/component)]
            start = now()
            result = self._raw(argv, timeout=1200)
            self.record('build-'+component, [*self._prefix(), *argv], result, start)
            require(result.returncode == 0, 'Sanitized image build failed: '+component)
            image = self._json(['image', 'inspect', tag])[0]
            require(all(image['Config'].get('Labels', {}).get(k) == v for k,v in context['labels'].items()), 'Image source label mismatch')
            records[component] = {'id': image['Id'], 'tag': tag, 'source': context,
                'command': image['Config'].get('Cmd') or [], 'entrypoint': image['Config'].get('Entrypoint') or [],
                'envHash': digest(image['Config'].get('Env') or []), 'volumes': image['Config'].get('Volumes') or {}}
            exclusive_json(self.root / f'image-{component}.json', records[component])
            print(json.dumps({'image': component, 'status': 'BUILT', 'id': image['Id']}), flush=True)
        for component, tag in (('mysql','mysql:8.4'),('redis','redis:7.4-alpine')):
            image = self._json(['image','inspect',tag])[0]
            require(any(x.startswith(component+'@sha256:') for x in image.get('RepoDigests', [])), 'Stock image digest unavailable')
            records[component] = {'id': image['Id'], 'tag': tag, 'repoDigests':image['RepoDigests'],
                'command': image['Config'].get('Cmd') or [], 'entrypoint': image['Config'].get('Entrypoint') or [],
                'envHash': digest(image['Config'].get('Env') or []), 'volumes': image['Config'].get('Volumes') or {}}
        exclusive_json(self.root / 'images.json', records)
        return {'status':'IMAGES_VERIFIED','images':{k:v['id'] for k,v in records.items()},'secretReview':'ALLOWLISTED_BUILD_INPUTS_ONLY'}

    def _revision_records(self):
        directory = lexical_path(self.root / 'revisions')
        records = []
        if directory.exists():
            for path in sorted(directory.iterdir()):
                require(path.is_dir() and re.fullmatch(r'\d{3}-(?:observation|fixed)-\d{2}', path.name), 'Unknown revision entry')
                lexical_path(path)
                receipt = path / 'revision.json'
                if receipt.exists():
                    records.append((path, json.loads(lexical_path(receipt).read_text())))
                else:
                    require(not (path / 'recreate-intent.json').exists(), 'Incomplete BE recreation; no adoption or start')
        return records

    def _image_records(self, *, original=False):
        images = json.loads(lexical_path(self.root / 'images.json').read_text())
        if not original:
            for directory, _ in self._revision_records():
                images = json.loads(lexical_path(directory / 'images.json').read_text())
        return images

    def _resolved_config(self, *, original=False):
        images = self._image_records(original=original)
        raw = execution_compose(self.manifest, self.repo, self.run_id, {k:v['id'] for k,v in images.items()})
        values = self._credentials()
        def resolve(value):
            if isinstance(value, str):
                return re.sub(r'\$\{(ISOLATED_[A-Z0-9_]+):\?fresh trial credentials required\}', lambda m:values[m[1]], value)
            if isinstance(value, dict):return {k:resolve(v) for k,v in value.items()}
            if isinstance(value, list):return [resolve(v) for v in value]
            return value
        return raw, resolve(raw), images

    def verify_image_sources(self, images):
        from isolated_images import (validate_materialized_context,validate_repo_source,
                                     validate_image_config,image_config_view,select_context,source_digest)
        files=[p for p in subprocess.check_output(['git','ls-files','-z'],cwd=self.repo).decode().split('\0') if p]
        inherited={
            'web':(['nginx','-g','daemon off;'],['/docker-entrypoint.sh'],
                   {'PATH','NGINX_VERSION','PKG_RELEASE','DYNPKG_RELEASE','NJS_VERSION','NJS_RELEASE'},{}),
            'chroma':(['--workers ${CHROMA_WORKERS} --host ${CHROMA_HOST_ADDR} --port ${CHROMA_HOST_PORT} --proxy-headers --log-config ${CHROMA_LOG_CONFIG} --timeout-keep-alive ${CHROMA_TIMEOUT_KEEP_ALIVE}'],
                      ['/docker_entrypoint.sh'],{'PATH','LANG','GPG_KEY','PYTHON_VERSION','PYTHON_SHA256','CHROMA_HOST_ADDR',
                      'CHROMA_HOST_PORT','CHROMA_WORKERS','CHROMA_LOG_CONFIG','CHROMA_TIMEOUT_KEEP_ALIVE'},{}),
            'mysql':(['mysqld'],['docker-entrypoint.sh'],{'PATH','GOSU_VERSION','MYSQL_MAJOR','MYSQL_VERSION','MYSQL_SHELL_VERSION'},{'/var/lib/mysql':{}}),
            'redis':(['redis-server'],['docker-entrypoint.sh'],{'PATH','REDIS_VERSION'},{'/data':{}}),
        }
        proof={}
        for component,record in images.items():
            if 'source' in record:
                source=record['source']
                validate_materialized_context(source);validate_repo_source(self.repo,source)
                additions=source.get('explicitAdditionalSources',[])
                require(component=='be' or not additions,'Explicit additional source scope is BE only')
                require(all(isinstance(path,str) and re.fullmatch(r'be/src/(?:main|test)/java/[A-Za-z0-9_/]+\.java',path)
                            and '..' not in path for path in additions),'Unknown explicit source addition')
                require(source_digest(select_context(self.repo,component,sorted(set(files)|set(additions))))==source['sourceDigest'], 'Source path set drift')
            config=self._json(['image','inspect',record['id']])[0]['Config']
            if component in ('be','ai','python-service'):
                proof[component]=validate_image_config(component,config)
            else:
                view=image_config_view(config);cmd,entry,keys,volumes=inherited[component]
                require(view['Cmd']==cmd and view['Entrypoint']==entry and set(view['Env'])==keys and view['Volumes']==volumes,
                        'Inherited image command/environment/volume review mismatch')
                if component=='chroma':
                    require(view['Env']['CHROMA_HOST_ADDR']=='0.0.0.0' and view['Env']['CHROMA_HOST_PORT']=='8000', 'Unknown Chroma listener')
                proof[component]={'status':'PASS','imageId':record['id'],'scope':'Reviewed inherited command/environment keys/volumes; not full layer history'}
        return proof

    def source_identity(self):
        images=self._image_records()
        return {'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=self.repo,text=True).strip(),
                'working_source_sha256':digest({k:v.get('source',{}).get('sourceDigest',v['id']) for k,v in images.items()}),
                'scope':'Image build inputs and immutable stock image IDs; test source hashes recorded separately'}

    def _expected(self, resolved, images):
        services = {}
        for name,spec in resolved['services'].items():
            image = self._json(['image','inspect',spec['image']])[0]['Config']
            recorded = next(v for v in images.values() if v['id'] == spec['image'])
            require(recorded['command'] == (image.get('Cmd') or []) and
                    recorded['entrypoint'] == (image.get('Entrypoint') or []) and
                    recorded['envHash'] == digest(image.get('Env') or []) and
                    recorded['volumes'] == (image.get('Volumes') or {}), 'Image configuration receipt drift')
            defaults = dict(x.split('=',1) for x in image.get('Env') or [])
            defaults.update(spec.get('environment',{}))
            mounts=[]
            for m in spec.get('volumes',[]):
                item={'type':m['type'],'destination':m['target'],'rw':not m.get('read_only',False)}
                item['name' if m['type']=='volume' else 'source']=self.project+'_'+m['source'] if m['type']=='volume' else m['source']
                mounts.append(item)
            require(set((image.get('Volumes') or {})) <= {x['destination'] for x in mounts}, 'Unplanned anonymous image volume')
            ports={}
            for port in spec.get('ports',[]):
                host_ip,host_port,container_port=port.split(':')
                ports[container_port+'/tcp']=[{'HostIp':host_ip,'HostPort':host_port}]
            services[name]={'image':spec['image'],'command':spec.get('command',image.get('Cmd') or []),
                'entrypoint':image.get('Entrypoint') or [],'envHash':digest(sorted(defaults.items())),
                'mounts':mounts,'networkNames':[self.project+'_'+n for n in spec['networks']],'ports':ports}
        return {'project':self.project,'services':services,'volumes':[self.project+'_'+n for n in resolved['volumes']],
                'networks':{self.project+'_'+n:{'driver':'bridge','internal':s.get('internal',False)} for n,s in resolved['networks'].items()}}

    def observe(self, expected):
        result=self._raw(['ps','-a','--no-trunc','--filter','label=com.docker.compose.project='+self.project,'--format','{{.ID}}'])
        require(result.returncode==0,'New resource inventory unavailable')
        ids=result.stdout.splitlines(); rows=self._json(['inspect',*ids]) if ids else []
        containers={}
        for row in rows:
            labels=row['Config'].get('Labels') or {};service=labels.get('com.docker.compose.service')
            require(service not in containers,'Duplicate service containers')
            containers[service]={'id':row['Id'],'image':row['Image'],'created':row['Created'],
                'state':row['State']['Status'],'startedAt':row['State']['StartedAt'],
                'project':labels.get('com.docker.compose.project'),'service':service,'runId':labels.get(RUN_LABEL),
                'command':row['Config'].get('Cmd') or [],'entrypoint':row['Config'].get('Entrypoint') or [],
                'envHash':digest(sorted(dict(x.split('=',1) for x in row['Config'].get('Env') or []).items())),
                'mounts':[{**{'type':m['Type'],'source':m['Source'],'destination':m['Destination'],'rw':m['RW']},
                           **({'name':m['Name']} if m['Type']=='volume' else {})} for m in row['Mounts']],
                'networks':{n:v['NetworkID'] for n,v in row['NetworkSettings']['Networks'].items()},
                'ports':row['HostConfig'].get('PortBindings') or {}}
            require(row['HostConfig']['NetworkMode'] != 'host' and not row['HostConfig']['Privileged']
                    and not any(row['HostConfig'].get(key) for key in ('VolumesFrom','ExtraHosts','Devices','DeviceRequests','PidMode','CapAdd','Dns','DnsSearch','Links'))
                    and row['HostConfig'].get('IpcMode','private') in ('private',''), 'Unsafe runtime container config')
        volumes={}
        for row in self._json(['volume','inspect',*expected['volumes']]):
            name=row['Name']
            volumes[name]={'name':row['Name'],'driver':row['Driver'],'options':row.get('Options'), 'created':row.get('CreatedAt'),'labels':row.get('Labels') or {}}
        networks={}
        for row in self._json(['network','inspect',*expected['networks']]):
            name=row['Name']
            networks[name]={'id':row['Id'],'name':row['Name'],'driver':row['Driver'],'internal':row['Internal'],
                'options':row.get('Options'),'created':row['Created'],'labels':row.get('Labels') or {}}
        return {'containers':containers,'volumes':volumes,'networks':networks}

    def create(self):
        from isolated_provenance import validate_created, validate_effective_compose
        self.configure_client()
        require(not (self.root/'creation.json').exists() and not (self.root/'creation-intent.json').exists(), 'Creation already attempted; no automatic adoption')
        before=self.inventory()
        require(before==self.preparation['before'],'Preexisting metadata changed since preparation; re-review required')
        raw,resolved,images=self._resolved_config()
        image_review=self.verify_image_sources(images)
        expected=self._expected(resolved,images)
        compose_path=self.root/'compose.json'
        if compose_path.exists():
            require(json.loads(lexical_path(compose_path).read_text())==raw,'Previous uncreated Compose plan differs; preserve it for review')
        else: exclusive_json(compose_path,raw)
        # Resolve using the installed Compose, but never persist or print its secret-bearing output.
        base=['compose','--project-directory',str(self.root),'--env-file',str(self.credentials_path),'-p',self.project,'-f',str(compose_path)]
        config=self._raw([*base,'config','--format','json'])
        self.record('compose-config',base+['config','--format','json'],subprocess.CompletedProcess([],config.returncode,stdout='',stderr=config.stderr),now())
        require(config.returncode==0,'Actual Compose config validation failed')
        effective=json.loads(config.stdout)
        validate_effective_compose(resolved,effective)
        started=now();argv=[*base,'create','--no-build','--no-recreate','--pull','never',*raw['services']]
        intent={'runId':self.run_id,'manifestDigest':digest(self.manifest),'composeDigest':digest(raw),'expected':expected,'imageReview':image_review,
                'before':before,'argv':argv,'startedAt':started,'status':'INCOMPLETE'}
        exclusive_json(self.root/'creation-intent.json',intent)
        result=self._raw(argv,timeout=180);self.record('create',[*self._prefix(),*argv],result,started)
        require(result.returncode==0,'Creation incomplete; do not start any resources')
        finished=now();observed=self.observe(expected)
        exclusive_json(self.root/'creation-observed.json',observed)
        receipt=validate_created({k:before[k] for k in ('containers','volumes','networks')},observed,expected,self.run_id,started,finished)
        wrapped={'provenance':receipt,'manifestDigest':digest(self.manifest),'composeDigest':digest(raw),'sourceDigest':digest(images),
                 'creationCommand':argv,'creationExitCode':result.returncode,'beforeDigest':digest(before)}
        exclusive_json(self.root/'creation.json',wrapped)
        return {'status':'CREATED_VERIFIED','containers':{k:v['id'] for k,v in observed['containers'].items()},'started':False}

    def verify_created(self):
        """Complete read-only validation after a successful create's metadata-format failure.

        A failed/interrupted create, missing evidence, changed resources or any
        process start cannot be adopted. This method never creates or starts.
        """
        from isolated_provenance import validate_created,validate_current
        require(not (self.root/'creation.json').exists() and not self._start_rows(), 'Creation verification is not adoption or a start retry')
        intent=json.loads(lexical_path(self.root/'creation-intent.json').read_text())
        records=[json.loads(lexical_path(p).read_text()) for p in self.results.glob('*-create.json')]
        require(len(records)==1 and records[0]['exitCode']==0 and records[0]['runId']==self.run_id,
                'One completed successful create record required; interrupted creation cannot resume')
        record=records[0]
        require(json.loads(record['argv'])==[*self._prefix(),*intent['argv']] and record['startedAt']==intent['startedAt'],
                'Actual create command/window does not match creation intent')
        require(intent['runId']==self.run_id and intent['before']==self.preparation['before'],'Creation intent ownership mismatch')
        raw,resolved,images=self._resolved_config()
        require(intent['manifestDigest']==digest(self.manifest) and intent['composeDigest']==digest(raw)
                and json.loads(lexical_path(self.root/'compose.json').read_text())==raw,'Creation config changed')
        self.verify_image_sources(images)
        expected=self._expected(resolved,images)
        require(expected==intent['expected'],'Expected immutable configuration changed')
        current=self.inventory();before=intent['before']
        require(current['frozen']==before['frozen'],'Frozen metadata changed')
        for kind in ('volumes','networks'):
            require(set(current[kind])==set(before[kind])|set(expected[kind]),'Unattributed resource inventory change')
        observed=self.observe(expected)
        require(set(current['containers'])==set(before['containers'])|{v['id'] for v in observed['containers'].values()},'Unattributed container inventory change')
        original_path=self.root/'creation-observed.json'
        if not original_path.exists():original_path=self.root/'creation-observed-blocked.json'
        original=json.loads(lexical_path(original_path).read_text())
        receipt=validate_created({k:before[k] for k in ('containers','volumes','networks')},original,expected,
                                 self.run_id,intent['startedAt'],record['finishedAt'])
        validate_current(receipt,observed)
        require(all(row['state']=='created' and row['startedAt']==original['containers'][name]['startedAt']
                    for name,row in observed['containers'].items()),'Creation verification requires unchanged never-started state')
        wrapped={'provenance':receipt,'manifestDigest':digest(self.manifest),'composeDigest':digest(raw),'sourceDigest':digest(images),
                 'creationCommand':intent['argv'],'creationExitCode':0,'beforeDigest':digest(before),
                 'verification':'Preserved successful create and unchanged never-started metadata; no recreation/adoption'}
        exclusive_json(self.root/'creation.json',wrapped)
        return {'status':'CREATED_VERIFIED','containers':len(observed['containers']),'volumes':len(observed['volumes']),
                'networks':len(observed['networks']),'started':False}

    def _receipt(self):
        from isolated_provenance import validate_current
        wrapped=json.loads(lexical_path(self.root/'creation.json').read_text())
        raw,_,images=self._resolved_config(original=True)
        require(wrapped['manifestDigest']==digest(self.manifest) and wrapped['composeDigest']==digest(raw)
                and wrapped['sourceDigest']==digest(images),'Original configuration/source receipt drift')
        require(json.loads(lexical_path(self.root/'compose.json').read_text())==raw,'Original Compose file drift')
        receipt=wrapped['provenance']
        for directory, revision in self._revision_records():
            next_images=json.loads(lexical_path(directory/'images.json').read_text())
            next_raw=execution_compose(self.manifest,self.repo,self.run_id,{k:v['id'] for k,v in next_images.items()})
            require(revision['schema']==1 and revision['status']=='COMPLETE' and revision['runId']==self.run_id
                    and revision['manifestDigest']==digest(self.manifest) and revision['previousDigest']==digest(receipt)
                    and revision['sourceDigest']==digest(next_images) and revision['composeDigest']==digest(next_raw)
                    and revision['previousSourceDigest']==digest(images),'Revision chain/configuration drift')
            require(set(next_images)==set(images) and all(next_images[k]==images[k] for k in images if k!='be'),
                    'Non-BE image changed in revision')
            require(json.loads(lexical_path(directory/'compose.json').read_text())==next_raw,'Revision Compose file drift')
            next_receipt=revision['provenance']
            require(next_receipt['previous']==receipt,'Revision previous receipt mismatch')
            require(all(next_receipt['expected']['services'][service]['image']==spec['image']
                        for service,spec in next_raw['services'].items()),'Revision receipt/image mapping differs')
            command=revision['command']
            expected_argv=[*self._prefix(),'compose','--project-directory',str(self.root),'--env-file',str(self.credentials_path),
                '-p',self.project,'-f',str(directory/'compose.json'),'up','--no-start','--no-deps','--force-recreate',
                '--no-build','--pull','never','be','be-auth-short','be-student-short']
            require(command['exitCode']==0 and command['runId']==self.run_id and json.loads(command['argv'])==expected_argv
                    and command['startedAt']==next_receipt['revisionStartedAt']
                    and command['finishedAt']==next_receipt['revisionFinishedAt'],'Revision actual operation evidence differs')
            validate_current(next_receipt,next_receipt['resources'])
            receipt,images=next_receipt,next_images
        for name,sha in self.preparation['configHashes'].items():
            require(hashlib.sha256(lexical_path(self.root/name).read_bytes()).hexdigest()==sha,'Read-only nginx bind changed')
        return receipt

    def prepare_attempt(self):
        require(getattr(self,'attempt_id',None), 'Explicit attempt name required')
        receipt=self._receipt()
        self.verify_image_sources(self._image_records())
        require(not self.attempt_root.exists(), 'Attempt already exists; preserve original results')
        self.attempt_root.mkdir(mode=0o700,parents=True)
        for path in (self.results,self.fixtures,self.plans):path.mkdir(mode=0o700)
        exclusive_json(self.attempt_root/'attempt.json', {'schema':1,'attemptId':self.attempt_id,
            'trialId':self.manifest['id'],'project':self.project,'runId':self.run_id,
            'currentProvenanceDigest':digest(receipt),'source':self.source_identity(),'createdAt':now()})

    def _check_attempt_binding(self, receipt=None):
        receipt = receipt or self._receipt()
        attempt = getattr(self, 'attempt_id', None)
        if attempt is None:
            require(receipt.get('schema') != 2, 'A BE image revision requires a separately bound integration attempt')
            return None
        row = json.loads(lexical_path(self.attempt_root/'attempt.json').read_text())
        images = self._image_records()
        source_digest = digest({key: value.get('source', {}).get('sourceDigest', value['id'])
                                for key, value in images.items()})
        require(row.get('schema') == 1 and row.get('attemptId') == attempt
                and row.get('trialId') == self.manifest['id'] and row.get('project') == self.project
                and row.get('runId') == self.run_id and row.get('currentProvenanceDigest') == digest(receipt)
                and row.get('source', {}).get('working_source_sha256') == source_digest,
                'Attempt belongs to another image/source/provenance revision; preserve it and use a new attempt')
        return row

    def revise_be(self, revision, include_sources=()):
        """Build a new BE image and recreate only its three stopped trial containers.

        No start is issued here. All old receipts, build inputs and result records
        remain immutable; an incomplete recreation blocks later operations.
        """
        from isolated_images import materialize_context,validate_materialized_context,validate_image_config
        from isolated_provenance import validate_current,validate_effective_compose,validate_recreated,BE_REVISION_SERVICES
        require(not getattr(self,'attempt_id',None), 'Image revision is separate from an integration attempt')
        require(isinstance(revision,str) and re.fullmatch(r'(?:observation|fixed)-\d{2}',revision), 'Explicit BE revision identifier required')
        previous=self._receipt();before=self.observe(previous['expected']);validate_current(previous,before)
        require(all(row['state'] in ('created','exited') for row in before['containers'].values()),
                'All trial services must be stopped before BE image revision')
        inventory=self.inventory()
        require(inventory['frozen']==self.preparation['before']['frozen'],'Historical environment metadata changed')
        images=self._image_records()
        # Old BE source may now contain the diagnosed change. Its copied context
        # remains verifiable; unchanged component source must still match.
        for component,record in images.items():
            if 'source' in record:validate_materialized_context(record['source'])
        self.verify_image_sources({k:v for k,v in images.items() if k!='be'})
        revisions=lexical_path(self.root/'revisions');revisions.mkdir(mode=0o700,exist_ok=True)
        require(not any(path.name.endswith('-'+revision) for path in revisions.iterdir()), 'Revision name already used')
        number=len(list(revisions.iterdir()))+1
        require(number<=999,'Revision limit reached')
        name=f'{number:03d}-{revision}';directory=revisions/name;directory.mkdir(mode=0o700)
        files=[p for p in subprocess.check_output(['git','ls-files','-z'],cwd=self.repo).decode().split('\0') if p]
        require(isinstance(include_sources,(list,tuple)) and len(set(include_sources))==len(include_sources) and
                all(isinstance(path,str) and re.fullmatch(r'be/src/(?:main|test)/java/[A-Za-z0-9_/]+\.java',path)
                    and '..' not in path for path in include_sources),'Only explicit BE Java source additions allowed')
        files=sorted(set(files)|set(include_sources))
        context=materialize_context(self.repo,self.root,'be',files,revision=name)
        context['explicitAdditionalSources']=list(include_sources)
        tag=f'{self.project}-be:run-{self.run_id[:8]}-{name}'
        require(self._raw(['image','inspect',tag]).returncode!=0,'Revision image tag exists; no overwrite')
        argv=['build','--network','default','--pull=false','-f',str(directory/'contexts/be/Dockerfile.local'),
              '--label',RUN_LABEL+'='+self.run_id,
              *[item for key,value in context['labels'].items() for item in ('--label',key+'='+value)],
              '-t',tag,str(directory/'contexts/be')]
        start=now();result=self._raw(argv,timeout=1200)
        build_record=self.record('build-'+name,[*self._prefix(),*argv],result,start)
        exclusive_json(directory/'build-command.json',build_record)
        require(result.returncode==0,'BE revision image build failed; preserved original containers')
        image=self._json(['image','inspect',tag])[0]
        require(all(image['Config'].get('Labels',{}).get(k)==v for k,v in context['labels'].items()),'Revision image source labels mismatch')
        validate_image_config('be',image['Config'])
        updated=copy.deepcopy(images)
        updated['be']={'id':image['Id'],'tag':tag,'source':context,'command':image['Config'].get('Cmd') or [],
            'entrypoint':image['Config'].get('Entrypoint') or [],'envHash':digest(image['Config'].get('Env') or []),
            'volumes':image['Config'].get('Volumes') or {}}
        require(updated['be']['id']!=images['be']['id'],'BE revision did not change image identity')
        self.verify_image_sources(updated)
        exclusive_json(directory/'images.json',updated)
        raw=execution_compose(self.manifest,self.repo,self.run_id,{k:v['id'] for k,v in updated.items()})
        values=self._credentials()
        resolved=json.loads(re.sub(r'\$\{(ISOLATED_[A-Z0-9_]+):\?fresh trial credentials required\}',
                                  lambda match:values[match[1]],json.dumps(raw)))
        expected=self._expected(resolved,updated)
        expected['volumes']=sorted(expected['volumes'])
        for spec in expected['services'].values():spec['networkNames']=sorted(spec['networkNames'])
        expected_change=copy.deepcopy(previous['expected'])
        for service in BE_REVISION_SERVICES:expected_change['services'][service]['image']=updated['be']['id']
        require(expected==expected_change,'BE revision must only change the BE image')
        compose_path=directory/'compose.json';exclusive_json(compose_path,raw)
        base=['compose','--project-directory',str(self.root),'--env-file',str(self.credentials_path),'-p',self.project,'-f',str(compose_path)]
        config=self._raw([*base,'config','--format','json'])
        require(config.returncode==0,'Revision Compose configuration failed')
        validate_effective_compose(resolved,json.loads(config.stdout))
        # Recheck after build/config, immediately before the actual operation.
        current=self.observe(previous['expected']);validate_current(previous,current)
        def stable(value):
            copied=copy.deepcopy(value)
            for row in copied['containers'].values():row['mounts']=sorted(row['mounts'],key=lambda mount:mount['destination'])
            return copied
        require(stable(current)==stable(before),'Trial metadata changed during revision preparation')
        argv=[*base,'up','--no-start','--no-deps','--force-recreate','--no-build','--pull','never',*BE_REVISION_SERVICES]
        started=now()
        intent={'runId':self.run_id,'operation':'recreate-be-without-start','argv':argv,'startedAt':started,
                'previousDigest':digest(previous),'before':before,'expected':expected,'sourceDigest':digest(updated),
                'oldContainerIds':{k:before['containers'][k]['id'] for k in BE_REVISION_SERVICES}}
        exclusive_json(directory/'recreate-intent.json',intent)
        result=self._raw(argv,timeout=180)
        record=self.record('recreate-'+name,[*self._prefix(),*argv],result,started)
        exclusive_json(directory/'recreate-command.json',record)
        require(result.returncode==0,'BE recreation incomplete; no automatic adoption or start')
        observed=self.observe(expected);exclusive_json(directory/'observed.json',observed)
        receipt=validate_recreated(previous,before,observed,expected,started,record['finishedAt'])
        current_inventory=self.inventory()
        old_ids={r['id'] for r in before['containers'].values()};new_ids={r['id'] for r in observed['containers'].values()}
        require(set(current_inventory['containers'])==set(inventory['containers'])-old_ids|new_ids
                and current_inventory['volumes']==inventory['volumes'] and current_inventory['networks']==inventory['networks']
                and current_inventory['frozen']==inventory['frozen'],'Unrelated resource inventory changed during BE revision')
        wrapped={'schema':1,'status':'COMPLETE','revision':name,'runId':self.run_id,'provenance':receipt,
            'manifestDigest':digest(self.manifest),'previousDigest':digest(previous),'previousSourceDigest':digest(images),
            'sourceDigest':digest(updated),'composeDigest':digest(raw),'command':record,
            'oldContainerIds':intent['oldContainerIds'],'newContainerIds':{k:observed['containers'][k]['id'] for k in BE_REVISION_SERVICES}}
        exclusive_json(directory/'revision.json',wrapped)
        return {'status':'BE_RECREATED_VERIFIED','revision':name,'imageId':updated['be']['id'],
                'oldContainerIds':wrapped['oldContainerIds'],'newContainerIds':wrapped['newContainerIds'],'started':False}

    def _start_rows(self):
        path=self.root/'operations.jsonl'
        rows=[json.loads(x) for x in lexical_path(path).read_text().splitlines()] if path.exists() else []
        return [row for row in rows if row['operation']=='start']

    def _started(self):
        rows=self._start_rows()
        if not rows:return set()
        current=self._receipt()['resources']['containers']
        # A retired container's start intent cannot authorize an externally
        # started replacement bearing the same service name.
        return {service for row in rows for service,identifier in zip(row['services'],row.get('ids',[]))
                if service in current and current[service]['id']==identifier}

    def set_stage(self,suite,phase='browser'):
        require(suite in SUITES and phase in ('data','browser'), 'Unknown execution stage')
        receipt=self._receipt();attempt=self._check_attempt_binding(receipt)
        if suite!='auth':
            completed=json.loads((getattr(self,'attempt_root',self.root)/'auth-pass.json').read_text())
            require(completed['runId']==self.run_id and completed['status']=='PASS', 'Auth must pass before remaining suites')
            if attempt is not None:
                require(completed.get('attemptId')==self.attempt_id
                        and completed.get('currentProvenanceDigest')==digest(receipt)
                        and completed.get('source',{}).get('working_source_sha256')==attempt['source']['working_source_sha256'],
                        'Auth PASS is not from this attempt and current image revision')
        row={'suite':suite,'phase':phase,'runId':self.run_id,
             'attemptId':getattr(self,'attempt_id',None),'provenanceDigest':digest(receipt)}
        # This mutable cursor is not a provenance receipt. Each operation still checks the immutable creation proof.
        path=lexical_path(self.root/'active-stage.json')
        path.write_text(json.dumps(row)+'\n')
        exclusive_json(self.results/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')+'-stage.json'),row)

    def _allowed_services(self,operation):
        if operation in ('stop','unpause'):
            return self._started()
        receipt=self._receipt();attempt=self._check_attempt_binding(receipt)
        stage=json.loads(lexical_path(self.root/'active-stage.json').read_text())
        if attempt is not None:
            require(stage.get('attemptId')==self.attempt_id and stage.get('provenanceDigest')==digest(receipt),
                    'Active stage belongs to another attempt or image revision')
        require(stage.get('runId')==self.run_id and stage.get('suite') in SUITES, 'Explicit current run stage required')
        allowed=required_services(stage['suite'],stage['phase'])
        if stage['suite']=='student':
            allowed=[{'be-auth-short':'be-student-short','web-auth-test':'web-student-short'}.get(s,s) for s in allowed]
        return set(allowed)

    def _operation(self, operation, services, *, payload=None, stdin=None):
        from isolated_provenance import validate_current, operation_ids
        receipt=self._receipt();expected=receipt['expected']
        observed=self.observe(expected);validate_current(receipt,observed)
        allowed=self._allowed_services(operation)
        require(services and len(set(services))==len(services),'Explicit unique service targets required')
        require(set(services)<=allowed,'Services not required by the active suite/phase')
        if operation=='start' and set(services)&set(CONSUMERS):self.verify_pending_work()
        ids=operation_ids(receipt,observed,operation,list(services),allowed,self._started())
        if operation=='start':
            running={s for s,r in observed['containers'].items() if r['state']=='running'}
            require(not ({'web-auth-test','web-student-short'} <= running|set(services)),'Short endpoint port collision')
        argv=[operation,*ids]
        if operation=='stop':argv=['stop','--time','20',*ids]
        if operation=='exec':
            require(len(services)==1 and payload,'Single receipt-bound exec payload required')
            encoded=json.dumps(payload)
            require(not any(x in encoded for x in ('dodream-phase1','host.docker.internal','/var/run/docker.sock','.local/env','/Users/')),'Existing/host target in exec payload')
            require(payload[0] in ('python','sh','cp','curl','redis-cli'),'Unsupported trial exec tool')
            require(not (stdin and re.search(r'\b(?:DROP|TRUNCATE|DELETE|FLUSHALL|FLUSHDB)\b',stdin,re.I)), 'Deletion/reset SQL is forbidden')
            argv=['exec','-i',*ids,*payload]
        start=now()
        with (self.root/'operations.jsonl').open('a') as stream:stream.write(json.dumps({'operation':operation,'services':list(services),'ids':ids,'startedAt':start})+'\n')
        result=self._raw(argv,stdin=stdin,timeout=180)
        # SQL/results can include local account details; only bounded status is logged for exec.
        self.record(operation+'-'+'-'.join(services),[*self._prefix(),*argv] if operation!='exec' else ['docker','exec',*ids,'[reviewed payload]'],
                    result if operation!='exec' else subprocess.CompletedProcess([],result.returncode,stdout=''),start)
        require(result.returncode==0, 'Receipt-bound '+operation+' failed: '+','.join(services))
        return result

    def wait_healthy(self, services, seconds=180):
        deadline=time.monotonic()+seconds
        while True:
            receipt=self._receipt();expected=receipt['expected']
            observed=self.observe(expected)
            from isolated_provenance import validate_current
            validate_current(receipt,observed)
            ids=[observed['containers'][s]['id'] for s in services]
            fmt='{{json .State.Status}}\t{{if .State.Health}}{{json .State.Health.Status}}{{else}}null{{end}}'
            result=self._raw(['inspect','--format',fmt,*ids])
            states=[list(map(json.loads,x.split('\t'))) for x in result.stdout.splitlines()]
            if len(states)==len(ids) and all(s=='running' and h in (None,'healthy') for s,h in states):return
            require(not any(s in ('exited','dead') or h=='unhealthy' for s,h in states),'New service failed health; no auth retry')
            require(time.monotonic()<deadline,'New service health timeout')
            time.sleep(2)

    def sql(self, statement):
        command=['sh','-c','MYSQL_PWD="$MYSQL_PASSWORD" mysql --default-character-set=utf8mb4 -N -B -u"$MYSQL_USER" "$MYSQL_DATABASE"']
        return self._operation('exec',['mysql'],payload=command,stdin=statement).stdout.strip()

    def verify_pending_work(self):
        from isolated_checks import verify_pending_work
        return verify_pending_work(self)

    def compose_args(self,*args):
        return [sys.executable,str(Path(__file__).resolve()),'--manifest',str(self.manifest_path),'--action','legacy-exec','--payload',json.dumps(list(args))]

    def compose(self,name,*args,stdin=None):
        args=list(args);operation=args.pop(0)
        if operation=='exec':
            if args and args[0]=='-T':args.pop(0)
            service=args.pop(0)
            return self._operation('exec',[service],payload=args,stdin=stdin)
        require(operation in ('up','start','stop'),'Unsupported isolated legacy operation')
        services=[];i=0
        while i<len(args):
            if args[i] in ('-d','--no-deps','--wait'):i+=1
            elif args[i]=='--wait-timeout':require(i+1<len(args) and args[i+1]=='180','Unknown wait');i+=2
            else:require(not args[i].startswith('-'),'Unknown legacy option');services.append(args[i]);i+=1
        require(services and len(set(services))==len(services),'Explicit unique service targets required')
        from isolated_provenance import validate_current
        receipt=self._receipt();observed=self.observe(receipt['expected'])
        validate_current(receipt,observed)
        actual_operation='start' if operation in ('up','start') else 'stop'
        allowed=self._allowed_services(actual_operation)
        # A previously started, still-running service needs no new start. No unreceipted
        # or never-started target can acquire permission through this idempotent adapter.
        require(set(services)<=set(observed['containers']),'Unknown service target')
        require(all(s in allowed or (actual_operation=='stop' and observed['containers'][s]['state']=='created') for s in services), 'Service outside active stage')
        selected=[s for s in services if observed['containers'][s]['state'] not in (('running',) if actual_operation=='start' else ('created','exited'))]
        if actual_operation=='start':
            require(all(s in self._started() for s in services if s not in selected),'Running target lacks this runs start record')
        result=self._operation(actual_operation,selected) if selected else subprocess.CompletedProcess([],0,stdout='NO_NEW_OPERATION\n')
        if operation in ('up','start'):self.wait_healthy(services)
        return result

    def run(self,name,args):
        require(args[:3]==[sys.executable,str(Path(__file__).resolve()),'--manifest'],'Raw legacy process execution forbidden')
        started=now();result=subprocess.run(args,cwd=self.repo,env=self.clean_env(),capture_output=True,text=True)
        self.record(name,args,result,started);return result

    def pause_chroma(self,resume=False):return self._operation('unpause' if resume else 'pause',['chroma'])
    def crash_owned(self,service):raise PolicyError('Crash injection is not needed for this browser scope')
    def stop_owned_test(self,name):raise PolicyError('No one-off legacy containers are authorized')

    def fixture_binding(self,suite):
        receipt=self._receipt()
        return {'trialId':self.manifest['id'],'project':self.project,'suite':suite,'runId':self.run_id,
                'origin':self.origins['short' if suite in ('auth','demo-disabled') else 'main'],
                'syntheticOnly':True,'provenanceDigest':digest(receipt),
                **({'attemptId':self.attempt_id} if getattr(self,'attempt_id',None) else {})}

    def assert_ready_for_browser(self,suite):
        from isolated_provenance import validate_current
        receipt=self._receipt();observed=self.observe(receipt['expected'])
        validate_current(receipt,observed)
        required=SUITES[suite]
        if suite=='student':required=[{'be-auth-short':'be-student-short','web-auth-test':'web-student-short'}.get(s,s) for s in required]
        require(all(observed['containers'][s]['state'] in (('running','exited') if suite=='indexing' and s=='index-dispatcher' else ('running',)) for s in required),'Required isolated browser services not running')
        fixture=json.loads((getattr(self,'fixtures',self.root/'fixtures')/f'{suite}.json').read_text())
        require(all(fixture.get(k)==v for k,v in self.fixture_binding(suite).items()),'Fixture creation receipt mismatch')

    def stop_started(self):
        receipt=self._receipt();observed=self.observe(receipt['expected'])
        for s in ('index-dispatcher','worker',*sorted(self._started()-set(CONSUMERS))):
            if s in self._started() and observed['containers'][s]['state'] in ('running','paused'):
                if observed['containers'][s]['state']=='paused':self._operation('unpause',[s])
                self._operation('stop',[s])
        current=self.inventory()
        exclusive_json(self.results/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')+'-shutdown.json'),
                       {'status':'STOPPED_PRESERVED','frozenMetadataUnchanged':current['frozen']==self.preparation['before']['frozen'],
                        'inventory':current})
        require(current['frozen']==self.preparation['before']['frozen'],'Historical state metadata changed')
        return {'status':'STOPPED_PRESERVED','startedServices':sorted(self._started())}


def load_active_runtime():
    config=os.environ.get('DODREAM_ISOLATED_MANIFEST')
    require(config and Path(config).is_absolute(),'Explicit isolated runtime required')
    return TrialRuntime(Path(__file__).resolve().parents[2],config)


def java_boundary_plan(manifest, repo, manifest_path, revision, attempt):
    """File-only description of the existing helper, not execution permission."""
    from isolated_boundary_tests import CLASSES, COMMAND
    root=validate_manifest(manifest,repo,manifest_path)
    require(isinstance(revision,str) and re.fullmatch(r'\d{3}-fixed-\d{2}',revision), 'Explicit planned fixed BE revision required')
    require(isinstance(attempt,str) and re.fullmatch(r'[a-z][a-z0-9-]{0,47}',attempt), 'Explicit planned attempt required')
    return {'status':'PLAN_ONLY','executionAuthorized':False,'resourceProvenance':'NOT_CHECKED',
            'project':manifest['project'],'root':str(root),'manifest':str(manifest_path),
            'revision':revision,'attempt':attempt,'requiredServices':['mysql','redis','ai'],
            'javaClasses':list(CLASSES),'testCommand':list(COMMAND),
            'fixedFixture':'indexing-synthetic-44444444-4444-4444-8444-444444444444.pdf',
            'condition':'Fixed HTTP fixture must be unused; missing prior success evidence does not prove an empty database.'}


def prepare_java_boundary(runtime, revision):
    """Validate the existing trial before starting the three required services."""
    from isolated_provenance import validate_current
    require(isinstance(revision,str) and re.fullmatch(r'\d{3}-fixed-\d{2}',revision),
            'An explicit verified fixed BE revision is required')
    require(isinstance(runtime.attempt_id,str) and re.fullmatch(r'[a-z][a-z0-9-]{0,47}',runtime.attempt_id),
            'An explicit new boundary test attempt is required')
    receipt=runtime._receipt()
    revisions=runtime._revision_records()
    require(revisions and revisions[-1][0].name==revision, 'Requested BE revision is not the current verified revision')
    images=runtime._image_records()
    # A successful run of this exact source already consumed its fixed HTTP fixture.
    # Missing evidence is not an emptiness proof; the Java duplicate guard remains mandatory.
    previous=lexical_path(runtime.root/'boundary-tests')
    if previous.exists():
        records=list(previous.glob('???-fixed-??/*/result.json'))
        require(len(records)<=100, 'Too many prior boundary results; review the trial explicitly')
        for filename in records:
            result=json.loads(lexical_path(filename).read_text())
            same_source=result.get('sourceDigest')==images['be']['source']['sourceDigest']
            http_class=next((row for row in result.get('classes',[]) if row.get('class')==
                'A704.DODREAM.indexing.IndexingRequestBoundaryDatabaseTests'),{})
            require(not (same_source and result.get('status')=='PASS' and http_class.get('tests',0)>=6
                         and all(http_class.get(key)==0 for key in ('failures','errors','skipped'))),
                    'This source already completed its fixed HTTP fixture; Java rerun is blocked without deleting data or bypassing the guard')
    runtime.verify_image_sources(images)
    observed=runtime.observe(receipt['expected'])
    validate_current(receipt,observed)
    require(all(row['state'] in ('created','exited') for row in observed['containers'].values()),
            'Java boundary action requires stopped trial services; no running resources are adopted')
    runtime.prepare_attempt()
    runtime._check_attempt_binding(receipt)
    # Reuse the existing non-consumer scope; a fresh Java attempt has no browser auth PASS.
    runtime.set_stage('auth','browser')


def run_with_owned_cleanup(runtime, action):
    """Shared signal and finally path; only this runtime's recorded starts may stop."""
    def interrupted(signum,frame):
        raise KeyboardInterrupt('Trial interrupted; stopping only recorded new starts')
    previous={sig:signal.signal(sig,interrupted) for sig in (signal.SIGINT,signal.SIGTERM)}
    os.environ['DODREAM_ISOLATED_MANIFEST']=str(runtime.manifest_path)
    if runtime.attempt_id:os.environ['DODREAM_ISOLATED_ATTEMPT']=runtime.attempt_id
    try:
        return action()
    finally:
        try:runtime.stop_started()
        finally:
            for sig,handler in previous.items():signal.signal(sig,handler)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--action', choices=('plan','java-boundary-plan','prepare','build','create','verify-created','revise-be','validate','java-boundary','stop','legacy-exec'), default='plan',
                        help='Explicit stage. prepare/build/create never start applications. validate runs browser integration; java-boundary runs the four selected Java classes using only new mysql/redis/ai and a receipt-checked test container. Both stop only recorded new starts.')
    parser.add_argument('--revision')
    parser.add_argument('--include-source',action='append',default=[])
    parser.add_argument('--attempt')
    parser.add_argument('--suite', choices=SUITES)
    parser.add_argument('--phase', choices=('data', 'browser'))
    parser.add_argument('--operation', choices=('config', 'up'))
    parser.add_argument('--services', nargs='+')
    parser.add_argument('--payload', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    repo = Path(__file__).resolve().parents[2]
    runtime = None
    try:
        if args.action in ('plan','java-boundary-plan'):
            manifest = load_manifest(args.manifest, repo)
            if args.action=='plan':
                result = build_plan(manifest, repo, Path(args.manifest), args.suite, args.phase, args.operation, args.services)
            else:
                require(not any((args.suite,args.phase,args.operation,args.services,args.include_source,args.payload)),
                        'Java boundary plan does not accept other suite, operation or source overrides')
                result = java_boundary_plan(manifest,repo,Path(args.manifest),args.revision,args.attempt)
        else:
            require(not any((args.phase,args.operation,args.services)), 'Plan arguments cannot authorize execution')
            if args.action=='java-boundary':
                require(args.attempt and args.revision and args.suite is None and not args.include_source and args.payload is None,
                        'Java boundary execution requires explicit --revision and --attempt without suite or source overrides')
            runtime = TrialRuntime(repo,args.manifest,preparing=args.action=='prepare',attempt=args.attempt)
            if args.action=='prepare': result=runtime.prepare()
            elif args.action=='build': result=runtime.build_images()
            elif args.action=='create': result=runtime.create()
            elif args.action=='verify-created': result=runtime.verify_created()
            elif args.action=='revise-be': result=runtime.revise_be(args.revision,args.include_source)
            elif args.action=='stop': result=runtime.stop_started()
            elif args.action=='java-boundary':
                prepare_java_boundary(runtime,args.revision)
                from isolated_boundary_tests import run as run_java_boundary
                def selected_java():
                    runtime.compose('java-boundary-stores','start','mysql','redis')
                    runtime.compose('java-boundary-local-provider','start','ai')
                    return run_java_boundary(runtime)
                result=run_with_owned_cleanup(runtime,selected_java)
            elif args.action=='legacy-exec':
                require(args.payload is not None,'Explicit legacy proxy payload required')
                payload=json.loads(args.payload)
                require(isinstance(payload,list) and payload and all(isinstance(x,str) for x in payload), 'Invalid legacy payload')
                stdin=sys.stdin.read() if payload[0]=='exec' else None
                completed=runtime.compose('legacy-proxy',*payload,stdin=stdin)
                # Existing SQL/fixture callers consume this private pipe. Never include it in CLI evidence output.
                sys.stdout.write(completed.stdout or '')
                return completed.returncode
            elif args.action=='validate':
                require(args.suite in (None,'auth'), 'Validation must begin with auth; no suite skipping')
                if runtime.attempt_id: runtime.prepare_attempt()
                from isolated_checks import run_auth, run_remaining
                def selected_integration():
                    run_auth(runtime)
                    if args.suite is None: run_remaining(runtime)
                    return {'status':'PASS','scope':'AUTH_ONLY' if args.suite else 'RELATED_INTEGRATION'}
                result=run_with_owned_cleanup(runtime,selected_integration)
    except (Exception, KeyboardInterrupt) as error:
        message=f'{type(error).__name__}: {error}'
        if runtime is not None and runtime.preparation:
            message=runtime.redact(message)
            failure_root=runtime.results if runtime.results.is_dir() else runtime.root/'results'
            exclusive_json(failure_root/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')+'-action-failure.json'),
                           {'action':args.action,'error':message,'runId':runtime.run_id,'status':'FAIL'})
        print(f'ISOLATED_EXECUTION=BLOCKED: {message}', file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
