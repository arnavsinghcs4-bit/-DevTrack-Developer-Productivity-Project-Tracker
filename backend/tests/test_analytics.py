from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

BASE = "/api/v1/analytics/dashboard"
DSA = "/api/v1/dsa-problems"
GOALS = "/api/v1/goals"
TASKS = "/api/v1/tasks"
PROJECTS = "/api/v1/projects"


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _seed_dsa(client: TestClient, token: str, **overrides) -> None:
    payload = {
        "title": "Two Sum",
        "platform": "LeetCode",
        "difficulty": "Easy",
        "topic": "Arrays",
    }
    payload.update(overrides)
    res = client.post(DSA, json=payload, headers=_bearer(token))
    assert res.status_code == 201


def _seed_goal(client: TestClient, token: str, **overrides) -> None:
    payload = {
        "title": "Daily practice",
        "goal_type": "daily",
        "target_count": 5,
        "current_count": 2,
    }
    payload.update(overrides)
    res = client.post(GOALS, json=payload, headers=_bearer(token))
    assert res.status_code == 201


def _seed_task(client: TestClient, token: str, **overrides) -> None:
    payload = {"title": "Write docs"}
    payload.update(overrides)
    res = client.post(TASKS, json=payload, headers=_bearer(token))
    assert res.status_code == 201


def _seed_project_with_milestones(
    client: TestClient, token: str, milestones: int = 0, completed: int = 0
) -> int:
    res = client.post(
        PROJECTS, json={"title": "Seed Project"}, headers=_bearer(token)
    )
    assert res.status_code == 201
    project_id = res.json()["id"]
    for i in range(milestones):
        m = client.post(
            f"{PROJECTS}/{project_id}/milestones",
            json={"title": f"M{i}", "is_completed": i < completed},
            headers=_bearer(token),
        )
        assert m.status_code == 201
    return project_id


# ---------------------------------------------------------------------------
# Authentication and empty state
# ---------------------------------------------------------------------------


def test_dashboard_requires_authentication(client: TestClient):
    """1. The dashboard returns 401 without a Bearer token."""
    assert client.get(BASE).status_code == 401


def test_dashboard_empty_state(client: TestClient, token_a: str):
    """2. A fresh user gets a fully zero-filled, fixed-shape dashboard."""
    response = client.get(BASE, headers=_bearer(token_a))
    assert response.status_code == 200
    data = response.json()

    assert data["dsa"]["total"] == 0
    assert data["dsa"]["active_days"] == 0
    # Zero-filled difficulty buckets in canonical order
    assert [b["difficulty"] for b in data["dsa"]["by_difficulty"]] == [
        "Easy",
        "Medium",
        "Hard",
    ]
    assert all(b["count"] == 0 for b in data["dsa"]["by_difficulty"])
    assert data["dsa"]["by_topic"] == []
    assert data["dsa"]["by_platform"] == []
    # Dense trend: one point per requested day, all zeros
    assert len(data["dsa"]["solved_trend"]) == 30
    assert all(p["count"] == 0 for p in data["dsa"]["solved_trend"])

    assert data["goals"]["total"] == 0
    assert data["goals"]["completed"] == 0
    assert data["goals"]["completion_rate"] == 0.0
    assert data["goals"]["avg_progress_percent"] == 0.0
    assert [t["goal_type"] for t in data["goals"]["by_type"]] == ["daily", "weekly"]

    assert data["tasks"]["total"] == 0
    assert data["tasks"]["overdue"] == 0
    assert [s["status"] for s in data["tasks"]["by_status"]] == [
        "todo",
        "in_progress",
        "done",
    ]
    assert [p["priority"] for p in data["tasks"]["by_priority"]] == [
        "low",
        "medium",
        "high",
    ]

    assert data["projects"]["total"] == 0
    assert data["projects"]["milestones_total"] == 0
    assert data["projects"]["milestones_completed"] == 0


# ---------------------------------------------------------------------------
# Aggregation correctness
# ---------------------------------------------------------------------------


