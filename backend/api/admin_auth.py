"""Bearer-token gating for admin-only API routes.

The admin surface is internal-only — never linked from the public UI — but the
backend container is on a shared docker network behind an nginx proxy, so a
typo in nginx or a future routing change must NOT silently expose it. The
dependency below refuses every request unless WC26_ADMIN_TOKEN is set AND the
caller presents a matching `Authorization: Bearer <token>` header (or the
short-form `X-Admin-Token`).

Safe-by-default: if the env var is unset, every admin call returns 503. That
forces the operator to configure a token before the surface is reachable, so a
half-set-up box can't leak the harvester controls.
"""
from __future__ import annotations

import hmac
import os

from fastapi import Depends, Header, HTTPException, status


def _expected_token() -> str:
    return (os.getenv("WC26_ADMIN_TOKEN") or "").strip()


def admin_required(
    authorization: str | None = Header(default=None),
    x_admin_token: str | None = Header(default=None),
) -> None:
    expected = _expected_token()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin token not configured on the server (set WC26_ADMIN_TOKEN).",
        )

    presented = x_admin_token or ""
    if not presented and authorization:
        # "Bearer <token>" — case-insensitive on the scheme.
        parts = authorization.split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            presented = parts[1].strip()

    if not presented or not hmac.compare_digest(presented, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


AdminGate = Depends(admin_required)
