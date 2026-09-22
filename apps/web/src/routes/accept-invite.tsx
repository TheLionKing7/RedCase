import { createFileRoute, useNavigate, Link } from "@tanstack/react-router";
import { useState } from "react";
import { Loader2, ShieldCheck, PartyPopper } from "lucide-react";
import { acceptInvite } from "@/lib/api/accept-invite";

export const Route = createFileRoute("/accept-invite")({
  validateSearch: (search: Record<string, unknown>) => ({
    token: typeof search["token"] === "string" ? search["token"] : "",
  }),
  component: AcceptInvitePage,
});

function AcceptInvitePage() {
  const { token } = Route.useSearch();
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      const trimmed = name.trim();
      await acceptInvite(
        trimmed
          ? { token, password, name: trimmed }
          : { token, password },
      );
      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not accept invite");
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-4">
        <div className="w-full max-w-md text-center">
          <PartyPopper className="mx-auto size-12 text-gold" />
          <h1 className="mt-4 font-display text-2xl font-semibold text-foreground">
            Welcome to RedCase
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Your seat is active. Sign in to begin.
          </p>
          <button
            onClick={() => navigate({ to: "/signin" })}
            className="mt-6 inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-6 py-2.5 text-sm font-semibold text-primary-foreground transition-all duration-200 hover:bg-primary/90"
          >
            <ShieldCheck className="size-4" /> Go to sign in
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-md">
        <div className="mb-8 flex flex-col items-center text-center">
          <img
            src="/brand/redcase-mark-crimson.svg"
            alt="RedCase"
            className="size-12"
          />
          <h1 className="mt-4 font-display text-2xl font-semibold text-foreground">
            Accept your invite
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Set a password to activate your firm seat.
          </p>
        </div>

        {!token && (
          <div className="rounded-lg border border-warning/40 bg-warning/10 p-4 text-sm text-warning">
            This invite link is missing its token. Check the email from your
            firm administrator and open the full link.
          </div>
        )}

        <form
          onSubmit={onSubmit}
          className="space-y-4 rounded-xl border border-border bg-surface p-6 shadow-sm"
        >
          <label className="block">
            <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
              Full name
            </span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="mt-1.5 w-full rounded-lg border border-input bg-background/60 px-3 py-2.5 text-sm outline-none focus:border-gold"
              placeholder="Your name"
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
              autoComplete="new-password"
              minLength={8}
              className="mt-1.5 w-full rounded-lg border border-input bg-background/60 px-3 py-2.5 text-sm outline-none focus:border-gold"
              placeholder="At least 8 characters"
            />
          </label>
          <label className="block">
            <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
              Confirm password
            </span>
            <input
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              autoComplete="new-password"
              className="mt-1.5 w-full rounded-lg border border-input bg-background/60 px-3 py-2.5 text-sm outline-none focus:border-gold"
              placeholder="Re-enter password"
            />
          </label>

          {error && (
            <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={busy || !token}
            className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground transition-all duration-200 hover:bg-primary/90 disabled:opacity-50"
          >
            {busy ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <ShieldCheck className="size-4" />
            )}
            {busy ? "Activating…" : "Activate my seat"}
          </button>
        </form>

        <p className="mt-6 text-center text-xs text-muted-foreground">
          <Link
            to="/"
            className="text-foreground/80 underline-offset-2 hover:text-gold hover:underline"
          >
            Back to redcase.ai
          </Link>
        </p>
      </div>
    </div>
  );
}
