// CoachMarks — a shared, dismissible 3-step onboarding overlay shown once per
// (user, surface) pair. Part 3 Slice 3.
//
//  - One shared component; each surface passes a `surface` id and its steps.
//  - "Shown once and stays dismissed": completion is recorded in localStorage under
//    `redcase.coach.<user_ref>.<surface>`. It is NEVER server-persisted (and
//    carries no PII beyond the surface id + the existing local user_ref).
//  - If the flag exists (truthy), the overlay is suppressed entirely.
//
// UX: lightbox with a glass panel, step dots, Previous/Next, "Got it" on the
// last step. Accessible (role="dialog", labelled, Escape to dismiss, focus moved
// onto the panel when open).

import { useEffect, useRef, useState } from "react";
import { X, ChevronLeft, ChevronRight, Sparkles } from "lucide-react";
import { getSession } from "@/lib/auth/supabase";

export interface CoachStep {
  title: string;
  body: string;
}

interface CoachMarksProps {
  /** Namespace for the (user, surface) dismissal key, e.g. "search". */
  surface: string;
  steps: CoachStep[];
  /** Optional icon shown in the panel header. */
  icon?: typeof Sparkles;
}

const PREFIX = "redcase.coach";

function storageKey(surface: string): string {
  // Fail-safe: if we cannot identify the user we still key per-surface so the
  // overlay never loops every navigation.
  const ref = getSession()?.user_ref ?? "anon";
  return `${PREFIX}.${ref}.${surface}`;
}

function isDismissed(surface: string): boolean {
  if (typeof window === "undefined") return true;
  const key = storageKey(surface);
  return Boolean(window.localStorage.getItem(key));
}

function markDismissed(surface: string): void {
  if (typeof window === "undefined") return;
  const key = storageKey(surface);
  window.localStorage.setItem(key, "1");
}


export function CoachMarks({ surface, steps, icon: Icon = Sparkles }: CoachMarksProps) {
  const [open, setOpen] = useState<boolean>(false);
  const [step, setStep] = useState(0);
  const panelRef = useRef<HTMLDivElement>(null);

  // Initialize once on mount: only open if not already dismissed for this surface.
  useEffect(() => {
    if (!isDismissed(surface)) setOpen(true);
  }, [surface]);

  // Move focus into the dialog and lock Escape to dismiss.
  useEffect(() => {
    if (!open) return;
    panelRef.current?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") finish();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, surface]);

  if (!open || steps.length === 0) return null;

  const last = step === steps.length - 1;
  const current = steps[step]!;

  function finish() {
    markDismissed(surface);
    setOpen(false);
  }

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label={`${current.title} — guided tour`}
    >
      <div
        ref={panelRef}
        tabIndex={-1}
        className="w-full max-w-md rounded-2xl border border-gold/30 bg-surface p-6 shadow-elevated outline-none"
      >
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-2.5">
            <span className="flex size-9 items-center justify-center rounded-lg bg-gold/15 text-gold">
              <Icon className="size-5" />
            </span>
            <span className="font-mono text-[10px] uppercase tracking-[0.28em] text-muted-foreground">
              Guided tour · {step + 1} of {steps.length}
            </span>
          </div>
          <button
            onClick={finish}
            aria-label="Dismiss"
            className="rounded-lg p-1.5 text-muted-foreground transition-colors duration-200 hover:bg-border/60 hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/50"
          >
            <X className="size-4" />
          </button>
        </div>

        <h2 className="mt-5 font-display text-xl font-semibold text-foreground">
          {current.title}
        </h2>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          {current.body}
        </p>

        <div className="mt-6 flex items-center justify-between">
          {/* Step dots */}
          <div className="flex items-center gap-1.5">
            {steps.map((_, i) => (
              <button
                key={i}
                onClick={() => setStep(i)}
                aria-label={`Go to step ${i + 1}`}
                className={`h-1.5 rounded-full transition-all duration-200 ${
                  i === step ? "w-5 bg-gold" : "w-1.5 bg-steel/40 hover:bg-steel/60"
                }`}
              />
            ))}
          </div>

          <div className="flex items-center gap-2">
            {step > 0 && (
              <button
                onClick={() => setStep((s) => s - 1)}
                className="inline-flex items-center gap-1 rounded-lg border border-border px-3 py-2 text-sm font-medium text-muted-foreground transition-all duration-200 hover:border-gold/50 hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/50"
              >
                <ChevronLeft className="size-4" /> Back
              </button>
            )}
            {last ? (
              <button
                onClick={finish}
                className="inline-flex items-center gap-1.5 rounded-lg bg-gold px-4 py-2 text-sm font-semibold text-background transition-all duration-200 hover:bg-gold/90 hover:shadow-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/50"
              >
                <Sparkles className="size-4" /> Got it
              </button>
            ) : (
              <button
                onClick={() => setStep((s) => s + 1)}
                className="inline-flex items-center gap-1 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-all duration-200 hover:bg-primary/90 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/50"
              >
                Next <ChevronRight className="size-4" />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

