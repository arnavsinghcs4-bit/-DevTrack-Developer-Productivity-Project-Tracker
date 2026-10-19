from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Float, Select, case, cast, func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.dsa_problem import DSAProblem
from app.models.goal import Goal
from app.models.project import Milestone, Project
from app.models.task import Task
from app.models.user import User
from app.schemas.analytics import (
    CountByDifficulty,
    CountByGoalType,
    CountByPlatform,
    CountByPriority,
    CountByStatus,
    CountByTopic,
    DashboardResponse,
    DsaAnalytics,
    GoalAnalytics,
    ProjectAnalytics,
    ProjectProgress,
    TaskAnalytics,
    TrendPoint,
)

router = APIRouter(prefix="/analytics", tags=["Analytics"])

# Canonical category orders (matching the model's documented constraints).
# Breakdowns are zero-filled in this order so clients always receive a fixed,
# chartable shape even when a category has no rows.
DIFFICULTIES = ("Easy", "Medium", "Hard")
GOAL_TYPES = ("daily", "weekly")
TASK_STATUSES = ("todo", "in_progress", "done")
TASK_PRIORITIES = ("low", "medium", "high")
PROJECT_STATUSES = ("planning", "in_progress", "completed")

TOPIC_LIMIT = 10  # dashboard shows the top N topics by problem count
PROJECT_ITEM_LIMIT = 4  # "recent projects" list on the overview page


def _zero_filled_counts(rows, keys, label) -> list:
    """Builds [{label: key, count: n}, ...] with zeros for absent keys."""
    counts = dict.fromkeys(keys, 0)
    counts.update({row[0]: row[1] for row in rows})
    return [{label: key, "count": count} for key, count in counts.items()]


