from __future__ import annotations

import base64
import json
import re
import time

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.security.models import TokenPayload, User
from app.config import (
    SECRET_KEY_BYTES, ALGORITHM, JWT_ISSUER, JWT_AUDIENCE,
    JWT_CLOCK_SKEW_SECONDS, JWT_ACCESS_MAX_SECONDS,
)
from app.common.database import get_user_from_db
from app.common.db_session import get_db

bearer_scheme = HTTPBearer(auto_error=False)
MAX_TOKEN_BYTES = 8192


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate JSON member")
        value[key] = item
    return value


def _reject_json_constant(value):
    raise ValueError("Nonfinite JSON number")


def _strict_json_segment(segment):
    raw = base64.b64decode(segment + "=" * (-len(segment) % 4), altchars=b"-_", validate=True)
    value = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_reject_json_constant)
    if not isinstance(value, dict):
        raise ValueError("JWT JSON must be an object")
    return value


def decode_access_token(token: str) -> TokenPayload:
    """Verify the shared signature and strict claims before any user DB lookup.

    The HTTP dependency suppresses validation details and maps invalid credentials
    to one fixed 401 response. Database failures remain service errors.
    """
    if not isinstance(token, str) or not token.isascii() or len(token) > MAX_TOKEN_BYTES:
        raise ValueError("Invalid compact token")
    if not re.fullmatch(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", token):
        raise ValueError("Invalid compact token")
    segments = token.split(".")

    jwt.decode(
        token,
        SECRET_KEY_BYTES,
        algorithms=[ALGORITHM],
        issuer=JWT_ISSUER,
        audience=JWT_AUDIENCE,
        options={
            "leeway": JWT_CLOCK_SKEW_SECONDS,
            "require_exp": True,
            "require_iat": True,
            "require_nbf": True,
            "require_iss": True,
            "require_aud": True,
            "require_sub": True,
            "require_jti": True,
        },
    )
    header = _strict_json_segment(segments[0])
    if header.get("alg") != "HS256":
        raise ValueError("Invalid signing algorithm")
    # Check the signed raw JSON: library coercion must not accept string/float dates.
    payload = TokenPayload.model_validate(_strict_json_segment(segments[1]))
    if payload.iss != JWT_ISSUER or payload.aud not in (JWT_AUDIENCE, [JWT_AUDIENCE]):
        raise ValueError("Invalid issuer or audience")
    now = int(time.time())
    if not payload.iat <= payload.nbf < payload.exp:
        raise ValueError("Invalid token time order")
    if payload.iat > now + JWT_CLOCK_SKEW_SECONDS or payload.nbf > now + JWT_CLOCK_SKEW_SECONDS:
        raise ValueError("Token is not active")
    if payload.exp <= now - JWT_CLOCK_SKEW_SECONDS:
        raise ValueError("Token has expired")
    if payload.exp - payload.iat > JWT_ACCESS_MAX_SECONDS:
        raise ValueError("Access token lifetime exceeds policy")
    return payload


async def get_current_user(
    auth: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        if auth is None or auth.scheme.lower() != "bearer":
            raise ValueError("Bearer credentials required")
        payload = decode_access_token(auth.credentials)
        user_id = int(payload.sub)
    except (JWTError, ValueError, TypeError, OverflowError, AttributeError, RecursionError):
        raise credentials_exception from None

    user = get_user_from_db(db=db, user_id=user_id)
    if user is None:
        raise credentials_exception
    return user
