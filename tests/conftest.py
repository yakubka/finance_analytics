"""
Shared pytest fixtures.

Uses a file-based SQLite database (via aiosqlite) instead of :memory: so that
all connections within a single test share the same data.

WHY NOT :memory:?
SQLite creates a completely separate, empty database for every new connection
when the URL is sqlite+aiosqlite:///:memory:. The db_session fixture opens
connection A; the HTTP client inside the `client` fixture opens connection B.
Any rows inserted through session A are invisible to connection B, causing
endpoint tests that insert seed data to see count=0 and fail.

A named file (test_db.sqlite3) is shared by all connections and is deleted
after each test function via the engine fixture's teardown.
"""

import os

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Must be set before any app module is imported so that app/db/session.py
# picks up the test URL when it builds the module-level engine.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_db.sqlite3")
os.environ.setdefault("DATABASE_URL_SYNC", "sqlite:///./test_db.sqlite3")

from app.db.session import Base, get_db
from app.main import app
from app.models.transaction import Transaction, TransactionStatus, TransactionType
from app.models.user import User

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_db.sqlite3"


@pytest_asyncio.fixture(scope="function")
async def engine():
    """
    Create a fresh file-based SQLite engine for each test function.

    The file is created in the current working directory under the name
    test_db.sqlite3 and is removed during teardown so tests are fully
    isolated from one another.
    """
    _engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        echo=False,
    )
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield _engine

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await _engine.dispose()

    # Remove the SQLite file so the next test starts with a clean slate.
    try:
        os.unlink("./test_db.sqlite3")
    except FileNotFoundError:
        pass


@pytest_asyncio.fixture(scope="function")
async def db_session(engine):
    """
    Provide an AsyncSession for direct DB manipulation inside tests.

    Each helper (create_user, create_transaction) commits immediately so
    that the data is visible to other connections (i.e. the HTTP client).
    """
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def client(engine):
    """
    Return an AsyncClient wired to the FastAPI app with the test DB session.

    The get_db dependency is overridden to use the same engine as db_session,
    so both fixtures operate on the same SQLite file and share committed data.
    """
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


async def create_user(session: AsyncSession, **kwargs) -> User:
    """Insert a User row, commit, and return the persisted object."""
    defaults = {
        "first_name": "Alice",
        "last_name": "Smith",
        "email": "alice@example.com",
        "is_active": True,
    }
    defaults.update(kwargs)
    user = User(**defaults)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def create_transaction(session: AsyncSession, user_id: int, **kwargs) -> Transaction:
    """Insert a Transaction row, commit, and return the persisted object."""
    from datetime import datetime, timezone

    defaults = {
        "user_id": user_id,
        "amount": 100.00,
        "status": TransactionStatus.SUCCESSFUL,
        "type": TransactionType.PAYMENT,
        "paid_at": datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
    }
    defaults.update(kwargs)
    tx = Transaction(**defaults)
    session.add(tx)
    await session.commit()
    await session.refresh(tx)
    return tx