"""No Docker, real user session, provider key or external request in these tests."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
from unittest.mock import Mock, MagicMock
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import phase5_evaluate as runner


class EvaluationHostContract(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.bundle = runner.phase5.load()
        self.dataset_hash = runner.phase5.freeze()["dataset_sha256"]

    def tearDown(self):
        self.temporary.cleanup()

    def evaluator_without_runtime(self):
        evaluator = object.__new__(runner.Evaluation)
        evaluator.directory = self.directory
        evaluator.records = self.directory / "observations"
        evaluator.bundle = self.bundle
        evaluator.dataset_hash = self.dataset_hash
        evaluator.manifest = SimpleNamespace(run_id="offline-only")
        evaluator.execute_json = Mock(side_effect=AssertionError("No execution allowed"))
        evaluator._session_matches = Mock(side_effect=AssertionError("No session/key access allowed"))
        return evaluator

    def test_fixed_order_pairs_share_public_input_and_alternate(self):
        rows = runner.ordered_cases(self.bundle, "development")
        self.assertEqual(24, len(rows))
        self.assertEqual([("R01", "A"), ("R01", "B"), ("R03", "B"), ("R03", "A")], rows[:4])
        for index in range(0, len(rows), 2):
            first = runner.phase5.project_rag_case(*rows[index], self.bundle)
            second = runner.phase5.project_rag_case(*rows[index + 1], self.bundle)
            self.assertEqual(first["question"], second["question"])
            self.assertEqual(first["history"], second["history"])
            self.assertNotIn("expected_key_points", first)
            self.assertNotIn("evidence_source_ids", first)

    def test_grading_projection_excludes_gold_and_fixes_server_version(self):
        case = self.bundle["grading_gold.json"]["cases"][0]
        material = {"quiz_mapping": {case["id"]: 99}}
        body = runner.project_submission(case, material, [{"id": 99, "version": 7}])
        self.assertEqual({"answers": [{"quizId": 99, "version": 7, "answer": case["student_answer"]}]}, body)
        encoded = json.dumps(body)
        for field in ("correct_answer", "expected_is_correct", "rubric", "forbidden_judgments"):
            self.assertNotIn(field, encoded)

    def test_missing_mapping_and_invalid_version_cannot_make_new_submission(self):
        case = self.bundle["grading_gold.json"]["cases"][0]
        with self.assertRaisesRegex(RuntimeError, "PREPARED_QUIZ_MAPPING_REQUIRED"):
            runner.project_submission(case, {"quiz_mapping": {}}, [])
        with self.assertRaisesRegex(RuntimeError, "CURRENT_QUIZ_VERSION_REQUIRED"):
            runner.project_submission(case, {"quiz_mapping": {case["id"]: 99}}, [{"id": 99, "version": True}])

    def test_atomic_exclusive_save_never_overwrites_old_evidence(self):
        target = self.directory / "result.json"
        runner.save_new(target, {"original": True})
        with self.assertRaises(FileExistsError):
            runner.save_new(target, {"original": False})
        self.assertEqual({"original": True}, json.loads(target.read_text()))
        self.assertEqual([], list(self.directory.glob("*.next")))

    def test_interrupted_case_never_calls_executor_or_mints_retry(self):
        evaluator = self.evaluator_without_runtime()
        runner.save_new(self.directory / "started/R01-A.json", {"started": True})
        with self.assertRaisesRegex(RuntimeError, "PRIOR_INTERRUPTED_CASE"):
            evaluator.rag("R01", "A")
        evaluator.execute_json.assert_not_called()
        evaluator._session_matches.assert_not_called()

    def successful_record(self):
        case = self.bundle["rag_gold.json"]["cases"][0]
        return {"dataset_sha256": self.dataset_hash, "run_id": "offline-only",
                "kind": "rag", "case_id": case["id"], "variant": "A", "material_id": case["material_id"],
                "source_version": case["source_version"], "status": "SUCCESS", "answer": "합성 출력",
                "abstained": False, "retrieved_source_ids": [], "context_source_ids": [], "cited_source_ids": [],
                "requests_actual": 2, "usage": {"input_tokens": 5, "output_tokens": 5,
                    "cached_input_tokens": 0, "reasoning_tokens": 0},
                "computed_cost_usd": "0.00001", "reserved_cost_usd": "0.01", "cold": True,
                "latency_ms": {"total": 1}}

    def test_existing_success_returns_exact_record_without_paid_execution(self):
        evaluator = self.evaluator_without_runtime()
        record = self.successful_record()
        runner.save_new(evaluator.records / "R01-A.json", record)
        self.assertEqual(record, evaluator.rag("R01", "A"))
        evaluator.execute_json.assert_not_called()
        evaluator._session_matches.assert_not_called()

    def test_existing_failure_is_preserved_and_never_retried(self):
        evaluator = self.evaluator_without_runtime()
        record = self.successful_record()
        record["status"] = "ERROR"
        runner.save_new(evaluator.records / "R01-A.json", record)
        with self.assertRaisesRegex(RuntimeError, "PRIOR_FAILED_CASE"):
            evaluator.rag("R01", "A")
        evaluator.execute_json.assert_not_called()
        self.assertEqual(record, json.loads((evaluator.records / "R01-A.json").read_text()))

    def test_unresolved_call_count_never_becomes_zero_metrics(self):
        evaluator = self.evaluator_without_runtime()
        record = self.successful_record()
        record.update(status="TIMEOUT", requests_actual=None, accounting_unresolved=True)
        with self.assertRaisesRegex(RuntimeError, "CASE_ACCOUNTING_UNRESOLVED"):
            evaluator._finish("R01-A", record)
        saved = json.loads((self.directory / "unresolved/R01-A.json").read_text())
        self.assertIsNone(saved["requests_actual"])
        self.assertFalse((evaluator.records / "R01-A.json").exists())

    def test_unresolved_only_report_is_blocked_not_not_run(self):
        evaluator = self.evaluator_without_runtime()
        runner.save_new(self.directory / "unresolved/R01-A.json", {"requests_actual": None})
        report = json.loads(evaluator.report().read_text())
        self.assertEqual("BLOCKED_UNRESOLVED", report["execution"])
        self.assertEqual(["unresolved/R01-A.json"], report["unresolved_execution_evidence"])

    def test_grading_failure_does_not_invent_process_temperature(self):
        evaluator = self.evaluator_without_runtime()
        case = self.bundle["grading_gold.json"]["cases"][0]
        record = evaluator._failure(case, "grading")
        self.assertIsNone(record["cold"])

    def test_development_requires_successful_real_app_smoke(self):
        evaluator = self.evaluator_without_runtime()
        with self.assertRaisesRegex(RuntimeError, "APP_SMOKE_REQUIRED"):
            evaluator.run_split("development")
        evaluator.execute_json.assert_not_called()

    def test_interrupted_app_smoke_never_automatically_calls_again(self):
        evaluator = self.evaluator_without_runtime()
        runner.save_new(self.directory / "app-smoke-started.json", {"started": True})
        with self.assertRaisesRegex(RuntimeError, "PRIOR_APP_SMOKE_INTERRUPTED"):
            evaluator.app_smoke()
        evaluator.execute_json.assert_not_called()
        evaluator._session_matches.assert_not_called()

    def test_successful_app_smoke_receipt_replays_without_requests(self):
        evaluator = self.evaluator_without_runtime()
        previous = {"status": "PASS", "run_id": "offline-only", "dataset_sha256": self.dataset_hash}
        runner.save_new(self.directory / "app-smoke.json", previous)
        self.assertEqual(previous, evaluator.app_smoke())
        evaluator.execute_json.assert_not_called()

    def app_calls(self):
        material = {"material_id": 10, "source_revision": 1, "source_hash": "a" * 64}
        rows = [{"call_id": str(index), "purpose": purpose, "material_id": 10, "user_id": 20,
                 "source_revision": 1, "source_hash": "a" * 64, "state": "SUCCEEDED", "trace_id": None,
                 "dispatched_at": "observed", "input_tokens": 10, "output_tokens": 5, "cached_tokens": 0,
                 "reasoning_tokens": 0, "reserved_cost_nusd": 10000, "observed_cost_nusd": 1000}
                for index, purpose in enumerate(["query", "answer"])]
        return material, {"calls": rows, "incomplete_dispatch": False}

    def test_app_chat_attributes_only_exact_two_required_calls(self):
        material, after = self.app_calls()
        usage = runner.app_chat_usage({"calls": [], "incomplete_dispatch": False}, after, material, 20)
        self.assertEqual(2, usage["requests_actual"])
        self.assertEqual(["0", "1"], usage["provider_call_ids"])
        self.assertNotIn("provider_trace_id", usage)

    def test_app_chat_refuses_interleaved_or_inflight_usage(self):
        material, after = self.app_calls()
        after["calls"].append({**after["calls"][0], "call_id": "unrelated"})
        with self.assertRaisesRegex(RuntimeError, "APP_SMOKE_ACCOUNTING_AMBIGUOUS"):
            runner.app_chat_usage({"calls": []}, after, material, 20)
        material, after = self.app_calls()
        after["incomplete_dispatch"] = True
        with self.assertRaisesRegex(RuntimeError, "APP_SMOKE_ACCOUNTING_INFLIGHT"):
            runner.app_chat_usage({"calls": []}, after, material, 20)

    def test_each_case_rechecks_ai_identity_and_stopped_local_consumers(self):
        evaluator = self.evaluator_without_runtime()
        evaluator.manifest = SimpleNamespace(run_id="offline-only", digest="approved")
        session = self.directory / "session.json"
        session.write_text(json.dumps({"state": "OPEN", "manifest_sha256": "approved", "live_ai_id": "expected-ai"}))
        rows = {"ai": {"id": "expected-ai", "state": "running"},
                "worker": {"state": "exited"}, "index-dispatcher": {"state": "exited"}}
        evaluator.live = SimpleNamespace(SESSION=session, preflight=Mock(return_value=evaluator.manifest),
                                        owned=Mock(return_value=rows))
        runner.Evaluation._session_matches(evaluator)
        for service, changed in [("ai", {"id": "replacement-ai", "state": "running"}),
                                  ("worker", {"state": "running"}), ("index-dispatcher", {"state": "running"})]:
            evaluator.live.owned.return_value = {**rows, service: changed}
            with self.subTest(service=service), self.assertRaisesRegex(RuntimeError, "ISOLATED_LIVE_SESSION_CHANGED"):
                runner.Evaluation._session_matches(evaluator)

    def test_app_smoke_mocked_full_flow_uses_same_session_and_submission_keys(self):
        evaluator = self.evaluator_without_runtime()
        evaluator._session_matches = Mock()
        public = {row["material_key"]: row for row in runner.phase5.public_materials(self.bundle)}
        smoke = self.bundle["smoke_manifest.json"]
        evaluator.materials = {row["id"]: {"material_key": row["id"], "material_id": 10 + index,
            "source_revision": 1, "source_hash": public[row["id"]]["source_hash"]}
            for index, row in enumerate(smoke["materials"])}
        evaluator.manifest = SimpleNamespace(run_id="offline-only", data={"materials": [
            {**row, "user_ids": [20], "purposes": ["query", "answer", "grading"]}
            for row in evaluator.materials.values()]})
        evaluator.execute_json = Mock(return_value={"variant": "A"})
        calls, chat_bodies, submission_bodies = [], [], []
        chat_results, attempts = {}, {}
        def add_call(material, purpose, trace=None):
            calls.append({"call_id": str(uuid.uuid4()), "purpose": purpose,
                "material_id": material["material_id"], "user_id": 20, "source_revision": 1,
                "source_hash": material["source_hash"], "state": "SUCCEEDED", "trace_id": trace,
                "dispatched_at": "observed", "input_tokens": 10, "output_tokens": 5, "cached_tokens": 0,
                "reasoning_tokens": 0, "reserved_cost_nusd": 10000, "observed_cost_nusd": 1000})
        def call(path, body=None, token=None, headers=None, service="be", timeout=20):
            if path == "/rag/chat":
                self.assertEqual(32, timeout)
                chat_bodies.append(copy.deepcopy(body))
                material = next(row for row in evaluator.materials.values() if str(row["material_id"]) == body["document_id"])
                key = material["material_key"]
                source = public[key]["source_map"][0]
                session = body.get("session_id") or str(uuid.uuid4())
                abstained = key == "live-smoke-recycling-v1"
                reference = {"document_id": body["document_id"], "source_revision": 1,
                    "source_hash": material["source_hash"], "chunk_position": 0,
                    "content_hash": source["content_hash"], "material_title": public[key]["title"],
                    "excerpt": " ".join(public[key]["chapters"][0]["content"].split())[:300]}
                data = {"answer": "합성 오프라인 응답", "document_id": body["document_id"],
                    "source_hash": material["source_hash"], "source_revision": 1, "retrieval_variant": "A",
                    "mode": {"configured_mode": "LIVE_OPENAI", "embedding_provider": "live_openai",
                             "answer_provider": "live_openai", "grading_provider": "live_openai"},
                    "session_id": session, "message_id": len(chat_bodies), "sources": [reference],
                    "cited_source_ids": [] if abstained else ["chunk-0-" + source["content_hash"][:16]],
                    "abstained": abstained}
                chat_results[session] = data
                add_call(material, "query")
                add_call(material, "answer")
                return 200, data, {}
            if path.startswith("/rag/chat/sessions/"):
                session = path.split("/")[4]
                data = chat_results[session]
                if "/sources/" in path:
                    return 200, data["sources"][0], {}
                return 200, {"messages": [{"id": data["message_id"], "content": data["answer"],
                                           "sources": data["sources"]}]}, {}
            material_id = int(path.split("/")[3])
            material = next(row for row in evaluator.materials.values() if row["material_id"] == material_id)
            if path.endswith("/quizzes"):
                case = next(row for row in smoke["grading_cases"] if row["material_id"] == material["material_key"])
                return 200, [{"id": material_id * 10, "version": 0, "content": case["question"]}], {}
            if path.endswith("/quizzes/submit"):
                submission_bodies.append((headers["Idempotency-Key"], copy.deepcopy(body)))
                key = headers["Idempotency-Key"]
                if key not in attempts:
                    attempt = str(uuid.uuid4())
                    answer = body["answers"][0]
                    attempts[key] = (attempt, [{"snapshotAvailable": True, "attemptId": attempt,
                        "question_id": answer["quizId"], "student_answer": answer["answer"],
                        "is_correct": True, "ai_feedback": "합성 피드백"}])
                    add_call(material, "grading", attempt)
                attempt, results = attempts[key]
                return 200, results, {"X-Grading-Attempt-Id": attempt, "X-Grading-State": "SUCCEEDED"}
            attempt = path.rsplit("/", 1)[1]
            return 200, next(results for identity, results in attempts.values() if identity == attempt), {}
        client = SimpleNamespace(user={"userId": 20}, token="never-sent-real-token", call=call)
        evaluator.client = client
        evaluator.client_refresh = Mock(return_value=client)
        evaluator.ledger = Mock(side_effect=lambda: {"calls": copy.deepcopy(calls), "incomplete_dispatch": False})
        result = evaluator.app_smoke()
        self.assertEqual("PASS", result["status"])
        self.assertEqual(8, result["requests_actual"])
        self.assertEqual(chat_results[chat_bodies[1]["session_id"]]["session_id"], chat_bodies[1]["session_id"])
        self.assertNotIn("session_id", chat_bodies[2])
        self.assertEqual(4, len(submission_bodies))
        self.assertEqual(submission_bodies[0], submission_bodies[1])
        self.assertEqual(submission_bodies[2], submission_bodies[3])
        self.assertTrue(all(set(body) == {"answers"} for _, body in submission_bodies))
        self.assertEqual(5, len(list((self.directory / "app-smoke-observations").glob("*.json"))))

    def test_local_http_client_retains_legacy_timeout_and_accepts_live_deadline(self):
        from verify_student_demo import Client
        client = object.__new__(Client)
        client.bases = {"be": "http://127.0.0.1:18082", "ai": "http://127.0.0.1:18000"}
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b'{}'
        response.status = 200
        response.headers = {}
        client.opener = Mock()
        client.opener.open.return_value = response
        client.call("/api/session/me")
        self.assertEqual(20, client.opener.open.call_args.kwargs["timeout"])
        client.call("/rag/chat", service="ai", body={"question": "offline"}, timeout=32)
        self.assertEqual(32, client.opener.open.call_args.kwargs["timeout"])


if __name__ == "__main__":
    unittest.main()
