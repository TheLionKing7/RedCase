import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useRef, useState, type ReactNode } from "react";
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
  Send,
  FileWarning,
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
import {
  sendAssistantMessage,
  useChannels,
  useSendMessage,
  useThreads,
} from "@/lib/api/collaboration";
import { useVaultQuery } from "@/lib/api/query";
import type { Citation, QueryResponse } from "@/lib/api/types";
import { useBattleCard } from "@/lib/api/redteam";
import type { BattleCard } from "@/lib/api/redteam";
import { usePersona } from "@/lib/api/persona";
import { COURT_LEVELS } from "@/lib/court-filters";

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
type RedteamTab = "flaws" | "opposing" | "counters" | "authorities" | "probe";
type ResearchTab = "report" | "authorities" | "passages";
type ReviewerTab =
  | "clauses"
  | "missing"
  | "obligations"
  | "defined_terms"
  | "negotiation";
type ResearchMode = "legal" | "general";

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
  const analyses = useAnalyses();
  const identity = useIdentity();
  const membership = useMembership();
  const threads = useThreads();
  const channels = useChannels();
  const matters = useQuery({
    queryKey: ["matters", "my"],
    queryFn: () =>
      apiGet<{ matters: Array<{ id: string; matter_ref: string }> }>(
        "/v1/matters/my",
      ),
  });
  const diary = useCourtDiaryEntries();
  const persona = usePersona();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [bench, setBench] = useState<AssistantBench>("SmartBrief");
  const [smartBriefTab, setSmartBriefTab] = useState<WorkbenchTab>("overview");
  const [redteamTab, setRedteamTab] = useState<RedteamTab>("flaws");
  const [researchTab, setResearchTab] = useState<ResearchTab>("report");
  const [reviewerTab, setReviewerTab] = useState<ReviewerTab>("clauses");
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
  const [deckStatus, setDeckStatus] = useState("ALL");
  const [deckTab, setDeckTab] = useState<WorkbenchTab>("overview");
  const [teamChannelId, setTeamChannelId] = useState("");
  const [deckNotice, setDeckNotice] = useState("");
  const [opposingBrief, setOpposingBrief] = useState<File | null>(null);
  const [redteamNotice, setRedteamNotice] = useState("");
  const redteamFileInput = useRef<HTMLInputElement>(null);
  const battleCard = useBattleCard();
  const sendToTeam = useSendMessage(teamChannelId);
  const selectedOutput = useAnalysis(selectedId);
  const [courtCopyId, setCourtCopyId] = useState<string | null>(null);
  const [researchMode, setResearchMode] = useState<ResearchMode>("legal");
  const [researchQuestion, setResearchQuestion] = useState("");
  const [researchNotice, setResearchNotice] = useState("");
  const [activeResearchQuestion, setActiveResearchQuestion] = useState("");
  const [researchCourt, setResearchCourt] = useState("");
  const [researchYearFrom, setResearchYearFrom] = useState<number | "">("");
  const [researchYearTo, setResearchYearTo] = useState<number | "">("");
  const [researchRatio, setResearchRatio] = useState("");
  const research = useVaultQuery<QueryResponse>();
  const [reviewerLink, setReviewerLink] = useState("");
  const [reviewerUploadMessage, setReviewerUploadMessage] = useState("");
  const [reviewerUploading, setReviewerUploading] = useState(false);
  const [reviewerDocument, setReviewerDocument] = useState<{
    document_id: string;
    matter_id: string;
    title: string;
  } | null>(null);
  const [scrutinizing, setScrutinizing] = useState(false);
  const reviewerFileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const requestedBench = sessionStorage.getItem("redcase:workbench-bench");
    if (
      requestedBench &&
      ["SmartBrief", "Red-Teamer", "Deck", "Researcher", "Reviewer"].includes(
        requestedBench,
      )
    ) {
      setBench(requestedBench as AssistantBench);
      sessionStorage.removeItem("redcase:workbench-bench");
    }
    const selectBench = (event: Event) => {
      const nextBench = (event as CustomEvent<string>).detail as AssistantBench;
      if (
        ["SmartBrief", "Red-Teamer", "Deck", "Researcher", "Reviewer"].includes(
          nextBench,
        )
      ) {
        setBench(nextBench);
      }
    };
    window.addEventListener("redcase:workbench-bench", selectBench);
    return () =>
      window.removeEventListener("redcase:workbench-bench", selectBench);
  }, []);

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

  useEffect(() => {
    if (
      !courtCopyId ||
      courtCopyId !== selectedId ||
      bench !== "Deck" ||
      selectedOutput.data?.status !== "COMPLETE"
    )
      return;
    const timeout = window.setTimeout(() => {
      window.print();
      setCourtCopyId(null);
    }, 250);
    return () => window.clearTimeout(timeout);
  }, [bench, courtCopyId, selectedId, selectedOutput.data?.status]);

  function openCourtCopy(analysis: Analysis) {
    if (analysis.status !== "COMPLETE") return;
    setSelectedId(analysis.analysis_id);
    setBench("Deck");
    setCourtCopyId(analysis.analysis_id);
  }

  function askAssistantAboutSelectedAnalysis() {
    if (selectedAnalysis?.status !== "COMPLETE") return;
    window.dispatchEvent(
      new CustomEvent("redcase:assistant-message", {
        detail: {
          message: `Review my selected SmartBrief analysis ${selectedAnalysis.analysis_id} in the context of this opposing-brief review. Identify weaknesses, counterarguments, and authorities that need verification.`,
        },
      }),
    );
  }

  function probeBattleCardWithAssistant() {
    if (!battleCard.data) return;
    window.dispatchEvent(
      new CustomEvent("redcase:assistant-message", {
        detail: {
          message:
            "Probe this Red-Teamer battle card: challenge its procedural flaws and opposing arguments, test the counters, and verify its authorities.",
          context: {
            bench: "Red-Teamer",
            output: {
              type: "battle_card",
              label: `Battle card · ${battleCard.data.source_document_id.slice(0, 8)}`,
              content: JSON.stringify(battleCard.data),
            },
          },
        },
      }),
    );
  }

  async function shareSelectedWithTeam() {
    if (!selectedAnalysis || selectedAnalysis.status !== "COMPLETE") return;
    if (!teamChannelId) {
      setDeckNotice("Choose a team channel before sharing this output.");
      return;
    }
    try {
      await sendToTeam.mutateAsync({
        body: `Completed ${PACK_LABEL[selectedAnalysis.prompt_pack] ?? selectedAnalysis.prompt_pack} output · ${selectedAnalysis.analysis_id}`,
        analysis_id: selectedAnalysis.analysis_id,
        document_id: selectedAnalysis.document_id,
      });
      setDeckNotice("Completed output reference sent to the selected channel.");
    } catch (error) {
      setDeckNotice(
        error instanceof Error
          ? error.message
          : "Could not send output to the team.",
      );
    }
  }

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

  const selectedAnalysis = analyses.data?.find(
    (item) => item.analysis_id === selectedId,
  );
  const assistantReference =
    selectedAnalysis?.status === "COMPLETE"
      ? {
          type: "analysis" as const,
          id: selectedAnalysis.analysis_id,
          label:
            PACK_LABEL[selectedAnalysis.prompt_pack] ?? "SmartBrief output",
        }
      : undefined;
  const partnerEyebrow = membership.isPending
    ? "Loading partner…"
    : membership.data?.full_name
      ? `${membership.data.full_name}${membership.data.role ? ` · ${membership.data.role}` : ""}`
      : identity.name && identity.name.toLowerCase() !== "counsel"
        ? `${identity.name}${identity.role ? ` · ${identity.role}` : ""}`
        : "Partner";
  const reviewQueue = (analyses.data ?? []).filter(
    (analysis) => analysis.prompt_pack === "CONTRACT_REVIEW",
  );
  const deckAnalyses =
    deckStatus === "ALL"
      ? (analyses.data ?? [])
      : (analyses.data ?? []).filter(
          (analysis) => analysis.status === deckStatus,
        );

  return (
    <AppShell
      eyebrow={partnerEyebrow}
      title="Workbench"
      assistantContext={{
        bench,
        ...(assistantReference ? { reference: assistantReference } : {}),
      }}
    >
      <CoachMarks surface="workbench" steps={coachSteps} />
      <div className="workbench-print mx-auto max-w-7xl space-y-6 pb-28">
        <div className="print-hide sticky -mt-8 z-20 -mx-5 flex flex-wrap items-center gap-2 border-b border-border bg-background/95 px-5 py-3 backdrop-blur-xl lg:-mx-8 lg:px-8" style={{ top: "var(--workbench-header-height, 5.5rem)" }}>
          <span className="font-mono text-xs font-medium uppercase tracking-[0.14em] text-foreground">
            {bench}
          </span>
          <span aria-hidden="true" className="px-1 font-mono text-sm text-steel">
            |
          </span>
          {bench === "SmartBrief" ? (
            <ToolMenu
              label="SmartBrief sections"
              items={[
                { id: "overview", label: "Overview" },
                { id: "arguments", label: "Arguments" },
                { id: "similar", label: "Similar Cases" },
                { id: "law", label: "Law" },
              ]}
              active={smartBriefTab}
              onSelect={(id) => setSmartBriefTab(id as WorkbenchTab)}
            />
          ) : bench === "Deck" ? (
            <>
              <ToolMenu
                label="Deck output sections"
                items={[
                  { id: "overview", label: "Overview" },
                  { id: "arguments", label: "Arguments" },
                  { id: "similar", label: "Similar Cases" },
                  { id: "law", label: "Law" },
                ]}
                active={deckTab}
                onSelect={(id) => setDeckTab(id as WorkbenchTab)}
              />
              <label className="sr-only" htmlFor="deck-status-filter">
                Filter deck by status
              </label>
              <select
                id="deck-status-filter"
                value={deckStatus}
                onChange={(event) => setDeckStatus(event.target.value)}
                className="rounded-lg border border-border bg-background px-3 py-2 text-xs outline-none transition-all duration-200 focus-visible:ring-2 focus-visible:ring-gold"
              >
                <option value="ALL">All statuses</option>
                <option value="COMPLETE">Finished</option>
                <option value="RUNNING">In progress</option>
                <option value="DRAFT">Drafts</option>
                <option value="NEEDS_REVIEW">Needs review</option>
                <option value="FAILED">Failed</option>
              </select>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={
                  !selectedAnalysis ||
                  selectedAnalysis.status !== "COMPLETE" ||
                  selectedOutput.isFetching
                }
                onClick={() =>
                  selectedAnalysis && openCourtCopy(selectedAnalysis)
                }
              >
                <Printer className="mr-1.5 size-3.5" /> Court Copy
              </Button>
              <label className="sr-only" htmlFor="deck-team-channel">
                Team channel
              </label>
              <select
                id="deck-team-channel"
                value={teamChannelId}
                onChange={(event) => setTeamChannelId(event.target.value)}
                className="min-w-36 rounded-lg border border-border bg-background px-3 py-2 text-xs outline-none transition-all duration-200 focus-visible:ring-2 focus-visible:ring-gold"
              >
                <option value="">Choose team channel</option>
                {(channels.data ?? []).map((channel) => (
                  <option key={channel.id} value={channel.id}>
                    {channel.name}
                  </option>
                ))}
              </select>
              <Button
                type="button"
                size="sm"
                disabled={
                  !selectedAnalysis ||
                  selectedAnalysis.status !== "COMPLETE" ||
                  !teamChannelId ||
                  sendToTeam.isPending
                }
                onClick={() => void shareSelectedWithTeam()}
              >
                {sendToTeam.isPending ? (
                  <Loader2 className="mr-1.5 size-3.5 animate-spin" />
                ) : (
                  <Send className="mr-1.5 size-3.5" />
                )}
                Send to team
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={analyses.isFetching}
                onClick={() => void analyses.refetch()}
              >
                {analyses.isFetching ? (
                  <Loader2 className="mr-1.5 size-3.5 animate-spin" />
                ) : (
                  <GitBranch className="mr-1.5 size-3.5" />
                )}
                Refresh
              </Button>
            </>
          ) : bench === "Red-Teamer" ? (
            <ToolMenu
              label="Red-Teamer sections"
              items={[
                { id: "flaws", label: "Flaws" },
                { id: "opposing", label: "Opposing arguments" },
                { id: "counters", label: "Counters" },
                { id: "authorities", label: "Authorities" },
                { id: "probe", label: "Probe with assistant" },
              ]}
              active={redteamTab}
              onSelect={(id) => {
                const next = id as RedteamTab;
                setRedteamTab(next);
                if (next === "probe") probeBattleCardWithAssistant();
              }}
            />
          ) : bench === "Researcher" ? (
            <ToolMenu
              label="Researcher report"
              items={[
                { id: "report", label: "Report" },
                { id: "authorities", label: "Authorities" },
                { id: "passages", label: "Passages" },
              ]}
              active={researchTab}
              onSelect={(id) => setResearchTab(id as ResearchTab)}
              action={{ label: "Export", onClick: () => window.print() }}
            />
          ) : bench === "Reviewer" ? (
            <ToolMenu
              label="Reviewer sections"
              items={[
                { id: "clauses", label: "Clauses & risks" },
                { id: "missing", label: "Missing" },
                { id: "obligations", label: "Obligations" },
                { id: "defined_terms", label: "Defined terms" },
                { id: "negotiation", label: "Negotiation" },
              ]}
              active={reviewerTab}
              onSelect={(id) => setReviewerTab(id as ReviewerTab)}
            />
          ) : (
            <span className="text-xs text-muted-foreground">
              Adversarial brief review
            </span>
          )}
        </div>
        {bench === "Deck" && deckNotice && (
          <p role="status" className="print-hide text-sm text-muted-foreground">
            {deckNotice}
          </p>
        )}
        <div className="grid gap-6 lg:grid-cols-[300px_minmax(0,1fr)]">
          {bench !== "SmartBrief" && bench !== "Deck" && (
            <aside className="workbench-tools space-y-3 print-hide">
              {bench === "Red-Teamer" ? (
                <div className="panel space-y-3 p-4">
                  <div>
                    <h2 className="text-sm font-semibold">Opposing brief</h2>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Upload a PDF or DOCX to generate a battle card of flaws,
                      arguments, counters, and authorities.
                    </p>
                  </div>
                  <input
                    ref={redteamFileInput}
                    type="file"
                    accept="application/pdf,.pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,.docx"
                    className="sr-only"
                    onChange={(event) => {
                      const file = event.currentTarget.files?.[0] ?? null;
                      if (file && !/\.(pdf|docx)$/i.test(file.name)) {
                        setOpposingBrief(null);
                        setRedteamNotice(
                          "Choose a PDF or DOCX opposing brief.",
                        );
                        event.currentTarget.value = "";
                        return;
                      }
                      if (file && file.size > 20 * 1024 * 1024) {
                        setOpposingBrief(null);
                        setRedteamNotice(
                          "The opposing brief must be 20 MB or smaller.",
                        );
                        event.currentTarget.value = "";
                        return;
                      }
                      setOpposingBrief(file);
                      setRedteamNotice(
                        file ? `${file.name} ready for review.` : "",
                      );
                      battleCard.reset();
                      event.currentTarget.value = "";
                    }}
                  />
                  <Button
                    type="button"
                    variant="outline"
                    className="w-full"
                    onClick={() => redteamFileInput.current?.click()}
                  >
                    <Upload className="mr-2 size-4" />{" "}
                    {opposingBrief?.name ?? "Choose opposing brief"}
                  </Button>
                  <Button
                    type="button"
                    className="w-full"
                    disabled={!opposingBrief || battleCard.isPending}
                    onClick={async () => {
                      if (!opposingBrief) return;
                      setRedteamNotice("");
                      try {
                        await battleCard.mutateAsync({
                          document_name: opposingBrief.name,
                          content_base64: await readFileAsBase64(opposingBrief),
                        });
                        setRedteamNotice(
                          "Battle card generated. Review every finding before relying on it.",
                        );
                      } catch (error) {
                        setRedteamNotice(
                          error instanceof Error
                            ? error.message
                            : "Could not analyze the opposing brief.",
                        );
                      }
                    }}
                  >
                    {battleCard.isPending ? (
                      <Loader2 className="mr-2 size-4 animate-spin" />
                    ) : (
                      <Swords className="mr-2 size-4" />
                    )}
                    {battleCard.isPending
                      ? "Analyzing brief…"
                      : "Generate battle card"}
                  </Button>
                  {redteamNotice && (
                    <p role="status" className="text-xs text-muted-foreground">
                      {redteamNotice}
                    </p>
                  )}
                  {battleCard.isError && (
                    <p role="alert" className="text-xs text-destructive">
                      {battleCard.error.message}
                    </p>
                  )}
                </div>
              ) : (
                <div className="panel space-y-2 p-4">
                  <h2 className="text-sm font-semibold">{bench} tools</h2>
                  <p className="text-xs text-muted-foreground">
                    Use the bench tools above to search or review existing
                    output.
                  </p>
                </div>
              )}
            </aside>
          )}
          {bench === "SmartBrief" && (
            <aside className="workbench-tools space-y-3 print-hide">
              {bench === "SmartBrief" && (
                <div id="workbench-source" className="panel space-y-3 p-4">
                  <div>
                    <h2 className="text-sm font-semibold">
                      Start with a source
                    </h2>
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
                          <option value="ADVERSAL_BRIEF">
                            Adversarial Brief
                          </option>
                          <option value="SUMMONS_RESPONSE">
                            Summons Response
                          </option>
                          <option value="CONTRACT_REVIEW">
                            Contract Review
                          </option>
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
              )}
              {uploadMessage && (
                <p role="status" className="text-xs text-muted-foreground">
                  {uploading ? "Uploading…" : uploadMessage}
                </p>
              )}
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
          )}
          <section className="workbench-content panel min-w-0 p-5">
            <div className="print-only mb-6 border-b-2 border-black pb-4 text-black">
              <p className="font-mono text-[10px] uppercase tracking-[0.2em]">
                {membership.data?.firm_name ?? "RedCase"} · Legal Practitioners
              </p>
              <h1 className="mt-2 text-2xl font-semibold">
                {selectedId
                  ? `${PACK_LABEL[analyses.data?.find((item) => item.analysis_id === selectedId)?.prompt_pack ?? ""] ?? "Legal analysis"} · ${selectedId.slice(0, 8)}`
                  : "Legal analysis"}
              </h1>
              <p className="mt-1 text-sm">
                Court Copy · Printed {new Date().toLocaleDateString("en-GB")}
              </p>
              <p className="mt-3 inline-block border border-black px-2 py-1 font-mono text-[10px] font-bold uppercase tracking-widest">
                Counsel review copy · Not filed
              </p>
            </div>
            {bench === "SmartBrief" && selectedId ? (
              <div className="min-h-[60vh]">
                <div className="mb-4 flex items-center gap-2 border-b border-border pb-3">
                  <LayoutDashboard className="size-4 text-gold" />
                  <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-steel">
                    SmartBrief output
                  </span>
                </div>
                <AnalysisWorkspace
                  id={selectedId}
                  tab={smartBriefTab}
                  reviewerMode
                />
              </div>
            ) : bench === "Red-Teamer" && battleCard.data ? (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="text-lg font-semibold">
                      Opposing brief review
                    </h2>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Battle card findings are advisory; verify every authority
                      and proposition.
                    </p>
                  </div>
                  {selectedAnalysis?.status === "COMPLETE" && (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={askAssistantAboutSelectedAnalysis}
                    >
                      <MessageSquare className="mr-2 size-4" /> Ask Assistant
                      about selected SmartBrief
                    </Button>
                  )}
                </div>
                <RedteamSummary
                  card={battleCard.data}
                  tab={redteamTab}
                  onProbe={probeBattleCardWithAssistant}
                />
              </div>
            ) : bench === "Red-Teamer" ? (
              <div className="panel flex min-h-[50vh] flex-col items-center justify-center gap-3 px-6 py-16 text-center">
                <FileWarning className="size-9 text-steel" />
                <h2 className="text-lg font-semibold">
                  Challenge the opposing case
                </h2>
                <p className="max-w-md text-sm text-muted-foreground">
                  Choose an opposing brief from the Red-Teamer panel. Its battle
                  card will appear here alongside your selected SmartBrief
                  analysis context.
                </p>
                {selectedAnalysis?.status === "COMPLETE" && (
                  <p className="rounded-lg border border-gold/30 bg-gold/5 px-3 py-2 text-xs text-gold">
                    Selected SmartBrief:{" "}
                    {PACK_LABEL[selectedAnalysis.prompt_pack] ??
                      selectedAnalysis.prompt_pack}{" "}
                    · {selectedAnalysis.analysis_id.slice(0, 8)}
                  </p>
                )}
                <Button
                  type="button"
                  variant="outline"
                  onClick={askAssistantAboutSelectedAnalysis}
                  disabled={selectedAnalysis?.status !== "COMPLETE"}
                >
                  <MessageSquare className="mr-2 size-4" /> Ask Assistant about
                  this analysis
                </Button>
              </div>
            ) : (
              <BenchView
                bench={bench}
                analyses={analyses.data ?? []}
                deckStatus={deckStatus}
                selectedId={selectedId}
                deckTab={deckTab}
                researchTab={researchTab}
                reviewerTab={reviewerTab}
                reviewerSpecialty={persona.data?.reviewer_specialty ?? null}
                onResearchTabChange={setResearchTab}
                onReviewerTabChange={setReviewerTab}
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
                }}
                onAssistant={() =>
                  window.dispatchEvent(new Event("redcase:assistant-open"))
                }
                onReview={(id) => {
                  setSelectedId(id);
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
  deckStatus,
  selectedId,
  deckTab,
  researchTab,
  reviewerTab,
  reviewerSpecialty,
  onResearchTabChange,
  onReviewerTabChange,
  diary,
  threads,
  onSelect,
  onAssistant,
  onReview,
  onSendToInbox,
}: {
  bench: string;
  analyses: Analysis[];
  deckStatus: string;
  selectedId: string | null;
  deckTab: WorkbenchTab;
  researchTab: ResearchTab;
  reviewerTab: ReviewerTab;
  reviewerSpecialty: string | null;
  onResearchTabChange: (tab: ResearchTab) => void;
  onReviewerTabChange: (tab: ReviewerTab) => void;
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
  const [researchCourt, setResearchCourt] = useState("");
  const [researchYearFrom, setResearchYearFrom] = useState<number | "">("");
  const [researchYearTo, setResearchYearTo] = useState<number | "">("");
  const [researchRatio, setResearchRatio] = useState("");
  const [selectedReviewId, setSelectedReviewId] = useState<string | null>(null);
  const deckAnalyses =
    deckStatus === "ALL"
      ? analyses
      : analyses.filter((analysis) => analysis.status === deckStatus);
  const selectedDeckAnalysis =
    analyses.find((analysis) => analysis.analysis_id === selectedId) ?? null;
  const reviewQueue = analyses.filter(
    (analysis) => analysis.prompt_pack === "CONTRACT_REVIEW",
  );
  const activeReviewId =
    selectedReviewId &&
    reviewQueue.some((analysis) => analysis.analysis_id === selectedReviewId)
      ? selectedReviewId
      : (reviewQueue[0]?.analysis_id ?? null);
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
            rows: deckAnalyses.filter((item) => item.status === "DRAFT"),
          },
          {
            title: "In progress",
            rows: deckAnalyses.filter((item) => item.status === "RUNNING"),
          },
          {
            title: "Ready for review",
            rows: deckAnalyses.filter((item) => item.status === "NEEDS_REVIEW"),
          },
          {
            title: "Completed",
            rows: deckAnalyses.filter((item) => item.status === "COMPLETE"),
          },
          {
            title: "Could not complete",
            rows: deckAnalyses.filter((item) => item.status === "FAILED"),
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
                      {analysis.analysis_id.slice(0, 8)} ┬╖{" "}
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
        <section aria-label="Selected deck output" className="panel space-y-4 p-4 sm:p-5">
          {selectedDeckAnalysis ? (
            <>
              <h3 className="text-sm font-semibold">
                {PACK_LABEL[selectedDeckAnalysis.prompt_pack] ??
                  selectedDeckAnalysis.prompt_pack}
              </h3>
              <AnalysisWorkspace
                id={selectedDeckAnalysis.analysis_id}
                tab={deckTab}
                reviewerMode
              />
            </>
          ) : (
            <EmptyToolState>
              Choose a Deck item to inspect its output sections.
            </EmptyToolState>
          )}
        </section>
      </div>
    );
  if (bench === "Red-Teamer")
    return (
      <section className="space-y-5">
        <div className="flex items-center gap-3">
          <Swords className="size-5 text-gold" />
          <div>
            <h2 className="text-lg font-semibold">Red-Teamer</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Battle cards show the principal vulnerabilities and counterpoints
              from the selected brief.
            </p>
          </div>
        </div>
        {analyses.length ? (
          <section className="space-y-2">
            <h3 className="font-mono text-[10px] uppercase tracking-widest text-steel">
              Recent analysis available to challenge
            </h3>
            {analyses.slice(0, 5).map((analysis) => (
              <article
                key={analysis.analysis_id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border p-4"
              >
                <div>
                  <p className="text-sm font-medium">
                    {PACK_LABEL[analysis.prompt_pack] ?? analysis.prompt_pack}
                  </p>
                  <p className="mt-1 font-mono text-[10px] text-muted-foreground">
                    {analysis.analysis_id.slice(0, 8)} ┬╖ {analysis.status}
                  </p>
                </div>
                <div className="flex gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => onReview(analysis.analysis_id)}
                  >
                    Open output
                  </Button>
                  <Button type="button" size="sm" onClick={onAssistant}>
                    Challenge with Assistant
                  </Button>
                </div>
              </article>
            ))}
          </section>
        ) : (
          <div className="rounded-xl border border-dashed border-border p-6 text-sm text-muted-foreground">
            No SmartBrief outputs are available yet. Run an analysis in the
            SmartBrief bench, then return here to challenge its reasoning.
          </div>
        )}
      </section>
    );
  if (bench === "Researcher")
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <Scale className="size-5 text-gold" />
          <div>
            <h2 className="text-lg font-semibold">Researcher</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Search the existing Vault index and inspect grounded, page-pinned
              results.
            </p>
          </div>
        </div>
        <div className="grid items-start gap-4 xl:grid-cols-[minmax(18rem,0.8fr)_minmax(0,1.6fr)]">
          <section
            aria-label="Research inputs"
            className="panel space-y-4 p-4 sm:p-5"
          >
            <form
              className="space-y-3"
              onSubmit={(event) => {
                event.preventDefault();
                const question = researchQuestion.trim();
                if (question.length < 10 || research.isPending) return;
                setResearchNotice("");
                setActiveResearchQuestion(question);
                research.mutate(
                  {
                    question,
                    court_level: researchCourt || null,
                    year_from: researchYearFrom || null,
                    year_to: researchYearTo || null,
                    ratio_decidendi: researchRatio || null,
                  },
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
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="space-y-1.5 text-xs text-muted-foreground">
                  <span className="font-mono uppercase tracking-widest">
                    Court
                  </span>
                  <select
                    value={researchCourt}
                    onChange={(event) => setResearchCourt(event.target.value)}
                    className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-gold"
                  >
                    {COURT_LEVELS.map((court) => (
                      <option
                        key={`${court.label}:${court.value}`}
                        value={court.value}
                      >
                        {court.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="space-y-1.5 text-xs text-muted-foreground">
                  <span className="font-mono uppercase tracking-widest">
                    Ratio / topic
                  </span>
                  <input
                    value={researchRatio}
                    onChange={(event) => setResearchRatio(event.target.value)}
                    maxLength={200}
                    placeholder="Optional legal principle"
                    className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-gold"
                  />
                </label>
                <label className="space-y-1.5 text-xs text-muted-foreground">
                  <span className="font-mono uppercase tracking-widest">
                    From year
                  </span>
                  <input
                    type="number"
                    min={1960}
                    max={2026}
                    value={researchYearFrom}
                    onChange={(event) =>
                      setResearchYearFrom(
                        event.target.value ? Number(event.target.value) : "",
                      )
                    }
                    placeholder="1960"
                    className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-gold"
                  />
                </label>
                <label className="space-y-1.5 text-xs text-muted-foreground">
                  <span className="font-mono uppercase tracking-widest">
                    To year
                  </span>
                  <input
                    type="number"
                    min={1960}
                    max={2026}
                    value={researchYearTo}
                    onChange={(event) =>
                      setResearchYearTo(
                        event.target.value ? Number(event.target.value) : "",
                      )
                    }
                    placeholder="2026"
                    className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-gold"
                  />
                </label>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <Button
                  type="submit"
                  disabled={
                    researchQuestion.trim().length < 10 || research.isPending
                  }
                >
                  <Scale className="mr-2 size-4" />
                  {research.isPending ? "SearchingΓÇª" : "Search authorities"}
                </Button>
                <span className="text-xs text-muted-foreground">
                  Minimum 10 characters ┬╖ verified citations only
                </span>
              </div>
            </form>
          </section>
          <section
            aria-label="Research results"
            className="panel min-w-0 space-y-4 p-4 sm:p-5"
          >
            {research.isPending && (
              <div
                className="flex items-center gap-2 rounded-xl border border-border p-5 text-sm text-muted-foreground"
                role="status"
              >
                <Loader2 className="size-4 animate-spin" /> Searching the Vault…
              </div>
            )}
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
                tab={researchTab}
                authorityLimit={research.data.citations.length}
                onAssistant={onAssistant}
              />
            )}
            {!research.data && !research.isPending && !research.isError && (
              <EmptyToolState>
                Submit a legal question to review the research report and
                citations here.
              </EmptyToolState>
            )}
          </section>
        </div>
      </div>
    );
  if (bench === "Reviewer")
    return (
      <div className="space-y-4">
        <div>
          <h2 className="text-lg font-semibold">Reviewer</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Select a contract review to inspect its existing analysis sections
            and supporting authorities.
          </p>
          {reviewerSpecialty && (
            <p className="mt-2 rounded-lg border border-gold/20 bg-gold/5 px-3 py-2 text-xs text-muted-foreground">
              Review focus · {reviewerSpecialty}
            </p>
          )}
        </div>
        <div className="grid items-start gap-4 xl:grid-cols-[minmax(18rem,0.8fr)_minmax(0,1.6fr)]">
          <section
            aria-label="Contract review queue"
            className="panel space-y-4 p-4 sm:p-5"
          >
            <div className="space-y-3">
              <h3 className="font-mono text-[10px] uppercase tracking-widest text-steel">
                Contract review deck
              </h3>
              {reviewQueue.length ? (
                reviewQueue.map((analysis) => (
                  <article
                    key={analysis.analysis_id}
                    className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-warning/30 p-4"
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-medium">
                        {PACK_LABEL[analysis.prompt_pack] ??
                          analysis.prompt_pack}
                      </p>
                      <p className="mt-1 font-mono text-[10px] text-muted-foreground">
                        {analysis.analysis_id.slice(0, 8)} ┬╖{" "}
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
                        onClick={() => {
                          setSelectedReviewId(analysis.analysis_id);
                          onSelect(analysis.analysis_id);
                        }}
                      >
                        Open review
                      </Button>
                    </div>
                  </article>
                ))
              ) : (
                <div className="rounded-xl border border-dashed border-border p-5 text-sm text-muted-foreground">
                  No contract reviews are available yet. Run Contract Review
                  from SmartBrief, then return here to inspect its output.
                </div>
              )}
            </div>
            <section className="space-y-2 border-t border-border pt-4">
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
                      {new Date(entry.starts_at).toLocaleString()} ┬╖{" "}
                      {entry.status}
                    </p>
                  </article>
                ))
              ) : (
                <div className="rounded-xl border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
                  No court diary entries available.
                </div>
              )}
            </section>
          </section>
          <section
            aria-label="Contract review output"
            className="panel min-w-0 space-y-4 p-4 sm:p-5"
          >
            {activeReviewId ? (
              <AnalysisWorkspace
                id={activeReviewId}
                tab={reviewerTab}
                reviewerMode
              />
            ) : (
              <EmptyToolState>
                Choose an item in the review queue to inspect its available
                analysis output. Reviewer sections reflect fields returned by
                that analysis; no additional fields are inferred.
              </EmptyToolState>
            )}
          </section>
        </div>
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

function readFileAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1] ?? "");
    reader.onerror = () => reject(new Error("Could not read the brief."));
    reader.readAsDataURL(file);
  });
}

