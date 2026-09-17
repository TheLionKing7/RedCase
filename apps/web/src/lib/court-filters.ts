// Vault Search filter-chip option lists (UI constants, formerly part of the
// aetoes-data mock). The backend owns the canonical court levels
// (documents.court_level CHECK constraint, Phase1-Design §2.1); `value` is the
// exact enum the CHECK constraint stores and QueryRequest.court_level expects —
// display labels alone ("Supreme Court") would never match a row.
//
// `value: ""` means "no filter" and maps to null on the wire.

export interface FilterOption {
  label: string;
  value: string;
}

export const COURT_LEVELS: FilterOption[] = [
  { label: "All Courts", value: "" },
  { label: "Supreme Court", value: "SUPREME_COURT" },
  { label: "Court of Appeal", value: "COURT_OF_APPEAL" },
  { label: "Federal High Court", value: "FEDERAL_HIGH_COURT" },
  { label: "State High Court", value: "STATE_HIGH_COURT" },
  { label: "National Industrial Court", value: "NICN" },
];

export const RATIO_TAGS: FilterOption[] = [
  { label: "All Ratios", value: "" },
  { label: "Jurisdiction", value: "Jurisdiction" },
  { label: "Interlocutory injunction", value: "Interlocutory injunction" },
  { label: "Locus standi", value: "Locus standi" },
  { label: "Force majeure", value: "Force majeure" },
  { label: "Condition precedent", value: "Condition precedent" },
  { label: "Evidence & burden of proof", value: "Evidence & burden of proof" },
];
