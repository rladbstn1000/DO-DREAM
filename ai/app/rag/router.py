from datetime import datetime
import asyncio
import json
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
from app.rag.models import ChatSessionDetailDto, ChatSessionDto, ChatMessageDto
from app.rag.provenance import SourceReference, RuntimeMode, runtime_mode, source_references
from app.rag.quiz_service import generate_quiz_with_rag, grade_quiz_answers
from app.rag.grading_contract import (BatchGradingRequest, GradingResultResponse,
    load_grading_snapshot, validate_results, GRADING_TIMEOUT_SECONDS)
from app.security.auth import get_current_user
from app.security.models import User
from app.security.authorization import (
    teacher_only, require_document, require_file, require_object_url, document_json_key,
    require_history_subject, require_history_material, require_quizzes, document_ref,
)
from app.common.db_session import get_db, SessionLocal
from app.common.database import get_user_from_db
from app.indexing import store as index_store
from app.indexing.source import INDEX_SPEC
from app.rag.service import download_json_from_cloudfront
from app.config import AI_MODE


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InitialEmbeddingRequest(RequestModel):
    pdf_id: StrictInt = Field(gt=0, le=9223372036854775807)
    s3_url: HttpUrl
    index_spec: str = INDEX_SPEC


class EmbeddingRequest(RequestModel):
    document_id: str
    s3_url: HttpUrl
    index_spec: str = INDEX_SPEC


class ChatRequest(RequestModel):
    document_id: str
    question: str = Field(min_length=1,max_length=4000)
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    session_id: str
    message_id: int
    document_id: str
    source_revision: int
    source_hash: str
    sources: List[SourceReference]
    mode: RuntimeMode
    cited_source_ids: Optional[List[str]] = None
    abstained: Optional[bool] = None
    retrieval_variant: Optional[str] = None
    stage_latency_ms: Optional[dict[str,float]] = None


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


router = APIRouter(prefix="/rag", tags=["RAG"])


@router.get('/mode',response_model=RuntimeMode)
def get_runtime_mode(current_user: User = Depends(get_current_user)):
    return runtime_mode()


async def accept_embedding(request, current_user, common_db, document_id):
    teacher_only(current_user)
    require_document(common_db, current_user, document_id)
    key = document_json_key(common_db, document_id)
    url = require_object_url(request.s3_url, key)
    # Auth and object binding precede storage; no common DB connection waits on it.
    common_db.rollback()
    common_db.close()
    source = await download_json_from_cloudfront(url)
    status = index_store.accept_source(current_user.id, document_id, key, source, request.index_spec)
    return {**status, 'document_id':document_id,
        'check_status_url':'/rag/embeddings/status/'+status['job_id']}


@router.post('/embeddings/create-initial', status_code=202)
async def api_create_initial_embedding(request: InitialEmbeddingRequest,
    current_user: User = Depends(get_current_user), common_db: Session = Depends(get_db)):
    return await accept_embedding(request,current_user,common_db,'pdf_'+str(request.pdf_id))


@router.post('/embeddings/create', status_code=202)
async def api_create_embedding(request: EmbeddingRequest,
    current_user: User = Depends(get_current_user), common_db: Session = Depends(get_db)):
    teacher_only(current_user)
    if document_ref(request.document_id)[0] != 'material':
        raise HTTPException(400,'Expected a material identifier')
    return await accept_embedding(request,current_user,common_db,request.document_id)


@router.get('/embeddings/status/{task_id}')
async def check_embedding_status(task_id: str, current_user: User = Depends(get_current_user)):
    return index_store.public_status(task_id,current_user)


class RetryIndexRequest(RequestModel):
    expected_generation: StrictInt = Field(ge=0,le=3)


@router.post('/embeddings/retry/{task_id}',status_code=202)
async def retry_embedding(task_id: str, request: RetryIndexRequest,
                          current_user: User = Depends(get_current_user)):
    return index_store.public_status(task_id,current_user,request.expected_generation)


