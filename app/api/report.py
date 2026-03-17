"""API endpoints for analytics reports."""

import calendar
from datetime import date
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.report import CountryReportResponse, ReportResponse
from app.services.country_service import CountryReportService
from app.services.report_service import ReportService

router = APIRouter(prefix="/report", tags=["Reports"])


def _default_start() -> date:
    """Return the date exactly one calendar month ago.

    FIXED: the original implementation used ``timedelta(days=30)`` which is
    not the same as "one month ago" — February has 28/29 days and some months
    have 31.  The ТЗ specifies *one month ago*, so we use proper calendar
    arithmetic via the stdlib ``calendar`` module.
    """
    today = date.today()
    month = today.month - 1 or 12  # wrap December ← January
    year = today.year - (1 if today.month == 1 else 0)
    # Clamp the day to the last valid day of the target month
    # (e.g. March 31 → February 28/29).
    day = min(today.day, calendar.monthrange(year, month)[1])
    return today.replace(year=year, month=month, day=day)


@router.get(
    "",
    response_model=ReportResponse,
    summary="Transaction analytics report",
    description=(
        "Returns aggregated metrics for transactions within the specified date range. "
        "Monetary aggregates (avg, min, max, total) are computed over **successful** "
        "transactions only; `count` reflects all transactions matching the filters."
    ),
)
async def get_report(
    db: Annotated[AsyncSession, Depends(get_db)],
    start_date: Annotated[
        Optional[date],
        Query(description="Start date (YYYY-MM-DD). Defaults to one calendar month ago."),
    ] = None,
    end_date: Annotated[
        Optional[date],
        Query(description="End date (YYYY-MM-DD). Defaults to today."),
    ] = None,
    status: Annotated[
        Literal["successful", "failed", "all"],
        Query(description="Filter by transaction status."),
    ] = "all",
    # FIXED: was named `type`, which shadows the Python builtin.
    # The public query-parameter name is preserved via Query(alias="type") so
    # existing API clients see no breaking change.
    tx_type: Annotated[
        Literal["payment", "invoice", "all"],
        Query(alias="type", description="Filter by transaction type."),
    ] = "all",
    include_avg: Annotated[bool, Query(description="Include average amount.")] = False,
    include_min: Annotated[bool, Query(description="Include minimum amount.")] = False,
    include_max: Annotated[bool, Query(description="Include maximum amount.")] = False,
    include_daily_shift: Annotated[
        bool, Query(description="Include daily totals with % change vs. previous day.")
    ] = False,
) -> ReportResponse:
    """Compute and return transaction analytics for the requested filters."""
    resolved_start = start_date or _default_start()
    resolved_end = end_date or date.today()

    if resolved_start > resolved_end:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="start_date must not be after end_date.",
        )

    service = ReportService(session=db)
    return await service.get_report(
        start_date=resolved_start,
        end_date=resolved_end,
        status=status,
        tx_type=tx_type,
        include_avg=include_avg,
        include_min=include_min,
        include_max=include_max,
        include_daily_shift=include_daily_shift,
    )


@router.get(
    "/by-country",
    response_model=CountryReportResponse,
    summary="Transaction analytics grouped by country",
    description=(
        "Joins successful transaction data with the country CSV "
        "and returns aggregated statistics per country. "
        "Only the 100 users present in the CSV file are included."
    ),
)
async def get_report_by_country(
    db: Annotated[AsyncSession, Depends(get_db)],
    sort_by: Annotated[
        Literal["count", "total", "avg"],
        Query(description="Metric to sort countries by (descending)."),
    ] = "total",
    top_n: Annotated[
        Optional[int],
        Query(ge=1, description="Limit the number of countries returned."),
    ] = None,
) -> CountryReportResponse:
    """Return per-country transaction statistics joined with the country CSV."""
    service = CountryReportService(session=db)
    try:
        return await service.get_country_report(sort_by=sort_by, top_n=top_n)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
