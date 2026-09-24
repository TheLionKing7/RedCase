import { createFileRoute, Link } from "@tanstack/react-router";
import { useMemo, useState, type ReactNode } from "react";
import {
  ArrowUpRight,
  Briefcase,
  Scale,
  Clock,
  BookOpenCheck,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { CoachMarks } from "@/components/CoachMarks";
import { useIdentity } from "@/lib/identity";
import { useAnalyses } from "@/lib/api/workbench";
import type { Analysis } from "@/lib/api/workbench";
import { useDeadlineEvents } from "@/lib/api/deadlines";

// Part 3 Slice 2 — role landing by clearance, reworked for IA §2 (2026-09-23).
//
// Home is a calm, uncluttered practitioner landing. The eyebrow shows the user's REAL
// personnel identity from the firm register (members/me) — "Tosin Adebayo · Aetoes
// Legal" — never a hardcoded "ANON" or a bare clearance swing. That identity is the
// human's name, deliberately SEPARATE from the agent persona (unless the user authors it).
//
// §8.5: admin capability is an ORTHOGONAL, grantable flag (`is_firm_admin`), so
// home is the practitioner landing for EVERYONE. The Workbench hero card preserves the
// shortcut into the workbench; beneath it sits the Home menu (design doc §2: inbox,
// today's schedule, my deadlines, quick time-capture).
//
// This compose uses EXISTING typed clients only (analyses + members) plus links into the
// other authenticated pages — no invented endpoint.

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

function AuthenticatedHome() {
  return (
    <>
      <CoachMarks
        surface="home"
        icon={Scale}
        steps={[
          {
            title: "Your morning brief",
            body: "This is your RedCase landing — firm deadlines, recent analyses and your next priorities, all in one place after sign-in.",
          },
          {
            title: "Know what's due",
            body: "Keep an eye on overdue and upcoming statutory deadlines so nothing slips. Missed dates surface here so they can't hide.",
          },
          {
            title: "Jump to a tool",
            body: "Open the Workbench, Red-Teamer, or Vault Search from right here.",
          },
        ]}
      />
      <PractitionerLanding />
    </>
  );
}

function AnalysisStatus({ status }: { status: string }) {
  if (status === "COMPLETED") {
    return (
      <span className="rounded-full bg-success/15 px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest text-success">
        Completed
      </span>
    );
  }
  if (status === "PENDING") {
    return (
      <span className="rounded-full bg-warning/15 px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest text-warning">
        Pending
      </span>
    );
  }
  return (
    <span className="rounded-full bg-muted px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
      Needs review
    </span>
  );
}

const PACK_LABEL: Record<string, string> = {
  ADVERSARIAL_BRIEF: "Adversarial brief",
  SUMMONS_RESPONSE: "Summons response",
  CONTRACT_REVIEW: "Contract review",
  NIGERIAN_LAW_CHECK: "Nigerian law check",
  RED_TEAM: "Red-teamer",
};

function PractitionerLanding() {
  const analyses = useAnalyses();
  const identity = useIdentity();

  const eyebrow =
    identity.role && identity.firmName
      ? `${identity.name} · ${identity.role} · ${identity.firmName}`
      : identity.eyebrow;

  const myRecent = useMemo(() => {
    const items = analyses.data ?? [];
    return [...items].sort((a, b) => a.created_at.localeCompare(b.created_at)).reverse().slice(0, 4);
  }, [analyses.data]);

  return (
    <AppShell
      eyebrow={eyebrow}
      title={`Welcome, ${identity.name}`}
    >
      <div className="mx-auto max-w-6xl space-y-6">
        <section className="panel glow-gold p-6">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.28em] text-gold">
                {eyebrow}
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

        <HomeMenu />
      </div>
    </AppShell>
  );
}

/**
 * The practitioner's home menu — four quiet shortcuts under the hero. No header label:
 * the user knows they're on Home. Each card is a jump into a real surface; the design
 * document's Home = Inbox (assignments · today's schedule · my deadlines · quick
 * time-capture) maps onto these four.
 */
