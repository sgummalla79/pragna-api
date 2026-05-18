import os
from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config
# Do not call fileConfig here — our configure_logging() is already applied at startup.
# Calling fileConfig would reset the root logger level to WARN (from alembic.ini),
# silently dropping all INFO logs for the rest of the process lifetime.

# Read DATABASE_URL from environment (set before alembic runs)
database_url = os.getenv("DATABASE_URL", "")
if not database_url:
    raise RuntimeError("DATABASE_URL environment variable is not set.")
# Use psycopg v3 driver — replace postgresql:// with postgresql+psycopg://
if database_url.startswith("postgresql://") or database_url.startswith("postgres://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
config.set_main_option("sqlalchemy.url", database_url)

target_metadata = None


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
