## Run Alembic Migrations

# Configuration
cp alembic.ini.example alembic.ini

# Update the alembic.ini with your database credentials (sqlalchemy.url)

# (Optional) Create a new migration

alembic revision --autogenerate -m "Initial Commit"
# Upgrade the database

alembic upgrade head

