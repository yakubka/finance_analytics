#!/bin/bash
set -e

echo "Waiting for PostgreSQL to be ready..."
until python -c "
import asyncio, asyncpg, os
async def check():
    url = os.environ.get('DATABASE_URL', '')
    import re
    m = re.match(r'postgresql\+asyncpg://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)', url)
    if not m:
        raise ValueError(f'Cannot parse DATABASE_URL: {url}')
    user, password, host, port, db = m.groups()
    conn = await asyncpg.connect(
        user=user, password=password, host=host, port=int(port), database=db
    )
    await conn.close()
asyncio.run(check())
" 2>/dev/null; do
  echo "  PostgreSQL not ready — retrying in 2s..."
  sleep 2
done
echo "PostgreSQL is ready."

echo "Running Alembic migrations..."
# FIX: wrap alembic in an explicit error block so the failure reason is
# printed clearly before the container exits. Without this, set -e causes
# a silent exit with code 1 and the migration error is lost in log noise.
if ! alembic upgrade head; then
  echo ""
  echo "ERROR: Alembic migration failed — see output above."
  echo "Common causes:"
  echo "  - Column type mismatch (e.g. native ENUM vs VARCHAR)"
  echo "  - Migration already applied to an incompatible schema"
  echo "  - Database unreachable despite healthcheck passing"
  echo ""
  echo "To reset: docker compose down -v && docker compose up --build"
  exit 1
fi
echo "Migrations applied."

if [ "${SEED_DB:-false}" = "true" ]; then
  echo "Seeding database..."
  if ! python scripts/seed.py; then
    echo ""
    echo "ERROR: Seed script failed — see output above."
    exit 1
  fi
  echo "Database seeded."
fi

echo "Starting application..."
exec uvicorn app.main:app \
  --host "${APP_HOST:-0.0.0.0}" \
  --port "${APP_PORT:-8000}"