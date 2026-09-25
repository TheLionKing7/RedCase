// Thin typed fetch client for the RedCase FastAPI backend at /v1/*.
//
// Auth (owner ruling 3, 2026-09-16): Supabase Auth email magic link; the
// FastAPI backend verifies the Supabase JWT (shared secret) and derives
// user_ref + tenant_id from the claims for the RLS session vars and
// query_audit. This client only ever forwards the user's JWT — it holds no
// API keys and no service-role material (ZDR convention 1: nothing secret in
// the bundle).

import { getAccessToken } from "@/lib/auth/supabase";

export const API_BASE_URL =
  import.meta.env.VITE_API_URL ??
  import.meta.env.VITE_API_BASE_URL ??
  (import.meta.env.DEV ? "http://127.0.0.1:8000" : "https://api.redcase.xyz");

export class ApiError extends Error {
  readonly status: number;
  readonly body: string;

  constructor(status: number, body: string) {
    super(`API ${status}: ${body.slice(0, 200)}`);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }

  /** 401 → the Supabase session is missing or expired; prompt sign-in. */
  get isAuthError(): boolean {
    return this.status === 401 || this.status === 403;
  }
}

export async function apiPost<TResponse, TRequest>(
  path: string,
  body: TRequest,
  opts: { signal?: AbortSignal } = {},
): Promise<TResponse> {
  const headers: Record<string, string> = {
    "content-type": "application/json",
  };
  const token = getAccessToken();
  if (token) headers["authorization"] = `Bearer ${token}`;

  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      signal: opts.signal ?? null,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError(0, "network unreachable — is the FastAPI backend up?");
  }

  const text = await res.text();
  if (!res.ok) throw new ApiError(res.status, text);
  if (res.status === 204 || !text) return undefined as TResponse;
  return JSON.parse(text) as TResponse;
}

/** GET variant for list endpoints (e.g. /v1/deadlines/events in Phase 3). */
export async function apiGet<TResponse>(
  path: string,
  opts: { signal?: AbortSignal } = {},
): Promise<TResponse> {
  const headers: Record<string, string> = {};
  const token = getAccessToken();
  if (token) headers["authorization"] = `Bearer ${token}`;

  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      method: "GET",
      headers,
      signal: opts.signal ?? null,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError(0, "network unreachable — is the FastAPI backend up?");
  }

  const text = await res.text();
  if (!res.ok) throw new ApiError(res.status, text);
  if (res.status === 204 || !text) return undefined as TResponse;
  return JSON.parse(text) as TResponse;
}

export async function apiDelete<TResponse = void>(path: string, opts: { signal?: AbortSignal } = {}): Promise<TResponse> {
  const token = getAccessToken();
  const res = await fetch(`${API_BASE_URL}${path}`, { method: "DELETE", headers: token ? { authorization: `Bearer ${token}` } : {}, signal: opts.signal ?? null });
  const text = await res.text();
  if (!res.ok) throw new ApiError(res.status, text);
  return (text ? JSON.parse(text) : undefined) as TResponse;
}

/** PUT variant for idempotent create-or-update endpoints (e.g. /v1/persona). */
export async function apiPut<TResponse, TRequest>(
  path: string,
  body: TRequest,
  opts: { signal?: AbortSignal } = {},
): Promise<TResponse> {
  const headers: Record<string, string> = {
    "content-type": "application/json",
  };
  const token = getAccessToken();
  if (token) headers["authorization"] = `Bearer ${token}`;

  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      method: "PUT",
      headers,
      body: JSON.stringify(body),
      signal: opts.signal ?? null,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError(0, "network unreachable — is the FastAPI backend up?");
  }

  const text = await res.text();
  if (!res.ok) throw new ApiError(res.status, text);
  if (res.status === 204 || !text) return undefined as TResponse;
  return JSON.parse(text) as TResponse;
}

/** Raw-body upload path (no JSON serialization); progress is reported by XHR. */
export function apiUpload<TResponse>(
  path: string,
  file: File,
  onProgress: (percent: number) => void,
): Promise<TResponse> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE_URL}${path}`);
    const token = getAccessToken();
    if (token) xhr.setRequestHeader("authorization", `Bearer ${token}`);
    xhr.setRequestHeader("content-type", file.type || "application/octet-stream");
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(Math.round((event.loaded / event.total) * 100));
    };
    xhr.onerror = () => reject(new ApiError(0, "network unreachable — is the FastAPI backend up?"));
    xhr.onload = () => {
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new ApiError(xhr.status, xhr.responseText));
        return;
      }
      try {
        resolve(JSON.parse(xhr.responseText) as TResponse);
      } catch {
        reject(new ApiError(xhr.status, "invalid upload response"));
      }
    };
    xhr.send(file);
  });
}
