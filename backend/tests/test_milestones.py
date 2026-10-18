import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.project import Milestone

PROJECTS = "/api/v1/projects"


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_project(client: TestClient, token: str, title: str = "My Project") -> int:
    res = client.post(PROJECTS, json={"title": title}, headers=_bearer(token))
    assert res.status_code == 201
    return res.json()["id"]


def _base(project_id: int) -> str:
    return f"{PROJECTS}/{project_id}/milestones"


# ---------------------------------------------------------------------------
# Creation through an owned parent project
# ---------------------------------------------------------------------------

def test_create_milestone_under_own_project(client: TestClient, token_a: str):
    """1. Create returns 201; parent comes from the path, not the body."""
    project_id = _create_project(client, token_a)
    response = client.post(
        _base(project_id), json={"title": "MVP"}, headers=_bearer(token_a)
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "MVP"
    assert data["project_id"] == project_id
    assert data["is_completed"] is False


def test_create_milestone_under_foreign_project_rejected(
    client: TestClient, token_a: str, token_b: str, db_session: Session
):
    """2. Another user's project returns 404 and creates nothing."""
    project_id = _create_project(client, token_b, "Bob's Project")
    response = client.post(
        _base(project_id), json={"title": "Sneaky"}, headers=_bearer(token_a)
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"
    assert db_session.execute(select(Milestone)).scalars().all() == []


def test_spoofed_body_fields_rejected(client: TestClient, token_a: str):
    """3. user_id/project_id in the body are unknown fields -> 422."""
    project_id = _create_project(client, token_a)
    response = client.post(
        _base(project_id),
        json={"title": "X", "user_id": 9999, "project_id": 9999},
        headers=_bearer(token_a),
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------

def test_list_milestones_scoped_to_project(client: TestClient, token_a: str, token_b: str):
    """4. Listing shows only the requested project's milestones; foreign project -> 404."""
    p1 = _create_project(client, token_a, "Project One")
    p2 = _create_project(client, token_a, "Project Two")
    bp = _create_project(client, token_b, "Bob's Project")

    client.post(_base(p1), json={"title": "M1"}, headers=_bearer(token_a))
    client.post(_base(p1), json={"title": "M2"}, headers=_bearer(token_a))
    client.post(_base(p2), json={"title": "M3"}, headers=_bearer(token_a))
    client.post(_base(bp), json={"title": "BM1"}, headers=_bearer(token_b))

    list_p1 = client.get(_base(p1), headers=_bearer(token_a))
    assert list_p1.status_code == 200
    body = list_p1.json()
    assert body["total"] == 2
    assert {item["title"] for item in body["items"]} == {"M1", "M2"}
    assert all(item["project_id"] == p1 for item in body["items"])

    # Bob cannot list milestones of Alice's project
    assert client.get(_base(p1), headers=_bearer(token_b)).status_code == 404


# ---------------------------------------------------------------------------
# Read, update, delete
# ---------------------------------------------------------------------------

def test_retrieve_own_milestone(client: TestClient, token_a: str):
    project_id = _create_project(client, token_a)
    created = client.post(
        _base(project_id), json={"title": "M"}, headers=_bearer(token_a)
    )
    milestone_id = created.json()["id"]

    response = client.get(
        f"{_base(project_id)}/{milestone_id}", headers=_bearer(token_a)
    )
    assert response.status_code == 200
    assert response.json()["id"] == milestone_id


def test_update_own_milestone_partial(client: TestClient, token_a: str, db_session: Session):
    project_id = _create_project(client, token_a)
    created = client.post(
        _base(project_id), json={"title": "M", "due_date": "2026-11-30"},
        headers=_bearer(token_a),
    )
    milestone_id = created.json()["id"]

    response = client.patch(
        f"{_base(project_id)}/{milestone_id}",
        json={"is_completed": True},
        headers=_bearer(token_a),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["is_completed"] is True
    assert data["title"] == "M"  # preserved
    assert data["due_date"] == "2026-11-30"  # preserved
    assert db_session.get(Milestone, milestone_id).is_completed is True


def test_delete_own_milestone(client: TestClient, token_a: str, db_session: Session):
    project_id = _create_project(client, token_a)
    created = client.post(
        _base(project_id), json={"title": "M"}, headers=_bearer(token_a)
    )
    milestone_id = created.json()["id"]

    response = client.delete(
        f"{_base(project_id)}/{milestone_id}", headers=_bearer(token_a)
    )
    assert response.status_code == 204
    assert response.content == b""
    assert db_session.get(Milestone, milestone_id) is None


# ---------------------------------------------------------------------------
# Authentication and cross-user isolation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "method, path_template, body",
    [
        ("GET", "{base}", None),
        ("POST", "{base}", {"title": "X"}),
        ("GET", "{base}/1", None),
        ("PATCH", "{base}/1", {"is_completed": True}),
        ("DELETE", "{base}/1", None),
    ],
)
def test_unauthenticated_requests_rejected(
    client: TestClient, method: str, path_template: str, body
):
    """7. Every nested endpoint returns 401 without a Bearer token."""
    assert (
        client.request(method, path_template.format(base=_base(1)), json=body).status_code
        == 401
    )


def test_cross_user_milestone_operations_return_404(
    client: TestClient, token_a: str, token_b: str, db_session: Session
):
    """8-10. Through a foreign parent project, milestones are invisible."""
    project_id = _create_project(client, token_a)
    created = client.post(
        _base(project_id), json={"title": "M"}, headers=_bearer(token_a)
    )
    milestone_id = created.json()["id"]

    # Bob uses Alice's project path: every operation 404s
    assert client.get(
        f"{_base(project_id)}/{milestone_id}", headers=_bearer(token_b)
    ).status_code == 404
    patch = client.patch(
        f"{_base(project_id)}/{milestone_id}",
        json={"title": "Hijacked"},
        headers=_bearer(token_b),
    )
    assert patch.status_code == 404
    assert (
        client.delete(f"{_base(project_id)}/{milestone_id}", headers=_bearer(token_b)).status_code
        == 404
    )

    # Nothing changed, nothing deleted
    row = db_session.get(Milestone, milestone_id)
    assert row.title == "M"


def test_missing_ids_return_404(client: TestClient, token_a: str):
    """13. Missing project and missing milestone both return 404."""
    project_id = _create_project(client, token_a)

    assert client.get(_base(999999), headers=_bearer(token_a)).status_code == 404
    assert (
        client.post(_base(999999), json={"title": "X"}, headers=_bearer(token_a)).status_code
        == 404
    )
    assert client.get(f"{_base(project_id)}/999999", headers=_bearer(token_a)).status_code == 404


def test_pagination_bounds(client: TestClient, token_a: str):
    """Nested listing honors the same pagination bounds as other resources."""
    project_id = _create_project(client, token_a)
    for i in range(3):
        assert (
            client.post(_base(project_id), json={"title": f"M{i}"}, headers=_bearer(token_a)).status_code
            == 201
        )

    page1 = client.get(
        _base(project_id), params={"page": 1, "page_size": 2}, headers=_bearer(token_a)
    )
    assert page1.status_code == 200
    assert page1.json()["total"] == 3
    assert len(page1.json()["items"]) == 2

    assert (
        client.get(_base(project_id), params={"page_size": 101}, headers=_bearer(token_a)).status_code
        == 422
    )
    assert (
        client.get(_base(project_id), params={"page": 10**18}, headers=_bearer(token_a)).status_code
        == 422
    )
