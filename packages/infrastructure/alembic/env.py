"""Alembic environment: runs migrations against the database named by ``DATABASE_URL``.

The URL comes from the process environment first, then from the git-ignored ``.env`` at the
repository root. It is never read from ``alembic.ini``, so no credential can be committed by
accident. A plain ``postgresql://`` URL is upgraded to the ``asyncpg`` driver because the rest of
the application is async.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from alembic import context
from dotenv import dotenv_values
from sqlalchemy import pool
from sqlalchemy.engine import URL, Connection, make_url
from sqlalchemy.ext.asyncio import create_async_engine

import asebe_infrastructure.database.models  # noqa: F401  (registers every model on Base.metadata)
from asebe_infrastructure.database.base import Base

target_metadata = Base.metadata


def get_database_url() -> URL:
    url = os.environ.get("DATABASE_URL")
    if not url:
        for parent in Path(__file__).resolve().parents:
            env_file = parent / ".env"
            if env_file.is_file():
                url = dotenv_values(env_file).get("DATABASE_URL")
                break
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Put it in the .env file at the repository root, "
            "or export it in your shell."
        )
    parsed = make_url(url)
    if parsed.drivername in {"postgres", "postgresql"}:
        parsed = parsed.set(drivername="postgresql+asyncpg")
    return parsed


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(get_database_url(), poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("Offline migrations are not supported; run against a database.")

asyncio.run(run_migrations_online())
