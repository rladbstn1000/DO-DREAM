#!/usr/bin/env python3
"""3-A real HTTP/MySQL grading checks; only dedicated new synthetic fixture rows.

Every container operation uses the existing fixed-project scope gate. Provider
faults are local files, never auth/DB/server replacements. Outputs contain checks
and aggregate execution/commit counts, never tokens, answers or request bodies.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import copy
import json
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

from manage import RESULTS, compose_args, clean_env
from scope_guard import ScopeError
from verify import BASE, ENV, CHECKS, NoRedirect, check as base_check, req, payload, sql, docker_exec

RUN_STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
SCENARIOS = ("sequential", "concurrent", "actual_database_constraints", "snapshots", "failures",
             "atomic_and_fence", "authorization", "statistics_and_legacy", "lost_response_and_transaction",
             "independent_query_during_provider", "restart_windows")


def progress(row):
    with (RESULTS / ("grading-progress-" + RUN_STAMP + ".jsonl")).open("a") as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def check(name, passed, detail=""):
    base_check(name, passed, detail)
    progress(CHECKS[-1])


class PrerequisiteFailure(RuntimeError):
    pass


class RunnerInterrupted(RuntimeError):
    pass


def record_error(name, error):
    environment = isinstance(error, (RunnerInterrupted, ScopeError, subprocess.TimeoutExpired,
        urllib.error.URLError, TimeoutError, ConnectionError))
    state = "BLOCKED" if environment else "FAIL"
    CHECKS.append({"name": name, "status": state, "detail": type(error).__name__})
    progress(CHECKS[-1])
    print(name, state, type(error).__name__)


def require(name, passed, detail=""):
    check(name, passed, detail)
    if not passed:
        raise PrerequisiteFailure(name)


def query(statement):
    raw = sql(statement).strip()
    return [json.loads(line) for line in raw.splitlines()] if raw else []


def http(service, path, token=None, body=None, headers=None, method=None):
    # A fresh opener/socket for every call also makes parallel clients independent.
    if not path.startswith("/") or path.startswith("//"):
        raise ValueError("Only local paths allowed")
    h = {"Content-Type": "application/json", **(headers or {})}
    if token:
        h["Authorization"] = "Bearer " + token
    request = urllib.request.Request(BASE[service] + path, headers=h, method=method,
        data=None if body is None else json.dumps(body).encode())
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        response = opener.open(request, timeout=55)
    except urllib.error.HTTPError as error:
        response = error
    raw = response.read()
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        data = None
    return response.status, data, response.headers


class Runner:
    def __init__(self):
        self.tokens = {}
        self.users = {}
        self.controls = []
        self.evidence = []
        self.completed = []
        self.pool = ThreadPoolExecutor(max_workers=14)
        self.be_stopped = False

    def initialize(self):
        for who in ("owner", "shared", "class", "unshared", "other"):
            teacher = who in ("owner", "other")
            body = {"email": f"authz-{who}@local.dodream.invalid", "password": ENV["LOCAL_TEACHER_PASSWORD"]} if teacher else {
                "deviceId": "dodream-authz-" + who, "deviceSecret": ENV["LOCAL_STUDENT_SECRET"]}
            code, data, _, _ = req("be", "/api/auth/" + ("teacher" if teacher else "student") + "/login", body=body)
            require("grading_login_" + who, code == 200 and isinstance(data, dict) and bool(data.get("accessToken")), f"HTTP {code}")
            self.tokens[who] = data["accessToken"]
            self.users[who] = int(payload(data["accessToken"])["sub"])
        rows = query("SELECT JSON_OBJECT('id',id,'title',title,'teacher',teacher_id) FROM materials WHERE title IN ('[GRADING LOCAL] phase3b','[GRADING LOCAL] phase3b second') AND deleted_at IS NULL;")
        require("dedicated_grading_materials", len(rows) == 2 and all(row["teacher"] == self.users["owner"] for row in rows))
        self.material = next(row["id"] for row in rows if row["title"] == "[GRADING LOCAL] phase3b")
        self.second = next(row["id"] for row in rows if row["title"] == "[GRADING LOCAL] phase3b second")
        self.teacher_quizzes = self.quizzes("owner")
        require("dedicated_grading_questions", len(self.teacher_quizzes) >= 2)
        students = self.quizzes("shared")
        require("grading_student_version_without_answers", all(isinstance(q.get("version"), int) and "correct_answer" not in q for q in students))
        rows = query("SELECT JSON_OBJECT('name',index_name,'cols',GROUP_CONCAT(column_name ORDER BY seq_in_index),'unique',MAX(non_unique)=0) FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name='grading_attempts' GROUP BY index_name;")
        check("actual_mysql_student_key_uniqueness", any(row["unique"] and row["cols"] == "student_id,idempotency_key" for row in rows))

    def quizzes(self, who="shared", material=None):
        code, data, _ = http("be", f"/api/materials/{material or self.material}/quizzes", self.tokens[who])
        if code != 200 or not isinstance(data, list):
            raise PrerequisiteFailure("quiz lookup")
        return data

    def body(self, *, wrong=False, material=None, subset=None):
        public = self.quizzes("shared", material)
        trusted = {q["id"]: q for q in self.quizzes("owner", material)}
        chosen = public if subset is None else public[:subset]
        return {"answers": [{"quizId": q["id"], "version": q["version"],
            "answer": "synthetic intentionally wrong" if wrong else trusted[q["id"]]["correct_answer"]} for q in chosen]}

    def submit(self, key, body, who="shared", material=None):
        headers = {} if key is None else {"Idempotency-Key": key}
        return http("be", f"/api/materials/{material or self.material}/quizzes/submit", self.tokens.get(who), body, headers)

    def attempt(self, key, who="shared"):
        uuid.UUID(key)
        rows = query(f"SELECT JSON_OBJECT('id',id,'attemptId',attempt_id,'state',state,'generation',execution_generation,'dispatched',dispatched_at IS NOT NULL,'material',material_id) FROM grading_attempts WHERE student_id={self.users[who]} AND idempotency_key='{key}';")
        return rows[0] if rows else None

    def counts(self, key, who="shared"):
        uuid.UUID(key)
        rows = query(f"SELECT JSON_OBJECT('attempts',COUNT(*),'items',COALESCE(SUM((SELECT COUNT(*) FROM grading_attempt_items i WHERE i.attempt_id=a.id)),0),'results',COALESCE(SUM((SELECT COUNT(*) FROM grading_attempt_results r WHERE r.attempt_id=a.id)),0),'logs',COALESCE(SUM((SELECT COUNT(*) FROM student_quiz_logs l WHERE l.attempt_id=a.id)),0)) FROM grading_attempts a WHERE student_id={self.users[who]} AND idempotency_key='{key}';")
        return rows[0]

    def provider(self, key):
        uuid.UUID(key)
        return json.loads(docker_exec("ai", ["python", "-c", "import json; from app.local_grading import grading_stats; print(json.dumps(grading_stats(" + repr(key) + ")))"]))

    def call_total(self, key):
        return sum(row["started"] for row in self.provider(key))

    def control(self, service, key, generation=1, **value):
        uuid.UUID(key)
        if service == "ai":
            path = f"/app/db_data/local_provider/grading-controls/{key}.{generation}.json"
        else:
            path = f"/app/local-data/grading-controls/{key}.{generation}.json"
        docker_exec(service, ["sh", "-c", 'mkdir -p "${1%/*}" && cat > "$1"', "control", path], json.dumps(value))
        self.controls.append((service, path))
        return path

    def release(self, service, key, generation=1):
        path = ("/app/db_data/local_provider" if service == "ai" else "/app/local-data") + f"/grading-controls/{key}.{generation}.release"
        docker_exec(service, ["sh", "-c", ': > "$1"', "release", path])
        self.controls.append((service, path))

    def events(self, key, generation=1):
        path = f"/app/local-data/grading-controls/{key}.{generation}.events.jsonl"
        raw = docker_exec("be", ["sh", "-c", 'if [ -f "$1" ]; then cat "$1"; fi', "events", path])
        return [json.loads(line) for line in raw.splitlines() if line.strip()]

    def wait_event(self, key, event_name, generation=1, seconds=20):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            events = self.events(key, generation)
            if any(event["event"] == event_name for event in events):
                return events
            time.sleep(.15)
        raise PrerequisiteFailure("Expected grading gate was not reached")

    def status(self, attempt, who="shared", material=None):
        return http("be", f"/api/materials/{material or self.material}/quiz-attempts/{attempt}", self.tokens.get(who))

    def retry(self, attempt, generation, confirm=False, who="shared", material=None):
        return http("be", f"/api/materials/{material or self.material}/quiz-attempts/{attempt}/retry", self.tokens.get(who),
                    {"expectedGeneration": generation, "confirmUnknown": confirm})

    def observe(self, label, key, expected_logs, expected_calls, who="shared"):
        counts, calls = self.counts(key, who), self.provider(key)
        check(label + "_one_attempt", counts["attempts"] == 1)
        check(label + "_atomic_results_logs", counts["logs"] == counts["results"] == expected_logs)
        check(label + "_provider_calls", sum(row["started"] for row in calls) == expected_calls)
        self.evidence.append({"case": label, "submissionKey": key, "db": counts, "provider": calls})

    def edit(self, suffix):
        rows = self.quizzes("owner")
        changed = [{key: value for key, value in row.items() if key not in ("id", "version")} for row in rows]
        for index, row in enumerate(changed):
            row["correct_answer"] = f"synthetic {suffix} {index}"
            row["content"] = f"Synthetic edited question {suffix} {index}"
        code, _, _ = http("be", f"/api/materials/{self.material}/quizzes", self.tokens["owner"], changed)
        require("teacher_edit_" + suffix, code == 200, f"HTTP {code}")

    def sequential(self):
        key, body = str(uuid.uuid4()), self.body()
        first = self.submit(key, body)
        require("submit_success_shape", first[0] == 200 and isinstance(first[1], list) and len(first[1]) == len(body["answers"]), f"HTTP {first[0]}")
        check("submit_headers", bool(first[2].get("X-Grading-Attempt-Id")) and first[2].get("X-Grading-State") == "SUCCEEDED")
        second = self.submit(key, body)
        check("same_key_exact_replay", second[0] == 200 and second[1] == first[1])
        reordered = {"answers": list(reversed(body["answers"]))}
        reordered_result = self.submit(key, reordered)
        check("answer_order_normalized_replay", reordered_result[0] == 200 and reordered_result[1] == first[1])
        altered = copy.deepcopy(body)
        altered["answers"][0]["answer"] += " "
        check("answer_whitespace_is_significant", self.submit(key, altered)[0] == 409)
        check("same_key_different_material_conflict", self.submit(key, self.body(material=self.second), material=self.second)[0] == 409)
        self.observe("sequential", key, len(body["answers"]), 1)
        new_key = str(uuid.uuid4())
        new = self.submit(new_key, body)
        check("new_key_new_attempt", new[0] == 200 and new[2].get("X-Grading-Attempt-Id") != first[2].get("X-Grading-Attempt-Id"))
        self.observe("intentional_new_submission", new_key, len(body["answers"]), 1)
        check("other_student_same_key_independent", self.submit(key, body, "class")[0] == 200)
        self.observe("same_key_other_student", key, len(body["answers"]), 2, "class")
        attempt_id = first[2].get("X-Grading-Attempt-Id")
        for who, expected in (("shared", 404), ("class", 404), ("owner", 403), (None, 401)):
            denied = http("ai", "/rag/quiz/grade-batch", self.tokens.get(who),
                {"attempt_id": attempt_id, "execution_generation": 1, "execution_token": "A" * 43})
            check("direct_ai_private_capability_required_" + str(who), denied[0] == expected)
        check("direct_ai_denials_do_not_invoke_provider", self.call_total(key) == 2)
        for action, expected in ((lambda: self.status(attempt_id, "class"), 404),
                (lambda: self.retry(attempt_id, 1, who="class"), 404),
                (lambda: self.status(attempt_id, "other"), 403),
                (lambda: self.status(attempt_id, "unshared"), 404),
                (lambda: self.status(attempt_id, None), 401),
                (lambda: self.retry(attempt_id, 1, who=None), 401)):
            check("foreign_attempt_denied", action()[0] == expected)
        check("same_key_missing_rejected", self.submit(None, body)[0] == 400)
        for invalid in ("invalid", "A0000000-0000-4000-8000-000000000000"):
            check("key_format_rejected", self.submit(invalid, body)[0] == 400)
        for invalid in ({"answers": body["answers"] * 2}, {"answers": []},
                        {"answers": [{**body["answers"][0], "answer": "x" * 2001}]},
                        {"answers": [{**body["answers"][0], "version": True}]}):
            bad_key = str(uuid.uuid4())
            check("invalid_submission_rejected", self.submit(bad_key, invalid)[0] == 400)
            check("invalid_submission_has_no_attempt", self.counts(bad_key)["attempts"] == 0)
        forged_key = str(uuid.uuid4())
        forged = self.submit(forged_key, {**body, "studentId": self.users["class"], "score": 100,
                                       "correct_answer": "synthetic forged answer"})
        check("legacy_ignored_metadata_cannot_set_grading_owner", forged[0] == 200 and self.counts(forged_key)["logs"] == len(body["answers"]) and self.counts(forged_key, "class")["attempts"] == 0)
        partial_key = str(uuid.uuid4())
        check("partial_submission_remains_allowed", self.submit(partial_key, self.body(subset=1))[0] == 200)
        self.observe("partial", partial_key, 1, 1)

    def concurrent(self):
        for round_number in range(3):
            key, body = str(uuid.uuid4()), self.body()
            self.control("ai", key, delay_seconds=1)
            futures = [self.pool.submit(self.submit, key, body) for _ in range(12)]
            responses = [future.result(timeout=50) for future in futures]
            check(f"concurrent_{round_number}_statuses", all(row[0] in (200, 202) for row in responses), "12 independent HTTP connections")
            check(f"concurrent_{round_number}_successful_owner", any(row[0] == 200 for row in responses))
            replay = self.submit(key, body)
            check(f"concurrent_{round_number}_replay", replay[0] == 200)
            self.observe(f"concurrent_{round_number}", key, len(body["answers"]), 1)

    def actual_database_constraints(self):
        key = str(uuid.uuid4())
        program = '''import json, threading, uuid
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from app.common.db_session import engine
student, material, key = INPUT
with engine.connect() as c:
    assert c.execute(text("SELECT title FROM materials WHERE id=:m"),{"m":material}).scalar().startswith("[GRADING LOCAL]")
barrier=threading.Barrier(12)
statement=text("INSERT INTO grading_attempts(attempt_id,student_id,material_id,idempotency_key,request_fingerprint,state,execution_generation,created_at,completed_at,failure_code) VALUES(:a,:s,:m,:k,:f,'REVOKED',0,UTC_TIMESTAMP(6),UTC_TIMESTAMP(6),'LOCAL_CONSTRAINT_PROBE')")
def insert(index):
    with engine.connect() as c:
        identity=int(c.execute(text("SELECT CONNECTION_ID()")).scalar())
        barrier.wait(timeout=15)
        try:
            c.execute(statement,{"a":str(uuid.uuid4()),"s":student,"m":material,"k":key,"f":"0"*64})
            c.commit()
            return {"connection":identity,"outcome":"inserted"}
        except IntegrityError as error:
            code=error.orig.args[0]
            c.rollback()
            return {"connection":identity,"outcome":"rejected","mysqlCode":code}
with ThreadPoolExecutor(max_workers=12) as pool:
    rows=list(pool.map(insert,range(12)))
nulls=[]
for nullable in ("s","k"):
    values={"a":str(uuid.uuid4()),"s":student,"m":material,"k":str(uuid.uuid4()),"f":"0"*64}
    values[nullable]=None
    try:
        with engine.begin() as c:c.execute(statement,values)
        nulls.append({"field":nullable,"mysqlCode":0})
    except IntegrityError as error:nulls.append({"field":nullable,"mysqlCode":error.orig.args[0]})
print(json.dumps({"connections":rows,"nulls":nulls}))
'''.replace("INPUT", repr((self.users["shared"], self.material, key)))
        result = json.loads(docker_exec("ai", ["python", "-"], program))
        rows = result["connections"]
        check("mysql_race_twelve_independent_connections", len(rows) == 12 and len({row["connection"] for row in rows}) == 12)
        check("mysql_unique_constraint_one_insert_eleven_duplicates", sum(row["outcome"] == "inserted" for row in rows) == 1 and sum(row.get("mysqlCode") == 1062 for row in rows) == 11)
        check("mysql_required_student_and_key_reject_null", len(result["nulls"]) == 2 and all(row["mysqlCode"] == 1048 for row in result["nulls"]))
        self.observe("mysql_constraint_probe", key, 0, 0)
        check("mysql_constraint_probe_no_snapshot_or_provider", self.counts(key)["items"] == 0)
        self.evidence.append({"case": "mysql_independent_constraint_connections", **result})

    def snapshots(self):
        stale_body = self.body()
        self.edit("before-accept")
        key = str(uuid.uuid4())
        check("quiz_version_conflict", self.submit(key, stale_body)[0] == 409)
        check("version_conflict_has_no_attempt", self.counts(key)["attempts"] == 0)
        key, body = str(uuid.uuid4()), self.body()
        self.control("be", key, mode="before_dispatch")
        future = self.pool.submit(self.submit, key, body)
        try:
            self.wait_event(key, "before_dispatch")
            row = self.attempt(key)
            require("accepted_snapshot_persisted_before_provider", bool(row) and row["state"] == "PROCESSING" and not row["dispatched"])
            code, state, _ = self.status(row["attemptId"])
            check("processing_state_has_no_snapshot_answer", code == 202 and isinstance(state, dict) and
                  set(state) == {"attemptId", "state", "generation", "failureCode", "retryable", "deadlineAt"})
            self.edit("during-grading")
            self.release("be", key)
            response = future.result(timeout=40)
            require("inflight_edit_uses_snapshot", response[0] == 200 and all(item["is_correct"] for item in response[1]), f"HTTP {response[0]}")
            check("snapshot_answer_not_live_answer", {item["correct_answer"] for item in response[1]} == {item["answer"] for item in body["answers"]})
            self.edit("after-grading")
            replay = self.submit(key, body)
            check("edited_quiz_same_key_retains_result", replay[0] == 200 and replay[1] == response[1])
            status = self.status(row["attemptId"])
            check("stored_result_snapshot_stable", status[0] == 200 and status[1] == response[1])
            self.observe("immutable_snapshot", key, len(body["answers"]), 1)
        finally:
            self.release("be", key)

    def failures(self):
        for mode in ("http_error", "missing", "duplicate", "wrong_id", "wrong_type", "long_feedback", "wrong_answer"):
            key, body = str(uuid.uuid4()), self.body()
            self.control("ai", key, mode=mode)
            response = self.submit(key, body)
            check("provider_" + mode + "_confirmed_failure", response[0] == 502 and response[1].get("state") == "FAILED", f"HTTP {response[0]}")
            check("provider_" + mode + "_no_snapshot_exposure", isinstance(response[1], dict) and
                  set(response[1]) == {"attemptId", "state", "generation", "failureCode", "retryable", "deadlineAt"})
            self.observe("provider_" + mode, key, 0, 1)
            row = self.attempt(key)
            retried = self.retry(row["attemptId"], row["generation"])
            check("provider_" + mode + "_explicit_retry", retried[0] == 200)
            self.observe("provider_" + mode + "_recovered", key, len(body["answers"]), 2)
        key, body = str(uuid.uuid4()), self.body()
        self.control("ai", key, delay_seconds=11)
        response = self.submit(key, body)
        check("provider_timeout_unknown", response[0] == 503 and response[1].get("state") == "UNKNOWN", f"HTTP {response[0]}")
        row = self.attempt(key)
        check("unknown_requires_explicit_confirmation", self.retry(row["attemptId"], 1)[0] == 409)
        self.observe("timeout_before_recovery", key, 0, 1)
        check("unknown_confirmed_retry", self.retry(row["attemptId"], 1, True)[0] == 200)
        self.observe("timeout_recovered", key, len(body["answers"]), 2)
        key, body = str(uuid.uuid4()), self.body()
        for generation in (1, 2, 3):
            self.control("ai", key, generation, mode="http_error")
        self.submit(key, body)
        row = self.attempt(key)
        for generation in (1, 2):
            check("bounded_retry_failure_" + str(generation), self.retry(row["attemptId"], generation)[0] == 502)
        check("retry_limit_rejected", self.retry(row["attemptId"], 3)[0] == 409)
        self.observe("bounded_retries", key, 0, 3)

    def atomic_and_fence(self):
        key, body = str(uuid.uuid4()), self.body()
        self.control("be", key, mode="fail_after_first_log")
        response = self.submit(key, body)
        check("result_transaction_failure_is_unknown", response[0] == 503 and response[1].get("state") == "UNKNOWN")
        self.observe("atomic_rollback", key, 0, 1)
        row = self.attempt(key)
        check("atomic_rollback_explicit_recovery", self.retry(row["attemptId"], 1, True)[0] == 200)
        self.observe("atomic_recovered", key, len(body["answers"]), 2)
        key, body = str(uuid.uuid4()), self.body()
        self.control("be", key, mode="after_response")
        future = self.pool.submit(self.submit, key, body)
        try:
            self.wait_event(key, "after_response")
            row = self.attempt(key)
            # Explicit fault injection on this new attempt only, separate from real restarts.
            sql(f"UPDATE grading_attempts SET deadline_at=DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 1 SECOND) WHERE id={row['id']} AND material_id={self.material} AND state='PROCESSING';")
            check("expired_dispatched_attempt_becomes_unknown", self.status(row["attemptId"])[0] == 503)
            recovered = self.retry(row["attemptId"], 1, True)
            require("generation_two_finishes", recovered[0] == 200)
            self.release("be", key)
            late = future.result(timeout=45)
            check("late_generation_cannot_overwrite_success", late[0] == 200 and late[1] == recovered[1])
            self.observe("late_generation_fence", key, len(body["answers"]), 2)
        finally:
            self.release("be", key)

    def authorization(self):
        body = self.body()
        for who, expected in (("unshared", 404), ("owner", 403), (None, 401)):
            key = str(uuid.uuid4())
            check("new_submission_access_" + str(who), self.submit(key, body, who)[0] == expected)
            check("denied_submission_no_provider_" + str(who), self.call_total(key) == 0)
        key = str(uuid.uuid4())
        self.control("be", key, mode="after_response")
        future = self.pool.submit(self.submit, key, body)
        revoked = False
        try:
            self.wait_event(key, "after_response")
            row = self.attempt(key)
            code, _, _ = http("be", f"/api/materials/{self.material}/shares/{self.users['shared']}", self.tokens["owner"], method="DELETE")
            require("dedicated_share_revoked", code == 204)
            revoked = True
            check("revoked_attempt_status_denied", self.status(row["attemptId"])[0] == 404)
            check("revoked_attempt_replay_denied", self.submit(key, body)[0] == 404)
            check("revoked_attempt_retry_denied", self.retry(row["attemptId"], 1, True)[0] == 404)
            self.release("be", key)
            response = future.result(timeout=40)
            check("revoked_inflight_response_denied", response[0] == 404)
            check("revoked_attempt_terminal_state", self.attempt(key)["state"] == "REVOKED")
            self.observe("revoked_during_grading", key, 0, 1)
        finally:
            self.release("be", key)
            if revoked:
                classroom = query(f"SELECT JSON_OBJECT('classroom',classroom_id) FROM student_profiles WHERE user_id={self.users['shared']};")[0]["classroom"]
                code, _, _ = http("be", "/api/materials/share", self.tokens["owner"], {"materialId": self.material,
                    "shares": {str(classroom): {"type": "INDIVIDUAL", "studentIds": [self.users["shared"]]}}})
                require("dedicated_share_restored", code == 200)
        key, body = str(uuid.uuid4()), self.body()
        self.control("be", key, mode="after_response")
        future = self.pool.submit(self.submit, key, body)
        deleted = False
        try:
            self.wait_event(key, "after_response")
            row = self.attempt(key)
            sql(f"UPDATE materials SET deleted_at=UTC_TIMESTAMP(6) WHERE id={self.material} AND title='[GRADING LOCAL] phase3b' AND deleted_at IS NULL;")
            deleted = True
            check("deleted_attempt_status_denied", self.status(row["attemptId"])[0] == 404)
            check("deleted_attempt_retry_denied", self.retry(row["attemptId"], 1, True)[0] == 404)
            self.release("be", key)
            check("deleted_inflight_response_denied", future.result(timeout=40)[0] == 404)
            check("deleted_attempt_terminal_state", self.attempt(key)["state"] == "REVOKED")
            self.observe("deleted_during_grading", key, 0, 1)
        finally:
            self.release("be", key)
            if deleted:
                sql(f"UPDATE materials SET deleted_at=NULL WHERE id={self.material} AND title='[GRADING LOCAL] phase3b';")

    def statistics_and_legacy(self):
        old_key, body = str(uuid.uuid4()), self.body()
        self.control("be", old_key, mode="after_response")
        old_future = self.pool.submit(self.submit, old_key, body)
        try:
            self.wait_event(old_key, "after_response")
            new_key = str(uuid.uuid4())
            newer = self.submit(new_key, self.body(wrong=True))
            require("newer_submission_finishes_first", newer[0] == 200 and all(not result["is_correct"] for result in newer[1]))
            self.release("be", old_key)
            require("older_submission_finishes_later", old_future.result(timeout=40)[0] == 200)
            code, stats, _ = http("be", f"/api/stats/student/{self.users['shared']}/materials", self.tokens["shared"])
            material_stats = next((row for row in stats if row["materialId"] == self.material), None) if isinstance(stats, list) else None
            check("latest_stats_use_submission_order", code == 200 and material_stats is not None and material_stats["correctCount"] == 0)
            totals = query(f"SELECT JSON_OBJECT('logs',COUNT(*),'submissions',COUNT(DISTINCT l.attempt_id)) FROM student_quiz_logs l JOIN quizzes q ON q.id=l.quiz_id WHERE q.material_id={self.material} AND l.student_id={self.users['shared']};")[0]
            check("submission_count_distinct_from_question_logs", material_stats is not None and material_stats.get("submissionCount") == totals["submissions"] and material_stats["tryCount"] == totals["logs"])
            replay = self.submit(new_key, self.body(wrong=True))
            after_replay = query(f"SELECT JSON_OBJECT('logs',COUNT(*),'submissions',COUNT(DISTINCT l.attempt_id)) FROM student_quiz_logs l JOIN quizzes q ON q.id=l.quiz_id WHERE q.material_id={self.material} AND l.student_id={self.users['shared']};")[0]
            check("replay_does_not_increment_statistics", replay[0] == 200 and after_replay == totals)
            old, new = self.attempt(old_key), self.attempt(new_key)
            # Explicit tie injection only into the two new test attempts' derived log order.
            try:
                sql(f"UPDATE student_quiz_logs l JOIN grading_attempts a ON a.id=l.attempt_id SET l.submitted_at=(SELECT created_at FROM (SELECT created_at FROM grading_attempts WHERE id={new['id']}) clock) WHERE a.id={old['id']} AND a.material_id={self.material};")
                code, tied_stats, _ = http("be", f"/api/stats/student/{self.users['shared']}/materials", self.tokens["shared"])
                check("latest_stats_tie_uses_attempt_order", code == 200 and next(row for row in tied_stats if row["materialId"] == self.material)["correctCount"] == 0)
            finally:
                # Restore each log's actual accepted time even if the observation fails.
                sql(f"UPDATE student_quiz_logs l JOIN grading_attempts a ON a.id=l.attempt_id SET l.submitted_at=a.created_at WHERE a.id={old['id']} AND a.material_id={self.material};")
        finally:
            self.release("be", old_key)
        # A new synthetic legacy row, never a rewrite of an existing user's history.
        quiz_id = self.quizzes("shared")[0]["id"]
        sql(f"INSERT INTO student_quiz_logs(quiz_id,student_id,student_answer,is_correct,ai_feedback,solved_at) SELECT q.id,{self.users['shared']},'phase3a synthetic legacy',0,'synthetic legacy','2001-01-01 00:00:00' FROM quizzes q JOIN materials m ON m.id=q.material_id WHERE q.id={quiz_id} AND m.id={self.material} AND m.title='[GRADING LOCAL] phase3b';")
        self.edit("legacy-current")
        code, history, _ = http("be", f"/api/materials/{self.material}/quizzes/history", self.tokens["shared"])
        legacy = [row for row in history if row.get("student_answer") == "phase3a synthetic legacy"] if isinstance(history, list) else []
        check("legacy_history_retained_without_forged_snapshot", code == 200 and bool(legacy) and all(row.get("snapshotAvailable") is False and row.get("correct_answer") is None and row.get("questionContent") is None for row in legacy))
        code, stats, _ = http("be", f"/api/stats/student/{self.users['shared']}/materials", self.tokens["shared"])
        expected_legacy = query(f"SELECT JSON_OBJECT('count',COUNT(*)) FROM student_quiz_logs l JOIN quizzes q ON q.id=l.quiz_id WHERE q.material_id={self.material} AND l.student_id={self.users['shared']} AND l.attempt_id IS NULL;")[0]["count"]
        check("legacy_question_logs_reported_separately", code == 200 and next(row for row in stats if row["materialId"] == self.material).get("legacyLogCount") == expected_legacy)

    def operation(self, name, *args):
        result = subprocess.run(compose_args(*args), capture_output=True, text=True, env=clean_env(), timeout=65)
        require(name, result.returncode == 0, "guarded own Spring service; output not retained")

    def start_be(self):
        self.operation("own_spring_start", "start", "be")
        self.be_stopped = False
        end = time.monotonic() + 65
        while time.monotonic() < end:
            try:
                if http("be", "/actuator/health")[0] == 200:
                    check("own_spring_ready", True)
                    return
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                pass
            time.sleep(.5)
        raise PrerequisiteFailure("Own Spring restart health deadline")

    def wait_state(self, attempt, expected, timeout=40):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            code, data, _ = self.status(attempt)
            if isinstance(data, dict) and data.get("state") == expected:
                return code, data
            time.sleep(.3)
        raise PrerequisiteFailure("Attempt did not reach expected recovery state")

    def restart_windows(self):
        # Four real process stops; gate injection establishes the observed crash window.
        for window in ("before_dispatch", "provider_inflight", "after_response", "after_commit"):
            key, body = str(uuid.uuid4()), self.body()
            if window == "provider_inflight":
                self.control("ai", key, gate=True)
            else:
                self.control("be", key, mode=window)
            future = self.pool.submit(self.submit, key, body)
            try:
                if window == "provider_inflight":
                    end = time.monotonic() + 15
                    while time.monotonic() < end and self.call_total(key) == 0:
                        time.sleep(.1)
                    require("restart_provider_started", self.call_total(key) == 1)
                else:
                    self.wait_event(key, window)
                row = self.attempt(key)
                require("restart_" + window + "_window_observed", bool(row) and row["state"] == ("SUCCEEDED" if window == "after_commit" else "PROCESSING"))
                # If a stop command times out after stopping the process, cleanup still
                # attempts a guarded restoration; a rejected gate cannot affect outsiders.
                self.be_stopped = True
                self.operation("restart_" + window + "_stop", "stop", "be")
                self.start_be()
                # Network/server interruption is observed separately from state recovery.
                try:
                    lost = future.result(timeout=10)
                    check("restart_" + window + "_request_interrupted", lost[0] != 200)
                except (urllib.error.URLError, TimeoutError, ConnectionError):
                    check("restart_" + window + "_request_interrupted", True)
                if window == "after_commit":
                    replay = self.submit(key, body)
                    check("restart_completed_replay", replay[0] == 200)
                    self.observe("restart_after_commit", key, len(body["answers"]), 1)
                else:
                    expected = "FAILED" if window == "before_dispatch" else "UNKNOWN"
                    code, state = self.wait_state(row["attemptId"], expected)
                    check("restart_" + window + "_recoverable", code == (502 if expected == "FAILED" else 503))
                    self.observe("restart_" + window + "_before_recovery", key, 0, 0 if window == "before_dispatch" else 1)
                    result = self.retry(row["attemptId"], state["generation"], expected == "UNKNOWN")
                    check("restart_" + window + "_explicit_recovery", result[0] == 200)
                    self.observe("restart_" + window + "_after_recovery", key, len(body["answers"]), 1 if window == "before_dispatch" else 2)
            finally:
                if self.be_stopped:
                    self.start_be()
                self.release("ai" if window == "provider_inflight" else "be", key)

    def lost_response_and_transaction(self):
        key, body = str(uuid.uuid4()), self.body()
        self.control("be", key, mode="after_commit_response_lost")
        response = self.submit(key, body)
        check("after_commit_response_fault_injected", response[0] == 503)
        require("after_commit_database_is_successful", self.attempt(key)["state"] == "SUCCEEDED")
        check("after_commit_same_key_recovers_result", self.submit(key, body)[0] == 200)
        self.observe("committed_response_lost", key, len(body["answers"]), 1)
        events = self.events(key)
        boundary = [row for row in events if row["event"] == "provider_boundary"]
        check("real_spring_provider_boundary_without_transaction_or_connection", len(boundary) == 1
              and boundary[0].get("transactionActive") is False and boundary[0].get("connectionBound") is False
              and boundary[0].get("hibernateConnectionHeld") is False)
        self.evidence.append({"case": "spring_actual_provider_boundary", "events": boundary})
        key, body = str(uuid.uuid4()), self.body()
        self.control("be", key, mode="after_response")
        future = self.pool.submit(self.submit, key, body)
        try:
            self.wait_event(key, "after_response")
            started = time.monotonic()
            value = query("SELECT JSON_OBJECT('independent',1);")
            check("independent_database_request_during_grading", value == [{"independent": 1}] and time.monotonic() - started < 5, "independent mysql client; auxiliary evidence")
            self.release("be", key)
            check("delayed_request_still_completes", future.result(timeout=40)[0] == 200)
        finally:
            self.release("be", key)

    def independent_query_during_provider(self):
        key, body = str(uuid.uuid4()), self.body()
        self.control("ai", key, gate=True)
        future = self.pool.submit(self.submit, key, body)
        try:
            end = time.monotonic() + 6
            counters = self.provider(key)
            while not counters and time.monotonic() < end:
                time.sleep(.05)
                counters = self.provider(key)
            require("actual_provider_wait_observed", bool(counters) and counters[0]["started"] == 1
                    and counters[0]["finished"] == 0)
            started = time.monotonic()
            value = query("SELECT JSON_OBJECT('independent',1);")
            still_waiting = self.provider(key)
            check("independent_db_connection_while_provider_waits", value == [{"independent": 1}]
                  and time.monotonic() - started < 5 and still_waiting[0]["finished"] == 0,
                  "provider started but unfinished before and after independent MySQL query")
            self.release("ai", key)
            check("actual_delayed_provider_completes_after_release", future.result(timeout=20)[0] == 200)
            self.observe("actual_provider_wait", key, len(body["answers"]), 1)
        finally:
            self.release("ai", key)

    def run(self):
        self.initialize()
        # One real positive execution is a prerequisite for all fault/concurrency cases.
        # A common integration failure stops here rather than repeating that same cause.
        key, body = str(uuid.uuid4()), self.body()
        response = self.submit(key, body)
        require("grading_normal_execution_prerequisite", response[0] == 200 and isinstance(response[1], list)
                and len(response[1]) == len(body["answers"]) and all(result.get("is_correct") is True
                    and result.get("snapshotAvailable") is True for result in response[1]), f"HTTP {response[0]}")
        self.observe("normal_prerequisite", key, len(body["answers"]), 1)
        for name in SCENARIOS:
            try:
                getattr(self, name)()
            except RunnerInterrupted:
                raise
            except Exception as error:
                record_error(name + "_execution", error)
            self.completed.append(name)

    def close(self):
        if self.be_stopped:
            try:
                self.start_be()
            except Exception as error:
                record_error("own_spring_restore", error)
        # Keep release files present until all bounded in-flight HTTP calls finish.
        self.pool.shutdown(wait=True, cancel_futures=True)
        # Only files created with this invocation's fresh UUID keys are removed.
        for service in ("ai", "be"):
            paths = list(dict.fromkeys(path for target, path in self.controls if target == service))
            if not paths:
                continue
            try:
                docker_exec(service, ["sh", "-c", 'rm -f -- "$@"', "cleanup", *paths])
            except Exception as error:
                record_error("grading_control_cleanup", error)


if __name__ == "__main__":
    def interrupted(signum, frame):
        raise RunnerInterrupted("Owned grading runner interrupted")
    signal.signal(signal.SIGINT, interrupted)
    runner = Runner()
    try:
        runner.run()
    except Exception as error:
        record_error("grading_execution", error)
    finally:
        runner.close()
    for name in SCENARIOS:
        if name not in runner.completed:
            row = {"name": name + "_not_completed", "status": "NOT_RUN", "detail": "Prerequisite failure or explicit runner interruption"}
            CHECKS.append(row)
            progress(row)
    output = {"mode": "grading", "checks": CHECKS, "total": len(CHECKS),
        "counts": {state: sum(row["status"] == state for row in CHECKS) for state in ("PASS", "FAIL", "BLOCKED", "NOT_RUN")}}
    for suffix in ("", "-" + RUN_STAMP):
        (RESULTS / ("grading-checks" + suffix + ".json")).write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
        (RESULTS / ("grading-attempt-evidence" + suffix + ".json")).write_text(json.dumps(runner.evidence, indent=2) + "\n")
    print(json.dumps(output["counts"]))
    sys.exit(1 if any(row["status"] in ("FAIL", "BLOCKED") for row in CHECKS) else 0)
