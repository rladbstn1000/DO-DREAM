"""Synthetic command/metadata checks only; never contacts Docker."""
import copy
from pathlib import Path
import sys
import unittest
import socket
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scope_guard import command_scope,validate_inventory,validate_plan,preservation_status,port_available,ScopeError,PROJECT,RUN_LABEL

ROOT=Path('/synthetic/dodream')
def plan():
    return {'name':PROJECT,'services':{'be':{'build':{'context':str(ROOT/'be'),'dockerfile':'Dockerfile.local'},'networks':{'default':{}}},'web':{'ports':[{'host_ip':'127.0.0.1','published':'15173'}],'networks':{'default':{},'gateway':{}}}},'volumes':{'be-data':{'name':PROJECT+'_be-data'}},'networks':{'default':{'name':PROJECT+'_default','internal':True},'gateway':{'name':PROJECT+'_gateway'}}}
def row(**changes):
    return {'id':'synthetic-id','name':PROJECT+'-be-1','project':PROJECT,'service':'be','image_tag':PROJECT+'-be','networks':[PROJECT+'_default'],'mounts':[{'type':'volume','name':PROJECT+'_be-data','source':'/synthetic-volume','destination':'/app/local-data','rw':True}],**changes}

class CommandScopeTests(unittest.TestCase):
    def test_known_exec_targets_only_redis(self):self.assertEqual(command_scope(['exec','-T','redis','redis-cli','GET','owned:key']),('exec',['redis']))
    def test_foreign_service_refused(self):
        with self.assertRaises(ScopeError):command_scope(['stop','etch-backend'])
    def test_unknown_service_refused(self):
        with self.assertRaises(ScopeError):command_scope(['restart','mystery'])
    def test_override_project_refused(self):
        with self.assertRaises(ScopeError):command_scope(['-p','etch','stop'])
    def test_other_compose_file_refused(self):
        with self.assertRaises(ScopeError):command_scope(['--file','other.yml','up'])
    def test_global_delete_verbs_refused(self):
        for verb in ('down','rm','prune','system','volume','kill'):
            with self.subTest(verb=verb),self.assertRaises(ScopeError):command_scope([verb])
    def test_redis_flush_is_refused(self):
        for payload in (['redis-cli','FLUSHDB'],['redis-cli','EVAL',"redis.call('FLUSHALL')",'0']):
            with self.subTest(payload=payload),self.assertRaises(ScopeError):command_scope(['exec','-T','redis',*payload])
    def test_anonymous_one_off_refused(self):
        with self.assertRaises(ScopeError):command_scope(['run','--rm','--no-deps','be-test'])
    def test_labelled_one_off_allowed(self):
        self.assertEqual(command_scope(['--profile','test','run','--rm','--no-deps','--name','dodream-phase2b-test-123','--label',RUN_LABEL,'be-test']),('run',['be-test']))
    def test_foreign_one_off_name_refused(self):
        with self.assertRaises(ScopeError):command_scope(['run','--rm','--no-deps','--name','etch-test','--label',RUN_LABEL,'be-test'])
    def test_other_env_override_refused(self):
        with self.assertRaises(ScopeError):command_scope(['run','--rm','--no-deps','--name','dodream-phase2b-test-123','--label',RUN_LABEL,'-e','DATABASE_URL=foreign','be-test'])
    def test_invalid_profile_refused(self):
        with self.assertRaises(ScopeError):command_scope(['--profile','production','up'])

