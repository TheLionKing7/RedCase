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

ZDR: invited_email is PII and is never logged; audit rows carry ids and step names.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.deps import TenantContext, get_tenant_context
from app.middleware.zdr import get_logger
from app.onboarding import clearance_for_role, normalize_email, valid_email

log = get_logger("redcase.invites")

router = APIRouter(prefix="/v1", tags=["invites"])

_INVITE_UPGRADE_COPY = (
    "This firm's license is at capacity. Add seats to invite more licensed lawyers to RedCase."
)


class InviteRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: str = Field(min_length=1, max_length=32)


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
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", ctx.tenant_id)
            row = await conn.fetchrow(
                "INSERT INTO firm_invites"
                " (tenant_id, invited_email, role, clearance, invited_by)"
                " VALUES ($1, $2, $3, $4, $5)"
                " RETURNING id",
                uuid.UUID(ctx.tenant_id),
                email,
                body.role.upper(),
                clearance,
                ctx.user_ref,
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
    }
