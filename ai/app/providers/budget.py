"""One durable, conservative run budget shared by CLI, API and worker processes.

Costs are integer nano-US dollars. An unresolved dispatch halts the run; neither
process restart nor timeout releases its reservation. This is not an invoice.
"""
from datetime import datetime, timezone
from contextlib import contextmanager
from contextvars import ContextVar
import os
from pathlib import Path
import sqlite3
from uuid import UUID, uuid4

from .contract import CHAT_MODEL, EMBEDDING_MODEL, Manifest, ProviderError

# Standard synchronous API prices, USD per million tokens, checked 2026-09-30:
# https://developers.openai.com/api/docs/pricing
# These integer rates are the equivalent nano-USD per token.
PRICES = {EMBEDDING_MODEL: {"input": 20, "cached": 20, "output": 0},
          CHAT_MODEL: {"input": 400, "cached": 100, "output": 1600}}
PRICE_VERSION = "openai-standard-2026-09-30"
FINAL_STATES = {"SUCCEEDED", "REFUSED", "TRUNCATED", "INVALID_RESPONSE", "HTTP_ERROR", "UNKNOWN"}
_TRACE_ID = ContextVar("live_provider_trace_id", default=None)


@contextmanager
def provider_trace(trace_id):
    """Correlate one app/evaluation request, including work offloaded to a thread."""
    try:
        if str(UUID(trace_id)) != trace_id:
            raise ValueError("Noncanonical trace")
    except (ValueError, TypeError, AttributeError):
        raise ProviderError("LIVE_TRACE_INVALID") from None
    token = _TRACE_ID.set(trace_id)
    try:
        yield
    finally:
        _TRACE_ID.reset(token)


def now():
    return datetime.now(timezone.utc).isoformat()


def cost_nusd(model, input_tokens, output_tokens=0, cached_tokens=0):
    values = [input_tokens, output_tokens, cached_tokens]
    if (model not in PRICES or any(type(item) is not int or item < 0 for item in values)
            or cached_tokens > input_tokens or (model == EMBEDDING_MODEL and output_tokens)):
        raise ProviderError("LIVE_USAGE_INVALID")
    price = PRICES[model]
    return ((input_tokens - cached_tokens) * price["input"]
            + cached_tokens * price["cached"] + output_tokens * price["output"])