def build_dashboard_statements(
    user_id: int, today: date, days: int
) -> dict[str, Select]:
    """
    Builds every SELECT the dashboard endpoint executes, keyed by a stable
    name (17 statements, each intended to run exactly once per request).

    This factory exists deliberately (Branch F): the performance test and
    scripts/explain_dashboard.py EXPLAIN the *exact* statements production
    runs — there is no second copy of these queries to drift out of sync.
    Adding a statement here automatically puts it under the perf test's
    query-count, plan, and timing assertions.

    Indexing context (composite indices placed in the initial migration):
    - dsa_problems: (user_id, solved_date), (user_id, topic),
      (user_id, difficulty) — the trend's range filter and the GROUP BYs
      can be answered by walking an index instead of scanning the table.
    - tasks: (user_id, status, priority); goals: (user_id, ...);
      milestones reach ownership through projects (ix_milestones_project_id).
    """
    uid = user_id
    cutoff = today - timedelta(days=days - 1)  # inclusive lower bound

    owner = DSAProblem.user_id == uid
    goal_owner = Goal.user_id == uid
    task_owner = Task.user_id == uid
    project_owner = Project.user_id == uid

    return {
        # ---- DSA problems: totals, breakdowns, distinct days, daily trend
        "dsa_total": select(func.count()).select_from(DSAProblem).where(owner),
        "dsa_active_days": select(func.count(func.distinct(DSAProblem.solved_date))).where(
            owner
        ),
        "dsa_by_difficulty": select(DSAProblem.difficulty, func.count())
        .where(owner)
        .group_by(DSAProblem.difficulty),
        "dsa_by_topic": select(DSAProblem.topic, func.count())
        .where(owner)
        .group_by(DSAProblem.topic)
        .order_by(func.count().desc(), DSAProblem.topic.asc())
        .limit(TOPIC_LIMIT),
        "dsa_by_platform": select(DSAProblem.platform, func.count())
        .where(owner)
        .group_by(DSAProblem.platform)
        .order_by(func.count().desc(), DSAProblem.platform.asc()),
        # Range scan over (user_id, solved_date): only `days` rows are
        # touched, regardless of how large the user's full history is.
        "dsa_trend": select(DSAProblem.solved_date, func.count())
        .where(owner, DSAProblem.solved_date >= cutoff)
        .group_by(DSAProblem.solved_date),
        # ---- Goals: totals, completion rate, SQL AVG of progress percentage
        "goals_total": select(func.count()).select_from(Goal).where(goal_owner),
        "goals_completed": select(func.count())
        .select_from(Goal)
        .where(goal_owner, Goal.is_completed.is_(True)),
        "goals_by_type": select(
            Goal.goal_type,
            func.count(),
            func.coalesce(func.sum(case((Goal.is_completed.is_(True), 1), else_=0)), 0),
        )
        .where(goal_owner)
        .group_by(Goal.goal_type),
        # AVG(current / target * 100), computed in SQL; target_count > 0 is a
        # defensive filter (the API enforces >= 1, but the column has no CHECK).
        "goals_avg_progress": select(
            func.avg(
                cast(Goal.current_count, Float) / cast(Goal.target_count, Float) * 100
            )
        )
        .where(goal_owner, Goal.target_count > 0),
        # ---- Tasks: status/priority breakdowns and overdue count
        "tasks_total": select(func.count()).select_from(Task).where(task_owner),
        "tasks_overdue": select(func.count())
        .select_from(Task)
        .where(
            task_owner,
            Task.due_date.is_not(None),
            Task.due_date < today,
            Task.status != "done",
        ),
        "tasks_by_status": select(Task.status, func.count())
        .where(task_owner)
        .group_by(Task.status),
        "tasks_by_priority": select(Task.priority, func.count())
        .where(task_owner)
        .group_by(Task.priority),
        # ---- Projects and milestones (milestones joined through owned projects)
        "projects_total": select(func.count()).select_from(Project).where(project_owner),
        "projects_by_status": select(Project.status, func.count())
        .where(project_owner)
        .group_by(Project.status),
        # Each milestone joins to exactly one project, so COUNT(*) counts
        # milestones (not projects); ownership flows through the join.
        "milestones_rollup": select(
            func.count(),
            func.coalesce(func.sum(case((Milestone.is_completed.is_(True), 1), else_=0)), 0),
        )
        .select_from(Milestone)
        .join(Project, Milestone.project_id == Project.id)
        .where(Project.user_id == uid),
        # ---- Per-project milestone rollup for the "recent projects" list
        # LEFT JOIN so milestone-less projects still appear with 0/0; the
        # aggregate is computed in SQL, so the limit keeps the row count to
        # PROJECT_ITEM_LIMIT regardless of how many projects the user has.
        "project_progress": select(
            Project.id,
            Project.title,
            Project.status,
            Project.created_at,
            func.count(Milestone.id),
            func.coalesce(
                func.sum(case((Milestone.is_completed.is_(True), 1), else_=0)), 0
            ),
        )
        .select_from(Project)
        .outerjoin(Milestone, Milestone.project_id == Project.id)
        .where(project_owner)
        .group_by(Project.id, Project.title, Project.status, Project.created_at)
        .order_by(Project.created_at.desc(), Project.id.desc())
        .limit(PROJECT_ITEM_LIMIT),
    }


