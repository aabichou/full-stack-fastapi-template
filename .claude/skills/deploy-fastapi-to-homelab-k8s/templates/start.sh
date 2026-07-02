#! /usr/bin/env bash
# Production single-container entrypoint: wait for the DB, migrate, seed, serve.
set -e
cd /app/backend
python app/backend_pre_start.py      # wait for Postgres
alembic upgrade head                 # migrations
python app/initial_data.py           # seed (idempotent)
exec fastapi run app/main.py --host 0.0.0.0 --port 8000
