"""Public references describe only immutable chunks actually used for an answer."""
import hashlib
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.config import APP_ENV, AI_MODE


class RuntimeMode(BaseModel):
    environment: str
    answer_provider: Literal['local_stub', 'configured_unverified', 'live_openai']
    embedding_provider: Literal['local_hash8', 'configured_unverified', 'live_openai']
    grading_provider: Literal['local_stub', 'configured_unverified', 'live_openai']
    configured_mode: Optional[Literal['LOCAL_FAKE','LIVE_OPENAI']] = None
    embedding_model: Optional[str] = None
    answer_model: Optional[str] = None
    grading_model: Optional[str] = None
    index_spec: Optional[str] = None
    real_ai_verified: bool = False


def runtime_mode(index_spec=None):
    from app.indexing.source import INDEX_SPEC, LIVE_SPEC
    local = AI_MODE == 'LOCAL_FAKE'
    return RuntimeMode(environment=APP_ENV,configured_mode=AI_MODE,
        answer_provider='local_stub' if local else 'live_openai',
        embedding_provider='local_hash8' if local else 'live_openai',
        grading_provider='local_stub' if local else 'live_openai',
        embedding_model='sha256-hash8' if local else 'text-embedding-3-small',
        answer_model='local-deterministic' if local else 'gpt-4.1-mini-2025-04-14',
        grading_model='local-deterministic' if local else 'gpt-4.1-mini-2025-04-14',
        index_spec=index_spec or (INDEX_SPEC if local else LIVE_SPEC))


class SourceReference(BaseModel):
    model_config = ConfigDict(extra='forbid')
    document_id: str
    source_revision: int = Field(gt=0)
    source_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    chunk_position: int = Field(ge=0, lt=500)
    content_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    material_title: Optional[str] = None
    excerpt: str = Field(min_length=1, max_length=300)


def source_references(pointer, documents, material_title):
    """No invented page/section IDs or exposure of candidate names/raw metadata."""
    if not isinstance(documents, list) or not 1 <= len(documents) <= 5:
        raise ValueError('Missing answer input provenance')
    result=[]
    seen=set()
    for document in documents:
        meta=document.metadata
        expected={'type':'content','resource_kind':pointer['resource_kind'],
            'resource_id':str(pointer['resource_id']),'source_revision':str(pointer['source_revision']),
            'source_hash':pointer['source_hash'],'index_spec':pointer['spec']}
        position=meta.get('position')
        content=document.page_content
        if (any(meta.get(k)!=v for k,v in expected.items()) or type(position) is not int
                or not isinstance(content,str) or not content
                or meta.get('content_hash')!=hashlib.sha256(content.encode('utf-8')).hexdigest()
                or position in seen):
            raise ValueError('Answer input provenance does not match selected source')
        seen.add(position)
        document_id=('pdf_' if pointer['resource_kind']=='PDF' else '')+str(pointer['resource_id'])
        result.append(SourceReference(document_id=document_id,source_revision=pointer['source_revision'],
            source_hash=pointer['source_hash'],chunk_position=position,content_hash=meta['content_hash'],
            material_title=material_title,excerpt=content[:300]))
    return result
