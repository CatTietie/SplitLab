#!/bin/bash
set -e

# Ensure metadata directory exists for persistent state
mkdir -p /app/metadata

echo "Running database migrations..."
alembic upgrade head

echo "Starting application..."
exec "$@"
