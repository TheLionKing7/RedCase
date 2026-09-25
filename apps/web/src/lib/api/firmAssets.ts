import { apiPost, apiUpload } from "@/lib/api/client";

export type FirmAssetType = "logo" | "rc-document" | "personal-id";
export interface UploadedFirmAsset {
  path: string;
  content_type: string;
  classification: string;
}

export function uploadFirmAsset(
  type: FirmAssetType,
  file: File,
  onProgress: (percent: number) => void,
) {
  return apiUpload<UploadedFirmAsset>(`/v1/firm/assets/${type}`, file, onProgress);
}

export async function getFirmAssetPreview(type: FirmAssetType, path: string) {
  const result = await apiPost<{ signed_url: string }, { path: string }>(
    `/v1/firm/assets/${type}/signed-url`,
    { path },
  );
  return result.signed_url;
}
