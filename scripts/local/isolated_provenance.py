"""Pure creation/operation policy for isolated_trial; this module never executes.

Metadata is deliberately bounded and contains no environment values. ``envHash``
is the caller's SHA-256 of the canonical, explicitly generated environment.
Expected mounts use type/name/destination/rw for volumes, or
type/source/destination/rw for read-only binds. Observed volume mounts also carry
the Docker source path. The caller owns source/manifest digests and command logs.
This policy proves correspondence to supplied metadata, not metadata authenticity.
"""
import copy
from datetime import datetime, timezone
from pathlib import PurePosixPath
import re
from uuid import UUID


PROJECT_LABEL = 'com.docker.compose.project'
RUN_LABEL = 'io.dodream.trial.run-id'
CONTAINER_KEYS = {'id', 'image', 'created', 'state', 'startedAt', 'project', 'service',
                  'runId', 'command', 'entrypoint', 'envHash', 'mounts', 'networks', 'ports'}
MUTABLE_KEYS = {'state', 'startedAt'}
VOLUME_KEYS = {'name', 'driver', 'options', 'created', 'labels'}
NETWORK_KEYS = VOLUME_KEYS | {'id', 'internal'}


class ProvenanceError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ProvenanceError(message)


def _keys(value, keys, label):
    require(isinstance(value, dict) and set(value) == set(keys), f'Invalid {label} fields')


def _identifier(value, label, image=False):
    pattern = r'sha256:[0-9a-f]{64}' if image else r'[0-9a-f]{64}'
    require(isinstance(value, str) and re.fullmatch(pattern, value), f'Full immutable {label} required')


def _timestamp(value):
    require(isinstance(value, str), 'Timestamp must be an ISO string')
    match = re.fullmatch(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})', value)
    require(match is not None, 'Strict timezone-aware ISO timestamp required')
    # Docker uses nanoseconds; Python 3.9 accepts only microsecond fractions.
    # Truncate for comparison only, keeping original metadata in the receipt.
    fraction = ('.' + match[2][:6].ljust(6, '0')) if match[2] else ''
    normalized = match[1] + fraction + ('+00:00' if match[3] == 'Z' else match[3])
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ProvenanceError('Invalid ISO timestamp') from error
    require(parsed.tzinfo is not None, 'Timezone-aware timestamp required')
    return parsed.astimezone(timezone.utc)


def _never_started(value):
    return isinstance(value, str) and bool(re.fullmatch(r'0001-01-01T00:00:00(?:\.0+)?(?:Z|\+00:00)', value))


def _created_in_window(value, start, end):
    moment = _timestamp(value)
    # Docker volumes/networks may only expose whole-second timestamps.
    require(start.replace(microsecond=0) <= moment <= end, 'Creation time outside recorded command window')


def _names(values, label):
    require(isinstance(values, (list, tuple, set)) and all(isinstance(v, str) and v for v in values),
            f'Explicit {label} list required')
    require(len(values) == len(set(values)), f'Duplicate {label}')
    return set(values)


def _labels(labels, project, run_id):
    require(isinstance(labels, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in labels.items()),
            'Invalid non-secret resource labels')
    require(labels.get(PROJECT_LABEL) == project and labels.get(RUN_LABEL) == run_id,
            'Resource lacks matching project and creation-run labels')


