import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.project import Milestone, Project
from app.models.task import Task

BASE = "/api/v1/projects"


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _valid_payload(**overrides) -> dict:
    payload = {
        "title": "DevTrack",
        "description": "Developer productivity tracker",
        "tech_stack": "FastAPI, React, PostgreSQL",
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# CRUD basics
# ---------------------------------------------------------------------------

def test_create_project_success_with_defaults(client: TestClient, token_a: str):
    """1. Authenticated create returns 201 with defaults applied."""
    response = client.post(BASE, json=_valid_payload(), headers=_bearer(token_a))
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "DevTrack"
    assert data["status"] == "in_progress"
    assert data["repo_url"] is None
    assert data["demo_url"] is None


def test_create_project_owned_by_authenticated_user(
    client: TestClient, token_a: str, db_session: Session
):
    """2. The stored project's user_id equals the authenticated user."""
    response = client.post(BASE, json=_valid_payload(), headers=_bearer(token_a))
    row = db_session.get(Project, response.json()["id"])
    assert row.user_id == response.json()["user_id"]


def test_list_projects_returns_only_own(client: TestClient, token_a: str, token_b: str):
    """3. Each user's list contains only their own projects."""
    client.post(BASE, json=_valid_payload(title="A Project"), headers=_bearer(token_a))
    client.post(BASE, json=_valid_payload(title="B Project"), headers=_bearer(token_b))

    list_a = client.get(BASE, headers=_bearer(token_a))
    assert list_a.status_code == 200
    assert list_a.json()["total"] == 1
    assert list_a.json()["items"][0]["title"] == "A Project"


def test_retrieve_own_project(client: TestClient, token_a: str):
    created = client.post(BASE, json=_valid_payload(), headers=_bearer(token_a))
    project_id = created.json()["id"]
    response = client.get(f"{BASE}/{project_id}", headers=_bearer(token_a))
    assert response.status_code == 200
    assert response.json()["id"] == project_id


def test_update_own_project_partial(client: TestClient, token_a: str, db_session: Session):
    """5. PATCH applies only supplied fields; nullable URLs can be set and cleared."""
    created = client.post(
        BASE,
        json=_valid_payload(repo_url="https://github.com/example/devtrack"),
        headers=_bearer(token_a),
    )
    project_id = created.json()["id"]

    patched = client.patch(
        f"{BASE}/{project_id}",
        json={"status": "completed", "demo_url": "https://devtrack.example.com"},
        headers=_bearer(token_a),
    )
    assert patched.status_code == 200
    data = patched.json()
    assert data["status"] == "completed"
    assert data["demo_url"] == "https://devtrack.example.com"
    assert data["repo_url"] == "https://github.com/example/devtrack"  # preserved
    assert data["title"] == "DevTrack"  # preserved

    # Clear a nullable field explicitly
    cleared = client.patch(
        f"{BASE}/{project_id}", json={"repo_url": None}, headers=_bearer(token_a)
    )
    assert cleared.status_code == 200
    assert cleared.json()["repo_url"] is None
    assert db_session.get(Project, project_id).repo_url is None


def test_delete_project_cascades_milestones_and_nulls_tasks(
    client: TestClient, token_a: str, db_session: Session
):
    """6. Deleting a project removes milestones and detaches (keeps) tasks."""
    project_id = client.post(
        BASE, json=_valid_payload(), headers=_bearer(token_a)
    ).json()["id"]

    milestone_id = client.post(
        f"{BASE}/{project_id}/milestones",
        json={"title": "MVP"},
        headers=_bearer(token_a),
    ).json()["id"]

    task_id = client.post(
        "/api/v1/tasks",
        json={"title": "Write README", "project_id": project_id},
        headers=_bearer(token_a),
    ).json()["id"]

    response = client.delete(f"{BASE}/{project_id}", headers=_bearer(token_a))
    assert response.status_code == 204
    assert response.content == b""

    # Milestone cascade-deleted; task survives with a NULL project
    assert db_session.get(Milestone, milestone_id) is None
    surviving_task = db_session.get(Task, task_id)
    assert surviving_task is not None
    assert surviving_task.project_id is None
    assert client.get(f"{BASE}/{project_id}", headers=_bearer(token_a)).status_code == 404


# ---------------------------------------------------------------------------
# Authentication, cross-user isolation, spoofing, validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "method, path, body",
    [
        ("POST", BASE, {"title": "X"}),
        ("GET", BASE, None),
        ("GET", f"{BASE}/1", None),
        ("PATCH", f"{BASE}/1", {"status": "completed"}),
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
    """8. Another user's project is invisible to read, update, and delete."""
    created = client.post(BASE, json=_valid_payload(), headers=_bearer(token_a))
    project_id = created.json()["id"]

    get_res = client.get(f"{BASE}/{project_id}", headers=_bearer(token_b))
    assert get_res.status_code == 404
    assert get_res.json()["detail"] == "Project not found"
    assert (
        client.patch(f"{BASE}/{project_id}", json={"title": "Hijacked"}, headers=_bearer(token_b)).status_code
        == 404
    )
    assert client.delete(f"{BASE}/{project_id}", headers=_bearer(token_b)).status_code == 404

    assert db_session.get(Project, project_id).title == "DevTrack"  # unchanged


def test_client_supplied_user_id_rejected(client: TestClient, token_a: str, db_session: Session):
    """9. A spoofed user_id is rejected with 422 and creates nothing."""
    response = client.post(
        BASE, json=_valid_payload(user_id=9999), headers=_bearer(token_a)
    )
    assert response.status_code == 422
    assert db_session.execute(select(Project)).scalars().all() == []


@pytest.mark.parametrize(
    "payload",
    [
        {},  # missing title
        _valid_payload(status="on_hold"),  # not an allowed status
        _valid_payload(repo_url="javascript:alert(1)"),  # non-http scheme
        _valid_payload(demo_url="not a url"),  # no scheme/host
    ],
)
def test_invalid_input_returns_422(client: TestClient, token_a: str, payload: dict):
    """10. Malformed payloads are rejected with 422."""
    assert client.post(BASE, json=payload, headers=_bearer(token_a)).status_code == 422


def test_missing_record_returns_404(client: TestClient, token_a: str):
    """11. Read/update/delete of a nonexistent id returns 404."""
    assert client.get(f"{BASE}/999999", headers=_bearer(token_a)).status_code == 404
    assert (
        client.patch(f"{BASE}/999999", json={"title": "X"}, headers=_bearer(token_a)).status_code
        == 404
    )
    assert client.delete(f"{BASE}/999999", headers=_bearer(token_a)).status_code == 404
