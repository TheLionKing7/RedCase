import { Link } from "@tanstack/react-router";
import {
  Archive,
  ArrowDownLeft,
  ArrowLeft,
  ArrowUpRight,
  FilePlus2,
  Hash,
  MessageSquare,
  Paperclip,
  Plus,
  Send,
  Users,
} from "lucide-react";
import { type FormEvent, useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import {
  useAddChannelParticipants,
  useChannels,
  useCreateDirectChannel,
  useCreatePin,
  useCreateThread,
  useDeletePin,
  useMarkChannelRead,
  useMembers,
  useMessages,
  usePins,
  useSendMessage,
  useThreads,
} from "@/lib/api/collaboration";

type Section =
  "pins" | "chats" | "channels" | "threads" | "contacts" | "archived";
type ChannelKind = "matter" | "direct";
type DiscussReference = { analysisId: string; label: string };

const RESOURCE_TYPES = [
  "CHANNEL",
  "MESSAGE",
  "THREAD",
  "ANALYSIS",
  "MATTER",
] as const;
const inputClass =
  "min-w-0 rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none transition-all duration-200 focus-visible:ring-2 focus-visible:ring-gold";

function State({ text, error = false }: { text: string; error?: boolean }) {
  return (
    <div
      role={error ? "alert" : "status"}
      className={`rounded-xl border border-dashed p-8 text-center text-sm ${error ? "border-destructive/50 text-destructive" : "border-border text-muted-foreground"}`}
    >
      {text}
    </div>
  );
}

function MessagePanel({
  channelId,
  channelName,
  archived,
  discuss,
  onDiscussSent,
}: {
  channelId: string;
  channelName: string;
  archived: boolean;
  discuss: DiscussReference | null;
  onDiscussSent: () => void;
}) {
  const messages = useMessages(channelId);
  const send = useSendMessage(channelId);
  const markRead = useMarkChannelRead();
  const [body, setBody] = useState("");
  const [replyTo, setReplyTo] = useState<string | undefined>();
  const [attachment, setAttachment] = useState("");
  const [attachmentKind, setAttachmentKind] = useState<
    "document_id" | "analysis_id"
  >("analysis_id");
  const [showAttachment, setShowAttachment] = useState(Boolean(discuss));

  useEffect(() => {
    if (messages.data) markRead.mutate(channelId);
  }, [channelId, messages.dataUpdatedAt]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const value = body.trim();
    if (!value || archived || send.isPending) return;
    const reference = attachment.trim() || (discuss ? discuss.analysisId : "");
    send.mutate(
      {
        body: value,
        ...(replyTo ? { thread_id: replyTo } : {}),
        ...(reference
          ? {
              [discuss && !attachment.trim() ? "analysis_id" : attachmentKind]:
                reference,
            }
          : {}),
      },
      {
        onSuccess: () => {
          setBody("");
          setReplyTo(undefined);
          setAttachment("");
          onDiscussSent();
        },
      },
    );
  };

  const replyTarget = messages.data?.find((message) => message.id === replyTo);
  return (
    <section
      aria-label={`${channelName} conversation`}
      className="flex min-h-[560px] flex-col overflow-hidden rounded-xl border border-border bg-surface shadow-sm lg:h-[min(72vh,760px)]"
    >
      <header className="flex items-center gap-3 border-b border-border px-4 py-3 sm:px-5">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-gold/10 text-gold">
          <Hash className="size-4" />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-sm font-semibold">{channelName}</h2>
          <p className="text-xs text-muted-foreground">
            {messages.data?.length ?? 0} messages · matter conversation
          </p>
        </div>
        {archived && (
          <span className="rounded-full bg-muted px-2.5 py-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
            Read only
          </span>
        )}
      </header>

      <div
        className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4 sm:p-5"
        aria-live="polite"
      >
        {messages.isLoading ? (
          <div
            className="space-y-3"
            aria-busy="true"
            aria-label="Loading conversation"
          >
            {[0, 1, 2].map((item) => (
              <div
                key={item}
                className="h-16 animate-pulse rounded-lg bg-muted/60"
              />
            ))}
          </div>
        ) : messages.isError ? (
          <State
            error
            text="Messages are unavailable. Retry the conversation."
          />
        ) : messages.data?.length ? (
          messages.data.map((message) => (
            <article
              key={message.id}
              className={`group max-w-[94%] rounded-xl border border-border/70 p-3 sm:max-w-[86%] ${message.sender_kind === "USER" ? "bg-background" : "bg-muted/40"}`}
            >
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-[10px] text-muted-foreground">
                <span className="font-semibold text-steel">
                  {message.sender_ref}
                </span>
                <span>{new Date(message.created_at).toLocaleString()}</span>
                {message.sender_kind !== "USER" && (
                  <span className="rounded-full bg-steel/10 px-1.5 py-0.5">
                    {message.sender_kind}
                  </span>
                )}
              </div>
              <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-relaxed">
                {message.body}
              </p>
              {(message.analysis_id || message.document_id) && (
                <p className="mt-2 flex items-center gap-1.5 text-[10px] text-steel">
                  <Paperclip className="size-3" />
                  {message.analysis_id
                    ? `Analysis ${message.analysis_id.slice(0, 8)}`
                    : `Document ${message.document_id?.slice(0, 8)}`}
                </p>
              )}
              {!archived && (
                <button
                  type="button"
                  onClick={() => setReplyTo(message.id)}
                  className="mt-2 inline-flex items-center gap-1 rounded-md px-2 py-1 text-[10px] text-muted-foreground opacity-100 transition-all duration-200 hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100"
                >
                  <ArrowDownLeft className="size-3" /> Reply
                </button>
              )}
            </article>
          ))
        ) : (
          <div className="flex h-full min-h-64 flex-col items-center justify-center text-center">
            <span className="flex size-12 items-center justify-center rounded-full bg-gold/10 text-gold">
              <MessageSquare className="size-5" />
            </span>
            <p className="mt-4 text-sm font-medium">A clear space to begin</p>
            <p className="mt-1 max-w-xs text-xs text-muted-foreground">
              Share an update, ask a question, or bring a brief into the
              conversation.
            </p>
          </div>
        )}
      </div>

      {archived ? (
        <p className="border-t border-border bg-muted/30 px-4 py-3 text-xs text-muted-foreground sm:px-5">
          This concluded matter is preserved for reference. Replies and new
          posts are disabled.
        </p>
      ) : (
        <div className="border-t border-border bg-background/50 p-3 sm:p-4">
          {discuss && (
            <div className="mb-3 flex items-start gap-2 rounded-lg border border-gold/30 bg-gold/5 p-3">
              <FilePlus2 className="mt-0.5 size-4 shrink-0 text-gold" />
              <p className="min-w-0 flex-1 text-xs">
                <span className="font-medium">Discussing {discuss.label}</span>
                <span className="mt-0.5 block text-muted-foreground">
                  The brief reference will be attached to your first message.
                  Document content is not copied.
                </span>
              </p>
            </div>
          )}
          {replyTarget && (
            <div className="mb-2 flex items-center gap-2 rounded-lg bg-muted/60 px-3 py-2 text-xs">
              <ArrowDownLeft className="size-3.5 text-steel" />
              <span className="min-w-0 flex-1 truncate">
                Replying to {replyTarget.sender_ref}: {replyTarget.body}
              </span>
              <button
                type="button"
                onClick={() => setReplyTo(undefined)}
                aria-label="Cancel reply"
                className="rounded p-1 hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold"
              >
                ×
              </button>
            </div>
          )}
          {showAttachment && (
            <div className="mb-2 flex flex-col gap-2 sm:flex-row">
              <select
                aria-label="Attachment type"
                value={attachmentKind}
                onChange={(event) =>
                  setAttachmentKind(event.target.value as typeof attachmentKind)
                }
                className={`${inputClass} sm:w-36`}
              >
                <option value="analysis_id">Analysis reference</option>
                <option value="document_id">Document reference</option>
              </select>
              <input
                aria-label="Attachment reference ID"
                value={attachment || (discuss?.analysisId ?? "")}
                onChange={(event) => setAttachment(event.target.value)}
                placeholder="Paste an accessible UUID"
                className={`flex-1 ${inputClass}`}
              />
              <button
                type="button"
                onClick={() => {
                  setShowAttachment(false);
                  setAttachment("");
                }}
                className="rounded-lg px-3 py-2 text-xs text-muted-foreground transition-all duration-200 hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold"
              >
                Remove
              </button>
            </div>
          )}
          {send.isError && (
            <p role="alert" className="mb-2 text-xs text-destructive">
              Unable to send this message. Verify the attachment reference and
              try again.
            </p>
          )}
          <form onSubmit={submit} className="flex items-end gap-2">
            <label className="sr-only" htmlFor="channel-message">
              Message
            </label>
            <textarea
              id="channel-message"
              value={body}
              onChange={(event) => setBody(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                }
              }}
              placeholder="Write a message…"
              rows={2}
              maxLength={4000}
              className="min-h-11 min-w-0 flex-1 resize-y rounded-lg border border-border bg-background px-3 py-2.5 text-sm outline-none transition-all duration-200 focus-visible:ring-2 focus-visible:ring-gold"
            />
            <button
              type="button"
              onClick={() => setShowAttachment((shown) => !shown)}
              aria-label={
                showAttachment
                  ? "Hide attachment reference"
                  : "Attach a document or analysis reference"
              }
              className={`mb-0.5 rounded-lg p-2.5 transition-all duration-200 hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold ${showAttachment ? "text-gold" : "text-muted-foreground"}`}
            >
              <Paperclip className="size-4" />
            </button>
            <Button
              type="submit"
              disabled={send.isPending || !body.trim()}
              aria-label="Send message"
              className="mb-0.5"
            >
              <Send className="size-4 sm:mr-2" />
              <span className="sr-only sm:not-sr-only">
                {send.isPending ? "Sending…" : "Send"}
              </span>
            </Button>
          </form>
          <p className="mt-2 text-[10px] text-muted-foreground">
            Enter to send · Shift + Enter for a new line · References only; no
            raw file content
          </p>
        </div>
      )}
    </section>
  );
}

