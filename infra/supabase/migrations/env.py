"""Alembic environment — async engine, URL from DATABASE_URL env var only.

Migration DDL lives in this directory per HANDOFF.md §1
(``infra/supabase/migrations`` = Alembic-managed DDL from the design docs).
"""

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Never read a URL from the ini file: DATABASE_URL is the single source
# (AWS Secrets Manager in deployment, env var locally/CI — HANDOFF.md §3).
url = os.environ.get("DATABASE_URL")
if not url:
    raise RuntimeError("DATABASE_URL env var is required for migrations")
# SQLAlchemy resolves bare postgresql:// to psycopg2; we standardise on asyncpg.
url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
config.set_main_option("sqlalchemy.url", url)

target_metadata = None  # DDL is hand-written from the design docs, no autogenerate


def run_migrations_offline() -> None:
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


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
