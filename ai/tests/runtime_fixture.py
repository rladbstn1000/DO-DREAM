"""Synthetic, process-local auth fixture shared by both Python test suites."""
import base64
import os
import secrets
import tempfile
import time
import uuid

TEMP = tempfile.TemporaryDirectory(prefix="dodream-ai-unit-")
os.environ.update(
    APP_ENV="test", LOCAL_EXTERNAL_STUBS="true", JWT_ALGORITHM="HS256",
    JWT_ISSUER="dodream", JWT_AUDIENCE="dodream-api",
    JWT_SECRET_BASE64=base64.b64encode(secrets.token_bytes(64)).decode(),
    DATABASE_URL=f"sqlite:///{TEMP.name}/users.db",
    RAG_DATABASE_URL=f"sqlite:///{TEMP.name}/rag.db",
    LOCAL_PROVIDER_DATA_DIR=f"{TEMP.name}/provider",
)


def access_claims(subject="101", **changes):
    now = int(time.time())
    return {
        "sub": subject, "iss": "dodream", "aud": ["dodream-api"],
        "token_use": "access", "jti": str(uuid.uuid4()), "role": "STUDENT",
        "iat": now, "nbf": now, "exp": now + 60, **changes,
    }
