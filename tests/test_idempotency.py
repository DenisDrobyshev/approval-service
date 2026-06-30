from tests.conftest import SAMPLE_PAYLOAD, auth_headers, base_url


async def test_repeated_create_with_same_key_is_deduped(client):
    headers = {**auth_headers(), "Idempotency-Key": "key-create-1"}

    first = await client.post(base_url(), json=SAMPLE_PAYLOAD, headers=headers)
    second = await client.post(base_url(), json=SAMPLE_PAYLOAD, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 201
    # Same resource returned, and only one was actually created.
    assert first.json()["id"] == second.json()["id"]

    listing = await client.get(base_url(), headers=auth_headers())
    assert listing.json()["total"] == 1


async def test_same_key_different_payload_conflicts(client):
    headers = {**auth_headers(), "Idempotency-Key": "key-create-2"}
    await client.post(base_url(), json=SAMPLE_PAYLOAD, headers=headers)

    other = {**SAMPLE_PAYLOAD, "title": "A different title"}
    resp = await client.post(base_url(), json=other, headers=headers)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "idempotency_key_reuse"


async def test_create_without_key_is_not_deduped(client):
    await client.post(base_url(), json=SAMPLE_PAYLOAD, headers=auth_headers())
    await client.post(base_url(), json=SAMPLE_PAYLOAD, headers=auth_headers())
    listing = await client.get(base_url(), headers=auth_headers())
    assert listing.json()["total"] == 2


async def test_idempotent_approve_replays_without_conflict(client):
    created = await client.post(
        base_url(), json=SAMPLE_PAYLOAD, headers=auth_headers()
    )
    rid = created.json()["id"]
    headers = {**auth_headers(), "Idempotency-Key": "key-approve-1"}

    first = await client.post(
        f"{base_url()}/{rid}/approve", json={"comment": "ok"}, headers=headers
    )
    second = await client.post(
        f"{base_url()}/{rid}/approve", json={"comment": "ok"}, headers=headers
    )
    assert first.status_code == 200
    # The retry replays the stored 200 rather than hitting the state machine 409.
    assert second.status_code == 200
    assert first.json() == second.json()


async def test_idempotency_is_scoped_per_workspace(client):
    # Same key in two workspaces must not collide.
    h1 = {
        **auth_headers(workspace="ws_alpha"),
        "Idempotency-Key": "shared-key",
    }
    h2 = {
        **auth_headers(workspace="ws_beta"),
        "Idempotency-Key": "shared-key",
    }
    r1 = await client.post(base_url("ws_alpha"), json=SAMPLE_PAYLOAD, headers=h1)
    r2 = await client.post(base_url("ws_beta"), json=SAMPLE_PAYLOAD, headers=h2)
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] != r2.json()["id"]
