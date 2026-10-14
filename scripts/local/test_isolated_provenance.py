"""Synthetic-only provenance policy tests; process and network access fail closed."""
import contextlib
import copy
import os
import socket
import subprocess
import unittest
from unittest import mock

import isolated_provenance as policy


PROJECT = 'dodream-evidence-20261014'
RUN_ID = '00000000-0000-4000-8000-000000000001'
BEGIN = '2026-10-14T01:00:00.200000Z'
CREATED = '2026-10-14T01:00:00.500000Z'
END = '2026-10-14T01:00:02Z'
ZERO = '0001-01-01T00:00:00Z'
VOLUME = PROJECT + '_mysql-data'
NETWORK = PROJECT + '_default'


def fail_effect(*args, **kwargs):
    raise AssertionError('Pure provenance policy attempted a real effect')


def scenario():
    labels = {policy.PROJECT_LABEL: PROJECT, policy.RUN_LABEL: RUN_ID}
    mount = {'type': 'volume', 'name': VOLUME, 'destination': '/var/lib/mysql', 'rw': True}
    service = {'image': 'sha256:' + 'a' * 64, 'command': ['mysqld'], 'entrypoint': ['docker-entrypoint.sh'],
               'envHash': 'b' * 64, 'mounts': [mount], 'networkNames': [NETWORK], 'ports': {}}
    expected = {'project': PROJECT, 'services': {'mysql': service}, 'volumes': [VOLUME],
                'networks': {NETWORK: {'driver': 'bridge', 'internal': True}}}
    observed = {
        'containers': {'mysql': {'id': 'c' * 64, 'image': service['image'], 'created': CREATED,
            'state': 'created', 'startedAt': ZERO, 'project': PROJECT, 'service': 'mysql', 'runId': RUN_ID,
            'command': service['command'], 'entrypoint': service['entrypoint'], 'envHash': service['envHash'],
            'mounts': [{**mount, 'source': '/var/lib/docker/volumes/' + VOLUME + '/_data'}],
            'networks': {NETWORK: 'd' * 64}, 'ports': {}}},
        'volumes': {VOLUME: {'name': VOLUME, 'driver': 'local', 'options': {}, 'created': CREATED, 'labels': labels}},
        'networks': {NETWORK: {'id': 'd' * 64, 'name': NETWORK, 'driver': 'bridge', 'internal': True,
                               'options': {}, 'created': CREATED, 'labels': labels}},
    }
    before = {'containers': ['e' * 64], 'volumes': ['dodream-phase1_mysql-data'], 'networks': ['dodream-phase1_default']}
    return copy.deepcopy((before, observed, expected))


def compose_scenario():
    labels = {policy.RUN_LABEL: RUN_ID}
    raw = {'name': PROJECT, 'services': {'web': {
        'image': 'sha256:' + 'a' * 64, 'networks': ['default'], 'cpus': 1.0, 'mem_limit': '128m',
        'environment': {'APP_ENV': 'local', 'SYNTHETIC_SECRET': 'NOT_A_REAL_SECRET'}, 'labels': labels,
        'command': ['nginx', '-g', 'daemon off;'], 'ports': ['127.0.0.1:25173:80'],
        'depends_on': {'mysql': {'condition': 'service_healthy'}},
        'volumes': [{'type': 'volume', 'source': 'mysql-data', 'target': '/data', 'read_only': False},
                    {'type': 'bind', 'source': '/synthetic/trial/nginx.conf', 'target': '/config',
                     'read_only': True, 'bind': {'create_host_path': False}}],
        'healthcheck': {'test': ['CMD', 'true'], 'interval': '5s', 'timeout': '5s', 'retries': 20}}},
        'volumes': {'mysql-data': {'driver': 'local', 'labels': labels}},
        'networks': {'default': {'driver': 'bridge', 'internal': True, 'labels': labels}}}
    actual = copy.deepcopy(raw)
    actual['services']['web'].update(cpus='1', mem_limit=134217728, networks={'default': None},
                                    ports=[{'mode': 'ingress', 'host_ip': '127.0.0.1', 'published': '25173',
                                            'target': 80, 'protocol': 'tcp'}])
    actual['services']['web']['depends_on']['mysql']['required'] = True
    actual['services']['web']['volumes'][0].pop('read_only')
    actual['services']['web']['volumes'][0]['volume'] = {}
    for kind in ('volumes', 'networks'):
        for name, row in actual[kind].items():
            row['name'] = PROJECT + '_' + name
    return raw, actual


