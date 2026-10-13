from datetime import datetime
from typing import List, TYPE_CHECKING
from sqlalchemy import String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

if TYPE_CHECKING:
    from app.models.dsa_problem import DSAProblem
    from app.models.goal import Goal
    from app.models.task import Task
    from app.models.project import Project


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
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

    # Relationships with cascade delete (multi-tenant user isolation)
    dsa_problems: Mapped[List["DSAProblem"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    goals: Mapped[List["Goal"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    tasks: Mapped[List["Task"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    projects: Mapped[List["Project"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
