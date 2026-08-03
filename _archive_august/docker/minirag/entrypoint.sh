#!/bin/bash
set -e

echo "Starting FastAPI application setup..."

# Wait for database to be ready (optional but recommended)
echo "Waiting for database connection..."
python -c "
import time
import sys
import os
try:
    import psycopg2
    from urllib.parse import urlparse
    
    # Get database URL from environment or use default
    database_url = os.getenv('DATABASE_URL', 'postgresql://postgres:secret_password@pgvector:5432/minirag')
    parsed = urlparse(database_url)
    
    max_attempts = 30
    attempt = 0
    while attempt < max_attempts:
        try:
            conn = psycopg2.connect(
                host=parsed.hostname,
                port=parsed.port or 5432,
                user=parsed.username,
                password=parsed.password,
                database=parsed.path.lstrip('/'),
                connect_timeout=5
            )
            conn.close()
            print('Database connection successful!')
            break
        except psycopg2.OperationalError as e:
            attempt += 1
            print(f'Database connection attempt {attempt}/{max_attempts} failed: {e}')
            if attempt < max_attempts:
                time.sleep(2)
            else:
                print('Failed to connect to database after all attempts')
                sys.exit(1)
        except Exception as e:
            print(f'Database connection check failed: {e}')
            break
except ImportError:
    print('psycopg2 not available, skipping database connection check')
except Exception as e:
    print(f'Database connection check error: {e}')
"

# Run database migrations
echo "Running database migrations..."
cd /app/models/db_schemes/minirag/
alembic upgrade head

# Return to app directory
cd /app

echo "Starting application with command: $@"

# Execute the command passed to the container (from CMD or docker-compose command)
exec "$@"