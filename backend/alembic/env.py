"""Alembic async environment for VoiceField backend.

- Reads DATABASE_URL from app.core.config.get_settings() (same source as
  app/core/database.py), stripping libpq-style query params (e.g.
  ?sslmode=require) because asyncpg takes TLS via connect_args.
- Imports Base.metadata from app.models.models (which itself imports Base
  from app.core.database — verified).
- Supports offline + online modes with the async run_sync pattern.
"""

import asyncio
import os
import sys
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Ensure backend root (this file's parent's parent) is on sys.path so
# `import app...` works regardless of prepend_sys_path handling.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import application settings + model metadata.
from app.core.config import get_settings  # noqa: E402
from app.models import models as _models  # noqa: E402,F401  (ensure models registered)
from app.core.database import Base, _connect_args  # noqa: E402

target_metadata = Base.metadata


def get_url() -> str:
    """Return the SQLAlchemy URL with query params stripped (asyncpg compat)."""
    settings = get_settings()
    url = settings.DATABASE_URL
    return url.split("?")[0]


def get_connect_args() -> dict:
    """TLS connect args for managed Postgres (mirrors app.core.database)."""
    settings = get_settings()
    return _connect_args(settings.DATABASE_URL)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode using an async engine."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=get_connect_args(),
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
