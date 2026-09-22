import { useEffect, useRef, useState } from "react";
import { Send, AlertCircle, X, Headset } from "lucide-react";
import knowledge from "@/data/receptionist-knowledge.json";

type Message = { role: "user" | "assistant"; text: string };

const ESCALATE = "I don't want to guess — let me connect you.";
const WELCOME =
  "Hello — I'm RedCase's receptionist. Ask me about the platform, security, or what's shipped vs. on the roadmap.";

function normalize(s: string) {
  return s.toLowerCase().replace(/[^a-z0-9 ]/g, " ").replace(/\s+/g, " ").trim();
}

// Deterministic, purely local classifier over the curated knowledge file.
// No network call, nothing persisted — visitor input lives in browser state only.
function answer(question: string): string {
  const q = normalize(question);

  // Pricing guard — we never discuss figures, only escalate.
  if (/price|pric|cost|fee|subscription|how much|costing|package/.test(q)) {
    return "Talk to us.";
  }

  const faq = knowledge.faq.find((f) => {
    const words = normalize(f.q).split(" ").filter((w) => w.length > 3);
    return words.filter((w) => q.includes(w)).length >= 2;
  });
  if (faq) return faq.a;

  const cap = knowledge.capabilities;
  const hits: string[] = [];

  if (/train|data used|your model|model/.test(q)) hits.push("No. Every AI call is zero-retention — client conversations never touch a model provider's logs, and nothing you write is used to train anyone's model.");
  if (/citation|page-pin|pinned|verify|source/.test(q)) hits.push("Every legal proposition carries a citation to a specific page and paragraph of a stored source you can open and verify. If RedCase can't verify the authority in the vaults, it refuses to answer rather than guess.");
  if (/encrypt|aes|key|control access|permission|secure|security/.test(q)) hits.push("Documents are encrypted with AES-256, per-document keys your firm controls. Permission is scoped per user by clearance and explicit grants.");
  if (/court|jurisprud|principal|supreme|appeal|nicn|which courts/.test(q)) hits.push(cap.dual_vault.label + ". Vault B indexes Supreme Court, Court of Appeal, Federal and State High Courts, and the NICN, cited to page and paragraph by ratio decidendi.");
  if (/legal assistant|assistant learn|learn how i work/.test(q)) hits.push("One assistant per lawyer, bound to a Workbench. It learns your preferences from the work you do in your workbench — and converses only there, under your permissions.");
  if (/vault/.test(q)) hits.push(cap.dual_vault.label);
  if (/search|semantic/.test(q)) hits.push(cap.vault_search.label);
  if (/workbench|analy|analysis|brief|smartbrief|red.team|summons|contract/.test(q)) hits.push(cap.workbench_analysis.label);
  if (/deadline|tracker|deadlines/.test(q)) hits.push("Deadline tracker — " + cap.deadline_tracker.status.replace(/-/g, " ") + ".");
  if (/client portal|portal/.test(q)) hits.push(cap.client_portal.label + " — " + cap.client_portal.status + ".");
  if (/slack/.test(q)) hits.push(cap.slack_connector.label + " — " + cap.slack_connector.status + ".");
  if (/time|invoice|invoic|conflict check|ops|operation|practice/.test(q)) hits.push(cap.practice_ops.label + ".");

  if (hits.length) return hits.join(" ");

  return ESCALATE;
}

const SUGGESTIONS = [
  "Is my data used to train your models?",
  "Which Nigerian courts are covered?",
  "What does page-pinned citations mean?",
  "Is the deadline tracker available?",
  "Is there a client portal?",
  "What's your price?",
];

