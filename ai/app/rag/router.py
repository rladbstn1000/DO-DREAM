from datetime import datetime
from typing import Optional, List
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StrictInt
from sqlalchemy.orm import Session
from langchain_core.messages import HumanMessage, AIMessage

from app.rag.tasks import create_embedding_task, create_initial_embedding_task
from app.rag.service import get_rag_chain
from app.rag.database import get_rag_db
from app.rag import models as rag_models
from app.rag.models import ChatSessionDetailDto, ChatSessionDto
from app.rag.quiz_service import generate_quiz_with_rag, grade_quiz_answers
from app.security.auth import get_current_user
from app.security.models import User
from app.security.authorization import (
    teacher_only, require_document, require_file, require_object_url, document_json_key,
    require_history_subject, require_history_material, require_quizzes, document_ref,
)
from app.common.db_session import get_db


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InitialEmbeddingRequest(RequestModel):
    pdf_id: StrictInt = Field(gt=0, le=9223372036854775807)
    s3_url: HttpUrl


class EmbeddingRequest(RequestModel):
    document_id: str
    s3_url: HttpUrl


class ChatRequest(RequestModel):
    document_id: str
    question: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    session_id: str


class GenerateQuizRequest(RequestModel):
    document_id: str
    num_questions: int = Field(default=10, ge=5, le=20)


class QuizQuestionResponse(BaseModel):
    question_type: str
    question_number: int
    title: str
    content: str
    correct_answer: str
    chapter_reference: Optional[str] = None


class GenerateQuizResponse(BaseModel):
    questions: List[QuizQuestionResponse]
    generated_at: datetime


class GradeStudentAnswerItem(RequestModel):
    question_id: StrictInt = Field(gt=0, le=9223372036854775807)
    student_answer: str


class BatchGradingRequest(RequestModel):
    material_id: StrictInt = Field(gt=0, le=9223372036854775807)
    student_answers: List[GradeStudentAnswerItem]


class GradingResultResponse(BaseModel):
    question_id: int
    student_answer: str
    is_correct: bool
    ai_feedback: str


router = APIRouter(prefix="/rag", tags=["RAG"])


def enqueue_embedding(task, *, document_id, user, rag_db, arguments):
    # Authorization and URL binding have already completed before metadata or queue writes.
    task_id = str(uuid.uuid4())
    rag_db.add(rag_models.EmbeddingTask(id=task_id, user_id=user.id, document_id=document_id))
    rag_db.commit()
    try:
        task.apply_async(kwargs={**arguments, "user_id": user.id}, task_id=task_id)
    except Exception:
        raise HTTPException(503, "Embedding queue unavailable") from None
    return task_id


@router.post("/embeddings/create-initial", status_code=202)
async def api_create_initial_embedding(
    request: InitialEmbeddingRequest, current_user: User = Depends(get_current_user),
    common_db: Session = Depends(get_db), rag_db: Session = Depends(get_rag_db),
):
    file = require_file(common_db, current_user, request.pdf_id)
    url = require_object_url(request.s3_url, file.json_s3_key)
    document_id = f"pdf_{file.id}"
    task_id = enqueue_embedding(create_initial_embedding_task, document_id=document_id,
        user=current_user, rag_db=rag_db,
        arguments={"pdf_id": str(file.id), "s3_url": url})
    return {"status": "processing", "message": "초기 임베딩 생성 작업이 시작되었습니다.",
            "pdf_id": file.id, "collection_name": f"material_{document_id}",
            "task_id": task_id, "check_status_url": f"/rag/embeddings/status/{task_id}"}


@router.post("/embeddings/create", status_code=202)
async def api_create_embedding(
    request: EmbeddingRequest, current_user: User = Depends(get_current_user),
    common_db: Session = Depends(get_db), rag_db: Session = Depends(get_rag_db),
):
    teacher_only(current_user)
    if document_ref(request.document_id)[0] != "material":
        raise HTTPException(400, "Expected a material identifier")
    require_document(common_db, current_user, request.document_id)
    url = require_object_url(request.s3_url, document_json_key(common_db, request.document_id))
    task_id = enqueue_embedding(create_embedding_task, document_id=request.document_id,
        user=current_user, rag_db=rag_db,
        arguments={"document_id": request.document_id, "s3_url": url})
    return {"status": "processing", "message": "임베딩 생성 작업이 시작되었습니다.",
            "document_id": request.document_id, "task_id": task_id,
            "check_status_url": f"/rag/embeddings/status/{task_id}"}


@router.get("/embeddings/status/{task_id}")
async def check_embedding_status(
    task_id: str, current_user: User = Depends(get_current_user),
    common_db: Session = Depends(get_db), rag_db: Session = Depends(get_rag_db),
):
    teacher_only(current_user)
    task = rag_db.query(rag_models.EmbeddingTask).filter(
        rag_models.EmbeddingTask.id == task_id,
        rag_models.EmbeddingTask.user_id == current_user.id).first()
    if task is None:
        raise HTTPException(404, "Object not found")
    require_document(common_db, current_user, task.document_id)
    from celery.result import AsyncResult
    result = AsyncResult(task_id, app=create_embedding_task.app)
    state = result.state
    response = {"task_id": task_id, "status": state}
    if state == "SUCCESS":
        # Only object identity and aggregate completion are exposed, never task exception/URL data.
        response["result"] = {"status": "success", "document_id": task.document_id}
    elif state == "FAILURE":
        response["message"] = "임베딩 생성 작업이 실패했습니다."
    return response


