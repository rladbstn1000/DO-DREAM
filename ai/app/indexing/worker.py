"""One delivery can claim one generation; only its candidate is ever written."""
import copy
import httpx
from app.indexing import store, chroma, hooks
from app.indexing.source import parse_snapshot, make_chunks, BATCH_SIZE
from app.config import AI_MODE


def process(job_id, *, manual_live=False):
    receipt = store.receipt_context(job_id)
    if receipt:
        hooks.event(receipt,'worker_received')
    ctx = store.claim_execution(job_id, manual_live=manual_live)
    if ctx is None:
        if receipt:
            hooks.event(receipt,'duplicate_or_terminal_ignored')
        return {'status':'ignored'}
    hooks.event(ctx,'execution_claimed')
    try:
        controls = hooks.control(ctx)
        fault = controls.get('fault')
        source = parse_snapshot(ctx['source_json'], '0'*64 if fault == 'hash_mismatch' else ctx['source_hash'], ctx['source_bytes'])
        chunks = make_chunks(source, ctx['resource_kind'], ctx['resource_id'], ctx['source_revision'], ctx['source_hash'], ctx['spec'])
        if not store.execution_progress(ctx, chunks=len(chunks)):
            return {'status':'revoked'}
        collection = chroma.create(ctx['candidate'],ctx)
        hooks.event(ctx,'candidate_created',expected_chunks=len(chunks))
        expected_vectors = []
        batch_size = min(3 if AI_MODE == 'LIVE_OPENAI' else BATCH_SIZE,max(1,len(chunks)//2))
        for offset in range(0,len(chunks),batch_size):
            if not store.execution_progress(ctx,embedding_call=True):
                return {'status':'revoked'}
            batch = chunks[offset:offset+batch_size]
            if fault == 'embedding_failure':
                raise ValueError('EMBEDDING_FAILURE')
            batch_vectors = chroma.vectors([chunk['document'] for chunk in batch], ctx, purpose='index', role='worker')
            expected_vectors.extend(batch_vectors)
            writes = copy.deepcopy(batch)
            write_vectors = copy.deepcopy(batch_vectors)
            if fault == 'bad_dimension':
                write_vectors[0] = [1.0]
            if fault == 'bad_vector':
                write_vectors[0][0] = float('nan')
            if fault == 'bad_stored_vector':
                write_vectors[0][0] += 0.1
            if fault == 'bad_document':
                writes[0]['document'] = 'CORRUPTED_SYNTHETIC_CONTENT'
            if fault == 'foreign_metadata':
                writes[0]['metadata']['resource_id'] = '9223372036854775807'
            if fault == 'missing_chunk' and offset+len(batch) >= len(chunks):
                writes,write_vectors = writes[:-1],write_vectors[:-1]
            if fault == 'storage_timeout':
                raise httpx.ReadTimeout('Local index storage timeout')
            # Recheck the generation/lease after embedding and before every write.
            if not store.execution_progress(ctx):
                return {'status':'revoked'}
            hooks.gate(ctx,'before_write')
            if writes:
                chroma.upsert(collection,writes,write_vectors)
                if fault == 'duplicate_batch':
                    chroma.upsert(collection,writes,write_vectors)
            hooks.event(ctx,'batch_written',chunks=len(writes),upserts=(2 if fault == 'duplicate_batch' else 1) if writes else 0)
            if offset == 0:
                hooks.gate(ctx,'after_partial')
                if fault == 'partial_failure':
                    raise ValueError('PARTIAL_WRITE_FAILURE')
        if fault == 'extra_chunk':
            extra = copy.deepcopy(chunks[0]);extra['id']='f'*64
            chroma.upsert(collection,[extra],[expected_vectors[0]])
        if not store.execution_progress(ctx):
            return {'status':'revoked'}
        validated = chroma.validate(collection,chunks,expected_vectors)
        if not store.execution_progress(ctx,validated=validated):
            return {'status':'revoked'}
        hooks.gate(ctx,'before_activation')
        active = store.activate(ctx)
        if active:
            hooks.event(ctx,'activation_committed',chunks=validated[0])
            hooks.gate(ctx,'after_activation')
        else:
            hooks.event(ctx,'activation_rejected')
        return {'status':'active' if active else 'superseded'}
    except Exception as error:
        # No raw source, collection transport response, token or URL enters Celery.
        if isinstance(error,httpx.TimeoutException):
            code='INDEX_STORAGE_TIMEOUT'
        elif isinstance(error,ValueError):
            known = str(error)
            code = known if known in {'EMPTY_SOURCE','STALE_EXECUTION','EMBEDDING_FAILURE',
                'INVALID_VECTOR_DIMENSION','INVALID_VECTOR_VALUE','CANDIDATE_CHUNK_SET_MISMATCH',
                'CANDIDATE_CONTENT_MISMATCH','CANDIDATE_VECTOR_MISMATCH','CANDIDATE_QUERY_FAILED',
                'PARTIAL_WRITE_FAILURE'} else 'INDEX_VALIDATION_FAILED'
        else:
            code='INDEX_EXECUTION_UNAVAILABLE'
        store.fail_execution(ctx,code)
        hooks.event(ctx,'execution_failed')
        return {'status':'failed','failure_code':code}
