"""Synthetic contracts against only this CI run's real internal services."""
import os
import signal
import uuid

import chromadb
from chromadb.config import Settings
import pymysql
import redis


def main():
    with pymysql.connect(host="mysql", user="dodream_ci", password=os.environ["CI_MYSQL_PASSWORD"],
                         database="dodream_ci", connect_timeout=5, read_timeout=5, write_timeout=5) as db:
        with db.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() "
                           "AND table_name IN ('grading_attempts','grading_attempt_items',"
                           "'grading_attempt_results','index_resources','index_jobs','index_executions')")
            assert cursor.fetchone()[0] == 6, "CI_MYSQL_LEDGER_TABLES"
            cursor.execute("SELECT COUNT(*) FROM information_schema.table_constraints WHERE table_schema=DATABASE() "
                           "AND constraint_name IN ('ck_index_job_snapshot','fk_grading_result_item','uq_index_resource')")
            assert cursor.fetchone()[0] == 3, "CI_MYSQL_LEDGER_CONSTRAINTS"
    cache = redis.Redis(host="redis", socket_timeout=3, socket_connect_timeout=3)
    key = "ci-probe:" + str(uuid.uuid4())
    assert cache.set(key, "first", nx=True, ex=60)
    assert not cache.set(key, "second", nx=True, ex=60)
    assert cache.get(key) == b"first", "CI_REDIS_ATOMIC_KEY"
    client = chromadb.HttpClient(host="chroma", port=8000, settings=Settings(anonymized_telemetry=False))
    collection = client.create_collection("ci-probe-" + uuid.uuid4().hex, embedding_function=None)
    collection.add(ids=["synthetic-a", "synthetic-b"], embeddings=[[1.0, 0.0], [0.0, 1.0]],
                   documents=["CI public synthetic first chunk", "CI public synthetic second chunk"],
                   metadatas=[{"position": 0}, {"position": 1}])
    result = collection.query(query_embeddings=[[1.0, 0.0]], n_results=1, include=["metadatas", "distances"])
    assert collection.count() == 2 and result["ids"] == [["synthetic-a"]], "CI_CHROMA_QUERY"
    assert result["metadatas"][0][0]["position"] == 0, "CI_CHROMA_METADATA"
    print("PASS: real fresh MySQL constraints, Redis SET NX, Chroma explicit-vector round trip")


if __name__ == "__main__":
    def deadline(_signal, _frame):
        raise TimeoutError("CI_SERVICE_PROBE_DEADLINE")

    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(45)
    try:
        main()
    finally:
        signal.alarm(0)
