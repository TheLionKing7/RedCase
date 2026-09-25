import { createFileRoute } from "@tanstack/react-router";
import { CheckCircle2, Loader2, Settings2 } from "lucide-react";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { PERSONA_TONES, usePersona, useSavePersona, type TonePreset } from "@/lib/api/persona";

export const Route = createFileRoute("/_authed/settings")({ component: SettingsPage });

function SettingsPage() {
  const persona = usePersona();
  const save = useSavePersona();
  const [name, setName] = useState("Assistant");
  const [tone, setTone] = useState<TonePreset>("PROFESSIONAL");
  const [rules, setRules] = useState("");
  const [notice, setNotice] = useState("");
  useEffect(() => {
    if (!persona.data) return;
    setName(persona.data.agent_name || "Assistant");
    setTone(persona.data.tone_preset || "PROFESSIONAL");
    setRules(persona.data.rules_of_engagement || "");
  }, [persona.data]);

  return <AppShell eyebrow="PERSONAL SETTINGS" title="Settings"><div className="mx-auto max-w-5xl space-y-6">
    <section><p className="font-mono text-[10px] uppercase tracking-[0.28em] text-steel">Assistant Persona</p><h2 className="mt-1 font-display text-2xl">How your assistant communicates</h2><p className="mt-2 text-sm text-muted-foreground">This preference belongs to you. It shapes tone, never the sources the assistant may cite.</p></section>
    {notice && <p role="status" className="rounded-lg border border-success/40 bg-success/10 p-3 text-sm text-success">{notice}</p>}
    {persona.isPending ? <div className="panel flex items-center gap-2 p-5 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" />Loading preferences…</div> : <form className="panel space-y-5 p-5 sm:p-7" onSubmit={(event) => {
      event.preventDefault();
      save.mutate({ agent_name: name.trim() || "Assistant", tone_preset: tone, rules_of_engagement: rules.trim() || null }, {
        onSuccess: () => setNotice("Assistant persona saved."),
        onError: () => setNotice("Could not save your persona. Check the API connection and retry."),
      });
    }}>
      <label className="block"><span className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">Assistant name</span><input value={name} onChange={(event) => setName(event.target.value)} className="mt-1.5 w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm" maxLength={120} /></label>
      <label className="block"><span className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">Tone</span><select value={tone} onChange={(event) => setTone(event.target.value as TonePreset)} className="mt-1.5 w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm">{PERSONA_TONES.map((option) => <option key={option} value={option}>{option.toLowerCase()}</option>)}</select></label>
      <label className="block"><span className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">Working preferences</span><textarea value={rules} onChange={(event) => setRules(event.target.value)} className="mt-1.5 min-h-32 w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm" maxLength={4000} placeholder="How should your assistant structure its work?" /></label>
      <div className="flex items-start gap-2 rounded-lg border border-border/60 bg-background/50 p-3 text-xs text-muted-foreground"><Settings2 className="mt-0.5 size-4 shrink-0 text-gold" />Grounding and citation safeguards cannot be changed by persona preferences.</div>
      <button type="submit" disabled={save.isPending} className="inline-flex items-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground transition-all duration-200 hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold disabled:opacity-60">{save.isPending ? <Loader2 className="size-4 animate-spin" /> : <CheckCircle2 className="size-4" />}{save.isPending ? "Saving…" : "Save persona"}</button>
    </form>}
  </div></AppShell>;
}