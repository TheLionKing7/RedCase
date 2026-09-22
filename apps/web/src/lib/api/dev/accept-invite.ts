// DEV ADAPTER — accept-invite. Mirrors the POST /v1/invites/accept contract
// so the invite completion flow is demoable without a live backend or a real invite
// token. Selected only when VITE_API_DEV_ADAPTER=1 (see lib/api/accept-invite.ts).

import type {
  AcceptInviteRequest,
  AcceptInviteResponse,
} from "../accept-invite";

export function acceptInviteDev(
  req: AcceptInviteRequest,
): Promise<AcceptInviteResponse> {
  return new Promise((resolve) =>
    setTimeout(
      () =>
        resolve({
          status: "ACTIVE",
          tenant_id: "00000000-0000-0000-0000-000000000000",
        }),
      600,
    ),
  );
}
