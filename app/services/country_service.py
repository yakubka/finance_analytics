"""Country-level analytics using pandas to join CSV data with DB transactions."""

from pathlib import Path
from typing import Optional

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.transaction import Transaction, TransactionStatus
from app.schemas.report import CountryReportResponse, CountryStats

VALID_SORT_COLUMNS = {"count", "total", "avg"}


class CountryReportService:
    """Joins transaction data with country CSV and returns aggregated stats."""

    def __init__(
        self,
        session: AsyncSession,
        # FIXED: was annotated as `str = None`, which is contradictory —
        # the declared type `str` does not include None, but the default is None.
        # Correct annotation is Optional[str] (i.e. str | None).
        csv_path: Optional[str] = None,
    ) -> None:
        self.session = session
        self.csv_path = csv_path or settings.csv_path

    def _load_country_map(self) -> pd.DataFrame:
        """Load user_id → country mapping from CSV file."""
        path = Path(self.csv_path)
        if not path.exists():
            raise FileNotFoundError(f"Country CSV not found at: {self.csv_path}")
        df = pd.read_csv(path, sep=";")
        df.columns = df.columns.str.strip()
        return df[["user_id", "country"]]

    async def get_country_report(
        self,
        sort_by: str,
        top_n: Optional[int],
    ) -> CountryReportResponse:
        """Aggregate successful transaction data by country using a pandas join.

        Note: this endpoint fetches all successful transactions into memory for
        the pandas merge.  For the current dataset size (≤12 000 rows) this is
        acceptable.  If the dataset grows significantly, consider pushing the
        join and aggregation into PostgreSQL via a subquery or a CTE.
        """
        if sort_by not in VALID_SORT_COLUMNS:
            raise ValueError(
                f"sort_by must be one of {VALID_SORT_COLUMNS}, got {sort_by!r}"
            )

        country_df = self._load_country_map()

        stmt = select(
            Transaction.user_id,
            Transaction.amount,
        ).where(Transaction.status == TransactionStatus.SUCCESSFUL)

        result = await self.session.execute(stmt)
        rows = result.all()

        if not rows:
            return CountryReportResponse(sort_by=sort_by, top_n=top_n, data=[])

        tx_df = pd.DataFrame(rows, columns=["user_id", "amount"])
        tx_df["amount"] = tx_df["amount"].astype(float)

        merged = tx_df.merge(country_df, on="user_id", how="inner")

        if merged.empty:
            return CountryReportResponse(sort_by=sort_by, top_n=top_n, data=[])

        agg = (
            merged.groupby("country")["amount"]
            .agg(count="count", total="sum", avg="mean")
            .reset_index()
        )

        agg = agg.sort_values(by=sort_by, ascending=False)

        if top_n is not None and top_n > 0:
            agg = agg.head(top_n)

        data = [
            CountryStats(
                country=row["country"],
                count=int(row["count"]),
                total=round(float(row["total"]), 2),
                avg=round(float(row["avg"]), 2),
            )
            for _, row in agg.iterrows()
        ]

        return CountryReportResponse(sort_by=sort_by, top_n=top_n, data=data)
