"""Pure launcher delegation checks; no real runtime, credentials or service calls.

Every module load substitutes the isolated runtime and historical scope module.
All process, network and directory-creation entry points fail unless a test
supplies a bounded in-memory result for the precise child argv under test.
"""
import contextlib
import os
from pathlib import Path
import socket
import subprocess
import sys
import types
import unittest
from unittest import mock
import urllib.request


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'scripts/local'


def forbidden(*args, **kwargs):
    raise AssertionError('Pure launcher test attempted a real side effect')


class IsolatedLauncherBindingTests(unittest.TestCase):
    def setUp(self):
        self.effects = contextlib.ExitStack()
        self.addCleanup(self.effects.close)
        self.runtime = mock.Mock()
        self.runtime.repo = ROOT
        self.runtime.root = ROOT / '.local/isolated/UNIT_SYNTHETIC_ONLY'
        self.runtime.results = self.runtime.root / 'results'
        self.runtime.attempt_id = None
        self.runtime.attempt_root = self.runtime.root
        self.runtime.fixtures = self.runtime.root / 'fixtures'
        self.runtime.project = 'UNIT_SYNTHETIC_PROJECT'
        self.runtime.credentials_path = self.runtime.root / 'credentials.env'
        self.runtime.run_id = '12345678-1234-4234-8234-123456789012'
        self.runtime.origins = {'main': 'http://127.0.0.1:25173', 'short': 'http://127.0.0.1:25174'}
        self.runtime.settings.return_value = {'LOCAL_TEACHER_PASSWORD': 'SYNTHETIC_NOT_A_SECRET'}
        self.runtime.clean_env.return_value = {'DODREAM_ISOLATED_MANIFEST': str(SCRIPTS / 'isolated-trial.json')}
        self.runtime.compose_args.return_value = ['UNIT_SYNTHETIC_PROXY', 'validated-operation']
        self.runtime.assert_ready_for_browser = mock.Mock()
        self.runtime._started.return_value = set()
        self.runtime.source_identity.return_value = {'digest': 'UNIT_SYNTHETIC_SOURCE'}
        self.runtime.fixture_binding.side_effect = lambda suite: {
            'trialId': 'UNIT_SYNTHETIC_TRIAL', 'project': self.runtime.project, 'suite': suite,
            'origin': self.runtime.origins['main'], 'runId': self.runtime.run_id,
            'syntheticOnly': True, 'provenanceDigest': 'UNIT_SYNTHETIC_DIGEST'}
        self.stub_trial = types.ModuleType('isolated_trial')
        self.stub_trial.load_active_runtime = mock.Mock(return_value=self.runtime)
        self.stub_scope = types.ModuleType('scope_guard')
        self.stub_scope.MAIN = ('FORBIDDEN_LEGACY_SERVICE',)
        for name in ('gate', 'port_available', 'read_metadata', 'require_keyless_local'):
            setattr(self.stub_scope, name, mock.Mock(side_effect=forbidden))
        self.effects.enter_context(mock.patch.dict(sys.modules, {
            'isolated_trial': self.stub_trial, 'scope_guard': self.stub_scope}))
        self.effects.enter_context(mock.patch.dict(os.environ, {
            'DODREAM_ISOLATED_MANIFEST': str(SCRIPTS / 'isolated-trial.json'),
            'DODREAM_RESULTS_DIR': '/FORBIDDEN_LEGACY_RESULTS',
        }, clear=True))
        for module, name in ((subprocess, 'run'), (subprocess, 'Popen'),
                             (subprocess, 'check_call'), (subprocess, 'check_output'),
                             (os, 'system'), (os, 'popen'), (socket, 'socket'),
                             (socket, 'create_connection'), (urllib.request, 'urlopen'),
                             (urllib.request.OpenerDirector, 'open'), (Path, 'mkdir')):
            self.effects.enter_context(mock.patch.object(module, name, side_effect=forbidden))
        original_read = Path.read_text
        def source_only_read(path, *args, **kwargs):
            if path.parent != SCRIPTS or path.suffix != '.py':
                raise AssertionError('Only reviewed launcher source can be read in this test')
            return original_read(path, *args, **kwargs)
        self.effects.enter_context(mock.patch.object(Path, 'read_text', source_only_read))
        self.manage = self.load('manage')

    def load(self, name):
        filename = SCRIPTS / (name + '.py')
        module = types.ModuleType(name)
        module.__file__ = str(filename)
        self.effects.enter_context(mock.patch.dict(sys.modules, {name: module}))
        exec(compile(filename.read_text(), str(filename), 'exec'), module.__dict__)
        return module

    def load_checks(self):
        helper = self.load('isolated_checks')
        self.effects.enter_context(mock.patch.object(helper, 'initial_ownership', return_value={
            'runId': self.runtime.run_id, 'project': self.runtime.project,
            'provenanceDigest': 'UNIT_SYNTHETIC_DIGEST'}))
        return helper

    def test_import_uses_only_explicit_runtime_without_creating_legacy_results(self):
        self.stub_trial.load_active_runtime.assert_called_once_with()
        self.assertIs(self.manage.ISOLATED, self.runtime)
        self.assertEqual(self.manage.RESULTS, self.runtime.results)
        self.assertEqual(self.manage.ENV_FILE, self.runtime.credentials_path)
        self.assertEqual(self.manage.PROJECT, self.runtime.project)

    def test_invalid_explicit_runtime_does_not_fall_back(self):
        self.stub_trial.load_active_runtime.side_effect = ValueError('SYNTHETIC_BAD_RECEIPT')
        with self.assertRaisesRegex(ValueError, 'SYNTHETIC_BAD_RECEIPT'):
            self.load('manage')

    def test_empty_explicit_manifest_is_still_validated(self):
        os.environ['DODREAM_ISOLATED_MANIFEST'] = ''
        self.stub_trial.load_active_runtime.side_effect = ValueError('SYNTHETIC_MISSING_CONFIG')
        with self.assertRaisesRegex(ValueError, 'SYNTHETIC_MISSING_CONFIG'):
            self.load('manage')

    def test_settings_environment_and_redaction_delegate(self):
        for name, args in [('settings', ()), ('clean_env', ()), ('redact', ('SYNTHETIC_TEXT',))]:
            delegated = getattr(self.runtime, name)
            self.assertIs(getattr(self.manage, name)(*args), delegated.return_value)
            delegated.assert_called_once_with(*args)

    def test_operations_record_and_fault_cleanup_delegate(self):
        result = subprocess.CompletedProcess(['SYNTHETIC_COMMAND'], 0, stdout='SYNTHETIC_OUTPUT')
        cases = [('compose_args', ('exec', '-T', 'mysql', 'SYNTHETIC_COMMAND')),
                 ('compose', ('synthetic-stop', 'stop', 'worker')),
                 ('run', ('synthetic-child', ['SYNTHETIC_COMMAND'])),
                 ('record', ('synthetic-record', ['SYNTHETIC_COMMAND'], result, 'SYNTHETIC_TIME')),
                 ('crash_owned', ('worker',)), ('pause_chroma', (True,)),
                 ('stop_owned_test', ('SYNTHETIC_OWNED_NAME',))]
        for name, args in cases:
            with self.subTest(name=name):
                delegated = getattr(self.runtime, name)
                self.assertIs(getattr(self.manage, name)(*args), delegated.return_value)
                delegated.assert_called_once_with(*args)

    def test_unsupported_whole_environment_paths_stop_before_legacy_gate(self):
        for name, args in [('compose_base', ()), ('unit_tests', ()), ('init', ()),
                           ('check', ()), ('snapshot', ('before',)), ('main', ())]:
            with self.subTest(name=name), self.assertRaises((RuntimeError, SystemExit)):
                getattr(self.manage, name)(*args)

    def test_verify_origins_do_not_require_old_port_settings(self):
        verify = self.load('verify')
        self.assertEqual(verify.BASE, {'be': self.runtime.origins['main'],
            'ai': self.runtime.origins['main'] + '/ai', 'web': self.runtime.origins['main']})
        self.assertIs(verify.ENV, self.runtime.settings.return_value)
        with self.assertRaisesRegex(ValueError, 'explicitly configured'):
            verify.req('pdf', '/health')
        with self.assertRaisesRegex(RuntimeError, 'not an isolated trial'):
            verify.persistence()
        with self.assertRaisesRegex(RuntimeError, 'not an isolated trial'):
            verify.persistence_containers()

    def test_sql_exec_uses_only_central_proxy_argv(self):
        verify = self.load('verify')
        def fake_child(argv, **kwargs):
            self.assertEqual(argv, ['UNIT_SYNTHETIC_PROXY', 'validated-operation'])
            self.assertEqual(kwargs['env'], self.runtime.clean_env.return_value)
            self.assertEqual(kwargs['input'], 'SELECT SYNTHETIC_ONLY;')
            return subprocess.CompletedProcess(argv, 0, stdout='SYNTHETIC_RESULT\n')
        with mock.patch.object(subprocess, 'run', side_effect=fake_child):
            self.assertEqual(verify.sql('SELECT SYNTHETIC_ONLY;'), 'SYNTHETIC_RESULT')
        argv = self.runtime.compose_args.call_args.args
        self.assertEqual(argv[:4], ('exec', '-T', 'mysql', 'sh'))
        self.assertNotIn('dodream-phase1', ' '.join(argv))

    def test_student_prepare_requires_callback_before_any_request(self):
        self.load('verify')
        preparation = self.load('student_demo_prepare')
        with mock.patch.object(preparation, 'req', side_effect=forbidden):
            with self.assertRaisesRegex(RuntimeError, 'pending-job callback'):
                preparation.prepare()

    def test_student_prepare_hands_new_jobs_to_callback_before_readiness_wait(self):
        self.load('verify')
        preparation = self.load('student_demo_prepare')
        metadata = {'fixtureVersion': preparation.VERSION, 'samples': [
            {'key': 'SYNTHETIC_SAMPLE', 'fileId': 101, 'materialId': 201}],
            'counts': {'files': 2, 'materials': 2, 'quizzes': 4, 'logicalJobs': 4}}
        calls = []
        def fake_req(service, path, *args, **kwargs):
            calls.append((service, path))
            if path == '/api/auth/demo/config':
                data = {'enabled': True, 'fixtureVersion': preparation.VERSION}
            elif path == '/api/auth/teacher/login':
                data = {'accessToken': 'SYNTHETIC_NOT_A_TOKEN'}
            elif path == '/api/demo/preparation':
                data = metadata
            elif path == '/api/demo/prepare':
                data = {}
            else:
                self.fail('Unexpected synthetic request')
            return 200, data, {}, b''
        def after_enqueue(actual):
            self.assertIs(actual, metadata)
            self.assertEqual(calls.count(('be', '/api/demo/prepare')), 2)
            self.assertEqual(calls.count(('be', '/api/demo/preparation')), 2)
            self.assertEqual(calls.count(('be', '/api/auth/demo/config')), 1)
            raise ValueError('SYNTHETIC_STOP_BEFORE_CONSUMERS')
        with mock.patch.object(preparation, 'req', side_effect=fake_req):
            with self.assertRaisesRegex(ValueError, 'SYNTHETIC_STOP_BEFORE_CONSUMERS'):
                preparation.prepare(after_enqueue=after_enqueue)

    def test_browser_launchers_refuse_bad_provenance_before_effects(self):
        self.runtime.assert_ready_for_browser.side_effect = ValueError('SYNTHETIC_BAD_PROVENANCE')
        indexing = self.load('indexing_browser_checks')
        with self.assertRaisesRegex(ValueError, 'SYNTHETIC_BAD_PROVENANCE'):
            indexing.browser(mock.Mock())
        student = self.load('verify_student_web')
        with self.assertRaisesRegex(ValueError, 'SYNTHETIC_BAD_PROVENANCE'):
            student.main()
        self.assertEqual(self.runtime.assert_ready_for_browser.call_args_list,
                         [mock.call('indexing'), mock.call('student')])

    def pending_fixture(self):
        import json
        helper = self.load_checks()
        owner = {'runId': self.runtime.run_id, 'project': self.runtime.project,
                 'provenanceDigest': 'UNIT_SYNTHETIC_DIGEST', 'teachers': [{'id': 42, 'email': 'authz-owner@local.dodream.invalid'}]}
        job = {'jobId': '23456789-2345-4345-8345-234567890123', 'state': 'QUEUED',
               'resourceKind': 'MATERIAL', 'resourceId': 201, 'ownerId': 42, 'actualOwner': 42,
               'title': '[INDEXING LOCAL] SYNTHETIC_ONLY', 'fileName': 'indexing-synthetic-only.pdf', 'snapshotValid': 1}
        self.effects.enter_context(mock.patch.object(Path, 'is_file', return_value=True))
        self.effects.enter_context(mock.patch.object(Path, 'is_symlink', return_value=False))
        self.effects.enter_context(mock.patch.object(Path, 'read_text', return_value=json.dumps(owner)))
        self.effects.enter_context(mock.patch.object(helper, 'stamped'))
        return helper, owner, job

    def test_pending_job_and_queue_ids_are_bound_to_new_owner(self):
        import json
        helper, _, job = self.pending_fixture()
        self.runtime.sql.return_value = json.dumps(job)
        self.runtime._operation.return_value = subprocess.CompletedProcess([], 0,
            stdout=json.dumps({'jobs': [job['jobId']], 'invalid': [], 'keyCount': 1}))
        report = helper.verify_pending_work(self.runtime)
        self.assertEqual(report['pendingJobs'][0]['ownerId'], 42)
        statement = self.runtime.sql.call_args.args[0]
        self.assertIn('m.teacher_id', statement)
        self.assertIn('f.uploader_id', statement)
        self.assertIn("resource_kind='PDF'", statement)
        self.assertNotIn('uploaded_by', statement)
        self.assertNotIn('users.email', statement)

    def test_pending_jobs_reject_wrong_owners_kinds_and_snapshots(self):
        import json
        helper, _, job = self.pending_fixture()
        for delta in ({'ownerId': 999}, {'actualOwner': 999}, {'resourceKind': 'FILE'},
                      {'snapshotValid': 0}, {'title': 'UNREVIEWED_FIXTURE'}):
            with self.subTest(delta=delta):
                self.runtime.sql.return_value = json.dumps({**job, **delta})
                self.runtime._operation.reset_mock()
                with self.assertRaises(RuntimeError):
                    helper.verify_pending_work(self.runtime)
                self.runtime._operation.assert_not_called()

    def test_broker_rejects_tasks_outside_the_new_fixture_ledger(self):
        import json
        helper, _, job = self.pending_fixture()
        self.runtime.sql.return_value = json.dumps(job)
        for queue in ({'jobs': ['34567890-3456-4456-8456-345678901234'], 'invalid': []},
                      {'jobs': [], 'invalid': ['unknown-task']}):
            with self.subTest(queue=queue):
                self.runtime._operation.return_value = subprocess.CompletedProcess([], 0, stdout=json.dumps(queue))
                with self.assertRaisesRegex(RuntimeError, 'outside this trial'):
                    helper.verify_pending_work(self.runtime)

    def test_pending_owner_receipt_mismatch_prevents_db_and_queue_queries(self):
        import json
        helper, owner, _ = self.pending_fixture()
        with mock.patch.object(Path, 'read_text', return_value=json.dumps({**owner, 'runId': 'OLD_RUN'})):
            with self.assertRaisesRegex(RuntimeError, 'does not match'):
                helper.verify_pending_work(self.runtime)
        self.runtime.sql.assert_not_called()
        self.runtime._operation.assert_not_called()

    def test_auth_gate_orders_empty_checks_migrations_seed_and_browser_without_consumers(self):
        import json
        helper = self.load_checks()
        self.runtime.sql.side_effect = ['0', '', 'SYNTHETIC_MIGRATION_RESULT', 'SYNTHETIC_MIGRATION_RESULT', '2', '0']
        self.runtime._operation.side_effect = [
            subprocess.CompletedProcess([], 0, stdout='0'),
            subprocess.CompletedProcess([], 0, stdout='0'),
            subprocess.CompletedProcess([], 0, stdout=json.dumps({'chat_sessions': 0, 'chat_messages': 0, 'embedding_tasks': 0})),
        ]
        self.runtime.preparation = {'before': {'frozen': 'SYNTHETIC_FROZEN_METADATA'}}
        self.runtime.inventory.return_value = {'frozen': 'SYNTHETIC_FROZEN_METADATA'}
        with mock.patch.object(Path, 'exists', return_value=False), \
                mock.patch.object(Path, 'read_text', return_value='SELECT SYNTHETIC_MIGRATION;'), \
                mock.patch.object(helper, 'register_pending_fixtures'), \
                mock.patch.object(helper, 'fixture'), mock.patch.object(helper, 'write_new') as written, \
                mock.patch.object(helper, 'request', side_effect=[
                    (200, {'headerName': 'SYNTHETIC_CSRF', 'token': 'SYNTHETIC_VALUE'}),
                    (200, {'accessToken': 'SYNTHETIC_NOT_A_TOKEN'}), (200, {})]), \
                mock.patch.object(helper, 'run_browser', return_value={'counts': {'PASS': 17}}):
            result = helper.run_auth(self.runtime)
        self.assertEqual(result['status'], 'PASS')
        self.assertFalse(result['consumersStarted'])
        self.assertEqual(self.runtime.compose.call_args_list, [
            mock.call('new-data-start', 'start', 'mysql', 'redis'),
            mock.call('new-primary-seed', 'start', 'be'),
            mock.call('new-auth-dependencies', 'start', 'ai', 'be-auth-short'),
            mock.call('new-auth-web', 'start', 'web-auth-test'),
        ])
        self.assertEqual(self.runtime.set_stage.call_args_list, [mock.call('auth', 'data'), mock.call('auth', 'browser')])
        written_names = [call.args[0].name for call in written.call_args_list]
        self.assertEqual(written_names[:4], ['auth-empty-stores.json', 'auth-migrations.json', 'isolated-auth-gate.json', 'auth-pass.json'])
        self.assertTrue(written_names[4].endswith('-auth-completed.json'))

    def test_nonempty_new_db_blocks_auth_before_migration_or_app_start(self):
        helper = self.load_checks()
        self.runtime.sql.return_value = '1'
        with mock.patch.object(Path, 'exists', return_value=False):
            with self.assertRaisesRegex(RuntimeError, 'not empty'):
                helper.run_auth(self.runtime)
        self.runtime.compose.assert_called_once_with('new-data-start', 'start', 'mysql', 'redis')
        self.runtime.sql.assert_called_once()
        self.runtime._operation.assert_not_called()

    def test_auth_preparation_resumes_only_its_receipted_partial_migration(self):
        import json
        helper = self.load_checks()
        binding = self.runtime.fixture_binding('auth')
        empty = {key: binding[key] for key in ('runId', 'project', 'provenanceDigest')}
        empty.update(status='PASS', applicationTables=0, redisDatabase0=0, redisDatabase1=0)
        self.runtime._started.return_value = {'mysql', 'redis'}
        self.runtime.sql.side_effect = ['grading_attempts', 'MIGRATION_ONE', 'MIGRATION_TWO', '2', '0']
        self.runtime._operation.return_value = subprocess.CompletedProcess([], 0,
            stdout=json.dumps({'chat_sessions': 0, 'chat_messages': 0, 'embedding_tasks': 0}))
        self.runtime.preparation = {'before': {'frozen': 'SYNTHETIC_FROZEN'}}
        self.runtime.inventory.return_value = {'frozen': 'SYNTHETIC_FROZEN'}
        def read(path, *args, **kwargs):
            if path.name == 'auth-empty-stores.json': return json.dumps(empty)
            if path.suffix == '.sql': return 'SELECT SYNTHETIC_MIGRATION;'
            self.fail('Unexpected read in resumed synthetic preparation')
        with mock.patch.object(Path, 'exists', lambda path: path.name == 'auth-empty-stores.json'), \
                mock.patch.object(Path, 'read_text', read), \
                mock.patch.object(helper, 'register_pending_fixtures'), \
                mock.patch.object(helper, 'fixture'), mock.patch.object(helper, 'write_new') as written, \
                mock.patch.object(helper, 'request', side_effect=[
                    (200, {'headerName': 'SYNTHETIC_CSRF', 'token': 'SYNTHETIC_VALUE'}),
                    (200, {'accessToken': 'SYNTHETIC_NOT_A_TOKEN'}), (200, {})]), \
                mock.patch.object(helper, 'run_browser', return_value={'counts': {'PASS': 17}}):
            self.assertEqual(helper.run_auth(self.runtime)['status'], 'PASS')
        self.assertNotIn('auth-empty-stores.json', [call.args[0].name for call in written.call_args_list])
        self.assertEqual(self.runtime._operation.call_args.args[:2], ('exec', ['ai']))
        self.assertEqual(self.runtime._operation.call_count, 1)

    def test_partial_migration_resume_rejects_unexpected_tables(self):
        import json
        helper = self.load_checks()
        binding = self.runtime.fixture_binding('auth')
        empty = {key: binding[key] for key in ('runId', 'project', 'provenanceDigest')}
        empty.update(status='PASS', applicationTables=0, redisDatabase0=0, redisDatabase1=0)
        self.runtime.sql.return_value = 'UNREVIEWED_TABLE'
        with mock.patch.object(Path, 'exists', lambda path: path.name == 'auth-empty-stores.json'), \
                mock.patch.object(Path, 'read_text', lambda path: json.dumps(empty) if path.name == 'auth-empty-stores.json' else 'SELECT SYNTHETIC_MIGRATION;'):
            with self.assertRaisesRegex(RuntimeError, 'Unexpected tables'):
                helper.run_auth(self.runtime)
        self.runtime.compose.assert_called_once_with('new-data-start', 'start', 'mysql', 'redis')
        self.runtime.sql.assert_called_once()

    def test_followup_auth_reuses_only_initial_setup_proofs_and_reruns_browser(self):
        import hashlib
        import json
        helper = self.load_checks()
        self.runtime.attempt_id = 'fixed-01'
        self.runtime.attempt_root = self.runtime.root / 'attempts/fixed-01'
        self.runtime.results = self.runtime.attempt_root / 'results'
        self.runtime.fixtures = self.runtime.attempt_root / 'fixtures'
        self.runtime._started.return_value = {'mysql', 'redis', 'be', 'worker', 'index-dispatcher'}
        self.runtime.sql.return_value = '2'
        self.runtime.preparation = {'before': {'frozen': 'SYNTHETIC_FROZEN'}}
        self.runtime.inventory.return_value = {'frozen': 'SYNTHETIC_FROZEN'}
        ownership = helper.initial_ownership(self.runtime)
        migration = 'SELECT SYNTHETIC_MIGRATION;'
        proofs = {
            'auth-empty-stores.json': {**ownership, 'status': 'PASS', 'applicationTables': 0,
                'redisDatabase0': 0, 'redisDatabase1': 0},
            'auth-migrations.json': {**ownership, 'status': 'PASS', 'sha256': {
                name: hashlib.sha256(migration.encode()).hexdigest()
                for name in ('V003__grading_attempts.sql', 'V004__indexing_ledger.sql')}},
        }
        def read(path, *args, **kwargs):
            if path.suffix == '.sql': return migration
            self.assertEqual(path.parent, self.runtime.root / 'results')
            return json.dumps(proofs[path.name])
        with mock.patch.object(Path, 'exists', lambda path: path.name in proofs), \
                mock.patch.object(Path, 'is_file', return_value=True), \
                mock.patch.object(Path, 'read_text', read), \
                mock.patch.object(helper, 'register_pending_fixtures'), \
                mock.patch.object(helper, 'fixture'), mock.patch.object(helper, 'write_new') as written, \
                mock.patch.object(helper, 'request', side_effect=[
                    (200, {'headerName': 'SYNTHETIC_CSRF', 'token': 'SYNTHETIC_VALUE'}),
                    (200, {'accessToken': 'SYNTHETIC_NOT_A_TOKEN'}), (200, {})]), \
                mock.patch.object(helper, 'run_browser', return_value={'counts': {'PASS': 17}}) as browser:
            result = helper.run_auth(self.runtime)
        browser.assert_called_once_with(self.runtime, 'auth')
        self.assertEqual(result['newEmptyDatabaseAndRedis'], 'INITIAL_PROOF_REUSED')
        self.assertEqual(result['migrationsBeforeSpring'], 'INITIAL_PROOF_REUSED')
        self.runtime._operation.assert_not_called()  # no empty-Redis or SQLite recheck
        self.runtime.sql.assert_called_once()  # only preserved teacher seed assertion
        self.assertTrue(all(self.runtime.attempt_root in call.args[0].parents for call in written.call_args_list))
        self.assertEqual(self.runtime.compose.call_args_list[0],
                         mock.call('auth-consumers-stop', 'stop', 'index-dispatcher', 'worker'))

    def test_followup_seed_reuses_exact_nine_ids_without_cloning(self):
        import json
        helper = self.load_checks()
        self.runtime.attempt_id = 'fixed-01'
        self.runtime.results = self.runtime.root / 'attempts/fixed-01/results'
        self.runtime.manifest_path = SCRIPTS / 'isolated-trial.json'
        self.manage.RESULTS = self.runtime.results
        fixture = {'authorization': dict(zip(('editable', 'second-shared', 'class-shared', 'private',
            'draft', 'other-owned', 'remote-owned'), range(101, 108))), 'grading': {'primary': 108, 'second': 109}}
        rows = [{'id': identifier, 'title': '[AUTHZ 5] ' + suffix}
                for suffix, identifier in fixture['authorization'].items()]
        rows += [{'id': 108, 'title': '[GRADING LOCAL] phase5'},
                 {'id': 109, 'title': '[GRADING LOCAL] phase5 second'}]
        self.runtime.sql.return_value = '\n'.join(json.dumps(row) for row in rows)
        with mock.patch.object(Path, 'exists', return_value=False), \
                mock.patch.object(Path, 'is_file', return_value=True), \
                mock.patch.object(Path, 'is_symlink', return_value=False), \
                mock.patch.object(Path, 'read_text', return_value=json.dumps(fixture)), \
                mock.patch.object(helper, 'write_new') as written, mock.patch.object(helper, 'stamped') as stamped:
            self.assertEqual(helper.fresh_phase5_fixtures(self.runtime), fixture)
        self.runtime.sql.assert_called_once()
        self.assertTrue(self.runtime.sql.call_args.args[0].startswith('SELECT '))
        self.assertEqual(len(written.call_args_list), 2)
        self.assertEqual(stamped.call_args.args[2]['addedRows'], 0)

    def test_followup_seed_rejects_duplicate_or_mismatched_ids_before_writing(self):
        import json
        helper = self.load_checks()
        self.runtime.attempt_id = 'fixed-01'
        self.runtime.results = self.runtime.root / 'attempts/fixed-01/results'
        self.runtime.manifest_path = SCRIPTS / 'isolated-trial.json'
        self.manage.RESULTS = self.runtime.results
        fixture = {'authorization': dict(zip(('editable', 'second-shared', 'class-shared', 'private',
            'draft', 'other-owned', 'remote-owned'), range(101, 108))), 'grading': {'primary': 108, 'second': 109}}
        self.runtime.sql.return_value = ''
        with mock.patch.object(Path, 'exists', return_value=False), \
                mock.patch.object(Path, 'is_file', return_value=True), \
                mock.patch.object(Path, 'is_symlink', return_value=False), \
                mock.patch.object(Path, 'read_text', return_value=json.dumps(fixture)), \
                mock.patch.object(helper, 'write_new') as written:
            with self.assertRaisesRegex(RuntimeError, 'do not match preserved'):
                helper.fresh_phase5_fixtures(self.runtime)
        written.assert_not_called()

    def test_initial_ownership_uses_immutable_creation_not_current_revision_digest(self):
        import hashlib
        import json
        helper = self.load('isolated_checks')
        receipt = {'runId': self.runtime.run_id, 'project': self.runtime.project,
                   'schema': 1, 'source': 'SYNTHETIC_ORIGINAL'}
        with mock.patch.object(Path, 'read_text', return_value=json.dumps({'provenance': receipt})):
            ownership = helper.initial_ownership(self.runtime)
        expected = hashlib.sha256(json.dumps(receipt, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        self.assertEqual(ownership['provenanceDigest'], expected)
        self.runtime.fixture_binding.assert_not_called()
        with mock.patch.object(Path, 'read_text', return_value=json.dumps({'provenance': {**receipt, 'runId': 'OTHER'}})):
            with self.assertRaisesRegex(RuntimeError, 'another trial'):
                helper.initial_ownership(self.runtime)

    def test_followup_missing_initial_empty_proof_does_not_rebaseline_store(self):
        helper = self.load_checks()
        self.runtime.attempt_id = 'fixed-01'
        self.runtime.attempt_root = self.runtime.root / 'attempts/fixed-01'
        self.runtime.results = self.runtime.attempt_root / 'results'
        with mock.patch.object(Path, 'exists', return_value=False), \
                mock.patch.object(Path, 'is_file', return_value=False), \
                mock.patch.object(helper, 'write_new') as written:
            with self.assertRaisesRegex(RuntimeError, 'original empty-store proof'):
                helper.run_auth(self.runtime)
        self.runtime.sql.assert_not_called()
        self.runtime._operation.assert_not_called()
        written.assert_not_called()

    def test_followup_chroma_preserves_original_empty_proof_without_new_empty_claim(self):
        import json
        helper = self.load_checks()
        self.runtime.attempt_id = 'fixed-01'
        self.runtime.results = self.runtime.root / 'attempts/fixed-01/results'
        proof = {'status': 'PASS', 'runId': self.runtime.run_id, 'collections': 0}
        def read(path, *args, **kwargs):
            self.assertEqual(path, self.runtime.root / 'results/new-chroma-empty.json')
            return json.dumps(proof)
        with mock.patch.object(Path, 'exists', return_value=True), \
                mock.patch.object(Path, 'read_text', read), \
                mock.patch.object(helper, 'write_new') as written:
            helper.start_main(self.runtime, 'indexing')
        self.runtime._operation.assert_not_called()
        written.assert_not_called()
        self.assertIn(mock.call('new-chroma', 'start', 'chroma'), self.runtime.compose.call_args_list)

    def test_remaining_suites_stop_on_first_failure(self):
        helper = self.load_checks()
        with mock.patch.object(helper, 'stamped'), \
                mock.patch.object(helper, 'run_suite', side_effect=RuntimeError('SYNTHETIC_SUITE_FAILURE')) as suite:
            with self.assertRaisesRegex(RuntimeError, 'SYNTHETIC_SUITE_FAILURE'):
                helper.run_remaining(self.runtime)
        suite.assert_called_once_with(self.runtime, 'authorization')


if __name__ == '__main__':
    unittest.main(verbosity=2)
