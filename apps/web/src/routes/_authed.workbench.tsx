import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
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
  GitBranch,
  Upload,
  MoreHorizontal,
  Inbox,
  ChevronRight,
  Printer,
  MessageSquare,
} from "lucide-react";
import { useIdentity } from "@/lib/identity";
import { AnalysisSectionCard } from "@/components/assistant/AnalysisSectionCard";
import { apiGet, apiPost, apiUpload } from "@/lib/api/client";
import { useQuery } from "@tanstack/react-query";
import { AppShell } from "@/components/AppShell";
import { CoachMarks } from "@/components/CoachMarks";
import type { CoachStep } from "@/components/CoachMarks";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  useAnalyses,
  useAnalysis,
  useChainAnalysis,
} from "@/lib/api/workbench";
import type { Analysis, PromptPack } from "@/lib/api/workbench";
import type { AssistantBench } from "@/lib/api/assistantContext";
import { useCourtDiaryEntries } from "@/lib/api/court-diary";
import { useMembership } from "@/lib/api/members";
import { sendAssistantMessage, useThreads } from "@/lib/api/collaboration";
import { useVaultQuery } from "@/lib/api/query";
import type { Citation, QueryResponse } from "@/lib/api/types";

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
  if (status === "DRAFT") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
        Draft
      </span>
    );
  }
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
  const navigate = useNavigate();
  const analyses = useAnalyses();
  const identity = useIdentity();
  const membership = useMembership();
  const threads = useThreads();
  const matters = useQuery({
    queryKey: ["matters", "my"],
    queryFn: () =>
      apiGet<{ matters: Array<{ id: string; matter_ref: string }> }>(
        "/v1/matters/my",
      ),
  });
  const diary = useCourtDiaryEntries();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [bench, setBench] = useState<AssistantBench>("SmartBrief");
  const [uploadMatter, setUploadMatter] = useState("");
  const [uploadMessage, setUploadMessage] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadedDocument, setUploadedDocument] = useState<{
    document_id: string;
    matter_id: string;
    title: string;
  } | null>(null);
  const [startingAnalysis, setStartingAnalysis] = useState(false);
  const [analysisPack, setAnalysisPack] =
    useState<PromptPack>("ADVERSAL_BRIEF");

  useEffect(() => {
    const requestedMatter = sessionStorage.getItem("redcase:workbench-matter");
    const availableMatters = matters.data?.matters ?? [];
    if (
      !requestedMatter ||
      !availableMatters.some((matter) => matter.id === requestedMatter)
    )
      return;
    setUploadMatter(requestedMatter);
    sessionStorage.removeItem("redcase:workbench-matter");
  }, [matters.data]);

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
    <AppShell
      eyebrow={`${membership.data?.full_name ?? identity.name}${membership.data?.role ? ` · ${membership.data.role}` : ""}`}
      title="Legal Workbench"
      assistantContext={{
        bench,
        ...(selectedId &&
        analyses.data?.find((item) => item.analysis_id === selectedId)
          ?.status === "COMPLETE"
          ? {
              reference: {
                type: "analysis",
                id: selectedId,
                label:
                  PACK_LABEL[
                    analyses.data.find(
                      (item) => item.analysis_id === selectedId,
                    )!.prompt_pack
                  ] ?? "SmartBrief output",
              },
            }
          : {}),
      }}
    >
      <CoachMarks surface="workbench" steps={coachSteps} />
      <div className="workbench-print mx-auto max-w-7xl space-y-6 pb-28">
        <div className="grid gap-6 lg:grid-cols-[300px_minmax(0,1fr)]">
          <aside className="workbench-tools space-y-3 print-hide">
            <div className="panel space-y-3 p-4">
              <div>
                <h2 className="text-sm font-semibold">Start with a source</h2>
                <p className="mt-1 text-xs text-muted-foreground">
                  {matters.data?.matters.find(
                    (matter) => matter.id === uploadMatter,
                  )?.matter_ref
                    ? `Selected matter: ${matters.data.matters.find((matter) => matter.id === uploadMatter)?.matter_ref}`
                    : "Upload a PDF or DOCX to an assigned matter, then choose the appropriate review."}
                </p>
              </div>
              <label className="flex cursor-pointer items-center justify-center gap-2 rounded-xl border border-dashed border-gold/50 bg-gold/5 px-4 py-3 text-sm font-medium text-gold transition-all duration-200 hover:bg-gold/10 focus-within:ring-2 focus-within:ring-gold">
                <Upload className="size-4" />
                {uploading ? "Uploading document…" : "Choose PDF or DOCX"}
                <input
                  type="file"
                  accept="application/pdf,.pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,.docx"
                  className="sr-only"
                  disabled={uploading}
                  onChange={async (event) => {
                    const input = event.currentTarget;
                    const file = input.files?.[0];
                    if (!file) return;
                    if (!uploadMatter) {
                      setUploadMessage(
                        "Choose a matter below before uploading.",
                      );
                      input.value = "";
                      return;
                    }
                    if (!/\.(pdf|docx)$/i.test(file.name)) {
                      setUploadMessage("Choose a PDF or DOCX document.");
                      input.value = "";
                      return;
                    }
                    setUploading(true);
                    setUploadMessage("");
                    try {
                      const result = await apiUpload<{
                        document_id: string;
                        duplicate?: boolean;
                      }>(
                        `/v1/matters/${uploadMatter}/documents?title=${encodeURIComponent(file.name)}`,
                        file,
                        () => undefined,
                      );
                      if (result.duplicate) {
                        const matterDocuments = await apiGet<{
                          documents: Array<{ document_id: string }>;
                        }>(`/v1/matters/${uploadMatter}/documents`);
                        if (
                          !matterDocuments.documents.some(
                            (document) =>
                              document.document_id === result.document_id,
                          )
                        ) {
                          setUploadedDocument(null);
                          setUploadMessage(
                            "This document already exists outside the selected matter. It was not attached or analyzed here.",
                          );
                          return;
                        }
                      }
                      setUploadedDocument({
                        document_id: result.document_id,
                        matter_id: uploadMatter,
                        title: file.name.replace(/\.(pdf|docx)$/i, ""),
                      });
                      setUploadMessage(
                        result.duplicate
                          ? "This document is already in the matter vault."
                          : "Document uploaded and ready for analysis.",
                      );
                    } catch (error) {
                      setUploadMessage(
                        error instanceof Error
                          ? error.message
                          : "Upload failed.",
                      );
                    } finally {
                      setUploading(false);
                      input.value = "";
                    }
                  }}
                />
              </label>
              {uploadedDocument && (
                <div className="rounded-lg border border-gold/30 bg-gold/5 p-3">
                  <p className="truncate text-xs font-medium">
                    {uploadedDocument.title}
                  </p>
                  <label className="mt-2 block text-[10px] uppercase tracking-widest text-muted-foreground">
                    Analysis pack
                  </label>
                  <div className="mt-1 flex gap-2">
                    <select
                      value={analysisPack}
                      onChange={(event) =>
                        setAnalysisPack(event.target.value as PromptPack)
                      }
                      aria-label="Analysis pack"
                      className="min-w-0 flex-1 rounded-lg border border-border bg-background px-2 py-2 text-xs"
                    >
                      <option value="ADVERSAL_BRIEF">Adversarial Brief</option>
                      <option value="SUMMONS_RESPONSE">Summons Response</option>
                      <option value="CONTRACT_REVIEW">Contract Review</option>
                    </select>
                    <Button
                      type="button"
                      size="sm"
                      disabled={startingAnalysis}
                      onClick={async () => {
                        if (!uploadedDocument) return;
                        setStartingAnalysis(true);
                        try {
                          await apiPost<
                            { analysis_id: string },
                            { prompt_pack: PromptPack; matter_id: string }
                          >(
                            `/v1/documents/${uploadedDocument.document_id}/analyze`,
                            {
                              prompt_pack: analysisPack,
                              matter_id: uploadedDocument.matter_id,
                            },
                          );
                          await analyses.refetch();
                          setSelectedId(null);
                          setBench("Deck");
                          setUploadMessage(
                            "Analysis started. Follow its status in your Deck; completed output opens when selected.",
                          );
                        } catch (error) {
                          setUploadMessage(
                            error instanceof Error
                              ? error.message
                              : "Could not start analysis.",
                          );
                        } finally {
                          setStartingAnalysis(false);
                        }
                      }}
                    >
                      {startingAnalysis ? (
                        <Loader2 className="size-3 animate-spin" />
                      ) : (
                        <ChevronRight className="size-3" />
                      )}
                      {startingAnalysis ? "Starting…" : "Analyze"}
                    </Button>
                  </div>
                </div>
              )}
              {matters.data?.matters.length ? (
                <select
                  aria-label="Matter for upload"
                  value={uploadMatter}
                  onChange={(event) => {
                    setUploadMatter(event.target.value);
                    setUploadedDocument(null);
                    setUploadMessage("");
                  }}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-xs"
                >
                  <option value="">Choose matter for upload</option>
                  {matters.data.matters.map((matter) => (
                    <option key={matter.id} value={matter.id}>
                      {matter.matter_ref}
                    </option>
                  ))}
                </select>
              ) : (
                <p className="text-[11px] text-muted-foreground">
                  Upload requires an assigned matter. PDF and DOCX files are
                  converted to searchable text during secure ingestion.
                </p>
              )}
            </div>
            {uploadMessage && (
              <p role="status" className="text-xs text-muted-foreground">
                {uploading ? "Uploading…" : uploadMessage}
              </p>
            )}
            <div className="panel space-y-3 p-4">
              <div className="flex items-center gap-2">
                <Printer className="size-4 text-steel" />
                <h2 className="text-sm font-semibold">Court copy</h2>
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="w-full"
                disabled={
                  !selectedId ||
                  bench !== "SmartBrief" ||
                  analyses.data?.find((item) => item.analysis_id === selectedId)
                    ?.status !== "COMPLETE"
                }
                onClick={() => window.print()}
              >
                <Printer className="mr-2 size-3.5" /> Print completed analysis
              </Button>
              <p className="text-[10px] text-muted-foreground">
                {membership.data?.firm_name ?? "Your firm"} · browser print
                layout. Select a completed analysis first.
              </p>
            </div>
            <div className="font-mono text-[10px] uppercase tracking-[0.28em] text-muted-foreground">
              Deck{" "}
              <span className="normal-case tracking-normal">
                · finished / in-progress / drafts
              </span>
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
                  <div
                    key={a.analysis_id}
                    className={`panel p-3 transition-all duration-200 ${selectedId === a.analysis_id ? "glow-gold border-gold/50" : "hover:border-steel/40"}`}
                  >
                    <button
                      onClick={() => setSelectedId(a.analysis_id)}
                      className="w-full text-left"
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
                    <div className="mt-2 flex items-center justify-between border-t border-border/60 pt-2">
                      <span className="text-[10px] text-muted-foreground">
                        {a.status === "COMPLETE"
                          ? "Finished"
                          : a.status === "RUNNING"
                            ? "In progress"
                            : "Draft / review"}
                      </span>
                      <details className="relative">
                        <summary
                          aria-label="Deck item actions"
                          className="list-none cursor-pointer rounded-md p-1 text-muted-foreground transition-all duration-200 hover:bg-surface hover:text-foreground"
                        >
                          <MoreHorizontal className="size-4" />
                        </summary>
                        <div className="absolute right-0 z-10 mt-1 w-52 rounded-lg border border-border bg-sidebar p-1 shadow-lg">
                          <p className="px-2 py-1 font-mono text-[9px] uppercase tracking-widest text-steel">
                            Send to Assistant inbox
                          </p>
                          {threads.data?.length ? (
                            threads.data.map((thread) => (
                              <button
                                type="button"
                                key={thread.thread_id}
                                onClick={() => {
                                  void sendAssistantMessage(
                                    thread.thread_id,
                                    `Please review the referenced SmartBrief output ${a.analysis_id}.`,
                                    {
                                      bench: "Deck",
                                      reference: {
                                        type: "analysis",
                                        id: a.analysis_id,
                                        label:
                                          PACK_LABEL[a.prompt_pack] ??
                                          "SmartBrief output",
                                      },
                                    },
                                  ).then(
                                    () =>
                                      setUploadMessage(
                                        `Sent reference to “${thread.title}”.`,
                                      ),
                                    () =>
                                      setUploadMessage(
                                        "Could not send output reference. Please retry.",
                                      ),
                                  );
                                }}
                                className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-xs transition-all duration-200 hover:bg-surface"
                              >
                                <Inbox className="size-3.5" />
                                {thread.title}
                              </button>
                            ))
                          ) : (
                            <p className="px-2 py-2 text-xs text-muted-foreground">
                              Create a thread in the Assistant first.
                            </p>
                          )}
                        </div>
                      </details>
                    </div>
                    {a.status === "COMPLETE" && (
                      <Link
                        to="/channels"
                        search={{ analysis: a.analysis_id } as never}
                        className="mt-2 inline-flex w-full items-center justify-center gap-2 rounded-lg border border-gold/30 px-3 py-2 text-xs font-medium text-gold transition-all duration-200 hover:border-gold/60 hover:bg-gold/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold"
                      >
                        <MessageSquare className="size-3.5" /> Discuss this
                        brief
                      </Link>
                    )}
                  </div>
                ))}
              </div>
            )}
          </aside>
          <section className="workbench-content panel min-w-0 p-5">
            <div className="print-only mb-6 border-b border-black pb-4 text-black">
              <p className="font-mono text-[10px] uppercase tracking-[0.2em]">
                {membership.data?.firm_name ?? "RedCase"}
              </p>
              <h1 className="mt-2 text-2xl font-semibold">
                {selectedId
                  ? `${PACK_LABEL[analyses.data?.find((item) => item.analysis_id === selectedId)?.prompt_pack ?? ""] ?? "Legal analysis"} · ${selectedId.slice(0, 8)}`
                  : "Legal analysis"}
              </h1>
              <p className="mt-1 text-sm">
                Printed {new Date().toLocaleDateString("en-GB")}
              </p>
            </div>
            <nav
              aria-label="Workbench benches"
              className="print-hide mb-5 flex gap-2 overflow-x-auto border-b border-border pb-3"
            >
              {(
                [
                  "SmartBrief",
                  "Red-Teamer",
                  "Deck",
                  "Researcher",
                  "Reviewer",
                ] as AssistantBench[]
              ).map((item) => (
                <button
                  type="button"
                  key={item}
                  onClick={() => {
                    if (item === "Red-Teamer") {
                      void navigate({ to: "/red-teamer" });
                      return;
                    }
                    setBench(item);
                    if (item !== "SmartBrief") setSelectedId(null);
                  }}
                  aria-current={bench === item ? "page" : undefined}
                  className={`shrink-0 rounded-lg px-3 py-2 text-xs font-medium transition-all duration-200 ${bench === item ? "bg-gold text-background" : "text-muted-foreground hover:bg-surface hover:text-foreground"}`}
                >
                  {item}
                </button>
              ))}
            </nav>
            {bench === "SmartBrief" && selectedId ? (
              <div className="min-h-[60vh]">
                <div className="mb-4 flex items-center gap-2 border-b border-border pb-3">
                  <LayoutDashboard className="size-4 text-gold" />
                  <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-steel">
                    SmartBrief output
                  </span>
                </div>
                <AnalysisWorkspace id={selectedId} />
              </div>
            ) : (
              <BenchView
                bench={bench}
                analyses={analyses.data ?? []}
                diary={diary.data ?? []}
                threads={threads.data ?? []}
                onSendToInbox={(analysis, threadId) => {
                  const thread = threads.data?.find(
                    (item) => item.thread_id === threadId,
                  );
                  if (!thread) return;
                  void sendAssistantMessage(
                    threadId,
                    `Please review the referenced SmartBrief output ${analysis.analysis_id}.`,
                    {
                      bench: "Deck",
                      reference: {
                        type: "analysis",
                        id: analysis.analysis_id,
                        label:
                          PACK_LABEL[analysis.prompt_pack] ??
                          "SmartBrief output",
                      },
                    },
                  ).then(
                    () =>
                      setUploadMessage(`Sent reference to “${thread.title}”.`),
                    () =>
                      setUploadMessage(
                        "Could not send output reference. Please retry.",
                      ),
                  );
                }}
                onSelect={(id) => {
                  setSelectedId(id);
                  setBench("SmartBrief");
                }}
                onAssistant={() =>
                  window.dispatchEvent(new Event("redcase:assistant-open"))
                }
                onReview={(id) => {
                  setSelectedId(id);
                  setBench("SmartBrief");
                }}
              />
            )}
          </section>
        </div>
      </div>
    </AppShell>
  );
}

