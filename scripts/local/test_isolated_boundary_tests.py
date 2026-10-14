"""Synthetic Docker metadata only; every process/network call fails immediately."""
import contextlib
import copy
import json
import os
from pathlib import Path
import socket
import subprocess
import unittest
from unittest import mock
import urllib.request

from isolated_boundary_tests import (COMMAND, LABEL_PREFIX, UNUSED_IMAGE_CACHE, UNUSED_CACHE_TMPFS,
                                     expected_config, validate_container, stable_resources, test_environment, junit_summary,
                                     TEST_CACHE, boundary_dockerfile, validate_boundary_dockerfile, junit_outcome, CLASSES, validate_selected_test_sources)


def forbidden(*args, **kwargs):
    raise AssertionError('Pure boundary-test policy attempted execution')


class BoundaryTestPolicyTests(unittest.TestCase):
    def setUp(self):
        self.effects = contextlib.ExitStack()
        self.addCleanup(self.effects.close)
        for module, name in ((subprocess, 'run'), (subprocess, 'Popen'), (subprocess, 'check_output'),
                             (os, 'system'), (os, 'popen'), (socket, 'socket'), (socket, 'create_connection'),
                             (urllib.request, 'urlopen'), (urllib.request.OpenerDirector, 'open')):
            self.effects.enter_context(mock.patch.object(module, name, side_effect=forbidden))
        self.project = 'dodream-evidence-20261014'
        self.run_id = '00000000-0000-4000-8000-000000000001'
        self.image = {'Id': 'sha256:' + 'a' * 64, 'Config': {'Entrypoint': ['/__cacert_entrypoint.sh'], 'Volumes': {UNUSED_IMAGE_CACHE: {}}, 'User': 'root',
            'Cmd': ['gradle', '--offline', '--no-daemon', 'test', '--rerun-tasks'], 'WorkingDir': '/workspace',
            'Env': ['PATH=/SYNTHETIC_ONLY'], 'Labels': {'io.dodream.isolated.source-digest': 'SYNTHETIC_SOURCE'}}}
        self.environment = {'MYSQL_HOST': 'mysql', 'REDIS_HOST': 'redis',
            'MYSQL_DATABASE': self.project.replace('-', '_'), 'MYSQL_USER': 'synthetic_trial',
            'MYSQL_PASSWORD': 'SYNTHETIC_NOT_A_SECRET', 'SPRING_PROFILES_ACTIVE': 'local',
            'LOCAL_DATA_DIR': '/app/local-data', 'AI_BASE_URL': 'http://ai:8000',
            'HOME': '/root', 'GRADLE_USER_HOME': TEST_CACHE}
        self.volume = {'Name': self.project + '_be-data', 'Driver': 'local', 'Options': {},
                       'Mountpoint': '/SYNTHETIC_DOCKER_VOLUME/' + self.project + '_be-data/_data',
                       'Labels': {'io.dodream.trial.run-id': self.run_id, 'com.docker.compose.project': self.project,
                                  'com.docker.compose.volume': 'be-data'}}
        self.network = {'Name': self.project + '_default', 'Id': 'b' * 64, 'Internal': True, 'Driver': 'bridge',
                        'Labels': {'io.dodream.trial.run-id': self.run_id, 'com.docker.compose.project': self.project,
                                   'com.docker.compose.network': 'default'}}
        self.expected = expected_config(self.project, self.run_id, '002-fixed-01', 'focused-java-02', self.image,
                                        self.environment, self.volume, self.network)
        self.actual = {'Id': 'c' * 64, 'Name': '/' + self.expected['name'], 'Image': self.image['Id'],
            'Created': '2026-10-14T00:01:01.123456789Z',
            'Config': {'Labels': self.expected['labels'], 'Cmd': COMMAND, 'Entrypoint': [], 'User': '0:0',
                'WorkingDir': '/workspace', 'Env': self.image['Config']['Env'] + [key + '=' + value for key, value in self.environment.items()]},
            'HostConfig': {'PortBindings': {}, 'PublishAllPorts': False, 'Privileged': False,
                'NetworkMode': self.network['Id'], 'IpcMode': 'private', 'RestartPolicy': {'Name': 'no'},
                'Memory': 1280 * 1024 * 1024, 'NanoCpus': 2_000_000_000,
                'Tmpfs': {UNUSED_IMAGE_CACHE: UNUSED_CACHE_TMPFS}},
            'Mounts': [{'Type': 'volume', 'Name': self.volume['Name'], 'Source': self.volume['Mountpoint'],
                'Destination': '/app/local-data', 'RW': True, 'Driver': 'local'}],
            'NetworkSettings': {'Networks': {self.network['Name']: {'NetworkID': ''}}},
            'State': {'Status': 'created', 'StartedAt': '0001-01-01T00:00:00Z', 'ExitCode': 0}}
        self.window = ('2026-10-14T00:01:00+00:00', '2026-10-14T00:01:02+00:00')

    def validate(self, value=None, **kwargs):
        return validate_container(value or self.actual, self.expected, created_window=self.window, **kwargs)

    def reject(self, mutate, message=None):
        value = copy.deepcopy(self.actual)
        mutate(value)
        with self.assertRaisesRegex(RuntimeError, message or '.'):
            self.validate(value)
            forbidden()

    def test_fresh_created_metadata_has_only_reviewed_volume_network_and_no_secrets(self):
        result = self.validate(before_ids=['d' * 64])
        self.assertEqual(result['state'], 'created')
        self.assertEqual(result['ports'], 0)
        self.assertNotIn('SYNTHETIC_NOT_A_SECRET', json.dumps(result))
        self.assertEqual(self.expected['name'], self.project + '-boundary-tests-fixed-01-focused-java-02')
        self.assertFalse(any(key.startswith('com.docker.compose.') for key in result['labels']))

    def test_old_or_changed_container_id_is_refused(self):
        with self.assertRaisesRegex(RuntimeError, 'not freshly created'):
            self.validate(before_ids=[self.actual['Id']])
        with self.assertRaisesRegex(RuntimeError, 'not freshly created'):
            self.validate(container_id='d' * 64)

    def test_creation_time_outside_exact_command_is_refused(self):
        for value in ('2026-10-13T00:00:00Z', '2026-10-14T00:01:03Z'):
            self.reject(lambda actual: actual.update(Created=value), 'outside')

    def test_wrong_image_name_or_run_project_labels_refused(self):
        self.reject(lambda actual: actual.update(Image='sha256:' + 'd' * 64), 'name/image')
        self.reject(lambda actual: actual.update(Name='/dodream-phase1-be-1'), 'name/image')
        for key, value in ((LABEL_PREFIX + 'run', 'old-run'), (LABEL_PREFIX + 'project', 'dodream-phase1'),
                           ('com.docker.compose.project', self.project)):
            self.reject(lambda actual: actual['Config']['Labels'].update({key: value}), 'labels')

    def test_wrong_env_endpoint_or_extra_env_refused(self):
        for pair in ('MYSQL_HOST=host.docker.internal', 'REDIS_HOST=old-redis', 'UNREVIEWED_OVERRIDE=true'):
            self.reject(lambda actual: actual['Config']['Env'].append(pair), 'environment')

    def test_old_volume_bind_home_socket_or_extra_mount_refused(self):
        for change in ({'Name': 'dodream-phase1_be-data'}, {'Type': 'bind', 'Source': '/Users/synthetic/.local'},
                       {'Source': '/var/run/docker.sock'}, {'Destination': '/elsewhere'}, {'RW': False}):
            self.reject(lambda actual: actual['Mounts'][0].update(change), 'volume')
        self.reject(lambda actual: actual['Mounts'].append(copy.deepcopy(actual['Mounts'][0])), 'exactly one')

    def test_privileged_host_ports_or_socket_bind_flags_refused(self):
        for key, value in (('Privileged', True), ('NetworkMode', 'host'), ('PublishAllPorts', True),
                           ('PortBindings', {'8080/tcp': [{'HostPort': '25199'}]}), ('Binds', ['/var/run/docker.sock:/var/run/docker.sock']),
                           ('VolumesFrom', ['OLD_ID']), ('ExtraHosts', ['old:127.0.0.1']), ('PidMode', 'host'), ('CapAdd', ['SYS_ADMIN'])):
            self.reject(lambda actual: actual['HostConfig'].update({key: value}))

    def test_exact_selected_command_and_empty_entrypoint_required(self):
        for patch in ({'Cmd': ['gradle', 'test']}, {'Entrypoint': ['sh', '-c']}, {'User': 'root'}, {'WorkingDir': '/app'}):
            self.reject(lambda actual: actual['Config'].update(patch), 'command/user')
        self.assertEqual(COMMAND.count('--tests'), 4)
        self.assertEqual([COMMAND[index + 1] for index, part in enumerate(COMMAND) if part == '--tests'],
                         ['*.' + name.rsplit('.', 1)[1] for name in CLASSES])
        self.assertNotIn('sh', COMMAND)

    def test_runtime_network_attachment_must_match_actual_new_id(self):
        running = copy.deepcopy(self.actual)
        running['State'].update(Status='running', StartedAt='2026-10-14T00:01:03Z')
        with self.assertRaisesRegex(RuntimeError, 'network ID'):
            self.validate(running)
        running['NetworkSettings']['Networks'][self.network['Name']]['NetworkID'] = self.network['Id']
        self.assertEqual(self.validate(running)['state'], 'running')
        running['NetworkSettings']['Networks']['old-network'] = {'NetworkID': 'f' * 64}
        with self.assertRaisesRegex(RuntimeError, 'network attachment'):
            self.validate(running)

    def test_resource_limits_and_restart_policy_are_fixed(self):
        for patch in ({'Memory': 0}, {'NanoCpus': 0}, {'RestartPolicy': {'Name': 'always'}}):
            self.reject(lambda actual: actual['HostConfig'].update(patch))

    def test_image_entrypoint_anonymous_volume_or_unreviewed_target_refused(self):
        for patch in ({'Entrypoint': ['sh']}, {'Volumes': {'/home/gradle/.gradle': {}, '/unexpected': {}}}, {'Cmd': ['java']},
                      {'Labels': {'com.docker.compose.project': self.project}}):
            image = copy.deepcopy(self.image)
            image['Config'].update(patch)
            with self.assertRaises(RuntimeError):
                expected_config(self.project, self.run_id, '002-fixed-01', 'focused-java-02', image, self.environment, self.volume, self.network)

    def test_only_observed_cacert_image_entrypoint_is_allowed_and_runtime_is_empty(self):
        self.assertEqual(self.image['Config']['Entrypoint'], ['/__cacert_entrypoint.sh'])
        self.assertEqual(self.expected['entrypoint'], [])
        for entrypoint in (None, [], ['/another-entrypoint.sh'], ['/__cacert_entrypoint.sh', 'extra']):
            image = copy.deepcopy(self.image)
            image['Config']['Entrypoint'] = entrypoint
            with self.assertRaisesRegex(RuntimeError, 'entrypoint'):
                expected_config(self.project, self.run_id, '002-fixed-01', 'focused-java-02', image,
                                self.environment, self.volume, self.network)
        self.reject(lambda actual: actual['Config'].update(Entrypoint=['/__cacert_entrypoint.sh']), 'command/user')

    def test_attempt_identity_is_explicit_and_separates_container_name_and_labels(self):
        second = expected_config(self.project, self.run_id, '002-fixed-01', 'focused-java-03', self.image,
                                 self.environment, self.volume, self.network)
        self.assertNotEqual(self.expected['name'], second['name'])
        self.assertEqual(second['labels'][LABEL_PREFIX + 'attempt'], 'focused-java-03')
        for attempt in (None, '', '../old', 'UPPER', 'a' * 49):
            with self.assertRaisesRegex(RuntimeError, 'attempt'):
                expected_config(self.project, self.run_id, '002-fixed-01', attempt, self.image,
                                self.environment, self.volume, self.network)

    def test_expected_stores_must_use_same_new_trial(self):
        for change in ({'Name': 'dodream-phase1_be-data'}, {'Options': {'device': '/OLD_DATA'}},
                       {'Mountpoint': '/OLD_DATA/_data'}, {'Labels': {}}):
            with self.assertRaises(RuntimeError):
                expected_config(self.project, self.run_id, '002-fixed-01', 'focused-java-02', self.image, self.environment, {**self.volume, **change}, self.network)
        for change in ({'Name': 'bridge'}, {'Internal': False}, {'Id': 'bridge'}, {'Labels': {}}):
            with self.assertRaises(RuntimeError):
                expected_config(self.project, self.run_id, '002-fixed-01', 'focused-java-02', self.image, self.environment, self.volume, {**self.network, **change})

    def test_only_unused_declared_image_volume_is_covered_by_exact_tmpfs(self):
        for value in ({}, {'/OLD_CACHE': UNUSED_CACHE_TMPFS}, {UNUSED_IMAGE_CACHE: 'rw'},
                      {UNUSED_IMAGE_CACHE: UNUSED_CACHE_TMPFS, '/EXTRA': 'rw'}):
            self.reject(lambda actual: actual['HostConfig'].update(Tmpfs=value), 'temporary mount')
        value = copy.deepcopy(self.actual)
        value['Mounts'].append({'Type': 'tmpfs', 'Source': '', 'Destination': UNUSED_IMAGE_CACHE, 'RW': True})
        self.assertEqual(self.validate(value)['volume'], self.volume['Name'])
        value['Mounts'][1]['Destination'] = '/root/.gradle'
        with self.assertRaisesRegex(RuntimeError, 'temporary mount'):
            self.validate(value)

    def test_mount_order_normalization_preserves_source_and_every_field(self):
        original = {'containers': {'synthetic': {'state': 'created', 'mounts': [
            {'source': '/ONE', 'destination': '/first'}, {'source': '/TWO', 'destination': '/second'}]}}}
        changed = copy.deepcopy(original)
        changed['containers']['synthetic']['mounts'].reverse()
        self.assertEqual(stable_resources(original), stable_resources(changed))
        changed['containers']['synthetic']['mounts'][0]['source'] = '/OLD_DATA'
        self.assertNotEqual(stable_resources(original), stable_resources(changed))
        self.assertEqual(original['containers']['synthetic']['mounts'][0]['source'], '/ONE')

    def test_root_runtime_uses_verified_root_build_cache_not_anonymous_gradle_volume(self):
        dockerfile = """FROM gradle:8.14.3-jdk17 AS build
WORKDIR /workspace
COPY --chown=gradle:gradle build.gradle settings.gradle gradle.lockfile ./
COPY --chown=gradle:gradle src ./src
RUN gradle --no-daemon bootJar testClasses resolveTestRuntime
FROM build AS test
"""
        environment = {key: value for key, value in self.environment.items() if key not in ('HOME', 'GRADLE_USER_HOME')}
        self.assertEqual(test_environment(self.image, environment, dockerfile), self.environment)
        for key, value in (('User', 'gradle'), ('Env', ['HOME=/home/gradle']), ('Env', ['GRADLE_USER_HOME=/OLD_CACHE'])):
            image = copy.deepcopy(self.image)
            image['Config'][key] = value
            with self.assertRaises(RuntimeError):
                test_environment(image, environment, dockerfile)
        with self.assertRaisesRegex(RuntimeError, 'Build user/cache'):
            test_environment(self.image, environment, dockerfile.replace('WORKDIR /workspace', 'USER gradle\nWORKDIR /workspace'))

    def test_generated_cache_stage_preserves_original_and_refuses_other_inputs(self):
        original = "FROM gradle:8.14.3-jdk17 AS build\nFROM build AS test\n"
        generated = boundary_dockerfile(original)
        self.assertTrue(generated.startswith(original))
        self.assertIn('FROM test AS boundary-tests', generated)
        self.assertIn('test -d /home/gradle/.gradle/caches/modules-2', generated)
        self.assertIn('cp -a /home/gradle/.gradle/. ' + TEST_CACHE + '/', generated)
        receipt = validate_boundary_dockerfile(original, generated)
        self.assertEqual(receipt['cacheDestination'], TEST_CACHE)
        self.assertNotEqual(receipt['originalSha256'], receipt['generatedSha256'])
        for changed in (generated.replace('/home/gradle/.gradle/.', '/OLD_HOST_DATA/.'),
                        generated + 'COPY credentials.env /tmp/secret\n', generated.replace('FROM test AS', 'FROM other AS')):
            with self.assertRaisesRegex(RuntimeError, 'exact cache-copy'):
                validate_boundary_dockerfile(original, changed)
        with self.assertRaisesRegex(RuntimeError, 'unchanged original'):
            boundary_dockerfile(generated)

    def test_wildcard_package_selectors_require_unique_exact_reviewed_declarations(self):
        sources = {'src/test/java/' + name.replace('.', '/') + '.java':
                   'package ' + name.rsplit('.', 1)[0] + ';\nclass ' + name.rsplit('.', 1)[1] + ' {}'
                   for name in CLASSES}
        self.assertEqual(set(validate_selected_test_sources(sources)), set(CLASSES))
        for changed in ({**sources, 'src/test/java/other/Other.java': 'class IndexingObservationTests {}'},
                        {path: text for path, text in sources.items() if not path.endswith('IndexingObservationTests.java')},
                        {path: text.replace('package A704.DODREAM.indexing;', 'package other;') for path, text in sources.items()}):
            with self.assertRaises(RuntimeError):
                validate_selected_test_sources(changed)

    def test_gradle_filter_failure_is_distinct_from_plugin_or_product_failures(self):
        outcome = junit_outcome(1, '1', [], list(CLASSES), ':test No tests found for given includes [A704.DODREAM.indexing.IndexingObservationTests]')
        self.assertEqual(outcome['status'], 'FAIL')
        self.assertEqual(outcome['executionPhase'], 'GRADLE_NO_TESTS_FOUND')
        self.assertEqual(outcome['reportedJavaTests'], 0)

    def test_gradle_preparation_failure_has_explicit_zero_results_without_missing_xml_masking_cause(self):
        outcome = junit_outcome(1, '1\n', [], list(CLASSES),
                               "Plugin [id: 'org.springframework.boot', version: '3.5.7'] was not found in offline cache")
        self.assertEqual(outcome['status'], 'FAIL')
        self.assertEqual(outcome['executionPhase'], 'GRADLE_PLUGIN_RESOLUTION_FAILURE')
        self.assertEqual(outcome['reportedJavaTests'], 0)
        self.assertEqual(outcome['missingClasses'], list(CLASSES))
        self.assertEqual(junit_outcome(0, '0', [], list(CLASSES), '')['status'], 'FAIL')
        reports = [{'class': name, 'tests': 1, 'failures': 0, 'errors': 0, 'skipped': 0} for name in CLASSES]
        self.assertEqual(junit_outcome(0, '0', reports, [], '')['status'], 'PASS')
        reports[0]['skipped'] = 1
        self.assertEqual(junit_outcome(0, '0', reports, [], '')['status'], 'FAIL')

    def test_junit_export_omits_private_stdout_and_error_details_after_redaction(self):
        secret = 'SYNTHETIC_NOT_A_SECRET'
        xml = '<testsuite name="SYNTHETIC_CLASS" tests="2" failures="1" errors="0" skipped="0">' + \
              '<testcase classname="SYNTHETIC_CLASS" name="failure-' + secret + '"><failure message="' + secret + '">' + secret + \
              '</failure></testcase><system-out>' + secret + '</system-out></testsuite>'
        calls = []
        def redact(value):
            calls.append(value)
            return value.replace(secret, '[REDACTED]')
        summary = junit_summary('SYNTHETIC_CLASS', xml, redact)
        self.assertEqual(calls, [xml])
        self.assertEqual(summary['tests'], 2)
        self.assertEqual(summary['failedCases'], [{'class': 'SYNTHETIC_CLASS', 'name': 'failure-[REDACTED]'}])
        self.assertNotIn(secret, json.dumps(summary))
        self.assertNotIn('system-out', json.dumps(summary))
        with self.assertRaisesRegex(RuntimeError, 'Unexpected selected'):
            junit_summary('ANOTHER_CLASS', xml, redact)

    def test_run_refuses_other_running_services_before_any_executor(self):
        from isolated_boundary_tests import run
        runtime = mock.Mock()
        runtime.attempt_id = 'focused-java-02'
        runtime._receipt.return_value = {'expected': {}}
        runtime.observe.return_value = {'containers': {
            'mysql': {'state': 'running'}, 'redis': {'state': 'running'}, 'worker': {'state': 'running'}}}
        runtime._raw.side_effect = forbidden
        with mock.patch('isolated_provenance.validate_current'):
            with self.assertRaisesRegex(RuntimeError, 'Only new MySQL, Redis and AI'):
                run(runtime)
        runtime._raw.assert_not_called()
        runtime._resolved_config.assert_not_called()

    def test_expected_endpoints_and_fixed_source_revision_required(self):
        for patch in ({'MYSQL_HOST': 'old-mysql'}, {'MYSQL_DATABASE': 'dodream_phase1'}, {'REDIS_HOST': 'old-redis'},
                      {'LOCAL_DATA_DIR': '/OLD_DATA'}, {'AI_BASE_URL': 'https://external.invalid'}):
            with self.assertRaises(RuntimeError):
                expected_config(self.project, self.run_id, '002-fixed-01', 'focused-java-02', self.image, {**self.environment, **patch}, self.volume, self.network)
        with self.assertRaisesRegex(RuntimeError, 'fixed BE revision'):
            expected_config(self.project, self.run_id, '001-observation-01', 'focused-java-02', self.image, self.environment, self.volume, self.network)


if __name__ == '__main__':
    unittest.main(verbosity=2)
