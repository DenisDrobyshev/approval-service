"""Domain enumerations shared across the service."""

from __future__ import annotations

from enum import Enum


class SourceType(str, Enum):
    """Type of the external entity an approval request points at."""

    publication = "publication"
    scenario = "scenario"
    edit = "edit"
    external = "external"


class RequestStatus(str, Enum):
    """Lifecycle status of an approval request."""

    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"

    @property
    def is_final(self) -> bool:
        """Final states are terminal: a request cannot leave them."""
        return self in _FINAL_STATUSES


_FINAL_STATUSES = frozenset(
    {RequestStatus.approved, RequestStatus.rejected, RequestStatus.cancelled}
)


class Action(str, Enum):
    """Authorization scopes carried by the auth context."""

    read = "approval:read"
    create = "approval:create"
    decide = "approval:decide"
    cancel = "approval:cancel"


class AuditAction(str, Enum):
    """What happened, as recorded in the audit trail."""

    created = "created"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"


class EventType(str, Enum):
    """Domain events emitted through the transactional outbox."""

    created = "approval_request.created"
    approved = "approval_request.approved"
    rejected = "approval_request.rejected"
    cancelled = "approval_request.cancelled"