function BenchView({
  bench,
  analyses,
  diary,
  threads,
  onSelect,
  onAssistant,
  onReview,
  onSendToInbox,
}: {
  bench: string;
  analyses: Analysis[];
  threads: Array<{ thread_id: string; title: string }>;
  diary: Array<{
    id: string;
    title: string;
    entry_type: string;
    starts_at: string;
    status: string;
  }>;
  onSelect: (id: string) => void;
  onAssistant: () => void;
  onReview: (id: string) => void;
  onSendToInbox: (analysis: Analysis, threadId: string) => void;
}) {
  const research = useVaultQuery<QueryResponse>();
  const [researchQuestion, setResearchQuestion] = useState("");
  const [researchNotice, setResearchNotice] = useState("");
  const [activeResearchQuestion, setActiveResearchQuestion] = useState("");
  if (bench === "Deck")
    return (
      <div className="space-y-3">
        <div>
          <h2 className="text-lg font-semibold">Deck</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Your analyses, grouped by workflow state. Open an item to inspect
            its sections and citations.
          </p>
        </div>
        {[
          {
            title: "Drafts",
            rows: analyses.filter((item) => item.status === "DRAFT"),
          },
          {
            title: "In progress",
            rows: analyses.filter((item) => item.status === "RUNNING"),
          },
          {
            title: "Ready for review",
            rows: analyses.filter((item) => item.status === "NEEDS_REVIEW"),
          },
          {
            title: "Completed",
            rows: analyses.filter((item) => item.status === "COMPLETE"),
          },
          {
            title: "Could not complete",
            rows: analyses.filter((item) => item.status === "FAILED"),
          },
        ].map((group) => (
          <section key={group.title} className="space-y-2">
            <h3 className="font-mono text-[10px] uppercase tracking-[0.2em] text-steel">
              {group.title}{" "}
              <span className="text-muted-foreground">
                ({group.rows.length})
              </span>
            </h3>
            {group.rows.length === 0 && group.title === "Drafts" ? (
              <p className="rounded-xl border border-dashed border-border p-4 text-xs text-muted-foreground">
                No saved drafts yet.
              </p>
            ) : null}
            {group.rows.map((analysis) => (
              <article
                key={analysis.analysis_id}
                className="flex items-center gap-3 rounded-xl border border-border p-3 transition-all duration-200 hover:border-gold/50"
              >
                <button
                  type="button"
                  onClick={() => onSelect(analysis.analysis_id)}
                  className="flex min-w-0 flex-1 items-center justify-between gap-3 rounded-lg p-1 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold"
                >
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium">
                      {PACK_LABEL[analysis.prompt_pack] ?? analysis.prompt_pack}
                    </span>
                    <span className="mt-1 block truncate font-mono text-[10px] text-muted-foreground">
                      {analysis.analysis_id.slice(0, 8)} ·{" "}
                      {new Date(analysis.created_at).toLocaleDateString(
                        "en-GB",
                      )}
                    </span>
                  </span>
                  <StatusBadge status={analysis.status} />
                </button>
                <details className="relative shrink-0">
                  <summary
                    aria-label={`Actions for ${PACK_LABEL[analysis.prompt_pack] ?? analysis.prompt_pack}`}
                    className="list-none cursor-pointer rounded-lg p-2 text-muted-foreground transition-all duration-200 hover:bg-surface hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold [&::-webkit-details-marker]:hidden"
                  >
                    <MoreHorizontal className="size-4" />
                  </summary>
                  <div className="absolute right-0 z-10 mt-1 w-56 rounded-xl border border-border bg-sidebar p-2 shadow-lg">
                    <p className="px-2 py-1 font-mono text-[9px] uppercase tracking-widest text-steel">
                      Send to Inbox
                    </p>
                    {threads.length ? (
                      threads.map((thread) => (
                        <button
                          key={thread.thread_id}
                          type="button"
                          onClick={() =>
                            onSendToInbox(analysis, thread.thread_id)
                          }
                          className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-xs transition-all duration-200 hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold"
                        >
                          <Inbox className="size-3.5 shrink-0" />
                          <span className="truncate">{thread.title}</span>
                        </button>
                      ))
                    ) : (
                      <p className="px-2 py-2 text-xs text-muted-foreground">
                        Create an Assistant thread before sending a reference.
                      </p>
                    )}
                  </div>
                </details>
              </article>
            ))}
          </section>
        ))}
      </div>
    );
  if (bench === "Red-Teamer")
    return (
      <div className="rounded-xl border border-border bg-background/60 p-6">
        <div className="flex items-center gap-3">
          <Swords className="size-5 text-gold" />
          <h2 className="text-lg font-semibold">Red-Teamer</h2>
        </div>
        <p className="mt-2 max-w-xl text-sm text-muted-foreground">
          Review strategy and challenge assumptions. Open a battle card from the
          Red-Teamer bench, then ask the Personal Assistant to probe its
          reasoning and counter-arguments.
        </p>
        <Link
          to="/red-teamer"
          className="mt-4 inline-flex rounded-lg bg-gold px-4 py-2 text-sm font-semibold text-background transition-all duration-200 hover:bg-gold/90"
        >
          Open Red-Teamer <ChevronRight className="ml-2 size-4" />
        </Link>
        <button
          type="button"
          onClick={onAssistant}
          className="ml-3 mt-4 inline-flex rounded-lg border border-border px-4 py-2 text-sm transition-all duration-200 hover:border-gold/50"
        >
          Question current output
        </button>
      </div>
    );
  if (bench === "Researcher")
    return (
      <div className="space-y-4 rounded-xl border border-border bg-background/60 p-5 sm:p-6">
        <div className="flex items-center gap-3">
          <Scale className="size-5 text-gold" />
          <h2 className="text-lg font-semibold">Researcher</h2>
        </div>
        <p className="text-sm text-muted-foreground">
          Research is Vault Search in context: ask a legal question and review
          the returned answer and verified, page-pinned citations. The
          underlying query endpoint determines accessible sources.
        </p>
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            const question = researchQuestion.trim();
            if (question.length < 10 || research.isPending) return;
            setResearchNotice("");
            setActiveResearchQuestion(question);
            research.mutate(
              { question },
              {
                onError: () =>
                  setResearchNotice(
                    "Research could not be completed. Check the connection and try again.",
                  ),
              },
            );
          }}
        >
          <label
            htmlFor="workbench-research"
            className="block font-mono text-[10px] uppercase tracking-widest text-muted-foreground"
          >
            Legal research question
          </label>
          <textarea
            id="workbench-research"
            value={researchQuestion}
            onChange={(event) => setResearchQuestion(event.target.value)}
            minLength={10}
            maxLength={2000}
            rows={3}
            placeholder="e.g. What is the effect of a defective originating process on jurisdiction?"
            className="w-full resize-y rounded-lg border border-border bg-background px-3 py-2.5 text-sm outline-none transition-all duration-200 focus-visible:ring-2 focus-visible:ring-gold"
          />
          <div className="flex flex-wrap items-center gap-3">
            <Button
              type="submit"
              disabled={
                researchQuestion.trim().length < 10 || research.isPending
              }
            >
              <Scale className="mr-2 size-4" />
              {research.isPending ? "Searching…" : "Search authorities"}
            </Button>
            <span className="text-xs text-muted-foreground">
              Minimum 10 characters · verified citations only
            </span>
          </div>
        </form>
        {researchNotice && (
          <p role="alert" className="text-sm text-destructive">
            {researchNotice}
          </p>
        )}
        {research.isError && (
          <p
            role="alert"
            className="rounded-lg border border-destructive/40 p-3 text-sm text-destructive"
          >
            {research.error instanceof Error
              ? research.error.message
              : "Research failed."}
          </p>
        )}
        {research.data && (
          <ResearchResults
            question={activeResearchQuestion}
            answer={research.data.answer}
            refusal={research.data.refusal}
            citations={research.data.citations}
            onAssistant={onAssistant}
          />
        )}
      </div>
    );
  if (bench === "Reviewer")
    return (
      <div className="space-y-3">
        <div>
          <h2 className="text-lg font-semibold">Reviewer</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Review analyses flagged for human attention alongside upcoming court
            diary items.
          </p>
        </div>
        <section className="space-y-2">
          <h3 className="font-mono text-[10px] uppercase tracking-widest text-steel">
            Analysis review queue
          </h3>
          {analyses.filter((analysis) => analysis.status === "NEEDS_REVIEW")
            .length ? (
            analyses
              .filter((analysis) => analysis.status === "NEEDS_REVIEW")
              .map((analysis) => (
                <article
                  key={analysis.analysis_id}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-warning/30 p-4"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-medium">
                      {PACK_LABEL[analysis.prompt_pack] ?? analysis.prompt_pack}
                    </p>
                    <p className="mt-1 font-mono text-[10px] text-muted-foreground">
                      {analysis.analysis_id.slice(0, 8)} ·{" "}
                      {new Date(analysis.created_at).toLocaleDateString(
                        "en-GB",
                      )}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <StatusBadge status={analysis.status} />
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => onReview(analysis.analysis_id)}
                    >
                      Review output
                    </Button>
                  </div>
                </article>
              ))
          ) : (
            <div className="rounded-xl border border-dashed border-border p-5 text-sm text-muted-foreground">
              No analyses are currently flagged for manual review.
            </div>
          )}
        </section>
        <section className="space-y-2">
          <h3 className="font-mono text-[10px] uppercase tracking-widest text-steel">
            Hearings &amp; court diary
          </h3>
          {diary.length ? (
            diary.map((entry) => (
              <article
                key={entry.id}
                className="rounded-xl border border-border p-4"
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm font-medium">{entry.title}</span>
                  <span className="text-[10px] uppercase text-gold">
                    {entry.entry_type}
                  </span>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  {new Date(entry.starts_at).toLocaleString()} · {entry.status}
                </p>
              </article>
            ))
          ) : (
            <div className="rounded-xl border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
              No court diary entries available.
            </div>
          )}
        </section>
      </div>
    );
  return (
    <div className="panel flex min-h-[60vh] flex-col items-center justify-center gap-3 px-6 py-20 text-center">
      <LayoutDashboard className="size-8 text-steel" />
      <h2 className="text-lg font-semibold">SmartBrief</h2>
      <p className="max-w-sm text-sm text-muted-foreground">
        Select a Deck output to open the Overview, Arguments, Similar Cases and
        Law sections.
      </p>
    </div>
  );
}

