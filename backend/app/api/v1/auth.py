from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user
from app.core.config import settings
from app.core.rate_limit import auth_rate_limit
from app.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.user import (
    UserCreate,
    UserLogin,
    UserResponse,
    TokenPair,
    RefreshRequest,
    LogoutRequest,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

# A real bcrypt hash (of a string committed to the repository, so not a
# secret) used to equalize login timing: when the email is unknown we still
# perform one full bcrypt comparison against this hash, making the
# "no such user" path cost the same as the "wrong password" path. Without
# it, response time would reveal whether an account exists (user enumeration
# via timing side channel). A caller who somehow knows the dummy plaintext
# still gets 401, because no user row backs the comparison.
DUMMY_PASSWORD_HASH = get_password_hash(
    "devtrack-timing-equalizer-not-a-real-password"
)

# Uniform failure for every dead refresh token (unknown, expired, logged
# out). Callers learn nothing about why — and nothing about whether a
# (stolen) token ever existed.
_REFRESH_INVALID = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired refresh token",
    headers={"WWW-Authenticate": "Bearer"},
)


def _as_utc(dt: datetime) -> datetime:
    """
    Normalizes datetimes read back from the database.

    Postgres with DateTime(timezone=True) returns timezone-aware values;
    SQLite (tests, local dev) returns naive UTC. Comparing the two directly
    raises TypeError, so every comparison goes through this helper.
    """
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _issue_refresh_token(db: Session, user: User) -> tuple[str, RefreshToken]:
    """
    Persists a new refresh-token row (storing only the SHA-256 hash) and
    returns the raw token exactly once — it can never be retrieved again.
    """
    raw_token = generate_refresh_token()
    record = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(raw_token),
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return raw_token, record


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new developer account",
)
def register(
    user_in: UserCreate,
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(auth_rate_limit),
):
    """
    Registers a new user with an email, password, and full name.
    - Enforces email normalization and uniqueness.
    - Hashes password using bcrypt.
    - Never returns hashed_password in the response.
    """
    # 1. Check if user already exists
    stmt = select(User).where(User.email == user_in.email)
    existing_user = db.execute(stmt).scalar_one_or_none()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    # 2. Hash password with bcrypt
    hashed_password = get_password_hash(user_in.password)

    # 3. Create user record
    new_user = User(
        email=user_in.email,
        hashed_password=hashed_password,
        full_name=user_in.full_name,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


@router.post(
    "/login",
    response_model=TokenPair,
    summary="Authenticate and obtain a token pair",
)
def login(
    user_in: UserLogin,
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(auth_rate_limit),
):
    """
    Authenticates user credentials and returns a token pair:
    - a short-lived JWT access token (stateless, minutes),
    - a long-lived opaque refresh token (server-side, single-use, rotating).
    Returns generic 401 error on invalid email or password to prevent user enumeration.
    Rate-limited per IP (sliding window) to slow credential stuffing.
    """
    stmt = select(User).where(User.email == user_in.email)
    user = db.execute(stmt).scalar_one_or_none()

    # Always run exactly one bcrypt comparison — against the real hash when
    # the account exists, against a dummy hash otherwise — so response timing
    # does not reveal whether the email is registered (timing side channel).
    stored_hash = user.hashed_password if user is not None else DUMMY_PASSWORD_HASH
    password_matches = verify_password(user_in.password, stored_hash)

    if user is None or not password_matches:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # JWT access token with user.id as subject + a server-side refresh session
    access_token = create_access_token(subject=str(user.id))
    refresh_token, _record = _issue_refresh_token(db, user)
    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )


@router.post(
    "/refresh",
    response_model=TokenPair,
    summary="Rotate refresh token into a new token pair",
)
def refresh_tokens(
    refresh_in: RefreshRequest,
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(auth_rate_limit),
):
    """
    Exchanges a valid refresh token for a completely NEW access + refresh
    token pair (sliding-window sessions without long-lived JWTs).

    Rotation protocol:
    - The presented token is single-use: on success it is revoked and linked
      to its successor (replaced_by_token_id), forming an auditable chain.
    - Replaying an already-rotated token is treated as theft: BOTH the
      attacker and the legitimate client cannot hold the same fresh token,
      so the user's entire token family is revoked and a fresh login is
      forced. This is the main security win over a static long-lived token.
    - Access tokens are stateless, so rotation does not retroactively
      invalidate issued JWTs; their exposure is bounded by
      ACCESS_TOKEN_EXPIRE_MINUTES.
    """
    token_hash = hash_refresh_token(refresh_in.refresh_token)
    stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    record = db.execute(stmt).scalar_one_or_none()
    if record is None:
        raise _REFRESH_INVALID

    now = datetime.now(timezone.utc)

    # Already revoked: either replayed rotation (compromise signal) or a
    # logged-out token. Both answer 401; only the replay case burns the family.
    if record.revoked_at is not None:
        if record.replaced_by_token_id is not None:
            db.execute(
                update(RefreshToken)
                .where(
                    RefreshToken.user_id == record.user_id,
                    RefreshToken.revoked_at.is_(None),
                )
                .values(revoked_at=now)
            )
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token reuse detected; all sessions have been revoked",
                headers={"WWW-Authenticate": "Bearer"},
            )
        raise _REFRESH_INVALID

    # Lazy expiry: burn the row so it stops matching future lookups.
    if _as_utc(record.expires_at) <= now:
        record.revoked_at = now
        db.commit()
        raise _REFRESH_INVALID

    user = db.get(User, record.user_id)
    if user is None:
        # Defence in depth: the FK cascades token rows on user deletion, but
        # never mint tokens for a user that no longer exists regardless.
        raise _REFRESH_INVALID

    new_raw_token, new_record = _issue_refresh_token(db, user)
    record.revoked_at = now
    record.replaced_by_token_id = new_record.id
    db.commit()

    return TokenPair(
        access_token=create_access_token(subject=str(user.id)),
        refresh_token=new_raw_token,
        token_type="bearer",
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke refresh token(s) server-side",
)
def logout(
    logout_in: Optional[LogoutRequest] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(auth_rate_limit),
):
    """
    Server-side logout — the reason refresh tokens live in a table.

    Best-effort and idempotent by design: an unknown, expired, or
    already-revoked refresh token still returns 204, because logout must
    never surface an error to a user who is trying to leave. The client
    clears local state regardless; this endpoint is what makes the session
    dead for a thief who already copied the token.

    - Default: revoke the provided refresh token (this device only).
    - all_devices=true: revoke every active refresh token (log out
      everywhere). Requires a valid Bearer token, and — like every other
      write here — is scoped to the authenticated user (no cross-user
      revocation, even with a valid-looking token id).
    """
    payload = logout_in or LogoutRequest()
    now = datetime.now(timezone.utc)

    if payload.all_devices:
        db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == current_user.id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now),
        )
    elif payload.refresh_token:
        stmt = select(RefreshToken).where(
            RefreshToken.token_hash == hash_refresh_token(payload.refresh_token),
            # Ownership scoping: revoking is user-scoped, never global
            RefreshToken.user_id == current_user.id,
        )
        record = db.execute(stmt).scalar_one_or_none()
        if record is not None and record.revoked_at is None:
            record.revoked_at = now

    db.commit()
    return None


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current authenticated user profile",
)
def read_current_user(
    current_user: User = Depends(get_current_user),
):
    """
    Returns the currently authenticated user's profile information.
    Protected endpoint requiring a valid Bearer token.
    """
    return current_user
