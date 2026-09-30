"""Short MySQL transactions fence delivery, execution and activation.

No broker, storage, embedding or LLM operation runs inside these transactions.
"""
from datetime import timedelta
import uuid
from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from app.common.db_session import SessionLocal as CommonSession, engine
from sqlalchemy.orm import sessionmaker
SessionLocal = (sessionmaker(bind=engine.execution_options(isolation_level="READ COMMITTED"), autoflush=False)
                if engine.dialect.name == "mysql" else CommonSession)
from app.common.models import UploadedFile, Material
from app.common.database import get_user_from_db
from app.security.authorization import (teacher_only, require_document, document_ref,
    document_json_key, require_object_url, fail_closed)
from app.indexing.models import IndexResource, IndexJob, IndexExecution
from app.indexing.source import INDEX_SPEC, INDEX_SPECS, LOCAL_INDEX_SPECS, LIVE_SPEC, normalize_source
from app.config import AI_MODE

LEASE_SECONDS = 30
MAX_DELIVERIES = 5
MAX_EXECUTIONS = 3
BATCH_JOBS = 10


def now(db):
    return db.query(func.utc_timestamp(6) if db.bind.dialect.name == 'mysql' else func.current_timestamp()).scalar()


def identity(value):
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(400, 'Invalid index job identifier') from None
    return value


def document(resource):
    return ('pdf_' if resource.resource_kind == 'PDF' else '') + str(resource.resource_id)


def current_owner(db, resource):
    user = get_user_from_db(db, resource.owner_id)
    if user is None:
        raise HTTPException(404, 'Object not found')
    teacher_only(user)
    # Lock the actual resource as well as the ledger for activation/current-owner checks.
    model = UploadedFile if resource.resource_kind == 'PDF' else Material
    db.query(model).filter(model.id == resource.resource_id).with_for_update().populate_existing().first()
    require_document(db, user, document(resource))
    return user


def _resource(db, resource_pk):
    # A preliminary hint may already live in SQLAlchemy's identity map. FOR
    # UPDATE alone locks the fresh row but does not refresh that cached object.
    return db.query(IndexResource).filter(IndexResource.id == resource_pk).with_for_update().populate_existing().one()


def _job_locked(db, job_id):
    row = db.query(IndexJob).filter(IndexJob.job_id == identity(job_id)).first()
    if row is None:
        raise HTTPException(404, 'Object not found')
    hint = db.get(IndexResource, row.resource_pk)
    if hint.resource_kind == 'MATERIAL':
        material = db.get(Material, hint.resource_id)
        if material is not None:
            db.query(UploadedFile).filter(UploadedFile.id == material.uploaded_file_id).with_for_update().first()
            db.query(Material).filter(Material.id == material.id).with_for_update().populate_existing().first()
    else:
        db.query(UploadedFile).filter(UploadedFile.id == hint.resource_id).with_for_update().populate_existing().first()
    resource = _resource(db, row.resource_pk)
    job = db.query(IndexJob).filter(IndexJob.id == row.id).with_for_update().populate_existing().one()
    return resource, job


def _is_latest(resource, job):
    return (resource.latest_job_id == job.id and resource.source_revision == job.source_revision
            and resource.current_source_hash == job.source_hash)


def _terminal(job, state, code, clock):
    job.state, job.failure_code, job.completed_at, job.updated_at = state, code, clock, clock
    job.delivery_claim_token = None
    job.delivery_deadline = None


def _permission_or_terminal(db, resource, job, clock):
    try:
        current_owner(db, resource)
    except HTTPException as error:
        if error.status_code not in (403,404):
            raise
        _terminal(job, 'REVOKED', 'RESOURCE_REVOKED', clock)
        return False
    if not _is_latest(resource, job):
        _terminal(job, 'SUPERSEDED', 'NEWER_SOURCE_REQUESTED', clock)
        return False
    return True


def view(db, resource, job):
    active = db.get(IndexExecution, resource.active_execution_id) if resource.active_execution_id else None
    active_job = db.get(IndexJob, active.job_pk) if active else None
    readable = bool(active and active.state == 'ACTIVE' and active_job
        and active_job.resource_pk == resource.id and active_job.source_revision == resource.source_revision
        and active_job.source_hash == resource.current_source_hash)
    return {'task_id': job.job_id, 'job_id': job.job_id, 'state': job.state,
        'status': {'SUCCEEDED':'SUCCESS','FAILED':'FAILURE','PROCESSING':'STARTED','QUEUED':'PENDING'}.get(job.state, job.state),
        'sourceRevision': job.source_revision, 'generation': job.execution_generation,
        'readable': readable, 'activeCurrent': bool(readable and active_job.id == resource.latest_job_id),
        'failureCode': job.failure_code,
        'retryable': job.state == 'FAILED' and job.execution_generation < MAX_EXECUTIONS
                     and job.delivery_attempts < MAX_DELIVERIES and _is_latest(resource, job)}


