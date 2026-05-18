import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.core.config import settings


def create_access_token(user_id: uuid.UUID, expires_in: timedelta | None = None) -> str:
    delta = expires_in or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    expire = datetime.now(timezone.utc) + delta
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "typ": "access",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def verify_token(token: str) -> uuid.UUID | None:
    """Verify an access JWT and return the user_id.

    Accepts both new short-lived tokens (with ``typ=access``) and legacy
    long-lived tokens issued before the refresh-token rollout (no ``typ``
    claim). Refresh tokens are opaque strings (not JWTs) and never reach here.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        token_type = payload.get("typ")
        if token_type is not None and token_type != "access":
            return None
        user_id_str: str | None = payload.get("sub")
        if user_id_str is None:
            return None
        return uuid.UUID(user_id_str)
    except (JWTError, ValueError):
        return None


def generate_refresh_token() -> str:
    """Generate an opaque refresh token with high entropy (256 bits)."""
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    """Hash a refresh token for storage. Plain SHA-256 is appropriate here:
    the input is a cryptographically random 256-bit value, so a slow KDF
    would only add cost without raising the attacker's effort."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
