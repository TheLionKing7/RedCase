import { createFileRoute } from "@tanstack/react-router";
import { useRef, useState } from "react";
import {
  UploadCloud,
  FileWarning,
  Gavel,
  Swords,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  RotateCcw,
  ShieldAlert,
  BadgeCheck,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { ApiError } from "@/lib/api/client";
import { useBattleCard } from "@/lib/api/redteam";
import type { BattleCard, BattleSeverity } from "@/lib/api/redteam";

export const Route = createFileRoute("/_authed/red-teamer")({
  head: () => ({
    meta: [
      { title: "Red-Teamer — RedCase" },
      {
        name: "description",
        content:
          "Upload an opposing party's brief and generate a Battle Card of procedural flaws, argument strength ratings and binding counter-precedents.",
      },
      { property: "og:title", content: "Red-Teamer — RedCase" },
      {
        property: "og:description",
        content:
          "Adversarial brief analysis with procedural kill-shots and Supreme Court counter-authority.",
      },
    ],
  }),
  component: RedTeamer,
});

type Phase = "idle" | "loaded" | "running" | "done";

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1] ?? "");
    reader.onerror = () => reject(new Error("Could not read the file"));
    reader.readAsDataURL(file);
  });
}

function RedTeamer() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [file, setFile] = useState<File | null>(null);
  const [fileName, setFileName] = useState("");
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const battleCard = useBattleCard();

  function accept(f?: File) {
    if (!f) return;
    setFile(f);
    setFileName(f.name);
    setPhase("loaded");
  }

  async function analyze() {
    if (!file || battleCard.isPending) return;
    setPhase("running");
    try {
      await battleCard.mutateAsync({
        document_name: file.name,
        content_base64: await fileToBase64(file),
      });
      setPhase("done");
    } catch {
      setPhase("loaded"); // error state renders below; brief stays loaded
    }
  }

  function reset() {
    battleCard.reset();
    setFile(null);
    setFileName("");
    setPhase("idle");
  }

  return (
    <AppShell eyebrow="Adversarial Analysis" title="Red-Teamer">
      <div className="mx-auto max-w-6xl space-y-6">
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            accept(e.dataTransfer.files?.[0]);
          }}
          onClick={() => inputRef.current?.click()}
          className={`panel flex cursor-pointer flex-col items-center justify-center gap-3 border-dashed px-6 py-14 text-center transition-all ${
            dragging ? "glow-steel border-steel" : "hover:border-gold/50"
          }`}
        >
          <input
            ref={inputRef}
            type="file"
            className="hidden"
            onChange={(e) => accept(e.target.files?.[0] ?? undefined)}
          />
          <UploadCloud className="size-9 text-steel" />
          <div className="text-base font-semibold">
            {phase === "idle"
              ? "Drop the opposing party's brief here"
              : fileName}
          </div>
          <p className="max-w-md text-sm text-muted-foreground">
            PDF, DOCX or scanned filings up to 200MB. Documents are processed
            inside the Aetoes tenancy — nothing leaves the firm's vault.
          </p>
          {phase !== "idle" && file && (
            <span className="inline-flex items-center gap-1.5 text-xs text-success">
              <CheckCircle2 className="size-3.5" /> Loaded ·{" "}
              {(file.size / 1024 / 1024).toFixed(1)} MB · privilege lock applied
            </span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button
            disabled={phase === "idle" || battleCard.isPending}
            onClick={analyze}
            className="inline-flex items-center gap-2 rounded-lg bg-gold px-6 py-3 text-sm font-semibold text-gold-foreground transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {battleCard.isPending ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Swords className="size-4" />
            )}
            {battleCard.isPending
              ? "Running Red-Team Analysis…"
              : "Analyze Brief"}
          </button>
          {phase === "done" && (
            <button
              onClick={reset}
              className="inline-flex items-center gap-2 rounded-lg border border-border px-4 py-3 text-sm text-muted-foreground hover:text-foreground"
            >
              <RotateCcw className="size-4" /> Reset
            </button>
          )}
          {phase === "idle" && (
            <span className="text-xs text-muted-foreground">
              Upload a brief to enable analysis.
            </span>
          )}
        </div>

        {battleCard.isError && <RedteamErrorState error={battleCard.error} />}

        {battleCard.isPending && (
          <div className="panel bg-background/60 p-5 font-mono text-xs leading-relaxed text-muted-foreground">
            Analyzing brief — extraction, procedural-gate checks,
            counter-precedent matching, and critic review. This can take a
            minute or two.
          </div>
        )}

        {phase === "done" && battleCard.data && (
          <BattleCardView card={battleCard.data} />
        )}
      </div>
    </AppShell>
  );
}

function severityStyle(sev: BattleSeverity): string {
  // §1.2 severities: HIGH | MED | LOW.
  if (sev === "HIGH") return "bg-destructive/15 text-destructive";
  if (sev === "MED") return "bg-warning/15 text-warning";
  return "bg-muted text-muted-foreground";
}

/** Authority chip — §1.2 authority entries are namespace-qualified ids
 *  ("B:doc_uuid" / "A:doc_uuid"); rendered as-is, never fabricated. */