function ConversationWorkspace({
  kind,
  archivedOnly = false,
  discuss = null,
}: {
  kind: ChannelKind | "all";
  archivedOnly?: boolean;
  discuss?: DiscussReference | null;
}) {
  const channels = useChannels();
  const members = useMembers();
  const createDirect = useCreateDirectChannel();
  const [selectedId, setSelectedId] = useState("");
  const [directUser, setDirectUser] = useState("");
  const [selectedMembers, setSelectedMembers] = useState<string[]>([]);
  const [notice, setNotice] = useState("");
  const [activeDiscuss, setActiveDiscuss] = useState(discuss);
  const list = useMemo(
    () =>
      (channels.data ?? []).filter((channel) => {
        if (archivedOnly) return channel.is_archived;
        if (channel.is_archived) return false;
        if (kind === "matter") return channel.kind === "MATTER";
        if (kind === "direct") return channel.kind === "DIRECT";
        return channel.kind === "MATTER" || channel.kind === "DIRECT";
      }),
    [channels.data, archivedOnly, kind],
  );
  const selected = list.find((channel) => channel.id === selectedId) ?? list[0];
  const addParticipants = useAddChannelParticipants(selected?.id ?? "");

  useEffect(() => {
    setActiveDiscuss(discuss);
  }, [discuss]);

  useEffect(() => {
    if (discuss && list.length === 1 && list[0]) setSelectedId(list[0].id);
  }, [discuss, list]);

  const createDm = (event: FormEvent) => {
    event.preventDefault();
    if (!directUser || createDirect.isPending) return;
    createDirect.mutate(directUser, {
      onSuccess: (channel) => {
        setSelectedId(channel.id);
        setDirectUser("");
      },
    });
  };
  const inviteMembers = (event: FormEvent) => {
    event.preventDefault();
    if (!selectedMembers.length || addParticipants.isPending) return;
    addParticipants.mutate(selectedMembers, {
      onSuccess: ({ added_count }) => {
        setNotice(
          `${added_count} participant${added_count === 1 ? "" : "s"} added.`,
        );
        setSelectedMembers([]);
      },
      onError: () =>
        setNotice("Could not add participants. Retry the request."),
    });
  };

  return (
    <div className="space-y-4">
      {activeDiscuss && (
        <div className="flex flex-col gap-3 rounded-xl border border-gold/30 bg-gold/5 p-4 sm:flex-row sm:items-center">
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold">Start a matter discussion</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Choose the accessible matter channel for {activeDiscuss.label}.
              The brief reference stays attached to your first message.
            </p>
          </div>
          {list.length > 1 && (
            <label className="flex items-center gap-2 text-xs">
              <span className="sr-only">Choose matter channel</span>
              <select
                value={selected?.id ?? ""}
                onChange={(event) => setSelectedId(event.target.value)}
                className={`${inputClass} max-w-full`}
              >
                <option value="">Choose a channel</option>
                {list.map((channel) => (
                  <option key={channel.id} value={channel.id}>
                    {channel.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          {list.length === 1 && (
            <span className="rounded-lg bg-background px-3 py-2 text-xs font-medium">
              {list[0]?.name}
            </span>
          )}
        </div>
      )}
      {kind === "direct" && (
        <form onSubmit={createDm} className="flex flex-col gap-2 sm:flex-row">
          <label className="sr-only" htmlFor="new-direct-contact">
            Start a direct conversation
          </label>
          <select
            id="new-direct-contact"
            value={directUser}
            onChange={(event) => setDirectUser(event.target.value)}
            className={`flex-1 ${inputClass}`}
          >
            <option value="">Choose a colleague</option>
            {members.data?.map((member) => (
              <option key={member.user_ref} value={member.user_ref}>
                {member.full_name} ·{" "}
                {member.role ?? member.clearance ?? "Firm member"}
              </option>
            ))}
          </select>
          <Button
            type="submit"
            disabled={!directUser || createDirect.isPending}
          >
            <Plus className="mr-2 size-4" />
            {createDirect.isPending ? "Opening…" : "New direct message"}
          </Button>
        </form>
      )}
      {(channels.isError || members.isError) && (
        <State
          error
          text="Workspace data is unavailable. Check your connection and retry."
        />
      )}
      {createDirect.isError && (
        <State
          error
          text="Could not open this direct conversation. Confirm the selected colleague is a current firm member."
        />
      )}
      {notice && (
        <p role="status" className="text-xs text-muted-foreground">
          {notice}
        </p>
      )}

      <div className="grid min-h-[560px] gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
        <aside
          aria-label={
            archivedOnly ? "Archived conversations" : "Conversation list"
          }
          className="flex min-h-48 flex-col overflow-hidden rounded-xl border border-border bg-surface shadow-sm lg:min-h-0"
        >
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <div>
              <h2 className="text-sm font-semibold">
                {archivedOnly
                  ? "Archived"
                  : kind === "matter"
                    ? "Matter channels"
                    : kind === "direct"
                      ? "Direct"
                      : "Conversations"}
              </h2>
              <p className="mt-0.5 text-[11px] text-muted-foreground">
                {list.length}{" "}
                {list.length === 1 ? "conversation" : "conversations"}
              </p>
            </div>
            {archivedOnly ? (
              <Archive className="size-4 text-muted-foreground" />
            ) : (
              <Users className="size-4 text-steel" />
            )}
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-2" role="list">
            {channels.isLoading ? (
              <div
                className="space-y-2 p-2"
                aria-busy="true"
                aria-label="Loading conversations"
              >
                {[0, 1, 2].map((item) => (
                  <div
                    key={item}
                    className="h-14 animate-pulse rounded-lg bg-muted/60"
                  />
                ))}
              </div>
            ) : list.length ? (
              list.map((channel) => (
                <button
                  type="button"
                  key={channel.id}
                  onClick={() => {
                    setSelectedId(channel.id);
                    setNotice("");
                  }}
                  aria-current={
                    selected?.id === channel.id ? "true" : undefined
                  }
                  className={`mb-1 flex w-full items-start gap-3 rounded-lg border px-3 py-3 text-left transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold ${selected?.id === channel.id ? "border-gold/40 bg-gold/5" : "border-transparent hover:border-border hover:bg-background"}`}
                >
                  <span
                    className={`mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg ${channel.kind === "DIRECT" ? "bg-steel/10 text-steel" : "bg-gold/10 text-gold"}`}
                  >
                    {channel.kind === "DIRECT" ? (
                      <MessageSquare className="size-4" />
                    ) : (
                      <Hash className="size-4" />
                    )}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-xs font-medium">
                      {channel.name}
                    </span>
                    <span className="mt-1 block text-[10px] text-muted-foreground">
                      {channel.kind === "DIRECT"
                        ? "Direct message"
                        : `Matter · ${channel.matter_id?.slice(0, 8) ?? "Firm"}`}
                    </span>
                  </span>
                  {channel.is_archived && (
                    <Archive className="size-3 text-muted-foreground" />
                  )}
                </button>
              ))
            ) : (
              <div className="p-3">
                <State
                  text={
                    archivedOnly
                      ? "No archived channels are available."
                      : kind === "direct"
                        ? "No direct conversations yet. Choose a colleague above to start one."
                        : "No matter channels are available to you."
                  }
                />
              </div>
            )}
          </div>
          {selected?.kind === "MATTER" &&
            !selected.is_archived &&
            !archivedOnly && (
              <form
                onSubmit={inviteMembers}
                className="space-y-2 border-t border-border p-3"
              >
                <label
                  htmlFor="channel-participants"
                  className="font-mono text-[9px] uppercase tracking-widest text-muted-foreground"
                >
                  Add participants
                </label>
                <select
                  id="channel-participants"
                  multiple
                  value={selectedMembers}
                  onChange={(event) =>
                    setSelectedMembers(
                      Array.from(
                        event.target.selectedOptions,
                        (option) => option.value,
                      ),
                    )
                  }
                  className="max-h-24 w-full rounded-lg border border-border bg-background p-2 text-xs outline-none focus-visible:ring-2 focus-visible:ring-gold"
                >
                  {members.data?.map((member) => (
                    <option key={member.user_ref} value={member.user_ref}>
                      {member.full_name}
                    </option>
                  ))}
                </select>
                <Button
                  type="submit"
                  variant="outline"
                  size="sm"
                  disabled={
                    !selectedMembers.length || addParticipants.isPending
                  }
                  className="w-full"
                >
                  {addParticipants.isPending
                    ? "Adding…"
                    : "Add selected members"}
                </Button>
                <p className="text-[10px] text-muted-foreground">
                  Hold Ctrl or Cmd to select more than one.
                </p>
              </form>
            )}
        </aside>
        {selected ? (
          <MessagePanel
            key={selected.id}
            channelId={selected.id}
            channelName={selected.name}
            archived={archivedOnly || selected.is_archived}
            discuss={activeDiscuss}
            onDiscussSent={() => {
              if (activeDiscuss) {
                setNotice("Brief reference shared with the channel.");
                setActiveDiscuss(null);
                window.history.replaceState(
                  window.history.state,
                  "",
                  "/channels",
                );
              }
            }}
          />
        ) : (
          <div className="hidden rounded-xl border border-dashed border-border bg-surface/50 lg:flex lg:items-center lg:justify-center">
            <div className="max-w-xs px-6 text-center">
              <MessageSquare className="mx-auto size-7 text-muted-foreground" />
              <h2 className="mt-3 text-sm font-semibold">
                Select a conversation
              </h2>
              <p className="mt-1 text-xs text-muted-foreground">
                Messages and matter references stay in their permission-scoped
                channel.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Pins() {
  const pins = usePins();
  const remove = useDeletePin();
  const create = useCreatePin();
  const [resourceType, setResourceType] = useState<string>("CHANNEL");
  const [resourceId, setResourceId] = useState("");
  const [label, setLabel] = useState("");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const id = resourceId.trim();
    const name = label.trim();
    if (id && name && !create.isPending)
      create.mutate(
        { resource_type: resourceType, resource_id: id, label: name },
        {
          onSuccess: () => {
            setResourceId("");
            setLabel("");
          },
        },
      );
  };
  if (pins.isLoading) return <State text="Loading pins…" />;
  if (pins.isError)
    return (
      <State
        error
        text="Pins are unavailable. Check the API connection and retry."
      />
    );
  return (
    <div className="space-y-4">
      <form
        onSubmit={submit}
        className="grid gap-2 sm:grid-cols-[auto_minmax(0,1fr)_minmax(0,1fr)_auto]"
      >
        <select
          value={resourceType}
          onChange={(event) => setResourceType(event.target.value)}
          aria-label="Resource type"
          className={inputClass}
        >
          {RESOURCE_TYPES.map((item) => (
            <option key={item}>{item}</option>
          ))}
        </select>
        <input
          value={resourceId}
          onChange={(event) => setResourceId(event.target.value)}
          placeholder="Resource UUID"
          aria-label="Resource ID"
          className={inputClass}
        />
        <input
          value={label}
          onChange={(event) => setLabel(event.target.value)}
          placeholder="Pin label"
          aria-label="Pin label"
          className={inputClass}
        />
        <Button
          type="submit"
          disabled={create.isPending || !resourceId.trim() || !label.trim()}
        >
          <Plus className="mr-2 size-4" />
          Pin
        </Button>
      </form>
      {create.isError && (
        <State
          error
          text="Could not create this pin. Check the resource ID and type."
        />
      )}
      {pins.data?.length ? (
        <div className="grid gap-3 sm:grid-cols-2">
          {pins.data.map((pin) => (
            <article
              key={pin.id}
              className="rounded-xl border border-border bg-surface p-4"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <strong>{pin.label}</strong>
                  <p className="mt-1 font-mono text-[10px] text-muted-foreground">
                    {pin.resource_type} · {pin.resource_id.slice(0, 8)}
                  </p>
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => remove.mutate(pin.id)}
                >
                  Remove
                </Button>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <State text="No pins yet. Save a matter, message, or analysis reference here." />
      )}
    </div>
  );
}

function Threads() {
  const threads = useThreads();
  const create = useCreateThread();
  const [title, setTitle] = useState("");
  return (
    <section className="space-y-4">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          const value = title.trim();
          if (value && !create.isPending)
            create.mutate(value, { onSuccess: () => setTitle("") });
        }}
        className="flex flex-col gap-2 sm:flex-row"
      >
        <input
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="New thread title"
          aria-label="New thread title"
          className={`flex-1 ${inputClass}`}
        />
        <Button type="submit" disabled={create.isPending || !title.trim()}>
          <Plus className="mr-2 size-4" />
          {create.isPending ? "Creating…" : "New thread"}
        </Button>
      </form>
      {create.isError && (
        <State error text="Unable to create the thread. Please retry." />
      )}
      {threads.isLoading ? (
        <State text="Loading threads…" />
      ) : threads.isError ? (
        <State
          error
          text="Threads are unavailable. Check the API connection and retry."
        />
      ) : threads.data?.length ? (
        <div className="grid gap-3 md:grid-cols-2">
          {threads.data.map((thread) => (
            <Link
              key={thread.thread_id}
              to="/threads/$threadId"
              params={{ threadId: thread.thread_id }}
              className="rounded-xl border border-border bg-surface p-4 transition-all duration-200 hover:border-gold/50"
            >
              <MessageSquare className="size-4 text-gold" />
              <strong className="mt-3 block">{thread.title}</strong>
              <small className="text-muted-foreground">
                Updated {new Date(thread.updated_at).toLocaleString()}
              </small>
            </Link>
          ))}
        </div>
      ) : (
        <State text="No assistant threads yet. Create one to begin grounded work." />
      )}
    </section>
  );
}

function Contacts() {
  const members = useMembers();
  if (members.isLoading) return <State text="Loading firm directory…" />;
  if (members.isError)
    return (
      <State
        error
        text="Contacts are unavailable. Check the API connection and retry."
      />
    );
  return members.data?.length ? (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {members.data.map((member) => (
        <article
          key={member.user_ref}
          className="rounded-xl border border-border bg-surface p-4 shadow-sm"
        >
          <div className="flex items-center gap-3">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-gold/15 font-semibold text-gold">
              {member.full_name.slice(0, 2).toUpperCase()}
            </span>
            <div className="min-w-0">
              <strong className="block truncate">{member.full_name}</strong>
              <small className="text-muted-foreground">
                {member.role ?? member.clearance ?? "Firm member"}
              </small>
            </div>
          </div>
        </article>
      ))}
    </div>
  ) : (
    <State text="No firm members found." />
  );
}

export function CollaborationWorkspace({ section }: { section: Section }) {
  const titles: Record<Section, string> = {
    pins: "Pins",
    chats: "Direct",
    channels: "Matter Channels",
    threads: "Assistant Threads",
    contacts: "Contacts",
    archived: "Archived",
  };
  const nav: Array<{ id: Section; label: string; icon: typeof MessageSquare }> =
    [
      { id: "channels", label: "Channels", icon: Hash },
      { id: "chats", label: "Direct", icon: MessageSquare },
      { id: "contacts", label: "Contacts", icon: Users },
      { id: "archived", label: "Archived", icon: Archive },
    ];
  const [discuss, setDiscuss] = useState<DiscussReference | null>(null);
  useEffect(() => {
    if (section !== "channels") {
      setDiscuss(null);
      return;
    }
    const params = new URLSearchParams(window.location.search);
    const analysisId = params.get("analysis");
    if (analysisId)
      setDiscuss({ analysisId, label: `brief ${analysisId.slice(0, 8)}` });
  }, [section]);

  return (
    <AppShell
      title={titles[section]}
      eyebrow={`COMMUNICATIONS · ${section.toUpperCase()}`}
    >
      <div className="mx-auto max-w-7xl space-y-5">
        <nav
          className="flex gap-1 overflow-x-auto border-b border-border pb-2"
          aria-label="Collaboration sections"
        >
          {nav.map((item) => {
            const Icon = item.icon;
            return (
              <Link
                key={item.id}
                to={`/${item.id}`}
                aria-current={item.id === section ? "page" : undefined}
                className={`inline-flex shrink-0 items-center gap-2 rounded-t-lg border-b-2 px-3 py-2.5 text-xs font-medium transition-all duration-200 hover:text-foreground ${item.id === section ? "border-gold text-gold" : "border-transparent text-muted-foreground"}`}
              >
                <Icon className="size-3.5" />
                {item.label}
              </Link>
            );
          })}
        </nav>
        {section === "pins" && <Pins />}
        {section === "channels" && (
          <ConversationWorkspace kind="matter" discuss={discuss} />
        )}
        {section === "chats" && <ConversationWorkspace kind="direct" />}
        {section === "archived" && (
          <ConversationWorkspace kind="all" archivedOnly />
        )}
        {section === "threads" && <Threads />}
        {section === "contacts" && <Contacts />}
      </div>
    </AppShell>
  );
}
