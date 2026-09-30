"""Bounded durable-outbox polling: python -m app.indexing.dispatcher."""
import time
from app.indexing import store,hooks


def dispatch_once():
    from app.config import AI_MODE
    if AI_MODE != 'LOCAL_FAKE':
        raise RuntimeError('Live dispatch is manual only')
    from app.celery_config import celery_app
    claimed = store.claim_deliveries()
    for row in claimed:
        try:
            hooks.event(row,'delivery_attempted')
            celery_app.send_task('dodream.indexing.process',kwargs={'job_id':row['job_id']},
                queue='indexing-v3', retry=False, ignore_result=True)
            hooks.event(row,'broker_send_returned')
            hooks.gate(row,'after_send')
            store.delivery_result(row['job_id'],row['token'],True)
        except Exception:
            # A crash after send leaves the lease in CLAIMED. A transport error can
            # also mean the broker accepted it; duplicate delivery is intentionally safe.
            store.delivery_result(row['job_id'],row['token'],False)
            hooks.event(row,'delivery_unconfirmed')
    return len(claimed)


def main():
    while True:
        try:
            dispatch_once()
        except Exception:
            print('Index dispatcher dependency unavailable',flush=True)
        time.sleep(1)


if __name__ == '__main__':
    main()
