// Legal Workbench typed client — Feature-Addendum §3.2, Steps A + B.
// The Workbench (Step B) is a tabbed workspace (Overview / Arguments / Similar
// Cases / Law) over a single `document_analyses` object (Addendum §3.1). These
// shapes mirror the FastAPI AnalysisStatus wire model in app/routers/analyses.py
// (owner ruling 2 — no invented fields). The `list` endpoint is the per-user
// "My Operations" surface (§6.2); `get` fetches the tabbed pack output.

import { useQuery } from "@tanstack/react-query";

import { apiGet } from "@/lib/api/client";

/** §3.1 status values. */
export type AnalysisStatusValue =
  | "RUNNING"
  | "COMPLETE"
  | "FAILED"
  | "NEEDS_REVIEW";

/** §3.3 prompt packs. */
export type PromptPack =
  | "ADVERSAL_BRIEF"
  | "SUMMONS_RESPONSE"
  | "CONTRACT_REVIEW";

/** Wire mirror of AnalysisStatus (app/routers/analyses.py). */
export interface Analysis {
  analysis_id: string;
  document_id: string;
  prompt_pack: PromptPack;
  status: AnalysisStatusValue;
  output: Record<string, unknown> | null;
  confidence: Record<string, unknown> | null;
  error: string | null;
  created_by: string;
  created_at: string;
}

export function listAnalyses(): Promise<Analysis[]> {
  return apiGet<Analysis[]>("/v1/analyses");
}

export function getAnalysis(id: string): Promise<Analysis> {
  return apiGet<Analysis>(`/v1/analyses/${id}`);
}

export function useAnalyses() {
  return useQuery({
    queryKey: ["analyses", "list"],
    queryFn: listAnalyses,
  });
}

export function useAnalysis(id: string | null) {
  return useQuery({
    queryKey: ["analyses", id],
    queryFn: () => getAnalysis(id!),
    enabled: !!id,
  });
}
