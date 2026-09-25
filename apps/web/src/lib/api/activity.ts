import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "@/lib/api/client";

export interface ActivitySession {
  id: string;
  area: string;
  started_at: string;
  ended_at: string | null;
  duration: number | null;
}

export function useActivitySessions() {
  return useQuery({
    queryKey: ["activity-sessions"],
    queryFn: () => apiGet<{ sessions: ActivitySession[] }>("/v1/activity-sessions"),
  });
}

export function useClockIn() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (area: string) => apiPost<ActivitySession, { area: string }>("/v1/activity-sessions/clock-in", { area }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["activity-sessions"] }),
  });
}

export function useClockOut() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiPost<ActivitySession, Record<string, never>>("/v1/activity-sessions/clock-out", {}),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["activity-sessions"] }),
  });
}