"""Actual HTTP Chroma operations. No local file/memory fallback exists."""
import hashlib
import json
import math
import struct
from fastapi import HTTPException
from app.config import LOCAL_EXTERNAL_STUBS
from app.indexing.source import DIMENSION, BATCH_SIZE


def client():
    return _http_client()


class BoundedHTTPClient:
    """Pinned SDK collections share exactly one configured HTTP transport.

    Chroma 0.6.3 Client.from_system creates new HTTP System UUIDs and therefore
    silently replaces the supplied transport. Use its actual ServerAPI and
    Collection implementations directly, without that shared-client factory.
    """
    def __init__(self, system, server):
        self._system, self._server = system, server

    def heartbeat(self):
        return self._server.heartbeat()

    def get_version(self):
        return self._server.get_version()

    def list_collections(self, limit=None, offset=None):
        return [model.name for model in self._server.list_collections(limit=limit,offset=offset)]

    def create_collection(self, *, name, embedding_function, metadata):
        if embedding_function is not None:
            raise ValueError('Only explicit index vectors are supported')
        from chromadb.api.models.Collection import Collection
        model = self._server.create_collection(name=name,metadata=metadata)
        return Collection(client=self._server,model=model,embedding_function=None)

    def get_collection(self, name, *, embedding_function):
        if embedding_function is not None:
            raise ValueError('Only explicit index vectors are supported')
        from chromadb.api.models.Collection import Collection
        model = self._server.get_collection(name=name)
        return Collection(client=self._server,model=model,embedding_function=None)

    def close(self):
        self._system.stop()
        self._server._session.close()


from functools import lru_cache
@lru_cache(maxsize=1)
def _http_client():
    # Configure the actual SDK transport before any network operation. No SDK
    # Client/AdminClient constructor may create a second timeout=None transport.
    import chromadb
    import httpx
    from chromadb.config import Settings, System
    from chromadb.api import ServerAPI
    from app.config import CHROMA_HOST, CHROMA_PORT
    if chromadb.__version__ != '0.6.3':
        raise RuntimeError('Unsupported Chroma HTTP client version')
    system = System(Settings(chroma_api_impl='chromadb.api.fastapi.FastAPI',
        chroma_server_host=CHROMA_HOST, chroma_server_http_port=CHROMA_PORT,
        anonymized_telemetry=False, allow_reset=False))
    transport = system.instance(ServerAPI)
    transport._session.timeout = httpx.Timeout(5.0, connect=2.0)
    try:
        system.start()
        return BoundedHTTPClient(system,transport)
    except Exception:
        system.stop()
        transport._session.close()
        raise


def vectors(texts):
    if not LOCAL_EXTERNAL_STUBS:
        # This specification intentionally describes the explicit local hash model.
        # Missing real configuration never silently selects it in deployment.
        raise RuntimeError('Local index specification is unavailable outside local/test')
    return [[byte / 255 for byte in hashlib.sha256(text.encode('utf-8')).digest()[:DIMENSION]] for text in texts]


def create(name, ctx):
    return client().create_collection(name=name, embedding_function=None,
        metadata={'hnsw:space':'cosine', 'job_id':ctx['job_id'], 'generation':ctx['generation'],
                  'source_hash':ctx['source_hash'], 'index_spec':ctx['spec']})


def fetch(name):
    return client().get_collection(name=name, embedding_function=None)


def float_vector(value):
    if len(value) != DIMENSION:
        raise ValueError('INVALID_VECTOR_DIMENSION')
    result = []
    for number in value:
        if isinstance(number, bool) or not isinstance(number, (int,float)) or not math.isfinite(number):
            raise ValueError('INVALID_VECTOR_VALUE')
        converted = struct.unpack('<f', struct.pack('<f', number))[0]
        if not math.isfinite(converted):
            raise ValueError('INVALID_VECTOR_VALUE')
        result.append(converted)
    return result


def upsert(collection, chunks, embeddings):
    clean = [float_vector(vector) for vector in embeddings]
    if len(chunks) != len(clean):
        raise ValueError('INVALID_VECTOR_COUNT')
    collection.upsert(ids=[chunk['id'] for chunk in chunks],
        documents=[chunk['document'] for chunk in chunks], metadatas=[chunk['metadata'] for chunk in chunks],
        embeddings=clean)


def validate(collection, chunks, expected_vectors):
    expected = {chunk['id']: (chunk, float_vector(vector)) for chunk, vector in zip(chunks, expected_vectors)}
    if len(expected) != len(chunks) or not expected:
        raise ValueError('INVALID_EXPECTED_CHUNKS')
    actual = collection.get(include=['documents','metadatas','embeddings'])
    ids = actual['ids']
    if len(set(ids)) != len(ids) or set(ids) != set(expected) or collection.count() != len(expected):
        raise ValueError('CANDIDATE_CHUNK_SET_MISMATCH')
    docs, metadata, embeddings = actual['documents'], actual['metadatas'], actual['embeddings']
    if docs is None or metadata is None or embeddings is None or not len(ids) == len(docs) == len(metadata) == len(embeddings):
        raise ValueError('CANDIDATE_SHAPE_MISMATCH')
    digest_rows = []
    for index, identity in enumerate(ids):
        chunk, vector = expected[identity]
        stored = [float(item) for item in embeddings[index]]
        if docs[index] != chunk['document'] or metadata[index] != chunk['metadata']:
            raise ValueError('CANDIDATE_CONTENT_MISMATCH')
        if float_vector(stored) != vector:
            raise ValueError('CANDIDATE_VECTOR_MISMATCH')
        digest_rows.append([identity, docs[index], metadata[index], vector])
    query = collection.query(query_embeddings=[expected_vectors[0]], n_results=1,
        where={'type':'content'}, include=['documents','metadatas','distances'])
    if (not query.get('ids') or len(query['ids'][0]) != 1 or query['ids'][0][0] not in expected
            or not query.get('metadatas') or query['metadatas'][0][0].get('type') != 'content'):
        raise ValueError('CANDIDATE_QUERY_FAILED')
    digest_rows.sort(key=lambda row: row[0])
    digest = hashlib.sha256(json.dumps(digest_rows,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return len(ids), digest


def retrieve(pointer, query, limit=5):
    try:
        collection = fetch(pointer['candidate'])
        result = collection.query(query_embeddings=vectors([query]), n_results=limit,
            where={'$and':[{'type':'content'}, {'resource_kind':pointer['resource_kind']},
                {'resource_id':str(pointer['resource_id'])}, {'source_revision':str(pointer['source_revision'])},
                {'source_hash':pointer['source_hash']}, {'index_spec':pointer['spec']}]},
            include=['documents','metadatas','distances'])
        docs, metadata = result['documents'][0], result['metadatas'][0]
        if not docs or len(docs) != len(metadata):
            raise ValueError('Active collection returned no content')
        from langchain_core.documents import Document
        return [Document(page_content=content, metadata=meta) for content, meta in zip(docs, metadata)]
    except Exception:
        raise HTTPException(503, {'code':'INDEX_STORAGE_UNAVAILABLE'}) from None
