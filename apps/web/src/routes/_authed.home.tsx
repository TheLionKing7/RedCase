import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  ArrowUpRight,
  Briefcase,
  Scale,
  Clock,
  BookOpenCheck,
  ArrowLeft,
  ChevronRight,
  Loader2,
  Timer,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { CoachMarks } from "@/components/CoachMarks";
import { useIdentity } from "@/lib/identity";
import { useAnalyses } from "@/lib/api/workbench";
import type { Analysis } from "@/lib/api/workbench";
import { useDeadlineEvents } from "@/lib/api/deadlines";
import { apiGet, apiPost } from "@/lib/api/client";
import { useQuery } from "@tanstack/react-query";
import { useActivitySessions, useClockIn, useClockOut } from "@/lib/api/activity";
import type { ActivitySession } from "@/lib/api/activity";
import type { DeadlineEvent } from "@/lib/api/deadlines";
import { useCourtDiaryEntries } from "@/lib/api/court-diary";
import { sendAssistantMessage, useCreateThread, useThreads } from "@/lib/api/collaboration";

type HomePanel = "Inbox" | "Today" | "My deadlines" | "My matters" | "Time logger" | null;
type HomeInboxItem = { id: string; label: string; detail: string; kind: "analysis" | "deadline" | "matter" };
type HomeMatter = { id: string; matter_ref: string; status: string; progress_note: string | null };

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
      title="Welcome"
    >
      <div className="mx-auto max-w-6xl space-y-6 pb-16">
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
            <div className="flex flex-wrap items-center gap-3">
              <Link
                to="/workbench"
                className="inline-flex items-center gap-2 rounded-lg bg-gold px-4 py-2.5 text-sm font-semibold text-background transition-all duration-200 hover:bg-gold/90 hover:shadow-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/50"
              >
                Open Workbench <ArrowUpRight className="size-4" />
              </Link>
              <TimeLogger onOpen={() => window.dispatchEvent(new Event("redcase:open-time-panel"))} />
            </div>
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
  const matters = useQuery({ queryKey: ["matters", "my"], queryFn: () => apiGet<{ matters: HomeMatter[] }>("/v1/matters/my") });
  const courtDiary = useCourtDiaryEntries();
  const today = new Date().toISOString().slice(0, 10);
  const events = deadlineEvents.data ?? [];
  const dueToday = events.filter((event) => event.due_date === today);
  const upcoming = events
    .filter((event) => event.due_date >= today && event.status !== "DISMISSED")
    .sort((a, b) => a.due_date.localeCompare(b.due_date));
  const [visible, setVisible] = useState({ inbox: true, today: true, deadlines: true, matters: true });
  const [panel, setPanel] = useState<HomePanel>(null);
  const [matterId, setMatterId] = useState<string | null>(null);
  const panelItems: HomeInboxItem[] = [
    ...(analyses.data ?? []).slice(0, 8).map((item) => ({ id: item.analysis_id, label: PACK_LABEL[item.prompt_pack] ?? item.prompt_pack, detail: `${item.status.toLowerCase().replace("_", " ")} · ${new Date(item.created_at).toLocaleDateString("en-GB")}`, kind: "analysis" as const })),
    ...upcoming.slice(0, 8).map((item) => ({ id: item.id, label: item.description, detail: `Due ${item.due_date}`, kind: "deadline" as const })),
    ...(matters.data?.matters ?? []).slice(0, 8).map((item) => ({ id: item.id, label: item.matter_ref, detail: `${item.status}${item.progress_note ? ` · ${item.progress_note}` : ""}`, kind: "matter" as const })),
  ];
  useEffect(() => {
    const openTimePanel = () => setPanel("Time logger");
    window.addEventListener("redcase:open-time-panel", openTimePanel);
    return () => window.removeEventListener("redcase:open-time-panel", openTimePanel);
  }, []);

  return (
    <section aria-labelledby="home-inbox-heading" className="space-y-3">
      <div className="flex items-end justify-between gap-4">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-steel">Your working day</p>
          <h2 id="home-inbox-heading" className="mt-1 font-display text-xl font-semibold">Inbox, deadlines &amp; matters</h2>
        </div>
        <div className="flex items-center gap-3">
          <Link to="/tracker" className="hidden text-xs font-medium text-gold transition-colors hover:text-foreground sm:inline">Open tracker <ArrowUpRight className="ml-1 inline size-3.5" /></Link>
          <details className="relative">
            <summary className="cursor-pointer list-none rounded-lg border border-border px-3 py-2 text-xs font-medium text-muted-foreground transition-all duration-200 hover:border-gold/50 hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/50">Customize home</summary>
            <div className="absolute right-0 z-10 mt-2 w-48 rounded-xl border border-border bg-sidebar p-3 shadow-lg">
              <p className="mb-2 text-[10px] uppercase tracking-widest text-steel">Show widgets</p>
              <div className="space-y-2">
                {([ ["inbox", "Inbox"], ["today", "Today"], ["deadlines", "My deadlines"], ["matters", "My matters"] ] as const).map(([key, label]) => <label key={key} className="flex items-center gap-2 text-xs text-muted-foreground"><input type="checkbox" checked={visible[key]} onChange={() => setVisible((current) => ({ ...current, [key]: !current[key] }))} className="accent-gold" />{label}</label>)}
              </div>
            </div>
          </details>
        </div>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {visible.inbox && <InboxCard icon={Briefcase} title="Inbox" detail="Assignments and recent work product" onClick={() => setPanel("Inbox")}>
          {analyses.isPending ? <CardState>Loading recent work…</CardState> : analyses.isError ? <CardState>Recent work is temporarily unavailable.</CardState> : analyses.data?.length ? <CardState>{analyses.data.length} recent analysis{analyses.data.length === 1 ? "" : "es"} available in the Workbench.</CardState> : <CardState>No work product yet. Start from the Workbench.</CardState>}
        </InboxCard>}
        {visible.today && <InboxCard icon={BookOpenCheck} title="Today" detail="What needs attention today" onClick={() => setPanel("Today")}>
          {deadlineEvents.isPending ? <CardState>Loading your schedule…</CardState> : dueToday.length ? <EventList events={dueToday} /> : <CardState>No deadlines or hearings due today.</CardState>}
        </InboxCard>}
        {visible.deadlines && <InboxCard icon={Clock} title="My deadlines" detail="The next statutory dates in your queue" onClick={() => setPanel("My deadlines")}>
          {deadlineEvents.isPending ? <CardState>Loading upcoming dates…</CardState> : upcoming.length ? <EventList events={upcoming.slice(0, 3)} /> : <CardState>No upcoming deadlines found.</CardState>}
        </InboxCard>}
        {visible.matters && <InboxCard icon={Scale} title="My matters" detail="Your assigned matters" onClick={() => setPanel("My matters")}>
          {matters.isPending ? <CardState>Loading assigned matters…</CardState> : matters.isError ? <CardState>Matters are temporarily unavailable.</CardState> : <CardState>{matters.data?.matters.length ?? 0} assigned matter{matters.data?.matters.length === 1 ? "" : "s"}</CardState>}
        </InboxCard>}
      </div>
      <button type="button" data-open-time-panel onClick={() => setPanel("Time logger")} className="flex w-full items-center gap-3 rounded-xl border border-border/70 bg-background/60 p-4 text-left transition-all duration-200 hover:border-gold/50 hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-gold"><span className="flex size-10 items-center justify-center rounded-lg bg-gold/10 text-gold"><Timer className="size-5" /></span><span className="min-w-0 flex-1"><span className="block text-sm font-medium">Time logger</span><span className="block text-xs text-muted-foreground">Clock in, clock out, and review your sessions</span></span><ChevronRight className="size-4 text-muted-foreground" /></button>
      <HomeSidePanel panel={panel} onClose={() => setPanel(null)} items={panelItems} analyses={analyses.data ?? []} deadlines={upcoming} todayEvents={dueToday} diary={courtDiary.data ?? []} matters={matters.data?.matters ?? []} loading={analyses.isPending || deadlineEvents.isPending || matters.isPending || courtDiary.isPending} matterId={matterId} onMatter={setMatterId} />
    </section>
  );
}

