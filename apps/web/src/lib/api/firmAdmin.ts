// Firm Command typed client — Addendum §8.5 (admin-capability surface).
// These shapes mirror the FastAPI wire model in app/routers/firm_admin.py
// (owner ruling 2 — no invented fields). All of these endpoints are gated
// server-side by `require_firm_admin`; the JWT `app_metadata.is_firm_admin`
// claim must be present or FastAPI returns 403. This client only shapes the calls.

import { useQuery } from "@tanstack/react-query";

import { apiGet } from "@/lib/api/client";

/** subscriptions billing anchors (migration 0004). */
export interface FirmSeats {
  plan: string;
  status: string;
  max_seats: number;
  current_seats: number;
}

export function getFirmOverview(): Promise<{ seats: FirmSeats }> {
  return apiGet<{ seats: FirmSeats }>("/v1/firm/admin/overview");
}

export function useFirmOverview() {
  return useQuery({
    queryKey: ["firm", "admin", "overview"],
    queryFn: getFirmOverview,
  });
}

/** One row on the append-only admin grant/revoke ledger. */
export interface AdminLedgerEntry {
  id: string;
  user_ref: string;
  action: "GRANTED" | "REVOKED";
  granted_by: string;
  created_at: string;
}

export function getAdminLedger(): Promise<{ entries: AdminLedgerEntry[] }> {
  return apiGet<{ entries: AdminLedgerEntry[] }>("/v1/firm/admin/admins");
}

export function useAdminLedger() {
  return useQuery({
    queryKey: ["firm", "admin", "ledger"],
    queryFn: getAdminLedger,
  });
}

/** Firm identity (no PII). */
export interface FirmSettings {
  firm: { name: string; slug: string; jurisdiction: string };
}

export function getFirmSettings(): Promise<FirmSettings> {
  return apiGet<FirmSettings>("/v1/firm/admin/settings");
}

export function useFirmSettings() {
  return useQuery({
    queryKey: ["firm", "admin", "settings"],
    queryFn: getFirmSettings,
  });
}
