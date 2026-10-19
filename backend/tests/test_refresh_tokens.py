"""
Branch E: refresh-token rotation and server-side logout.

Covers the full protocol: pair issuance, single-use rotation, replay (reuse)
detection with family revocation, lazy expiry, user deletion, hashed-at-rest
storage, and idempotent logout with ownership scoping.
"""
import hashlib
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.refresh_token import RefreshToken
from app.models.user import User

PASSWORD = "StrongPassword123!"


def _register(client: TestClient, email: str, full_name: str = "Test User") -> None:
    res = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": full_name},
    )
    assert res.status_code == 201


def _login_pair(client: TestClient, email: str) -> tuple[str, str]:
    """Logs in and returns (access_token, refresh_token)."""
    res = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
    )
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data and "refresh_token" in data
    return data["access_token"], data["refresh_token"]


def _refresh(client: TestClient, refresh_token: str):
    return client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})


# ---------------------------------------------------------------------------
# Pair issuance
# ---------------------------------------------------------------------------


def test_login_returns_token_pair(client: TestClient):
    _register(client, "alice@example.com")
    access, refresh = _login_pair(client, "alice@example.com")
    # Opaque refresh token is a distinct value from the JWT access token
    assert access != refresh
    assert len(refresh) >= 32


def test_login_issues_independent_pairs_per_session(client: TestClient):
    """Two logins = two independent refresh sessions (multi-device ready)."""
    _register(client, "alice@example.com")
    _, refresh_one = _login_pair(client, "alice@example.com")
    _, refresh_two = _login_pair(client, "alice@example.com")
    assert refresh_one != refresh_two
    # Both are independently usable
    assert _refresh(client, refresh_one).status_code == 200
    assert _refresh(client, refresh_two).status_code == 200


# ---------------------------------------------------------------------------
# Rotation
# ---------------------------------------------------------------------------


def test_refresh_rotates_into_new_pair(client: TestClient, db_session: Session):
    _register(client, "alice@example.com")
    access, refresh_a = _login_pair(client, "alice@example.com")

    rotated = _refresh(client, refresh_a)
    assert rotated.status_code == 200
    refresh_b = rotated.json()["refresh_token"]
    assert refresh_b != refresh_a

    # The superseded row is revoked and linked to its successor (the chain)
    record = db_session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == hashlib.sha256(refresh_a.encode()).hexdigest())
    ).scalar_one()
    assert record.revoked_at is not None
    assert record.replaced_by_token_id is not None

    # Access tokens are stateless: rotation does not retroactively kill
    # already-issued JWTs (their exposure is bounded by ACCESS_TOKEN_EXPIRE_MINUTES)
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert me.status_code == 200

    # The chain keeps working: refresh with the successor, and again
    assert _refresh(client, refresh_b).status_code == 200


def test_refresh_unknown_token_rejected(client: TestClient):
    res = _refresh(client, "not-a-real-token")
    assert res.status_code == 401
    assert res.json()["detail"] == "Invalid or expired refresh token"


def test_expired_refresh_token_rejected(client: TestClient, db_session: Session):
    _register(client, "alice@example.com")
    _, refresh = _login_pair(client, "alice@example.com")

    # Age the token past its TTL directly in the DB
    record = db_session.execute(select(RefreshToken)).scalar_one()
    record.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()

    res = _refresh(client, refresh)
    assert res.status_code == 401
    # Lazy expiry burned the row: it is now revoked for good
    db_session.refresh(record)
    assert record.revoked_at is not None


# ---------------------------------------------------------------------------
# Reuse (replay) detection — the core security property of rotation
# ---------------------------------------------------------------------------


