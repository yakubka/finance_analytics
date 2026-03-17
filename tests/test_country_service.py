"""Unit tests for CountryReportService."""

import os
import tempfile
from datetime import datetime, timezone

import pytest

from app.models.transaction import TransactionStatus, TransactionType
from app.services.country_service import CountryReportService
from tests.conftest import create_transaction, create_user


def _write_csv(content: str) -> str:
    """Write CSV content to a temp file and return its path."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False)
    f.write(content)
    f.close()
    return f.name


@pytest.fixture(autouse=True)
def cleanup_tmp_files():
    """Remove temp CSV files after each test."""
    paths: list[str] = []
    yield paths
    for p in paths:
        try:
            os.unlink(p)
        except FileNotFoundError:
            pass


@pytest.mark.asyncio
async def test_country_report_basic(db_session, cleanup_tmp_files):
    """Aggregates by country and returns correct totals."""
    csv_path = _write_csv("user_id;country\n1;Germany\n2;France\n")
    cleanup_tmp_files.append(csv_path)

    user1 = await create_user(db_session, email="a@test.com")
    user2 = await create_user(db_session, email="b@test.com")

    await create_transaction(
        db_session, user1.id,
        amount=100.0,
        status=TransactionStatus.SUCCESSFUL,
        paid_at=datetime(2024, 6, 10, tzinfo=timezone.utc),
    )
    await create_transaction(
        db_session, user2.id,
        amount=200.0,
        status=TransactionStatus.SUCCESSFUL,
        paid_at=datetime(2024, 6, 10, tzinfo=timezone.utc),
    )

    service = CountryReportService(db_session, csv_path=csv_path)
    result = await service.get_country_report(sort_by="total", top_n=None)

    assert result.sort_by == "total"
    assert len(result.data) == 2
    # France has the higher total → comes first
    assert result.data[0].country == "France"
    assert result.data[0].total == pytest.approx(200.0)
    assert result.data[1].country == "Germany"


@pytest.mark.asyncio
async def test_country_report_top_n(db_session, cleanup_tmp_files):
    """top_n limits the number of rows returned."""
    csv_path = _write_csv("user_id;country\n1;Germany\n2;France\n3;Spain\n")
    cleanup_tmp_files.append(csv_path)

    for i, email in enumerate(["c@test.com", "d@test.com", "e@test.com"], start=1):
        user = await create_user(db_session, email=email)
        await create_transaction(
            db_session, user.id,
            amount=float(i * 100),
            status=TransactionStatus.SUCCESSFUL,
            paid_at=datetime(2024, 6, 10, tzinfo=timezone.utc),
        )

    service = CountryReportService(db_session, csv_path=csv_path)
    result = await service.get_country_report(sort_by="total", top_n=2)

    assert len(result.data) == 2


@pytest.mark.asyncio
async def test_country_report_sort_by_count(db_session, cleanup_tmp_files):
    """Sorting by count returns country with most transactions first."""
    csv_path = _write_csv("user_id;country\n1;Germany\n2;France\n")
    cleanup_tmp_files.append(csv_path)

    user1 = await create_user(db_session, email="f@test.com")
    user2 = await create_user(db_session, email="g@test.com")

    # Germany user → 3 transactions
    for _ in range(3):
        await create_transaction(
            db_session, user1.id,
            amount=10.0,
            status=TransactionStatus.SUCCESSFUL,
            paid_at=datetime(2024, 6, 10, tzinfo=timezone.utc),
        )
    # France user → 1 transaction with higher amount
    await create_transaction(
        db_session, user2.id,
        amount=500.0,
        status=TransactionStatus.SUCCESSFUL,
        paid_at=datetime(2024, 6, 10, tzinfo=timezone.utc),
    )

    service = CountryReportService(db_session, csv_path=csv_path)
    result = await service.get_country_report(sort_by="count", top_n=None)

    assert result.data[0].country == "Germany"
    assert result.data[0].count == 3


@pytest.mark.asyncio
async def test_country_report_excludes_failed(db_session, cleanup_tmp_files):
    """Only successful transactions are included in country stats."""
    csv_path = _write_csv("user_id;country\n1;Germany\n")
    cleanup_tmp_files.append(csv_path)

    user = await create_user(db_session, email="h@test.com")
    await create_transaction(
        db_session, user.id,
        amount=300.0,
        status=TransactionStatus.SUCCESSFUL,
        paid_at=datetime(2024, 6, 10, tzinfo=timezone.utc),
    )
    await create_transaction(
        db_session, user.id,
        amount=9999.0,
        status=TransactionStatus.FAILED,
        paid_at=datetime(2024, 6, 10, tzinfo=timezone.utc),
    )

    service = CountryReportService(db_session, csv_path=csv_path)
    result = await service.get_country_report(sort_by="total", top_n=None)

    assert result.data[0].total == pytest.approx(300.0)
    assert result.data[0].count == 1


@pytest.mark.asyncio
async def test_country_report_user_not_in_csv(db_session, cleanup_tmp_files):
    """Users absent from the CSV are excluded from results (inner join)."""
    csv_path = _write_csv("user_id;country\n1;Germany\n")
    cleanup_tmp_files.append(csv_path)

    user1 = await create_user(db_session, email="i@test.com")   # id → appears in CSV
    user2 = await create_user(db_session, email="j@test.com")   # id → NOT in CSV

    await create_transaction(
        db_session, user1.id,
        amount=100.0,
        status=TransactionStatus.SUCCESSFUL,
        paid_at=datetime(2024, 6, 10, tzinfo=timezone.utc),
    )
    await create_transaction(
        db_session, user2.id,
        amount=500.0,
        status=TransactionStatus.SUCCESSFUL,
        paid_at=datetime(2024, 6, 10, tzinfo=timezone.utc),
    )

    service = CountryReportService(db_session, csv_path=csv_path)
    result = await service.get_country_report(sort_by="total", top_n=None)

    # Only Germany (user1) should appear
    assert len(result.data) == 1
    assert result.data[0].country == "Germany"


@pytest.mark.asyncio
async def test_country_report_file_not_found(db_session):
    """FileNotFoundError is raised when CSV path does not exist."""
    service = CountryReportService(db_session, csv_path="/nonexistent/path.csv")
    with pytest.raises(FileNotFoundError):
        await service.get_country_report(sort_by="total", top_n=None)


@pytest.mark.asyncio
async def test_country_report_invalid_sort_by(db_session, cleanup_tmp_files):
    """ValueError is raised for unsupported sort_by value."""
    csv_path = _write_csv("user_id;country\n1;Germany\n")
    cleanup_tmp_files.append(csv_path)

    service = CountryReportService(db_session, csv_path=csv_path)
    with pytest.raises(ValueError):
        await service.get_country_report(sort_by="invalid", top_n=None)


@pytest.mark.asyncio
async def test_country_report_empty_transactions(db_session, cleanup_tmp_files):
    """Empty transaction table returns empty data list."""
    csv_path = _write_csv("user_id;country\n1;Germany\n")
    cleanup_tmp_files.append(csv_path)

    await create_user(db_session, email="k@test.com")

    service = CountryReportService(db_session, csv_path=csv_path)
    result = await service.get_country_report(sort_by="total", top_n=None)

    assert result.data == []
