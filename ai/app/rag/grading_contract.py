"""Read a server-owned grading snapshot and validate a complete provider batch."""
import hashlib
import hmac
import uuid

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, field_validator
from sqlalchemy import func

from app.common.models import GradingAttempt, GradingAttemptItem
from app.security.authorization import fail_closed, student_only, require_material, require_quizzes
from app.config import AI_MODE

MAX_QUESTIONS = 50
MAX_ANSWER_CHARS = 2000
MAX_FEEDBACK_CHARS = 2000
GRADING_TIMEOUT_SECONDS = 10


class BatchGradingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attempt_id: StrictStr
    execution_generation: StrictInt = Field(ge=1, le=2147483647)
    execution_token: StrictStr = Field(pattern=r"^[A-Za-z0-9_-]{43}$")

    @field_validator("attempt_id")
    @classmethod
    def canonical_uuid(cls, value):
        if str(uuid.UUID(value)) != value:
            raise ValueError("Expected a canonical attempt identifier")
        return value


class GradingResultResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_id: StrictInt = Field(gt=0, le=9223372036854775807)
    student_answer: StrictStr = Field(max_length=MAX_ANSWER_CHARS)
    is_correct: StrictBool
    ai_feedback: StrictStr = Field(max_length=MAX_FEEDBACK_CHARS)


@fail_closed
def load_grading_snapshot(db, user, request):
    student_only(user)
    attempt = db.query(GradingAttempt).filter(GradingAttempt.attempt_id == request.attempt_id,
                                             GradingAttempt.student_id == user.id).first()
    if attempt is None:
        raise HTTPException(404, "Object not found")
    material = require_material(db, user, attempt.material_id)
    supplied = hashlib.sha256(request.execution_token.encode("ascii")).hexdigest()
    if not attempt.execution_token_hash or not hmac.compare_digest(supplied, attempt.execution_token_hash):
        raise HTTPException(404, "Object not found")
    # Deadline comparison uses the shared DB clock, matching the Spring lease.
    now_function = func.utc_timestamp(6) if db.bind.dialect.name == "mysql" else func.current_timestamp()
    now = db.query(now_function).scalar()
    if (attempt.state != "PROCESSING" or attempt.execution_generation != request.execution_generation
            or attempt.deadline_at is None or attempt.deadline_at <= now):
        raise HTTPException(409, "Grading execution is not active")
    items = db.query(GradingAttemptItem).filter(GradingAttemptItem.attempt_id == attempt.id).order_by(
        GradingAttemptItem.quiz_id).all()
    if not 1 <= len(items) <= MAX_QUESTIONS:
        raise HTTPException(503, "Grading snapshot unavailable")
    # Only membership is checked against live quizzes. Content/answers always use snapshots.
    require_quizzes(db, user, attempt.material_id, [item.quiz_id for item in items])
    if any(item.grading_version != "snapshot-v1" or item.quiz_version is None or item.quiz_version < 0
           or not isinstance(item.question_content, str) or len(item.question_content) > 20000
           or not isinstance(item.correct_answer, str) or len(item.correct_answer) > MAX_ANSWER_CHARS
           or not isinstance(item.student_answer, str) or len(item.student_answer) > MAX_ANSWER_CHARS
           for item in items):
        raise HTTPException(503, "Grading snapshot unavailable")
    questions = [{"id": item.quiz_id, "content": item.question_content,
                  "correct_answer": item.correct_answer} for item in items]
    answers = [{"question_id": item.quiz_id, "student_answer": item.student_answer} for item in items]
    context = {"attempt_id": attempt.attempt_id, "submission_key": attempt.idempotency_key,
               "generation": attempt.execution_generation, "material_title": material.title}
    if AI_MODE == 'LIVE_OPENAI':
        from app.indexing.store import resolve_active
        from app.indexing.runtime import authorize_pointer
        pointer = resolve_active(db,user,str(attempt.material_id))
        authorize_pointer(pointer,'grading')
        context['pointer'] = pointer
    # Material/user/snapshots are plain values now. No connection/transaction is retained
    # while waiting for the provider, including the authentication dependency's session.
    db.rollback()
    db.close()
    return questions, answers, context


def validate_results(results, answers):
    if type(results) is not list or len(results) != len(answers):
        raise ValueError("Invalid grading result count")
    expected = {answer["question_id"]: answer["student_answer"] for answer in answers}
    validated = [GradingResultResponse.model_validate(result) for result in results]
    ids = [result.question_id for result in validated]
    if len(set(ids)) != len(ids) or set(ids) != set(expected):
        raise ValueError("Invalid grading result identifiers")
    if any(result.student_answer != expected[result.question_id] for result in validated):
        raise ValueError("Invalid grading result answer")
    return validated
