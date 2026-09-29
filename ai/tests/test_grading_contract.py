"""3-A accepted snapshots, strict provider results, and bounded local fault evidence."""
import asyncio
from datetime import datetime, timedelta
import json
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.exc import OperationalError
from runtime_fixture import access_claims
from grading_fixture import make_attempt
import test_object_authorization as authz
from test_object_authorization import DOC, DOC_TWO, STUDENT, SECOND, OWNER
from app.main import app
from app.common.db_session import Base, SessionLocal, engine, get_db
from app.common.models import GradingAttempt, GradingAttemptItem, Quiz, Material, MaterialShare
from app.local_grading import control_path, grading_stats
from app.rag.grading_contract import validate_results
from app.rag.quiz_service import _grading_json, grade_quiz_answers, GradingResponseError


class GradingContractTests(unittest.TestCase):
    headers = authz.ObjectAuthorizationTests.headers

    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(engine)
        cls.client = TestClient(app)

    def setUp(self):
        authz.ObjectAuthorizationTests.setUp(self)
        with SessionLocal() as db:
            db.query(Material).filter(Material.id == DOC).update({"title": "[GRADING LOCAL] unit snapshot"})
            db.commit()

    def attempt(self, answer="trusted database answer", **changes):
        return make_attempt(DOC, STUDENT, [(7101, answer)], **changes)

    def post(self, body, user=STUDENT):
        return self.client.post("/rag/quiz/grade-batch", headers=self.headers(user), json=body)

    def identity(self, body):
        with SessionLocal() as db:
            row = db.query(GradingAttempt).filter(GradingAttempt.attempt_id == body["attempt_id"]).one()
            return row.id, row.idempotency_key

    def test_committed_snapshot_survives_live_question_and_answer_edits(self):
        body = self.attempt()
        with SessionLocal() as db:
            db.query(Quiz).filter(Quiz.id == 7101).update({"content": "edited question", "correct_answer": "edited answer"})
            db.commit()
        response = self.post(body)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()[0]["is_correct"])
        self.assertEqual(set(response.json()[0]), {"question_id", "student_answer", "is_correct", "ai_feedback"})
        self.assertNotIn("correct_answer", response.text)

    def test_snapshot_answer_is_not_replaced_by_request_fields(self):
        body = self.attempt("wrong answer")
        response = self.post(body)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()[0]["is_correct"])
        with patch("app.rag.router.grade_quiz_answers") as provider:
            for extra in ({"student_answers": []}, {"correct_answer": "wrong answer"},
                          {"questions": []}, {"material_id": DOC_TWO}, {"student_id": SECOND}):
                self.assertEqual(self.post({**body, **extra}).status_code, 422)
            provider.assert_not_called()

    def test_old_direct_grading_contract_requires_accepted_attempt(self):
        with patch("app.rag.router.grade_quiz_answers") as provider:
            response = self.post({"material_id": DOC, "student_answers": [{"question_id": 7101, "student_answer": "x"}]})
            self.assertEqual(response.status_code, 422)
            provider.assert_not_called()

    def test_attempt_owner_role_and_capability_are_required_before_provider(self):
        body = self.attempt()
        with patch("app.rag.router.grade_quiz_answers") as provider:
            self.assertEqual(self.post(body, SECOND).status_code, 404)
            self.assertEqual(self.post(body, OWNER).status_code, 403)
            self.assertEqual(self.post({**body, "attempt_id": str(uuid.uuid4())}).status_code, 404)
            self.assertEqual(self.post({**body, "execution_token": "A" * 43}).status_code, 404)
            self.assertEqual(self.client.post("/rag/quiz/grade-batch", json=body).status_code, 401)
            provider.assert_not_called()

    def test_stale_generation_deadline_and_terminal_states_never_call_provider(self):
        body = self.attempt()
        with patch("app.rag.router.grade_quiz_answers") as provider:
            self.assertEqual(self.post({**body, "execution_generation": 2}).status_code, 409)
            for state in ("READY", "SUCCEEDED", "FAILED", "UNKNOWN", "REVOKED"):
                with SessionLocal() as db:
                    db.query(GradingAttempt).filter(GradingAttempt.attempt_id == body["attempt_id"]).update({"state": state})
                    db.commit()
                self.assertEqual(self.post(body).status_code, 409)
            with SessionLocal() as db:
                db.query(GradingAttempt).filter(GradingAttempt.attempt_id == body["attempt_id"]).update(
                    {"state": "PROCESSING", "deadline_at": datetime.utcnow() - timedelta(seconds=1)})
                db.commit()
            self.assertEqual(self.post(body).status_code, 409)
            provider.assert_not_called()

    def test_current_share_and_material_are_rechecked_for_accepted_attempt(self):
        body = self.attempt()
        with SessionLocal() as db:
            db.query(MaterialShare).filter(MaterialShare.material_id == DOC, MaterialShare.student_id == STUDENT).delete()
            db.commit()
        with patch("app.rag.router.grade_quiz_answers") as provider:
            self.assertEqual(self.post(body).status_code, 404)
            provider.assert_not_called()

    def test_provider_boundary_has_no_common_database_transaction(self):
        body = self.attempt()
        sessions = []
        def database():
            db = SessionLocal()
            sessions.append(db)
            try:
                yield db
            finally:
                db.close()
        async def provider(questions, answers, **kwargs):
            self.assertEqual(len(sessions), 1)
            self.assertFalse(sessions[0].in_transaction())
            # A separate DB connection can read the accepted snapshot at the boundary.
            with engine.connect() as connection:
                self.assertIsNotNone(connection.execute(GradingAttempt.__table__.select()).first())
            return [{"question_id": 7101, "student_answer": answers[0]["student_answer"], "is_correct": True, "ai_feedback": "ok"}]
        app.dependency_overrides[get_db] = database
        try:
            with patch("app.rag.router.grade_quiz_answers", side_effect=provider):
                self.assertEqual(self.post(body).status_code, 200)
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_partial_duplicate_foreign_or_coerced_provider_results_fail_whole_batch(self):
        body = self.attempt()
        valid = {"question_id": 7101, "student_answer": "trusted database answer", "is_correct": True, "ai_feedback": "ok"}
        malformed = [[], [valid, valid], [{**valid, "question_id": 7102}], [{**valid, "question_id": "7101"}],
            [{**valid, "question_id": True}], [{**valid, "is_correct": "false"}], [{**valid, "is_correct": 1}],
            [{**valid, "ai_feedback": None}], [{**valid, "ai_feedback": "x" * 2001}],
            [{**valid, "student_answer": "altered"}], [{**valid, "correct_answer": "forged"}], {}]
        for results in malformed:
            with self.subTest(kind=type(results).__name__), patch("app.rag.router.grade_quiz_answers", new=AsyncMock(return_value=results)):
                response = self.post(body)
                self.assertEqual(response.status_code, 502)
                self.assertEqual(response.json(), {"detail": "Invalid grading provider response"})

    def test_snapshot_corruption_and_database_error_fail_closed(self):
        body = self.attempt()
        identity, _ = self.identity(body)
        with SessionLocal() as db:
            db.query(GradingAttemptItem).filter(GradingAttemptItem.attempt_id == identity).update({"grading_version": "unknown"})
            db.commit()
        with patch("app.rag.router.grade_quiz_answers") as provider:
            self.assertEqual(self.post(body).status_code, 503)
            provider.assert_not_called()
        def broken(connection, cursor, statement, parameters, context, executemany):
            if "FROM grading_attempts" in statement:
                raise OperationalError("synthetic query", {}, Exception("synthetic unavailable"))
        event.listen(engine, "before_cursor_execute", broken)
        try:
            with patch("app.rag.router.grade_quiz_answers") as provider:
                self.assertEqual(self.post(body).status_code, 503)
                provider.assert_not_called()
        finally:
            event.remove(engine, "before_cursor_execute", broken)

    def test_execution_input_is_strict_and_bounded(self):
        body = self.attempt()
        with patch("app.rag.router.grade_quiz_answers") as provider:
            for field, value in (("execution_generation", True), ("execution_generation", "1"),
                ("execution_generation", 0), ("execution_token", "a" * 10000),
                ("attempt_id", body["attempt_id"].upper()), ("attempt_id", "../other")):
                self.assertEqual(self.post({**body, field: value}).status_code, 422)
            provider.assert_not_called()

    def test_snapshot_text_and_question_count_limits_reject_before_provider(self):
        for field, value in (("question_content", "x" * 20001), ("correct_answer", "x" * 2001),
                             ("student_answer", "x" * 2001), ("quiz_version", -1)):
            body = self.attempt()
            identity, _ = self.identity(body)
            with SessionLocal() as db:
                db.query(GradingAttemptItem).filter(GradingAttemptItem.attempt_id == identity).update({field: value})
                db.commit()
            with patch("app.rag.router.grade_quiz_answers") as provider:
                self.assertEqual(self.post(body).status_code, 503)
                provider.assert_not_called()
        body = self.attempt()
        identity, _ = self.identity(body)
        with SessionLocal() as db:
            db.add_all([GradingAttemptItem(attempt_id=identity, quiz_id=8000+index, quiz_version=0,
                question_number=index+2, question_type="SHORT_ANSWER", title="Synthetic",
                question_content="Synthetic", correct_answer="a", student_answer="a", grading_version="snapshot-v1")
                for index in range(50)])
            db.commit()
        with patch("app.rag.router.grade_quiz_answers") as provider:
            self.assertEqual(self.post(body).status_code, 503)
            provider.assert_not_called()

    def test_local_faults_have_durable_started_and_completed_counts(self):
        for mode in ("normal", "http_error", "missing", "duplicate", "wrong_id", "wrong_type", "long_feedback", "wrong_answer"):
            body = self.attempt()
            _, key = self.identity(body)
            path = control_path(key, 1)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"mode": mode}))
            try:
                response = self.post(body)
                self.assertEqual(response.status_code, 200 if mode == "normal" else 503 if mode == "http_error" else 502)
                counts = grading_stats(key)
                self.assertEqual(counts[0]["started"], 1)
                self.assertEqual(counts[0]["finished"], 1)
                self.assertEqual(counts[0]["returned"], 0 if mode == "http_error" else 1)
            finally:
                path.unlink()

    def test_local_gate_and_delay_are_bounded_and_cancellation_is_recorded(self):
        body = self.attempt()
        _, key = self.identity(body)
        path = control_path(key, 1)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"mode": "normal", "gate": True}))
        try:
            with patch("app.rag.router.GRADING_TIMEOUT_SECONDS", .05):
                self.assertEqual(self.post(body).status_code, 504)
            self.assertEqual(grading_stats(key)[0], {"generation": 1, "started": 1, "finished": 1, "returned": 0})
            path.with_suffix(".release").touch()
            self.assertEqual(self.post(body).status_code, 200)
            self.assertEqual(grading_stats(key)[0]["returned"], 1)
        finally:
            path.unlink()
            path.with_suffix(".release").unlink(missing_ok=True)

    def test_fault_controls_cannot_affect_nondedicated_material(self):
        body = self.attempt()
        _, key = self.identity(body)
        with SessionLocal() as db:
            db.query(Material).filter(Material.id == DOC).update({"title": "ordinary synthetic material"})
            db.commit()
        path = control_path(key, 1)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"mode": "normal"}))
        try:
            self.assertEqual(self.post(body).status_code, 504)
            self.assertEqual(grading_stats(key), [])
        finally:
            path.unlink()

    def test_production_provider_json_requires_actual_boolean_and_bounded_feedback(self):
        self.assertEqual(_grading_json('{"is_correct":false,"feedback":"try again"}')["is_correct"], False)
        for raw in ('{}', '[]', '{"is_correct":"false","feedback":"x"}',
            '{"is_correct":false,"feedback":null}', '{"is_correct":false,"is_correct":true,"feedback":"x"}',
            json.dumps({"is_correct": True, "feedback": "x" * 2001}), 'not json'):
            with self.assertRaises(ValueError):
                _grading_json(raw)

    def test_valid_unicode_and_control_feedback_fits_complete_json_bound(self):
        for text in ("\x00" * 2000, "한" * 2000, "😀" * 2000):
            raw = json.dumps({"is_correct": True, "feedback": text}, ensure_ascii=True)
            self.assertGreater(len(raw), 12000)
            self.assertEqual(_grading_json(raw)["feedback"], text)
        with self.assertRaises(GradingResponseError):
            _grading_json(" " * 32769)

    def test_production_provider_exception_is_not_converted_into_wrong_answer(self):
        async def execute():
            with patch("app.rag.quiz_service.LOCAL_EXTERNAL_STUBS", False), \
                    patch("app.rag.quiz_service._grade_one", new=AsyncMock(side_effect=TimeoutError)) as provider:
                with self.assertRaises(TimeoutError):
                    await grade_quiz_answers([{"id": 1}], [{"question_id": 1, "student_answer": "x"}])
                self.assertEqual(provider.await_count, 1)
        asyncio.run(execute())

    def test_production_malformed_payload_is_confirmed_failure_not_unknown(self):
        from fastapi import HTTPException
        async def execute():
            with patch("app.rag.quiz_service.LOCAL_EXTERNAL_STUBS", False), \
                    patch("app.rag.quiz_service._grade_one", new=AsyncMock(side_effect=GradingResponseError)):
                with self.assertRaises(HTTPException) as failure:
                    await grade_quiz_answers([{"id": 1}], [{"question_id": 1, "student_answer": "x"}])
                self.assertEqual(failure.exception.status_code, 502)
        asyncio.run(execute())

    def test_zero_initial_quiz_revision_is_a_valid_immutable_snapshot(self):
        body = self.attempt()
        identity, _ = self.identity(body)
        with SessionLocal() as db:
            db.query(GradingAttemptItem).filter(GradingAttemptItem.attempt_id == identity).update({"quiz_version": 0})
            db.commit()
        self.assertEqual(self.post(body).status_code, 200)
