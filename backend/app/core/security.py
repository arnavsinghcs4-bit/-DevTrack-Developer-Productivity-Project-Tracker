from datetime import datetime, timedelta, timezone
from typing import Any, Union
import bcrypt
import hashlib
import jwt
import secrets
from app.core.config import settings


def get_password_hash(password: str) -> str:
    """
    Hashes a plain-text password using bcrypt with a randomized salt.
    """
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifies a plain-text password against an existing bcrypt hash.
    Protects against timing attacks.
    """
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8")
        )
    except Exception:
        return False


def create_access_token(subject: Union[str, Any], expires_delta: Union[timedelta, None] = None) -> str:
    """
    Encodes a signed JSON Web Token (JWT) with expiration.
    """
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode = {
        "exp": expire,
        "iat": now,
        "sub": str(subject),
    }
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Decodes and validates a JWT token using the configured secret key
    and strictly enforcing the configured algorithm.
    Raises jwt.PyJWTError on invalid or expired token.
    """
    return jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
        options={"require": ["exp", "sub", "iat"]},
    )


def generate_refresh_token() -> str:
    """
    Generates an opaque, URL-safe refresh token with 384 bits of entropy.

    Unlike the JWT access token this carries no claims: it is only ever
    looked up server-side (by hash), so there is nothing to decode, forge,
    or extend. At 384 bits, brute-forcing the token space is not a
    meaningful attack — which is also why it is safe to store unauthenticated
    lookups by a fast hash (see hash_refresh_token).
    """
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    """
    SHA-256 digest of a refresh token — the only form ever persisted.

    A fast hash is deliberate here (contrast with bcrypt for passwords):
    refresh tokens are uniform high-entropy secrets, not user-chosen
    passwords, so there is no dictionary to defend against and no per-token
    salt to manage, while a leaked database still yields no usable tokens.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
