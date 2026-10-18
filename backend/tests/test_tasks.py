import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.task import Task

BASE = "/api/v1/tasks"
PROJECTS = "/api/v1/projects"


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_project(client: TestClient, token: str, title: str = "My Project") -> int:
    res = client.post(
        PROJECTS, json={"title": title}, headers=_bearer(token)
    )
    assert res.status_code == 201
    return res.json()["id"]


def _valid_payload(**overrides) -> dict:
    payload = {"title": "Implement auth middleware"}
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Creation, including cross-entity authorization on project_id
# ---------------------------------------------------------------------------

def test_create_task_without_project(client: TestClient, token_a: str):
    """1. Create succeeds without a project and applies defaults."""
    response = client.post(BASE, json=_valid_payload(), headers=_bearer(token_a))
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "todo"
    assert data["priority"] == "medium"
    assert data["project_id"] is None


def test_create_task_with_own_project(client: TestClient, token_a: str):
    """2. Attaching a task to an owned project succeeds."""
    project_id = _create_project(client, token_a)
    response = client.post(
        BASE, json=_valid_payload(project_id=project_id), headers=_bearer(token_a)
    )
    assert response.status_code == 201
    assert response.json()["project_id"] == project_id


def test_create_task_with_foreign_project_rejected(
    client: TestClient, token_a: str, token_b: str, db_session: Session
):
    """3. Attaching to another user's project returns 404 and creates nothing."""
    project_id = _create_project(client, token_b, "Bob's Project")

    response = client.post(
        BASE, json=_valid_payload(project_id=project_id), headers=_bearer(token_a)
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"
    assert db_session.execute(select(Task)).scalars().all() == []


def test_create_task_owned_by_authenticated_user(
    client: TestClient, token_a: str, db_session: Session
):
    """The stored task's user_id equals the authenticated user."""
    response = client.post(BASE, json=_valid_payload(), headers=_bearer(token_a))
    row = db_session.get(Task, response.json()["id"])
    assert row.user_id == response.json()["user_id"]


# ---------------------------------------------------------------------------
# Listing with filters
# ---------------------------------------------------------------------------

def test_list_filters_and_ownership(client: TestClient, token_a: str, token_b: str):
    """5. status/priority filters apply in SQL; lists stay user-scoped."""
    client.post(BASE, json=_valid_payload(title="A1", status="todo"), headers=_bearer(token_a))
    client.post(BASE, json=_valid_payload(title="A2", status="done", priority="high"), headers=_bearer(token_a))
    client.post(BASE, json=_valid_payload(title="B1"), headers=_bearer(token_b))

    all_a = client.get(BASE, headers=_bearer(token_a))
    assert all_a.status_code == 200
    assert all_a.json()["total"] == 2

    done_only = client.get(BASE, params={"status": "done"}, headers=_bearer(token_a))
    assert done_only.json()["total"] == 1
    assert done_only.json()["items"][0]["title"] == "A2"

    high_only = client.get(BASE, params={"priority": "high"}, headers=_bearer(token_a))
    assert high_only.json()["total"] == 1

    # Bob sees only his own task
    list_b = client.get(BASE, headers=_bearer(token_b))
    assert list_b.json()["total"] == 1
    assert list_b.json()["items"][0]["title"] == "B1"

    # Invalid filter values are rejected with 422
    assert client.get(BASE, params={"status": "urgent"}, headers=_bearer(token_a)).status_code == 422


# ---------------------------------------------------------------------------
# Read, update, delete own tasks
# ---------------------------------------------------------------------------

def test_retrieve_own_task(client: TestClient, token_a: str):
    created = client.post(BASE, json=_valid_payload(), headers=_bearer(token_a))
    task_id = created.json()["id"]
    response = client.get(f"{BASE}/{task_id}", headers=_bearer(token_a))
    assert response.status_code == 200
    assert response.json()["id"] == task_id


def test_update_own_task_partial(client: TestClient, token_a: str, db_session: Session):
    created = client.post(BASE, json=_valid_payload(), headers=_bearer(token_a))
    task_id = created.json()["id"]

    response = client.patch(
        f"{BASE}/{task_id}",
        json={"status": "in_progress", "priority": "high"},
        headers=_bearer(token_a),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "in_progress"
    assert data["priority"] == "high"
    assert data["title"] == "Implement auth middleware"  # preserved
    assert db_session.get(Task, task_id).status == "in_progress"


def test_patch_detach_project_with_null(client: TestClient, token_a: str, db_session: Session):
    """An explicit project_id: null detaches the task (mirrors SET NULL)."""
    project_id = _create_project(client, token_a)
    created = client.post(
        BASE, json=_valid_payload(project_id=project_id), headers=_bearer(token_a)
    )
    task_id = created.json()["id"]

    response = client.patch(
        f"{BASE}/{task_id}", json={"project_id": None}, headers=_bearer(token_a)
    )
    assert response.status_code == 200
    assert response.json()["project_id"] is None
    assert db_session.get(Task, task_id).project_id is None


def test_patch_attach_foreign_project_rejected(
    client: TestClient, token_a: str, token_b: str, db_session: Session
):
    """PATCH cannot move a task under another user's project."""
    project_id = _create_project(client, token_b, "Bob's Project")
    created = client.post(BASE, json=_valid_payload(), headers=_bearer(token_a))
    task_id = created.json()["id"]

    response = client.patch(
        f"{BASE}/{task_id}", json={"project_id": project_id}, headers=_bearer(token_a)
    )
    assert response.status_code == 404
    assert db_session.get(Task, task_id).project_id is None  # unchanged


def test_delete_own_task(client: TestClient, token_a: str, db_session: Session):
    created = client.post(BASE, json=_valid_payload(), headers=_bearer(token_a))
    task_id = created.json()["id"]

    response = client.delete(f"{BASE}/{task_id}", headers=_bearer(token_a))
    assert response.status_code == 204
    assert response.content == b""
    assert client.get(f"{BASE}/{task_id}", headers=_bearer(token_a)).status_code == 404
    assert db_session.get(Task, task_id) is None


# ---------------------------------------------------------------------------
# Authentication, cross-user isolation, spoofing, validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "method, path, body",
    [
        ("POST", BASE, {"title": "X"}),
        ("GET", BASE, None),
        ("GET", f"{BASE}/1", None),
        ("PATCH", f"{BASE}/1", {"status": "done"}),
        ("DELETE", f"{BASE}/1", None),
    ],
)
def test_unauthenticated_requests_rejected(
    client: TestClient, method: str, path: str, body
):
    """7. Every endpoint returns 401 without a Bearer token."""
    assert client.request(method, path, json=body).status_code == 401


def test_cross_user_read_update_delete_return_404(
    client: TestClient, token_a: str, token_b: str, db_session: Session
):
    """8-10. Another user's task is invisible to read, update, and delete."""
    created = client.post(BASE, json=_valid_payload(), headers=_bearer(token_a))
    task_id = created.json()["id"]

    assert client.get(f"{BASE}/{task_id}", headers=_bearer(token_b)).status_code == 404
    patch = client.patch(
        f"{BASE}/{task_id}", json={"status": "done"}, headers=_bearer(token_b)
    )
    assert patch.status_code == 404
    assert client.delete(f"{BASE}/{task_id}", headers=_bearer(token_b)).status_code == 404

    # Nothing changed and nothing was deleted
    row = db_session.get(Task, task_id)
    assert row.status == "todo"


def test_client_supplied_user_id_rejected(client: TestClient, token_a: str, db_session: Session):
    """11. A spoofed user_id is rejected with 422 and creates nothing."""
    response = client.post(
        BASE, json=_valid_payload(user_id=9999), headers=_bearer(token_a)
    )
    assert response.status_code == 422
    assert db_session.execute(select(Task)).scalars().all() == []


@pytest.mark.parametrize(
    "payload",
    [
        {},  # missing title
        _valid_payload(status="urgent"),  # not an allowed status
        _valid_payload(priority="critical"),  # not an allowed priority
        _valid_payload(project_id=0),  # below minimum
    ],
)
def test_invalid_input_returns_422(client: TestClient, token_a: str, payload: dict):
    """12. Malformed payloads are rejected with 422."""
    assert client.post(BASE, json=payload, headers=_bearer(token_a)).status_code == 422


def test_missing_record_returns_404(client: TestClient, token_a: str):
    """13. Read/update/delete of a nonexistent id returns 404."""
    assert client.get(f"{BASE}/999999", headers=_bearer(token_a)).status_code == 404
    assert (
        client.patch(f"{BASE}/999999", json={"status": "done"}, headers=_bearer(token_a)).status_code
        == 404
    )
    assert client.delete(f"{BASE}/999999", headers=_bearer(token_a)).status_code == 404
