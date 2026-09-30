"""Legacy import compatibility; configuration is injected, never .env-discovered.

Active document routes use app.config directly. Keep one validation contract.
"""
from app.config import ALGORITHM, DATABASE_URL, JWT_ISSUER, SECRET_KEY_BASE64, SECRET_KEY_BYTES
