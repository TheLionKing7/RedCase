// DEV ADAPTER — Statutory Tracker. Mirrors the Phase3 §3.1 deadline_events
// shape EXACTLY (owner ruling 2); content is converted from the former MVP
// mock so the approved UI stays reviewable until the Phase 3 endpoint lands.
// Selected only when VITE_API_DEV_ADAPTER=1 (see lib/api/deadlines.ts).
//
// Dates are computed relative to TODAY so the calendar and status chips are
// always live. rule_id is null on every row — the UI therefore shows the
// "⚠ unvalidated rule" warning, which is exactly what the design prescribes
// for rows counsel has not yet validated (Phase3 §3.1 seeding note).

import type { DeadlineEvent } from "@/lib/api/deadlines";

const TENANT = "a0000001-0000-4000-8000-000000000001";
const MATTER_ZENITH = "3f6c8b20-7d1e-4f5a-9c2d-5e8a1b3d4f60";
const MATTER_ADEYEMI = "8c1e2d40-9a3b-4c7e-b2f5-6d0e9a1c3b78";

function iso(daysFromNow: number): string {
  const d = new Date();
  d.setDate(d.getDate() + daysFromNow);
  return d.toISOString().slice(0, 10);
}

function isoNow(): string {
  return new Date().toISOString();
}

export function listDeadlineEventsDev(): Promise<DeadlineEvent[]> {
  const rows: Array<Omit<DeadlineEvent, "id" | "created_at">> = [
    {
      tenant_id: TENANT,
      matter_id: MATTER_ZENITH,
      source_document_id: null,
      rule_id: null,
      event_type: "FILING_DEADLINE",
      description: "File Memorandum of Conditional Appearance",
      trigger_date: iso(-11),
      due_date: iso(1),
      confidence: 0.9,
      status: "PENDING",
      assigned_to: null,
    },
    {
      tenant_id: TENANT,
      matter_id: MATTER_ADEYEMI,
      source_document_id: null,
      rule_id: null,
      event_type: "FILING_DEADLINE",
      description: "Reply on Points of Law to Counter-Affidavit",
      trigger_date: iso(-5),
      due_date: iso(2),
      confidence: 0.85,
      status: "PENDING",
      assigned_to: null,
    },
    {
      tenant_id: TENANT,
      matter_id: MATTER_ADEYEMI,
      source_document_id: null,
      rule_id: null,
      event_type: "HEARING",
      description: "Hearing — Tax Appeal Tribunal, Lagos Zone",
      trigger_date: null,
      due_date: iso(4),
      confidence: 1.0,
      status: "PENDING",
      assigned_to: null,
    },
    {
      tenant_id: TENANT,
      matter_id: MATTER_ZENITH,
      source_document_id: null,
      rule_id: null,
      event_type: "FILING_DEADLINE",
      description: "Notice of Appeal (interlocutory) — filing window closes",
      trigger_date: iso(-12),
      due_date: iso(2),
      confidence: 0.8,
      status: "PENDING",
      assigned_to: null,
    },
    {
      tenant_id: TENANT,
      matter_id: MATTER_ZENITH,
      source_document_id: null,
      rule_id: null,
      event_type: "FILING_DEADLINE",
      description: "Transmit Record of Appeal to CA Registry",
      trigger_date: iso(-55),
      due_date: iso(5),
      confidence: 0.75,
      status: "NOTIFIED",
      assigned_to: null,
    },
    {
      tenant_id: TENANT,
      matter_id: MATTER_ZENITH,
      source_document_id: null,
      rule_id: null,
      event_type: "FILING_DEADLINE",
      description: "Motion on Notice for Stay Pending Arbitration",
      trigger_date: iso(-10),
      due_date: iso(8),
      confidence: 0.7,
      status: "PENDING",
      assigned_to: null,
    },
    {
      tenant_id: TENANT,
      matter_id: MATTER_ADEYEMI,
      source_document_id: null,
      rule_id: null,
      event_type: "FILING_DEADLINE",
      description: "Final Written Address (Claimant)",
      trigger_date: iso(-9),
      due_date: iso(12),
      confidence: 0.65,
      status: "PENDING",
      assigned_to: null,
    },
    {
      tenant_id: TENANT,
      matter_id: MATTER_ZENITH,
      source_document_id: null,
      rule_id: null,
      event_type: "FILING_DEADLINE",
      description: "File Statement of Defence — window closed (filed on time)",
      trigger_date: iso(-25),
      due_date: iso(-18),
      confidence: 1.0,
      status: "NOTIFIED",
      assigned_to: null,
    },
    {
      tenant_id: TENANT,
      matter_id: MATTER_ZENITH,
      source_document_id: null,
      rule_id: null,
      event_type: "LIMITATION",
      description:
        "Limitation period — action in contract (6 years, unvalidated rule)",
      trigger_date: iso(-2195),
      due_date: iso(-3),
      confidence: 0.4,
      status: "DISMISSED",
      assigned_to: null,
    },
    {
      tenant_id: TENANT,
      matter_id: MATTER_ADEYEMI,
      source_document_id: null,
      rule_id: null,
      event_type: "FILING_DEADLINE",
      description: "File defence to amended statement of claim — MISSED",
      trigger_date: iso(-30),
      due_date: iso(-2),
      confidence: 0.95,
      status: "MISSED",
      assigned_to: null,
    },
  ];
  const events: DeadlineEvent[] = rows.map((r, i) => ({
    ...r,
    id: `00000000-0000-4000-8000-0000000000${String(i + 1).padStart(2, "0")}`,
    created_at: isoNow(),
  }));
  return new Promise((resolve) => setTimeout(() => resolve(events), 300));
}