function ResearchResults({
  question,
  answer,
  refusal,
  citations,
  onAssistant,
}: {
  question: string;
  answer: string;
  refusal: boolean;
  citations: Citation[];
  onAssistant: () => void;
}) {
  return (
    <section
      aria-live="polite"
      className="space-y-3 border-t border-border pt-4"
    >
      <div
        className={`rounded-xl border p-4 ${refusal ? "border-warning/40 bg-warning/5" : "border-border bg-background"}`}
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold">Research answer</h3>
          <span
            className={`font-mono text-[10px] uppercase tracking-widest ${refusal ? "text-warning" : "text-success"}`}
          >
            {refusal ? "Verification refused" : "Grounded response"}
          </span>
        </div>
        <p className="mt-3 whitespace-pre-wrap text-sm leading-6">{answer}</p>
        {refusal && (
          <p className="mt-3 text-xs text-warning">
            Do not rely on this as a verified answer. Refine the question or
            consult the source material.
          </p>
        )}
      </div>
      <div>
        <h3 className="mb-2 font-mono text-[10px] uppercase tracking-widest text-steel">
          Sources ({citations.length})
        </h3>
        {citations.length ? (
          <div className="grid gap-2 sm:grid-cols-2">
            {citations.map((citation) => (
              <article
                key={`${citation.document_id}:${citation.page_start}:${citation.citation}`}
                className="rounded-xl border border-border p-3"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="rounded border border-gold/40 bg-gold/10 px-1.5 py-0.5 font-mono text-[10px] text-gold">
                    {citation.court_level} · {citation.year}
                  </span>
                  <span
                    className={`font-mono text-[9px] uppercase ${citation.verified ? "text-success" : "text-warning"}`}
                  >
                    {citation.verified ? "Verified" : "Unverified"}
                  </span>
                </div>
                <h4 className="mt-2 text-sm font-medium">
                  {citation.case_title}
                </h4>
                <p className="mt-1 font-mono text-xs text-gold">
                  {citation.citation}
                </p>
                <p className="mt-1 font-mono text-[10px] text-muted-foreground">
                  pp. {citation.page_start}–{citation.page_end}
                  {citation.paragraph_refs.length
                    ? ` · ¶ ${citation.paragraph_refs.join(", ¶ ")}`
                    : ""}
                </p>
                {citation.source_pdf_url && (
                  <a
                    className="mt-2 inline-flex text-xs underline underline-offset-2 transition-colors hover:text-gold"
                    href={citation.source_pdf_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Open source PDF
                  </a>
                )}
              </article>
            ))}
          </div>
        ) : (
          <p className="rounded-lg border border-dashed border-border p-4 text-sm text-muted-foreground">
            No citations were returned. Treat the answer cautiously and verify
            against primary sources.
          </p>
        )}
      </div>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => {
          window.dispatchEvent(
            new CustomEvent("redcase:assistant-message", {
              detail: {
                message: `Research question: ${question}\n\nVault Search response: ${answer}\n\nSources: ${
                  citations
                    .map(
                      (citation) =>
                        `${citation.case_title} (${citation.citation}), pp. ${citation.page_start}–${citation.page_end}${citation.verified ? " [verified]" : " [unverified]"}`,
                    )
                    .join("; ") || "No citations returned."
                }`,
                context: { bench: "Researcher" },
              },
            }),
          );
          onAssistant();
        }}
      >
        Discuss research with Assistant
      </Button>
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
      <nav
        aria-label="Analysis sections"
        className="flex gap-2 overflow-x-auto border-b border-border"
      >
        {(
          [
            { id: "overview", label: "Overview" },
            { id: "arguments", label: "Arguments" },
            { id: "similar", label: "Similar Cases" },
            { id: "law", label: "Law" },
          ] as const
        ).map((item) => (
          <button
            key={item.id}
            type="button"
            aria-current={tab === item.id ? "page" : undefined}
            onClick={() => setTab(item.id)}
            className={`shrink-0 border-b-2 px-3 py-2 text-xs font-medium transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold ${tab === item.id ? "border-gold text-gold" : "border-transparent text-muted-foreground hover:text-foreground"}`}
          >
            {item.label}
          </button>
        ))}
      </nav>
      <div
        role="tabpanel"
        aria-label={
          tab === "similar"
            ? "Similar Cases"
            : `${tab.slice(0, 1).toUpperCase()}${tab.slice(1)}`
        }
      >
        <AnalysisSectionCard
          section={tab === "similar" ? "similar_cases" : tab}
          data={sections[tab === "similar" ? "similar_cases" : tab]}
          className="border-border bg-background"
        />
      </div>
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
          <div className="flex items-center gap-3">
            {a.status === "COMPLETE" && <ReanalyzeMenu analysis={a} />}
            <StatusBadge status={a.status} />
          </div>
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
    </div>
  );
}

