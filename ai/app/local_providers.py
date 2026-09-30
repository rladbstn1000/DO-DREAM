"""Explicit, network-free external-provider doubles for local/test only.

These are deterministic contract fixtures, not an AI or retrieval-quality evaluation.
The existing routers, JWT verification, shared users DB and Celery worker remain real.
"""
import hashlib
import json
from pathlib import Path
import sqlite3
import re
import uuid
from urllib.parse import urlsplit, unquote
from langchain_core.documents import Document
from fastapi import HTTPException
from app.config import LOCAL_EXTERNAL_STUBS, LOCAL_PROVIDER_DATA_DIR, LOCAL_OBJECT_STORAGE_DIR

if not LOCAL_EXTERNAL_STUBS:
    raise RuntimeError("Local providers require LOCAL_EXTERNAL_STUBS=true in local/test")

MARKER = "[LOCAL STUB: 실제 AI 아님]"
FIXTURE_BASE = "https://local-fixture.invalid/"
SAMPLE_CONTENT = "이 자료는 로컬 실행 검증을 위한 합성 학습 자료입니다. 물은 수소와 산소로 구성됩니다."


def load_fixture_json(url):
    if url not in (FIXTURE_BASE + "sample.json", FIXTURE_BASE + "local/synthetic/lesson.json"):
        parsed = urlsplit(url)
        key = unquote(parsed.path.lstrip("/"))
        indexing_key = (parsed.path == '/' + key and re.fullmatch(
            r"local/synthetic/indexing/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.json", key))
        if (parsed.scheme != "https" or parsed.netloc != "local-fixture.invalid" or parsed.query or parsed.fragment
                or not (indexing_key or re.fullmatch(r"local/synthetic/authz/[A-Za-z0-9/_-]+\.json", key))):
            raise ValueError("Local storage accepts only authorized synthetic object keys; network denied")
        path = Path(LOCAL_OBJECT_STORAGE_DIR) / (hashlib.sha256(key.encode()).hexdigest() + ".json")
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 10 * 1024 * 1024:
            raise ValueError("Synthetic object unavailable")
        data = json.loads(path.read_text())
        if not isinstance(data, dict):
            raise ValueError("Invalid synthetic object")
        return data
    return {
        "external_provider": "local_stub",
        "chapters": [{"id": "local-1", "title": "로컬 합성 과학", "type": "content", "content": SAMPLE_CONTENT}],
        "parsedData": {"indexes": ["01 로컬 합성 과학"], "data": [{"index": "01", "index_title": "로컬 합성 과학", "titles": [{"title": "물의 구성", "s_titles": [{"s_title": "합성 내용", "contents": SAMPLE_CONTENT, "ss_titles": []}]}], "concept_checks": []}]},
    }


def write_fixture_pdf(url, path):
    if url == FIXTURE_BASE + 'sample.pdf':
        Path(path).write_bytes(b'%PDF-1.4\n% DO-DREAM LOCAL SYNTHETIC FIXTURE\n%%EOF\n')
        return
    parsed = urlsplit(url)
    key = parsed.path.lstrip('/')
    match = re.fullmatch(r'local/synthetic/indexing-pdf/([0-9a-f-]{36})\.pdf',key)
    if (parsed.scheme != 'https' or parsed.netloc != 'local-fixture.invalid' or parsed.query or parsed.fragment
            or not match or str(uuid.UUID(match.group(1))) != match.group(1)):
        raise HTTPException(400,'Local storage accepts only bound synthetic PDF objects')
    source = Path(LOCAL_OBJECT_STORAGE_DIR)/(hashlib.sha256(key.encode()).hexdigest()+'.pdf')
    if source.is_symlink() or not source.is_file() or source.stat().st_size > 10*1024*1024:
        raise HTTPException(404,'Synthetic PDF unavailable')
    data = source.read_bytes()
    if b'DO-DREAM LOCAL SYNTHETIC FIXTURE' not in data:
        raise HTTPException(400,'Synthetic PDF marker missing')
    Path(path).write_bytes(data+b'\n% INDEX LOCAL INITIAL\n')