def test_refresh_reuse_revokes_entire_token_family(client: TestClient):
    _register(client, "alice@example.com")
    _, refresh_a = _login_pair(client, "alice@example.com")

    rotated = _refresh(client, refresh_a)
    assert rotated.status_code == 200
    refresh_b = rotated.json()["refresh_token"]

    # Replaying the superseded token is treated as theft...
    replay = _refresh(client, refresh_a)
    assert replay.status_code == 401
    assert "reuse" in replay.json()["detail"].lower()

    # ...and kills the WHOLE family, including the legitimately-held successor:
    # both the attacker and the real client are locked out, forcing a clean
    # re-authentication.
    assert _refresh(client, refresh_b).status_code == 401


def test_refresh_after_user_deleted_rejected(
    client: TestClient, db_session: Session
):
    _register(client, "ghost@example.com")
    _, refresh = _login_pair(client, "ghost@example.com")

    user = db_session.execute(
        select(User).where(User.email == "ghost@example.com")
    ).scalar_one()
    db_session.delete(user)
    db_session.commit()

    assert _refresh(client, refresh).status_code == 401


# ---------------------------------------------------------------------------
# Storage hygiene
# ---------------------------------------------------------------------------


def test_refresh_token_hashed_at_rest(client: TestClient, db_session: Session):
    """The raw token is returned exactly once; only its SHA-256 digest persists."""
    _register(client, "alice@example.com")
    _, refresh = _login_pair(client, "alice@example.com")
    record = db_session.execute(select(RefreshToken)).scalar_one()
    assert record.token_hash == hashlib.sha256(refresh.encode("utf-8")).hexdigest()
    assert record.token_hash != refresh
    assert len(record.token_hash) == 64


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


def test_logout_revokes_only_provided_session(client: TestClient):
    _register(client, "alice@example.com")
    _, refresh_one = _login_pair(client, "alice@example.com")
    access_two, refresh_two = _login_pair(client, "alice@example.com")

    res = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_one},
        headers={"Authorization": f"Bearer {access_two}"},
    )
    assert res.status_code == 204

    # This device's session is dead...
    assert _refresh(client, refresh_one).status_code == 401
    # ...while the other session keeps working
    assert _refresh(client, refresh_two).status_code == 200


def test_logout_all_devices_revokes_every_session(client: TestClient):
    _register(client, "alice@example.com")
    access_one, refresh_one = _login_pair(client, "alice@example.com")
    _, refresh_two = _login_pair(client, "alice@example.com")

    res = client.post(
        "/api/v1/auth/logout",
        json={"all_devices": True},
        headers={"Authorization": f"Bearer {access_one}"},
    )
    assert res.status_code == 204

    for token in (refresh_one, refresh_two):
        assert _refresh(client, token).status_code == 401


def test_logout_cannot_revoke_another_users_token(client: TestClient):
    """Ownership scoping: Bob cannot kill Alice's session with her token id."""
    _register(client, "alice@example.com")
    _register(client, "bob@example.com")
    _, refresh_a = _login_pair(client, "alice@example.com")
    access_b, _ = _login_pair(client, "bob@example.com")

    res = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_a},
        headers={"Authorization": f"Bearer {access_b}"},
    )
    # Quiet 204 (no existence leak) but Alice's session is untouched
    assert res.status_code == 204
    assert _refresh(client, refresh_a).status_code == 200


def test_logout_is_idempotent_and_tolerates_garbage(client: TestClient):
    _register(client, "alice@example.com")
    access, refresh = _login_pair(client, "alice@example.com")
    headers = {"Authorization": f"Bearer {access}"}

    first = client.post(
        "/api/v1/auth/logout", json={"refresh_token": refresh}, headers=headers
    )
    assert first.status_code == 204
    assert first.content == b""  # no body on 204

    # Logging out twice — and with a token the server has never seen — must
    # never surface an error to a user who is trying to leave
    assert client.post(
        "/api/v1/auth/logout", json={"refresh_token": refresh}, headers=headers
    ).status_code == 204
    assert client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": "never-issued-token"},
        headers=headers,
    ).status_code == 204


def test_logout_requires_bearer_authentication(client: TestClient):
    _register(client, "alice@example.com")
    res = client.post("/api/v1/auth/logout", json={})
    assert res.status_code == 401
