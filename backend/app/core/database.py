from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from app.core.config import settings

# In SQLAlchemy 2.0, create_engine handles connection pooling
engine = create_engine(
    settings.SQLALCHEMY_DATABASE_URI,
    echo=False,  # Set to True if query debugging is needed
    pool_pre_ping=True,  # Automatically check if connection is alive before using
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a database session for each request
    and guarantees it is closed when the request finishes.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
