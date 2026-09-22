"""Entitlement gate — Feature-Addendum §6 (monetization, server-side).

Design rules implemented:
- ``require_feature("workbench.analyze")`` is a FastAPI dependency factory:
  it resolves the tenant context, evaluates the gate, writes exactly one
  ``entitlement_events`` row for the DECISION (§6: "every gate decision
  logged"), and raises 402/403 with upgrade copy on DENY.
- Decision order: DENY_SUSPENDED (403) -> DENY_PLAN (402) -> DENY_SEAT
  (402) -> ALLOW. Suspended tenants keep read access to their own data
  (never hostage the firm's documents); only generative features stop.
- The gate event is written on a DEDICATED short transaction (not the
  request transaction): a DENY raises HTTPException, which would roll the
  request transaction back and destroy the audit row. Same lesson as the
  Step A /analyze INSERT race.
- Suspension applies to generative (PREMIUM-gated) features only; Core
  surfaces (channels, read paths) are never gated here.

CONFLICT RECORDED (HANDOFF.md rule 3, reported to owner): §6 counts seats
from "active users with clearance in ('PARTNER','SENIOR','STAFF')", but
Phase 1 has no users/clearance table (users are Supabase Auth records;
clearance provisioning is Phase 2). The Phase 1 gate checks the billing
anchors (subscriptions.current_seats vs max_seats) instead; clearance-
based counting lands with Phase 2 user provisioning. A tenant with NO
subscriptions row is treated as plan CORE / status ACTIVE (the DDL
defaults), so Core-tier behavior never depends on a row existing.

ZDR: log lines carry tenant/feature/decision only — no user content.
"""

import uuid
from collections.abc import Awaitable, Callable

from fastapi import Depends, HTTPException, Request, status

from app.deps import TenantContext, get_tenant_context
from app.middleware.zdr import get_logger

log = get_logger("redcase.entitlements")

# §6: the Workbench is the premium surface. Core-tier features are simply
# not listed here and skip the plan/seat gate (suspension still applies).
PREMIUM_FEATURES = frozenset(
    {"workbench.analyze", "workbench.chat", "workbench.assistant"}
)

_UPGRADE_COPY = {
    "DENY_PLAN": (
        "The Legal Workbench is a per-seat premium feature of RedCase — "
        "document analysis, Expert Chat, and battle cards. Upgrade this "
        "firm's plan to give every licensed lawyer a personal workbench."
    ),
    "DENY_SEAT": (
        "All premium Workbench seats for this firm are in use. Add seats "
        "to keep every licensed lawyer working."
    ),
    "DENY_SUSPENDED": (
        "This firm's subscription is suspended, so generative features are "
        "paused. Your documents and data remain fully accessible; please "
        "settle billing to resume analysis."
    ),
}


def require_feature(
    feature: str,
) -> Callable[..., Awaitable[None]]:
    """Dependency factory: gate a route on the tenant's entitlement."""

    async def _gate(
        request: Request,
        ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
    ) -> None:
        pool = request.app.state.db_pool
        decision = "ALLOW"
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT set_config('app.tenant_id', $1, true)", ctx.tenant_id
                )
                row = await conn.fetchrow(
                    "SELECT plan, status, max_seats, current_seats"
                    " FROM subscriptions WHERE tenant_id = $1::uuid",
                    uuid.UUID(ctx.tenant_id),
                )
                plan = row["plan"] if row else "CORE"
                sub_status = row["status"] if row else "ACTIVE"
                max_seats = row["max_seats"] if row else 0
                current_seats = row["current_seats"] if row else 0

                if feature in PREMIUM_FEATURES and sub_status == "SUSPENDED":
                    decision = "DENY_SUSPENDED"
                elif feature in PREMIUM_FEATURES and plan != "PREMIUM":
                    decision = "DENY_PLAN"
                elif (
                    feature in PREMIUM_FEATURES
                    and max_seats > 0
                    and current_seats >= max_seats
                ):
                    decision = "DENY_SEAT"

                await conn.execute(
                    "INSERT INTO entitlement_events"
                    " (tenant_id, user_ref, feature, decision)"
                    " VALUES ($1, $2, $3, $4)",
                    uuid.UUID(ctx.tenant_id),
                    ctx.user_ref,
                    feature,
                    decision,
                )
        log.info(
            "entitlement_gate",
            feature=feature,
            decision=decision,
            tenant_id=ctx.tenant_id,
        )
        if decision != "ALLOW":
            code = (
                status.HTTP_403_FORBIDDEN
                if decision == "DENY_SUSPENDED"
                else status.HTTP_402_PAYMENT_REQUIRED
            )
            raise HTTPException(
                code, detail=f"{_UPGRADE_COPY[decision]} [{feature}: {decision}]"
            )

    return _gate
