"""
Branch F: EXPLAIN-driven performance validation of the dashboard endpoint.

Methodology (deterministic, CI-safe — no flaky micro-benchmarks):
- Seeds a realistic two-user dataset (~5,300 rows total: ~2,000/1,500 DSA
  problems across 730 days, hundreds of goals/tasks, dozens of projects
  with milestones) via Core bulk inserts — no bcrypt, no HTTP login.
- Asserts the exact SQL PRODUCTION statements (imported from
  build_dashboard_statements — zero drift) against SQLite's
  EXPLAIN QUERY PLAN for the one query whose selectivity makes the
  planner's choice unambiguous: the trend's range scan must ride
  idx_dsa_user_solved_date, never a full table scan.
- Pins the per-request statement COUNT (an N+1 guard that fails the moment
  someone adds a per-row query) and uses a generous wall-time ceiling
  (~2s vs ~50ms real) purely as a catastrophic-regression net — timing
  asserts with tight bounds on shared CI runners are how suites become
  flaky, so the strict assertions are structural, not temporal.
- Verifies metrics stay correct AND user-isolated at volume: a perf test
  that doesn't check the numbers is theater.
"""
import random
from datetime import date, timedelta
from time import perf_counter

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, insert, select, text
from sqlalchemy.dialects import sqlite
from sqlalchemy.orm import Session

from app.api.v1.analytics import build_dashboard_statements
from app.core.security import create_access_token
from app.models.dsa_problem import DSAProblem
from app.models.goal import Goal
from app.models.project import Milestone, Project
from app.models.task import Task
from app.models.user import User

# Wall-time ceiling per dashboard request. Real runtime against the seeded
# in-memory dataset is ~30-80ms; the ~30x headroom absorbs slow CI runners
# while still catching accidental O(N^2) or per-row query regressions.
WALL_TIME_CEILING_SECONDS = 2.0

# The five business tables: any statement touching one of these is a
# dashboard query (the JWT user-lookup on `users` is deliberately excluded
# from the N+1 count).
BUSINESS_TABLES = ("dsa_problems", "goals", "tasks", "projects", "milestones")

TOPICS = [
    "Arrays", "Strings", "Hash Map", "Two Pointers", "Sliding Window", "Stack",
    "Linked List", "Trees", "Graphs", "Dynamic Programming", "Greedy", "Binary Search",
]
PLATFORMS = ["LeetCode", "Codeforces", "HackerRank", "NeetCode", "Other"]
DIFFICULTIES = ["Easy", "Medium", "Hard"]
GOAL_TYPES = ["daily", "weekly"]
TASK_STATUSES = ["todo", "in_progress", "done"]
TASK_PRIORITIES = ["low", "medium", "high"]
PROJECT_STATUSES = ["planning", "in_progress", "completed"]


