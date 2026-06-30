from tests.conftest import SAMPLE_PAYLOAD, auth_headers, base_url


async def test_other_workspace_cannot_read_request(client):
    created = await client.post(
        base_url("ws_alpha"),
        json=SAMPLE_PAYLOAD,
        headers=auth_headers(workspace="ws_alpha"),
    )
    rid = created.json()["id"]

    # ws_beta caller, ws_beta path, but the id belongs to ws_alpha -> 404.
    resp = await client.get(
        f"{base_url('ws_beta')}/{rid}",
        headers=auth_headers(workspace="ws_beta"),
    )
    assert resp.status_code == 404


async def test_other_workspace_listing_is_empty(client):
    await client.post(
        base_url("ws_alpha"),
        json=SAMPLE_PAYLOAD,
        headers=auth_headers(workspace="ws_alpha"),
    )
    resp = await client.get(
        base_url("ws_beta"), headers=auth_headers(workspace="ws_beta")
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


async def test_other_workspace_cannot_decide_request(client):
    created = await client.post(
        base_url("ws_alpha"),
        json=SAMPLE_PAYLOAD,
        headers=auth_headers(workspace="ws_alpha"),
    )
    rid = created.json()["id"]

    resp = await client.post(
        f"{base_url('ws_beta')}/{rid}/approve",
        json={},
        headers=auth_headers(workspace="ws_beta"),
    )
    assert resp.status_code == 404
