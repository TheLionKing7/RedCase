// Vault Search data hook — POST /v1/query (Phase1-Design §3.5).
//
// Replaces the deleted VAULT_RESULTS mock: the screen submits a QueryRequest
// and renders the server's QueryResponse (answer + verified citations, or a
// refusal — never an unverified answer; §3.4).

import { useMutation } from "@tanstack/react-query";

import { apiPost } from "@/lib/api/client";
import type { QueryRequest, QueryResponse } from "@/lib/api/types";

export function runVaultQuery(req: QueryRequest): Promise<QueryResponse> {
  return apiPost<QueryResponse, QueryRequest>("/v1/query", req);
}

export function useVaultQuery() {
  return useMutation({ mutationFn: runVaultQuery });
}
