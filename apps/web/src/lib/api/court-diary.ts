import { useQuery } from "@tanstack/react-query";

import { apiGet } from "@/lib/api/client";

export type CourtDiaryEntry = {
  id: string;
  matter_id: string;
  source_document_id: string | null;
  event_id: string | null;
  title: string;
  entry_type: "HEARING" | "FILING" | "MENTION" | "OTHER";
  starts_at: string;
  ends_at: string | null;
  courtroom: string | null;
  judge: string | null;
  notes: string | null;
  status: "SCHEDULED" | "COMPLETED" | "ADJOURNED" | "CANCELLED";
  created_by: string;
  created_at: string;
};

export function listCourtDiaryEntries(): Promise<CourtDiaryEntry[]> {
  return apiGet<CourtDiaryEntry[]>("/v1/court-diary/entries");
}

export function useCourtDiaryEntries() {
  return useQuery({
    queryKey: ["court-diary", "entries"],
    queryFn: listCourtDiaryEntries,
  });
}