@fail_closed
def accept_source(user_id, document_id, expected_key, source, spec=INDEX_SPEC):
    if spec not in INDEX_SPECS:
        raise HTTPException(400, 'Unsupported index specification')
    kind, object_id = document_ref(document_id)
    kind = 'PDF' if kind == 'file' else 'MATERIAL'
    try:
        raw, digest, size = normalize_source(source, kind)
    except ValueError:
        raise HTTPException(422, 'Invalid index source') from None
    # Race on first resource insertion rolls back completely, then observes the winner.
    for retry in range(2):
        try:
            with SessionLocal.begin() as db:
                user = get_user_from_db(db, user_id)
                if user is None:
                    raise HTTPException(404, 'Object not found')
                teacher_only(user)
                obj = require_document(db, user, document_id)
                file_id = obj.id if kind == 'PDF' else obj.uploaded_file_id
                db.query(UploadedFile).filter(UploadedFile.id == file_id).with_for_update().populate_existing().one()
                if kind == 'MATERIAL':
                    material = db.query(Material).filter(Material.id == object_id).with_for_update().populate_existing().one()
                    if material.uploaded_file_id != file_id:
                        raise HTTPException(409, 'Index source changed during preparation')
                require_document(db, user, document_id)
                if document_json_key(db, document_id) != expected_key:
                    raise HTTPException(409, 'Index source changed during preparation')
                clock = now(db)
                resource = db.query(IndexResource).filter(IndexResource.resource_kind == kind,
                    IndexResource.resource_id == object_id).with_for_update().first()
                if resource is None:
                    resource = IndexResource(resource_kind=kind, resource_id=object_id, owner_id=user_id,
                        source_revision=0, current_source_hash='', request_seq=0, activation_count=0,
                        created_at=clock, updated_at=clock)
                    db.add(resource)
                    db.flush()
                if resource.owner_id != user_id:
                    raise HTTPException(404, 'Object not found')
                if resource.current_source_hash != digest:
                    resource.source_revision += 1
                    resource.current_source_hash = digest
                existing = db.query(IndexJob).filter(IndexJob.resource_pk == resource.id,
                    IndexJob.source_revision == resource.source_revision, IndexJob.index_spec == spec).first()
                if existing is not None:
                    return view(db, resource, existing)
                resource.request_seq += 1
                resource.updated_at = clock
                job = IndexJob(job_id=str(uuid.uuid4()), resource_pk=resource.id,
                    source_revision=resource.source_revision, source_hash=digest, snapshot_json=raw,
                    snapshot_bytes=size, index_spec=spec, request_seq=resource.request_seq,
                    state='QUEUED', delivery_state='PENDING', delivery_attempts=0, execution_generation=0,
                    next_delivery_at=clock, created_at=clock, updated_at=clock)
                db.add(job)
                db.flush()
                resource.latest_job_id = job.id
                return view(db, resource, job)
        except IntegrityError:
            if retry:
                raise
    raise RuntimeError('Index source transaction unavailable')


@fail_closed
def public_status(job_id, user, retry_generation=None):
    teacher_only(user)
    try:
        identity(job_id)
    except HTTPException:
        raise HTTPException(404,'Object not found') from None
    with SessionLocal.begin() as db:
        resource, job = _job_locked(db, job_id)
        if resource.owner_id != user.id:
            raise HTTPException(404, 'Object not found')
        require_document(db, user, document(resource))
        recover_one(db, resource, job, now(db))
        if retry_generation is not None:
            available = view(db, resource, job)
            if job.execution_generation != retry_generation or not available['retryable']:
                raise HTTPException(409, 'Index job cannot be retried')
            job.state, job.delivery_state, job.failure_code, job.completed_at = 'QUEUED', 'PENDING', None, None
            job.next_delivery_at = now(db)
            job.updated_at = job.next_delivery_at
        return view(db, resource, job)


