"""Celery remains real; ownership is rechecked before provider reads or writes."""
import httpx
from fastapi import HTTPException
from app.config import LOCAL_EXTERNAL_STUBS
from app.celery_config import celery_app
from app.common.db_session import SessionLocal
from app.common.database import get_user_from_db
from app.security.authorization import (
    teacher_only, require_document, require_object_url, document_json_key,
)
from app.rag.service import (
    extract_data_from_json, create_and_store_embeddings,
    extract_initial_data_from_json, create_initial_embeddings,
)


def download_json_sync(url):
    if LOCAL_EXTERNAL_STUBS:
        from app.local_providers import load_fixture_json
        return load_fixture_json(url)
    response = httpx.get(url, follow_redirects=True, timeout=60.0)
    response.raise_for_status()
    return response.json()


def authorize_job(user_id, document_id, url):
    # Legacy queued jobs lacking an owner fail closed; they are never re-owned.
    with SessionLocal() as db:
        user = get_user_from_db(db, user_id) if user_id is not None else None
        if user is None:
            raise HTTPException(404, "Object not found")
        teacher_only(user)
        require_document(db, user, document_id)
        require_object_url(url, document_json_key(db, document_id))


@celery_app.task(name="create_initial_embedding_task", bind=True, max_retries=3)
def create_initial_embedding_task(self, pdf_id: str, s3_url: str, user_id=None):
    authorize_job(user_id, f"pdf_{pdf_id}", s3_url)
    try:
        documents = extract_initial_data_from_json(download_json_sync(s3_url))
        create_initial_embeddings(pdf_id, documents)
        return {"status": "success", "external_provider": "local_stub" if LOCAL_EXTERNAL_STUBS else "configured",
                "pdf_id": pdf_id, "collection_name": f"material_pdf_{pdf_id}", "document_count": len(documents)}
    except HTTPException:
        raise
    except Exception:
        # Do not persist provider exceptions containing signed URLs in the Celery result backend.
        raise self.retry(exc=RuntimeError("Embedding provider unavailable"), countdown=60) from None


@celery_app.task(name="create_embedding_task", bind=True, max_retries=3)
def create_embedding_task(self, document_id: str, s3_url: str, user_id=None):
    authorize_job(user_id, document_id, s3_url)
    try:
        documents = extract_data_from_json(download_json_sync(s3_url))
        create_and_store_embeddings(document_id, documents)
        return {"status": "success", "external_provider": "local_stub" if LOCAL_EXTERNAL_STUBS else "configured",
                "document_id": document_id}
    except HTTPException:
        raise
    except Exception:
        raise self.retry(exc=RuntimeError("Embedding provider unavailable"), countdown=60) from None
