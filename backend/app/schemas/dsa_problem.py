from datetime import date, datetime
from typing import List, Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Allowed values mirror the model's declared constraints (see app/models/dsa_problem.py)
DSAPlatform = Literal["LeetCode", "Codeforces", "HackerRank", "NeetCode", "Other"]
DSADifficulty = Literal["Easy", "Medium", "Hard"]


class DSAProblemBase(BaseModel):
    """
    Shared validated fields for create and response payloads.
    Length limits mirror the underlying String(n) columns.
    """

    platform: DSAPlatform = Field(
        ...,
        description="Platform: LeetCode, Codeforces, HackerRank, NeetCode, Other",
    )
    title: str = Field(..., min_length=1, max_length=200)
    problem_url: Optional[str] = Field(None, max_length=500)
    topic: str = Field(..., min_length=1, max_length=100)
    difficulty: DSADifficulty = Field(..., description="Difficulty: Easy, Medium, Hard")
    solved_date: date = Field(default_factory=date.today)
    notes: Optional[str] = None

    @field_validator("title", "topic")
    @classmethod
    def strip_blank_values(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Value cannot be empty or only whitespace")
        return cleaned

    @field_validator("problem_url")
    @classmethod
    def validate_problem_url(cls, v: str | None) -> str | None:
        """Store only http(s) URLs to block javascript:/data: payloads."""
        if v is None:
            return v
        cleaned = v.strip()
        parsed = urlparse(cleaned)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("problem_url must be a valid http:// or https:// URL")
        return cleaned


class DSAProblemCreate(DSAProblemBase):
    """
    Payload for creating a DSA problem. Ownership (user_id) is deliberately
    absent: the server always assigns it from the authenticated user.
    Unknown fields (e.g. a spoofed user_id) are rejected with HTTP 422.
    """

    model_config = ConfigDict(extra="forbid")


class DSAProblemUpdate(BaseModel):
    """
    Payload for partial (PATCH) updates. Every field is optional; omitted
    fields keep their current values. Fields that are NOT NULL in the
    database reject an explicit `null` instead of silently dropping it.
    """

    platform: Optional[DSAPlatform] = None
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    problem_url: Optional[str] = Field(None, max_length=500)
    topic: Optional[str] = Field(None, min_length=1, max_length=100)
    difficulty: Optional[DSADifficulty] = None
    solved_date: Optional[date] = None
    notes: Optional[str] = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("platform", "title", "topic", "difficulty", "solved_date")
    @classmethod
    def reject_null_for_required_fields(cls, v):
        if v is None:
            raise ValueError("This field cannot be set to null")
        return v

    @field_validator("title", "topic")
    @classmethod
    def strip_blank_values(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Value cannot be empty or only whitespace")
        return cleaned

    @field_validator("problem_url")
    @classmethod
    def validate_problem_url(cls, v: str | None) -> str | None:
        """Store only http(s) URLs to block javascript:/data: payloads."""
        if v is None:
            return v
        cleaned = v.strip()
        parsed = urlparse(cleaned)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("problem_url must be a valid http:// or https:// URL")
        return cleaned


class DSAProblemResponse(DSAProblemBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DSAProblemListResponse(BaseModel):
    items: List[DSAProblemResponse]
    total: int
    page: int
    page_size: int
