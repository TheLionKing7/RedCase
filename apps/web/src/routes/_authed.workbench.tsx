import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import {
  LayoutDashboard,
  Swords,
  Scale,
  Gavel,
  Loader2,
  ShieldAlert,
  CheckCircle2,
  Clock,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { CoachMarks } from "@/components/CoachMarks";
import type { CoachStep } from "@/components/CoachMarks";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { useAnalyses, useAnalysis } from "@/lib/api/workbench";
import type { Analysis } from "@/lib/api/workbench";
import {
  PERSONA_TONES,
  usePersona,
  usePracticeAreas,
  useSavePersona,
} from "@/lib/api/persona";
import { type TonePreset } from "@/lib/api/persona";

export const Route = createFileRoute("/_authed/workbench")({
  head: () => ({
    meta: [
      { title: "Legal Workbench — RedCase" },
      {
        name: "description",
        content:
          "Tabbed legal workspace: Overview, Arguments, Similar Cases and Law across briefs, summons and contracts, with per-section confidence and pinned citations.",
      },
      { property: "og:title", content: "Legal Workbench — RedCase" },
      {
        property: "og:description",
        content:
          "Aetoes Legal workbench — overview, adversarial arguments, similar cases and legal authority in one workspace.",
      },
    ],
  }),
  component: Workbench,
});

type WorkbenchTab = "overview" | "arguments" | "similar" | "law";

const PACK_LABEL: Record<string, string> = {
  ADVERSAL_BRIEF: "Adversarial Brief",
  SUMMONS_RESPONSE: "Summons Response",
  CONTRACT_REVIEW: "Contract Review",
};

function StatusBadge({ status }: { status: Analysis["status"] }) {
  if (status === "COMPLETE") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-success/15 px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest text-success">
        <CheckCircle2 className="size-3" /> Complete
      </span>
    );
  }
  if (status === "RUNNING") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-steel/15 px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest text-steel">
        <Clock className="size-3" /> Running
      </span>
    );
  }
  if (status === "FAILED") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-destructive/15 px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest text-destructive">
        <ShieldAlert className="size-3" /> Failed
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-warning/15 px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest text-warning">
      Needs Review
    </span>
  );
}

