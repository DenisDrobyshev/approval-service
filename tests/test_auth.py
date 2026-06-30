from tests.conftest import SAMPLE_PAYLOAD, auth_headers, base_url


async def test_missing_auth_headers_returns_401(client):
    resp = await client.post(base_url(), json=SAMPLE_PAYLOAD)
    assert resp.status_code == 401


async def test_workspace_mismatch_returns_403(client):
    # Credentials say ws_alpha but the path targets ws_beta.
    resp = await client.post(
        base_url("ws_beta"),
        json=SAMPLE_PAYLOAD,
        headers=auth_headers(workspace="ws_alpha"),
    )
    assert resp.status_code == 403


async def test_missing_scope_returns_403(client):
    # Caller can read but not create.
    resp = await client.post(
        base_url(),
        json=SAMPLE_PAYLOAD,
        headers=auth_headers(scopes=("approval:read",)),
    )
    assert resp.status_code == 403


async def test_read_scope_allows_listing(client):
    resp = await client.get(
        base_url(), headers=auth_headers(scopes=("approval:read",))
    )
    assert resp.status_code == 200
