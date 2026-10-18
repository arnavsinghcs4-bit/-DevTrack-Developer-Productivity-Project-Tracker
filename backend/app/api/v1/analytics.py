from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Float, case, cast, func, select
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


def _zero_filled_counts(rows, keys, label) -> list:
    """Builds [{label: key, count: n}, ...] with zeros for absent keys."""
    counts = dict.fromkeys(keys, 0)
    counts.update({row[0]: row[1] for row in rows})
    return [{label: key, "count": count} for key, count in counts.items()]


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

    The `solved_trend` is a dense daily series (missing days are zero-filled)
    across the requested window so chart clients can plot it directly.
    """
    uid = current_user.id
    today = date.today()
    cutoff = today - timedelta(days=days - 1)  # inclusive lower bound

    # ------------------------------------------------------------------
    # DSA problems: totals, breakdowns, distinct active days, daily trend
    # ------------------------------------------------------------------
    owner = DSAProblem.user_id == uid

    dsa_total = db.execute(
        select(func.count()).select_from(DSAProblem).where(owner)
    ).scalar_one()

    active_days = db.execute(
        select(func.count(func.distinct(DSAProblem.solved_date))).where(owner)
    ).scalar_one()

    difficulty_rows = db.execute(
        select(DSAProblem.difficulty, func.count())
        .where(owner)
        .group_by(DSAProblem.difficulty)
    ).all()

    topic_rows = db.execute(
        select(DSAProblem.topic, func.count())
        .where(owner)
        .group_by(DSAProblem.topic)
        .order_by(func.count().desc(), DSAProblem.topic.asc())
        .limit(TOPIC_LIMIT)
    ).all()

    platform_rows = db.execute(
        select(DSAProblem.platform, func.count())
        .where(owner)
        .group_by(DSAProblem.platform)
        .order_by(func.count().desc(), DSAProblem.platform.asc())
    ).all()

    trend_rows = db.execute(
        select(DSAProblem.solved_date, func.count())
        .where(owner, DSAProblem.solved_date >= cutoff)
        .group_by(DSAProblem.solved_date)
    ).all()
    trend_counts = {row[0]: row[1] for row in trend_rows}
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
    goal_owner = Goal.user_id == uid

    goal_total = db.execute(
        select(func.count()).select_from(Goal).where(goal_owner)
    ).scalar_one()

    goal_completed = db.execute(
        select(func.count())
        .select_from(Goal)
        .where(goal_owner, Goal.is_completed.is_(True))
    ).scalar_one()

    goal_type_rows = db.execute(
        select(
            Goal.goal_type,
            func.count(),
            func.coalesce(
                func.sum(case((Goal.is_completed.is_(True), 1), else_=0)), 0
            ),
        )
        .where(goal_owner)
        .group_by(Goal.goal_type)
    ).all()
    goal_type_map = dict.fromkeys(GOAL_TYPES, (0, 0))
    goal_type_map.update({row[0]: (row[1], row[2]) for row in goal_type_rows})

    # AVG(current / target * 100), computed in SQL; target_count > 0 is a
    # defensive filter (the API enforces >= 1, but the column has no CHECK).
    avg_progress = db.execute(
        select(
            func.avg(
                cast(Goal.current_count, Float) / cast(Goal.target_count, Float) * 100
            )
        )
        .where(goal_owner, Goal.target_count > 0)
    ).scalar()

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
    task_owner = Task.user_id == uid

    task_total = db.execute(
        select(func.count()).select_from(Task).where(task_owner)
    ).scalar_one()

    overdue = db.execute(
        select(func.count())
        .select_from(Task)
        .where(
            task_owner,
            Task.due_date.is_not(None),
            Task.due_date < today,
            Task.status != "done",
        )
    ).scalar_one()

    task_status_rows = db.execute(
        select(Task.status, func.count()).where(task_owner).group_by(Task.status)
    ).all()

    task_priority_rows = db.execute(
        select(Task.priority, func.count())
        .where(task_owner)
        .group_by(Task.priority)
    ).all()

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
    project_owner = Project.user_id == uid

    project_total = db.execute(
        select(func.count()).select_from(Project).where(project_owner)
    ).scalar_one()

    project_status_rows = db.execute(
        select(Project.status, func.count())
        .where(project_owner)
        .group_by(Project.status)
    ).all()

    # Each milestone joins to exactly one project, so COUNT(*) counts
    # milestones (not projects); ownership flows through the join.
    milestone_total, milestone_completed = db.execute(
        select(
            func.count(),
            func.coalesce(
                func.sum(case((Milestone.is_completed.is_(True), 1), else_=0)), 0
            ),
        )
        .select_from(Milestone)
        .join(Project, Milestone.project_id == Project.id)
        .where(Project.user_id == uid)
    ).one()

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
    )

    return DashboardResponse(
        generated_at=datetime.now(timezone.utc),
        dsa=dsa,
        goals=goals,
        tasks=tasks,
        projects=projects,
    )
