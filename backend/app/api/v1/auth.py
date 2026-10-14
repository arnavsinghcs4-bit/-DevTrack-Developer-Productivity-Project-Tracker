from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user
from app.core.security import get_password_hash, verify_password, create_access_token
from app.models.user import User
from app.schemas.user import UserCreate, UserLogin, UserResponse, Token

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new developer account",
)
def register(
    user_in: UserCreate,
    db: Session = Depends(get_db),
):
    """
    Registers a new user with an email, password, and full name.
    - Enforces email normalization and uniqueness.
    - Hashes password using bcrypt.
    - Never returns hashed_password in the response.
    """
    # 1. Check if user already exists
    stmt = select(User).where(User.email == user_in.email)
    existing_user = db.execute(stmt).scalar_one_or_none()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    # 2. Hash password with bcrypt
    hashed_password = get_password_hash(user_in.password)

    # 3. Create user record
    new_user = User(
        email=user_in.email,
        hashed_password=hashed_password,
        full_name=user_in.full_name,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


@router.post(
    "/login",
    response_model=Token,
    summary="Authenticate and obtain JWT access token",
)
def login(
    user_in: UserLogin,
    db: Session = Depends(get_db),
):
    """
    Authenticates user credentials and returns a signed JWT bearer access token.
    Returns generic 401 error on invalid email or password to prevent user enumeration.
    """
    stmt = select(User).where(User.email == user_in.email)
    user = db.execute(stmt).scalar_one_or_none()

    if not user or not verify_password(user_in.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Generate JWT access token with user.id as subject
    access_token = create_access_token(subject=str(user.id))
    return Token(access_token=access_token, token_type="bearer")


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current authenticated user profile",
)
def read_current_user(
    current_user: User = Depends(get_current_user),
):
    """
    Returns the currently authenticated user's profile information.
    Protected endpoint requiring a valid Bearer token.
    """
    return current_user