def test_dashboard_aggregates_own_data(client: TestClient, token_a: str):
    """3. SQL aggregation returns exact counts, rates, and trend buckets."""
    today = date.today().isoformat()

    # DSA: 2 Easy (Arrays), 1 Hard (Dynamic Programming), 1 Medium (Arrays)
    _seed_dsa(client, token_a)
    _seed_dsa(client, token_a, title="Valid Parentheses")
    _seed_dsa(client, token_a, difficulty="Hard", topic="Dynamic Programming")
    _seed_dsa(client, token_a, difficulty="Medium")

    # Goals: 2 daily (1 completed, 50% and 100% progress), 1 weekly
    _seed_goal(client, token_a, current_count=5)  # 100% progress
    _seed_goal(
        client, token_a, goal_type="weekly", current_count=2, is_completed=True
    )
    _seed_goal(client, token_a, current_count=2)  # 40% progress

    # Tasks: 1 done, 1 overdue (past due, not done), 1 upcoming
    _seed_task(client, token_a, status="done", priority="low", due_date="2020-01-01")
    _seed_task(
        client,
        token_a,
        status="in_progress",
        priority="high",
        due_date=(date.today() - timedelta(days=1)).isoformat(),
    )
    _seed_task(
        client,
        token_a,
        due_date=(date.today() + timedelta(days=7)).isoformat(),
    )

    # Projects: 1 project, 2 milestones (1 completed)
    _seed_project_with_milestones(client, token_a, milestones=2, completed=1)

    data = client.get(BASE, headers=_bearer(token_a)).json()

    # --- DSA ---
    assert data["dsa"]["total"] == 4
    assert data["dsa"]["active_days"] == 1  # all solved today
    difficulty = {b["difficulty"]: b["count"] for b in data["dsa"]["by_difficulty"]}
    assert difficulty == {"Easy": 2, "Medium": 1, "Hard": 1}
    topics = {b["topic"]: b["count"] for b in data["dsa"]["by_topic"]}
    assert topics == {"Arrays": 3, "Dynamic Programming": 1}
    platforms = {b["platform"]: b["count"] for b in data["dsa"]["by_platform"]}
    assert platforms == {"LeetCode": 4}
    # Today is the last bucket of the 30-day window and holds all 4 solves
    assert len(data["dsa"]["solved_trend"]) == 30
    assert data["dsa"]["solved_trend"][-1] == {"solved_date": today, "count": 4}
    assert sum(p["count"] for p in data["dsa"]["solved_trend"]) == 4

    # --- Goals ---
    assert data["goals"]["total"] == 3
    assert data["goals"]["completed"] == 1
    assert data["goals"]["completion_rate"] == 33.3  # 1/3
    # progress: 100% + 40% + 40% = 60.0 average
    assert data["goals"]["avg_progress_percent"] == 60.0
    by_type = {t["goal_type"]: t for t in data["goals"]["by_type"]}
    assert by_type["daily"]["total"] == 2
    assert by_type["daily"]["completed"] == 0
    assert by_type["weekly"]["total"] == 1
    assert by_type["weekly"]["completed"] == 1

    # --- Tasks ---
    assert data["tasks"]["total"] == 3
    assert data["tasks"]["overdue"] == 1  # only the in_progress past-due task
    status = {s["status"]: s["count"] for s in data["tasks"]["by_status"]}
    assert status == {"todo": 1, "in_progress": 1, "done": 1}
    priority = {p["priority"]: p["count"] for p in data["tasks"]["by_priority"]}
    assert priority == {"low": 1, "medium": 1, "high": 1}

    # --- Projects ---
    assert data["projects"]["total"] == 1
    project_status = {s["status"]: s["count"] for s in data["projects"]["by_status"]}
    assert project_status == {"planning": 0, "in_progress": 1, "completed": 0}
    assert data["projects"]["milestones_total"] == 2
    assert data["projects"]["milestones_completed"] == 1


