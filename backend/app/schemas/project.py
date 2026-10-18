from datetime import date, datetime
from typing import List, Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Allowed values mirror the model's declared constraints (see app/models/project.py)
ProjectStatus = Literal["planning", "in_progress", "completed"]


def _validate_http_url(v: Optional[str]) -> Optional[str]:
    """Store only http(s) URLs to block javascript:/data: payloads."""
    if v is None:
        return v
    cleaned = v.strip()
    parsed = urlparse(cleaned)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("URL must be a valid http:// or https:// URL")
    return cleaned


class ProjectBase(BaseModel):
    """Shared validated fields for projects."""

    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    tech_stack: Optional[str] = Field(None, max_length=300)
    repo_url: Optional[str] = Field(None, max_length=500)
    demo_url: Optional[str] = Field(None, max_length=500)
    status: ProjectStatus = "in_progress"

    @field_validator("title")
    @classmethod
    def strip_title(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Title cannot be empty or only whitespace")
        return cleaned

    @field_validator("repo_url", "demo_url")
    @classmethod
    def validate_urls(cls, v: Optional[str]) -> Optional[str]:
        return _validate_http_url(v)


class ProjectCreate(ProjectBase):
    """
    Payload for creating a project. Ownership (user_id) is deliberately
    absent: the server always assigns it from the authenticated user, and
    unknown fields are rejected with HTTP 422.
    """

    model_config = ConfigDict(extra="forbid")


class ProjectUpdate(BaseModel):
    """
    Payload for partial (PATCH) updates. Omitted fields keep their current
    values; NOT NULL columns reject an explicit `null`, while nullable
    columns (including URLs) may be cleared with an explicit `null`.
    """

    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    tech_stack: Optional[str] = Field(None, max_length=300)
    repo_url: Optional[str] = Field(None, max_length=500)
    demo_url: Optional[str] = Field(None, max_length=500)
    status: Optional[ProjectStatus] = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("title", "status")
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

    @field_validator("repo_url", "demo_url")
    @classmethod
    def validate_urls(cls, v: Optional[str]) -> Optional[str]:
        return _validate_http_url(v)


class ProjectResponse(ProjectBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProjectListResponse(BaseModel):
    items: List[ProjectResponse]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Milestones are a nested resource: they have no user_id of their own and are
# owned transitively through their parent project (app/models/project.py).
# ---------------------------------------------------------------------------

class MilestoneBase(BaseModel):
    """Shared validated fields for milestones."""

    title: str = Field(..., min_length=1, max_length=200)
    is_completed: bool = False
    due_date: Optional[date] = None

    @field_validator("title")
    @classmethod
    def strip_title(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Title cannot be empty or only whitespace")
        return cleaned


class MilestoneCreate(MilestoneBase):
    """
    Payload for creating a milestone. The parent project comes from the URL
    path (verified as owned); unknown fields are rejected with HTTP 422.
    """

    model_config = ConfigDict(extra="forbid")


class MilestoneUpdate(BaseModel):
    """Payload for partial (PATCH) milestone updates."""

    title: Optional[str] = Field(None, min_length=1, max_length=200)
    is_completed: Optional[bool] = None
    due_date: Optional[date] = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("title", "is_completed")
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


class MilestoneResponse(MilestoneBase):
    # Note: the milestones table has created_at only (no updated_at column)
    id: int
    project_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MilestoneListResponse(BaseModel):
    items: List[MilestoneResponse]
    total: int
    page: int
    page_size: int
