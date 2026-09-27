import { useQuery } from "@tanstack/react-query";

import { apiGet } from "@/lib/api/client";

const USE_DEV_ADAPTER = import.meta.env.VITE_API_DEV_ADAPTER === "1";

function iso(daysFromNow: number, hour: number): string {
  const date = new Date();
  date.setDate(date.getDate() + daysFromNow);
  date.setHours(hour, 30, 0, 0);
  return date.toISOString();
}

const DEV_ENTRIES: CourtDiaryEntry[] = [
  {
    id: "d0000001-0000-4000-8000-000000000001",
    matter_id: "3f6c8b20-7d1e-4f5a-9c2d-5e8a1b3d4f60",
    source_document_id: null,
    event_id: null,
    title: "Case management conference",
    entry_type: "HEARING",
    starts_at: iso(2, 10),
    ends_at: null,
    courtroom: "Court 4, Lagos High Court",
    judge: null,
    notes: "Synthetic development fixture",
    status: "SCHEDULED",
    created_by: "dev-fixture",
    created_at: new Date().toISOString(),
  },
  {
    id: "d0000001-0000-4000-8000-000000000002",
    matter_id: "8c1e2d40-9a3b-4c7e-b2f5-6d0e9a1c3b78",
    source_document_id: null,
    event_id: null,
    title: "Counsel preparation meeting",
    entry_type: "OTHER",
    starts_at: iso(5, 14),
    ends_at: null,
    courtroom: null,
    judge: null,
    notes: "Synthetic development fixture",
    status: "SCHEDULED",
    created_by: "dev-fixture",
    created_at: new Date().toISOString(),
  },
  {
    id: "d0000001-0000-4000-8000-000000000003",
    matter_id: "3f6c8b20-7d1e-4f5a-9c2d-5e8a1b3d4f60",
    source_document_id: null,
    event_id: null,
    title: "Mention for filing update",
    entry_type: "MENTION",
    starts_at: iso(9, 9),
    ends_at: null,
    courtroom: "Registry, Court 2",
    judge: null,
    notes: "Synthetic development fixture",
    status: "SCHEDULED",
    created_by: "dev-fixture",
    created_at: new Date().toISOString(),
  },
];

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
  return USE_DEV_ADAPTER
    ? Promise.resolve(DEV_ENTRIES)
    : apiGet<CourtDiaryEntry[]>("/v1/court-diary/entries");
}

export function useCourtDiaryEntries() {
  return useQuery({
    queryKey: ["court-diary", "entries"],
    queryFn: listCourtDiaryEntries,
  });
}
