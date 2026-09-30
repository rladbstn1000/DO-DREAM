"""Public references describe only immutable chunks actually used for an answer."""
import hashlib
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.config import APP_ENV, LOCAL_EXTERNAL_STUBS


class RuntimeMode(BaseModel):
    environment: str
    answer_provider: Literal['local_stub', 'configured_unverified']
    embedding_provider: Literal['local_hash8', 'configured_unverified']
    grading_provider: Literal['local_stub', 'configured_unverified']


def runtime_mode():
    return RuntimeMode(environment=APP_ENV,
        answer_provider='local_stub' if LOCAL_EXTERNAL_STUBS else 'configured_unverified',
        embedding_provider='local_hash8' if LOCAL_EXTERNAL_STUBS else 'configured_unverified',
        grading_provider='local_stub' if LOCAL_EXTERNAL_STUBS else 'configured_unverified')


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