def _seed_user(db: Session, user_id: int, rng: random.Random, volumes: dict) -> dict:
    """
    Bulk-inserts a realistic year-ish of activity for one user and returns
    independently-computed expectations (from the in-memory seed data, not
    from SQL) so correctness assertions never re-derive with the same query
    shape they are validating.
    """
    today = date.today()

    solved_dates = [
        today - timedelta(days=rng.randrange(0, 730)) for _ in range(volumes["problems"])
    ]
    db.execute(
        insert(DSAProblem),
        [
            {
                "user_id": user_id,
                "title": f"Problem {i}",
                "platform": rng.choice(PLATFORMS),
                "topic": rng.choice(TOPICS),
                "difficulty": rng.choice(DIFFICULTIES),
                "solved_date": solved_dates[i],
            }
            for i in range(volumes["problems"])
        ],
    )

    goal_rows = []
    for i in range(volumes["goals"]):
        target = rng.randint(1, 10)
        goal_rows.append(
            {
                "user_id": user_id,
                "title": f"Goal {i}",
                "goal_type": rng.choice(GOAL_TYPES),
                "target_count": target,
                "current_count": rng.randint(0, target),
                "start_date": today - timedelta(days=rng.randrange(0, 90)),
                "is_completed": rng.random() < 0.6,
            }
        )
    db.execute(insert(Goal), goal_rows)

    task_rows = []
    overdue_expected = 0
    for i in range(volumes["tasks"]):
        status = rng.choice(TASK_STATUSES)
        if rng.random() < 0.15:
            due_date = today - timedelta(days=rng.randint(1, 60))
            if status != "done":
                overdue_expected += 1
        elif rng.random() < 0.7:
            # Strictly future due dates: the "overdue" expectation is derived
            # purely from the 15% branch above, with no accidental overlap
            due_date = today + timedelta(days=rng.randint(1, 30))
        else:
            due_date = None
        task_rows.append(
            {
                "user_id": user_id,
                "title": f"Task {i}",
                "status": status,
                "priority": rng.choice(TASK_PRIORITIES),
                "due_date": due_date,
            }
        )
    db.execute(insert(Task), task_rows)

    db.execute(
        insert(Project),
        [
            {
                "user_id": user_id,
                "title": f"Project {i}",
                "status": rng.choice(PROJECT_STATUSES),
            }
            for i in range(volumes["projects"])
        ],
    )
    project_ids = [
        row[0]
        for row in db.execute(
            select(Project.id).where(Project.user_id == user_id)
        ).all()
    ]
    milestone_rows = []
    for project_id in project_ids:
        for j in range(volumes["milestones_per_project"]):
            milestone_rows.append(
                {
                    "project_id": project_id,
                    "title": f"Milestone {project_id}-{j}",
                    "is_completed": rng.random() < 0.5,
                }
            )
    db.execute(insert(Milestone), milestone_rows)

    window_start = today - timedelta(days=29)
    return {
        "problems": volumes["problems"],
        "overdue": overdue_expected,
        "trend_window_30d": sum(1 for d in solved_dates if d >= window_start),
    }


@pytest.fixture
def seeded_dashboard(client: TestClient, db_session: Session) -> dict:
    """
    Two users with comparable volumes (so neither dominates the tables and
    index-vs-scan planner behavior stays honest), seeded deterministically.
    """
    rng = random.Random(42)
    db_session.execute(
        insert(User),
        [
            {"id": 1, "email": "heavy@example.com", "hashed_password": "seed-hash-a", "full_name": "Heavy User"},
            {"id": 2, "email": "medium@example.com", "hashed_password": "seed-hash-b", "full_name": "Medium User"},
        ],
    )
    expected_a = _seed_user(
        db_session, 1, rng,
        {"problems": 2000, "goals": 200, "tasks": 600, "projects": 40, "milestones_per_project": 4},
    )
    expected_b = _seed_user(
        db_session, 2, rng,
        {"problems": 1500, "goals": 120, "tasks": 400, "projects": 25, "milestones_per_project": 4},
    )
    db_session.commit()

    return {
        "client": client,
        "db": db_session,
        "headers_a": {"Authorization": f"Bearer {create_access_token(subject='1')}"},
        "headers_b": {"Authorization": f"Bearer {create_access_token(subject='2')}"},
        "expected_a": expected_a,
        "expected_b": expected_b,
    }


def _query_plan(db: Session, stmt) -> str:
    """Renders SQLite's EXPLAIN QUERY PLAN for a statement as one string."""
    compiled = stmt.compile(
        dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}
    )
    rows = db.execute(text(f"EXPLAIN QUERY PLAN {compiled}")).all()
    return "\n".join(str(row[-1]) for row in rows)


# ---------------------------------------------------------------------------
# Structural assertions (deterministic)
# ---------------------------------------------------------------------------


