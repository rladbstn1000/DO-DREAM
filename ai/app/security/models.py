from typing import Annotated, Literal, Optional, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator

# Shared with Spring: bounded NumericDate avoids overflow in Date conversion.
NumericDate = Annotated[StrictInt, Field(gt=0, le=253402300799)]


class TokenPayload(BaseModel):
    """Required access-token contract. Legacy and refresh payloads are rejected."""
    model_config = ConfigDict(strict=True)

    sub: Annotated[StrictStr, Field(pattern=r"^[1-9][0-9]*$")]
    iss: StrictStr
    aud: Union[StrictStr, list[StrictStr]]
    token_use: Literal["access"]
    jti: StrictStr
    role: Literal["TEACHER", "STUDENT"]
    iat: NumericDate
    nbf: NumericDate
    exp: NumericDate
    name: Optional[StrictStr] = None

    @field_validator("sub")
    @classmethod
    def positive_long_subject(cls, value):
        if len(value) > 19 or int(value) > 9223372036854775807:
            raise ValueError("Subject is outside the positive Long range")
        return value

    @field_validator("jti")
    @classmethod
    def canonical_uuid(cls, value):
        if str(UUID(value)) != value:
            raise ValueError("jti must be a canonical lowercase UUID")
        return value

    @field_validator("name", mode="before")
    @classmethod
    def optional_name_must_be_nonblank(cls, value):
        # Missing is allowed; explicitly supplied null/non-string/blank is not.
        if not isinstance(value, str) or not value.strip():
            raise ValueError("name must be a nonblank string when present")
        return value


class User(BaseModel):
    """User returned by the real shared database lookup."""
    id: int
    name: str
    role: str
