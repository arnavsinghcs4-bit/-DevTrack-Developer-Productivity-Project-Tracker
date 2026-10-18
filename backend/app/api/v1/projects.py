from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.project import Project
from app.models.user import User
from app.schemas.project import (
    ProjectCreate,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdate,
)

router = APIRouter(prefix="/projects", tags=["Projects"])

# Identical message whether the record is missing or owned by someone else,
# so a 404 never reveals whether another user's record exists.
NOT_FOUND_DETAIL = "Project not found"


def _get_owned_project(
    db: Session, project_id: int, user_id: int
) -> Project | None:
    """
    Load a single project constrained to the owner in the SQL query itself.
    Ownership is enforced by the database layer, never by client-supplied data.
    """
    stmt = select(Project).where(
        Project.id == project_id, Project.user_id == user_id
    )
    return db.execute(stmt).scalar_one_or_none()


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a project",
)
def create_project(
    project_in: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Creates a project owned by the authenticated user. The owner is always
    taken from the verified JWT identity.
    """
    db_project = Project(**project_in.model_dump())
    db_project.user_id = current_user.id
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    return db_project


@router.get(
    "",
    response_model=ProjectListResponse,
    summary="List the authenticated user's projects (paginated)",
)
def list_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page: int = Query(
        1, ge=1, le=1_000_000, description="1-based page number (max 1,000,000)"
    ),
    page_size: int = Query(
        20, ge=1, le=100, description="Records per page (1-100)"
    ),
):
    """Returns only the authenticated user's projects, filtered in SQL."""
    owner_filter = Project.user_id == current_user.id

    total = db.execute(
        select(func.count()).select_from(Project).where(owner_filter)
    ).scalar_one()

    stmt = (
        select(Project)
        .where(owner_filter)
        .order_by(Project.created_at.desc(), Project.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = db.execute(stmt).scalars().all()

    return ProjectListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Retrieve one of the authenticated user's projects",
)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns 404 for records that do not exist or belong to another user."""
    project = _get_owned_project(db, project_id, current_user.id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL
        )
    return project


@router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Partially update one of the authenticated user's projects",
)
def update_project(
    project_id: int,
    project_in: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Applies only the fields present in the payload (exclude_unset). The
    update schema declares no ownership columns, so the owner cannot change.
    """
    project = _get_owned_project(db, project_id, current_user.id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL
        )

    updates = project_in.model_dump(exclude_unset=True)
    for field_name, value in updates.items():
        setattr(project, field_name, value)

    db.commit()
    db.refresh(project)
    return project


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete one of the authenticated user's projects",
)
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Deletes the project only if it exists AND is owned by the caller.
    Database-level cascades apply: milestones are deleted (ON DELETE CASCADE)
    while tasks survive with project_id set to NULL (ON DELETE SET NULL).
    """
    project = _get_owned_project(db, project_id, current_user.id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL
        )

    db.delete(project)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
