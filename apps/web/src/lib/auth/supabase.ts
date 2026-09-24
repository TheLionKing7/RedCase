// Supabase Auth (email magic link) — minimal HTTP implementation.
//
// Owner ruling 3 (2026-09-16): auth is Supabase Auth email magic link; the
// FastAPI backend verifies the Supabase JWT (shared secret) and derives
// user_ref + tenant_id from the claims. No standalone API-key auth.
//
// Implemented against Supabase's public Auth HTTP API directly (the endpoints
// supabase-js calls) to avoid adding a dependency; session shape matches
// supabase-js v2 so swapping to the SDK later is a drop-in.

const SUPABASE_URL: string | undefined = import.meta.env.VITE_SUPABASE_URL;
const ANON_KEY: string | undefined = import.meta.env.VITE_SUPABASE_ANON_KEY;

const STORAGE_KEY = "redcase.auth.session";

export interface AuthSession {
  access_token: string;
  refresh_token: string;
  /** Unix seconds. */
  expires_at: number;
  /** From the JWT `sub` claim — surfaced for display only; the backend
   *  derives user_ref/tenant_id server-side from the token itself. */
  user_ref: string | null;
}

export class AuthError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AuthError";
  }
}

function requireConfig(): { url: string; key: string } {
  if (!SUPABASE_URL || !ANON_KEY) {
    throw new AuthError(
      "Supabase auth is not configured (VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY)",
    );
  }
  return { url: SUPABASE_URL, key: ANON_KEY };
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Step 1 of the magic link: Supabase emails the user a 6–8 digit OTP. */
export async function signInWithEmail(email: string): Promise<void> {
  const { url, key } = requireConfig();
  if (!EMAIL_RE.test(email)) throw new AuthError("Enter a valid email address");
  const res = await fetch(`${url}/auth/v1/otp`, {
    method: "POST",
    headers: { apikey: key, "content-type": "application/json" },
    body: JSON.stringify({ email, create_user: true }),
  });
  if (!res.ok) {
    throw new AuthError(`Could not send sign-in email (HTTP ${res.status})`);
  }
}

/** Step 2: exchange the OTP from the email for a JWT session. */
export async function verifyOtp(
  email: string,
  token: string,
): Promise<AuthSession> {
  const { url, key } = requireConfig();
  const res = await fetch(`${url}/auth/v1/verify`, {
    method: "POST",
    headers: { apikey: key, "content-type": "application/json" },
    body: JSON.stringify({ email, token, type: "email" }),
  });
  const data = (await res.json()) as {
    access_token?: string;
    refresh_token?: string;
    expires_at?: number;
    user?: { id?: string };
    error_description?: string;
    msg?: string;
  };
  if (!res.ok || !data.access_token) {
    throw new AuthError(
      data.error_description ??
        data.msg ??
        `Sign-in failed (HTTP ${res.status})`,
    );
  }
  const session: AuthSession = {
    access_token: data.access_token,
    refresh_token: data.refresh_token ?? "",
    expires_at: data.expires_at ?? 0,
    user_ref: data.user?.id ?? null,
  };
  persist(session);
  return session;
}

/** Step: email+password sign-in via Supabase Auth password grant. */
export async function signInWithPassword(
  email: string,
  password: string,
): Promise<AuthSession> {
  const { url, key } = requireConfig();
  if (!EMAIL_RE.test(email)) throw new AuthError("Enter a valid email address");
  if (!password) throw new AuthError("Enter your password");
  const res = await fetch(`${url}/auth/v1/token?grant_type=password`, {
    method: "POST",
    headers: { apikey: key, "content-type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const data = (await res.json()) as {
    access_token?: string;
    refresh_token?: string;
    expires_at?: number;
    user?: { id?: string };
    error_description?: string;
    msg?: string;
    code?: string;
  };
  if (!res.ok || !data.access_token) {
    throw new AuthError(
      data.error_description ??
        data.msg ??
        `Sign-in failed (HTTP ${res.status})`,
    );
  }
  const session: AuthSession = {
    access_token: data.access_token,
    refresh_token: data.refresh_token ?? "",
    expires_at: data.expires_at ?? 0,
    user_ref: data.user?.id ?? null,
  };
  persist(session);
  return session;
}

export function getSession(): AuthSession | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    const session = JSON.parse(raw) as AuthSession;
    if (!session.access_token) return null;
    // 60s skew margin on expiry.
    if (session.expires_at && session.expires_at < Date.now() / 1000 + 60) {
      return null;
    }
    return session;
  } catch {
    return null;
  }
}

/**
 * Clearance from the current session's JWT `app_metadata.clearance` claim
 * (STAFF | SENIOR | PARTNER | ADMIN — the claim contract in apps/api/app/deps.py).
 * Used by the post-login role landing (Part 3 Slice 2). Fails closed to
 * STAFF when the claim is absent: an unmapped user gets the floor, never the
 * ceiling. Returns "ANON" when there is no session at all.
 */
export function getClearance(): string {
  const token = getAccessToken();
  if (!token) return "ANON";
  try {
    const payloadB64 = token.split(".")[1] ?? "";
    const pad = "=".repeat(-payloadB64.length % 4);
    const payload = JSON.parse(atob(payloadB64)) as {
      app_metadata?: { clearance?: string };
    };
    return payload.app_metadata?.clearance ?? "STAFF";
  } catch {
    return "STAFF";
  }
}

/**
 * Firm-admin capability from the current session's JWT `app_metadata.is_firm_admin`
 * claim (Addendum §8.5 — an ORTHOGONAL, grantable admin flag, NOT derived from
 * clearance). Used to gate the Firm Command nav entry. Fails closed to `false` when
 * the claim is absent or there is no session — an unmapped user is never treated as an
 * admin. The claim is the same source `app.deps.verify_supabase_jwt` reads for the
 * server-side `require_firm_admin` gate; this only (de)selects UI, never enforces.
 */
export function getFirmAdmin(): boolean {
  const token = getAccessToken();
  if (!token) return false;
  try {
    const payloadB64 = token.split(".")[1] ?? "";
    const pad = "=".repeat(-payloadB64.length % 4);
    const payload = JSON.parse(atob(payloadB64)) as {
      app_metadata?: { is_firm_admin?: boolean };
    };
    return payload.app_metadata?.is_firm_admin === true;
  } catch {
    return false;
  }
}

/** JWT sent as `Authorization: Bearer` to FastAPI (see lib/api/client.ts). */
export function getAccessToken(): string | null {
  return getSession()?.access_token ?? null;
}

/**
 * The sign-in email from the current session's JWT `email` claim (Supabase sets it
 * on the token). Used as the identity fallback chain's "email local-part" source —
 * never the string "ANON" (Shell-UX-Spec §0). Returns null when there is no
 * session or no email claim (e.g. dev-adapter mode).
 */
export function getSignInEmail(): string | null {
  const token = getAccessToken();
  if (!token) return null;
  try {
    const payloadB64 = token.split(".")[1] ?? "";
    const pad = "=".repeat(-payloadB64.length % 4);
    const payload = JSON.parse(atob(payloadB64)) as { email?: string };
    return typeof payload.email === "string" && payload.email ? payload.email : null;
  } catch {
    return null;
  }
}

export function signOut(): void {
  if (typeof window !== "undefined")
    window.localStorage.removeItem(STORAGE_KEY);
}

function persist(session: AuthSession): void {
  if (typeof window !== "undefined") {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  }
}
