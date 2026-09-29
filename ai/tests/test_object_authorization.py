"""Real JWT + SQL relations; mocks measure only forbidden provider/queue boundaries."""
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from sqlalchemy import event
from sqlalchemy.exc import OperationalError
from fastapi.testclient import TestClient
from jose import jwt
from runtime_fixture import access_claims
from app.config import SECRET_KEY_BYTES, LOCAL_OBJECT_STORAGE_DIR
from app.main import app
from app.common.db_session import Base, engine, SessionLocal
from app.common.models import (User, RoleEnum, TeacherProfile, StudentProfile, ClassroomTeacher,
    UploadedFile, Material, MaterialShare, Quiz)
from app.rag.database import SessionLocal as RagSession
from app.rag.models import ChatSession, ChatMessage, EmbeddingTask
from app.rag.service import extract_data_from_json, create_and_store_embeddings, _get_collection_name
from app.local_providers import LocalVectorStore, LocalEmbeddings, load_fixture_json, FIXTURE_BASE
from langchain_core.documents import Document

OWNER, OTHER, OUTSIDE = 3101, 3102, 3103
STUDENT, PEER, OTHER_CLASS, SECOND = 3201, 3202, 3203, 3204
DOC, DOC_TWO, PRIVATE, DRAFT, OTHER_DOC = 5101, 5102, 5103, 5104, 5105
KEY = 'local/synthetic/lesson.json'


class ObjectAuthorizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(engine)
        cls.client = TestClient(app)

    def setUp(self):
        with RagSession() as db:
            ids = [r.id for r in db.query(ChatSession).filter(ChatSession.user_id.in_([OWNER, OTHER, OUTSIDE, STUDENT, PEER, OTHER_CLASS, SECOND])).all()]
            db.query(ChatMessage).filter(ChatMessage.session_id.in_(ids)).delete(synchronize_session=False)
            db.query(ChatSession).filter(ChatSession.id.in_(ids)).delete(synchronize_session=False)
            db.query(EmbeddingTask).filter(EmbeddingTask.user_id.in_([OWNER, OTHER, OUTSIDE, STUDENT])).delete(synchronize_session=False)
            db.commit()
        with SessionLocal() as db:
            owned = [(Quiz, [7101,7102]), (MaterialShare, list(range(6101,6106))),
                     (Material, list(range(5101,5106))), (UploadedFile, list(range(4101,4106))),
                     (ClassroomTeacher, [51,52,53]), (StudentProfile, [501,502,503,504]),
                     (TeacherProfile, [41,42,43]), (User, [OWNER,OTHER,OUTSIDE,STUDENT,PEER,OTHER_CLASS,SECOND])]
            for model, ids in owned:
                db.query(model).filter(model.id.in_(ids)).delete(synchronize_session=False)
            db.add_all([
                *(User(id=value, name='Synthetic teacher', role=RoleEnum.TEACHER) for value in (OWNER, OTHER, OUTSIDE)),
                *(User(id=value, name='Synthetic student', role=RoleEnum.STUDENT) for value in (STUDENT, PEER, OTHER_CLASS, SECOND)),
                TeacherProfile(id=41, user_id=OWNER), TeacherProfile(id=42, user_id=OTHER), TeacherProfile(id=43, user_id=OUTSIDE),
                StudentProfile(id=501, user_id=STUDENT, classroom_id=61), StudentProfile(id=502, user_id=PEER, classroom_id=61),
                StudentProfile(id=503, user_id=OTHER_CLASS, classroom_id=62), StudentProfile(id=504, user_id=SECOND, classroom_id=61),
                ClassroomTeacher(id=51, teacher_id=41, classroom_id=61), ClassroomTeacher(id=52, teacher_id=42, classroom_id=61),
                ClassroomTeacher(id=53, teacher_id=43, classroom_id=62),
                *(UploadedFile(id=4101+i, uploader_id=OWNER if i < 4 else OTHER, s3_key=KEY, json_s3_key=KEY) for i in range(5)),
                *(Material(id=DOC+i, uploaded_file_id=4101+i, teacher_id=OWNER if i < 4 else OTHER,
                           title='Synthetic material '+str(i), post_status='DRAFT' if i==3 else 'PUBLISHED') for i in range(5)),
                MaterialShare(id=6101, material_id=DOC, teacher_id=OWNER, student_id=STUDENT, share_type='INDIVIDUAL', class_id=61),
                MaterialShare(id=6102, material_id=DOC_TWO, teacher_id=OWNER, student_id=STUDENT, share_type='CLASS', class_id=61),
                MaterialShare(id=6103, material_id=DRAFT, teacher_id=OWNER, student_id=STUDENT, share_type='INDIVIDUAL', class_id=61),
                MaterialShare(id=6104, material_id=OTHER_DOC, teacher_id=OTHER, student_id=STUDENT, share_type='INDIVIDUAL', class_id=61),
                MaterialShare(id=6105, material_id=DOC, teacher_id=OWNER, student_id=SECOND, share_type='INDIVIDUAL', class_id=61),
                Quiz(id=7101, material_id=DOC, content='Synthetic question', correct_answer='trusted database answer'),
                Quiz(id=7102, material_id=DOC_TWO, content='Other question', correct_answer='other trusted answer'),
            ])
            db.commit()
        for doc in (DOC, DOC_TWO, PRIVATE, DRAFT, OTHER_DOC):
            create_and_store_embeddings(str(doc), [Document(page_content='Safe lesson content', metadata={'type':'content'})])
        create_and_store_embeddings('pdf_4101', [Document(page_content='Teacher draft content', metadata={'type':'content'})])

    def headers(self, user=STUDENT):
        role = 'TEACHER' if user in (OWNER, OTHER, OUTSIDE) else 'STUDENT'
        return {'Authorization': 'Bearer '+jwt.encode(access_claims(str(user), role=role), SECRET_KEY_BYTES, algorithm='HS256')}

    def chat(self, user=STUDENT, document=DOC, session=None):
        body={'document_id':str(document), 'question':'Synthetic question'}
        if session is not None: body['session_id']=session
        return self.client.post('/rag/chat', headers=self.headers(user), json=body)

    def counts(self):
        with RagSession() as db:
            return (db.query(ChatSession).count(), db.query(ChatMessage).count(), db.query(EmbeddingTask).count())

    def test_direct_and_class_share_positive_with_distinct_profile_ids(self):
        self.assertEqual(self.chat().status_code, 200)
        self.assertEqual(self.chat(document=DOC_TWO).status_code, 200)
        self.assertEqual(self.chat(OWNER, DRAFT).status_code, 200)
        self.assertEqual(self.chat(OWNER, 'pdf_4101').status_code, 200)

    def test_unshared_peer_other_class_draft_and_initial_denied_without_effects(self):
        before=self.counts()
        with patch('app.rag.router.get_rag_chain') as provider:
            for user, document, expected in [(PEER,DOC,404),(OTHER_CLASS,DOC,404),(STUDENT,PRIVATE,404),
                    (STUDENT,DRAFT,404),(OTHER,DOC,404),(STUDENT,'pdf_4101',403)]:
                with self.subTest(user=user, document=document):
                    self.assertEqual(self.chat(user,document).status_code,expected)
            provider.assert_not_called()
        self.assertEqual(self.counts(),before)

    def test_missing_auth_is_401_without_effects(self):
        before=self.counts()
        self.assertEqual(self.client.post('/rag/chat',json={'document_id':str(DOC),'question':'x'}).status_code,401)
        self.assertEqual(self.counts(),before)

    def test_noncanonical_and_colliding_document_ids_are_400(self):
        before=self.counts()
        with patch('app.rag.router.get_rag_chain') as provider:
            for value in ('05101','5101/','5101?','pdf-4101','pdf_04101','pdf_4101/','0','-1','１','9'*100):
                with self.subTest(value=value):
                    self.assertEqual(self.chat(OWNER,value).status_code,400)
            provider.assert_not_called()
        self.assertEqual(self.counts(),before)
        self.assertNotEqual(_get_collection_name('4101'),_get_collection_name('pdf_4101'))

    def test_accessible_document_switch_is_409_and_other_user_session_is_404(self):
        session=self.chat().json()['session_id'];before=self.counts()
        with patch('app.rag.router.get_rag_chain') as provider:
            self.assertEqual(self.chat(document=DOC_TWO,session=session).status_code,409)
            self.assertEqual(self.chat(SECOND,DOC,session).status_code,404)
            provider.assert_not_called()
        self.assertEqual(self.counts(),before)
        self.assertEqual(self.chat(session=session).status_code,200)

    def test_share_revocation_applies_to_existing_session_and_history(self):
        session=self.chat().json()['session_id']
        with SessionLocal() as db:
            db.query(MaterialShare).filter(MaterialShare.id==6101).delete();db.commit()
        before=self.counts()
        with patch('app.rag.router.get_rag_chain') as provider:
            self.assertEqual(self.chat(session=session).status_code,404);provider.assert_not_called()
        self.assertEqual(self.counts(),before)
        self.assertEqual(self.client.get(f'/rag/chat/sessions?student_id={STUDENT}',headers=self.headers(OWNER)).json(),[])
        self.assertEqual(self.client.get(f'/rag/chat/sessions/{session}/messages?student_id={STUDENT}',headers=self.headers(OWNER)).status_code,404)

    def test_assignment_revocation_applies_to_individual_and_class_share(self):
        self.assertEqual(self.chat().status_code,200)
        with SessionLocal() as db:
            db.query(ClassroomTeacher).filter(ClassroomTeacher.id==51).delete();db.commit()
        for document in (DOC,DOC_TWO):self.assertEqual(self.chat(document=document).status_code,404)
        self.assertEqual(self.client.get(f'/rag/chat/sessions?student_id={STUDENT}',headers=self.headers(OWNER)).status_code,404)

    def test_class_share_requires_current_class_and_matching_share_owner(self):
        with SessionLocal() as db:
            db.query(MaterialShare).filter(MaterialShare.id==6102).update({'class_id':62})
            db.query(MaterialShare).filter(MaterialShare.id==6101).update({'teacher_id':OTHER});db.commit()
        self.assertEqual(self.chat().status_code,404)
        self.assertEqual(self.chat(document=DOC_TWO).status_code,404)

    def test_history_list_and_detail_require_owner_assignment_and_current_share(self):
        own=self.chat().json()['session_id'];other=self.chat(document=OTHER_DOC).json()['session_id']
        response=self.client.get(f'/rag/chat/sessions?student_id={STUDENT}',headers=self.headers(OWNER))
        self.assertEqual(response.status_code,200)
        self.assertEqual([r['id'] for r in response.json()],[own])
        for user,session,student,expected in [(OWNER,own,STUDENT,200),(OWNER,other,STUDENT,404),
                (OUTSIDE,own,STUDENT,404),(STUDENT,own,STUDENT,200),(SECOND,own,STUDENT,404),(OWNER,own,501,404),(OWNER,own,SECOND,404)]:
            self.assertEqual(self.client.get(f'/rag/chat/sessions/{session}/messages?student_id={student}',headers=self.headers(user)).status_code,expected)

    def test_student_history_list_is_self_only_and_rechecks_current_share(self):
        own=self.chat().json()['session_id']
        second=self.chat(document=DOC_TWO).json()['session_id']
        peer=self.chat(SECOND).json()['session_id']
        response=self.client.get(f'/rag/chat/sessions?student_id={STUDENT}',headers=self.headers())
        self.assertEqual(response.status_code,200)
        self.assertEqual({row['id'] for row in response.json()},{own,second})
        self.assertNotIn(peer,{row['id'] for row in response.json()})
        self.assertEqual(self.client.get(f'/rag/chat/sessions?student_id={SECOND}',headers=self.headers()).status_code,404)
        with SessionLocal() as db:
            db.query(MaterialShare).filter(MaterialShare.id==6101).delete();db.commit()
        response=self.client.get(f'/rag/chat/sessions?student_id={STUDENT}',headers=self.headers())
        self.assertEqual(response.status_code,200)
        self.assertEqual({row['id'] for row in response.json()},{second})
        self.assertEqual(self.client.get(f'/rag/chat/sessions/{own}/messages?student_id={STUDENT}',headers=self.headers()).status_code,404)

    def test_deleted_material_and_inconsistent_file_owner_are_denied(self):
        from datetime import datetime
        with SessionLocal() as db:
            db.query(Material).filter(Material.id==DOC).update({'deleted_at':datetime.utcnow()})
            db.query(UploadedFile).filter(UploadedFile.id==4102).update({'uploader_id':OTHER});db.commit()
        self.assertEqual(self.chat().status_code,404)
        self.assertEqual(self.chat(OWNER,DOC_TWO).status_code,404)
        self.assertEqual(self.chat(document=DOC_TWO).status_code,404)

    def test_deleted_linked_file_is_not_an_initial_document_bypass(self):
        from datetime import datetime
        from fastapi import HTTPException
        from app.rag.tasks import create_initial_embedding_task
        with patch('app.rag.router.create_initial_embedding_task.apply_async'):
            response=self.client.post('/rag/embeddings/create-initial',headers=self.headers(OWNER),
                json={'pdf_id':4101,'s3_url':FIXTURE_BASE+'sample.json'})
        self.assertEqual(response.status_code,202)
        task=response.json()['task_id']
        with SessionLocal() as db:
            db.query(Material).filter(Material.id==DOC).update({'deleted_at':datetime.utcnow()});db.commit()
        before=self.counts()
        with patch('app.rag.router.get_rag_chain') as chain, patch('app.rag.router.create_initial_embedding_task.apply_async') as queue, \
             patch('app.rag.router.generate_quiz_with_rag') as quiz, patch('app.document_processor.router.PDFParser') as parser, \
             patch('celery.result.AsyncResult') as status, patch('app.rag.tasks.download_json_sync') as download:
            self.assertEqual(self.chat(OWNER,'pdf_4101').status_code,404)
            for path,body in [('/rag/embeddings/create-initial',{'pdf_id':4101,'s3_url':FIXTURE_BASE+'sample.json'}),
                    ('/rag/quiz/generate',{'document_id':'pdf_4101','num_questions':5}),
                    ('/document/process-concept-check',{'uploaded_file_id':4101,'concept_checks':[{'contents':'x'}]}),
                    ('/document/parse-pdf-from-cloudfront',{'uploaded_file_id':4101,'cloudfront_url':FIXTURE_BASE+'sample.pdf'})]:
                self.assertEqual(self.client.post(path,headers=self.headers(OWNER),json=body).status_code,404)
            self.assertEqual(self.client.get('/rag/embeddings/status/'+task,headers=self.headers(OWNER)).status_code,404)
            with self.assertRaises(HTTPException):
                create_initial_embedding_task.run('4101',FIXTURE_BASE+'sample.json',OWNER)
            for boundary in (chain,queue,quiz,parser,status,download):boundary.assert_not_called()
        self.assertEqual(self.counts(),before)

    def test_embedding_denials_happen_before_metadata_and_enqueue(self):
        before=self.counts()
        with patch('app.rag.router.create_embedding_task.apply_async') as queue:
            for user,document,url,expected in [(OTHER,DOC,FIXTURE_BASE+'sample.json',404),
                    (STUDENT,DOC,FIXTURE_BASE+'sample.json',403),(OWNER,DOC,FIXTURE_BASE+'wrong.json',400)]:
                response=self.client.post('/rag/embeddings/create',headers=self.headers(user),
                    json={'document_id':str(document),'s3_url':url})
                self.assertEqual(response.status_code,expected)
            queue.assert_not_called()
        self.assertEqual(self.counts(),before)

    def test_embedding_metadata_status_and_initial_owner_positive(self):
        with patch('app.rag.router.create_embedding_task.apply_async') as queue:
            response=self.client.post('/rag/embeddings/create',headers=self.headers(OWNER),json={'document_id':str(DOC),'s3_url':FIXTURE_BASE+'sample.json'})
            self.assertEqual(response.status_code,202);queue.assert_called_once()
            self.assertEqual(queue.call_args.kwargs['kwargs']['user_id'],OWNER)
        task=response.json()['task_id']
        with patch('celery.result.AsyncResult') as result:
            result.return_value.state='SUCCESS'
            self.assertEqual(self.client.get('/rag/embeddings/status/'+task,headers=self.headers(OWNER)).status_code,200)
            result.reset_mock()
            self.assertEqual(self.client.get('/rag/embeddings/status/'+task,headers=self.headers(OTHER)).status_code,404)
            self.assertEqual(self.client.get('/rag/embeddings/status/'+task,headers=self.headers(STUDENT)).status_code,403)
            self.assertEqual(self.client.get('/rag/embeddings/status/legacy-task',headers=self.headers(OWNER)).status_code,404)
            result.assert_not_called()
        with patch('app.rag.router.create_initial_embedding_task.apply_async') as queue:
            self.assertEqual(self.client.post('/rag/embeddings/create-initial',headers=self.headers(OWNER),json={'pdf_id':4101,'s3_url':FIXTURE_BASE+'sample.json'}).status_code,202)
            queue.assert_called_once()

    def test_initial_and_quiz_generation_other_owner_denied_before_provider(self):
        with patch('app.rag.router.create_initial_embedding_task.apply_async') as queue, patch('app.rag.router.generate_quiz_with_rag') as provider:
            self.assertEqual(self.client.post('/rag/embeddings/create-initial',headers=self.headers(OTHER),json={'pdf_id':4101,'s3_url':FIXTURE_BASE+'sample.json'}).status_code,404)
            for user,doc,status in [(OTHER,DOC,404),(STUDENT,DOC,403),(OTHER,'pdf_4101',404)]:
                self.assertEqual(self.client.post('/rag/quiz/generate',headers=self.headers(user),json={'document_id':str(doc),'num_questions':5}).status_code,status)
            queue.assert_not_called();provider.assert_not_called()
        response=self.client.post('/rag/quiz/generate',headers=self.headers(OWNER),json={'document_id':str(DOC),'num_questions':5})
        self.assertEqual(response.status_code,200);self.assertIn('correct_answer',response.json()['questions'][0])

    def test_grading_uses_database_answer_and_rejects_forged_fields(self):
        body={'material_id':DOC,'student_answers':[{'question_id':7101,'student_answer':'trusted database answer'}]}
        response=self.client.post('/rag/quiz/grade-batch',headers=self.headers(),json=body)
        self.assertEqual(response.status_code,200);self.assertTrue(response.json()[0]['is_correct'])
        body['student_answers'][0]['student_answer']='forged answer'
        response=self.client.post('/rag/quiz/grade-batch',headers=self.headers(),json=body)
        self.assertFalse(response.json()[0]['is_correct'])
        with patch('app.rag.router.grade_quiz_answers') as provider:
            for extra in ({'questions':[{'id':7101,'correct_answer':'forged answer'}]},{'studentId':SECOND},{'score':100}):
                self.assertEqual(self.client.post('/rag/quiz/grade-batch',headers=self.headers(),json={**body,**extra}).status_code,422)
            provider.assert_not_called()

    def test_grading_mismatched_unknown_duplicate_and_unshared_denied_before_provider(self):
        with patch('app.rag.router.grade_quiz_answers') as provider:
            for user,ids,status in [(STUDENT,[7102],400),(STUDENT,[7999],400),(STUDENT,[7101,7101],400),(PEER,[7101],404),(OWNER,[7101],403)]:
                body={'material_id':DOC,'student_answers':[{'question_id':value,'student_answer':'x'} for value in ids]}
                self.assertEqual(self.client.post('/rag/quiz/grade-batch',headers=self.headers(user),json=body).status_code,status)
            provider.assert_not_called()

    def test_legacy_quiz_answer_chunks_are_excluded_from_student_search(self):
        store=LocalVectorStore(collection_name=_get_collection_name(str(DOC)))
        store.delete_collection()
        LocalVectorStore.from_documents(documents=[
            Document(page_content='TEACHER_ANSWER_SENTINEL',metadata={'type':'quiz'}),
            Document(page_content='Safe lesson content',metadata={'type':'content'}),
            Document(page_content='UNTYPED_PRIVATE_SENTINEL',metadata={})],embedding=LocalEmbeddings(),collection_name=store.name)
        response=self.chat()
        self.assertEqual(response.status_code,200)
        self.assertIn('Safe lesson content',response.json()['answer'])
        self.assertNotIn('SENTINEL',response.json()['answer'])

    def test_database_permission_error_is_503_and_has_no_side_effects(self):
        before=self.counts()
        def broken(connection,cursor,statement,parameters,context,executemany):
            if statement.lstrip().upper().startswith('SELECT') and 'FROM materials' in statement:
                raise OperationalError('authorization query',{},Exception('synthetic unavailable'))
        event.listen(engine,'before_cursor_execute',broken)
        try:
            with patch('app.rag.router.get_rag_chain') as provider:
                self.assertEqual(self.chat().status_code,503);provider.assert_not_called()
        finally:event.remove(engine,'before_cursor_execute',broken)
        self.assertEqual(self.counts(),before)

    def test_worker_rechecks_owner_before_storage_download(self):
        from app.rag.tasks import create_embedding_task
        with patch('app.rag.tasks.download_json_sync') as download:
            from fastapi import HTTPException
            with self.assertRaises(HTTPException):
                create_embedding_task.run(str(DOC),FIXTURE_BASE+'sample.json',OTHER)
            download.assert_not_called()

    def test_direct_document_processing_requires_real_file_owner(self):
        with patch('app.document_processor.router.PDFParser') as parser:
            for user,status in [(STUDENT,403),(OTHER,404)]:
                self.assertEqual(self.client.post('/document/process-concept-check',headers=self.headers(user),json={'uploaded_file_id':4101,'concept_checks':[{'contents':'x'}]}).status_code,status)
                self.assertEqual(self.client.post('/document/parse-pdf-from-cloudfront',headers=self.headers(user),json={'uploaded_file_id':4101,'cloudfront_url':FIXTURE_BASE+'sample.pdf'}).status_code,status)
            parser.assert_not_called()
        response=self.client.post('/document/process-concept-check',headers=self.headers(OWNER),json={'uploaded_file_id':4101,'concept_checks':[{'contents':'synthetic'}]})
        self.assertEqual(response.status_code,200)

    def test_direct_pdf_owner_success_and_url_mismatch_before_download(self):
        with SessionLocal() as db:
            db.query(UploadedFile).filter(UploadedFile.id==4101).update({'s3_key':'sample.pdf'});db.commit()
        response=self.client.post('/document/parse-pdf-from-cloudfront',headers=self.headers(OWNER),
            json={'uploaded_file_id':4101,'cloudfront_url':FIXTURE_BASE+'sample.pdf'})
        self.assertEqual(response.status_code,200)
        self.assertIn('parsed_data',response.json())
        with patch('app.document_processor.router.download_from_cloudfront') as download:
            self.assertEqual(self.client.post('/document/parse-pdf-from-cloudfront',headers=self.headers(OWNER),
                json={'uploaded_file_id':4101,'cloudfront_url':FIXTURE_BASE+'other.pdf'}).status_code,400)
            download.assert_not_called()
        self.assertEqual(self.client.post('/document/parse-pdf-from-cloudfront',
            json={'uploaded_file_id':4101,'cloudfront_url':FIXTURE_BASE+'sample.pdf'}).status_code,401)

    def test_status_rechecks_current_object_before_celery_access(self):
        with patch('app.rag.router.create_embedding_task.apply_async'):
            response=self.client.post('/rag/embeddings/create',headers=self.headers(OWNER),
                json={'document_id':str(DOC),'s3_url':FIXTURE_BASE+'sample.json'})
        task=response.json()['task_id']
        with SessionLocal() as db:
            db.query(UploadedFile).filter(UploadedFile.id==4101).update({'uploader_id':OTHER});db.commit()
        with patch('celery.result.AsyncResult') as result:
            self.assertEqual(self.client.get('/rag/embeddings/status/'+task,headers=self.headers(OWNER)).status_code,404)
            result.assert_not_called()

    def test_local_storage_reads_only_named_synthetic_objects_without_network(self):
        key='local/synthetic/authz/unit-fixture.json';root=Path(LOCAL_OBJECT_STORAGE_DIR);root.mkdir(parents=True,exist_ok=True)
        path=root/(hashlib.sha256(key.encode()).hexdigest()+'.json')
        path.write_text(json.dumps({'chapters':[{'type':'content','content':'Persisted synthetic content'}]}))
        try:
            with patch('httpx.get',side_effect=AssertionError('Network attempt')):
                self.assertEqual(load_fixture_json(FIXTURE_BASE+key)['chapters'][0]['content'],'Persisted synthetic content')
                for url in ('https://external.invalid/'+key,FIXTURE_BASE+'../private.json',FIXTURE_BASE+key+'?override=1'):
                    with self.assertRaises(ValueError):load_fixture_json(url)
        finally:path.unlink()
