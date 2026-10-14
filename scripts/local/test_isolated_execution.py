"""Actual TrialRuntime wiring with synthetic files and Docker/process fail-closed doubles."""
import contextlib
import copy
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest
from unittest import mock

import isolated_trial as trial
import isolated_provenance as policy
from test_isolated_provenance import scenario, compose_scenario, RUN_ID, BEGIN, END


def forbidden(*args, **kwargs):
    raise AssertionError('Pure execution wiring test attempted a real process or network operation')


class IsolatedExecutionWiringTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        for module, name in ((subprocess, 'run'), (subprocess, 'Popen'), (subprocess, 'check_output'),
                             (subprocess, 'check_call'), (os, 'system'), (os, 'popen'),
                             (socket, 'socket'), (socket, 'create_connection')):
            self.stack.enter_context(mock.patch.object(module, name, side_effect=forbidden))
        directory = self.stack.enter_context(tempfile.TemporaryDirectory(prefix='dodream-pure-execution-'))
        self.root = Path(directory).resolve()
        self.runtime = runtime = trial.TrialRuntime.__new__(trial.TrialRuntime)
        runtime.repo = self.root / 'synthetic-repo'
        runtime.root = self.root
        runtime.results = self.root / 'results'
        runtime.results.mkdir()
        runtime.credentials_path = self.root / 'credentials.env'
        runtime.manifest_path = runtime.repo / 'scripts/local/isolated-trial.json'
        runtime.run_id = RUN_ID
        runtime.project = 'dodream-evidence-20261014'
        runtime.host = 'unix:///synthetic/docker.sock'
        runtime.docker = '/synthetic/docker'
        runtime.manifest = {'schema': 1, 'id': 'evidence-portability-20261014', 'project': runtime.project,
                            'root': '.local/isolated/evidence-portability-20261014', 'credentials': 'credentials.env',
                            'origins': {'main': 'http://127.0.0.1:25173', 'short': 'http://127.0.0.1:25174'}}
        runtime.origins = runtime.manifest['origins']
        runtime.preparation = {'configHashes': {}}
        self.before, self.observed, self.expected = scenario()
        base_row = copy.deepcopy(self.observed['containers']['mysql'])
        base_spec = copy.deepcopy(self.expected['services']['mysql'])
        names = set().union(*trial.SUITES.values()) | {'be-student-short', 'web-student-short'}
        for index, name in enumerate(sorted(names), 1):
            self.observed['containers'][name] = {**copy.deepcopy(base_row), 'id': f'{index:064x}', 'service': name}
            self.expected['services'][name] = copy.deepcopy(base_spec)
        self.receipt = policy.validate_created(self.before, self.observed, self.expected, RUN_ID, BEGIN, END)
        runtime._receipt = mock.Mock(return_value=self.receipt)
        runtime.observe = mock.Mock(side_effect=lambda expected: copy.deepcopy(self.observed))
        runtime.verify_pending_work = mock.Mock()
        self.calls = []
        def execute(args, **kwargs):
            self.calls.append((args, kwargs))
            return subprocess.CompletedProcess(args, 0, stdout='', stderr='')
        runtime._raw = mock.Mock(side_effect=execute)
        (self.root / 'creation-intent.json').write_text(json.dumps({'expected': self.expected}))
        (self.root / 'active-stage.json').write_text(json.dumps({'suite': 'auth', 'phase': 'browser', 'runId': RUN_ID}))

    def start_record(self, names):
        (self.root / 'operations.jsonl').write_text(json.dumps({'operation': 'start', 'services': names, 'ids': [self.observed['containers'][name]['id'] for name in names]}) + '\n')
        for name in names:
            self.observed['containers'][name].update(state='running', startedAt=END)

    def completed_create_evidence(self):
        """Only temporary synthetic files, never a real trial's creation evidence."""
        raw, _ = compose_scenario()
        images = {'synthetic-image': {'id': 'sha256:' + 'a' * 64}}
        before = {**copy.deepcopy(self.before), 'frozen': [], 'rows': []}
        argv = ['compose', '--project-directory', str(self.root), '--env-file', str(self.runtime.credentials_path),
                '-p', self.runtime.project, '-f', str(self.root / 'compose.json'),
                'create', '--no-build', '--no-recreate', '--pull', 'never', *self.expected['services']]
        intent = {'runId': RUN_ID, 'manifestDigest': trial.digest(self.runtime.manifest),
                  'composeDigest': trial.digest(raw), 'expected': self.expected,
                  'before': before, 'argv': argv, 'startedAt': BEGIN, 'status': 'INCOMPLETE'}
        (self.root / 'creation-intent.json').write_text(json.dumps(intent))
        (self.root / 'compose.json').write_text(json.dumps(raw))
        (self.root / 'creation-observed.json').write_text(json.dumps(self.observed))
        record = {'runId': RUN_ID, 'exitCode': 0, 'argv': json.dumps([*self.runtime._prefix(), *argv]),
                  'startedAt': BEGIN, 'finishedAt': END}
        path = self.runtime.results / 'synthetic-create.json'
        path.write_text(json.dumps(record))
        current = {'containers': before['containers'] + [r['id'] for r in self.observed['containers'].values()],
                   'volumes': before['volumes'] + list(self.expected['volumes']),
                   'networks': before['networks'] + list(self.expected['networks']), 'frozen': []}
        self.runtime.preparation['before'] = before
        self.runtime.inventory = mock.Mock(return_value=current)
        self.runtime._resolved_config = mock.Mock(return_value=(raw, raw, images))
        self.runtime._expected = mock.Mock(return_value=self.expected)
        self.runtime.verify_image_sources = mock.Mock(return_value={'status': 'SYNTHETIC_ONLY'})
        return path, record

    def test_auth_start_calls_only_verified_new_ids_and_records_intent(self):
        self.runtime._operation('start', ['mysql', 'redis'])
        ids = [self.observed['containers'][name]['id'] for name in ('mysql', 'redis')]
        self.assertEqual(self.calls[0][0], ['start', *ids])
        self.assertEqual(self.runtime._started(), {'mysql', 'redis'})
        self.runtime.verify_pending_work.assert_not_called()
        self.runtime.observe.assert_called_once()

    def test_missing_receipt_and_config_only_pass_cannot_start(self):
        self.runtime._receipt.side_effect = FileNotFoundError('Synthetic missing creation receipt')
        with self.assertRaises(FileNotFoundError):
            self.runtime._operation('start', ['mysql'])
        self.assertFalse(self.calls)

    def test_existing_id_and_unexpected_metadata_reject_before_mutation(self):
        self.observed['containers']['mysql']['id'] = self.before['containers'][0]
        with self.assertRaises(policy.ProvenanceError):
            self.runtime._operation('start', ['mysql'])
        self.assertFalse(self.calls)

    def test_implicit_services_old_ids_and_consumers_reject_in_auth(self):
        for names in ([], ['mysql', 'mysql'], ['dodream-phase1-mysql-1'], [self.before['containers'][0]], ['worker'], ['index-dispatcher']):
            with self.subTest(names=names), self.assertRaises((trial.PolicyError, policy.ProvenanceError)):
                self.runtime._operation('start', names)
        self.runtime.verify_pending_work.assert_not_called()
        self.assertFalse(self.calls)

    def test_unknown_operation_does_not_reuse_valid_start_scope(self):
        for operation in ('config', 'up', 'restart', 'down', 'run', 'rm'):
            with self.subTest(operation=operation), self.assertRaises((trial.PolicyError, policy.ProvenanceError)):
                self.runtime._operation(operation, ['mysql'])
        self.assertFalse(self.calls)

    def test_stop_exec_pause_cannot_target_unstarted_services(self):
        for operation in ('stop', 'pause', 'exec'):
            with self.subTest(operation=operation), self.assertRaises((trial.PolicyError, policy.ProvenanceError)):
                self.runtime._operation(operation, ['mysql'], payload=['redis-cli', 'ping'] if operation == 'exec' else None)
        self.assertFalse(self.calls)

    def test_cleanup_stops_only_started_new_ids_after_stage_changes(self):
        self.start_record(['mysql'])
        (self.root / 'active-stage.json').write_text(json.dumps({'suite': 'grading', 'phase': 'browser', 'runId': RUN_ID}))
        self.runtime._operation('stop', ['mysql'])
        self.assertEqual(self.calls[0][0], ['stop', '--time', '20', self.observed['containers']['mysql']['id']])
        with self.assertRaises((trial.PolicyError, policy.ProvenanceError)):
            self.runtime._operation('stop', ['redis'])

    def test_failed_start_retains_new_intent_for_bounded_error_cleanup(self):
        self.runtime._raw.side_effect = RuntimeError('Synthetic interrupted start')
        with self.assertRaises(RuntimeError):
            self.runtime._operation('start', ['mysql'])
        self.assertEqual(self.runtime._started(), {'mysql'})
        self.assertNotIn('worker', self.runtime._started())

    def test_exec_rejects_old_endpoints_and_deletion_sql_before_command(self):
        self.start_record(['mysql'])
        for payload, stdin in ((['sh', '-c', 'curl http://host.docker.internal:3306'], None),
                                (['sh', '-c', 'cat /old/.local/env'], None),
                                (['sh', '-c', 'mysql'], 'DELETE FROM synthetic;'),
                                (['sh', '-c', 'mysql'], 'TRUNCATE synthetic;'),
                                (['docker', 'start', 'old-id'], None)):
            with self.subTest(payload=payload, stdin=stdin), self.assertRaises(trial.PolicyError):
                self.runtime._operation('exec', ['mysql'], payload=payload, stdin=stdin)
        self.assertFalse(self.calls)

    def test_suite_data_phase_and_wrong_run_cursor_fail_closed(self):
        for stage in ({'suite': 'auth', 'phase': 'data', 'runId': RUN_ID},
                      {'suite': 'auth', 'phase': 'browser', 'runId': 'old-run'}):
            (self.root / 'active-stage.json').write_text(json.dumps(stage))
            with self.subTest(stage=stage), self.assertRaises(trial.PolicyError):
                self.runtime._operation('start', ['be'])
        self.assertFalse(self.calls)

    def test_student_uses_separate_created_short_services(self):
        (self.root / 'active-stage.json').write_text(json.dumps({'suite': 'student', 'phase': 'browser', 'runId': RUN_ID}))
        self.runtime._operation('start', ['be-student-short'])
        self.assertEqual(self.calls[0][0], ['start', self.observed['containers']['be-student-short']['id']])
        with self.assertRaises(trial.PolicyError):
            self.runtime._operation('start', ['be-auth-short'])

    def test_consumers_require_current_suite_and_pending_fixture_guard(self):
        (self.root / 'active-stage.json').write_text(json.dumps({'suite': 'indexing', 'phase': 'browser', 'runId': RUN_ID}))
        self.runtime.verify_pending_work.side_effect = trial.PolicyError('Synthetic unowned queued work')
        with self.assertRaises(trial.PolicyError):
            self.runtime._operation('start', ['worker'])
        self.runtime.verify_pending_work.assert_called_once()
        self.assertFalse(self.calls)

    def test_legacy_up_translates_explicit_services_to_guarded_start_not_compose_up(self):
        self.runtime.wait_healthy = mock.Mock()
        self.runtime.compose('synthetic-up', 'up', '-d', '--no-deps', '--wait', '--wait-timeout', '180', 'mysql')
        self.assertEqual(self.calls[0][0], ['start', self.observed['containers']['mysql']['id']])
        self.runtime.wait_healthy.assert_called_once_with(['mysql'])
        with self.assertRaises(trial.PolicyError):
            self.runtime.compose('synthetic-whole-up', 'up', '-d')

    def test_running_recorded_service_is_an_explicit_idempotent_noop(self):
        self.start_record(['mysql'])
        self.runtime.wait_healthy = mock.Mock()
        result = self.runtime.compose('synthetic-running', 'up', '-d', '--no-deps', 'mysql')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, 'NO_NEW_OPERATION\n')
        self.assertFalse(self.calls)
        self.runtime.observe.assert_called_once()
        self.assertGreaterEqual(self.runtime._receipt.call_count,1)
        self.runtime.wait_healthy.assert_called_once_with(['mysql'])

    def test_running_service_without_this_runs_start_record_cannot_be_adopted(self):
        self.observed['containers']['mysql'].update(state='running', startedAt=END)
        self.runtime.wait_healthy = mock.Mock()
        with self.assertRaisesRegex(trial.PolicyError, 'start record'):
            self.runtime.compose('synthetic-unowned-running', 'up', '-d', 'mysql')
        self.assertFalse(self.calls)
        self.runtime.wait_healthy.assert_not_called()

    def test_running_recorded_consumer_still_rejects_in_auth_stage(self):
        self.start_record(['worker'])
        self.runtime.wait_healthy = mock.Mock()
        with self.assertRaisesRegex(trial.PolicyError, 'active stage'):
            self.runtime.compose('synthetic-auth-worker', 'up', '-d', 'worker')
        self.assertFalse(self.calls)
        self.runtime.wait_healthy.assert_not_called()
        self.runtime.verify_pending_work.assert_not_called()

    def test_create_rejects_effective_old_mount_before_creation(self):
        raw, effective = compose_scenario()
        effective['services']['web']['volumes'][0]['source'] = 'dodream-phase1_mysql-data'
        (self.root / 'creation-intent.json').unlink()  # Synthetic test-owned fixture only.
        self.runtime.preparation['before'] = copy.deepcopy(self.before)
        self.runtime.inventory = mock.Mock(return_value=copy.deepcopy(self.before))
        self.runtime._resolved_config = mock.Mock(return_value=(raw, raw, {}))
        self.runtime.configure_client = mock.Mock()
        self.runtime.verify_image_sources = mock.Mock(return_value={'status': 'SYNTHETIC_ONLY'})
        self.runtime._expected = mock.Mock(return_value=self.expected)
        self.runtime._raw.side_effect = lambda args, **kwargs: subprocess.CompletedProcess(args, 0, stdout=json.dumps(effective), stderr='')
        with self.assertRaises(policy.ProvenanceError):
            self.runtime.create()
        self.assertEqual(self.runtime._raw.call_count, 1)
        self.assertIn('config', self.runtime._raw.call_args.args[0])
        self.assertFalse((self.root / 'creation-intent.json').exists())
        self.assertFalse((self.root / 'creation.json').exists())

    def test_observe_normalizes_binds_without_volume_only_fields(self):
        before, observed, expected = scenario()
        container = observed['containers']['mysql']
        environment = ['SYNTHETIC=NOT_A_SECRET']
        container['envHash'] = trial.digest([['SYNTHETIC', 'NOT_A_SECRET']])
        expected['services']['mysql']['envHash'] = container['envHash']
        bind = {'type': 'bind', 'source': '/synthetic/new-trial/nginx.conf', 'destination': '/config', 'rw': False}
        container['mounts'].append(copy.deepcopy(bind))
        expected['services']['mysql']['mounts'].append(copy.deepcopy(bind))
        raw_container = {'Id': container['id'], 'Image': container['image'], 'Created': container['created'],
            'State': {'Status': 'created', 'StartedAt': container['startedAt']},
            'Config': {'Labels': {'com.docker.compose.project': self.runtime.project,
                        'com.docker.compose.service': 'mysql', trial.RUN_LABEL: RUN_ID},
                       'Cmd': container['command'], 'Entrypoint': container['entrypoint'], 'Env': environment},
            'Mounts': [{'Type': mount['type'], 'Name': mount.get('name', ''), 'Source': mount['source'],
                        'Destination': mount['destination'], 'RW': mount['rw']} for mount in container['mounts']],
            'NetworkSettings': {'Networks': {key: {'NetworkID': value} for key, value in container['networks'].items()}},
            'HostConfig': {'NetworkMode': next(iter(container['networks'])), 'Privileged': False, 'PortBindings': {}}}
        def metadata(args):
            if args[0] == 'inspect':
                return [raw_container]
            if args[:2] == ['volume', 'inspect']:
                row = observed['volumes'][args[2]]
                return [{'Name': row['name'], 'Driver': row['driver'], 'Options': row['options'],
                         'CreatedAt': row['created'], 'Labels': row['labels']}]
            if args[:2] == ['network', 'inspect']:
                row = observed['networks'][args[2]]
                return [{'Name': row['name'], 'Driver': row['driver'], 'Options': row['options'],
                         'Created': row['created'], 'Labels': row['labels'], 'Id': row['id'], 'Internal': row['internal']}]
            self.fail('Unexpected metadata command')
        self.runtime._json = mock.Mock(side_effect=metadata)
        self.runtime._raw.side_effect = lambda args, **kwargs: subprocess.CompletedProcess(args, 0, stdout=container['id'] + '\n')
        normalized = trial.TrialRuntime.observe(self.runtime, expected)
        self.assertEqual(normalized, observed)
        policy.validate_created(before, normalized, expected, RUN_ID, BEGIN, END)

    def test_receipt_wrapper_returns_only_verified_provenance_and_rejects_config_drift(self):
        raw, _ = compose_scenario()
        images = {'mysql': {'id': 'sha256:' + 'a' * 64, 'source': {'digest': 'SYNTHETIC'}}}
        wrapped = {'provenance': self.receipt, 'manifestDigest': trial.digest(self.runtime.manifest),
                   'composeDigest': trial.digest(raw), 'sourceDigest': trial.digest(images)}
        (self.root / 'creation.json').write_text(json.dumps(wrapped))
        (self.root / 'compose.json').write_text(json.dumps(raw))
        self.runtime._resolved_config = mock.Mock(return_value=(raw, raw, images))
        self.assertEqual(trial.TrialRuntime._receipt(self.runtime), self.receipt)
        changed = copy.deepcopy(raw)
        changed['services']['web']['command'] = ['sh']
        (self.root / 'compose.json').write_text(json.dumps(changed))
        with self.assertRaises(trial.PolicyError):
            trial.TrialRuntime._receipt(self.runtime)

    def test_resolved_config_replaces_base64_digit_key_with_only_synthetic_credentials(self):
        components = ('be', 'ai', 'python-service', 'web', 'chroma', 'mysql', 'redis')
        images = {name: {'id': 'sha256:' + f'{index:064x}'} for index, name in enumerate(components, 1)}
        (self.root / 'images.json').write_text(json.dumps(images))
        values = {'ISOLATED_' + key: 'SYNTHETIC_NOT_A_SECRET_' + key for key in
                  ('MYSQL_PASSWORD', 'MYSQL_ROOT_PASSWORD', 'JWT_SECRET_BASE64', 'TEACHER_PASSWORD', 'STUDENT_SECRET')}
        self.runtime._credentials = mock.Mock(return_value=values)
        raw, resolved, recorded = trial.TrialRuntime._resolved_config(self.runtime)
        self.assertEqual(recorded, images)
        self.assertIn('${ISOLATED_JWT_SECRET_BASE64:', raw['services']['be']['environment']['JWT_SECRET'])
        for name in ('be', 'be-auth-short', 'be-student-short'):
            self.assertEqual(resolved['services'][name]['environment']['JWT_SECRET'], values['ISOLATED_JWT_SECRET_BASE64'])
        for name in ('ai', 'worker', 'index-dispatcher'):
            self.assertEqual(resolved['services'][name]['environment']['JWT_SECRET_BASE64'], values['ISOLATED_JWT_SECRET_BASE64'])
        self.assertNotIn('${ISOLATED_', json.dumps(resolved))
        self.runtime._credentials.assert_called_once()
        self.assertFalse(self.calls)

    def test_verify_created_completes_only_preserved_successful_never_started_creation(self):
        self.completed_create_evidence()
        result = self.runtime.verify_created()
        self.assertEqual(result['status'], 'CREATED_VERIFIED')
        self.assertFalse(result['started'])
        wrapped = json.loads((self.root / 'creation.json').read_text())
        self.assertEqual(wrapped['creationExitCode'], 0)
        self.assertEqual(wrapped['provenance']['resources'], self.observed)
        policy.validate_current(wrapped['provenance'], self.observed)
        self.assertFalse(self.calls)
        self.runtime.verify_image_sources.assert_called_once()

    def test_verify_created_refuses_missing_or_failed_original_create_record(self):
        path, record = self.completed_create_evidence()
        path.unlink()  # Synthetic test-owned file only.
        with self.assertRaisesRegex(trial.PolicyError, 'successful create record'):
            self.runtime.verify_created()
        path.write_text(json.dumps({**record, 'exitCode': 2}))
        with self.assertRaisesRegex(trial.PolicyError, 'successful create record'):
            self.runtime.verify_created()
        self.assertFalse((self.root / 'creation.json').exists())
        self.assertFalse(self.calls)

    def test_verify_created_refuses_original_observation_drift(self):
        self.completed_create_evidence()
        changed = copy.deepcopy(self.observed)
        changed['containers']['mysql']['image'] = 'sha256:' + 'f' * 64
        (self.root / 'creation-observed.json').write_text(json.dumps(changed))
        with self.assertRaises((trial.PolicyError, policy.ProvenanceError)):
            self.runtime.verify_created()
        self.assertFalse((self.root / 'creation.json').exists())
        self.assertFalse(self.calls)

    def test_verify_created_refuses_any_prior_start_intent_even_without_actual_start(self):
        self.completed_create_evidence()
        (self.root / 'operations.jsonl').write_text(json.dumps({'operation': 'start', 'services': ['mysql']}) + '\n')
        with self.assertRaisesRegex(trial.PolicyError, 'not adoption or a start retry'):
            self.runtime.verify_created()
        self.assertFalse((self.root / 'creation.json').exists())
        self.runtime.inventory.assert_not_called()
        self.assertFalse(self.calls)

    def test_verify_created_accepts_only_mount_order_change_in_current_never_started_metadata(self):
        bind = {'type': 'bind', 'source': '/synthetic/new-trial/nginx.conf', 'destination': '/config', 'rw': False}
        self.expected['services']['mysql']['mounts'].append(copy.deepcopy(bind))
        self.observed['containers']['mysql']['mounts'].append(copy.deepcopy(bind))
        self.completed_create_evidence()
        self.observed['containers']['mysql']['mounts'].reverse()
        result = self.runtime.verify_created()
        self.assertEqual(result['status'], 'CREATED_VERIFIED')
        self.assertFalse(result['started'])
        wrapped = json.loads((self.root / 'creation.json').read_text())
        self.assertNotEqual(wrapped['provenance']['resources']['containers']['mysql']['mounts'],
                            self.observed['containers']['mysql']['mounts'])
        policy.validate_current(wrapped['provenance'], self.observed)
        self.assertFalse(self.calls)


    def test_retired_container_start_record_does_not_authorize_replacement(self):
        self.start_record(['be'])
        newer=copy.deepcopy(self.receipt)
        newer['resources']['containers']['be']['id']='9'*64
        self.runtime._receipt.return_value=newer
        self.assertNotIn('be',self.runtime._started())

    def test_incomplete_revision_blocks_all_current_receipt_resolution(self):
        directory=self.root/'revisions/001-observation-01'
        directory.mkdir(parents=True)
        (directory/'recreate-intent.json').write_text('{}')
        with self.assertRaisesRegex(trial.PolicyError,'Incomplete BE recreation'):
            self.runtime._revision_records()
        self.assertFalse(self.calls)

    def test_revision_running_service_rejected_before_build_or_recreation(self):
        self.observed['containers']['mysql'].update(state='running',startedAt=END)
        with self.assertRaisesRegex(trial.PolicyError,'must be stopped'):
            self.runtime.revise_be('observation-01')
        self.assertFalse(self.calls)

    def test_revision_unknown_identifier_rejected_before_metadata_or_execution(self):
        for name in ('../old','observation','be','fixed-1','fixed-001',''):
            with self.subTest(name=name),self.assertRaises(trial.PolicyError):
                self.runtime.revise_be(name)
        self.runtime.observe.assert_not_called()
        self.assertFalse(self.calls)

    def test_attempt_directories_are_exclusive_and_bind_current_source(self):
        self.runtime.attempt_id='fixed-boundary-01'
        self.runtime.attempt_root=self.root/'attempts'/self.runtime.attempt_id
        self.runtime.results=self.runtime.attempt_root/'results'
        self.runtime.fixtures=self.runtime.attempt_root/'fixtures'
        self.runtime.plans=self.runtime.attempt_root/'browser-ui'
        self.runtime._image_records=mock.Mock(return_value={})
        self.runtime.verify_image_sources=mock.Mock()
        self.runtime.source_identity=mock.Mock(return_value={'working_source_sha256':'a'*64})
        self.runtime.prepare_attempt()
        row=json.loads((self.runtime.attempt_root/'attempt.json').read_text())
        self.assertEqual(row['currentProvenanceDigest'],trial.digest(self.receipt))
        self.assertEqual(row['attemptId'],'fixed-boundary-01')
        self.assertEqual(row['runId'],RUN_ID)
        self.assertEqual(self.runtime.clean_env()['DODREAM_ISOLATED_ATTEMPT'],'fixed-boundary-01')
        with self.assertRaisesRegex(trial.PolicyError,'already exists'):
            self.runtime.prepare_attempt()
        self.assertFalse(self.calls)

    def bound_attempt(self):
        runtime=self.runtime
        runtime.attempt_id='fixed-01';runtime.attempt_root=self.root/'attempts/fixed-01'
        runtime.attempt_root.mkdir(parents=True)
        images={'be':{'id':'sha256:'+'a'*64,'source':{'sourceDigest':'b'*64}}}
        runtime._image_records=mock.Mock(return_value=images)
        identity={'working_source_sha256':trial.digest({'be':'b'*64})}
        row={'schema':1,'attemptId':runtime.attempt_id,'trialId':runtime.manifest['id'],
             'project':runtime.project,'runId':runtime.run_id,'currentProvenanceDigest':trial.digest(self.receipt),'source':identity}
        (runtime.attempt_root/'attempt.json').write_text(json.dumps(row))
        passed={'status':'PASS','runId':runtime.run_id,'attemptId':runtime.attempt_id,
                'currentProvenanceDigest':trial.digest(self.receipt),'source':identity}
        (runtime.attempt_root/'auth-pass.json').write_text(json.dumps(passed))
        return row,passed

    def test_attempt_checks_current_source_and_provenance_before_stage_or_start(self):
        row,passed=self.bound_attempt()
        self.runtime.set_stage('indexing')
        stage=json.loads((self.root/'active-stage.json').read_text())
        self.assertEqual(stage['attemptId'],'fixed-01')
        for field,value in (('currentProvenanceDigest','0'*64),('source',{'working_source_sha256':'0'*64})):
            stale={**row,field:value}
            (self.runtime.attempt_root/'attempt.json').write_text(json.dumps(stale))
            with self.assertRaisesRegex(trial.PolicyError,'another image/source/provenance'):
                self.runtime.set_stage('indexing')
            with self.assertRaisesRegex(trial.PolicyError,'another image/source/provenance'):
                self.runtime._operation('start',['mysql'])
        self.assertFalse(self.calls)

    def test_attempt_refuses_another_images_auth_pass_even_with_matching_run_id(self):
        row,passed=self.bound_attempt()
        for field,value in (('attemptId','observation-01'),('currentProvenanceDigest','0'*64),
                            ('source',{'working_source_sha256':'0'*64})):
            (self.runtime.attempt_root/'auth-pass.json').write_text(json.dumps({**passed,field:value}))
            with self.assertRaisesRegex(trial.PolicyError,'Auth PASS is not from this attempt'):
                self.runtime.set_stage('indexing')
        self.assertFalse(self.calls)

    def test_stale_attempt_does_not_block_receipted_cleanup(self):
        row,passed=self.bound_attempt()
        self.start_record(['mysql'])
        (self.runtime.attempt_root/'attempt.json').write_text(json.dumps({**row,'currentProvenanceDigest':'0'*64}))
        self.runtime._operation('stop',['mysql'])
        self.assertEqual(self.calls[-1][0],['stop','--time','20',self.observed['containers']['mysql']['id']])

    def test_attempt_cannot_borrow_another_attempts_active_stage(self):
        self.bound_attempt();self.runtime.set_stage('auth','data')
        stage=json.loads((self.root/'active-stage.json').read_text());stage['attemptId']='observation-01'
        (self.root/'active-stage.json').write_text(json.dumps(stage))
        with self.assertRaisesRegex(trial.PolicyError,'Active stage belongs to another attempt'):
            self.runtime._operation('start',['mysql'])
        self.assertFalse(self.calls)

    def test_revision_without_attempt_cannot_reuse_initial_auth_gate(self):
        self.runtime._receipt.return_value={'schema':2}
        with self.assertRaisesRegex(trial.PolicyError,'separately bound integration attempt'):
            self.runtime.set_stage('auth')
        self.assertFalse(self.calls)

    def test_revision_recreates_only_three_be_services_without_start(self):
        from test_isolated_provenance import ZERO
        runtime=self.runtime
        runtime.preparation['before']={'frozen':[]}
        images={name:{'id':self.expected['services']['mysql']['image']} for name in
                ('be','ai','python-service','web','chroma','mysql','redis')}
        runtime._image_records=mock.Mock(return_value=images)
        runtime.verify_image_sources=mock.Mock()
        runtime._credentials=mock.Mock(return_value={'ISOLATED_'+key:'SYNTHETIC_NOT_SECRET' for key in
            ('MYSQL_PASSWORD','MYSQL_ROOT_PASSWORD','JWT_SECRET_BASE64','TEACHER_PASSWORD','STUDENT_SECRET')})
        new_image='sha256:'+'f'*64
        new_expected=copy.deepcopy(self.receipt['expected'])
        after=copy.deepcopy(self.observed)
        for index,name in enumerate(policy.BE_REVISION_SERVICES,30):
            new_expected['services'][name]['image']=new_image
            after['containers'][name].update(id=f'{index:064x}',image=new_image,created=END,state='created',startedAt=ZERO)
        runtime._expected=mock.Mock(return_value=new_expected)
        runtime.observe.side_effect=[copy.deepcopy(self.observed),copy.deepcopy(self.observed),after]
        inventory={'containers':[row['id'] for row in self.observed['containers'].values()],
                   'volumes':list(self.observed['volumes']),'networks':list(self.observed['networks']),'frozen':[]}
        new_inventory={**inventory,'containers':[row['id'] for row in after['containers'].values()]}
        runtime.inventory=mock.Mock(side_effect=[inventory,new_inventory])
        runtime._json=mock.Mock(return_value=[{'Id':new_image,'Config':{'Labels':{},'Env':[]}}])
        context={'labels':{},'sourceDigest':'a'*64}
        def effect(args,**kwargs):
            self.calls.append((args,kwargs))
            if args[:2]==['image','inspect']:return subprocess.CompletedProcess(args,1,stdout='',stderr='')
            return subprocess.CompletedProcess(args,0,stdout='{}',stderr='')
        runtime._raw.side_effect=effect
        with mock.patch('isolated_images.materialize_context',return_value=context),\
             mock.patch('isolated_images.validate_image_config'),\
             mock.patch('isolated_provenance.validate_effective_compose'),\
             mock.patch.object(subprocess,'check_output',return_value=b'be/Dockerfile.local\0'),\
             mock.patch.object(trial,'now',return_value=END):
            result=runtime.revise_be('observation-01',['be/src/test/java/SyntheticTest.java'])
        self.assertFalse(result['started'])
        mutation=[args for args,_ in self.calls if 'up' in args]
        self.assertEqual(len(mutation),1)
        self.assertEqual(mutation[0][-10:],['up','--no-start','--no-deps','--force-recreate','--no-build','--pull','never',*policy.BE_REVISION_SERVICES])
        self.assertFalse(any(args[0] in ('start','run','stop','rm','restart') for args,_ in self.calls))
        revision=json.loads((self.root/'revisions/001-observation-01/revision.json').read_text())
        self.assertEqual(revision['provenance']['previous'],self.receipt)
        self.assertEqual(revision['oldContainerIds']['be'],self.observed['containers']['be']['id'])
        self.assertEqual(revision['newContainerIds']['be'],after['containers']['be']['id'])


if __name__ == '__main__':
    unittest.main()
