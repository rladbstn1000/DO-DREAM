"""Only durable job UUIDs enter the new trusted internal indexing queue."""
from app.celery_config import celery_app


@celery_app.task(name='dodream.indexing.process', bind=True, max_retries=0,
    acks_late=True, reject_on_worker_lost=True, ignore_result=True)
def process_index_job(self, job_id: str):
    from app.indexing.worker import process
    try:
        return process(job_id)
    except Exception:
        # MySQL is the recovery ledger; do not put SQL/provider exception bodies in broker logs.
        return {'status':'unavailable','failure_code':'INDEX_DEPENDENCY_UNAVAILABLE'}


# Old signatures are kept as explicit terminal rejection for any previously queued
# messages. Their original SQLite/index data is retained and never re-owned/deleted.
@celery_app.task(name='create_initial_embedding_task', max_retries=0)
def create_initial_embedding_task(pdf_id, s3_url, user_id=None):
    authorize_job(user_id,'pdf_'+str(pdf_id),s3_url)
    raise HTTPException(409,'Legacy indexing request is not executable')


@celery_app.task(name='create_embedding_task', max_retries=0)
def create_embedding_task(document_id, s3_url, user_id=None):
    authorize_job(user_id,document_id,s3_url)
    raise HTTPException(409,'Legacy indexing request is not executable')


from fastapi import HTTPException

def download_json_sync(url):
    raise RuntimeError('Legacy queued URL downloads are disabled')


def authorize_job(user_id, document_id, url):
    from app.common.db_session import SessionLocal
    from app.common.database import get_user_from_db
    from app.security.authorization import teacher_only,require_document,require_object_url,document_json_key
    with SessionLocal() as db:
        user=get_user_from_db(db,user_id) if user_id is not None else None
        if user is None:raise HTTPException(404,'Object not found')
        teacher_only(user)
        require_document(db,user,document_id)
        require_object_url(url,document_json_key(db,document_id))
