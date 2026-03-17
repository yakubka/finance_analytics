"""Pydantic schemas for request/response validation."""

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class DailyEntry(BaseModel):
    """Statistics for a single day."""

    date: date
    total: float = Field(..., description="Total amount of successful transactions for the day")
    change_pct: Optional[float] = Field(
        None, description="Percentage change vs. previous day (null for the first day)"
    )


class ReportResponse(BaseModel):
    """Response schema for GET /report endpoint."""

    total: float = Field(..., description="Total amount of successful transactions")
    count: int = Field(..., description="Number of transactions matching filters")
    avg: Optional[float] = Field(None, description="Average transaction amount (successful only)")
    min: Optional[float] = Field(None, description="Minimum transaction amount (successful only)")
    max: Optional[float] = Field(None, description="Maximum transaction amount (successful only)")
    daily: Optional[list[DailyEntry]] = Field(
        None, description="Per-day breakdown with % change vs previous day"
    )


class CountryStats(BaseModel):
    """Aggregated statistics for one country."""

    country: str
    count: int
    total: float
    avg: float


class CountryReportResponse(BaseModel):
    """Response schema for GET /report/by-country endpoint."""

    sort_by: str
    top_n: Optional[int]
    data: list[CountryStats]