def _mounts(actual, expected, volume_names):
    require(isinstance(actual, list) and isinstance(expected, list), 'Explicit mount lists required')
    require(len(actual) == len(expected), 'Unexpected or missing mount')
    actual_by_target = {}
    for mount in actual:
        require(isinstance(mount, dict) and isinstance(mount.get('destination'), str), 'Invalid observed mount')
        destination = mount['destination']
        require(destination not in actual_by_target, 'Duplicate mount destination')
        actual_by_target[destination] = mount
    expected_targets = set()
    for wanted in expected:
        require(isinstance(wanted, dict), 'Invalid expected mount')
        mount_type = wanted.get('type')
        require(mount_type in ('volume', 'bind'), 'Unsupported mount type')
        fields = {'type', 'destination', 'rw', 'name' if mount_type == 'volume' else 'source'}
        _keys(wanted, fields, 'expected mount')
        destination = wanted['destination']
        require(isinstance(destination, str) and destination.startswith('/') and '..' not in PurePosixPath(destination).parts,
                'Explicit absolute mount destination required')
        require(destination not in expected_targets, 'Duplicate expected mount destination')
        expected_targets.add(destination)
        require(type(wanted['rw']) is bool, 'Mount access must be explicit')
        actual_mount = actual_by_target.get(destination)
        require(actual_mount is not None, 'Expected mount absent')
        if mount_type == 'volume':
            _keys(actual_mount, fields | {'source'}, 'observed volume mount')
            require(wanted['name'] in volume_names, 'Mount references an unplanned volume')
            source = actual_mount['source']
            require(isinstance(source, str) and source.startswith('/') and '..' not in PurePosixPath(source).parts and
                    PurePosixPath(source).parts[-3:] == ('volumes', wanted['name'], '_data'),
                    'Volume source does not correspond to its new local volume')
        else:
            _keys(actual_mount, fields, 'observed bind mount')
            require(wanted['rw'] is False, 'Source binds must be read-only')
            source = wanted['source']
            require(isinstance(source, str) and source.startswith('/') and '..' not in PurePosixPath(source).parts and
                    source != '/var/run/docker.sock', 'Unsafe bind source')
        require(all(actual_mount[k] == wanted[k] for k in fields), 'Mount differs from approved configuration')
    require(set(actual_by_target) == expected_targets, 'Unexpected mount destinations')