function ToolMenu({
  label,
  items,
  active,
  onSelect,
  action,
}: {
  label: string;
  items: Array<{ id: string; label: string }>;
  active: string;
  onSelect: (id: string) => void;
  action?: { label: string; onClick: () => void };
}) {
  return (
    <nav
      aria-label={label}
      className="flex min-w-0 flex-wrap items-center gap-1"
    >
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          aria-current={active === item.id ? "page" : undefined}
          onClick={() => onSelect(item.id)}
          className={`rounded-lg border px-3 py-2 text-xs transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold ${active === item.id ? "border-gold/50 bg-gold/10 text-gold" : "border-transparent text-muted-foreground hover:border-border hover:text-foreground"}`}
        >
          {item.label}
        </button>
      ))}
      {action && (
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={action.onClick}
        >
          {action.label}
        </Button>
      )}
    </nav>
  );
}

function RedteamSummary({
  card,
  tab,
  onProbe,
}: {
  card: BattleCard;
  tab: RedteamTab;
  onProbe: () => void;
}) {
  const flaws = card.sections.procedural_flaws;
  const opposing = card.sections.opposing_arguments;
  const authorities = Array.from(
    new Set([
      ...flaws.flatMap((item) => item.authority),
      ...opposing.flatMap((item) => item.authority),
    ]),
  );
  return (
    <div className="space-y-4">
      <div className="panel border-gold/30 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            {card.critic_verdict.pass ? (
              <CheckCircle2 className="size-4 text-success" />
            ) : (
              <ShieldAlert className="size-4 text-warning" />
            )}
            <h3 className="text-sm font-semibold">Battle card</h3>
          </div>
          <span className="font-mono text-[10px] text-muted-foreground">
            {new Date(card.generated_at).toLocaleDateString("en-GB")}
          </span>
        </div>
        <p className="mt-2 text-xs text-muted-foreground">
          Matter {card.matter_id} · source {card.source_document_id.slice(0, 8)}
          {" · "}
          {card.critic_verdict.pass
            ? "Critic checks passed"
            : "Manual review recommended"}
        </p>
      </div>
      {tab === "flaws" && (
        <section className="panel space-y-3 p-5">
          <h4 className="flex items-center gap-2 font-semibold">
            <FileWarning className="size-4 text-warning" /> Procedural flaws
          </h4>
          {card.sections.procedural_flaws.length ? (
            card.sections.procedural_flaws.map((flaw) => (
              <article
                key={flaw.flaw}
                className="rounded-lg border border-border p-3"
              >
                <div className="flex flex-wrap items-center justify-between gap-2 text-sm font-medium">
                  {flaw.flaw}
                  <span className="font-mono text-[10px] text-warning">
                    {flaw.severity} · {Math.round(flaw.confidence * 100)}%
                  </span>
                </div>
                <p className="mt-2 text-xs text-muted-foreground">
                  {flaw.basis}
                </p>
                <AuthorityChips authority={flaw.authority} />
              </article>
            ))
          ) : (
            <p className="text-sm text-muted-foreground">
              No procedural flaws were returned.
            </p>
          )}
        </section>
      )}
      {tab === "opposing" && (
        <section className="panel space-y-3 p-5">
          <h4 className="font-semibold">Opposing arguments</h4>
          {card.sections.opposing_arguments.length ? (
            card.sections.opposing_arguments.map((argument) => (
              <article
                key={argument.argument}
                className="rounded-lg border border-border p-3"
              >
                <p className="text-sm font-medium">{argument.argument}</p>
                <p className="mt-2 text-xs text-muted-foreground">
                  Our counter: {argument.our_counter}
                </p>
                <div className="mt-2 flex flex-wrap items-center gap-2 font-mono text-[10px] text-steel">
                  Strength {argument.strength}/10 · confidence{" "}
                  {Math.round(argument.confidence * 100)}%
                  {argument.manual_review && (
                    <span className="text-warning">Manual review</span>
                  )}
                </div>
                <AuthorityChips authority={argument.authority} />
              </article>
            ))
          ) : (
            <p className="text-sm text-muted-foreground">
              No opposing arguments were returned.
            </p>
          )}
        </section>
      )}
      {tab === "counters" && (
        <section className="panel space-y-3 p-5">
          <h4 className="font-semibold">Counters</h4>
          {opposing.length ? (
            opposing.map((argument) => (
              <article
                key={argument.argument}
                className="rounded-lg border border-border p-3"
              >
                <p className="text-xs text-muted-foreground">
                  Response to: {argument.argument}
                </p>
                <p className="mt-2 text-sm">
                  {argument.our_counter || "No counter returned."}
                </p>
                <AuthorityChips authority={argument.authority} />
              </article>
            ))
          ) : (
            <EmptyToolState>Battle card returned no counters.</EmptyToolState>
          )}
        </section>
      )}
      {tab === "authorities" && (
        <section className="panel space-y-3 p-5">
          <h4 className="font-semibold">Authorities</h4>
          {authorities.length ? (
            <AuthorityChips authority={authorities} />
          ) : (
            <EmptyToolState>
              No authorities were returned in this battle card.
            </EmptyToolState>
          )}
        </section>
      )}
      {tab === "probe" && (
        <section className="panel space-y-3 p-5">
          <h4 className="font-semibold">Probe this battle card</h4>
          <p className="text-sm text-muted-foreground">
            Ask the cross-bench Assistant to probe the returned flaws,
            counterarguments, and authorities.
          </p>
          <Button type="button" onClick={onProbe}>
            <MessageSquare className="mr-2 size-4" />
            Probe with Assistant
          </Button>
        </section>
      )}
    </div>
  );
}

