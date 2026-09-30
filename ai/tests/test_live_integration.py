"""Offline provider-boundary contracts. No paid client, key or network is used."""
import asyncio
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import AsyncMock, Mock, patch
from fastapi import HTTPException
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.documents import Document
import runtime_fixture
import test_object_authorization as authz
from app.common.db_session import SessionLocal
from app.indexing import chroma, store
from app.indexing.models import IndexJob, IndexResource, IndexExecution
from app.indexing.source import LIVE_SPEC, INDEX_SPEC, normalize_source, make_chunks, specification
from app.indexing.worker import process
from app.rag.service import VersionedRagChain
from app.rag.quiz_service import _grade_batch, GradingResponseError


def pointer():
    return {'candidate':'test-live-candidate','source_revision':1,'source_hash':'a'*64,
        'spec':LIVE_SPEC,'job_id':'job','resource_kind':'MATERIAL','resource_id':1,'generation':1,'user_id':2}


def documents(selected=None):
    selected=selected or pointer()
    chunks=make_chunks({'blocks':[{'type':'content','text':text} for text in
        ['첫 번째 학습 근거','두 번째 별도 학습 근거','세 번째 학습 근거']]},
        selected['resource_kind'],selected['resource_id'],selected['source_revision'],selected['source_hash'],selected['spec'])
    return [Document(page_content=chunk['document'],metadata=chunk['metadata']) for chunk in chunks]


class LiveIndexIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        authz.ObjectAuthorizationTests.setUpClass()
        cls.client=authz.ObjectAuthorizationTests.client

    def setUp(self):
        authz.ObjectAuthorizationTests.setUp(self)

    def job(self,spec=LIVE_SPEC):
        return store.accept_source(authz.OWNER,str(authz.DOC),authz.KEY,
            {'chapters':[{'type':'content','content':'Approved authored live source'},
                {'type':'quiz','content':'PRIVATE_QUIZ','qa':[{'answer':'PRIVATE_GOLD'}]}]},spec)

    def state(self,job):
        with SessionLocal() as db:
            row=db.query(IndexJob).filter(IndexJob.job_id==job['job_id']).one()
            resource=db.get(IndexResource,row.resource_pk)
            return (row.state,row.execution_generation,row.delivery_state,row.delivery_attempts,
                resource.active_execution_id,db.query(IndexExecution).filter(IndexExecution.job_pk==row.id).count())

    def test_local_delivery_and_worker_cannot_consume_live_job(self):
        job=self.job();before=self.state(job)
        self.assertNotIn(job['job_id'],[row['job_id'] for row in store.claim_deliveries()])
        self.assertEqual(process(job['job_id'])['status'],'ignored')
        self.assertEqual(self.state(job),before)

    def test_live_common_worker_and_manual_worker_reject_old_local_without_mutation(self):
        job=self.job(INDEX_SPEC);before=self.state(job)
        with patch('app.indexing.store.AI_MODE','LIVE_OPENAI'):
            self.assertIsNone(store.claim_execution(job['job_id']))
            self.assertIsNone(store.claim_execution(job['job_id'],manual_live=True))
            with self.assertRaises(RuntimeError):store.claim_deliveries()
        self.assertEqual(self.state(job),before)

    def test_denied_live_scope_precedes_claim_and_provider_construction(self):
        job=self.job();before=self.state(job)
        with patch('app.indexing.store.AI_MODE','LIVE_OPENAI'), \
                patch('app.indexing.runtime.authorize_pointer',side_effect=RuntimeError('scope denied')), \
                patch('app.indexing.runtime.provider') as provider:
            with self.assertRaises(RuntimeError):store.claim_execution(job['job_id'],manual_live=True)
            provider.assert_not_called()
        self.assertEqual(self.state(job),before)

    def test_approved_new_candidate_uses_1536_and_preserves_existing_hash8_collection(self):
        existing=copy.deepcopy({name:collection.rows for name,collection in self.chroma.collections.items()})
        job=self.job()
        adapter=Mock();adapter.embed.side_effect=lambda texts,scope:[[1.0]+[0.0]*1535 for _ in texts]
        with patch('app.indexing.store.AI_MODE','LIVE_OPENAI'),patch('app.indexing.chroma.AI_MODE','LIVE_OPENAI'), \
                patch('app.indexing.runtime.authorize_pointer') as gate,patch('app.indexing.runtime.provider',return_value=adapter):
            result=process(job['job_id'],manual_live=True)
        self.assertEqual(result['status'],'active')
        self.assertEqual(adapter.embed.call_count,1)
        self.assertEqual(gate.call_args_list[0].args[1:],('index','worker'))
        self.assertEqual(adapter.embed.call_args.args[1].spec,LIVE_SPEC)
        for name,rows in existing.items():self.assertEqual(self.chroma.collections[name].rows,rows)
        added=[collection for name,collection in self.chroma.collections.items() if name not in existing]
        self.assertEqual(len(added),1)
        self.assertTrue(all(len(row[2])==1536 for row in added[0].rows.values()))
        self.assertNotIn('PRIVATE_',json.dumps(added[0].get()))

    def test_wrong_dimension_never_activates_or_replaces_existing_pointer(self):
        job=self.job();before=self.state(job)
        adapter=Mock();adapter.embed.return_value=[[1.0]*8]
        with patch('app.indexing.store.AI_MODE','LIVE_OPENAI'),patch('app.indexing.chroma.AI_MODE','LIVE_OPENAI'), \
                patch('app.indexing.runtime.authorize_pointer'),patch('app.indexing.runtime.provider',return_value=adapter):
            result=process(job['job_id'],manual_live=True)
        self.assertEqual(result['status'],'failed')
        self.assertEqual(result['failure_code'],'INVALID_VECTOR_DIMENSION')
        self.assertEqual(self.state(job)[4],before[4])

    def test_query_collection_spec_mismatch_rejected_before_embedding(self):
        selected=pointer();collection=Mock(metadata={'index_spec':INDEX_SPEC})
        with patch('app.indexing.runtime.authorize_pointer'),patch.object(chroma,'fetch',return_value=collection), \
                patch.object(chroma,'vectors') as embed:
            with self.assertRaises(HTTPException):chroma.retrieve(selected,'question',3)
            embed.assert_not_called();collection.query.assert_not_called()

    def test_spec_identifies_space_and_normalization_not_only_dimension(self):
        self.assertEqual(specification(LIVE_SPEC)['dimensions'],1536)
        self.assertEqual(specification(LIVE_SPEC)['normalization'],'l2')
        self.assertEqual(specification(INDEX_SPEC)['dimensions'],8)
        with self.assertRaises(ValueError):specification('other-model-1536')
        with self.assertRaises(ValueError):chroma.float_vector([1.0]*1536,LIVE_SPEC)