function OverviewTab({ output, sections }: { output: any; sections: any }) {
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

/** The non‑current prompt packs, for "Re-analyze with…" (analysis chaining §1.7). */
const OTHER_PACKS = (current: string): PromptPack[] =>
  (Object.keys(PACK_LABEL) as PromptPack[]).filter((p) => p !== current);

/** "Re-analyze with…" — chain a child analysis on the SAME document with a
 *  different pack (full provenance via parent_analysis_id). Only meaningful when the
 *  source analysis is COMPLETE and at least one other pack exists. */
function ReanalyzeMenu({ analysis }: { analysis: Analysis }) {
  const chain = useChainAnalysis();
  const [pack, setPack] = useState<PromptPack | "">("");
  const options = OTHER_PACKS(analysis.prompt_pack);
  if (options.length === 0) return null;

  return (
    <div className="flex items-center gap-2">
      <select
        value={pack}
        onChange={(e) => setPack(e.target.value as PromptPack)}
        aria-label="Re-analyze with a different tool"
        className="h-8 rounded-md border border-input bg-background px-2 text-xs focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
      >
        <option value="">Re-analyze with…</option>
        {options.map((p) => (
          <option key={p} value={p}>
            {PACK_LABEL[p] ?? p}
          </option>
        ))}
      </select>
      <Button
        type="button"
        size="sm"
        variant="outline"
        disabled={!pack || chain.isPending}
        onClick={() => {
          if (!pack) return;
          chain.mutate(
            { analysis_id: analysis.analysis_id, prompt_pack: pack },
            {
              onSuccess: () => setPack(""),
              onError: () => setPack(""),
            },
          );
        }}
        className="gap-1.5"
      >
        {chain.isPending ? (
          <Loader2 className="size-3 animate-spin" />
        ) : (
          <GitBranch className="size-3" />
        )}
        Chain
      </Button>
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
