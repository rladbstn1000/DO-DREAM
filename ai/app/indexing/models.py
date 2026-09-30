"""Mappings for additive V004; only indexing writes these three ledger tables."""
from sqlalchemy import Column, Integer, BigInteger, String, Text, DateTime, ForeignKey, UniqueConstraint
from app.common.db_session import Base

ID = BigInteger().with_variant(Integer, 'sqlite')


class IndexResource(Base):
    __tablename__ = 'index_resources'
    __table_args__ = (UniqueConstraint('resource_kind', 'resource_id'),)
    id = Column(ID, primary_key=True, autoincrement=True)
    resource_kind = Column(String(16), nullable=False)
    resource_id = Column(BigInteger, nullable=False)
    owner_id = Column(BigInteger, nullable=False)
    source_revision = Column(BigInteger, nullable=False, default=0)
    current_source_hash = Column(String(64), nullable=False)
    request_seq = Column(BigInteger, nullable=False, default=0)
    latest_job_id = Column(BigInteger)
    active_execution_id = Column(BigInteger)
    activation_count = Column(BigInteger, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)


class IndexJob(Base):
    __tablename__ = 'index_jobs'
    __table_args__ = (UniqueConstraint('resource_pk', 'source_revision', 'index_spec'),)
    id = Column(ID, primary_key=True, autoincrement=True)
    job_id = Column(String(36), nullable=False, unique=True)
    resource_pk = Column(BigInteger, ForeignKey('index_resources.id'), nullable=False)
    source_revision = Column(BigInteger, nullable=False)
    source_hash = Column(String(64), nullable=False)
    snapshot_json = Column(Text, nullable=False)
    snapshot_bytes = Column(Integer, nullable=False)
    index_spec = Column(String(64), nullable=False)
    request_seq = Column(BigInteger, nullable=False)
    state = Column(String(20), nullable=False)
    delivery_state = Column(String(16), nullable=False, default='PENDING')
    delivery_attempts = Column(Integer, nullable=False, default=0)
    delivery_claim_token = Column(String(36))
    delivery_deadline = Column(DateTime)
    next_delivery_at = Column(DateTime, nullable=False)
    last_delivered_at = Column(DateTime)
    execution_generation = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime)
    failure_code = Column(String(64))


class IndexExecution(Base):
    __tablename__ = 'index_executions'
    __table_args__ = (UniqueConstraint('job_pk', 'generation'),)
    id = Column(ID, primary_key=True, autoincrement=True)
    job_pk = Column(BigInteger, ForeignKey('index_jobs.id'), nullable=False)
    generation = Column(Integer, nullable=False)
    candidate_name = Column(String(100), nullable=False, unique=True)
    claim_token = Column(String(36), nullable=False)
    lease_until = Column(DateTime, nullable=False)
    state = Column(String(20), nullable=False)
    expected_chunks = Column(Integer)
    actual_chunks = Column(Integer)
    content_digest = Column(String(64))
    embedding_calls = Column(Integer, nullable=False, default=0)
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime)
    failure_code = Column(String(64))
