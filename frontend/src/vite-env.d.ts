/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

interface Window {
  pulseGridSecurity?: {
    getCsrfHeaders: () => HeadersInit | Promise<HeadersInit>;
  };
}
