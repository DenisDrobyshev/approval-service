"""HTTP routes for the approval-request resource."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Path, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from .. import service
from ..auth import Principal, require
from ..database import get_db
from ..enums import Action, RequestStatus
from ..schemas import (
    ApprovalRequestCreate,
    ApprovalRequestList,
    ApprovalRequestRead,
    ApproveBody,
    CancelBody,
    RejectBody,
    serialize_request,
)

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/approval-requests",
    tags=["approval-requests"],
)

IdempotencyKey = Header(default=None, alias="Idempotency-Key")


@router.post("", status_code=201)
async def create_approval_request(
    request: Request,
    payload: ApprovalRequestCreate,
    workspace_id: str = Path(...),
    idempotency_key: str | None = IdempotencyKey,
    principal: Principal = Depends(require(Action.create)),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    fingerprint = service.request_fingerprint(
        "POST", request.url.path, payload.model_dump(mode="json")
    )
    status_code, body = await service.create_request(
        db, principal, payload, idempotency_key, fingerprint
    )
    return JSONResponse(status_code=status_code, content=body)


@router.get("", response_model=ApprovalRequestList)
async def list_approval_requests(
    workspace_id: str = Path(...),
    status: RequestStatus | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(require(Action.read)),
    db: AsyncSession = Depends(get_db),
) -> ApprovalRequestList:
    rows, total = await service.list_requests(
        db, workspace_id, status, limit, offset
    )
    return ApprovalRequestList(
        items=[ApprovalRequestRead.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{request_id}", response_model=ApprovalRequestRead)
async def get_approval_request(
    workspace_id: str = Path(...),
    request_id: str = Path(...),
    principal: Principal = Depends(require(Action.read)),
    db: AsyncSession = Depends(get_db),
) -> ApprovalRequestRead:
    req = await service.get_request(db, workspace_id, request_id)
    return ApprovalRequestRead.model_validate(req)


@router.post("/{request_id}/approve")
async def approve_approval_request(
    request: Request,
    body: ApproveBody | None = None,
    workspace_id: str = Path(...),
    request_id: str = Path(...),
    idempotency_key: str | None = IdempotencyKey,
    principal: Principal = Depends(require(Action.decide)),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    body = body or ApproveBody()
    fingerprint = service.request_fingerprint(
        "POST", request.url.path, body.model_dump(mode="json")
    )
    status_code, resp = await service.approve_request(
        db, principal, workspace_id, request_id, body, idempotency_key, fingerprint
    )
    return JSONResponse(status_code=status_code, content=resp)


@router.post("/{request_id}/reject")
async def reject_approval_request(
    request: Request,
    body: RejectBody,
    workspace_id: str = Path(...),
    request_id: str = Path(...),
    idempotency_key: str | None = IdempotencyKey,
    principal: Principal = Depends(require(Action.decide)),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    fingerprint = service.request_fingerprint(
        "POST", request.url.path, body.model_dump(mode="json")
    )
    status_code, resp = await service.reject_request(
        db, principal, workspace_id, request_id, body, idempotency_key, fingerprint
    )
    return JSONResponse(status_code=status_code, content=resp)


@router.post("/{request_id}/cancel")
async def cancel_approval_request(
    request: Request,
    body: CancelBody | None = None,
    workspace_id: str = Path(...),
    request_id: str = Path(...),
    idempotency_key: str | None = IdempotencyKey,
    principal: Principal = Depends(require(Action.cancel)),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    body = body or CancelBody()
    fingerprint = service.request_fingerprint(
        "POST", request.url.path, body.model_dump(mode="json")
    )
    status_code, resp = await service.cancel_request(
        db, principal, workspace_id, request_id, body, idempotency_key, fingerprint
    )
    return JSONResponse(status_code=status_code, content=resp)
