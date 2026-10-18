from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Allowed values mirror the model's declared constraints (see app/models/goal.py)
GoalType = Literal["daily", "weekly"]


class GoalBase(BaseModel):
    """
    Shared validated fields for goals. Length limits mirror the underlying
    String(n) columns; count constraints keep progress metrics meaningful.
    """

    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    goal_type: GoalType = Field(..., description="Goal cadence: daily or weekly")
    target_count: int = Field(1, ge=1)
    current_count: int = Field(0, ge=0)
    start_date: date = Field(default_factory=date.today)
    end_date: Optional[date] = None
    is_completed: bool = False

    @field_validator("title")
    @classmethod
    def strip_title(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Title cannot be empty or only whitespace")
        return cleaned

    @model_validator(mode="after")
    def validate_date_range(self) -> "GoalBase":
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")
        return self


class GoalCreate(GoalBase):
    """
    Payload for creating a goal. Ownership (user_id) is deliberately absent:
    the server always assigns it from the authenticated user, and unknown
    fields are rejected with HTTP 422.
    """

    model_config = ConfigDict(extra="forbid")


class GoalUpdate(BaseModel):
    """
    Payload for partial (PATCH) updates. Omitted fields keep their current
    values; NOT NULL columns reject an explicit `null`. The combined
    start/end date range is re-checked against stored values by the endpoint.
    """

    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    goal_type: Optional[GoalType] = None
    target_count: Optional[int] = Field(None, ge=1)
    current_count: Optional[int] = Field(None, ge=0)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_completed: Optional[bool] = None

    model_config = ConfigDict(extra="forbid")

    @field_validator(
        "title", "goal_type", "target_count", "current_count", "start_date", "is_completed"
    )
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


class GoalResponse(GoalBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GoalListResponse(BaseModel):
    items: List[GoalResponse]
    total: int
    page: int
    page_size: int
