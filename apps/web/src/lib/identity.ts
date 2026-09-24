// Display-identity resolver — Shell-UX-Spec §0 (SLICE 0-a).
//
// The ANON fix. The identity fallback chain is now, in order:
//   1. display_name from /v1/members/me (firm register — "Tosin Adebayo")
//   2. profile (no dedicated profile surface yet — reserved; email local-part serves as
//      the next stable human signal)
//   3. email local-part, capitalized ("t.adebayo@aetoes.ng" -> "T. Adebayo")
//   4. "Counsel" — the terminal role-appropriate fallback
// The string "ANON" is never rendered.
//
// `useIdentity()` returns the resolved short name plus the firm name and role for the
// header eyebrow / chip ("Persona/Firm · REDCASE"). In dev-adapter mode
// (VITE_API_DEV_ADAPTER=1), getMembership() already returns the demo persona via
// lib/api/dev/members.ts, so the chain's first hop resolves and no email parsing is
// ever needed for screenshots.

import { useMembership } from "@/lib/api/members";
import { getSignInEmail } from "@/lib/auth/supabase";

/** First component of `foo.bar@baz.ng` -> "Foo. Bar" (dots retained, no ".ng"). */
export function localPartFromEmail(email: string): string | null {
  const at = email.indexOf("@");
  const local = at === -1 ? email : email.slice(0, at);
  const cleaned = local.replace(/[._-]+/g, " ").trim();
  if (!cleaned) return null;
  return cleaned
    .split(/\s+/)
    .map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w))
    .join(" ");
}

export interface DisplayIdentity {
  /** Short human name shown in the greeting / header. Never "ANON". */
  name: string;
  /** Full membership eyebrow: "Name · Firm — "Persona/Firm" by default. */
  eyebrow: string;
  firmName: string;
  role: string | null;
  clearance: string;
}

export function useIdentity(): DisplayIdentity {
  const { data } = useMembership();

  if (data) {
    const firm = data.firm_name || "REDCASE";
    const eyebrow = data.full_name
      ? `${data.full_name}${data.role ? ` · ${data.role}` : ""} · ${firm}`
      : `${firm}`;
    return {
      name: data.full_name,
      eyebrow,
      firmName: data.firm_name,
      role: data.role,
      clearance: data.clearance,
    };
  }

  // No register row (pre-provisioning / prod fallback): email local-part, else
  // terminal "Counsel". Never the string "ANON".
  const email = getSignInEmail();
  const localPart = email ? localPartFromEmail(email) : null;
  const name = localPart ?? "Counsel";
  const firm = "REDCASE";
  return {
    name,
    eyebrow: `${name} · ${firm}`,
    firmName: firm,
    role: null,
    clearance: "STAFF",
  };
}
