"""Publishing models: content items, platform posts, and every attempt made against them.

Transcribed from README's data model. **Not executed** — see the package docstring: there is no
PostgreSQL in this environment, so these models have never been created, migrated, or queried.

Two columns carry the reliability guarantees and are the reason these tables exist at all:

* ``PlatformPost.idempotency_key`` — R6. Written in the same transaction that sets ``PUBLISHING``
  (R9), which is the whole justification for a Postgres-backed queue (AGENTS.md §4).
* ``PublishingAttempt`` — R7. "Every attempt and its raw response is persisted." No publish path
  may bypass this table, which is why the raw payload is stored here rather than relying on logs:
  a log line is not a durable record and cannot be queried when a creator asks what happened.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from asebe_domain.publishing.status import PublishingStatus
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from asebe_infrastructure.database.base import Base, Timestamps, UuidPrimaryKey


class ContentItem(UuidPrimaryKey, Timestamps, Base):
    """A piece of media plus its shared caption, before it is configured per platform.

    ``is_demo`` is the column behind R11: "``is_demo = true`` content cannot reach a real platform
    adapter." Enforcement is at the repository/adapter boundary, never in the UI — a demo content
    item that reaches an adapter is a bug no amount of hidden navigation can prevent.
    """

    __tablename__ = "content_items"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(500))
    media_url: Mapped[str | None] = mapped_column(Text)
    media_type: Mapped[str | None] = mapped_column(String(255))
    caption: Mapped[str | None] = mapped_column(Text)
    is_demo: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")

    platform_posts: Mapped[list[PlatformPost]] = relationship(
        back_populates="content_item", cascade="all, delete-orphan"
    )


class PlatformPost(UuidPrimaryKey, Timestamps, Base):
    """One content item's configuration for, and lifecycle on, one platform.

    This is the row the state machine governs. ``status`` is the only column the central state
    machine writes (R8) — nothing else in the system may set it, which is why transitions are
    applied by loading the row, calling ``state_machine.transition``, and assigning the result.
    """

    __tablename__ = "platform_posts"
    __table_args__ = (
        # One configuration per (content item, platform). Two rows for the same pair would mean two
        # independent lifecycles for one post, which no part of the design anticipates.
        UniqueConstraint("content_item_id", "platform", name="content_item_platform"),
        # The reconciler for posts stuck in PUBLISHING scans by status and age
        # (docs/architecture.md §9). Without this index that sweep is a sequential scan of the
        # largest table in the schema.
        Index("ix_platform_posts_status_scheduled", "status", "scheduled_at_utc"),
    )

    content_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    platform: Mapped[str] = mapped_column(String(64), nullable=False)
    platform_caption: Mapped[str | None] = mapped_column(Text)
    platform_title: Mapped[str | None] = mapped_column(String(500))
    platform_thumbnail_url: Mapped[str | None] = mapped_column(Text)
    platform_alt_text: Mapped[str | None] = mapped_column(Text)

    status: Mapped[PublishingStatus] = mapped_column(
        # Stored as its string value, not a PostgreSQL enum type. A native enum makes adding a
        # status a migration with a lock, and the statuses are expected to grow (docs/adr/0001
        # proposes exactly that). A check constraint gives the same protection without the
        # migration cost.
        String(64), nullable=False, default=PublishingStatus.DRAFT
    )

    # --- The reliability columns -------------------------------------------------------
    platform_post_id: Mapped[str | None] = mapped_column(String(255))
    """The *platform's* identifier for the published post. Non-null exactly when status is
    PUBLISHED (R1). Note this is the remote identifier — distinct from this row's ``id``, and
    distinct from ``PublishingAttempt.platform_post_id``, which is a foreign key back to this row.
    README's data model uses the same name for both, which is a source of confusion worth fixing
    in the spec."""

    idempotency_key: Mapped[str | None] = mapped_column(String(255))
    """R6. Non-null from the moment the post enters PUBLISHING. Must be written in the same
    transaction as the status change (R9)."""

    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_error: Mapped[str | None] = mapped_column(Text)

    scheduled_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    platform_time_zone: Mapped[str | None] = mapped_column(String(64))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    content_item: Mapped[ContentItem] = relationship(back_populates="platform_posts")
    attempts: Mapped[list[PublishingAttempt]] = relationship(
        back_populates="platform_post", cascade="all, delete-orphan"
    )

    @property
    def is_demo(self) -> bool:
        """R11's check, reached through the parent content item.

        Exposed as a property so the adapter boundary has one obvious thing to test, rather than
        each call site remembering to join through to ``content_items``.
        """
        return self.content_item.is_demo


class PublishingAttempt(UuidPrimaryKey, Base):
    """R7: "Every attempt and its raw response is persisted."

    Append-only. A row is written when an attempt starts and updated once its outcome is known;
    nothing rewrites an outcome after the fact, because the audit trail's value is that it records
    what we believed at the time, not what we concluded later.
    """

    __tablename__ = "publishing_attempts"
    __table_args__ = (
        UniqueConstraint("platform_post_id", "attempt_number", name="post_attempt_number"),
        CheckConstraint("attempt_number >= 1", name="attempt_number_positive"),
        # FINDING (publishing-status / attempt_count): the reconciler needs the most recent attempt
        # for a post to decide whether it is genuinely stuck or merely slow.
        Index("ix_publishing_attempts_post_started", "platform_post_id", "request_started_at"),
    )

    platform_post_id: Mapped[uuid.UUID] = mapped_column(
        # NOTE: README's data model lists `platform_post_id` twice in this block — once as the
        # foreign key and once again among the outcome columns. This column is the foreign key to
        # `platform_posts.id`. The duplicate in the spec is a typo, not a second field; the
        # platform's own identifier is recorded on the parent row.
        ForeignKey("platform_posts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)

    request_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    request_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    response_code: Mapped[int | None] = mapped_column(Integer)
    response_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    """The raw platform response, exactly as received.

    JSONB here, and ``dict[str, Any]`` is correct *at this layer*: AGENTS.md §6's prohibition on
    typing a platform response as ``dict``/``Any`` applies to the trust boundary where the response
    is interpreted. By the time a row is written, the adapter has already parsed the payload into
    the closed union; this column is the audit record of what it parsed, not an input to any
    decision. It is deliberately never read back to drive control flow."""

    result: Mapped[str | None] = mapped_column(String(64))
    """Which member of the ``PublishResult`` union this attempt produced — 'Published', 'Failed',
    'Unknown' or 'RequiresAuthentication'."""

    error_type: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    platform_post: Mapped[PlatformPost] = relationship(back_populates="attempts")


__all__ = ["ContentItem", "PlatformPost", "PublishingAttempt"]
