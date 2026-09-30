"""Runtime settings. Local provider doubles require an explicit local/test profile."""
import base64
import os

APP_ENV = os.getenv("APP_ENV", "production").lower()
# Configuration is injected by the guarded launcher. Never discover/source .env
# files or select a paid provider merely because a key happens to exist.
AI_MODE = os.getenv('DODREAM_AI_MODE', 'LOCAL_FAKE')
if AI_MODE not in {'LOCAL_FAKE', 'LIVE_OPENAI'}:
    raise RuntimeError('Unsupported DODREAM_AI_MODE')
LOCAL_EXTERNAL_STUBS = os.getenv("LOCAL_EXTERNAL_STUBS", "false").lower() == "true"
if LOCAL_EXTERNAL_STUBS and APP_ENV not in {"local", "test"}:
    raise RuntimeError("LOCAL_EXTERNAL_STUBS is permitted only in local/test")
if APP_ENV == "local" and not LOCAL_EXTERNAL_STUBS:
    raise RuntimeError("Local runtime requires LOCAL_EXTERNAL_STUBS=true")
if AI_MODE == 'LIVE_OPENAI' and (APP_ENV not in {'local', 'test'} or not LOCAL_EXTERNAL_STUBS):
    raise RuntimeError('Phase 5 live AI requires isolated local file/OCR providers')
if AI_MODE == 'LOCAL_FAKE' and not LOCAL_EXTERNAL_STUBS:
    raise RuntimeError('LOCAL_FAKE requires explicit local provider isolation')
RAG_RETRIEVAL_VARIANT = os.getenv('DODREAM_RAG_VARIANT', 'A')
if RAG_RETRIEVAL_VARIANT not in {'A', 'B'}:
    raise RuntimeError('Unsupported RAG retrieval variant')

ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
if ALGORITHM != "HS256":
    raise RuntimeError("JWT_ALGORITHM must be HS256")
JWT_ISSUER = os.getenv("JWT_ISSUER", "dodream")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "dodream-api")
if JWT_ISSUER != "dodream" or JWT_AUDIENCE != "dodream-api":
    raise RuntimeError("JWT issuer/audience must match the shared dodream contract")
JWT_CLOCK_SKEW_SECONDS = 5
JWT_ACCESS_MAX_SECONDS = 900
SECRET_KEY_BASE64 = os.getenv("JWT_SECRET_BASE64")
try:
    SECRET_KEY_BYTES = base64.b64decode(SECRET_KEY_BASE64 or "", validate=True)
except (ValueError, TypeError):
    raise RuntimeError("JWT_SECRET_BASE64 must be valid base64") from None
if base64.b64encode(SECRET_KEY_BYTES).decode("ascii") != SECRET_KEY_BASE64:
    raise RuntimeError("JWT_SECRET_BASE64 must use canonical standard base64")
if len(SECRET_KEY_BYTES) < 32:
    raise RuntimeError("JWT_SECRET_BASE64 must encode at least 32 bytes")
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GMS_KEY = os.getenv("GMS_KEY")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
HUGGINGFACE_TOKEN = os.getenv("HUGGINGFACE_TOKEN")
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
RAG_DATABASE_URL = os.getenv("RAG_DATABASE_URL", "sqlite:////app/db_data/rag.db")
LOCAL_PROVIDER_DATA_DIR = os.getenv("LOCAL_PROVIDER_DATA_DIR", "/app/db_data/local_provider")
# Exact object-key binding for authorized provider requests; no wildcard host.
OBJECT_STORAGE_HOST = os.getenv("OBJECT_STORAGE_HOST", "")
LOCAL_OBJECT_STORAGE_DIR = os.getenv("LOCAL_OBJECT_STORAGE_DIR", "/app/be-local-data/objects")
# One dedicated HTTP Chroma server owns persistence; clients never mount its data.
CHROMA_HOST = os.getenv('CHROMA_HOST', 'chroma')
CHROMA_PORT = int(os.getenv('CHROMA_PORT', '8000'))
if not CHROMA_HOST or '/' in CHROMA_HOST or not 1 <= CHROMA_PORT <= 65535:
    raise RuntimeError('Invalid Chroma endpoint')
