#!/bin/sh
set -eu

echo "Waiting for database..."

DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-5432}"

while ! nc -z "$DB_HOST" "$DB_PORT"; do
  sleep 1
done

echo "Database ready"

python manage.py migrate --noinput
python manage.py collectstatic --noinput

gunicorn realtyos.wsgi:application \
  --bind 0.0.0.0:8000 \
  --worker-class gthread \
  --workers "${GUNICORN_WORKERS:-2}" \
  --threads "${GUNICORN_THREADS:-4}" \
  --timeout "${GUNICORN_TIMEOUT:-180}"
