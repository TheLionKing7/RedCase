// Personnel identity typed client — IA §2 (S10-4 firm_members).
//
// Mirrors the FastAPI wire model in app/routers/members.py (owner ruling 2 — no
// invented fields). Returns the user's REAL personnel name + firm name from the
// register — the human's identity, deliberately SEPARATE from the agent persona
// (agent_personas, S10-2). The Home eyebrow and AppShell header render this,
// never a hardcoded "ANON" or a bare clearance string.

import { useQuery } from "@tanstack/react-query";

import { apiGet } from "@/lib/api/client";
import { getMembershipDev } from "@/lib/api/dev/members";

/** Wire mirror of GET /v1/members/me. */
export interface Membership {
  full_name: string;
  role: string | null;
  clearance: string;
  firm_name: string;
}

/**
 * Personnel identity — GET /v1/members/me. Falls back to the schema-exact dev
 * adapter (demo persona) when VITE_API_DEV_ADAPTER=1 so the chrome shows a real
 * name in development, mirroring the accept-invite adapter pattern.
 */
export function getMembership(): Promise<Membership> {
  if (import.meta.env.VITE_API_DEV_ADAPTER === "1") {
    return getMembershipDev();
  }
  return apiGet<Membership>("/v1/members/me");
}

/** Current user's personnel record; 404 (not yet in the register) → null. */
export function useMembership() {
  return useQuery<Membership | null>({
    queryKey: ["members", "me"],
    queryFn: async () => {
      try {
        return await getMembership();
      } catch {
        // No register row yet (pre-provisioning): the caller falls back to
        // clearance/role gracefully rather than blocking the whole surface.
        return null;
      }
    },
  });
}
