"""Shared test setup: the real trained model + a clean database per test.

Every API/database test runs twice: on in-memory SQLite (always) and on PostgreSQL when
TEST_DATABASE_URL is set (in .env). The PostgreSQL test database is wiped before and after each test.
"""
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

from backend.app import config  # noqa: F401  loads .env
from backend.app.database import session

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(params=["sqlite", "postgres"])
def database(request):
    """Point the app at a fresh database and yield its kind."""
    if request.param == "sqlite":
        session.init_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    else:
        url = os.environ.get("TEST_DATABASE_URL")
        if not url:
            pytest.skip("TEST_DATABASE_URL not set")
        session.init_engine(url)
        session.Base.metadata.drop_all(session.engine)
        session.Base.metadata.create_all(session.engine)
    yield request.param
    session.Base.metadata.drop_all(session.engine)
    session.engine.dispose()
    session.engine = None


@pytest.fixture()
def client(database):
    from backend.app.main import app
    from backend.app.utils.rate_limit import HITS
    HITS.clear()
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def sample_csv() -> bytes:
    """44 real CICIDS2017 rows (20 benign + 24 attacks). Taken from the dataset, so possibly seen in training:
    use it to test the plumbing, never to measure accuracy."""
    return (FIXTURES / "sample_flows.csv").read_bytes()
