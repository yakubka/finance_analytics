#!/bin/bash
set -e

echo "Waiting for PostgreSQL to be ready..."
until python -c "
import asyncio, asyncpg, os
async def check():
    url = os.environ.get('DATABASE_URL', '')
    # Parse host/port from asyncpg-style URL
    import re
    m = re.match(r'postgresql\+asyncpg://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)', url)
    if not m:
        raise ValueError(f'Cannot parse DATABASE_URL: {url}')
    user, password, host, port, db = m.groups()
    conn = await asyncpg.connect(user=user, password=password, host=host, port=int(port), database=db)
    await conn.close()
asyncio.run(check())
" 2>/dev/null; do
  echo "  PostgreSQL not ready — retrying in 2s..."
  sleep 2
done
echo "PostgreSQL is ready."

echo "Running Alembic migrations..."
alembic upgrade head
echo "Migrations applied."

if [ "${SEED_DB:-false}" = "true" ]; then
  echo "Seeding database..."
  python scripts/seed.py
  echo "Database seeded."
fi

echo "Starting application..."
exec uvicorn app.main:app --host "${APP_HOST:-0.0.0.0}" --port "${APP_PORT:-8000}"
