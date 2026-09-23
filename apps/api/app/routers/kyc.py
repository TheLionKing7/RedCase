"""Firm KYC onboarding — Addendum S10.2 (S10-1).

The KYC step of the onboarding wizard. Firm-admin-only (the orthogonal ``is_firm_admin``
capability, Addendum 8.5 — never derived from clearance). KYC documents are
PARTNER_RESTRICTED-class content, so this router stores only STORAGE PATHS in
``firm_kyc`` and never document bytes.

  * GET  /v1/firm/kyc - the firm's KYC row (status, refs, stem fields).
  * POST /v1/firm/kyc - upsert the firm's KYC row. The caller supplies the
                          storage paths the client already uploaded to the private bucket
                          (the client gets those paths from the storage layer; this
                          router is the record, not the bytes).

verification_status is PENDING on submit and flips only via a manual ops review
(tenant zero) — there is deliberately NO client endpoint to set VERIFIED/REJECTED;
``reviewed_by``/``reviewed_at`` are written by the ops path only.

ZDR: firm_kyc holds paths and status, no document content, no email, no scan.
"""
from datetime import UTC, datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.deps import TenantContext, require_firm_admin
from app.middleware.zdr import get_logger

log = get_logger("redcase.kyc")

router = APIRouter(prefix="/v1/firm", tags=["firm-kyc"])

_ID_DOC_TYPES = ("national-id", "passport", "drivers-license")


class KycSubmitIn(BaseModel):
    """KYC submission — storage paths only, never document content."""

    firm_website: Optional[str] = Field(default=None, max_length=1000)
    rc_path: Optional[str] = Field(default=None, max_length=512)
    id_document_path: Optional[str] = Field(default=None, max_length=512)
    id_document_type: Optional[str] = Field(default=None, max_length=32)


@router.get("/kyc")
async def get_kyc(
    ctx: TenantContext = Depends(require_firm_admin),  # noqa: B008
) -> dict:
    """The firm's KYC record (paths + verification state). Firm-admin only."""
    row = await ctx.db.fetchrow(
        "SELECT firm_website, rc_path, id_document_path, id_document_type,"
        " verification_status, submitted_at, reviewed_by, reviewed_at"
        " FROM firm_kyc WHERE tenant_id = $1::uuid",
        UUID(ctx.tenant_id),
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="KYC not submitted yet")
    return {
        "kyc": {
            "firm_website": row["firm_website"],
            "rc_path": row["rc_path"],
            "id_document_path": row["id_document_path"],
            "id_document_type": row["id_document_type"],
            "verification_status": row["verification_status"],
            "submitted_at": (
                row["submitted_at"].isoformat() if row["submitted_at"] else None
            ),
            "reviewed_by": row["reviewed_by"],
            "reviewed_at": (
                row["reviewed_at"].isoformat() if row["reviewed_at"] else None
            ),
        }
    }


@router.post("/kyc", status_code=200)
async def submit_kyc(
    body: KycSubmitIn,
    ctx: TenantContext = Depends(require_firm_admin),  # noqa: B008
) -> dict:
    """Upsert the firm's KYC record. Firm-admin only; PENDING after submit.

    Both document paths are required (a KYC submission with neither is rejected). At
    least one must be present to be meaningful; we require rc_path + id_document_path
    for a valid KYC packet (per S10.2 firm-identity + administrator-ID documents).
    """

    if body.id_document_type and body.id_document_type not in _ID_DOC_TYPES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"id_document_type must be one of {', '.join(_ID_DOC_TYPES)}",
        )
    if not body.rc_path or not body.id_document_path:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="KYC requires both the firm RC document and the administrator ID document",
        )

    now = datetime.now(UTC)
    await ctx.db.execute(
        """
        INSERT INTO firm_kyc
            (tenant_id, firm_website, rc_path, id_document_path, id_document_type,
             verification_status, submitted_at)
        VALUES ($1, $2, $3, $4, $5, 'PENDING', $6)
        ON CONFLICT (tenant_id)
        DO UPDATE SET
            firm_website = EXCLUDED.firm_website,
            rc_path = EXCLUDED.rc_path,
            id_document_path = EXCLUDED.id_document_path,
            id_document_type = EXCLUDED.id_document_type,
            verification_status = 'PENDING',
            submitted_at = EXCLUDED.submitted_at,
            reviewed_by = NULL,
            reviewed_at = NULL
        """,
        UUID(ctx.tenant_id),
        body.firm_website,
        body.rc_path,
        body.id_document_path,
        body.id_document_type,
        now,
    )
    log.info(
        "firm_kyc_submitted",
        tenant_id=ctx.tenant_id,
        status="PENDING",
        verified=False,
    )
    return {
        "kyc": {
            "firm_website": body.firm_website,
            "verification_status": "PENDING",
            "submitted_at": now.isoformat(),
        }
    }
