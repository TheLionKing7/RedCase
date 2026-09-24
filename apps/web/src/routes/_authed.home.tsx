import { createFileRoute, Link } from "@tanstack/react-router";
import { useMemo, useState } from "react";
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
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {/* Time logger — Clock-in / Clock-out. Attendance is Phase 4, so this is a
          quick in-place capture affordance (local state), not a billing entry. */}
      <TimeLogger />

      {/* Partner's Locker / Inbox — my purview, a filtered view over the firm vault. */}
      <MenuLink
        to="/workbench"
        icon={Briefcase}
        label="Partner's Locker"
        sub="Inbox · assignments routed to me"
      />

      {/* Scheduler — day-to-day activities, meetings, court-sittings, events. Builds on
          the deadline engine; until then Tracker shows the pending-validation state. */}
      <MenuLink
        to="/tracker"
        icon={BookOpenCheck}
        label="Scheduler"
        sub="Meetings · court-sittings · events"
      />

      {/* My matters / My deadlines — personal workload surfaces. */}
      <MenuLink
        to="/workbench"
        icon={Scale}
        label="My matters / My deadlines"
        sub="Personal workload · send to workbench"
      />
    </div>
  );
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