function InboxCard({ icon: Icon, title, detail, children, onClick }: { icon: typeof Scale; title: string; detail: string; children: ReactNode; onClick: () => void }) {
  return <article className="rounded-xl border border-border/70 bg-background/60 p-4 transition-all duration-200 hover:border-gold/50 hover:shadow-md"><button type="button" onClick={onClick} aria-label={`Open ${title}`} className="flex w-full items-start gap-3 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-gold"><span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-gold/10 text-gold"><Icon className="size-4.5" /></span><span className="min-w-0 flex-1"><span className="block text-sm font-semibold">{title}</span><span className="mt-0.5 block text-[11px] text-muted-foreground">{detail}</span></span><ChevronRight className="mt-1 size-4 text-muted-foreground" /></button><div className="mt-4">{children}</div></article>;
}

function CardState({ children }: { children: React.ReactNode }) { return <p className="text-xs leading-5 text-muted-foreground">{children}</p>; }

function EventList({ events }: { events: Array<{ id: string; description: string; due_date: string }> }) {
  return <ul className="space-y-2">{events.map((event) => <li key={event.id} className="flex items-start justify-between gap-3 text-xs"><span className="min-w-0 truncate text-foreground">{event.description}</span><time className="shrink-0 font-mono text-[10px] text-gold">{event.due_date}</time></li>)}</ul>;
}

