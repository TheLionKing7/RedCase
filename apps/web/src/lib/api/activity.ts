import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "@/lib/api/client";

export interface ActivitySession {
  id: string;
  area: string;
  target_type: "matter" | "area" | null;
  target_ref: string | null;
  target_label?: string | null;
  started_at: string;
  ended_at: string | null;
  duration: number | null;
}

export interface ActivitySessionGroup {
  target_type: "matter" | "area";
  target_ref: string;
  target_label: string;
  total_duration: number;
  session_count: number;
}

export function useActivitySessions() {
  return useQuery({
    queryKey: ["activity-sessions"],
    queryFn: () =>
      apiGet<{
        sessions: ActivitySession[];
        groups: ActivitySessionGroup[];
      }>("/v1/activity-sessions"),
  });
}

export function useClockIn() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (target: {
      area: string;
      target_type: "matter" | "area";
      target_ref: string;
    }) =>
      apiPost<ActivitySession, typeof target>(
        "/v1/activity-sessions/clock-in",
        target,
      ),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["activity-sessions"] }),
  });
}

export function useClockOut() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiPost<ActivitySession, Record<string, never>>(
        "/v1/activity-sessions/clock-out",
        {},
      ),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["activity-sessions"] }),
  });
}
