"""SQLAlchemy model for Transactions table."""

import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class TransactionStatus(str, enum.Enum):
    """Possible statuses of a transaction."""

    SUCCESSFUL = "successful"
    FAILED = "failed"


class TransactionType(str, enum.Enum):
    """Possible types of a transaction."""

    PAYMENT = "payment"
    INVOICE = "invoice"


class Transaction(Base):
    """Represents a financial transaction linked to a user."""

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    status: Mapped[TransactionStatus] = mapped_column(
        Enum(
            TransactionStatus,
            name="transaction_status",
            create_type=False,
            native_enum=False,  # FIX: prevents asyncpg from using its own native enum
                                # codec which encodes by .name ("SUCCESSFUL") instead
                                # of .value ("successful"). With native_enum=False
                                # SQLAlchemy passes values as plain strings via its
                                # own bind_processor where values_callable is respected.
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )

    type: Mapped[TransactionType] = mapped_column(
        Enum(
            TransactionType,
            name="transaction_type",
            create_type=False,
            native_enum=False,  # same fix as above
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )

    paid_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="transactions")  # noqa: F821

    # Composite indexes for common query patterns
    __table_args__ = (
        Index("ix_transactions_paid_at_status", "paid_at", "status"),
        Index("ix_transactions_paid_at_type", "paid_at", "type"),
        Index("ix_transactions_user_status", "user_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<Transaction id={self.id} amount={self.amount} status={self.status}>"