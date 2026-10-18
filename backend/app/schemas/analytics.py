from datetime import date, datetime
from typing import List

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Analytics response schemas. Counts are zero-filled server-side so clients
# always receive a fixed, chartable shape even when a category has no rows.
# ---------------------------------------------------------------------------

class CountByDifficulty(BaseModel):
    difficulty: str
    count: int


class CountByTopic(BaseModel):
    topic: str
    count: int


class CountByPlatform(BaseModel):
    platform: str
    count: int


class TrendPoint(BaseModel):
    solved_date: date
    count: int


class DsaAnalytics(BaseModel):
    total: int
    active_days: int  # distinct solved_date values, all time
    by_difficulty: List[CountByDifficulty]  # Easy/Medium/Hard, zero-filled
    by_topic: List[CountByTopic]  # top 10 by count
    by_platform: List[CountByPlatform]
    solved_trend: List[TrendPoint]  # dense daily buckets across the window


class CountByGoalType(BaseModel):
    goal_type: str
    total: int
    completed: int


class GoalAnalytics(BaseModel):
    total: int
    completed: int
    completion_rate: float  # percent, 0-100
    avg_progress_percent: float  # SQL AVG(current/target * 100)
    by_type: List[CountByGoalType]  # daily/weekly, zero-filled


class CountByStatus(BaseModel):
    status: str
    count: int


class CountByPriority(BaseModel):
    priority: str
    count: int


class TaskAnalytics(BaseModel):
    total: int
    overdue: int  # past due, not done
    by_status: List[CountByStatus]  # todo/in_progress/done, zero-filled
    by_priority: List[CountByPriority]  # low/medium/high, zero-filled


class ProjectAnalytics(BaseModel):
    total: int
    by_status: List[CountByStatus]  # planning/in_progress/completed, zero-filled
    milestones_total: int
    milestones_completed: int


class DashboardResponse(BaseModel):
    generated_at: datetime
    dsa: DsaAnalytics
    goals: GoalAnalytics
    tasks: TaskAnalytics
    projects: ProjectAnalytics
