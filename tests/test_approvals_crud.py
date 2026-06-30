from tests.conftest import SAMPLE_PAYLOAD, auth_headers, base_url


async def test_create_returns_201_and_pending(client):
    resp = await client.post(base_url(), json=SAMPLE_PAYLOAD, headers=auth_headers())
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"].startswith("req_")
    assert body["status"] == "pending"
    assert body["sourceType"] == "publication"
    assert body["sourceId"] == "pub_123"
    assert body["reviewerUserIds"] == ["usr_1", "usr_2"]
    assert body["workspaceId"] == "ws_alpha"
    assert body["createdByUserId"] == "usr_admin"


async def test_get_returns_created_request(client):
    created = await client.post(
        base_url(), json=SAMPLE_PAYLOAD, headers=auth_headers()
    )
    request_id = created.json()["id"]

    resp = await client.get(f"{base_url()}/{request_id}", headers=auth_headers())
    assert resp.status_code == 200
    assert resp.json()["id"] == request_id


async def test_list_returns_items_and_total(client):
    for i in range(3):
        payload = {**SAMPLE_PAYLOAD, "sourceId": f"pub_{i}"}
        await client.post(base_url(), json=payload, headers=auth_headers())

    resp = await client.get(base_url(), headers=auth_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 3
    assert body["limit"] == 50
    assert body["offset"] == 0


async def test_list_status_filter(client):
    created = await client.post(
        base_url(), json=SAMPLE_PAYLOAD, headers=auth_headers()
    )
    request_id = created.json()["id"]
    await client.post(
        f"{base_url()}/{request_id}/approve", json={}, headers=auth_headers()
    )

    pending = await client.get(
        f"{base_url()}?status=pending", headers=auth_headers()
    )
    approved = await client.get(
        f"{base_url()}?status=approved", headers=auth_headers()
    )
    assert pending.json()["total"] == 0
    assert approved.json()["total"] == 1


async def test_get_unknown_returns_404(client):
    resp = await client.get(f"{base_url()}/req_does_not_exist", headers=auth_headers())
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


async def test_unknown_field_rejected_422(client):
    payload = {**SAMPLE_PAYLOAD, "unexpected": "x"}
    resp = await client.post(base_url(), json=payload, headers=auth_headers())
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


async def test_invalid_source_type_rejected_422(client):
    payload = {**SAMPLE_PAYLOAD, "sourceType": "banana"}
    resp = await client.post(base_url(), json=payload, headers=auth_headers())
    assert resp.status_code == 422
