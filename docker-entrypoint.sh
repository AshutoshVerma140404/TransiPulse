#!/bin/bash
set -e

echo "Starting TransiPulse with Docker..."

# Wait for database if needed
if [ "$DATABASE_URL" = "sqlite+aiosqlite:///./transipulse.db" ]; then
    echo "Using SQLite database..."
else
    echo "Waiting for database..."
    # Add logic to wait for external database if needed
fi

# Seed database if empty
if [ ! -f "transipulse.db" ]; then
    echo "Seeding database with sample data..."
    python -m app.data.seed
fi

# Run migrations if using PostgreSQL
if [[ "$DATABASE_URL" == postgresql* ]]; then
    echo "Running database migrations..."
    alembic upgrade head
fi

# Start the application
echo "Starting TransiPulse server..."
exec python -m app.main
