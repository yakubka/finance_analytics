"""Unit tests for ReportService business logic."""

from datetime import date, datetime, timezone

import pytest

from app.models.transaction import TransactionStatus, TransactionType
from app.services.report_service import ReportService
from tests.conftest import create_transaction, create_user


@pytest.mark.asyncio
async def test_report_total_only_successful(db_session):
    """Total must include only successful transactions."""
    user = await create_user(db_session, email="u1@test.com")
    await create_transaction(
        db_session, user.id,
        amount=200.00,
        status=TransactionStatus.SUCCESSFUL,
        paid_at=datetime(2024, 6, 10, tzinfo=timezone.utc),
    )
    await create_transaction(
        db_session, user.id,
        amount=999.00,
        status=TransactionStatus.FAILED,
        paid_at=datetime(2024, 6, 10, tzinfo=timezone.utc),
    )

    service = ReportService(db_session)
    result = await service.get_report(
        start_date=date(2024, 6, 1),
        end_date=date(2024, 6, 30),
        status="all",
        tx_type="all",
        include_avg=False,
        include_min=False,
        include_max=False,
        include_daily_shift=False,
    )

    assert result.total == pytest.approx(200.00)
    assert result.count == 2  # both rows counted


@pytest.mark.asyncio
async def test_report_count_with_status_filter(db_session):
    """Count must reflect the status filter."""
    user = await create_user(db_session, email="u2@test.com")
    for _ in range(3):
        await create_transaction(
            db_session, user.id,
            status=TransactionStatus.SUCCESSFUL,
            paid_at=datetime(2024, 6, 10, tzinfo=timezone.utc),
        )
    for _ in range(2):
        await create_transaction(
            db_session, user.id,
            status=TransactionStatus.FAILED,
            paid_at=datetime(2024, 6, 10, tzinfo=timezone.utc),
        )

    service = ReportService(db_session)
    result = await service.get_report(
        start_date=date(2024, 6, 1),
        end_date=date(2024, 6, 30),
        status="failed",
        tx_type="all",
        include_avg=False,
        include_min=False,
        include_max=False,
        include_daily_shift=False,
    )
    assert result.count == 2
    assert result.total == pytest.approx(0.0)  # failed → no monetary aggregate


@pytest.mark.asyncio
async def test_report_include_avg_min_max(db_session):
    """avg/min/max must be returned when requested and computed over successful rows only."""
    user = await create_user(db_session, email="u3@test.com")
    amounts = [100.0, 200.0, 300.0]
    for amt in amounts:
        await create_transaction(
            db_session, user.id,
            amount=amt,
            status=TransactionStatus.SUCCESSFUL,
            paid_at=datetime(2024, 6, 10, tzinfo=timezone.utc),
        )

    service = ReportService(db_session)
    result = await service.get_report(
        start_date=date(2024, 6, 1),
        end_date=date(2024, 6, 30),
        status="all",
        tx_type="all",
        include_avg=True,
        include_min=True,
        include_max=True,
        include_daily_shift=False,
    )

    assert result.avg == pytest.approx(200.0)
    assert result.min == pytest.approx(100.0)
    assert result.max == pytest.approx(300.0)


@pytest.mark.asyncio
async def test_report_avg_none_when_not_requested(db_session):
    """avg must be None when include_avg=False."""
    user = await create_user(db_session, email="u4@test.com")
    await create_transaction(db_session, user.id, paid_at=datetime(2024, 6, 10, tzinfo=timezone.utc))

    service = ReportService(db_session)
    result = await service.get_report(
        start_date=date(2024, 6, 1),
        end_date=date(2024, 6, 30),
        status="all",
        tx_type="all",
        include_avg=False,
        include_min=False,
        include_max=False,
        include_daily_shift=False,
    )
    assert result.avg is None
    assert result.min is None
    assert result.max is None


@pytest.mark.asyncio
async def test_report_type_filter(db_session):
    """Type filter must restrict which transactions appear in count."""
    user = await create_user(db_session, email="u5@test.com")
    await create_transaction(
        db_session, user.id,
        type=TransactionType.PAYMENT,
        paid_at=datetime(2024, 6, 10, tzinfo=timezone.utc),
    )
    await create_transaction(
        db_session, user.id,
        type=TransactionType.INVOICE,
        paid_at=datetime(2024, 6, 10, tzinfo=timezone.utc),
    )

    service = ReportService(db_session)
    result = await service.get_report(
        start_date=date(2024, 6, 1),
        end_date=date(2024, 6, 30),
        status="all",
        tx_type="payment",
        include_avg=False,
        include_min=False,
        include_max=False,
        include_daily_shift=False,
    )
    assert result.count == 1