def validate_created(before, observed, expected, run_id, started_at, finished_at):
    """Validate complete first creation, returning a receipt of exact observations.

    ``expected`` = {project, services: {name: {image, command, entrypoint,
    envHash, mounts, networkNames, ports}}, volumes: [effective names],
    networks: {effective name: {driver, internal}}}. This only accepts first
    creation, never adoption or an incomplete/retried create. A later operation
    must call validate_current with fresh observations.
    """
    _keys(before, {'containers', 'volumes', 'networks'}, 'before inventory')
    _keys(observed, {'containers', 'volumes', 'networks'}, 'observed inventory')
    _keys(expected, {'project', 'services', 'volumes', 'networks'}, 'expected configuration')
    try:
        require(str(UUID(run_id)) == run_id, 'Canonical creation run UUID required')
    except (ValueError, TypeError, AttributeError) as error:
        raise ProvenanceError('Canonical creation run UUID required') from error
    start, end = _timestamp(started_at), _timestamp(finished_at)
    require(start <= end, 'Invalid creation interval')
    project = expected['project']
    require(isinstance(project, str) and re.fullmatch(r'dodream-evidence-\d{8}', project), 'Finite isolated project required')
    require(isinstance(expected['services'], dict) and expected['services'], 'Explicit expected services required')
    volumes = _names(expected['volumes'], 'expected volumes')
    require(isinstance(expected['networks'], dict) and expected['networks'], 'Explicit expected networks required')
    networks = set(expected['networks'])
    require(all(name.startswith(project + '_') for name in volumes | networks), 'Resource outside isolated namespace')
    for field in ('containers', 'volumes', 'networks'):
        require(isinstance(observed[field], dict), 'Observed resources must be keyed objects')
    require(set(observed['containers']) == set(expected['services']), 'Incomplete or unexpected created services')
    require(set(observed['volumes']) == volumes, 'Incomplete or unexpected created volumes')
    require(set(observed['networks']) == networks, 'Incomplete or unexpected created networks')
    before_ids = _names(before['containers'], 'preexisting IDs')
    before_volumes = _names(before['volumes'], 'preexisting volumes')
    before_networks = _names(before['networks'], 'preexisting networks')
    require(not volumes & before_volumes and not networks & before_networks, 'Created names existed before this run')
    for name, volume in observed['volumes'].items():
        _keys(volume, VOLUME_KEYS, 'volume metadata')
        require(volume['name'] == name and volume['driver'] == 'local' and volume['options'] in ({}, None),
                'Volume driver or options can reference existing storage')
        _labels(volume['labels'], project, run_id)
        _created_in_window(volume['created'], start, end)
    network_ids = set()
    for name, network in observed['networks'].items():
        _keys(network, NETWORK_KEYS, 'network metadata')
        _keys(expected['networks'][name], {'driver', 'internal'}, 'expected network')
        _identifier(network['id'], 'network ID')
        require(network['id'] not in network_ids, 'Duplicate network ID')
        network_ids.add(network['id'])
        require(network['name'] == name and network['driver'] == 'bridge' and network['options'] in ({}, None),
                'Unexpected network driver/options')
        require(type(network['internal']) is bool and
                all(network[key] == expected['networks'][name][key] for key in ('driver', 'internal')),
                'Network differs from reviewed isolation configuration')
        _labels(network['labels'], project, run_id)
        _created_in_window(network['created'], start, end)
    container_ids = set()
    for service, row in observed['containers'].items():
        _keys(row, CONTAINER_KEYS, 'container metadata')
        wanted = expected['services'][service]
        _keys(wanted, {'image', 'command', 'entrypoint', 'envHash', 'mounts', 'networkNames', 'ports'}, 'expected service')
        _identifier(row['id'], 'container ID')
        _identifier(row['image'], 'image ID', image=True)
        require(row['id'] not in before_ids and row['id'] not in container_ids, 'Existing or duplicate container ID')
        container_ids.add(row['id'])
        require(row['project'] == project and row['service'] == service and row['runId'] == run_id,
                'Container creation ownership differs')
        require(row['state'] == 'created' and _never_started(row['startedAt']), 'Created container has already been started')
        _created_in_window(row['created'], start, end)
        for key in ('command', 'entrypoint'):
            require(isinstance(row[key], list) and all(isinstance(v, str) for v in row[key]), 'Explicit command/entrypoint required')
        require(isinstance(row['envHash'], str) and re.fullmatch(r'[0-9a-f]{64}', row['envHash']), 'Environment digest required')
        require(all(row[key] == wanted[key] for key in ('image', 'command', 'entrypoint', 'envHash', 'ports')),
                'Image, command, environment or ports differ from the approved service')
        allowed_networks = _names(wanted['networkNames'], 'service networks')
        require(allowed_networks <= networks and isinstance(row['networks'], dict) and set(row['networks']) == allowed_networks,
                'Container has an unexpected network reference')
        # Docker create records configured network names before the first start
        # attaches endpoints. The separately created network IDs are already
        # proven fresh above; an empty ID is valid only for never-started create.
        require(all(row['networks'][name] == observed['networks'][name]['id'] or
                    (row['networks'][name] == '' and row['state'] == 'created' and _never_started(row['startedAt']))
                    for name in allowed_networks),
                'Container is attached to an old or mismatched network ID')
        _mounts(row['mounts'], wanted['mounts'], volumes)
    saved_expected = copy.deepcopy(expected)
    saved_expected['volumes'] = sorted(volumes)
    for service in saved_expected['services'].values():
        service['networkNames'] = sorted(service['networkNames'])
    return {'schema': 1, 'status': 'CREATED_VERIFIED', 'runId': run_id, 'project': project,
            'creationStartedAt': started_at, 'creationFinishedAt': finished_at,
            'before': {key: sorted(value) for key, value in before.items()},
            'expected': saved_expected, 'resources': copy.deepcopy(observed)}


