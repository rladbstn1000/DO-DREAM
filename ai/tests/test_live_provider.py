"""Offline contracts only. MockTransport cannot send a real provider request."""
import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import importlib
import json
import math
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx

from app.providers import BudgetLedger, CallScope, CHAT_MODEL, EMBEDDING_MODEL, LIVE_SPEC, LiveOpenAI, ProviderError
from app.providers.budget import cost_nusd, provider_trace
from app.providers.contract import canonical, load_manifest, manifest_from_dict
from app.providers.openai import authorize_scope, approved_material_ids, read_key_file


def manifest_data(**limits):
    return {"schema_version": 1, "run_id": str(uuid4()), "authorized": True,
            "approval_reference": "OFFLINE_TEST_ONLY; not real human authorization",
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "models": {"embedding": EMBEDDING_MODEL, "answer": CHAT_MODEL, "grading": CHAT_MODEL},
            "limits": {"max_requests": 20, "max_cost_usd": "1", "max_input_bytes": 16384,
                       "max_output_tokens": 1024, **limits},
            "dataset_sha256": "d" * 64, "isolation": {"verified": True, "evidence_sha256": "e" * 64},
            "allowed_roles": ["api", "worker", "cli"],
            "materials": [{"material_id": 101, "user_ids": [201, 301], "source_revision": 1,
                           "source_hash": "a" * 64, "spec": LIVE_SPEC,
                           "purposes": ["index", "query", "answer", "rewrite", "grading"]}]}


def scope(purpose="query"):
    return CallScope(101, 201, LIVE_SPEC, 1, "a" * 64, purpose)


SCHEMA = {"type": "object", "properties": {"is_correct": {"type": "boolean"},
          "feedback": {"type": "string", "maxLength": 2000}},
          "required": ["is_correct", "feedback"], "additionalProperties": False}
MESSAGES = [{"role": "system", "content": "Use only the supplied immutable snapshot."},
            {"role": "user", "content": "Synthetic offline fixture, not student data."}]


def embedding_response(*, dimensions=1536, input_tokens=10):
    return {"model": EMBEDDING_MODEL, "data": [{"index": 0, "embedding": [1.0] * dimensions}],
            "usage": {"prompt_tokens": input_tokens, "total_tokens": input_tokens}}