export function Receptionist() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([{ role: "assistant", text: WELCOME }]);
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  const last = messages[messages.length - 1];
  const showingEscalate =
    last?.role === "assistant" && last?.text === ESCALATE;

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, open]);

  const submit = (raw: string) => {
    const text = raw.trim();
    if (!text) return;
    setMessages((m) => [
      ...m,
      { role: "user", text },
      { role: "assistant", text: answer(text) },
    ]);
    setInput("");
  };

  return (
    <>
      {/* Launcher button */}
      <button
        type="button"
        onClick={ () => setOpen((v) => !v) }
        aria-expanded={ open }
        aria-label={ open ? "Close receptionist chat" : "Open receptionist chat" }
        className="fixed bottom-5 right-5 z-50 inline-flex size-14 items-center justify-center rounded-full bg-gradient-to-br from-primary to-[#8f0013] text-primary-foreground shadow-elevated ring-1 ring-white/10 transition-all duration-200 hover:scale-105 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold"
      >
        <Headset className="size-6" />
        <span className="absolute -right-0.5 -top-0.5 flex size-3">
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-[#3ecf8e] opacity-75" />
          <span className="relative inline-flex size-3 rounded-full bg-[#3ecf8e]" />
        </span>
      </button>

      { open && (
        <aside className="fixed bottom-24 right-5 z-50 flex w-[min(92vw,24rem)] flex-col overflow-hidden rounded-2xl border border-border bg-surface shadow-elevated">
          {/* Header */}
          <div className="flex items-center gap-3 border-b border-border/60 bg-background/40 px-4 py-3">
            <div className="relative">
              <div className="flex size-10 items-center justify-center rounded-full bg-gradient-to-br from-primary to-[#8f0013] text-primary-foreground ring-1 ring-white/10">
                <Headset className="size-5" />
              </div>
              <span className="absolute -bottom-0.5 -right-0.5 size-3 rounded-full bg-[#3ecf8e] ring-2 ring-surface" />
            </div>
            <div className="flex-1">
              <p className="text-sm font-semibold text-foreground">RedCase Receptionist</p>
              <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                Curated knowledge only
              </p>
            </div>
            <button
              type="button"
              onClick={ () => setOpen(false) }
              aria-label="Close chat"
              className="inline-flex size-8 items-center justify-center rounded-lg text-muted-foreground transition-colors duration-200 hover:bg-muted hover:text-foreground"
            >
              <X className="size-4" />
            </button>
          </div>

          {/* Thread */}
          <div ref={ scrollRef } className="max-h-80 flex-1 space-y-3 overflow-y-auto px-4 py-4">
            { messages.map((msg, i) => (
              <div
                key={ i }
                className={ `flex ${ msg.role === "user" ? "justify-end" : "justify-start" }` }
              >
                <div
                  className={ `max-w-[85%] rounded-xl px-4 py-3 text-sm leading-relaxed ${ msg.role === "user"
                    ? "bg-primary text-primary-foreground"
                    : "border border-border bg-background/50 text-foreground/90" }` }
                >
                  { msg.text }
                  { msg.role === "assistant" && showingEscalate && (
                    <div className="mt-3">
                      <a
                        href="/onboarding"
                        className="inline-flex items-center justify-center rounded-lg border border-gold/40 px-4 py-2 text-sm font-semibold text-foreground transition-all duration-200 hover:bg-gold/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold"
                      >
                        Talk to us
                      </a>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>

          { showingEscalate && (
            <div className="flex items-center gap-2 border-t border-border/60 bg-warning/10 px-4 py-2.5 text-xs text-warning">
              <AlertCircle className="size-3.5 shrink-0" />
              That's outside my knowledge — I'd rather not guess. A real person will take it from here.
            </div>
          )}

          {/* Composer */}
          <div className="border-t border-border/60 p-3">
            <div className="flex flex-wrap gap-2 px-1 pb-2">
              { SUGGESTIONS.map((s) => (
                <button
                  key={ s }
                  type="button"
                  onClick={ () => submit(s) }
                  className="rounded-full border border-border bg-background/40 px-3 py-1 text-xs text-muted-foreground transition-colors duration-200 hover:border-gold/40 hover:text-foreground"
                >
                  { s }
                </button>
              ))}
            </div>
            <form
              onSubmit={ (e) => { e.preventDefault(); submit(input); } }
              className="flex items-center gap-2"
            >
              <input
                value={ input }
                onChange={ (e) => setInput(e.target.value) }
                placeholder="Ask about RedCase…"
                className="h-11 flex-1 rounded-lg border border-border bg-background px-4 text-sm text-foreground placeholder:text-muted-foreground focus:border-gold/50 focus:outline-none focus:ring-2 focus:ring-gold/30"
                aria-label="Ask the receptionist"
              />
              <button
                type="submit"
                className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-primary px-4 text-sm font-semibold text-primary-foreground transition-all duration-200 hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold"
                aria-label="Send"
              >
                <Send className="size-4" />
              </button>
            </form>
            <p className="mt-2 px-1 text-[11px] text-muted-foreground/70">
              Nothing you type is stored — this chat is ephemeral and makes no network calls.
            </p>
          </div>
        </aside>
      )}
    </>
  );
}
