// DEV ADAPTER — members/me. Mirrors the GET /v1/members/me contract so the
// shell's identity chrome (Home greeting, header eyebrow, top-right chip) is demoable
// without a live backend, a Supabase JWT, or a `firm_members` row.
//
// The persona mirrors migration 0024's seeded tenant-zero managing partner ("Tosin
// Adebayo · Aetoes Legal"), so what a screenshot shows is exactly what a provisioned
// production persona renders — a real name, never "ANON".
//
// Selected only when VITE_API_DEV_ADAPTER=1 (see lib/api/members.ts).

import type { Membership } from "../members";

export function getMembershipDev(): Promise<Membership> {
  return new Promise((resolve) =>
    setTimeout(
      () =>
        resolve({
          full_name: "Tosin Adebayo",
          role: "Managing Partner",
          clearance: "PARTNER",
          firm_name: "Aetoes Legal",
        }),
      120,
    ),
  );
}
