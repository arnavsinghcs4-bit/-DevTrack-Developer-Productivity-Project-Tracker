from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.project import Project
from app.models.task import Task
from app.models.user import User
from app.schemas.task import (
    TaskCreate,
    TaskListResponse,
    TaskPriority,
    TaskResponse,
    TaskStatus,
    TaskUpdate,
)

router = APIRouter(prefix="/tasks", tags=["Tasks"])

# Uniform messages: a 404 never reveals whether another user's record exists.
TASK_NOT_FOUND_DETAIL = "Task not found"
PROJECT_NOT_FOUND_DETAIL = "Project not found"


def _get_owned_task(db: Session, task_id: int, user_id: int) -> Task | None:
    """
    Load a single task constrained to the owner in the SQL query itself.
    Ownership is enforced by the database layer, never by client-supplied data.
    """
    stmt = select(Task).where(Task.id == task_id, Task.user_id == user_id)
    return db.execute(stmt).scalar_one_or_none()


def _get_owned_project(db: Session, project_id: int, user_id: int) -> Project | None:
    """Verify a referenced project exists AND belongs to the caller."""
    stmt = select(Project).where(
        Project.id == project_id, Project.user_id == user_id
    )
    return db.execute(stmt).scalar_one_or_none()


@router.post(
    "",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a task",
)
def create_task(
    task_in: TaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Creates a task owned by the authenticated user. If a project_id is
    supplied, the project must exist and belong to the caller; otherwise the
    same 404 as a missing project is returned (no existence disclosure).
    """
    payload = task_in.model_dump()

    project_id = payload.get("project_id")
    if project_id is not None:
        if _get_owned_project(db, project_id, current_user.id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=PROJECT_NOT_FOUND_DETAIL,
            )

    db_task = Task(**payload)
    db_task.user_id = current_user.id
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task


@router.get(
    "",
    response_model=TaskListResponse,
    summary="List the authenticated user's tasks (paginated, filterable)",
)
def list_tasks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page: int = Query(
        1, ge=1, le=1_000_000, description="1-based page number (max 1,000,000)"
    ),
    page_size: int = Query(
        20, ge=1, le=100, description="Records per page (1-100)"
    ),
    task_status: Optional[TaskStatus] = Query(
        None, alias="status", description="Filter by status"
    ),
    priority: Optional[TaskPriority] = Query(
        None, description="Filter by priority"
    ),
):
    """
    Returns only the authenticated user's tasks. Optional status/priority
    filters are applied in SQL and served by the (user_id, status, priority)
    composite index.
    """
    filters = [Task.user_id == current_user.id]
    if task_status is not None:
        filters.append(Task.status == task_status)
    if priority is not None:
        filters.append(Task.priority == priority)

    total = db.execute(
        select(func.count()).select_from(Task).where(*filters)
    ).scalar_one()

    stmt = (
        select(Task)
        .where(*filters)
        .order_by(Task.created_at.desc(), Task.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = db.execute(stmt).scalars().all()

    return TaskListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
    summary="Retrieve one of the authenticated user's tasks",
)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns 404 for records that do not exist or belong to another user."""
    task = _get_owned_task(db, task_id, current_user.id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=TASK_NOT_FOUND_DETAIL
        )
    return task


@router.patch(
    "/{task_id}",
    response_model=TaskResponse,
    summary="Partially update one of the authenticated user's tasks",
)
def update_task(
    task_id: int,
    task_in: TaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Applies only the fields present in the payload. A supplied project_id
    must reference an owned project; an explicit null detaches the task.
    The owner cannot be changed: the update schema declares no user_id.
    """
    task = _get_owned_task(db, task_id, current_user.id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=TASK_NOT_FOUND_DETAIL
        )

    updates = task_in.model_dump(exclude_unset=True)

    project_id = updates.get("project_id")
    if project_id is not None:
        if _get_owned_project(db, project_id, current_user.id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=PROJECT_NOT_FOUND_DETAIL,
            )

    for field_name, value in updates.items():
        setattr(task, field_name, value)

    db.commit()
    db.refresh(task)
    return task


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete one of the authenticated user's tasks",
)
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Deletes the task only if it exists AND is owned by the caller."""
    task = _get_owned_task(db, task_id, current_user.id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=TASK_NOT_FOUND_DETAIL
        )

    db.delete(task)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
