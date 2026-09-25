import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api/client";

export interface VaultDocument {
  document_id: string;
  title: string | null;
  citation: string | null;
  doc_type: string | null;
  classification: string | null;
  ingested_at: string | null;
  matter_id: string | null;
}

export function useVaultDocuments(vaultType: "firm" | "juris") {
  return useQuery({
    queryKey: ["vault", "documents", vaultType],
    queryFn: () =>
      apiGet<{ documents: VaultDocument[] }>(
        `/v1/vault/documents?vault_type=${vaultType}`,
      ),
  });
}
