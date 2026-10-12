import { ApiError } from "../api/client";

export interface Phase4ErrorDetails {
  message: string;
  status?: number;
  code?: string;
  retryAfterSeconds?: number;
}

type ErrorWithMetadata = {
  message?: unknown;
  status?: unknown;
  code?: unknown;
  retryAfter?: unknown;
  retryAfterSeconds?: unknown;
  headers?: unknown;
  response?: unknown;
};

function record(value: unknown): ErrorWithMetadata | undefined {
  return typeof value === "object" && value !== null ? value as ErrorWithMetadata : undefined;
}

function readHeader(source: unknown, name: string): string | null {
  if (source instanceof Headers) return source.get(name);
  const value = record(source);
  const getter = value ? (value as unknown as { get?: unknown }).get : undefined;
  if (typeof getter === "function") {
    try {
      const result = (getter as (headerName: string) => unknown)(name);
      return typeof result === "string" ? result : null;
    } catch {
      return null;
    }
  }
  if (value && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    const found = entries.find(([key]) => key.toLowerCase() === name.toLowerCase());
    return typeof found?.[1] === "string" ? found[1] : null;
  }
  return null;
}

function parseRetryAfter(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value) && value >= 0) {
    return Math.ceil(value);
  }
  if (typeof value !== "string" || value.trim() === "") return undefined;
  const seconds = Number(value);
  if (Number.isFinite(seconds) && seconds >= 0) return Math.ceil(seconds);
  const dateMs = Date.parse(value);
  if (!Number.isFinite(dateMs)) return undefined;
  return Math.max(0, Math.ceil((dateMs - Date.now()) / 1000));
}

export function getPhase4Error(error: unknown): Phase4ErrorDetails {
  const metadata = record(error);
  const nestedResponse = record(metadata?.response);
  const headers = metadata?.headers ?? nestedResponse?.headers;
  const retryAfterSeconds = parseRetryAfter(
    metadata?.retryAfterSeconds
      ?? metadata?.retryAfter
      ?? readHeader(headers, "Retry-After"),
  );
  const message = error instanceof Error
    ? error.message
    : typeof metadata?.message === "string"
      ? metadata.message
      : "The service could not complete this request.";
  const status = typeof metadata?.status === "number" ? metadata.status : undefined;
  const code = typeof metadata?.code === "string"
    ? metadata.code
    : error instanceof ApiError
      ? error.code
      : undefined;

  return {
    message,
    ...(status === undefined ? {} : { status }),
    ...(code === undefined ? {} : { code }),
    ...(retryAfterSeconds === undefined ? {} : { retryAfterSeconds }),
  };
}

export function feedbackMessage(
  error: unknown,
  operationLabel = "This request",
): string {
  const details = getPhase4Error(error);
  if (details.status === 429) {
    if (details.retryAfterSeconds !== undefined) {
      const seconds = details.retryAfterSeconds;
      const wait = seconds <= 1 ? "a few seconds" : "about " + seconds + " seconds";
      return operationLabel + " is temporarily rate limited. Please wait " + wait + " before trying again.";
    }
    return operationLabel + " is temporarily rate limited. Please wait a moment before trying again.";
  }
  if (details.status === 503) {
    return operationLabel + " is temporarily unavailable. You can try again shortly.";
  }
  return details.message || operationLabel + " could not be completed.";
}

export function createIdempotencyKey(): string {
  if (typeof crypto === "undefined" || typeof crypto.randomUUID !== "function") {
    throw new Error("Secure request identifiers are unavailable. Reload this page before trying again.");
  }
  return crypto.randomUUID();
}

export function isCanonicalId(value: string): boolean {
  if (!/^[1-9][0-9]{0,18}$/.test(value)) return false;
  try {
    return BigInt(value) <= 9223372036854775807n;
  } catch {
    return false;
  }
}

export function quoteVersion(version: number): string {
  return "\"" + String(version) + "\"";
}
