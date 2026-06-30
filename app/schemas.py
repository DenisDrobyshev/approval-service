"""Pydantic request/response models.

The public API speaks camelCase (``sourceType``, ``reviewerUserIds``) to match
the example in the task; internally everything stays snake_case. The
``CamelModel`` base wires up the alias generator and lets us populate models
from ORM objects.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from .enums import RequestStatus, SourceType


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class ApprovalRequestCreate(CamelModel):
    model_config = ConfigDict(extra="forbid")

    source_type: SourceType
    source_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=512)
    description: str | None = Field(default=None, max_length=4000)
    reviewer_user_ids: list[str] = Field(default_factory=list, max_length=100)


class ApproveBody(CamelModel):
    model_config = ConfigDict(extra="forbid")

    comment: str | None = Field(default=None, max_length=2000)


class RejectBody(CamelModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=2000)


class CancelBody(CamelModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=2000)


class ApprovalRequestRead(CamelModel):
    id: str
    workspace_id: str
    source_type: SourceType
    source_id: str
    title: str
    description: str | None
    reviewer_user_ids: list[str]
    status: RequestStatus
    decision_comment: str | None
    decision_reason: str | None
    decided_by_user_id: str | None
    decided_at: datetime | None
    created_by_user_id: str
    created_at: datetime
    updated_at: datetime


class ApprovalRequestList(CamelModel):
    items: list[ApprovalRequestRead]
    total: int
    limit: int
    offset: int


class HealthResponse(CamelModel):
    status: str
    service: str
    version: str


def serialize_request(obj) -> dict:
    """Serialize an ApprovalRequest ORM row to a camelCase JSON dict."""
    return ApprovalRequestRead.model_validate(obj).model_dump(
        mode="json", by_alias=True
    )
