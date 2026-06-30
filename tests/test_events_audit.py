"""Audit-trail and transactional-outbox behaviour."""

from sqlalchemy import select

from app.database import SessionLocal
from app.models import AuditLog, OutboxEvent
from tests.conftest import SAMPLE_PAYLOAD, auth_headers, base_url


async def _events_for(workspace: str) -> list[OutboxEvent]:
    async with SessionLocal() as db:
        rows = await db.scalars(
            select(OutboxEvent).where(OutboxEvent.workspace_id == workspace)
        )
        return list(rows)


async def _audit_for(request_id: str) -> list[AuditLog]:
    async with SessionLocal() as db:
        rows = await db.scalars(
            select(AuditLog).where(AuditLog.approval_request_id == request_id)
        )
        return list(rows)


async def test_create_emits_created_event(client):
    created = await client.post(
        base_url(), json=SAMPLE_PAYLOAD, headers=auth_headers()
    )
    rid = created.json()["id"]

    events = await _events_for("ws_alpha")
    assert len(events) == 1
    evt = events[0]
    assert evt.event_type == "approval_request.created"
    assert evt.aggregate_id == rid
    assert evt.published_at is None  # not yet relayed
    # Curated payload: identifiers and status only, no description / raw data.
    assert evt.payload["status"] == "pending"
    assert "description" not in evt.payload


async def test_decision_emits_event_and_audit(client):
    created = await client.post(
        base_url(), json=SAMPLE_PAYLOAD, headers=auth_headers()
    )
    rid = created.json()["id"]
    await client.post(
        f"{base_url()}/{rid}/approve",
        json={"comment": "Approved"},
        headers=auth_headers(),
    )

    events = await _events_for("ws_alpha")
    types = sorted(e.event_type for e in events)
    assert types == ["approval_request.approved", "approval_request.created"]

    audit = await _audit_for(rid)
    actions = sorted(a.action for a in audit)
    assert actions == ["approved", "created"]
    approved_entry = next(a for a in audit if a.action == "approved")
    assert approved_entry.from_status == "pending"
    assert approved_entry.to_status == "approved"
    assert approved_entry.actor_user_id == "usr_admin"


async def test_event_title_is_redacted(client):
    payload = {**SAMPLE_PAYLOAD, "title": "ping me at leak@corp.com"}
    await client.post(base_url(), json=payload, headers=auth_headers())

    events = await _events_for("ws_alpha")
    assert "leak@corp.com" not in events[0].payload["title"]
    assert "[REDACTED_EMAIL]" in events[0].payload["title"]


async def test_failed_decision_writes_no_event(client):
    created = await client.post(
        base_url(), json=SAMPLE_PAYLOAD, headers=auth_headers()
    )
    rid = created.json()["id"]
    await client.post(f"{base_url()}/{rid}/approve", json={}, headers=auth_headers())

    # A second (conflicting) approve must not add another event.
    await client.post(f"{base_url()}/{rid}/approve", json={}, headers=auth_headers())

    events = await _events_for("ws_alpha")
    assert len(events) == 2  # created + approved, nothing from the conflict
