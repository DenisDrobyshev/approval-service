"""Auth stub.

For local runs the caller supplies its identity through headers instead of a
real token issuer:

* ``X-Workspace-Id`` - the workspace the caller acts in.
* ``X-User-Id``      - the acting user.
* ``X-Scopes``       - granted actions, comma- or space-separated, e.g.
                       ``approval:read approval:create``.

Two checks protect every workspace-scoped route:

1. ``X-Workspace-Id`` must equal the ``{workspace_id}`` in the path
   (cross-workspace access is rejected before any data is touched).
2. The route's required scope must be present in ``X-Scopes``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Path, status

from .enums import Action

_SCOPE_SPLIT = re.compile(r"[,\s]+")


@dataclass(frozen=True)
class Principal:
    workspace_id: str
    user_id: str
    scopes: frozenset[str]

    def has_scope(self, action: Action) -> bool:
        return action.value in self.scopes


def _parse_scopes(raw: str | None) -> frozenset[str]:
    if not raw:
        return frozenset()
    return frozenset(part for part in _SCOPE_SPLIT.split(raw.strip()) if part)


async def get_principal(
    x_workspace_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
    x_scopes: str | None = Header(default=None),
) -> Principal:
    if not x_workspace_id or not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication context (X-Workspace-Id, X-User-Id)",
        )
    return Principal(
        workspace_id=x_workspace_id,
        user_id=x_user_id,
        scopes=_parse_scopes(x_scopes),
    )


def require(action: Action):
    """Build a dependency that enforces workspace match + a required scope."""

    async def _checker(
        workspace_id: str = Path(...),
        principal: Principal = Depends(get_principal),
    ) -> Principal:
        if principal.workspace_id != workspace_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Workspace mismatch between credentials and path",
            )
        if not principal.has_scope(action):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required scope: {action.value}",
            )
        return principal

    return _checker