class LiveRagContractTests(unittest.TestCase):
    def invoke(self,*,value=None,history=None,variant='A',docs=None):
        docs=docs if docs is not None else documents()
        citations=['chunk-'+str(doc.metadata['position'])+'-'+doc.metadata['content_hash'][:16] for doc in docs]
        value=value if value is not None else {'answer':'학습 자료에 따른 답변','source_ids':citations[:1],'abstained':False}
        adapter=Mock();adapter.structured=AsyncMock(side_effect=
            [{'question':'재작성한 검색 질문'},value] if variant=='B' and history else [value])
        with patch('app.rag.service.AI_MODE','LIVE_OPENAI'),patch('app.rag.service.RAG_RETRIEVAL_VARIANT',variant), \
                patch('app.indexing.runtime.authorize_pointer'),patch('app.indexing.runtime.provider',return_value=adapter), \
                patch('app.indexing.chroma.retrieve',return_value=docs) as retrieval:
            result=asyncio.run(VersionedRagChain(pointer()).ainvoke({'input':'현재 질문','chat_history':history or []}))
        return result,adapter,retrieval

    def test_all_three_actual_context_chunks_returned_not_only_cited_one(self):
        result,adapter,retrieval=self.invoke()
        self.assertEqual(len(result['context']),3);self.assertEqual(len(result['cited_source_ids']),1)
        payload=json.loads(adapter.structured.call_args.kwargs['messages'][1]['content'])
        self.assertEqual([row['text'] for row in payload['context']],[doc.page_content for doc in result['context']])
        self.assertEqual(retrieval.call_args.args[2],3)
        self.assertEqual(adapter.structured.call_args.kwargs['scope'].purpose,'answer')
        self.assertEqual(set(result['stage_latency_ms']),{'rewrite','retrieval_including_query_embedding','answer','total'})

    def test_unknown_duplicate_or_missing_source_id_is_failure(self):
        for ids in [['invented'],[],[True]]:
            with self.subTest(ids=ids),self.assertRaises(ValueError):
                self.invoke(value={'answer':'answer','source_ids':ids,'abstained':False})
        identity='chunk-0-'+documents()[0].metadata['content_hash'][:16]
        with self.assertRaises(ValueError):self.invoke(value={'answer':'answer','source_ids':[identity,identity],'abstained':False})

    def test_abstention_still_tracks_every_context_and_no_invented_citation(self):
        result,_,_=self.invoke(value={'answer':'자료에서 확인할 수 없습니다.','source_ids':[],'abstained':True})
        self.assertTrue(result['abstained']);self.assertEqual(len(result['context']),3)

    def test_metadata_or_content_tamper_is_rejected_before_answer_request(self):
        for field,value in [('type','quiz'),('source_hash','b'*64),('content_hash','c'*64)]:
            docs=documents();docs[0].metadata[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):self.invoke(docs=docs)

    def test_only_history_rewrite_changes_between_A_and_B(self):
        history=[HumanMessage(content='이전 질문'),AIMessage(content='이전 답변')]
        a,provider_a,retrieval_a=self.invoke(history=history,variant='A')
        b,provider_b,retrieval_b=self.invoke(history=history,variant='B')
        self.assertEqual(provider_a.structured.await_count,1);self.assertEqual(provider_b.structured.await_count,2)
        self.assertEqual(retrieval_a.call_args.args[1],'현재 질문')
        self.assertEqual(retrieval_b.call_args.args[1],'재작성한 검색 질문')
        self.assertEqual(provider_a.structured.call_args.kwargs,provider_b.structured.call_args.kwargs)
        _,provider_no_history,_=self.invoke(variant='B')
        self.assertEqual(provider_no_history.structured.await_count,1)

    def test_oversize_history_rejected_before_provider_or_search(self):
        with self.assertRaises(ValueError):self.invoke(history=[HumanMessage(content='x'*4001)])

    def test_provider_failure_never_falls_back_to_local_text(self):
        with patch('app.rag.service.AI_MODE','LIVE_OPENAI'),patch('app.indexing.runtime.authorize_pointer'), \
                patch('app.indexing.runtime.provider',side_effect=TimeoutError):
            with self.assertRaises(TimeoutError):
                asyncio.run(VersionedRagChain(pointer()).ainvoke({'input':'질문','chat_history':[]}))