def validate_current(receipt, observed):
    """Recheck immutable properties against a complete, verified creation receipt."""
    if receipt.get('schema') == 2:
        _keys(receipt, {'schema', 'status', 'previous', 'runId', 'project', 'before',
                        'expected', 'resources', 'revisionStartedAt', 'revisionFinishedAt'}, 'revision receipt')
        checked = validate_recreated(receipt['previous'], receipt['before'], receipt['resources'],
                                     receipt['expected'], receipt['revisionStartedAt'], receipt['revisionFinishedAt'])
        require(checked == receipt, 'Revision receipt does not match its preserved evidence')
        return _validate_observed_current(receipt, observed)
    _keys(receipt, {'schema', 'status', 'runId', 'project', 'creationStartedAt', 'creationFinishedAt',
                    'before', 'expected', 'resources'}, 'creation receipt')
    require(receipt['schema'] == 1 and receipt['status'] == 'CREATED_VERIFIED', 'Incomplete or unknown creation receipt')
    require(receipt['project'] == receipt['expected']['project'], 'Receipt project mismatch')
    # A receipt file or status marker alone is insufficient: revalidate its evidence.
    validate_created(receipt['before'], receipt['resources'], receipt['expected'], receipt['runId'],
                     receipt['creationStartedAt'], receipt['creationFinishedAt'])
    return _validate_observed_current(receipt, observed)


def _validate_observed_current(receipt, observed):
    _keys(observed, {'containers', 'volumes', 'networks'}, 'current inventory')
    for resource in ('volumes', 'networks'):
        require(observed[resource] == receipt['resources'][resource], f'Current {resource} differ from creation evidence')
    require(isinstance(observed['containers'], dict) and
            set(observed['containers']) == set(receipt['resources']['containers']), 'Current service set differs')
    for service, row in observed['containers'].items():
        _keys(row, CONTAINER_KEYS, 'current container metadata')
        require(row['state'] in ('created', 'running', 'paused', 'exited'), 'Unknown, restarting or dead container state')
        started = _timestamp(row['startedAt'])
        if row['state'] == 'created':
            require(_never_started(row['startedAt']), 'Created state cannot hide an earlier start')
        else:
            require(started >= _timestamp(row['created']), 'Started container lacks a valid start time')
        saved = receipt['resources']['containers'][service]
        require(all(row[key] == saved[key] for key in CONTAINER_KEYS - MUTABLE_KEYS - {'networks', 'mounts'}),
                'Current container differs from its verified creation evidence')
        _mounts(row['mounts'], receipt['expected']['services'][service]['mounts'], set(receipt['resources']['volumes']))
        require(sorted(row['mounts'], key=lambda mount: mount['destination']) ==
                sorted(saved['mounts'], key=lambda mount: mount['destination']),
                'Current mount records differ from creation evidence')
        require(isinstance(row['networks'], dict) and set(row['networks']) == set(saved['networks']),
                'Current container network names differ from creation evidence')
        require(all(network_id == receipt['resources']['networks'][name]['id'] or
                    (network_id == '' and row['state'] == 'created' and _never_started(row['startedAt']))
                    for name, network_id in row['networks'].items()),
                'Current network ID is missing after start or differs from the new network')


BE_REVISION_SERVICES = ('be', 'be-auth-short', 'be-student-short')


