#!/usr/bin/env python3
"""Frozen synthetic evaluation preparation and evidence review. Never calls a provider.

The app runner imports public_materials/project_rag_case only. Gold stays in this
offline evaluator; grading inputs must still come from the real app snapshot.
"""
import argparse
import collections
import copy
import datetime
from decimal import Decimal
import hashlib
import html
import json
from pathlib import Path
import statistics

DATA = Path(__file__).with_name("phase5_data")
ROOT = Path(__file__).resolve().parents[2]
FILES = ("corpus.json", "rag_gold.json", "grading_gold.json", "smoke_manifest.json",
         "server_quizzes.json", "plan.json")
FORBIDDEN = {"expected_key_points", "expected_absence", "expected_is_correct", "rubric",
             "forbidden_judgments", "evidence_source_ids", "correct_answer", "student_answer"}
STATUSES = {"SUCCESS", "ERROR", "TIMEOUT", "NOT_RUN"}
LATENCY_STAGES = {"rewrite", "query_embedding", "vector_search", "retrieval_including_query_embedding",
                  "answer", "grading", "total"}


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON field")
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def load(data=DATA):
    return {name: read_json(Path(data) / name) for name in FILES}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def assert_public(value):
    if isinstance(value, dict):
        require(not FORBIDDEN.intersection(value), "Evaluator field in public input")
        for child in value.values():
            assert_public(child)
    elif isinstance(value, list):
        for child in value:
            assert_public(child)


def public_materials(bundle=None, include_smoke=True):
    """Authored text only, matching content-v1's one short block = one chunk.

    Stable IDs map to runtime chunk_position and content_hash. Real resource IDs
    and source revisions must be recorded separately after normal publication.
    """
    bundle = bundle or load()
    materials = list(bundle["corpus.json"]["materials"])
    if include_smoke:
        materials += bundle["smoke_manifest.json"]["materials"]
    output = []
    for material in materials:
        chapters, mapping = [], []
        for position, section in enumerate(material["sections"]):
            normalized = " ".join(section["text"].split())
            require(0 < len(normalized) < 900 and "<" not in normalized,
                    "Evaluation section must be one plain content-v1 chunk")
            chapters.append({"id": section["source_id"], "type": "content",
                             "title": section["title"], "content": section["text"]})
            mapping.append({"source_id": section["source_id"], "chunk_position": position,
                            "content_hash": hashlib.sha256(normalized.encode()).hexdigest()})
        snapshot = {"blocks": [{"text": c["content"], "type": "content"} for c in chapters]}
        output.append({"material_key": material["id"], "title": material["title"],
                       "source_version": material["source_version"],
                       "source_hash": digest(snapshot), "chapters": chapters, "source_map": mapping})
    assert_public(output)
    return output


def project_rag_case(case_id, variant, bundle=None):
    """Strict allowlist. No labels, expected evidence, rubric or gold enters RAG."""
    require(variant in ("A", "B"), "Unknown variant")
    bundle = bundle or load()
    case = next(c for c in bundle["rag_gold.json"]["cases"] if c["id"] == case_id)
    result = {key: copy.deepcopy(case[key]) for key in
              ("id", "material_id", "source_version", "question", "history")}
    result["variant"] = variant
    result["rewrite_for_retrieval"] = variant == "B" and bool(case["history"])
    result["top_k"] = 3
    assert_public(result)
    return result


