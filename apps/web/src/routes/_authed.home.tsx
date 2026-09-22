import { createFileRoute, Link } from "@tanstack/react-router";
import { useMemo } from "react";
import {
  Search,
  ShieldAlert,
  CalendarClock,
  ArrowUpRight,
  Briefcase,
  Scale,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { CoachMarks } from "@/components/CoachMarks";
import { getClearance } from "@/lib/auth/supabase";
import { useAnalyses } from "@/lib/api/workbench";
import type { Analysis } from "@/lib/api/workbench";

// Part 3 Slice 2 — role landing by clearance.
//
// The `_authed` pathless layout owns every authenticated surface; this is its home
// route (POST-login landing).
//
// §8.5 (audit H3): admin capability is an ORTHOGONAL, grantable flag (JWT
// `app_metadata.is_firm_admin`), NOT derived from clearance. So home dispatches
// EVERYONE to the practitioner workbench compose; the run-the-firm surface lives on
// its own admin-gated route (`/firm-command`) and is surfaced to admins only via the
// AppShell nav.
//
// This compose uses EXISTING typed clients only (analyses) plus quick links into the
// other authenticated pages — no new endpoint is invented here.

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
            title: "Jump straight to work",
            body: "Open Vault Search, the Workbench, the Red-Teamer or the Tracker from here.",
          },
        ]}
      />
      {/* §8.5: admin capability is orthagonal to clearance, so home is now the
          practitioner landing for EVERYONE. The run-the-firm surface moved to its own
          admin-gated route (/firm-command). */}
      <PractitionerLanding clearance={clearance} />
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
