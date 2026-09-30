"""One approved synthetic RAG observation through the real application chain.

An internal CLI only, never an HTTP endpoint. Receives an actual short-lived
student access token over stdin, verifies existing JWT/current DB permissions,
then runs the same VersionedRagChain used by /rag/chat with fixed public history.
Gold labels are not accepted or imported. The host evaluator maps the returned
genuine chunk references to its stable IDs and keeps semantic review separate.
"""
from __future__ import annotations

import argparse
import asyncio
from decimal import Decimal
import json
import os
import re
import sys
import time
from uuid import uuid4

from app.providers.contract import ProviderError, strict_json
from app.providers.budget import provider_trace

MAX_INPUT_BYTES = 65536
CASE_FIELDS = {"id", "material_id", "source_version", "question", "history",
               "variant", "rewrite_for_retrieval", "top_k"}


def validate_payload(payload, variant):
    if (type(payload) is not dict or set(payload) != {"access_token", "case", "material_id", "cold"}
            or type(payload["access_token"]) is not str or not 1 <= len(payload["access_token"]) <= 8192
            or type(payload["material_id"]) is not int or not 0 < payload["material_id"] <= 2**63-1
            or type(payload["cold"]) is not bool):
        raise ProviderError("EVALUATION_INPUT_INVALID")
    case = payload["case"]
    if (type(case) is not dict or set(case) != CASE_FIELDS
            or type(case["id"]) is not str or re.fullmatch(r"R(?:0[1-9]|1[0-9]|2[0-4])", case["id"]) is None
            or case["material_id"] not in {"water-lab-v1", "reuse-lab-v1"}
            or case["source_version"] != "authored-phase5-v1"
            or case["variant"] != variant or variant not in {"A", "B"}
            or type(case["top_k"]) is not int or case["top_k"] != 3
            or type(case["question"]) is not str or not 1 <= len(case["question"]) <= 4000
            or type(case["history"]) is not list or len(case["history"]) > 12
            or type(case["rewrite_for_retrieval"]) is not bool
            or case["rewrite_for_retrieval"] != (variant == "B" and bool(case["history"]))):
        raise ProviderError("EVALUATION_INPUT_INVALID")
    for row in case["history"]:
        if (type(row) is not dict or set(row) != {"role", "content"}
                or row["role"] not in {"user", "assistant"}
                or type(row["content"]) is not str or not 1 <= len(row["content"]) <= 4000):
            raise ProviderError("EVALUATION_INPUT_INVALID")
    if sum(len(row["content"]) for row in case["history"]) > 8000:
        raise ProviderError("EVALUATION_INPUT_INVALID")
    return case


def usage_for_trace(summary, trace_id):
    calls = [row for row in summary["calls"] if row.get("trace_id") == trace_id]
    complete = all(row["observed_cost_nusd"] is not None for row in calls)
    usage = {target: sum(row[source] or 0 for row in calls) if complete else None
             for target, source in (("input_tokens", "input_tokens"), ("output_tokens", "output_tokens"),
                                    ("cached_input_tokens", "cached_tokens"), ("reasoning_tokens", "reasoning_tokens"))}
    decimal_cost = lambda value: format(Decimal(value) / Decimal(1_000_000_000), "f")
    return {"requests_actual": sum(row["dispatched_at"] is not None for row in calls),
            "usage": usage,
            "computed_cost_usd": decimal_cost(sum(row["observed_cost_nusd"] or 0 for row in calls)) if complete else None,
            "reserved_cost_usd": decimal_cost(sum(row["reserved_cost_nusd"] for row in calls)),
            "provider_call_ids": [row["call_id"] for row in calls], "provider_trace_id": trace_id,
            "actual_invoice_verified": False}