function HomeSidePanel({ panel, onClose, items, analyses, deadlines, todayEvents, diary, matters, loading, matterId, onMatter }: {
  panel: HomePanel; onClose: () => void; items: HomeInboxItem[]; analyses: Analysis[];
  deadlines: DeadlineEvent[]; todayEvents: DeadlineEvent[]; matters: HomeMatter[]; loading: boolean;
  diary: Array<{ id: string; title: string; entry_type: string; starts_at: string; status: string }>;
  matterId: string | null; onMatter: (id: string | null) => void;
}) {
  const sessions = useActivitySessions();
  const clockIn = useClockIn();
  const clockOut = useClockOut();
  const createThread = useCreateThread();
  const threads = useThreads();
  const [area, setArea] = useState("General");
  const [notice, setNotice] = useState("");
  if (!panel) return null;
  const isMatter = panel === "My matters" && matterId;
  const openActivity = (fn: () => void, ok: string) => { try { fn(); setNotice(ok); } catch { setNotice("Could not update this session."); } };
  const formatDuration = (seconds: number | null, started: string) => {
    const elapsed = seconds ?? Math.max(0, Math.floor((Date.now() - new Date(started).getTime()) / 1000));
    return `${Math.floor(elapsed / 3600)}h ${Math.floor((elapsed % 3600) / 60)}m`;
  };
  const sessionRows: ActivitySession[] = sessions.data?.sessions ?? [];
  const renderList = (list: HomeInboxItem[]) => loading ? <LoadingRows /> : list.length ? <ul className="divide-y divide-border">{list.map((item) => <li key={`${item.kind}:${item.id}`} className="flex flex-wrap items-center gap-3 py-4"><div className="min-w-0 flex-1"><p className="truncate text-sm font-medium">{item.label}</p><p className="mt-1 text-xs capitalize text-muted-foreground">{item.detail}</p></div><div className="flex shrink-0 flex-wrap gap-2">{item.kind === "analysis" && <><button type="button" onClick={() => void navigator.clipboard?.writeText(item.id)} className="rounded-lg border border-border px-3 py-1.5 text-xs transition-all duration-200 hover:border-gold/50">Copy reference</button>{threads.data?.length ? <details className="relative"><summary className="cursor-pointer list-none rounded-lg border border-border px-3 py-1.5 text-xs transition-all duration-200 hover:border-gold/50">Send to Assistant inbox</summary><div className="absolute right-0 z-10 mt-1 w-52 rounded-lg border border-border bg-sidebar p-1 shadow-lg">{threads.data.map((thread) => <button type="button" key={thread.thread_id} onClick={() => void sendAssistantMessage(thread.thread_id, `Home inbox reference: please review SmartBrief output ${item.id} (${item.label}) and assess its reasoning and authorities.`).then(() => setNotice(`Sent ${item.label} to “${thread.title}”.`), () => setNotice("Could not send reference to Assistant; retry."))} className="block w-full rounded-md px-2 py-2 text-left text-xs transition-all duration-200 hover:bg-surface">{thread.title}</button>)}</div></details> : <button type="button" disabled={createThread.isPending} onClick={() => createThread.mutate(`Review: ${item.label}`, { onSuccess: async (thread) => { try { await sendAssistantMessage(thread.thread_id, `Please review SmartBrief output ${item.id} (${item.label}) and assess its reasoning and authorities.`); setNotice("Created an Assistant thread and sent the output reference."); } catch { setNotice("Thread created, but sending the output reference failed."); } }, onError: () => setNotice("Could not create an Assistant thread; retry.") })} className="rounded-lg border border-border px-3 py-1.5 text-xs transition-all duration-200 hover:border-gold/50 disabled:opacity-60">Send to Assistant inbox</button>}</>}{item.kind === "deadline" && <Link to="/tracker" className="rounded-lg border border-border px-3 py-1.5 text-xs transition-all duration-200 hover:border-gold/50">Open tracker</Link>}{item.kind === "matter" ? <button type="button" onClick={() => { sessionStorage.setItem("redcase:workbench-matter", item.id); window.location.assign("/workbench"); }} className="rounded-lg bg-gold px-3 py-1.5 text-xs font-semibold text-background transition-all duration-200 hover:bg-gold/90">Select for Workbench upload</button> : <Link to="/workbench" className="rounded-lg bg-gold px-3 py-1.5 text-xs font-semibold text-background transition-all duration-200 hover:bg-gold/90">{item.kind === "analysis" ? "Open in Workbench" : "Promote to Workbench"}</Link>}</div></li>)}</ul> : <EmptyPanel>No items need your attention right now.</EmptyPanel>;
  return <div className="fixed inset-0 z-[65]" role="presentation"><button aria-label="Close workspace panel" className="absolute inset-0 bg-black/40" onClick={onClose} /><aside role="dialog" aria-modal="true" aria-label={panel} className="absolute inset-y-0 right-0 flex w-full max-w-2xl translate-x-0 flex-col border-l border-border bg-background shadow-2xl transition-transform duration-200"><header className="flex items-center gap-3 border-b border-border px-5 py-4"><button type="button" onClick={isMatter ? () => onMatter(null) : onClose} className="rounded-lg p-2 transition-all duration-200 hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold" aria-label="Back"><ArrowLeft className="size-4" /></button><div className="min-w-0 flex-1"><div className="font-mono text-[10px] uppercase tracking-[0.2em] text-steel">Workspace</div><h2 className="truncate text-lg font-semibold">{isMatter ? matters.find((matter) => matter.id === matterId)?.matter_ref ?? "Matter" : panel}</h2></div><button type="button" onClick={onClose} aria-label="Close" className="rounded-lg p-2 transition-all duration-200 hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold">×</button></header><div className="min-h-0 flex-1 overflow-y-auto p-5">
    {panel === "Inbox" && renderList(items)}
    {panel === "Today" && <div className="space-y-6"><p className="text-sm text-muted-foreground">Today's hearings, filings, research, reviews and meetings.</p>{todayEvents.length || diary.length ? <ul className="divide-y divide-border">{[...todayEvents.map((event) => ({ id: event.id, label: event.description, kind: event.event_type.replace("_", " "), at: "" })), ...diary.map((entry) => ({ id: entry.id, label: entry.title, kind: entry.entry_type.toLowerCase(), at: new Date(entry.starts_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) }))].map((item) => <li key={item.id} className="flex items-center justify-between gap-3 py-4"><span className="text-sm">{item.label}</span><span className="shrink-0 rounded-full bg-gold/10 px-2 py-1 text-[10px] font-medium capitalize text-gold">{item.at && `${item.at} · `}{item.kind}</span></li>)}</ul> : <EmptyPanel>No hearings, filings, research, reviews or meetings are scheduled today.</EmptyPanel>}</div>}
    {panel === "My deadlines" && (loading ? <LoadingRows /> : deadlines.length ? <ul className="divide-y divide-border">{deadlines.map((event) => <li key={event.id} className="flex flex-wrap items-center gap-3 py-4"><div className="min-w-0 flex-1"><p className="text-sm font-medium">{event.description}</p><p className="mt-1 font-mono text-xs text-gold">Due {event.due_date}</p></div><button type="button" disabled={createThread.isPending} onClick={() => { setNotice(""); createThread.mutate(`Deadline reminder: ${event.description}`, { onSuccess: async (thread) => { try { await sendAssistantMessage(thread.thread_id, `Reminder requested for ${event.description}, due ${event.due_date}. Please include this in my reminders.`); setNotice("Reminder recorded in your Assistant thread."); } catch { setNotice("Assistant thread created, but the reminder message could not be sent."); } }, onError: () => setNotice("Could not create reminder thread; retry.") }); }} className="rounded-lg border border-border px-3 py-2 text-xs transition-all duration-200 hover:border-gold/50 disabled:opacity-60">{createThread.isPending ? "Recording…" : "Set reminder"}</button><Link to="/workbench" className="rounded-lg bg-gold px-3 py-2 text-xs font-semibold text-background transition-all duration-200 hover:bg-gold/90">Open in Workbench</Link></li>)}</ul> : <EmptyPanel>No upcoming deadlines.</EmptyPanel>)}
    {panel === "My matters" && (!matterId ? loading ? <LoadingRows /> : matters.length ? <ul className="divide-y divide-border">{matters.map((matter) => <li key={matter.id}><button type="button" onClick={() => onMatter(matter.id)} className="flex w-full items-center gap-3 py-4 text-left transition-all duration-200 hover:text-gold"><span className="min-w-0 flex-1"><span className="block text-sm font-medium">{matter.matter_ref}</span><span className="mt-1 block text-xs text-muted-foreground">{matter.status}{matter.progress_note ? ` · ${matter.progress_note}` : ""}</span></span><ChevronRight className="size-4" /></button></li>)}</ul> : <EmptyPanel>No matters are assigned to you.</EmptyPanel> : <div className="panel space-y-4 p-5"><div><p className="font-mono text-[10px] uppercase tracking-widest text-steel">Matter overview</p><h3 className="mt-1 text-lg font-semibold">{matters.find((matter) => matter.id === matterId)?.matter_ref}</h3></div><p className="text-sm text-muted-foreground">{matters.find((matter) => matter.id === matterId)?.progress_note || "No progress note has been added."}</p><Link to="/workbench" className="inline-flex items-center gap-2 rounded-lg bg-gold px-4 py-2 text-sm font-semibold text-background transition-all duration-200 hover:bg-gold/90">Open matter tools <ChevronRight className="size-4" /></Link></div>)}
    {panel === "Time logger" && <section className="space-y-5"><div className="panel space-y-4 p-5"><label className="block"><span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Where are you working?</span><input value={area} onChange={(event) => setArea(event.target.value)} maxLength={160} className="mt-2 w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-gold" /></label>{sessionRows.some((session) => !session.ended_at) ? <button type="button" disabled={clockOut.isPending} onClick={() => clockOut.mutate(undefined, { onSuccess: () => setNotice("Clocked out. Session saved."), onError: () => setNotice("Could not clock out; retry.") })} className="inline-flex items-center gap-2 rounded-lg bg-destructive/15 px-4 py-2.5 text-sm font-semibold text-destructive transition-all duration-200 hover:bg-destructive/25 disabled:opacity-60"><Clock className="size-4" />{clockOut.isPending ? "Saving…" : "Clock-out"}</button> : <button type="button" disabled={clockIn.isPending || !area.trim()} onClick={() => clockIn.mutate(area.trim(), { onSuccess: () => setNotice("Clocked in. Your session has started."), onError: () => setNotice("Could not clock in; retry.") })} className="inline-flex items-center gap-2 rounded-lg bg-gold px-4 py-2.5 text-sm font-semibold text-background transition-all duration-200 hover:bg-gold/90 disabled:opacity-60"><Clock className="size-4" />{clockIn.isPending ? "Starting…" : "Clock-in"}</button>}{notice && <p role="status" className="text-sm text-muted-foreground">{notice}</p>}</div><div><h3 className="text-sm font-semibold">Recent sessions</h3>{sessions.isPending ? <LoadingRows /> : sessionRows.length ? <ul className="mt-3 divide-y divide-border">{sessionRows.map((session) => <li key={session.id} className="flex items-center justify-between gap-3 py-3"><span className="min-w-0"><span className="block truncate text-sm font-medium">{session.area}</span><span className="mt-1 block font-mono text-[10px] text-muted-foreground">{new Date(session.started_at).toLocaleString()}</span></span><span className="shrink-0 text-right text-xs text-muted-foreground">{session.ended_at ? new Date(session.ended_at).toLocaleTimeString() : "In progress"}<span className="block font-mono text-gold">{formatDuration(session.duration, session.started_at)}</span></span></li>)}</ul> : <EmptyPanel>No sessions yet. Clock in when you start work.</EmptyPanel>}</div><p className="text-xs text-muted-foreground">Personal activity tracking is stored separately from billable time entries.</p></section>}
    {notice && panel !== "Time logger" && <p role="status" className="mt-4 text-sm text-muted-foreground">{notice}</p>}
  </div></aside></div>;
}

function EmptyPanel({ children }: { children: ReactNode }) { return <div className="rounded-xl border border-dashed border-border p-8 text-center text-sm text-muted-foreground">{children}</div>; }
function LoadingRows() { return <div aria-busy="true" className="space-y-3">{[0, 1, 2].map((index) => <div key={index} className="h-14 animate-pulse rounded-lg bg-surface" />)}<span className="sr-only">Loading workspace items</span></div>; }

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

function TimeLogger({ onOpen }: { onOpen: () => void }) {
  const sessions = useActivitySessions();
  const clockIn = useClockIn();
  const clockOut = useClockOut();
  const active = sessions.data?.sessions.find((session) => !session.ended_at);
  const [area, setArea] = useState("General");
  const busy = clockIn.isPending || clockOut.isPending;
  return (
    <div className="min-w-[210px] rounded-xl border border-border/70 bg-background/60 p-3 transition-all duration-200 hover:border-gold/50 sm:min-w-[250px]">
      <div className="flex items-center gap-2"><Clock className="size-4 text-gold" /><span className="min-w-0 flex-1"><span className="block text-xs font-semibold">Time logger</span><span className="block truncate text-[10px] text-muted-foreground">{active ? `Working in ${active.area}` : "Attendance session"}</span></span></div>
      <div className="mt-2 flex gap-2"><input aria-label="Activity area" value={area} onChange={(event) => setArea(event.target.value)} maxLength={160} className="min-w-0 flex-1 rounded-md border border-border bg-background px-2 py-1.5 text-xs" /><button type="button" disabled={busy || (!active && !area.trim())} onClick={() => active ? clockOut.mutate() : clockIn.mutate(area.trim())} className={`shrink-0 rounded-lg px-3 py-1.5 text-xs font-semibold transition-all duration-200 disabled:opacity-60 ${active ? "bg-destructive/15 text-destructive hover:bg-destructive/25" : "bg-gold text-background hover:bg-gold/90"}`}>{busy ? <Loader2 className="size-3.5 animate-spin" /> : active ? "Clock-out" : "Clock-in"}</button></div>
      <button type="button" onClick={onOpen} className="mt-2 text-[10px] font-medium text-gold transition-all duration-200 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold">View time history <ArrowUpRight className="ml-1 inline size-3" /></button>
      {(clockIn.isError || clockOut.isError) && <p role="alert" className="mt-2 text-[10px] text-destructive">Could not update session. Please retry.</p>}
    </div>
  );
}
