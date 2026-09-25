import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import {
  ArrowUpRight,
  FileText,
  Landmark,
  Loader2,
  Search,
  ShieldCheck,
  Vault as VaultIcon,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { useVaultDocuments, type VaultDocument } from "@/lib/api/vault";
import { apiGet } from "@/lib/api/client";

export const Route = createFileRoute("/_authed/vault")({
  component: VaultPage,
});

function VaultPage() {
  const [selected, setSelected] = useState<VaultDocument | null>(null);
  return (
    <AppShell eyebrow="DUAL VAULT · DOCUMENT SURFACES" title="Vault">
      <div className="mx-auto max-w-7xl space-y-7">
        <header className="max-w-3xl border-l-2 border-gold/70 pl-5 py-1">
          <p className="font-mono text-[10px] uppercase tracking-[0.24em] text-gold">
            Two libraries · separate permissions
          </p>
          <h2 className="mt-2 font-display text-3xl sm:text-4xl">
            Find the record behind the work.
          </h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            Public Nigerian jurisprudence and your firm’s Internal Briefs live
            side by side, never in the same access boundary.
          </p>
        </header>
        <div className="grid gap-5 lg:grid-cols-2">
          <VaultSurface
            type="juris"
            title="Juris OS"
            subtitle="Vault B · Nigerian public jurisprudence"
            icon={Landmark}
            onSelect={setSelected}
          />
          <VaultSurface
            type="firm"
            title="Internal Briefs"
            subtitle="Vault A · firm documents and granted matter files"
            icon={VaultIcon}
            onSelect={setSelected}
          />
        </div>
        {selected && (
          <DocumentDetail
            document={selected}
            onClose={() => setSelected(null)}
          />
        )}
      </div>
    </AppShell>
  );
}

function VaultSurface({
  type,
  title,
  subtitle,
  icon: Icon,
  onSelect,
}: {
  type: "firm" | "juris";
  title: string;
  subtitle: string;
  icon: typeof Landmark;
  onSelect: (doc: VaultDocument) => void;
}) {
  const query = useVaultDocuments(type);
  const documents = query.data?.documents ?? [];
  return (
    <section className="panel overflow-hidden">
      <div className="flex items-center gap-3 border-b border-border px-5 py-4">
        <span className="grid size-9 place-items-center rounded-lg bg-gold/10 text-gold">
          <Icon className="size-4" />
        </span>
        <div className="min-w-0">
          <h3 className="font-display text-xl">{title}</h3>
          <p className="text-xs text-muted-foreground">{subtitle}</p>
        </div>
        <span className="ml-auto rounded-full border border-border px-2 py-1 font-mono text-[9px] uppercase tracking-widest text-muted-foreground">
          {type === "juris" ? "Public" : "Restricted"}
        </span>
      </div>
      {query.isPending ? (
        <div className="flex items-center gap-2 p-6 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" />
          Loading visible files…
        </div>
      ) : query.isError ? (
        <p role="alert" className="p-6 text-sm text-destructive">
          Could not load this vault. Check your connection and try again.
        </p>
      ) : documents.length === 0 ? (
        <div className="px-6 py-10 text-center">
          <Search className="mx-auto size-5 text-muted-foreground" />
          <p className="mt-3 text-sm font-medium">No visible files yet</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Files appear here when they are indexed and your access allows it.
          </p>
        </div>
      ) : (
        <ul className="divide-y divide-border/70">
          {documents.map((doc) => (
            <li key={doc.document_id}>
              <button
                type="button"
                onClick={() => onSelect(doc)}
                className="group flex w-full items-start gap-3 px-5 py-4 text-left transition-all duration-200 hover:bg-sidebar-accent/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-gold"
              >
                <FileText className="mt-0.5 size-4 shrink-0 text-steel" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium group-hover:text-gold">
                    {doc.title || "Untitled document"}
                  </span>
                  <span className="mt-1 block truncate font-mono text-[10px] text-muted-foreground">
                    {doc.citation || doc.doc_type || "Firm record"}
                  </span>
                </span>
                <ArrowUpRight className="size-4 shrink-0 text-muted-foreground transition-all duration-200 group-hover:text-gold" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function DocumentDetail({
  document,
  onClose,
}: {
  document: VaultDocument;
  onClose: () => void;
}) {
  const [content, setContent] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  async function open() {
    setLoading(true);
    setError("");
    try {
      const result = await apiGet<{
        chunks?: { text: string }[];
      }>(`/v1/documents/${document.document_id}`);
      setContent(
        result.chunks?.map((chunk) => chunk.text).join("\n\n") ||
          "Document metadata loaded; no readable text was returned.",
      );
    } catch {
      setError(
        "This document could not be opened. It may no longer be available to your account.",
      );
    } finally {
      setLoading(false);
    }
  }
  return (
    <section className="panel p-5 sm:p-7" aria-live="polite">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-widest text-gold">
            Document surface
          </p>
          <h3 className="mt-1 font-display text-2xl">
            {document.title || "Untitled document"}
          </h3>
          <p className="mt-1 font-mono text-xs text-muted-foreground">
            {document.citation || document.classification || "Indexed record"}
          </p>
        </div>
        <button
          onClick={onClose}
          className="rounded-md border border-border px-3 py-1.5 text-xs transition-all duration-200 hover:bg-sidebar-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold"
        >
          Close
        </button>
      </div>
      <div className="mt-5 flex items-center gap-2 rounded-lg border border-success/20 bg-success/5 p-3 text-xs text-muted-foreground">
        <ShieldCheck className="size-4 text-success" />
        Access is enforced by database row-level policies.
      </div>
      {content ? (
        <pre className="mt-4 max-h-[32rem] overflow-auto whitespace-pre-wrap rounded-lg bg-background p-4 text-sm leading-6">
          {content}
        </pre>
      ) : (
        <button
          onClick={open}
          disabled={loading}
          className="mt-5 inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm text-primary-foreground transition-all duration-200 hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold disabled:opacity-60"
        >
          {loading ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <FileText className="size-4" />
          )}
          Open document
        </button>
      )}
      {error && (
        <p role="alert" className="mt-3 text-sm text-destructive">
          {error}
        </p>
      )}
    </section>
  );
}
