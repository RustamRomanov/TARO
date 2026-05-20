#!/bin/sh
# Явный вывод в stdout: в Railway иначе видно только «Starting Container», пока идут миграции или импорт.
set -e
export PYTHONUNBUFFERED=1
PORT="${PORT:-8000}"
echo "[astrov] start.sh PORT=$PORT"
echo "[astrov] python $(python -V 2>&1)"
if [ -n "$DATABASE_URL" ]; then
  echo "[astrov] alembic upgrade head..."
  python -u -m alembic upgrade head
  echo "[astrov] alembic done"
else
  echo "[astrov] DATABASE_URL empty, skip migrations"
fi
echo "[astrov] uvicorn app.main:app --host 0.0.0.0 --port $PORT"
exec python -u -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
