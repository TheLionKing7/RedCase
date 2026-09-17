// Vault Search filter-chip option lists (UI constants, formerly part of the
// aetoes-data mock). These are presentation options; the backend owns the
// canonical court levels (documents.court_level CHECK constraint,
// Phase1-Design §2.1).

export const COURT_LEVELS = [
  "All Courts",
  "Supreme Court",
  "Court of Appeal",
  "Federal High Court",
  "State High Court",
  "National Industrial Court",
];

export const RATIO_TAGS = [
  "All Ratios",
  "Jurisdiction",
  "Interlocutory injunction",
  "Locus standi",
  "Force majeure",
  "Condition precedent",
  "Evidence & burden of proof",
];