def test_exactly_one_statement_per_builder_entry(seeded_dashboard: dict):
    """N+1 guard: the endpoint runs each dashboard statement exactly once."""
    client = seeded_dashboard["client"]
    db = seeded_dashboard["db"]
    statements = build_dashboard_statements(1, date.today(), 30)

    executed = []

    def _record(conn, cursor, statement, parameters, context, executemany):
        executed.append(statement)

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", _record)
    try:
        res = client.get("/api/v1/analytics/dashboard", headers=seeded_dashboard["headers_a"])
    finally:
        event.remove(engine, "before_cursor_execute", _record)

    assert res.status_code == 200
    dashboard_statements = [
        s for s in executed if any(table in s for table in BUSINESS_TABLES)
    ]
    assert len(dashboard_statements) == len(statements), (
        f"Expected exactly {len(statements)} business queries "
        f"(one per build_dashboard_statements entry), got "
        f"{len(dashboard_statements)} — a per-row or duplicated query slipped in"
    )


def test_trend_range_scan_uses_composite_index(seeded_dashboard: dict):
    """
    The trend query is the only one whose predicate has real selectivity
    (user_id equality + a ~4% date window over 730 days of history), so the
    planner's choice is not ambiguous: it MUST ride
    idx_dsa_user_solved_date and never scan the table. Other dashboard
    predicates are near-50% selective, where a full scan is a legitimate
    planner choice at these volumes — asserting a plan there would pin a
    decision, not a property, so we deliberately don't.
    """
    db = seeded_dashboard["db"]
    stmts = build_dashboard_statements(1, date.today(), 30)
    plan = _query_plan(db, stmts["dsa_trend"])
    assert "idx_dsa_user_solved_date" in plan, f"trend missed its index:\n{plan}"
    assert "SCAN dsa_problems" not in plan, f"trend fell back to a full scan:\n{plan}"


# ---------------------------------------------------------------------------
# Correctness and isolation at volume
# ---------------------------------------------------------------------------


def test_metrics_correct_and_isolated_at_volume(seeded_dashboard: dict):
    """Numbers must survive the refactor AND the row count: totals and the
    dense trend are checked against independently-computed seed expectations,
    and the second user's dashboard proves user scoping at scale."""
    client = seeded_dashboard["client"]

    res_a = client.get("/api/v1/analytics/dashboard", headers=seeded_dashboard["headers_a"])
    assert res_a.status_code == 200
    body_a = res_a.json()
    assert body_a["dsa"]["total"] == seeded_dashboard["expected_a"]["problems"]
    assert body_a["tasks"]["overdue"] == seeded_dashboard["expected_a"]["overdue"]
    assert len(body_a["dsa"]["solved_trend"]) == 30
    assert sum(p["count"] for p in body_a["dsa"]["solved_trend"]) == (
        seeded_dashboard["expected_a"]["trend_window_30d"]
    )
    # Zero-fill shape: every breakdown has the full canonical category set
    assert [c["difficulty"] for c in body_a["dsa"]["by_difficulty"]] == ["Easy", "Medium", "Hard"]

    res_b = client.get("/api/v1/analytics/dashboard", headers=seeded_dashboard["headers_b"])
    body_b = res_b.json()
    assert body_b["dsa"]["total"] == seeded_dashboard["expected_b"]["problems"]
    assert body_b["dsa"]["total"] != body_a["dsa"]["total"]  # scoping visible


# ---------------------------------------------------------------------------
# Timing net (catastrophic-regression only — see module docstring)
# ---------------------------------------------------------------------------


def test_dashboard_wall_time_at_volume(seeded_dashboard: dict):
    client = seeded_dashboard["client"]
    headers = seeded_dashboard["headers_a"]

    # Warm-up: first request pays one-time statement compilation costs
    assert client.get("/api/v1/analytics/dashboard", headers=headers).status_code == 200

    for days in (30, 365):
        started = perf_counter()
        res = client.get(f"/api/v1/analytics/dashboard?days={days}", headers=headers)
        elapsed = perf_counter() - started
        assert res.status_code == 200
        assert elapsed < WALL_TIME_CEILING_SECONDS, (
            f"dashboard?days={days} took {elapsed:.3f}s over the seeded volume "
            f"(ceiling {WALL_TIME_CEILING_SECONDS}s) — likely a scan or N+1 regression"
        )
