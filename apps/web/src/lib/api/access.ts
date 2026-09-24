// Access-request flow typed client — IA spec §1.6 (S10-4).
//
// Mirrors the FastAPI wire model in app/routers/access.py (owner ruling 2 — no
// invented fields). A user requests a named GRANT on a named document; a licensed
// senior reviewer (PARTNER/ADMIN — never the requester) approves (writing a real
// document_grants ACL row) or denies. The request row itself grants nothing.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiGet, apiPost } from "@/lib/api/client";

export type AccessDecisionStatus = "PENDING" | "APPROVED" | "DENIED";

/** Wire mirror of the access_requests SELECT shape (app/routers/access.py). */
export interface AccessRequest {
  id: string;
  document_id: string;
  requester_ref: string;
  grantee_ref: string;
  grant_level: string;
  reason: string | null;
  status: AccessDecisionStatus;
  decided_by: string | null;
  decided_at: string | null;
  created_at: string;
}

export interface CreateAccessRequest {
  document_id: string;
  grantee_ref: string;
  grant_level: "READ" | "ANNOTATE";
  reason?: string | null;
}

/** The caller's requests: what they asked for + what awaits their decision. */
export function getAccessRequests(): Promise<{ requests: AccessRequest[] }> {
  return apiGet<{ requests: AccessRequest[] }>("/v1/access-requests");
}

export function useAccessRequests() {
  return useQuery({
    queryKey: ["access", "requests"],
    queryFn: getAccessRequests,
  });
}

export function createAccessRequest(
  body: CreateAccessRequest,
): Promise<{ request: AccessRequest }> {
  return apiPost<{ request: AccessRequest }, CreateAccessRequest>(
    "/v1/access-requests",
    body,
  );
}

export function useCreateAccessRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createAccessRequest,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["access", "requests"] }),
  });
}

export function decideAccessRequest(input: {
  id: string;
  approve: boolean;
  grant_level?: string | null;
}): Promise<{ status: AccessDecisionStatus }> {
  return apiPost<
    { status: AccessDecisionStatus },
    { approve: boolean; grant_level?: string | null }
  >(`/v1/access-requests/${input.id}/decide`, {
    approve: input.approve,
    grant_level: input.grant_level ?? null,
  });
}

export function useDecideAccessRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: decideAccessRequest,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["access", "requests"] }),
  });
}