def chat_response(*, content=None, finish="stop", refusal=None, cached=0, reasoning=0):
    return {"model": CHAT_MODEL, "choices": [{"index": 0, "finish_reason": finish,
            "message": {"role": "assistant", "content": content if content is not None else
                        '{"is_correct":true,"feedback":"합성 대역 응답"}', "refusal": refusal}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30,
                      "prompt_tokens_details": {"cached_tokens": cached},
                      "completion_tokens_details": {"reasoning_tokens": reasoning}}}


class Fixture:
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.key_path = self.directory / "test-provider.env"
        self.key_path.write_text("OPENAI_API_KEY=sk-offline-fixture-not-a-real-key\n")
        self.key_path.chmod(0o600)
        self.manifest_path = self.directory / "manifest.json"
        self.data = manifest_data()
        self.manifest_path.write_text(canonical(self.data))
        self.manifest = load_manifest(self.manifest_path)
        self.path = self.directory / "budget.sqlite3"
        self.ledger = BudgetLedger.initialize(self.path, self.manifest)
        self.environment = patch.dict(os.environ, {
            "DODREAM_AI_MODE": "LIVE_OPENAI",
            "LIVE_API_AUTHORIZED": "true", "LIVE_RUN_MANIFEST": str(self.manifest_path),
            "LIVE_BUDGET_LEDGER": str(self.path), "LIVE_PROVIDER_KEY_FILE": str(self.key_path)}, clear=False)
        self.environment.start()
        self.requests = []

    def tearDown(self):
        self.environment.stop()
        self.temporary.cleanup()

    def provider(self, body=None, *, status=200, handler=None, role="api"):
        def record(request):
            self.requests.append(request)
            if handler:
                return handler(request)
            return httpx.Response(status, json=body if body is not None else embedding_response(),
                                  headers={"x-request-id": "req_offline_fixture"})
        return LiveOpenAI(self.manifest, self.ledger, role=role, key_file=self.key_path,
                          transport=httpx.MockTransport(record))


class ManifestAndKeyContract(Fixture, unittest.TestCase):
    def test_explicit_local_mode_blocks_authorized_environment_before_key_access(self):
        with patch.dict(os.environ, {"DODREAM_AI_MODE": "LOCAL_FAKE"}), \
             patch("app.providers.openai.read_key_file", side_effect=AssertionError("key accessed")):
            with self.assertRaisesRegex(ProviderError, "LIVE_MODE_REQUIRED"):
                LiveOpenAI.from_environment(role="api")

    def test_import_creates_no_http_client_or_key_read(self):
        with patch("httpx.AsyncClient", side_effect=AssertionError("import client")), \
             patch("app.providers.openai.read_key_file", side_effect=AssertionError("import secret")):
            importlib.reload(importlib.import_module("app.providers"))
            importlib.reload(importlib.import_module("app.providers.openai"))

    def test_default_authorization_denied_before_manifest_or_key_read(self):
        with patch.dict(os.environ, {"LIVE_API_AUTHORIZED": "false"}), \
             patch("app.providers.openai.load_manifest", side_effect=AssertionError("manifest accessed")), \
             patch("app.providers.openai.read_key_file", side_effect=AssertionError("key accessed")):
            with self.assertRaisesRegex(ProviderError, "LIVE_NOT_AUTHORIZED"):
                LiveOpenAI.from_environment(role="api")

    def test_false_manifest_cannot_be_enabled_by_environment(self):
        self.data["authorized"] = False
        self.manifest_path.write_text(canonical(self.data))
        with self.assertRaisesRegex(ProviderError, "LIVE_NOT_AUTHORIZED"):
            LiveOpenAI.from_environment(role="api")

    def test_missing_user_approval_is_denied(self):
        self.data["approval_reference"] = ""
        with self.assertRaisesRegex(ProviderError, "LIVE_APPROVAL_REFERENCE_REQUIRED"):
            manifest_from_dict(self.data)

    def test_isolation_and_expiry_required(self):
        self.data["isolation"]["verified"] = False
        with self.assertRaisesRegex(ProviderError, "LIVE_ISOLATION_REQUIRED"):
            manifest_from_dict(self.data)
        self.data["isolation"]["verified"] = True
        self.data["expires_at"] = "2000-01-01T00:00:00Z"
        with self.assertRaisesRegex(ProviderError, "LIVE_AUTHORIZATION_EXPIRED"):
            manifest_from_dict(self.data)

    def test_model_alias_substitution_rejected(self):
        self.data["models"]["answer"] = "gpt-4.1-mini"
        with self.assertRaisesRegex(ProviderError, "LIVE_MANIFEST_INVALID"):
            manifest_from_dict(self.data)

    def test_material_principal_source_space_and_purpose_are_exact(self):
        for change in [{"material_id": 102}, {"user_id": 999}, {"source_revision": 2},
                       {"source_hash": "b" * 64}, {"spec": "same-dim-different-model"},
                       {"resource_kind": "PDF"}, {"purpose": "quiz_generation"}]:
            with self.subTest(change=change), self.assertRaisesRegex(ProviderError, "LIVE_SCOPE_DENIED"):
                authorize_scope(replace(scope(), **change), "api")
        self.assertEqual(frozenset({101}), approved_material_ids("worker"))

    def test_worker_cannot_answer_and_api_cannot_index(self):
        for purpose, role in [("query", "worker"), ("index", "api")]:
            with self.assertRaisesRegex(ProviderError, "LIVE_ROLE_DENIED"):
                authorize_scope(scope(purpose), role)
        authorize_scope(scope("index"), "worker")

    def test_duplicate_manifest_field_is_rejected(self):
        self.manifest_path.write_text('{"authorized":false,"authorized":true}')
        with self.assertRaisesRegex(ProviderError, "LIVE_MANIFEST_INVALID"):
            load_manifest(self.manifest_path)

    def test_key_parser_is_allowlisted_and_never_executes_shell(self):
        for text in ["export OPENAI_API_KEY=sk-abcdefghijklmn", "OTHER_KEY=sk-abcdefghijklmn",
                     "OPENAI_API_KEY=$(touch sentinel)", "OPENAI_API_KEY=sk-abcdefghijklmn\nOPENAI_API_KEY=sk-abcdefghijklmn"]:
            self.key_path.write_text(text)
            with self.subTest(text=text), self.assertRaisesRegex(ProviderError, "LIVE_KEY_FILE_INVALID"):
                read_key_file(self.key_path)
        self.assertFalse((self.directory / "sentinel").exists())

    def test_key_rejects_group_readable_or_symlink(self):
        self.key_path.chmod(0o640)
        with self.assertRaisesRegex(ProviderError, "LIVE_KEY_FILE_INVALID"):
            read_key_file(self.key_path)
        self.key_path.chmod(0o600)
        alias = self.directory / "alias.env"
        alias.symlink_to(self.key_path)
        with self.assertRaisesRegex(ProviderError, "LIVE_KEY_FILE_INVALID"):
            read_key_file(alias)


class DurableBudgetContract(Fixture, unittest.TestCase):
    def reserve(self, ledger=None):
        return (ledger or self.ledger).reserve(model=CHAT_MODEL, scope=scope("grading"),
                                             input_token_upper_bound=100, max_output_tokens=10)

    def test_integer_prices_cached_discount_and_no_double_count_reasoning(self):
        self.assertEqual(20_000_000, cost_nusd(EMBEDDING_MODEL, 1_000_000))
        self.assertEqual(400_000_000, cost_nusd(CHAT_MODEL, 1_000_000))
        self.assertEqual(100_000_000, cost_nusd(CHAT_MODEL, 1_000_000, cached_tokens=1_000_000))
        self.assertEqual(1_600_000_000, cost_nusd(CHAT_MODEL, 0, output_tokens=1_000_000))
        call_id = self.reserve()
        self.ledger.dispatched(call_id)
        self.ledger.finish(call_id, state="SUCCEEDED", usage={"input_tokens": 100, "cached_tokens": 50,
            "output_tokens": 10, "reasoning_tokens": 4})
        result = self.ledger.summary()
        self.assertEqual(41_000, result["calculated_observed_cost_nusd"])
        self.assertEqual(10, result["output_tokens"])
        self.assertEqual(4, result["reasoning_tokens"])
        self.assertFalse(result["actual_invoice_verified"])

    def test_single_concurrency_is_shared_across_connections(self):
        self.reserve()
        second = BudgetLedger(self.path, self.manifest)
        with self.assertRaisesRegex(ProviderError, "LIVE_CONCURRENCY_LIMIT"):
            self.reserve(second)

    def test_concurrent_reservation_has_exactly_one_winner(self):
        barrier = threading.Barrier(2)
        results = []
        def reserve():
            ledger = BudgetLedger(self.path, self.manifest)
            barrier.wait()
            try:
                self.reserve(ledger)
                results.append("reserved")
            except ProviderError as error:
                results.append(error.code)
        threads = [threading.Thread(target=reserve) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
        self.assertCountEqual(["reserved", "LIVE_CONCURRENCY_LIMIT"], results)

    def test_unknown_keeps_reservation_and_halts_after_restart(self):
        call_id = self.reserve()
        self.ledger.dispatched(call_id)
        self.ledger.finish(call_id, state="UNKNOWN")
        restarted = BudgetLedger(self.path, self.manifest)
        self.assertEqual(56_000, restarted.summary()["unresolved_reserved_cost_nusd"])
        with self.assertRaisesRegex(ProviderError, "LIVE_RUN_HALTED"):
            self.reserve(restarted)

    def test_crash_leaves_inflight_record_blocking_restart(self):
        call_id = self.reserve()
        self.ledger.dispatched(call_id)
        with self.assertRaisesRegex(ProviderError, "LIVE_CONCURRENCY_LIMIT"):
            self.reserve(BudgetLedger(self.path, self.manifest))
        self.assertTrue(self.ledger.summary()["incomplete_dispatch"])

    def test_failure_and_explicit_retry_both_count(self):
        first = self.reserve()
        self.ledger.dispatched(first)
        self.ledger.finish(first, state="HTTP_ERROR")
        second = self.reserve()
        self.ledger.dispatched(second)
        self.ledger.finish(second, state="INVALID_RESPONSE")
        self.assertEqual(2, self.ledger.summary()["requests_dispatched"])
        self.assertEqual(112_000, self.ledger.summary()["unresolved_reserved_cost_nusd"])

    def test_request_cap_survives_process_restart(self):
        data = manifest_data(max_requests=1)
        manifest = manifest_from_dict(data)
        path = self.directory / "one.sqlite3"
        ledger = BudgetLedger.initialize(path, manifest)
        call_id = self.reserve(ledger)
        ledger.finish(call_id, state="HTTP_ERROR")
        with self.assertRaisesRegex(ProviderError, "LIVE_REQUEST_LIMIT"):
            self.reserve(BudgetLedger(path, manifest))

    def test_next_request_refused_before_budget_overrun(self):
        manifest = manifest_from_dict(manifest_data(max_cost_usd="0.000055999"))
        ledger = BudgetLedger.initialize(self.directory / "small.sqlite3", manifest)
        with self.assertRaisesRegex(ProviderError, "LIVE_COST_LIMIT"):
            self.reserve(ledger)
        self.assertEqual(0, ledger.summary()["requests_reserved"])

    def test_changed_manifest_and_missing_ledger_do_not_reset_budget(self):
        changed = json.loads(canonical(self.data))
        changed["limits"]["max_requests"] += 1
        with self.assertRaisesRegex(ProviderError, "LIVE_BUDGET_MANIFEST_MISMATCH"):
            BudgetLedger.initialize(self.path, manifest_from_dict(changed))
        missing = self.directory / "missing.sqlite3"
        with self.assertRaisesRegex(ProviderError, "LIVE_BUDGET_NOT_INITIALIZED"):
            BudgetLedger(missing, self.manifest)
        self.assertFalse(missing.exists())

    def test_reinitializing_same_manifest_preserves_existing_usage(self):
        call_id = self.reserve()
        self.ledger.finish(call_id, state="HTTP_ERROR")
        repeated = BudgetLedger.initialize(self.path, self.manifest)
        self.assertEqual(1, repeated.summary()["requests_reserved"])

    def test_trace_records_no_prompt_and_resets_after_request(self):
        trace_id = str(uuid4())
        with provider_trace(trace_id):
            call_id = self.reserve()
        self.ledger.finish(call_id, state="HTTP_ERROR")
        second = self.reserve()
        self.ledger.finish(second, state="HTTP_ERROR")
        calls = self.ledger.summary()["calls"]
        self.assertEqual(trace_id, calls[0]["trace_id"])
        self.assertIsNone(calls[1]["trace_id"])


class HTTPProviderContract(Fixture, unittest.IsolatedAsyncioTestCase):
    async def test_embedding_exact_request_dimensions_l2_and_usage(self):
        vectors = await self.provider().aembed(["직접 작성한 합성 본문"], scope())
        self.assertEqual(1536, len(vectors[0]))
        self.assertAlmostEqual(1.0, sum(number * number for number in vectors[0]), places=10)
        payload = json.loads(self.requests[0].content)
        self.assertEqual("https://api.openai.com/v1/embeddings", str(self.requests[0].url))
        self.assertEqual(1536, payload["dimensions"])
        self.assertEqual(EMBEDDING_MODEL, payload["model"])
        result = self.ledger.summary()
        self.assertEqual(1, result["requests_dispatched"])
        self.assertEqual(200, result["calculated_observed_cost_nusd"])
        self.assertEqual("req_offline_fixture", result["calls"][0]["provider_request_id"])

    async def test_structured_payload_snapshot_and_usage(self):
        value = await self.provider(chat_response(cached=10, reasoning=2)).structured(
            MESSAGES, SCHEMA, "grading", scope("grading"), max_output_tokens=100)
        self.assertTrue(value["is_correct"])
        payload = json.loads(self.requests[0].content)
        self.assertEqual(CHAT_MODEL, payload["model"])
        self.assertEqual(100, payload["max_completion_tokens"])
        self.assertTrue(payload["response_format"]["json_schema"]["strict"])
        self.assertEqual("default", payload["service_tier"])
        self.assertEqual(1, payload["n"])
        self.assertNotIn("reasoning_effort", payload)
        self.assertNotIn("tools", payload)
        self.assertEqual(21_000, self.ledger.summary()["calculated_observed_cost_nusd"])

    async def test_scope_denial_happens_before_key_budget_or_transport(self):
        provider = self.provider()
        with patch("app.providers.openai.read_key_file", side_effect=AssertionError("key accessed")):
            with self.assertRaisesRegex(ProviderError, "LIVE_SCOPE_DENIED"):
                await provider.aembed(["test"], replace(scope(), material_id=999))
        self.assertEqual([], self.requests)
        self.assertEqual(0, self.ledger.summary()["requests_reserved"])

    async def test_revocation_blocks_existing_provider_before_transport(self):
        provider = self.provider()
        self.data["authorized"] = False
        self.manifest_path.write_text(canonical(self.data))
        with self.assertRaisesRegex(ProviderError, "LIVE_NOT_AUTHORIZED"):
            await provider.aembed(["test"], scope())
        self.assertEqual([], self.requests)

    async def test_oversize_input_is_rejected_without_truncating_or_calling(self):
        with self.assertRaisesRegex(ProviderError, "LIVE_INPUT_TOO_LARGE"):
            await self.provider().aembed(["가" * 2000], scope())
        self.assertEqual([], self.requests)

    async def test_dimension_mismatch_never_returns_local_vector(self):
        with self.assertRaisesRegex(ProviderError, "LIVE_EMBEDDING_INVALID"):
            await self.provider(embedding_response(dimensions=8)).aembed(["test"], scope())
        self.assertEqual("INVALID_RESPONSE", self.ledger.summary()["calls"][0]["state"])

    async def test_nonfinite_vector_is_rejected(self):
        body = embedding_response()
        body["data"][0]["embedding"][0] = "NaN"
        with self.assertRaisesRegex(ProviderError, "LIVE_EMBEDDING_INVALID"):
            await self.provider(body).aembed(["test"], scope())

    async def test_refusal_is_not_false_grade(self):
        with self.assertRaisesRegex(ProviderError, "LIVE_REFUSAL"):
            await self.provider(chat_response(refusal="synthetic refusal")).structured(
                MESSAGES, SCHEMA, "grading", scope("grading"))
        self.assertEqual("REFUSED", self.ledger.summary()["calls"][0]["state"])

    async def test_truncation_is_not_false_grade(self):
        with self.assertRaisesRegex(ProviderError, "LIVE_OUTPUT_TRUNCATED"):
            await self.provider(chat_response(finish="length")).structured(
                MESSAGES, SCHEMA, "grading", scope("grading"))
        self.assertEqual("TRUNCATED", self.ledger.summary()["calls"][0]["state"])

    async def test_strict_response_rejects_wrong_type_and_extra_fields(self):
        for content in ['{"is_correct":"true","feedback":"x"}',
                        '{"is_correct":true,"feedback":"x","answer":"secret"}',
                        '{"is_correct":true,"is_correct":false,"feedback":"x"}']:
            with self.subTest(content=content), self.assertRaisesRegex(ProviderError, "LIVE_SCHEMA_INVALID"):
                await self.provider(chat_response(content=content)).structured(
                    MESSAGES, SCHEMA, "grading", scope("grading"))

    async def test_wrong_model_response_halts_without_fallback(self):
        body = embedding_response()
        body["model"] = "unapproved-model"
        with self.assertRaisesRegex(ProviderError, "LIVE_RESPONSE_MODEL_MISMATCH"):
            await self.provider(body).aembed(["test"], scope())
        self.assertTrue(self.ledger.summary()["halted"])

    async def test_http_rate_limit_has_no_automatic_retry(self):
        with self.assertRaisesRegex(ProviderError, "LIVE_HTTP_ERROR"):
            await self.provider({"error": "not exposed"}, status=429).aembed(["test"], scope())
        self.assertEqual(1, len(self.requests))
        self.assertGreater(self.ledger.summary()["unresolved_reserved_cost_nusd"], 0)

    async def test_redirect_does_not_forward_key_to_other_host(self):
        def redirect(_):
            return httpx.Response(307, headers={"location": "https://unapproved.example/collect"})
        with self.assertRaisesRegex(ProviderError, "LIVE_HTTP_ERROR"):
            await self.provider(handler=redirect).aembed(["test"], scope())
        self.assertEqual(["api.openai.com"], [request.url.host for request in self.requests])

    async def test_timeout_retains_reservation_halts_run_and_has_no_retry(self):
        def timeout(request):
            raise httpx.ReadTimeout("synthetic timeout; no real network", request=request)
        with self.assertRaises(ProviderError) as error:
            await self.provider(handler=timeout).aembed(["test"], scope())
        self.assertTrue(error.exception.unknown)
        self.assertEqual("LIVE_TIMEOUT_UNKNOWN", error.exception.code)
        self.assertEqual(1, len(self.requests))
        result = self.ledger.summary()
        self.assertTrue(result["halted"])
        self.assertEqual("UNKNOWN", result["calls"][0]["state"])
        self.assertGreater(result["unresolved_reserved_cost_nusd"], 0)

    async def test_total_deadline_is_distinct_from_read_timeout(self):
        async def slow(request):
            self.requests.append(request)
            await asyncio.sleep(0.1)
            return httpx.Response(200, json=embedding_response())
        provider = LiveOpenAI(self.manifest, self.ledger, role="api", key_file=self.key_path,
                              transport=httpx.MockTransport(slow))
        with patch("app.providers.openai.TOTAL_TIMEOUT_SECONDS", 0.01):
            with self.assertRaisesRegex(ProviderError, "LIVE_TIMEOUT_UNKNOWN"):
                await provider.aembed(["test"], scope())
        self.assertEqual(1, len(self.requests))
        self.assertTrue(self.ledger.summary()["halted"])

    async def test_usage_and_records_exclude_prompts_and_secret(self):
        await self.provider().aembed(["DO_NOT_RECORD_THIS_SYNTHETIC_PROMPT"], scope())
        rendered = canonical(self.ledger.summary())
        self.assertNotIn("DO_NOT_RECORD", rendered)
        self.assertNotIn("sk-offline", rendered)
        self.assertNotIn("Authorization", rendered)

    async def test_sync_wrapper_refuses_nested_event_loop_without_call(self):
        with self.assertRaisesRegex(ProviderError, "LIVE_SYNC_CALL_IN_EVENT_LOOP"):
            self.provider().embed(["test"], scope())
        self.assertEqual([], self.requests)


if __name__ == "__main__":
    unittest.main()
