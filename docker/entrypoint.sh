#!/bin/sh
set -e

echo "⏳ Waiting for postgres..."

until pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER"; do
  sleep 2
done

echo "✅ Postgres is up"

echo "📦 Applying alembic migrations..."
alembic upgrade head

echo "🚀 Starting app"
exec python main.py
