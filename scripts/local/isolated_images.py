"""Finite, offline image context preparation for the isolated evidence trial.

No Git, Docker, network, environment, or credential discovery is performed here.
The caller supplies the Git-tracked path inventory. Context creation is exclusive;
an existing context is evidence to inspect, never an output to overwrite.
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat


class ContextPolicyError(ValueError):
    pass


COMPONENT_ROOTS = {
    'be': 'be', 'ai': 'ai', 'python-service': 'python-service',
    'web': 'fe-web', 'chroma': 'scripts/local/chroma',
}
EXACT = {
    'be': {'Dockerfile.local', '.dockerignore', 'build.gradle', 'settings.gradle', 'gradle.lockfile'},
    'ai': {'Dockerfile.local', '.dockerignore', 'requirements.local.lock.txt'},
    'python-service': {'Dockerfile.local', '.dockerignore', 'requirements.local.lock.txt', 'main.py'},
    'web': {'Dockerfile.local', '.dockerignore', 'package.json', 'package-lock.json', 'index.html',
            'nginx.local.conf', 'vite.config.ts', 'vite.showcase.config.ts', 'vite-env.d.ts',
            'tsconfig.json', 'tsconfig.app.json', 'tsconfig.node.json',
            'scripts/showcase-graph.mjs', 'scripts/showcase-paths.mjs', 'local-env/README.md'},
    'chroma': {'Dockerfile.local'},
}
EXTENSIONS = {
    'be': {'.java', '.yml', '.sql', '.json', '.xml', '.html'},
    'ai': {'.py'}, 'python-service': {'.py'},
    'web': {'.ts', '.tsx', '.css', '.png', '.jpg', '.jpeg', '.svg', '.woff', '.woff2', '.txt'},
    'chroma': set(),
}
TOKEN_PATTERNS = {
    'private_key_header': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'aws_access_key': re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'google_key': re.compile(r'\bAIza[A-Za-z0-9_-]{30,}\b'),
    'github_token': re.compile(r'\b(?:ghp_|github_pat_)[A-Za-z0-9_]{20,}\b'),
    'provider_token': re.compile(r'\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}\b'),
}


def require(condition, message):
    if not condition:
        raise ContextPolicyError(message)


def safe_path(path):
    """Inspect ancestors before opening; do not follow symlinks or hard-linked files."""
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts, 'An absolute path without traversal is required')
    for candidate in (path, *path.parents):
        try:
            metadata = candidate.lstat()
        except FileNotFoundError:
            continue
        require(not stat.S_ISLNK(metadata.st_mode), 'Symbolic links are forbidden')
        if stat.S_ISREG(metadata.st_mode):
            require(metadata.st_nlink == 1, 'Hard-linked files are forbidden')
    return path


def forbidden(parts):
    return any(part in {'.git', '.local', '.DS_Store', '.aws', '.ssh', 'node_modules', '__pycache__'}
               or part.startswith('.env') or part.endswith(('.pem', '.key'))
               or 'credentials' in part.lower() for part in parts)


def selected_paths(component, tracked_paths):
    require(component in COMPONENT_ROOTS, 'Unknown image component')
    require(isinstance(tracked_paths, (list, tuple)) and all(isinstance(p, str) for p in tracked_paths),
            'An explicit Git-tracked path list is required')
    require(len(set(tracked_paths)) == len(tracked_paths), 'Duplicate tracked paths are forbidden')
    prefix = COMPONENT_ROOTS[component] + '/'
    selected = {}
    for source in tracked_paths:
        require(source and '\\' not in source and '\x00' not in source and '\n' not in source
                and '\r' not in source and not source.startswith('/')
                and '..' not in PurePosixPath(source).parts, 'Invalid tracked path')
        if not source.startswith(prefix) or forbidden(PurePosixPath(source).parts):
            continue
        relative = source[len(prefix):]
        require(str(PurePosixPath(relative)) == relative, 'Noncanonical tracked path')
        tree = ('src/',) if component in ('be', 'web') else ('app/', 'tests/')
        if relative in EXACT[component] or (relative.startswith(tree)
                and PurePosixPath(relative).suffix in EXTENSIONS[component]):
            selected[relative] = source
    require(EXACT[component].issubset(selected), 'A required reviewed build input is missing')
    if component in ('be', 'web'):
        require(any(p.startswith('src/') for p in selected), 'Source tree is missing')
    if component in ('ai', 'python-service'):
        require(all(any(p.startswith(tree) for p in selected) for tree in ('app/', 'tests/')),
                'Application or test source tree is missing')
    return dict(sorted(selected.items()))


def read_source(repo, source):
    filename = safe_path(repo / source)
    require(filename.is_file(), 'A selected source is not a regular file')
    descriptor = os.open(filename, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(descriptor, 'rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1, 'Unsafe source file')
        data = stream.read()
        after = os.fstat(stream.fileno())
    require((before.st_ino, before.st_size, before.st_mtime_ns) ==
            (after.st_ino, after.st_size, after.st_mtime_ns), 'Source changed while reading')
    return data


def context_bytes(repo, component, tracked_paths):
    repo = safe_path(repo)
    require(repo.is_dir(), 'Repository directory is missing')
    return {relative: read_source(repo, source)
            for relative, source in selected_paths(component, tracked_paths).items()}


def select_context(repo, component, tracked_paths):
    """Return context-relative path -> current source SHA-256; read selected files only."""
    return {path: hashlib.sha256(data).hexdigest()
            for path, data in context_bytes(repo, component, tracked_paths).items()}


def source_digest(mapping):
    require(isinstance(mapping, dict) and mapping, 'A nonempty source mapping is required')
    require(all(isinstance(path, str) and path and not path.startswith('/')
                and not any(character in path for character in ('\\', '\x00', '\n', '\r'))
                and str(PurePosixPath(path)) == path and '..' not in PurePosixPath(path).parts
                and not forbidden(PurePosixPath(path).parts)
                and isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value)
                for path, value in mapping.items()), 'Invalid source digest mapping')
    canonical = json.dumps(mapping, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(canonical).hexdigest()


def allowed_candidate(component, path, category, line, token):
    if component == 'ai' and path == 'tests/test_live_provider.py' and category == 'provider_token':
        if ('self.key_path.write_text(' in line and 'OPENAI_API_KEY=' in line
                and 'fixture' in token.lower()
                and re.search(r'not[-_]?(?:a[-_]?)?real', token, re.I)):
            return 'Explicit not-real fixture token in the reviewed mock-provider test'
    parser_paths = {'src/main/java/A704/DODREAM/file/service/CloudFrontService.java',
                    'src/main/java/A704/DODREAM/file/service/PdfService.java'}
    if component == 'be' and path in parser_paths and category == 'private_key_header':
        if re.search(r'\.(?:replace|contains)\("-----BEGIN PRIVATE KEY-----"', line):
            return 'Reviewed PEM delimiter parsing code; no private key body'
    return None


def scan_bytes(component, sources):
    candidates, allowed = [], []
    text_count, binary_count = 0, 0
    for path, data in sources.items():
        try:
            text = data.decode('utf-8')
        except UnicodeDecodeError:
            binary_count += 1
            continue
        text_count += 1
        for number, line in enumerate(text.splitlines(), 1):
            for category, pattern in TOKEN_PATTERNS.items():
                for match in pattern.finditer(line):
                    reason = allowed_candidate(component, path, category, line, match.group())
                    finding = {'path': path, 'line': number, 'category': category}
                    if reason:
                        allowed.append({**finding, 'reason': reason})
                    else:
                        candidates.append(finding)
    return {'scope': 'Selected source text: known token and private-key formats only; not image/dependency history',
            'textFiles': text_count, 'binaryFilesNotTextScanned': binary_count,
            'candidates': candidates, 'allowedFindings': allowed}


def scan_context(repo, component, tracked_paths):
    """Return bounded candidate metadata, never matched values or source lines."""
    return scan_bytes(component, context_bytes(repo, component, tracked_paths))


def materialize_context(repo, trialroot, component, tracked_paths, *, revision=None):
    """Exclusively create one trial context after all selected input validation."""
    repo, trialroot = safe_path(repo), safe_path(trialroot)
    require(trialroot.parent == repo / '.local/isolated'
            and re.fullmatch(r'evidence-portability-\d{8}', trialroot.name), 'Unknown trial root')
    if revision is not None:
        require(component == 'be' and isinstance(revision, str) and
                re.fullmatch(r'\d{3}-(?:observation|fixed)-\d{2}', revision), 'Only explicit BE revision contexts allowed')
    destination = safe_path((trialroot / 'revisions' / revision if revision else trialroot) / 'contexts' / component)
    require(not destination.exists(), 'Context already exists; no overwrite or adoption')
    sources = context_bytes(repo, component, tracked_paths)
    scan = scan_bytes(component, sources)
    require(not scan['candidates'], 'Secret candidate in selected build source; inspect bounded scan metadata')
    mapping = {path: hashlib.sha256(data).hexdigest() for path, data in sources.items()}
    digest = source_digest(mapping)
    # No deletion or rollback: an interrupted partial context remains distinguishable evidence.
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    safe_path(destination.parent)
    destination.mkdir(mode=0o700)
    for relative, data in sources.items():
        target = destination / relative
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        safe_path(target)
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
    return {
        'schema': 1, 'component': component, 'contextPath': str(destination), 'sourceDigest': digest,
        'sourceFiles': [{'source': COMPONENT_ROOTS[component] + '/' + path, 'path': path,
                         'sha256': mapping[path], 'bytes': len(data)} for path, data in sources.items()],
        'labels': {'io.dodream.isolated.component': component, 'io.dodream.isolated.source-digest': digest},
        'secretScan': scan, 'imageId': None, 'buildExecuted': False,
    }


def record_mapping(record):
    """Validate bounded source metadata without opening any listed path."""
    require(isinstance(record, dict) and record.get('schema') == 1, 'Invalid context record')
    component = record.get('component')
    require(component in COMPONENT_ROOTS, 'Unknown recorded image component')
    rows = record.get('sourceFiles')
    require(isinstance(rows, list) and rows, 'Source file receipt is missing')
    require(all(isinstance(row, dict) and set(row) == {'source', 'path', 'sha256', 'bytes'}
                and isinstance(row['source'], str) and isinstance(row['path'], str)
                and isinstance(row['bytes'], int) and row['bytes'] >= 0 for row in rows),
            'Malformed source file receipt')
    selected = selected_paths(component, [row['source'] for row in rows])
    require(len(rows) == len(selected) and all(selected.get(row['path']) == row['source'] for row in rows),
            'Recorded source is outside the reviewed context')
    mapping = {row['path']: row['sha256'] for row in rows}
    require(len(mapping) == len(rows) and source_digest(mapping) == record.get('sourceDigest'),
            'Source manifest digest mismatch')
    return mapping


def validate_materialized_context(record):
    """Verify exact copied path set and bytes. Unknown paths are never opened."""
    mapping = record_mapping(record)
    component = record['component']
    destination = safe_path(record.get('contextPath', ''))
    contextroot = destination.parent.parent
    if contextroot.parent.name == 'revisions':
        require(component == 'be' and re.fullmatch(r'\d{3}-(?:observation|fixed)-\d{2}', contextroot.name),
                'Unknown BE revision context')
        contextroot = contextroot.parent.parent
    require(destination.name == component and destination.parent.name == 'contexts'
            and re.fullmatch(r'evidence-portability-\d{8}', contextroot.name)
            and contextroot.parent.name == 'isolated'
            and contextroot.parent.parent.name == '.local', 'Unknown context destination')
    require(destination.is_dir(), 'Materialized context is missing')
    directories = {str(parent) for path in mapping for parent in PurePosixPath(path).parents if str(parent) != '.'}
    seen = set()
    def walk(directory, prefix=''):
        with os.scandir(directory) as entries:
            for entry in entries:
                relative = prefix + entry.name
                # Reject .DS_Store, unexpected secrets and other unknown names before stat/read.
                require(relative in mapping or relative in directories, 'Unexpected materialized context path')
                metadata = entry.stat(follow_symlinks=False)
                require(not stat.S_ISLNK(metadata.st_mode), 'Materialized context symlink')
                if relative in directories:
                    require(stat.S_ISDIR(metadata.st_mode), 'Expected context directory')
                    walk(Path(entry.path), relative + '/')
                else:
                    require(stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1, 'Unsafe context file')
                    seen.add(relative)
    walk(destination)
    require(seen == set(mapping), 'Materialized context file set mismatch')
    sizes = {row['path']: row['bytes'] for row in record['sourceFiles']}
    for relative, expected in mapping.items():
        data = read_source(destination, relative)
        require(len(data) == sizes[relative] and hashlib.sha256(data).hexdigest() == expected,
                'Materialized context bytes changed')
    return {'status': 'PASS', 'component': component, 'sourceDigest': record['sourceDigest'], 'files': len(mapping)}


def validate_repo_source(repo, record):
    """Check current bytes of receipted files; caller separately supplies fresh Git inventory."""
    mapping = record_mapping(record)
    repo = safe_path(repo)
    for row in record['sourceFiles']:
        data = read_source(repo, row['source'])
        require(len(data) == row['bytes'] and hashlib.sha256(data).hexdigest() == mapping[row['path']],
                'Current source differs from image build receipt')
    return {'status': 'PASS', 'component': record['component'], 'sourceDigest': record['sourceDigest'],
            'files': len(mapping), 'scope': 'Receipted source paths only; compare fresh select_context for added tracked files'}


def image_config_view(config):
    require(isinstance(config, dict), 'Image config metadata is required')
    def argv(name):
        value = config.get(name) or []
        require(isinstance(value, list) and len(value) <= 64
                and all(isinstance(item, str) and len(item) <= 1024
                        and not any(char in item for char in ('\x00', '\n', '\r')) for item in value),
                'Invalid image command metadata')
        return value
    environment = config.get('Env') or []
    require(isinstance(environment, list) and len(environment) <= 128
            and all(isinstance(item, str) and '=' in item and not any(c in item for c in ('\x00', '\n', '\r'))
                    for item in environment), 'Invalid image environment metadata')
    pairs = [item.split('=', 1) for item in environment]
    require(len({key for key, _ in pairs}) == len(pairs), 'Duplicate image environment keys')
    variables = dict(pairs)
    unsafe = re.compile(r'(?:OPENAI|ANTHROPIC|AWS|AZURE|GOOGLE|GEMINI|GMS|VAULT|CLOVA|FIREBASE|SENTRY|HUGGING_FACE|HF_TOKEN|LANGSMITH|LANGCHAIN_API|DODREAM|LOCAL_TEACHER|LOCAL_STUDENT|JWT_SECRET|MYSQL_PASSWORD|MYSQL_ROOT_PASSWORD|DATABASE_URL|CELERY_BROKER_URL|RAG_DATABASE_URL)', re.I)
    require(not any(unsafe.match(key) or key.upper().endswith(('_API_KEY', '_TOKEN', '_SECRET', '_PASSWORD', '_CREDENTIALS'))
                    for key in variables), 'Ambient provider or runtime credentials in image environment')
    require(not config.get('OnBuild'), 'Unreviewed image OnBuild hook')
    volumes = config.get('Volumes') or {}
    require(isinstance(volumes, dict), 'Invalid image volume metadata')
    return {'Cmd': argv('Cmd'), 'Entrypoint': argv('Entrypoint'), 'Env': variables, 'Volumes': volumes}


def validate_image_config(component, image_config, *, expected_base_config=None):
    """Validate supplied image metadata only; base provenance must be checked by caller.

    For inherited configurations, the caller must supply independently reviewed
    base-image metadata, never the new image itself as its own expected value.
    """
    require(component in {*COMPONENT_ROOTS, 'mysql', 'redis'}, 'Unknown image component')
    observed = image_config_view(image_config)
    known = {
        'be': ([], ['java', '-jar', '/app/app.jar']),
        'ai': (['uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', '8000', '--no-access-log'], []),
        'python-service': (['uvicorn', 'main:app', '--host', '0.0.0.0', '--port', '8000', '--no-access-log'], []),
    }
    if component in known:
        command, entrypoint = known[component]
        require(observed['Cmd'] == command and observed['Entrypoint'] == entrypoint,
                'Image command differs from reviewed Dockerfile')
        require(not observed['Volumes'], 'Unplanned application-image volumes')
        if component == 'be':
            permitted = {'PATH', 'JAVA_HOME', 'LANG', 'LANGUAGE', 'LC_ALL', 'JAVA_VERSION'}
            fixed = {}
        else:
            permitted = {'PATH', 'LANG', 'GPG_KEY', 'PYTHON_VERSION', 'PYTHON_SHA256', 'PYTHON_PIP_VERSION',
                         'PYTHON_SETUPTOOLS_VERSION', 'PYTHON_GET_PIP_URL', 'PYTHON_GET_PIP_SHA256'}
            fixed = {'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUNBUFFERED': '1',
                     'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1'}
            if component == 'ai':
                fixed['LANGCHAIN_TRACING_V2'] = 'false'
        require(set(observed['Env']) <= permitted | set(fixed), 'Unreviewed application-image environment key')
        require(all(observed['Env'].get(key) == value for key, value in fixed.items()),
                'Offline application-image defaults are missing or changed')
    else:
        require(expected_base_config is not None, 'Independently reviewed base-image config is required')
        expected = image_config_view(expected_base_config)
        require(observed == expected, 'Inherited base-image configuration changed')
        require(observed['Cmd'] or observed['Entrypoint'], 'Base-image execution command is missing')
        if component == 'web':
            require(observed['Cmd'] == ['nginx', '-g', 'daemon off;']
                    and observed['Entrypoint'] == ['/docker-entrypoint.sh'], 'Unknown nginx base command')
    return {'status': 'PASS', 'component': component, 'environmentKeys': sorted(observed['Env']),
            'command': observed['Cmd'], 'entrypoint': observed['Entrypoint'],
            'scope': 'Supplied image config; not complete image layer/history inspection'}
