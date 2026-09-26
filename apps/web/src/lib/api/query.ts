// Vault Search data hook — POST /v1/query (Phase1-Design §3.5).
//
// Renders the API's grounded response, verified citations, or explicit refusal.

import { useMutation } from "@tanstack/react-query";

import { apiPost } from "@/lib/api/client";
import { runVaultQueryDev } from "@/lib/api/dev/query";
import type { QueryRequest, QueryResponse } from "@/lib/api/types";

const USE_DEV_ADAPTER = import.meta.env.VITE_API_DEV_ADAPTER === "1";

export function runVaultQuery(req: QueryRequest): Promise<QueryResponse> {
  return USE_DEV_ADAPTER
    ? runVaultQueryDev(req)
    : apiPost<QueryResponse, QueryRequest>("/v1/query", req);
}

export function useVaultQuery<TData = QueryResponse>() {
  return useMutation({
    mutationFn: async (request: QueryRequest) =>
      (await runVaultQuery(request)) as TData,
  });
}
