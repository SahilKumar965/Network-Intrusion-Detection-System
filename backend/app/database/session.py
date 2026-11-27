"""SQLAlchemy engine and per-request session. All queries go through the ORM, so they are parameterized."""
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


engine = None
SessionLocal = sessionmaker(autoflush=False, expire_on_commit=False)


def init_engine(url: str, **kwargs) -> None:
    """Create the engine and tables. Called once at startup (tests pass their own URL)."""
    global engine
    if not url:
        raise RuntimeError("DATABASE_URL is not set (see .env.example)")
    engine = create_engine(url, pool_pre_ping=True, **kwargs)
    SessionLocal.configure(bind=engine)
    from backend.app.models import db_models  # noqa: F401  registers the tables on Base
    # shortcut: create_all instead of Alembic migrations; add Alembic when the schema starts changing.
    Base.metadata.create_all(engine)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
