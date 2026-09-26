import { createFileRoute, redirect, useRouter } from "@tanstack/react-router";
import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { Loader2, ShieldCheck, Mail, ArrowRight } from "lucide-react";
import {
  getSession,
  signInWithPassword,
  signInWithEmail,
  AuthError,
} from "@/lib/auth/supabase";

export const Route = createFileRoute("/signin")({
  beforeLoad: () => {
    if (
      typeof window !== "undefined" &&
      import.meta.env.VITE_API_DEV_ADAPTER !== "1" &&
      getSession()
    ) {
      throw redirect({ to: "/home" });
    }
  },
  component: SignInPage,
});

function SignInPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sentOtp, setSentOtp] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await signInWithPassword(email.trim(), password);
      await router.invalidate();
      // Slice 2: land on the clearance-aware home (PARTNER/ADMIN → firm
      // dashboard; SENIOR/ASSOCIATE/STAFF → workbench).
      await router.navigate({ to: "/home" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed");
      setBusy(false);
    }
  }

  async function onMagicLink() {
    setError(null);
    setBusy(true);
    try {
      await signInWithEmail(email.trim());
      setSentOtp(true);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not send sign-in email",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-md">
        <div className="mb-8 flex flex-col items-center text-center">
          <img
            src="/brand/redcase_firefly.svg"
            alt="RedCase"
            className="h-10 w-auto object-contain"
          />
          <h1 className="mt-4 font-display text-2xl font-semibold text-foreground">
            Sign in to RedCase
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Access your firm&rsquo;s workbench and vaults.
          </p>
        </div>

        <form
          onSubmit={onSubmit}
          className="space-y-4 rounded-xl border border-border bg-surface p-6 shadow-sm"
        >
          <label className="block">
            <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
              Email
            </span>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              className="mt-1.5 w-full rounded-lg border border-input bg-background/60 px-3 py-2.5 text-sm outline-none focus:border-gold"
              placeholder="you@yourfirm.com"
            />
          </label>

          <label className="block">
            <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
              Password
            </span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              className="mt-1.5 w-full rounded-lg border border-input bg-background/60 px-3 py-2.5 text-sm outline-none focus:border-gold"
              placeholder="••••••••"
            />
          </label>

          {error && (
            <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={busy}
            className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground transition-all duration-200 hover:bg-primary/90 disabled:opacity-50"
          >
            {busy ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <ShieldCheck className="size-4" />
            )}
            {busy ? "Signing in…" : "Sign in"}
          </button>

          <div className="relative py-1 text-center">
            <span className="px-2 text-[11px] uppercase tracking-widest text-muted-foreground">
              or
            </span>
          </div>

          <button
            type="button"
            onClick={onMagicLink}
            disabled={busy || !email}
            className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-input bg-background px-4 py-2.5 text-sm font-medium text-foreground transition-all duration-200 hover:bg-accent disabled:opacity-50"
          >
            <Mail className="size-4" />
            {sentOtp ? "Email sent — check your inbox" : "Send magic link"}
          </button>
        </form>

        <div className="mt-6 flex flex-col items-center gap-3">
          <Link
            to="/onboarding"
            className="inline-flex items-center gap-1.5 text-sm font-medium text-foreground transition-colors duration-200 hover:text-gold"
          >
            New firm? Start your firm <ArrowRight className="size-3.5" />
          </Link>
          <div className="flex items-center gap-3">
            <img
              src="/brand/redcase-mark-white.svg"
              alt=""
              aria-hidden="true"
              className="size-4 opacity-70"
            />
            <Link
              to="/"
              className="text-xs text-muted-foreground underline-offset-2 hover:text-gold hover:underline"
            >
              Back to redcase.xyz
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
