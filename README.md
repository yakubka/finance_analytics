# Analytics API

A FastAPI-based analytics service backed by PostgreSQL that exposes transaction reporting endpoints with filtering, aggregation, and country-level breakdowns.

---

## Tech Stack

| Layer | Technology |
|---|---|
| API framework | FastAPI 0.111 |
| ORM | SQLAlchemy 2 (async) |
| Database | PostgreSQL 16 |
| Migrations | Alembic |
| Data processing | pandas |
| Containerisation | Docker + Docker Compose |
| Testing | pytest + pytest-asyncio (SQLite in-memory) |

---

## Project Structure

```
analytics_api/
├── app/
│   ├── api/            # FastAPI routers
│   ├── db/             # Engine, session, Base
│   ├── models/         # SQLAlchemy ORM models
│   ├── schemas/        # Pydantic response schemas
│   ├── services/       # Business logic (ReportService, CountryReportService)
│   ├── config.py       # Settings via pydantic-settings
│   └── main.py         # App factory
├── migrations/
│   └── versions/       # Alembic migration files
├── scripts/
│   └── seed.py         # Mock data generator (120 users, 12 000 transactions)
├── tests/
│   ├── conftest.py     # Fixtures (in-memory SQLite, AsyncClient)
│   ├── test_report_service.py
│   ├── test_country_service.py
│   └── test_endpoints.py
├── user_country.csv    # 100-row user → country mapping
├── Dockerfile
├── docker-compose.yml
├── docker-entrypoint.sh
├── alembic.ini
└── requirements.txt
```

---

## Quick Start (Docker)

### 1. Clone the repository

```bash
git clone https://github.com/yakubka/finance_analytics.git
cd analytics_api
```

All configuration has sensible defaults built into `app/config.py` so no `.env` file is required for local Docker usage. If you want to override any value, copy the example and edit it:

```bash
cp .env.example .env   # optional
```

### 2. Start services

```bash
docker-compose up --build
```

The entrypoint automatically:
1. Waits for PostgreSQL to become healthy
2. Runs `alembic upgrade head` to apply all migrations
3. Starts Uvicorn on port **8000**

### 3. Seed the database (first run)

**Option A — automatic** (set env var before starting):

```bash
SEED_DB=true docker-compose up --build
```

**Option B — manual** (after services are running):

```bash
docker-compose exec app python scripts/seed.py
```

This inserts **120 users** and **12 000 transactions** distributed over the last 2 years with balanced statuses and types.

### 4. Explore the API

| URL | Description |
|---|---|
| http://localhost:8000/docs | Swagger UI |
| http://localhost:8000/redoc | ReDoc |
| http://localhost:8000/healthz | Liveness probe |

---

## API Reference

### `GET /report`

Returns aggregated transaction metrics for a configurable date range.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `start_date` | `YYYY-MM-DD` | one calendar month ago | Range start (inclusive) |
| `end_date` | `YYYY-MM-DD` | today | Range end (inclusive) |
| `status` | `successful` / `failed` / `all` | `all` | Filter by status |
| `type` | `payment` / `invoice` / `all` | `all` | Filter by type |
| `include_avg` | bool | `false` | Add average amount to response |
| `include_min` | bool | `false` | Add minimum amount |
| `include_max` | bool | `false` | Add maximum amount |
| `include_daily_shift` | bool | `false` | Add daily totals with % change vs. previous day |

> **Note:** `total`, `avg`, `min`, `max` are computed over **successful** transactions only. `count` reflects all transactions that match the filters.

**Example request:**

```
GET /report?start_date=2024-01-01&end_date=2024-03-31&status=successful&include_avg=true&include_daily_shift=true
```

**Example response:**

```json
{
  "total": 312847.50,
  "count": 1423,
  "avg": 219.85,
  "min": null,
  "max": null,
  "daily": [
    { "date": "2024-01-01", "total": 4821.30, "change_pct": null },
    { "date": "2024-01-02", "total": 5203.10, "change_pct": 7.92 }
  ]
}
```

---

### `GET /report/by-country`

Joins successful transaction data with the country CSV and returns per-country aggregates.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `sort_by` | `count` / `total` / `avg` | `total` | Metric to sort by (descending) |
| `top_n` | integer ≥ 1 | — | Limit number of countries returned |

**Example request:**

```
GET /report/by-country?sort_by=count&top_n=5
```

**Example response:**

```json
{
  "sort_by": "count",
  "top_n": 5,
  "data": [
    { "country": "Germany",       "count": 420, "total": 89234.10, "avg": 212.46 },
    { "country": "United States", "count": 380, "total": 76102.50, "avg": 200.27 }
  ]
}
```

---

## Running Tests Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests with coverage report
pytest
```

Tests use an **in-memory SQLite** database — no PostgreSQL required.

To see the HTML coverage report:

```bash
pytest --cov-report=html
open htmlcov/index.html
```

---

## Database Migrations

```bash
# Apply all pending migrations
docker-compose exec app alembic upgrade head

# Roll back one migration
docker-compose exec app alembic downgrade -1

# Generate a new migration after model changes
docker-compose exec app alembic revision --autogenerate -m "your description"
```

---

## Design Notes

### Query optimisation

The `transactions` table has the following indexes:

- `ix_transactions_paid_at` — primary date-range filter
- `ix_transactions_status` / `ix_transactions_type` — single-column filters
- `ix_transactions_paid_at_status` — composite for the common `WHERE paid_at BETWEEN … AND status = …` pattern
- `ix_transactions_paid_at_type` — composite for type-filtered date queries
- `ix_transactions_user_status` — composite for per-user successful lookup (country report)

All monetary aggregates (`SUM`, `AVG`, `MIN`, `MAX`) are computed in a single SQL round-trip using `CASE` expressions to restrict calculations to successful rows without a second query.

### Country report

The endpoint performs the join in **pandas** (in application memory) rather than SQL because the country data lives in a CSV file outside the database. The inner join ensures only the 100 users present in the CSV contribute to the results.
