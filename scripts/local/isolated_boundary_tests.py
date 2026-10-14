"""One bounded, receipt-checked Java boundary test container; no CLI or import effects.

Uses the current fixed BE revision's unchanged test target, the same new MySQL /
Redis / local AI network and one new be-data volume. It never removes a container or volume.
The parent runtime remains the sole Docker executor and credential source.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET


CLASSES = (
    'A704.DODREAM.indexing.IndexingObservationTests',
    'A704.DODREAM.indexing.IndexingRequestBoundaryDatabaseTests',
    'A704.DODREAM.file.FileInputBoundaryTests',
    'A704.DODREAM.file.PdfUploadPermissionBoundaryTests',
)
COMMAND = ['gradle', '--offline', '--no-daemon', 'test',
           *[part for name in CLASSES for part in ('--tests', '*.' + name.rsplit('.', 1)[1])], '--rerun-tasks']
LABEL_PREFIX = 'org.dodream.trial.'
UNUSED_IMAGE_CACHE = '/home/gradle/.gradle'
UNUSED_CACHE_TMPFS = 'rw,noexec,nosuid,size=16m'
TEST_CACHE = '/opt/dodream-test-gradle-cache'
BOUNDARY_DOCKERFILE_LABEL = 'org.dodream.trial.boundary-dockerfile-sha256'
BOUNDARY_STAGE = '''\nFROM test AS boundary-tests
RUN test -d /home/gradle/.gradle/caches/modules-2 && mkdir /opt/dodream-test-gradle-cache && cp -a /home/gradle/.gradle/. /opt/dodream-test-gradle-cache/ && test -d /opt/dodream-test-gradle-cache/caches/modules-2
'''


def boundary_dockerfile(original):
    """Append only an image-local public build-cache copy, never host data."""
    require(isinstance(original, str) and original.endswith('\n') and 'AS boundary-tests' not in original,
            'An unchanged original Dockerfile is required')
    return original + BOUNDARY_STAGE


def validate_boundary_dockerfile(original, generated):
    require(generated == boundary_dockerfile(original), 'Boundary Dockerfile differs from the exact cache-copy stage')
    return {'originalSha256': hashlib.sha256(original.encode()).hexdigest(),
            'generatedSha256': hashlib.sha256(generated.encode()).hexdigest(),
            'target': 'boundary-tests', 'cacheSource': UNUSED_IMAGE_CACHE, 'cacheDestination': TEST_CACHE}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def timestamp(value):
    require(isinstance(value, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|\+00:00)', value),
            'Invalid Docker creation timestamp')
    value = re.sub(r'(\.\d{6})\d+', r'\1', value)
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def write_new(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def stable_resources(observed):
    """Docker may reorder Mounts; every mount field still participates in comparison."""
    result = json.loads(json.dumps(observed))
    for row in result['containers'].values():
        row['mounts'] = sorted(row.get('mounts', []), key=lambda value: json.dumps(value, sort_keys=True))
    return result


def test_environment(image, be_environment, dockerfile):
    """Require the observed root build/cache contract before overriding runtime HOME."""
    lines = [line.strip() for line in dockerfile.splitlines()]
    require('FROM gradle:8.14.3-jdk17 AS build' in lines and 'FROM build AS test' in lines,
            'Unexpected Gradle build/test stages')
    stage = lines[lines.index('FROM gradle:8.14.3-jdk17 AS build'):lines.index('FROM build AS test')]
    instructions = [line for line in stage if line and not line.startswith('#')]
    require(instructions == ['FROM gradle:8.14.3-jdk17 AS build', 'WORKDIR /workspace',
            'COPY --chown=gradle:gradle build.gradle settings.gradle gradle.lockfile ./',
            'COPY --chown=gradle:gradle src ./src',
            'RUN gradle --no-daemon bootJar testClasses resolveTestRuntime'],
            'Build user/cache contract changed')
    config = image['Config']
    require(config.get('User') == 'root', 'Test target must retain the reviewed root build user')
    values = dict(item.split('=', 1) for item in config.get('Env') or [])
    require('HOME' not in values and 'GRADLE_USER_HOME' not in values,
            'Build cache HOME differs from the reviewed image metadata')
    require('HOME' not in be_environment and 'GRADLE_USER_HOME' not in be_environment,
            'Spring settings may not override the Gradle cache')
    return {**be_environment, 'HOME': '/root', 'GRADLE_USER_HOME': TEST_CACHE}


def junit_summary(expected_class, private_text, redact):
    """Parse a redacted copy; export only counts and failed test identities."""
    document = ET.fromstring(redact(private_text))
    require(document.attrib.get('name') == expected_class, 'Unexpected selected JUnit class')
    result = {'class': expected_class, **{key: int(document.attrib[key])
              for key in ('tests', 'failures', 'errors', 'skipped')}}
    result['failedCases'] = [{'class': child.attrib.get('classname', expected_class), 'name': child.attrib.get('name', '')}
                             for child in document.findall('testcase') if child.find('failure') is not None or child.find('error') is not None]
    return result


def validate_selected_test_sources(sources):
    """Gradle treats an uppercase-leading selector as a simple class pattern.

    The wildcard package prefix is safe only when these four declarations are
    unique in the exact, already hashed test source context.
    """
    require(isinstance(sources, dict) and sources, 'Selected test sources are missing')
    matches = {}
    for full_class in CLASSES:
        simple = full_class.rsplit('.', 1)[1]
        expected = 'src/test/java/' + full_class.replace('.', '/') + '.java'
        declarations = [path for path, text in sources.items()
                        for _ in re.finditer(r'\bclass\s+' + re.escape(simple) + r'\b', text)]
        require(declarations == [expected], 'Selected simple class is missing or ambiguous')
        package = full_class.rsplit('.', 1)[0]
        require(re.search(r'^package\s+' + re.escape(package) + r'\s*;', sources[expected], re.MULTILINE),
                'Selected test package differs from its full class')
        matches[full_class] = expected
    return matches


def junit_outcome(exit_code, wait_output, reports, missing_reports, log_text):
    passed = exit_code == 0 and wait_output.strip() == '0' and not missing_reports and len(reports) == len(CLASSES) and all(
        row['class'] == name and row['tests'] > 0 and row['failures'] == row['errors'] == row['skipped'] == 0
        for row, name in zip(reports, CLASSES))
    log_text = log_text.lower()
    preparation_failure = not reports and exit_code != 0
    phase = ('GRADLE_NO_TESTS_FOUND' if preparation_failure and 'no tests found for given includes' in log_text
             else 'GRADLE_PLUGIN_RESOLUTION_FAILURE' if preparation_failure and 'org.springframework.boot' in log_text
             and 'plugin' in log_text and ('not found' in log_text or 'could not resolve' in log_text)
             else 'GRADLE_FAILED_WITHOUT_JUNIT_REPORTS' if preparation_failure
             else 'SELECTED_JUNIT_REPORTS')
    return {'status': 'PASS' if passed else 'FAIL', 'executionPhase': phase,
            'reportedJavaTests': sum(row['tests'] for row in reports), 'missingClasses': missing_reports}


def expected_config(project, run_id, revision, attempt, image, environment, volume, network):
    """Pure expected shape; no environment or Docker discovery."""
    require(re.fullmatch(r'dodream-evidence-\d{8}', project), 'Unknown isolated project')
    require(re.fullmatch(r'\d{3}-fixed-\d{2}', revision), 'A verified fixed BE revision is required')
    require(isinstance(attempt, str) and re.fullmatch(r'[a-z][a-z0-9-]{0,47}', attempt), 'Explicit boundary test attempt required')
    require(re.fullmatch(r'[0-9a-f-]{36}', run_id), 'Invalid isolated run')
    require(re.fullmatch(r'sha256:[0-9a-f]{64}', image['Id']), 'Immutable test image required')
    config = image['Config']
    require(config.get('Entrypoint') == ['/__cacert_entrypoint.sh'] and config.get('Volumes') == {UNUSED_IMAGE_CACHE: {}}
            and config.get('User') == 'root',
            'Test image has an unreviewed entrypoint, volume or build user')
    image_environment = dict(item.split('=', 1) for item in config.get('Env') or [])
    require('HOME' not in image_environment and 'GRADLE_USER_HOME' not in image_environment,
            'Test image cache HOME differs')
    require((config.get('Cmd') or []) == ['gradle', '--offline', '--no-daemon', 'test', '--rerun-tasks'],
            'Test image is not the reviewed test target')
    require(config.get('WorkingDir') == '/workspace', 'Unexpected test image work directory')
    require(volume['Name'] == project + '_be-data' and volume['Driver'] == 'local'
            and not volume.get('Options'), 'Only the new plain be-data volume is allowed')
    require(network['Name'] == project + '_default' and network['Internal'] is True
            and network['Driver'] == 'bridge' and re.fullmatch(r'[0-9a-f]{64}', network['Id']),
            'Only the new internal default network is allowed')
    mountpoint = Path(volume['Mountpoint'])
    require(mountpoint.is_absolute() and '..' not in mountpoint.parts and mountpoint.name == '_data'
            and mountpoint.parent.name == volume['Name'] and not str(mountpoint).startswith('/Users/'),
            'Unexpected new volume storage source')
    for resource, kind, name in ((volume, 'volume', 'be-data'), (network, 'network', 'default')):
        labels = resource.get('Labels') or {}
        require(labels.get('io.dodream.trial.run-id') == run_id
                and labels.get('com.docker.compose.project') == project
                and labels.get('com.docker.compose.' + kind) == name,
                'New store/network creation labels do not match this run')
    require(environment.get('MYSQL_HOST') == 'mysql' and environment.get('REDIS_HOST') == 'redis'
            and environment.get('MYSQL_DATABASE') == project.replace('-', '_')
            and environment.get('MYSQL_USER') == 'synthetic_trial'
            and environment.get('SPRING_PROFILES_ACTIVE') == 'local'
            and environment.get('LOCAL_DATA_DIR') == '/app/local-data'
            and environment.get('AI_BASE_URL') == 'http://ai:8000'
            and environment.get('HOME') == '/root' and environment.get('GRADLE_USER_HOME') == TEST_CACHE,
            'Wrong new test service endpoints/cache')
    defaults = dict(item.split('=', 1) for item in config.get('Env') or [])
    defaults.update(environment)
    labels = dict(config.get('Labels') or {})
    labels.update({LABEL_PREFIX + 'project': project, LABEL_PREFIX + 'run': run_id,
                   LABEL_PREFIX + 'role': 'boundary-test', LABEL_PREFIX + 'revision': revision, LABEL_PREFIX + 'attempt': attempt})
    require(not any(key.startswith('com.docker.compose.') for key in labels), 'Test container cannot claim a Compose service')
    return {'name': project + '-boundary-tests-' + revision[4:] + '-' + attempt,
            'project': project, 'runId': run_id, 'revision': revision, 'attemptId': attempt,
            'image': image['Id'], 'labels': labels, 'command': COMMAND, 'entrypoint': [],
            'envHash': digest(sorted(defaults.items())), 'user': '0:0', 'workdir': '/workspace',
            'volumeName': volume['Name'], 'volumeSource': volume['Mountpoint'],
            'volumeDestination': '/app/local-data', 'networkName': network['Name'], 'networkId': network['Id']}


def validate_container(actual, expected, *, container_id=None, created_window=None, before_ids=()):
    """Pure validation; never emits credential values or acquires connections."""
    identifier = actual.get('Id')
    require(isinstance(identifier, str) and re.fullmatch(r'[0-9a-f]{64}', identifier), 'Invalid test container ID')
    require(identifier not in before_ids and (container_id is None or identifier == container_id), 'Test container ID was not freshly created')
    require(actual.get('Name') == '/' + expected['name'] and actual.get('Image') == expected['image'],
            'Test container name/image differs')
    if created_window:
        require(timestamp(created_window[0]) <= timestamp(actual['Created']) <= timestamp(created_window[1]),
                'Test container creation falls outside the actual command')
    config, host = actual['Config'], actual['HostConfig']
    require(config.get('Labels') == expected['labels'], 'Test labels differ from the reviewed identity')
    require((config.get('Cmd') or []) == expected['command'] and (config.get('Entrypoint') or []) == expected['entrypoint']
            and config.get('User') == expected['user'] and config.get('WorkingDir') == expected['workdir'],
            'Test command/user/working directory differs')
    env = config.get('Env') or []
    require(all('=' in value for value in env) and len({value.split('=', 1)[0] for value in env}) == len(env),
            'Malformed/duplicate test environment keys')
    require(digest(sorted(dict(value.split('=', 1) for value in env).items())) == expected['envHash'],
            'Test environment differs from the new trial settings')
    require(not host.get('PortBindings') and not host.get('PublishAllPorts') and not host.get('Privileged')
            and host.get('NetworkMode') == expected['networkId'], 'Unsafe test port/network/privilege configuration')
    require(not any(host.get(key) for key in ('Binds', 'VolumesFrom', 'ExtraHosts', 'Devices', 'DeviceRequests',
            'PidMode', 'CapAdd', 'Dns', 'DnsSearch', 'Links', 'SecurityOpt', 'Sysctls'))
            and host.get('IpcMode', 'private') in ('private', '')
            and host.get('RestartPolicy', {}).get('Name', 'no') == 'no', 'Unreviewed test host resource reference')
    require(host.get('Memory') == 1280 * 1024 * 1024 and host.get('NanoCpus') == 2_000_000_000,
            'Test resource bound differs')
    require(host.get('Tmpfs') == {UNUSED_IMAGE_CACHE: UNUSED_CACHE_TMPFS},
            'Unused image cache must have exactly the reviewed temporary mount')
    mounts = actual.get('Mounts') or []
    volumes = [mount for mount in mounts if mount.get('Type') == 'volume']
    temporary = [mount for mount in mounts if mount.get('Type') == 'tmpfs']
    require(len(volumes) == 1 and len(temporary) <= 1 and len(mounts) == 1 + len(temporary),
            'Test requires exactly one new data volume')
    require(not temporary or (temporary[0].get('Destination') == UNUSED_IMAGE_CACHE
            and not temporary[0].get('Source') and temporary[0].get('RW') is True
            and not temporary[0].get('Name')), 'Unreviewed temporary mount')
    mount = volumes[0]
    require(mount.get('Type') == 'volume' and mount.get('Name') == expected['volumeName']
            and mount.get('Source') == expected['volumeSource'] and mount.get('Destination') == expected['volumeDestination']
            and mount.get('RW') is True and mount.get('Driver') == 'local', 'Existing volume/bind/socket mount refused')
    networks = actual['NetworkSettings']['Networks']
    require(set(networks) == {expected['networkName']}, 'Unexpected test network attachment')
    attached = networks[expected['networkName']]['NetworkID']
    state = actual['State']['Status']
    never_started = state == 'created' and actual['State'].get('StartedAt', '').startswith('0001-')
    # Docker defers endpoint allocation for a never-started container. Its
    # NetworkMode already names the exact verified internal network ID.
    require(attached == expected['networkId'] or (never_started and attached == ''), 'Test network ID differs')
    require(state in ('created', 'running', 'exited'), 'Unknown test container state')
    return {'id': identifier, 'name': expected['name'], 'image': actual['Image'], 'created': actual['Created'],
            'state': state, 'exitCode': actual['State'].get('ExitCode'), 'envHash': expected['envHash'],
            'labels': expected['labels'], 'command': expected['command'], 'user': expected['user'],
            'volume': expected['volumeName'], 'networkId': expected['networkId'], 'ports': 0}


def run(runtime):
    """Explicit parent-authorized execution only; importing this file does nothing."""
    from isolated_images import safe_path
    from isolated_provenance import validate_current
    attempt = runtime.attempt_id
    require(isinstance(attempt, str) and re.fullmatch(r'[a-z][a-z0-9-]{0,47}', attempt), 'Explicit boundary test attempt required')
    receipt = runtime._receipt()
    observed = runtime.observe(receipt['expected'])
    validate_current(receipt, observed)
    require(all(row['state'] == 'running' if name in ('mysql', 'redis', 'ai') else row['state'] in ('created', 'exited')
                for name, row in observed['containers'].items()), 'Only new MySQL, Redis and AI may run during the boundary tests')
    _, resolved, images = runtime._resolved_config()
    runtime.verify_image_sources(images)
    source = images['be']['source']
    context = safe_path(source['contextPath'])
    test_paths = [row['path'] for row in source['sourceFiles']
                  if row['path'].startswith('src/test/java/') and row['path'].endswith('.java')]
    selected_sources = validate_selected_test_sources({path: safe_path(context / path).read_text() for path in test_paths})
    revision = context.parent.parent.name
    require(re.fullmatch(r'\d{3}-fixed-\d{2}', revision), 'Boundary tests require the verified fixed BE revision')
    before = runtime.inventory()
    require(before['frozen'] == runtime.preparation['before']['frozen'], 'Frozen metadata changed')
    root = safe_path(runtime.root / 'boundary-tests' / revision / attempt)
    require(not root.exists(), 'Boundary test already attempted; preserve its original evidence')
    root.mkdir(mode=0o700, parents=True)
    original_dockerfile = (context / 'Dockerfile.local').read_text()
    generated_dockerfile = boundary_dockerfile(original_dockerfile)
    dockerfile_receipt = validate_boundary_dockerfile(original_dockerfile, generated_dockerfile)
    dockerfile_path = safe_path(root / 'Dockerfile.boundary-tests')
    with dockerfile_path.open('x') as stream:
        stream.write(generated_dockerfile)
    dockerfile_path.chmod(0o600)
    write_new(root / 'dockerfile.json', {**dockerfile_receipt, 'sourceDigest': source['sourceDigest'],
              'selectedTestSources': selected_sources, 'testSelectors': COMMAND})
    image_tag = runtime.project + '-boundary-tests:run-' + runtime.run_id[:8] + '-' + revision + '-' + attempt
    require(runtime._raw(['image', 'inspect', image_tag]).returncode != 0, 'Test image tag already exists')
    build = ['build', '--network', 'default', '--pull=false', '--target', 'boundary-tests',
             '-f', str(dockerfile_path),
             '--label', BOUNDARY_DOCKERFILE_LABEL + '=' + dockerfile_receipt['generatedSha256'],
             *[item for key, value in source['labels'].items() for item in ('--label', key + '=' + value)],
             '--label', LABEL_PREFIX + 'run=' + runtime.run_id, '-t', image_tag, str(context)]
    started = utc()
    result = runtime._raw(build, timeout=1200)
    build_record = runtime.record('boundary-test-build', [*runtime._prefix(), *build], result, started)
    write_new(root / 'build.json', build_record)
    require(result.returncode == 0, 'Boundary test image build failed')
    runtime.verify_image_sources(images)
    require(validate_boundary_dockerfile((context / 'Dockerfile.local').read_text(), dockerfile_path.read_text()) == dockerfile_receipt,
            'Boundary build source changed')
    image = runtime._json(['image', 'inspect', image_tag])[0]
    require((image['Config'].get('Labels') or {}).get(BOUNDARY_DOCKERFILE_LABEL) == dockerfile_receipt['generatedSha256'],
            'Boundary image Dockerfile provenance differs')
    require(all((image['Config'].get('Labels') or {}).get(key) == value for key, value in source['labels'].items()),
            'Test image source labels do not match the fixed BE context')
    volume = runtime._json(['volume', 'inspect', runtime.project + '_be-data'])[0]
    network = runtime._json(['network', 'inspect', runtime.project + '_default'])[0]
    require(network['Id'] == observed['networks'][network['Name']]['id']
            and volume['Name'] in observed['volumes'], 'New test store/network receipt mismatch')
    environment = test_environment(image, resolved['services']['be']['environment'],
                                   (context / 'Dockerfile.local').read_text())
    expected = expected_config(runtime.project, runtime.run_id, revision, attempt, image, environment, volume, network)
    name = expected['name']
    found = runtime._raw(['ps', '-a', '--no-trunc', '--filter', 'name=^/' + name + '$', '--format', '{{.ID}}'])
    require(found.returncode == 0 and not found.stdout.strip(), 'Test container name is not absent')
    env_path = safe_path(root / 'new-spring.env')
    require(all(re.fullmatch(r'[A-Z][A-Z0-9_]*', key) and isinstance(value, str)
                and not any(char in value for char in ('\n', '\r', '\0')) for key, value in environment.items()),
            'Unsafe new Spring environment serialization')
    descriptor = os.open(env_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        for key, value in sorted(environment.items()):
            stream.write(key + '=' + value + '\n')
    create = ['create', '--name', name, '--user', '0:0', '--workdir', '/workspace', '--entrypoint', '',
              '--cpus', '2', '--memory', '1280m', '--restart', 'no', '--network', expected['networkId'],
              '--mount', 'type=volume,source=' + expected['volumeName'] + ',target=/app/local-data',
              '--tmpfs', UNUSED_IMAGE_CACHE + ':' + UNUSED_CACHE_TMPFS,
              '--env-file', str(env_path),
              *[item for key, value in expected['labels'].items() for item in ('--label', key + '=' + value)],
              image['Id'], *COMMAND]
    current = runtime.observe(receipt['expected'])
    validate_current(receipt, current)
    require(stable_resources(current) == stable_resources(observed), 'Trial metadata changed before test creation')
    started = utc()
    write_new(root / 'creation-intent.json', {'expected': expected, 'beforeIds': before['containers'],
              'sourceDigest': source['sourceDigest'], 'runtimeImageId': images['be']['id'],
              'imageTag': image_tag, 'argv': create, 'startedAt': started})
    result = runtime._raw(create, timeout=180)
    command = runtime.record('boundary-test-create', [*runtime._prefix(), *create], result, started)
    require(result.returncode == 0, 'Boundary test container creation failed')
    identifier = result.stdout.strip()
    require(re.fullmatch(r'[0-9a-f]{64}', identifier), 'Create did not return one complete container ID')
    window = (started, command['finishedAt'])
    def inspect():
        actual = runtime._json(['inspect', identifier])[0]
        row = validate_container(actual, expected, container_id=identifier, created_window=window,
                                 before_ids=before['containers'])
        runtime_current = runtime.observe(receipt['expected'])
        validate_current(receipt, runtime_current)
        require(runtime_current['volumes'] == observed['volumes'] and runtime_current['networks'] == observed['networks'],
                'New test store/network metadata changed')
        require(all(item['state'] == 'running' if name in ('mysql', 'redis', 'ai') else item['state'] in ('created', 'exited')
                    for name, item in runtime_current['containers'].items()), 'Unexpected app/consumer start during boundary tests')
        return row
    created = inspect()
    require(created['state'] == 'created', 'New boundary test already started')
    write_new(root / 'creation.json', {'schema': 1, 'status': 'CREATED_VERIFIED', 'runId': runtime.run_id,
              'sourceDigest': source['sourceDigest'], 'runtimeImageId': images['be']['id'],
              'resources': created, 'expected': expected, 'command': command})
    start_attempted = False
    try:
        require(inspect()['state'] == 'created', 'Test changed before start')
        started = utc()
        write_new(root / 'start-intent.json', {'operation': 'start', 'id': identifier, 'runId': runtime.run_id,
                  'sourceDigest': source['sourceDigest'], 'startedAt': started})
        start_attempted = True
        result = runtime._raw(['start', identifier], timeout=60)
        runtime.record('boundary-test-start', [*runtime._prefix(), 'start', identifier], result, started)
        require(result.returncode == 0, 'Boundary test failed to start')
        inspect()
        started = utc()
        result = runtime._raw(['wait', identifier], timeout=900)
        runtime.record('boundary-test-wait', [*runtime._prefix(), 'wait', identifier], result, started)
        require(result.returncode == 0 and re.fullmatch(r'\d+\s*', result.stdout), 'Boundary test wait did not complete')
        completed = inspect()
        require(completed['state'] == 'exited', 'Boundary test did not exit')
        logs = runtime._raw(['logs', identifier], timeout=30)
        runtime.record('boundary-test-log', [*runtime._prefix(), 'logs', identifier], logs, utc())
        reports = []
        missing_reports = []
        for class_name in CLASSES:
            inspect()
            filename = 'TEST-' + class_name + '.xml'
            target = safe_path(root / filename)
            require(not target.exists(), 'JUnit evidence already exists')
            try:
                copied = runtime._raw(['cp', identifier + ':/workspace/build/test-results/test/' + filename, str(target)], timeout=30)
            finally:
                if target.exists():
                    safe_path(target).chmod(0o600)
            runtime.record('boundary-test-report', [*runtime._prefix(), 'cp', identifier + ':' + filename, str(target)], copied, utc())
            if copied.returncode != 0:
                missing_reports.append(class_name)
                continue
            require(target.is_file() and not target.is_symlink()
                    and target.stat().st_mode & 0o777 == 0o600 and target.stat().st_size <= 10 * 1024 * 1024,
                    'Private selected JUnit report unavailable or unsafe')
            reports.append(junit_summary(class_name, target.read_text(), runtime.redact))
        write_new(root / 'reports.json', {'classes': reports, 'missingClasses': missing_reports, 'rawXml': 'PRIVATE_MODE_0600_NOT_EXPORTED',
                  'scope': 'Counts and failed test names only; stdout and failure messages excluded'})
        outcome = junit_outcome(completed['exitCode'], result.stdout, reports, missing_reports, (logs.stdout or '') + (logs.stderr or ''))
        final_inventory = runtime.inventory()
        require(final_inventory['frozen'] == before['frozen'] and set(final_inventory['volumes']) == set(before['volumes'])
                and set(final_inventory['networks']) == set(before['networks'])
                and set(final_inventory['containers']) == set(before['containers']) | {identifier},
                'Unrelated resource metadata/inventory changed during boundary tests')
        summary = {**outcome, 'runId': runtime.run_id, 'revision': revision, 'attemptId': attempt,
                   'sourceDigest': source['sourceDigest'], 'runtimeImageId': images['be']['id'],
                   'testImageId': image['Id'], 'containerId': identifier, 'exitCode': completed['exitCode'],
                   'classes': reports, 'testCount': sum(row['tests'] for row in reports), 'containerRemoved': False, 'frozenMetadataUnchanged': True}
        write_new(root / 'result.json', summary)
        require(outcome['status'] == 'PASS', 'Boundary Gradle exit ' + str(completed['exitCode']) + '; ' + outcome['executionPhase']
                + '; JUnit reports missing ' + str(len(missing_reports)) + '; preserved logs and available reports')
        return summary
    except BaseException as failure:
        write_new(root / 'failure.json', {'status': 'FAIL', 'runId': runtime.run_id, 'containerId': identifier,
                  'errorType': type(failure).__name__, 'sourceDigest': source['sourceDigest'], 'finishedAt': utc()})
        raise
    finally:
        if start_attempted:
            row = inspect()
            if row['state'] == 'running':
                started = utc()
                write_new(root / 'stop-intent.json', {'operation': 'stop', 'id': identifier, 'runId': runtime.run_id,
                          'sourceDigest': source['sourceDigest'], 'startedAt': started})
                stopped = runtime._raw(['stop', '--time', '20', identifier], timeout=45)
                runtime.record('boundary-test-stop', [*runtime._prefix(), 'stop', '--time', '20', identifier], stopped, started)
                require(stopped.returncode == 0 and inspect()['state'] == 'exited', 'Boundary test cleanup failed')
