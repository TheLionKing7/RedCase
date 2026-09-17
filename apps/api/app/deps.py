"""Auth + tenant/user context resolution (Tasks 1.4/1.5).

OWNER RULING 3 (2026-09-16): Supabase Auth email magic link -> FastAPI verifies
the Supabase JWT with the shared JWT secret -> user_ref + tenant_id come from
the claims and feed the RLS session vars and query_audit. No standalone
API-key auth.

Claim contract (provisioned on the Supabase user record, Phase 2):
  sub                          -> user_ref
  app_metadata.tenant_id       -> tenant (uuid of the tenants row)
A token missing either claim is rejected — tenant scoping is never guessed.
"""

import base64
import hashlib
import hmac
import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass

import asyncpg
from fastapi import HTTPException, Request, status

from app.config import Settings


@dataclass(frozen=True)
class TenantContext:
    tenant_id: str
    user_ref: str
    db: asyncpg.Connection  # connection with RLS GUCs set inside a transaction


class JwtError(ValueError):
    pass


def _b64url_decode(seg: str) -> bytes:
    return base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4))


def verify_supabase_jwt(token: str, secret: str) -> dict:
    """Verify an HS256 Supabase JWT (shared-secret config) and return claims.

    Checks signature, exp. Raises JwtError on any problem — never returns
    unverified claims."""
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
    except ValueError as exc:
        raise JwtError("malformed token") from exc
    expected = hmac.new(
        secret.encode(),
        f"{header_b64}.{payload_b64}".encode(),
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(expected, _b64url_decode(sig_b64)):
        raise JwtError("bad signature")
    header = json.loads(_b64url_decode(header_b64))
    if header.get("alg") != "HS256":
        raise JwtError(f"unsupported alg {header.get('alg')!r}")
    claims = json.loads(_b64url_decode(payload_b64))
    exp = claims.get("exp")
    if not isinstance(exp, (int, float)) or exp < time.time():
        raise JwtError("expired token")
    return claims


async def get_tenant_context(
    request: Request,
) -> AsyncIterator[TenantContext]:
    """FastAPI dependency: verify Bearer JWT, open an RLS-scoped connection.

    Settings come from ``app.state.settings`` (the instance create_app was
    built with), NOT ``get_settings()`` — the lru_cached factory re-reads the
    real .env, which would silently ignore per-app test settings.

    The connection is released when the response completes; the transaction
    commits on success / rolls back on exception (including audit-write
    failure — HALT contract, HANDOFF.md 5)."""
    settings: Settings = request.app.state.settings
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail="Missing Bearer token (Supabase JWT)"
        )
    if not settings.supabase_jwt_secret:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="supabase_jwt_secret not provisioned",
        )
    try:
        claims = verify_supabase_jwt(
            auth.removeprefix("Bearer ").strip(),
            settings.supabase_jwt_secret.get_secret_value(),
        )
    except JwtError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    user_ref = claims.get("sub")
    tenant_id = (claims.get("app_metadata") or {}).get("tenant_id")
    if not user_ref or not tenant_id:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="token lacks sub or app_metadata.tenant_id — user provisioning"
            " must set the tenant claim (Phase 2)",
        )

    pool: asyncpg.Pool | None = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail="database not configured"
        )

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.tenant_id', $1, true)", str(tenant_id)
            )
            await conn.execute("SELECT set_config('app.user_ref', $1, true)", str(user_ref))
            yield TenantContext(
                tenant_id=str(tenant_id), user_ref=str(user_ref), db=conn
            )
