// DEV ADAPTER — Vault Search. Mirrors the Phase1 §3.5 QueryResponse schema
// EXACTLY using types from lib/api/types (the wire contract); fixture content
// draws on the live benchmark corpus (fixtures/landmark-sc) so the redesigned
// results UI is reviewable without the FastAPI backend or model credentials.
// Selected only when VITE_API_DEV_ADAPTER=1 (see lib/api/query.ts).

import type { QueryRequest, QueryResponse } from "@/lib/api/types";

function answerFor(req: QueryRequest): QueryResponse {
  const filters = [
    req.court_level,
    req.year_from ? `from ${req.year_from}` : null,
    req.year_to ? `to ${req.year_to}` : null,
    req.ratio_decidendi,
  ].filter(Boolean);
  const scope = filters.length ? ` under ${filters.join(", ")}` : "";

  return {
    answer:
      `On the issue as stated${scope}, the consistent thread in the retrieved ` +
      "passages is that an originating process that fails a condition " +
      "preceder to the court's jurisdiction renders the proceeding a nullity, " +
      "not a mere irregularity — and that objection must be raised timeously, " +
      "at the earliest opportunity. The authorities retrieved pin this to " +
      "Madukolu v. Nkemdilim (competence as a unity of jurisdiction, " +
      "subject-matter and venue) and Adegoke Motors v. Adesanya (conditions " +
      "preceder going to jurisdiction versus procedure).",
    citations: [
      {
        document_id: "86c9c070-2304-456a-8a62-4ec8bc0d0b95",
        case_title: "Madukolu v. Nkemdilim",
        citation: "[1962] 1 All NLR 587",
        court_level: "SUPREME_COURT",
        year: 1962,
        page_start: 3,
        page_end: 4,
        paragraph_refs: ["12", "13"],
        source_pdf_url: "#dev-madukolu",
        verified: true,
      },
      {
        document_id: "2a17bb5b-a6d5-41bd-b66e-bf3505bc6380",
        case_title: "Adegoke Motors Ltd. v. Dr. Babatunde Adesanya",
        citation: "(1989) 3 NWLR (Pt. 109) 250",
        court_level: "SUPREME_COURT",
        year: 1989,
        page_start: 261,
        page_end: 263,
        paragraph_refs: ["31"],
        source_pdf_url: "#dev-adegoke",
        verified: true,
      },
      {
        document_id: "c68f1e92-3b7a-4d2c-9e5f-8a1d3b4c5e60",
        case_title: "Amaechi v. Independent National Electoral Commission",
        citation: "(2008) 5 NWLR (Pt. 1080) 227",
        court_level: "SUPREME_COURT",
        year: 2008,
        page_start: 589,
        page_end: 590,
        paragraph_refs: ["104"],
        source_pdf_url: "#dev-amaechi",
        verified: true,
      },
    ],
    refusal: false,
  };
}

export function runVaultQueryDev(req: QueryRequest): Promise<QueryResponse> {
  return new Promise((resolve) => setTimeout(() => resolve(answerFor(req)), 700));
}
