"""Fixed, opt-in OpenAI HTTP boundary with no SDK/LangChain automatic retries.

httpx 0.28.1 is already pinned by the application. No client exists at import.
Only embeddings and Chat Completions are permitted. No arbitrary URL, tools,
redirects, proxies from the environment, or local response fallback exists.
"""
import asyncio
import math
import os
from pathlib import Path
import re
import stat
import time

import httpx

from .budget import BudgetLedger
from .contract import (CHAT_MODEL, DIMENSIONS, EMBEDDING_MODEL, CallScope, ProviderError,
                       canonical, load_manifest, strict_json)

API_ORIGIN = "https://api.openai.com"
ENDPOINTS = {"/v1/embeddings", "/v1/chat/completions"}
READ_TIMEOUT_SECONDS = 5.0
TOTAL_TIMEOUT_SECONDS = 8.0
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
REQUEST_ID = re.compile(r"[A-Za-z0-9_-]{1,200}\Z")


def environment_manifest():
    if os.getenv("DODREAM_AI_MODE", "LOCAL_FAKE") != "LIVE_OPENAI":
        raise ProviderError("LIVE_MODE_REQUIRED")
    if os.getenv("LIVE_API_AUTHORIZED", "false") != "true":
        raise ProviderError("LIVE_NOT_AUTHORIZED")
    path = os.getenv("LIVE_RUN_MANIFEST")
    if not path:
        raise ProviderError("LIVE_MANIFEST_REQUIRED")
    return load_manifest(path)


def authorize_scope(scope: CallScope, role):
    """Check before DB claim or any key access; this function performs no network I/O."""
    manifest = environment_manifest()
    manifest.authorize(scope, role)


def approved_material_ids(role):
    manifest = environment_manifest()
    if role not in manifest.data["allowed_roles"]:
        raise ProviderError("LIVE_ROLE_DENIED")
    return frozenset(item["material_id"] for item in manifest.data["materials"])


def read_key_file(path):
    """Parse one variable as data. Never source a shell or inspect another key file."""
    descriptor = None
    try:
        source = Path(path).expanduser()
        before = source.lstat()
        if (not stat.S_ISREG(before.st_mode) or before.st_mode & 0o077
                or before.st_size > 4096):
            raise ProviderError("LIVE_KEY_FILE_INVALID")
        descriptor = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        after = os.fstat(descriptor)
        if (before.st_ino, before.st_dev) != (after.st_ino, after.st_dev):
            raise ProviderError("LIVE_KEY_FILE_INVALID")
        with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
            descriptor = None
            lines = stream.read(4097)
        if len(lines.encode("utf-8")) > 4096:
            raise ProviderError("LIVE_KEY_FILE_INVALID")
        value = None
        for line in lines.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if not line.startswith("OPENAI_API_KEY=") or value is not None:
                raise ProviderError("LIVE_KEY_FILE_INVALID")
            value = line.split("=", 1)[1].strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            if not re.fullmatch(r"sk-[A-Za-z0-9_-]{12,500}", value):
                raise ProviderError("LIVE_KEY_FILE_INVALID")
        if value is None:
            raise ProviderError("LIVE_KEY_FILE_INVALID")
        return value
    except (OSError, UnicodeError, ValueError):
        raise ProviderError("LIVE_KEY_FILE_INVALID") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _usage(body, model):
    usage = body.get("usage")
    if type(usage) is not dict:
        raise ProviderError("LIVE_USAGE_INVALID")
    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens", 0) if model == EMBEDDING_MODEL else usage.get("completion_tokens")
    if (type(prompt) is not int or prompt < 0 or type(completion) is not int or completion < 0
            or type(usage.get("total_tokens")) is not int
            or usage["total_tokens"] != prompt + completion):
        raise ProviderError("LIVE_USAGE_INVALID")
    prompt_details = usage.get("prompt_tokens_details") or {}
    completion_details = usage.get("completion_tokens_details") or {}
    if type(prompt_details) is not dict or type(completion_details) is not dict:
        raise ProviderError("LIVE_USAGE_INVALID")
    cached = prompt_details.get("cached_tokens", 0)
    reasoning = completion_details.get("reasoning_tokens", 0)
    if (type(cached) is not int or not 0 <= cached <= prompt
            or type(reasoning) is not int or not 0 <= reasoning <= completion
            or (model == EMBEDDING_MODEL and (completion or cached or reasoning))):
        raise ProviderError("LIVE_USAGE_INVALID")
    return {"input_tokens": prompt, "cached_tokens": cached,
            "output_tokens": completion, "reasoning_tokens": reasoning}


