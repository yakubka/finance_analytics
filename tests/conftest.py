"""
Shared pytest fixtures.

Uses an in-memory SQLite database (via aiosqlite) so tests run
without a live PostgreSQL instance.
"""

import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Point to the test SQLite DB before importing app modules
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DATABASE_URL_SYNC", "sqlite:///:memory:")

from app.db.session import Base, get_db
from app.main import app
from app.models.transaction import Transaction, TransactionStatus, TransactionType
from app.models.user import User


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="function")
async def engine():
    """Create a fresh in-memory SQLite engine for each test function."""
    _engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield _engine
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await _engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(engine):
    """Provide a transactional session that is rolled back after each test."""
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def client(engine):
    """
    Return an AsyncClient wired to the FastAPI app with the test DB session.

    The `get_db` dependency is overridden to use the in-memory engine.
    """
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

async def create_user(session: AsyncSession, **kwargs) -> User:
    """Insert a User row and return the persisted object."""
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
    """Insert a Transaction row and return the persisted object."""
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