class MetadataScopeTests(unittest.TestCase):
    def test_valid_owned_inventory(self):self.assertEqual(validate_inventory([row()],{PROJECT+'-be'},ROOT),[row()])
    def test_name_is_not_ownership(self):
        with self.assertRaises(ScopeError):validate_inventory([row(project='etch')],(),ROOT)
    def test_unknown_labelled_service_refused(self):
        with self.assertRaises(ScopeError):validate_inventory([row(service='mystery')],(),ROOT)
    def test_foreign_project_volume_refused(self):
        with self.assertRaises(ScopeError):validate_inventory([row(name='etch',project='etch',networks=[])],(),ROOT)
    def test_foreign_project_network_refused(self):
        with self.assertRaises(ScopeError):validate_inventory([row(name='etch',project='etch',mounts=[])],(),ROOT)
    def test_foreign_build_tag_refused(self):
        with self.assertRaises(ScopeError):validate_inventory([row(name='etch',project='etch',mounts=[],networks=[])],{PROJECT+'-be'},ROOT)
    def test_own_foreign_mount_refused(self):
        with self.assertRaises(ScopeError):validate_inventory([row(mounts=[{'type':'volume','name':'etch_data'}])],(),ROOT)
    def test_docker_socket_bind_refused(self):
        with self.assertRaises(ScopeError):validate_inventory([row(mounts=[{'type':'bind','source':'/var/run/docker.sock','rw':True}])],(),ROOT)
    def test_foreign_ancestor_bind_refused(self):
        with self.assertRaises(ScopeError):validate_inventory([row(name='other',project='other',networks=[],mounts=[{'type':'bind','source':'/synthetic','rw':True}])],(),ROOT)
    def test_own_foreign_network_refused(self):
        with self.assertRaises(ScopeError):validate_inventory([row(networks=['etch_default'])],(),ROOT)
    def test_unrelated_prebuilt_image_is_read_only(self):
        foreign=row(name='other-mysql',project='other',service='mysql',image_tag='mysql:8.4',mounts=[],networks=[])
        self.assertEqual(validate_inventory([foreign],{PROJECT+'-be'},ROOT),[])

class PlanScopeTests(unittest.TestCase):
    def test_local_plan_allowed(self):self.assertIn(PROJECT+'-be',validate_plan(plan(),ROOT)[0])
    def test_external_volume_refused(self):
        p=plan();p['volumes']['be-data']['external']=True
        with self.assertRaises(ScopeError):validate_plan(p,ROOT)
    def test_foreign_build_context_refused(self):
        p=plan();p['services']['be']['build']['context']='/other-project'
        with self.assertRaises(ScopeError):validate_plan(p,ROOT)
    def test_wrong_service_build_context_refused(self):
        p=plan();p['services']['be']['build']['context']=str(ROOT/'ai')
        with self.assertRaises(ScopeError):validate_plan(p,ROOT)
    def test_public_port_refused(self):
        p=plan();p['services']['web']['ports'][0]['host_ip']='0.0.0.0'
        with self.assertRaises(ScopeError):validate_plan(p,ROOT)
    def test_noninternal_application_network_refused(self):
        p=plan();p['networks']['default']['internal']=False
        with self.assertRaises(ScopeError):validate_plan(p,ROOT)
    def test_privileged_refused(self):
        p=plan();p['services']['be']['privileged']=True
        with self.assertRaises(ScopeError):validate_plan(p,ROOT)

class PreservationTests(unittest.TestCase):
    def test_missing_and_empty_evidence_are_not_run(self):
        for evidence in (None,{}, {'checks':[]}):self.assertEqual(preservation_status(True,evidence),'NOT_RUN')
    def test_executed_failure_and_missing_volume_remain_fail(self):
        self.assertEqual(preservation_status(True,{'checks':[{'status':'FAIL'}]}),'FAIL')
        self.assertEqual(preservation_status(False,None),'FAIL')
    def test_blocked_is_distinct_from_pass(self):
        self.assertEqual(preservation_status(True,{'checks':[{'status':'BLOCKED'}]}),'BLOCKED')
        self.assertEqual(preservation_status(True,{'checks':[{'status':'PASS'}]}),'PASS')

class LocalPortTests(unittest.TestCase):
    def test_active_listener_is_refused_even_with_reuseaddr(self):
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            listener.bind(('127.0.0.1',0));listener.listen()
            self.assertFalse(port_available(listener.getsockname()[1]))
    def test_closed_listener_becomes_available(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1',0));port=listener.getsockname()[1];listener.listen()
        self.assertTrue(port_available(port))

if __name__=='__main__':unittest.main()
