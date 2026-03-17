"""Integration tests for GET /report and GET /report/by-country endpoints."""

import os
import tempfile
from datetime import datetime, timezone

import pytest

from app.models.transaction import TransactionStatus, TransactionType
from tests.conftest import create_transaction, create_user


# ---------------------------------------------------------------------------
# /report endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_healthcheck(client):
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_report_default_params(client, db_session):
    """GET /report with no params returns a valid response structure."""
    user = await create_user(db_session, email="ep1@test.com")
    await create_transaction(
        db_session, user.id,
        amount=150.0,
        status=TransactionStatus.SUCCESSFUL,
        paid_at=datetime.now(tz=timezone.utc),
    )

    response = await client.get("/report")
    assert response.status_code == 200

    body = response.json()
    assert "total" in body
    assert "count" in body
    assert body["avg"] is None
    assert body["min"] is None
    assert body["max"] is None
    assert body["daily"] is None


@pytest.mark.asyncio
async def test_report_with_all_includes(client, db_session):
    """All optional fields are returned when requested."""
    user = await create_user(db_session, email="ep2@test.com")
    await create_transaction(
        db_session, user.id,
        amount=250.0,
        status=TransactionStatus.SUCCESSFUL,
        paid_at=datetime.now(tz=timezone.utc),
    )

    response = await client.get(
        "/report",
        params={
            "include_avg": True,
            "include_min": True,
            "include_max": True,
            "include_daily_shift": True,
        },
    )
    assert response.status_code == 200

    body = response.json()
    assert body["avg"] is not None
    assert body["min"] is not None
    assert body["max"] is not None
    assert isinstance(body["daily"], list)


@pytest.mark.asyncio
async def test_report_invalid_date_range(client):
    """start_date after end_date returns HTTP 422."""
    response = await client.get(
        "/report",
        params={"start_date": "2025-12-31", "end_date": "2025-01-01"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_report_status_filter_successful(client, db_session):
    """Status filter=successful returns only successful transaction count."""
    user = await create_user(db_session, email="ep3@test.com")
    await create_transaction(
        db_session, user.id,
        status=TransactionStatus.SUCCESSFUL,
        paid_at=datetime.now(tz=timezone.utc),
    )
    await create_transaction(
        db_session, user.id,
        status=TransactionStatus.FAILED,
        paid_at=datetime.now(tz=timezone.utc),
    )

    response = await client.get("/report", params={"status": "successful"})
    assert response.status_code == 200
    assert response.json()["count"] == 1


@pytest.mark.asyncio
async def test_report_type_filter(client, db_session):
    """Type filter returns only transactions of the requested type."""
    user = await create_user(db_session, email="ep4@test.com")
    await create_transaction(
        db_session, user.id,
        type=TransactionType.PAYMENT,
        paid_at=datetime.now(tz=timezone.utc),
    )
    await create_transaction(
        db_session, user.id,
        type=TransactionType.INVOICE,
        paid_at=datetime.now(tz=timezone.utc),
    )

    response = await client.get("/report", params={"type": "invoice"})
    assert response.status_code == 200
    assert response.json()["count"] == 1


@pytest.mark.asyncio
async def test_report_invalid_status_value(client):
    """Unknown status value returns HTTP 422."""
    response = await client.get("/report", params={"status": "pending"})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# /report/by-country endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_by_country_returns_200(client, db_session, monkeypatch):
    """GET /report/by-country returns 200 with correct structure."""
    csv_content = "user_id;country\n1;Germany\n2;France\n"
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False)
    tmp.write(csv_content)
    tmp.close()

    from app.services import country_service as cs_module

    monkeypatch.setattr(cs_module.settings, "csv_path", tmp.name)

    user1 = await create_user(db_session, email="c1@test.com")
    user2 = await create_user(db_session, email="c2@test.com")
    await create_transaction(
        db_session, user1.id,
        amount=100.0,
        status=TransactionStatus.SUCCESSFUL,
        paid_at=datetime.now(tz=timezone.utc),
    )
    await create_transaction(
        db_session, user2.id,
        amount=200.0,
        status=TransactionStatus.SUCCESSFUL,
        paid_at=datetime.now(tz=timezone.utc),
    )

    response = await client.get("/report/by-country")
    assert response.status_code == 200

    body = response.json()
    assert "data" in body
    assert "sort_by" in body
    assert isinstance(body["data"], list)

    os.unlink(tmp.name)


@pytest.mark.asyncio
async def test_by_country_sort_by_count(client, db_session, monkeypatch):
    """sort_by=count returns countries ordered by transaction count."""
    csv_content = "user_id;country\n1;Germany\n2;France\n"
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False)
    tmp.write(csv_content)
    tmp.close()

    from app.services import country_service as cs_module

    monkeypatch.setattr(cs_module.settings, "csv_path", tmp.name)

    user1 = await create_user(db_session, email="cc1@test.com")
    user2 = await create_user(db_session, email="cc2@test.com")

    for _ in range(3):
        await create_transaction(
            db_session, user1.id,
            amount=10.0,
            status=TransactionStatus.SUCCESSFUL,
            paid_at=datetime.now(tz=timezone.utc),
        )
    await create_transaction(
        db_session, user2.id,
        amount=500.0,
        status=TransactionStatus.SUCCESSFUL,
        paid_at=datetime.now(tz=timezone.utc),
    )

    response = await client.get("/report/by-country", params={"sort_by": "count"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data[0]["country"] == "Germany"
    assert data[0]["count"] == 3

    os.unlink(tmp.name)


@pytest.mark.asyncio
async def test_by_country_top_n(client, db_session, monkeypatch):
    """top_n parameter limits the number of countries returned."""
    csv_content = "user_id;country\n1;Germany\n2;France\n3;Spain\n"
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False)
    tmp.write(csv_content)
    tmp.close()

    from app.services import country_service as cs_module

    monkeypatch.setattr(cs_module.settings, "csv_path", tmp.name)

    for email in ["t1@test.com", "t2@test.com", "t3@test.com"]:
        user = await create_user(db_session, email=email)
        await create_transaction(
            db_session, user.id,
            amount=100.0,
            status=TransactionStatus.SUCCESSFUL,
            paid_at=datetime.now(tz=timezone.utc),
        )

    response = await client.get("/report/by-country", params={"top_n": 2})
    assert response.status_code == 200
    assert len(response.json()["data"]) == 2

    os.unlink(tmp.name)