function EmptyToolState({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-lg border border-dashed border-border p-4 text-sm text-muted-foreground">
      {children}
    </p>
  );
}

function ResearchResults({
  question,
  answer,
  refusal,
  citations,
  tab,
  authorityLimit,
  onAssistant,
}: {
  question: string;
  answer: string;
  refusal: boolean;
  citations: Citation[];
  tab: ResearchTab;
  authorityLimit: number;
  onAssistant: () => void;
}) {
  const visibleCitations = citations.slice(0, authorityLimit);
  return (
    <section aria-live="polite" className="min-w-0 space-y-3">
      {tab === "report" ? (
        <>
          <p className="font-mono text-[10px] uppercase tracking-widest text-steel">
            Question · {question}
          </p>
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
            <p className="mt-3 whitespace-pre-wrap text-sm leading-6">
              {answer}
            </p>
            {refusal && (
              <p className="mt-3 text-xs text-warning">
                Do not rely on this as a verified answer. Refine the question or
                consult the source material.
              </p>
            )}
          </div>
        </>
      ) : tab === "authorities" ? (
        <div>
          <h3 className="mb-2 font-mono text-[10px] uppercase tracking-widest text-steel">
            Authorities ({visibleCitations.length})
          </h3>
          {visibleCitations.length ? (
            <div className="space-y-2">
              {visibleCitations.map((citation) => (
                <article
                  key={`${citation.document_id}:${citation.page_start}:${citation.citation}`}
                  className="rounded-xl border border-border p-3"
                >
                  <h4 className="text-sm font-medium">{citation.case_title}</h4>
                  <p className="mt-1 font-mono text-xs text-gold">
                    {citation.citation}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {citation.court_level} · {citation.year} ·{" "}
                    {citation.verified ? "Verified" : "Unverified"}
                  </p>
                </article>
              ))}
            </div>
          ) : (
            <EmptyToolState>
              No authorities returned for this research.
            </EmptyToolState>
          )}
        </div>
      ) : (
        <div>
          <h3 className="mb-2 font-mono text-[10px] uppercase tracking-widest text-steel">
            Pinned passages
          </h3>
          {visibleCitations.length ? (
            <div className="space-y-2">
              {visibleCitations.map((citation) => (
                <article
                  key={`${citation.document_id}:${citation.page_start}:${citation.citation}`}
                  className="rounded-xl border border-border p-3"
                >
                  <h4 className="text-sm font-medium">{citation.case_title}</h4>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Page {citation.page_start}–{citation.page_end}
                    {citation.paragraph_refs.length
                      ? ` · ¶ ${citation.paragraph_refs.join(", ¶ ")}`
                      : ""}
                  </p>
                  {citation.source_pdf_url && (
                    <a
                      href={citation.source_pdf_url}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-2 inline-flex text-xs underline hover:text-gold"
                    >
                      Open source PDF
                    </a>
                  )}
                </article>
              ))}
            </div>
          ) : (
            <EmptyToolState>No source passages were returned.</EmptyToolState>
          )}
        </div>
      )}
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

function AnalysisWorkspace({
  id,
  tab: selectedTab,
  reviewerMode = false,
}: {
  id: string;
  tab?: WorkbenchTab;
  reviewerMode?: boolean;
}) {
  const analysis = useAnalysis(id);
  const [localTab, setLocalTab] = useState<WorkbenchTab>("overview");
  const tab = selectedTab ?? localTab;

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
      {!reviewerMode && (
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
              onClick={() => setLocalTab(item.id)}
              className={`shrink-0 border-b-2 px-3 py-2 text-xs font-medium transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold ${tab === item.id ? "border-gold text-gold" : "border-transparent text-muted-foreground hover:text-foreground"}`}
            >
              {item.label}
            </button>
          ))}
        </nav>
      )}
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
