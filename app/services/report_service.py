"""Business logic for report generation and analytics."""

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Transaction, TransactionStatus, TransactionType
from app.schemas.report import DailyEntry, ReportResponse


class ReportService:
    """Handles analytics queries over the transactions table."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_report(
        self,
        start_date: date,
        end_date: date,
        status: str,
        tx_type: str,
        include_avg: bool,
        include_min: bool,
        include_max: bool,
        include_daily_shift: bool,
    ) -> ReportResponse:
        """
        Compute aggregated metrics for the given filters.

        Monetary metrics (avg, min, max, total) are computed only over
        successful transactions. ``count`` reflects all matched transactions.

        ``Transaction.amount`` is a ``Numeric(10, 2)`` column; PostgreSQL
        returns ``Decimal`` values.  These are rounded and cast to ``float``
        only at the response boundary so that precision is preserved throughout
        the computation.
        """
        start_dt = datetime(
            start_date.year, start_date.month, start_date.day, tzinfo=timezone.utc
        )
        end_dt = datetime(
            end_date.year, end_date.month, end_date.day, 23, 59, 59, tzinfo=timezone.utc
        )

        # CASE expression keeps the single-query approach: SUM/AVG/MIN/MAX
        # operate only on successful rows while COUNT covers all matched rows.
        successful_amount = case(
            (Transaction.status == TransactionStatus.SUCCESSFUL, Transaction.amount),
            else_=None,
        )

        agg_stmt = select(
            func.count(Transaction.id).label("count"),
            func.coalesce(func.sum(successful_amount), 0).label("total"),
            func.avg(successful_amount).label("avg"),
            func.min(successful_amount).label("min"),
            func.max(successful_amount).label("max"),
        ).where(
            Transaction.paid_at >= start_dt,
            Transaction.paid_at <= end_dt,
        )

        if status != "all":
            agg_stmt = agg_stmt.where(
                Transaction.status == TransactionStatus(status)
            )
        if tx_type != "all":
            agg_stmt = agg_stmt.where(
                Transaction.type == TransactionType(tx_type)
            )

        result = await self.session.execute(agg_stmt)
        row = result.one()

        daily: Optional[list[DailyEntry]] = None
        if include_daily_shift:
            daily = await self._get_daily_shift(start_dt, end_dt, status, tx_type)

        # FIXED: Decimal values returned by PostgreSQL are rounded to 2dp and
        # converted to float only here at the API response boundary.
        # float(None) would raise, so we guard each optional field.
        return ReportResponse(
            total=round(float(row.total), 2),
            count=row.count,
            avg=round(float(row.avg), 2) if include_avg and row.avg is not None else None,
            min=round(float(row.min), 2) if include_min and row.min is not None else None,
            max=round(float(row.max), 2) if include_max and row.max is not None else None,
            daily=daily,
        )

    async def _get_daily_shift(
        self,
        start_dt: datetime,
        end_dt: datetime,
        status: str,
        tx_type: str,
    ) -> list[DailyEntry]:
        """Return per-day successful totals with % change vs. the previous day."""
        # func.date() works in both PostgreSQL and SQLite (test dialect).
        day_col = func.date(Transaction.paid_at).label("day")

        stmt = (
            select(
                day_col,
                func.sum(Transaction.amount).label("daily_total"),
            )
            .where(
                Transaction.paid_at >= start_dt,
                Transaction.paid_at <= end_dt,
                Transaction.status == TransactionStatus.SUCCESSFUL,
            )
            .group_by(day_col)
            .order_by(day_col)
        )

        if tx_type != "all":
            stmt = stmt.where(Transaction.type == TransactionType(tx_type))

        result = await self.session.execute(stmt)
        rows = result.all()

        entries: list[DailyEntry] = []
        prev_total: Optional[float] = None

        for row in rows:
            current_total = round(float(row.daily_total), 2)
            if prev_total is not None and prev_total != 0:
                change_pct = round((current_total - prev_total) / prev_total * 100, 2)
            else:
                change_pct = None

            raw_day = row.day
            parsed_day = date.fromisoformat(raw_day) if isinstance(raw_day, str) else raw_day

            entries.append(
                DailyEntry(
                    date=parsed_day,
                    total=current_total,
                    change_pct=change_pct,
                )
            )
            prev_total = current_total

        return entries