function Workbench() {
  const analyses = useAnalyses();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const coachSteps: CoachStep[] = [
    {
      title: "Upload a document to begin",
      body: "Every analysis starts with a source — a brief, summons, or contract. Upload it from a matter or the vault, then pick a prompt pack.",
    },
    {
      title: "Run an analysis",
      body: "Pick Adversarial Brief, Summons Response, or Contract Review. RedCase drafts the section and verifies it against Nigerian law.",
    },
    {
      title: "Verify every claim",
      body: "Check the Critic verdict, per-section confidence, and pinned authorities before you rely on anything. Nothing is invented.",
    },
  ];

  return (
    <AppShell eyebrow="Legal Workbench" title="Workbench">
      <CoachMarks surface="workbench" steps={coachSteps} />
      <div className="mx-auto max-w-7xl space-y-6">
        <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
          <aside className="space-y-3">
            <div className="font-mono text-[10px] uppercase tracking-[0.28em] text-muted-foreground">
              My Analyses
            </div>
            {analyses.isPending ? (
              <div className="panel flex items-center gap-2 p-4 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" /> Loading your
                workbench…
              </div>
            ) : analyses.isError ? (
              <div className="panel border-destructive/40 p-4 text-sm text-destructive">
                Could not load analyses.
              </div>
            ) : (
              <div className="space-y-2">
                {analyses.data!.length === 0 && (
                  <div className="panel p-4 text-sm text-muted-foreground">
                    No analyses yet. Run an analysis from a matter or vault to
                    see it here.
                  </div>
                )}
                {analyses.data!.map((a) => (
                  <button
                    key={a.analysis_id}
                    onClick={() => setSelectedId(a.analysis_id)}
                    className={`panel w-full p-4 text-left transition-colors ${selectedId === a.analysis_id ? "glow-gold border-gold/50" : "hover:border-steel/40"}`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-medium">
                        {PACK_LABEL[a.prompt_pack] ?? a.prompt_pack}
                      </span>
                      <StatusBadge status={a.status} />
                    </div>
                    <div className="mt-2 truncate font-mono text-[11px] text-muted-foreground">
                      {a.analysis_id.slice(0, 8)} ·{" "}
                      {new Date(a.created_at).toLocaleDateString("en-GB")}
                    </div>
                    <div className="mt-1 truncate font-mono text-[10px] text-muted-foreground/70">
                      doc {a.document_id.slice(0, 8)}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </aside>
          <section>
            {selectedId ? (
              <AnalysisWorkspace id={selectedId} />
            ) : (
              <div className="panel flex flex-col items-center justify-center gap-3 px-6 py-20 text-center">
                <LayoutDashboard className="size-8 text-steel" />
                <p className="max-w-sm text-sm text-muted-foreground">
                  Select an analysis to open its tabbed workspace — Overview,
                  Arguments, Similar Cases and Law.
                </p>
              </div>
            )}
          </section>
        </div>
      </div>
      <PersonaSettings />
    </AppShell>
  );
}

function PersonaSettings() {
  const persona = usePersona();
  const save = useSavePersona();
  const practiceAreas = usePracticeAreas();
  const [agentName, setAgentName] = useState<string>("Assistant");
  const [tone, setTone] = useState<TonePreset>("PROFESSIONAL");
  const [rules, setRules] = useState("");
  const [tags, setTags] = useState("");
  const [flash, setFlash] = useState<string | null>(null);
  const [flashType, setFlashType] = useState<"ok" | "err">("ok");

  useEffect(() => {
    if (persona.data) {
      setAgentName(persona.data.agent_name ?? "Assistant");
      setTone(persona.data.tone_preset ?? "PROFESSIONAL");
      setRules(persona.data.rules_of_engagement ?? "");
      setTags(persona.data.practice_areas?.join(", ") ?? "");
    }
  }, [persona.data]);

  return (
    <section className="mx-auto mt-8 max-w-5xl space-y-6 border-t border-border pt-8">
      <div>
        <div className="font-mono text-[10px] uppercase tracking-[0.28em] text-steel">
          Assistant Persona
        </div>
        <h2 className="mt-1 text-xl font-semibold">How your assistant communicates</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Saved per user. Shapes HOW the assistant writes — it can never change what it may cite.
        </p>
      </div>

      {flash && (
        <div
          className={`rounded-lg border px-3 py-2 text-sm ${
            flashType === "ok"
              ? "border-success/40 bg-success/10 text-success"
              : "border-destructive/40 bg-destructive/10 text-destructive"
          }`}
        >
          {flash}
        </div>
      )}

      {(persona.isLoading || practiceAreas.isLoading) && (
        <div className="panel flex items-center gap-2 p-4 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> Loading your persona…
        </div>
      )}

      {persona.data && practiceAreas.data && (
        <form
          className="panel space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate(
              {
                agent_name: agentName.trim() || "Assistant",
                tone_preset: tone,
                rules_of_engagement: rules.trim() || null,
                practice_areas: tags.split(",").map((s) => s.trim()).filter(Boolean),
              },
              {
                onSuccess: () => { setFlash("Persona saved."); setFlashType("ok"); },
                onError: (err: unknown) => {
                  setFlash(
                    err instanceof Error ? `Could not save: ${err.message}` : "Could not save persona.",
                  );
                  setFlashType("err");
                },
              },
            );
          }}
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">Agent name</span>
              <input value={agentName} onChange={(e) => setAgentName(e.target.value)}
                className="mt-1.5 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" placeholder="Assistant" />
            </label>
            <label className="block">
              <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">Tone preset</span>
              <select value={tone} onChange={(e) => setTone(e.target.value as TonePreset)}
                className="mt-1.5 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm">
                {PERSONA_TONES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </label>
          </div>
          <label className="block">
            <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">Rules of engagement</span>
            <textarea value={rules} onChange={(e) => setRules(e.target.value)} rows={3}
              className="mt-1.5 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
              placeholder="How should the assistant approach matters?" />
          </label>
          <label className="block">
            <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">Practice areas (research lens)</span>
            <input value={tags} onChange={(e) => setTags(e.target.value)}
              className="mt-1.5 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" placeholder="Litigation, Tax" />
          </label>
          <button type="submit" disabled={save.isPending}
            className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-5 py-2 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold disabled:opacity-60">
            {save.isPending ? <Loader2 className="size-4 animate-spin" /> : <CheckCircle2 className="size-4" />}
            {save.isPending ? "Saving…" : "Save persona"}
          </button>
        </form>
      )}
    </section>
  );
}

function AuthorityChips({ authority }: { authority: unknown }) {
  const list = Array.isArray(authority) ? (authority as string[]) : [];
  if (list.length === 0) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {list.map((a) => (
        <span
          key={a}
          className="rounded-full border border-steel/40 px-2 py-0.5 font-mono text-[10px] text-steel"
        >
          {a}
        </span>
      ))}
    </div>
  );
}

function ReviewFlag({ manual }: { manual?: boolean }) {
  if (!manual) return null;
  return (
    <span className="ml-2 rounded-full bg-warning/15 px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest text-warning">
      [MANUAL REVIEW]
    </span>
  );
}

function AnalysisWorkspace({ id }: { id: string }) {
  const analysis = useAnalysis(id);
  const [tab, setTab] = useState<WorkbenchTab>("overview");

  if (analysis.isPending) {
    return (
      <div className="panel flex items-center gap-2 p-6 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" /> Loading analysis…
      </div>
    );
  }
  if (analysis.isError || !analysis.data) {
    return (
      <div className="panel border-destructive/40 p-6 text-sm text-destructive">
        Could not load this analysis.
      </div>
    );
  }

  const a = analysis.data as any;
  const output: any = a.output ?? {};
  const sections = output.sections ?? {};
  const verdict = output.critic_verdict ?? {};

  return (
    <div className="space-y-4">
      <div className="panel glow-gold p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.28em] text-gold">
              {PACK_LABEL[a.prompt_pack] ?? a.prompt_pack}
            </div>
            <h2 className="mt-1 text-xl font-semibold">
              Analysis {a.analysis_id.slice(0, 8)}
            </h2>
          </div>
          <StatusBadge status={a.status} />
        </div>
        {a.error && <p className="mt-3 text-sm text-destructive">{a.error}</p>}
        {typeof verdict.pass === "boolean" && (
          <p className="mt-3 font-mono text-[11px] text-muted-foreground">
            Critic verdict: {verdict.pass ? "PASS" : "FAIL"} · regenerations{" "}
            {verdict.regenerations ?? 0}
            {Array.isArray(verdict.downgraded_sections) &&
              verdict.downgraded_sections.length > 0 &&
              ` · downgraded: ${verdict.downgraded_sections.join(", ")}`}
          </p>
        )}
      </div>

      <Tabs
        value={tab}
        onValueChange={(v) => setTab(v as WorkbenchTab)}
        className="w-full"
      >
        <TabsList className="h-auto w-full justify-start rounded-none border-b bg-transparent p-0">
          {(
            [
              { id: "overview", label: "Overview", icon: LayoutDashboard },
              { id: "arguments", label: "Arguments", icon: Swords },
              { id: "similar", label: "Similar Cases", icon: Scale },
              { id: "law", label: "Law", icon: Gavel },
            ] as const
          ).map((t) => (
            <TabsTrigger
              key={t.id}
              value={t.id}
              className="gap-2 rounded-none border-b-2 border-transparent data-[state=active]:border-gold data-[state=active]:shadow-none"
            >
              <t.icon className="size-4 text-steel" />
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value="overview" className="mt-4">
          <OverviewTab output={output} sections={sections} />
        </TabsContent>
        <TabsContent value="arguments" className="mt-4">
          <ArgumentsTab sections={sections} />
        </TabsContent>
        <TabsContent value="similar" className="mt-4">
          <SimilarTab output={output} />
        </TabsContent>
        <TabsContent value="law" className="mt-4">
          <LawTab output={output} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function OverviewTab({
  output,
  sections,
}: {
  output: any;
  sections: any;
}) {
  const overview = sections.overview ?? {};

  const items: Array<[string, string]> = [];
  if (typeof overview.court === "string" && overview.court)
    items.push(["Court", overview.court]);
  if (typeof overview.case_number === "string" && overview.case_number)
    items.push(["Case No.", overview.case_number]);
  if (typeof overview.served_on === "string" && overview.served_on)
    items.push(["Served on", overview.served_on]);
  if (typeof overview.return_date === "string" && overview.return_date)
    items.push(["Return date", overview.return_date]);
  if (typeof overview.claimant === "string" && overview.claimant)
    items.push(["Claimant", overview.claimant]);
  if (typeof overview.defendant === "string" && overview.defendant)
    items.push(["Defendant", overview.defendant]);
  if (typeof overview.claims_served === "number")
    items.push(["Claims served", String(overview.claims_served)]);
  if (typeof overview.agreement_date === "string" && overview.agreement_date)
    items.push(["Agreement date", overview.agreement_date]);
  if (typeof overview.clause_count === "number")
    items.push(["Clauses", String(overview.clause_count)]);
  if (overview.overall_risk && typeof overview.overall_risk === "string")
    items.push(["Overall risk", overview.overall_risk]);
  const parties = overview.parties ?? {};
  if (parties && typeof parties === "object") {
    Object.entries(parties).forEach(([k, v]) => {
      if (v) items.push([`Party: ${k}`, String(v)]);
    });
  }

  const headlineFlags = Array.isArray(overview.headline_flags)
    ? overview.headline_flags
    : [];
  const headlineRisks = Array.isArray(overview.headline_risks)
    ? overview.headline_risks
    : [];
  const flags = headlineFlags.length > 0 ? headlineFlags : headlineRisks;

  return (
    <div className="space-y-4">
      <div className="panel p-5">
        <div className="font-mono text-[10px] uppercase tracking-[0.28em] text-muted-foreground">
          Overview
        </div>
        {items.length === 0 ? (
          <p className="mt-3 text-sm text-muted-foreground">
            {output.source_document_id
              ? `Document ${String(output.source_document_id).slice(0, 8)} analyzed${output.generated_at ? ` on ${new Date(String(output.generated_at)).toLocaleDateString("en-GB")}` : ""}.`
              : "No overview fields for this pack."}
          </p>
        ) : (
          <dl className="mt-3 grid gap-x-8 gap-y-2 sm:grid-cols-2">
            {items.map(([k, v], i) => (
              <div key={i}>
                <dt className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                  {k}
                </dt>
                <dd className="mt-0.5 text-sm">{v}</dd>
              </div>
            ))}
          </dl>
        )}
        {flags.length > 0 && (
          <ul className="mt-4 space-y-1.5">
            {flags.map((f: unknown, i: number) => (
              <li key={i} className="text-sm text-warning">
                • {String(f)}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function ArgumentsTab({ sections }: { sections: any }) {
  const rows = sections.arguments ?? [];
  return (
    <div className="space-y-4">
      {rows.length === 0 ? (
        <div className="panel p-5 text-sm text-muted-foreground">
          No arguments produced for this analysis.
        </div>
      ) : (
        rows.map((r: any, i: number) => (
          <div key={i} className="panel p-5">
            <div className="flex items-start justify-between gap-3">
              <p className="text-sm font-medium">
                {r.claim || r.clause || r.argument || `Item ${i + 1}`}
                <ReviewFlag manual={r.manual_review} />
              </p>
              {typeof r.risk === "string" && (
                <span className="rounded-full bg-steel/10 px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest text-steel">
                  {r.risk}
                </span>
              )}
              {typeof r.response_deadline === "string" &&
                r.response_deadline && (
                  <span className="font-mono text-[11px] text-steel">
                    {r.response_deadline}
                  </span>
                )}
            </div>
            {r.strategy && (
              <p className="mt-2 text-sm text-muted-foreground">{r.strategy}</p>
            )}
            {r.our_counter && (
              <p className="mt-2 text-sm text-muted-foreground">
                {r.our_counter}
              </p>
            )}
            {r.basis && (
              <p className="mt-2 text-sm text-muted-foreground">{r.basis}</p>
            )}
            {r.rationale && (
              <p className="mt-2 text-sm text-muted-foreground">
                {r.rationale}
              </p>
            )}
            <AuthorityChips authority={r.authority} />
            {typeof r.confidence === "number" && (
              <p className="mt-2 font-mono text-[11px] text-muted-foreground">
                Confidence {(r.confidence * 100).toFixed(0)}%
              </p>
            )}
          </div>
        ))
      )}
    </div>
  );
}

function collectAuthorities(sections: any): string[] {
  const out = new Set<string>();
  const args = sections.arguments ?? [];
  args.forEach((r: any) => {
    (r.authority ?? []).forEach((a: string) => out.add(a));
  });
  const law = sections.law ?? [];
  law.forEach((p: any) => {
    (p.authority ?? []).forEach((a: string) => out.add(a));
  });
  return [...out];
}

function SimilarTab({ output }: { output: any }) {
  const sections = (output.sections ?? {}) as any;
  const list = collectAuthorities(sections);
  return (
    <div className="space-y-4">
      <div className="panel p-5">
        <div className="font-mono text-[10px] uppercase tracking-[0.28em] text-muted-foreground">
          Similar Cases &amp; Authorities
        </div>
        {list.length === 0 ? (
          <p className="mt-3 text-sm text-muted-foreground">
            No authorities were pinned to this analysis. Retrieval returned no
            similar cases.
          </p>
        ) : (
          <div className="mt-3 space-y-2">
            {list.map((id) => (
              <div
                key={id}
                className="flex items-center gap-3 rounded-lg border border-steel/30 px-3 py-2.5"
              >
                <Scale className="size-4 shrink-0 text-steel" />
                <span className="font-mono text-xs">
                  {id.startsWith("A:") ? "Vault A" : "Vault B"} · {id}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function LawTab({ output }: { output: any }) {
  const sections = (output.sections ?? {}) as any;
  const points = sections.law ?? [];
  return (
    <div className="space-y-4">
      {points.length === 0 ? (
        <div className="panel p-5 text-sm text-muted-foreground">
          No law points produced for this analysis.
        </div>
      ) : (
        points.map((p: any, i: number) => (
          <div key={i} className="panel p-5">
            <p className="text-sm font-medium">
              <Gavel className="mr-2 inline size-4 text-gold" />
              {p.point}
            </p>
            <AuthorityChips authority={p.authority} />
            {typeof p.confidence === "number" && (
              <p className="mt-2 font-mono text-[11px] text-muted-foreground">
                Confidence {(p.confidence * 100).toFixed(0)}%
              </p>
            )}
          </div>
        ))
      )}
    </div>
  );
}