def test_dashboard_overdue_excludes_done_and_future(client: TestClient, token_a: str):
    """Overdue = past due_date AND status != done (a done late task is not overdue)."""
    past = (date.today() - timedelta(days=3)).isoformat()
    future = (date.today() + timedelta(days=3)).isoformat()

    _seed_task(client, token_a, status="done", due_date=past)  # done: not overdue
    _seed_task(client, token_a, status="todo", due_date=future)  # future: not overdue
    _seed_task(client, token_a, status="todo")  # no due date: not overdue
    _seed_task(client, token_a, status="todo", due_date=past)  # overdue

    data = client.get(BASE, headers=_bearer(token_a)).json()
    assert data["tasks"]["total"] == 4
    assert data["tasks"]["overdue"] == 1


# ---------------------------------------------------------------------------
# Isolation and trend window
# ---------------------------------------------------------------------------


def test_dashboard_isolated_between_users(client: TestClient, token_a: str, token_b: str):
    """4. One user's activity never appears in another user's dashboard."""
    _seed_dsa(client, token_a)
    _seed_dsa(client, token_a, difficulty="Hard")
    _seed_goal(client, token_a, is_completed=True)
    _seed_task(client, token_a, status="done")
    _seed_project_with_milestones(client, token_a, milestones=1, completed=1)

    data_b = client.get(BASE, headers=_bearer(token_b)).json()
    assert data_b["dsa"]["total"] == 0
    assert data_b["goals"]["total"] == 0
    assert data_b["tasks"]["total"] == 0
    assert data_b["projects"]["total"] == 0
    assert data_b["projects"]["milestones_total"] == 0
    assert all(b["count"] == 0 for b in data_b["dsa"]["by_difficulty"])

    data_a = client.get(BASE, headers=_bearer(token_a)).json()
    assert data_a["dsa"]["total"] == 2


def test_dashboard_trend_window(client: TestClient, token_a: str):
    """5. `days` controls the dense trend window; old solves fall outside it."""
    _seed_dsa(
        client,
        token_a,
        title="Old solve",
        solved_date=(date.today() - timedelta(days=40)).isoformat(),
    )
    _seed_dsa(client, token_a, title="Recent solve")  # today

    # 30-day window: only the recent solve counts toward the trend
    narrow = client.get(BASE, params={"days": 30}, headers=_bearer(token_a)).json()
    assert len(narrow["dsa"]["solved_trend"]) == 30
    assert sum(p["count"] for p in narrow["dsa"]["solved_trend"]) == 1
    # Totals and active days still cover all time
    assert narrow["dsa"]["total"] == 2
    assert narrow["dsa"]["active_days"] == 2

    # 90-day window: both solves appear as dense buckets
    wide = client.get(BASE, params={"days": 90}, headers=_bearer(token_a)).json()
    assert len(wide["dsa"]["solved_trend"]) == 90
    assert sum(p["count"] for p in wide["dsa"]["solved_trend"]) == 2

    # The dense series ends today
    assert narrow["dsa"]["solved_trend"][-1]["solved_date"] == date.today().isoformat()


@pytest.mark.parametrize("days", [0, -1, 366, 10**9, "abc"])
def test_dashboard_days_bounds(client: TestClient, token_a: str, days):
    """6. The days parameter is bounded (1-365) and must be an integer."""
    assert (
        client.get(BASE, params={"days": days}, headers=_bearer(token_a)).status_code
        == 422
    )


def test_dashboard_days_custom_window(client: TestClient, token_a: str):
    """7. A custom window size produces exactly that many trend buckets."""
    data = client.get(BASE, params={"days": 7}, headers=_bearer(token_a)).json()
    assert len(data["dsa"]["solved_trend"]) == 7


def test_dashboard_generated_at_present(client: TestClient, token_a: str):
    """The response stamps when it was generated (UTC)."""
    data = client.get(BASE, headers=_bearer(token_a)).json()
    assert data["generated_at"].endswith(("Z", "+00:00"))
