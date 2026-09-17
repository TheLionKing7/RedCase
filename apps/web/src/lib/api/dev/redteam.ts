// DEV ADAPTER — Red-Teamer. Mirrors the Phase3 §1.2 Battle Card schema
// EXACTLY (owner ruling 2); content is converted from the former MVP mock so
// the approved UI stays reviewable until the Phase 3 endpoint lands.
// Selected only when VITE_API_DEV_ADAPTER=1 (see lib/api/redteam.ts).

import type { BattleCard, RedteamRequest } from "@/lib/api/redteam";

const MATTER_ID = "3f6c8b20-7d1e-4f5a-9c2d-5e8a1b3d4f60";
const SOURCE_DOC_ID = "b7a1c9d4-2e6f-4a8b-b3c5-1d9e7f2a4c68";

export function generateBattleCardDev(
  _req: RedteamRequest,
): Promise<BattleCard> {
  return new Promise((resolve) =>
    setTimeout(
      () =>
        resolve({
          matter_id: MATTER_ID,
          source_document_id: SOURCE_DOC_ID,
          generated_at: new Date().toISOString(),
          sections: {
            procedural_flaws: [
              {
                flaw: "No pre-action protocol form filed",
                basis:
                  "The originating summons is unaccompanied by Form 01 and the requisite written statements on oath. This is a condition precedent, not a mere irregularity.",
                authority: ["B:86c9c070-2304-456a-8a62-4ec8bc0d0b95"],
                severity: "HIGH",
                confidence: 0.91,
              },
              {
                flaw: "Affidavit contains legal argument and conclusions",
                basis:
                  "Paragraphs 9, 14 and 21 of the supporting affidavit contain submissions and prayers, offending the rule against argumentative affidavits; liable to be struck out.",
                authority: ["B:2a17bb5b-a6d5-41bd-b66e-bf3505bc6380"],
                severity: "MED",
                confidence: 0.84,
              },
              {
                flaw: "Arbitration clause not pleaded around",
                basis:
                  "Clause 34 of the JV Agreement mandates LCA arbitration. The brief does not plead waiver or invalidity, exposing the suit to a stay application.",
                authority: ["B:86c9c070-2304-456a-8a62-4ec8bc0d0b95"],
                severity: "HIGH",
                confidence: 0.88,
              },
              {
                flaw: "Exhibits not certified",
                basis:
                  "Exhibits ZE-3 to ZE-7 are photocopies of public documents tendered without CTC endorsement; inadmissible as secondary evidence.",
                authority: [],
                severity: "LOW",
                confidence: 0.72,
              },
            ],
            opposing_arguments: [
              {
                argument:
                  "Meridian repudiated the charterparty by withdrawing the vessel on 11 March 2026.",
                strength: 7,
                our_counter:
                  "Withdrawal followed 41 days of unpaid hire; the anti-technicality notice was validly served, converting withdrawal into a contractual right, not repudiation.",
                authority: ["B:86c9c070-2304-456a-8a62-4ec8bc0d0b95"],
                confidence: 0.9,
                manual_review: false,
              },
              {
                argument:
                  "Force majeure notice was served out of time and is void.",
                strength: 4,
                our_counter:
                  "Clause 22.3 contains no time bar; the 14-day requirement applies only to claims for extension, not to suspension of obligations.",
                authority: [],
                confidence: 0.86,
                manual_review: false,
              },
              {
                argument:
                  "The Federal High Court has admiralty jurisdiction over the claim.",
                strength: 6,
                our_counter:
                  "Claim is in substance for breach of a joint venture funding obligation — not a maritime claim under s.2 AJA 1991. Madukolu competence test fails on subject-matter.",
                authority: ["B:2a17bb5b-a6d5-41bd-b66e-bf3505bc6380"],
                confidence: 0.82,
                manual_review: true,
              },
              {
                argument:
                  "Liquidated damages of US$4.2m are enforceable as agreed.",
                strength: 3,
                our_counter:
                  "Sum is a penalty: it is not a genuine pre-estimate of loss and exceeds total contract value for the affected period by 2.4x.",
                authority: [],
                confidence: 0.78,
                manual_review: false,
              },
            ],
            jurisdictional_notes: [
              "Madukolu competence test: due process and fulfilment of every condition precedent defeats the suit on the unfiled pre-action protocol.",
              "Where parties agree to arbitrate, the court should stay proceedings absent strong cause.",
            ],
          },
          critic_verdict: {
            pass: true,
            regenerations: 0,
            downgraded_sections: [],
          },
        }),
      900,
    ),
  );
}
