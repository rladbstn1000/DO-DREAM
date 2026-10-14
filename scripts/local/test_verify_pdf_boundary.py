"""Pure evidence/expectation checks. Network and subprocess calls are forbidden."""
import contextlib
import copy
import json
import socket
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import verify_pdf_boundary as check


class PdfBoundaryEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack(); self.addCleanup(self.stack.close)
        def forbidden(*args, **kwargs): raise AssertionError('Pure PDF evidence test attempted external effects')
        for obj, name in ((socket, 'socket'), (socket, 'create_connection'), (subprocess, 'run'),
                          (subprocess, 'check_output'), (subprocess, 'Popen')):
            self.stack.enter_context(mock.patch.object(obj, name, side_effect=forbidden))
        root = Path(self.stack.enter_context(tempfile.TemporaryDirectory())).resolve()
        self.runtime = SimpleNamespace(results=root, run_id='00000000-0000-4000-8000-000000000001',
            _receipt=mock.Mock(return_value={'synthetic': True}), source_identity=mock.Mock(return_value={'sourceHash': 'f'*64}))
        self.before = {'counts': {'files': 6, 'jobs': 0, 'resources': 0, 'executions': 0}, 'files': [], 'objects': []}
        self.after = {'counts': {'files': 7, 'jobs': 1, 'resources': 1, 'executions': 0},
            'files': [{'id': 7, 'ownerId': 1, 'bytes': len(check.BODY), 'hasParsedObject': True}],
            'objects': [{'fileId': 7, 'exists': True, 'bytes': len(check.BODY), 'sha256': check.BODY_HASH}]}
        self.observed = [self.event(stage) for stage in ('REQUEST_BEGIN', 'STORAGE_BOUNDARY', 'REQUEST_END')]
        self.stack.enter_context(mock.patch.object(check, 'login', return_value=('SYNTHETIC-TOKEN-NOT-REAL', 1)))
        self.snap = self.stack.enter_context(mock.patch.object(check, 'snapshot', side_effect=[self.before, self.after]))
        self.events = self.stack.enter_context(mock.patch.object(check, 'events', side_effect=[[], self.observed]))
        self.http = self.stack.enter_context(mock.patch.object(check, '_http', return_value=(200,
            {'pdfId': 7, 'indexing': {'jobId': '00000000-0000-4000-8000-000000000007'}}, {})))

    def event(self, stage):
        return {'correlationId': '00000000-0000-4000-8000-000000000099', 'stage': stage,
                'at': '2026-10-14T12:00:00Z', **{field: False for field in check.BOOLEAN_FIELDS}}

    def test_reproduction_preserves_one_failure_and_fixed_input_contract(self):
        self.snap.side_effect = [self.before, self.before]
        self.observed[1]['physicalConnectionHeld'] = True
        self.http.return_value = 503, {'code': 'INDEXING_TRANSACTION_BOUNDARY', 'message': 'MUST-NOT-PERSIST'}, {}
        evidence = check.reproduction(self.runtime, 503)
        self.assertEqual(evidence['status'], 'PASS')
        self.assertEqual(self.http.call_count, 1)
        self.assertEqual(self.http.call_args.kwargs['body'], check.BODY)
        self.assertTrue(self.http.call_args.args[1].endswith('indexing-synthetic-c20cf22c-8758-4609-90f5-2466714127aa.pdf'))
        text = (self.runtime.results/'pdf-boundary-reproduction-503.json').read_text()
        self.assertNotIn('SYNTHETIC-TOKEN-NOT-REAL', text)
        self.assertNotIn('MUST-NOT-PERSIST', text)
        self.assertNotIn(check.BODY.decode(), text)
        with self.assertRaises(ValueError): check.reproduction(self.runtime, 503)
        self.assertEqual(self.http.call_count, 1)

    def test_fixed_success_requires_no_held_connection_and_original_object(self):
        result = check.reproduction(self.runtime, 200)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['response']['fileId'], 7)

    def test_success_with_boundary_connection_is_fail_and_preserves_evidence(self):
        self.observed[1]['detachedPhysicalConnectionHeld'] = True
        with self.assertRaises(ValueError): check.reproduction(self.runtime, 200)
        row = json.loads((self.runtime.results/'pdf-boundary-reproduction-200.json').read_text())
        self.assertEqual(row['status'], 'FAIL')
        self.assertIn('external_boundary_holds_transaction_or_connection', row['failedChecks'])

    def test_duplicate_case_refuses_new_request(self):
        self.before['files'] = [{'id': 7}]
        with self.assertRaises(ValueError): check.reproduction(self.runtime, 200)
        self.http.assert_not_called()

    def test_wrong_http_status_is_not_hidden_as_expected_failure(self):
        self.snap.side_effect = [self.before, self.before]
        self.http.return_value = 500, {'code': 'OTHER_FAILURE'}, {}
        with self.assertRaises(ValueError): check.reproduction(self.runtime, 503)
        row = json.loads((self.runtime.results/'pdf-boundary-reproduction-503.json').read_text())
        self.assertIn('expected_http_status', row['failedChecks'])
        self.assertIn('original_boundary_failure', row['failedChecks'])

    def test_failure_mode_never_runs_extra_fixtures_or_consumers(self):
        with mock.patch.object(check, 'reproduction', return_value={'status':'PASS'}) as reproduction, \
             mock.patch.object(check, 'verify_denials') as denials, \
             mock.patch.object(check, 'verify_provider_failure') as provider, \
             mock.patch.object(check, 'verify_activation') as activation:
            check.run(self.runtime, 503)
        reproduction.assert_called_once_with(self.runtime, 503)
        denials.assert_not_called(); provider.assert_not_called(); activation.assert_not_called()

    def test_denial_cases_keep_hidden_file_404_and_size_over_10mb(self):
        self.snap.side_effect = [self.after, self.after]
        self.http.side_effect = [(status, None, {}) for status in (401,403,404,400,400,413)]
        row = check.verify_denials(self.runtime, {'status':'PASS','response':{'http':200,'fileId':7}})
        self.assertEqual(row['status'], 'PASS')
        self.assertEqual([case['expected'] for case in row['cases']], [401,403,404,400,400,413])
        self.assertEqual(len(self.http.call_args_list[-1].kwargs['body']), 10*1024*1024+1)


if __name__ == '__main__': unittest.main()
