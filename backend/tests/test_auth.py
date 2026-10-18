from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import verify_password, create_access_token
from app.models.user import User


def test_successful_registration(client: TestClient, db_session: Session):
    """1. Test successful user registration."""
    payload = {
        "email": "developer@example.com",
        "password": "StrongPassword123!",
        "full_name": "Dev User",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "developer@example.com"
    assert data["full_name"] == "Dev User"
    assert "id" in data
    assert "created_at" in data


def test_duplicate_email_registration(client: TestClient):
    """2. Test that registering with an existing email returns HTTP 409 Conflict."""
    payload = {
        "email": "unique@example.com",
        "password": "StrongPassword123!",
        "full_name": "First User",
    }
    res1 = client.post("/api/v1/auth/register", json=payload)
    assert res1.status_code == 201

    # Second registration with same email (even with different casing)
    duplicate_payload = {
        "email": "UNIQUE@example.com",
        "password": "AnotherPassword456!",
        "full_name": "Duplicate User",
    }
    res2 = client.post("/api/v1/auth/register", json=duplicate_payload)
    assert res2.status_code == 409
    assert "already exists" in res2.json()["detail"].lower()


def test_password_is_hashed_in_database(client: TestClient, db_session: Session):
    """3. Test that password is never stored in plaintext and is properly hashed."""
    plain_password = "SuperSecretPassword123"
    payload = {
        "email": "hashcheck@example.com",
        "password": plain_password,
        "full_name": "Hash Check",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201

    # Directly inspect database record
    user = db_session.execute(
        select(User).where(User.email == "hashcheck@example.com")
    ).scalar_one()

    assert user.hashed_password != plain_password
    assert user.hashed_password.startswith("$2b$") or user.hashed_password.startswith("$2a$")
    assert verify_password(plain_password, user.hashed_password) is True


def test_registration_response_excludes_hashed_password(client: TestClient):
    """4. Test that the registration response payload never leaks hashed_password."""
    payload = {
        "email": "leakcheck@example.com",
        "password": "PasswordToNotLeak123",
        "full_name": "Leak Check",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert "hashed_password" not in data
    assert "password" not in data


def test_successful_login(client: TestClient):
    """5. Test successful login returning a valid JWT access token."""
    # Register first
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "loginuser@example.com",
            "password": "ValidPassword123",
            "full_name": "Login User",
        },
    )

    # Login
    login_payload = {
        "email": "loginuser@example.com",
        "password": "ValidPassword123",
    }
    response = client.post("/api/v1/auth/login", json=login_payload)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert len(data["access_token"]) > 20


def test_login_incorrect_password(client: TestClient):
    """6. Test login failure with incorrect password returns generic 401."""
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "wrongpass@example.com",
            "password": "CorrectPassword123",
            "full_name": "Wrong Pass",
        },
    )

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "wrongpass@example.com",
            "password": "WrongPassword999",
        },
    )
    assert response.status_code == 401
    assert "incorrect email or password" in response.json()["detail"].lower()


def test_access_me_with_valid_token(client: TestClient):
    """7. Test access to /api/v1/auth/me with a valid Bearer token."""
    reg_res = client.post(
        "/api/v1/auth/register",
        json={
            "email": "metest@example.com",
            "password": "ValidPassword123",
            "full_name": "Me Test",
        },
    )
    user_id = reg_res.json()["id"]

    login_res = client.post(
        "/api/v1/auth/login",
        json={
            "email": "metest@example.com",
            "password": "ValidPassword123",
        },
    )
    token = login_res.json()["access_token"]

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == user_id
    assert data["email"] == "metest@example.com"
    assert data["full_name"] == "Me Test"
    assert "hashed_password" not in data


def test_access_me_missing_token(client: TestClient):
    """8. Test access to /api/v1/auth/me with missing Authorization header returns 401."""
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_access_me_invalid_token(client: TestClient):
    """9. Test access to /api/v1/auth/me with an invalid or tampered token returns 401."""
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid.token.garbage"},
    )
    assert response.status_code == 401
    assert "could not validate credentials" in response.json()["detail"].lower()


def test_access_me_expired_token(client: TestClient):
    """10. Test access to /api/v1/auth/me with an expired JWT token returns 401."""
    # Create token expired 10 minutes ago
    expired_token = create_access_token(
        subject="1",
        expires_delta=timedelta(minutes=-10),
    )
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401
    assert "expired" in response.json()["detail"].lower()


def test_access_me_nonexistent_user_token(client: TestClient):
    """11. Test valid token pointing to a user ID that does not exist in the database."""
    # User ID 99999 does not exist
    token_ghost_user = create_access_token(subject="99999")
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token_ghost_user}"},
    )
    assert response.status_code == 401
    assert "user not found" in response.json()["detail"].lower()


def test_registration_valid_ascii_password(client: TestClient):
    """12. Test registration with an ordinary valid ASCII password."""
    payload = {
        "email": "asciipass@example.com",
        "password": "ValidAsciiPassword123!",
        "full_name": "Ascii User",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    assert response.json()["email"] == "asciipass@example.com"


def test_registration_valid_multibyte_unicode_password(client: TestClient):
    """13. Test registration with a valid multibyte Unicode password whose UTF-8 byte count is <= 72 bytes."""
    # "Pä§§wörd🔑2026" is 14 characters, but 20 bytes in UTF-8
    multibyte_pass = "Pä§§wörd🔑2026"
    assert len(multibyte_pass.encode("utf-8")) <= 72

    payload = {
        "email": "unicodepass@example.com",
        "password": multibyte_pass,
        "full_name": "Unicode User",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    assert response.json()["email"] == "unicodepass@example.com"

    # Verify user can also log in successfully with this multibyte password
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "unicodepass@example.com", "password": multibyte_pass},
    )
    assert login_res.status_code == 200
    assert "access_token" in login_res.json()


def test_registration_oversized_unicode_password_rejected(client: TestClient, db_session: Session):
    """14. Test that a password with < 72 characters but > 72 UTF-8 bytes returns HTTP 422 and does NOT create a user."""
    # 25 lock emojis: character count is 25 (< 72), but UTF-8 byte count is 25 * 4 = 100 bytes (> 72 bytes)
    oversized_pass = "🔐" * 25
    assert len(oversized_pass) < 72
    assert len(oversized_pass.encode("utf-8")) > 72

    payload = {
        "email": "oversized@example.com",
        "password": oversized_pass,
        "full_name": "Oversized User",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    # Must return HTTP 422 Unprocessable Entity, not an unhandled HTTP 500 error
    assert response.status_code == 422
    data = response.json()
    assert "72 bytes" in str(data["detail"]).lower()

    # Confirm that the user was NOT created in the database
    user = db_session.execute(
        select(User).where(User.email == "oversized@example.com")
    ).scalar_one_or_none()
    assert user is None


def test_login_oversized_password_rejected(client: TestClient):
    """15. Test that submitting an oversized password (>72 bytes) during login returns HTTP 422."""
    oversized_pass = "🔐" * 25
    payload = {
        "email": "somelogin@example.com",
        "password": oversized_pass,
    }
    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 422
    assert "72 bytes" in str(response.json()["detail"]).lower()
