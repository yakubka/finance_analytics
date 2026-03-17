"""SQLAlchemy model for Users table."""

from datetime import datetime

from sqlalchemy import DateTime, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class User(Base):
    """Represents an application user."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    # FIXED: was `default=True` (Python-side ORM default only).
    # The migration already installs a PostgreSQL server_default of "true",
    # so the model must declare server_default as well to stay consistent.
    # With only a Python-side default, rows inserted via raw SQL (e.g. seed
    # scripts or manual psql) would have no DB-level default to fall back on.
    is_active: Mapped[bool] = mapped_column(
        server_default=text("true"),
        nullable=False,
    )

    # Relationships
    transactions: Mapped[list["Transaction"]] = relationship(  # noqa: F821
        "Transaction", back_populates="user", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"
