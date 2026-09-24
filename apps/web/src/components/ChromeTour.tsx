import { useEffect, useRef, useState, type ReactElement } from "react";
import { ChevronLeft, ChevronRight, Compass, Sparkles, X } from "lucide-react";
import { getSession } from "@/lib/auth/supabase";

const REPLAY_EVENT = "redcase:replay-chrome-tour";
const PREFIX = "redcase.chrome-tour";

export function replayChromeTour(): void {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(REPLAY_EVENT));
}

function storageKey(): string {
  return `${PREFIX}.${getSession()?.user_ref ?? "anon"}`;
}

export function ChromeTour({ isFirmAdmin }: { isFirmAdmin: boolean }): ReactElement | null {
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState(0);
  const panelRef = useRef<HTMLDivElement>(null);
  const steps = [
    { title: "Start from Home", body: "Home is your calm morning brief: priorities, deadlines, recent work, and the shortcuts you use most." },
    { title: "Make the Workbench yours", body: "Workbench is where grounded analyses live. Use the rail sub-panel to move between SmartBrief, Red-Teamer, and your recent work." },
    { title: "Search both vaults", body: "Vault brings firm documents and Nigerian jurisprudence together, with access controls and citations kept visible." },
    { title: "Stay close to the firm", body: "Messenger, the task bar, and presence keep channels, chats, threads, pins, and contacts within reach." },
    isFirmAdmin
      ? { title: "Run the firm", body: "Firm Ops is your admin command centre for departments, seats, access, and the operational view of Aetoes Legal." }
      : { title: "Shape your workspace", body: "Use Customize home, appearance density, and the task bar to keep RedCase aligned with the way you practise." },
  ];

  useEffect(() => {
    const openIfNeeded = () => {
      if (!window.localStorage.getItem(storageKey())) {
        setStep(0);
        setOpen(true);
      }
    };
    openIfNeeded();
    const replay = () => { setStep(0); setOpen(true); };
    window.addEventListener(REPLAY_EVENT, replay);
    return () => window.removeEventListener(REPLAY_EVENT, replay);
  }, []);

  useEffect(() => {
    if (!open) return;
    panelRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === "Escape") finish(); };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open]);

  if (!open) return null;
  const current = steps[step]!;
  const finish = () => { window.localStorage.setItem(storageKey(), "1"); setOpen(false); };

  return <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-label={`${current.title} — RedCase tour`}>
    <div ref={panelRef} tabIndex={-1} className="w-full max-w-md rounded-2xl border border-gold/30 bg-surface p-6 shadow-elevated outline-none">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-2.5"><span className="flex size-9 items-center justify-center rounded-lg bg-gold/15 text-gold"><Compass className="size-5" /></span><span className="font-mono text-[10px] uppercase tracking-[0.28em] text-muted-foreground">Chrome tour · {step + 1} of {steps.length}</span></div>
        <button type="button" onClick={finish} aria-label="Skip tour" className="rounded-lg p-1.5 text-muted-foreground transition-all duration-200 hover:bg-border/60 hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/50"><X className="size-4" /></button>
      </div>
      <h2 className="mt-5 font-display text-xl font-semibold text-foreground">{current.title}</h2>
      <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{current.body}</p>
      <div className="mt-6 flex items-center justify-between gap-3"><div className="flex items-center gap-1.5">{steps.map((item, index) => <button type="button" key={item.title} onClick={() => setStep(index)} aria-label={`Go to tour step ${index + 1}`} className={`h-1.5 rounded-full transition-all duration-200 ${index === step ? "w-5 bg-gold" : "w-1.5 bg-steel/40 hover:bg-steel/60"}`} />)}</div><div className="flex items-center gap-2">{step > 0 && <button type="button" onClick={() => setStep((value) => value - 1)} className="inline-flex items-center gap-1 rounded-lg border border-border px-3 py-2 text-sm font-medium text-muted-foreground transition-all duration-200 hover:border-gold/50 hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/50"><ChevronLeft className="size-4" /> Back</button>}{step === steps.length - 1 ? <button type="button" onClick={finish} className="inline-flex items-center gap-1.5 rounded-lg bg-gold px-4 py-2 text-sm font-semibold text-background transition-all duration-200 hover:bg-gold/90 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/50"><Sparkles className="size-4" /> Got it</button> : <button type="button" onClick={() => setStep((value) => value + 1)} className="inline-flex items-center gap-1 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-all duration-200 hover:bg-primary/90 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/50">Next <ChevronRight className="size-4" /></button>}</div></div>
    </div>
  </div>;
}
