"""Private firm logo and KYC uploads stored as Supabase Storage bytes.

All routes are firm-admin-only. KYC objects are classified PARTNER_RESTRICTED and
can only be retrieved using short-lived signed URLs issued by this API. Object
keys are generated server-side under the authenticated tenant prefix.
"""

from __future__ import annotations

from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.config import Settings
from app.deps import TenantContext, require_firm_admin

router = APIRouter(prefix="/v1/firm", tags=["firm-assets"])
assets_router = APIRouter(prefix="/assets", tags=["firm-assets"])
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_MIME_EXTENSIONS = {
    "application/pdf": "pdf",
    "image/jpeg": "jpg",
    "image/png": "png",
}
_SIGNATURES = {
    "application/pdf": lambda body: body.startswith(b"%PDF-"),
    "image/jpeg": lambda body: body.startswith(b"\xff\xd8\xff"),
    "image/png": lambda body: body.startswith(b"\x89PNG\r\n\x1a\n"),
}


class SignedUrlRequest(BaseModel):
    path: str


class FirmIdentityRequest(BaseModel):
    firm_name: str
    jurisdiction: str = "NG"
    logo_path: str | None = None


@router.post("/identity")
async def save_firm_identity(
    body: FirmIdentityRequest,
    request: Request,
    ctx: TenantContext = Depends(require_firm_admin),  # noqa: B008
) -> dict[str, str]:
    """Save firm identity and a logo reference under the caller's tenant."""
    if body.jurisdiction.upper() != "NG":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only Nigeria is currently supported.",
        )
    if body.logo_path and (
        not body.logo_path.startswith(
            f"{request.app.state.settings.storage_brand_prefix}/{ctx.tenant_id}/logo/"
        )
        or ".." in body.logo_path
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Logo not found.")
    await ctx.db.execute(
        "UPDATE tenants SET name = $1, jurisdiction = $2, logo_path = COALESCE($3, logo_path)"
        " WHERE id = $4::uuid",
        body.firm_name.strip()[:160],
        body.jurisdiction.upper(),
        body.logo_path,
        ctx.tenant_id,
    )
    return {"status": "saved"}


def _sniff_content_type(body: bytes) -> str | None:
    return next((mime for mime, check in _SIGNATURES.items() if check(body)), None)


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    if not settings.supabase_url or not settings.supabase_service_role:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Private storage is not configured.",
        )
    return settings


async def _storage_request(
    settings: Settings, method: str, endpoint: str, **kwargs
) -> httpx.Response:
    assert settings.supabase_url and settings.supabase_service_role
    key = settings.supabase_service_role.get_secret_value()
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        **kwargs.pop("headers", {}),
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        return await client.request(
            method,
            f"{settings.supabase_url.rstrip('/')}/storage/v1{endpoint}",
            headers=headers,
            **kwargs,
        )


@assets_router.post("/{asset_type}")
async def upload_firm_asset(
    asset_type: str,
    request: Request,
    ctx: TenantContext = Depends(require_firm_admin),  # noqa: B008
) -> dict[str, str]:
    """Stream an actual PDF/JPEG/PNG upload and store bytes in a private bucket."""
    if asset_type not in {"logo", "rc-document", "personal-id"}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown firm asset.")

    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Files must be 10 MB or smaller.",
            )
        body.extend(chunk)
    content_type = _sniff_content_type(bytes(body))
    if content_type is None:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Upload a valid PDF, JPG, or PNG file.",
        )
    if asset_type == "logo" and content_type == "application/pdf":
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="A firm logo must be a JPG or PNG image.",
        )

    settings = _settings(request)
    is_kyc = asset_type != "logo"
    bucket = settings.storage_kyc_bucket if is_kyc else settings.storage_brand_bucket
    prefix = settings.storage_kyc_prefix if is_kyc else settings.storage_brand_prefix
    key = f"{prefix}/{ctx.tenant_id}/{asset_type}/{uuid4().hex}.{_MIME_EXTENSIONS[content_type]}"
    response = await _storage_request(
        settings,
        "POST",
        f"/object/{bucket}/{key}",
        content=bytes(body),
        headers={"Content-Type": content_type, "x-upsert": "false"},
    )
    if response.is_error:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, detail="Private storage could not save the file."
        )

    if asset_type == "logo":
        await ctx.db.execute(
            "UPDATE tenants SET logo_path = $1 WHERE id = $2::uuid",
            key,
            ctx.tenant_id,
        )
    return {
        "path": key,
        "content_type": content_type,
        "classification": "PARTNER_RESTRICTED" if is_kyc else "FIRM_BRANDING",
    }


@assets_router.post("/{asset_type}/signed-url")
async def get_firm_asset_signed_url(
    asset_type: str,
    body: SignedUrlRequest,
    request: Request,
    ctx: TenantContext = Depends(require_firm_admin),  # noqa: B008
) -> dict[str, str]:
    """Issue an admin-only, short-lived signed URL for an asset in this tenant."""
    if asset_type not in {"logo", "rc-document", "personal-id"}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown firm asset.")
    is_kyc = asset_type != "logo"
    bucket = (
        request.app.state.settings.storage_kyc_bucket
        if is_kyc
        else request.app.state.settings.storage_brand_bucket
    )
    prefix = (
        request.app.state.settings.storage_kyc_prefix
        if is_kyc
        else request.app.state.settings.storage_brand_prefix
    )
    expected_prefix = f"{prefix}/{ctx.tenant_id}/{asset_type}/"
    if not body.path.startswith(expected_prefix) or ".." in body.path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Asset not found.")

    result = await _storage_request(
        _settings(request),
        "POST",
        f"/object/sign/{bucket}/{body.path}",
        json={"expiresIn": 60},
    )
    if result.is_error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Asset not found.")
    data = result.json()
    signed_path = data.get("signedURL") or data.get("signedUrl")
    if not signed_path:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail="Could not sign asset URL.")
    return {
        "signed_url": f"{request.app.state.settings.supabase_url.rstrip('/')}/storage/v1{signed_path}",
        "expires_in": "60",
    }

