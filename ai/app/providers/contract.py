"""Small fixed model/scope contract; no environment or secret reads at import."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
import hashlib
import json
import re
from pathlib import Path
from uuid import UUID

EMBEDDING_MODEL = "text-embedding-3-small"
CHAT_MODEL = "gpt-4.1-mini-2025-04-14"
LIVE_SPEC = "openai-text-embedding-3-small-1536-l2-content-v1"
DIMENSIONS = 1536
PURPOSES = frozenset({"index", "query", "answer", "rewrite", "grading"})
ROLES = frozenset({"api", "worker", "cli"})
HEX = re.compile(r"[0-9a-f]{64}\Z")


class ProviderMode(str, Enum):
    LOCAL_FAKE = "LOCAL_FAKE"
    LIVE_OPENAI = "LIVE_OPENAI"


class ProviderError(RuntimeError):
    """Sanitized code only: provider bodies, prompts and keys never enter errors."""
    def __init__(self, code, *, unknown=False):
        self.code = code
        self.unknown = unknown
        super().__init__(code)


def strict_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON field")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _require(condition, code="LIVE_MANIFEST_INVALID"):
    if not condition:
        raise ProviderError(code)


def _integer(value, minimum=1, maximum=2**63-1):
    return type(value) is int and minimum <= value <= maximum


@dataclass(frozen=True)
class CallScope:
    material_id: int
    user_id: int
    spec: str
    source_revision: int
    source_hash: str
    purpose: str
    resource_kind: str = "MATERIAL"

    def validate(self):
        _require(self.resource_kind == "MATERIAL" and _integer(self.material_id)
                 and _integer(self.user_id) and _integer(self.source_revision)
                 and self.spec == LIVE_SPEC and isinstance(self.source_hash, str)
                 and HEX.fullmatch(self.source_hash) is not None
                 and self.purpose in PURPOSES, "LIVE_SCOPE_DENIED")


@dataclass(frozen=True)
class Manifest:
    data: dict
    digest: str
    path: str | None = None

    @property
    def run_id(self):
        return self.data["run_id"]

    @property
    def max_requests(self):
        return self.data["limits"]["max_requests"]

    @property
    def max_cost_nusd(self):
        return int(Decimal(self.data["limits"]["max_cost_usd"]) * 1_000_000_000)

    def authorize(self, scope, role):
        scope.validate()
        _require(self.data["authorized"] is True, "LIVE_NOT_AUTHORIZED")
        expiry = datetime.fromisoformat(self.data["expires_at"].replace("Z", "+00:00"))
        _require(expiry > datetime.now(timezone.utc), "LIVE_AUTHORIZATION_EXPIRED")
        _require(role in self.data["allowed_roles"], "LIVE_ROLE_DENIED")
        _require(role != "worker" or scope.purpose == "index", "LIVE_ROLE_DENIED")
        _require(role != "api" or scope.purpose != "index", "LIVE_ROLE_DENIED")
        _require(any(item["material_id"] == scope.material_id
                     and scope.user_id in item["user_ids"]
                     and item["source_revision"] == scope.source_revision
                     and item["source_hash"] == scope.source_hash
                     and item["spec"] == scope.spec
                     and scope.purpose in item["purposes"]
                     for item in self.data["materials"]), "LIVE_SCOPE_DENIED")


def manifest_from_dict(data, *, path=None, require_authorized=True):
    try:
        _require(type(data) is dict and set(data) == {"schema_version", "run_id", "authorized",
            "approval_reference", "expires_at", "models", "limits", "dataset_sha256",
            "isolation", "allowed_roles", "materials"})
        _require(data["schema_version"] == 1 and type(data["schema_version"]) is int)
        _require(str(UUID(data["run_id"])) == data["run_id"])
        _require(type(data["authorized"]) is bool)
        if require_authorized:
            _require(data["authorized"] is True, "LIVE_NOT_AUTHORIZED")
        _require(isinstance(data["approval_reference"], str)
                 and len(data["approval_reference"]) <= 500)
        if data["authorized"]:
            _require(bool(data["approval_reference"].strip()), "LIVE_APPROVAL_REFERENCE_REQUIRED")
        expiry = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
        _require(expiry.utcoffset() is not None and expiry.utcoffset().total_seconds() == 0)
        if require_authorized:
            _require(expiry > datetime.now(timezone.utc), "LIVE_AUTHORIZATION_EXPIRED")
        _require(data["models"] == {"embedding": EMBEDDING_MODEL, "answer": CHAT_MODEL, "grading": CHAT_MODEL})
        limits = data["limits"]
        _require(type(limits) is dict and set(limits) == {"max_requests", "max_cost_usd",
            "max_input_bytes", "max_output_tokens"})
        _require(_integer(limits["max_requests"], maximum=500))
        _require(isinstance(limits["max_cost_usd"], str)
                 and re.fullmatch(r"(?:0|[1-9][0-9]{0,5})(?:\.[0-9]{1,9})?", limits["max_cost_usd"]) is not None)
        cost = Decimal(limits["max_cost_usd"])
        _require(cost.is_finite() and cost > 0)
        _require(_integer(limits["max_input_bytes"], 256, 16384)
                 and _integer(limits["max_output_tokens"], 1, 1024))
        _require(isinstance(data["dataset_sha256"], str) and HEX.fullmatch(data["dataset_sha256"]) is not None)
        isolation = data["isolation"]
        _require(type(isolation) is dict and set(isolation) == {"verified", "evidence_sha256"}
                 and type(isolation["verified"]) is bool and isinstance(isolation["evidence_sha256"], str))
        if require_authorized or data["authorized"]:
            _require(isolation["verified"] is True
                     and HEX.fullmatch(isolation["evidence_sha256"]) is not None, "LIVE_ISOLATION_REQUIRED")
        roles = data["allowed_roles"]
        _require(type(roles) is list and bool(roles) and len(set(roles)) == len(roles)
                 and set(roles) <= ROLES)
        materials = data["materials"]
        _require(type(materials) is list and 1 <= len(materials) <= 16)
        material_ids = set()
        for item in materials:
            _require(type(item) is dict and set(item) == {"material_id", "user_ids", "source_revision",
                "source_hash", "spec", "purposes"})
            _require(_integer(item["material_id"]) and item["material_id"] not in material_ids)
            material_ids.add(item["material_id"])
            _require(type(item["user_ids"]) is list and 1 <= len(item["user_ids"]) <= 16
                     and all(_integer(value) for value in item["user_ids"])
                     and len(set(item["user_ids"])) == len(item["user_ids"]))
            _require(_integer(item["source_revision"]) and item["spec"] == LIVE_SPEC
                     and isinstance(item["source_hash"], str) and HEX.fullmatch(item["source_hash"]) is not None)
            _require(type(item["purposes"]) is list and bool(item["purposes"])
                     and len(set(item["purposes"])) == len(item["purposes"])
                     and set(item["purposes"]) <= PURPOSES)
        return Manifest(data, hashlib.sha256(canonical(data).encode()).hexdigest(), str(path) if path else None)
    except ProviderError:
        raise
    except (ValueError, TypeError, KeyError, OverflowError, AttributeError, InvalidOperation):
        raise ProviderError("LIVE_MANIFEST_INVALID") from None


def load_manifest(path, *, require_authorized=True):
    try:
        source = Path(path)
        if source.stat().st_size > 65536:
            raise ProviderError("LIVE_MANIFEST_INVALID")
        return manifest_from_dict(strict_json(source.read_text(encoding="utf-8")),
                                  path=str(source), require_authorized=require_authorized)
    except (OSError, UnicodeError, ValueError, TypeError):
        raise ProviderError("LIVE_MANIFEST_INVALID") from None
