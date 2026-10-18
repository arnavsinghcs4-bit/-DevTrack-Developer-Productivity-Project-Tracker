from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.project import Milestone, Project
from app.models.user import User
from app.schemas.project import (
    MilestoneCreate,
    MilestoneListResponse,
    MilestoneResponse,
    MilestoneUpdate,
)

# Milestones have no user_id column: ownership is transitive through the
# parent project, so every query joins the projects table and filters on
# Project.user_id == current_user.id.
router = APIRouter(
    prefix="/projects/{project_id}/milestones", tags=["Milestones"]
)

PROJECT_NOT_FOUND_DETAIL = "Project not found"
MILESTONE_NOT_FOUND_DETAIL = "Milestone not found"


def _get_owned_project(db: Session, project_id: int, user_id: int) -> Project | None:
    stmt = select(Project).where(
        Project.id == project_id, Project.user_id == user_id
    )
    return db.execute(stmt).scalar_one_or_none()


def _get_owned_milestone(
    db: Session, project_id: int, milestone_id: int, user_id: int
) -> Milestone | None:
    """
    Load a milestone constrained to (project, owner) in the SQL query itself.
    The join on projects.user_id enforces ownership for this nested resource.
    """
    stmt = (
        select(Milestone)
        .join(Project, Milestone.project_id == Project.id)
        .where(
            Milestone.id == milestone_id,
            Milestone.project_id == project_id,
            Project.user_id == user_id,
        )
    )
    return db.execute(stmt).scalar_one_or_none()


@router.post(
    "",
    response_model=MilestoneResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a milestone under an owned project",
)
def create_milestone(
    project_id: int,
    milestone_in: MilestoneCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Creates a milestone under the project identified by the URL path. The
    parent project must belong to the caller; the project_id is taken from
    the verified path, never from the request body.
    """
    if _get_owned_project(db, project_id, current_user.id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=PROJECT_NOT_FOUND_DETAIL
        )

    db_milestone = Milestone(**milestone_in.model_dump())
    db_milestone.project_id = project_id
    db.add(db_milestone)
    db.commit()
    db.refresh(db_milestone)
    return db_milestone


@router.get(
    "",
    response_model=MilestoneListResponse,
    summary="List milestones of an owned project (paginated)",
)
def list_milestones(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page: int = Query(
        1, ge=1, le=1_000_000, description="1-based page number (max 1,000,000)"
    ),
    page_size: int = Query(
        20, ge=1, le=100, description="Records per page (1-100)"
    ),
):
    """Returns milestones only for a project owned by the caller."""
    if _get_owned_project(db, project_id, current_user.id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=PROJECT_NOT_FOUND_DETAIL
    )

    project_filter = Milestone.project_id == project_id

    total = db.execute(
        select(func.count()).select_from(Milestone).where(project_filter)
    ).scalar_one()

    stmt = (
        select(Milestone)
        .where(project_filter)
        .order_by(Milestone.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = db.execute(stmt).scalars().all()

    return MilestoneListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


@router.get(
    "/{milestone_id}",
    response_model=MilestoneResponse,
    summary="Retrieve one milestone of an owned project",
)
def get_milestone(
    project_id: int,
    milestone_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns 404 for milestones that do not exist, or whose project is foreign."""
    milestone = _get_owned_milestone(db, project_id, milestone_id, current_user.id)
    if milestone is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=MILESTONE_NOT_FOUND_DETAIL
        )
    return milestone


@router.patch(
    "/{milestone_id}",
    response_model=MilestoneResponse,
    summary="Partially update one milestone of an owned project",
)
def update_milestone(
    project_id: int,
    milestone_id: int,
    milestone_in: MilestoneUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Applies only the fields present in the payload; parent stays fixed."""
    milestone = _get_owned_milestone(db, project_id, milestone_id, current_user.id)
    if milestone is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=MILESTONE_NOT_FOUND_DETAIL
        )

    updates = milestone_in.model_dump(exclude_unset=True)
    for field_name, value in updates.items():
        setattr(milestone, field_name, value)

    db.commit()
    db.refresh(milestone)
    return milestone


@router.delete(
    "/{milestone_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete one milestone of an owned project",
)
def delete_milestone(
    project_id: int,
    milestone_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Deletes the milestone only if its project is owned by the caller."""
    milestone = _get_owned_milestone(db, project_id, milestone_id, current_user.id)
    if milestone is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=MILESTONE_NOT_FOUND_DETAIL
        )

    db.delete(milestone)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
