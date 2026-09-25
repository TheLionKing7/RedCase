/// <reference types="vite/client" />

// Vite env typing for the RedCase frontend (see .env.example).
interface ImportMetaEnv {
  /** FastAPI backend base URL, e.g. https://api.redcase.xyz. */
  readonly VITE_API_URL?: string;
  /** FastAPI backend base URL, e.g. http://127.0.0.1:8000 */
  readonly VITE_API_BASE_URL?: string;
  /** Supabase project URL for Auth (magic link). */
  readonly VITE_SUPABASE_URL?: string;
  /** Supabase anon key — publishable, NOT a secret. */
  readonly VITE_SUPABASE_ANON_KEY?: string;
  /** Set to "1" to route API calls through the schema-exact dev adapters
   *  (lib/api/dev/*) while the Phase 3 endpoints are unbuilt. */
  readonly VITE_API_DEV_ADAPTER?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
