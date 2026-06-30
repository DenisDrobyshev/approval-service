"""SQLAlchemy ORM models.

The service owns four tables:

* ``approval_requests`` - the aggregate the API operates on.
* ``idempotency_keys``  - dedup store so a retried request is a no-op.
* ``audit_log``         - immutable trail of who changed what.
* ``outbox_events``     - transactional outbox for downstream integration.

Everything is scoped by ``workspace_id`` so one tenant can never read
another tenant's data.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base
from .enums import RequestStatus


def _uuid_hex() -> str:
    return uuid.uuid4().hex


def _request_id() -> str:
    return f"req_{uuid.uuid4().hex}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=_request_id)
    workspace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_user_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=RequestStatus.pending.value, index=True
    )

    decision_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_by_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    __table_args__ = (
        Index("ix_approval_requests_ws_created", "workspace_id", "created_at"),
        Index("ix_approval_requests_ws_status", "workspace_id", "status"),
    )


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=_uuid_hex)
    workspace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)

    # Hash of method + path + body so a reused key with a different payload
    # can be rejected instead of silently returning the wrong response.
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)

    response_status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[dict] = mapped_column(JSON, nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(40), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (
        UniqueConstraint("workspace_id", "idempotency_key", name="uq_idempotency_ws_key"),
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=_uuid_hex)
    workspace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    approval_request_id: Mapped[str] = mapped_column(
        String(40), nullable=False, index=True
    )
    actor_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=_uuid_hex)
    workspace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    aggregate_type: Mapped[str] = mapped_column(
        String(40), nullable=False, default="approval_request"
    )
    aggregate_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    # NULL until a relay/publisher process ships the event downstream.
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