class ProvenancePolicyTests(unittest.TestCase):
    def setUp(self):
        self.effects = contextlib.ExitStack()
        self.addCleanup(self.effects.close)
        for module, name in ((subprocess, 'Popen'), (subprocess, 'run'), (subprocess, 'check_call'),
                             (subprocess, 'check_output'), (os, 'system'), (os, 'popen'),
                             (socket, 'socket'), (socket, 'create_connection')):
            self.effects.enter_context(mock.patch.object(module, name, side_effect=fail_effect))
        self.before, self.observed, self.expected = scenario()

    def create(self):
        return policy.validate_created(self.before, self.observed, self.expected, RUN_ID, BEGIN, END)

    def test_complete_new_creation_returns_detached_evidence(self):
        receipt = self.create()
        self.assertEqual(receipt['status'], 'CREATED_VERIFIED')
        self.assertEqual(receipt['runId'], RUN_ID)
        policy.validate_current(receipt, self.observed)
        self.observed['containers']['mysql']['image'] = 'sha256:' + 'f' * 64
        self.assertNotEqual(receipt['resources'], self.observed)

    def test_existing_container_id_and_same_named_resources_cannot_be_adopted(self):
        for field, old in (('containers', 'c' * 64), ('volumes', VOLUME), ('networks', NETWORK)):
            with self.subTest(field=field):
                before = copy.deepcopy(self.before)
                before[field].append(old)
                with self.assertRaises(policy.ProvenanceError):
                    policy.validate_created(before, self.observed, self.expected, RUN_ID, BEGIN, END)

    def test_incomplete_and_unexpected_creation_fail(self):
        for field in ('containers', 'volumes', 'networks'):
            for mode in ('missing', 'extra'):
                with self.subTest(field=field, mode=mode):
                    observed = copy.deepcopy(self.observed)
                    if mode == 'missing':
                        observed[field] = {}
                    else:
                        observed[field]['unplanned'] = {}
                    with self.assertRaises(policy.ProvenanceError):
                        policy.validate_created(self.before, observed, self.expected, RUN_ID, BEGIN, END)

    def test_every_resource_requires_creation_time_in_recorded_interval(self):
        for field, key in (('containers', 'mysql'), ('volumes', VOLUME), ('networks', NETWORK)):
            for timestamp in ('2026-10-13T23:59:59Z', '2026-10-14T01:00:03Z', 'not-a-time', '2026-10-14T01:00:00'):
                with self.subTest(field=field, timestamp=timestamp):
                    observed = copy.deepcopy(self.observed)
                    observed[field][key]['created'] = timestamp
                    with self.assertRaises(policy.ProvenanceError):
                        policy.validate_created(self.before, observed, self.expected, RUN_ID, BEGIN, END)

    def test_docker_whole_second_creation_precision_is_accepted(self):
        for field, key in (('volumes', VOLUME), ('networks', NETWORK)):
            self.observed[field][key]['created'] = '2026-10-14T01:00:00Z'
        self.create()

    def test_docker_nanoseconds_compare_on_python39_without_rewriting_evidence(self):
        value = '2026-10-14T01:00:00.636774959Z'
        for field, key in (('containers', 'mysql'), ('volumes', VOLUME), ('networks', NETWORK)):
            self.observed[field][key]['created'] = value
        receipt = self.create()
        self.assertEqual(receipt['resources']['containers']['mysql']['created'], value)
        self.assertEqual(policy._timestamp(value).microsecond, 636774)
        for invalid in ('2026-10-14T01:00:00.1234567890Z', '2026-10-14 01:00:00Z',
                        '2026-10-14T01:00:00.Z', '2026-10-14T01:00:00Z\n'):
            with self.subTest(invalid=invalid), self.assertRaises(policy.ProvenanceError):
                policy._timestamp(invalid)

    def test_never_started_created_network_can_be_unattached_then_bind_new_id(self):
        self.observed['containers']['mysql']['networks'][NETWORK] = ''
        receipt = self.create()
        self.assertEqual(receipt['resources']['containers']['mysql']['networks'][NETWORK], '')
        self.assertEqual(receipt['resources']['networks'][NETWORK]['id'], 'd' * 64)
        policy.validate_current(receipt, self.observed)
        current = copy.deepcopy(self.observed)
        current['containers']['mysql'].update(state='running', startedAt=END)
        current['containers']['mysql']['networks'][NETWORK] = 'd' * 64
        policy.validate_current(receipt, current)

    def test_empty_started_network_or_wrong_new_network_id_is_rejected(self):
        self.observed['containers']['mysql']['networks'][NETWORK] = ''
        receipt = self.create()
        for state, started, identifier in (('running', END, ''), ('exited', END, ''),
                                            ('created', END, ''), ('created', ZERO, 'e' * 64),
                                            ('running', END, 'e' * 64)):
            with self.subTest(state=state, started=started, identifier=identifier):
                current = copy.deepcopy(self.observed)
                current['containers']['mysql'].update(state=state, startedAt=started)
                current['containers']['mysql']['networks'][NETWORK] = identifier
                with self.assertRaises(policy.ProvenanceError):
                    policy.validate_current(receipt, current)

    def test_started_or_previously_started_container_is_not_new_creation(self):
        for state, started in (('running', ZERO), ('exited', CREATED), ('created', CREATED), ('created', '')):
            with self.subTest(state=state, started=started):
                self.observed['containers']['mysql'].update(state=state, startedAt=started)
                with self.assertRaises(policy.ProvenanceError):
                    self.create()

    def test_wrong_project_service_run_or_image_reject(self):
        for field, value in (('project', 'dodream-phase1'), ('service', 'worker'), ('runId', 'old'),
                             ('image', 'mysql:8.4'), ('id', 'short-id'), ('command', ['sh']),
                             ('entrypoint', ['sh']), ('envHash', 'f' * 64), ('ports', {'3306': '3306'})):
            with self.subTest(field=field):
                observed = copy.deepcopy(self.observed)
                observed['containers']['mysql'][field] = value
                with self.assertRaises(policy.ProvenanceError):
                    policy.validate_created(self.before, observed, self.expected, RUN_ID, BEGIN, END)

    def test_resource_labels_do_not_substitute_for_newness(self):
        for field, key in (('volumes', VOLUME), ('networks', NETWORK)):
            for labels in ({}, {policy.PROJECT_LABEL: PROJECT},
                           {policy.PROJECT_LABEL: 'dodream-phase1', policy.RUN_LABEL: RUN_ID}):
                with self.subTest(field=field, labels=labels):
                    observed = copy.deepcopy(self.observed)
                    observed[field][key]['labels'] = labels
                    with self.assertRaises(policy.ProvenanceError):
                        policy.validate_created(self.before, observed, self.expected, RUN_ID, BEGIN, END)

    def test_local_volume_driver_options_cannot_bind_old_storage(self):
        for patch in ({'driver': 'nfs'}, {'options': {'type': 'none', 'device': '/old/data', 'o': 'bind'}}):
            with self.subTest(patch=patch):
                observed = copy.deepcopy(self.observed)
                observed['volumes'][VOLUME].update(patch)
                with self.assertRaises(policy.ProvenanceError):
                    policy.validate_created(self.before, observed, self.expected, RUN_ID, BEGIN, END)

    def test_network_driver_options_internal_and_actual_id_must_match(self):
        for patch in ({'driver': 'host'}, {'options': {'com.docker.network.bridge.name': 'old'}}, {'internal': False}):
            with self.subTest(patch=patch):
                observed = copy.deepcopy(self.observed)
                observed['networks'][NETWORK].update(patch)
                with self.assertRaises(policy.ProvenanceError):
                    policy.validate_created(self.before, observed, self.expected, RUN_ID, BEGIN, END)
        self.observed['containers']['mysql']['networks'][NETWORK] = 'e' * 64
        with self.assertRaises(policy.ProvenanceError):
            self.create()

    def test_extra_old_network_and_storage_mount_reject(self):
        self.observed['containers']['mysql']['networks']['dodream-phase1_default'] = 'e' * 64
        with self.assertRaises(policy.ProvenanceError):
            self.create()
        self.before, self.observed, self.expected = scenario()
        self.observed['containers']['mysql']['mounts'].append({'type': 'bind', 'source': '/old/data', 'destination': '/old', 'rw': True})
        with self.assertRaises(policy.ProvenanceError):
            self.create()

    def test_volume_mount_source_must_match_new_volume_not_old_volume(self):
        for source in ('/var/lib/docker/volumes/dodream-phase1_mysql-data/_data', '/old/rag.db',
                       '/var/lib/docker/volumes/../' + VOLUME + '/_data'):
            with self.subTest(source=source):
                self.observed['containers']['mysql']['mounts'][0]['source'] = source
                with self.assertRaises(policy.ProvenanceError):
                    self.create()

    def test_read_only_exact_source_bind_can_be_verified(self):
        bind = {'type': 'bind', 'source': '/synthetic/new-trial/nginx.conf', 'destination': '/etc/nginx/conf.d/default.conf', 'rw': False}
        self.expected['services']['mysql']['mounts'].append(bind)
        self.observed['containers']['mysql']['mounts'].append(copy.deepcopy(bind))
        self.create()
        self.observed['containers']['mysql']['mounts'][-1]['rw'] = True
        with self.assertRaises(policy.ProvenanceError):
            self.create()

    def test_docker_socket_and_writeable_binds_reject_even_when_expected(self):
        for source, rw in (('/var/run/docker.sock', False), ('/synthetic/new-trial/file', True)):
            with self.subTest(source=source, rw=rw):
                before, observed, expected = scenario()
                bind = {'type': 'bind', 'source': source, 'destination': '/data', 'rw': rw}
                expected['services']['mysql']['mounts'].append(bind)
                observed['containers']['mysql']['mounts'].append(copy.deepcopy(bind))
                with self.assertRaises(policy.ProvenanceError):
                    policy.validate_created(before, observed, expected, RUN_ID, BEGIN, END)

    def test_current_state_may_change_but_not_immutable_fields(self):
        receipt = self.create()
        current = copy.deepcopy(self.observed)
        current['containers']['mysql'].update(state='running', startedAt=END)
        policy.validate_current(receipt, current)
        for field, value in (('id', 'f' * 64), ('image', 'sha256:' + 'f' * 64), ('envHash', 'f' * 64),
                             ('created', END), ('command', ['sh']), ('entrypoint', []), ('networks', {}),
                             ('mounts', []), ('ports', {'bad': 'bad'}), ('runId', 'old')):
            with self.subTest(field=field):
                changed = copy.deepcopy(current)
                changed['containers']['mysql'][field] = value
                with self.assertRaises(policy.ProvenanceError):
                    policy.validate_current(receipt, changed)

    def test_current_volume_and_network_replacement_rejects(self):
        receipt = self.create()
        for field, key, property_name, value in (('volumes', VOLUME, 'created', END),
                                                 ('networks', NETWORK, 'id', 'f' * 64)):
            with self.subTest(field=field):
                current = copy.deepcopy(self.observed)
                current[field][key][property_name] = value
                with self.assertRaises(policy.ProvenanceError):
                    policy.validate_current(receipt, current)

    def test_current_mount_order_is_irrelevant_but_full_source_path_remains_fixed(self):
        bind = {'type': 'bind', 'source': '/synthetic/new-trial/nginx.conf', 'destination': '/config', 'rw': False}
        self.expected['services']['mysql']['mounts'].append(copy.deepcopy(bind))
        self.observed['containers']['mysql']['mounts'].append(copy.deepcopy(bind))
        receipt = self.create()
        current = copy.deepcopy(self.observed)
        current['containers']['mysql']['mounts'].reverse()
        policy.validate_current(receipt, current)
        for source in ('/old/existing/data', '/other/volumes/' + VOLUME + '/_data'):
            with self.subTest(source=source):
                changed = copy.deepcopy(current)
                changed['containers']['mysql']['mounts'][1]['source'] = source
                with self.assertRaises(policy.ProvenanceError):
                    policy.validate_current(receipt, changed)

    def test_receipt_presence_or_marker_cannot_authorize_operation(self):
        receipt = self.create()
        for change in ('status', 'before', 'resources'):
            with self.subTest(change=change):
                changed = copy.deepcopy(receipt)
                if change == 'status':
                    changed['status'] = 'INCOMPLETE'
                elif change == 'before':
                    changed['before']['containers'].append('c' * 64)
                else:
                    changed['resources']['containers']['mysql']['startedAt'] = END
                with self.assertRaises(policy.ProvenanceError):
                    policy.validate_current(changed, self.observed)

    def test_start_returns_only_exact_approved_new_ids(self):
        receipt = self.create()
        self.assertEqual(policy.operation_ids(receipt, self.observed, 'start', ['mysql'], ['mysql'], []), ['c' * 64])
        for operation, services, allowed in (('config', ['mysql'], ['mysql']), ('up', ['mysql'], ['mysql']),
                                              ('start', [], ['mysql']), ('start', ['mysql'], []),
                                              ('start', ['worker'], ['worker']), ('start', ['c' * 64], ['mysql']),
                                              ('start', ['mysql', 'mysql'], ['mysql'])):
            with self.subTest(operation=operation, services=services):
                with self.assertRaises(policy.ProvenanceError):
                    policy.operation_ids(receipt, self.observed, operation, services, allowed, [])

    def test_stop_pause_unpause_exec_require_this_runs_started_set(self):
        receipt = self.create()
        current = copy.deepcopy(self.observed)
        current['containers']['mysql'].update(state='running', startedAt=END)
        for operation in ('stop', 'pause', 'exec'):
            with self.subTest(operation=operation):
                with self.assertRaises(policy.ProvenanceError):
                    policy.operation_ids(receipt, current, operation, ['mysql'], ['mysql'], [])
                self.assertEqual(policy.operation_ids(receipt, current, operation, ['mysql'], ['mysql'], ['mysql']), ['c' * 64])
        current['containers']['mysql']['state'] = 'paused'
        self.assertEqual(policy.operation_ids(receipt, current, 'unpause', ['mysql'], ['mysql'], ['mysql']), ['c' * 64])

    def test_state_incompatible_operation_and_dead_resources_reject(self):
        receipt = self.create()
        for state, operation in (('running', 'start'), ('created', 'exec'), ('exited', 'pause'),
                                 ('running', 'unpause'), ('dead', 'stop'), ('restarting', 'stop')):
            with self.subTest(state=state, operation=operation):
                current = copy.deepcopy(self.observed)
                current['containers']['mysql'].update(state=state, startedAt=END)
                with self.assertRaises(policy.ProvenanceError):
                    policy.operation_ids(receipt, current, operation, ['mysql'], ['mysql'], ['mysql'])

    def test_error_or_signal_cleanup_cannot_expand_to_unknown_id(self):
        receipt = self.create()
        current = copy.deepcopy(self.observed)
        current['containers']['mysql'].update(state='running', startedAt=END)
        for requested, allowed, started in ((['old-id'], ['mysql'], ['mysql']),
                                            (['mysql'], ['mysql', 'old-id'], ['mysql']),
                                            (['mysql'], ['mysql'], ['mysql', 'old-id'])):
            with self.subTest(requested=requested, allowed=allowed, started=started):
                with self.assertRaises(policy.ProvenanceError):
                    policy.operation_ids(receipt, current, 'stop', requested, allowed, started)

    def test_unknown_metadata_and_secret_fields_reject(self):
        for field, key in (('containers', 'mysql'), ('volumes', VOLUME), ('networks', NETWORK)):
            with self.subTest(field=field):
                observed = copy.deepcopy(self.observed)
                observed[field][key]['environment'] = {'SYNTHETIC': 'NOT_A_SECRET'}
                with self.assertRaises(policy.ProvenanceError):
                    policy.validate_created(self.before, observed, self.expected, RUN_ID, BEGIN, END)

    def test_effective_compose_allows_only_known_v2_normalization(self):
        raw, effective = compose_scenario()
        saved = copy.deepcopy(effective)
        result = policy.validate_effective_compose(raw, effective)
        self.assertEqual(result['status'], 'PASS')
        self.assertFalse(result['executionAuthorized'])
        self.assertEqual(effective, saved)

    def test_effective_inherited_command_null_is_omitted_but_empty_array_is_override(self):
        for field in ('command', 'entrypoint'):
            with self.subTest(field=field):
                raw, effective = compose_scenario()
                raw['services']['web'].pop(field, None)
                effective['services']['web'][field] = None
                policy.validate_effective_compose(raw, effective)
                effective['services']['web'][field] = []
                with self.assertRaises(policy.ProvenanceError):
                    policy.validate_effective_compose(raw, effective)
                raw['services']['web'][field] = ['synthetic-command']
                effective['services']['web'][field] = None
                with self.assertRaises(policy.ProvenanceError):
                    policy.validate_effective_compose(raw, effective)

    def test_effective_empty_bind_object_preserves_explicit_false_plan_only(self):
        raw, effective = compose_scenario()
        effective['services']['web']['volumes'][1]['bind'] = {}
        policy.validate_effective_compose(raw, effective)
        for invalid in ({'create_host_path': True}, None):
            with self.subTest(invalid=invalid):
                changed = copy.deepcopy(effective)
                if invalid is None:
                    changed['services']['web']['volumes'][1].pop('bind')
                else:
                    changed['services']['web']['volumes'][1]['bind'] = invalid
                with self.assertRaises(policy.ProvenanceError):
                    policy.validate_effective_compose(raw, changed)
        for planned in ({}, {'create_host_path': True}, None):
            with self.subTest(planned=planned):
                changed = copy.deepcopy(raw)
                if planned is None:
                    changed['services']['web']['volumes'][1].pop('bind')
                else:
                    changed['services']['web']['volumes'][1]['bind'] = planned
                with self.assertRaises(policy.ProvenanceError):
                    policy.validate_effective_compose(changed, effective)

    def test_authored_null_command_or_entrypoint_is_not_silently_normalized(self):
        for field in ('command', 'entrypoint'):
            raw, effective = compose_scenario()
            raw['services']['web'][field] = None
            effective['services']['web'][field] = None
            with self.subTest(field=field), self.assertRaises(policy.ProvenanceError):
                policy.validate_effective_compose(raw, effective)

    def test_effective_empty_ipam_only_is_normalized_without_allowing_authored_ipam(self):
        raw, effective = compose_scenario()
        effective['networks']['default']['ipam'] = {}
        policy.validate_effective_compose(raw, effective)
        for value in (None, {'driver': 'default'}, {'driver': 'unreviewed'},
                      {'config': [{'subnet': '10.0.0.0/8'}]}):
            with self.subTest(value=value):
                changed = copy.deepcopy(effective)
                changed['networks']['default']['ipam'] = value
                with self.assertRaises(policy.ProvenanceError):
                    policy.validate_effective_compose(raw, changed)
        raw['networks']['default']['ipam'] = {}
        with self.assertRaises(policy.ProvenanceError):
            policy.validate_effective_compose(raw, effective)

    def test_effective_compose_rejects_unknown_and_dangerous_service_fields(self):
        for field, value in (('privileged', True), ('network_mode', 'host'), ('pid', 'host'), ('ipc', 'host'),
                             ('extra_hosts', ['mysql:host-gateway']), ('volumes_from', ['old-container']),
                             ('devices', ['/dev/sda:/dev/sda']), ('env_file', ['/old/env']), ('restart', 'always'),
                             ('build', '/old/source'), ('entrypoint', ['sh']), ('cap_add', ['SYS_ADMIN'])):
            with self.subTest(field=field):
                raw, effective = compose_scenario()
                effective['services']['web'][field] = value
                with self.assertRaises(policy.ProvenanceError):
                    policy.validate_effective_compose(raw, effective)

    def test_effective_compose_rejects_image_command_credentials_and_cpu_drift(self):
        for field, value in (('image', 'sha256:' + 'b' * 64), ('command', ['sh']), ('cpus', 2),
                             ('mem_limit', 1), ('environment', {'DATABASE_URL': 'SYNTHETIC_OLD_ENDPOINT'}),
                             ('labels', {policy.RUN_LABEL: 'old-run'})):
            with self.subTest(field=field):
                raw, effective = compose_scenario()
                effective['services']['web'][field] = value
                with self.assertRaises(policy.ProvenanceError):
                    policy.validate_effective_compose(raw, effective)

    def test_effective_compose_rejects_old_mounts_write_access_and_bind_creation(self):
        for index, field, value in ((0, 'source', 'dodream-phase1_mysql-data'), (1, 'source', '/old/.local/rag.db'),
                                     (1, 'read_only', False), (1, 'bind', {'create_host_path': True}),
                                     (0, 'volume', {'subpath': 'old'})):
            with self.subTest(index=index, field=field):
                raw, effective = compose_scenario()
                effective['services']['web']['volumes'][index][field] = value
                with self.assertRaises(policy.ProvenanceError):
                    policy.validate_effective_compose(raw, effective)

    def test_effective_compose_rejects_port_network_and_dependency_escape(self):
        for field, value in (('ports', [{'host_ip': '0.0.0.0', 'published': '25173', 'target': 80}]),
                             ('ports', ['127.0.0.1:15173:80']), ('networks', {'default': {'aliases': ['old-service']}}),
                             ('networks', ['old-network']), ('depends_on', {'worker': {'condition': 'service_started'}}),
                             ('depends_on', {'mysql': {'condition': 'service_healthy', 'required': False}}),
                             ('depends_on', {'mysql': {'condition': 'service_healthy', 'restart': True}})):
            with self.subTest(field=field, value=value):
                raw, effective = compose_scenario()
                effective['services']['web'][field] = value
                with self.assertRaises(policy.ProvenanceError):
                    policy.validate_effective_compose(raw, effective)

    def test_effective_compose_rejects_resource_name_external_driver_and_options(self):
        for kind, key in (('volumes', 'mysql-data'), ('networks', 'default')):
            for field, value in (('name', 'dodream-phase1_old'), ('external', True),
                                 ('driver_opts', {'device': '/old/data'}), ('driver', 'external-driver'),
                                 ('unreviewed', True)):
                with self.subTest(kind=kind, field=field):
                    raw, effective = compose_scenario()
                    effective[kind][key][field] = value
                    with self.assertRaises(policy.ProvenanceError):
                        policy.validate_effective_compose(raw, effective)
        raw, effective = compose_scenario()
        effective['networks']['default']['internal'] = False
        with self.assertRaises(policy.ProvenanceError):
            policy.validate_effective_compose(raw, effective)

    def test_effective_compose_requires_exact_service_resource_and_project_sets(self):
        for kind in ('services', 'volumes', 'networks'):
            for extra in (True, False):
                with self.subTest(kind=kind, extra=extra):
                    raw, effective = compose_scenario()
                    if extra:
                        effective[kind]['unexpected'] = {}
                    else:
                        effective[kind] = {}
                    with self.assertRaises(policy.ProvenanceError):
                        policy.validate_effective_compose(raw, effective)
        raw, effective = compose_scenario()
        effective['name'] = 'dodream-phase1'
        with self.assertRaises(policy.ProvenanceError):
            policy.validate_effective_compose(raw, effective)


