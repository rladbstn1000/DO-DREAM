"""Ledger/authorization tests; real Chroma and Celery are separate HTTP integration checks."""
import copy
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from fastapi import HTTPException
from sqlalchemy import event
from sqlalchemy.exc import OperationalError
import runtime_fixture
import test_object_authorization as authz
from app.common.db_session import SessionLocal,engine,Base
from app.common.models import Material,UploadedFile
from app.common.database import get_user_from_db
from app.indexing import store,chroma,hooks
from app.indexing.models import IndexResource,IndexJob,IndexExecution
from app.indexing.source import normalize_source,parse_snapshot,make_chunks,INDEX_SPEC
from app.indexing.worker import process
from app.indexing.dispatcher import dispatch_once
from app.rag.database import SessionLocal as RagSession
from app.rag.models import ChatMessage


class IndexingContractTests(unittest.TestCase):
    headers=authz.ObjectAuthorizationTests.headers
    chat=authz.ObjectAuthorizationTests.chat

    @classmethod
    def setUpClass(cls):
        authz.ObjectAuthorizationTests.setUpClass()
        cls.client=authz.ObjectAuthorizationTests.client

    def setUp(self):
        authz.ObjectAuthorizationTests.setUp(self)

    def source(self,suffix='one'):
        return {'chapters':[{'type':'content','content':'[INDEX LOCAL] '+suffix+' '+('Synthetic learning content. '*100)},
            {'type':'quiz','content':'PRIVATE_QUIZ_TEXT','qa':[{'question':'q','answer':'ANSWER_CANARY'}]}]}

    def job(self,suffix='one',spec=INDEX_SPEC):
        return store.accept_source(authz.OWNER,str(authz.DOC),authz.KEY,self.source(suffix),spec)

    def rows(self,job):
        with SessionLocal() as db:
            j=db.query(IndexJob).filter(IndexJob.job_id==job['job_id']).one()
            r=db.get(IndexResource,j.resource_pk)
            e=db.query(IndexExecution).filter(IndexExecution.job_pk==j.id).order_by(IndexExecution.generation).all()
            return {'state':j.state,'delivery':j.delivery_attempts,'generation':j.execution_generation,
                'active':r.active_execution_id,'activations':r.activation_count,
                'execution_ids':[x.id for x in e],'candidates':[x.candidate_name for x in e],
                'snapshot':j.snapshot_json,'revision':j.source_revision,'hash':j.source_hash}

    def fault(self,job,value):
        root=hooks.directory();root.mkdir(parents=True,exist_ok=True)
        path=root/(job['job_id']+'.json');path.write_text(json.dumps(value))
        self.addCleanup(lambda:path.unlink(missing_ok=True))
        return path

    def principal(self):
        with SessionLocal() as db:return get_user_from_db(db,authz.OWNER)

    def expire(self,job):
        with SessionLocal.begin() as db:
            j=db.query(IndexJob).filter(IndexJob.job_id==job['job_id']).one()
            db.query(IndexExecution).filter(IndexExecution.job_pk==j.id,IndexExecution.generation==j.execution_generation).update({'lease_until':store.now(db)-timedelta(seconds=1)})

    def test_source_snapshot_is_string_only_canonical_and_excludes_answers(self):
        raw,digest,size=normalize_source(self.source(),'MATERIAL')
        self.assertNotIn('CANARY',raw);self.assertNotIn('PRIVATE_QUIZ_TEXT',raw)
        self.assertEqual(hashlib.sha256(raw.encode()).hexdigest(),digest)
        self.assertEqual(len(raw.encode()),size)
        self.assertEqual(parse_snapshot(raw,digest,size),json.loads(raw))
        with self.assertRaises(ValueError):parse_snapshot(raw+' ',digest,size)
        for value in ('\ud800','\x01'):
            with self.assertRaises(ValueError):normalize_source({'chapters':[{'type':'content','content':value}]},'MATERIAL')

    def test_initial_pdf_nested_concept_checks_never_enter_source(self):
        raw,_,_=normalize_source({'parsedData':{'data':[{'titles':[
            {'title':'Safe','s_titles':[{'s_title':'개념 Check','contents':'SENTINEL_A'},
                {'s_title':'Safe sub','contents':'safe learning','ss_titles':[
                    {'ss_title':'개념 check','contents':123},{'ss_title':'Safe nested','contents':'safe nested'}]}]},
            {'title':'개념 Check','s_titles':[{'contents':'SENTINEL_C'}]}]}]}},'PDF')
        self.assertNotIn('SENTINEL',raw)
        self.assertIn('safe learning',raw);self.assertIn('safe nested',raw)

    def test_same_source_spec_is_same_job_and_old_duplicate_cannot_become_latest(self):
        first=self.job();second=self.job()
        self.assertEqual(first['job_id'],second['job_id'])
        newer=self.job(spec='local-hash8-content-v2')
        self.assertEqual(self.rows(first)['revision'],self.rows(newer)['revision'])
        replay=self.job()
        self.assertEqual(replay['job_id'],first['job_id'])
        self.assertEqual(process(first['job_id'])['status'],'ignored')
        self.assertEqual(self.rows(first)['state'],'SUPERSEDED')
        self.assertEqual(process(newer['job_id'])['status'],'active')

    def test_snapshot_retained_when_later_source_is_accepted(self):
        first=self.job('original');raw=self.rows(first)['snapshot']
        self.job('changed')
        self.assertEqual(self.rows(first)['snapshot'],raw)
        self.assertNotIn('changed',raw)

    def test_candidate_ids_metadata_and_vector_validation_are_complete(self):
        job=self.job();self.assertEqual(process(job['job_id'])['status'],'active')
        rows=self.rows(job);collection=self.chroma.collections[rows['candidates'][0]]
        self.assertGreater(collection.count(),1)
        self.assertTrue(all(r[1]['type']=='content' for r in collection.rows.values()))
        self.assertNotIn('CANARY',json.dumps(collection.get()))
        self.assertEqual(self.rows(job)['activations'],2)  # setup's original + new source
        self.assertEqual(process(job['job_id'])['status'],'ignored')
        self.assertEqual(self.rows(job)['activations'],2)

    def test_same_source_failed_reindex_preserves_readable_active_and_all_chunks(self):
        first=self.job();process(first['job_id'])
        old=self.rows(first);before=copy.deepcopy(self.chroma.collections[old['candidates'][0]].rows)
        second=self.job(spec='local-hash8-content-v2');self.fault(second,{'fault':'partial_failure'})
        self.assertEqual(process(second['job_id'])['status'],'failed')
        self.assertEqual(self.rows(second)['active'],old['active'])
        self.assertEqual(self.chroma.collections[old['candidates'][0]].rows,before)
        status=store.public_status(second['job_id'],self.principal())
        self.assertTrue(status['readable']);self.assertFalse(status['activeCurrent'])
        self.assertEqual(self.chat().status_code,200)

    def test_changed_source_old_active_is_explicitly_unavailable_without_new_message(self):
        self.job('new source')
        with RagSession() as db:before=db.query(ChatMessage).count()
        response=self.chat();self.assertEqual(response.status_code,409)
        self.assertEqual(response.json()['detail']['code'],'INDEX_NOT_READY')
        with RagSession() as db:self.assertEqual(db.query(ChatMessage).count(),before)

    def test_session_context_cannot_cross_source_revision_but_history_is_retained(self):
        response=self.chat();self.assertEqual(response.status_code,200)
        session=response.json()['session_id']
        job=self.job();process(job['job_id'])
        with RagSession() as db:before=db.query(ChatMessage).count()
        response=self.chat(session=session)
        self.assertEqual(response.status_code,409)
        self.assertEqual(response.json()['detail']['code'],'RAG_SOURCE_CHANGED')
        with RagSession() as db:self.assertEqual(db.query(ChatMessage).count(),before)
        self.assertEqual(self.chat().status_code,200)

    def test_actual_storage_transport_failure_never_falls_back_to_legacy_store(self):
        with patch('app.indexing.chroma.client',side_effect=ConnectionError),patch('app.local_providers.LocalVectorStore') as legacy:
            self.assertEqual(self.chat().status_code,503)
            legacy.assert_not_called()

    def test_bad_candidate_never_activates(self):
        for fault in ('missing_chunk','foreign_metadata','bad_dimension','bad_vector','bad_stored_vector',
                      'bad_document','extra_chunk','hash_mismatch','embedding_failure','storage_timeout'):
            with self.subTest(fault=fault):
                job=self.job(fault);before=self.rows(job)['active']
                self.fault(job,{'fault':fault})
                self.assertEqual(process(job['job_id'])['status'],'failed')
                self.assertEqual(self.rows(job)['active'],before)
                self.assertEqual(self.rows(job)['state'],'FAILED')

    def test_repeated_same_chunk_batch_is_idempotent_without_extra_embedding_call(self):
        source={'chapters':[{'type':'content','content':'[INDEX LOCAL] block '+str(i)+' '+('x'*100)} for i in range(3)]}
        job=store.accept_source(authz.OWNER,str(authz.DOC),authz.KEY,source)
        self.fault(job,{'fault':'duplicate_batch'})
        with patch.object(chroma,'upsert',wraps=chroma.upsert) as writes, patch.object(chroma,'vectors',wraps=chroma.vectors) as embeddings:
            self.assertEqual(process(job['job_id'])['status'],'active')
        self.assertEqual(writes.call_count,6)
        self.assertEqual(embeddings.call_count,3)
        with SessionLocal() as db:
            j=db.query(IndexJob).filter(IndexJob.job_id==job['job_id']).one()
            e=db.query(IndexExecution).filter(IndexExecution.job_pk==j.id).one()
            self.assertEqual(e.expected_chunks,3)
            self.assertEqual(e.actual_chunks,3)
            self.assertEqual(e.embedding_calls,3)  # 3 deterministic chunks / batch1

    def test_local_immutable_indexing_object_requires_exact_canonical_key(self):
        from app.local_providers import load_fixture_json,FIXTURE_BASE,LOCAL_OBJECT_STORAGE_DIR
        key='local/synthetic/indexing/01234567-89ab-4cde-8fab-0123456789ab.json'
        root=Path(LOCAL_OBJECT_STORAGE_DIR);root.mkdir(parents=True,exist_ok=True)
        path=root/(hashlib.sha256(key.encode()).hexdigest()+'.json')
        source=self.source();path.write_text(json.dumps(source))
        self.addCleanup(lambda:path.unlink(missing_ok=True))
        with patch('httpx.get',side_effect=AssertionError('Network attempt')):
            self.assertEqual(load_fixture_json(FIXTURE_BASE+key),source)
            for changed in (key.upper(),key.replace('01234567','not-a-uuid'),key.replace('/indexing/','/indexing/../'),
                            key.replace('/indexing/','/indexing%2f'),key+'?override=1',key+'#fragment'):
                with self.subTest(key=changed),self.assertRaises(ValueError):load_fixture_json(FIXTURE_BASE+changed)

    def test_activation_transaction_failure_rolls_back_pointer_and_success_state(self):
        job=self.job();before=self.rows(job)['active']
        self.fault(job,{'fault':'activation_rollback'})
        self.assertEqual(process(job['job_id'])['status'],'failed')
        self.assertEqual(self.rows(job)['active'],before)
        self.assertEqual(self.rows(job)['state'],'FAILED')

    def test_generation_claim_duplicate_and_late_writes_are_physically_separate(self):
        job=self.job();old=store.claim_execution(job['job_id'])
        self.assertIsNone(store.claim_execution(job['job_id']))
        old_candidate=chroma.create(old['candidate'],old)
        self.expire(job)
        status=store.public_status(job['job_id'],self.principal());self.assertEqual(status['state'],'FAILED')
        store.public_status(job['job_id'],self.principal(),1)
        self.assertEqual(process(job['job_id'])['status'],'active')
        active=self.rows(job);contents=copy.deepcopy(self.chroma.collections[active['candidates'][1]].rows)
        old_candidate.upsert(ids=['late'],documents=['late old generation'],metadatas=[{'type':'content'}],embeddings=[[0.1]*8])
        with self.assertRaises(ValueError):store.activate(old)
        store.fail_execution(old,'STALE_EXECUTION')
        self.assertNotEqual(active['candidates'][0],active['candidates'][1])
        self.assertEqual(self.rows(job)['active'],active['active'])
        self.assertEqual(self.chroma.collections[active['candidates'][1]].rows,contents)
        self.assertEqual(self.rows(job)['state'],'SUCCEEDED')

    def test_current_owner_loss_at_activation_is_revoked(self):
        job=self.job();before=self.rows(job)['active']
        def gate(ctx,name):
            if name=='before_activation':
                with SessionLocal.begin() as db:db.query(Material).filter(Material.id==authz.DOC).update({'teacher_id':authz.OTHER})
        with patch('app.indexing.hooks.gate',side_effect=gate):
            self.assertEqual(process(job['job_id'])['status'],'superseded')
        self.assertEqual(self.rows(job)['active'],before)
        self.assertEqual(self.rows(job)['state'],'REVOKED')

    def test_older_completion_cannot_replace_newer_request(self):
        job=self.job('old')
        def gate(ctx,name):
            if name=='before_activation' and ctx['job_id']==job['job_id']:
                newer=self.job('new')
                self.assertEqual(process(newer['job_id'])['status'],'active')
        with patch('app.indexing.hooks.gate',side_effect=gate):
            self.assertEqual(process(job['job_id'])['status'],'superseded')
        self.assertEqual(self.rows(job)['state'],'SUPERSEDED')

    def test_dispatch_is_outside_database_transaction_and_contains_only_job_uuid(self):
        job=self.job();calls=[]
        def send(name,**kwargs):
            self.assertEqual(name,'dodream.indexing.process');self.assertEqual(kwargs['kwargs'],{'job_id':job['job_id']})
            self.assertEqual(kwargs['queue'],'indexing-v3');calls.append(kwargs)
            with engine.connect() as db:self.assertIsNotNone(db.execute(IndexJob.__table__.select()).first())
        with patch('app.celery_config.celery_app.send_task',side_effect=send):
            self.assertEqual(dispatch_once(),1)
        self.assertEqual(len(calls),1);self.assertEqual(self.rows(job)['delivery'],1)

    def test_delivery_failure_is_bounded_and_never_loses_committed_job(self):
        job=self.job()
        with patch('app.celery_config.celery_app.send_task',side_effect=ConnectionError):
            for _ in range(5):
                with SessionLocal.begin() as db:
                    db.query(IndexJob).filter(IndexJob.job_id==job['job_id']).update({'next_delivery_at':store.now(db)-timedelta(seconds=1)})
                dispatch_once()
        self.assertEqual(self.rows(job)['delivery'],5);self.assertEqual(self.rows(job)['state'],'FAILED')
        self.assertFalse(store.public_status(job['job_id'],self.principal())['retryable'])

    def test_sent_but_unstarted_job_is_rediscovered_from_mysql(self):
        job=self.job()
        with patch('app.celery_config.celery_app.send_task') as broker:dispatch_once()
        with SessionLocal.begin() as db:
            db.query(IndexJob).filter(IndexJob.job_id==job['job_id']).update({'delivery_deadline':store.now(db)-timedelta(seconds=1)})
        with patch('app.celery_config.celery_app.send_task') as broker:
            dispatch_once();broker.assert_called_once()
        self.assertEqual(self.rows(job)['delivery'],2)

    def test_empty_source_fails_without_replacing_previous_index(self):
        job=self.job()
        # A corrupt/legacy persisted empty snapshot is still rejected by the
        # worker, independently of the stricter new-request admission contract.
        raw='{"blocks":[]}'
        with SessionLocal.begin() as db:
            j=db.query(IndexJob).filter(IndexJob.job_id==job['job_id']).one()
            j.snapshot_json,j.snapshot_bytes=raw,len(raw.encode())
            j.source_hash=hashlib.sha256(raw.encode()).hexdigest()
            db.get(IndexResource,j.resource_pk).current_source_hash=j.source_hash
        before=self.rows(job)['active']
        outcome=process(job['job_id']);self.assertEqual(outcome['failure_code'],'EMPTY_SOURCE')
        self.assertEqual(self.rows(job)['active'],before)

    def test_empty_source_is_422_before_any_ledger_mutation(self):
        with SessionLocal() as db:before=db.query(IndexJob).count()
        for source in ({'chapters':[]},{'chapters':[{'type':'quiz','content':'ANSWER_ONLY'}]},
                       {'chapters':[{'type':'content','content':'새 챕터의 내용을 입력하세요'}]}):
            with self.subTest(source=source),self.assertRaises(HTTPException) as caught:
                store.accept_source(authz.OWNER,str(authz.DOC),authz.KEY,source)
            self.assertEqual(caught.exception.status_code,422)
        with SessionLocal() as db:self.assertEqual(db.query(IndexJob).count(),before)

    def test_execution_must_belong_to_claimed_job_even_with_other_valid_token(self):
        first=self.job('first');old=store.claim_execution(first['job_id'])
        newer=self.job('newer');current=store.claim_execution(newer['job_id'])
        crossed={**old,'execution_id':current['execution_id'],'token':current['token']}
        with self.assertRaisesRegex(ValueError,'STALE_EXECUTION'):store.execution_progress(crossed)
        self.assertEqual(self.rows(newer)['state'],'PROCESSING')

    def test_locked_resource_refreshes_preloaded_identity_after_other_connection_commit(self):
        first=self.job('first')
        with SessionLocal() as db:
            job=db.query(IndexJob).filter(IndexJob.job_id==first['job_id']).one()
            cached=db.get(IndexResource,job.resource_pk)
            before=(cached.latest_job_id,cached.source_revision,cached.current_source_hash)
            newer=self.job('newer')  # separate Session/connection commits a newer source
            self.assertEqual((cached.latest_job_id,cached.source_revision,cached.current_source_hash),before)
            locked=store._resource(db,cached.id)
            self.assertIs(locked,cached)
            self.assertNotEqual(locked.latest_job_id,before[0])
            self.assertEqual(locked.source_revision,before[1]+1)
            self.assertEqual(locked.current_source_hash,self.rows(newer)['hash'])
            self.assertFalse(store._is_latest(locked,job))

    def test_current_owner_locked_read_refreshes_preloaded_material(self):
        job=self.job()
        with SessionLocal() as db:
            row=db.query(IndexJob).filter(IndexJob.job_id==job['job_id']).one()
            resource=db.get(IndexResource,row.resource_pk)
            cached=db.get(Material,authz.DOC)
            self.assertEqual(cached.teacher_id,authz.OWNER)
            with SessionLocal.begin() as other:
                other.query(Material).filter(Material.id==authz.DOC).update({'teacher_id':authz.OTHER})
            with self.assertRaises(HTTPException) as caught:store.current_owner(db,resource)
            self.assertEqual(caught.exception.status_code,404)
            self.assertEqual(cached.teacher_id,authz.OTHER)

    def test_chroma_transport_is_pinned_and_finite_before_client_initial_probes(self):
        import chromadb
        import httpx
        import uuid
        from chromadb.api.configuration import CollectionConfigurationInternal
        from app.indexing.chroma import _http_client
        _http_client.cache_clear()
        # Do not mock the client factory: exercise the actual SDK ServerAPI and
        # Collection objects so a silently replaced transport cannot pass again.
        adapter=_http_client();self.addCleanup(adapter.close);self.addCleanup(_http_client.cache_clear)
        captured=[]
        model={'id':str(uuid.uuid4()),'name':'idx_transport_contract',
            'configuration_json':CollectionConfigurationInternal().to_json(),'metadata':{'type':'content'},
            'dimension':8,'tenant':'default_tenant','database':'default_database','version':0,'log_position':0}
        def respond(method,url,**kwargs):
            captured.append(adapter._server._session.timeout)
            if url.endswith('/heartbeat'):data={'nanosecond heartbeat':1}
            elif url.endswith('/version'):data='0.6.3'
            elif url.endswith('/collections') and method=='get':data=[model]
            else:data=model
            return httpx.Response(200,json=data,request=httpx.Request(method,url))
        with patch.object(adapter._server._session,'request',side_effect=respond):
            self.assertEqual(adapter.heartbeat(),1);self.assertEqual(adapter.get_version(),'0.6.3')
            self.assertEqual(adapter.list_collections(),['idx_transport_contract'])
            created=adapter.create_collection(name=model['name'],metadata=model['metadata'],embedding_function=None)
            fetched=adapter.get_collection(model['name'],embedding_function=None)
        self.assertIs(created._client,adapter._server);self.assertIs(fetched._client,adapter._server)
        self.assertIsNone(created._embedding_function);self.assertIsNone(fetched._embedding_function)
        with patch.object(adapter._server._session,'request',side_effect=httpx.ReadTimeout('synthetic query stall')) as query:
            with self.assertRaises(httpx.ReadTimeout):
                fetched.query(query_embeddings=[[0.1]*8],n_results=1)
        self.assertEqual(query.call_count,1)
        self.assertEqual(chromadb.__version__,'0.6.3')
        self.assertEqual(len(captured),5)
        for timeout in captured:
            self.assertEqual(timeout.connect,2);self.assertEqual(timeout.read,5)
            self.assertEqual(timeout.write,5);self.assertEqual(timeout.pool,5)

    def test_sdk_read_timeout_has_one_attempt_and_becomes_storage_503(self):
        import httpx
        from app.indexing.chroma import _http_client
        _http_client.cache_clear()
        adapter=_http_client();self.addCleanup(adapter.close);self.addCleanup(_http_client.cache_clear)
        def timeout(method,url,**kwargs):
            self.assertEqual(adapter._server._session.timeout.read,5)
            raise httpx.ReadTimeout('synthetic stalled Chroma response')
        with patch.object(chroma,'client',return_value=adapter),patch.object(adapter._server._session,'request',side_effect=timeout) as request:
            with self.assertRaises(HTTPException) as caught:chroma.retrieve({'candidate':'idx_transport_contract','spec':'local-hash8-content-v1'},'query')
        self.assertEqual(caught.exception.status_code,503)
        self.assertEqual(caught.exception.detail,{'code':'INDEX_STORAGE_UNAVAILABLE'})
        self.assertEqual(request.call_count,1)
