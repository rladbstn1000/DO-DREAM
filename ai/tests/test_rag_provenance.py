"""Real JWT/SQL policy with the existing unit Chroma adapter, no external model."""
import copy
import hashlib
import json
import unittest
from unittest.mock import patch
from sqlalchemy import event
from sqlalchemy.exc import OperationalError
from langchain_core.documents import Document
import runtime_fixture
import test_object_authorization as authz
from app.common.db_session import SessionLocal
from app.common.models import MaterialShare,Material,User,RoleEnum
from app.rag.database import SessionLocal as RagSession
from app.rag.models import ChatMessage,ChatMessageSources
from app.rag.provenance import runtime_mode,source_references
from app.rag.service import VersionedRagChain
from app.indexing import chroma,store
from app.indexing.worker import process
from indexing_fixture import seed_index


class RagProvenanceTests(unittest.TestCase):
    headers=authz.ObjectAuthorizationTests.headers
    chat=authz.ObjectAuthorizationTests.chat

    @classmethod
    def setUpClass(cls):
        authz.ObjectAuthorizationTests.setUpClass()
        cls.client=authz.ObjectAuthorizationTests.client

    def setUp(self):
        authz.ObjectAuthorizationTests.setUp(self)

    def source_url(self,response,index=0,message=None):
        return (f"/rag/chat/sessions/{response['session_id']}/messages/"
            f"{response['message_id'] if message is None else message}/sources/{index}")

    def source(self,response,user=authz.STUDENT,subject=authz.STUDENT,index=0,message=None):
        return self.client.get(self.source_url(response,index,message)+f'?student_id={subject}',headers=self.headers(user))

    def history(self,response,user=authz.STUDENT,subject=authz.STUDENT):
        return self.client.get(f"/rag/chat/sessions/{response['session_id']}/messages?student_id={subject}",headers=self.headers(user))

    def test_response_references_exact_local_answer_input_not_unused_retrieval(self):
        seed_index(str(authz.DOC),[Document(page_content='A'*420,metadata={'type':'content'}),
            Document(page_content='Unused retrieved text',metadata={'type':'content'})])
        with patch.object(chroma,'retrieve',wraps=chroma.retrieve) as retrieval:
            response=self.chat()
        self.assertEqual(response.status_code,200)
        data=response.json();self.assertEqual(len(data['sources']),1)
        source=data['sources'][0]
        self.assertEqual(set(source),{'document_id','source_revision','source_hash','chunk_position',
            'content_hash','material_title','excerpt'})
        self.assertEqual(source['excerpt'],'A'*300)
        self.assertEqual(source['content_hash'],hashlib.sha256(('A'*420).encode()).hexdigest())
        self.assertEqual(source['chunk_position'],0)
        self.assertEqual(source['material_title'],'Synthetic material 0')
        self.assertTrue(data['answer'].endswith(source['excerpt']))
        self.assertNotIn('Unused retrieved text',response.text)
        self.assertNotIn('candidate',response.text);self.assertNotIn('idx_',response.text)
        pointer=retrieval.call_args.args[0]
        self.assertEqual((source['document_id'],source['source_revision'],source['source_hash']),
            (str(pointer['resource_id']),pointer['source_revision'],pointer['source_hash']))
        self.assertEqual(data['source_revision'],source['source_revision'])
        self.assertEqual(data['source_hash'],source['source_hash'])

    def test_history_recovers_committed_answer_and_sources_without_resending_post(self):
        data=self.chat().json()
        with RagSession() as db:before=db.query(ChatMessage).count()
        history=self.history(data);self.assertEqual(history.status_code,200)
        answer=next(m for m in history.json()['messages'] if m['id']==data['message_id'])
        self.assertEqual(answer['sources'],data['sources'])
        self.assertEqual(answer['mode'],data['mode'])
        self.assertEqual(answer['content'],data['answer'])
        self.assertEqual(history.json()['source_hash'],data['source_hash'])
        self.assertEqual(history.json()['document_id'],str(authz.DOC))
        with RagSession() as db:self.assertEqual(db.query(ChatMessage).count(),before)

    def test_source_lookup_rechecks_actual_current_authorization(self):
        data=self.chat().json()
        self.assertEqual(self.source(data).json(),data['sources'][0])
        self.assertEqual(self.source(data,user=authz.OWNER).status_code,200)
        self.assertEqual(self.source(data,user=authz.OTHER).status_code,404)
        self.assertEqual(self.source(data,user=authz.SECOND).status_code,404)
        self.assertEqual(self.source(data,user=authz.SECOND,subject=authz.SECOND).status_code,404)
        self.assertEqual(self.client.get(self.source_url(data)+f'?student_id={authz.STUDENT}').status_code,401)
        with SessionLocal.begin() as db:db.query(MaterialShare).filter(MaterialShare.id==6101).delete()
        with patch.object(chroma,'retrieve') as search:
            self.assertEqual(self.source(data).status_code,404)
            self.assertEqual(self.history(data).status_code,404)
            self.assertEqual(self.source(data,user=authz.OWNER).status_code,404)
            search.assert_not_called()

    def test_source_lookup_binds_session_message_and_reference_index(self):
        first=self.chat().json();second=self.chat().json()
        self.assertEqual(self.source(first,message=second['message_id']).status_code,404)
        self.assertEqual(self.source(first,index=-1).status_code,404)
        self.assertEqual(self.source(first,index=1).status_code,404)
        with RagSession() as db:
            user_message=db.query(ChatMessage).filter(ChatMessage.session_id==first['session_id'],ChatMessage.role=='user').one()
            user_id=user_message.id
        self.assertEqual(self.source(first,message=user_id).status_code,404)

    def test_changed_source_requires_new_session_and_preserves_old_history(self):
        old=self.chat().json()
        seed_index(str(authz.DOC),[Document(page_content='Changed safe learning text',metadata={'type':'content'})])
        denied=self.source(old)
        self.assertEqual(denied.status_code,409)
        self.assertEqual(denied.json()['detail']['code'],'RAG_SOURCE_CHANGED')
        self.assertEqual(self.chat(session=old['session_id']).status_code,409)
        self.assertEqual(self.history(old).json()['messages'][-1]['sources'],old['sources'])
        new=self.chat().json()
        self.assertNotEqual(old['source_revision'],new['source_revision'])
        self.assertEqual(self.source(new).status_code,200)

    def test_legacy_message_has_no_invented_sources_or_mode(self):
        data=self.chat().json()
        with RagSession.begin() as db:
            db.query(ChatMessageSources).filter(ChatMessageSources.message_id==data['message_id']).delete()
        message=self.history(data).json()['messages'][-1]
        self.assertEqual(message['sources'],[]);self.assertIsNone(message['mode'])
        self.assertEqual(self.source(data).status_code,404)

    def test_invalid_provider_context_never_saves_a_successful_answer(self):
        original=chroma.retrieve
        for field,value in [('source_hash','0'*64),('resource_id','999'),('type','quiz'),('position',True),('content_hash','0'*64)]:
            with self.subTest(field=field):
                def altered(pointer,query,limit=5):
                    docs=copy.deepcopy(original(pointer,query,limit));docs[0].metadata[field]=value;return docs
                with RagSession() as db:
                    before=db.query(ChatMessage).filter(ChatMessage.role=='ai').count()
                    source_count=db.query(ChatMessageSources).count()
                with patch.object(chroma,'retrieve',side_effect=altered):response=self.chat()
                self.assertEqual(response.status_code,503)
                with RagSession() as db:
                    self.assertEqual(db.query(ChatMessage).filter(ChatMessage.role=='ai').count(),before)
                    self.assertEqual(db.query(ChatMessageSources).count(),source_count)

    def test_provider_failure_never_becomes_a_stub_success(self):
        with patch('app.rag.router.get_rag_chain',side_effect=RuntimeError('synthetic provider failure')):
            response=self.chat()
        self.assertEqual(response.status_code,503)
        self.assertNotIn('sources',response.json());self.assertNotIn('synthetic provider failure',response.text)

    def test_provenance_and_answer_commit_together(self):
        def fail(*args):raise RuntimeError('synthetic provenance insertion failure')
        with RagSession() as db:
            before=db.query(ChatMessage).filter(ChatMessage.role=='ai').count()
            references=db.query(ChatMessageSources).count()
        event.listen(ChatMessageSources,'before_insert',fail)
        try:response=self.chat()
        finally:event.remove(ChatMessageSources,'before_insert',fail)
        self.assertEqual(response.status_code,503)
        with RagSession() as db:
            self.assertEqual(db.query(ChatMessage).filter(ChatMessage.role=='ai').count(),before)
            self.assertEqual(db.query(ChatMessageSources).count(),references)

    def test_question_size_rejected_before_message_write(self):
        with RagSession() as db:before=db.query(ChatMessage).count()
        for question in ('','a'*4001):
            response=self.client.post('/rag/chat',headers=self.headers(),json={'document_id':str(authz.DOC),'question':question})
            self.assertEqual(response.status_code,422)
        with RagSession() as db:self.assertEqual(db.query(ChatMessage).count(),before)

    def test_server_mode_requires_auth_and_never_claims_verified_real_ai(self):
        self.assertEqual(self.client.get('/rag/mode').status_code,401)
        mode=self.client.get('/rag/mode',headers=self.headers())
        self.assertEqual(mode.status_code,200)
        self.assertEqual(mode.json(),{'environment':'test','answer_provider':'local_stub',
            'embedding_provider':'local_hash8','grading_provider':'local_stub'})
        with patch('app.rag.provenance.LOCAL_EXTERNAL_STUBS',False):
            value=runtime_mode().model_dump()
            self.assertEqual(set(value.values()),{'test','configured_unverified'})

    def during_answer(self,mutation):
        original=VersionedRagChain.ainvoke
        async def waiting(chain,request):
            result=await original(chain,request)
            mutation()
            return result
        with patch.object(VersionedRagChain,'ainvoke',new=waiting),patch.object(chroma,'retrieve',wraps=chroma.retrieve) as retrieval:
            response=self.chat()
        self.assertEqual(retrieval.call_count,1)
        return response

    def answer_counts(self):
        with RagSession() as db:
            return (db.query(ChatMessage).filter(ChatMessage.role=='user').count(),
                db.query(ChatMessage).filter(ChatMessage.role=='ai').count(),db.query(ChatMessageSources).count())

    def assert_answer_not_saved(self,before):
        after=self.answer_counts()
        self.assertEqual(after,(before[0]+1,before[1],before[2]))

    def test_share_revoked_during_answer_denies_late_response_but_keeps_question(self):
        before=self.answer_counts()
        def revoke():
            with SessionLocal.begin() as db:db.query(MaterialShare).filter(MaterialShare.id==6101).delete()
        response=self.during_answer(revoke)
        self.assertEqual(response.status_code,404)
        self.assert_answer_not_saved(before)

    def test_material_deleted_during_answer_denies_late_response(self):
        from datetime import datetime
        before=self.answer_counts()
        def remove():
            with SessionLocal.begin() as db:db.get(Material,authz.DOC).deleted_at=datetime.utcnow()
        response=self.during_answer(remove)
        self.assertEqual(response.status_code,404)
        self.assert_answer_not_saved(before)

    def test_current_user_role_is_reread_after_provider_wait(self):
        before=self.answer_counts()
        def change_role():
            with SessionLocal.begin() as db:db.get(User,authz.STUDENT).role=RoleEnum.TEACHER
        response=self.during_answer(change_role)
        self.assertEqual(response.status_code,404)
        self.assert_answer_not_saved(before)

    def test_source_changed_while_answer_waits_has_no_mixed_version_success(self):
        for activate in (False,True):
            with self.subTest(activate=activate):
                # Establish a current, readable source before each request.
                seed_index(str(authz.DOC),[Document(page_content='Starting source '+str(activate),metadata={'type':'content'})])
                before=self.answer_counts()
                def revise():
                    job=store.accept_source(authz.OWNER,str(authz.DOC),authz.KEY,
                        {'chapters':[{'type':'content','content':'New revision '+str(activate)}]})
                    if activate:process(job['job_id'])
                response=self.during_answer(revise)
                self.assertEqual(response.status_code,409)
                self.assertEqual(response.json()['detail']['code'],'RAG_SOURCE_CHANGED')
                self.assert_answer_not_saved(before)

    def test_same_source_new_spec_during_answer_keeps_original_input_reference(self):
        def reindex():
            job=store.accept_source(authz.OWNER,str(authz.DOC),authz.KEY,
                {'chapters':[{'type':'content','content':'Safe lesson content'}]},'local-hash8-content-v2')
            self.assertEqual(process(job['job_id'])['status'],'active')
        response=self.during_answer(reindex)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['sources'][0]['excerpt'],'Safe lesson content')
        self.assertEqual(self.source(response.json()).status_code,200)

    def test_final_authority_database_failure_fails_closed_without_raw_exception(self):
        before=self.answer_counts()
        with patch('app.rag.router.get_user_from_db',side_effect=OperationalError('PRIVATE_SQL',{},Exception('PRIVATE_FAILURE'))):
            response=self.chat()
        self.assertEqual(response.status_code,503)
        self.assertNotIn('PRIVATE_',response.text)
        self.assert_answer_not_saved(before)


if __name__=='__main__':unittest.main()
