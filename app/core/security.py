from datetime import UTC, datetime, timedelta
from enum import StrEnum

import jwt
from pwdlib import PasswordHash

from app.core.config import settings
from app.core.exceptions import AuthenticationFailed

_password_hash = PasswordHash.recommended()
# Used when the login name doesn't exist, so a wrong login takes as long as a wrong password.
_DUMMY_HASH = _password_hash.hash("dummy-password")


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if password_hash is None:
        _password_hash.verify(password, _DUMMY_HASH)
        return False
    return _password_hash.verify(password, password_hash)


def create_token(user_id: int, token_version: int, token_type: TokenType) -> str:
    now = datetime.now(UTC)
    if token_type is TokenType.ACCESS:
        lifetime = timedelta(minutes=settings.access_token_minutes)
    else:
        lifetime = timedelta(days=settings.refresh_token_days)
    payload = {
        "sub": str(user_id),
        "ver": token_version,
        "type": token_type.value,
        "iat": now,
        "exp": now + lifetime,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str, expected_type: TokenType) -> tuple[int, int]:
    """Return (user_id, token_version). The caller checks the version against the user."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as e:
        raise AuthenticationFailed("Session expired, please sign in again") from e
    except jwt.PyJWTError as e:
        raise AuthenticationFailed("Invalid token") from e
    if payload.get("type") != expected_type.value:
        raise AuthenticationFailed("Invalid token")
    return int(payload["sub"]), int(payload["ver"])
