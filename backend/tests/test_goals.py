from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.goal import Goal

BASE = "/api/v1/goals"


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _user_id(client: TestClient, token: str) -> int:
    me = client.get("/api/v1/auth/me", headers=_bearer(token))
    assert me.status_code == 200
    return me.json()["id"]


def _valid_payload(**overrides) -> dict:
    payload = {
        "title": "Solve 3 problems daily",
        "description": "Daily DSA streak",
        "goal_type": "daily",
        "target_count": 3,
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Creation, ownership, listing, retrieval, update, delete
# ---------------------------------------------------------------------------

def test_create_goal_success_with_defaults(client: TestClient, token_a: str):
    """1. Authenticated create returns 201 with defaults applied."""
    response = client.post(BASE, json=_valid_payload(), headers=_bearer(token_a))
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Solve 3 problems daily"
    assert data["goal_type"] == "daily"
    assert data["target_count"] == 3
    assert data["current_count"] == 0
    assert data["is_completed"] is False
    assert data["start_date"] == date.today().isoformat()
    assert data["end_date"] is None


def test_create_goal_owned_by_authenticated_user(
    client: TestClient, token_a: str, db_session: Session
):
    """2. The stored goal's user_id equals the authenticated user."""
    response = client.post(BASE, json=_valid_payload(), headers=_bearer(token_a))
    owner_id = _user_id(client, token_a)
    assert response.json()["user_id"] == owner_id

    row = db_session.execute(
        select(Goal).where(Goal.id == response.json()["id"])
    ).scalar_one()
    assert row.user_id == owner_id


def test_list_goals_returns_only_own(client: TestClient, token_a: str, token_b: str):
    """3. Each user's list contains only their own goals."""
    client.post(BASE, json=_valid_payload(title="A Goal 1"), headers=_bearer(token_a))
    client.post(BASE, json=_valid_payload(title="A Goal 2"), headers=_bearer(token_a))
    client.post(BASE, json=_valid_payload(title="B Goal 1"), headers=_bearer(token_b))

    list_a = client.get(BASE, headers=_bearer(token_a))
    assert list_a.status_code == 200
    assert list_a.json()["total"] == 2
    assert {item["title"] for item in list_a.json()["items"]} == {"A Goal 1", "A Goal 2"}


def test_retrieve_own_goal(client: TestClient, token_a: str):
    """4. The owner can fetch a single goal by id."""
    created = client.post(BASE, json=_valid_payload(), headers=_bearer(token_a))
    goal_id = created.json()["id"]

    response = client.get(f"{BASE}/{goal_id}", headers=_bearer(token_a))
    assert response.status_code == 200
    assert response.json()["id"] == goal_id


def test_update_own_goal_partial(client: TestClient, token_a: str, db_session: Session):
    """5. PATCH applies only supplied fields and persists changes."""
    created = client.post(BASE, json=_valid_payload(), headers=_bearer(token_a))
    goal_id = created.json()["id"]

    response = client.patch(
        f"{BASE}/{goal_id}",
        json={"current_count": 2, "is_completed": True},
        headers=_bearer(token_a),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["current_count"] == 2
    assert data["is_completed"] is True
    assert data["title"] == "Solve 3 problems daily"  # preserved

    row = db_session.get(Goal, goal_id)
    assert row.current_count == 2


def test_delete_own_goal(client: TestClient, token_a: str, db_session: Session):
    """6. DELETE removes the record: 204, then 404 and gone from the database."""
    created = client.post(BASE, json=_valid_payload(), headers=_bearer(token_a))
    goal_id = created.json()["id"]

    response = client.delete(f"{BASE}/{goal_id}", headers=_bearer(token_a))
    assert response.status_code == 204
    assert response.content == b""
    assert client.get(f"{BASE}/{goal_id}", headers=_bearer(token_a)).status_code == 404
    assert db_session.get(Goal, goal_id) is None


# ---------------------------------------------------------------------------
# Authentication and cross-user isolation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "method, path, body",
    [
        ("POST", BASE, {"title": "X", "goal_type": "daily"}),
        ("GET", BASE, None),
        ("GET", f"{BASE}/1", None),
        ("PATCH", f"{BASE}/1", {"current_count": 1}),
        ("DELETE", f"{BASE}/1", None),
    ],
)
def test_unauthenticated_requests_rejected(
    client: TestClient, method: str, path: str, body
):
    """7. Every endpoint returns 401 without a Bearer token."""
    assert client.request(method, path, json=body).status_code == 401


def test_user_cannot_read_other_users_goal(client: TestClient, token_a: str, token_b: str):
    """8. Fetching a foreign goal returns the same 404 as a missing one."""
    created = client.post(BASE, json=_valid_payload(), headers=_bearer(token_a))
    goal_id = created.json()["id"]

    response = client.get(f"{BASE}/{goal_id}", headers=_bearer(token_b))
    assert response.status_code == 404
    assert response.json()["detail"] == "Goal not found"
    missing = client.get(f"{BASE}/999999", headers=_bearer(token_b))
    assert missing.json()["detail"] == response.json()["detail"]


def test_user_cannot_update_other_users_goal(
    client: TestClient, token_a: str, token_b: str, db_session: Session
):
    """9. PATCH on a foreign goal returns 404 and changes nothing."""
    created = client.post(BASE, json=_valid_payload(), headers=_bearer(token_a))
    goal_id = created.json()["id"]

    response = client.patch(
        f"{BASE}/{goal_id}", json={"current_count": 99}, headers=_bearer(token_b)
    )
    assert response.status_code == 404
    assert db_session.get(Goal, goal_id).current_count == 0


def test_user_cannot_delete_other_users_goal(
    client: TestClient, token_a: str, token_b: str, db_session: Session
):
    """10. DELETE on a foreign goal returns 404 and the record survives."""
    created = client.post(BASE, json=_valid_payload(), headers=_bearer(token_a))
    goal_id = created.json()["id"]

    response = client.delete(f"{BASE}/{goal_id}", headers=_bearer(token_b))
    assert response.status_code == 404
    assert db_session.get(Goal, goal_id) is not None


# ---------------------------------------------------------------------------
# Validation and spoofing protection
# ---------------------------------------------------------------------------

def test_client_supplied_user_id_rejected(client: TestClient, token_a: str, db_session: Session):
    """11. A spoofed user_id is rejected with 422 and creates nothing."""
    response = client.post(
        BASE, json=_valid_payload(user_id=9999), headers=_bearer(token_a)
    )
    assert response.status_code == 422
    assert db_session.execute(select(Goal)).scalars().all() == []


@pytest.mark.parametrize(
    "payload",
    [
        {},  # missing required fields
        _valid_payload(goal_type="monthly"),  # not an allowed cadence
        _valid_payload(target_count=0),  # below minimum
        _valid_payload(current_count=-1),  # negative progress
        _valid_payload(title="   "),  # whitespace only
    ],
)
def test_invalid_input_returns_422(client: TestClient, token_a: str, payload: dict):
    """12. Malformed payloads are rejected with 422."""
    assert client.post(BASE, json=payload, headers=_bearer(token_a)).status_code == 422


def test_create_rejects_end_date_before_start_date(client: TestClient, token_a: str):
    """13. An inverted date range is rejected at creation."""
    response = client.post(
        BASE,
        json=_valid_payload(start_date="2026-10-10", end_date="2026-10-01"),
        headers=_bearer(token_a),
    )
    assert response.status_code == 422


def test_patch_cannot_invert_stored_date_range(client: TestClient, token_a: str):
    """14. PATCH re-validates the combined stored range, not just the payload."""
    created = client.post(
        BASE,
        json=_valid_payload(start_date="2026-10-01", end_date="2026-10-31"),
        headers=_bearer(token_a),
    )
    goal_id = created.json()["id"]

    # Moving start_date past the stored end_date must fail with 422
    response = client.patch(
        f"{BASE}/{goal_id}",
        json={"start_date": "2026-11-15"},
        headers=_bearer(token_a),
    )
    assert response.status_code == 422
    assert "end_date" in response.json()["detail"]


def test_missing_record_returns_404(client: TestClient, token_a: str):
    """13b. Read/update/delete of a nonexistent id returns 404."""
    assert client.get(f"{BASE}/999999", headers=_bearer(token_a)).status_code == 404
    assert (
        client.patch(f"{BASE}/999999", json={"current_count": 1}, headers=_bearer(token_a)).status_code
        == 404
    )
    assert client.delete(f"{BASE}/999999", headers=_bearer(token_a)).status_code == 404
