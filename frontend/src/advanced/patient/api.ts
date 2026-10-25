import { ApiError, type ApiClient, type ApiRequestOptions } from "../../api/client";
import { formatDateTime } from "../../hospital/ui";

const MAX_ID = 9223372036854775807n;
const MAX_VERSION = Number.MAX_SAFE_INTEGER;

export function isId(value: string): boolean {
  if (!/^[1-9][0-9]{0,18}$/.test(value)) return false;
  try {
    return BigInt(value) <= MAX_ID;
  } catch {
    return false;
  }
}

export function parseId(value: string, label = "ID"): string {
  const normalized = value.trim();
  if (!isId(normalized)) {
    throw new Error(`${label} must be a positive decimal ID.`);
  }
  return normalized;
}

export function parseVersion(value: string, label = "Version"): number {
  const normalized = value.trim();
  if (!/^[1-9][0-9]*$/.test(normalized)) {
    throw new Error(`${label} must be a positive whole number.`);
  }
  const parsed = Number(normalized);
  if (!Number.isSafeInteger(parsed) || parsed > MAX_VERSION) {
    throw new Error(`${label} is outside the supported range.`);
  }
  return parsed;
}

export function buildQuery(
  path: string,
  values: Record<string, string | undefined>,
): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value !== undefined && value !== "") params.set(key, value);
  }
  return params.size ? `${path}?${params.toString()}` : path;
}

export function newIdempotencyKey(): string {
  if (typeof crypto === "undefined" || typeof crypto.randomUUID !== "function") {
    throw new Error("Secure command identifiers are unavailable. Reload and try again.");
  }
  return crypto.randomUUID();
}

export async function sendCommand<T>(
  api: ApiClient,
  path: string,
  body: unknown,
  options: Pick<ApiRequestOptions, "ifMatch" | "signal"> = {},
  idempotencyKey = newIdempotencyKey(),
): Promise<{ data: T; etag: string | null }> {
  const response = await api.requestWithMetadata<T>(path, {
    method: "POST",
    body,
    idempotencyKey,
    ...(options.ifMatch ? { ifMatch: options.ifMatch } : {}),
    ...(options.signal ? { signal: options.signal } : {}),
  });
  return { data: response.data, etag: response.etag };
}

export function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 412) {
      return `${error.message} Refresh to load the latest version before trying again.`;
    }
    return error.message;
  }
  return error instanceof Error ? error.message : "The request could not be completed.";
}

export function formatTime(value: string | null | undefined): string {
  return formatDateTime(value);
}

export function idempotencyRecovery(error: unknown): boolean {
  return error instanceof ApiError &&
    (error.status === 0 || error.status >= 500 || error.code === "invalid_response");
}
