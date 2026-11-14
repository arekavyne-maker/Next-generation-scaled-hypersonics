/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Force the deterministic mock dataset; no network requests are made. */
  readonly VITE_USE_MOCK?: string;
  /** API surface root. Path form (e.g. "/api") enables the dev proxy layout. */
  readonly VITE_API_BASE?: string;
  /** "proxy" (default in dev) or "direct". */
  readonly VITE_API_MODE?: string;
  /** Per-service base URL overrides, e.g. VITE_API_ONTOLOGY. */
  readonly VITE_API_ONTOLOGY?: string;
  readonly VITE_API_FABRIC?: string;
  readonly VITE_API_POLICY?: string;
  readonly VITE_API_AUDIT?: string;
  readonly VITE_API_THREAD?: string;
  readonly VITE_API_INGEST?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
