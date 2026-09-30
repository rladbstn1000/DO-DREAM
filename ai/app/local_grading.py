"""Local-only grading fault boundary and durable synthetic call evidence.

Controls are files written by the guarded project test runner, never HTTP input.
Only accepted attempts for dedicated [GRADING LOCAL] materials can use faults.
The evidence database stores identities/times/outcomes, never answers or tokens.
"""
import asyncio
import json
from pathlib import Path
import sqlite3
import time
import uuid
from contextlib import contextmanager

from fastapi import HTTPException
from app.config import LOCAL_EXTERNAL_STUBS, LOCAL_PROVIDER_DATA_DIR

if not LOCAL_EXTERNAL_STUBS:
    raise RuntimeError("Local grading requires explicit local/test providers")

MODES = frozenset(("normal", "http_error", "missing", "duplicate", "wrong_id",
                   "wrong_type", "long_feedback", "wrong_answer"))


def _identity(value):
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise ValueError("Invalid synthetic submission identifier")
    return value


def control_path(submission_key, generation):
    _identity(submission_key)
    if type(generation) is not int or generation < 1:
        raise ValueError("Invalid synthetic generation")
    return Path(LOCAL_PROVIDER_DATA_DIR) / "grading-controls" / f"{submission_key}.{generation}.json"


@contextmanager
def _connect():
    directory = Path(LOCAL_PROVIDER_DATA_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(directory / "grading-events.sqlite3", timeout=5)
    connection.execute("""CREATE TABLE IF NOT EXISTS grading_calls (
        id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL, submission_key TEXT NOT NULL,
        generation INTEGER NOT NULL, started_at REAL NOT NULL,
        completed_at REAL, outcome TEXT NOT NULL)""")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def grading_stats(submission_key):
    """Runner-only aggregate evidence; no HTTP route exposes this function."""
    _identity(submission_key)
    with _connect() as db:
        rows = db.execute("""SELECT generation, COUNT(*),
            SUM(CASE WHEN completed_at IS NOT NULL THEN 1 ELSE 0 END),
            SUM(CASE WHEN outcome='returned' THEN 1 ELSE 0 END)
            FROM grading_calls WHERE submission_key=? GROUP BY generation ORDER BY generation""",
            (submission_key,)).fetchall()
    return [{"generation": row[0], "started": row[1], "finished": row[2],
             "returned": row[3]} for row in rows]


def _control(context):
    path = control_path(context["submission_key"], context["generation"])
    if not path.exists():
        return {"mode": "normal", "delay_seconds": 0, "gate": False}, path
    if not context["material_title"].startswith("[GRADING LOCAL]"):
        raise ValueError("Fault control requires a dedicated grading fixture")
    if path.is_symlink() or path.stat().st_size > 1024:
        raise ValueError("Invalid local grading control")
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or set(value) - {"mode", "delay_seconds", "gate"}:
        raise ValueError("Invalid local grading control")
    mode, delay, gate = value.get("mode", "normal"), value.get("delay_seconds", 0), value.get("gate", False)
    if (mode not in MODES or type(delay) not in (int, float) or not 0 <= delay <= 30
            or type(gate) is not bool):
        raise ValueError("Invalid local grading control")
    return {"mode": mode, "delay_seconds": delay, "gate": gate}, path


async def grade_snapshot(questions, answers, context):
    from app.local_providers import grade_answers
    control, path = _control(context)
    call_id = str(uuid.uuid4())
    with _connect() as db:
        db.execute("INSERT INTO grading_calls VALUES (?, ?, ?, ?, ?, NULL, 'started')",
            (call_id, context["attempt_id"], context["submission_key"], context["generation"], time.time()))
    outcome = "failed"
    try:
        await asyncio.sleep(control["delay_seconds"])
        while control["gate"] and not path.with_suffix(".release").is_file():
            await asyncio.sleep(.05)
        if control["mode"] == "http_error":
            raise HTTPException(503, "Local grading provider unavailable")
        results = grade_answers(questions, answers)
        mode = control["mode"]
        if mode == "missing":
            results = results[:-1]
        elif mode == "duplicate":
            results = results + [dict(results[0])]
        elif mode == "wrong_id":
            results[0]["question_id"] = 9223372036854775807
        elif mode == "wrong_type":
            results[0]["is_correct"] = "false"
        elif mode == "long_feedback":
            results[0]["ai_feedback"] = "x" * 2001
        elif mode == "wrong_answer":
            results[0]["student_answer"] = "synthetic altered answer"
        outcome = "returned"
        return results
    except asyncio.CancelledError:
        outcome = "cancelled"
        raise
    finally:
        with _connect() as db:
            db.execute("UPDATE grading_calls SET completed_at=?, outcome=? WHERE id=?",
                (time.time(), outcome, call_id))
