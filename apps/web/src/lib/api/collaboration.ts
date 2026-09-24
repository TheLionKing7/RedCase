import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiDelete, apiGet, apiPost } from "@/lib/api/client";
import { getAccessToken } from "@/lib/auth/supabase";

export type Member = { user_ref: string; full_name: string; role: string | null; clearance: string | null };
export type Pin = { id: string; resource_type: string; resource_id: string; label: string; created_at: string };
export type Channel = { id: string; name: string; kind: string; matter_id: string | null; created_at: string };
export type Message = { id: string; channel_id: string; sender_ref: string; sender_kind: string; body: string; thread_id: string | null; document_id: string | null; analysis_id: string | null; created_at: string };
export type AssistantTurn = { id: string; role: "USER" | "ASSISTANT"; content: string; created_at: string };
export type AssistantThreadDetail = { thread_id: string; title: string; created_at: string; turns: AssistantTurn[]; digest: Record<string, unknown> };
export type AssistantThread = { thread_id: string; title: string; created_at: string; updated_at: string };

export const usePins = () => useQuery({ queryKey: ["pins"], queryFn: () => apiGet<Pin[]>("/v1/pins") });
export const useMembers = () => useQuery({ queryKey: ["members", "directory"], queryFn: () => apiGet<Member[]>("/v1/members") });
export const useChannels = () => useQuery({ queryKey: ["channels"], queryFn: () => apiGet<Channel[]>("/v1/channels") });
export const useMessages = (channelId: string | undefined) => useQuery({ queryKey: ["messages", channelId], queryFn: () => apiGet<Message[]>(`/v1/channels/${channelId}/messages`), enabled: Boolean(channelId) });
export const useThreads = () => useQuery({ queryKey: ["assistant-threads"], queryFn: () => apiGet<AssistantThread[]>("/v1/assistant/threads") });
export const useThread = (id: string) => useQuery({ queryKey: ["assistant-thread", id], queryFn: () => apiGet<AssistantThreadDetail>(`/v1/assistant/threads/${id}`), enabled: Boolean(id) });
export async function sendAssistantMessage(id: string, message: string): Promise<string> {
  const response = await fetch(`${(import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://127.0.0.1:8000"}/v1/assistant/threads/${id}/messages`, { method: "POST", headers: { "content-type": "application/json", ...(getAccessToken() ? { authorization: `Bearer ${getAccessToken()}` } : {}) }, body: JSON.stringify({ message }) });
  if (!response.ok || !response.body) throw new Error("Unable to send assistant message");
  const reader = response.body.getReader(); const decoder = new TextDecoder(); let result = "";
  while (true) { const next = await reader.read(); if (next.done) break; for (const line of decoder.decode(next.value).split("\n")) { if (!line.startsWith("data: ")) continue; try { const event = JSON.parse(line.slice(6)) as { event?: string; content?: string }; if (event.event === "assistant_reply") result = event.content ?? ""; } catch { /* incomplete SSE frame */ } } }
  return result;
}
export function useCreatePin() { const qc = useQueryClient(); return useMutation({ mutationFn: (body: { resource_type: string; resource_id: string; label: string }) => apiPost<Pin, typeof body>("/v1/pins", body), onSuccess: () => qc.invalidateQueries({ queryKey: ["pins"] }) }); }
export function useDeletePin() { const qc = useQueryClient(); return useMutation({ mutationFn: (id: string) => apiDelete(`/v1/pins/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ["pins"] }) }); }
export function useSendMessage(channelId: string) { const qc = useQueryClient(); return useMutation({ mutationFn: (body: { body: string }) => apiPost(`/v1/channels/${channelId}/messages`, body), onSuccess: () => qc.invalidateQueries({ queryKey: ["messages", channelId] }) }); }
export function useCreateThread() { const qc = useQueryClient(); return useMutation({ mutationFn: (title: string) => apiPost<{ thread_id: string }, { title: string }>("/v1/assistant/threads", { title }), onSuccess: () => qc.invalidateQueries({ queryKey: ["assistant-threads"] }) }); }
