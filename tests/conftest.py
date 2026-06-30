"""Shared pytest fixtures.

A file-based SQLite database is used so the suite needs no external
infrastructure. The DATABASE_URL is set *before* the app is imported so the
application engine points at the test database.
"""

from __future__ import annotations

import os

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_approval.db"
os.environ["AUTO_CREATE_TABLES"] = "false"

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

DEFAULT_SCOPES = (
    "approval:read",
    "approval:create",
    "approval:decide",
    "approval:cancel",
)


def auth_headers(
    workspace: str = "ws_alpha",
    user: str = "usr_admin",
    scopes: tuple[str, ...] = DEFAULT_SCOPES,
) -> dict[str, str]:
    return {
        "X-Workspace-Id": workspace,
        "X-User-Id": user,
        "X-Scopes": " ".join(scopes),
    }


@pytest_asyncio.fixture
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client(_schema):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def base_url(workspace: str = "ws_alpha") -> str:
    return f"/api/v1/workspaces/{workspace}/approval-requests"


SAMPLE_PAYLOAD = {
    "sourceType": "publication",
    "sourceId": "pub_123",
    "title": "Instagram reel draft",
    "description": "Needs final approval",
    "reviewerUserIds": ["usr_1", "usr_2"],
}