class LiveGradingContractTests(unittest.TestCase):
    def grade(self,result):
        adapter=Mock();adapter.structured=AsyncMock(return_value=result)
        with patch('app.indexing.runtime.authorize_pointer'),patch('app.indexing.runtime.provider',return_value=adapter):
            actual=asyncio.run(_grade_batch([{'id':7,'content':'문제','correct_answer':'서버 정답'}],
                [{'question_id':7,'student_answer':'학생 답안'}],{'pointer':pointer()}))
        return actual,adapter

    def test_only_snapshot_fields_sent_and_false_is_real_result(self):
        actual,adapter=self.grade({'results':[{'question_id':7,'is_correct':False,'feedback':'핵심 내용이 빠졌습니다.'}]})
        self.assertFalse(actual[0]['is_correct']);self.assertEqual(actual[0]['student_answer'],'학생 답안')
        call=adapter.structured.call_args.kwargs
        self.assertEqual(call['schema_name'],'snapshot_grading');self.assertEqual(call['scope'].purpose,'grading')
        payload=json.loads(call['messages'][1]['content'])
        self.assertEqual(payload,{'snapshots':[{'question_id':7,'question':'문제','server_answer':'서버 정답','student_answer':'학생 답안'}]})

    def test_wrong_set_type_feedback_or_partial_result_never_becomes_success(self):
        cases=[{'results':[]},{'results':[{'question_id':8,'is_correct':True,'feedback':'x'}]},
            {'results':[{'question_id':7,'is_correct':'false','feedback':'x'}]},
            {'results':[{'question_id':7,'is_correct':False,'feedback':'x'*2001}]},
            {'results':[{'question_id':7,'is_correct':False,'feedback':'x','correct_answer':'forged'}]}]
        for result in cases:
            with self.subTest(result=str(result)[:80]),self.assertRaises(GradingResponseError):self.grade(result)


class ImportSafetyTests(unittest.TestCase):
    def test_key_presence_does_not_select_live_mode(self):
        environment=dict(os.environ,DODREAM_AI_MODE='LOCAL_FAKE',OPENAI_API_KEY='synthetic-key-never-used')
        environment['PYTHONPATH']=str(Path(__file__).parents[1])
        result=subprocess.run([sys.executable,'-c','from app.config import AI_MODE; print(AI_MODE)'],
            env=environment,capture_output=True,text=True,timeout=10,check=True)
        self.assertEqual(result.stdout.strip(),'LOCAL_FAKE')

    def test_live_mode_cannot_enable_legacy_ocr_or_external_files(self):
        environment=dict(os.environ,DODREAM_AI_MODE='LIVE_OPENAI',LOCAL_EXTERNAL_STUBS='false')
        environment['PYTHONPATH']=str(Path(__file__).parents[1])
        result=subprocess.run([sys.executable,'-c','import app.config'],env=environment,
            capture_output=True,text=True,timeout=10)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('isolated local file/OCR providers',result.stderr)

    def test_legacy_import_time_clients_and_dotenv_discovery_are_removed(self):
        root=Path(__file__).parents[1]/'app'
        for name in ['rag/service.py','rag/quiz_service.py','config.py']:
            content=(root/name).read_text()
            for forbidden in ['load_dotenv(', 'ChatOpenAI(', 'OpenAIEmbeddings(', 'HuggingFaceCrossEncoder(', 'trust_remote_code']:
                self.assertNotIn(forbidden,content)

    def test_live_celery_startup_exits_instead_of_consuming_old_queue(self):
        from app.celery_config import prohibit_live_queue_consumer
        with patch('app.celery_config.AI_MODE','LIVE_OPENAI'),self.assertRaises(SystemExit):
            prohibit_live_queue_consumer()


if __name__=='__main__':unittest.main()
