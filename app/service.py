"""Business logic: state machine, idempotency, audit trail and outbox.

Every successful mutation is atomic - the aggregate change, its audit entry,
its outbox event and (when supplied) the idempotency record all commit in a
single transaction, or none of them do.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import Principal
from .enums import AuditAction, EventType, RequestStatus, SourceType
from .errors import ConflictError, IdempotencyConflictError, NotFoundError
from .events import build_event_payload, event_type_for_status
from .models import ApprovalRequest, AuditLog, IdempotencyKey, OutboxEvent, utcnow
from .schemas import (
    ApprovalRequestCreate,
    ApproveBody,
    CancelBody,
    RejectBody,
    serialize_request,
)
from .security import redact_obj


# --------------------------------------------------------------------------- #
# Idempotency
# --------------------------------------------------------------------------- #
def request_fingerprint(method: str, path: str, body: dict[str, Any]) -> str:
    """Stable hash of an inbound mutation, used to detect key reuse."""
    canonical = json.dumps(
        {"method": method, "path": path, "body": body},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def _load_idempotency(
    db: AsyncSession, workspace_id: str, key: str
) -> IdempotencyKey | None:
    return await db.scalar(
        select(IdempotencyKey).where(
            IdempotencyKey.workspace_id == workspace_id,
            IdempotencyKey.idempotency_key == key,
        )
    )


async def _replay_if_seen(
    db: AsyncSession, workspace_id: str, key: str | None, fingerprint: str
) -> tuple[int, dict] | None:
    if not key:
        return None
    existing = await _load_idempotency(db, workspace_id, key)
    if existing is None:
        return None
    if existing.request_fingerprint != fingerprint:
        raise IdempotencyConflictError(
            "Idempotency-Key was already used with a different request payload"
        )
    return existing.response_status_code, existing.response_body


async def _commit_idempotent(
    db: AsyncSession,
    workspace_id: str,
    key: str | None,
    fingerprint: str,
    status_code: int,
    body: dict,
    target_id: str | None,
) -> tuple[int, dict]:
    """Commit the unit of work, recording the idempotency result if a key was
    supplied. A concurrent duplicate (unique-constraint violation) loses the
    race, rolls back and replays the winner's stored response."""
    if key:
        db.add(
            IdempotencyKey(
                workspace_id=workspace_id,
                idempotency_key=key,
                request_fingerprint=fingerprint,
                response_status_code=status_code,
                response_body=body,
                target_id=target_id,
            )
        )
    try:
        await db.commit()
        return status_code, body
    except IntegrityError:
        await db.rollback()
        if key:
            existing = await _load_idempotency(db, workspace_id, key)
            if existing is not None:
                if existing.request_fingerprint != fingerprint:
                    raise IdempotencyConflictError(
                        "Idempotency-Key was already used with a different request payload"
                    ) from None
                return existing.response_status_code, existing.response_body
        raise


# --------------------------------------------------------------------------- #
# Audit + outbox helpers
# --------------------------------------------------------------------------- #
def _record_audit(
    db: AsyncSession,
    req: ApprovalRequest,
    actor_user_id: str,
    action: AuditAction,
    from_status: RequestStatus | None,
    to_status: RequestStatus,
    details: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            workspace_id=req.workspace_id,
            approval_request_id=req.id,
            actor_user_id=actor_user_id,
            action=action.value,
            from_status=from_status.value if from_status else None,
            to_status=to_status.value,
            details=redact_obj(details or {}),
        )
    )


def _emit_event(db: AsyncSession, req: ApprovalRequest, event_type: EventType) -> None:
    db.add(
        OutboxEvent(
            workspace_id=req.workspace_id,
            aggregate_type="approval_request",
            aggregate_id=req.id,
            event_type=event_type.value,
            payload=build_event_payload(req),
        )
    )


# --------------------------------------------------------------------------- #
# Reads
# --------------------------------------------------------------------------- #
async def get_request(
    db: AsyncSession, workspace_id: str, request_id: str
) -> ApprovalRequest:
    req = await db.scalar(
        select(ApprovalRequest).where(
            ApprovalRequest.id == request_id,
            ApprovalRequest.workspace_id == workspace_id,
        )
    )
    if req is None:
        raise NotFoundError("Approval request not found")
    return req


