from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class RefreshToken(Base):
    """
    Server-side record of an issued refresh token session.

    Design decisions (interview talking points):
    - The token itself is an opaque, URL-safe string with 384 bits of entropy
      (secrets.token_urlsafe(48)); it carries no claims to forge or extend.
      Only its SHA-256 digest is stored, so a database leak yields no usable
      credentials (same rationale as hashing passwords — see security.py for
      why a fast hash is fine here).
    - Single use: every successful /auth/refresh ROTATES — the presented row
      is revoked and linked to its successor via replaced_by_token_id,
      forming an auditable chain.
    - Replaying an already-rotated token is a strong compromise signal (an
      attacker and the legitimate client cannot both hold the same fresh
      token), so the endpoint revokes the user's entire token family.
    - Lifetime (REFRESH_TOKEN_EXPIRE_DAYS) is independent of the short-lived
      JWT access token; expiring rows are lazily marked revoked on sight.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # NULL = still active. Set by rotation, logout, reuse-detection kills,
    # and lazy expiry checks.
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Rotation chain: points at the token that superseded this one. A revoked
    # row WITH a successor = replayed token (see module docstring).
    replaced_by_token_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("refresh_tokens.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="refresh_tokens")