@router.get(
    "/dashboard",
    response_model=DashboardResponse,
    summary="Productivity dashboard metrics (authenticated user only)",
)
def get_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    days: int = Query(
        30, ge=1, le=365, description="Trend window in days (1-365, default 30)"
    ),
):
    """
    Aggregated productivity metrics for the authenticated user, computed with
    real SQL aggregation (GROUP BY, COUNT(DISTINCT), conditional SUM(CASE),
    AVG) rather than Python-side number crunching. Every query is scoped by
    user_id so one account can never observe another's metrics.

    Exactly one statement per entry in build_dashboard_statements runs — the
    performance suite pins that count (N+1 guard) alongside plan and timing
    assertions. The `solved_trend` is a dense daily series (missing days are
    zero-filled) across the requested window so chart clients can plot it
    directly.
    """
    today = date.today()
    stmts = build_dashboard_statements(current_user.id, today, days)

    # ------------------------------------------------------------------
    # DSA problems: totals, breakdowns, distinct active days, daily trend
    # ------------------------------------------------------------------
    dsa_total = db.execute(stmts["dsa_total"]).scalar_one()
    active_days = db.execute(stmts["dsa_active_days"]).scalar_one()
    difficulty_rows = db.execute(stmts["dsa_by_difficulty"]).all()
    topic_rows = db.execute(stmts["dsa_by_topic"]).all()
    platform_rows = db.execute(stmts["dsa_by_platform"]).all()

    trend_rows = db.execute(stmts["dsa_trend"]).all()
    trend_counts = {row[0]: row[1] for row in trend_rows}
    cutoff = today - timedelta(days=days - 1)
    solved_trend = [
        TrendPoint(
            solved_date=cutoff + timedelta(days=i),
            count=trend_counts.get(cutoff + timedelta(days=i), 0),
        )
        for i in range(days)
    ]

    dsa = DsaAnalytics(
        total=dsa_total,
        active_days=active_days,
        by_difficulty=[
            CountByDifficulty(**item)
            for item in _zero_filled_counts(difficulty_rows, DIFFICULTIES, "difficulty")
        ],
        by_topic=[CountByTopic(topic=row[0], count=row[1]) for row in topic_rows],
        by_platform=[
            CountByPlatform(platform=row[0], count=row[1]) for row in platform_rows
        ],
        solved_trend=solved_trend,
    )

    # ------------------------------------------------------------------
    # Goals: totals, completion rate, SQL AVG of progress percentage
    # ------------------------------------------------------------------
    goal_total = db.execute(stmts["goals_total"]).scalar_one()
    goal_completed = db.execute(stmts["goals_completed"]).scalar_one()
    goal_type_rows = db.execute(stmts["goals_by_type"]).all()
    goal_type_map = dict.fromkeys(GOAL_TYPES, (0, 0))
    goal_type_map.update({row[0]: (row[1], row[2]) for row in goal_type_rows})

    avg_progress = db.execute(stmts["goals_avg_progress"]).scalar()

    goals = GoalAnalytics(
        total=goal_total,
        completed=goal_completed,
        completion_rate=round(goal_completed * 100.0 / goal_total, 1)
        if goal_total
        else 0.0,
        avg_progress_percent=round(float(avg_progress or 0.0), 1),
        by_type=[
            CountByGoalType(
                goal_type=goal_type, total=tot, completed=comp
            )
            for goal_type, (tot, comp) in goal_type_map.items()
        ],
    )

    # ------------------------------------------------------------------
    # Tasks: status/priority breakdowns and overdue count
    # ------------------------------------------------------------------
    task_total = db.execute(stmts["tasks_total"]).scalar_one()
    overdue = db.execute(stmts["tasks_overdue"]).scalar_one()
    task_status_rows = db.execute(stmts["tasks_by_status"]).all()
    task_priority_rows = db.execute(stmts["tasks_by_priority"]).all()

    tasks = TaskAnalytics(
        total=task_total,
        overdue=overdue,
        by_status=[
            CountByStatus(**item)
            for item in _zero_filled_counts(task_status_rows, TASK_STATUSES, "status")
        ],
        by_priority=[
            CountByPriority(**item)
            for item in _zero_filled_counts(
                task_priority_rows, TASK_PRIORITIES, "priority"
            )
        ],
    )

    # ------------------------------------------------------------------
    # Projects and milestones (milestones joined through owned projects)
    # ------------------------------------------------------------------
    project_total = db.execute(stmts["projects_total"]).scalar_one()
    project_status_rows = db.execute(stmts["projects_by_status"]).all()
    milestone_total, milestone_completed = db.execute(stmts["milestones_rollup"]).one()
    project_progress_rows = db.execute(stmts["project_progress"]).all()

    projects = ProjectAnalytics(
        total=project_total,
        by_status=[
            CountByStatus(**item)
            for item in _zero_filled_counts(
                project_status_rows, PROJECT_STATUSES, "status"
            )
        ],
        milestones_total=milestone_total,
        milestones_completed=milestone_completed,
        items=[
            ProjectProgress(
                id=row[0],
                title=row[1],
                status=row[2],
                created_at=row[3],
                milestone_total=row[4],
                milestone_completed=row[5],
                # A project with no milestones has no meaningful percentage;
                # report 0.0 rather than inventing progress (or dividing by 0).
                progress_percent=round(row[5] * 100.0 / row[4], 1) if row[4] else 0.0,
            )
            for row in project_progress_rows
        ],
    )

    return DashboardResponse(
        generated_at=datetime.now(timezone.utc),
        dsa=dsa,
        goals=goals,
        tasks=tasks,
        projects=projects,
    )
