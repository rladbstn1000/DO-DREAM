"""SQL ledger fixtures with a mocked Chroma transport for unit tests only.

Actual Chroma/broker integration is executed separately by the guarded root runner.
"""
import copy
from unittest.mock import patch
from app.indexing import store
from app.indexing.models import IndexResource,IndexJob,IndexExecution
from app.indexing.worker import process
from app.common.db_session import SessionLocal
from app.common.models import Material,UploadedFile
from app.security.authorization import document_ref


class FakeCollection:
    def __init__(self,metadata=None):
        self.rows={}; self.metadata=metadata or {}
    def upsert(self,ids,documents,metadatas,embeddings):
        for identity,doc,meta,vector in zip(ids,documents,metadatas,embeddings):
            self.rows[identity]=(doc,copy.deepcopy(meta),list(vector))
    def count(self):return len(self.rows)
    def get(self,include=None):
        return {'ids':list(self.rows),'documents':[r[0] for r in self.rows.values()],
            'metadatas':[r[1] for r in self.rows.values()],'embeddings':[r[2] for r in self.rows.values()]}
    def query(self,query_embeddings,n_results,where,include=None):
        def matches(meta,condition):
            if '$and' in condition:return all(matches(meta,part) for part in condition['$and'])
            return all(meta.get(k)==v for k,v in condition.items())
        rows=[(key,row) for key,row in self.rows.items() if matches(row[1],where)][:n_results]
        return {'ids':[[row[0] for row in rows]],'documents':[[row[1][0] for row in rows]],
                'metadatas':[[row[1][1] for row in rows]],'distances':[[0.0 for row in rows]]}


class FakeChroma:
    def __init__(self):self.collections={}
    def create_collection(self,name,embedding_function,metadata):
        assert embedding_function is None
        if name in self.collections:raise ValueError('Duplicate candidate')
        value=FakeCollection(metadata);self.collections[name]=value;return value
    def get_collection(self,name,embedding_function):
        assert embedding_function is None
        return self.collections[name]


def enable(test):
    client=FakeChroma()
    replacement=patch('app.indexing.chroma.client',return_value=client)
    replacement.start();test.addCleanup(replacement.stop)
    return client


def clear_resources(ids):
    with SessionLocal.begin() as db:
        resources=[r.id for r in db.query(IndexResource).filter(IndexResource.resource_id.in_(ids)).all()]
        jobs=[r.id for r in db.query(IndexJob).filter(IndexJob.resource_pk.in_(resources)).all()]
        db.query(IndexExecution).filter(IndexExecution.job_pk.in_(jobs)).delete(synchronize_session=False)
        db.query(IndexJob).filter(IndexJob.id.in_(jobs)).delete(synchronize_session=False)
        db.query(IndexResource).filter(IndexResource.id.in_(resources)).delete(synchronize_session=False)


def seed_index(document_id,documents):
    kind, identity=document_ref(document_id)
    with SessionLocal() as db:
        obj=db.get(UploadedFile if kind=='file' else Material,identity)
        owner=obj.uploader_id if kind=='file' else obj.teacher_id
        file=obj if kind=='file' else db.get(UploadedFile,obj.uploaded_file_id)
        key=file.json_s3_key
    source={'chapters':[{'type':d.metadata.get('type','content'),'content':d.page_content} for d in documents]}
    job=store.accept_source(owner,document_id,key,source)
    outcome=process(job['job_id'])
    assert outcome['status']=='active',outcome
    return job