function AuthorityChips({ authority }: { authority: string[] }) {
  if (authority.length === 0) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {authority.map((a) => (
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

function BattleCardView({ card }: { card: BattleCard }) {
  const generated = new Date(card.generated_at).toLocaleDateString("en-GB");
  return (
    <div className="space-y-6">
      <div className="panel glow-gold p-6">
        <div className="font-mono text-[10px] uppercase tracking-[0.28em] text-gold">
          Battle Card · Generated {generated}
        </div>
        <h2 className="mt-2 font-mono text-sm text-muted-foreground">
          Matter <span className="text-foreground">{card.matter_id}</span>
        </h2>
        <p className="mt-1 font-mono text-[11px] text-muted-foreground">
          Source document {card.source_document_id}
        </p>
      </div>

      <section className="panel p-6">
        <h3 className="flex items-center gap-2 text-lg font-semibold">
          <FileWarning className="size-4 text-destructive" /> Procedural Flaws
        </h3>
        <div className="mt-4 space-y-3">
          {card.sections.procedural_flaws.map((f) => (
            <div
              key={f.flaw}
              className="rounded-lg border border-border bg-background/40 p-4"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium">{f.flaw}</span>
                <span
                  className={`rounded-full px-2.5 py-0.5 font-mono text-[10px] uppercase tracking-widest ${severityStyle(f.severity)}`}
                >
                  {f.severity}
                </span>
              </div>
              <p className="mt-2 text-sm text-foreground/85">{f.basis}</p>
              <AuthorityChips authority={f.authority} />
              <p className="mt-2 font-mono text-[11px] text-muted-foreground">
                Confidence {(f.confidence * 100).toFixed(0)}%
              </p>
            </div>
          ))}
        </div>
      </section>

      <section className="panel p-6">
        <h3 className="flex items-center gap-2 text-lg font-semibold">
          <AlertTriangle className="size-4 text-warning" /> Opposing Argument
          Strength
        </h3>
        <div className="mt-4 space-y-5">
          {card.sections.opposing_arguments.map((a) => (
            <div key={a.argument}>
              <div className="flex items-start justify-between gap-4">
                <p className="text-sm font-medium">
                  {a.argument}
                  {a.manual_review && (
                    <span className="ml-2 rounded-full bg-warning/15 px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest text-warning">
                      [MANUAL REVIEW]
                    </span>
                  )}
                </p>
                <span className="shrink-0 font-mono text-sm text-steel">
                  {a.strength}/10
                </span>
              </div>
              <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-muted">
                <div
                  className={`h-full rounded-full ${
                    a.strength >= 7
                      ? "bg-destructive"
                      : a.strength >= 5
                        ? "bg-warning"
                        : "bg-success"
                  }`}
                  style={{ width: `${a.strength * 10}%` }}
                />
              </div>
              <p className="mt-2 text-sm text-muted-foreground">
                <span className="font-mono text-[10px] uppercase tracking-widest text-gold">
                  Our counter ·{" "}
                </span>
                {a.our_counter}
              </p>
              <AuthorityChips authority={a.authority} />
              <p className="mt-2 font-mono text-[11px] text-muted-foreground">
                Confidence {(a.confidence * 100).toFixed(0)}%
              </p>
            </div>
          ))}
        </div>
      </section>

      {card.sections.jurisdictional_notes.length > 0 && (
        <section className="panel p-6">
          <h3 className="flex items-center gap-2 text-lg font-semibold">
            <Gavel className="size-4 text-gold" /> Jurisdictional Notes
          </h3>
          <ul className="mt-4 list-disc space-y-2 pl-5 text-sm text-foreground/85">
            {card.sections.jurisdictional_notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </section>
      )}

      <footer
        className={`panel flex flex-wrap items-center justify-between gap-3 p-4 text-xs ${
          card.critic_verdict.pass ? "border-success/40" : "border-warning/40"
        }`}
      >
        <span
          className={`inline-flex items-center gap-1.5 font-mono uppercase tracking-widest ${
            card.critic_verdict.pass ? "text-success" : "text-warning"
          }`}
        >
          {card.critic_verdict.pass ? (
            <BadgeCheck className="size-4" />
          ) : (
            <ShieldAlert className="size-4" />
          )}
          Critic {card.critic_verdict.pass ? "PASS" : "DOWNGRADED"} ·{" "}
          {card.critic_verdict.regenerations} regenerations
        </span>
        <span className="text-muted-foreground">
          ADVISORY — for counsel review. Not legal advice.
          {card.critic_verdict.downgraded_sections.length > 0 &&
            ` Downgraded: ${card.critic_verdict.downgraded_sections.join(", ")}`}
        </span>
      </footer>
    </div>
  );
}

function RedteamErrorState({ error }: { error: unknown }) {
  const auth = error instanceof ApiError && error.isAuthError;
  return (
    <section className="panel border-destructive/40 p-6">
      <h2 className="flex items-center gap-2 text-base font-semibold text-destructive">
        <ShieldAlert className="size-4" />
        {auth ? "Sign-in required" : "Analysis failed"}
      </h2>
      <p className="mt-2 text-sm text-muted-foreground">
        {auth
          ? "Your Supabase session is missing or expired. Sign in again with the email magic link."
          : error instanceof Error
            ? error.message
            : "Unknown error — the Red-Teamer endpoint lands in Phase 3 (set VITE_API_DEV_ADAPTER=1 to preview with schema-shaped data)."}
      </p>
    </section>
  );
}
