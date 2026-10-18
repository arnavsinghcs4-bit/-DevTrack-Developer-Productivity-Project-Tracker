"""
Tests for E-lite hardening:
- InMemoryRateLimiter sliding-window unit behavior (fake clock, no sleeping)
- Login/register rate limiting through the real endpoints
- Scope isolation (a lockout on one endpoint does not bleed into others)
- The RATE_LIMIT_ENABLED kill switch
- The login timing fix: unknown emails still trigger exactly one bcrypt
  comparison (against a dummy hash), so timing cannot reveal account existence
"""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app.api.v1.auth as auth_module
from app.core.config import settings
from app.core.rate_limit import InMemoryRateLimiter, auth_rate_limit, limiter
from app.main import app

LOGIN = "/api/v1/auth/login"
REGISTER = "/api/v1/auth/register"
ME = "/api/v1/auth/me"


class FakeClock:
    """Manually advanced clock for deterministic window tests."""

    def __init__(self, start: float = 1000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


# ---------------------------------------------------------------------------
# Unit tests: InMemoryRateLimiter
# ---------------------------------------------------------------------------


def test_limiter_allows_up_to_limit_then_blocks():
    clock = FakeClock()
    rl = InMemoryRateLimiter(clock=clock)

    for _ in range(3):
        rl.check("k", limit=3, window_seconds=60)  # within budget

    with pytest.raises(HTTPException) as exc_info:
        rl.check("k", limit=3, window_seconds=60)  # over budget
    assert exc_info.value.status_code == 429
    assert "Retry-After" in exc_info.value.headers
    assert int(exc_info.value.headers["Retry-After"]) >= 1


def test_limiter_window_slides():
    clock = FakeClock()
    rl = InMemoryRateLimiter(clock=clock)

    for _ in range(2):
        rl.check("k", limit=2, window_seconds=60)
    clock.advance(31)
    with pytest.raises(HTTPException):
        rl.check("k", limit=2, window_seconds=60)  # still inside the window

    clock.advance(30)  # 61s after the first hit -> it expired
    rl.check("k", limit=2, window_seconds=60)  # allowed again


def test_limiter_rejected_requests_do_not_extend_the_lockout():
    """A blocked client retrying must not re-arm its own window."""
    clock = FakeClock()
    rl = InMemoryRateLimiter(clock=clock)

    rl.check("k", limit=1, window_seconds=60)  # accepted at t0
    clock.advance(10)
    with pytest.raises(HTTPException):
        rl.check("k", limit=1, window_seconds=60)  # rejected at t0+10
    clock.advance(50)  # now t0+60: the accepted hit expired
    rl.check("k", limit=1, window_seconds=60)  # proves rejection was not recorded


def test_limiter_keys_are_independent():
    clock = FakeClock()
    rl = InMemoryRateLimiter(clock=clock)

    for _ in range(2):
        rl.check("login", limit=2, window_seconds=60)
    with pytest.raises(HTTPException):
        rl.check("login", limit=2, window_seconds=60)

    rl.check("register", limit=2, window_seconds=60)  # separate budget untouched


def test_limiter_reset_clears_counters():
    clock = FakeClock()
    rl = InMemoryRateLimiter(clock=clock)
    for _ in range(2):
        rl.check("k", limit=2, window_seconds=60)
    with pytest.raises(HTTPException):
        rl.check("k", limit=2, window_seconds=60)

    rl.reset()
    rl.check("k", limit=2, window_seconds=60)  # budget restored


# ---------------------------------------------------------------------------
# Integration fixture: same app + DB, but with the limiter ACTIVELY enforced
# and a deterministic clock (conftest disables the limiter for all other tests)
# ---------------------------------------------------------------------------


@pytest.fixture
def limited_client(client: TestClient, monkeypatch):
    fake_clock = FakeClock()
    monkeypatch.setattr(limiter, "_clock", fake_clock)
    limiter.reset()
    app.dependency_overrides.pop(auth_rate_limit, None)  # enable the limiter
    try:
        yield client, fake_clock
    finally:
        limiter.reset()
        app.dependency_overrides[auth_rate_limit] = lambda: None  # restore


def test_login_rate_limited_after_burst(limited_client):
    client, clock = limited_client
    # Register one account (1 of 5 register hits; separate budget anyway)
    reg = client.post(
        REGISTER,
        json={
            "email": "rate@example.com",
            "password": "StrongPassword123!",
            "full_name": "Rate Tester",
        },
    )
    assert reg.status_code == 201

    # 10 wrong-password attempts fit the default login budget (401, not 429)
    for _ in range(settings.RATE_LIMIT_LOGIN_ATTEMPTS):
        res = client.post(
            LOGIN,
            json={"email": "rate@example.com", "password": "WrongPassword999!"},
        )
        assert res.status_code == 401

    # The 11th attempt within the window is rejected by the limiter
    blocked = client.post(
        LOGIN,
        json={"email": "rate@example.com", "password": "WrongPassword999!"},
    )
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers
    assert blocked.json()["detail"] == "Too many requests. Please try again shortly."

    # After the window slides, attempts are served again (still 401, not 429)
    clock.advance(settings.RATE_LIMIT_WINDOW_SECONDS + 1)
    recovered = client.post(
        LOGIN,
        json={"email": "rate@example.com", "password": "WrongPassword999!"},
    )
    assert recovered.status_code == 401


def test_register_rate_limited_after_burst(limited_client):
    client, _clock = limited_client
    payload = {
        "email": "burst@example.com",
        "password": "StrongPassword123!",
        "full_name": "Burst Tester",
    }

    # First call succeeds (201); the next ones conflict (409) but still count
    for i in range(settings.RATE_LIMIT_REGISTER_ATTEMPTS):
        res = client.post(REGISTER, json=payload)
        assert res.status_code == (201 if i == 0 else 409)

    blocked = client.post(REGISTER, json=payload)
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


def test_lockout_is_scoped_to_the_limited_endpoint(limited_client, monkeypatch):
    """A register lockout must not block login or /me (independent budgets)."""
    client, _clock = limited_client
    scoped_payload = {
        "email": "scoped@example.com",
        "password": "StrongPassword123!",
        "full_name": "Scoped Tester",
    }
    client.post(REGISTER, json=scoped_payload)
    token = client.post(
        LOGIN,
        json={"email": "scoped@example.com", "password": "StrongPassword123!"},
    ).json()["access_token"]

    # Exhaust the register budget (same email -> 409s, which still count)
    conflict_payload = {
        "email": "scoped@example.com",
        "password": "AnotherPassword123!",
        "full_name": "Scoped Tester",
    }
    for _ in range(settings.RATE_LIMIT_REGISTER_ATTEMPTS - 1):
        client.post(REGISTER, json=conflict_payload)
    assert client.post(REGISTER, json=conflict_payload).status_code == 429

    # Login (different budget) and /me (not limited at all) keep working
    login_res = client.post(
        LOGIN,
        json={"email": "scoped@example.com", "password": "WrongPassword999!"},
    )
    assert login_res.status_code == 401  # not 429: login budget untouched
    me = client.get(ME, headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200


def test_rate_limit_disabled_via_settings(limited_client, monkeypatch):
    """RATE_LIMIT_ENABLED=false turns the limiter off entirely."""
    client, _clock = limited_client
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)

    payload = {
        "email": "nobudget@example.com",
        "password": "StrongPassword123!",
        "full_name": "No Budget",
    }
    statuses = [
        client.post(REGISTER, json=payload).status_code
        for _ in range(settings.RATE_LIMIT_REGISTER_ATTEMPTS + 5)
    ]
    assert 429 not in statuses  # well past the register budget


# ---------------------------------------------------------------------------
# Timing side-channel fix: unknown emails still cost one bcrypt comparison
# ---------------------------------------------------------------------------


def test_unknown_email_performs_dummy_bcrypt_compare(client, monkeypatch):
    calls = []

    def spy_verify(plain_password: str, hashed_password: str) -> bool:
        calls.append((plain_password, hashed_password))
        return False

    monkeypatch.setattr(auth_module, "verify_password", spy_verify)

    ghost = client.post(
        LOGIN, json={"email": "ghost@example.com", "password": "Whatever123!"}
    )
    assert ghost.status_code == 401
    # Exactly one comparison was made, against the dummy hash
    assert len(calls) == 1
    assert calls[0][1] == auth_module.DUMMY_PASSWORD_HASH

    # Known email, wrong password: still one comparison, against the REAL hash
    reg = client.post(
        REGISTER,
        json={
            "email": "real@example.com",
            "password": "StrongPassword123!",
            "full_name": "Real User",
        },
    )
    assert reg.status_code == 201
    wrong = client.post(
        LOGIN, json={"email": "real@example.com", "password": "WrongPassword999!"}
    )
    assert wrong.status_code == 401
    assert len(calls) == 2
    assert calls[1][1] != auth_module.DUMMY_PASSWORD_HASH

    # Both failure modes return the identical generic error (no enumeration)
    assert ghost.json() == wrong.json()


def test_login_rate_limit_dependency_only_applies_to_auth_paths():
    """The dependency itself is a no-op for paths outside login/register."""

    class _FakeRequest:
        def __init__(self, path):
            self.url = type("U", (), {"path": path})()
            self.client = type("C", (), {"host": "1.2.3.4"})()

    auth_rate_limit(_FakeRequest("/api/v1/dsa-problems"))  # no exception
    auth_rate_limit(_FakeRequest("/api/v1/auth/me"))  # no exception
