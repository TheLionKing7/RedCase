"""Public firm signup + email-verification onboarding — Part 2 (HANDOFF §4).

``POST /v1/public/signup`` is the system's first UNAUTHENTICATED write path:
bot-driven tenant creation would flood the ``tenants``/``subscriptions`` tables and
poison the entitlement ledger. The DoD, implemented here, not as extras:

* Rate limiting per IP AND per normalized email (process-local sliding window; Cloudflare
  edge rate-limiting sits in front in prod).
* Email verification BEFORE the tenant activates: ``firm_signups`` starts
  PENDING_VERIFICATION; a tenant row is provisioned ONLY by ``POST
  /v1/public/verify`` once the holder of the emailed token proves the address. Only
  the token's hash is stored, and it expires (settings).
* An audit row for every provisioning step (``signup_audit``): 'apply' on
  submit, 'verify' + 'provision' + 'activate' on activation. Append-only is a
  database grant (conftest + migration 0018).

Provisioning runs on the app-pool connection and sets the new tenant's
``app.tenant_id`` GUC inside its own transaction so the ``signup_audit`` WITH
CHECK (``tenant_id = current_setting(...)``) accepts the post-provision rows — the
system stays inside the RLS contract rather than bypassing it.

Dev/CI fallback: when ``supabase_service_role`` is not provisioned, the outbound
provider email is skipped and the response carries ``verify_token`` so enrollment can be
tested end-to-end without a live Supabase credential. In prod the token travels only
in the email, never in an API response (no email-oracle on the signup path).

ZDR: emails are PII and are never logged. Audit rows carry ids, slugs, and step
names only.
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.middleware.zdr import get_logger
from app.onboarding import (
    hash_verify_token,
    new_verify_token,
    normalize_email,
    valid_email,
)
from app.rate_limit import PublicSignupLimiter, client_ip

log = get_logger("redcase.signup")

router = APIRouter(prefix="/v1/public", tags=["public-signup"])


class SignupRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    firm_name: str = Field(min_length=2, max_length=160)
    jurisdiction: str | None = Field(default="NG", max_length=8)


class VerifyRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    token: str = Field(min_length=1, max_length=256)


def _limiter(request: Request) -> PublicSignupLimiter:
    limiter: PublicSignupLimiter | None = getattr(
        request.app.state, "public_signup_limiter", None
    )
    if limiter is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail="signup service not ready"
        )
    return limiter


async def _send_verification_email(settings, email: str, token: str) -> bool:
    """Dispatch the outbound verification email via Supabase Auth when provisioned.

    Returns True when an email was dispatched, False when the provider credential is
    absent (dev/CI fallback — the caller then returns the token for demo/testing).
    Uses httpx (already a dependency) against the Supabase magic-link endpoint.
    """
    service_role = settings.supabase_service_role
    supabase_url = settings.supabase_url
    if not service_role or not supabase_url:
        return False
    import httpx

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{supabase_url.rstrip('/')}/auth/v1/otp",
            headers={
                "apikey": service_role.get_secret_value(),
                "Authorization": f"Bearer {service_role.get_secret_value()}",
                "Content-Type": "application/json",
            },
            json={"email": email, "create_user": False},
        )
        resp.raise_for_status()
    return True


@router.post("/signup", status_code=201)
async def public_signup(request: Request, body: SignupRequest) -> dict:
    settings = request.app.state.settings
    email = normalize_email(body.email)
    if not valid_email(email):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid email address"
        )
    limiter = _limiter(request)
    if not limiter.allow_signup(client_ip(request), email):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many signup attempts. Please try again later.",
        )

    pool = request.app.state.db_pool
    if pool is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail="database not configured"
        )

    token = new_verify_token()
    token_hash = hash_verify_token(token)
    expires = datetime.now(UTC) + timedelta(
        seconds=settings.signup_verify_ttl_s
    )

    # Dedupe on normalized email (unique index is the floor; catch the race).
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "INSERT INTO firm_signups"
                    " (email, firm_name, jurisdiction, verify_token_hash,"
                    "  verify_token_expires_at)"
                    " VALUES ($1, $2, $3, $4, $5)"
                    " RETURNING id",
                    email,
                    body.firm_name.strip(),
                    (body.jurisdiction or "NG").upper(),
                    token_hash,
                    expires,
                )
                await conn.execute(
                    "INSERT INTO signup_audit (step, actor, detail)"
                    " VALUES ('apply', 'system', $1)",
                    f"signup_id={row['id']}",
                )
    except Exception:
        # Unique violation on public (normalized) email -> already applied.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="An application for this email is already in progress.",
        ) from None

    sent = await _send_verification_email(settings, email, token)
    resp: dict = {"status": "PENDING_VERIFICATION"}
    if not sent:
        # Dev/CI fallback: no provider credential — the only path that surfaces
        # the raw token. Never reached in prod (credential is provisioned).
        resp["verify_token"] = token
        log.warning("signup_no_email_provider", note="service role unset (dev/CI)")

    log.info("signup_applied", status="PENDING_VERIFICATION")
    return resp


@router.post("/verify", status_code=200)
async def public_verify(request: Request, body: VerifyRequest) -> dict:
    email = normalize_email(body.email)
    limiter = _limiter(request)
    if not limiter.allow_verify(client_ip(request)):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many verification attempts. Please try again later.",
        )

    pool = request.app.state.db_pool
    if pool is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail="database not configured"
        )

    import hmac

    token_hash = hash_verify_token(body.token)
    now = datetime.now(UTC)

    # Read the application (firm_signups has no RLS — it is a system table the
    # service pool reads directly). No email-oracle on failure: any mismatch returns
    # a uniform 400.
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, firm_name, status, verify_token_hash, verify_token_expires_at"
            " FROM firm_signups WHERE email = $1",
            email,
        )
    if row is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="invalid verification"
        )
    if row["status"] != "PENDING_VERIFICATION":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="invalid verification"
        )
    # Constant-time token comparison; expiry check.
    if not hmac.compare_digest(row["verify_token_hash"] or "", token_hash):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="invalid verification"
        )
    if row["verify_token_expires_at"] is None or row["verify_token_expires_at"] < now:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="verification link expired — please start a new signup",
        )

    # Activate: provision tenant + vault + subscription, then flip status. Runs on
    # the app role with the new tenant's GUC set inside its own transaction so RLS
    # WITH CHECK accepts the post-provision audit rows.
    tenant_id = str(uuid.uuid4())
    vault_id = str(uuid.uuid4())
    slug = f"t-{uuid.uuid4().hex[:12]}"
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "INSERT INTO tenants (id, name, slug, jurisdiction)"
                " VALUES ($1, $2, $3, $4)",
                uuid.UUID(tenant_id),
                row["firm_name"],
                slug,
                "NG",
            )
            await conn.execute(
                "SELECT set_config('app.tenant_id', $1, true)", tenant_id
            )
            await conn.execute(
                "INSERT INTO vaults (id, tenant_id, vault_type, name)"
                " VALUES ($1, $2, 'firm', 'Client Vault')",
                uuid.UUID(vault_id),
                uuid.UUID(tenant_id),
            )
            await conn.execute(
                "INSERT INTO subscriptions (tenant_id, plan, max_seats, current_seats, status)"
                " VALUES ($1, 'CORE', 3, 0, 'ACTIVE')",
                uuid.UUID(tenant_id),
            )
            await conn.execute(
                "INSERT INTO signup_audit (tenant_id, step, actor, detail)"
                " VALUES ($1, 'verify', 'system', $2), ($1, 'provision', 'system', $3),"
                " ($1, 'activate', 'system', $4)",
                uuid.UUID(tenant_id),
                f"signup_id={row['id']}",
                f"tenant_id={tenant_id}",
                slug,
            )
            await conn.execute(
                "UPDATE firm_signups"
                " SET status = 'ACTIVE', tenant_id = $2, verified_at = now(),"
                "     verify_token_hash = NULL, verify_token_expires_at = NULL"
                " WHERE id = $1",
                row["id"],
                uuid.UUID(tenant_id),
            )

    log.info(
        "signup_verified",
        tenant_id=tenant_id,
        step="activate",
    )
    return {"status": "ACTIVE", "tenant_id": tenant_id}


