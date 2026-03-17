"""initial schema: users and transactions

Revision ID: 0001_initial
Revises:
Create Date: 2024-01-01 00:00:00.000000

ENUM fix note
─────────────
The original code set create_type=False on the module-level ENUM objects and
then called .create(bind, checkfirst=True) manually *before* op.create_table.
That worked for the first SQL statement, but Alembic's op.create_table()
internally copies every column type via sqlalchemy Column.copy().
postgresql.ENUM.copy() does NOT forward create_type=False to the constructor,
so the copy gets the default create_type=True.  When op.create_table fires the
before_create event, _on_table_create runs on that copy and issues a second
CREATE TYPE … without IF NOT EXISTS → DuplicateObjectError.

Fix: remove create_type=False and remove the manual .create() calls entirely.
     SQLAlchemy's _on_table_create fires exactly once when op.create_table
     ("transactions", …) is executed, creating both ENUMs idempotently inside
     the Alembic transaction.  If the migration is rolled back, PostgreSQL
     reverts the CREATE TYPE as well, so re-runs always start clean.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ── ENUM type objects ──────────────────────────────────────────────────────
# create_type is intentionally left at its default (True).
# _on_table_create will create each type exactly once when the "transactions"
# table is first built.  Do NOT call .create() manually before op.create_table;
# that is what caused the DuplicateObjectError in the original migration.
transaction_status_enum = postgresql.ENUM(
    "successful",
    "failed",
    name="transaction_status",
)

transaction_type_enum = postgresql.ENUM(
    "payment",
    "invoice",
    name="transaction_type",
)


def upgrade() -> None:
    # ── users ──────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_id", "users", ["id"], unique=False)
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # ── transactions ───────────────────────────────────────────────────────
    # _on_table_create fires here and issues both CREATE TYPE statements once.
    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("status", transaction_status_enum, nullable=False),
        sa.Column("type", transaction_type_enum, nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_transactions_id", "transactions", ["id"], unique=False)
    op.create_index(
        "ix_transactions_user_id", "transactions", ["user_id"], unique=False
    )
    op.create_index(
        "ix_transactions_status", "transactions", ["status"], unique=False
    )
    op.create_index(
        "ix_transactions_type", "transactions", ["type"], unique=False
    )
    op.create_index(
        "ix_transactions_paid_at", "transactions", ["paid_at"], unique=False
    )
    # Composite indexes for common analytical query patterns
    op.create_index(
        "ix_transactions_paid_at_status",
        "transactions",
        ["paid_at", "status"],
        unique=False,
    )
    op.create_index(
        "ix_transactions_paid_at_type",
        "transactions",
        ["paid_at", "type"],
        unique=False,
    )
    op.create_index(
        "ix_transactions_user_status",
        "transactions",
        ["user_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    # Drop tables first; _on_table_drop will attempt to drop the ENUM types.
    op.drop_table("transactions")
    op.drop_table("users")

    # Explicit drops with checkfirst=True act as a safety net: if
    # _on_table_drop already removed the types, these become no-ops.
    bind = op.get_bind()
    transaction_status_enum.drop(bind, checkfirst=True)
    transaction_type_enum.drop(bind, checkfirst=True)