@router.post("/chat", response_model=ChatResponse)
async def api_chat_with_rag(
    request: ChatRequest, rag_db: Session = Depends(get_rag_db),
    current_user: User = Depends(get_current_user), common_db: Session = Depends(get_db),
):
    material = require_document(common_db, current_user, request.document_id)
    material_title = getattr(material,'title',None)
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
    pointer = index_store.resolve_active(common_db,current_user,request.document_id)
    from app.indexing.runtime import authorize_pointer
    try:
        authorize_pointer(pointer,'query')
    except (ValueError, RuntimeError):
        raise HTTPException(503, {'code':'AI_SCOPE_NOT_AUTHORIZED'}) from None
    if session is not None:
        version = rag_db.get(rag_models.ChatSessionIndex,session.id)
        if version is None or version.source_revision != pointer['source_revision'] or version.source_hash != pointer['source_hash']:
            raise HTTPException(409,{'code':'RAG_SOURCE_CHANGED'})
    # Authorization, active version and session version all precede any write.
    if session is None:
        session = rag_models.ChatSession(id=str(uuid.uuid4()), user_id=current_user.id,
                                         document_id=request.document_id)
        rag_db.add(session)
        rag_db.add(rag_models.ChatSessionIndex(session_id=session.id,
            source_revision=pointer['source_revision'],source_hash=pointer['source_hash']))
        rag_db.commit()
    rag_db.add(rag_models.ChatMessage(session_id=session.id, role="user", content=request.question))
    rag_db.commit()
    history = [HumanMessage(content=m.content) if m.role == "user" else AIMessage(content=m.content)
               for m in messages if m.role in {"user", "ai"}]
    try:
        chain = get_rag_chain(pointer)
        result = await asyncio.wait_for(chain.ainvoke({"input": request.question, "chat_history": history}),
            timeout=28 if AI_MODE == 'LIVE_OPENAI' else 15)
        answer = result["answer"]
        if not isinstance(answer,str) or not answer.strip():
            raise ValueError('Answer provider returned invalid text')
        sources=source_references(pointer,result.get('context'),material_title)
        mode=runtime_mode(pointer['spec'])
        # Provider waiting must not retain a previous permission grant. Resolve
        # current authority in a new DB session, never the closed/expired one.
        revalidate_answer_source(current_user.id,request.document_id,pointer)
        message=rag_models.ChatMessage(session_id=session.id, role="ai", content=answer)
        rag_db.add(message)
        rag_db.flush()
        rag_db.add(rag_models.ChatMessageSources(message_id=message.id,
            sources_json=json.dumps([source.model_dump() for source in sources],ensure_ascii=False),
            mode_json=mode.model_dump_json()))
        rag_db.commit()
        return ChatResponse(answer=answer,session_id=session.id,message_id=message.id,
            document_id=request.document_id,source_revision=pointer['source_revision'],
            source_hash=pointer['source_hash'],sources=sources,mode=mode,
            cited_source_ids=result.get('cited_source_ids'),abstained=result.get('abstained'),
            retrieval_variant=result.get('variant'),stage_latency_ms=result.get('stage_latency_ms'))
    except HTTPException:
        rag_db.rollback()
        raise
    except Exception:
        rag_db.rollback()
        raise HTTPException(503, "RAG processing unavailable") from None


def revalidate_answer_source(user_id,document_id,selected):
    with SessionLocal() as fresh_db:
        principal=get_user_from_db(fresh_db,user_id)
        if principal is None:raise HTTPException(404,'Object not found')
        try:
            current=index_store.resolve_active(fresh_db,principal,document_id)
        except HTTPException as error:
            if error.status_code==409:
                raise HTTPException(409,{'code':'RAG_SOURCE_CHANGED'}) from None
            raise
    # A same-source spec/candidate replacement is safe. Do not switch the answer
    # to that candidate or run retrieval again after the model used selected.
    if any(current[key]!=selected[key] for key in ('resource_kind','resource_id','source_revision','source_hash')):
        raise HTTPException(409,{'code':'RAG_SOURCE_CHANGED'})


