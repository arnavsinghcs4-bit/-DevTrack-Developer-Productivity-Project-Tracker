import pytest
from typing import Generator
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app

# Create completely isolated in-memory SQLite database for testing
# This guarantees that tests NEVER touch or pollute the real Neon database
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine,
)


@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    """
    Creates fresh database tables before each test function
    and tears them down after the test completes.
    """
    Base.metadata.create_all(bind=test_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """
    TestClient fixture that overrides FastAPI's get_db dependency
    to use the isolated in-memory test database session.
    """
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Shared auth fixtures for API endpoint tests
# ---------------------------------------------------------------------------

def register_and_login(
    client: TestClient, email: str, full_name: str = "Test User"
) -> str:
    """Registers a user and returns a valid JWT access token."""
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "StrongPassword123!",
            "full_name": full_name,
        },
    )
    assert reg.status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "StrongPassword123!"},
    )
    assert login.status_code == 200
    return login.json()["access_token"]


@pytest.fixture
def token_a(client: TestClient) -> str:
    """A registered, logged-in user ("alice") for ownership tests."""
    return register_and_login(client, "alice@example.com", "Alice")


@pytest.fixture
def token_b(client: TestClient) -> str:
    """A second independent user ("bob") for cross-user isolation tests."""
    return register_and_login(client, "bob@example.com", "Bob")
