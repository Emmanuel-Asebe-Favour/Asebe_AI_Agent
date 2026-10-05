"""Where the database URL comes from.

Shared by the application and by Alembic's ``env.py`` so there is exactly one answer to "which
database am I talking to". The URL is read from the process environment first, then from the
git-ignored ``.env`` at the repository root. It is never stored in a file that is committed.

A plain ``postgresql://`` URL is upgraded to the ``asyncpg`` driver, because every database call
in this package is async.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy.engine import URL, make_url


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


__all__ = ["get_database_url"]