def validate_recreated(previous, before, observed, expected, started_at, finished_at):
    """Validate a stopped, BE-only image revision without adopting storage or IDs.

    This is not a fresh-creation receipt: original storage timestamps, old IDs and
    the complete prior receipt remain attached and are recursively revalidated.
    """
    validate_current(previous, before)
    require(all(row['state'] in ('created', 'exited') for row in before['containers'].values()),
            'BE revision requires every trial service stopped or never started')
    require(set(BE_REVISION_SERVICES) <= set(before['containers']), 'All three dedicated BE services required')
    _keys(expected, {'project', 'services', 'volumes', 'networks'}, 'revision expected configuration')
    require(set(expected['services']) == set(previous['expected']['services']), 'Revision service set changed')
    wanted = copy.deepcopy(previous['expected'])
    image_ids = {expected['services'][name]['image'] for name in BE_REVISION_SERVICES}
    require(len(image_ids) == 1, 'One verified BE image must serve all BE variants')
    image_id = next(iter(image_ids)); _identifier(image_id, 'revision image ID', image=True)
    require(all(image_id != wanted['services'][name]['image'] for name in BE_REVISION_SERVICES),
            'Revision requires a different immutable BE image')
    for name in BE_REVISION_SERVICES:
        wanted['services'][name]['image'] = image_id
    require(expected == wanted, 'Only the BE image may change in a revision')
    _keys(observed, {'containers', 'volumes', 'networks'}, 'revision observations')
    require(set(observed['containers']) == set(before['containers']), 'Revision service set changed')
    require(all(observed[k] == before[k] for k in ('volumes', 'networks')),
            'Revision must preserve every trial volume and network')
    start, end = _timestamp(started_at), _timestamp(finished_at)
    require(start <= end, 'Invalid revision interval')
    forbidden_ids = {row['id'] for row in before['containers'].values()}
    ancestor = previous
    while ancestor.get('schema') == 2:
        forbidden_ids.update(row['id'] for row in ancestor['resources']['containers'].values())
        ancestor = ancestor['previous']
    forbidden_ids.update(ancestor['before']['containers'])
    forbidden_ids.update(row['id'] for row in ancestor['resources']['containers'].values())
    new_ids = set()
    for name, row in observed['containers'].items():
        old = before['containers'][name]
        if name not in BE_REVISION_SERVICES:
            # Docker's mount order is unspecified; no other field may change.
            left, right = copy.deepcopy(row), copy.deepcopy(old)
            for item in (left, right): item['mounts'] = sorted(item['mounts'], key=lambda m:m['destination'])
            require(left == right, 'Unselected service changed during BE revision')
            continue
        _keys(row, CONTAINER_KEYS, 'recreated container')
        _identifier(row['id'], 'recreated container ID')
        require(row['id'] not in forbidden_ids | new_ids, 'Existing, reused or duplicate revision container ID')
        new_ids.add(row['id'])
        require(row['state'] == 'created' and _never_started(row['startedAt']), 'Recreated service already started')
        _created_in_window(row['created'], start, end)
        require(row['image'] == image_id, 'Wrong recreated BE image')
        require(all(row[key] == old[key] for key in CONTAINER_KEYS -
                    {'id', 'image', 'created', 'state', 'startedAt', 'networks', 'mounts'}),
                'BE revision changed command, environment, ownership or ports')
        _mounts(row['mounts'], expected['services'][name]['mounts'], set(before['volumes']))
        require(sorted(row['mounts'], key=lambda m:m['destination']) == sorted(old['mounts'], key=lambda m:m['destination']),
                'BE revision changed an existing mount')
        require(set(row['networks']) == set(old['networks']) and all(value in ('', observed['networks'][key]['id'])
                for key, value in row['networks'].items()), 'BE revision changed network identity')
    return {'schema': 2, 'status': 'BE_RECREATED_VERIFIED', 'previous': copy.deepcopy(previous),
            'runId': previous['runId'], 'project': previous['project'], 'before': copy.deepcopy(before),
            'expected': copy.deepcopy(expected), 'resources': copy.deepcopy(observed),
            'revisionStartedAt': started_at, 'revisionFinishedAt': finished_at}


def operation_ids(receipt, observed, operation, services, allowed_services, started_services):
    """Return only exact freshly revalidated IDs; never executes any command.

    The runner must persist start intent before issuing it and record actual starts.
    Error/signal cleanup passes only that run's started service set. This function
    cannot prevent an unrelated caller from invoking Docker outside the runner.
    """
    require(operation in ('start', 'stop', 'pause', 'unpause', 'exec'), 'Unapproved resource operation')
    require(isinstance(services, (list, tuple)), 'Ordered explicit operation services required')
    requested = _names(services, 'operation services')
    require(requested, 'Implicit whole-project operation is forbidden')
    allowed = _names(allowed_services, 'allowed services')
    started = _names(started_services, 'started services')
    validate_current(receipt, observed)
    known = set(receipt['resources']['containers'])
    require(requested <= allowed <= known and started <= known, 'Operation targets unknown or unapproved services')
    if operation != 'start':
        require(requested <= started, 'Operation may only target services started by this run')
    allowed_states = {'start': {'created', 'exited'}, 'stop': {'running', 'paused', 'exited'},
                      'pause': {'running'}, 'unpause': {'paused'}, 'exec': {'running'}}[operation]
    require(all(observed['containers'][service]['state'] in allowed_states for service in requested),
            'Operation is incompatible with current container state')
    return [observed['containers'][service]['id'] for service in services]