def map_runtime_sources(material_key, source_hash, context_sources, cited_ids, bundle=None):
    """Map genuine app positions/hashes to stable evaluator IDs, without a gold lookup.

    context_sources must be all chunks actually given to the answer model. These
    are not reconstructed from expected evidence or a generated source string.
    The caller also validates current authorization and runtime source revision.
    """
    materials = public_materials(bundle or load(), include_smoke=False)
    material = next((m for m in materials if m["material_key"] == material_key), None)
    require(material is not None and source_hash == material["source_hash"], "Runtime source hash mismatch")
    require(type(context_sources) is list and len(context_sources) <= 3, "Invalid runtime context")
    mapping = {s["chunk_position"]: s for s in material["source_map"]}
    stable, runtime_to_stable = [], {}
    for source in context_sources:
        position = source.get("chunk_position")
        require(type(position) is int and position in mapping, "Unknown runtime chunk position")
        expected = mapping[position]
        require(source.get("content_hash") == expected["content_hash"], "Runtime chunk hash mismatch")
        require(source.get("source_hash") == source_hash, "Runtime context source mismatch")
        require(expected["source_id"] not in stable, "Duplicate runtime source")
        stable.append(expected["source_id"])
        runtime_to_stable[f"chunk-{position}-{expected['content_hash'][:16]}"] = expected["source_id"]
    require(type(cited_ids) is list and all(type(v) is str for v in cited_ids), "Invalid runtime citations")
    require(len(cited_ids) == len(set(cited_ids)) and set(cited_ids) <= set(runtime_to_stable),
            "Runtime citation was not provided to model")
    return {"context_source_ids": stable,
            "cited_source_ids": [runtime_to_stable[value] for value in cited_ids]}


def validate(bundle):
    versions = {value["dataset_version"] for value in bundle.values()}
    require(versions == {"phase5-eval-v1"}, "Unexpected dataset version")
    materials = bundle["corpus.json"]["materials"]
    smoke = bundle["smoke_manifest.json"]["materials"]
    require(len(materials) == 2 and len(smoke) == 2, "Expected two evaluation and two smoke materials")
    all_materials = materials + smoke
    material_map = {m["id"]: m for m in all_materials}
    require(len(material_map) == 4, "Duplicate material ID")
    require(all(len(m["sections"]) > 3 for m in materials), "Top3 must not retrieve entire material")
    require(all(not m["use_in_retrieval_metrics"] and m["copied_from_version"] == "student-web-v1"
                for m in smoke), "Smoke copies are not retrieval benchmark")
    all_sections = [s for m in all_materials for s in m["sections"]]
    require(len({s["source_id"] for s in all_sections}) == len(all_sections), "Duplicate source ID")
    require(len({s["text"] for m in materials for s in m["sections"]}) == 16,
            "Evaluation chunks must be distinct authored passages")
    public_materials(bundle)
    rag = bundle["rag_gold.json"]["cases"]
    grade = bundle["grading_gold.json"]["cases"]
    require(len(rag) == 24 and len(grade) == 16, "Expected 24 RAG and 16 grading cases")
    require(collections.Counter(c["category"] for c in rag) ==
            {"direct": 8, "history": 8, "absence": 8}, "RAG categories changed")
    require(collections.Counter(c["category"] for c in grade) ==
            {"clear_correct": 4, "paraphrase": 4, "partial": 3, "wrong": 3, "negation": 2},
            "Grading coverage changed")
    for cases, expected_size in ((rag, 12), (grade, 8)):
        require(len({c["id"] for c in cases}) == len(cases), "Duplicate case ID")
        require(len({c["question"] for c in cases}) == len(cases), "Duplicate question")
        require(len({c["concept_id"] for c in cases}) == len(cases), "Concept repeats across splits")
        require(collections.Counter(c["split"] for c in cases) ==
                {"development": expected_size, "final": expected_size}, "Split counts changed")
        for case in cases:
            require(case["material_id"] in {m["id"] for m in materials}, "Case uses smoke/unknown material")
            m = material_map[case["material_id"]]
            require(case["source_version"] == m["source_version"], "Source version mismatch")
            available = {s["source_id"] for s in m["sections"]}
            require(set(case["evidence_source_ids"]) <= available, "Foreign evidence")
            require(bool(case["rubric"]) and bool(case["forbidden_judgments"]), "Missing rubric")
    for case in rag:
        require(type(case["expected_absence"]) is bool, "Invalid absence label")
        require(case["expected_absence"] == (case["category"] == "absence"), "Absence category mismatch")
        require(bool(case["evidence_source_ids"]) != case["expected_absence"], "Evidence/absence mismatch")
        require(bool(case["history"]) == (case["category"] == "history"), "History category mismatch")
        require(all(set(turn) == {"role", "content"} and turn["role"] in {"user", "assistant"}
                    and isinstance(turn["content"], str) and turn["content"] for turn in case["history"]),
                "Invalid fixed history")
        a, b = project_rag_case(case["id"], "A", bundle), project_rag_case(case["id"], "B", bundle)
        require(a["history"] == b["history"] and a["question"] == b["question"], "Unpaired inputs")
    for split in ("development", "final"):
        require(collections.Counter(c["category"] for c in rag if c["split"] == split) ==
                {"direct": 4, "history": 4, "absence": 4}, "Unbalanced RAG split")
    require(all(type(c["expected_is_correct"]) is bool for c in grade), "Nonboolean grading gold")
    quizzes = bundle["server_quizzes.json"]["materials"]
    require({m["material_id"] for m in quizzes} == set(material_map), "Quiz material scope changed")
    qmap = {q["evaluation_case_id"]: q for m in quizzes for q in m["quizzes"] if "evaluation_case_id" in q}
    require(set(qmap) == {c["id"] for c in grade}, "Quiz/case mapping changed")
    for case in grade:
        q = qmap[case["id"]]
        require(q["question"] == case["question"] and q["correct_answer"] == case["correct_answer"],
                "Server quiz differs from evaluator snapshot definition")
    plan = bundle["plan.json"]
    require(plan["live_api_authorized"] is False and plan["provider_calls_performed"] == 0,
            "Preparation plan cannot grant authorization or claim live calls")
    require(plan["retrieval"]["top_k"] == 3 and plan["retrieval"]["reranker"] is False,
            "Comparison retrieval contract changed")
    require(plan["models"] == {"embedding": "text-embedding-3-small", "dimensions": 1536,
            "answer": "gpt-4.1-mini-2025-04-14", "grading": "gpt-4.1-mini-2025-04-14",
            "rewrite": "gpt-4.1-mini-2025-04-14"}, "Unexpected model combination")
    return {"status": "PASS", "rag_cases": 24, "grading_cases": 16,
            "evaluation_materials": 2, "evaluation_chunks": 16, "smoke_materials": 2,
            "provider_requests": 0, "semantic_human_review": "NOT_RUN"}


