"""The audit log: an append-only record of who changed what, and from what to what.

Fields are transcribed from README's "Audit logs" section — actor, action, resource type, resource
ID, previous state, new state, timestamp — plus ``detail`` for evidence that does not fit a state
(for example, which verification outcome justified a status change).

Two design choices worth knowing about:

* **No foreign key from ``actor_user_id`` to ``users``.** An audit entry must outlive the account
  it describes. A foreign key forces a choice at deletion time between refusing to delete the
  user, cascading and erasing the record, or nulling the actor and erasing *who*. The log wants
  none of those, so it stores the id as plain data. The same goes for ``resource_id``.
* **The database itself refuses to change or delete a row** (a trigger created in the migration).
  Application code that "never updates audit rows" is a promise; a trigger is a guarantee, and an
  audit log that can be quietly edited by a bug, or by whoever is being audited, is not one.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Index, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from asebe_infrastructure.database.base import Base, UuidPrimaryKey

ACTOR_USER = "user"
ACTOR_SYSTEM = "system"


class AuditLog(UuidPrimaryKey, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        CheckConstraint(
            f"actor_type IN ('{ACTOR_USER}', '{ACTOR_SYSTEM}')", name="actor_type_known"
        ),
        # A person is always identified; the system never pretends to be one. Without this, a row
        # could say "user" and name nobody, which is an attribution that attributes nothing.
        CheckConstraint(
            f"(actor_type = '{ACTOR_USER}') = (actor_user_id IS NOT NULL)",
            name="actor_matches_type",
        ),
        # "Show me everything that happened to this post" is the question an audit log exists to
        # answer, and "what did this admin do" is the second.
        Index("ix_audit_logs_resource", "resource_type", "resource_id", "occurred_at"),
        Index("ix_audit_logs_actor", "actor_user_id", "occurred_at"),
    )

    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(64), nullable=False)
    previous_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    new_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    detail: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
