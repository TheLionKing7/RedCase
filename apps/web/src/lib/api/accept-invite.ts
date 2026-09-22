import { apiPost } from "./client";

export interface AcceptInviteRequest {
  token: string;
  password: string;
  name?: string;
}

export interface AcceptInviteResponse {
  status: string;
  tenant_id?: string;
}

/**
 * Complete a firm invite: exchange the invite token for a provisioned user
 * (sets password, activates the seat, returns the tenant). Backend contract:
 * POST /v1/invites/accept. Falls back to the dev adapter when
 * VITE_API_DEV_ADAPTER=1 (demo without a live backend).
 */
export async function acceptInvite(
  req: AcceptInviteRequest,
): Promise<AcceptInviteResponse> {
  if (import.meta.env.VITE_API_DEV_ADAPTER === "1") {
    const { acceptInviteDev } = await import("./dev/accept-invite");
    return acceptInviteDev(req);
  }
  return apiPost<AcceptInviteResponse, AcceptInviteRequest>(
    "/v1/invites/accept",
    req,
  );
}
