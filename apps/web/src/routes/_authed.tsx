import { createFileRoute, redirect, Outlet } from "@tanstack/react-router";
import { getSession } from "@/lib/auth/supabase";

// Part 3 Slice 1 — auth boundary. Pathless layout that wraps every
// authenticated surface. The beforeLoad guard redirects to /signin when there is
// no Supabase session. VITE_API_DEV_ADAPTER=1 (dev/demo) bypasses the gate
// so unauthenticated browsing of the existing pages still works in dev; the gate is
// only ever enforced against a real Supabase project. getSession() reads
// localStorage, which is client-only, so this guard only redirects client-side —
// the server still renders the shell (SSR-safe), and the client guard enforces.

export const Route = createFileRoute("/_authed")({
  beforeLoad: () => {
    if (import.meta.env.VITE_API_DEV_ADAPTER === "1") return;
    // Client-only: localStorage isn't available during SSR.
    if (typeof window === "undefined") return;
    if (!getSession()) {
      throw redirect({ to: "/signin" });
    }
  },
  component: Outlet,
});
