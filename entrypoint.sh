#!/usr/bin/env sh
set -e

cd /app

echo "[entrypoint] makemigrations (if any new models) ..."
python manage.py makemigrations api --noinput

echo "[entrypoint] migrate ..."
python manage.py migrate --noinput

echo "[entrypoint] collectstatic ..."
python manage.py collectstatic --noinput >/dev/null

echo "[entrypoint] seed_factors ..."
python manage.py seed_factors

echo "[entrypoint] seed_demo (idempotent) ..."
python manage.py seed_demo

echo "[entrypoint] starting gunicorn on :${PORT:-8000} ..."
exec gunicorn server.wsgi:application \
    --bind=0.0.0.0:${PORT:-8000} \
    --workers=2 \
    --threads=2 \
    --timeout=60 \
    --access-logfile=- \
    --error-logfile=-
