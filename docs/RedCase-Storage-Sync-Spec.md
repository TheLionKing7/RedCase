# RedCase Storage Adapter & Vault Sync Spec
**Status:** Phase 4 design authority (2026-09-23) · Adapts the external "file routing + BYO-storage" design to RedCase's existing architecture · Extends IA Spec §2 (Integrations), Addendum §7/§10

---

## 1. Verdict on the imported design

Adopt: the **Storage Adapter Layer** (one interface: `put/get/list/move/delete/presign`), the **integrity model** (checksums at write + on every sync pass + nightly reconciliation), **immutable versions** (never overwrite), **conflict routing to `/_conflicts/`** (never auto-delete), and the **backup-first commercial wedge**. All correct, all ours now.

Adapt (critically — these protect existing contracts):

### 1.1 Physical keys stay content-addressed; friendly names are a *display/sync-materialization* layer
The proposed naming (`AcmeLLC_Litigation_Brief_20260923_001.pdf`) must **never** be the storage identity. Our ingestion is hash-idempotent (`documents.pdf_sha256` dedup), citations are page-pinned to source PDFs, and integrity is content-addressed. Renaming physical keys breaks dedup and severs the citation→source link. Instead:
- **Physical key** (unchanged): content hash + extension.
- **`documents.display_name`** (new column): the router-generated friendly name, shown in UI, used as the download filename, and materialized as the on-disk name **at sync time** when publishing to client storage.

### 1.2 Routing taxonomy maps to existing schema — no parallel classification
- Category ← the document's **matter's practice area** (existing `tenant_practice_areas` / matter link), falling back to `doc_type`. Rules-first, exactly as the source design's own phasing suggests; AI classification is a later upgrade *writing into the same fields*, not a new taxonomy.
- Folder plan: `/{firm_slug}/{practice_area}/{year}/{year-month}/` with the friendly filename materialized inside. Lazy folder creation, sequence numbers per (firm, matter, day).

### 1.3 The DB-index / client-storage model is already our model
`documents` + chunks + `pdf_sha256` already implement "our DB is the index." The sync engine's job is therefore *export/import reconciliation against an index that already exists* — half the design's Phase 2 is already built.

### 1.4 Vault A encryption boundary
Source PDFs in Supabase Storage are server-side encrypted; **chunk text** for CONFIDENTIAL+ is envelope-encrypted at the app layer. Sync therefore moves *source documents* (reversible, firm-controller-owned target) — never decrypted chunks. Client-linked storage is the **firm's own system** (they remain controller), which simplifies the NDPA posture; add one register line, no transfer assessment.

## 2. Architecture (as adapted)

```
Upload/API/email-in → File Router (classify → normalize → display_name → route plan)
  → ingest into vault (existing pipeline: hash idempotency, page-tracked chunks, grants)
  → SAL.put(source_pdf) with post-write SHA-256 verify (db hash == provider hash)

Sync Engine (per linked storage):
  Outbound mirror: vault documents → client storage, display_name materialized
  Inbound watch:   provider poll/webhook → candidate imports (dedup by hash → classify → vault)
  Nightly reconciliation: index vs listing; drift flagged; conflicts → /_conflicts/ + alert
  Versions: immutable; soft-delete + 30-day trash before purge; audit every touch

SAL adapters: S3 · GCS · Azure Blob · Google Drive · Dropbox · SharePoint → RedCase Cloud (Phase 5)
```

## 3. Build order (inside the phase map)

| Step | Content |
|---|---|
| P4-S1 | SAL interface + first adapter (Google Drive — where small firms already live) + `display_name` router + outbound mirror job |
| P4-S2 | Inbound watch + dedup import + reconciliation job + conflicts UI |
| P4-S3 | More adapters (S3, SharePoint) + AI classification upgrade |
| P5-S1 | **RedCase Cloud adapter**: replica/backup tier first (mirror linked storage → RedCase Cloud, DR sale), then primary-storage tier with per-firm isolation, GB+egress metering, hot/warm/cold tiering, migration tool |

## 4. Commercial note (why backup-first is right)

Selling storage means 24/7 SLA, data-loss liability, and egress unit-economics — real capital obligations. The replica tier monetizes the same trust with a fraction of the liability ("we mirror your vault for disaster recovery"), and the migration tool converts it into a primary-storage upsell. Sequence: replica → primary → tiering discounts.

## 5. What this does NOT touch

Grounding contract, citation pinning, RLS/grants, envelope crypto, ZDR, the agent taxonomy. Sync operates *below* all of them, on source documents only.
