"""Internal evaluator input/accounting tests: no DB, token verification or network."""
import copy
import unittest

from app.evaluation_run import validate_payload, usage_for_trace
from app.providers import ProviderError


def payload():
    return {"access_token": "offline-never-verified-token", "material_id": 101, "cold": True,
            "case": {"id": "R01", "material_id": "water-lab-v1", "source_version": "authored-phase5-v1",
                     "question": "직접 작성한 질문", "history": [], "variant": "A",
                     "rewrite_for_retrieval": False, "top_k": 3}}


class EvaluationInputContract(unittest.TestCase):
    def test_accepts_only_projected_public_case(self):
        value = payload()
        self.assertEqual(value["case"], validate_payload(value, "A"))

    def test_gold_or_extra_context_is_rejected(self):
        for field in ["expected_key_points", "evidence_source_ids", "correct_answer", "context"]:
            value = payload()
            value["case"][field] = ["forbidden"]
            with self.subTest(field=field), self.assertRaisesRegex(ProviderError, "EVALUATION_INPUT_INVALID"):
                validate_payload(value, "A")

    def test_fixed_history_is_not_replaced_with_gold(self):
        value = payload()
        value["case"].update(variant="B", rewrite_for_retrieval=True,
                             history=[{"role": "user", "content": "고정된 이전 질문"},
                                      {"role": "assistant", "content": "고정된 이전 답변"}])
        original = copy.deepcopy(value)
        validate_payload(value, "B")
        self.assertEqual(original, value)
        value["case"]["history"][0]["expected"] = "gold"
        with self.assertRaisesRegex(ProviderError, "EVALUATION_INPUT_INVALID"):
            validate_payload(value, "B")

    def test_cli_variant_and_top_k_cannot_differ_from_frozen_case(self):
        value = payload()
        with self.assertRaisesRegex(ProviderError, "EVALUATION_INPUT_INVALID"):
            validate_payload(value, "B")
        value["case"]["top_k"] = 5
        with self.assertRaisesRegex(ProviderError, "EVALUATION_INPUT_INVALID"):
            validate_payload(value, "A")

    def test_summary_excludes_other_api_traffic_and_counts_rewrite(self):
        def call(identity, trace, model_input, cost):
            return {"call_id": identity, "trace_id": trace, "dispatched_at": "observed",
                    "input_tokens": model_input, "output_tokens": 5, "cached_tokens": 1,
                    "reasoning_tokens": 0, "observed_cost_nusd": cost, "reserved_cost_nusd": 10000}
        summary = {"calls": [call("rewrite", "this-case", 20, 500),
                             call("query", "this-case", 10, 200),
                             call("answer", "this-case", 30, 1000),
                             call("other-api", "another-case", 999, 999)]}
        result = usage_for_trace(summary, "this-case")
        self.assertEqual(3, result["requests_actual"])
        self.assertEqual(["rewrite", "query", "answer"], result["provider_call_ids"])
        self.assertEqual(60, result["usage"]["input_tokens"])
        self.assertEqual("0.0000017", result["computed_cost_usd"])
        self.assertEqual("0.00003", result["reserved_cost_usd"])
        self.assertFalse(result["actual_invoice_verified"])

    def test_timeout_usage_stays_unknown_and_reservation_is_retained(self):
        summary = {"calls": [{"call_id": "timeout", "trace_id": "this-case", "dispatched_at": "observed",
                    "input_tokens": None, "output_tokens": None, "cached_tokens": None,
                    "reasoning_tokens": None, "observed_cost_nusd": None, "reserved_cost_nusd": 10000}]}
        result = usage_for_trace(summary, "this-case")
        self.assertEqual(1, result["requests_actual"])
        self.assertIsNone(result["usage"]["input_tokens"])
        self.assertIsNone(result["computed_cost_usd"])
        self.assertEqual("0.00001", result["reserved_cost_usd"])


if __name__ == "__main__":
    unittest.main()
