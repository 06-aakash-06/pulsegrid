export interface ApiClientConfig {
  baseUrl?: string;
  fetcher?: typeof fetch;
}

export interface ApiRequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  headers?: HeadersInit;
  accessToken?: string;
  credentials?: RequestCredentials;
  idempotencyKey?: string;
  ifMatch?: string;
  requestId?: string;
  correlationId?: string;
  traceparent?: string;
  signal?: AbortSignal;
}

export interface ApiErrorEnvelope {
  error?: {
    code?: string;
    message?: string;
    request_id?: string;
  };
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId?: string;

  constructor(
    message: string,
    status: number,
    code = "request_failed",
    requestId?: string,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

export class ApiConfigurationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ApiConfigurationError";
  }
}

export interface ApiClient {
  request<T>(path: string, options?: ApiRequestOptions): Promise<T>;
  requestWithMetadata<T>(path: string, options?: ApiRequestOptions): Promise<ApiResponse<T>>;
}

export interface ApiResponse<T> {
  data: T;
  status: number;
  etag: string | null;
  headers: Headers;
}

function createRequestId(): string {
  if (typeof crypto === "undefined" || typeof crypto.randomUUID !== "function") {
    throw new ApiConfigurationError("Secure request identifiers are unavailable.");
  }
  return crypto.randomUUID();
}

function protocolId(value?: string): string {
  if (value === undefined) return createRequestId();
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value)) {
    throw new ApiConfigurationError("Request and correlation identifiers must be UUIDs.");
  }
  return value;
}

function joinUrl(baseUrl: string, path: string): string {
  if (!path.startsWith("/") || path.startsWith("//")) {
    throw new ApiConfigurationError("API paths must be origin-relative paths.");
  }
  return `${baseUrl.replace(/\/$/, "")}${path}`;
}

async function readResponse<T>(response: Response): Promise<T> {
  if (response.status === 204) return undefined as T;

  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.toLowerCase().includes("application/json")) {
    if (!response.ok) {
      throw new ApiError("The service could not complete this request.", response.status);
    }
    throw new ApiError("The service returned an unsupported response.", response.status, "invalid_response");
  }

  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new ApiError("The service returned an unreadable response.", response.status, "invalid_response");
  }

  if (!response.ok) {
    const envelope = payload !== null && typeof payload === "object"
      ? payload as ApiErrorEnvelope
      : {};
    const error = envelope.error && typeof envelope.error === "object" ? envelope.error : undefined;
    throw new ApiError(
      error?.message || "The service could not complete this request.",
      response.status,
      error?.code || "request_failed",
      error?.request_id,
    );
  }

  return payload as T;
}

export function createApiClient(config: ApiClientConfig = {}): ApiClient {
  const baseUrl = (config.baseUrl ?? "").trim();
  const fetcher = config.fetcher ?? fetch.bind(globalThis);

  async function requestWithMetadata<T>(path: string, options: ApiRequestOptions = {}): Promise<ApiResponse<T>> {
    const headers = new Headers(options.headers);
    headers.set("Accept", "application/json");
    headers.set("X-Request-ID", protocolId(options.requestId));
    headers.set("X-Correlation-ID", protocolId(options.correlationId));

    if (options.body !== undefined) headers.set("Content-Type", "application/json");
    if (options.accessToken) headers.set("Authorization", `Bearer ${options.accessToken}`);
    if (options.idempotencyKey) headers.set("Idempotency-Key", options.idempotencyKey);
    if (options.ifMatch) headers.set("If-Match", options.ifMatch);
    if (options.traceparent) headers.set("traceparent", options.traceparent);

    const response = await fetcher(joinUrl(baseUrl, path), {
      method: options.method ?? "GET",
      headers,
      credentials: options.credentials ?? "omit",
      signal: options.signal,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });

    const data = await readResponse<T>(response);
    return {
      data,
      status: response.status,
      etag: response.headers.get("ETag"),
      headers: response.headers,
    };
  }

  return {
    async request<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
      const response = await requestWithMetadata<T>(path, options);
      return response.data;
    },
    requestWithMetadata,
  };
}

export const apiClient = createApiClient({
  baseUrl: import.meta.env.VITE_API_BASE_URL ?? "",
});
