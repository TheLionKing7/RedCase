import { createFileRoute, Link } from "@tanstack/react-router";
import { useMemo } from "react";
import {
  Search,
  ShieldAlert,
  CalendarClock,
  Flame,
  Loader2,
  ArrowUpRight,
  Briefcase,
  Scale,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { getClearance } from "@/lib/auth/supabase";
import { useDeadlineEvents } from "@/lib/api/deadlines";
import type { DeadlineEvent } from "@/lib/api/deadlines";
import { useAnalyses } from "@/lib/api/workbench";
import type { Analysis } from "@/lib/api/workbench";

// Part 3 Slice 2 — role landing by clearance.
//
// The `_authed` pathless layout owns every authenticated surface; this is its home
// route (POST-login landing). getClearance() reads the JWT `app_metadata.clearance`
// claim and dispatches with fail-closed semantics (missing claim → STAFF → workbench):
//   - PARTNER / ADMIN  → Firm Dashboard (run-the-firm compose)
//   - SENIOR / ASSOCIATE / STAFF → Legal Workbench (do-the-work compose)
//
// The two surfaces compose EXISTING typed clients only (deadline events + analyses) plus
// quick links into the other authenticated pages — no new endpoint is invented here.

export const Route = createFileRoute("/_authed/home")({
  head: () => ({
    meta: [
      { title: "Home — RedCase" },
      {
        name: "description",
        content:
          "Your RedCase landing — firm command center for partners, legal workbench for practitioners.",
      },
    ],
  }),
  component: AuthenticatedHome,
});

const GLANCE_LINKS = [
  { to: "/search", label: "Vault Search", sub: "Dual-vault retrieval", icon: Search },
  { to: "/red-teamer", label: "Case Red-Teamer", sub: "Adversarial analysis", icon: ShieldAlert },
  { to: "/tracker", label: "Statutory Tracker", sub: "Deadline computation", icon: CalendarClock },
  { to: "/workbench", label: "Legal Workbench", sub: "Arguments · law · cases", icon: Briefcase },
] as const;

function AuthenticatedHome() {
  const clearance = getClearance();
  if (clearance === "PARTNER" || clearance === "ADMIN") return <FirmDashboard />;
  return <PractitionerLanding clearance={clearance} />;
}

function Stat({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <div className="panel p-5">
      <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">{label}</div>
      <div className={`mt-2 font-display text-3xl ${tone}`}>{value}</div>
    </div>
  );
}

function AnalysisStatus({ status }: { status: Analysis["status"] }) {
  const map: Record<string, { label: string; cls: string }> = {
    COMPLETE: { label: "Complete", cls: "bg-success/15 text-success" },
    RUNNING: { label: "Running", cls: "bg-steel/15 text-steel" },
    FAILED: { label: "Failed", cls: "bg-destructive/15 text-destructive" },
  };
  const s = map[status] ?? { label: "Needs review", cls: "bg-warning/15 text-warning" };
  return (
    <span className={`rounded-full px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest ${s.cls}`}>
      {s.label}
    </span>
  );
}

const PACK_LABEL: Record<string, string> = {
  ADVERSAL_BRIEF: "Adversarial Brief",
  SUMMONS_RESPONSE: "Summons Response",
  CONTRACT_REVIEW: "Contract Review",
};

function FirmDashboard() {
  const deadlines = useDeadlineEvents();
  const analyses = useAnalyses();

  const deadlineStats = useMemo(() => {
    const events = deadlines.data ?? [];
    const now = new Date();
    const todayIso = now.toISOString().slice(0, 10);
    const in14 = new Date(now.getTime() + 14 * 86400_000).toISOString().slice(0, 10);
    const overdue = events.filter(
      (e) => e.status !== "MISSED" && e.status !== "DISMISSED" && e.due_date < todayIso,
    ).length;
    const due14 = events.filter(
      (e) =>
        e.status !== "MISSED" &&
        e.status !== "DISMISSED" &&
        e.due_date >= todayIso &&
        e.due_date <= in14,
    ).length;
    const open = events.filter((e) => e.status !== "MISSED" && e.status !== "DISMISSED").length;
    const missed = events.filter((e) => e.status === "MISSED").length;
    return { overdue, due14, open, missed };
  }, [deadlines.data]);

  const upcoming = useMemo(() => {
    const events = deadlines.data ?? [];
    return [...events]
      .filter((e) => e.status !== "MISSED" && e.status !== "DISMISSED")
      .sort((a, b) => a.due_date.localeCompare(b.due_date))
      .slice(0, 6);
  }, [deadlines.data]);

  const recentAnalyses = useMemo(() => {
    const items = analyses.data ?? [];
    return [...items].sort((a, b) => a.created_at.localeCompare(b.created_at)).reverse().slice(0, 5);
  }, [analyses.data]);

  return (
    <AppShell eyebrow="Firm Command Center" title="Firm Dashboard">
      <div className="mx-auto max-w-7xl space-y-6">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Stat label="Overdue deadlines" value={String(deadlineStats.overdue)} tone="text-destructive" />
          <Stat label="Due in 14 days" value={String(deadlineStats.due14)} tone="text-warning" />
          <Stat label="Open workstreams" value={String(deadlineStats.open)} tone="text-steel" />
          <Stat label="Missed" value={String(deadlineStats.missed)} tone="text-muted-foreground" />
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          <section className="panel p-6">
            <h2 className="flex items-center gap-2 text-lg font-semibold">
              <Flame className="size-4 text-gold" /> Upcoming deadlines
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Firm-wide statutory and court deadlines, soonest first.
            </p>
            {deadlines.isPending ? (
              <div className="mt-4 flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" /> Loading deadlines…
              </div>
            ) : deadlines.isError || upcoming.length === 0 ? (
              <div className="mt-4 rounded-lg border border-border/60 p-4 text-sm text-muted-foreground">
                {deadlines.isError ? "Deadline service unavailable right now." : "No deadlines on the firm calendar yet."}
              </div>
            ) : (
              <ul className="mt-4 space-y-2">
                {upcoming.map((e) => (
                  <li key={e.id} className="flex items-center justify-between gap-3 rounded-lg border border-border/60 px-4 py-3">
                    <div>
                      <div className="text-sm font-medium">{e.description}</div>
                      <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                        {e.event_type.replaceAll("_", " ")}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="font-mono text-sm">
                        {new Date(e.due_date).toLocaleDateString("en-GB", { day: "2-digit", month: "short" })}
                      </div>
                      <div className="font-mono text-[10px] text-muted-foreground">due</div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="panel p-6">
            <h2 className="flex items-center gap-2 text-lg font-semibold">
              <Scale className="size-4 text-gold" /> Recent workbench analyses
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Latest adversarial briefs and reviews across the firm.
            </p>
            {analyses.isPending ? (
              <div className="mt-4 flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" /> Loading analyses…
              </div>
            ) : analyses.isError || recentAnalyses.length === 0 ? (
              <div className="mt-4 rounded-lg border border-border/60 p-4 text-sm text-muted-foreground">
                {analyses.isError ? "Workbench service unavailable right now." : "No workbench analyses have been run yet."}
              </div>
            ) : (
              <ul className="mt-4 space-y-2">
                {recentAnalyses.map((a) => (
                  <li key={a.analysis_id} className="flex items-center justify-between gap-3 rounded-lg border border-border/60 px-4 py-3">
                    <div>
                      <div className="text-sm font-medium">{PACK_LABEL[a.prompt_pack] ?? a.prompt_pack}</div>
                      <div className="font-mono text-[10px] text-muted-foreground">
                        {new Date(a.created_at).toLocaleDateString("en-GB")}
                      </div>
                    </div>
                    <AnalysisStatus status={a.status} />
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>

        <QuickLinks title="Open a workspace" />
      </div>
    </AppShell>
  );
}

function PractitionerLanding({ clearance }: { clearance: string }) {
  const analyses = useAnalyses();

  const myRecent = useMemo(() => {
    const items = analyses.data ?? [];
    return [...items].sort((a, b) => a.created_at.localeCompare(b.created_at)).reverse().slice(0, 4);
  }, [analyses.data]);

  return (
    <AppShell eyebrow="Legal Workbench" title={`Welcome, ${clearance}`}>
      <div className="mx-auto max-w-6xl space-y-6">
        <section className="panel glow-gold p-6">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.28em] text-gold">
                {clearance} · redcase
              </div>
              <h2 className="mt-1 text-2xl font-semibold">
                Workbench — your matters, your authority
              </h2>
              <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
                Run adversarial briefs, summons responses and contract reviews, then verify
                against Nigerian law with page-pinned citations. Pick up where you left off.
              </p>
            </div>
            <Link
              to="/workbench"
              className="inline-flex items-center gap-2 rounded-lg bg-gold px-4 py-2.5 text-sm font-semibold text-background transition-all duration-200 hover:bg-gold/90 hover:shadow-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/50"
            >
              Open Workbench <ArrowUpRight className="size-4" />
            </Link>
          </div>
        </section>

        {!analyses.isPending &&
          !analyses.isError &&
          (myRecent.length > 0 ? (
            <section className="panel p-6">
              <h2 className="text-lg font-semibold">Your recent analyses</h2>
              <ul className="mt-4 grid gap-3 sm:grid-cols-2">
                {myRecent.map((a) => (
                  <li key={a.analysis_id} className="flex items-center justify-between gap-3 rounded-lg border border-border/60 px-4 py-3">
                    <div>
                      <div className="text-sm font-medium">{PACK_LABEL[a.prompt_pack] ?? a.prompt_pack}</div>
                      <div className="font-mono text-[10px] text-muted-foreground">
                        {new Date(a.created_at).toLocaleDateString("en-GB")}
                      </div>
                    </div>
                    <AnalysisStatus status={a.status} />
                  </li>
                ))}
              </ul>
            </section>
          ) : (
            <section className="panel border-dashed border-steel/30 p-6">
              <p className="text-sm text-muted-foreground">
                No workbench analyses yet. Run your first from the Workbench.
              </p>
            </section>
          ))}

        <QuickLinks title="Jump to a tool" />
      </div>
    </AppShell>
  );
}

function QuickLinks({ title }: { title: string }) {
  return (
    <section>
      <h2 className="font-mono text-[10px] uppercase tracking-[0.28em] text-muted-foreground">
        {title}
      </h2>
      <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {GLANCE_LINKS.map(({ to, label, sub, icon: Icon }) => (
          <Link
            key={to}
            to={to}
            className="group flex items-start gap-3 rounded-xl border border-border/70 bg-background/60 p-4 transition-all duration-200 hover:border-gold/50 hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/40"
          >
            <Icon className="mt-0.5 size-4 shrink-0 text-steel transition-colors group-hover:text-gold" />
            <span>
              <span className="block text-sm font-medium">{label}</span>
              <span className="mt-0.5 block text-[11px] text-muted-foreground">{sub}</span>
            </span>
          </Link>
        ))}
      </div>
    </section>
  );
}
