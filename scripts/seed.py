"""
Seed script: generates ≥100 users and ≥10,000 transactions.

Run inside the container:
    python scripts/seed.py

Or via docker-compose:
    docker-compose exec app python scripts/seed.py
"""

import asyncio
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
# Make sure the app package is importable when running from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from faker import Faker
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.transaction import Transaction, TransactionStatus, TransactionType
from app.models.user import User

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@db:5432/analytics",
)

NUM_USERS = 120
NUM_TRANSACTIONS = 12_000

# Use enum members directly — never .value strings.
# With native_enum=False + values_callable, SQLAlchemy maps enum members to
# their .value for storage. Passing raw strings bypasses this mapping and can
# cause silent type mismatches or future regressions if enum values change.
STATUSES = [TransactionStatus.SUCCESSFUL, TransactionStatus.FAILED]
TYPES = [TransactionType.PAYMENT, TransactionType.INVOICE]

fake = Faker()
rng = random.Random(42)  # deterministic seed for reproducibility


def _random_dt_last_2_years() -> datetime:
    """Return a random timezone-aware datetime within the last 2 years."""
    now = datetime.now(tz=timezone.utc)
    days_back = rng.randint(0, 730)
    seconds_back = rng.randint(0, 86_400)
    return now - timedelta(days=days_back, seconds=seconds_back)


def _generate_users(n: int) -> list[dict]:
    """Generate n unique user records."""
    seen_emails: set[str] = set()
    users: list[dict] = []
    while len(users) < n:
        email = fake.unique.email()
        if email in seen_emails:
            continue
        seen_emails.add(email)
        users.append(
            {
                "first_name": fake.first_name(),
                "last_name": fake.last_name(),
                "email": email,
                "registered_at": _random_dt_last_2_years(),
                "is_active": rng.random() > 0.05,  # 95 % active
            }
        )
    return users


def _generate_transactions(user_ids: list[int], n: int) -> list[dict]:
    """
    Generate n transaction records distributed across user_ids.

    Distribution:
      - Statuses: ~60 % successful, ~40 % failed
      - Types:    ~55 % payment,    ~45 % invoice

    NOTE: status and type are stored as enum *members* (not .value strings).
    SQLAlchemy's bind_processor (via values_callable) converts them to the
    correct string value at query time.
    """
    transactions: list[dict] = []
    for _ in range(n):
        # Pass enum members, not status.value — keeps typing consistent with
        # the Mapped[TransactionStatus] / Mapped[TransactionType] annotations.
        status: TransactionStatus = rng.choices(STATUSES, weights=[60, 40])[0]
        tx_type: TransactionType = rng.choices(TYPES, weights=[55, 45])[0]
        amount = Decimal(str(round(rng.uniform(1.0, 1000.0), 2)))
        transactions.append(
            {
                "user_id": rng.choice(user_ids),
                "amount": amount,
                "status": status,           # enum member, NOT status.value
                "type": tx_type,            # enum member, NOT tx_type.value
                "paid_at": _random_dt_last_2_years(),
                "description": (
                    fake.sentence(nb_words=6) if rng.random() > 0.4 else None
                ),
            }
        )
    return transactions


async def seed() -> None:
    """Drop existing data and populate with fresh mock records."""
    engine = create_async_engine(DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_factory() as session:
        # Clear existing data to allow repeated seeding
        await session.execute(
            text("TRUNCATE TABLE transactions RESTART IDENTITY CASCADE")
        )
        await session.execute(
            text("TRUNCATE TABLE users RESTART IDENTITY CASCADE")
        )
        await session.commit()
        print("Cleared existing data.")

        # --- Users ---
        user_dicts = _generate_users(NUM_USERS)
        user_objects = [User(**u) for u in user_dicts]
        session.add_all(user_objects)
        await session.flush()  # populate auto-generated IDs
        user_ids = [u.id for u in user_objects]
        await session.commit()
        print(f"Inserted {len(user_ids)} users.")

        # --- Transactions (batched to keep memory low) ---
        tx_dicts = _generate_transactions(user_ids, NUM_TRANSACTIONS)
        batch_size = 1_000
        total_inserted = 0

        for i in range(0, len(tx_dicts), batch_size):
            batch = tx_dicts[i : i + batch_size]
            session.add_all([Transaction(**t) for t in batch])
            await session.commit()
            total_inserted += len(batch)
            print(
                f"  Transactions inserted: {total_inserted}/{NUM_TRANSACTIONS}",
                end="\r",
            )

        print(f"\nInserted {total_inserted} transactions. Seeding complete. ✓")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())