@pytest.mark.asyncio
async def test_report_date_range_filter(db_session):
    """Transactions outside the date range must not appear in results."""
    user = await create_user(db_session, email="u6@test.com")
    await create_transaction(
        db_session, user.id,
        paid_at=datetime(2024, 5, 1, tzinfo=timezone.utc),  # before range
    )
    await create_transaction(
        db_session, user.id,
        paid_at=datetime(2024, 6, 15, tzinfo=timezone.utc),  # inside range
    )
    await create_transaction(
        db_session, user.id,
        paid_at=datetime(2024, 7, 1, tzinfo=timezone.utc),  # after range
    )

    service = ReportService(db_session)
    result = await service.get_report(
        start_date=date(2024, 6, 1),
        end_date=date(2024, 6, 30),
        status="all",
        tx_type="all",
        include_avg=False,
        include_min=False,
        include_max=False,
        include_daily_shift=False,
    )
    assert result.count == 1


@pytest.mark.asyncio
async def test_report_empty_range(db_session):
    """Querying an empty range returns zeros and empty collections."""
    user = await create_user(db_session, email="u7@test.com")
    await create_transaction(
        db_session, user.id,
        paid_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )

    service = ReportService(db_session)
    result = await service.get_report(
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
        status="all",
        tx_type="all",
        include_avg=True,
        include_min=True,
        include_max=True,
        include_daily_shift=False,
    )
    assert result.count == 0
    assert result.total == pytest.approx(0.0)
    assert result.avg is None
    assert result.min is None
    assert result.max is None


@pytest.mark.asyncio
async def test_report_daily_shift_single_day(db_session):
    """With a single day of data the first entry has change_pct=None."""
    user = await create_user(db_session, email="u8@test.com")
    await create_transaction(
        db_session, user.id,
        amount=500.0,
        status=TransactionStatus.SUCCESSFUL,
        paid_at=datetime(2024, 6, 15, 10, 0, tzinfo=timezone.utc),
    )

    service = ReportService(db_session)
    result = await service.get_report(
        start_date=date(2024, 6, 15),
        end_date=date(2024, 6, 15),
        status="all",
        tx_type="all",
        include_avg=False,
        include_min=False,
        include_max=False,
        include_daily_shift=True,
    )
    assert result.daily is not None
    assert len(result.daily) == 1
    assert result.daily[0].change_pct is None
    assert result.daily[0].total == pytest.approx(500.0)


@pytest.mark.asyncio
async def test_report_daily_shift_two_days(db_session):
    """Percentage change is correct across two consecutive days."""
    user = await create_user(db_session, email="u9@test.com")
    await create_transaction(
        db_session, user.id,
        amount=100.0,
        status=TransactionStatus.SUCCESSFUL,
        paid_at=datetime(2024, 6, 14, 10, 0, tzinfo=timezone.utc),
    )
    await create_transaction(
        db_session, user.id,
        amount=150.0,
        status=TransactionStatus.SUCCESSFUL,
        paid_at=datetime(2024, 6, 15, 10, 0, tzinfo=timezone.utc),
    )

    service = ReportService(db_session)
    result = await service.get_report(
        start_date=date(2024, 6, 14),
        end_date=date(2024, 6, 15),
        status="all",
        tx_type="all",
        include_avg=False,
        include_min=False,
        include_max=False,
        include_daily_shift=True,
    )
    assert result.daily is not None
    assert result.daily[0].change_pct is None
    assert result.daily[1].change_pct == pytest.approx(50.0)  # (150-100)/100*100


@pytest.mark.asyncio
async def test_report_daily_shift_only_successful(db_session):
    """Daily shift must ignore failed transactions."""
    user = await create_user(db_session, email="u10@test.com")
    await create_transaction(
        db_session, user.id,
        amount=200.0,
        status=TransactionStatus.SUCCESSFUL,
        paid_at=datetime(2024, 6, 14, 10, 0, tzinfo=timezone.utc),
    )
    await create_transaction(
        db_session, user.id,
        amount=9999.0,
        status=TransactionStatus.FAILED,   # must be excluded from daily
        paid_at=datetime(2024, 6, 14, 11, 0, tzinfo=timezone.utc),
    )

    service = ReportService(db_session)
    result = await service.get_report(
        start_date=date(2024, 6, 14),
        end_date=date(2024, 6, 14),
        status="all",
        tx_type="all",
        include_avg=False,
        include_min=False,
        include_max=False,
        include_daily_shift=True,
    )
    assert result.daily[0].total == pytest.approx(200.0)
