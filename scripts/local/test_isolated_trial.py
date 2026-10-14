"""Pure offline policy tests: no Docker, sockets, credentials, or browser execution.

Run directly: python3 scripts/local/test_isolated_trial.py
Every case poisons process, network, and planner execution entry points. All
candidate mutations are in-memory; the symlink test uses only a temporary tree.
"""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest
from unittest import mock

import isolated_trial as trial


REPO = Path(__file__).resolve().parents[2]
CONFIG = REPO / 'scripts/local/isolated-trial.json'
MANIFEST = json.loads(CONFIG.read_text())
DISABLED_EXECUTE = trial.execute_invocation


def forbidden_effect(*args, **kwargs):
    raise AssertionError('Pure policy test attempted execution or network access')


class OfflineIsolationPolicyTests(unittest.TestCase):
    def setUp(self):
        self.effects = contextlib.ExitStack()
        self.addCleanup(self.effects.close)
        for module, name in (
            (subprocess, 'Popen'), (subprocess, 'run'),
            (subprocess, 'check_call'), (subprocess, 'check_output'),
            (os, 'system'), (os, 'popen'),
            (socket, 'socket'), (socket, 'create_connection'),
            (trial, 'execute_invocation'),
        ):
            self.effects.enter_context(mock.patch.object(module, name, side_effect=forbidden_effect))
        self.manifest = copy.deepcopy(MANIFEST)

    def invocation(self, suite='grading', phase='browser', operation='up'):
        manifest = copy.deepcopy(self.manifest)
        services = trial.required_services(suite, phase)
        return dict(
            manifest=manifest, repo=REPO, config_path=CONFIG,
            suite=suite, phase=phase, operation=operation, services=services,
            argv=trial.command_for(manifest, REPO, suite, phase, operation, services),
            compose=trial.candidate_compose(manifest, REPO, suite, phase),
        )

    def assert_rejected(self, invocation):
        with self.assertRaises(trial.PolicyError):
            trial.validate_invocation(**invocation)

    def test_all_suite_service_sets_and_data_phases_are_explicit(self):
        expected = {
            'auth': ['mysql', 'redis', 'be', 'ai', 'be-auth-short', 'web-auth-test'],
            'demo-disabled': ['mysql', 'redis', 'be', 'ai', 'be-auth-short', 'web-auth-test'],
            'grading': ['mysql', 'redis', 'be', 'ai', 'python-service', 'web'],
            'hardening': ['mysql', 'redis', 'be', 'ai', 'python-service', 'web', 'chroma'],
            'authorization': ['mysql', 'redis', 'be', 'ai', 'python-service', 'web', 'chroma', 'worker', 'index-dispatcher'],
            'indexing': ['mysql', 'redis', 'be', 'ai', 'python-service', 'web', 'chroma', 'worker', 'index-dispatcher'],
            'student': ['mysql', 'redis', 'be', 'ai', 'python-service', 'web', 'chroma', 'worker', 'index-dispatcher', 'be-auth-short', 'web-auth-test'],
        }
        self.assertEqual(set(trial.SUITES), set(expected))
        for suite, services in expected.items():
            with self.subTest(suite=suite):
                self.assertEqual(trial.required_services(suite, 'browser'), services)
                self.assertEqual(trial.required_services(suite, 'data'),
                                 [s for s in services if s in ('mysql', 'redis', 'chroma')])

    def test_every_suite_phase_operation_validates_without_execution(self):
        for suite in trial.SUITES:
            for phase in ('data', 'browser'):
                for operation in ('config', 'up'):
                    with self.subTest(suite=suite, phase=phase, operation=operation):
                        invocation = self.invocation(suite, phase, operation)
                        result = trial.validate_invocation(**invocation)
                        self.assertEqual(result['status'], 'PASS')
                        self.assertEqual(result['scope'], 'OFFLINE_PLAN_ONLY')
                        self.assertIs(result['executionAuthorized'], False)
                        self.assertEqual(result['resourceFreshness'], 'NOT_CHECKED')
                        self.assertEqual(result['integration'], 'NOT_RUN')
                        self.assertEqual(set(invocation['compose']['services']), set(invocation['services']))
                        for service in invocation['compose']['services'].values():
                            self.assertLessEqual(set(service.get('depends_on', {})), set(invocation['services']))

    def test_plan_contains_new_resource_targets_and_unmet_execution_conditions(self):
        plan = trial.build_plan(self.manifest, REPO, CONFIG, 'student', 'browser', 'up',
                                trial.required_services('student', 'browser'))
        self.assertEqual(plan['status'], 'PREPARED_OFFLINE_ONLY')
        self.assertIs(plan['newEnvironmentStarted'], False)
        self.assertEqual(plan['manifest'], str(CONFIG))
        self.assertEqual(plan['origin'], self.manifest['origins']['main'])
        self.assertEqual(plan['shortOrigin'], self.manifest['origins']['short'])
        self.assertEqual(plan['browserEnvironment'], {'DODREAM_ISOLATED_MANIFEST': str(CONFIG)})
        self.assertTrue(plan['prestartConditions'])
        self.assertIn('NOT_VERIFIED', plan['images'])
        self.assertIn('NOT_GENERATED', plan['credentials'])
        for effective in (*plan['effectiveVolumes'].values(), *plan['effectiveNetworks'].values()):
            self.assertTrue(effective.startswith(self.manifest['project'] + '_'))
            self.assertNotIn('dodream-phase1', effective)
        for path in plan['paths'].values():
            self.assertTrue(Path(path).is_relative_to(Path(plan['root'])))
        self.assertTrue(plan['compose']['networks']['default']['internal'])

    def test_demo_and_phase5_permissions_are_minimal_per_suite(self):
        for suite in trial.SUITES:
            with self.subTest(suite=suite):
                compose = trial.candidate_compose(self.manifest, REPO, suite, 'browser')
                main = compose['services']['be']['environment']
                self.assertEqual(main['LOCAL_DEMO_ENABLED'],
                                 'true' if suite in ('student', 'hardening') else 'false')
                self.assertEqual(main['LOCAL_PHASE5_ENABLED'], 'false')
                if 'be-auth-short' in compose['services']:
                    short = compose['services']['be-auth-short']['environment']
                    self.assertEqual(short['LOCAL_DEMO_ENABLED'], 'true' if suite == 'student' else 'false')
                    self.assertEqual(short['LOCAL_PHASE5_ENABLED'], 'false')

    def test_metadata_config_pass_cannot_authorize_up(self):
        invocation = self.invocation(operation='config')
        trial.validate_invocation(**invocation)
        invocation['argv'] = self.invocation(operation='up')['argv']
        self.assert_rejected(invocation)

    def test_up_pass_cannot_authorize_config_or_implicit_dependency_start(self):
        invocation = self.invocation()
        trial.validate_invocation(**invocation)
        for change in ('config', 'omit_no_deps', 'omit_targets'):
            candidate = copy.deepcopy(invocation)
            if change == 'config':
                candidate['argv'] = self.invocation(operation='config')['argv']
            elif change == 'omit_no_deps':
                candidate['argv'].remove('--no-deps')
            else:
                candidate['argv'] = candidate['argv'][:-len(candidate['services'])]
            with self.subTest(change=change):
                self.assert_rejected(candidate)

    def test_direct_start_with_existing_container_id_is_rejected(self):
        invocation = self.invocation()
        invocation['argv'] = ['docker', 'start', 'b5dc18999787fddd9588915ac1de776544dfaa3544a4b8569d1079a043c035f1']
        self.assert_rejected(invocation)
        invocation['operation'] = 'start'
        self.assert_rejected(invocation)

    def test_unapproved_operations_and_shell_commands_are_rejected(self):
        for operation in ('start', 'restart', 'run', 'exec', 'down', 'build', 'stop', 'metadata', ''):
            with self.subTest(operation=operation):
                invocation = self.invocation()
                invocation['operation'] = operation
                self.assert_rejected(invocation)
        for argv in ('docker compose up', ['sh', '-c', 'docker compose up'], ['docker', 'compose', 'up']):
            with self.subTest(argv=argv):
                invocation = self.invocation()
                invocation['argv'] = argv
                self.assert_rejected(invocation)

    def test_existing_named_or_external_volume_reference_is_rejected(self):
        for value in ({'external': True}, {'name': 'dodream-phase1_mysql-data'},
                      {'external': True, 'name': 'dodream-phase1_mysql-data'}):
            with self.subTest(value=value):
                invocation = self.invocation()
                invocation['compose']['volumes']['mysql-data'] = value
                self.assert_rejected(invocation)

    def test_new_volume_name_cannot_hide_old_volume_mount(self):
        invocation = self.invocation()
        invocation['compose']['volumes']['new-mysql-data'] = {}
        invocation['compose']['services']['mysql']['volumes'][0]['source'] = 'dodream-phase1_mysql-data'
        self.assert_rejected(invocation)

    def test_missing_manifest_and_old_env_fallback_are_rejected_without_reading(self):
        with mock.patch.object(Path, 'open', side_effect=forbidden_effect):
            for config in (None, '.local/env', str(REPO / '.local/env'), str(REPO / '.env')):
                with self.subTest(config=config), self.assertRaises(trial.PolicyError):
                    trial.load_manifest(config, REPO)
        for field, value in (('credentials', '../env'), ('credentials', str(REPO / '.local/env')),
                             ('root', '.local'), ('root', '.local/phase5')):
            with self.subTest(field=field, value=value):
                invocation = self.invocation()
                invocation['manifest'][field] = value
                self.assert_rejected(invocation)
        invocation = self.invocation()
        del invocation['manifest']['credentials']
        self.assert_rejected(invocation)

    def test_actual_env_file_config_project_and_root_cannot_be_substituted(self):
        for option, value in (
            ('--env-file', str(REPO / '.local/env')),
            ('--project-directory', str(REPO)),
            ('-p', 'dodream-phase1'),
            ('-f', str(REPO / 'compose.local.yml')),
        ):
            with self.subTest(option=option):
                invocation = self.invocation()
                invocation['argv'][invocation['argv'].index(option) + 1] = value
                self.assert_rejected(invocation)

    def test_old_objects_sqlite_home_and_docker_socket_binds_are_rejected(self):
        for source, target in (
            (str(REPO / '.local/objects'), '/app/local-data/objects'),
            (str(REPO / '.local/rag.db'), '/app/db_data/rag.db'),
            (str(Path.home()), '/host-home'),
            ('/var/run/docker.sock', '/var/run/docker.sock'),
        ):
            with self.subTest(source=source):
                invocation = self.invocation()
                invocation['compose']['services']['ai']['volumes'].append(
                    {'type': 'bind', 'source': source, 'target': target, 'read_only': True})
                self.assert_rejected(invocation)

    def test_new_project_cannot_use_old_db_redis_or_chroma_endpoints(self):
        mutations = (
            ('ai', 'DATABASE_URL', 'mysql+pymysql://synthetic:synthetic@host.docker.internal:3306/dodream'),
            ('ai', 'CELERY_BROKER_URL', 'redis://host.docker.internal:6379/1'),
            ('ai', 'CHROMA_HOST', 'dodream-phase1-chroma-1'),
            ('be', 'MYSQL_HOST', 'host.docker.internal'),
            ('be', 'MYSQL_DATABASE', 'dodream'),
            ('be', 'REDIS_HOST', 'dodream-phase1-redis-1'),
            ('ai', 'RAG_DATABASE_URL', 'sqlite:////old/rag.db'),
            ('ai', 'LOCAL_OBJECT_STORAGE_DIR', '/old/objects'),
        )
        for service, key, value in mutations:
            with self.subTest(service=service, setting=key):
                invocation = self.invocation('indexing')
                invocation['compose']['services'][service]['environment'][key] = value
                self.assert_rejected(invocation)

    def test_network_alias_external_gateway_and_host_network_escape_are_rejected(self):
        for mutation in ('external_network', 'named_network', 'extra_hosts', 'network_mode', 'egress'):
            with self.subTest(mutation=mutation):
                invocation = self.invocation()
                compose = invocation['compose']
                if mutation == 'external_network':
                    compose['networks']['default']['external'] = True
                elif mutation == 'named_network':
                    compose['networks']['default']['name'] = 'dodream-phase1_default'
                elif mutation == 'extra_hosts':
                    compose['services']['ai']['extra_hosts'] = ['mysql:host-gateway']
                elif mutation == 'network_mode':
                    compose['services']['ai']['network_mode'] = 'host'
                else:
                    compose['networks']['default']['internal'] = False
                self.assert_rejected(invocation)

    def test_unneeded_workers_dispatcher_and_unknown_services_are_rejected(self):
        for suite in ('auth', 'demo-disabled', 'grading', 'hardening'):
            for service in ('worker', 'index-dispatcher', 'scheduler', 'unknown'):
                with self.subTest(suite=suite, service=service):
                    invocation = self.invocation(suite)
                    invocation['services'].append(service)
                    invocation['argv'].append(service)
                    self.assert_rejected(invocation)
                    invocation = self.invocation(suite)
                    invocation['compose']['services'][service] = {'image': 'synthetic:not-run'}
                    self.assert_rejected(invocation)

    def test_missing_services_unknown_suite_phase_and_config_are_rejected(self):
        for key, value in (('services', None), ('services', []), ('suite', 'showcase'),
                           ('phase', 'prepare'), ('config_path', REPO / 'compose.local.yml')):
            with self.subTest(key=key, value=value):
                invocation = self.invocation()
                invocation[key] = value
                self.assert_rejected(invocation)
        invocation = self.invocation()
        del invocation['compose']['services']['redis']
        self.assert_rejected(invocation)

    def test_manifest_fields_roots_ports_and_unknown_keys_are_rejected(self):
        mutations = (
            ('schema', 2), ('id', 'legacy'), ('project', 'dodream-phase1'),
            ('root', '/tmp/another-project'), ('root', '.local/isolated/../env'),
            ('origins', {'main': 'http://127.0.0.1:15173', 'short': 'http://127.0.0.1:25174'}),
            ('origins', {'main': 'http://localhost:25173', 'short': 'http://127.0.0.1:25174'}),
            ('origins', {'main': 'https://example.test', 'short': 'http://127.0.0.1:25174'}),
            ('origins', {'main': 'http://127.0.0.1:25174', 'short': 'http://127.0.0.1:25174'}),
            ('origins', {'main': 'http://127.0.0.1:25173'}),
            ('extra_setting', 'not-reviewed'),
        )
        for key, value in mutations:
            with self.subTest(key=key, value=value):
                invocation = self.invocation()
                invocation['manifest'][key] = value
                self.assert_rejected(invocation)

    def test_symlink_trial_root_ancestor_and_credentials_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix='dodream-pure-policy-') as directory:
            fake_repo = Path(directory).resolve()
            config = fake_repo / 'scripts/local/isolated-trial.json'
            target = fake_repo / 'synthetic-target'
            target.mkdir()
            for suffix in ('.local', self.manifest['root'], self.manifest['root'] + '/credentials.env'):
                with self.subTest(suffix=suffix):
                    link = fake_repo / suffix
                    link.parent.mkdir(parents=True, exist_ok=True)
                    link.symlink_to(target, target_is_directory=True)
                    try:
                        with self.assertRaises(trial.PolicyError):
                            trial.validate_manifest(self.manifest, fake_repo, config)
                    finally:
                        link.unlink()

    def test_hardlinked_trial_inputs_are_rejected_without_reading_contents(self):
        with tempfile.TemporaryDirectory(prefix='dodream-pure-hardlink-') as directory:
            fake_repo = Path(directory).resolve()
            config = fake_repo / 'scripts/local/isolated-trial.json'
            source = fake_repo / 'synthetic-input.txt'
            source.write_text('SYNTHETIC_POLICY_INPUT_ONLY\n')
            for suffix in ('scripts/local/isolated-trial.json',
                           self.manifest['root'] + '/credentials.env',
                           self.manifest['root'] + '/compose.json'):
                with self.subTest(suffix=suffix):
                    linked = fake_repo / suffix
                    linked.parent.mkdir(parents=True, exist_ok=True)
                    os.link(source, linked)
                    try:
                        with mock.patch.object(Path, 'open', side_effect=forbidden_effect), \
                                self.assertRaises(trial.PolicyError):
                            trial.validate_manifest(self.manifest, fake_repo, config)
                    finally:
                        linked.unlink()

    def test_actual_execution_stays_disabled_even_for_valid_plan(self):
        invocation = self.invocation()
        self.assertEqual(trial.validate_invocation(**invocation)['status'], 'PASS')
        with self.assertRaises(trial.ExecutionDisabled):
            DISABLED_EXECUTE(**invocation, executor=forbidden_effect)

    def test_relative_or_missing_config_and_nonobject_manifest_are_rejected(self):
        for config in (None, 'scripts/local/isolated-trial.json'):
            with self.subTest(config=config):
                invocation = self.invocation()
                invocation['config_path'] = config
                self.assert_rejected(invocation)
        for manifest in (None, [], 'synthetic-but-not-config'):
            with self.subTest(manifest=manifest):
                invocation = self.invocation()
                invocation['manifest'] = manifest
                self.assert_rejected(invocation)

    def test_ambient_compose_docker_and_connection_settings_cannot_override_plan(self):
        for environment in (
            {'COMPOSE_FILE': str(REPO / 'compose.local.yml')},
            {'COMPOSE_PROJECT_NAME': 'dodream-phase1'},
            {'DOCKER_HOST': 'tcp://example.invalid:2375'},
            {'DOCKER_CONTEXT': 'unreviewed'},
            {'DATABASE_URL': 'mysql://old-db/example'},
            {'CELERY_BROKER_URL': 'redis://old-redis/1'},
            {'CHROMA_HOST': 'old-chroma'},
            {'ISOLATED_MYSQL_PASSWORD': 'SYNTHETIC_NOT_A_CREDENTIAL'},
        ):
            with self.subTest(keys=list(environment)):
                invocation = self.invocation()
                invocation['environment'] = environment
                self.assert_rejected(invocation)
        invocation = self.invocation()
        invocation['environment'] = {}
        self.assertEqual(trial.validate_invocation(**invocation)['status'], 'PASS')

    def test_supplied_inventory_is_pure_and_never_grants_execution(self):
        plan = trial.build_plan(self.manifest, REPO, CONFIG, 'grading', 'data', 'up',
                                trial.required_services('grading', 'data'))
        inventory = {'containers': [{'id': 'SYNTHETIC_OLD_ID', 'name': 'dodream-phase1-mysql-1',
                                    'project': 'dodream-phase1', 'volumes': ['dodream-phase1_mysql-data'],
                                    'networks': ['dodream-phase1_default']}],
                     'volumes': ['dodream-phase1_mysql-data'], 'networks': ['dodream-phase1_default']}
        result = trial.validate_fresh_inventory(plan, inventory)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['scope'], 'SUPPLIED_METADATA_ONLY')
        self.assertIs(result['executionAuthorized'], False)
        with self.assertRaises(trial.ExecutionDisabled):
            DISABLED_EXECUTE(plan, metadata=inventory, executor=forbidden_effect)

    def test_existing_trial_named_resources_cannot_be_adopted(self):
        plan = trial.build_plan(self.manifest, REPO, CONFIG, 'grading', 'data', 'up',
                                trial.required_services('grading', 'data'))
        volume = next(iter(plan['effectiveVolumes'].values()))
        network = next(iter(plan['effectiveNetworks'].values()))
        for collision in ('volume', 'network', 'container_project', 'container_name', 'container_volume', 'container_network'):
            with self.subTest(collision=collision):
                inventory = {'containers': [], 'volumes': [], 'networks': []}
                if collision == 'volume':
                    inventory['volumes'] = [volume]
                elif collision == 'network':
                    inventory['networks'] = [network]
                else:
                    row = {'id': 'SYNTHETIC_EXISTING_ID', 'name': 'synthetic-other-name',
                           'project': 'synthetic-other-project', 'volumes': [], 'networks': []}
                    if collision == 'container_project':
                        row['project'] = plan['project']
                    elif collision == 'container_name':
                        row['name'] = plan['project'] + '-mysql-1'
                    elif collision == 'container_volume':
                        row['volumes'] = [volume]
                    else:
                        row['networks'] = [network]
                    inventory['containers'] = [row]
                with self.assertRaises(trial.PolicyError):
                    trial.validate_fresh_inventory(plan, inventory)

    def test_incomplete_or_secret_bearing_metadata_is_rejected(self):
        plan = trial.build_plan(self.manifest, REPO, CONFIG, 'grading', 'data', 'up',
                                trial.required_services('grading', 'data'))
        for inventory in (None, {}, {'containers': [], 'volumes': []},
                          {'containers': [], 'volumes': {}, 'networks': []},
                          {'containers': [], 'volumes': [123], 'networks': []},
                          {'containers': [{'id': 'SYNTHETIC', 'env': {'VALUE': 'SYNTHETIC'}}],
                           'volumes': [], 'networks': []}):
            with self.subTest(inventory=inventory), self.assertRaises(trial.PolicyError):
                trial.validate_fresh_inventory(plan, inventory)

    def test_cli_plan_is_json_only_and_does_not_read_or_create_credentials(self):
        real_open = Path.open
        allowed_reads = {CONFIG, *(REPO / p for p in (
            'compose.local.yml', 'scripts/local/nginx.auth-test.conf', 'fe-web/nginx.local.conf',
            'be/Dockerfile.local', 'ai/Dockerfile.local', 'fe-web/Dockerfile.local',
            'python-service/Dockerfile.local', 'scripts/local/chroma/Dockerfile.local'))}

        def only_reviewed_source_reads(path, mode='r', *args, **kwargs):
            self.assertIn(Path(path), allowed_reads)
            self.assertNotIn('w', mode)
            self.assertNotIn('a', mode)
            self.assertNotIn('+', mode)
            return real_open(path, mode, *args, **kwargs)

        output = io.StringIO()
        with mock.patch.object(Path, 'open', only_reviewed_source_reads), \
                mock.patch.object(Path, 'mkdir', side_effect=forbidden_effect), \
                contextlib.redirect_stdout(output):
            code = trial.main(['--manifest', str(CONFIG), '--suite', 'auth', '--phase', 'browser',
                               '--operation', 'up', '--services', *trial.required_services('auth', 'browser')])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())['status'], 'PREPARED_OFFLINE_ONLY')

    def test_cli_refuses_missing_or_old_config_with_nonzero_status(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            trial.main([])
        self.assertEqual(raised.exception.code, 2)
        with contextlib.redirect_stderr(io.StringIO()), mock.patch.object(Path, 'open', side_effect=forbidden_effect):
            code = trial.main(['--manifest', str(REPO / '.local/env'), '--suite', 'grading',
                               '--phase', 'browser', '--operation', 'up', '--services',
                               *trial.required_services('grading', 'browser')])
        self.assertEqual(code, 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
