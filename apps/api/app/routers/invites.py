"""Firm invite + seat counting — Part 2 (HANDOFF §4, Addendum §6).

``POST /v1/invites`` is the monetization schema's first live exercise: seats are
consumed at INVITE time against ``subscriptions``. The DoD:

* Under the limit — invite succeeds and ``current_seats`` is incremented.
* At/over ``max_seats`` — invite is DENIED and ``current_seats`` is NOT
  incremented, with upgrade copy (402).
* ``role -> clearance`` mapping is the RLS ladder's first live use: a firm inviting
  an ASSOCIATE or STAFF lands at STAFF clearance — the floor, never the ceiling
  (mapping in ``app.onboarding``). One mapping error here would hand a non-partner
  employee CONFIDENTIAL-document vision.

Inviting is an authenticated, tenant-scoped, PARTNER/ADMIN-only operation. Every
provisioning verdict writes one immutable ``signup_audit`` row ('invite' + deny):
the DENY audit commits in its own transaction so the 402/403 raised after it cannot
roll back the audit, and the seat increment + invite insert are atomic (a failure of
either rolls back both together — the seat counter is untouched on a failed invite).

ZDR: invited_email is PII and is never logged. Audit rows carry ids and step names.
The one documented exception (Part 3 Slice 1 spec, explicit): the
``invite_accepted`` audit row records the invited email in ``detail`` because the
spec mandates it — flagged here and in HANDOFF as an intentional spec-mandated
inclusion that the ZDR filter does not strip.
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.deps import TenantContext, get_tenant_context
from app.middleware.zdr import get_logger
from app.onboarding import (
    clearance_for_role,
    hash_invite_token,
    new_invite_token,
    normalize_email,
    valid_email,
)
from app.rate_limit import InviteAcceptLimiter, client_ip

log = get_logger("redcase.invites")

router = APIRouter(prefix="/v1", tags=["invites"])

_INVITE_UPGRADE_COPY = (
    "This firm's license is at capacity. Add seats to invite more licensed lawyers to RedCase."
)


class InviteRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: str = Field(min_length=1, max_length=32)


class AcceptInviteRequest(BaseModel):
    # token + password only. clearance is deliberately NOT a field: it is derived
    # server-side from the invite's role mapping, never taken from the client.
    token: str = Field(min_length=1, max_length=256)
    password: str = Field(min_length=8, max_length=200)
    name: str | None = Field(default=None, max_length=160)


_WHO_CAN_INVITE = {"PARTNER", "ADMIN"}


@router.post("/invites", status_code=201)
async def create_invite(
    request: Request,
    body: InviteRequest,
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> dict:
    email = normalize_email(body.email)
    if not valid_email(email):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid email address")

    # Only PARTNER/ADMIN may grant seats (the invite is a partner act).
    if ctx.clearance not in _WHO_CAN_INVITE:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Only partners can invite new members to the firm.",
        )

    try:
        clearance = clearance_for_role(body.role.upper())
    except (KeyError, ValueError):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unknown role. Valid roles: PARTNER, SENIOR, ASSOCIATE, STAFF.",
        ) from None

    pool = request.app.state.db_pool
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database not configured")
    settings = request.app.state.settings

    # Seat gate (committed read + DENY audit), then the atomic credit path. The
    # DENY verdict must raise OUTSIDE its transaction, else the 402/403 rollback
    # would discard the invite_denied audit row (every verdict writes one audit row).
    deny: tuple[int, str] | None = None
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", ctx.tenant_id)
            sub = await conn.fetchrow(
                "SELECT max_seats, current_seats, status"
                " FROM subscriptions WHERE tenant_id = $1::uuid",
                uuid.UUID(ctx.tenant_id),
            )
            sub_status = sub["status"] if sub else "ACTIVE"
            max_seats = sub["max_seats"] if sub else 0
            current_seats = sub["current_seats"] if sub else 0
            if sub_status == "SUSPENDED":
                await conn.execute(
                    "INSERT INTO signup_audit"
                    " (tenant_id, step, actor, detail)"
                    " VALUES ($1, 'invite_denied', $2, $3)",
                    uuid.UUID(ctx.tenant_id),
                    ctx.user_ref,
                    "reason=suspended",
                )
                deny = (
                    status.HTTP_403_FORBIDDEN,
                    "This firm's subscription is suspended; invites are paused.",
                )
            elif current_seats >= max_seats:
                await conn.execute(
                    "INSERT INTO signup_audit"
                    " (tenant_id, step, actor, detail)"
                    " VALUES ($1, 'invite_denied', $2, $3)",
                    uuid.UUID(ctx.tenant_id),
                    ctx.user_ref,
                    "reason=seat_capacity",
                )
                deny = (
                    status.HTTP_402_PAYMENT_REQUIRED,
                    _INVITE_UPGRADE_COPY + " [invite: DENY_SEAT]",
                )

        if deny is not None:
            # Raised after the DENY transaction committed -> audit survives.
            raise HTTPException(status_code=deny[0], detail=deny[1])

        # Seat available: invite + seat increment + audit are one atomic unit. A
        # failure anywhere rolls back all three together (Addendum §6). Re-set the
        # tenant GUC: the DENY transaction above committed with is_local=true, which
        # resets the placeholder to its empty session default and would make the policy's
        # ``current_setting(...)::uuid`` cast fail on "".
        token = new_invite_token()
        token_hash = hash_invite_token(token)
        token_expires = datetime.now(UTC) + timedelta(seconds=settings.invite_token_ttl_s)
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", ctx.tenant_id)
            row = await conn.fetchrow(
                "INSERT INTO firm_invites"
                " (tenant_id, invited_email, role, clearance, invited_by,"
                "  invite_token_hash, invite_token_expires_at)"
                " VALUES ($1, $2, $3, $4, $5, $6, $7)"
                " RETURNING id",
                uuid.UUID(ctx.tenant_id),
                email,
                body.role.upper(),
                clearance,
                ctx.user_ref,
                token_hash,
                token_expires,
            )
            # Consume the seat atomically with the invite (Addendum §6: seats
            # are consumed at invite time).
            await conn.execute(
                "UPDATE subscriptions SET current_seats = current_seats + 1"
                " WHERE tenant_id = $1::uuid",
                uuid.UUID(ctx.tenant_id),
            )
            await conn.execute(
                "INSERT INTO signup_audit (tenant_id, step, actor, detail)"
                " VALUES ($1, 'invite', $2, $3)",
                uuid.UUID(ctx.tenant_id),
                ctx.user_ref,
                f"invite_id={row['id']}",
            )

    log.info(
        "invite_created",
        tenant_id=ctx.tenant_id,
        role=body.role.upper(),
        clearance=clearance,
    )
    return {
        "id": str(row["id"]),
        "email": email,
        "role": body.role.upper(),
        "clearance": clearance,
        "status": "PENDING",
        # Raw token for the invite link. In dev/CI (no email dispatch in create_invite
        # yet) the partner forwards this link; in prod the outbound email should carry
        # it (tagged follow-up, same as the signup path's email provider).
        "token": token,
        "invite_url": f"/accept-invite?token={token}",
        "expires_at": token_expires.isoformat(),
    }


async def _create_supabase_user(
    settings, email: str, password: str, name: str | None,
    tenant_id: str, clearance: str,
) -> str | None:
    """Create the invited user in Supabase Auth (admin API, service-role).

    Returns the created user's id, or None in dev/CI when the service role is not
    provisioned (the caller then treats provisioning as internally tracked — tests
    inject this via monkeypatch). ``app_metadata`` (tenant_id + clearance) is set
    HERE, derived from the invite's role mapping — never from client input, so a
    forged clearance claim cannot reach the JWT.
    """
    service_role = settings.supabase_service_role
    supabase_url = settings.supabase_url
    if not service_role or not supabase_url:
        return None

    import httpx

    payload: dict = {
        "email": email,
        "password": password,
        "email_confirm": True,
        "app_metadata": {"tenant_id": tenant_id, "clearance": clearance},
    }
    if name:
        payload["user_metadata"] = {"full_name": name}
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{supabase_url.rstrip('/')}/auth/v1/admin/users",
            headers={
                "apikey": service_role.get_secret_value(),
                "Authorization": f"Bearer {service_role.get_secret_value()}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
    return data.get("id")


def _accept_limiter(request: Request) -> "InviteAcceptLimiter":
    limiter: InviteAcceptLimiter | None = getattr(
        request.app.state, "invite_accept_limiter", None
    )
    if limiter is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail="invite service not ready"
        )
    return limiter


@router.post("/invites/accept", status_code=200)
async def accept_invite(request: Request, body: AcceptInviteRequest) -> dict:
    """Complete a firm invite: redeem the token and provision the user.

    Unauthenticated by design (this IS the bootstrap path), but hardened: rate
    limited per IP + per token, token matched by subkeyed hash, single-use (a second
    redeem is rejected), and the granted clearance is derived server-side from the INVITE's
    role mapping — a forged ``clearance`` field in the body is silently ignored. The
    Supabase user's ``app_metadata`` comes from that server-derived value.
    """
    settings = request.app.state.settings
    pool = request.app.state.db_pool
    if pool is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="database not configured")

    limiter = _accept_limiter(request)
    token_hash = hash_invite_token(body.token)
    if not limiter.allow_accept(client_ip(request), token_hash):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please try again later.",
        )

    # Claim the invite atomically & single-use via the SECURITY DEFINER function
    # (bypasses RLS so an unauthenticated token lookup can learn the tenant). The claim
    # commits on success; if no row is claimed the UPDATE matched nothing, so raising
    # after the transaction is safe (nothing to roll back).
    claimed = None
    async with pool.acquire() as conn:
        async with conn.transaction():
            claimed = await conn.fetchrow(
                "SELECT * FROM redcase_claim_invite($1, now())", token_hash
            )
            if claimed is not None:
                await conn.execute(
                    "SELECT set_config('app.tenant_id', $1, true)",
                    str(claimed["r_tenant_id"]),
                )
                await conn.execute(
                    "INSERT INTO signup_audit (tenant_id, step, actor, detail)"
                    " VALUES ($1, 'invite_accepted', 'system', $2)",
                    claimed["r_tenant_id"],
                    f"invite_id={claimed['r_id']},token_hash={token_hash},"
                    f"email={claimed['r_invited_email']},clearance={claimed['r_clearance']}",
                )

    if claimed is None:
        # Uniform 400 (no email/token oracle on failure): unknown, already-used, and
        # expired tokens all look identical to the caller.
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="This invite link is invalid or has already been used.",
        )

    tenant_id = str(claimed["r_tenant_id"])
    email = claimed["r_invited_email"]
    clearance = claimed["r_clearance"]

    try:
        user_id = await _create_supabase_user(
            settings, email, body.password, body.name, tenant_id, clearance
        )
    except Exception:
        # Provisioning failed — re-open the invite so the invitee can retry.
        log.exception("invite_user_provision_failed", tenant_id=tenant_id)
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE firm_invites SET status = 'PENDING', accepted_at = NULL"
                " WHERE id = $1::uuid",
                claimed["r_id"],
            )
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not activate your account. Please try again.",
        ) from None

    if user_id is not None:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT set_config('app.tenant_id', $1, true)", tenant_id
                )
                await conn.execute(
                    "UPDATE firm_invites SET accepted_user_ref = $2"
                    " WHERE id = $1::uuid",
                    claimed["r_id"],
                    user_id,
                )

    log.info(
        "invite_accepted",
        tenant_id=tenant_id,
        clearance=clearance,
        invite_id=str(claimed["r_id"]),
    )
    return {
        "status": "ACCEPTED",
        "tenant_id": tenant_id,
        "email": email,
        "clearance": clearance,
    }
