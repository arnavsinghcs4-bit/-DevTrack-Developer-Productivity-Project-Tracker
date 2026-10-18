from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.dsa_problem import DSAProblem
from app.models.user import User

BASE = "/api/v1/dsa-problems"


# ---------------------------------------------------------------------------
# Helpers and fixtures (all backed by the isolated in-memory SQLite database)
# ---------------------------------------------------------------------------

def _register_and_login(client: TestClient, email: str, full_name: str = "Test User") -> str:
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "StrongPassword123!",
            "full_name": full_name,
        },
    )
    assert reg.status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "StrongPassword123!"},
    )
    assert login.status_code == 200
    return login.json()["access_token"]


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _user_id(client: TestClient, token: str) -> int:
    me = client.get("/api/v1/auth/me", headers=_bearer(token))
    assert me.status_code == 200
    return me.json()["id"]


def _valid_payload(**overrides) -> dict:
    payload = {
        "platform": "LeetCode",
        "title": "Two Sum",
        "topic": "Arrays",
        "difficulty": "Easy",
        "problem_url": "https://leetcode.com/problems/two-sum/",
        "notes": "Hash map approach",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def token_a(client: TestClient) -> str:
    return _register_and_login(client, "alice@example.com", "Alice")


@pytest.fixture
def token_b(client: TestClient) -> str:
    return _register_and_login(client, "bob@example.com", "Bob")


# ---------------------------------------------------------------------------
# 1-2. Creation and ownership
# ---------------------------------------------------------------------------

def test_create_dsa_problem_success(client: TestClient, token_a: str):
    """1. Authenticated user creates a DSA problem and receives 201 with the stored record."""
    response = client.post(BASE, json=_valid_payload(), headers=_bearer(token_a))
    assert response.status_code == 201
    data = response.json()
    assert data["platform"] == "LeetCode"
    assert data["title"] == "Two Sum"
    assert data["topic"] == "Arrays"
    assert data["difficulty"] == "Easy"
    assert data["problem_url"] == "https://leetcode.com/problems/two-sum/"
    assert data["notes"] == "Hash map approach"
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data
    # No internal/derived fields leak into the public response
    assert "hashed_password" not in data


def test_create_dsa_problem_owned_by_authenticated_user(
    client: TestClient, token_a: str, db_session: Session
):
    """2. The stored record's user_id equals the authenticated user, not any client value."""
    response = client.post(BASE, json=_valid_payload(), headers=_bearer(token_a))
    assert response.status_code == 201
    data = response.json()

    owner_id = _user_id(client, token_a)
    assert data["user_id"] == owner_id

    # Verify in the database directly
    row = db_session.execute(
        select(DSAProblem).where(DSAProblem.id == data["id"])
    ).scalar_one()
    assert row.user_id == owner_id


def test_create_assigns_solved_date_default(
    client: TestClient, token_a: str
):
    """Omitting solved_date defaults to today (mirrors the model default)."""
    payload = _valid_payload()
    del payload["problem_url"]
    payload.pop("solved_date", None)
    response = client.post(BASE, json=payload, headers=_bearer(token_a))
    assert response.status_code == 201
    assert response.json()["solved_date"] == date.today().isoformat()


# ---------------------------------------------------------------------------
# 3-6. Read, list, update, delete own records
# ---------------------------------------------------------------------------

def test_list_returns_only_own_records(
    client: TestClient, token_a: str, token_b: str
):
    """3. Each user's list contains only their own records."""
    client.post(BASE, json=_valid_payload(title="A1"), headers=_bearer(token_a))
    client.post(BASE, json=_valid_payload(title="A2"), headers=_bearer(token_a))
    client.post(BASE, json=_valid_payload(title="B1"), headers=_bearer(token_b))

    list_a = client.get(BASE, headers=_bearer(token_a))
    assert list_a.status_code == 200
    body_a = list_a.json()
    assert body_a["total"] == 2
    assert {item["title"] for item in body_a["items"]} == {"A1", "A2"}
    assert all(item["platform"] == "LeetCode" for item in body_a["items"])

    list_b = client.get(BASE, headers=_bearer(token_b))
    assert list_b.status_code == 200
    body_b = list_b.json()
    assert body_b["total"] == 1
    assert [item["title"] for item in body_b["items"]] == ["B1"]


def test_retrieve_own_record(client: TestClient, token_a: str):
    """4. The owner can fetch a single record by id."""
    created = client.post(BASE, json=_valid_payload(), headers=_bearer(token_a))
    problem_id = created.json()["id"]

    response = client.get(f"{BASE}/{problem_id}", headers=_bearer(token_a))
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == problem_id
    assert data["title"] == "Two Sum"


def test_update_own_record(
    client: TestClient, token_a: str, db_session: Session
):
    """5. The owner can update their record; changes persist."""
    created = client.post(BASE, json=_valid_payload(), headers=_bearer(token_a))
    problem_id = created.json()["id"]

    response = client.patch(
        f"{BASE}/{problem_id}",
        json={"difficulty": "Hard", "notes": "Revisit Dijkstra"},
        headers=_bearer(token_a),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["difficulty"] == "Hard"
    assert data["notes"] == "Revisit Dijkstra"

    row = db_session.execute(
        select(DSAProblem).where(DSAProblem.id == problem_id)
    ).scalar_one()
    assert row.difficulty == "Hard"
    assert row.notes == "Revisit Dijkstra"


def test_delete_own_record(
    client: TestClient, token_a: str, db_session: Session
):
    """6. The owner deletes their record: 204, gone from API and database."""
    created = client.post(BASE, json=_valid_payload(), headers=_bearer(token_a))
    problem_id = created.json()["id"]

    response = client.delete(f"{BASE}/{problem_id}", headers=_bearer(token_a))
    assert response.status_code == 204
    assert response.content == b""

    assert (
        client.get(f"{BASE}/{problem_id}", headers=_bearer(token_a)).status_code
        == 404
    )
    row = db_session.execute(
        select(DSAProblem).where(DSAProblem.id == problem_id)
    ).scalar_one_or_none()
    assert row is None


# ---------------------------------------------------------------------------
# 7. Authentication required on every endpoint
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "method, path, body",
    [
        ("POST", BASE, {"platform": "LeetCode", "title": "X", "topic": "Arrays", "difficulty": "Easy"}),
        ("GET", BASE, None),
        ("GET", f"{BASE}/1", None),
        ("PATCH", f"{BASE}/1", {"difficulty": "Hard"}),
        ("DELETE", f"{BASE}/1", None),
    ],
)
def test_unauthenticated_requests_rejected(
    client: TestClient, method: str, path: str, body
):
    """7. Every endpoint returns 401 without a Bearer token."""
    response = client.request(method, path, json=body)
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# 8-10. Cross-user access is denied with 404 (no existence disclosure)
# ---------------------------------------------------------------------------

def test_user_cannot_retrieve_other_users_record(
    client: TestClient, token_a: str, token_b: str
):
    """8. Fetching another user's record returns the same 404 as a missing one."""
    created = client.post(BASE, json=_valid_payload(), headers=_bearer(token_a))
    problem_id = created.json()["id"]

    response = client.get(f"{BASE}/{problem_id}", headers=_bearer(token_b))
    assert response.status_code == 404
    assert response.json()["detail"] == "DSA problem not found"

    # Identical response for a truly nonexistent id -> no existence leak
    missing = client.get(f"{BASE}/999999", headers=_bearer(token_b))
    assert missing.status_code == 404
    assert missing.json()["detail"] == response.json()["detail"]


def test_user_cannot_update_other_users_record(
    client: TestClient, token_a: str, token_b: str, db_session: Session
):
    """9. PATCH on another user's record returns 404 and changes nothing."""
    created = client.post(BASE, json=_valid_payload(), headers=_bearer(token_a))
    problem_id = created.json()["id"]

    response = client.patch(
        f"{BASE}/{problem_id}",
        json={"title": "Hijacked Title"},
        headers=_bearer(token_b),
    )
    assert response.status_code == 404

    row = db_session.execute(
        select(DSAProblem).where(DSAProblem.id == problem_id)
    ).scalar_one()
    assert row.title == "Two Sum"


def test_user_cannot_delete_other_users_record(
    client: TestClient, token_a: str, token_b: str, db_session: Session
):
    """10. DELETE on another user's record returns 404 and the record survives."""
    created = client.post(BASE, json=_valid_payload(), headers=_bearer(token_a))
    problem_id = created.json()["id"]

    response = client.delete(f"{BASE}/{problem_id}", headers=_bearer(token_b))
    assert response.status_code == 404

    row = db_session.execute(
        select(DSAProblem).where(DSAProblem.id == problem_id)
    ).scalar_one_or_none()
    assert row is not None


# ---------------------------------------------------------------------------
# 11. Client-supplied ownership fields are ignored
# ---------------------------------------------------------------------------

def test_client_supplied_user_id_cannot_override_owner(
    client: TestClient, token_a: str, token_b: str, db_session: Session
):
    """11. A spoofed user_id in create or PATCH payloads is rejected with 422 and never changes ownership."""
    owner_a = _user_id(client, token_a)
    owner_b = _user_id(client, token_b)

    # Creation with a foreign user_id in the body is rejected outright
    created = client.post(
        BASE,
        json=_valid_payload(user_id=owner_b),
        headers=_bearer(token_a),
    )
    assert created.status_code == 422
    # ...and no record was created
    assert db_session.execute(select(DSAProblem)).scalars().all() == []

    # Legitimate creation for comparison
    legit = client.post(BASE, json=_valid_payload(), headers=_bearer(token_a))
    assert legit.status_code == 201
    problem_id = legit.json()["id"]
    assert legit.json()["user_id"] == owner_a

    # PATCH attempting to transfer ownership is rejected too
    patched = client.patch(
        f"{BASE}/{problem_id}",
        json={"user_id": owner_b},
        headers=_bearer(token_a),
    )
    assert patched.status_code == 422

    row = db_session.execute(
        select(DSAProblem).where(DSAProblem.id == problem_id)
    ).scalar_one()
    assert row.user_id == owner_a


# ---------------------------------------------------------------------------
# 12-14. Validation and 404 behavior
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "payload",
    [
        {},  # missing all required fields
        _valid_payload(difficulty="Impossible"),  # not an allowed value
        _valid_payload(platform="LeetHub"),  # not an allowed platform
        _valid_payload(title="x" * 201),  # exceeds String(200)
        _valid_payload(title="   "),  # whitespace only
        _valid_payload(problem_url="javascript:alert(1)"),  # non-http scheme
        _valid_payload(problem_url="not a url"),  # no scheme/host
        {"user_id": 1, **_valid_payload()},  # unknown ownership field (extra=forbid)
    ],
)
def test_invalid_input_returns_422(client: TestClient, token_a: str, payload: dict):
    """12. Malformed payloads are rejected with HTTP 422 before touching the database."""
    response = client.post(BASE, json=payload, headers=_bearer(token_a))
    assert response.status_code == 422