function HomeMenu() {
  const analyses = useAnalyses();
  const deadlineEvents = useDeadlineEvents();
  const today = new Date().toISOString().slice(0, 10);
  const events = deadlineEvents.data ?? [];
  const dueToday = events.filter((event) => event.due_date === today);
  const upcoming = events
    .filter((event) => event.due_date >= today && event.status !== "DISMISSED")
    .sort((a, b) => a.due_date.localeCompare(b.due_date));

  return (
    <section aria-labelledby="home-inbox-heading" className="space-y-3">
      <div className="flex items-end justify-between gap-4">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-steel">Your working day</p>
          <h2 id="home-inbox-heading" className="mt-1 font-display text-xl font-semibold">Inbox, deadlines &amp; matters</h2>
        </div>
        <Link to="/tracker" className="hidden text-xs font-medium text-gold transition-colors hover:text-foreground sm:inline">Open tracker <ArrowUpRight className="ml-1 inline size-3.5" /></Link>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <InboxCard icon={Briefcase} title="Inbox" detail="Assignments and recent work product">
          {analyses.isPending ? <CardState>Loading recent work…</CardState> : analyses.isError ? <CardState>Recent work is temporarily unavailable.</CardState> : analyses.data?.length ? <CardState>{analyses.data.length} recent analysis{analyses.data.length === 1 ? "" : "es"} available in the Workbench.</CardState> : <CardState>No work product yet. Start from the Workbench.</CardState>}
        </InboxCard>
        <InboxCard icon={BookOpenCheck} title="Today" detail="What needs attention today">
          {deadlineEvents.isPending ? <CardState>Loading your schedule…</CardState> : dueToday.length ? <EventList events={dueToday} /> : <CardState>No deadlines or hearings due today.</CardState>}
        </InboxCard>
        <InboxCard icon={Clock} title="My deadlines" detail="The next statutory dates in your queue">
          {deadlineEvents.isPending ? <CardState>Loading upcoming dates…</CardState> : upcoming.length ? <EventList events={upcoming.slice(0, 3)} /> : <CardState>No upcoming deadlines found.</CardState>}
        </InboxCard>
        <InboxCard icon={Scale} title="My matters" detail="Open your personal workbench view">
          <div className="flex items-center justify-between gap-3"><CardState>Matters are organised from the Workbench.</CardState><Link to="/workbench" className="shrink-0 rounded-lg bg-gold px-3 py-2 text-xs font-semibold text-background transition-all duration-200 hover:bg-gold/90 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold">Open</Link></div>
        </InboxCard>
      </div>
    </section>
  );
}

function InboxCard({ icon: Icon, title, detail, children }: { icon: typeof Scale; title: string; detail: string; children: ReactNode }) {
  return <article className="rounded-xl border border-border/70 bg-background/60 p-4 transition-all duration-200 hover:border-gold/50 hover:shadow-md"><div className="flex items-start gap-3"><div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-gold/10 text-gold"><Icon className="size-4.5" /></div><div className="min-w-0"><h3 className="text-sm font-semibold">{title}</h3><p className="mt-0.5 text-[11px] text-muted-foreground">{detail}</p></div></div><div className="mt-4">{children}</div></article>;
}

function CardState({ children }: { children: React.ReactNode }) { return <p className="text-xs leading-5 text-muted-foreground">{children}</p>; }

function EventList({ events }: { events: Array<{ id: string; description: string; due_date: string }> }) {
  return <ul className="space-y-2">{events.map((event) => <li key={event.id} className="flex items-start justify-between gap-3 text-xs"><span className="min-w-0 truncate text-foreground">{event.description}</span><time className="shrink-0 font-mono text-[10px] text-gold">{event.due_date}</time></li>)}</ul>;
}

function MenuLink({
  to,
  icon: Icon,
  label,
  sub,
}: {
  to: string;
  icon: typeof Scale;
  label: string;
  sub: string;
}) {
  return (
    <Link
      to={to}
      className="group flex items-center gap-4 rounded-xl border border-border/70 bg-background/60 p-4 transition-all duration-200 hover:border-gold/50 hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/40"
    >
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-gold/10 text-gold">
        <Icon className="size-5" />
      </div>
      <span className="min-w-0">
        <span className="block text-sm font-medium">{label}</span>
        <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">{sub}</span>
      </span>
    </Link>
  );
}

function TimeLogger() {
  const [clockedIn, setClockedIn] = useState(false);
  const toggle = () => setClockedIn((v) => !v);
  return (
    <div className="rounded-xl border border-border/70 bg-background/60 p-4 transition-all duration-200 hover:border-gold/50 hover:shadow-md">
      <div className="flex items-center gap-4">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-gold/10 text-gold">
          <Clock className="size-5" />
        </div>
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-medium">Time logger</span>
          <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">
            {clockedIn ? "Clocked in — tap Clock-out when done" : "Attendance capture"}
          </span>
        </span>
        <button
          type="button"
          onClick={toggle}
          className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/50 ${
            clockedIn
              ? "bg-rose-500/15 text-rose-300 hover:bg-rose-500/25"
              : "bg-gold text-background hover:bg-gold/90"
          }`}
        >
          {clockedIn ? "Clock-out" : "Clock-in"}
        </button>
      </div>
      <p className="mt-3 text-[11px] text-muted-foreground">
        Attendance (Phase 4) — this is a capture affordance, kept separate from billable
        time entries per design correction §1.2.
      </p>
    </div>
  );
}
