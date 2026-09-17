// RedCase API contract types — POST /v1/query (Phase1-Design §3.5, verbatim).
//
// These types are the frontend mirror of the FastAPI response schemas. Until
// Task 1.4 lands there is no live OpenAPI to generate from, so they are
// transcribed from the design doc, which is the source of truth (HANDOFF.md
// rule 3). Once apps/api exposes /v1/query, regenerate with:
//   npx openapi-typescript http://127.0.0.1:8000/openapi.json -o src/lib/api/generated.ts
// and diff against this file — any drift is a design-doc violation to report,
// not to paper over.
//
// OWNER RULING (2026-09-16): no `vault` field is added here. Vault selection
// is server-side (Phase 2 router); Phase 1 is locked to Vault B.

/** QueryRequest — Phase1-Design §3.5 (question: 10–2000 chars; years 1960–2026). */
export interface QueryRequest {
  question: string;
  court_level?: string | null;
  year_from?: number | null;
  year_to?: number | null;
  ratio_decidendi?: string | null;
}

/** Citation — one verified, page-pinned authority (Phase1-Design §3.5). */
export interface Citation {
  document_id: string;
  case_title: string;
  citation: string;
  court_level: string;
  year: number;
  page_start: number;
  page_end: number;
  paragraph_refs: string[];
  source_pdf_url: string;
  verified: boolean;
}

/**
 * QueryResponse — Phase1-Design §3.5.
 * refusal=true (§3.4): best retrieved vsim < VECTOR_GATE (0.78), or citation
 * integrity failed twice. The UI must render a refusal state — never an
 * unverified answer.
 */
export interface QueryResponse {
  answer: string;
  citations: Citation[];
  refusal: boolean;
}
