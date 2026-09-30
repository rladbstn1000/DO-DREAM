#!/usr/bin/env python3
"""Future authorized evaluation only; no approval, key discovery or paid retries.

The host alone reads gold for comparison. Only public RAG cases and student
answers cross into the application. All outputs are append-only per case; an
interrupted/failed case blocks automatic resubmission, including after restart.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ai"))
from scripts.evaluation import phase5
from app.evaluation_run import usage_for_trace


def require(condition, code):
    if not condition:
        raise RuntimeError(code)


def stamp():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def save_new(path, value):
    """Atomic visibility with exclusive destination: never replace old evidence."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".next")
    try:
        descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(canonical(value) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        # Link is atomic and refuses existing files, unlike os.replace.
        os.link(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def ordered_cases(bundle, split):
    cases = [row for row in bundle["rag_gold.json"]["cases"] if row["split"] == split]
    # Identical fixed history for both groups; alternate which variant runs first.
    return [(row["id"], variant) for index, row in enumerate(cases)
            for variant in (("A", "B") if index % 2 == 0 else ("B", "A"))]


def project_submission(case, material, quizzes):
    """Only quiz ID/version and the fixed synthetic student answer leave evaluator."""
    quiz_id = material["quiz_mapping"].get(case["id"])
    require(type(quiz_id) is int and quiz_id > 0, "PREPARED_QUIZ_MAPPING_REQUIRED")
    found = [row for row in quizzes if row.get("id") == quiz_id]
    require(len(found) == 1 and type(found[0].get("version")) is int
            and found[0]["version"] >= 0, "CURRENT_QUIZ_VERSION_REQUIRED")
    return {"answers": [{"quizId": quiz_id, "version": found[0]["version"], "answer": case["student_answer"]}]}


def app_chat_usage(before, after, material, user_id):
    """Accept API attribution only when exactly its two mandatory calls occurred.

    /rag/chat predates provider trace IDs. A successful A response necessarily
    makes one query embedding and one answer call. Extra/interleaved calls make
    attribution ambiguous and stop the smoke instead of guessing usage.
    """
    require(not before.get("incomplete_dispatch") and not after.get("incomplete_dispatch"),
            "APP_SMOKE_ACCOUNTING_INFLIGHT")
    old = {row["call_id"] for row in before["calls"]}
    calls = [row for row in after["calls"] if row["call_id"] not in old]
    require(len(calls) == 2 and {row["purpose"] for row in calls} == {"query", "answer"}
            and all(row["material_id"] == material["material_id"] and row["user_id"] == user_id
                    and row["source_hash"] == material["source_hash"]
                    and row["source_revision"] == material["source_revision"]
                    and row["state"] == "SUCCEEDED" and row["trace_id"] is None for row in calls),
            "APP_SMOKE_ACCOUNTING_AMBIGUOUS")
    trace = str(uuid.uuid4())
    result = usage_for_trace({"calls": [{**row, "trace_id": trace} for row in calls]}, trace)
    result["attribution"] = "exact_two_required_app_calls_without_interleaving"
    result.pop("provider_trace_id")  # No invented server-side trace identifier.
    return result


@contextmanager
def evaluator_lock(directory):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "evaluation.lock").open("a+") as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("EVALUATION_ALREADY_RUNNING") from None
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


class Evaluation:
    def __init__(self):
        # Importing the pure projection/test helpers reads no generated secrets.
        import live_ai
        import manage
        import phase5_prepare
        self.live, self.manage = live_ai, manage
        self.manifest = live_ai.preflight()
        session = json.loads(live_ai.SESSION.read_text())
        require(session.get("state") == "OPEN" and session.get("run_id") == self.manifest.run_id
                and session.get("manifest_sha256") == self.manifest.digest, "MATCHING_OPEN_SESSION_REQUIRED")
        owned = live_ai.owned()
        require(owned["ai"]["id"] == session["live_ai_id"] and owned["ai"]["state"] == "running"
                and all(owned[name]["state"] == "exited" for name in ("worker", "index-dispatcher")),
                "ISOLATED_LIVE_SESSION_REQUIRED")
        self.bundle = phase5.load()
        phase5.validate(self.bundle)
        self.dataset_hash = phase5.freeze()["dataset_sha256"]
        prepared = json.loads((manage.RESULTS / "phase5-prepared.json").read_text())
        self.materials = {row["material_key"]: row for row in prepared["materials"]}
        self.client = phase5_prepare.student_client(create=False)
        require(self.client.user["userId"] == prepared["student_id"], "APPROVED_SYNTHETIC_STUDENT_REQUIRED")
        approved = {row["material_id"]: row for row in self.manifest.data["materials"]}
        for key in {row["material_id"] for row in self.bundle["rag_gold.json"]["cases"]}:
            material = self.materials[key]
            entry = approved.get(material["material_id"])
            require(entry is not None and prepared["student_id"] in entry["user_ids"]
                    and {"query", "answer", "rewrite", "grading"} <= set(entry["purposes"]),
                    "ALL_EVALUATION_SCOPES_REQUIRED")
        self.directory = ROOT / ".local/phase5/evaluation" / self.manifest.run_id
        self.records = self.directory / "observations"
        self.client_refresh = phase5_prepare.student_client

    def _session_matches(self):
        # Recheck human authorization, code/dataset evidence and revocation before
        # every case. This never reads provider key contents on the host.
        current = self.live.preflight()
        require(current.digest == self.manifest.digest, "EVALUATION_APPROVAL_CHANGED")
        state = json.loads(self.live.SESSION.read_text())
        require(state.get("state") == "OPEN" and state.get("manifest_sha256") == current.digest,
                "MATCHING_OPEN_SESSION_REQUIRED")
        rows = self.live.owned()
        require(rows.get("ai", {}).get("id") == state.get("live_ai_id")
                and rows.get("ai", {}).get("state") == "running"
                and all(rows.get(name, {}).get("state") == "exited" for name in ("worker", "index-dispatcher")),
                "ISOLATED_LIVE_SESSION_CHANGED")

    def execute_json(self, arguments, payload=None, timeout=40):
        import scope_guard
        self._session_matches()
        base = self.manage.compose_base() + ["-f", str(ROOT / "compose.live.yml")]
        environment = self.manage.clean_env()
        environment["DODREAM_LIVE_KEY_CONFIG"] = str(self.live.KEY_FILE)
        operation = ["exec", "-T", "ai", "python", *arguments]
        scope_guard.gate(operation, base, ROOT, environment, self.manage.RESULTS)
        try:
            completed = subprocess.run([*base, *operation], cwd=ROOT, env=environment,
                input=None if payload is None else canonical(payload), text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            # Do not expose exception input/stdout: stdin contains a short-lived JWT.
            raise RuntimeError("EVALUATION_EXECUTION_TIMEOUT_UNKNOWN") from None
        require(len(completed.stdout) <= 2 * 1024 * 1024, "EVALUATION_RESPONSE_TOO_LARGE")
        lines = completed.stdout.splitlines()
        require(bool(lines), "EVALUATION_EXECUTION_NO_RESULT")
        try:
            result = json.loads(lines[-1])
        except ValueError:
            raise RuntimeError("EVALUATION_EXECUTION_INVALID_RESULT") from None
        require(type(result) is dict, "EVALUATION_EXECUTION_INVALID_RESULT")
        require(completed.returncode == 0 or result.get("status") in {"ERROR", "TIMEOUT"},
                "EVALUATION_EXECUTION_EXIT_MISMATCH")
        return result

    def ledger(self):
        code = ("import json; from app.providers import LiveOpenAI; "
                "print(json.dumps(LiveOpenAI.from_environment(role='api').ledger.summary()))")
        result = self.execute_json(["-c", code], timeout=15)
        require(result.get("run_id") == self.manifest.run_id, "EVALUATION_LEDGER_MISMATCH")
        return result

    def _existing(self, key):
        path = self.records / (key + ".json")
        marker = self.directory / "started" / (key + ".json")
        if path.exists():
            record = json.loads(path.read_text())
            phase5.validate_record(record, self.bundle, self.dataset_hash)
            require(record["status"] == "SUCCESS", "PRIOR_FAILED_CASE_REQUIRES_REVIEW_NO_AUTOMATIC_RETRY")
            return record
        require(not marker.exists(), "PRIOR_INTERRUPTED_CASE_REQUIRES_REVIEW_NO_AUTOMATIC_RETRY")
        return None

    def _start(self, key, public_input):
        save_new(self.directory / "started" / (key + ".json"),
            {"started_at": stamp(), "dataset_sha256": self.dataset_hash, "run_id": self.manifest.run_id,
             "public_input": public_input, "public_input_sha256": hashlib.sha256(canonical(public_input).encode()).hexdigest(),
             "automatic_retry_permitted": False})

    def _finish(self, key, record):
        if record.get("accounting_unresolved"):
            # A lost process result is not evidence of zero calls. Preserve it
            # separately instead of feeding invented counts into quality metrics.
            save_new(self.directory / "unresolved" / (key + ".json"), record)
            raise RuntimeError("CASE_ACCOUNTING_UNRESOLVED_NO_AUTOMATIC_RETRY")
        phase5.validate_record(record, self.bundle, self.dataset_hash)
        save_new(self.records / (key + ".json"), record)
        require(record["status"] == "SUCCESS", "CASE_FAILED_STOP_EVALUATION_AND_REVIEW")
        return record

    def _failure(self, case, kind, *, variant=None, code="EVALUATION_FAILED", elapsed=0):
        record = {"dataset_sha256": self.dataset_hash, "run_id": self.manifest.run_id,
                  "kind": kind, "case_id": case["id"], "material_id": case["material_id"],
                  "source_version": case["source_version"], "status": "TIMEOUT" if "TIMEOUT" in code else "ERROR",
                  "error_code": code, "requests_actual": None, "usage": {"input_tokens": None,
                      "output_tokens": None, "cached_input_tokens": None, "reasoning_tokens": None},
                  "computed_cost_usd": None, "reserved_cost_usd": None, "cold": True if kind == "rag" else None,
                  "latency_ms": {"total": elapsed}, "accounting_unresolved": True}
        if kind == "rag":
            record.update(variant=variant, retrieved_source_ids=[], context_source_ids=[], cited_source_ids=[])
        return record

    def rag(self, case_id, variant):
        key = case_id + "-" + variant
        previous = self._existing(key)
        if previous is not None:
            return previous
        self._session_matches()
        public_case = phase5.project_rag_case(case_id, variant, self.bundle)
        material = self.materials[public_case["material_id"]]
        self.client = self.client_refresh(create=False)
        self._start(key, public_case)
        started = time.monotonic()
        try:
            raw = self.execute_json(["-m", "app.evaluation_run", "--variant", variant],
                {"access_token": self.client.token, "case": public_case,
                 "material_id": material["material_id"], "cold": True})
            require(raw.get("dataset_sha256") == self.dataset_hash and raw.get("run_id") == self.manifest.run_id
                    and raw.get("case_id") == case_id and raw.get("variant") == variant,
                    "EVALUATION_RESULT_IDENTITY_MISMATCH")
            if raw.get("status") == "SUCCESS":
                require(raw.get("source_revision") == material["source_revision"]
                        and raw.get("source_hash") == material["source_hash"], "EVALUATION_SOURCE_CHANGED")
                mapped = phase5.map_runtime_sources(public_case["material_id"], raw["source_hash"],
                    raw["context_sources"], raw["cited_runtime_source_ids"], self.bundle)
            else:
                mapped = {"context_source_ids": [], "cited_source_ids": []}
            raw.update(mapped, retrieved_source_ids=list(mapped["context_source_ids"]))
            # Keep actual excerpts for the side-by-side local review table, while
            # mapping itself uses the fixed public position/hash map, never gold.
            record = raw
        except Exception as error:
            code = str(error) if isinstance(error, RuntimeError) and str(error).replace("_", "").isalnum() else "EVALUATION_EXECUTION_FAILED"
            record = self._failure(public_case, "rag", variant=variant, code=code,
                                   elapsed=(time.monotonic() - started) * 1000)
            # No invented zero usage: retain an explicit accounting-unresolved
            # marker and full ledger snapshot when the process lost its result.
            try:
                snapshot = self.ledger()
                save_new(self.directory / "unresolved" / (key + "-ledger.json"), snapshot)
            except Exception:
                pass
        return self._finish(key, record)

    def grading(self, case_id):
        key = case_id
        previous = self._existing(key)
        if previous is not None:
            return previous
        self._session_matches()
        case = next(row for row in self.bundle["grading_gold.json"]["cases"] if row["id"] == case_id)
        material = self.materials[case["material_id"]]
        self.client = self.client_refresh(create=False)
        material_id = material["material_id"]
        code, quizzes, _ = self.client.call(f"/api/materials/{material_id}/quizzes", token=self.client.token)
        require(code == 200 and type(quizzes) is list, "CURRENT_QUIZ_READ_FAILED")
        body = project_submission(case, material, quizzes)
        submission_key = str(uuid.uuid4())
        # Both frozen body and key are durable before the first POST. Never mint
        # a replacement key automatically after a timeout or failed submission.
        self._start(key, {"case_id": case_id, "material_id": material_id,
                          "idempotency_key": submission_key, "body": body})
        started = time.monotonic()
        attempt = None
        try:
            code, results, headers = self.client.call(f"/api/materials/{material_id}/quizzes/submit",
                body=body, token=self.client.token, headers={"Idempotency-Key": submission_key})
            grading_ms = (time.monotonic() - started) * 1000
            attempt = headers.get("X-Grading-Attempt-Id")
            require(isinstance(attempt, str) and str(uuid.UUID(attempt)) == attempt, "GRADING_ATTEMPT_ID_REQUIRED")
            require(code == 200 and headers.get("X-Grading-State") == "SUCCEEDED" and type(results) is list
                    and len(results) == 1, "GRADING_NOT_SUCCEEDED")
            value = results[0]
            require(value.get("question_id") == body["answers"][0]["quizId"]
                    and value.get("student_answer") == case["student_answer"]
                    and value.get("snapshotAvailable") is True and value.get("attemptId") == attempt
                    and type(value.get("is_correct")) is bool and isinstance(value.get("ai_feedback"), str),
                    "GRADING_SNAPSHOT_RESULT_INVALID")
            observed = self.ledger()
            usage = usage_for_trace(observed, attempt)
            require(usage["requests_actual"] == 1, "GRADING_PROVIDER_TRACE_MISMATCH")
            # Successful same-key replay and GET must add no provider call.
            replay_code, replay, replay_headers = self.client.call(f"/api/materials/{material_id}/quizzes/submit",
                body=body, token=self.client.token, headers={"Idempotency-Key": submission_key})
            get_code, stored, _ = self.client.call(f"/api/materials/{material_id}/quiz-attempts/{attempt}", token=self.client.token)
            require(replay_code == 200 and replay == results and replay_headers.get("X-Grading-Attempt-Id") == attempt
                    and get_code == 200 and stored == results, "GRADING_REPLAY_MISMATCH")
            after = usage_for_trace(self.ledger(), attempt)
            require(after["provider_call_ids"] == usage["provider_call_ids"], "GRADING_REPLAY_ADDED_PROVIDER_REQUEST")
            record = {"dataset_sha256": self.dataset_hash, "run_id": self.manifest.run_id,
                "kind": "grading", "case_id": case_id, "material_id": case["material_id"],
                "source_version": case["source_version"], "status": "SUCCESS",
                "is_correct": value["is_correct"], "feedback": value["ai_feedback"],
                "attempt_id": attempt, "same_submission_replay_no_extra_request": True,
                "cold": None, "cold_policy": "long_running_api_process_history_unknown",
                "latency_ms": {"grading": grading_ms,
                    "total": (time.monotonic()-started)*1000}, **usage}
        except Exception as error:
            code = str(error) if isinstance(error, RuntimeError) and str(error).replace("_", "").isalnum() else "GRADING_EXECUTION_FAILED"
            record = self._failure(case, "grading", code=code, elapsed=(time.monotonic()-started)*1000)
            record["attempt_id"] = attempt
            if attempt:
                try:
                    record.update(usage_for_trace(self.ledger(), attempt), accounting_unresolved=False)
                except Exception:
                    pass
        return self._finish(key, record)

    def observations(self):
        return [json.loads(path.read_text()) for path in sorted(self.records.glob("*.json"))]

    def report(self):
        records = self.observations()
        result = phase5.metrics(records, self.bundle, self.dataset_hash)
        result["unresolved_execution_evidence"] = [str(path.relative_to(self.directory))
            for path in sorted((self.directory / "unresolved").glob("*.json"))]
        if result["unresolved_execution_evidence"]:
            result["execution"] = "BLOCKED_UNRESOLVED" if not records else "PARTIAL_UNRESOLVED"
        name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        output = self.directory / "reports" / (name + ".json")
        save_new(output, result)
        save_new(output.with_name(name + "-observations.json"), records)
        phase5.write_once(output.with_suffix(".html"), phase5.review_html(records, self.bundle, self.dataset_hash))
        return output

    def smoke(self):
        # Small development-only gate. Application smoke on both dedicated smoke
        # copies and the live browser journey remain separately required evidence.
        self.rag("R01", "A")
        self.grading("G01")
        target = self.directory / "small-smoke.json"
        if not target.exists():
            save_new(target, {"status": "PASS", "cases": ["R01-A", "G01"],
                              "dataset_sha256": self.dataset_hash, "run_id": self.manifest.run_id,
                              "semantic_quality_review": "NOT_RUN", "observed_at": stamp()})

    def app_smoke(self):
        target = self.directory / "app-smoke.json"
        if target.exists():
            prior = json.loads(target.read_text())
            require(prior.get("status") == "PASS" and prior.get("run_id") == self.manifest.run_id
                    and prior.get("dataset_sha256") == self.dataset_hash, "PRIOR_APP_SMOKE_FAILED_NO_AUTOMATIC_RETRY")
            return prior
        started_path = self.directory / "app-smoke-started.json"
        require(not started_path.exists(), "PRIOR_APP_SMOKE_INTERRUPTED_NO_AUTOMATIC_RETRY")
        self._session_matches()
        config = self.execute_json(["-c", "import json; from app.config import RAG_RETRIEVAL_VARIANT; print(json.dumps({'variant':RAG_RETRIEVAL_VARIANT}))"])
        require(config.get("variant") == "A", "APP_SMOKE_REQUIRES_CONFIGURED_A")
        public = {row["material_key"]: row for row in phase5.public_materials(self.bundle)}
        approved = {row["material_id"]: row for row in self.manifest.data["materials"]}
        for source in self.bundle["smoke_manifest.json"]["materials"]:
            material = self.materials[source["id"]]
            entry = approved.get(material["material_id"])
            require(entry is not None and self.client.user["userId"] in entry["user_ids"]
                    and {"query", "answer", "grading"} <= set(entry["purposes"]), "APP_SMOKE_APPROVAL_REQUIRED")
        save_new(started_path, {"run_id": self.manifest.run_id, "dataset_sha256": self.dataset_hash,
            "started_at": stamp(), "automatic_retry_permitted": False,
            "cases": ["water_question", "water_followup", "recycling_absence", "water_grade", "recycling_grade"]})
        observations = []
        water_session = None
        try:
            for index, scenario in enumerate(self.bundle["smoke_manifest.json"]["scenarios"]):
                self._session_matches()
                self.client = self.client_refresh(create=False)
                material = self.materials[scenario["material_id"]]
                body = {"document_id": str(material["material_id"]), "question": scenario["question"]}
                if index == 1:
                    require(water_session is not None, "APP_SMOKE_PRIOR_SESSION_REQUIRED")
                    body["session_id"] = water_session
                save_new(self.directory / "app-smoke-inputs" / (str(index) + ".json"), body)
                before = self.ledger()
                started = time.monotonic()
                code, data, _ = self.client.call("/rag/chat", body=body, token=self.client.token, service="ai", timeout=32)
                require(code == 200 and type(data) is dict and isinstance(data.get("answer"), str)
                        and bool(data["answer"].strip()) and data.get("document_id") == body["document_id"]
                        and data.get("source_hash") == material["source_hash"]
                        and data.get("source_revision") == material["source_revision"]
                        and data.get("retrieval_variant") == "A", "APP_SMOKE_CHAT_FAILED")
                mode = data.get("mode", {})
                require(mode.get("configured_mode") == "LIVE_OPENAI"
                        and all(mode.get(field) == "live_openai" for field in
                                ("embedding_provider", "answer_provider", "grading_provider")), "APP_SMOKE_MODE_MISMATCH")
                session_id = data.get("session_id")
                require(isinstance(session_id, str) and str(uuid.UUID(session_id)) == session_id
                        and type(data.get("message_id")) is int, "APP_SMOKE_MESSAGE_INVALID")
                if index == 0:
                    water_session = session_id
                if index == 1:
                    require(session_id == water_session, "APP_SMOKE_FOLLOWUP_SESSION_MISMATCH")
                sources = data.get("sources")
                require(type(sources) is list and 1 <= len(sources) <= 3, "APP_SMOKE_SOURCES_REQUIRED")
                mapping = {row["chunk_position"]: row for row in public[scenario["material_id"]]["source_map"]}
                actual_ids = set()
                for source_index, source in enumerate(sources):
                    mapped = mapping.get(source.get("chunk_position"))
                    require(type(source.get("chunk_position")) is int and mapped is not None
                            and source.get("content_hash") == mapped["content_hash"]
                            and source.get("source_hash") == material["source_hash"]
                            and source.get("source_revision") == material["source_revision"], "APP_SMOKE_SOURCE_CHANGED")
                    expected_excerpt = " ".join(public[scenario["material_id"]]["chapters"][source["chunk_position"]]["content"].split())[:300]
                    require(source.get("excerpt") == expected_excerpt, "APP_SMOKE_SOURCE_EXCERPT_MISMATCH")
                    actual_ids.add("chunk-" + str(source["chunk_position"]) + "-" + mapped["content_hash"][:16])
                    path = f"/rag/chat/sessions/{session_id}/messages/{data['message_id']}/sources/{source_index}?student_id={self.client.user['userId']}"
                    source_code, stored, _ = self.client.call(path, token=self.client.token, service="ai")
                    require(source_code == 200 and stored == source, "APP_SMOKE_STORED_SOURCE_MISMATCH")
                cited = data.get("cited_source_ids")
                require(type(cited) is list and all(type(value) is str for value in cited)
                        and len(set(cited)) == len(cited) and set(cited) <= actual_ids,
                        "APP_SMOKE_CITATION_INVALID")
                require(data.get("abstained") is (index == 2)
                        and (not cited if index == 2 else bool(cited)), "APP_SMOKE_REPORTED_ABSTENTION_FAILED")
                history_path = f"/rag/chat/sessions/{session_id}/messages?student_id={self.client.user['userId']}"
                history_code, history, _ = self.client.call(history_path, token=self.client.token, service="ai")
                messages = history.get("messages", []) if type(history) is dict else []
                matching = [row for row in messages if row.get("id") == data["message_id"]]
                require(history_code == 200 and len(matching) == 1
                        and matching[0].get("content") == data["answer"] and matching[0].get("sources") == sources,
                        "APP_SMOKE_HISTORY_MISMATCH")
                accounting = app_chat_usage(before, self.ledger(), material, self.client.user["userId"])
                observation = {"kind": "app_chat", "scenario": index, "material_key": scenario["material_id"],
                    "status": "PASS", "answer": data["answer"], "abstained": data["abstained"],
                    "session_id": session_id, "message_id": data["message_id"], "sources": sources,
                    "cited_source_ids": cited, "stage_latency_ms": data.get("stage_latency_ms", {}),
                    "total_ms": (time.monotonic()-started)*1000, "cold": None,
                    "semantic_human_review": "NOT_RUN", **accounting}
                save_new(self.directory / "app-smoke-observations" / ("chat-" + str(index) + ".json"), observation)
                observations.append(observation)
            for index, case in enumerate(self.bundle["smoke_manifest.json"]["grading_cases"]):
                observations.append(self._app_smoke_grade(index, case))
            result = {"status": "PASS", "run_id": self.manifest.run_id, "dataset_sha256": self.dataset_hash,
                "new_material_copies": 2, "app_questions": 3, "server_snapshot_gradings": 2,
                "same_submission_replay_no_extra_request": True, "observed_at": stamp(),
                "requests_actual": sum(row["requests_actual"] for row in observations),
                "semantic_human_review": "NOT_RUN", "browser_student_journey": "NOT_RUN",
                "history_policy": "Actual prior app conversation; excluded from fixed-history A/B metrics",
                "observation_files": [str(path.relative_to(self.directory)) for path in
                    sorted((self.directory / "app-smoke-observations").glob("*.json"))]}
        except Exception as error:
            code = str(error) if isinstance(error, RuntimeError) and str(error).replace("_", "").isalnum() else "APP_SMOKE_EXECUTION_FAILED"
            result = {"status": "FAIL", "run_id": self.manifest.run_id, "dataset_sha256": self.dataset_hash,
                      "error_code": code, "completed_observations": len(observations),
                      "requests_actual": None, "accounting_status": "UNRESOLVED_CHECK_SHARED_LEDGER",
                      "automatic_retry_permitted": False, "observed_at": stamp()}
        save_new(target, result)
        require(result["status"] == "PASS", "APP_SMOKE_FAILED_STOP_BEFORE_EVALUATION")
        return result

    def _app_smoke_grade(self, index, case):
        self._session_matches()
        self.client = self.client_refresh(create=False)
        material = self.materials[case["material_id"]]
        identity = material["material_id"]
        code, quizzes, _ = self.client.call(f"/api/materials/{identity}/quizzes", token=self.client.token)
        require(code == 200 and type(quizzes) is list, "APP_SMOKE_QUIZ_READ_FAILED")
        matching = [row for row in quizzes if row.get("content") == case["question"]]
        require(len(matching) == 1 and type(matching[0].get("id")) is int
                and type(matching[0].get("version")) is int, "APP_SMOKE_QUIZ_BINDING_FAILED")
        key = str(uuid.uuid4())
        body = {"answers": [{"quizId": matching[0]["id"], "version": matching[0]["version"],
                              "answer": case["student_answer"]}]}
        save_new(self.directory / "app-smoke-inputs" / ("grade-" + str(index) + ".json"),
                 {"idempotency_key": key, "material_id": identity, "body": body})
        code, results, headers = self.client.call(f"/api/materials/{identity}/quizzes/submit", body=body,
                                                token=self.client.token, headers={"Idempotency-Key": key})
        attempt = headers.get("X-Grading-Attempt-Id")
        require(code == 200 and headers.get("X-Grading-State") == "SUCCEEDED" and isinstance(attempt, str)
                and str(uuid.UUID(attempt)) == attempt and type(results) is list and len(results) == 1,
                "APP_SMOKE_GRADING_FAILED")
        value = results[0]
        require(value.get("snapshotAvailable") is True and value.get("attemptId") == attempt
                and value.get("question_id") == matching[0]["id"] and value.get("student_answer") == case["student_answer"]
                and value.get("is_correct") is True, "APP_SMOKE_SIMPLE_GRADING_MISMATCH")
        before = usage_for_trace(self.ledger(), attempt)
        require(before["requests_actual"] == 1, "APP_SMOKE_GRADING_TRACE_MISMATCH")
        code, replay, replay_headers = self.client.call(f"/api/materials/{identity}/quizzes/submit", body=body,
                                                      token=self.client.token, headers={"Idempotency-Key": key})
        get_code, stored, _ = self.client.call(f"/api/materials/{identity}/quiz-attempts/{attempt}", token=self.client.token)
        require(code == 200 and replay_headers.get("X-Grading-Attempt-Id") == attempt and replay == results
                and get_code == 200 and stored == results, "APP_SMOKE_GRADING_REPLAY_FAILED")
        after = usage_for_trace(self.ledger(), attempt)
        require(before["provider_call_ids"] == after["provider_call_ids"], "APP_SMOKE_GRADING_REPLAY_PAID_AGAIN")
        record = {"kind": "app_grading", "status": "PASS", "material_key": case["material_id"],
                  "attempt_id": attempt, "is_correct": value["is_correct"], "feedback": value.get("ai_feedback"),
                  "same_submission_replay_no_extra_request": True, "cold": None, **after}
        save_new(self.directory / "app-smoke-observations" / ("grade-" + str(index) + ".json"), record)
        return record

    def run_split(self, split):
        app_gate = self.directory / "app-smoke.json"
        require(app_gate.exists(), "APP_SMOKE_REQUIRED")
        app_receipt = json.loads(app_gate.read_text())
        require(app_receipt.get("status") == "PASS" and app_receipt.get("run_id") == self.manifest.run_id
                and app_receipt.get("dataset_sha256") == self.dataset_hash, "APP_SMOKE_REQUIRED")
        gate = self.directory / "small-smoke.json"
        require(gate.exists() and json.loads(gate.read_text()).get("status") == "PASS", "SMALL_SMOKE_REQUIRED")
        if split == "final":
            for case_id, variant in ordered_cases(self.bundle, "development"):
                require(self._existing(case_id + "-" + variant) is not None, "DEVELOPMENT_EXECUTION_REQUIRED")
            for row in self.bundle["grading_gold.json"]["cases"]:
                if row["split"] == "development":
                    require(self._existing(row["id"]) is not None, "DEVELOPMENT_EXECUTION_REQUIRED")
        for case_id, variant in ordered_cases(self.bundle, split):
            self.rag(case_id, variant)
        for case in self.bundle["grading_gold.json"]["cases"]:
            if case["split"] == split:
                self.grading(case["id"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["app-smoke", "smoke", "development", "final", "report"])
    args = parser.parse_args()
    try:
        evaluator = Evaluation()
        with evaluator_lock(evaluator.directory):
            if args.command == "app-smoke":
                evaluator.app_smoke()
            elif args.command == "smoke":
                evaluator.smoke()
            elif args.command in {"development", "final"}:
                evaluator.run_split(args.command)
            report = evaluator.report()
        unresolved = bool(list((evaluator.directory / "unresolved").glob("*.json")))
        print(json.dumps({"status": "BLOCKED_UNRESOLVED" if unresolved else "PASS", "command": args.command, "report": str(report),
                          "semantic_human_review": "NOT_RUN", "model_adoption": "NOT_DECIDED"}))
        return 2 if unresolved else 0
    except Exception as error:
        code = str(error) if isinstance(error, RuntimeError) and str(error).replace("_", "").isalnum() else type(error).__name__
        print(json.dumps({"status": "BLOCKED", "reason": code, "provider_requests": "not_asserted",
                          "automatic_retry": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