class BeRevisionPolicyTests(unittest.TestCase):
    """Synthetic stopped old IDs -> newly created BE IDs; no execution allowed."""
    def setUp(self):
        ProvenancePolicyTests.setUp(self)
        base = self.observed['containers']['mysql']
        spec = self.expected['services']['mysql']
        for index, name in enumerate(policy.BE_REVISION_SERVICES, 1):
            self.observed['containers'][name] = {**copy.deepcopy(base), 'id': f'{index:064x}', 'service': name}
            self.expected['services'][name] = copy.deepcopy(spec)
        self.previous = ProvenancePolicyTests.create(self)
        self.stopped = copy.deepcopy(self.observed)
        for row in self.stopped['containers'].values(): row.update(state='exited', startedAt=END)
        self.after = copy.deepcopy(self.stopped)
        self.next_expected = copy.deepcopy(self.previous['expected'])
        self.new_image = 'sha256:' + 'f' * 64
        for index, name in enumerate(policy.BE_REVISION_SERVICES, 10):
            self.after['containers'][name].update(id=f'{index:064x}', image=self.new_image,
                state='created', startedAt=ZERO, created='2026-10-14T01:01:01Z')
            self.next_expected['services'][name]['image'] = self.new_image

    def revise(self):
        return policy.validate_recreated(self.previous, self.stopped, self.after, self.next_expected,
                                         '2026-10-14T01:01:00Z', '2026-10-14T01:01:02Z')

    def test_revision_keeps_original_receipt_storage_and_non_be_ids(self):
        revised=self.revise()
        self.assertEqual(revised['previous'],self.previous)
        self.assertEqual(revised['resources']['volumes'],self.previous['resources']['volumes'])
        self.assertEqual(revised['resources']['containers']['mysql'],self.stopped['containers']['mysql'])
        policy.validate_current(revised,self.after)
        running=copy.deepcopy(self.after)
        running['containers']['be'].update(state='running',startedAt='2026-10-14T01:01:03Z')
        policy.validate_current(revised,running)
        ids=policy.operation_ids(revised,self.after,'start',['be'],{'be'},set())
        self.assertEqual(ids,[self.after['containers']['be']['id']])

    def test_revision_refuses_running_unselected_service(self):
        self.stopped['containers']['mysql']['state']='running'
        with self.assertRaises(policy.ProvenanceError):self.revise()

    def test_revision_refuses_stale_old_and_foreign_container_ids(self):
        for candidate in (self.stopped['containers']['be']['id'],self.before['containers'][0],
                          self.after['containers']['be-auth-short']['id']):
            with self.subTest(candidate=candidate):
                original=self.after['containers']['be']['id']
                self.after['containers']['be']['id']=candidate
                with self.assertRaises(policy.ProvenanceError):self.revise()
                self.after['containers']['be']['id']=original

    def test_revision_refuses_environment_mount_network_and_unselected_changes(self):
        mutations=[lambda: self.next_expected['services']['be'].update(envHash='a'*64),
                   lambda: self.after['containers']['be'].update(envHash='a'*64),
                   lambda: self.after['containers']['mysql'].update(image=self.new_image),
                   lambda: self.after['volumes'][VOLUME].update(created='2026-10-14T01:01:01Z'),
                   lambda: self.after['networks'][NETWORK].update(id='e'*64),
                   lambda: self.after['containers']['be']['mounts'][0].update(name='dodream-phase1_mysql-data')]
        for mutate in mutations:
            old_after,old_expected=copy.deepcopy(self.after),copy.deepcopy(self.next_expected)
            mutate()
            with self.assertRaises(policy.ProvenanceError):self.revise()
            self.after,self.next_expected=old_after,old_expected

    def test_revision_refuses_started_wrong_window_or_mismatched_be_image(self):
        for changes in ({'state':'running','startedAt':'2026-10-14T01:01:01Z'},
                        {'created':CREATED},{'image':'sha256:'+'1'*64}):
            original=copy.deepcopy(self.after['containers']['be'])
            self.after['containers']['be'].update(changes)
            with self.assertRaises(policy.ProvenanceError):self.revise()
            self.after['containers']['be']=original

    def test_revision_chain_cannot_return_to_retired_original_container_id(self):
        first=self.revise()
        next_stopped=copy.deepcopy(self.after)
        next_after=copy.deepcopy(self.after)
        next_expected=copy.deepcopy(first['expected'])
        for index,name in enumerate(policy.BE_REVISION_SERVICES,20):
            next_stopped['containers'][name].update(state='exited',startedAt='2026-10-14T01:01:03Z')
            next_after['containers'][name].update(id=f'{index:064x}',created='2026-10-14T01:02:01Z',image='sha256:'+'2'*64)
            next_expected['services'][name]['image']='sha256:'+'2'*64
        second=policy.validate_recreated(first,next_stopped,next_after,next_expected,'2026-10-14T01:02:00Z','2026-10-14T01:02:02Z')
        policy.validate_current(second,next_after)
        next_after['containers']['be']['id']=self.previous['resources']['containers']['be']['id']
        with self.assertRaises(policy.ProvenanceError):
            policy.validate_recreated(first,next_stopped,next_after,next_expected,'2026-10-14T01:02:00Z','2026-10-14T01:02:02Z')


if __name__ == '__main__':
    unittest.main()