def _schema_valid(value, schema):
    """Validate our narrow strict output schemas again after Structured Outputs."""
    kind = schema.get("type")
    if kind == "object":
        if (type(value) is not dict or schema.get("additionalProperties") is not False
                or set(value) != set(schema.get("required", []))
                or set(value) != set(schema.get("properties", {}))):
            return False
        return all(_schema_valid(value[key], child) for key, child in schema["properties"].items())
    if kind == "array":
        return (type(value) is list and schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", 50)
                and all(_schema_valid(item, schema["items"]) for item in value))
    if kind == "string":
        if type(value) is not str:
            return False
        try:
            value.encode("utf-8")
        except UnicodeError:
            return False
        return (schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", 2000)
                and ("enum" not in schema or value in schema["enum"]))
    if kind == "boolean":
        return type(value) is bool
    if kind == "integer":
        return (type(value) is int and schema.get("minimum", -(2**63)) <= value <= schema.get("maximum", 2**63-1)
                and ("enum" not in schema or value in schema["enum"]))
    return False


def _schema_supported(schema, *, depth=0):
    if type(schema) is not dict or depth > 5:
        return False
    kind = schema.get("type")
    if kind == "object":
        fields = schema.get("properties")
        required = schema.get("required")
        return (set(schema) <= {"type", "properties", "required", "additionalProperties"}
                and schema.get("additionalProperties") is False and type(fields) is dict and bool(fields)
                and type(required) is list and len(set(required)) == len(required) and set(fields) == set(required)
                and all(_schema_supported(child, depth=depth+1) for child in fields.values()))
    if kind == "array":
        return (set(schema) <= {"type", "items", "minItems", "maxItems"}
                and all(type(schema[key]) is int and 0 <= schema[key] <= 50
                        for key in ("minItems", "maxItems") if key in schema)
                and schema.get("minItems", 0) <= schema.get("maxItems", 50)
                and _schema_supported(schema.get("items"), depth=depth+1))
    allowed = {"string": {"type", "minLength", "maxLength", "enum"},
               "integer": {"type", "minimum", "maximum", "enum"}, "boolean": {"type"}}
    if kind not in allowed or not set(schema) <= allowed[kind]:
        return False
    bound_names = ("minLength", "maxLength") if kind == "string" else ("minimum", "maximum")
    if any(type(schema[name]) is not int for name in bound_names if name in schema):
        return False
    if kind == "string" and not 0 <= schema.get("minLength", 0) <= schema.get("maxLength", 2000) <= 4000:
        return False
    if kind == "integer" and schema.get("minimum", -(2**63)) > schema.get("maximum", 2**63-1):
        return False
    if "enum" in schema:
        expected_type = str if kind == "string" else int
        if (type(schema["enum"]) is not list or not 1 <= len(schema["enum"]) <= 50
                or any(type(value) is not expected_type for value in schema["enum"])):
            return False
    return True


