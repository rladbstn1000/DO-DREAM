from celery import Celery
from app.config import CELERY_BROKER_URL

celery_app = Celery('dodream_rag_worker',broker=CELERY_BROKER_URL,
    backend=CELERY_BROKER_URL,include=['app.rag.tasks'])
celery_app.conf.update(
    task_default_queue='indexing-v3',
    task_routes={'dodream.indexing.process':{'queue':'indexing-v3'}},
    task_track_started=True, broker_connection_retry_on_startup=True,
    broker_connection_timeout=2, broker_transport_options={'visibility_timeout':60,'socket_timeout':3,'socket_connect_timeout':2},
    result_backend_transport_options={'visibility_timeout':60}, visibility_timeout=60,
    worker_prefetch_multiplier=1, task_acks_late=True, task_reject_on_worker_lost=True,
    task_acks_on_failure_or_timeout=True, task_publish_retry=False,
    task_soft_time_limit=50, task_time_limit=55, result_expires=3600,
)
if __name__ == '__main__':
    celery_app.start()
