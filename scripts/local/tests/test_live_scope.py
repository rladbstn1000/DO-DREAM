"""No Docker/provider connections. Scope and launch denial stay independently tested."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import live_ai
import manage
import scope_guard
from scope_guard import validate_plan, require_keyless_local, ScopeError
from test_scope_guard import plan, row, ROOT

class LiveScopeTests(unittest.TestCase):
    def live(self):
        p=plan();p['services']['ai']={'environment':{'DODREAM_AI_MODE':'LIVE_OPENAI','LIVE_API_AUTHORIZED':'true'},
            'networks':{'default':{},'gateway':{}},'volumes':[
                {'type':'bind','source':str(ROOT/'.local/phase5/live/manifest.json'),'target':'/run/dodream-live/manifest.json','read_only':True},
                {'type':'bind','source':str(Path.home()/'.config/dodream/provider-live.env'),'target':'/run/secrets/dodream-provider-live.env','read_only':True}]}
        return p
    def test_only_explicit_live_ai_gets_fixed_readonly_mounts(self):
        validate_plan(self.live(),ROOT)
    def test_key_file_presence_cannot_enable_live_session(self):
        with patch.dict(os.environ,{'LIVE_API_AUTHORIZED':'false'},clear=True),patch.object(live_ai,'metadata_only_key') as key:
            with self.assertRaisesRegex(RuntimeError,'LIVE_NOT_AUTHORIZED'):live_ai.preflight()
            key.assert_not_called()
    def test_running_images_and_future_ai_tag_must_match_offline_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'live-offline-contract.json').write_text(json.dumps({
                'validated_image_ids':{s:'sha256:'+s for s in ('ai','be','web')}}))
            rows={s:{'id':s+'-container','image_tag':s+'-tag'} for s in ('ai','be','web')}
            for mismatch in (None,'be-container','ai-tag'):
                def read(args,env):
                    if args[-1]==mismatch:return 'sha256:unexpected'
                    return 'sha256:'+args[-1].split('-')[0]
                with self.subTest(mismatch=mismatch),patch.object(manage,'RESULTS',root),\
                     patch.object(manage,'clean_env',return_value={}),patch.object(scope_guard,'_read',side_effect=read):
                    if mismatch:
                        with self.assertRaisesRegex(RuntimeError,'NOT_TESTED'):live_ai.require_tested_images(rows)
                    else:live_ai.require_tested_images(rows)
    def test_live_plan_requires_authorization_and_both_fixed_mounts(self):
        for transform in (lambda s:s['environment'].update(LIVE_API_AUTHORIZED='false'),
                          lambda s:s['volumes'].pop(),lambda s:s['volumes'][1].update(source='/other/project/key.env'),
                          lambda s:s['volumes'][1].update(read_only=False)):
            p=self.live();transform(p['services']['ai'])
            with self.assertRaises(ScopeError):validate_plan(p,ROOT)
    def test_shared_worker_cannot_become_live_or_receive_key(self):
        for mode in ('LOCAL_FAKE','LIVE_OPENAI'):
            p=self.live();p['services']['worker']=copy.deepcopy(p['services'].pop('ai'))
            p['services']['worker']['environment']['DODREAM_AI_MODE']=mode
            with self.assertRaises(ScopeError):validate_plan(p,ROOT)
    def test_local_ai_cannot_have_gateway_or_live_flags(self):
        p=self.live();p['services']['ai']['environment']={'DODREAM_AI_MODE':'LOCAL_FAKE','LIVE_API_AUTHORIZED':'false'}
        with self.assertRaises(ScopeError):validate_plan(p,ROOT)
        p['services']['ai']['volumes']=[]
        with self.assertRaises(ScopeError):validate_plan(p,ROOT)

    def test_close_stops_live_ai_before_replacement_consumer_blocks_restore(self):
        for replacement in ('worker','index-dispatcher'):
            with self.subTest(replacement=replacement),tempfile.TemporaryDirectory() as directory:
                session=Path(directory)/'session.json'
                before={service:{'id':service+'-original','state':'running'}
                        for service in ('ai','worker','index-dispatcher','web')}
                session.write_text(json.dumps({'state':'OPEN','before':before}))
                current=copy.deepcopy(before);current[replacement]['id']='replacement-id'
                actions=[];states=[]
                def execute(name,args,live=False):actions.append((name,args))
                def save(value):states.append(copy.deepcopy(value))
                with patch.object(live_ai,'SESSION',session),patch.object(live_ai,'owned',return_value=current),\
                     patch.object(live_ai,'execute',side_effect=execute),patch.object(live_ai,'save_session',side_effect=save),\
                     patch.object(live_ai,'preflight',side_effect=AssertionError('revocation needs no approval')):
                    with self.assertRaisesRegex(RuntimeError,'LOCAL_CONSUMER_ID_CHANGED'):
                        live_ai.close_session()
                self.assertEqual(actions,[('live-ai-close',['stop','ai'])])
                self.assertEqual(states[-1]['state'],'LIVE_STOPPED_RESTORING')
                self.assertFalse(any(name.startswith('local-restore') for name,_ in actions))

    def test_close_does_not_claim_closed_if_ai_stop_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            session=Path(directory)/'session.json'
            session.write_text(json.dumps({'state':'OPEN','before':{}}))
            with patch.object(live_ai,'SESSION',session),patch.object(live_ai,'owned',return_value={}),\
                 patch.object(live_ai,'execute',side_effect=RuntimeError('STOP_FAILED')),\
                 patch.object(live_ai,'save_session') as save:
                with self.assertRaisesRegex(RuntimeError,'STOP_FAILED'):live_ai.close_session()
                save.assert_not_called()
            self.assertEqual(json.loads(session.read_text())['state'],'OPEN')

    def test_contract_digest_invalidates_each_runtime_gate_and_test_change(self):
        paths=('compose.local.yml','compose.live.yml','scripts/local/live_ai.py','scripts/local/scope_guard.py',
               'scripts/local/manage.py','scripts/local/tests/test_live_scope.py','scripts/evaluation/phase5.py',
               'scripts/evaluation/phase5_data/freeze.json','ai/app/providers/budget.py',
               'ai/app/evaluation_run.py','ai/tests/test_provider.py','be/src/main/Example.java',
               'fe-web/src/Example.ts','fe-web/tests/example.mjs','ai/Dockerfile.local',
               'ai/requirements.local.lock.txt','be/Dockerfile.local','fe-web/Dockerfile.local','fe-web/package-lock.json')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for relative in paths:
                path=root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('original')
            with patch.object(live_ai,'ROOT',root):
                original=live_ai.contract_digest()
                for relative in paths:
                    with self.subTest(path=relative):
                        path=root/relative;path.write_text('changed')
                        self.assertNotEqual(live_ai.contract_digest(),original)
                        path.write_text('original')
                        self.assertEqual(live_ai.contract_digest(),original)

    def test_contract_digest_does_not_read_excluded_metadata_or_bytecode(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);cache=root/'scripts/local/__pycache__';cache.mkdir(parents=True)
            cache_file=cache/'ignored.pyc';cache_file.write_text('ignored')
            metadata=root/'scripts/local/.DS_Store';metadata.write_text('ignored')
            original_read=Path.read_bytes
            def protected_read(path):
                if path in (metadata,cache_file):raise AssertionError('excluded file read')
                return original_read(path)
            with patch.object(live_ai,'ROOT',root),patch.object(Path,'read_bytes',protected_read):
                self.assertEqual(live_ai.contract_digest(),__import__('hashlib').sha256().hexdigest())

    def test_local_regression_requires_exactly_one_keyless_internal_ai(self):
        clean=row(service='ai',name=scope_guard.PROJECT+'-ai-1',mounts=[])
        require_keyless_local([clean])
        forbidden=[[],[clean,copy.deepcopy(clean)],
                   [{**clean,'mounts':[{'type':'bind'}]}],
                   [{**clean,'networks':[scope_guard.PROJECT+'_default',scope_guard.PROJECT+'_gateway']}],
                   [{**clean,'project':'another-project'}]]
        for rows in forbidden:
            with self.subTest(rows=rows),self.assertRaisesRegex(ScopeError,'Local regression refused'):
                require_keyless_local(rows)

    def test_all_regression_entrypoints_refuse_live_ai_before_any_suite(self):
        live=row(service='ai',name=scope_guard.PROJECT+'-ai-1',mounts=[{'type':'bind'}])
        commands=('test','auth','authorization','grading','indexing','startup','smoke','security',
                  'persistence','demo-api','student-web')
        for command in commands:
            with self.subTest(command=command),patch.object(sys,'argv',['manage.py',command]),\
                 patch.object(manage,'settings',return_value={}),patch.object(manage,'clean_env',return_value={}),\
                 patch.object(scope_guard,'read_metadata',return_value=[live]),\
                 patch.object(manage,'run') as run,patch.object(manage,'unit_tests') as units:
                with self.assertRaisesRegex(ScopeError,'Local regression refused'):manage.main()
                run.assert_not_called();units.assert_not_called()

    def test_local_exec_gate_checks_actual_container_not_only_local_plan(self):
        p=plan();p['services']['ai']={'environment':{'DODREAM_AI_MODE':'LOCAL_FAKE','LIVE_API_AUTHORIZED':'false'},
                                   'networks':{'default':{}}}
        live=row(service='ai',name=scope_guard.PROJECT+'-ai-1',mounts=[{'type':'bind','rw':False,
                 'source':str(Path.home()/'.config/dodream/provider-live.env'),
                 'destination':'/run/secrets/dodream-provider-live.env'}])
        def read(args,env):
            if args[:3]==['docker','context','inspect']:return 'unix:///synthetic/docker.sock'
            if args[0]=='synthetic-compose':return json.dumps(p)
            if args[:3]==['docker','volume','ls']:return '\n'.join(sorted(scope_guard.EXISTING_VOLUMES))
            if args[:3] in (['docker','volume','inspect'],['docker','network','inspect']):return scope_guard.PROJECT
            raise AssertionError('unexpected external operation')
        with patch.object(scope_guard,'_read',side_effect=read),patch.object(scope_guard,'read_metadata',return_value=[live]):
            with self.assertRaisesRegex(ScopeError,'Local regression refused'):
                scope_guard._gate(['exec','-T','ai','python','-m','unittest'],['synthetic-compose'],ROOT,{})

if __name__=='__main__':unittest.main()
