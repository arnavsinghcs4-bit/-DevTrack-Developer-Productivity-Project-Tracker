from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.goal import Goal
from app.models.user import User
from app.schemas.goal import (
    GoalCreate,
    GoalListResponse,
    GoalResponse,
    GoalUpdate,
)

router = APIRouter(prefix="/goals", tags=["Goals"])

# Identical message whether the record is missing or owned by someone else,
# so a 404 never reveals whether another user's record exists.
NOT_FOUND_DETAIL = "Goal not found"


def _get_owned_goal(db: Session, goal_id: int, user_id: int) -> Goal | None:
    """
    Load a single goal constrained to the owner in the SQL query itself.
    Ownership is enforced by the database layer, never by client-supplied data.
    """
    stmt = select(Goal).where(Goal.id == goal_id, Goal.user_id == user_id)
    return db.execute(stmt).scalar_one_or_none()


@router.post(
    "",
    response_model=GoalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a goal",
)
def create_goal(
    goal_in: GoalCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Creates a goal owned by the authenticated user. The owner is always
    taken from the verified JWT identity; the start/end date range is
    validated by the schema.
    """
    db_goal = Goal(**goal_in.model_dump())
    db_goal.user_id = current_user.id
    db.add(db_goal)
    db.commit()
    db.refresh(db_goal)
    return db_goal


@router.get(
    "",
    response_model=GoalListResponse,
    summary="List the authenticated user's goals (paginated)",
)
def list_goals(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page: int = Query(
        1, ge=1, le=1_000_000, description="1-based page number (max 1,000,000)"
    ),
    page_size: int = Query(
        20, ge=1, le=100, description="Records per page (1-100)"
    ),
):
    """Returns only the authenticated user's goals, filtered in SQL."""
    owner_filter = Goal.user_id == current_user.id

    total = db.execute(
        select(func.count()).select_from(Goal).where(owner_filter)
    ).scalar_one()

    stmt = (
        select(Goal)
        .where(owner_filter)
        .order_by(Goal.start_date.desc(), Goal.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = db.execute(stmt).scalars().all()

    return GoalListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get(
    "/{goal_id}",
    response_model=GoalResponse,
    summary="Retrieve one of the authenticated user's goals",
)
def get_goal(
    goal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns 404 for records that do not exist or belong to another user."""
    goal = _get_owned_goal(db, goal_id, current_user.id)
    if goal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL
        )
    return goal


@router.patch(
    "/{goal_id}",
    response_model=GoalResponse,
    summary="Partially update one of the authenticated user's goals",
)
def update_goal(
    goal_id: int,
    goal_in: GoalUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Applies only the fields present in the payload (exclude_unset). After
    applying, the combined stored date range is re-validated so a PATCH
    cannot leave end_date before start_date.
    """
    goal = _get_owned_goal(db, goal_id, current_user.id)
    if goal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL
        )

    updates = goal_in.model_dump(exclude_unset=True)
    for field_name, value in updates.items():
        setattr(goal, field_name, value)

    # Re-check the resulting state (not just the payload): either date may
    # have been changed independently. No commit has happened yet, so the
    # transaction is still rolled back when the session closes.
    if goal.end_date is not None and goal.end_date < goal.start_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="end_date cannot be before start_date",
        )

    db.commit()
    db.refresh(goal)
    return goal


@router.delete(
    "/{goal_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete one of the authenticated user's goals",
)
def delete_goal(
    goal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Deletes the goal only if it exists AND is owned by the caller."""
    goal = _get_owned_goal(db, goal_id, current_user.id)
    if goal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL
        )

    db.delete(goal)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
