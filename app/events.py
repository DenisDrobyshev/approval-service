"""Building blocks for domain events written to the outbox.

Events carry identifiers and status only. Free-text fields that could carry
pasted secrets (title / comment / reason) are passed through the redactor;
``description`` and raw provider data are never included. This keeps the
event stream safe to fan out to other services.
"""

from __future__ import annotations

from .enums import EventType, RequestStatus
from .models import ApprovalRequest
from .security import redact_text

_STATUS_TO_EVENT = {
    RequestStatus.approved: EventType.approved,
    RequestStatus.rejected: EventType.rejected,
    RequestStatus.cancelled: EventType.cancelled,
}


def event_type_for_status(new_status: RequestStatus) -> EventType:
    return _STATUS_TO_EVENT[new_status]


def build_event_payload(req: ApprovalRequest) -> dict:
    """Curated, redacted snapshot safe to publish downstream."""
    return {
        "id": req.id,
        "workspaceId": req.workspace_id,
        "sourceType": req.source_type,
        "sourceId": req.source_id,
        "title": redact_text(req.title),
        "status": req.status,
        "reviewerUserIds": list(req.reviewer_user_ids or []),
        "decidedByUserId": req.decided_by_user_id,
        "decidedAt": req.decided_at.isoformat() if req.decided_at else None,
        "decisionComment": redact_text(req.decision_comment),
        "decisionReason": redact_text(req.decision_reason),
        "createdByUserId": req.created_by_user_id,
        "createdAt": req.created_at.isoformat() if req.created_at else None,
    }
