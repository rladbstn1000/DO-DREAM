"""ENTRYPOINT_DISPATCH_TEST only: synthetic metadata, no Docker/DB/Java/browser execution."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import unittest
from unittest import mock

import isolated_boundary_tests as boundary
import isolated_provenance as provenance
import isolated_trial as trial
from test_isolated_provenance import scenario, RUN_ID, BEGIN, END


def forbidden(*args, **kwargs):
    raise AssertionError('Pure entrypoint test attempted an actual executor or network operation')


class JavaBoundaryEntrypointTests(unittest.TestCase):
    def setUp(self):
        self.stack=contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        for module,name in ((subprocess,'run'),(subprocess,'Popen'),(subprocess,'check_call'),(subprocess,'check_output'),
                            (os,'system'),(os,'popen'),(socket,'socket'),(socket,'create_connection')):
            self.stack.enter_context(mock.patch.object(module,name,side_effect=forbidden))
        self.stack.enter_context(mock.patch.dict(os.environ,{},clear=True))
        self.root=Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix='dodream-java-entrypoint-'))).resolve()
        self.runtime=mock.Mock()
        self.runtime.root=self.root
        self.runtime.results=self.root/'results'
        self.runtime.manifest_path=self.root/'scripts/local/isolated-trial.json'
        self.runtime.attempt_id='synthetic-java-attempt'
        self.runtime.preparation=None
        self.before,self.observed,self.expected=scenario()
        self.receipt=provenance.validate_created(self.before,self.observed,self.expected,RUN_ID,BEGIN,END)
        self.runtime._receipt.return_value=self.receipt
        self.runtime._revision_records.return_value=[(self.root/'004-fixed-03',{})]
        self.images={'be':{'source':{'sourceDigest':'SYNTHETIC_SOURCE_DIGEST'}}}
        self.runtime._image_records.return_value=self.images
        self.runtime.observe.side_effect=lambda expected:copy.deepcopy(self.observed)
        self.runtime._raw.side_effect=forbidden
        self.handlers={signal.SIGINT:'original-int',signal.SIGTERM:'original-term'}
        self.signal_calls=[]
        def install(sig,handler):
            previous=self.handlers[sig]
            self.handlers[sig]=handler
            self.signal_calls.append((sig,handler))
            return previous
        self.stack.enter_context(mock.patch.object(trial.signal,'signal',side_effect=install))

    def argv(self,*extra):
        return ['--manifest',str(self.runtime.manifest_path),'--action','java-boundary',
                '--revision','004-fixed-03','--attempt',self.runtime.attempt_id,*extra]

    def main(self,argv):
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            return trial.main(argv)

    def test_help_and_plan_never_construct_runtime_or_execute(self):
        with mock.patch.object(trial,'TrialRuntime',side_effect=forbidden),mock.patch.object(boundary,'run',side_effect=forbidden):
            with self.assertRaises(SystemExit) as exited:
                self.main(['--help'])
            self.assertEqual(exited.exception.code,0)
            with mock.patch.object(trial,'load_manifest',return_value={'synthetic':True}), \
                 mock.patch.object(trial,'build_plan',return_value={'execution':'NOT_RUN'}):
                self.assertEqual(self.main(['--manifest',str(self.runtime.manifest_path),'--action','plan']),0)

    def test_explicit_revision_attempt_and_no_overrides_required_before_runtime(self):
        with mock.patch.object(trial,'TrialRuntime',side_effect=forbidden):
            for argv in (['--manifest',str(self.runtime.manifest_path),'--action','java-boundary'],
                         self.argv('--suite','auth'),self.argv('--include-source','anything'),
                         self.argv('--services','worker'),self.argv('--payload','[]')):
                with self.subTest(argv=argv):
                    self.assertEqual(self.main(argv),2)

    def test_java_plan_uses_exact_helper_classes_and_three_services_without_runtime_or_secrets(self):
        manifest={'schema':1,'id':'evidence-portability-20261014','project':'dodream-evidence-20261014',
            'root':'.local/isolated/evidence-portability-20261014','credentials':'credentials.env',
            'origins':{'main':'http://127.0.0.1:25173','short':'http://127.0.0.1:25174'}}
        self.runtime.manifest_path.parent.mkdir(parents=True)
        self.runtime.manifest_path.write_text(json.dumps(manifest))
        with mock.patch.object(trial,'TrialRuntime',side_effect=forbidden), \
             mock.patch.object(boundary,'run',side_effect=forbidden), \
             mock.patch.object(trial,'__file__',str(self.root/'scripts/local/isolated_trial.py')):
            output=io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(trial.main(['--manifest',str(self.runtime.manifest_path),
                    '--action','java-boundary-plan','--revision','004-fixed-03','--attempt','planned-java']),0)
            result=json.loads(output.getvalue())
        self.assertEqual(result['requiredServices'],['mysql','redis','ai'])
        self.assertEqual(result['javaClasses'],list(boundary.CLASSES))
        self.assertEqual(result['testCommand'],boundary.COMMAND)
        self.assertFalse(result['executionAuthorized'])
        self.assertEqual(result['resourceProvenance'],'NOT_CHECKED')
        self.assertFalse((self.root/'.local').exists())

    def test_bad_manifest_constructor_failure_never_dispatches(self):
        with mock.patch.object(trial,'TrialRuntime',side_effect=trial.PolicyError('Synthetic invalid manifest')), \
             mock.patch.object(boundary,'run') as run:
            self.assertEqual(self.main(self.argv()),2)
            run.assert_not_called()
        self.runtime.compose.assert_not_called()

    def test_dispatch_starts_only_three_services_then_calls_existing_helper_and_cleanup(self):
        with mock.patch.object(trial,'TrialRuntime',return_value=self.runtime), \
             mock.patch.object(trial,'prepare_java_boundary') as prepare, \
             mock.patch.object(boundary,'run',return_value={'status':'SYNTHETIC_DISPATCH_ONLY'}) as run:
            self.assertEqual(self.main(self.argv()),0)
        prepare.assert_called_once_with(self.runtime,'004-fixed-03')
        self.assertEqual(self.runtime.compose.call_args_list,[mock.call('java-boundary-stores','start','mysql','redis'),
            mock.call('java-boundary-local-provider','start','ai')])
        run.assert_called_once_with(self.runtime)
        self.runtime.stop_started.assert_called_once_with()
        self.assertEqual(self.handlers,{signal.SIGINT:'original-int',signal.SIGTERM:'original-term'})

    def test_validate_keeps_browser_integration_separate_from_java(self):
        with mock.patch.object(trial,'TrialRuntime',return_value=self.runtime), \
             mock.patch('isolated_checks.run_auth') as auth,mock.patch('isolated_checks.run_remaining') as remaining, \
             mock.patch.object(boundary,'run',side_effect=forbidden):
            self.assertEqual(self.main(['--manifest',str(self.runtime.manifest_path),'--action','validate']),0)
        auth.assert_called_once_with(self.runtime)
        remaining.assert_called_once_with(self.runtime)
        self.runtime.stop_started.assert_called_once_with()

    def test_helper_failure_and_both_signals_use_owned_finally_cleanup(self):
        for failure in ('exception',signal.SIGINT,signal.SIGTERM):
            with self.subTest(failure=failure):
                self.runtime.stop_started.reset_mock()
                def invoke(runtime):
                    if failure=='exception':raise RuntimeError('Synthetic helper failure')
                    self.handlers[failure](failure,None)
                with mock.patch.object(trial,'TrialRuntime',return_value=self.runtime), \
                     mock.patch.object(trial,'prepare_java_boundary'),mock.patch.object(boundary,'run',side_effect=invoke):
                    self.assertEqual(self.main(self.argv()),2)
                self.runtime.stop_started.assert_called_once_with()
                self.assertEqual(self.handlers,{signal.SIGINT:'original-int',signal.SIGTERM:'original-term'})

    def test_signal_handlers_restore_even_when_owned_cleanup_fails(self):
        self.runtime.stop_started.side_effect=RuntimeError('Synthetic cleanup refusal')
        with self.assertRaisesRegex(RuntimeError,'cleanup refusal'):
            trial.run_with_owned_cleanup(self.runtime,lambda:{'synthetic':True})
        self.assertEqual(self.handlers,{signal.SIGINT:'original-int',signal.SIGTERM:'original-term'})

    def test_preflight_validates_current_sources_receipt_and_attempt_before_stage(self):
        trial.prepare_java_boundary(self.runtime,'004-fixed-03')
        self.runtime.verify_image_sources.assert_called_once_with(self.images)
        self.runtime.prepare_attempt.assert_called_once_with()
        self.runtime._check_attempt_binding.assert_called_once_with(self.receipt)
        self.runtime.set_stage.assert_called_once_with('auth','browser')
        self.runtime.compose.assert_not_called()
        self.runtime._raw.assert_not_called()

    def test_fresh_attempt_actual_stage_and_operation_allow_three_services_but_refuse_consumers(self):
        runtime=trial.TrialRuntime.__new__(trial.TrialRuntime)
        runtime.root=self.root
        runtime.repo=self.root/'synthetic-repo'
        runtime.project='dodream-evidence-20261014'
        runtime.manifest={'id':'evidence-portability-20261014'}
        runtime.run_id=RUN_ID
        runtime.attempt_id='synthetic-java-fresh'
        runtime.attempt_root=self.root/'attempts'/runtime.attempt_id
        runtime.results=runtime.attempt_root/'results'
        runtime.fixtures=runtime.attempt_root/'fixtures'
        runtime.plans=runtime.attempt_root/'browser-ui'
        images={'be':{'id':'sha256:'+'a'*64,'source':{'sourceDigest':'b'*64}}}
        runtime._image_records=mock.Mock(return_value=images)
        runtime._revision_records=mock.Mock(return_value=[(self.root/'004-fixed-03',{})])
        runtime.verify_image_sources=mock.Mock()
        runtime.source_identity=mock.Mock(return_value={'working_source_sha256':trial.digest({'be':'b'*64})})
        base_row=copy.deepcopy(self.observed['containers']['mysql'])
        base_spec=copy.deepcopy(self.expected['services']['mysql'])
        for index,name in enumerate(sorted((set(trial.SUITES['auth'])|set(trial.CONSUMERS))-{'mysql'}),1):
            self.observed['containers'][name]={**copy.deepcopy(base_row),'id':f'{index:064x}','service':name}
            self.expected['services'][name]=copy.deepcopy(base_spec)
        receipt=provenance.validate_created(self.before,self.observed,self.expected,RUN_ID,BEGIN,END)
        runtime._receipt=mock.Mock(return_value=receipt)
        runtime.observe=mock.Mock(side_effect=lambda expected:copy.deepcopy(self.observed))
        runtime.verify_pending_work=mock.Mock(side_effect=forbidden)
        runtime._raw=mock.Mock(side_effect=forbidden)

        # Real attempt creation/binding, set_stage and operation policy must work without fake auth success.
        trial.prepare_java_boundary(runtime,'004-fixed-03')
        self.assertFalse((runtime.attempt_root/'auth-pass.json').exists())
        stage=json.loads((self.root/'active-stage.json').read_text())
        self.assertEqual((stage['suite'],stage['phase'],stage['attemptId']),
                         ('auth','browser','synthetic-java-fresh'))
        allowed=runtime._allowed_services('start')
        self.assertLessEqual({'mysql','redis','ai'},allowed)
        self.assertFalse(set(trial.CONSUMERS)&allowed)
        for names in (('mysql','redis'),('ai',)):
            with self.subTest(allowed_services=names),self.assertRaisesRegex(AssertionError,'actual executor'):
                runtime.compose('synthetic-dispatch-only','start',*names)
            runtime._raw.assert_called_with(['start',*[self.observed['containers'][name]['id'] for name in names]],
                                           stdin=None,timeout=180)
        attempted_calls=runtime._raw.call_count
        for consumer in trial.CONSUMERS:
            with self.subTest(forbidden_service=consumer),self.assertRaisesRegex(trial.PolicyError,'outside active stage'):
                runtime.compose('synthetic-consumer-refusal','start',consumer)
        self.assertEqual(runtime._raw.call_count,attempted_calls)
        runtime.verify_pending_work.assert_not_called()
        self.assertFalse((runtime.attempt_root/'auth-pass.json').exists())

    def test_bad_receipt_revision_or_attempt_refuses_before_any_start(self):
        cases=[('receipt',lambda:setattr(self.runtime._receipt,'side_effect',trial.PolicyError('Synthetic invalid receipt'))),
               ('revision',lambda:setattr(self.runtime._revision_records,'return_value',[(self.root/'003-fixed-02',{})])),
               ('attempt',lambda:setattr(self.runtime,'attempt_id','../previous'))]
        for name,change in cases:
            with self.subTest(name=name):
                self.runtime._receipt.side_effect=None
                self.runtime._revision_records.return_value=[(self.root/'004-fixed-03',{})]
                self.runtime.attempt_id='synthetic-java-attempt'
                change()
                with self.assertRaises(trial.PolicyError):trial.prepare_java_boundary(self.runtime,'004-fixed-03')
                self.runtime.prepare_attempt.assert_not_called()
                self.runtime.compose.assert_not_called()
        self.runtime._raw.assert_not_called()

    def test_attempt_preparation_or_revision_binding_failure_does_not_start_or_stop_resources(self):
        for method in ('prepare_attempt','_check_attempt_binding'):
            with self.subTest(method=method):
                self.runtime.prepare_attempt.side_effect=None
                self.runtime._check_attempt_binding.side_effect=None
                getattr(self.runtime,method).side_effect=trial.PolicyError('Synthetic attempt refused')
                with self.assertRaisesRegex(trial.PolicyError,'attempt refused'):
                    trial.prepare_java_boundary(self.runtime,'004-fixed-03')
                self.runtime.compose.assert_not_called()
                self.runtime.stop_started.assert_not_called()

    def test_existing_container_volume_endpoint_or_running_service_refused_by_actual_provenance(self):
        original=copy.deepcopy(self.observed)
        changes=[lambda value:value['containers']['mysql'].update(id=self.before['containers'][0]),
                 lambda value:value['containers']['mysql']['mounts'][0].update(source='dodream-phase1_mysql-data'),
                 lambda value:value['containers']['mysql']['ports'].update({'3306/tcp':[{'HostIp':'0.0.0.0','HostPort':'3306'}]}),
                 lambda value:value['containers']['mysql'].update(state='running')]
        for change in changes:
            with self.subTest(change=change):
                self.observed=copy.deepcopy(original)
                change(self.observed)
                with self.assertRaises((trial.PolicyError,provenance.ProvenanceError)):
                    trial.prepare_java_boundary(self.runtime,'004-fixed-03')
                self.runtime.prepare_attempt.assert_not_called()
                self.runtime.compose.assert_not_called()

    def test_successful_same_source_http_fixture_is_file_blocked_without_metadata_or_database_reads(self):
        directory=self.root/'boundary-tests/004-fixed-03/prior-attempt'
        directory.mkdir(parents=True)
        value={'status':'PASS','sourceDigest':'SYNTHETIC_SOURCE_DIGEST','classes':[
            {'class':'A704.DODREAM.indexing.IndexingRequestBoundaryDatabaseTests','tests':6,'failures':0,'errors':0,'skipped':0}]}
        filename=directory/'result.json'
        filename.write_text(json.dumps(value))
        before=filename.read_bytes()
        with self.assertRaisesRegex(trial.PolicyError,'already completed its fixed HTTP fixture'):
            trial.prepare_java_boundary(self.runtime,'004-fixed-03')
        self.assertEqual(filename.read_bytes(),before)
        self.runtime.observe.assert_not_called()
        self.runtime.verify_image_sources.assert_not_called()
        self.runtime.prepare_attempt.assert_not_called()
        self.runtime.compose.assert_not_called()
        self.runtime.sql.assert_not_called()

    def test_selected_classes_and_zero_or_skipped_results_still_use_existing_helper_policy(self):
        self.assertEqual(boundary.CLASSES,('A704.DODREAM.indexing.IndexingObservationTests',
            'A704.DODREAM.indexing.IndexingRequestBoundaryDatabaseTests','A704.DODREAM.file.FileInputBoundaryTests',
            'A704.DODREAM.file.PdfUploadPermissionBoundaryTests'))
        self.assertEqual([boundary.COMMAND[i+1] for i,value in enumerate(boundary.COMMAND) if value=='--tests'],
                         ['*.'+name.rsplit('.',1)[1] for name in boundary.CLASSES])
        reports=[{'class':name,'tests':1,'failures':0,'errors':0,'skipped':0} for name in boundary.CLASSES]
        self.assertEqual(boundary.junit_outcome(0,'0',reports,[],'')['status'],'PASS')
        for field in ('tests','skipped'):
            bad=copy.deepcopy(reports)
            bad[0][field]=0 if field=='tests' else 1
            self.assertEqual(boundary.junit_outcome(0,'0',bad,[],'')['status'],'FAIL')


if __name__=='__main__':
    unittest.main(verbosity=2)
