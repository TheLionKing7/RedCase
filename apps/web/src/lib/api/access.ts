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
  document_id: string | null;
  brief_name?: string | null;
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
  brief_name: string;
  document_id?: string;
  grantee_ref?: string | null;
  grant_level: "READ" | "ANNOTATE";
  reason?: string | null;
}

export interface AccessGrant {
  id: string;
  document_id: string;
  brief_name: string | null;
  granted_at: string;
  expires_at: string | null;
  relinquished_at: string | null;
  grant_level: string;
}

export function useAccessGrants() {
  return useQuery({
    queryKey: ["access", "grants"],
    queryFn: () => apiGet<{ grants: AccessGrant[] }>("/v1/access-grants"),
  });
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

export function useRelinquishGrant() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (grantId: string) =>
      apiPost<{ status: string }, Record<string, never>>(
        `/v1/access-grants/${grantId}/relinquish`,
        {},
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["access", "grants"] });
      qc.invalidateQueries({ queryKey: ["access", "requests"] });
    },
  });
}

export function decideAccessRequest(input: {
  id: string;
  approve: boolean;
  grant_level?: string | null;
  expires_at?: string | null;
  grantee_ref?: string | null;
}): Promise<{ status: AccessDecisionStatus }> {
  return apiPost<
    { status: AccessDecisionStatus },
    {
      approve: boolean;
      grant_level?: string | null;
      expires_at?: string | null;
      grantee_ref?: string | null;
    }
  >(`/v1/access-requests/${input.id}/decide`, {
    approve: input.approve,
    grant_level: input.grant_level ?? null,
    expires_at: input.expires_at ?? null,
    grantee_ref: input.grantee_ref ?? null,
  });
}

export function useDecideAccessRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: decideAccessRequest,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["access", "requests"] }),
  });
}
