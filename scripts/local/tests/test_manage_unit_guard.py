"""Exercise the real unit-test orchestration without Docker, settings or DB access."""
import copy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import manage
from scope_guard import ScopeError


class UnitDispatcherGuardTests(unittest.TestCase):
    def setUp(self):
        self.row = {'id': 'original-container-id', 'project': manage.PROJECT,
                    'service': 'index-dispatcher',
                    'name': manage.PROJECT + '-index-dispatcher-1', 'state': 'running'}
        self.ai = {'id': 'keyless-ai-id', 'project': manage.PROJECT, 'service': 'ai',
                   'name': manage.PROJECT + '-ai-1', 'state': 'running',
                   'mounts': [], 'networks': [manage.PROJECT + '_default']}
        self.dependencies = {'mysql': 'exited', 'redis': 'exited'}
        self.actions = []
        self.failure = None
        self.exception = None
        self.replace_before_restore = False
        self.gate_failure = False
        self.gates = 0
        for name, value in (
            ('clean_env', lambda: {}), ('compose_base', lambda: ['verified-compose']),
            ('compose', self.compose), ('run', self.run_command),
            ('settings', unittest.mock.Mock(side_effect=AssertionError('settings must not be read'))),
        ):
            patcher = patch.object(manage, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        for name, value in (('gate', self.gate), ('read_metadata', self.metadata)):
            patcher = patch.object(manage.scope_guard, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def gate(self, *args):
        self.gates += 1
        if self.gate_failure:
            raise ScopeError('synthetic scope refusal')

    def metadata(self, env):
        return [copy.deepcopy(self.ai)] + ([] if self.row is None else [copy.deepcopy(self.row)])

    def compose(self, name, *args):
        self.actions.append(('compose', name, args))
        if name == 'unit-dispatcher-stop':
            self.assertEqual(args, ('stop', 'index-dispatcher'))
            self.assertGreater(self.gates, 0)
            self.row['state'] = 'exited'
        else:
            self.assertIn(name, ('be-tests', 'ai-tests', 'pdf-tests'))
            self.assertFalse(self.row and self.row['state'] == 'running')
            # A regression to Compose start must fail: its dependency traversal
            # could start initially stopped MySQL/Redis along with the dispatcher.
            self.assertNotIn('start', args)
        if name == 'pdf-tests' and self.replace_before_restore:
            self.row['id'] = 'replacement-container-id'
        if name == self.exception:
            raise RuntimeError('synthetic suite exception')
        return SimpleNamespace(returncode=int(name == self.failure))

    def run_command(self, name, args):
        self.actions.append(('run', name, args))
        self.assertEqual(name, 'unit-dispatcher-restore')
        self.assertEqual(args, ['docker', 'start', 'original-container-id'])
        self.assertEqual(self.row['id'], 'original-container-id')
        self.assertGreaterEqual(self.gates, 2)
        if name != self.failure:
            self.row['state'] = 'running'
        self.assertEqual(self.dependencies, {'mysql': 'exited', 'redis': 'exited'})
        return SimpleNamespace(returncode=int(name == self.failure))

    def names(self):
        return [action[1] for action in self.actions]

    def test_running_dispatcher_restores_exact_id_without_dependency_start(self):
        self.assertEqual(manage.unit_tests(), 0)
        self.assertEqual(self.names(), ['unit-dispatcher-stop', 'be-tests', 'ai-tests',
                                       'pdf-tests', 'unit-dispatcher-restore'])
        self.assertEqual(self.row['state'], 'running')
        self.assertEqual(self.dependencies, {'mysql': 'exited', 'redis': 'exited'})

    def test_stopped_dispatcher_states_are_not_started(self):
        for state in ('exited', 'created'):
            with self.subTest(state=state):
                self.row['state'] = state
                self.actions.clear()
                self.assertEqual(manage.unit_tests(), 0)
                self.assertEqual(self.names(), ['be-tests', 'ai-tests', 'pdf-tests'])
                self.assertEqual(self.row['state'], state)

    def test_absent_dispatcher_is_not_created(self):
        self.row = None
        self.assertEqual(manage.unit_tests(), 0)
        self.assertEqual(self.names(), ['be-tests', 'ai-tests', 'pdf-tests'])
        self.assertIsNone(self.row)

    def test_nonzero_suite_result_is_preserved_after_restoration(self):
        self.failure = 'be-tests'
        self.assertEqual(manage.unit_tests(), 1)
        self.assertIn('pdf-tests', self.names())
        self.assertEqual(self.names()[-1], 'unit-dispatcher-restore')
        self.assertEqual(self.row['state'], 'running')

    def test_suite_exception_restores_before_propagating(self):
        self.exception = 'ai-tests'
        with self.assertRaisesRegex(RuntimeError, 'synthetic suite exception'):
            manage.unit_tests()
        self.assertEqual(self.names()[-1], 'unit-dispatcher-restore')
        self.assertNotIn('pdf-tests', self.names())
        self.assertEqual(self.row['state'], 'running')

    def test_failed_stop_skips_suites_and_restores_original_running_state(self):
        self.failure = 'unit-dispatcher-stop'
        self.assertEqual(manage.unit_tests(), 1)
        self.assertEqual(self.names(), ['unit-dispatcher-stop', 'unit-dispatcher-restore'])
        self.assertEqual(self.row['state'], 'running')

    def test_failed_restoration_is_an_explicit_blocker(self):
        self.failure = 'unit-dispatcher-restore'
        with self.assertRaisesRegex(ScopeError, 'restoration failed'):
            manage.unit_tests()
        self.assertEqual(self.row['state'], 'exited')

    def test_replacement_identity_is_never_started(self):
        self.replace_before_restore = True
        with self.assertRaisesRegex(ScopeError, 'identity/state changed'):
            manage.unit_tests()
        self.assertNotIn('unit-dispatcher-restore', self.names())
        self.assertEqual(self.row['state'], 'exited')

    def test_unsupported_initial_state_refuses_all_commands(self):
        for state in ('paused', 'restarting', 'dead'):
            with self.subTest(state=state):
                self.row['state'] = state
                with self.assertRaisesRegex(ScopeError, 'unsupported initial state'):
                    manage.unit_tests()
                self.assertEqual(self.actions, [])

    def test_foreign_primary_name_refuses_all_commands(self):
        self.row['name'] = 'other-project-index-dispatcher-1'
        with self.assertRaisesRegex(ScopeError, 'ambiguous'):
            manage.unit_tests()
        self.assertEqual(self.actions, [])

    def test_scope_refusal_precedes_any_stop_or_test(self):
        self.gate_failure = True
        with self.assertRaisesRegex(ScopeError, 'synthetic scope refusal'):
            manage.unit_tests()
        self.assertEqual(self.actions, [])

    def test_live_key_mount_refuses_before_dispatcher_stop_or_any_suite(self):
        self.ai['mounts'] = [{'type': 'bind'}]
        with self.assertRaisesRegex(ScopeError, 'Local regression refused'):
            manage.unit_tests()
        self.assertEqual(self.actions, [])
        self.assertEqual(self.row['state'], 'running')

    def test_live_egress_refuses_before_dispatcher_stop_or_any_suite(self):
        self.ai['networks'].append(manage.PROJECT + '_gateway')
        with self.assertRaisesRegex(ScopeError, 'Local regression refused'):
            manage.unit_tests()
        self.assertEqual(self.actions, [])
        self.assertEqual(self.row['state'], 'running')


if __name__ == '__main__':
    unittest.main()