class BudgetLedger:
    def __init__(self, path, manifest: Manifest):
        self.path = str(path)
        self.manifest = manifest
        if not Path(self.path).is_file():
            raise ProviderError("LIVE_BUDGET_NOT_INITIALIZED")
        with self._connect() as connection:
            self._run(connection)

    @classmethod
    def initialize(cls, path, manifest: Manifest):
        """Explicit preflight only; never replaces a file or resets an existing run."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
        except FileExistsError:
            if path.is_symlink() or not path.is_file():
                raise ProviderError("LIVE_BUDGET_INVALID") from None
        connection = sqlite3.connect(str(path), timeout=5)
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS live_runs (
                    run_id TEXT PRIMARY KEY, manifest_sha256 TEXT NOT NULL,
                    price_version TEXT NOT NULL, max_requests INTEGER NOT NULL,
                    max_cost_nusd INTEGER NOT NULL, created_at TEXT NOT NULL,
                    halted INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS live_calls (
                    call_id TEXT PRIMARY KEY, run_id TEXT NOT NULL,
                    model TEXT NOT NULL, purpose TEXT NOT NULL,
                    material_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
                    source_revision INTEGER NOT NULL, source_hash TEXT NOT NULL,
                    input_token_upper_bound INTEGER NOT NULL, max_output_tokens INTEGER NOT NULL,
                    reserved_cost_nusd INTEGER NOT NULL, state TEXT NOT NULL,
                    created_at TEXT NOT NULL, dispatched_at TEXT, completed_at TEXT,
                    provider_request_id TEXT, input_tokens INTEGER, cached_tokens INTEGER,
                    output_tokens INTEGER, reasoning_tokens INTEGER, observed_cost_nusd INTEGER,
                    latency_ms INTEGER, trace_id TEXT,
                    FOREIGN KEY(run_id) REFERENCES live_runs(run_id));
                CREATE INDEX IF NOT EXISTS live_calls_run ON live_calls(run_id);
            """)
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT manifest_sha256,price_version FROM live_runs WHERE run_id=?",
                                     (manifest.run_id,)).fetchone()
            if row and row != (manifest.digest, PRICE_VERSION):
                raise ProviderError("LIVE_BUDGET_MANIFEST_MISMATCH")
            if not row:
                connection.execute("INSERT INTO live_runs VALUES(?,?,?,?,?,?,0)",
                    (manifest.run_id, manifest.digest, PRICE_VERSION, manifest.max_requests,
                     manifest.max_cost_nusd, now()))
            connection.commit()
        except (sqlite3.Error, OSError):
            connection.rollback()
            raise ProviderError("LIVE_BUDGET_INVALID") from None
        finally:
            connection.close()
        return cls(path, manifest)

    @contextmanager
    def _connect(self):
        connection = None
        try:
            if Path(self.path).is_symlink():
                raise ProviderError("LIVE_BUDGET_INVALID")
            # mode=rw is essential: a removed ledger must not silently reset cost.
            uri = Path(self.path).absolute().as_uri() + "?mode=rw"
            connection = sqlite3.connect(uri, uri=True, timeout=5)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA synchronous=FULL")
            with connection:
                yield connection
        except (sqlite3.Error, OSError):
            raise ProviderError("LIVE_BUDGET_INVALID") from None
        finally:
            if connection is not None:
                connection.close()

    def _run(self, connection):
        try:
            row = connection.execute("SELECT * FROM live_runs WHERE run_id=?", (self.manifest.run_id,)).fetchone()
            if row is None:
                raise ProviderError("LIVE_BUDGET_NOT_INITIALIZED")
            if row["manifest_sha256"] != self.manifest.digest or row["price_version"] != PRICE_VERSION:
                raise ProviderError("LIVE_BUDGET_MANIFEST_MISMATCH")
            return row
        except sqlite3.Error:
            raise ProviderError("LIVE_BUDGET_INVALID") from None

    def reserve(self, *, model, scope, input_token_upper_bound, max_output_tokens):
        if type(input_token_upper_bound) is not int or input_token_upper_bound <= 0:
            raise ProviderError("LIVE_INPUT_TOO_LARGE")
        reserved = cost_nusd(model, input_token_upper_bound, max_output_tokens)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            run = self._run(connection)
            if run["halted"]:
                raise ProviderError("LIVE_RUN_HALTED")
            pending = connection.execute("SELECT COUNT(*) FROM live_calls WHERE run_id=? AND state IN ('RESERVED','DISPATCHED')",
                                         (self.manifest.run_id,)).fetchone()[0]
            if pending:
                raise ProviderError("LIVE_CONCURRENCY_LIMIT")
            count, consumed = connection.execute("SELECT COUNT(*),COALESCE(SUM(COALESCE(observed_cost_nusd,reserved_cost_nusd)),0) FROM live_calls WHERE run_id=?",
                                                (self.manifest.run_id,)).fetchone()
            if count >= run["max_requests"]:
                raise ProviderError("LIVE_REQUEST_LIMIT")
            if consumed + reserved > run["max_cost_nusd"]:
                raise ProviderError("LIVE_COST_LIMIT")
            call_id = str(uuid4())
            connection.execute("""INSERT INTO live_calls
                (call_id,run_id,model,purpose,material_id,user_id,source_revision,source_hash,
                 input_token_upper_bound,max_output_tokens,reserved_cost_nusd,state,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,'RESERVED',?)""",
                (call_id, self.manifest.run_id, model, scope.purpose, scope.material_id,
                 scope.user_id, scope.source_revision, scope.source_hash, input_token_upper_bound,
                 max_output_tokens, reserved, now()))
            connection.execute("UPDATE live_calls SET trace_id=? WHERE call_id=?", (_TRACE_ID.get(), call_id))
            return call_id

    def dispatched(self, call_id):
        with self._connect() as connection:
            changed = connection.execute("UPDATE live_calls SET state='DISPATCHED',dispatched_at=? WHERE call_id=? AND run_id=? AND state='RESERVED'",
                                         (now(), call_id, self.manifest.run_id)).rowcount
            if changed != 1:
                raise ProviderError("LIVE_BUDGET_STATE_INVALID")

    def finish(self, call_id, *, state, usage=None, request_id=None, latency_ms=0):
        if state not in FINAL_STATES or type(latency_ms) is not int or latency_ms < 0:
            raise ProviderError("LIVE_BUDGET_STATE_INVALID")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM live_calls WHERE call_id=? AND run_id=?",
                                     (call_id, self.manifest.run_id)).fetchone()
            if row is None or row["state"] not in {"RESERVED", "DISPATCHED"}:
                raise ProviderError("LIVE_BUDGET_STATE_INVALID")
            observed = None
            tokens = (None, None, None, None)
            if usage is not None:
                tokens = (usage["input_tokens"], usage["cached_tokens"], usage["output_tokens"], usage["reasoning_tokens"])
                observed = cost_nusd(row["model"], tokens[0], tokens[2], tokens[1])
                if type(tokens[3]) is not int or not 0 <= tokens[3] <= tokens[2]:
                    raise ProviderError("LIVE_USAGE_INVALID")
            if state == "UNKNOWN" or (observed is not None and observed > row["reserved_cost_nusd"]):
                connection.execute("UPDATE live_runs SET halted=1 WHERE run_id=?", (self.manifest.run_id,))
            connection.execute("""UPDATE live_calls SET state=?,completed_at=?,provider_request_id=?,
                input_tokens=?,cached_tokens=?,output_tokens=?,reasoning_tokens=?,observed_cost_nusd=?,latency_ms=?
                WHERE call_id=?""", (state, now(), request_id, *tokens, observed, latency_ms, call_id))

    def summary(self):
        with self._connect() as connection:
            run = self._run(connection)
            rows = [dict(row) for row in connection.execute("SELECT * FROM live_calls WHERE run_id=? ORDER BY created_at,call_id",
                                                           (self.manifest.run_id,))]
        pending = any(row["state"] in {"RESERVED", "DISPATCHED"} for row in rows)
        return {"run_id": self.manifest.run_id, "manifest_sha256": self.manifest.digest,
                "price_version": PRICE_VERSION, "requests_reserved": len(rows),
                "requests_dispatched": sum(row["dispatched_at"] is not None for row in rows),
                "calculated_observed_cost_nusd": sum(row["observed_cost_nusd"] or 0 for row in rows),
                "unresolved_reserved_cost_nusd": sum(row["reserved_cost_nusd"] for row in rows
                                                     if row["observed_cost_nusd"] is None),
                "input_tokens": sum(row["input_tokens"] or 0 for row in rows),
                "cached_tokens": sum(row["cached_tokens"] or 0 for row in rows),
                "output_tokens": sum(row["output_tokens"] or 0 for row in rows),
                # Reasoning is already included in output_tokens; never add it twice.
                "reasoning_tokens": sum(row["reasoning_tokens"] or 0 for row in rows),
                "halted": bool(run["halted"]), "incomplete_dispatch": pending,
                "actual_invoice_verified": False, "calls": rows}