def recover_one(db, resource, job, clock):
    if job.state == 'PROCESSING':
        execution = db.query(IndexExecution).filter(IndexExecution.job_pk == job.id,
            IndexExecution.generation == job.execution_generation).with_for_update().first()
        if execution is not None and execution.lease_until <= clock:
            if execution.state != 'ACTIVE':
                execution.state, execution.failure_code, execution.completed_at = 'EXPIRED', 'EXECUTION_LEASE_EXPIRED', clock
            _terminal(job, 'FAILED', 'EXECUTION_LEASE_EXPIRED', clock)
    elif job.state == 'QUEUED' and job.delivery_state in ('CLAIMED','SENT') and job.delivery_deadline and job.delivery_deadline <= clock:
        if job.delivery_attempts >= MAX_DELIVERIES:
            _terminal(job, 'FAILED', 'DELIVERY_LIMIT', clock)
        else:
            job.delivery_state, job.delivery_claim_token, job.delivery_deadline = 'PENDING', None, None
            job.next_delivery_at = clock


def claim_deliveries():
    if AI_MODE != 'LOCAL_FAKE':
        raise RuntimeError('Live jobs require the single-job manual worker')
    with SessionLocal() as db:
        ids = [row.job_id for row in db.query(IndexJob).filter(IndexJob.state.in_(('QUEUED','PROCESSING')),
            IndexJob.index_spec.in_(LOCAL_INDEX_SPECS))
            .order_by(IndexJob.next_delivery_at, IndexJob.id).limit(BATCH_JOBS).all()]
    claimed = []
    for job_id in ids:
        with SessionLocal.begin() as db:
            resource, job = _job_locked(db, job_id)
            clock = now(db)
            recover_one(db, resource, job, clock)
            if job.state != 'QUEUED' or job.delivery_state != 'PENDING' or job.next_delivery_at > clock:
                continue
            if not _permission_or_terminal(db, resource, job, clock):
                continue
            if job.delivery_attempts >= MAX_DELIVERIES:
                _terminal(job, 'FAILED', 'DELIVERY_LIMIT', clock)
                continue
            token = str(uuid.uuid4())
            job.delivery_attempts += 1
            job.delivery_state, job.delivery_claim_token = 'CLAIMED', token
            job.delivery_deadline, job.updated_at = clock + timedelta(seconds=LEASE_SECONDS), clock
            claimed.append({'job_id':job.job_id,'token':token,'snapshot_json':job.snapshot_json,
                            'generation':job.execution_generation})
    return claimed


def delivery_result(job_id, token, sent):
    with SessionLocal.begin() as db:
        _, job = _job_locked(db, job_id)
        if job.delivery_claim_token != token or job.state != 'QUEUED':
            return
        clock = now(db)
        job.delivery_claim_token = None
        job.delivery_state = 'SENT' if sent else 'PENDING'
        job.last_delivered_at = clock if sent else job.last_delivered_at
        job.next_delivery_at = clock + timedelta(seconds=2)
        job.delivery_deadline = clock + timedelta(seconds=LEASE_SECONDS) if sent else None
        job.updated_at = clock
        if not sent and job.delivery_attempts >= MAX_DELIVERIES:
            _terminal(job, 'FAILED', 'DELIVERY_LIMIT', clock)


def claim_execution(job_id, *, manual_live=False):
    with SessionLocal.begin() as db:
        resource, job = _job_locked(db, job_id)
        # Reject a misrouted message BEFORE recovery, claim, state or lease writes.
        if AI_MODE == 'LOCAL_FAKE':
            if manual_live or job.index_spec not in LOCAL_INDEX_SPECS:
                return None
        else:
            if not manual_live or job.index_spec != LIVE_SPEC:
                return None
            from app.indexing.runtime import authorize_pointer
            authorize_pointer({'resource_kind':resource.resource_kind,'resource_id':resource.resource_id,
                'user_id':resource.owner_id,'spec':job.index_spec,'source_revision':job.source_revision,
                'source_hash':job.source_hash}, 'index', 'worker')
        clock = now(db)
        recover_one(db, resource, job, clock)
        if job.state != 'QUEUED' or not _permission_or_terminal(db, resource, job, clock):
            return None
        if job.execution_generation >= MAX_EXECUTIONS:
            _terminal(job, 'FAILED', 'EXECUTION_LIMIT', clock)
            return None
        job.execution_generation += 1
        token = str(uuid.uuid4())
        candidate = 'idx_' + uuid.UUID(job.job_id).hex + '_g' + str(job.execution_generation)
        execution = IndexExecution(job_pk=job.id, generation=job.execution_generation,
            candidate_name=candidate, claim_token=token, lease_until=clock + timedelta(seconds=LEASE_SECONDS),
            state='BUILDING', embedding_calls=0, started_at=clock)
        db.add(execution)
        db.flush()
        job.state, job.updated_at, job.failure_code = 'PROCESSING', clock, None
        job.delivery_state, job.delivery_claim_token, job.delivery_deadline = 'SENT', None, None
        return {'job_id':job.job_id,'execution_id':execution.id,'token':token,
            'generation':execution.generation,'candidate':candidate, 'source_json':job.snapshot_json,
            'source_hash':job.source_hash,'source_bytes':job.snapshot_bytes,'source_revision':job.source_revision,
            'spec':job.index_spec,'resource_kind':resource.resource_kind,'resource_id':resource.resource_id,
            'user_id':resource.owner_id}


