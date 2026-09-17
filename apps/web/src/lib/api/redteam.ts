// Red-Teamer typed client — Battle Card contract, Phase3-Design §1.2 (verbatim).
// The backend endpoint lands in Phase 3 (Task 3.2); the dev adapter
// (lib/api/dev/redteam.ts) mirrors this schema exactly for development.
// OWNER RULING 2 (2026-09-16): do not invent response shapes — every field
// below comes straight from the design doc.

import { useMutation } from "@tanstack/react-query";

import { apiPost } from "@/lib/api/client";
import { generateBattleCardDev } from "@/lib/api/dev/redteam";

/** §1.2: severity is HIGH|MED|LOW — not the MVP mock's Critical/High/Moderate. */
export type BattleSeverity = "HIGH" | "MED" | "LOW";

/** §1.2 procedural_flaws[] item. `authority` entries are namespace-qualified
 *  document ids: "B:doc_uuid" (Vault B) or "A:doc_uuid" (Vault A). */
export interface ProceduralFlaw {
  flaw: string;
  basis: string;
  authority: string[];
  severity: BattleSeverity;
  confidence: number;
}

/** §1.2 opposing_arguments[] item. strength is 0–10 (the MVP mock's /100 was
 *  a mock artifact; the contract says `strength: 7`). */
export interface OpposingArgument {
  argument: string;
  strength: number;
  our_counter: string;
  authority: string[];
  confidence: number;
  manual_review: boolean;
}

/** §1.2 sections object. */
export interface BattleCardSections {
  procedural_flaws: ProceduralFlaw[];
  opposing_arguments: OpposingArgument[];
  jurisdictional_notes: string[];
}

/** §1.2 Battle Card — the contract every agent stage produces/consumes. */
export interface BattleCard {
  matter_id: string;
  source_document_id: string;
  generated_at: string;
  sections: BattleCardSections;
  critic_verdict: {
    pass: boolean;
    regenerations: number;
    downgraded_sections: string[];
  };
}

/**
 * Request shape is NOT defined in §1.2 (Phase 3 will fix the upload+analyze
 * flow). This provisional shape exists so the typed client can be built now;
 * it will be reconciled with the Phase 3 endpoint when that task starts.
 */
export interface RedteamRequest {
  document_name: string;
  content_base64: string;
}

const USE_DEV_ADAPTER = import.meta.env.VITE_API_DEV_ADAPTER === "1";

export function generateBattleCard(req: RedteamRequest): Promise<BattleCard> {
  return USE_DEV_ADAPTER
    ? generateBattleCardDev(req)
    : apiPost<BattleCard, RedteamRequest>("/v1/redteam/battle-card", req);
}

export function useBattleCard() {
  return useMutation({ mutationFn: generateBattleCard });
}