async def run_observation(payload, variant):
    case = validate_payload(payload, variant)
    # Deferred imports are intentional: the CLI variant is fixed before config
    # import and this module can validate public input offline without app setup.
    from fastapi import HTTPException
    from fastapi.security import HTTPAuthorizationCredentials
    from langchain_core.messages import AIMessage, HumanMessage
    from app.common.db_session import SessionLocal
    from app.config import AI_MODE, RAG_RETRIEVAL_VARIANT
    from app.providers import LiveOpenAI
    from app.indexing.runtime import authorize_pointer
    from app.indexing.store import resolve_active
    from app.security.auth import get_current_user
    from app.security.authorization import require_material, student_only
    from app.rag.provenance import source_references
    from app.rag.router import revalidate_answer_source
    from app.rag.service import VersionedRagChain

    if AI_MODE != "LIVE_OPENAI" or RAG_RETRIEVAL_VARIANT != variant:
        raise ProviderError("EVALUATION_MODE_MISMATCH")
    client = LiveOpenAI.from_environment(role="api")
    trace_id = str(uuid4())
    started = time.monotonic()
    record = {"dataset_sha256": client.manifest.data["dataset_sha256"], "run_id": client.manifest.run_id,
              "kind": "rag", "case_id": case["id"], "variant": variant,
              "material_id": case["material_id"], "source_version": case["source_version"],
              "status": "ERROR", "answer": None, "abstained": None,
              "context_sources": [], "cited_runtime_source_ids": [], "cold": payload["cold"],
              "runtime_material_id": payload["material_id"], "latency_ms": {}}
    try:
        with SessionLocal() as db:
            user = await get_current_user(
                auth=HTTPAuthorizationCredentials(scheme="Bearer", credentials=payload["access_token"]), db=db)
            student_only(user)
            material = require_material(db, user, payload["material_id"])
            title = material.title
            pointer = resolve_active(db, user, str(payload["material_id"]))
        authorize_pointer(pointer, "query")
        record.update(source_revision=pointer["source_revision"], source_hash=pointer["source_hash"],
                      index_spec=pointer["spec"])
        history = [HumanMessage(content=row["content"]) if row["role"] == "user"
                   else AIMessage(content=row["content"]) for row in case["history"]]
        with provider_trace(trace_id):
            result = await asyncio.wait_for(VersionedRagChain(pointer).ainvoke(
                {"input": case["question"], "chat_history": history}), timeout=28)
        sources = source_references(pointer, result["context"], title)
        revalidate_answer_source(user.id, str(payload["material_id"]), pointer)
        authorize_pointer(pointer, "answer")
        record.update(status="SUCCESS", answer=result["answer"], abstained=result["abstained"],
                      context_sources=[source.model_dump() for source in sources],
                      cited_runtime_source_ids=result["cited_source_ids"],
                      latency_ms=result["stage_latency_ms"])
    except ProviderError as error:
        record["status"] = "TIMEOUT" if error.code == "LIVE_TIMEOUT_UNKNOWN" else "ERROR"
        record["error_code"] = error.code
    except TimeoutError:
        record["status"], record["error_code"] = "TIMEOUT", "EVALUATION_TOTAL_TIMEOUT"
    except HTTPException as error:
        record["error_code"] = "APPLICATION_HTTP_" + str(error.status_code)
    except Exception:
        record["error_code"] = "EVALUATION_APPLICATION_ERROR"
    finally:
        record["latency_ms"]["total"] = (time.monotonic() - started) * 1000
        record.update(usage_for_trace(client.ledger.summary(), trace_id))
    return record


def main():
    parser = argparse.ArgumentParser(description="One authorized synthetic RAG observation (stdin only).")
    parser.add_argument("--variant", required=True, choices=["A", "B"])
    args = parser.parse_args()
    # Internal process-local comparison, never a request-controlled HTTP setting.
    os.environ["DODREAM_RAG_VARIANT"] = args.variant
    execution_entered = False
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise ProviderError("EVALUATION_INPUT_TOO_LARGE")
        payload = strict_json(raw)
        validate_payload(payload, args.variant)
        execution_entered = True
        result = asyncio.run(run_observation(payload, args.variant))
    except ProviderError as error:
        result = {"status": "ERROR", "error_code": error.code,
                  "requests_actual": None if execution_entered else 0}
    except Exception:
        result = {"status": "ERROR", "error_code": "EVALUATION_PRECHECK_FAILED",
                  "requests_actual": None if execution_entered else 0}
    # Token and input payload are never echoed. Only synthetic output/evidence is
    # returned to the ignored local evaluator record; no external write occurs.
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0 if result["status"] == "SUCCESS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
