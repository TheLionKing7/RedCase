import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import {
  Check,
  Clock3,
  FileKey,
  Loader2,
  ShieldCheck,
  Undo2,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import {
  useAccessGrants,
  useAccessRequests,
  useCreateAccessRequest,
  useRelinquishGrant,
} from "@/lib/api/access";

export const Route = createFileRoute("/_authed/access-requests")({
  component: AccessRequestsPage,
});

function AccessRequestsPage() {
  const requests = useAccessRequests();
  const grants = useAccessGrants();
  const create = useCreateAccessRequest();
  const relinquish = useRelinquishGrant();
  const [briefName, setBriefName] = useState("");
  const [note, setNote] = useState("");
  const [notice, setNotice] = useState("");
  const onSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!briefName.trim() || create.isPending) return;
    create.mutate(
      {
        brief_name: briefName.trim(),
        reason: note.trim() || null,
        grant_level: "READ",
        grantee_ref: null,
      },
      {
        onSuccess: () => {
          setBriefName("");
          setNote("");
          setNotice("Access request sent for review.");
        },
        onError: () =>
          setNotice(
            "Request was not sent. Check the brief name and try again.",
          ),
      },
    );
  };
  const activeGrants =
    grants.data?.grants.filter(
      (grant) =>
        !grant.relinquished_at &&
        (!grant.expires_at || new Date(grant.expires_at) > new Date()),
    ) ?? [];
  const ownRequests = requests.data?.requests ?? [];
  return (
    <AppShell eyebrow="VAULT · CONTROLLED ACCESS" title="Access & Request">
      <div className="mx-auto max-w-6xl space-y-7">
        <header className="max-w-3xl border-l-2 border-gold/70 pl-5 py-1">
          <p className="font-mono text-[10px] uppercase tracking-[0.24em] text-gold">
            Privilege stays in your hands
          </p>
          <h2 className="mt-2 font-display text-3xl sm:text-4xl">
            Request what you need. Release it when you’re done.
          </h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            Every request is reviewed by an authorized partner. Access can be
            time-limited and relinquished at any time.
          </p>
        </header>
        {notice && (
          <p
            role="status"
            className="rounded-lg border border-gold/25 bg-gold/5 p-3 text-sm"
          >
            {notice}
          </p>
        )}
        <div className="grid gap-5 lg:grid-cols-[0.85fr_1.15fr]">
          <section className="panel h-fit p-5 sm:p-6">
            <div className="flex items-center gap-3">
              <span className="grid size-9 place-items-center rounded-lg bg-gold/10 text-gold">
                <FileKey className="size-4" />
              </span>
              <div>
                <h3 className="font-semibold">Request a brief</h3>
                <p className="text-xs text-muted-foreground">
                  For the current signed-in user
                </p>
              </div>
            </div>
            <p className="mt-4 text-sm leading-6 text-muted-foreground">
              Name the Internal Briefs file you need. An optional note helps the
              reviewing partner understand the request.
            </p>
            <form onSubmit={onSubmit} className="mt-5 space-y-4">
              <label className="block">
                <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                  Brief name
                </span>
                <input
                  required
                  maxLength={300}
                  value={briefName}
                  onChange={(e) => setBriefName(e.target.value)}
                  placeholder="Exact title from Internal Briefs"
                  className="mt-1.5 w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-gold"
                />
              </label>
              <label className="block">
                <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                  Note · optional
                </span>
                <textarea
                  maxLength={1000}
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="A short reason for this access"
                  className="mt-1.5 min-h-24 w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-gold"
                />
              </label>
              <button
                type="submit"
                disabled={create.isPending}
                className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground transition-all duration-200 hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold disabled:opacity-60"
              >
                {create.isPending ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Check className="size-4" />
                )}
                {create.isPending ? "Sending…" : "Send request"}
              </button>
            </form>
            <div className="mt-4 flex items-start gap-2 rounded-lg border border-border/70 p-3 text-xs leading-5 text-muted-foreground">
              <ShieldCheck className="mt-0.5 size-4 shrink-0 text-gold" />A
              request itself never grants access; the document remains hidden
              until approved.
            </div>
          </section>
          <section className="panel overflow-hidden">
            <div className="flex items-center justify-between border-b border-border px-5 py-4">
              <div>
                <h3 className="font-semibold">Granted access</h3>
                <p className="mt-1 text-xs text-muted-foreground">
                  Active files and their access windows
                </p>
              </div>
              <span className="rounded-full border border-border px-2 py-1 font-mono text-[10px]">
                {activeGrants.length} active
              </span>
            </div>
            {grants.isPending ? (
              <Loading />
            ) : grants.isError ? (
              <ErrorState text="Could not load granted files. Retry after checking your connection." />
            ) : activeGrants.length === 0 ? (
              <Empty text="No active grants. Approved briefs will appear here." />
            ) : (
              <ul className="divide-y divide-border/70">
                {activeGrants.map((grant) => (
                  <li
                    key={grant.id}
                    className="flex flex-wrap items-center justify-between gap-3 px-5 py-4"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">
                        {grant.brief_name ||
                          `Brief ${grant.document_id.slice(0, 8)}`}
                      </p>
                      <p className="mt-1 flex items-center gap-1.5 font-mono text-[10px] text-muted-foreground">
                        <Clock3 className="size-3" />
                        From {dateLabel(grant.granted_at)} · To{" "}
                        {grant.expires_at
                          ? dateLabel(grant.expires_at)
                          : "No expiry"}
                      </p>
                    </div>
                    <button
                      type="button"
                      disabled={relinquish.isPending}
                      onClick={() =>
                        relinquish.mutate(grant.id, {
                          onSuccess: () => setNotice("Access relinquished."),
                          onError: () =>
                            setNotice(
                              "Access could not be relinquished. Retry or contact a partner.",
                            ),
                        })
                      }
                      className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs transition-all duration-200 hover:border-destructive/50 hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold disabled:opacity-60"
                    >
                      <Undo2 className="size-3.5" />
                      Relinquish
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
        <section className="panel p-5 sm:p-6">
          <h3 className="font-semibold">Your requests</h3>
          <p className="mt-1 text-xs text-muted-foreground">
            Requests you have submitted and their review status
          </p>
          {requests.isPending ? (
            <Loading />
          ) : requests.isError ? (
            <ErrorState text="Could not load requests. Refresh to try again." />
          ) : ownRequests.length === 0 ? (
            <Empty text="You haven’t requested any briefs yet." />
          ) : (
            <ul className="mt-4 divide-y divide-border/70">
              {ownRequests.map((request) => (
                <li
                  key={request.id}
                  className="flex flex-wrap items-center justify-between gap-3 py-3"
                >
                  <div>
                    <p className="text-sm font-medium">
                      {request.brief_name ||
                        `Brief ${(request.document_id ?? "unknown").slice(0, 8)}`}
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {request.reason || "No note added"}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span
                      className={`rounded-full px-2.5 py-1 font-mono text-[10px] uppercase ${request.status === "APPROVED" ? "bg-success/10 text-success" : request.status === "DENIED" ? "bg-destructive/10 text-destructive" : "bg-gold/10 text-gold"}`}
                    >
                      {request.status.toLowerCase()}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </AppShell>
  );
}

function dateLabel(date: string) {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(
    new Date(date),
  );
}
function Loading() {
  return (
    <div className="flex items-center gap-2 p-5 text-sm text-muted-foreground">
      <Loader2 className="size-4 animate-spin" />
      Loading…
    </div>
  );
}
function ErrorState({ text }: { text: string }) {
  return (
    <p role="alert" className="p-5 text-sm text-destructive">
      {text}
    </p>
  );
}
function Empty({ text }: { text: string }) {
  return (
    <p className="p-8 text-center text-sm text-muted-foreground">{text}</p>
  );
}