def freeze(data=DATA):
    """Create once before outputs; an existing freeze is verified, never rewritten."""
    data = Path(data)
    bundle = load(data)
    validate(bundle)
    hashes = {name: hashlib.sha256((data / name).read_bytes()).hexdigest() for name in FILES}
    manifest = {"dataset_version": "phase5-eval-v1", "files_sha256": hashes,
                "dataset_sha256": digest(hashes), "outputs_observed_before_freeze": False,
                "frozen_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "semantic_human_review": "NOT_RUN", "provider_requests": 0}
    path = data / "freeze.json"
    if path.exists():
        old = read_json(path)
        require(old["files_sha256"] == hashes and old["dataset_sha256"] == digest(hashes),
                "Frozen inputs changed: preserve old freeze and use a new dataset version")
        require(old["outputs_observed_before_freeze"] is False, "Dataset was not prospectively frozen")
        return old
    with path.open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return manifest


def _nonnegative(value, field):
    require(type(value) is int and value >= 0, "Invalid " + field)


def validate_record(record, bundle, dataset_hash):
    """Validate observed evidence, never infer outputs or semantic success."""
    require(record.get("dataset_sha256") == dataset_hash, "Record uses different frozen dataset")
    require(record.get("status") in STATUSES, "Invalid observation status")
    require(isinstance(record.get("run_id"), str) and record["run_id"], "Missing run ID")
    kind = record.get("kind")
    require(kind in {"rag", "grading"}, "Invalid observation kind")
    cases = bundle["rag_gold.json" if kind == "rag" else "grading_gold.json"]["cases"]
    case = next((c for c in cases if c["id"] == record.get("case_id")), None)
    require(case is not None, "Unknown observed case")
    require(record.get("material_id") == case["material_id"] and
            record.get("source_version") == case["source_version"], "Observed material/version mismatch")
    if kind == "rag":
        require(record.get("variant") in {"A", "B"}, "Invalid observed variant")
        m = next(m for m in bundle["corpus.json"]["materials"] if m["id"] == case["material_id"])
        available = {s["source_id"] for s in m["sections"]}
        sets = []
        for key in ("retrieved_source_ids", "context_source_ids", "cited_source_ids"):
            values = record.get(key, [])
            require(type(values) is list and all(isinstance(v, str) for v in values), "Invalid source IDs")
            require(len(set(values)) == len(values) and set(values) <= available, "Unknown/duplicate source ID")
            require(len(values) <= 3, "More than fixed top3 sources")
            sets.append(set(values))
        require(sets[2] <= sets[1] <= sets[0], "Cited/context sources were not retrieved")
        if record["status"] == "SUCCESS":
            require(isinstance(record.get("answer"), str) and bool(record["answer"]), "Missing actual answer")
            require(type(record.get("abstained")) is bool, "Missing abstention observation")
    elif record["status"] == "SUCCESS":
        require(type(record.get("is_correct")) is bool, "Invalid grading observation")
    if record["status"] == "NOT_RUN":
        require(record.get("requests_actual", 0) == 0, "NOT_RUN cannot claim requests")
        return case
    _nonnegative(record.get("requests_actual"), "request count")
    usage = record.get("usage", {})
    require(set(usage) == {"input_tokens", "output_tokens", "cached_input_tokens", "reasoning_tokens"},
            "Missing usage dimensions (use null when unknown)")
    for name, value in usage.items():
        if value is not None:
            _nonnegative(value, name)
    require(usage["cached_input_tokens"] is None or usage["input_tokens"] is None or
            usage["cached_input_tokens"] <= usage["input_tokens"], "Cached tokens exceed input")
    require(usage["reasoning_tokens"] is None or usage["output_tokens"] is None or
            usage["reasoning_tokens"] <= usage["output_tokens"], "Reasoning tokens exceed output")
    for key in ("computed_cost_usd", "reserved_cost_usd"):
        value = record.get(key)
        require(value is None or isinstance(value, str), "Costs use decimal strings or null")
        if value is not None:
            amount = Decimal(value)
            require(amount.is_finite() and amount >= 0, "Invalid cost")
    require("cold" in record and (record["cold"] is None or type(record["cold"]) is bool),
            "Missing cold/warm marker (explicit null if not observed)")
    latency = record.get("latency_ms")
    require(isinstance(latency, dict) and "total" in latency, "Missing latency")
    require(set(latency) <= LATENCY_STAGES,
            "Unknown latency stage")
    for key, value in latency.items():
        require(type(value) in {int, float} and value >= 0 and value < float("inf"), "Invalid latency")
    return case


def metrics(records, bundle=None, dataset_hash=None):
    bundle = bundle or load()
    dataset_hash = dataset_hash or freeze()["dataset_sha256"]
    seen = set()
    for r in records:
        validate_record(r, bundle, dataset_hash)
        key = (r["kind"], r.get("variant"), r["case_id"])
        require(key not in seen, "Duplicate case observation; review distinct runs separately")
        seen.add(key)
    observed = [r for r in records if r["status"] != "NOT_RUN"]
    rag_gold = {c["id"]: c for c in bundle["rag_gold.json"]["cases"]}
    grade_gold = {c["id"]: c for c in bundle["grading_gold.json"]["cases"]}
    report = {"dataset_sha256": dataset_hash, "execution": "NOT_RUN" if not observed else "PARTIAL",
              "human_answer_quality_review": "NOT_RUN", "semantic_grounding": "NOT_RUN",
              "invoice_verified": False, "model_adoption": "DEFERRED", "variants": {}}
    for variant in ("A", "B"):
        rows = [r for r in observed if r["kind"] == "rag" and r["variant"] == variant]
        answerable = [r for r in rows if not rag_gold[r["case_id"]]["expected_absence"]]
        absent = [r for r in rows if rag_gold[r["case_id"]]["expected_absence"]]
        hits = sum(r["status"] == "SUCCESS" and bool(set(r.get("retrieved_source_ids", [])) &
                   set(rag_gold[r["case_id"]]["evidence_source_ids"])) for r in answerable)
        abstentions = sum(r["status"] == "SUCCESS" and r.get("abstained") is True for r in absent)
        report["variants"][variant] = {
            "executed": len(rows), "planned": 24, "status_counts": dict(collections.Counter(r["status"] for r in rows)),
            "answerable_executed": len(answerable), "answerable_planned": 16,
            "hit_at_3_numerator": hits, "hit_at_3": hits / len(answerable) if answerable else None,
            "absence_executed": len(absent), "absence_planned": 8,
            "reported_abstention_numerator": abstentions,
            "reported_abstention_rate": abstentions / len(absent) if absent else None,
            "source_structure": "PASS" if any(r["status"] == "SUCCESS" for r in rows) else "NOT_RUN"}
    grades = [r for r in observed if r["kind"] == "grading"]
    correct = sum(r["status"] == "SUCCESS" and r.get("is_correct") ==
                  grade_gold[r["case_id"]]["expected_is_correct"] for r in grades)
    report["grading"] = {"executed": len(grades), "planned": 16, "agreement_numerator": correct,
                         "agreement": correct / len(grades) if grades else None,
                         "status_counts": dict(collections.Counter(r["status"] for r in grades))}
    if len(observed) == 64:
        report["execution"] = "COMPLETE"  # execution completeness says nothing about quality
    report["observed_requests_actual"] = sum(r["requests_actual"] for r in observed)
    for key in ("computed_cost_usd", "reserved_cost_usd"):
        known = [Decimal(r[key]) for r in observed if r.get(key) is not None]
        report[key] = str(sum(known, Decimal(0))) if known else None
    report["unknown_cost_records"] = sum(r.get("computed_cost_usd") is None for r in observed)
    report["usage"] = {name: {"known_sum": sum(r["usage"][name] for r in observed if r["usage"][name] is not None),
                              "unknown_records": sum(r["usage"][name] is None for r in observed)}
                       for name in ("input_tokens", "output_tokens", "cached_input_tokens", "reasoning_tokens")}
    report["latency_ms"] = {}
    for stage in sorted(LATENCY_STAGES):
        report["latency_ms"][stage] = {}
        for label in ("SUCCESS", "ERROR", "TIMEOUT"):
            values = [r["latency_ms"][stage] for r in observed if r["status"] == label and stage in r["latency_ms"]]
            report["latency_ms"][stage][label] = {"n": len(values), "median": statistics.median(values) if values else None}
    report["cold_warm_total_latency_ms"] = {}
    for cold in (True, False, None):
        values = [r["latency_ms"]["total"] for r in observed if r["cold"] is cold]
        label = "unknown" if cold is None else "cold" if cold else "warm"
        report["cold_warm_total_latency_ms"][label] = {
            "n": len(values), "median": statistics.median(values) if values else None}
    report["accounting_scope"] = "These case observations only; task-wide smoke/UI/retry totals must come from shared durable provider ledger. Do not sum overlapping ledger and case costs."
    return report


def review_html(records, bundle, dataset_hash):
    report = metrics(records, bundle, dataset_hash)
    indexed = {(r["kind"], r.get("variant"), r["case_id"]): r for r in records}
    sources = {s["source_id"]: s["text"] for m in bundle["corpus.json"]["materials"] for s in m["sections"]}
    esc = lambda value: html.escape(str(value), quote=True)
    rows = []
    for case in bundle["rag_gold.json"]["cases"]:
        for variant in ("A", "B"):
            r = indexed.get(("rag", variant, case["id"]), {})
            actual_context = "\n\n".join(f"{sid}: {sources[sid]}" for sid in r.get("context_source_ids", []))
            expected = "\n".join(case["expected_key_points"])
            details = ("실제 생성 입력 구간: " + (actual_context or "NOT_RUN") +
                       "\n모델 인용 ID: " + ", ".join(r.get("cited_source_ids", [])))
            reason = "의미·근거 충실성은 사람 검토 NOT_RUN. 유효한 source ID만으로 근거 지지를 판정하지 않음."
            cells = [case["id"] + " / " + variant, case["split"] + " / " + case["category"],
                     case["question"] + "\n이전 대화: " + json.dumps(case["history"], ensure_ascii=False),
                     r.get("answer", "NOT_RUN"), details,
                     "Evaluator 전용 기대: " + expected + "\n금지: " + "; ".join(case["forbidden_judgments"]),
                     r.get("status", "NOT_RUN") + "\n" + reason]
            rows.append("<tr>" + "".join("<td>" + esc(v) + "</td>" for v in cells) + "</tr>")
    for case in bundle["grading_gold.json"]["cases"]:
        r = indexed.get(("grading", None, case["id"]), {})
        verdict = "NOT_RUN" if r.get("status") != "SUCCESS" else (
            "고정 합성 기대값 일치" if r["is_correct"] == case["expected_is_correct"] else "고정 합성 기대값 불일치")
        cells = [case["id"], case["split"] + " / " + case["category"], case["question"],
                 "학생 답안: " + case["student_answer"] + "\n실제 판정: " + str(r.get("is_correct", "NOT_RUN")),
                 "\n".join(sources[sid] for sid in case["evidence_source_ids"]),
                 "기대 판정: " + str(case["expected_is_correct"]) + "\n" + json.dumps(case["rubric"], ensure_ascii=False),
                 verdict + "\n전문가/실제 학생 평가 아님. 사람 검토 NOT_RUN."]
        rows.append("<tr>" + "".join("<td>" + esc(v) + "</td>" for v in cells) + "</tr>")
    return """<!doctype html><html lang="ko"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>DO:DREAM 5단계 로컬 평가 검토표</title><style>
body{font:15px/1.6 system-ui,sans-serif;margin:24px;color:#172c37;background:#f6f8f9}h1{font-size:24px}
table{border-collapse:collapse;width:100%;background:white}th,td{border:1px solid #bac7cc;padding:12px;vertical-align:top;white-space:pre-wrap;overflow-wrap:anywhere}th{background:#dfebed}td{min-width:180px}pre{white-space:pre-wrap}.scroll{overflow-x:auto}caption{text-align:left;font-weight:bold;padding:12px 0}
</style><h1>DO:DREAM 5단계 로컬 평가 검토표</h1>
<p>직접 작성한 내부 합성 자료입니다. 전문가 검증 또는 실제 학생 평가가 아닙니다. 표의 기대값은 evaluator만 사용합니다.
외부 요청을 수행하는 기능, 원격 자산, 유료 심판 모델은 없습니다. 관측 기록이 없으면 모든 실행·답변 검토는 NOT_RUN입니다.</p>
<p>Dataset SHA-256: """ + esc(dataset_hash) + "</p><details><summary>집계와 한계</summary><pre>" + esc(
        json.dumps(report, ensure_ascii=False, indent=2)) + "</pre></details><div class=scroll><table><caption>실제 답변·참고 구간·고정 기준·검토 필요 사유</caption><thead><tr>" + "".join(
        "<th scope=col>" + title + "</th>" for title in ["문항 / 비교군", "분리 / 유형", "질문과 고정 대화", "실제 답변/판정", "참고 구간", "Evaluator 기준", "실행/검토 상태"]) + "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div></html>"


def write_once(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "freeze", "export", "review"))
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--records", type=Path, help="One run's synthetic observation JSON array; optional")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    bundle = load(args.data)
    check = validate(bundle)
    if args.command == "validate":
        require((args.data / "freeze.json").is_file(), "Run freeze before validating final inputs")
    frozen = freeze(args.data)
    if args.command in {"validate", "freeze"}:
        print(json.dumps({**check, "dataset_sha256": frozen["dataset_sha256"]}, ensure_ascii=False))
        return
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    if args.command == "export":
        output = args.output or ROOT / ".local/phase5/evaluation" / (stamp + "-public-inputs.json")
        value = {"dataset_sha256": frozen["dataset_sha256"], "materials": public_materials(bundle),
                 "rag_cases": [project_rag_case(c["id"], v, bundle)
                               for c in bundle["rag_gold.json"]["cases"] for v in ("A", "B")]}
        assert_public(value)
        write_once(output, json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"status": "PASS", "output": str(output), "provider_requests": 0}))
    else:
        records = read_json(args.records) if args.records else []
        require(type(records) is list, "Observation file must be an array")
        output = args.output or ROOT / ".local/phase5/evaluation" / (stamp + "-review.html")
        write_once(output, review_html(records, bundle, frozen["dataset_sha256"]))
        report = metrics(records, bundle, frozen["dataset_sha256"])
        write_once(output.with_suffix(".json"), json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"execution": report["execution"], "output": str(output),
                          "human_review": "NOT_RUN", "provider_requests_performed_by_this_command": 0}))


if __name__ == "__main__":
    main()