class LiveOpenAI:
    def __init__(self, manifest, ledger, *, role, key_file, transport=None):
        if role not in manifest.data["allowed_roles"]:
            raise ProviderError("LIVE_ROLE_DENIED")
        if ledger.manifest.digest != manifest.digest:
            raise ProviderError("LIVE_BUDGET_MANIFEST_MISMATCH")
        self.manifest, self.ledger, self.role = manifest, ledger, role
        self.key_file = str(key_file)
        # Only test code injects an offline httpx.MockTransport. Production uses
        # AsyncHTTPTransport(retries=0), created inside the bounded request.
        self._transport = transport

    @classmethod
    def from_environment(cls, *, role):
        manifest = environment_manifest()
        ledger_path = os.getenv("LIVE_BUDGET_LEDGER")
        if not ledger_path:
            raise ProviderError("LIVE_BUDGET_REQUIRED")
        return cls(manifest, BudgetLedger(ledger_path, manifest), role=role,
                   key_file=os.getenv("LIVE_PROVIDER_KEY_FILE", "~/.config/dodream/provider-live.env"))

    def authorize(self, scope):
        if os.getenv("DODREAM_AI_MODE", "LOCAL_FAKE") != "LIVE_OPENAI":
            raise ProviderError("LIVE_MODE_REQUIRED")
        if os.getenv("LIVE_API_AUTHORIZED", "false") != "true":
            raise ProviderError("LIVE_NOT_AUTHORIZED")
        current = load_manifest(self.manifest.path) if self.manifest.path else self.manifest
        if current.digest != self.manifest.digest:
            raise ProviderError("LIVE_BUDGET_MANIFEST_MISMATCH")
        current.authorize(scope, self.role)

    async def _request(self, *, endpoint, payload, scope, max_output_tokens, validate):
        self.authorize(scope)
        if endpoint not in ENDPOINTS:
            raise ProviderError("LIVE_ENDPOINT_DENIED")
        try:
            encoded = canonical(payload).encode("utf-8")
        except (ValueError, UnicodeError, TypeError):
            raise ProviderError("LIVE_INPUT_INVALID") from None
        if len(encoded) > self.manifest.data["limits"]["max_input_bytes"]:
            raise ProviderError("LIVE_INPUT_TOO_LARGE")
        # UTF-8 bytes bound byte-level BPE tokens conservatively, plus 4,096 for
        # bounded chat/JSON-schema framing. This is a reservation, not usage.
        token_bound = len(encoded) + 4096
        key = read_key_file(self.key_file)
        call_id = self.ledger.reserve(model=payload["model"], scope=scope,
            input_token_upper_bound=token_bound, max_output_tokens=max_output_tokens)
        started = time.monotonic()
        usage, request_id, final_state = None, None, "UNKNOWN"
        try:
            async with asyncio.timeout(TOTAL_TIMEOUT_SECONDS):
                transport = self._transport or httpx.AsyncHTTPTransport(retries=0, verify=True)
                async with httpx.AsyncClient(transport=transport,
                    timeout=httpx.Timeout(READ_TIMEOUT_SECONDS, connect=2.0, write=2.0, pool=2.0),
                    follow_redirects=False, trust_env=False) as client:
                    self.ledger.dispatched(call_id)
                    async with client.stream("POST", API_ORIGIN + endpoint,
                        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
                        content=encoded) as response:
                        raw_request_id = response.headers.get("x-request-id", "")
                        request_id = raw_request_id if REQUEST_ID.fullmatch(raw_request_id) else None
                        if response.status_code != 200:
                            # Do not read/log upstream error bodies; their billing
                            # status is unverified and the reservation stays held.
                            final_state = "UNKNOWN" if response.status_code >= 500 else "HTTP_ERROR"
                            raise ProviderError("LIVE_HTTP_ERROR", unknown=final_state == "UNKNOWN")
                        raw = bytearray()
                        async for chunk in response.aiter_bytes():
                            raw.extend(chunk)
                            if len(raw) > MAX_RESPONSE_BYTES:
                                raise ProviderError("LIVE_RESPONSE_TOO_LARGE", unknown=True)
            try:
                body = strict_json(bytes(raw))
            except (ValueError, UnicodeError):
                raise ProviderError("LIVE_RESPONSE_INVALID", unknown=True) from None
            if type(body) is not dict or body.get("model") != payload["model"]:
                raise ProviderError("LIVE_RESPONSE_MODEL_MISMATCH", unknown=True)
            usage = _usage(body, payload["model"])
            if usage["input_tokens"] > token_bound or usage["output_tokens"] > max_output_tokens:
                raise ProviderError("LIVE_USAGE_EXCEEDED_RESERVATION", unknown=True)
            result = validate(body)
            final_state = "SUCCEEDED"
            return result
        except (TimeoutError, httpx.TimeoutException, asyncio.CancelledError):
            raise ProviderError("LIVE_TIMEOUT_UNKNOWN", unknown=True) from None
        except httpx.HTTPError:
            raise ProviderError("LIVE_TRANSPORT_UNKNOWN", unknown=True) from None
        except ProviderError as error:
            if error.code == "LIVE_REFUSAL":
                final_state = "REFUSED"
            elif error.code == "LIVE_OUTPUT_TRUNCATED":
                final_state = "TRUNCATED"
            elif not error.unknown and final_state != "HTTP_ERROR":
                final_state = "INVALID_RESPONSE"
            raise
        except Exception:
            raise ProviderError("LIVE_RESPONSE_INVALID", unknown=True) from None
        finally:
            self.ledger.finish(call_id, state=final_state, usage=usage, request_id=request_id,
                               latency_ms=max(0, int((time.monotonic() - started) * 1000)))

    async def aembed(self, texts, scope):
        if (scope.purpose not in {"index", "query"} or type(texts) is not list or not 1 <= len(texts) <= 8
                or any(type(text) is not str or not text.strip() for text in texts)):
            raise ProviderError("LIVE_INPUT_INVALID")
        try:
            if any(len(text.encode("utf-8")) > 4096 for text in texts):
                raise ProviderError("LIVE_INPUT_TOO_LARGE")
        except UnicodeError:
            raise ProviderError("LIVE_INPUT_INVALID") from None
        def validate(body):
            data = body.get("data")
            if (type(data) is not list or len(data) != len(texts)
                    or any(type(item) is not dict for item in data)
                    or any(type(item.get("index")) is not int for item in data)
                    or {item.get("index") for item in data} != set(range(len(texts)))):
                raise ProviderError("LIVE_EMBEDDING_INVALID")
            vectors = []
            for item in sorted(data, key=lambda item: item["index"]):
                vector = item.get("embedding")
                if (type(vector) is not list or len(vector) != DIMENSIONS
                        or any(type(number) not in {float, int} or not math.isfinite(number) for number in vector)):
                    raise ProviderError("LIVE_EMBEDDING_INVALID")
                norm = math.sqrt(sum(number * number for number in vector))
                if not math.isfinite(norm) or norm <= 0:
                    raise ProviderError("LIVE_EMBEDDING_INVALID")
                vectors.append([number / norm for number in vector])
            return vectors
        return await self._request(endpoint="/v1/embeddings", scope=scope, max_output_tokens=0,
            payload={"model": EMBEDDING_MODEL, "input": texts, "dimensions": DIMENSIONS, "encoding_format": "float"},
            validate=validate)

    def embed(self, texts, scope):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.aembed(texts, scope))
        raise ProviderError("LIVE_SYNC_CALL_IN_EVENT_LOOP")

    async def structured(self, messages, schema, schema_name, scope, *, max_output_tokens=512):
        if (scope.purpose not in {"answer", "rewrite", "grading"}
                or type(messages) is not list or not 1 <= len(messages) <= 20
                or any(type(item) is not dict or set(item) != {"role", "content"}
                       or item["role"] not in {"system", "user", "assistant"}
                       or type(item["content"]) is not str for item in messages)
                or not isinstance(schema_name, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", schema_name)
                or type(max_output_tokens) is not int
                or not 1 <= max_output_tokens <= self.manifest.data["limits"]["max_output_tokens"]
                or not _schema_supported(schema) or schema.get("type") != "object"):
            raise ProviderError("LIVE_INPUT_INVALID")
        def validate(body):
            choices = body.get("choices")
            if type(choices) is not list or len(choices) != 1 or type(choices[0]) is not dict:
                raise ProviderError("LIVE_SCHEMA_INVALID")
            choice = choices[0]
            message = choice.get("message")
            if type(message) is not dict:
                raise ProviderError("LIVE_SCHEMA_INVALID")
            if message.get("refusal"):
                raise ProviderError("LIVE_REFUSAL")
            if choice.get("finish_reason") == "length":
                raise ProviderError("LIVE_OUTPUT_TRUNCATED")
            if choice.get("finish_reason") != "stop" or message.get("tool_calls"):
                raise ProviderError("LIVE_SCHEMA_INVALID")
            raw = message.get("content")
            if type(raw) is not str or len(raw) > 32768:
                raise ProviderError("LIVE_SCHEMA_INVALID")
            try:
                result = strict_json(raw)
                if not _schema_valid(result, schema):
                    raise ValueError("Schema mismatch")
            except (ValueError, TypeError, UnicodeError, KeyError):
                raise ProviderError("LIVE_SCHEMA_INVALID") from None
            return result
        return await self._request(endpoint="/v1/chat/completions", scope=scope, max_output_tokens=max_output_tokens,
            payload={"model": CHAT_MODEL, "messages": messages, "temperature": 0, "n": 1,
                     "max_completion_tokens": max_output_tokens, "service_tier": "default", "store": False,
                     "response_format": {"type": "json_schema", "json_schema": {
                         "name": schema_name, "strict": True, "schema": schema}}}, validate=validate)