@router.post("/quiz/generate", response_model=GenerateQuizResponse)
async def api_generate_quiz(
    request: GenerateQuizRequest, current_user: User = Depends(get_current_user),
    common_db: Session = Depends(get_db),
):
    teacher_only(current_user)
    require_document(common_db, current_user, request.document_id)
    pointer = index_store.resolve_active(common_db,current_user,request.document_id)
    try:
        questions = await generate_quiz_with_rag(request.document_id, request.num_questions, pointer=pointer)
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
    questions, answers, context = load_grading_snapshot(common_db, current_user, request)
    try:
        results = await asyncio.wait_for(grade_quiz_answers(questions, answers, execution=context),
                                         timeout=GRADING_TIMEOUT_SECONDS)
    except HTTPException:
        raise
    except Exception:
        # A dispatched provider timeout/exception leaves its work outcome unknown.
        raise HTTPException(504, "Grading outcome unknown") from None
    try:
        return validate_results(results, answers)
    except (ValueError, TypeError):
        raise HTTPException(502, "Invalid grading provider response") from None


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
    messages = (rag_db.query(rag_models.ChatMessage, rag_models.ChatMessageSources)
        .outerjoin(rag_models.ChatMessageSources,
                   rag_models.ChatMessageSources.message_id == rag_models.ChatMessage.id)
        .filter(rag_models.ChatMessage.session_id == session.id)
        .order_by(rag_models.ChatMessage.created_at.asc(), rag_models.ChatMessage.id.asc()).all())
    version=rag_db.get(rag_models.ChatSessionIndex,session.id)
    return ChatSessionDetailDto(session_id=session.id,document_id=session.document_id,
        material_title=material.title,source_revision=version.source_revision if version else None,
        source_hash=version.source_hash if version else None,
        messages=[message_dto(message, record) for message, record in messages])


def message_with_sources(rag_db,message):
    record=rag_db.get(rag_models.ChatMessageSources,message.id)
    return message_dto(message, record)


def message_dto(message, record):
    return ChatMessageDto(id=message.id,role=message.role,content=message.content,created_at=message.created_at,
        sources=[SourceReference.model_validate(value) for value in json.loads(record.sources_json)] if record else [],
        mode=RuntimeMode.model_validate_json(record.mode_json) if record else None)


@router.get('/chat/sessions/{session_id}/messages/{message_id}/sources/{source_index}',response_model=SourceReference)
def get_chat_source(session_id: str,message_id: int,source_index: int,student_id: int = Query(...),
    current_user: User = Depends(get_current_user),rag_db: Session = Depends(get_rag_db),
    common_db: Session = Depends(get_db)):
    require_history_subject(common_db,current_user,student_id)
    session=rag_db.query(rag_models.ChatSession).filter(rag_models.ChatSession.id==session_id,
        rag_models.ChatSession.user_id==student_id).first()
    if session is None:raise HTTPException(404,'Object not found')
    require_history_material(common_db,current_user,student_id,session.document_id)
    message=rag_db.query(rag_models.ChatMessage).filter(rag_models.ChatMessage.id==message_id,
        rag_models.ChatMessage.session_id==session.id,rag_models.ChatMessage.role=='ai').first()
    if message is None:raise HTTPException(404,'Object not found')
    pointer=index_store.resolve_active(common_db,current_user,session.document_id)
    version=rag_db.get(rag_models.ChatSessionIndex,session.id)
    if version is None or version.source_revision!=pointer['source_revision'] or version.source_hash!=pointer['source_hash']:
        raise HTTPException(409,{'code':'RAG_SOURCE_CHANGED'})
    sources=message_with_sources(rag_db,message).sources
    if source_index<0 or source_index>=len(sources):raise HTTPException(404,'Object not found')
    source=sources[source_index]
    if source.document_id!=session.document_id or source.source_revision!=version.source_revision or source.source_hash!=version.source_hash:
        raise HTTPException(409,{'code':'RAG_SOURCE_CHANGED'})
    return source
