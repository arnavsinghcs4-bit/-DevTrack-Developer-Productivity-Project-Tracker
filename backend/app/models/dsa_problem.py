from datetime import date, datetime
from typing import TYPE_CHECKING
from sqlalchemy import String, Text, Date, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class DSAProblem(Base):
    __tablename__ = "dsa_problems"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    platform: Mapped[str] = mapped_column(String(50), nullable=False)  # LeetCode, Codeforces, HackerRank, NeetCode, Other
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    problem_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    topic: Mapped[str] = mapped_column(String(100), index=True, nullable=False)  # Arrays, DP, Graphs, Trees, etc.
    difficulty: Mapped[str] = mapped_column(String(20), index=True, nullable=False)  # Easy, Medium, Hard
    solved_date: Mapped[date] = mapped_column(Date, index=True, default=date.today, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="dsa_problems")

    # Composite index for optimized user-level analytics queries
    __table_args__ = (
        Index("idx_dsa_user_topic", "user_id", "topic"),
        Index("idx_dsa_user_difficulty", "user_id", "difficulty"),
        Index("idx_dsa_user_solved_date", "user_id", "solved_date"),
    )
