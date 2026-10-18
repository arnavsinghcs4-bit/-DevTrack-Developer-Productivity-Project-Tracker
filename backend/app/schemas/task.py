from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Allowed values mirror the model's declared constraints (see app/models/task.py)
TaskStatus = Literal["todo", "in_progress", "done"]
TaskPriority = Literal["low", "medium", "high"]


class TaskBase(BaseModel):
    """
    Shared validated fields for tasks. `project_id` is optional; when present
    the endpoint verifies the project belongs to the authenticated user.
    """

    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    status: TaskStatus = "todo"
    priority: TaskPriority = "medium"
    due_date: Optional[date] = None
    project_id: Optional[int] = Field(None, ge=1)

    @field_validator("title")
    @classmethod
    def strip_title(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Title cannot be empty or only whitespace")
        return cleaned


class TaskCreate(TaskBase):
    """
    Payload for creating a task. Ownership (user_id) is deliberately absent:
    the server always assigns it from the authenticated user, and unknown
    fields are rejected with HTTP 422.
    """

    model_config = ConfigDict(extra="forbid")


class TaskUpdate(BaseModel):
    """
    Payload for partial (PATCH) updates. Omitted fields keep their current
    values; NOT NULL columns reject an explicit `null`. An explicit
    `project_id: null` detaches the task from its project (matching the
    database's ON DELETE SET NULL semantics).
    """

    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    due_date: Optional[date] = None
    project_id: Optional[int] = Field(None, ge=1)

    model_config = ConfigDict(extra="forbid")

    @field_validator("title", "status", "priority")
    @classmethod
    def reject_null_for_required_fields(cls, v):
        if v is None:
            raise ValueError("This field cannot be set to null")
        return v

    @field_validator("title")
    @classmethod
    def strip_title(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Title cannot be empty or only whitespace")
        return cleaned


class TaskResponse(TaskBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskListResponse(BaseModel):
    items: List[TaskResponse]
    total: int
    page: int
    page_size: int
