import copy
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / "phase5.py"
spec = importlib.util.spec_from_file_location("phase5_evaluation", MODULE)
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)


class EvaluationContracts(unittest.TestCase):
    def setUp(self):
        self.bundle = evaluation.load()
        self.hash = "a" * 64

    def record(self, ident="R01", variant="A", status="SUCCESS"):
        case = next(c for c in self.bundle["rag_gold.json"]["cases"] if c["id"] == ident)
        evidence = case["evidence_source_ids"]
        return {"dataset_sha256": self.hash, "run_id": "offline-contract-fixture",
                "kind": "rag", "case_id": ident, "variant": variant,
                "material_id": case["material_id"], "source_version": case["source_version"],
                "status": status, "answer": "합성 계약 검사 응답", "abstained": case["expected_absence"],
                "retrieved_source_ids": evidence, "context_source_ids": evidence, "cited_source_ids": evidence,
                "requests_actual": 2, "usage": {"input_tokens": 100, "output_tokens": 30,
                "cached_input_tokens": 20, "reasoning_tokens": 0}, "computed_cost_usd": "0.000082",
                "reserved_cost_usd": "0.002", "cold": False,
                "latency_ms": {"query_embedding": 50, "vector_search": 12, "answer": 100, "total": 170}}

    def test_frozen_sizes_categories_meaningful_chunk_count(self):
        result = evaluation.validate(self.bundle)
        self.assertEqual(result["rag_cases"], 24)
        self.assertEqual(result["grading_cases"], 16)
        self.assertEqual(result["evaluation_chunks"], 16)
        for material in evaluation.public_materials(self.bundle, include_smoke=False):
            self.assertEqual([s["chunk_position"] for s in material["source_map"]], list(range(8)))

    def test_projection_has_no_gold_and_history_is_identical(self):
        for case in self.bundle["rag_gold.json"]["cases"]:
            a = evaluation.project_rag_case(case["id"], "A", self.bundle)
            b = evaluation.project_rag_case(case["id"], "B", self.bundle)
            evaluation.assert_public(a)
            evaluation.assert_public(b)
            self.assertEqual(a["question"], b["question"])
            self.assertEqual(a["history"], b["history"])
            self.assertFalse(a["rewrite_for_retrieval"])
            self.assertEqual(b["rewrite_for_retrieval"], bool(case["history"]))
        evaluation.assert_public(evaluation.public_materials(self.bundle))

    def test_gold_poison_cannot_enter_projection(self):
        case = self.bundle["rag_gold.json"]["cases"][0]
        case["answer"] = "injected expected answer"
        case["evidence_source_ids"] = ["secret-label"]
        projected = evaluation.project_rag_case(case["id"], "A", self.bundle)
        self.assertNotIn("injected", json.dumps(projected))
        self.assertNotIn("secret-label", json.dumps(projected))

    def test_nested_gold_rejected(self):
        with self.assertRaisesRegex(ValueError, "Evaluator field"):
            evaluation.assert_public({"a": [{"expected_is_correct": True}]})

    def test_split_concept_duplication_rejected(self):
        self.bundle["rag_gold.json"]["cases"][1]["concept_id"] = self.bundle["rag_gold.json"]["cases"][0]["concept_id"]
        with self.assertRaisesRegex(ValueError, "Concept repeats"):
            evaluation.validate(self.bundle)

    def test_corpus_snapshot_digest_matches_app_canonical_contract(self):
        material = evaluation.public_materials(self.bundle)[0]
        expected = {"blocks": [{"text": c["content"], "type": "content"} for c in material["chapters"]]}
        self.assertEqual(material["source_hash"], evaluation.digest(expected))
        self.assertNotIn("quizzes", material)

    def test_actual_runtime_sources_map_without_gold(self):
        material = evaluation.public_materials(self.bundle)[0]
        source = material["source_map"][3]
        raw = {"chunk_position": 3, "content_hash": source["content_hash"],
               "source_hash": material["source_hash"]}
        cited = f"chunk-3-{source['content_hash'][:16]}"
        result = evaluation.map_runtime_sources(material["material_key"], material["source_hash"],
                                                [raw], [cited], self.bundle)
        self.assertEqual(result["cited_source_ids"], [source["source_id"]])
        # The mapper has no need for expected evidence or grading gold.
        public_only = {"corpus.json": self.bundle["corpus.json"], "smoke_manifest.json": self.bundle["smoke_manifest.json"]}
        self.assertEqual(result, evaluation.map_runtime_sources(material["material_key"], material["source_hash"],
                                                               [raw], [cited], public_only))

    def test_runtime_map_rejects_revision_content_and_unseen_citations(self):
        material = evaluation.public_materials(self.bundle)[0]
        source = material["source_map"][0]
        raw = {"chunk_position": 0, "content_hash": source["content_hash"], "source_hash": material["source_hash"]}
        with self.assertRaisesRegex(ValueError, "not provided"):
            evaluation.map_runtime_sources(material["material_key"], material["source_hash"], [raw], ["invented"], self.bundle)
        raw["content_hash"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "chunk hash"):
            evaluation.map_runtime_sources(material["material_key"], material["source_hash"], [raw], [], self.bundle)

    def test_long_section_rejected_instead_of_silent_different_chunks(self):
        self.bundle["corpus.json"]["materials"][0]["sections"][0]["text"] = "가" * 900
        with self.assertRaisesRegex(ValueError, "one plain"):
            evaluation.public_materials(self.bundle)

    def test_server_quiz_mismatch_rejected(self):
        self.bundle["server_quizzes.json"]["materials"][0]["quizzes"][0]["correct_answer"] = "wrong"
        with self.assertRaisesRegex(ValueError, "Server quiz differs"):
            evaluation.validate(self.bundle)

    def test_freeze_once_and_tamper_fails_without_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            for name in evaluation.FILES:
                shutil.copyfile(evaluation.DATA / name, data / name)
            first = evaluation.freeze(data)
            original = (data / "freeze.json").read_bytes()
            self.assertEqual(evaluation.freeze(data), first)
            path = data / "corpus.json"
            path.write_text(path.read_text() + "\n")
            with self.assertRaisesRegex(ValueError, "Frozen inputs changed"):
                evaluation.freeze(data)
            self.assertEqual((data / "freeze.json").read_bytes(), original)

    def test_duplicate_json_field_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "x.json"
            path.write_text('{"id":1,"id":2}')
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                evaluation.read_json(path)

    def test_no_records_is_not_run_not_zero_quality(self):
        report = evaluation.metrics([], self.bundle, self.hash)
        self.assertEqual(report["execution"], "NOT_RUN")
        self.assertIsNone(report["variants"]["A"]["hit_at_3"])
        self.assertIsNone(report["grading"]["agreement"])
        self.assertIsNone(report["computed_cost_usd"])
        self.assertEqual(report["human_answer_quality_review"], "NOT_RUN")
        self.assertEqual(report["observed_requests_actual"], 0)

    def test_error_and_timeout_count_in_executed_denominator(self):
        records = [self.record("R01"), self.record("R02", status="ERROR"), self.record("R03", status="TIMEOUT")]
        report = evaluation.metrics(records, self.bundle, self.hash)
        self.assertEqual(report["variants"]["A"]["answerable_executed"], 3)
        self.assertEqual(report["variants"]["A"]["hit_at_3"], 1 / 3)
        self.assertEqual(report["execution"], "PARTIAL")
        self.assertEqual(report["latency_ms"]["total"]["TIMEOUT"]["n"], 1)

    def test_absence_behavior_is_not_semantic_quality(self):
        report = evaluation.metrics([self.record("R17")], self.bundle, self.hash)
        self.assertEqual(report["variants"]["A"]["reported_abstention_rate"], 1)
        self.assertEqual(report["semantic_grounding"], "NOT_RUN")
        self.assertEqual(report["model_adoption"], "DEFERRED")

    def test_unknown_cost_keeps_reservation_and_unknown_usage(self):
        r = self.record(status="TIMEOUT")
        r["computed_cost_usd"] = None
        r["usage"] = dict.fromkeys(r["usage"], None)
        report = evaluation.metrics([r], self.bundle, self.hash)
        self.assertEqual(report["unknown_cost_records"], 1)
        self.assertIsNone(report["computed_cost_usd"])
        self.assertEqual(report["reserved_cost_usd"], "0.002")
        self.assertEqual(report["usage"]["input_tokens"]["unknown_records"], 1)

    def test_unknown_and_unpassed_citation_rejected(self):
        r = self.record()
        r["cited_source_ids"] = ["water-lab-v1-08"]
        with self.assertRaisesRegex(ValueError, "were not retrieved"):
            evaluation.metrics([r], self.bundle, self.hash)
        r["cited_source_ids"] = ["invented"]
        with self.assertRaisesRegex(ValueError, "Unknown/duplicate"):
            evaluation.metrics([r], self.bundle, self.hash)

    def test_wrong_material_version_and_dataset_rejected(self):
        for key, value in (("material_id", "reuse-lab-v1"), ("source_version", "old"), ("dataset_sha256", "old")):
            with self.subTest(key=key):
                r = self.record()
                r[key] = value
                with self.assertRaises(ValueError):
                    evaluation.metrics([r], self.bundle, self.hash)

    def test_not_run_cannot_claim_requests(self):
        with self.assertRaisesRegex(ValueError, "cannot claim"):
            evaluation.metrics([self.record(status="NOT_RUN")], self.bundle, self.hash)

    def test_duplicate_observations_are_not_summed(self):
        r = self.record()
        with self.assertRaisesRegex(ValueError, "Duplicate case"):
            evaluation.metrics([r, copy.deepcopy(r)], self.bundle, self.hash)

    def test_invalid_usage_types_counts_costs_rejected(self):
        for value in (-1, True, 1.5):
            r = self.record()
            r["requests_actual"] = value
            with self.assertRaises(ValueError):
                evaluation.metrics([r], self.bundle, self.hash)
        r = self.record()
        r["usage"]["cached_input_tokens"] = 101
        with self.assertRaisesRegex(ValueError, "exceed input"):
            evaluation.metrics([r], self.bundle, self.hash)
        r = self.record()
        r["computed_cost_usd"] = "NaN"
        with self.assertRaisesRegex(ValueError, "Invalid cost"):
            evaluation.metrics([r], self.bundle, self.hash)

    def test_review_escapes_actual_text_and_contains_no_script(self):
        r = self.record()
        r["answer"] = '<script src="https://example.invalid"></script>'
        output = evaluation.review_html([r], self.bundle, self.hash)
        self.assertNotIn("<script", output)
        self.assertIn("&lt;script", output)
        self.assertIn("default-src 'none'", output)
        self.assertIn("사람 검토 NOT_RUN", output)

    def test_prepare_offline_never_opens_socket(self):
        with patch("socket.socket", side_effect=AssertionError("Network forbidden")):
            evaluation.validate(self.bundle)
            evaluation.public_materials(self.bundle)
            evaluation.review_html([], self.bundle, self.hash)

    def test_grading_failure_is_not_a_boolean_false_prediction(self):
        c = self.bundle["grading_gold.json"]["cases"][2]
        r = self.record(status="TIMEOUT")
        r.update(kind="grading", case_id=c["id"], material_id=c["material_id"],
                 source_version=c["source_version"], is_correct=False)
        r.pop("variant")
        report = evaluation.metrics([r], self.bundle, self.hash)
        self.assertFalse(c["expected_is_correct"])
        self.assertEqual(report["grading"]["agreement_numerator"], 0)
        self.assertEqual(report["grading"]["agreement"], 0)

    def test_unobserved_cold_marker_is_explicit_and_not_counted_as_warm(self):
        r = self.record()
        r["cold"] = None
        report = evaluation.metrics([r], self.bundle, self.hash)
        self.assertEqual(report["cold_warm_total_latency_ms"]["unknown"]["n"], 1)
        self.assertEqual(report["cold_warm_total_latency_ms"]["warm"]["n"], 0)
        self.assertEqual(report["cold_warm_total_latency_ms"]["cold"]["n"], 0)
        r.pop("cold")
        with self.assertRaisesRegex(ValueError, "Missing cold/warm marker"):
            evaluation.metrics([r], self.bundle, self.hash)

    def test_output_creation_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "review.html"
            evaluation.write_once(path, "first")
            with self.assertRaises(FileExistsError):
                evaluation.write_once(path, "second")
            self.assertEqual(path.read_text(), "first")


if __name__ == "__main__":
    unittest.main()