def parse_pdf(path):
    if b"DO-DREAM LOCAL SYNTHETIC FIXTURE" not in Path(path).read_bytes():
        raise ValueError("Local PDF provider accepts only its synthetic fixture")
    if b'INDEX LOCAL INITIAL' in Path(path).read_bytes():
        return {'external_provider':'local_stub','indexes':['01 Synthetic initial'],
            'data':[{'index':'01','index_title':'Synthetic initial','titles':[{'title':'Synthetic lesson',
                's_titles':[{'s_title':'First','contents':'[INDEX LOCAL] Initial synthetic content one. '+('Water learning text. '*100),'ss_titles':[]},
                            {'s_title':'Second','contents':'[INDEX LOCAL] Initial synthetic content two. '+('Safe science text. '*100),'ss_titles':[]}]}],
                'concept_checks':[]}]}
    data = load_fixture_json(FIXTURE_BASE + "sample.json")["parsedData"]
    return {"external_provider": "local_stub", **data}


def process_concept_checks(items):
    return {"external_provider": "local_stub", "processed_concept_checks": [
        {"title": MARKER, "questions": [{"question": item.get("contents", ""), "answer": item.get("answer", "")}]} for item in items
    ]}


class LocalEmbeddings:
    """Small deterministic hash vectors; no trained model and no network."""
    def embed_documents(self, texts):
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text):
        return [byte / 255 for byte in hashlib.sha256(text.encode()).digest()[:8]]


class LocalVectorStore:
    """SQLite-backed stand-in for the Chroma persistence/embedding boundary."""
    def __init__(self, *, collection_name, **kwargs):
        self.name = collection_name
        directory = Path(LOCAL_PROVIDER_DATA_DIR)
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "vectors.sqlite3"
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS chunks (collection TEXT NOT NULL, content TEXT NOT NULL, metadata TEXT NOT NULL, vector TEXT NOT NULL)")

    def connect(self):
        return sqlite3.connect(self.path, timeout=30)

    def delete_collection(self):
        with self.connect() as db:
            db.execute("DELETE FROM chunks WHERE collection = ?", (self.name,))

    @classmethod
    def from_documents(cls, *, documents, embedding, collection_name, **kwargs):
        store = cls(collection_name=collection_name)
        vectors = embedding.embed_documents([doc.page_content for doc in documents])
        with store.connect() as db:
            db.executemany("INSERT INTO chunks VALUES (?, ?, ?, ?)", [
                (collection_name, doc.page_content, json.dumps(doc.metadata, ensure_ascii=False), json.dumps(vector))
                for doc, vector in zip(documents, vectors)
            ])
        return store

    def similarity_search(self, query, k=5, filter=None):
        # Stable fixture ordering, deliberately not presented as semantic retrieval.
        with self.connect() as db:
            rows = db.execute("SELECT content, metadata FROM chunks WHERE collection = ? ORDER BY rowid", (self.name,)).fetchall()
        documents = [Document(page_content=content, metadata=json.loads(metadata)) for content, metadata in rows]
        if filter is not None:
            documents = [doc for doc in documents if all(doc.metadata.get(key) == value for key, value in filter.items())]
        return documents[:k]


class LocalRagChain:
    def __init__(self, collection):
        self.store = LocalVectorStore(collection_name=collection)
        if not self.store.similarity_search("", k=1, filter={"type": "content"}):
            raise ValueError("No local embedding fixture exists for this document")

    async def ainvoke(self, request):
        docs = self.store.similarity_search(request["input"], k=1, filter={"type": "content"})
        if not docs:
            raise ValueError("Local collection is empty")
        return {"answer": f"{MARKER} {docs[0].page_content[:300]}"}


def generate_quiz(collection, num_questions):
    docs = LocalVectorStore(collection_name=collection).similarity_search("", k=1)
    if not docs:
        raise ValueError("No local embedding fixture exists for this document")
    return [{"question_type": "SHORT_ANSWER", "content": f"{MARKER} 물을 구성하는 두 원소는?", "correct_answer": "수소와 산소", "chapter_reference": docs[0].metadata.get("title", "local fixture")} for _ in range(num_questions)]


def grade_answers(questions, student_answers):
    question_map = {str(q["id"]): q for q in questions}
    results = []
    for answer in student_answers:
        question = question_map.get(str(answer["question_id"]))
        if question is None:
            raise ValueError("Unknown local grading question")
        correct = answer["student_answer"].strip() == question["correct_answer"].strip()
        results.append({"question_id": answer["question_id"], "student_answer": answer["student_answer"], "is_correct": correct, "ai_feedback": f"{MARKER} 문자열 일치 비교: {'일치' if correct else '불일치'}"})
    return results
