#!/bin/sh

echo "Waiting for database..."

while ! nc -z db 5432; do
  sleep 1
done

echo "Database ready"

python manage.py migrate

gunicorn realtyos.wsgi:application \
  --bind 0.0.0.0:8000 \
  --worker-class gthread \
  --workers "${GUNICORN_WORKERS:-2}" \
  --threads "${GUNICORN_THREADS:-4}" \
  --timeout "${GUNICORN_TIMEOUT:-180}"