def _memory_bytes(value):
    if type(value) is int:
        return value
    require(isinstance(value, str), 'Invalid memory limit')
    match = re.fullmatch(r'([0-9]+)([kmgt]?b?)', value.lower())
    require(match is not None, 'Unknown memory unit')
    unit = match[2].rstrip('b')
    return int(match[1]) * 1024 ** ('kmgt'.index(unit) + 1 if unit else 0)


def _port(value):
    if isinstance(value, str):
        match = re.fullmatch(r'(127\.0\.0\.1):([0-9]+):([0-9]+)', value)
        require(match is not None, 'Only explicit loopback port bindings allowed')
        return {'host_ip': match[1], 'published': str(int(match[2])), 'target': int(match[3]),
                'protocol': 'tcp', 'mode': 'ingress'}
    require(isinstance(value, dict) and {'host_ip', 'published', 'target'} <= set(value) <=
            {'host_ip', 'published', 'target', 'protocol', 'mode'}, 'Unknown normalized port fields')
    result = {'protocol': 'tcp', 'mode': 'ingress', **value}
    require(result['host_ip'] == '127.0.0.1' and result['protocol'] == 'tcp' and result['mode'] == 'ingress',
            'Unexpected port address/protocol/mode')
    require(str(result['published']).isdigit() and str(result['target']).isdigit(), 'Explicit numeric ports required')
    result['published'], result['target'] = str(int(result['published'])), int(result['target'])
    return result


def _compose_mount(value, *, effective=False):
    require(isinstance(value, dict) and {'type', 'source', 'target'} <= set(value) <=
            {'type', 'source', 'target', 'read_only', 'bind', 'volume'}, 'Unknown Compose mount fields')
    result = copy.deepcopy(value)
    result.setdefault('read_only', False)
    require(type(result['read_only']) is bool and result['type'] in ('volume', 'bind'), 'Unsupported mount/access')
    if result['type'] == 'volume':
        require('bind' not in result and result.get('volume', {}) == {}, 'Unapproved named-volume options')
        result.pop('volume', None)
    else:
        # Compose v2 omits the false member but retains the bind object. The
        # authored plan must still explicitly forbid creation of a host path.
        if effective and result.get('bind') == {}:
            result['bind'] = {'create_host_path': False}
        require('volume' not in result and result.get('bind') == {'create_host_path': False} and result['read_only'],
                'Source bind must be explicit, read-only and never create a host path')
    return result


