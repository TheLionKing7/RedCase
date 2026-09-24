import { FormEvent, useState } from "react";
import { Bot, Loader2, MessageSquarePlus, Send, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { sendAssistantMessage, useCreateThread, useThread, useThreads } from "@/lib/api/collaboration";

export function AssistantDock({ open, onClose }: { open: boolean; onClose: () => void }) {
  const threads = useThreads();
  const create = useCreateThread();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [reply, setReply] = useState<string>();
  const [sending, setSending] = useState(false);
  const activeId = selectedId ?? threads.data?.[0]?.thread_id;
  const selectedThread = useThread(activeId ?? "");

  if (!open) return null;
  const activeThread = selectedThread.data;
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const value = message.trim();
    if (!value || !activeId || sending) return;
    setSending(true);
    try { setReply(await sendAssistantMessage(activeId, value)); setMessage(""); } finally { setSending(false); }
  };
  const startThread = () => create.mutate("Assistant dock", { onSuccess: (thread) => setSelectedId(thread.thread_id) });

  return <aside className="fixed inset-y-0 right-0 z-[70] flex w-full max-w-md flex-col border-l border-border bg-sidebar shadow-2xl" aria-label="Assistant dock">
    <header className="flex items-center justify-between border-b border-border px-5 py-4"><div className="flex items-center gap-2.5"><span className="flex size-9 items-center justify-center rounded-lg bg-gold/15 text-gold"><Bot className="size-5" /></span><div><h2 className="text-sm font-semibold">Assistant</h2><p className="text-[11px] text-muted-foreground">Grounded in your permitted work</p></div></div><button type="button" onClick={onClose} aria-label="Close Assistant dock" className="rounded-lg p-2 text-muted-foreground transition-all duration-200 hover:bg-sidebar-accent hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-gold"><X className="size-4" /></button></header>
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4">
      <div className="flex items-center justify-between"><span className="font-mono text-[10px] uppercase tracking-[0.22em] text-steel">Your threads</span><Button type="button" variant="outline" size="sm" onClick={startThread} disabled={create.isPending}><MessageSquarePlus className="mr-1.5 size-3.5" />{create.isPending ? "Creating…" : "New"}</Button></div>
      {threads.isLoading ? <div className="flex items-center gap-2 rounded-xl border border-dashed border-border p-4 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" /> Loading threads…</div> : threads.isError ? <p role="alert" className="rounded-xl border border-destructive/40 p-4 text-sm text-destructive">Assistant threads are unavailable. Check the API connection and retry.</p> : threads.data?.length ? <div className="flex gap-2 overflow-x-auto pb-1">{threads.data.map((thread) => <button type="button" key={thread.thread_id} onClick={() => { setSelectedId(thread.thread_id); setReply(undefined); }} className={`shrink-0 rounded-lg border px-3 py-2 text-left text-xs transition-all duration-200 hover:border-gold/50 ${activeId === thread.thread_id ? "border-gold/50 bg-gold/10 text-gold" : "border-border text-muted-foreground"}`}>{thread.title}</button>)}</div> : <div className="rounded-xl border border-dashed border-border p-5 text-center text-sm text-muted-foreground">No assistant threads yet. Start a grounded conversation.</div>}
      {activeId && <section className="space-y-3">{selectedThread.isLoading ? <div className="text-sm text-muted-foreground">Loading conversation…</div> : activeThread?.turns.map((turn) => <article key={turn.id} className={`rounded-xl border p-3 ${turn.role === "ASSISTANT" ? "border-gold/30 bg-gold/5" : "border-border bg-background"}`}><div className="font-mono text-[10px] uppercase tracking-widest text-steel">{turn.role}</div><p className="mt-1 whitespace-pre-wrap text-sm">{turn.content}</p></article>)}{reply && <article className="rounded-xl border border-gold/30 bg-gold/5 p-3"><div className="font-mono text-[10px] uppercase tracking-widest text-steel">ASSISTANT</div><p className="mt-1 whitespace-pre-wrap text-sm">{reply}</p></article>}</section>}
    </div>
    <form onSubmit={submit} className="flex gap-2 border-t border-border p-4"><input value={message} onChange={(event) => setMessage(event.target.value)} placeholder={activeId ? "Ask the grounded assistant…" : "Create a thread to begin"} aria-label="Assistant message" disabled={!activeId || sending} className="min-w-0 flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none transition-all duration-200 focus-visible:ring-2 focus-visible:ring-gold" /><Button type="submit" disabled={!activeId || sending || !message.trim()} aria-label="Send assistant message"><Send className="size-4" />{sending ? "Thinking…" : "Send"}</Button></form>
  </aside>;
}
