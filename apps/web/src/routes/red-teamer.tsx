import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import {
  UploadCloud,
  FileWarning,
  Gavel,
  Swords,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  RotateCcw,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { BATTLE_CARD, STREAM_LINES } from "@/lib/aetoes-data";

export const Route = createFileRoute("/red-teamer")({
  head: () => ({
    meta: [
      { title: "Case Red-Teamer — Aetoes Ops Hub" },
      {
        name: "description",
        content:
          "Upload an opposing party's brief and generate a Battle Card of procedural flaws, argument strength ratings and binding counter-precedents.",
      },
      { property: "og:title", content: "Case Red-Teamer — Aetoes Ops Hub" },
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

function RedTeamer() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [fileName, setFileName] = useState("");
  const [dragging, setDragging] = useState(false);
  const [lines, setLines] = useState<string[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (phase !== "running") return;
    let i = 0;
    const t = setInterval(() => {
      i += 1;
      setLines(STREAM_LINES.slice(0, i));
      if (i >= STREAM_LINES.length) {
        clearInterval(t);
        setTimeout(() => setPhase("done"), 700);
      }
    }, 620);
    return () => clearInterval(t);
  }, [phase]);

  function accept(name?: string) {
    setFileName(name || "Meridian_Reply_Brief_FHC_L_CS_1184_2026.pdf");
    setPhase("loaded");
    setLines([]);
  }

  return (
    <AppShell eyebrow="Adversarial Analysis" title="Case Red-Teamer">
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
            accept(e.dataTransfer.files?.[0]?.name);
          }}
          onClick={() => inputRef.current?.click()}
          className={`panel flex cursor-pointer flex-col items-center justify-center gap-3 border-dashed px-6 py-14 text-center transition-all ${
            dragging ? "glow-cyan border-cyan" : "hover:border-gold/50"
          }`}
        >
          <input
            ref={inputRef}
            type="file"
            className="hidden"
            onChange={(e) => accept(e.target.files?.[0]?.name)}
          />
          <UploadCloud className="size-9 text-cyan" />
          <div className="text-base font-semibold">
            {phase === "idle" ? "Drop the opposing party's brief here" : fileName}
          </div>
          <p className="max-w-md text-sm text-muted-foreground">
            PDF, DOCX or scanned filings up to 200MB. Documents are processed inside the Aetoes
            tenancy — nothing leaves the firm's vault.
          </p>
          {phase !== "idle" && (
            <span className="inline-flex items-center gap-1.5 text-xs text-success">
              <CheckCircle2 className="size-3.5" /> Ingested · 34 pages · privilege lock applied
            </span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button
            disabled={phase === "idle" || phase === "running"}
            onClick={() => setPhase("running")}
            className="inline-flex items-center gap-2 rounded-lg bg-gold px-6 py-3 text-sm font-semibold text-gold-foreground transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {phase === "running" ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Swords className="size-4" />
            )}
            {phase === "running" ? "Running Red-Team Analysis…" : "Analyze Brief"}
          </button>
          {phase === "done" && (
            <button
              onClick={() => {
                setPhase("idle");
                setLines([]);
              }}
              className="inline-flex items-center gap-2 rounded-lg border border-border px-4 py-3 text-sm text-muted-foreground hover:text-foreground"
            >
              <RotateCcw className="size-4" /> Reset
            </button>
          )}
          {phase === "idle" && (
            <span className="text-xs text-muted-foreground">Upload a brief to enable analysis.</span>
          )}
        </div>

        {lines.length > 0 && (
          <div className="panel bg-background/60 p-5 font-mono text-xs leading-relaxed">
            {lines.map((l, i) => (
              <div
                key={l}
                className={i === lines.length - 1 && phase === "running" ? "stream-caret text-cyan" : "text-muted-foreground"}
              >
                {l}
              </div>
            ))}
          </div>
        )}

        {phase === "done" && <BattleCard />}
      </div>
    </AppShell>
  );
}

function BattleCard() {
  return (
    <div className="space-y-6">
      <div className="panel glow-gold p-6">
        <div className="font-mono text-[10px] uppercase tracking-[0.28em] text-gold">
          Battle Card · Generated {new Date().toLocaleDateString("en-GB")}
        </div>
        <h2 className="mt-2 text-xl font-semibold">{BATTLE_CARD.matter}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{BATTLE_CARD.filedBy}</p>
        <p className="mt-4 rounded-lg bg-surface-raised px-4 py-3 text-sm">
          <span className="font-mono text-[10px] uppercase tracking-widest text-cyan">
            Overall exposure
          </span>
          <br />
          {BATTLE_CARD.overallRisk}
        </p>
      </div>

      <section className="panel p-6">
        <h3 className="flex items-center gap-2 text-lg font-semibold">
          <FileWarning className="size-4 text-destructive" /> Procedural Flaws
        </h3>
        <div className="mt-4 space-y-3">
          {BATTLE_CARD.flaws.map((f) => (
            <div key={f.title} className="rounded-lg border border-border bg-background/40 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium">{f.title}</span>
                <span
                  className={`rounded-full px-2.5 py-0.5 font-mono text-[10px] uppercase tracking-widest ${
                    f.severity === "Critical"
                      ? "bg-destructive/15 text-destructive"
                      : f.severity === "High"
                        ? "bg-warning/15 text-warning"
                        : "bg-muted text-muted-foreground"
                  }`}
                >
                  {f.severity}
                </span>
              </div>
              <p className="mt-2 text-sm text-foreground/85">{f.detail}</p>
              <p className="mt-2 font-mono text-[11px] text-gold">{f.rule}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="panel p-6">
        <h3 className="flex items-center gap-2 text-lg font-semibold">
          <AlertTriangle className="size-4 text-warning" /> Opposing Argument Strength
        </h3>
        <div className="mt-4 space-y-5">
          {BATTLE_CARD.arguments.map((a) => (
            <div key={a.argument}>
              <div className="flex items-start justify-between gap-4">
                <p className="text-sm font-medium">{a.argument}</p>
                <span className="shrink-0 font-mono text-sm text-cyan">{a.strength}/100</span>
              </div>
              <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-muted">
                <div
                  className={`h-full rounded-full ${
                    a.strength >= 65 ? "bg-destructive" : a.strength >= 45 ? "bg-warning" : "bg-success"
                  }`}
                  style={{ width: `${a.strength}%` }}
                />
              </div>
              <p className="mt-2 text-sm text-muted-foreground">
                <span className="font-mono text-[10px] uppercase tracking-widest text-gold">
                  Our rebuttal ·{" "}
                </span>
                {a.rebuttal}
              </p>
            </div>
          ))}
        </div>
      </section>

      <section className="panel p-6">
        <h3 className="flex items-center gap-2 text-lg font-semibold">
          <Gavel className="size-4 text-gold" /> Binding Counter-Precedents
        </h3>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          {BATTLE_CARD.precedents.map((p) => (
            <div key={p.case} className="rounded-lg border border-border bg-background/40 p-4">
              <div className="font-semibold">{p.case}</div>
              <div className="font-mono text-xs text-gold">{p.citation}</div>
              <p className="mt-2 text-sm text-foreground/85">{p.holding}</p>
              <div className="mt-3 inline-flex items-center gap-1.5 rounded-full border border-cyan/40 px-2.5 py-1 font-mono text-[10px] text-cyan">
                Verified citation · {p.page}
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
