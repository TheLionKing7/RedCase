import { FormEvent, useEffect, useState } from "react";
import {
  Bot,
  Loader2,
  MessageSquarePlus,
  Send,
  ThumbsDown,
  ThumbsUp,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  sendAssistantMessage,
  useCreateThread,
  useThread,
  useThreads,
  submitAssistantFeedback,
} from "@/lib/api/collaboration";
import type { AssistantContext } from "@/lib/api/assistantContext";

export function AssistantDock({
  open,
  onClose,
  context,
  persistent = false,
  initialMessage = "",
  onMessageChange,
}: {
  open: boolean;
  onClose: () => void;
  context: AssistantContext;
  persistent?: boolean;
  initialMessage?: string;
  onMessageChange?: () => void;
}) {
  const threads = useThreads();
  const create = useCreateThread();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [reply, setReply] = useState<string>();
  const [sending, setSending] = useState(false);
  const [feedback, setFeedback] = useState<Record<string, "UP" | "DOWN">>({});
  const [feedbackMessage, setFeedbackMessage] = useState("");
  const activeId = selectedId ?? threads.data?.[0]?.thread_id;
  const selectedThread = useThread(activeId ?? "");

  useEffect(() => {
    if (!initialMessage) return;
    setMessage(initialMessage);
    onMessageChange?.();
  }, [initialMessage, onMessageChange]);

  if (!open && !persistent) return null;
  const activeThread = selectedThread.data;
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const value = message.trim();
    if (!value || !activeId || sending) return;
    setSending(true);
    try {
      setReply(await sendAssistantMessage(activeId, value, context));
      await selectedThread.refetch();
      setMessage("");
    } finally {
      setSending(false);
    }
  };
  const startThread = () =>
    create.mutate("Assistant dock", {
      onSuccess: (thread) => setSelectedId(thread.thread_id),
    });
  const contextLabel = `${context.bench}${context.reference ? ` · ${context.reference.label}` : ""}`;

  return (
    <aside
      className={
        persistent
          ? `fixed bottom-[3.75rem] right-0 z-[25] flex w-full flex-col border-t border-border bg-sidebar/95 shadow-xl backdrop-blur-xl transition-all duration-200 lg:left-[20.5rem] ${open ? "h-[min(28rem,65vh)]" : "h-0 overflow-hidden border-t-0"}`
          : "fixed inset-y-0 right-0 z-[70] flex w-full max-w-md flex-col border-l border-border bg-sidebar shadow-2xl"
      }
      aria-label="Assistant dock"
    >
      {(!persistent || open) && (
        <header className="flex items-center justify-between border-b border-border px-4 py-2.5">
          <div className="flex min-w-0 items-center gap-2.5">
            <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-gold/15 text-gold">
              <Bot className="size-4" />
            </span>
            <div className="min-w-0">
              <h2 className="text-xs font-semibold">Personal Assistant</h2>
              <p className="truncate text-[10px] text-muted-foreground">
                {contextLabel} · grounded in your permitted work
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1">
            {persistent && (
              <button
                type="button"
                onClick={onClose}
                aria-expanded={open}
                aria-label="Collapse Assistant panel"
                className="rounded-lg px-2 py-1 text-[10px] text-muted-foreground transition-all duration-200 hover:bg-sidebar-accent"
              >
                Collapse
              </button>
            )}
            {!persistent && (
              <button
                type="button"
                onClick={onClose}
                aria-label="Close Assistant dock"
                className="rounded-lg p-2 text-muted-foreground transition-all duration-200 hover:bg-sidebar-accent hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-gold"
              >
                <X className="size-4" />
              </button>
            )}
          </div>
        </header>
      )}
      {(open || !persistent) && (
        <>
          <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4">
            <div className="flex items-center justify-between">
              <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-steel">
                Your threads
              </span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={startThread}
                disabled={create.isPending}
              >
                <MessageSquarePlus className="mr-1.5 size-3.5" />
                {create.isPending ? "Creating…" : "New"}
              </Button>
            </div>
            {threads.isLoading ? (
              <div className="flex items-center gap-2 rounded-xl border border-dashed border-border p-4 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" /> Loading threads…
              </div>
            ) : threads.isError ? (
              <p
                role="alert"
                className="rounded-xl border border-destructive/40 p-4 text-sm text-destructive"
              >
                Assistant threads are unavailable. Check the API connection and
                retry.
              </p>
            ) : threads.data?.length ? (
              <div className="flex gap-2 overflow-x-auto pb-1">
                {threads.data.map((thread) => (
                  <button
                    type="button"
                    key={thread.thread_id}
                    onClick={() => {
                      setSelectedId(thread.thread_id);
                      setReply(undefined);
                    }}
                    className={`shrink-0 rounded-lg border px-3 py-2 text-left text-xs transition-all duration-200 hover:border-gold/50 ${activeId === thread.thread_id ? "border-gold/50 bg-gold/10 text-gold" : "border-border text-muted-foreground"}`}
                  >
                    {thread.title}
                  </button>
                ))}
              </div>
            ) : (
              <div className="rounded-xl border border-dashed border-border p-5 text-center text-sm text-muted-foreground">
                No assistant threads yet. Start a grounded conversation.
              </div>
            )}
            {activeId && (
              <section className="space-y-3">
                {selectedThread.isLoading ? (
                  <div className="text-sm text-muted-foreground">
                    Loading conversation…
                  </div>
                ) : (
                  activeThread?.turns.map((turn) => (
                    <article
                      key={turn.id}
                      className={`rounded-xl border p-3 ${turn.role === "ASSISTANT" ? "border-gold/30 bg-gold/5" : "border-border bg-background"}`}
                    >
                      <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-widest text-steel">
                        {turn.role}
                        {turn.source_bench && (
                          <span className="rounded bg-gold/10 px-1.5 py-0.5 text-gold">
                            {turn.source_bench}
                            {turn.source_label ? ` · ${turn.source_label}` : ""}
                          </span>
                        )}
                      </div>
                      <p className="mt-1 whitespace-pre-wrap text-sm">
                        {turn.content}
                      </p>
                      {turn.role === "ASSISTANT" && (
                        <div className="mt-3 flex items-center gap-2 border-t border-border/60 pt-2">
                          <span className="mr-auto text-[10px] text-muted-foreground">
                            Was this helpful?
                          </span>
                          {(["UP", "DOWN"] as const).map((rating) => (
                            <button
                              key={rating}
                              type="button"
                              aria-label={
                                rating === "UP"
                                  ? "Helpful answer"
                                  : "Unhelpful answer"
                              }
                              aria-pressed={feedback[turn.id] === rating}
                              disabled={Boolean(feedback[turn.id])}
                              onClick={async () => {
                                if (!activeId || feedback[turn.id]) return;
                                try {
                                  await submitAssistantFeedback(activeId, {
                                    message_id: turn.id,
                                    rating,
                                  });
                                  setFeedback((current) => ({
                                    ...current,
                                    [turn.id]: rating,
                                  }));
                                  setFeedbackMessage(
                                    "Thanks — your feedback was saved.",
                                  );
                                } catch {
                                  setFeedbackMessage(
                                    "Feedback could not be saved. Please retry.",
                                  );
                                }
                              }}
                              className={`rounded-md p-1.5 transition-all duration-200 hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold disabled:cursor-default ${feedback[turn.id] === rating ? "text-gold" : "text-muted-foreground"}`}
                            >
                              {rating === "UP" ? (
                                <ThumbsUp className="size-3.5" />
                              ) : (
                                <ThumbsDown className="size-3.5" />
                              )}
                            </button>
                          ))}
                        </div>
                      )}
                    </article>
                  ))
                )}
                {feedbackMessage && (
                  <p role="status" className="text-xs text-muted-foreground">
                    {feedbackMessage}
                  </p>
                )}
                {reply && (
                  <article className="rounded-xl border border-gold/30 bg-gold/5 p-3">
                    <div className="font-mono text-[10px] uppercase tracking-widest text-steel">
                      ASSISTANT
                    </div>
                    <p className="mt-1 whitespace-pre-wrap text-sm">{reply}</p>
                  </article>
                )}
              </section>
            )}
          </div>
          <form
            onSubmit={submit}
            className="flex gap-2 border-t border-border p-3"
          >
            <input
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              placeholder={
                activeId
                  ? `Ask about ${contextLabel}…`
                  : "Create a thread to begin"
              }
              aria-label="Assistant message"
              disabled={!activeId || sending}
              className="min-w-0 flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none transition-all duration-200 focus-visible:ring-2 focus-visible:ring-gold"
            />
            <Button
              type="submit"
              disabled={!activeId || sending || !message.trim()}
              aria-label="Send assistant message"
            >
              <Send className="size-4" />
              {sending ? "Thinking…" : "Send"}
            </Button>
          </form>
        </>
      )}
    </aside>
  );
}
