from tests.conftest import SAMPLE_PAYLOAD, auth_headers, base_url


async def _create(client) -> str:
    resp = await client.post(base_url(), json=SAMPLE_PAYLOAD, headers=auth_headers())
    return resp.json()["id"]


async def test_approve_pending(client):
    rid = await _create(client)
    resp = await client.post(
        f"{base_url()}/{rid}/approve",
        json={"comment": "Approved"},
        headers=auth_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "approved"
    assert body["decisionComment"] == "Approved"
    assert body["decidedByUserId"] == "usr_admin"
    assert body["decidedAt"] is not None


async def test_reject_pending(client):
    rid = await _create(client)
    resp = await client.post(
        f"{base_url()}/{rid}/reject",
        json={"reason": "Brand tone is wrong"},
        headers=auth_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"
    assert resp.json()["decisionReason"] == "Brand tone is wrong"


async def test_cancel_pending(client):
    rid = await _create(client)
    resp = await client.post(
        f"{base_url()}/{rid}/cancel",
        json={"reason": "Draft was removed"},
        headers=auth_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


async def test_cannot_redecide_after_final(client):
    rid = await _create(client)
    await client.post(f"{base_url()}/{rid}/approve", json={}, headers=auth_headers())

    # Approving again, rejecting and cancelling are all conflicts now.
    for action, payload in (
        ("approve", {}),
        ("reject", {"reason": "too late"}),
        ("cancel", {}),
    ):
        resp = await client.post(
            f"{base_url()}/{rid}/{action}", json=payload, headers=auth_headers()
        )
        assert resp.status_code == 409, action
        assert resp.json()["error"]["code"] == "conflict"


async def test_reject_requires_reason(client):
    rid = await _create(client)
    resp = await client.post(
        f"{base_url()}/{rid}/reject", json={}, headers=auth_headers()
    )
    assert resp.status_code == 422


async def test_decision_on_unknown_request_404(client):
    resp = await client.post(
        f"{base_url()}/req_missing/approve", json={}, headers=auth_headers()
    )
    assert resp.status_code == 404


async def test_cancel_requires_cancel_scope(client):
    rid = await _create(client)
    # decide scope does not grant cancel
    resp = await client.post(
        f"{base_url()}/{rid}/cancel",
        json={},
        headers=auth_headers(scopes=("approval:decide",)),
    )
    assert resp.status_code == 403