async def list_requests(
    db: AsyncSession,
    workspace_id: str,
    status_filter: RequestStatus | None,
    limit: int,
    offset: int,
) -> tuple[list[ApprovalRequest], int]:
    conditions = [ApprovalRequest.workspace_id == workspace_id]
    if status_filter is not None:
        conditions.append(ApprovalRequest.status == status_filter.value)

    total = await db.scalar(
        select(func.count()).select_from(ApprovalRequest).where(*conditions)
    )
    rows = (
        await db.scalars(
            select(ApprovalRequest)
            .where(*conditions)
            .order_by(ApprovalRequest.created_at.desc(), ApprovalRequest.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return list(rows), int(total or 0)


# --------------------------------------------------------------------------- #
# Mutations
# --------------------------------------------------------------------------- #
async def create_request(
    db: AsyncSession,
    principal: Principal,
    payload: ApprovalRequestCreate,
    idempotency_key: str | None,
    fingerprint: str,
) -> tuple[int, dict]:
    replay = await _replay_if_seen(
        db, principal.workspace_id, idempotency_key, fingerprint
    )
    if replay is not None:
        return replay

    req = ApprovalRequest(
        workspace_id=principal.workspace_id,
        source_type=SourceType(payload.source_type).value,
        source_id=payload.source_id,
        title=payload.title,
        description=payload.description,
        reviewer_user_ids=list(payload.reviewer_user_ids),
        status=RequestStatus.pending.value,
        created_by_user_id=principal.user_id,
    )
    db.add(req)
    await db.flush()

    _record_audit(
        db,
        req,
        principal.user_id,
        AuditAction.created,
        from_status=None,
        to_status=RequestStatus.pending,
    )
    _emit_event(db, req, EventType.created)

    body = serialize_request(req)
    return await _commit_idempotent(
        db, principal.workspace_id, idempotency_key, fingerprint, 201, body, req.id
    )


async def _apply_decision(
    db: AsyncSession,
    principal: Principal,
    workspace_id: str,
    request_id: str,
    new_status: RequestStatus,
    audit_action: AuditAction,
    *,
    comment: str | None,
    reason: str | None,
    idempotency_key: str | None,
    fingerprint: str,
) -> tuple[int, dict]:
    replay = await _replay_if_seen(db, workspace_id, idempotency_key, fingerprint)
    if replay is not None:
        return replay

    req = await get_request(db, workspace_id, request_id)

    current = RequestStatus(req.status)
    if current.is_final:
        raise ConflictError(
            f"Request is already in final state '{current.value}' and cannot be changed"
        )

    req.status = new_status.value
    req.decided_by_user_id = principal.user_id
    req.decided_at = utcnow()
    if comment is not None:
        req.decision_comment = comment
    if reason is not None:
        req.decision_reason = reason
    req.updated_at = utcnow()
    await db.flush()

    details: dict[str, Any] = {}
    if comment is not None:
        details["comment"] = comment
    if reason is not None:
        details["reason"] = reason

    _record_audit(
        db, req, principal.user_id, audit_action, current, new_status, details
    )
    _emit_event(db, req, event_type_for_status(new_status))

    body = serialize_request(req)
    return await _commit_idempotent(
        db, workspace_id, idempotency_key, fingerprint, 200, body, req.id
    )


async def approve_request(
    db: AsyncSession,
    principal: Principal,
    workspace_id: str,
    request_id: str,
    body: ApproveBody,
    idempotency_key: str | None,
    fingerprint: str,
) -> tuple[int, dict]:
    return await _apply_decision(
        db,
        principal,
        workspace_id,
        request_id,
        RequestStatus.approved,
        AuditAction.approved,
        comment=body.comment,
        reason=None,
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
    )


async def reject_request(
    db: AsyncSession,
    principal: Principal,
    workspace_id: str,
    request_id: str,
    body: RejectBody,
    idempotency_key: str | None,
    fingerprint: str,
) -> tuple[int, dict]:
    return await _apply_decision(
        db,
        principal,
        workspace_id,
        request_id,
        RequestStatus.rejected,
        AuditAction.rejected,
        comment=None,
        reason=body.reason,
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
    )


async def cancel_request(
    db: AsyncSession,
    principal: Principal,
    workspace_id: str,
    request_id: str,
    body: CancelBody,
    idempotency_key: str | None,
    fingerprint: str,
) -> tuple[int, dict]:
    return await _apply_decision(
        db,
        principal,
        workspace_id,
        request_id,
        RequestStatus.cancelled,
        AuditAction.cancelled,
        comment=None,
        reason=body.reason,
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
    )