@pytest.mark.parametrize("method, body", [("GET", None), ("PATCH", {"title": "X"}), ("DELETE", None)])
def test_missing_record_returns_404(
    client: TestClient, token_a: str, method: str, body
):
    """13. Read/update/delete of a nonexistent id returns 404."""
    response = client.request(method, f"{BASE}/999999", json=body, headers=_bearer(token_a))
    assert response.status_code == 404
    assert response.json()["detail"] == "DSA problem not found"


def test_patch_omitted_fields_are_preserved(client: TestClient, token_a: str):
    """14. PATCH only touches fields present in the payload."""
    created = client.post(
        BASE,
        json=_valid_payload(solved_date="2026-09-01"),
        headers=_bearer(token_a),
    )
    original = created.json()
    problem_id = original["id"]

    response = client.patch(
        f"{BASE}/{problem_id}",
        json={"notes": "Updated notes only"},
        headers=_bearer(token_a),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["notes"] == "Updated notes only"
    for unchanged in ("platform", "title", "topic", "difficulty", "solved_date", "problem_url", "user_id"):
        assert data[unchanged] == original[unchanged]
    assert data["solved_date"] == "2026-09-01"


# ---------------------------------------------------------------------------
# Extra coverage: pagination bounds, null handling, empty list
# ---------------------------------------------------------------------------

def test_list_pagination_with_bounds(client: TestClient, token_a: str):
    for i in range(5):
        res = client.post(
            BASE, json=_valid_payload(title=f"Problem {i}"), headers=_bearer(token_a)
        )
        assert res.status_code == 201

    page1 = client.get(BASE, params={"page": 1, "page_size": 2}, headers=_bearer(token_a))
    assert page1.status_code == 200
    body = page1.json()
    assert body["total"] == 5
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert len(body["items"]) == 2

    page3 = client.get(BASE, params={"page": 3, "page_size": 2}, headers=_bearer(token_a))
    assert page3.status_code == 200
    assert len(page3.json()["items"]) == 1

    beyond = client.get(BASE, params={"page": 99, "page_size": 2}, headers=_bearer(token_a))
    assert beyond.status_code == 200
    assert beyond.json()["items"] == []
    assert beyond.json()["total"] == 5

    # Out-of-bounds pagination parameters are rejected with 422
    assert client.get(BASE, params={"page": 0}, headers=_bearer(token_a)).status_code == 422
    assert client.get(BASE, params={"page_size": 0}, headers=_bearer(token_a)).status_code == 422
    assert client.get(BASE, params={"page_size": 101}, headers=_bearer(token_a)).status_code == 422
    # Extremely large page numbers are rejected instead of overflowing SQL OFFSET
    assert client.get(BASE, params={"page": 10**18}, headers=_bearer(token_a)).status_code == 422


def test_list_empty_returns_empty_page(client: TestClient, token_a: str):
    response = client.get(BASE, headers=_bearer(token_a))
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "page": 1, "page_size": 20}


def test_patch_explicit_null_on_required_field_rejected(
    client: TestClient, token_a: str
):
    """NOT NULL columns reject an explicit null with 422 instead of a database error."""
    created = client.post(BASE, json=_valid_payload(), headers=_bearer(token_a))
    problem_id = created.json()["id"]

    response = client.patch(
        f"{BASE}/{problem_id}", json={"title": None}, headers=_bearer(token_a)
    )
    assert response.status_code == 422


def test_patch_can_clear_nullable_fields(client: TestClient, token_a: str):
    """problem_url and notes are nullable and may be explicitly cleared."""
    created = client.post(BASE, json=_valid_payload(), headers=_bearer(token_a))
    problem_id = created.json()["id"]

    response = client.patch(
        f"{BASE}/{problem_id}",
        json={"problem_url": None, "notes": None},
        headers=_bearer(token_a),
    )
    assert response.status_code == 200
    assert response.json()["problem_url"] is None
    assert response.json()["notes"] is None
