"""User model: the account every other table hangs off.

Transcribed from README's data model, field for field. Nothing is added beyond that list: no
password hash, no email-verification flag, no session table. Authentication is a separate piece of
work (AGENTS.md: server-side sessions in Postgres), and inventing columns for it here would mean a
migration to undo whichever guess turned out wrong.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from asebe_infrastructure.database.base import Base, Timestamps, UuidPrimaryKey


class User(UuidPrimaryKey, Timestamps, Base):
    """A creator account.

    ``time_zone`` is an IANA name such as ``Africa/Lagos``. Scheduled times are stored in UTC and
    converted using this value, so it must never be a fixed offset: an offset cannot follow a
    daylight-saving change.
    """

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    display_name: Mapped[str | None] = mapped_column(String(200))
    preferred_language: Mapped[str] = mapped_column(
        String(16), nullable=False, default="en", server_default="en"
    )
    time_zone: Mapped[str] = mapped_column(
        String(64), nullable=False, default="UTC", server_default="UTC"
    )
    notification_preferences: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    onboarding_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="not_started", server_default="not_started"
    )
