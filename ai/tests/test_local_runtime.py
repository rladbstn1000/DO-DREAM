"""Local provider/real JWT+SQL unit checks; MySQL/Redis integration is in root smoke."""
import os
import subprocess
import sys
import unittest
from unittest.mock import patch
from runtime_fixture import access_claims

from fastapi.testclient import TestClient
from jose import jwt
from app.config import SECRET_KEY_BYTES, JWT_ISSUER
from app.main import app
from app.common.db_session import Base, engine, SessionLocal
from app.common.models import (User, RoleEnum, TeacherProfile, StudentProfile, ClassroomTeacher, UploadedFile, Material, MaterialShare)
from app.local_providers import load_fixture_json, grade_answers, FIXTURE_BASE
from app.rag.service import extract_data_from_json, create_and_store_embeddings


class LocalRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(engine)
        with SessionLocal() as db:
            db.add_all([
                User(id=101, name="Synthetic unit student", role=RoleEnum.STUDENT),
                User(id=110, name="Synthetic owner", role=RoleEnum.TEACHER),
                TeacherProfile(id=210, user_id=110), StudentProfile(id=211, user_id=101, classroom_id=310),
                ClassroomTeacher(id=212, teacher_id=210, classroom_id=310),
                UploadedFile(id=410, uploader_id=110, s3_key="local/synthetic/lesson.json", json_s3_key="local/synthetic/lesson.json"),
                Material(id=510, teacher_id=110, uploaded_file_id=410, title="Synthetic fixture", post_status="PUBLISHED"),
                MaterialShare(id=610, material_id=510, teacher_id=110, student_id=101, share_type="INDIVIDUAL", class_id=310),
            ])
            db.commit()
        cls.client = TestClient(app)
        cls.token = jwt.encode(access_claims(), SECRET_KEY_BYTES, algorithm="HS256")

    def test_real_jwt_and_database_lookup(self):
        result = self.client.get("/users/users/me", headers={"Authorization": f"Bearer {self.token}"})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["id"], 101)
        self.assertEqual(result.headers["X-DO-DREAM-External-Provider"], "local_stub")

    def test_missing_and_invalid_tokens_are_denied(self):
        self.assertIn(self.client.get("/users/users/me").status_code, (401, 403))
        result = self.client.get("/users/users/me", headers={"Authorization": "Bearer invalid"})
        self.assertEqual(result.status_code, 401)

    def test_external_url_never_downloaded_in_local(self):
        with patch("httpx.get", side_effect=AssertionError("Network attempt")):
            with self.assertRaises(ValueError):
                load_fixture_json("https://example.com/private.json")
            self.assertEqual(load_fixture_json(FIXTURE_BASE + "sample.json")["external_provider"], "local_stub")

    def test_existing_rag_route_persists_local_chat(self):
        docs = extract_data_from_json(load_fixture_json(FIXTURE_BASE + "sample.json"))
        create_and_store_embeddings("510", docs)
        result = self.client.post("/rag/chat", headers={"Authorization": f"Bearer {self.token}"}, json={"document_id": "510", "question": "합성 질문"})
        self.assertEqual(result.status_code, 200)
        self.assertIn("LOCAL STUB", result.json()["answer"])
        from app.rag.database import SessionLocal as RagSession
        from app.rag.models import ChatMessage
        with RagSession() as db:
            self.assertEqual(db.query(ChatMessage).filter(ChatMessage.session_id == result.json()["session_id"]).count(), 2)

    def test_local_grader_does_not_unconditionally_succeed(self):
        results = grade_answers([{"id": 1, "correct_answer": "synthetic"}], [{"question_id": 1, "student_answer": "wrong"}])
        self.assertFalse(results[0]["is_correct"])
        self.assertIn("LOCAL STUB", results[0]["ai_feedback"])
        with self.assertRaises(ValueError):
            grade_answers([], [{"question_id": 1, "student_answer": "wrong"}])

    def test_model_packages_not_loaded(self):
        self.assertFalse(any(name in sys.modules for name in ("torch", "transformers", "langchain_community", "openai", "langchain_chroma")))

    def test_deployment_rejects_stubs_and_missing_secret(self):
        for changes in ({"APP_ENV": "production"}, {"JWT_SECRET_BASE64": ""}):
            env = {**os.environ, **changes}
            result = subprocess.run([sys.executable, "-c", "import app.config"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
