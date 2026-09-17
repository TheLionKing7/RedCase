// Statutory Tracker typed client — deadline_events / deadline_rules shapes,
// Phase3-Design §3.1 (verbatim). The backend endpoint lands in Phase 3
// (Task 3.4); the dev adapter (lib/api/dev/deadlines.ts) mirrors these shapes
// exactly for development.
// OWNER RULING 2 (2026-09-16): do not invent shapes — fields below are the
// §3.1 DDL columns, camelCased only where the doc itself implies JSON.

import { useQuery } from "@tanstack/react-query";

import { apiGet } from "@/lib/api/client";
import { listDeadlineEventsDev } from "@/lib/api/dev/deadlines";

export type DeadlineEventType = "FILING_DEADLINE" | "HEARING" | "LIMITATION";
export type DeadlineStatus = "PENDING" | "NOTIFIED" | "DISMISSED" | "MISSED";
export type DeadlineComputation = "CALENDAR" | "BUSINESS";

/** §3.1 deadline_events row. */
export interface DeadlineEvent {
  id: string;
  tenant_id: string;
  matter_id: string;
  source_document_id: string | null;
  rule_id: string | null;
  event_type: DeadlineEventType;
  description: string;
  trigger_date: string | null;
  due_date: string;
  confidence: number | null;
  status: DeadlineStatus;
  assigned_to: string | null;
  created_at: string;
}

/** §3.1 deadline_rules row — validated by counsel before go-live;
 *  unvalidated rows surface a warning in the UI per the design note. */
export interface DeadlineRule {
  id: string;
  jurisdiction: string;
  court_level: string;
  rule_name: string;
  trigger_event: string;
  offset_days: number;
  computation: DeadlineComputation;
  source_ref: string;
  validated_by: string | null;
  validated_at: string | null;
  valid_from: string | null;
  valid_to: string | null;
}

const USE_DEV_ADAPTER = import.meta.env.VITE_API_DEV_ADAPTER === "1";

export function listDeadlineEvents(): Promise<DeadlineEvent[]> {
  return USE_DEV_ADAPTER
    ? listDeadlineEventsDev()
    : apiGet<DeadlineEvent[]>("/v1/deadlines/events");
}

export function useDeadlineEvents() {
  return useQuery({
    queryKey: ["deadlines", "events"],
    queryFn: listDeadlineEvents,
  });
}