def _compose_service(value, *, effective=False):
    require(isinstance(value, dict), 'Service config must be an object')
    allowed = {'image', 'networks', 'cpus', 'mem_limit', 'environment', 'volumes', 'depends_on',
               'healthcheck', 'command', 'entrypoint', 'labels', 'ports', 'restart', 'privileged', 'read_only'}
    require(set(value) <= allowed, 'Unknown or unsafe effective service property')
    result = copy.deepcopy(value)
    for field in ('command', 'entrypoint'):
        if field in result:
            if effective and result[field] is None:
                del result[field]
            else:
                require(isinstance(result[field], list) and all(isinstance(v, str) for v in result[field]),
                        'Explicit command/entrypoint array required')
    for field, default in (('restart', 'no'), ('privileged', False), ('read_only', False)):
        if field in result:
            require(result[field] == default, 'Unapproved service runtime behavior')
            del result[field]
    require({'image', 'networks', 'cpus', 'mem_limit'} <= set(result), 'Effective service fields missing')
    _identifier(result['image'], 'effective image', image=True)
    require(type(result['cpus']) in (int, float, str), 'Invalid CPU limit')
    try:
        result['cpus'] = float(result['cpus'])
    except ValueError as error:
        raise ProvenanceError('Invalid CPU limit') from error
    result['mem_limit'] = _memory_bytes(result['mem_limit'])
    networks = result['networks']
    if isinstance(networks, list):
        result['networks'] = sorted(_names(networks, 'Compose service networks'))
    else:
        require(isinstance(networks, dict) and all(value in (None, {}) for value in networks.values()),
                'Network aliases, addresses and driver options are not approved')
        result['networks'] = sorted(networks)
    for field in ('environment', 'labels'):
        if field in result:
            require(isinstance(result[field], dict) and all(isinstance(k, str) and isinstance(v, str)
                    for k, v in result[field].items()), 'Explicit string environment/labels required')
    if 'volumes' in result:
        require(isinstance(result['volumes'], list), 'Explicit service mounts required')
        result['volumes'] = sorted((_compose_mount(v, effective=effective) for v in result['volumes']), key=lambda v: v['target'])
    if 'ports' in result:
        require(isinstance(result['ports'], list), 'Explicit service ports required')
        result['ports'] = sorted((_port(v) for v in result['ports']), key=lambda v: (v['host_ip'], v['published'], v['target']))
    if 'depends_on' in result:
        require(isinstance(result['depends_on'], dict), 'Explicit dependency conditions required')
        for dependency in result['depends_on'].values():
            require(isinstance(dependency, dict) and 'condition' in dependency and
                    set(dependency) <= {'condition', 'required'}, 'Unknown dependency start/restart behavior')
            if 'required' in dependency:
                require(dependency.pop('required') is True, 'Optional dependency not approved')
    return result


def validate_effective_compose(raw_resolved, effective):
    """Compare resolved plan to installed Compose output before any creation.

    Only known Compose v2 normalization is accepted: names, byte memory limits,
    numeric CPUs, long ports, network maps, required dependencies and empty volume
    options. This is not a generic Compose sanitizer. Unknown fields fail closed.
    Arguments may contain fresh secrets in memory; no values are emitted in errors.
    """
    top = {'name', 'services', 'volumes', 'networks'}
    _keys(raw_resolved, top, 'resolved Compose plan')
    _keys(effective, top, 'effective Compose')
    require(raw_resolved['name'] == effective['name'] and isinstance(effective['name'], str) and
            re.fullmatch(r'dodream-evidence-\d{8}', effective['name']), 'Effective project mismatch')
    project = effective['name']
    for kind in ('services', 'volumes', 'networks'):
        require(isinstance(raw_resolved[kind], dict) and isinstance(effective[kind], dict) and
                set(raw_resolved[kind]) == set(effective[kind]), 'Effective resource set differs')
    for name in raw_resolved['services']:
        require(_compose_service(raw_resolved['services'][name]) == _compose_service(effective['services'][name], effective=True),
                'Effective service differs from its reviewed configuration')
    for kind in ('volumes', 'networks'):
        for key, planned in raw_resolved[kind].items():
            require(isinstance(planned, dict), 'Invalid planned storage/network')
            actual = copy.deepcopy(effective[kind][key])
            require(isinstance(actual, dict), 'Invalid effective storage/network')
            require(actual.pop('name', None) == project + '_' + key, 'Effective storage/network name mismatch')
            if kind == 'networks' and 'ipam' in actual:
                require(actual.pop('ipam') == {}, 'Unapproved network address-management configuration')
            for field in ('external', 'driver_opts'):
                if field in actual:
                    require(actual.pop(field) in (False, None, {}), 'External resource or driver options forbidden')
            require(set(actual) <= {'driver', 'labels', 'internal'}, 'Unknown effective storage/network property')
            expected = copy.deepcopy(planned)
            require(set(expected) <= {'driver', 'labels', 'internal'}, 'Unknown planned storage/network property')
            if kind == 'networks':
                actual.setdefault('internal', False)
                expected.setdefault('internal', False)
            require(actual == expected, 'Effective storage/network configuration drift')
    return {'status': 'PASS', 'scope': 'EFFECTIVE_COMPOSE_CONFIGURATION_ONLY', 'executionAuthorized': False}