def _execution(db, ctx):
    resource, job = _job_locked(db, ctx['job_id'])
    execution = db.query(IndexExecution).filter(IndexExecution.id == ctx['execution_id']).with_for_update().one()
    clock = now(db)
    if (execution.job_pk != job.id or job.state != 'PROCESSING' or job.execution_generation != ctx['generation']
            or execution.claim_token != ctx['token'] or execution.generation != ctx['generation']
            or execution.lease_until <= clock or execution.state not in ('BUILDING','VALIDATED')):
        raise ValueError('STALE_EXECUTION')
    return resource, job, execution, clock


def execution_progress(ctx, *, embedding_call=False, chunks=None, validated=None):
    with SessionLocal.begin() as db:
        resource, job, execution, clock = _execution(db, ctx)
        if not _permission_or_terminal(db, resource, job, clock):
            return False
        if embedding_call:
            execution.embedding_calls += 1
        if chunks is not None:
            execution.expected_chunks = chunks
        if validated is not None:
            execution.actual_chunks, execution.content_digest = validated
            execution.state = 'VALIDATED'
        return True


def activate(ctx):
    with SessionLocal.begin() as db:
        resource, job, execution, clock = _execution(db, ctx)
        if execution.state != 'VALIDATED':
            raise ValueError('CANDIDATE_NOT_VALIDATED')
        if not _permission_or_terminal(db, resource, job, clock):
            execution.state, execution.completed_at = job.state, clock
            return False
        resource.active_execution_id = execution.id
        resource.activation_count += 1
        resource.updated_at = clock
        execution.state, execution.completed_at = 'ACTIVE', clock
        _terminal(job, 'SUCCEEDED', None, clock)
        from app.indexing import hooks
        if hooks.control(ctx).get('fault') == 'activation_rollback':
            raise RuntimeError('LOCAL_ACTIVATION_TRANSACTION_ROLLBACK')
        return True


def fail_execution(ctx, code):
    with SessionLocal.begin() as db:
        resource, job = _job_locked(db, ctx['job_id'])
        execution = db.query(IndexExecution).filter(IndexExecution.id == ctx['execution_id']).with_for_update().one()
        if job.state != 'PROCESSING' or job.execution_generation != ctx['generation'] or execution.state == 'ACTIVE':
            return
        clock = now(db)
        execution.state, execution.failure_code, execution.completed_at = 'FAILED', code, clock
        _terminal(job, 'FAILED', code, clock)


@fail_closed
def resolve_active(db, user, document_id):
    # Authorize BEFORE even reading index names. A returned pointer is one request's
    # immutable physical version; no fallback to legacy or another resource exists.
    authorized = require_document(db, user, document_id)
    kind, object_id = document_ref(document_id)
    kind = 'PDF' if kind == 'file' else 'MATERIAL'
    resource = db.query(IndexResource).filter(IndexResource.resource_kind == kind,
        IndexResource.resource_id == object_id).first()
    if resource is not None and resource.owner_id != (authorized.uploader_id if kind == 'PDF' else authorized.teacher_id):
        raise HTTPException(404,'Object not found')
    if resource is None or not resource.active_execution_id:
        raise HTTPException(409, {'code':'INDEX_NOT_READY'})
    execution = db.get(IndexExecution, resource.active_execution_id)
    job = db.get(IndexJob, execution.job_pk) if execution else None
    if (not job or execution.state != 'ACTIVE' or job.resource_pk != resource.id
            or job.source_revision != resource.source_revision or job.source_hash != resource.current_source_hash):
        raise HTTPException(409, {'code':'INDEX_NOT_READY'})
    pointer = {'candidate':execution.candidate_name,'source_revision':job.source_revision,
        'source_hash':job.source_hash,'spec':job.index_spec,'job_id':job.job_id,
        'resource_kind':kind,'resource_id':object_id,'generation':execution.generation,'user_id':user.id}
    db.rollback()
    db.close()
    return pointer


def receipt_context(job_id):
    with SessionLocal() as db:
        job = db.query(IndexJob).filter(IndexJob.job_id == identity(job_id)).first()
        return None if job is None else {'job_id':job.job_id, 'snapshot_json':job.snapshot_json,
                                        'generation':job.execution_generation}
