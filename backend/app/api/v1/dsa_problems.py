from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.dsa_problem import DSAProblem
from app.models.user import User
from app.schemas.dsa_problem import (
    DSAProblemCreate,
    DSAProblemListResponse,
    DSAProblemResponse,
    DSAProblemUpdate,
)

router = APIRouter(prefix="/dsa-problems", tags=["DSA Problems"])

# Identical message whether the record is missing or owned by someone else,
# so a 404 never reveals whether another user's record exists.
NOT_FOUND_DETAIL = "DSA problem not found"


def _get_owned_problem(
    db: Session, problem_id: int, user_id: int
) -> DSAProblem | None:
    """
    Load a single DSA problem constrained to the owner in the SQL query itself.
    Ownership is enforced by the database layer, never by client-supplied data.
    """
    stmt = select(DSAProblem).where(
        DSAProblem.id == problem_id,
        DSAProblem.user_id == user_id,
    )
    return db.execute(stmt).scalar_one_or_none()


@router.post(
    "",
    response_model=DSAProblemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a DSA problem record",
)
def create_dsa_problem(
    problem_in: DSAProblemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Creates a DSA problem owned by the authenticated user.
    The owner is always taken from the verified JWT identity; any
    ownership field in the request body is ignored by the schema.
    """
    db_problem = DSAProblem(**problem_in.model_dump())
    db_problem.user_id = current_user.id
    db.add(db_problem)
    db.commit()
    db.refresh(db_problem)
    return db_problem


@router.get(
    "",
    response_model=DSAProblemListResponse,
    summary="List the authenticated user's DSA problems (paginated)",
)
def list_dsa_problems(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page: int = Query(
        1, ge=1, le=1_000_000, description="1-based page number (max 1,000,000)"
    ),
    page_size: int = Query(
        20, ge=1, le=100, description="Records per page (1-100)"
    ),
):
    """
    Returns only the authenticated user's records. The user filter is applied
    in SQL, so another user's rows can never appear in the result set.
    """
    owner_filter = DSAProblem.user_id == current_user.id

    total = db.execute(
        select(func.count()).select_from(DSAProblem).where(owner_filter)
    ).scalar_one()

    stmt = (
        select(DSAProblem)
        .where(owner_filter)
        .order_by(DSAProblem.solved_date.desc(), DSAProblem.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = db.execute(stmt).scalars().all()

    return DSAProblemListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


@router.get(
    "/{problem_id}",
    response_model=DSAProblemResponse,
    summary="Retrieve one of the authenticated user's DSA problems",
)
def get_dsa_problem(
    problem_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns 404 for records that do not exist or belong to another user."""
    problem = _get_owned_problem(db, problem_id, current_user.id)
    if problem is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL
        )
    return problem


@router.patch(
    "/{problem_id}",
    response_model=DSAProblemResponse,
    summary="Partially update one of the authenticated user's DSA problems",
)
def update_dsa_problem(
    problem_id: int,
    problem_in: DSAProblemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Applies only the fields present in the payload (exclude_unset); omitted
    fields keep their current values. The update schema declares no ownership
    columns, so the owner cannot be transferred.
    """
    problem = _get_owned_problem(db, problem_id, current_user.id)
    if problem is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL
        )

    updates = problem_in.model_dump(exclude_unset=True)
    for field_name, value in updates.items():
        setattr(problem, field_name, value)

    db.commit()
    db.refresh(problem)
    return problem


@router.delete(
    "/{problem_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete one of the authenticated user's DSA problems",
)
def delete_dsa_problem(
    problem_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Deletes the record only if it exists AND is owned by the caller."""
    problem = _get_owned_problem(db, problem_id, current_user.id)
    if problem is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL
        )

    db.delete(problem)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