@router.post("/chat", response_model=ChatResponse)
async def api_chat_with_rag(
    request: ChatRequest, rag_db: Session = Depends(get_rag_db),
    current_user: User = Depends(get_current_user), common_db: Session = Depends(get_db),
):
    require_document(common_db, current_user, request.document_id)
    session = None
    messages = []
    if request.session_id is not None:
        session = rag_db.query(rag_models.ChatSession).filter(
            rag_models.ChatSession.id == request.session_id,
            rag_models.ChatSession.user_id == current_user.id).first()
        if session is None:
            raise HTTPException(404, "Object not found")
        if session.document_id != request.document_id:
            raise HTTPException(409, "Session document cannot be changed")
        messages = rag_db.query(rag_models.ChatMessage).filter(
            rag_models.ChatMessage.session_id == session.id).order_by(rag_models.ChatMessage.created_at).all()
    # No message/session write, collection access, or LLM call occurs before the checks above.
    if session is None:
        session = rag_models.ChatSession(id=str(uuid.uuid4()), user_id=current_user.id,
                                         document_id=request.document_id)
        rag_db.add(session)
        rag_db.commit()
    rag_db.add(rag_models.ChatMessage(session_id=session.id, role="user", content=request.question))
    rag_db.commit()
    history = [HumanMessage(content=m.content) if m.role == "user" else AIMessage(content=m.content)
               for m in messages if m.role in {"user", "ai"}]
    try:
        chain = get_rag_chain(request.document_id)
        result = await chain.ainvoke({"input": request.question, "chat_history": history})
        answer = result["answer"]
        rag_db.add(rag_models.ChatMessage(session_id=session.id, role="ai", content=answer))
        rag_db.commit()
        return ChatResponse(answer=answer, session_id=session.id)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "RAG processing unavailable") from None


@router.post("/quiz/generate", response_model=GenerateQuizResponse)
async def api_generate_quiz(
    request: GenerateQuizRequest, current_user: User = Depends(get_current_user),
    common_db: Session = Depends(get_db),
):
    teacher_only(current_user)
    require_document(common_db, current_user, request.document_id)
    try:
        questions = await generate_quiz_with_rag(request.document_id, request.num_questions)
        for index, question in enumerate(questions, start=1):
            question["question_number"] = index
            question["title"] = f"{index}번 문제"
        return GenerateQuizResponse(questions=[QuizQuestionResponse(**q) for q in questions],
                                    generated_at=datetime.utcnow())
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Quiz generation unavailable") from None


@router.post("/quiz/grade-batch", response_model=List[GradingResultResponse])
async def api_grade_quiz_batch(
    request: BatchGradingRequest, current_user: User = Depends(get_current_user),
    common_db: Session = Depends(get_db),
):
    quizzes = require_quizzes(common_db, current_user, request.material_id,
                              [answer.question_id for answer in request.student_answers])
    questions = [{"id": quiz.id, "content": quiz.content, "correct_answer": quiz.correct_answer}
                 for quiz in quizzes.values()]
    answers = [answer.model_dump() for answer in request.student_answers]
    try:
        results = await grade_quiz_answers(questions, answers)
        if len(results) != len(quizzes) or {r.get("question_id") for r in results} != set(quizzes):
            raise ValueError("Invalid grading result identifiers")
        return [GradingResultResponse(**result) for result in results]
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Grading unavailable") from None


@router.get("/chat/sessions", response_model=List[ChatSessionDto])
async def get_student_chat_sessions(
    student_id: int = Query(...), current_user: User = Depends(get_current_user),
    rag_db: Session = Depends(get_rag_db), common_db: Session = Depends(get_db),
):
    require_history_subject(common_db, current_user, student_id)
    sessions = rag_db.query(rag_models.ChatSession).filter(
        rag_models.ChatSession.user_id == student_id).order_by(rag_models.ChatSession.created_at.desc()).all()
    result = []
    for session in sessions:
        try:
            material = require_history_material(common_db, current_user, student_id, session.document_id)
        except HTTPException as error:
            if error.status_code in {400, 404}:
                continue  # Legacy/missing/revoked objects disclose no title or message preview.
            raise
        last_message = rag_db.query(rag_models.ChatMessage).filter(
            rag_models.ChatMessage.session_id == session.id).order_by(rag_models.ChatMessage.created_at.desc()).first()
        result.append(ChatSessionDto(id=session.id, document_id=session.document_id,
            material_title=material.title, session_title=session.session_title, created_at=session.created_at,
            last_message_preview=last_message.content[:50] + "..." if last_message else "대화 없음"))
    return result


@router.get("/chat/sessions/{session_id}/messages", response_model=ChatSessionDetailDto)
async def get_student_chat_session_history(
    session_id: str, student_id: int = Query(...), current_user: User = Depends(get_current_user),
    rag_db: Session = Depends(get_rag_db), common_db: Session = Depends(get_db),
):
    require_history_subject(common_db, current_user, student_id)
    session = rag_db.query(rag_models.ChatSession).filter(
        rag_models.ChatSession.id == session_id, rag_models.ChatSession.user_id == student_id).first()
    if session is None:
        raise HTTPException(404, "Object not found")
    try:
        material = require_history_material(common_db, current_user, student_id, session.document_id)
    except HTTPException as error:
        if error.status_code == 400:
            raise HTTPException(404, "Object not found") from None
        raise
    messages = rag_db.query(rag_models.ChatMessage).filter(
        rag_models.ChatMessage.session_id == session.id).order_by(rag_models.ChatMessage.created_at.asc()).all()
    return ChatSessionDetailDto(session_id=session.id, material_title=material.title, messages=messages)
