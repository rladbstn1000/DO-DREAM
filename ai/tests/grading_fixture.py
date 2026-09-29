"""Only synthetic accepted attempts, persisted in the tests' temporary SQL DB."""
from datetime import datetime, timedelta
import hashlib
import secrets
import uuid

from app.common.db_session import SessionLocal
from app.common.models import GradingAttempt, GradingAttemptItem, Quiz


def make_attempt(material_id, student_id, submitted, **changes):
    token = secrets.token_urlsafe(32)
    identity = str(uuid.uuid4())
    internal_id = secrets.randbelow(2**52) + 1
    values = dict(id=internal_id, attempt_id=identity, student_id=student_id,
        material_id=material_id, idempotency_key=str(uuid.uuid4()), state="PROCESSING",
        execution_generation=1, execution_token_hash=hashlib.sha256(token.encode()).hexdigest(),
        deadline_at=datetime.utcnow() + timedelta(seconds=30))
    values.update(changes)
    with SessionLocal() as db:
        db.add(GradingAttempt(**values))
        for index, (quiz_id, answer) in enumerate(submitted, start=1):
            quiz = db.query(Quiz).filter(Quiz.id == quiz_id).one()
            db.add(GradingAttemptItem(attempt_id=internal_id, quiz_id=quiz_id, quiz_version=1,
                question_number=index, question_type="SHORT_ANSWER", title="Synthetic snapshot",
                question_content=quiz.content, correct_answer=quiz.correct_answer,
                student_answer=answer, grading_version="snapshot-v1"))
        db.commit()
    return {"attempt_id": identity, "execution_generation": values["execution_generation"],
            "execution_token": token}
